"""Indonesia: Bank Indonesia / Ministry of Finance public sector debt statistics (SUSPI): latest quarterly page,
its files (xlsx/pdf), saved with their sheet names and first rows.

  python -I pipeline/tools/debt_probe3.py OUTDIR
"""
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
PAGES = ["https://www.bi.go.id/id/statistik/ekonomi-keuangan/suspi/Pages/SUSPI_TWII_2026.aspx",
         "https://www.bi.go.id/en/statistik/ekonomi-keuangan/suspi/Pages/SUSPI_TWII_2026.aspx",
         "https://www.bi.go.id/id/statistik/metadata/metadata-suspi/default.aspx"]


def fetch(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:5000]
    except Exception as e:  # noqa: BLE001
        return None, repr(e).encode()


def main(out):
    out = Path(out)
    (out / "files").mkdir(parents=True, exist_ok=True)
    log = {"pages": [], "files": []}
    seen = set()
    for i, u in enumerate(PAGES):
        st, b = fetch(u)
        (out / f"page{i}.html").write_bytes(b)
        t = b.decode("utf-8", "replace")
        links = sorted(set(re.findall(r'href="([^"#]+\.(?:xlsx?|pdf|zip))"', t, re.I)))
        log["pages"].append({"url": u, "status": st, "bytes": len(b), "links": links})
        for l in links:
            full = urllib.parse.urljoin(u, l)
            if full in seen or len(seen) >= 30:
                continue
            seen.add(full)
            st2, fb = fetch(full.replace(" ", "%20"))
            name = re.sub(r"[^A-Za-z0-9._-]", "_", full.rsplit("/", 1)[-1])[:120]
            (out / "files" / name).write_bytes(fb)
            rec = {"url": full, "status": st2, "bytes": len(fb), "name": name}
            if name.lower().endswith(("xlsx", "xls")) and st2 == 200:
                try:
                    import openpyxl  # noqa: PLC0415
                    wb = openpyxl.load_workbook(io.BytesIO(fb), read_only=True, data_only=True)
                    rec["sheets"] = {}
                    for ws in wb.worksheets[:40]:
                        rows = []
                        for r in ws.iter_rows(max_row=12, values_only=True):
                            rows.append([str(c)[:40] for c in r[:14] if c is not None])
                        rec["sheets"][ws.title] = rows
                except Exception as e:  # noqa: BLE001
                    rec["err"] = repr(e)
            log["files"].append(rec)
            (out / "suspi.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
            print(st2, len(fb), full, flush=True)
    (out / "suspi.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
