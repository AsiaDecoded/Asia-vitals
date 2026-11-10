"""Trade probe round 9 (9 Nov 2026): Korea trade without an API key: KCS tradedata.go.kr, KOSIS, KITA.

  python -I pipeline/tools/trade_probe9.py discovery/trade9
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "discovery/trade9")
OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
LOG = []
PX = "https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/2L/IMT/"
METS = "https://metsonline.dosm.gov.my/api/"


def call(name, url, body=None, cap=2_000_000):
    t = time.time()
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=120) as r:
            b = r.read()
            st = r.status
    except urllib.error.HTTPError as e:
        b, st = e.read(), e.code
    except Exception as e:  # noqa: BLE001
        b, st = repr(e).encode(), -1
    (OUT / f"{name}.json").write_bytes(b[:cap])
    LOG.append({"name": name, "url": url, "body": body, "status": st, "bytes": len(b), "secs": round(time.time() - t, 1),
                "head": b[:300].decode("utf-8", "replace")})
    try:
        return json.loads(b)
    except Exception:  # noqa: BLE001
        return None


import re
def page(name, url, data=None, extra=None):
    h = {"User-Agent": UA, "Accept": "text/html,application/json,*/*", "Accept-Language": "ko,en;q=0.8"}
    if extra: h.update(extra)
    t = time.time()
    try:
        rq = urllib.request.Request(url, data=data, headers=h)
        with urllib.request.urlopen(rq, timeout=60) as r:
            b, st, ct = r.read(), r.status, r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        b, st, ct = e.read(), e.code, ""
    except Exception as e:  # noqa: BLE001
        b, st, ct = repr(e).encode(), -1, ""
    (OUT / f"{name}.txt").write_bytes(b[:3_000_000])
    LOG.append({"name": name, "url": url, "status": st, "bytes": len(b), "ctype": ct, "secs": round(time.time() - t, 1), "head": b[:200].decode("utf-8", "replace")})
    return b.decode("utf-8", "replace")

roots = {
    "kcs_root": "https://tradedata.go.kr/cts/index.do",
    "kcs_root2": "https://tradedata.go.kr/",
    "kcs_item": "https://tradedata.go.kr/cts/hmpg/openITS0201001Q.do",
    "kcs_nation": "https://tradedata.go.kr/cts/hmpg/openITS0101001Q.do",
    "unipass": "https://unipass.customs.go.kr/ets/",
    "kita_root": "https://stat.kita.net/",
    "kita_item": "https://stat.kita.net/stat/kts/prod/ProdImpExpList.screen",
    "kosis_root": "https://kosis.kr/",
    "kosis_trade": "https://kosis.kr/statHtml/statHtml.do?orgId=134&tblId=DT_134001_001",
}
for k, u in roots.items():
    h = page(k, u)
    eps = sorted(set(re.findall(r"[\w/\-\.]+\.(?:do|json|screen|action)", h)))
    (OUT / f"{k}_endpoints.txt").write_text("\n".join(eps))
    for i, js in enumerate(sorted(set(re.findall(r'src="([^"]+\.js[^"]*)"', h)))[:25]):
        base = re.match(r"https?://[^/]+", u).group(0)
        jsu = js if js.startswith("http") else base + "/" + js.lstrip("/")
        if "jquery" in jsu.lower() or "bootstrap" in jsu.lower():
            continue
        t = page(f"{k}_js{i}", jsu)
        hits = sorted(set(re.findall(r"[\w/\-\.]+\.(?:do|json|screen|action)", t)))
        if hits:
            (OUT / f"{k}_js{i}_endpoints.txt").write_text(jsu + "\n" + "\n".join(hits))
(OUT / "log.json").write_text(json.dumps(LOG, indent=1))
