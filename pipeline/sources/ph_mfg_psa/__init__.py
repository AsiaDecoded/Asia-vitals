"""Philippines manufacturing: PSA OpenSTAT (PXWeb, no key), as published, plus two calculated measures by division.

Published:
  - Volume of Production Index (VoPI), MISSI, 2018 = 100: index and y/y by PSIC 2009 division and group (60 rows),
    monthly from Jan 2018 (y/y from Jan 2019) (2G/MNFG/MISSI/2018/0032G4CMPO2). Chained Paasche-type index, weights
    updated annually from the ASPBI (PSA technical notes).
  - Backcast VoPI on the same 2018 base, total manufacturing and 11 divisions, Jan 2001 - Dec 2017 (y/y from Jan 2002)
    (2G/MNFG/MISSI/BAC/0012G4CMPO1). PSA publishes no y/y for 2018 in either table, so 2018 is a gap.
  - Average capacity utilisation rate, %, total and 22 divisions, monthly from Jan 2018 (2G/MNFG/MISSI/2018/0012G4CMCU2).
  - Gross value added in manufacturing by industry (22 industries + total), quarterly from 2000, PHP million at current
    and constant 2018 prices, y/y growth, % share of manufacturing (2B/NA/QT/10MFG/0462…Q1, 0472…Q2, 0492…Q4).
  - Manufacturing and industry as % of GDP, quarterly: read from data/ph/gdp/ph_gdp.csv (ph_gdp_psa), not refetched.

Calculated (asked for 3 Nov 2026; flagged in the outputs):
  - m3: plain average of the latest three published monthly y/y rates (3mma), per division.
  - ytd: calendar year to date, sum of the year's published monthly indices to the latest month / the same months a year
    earlier - 1, per division.

New data is detected from the folder listings' last-updated dates. Raw responses: raw/ph/mfg_psa/<month>/<name>.json.gz.
"""
import csv
import gzip
import hashlib
import json
import re

from core import psa
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "ph_mfg_psa"
DESCRIPTION = "Philippines manufacturing (PSA): MISSI volume of production index and capacity utilisation, GVA by industry"
OUT = DATA / "ph" / "mfg"
RAWDIR = RAW / "ph" / "mfg_psa"
GDP_CSV = DATA / "ph" / "gdp" / "ph_gdp.csv"
TABLES = {
    "vopi": "2G/MNFG/MISSI/2018/0032G4CMPO2.px",
    "vopi_back": "2G/MNFG/MISSI/BAC/0012G4CMPO1.px",
    "capu": "2G/MNFG/MISSI/2018/0012G4CMCU2.px",
    "gva_level": "2B/NA/QT/10MFG/0462B5BMFQ1.px",
    "gva_yoy": "2B/NA/QT/10MFG/0472B5BMFQ2.px",
    "gva_share": "2B/NA/QT/10MFG/0492B5BMFQ4.px",
}
FOLDERS = sorted({p.rsplit("/", 1)[0] for p in TABLES.values()})
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
MON = {m: i + 1 for i, m in enumerate(MONTHS)}
PSA_BLANKS = {"2022-06"}   # months PSA's table leaves blank for total y/y (index 92.22 -> 92.18); not filled here
QM = {"Q1": 3, "Q2": 6, "Q3": 9, "Q4": 12}
PRICE = {"At Current Prices": "current", "At Constant 2018 Prices": "constant_2018"}
# GVA industry names (PSA national accounts) -> PSIC code used in the MISSI tables
GVA_CODE = {
    "manufacture of food products": "C10", "manufacture of beverages": "C11", "manufacture of tobacco products": "C12",
    "manufacture of textiles": "C13", "manufacture of wearing apparel": "C14",
    "manufacture of leather and related products, including footwear": "C15",
    "manufacture of wood, bamboo, cane, rattan articles and related products": "C16",
    "manufacture of paper and paper products": "C17", "printing and reproduction of recorded media": "C18",
    "manufacture of coke and refined petroleum products": "C19", "manufacture of chemical and chemical products": "C20",
    "manufacture of basic pharmaceutical products and pharmaceutical preparations": "C21",
    "manufacture of rubber and plastic products": "C22", "manufacture of other non-metallic mineral products": "C23",
    "manufacture of basic metals": "C24", "manufacture of fabricated metal products, except machinery and equipment": "C25",
    "manufacture of computer, electronic and optical products": "C26", "manufacture of electrical equipment": "C27",
    "manufacture of machinery and equipment except electrical": "C28", "manufacture of transport equipment": "C29-C30",
    "manufacture of furniture": "C31", "other manufacturing": "C32", "gross value added in manufacturing": "C",
}


def _code(text):
    """'.C29, C30 Manufacture of …' -> ('C29-C30', 1, 'Manufacture of …'); 'C MANUFACTURING' -> ('C', 0, 'Manufacturing')."""
    lvl = len(text) - len(text.lstrip("."))
    t = text.strip(". ")
    m = re.match(r"^(C\d*(?:\s*(?:,|to|-)\s*C\d+)?)\s+(.*)$", t)
    if not m:
        raise CheckFailed([f"no PSIC code in {text!r}"])
    code = re.sub(r"\s*(?:,|to|-)\s*", "-", m.group(1))
    name = m.group(2)
    if code == "C":
        name, lvl = "Manufacturing", 0
    return code, lvl, name


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
    return int(str(y).split("-")[-1])


def build(t):
    # VoPI: monthly index and y/y, 2018 base, then the backcast where the 2018-base table has nothing.
    names, order = {}, {}
    vopi = {}          # (code, date) -> {index, yoy, base}
    for name, base in (("vopi", "2018"), ("vopi_back", "backcast")):
        for r in t[name]:
            if r["value"] is None or r["Month"] not in MON:
                continue
            grp = r.get("Industry Group/Division") or r.get("PSIC/Industry")
            code, lvl, nm = _code(grp)
            if name == "vopi":
                names.setdefault(code, (nm, lvl))
                order.setdefault(code, len(order))
            date = f"{r['Year']}-{MON[r['Month']]:02d}-01"
            rec = vopi.setdefault((code, date), {"base": base})
            if rec["base"] != base:
                continue                          # the 2018-base table wins where both have a month
            rec["index" if r["Item"] == "Index" else "yoy"] = r["value"]
    vrows = []
    for (code, date), v in vopi.items():
        nm, lvl = names.get(code, (code, 1))
        vrows.append({"date": date, "code": code, "name": nm, "level": lvl, "order": order.get(code, 99), "index": v.get("index"),
                      "yoy": v.get("yoy"), "base": v["base"]})
    vrows.sort(key=lambda r: (r["date"], r["order"]))
    latest = max(r["date"] for r in vrows if r["code"] == "C" and r["yoy"] is not None)

    # capacity utilisation, by division name -> code
    name_code = {nm.lower(): c for c, (nm, lvl) in names.items() if lvl <= 1}
    name_code["manufacturing"] = "C"
    name_code["manufacture of transport equipment"] = "C29-C30"
    name_code["other manufacturing and repair and installation of machinery and equipment"] = "C32-C33"
    crows = []
    for r in t["capu"]:
        if r["value"] is None or r["Month"] not in MON:
            continue
        k = r["Sector"].strip(". ").lower()
        if k not in name_code:
            raise CheckFailed([f"capacity utilisation: unknown sector {r['Sector']!r}"])
        code = name_code[k]
        crows.append({"date": f"{r['Year']}-{MON[r['Month']]:02d}-01", "code": code, "name": names.get(code, ("Manufacturing", 0))[0],
                      "rate": r["value"]})
    crows.sort(key=lambda r: (r["date"], order.get(r["code"], 99)))

    # GVA by industry, quarterly
    g = {}
    for name, measure in (("gva_level", "level"), ("gva_yoy", "yoy"), ("gva_share", "share")):
        for r in t[name]:
            if r["value"] is None:
                continue
            k = r["Industry"].strip(". ").lower()
            if k not in GVA_CODE:
                raise CheckFailed([f"GVA: unknown industry {r['Industry']!r}"])
            g[(GVA_CODE[k], r["Industry"].strip(". "), PRICE[r["Type of Valuation"]], measure, _year(r["Year"]), r["Period"])] = r["value"]
    grows = [{"date": f"{y}-{QM[p]:02d}-01", "period": f"{y}-{p}", "code": c, "industry": "Manufacturing" if c == "C" else ind,
              "price": pr, "measure": m, "value": v, "unit": "PHP mn" if m == "level" else "%"}
             for (c, ind, pr, m, y, p), v in g.items()]
    # manufacturing and industry as % of GDP, and manufacturing GVA y/y as in the GDP tables (ph_gdp_psa's output)
    if not GDP_CSV.exists():
        raise CheckFailed([f"{GDP_CSV} missing: ph_gdp_psa must run first"])
    for r in csv.DictReader(open(GDP_CSV, encoding="utf-8")):
        if r["code"] in ("manufacturing", "industry") and r["measure"] == "share":
            grows.append({"date": r["date"], "period": r["period"], "code": "C" if r["code"] == "manufacturing" else "industry",
                          "industry": r["industry"], "price": r["price"], "measure": "share_gdp", "value": float(r["value"]), "unit": "%"})
    grows.sort(key=lambda r: (r["date"], r["code"], r["price"], r["measure"]))

    # by division, latest month: published y/y for the latest and prior month; 3mma and YTD calculated
    ly, lm = int(latest[:4]), int(latest[5:7])
    divs = []
    for code, (nm, lvl) in names.items():
        if lvl > 1:
            continue
        s = {r["date"]: r for r in vrows if r["code"] == code}
        last3 = [s.get(f"{ly if lm - k > 0 else ly - 1}-{(lm - k - 1) % 12 + 1:02d}-01", {}).get("yoy") for k in range(3)]
        cur = [s.get(f"{ly}-{m:02d}-01", {}).get("index") for m in range(1, lm + 1)]
        prev = [s.get(f"{ly - 1}-{m:02d}-01", {}).get("index") for m in range(1, lm + 1)]
        p1 = s.get(f"{ly if lm > 1 else ly - 1}-{(lm - 2) % 12 + 1:02d}-01", {}).get("yoy")
        divs.append({"date": latest, "code": code, "name": nm, "level": lvl, "order": order[code],
                     "yoy": last3[0], "yoy_prev": p1,
                     "m3": round(sum(last3) / 3, 2) if None not in last3 else None,
                     "ytd": round((sum(cur) / sum(prev) - 1) * 100, 2) if None not in cur + prev and sum(prev) > 0 else None,
                     "ytd_months": f"Jan-{MONTHS[lm - 1][:3]} {ly}"})
    divs.sort(key=lambda r: r["order"])
    return {"vopi": vrows, "capu": crows, "gva": grows, "divs": divs, "latest": latest, "g": g, "names": names}


def check(b, state):
    errors, warnings = [], []
    v, latest = b["vopi"], b["latest"]
    if state.get("latest") and latest < state["latest"]:
        errors.append(f"latest month {latest} before the last stored ({state['latest']})")
    divs = [c for c, (nm, lvl) in b["names"].items() if lvl == 1]
    if len(divs) != 22:
        errors.append(f"{len(divs)} divisions in the VoPI table, expected 22")
    have = {(r["code"], r["date"]) for r in v if r["yoy"] is not None and r["index"] is not None}
    for c in ["C"] + divs:
        if (c, latest) not in have:
            errors.append(f"{latest}: no VoPI index and y/y for {c}")
    # no gaps in total y/y, Jan 2002 - Dec 2017 (backcast) and Jan 2019 on (2018 base)
    yy = {r["date"] for r in v if r["code"] == "C" and r["yoy"] is not None}
    y, m = 2002, 1
    while f"{y}-{m:02d}-01" <= latest:
        if y != 2018 and f"{y}-{m:02d}-01" not in yy:
            if f"{y}-{m:02d}" in PSA_BLANKS:
                warnings.append(f"total VoPI y/y {y}-{m:02d} left blank by PSA (known)")
            else:
                errors.append(f"gap: total VoPI y/y {y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    # published y/y against the published index, 2018 base, 2020 on (two-decimal indices)
    idx = {(r["code"], r["date"]): r["index"] for r in v if r["index"] is not None}
    bad = 0
    for r in v:
        if r["base"] != "2018" or r["yoy"] is None or r["date"] < "2020-01-01":
            continue
        a, p = idx.get((r["code"], r["date"])), idx.get((r["code"], f"{int(r['date'][:4]) - 1}{r['date'][4:]}"))
        if a and p and abs((a / p - 1) * 100 - r["yoy"]) > 0.15:
            bad += 1
            if bad <= 10:
                warnings.append(f"VoPI {r['code']} {r['date']}: published y/y {r['yoy']} vs index {(a / p - 1) * 100:.2f}")
    if bad > 10:
        warnings.append(f"... {bad} VoPI y/y vs index differences in all")
    # capacity utilisation
    if not any(r["code"] == "C" and r["date"] == latest for r in b["capu"]):
        warnings.append(f"capacity utilisation: no total for {latest}")
    if any(not 0 < r["rate"] <= 100 for r in b["capu"]):
        errors.append("capacity utilisation outside 0-100")
    # GVA: industries sum to the total, shares to 100, latest quarter
    g = b["g"]
    lq = max((y, p) for (c, _, pr, m, y, p) in g if c == "C" and m == "level")
    for pr in PRICE.values():
        tot = sum(v for (c, _, prc, m, y, p), v in g.items() if c == "C" and prc == pr and m == "level" and (y, p) == lq)
        parts = sum(v for (c, _, prc, m, y, p), v in g.items() if c != "C" and prc == pr and m == "level" and (y, p) == lq)
        if not tot or abs(parts / tot - 1) > 0.0005:
            errors.append(f"GVA {pr} {lq}: industries sum to {parts:,.0f}, total {tot:,.0f}")
        sh = sum(v for (c, _, prc, m, y, p), v in g.items() if c != "C" and prc == pr and m == "share" and (y, p) == lq)
        if abs(sh - 100) > 0.5:
            errors.append(f"GVA {pr} {lq}: industry shares sum to {sh:.1f}")
    # GVA total = manufacturing in the GDP tables
    gdp = {(r["period"], r["price"]): float(r["value"]) for r in csv.DictReader(open(GDP_CSV, encoding="utf-8"))
           if r["code"] == "manufacturing" and r["measure"] == "level"}
    for (c, _, pr, m, y, p), val in g.items():
        if c == "C" and m == "level" and (f"{y}-{p}", pr) in gdp and abs(gdp[(f"{y}-{p}", pr)] - val) > 1:
            errors.append(f"GVA manufacturing {y}-{p} {pr}: {val:,.0f} vs GDP table {gdp[(f'{y}-{p}', pr)]:,.0f}")
            break
    if not any(r["measure"] == "share_gdp" for r in b["gva"]):
        errors.append("no manufacturing share of GDP from ph_gdp.csv")
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
    latest = b["latest"]
    code, label = f"M{latest[:7]}", f"{MONTHS[int(latest[5:7]) - 1][:3]} {latest[:4]}"
    if not from_dir:
        dest = RAWDIR / latest[:7]
        if dest.exists():
            for p in dest.glob("*"):
                p.unlink()
            dest.rmdir()
        (RAWDIR / "_incoming").rename(dest)
    _write_csv(OUT / "ph_vopi.csv", b["vopi"], ["date", "code", "name", "level", "order", "index", "yoy", "base"])
    # page file: total and the 22 divisions only (groups stay in ph_vopi.csv)
    _write_csv(OUT / "ph_vopi_dash.csv", [r for r in b["vopi"] if r["level"] <= 1], ["date", "code", "name", "level", "order", "yoy", "base"])
    _write_csv(OUT / "ph_vopi_div.csv", b["divs"], ["date", "code", "name", "level", "order", "yoy", "yoy_prev", "m3", "ytd", "ytd_months"])
    _write_csv(OUT / "ph_capu.csv", b["capu"], ["date", "code", "name", "rate"])
    _write_csv(OUT / "ph_mfg_gva.csv", b["gva"], ["date", "period", "code", "industry", "price", "measure", "value", "unit"])
    SRC = "PSA, Monthly Integrated Survey of Selected Industries (OpenSTAT)"

    def long_rows():
        for r in b["vopi"]:
            for k, meas in (("index", "index"), ("yoy", "yoy")):
                yield {"country": "PH", "indicator": "vopi", "series": f"{r['code']}_{k}", "label": f"VoPI, {r['name']}, {meas}",
                       "measure": meas, "area": "national", "freq": "M", "date": r["date"], "value": r[k],
                       "unit": "2018=100" if k == "index" else "%", "source": SRC + (" (backcast)" if r["base"] == "backcast" else ""),
                       "release": code}
        for r in b["capu"]:
            yield {"country": "PH", "indicator": "capacity_utilisation", "series": r["code"], "label": f"Capacity utilisation, {r['name']}",
                   "measure": "level", "area": "national", "freq": "M", "date": r["date"], "value": r["rate"], "unit": "%",
                   "source": SRC, "release": code}
        for r in b["divs"]:
            for k in ("m3", "ytd"):
                yield {"country": "PH", "indicator": "vopi_calc", "series": f"{r['code']}_{k}", "label": f"VoPI, {r['name']}, {k} (calculated)",
                       "measure": k, "area": "national", "freq": "M", "date": r["date"], "value": r[k], "unit": "%",
                       "source": SRC + ", calculated", "release": code}
        for r in b["gva"]:
            yield {"country": "PH", "indicator": "mfg_gva", "series": f"{r['code']}_{r['price']}_{r['measure']}",
                   "label": f"{r['industry']}, {r['price'].replace('_', ' ')}, {r['measure']}", "measure": r["measure"],
                   "area": "national", "freq": "Q", "date": r["date"], "value": r["value"], "unit": r["unit"],
                   "source": "PSA, National Accounts of the Philippines (OpenSTAT)", "release": code}

    nlong = write_long(long_rows(), OUT / "long.csv")
    fp = hashlib.sha256(json.dumps(b["divs"], sort_keys=True).encode()).hexdigest()[:16]
    write_release(OUT, {"code": code, "label": label, "source": NAME}, warnings, len(b["vopi"]),
                  {"fingerprint": fp, "long_rows": nlong, "stamps": st, "latest": latest})
    return {"updated": True, "code": code, "summary": f"{label}: {len(b['vopi'])} VoPI rows, {len(b['gva'])} GVA rows",
            "warnings": warnings}
