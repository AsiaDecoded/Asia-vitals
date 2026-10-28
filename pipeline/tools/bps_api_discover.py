"""Probe the BPS WebAPI (webapi.bps.go.id) for Indonesian price data: subjects, variables (dynamic tables) on
inflation, CPI, core, components and wholesale prices; their periods; and a sample of data for each.

  BPS_KEY=... python -I pipeline/tools/bps_api_discover.py OUTDIR

The key never appears in the saved output (URLs are stored with it masked).
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

KEY = os.environ.get("BPS_KEY", "").strip()
API = "https://webapi.bps.go.id/v1/api"
UA = {"User-Agent": "asia-vitals/1.0 (research dashboard)", "Accept": "application/json"}
WANT = re.compile(r"(?i)inflasi|indeks harga konsumen|\bIHK\b|inti|harga yang diatur|bergejolak|andil|"
                  r"perdagangan besar|IHPB|harga produsen|consumer price|core|wholesale|producer price|administered|volatile")


def get(path):
    url = f"{API}/{path.strip('/')}/key/{KEY}/"
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
            body = r.read()
            st = r.status
    except urllib.error.HTTPError as e:
        body, st = e.read(), e.code
    except Exception as e:  # noqa: BLE001
        body, st = repr(e).encode(), None
    time.sleep(0.3)
    try:
        return st, json.loads(body), round(time.time() - t0, 2)
    except Exception:  # noqa: BLE001
        return st, {"raw": body[:500].decode("utf-8", "replace")}, round(time.time() - t0, 2)


def rows_of(d):
    """WebAPI list answers: {"data-availability": ..., "data": [paging, [rows]]}."""
    try:
        return d["data"][0], d["data"][1]
    except Exception:  # noqa: BLE001
        return None, []


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    log = []

    def save(name, path, d, st, secs):
        (out / f"{name}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1))
        log.append({"name": name, "path": path, "status": st, "secs": secs})
        (out / "log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
        print(name, st, secs, flush=True)

    if not KEY:
        (out / "log.json").write_text('{"error": "BPS_KEY not set"}')
        print("BPS_KEY not set")
        return
    # subjects
    for lang in ("ind", "eng"):
        st, d, s = get(f"list/model/subject/domain/0000/lang/{lang}")
        save(f"subjects_{lang}", f"list/model/subject/domain/0000/lang/{lang}", d, st, s)
    # every variable (dynamic table) in the national domain, all pages
    allvars, page = [], 1
    while page < 80:
        p = f"list/model/var/domain/0000/lang/ind/page/{page}"
        st, d, s = get(p)
        paging, rows = rows_of(d)
        if page == 1:
            save("vars_page1", p, d, st, s)
        allvars += rows
        if not paging or page >= int(paging.get("pages", 1)):
            break
        page += 1
    (out / "vars_all.json").write_text(json.dumps(allvars, ensure_ascii=False, indent=1))
    hits = [v for v in allvars if WANT.search(json.dumps(v, ensure_ascii=False))]
    (out / "vars_hits.json").write_text(json.dumps(hits, ensure_ascii=False, indent=1))
    print(len(allvars), "vars;", len(hits), "hits", flush=True)
    # English titles for the hits
    eng, page = {}, 1
    while page < 80:
        st, d, s = get(f"list/model/var/domain/0000/lang/eng/page/{page}")
        paging, rows = rows_of(d)
        for v in rows:
            eng[v.get("var_id")] = v.get("title")
        if not paging or page >= int(paging.get("pages", 1)):
            break
        page += 1
    (out / "vars_hits_eng.json").write_text(json.dumps({h["var_id"]: eng.get(h["var_id"]) for h in hits},
                                                       ensure_ascii=False, indent=1))
    # periods and the latest data for each hit (at most 60)
    for v in hits[:60]:
        vid = v["var_id"]
        st, d, s = get(f"list/model/th/domain/0000/var/{vid}")
        save(f"th_{vid}", f"list/model/th/domain/0000/var/{vid}", d, st, s)
        _p, ths = rows_of(d)
        ths = sorted(ths, key=lambda t: str(t.get("th")))
        for t in ths[-2:]:
            p = f"list/model/data/domain/0000/var/{vid}/th/{t['th_id']}"
            st, dd, s = get(p)
            save(f"data_{vid}_{t['th']}", p, dd, st, s)


def scrub(out):
    """Remove the key from anything saved, in case an answer echoes it."""
    for f in Path(out).glob("*.json"):
        t = f.read_text()
        if KEY and KEY in t:
            f.write_text(t.replace(KEY, "***"))


if __name__ == "__main__":
    try:
        main(sys.argv[1])
    finally:
        scrub(sys.argv[1])
