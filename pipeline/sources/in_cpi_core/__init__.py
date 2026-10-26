"""India core CPI measures (Asia Decoded calculation), all-India combined, 2024 base.

MoSPI publishes no core measure. These follow the RBI's two published measures:
- core1: CPI excluding food and beverages (division 01) and fuel (group 04.5 electricity, gas
  and other fuels; class 07.2.2 fuels and lubricants for personal transport equipment).
- core2: core1 also excluding gold/diamond/platinum jewellery and silver jewellery
  (items 13.2.1.1.1.01 and .02).

Calculation: MoSPI's CPI is a Young (modified Laspeyres) index, so an aggregate is the
weight-averaged item index. Each core index is the average of MoSPI's published item indices
(all-India, combined) over the items kept, weighted by MoSPI's published item weights
(Expert Group report, Annex 5.3d: an item's all-India combined weight is the sum of its
state x sector shares). y/y is the 12-month change in that index, from Jan 2026 (the first
month with a 2024-base year earlier). Checked against the RBI's published figures for
Jun-Aug 2026 (core1 3.9, 3.9, 4.2; core2 2.5, 2.7, 2.9): all match to one decimal.

Back to Jan 2014 (y/y from Jan 2015): each measure is also calculated on the 2012 base, the way the
RBI does (MPR Apr 2026, Table IV.1: "derived as residual from headline CPI"), from MoSPI's published
2012-base general index, Food and beverages and Fuel and light groups, and Petrol for vehicle, Diesel
for vehicle, Gold and Silver items, with MoSPI's 2012-base weights (fixed inputs in
raw/in/cpi_core/core2012_inputs.json). The 2012-base index is linked to the 2024-base index by the
ratio of their geometric-mean averages over the 2025 overlap year (the method MoSPI uses for its own
headline back series), and y/y is calculated from the linked index. 2012-base y/y for 2025 is checked
against the RBI's published Table IV.1. MoSPI published no 2012-base item indices for Mar-May 2020,
so those months, and y/y for Mar-May 2020 and Mar-May 2021, are missing.

Runs only when the MoSPI headline data (in_cpi_mospi) has changed, since it pages through
every item for every month.
"""
import csv
import gzip
import hashlib
import json
from collections import defaultdict

from core import mospi
from core.common import DATA, RAW, ROOT, CheckFailed, read_json, write_long, write_release

NAME = "in_cpi_core"
DESCRIPTION = "India core CPI 1 and 2 (excl. food and fuel; and precious metals), calculated from MoSPI items"
OUT = DATA / "in" / "cpi_core"
RAWDIR = RAW / "in" / "cpi_core"
WEIGHTS = ROOT / "raw" / "in" / "cpi_weights" / "Annex_5.3_CPI2024_weights.xlsx"
HEADLINE_RELEASE = DATA / "in" / "cpi" / "release.json"
FIRST_YEAR = 2025
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

PRECIOUS = {"13.2.1.1.1.01", "13.2.1.1.1.02"}
OLD_INPUTS = ROOT / "raw" / "in" / "cpi_core" / "core2012_inputs.json"
# MoSPI CPI 2012=100 weights, all-India combined (groups and items).
OLD_W = {"food_bev": 45.86, "fuel_light": 6.84, "petrol": 2.18697, "diesel": 0.148, "gold": 1.08035, "silver": 0.11175}
OLD_EXCL = {"core1": ["food_bev", "fuel_light", "petrol", "diesel"],
            "core2": ["food_bev", "fuel_light", "petrol", "diesel", "gold", "silver"]}
# RBI MPR April 2026, Table IV.1: 2012-base y/y, Jan-Dec 2025 (one decimal). A fixed reference check.
RBI_2025 = {"core1": [3.9, 4.3, 4.3, 4.4, 4.3, 4.6, 4.2, 4.3, 4.5, 4.5, 4.4, 4.8],
            "core2": [3.2, 3.4, 3.3, 3.5, 3.4, 3.5, 3.2, 3.1, 3.1, 2.6, 2.4, 2.4]}
LINK_YEAR = "2025"
CALC_VERSION = 3  # bump when the calculation changes, so the next run recomputes without new data


def _old_core():
    """{measure: {YYYY-MM-01: 2012-base core index}}, residual from the published general index."""
    src = json.loads(OLD_INPUTS.read_text())["series"]
    out = {}
    for key, excl in OLD_EXCL.items():
        wk = 100 - sum(OLD_W[e] for e in excl)
        idx = {}
        for m, g in src["general"].items():
            vals = [src[e].get(m) for e in excl]
            if None in vals:
                continue
            idx[f"{m}-01"] = (100 * g - sum(OLD_W[e] * v for e, v in zip(excl, vals))) / wk
        out[key] = idx
    return out


CONTRIB = [("food", "Food and beverages"), ("fuel", "Fuel"), ("core", "CPI excluding food and fuel")]


def _contrib_old():
    """2012 base: {month: {food, fuel, core, cpi}} contributions to y/y (pp), Jan 2015-Dec 2025."""
    src = json.loads(OLD_INPUTS.read_text())["series"]
    w = OLD_W
    out = {}
    for m, h in src["general"].items():
        p = f"{int(m[:4]) - 1}{m[4:]}"
        hp = src["general"].get(p)
        need = ["food_bev", "fuel_light", "petrol", "diesel"]
        if not hp or any(src[k].get(m) is None or src[k].get(p) is None for k in need):
            continue
        food = w["food_bev"] * (src["food_bev"][m] - src["food_bev"][p]) / hp
        fuel = sum(w[k] * (src[k][m] - src[k][p]) for k in ("fuel_light", "petrol", "diesel")) / hp
        cpi = (h / hp - 1) * 100
        out[f"{m}-01"] = {"food": food, "fuel": fuel, "core": cpi - food - fuel, "cpi": cpi, "base": "2012"}
    return out


def _contrib_new(rows, weights):
    """2024 base: {month: {food, fuel, core, cpi}} contributions to y/y (pp), from Jan 2026."""
    idx = defaultdict(dict)
    for r in rows:
        if r.get("state") != "All India" or r.get("sector") != "Combined" or r.get("index") in (None, ""):
            continue
        code = r.get("code") or ("general" if r.get("division") == "CPI (General)" and not r.get("group") else None)
        if code in ("general", "01", "04.5", "07.2.2"):
            idx[code][_month(r)] = float(r["index"])
    wt = lambda prefix: sum(w for k, (_, w) in weights.items() if k.startswith(prefix))
    wf, w045, w0722 = wt("01."), wt("04.5."), wt("07.2.2.")
    out = {}
    for m, h in idx["general"].items():
        p = _prev_year(m)
        hp = idx["general"].get(p)
        if not hp or any(p not in idx[c] or m not in idx[c] for c in ("01", "04.5", "07.2.2")):
            continue
        food = wf * (idx["01"][m] - idx["01"][p]) / hp
        fuel = (w045 * (idx["04.5"][m] - idx["04.5"][p]) + w0722 * (idx["07.2.2"][m] - idx["07.2.2"][p])) / hp
        cpi = (h / hp - 1) * 100
        out[m] = {"food": food, "fuel": fuel, "core": cpi - food - fuel, "cpi": cpi, "base": "2024"}
    return out


def _gm(vals):
    import math
    return math.exp(sum(math.log(v) for v in vals) / len(vals))  # gold/diamond/platinum jewellery; silver jewellery
MEASURES = [
    ("core1", "Core 1 (CPI excluding food and fuel)"),
    ("core2", "Core 2 (CPI excluding food, fuel and precious metals)"),
]


def _food_fuel(code):
    return code.startswith("01.") or code.startswith("04.5.") or code.startswith("07.2.2.")


def _excluded(measure, code):
    return _food_fuel(code) or (measure == "core2" and code in PRECIOUS)


def item_weights():
    """{item code: (name, all-India combined weight)} from Annex 5.3d; weights sum to 100."""
    import openpyxl
    wb = openpyxl.load_workbook(WEIGHTS, read_only=True, data_only=True)
    ws = wb["5.3d"]
    w, names = defaultdict(float), {}
    header = None
    for row in ws.iter_rows(values_only=True):
        if header is None:
            if row and row[0] == "State":
                header = [str(c).strip() if c else c for c in row]
            continue
        if not row or row[0] is None or row[4] is None:
            continue
        code = str(row[4]).strip()
        w[code] += float(row[13])
        names[code] = str(row[3]).strip()
    return {k: (names[k], w[k]) for k in w}


def _month(r):
    return f"{int(r['year'])}-{mospi.month_number(r['month']):02d}-01"


def _prev_year(d):
    return f"{int(d[:4]) - 1}{d[4:]}"


def update(from_file=None, **_):
    state = read_json(OUT / "release.json", {}) or {}
    head = read_json(HEADLINE_RELEASE, {}) or {}
    trigger = head.get("fingerprint")
    if (not from_file and trigger and trigger == state.get("headline_fingerprint")
            and state.get("calc_version") == CALC_VERSION):
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('latest_month')})"}

    weights = item_weights()
    if from_file:
        rows = json.loads(gzip.decompress(open(from_file, "rb").read()))
    else:
        import datetime as dt
        years = list(range(FIRST_YEAR, dt.date.today().year + 1))
        rows, _ = mospi.cpi("Current", years=years, state_code=1, sector_code=3, max_pages=600)

    items, general = defaultdict(dict), {}
    for r in rows:
        if r.get("state") != "All India" or r.get("sector") != "Combined":
            continue
        if r.get("item"):
            items[r["code"]][_month(r)] = float(r["index"]) if r.get("index") not in (None, "") else None
        elif r.get("division") == "CPI (General)":
            general[_month(r)] = float(r["index"])

    errors, warnings = [], []
    if not general:
        raise CheckFailed(["no general index returned"])
    months = sorted(general)
    latest = months[-1]
    total_w = sum(w for _, w in weights.values())
    if abs(total_w - 100) > 0.001:
        errors.append(f"item weights sum to {total_w:.4f}, expected 100")
    if set(items) != set(weights):
        errors.append(f"items in data and weights differ: {len(set(items) - set(weights))} not weighted, "
                      f"{len(set(weights) - set(items))} weighted but missing")
    for m in months:
        missing = [k for k in weights if items.get(k, {}).get(m) is None]
        if missing:
            errors.append(f"{m}: {len(missing)} item indices missing")
    if errors:
        raise CheckFailed(errors)
    # The weighted items must reproduce MoSPI's published general index (rounding: ±0.02).
    for m in months:
        agg = sum(w * items[k][m] for k, (_, w) in weights.items()) / total_w
        if abs(agg - general[m]) > 0.02:
            errors.append(f"{m}: items give {agg:.3f}, published general index {general[m]}")
    if state.get("latest_month") and latest < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one already stored ({state['latest_month']})")
    if errors:
        raise CheckFailed(errors)

    out = {}
    for key, _ in MEASURES:
        keep = {k: w for k, (_, w) in weights.items() if not _excluded(key, k)}
        sw = sum(keep.values())
        idx = {m: sum(w * items[k][m] for k, w in keep.items()) / sw for m in months}
        out[key] = {"weight": sw, "new": idx}

    # Link the 2012-base core to the 2024-base core over the 2025 overlap; y/y from the linked index.
    old = _old_core()
    links = {}
    for key, _ in MEASURES:
        new = out[key]["new"]
        ov = [m for m in new if m[:4] == LINK_YEAR]
        if len(ov) != 12 or any(m not in old[key] for m in ov):
            errors.append(f"{key}: no full {LINK_YEAR} overlap between the 2012-base and 2024-base core")
            continue
        f = _gm([new[m] for m in ov]) / _gm([old[key][m] for m in ov])
        links[key] = f
        linked = {m: v * f for m, v in old[key].items() if m < f"{LINK_YEAR}-01-01"}
        linked.update(new)
        out[key]["index"] = linked
        out[key]["basis"] = {m: ("2012 base, linked" if m < f"{LINK_YEAR}-01-01" else "2024 base") for m in linked}
        out[key]["yoy"] = {m: (linked[m] / linked[_prev_year(m)] - 1) * 100 for m in linked if _prev_year(m) in linked}
        # 2012-base y/y for 2025 against the RBI's published figures (one decimal: within 0.06pp).
        for i, ref in enumerate(RBI_2025[key]):
            m, p = f"2025-{i + 1:02d}-01", f"2024-{i + 1:02d}-01"
            yo = (old[key][m] / old[key][p] - 1) * 100
            if abs(yo - ref) > 0.06:
                errors.append(f"{key} {m[:7]}: 2012-base y/y {yo:.2f}, RBI published {ref}")
        # Calculated 2026 y/y is on the 2024 base alone, unaffected by the link.
    if errors:
        raise CheckFailed(errors)

    code = f"M{latest[:7]}"
    if state.get("code") == code:
        warnings.append("recent months revised (no new month)")
    release = {"code": code, "label": f"{MON[int(latest[5:7]) - 1]} {latest[:4]}", "latest_month": latest,
               "table": "Calculated from MoSPI CPI 2024 item indices (all-India, combined) and Annex 5.3d item weights; 2012-base residual core linked over 2025",
               "weights": {k: round(v["weight"], 4) for k, v in out.items()},
               "weights_2012": {k: round(100 - sum(OLD_W[e] for e in v), 4) for k, v in OLD_EXCL.items()},
               "link_factors_2012": {k: round(v, 6) for k, v in links.items()}, "link_year": LINK_YEAR}

    OUT.mkdir(parents=True, exist_ok=True)
    labels = dict(MEASURES)
    csv_rows = []
    for order, (key, label) in enumerate(MEASURES):
        for m in sorted(out[key]["index"]):
            y = out[key]["yoy"].get(m)
            csv_rows.append({"date": m, "series": key, "label": label, "order": order,
                             "index": round(out[key]["index"][m], 3), "yoy": None if y is None else round(y, 2),
                             "basis": out[key]["basis"][m]})
    csv_rows.sort(key=lambda r: (r["date"], r["order"]))
    cols = ["date", "series", "label", "order", "index", "yoy", "basis"]
    with open(OUT / "in_cpi_core.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in csv_rows:
            w.writerow(["" if r[c] is None else r[c] for c in cols])

    # Contributions to CPI y/y: within the 2012 base to Dec 2025, within the 2024 base from Jan 2026.
    contrib = _contrib_old()
    contrib = {m: v for m, v in contrib.items() if m < "2026-01-01"}
    contrib.update(_contrib_new(rows, weights))
    for m, v in contrib.items():
        # The published component indices, at their weights, must account for the headline (residual = core):
        # a large or implausible core contribution means a broken input.
        if not -5 < v["core"] < 10:
            raise CheckFailed([f"{m}: core contribution {v['core']:.2f}pp out of range"])
    with open(OUT / "in_cpi_contrib.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "cpi_yoy", "food", "fuel", "core", "base"])
        for m in sorted(contrib):
            v = contrib[m]
            w.writerow([m, round(v["cpi"], 2), round(v["food"], 3), round(v["fuel"], 3), round(v["core"], 3), v["base"]])

    def long_rows():
        for r in csv_rows:
            for meas, unit in (("index", "index, 2024 = 100"), ("yoy", "%")):
                yield {"country": "IN", "indicator": "cpi_core", "series": r["series"], "label": labels[r["series"]],
                       "measure": meas, "area": "all-India", "freq": "M", "date": r["date"], "value": r[meas],
                       "unit": unit, "source": "Asia Decoded calculation from MoSPI", "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    fingerprint = hashlib.sha256(json.dumps({k: v["index"] for k, v in out.items()}, sort_keys=True).encode()).hexdigest()[:16]
    RAWDIR.mkdir(parents=True, exist_ok=True)
    (RAWDIR / f"{code}_{fingerprint}.json.gz").write_bytes(gzip.compress(json.dumps(rows).encode()))
    write_release(OUT, release, warnings, len(csv_rows),
                  {"fingerprint": fingerprint, "headline_fingerprint": trigger, "long_rows": nlong,
                   "calc_version": CALC_VERSION})
    lv = {k: out[k]["yoy"].get(latest) for k in out}
    return {"updated": True, "code": code,
            "summary": f"{release['label']}: core1 {lv['core1']:.2f}%, core2 {lv['core2']:.2f}% y/y",
            "warnings": warnings}
