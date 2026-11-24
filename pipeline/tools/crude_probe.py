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
    import xlrd
    for f in ("T02_01_03.xls", "T02_01_03-1.xls"):
        b = get("https://www.eppo.go.th/wp-content/uploads/2026/06/" + f)
        wb = xlrd.open_workbook(file_contents=b)
        print(f, wb.sheet_names())
        sh = wb.sheet_by_index(0)
        for i in list(range(min(14, sh.nrows))) + list(range(max(0, sh.nrows - 4), sh.nrows)):
            print("  ", i, [c for c in sh.row_values(i)[:14]])


def tw():
    for sid in (238, 27):
        try:
            b = get(f"https://www.moeaea.gov.tw/ECW/populace/opendata/wHandOpenData_File.ashx?set_id={sid}")
            print("TWSET", sid, len(b))
            print(b[:2000].decode("utf-8-sig", "replace"))
        except Exception as e:  # noqa: BLE001
            print("TWERR", sid, repr(e)[:300])


def idn():
    import os
    key = os.environ.get("BPS_KEY", "")
    u = f"https://webapi.bps.go.id/v1/api/list/model/data/domain/0000/var/2173/key/{key}/"
    js = json.loads(get(u))
    print({k: (str(v)[:600]) for k, v in js.items()})


import urllib.error  # noqa: E402
import urllib.parse  # noqa: E402
for n, f in (("TH", th), ("TW", tw), ("ID", idn)):
    section(n, f)
