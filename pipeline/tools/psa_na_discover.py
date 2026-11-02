"""Probe PSA OpenSTAT for the Philippine national accounts (GDP), and the World Bank WDI for the Philippines.

  python -I pipeline/tools/psa_na_discover.py OUTDIR

Round na1: walks the OpenSTAT database tree, keeps every folder and table (tree.json), then for each table in a
national-accounts folder saves its metadata and, if under the cell limit, its full data as tidy rows (gzipped).
WDI: the Philippines' GDP series in US$ and real growth, as published (wdi.json).
"""
import gzip
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import psa  # noqa: E402

NA_WORDS = ("national account", "gross domestic", "gross national", "gdp", "gni", "economic account",
            "gross value added", "expenditure", "per capita")
WDI = ["NY.GDP.MKTP.CD", "NY.GDP.MKTP.KD", "NY.GDP.PCAP.CD", "NY.GDP.PCAP.KD", "NY.GDP.MKTP.KD.ZG",
       "NY.GDP.MKTP.KN", "NY.GDP.MKTP.CN", "NV.AGR.TOTL.KD.ZG", "NV.IND.TOTL.KD.ZG", "NV.SRV.TOTL.KD.ZG",
       "NV.IND.MANF.KD.ZG"]


def listing(path):
    time.sleep(0.4)
    return psa._request(f"{psa.BASE}/{path}" if path else psa.BASE)


def walk(path, depth, out, start):
    try:
        items = listing(path)
    except Exception as e:  # noqa: BLE001
        out.append({"path": path, "error": repr(e)[:300]})
        return
    for it in items:
        p = f"{path}/{it['id']}" if path else it["id"]
        out.append({"path": p, "type": it.get("type"), "text": it.get("text"), "updated": it.get("updated")})
        if it.get("type") == "l" and depth < 6 and time.time() - start < 1500:
            walk(p, depth + 1, out, start)


def is_na(rec, tree):
    text = (rec.get("text") or "").lower()
    if any(w in text for w in NA_WORDS):
        return True
    # anything under a folder whose name looks like national accounts
    parts = rec["path"].split("/")
    for i in range(1, len(parts)):
        anc = "/".join(parts[:i])
        t = next((r for r in tree if r["path"] == anc), None)
        if t and any(w in (t.get("text") or "").lower() for w in NA_WORDS):
            return True
    return False


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    start = time.time()
    tree = []
    walk("", 0, tree, start)
    (out / "tree.json").write_text(json.dumps(tree, ensure_ascii=False, indent=1))
    print("tree", len(tree))

    tables = [r for r in tree if r.get("type") == "t" and is_na(r, tree)]
    summary = {}
    for r in tables:
        if time.time() - start > 2400:
            summary[r["path"]] = {"skipped": "time"}
            continue
        name = r["path"].replace("/", "__")
        try:
            m = psa.meta(r["path"])
            (out / f"{name}.meta.json").write_text(json.dumps(m, ensure_ascii=False))
            cells = 1
            for v in m["variables"]:
                cells *= len(v["values"])
            info = {"text": r.get("text"), "updated": r.get("updated"), "cells": cells,
                    "vars": {v["code"]: len(v["values"]) for v in m["variables"]}}
            if cells <= 400_000:
                rows = psa.get(r["path"], {}, m)
                with gzip.open(out / f"{name}.json.gz", "wt", encoding="utf-8") as f:
                    json.dump(rows, f, ensure_ascii=False)
                info["rows"] = len(rows)
                info["nonnull"] = sum(x["value"] is not None for x in rows)
            summary[r["path"]] = info
            print(r["path"], info.get("rows"))
        except Exception as e:  # noqa: BLE001
            summary[r["path"]] = {"text": r.get("text"), "error": repr(e)[:300]}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))

    wdi = {}
    for code in WDI:
        url = f"https://api.worldbank.org/v2/country/PHL/indicator/{code}?format=json&per_page=200"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "asia-vitals", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as resp:
                d = json.loads(resp.read())
            wdi[code] = {"lastupdated": d[0].get("lastupdated"),
                         "values": {r["date"]: r["value"] for r in (d[1] or []) if r.get("value") is not None}}
        except Exception as e:  # noqa: BLE001
            wdi[code] = {"error": repr(e)[:300]}
    (out / "wdi.json").write_text(json.dumps(wdi, indent=1))
    print("done", round(time.time() - start), "s")


if __name__ == "__main__":
    main(sys.argv[1])
