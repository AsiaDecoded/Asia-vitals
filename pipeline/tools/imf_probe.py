"""Indonesia: World Bank WDI nominal GDP and IMF fiscal series reachable from GitHub Actions? DataMapper API (v1, v2), SDMX 2.1/3.0 (api.imf.org),
old dataservices endpoint; FRED (copy of WEO). Saves each response.

  python -I pipeline/tools/imf_probe.py OUTDIR
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json,text/html,*/*;q=0.8"}
IND = ["GGXCNL_NGDP", "GGXONLB_NGDP", "GGR_NGDP", "GGX_NGDP", "GGXWDG_NGDP", "CG_DEF_GDP", "cg_def", "GGXCNL_G01_GDP_PT"]
URLS = []
for i in IND:
    URLS += [f"https://www.imf.org/external/datamapper/api/v1/{i}/IDN", f"https://www.imf.org/external/datamapper/api/v2/{i}/IDN"]
META = ["https://api.worldbank.org/v2/sources/2/country/IDN/metadata?format=json",
        "https://api.worldbank.org/v2/sources/2/country/IDN/series/NY.GDP.MKTP.CN/metadata?format=json",
        "https://api.worldbank.org/v2/sources/2/series/NY.GDP.MKTP.CN/metadata?format=json",
        "https://api.worldbank.org/v2/sources/2/country/IDN/series/NY.GDP.MKTP.CN/time/YR2009/metadata?format=json",
        "https://api.worldbank.org/v2/sources/2/country/IDN/series/NY.GDP.MKTP.CN/time/YR2005/metadata?format=json",
        "https://api.worldbank.org/v2/sources/2/footnote/IDN~NY.GDP.MKTP.CN~YR2009/metadata?format=json",
        "https://api.worldbank.org/v2/country/IDN?format=json",
        "https://api.worldbank.org/v2/country/IDN/indicator/NY.GDP.MKTP.KN?format=json&per_page=200",
        "https://api.worldbank.org/v2/country/IDN/indicator/NY.GDP.DEFL.ZS?format=json&per_page=200"]
WDI = ["https://api.worldbank.org/v2/country/IDN/indicator/NY.GDP.MKTP.CN?format=json&per_page=200",
       "https://api.worldbank.org/v2/country/IDN/indicator/NY.GDP.MKTP.CN?format=json&per_page=200&source=2",
       "https://api.worldbank.org/v2/country/IDN/indicator/GC.NLD.TOTL.GD.ZS?format=json&per_page=200",
       "https://api.worldbank.org/v2/country/IDN/indicator/GC.REV.XGRT.GD.ZS?format=json&per_page=200",
       "https://api.worldbank.org/v2/sources/2?format=json",
       "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES/WEO/+/IDN.NGDP.A"]
URLS = META + WDI + URLS
URLS += [
    "https://www.imf.org/external/datamapper/api/v1/indicators",
    "https://www.imf.org/external/datamapper/api/v2/indicators",
    "https://www.imf.org/external/datamapper/api/v1/datasets",
    "https://api.imf.org/external/sdmx/2.1/dataflow",
    "https://api.imf.org/external/sdmx/2.1/data/IMF.RES,WEO/IDN.GGXCNL_NGDP.A",
    "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES/WEO/+/IDN.GGXCNL_NGDP.A",
    "https://api.imf.org/external/sdmx/2.1/data/IMF.STA,GFS_SOO/A.IDN..",
    "https://dataservices.imf.org/REST/SDMX_JSON.svc/CompactData/IFS/A.ID.GGXCNL_G01_GDP_PT",
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=GGNLBAIDA188N",
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=IDNGGXCNLG01GDPPT",
]


def fetch(url, timeout=60):
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
        (out / "pages" / f"{i:02d}.txt").write_bytes(b[:3_000_000])
        log.append({"i": i, "url": u, "status": st, "type": ct, "bytes": len(b), "secs": s, "head": b[:300].decode("utf-8", "replace")})
        (out / "urls.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
        print(i, st, len(b), s, u, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
