"""Philippines CPI: Philippine Statistics Authority, CPI for all income households (2018 = 100), OpenSTAT.

Everything is as published by the PSA; nothing is calculated here.
  - CPI by commodity group (COICOP 2018, 354 groups to 4 digits), Jan 2018 on: index (0012M4ACP22) and
    y/y (0012M4ACP23, Jan 2019 on). PSA's backcast on the 2018 base: index Jan 1994-Dec 2017 by group
    (0012M4ACP28) and all items 1957-1993 (0012M4ACP26); y/y Jan 1995-Dec 2018 by group and region
    (0012M4ACP29) and all items 1958-1994 (0012M4ACP27).
  - Core CPI (PSA definition: excludes rice, corn, fresh meat, fresh fish, fruits, vegetables, electricity,
    LPG, diesel and gasoline): index and y/y Jan 2018 / Jan 2019 on (0012M4ACP30, 31), backcast index
    1994-2017 and y/y 1995-2017 (0012M4ACP33, 34). PSA publishes no core y/y for 2018: left blank.
  - Seasonally adjusted CPI and its m/m change by major group, Philippines, NCR and AONCR (0012M4ASAC1, 2).
  - CPI for the bottom 30% income households (0022M4ABIR1, 2), national, NCR, AONCR.
  - Weights (% of CPI): all income (0012M4ACP25), core (0012M4ACP32, its all-items weight is core's share
    of the CPI), bottom 30% (0022M4ABIR3).
  - Regions: all-items y/y for NCR, AONCR and the 17 regions.
  - Every commodity group (national): index and y/y for the latest 25 months (ph_cpi_items.csv).

New data is detected from the folder listing's last-updated dates (one call); the tables are fetched only
when one of them changes. Raw responses: raw/ph/cpi_psa/<code>/<table>.json.gz.
"""
import csv
import gzip
import hashlib
import json
import re

from core import psa
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "ph_cpi_psa"
DESCRIPTION = "Philippines CPI (PSA OpenSTAT, 2018 = 100): headline, core, SA, bottom 30%, regions, weights"
OUT = DATA / "ph" / "cpi"
RAWDIR = RAW / "ph" / "cpi_psa"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
LONG_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
               "October", "November", "December"]
C = "2M/PI/CPI/2018NEW/"
TABLES = {
    "cpi_index": C + "0012M4ACP22.px", "cpi_yoy": C + "0012M4ACP23.px", "cpi_weights": C + "0012M4ACP25.px",
    "cpi_index_1957": C + "0012M4ACP26.px", "cpi_yoy_1958": C + "0012M4ACP27.px",
    "cpi_index_back": C + "0012M4ACP28.px", "cpi_yoy_back": C + "0012M4ACP29.px",
    "core_index": C + "0012M4ACP30.px", "core_yoy": C + "0012M4ACP31.px", "core_weights": C + "0012M4ACP32.px",
    "core_index_back": C + "0012M4ACP33.px", "core_yoy_back": C + "0012M4ACP34.px",
    "sa_index": "2M/PI/SACPI/0012M4ASAC1.px", "sa_mom": "2M/PI/SACPI/0012M4ASAC2.px",
    "b30_index": "2M/PI/BIH/2018NEW/0022M4ABIR1.px", "b30_yoy": "2M/PI/BIH/2018NEW/0022M4ABIR2.px",
    "b30_weights": "2M/PI/BIH/2018NEW/0022M4ABIR3.px",
}
FOLDERS = [C.rstrip("/"), "2M/PI/SACPI", "2M/PI/BIH/2018NEW"]
PH, NCR, AONCR = "PHILIPPINES", "National Capital Region (NCR)", "Areas Outside National Capital Region (AONCR)"
REGIONAL = lambda t: not t.startswith("....")  # noqa: E731 - Philippines, NCR, AONCR, 17 regions
LEVEL = lambda n: (lambda t: len(t.split(" - ")[0].split(".")) <= n)  # noqa: E731
SELECT = {
    "cpi_index": {"Geolocation": [PH, NCR, AONCR]},
    "cpi_yoy": {"Geolocation": [PH, NCR, AONCR]},
    "cpi_yoy_reg": {"Geolocation": REGIONAL, "Commodity Description": ["0 - ALL ITEMS"]},
    "cpi_weights": {"Geolocation": [PH, NCR, AONCR]},
    "cpi_index_1957": {"Geolocation": [PH]},
    "cpi_yoy_1958": {"Geolocation": [PH]},
    "cpi_index_back": {"Geolocation": [PH, NCR, AONCR]},
    "cpi_yoy_back": {"Geolocation": [PH, NCR, AONCR]},
    "cpi_yoy_back_reg": {"Geolocation": REGIONAL, "Commodity Description": ["0 - ALL ITEMS"]},
    "b30_index": {"Geolocation": ["PHILIPPINES", "NCR", "AONCR"], "Commodity Description": LEVEL(2)},
    "b30_yoy": {"Geolocation": ["PHILIPPINES", "NCR", "AONCR"], "Commodity Description": LEVEL(2)},
    "b30_weights": {"Geolocation": ["PHILIPPINES"]},
}
AREA = {PH: "national", "PHILIPPINES": "national", NCR: "ncr", "NCR": "ncr", AONCR: "aoncr", "AONCR": "aoncr"}

DIVISIONS = {
    "01": "Food and non-alcoholic beverages", "02": "Alcoholic beverages and tobacco", "03": "Clothing and footwear",
    "04": "Housing, water, electricity, gas and other fuels", "05": "Furnishings and household equipment",
    "06": "Health", "07": "Transport", "08": "Information and communication", "09": "Recreation, sport and culture",
    "10": "Education services", "11": "Restaurants and accommodation services", "12": "Financial services",
    "13": "Personal care and miscellaneous goods and services",
}
# key, commodity code, label, group
SERIES = [("all", "0", "All items", "headline")] + \
    [(f"d{k}", k, v, "division") for k, v in DIVISIONS.items()] + [
    ("food", "01.1", "Food", "drivers"),
    ("rice", "01.1.1.12", "Rice", "drivers"),
    ("meat", "01.1.2", "Meat", "drivers"),
    ("fish", "01.1.3", "Fish and other seafood", "drivers"),
    ("vegetables", "01.1.7", "Vegetables, tubers and pulses", "drivers"),
    ("rent", "04.1", "Actual rentals for housing", "drivers"),
    ("energy_home", "04.5", "Electricity, gas and other fuels", "drivers"),
    ("electricity", "04.5.1", "Electricity", "drivers"),
    ("lpg", "04.5.2", "Gas (LPG)", "drivers"),
    ("fuels_transport", "07.2.2", "Fuels and lubricants for personal transport", "drivers"),
    ("transport_services", "07.3", "Passenger transport services", "drivers"),
]
SA_KEYS = {"ALL ITEMS": "all", "FOOD AND NON-ALCOHOLIC BEVERAGES": "d01", "ALCOHOLIC BEVERAGES AND TOBACCO": "d02",
           "NON-FOOD": "nonfood", "CLOTHING AND FOOTWEAR": "d03", "HOUSING, WATER, ELECTRICITY, GAS, AND OTHER FUELS": "d04",
           "FURNISHINGS, HOUSEHOLD EQUIPMENT AND ROUTINE HOUSEHOLD MAINTENANCE": "d05", "HEALTH": "d06",
           "TRANSPORT": "d07", "INFORMATION AND COMMUNICATION": "d08", "RECREATION, SPORT AND CULTURE": "d09",
           "EDUCATION SERVICES": "d10", "RESTAURANTS AND ACCOMMODATION SERVICES": "d11", "FINANCIAL SERVICES": "d12",
           "PERSONAL CARE, AND MISCELLANEOUS GOODS AND SERVICES": "d13"}
REGION_NAMES = {
    "PHILIPPINES": "Philippines", NCR: "NCR", AONCR: "Areas outside NCR",
    "Cordillera Administrative Region (CAR)": "Cordillera (CAR)", "Region I (Ilocos Region)": "Ilocos (I)",
    "Region II (Cagayan Valley)": "Cagayan Valley (II)", "Region III (Central Luzon)": "Central Luzon (III)",
    "Region IV-A (CALABARZON)": "CALABARZON (IV-A)", "MIMAROPA Region": "MIMAROPA",
    "Region V (Bicol Region)": "Bicol (V)", "Region VI (Western Visayas)": "Western Visayas (VI)",
    "Region VII (Central Visayas)": "Central Visayas (VII)", "Region VIII (Eastern Visayas)": "Eastern Visayas (VIII)",
    "Region IX (Zamboanga Peninsula)": "Zamboanga Peninsula (IX)", "Region X (Northern Mindanao)": "Northern Mindanao (X)",
    "Region XI (Davao Region)": "Davao (XI)", "Region XII (SOCCSKSARGEN)": "SOCCSKSARGEN (XII)",
    "Bangsamoro Autonomous Region in Muslim Mindanao (BARMM)": "BARMM",
    "Region XIII (Caraga)": "Caraga (XIII)", "Negros Island Region (NIR)": "Negros Island (NIR)",
}
YOY_TOL = 0.15  # published y/y vs the published index (indices are rounded to one decimal)


def _code(t):
    return t.split(" - ")[0].strip()


def _name(t):
    s = t.split(" - ", 1)[1] if " - " in t else t
    return re.sub(r"\s*\((ND|SD|D|S|s)\)\s*$", "", s).strip()


def _dur(t):
    m = re.search(r"\((ND|SD|D|S|s)\)\s*$", t)
    return m.group(1).upper() if m else ""


def _date(year, period):
    p = period.strip()
    if p in MONTHS:
        return f"{year}-{MONTHS.index(p) + 1:02d}-01"
    if p in LONG_MONTHS:
        return f"{year}-{LONG_MONTHS.index(p) + 1:02d}-01"
    return None  # annual average


def _geo(r):
    return r.get("Geolocation", PH).strip(". ")


def stamps():
    out = {}
    for f in FOLDERS:
        for it in psa._request(f"{psa.BASE}/{f}"):
            out[f"{f}/{it['id']}"] = it.get("updated")
    return out


def fetch(dest):
    """All tables as tidy rows; also saved under dest."""
    dest.mkdir(parents=True, exist_ok=True)
    got = {}
    jobs = list(TABLES.items()) + [("cpi_yoy_reg", TABLES["cpi_yoy"]), ("cpi_yoy_back_reg", TABLES["cpi_yoy_back"])]
    metas = {}
    for name, path in jobs:
        m = metas.get(path) or psa.meta(path)
        metas[path] = m
        rows = psa.get(path, SELECT.get(name), m)
        got[name] = rows
        with gzip.open(dest / f"{name}.json.gz", "wt", encoding="utf-8") as f:
            json.dump({"path": path, "title": m.get("title"), "rows": rows}, f, ensure_ascii=False)
    return got


def load(src):
    return {p.name[:-8]: json.load(gzip.open(p, "rt"))["rows"] for p in src.glob("*.json.gz")}


def build(t):
    """Dashboard tables from the tidy rows. Returns dict of row lists and the latest month."""
    # index and y/y by (area, commodity code, date); current tables win over backcasts where both exist
    idx, yoy = {}, {}

    def put(store, rows, override):
        for r in rows:
            if r["value"] is None:
                continue
            d = _date(r["Year"], r["Period"])
            if not d:
                continue
            com = _code(r.get("Commodity Description", "0 - ALL ITEMS"))
            k = (AREA.get(_geo(r), _geo(r)), com, d)
            if override or k not in store:
                store[k] = r["value"]

    for name in ("cpi_index_1957", "cpi_index_back", "cpi_index"):
        put(idx, t[name], name == "cpi_index")
    for name in ("cpi_yoy_1958", "cpi_yoy_back", "cpi_yoy"):
        put(yoy, t[name], name == "cpi_yoy")
    core_idx, core_yoy = {}, {}
    for name, store in (("core_index_back", core_idx), ("core_index", core_idx),
                        ("core_yoy_back", core_yoy), ("core_yoy", core_yoy)):
        for r in t[name]:
            com = r.get("Commodity Description", "0 - ALL ITEMS")
            d = _date(r["Year"], r["Period"])
            if r["value"] is not None and d and _code(com) == "0":
                store[d] = r["value"]
    b_idx, b_yoy = {}, {}
    put(b_idx, t["b30_index"], True)
    put(b_yoy, t["b30_yoy"], True)

    latest = max(d for (a, c, d) in idx if a == "national" and c == "0")
    weights = {(AREA.get(_geo(r), _geo(r)), _code(r["Commodity Description"])): r["value"]
               for r in t["cpi_weights"] if r["value"] is not None}

    series = []
    order = 0

    def add(area, key, label, group, ix, yy, w=None):
        nonlocal order
        for d in sorted(set(ix) | set(yy)):
            series.append({"date": d, "area": area, "series": key, "label": label, "group": group, "order": order,
                           "index": ix.get(d), "yoy": yy.get(d), "weight": w})
        order += 1

    for key, com, label, group in SERIES:
        ix = {d: v for (a, c, d), v in idx.items() if a == "national" and c == com}
        yy = {d: v for (a, c, d), v in yoy.items() if a == "national" and c == com}
        add("national", key, label, group, ix, yy, weights.get(("national", com)))
        if key == "all":
            add("national", "core", "Core (PSA definition)", "headline", core_idx, core_yoy,
                next((r["value"] for r in t["core_weights"] if _code(r["Commodity Description"]) == "0"), None))
    for area, lab in (("ncr", "NCR"), ("aoncr", "Areas outside NCR")):
        for key, com, label in (("all", "0", "All items"), ("food", "01.1", "Food")):
            ix = {d: v for (a, c, dd), v in idx.items() for d in [dd] if a == area and c == com}
            yy = {d: v for (a, c, dd), v in yoy.items() for d in [dd] if a == area and c == com}
            add(area, key, f"{lab}: {label}", "area", ix, yy, weights.get((area, com)))
    for area in ("national", "ncr", "aoncr"):
        for key, com, label in (("b30_all", "0", "Bottom 30%: all items"), ("b30_food", "01.1", "Bottom 30%: food")):
            ix = {d: v for (a, c, d), v in b_idx.items() if a == area and c == com}
            yy = {d: v for (a, c, d), v in b_yoy.items() if a == area and c == com}
            bw = next((r["value"] for r in t["b30_weights"] if _code(r["Commodity Description"]) == com), None) \
                if area == "national" else None
            add(area, key, label, "bottom30", ix, yy, bw)

    # seasonally adjusted
    sa = {}
    for name, field in (("sa_index", "sa_index"), ("sa_mom", "sa_mom")):
        for r in t[name]:
            d = _date(r["Year"], r["Period"])
            if r["value"] is None or not d:
                continue
            key = SA_KEYS.get(r["Commodity Description"].strip())
            if not key:
                continue
            area = AREA.get(_geo(r), _geo(r))
            sa.setdefault((d, area, key), {"label": r["Commodity Description"].strip().capitalize()})[field] = r["value"]
    keys = list(dict.fromkeys(SA_KEYS.values()))
    sa_rows = [{"date": d, "area": a, "series": k, "label": ("Non-food" if k == "nonfood" else
                                                          "All items" if k == "all" else DIVISIONS[k[1:]]),
                "order": keys.index(k), "sa_index": v.get("sa_index"), "sa_mom": v.get("sa_mom")}
               for (d, a, k), v in sa.items()]
    sa_rows.sort(key=lambda r: (r["date"], r["area"], r["order"]))

    # regions: all-items y/y
    reg = {}
    for name in ("cpi_yoy_back_reg", "cpi_yoy_reg"):
        for r in t[name]:
            d = _date(r["Year"], r["Period"])
            if r["value"] is None or not d:
                continue
            reg[(d, r["Geolocation"].strip(". "))] = r["value"]
    rorder = list(REGION_NAMES)
    reg_rows = [{"date": d, "region": REGION_NAMES.get(g, g), "order": rorder.index(g) if g in rorder else 99,
                 "yoy": v} for (d, g), v in reg.items()]
    reg_rows.sort(key=lambda r: (r["date"], r["order"]))

    # every commodity group, national, 2018 base: index, y/y and weights
    cw = {_code(r["Commodity Description"]): r["value"] for r in t["core_weights"] if r["value"] is not None}
    bw = {_code(r["Commodity Description"]): r["value"] for r in t["b30_weights"] if r["value"] is not None}
    names = {}
    for r in t["cpi_index"]:
        names.setdefault(_code(r["Commodity Description"]), r["Commodity Description"])
    codes = sorted(names, key=lambda c: [int(x) for x in c.split(".")])
    weight_rows = [{"code": c, "name": _name(names[c]), "level": len(c.split(".")) - (1 if c == "0" else 0),
                    "durability": _dur(names[c]), "weight": weights.get(("national", c)),
                    "weight_ncr": weights.get(("ncr", c)), "weight_aoncr": weights.get(("aoncr", c)),
                    "in_core": c in cw, "weight_core": cw.get(c), "weight_b30": bw.get(c), "order": i}
                   for i, c in enumerate(codes)]
    item_rows = []
    y0 = f"{int(latest[:4]) - 2}{latest[4:]}"  # latest 25 months
    for (a, c, d), v in idx.items():
        if a == "national" and d >= y0 and c in names:
            item_rows.append({"date": d, "code": c, "name": _name(names[c]), "order": codes.index(c),
                              "index": v, "yoy": yoy.get((a, c, d))})
    item_rows.sort(key=lambda r: (r["date"], r["order"]))
    series.sort(key=lambda r: (r["date"], r["area"], r["order"]))
    return {"series": series, "sa": sa_rows, "regions": reg_rows, "weights": weight_rows, "items": item_rows,
            "latest": latest, "idx": idx, "yoy": yoy, "weights_map": weights}


def check(b, state):
    errors, warnings = [], []
    latest = b["latest"]
    if state.get("latest_month") and latest < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one already stored ({state['latest_month']})")
    have = {(r["area"], r["series"]) for r in b["series"] if r["date"] == latest and r["yoy"] is not None}
    for need in [("national", "all"), ("national", "core"), ("ncr", "all"), ("aoncr", "all"),
                 ("national", "b30_all"), ("national", "food")] + [("national", f"d{k}") for k in DIVISIONS]:
        if need not in have:
            errors.append(f"{need[0]} {need[1]}: no y/y for {latest}")
    if not any(r["date"] == latest and r["series"] == "all" and r["area"] == "national" and r["sa_mom"] is not None
               for r in b["sa"]):
        warnings.append(f"no seasonally adjusted m/m for {latest} yet")
    # gaps in headline y/y
    dates = sorted(r["date"] for r in b["series"] if r["area"] == "national" and r["series"] == "all" and r["yoy"] is not None)
    y, m = int(dates[0][:4]), int(dates[0][5:7])
    while f"{y}-{m:02d}-01" <= latest:
        if f"{y}-{m:02d}-01" not in dates:
            errors.append(f"headline y/y missing for {y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    # published y/y vs published index, 2018 base (Jan 2019 on)
    idx, yoy = b["idx"], b["yoy"]
    bad = []
    for (a, c, d), v in yoy.items():
        if a != "national" or d < "2019-01-01" or c.count(".") > 1:
            continue
        p = idx.get((a, c, f"{int(d[:4]) - 1}{d[4:]}"))
        n = idx.get((a, c, d))
        if p and n and abs((n / p - 1) * 100 - v) > YOY_TOL:
            bad.append(f"{c} {d[:7]}: published {v}, index gives {(n / p - 1) * 100:.2f}")
    if len(bad) > 5:
        errors.append(f"{len(bad)} published y/y rates differ from the index by more than {YOY_TOL}pp, e.g. {bad[:3]}")
    elif bad:
        warnings.append("y/y vs index: " + "; ".join(bad))
    # weights: divisions sum to 100; weighted division indices reproduce the all-items index
    w = b["weights_map"]
    wd = [w.get(("national", k)) for k in DIVISIONS]
    if None in wd or abs(sum(wd) - 100) > 0.01:
        errors.append(f"division weights sum to {sum(x or 0 for x in wd):.3f}, not 100")
    else:
        worst = 0
        for (a, c, d), v in idx.items():
            if a == "national" and c == "0" and d >= "2018-01-01":
                parts = [idx.get(("national", k, d)) for k in DIVISIONS]
                if None not in parts:
                    worst = max(worst, abs(sum(x * y for x, y in zip(parts, wd)) / 100 - v))
        if worst > 0.15:
            errors.append(f"weighted division indices miss the all-items index by up to {worst:.3f}")
    for r in b["series"]:
        if r["index"] is not None and not 0 < r["index"] < 1000:
            errors.append(f"{r['series']} {r['date']} index {r['index']} out of range")
            break
    return errors, warnings


def _write_csv(path, rows, cols):
    with open(path, "w", newline="") as f:
        wr = csv.writer(f, lineterminator="\n")
        wr.writerow(cols)
        for r in rows:
            wr.writerow(["" if r.get(c) is None else r[c] for c in cols])


def update(from_dir=None, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    if from_dir:
        from pathlib import Path
        t, st = load(Path(from_dir)), state.get("stamps", {})
    else:
        st = stamps()
        if st == state.get("stamps"):
            return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
        tmp = RAWDIR / "_incoming"
        t = fetch(tmp)
    b = build(t)
    errors, warnings = check(b, state)
    if errors:
        raise CheckFailed(errors)
    latest = b["latest"]
    code = f"C{latest[:7]}"
    if not from_dir:
        dest = RAWDIR / latest[:7]
        if dest.exists():
            for p in dest.glob("*"):
                p.unlink()
            dest.rmdir()
        (RAWDIR / "_incoming").rename(dest)
    _write_csv(OUT / "ph_cpi.csv", b["series"], ["date", "area", "series", "label", "group", "order", "index", "yoy", "weight"])
    _write_csv(OUT / "ph_cpi_sa.csv", b["sa"], ["date", "area", "series", "label", "order", "sa_index", "sa_mom"])
    _write_csv(OUT / "ph_cpi_regions.csv", b["regions"], ["date", "region", "order", "yoy"])
    _write_csv(OUT / "ph_cpi_weights.csv", b["weights"], ["code", "name", "level", "durability", "weight", "weight_ncr",
                                                           "weight_aoncr", "in_core", "weight_core", "weight_b30", "order"])
    _write_csv(OUT / "ph_cpi_items.csv", b["items"], ["date", "code", "name", "order", "index", "yoy"])
    label = f"{MONTHS[int(latest[5:7]) - 1]} {latest[:4]}"

    def long_rows():
        for r in b["series"]:
            for meas, unit in (("index", "index, 2018 = 100"), ("yoy", "%")):
                yield {"country": "PH", "indicator": "cpi", "series": r["series"], "label": r["label"], "measure": meas,
                       "area": r["area"], "freq": "M", "date": r["date"], "value": r[meas], "unit": unit,
                       "source": "Philippine Statistics Authority", "release": code}
        for r in b["sa"]:
            for meas, unit in (("sa_index", "index, 2018 = 100, seasonally adjusted"), ("sa_mom", "% m/m, seasonally adjusted")):
                yield {"country": "PH", "indicator": "cpi", "series": r["series"], "label": r["label"], "measure": meas,
                       "area": r["area"], "freq": "M", "date": r["date"], "value": r[meas], "unit": unit,
                       "source": "Philippine Statistics Authority", "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    fingerprint = hashlib.sha256(json.dumps(b["series"][-800:], sort_keys=True).encode()).hexdigest()[:16]
    if state.get("code") == code:
        warnings.append("same month re-published (revision or table refresh)")
    release = {"code": code, "label": label, "latest_month": latest,
               "table": "PSA OpenSTAT, CPI for all income households (2018 = 100): 0012M4ACP22-34, SACPI, bottom 30%"}
    write_release(OUT, release, warnings, len(b["series"]), {"fingerprint": fingerprint, "long_rows": nlong, "stamps": st})
    return {"updated": True, "code": code, "summary": f"{label}: {len(b['series'])} rows", "warnings": warnings}
