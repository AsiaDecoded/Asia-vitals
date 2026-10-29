"""Probe TPSO's Open API (index-api.tpso.go.th), round 5: CPI with a region type, timings, release stamps.

  python -I pipeline/tools/moc_discover.py OUTDIR
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
            return r.status, r.read(), round(time.time() - t0, 2)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), round(time.time() - t0, 2)
    except Exception as e:  # noqa: BLE001
        return None, repr(e).encode(), round(time.time() - t0, 2)


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    s = {"calls": [], "files": {}}

    def month(fam, t, yb, y, m, commodities=()):
        body = {"yearBase": yb, "year": y, "month": m, "type": t, "commodities": list(commodities)}
        st, b, secs = call(f"/OpenApi/{fam}/Month", body)
        name = f"{fam}_{t}_{yb}_{y}_{m:02d}{'_sel' if commodities else ''}.json"
        (out / name).write_bytes(b)
        info = {"body": body, "status": st, "secs": secs, "bytes": len(b)}
        try:
            d = json.loads(b)
            info["n"] = len(d)
            info["head"] = [r for r in d if r.get("commodityCode") in ("00000", "93000", "0000", "000")][:3]
            info["created"] = sorted({r.get("createdAt", "")[:16] for r in d})[:3]
        except Exception:  # noqa: BLE001
            info["text"] = b[:200].decode("utf-8", "replace")
        s["calls"].append(info)
        print(name, st, secs, info.get("n"), flush=True)
        (out / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1))

    for t in ("TG", "10", "CC", "NN", "EE", "SS"):
        month("Cpig", t, 2566, 2569, 9)
    for m in range(1, 9):
        month("Cpig", "TG", 2566, 2569, m)
    for y, m in ((2568, 9), (2568, 12), (2567, 6), (2566, 1), (2562, 1), (2553, 1), (2540, 6), (2519, 1)):
        month("Cpig", "TG", 2566, y, m)
    month("Cpig", "TG", 2566, 2569, 9, ["00000", "93000"])
    month("Cpil", "TG", 2566, 2569, 9)
    month("Cpiu", "TG", 2566, 2569, 9)
    for y, m in ((2569, 8), (2569, 7), (2568, 9)):
        month("Ppi", "CPA", 2564, y, m)
        month("Imex", "EXI", 2555, y, m)
    for url, name in (("https://www.price.moc.go.th/price/fileuploader/file_cpi/cpi_note_2566.pdf", "cpi_note_2566.pdf"),
                      ("https://www.price.moc.go.th/price/fileuploader/file_cpi/cpi_note_2562.pdf", "cpi_note_2562.pdf"),
                      ("https://uploads.tpso.go.th/economic/pdf/Cpig.pdf", "Cpig.pdf")):
        try:
            with urllib.request.urlopen(urllib.request.Request(urllib.parse.quote(url, safe=":/"), headers=UA), timeout=90) as r:
                (out / name).write_bytes(r.read())
                s["files"][name] = r.status
        except Exception as e:  # noqa: BLE001
            s["files"][name] = repr(e)[:200]
    (out / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
