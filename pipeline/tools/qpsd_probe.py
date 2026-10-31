"""World Bank Quarterly Public Sector Debt (QPSD), Indonesia: source list, series list and Indonesian data, to see
how far back Indonesia's SUSPI-based reporting goes; also the SUSPI quarterly pages for 2010-2014.

  python -I pipeline/tools/qpsd_probe.py OUTDIR
"""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
W = "https://api.worldbank.org/v2"


def fetch(url, timeout=120):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:5000]
    except Exception as e:  # noqa: BLE001
        return None, repr(e).encode()


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    log = []
    st, b = fetch(W + "/sources?format=json&per_page=200")
    (out / "sources.json").write_bytes(b)
    srcs = []
    try:
        srcs = [(s["id"], s["name"]) for s in json.loads(b)[1]]
    except Exception:  # noqa: BLE001
        pass
    q = [s for s in srcs if re.search(r"(?i)public sector debt", s[1])]
    log.append({"qpsd_sources": q})
    for sid, _ in q:
        st, b = fetch(f"{W}/sources/{sid}/series?format=json&per_page=1000")
        (out / f"series_{sid}.json").write_bytes(b)
        st, b = fetch(f"{W}/sources/{sid}/country/IDN/series/all/time/all?format=json&per_page=20000")
        (out / f"idn_{sid}.json").write_bytes(b)
        log.append({"source": sid, "status": st, "bytes": len(b), "head": b[:300].decode("utf-8", "replace")})
    for sec in ("GG", "CG", "BC"):
        for u in ("", ".CD", ".Z1"):
            sid = f"DP.DOD.DECT.CR.{sec}{u}"
            st, b = fetch(f"{W}/sources/20/country/IDN/series/{sid}/time/all?format=json&per_page=500")
            (out / f"idn_{sid}.json").write_bytes(b)
            log.append({"series": sid, "status": st, "bytes": len(b), "head": b[:200].decode("utf-8", "replace")})
    for y in []:
        for qq in ("I", "II", "III", "IV"):
            u = f"https://www.bi.go.id/id/statistik/ekonomi-keuangan/suspi/Pages/SUSPI_TW{qq}_{y}.aspx"
            st, b = fetch(u)
            t = b.decode("utf-8", "replace")
            links = [l for l in re.findall(r'href="([^"#]+\.(?:zip|xlsx?|pdf))"', t, re.I) if "Metadata" not in l]
            log.append({"page": u, "status": st, "links": links})
    (out / "qpsd.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
    print(json.dumps(log[:3])[:1500])


if __name__ == "__main__":
    main(sys.argv[1])
