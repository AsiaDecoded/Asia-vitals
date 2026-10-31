"""Indonesia: long USD/IDR series. BIS bilateral exchange rates (WS_XRU, daily/monthly/annual), IMF Exchange Rates
(ER, IMF.STA) for IDN, Bank Indonesia JISDOR and transaction-rate pages. Saves each response.

  python -I pipeline/tools/fx_probe.py OUTDIR
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
URLS = [
    "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/D.ID.IDR.A?format=csv",
    "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/M.ID.IDR.*?format=csv",
    "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/A.ID.IDR.*?format=csv",
    I + "/structure/dataflow/IMF.STA/ER/+?references=datastructure",
    I + "/data/dataflow/IMF.STA/ER/+/IDN.*.*.M",
    I + "/data/dataflow/IMF.STA/ER/+/IDN.*.*.*",
    "https://www.bi.go.id/en/statistik/informasi-kurs/jisdor/default.aspx",
    "https://www.bi.go.id/en/statistik/informasi-kurs/transaksi-bi/default.aspx",
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
        log.append({"i": i, "url": u, "status": st, "type": ct, "bytes": len(b), "secs": s, "head": b[:400].decode("utf-8", "replace")})
        (out / "urls.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
        print(i, st, len(b), s, u, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
