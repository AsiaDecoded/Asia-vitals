"""Long-run Indonesia government debt: IMF Historical Public Debt (HPD) and Global Debt Database (GDD) via the IMF SDMX
API, the IMF Fiscal Monitor, BIS credit to the government sector, and the DJPPR SUSPI page attachment.

  python -I pipeline/tools/debt_probe4.py OUTDIR
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json,*/*;q=0.8"}
I = "https://api.imf.org/external/sdmx/3.0"
URLS = [
    I + "/structure/dataflow/IMF.FAD/HPD/+?references=datastructure",
    I + "/structure/dataflow/IMF.FAD/GDD/+?references=datastructure",
    I + "/data/dataflow/IMF.FAD/HPD/+/*?c[COUNTRY]=IDN",
    I + "/data/dataflow/IMF.FAD/GDD/+/*?c[COUNTRY]=IDN",
    I + "/data/dataflow/IMF.FAD/HPD/+/IDN.*.*",
    I + "/data/dataflow/IMF.FAD/GDD/+/IDN.*.*",
    I + "/data/dataflow/IMF.FAD/FM/+/*?c[COUNTRY]=IDN",
    "https://stats.bis.org/api/v1/data/BIS,WS_TC,2.0/Q.ID.G.A.M.770.A?format=csv",
    "https://stats.bis.org/api/v1/data/BIS,WS_TC,2.0/Q.ID.G.A.M.XDC.A?format=csv",
    "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_TC/2.0/Q.ID.G.*.*.*.*?format=csv",
    "https://api-djppr.kemenkeu.go.id/web/api/v1/media/7DA006E5-1E14-48A4-9CC7-4ED2FC210606",
]


def fetch(url, timeout=120):
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type"), r.headers.get("Content-Disposition"), r.read(), round(time.time() - t0, 1)
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), None, e.read()[:20000], round(time.time() - t0, 1)
    except Exception as e:  # noqa: BLE001
        return None, None, None, repr(e).encode(), round(time.time() - t0, 1)


def main(out):
    out = Path(out)
    (out / "pages").mkdir(parents=True, exist_ok=True)
    log = []
    for i, u in enumerate(URLS):
        st, ct, cd, b, s = fetch(u)
        (out / "pages" / f"{i:02d}.bin").write_bytes(b[:20_000_000])
        log.append({"i": i, "url": u, "status": st, "type": ct, "disp": cd, "bytes": len(b), "secs": s, "head": b[:300].decode("utf-8", "replace")})
        (out / "urls.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
        print(i, st, len(b), s, u, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
