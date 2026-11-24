"""Crude oil import volumes probe (24 Nov 2026): what each national source gives. Prints to the log."""
import csv
import io
import json
import re
import sys
import traceback
import urllib.request

sys.path.insert(0, ".")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}


def get(url, data=None, headers=None):
    h = dict(UA, **(headers or {}))
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=120) as r:
        return r.read()


def section(name, fn):
    print(f"\n===== {name}")
    try:
        fn()
    except Exception:  # noqa: BLE001
        traceback.print_exc(limit=3)


def th():
    h = get("https://www.eppo.go.th/?p=25878").decode("utf-8", "replace")
    print("len", len(h))
    for m in re.findall(r'href="([^"]+)"[^>]*>(.{0,120}?)</a>', h, re.S):
        t = re.sub(r"<[^>]+>|\s+", " ", m[1]).strip()
        if re.search(r"xls|2\.1|T02", m[0] + t, re.I):
            print("LINK", m[0], "|", t[:80])


def tw():
    for sid in (238, 27):
        b = get(f"https://www.moeaea.gov.tw/ECW/populace/opendata/wHandOpenData_File.ashx?set_id={sid}")
        print(sid, len(b), b[:1500].decode("utf-8-sig", "replace"))


def idn():
    import os
    key = os.environ.get("BPS_KEY", "")
    for kw in ("minyak mentah", "impor migas", "volume impor"):
        u = f"https://webapi.bps.go.id/v1/api/list/model/var/domain/0000/keyword/{urllib.parse.quote(kw)}/key/{key}/"
        js = json.loads(get(u))
        data = js.get("data") or []
        rows = data[1] if len(data) > 1 else []
        print(kw, js.get("status"), [(r.get("var_id"), r.get("title"), r.get("unit")) for r in rows][:25])


def my():
    import socket
    socket.setdefaulttimeout(60)
    body = {"tradeClass": "classification", "hsType": "HS4_digit", "flowTypes": ["Imports"], "frequencyType": "MONTHLY",
            "years": ["2026"], "months": ["07", "08"], "products": [{"codeValue": "2709", "codeName": ""}]}
    try:
        js = json.loads(get("https://metsonline.dosm.gov.my/api/Trade/classification-query", json.dumps(body).encode(), {"Content-Type": "application/json", "Accept": "application/json"}))
        print("cols", js.get("columns"), str(js.get("items"))[:500], [k for k in js])
    except Exception as e:  # noqa: BLE001
        print("ERR", repr(e)[:300])


def jp():
    from sources.trade_jp import fetch
    r = list(csv.reader(io.StringIO(fetch("d61ma.csv"))))
    k = next(k for k, c in enumerate(r[4]) if c.strip() == "'30301'")
    for x in r[:12]:
        print("ROW", x[0][:30], x[k - 1:k + 3])
    good = [x for x in r if x and re.match(r"\d{4}/\d{2}", x[0]) and x[k] not in ("-", "")]
    for x in good[-3:]:
        print("DATA", x[0], x[k - 1:k + 3])


import urllib.error  # noqa: E402
import urllib.parse  # noqa: E402
for n, f in (("TH", th), ("TW", tw), ("ID", idn), ("MY", my), ("JP", jp)):
    section(n, f)
