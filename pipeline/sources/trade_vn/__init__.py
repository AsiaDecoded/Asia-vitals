"""Vietnam merchandise trade: General Statistics Office (NSO) monthly socio-economic report tables (Biểu 26 hàng hóa
xuất khẩu, Biểu 27 hàng hóa nhập khẩu), as published, US$ million (preliminary/estimate for the latest month).

  totals; exports of 'Điện tử, máy tính và linh kiện' (computers, electronic products and components), 'Điện thoại các
  loại và linh kiện' (phones and parts), 'Máy ảnh, máy quay phim và linh kiện' (cameras), 'Dây điện và cáp điện'
  (wires and cables); imports of 'Dầu thô' (crude oil) and 'Xăng dầu' (petroleum products).
The workbooks are the ones vn_gdp_nso / vn_ppi_nso already read (NSO WordPress media). Partner detail is published by
Vietnam Customs (customs.gov.vn), which does not answer requests from GitHub's runners: not collected.
"""
import io
import re
import time

from core import nso_vn, trade
from core.common import CheckFailed, write_release

NAME = "trade_vn"
DESCRIPTION = "Vietnam merchandise trade (NSO monthly report tables, US$): totals, electronics groups, oil imports"
ROWS = {"exports": {"TỔNG TRỊ GIÁ": "TOTAL", "Điện tử, máy tính và linh kiện": "computers_electronics",
                    "Điện thoại các loại và linh kiện": "phones", "Máy ảnh, máy quay phim và linh kiện": "cameras",
                    "Dây điện và cáp điện": "wires_cables"},
        "imports": {"TỔNG TRỊ GIÁ": "TOTAL", "Dầu thô": "crude_oil", "Xăng dầu": "petroleum_products"}}
BUDGET = 30


def sheets(blob):
    """(title, rows) for each sheet of an .xlsx or an old .xls workbook."""
    if blob[:4] == b"\xd0\xcf\x11\xe0":
        import xlrd  # noqa: PLC0415
        wb = xlrd.open_workbook(file_contents=blob)
        for sh in wb.sheets():
            yield sh.name, [tuple(sh.row_values(i)) for i in range(sh.nrows)]
        return
    import openpyxl  # noqa: PLC0415
    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    for ws in wb.worksheets:
        yield ws.title, list(ws.iter_rows(values_only=True))


def parse(blob, ym_hint):
    out = []
    for title, rows in sheets(blob):
        flow = "exports" if re.search(r"XK\s*tháng|^2\d\.\s*XK", title) else "imports" if re.search(r"NK\s*tháng", title) else None
        if not flow:
            continue
        head = " ".join(str(c) for r in rows[:6] for c in r if c)
        m = re.search(r"Tháng\s*(\d{1,2}).*?năm\s*(20\d\d)", head, re.S)
        if not m:
            continue
        d = f"{m.group(2)}-{int(m.group(1)):02d}-01"
        for r in rows:
            label = next((str(c).strip() for c in r[:2] if c and str(c).strip()), "")
            prod = next((p for k, p in ROWS[flow].items() if label.startswith(k)), None)
            if prod and len(r) > 3 and isinstance(r[3], (int, float)):
                out.append({"economy": "VN", "flow": flow, "partner": "WLD", "product": prod, "date": d, "value": float(r[3]),
                            "unit": "USD million", "usd_mn": float(r[3]), "usd_calculated": "", "series": f"NSO report {title.strip()} {label}"})
                if prod == "crude_oil" and isinstance(r[2], (int, float)):     # 'Lượng', thousand tonnes
                    out.append({"economy": "VN", "flow": flow, "partner": "WLD", "product": "crude_oil_volume", "date": d,
                                "value": round(float(r[2]) * 1000, 3), "unit": "tonnes", "usd_mn": None, "usd_calculated": "",
                                "series": f"NSO report {title.strip()} {label} (Lượng, thousand tonnes)"})
    return out


def update(force=False, **_):
    st = trade.Store("vn")
    warn = []
    today = time.strftime("%Y-%m")
    for ym in reversed(trade.months("2020-01", today)):
        y, m = int(ym[:4]), int(ym[5:7])
        after = f"{trade.shift(ym, 1)}-01T00:00:00"
        before = f"{trade.shift(ym, 2)}-01T00:00:00"
        def fetch():
            books = [b for b in nso_vn.report_workbooks(after, before) if not b["en"]]
            for b in [b for b in books if ".En" not in b.get("url", "")][:3]:   # English editions use other labels
                try:
                    rows = parse(nso_vn.get(b["url"])[0], ym)
                except Exception as e:  # noqa: BLE001  (some uploads are not .xlsx)
                    warn.append(f"{ym}: {b.get('url', '')[-60:]}: {repr(e)[:120]}")
                    continue
                if any(r["date"][:7] == ym for r in rows):
                    return [r for r in rows if r["date"][:7] == ym]
            return []
        got = st.get(f"q:{ym}", fetch, refresh=ym >= trade.shift(today, -2), budget=BUDGET)
        if got:
            st.data.pop(f"m:{ym}", None)
        elif got is not None and st.data.get(f"m:{ym}"):
            st.data.pop(f"q:{ym}", None)        # report not found this time: keep the earlier read, try again next run
    st.save()
    rows = [r for k, v in st.data.items() for r in (v or []) if k.startswith("q:") or f"q:{k[2:]}" not in st.data]
    if not rows:
        raise CheckFailed(["NSO report tables: nothing read"])
    last = trade.latest(rows)
    folder = trade.write("vn", rows)
    code = f"T{last[:7]}h{len(st.data)}"
    write_release(folder, {"code": code, "label": last[:7], "latest_month": last, "source": NAME, "table": "NSO monthly report tables 26, 27"},
                  warn[:20], len(rows), {"fetched": st.fetched})
    return {"updated": True, "code": code, "summary": f"{last[:7]}: {len(rows)} rows", "warnings": warn[:5]}
