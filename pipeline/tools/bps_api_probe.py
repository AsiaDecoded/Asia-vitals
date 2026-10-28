"""BPS WebAPI probe, round 4: every static table title (to find core / administered / volatile), the latest
inflation press releases, and 2026 data for the variables the dashboard would use.

  BPS_KEY=... python -I pipeline/tools/bps_api_probe.py OUTDIR
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bps_api_discover import KEY, get, rows_of, scrub  # noqa: E402

VARS = {  # var id: what it should be
    1: "headline m/m by city (and national?)",
    2249: "y/y 150 cities (2022=100)", 2245: "CPI 150 cities", 2388: "YTD 150 cities",
    2212: "CPI index group 01 and subgroups", 2223: "m/m group 01", 2234: "YTD group 01", 2250: "y/y group 01",
    2255: "y/y group 06 transport",
    2498: "WPI Indonesia (2023=100)", 2495: "WPI agriculture section", 1015: "WPI percentage and contributions",
    1721: "WPI 2018=100", 24: "WPI Indonesia (old)",
}


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    log = []

    def save(name, path, d, st, s):
        (out / f"{name}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1))
        log.append({"name": name, "path": path, "status": st, "secs": s})
        (out / "log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
        print(name, st, s, flush=True)

    # static tables: all titles
    tables, page = [], 1
    while page < 400:
        st, d, s = get(f"list/model/statictable/domain/0000/lang/ind/page/{page}")
        paging, rows = rows_of(d)
        tables += [{k: r.get(k) for k in ("table_id", "title", "subj_id", "subj", "updt_date", "size", "excel")} for r in rows]
        if not paging or page >= int(paging.get("pages", 1)):
            break
        page += 1
    (out / "static_all.json").write_text(json.dumps(tables, ensure_ascii=False, indent=1))
    hits = [t for t in tables if re.search(r"(?i)inti|diatur|bergejolak|komponen|core|andil", t.get("title") or "")]
    (out / "static_hits.json").write_text(json.dumps(hits, ensure_ascii=False, indent=1))
    print(len(tables), "static tables;", len(hits), "hits", flush=True)
    for t in hits[:15]:
        p = f"view/model/statictable/domain/0000/lang/ind/id/{t['table_id']}"
        st, d, s = get(p)
        save(f"static_view_{t['table_id']}", p, d, st, s)
    # press releases on inflation (latest)
    st, d, s = get("list/model/pressrelease/domain/0000/lang/ind/keyword/inflasi")
    save("pressrelease_inflasi", "list/model/pressrelease/.../keyword/inflasi", d, st, s)
    _p, rel = rows_of(d)
    if rel:
        rid = rel[0].get("brs_id")
        p = f"view/model/pressrelease/domain/0000/lang/ind/id/{rid}"
        st, d, s = get(p)
        save(f"pressrelease_view_{rid}", p, d, st, s)
        pdf = (d.get("data") or {}).get("pdf") if isinstance(d.get("data"), dict) else None
        if pdf:  # can the release PDF itself be downloaded from Actions?
            import urllib.request  # noqa: PLC0415
            try:
                with urllib.request.urlopen(urllib.request.Request(pdf, headers={"User-Agent": "asia-vitals/1.0"}), timeout=90) as r:
                    b = r.read()
                (out / "release.pdf").write_bytes(b)
                print("pdf", len(b), b[:8])
            except Exception as e:  # noqa: BLE001
                (out / "release_pdf_error.txt").write_text(repr(e))
    # 2026 data (th_id 126) for the dashboard variables
    for vid, what in VARS.items():
        st, d, s = get(f"list/model/th/domain/0000/var/{vid}")
        save(f"th_{vid}", f"th var {vid}", d, st, s)
        _p, ths = rows_of(d)
        ids = sorted((t["th_id"] for t in ths), key=int)
        for th in ids[-1:]:
            p = f"list/model/data/domain/0000/var/{vid}/th/{th}"
            st, d, s = get(p)
            save(f"data_{vid}_{th}", p, d, st, s)


if __name__ == "__main__":
    try:
        main(sys.argv[1])
    finally:
        scrub(sys.argv[1])
