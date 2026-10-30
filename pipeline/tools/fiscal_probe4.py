"""Indonesia fiscal discovery, round 4: data-apbn.kemenkeu.go.id (Ministry of Finance budget data portal) with a
cookie jar (round 1 saw a 307 redirect to itself), its scripts, and every data endpoint they name; plus DJPb
(Treasury) data pages. Looks for a published monthly budget outturn series.

  python -I pipeline/tools/fiscal_probe4.py OUTDIR
"""
import http.cookiejar
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "text/html,application/json,application/xhtml+xml,*/*;q=0.8", "Accept-Language": "id,en;q=0.8"}
JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(JAR), urllib.request.HTTPRedirectHandler())
START = ["https://data-apbn.kemenkeu.go.id/", "https://data-apbn.kemenkeu.go.id/lv2/apbn",
         "https://data-apbn.kemenkeu.go.id/lv2/realisasi", "https://data-apbn.kemenkeu.go.id/lv2/belanja",
         "https://djpb.kemenkeu.go.id/portal/id/", "https://djpb.kemenkeu.go.id/portal/id/data-publikasi.html",
         "https://www.djpb.kemenkeu.go.id/portal/id/berita/lainnya/data-dan-statistik.html",
         "https://djpb.kemenkeu.go.id/kppn/", "https://spanint.kemenkeu.go.id/"]


def fetch(url, timeout=60):
    try:
        with OPENER.open(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type"), r.read(), r.geturl(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), e.read()[:20000], url, dict(e.headers)
    except Exception as e:  # noqa: BLE001
        return None, None, repr(e).encode(), url, {}


def main(out):
    out = Path(out)
    (out / "pages").mkdir(parents=True, exist_ok=True)
    log, endpoints = [], set()
    for i, u in enumerate(START):
        st, ct, b, final, hd = fetch(u)
        txt = b.decode("utf-8", "replace")
        (out / "pages" / f"{i:02d}.txt").write_text(txt[:500000])
        scripts = re.findall(r'<script[^>]+src="([^"]+)"', txt)
        rec = {"url": u, "status": st, "type": ct, "final": final, "bytes": len(b), "scripts": scripts,
               "title": (re.search(r"<title>(.*?)</title>", txt, re.S | re.I) or [None, ""])[1].strip()[:150],
               "location": hd.get("Location"), "set_cookie": bool(hd.get("Set-Cookie")),
               "links": sorted({l for l in re.findall(r'href="([^"#]+)"', txt) if re.search(r"(?i)realisasi|apbn|data|xls|csv|pdf|api|download", l)})[:200]}
        base = final if final.endswith("/") else final.rsplit("/", 1)[0] + "/"
        for s in scripts[:12]:
            su = s if s.startswith("http") else (re.match(r"https?://[^/]+", final).group(0) + s if s.startswith("/") else base + s)
            st2, ct2, b2, _f, _h = fetch(su, 90)
            js = b2.decode("utf-8", "replace")
            (out / "pages" / f"{i:02d}_{re.sub(r'[^A-Za-z0-9]+', '_', s)[-60:]}.js").write_text(js[:3_000_000])
            endpoints |= set(re.findall(r"https?://[A-Za-z0-9.\-]*kemenkeu\.go\.id[A-Za-z0-9_\-./?=&]*", js))
            endpoints |= {final.split('/')[0] + "//" + final.split('/')[2] + p for p in re.findall(r"[\"'`](/(?:api|data|lv\d|json|services?)/[A-Za-z0-9_\-./]+)[\"'`]", js)}
        log.append(rec)
        (out / "urls.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
        print(i, st, final, rec["title"][:60], len(scripts), "scripts", flush=True)
    (out / "endpoints.json").write_text(json.dumps(sorted(endpoints), indent=1))
    tried = []
    for e in sorted(endpoints):
        if len(tried) >= 60 or not re.search(r"(?i)api|data|json|lv\d", e):
            continue
        st, ct, b, final, _h = fetch(e, 40)
        tried.append({"url": e, "status": st, "type": ct, "bytes": len(b), "head": b[:800].decode("utf-8", "replace")})
        if st == 200 and ct and ("json" in ct or "csv" in ct or "sheet" in ct or "excel" in ct):
            (out / "pages" / ("ep_" + re.sub(r"[^A-Za-z0-9]+", "_", e)[-80:])).write_bytes(b[:3_000_000])
    (out / "tried.json").write_text(json.dumps(tried, ensure_ascii=False, indent=1))
    (out / "cookies.json").write_text(json.dumps([c.name + "@" + c.domain for c in JAR], indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
