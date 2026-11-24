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


def jp():
    from sources.trade_jp import fetch
    r = list(csv.reader(io.StringIO(fetch("d61ma.csv"))))
    ci = next(i for i, x in enumerate(r) if x and x[0].strip() == "概況品コード")
    for i in range(max(0, ci - 4), ci + 2):
        print("ROW", i, r[i][:12])
    k = next(k for k, c in enumerate(r[ci]) if c.strip() == "'30301'")
    print("crude cols", k, [r[j][k - 1:k + 3] for j in range(ci - 3, ci + 2)])
    for x in r[-3:]:
        print("DATA", x[0], x[k - 1:k + 3])


def kr():
    from sources.trade_kr import Site
    s = Site()
    it = s.query(tradeKind="ETS_MNK_1020000A", priodFr="202608", priodTo="202608", hsSgnGrpCol="HS4_SGN", hsSgnWhrCol="HS4_SGN", hsSgn="2709", subHsSgn="")
    print(json.dumps(it[:2], ensure_ascii=False)[:1500])


def vn():
    from sources import nso_vn
    books = nso_vn.report_workbooks()
    print("books", [b.get("url", "")[-70:] for b in books[:3]])
    import openpyxl
    blob = nso_vn.get(books[0]["url"])[0]
    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    for ws in wb.worksheets:
        if re.search(r"NK\s*tháng", ws.title):
            rows = list(ws.iter_rows(values_only=True))
            for x in rows[:7]:
                print("HDR", x[:10])
            for x in rows:
                if x and any(isinstance(c, str) and "Dầu thô" in c for c in x):
                    print("CRUDE", x[:10])


def idn():
    from sources import trade_id
    js = trade_id.dataexim(2, "27", 2, 2025)
    print(str(js)[:1500])


def tw():
    meta = json.loads(get("https://data.gov.tw/api/v2/rest/dataset/11765"))
    print(json.dumps(meta, ensure_ascii=False)[:1500])
    for q in ("原油進口", "原油"):
        try:
            res = json.loads(get("https://data.gov.tw/api/v2/rest/dataset?q=" + urllib.parse.quote(q) + "&limit=20"))
            print(q, json.dumps(res, ensure_ascii=False)[:2000])
        except Exception as e:  # noqa: BLE001
            print("search", q, e)


def ind():
    h = get("https://ppac.gov.in/import-export").decode("utf-8", "replace")
    print("len", len(h))
    for m in re.findall(r'href="([^"]+\.(?:xlsx?|pdf|csv))"', h)[:40]:
        print("LINK", m)


def th():
    for u in ("https://www.eppo.go.th/index.php/en/component/k2/item/8653-table2-1-3", "https://www.eppo.go.th/index.php/en/en-energystatistics/petroleum-statistic"):
        h = get(u).decode("utf-8", "replace")
        print(u, "len", len(h))
        for m in re.findall(r'href="([^"]+)"[^>]*>([^<]{0,80})', h):
            if re.search(r"xls|download|2\.1-3|T02_01_03|table2", m[0], re.I):
                print("LINK", m[0], "|", m[1].strip())


def my():
    body = {"tradeClass": "classification", "hsType": "HS4_digit", "flowTypes": ["Imports"], "frequencyType": "MONTHLY",
            "years": ["2026"], "months": ["07", "08"], "products": [{"codeValue": "2709", "codeName": ""}]}
    for extra in ({}, {"measure": "QUANTITY"}, {"valueType": "Quantity"}, {"isQuantity": True}):
        js = json.loads(get("https://metsonline.dosm.gov.my/api/Trade/classification-query", json.dumps(dict(body, **extra)).encode(), {"Content-Type": "application/json"}))
        print(extra, js.get("columns"), str(js.get("items"))[:300])


def sg():
    for kw in ("crude", "petroleum", "oil"):
        js = json.loads(get("https://tablebuilder.singstat.gov.sg/api/table/resourceid?keyword=" + kw + "&searchOption=all"))
        recs = (js.get("Data") or {}).get("records") or []
        print(kw, len(recs))
        for r in recs[:25]:
            print("  ", r.get("id"), r.get("title"))


import urllib.parse  # noqa: E402
for n, f in (("JP", jp), ("KR", kr), ("VN", vn), ("ID", idn), ("TW", tw), ("IN", ind), ("TH", th), ("MY", my), ("SG", sg)):
    section(n, f)
