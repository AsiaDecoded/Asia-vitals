"""Indonesia 10-year government bond yield, long series: IMF MFS financial market prices (MFS_FMP), OECD MEI/finance
long-term rates (sdmx.oecd.org), BIS, Bank Indonesia SEKI tables listing. Saves each response.

  python -I pipeline/tools/yield_probe.py OUTDIR
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json,text/csv,*/*;q=0.8"}
I = "https://api.imf.org/external/sdmx/3.0"
O = "https://sdmx.oecd.org/public/rest"
URLS = [
    I + "/structure/dataflow/IMF.STA/MFS_FMP/+?references=datastructure",
    I + "/data/dataflow/IMF.STA/MFS_FMP/+/IDN.*.*",
    I + "/data/dataflow/IMF.STA/MFS_FMP/+/IDN.*.*.*",
    O + "/data/OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/IDN.M.IRLT.PA.....?format=csvfilewithlabels",
    O + "/data/OECD.SDD.STES,DSD_STES@DF_FINMARK,/IDN.M..PA.....?format=csvfilewithlabels",
    "https://www.bi.go.id/id/statistik/ekonomi-keuangan/seki/Default.aspx",
    "https://www.bi.go.id/SEKI/tabel/TABEL1_25.xls",
    "https://www.bi.go.id/SEKI/tabel/TABEL1_26.xls",
    "https://www.bi.go.id/SEKI/tabel/TABEL1_27.xls",
    "https://www.bi.go.id/SEKI/tabel/TABEL1_28.xls",
    "https://www.bi.go.id/SEKI/tabel/TABEL1_29.xls",
    "https://www.bi.go.id/SEKI/tabel/TABEL1_30.xls",
]


def fetch(url, timeout=180):
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type"), r.read(), round(time.time() - t0, 1)
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), e.read()[:20000], round(time.time() - t0, 1)
    except Exception as e:  # noqa: BLE001
        return None, None, repr(e).encode(), round(time.time() - t0, 1)


def main(out):
    out = Path(out)
    (out / "pages").mkdir(parents=True, exist_ok=True)
    log = []
    for i, u in enumerate(URLS):
        st, ct, b, s = fetch(u)
        (out / "pages" / f"{i:02d}.bin").write_bytes(b[:30_000_000])
        rec = {"i": i, "url": u, "status": st, "type": ct, "bytes": len(b), "secs": s, "head": b[:300].decode("utf-8", "replace")}
        if b[:4] == b"\xd0\xcf\x11\xe0":
            try:
                import xlrd  # noqa: PLC0415
                wb = xlrd.open_workbook(file_contents=b); sh = wb.sheet_by_index(wb.nsheets - 1)
                rec["xls"] = " | ".join(str(sh.cell_value(r, c)).strip() for r in range(min(5, sh.nrows)) for c in range(min(4, sh.ncols)) if str(sh.cell_value(r, c)).strip())[:300]
            except Exception as e:  # noqa: BLE001
                rec["xls"] = repr(e)
        log.append(rec)
        (out / "urls.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
        print(i, st, len(b), s, u, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
