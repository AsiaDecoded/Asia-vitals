"""Indonesia government debt: IMF WEO (GGXWDG, GGXWDG_NGDP), World Bank Quarterly Public Sector Debt (source 22) and
WDI central government debt; DJPPR public pages. Saves each response.

  python -I pipeline/tools/debt_probe.py OUTDIR
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json,text/html,*/*;q=0.8"}
URLS = [
    "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES/WEO/+/IDN.GGXWDG_NGDP.A",
    "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES/WEO/+/IDN.GGXWDG.A",
    "https://api.worldbank.org/v2/sources/22/series?format=json&per_page=500",
    "https://api.worldbank.org/v2/sources/22/country/IDN/series/DP.DOD.DECT.CR.CG.Z1/time/all?format=json&per_page=500",
    "https://api.worldbank.org/v2/sources/22/country/IDN/series/DP.DOD.DECT.CR.CG.CD/time/all?format=json&per_page=500",
    "https://api.worldbank.org/v2/sources/22/country/IDN/series/DP.DOD.DLD1.CR.CG.Z1/time/all?format=json&per_page=500",
    "https://api.worldbank.org/v2/sources/22/country/IDN/series/DP.DOD.DECT.CR.CG.LC/time/all?format=json&per_page=500",
    "https://api.worldbank.org/v2/country/IDN/indicator/GC.DOD.TOTL.GD.ZS?format=json&per_page=200",
    "https://api.worldbank.org/v2/country/IDN/indicator/GC.DOD.TOTL.CN?format=json&per_page=200",
    "https://www.djppr.kemenkeu.go.id/profilutang",
    "https://www.djppr.kemenkeu.go.id/page/load/2820",
    "https://api-djppr.kemenkeu.go.id/web/api/v1/media/public/profil-utang",
]


def fetch(url, timeout=90):
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
        (out / "pages" / f"{i:02d}.txt").write_bytes(b[:5_000_000])
        log.append({"i": i, "url": u, "status": st, "type": ct, "bytes": len(b), "secs": s, "head": b[:300].decode("utf-8", "replace")})
        (out / "urls.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
        print(i, st, len(b), s, u, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
