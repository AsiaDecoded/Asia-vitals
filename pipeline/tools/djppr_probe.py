"""DJPPR site (Ministry of Finance debt office): the SUSPI page and the app's API calls; saves page, scripts and any
API responses that mention suspi/profil utang.

  python -I pipeline/tools/djppr_probe.py OUTDIR
"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "text/html,application/json,*/*;q=0.8", "Origin": "https://djppr.kemenkeu.go.id", "Referer": "https://djppr.kemenkeu.go.id/en/suspi"}
BASE = "https://djppr.kemenkeu.go.id"


def fetch(url, timeout=90):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), e.read()[:20000]
    except Exception as e:  # noqa: BLE001
        return None, None, repr(e).encode()


def main(out):
    out = Path(out)
    (out / "js").mkdir(parents=True, exist_ok=True)
    log = []
    st, ct, b = fetch(BASE + "/en/suspi")
    (out / "page.html").write_bytes(b)
    t = b.decode("utf-8", "replace")
    scripts = sorted(set(re.findall(r'src="([^"]+\.js[^"]*)"', t)))
    log.append({"page": st, "bytes": len(b), "scripts": scripts})
    apis = set()
    for s in scripts[:40]:
        u = urllib.parse.urljoin(BASE + "/", s)
        st2, ct2, jb = fetch(u)
        name = re.sub(r"[^A-Za-z0-9._-]", "_", u.rsplit("/", 1)[-1])[:100]
        (out / "js" / name).write_bytes(jb)
        js = jb.decode("utf-8", "replace")
        for m in re.finditer(r'https?://[a-zA-Z0-9.-]*kemenkeu\.go\.id[^"\'`\s)]*', js):
            apis.add(m.group(0))
        for m in re.finditer(r'["\'`](/?(?:api|web/api|odata)[^"\'`]{0,120})["\'`]', js):
            apis.add(m.group(1))
        hits = [js[max(0, m.start() - 150): m.end() + 150] for m in re.finditer(r"(?i)suspi", js)][:10]
        log.append({"script": u, "status": st2, "bytes": len(jb), "suspi": hits})
    log.append({"apis": sorted(apis)[:300]})
    # try the likely API calls for SUSPI
    tried = []
    for a in sorted(apis):
        if re.search(r"(?i)suspi|statistik|publikasi|file|media|content", a) and a.startswith("http") and len(tried) < 40:
            for q in ("", "?$top=50", "?lang=en"):
                st3, ct3, rb = fetch(a.rstrip("/") + q)
                tried.append({"url": a + q, "status": st3, "type": ct3, "bytes": len(rb), "head": rb[:400].decode("utf-8", "replace")})
    log.append({"tried": tried})
    (out / "djppr.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
    print(json.dumps(log[0])[:500])


if __name__ == "__main__":
    main(sys.argv[1])
