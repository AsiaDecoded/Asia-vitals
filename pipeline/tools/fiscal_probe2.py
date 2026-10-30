"""Indonesia fiscal discovery, round 2: the Ministry of Finance single-page sites (DJPPR debt, Kemenkeu APBN KiTa,
data-apbn portal): fetch env.js and the main script bundles, list every API base URL and endpoint path in them,
and try the likely ones.

  python -I pipeline/tools/fiscal_probe2.py OUTDIR
"""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "*/*"}
SITES = ["https://djppr.kemenkeu.go.id/", "https://www.kemenkeu.go.id/", "https://data-apbn.kemenkeu.go.id/",
         "https://fiskal.kemenkeu.go.id/"]


def fetch(url, timeout=60):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type"), r.read(), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), e.read()[:5000], url
    except Exception as e:  # noqa: BLE001
        return None, None, repr(e).encode(), url


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rep = {}
    for site in SITES:
        st, ct, b, final = fetch(site)
        html = b.decode("utf-8", "replace")
        scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
        rec = {"status": st, "final": final, "scripts": scripts, "apis": [], "paths": []}
        base = final if final.endswith("/") else final.rsplit("/", 1)[0] + "/"
        for s in scripts:
            u = s if s.startswith("http") else base + s.lstrip("./")
            st2, ct2, b2, _ = fetch(u, 90)
            js = b2.decode("utf-8", "replace")
            name = re.sub(r"\W+", "_", site + s)[:120]
            (out / f"{name}.js").write_text(js[:3_000_000])
            rec["apis"] += re.findall(r"https?://[A-Za-z0-9.\-]+(?:/[A-Za-z0-9_\-./]*)?", js)
            rec["paths"] += re.findall(r"[\"'`](/?(?:api|v1|v2|rest|services?)/[A-Za-z0-9_\-./{}$]+)[\"'`]", js)
        rec["apis"] = sorted({a for a in rec["apis"] if not re.search(r"(?i)w3\.org|googleapis|gstatic|angular|github|mozilla|schema", a)})[:300]
        rec["paths"] = sorted(set(rec["paths"]))[:400]
        rep[site] = rec
        print(site, st, len(scripts), "scripts", len(rec["apis"]), "urls", len(rec["paths"]), "paths", flush=True)
    (out / "spa.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    # try API bases seen with fiscal words
    tried = []
    for site, rec in rep.items():
        for a in rec["apis"]:
            if re.search(r"(?i)api|backend|service", a) and re.search(r"(?i)kemenkeu|djppr", a) and len(tried) < 40:
                st, ct, b, _ = fetch(a, 30)
                tried.append({"url": a, "status": st, "type": ct, "head": b[:600].decode("utf-8", "replace")})
    (out / "tried.json").write_text(json.dumps(tried, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
