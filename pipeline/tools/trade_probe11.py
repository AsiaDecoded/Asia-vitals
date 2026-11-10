"""Trade probe round 11 (10 Nov 2026): KCS tradedata.go.kr menu fragments with a cookie session.

  python -I pipeline/tools/trade_probe11.py discovery/trade11
"""
import http.cookiejar
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "discovery/trade11")
OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
CJ = http.cookiejar.CookieJar()
OP = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CJ))
LOG = []
B = "https://tradedata.go.kr"


def go(name, path, data=None, xhr=True):
    h = {"User-Agent": UA, "Referer": B + "/cts/index.do", "Accept": "*/*", "Accept-Language": "ko"}
    if xhr:
        h["X-Requested-With"] = "XMLHttpRequest"
    if data is not None:
        h["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    t = time.time()
    try:
        with OP.open(urllib.request.Request(B + path, data=data, headers=h), timeout=60) as r:
            b, st = r.read(), r.status
    except urllib.error.HTTPError as e:
        b, st = e.read(), e.code
    except Exception as e:  # noqa: BLE001
        b, st = repr(e).encode(), -1
    (OUT / f"{name}.txt").write_bytes(b)
    txt = b.decode("utf-8", "replace")
    LOG.append({"name": name, "path": path, "status": st, "bytes": len(b), "secs": round(time.time() - t, 1),
                "title": (re.findall(r"<title>([^<]*)", txt) or [""])[0], "head": txt[:150]})
    return txt


go("index", "/cts/index.do", xhr=False)
for p in ("0100019", "0100027", "0100037", "0100018"):
    for mode, data in (("get", None), ("post", b"")):
        h = go(f"m{p}_{mode}", f"/cts/hmpg/openETS{p}Q.do", data=data)
        urls = sorted(set(re.findall(r"['\"](/cts/[\w/]+\.do)['\"]", h)))
        js = sorted(set(re.findall(r'src="([^"]+\.js[^"]*)"', h)))
        (OUT / f"m{p}_{mode}_urls.txt").write_text("\n".join(urls + ["--js--"] + js))
        for i, j in enumerate(js):
            if "/cts/js/" in j:
                t = go(f"m{p}_{mode}_js{i}", j if j.startswith("/") else "/" + j, xhr=False)
                (OUT / f"m{p}_{mode}_js{i}_urls.txt").write_text("\n".join(sorted(set(re.findall(r"['\"](/cts/[\w/]+\.do)['\"]", t)))))
(OUT / "log.json").write_text(json.dumps(LOG, indent=1))
