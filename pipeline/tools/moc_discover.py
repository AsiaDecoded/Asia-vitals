"""Probe Thailand's TPSO price-index site, round 3.

  python -I pipeline/tools/moc_discover.py OUTDIR

Saves every JS bundle the index.tpso.go.th pages load (cpi, ppi, exi-imi pages and the build manifest),
so the site's own data API can be read from them; retries dataapi.moc.go.th headline CPI three times.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9,th;q=0.8"}
SITE = "https://index.tpso.go.th"


def fetch(url, timeout=90):
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, r.read(), round(time.time() - t0, 1)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), round(time.time() - t0, 1)
    except Exception as e:  # noqa: BLE001
        return None, repr(e).encode(), round(time.time() - t0, 1)


def main(out):
    out = Path(out)
    (out / "js").mkdir(parents=True, exist_ok=True)
    summary = {"pages": {}, "chunks": [], "dataapi": []}
    st, body, _ = fetch(SITE + "/")
    build = re.search(r'/_next/static/([^/]+)/_buildManifest\.js', body.decode("utf-8", "replace"))
    chunks = set()
    if build:
        st, b, _ = fetch(f"{SITE}/_next/static/{build.group(1)}/_buildManifest.js")
        (out / "js" / "_buildManifest.js").write_bytes(b)
        chunks |= {"/_next/" + c for c in re.findall(r'"(static/chunks/[^"]+\.js)"', b.decode("utf-8", "replace"))}
    for page in ("/", "/cpi", "/ppi", "/exi-imi", "/cpip", "/cpi-weight", "/weight"):
        st, b, _ = fetch(SITE + page)
        summary["pages"][page] = {"status": st, "bytes": len(b)}
        chunks |= set(re.findall(r'/_next/static/chunks/[^"\']+\.js', b.decode("utf-8", "replace")))
    for c in sorted(chunks):
        if any(x in c for x in ("framework", "polyfills", "webpack", "main-")):
            continue
        st, b, _ = fetch(SITE + c)
        if st == 200:
            (out / "js" / c.replace("/_next/static/chunks/", "").replace("/", "__")).write_bytes(b)
            summary["chunks"].append(c)
    for i in range(3):
        st, b, secs = fetch("https://dataapi.moc.go.th/cpig-indexes?region_id=5&index_id=0000000000000000&from_year=2025&to_year=2026", 150)
        summary["dataapi"].append({"status": st, "secs": secs, "head": b[:200].decode("utf-8", "replace")})
        if st == 200:
            (out / "dataapi_cpig_2025_2026.json").write_bytes(b)
            break
        time.sleep(60)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
