"""Bank of Korea ECOS Open API client.

Uses the ECOS_KEY environment variable (repository secret) when set; otherwise ECOS's public
"sample" key, which returns at most 10 rows per call (so every query is paged by 10).

Series store (raw/kr/ecos/store.json.gz): {table: {item_code: {"name", "parent", "unit",
"values": {"YYYYMM": float}}}}, built by tools/ecos_backfill.py and kept current by the
Korea sources, which re-fetch only recent months.
"""
import gzip
import json
import os
import time
import urllib.parse
import urllib.request

from .common import RAW

KEY = os.environ.get("ECOS_KEY") or "sample"
PAGE = 10 if KEY == "sample" else 10000
BASE = "https://ecos.bok.or.kr/api"
UA = {"User-Agent": "Mozilla/5.0 (asia-vitals data pipeline; github.com/AsiaDecoded)"}
STORE = RAW / "kr" / "ecos" / "store.json.gz"
CALLS = {"n": 0}


def _get(parts, tries=4):
    url = f"{BASE}/" + "/".join(urllib.parse.quote(str(p), safe="*?") for p in parts)
    err = None
    for i in range(tries):
        try:
            CALLS["n"] += 1
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"ECOS request failed: {url.replace(KEY, '<key>')}: {err!r}")


def _paged(service, args):
    """All rows of a service call, paged by PAGE. Returns [] for ECOS 'no data' (INFO-200)."""
    rows, start, total = [], 1, None
    while True:
        r = _get([service, KEY, "json", "kr", start, start + PAGE - 1] + list(args))
        body = r.get(service)
        if not body:
            res = r.get("RESULT") or {}
            if res.get("CODE") == "INFO-200":  # no data for the request
                return rows
            raise RuntimeError(f"ECOS {service} {args}: {res}")
        total = int(body.get("list_total_count") or 0)
        rows += body.get("row") or []
        start += PAGE
        if start > total:
            return rows
        time.sleep(0.12)


def items(table):
    return _paged("StatisticItemList", [table])


def series(table, item, start, end):
    """Monthly rows of one item: [{"TIME", "DATA_VALUE", "ITEM_CODE1", "ITEM_NAME1", "UNIT_NAME"}]."""
    return _paged("StatisticSearch", [table, "M", start, end, item])


def month_all(table, ym):
    """Every item of a table for one month (item code left open)."""
    return _paged("StatisticSearch", [table, "M", ym, ym])


def load_store():
    if STORE.exists():
        with gzip.open(STORE, "rt") as f:
            return json.load(f)
    return {}


def save_store(store):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(STORE, "wt", compresslevel=9) as f:
        json.dump(store, f, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def put(store, table, rows, meta=None):
    """Merge ECOS rows into the store. Returns the number of values that changed."""
    t = store.setdefault(table, {})
    changed = 0
    for r in rows:
        code = r.get("ITEM_CODE1")
        v = r.get("DATA_VALUE")
        if code is None or v in (None, "", "-"):
            continue
        s = t.setdefault(code, {"name": r.get("ITEM_NAME1"), "parent": None, "unit": r.get("UNIT_NAME"), "values": {}})
        if meta and code in meta:
            s["parent"] = meta[code].get("P_ITEM_CODE")
        s["name"] = r.get("ITEM_NAME1") or s["name"]
        s["unit"] = r.get("UNIT_NAME") or s["unit"]
        if r.get("WGT") not in (None, ""):
            s.setdefault("wgt", {})[r["TIME"]] = float(r["WGT"])
        fv = float(v)
        if s["values"].get(r["TIME"]) != fv:
            changed += 1
            s["values"][r["TIME"]] = fv
    return changed
