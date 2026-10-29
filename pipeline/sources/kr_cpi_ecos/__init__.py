"""South Korea CPI: Ministry of Data and Statistics (Statistics Korea until Oct 2025), 2020 = 100 with 2022 weights, via the Bank of Korea's ECOS API.

Tables 901Y009 (CPI by expenditure, 458 items) and 901Y010 (special classification: goods and services
by type, fresh food, CPI excluding food and energy, excluding agricultural products and oil, living cost
index). ECOS publishes index levels only; y/y is calculated from the index (Statistics Korea derives its
published rates the same way). No seasonally adjusted CPI is published, so none is used or made here.

Calculated (Asia Decoded): contributions to all-items y/y, item contributions and a diffusion index.
The CPI is a Lowe index: since the 2022 basket was linked in at December 2022, the all-items index is
  I_t = I_L * sum_i w_i (I_i,t / B_i) / sum_i w_i (I_i,L / B_i)
with w_i the published 2022 weights (per 1,000), B_i the item's 2022 average index and L = Dec 2022.
That identity is checked against the published all-items index every month; contributions use it,
for months whose year-earlier month is on the same basket (Dec 2023 on).

Series store: raw/kr/ecos/store.json.gz (see core/ecos.py). Each run checks the latest headline month
(one API call); when a new month appears, every item of both tables is re-fetched for the latest three
months.
"""
import csv
import hashlib
import json
from pathlib import Path

from core import ecos
from core.common import DATA, CheckFailed, read_json, write_long, write_release

NAME = "kr_cpi_ecos"
DESCRIPTION = "South Korea CPI (Ministry of Data and Statistics via Bank of Korea ECOS), with contributions and diffusion"
OUT = DATA / "kr" / "cpi"
HERE = Path(__file__).resolve().parent
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
UNIT = "2020=100"
# Basket currently in use: linked in at LINK, weights from BASE_YEAR expenditure (price reference: that year's average).
LINK, BASE_YEAR = "202212", "2022"
# Published all-items y/y (Statistics Korea releases) used as a check on the calculated rates.
PUBLISHED = {"202604": 2.6, "202605": 3.1, "202608": 3.1, "202609": 2.9}
PUBLISHED_CORE = {"202608": 3.4, "202609": 2.8}  # excl. food and energy

DIVS = {"A": "Food and non-alcoholic beverages", "B": "Alcoholic beverages and tobacco", "C": "Clothing and footwear",
        "D": "Housing, water, electricity and fuels", "E": "Furnishings and household goods", "F": "Health",
        "G": "Transport", "H": "Communication", "I": "Recreation and culture", "J": "Education",
        "K": "Restaurants and hotels", "L": "Miscellaneous goods and services"}
# key, table, code, label, group
SERIES = [
    ("all", "901Y009", "0", "All items", "headline"),
    ("ex_food_energy", "901Y010", "DB", "Excl. food and energy", "headline"),
    ("ex_agri_oil", "901Y010", "QB", "Excl. agricultural products and oil", "headline"),
    ("living", "901Y010", "110", "Living cost index", "headline"),
    ("goods", "901Y010", "21", "Goods", "goods_services"),
    ("agri", "901Y010", "211", "Agricultural, livestock and fishery products", "goods_services"),
    ("industrial", "901Y010", "212", "Industrial products", "goods_services"),
    ("processed_food", "901Y010", "2121", "Processed food", "drivers"),
    ("petroleum", "901Y010", "2125", "Petroleum products", "drivers"),
    ("utilities", "901Y010", "213", "Electricity, gas and water", "drivers"),
    ("services", "901Y010", "22", "Services", "goods_services"),
    ("rent", "901Y010", "221", "Housing rent", "goods_services"),
    ("public", "901Y010", "222", "Public services", "goods_services"),
    ("personal", "901Y010", "223", "Personal services", "goods_services"),
    ("eating_out", "901Y010", "2231", "Eating out", "goods_services"),
    ("personal_ex_eating_out", "901Y010", "2239", "Personal services excl. eating out", "goods_services"),
    ("fresh", "901Y010", "10", "Fresh food", "drivers"),
    ("ex_fresh", "901Y010", "20", "Excl. fresh food", "headline"),
] + [("div_" + c, "901Y009", c, lab, "divisions") for c, lab in DIVS.items()] + [
    # published item indices (item history in the store from Jan 2015)
    ("jeonse", "901Y009", "D01101", "Jeonse (lump-sum deposit rent)", "items"),
    ("monthly_rent", "901Y009", "D01102", "Monthly rent", "items"),
    ("electricity", "901Y009", "D05101", "Electricity", "items"),
    ("city_gas", "901Y009", "D05201", "City gas", "items"),
    ("petrol", "901Y009", "G02101", "Petrol", "items"),
    ("diesel", "901Y009", "G02102", "Diesel", "items"),
    ("district_heating", "901Y009", "D05302", "District heating", "items"),
]
# Energy as the ministry defines it (release appendix: "에너지(9개): 석유류, 전기료, 도시가스, 지역난방비"); no index is
# published, so it is calculated from the nine item indices at their published 2022 weights (75.8 per 1,000).
PETROLEUM_ITEMS = ["G02101", "G02102", "G02103", "D05301", "D05202", "D05303"]  # petrol, diesel, vehicle LPG, kerosene, cooking LPG, butane
ENERGY_ITEMS = PETROLEUM_ITEMS + ["D05101", "D05201", "D05302"]  # + electricity, city gas, district heating
REQUIRED = ["all", "ex_food_energy", "ex_agri_oil", "goods", "services", "fresh", "petroleum", "utilities"]
# Contribution parts (special classification); industrial excl. petroleum = 212 minus 2125.
PARTS = [("agri", "Agricultural, livestock and fishery products"), ("industrial_ex_oil", "Industrial products excl. petroleum"),
         ("petroleum", "Petroleum products"), ("utilities", "Electricity, gas and water"), ("services", "Services")]
PART_CODES = {"agri": "211", "industrial": "212", "petroleum": "2125", "utilities": "213", "services": "22"}


def _ym(d):
    return d[:4] + d[5:7]


def _date(ym):
    return f"{ym[:4]}-{ym[4:]}-01"


def _shift(ym, k):
    y, m = int(ym[:4]), int(ym[4:]) - 1 + k
    return f"{y + m // 12}{m % 12 + 1:02d}"


def _months(a, b):
    out = []
    while a <= b:
        out.append(a)
        a = _shift(a, 1)
    return out


def _weights(store, table):
    """Published weights (per 1,000) by item code: from the latest month's rows, else the item list."""
    out = {}
    for code, s in store.get(table, {}).items():
        if s.get("wgt"):
            out[code] = s["wgt"][max(s["wgt"])]
    for r in (store.get("_items", {}).get(table) or []):
        if r.get("ITEM_CODE") not in out and r.get("WEIGHT") not in (None, ""):
            try:
                out[r["ITEM_CODE"]] = float(r["WEIGHT"])
            except ValueError:
                pass
    return out


def _refresh(store):
    """Fetch new months. Returns the list of months re-fetched (empty if nothing new)."""
    cpi = store["901Y009"]["0"]["values"]
    have = max(cpi)
    now = ecos.series("901Y009", "0", _shift(have, -2), _shift(have, 3))
    newest = max([r["TIME"] for r in now] + [have])
    if newest == have and all(cpi.get(r["TIME"]) == float(r["DATA_VALUE"]) for r in now):
        return []
    months = _months(_shift(newest, -2), newest)
    for ym in months:
        for table in ("901Y009", "901Y010"):
            ecos.put(store, table, ecos.month_all(table, ym))
    return months


def _yoy(vals, ym, nd=1):
    a, b = vals.get(ym), vals.get(_shift(ym, -12))
    return round((a / b - 1) * 100, nd) if a and b else None


def _lowe(store, w, codes, table, latest, errors, label):
    """Coefficients c_i with I_t = sum_i c_i I_i,t on the current basket; checks the identity."""
    tot = store["901Y009"]["0"]["values"]
    base = [ym for ym in _months(BASE_YEAR + "01", BASE_YEAR + "12")]
    c = {}
    for k in codes:
        v = store[table][k]["values"]
        if any(m not in v for m in base + [LINK]):
            errors.append(f"{label}: {k} missing in {BASE_YEAR} or {LINK}")
            return {}
        c[k] = w[k] / (sum(v[m] for m in base) / 12)
    den = sum(c[k] * store[table][k]["values"][LINK] for k in codes)
    c = {k: x * tot[LINK] / den for k, x in c.items()}
    worst = 0
    for ym in _months(LINK, latest):
        est = sum(c[k] * store[table][k]["values"].get(ym, float("nan")) for k in codes)
        worst = max(worst, abs(est - tot[ym]))
    if not worst < 0.03:
        errors.append(f"{label}: weighted indices miss the published all-items index by {worst:.3f} (limit 0.03)")
    return c, worst


def _aggregate(store, w, codes, latest):
    """Lowe aggregate of item indices on the current basket: sum w_i I_i,t / B_i, set to 100 at LINK (B_i: 2022 average)."""
    t = store["901Y009"]
    base = _months(BASE_YEAR + "01", BASE_YEAR + "12")
    b = {k: sum(t[k]["values"][m] for m in base) / 12 for k in codes}
    den = sum(w[k] * t[k]["values"][LINK] / b[k] for k in codes)
    return {ym: sum(w[k] * t[k]["values"][ym] / b[k] for k in codes) / den * 100
            for ym in _months(LINK, latest) if all(ym in t[k]["values"] for k in codes)}


def _write_csv(path, cols, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r.get(c) is None else r[c] for c in cols])


def update(**_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    store = ecos.load_store()
    if not store.get("901Y009", {}).get("0"):
        raise CheckFailed(["ECOS store is empty: run tools/ecos_backfill.py"])
    fetched = _refresh(store)
    errors = []
    unit = store["901Y009"]["0"].get("unit")
    if unit != UNIT:
        errors.append(f"ACTION: CPI unit is now '{unit}' (was {UNIT}): Statistics Korea has rebased the CPI; "
                      "update LINK, BASE_YEAR and the series codes in kr_cpi_ecos")
    tot = store["901Y009"]["0"]["values"]
    latest = max(tot)
    if state.get("latest_month") and _date(latest) < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one already stored ({state['latest_month']})")
    S = {}
    for key, table, code, *_r in SERIES:
        s = store.get(table, {}).get(code)
        S[key] = s["values"] if s else {}
        if key in REQUIRED and latest not in S[key]:
            errors.append(f"{key} ({table} {code}) missing for {latest}")
    for ym, pub in PUBLISHED.items():
        got = _yoy(tot, ym)
        if got is not None and abs(got - pub) > 0.051:
            errors.append(f"all-items y/y {ym}: calculated {got}, published {pub}")
    for ym, pub in PUBLISHED_CORE.items():
        got = _yoy(S["ex_food_energy"], ym)
        if got is not None and abs(got - pub) > 0.051:
            errors.append(f"excl. food and energy y/y {ym}: calculated {got}, published {pub}")
    # Contributions of the special-classification parts
    w10 = _weights(store, "901Y010")
    parts_codes = ["211", "212", "213", "22"]
    missing_w = [k for k in parts_codes + ["2125"] if k not in w10]
    if missing_w:
        errors.append(f"weights missing for {missing_w}")
    contrib, fit = [], {}
    if not missing_w:
        r = _lowe(store, w10, parts_codes, "901Y010", latest, errors, "goods and services parts")
        if r:
            c, fit["parts"] = r
            # petroleum shares the industrial products' scaling
            c["2125"] = c["212"] * (w10["2125"] / w10["212"]) * (
                (sum(store["901Y010"]["212"]["values"][m] for m in _months(BASE_YEAR + "01", BASE_YEAR + "12")))
                / (sum(store["901Y010"]["2125"]["values"][m] for m in _months(BASE_YEAR + "01", BASE_YEAR + "12"))))
            for ym in _months(_shift(LINK, 12), latest):
                prev = tot[_shift(ym, -12)]
                part = {}
                for k, code in PART_CODES.items():
                    v = store["901Y010"][code]["values"]
                    part[k] = c[code] * (v[ym] - v[_shift(ym, -12)]) / prev * 100
                part["industrial_ex_oil"] = part["industrial"] - part["petroleum"]
                ally = (tot[ym] / prev - 1) * 100
                gap = ally - sum(part[k] for k, _l in PARTS)
                if abs(gap) > 0.05:
                    errors.append(f"contributions {ym}: parts sum to {ally - gap:.2f}, all items {ally:.2f}")
                contrib.append({"date": _date(ym), "series": "all", "label": "All items", "order": 0, "contrib_yoy": round(ally, 2)})
                for i, (k, lab) in enumerate(PARTS, 1):
                    contrib.append({"date": _date(ym), "series": k, "label": lab, "order": i, "contrib_yoy": round(part[k], 2)})
    # Items: weights, contributions (latest 12 months), diffusion
    names = json.loads((HERE / "item_names_en.json").read_text())
    items9 = store["901Y009"]
    leaves = sorted(k for k in items9 if len(k) == 6)
    w9 = _weights(store, "901Y009")
    if len(leaves) < 400:
        errors.append(f"only {len(leaves)} CPI items in the store")
    nolabel = [k for k in leaves if k not in names]
    if nolabel:
        errors.append(f"items without an English name: {nolabel[:10]} (add to item_names_en.json)")
    wsum = sum(w9.get(k, 0) for k in leaves)
    if abs(wsum - 1000) > 1:
        errors.append(f"item weights sum to {wsum:.1f}, not 1000")
    items_rows = []
    r = _lowe(store, w9, [k for k in leaves if k in w9], "901Y009", latest, errors, "items")
    if r:
        ci, fit["items"] = r
        for ym in _months(_shift(latest, -11), latest):
            prev = tot.get(_shift(ym, -12))
            for k in leaves:
                v = items9[k]["values"]
                if ym not in v:
                    continue
                cy = None
                if _shift(ym, -12) >= LINK and _shift(ym, -12) in v and k in ci:
                    cy = round(ci[k] * (v[ym] - v[_shift(ym, -12)]) / prev * 100, 4)
                items_rows.append({"date": _date(ym), "code": k, "name": names.get(k, items9[k]["name"]),
                                   "weight": w9.get(k), "index": v[ym], "yoy": _yoy(v, ym), "contrib_yoy": cy})
    diff = []
    for ym in _months("201601", latest):
        up = down = flat = 0
        for k in leaves:
            y = _yoy(items9[k]["values"], ym)
            if y is None:
                continue
            if y > 0:
                up += 1
            elif y < 0:
                down += 1
            else:
                flat += 1
        n = up + down + flat
        if n:
            diff.append({"date": _date(ym), "items": n, "rising": up, "falling": down, "unchanged": flat,
                         "share_rising": round(up / n * 100, 1), "share_falling": round(down / n * 100, 1),
                         "diffusion": round((up - down) / n * 100, 1)})
    # Energy (calculated). Check: the same method on the six petroleum items reproduces the published petroleum
    # products index (901Y010 2125) y/y within 0.15pp every month from Dec 2023.
    energy = {}
    miss = [k for k in ENERGY_ITEMS if k not in w9 or k not in items9]
    if miss:
        errors.append(f"energy items missing: {miss}")
    else:
        ew = sum(w9[k] for k in ENERGY_ITEMS)
        if abs(ew + w9.get("A", 0) + _weights(store, "901Y010").get("DB", 0) - 1000) > 0.15:
            errors.append(f"energy weight {ew:.1f} + food {w9.get('A')} + core {_weights(store, '901Y010').get('DB')} != 1000")
        pet = _aggregate(store, w9, PETROLEUM_ITEMS, latest)
        pub = store["901Y010"]["2125"]["values"]
        for ym in _months(_shift(LINK, 12), latest):
            a, b = _yoy(pet, ym), _yoy(pub, ym)
            if a is None or b is None or abs(a - b) > 0.15:
                errors.append(f"petroleum check {ym}: items give {a}, published {b}")
        energy = {ym: round(v, 3) for ym, v in _aggregate(store, w9, ENERGY_ITEMS, latest).items()}
    if errors:
        raise CheckFailed(errors)

    rows = []
    for o, (key, table, code, lab, grp) in enumerate(SERIES):
        v = S[key]
        for ym in sorted(v):
            rows.append({"date": _date(ym), "area": "national", "series": key, "label": lab, "group": grp, "order": o,
                         "index": v[ym], "yoy": _yoy(v, ym)})
    for ym in sorted(energy):
        rows.append({"date": _date(ym), "area": "national", "series": "energy", "label": "Energy (calculated)", "group": "headline",
                     "order": len(SERIES), "index": energy[ym], "yoy": _yoy(energy, ym) if _shift(ym, -12) >= LINK else None})
    rows.sort(key=lambda r: (r["date"], r["order"]))
    blob = json.dumps([rows[-2000:], contrib[-120:], diff[-24:]], sort_keys=True).encode()
    fingerprint = hashlib.sha256(blob).hexdigest()[:16]
    code = f"C{latest[:4]}-{latest[4:]}"
    if fingerprint == state.get("fingerprint") and not fetched:
        ecos.save_store(store)
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    ecos.save_store(store)
    _write_csv(OUT / "kr_cpi.csv", ["date", "area", "series", "label", "group", "order", "index", "yoy"], rows)
    # Published 2022 basket weights (per 1,000) of every series in kr_cpi.csv: ECOS's weight for that item
    wts = {"901Y009": _weights(store, "901Y009"), "901Y010": w10}
    _write_csv(OUT / "kr_cpi_series_weights.csv", ["series", "label", "weight"],
               [{"series": key, "label": lab, "weight": wts[table].get(code)} for key, table, code, lab, _g in SERIES
                if wts[table].get(code) is not None]
               + [{"series": "energy", "label": "Energy (sum of the nine items' published weights)",
                   "weight": round(sum(w9[k] for k in ENERGY_ITEMS), 1)}])
    _write_csv(OUT / "kr_cpi_contrib.csv", ["date", "series", "label", "order", "contrib_yoy"], contrib)
    _write_csv(OUT / "kr_cpi_items.csv", ["date", "code", "name", "weight", "index", "yoy", "contrib_yoy"], items_rows)
    _write_csv(OUT / "kr_cpi_diffusion.csv", ["date", "items", "rising", "falling", "unchanged", "share_rising",
                                              "share_falling", "diffusion"], diff)
    label = f"{MONTHS[int(latest[4:]) - 1]} {latest[:4]}"

    def long_rows():
        for r in rows:
            for meas, unit in (("index", "index, 2020 = 100"), ("yoy", "%")):
                yield {"country": "KR", "indicator": "cpi", "series": r["series"], "label": r["label"], "measure": meas,
                       "area": "national", "freq": "M", "date": r["date"], "value": r[meas], "unit": unit,
                       "source": "Ministry of Data and Statistics (via Bank of Korea ECOS)", "release": code}
        for r in contrib:
            yield {"country": "KR", "indicator": "cpi", "series": "contrib_" + r["series"], "label": r["label"],
                   "measure": "contribution to y/y", "area": "national", "freq": "M", "date": r["date"],
                   "value": r["contrib_yoy"], "unit": "ppt", "source": "Asia Decoded calculations from Ministry of Data and Statistics", "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    release = {"code": code, "label": label, "latest_month": _date(latest),
               "table": "ECOS 901Y009, 901Y010 (Ministry of Data and Statistics CPI, 2020 = 100, 2022 weights)"}
    warnings = []
    write_release(OUT, release, warnings, len(rows), {"fingerprint": fingerprint, "long_rows": nlong,
                  "contrib_rows": len(contrib), "diffusion_items": diff[-1]["items"] if diff else None,
                  "fit_max_gap": {k: round(v, 4) for k, v in fit.items()}, "ecos_calls": ecos.CALLS["n"],
                  "refetched": fetched})
    return {"updated": True, "code": code, "summary": f"{label}: {len(rows)} rows, {len(contrib)} contribution rows, "
            f"{ecos.CALLS['n']} ECOS calls", "warnings": warnings}
