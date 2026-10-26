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
CALC_VERSION = 8  # bump when the calculation changes, so the next run recomputes without new data


FUEL_PRICES = ROOT / "raw" / "in" / "fuel_ppac" / "ppac_metro_daily.json"
GOLD_PRICES = ROOT / "raw" / "in" / "gold_rbi" / "gold_silver_mumbai_2019_2021.json"
GAP = ["2020-03", "2020-04", "2020-05"]  # MoSPI published no 2012-base item indices for these months


def _price_months():
    """Monthly average prices: petrol and diesel (PPAC, average of the four metros over calendar days,
    carrying each revision forward) and gold and silver (RBI, Mumbai monthly averages)."""
    import datetime as dt
    daily = json.loads(FUEL_PRICES.read_text())["daily"]
    days = sorted(daily)
    acc = defaultdict(lambda: defaultdict(list))
    d, end, cur = dt.date.fromisoformat(days[0]), dt.date.fromisoformat(days[-1]), None
    while d <= end:
        cur = daily.get(d.isoformat(), cur)
        for f in ("petrol", "diesel"):
            acc[f][d.strftime("%Y-%m")].append(sum(cur[f]) / len(cur[f]))
        d += dt.timedelta(days=1)
    out = {f: {m: sum(v) / len(v) for m, v in acc[f].items()} for f in acc}
    gold = json.loads(GOLD_PRICES.read_text())["data"]
    for f in ("gold", "silver"):
        out[f] = {m: v[f] for m, v in gold.items()}
    return out


def _old_inputs():
    """2012-base inputs, with the Mar-May 2020 item indices for petrol, diesel, gold and silver imputed:
    the Feb 2020 index moved with the item's market price, then benchmarked to MoSPI's Jun 2020 index
    (the gap between the index's and the price's Feb-Jun change spread evenly, geometrically, over the
    four months)."""
    src = json.loads(OLD_INPUTS.read_text())["series"]
    prices = _price_months()
    for k in ("petrol", "diesel", "gold", "silver"):
        s, pr = src[k], prices[k]
        if any(m in s for m in GAP) or "2020-02" not in s or "2020-06" not in s:
            continue
        r = (s["2020-06"] / s["2020-02"]) / (pr["2020-06"] / pr["2020-02"])
        for i, m in enumerate(GAP, start=1):
            s[m] = s["2020-02"] * pr[m] / pr["2020-02"] * r ** (i / 4)
    return src


def _old_core():
    """{measure: {YYYY-MM-01: 2012-base core index}}, residual from the published general index."""
    src = _old_inputs()
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
    src = _old_inputs()
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


def _fetch_items():
    """All 2024-base rows (all-India, combined). Keeps the rows already downloaded (the newest raw
    snapshot) and fetches only the last two stored months onwards (provisional to final revisions),
    plus any new months. When a new month appears, refetches the full history once."""
    import datetime as dt
    snaps = sorted(RAWDIR.glob("M*.json.gz")) if RAWDIR.exists() else []  # by release code (M2026-09_...)
    cached = json.loads(gzip.decompress(snaps[-1].read_bytes())) if snaps else []
    months = sorted({_month(r) for r in cached})
    if len(months) < 12:
        years = list(range(FIRST_YEAR, dt.date.today().year + 1))
        rows, _ = mospi.cpi("Current", years=years, state_code=1, sector_code=3, max_pages=600)
        return rows
    start = months[-2]
    today = dt.date.today()
    want, d = [], start
    while d <= f"{today.year}-{today.month:02d}-01":
        want.append(d)
        d = _shift_month(d, 1)
    fresh = []
    for y in sorted({m[:4] for m in want}):
        codes = ",".join(str(int(m[5:7])) for m in want if m[:4] == y)
        part, _ = mospi.cpi("Current", years=[y], month_code=codes, state_code=1, sector_code=3, max_pages=100)
        fresh.extend(part)
    got = {_month(r) for r in fresh}
    if got and max(got) > months[-1]:
        # A new month is out: refetch everything, so revisions MoSPI ships with a release
        # to any earlier month are picked up (once a month, ~5 minutes).
        print("in_cpi_core: new month, full refetch", flush=True)
        years = list(range(FIRST_YEAR, today.year + 1))
        rows, _ = mospi.cpi("Current", years=years, state_code=1, sector_code=3, max_pages=600)
        return rows
    return [r for r in cached if _month(r) not in got] + fresh


def _contrib_linked(rows, weights, headline):
    """Chain-linked contributions (pp) to the spliced headline y/y (chart 1), Jan 2015 on.

    2012 basket to Dec 2024 and 2024 basket from Jan 2026, as in the within-base version. Months in 2025
    compare a 2024 price on the old basket with a 2025 price on the new one, so each component's contribution
    is split at the 2025 link (annual average): w_old x (old 2025 average - old a year earlier) / old headline
    a year earlier, plus the same on the new basket from the 2025 average to the month, scaled by the old
    headline's change to the link (the decomposition used for annually chain-linked HICP contributions).
    The total is the spliced headline y/y; CPI excluding food and fuel is the residual."""
    src = _old_inputs()
    w = OLD_W
    old = {k: {f"{m}-01": v for m, v in src[k].items()} for k in ("general", "food_bev", "fuel_light", "petrol", "diesel")}
    new = defaultdict(dict)
    for r in rows:
        if r.get("state") != "All India" or r.get("sector") != "Combined" or r.get("index") in (None, ""):
            continue
        code = r.get("code") or ("general" if r.get("division") == "CPI (General)" and not r.get("group") else None)
        if code in ("general", "01", "04.5", "07.2.2"):
            new[code][_month(r)] = float(r["index"])
    wt = lambda prefix: sum(v for k, (_, v) in weights.items() if k.startswith(prefix))
    nw = {"01": wt("01."), "04.5": wt("04.5."), "07.2.2": wt("07.2.2.")}
    link = [f"{LINK_YEAR}-{i:02d}-01" for i in range(1, 13)]
    avg = lambda s: sum(s[m] for m in link) / 12 if all(m in s for m in link) else None
    oa = {k: avg(v) for k, v in old.items()}
    na = {k: avg(v) for k, v in new.items()}
    within_old, within_new = _contrib_old(), _contrib_new(rows, weights)
    out = {}
    for m, h in headline.items():
        if m < "2015-01-01" or h is None:
            continue
        p = _prev_year(m)
        if m < f"{LINK_YEAR}-01-01":
            v = within_old.get(m)
            if not v:
                continue
            food, fuel, basis = v["food"], v["fuel"], "2012 basket"
        elif m < f"{int(LINK_YEAR) + 1}-01-01":
            hp = old["general"].get(p)
            need_old = [old[k].get(p) for k in ("food_bev", "fuel_light", "petrol", "diesel")]
            if not hp or None in need_old or None in oa.values() or None in na.values() or any(m not in new[c] for c in nw):
                continue
            b = oa["general"] / hp
            food = (w["food_bev"] * (oa["food_bev"] - old["food_bev"][p]) / hp
                    + b * nw["01"] * (new["01"][m] - na["01"]) / na["general"])
            fuel = (sum(w[k] * (oa[k] - old[k][p]) for k in ("fuel_light", "petrol", "diesel")) / hp
                    + b * sum(nw[c] * (new[c][m] - na[c]) for c in ("04.5", "07.2.2")) / na["general"])
            basis = "2012 and 2024 baskets, linked over 2025"
        else:
            v = within_new.get(m)
            if not v:
                continue
            food, fuel, basis = v["food"], v["fuel"], "2024 basket"
        out[m] = {"food": food, "fuel": fuel, "core": h - food - fuel, "cpi": h, "base": basis}
    return out


def _shift_month(d, n):
    y, m = int(d[:4]), int(d[5:7]) - 1 + n
    return f"{y + m // 12}-{m % 12 + 1:02d}-01"


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
    snaps = sorted(RAWDIR.glob("M*.json.gz")) if RAWDIR.exists() else []
    if from_file:
        rows = json.loads(gzip.decompress(open(from_file, "rb").read()))
    elif snaps and trigger and trigger == state.get("headline_fingerprint"):
        rows = json.loads(gzip.decompress(snaps[-1].read_bytes()))  # only the calculation changed: no fetch
    else:
        rows = _fetch_items()

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
        out[key]["basis"] = {m: ("2024 base" if m >= f"{LINK_YEAR}-01-01" else
                                 "2012 base, linked; items imputed from prices" if m[:7] in GAP else "2012 base, linked")
                             for m in linked}
        out[key]["yoy"] = {m: (linked[m] / linked[_prev_year(m)] - 1) * 100 for m in linked if _prev_year(m) in linked}
        # The Mar-May 2020 imputation must be in place: no gap in the index or the y/y from Jan 2015.
        for m in [f"{y}-{mm}-01" for y in ("2020", "2021") for mm in ("03", "04", "05")]:
            if m not in out[key]["yoy"]:
                errors.append(f"{key} {m[:7]}: y/y missing (Mar-May 2020 imputation not applied)")
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

    # Chain-linked version: totals are the spliced headline y/y from in_cpi_mospi (chart 1).
    headline = {}
    for r in csv.DictReader(open(DATA / "in" / "cpi" / "in_cpi.csv")):
        if r["series"] == "combined" and r["yoy"] not in ("", None):
            headline[r["date"]] = float(r["yoy"])
    linked = _contrib_linked(rows, weights, headline)
    for m, v in linked.items():
        if not -5 < v["core"] < 10:
            raise CheckFailed([f"{m}: linked core contribution {v['core']:.2f}pp out of range"])
    with open(OUT / "in_cpi_contrib_linked.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "cpi_yoy", "food", "fuel", "core", "basis"])
        for m in sorted(linked):
            v = linked[m]
            w.writerow([m, round(v["cpi"], 2), round(v["food"], 3), round(v["fuel"], 3), round(v["core"], 3), v["base"]])

    # Item contributions to CPI y/y (2024 basket, from Jan 2026): weight x 12-month change in the item index
    # / headline index a year earlier. MoSPI's index is a weighted average of item indices, so they add up to
    # the headline y/y; checked to 0.02pp. y/y is MoSPI's published item inflation.
    iidx, iyoy, gen = defaultdict(dict), defaultdict(dict), {}
    for r in rows:
        if r.get("state") != "All India" or r.get("sector") != "Combined" or r.get("index") in (None, ""):
            continue
        if r.get("item"):
            iidx[r["code"]][_month(r)] = float(r["index"])
            if r.get("inflation") not in (None, ""):
                iyoy[r["code"]][_month(r)] = float(r["inflation"])
        elif r.get("division") == "CPI (General)" and not r.get("group"):
            gen[_month(r)] = float(r["index"])
    item_rows = []
    for m in sorted(gen):
        p = _prev_year(m)
        if p not in gen:
            continue
        tot = 0.0
        for code, (name, wt) in weights.items():
            s_ = iidx.get(code, {})
            if m not in s_ or p not in s_:
                continue
            c = wt * (s_[m] - s_[p]) / gen[p]
            tot += c
            item_rows.append([m, code, name, round(wt, 4), iyoy[code].get(m, ""), round(c, 4)])
        if abs(tot - (gen[m] / gen[p] - 1) * 100) > 0.02:
            raise CheckFailed([f"{m}: item contributions sum to {tot:.3f}, headline y/y {(gen[m] / gen[p] - 1) * 100:.3f}"])
    with open(OUT / "in_cpi_items.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "code", "name", "weight", "yoy", "contrib_yoy"])
        w.writerows(item_rows)

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
