"""Probe Vietnam NSO (nso.gov.vn, gso.gov.vn, PX-Web) and the IMF/DBnomics fallbacks from Actions.

  python -I pipeline/tools/nso_discover.py <seeds.txt> <out_dir> [max_fetch] [depth]

seeds.txt: one "name url" per line. HTML pages are crawled for links (depth-limited,
NSO/GSO/IMF/DBnomics hosts only, price-related or data-file links). Every response is saved
with status, headers and link list in summary.json.
"""
import hashlib
import html
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import os
CTX = ssl.create_default_context()
if os.environ.get("NSO_CA"):  # extra intermediate(s) if a host sends an incomplete chain
    CTX.load_verify_locations(os.environ["NSO_CA"])
CTX.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) asia-vitals/0.1 (+https://github.com/AsiaDecoded/asia-vitals)",
      "Accept": "*/*", "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8"}
HOSTS = ("nso.gov.vn", "gso.gov.vn", "mof.gov.vn")
KEY = re.compile(r"gi[aá]|CPI|PPI|[Pp]rice|l[aạ]m-?ph[aá]t|inflation|ti[eê]u-?d[uù]ng|consumer|s[aả]n-?xu[aấ]t|producer|"
                 r"xu[aấ]t-?nh[aậ]p|import|export|kinh-?t[eế]-?x[aã]-?h[oộ]i|socio|ni[eê]n-?gi[aá]m|yearbook|"
                 r"pxweb|px-?web|\.px($|\?)|api/v1|database|c[oơ]-s[oở]-d[uữ]|"
                 r"\.xlsx?($|\?)|\.ods|\.csv|\.json|\.xml|wp-content/uploads|lich|calendar|du-lieu|data-and-statistics", re.I)
FOLLOW = re.compile(os.environ["NSO_FOLLOW"], re.I) if os.environ.get("NSO_FOLLOW") else None
HREF = re.compile(r"""<a\b[^>]*?href\s*=\s*["']([^"'#]+)["'][^>]*>(.*?)</a>""", re.I | re.S)


def fetch(url, data=None, headers=None):
    url = urllib.parse.quote(url, safe=":/?&=%#+,;@!$'()*~")
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
            return r.status, dict(r.headers), r.read(), r.geturl(), time.time() - t, None
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read(), url, time.time() - t, f"HTTPError {e.code} {e.reason}"
    except Exception as e:  # noqa: BLE001
        return None, {}, b"", url, time.time() - t, f"{type(e).__name__}: {e}"


def text_of(body, headers):
    ct = headers.get("Content-Type", "")
    m = re.search(r"charset=([\w-]+)", ct)
    for enc in ([m.group(1)] if m else []) + ["utf-8", "cp1258", "latin-1"]:
        try:
            return body.decode(enc)
        except Exception:  # noqa: BLE001
            pass
    return body.decode("utf-8", "replace")


def main(seedfile, out, max_fetch=250, depth=2):
    out = Path(out); (out / "files").mkdir(parents=True, exist_ok=True)
    max_fetch, depth = int(max_fetch), int(depth)
    queue, seen, summary = [], set(), []
    for line in Path(seedfile).read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            parts = line.split(None, 2)
            name, url = parts[0], parts[1]
            post = parts[2] if len(parts) > 2 else None
            queue.append((name, url, post, 0, "seed"))
    while queue and len(summary) < max_fetch:
        name, url, post, d, parent = queue.pop(0)
        key = url + (post or "")
        if key in seen:
            continue
        seen.add(key)
        data = post.encode() if post else None
        hdr = {"Content-Type": "application/json"} if post and post.lstrip().startswith("{") else \
              ({"Content-Type": "application/x-www-form-urlencoded"} if post else None)
        status, headers, body, final, secs, err = fetch(url, data, hdr)
        ct = headers.get("Content-Type", "")
        h = hashlib.md5(key.encode()).hexdigest()[:10]
        low = url.lower().split("?")[0]
        ext = ("xlsx" if ("spreadsheetml" in ct or low.endswith(".xlsx")) else
               "xls" if ("excel" in ct or low.endswith(".xls")) else
               "ods" if ("opendocument" in ct or low.endswith(".ods")) else
               "pdf" if ("pdf" in ct or low.endswith(".pdf")) else
               "json" if "json" in ct else "xml" if "xml" in ct else "html" if "html" in ct else
               "csv" if "csv" in ct else "bin")
        fn = f"{name}_{h}.{ext}"
        (out / "files" / fn).write_bytes(body[:30_000_000])
        rec = {"name": name, "url": url, "post": post, "final_url": final, "status": status, "error": err,
               "type": ct, "bytes": len(body), "secs": round(secs, 1), "file": fn, "depth": d, "parent": parent,
               "headers": {k: v for k, v in headers.items() if k.lower() in
                           ("content-type", "content-disposition", "last-modified", "server", "set-cookie", "location")}}
        if ext == "html" or (ext == "bin" and body[:200].lstrip().startswith(b"<")):
            t = text_of(body, headers)
            tm = re.search(r"<title>(.*?)</title>", t, re.I | re.S)
            rec["title"] = html.unescape(tm.group(1).strip()) if tm else None
            links = []
            for href, label in HREF.findall(t):
                href = html.unescape(href.strip())
                if href.lower().startswith(("javascript", "mailto")):
                    continue
                absu = urllib.parse.urljoin(final, href)
                lab = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", label))).strip()[:120]
                links.append([absu, lab])
            rec["links"] = links[:400]
            if d < depth:
                for absu, lab in links:
                    host = urllib.parse.urlparse(absu).hostname or ""
                    if host.endswith(HOSTS) and ((FOLLOW.search(absu) or FOLLOW.search(lab)) if FOLLOW else (KEY.search(absu) or KEY.search(lab))):
                        queue.append((f"{name}-L{d+1}", absu, None, d + 1, url))
        summary.append(rec)
        print(len(summary), status, err or "", ct[:30], len(body), url[:140], flush=True)
        (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
