"""Philippines GDP: Philippine Statistics Authority national accounts, OpenSTAT (PXWeb, no key), as published.

All on PSA's 2018 base (constant 2018 prices; current prices), PHP million; growth rates are PSA's own (one decimal).
  - Quarterly, by industry (21 rows: 3 major sectors, 15 industries, GDP, net primary income, GNI), 2000 on:
    levels (2B/NA/QT/1SUM/0052B5BPRQ1), y/y growth (0062B5BPRQ2), % shares of GDP (0082B5BPRQ4).
  - Quarterly long series, 3 major sectors and GDP, Q1 1981 on: levels (23QNAP/PRD/0982B5BQPQ1), y/y from Q1 1982
    (0992B5BQPQ2). Used before 2000; it equals the detailed table where both have a quarter (checked).
  - Annual, by industry, 2000 on: levels (2B/NA/AN/1SUM/0052B5BPRA1), growth (0062B5BPRA2).
  - Annual long series, 3 major sectors and GDP, 1946 on: levels (23ANAP/0942B5BANA1), growth from 1947 (0952B5BANA2).
    Used before 2000; equal to the detailed table where both have a year (checked).

Calculated (asked for 2 Nov 2026; flagged calculated = y): year-to-date real growth for the current year, before PSA
publishes the full year: sum of the year's published quarterly levels at 2018 prices / the same quarters a year
earlier - 1, for GDP and the three sectors. PSA states these rates in its release text, not in its tables.

New data is detected from the folder listings' last-updated dates; tables are fetched only when one changes.
Raw responses: raw/ph/gdp_psa/<quarter>/<name>.json.gz.
"""
import csv
import gzip
import hashlib
import json

from core import psa
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "ph_gdp_psa"
DESCRIPTION = "Philippines GDP (PSA OpenSTAT, 2018 prices): quarterly and annual by industry, long series from 1946/1981"
OUT = DATA / "ph" / "gdp"
RAWDIR = RAW / "ph" / "gdp_psa"
NA = "2B/NA/"
TABLES = {
    "q_level": NA + "QT/1SUM/0052B5BPRQ1.px", "q_yoy": NA + "QT/1SUM/0062B5BPRQ2.px", "q_share": NA + "QT/1SUM/0082B5BPRQ4.px",
    "q_long_level": NA + "QT/23QNAP/PRD/0982B5BQPQ1.px", "q_long_yoy": NA + "QT/23QNAP/PRD/0992B5BQPQ2.px",
    "a_level": NA + "AN/1SUM/0052B5BPRA1.px", "a_yoy": NA + "AN/1SUM/0062B5BPRA2.px",
    "a_long_level": NA + "AN/23ANAP/0942B5BANA1.px", "a_long_yoy": NA + "AN/23ANAP/0952B5BANA2.px",
}
FOLDERS = sorted({p.rsplit("/", 1)[0] for p in TABLES.values()})
# PSA's row text (lower case, dots stripped) -> (code, label, level: 0 total, 1 major sector, 2 industry, order)
ROWS = [
    ("agriculture, forestry, and fishing", "agri", "Agriculture, forestry and fishing", 1),
    ("industry", "industry", "Industry", 1),
    ("mining and quarrying", "mining", "Mining and quarrying", 2),
    ("manufacturing", "manufacturing", "Manufacturing", 2),
    ("electricity, steam, water and waste management", "utilities", "Electricity, steam, water and waste management", 2),
    ("construction", "construction", "Construction", 2),
    ("services", "services", "Services", 1),
    ("wholesale and retail trade; repair of motor vehicles and motorcycles", "trade", "Wholesale and retail trade; repair of motor vehicles and motorcycles", 2),
    ("transportation and storage", "transport", "Transportation and storage", 2),
    ("accommodation and food service activities", "accommodation", "Accommodation and food service activities", 2),
    ("information and communication", "ict", "Information and communication", 2),
    ("financial and insurance activities", "finance", "Financial and insurance activities", 2),
    ("real estate and ownership of dwellings", "real_estate", "Real estate and ownership of dwellings", 2),
    ("professional and business services", "business", "Professional and business services", 2),
    ("public administration and defense; compulsory social activities", "public_admin", "Public administration and defense; compulsory social activities", 2),
    ("education", "education", "Education", 2),
    ("human health and social work activities", "health", "Human health and social work activities", 2),
    ("other services", "other_services", "Other services", 2),
    ("gross domestic product", "gdp", "Gross domestic product", 0),
    ("net primary income from the rest of the world", "npi", "Net primary income from the rest of the world", 0),
    ("gross national income", "gni", "Gross national income", 0),
    ("gdp share to gni", "gdp_share_gni", "GDP, % of GNI", 0),
    ("agriculture, forestry and fishing", "agri", "Agriculture, forestry and fishing", 1),   # spelling in the long series
]
CODE = {t: (c, lab, lv, i) for i, (t, c, lab, lv) in enumerate(ROWS)}
MAJOR = ("gdp", "agri", "industry", "services")
PRICE = {"At Current Prices": "current", "At Constant 2018 Prices": "constant_2018"}
QM = {"Q1": 3, "Q2": 6, "Q3": 9, "Q4": 12}


def _row(text):
    k = text.strip(". ").lower()
    if k not in CODE:
        raise CheckFailed([f"unknown industry row {text!r}"])
    return CODE[k]


def stamps():
    out = {}
    for f in FOLDERS:
        for it in psa._request(f"{psa.BASE}/{f}"):
            if it.get("type") == "t":
                out[f"{f}/{it['id']}"] = it.get("updated")
    return {k: v for k, v in out.items() if k in TABLES.values()}


def fetch(dest):
    dest.mkdir(parents=True, exist_ok=True)
    got = {}
    for name, path in TABLES.items():
        m = psa.meta(path)
        rows = psa.get(path, {}, m)
        got[name] = rows
        with gzip.open(dest / f"{name}.json.gz", "wt", encoding="utf-8") as f:
            json.dump({"path": path, "title": m.get("title"), "rows": rows}, f, ensure_ascii=False)
    return got


def load(src):
    return {p.name[:-8]: json.load(gzip.open(p, "rt"))["rows"] for p in src.glob("*.json.gz")}


def _year(y):
    return int(str(y).split("-")[-1])        # growth tables label years "2024-2025"


def build(t):
    q, a = {}, {}       # (code, price, measure, year, quarter) -> value ; (code, price, measure, year) -> value
    src_q, src_a = {}, {}

    def ind(r):
        return r.get("Industry") or r.get("Major Industries")

    for name, measure in (("q_long_level", "level"), ("q_long_yoy", "yoy"), ("q_level", "level"), ("q_yoy", "yoy"), ("q_share", "share")):
        for r in t[name]:
            if r["value"] is None:
                continue
            code = _row(ind(r))[0]
            k = (code, PRICE[r["Type of Valuation"]], measure, _year(r["Year"]), r["Period"])
            if name.startswith("q_long") and k in q:
                continue
            if not name.startswith("q_long") and k in q and src_q.get(k) == "long" and abs(q[k] - r["value"]) > (0.05 if measure != "level" else 1):
                src_q.setdefault("_diffs", []).append((k, q[k], r["value"]))
            q[k] = r["value"]
            src_q[k] = "long" if name.startswith("q_long") else "detail"
    for name, measure in (("a_long_level", "level"), ("a_long_yoy", "yoy"), ("a_level", "level"), ("a_yoy", "yoy")):
        for r in t[name]:
            if r["value"] is None:
                continue
            code = _row(ind(r))[0]
            k = (code, PRICE[r["Type of Valuation"]], measure, _year(r["Year"]))
            if not name.startswith("a_long") and k in a and src_a.get(k) == "long" and abs(a[k] - r["value"]) > (0.05 if measure != "level" else 1):
                src_a.setdefault("_diffs", []).append((k, a[k], r["value"]))
            a[k] = r["value"]
            src_a[k] = "long" if name.startswith("a_long") else "detail"

    info = {}
    for _, (c, lab, lv, i) in CODE.items():
        info.setdefault(c, (lab, lv, i))      # first spelling sets the order
    qrows = []
    for (code, price, measure, y, p), v in q.items():
        lab, lv, i = info[code]
        qrows.append({"date": f"{y}-{QM[p]:02d}-01", "period": f"{y}-{p}", "code": code, "industry": lab, "level": lv, "order": i,
                      "price": price, "measure": measure, "value": v, "unit": "PHP mn" if measure == "level" else "%",
                      "table": src_q[(code, price, measure, y, p)]})
    qrows.sort(key=lambda r: (r["date"], r["order"], r["price"], r["measure"]))
    arows = []
    for (code, price, measure, y), v in a.items():
        lab, lv, i = info[code]
        arows.append({"date": f"{y}-12-01", "year": y, "span": "Y", "code": code, "industry": lab, "level": lv, "order": i,
                      "price": price, "measure": measure, "value": v, "unit": "PHP mn" if measure == "level" else "%",
                      "calculated": "", "table": src_a[(code, price, measure, y)]})

    # Year to date (calculated): the current year's published quarters at 2018 prices against the same quarters a
    # year earlier, for a year PSA has not yet published in full.
    latest_q = max(k[3] * 10 + int(k[4][1]) for k in q if k[0] == "gdp" and k[2] == "level")
    ly, lq = divmod(latest_q, 10)
    ytd = []
    if lq < 4 and ("gdp", "constant_2018", "yoy", ly) not in a:
        qs = [f"Q{i}" for i in range(1, lq + 1)]
        for code in MAJOR:
            now_ = [q.get((code, "constant_2018", "level", ly, p)) for p in qs]
            was = [q.get((code, "constant_2018", "level", ly - 1, p)) for p in qs]
            if None in now_ or None in was:
                continue
            lab, lv, i = info[code]
            v = round((sum(now_) / sum(was) - 1) * 100, 2)
            span = {1: "Q1", 2: "H1", 3: "9M"}[lq]
            ytd.append({"date": f"{ly}-12-01", "year": ly, "span": span, "code": code, "industry": lab, "level": lv, "order": i,
                        "price": "constant_2018", "measure": "yoy", "value": v, "unit": "%", "calculated": "y",
                        "table": f"calculated from quarterly levels, {qs[0]}-{qs[-1]} {ly} on {qs[0]}-{qs[-1]} {ly - 1}"})
    arows += ytd
    arows.sort(key=lambda r: (r["year"], r["span"] != "Y", r["order"], r["price"], r["measure"]))
    return {"q": q, "a": a, "qrows": qrows, "arows": arows, "latest": (ly, lq), "ytd": ytd,
            "diffs": src_q.get("_diffs", []) + src_a.get("_diffs", [])}


def check(b, state):
    errors, warnings = [], []
    q, a = b["q"], b["a"]
    ly, lq = b["latest"]
    if b["diffs"]:
        errors.append(f"long and detailed tables disagree in {len(b['diffs'])} cells, e.g. {b['diffs'][:3]}")
    prev = state.get("latest")
    if prev and (ly * 10 + lq) < prev:
        errors.append(f"latest quarter {ly}-Q{lq} is before the last stored ({prev})")
    # every row of the detailed table, both prices, levels and growth, for the latest quarter
    for _, (code, lab, lv, i) in CODE.items():
        if code in ("gdp_share_gni", "npi"):
            continue
        for price in PRICE.values():
            for m in ("level", "yoy"):
                if (code, price, m, ly, f"Q{lq}") not in q:
                    errors.append(f"{ly}-Q{lq}: no {code} {price} {m}")
    # no gaps in real GDP y/y from Q1 1982, or annual from 1947
    for y in range(1982, ly + 1):
        for p in ("Q1", "Q2", "Q3", "Q4"):
            if (y, int(p[1])) <= (ly, lq) and ("gdp", "constant_2018", "yoy", y, p) not in q:
                errors.append(f"gap: real GDP y/y {y}-{p}")
    last_a = max(k[3] for k in a if k[0] == "gdp" and k[2] == "yoy")
    for y in range(1947, last_a + 1):
        for code in MAJOR:
            if code == "agri" and y == 1947:
                continue        # PSA's long series has no real agriculture growth for 1947
            if (code, "constant_2018", "yoy", y) not in a:
                errors.append(f"gap: annual real {code} growth {y}")
    # published growth against published levels (rounding to 0.1)
    for (code, price, m, y, p), v in q.items():
        if m != "yoy" or y < 2001:
            continue
        l1, l0 = q.get((code, price, "level", y, p)), q.get((code, price, "level", y - 1, p))
        if l1 and l0 and l0 > 0 and abs((l1 / l0 - 1) * 100 - v) > 0.15:
            warnings.append(f"{code} {price} {y}-{p}: published y/y {v} vs levels {(l1 / l0 - 1) * 100:.2f}")
    # parts sum to GDP (levels, latest quarter)
    for price in PRICE.values():
        g = q.get(("gdp", price, "level", ly, f"Q{lq}"))
        parts = sum(q.get((c, price, "level", ly, f"Q{lq}")) or 0 for c in ("agri", "industry", "services"))
        if g and abs(parts / g - 1) > 0.0005:
            errors.append(f"{price} {ly}-Q{lq}: sectors sum to {parts:,.0f}, GDP {g:,.0f}")
        sh = sum(q.get((c, price, "share", ly, f"Q{lq}")) or 0 for c in ("agri", "industry", "services"))
        if abs(sh - 100) > 0.2:
            errors.append(f"{price} {ly}-Q{lq}: sector shares sum to {sh:.1f}")
    # annual = sum of quarters, where all four are published
    for (code, price, m, y), v in a.items():
        if m != "level" or y < 2000 or code not in MAJOR:
            continue
        qs = [q.get((code, price, "level", y, f"Q{i}")) for i in range(1, 5)]
        if None not in qs and abs(sum(qs) / v - 1) > 0.0005:
            errors.append(f"{code} {price} {y}: quarters sum to {sum(qs):,.0f}, annual {v:,.0f}")
    for (code, price, m, y, p), v in q.items():
        if m == "yoy" and code in MAJOR and not -40 < v < (60 if price.startswith("constant") else 100):
            errors.append(f"{code} {price} {y}-{p}: y/y {v} out of range")
    return errors, warnings


def _write_csv(path, rows, cols):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def update(from_dir=None, force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    if from_dir:
        from pathlib import Path
        t, st = load(Path(from_dir)), state.get("stamps", {})
    else:
        st = stamps()
        if st == state.get("stamps") and not force:
            return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
        t = fetch(RAWDIR / "_incoming")
    b = build(t)
    errors, warnings = check(b, state)
    if errors:
        raise CheckFailed(errors)
    ly, lq = b["latest"]
    code, label = f"G{ly}Q{lq}", f"Q{lq} {ly}"
    if not from_dir:
        dest = RAWDIR / f"{ly}Q{lq}"
        if dest.exists():
            for p in dest.glob("*"):
                p.unlink()
            dest.rmdir()
        (RAWDIR / "_incoming").rename(dest)
    qcols = ["date", "period", "code", "industry", "level", "order", "price", "measure", "value", "unit", "table"]
    acols = ["date", "year", "span", "code", "industry", "level", "order", "price", "measure", "value", "unit", "calculated", "table"]
    _write_csv(OUT / "ph_gdp.csv", b["qrows"], qcols)
    _write_csv(OUT / "ph_gdp_annual.csv", b["arows"], acols)
    # dashboard file: growth and shares for GDP and the three sectors, every quarter; annual growth, all of it
    dash = [{**r, "freq": "Q", "span": "Q", "calculated": ""} for r in b["qrows"] if r["code"] in MAJOR and r["measure"] in ("yoy", "share")]
    dash += [{**r, "freq": "A", "period": str(r["year"]) if r["span"] == "Y" else f"{r['year']}-{r['span']}"}
             for r in b["arows"] if r["code"] in MAJOR and r["measure"] == "yoy"]
    _write_csv(OUT / "ph_gdp_dash.csv", dash, ["freq", "date", "period", "span", "code", "industry", "price", "measure", "value", "calculated"])

    def long_rows():
        for r in b["qrows"]:
            yield {"country": "PH", "indicator": "gdp", "series": f"{r['code']}_{r['price']}_{r['measure']}",
                   "label": f"{r['industry']}, {r['price'].replace('_', ' ')}, {r['measure']}", "measure": r["measure"],
                   "area": "national", "freq": "Q", "date": r["date"], "value": r["value"], "unit": r["unit"],
                   "source": "PSA, National Accounts of the Philippines (OpenSTAT)", "release": code}
        for r in b["arows"]:
            yield {"country": "PH", "indicator": "gdp_annual", "series": f"{r['code']}_{r['price']}_{r['measure']}_{r['span']}",
                   "label": f"{r['industry']}, {r['price'].replace('_', ' ')}, {r['measure']}" + (" (calculated)" if r["calculated"] else ""),
                   "measure": r["measure"], "area": "national", "freq": "A", "date": r["date"], "value": r["value"], "unit": r["unit"],
                   "source": "PSA, National Accounts of the Philippines (OpenSTAT)" + ("; calculated" if r["calculated"] else ""),
                   "release": code}

    nlong = write_long(long_rows(), OUT / "long.csv")
    fingerprint = hashlib.sha256(json.dumps(b["qrows"][-200:], sort_keys=True).encode()).hexdigest()[:16]
    release = {"code": code, "label": label, "source": NAME}
    write_release(OUT, release, warnings, len(b["qrows"]),
                  {"fingerprint": fingerprint, "long_rows": nlong, "stamps": st, "latest": ly * 10 + lq,
                   "ytd": [{k: r[k] for k in ("code", "span", "value")} for r in b["ytd"]]})
    return {"updated": True, "code": code, "summary": f"{label}: {len(b['qrows'])} quarterly rows, {len(b['arows'])} annual",
            "warnings": warnings}
