"""Thailand GDP by industry, quarterly and annual: NESDC (Office of the National Economic and Social Development
Council) Quarterly Gross Domestic Product, statistical tables (Excel), as published.

- Table 3: GDP at current market prices by industry (millions of baht), original (not seasonally adjusted).
- Table 4: GDP, chain volume measures, reference year 2002 (millions of baht), original.
- Table 4.1: GDP, chain volume measures, y/y growth (%), as NESDC publishes it to one decimal.
Rows: 24 industries in NESDC's grouping (agriculture; non-agriculture = industrial B-E plus services F-U, NESDC
counts construction in services), GDP; Table 3 also net primary income from abroad and GNI. Quarters from Q1 1993
(y/y from Q1 1994), full years from 1993. NESDC marks provisional years (p1) and revised quarters (r).

Calculated here (asked for 2 Nov 2026), flagged calculated = y:
- nominal y/y: single quarters, current-price level / level a year earlier - 1, every industry;
- year to date for the latest year while it has no annual figure: chain volume levels summed over the quarters
  published so far, on the same quarters a year earlier (span 6M for Q1-Q2, 9M for Q1-Q3; Q1 is the quarter itself).
  The checks confirm NESDC's annual chain volume level is the sum of its quarters, so this is NESDC's own annual method.

Access: www.nesdc.go.th sets a cookie on a first 302 (keep a cookie jar). The QGDP page holds a JSON listing of
downloads; files are served by `/en/?p=<post>&ddl=<attachment>`. NESDC's release calendar ("Forthcoming Releases")
gives GDP at 09:30 Bangkok (10:30 SGT): Q3 2026 on 16 Nov 2026, Q4 2026 on 15 Feb 2027.
"""
import csv
import gzip
import hashlib
import http.cookiejar
import io
import json
import re
import time
import urllib.error
import urllib.request

from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "th_gdp_nesdc"
DESCRIPTION = "Thailand GDP by industry, quarterly and annual (NESDC QGDP tables 3, 4, 4.1)"
OUT = DATA / "th" / "gdp"
RAWDIR = RAW / "th" / "gdp_nesdc"
PAGE = "https://www.nesdc.go.th/en/info/quarterly-gross-domestic-product-qgdp-en/"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en;q=0.9"}
SHEETS = {"Table 3": "current", "Table 4": "cvm_2002", "Table 4.1": "cvm_2002_yoy"}
SRC = "NESDC, Quarterly Gross Domestic Product (statistical tables)"

# NESDC's column number (n) in the table headers -> code, ISIC section, label, level (1 = top group)
ROWS = [
    (1, "agri", "A", "Agriculture", 1), (2, "agri_ffs", "A", "Agriculture, forestry and fishing", 2),
    (3, "nonagri", "B-U", "Non-agriculture", 1), (4, "industrial", "B-E", "Industrial", 2),
    (5, "mining", "B", "Mining and quarrying", 3), (6, "manufacturing", "C", "Manufacturing", 3),
    (7, "electricity", "D", "Electricity, gas, steam and air conditioning supply", 3),
    (8, "water", "E", "Water supply; sewerage, waste management and remediation", 3),
    (9, "services", "F-U", "Services", 2), (10, "construction", "F", "Construction", 3),
    (11, "trade", "G", "Wholesale and retail trade; repair of motor vehicles", 3),
    (12, "transport", "H", "Transportation and storage", 3), (13, "accommodation", "I", "Accommodation and food service", 3),
    (14, "ict", "J", "Information and communication", 3), (15, "finance", "K", "Financial and insurance", 3),
    (16, "real_estate", "L", "Real estate", 3), (17, "professional", "M", "Professional, scientific and technical", 3),
    (18, "admin", "N", "Administrative and support services", 3),
    (19, "public_admin", "O", "Public administration and defence; compulsory social security", 3),
    (20, "education", "P", "Education", 3), (21, "health", "Q", "Human health and social work", 3),
    (22, "arts", "R", "Arts, entertainment and recreation", 3), (23, "other_services", "S", "Other service activities", 3),
    (24, "households", "T", "Activities of households as employers", 3),
]
BY_N = {n: (c, i, l, lv) for n, c, i, l, lv in ROWS}
EXTRA = {"total": ("", "Gross domestic product", 0), "nfi": ("", "Net primary income from the rest of the world", 0),
         "gni": ("", "Gross national income", 0)}
QMON = {1: 3, 2: 6, 3: 9, 4: 12}
YTD_SPAN = {1: "Q", 2: "6M", 3: "9M"}

JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(JAR))


def get(url, timeout=180, tries=4):
    for i in range(tries):
        try:
            with OPENER.open(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read(), dict(r.headers), r.url
        except Exception:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def listing():
    """Every download on the QGDP page: [{name, post, ddl, url, last_updated}], newest attachment first."""
    body, _, _ = get(PAGE)
    t = body.decode("utf-8", "replace")
    t = t.replace("\\\\\\/", "/").replace("\\/", "/").replace('\\\\\\"', '"').replace('\\"', '"')
    items = {}
    for m in re.finditer(r'(https://www\.nesdc\.go\.th/(?:en/)?\?p=(\d+)&(?:amp;)?ddl=(\d+))', t):
        names = re.findall(r'"name":\s*"([^"]{2,200})"', t[max(0, m.start() - 700):m.start()])
        lu = re.search(r'"last_updated":\s*"([^"]*)"', t[m.end():m.end() + 900])
        items.setdefault(m.group(3), {"name": names[-1] if names else "", "post": m.group(2), "ddl": m.group(3),
                                      "url": m.group(1).replace("&amp;", "&"), "last_updated": lu.group(1) if lu else ""})
    return sorted(items.values(), key=lambda i: -int(i["ddl"]))


def pick(items):
    for pat in (r"^Statistical Tables \(Excel", r"^All tables QGDP\d-\d{4}"):
        hit = [i for i in items if re.search(pat, i["name"], re.I)]
        if hit:
            return hit[0]
    raise CheckFailed([f"NESDC QGDP page: no statistical tables (Excel) download among {len(items)} links"])


def read_book(data):
    """Cell values of the tables used, {sheet: [[...], ...]} (strings and numbers as stored)."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = {}
    for s in SHEETS:
        if s not in wb.sheetnames:
            raise CheckFailed([f"workbook: sheet {s!r} missing ({wb.sheetnames[:12]}...)"])
        out[s] = [[c for c in r] for r in wb[s].iter_rows(values_only=True)]
    return out


def num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    v = str(v).replace(",", "").strip()
    try:
        return float(v)
    except ValueError:
        return None


def columns(header, sheet):
    """Header row -> {column index: code}, by NESDC's (n) column numbers; GDP by its label."""
    cols = {}
    for j, h in enumerate(header):
        if h is None:
            continue
        s = re.sub(r"\s+", " ", str(h)).strip()
        m = re.search(r"\((\d+)\)\s*$", s)
        low = s.lower()
        if "residual" in low or "sum up" in low:
            continue
        if low.startswith("gross domestic product"):
            cols[j] = "total"
        elif "net factor income" in low or "net primary income" in low:
            cols[j] = "nfi"
        elif low.startswith("gross national income"):
            cols[j] = "gni"
        elif m and int(m.group(1)) in BY_N:
            cols[j] = BY_N[int(m.group(1))][0]
    return cols


def parse(book):
    """-> {(sheet, code, period): (value, status)}; period 'YYYY' (annual) or 'YYYY-Qn'."""
    out, errors = {}, []
    for s, rows in book.items():
        hi = next((i for i, r in enumerate(rows[:12]) if r and any(isinstance(c, str) and "Agriculture (1)" in c for c in r)), None)
        if hi is None:
            errors.append(f"{s}: header row not found")
            continue
        cols = columns(rows[hi], s)
        need = {c for _, c, *_ in ROWS} | {"total"}
        if not need <= set(cols.values()):
            errors.append(f"{s}: columns missing {sorted(need - set(cols.values()))}")
        year = None
        for r in rows[hi + 1:]:
            if not r or r[0] is None:
                continue
            lab = str(r[0]).strip()
            my = re.fullmatch(r"(\d{4})(\.0)?\s*([a-z]\d?)?", lab)
            mq = re.fullmatch(r"Q([1-4])\s*([a-z]\d?)?", lab)
            if my:
                year, period, st = int(my.group(1)), my.group(1), my.group(3) or ""
            elif mq and year:
                period, st = f"{year}-Q{mq.group(1)}", mq.group(2) or ""
            else:
                continue
            for j, code in cols.items():
                v = num(r[j]) if j < len(r) else None
                if v is not None:
                    out[(s, code, period)] = (v, st)
    if errors:
        raise CheckFailed(errors)
    return out


def qdate(period):
    if "-Q" in period:
        y, q = period.split("-Q")
        return f"{y}-{QMON[int(q)]:02d}-01"
    return f"{period}-12-01"


def prev_year(period):
    return f"{int(period[:4]) - 1}{period[4:]}"


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    RAWDIR.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    item = pick(listing())
    if state.get("ddl") == item["ddl"] and not force and (OUT / "th_gdp.csv").exists():
        return {"updated": False, "code": state.get("code"), "summary": f"no change ({state.get('label')}, NESDC file {item['ddl']})"}
    data, headers, final = get(item["url"])
    if data[:2] != b"PK":
        raise CheckFailed([f"{item['url']}: not an Excel file ({headers.get('Content-Type')}, {len(data)} bytes)"])
    book = read_book(data)
    P = parse(book)

    errors, warnings = [], []
    real = {p: v for (s, c, p), (v, _) in P.items() if s == "Table 4.1" and c == "total" and "-Q" in p}
    qs = sorted(real, key=lambda p: (int(p[:4]), p[-1]))
    if not qs:
        raise CheckFailed(["Table 4.1: no quarterly GDP growth"])
    latest = qs[-1]
    ly, lq = int(latest[:4]), int(latest[-1])
    # every quarter from Q1 1994 to the latest, GDP growth present
    want = [f"{y}-Q{q}" for y in range(1994, ly + 1) for q in range(1, 5) if (y, q) <= (ly, lq)]
    gaps = [p for p in want if p not in real]
    if gaps:
        errors.append(f"Table 4.1 GDP y/y gaps: {gaps[:8]}")
    for s in SHEETS:
        miss = [c for _, c, *_ in ROWS if (s, c, latest) not in P] + ([] if (s, "total", latest) in P else ["total"])
        if miss:
            errors.append(f"{s} {latest}: no figure for {miss}")
    last_year = max(int(p) for (s, c, p) in P if s == "Table 4.1" and c == "total" and "-Q" not in p)
    # published y/y vs the chain volume levels (NESDC rounds to one decimal)
    worst = []
    for (s, c, p), (v, _) in P.items():
        if s != "Table 4.1" or p[:4] < "1994":
            continue
        a, b = P.get(("Table 4", c, p)), P.get(("Table 4", c, prev_year(p)))
        if a and b and b[0]:
            d = abs((a[0] / b[0] - 1) * 100 - v)
            if d > 0.151:
                worst.append((round(d, 2), c, p, v))
    if worst:
        worst.sort(reverse=True)
        (errors if len(worst) > 20 else warnings).append(f"published y/y vs CVM levels off by >0.15pp in {len(worst)} cases: {worst[:6]}")
    # current prices are additive: agriculture + non-agriculture = GDP; industrial + services = non-agriculture
    for (s, c, p), (v, _) in P.items():
        if s == "Table 3" and c == "total":
            parts = [P.get((s, "agri", p)), P.get((s, "nonagri", p))]
            if all(parts) and abs(sum(x[0] for x in parts) - v) > max(2, 1e-4 * v):
                errors.append(f"Table 3 {p}: agriculture + non-agriculture {sum(x[0] for x in parts):.0f} vs GDP {v:.0f}")
            na = P.get((s, "nonagri", p)); parts = [P.get((s, "industrial", p)), P.get((s, "services", p))]
            if na and all(parts) and abs(sum(x[0] for x in parts) - na[0]) > max(2, 1e-4 * na[0]):
                warnings.append(f"Table 3 {p}: industrial + services vs non-agriculture differ")
    # annual = sum of the four quarters (current prices and chain volume): confirms the year-to-date method
    for s in ("Table 3", "Table 4"):
        for y in range(1993, last_year + 1):
            a = P.get((s, "total", str(y)))
            qv = [P.get((s, "total", f"{y}-Q{q}")) for q in range(1, 5)]
            if a and all(qv) and abs(sum(x[0] for x in qv) - a[0]) > max(5, 2e-5 * a[0]):
                warnings.append(f"{s} {y}: annual {a[0]:.0f} vs sum of quarters {sum(x[0] for x in qv):.0f}")
    for (s, c, p), (v, _) in P.items():
        if s == "Table 4.1" and not -60 < v < 150:
            errors.append(f"Table 4.1 {c} {p}: {v} out of range")
    if errors:
        raise CheckFailed(errors)

    meta = {c: (i, l, lv) for _, c, i, l, lv in ROWS}
    meta.update(EXTRA)
    code = f"G{latest}"
    label = f"Q{lq} {ly}"
    rows = []

    def add(period, c, price, measure, value, status, calc=""):
        i, l, lv = meta[c]
        span = "Q" if "-Q" in period else ("Y" if len(period) == 4 else period.split("-")[1])
        rows.append({"date": qdate(period) if span in ("Q", "Y") else f"{period[:4]}-{QMON[int(YTD_Q[span])]:02d}-01",
                     "period": period, "span": span, "code": c, "isic": i, "industry": l, "level": lv, "price": price,
                     "measure": measure, "value": round(value, 4) if measure == "level" else "",
                     "rate": round(value, 4) if measure == "yoy" else "", "status": status, "calculated": calc, "release": code})

    for (s, c, p), (v, st) in sorted(P.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0])):
        if s == "Table 3":
            add(p, c, "current", "level", v, st)
        elif s == "Table 4":
            add(p, c, "cvm_2002", "level", v, st)
        else:
            add(p, c, "cvm_2002", "yoy", v, st)
    # calculated: nominal y/y, single quarters
    for (s, c, p), (v, st) in P.items():
        if s == "Table 3" and "-Q" in p:
            b = P.get((s, c, prev_year(p)))
            if b and b[0] > 0 and v > 0:
                add(p, c, "current", "yoy", (v / b[0] - 1) * 100, st, "y")
    # calculated: real year to date for the latest year while it has no annual figure
    if ly > last_year and lq < 4:
        span = YTD_SPAN[lq]
        if lq > 1:
            for c in list(meta):
                cur = [P.get(("Table 4", c, f"{ly}-Q{q}")) for q in range(1, lq + 1)]
                pre = [P.get(("Table 4", c, f"{ly - 1}-Q{q}")) for q in range(1, lq + 1)]
                if all(cur) and all(pre):
                    add(f"{ly}-{span}", c, "cvm_2002", "yoy", (sum(x[0] for x in cur) / sum(x[0] for x in pre) - 1) * 100,
                        "", "y")

    blob = json.dumps(book, ensure_ascii=False, default=str).encode()
    fp = hashlib.sha256(blob).hexdigest()[:16]
    with gzip.open(RAWDIR / f"{latest}_{item['ddl']}.json.gz", "wb", compresslevel=9) as fh:
        fh.write(blob)
    cols = ["date", "period", "span", "code", "isic", "industry", "level", "price", "measure", "value", "rate", "status",
            "calculated", "release"]
    with open(OUT / "th_gdp.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    # dashboard file: growth rows only (published real y/y, calculated nominal y/y and year to date)
    with open(OUT / "th_gdp_dash.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(r for r in rows if r["measure"] == "yoy")
    nlong = write_long(({"country": "TH", "indicator": "gdp", "series": f"{r['code']}_{r['price']}_{r['measure']}_{r['span']}",
                         "label": f"{r['industry']}, {'current prices' if r['price'] == 'current' else 'chain volume (2002)'}"
                                  f"{', y/y' if r['measure'] == 'yoy' else ''}{' (calculated)' if r['calculated'] else ''}",
                         "measure": r["measure"], "area": "national", "freq": "Q" if r["span"] == "Q" else "A" if r["span"] == "Y" else r["span"],
                         "date": r["date"], "value": r["value"] if r["measure"] == "level" else r["rate"],
                         "unit": "THB mn" if r["measure"] == "level" else "%", "source": SRC, "release": code} for r in rows),
                       OUT / "long.csv")
    release = {"code": code, "label": label, "latest_quarter": latest, "latest_year": last_year, "file": item["name"],
               "ddl": item["ddl"], "url": item["url"], "nesdc_last_updated": item["last_updated"],
               "table": "NESDC QGDP statistical tables 3, 4, 4.1"}
    write_release(OUT, release, warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    st = read_json(OUT / "release.json", {})
    st["ddl"] = item["ddl"]
    (OUT / "release.json").write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n")
    return {"updated": True, "code": code, "summary": f"{label}: GDP {real[latest]:+.1f}% y/y; years to {last_year}; {len(rows)} rows",
            "warnings": warnings}


YTD_Q = {"Q": 1, "6M": 2, "9M": 3}
