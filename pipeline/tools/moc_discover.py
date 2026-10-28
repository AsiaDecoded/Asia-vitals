"""Probe TPSO's Open API (index-api.tpso.go.th), round 4.

  python -I pipeline/tools/moc_discover.py OUTDIR

GET /OpenApi/<Family>/Month/MasterData and POST /OpenApi/<Family>/Month for the latest months of each base,
for CPI (Cpig, Cpil, Cpiu), PPI and export/import prices (Imex); plus TPSO's COICOP 2018 file and the
CPI methodology PDF.
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9,th;q=0.8",
      "Origin": "https://index.tpso.go.th", "Referer": "https://index.tpso.go.th/"}
API = "https://index-api.tpso.go.th"


def call(path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    hdr = {**UA, **({"Content-Type": "application/json"} if data else {})}
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(API + path, data=data, headers=hdr), timeout=timeout) as r:
            return r.status, r.read(), round(time.time() - t0, 1)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), round(time.time() - t0, 1)
    except Exception as e:  # noqa: BLE001
        return None, repr(e).encode(), round(time.time() - t0, 1)


def get_file(url, dest, timeout=120):
    try:
        with urllib.request.urlopen(urllib.request.Request(urllib.parse.quote(url, safe=":/"), headers=UA), timeout=timeout) as r:
            dest.write_bytes(r.read())
            return r.status, dest.stat().st_size
    except Exception as e:  # noqa: BLE001
        return repr(e)[:200], 0


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    s = {"master": {}, "month": {}, "files": {}}
    masters = {}
    for fam in ("Cpig", "Cpil", "Cpiu", "Ppi", "Imex"):
        st, b, secs = call(f"/OpenApi/{fam}/Month/MasterData")
        (out / f"master_{fam}.json").write_bytes(b)
        s["master"][fam] = {"status": st, "secs": secs, "bytes": len(b), "head": b[:600].decode("utf-8", "replace")}
        try:
            masters[fam] = json.loads(b)
        except Exception:  # noqa: BLE001
            pass
        print(fam, st, secs, len(b), flush=True)
    (out / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1))

    def periods(m):
        found = []
        def walk(x):
            if isinstance(x, dict):
                if "yearBase" in x and "endYear" in x:
                    found.append(x)
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(m)
        return found

    jobs = []
    for fam, m in masters.items():
        ps = periods(m)
        s["master"][fam]["periods"] = ps[:20]
        types = {""}
        if fam == "Ppi":
            types = {"SOP", "CPA"}
        if fam == "Imex":
            types = {"EXI", "IMI"}
        seen = set()
        for p in ps:
            key = (p["yearBase"], p["endYear"], p["endPeriod"])
            if key in seen:
                continue
            seen.add(key)
            for t in sorted(types):
                jobs.append((fam, t, p["yearBase"], p["endYear"], p["endPeriod"]))
                jobs.append((fam, t, p["yearBase"], p["startYear"], p["startPeriod"]))
    if not jobs:  # fall back to the documented example shape
        for fam, t in (("Cpig", ""), ("Cpig", "TG"), ("Ppi", "SOP"), ("Ppi", "CPA"), ("Imex", "EXI"), ("Imex", "IMI")):
            for yb in (2566, 2562, 2558, 2555):
                jobs.append((fam, t, yb, 2569, 8))
    for fam, t, yb, y, mo in jobs[:60]:
        body = {"yearBase": yb, "year": y, "month": mo, "type": t, "commodities": []}
        st, b, secs = call(f"/OpenApi/{fam}/Month", body)
        name = f"month_{fam}_{t or 'all'}_{yb}_{y}_{mo:02d}.json"
        (out / name).write_bytes(b)
        info = {"body": body, "status": st, "secs": secs, "bytes": len(b)}
        try:
            d = json.loads(b)
            rows = d if isinstance(d, list) else d.get("data", d)
            info["n"] = len(rows) if isinstance(rows, list) else None
            info["sample"] = rows[:3] if isinstance(rows, list) else str(d)[:500]
        except Exception:  # noqa: BLE001
            info["text"] = b[:300].decode("utf-8", "replace")
        s["month"][name] = info
        print(name, st, secs, info.get("n"), flush=True)
        (out / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1))
    for url, name in (("https://uploads.tpso.go.th/economic/pdf/Th_CPI_COICOP2018.xlsx", "Th_CPI_COICOP2018.xlsx"),
                      ("https://uploads.tpso.go.th/กระบวนการจัดทำ-ดัชนีราคาผู้บริโภค.pdf", "cpi_process.pdf"),
                      ("https://uploads.tpso.go.th/กระบวนการจัดทำ-ดัชนีราคาผู้ผลิต.pdf", "ppi_process.pdf"),
                      ("https://uploads.tpso.go.th/exi-imi_price_index2025_note.pdf", "exi_imi_2025_note.pdf"),
                      ("https://uploads.tpso.go.th/economic/pdf/ppi_note_2564.pdf", "ppi_note_2564.pdf")):
        s["files"][name] = get_file(url, out / name)
    (out / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
