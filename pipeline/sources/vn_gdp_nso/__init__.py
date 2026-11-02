"""Vietnam GDP by industry, and industrial production by VSIC division, as published by NSO.

Quarterly GDP from the socio-economic report tables ("Biểu") released with the CPI in quarter-end months
(table 1, GDP at current prices: VND bn and % structure; table 2, GDP at constant prices: VND bn and
same period last year = 100; in Q1 books one combined table, with growth printed as a % rate from 2024).
28 rows: total, three sectors, product taxes less subsidies, and 23 sub-sectors (ISIC sections A01-A03, B-T).
Constant prices are 2010 prices to the Q4 2025 book and 2020 prices from the Q1 2026 book; current-price levels
from 2026 are on the rebased scale. Each book gives the reference quarter (estimate), the previous quarter
(preliminary) and the year to date; the latest book's figure for each period is kept, every vintage is stored.

Manufacturing below ISIC section C is not in the GDP tables. The deepest official split is the industrial
production index (IIP) by VSIC 2-digit division (24 manufacturing divisions, 10-33), same quarter last year = 100,
from the quarterly IIP table in the same books (Q1 books: the 'Quý I' column of the monthly IIP table).

Annual, from NSO's PX-Web yearbook database (updated once a year with the yearbook; re-exported at most monthly):
GDP by sector at current prices from 1986 (E03.02, VND bn and % structure) and at constant 2010 prices from 2005
(E03.03, VND bn and previous year = 100); GDP by expenditure at current prices from 1995 (E03.08) and constant
2010 prices from 2005 (E03.09). The last two years are NSO's preliminary and estimated figures.

Reads the workbooks that vn_ppi_nso downloads (raw/vn/ppi_nso/books); runs after it. Nothing is calculated:
rate is the published index - 100, or the published % rate where NSO prints the rate.
"""
import csv
import gzip
import json
import re
import time

from core import nso_vn as N
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "vn_gdp_nso"
DESCRIPTION = "Vietnam quarterly GDP by industry (current and constant prices) and IIP by VSIC division (NSO report tables)"
OUT = DATA / "vn" / "gdp"
BOOKS = RAW / "vn" / "ppi_nso"
REBASE_BOOK = "2026-Q1"   # first book on 2020 constant prices (and the revised current-price scale)
CODES = {c: (isic, en, lvl) for c, isic, en, lvl, _ in N.GDP_ROWS}
ORDER = {c: i for i, (c, *_rest) in enumerate(N.GDP_ROWS)}

# Industrial production index rows: (code, VSIC, English, level, Vietnamese label pattern), NSO's order
IIP_ROWS = [
    ("all", "B-E", "All industry", 0, r"^Toàn ngành"),
    ("b", "B", "Mining and quarrying", 1, r"^Khai khoáng\s*$"),
    ("b05", "05", "Coal and lignite", 2, r"^Khai thác than"),
    ("b06", "06", "Crude petroleum and natural gas", 2, r"^Khai thác dầu thô"),
    ("b07", "07", "Metal ores", 2, r"^Khai thác quặng kim loại"),
    ("b08", "08", "Other mining and quarrying", 2, r"^Khai khoáng khác"),
    ("b09", "09", "Mining support services", 2, r"^Hoạt động dịch vụ hỗ trợ khai"),
    ("c", "C", "Manufacturing", 1, r"^Công nghiệp chế biến,? chế tạo\s*$"),
    ("c10", "10", "Food products", 2, r"^Sản xuất,? chế biến thực phẩm"),
    ("c11", "11", "Beverages", 2, r"^Sản xuất đồ uống"),
    ("c12", "12", "Tobacco products", 2, r"^Sản xuất sản phẩm thuốc lá"),
    ("c13", "13", "Textiles", 2, r"^Dệt"),
    ("c14", "14", "Wearing apparel", 2, r"^Sản xuất trang phục"),
    ("c15", "15", "Leather and related products", 2, r"^Sản xuất da"),
    ("c16", "16", "Wood and wood products (excl. furniture)", 2, r"^Chế biến gỗ"),
    ("c17", "17", "Paper and paper products", 2, r"^Sản xuất giấy"),
    ("c18", "18", "Printing and reproduction of recorded media", 2, r"^In,? sao chép"),
    ("c19", "19", "Coke and refined petroleum products", 2, r"^Sản xuất than cốc"),
    ("c20", "20", "Chemicals and chemical products", 2, r"^Sản xuất hoá chất|^Sản xuất hóa chất"),
    ("c21", "21", "Pharmaceuticals", 2, r"^Sản xuất thuốc,? hoá dược|^Sản xuất thuốc,? hóa dược"),
    ("c22", "22", "Rubber and plastics products", 2, r"^Sản xuất sản phẩm từ cao su"),
    ("c23", "23", "Other non-metallic mineral products", 2, r"^Sản xuất sản phẩm từ khoáng phi kim"),
    ("c24", "24", "Basic metals", 2, r"^Sản xuất kim loại\s*$"),
    ("c25", "25", "Fabricated metal products (excl. machinery)", 2, r"^Sản xuất sản phẩm từ kim loại đúc sẵn"),
    ("c26", "26", "Computer, electronic and optical products", 2, r"^Sản xuất sản phẩm điện tử"),
    ("c27", "27", "Electrical equipment", 2, r"^Sản xuất thiết bị điện"),
    ("c28", "28", "Machinery and equipment n.e.c.", 2, r"^Sản xuất máy móc"),
    ("c29", "29", "Motor vehicles", 2, r"^Sản xuất xe có động cơ"),
    ("c30", "30", "Other transport equipment", 2, r"^Sản xuất phương tiện vận tải"),
    ("c31", "31", "Furniture", 2, r"^Sản xuất giường"),
    ("c32", "32", "Other manufacturing", 2, r"^Công nghiệp chế biến,? chế tạo khác"),
    ("c33", "33", "Repair and installation of machinery", 2, r"^Sửa chữa,? bảo dưỡng"),
    ("d", "D", "Electricity, gas, steam and air conditioning", 1, r"^Sản xuất và phân phối điện"),
    ("e", "E", "Water supply, sewerage and waste management", 1, r"^Cung cấp nước"),
    ("e36", "36", "Water collection, treatment and supply", 2, r"^Khai thác,? xử lý và cung cấp nước"),
    ("e37", "37", "Sewerage", 2, r"^Thoát nước"),
    ("e38", "38", "Waste collection, treatment and disposal; recycling", 2, r"^Hoạt động thu gom"),
]
UNIT = {"level": "VND bn", "share": "% of GDP", "yoy": "%"}
PXDIR = RAW / "vn" / "gdp_nso" / "px"
HIST = RAW / "vn" / "gdp_nso" / "hist_sheets.json.gz"
PX_TABLES = {"E03.02.px": ("sector", "current"), "E03.03.px": ("sector", "constant_2010"),
             "E03.08.px": ("expenditure", "current"), "E03.09.px": ("expenditure", "constant_2010")}
ANN_ITEMS = [  # (table kind, code, English label, level, PX label pattern)
    ("sector", "total", "GDP", 0, r"^Total$"), ("sector", "agri", "Agriculture, forestry and fishing", 1, r"^Agriculture"),
    ("sector", "ind_constr", "Industry and construction", 1, r"^Industry and construction"), ("sector", "services", "Services", 1, r"^Services"),
    ("sector", "taxes", "Taxes on products less subsidies on products", 1, r"^Taxes"),
    ("expenditure", "total", "GDP", 0, r"^TOTAL$"), ("expenditure", "final_consumption", "Final consumption", 1, r"^Final consumption(\(\*\))?$"),
    ("expenditure", "fc_household", "Household final consumption", 2, r"^Final consumption- Household"),
    ("expenditure", "fc_state", "Government final consumption", 2, r"^Final consumption- State"),
    ("expenditure", "gcf", "Gross capital formation", 1, r"^Gross capital formation$"),
    ("expenditure", "gfcf", "Gross fixed capital formation", 2, r"^Gross capital formation- Gross\s+fixed"),
    ("expenditure", "inventories", "Changes in inventories", 2, r"^Gross capital formation- Changes"),
    ("expenditure", "trade_balance", "Balance of trade (goods and services)", 1, r"^Balance of Trade"),
    ("expenditure", "discrepancy", "Statistical discrepancy", 1, r"^Statistical discrepancy"),
]


def _px_tables(force):
    PXDIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for t in PX_TABLES:
        p = PXDIR / f"{t}.gz"
        if force or not p.exists() or (time.time() - p.stat().st_mtime) > 31 * 86400:
            try:
                p.write_bytes(gzip.compress(N.px_export(t, db=N.PX_DB_NA)))
            except Exception as e:  # noqa: BLE001
                if not p.exists():
                    raise
                print(f"   PX-Web {t}: export failed ({e}); using stored copy")
        out[t] = gzip.decompress(p.read_bytes())
    return out


def _annual(force, warnings):
    rows = []
    for t, body in _px_tables(force).items():
        kind, price = PX_TABLES[t]
        meta, dims, cells = N.parse_px(body)
        upd = meta.get("LAST-UPDATED", "")
        item_dim = next(d for d in dims if d not in ("Year", "Items"))
        merged = {}
        for c in cells:
            if c["value"] is None:
                continue
            m = re.search(r"(\d{4})", c["Year"])
            if not m:
                continue
            year = m.group(1)
            status = "preliminary" if re.search(r"Prel", c["Year"]) else "estimate" if re.search(r"Est", c["Year"]) else ""
            item = re.sub(r"\s+", " ", c[item_dim]).strip()
            hit = next(((code, en, lvl) for k, code, en, lvl, pat in ANN_ITEMS if k == kind and re.search(pat, item)), None)
            if not hit:
                warnings.append(f"PX-Web {t}: item not recognised: {item}")
                continue
            it = c["Items"]
            measure = "level" if re.search(r"Bill", it) else "share" if re.search(r"Structure", it) else "yoy" if re.search(r"Index", it) else None
            if not measure:
                continue
            code, en, lvl = hit
            merged[(year, code, measure)] = {
                "date": f"{year}-12-01", "year": year, "table": kind, "code": code, "item": en, "level": lvl, "price": price,
                "measure": measure, "value": round(c["value"], 6), "rate": round(c["value"] - 100, 6) if measure == "yoy" else "",
                "unit": {"level": "VND bn", "share": "% of GDP", "yoy": "%"}[measure], "status": status,
                "px_table": t, "release_date": f"{upd[:4]}-{upd[4:6]}-{upd[6:8]}" if upd else "", "source": "nso_pxweb"}
        rows += list(merged.values())
    return rows

SPAN_LABEL = {"Q": "quarter", "6M": "first half", "9M": "nine months", "Y": "year"}


def _date(period, span):
    y = int(period[:4])
    m = {"Q": int(period[-1]) * 3 if "-Q" in period else 12, "6M": 6, "9M": 9, "Y": 12}[span]
    return f"{y}-{m:02d}-01"


def _iip_code(label):
    return next(((c, v, en, lvl) for c, v, en, lvl, pat in IIP_ROWS if N.re.search(pat, label)), None)


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    index = read_json(BOOKS / "books.json", {}) or {}
    if not index:
        raise CheckFailed(["no report workbooks stored (vn_ppi_nso must run first)"])
    latest_book = max(index)
    if not force and state.get("latest_book") == latest_book:
        return {"updated": False, "code": state.get("code"), "summary": f"no new quarter (latest {latest_book})"}
    errors, warnings = [], []
    vint, iip_v = [], []
    # History, Q3 2010 - Q4 2019: GDP sheets kept from the older report books (fixed; read once from NSO's media
    # library, raw/vn/gdp_nso/hist_sheets.json.gz). 1994 prices to 2012, 2010 prices from 2013. Quarter-on-year
    # rates for single quarters are in these tables only for Q1 and from Q2 2018; otherwise year to date.
    hist = json.loads(gzip.decompress(HIST.read_bytes())) if HIST.exists() else []
    for h in sorted(hist, key=lambda h: h["ref"]):
        for r in N.read_gdp_sheets(list(h["sheets"].items()), h["ref"]):
            vint.append({**r, "release": h["ref"], "release_date": "", "book": h["url"].rsplit("/", 1)[-1]})
    for key, info in sorted(index.items()):
        body = (BOOKS / "books" / info["file"]).read_bytes()
        rel = info["uploaded"][:10]
        for r in N.read_gdp_book(body, info["file"], key):
            vint.append({**r, "release": key, "release_date": rel})
        for r in N.read_iip_book(body, info["file"], key):
            iip_v.append({**r, "release": key, "release_date": rel})
    # GDP: latest vintage per period, span, industry, price basis and measure
    latest = {}
    for r in vint:
        latest[(r["period"], r["span"], r["code"], r["price"], r["measure"])] = r
    rows = []
    for (period, span, code, price, measure), r in latest.items():
        isic, en, lvl = CODES[code]
        pub = r["as_published"]
        rate = None
        if measure == "yoy":
            rate = r["value"] - 100 if pub == "index" else r["value"]
        rows.append({"date": _date(period, span), "period": period, "span": span, "code": code, "isic": isic, "industry": en,
                     "level": lvl, "price": price, "measure": measure, "value": round(r["value"], 6),
                     "rate": "" if rate is None else round(rate, 6), "as_published": pub, "unit": UNIT[measure],
                     "status": r["status"], "release": r["release"], "release_date": r["release_date"],
                     "base_break": 1 if period.startswith(REBASE_BOOK[:4]) and span == "Q" and period.endswith("Q1") else 0,
                     "label_vi": r["label_vi"], "source": "nso_report"})
    # IIP: latest vintage per period and row
    il = {}
    for r in iip_v:
        hit = _iip_code(r["label_vi"])
        if not hit:
            warnings.append(f"IIP {r['release']}: row not recognised: {r['label_vi'][:60]}")
            continue
        il[(r["period"], hit[0])] = (r, hit)
    iip = []
    for (period, code), (r, (c, vsic, en, lvl)) in il.items():
        iip.append({"date": _date(period, "Q"), "period": period, "code": code, "vsic": vsic, "industry": en, "level": lvl,
                    "value": round(r["value"], 6), "rate": round(r["value"] - 100, 6), "release": r["release"],
                    "release_date": r["release_date"], "label_vi": r["label_vi"], "source": "nso_report"})

    ann = _annual(force, warnings)

    # --- checks
    q = [r for r in rows if r["span"] == "Q"]
    last = max(r["period"] for r in q)
    if last != latest_book:
        errors.append(f"latest GDP quarter {last} is not the latest book's quarter {latest_book}")
    if state.get("latest_quarter") and last < state["latest_quarter"]:
        errors.append(f"latest quarter {last} is before the one stored ({state['latest_quarter']})")
    have = {(r["period"], r["code"], r["price"][:8], r["measure"]) for r in q}
    for code in CODES:
        for price, measure in (("current", "level"), ("current", "share"), ("constant", "level"), ("constant", "yoy")):
            if (last, code, price, measure) not in have:
                errors.append(f"{last}: {code} {price} {measure} missing")
    allq = sorted(index)
    miss = [k for k in allq if (k, "total", "constant", "yoy") not in have]
    ytd_have = {(r["period"], r["span"]) for r in rows if r["code"] == "total" and r["measure"] == "yoy"}
    for y in range(2013, int(last[:4])):
        for p, sp in ((f"{y}-Q1", "Q"), (f"{y}-H1", "6M"), (f"{y}-9M", "9M"), (str(y), "Y")):
            if (p, sp) not in ytd_have:
                errors.append(f"history: real GDP y/y {p} missing")
    if miss:
        errors.append(f"real GDP y/y missing for {miss}")
    for r in rows:
        if r["measure"] == "yoy" and not -80 < float(r["rate"]) < 250:
            errors.append(f"{r['period']} {r['code']} y/y {r['rate']} out of range")
        if r["measure"] == "share" and not 0 <= r["value"] <= 100.01:
            errors.append(f"{r['period']} {r['code']} share {r['value']} out of range")
        if r["measure"] == "level" and r["value"] <= 0:
            errors.append(f"{r['period']} {r['code']} level {r['value']} not positive")
    # identities NSO's tables hold (checks only; nothing derived is stored)
    by = {}
    for r in rows:
        by.setdefault((r["period"], r["span"], r["price"], r["measure"]), {})[r["code"]] = r["value"]
    parts = {"total": ["agri", "ind_constr", "services", "taxes"], "agri": ["agriculture", "forestry", "fishery"],
             "ind_constr": ["industry", "construction"], "industry": ["mining", "manufacturing", "electricity", "water"],
             "services": [c for c, (_, _, lvl) in CODES.items() if lvl == 2 and ORDER[c] > ORDER["services"] and c != "taxes"]}
    for (period, span, price, measure), d in by.items():
        if measure not in ("level", "share"):
            continue
        for tot, comp in parts.items():
            if tot in d and all(c in d for c in comp):
                s = sum(d[c] for c in comp)
                tol = 0.15 if measure == "share" else max(1.0, 0.0005 * d[tot])
                if abs(s - d[tot]) > tol:
                    (errors if tot == "total" else warnings).append(
                        f"{period} {span} {price} {measure}: {tot} {d[tot]:.2f} vs sum of parts {s:.2f}")
    ip = {(r["period"], r["code"]) for r in iip}
    for c in ("all", "c", "c10", "c26"):
        if (last, c) not in ip:
            errors.append(f"IIP {last} {c} missing")
    ndiv = len({r["code"] for r in iip if r["period"] == last and r["code"].startswith("c") and r["level"] == 2})
    if ndiv != 24:
        errors.append(f"IIP {last}: {ndiv} manufacturing divisions, expected 24")
    for r in iip:
        if not 30 < r["value"] < 300:
            errors.append(f"IIP {r['period']} {r['code']} {r['value']} out of range")
    have_a = {(r["table"], r["code"], r["price"], r["measure"]) for r in ann}
    for need in (("sector", "total", "current", "level"), ("sector", "total", "constant_2010", "yoy"),
                 ("expenditure", "fc_household", "current", "level"), ("expenditure", "gfcf", "constant_2010", "yoy")):
        if need not in have_a:
            errors.append(f"annual {need} missing")
    # the Q4 report's full-year current-price GDP and the yearbook's agree for years in both (warning only: revisions)
    yb = {r["year"]: r["value"] for r in ann if r["table"] == "sector" and r["code"] == "total" and r["price"] == "current" and r["measure"] == "level"}
    for r in rows:
        if r["span"] == "Y" and r["code"] == "total" and r["price"] == "current" and r["measure"] == "level" and r["period"] in yb:
            if abs(r["value"] - yb[r["period"]]) > 0.001 * yb[r["period"]]:
                warnings.append(f"{r['period']} nominal GDP: report {r['value']:.0f} vs yearbook {yb[r['period']]:.0f} (revised)")
    if errors:
        raise CheckFailed(errors)

    # --- outputs
    rows.sort(key=lambda r: (r["date"], r["span"], ORDER[r["code"]], r["price"], r["measure"]))
    cols = ["date", "period", "span", "code", "isic", "industry", "level", "price", "measure", "value", "rate", "as_published",
            "unit", "status", "release", "release_date", "base_break", "label_vi", "source"]
    with open(OUT / "vn_gdp.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    vint.sort(key=lambda r: (r["release"], r["period"], r["span"], ORDER[r["code"]], r["price"], r["measure"]))
    with open(OUT / "vn_gdp_vintages.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["release", "release_date", "period", "span", "code", "price", "measure", "status",
                                          "value", "as_published"], lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(vint)
    with open(OUT / "vn_gdp_dash.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "period", "span", "code", "isic", "industry", "level", "price", "measure",
                                          "value", "rate", "status", "base_break"], lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    iip.sort(key=lambda r: (r["date"], [c for c, *_ in IIP_ROWS].index(r["code"])))
    with open(OUT / "vn_iip.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "period", "code", "vsic", "industry", "level", "value", "rate", "release",
                                          "release_date", "label_vi", "source"], lineterminator="\n")
        w.writeheader()
        w.writerows(iip)
    with open(OUT / "vn_iip_dash.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "period", "code", "vsic", "industry", "level", "rate"], lineterminator="\n",
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(iip)
    ann.sort(key=lambda r: (r["table"], r["date"], r["code"], r["price"], r["measure"]))
    acols = ["date", "year", "table", "code", "item", "level", "price", "measure", "value", "rate", "unit", "status", "px_table",
             "release_date", "source"]
    with open(OUT / "vn_gdp_annual.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=acols, lineterminator="\n")
        w.writeheader()
        w.writerows(ann)
    code = f"G{last}"

    def long_rows():
        for r in rows:
            if r["span"] != "Q" and r["span"] != "Y":
                continue
            yield {"country": "VN", "indicator": "gdp", "series": f"{r['code']}_{r['price']}", "label": r["industry"],
                   "measure": r["measure"], "area": "national", "freq": "Q" if r["span"] == "Q" else "A", "date": r["date"],
                   "value": r["rate"] if r["measure"] == "yoy" else r["value"], "unit": r["unit"], "source": N.SOURCE,
                   "release": code}
        for r in ann:
            yield {"country": "VN", "indicator": "gdp_annual", "series": f"{r['table']}_{r['code']}_{r['price']}", "label": r["item"],
                   "measure": r["measure"], "area": "national", "freq": "A", "date": r["date"],
                   "value": r["rate"] if r["measure"] == "yoy" else r["value"], "unit": r["unit"], "source": N.SOURCE, "release": code}
        for r in iip:
            yield {"country": "VN", "indicator": "iip", "series": f"iip_{r['code']}", "label": f"Industrial production: {r['industry']}",
                   "measure": "yoy", "area": "national", "freq": "Q", "date": r["date"], "value": r["rate"], "unit": "%",
                   "source": N.SOURCE, "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    release = {"code": code, "label": last.replace("-", " "), "latest_quarter": last, "latest_book": latest_book,
               "table": "NSO socio-economic report tables 1-2 (GDP) and quarterly IIP; PX-Web E03.02, E03.03, E03.08, E03.09 (annual)",
               "books": len(index)}
    write_release(OUT, release, warnings, len(rows), {"long_rows": nlong, "iip_rows": len(iip), "vintage_rows": len(vint), "annual_rows": len(ann)})
    return {"updated": True, "code": code, "summary": f"{last}: {len(rows)} quarterly GDP rows, {len(ann)} annual, {len(iip)} IIP rows, {len(index)} books",
            "warnings": warnings}
