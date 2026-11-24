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


def vn():
    from core import nso_vn
    books = [b for b in nso_vn.report_workbooks("2026-10-01T00:00:00", "2026-11-20T00:00:00") if not b["en"]]
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
    for ds in (11765, 11766, 161208, 11767, 11768, 11769, 11770, 11771, 161209, 161211, 161212):
        try:
            meta = json.loads(get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}"))["result"]
            print(ds, meta["title"], [(d.get("resourceDescription"), d.get("resourceDownloadUrl")) for d in meta.get("distribution", [])][:3])
        except Exception as e:  # noqa: BLE001
            print(ds, e)


def ind():
    import openpyxl
    blob = get("https://ppac.gov.in/uploads/pages/1669199925_Import-Export-C.xlsx")
    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    print(wb.sheetnames)
    for ws in wb.worksheets[:3]:
        rows = list(ws.iter_rows(values_only=True))
        print("SHEET", ws.title, len(rows))
        for x in rows[:14]:
            print("  ", [c for c in x[:16]])


def th():
    h = get("https://www.eppo.go.th/index.php/en/component/k2/item/8653-table2-1-3").decode("utf-8", "replace")
    for m in sorted(set(re.findall(r'(https?://[^"\' ]+\.xlsx?)', h)))[:60]:
        print("XLS", m)
    i = h.find("2.1-3")
    print(re.sub(r"\s+", " ", h[i - 500:i + 3000]) if i > 0 else "no 2.1-3")


def my():
    body = {"tradeClass": "classification", "hsType": "HS4_digit", "flowTypes": ["Imports"], "frequencyType": "MONTHLY",
            "years": ["2026"], "months": ["07", "08"], "products": [{"codeValue": "2709", "codeName": ""}]}
    try:
        js = json.loads(get("https://metsonline.dosm.gov.my/api/Trade/classification-query", json.dumps(body).encode(), {"Content-Type": "application/json", "Accept": "application/json"}))
        print(js.get("columns"), str(js.get("items"))[:500], [k for k in js])
    except urllib.error.HTTPError as e:
        print(e.code, e.read()[:500])


import urllib.error  # noqa: E402
import urllib.parse  # noqa: E402
for n, f in (("VN", vn), ("ID", idn), ("TW", tw), ("IN", ind), ("TH", th), ("MY", my)):
    section(n, f)
