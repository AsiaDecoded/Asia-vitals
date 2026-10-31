"""DJPPR web API: the site menu (/page), the SUSPI and debt-profile pages (/page?url=...), and the media files they
link (first 40). Saves everything.

  python -I pipeline/tools/djppr_probe2.py OUTDIR
"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api-djppr.kemenkeu.go.id/web/api/v1"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json,*/*;q=0.8", "Origin": "https://djppr.kemenkeu.go.id", "Referer": "https://djppr.kemenkeu.go.id/"}


def fetch(url, timeout=120):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type"), r.headers.get("Content-Disposition"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), None, e.read()[:20000]
    except Exception as e:  # noqa: BLE001
        return None, None, None, repr(e).encode()


def main(out):
    out = Path(out)
    (out / "media").mkdir(parents=True, exist_ok=True)
    log = {"pages": [], "media": []}
    st, ct, cd, b = fetch(API + "/page")
    (out / "menu.json").write_bytes(b)
    t = b.decode("utf-8", "replace")
    urls = sorted(set(re.findall(r'"url"\s*:\s*"([^"]+)"', t)))
    debt = [u for u in urls if re.search(r"(?i)suspi|utang|debt|profil|statist|data", u)]
    log["menu"] = {"status": st, "bytes": len(b), "debt_urls": debt[:200]}
    want = sorted(set(["/en/suspi", "/suspi", "/id/suspi"] + debt[:30]))
    media = []
    for i, u in enumerate(want):
        st, ct, cd, b = fetch(API + "/page?url=" + urllib.parse.quote(u))
        (out / f"page_{i:02d}.json").write_bytes(b)
        t = b.decode("utf-8", "replace")
        ids = re.findall(r"media/([0-9A-Fa-f-]{36})", t) + re.findall(r'"(?:file|fileId|mediaId|id)"\s*:\s*"([0-9A-Fa-f-]{36})"', t)
        names = re.findall(r'"(?:fileName|name|title|judul)"\s*:\s*"([^"]{3,160})"', t)
        log["pages"].append({"url": u, "status": st, "bytes": len(b), "media": ids[:60], "names": names[:60]})
        media += ids
    seen = set()
    for m in media:
        if m.lower() in seen or len(seen) >= 40:
            continue
        seen.add(m.lower())
        st, ct, cd, b = fetch(f"{API}/media/{m}")
        ext = ".xlsx" if b[:2] == b"PK" else (".pdf" if b[:4] == b"%PDF" else ".bin")
        (out / "media" / f"{m}{ext}").write_bytes(b)
        log["media"].append({"id": m, "status": st, "type": ct, "disp": cd, "bytes": len(b), "ext": ext})
    (out / "djppr2.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
    print(json.dumps(log["menu"])[:800])


if __name__ == "__main__":
    main(sys.argv[1])
