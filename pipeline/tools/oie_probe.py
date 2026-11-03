"""Probe Thailand's Office of Industrial Economics (OIE, oie.go.th) from Actions (blocked from the Claude sandbox):
the Manufacturing Production Index (MPI) and related monthly indices, as linked from the Bank of Thailand's real
sector page, plus OIE's index pages, to find the files, their layout and coverage.

  python -I pipeline/tools/oie_probe.py <out_dir>
"""
import hashlib
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept": "*/*", "Accept-Language": "en;q=0.9,th;q=0.8"}
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
BASE = "https://www.oie.go.th/assets/portals/1/fileups/2/files/Industrial%20index/"
FILES = [f"indexes_eng/month/{n}" for n in ("Prodidx1_E.xlsx", "Prodidx2_E.xlsx", "Shipidx_E.xlsx", "Invidx_E.xlsx",
                                             "Invratio_E.xlsx", "labidx_E.xlsx", "labaprod2_E.xlsx", "capidx_E.xlsx")]
FILES += [f"indexes_thai/month/{n}" for n in ("Prodidx1.xlsx", "Prodidx2.xlsx", "capidx.xlsx")]
FILES += [f"indexes_eng/year/{n}" for n in ("Prodidx1_E.xlsx", "capidx_E.xlsx")]
PAGES = ["https://www.oie.go.th/", "https://www.oie.go.th/view/1/index_industrial/EN-US",
         "https://www.oie.go.th/view/1/%E0%B8%94%E0%B8%B1%E0%B8%8A%E0%B8%99%E0%B8%B5%E0%B8%AD%E0%B8%B8%E0%B8%95%E0%B8%AA%E0%B8%B2%E0%B8%AB%E0%B8%81%E0%B8%A3%E0%B8%A3%E0%B8%A1/TH-TH",
         "https://www.oie.go.th/view/1/industrial_index/EN-US", "https://indexes.oie.go.th/", "https://indexes.oie.go.th/Default.aspx",
         "https://indexes.oie.go.th/en/", "https://www.oie.go.th/en/"]
FOLLOW = re.compile(r"(index|indices|ดัชนี|%E0%B8%94%E0%B8%B1%E0%B8%8A%E0%B8%99%E0%B8%B5|MPI|Prodidx|capidx|\.xlsx?)", re.I)
SUMMARY = []


def fetch(url, out, timeout=120):
    req = urllib.request.Request(url, headers=UA)
    status, headers, body, err = None, {}, b"", None
    for attempt in range(3):
        try:
            with OPENER.open(req, timeout=timeout) as r:
                status, headers, body = r.status, dict(r.headers), r.read()
            err = None
            break
        except urllib.error.HTTPError as e:
            status, headers, body, err = e.code, dict(e.headers), e.read(), f"HTTPError {e.code}"
            if e.code not in (429, 500, 502, 503, 504):
                break
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        time.sleep(3 * (attempt + 1))
    ct = headers.get("Content-Type", "")
    fn = None
    if body:
        h = hashlib.md5(url.encode()).hexdigest()[:8]
        base = re.sub(r"[^A-Za-z0-9._-]+", "_", urllib.parse.unquote(url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]))[-80:]
        sub = "files" if re.search(r"\.(xlsx?|csv|zip|pdf)$", url.split("?")[0], re.I) or "sheet" in ct or "excel" in ct else "pages"
        fn = f"{sub}/{h}_{base or 'index'}" + ("" if sub == "files" else ".html")
        (out / fn).parent.mkdir(parents=True, exist_ok=True)
        (out / fn).write_bytes(body)
    SUMMARY.append({"url": url, "status": status, "error": err, "bytes": len(body), "ctype": ct, "file": fn,
                    "last_modified": headers.get("Last-Modified", "")})
    return status, ct, body


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        fetch(BASE + f, out)
    seen, found = set(), set()
    queue = [(p, 0) for p in PAGES]
    while queue and len(seen) < 80:
        u, d = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)
        st, ct, body = fetch(u, out)
        if not body or "html" not in ct:
            continue
        for m in re.finditer(r"""href\s*=\s*["']([^"'#]+)""", body.decode("utf-8", "replace"), re.I):
            v = urllib.parse.urljoin(u, m.group(1).strip())
            if not v.startswith("http") or "oie.go.th" not in v:
                continue
            if re.search(r"\.(xlsx?|csv|zip)(\?|$)", v, re.I):
                found.add(v)
            elif d < 2 and FOLLOW.search(v):
                queue.append((v, d + 1))
    for v in sorted(found - {BASE + f for f in FILES})[:60]:
        fetch(v, out)
    (out / "found.json").write_text(json.dumps(sorted(found), ensure_ascii=False, indent=0))
    (out / "summary.json").write_text(json.dumps(SUMMARY, ensure_ascii=False, indent=0))
    print(f"{len(SUMMARY)} requests, {sum(1 for s in SUMMARY if s['status'] == 200)} ok, {len(found)} file links")


if __name__ == "__main__":
    main()
