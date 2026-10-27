"""SingStat Table Builder API client (no key): metadata and full table data, paged."""
import json
import time
import urllib.parse
import urllib.request

BASE = "https://tablebuilder.singstat.gov.sg/api/table"
UA = {"User-Agent": "Mozilla/5.0 (asia-vitals data pipeline; github.com/AsiaDecoded)", "Accept": "application/json"}
PAGE = 2000


def _get(url, tries=4):
    err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"SingStat request failed: {url}: {err!r}")


def search(keyword):
    q = urllib.parse.urlencode({"keyword": keyword, "searchOption": "all"})
    return (_get(f"{BASE}/resourceid?{q}").get("Data") or {}).get("records") or []


def metadata(table_id):
    return _get(f"{BASE}/metadata/{table_id}")["Data"]["records"]


def table(table_id):
    """Every row of a table with all its periods: {"meta": ..., "rows": [{seriesNo, rowText, uoM, footnote, columns:[{key,value}]}]}.

    The API pages by data points (offset/limit); a row can continue on the next page, so rows are merged by seriesNo.
    """
    meta = metadata(table_id)
    total = int(meta.get("total") or 0)
    rows, order = {}, []
    offset = 0
    while True:
        q = urllib.parse.urlencode({"offset": offset, "limit": PAGE})
        page = (_get(f"{BASE}/tabledata/{table_id}?{q}").get("Data") or {}).get("row") or []
        got = 0
        for r in page:
            k = r["seriesNo"]
            if k not in rows:
                rows[k] = {kk: r.get(kk) for kk in ("seriesNo", "rowText", "uoM", "footnote")}
                rows[k]["columns"] = {}
                order.append(k)
            for c in r.get("columns") or []:
                rows[k]["columns"][c["key"]] = c["value"]
                got += 1
        if not page or got == 0:
            break
        offset += PAGE
        if total and offset >= total:
            break
        time.sleep(0.3)
    out = []
    for k in order:
        r = rows[k]
        r["columns"] = [{"key": kk, "value": vv} for kk, vv in r["columns"].items()]
        out.append(r)
    n = sum(len(r["columns"]) for r in out)
    if total and n < total:
        raise RuntimeError(f"{table_id}: got {n} data points, metadata says {total}")
    return {"meta": meta, "rows": out}
