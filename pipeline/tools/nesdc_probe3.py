"""Round r3 of the NESDC probe: downloads the files listed on NESDC's QGDP and national-accounts pages.

NESDC (WordPress) sets a cookie on a first 302; files are served by `/en/?p=<post>&ddl=<attachment>` links held
in a JSON listing inside each page. This lists every (name, link, last_updated) found and downloads the files whose
name looks like statistical tables or GDP.

  python -I pipeline/tools/nesdc_probe3.py <out_dir> [max_files]
"""
import hashlib
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en;q=0.9,th;q=0.8"}
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
PAGES = ["https://www.nesdc.go.th/en/info/quarterly-gross-domestic-product-qgdp-en/",
         "https://www.nesdc.go.th/en/info/national-accounts/",
         "https://www.nesdc.go.th/info/quarterly-gross-domestic-product-qgdp/"]
WANT = re.compile(r"statistical table|all tables|national account|gdp|gross domestic|ตาราง|บัญชีประชาชาติ|time series|"
                  r"release calendar|calendar|chain volume", re.I)
SUMMARY = []


def fetch(url, timeout=180):
    req = urllib.request.Request(url, headers=UA)
    for attempt in range(3):
        try:
            with OPENER.open(req, timeout=timeout) as r:
                return r.status, dict(r.headers), r.read(), r.url
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504):
                return e.code, dict(e.headers), e.read(), url
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(4 * (attempt + 1))
    return None, {}, b"", url


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    max_files = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    items = {}
    for page in PAGES:
        st, h, body, final = fetch(page)
        SUMMARY.append({"url": page, "status": st, "bytes": len(body)})
        t = body.decode("utf-8", "replace")
        t = t.replace("\\\\\\/", "/").replace("\\/", "/").replace('\\\\\\"', '"').replace('\\"', '"')
        for m in re.finditer(r'href="?(https://www\.nesdc\.go\.th/(?:en/)?\?p=(\d+)&(?:amp;)?ddl=(\d+))', t):
            back = t[max(0, m.start() - 700):m.start()]
            names = re.findall(r'"name":\s*"([^"]{2,200})"', back)
            fwd = t[m.end():m.end() + 900]
            lu = re.search(r'"last_updated":\s*"([^"]*)"', fwd)
            cat = re.search(r'"category":\s*"([^"]*)"', fwd)
            key = m.group(3)
            if key not in items:
                items[key] = {"post": m.group(2), "ddl": key, "url": m.group(1).replace("&amp;", "&"),
                              "name": names[-1] if names else "", "last_updated": lu.group(1) if lu else "",
                              "category": cat.group(1) if cat else "", "page": page}
    (out / "items.json").write_text(json.dumps(list(items.values()), ensure_ascii=False, indent=1))
    picks = [i for i in items.values() if WANT.search(i["name"] + " " + i["category"])]
    # newest first by attachment id
    picks.sort(key=lambda i: -int(i["ddl"]))
    for i in picks[:max_files]:
        st, h, body, final = fetch(i["url"])
        cd = h.get("Content-Disposition", "")
        fn = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', cd)
        base = re.sub(r"[^A-Za-z0-9._-]+", "_", (fn.group(1) if fn else final.rsplit("/", 1)[-1]))[-90:]
        f = f"files/{i['ddl']}_{base}"
        if body:
            (out / f).parent.mkdir(parents=True, exist_ok=True)
            (out / f).write_bytes(body)
        SUMMARY.append({"url": i["url"], "final": final, "status": st, "bytes": len(body), "ctype": h.get("Content-Type", ""),
                        "disposition": cd, "file": f, "name": i["name"], "last_updated": i["last_updated"]})
    (out / "summary.json").write_text(json.dumps(SUMMARY, ensure_ascii=False, indent=1))
    print(f"{len(items)} download links, {len(picks)} picked")


if __name__ == "__main__":
    main()
