"""Trade probe round 14 (10 Nov 2026): KCS tradedata.go.kr menu fragments with a cookie session.

  python -I pipeline/tools/trade_probe14.py discovery/trade14
"""
import http.cookiejar
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "discovery/trade14")
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
import urllib.parse
go("page19", "/cts/hmpg/openETS0100019Q.do", data=b"menuId=ETS_MNK_10200000")
base = {"priodKind": "MON", "statsBase": "acptDd", "ttwgTpcd": "1000", "selectPaging": "1", "showPagingLine": "1000",
        "sortColumn": "", "sortOrder": ""}
Q = {
    "hs2_85": dict(base, tradeKind="ETS_MNK_1020000A", priodFr="202501", priodTo="202609", hsSgnGrpCol="HS2_SGN", hsSgnWhrCol="HS2_SGN", hsSgn="85", subHsSgn=""),
    "hs4_list": dict(base, tradeKind="ETS_MNK_1020000A", priodFr="202601", priodTo="202609", hsSgnGrpCol="HS4_SGN", hsSgnWhrCol="HS4_SGN", hsSgn="8419,8470,8471,8472,8473,2709,2710", subHsSgn=""),
    "hs2_all": dict(base, tradeKind="ETS_MNK_1020000A", priodFr="202609", priodTo="202609", hsSgnGrpCol="HS2_SGN", hsSgnWhrCol="HS2_SGN", hsSgn="", subHsSgn=""),
    "cnty_us_cn": dict(base, tradeKind="ETS_MNK_1020000D", priodFr="202501", priodTo="202609", cntyNm="US,CN"),
    "cnty_all": dict(base, tradeKind="ETS_MNK_1020000D", priodFr="202609", priodTo="202609", cntyNm=""),
    "cnty_old": dict(base, tradeKind="ETS_MNK_1020000D", priodFr="199001", priodTo="199012", cntyNm="US"),
    "hs_old": dict(base, tradeKind="ETS_MNK_1020000A", priodFr="200001", priodTo="200012", hsSgnGrpCol="HS2_SGN", hsSgnWhrCol="HS2_SGN", hsSgn="85", subHsSgn=""),
    "eu": dict(base, tradeKind="ETS_MNK_1020000I", priodFr="202601", priodTo="202609", cntnEbkUnfcClsfCd="EU"),
}
for k, d in Q.items():
    go(f"q_{k}", "/cts/hmpg/retrieveTrade.do", data=urllib.parse.urlencode(d).encode())
(OUT / "log.json").write_text(json.dumps(LOG, indent=1))
