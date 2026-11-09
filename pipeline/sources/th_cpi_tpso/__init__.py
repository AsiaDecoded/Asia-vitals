"""Thailand CPI: Trade Policy and Strategy Office (TPSO), Ministry of Commerce, Open API (index-api.tpso.go.th).

Everything is as published by TPSO; nothing is calculated here.
  - General CPI (Cpig), 2023 = 100 (base year BE 2566, basket used from January 2025), TPSO's series linked back
    to January 1976: index, y/y and m/m as published, for all 194 published series (8 groups and their sub-groups,
    plus TPSO's special aggregates: core CPI, fresh food, energy, CPI excluding food, beverages and energy,
    CPI excluding fresh food, excluding energy, excluding gasoline and diesel).
    Whole country (type TG) from 1976; Bangkok and vicinity (type 10) from 1990; the four regions
    (CC, NN, EE, SS) for the latest 25 months.
  - Low-income households CPI (Cpil, type TL), 2023 = 100, from 1990.
  - Weights: TPSO's published 2023-basket expenditure shares (% of CPI), from the rebasing note
    "การปรับปรุงดัชนีราคาผู้บริโภค ปีฐาน 2566" (Feb 2025), in weights_2566.csv: the eight groups, core,
    fresh food and energy. TPSO publishes no weights below group level.
  - English labels for TPSO's Thai series names: names.csv (labels only).
TPSO publishes no seasonally adjusted CPI.

New data is detected from the MasterData call (one call: latest month of the 2023 base). A new month re-fetches
the latest three months of every set; a missing set is backfilled. Store of every month fetched (rows as the API
returned them): raw/th/cpi_tpso/store.json.gz; each run's new responses: raw/th/cpi_tpso/<YYYY-MM>/.
"""
import csv
import gzip
import hashlib
import json
from pathlib import Path

from core import tpso
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "th_cpi_tpso"
DESCRIPTION = "Thailand CPI (TPSO Open API, 2023 = 100): headline, core, fresh food, energy, groups, regions, low income"
OUT = DATA / "th" / "cpi"
RAWDIR = RAW / "th" / "cpi_tpso"
STORE = RAWDIR / "store.json.gz"
HERE = Path(__file__).resolve().parent
BASE_BE = 2566
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# (family, type): first month to keep ("" = the API's first month), or a number of latest months
SETS = {
    ("Cpig", "TG"): "",
    ("Cpig", "10"): "1990-01",
    ("Cpil", "TL"): "1990-01",
    ("Cpig", "CC"): 25, ("Cpig", "NN"): 25, ("Cpig", "EE"): 25, ("Cpig", "SS"): 25,
}
AREA = {("Cpig", "TG"): "national", ("Cpig", "10"): "bangkok", ("Cpil", "TL"): "lowincome"}
REGIONS = [("TG", "Thailand"), ("10", "Bangkok and vicinity"), ("CC", "Central"), ("NN", "North"),
           ("EE", "Northeast"), ("SS", "South")]
GROUPS = ["10000", "20000", "30000", "40000", "50000", "60000", "70000"]
# key, code, group (national series)
SERIES = [
    ("all", "00000", "headline"), ("core", "93000", "headline"),
    ("ex_food_energy", "81000", "measure"), ("core_ex_rent", "94000", "measure"),
    ("ex_fresh_food", "97000", "measure"), ("ex_energy", "98000", "measure"), ("ex_fuel", "95200", "measure"),
    ("fresh_food_energy", "90000", "component"), ("fresh_food", "91000", "component"), ("energy", "92000", "component"),
    ("fuel", "95100", "component"), ("food_ex_fresh", "82000", "component"),
    ("food", "10000", "group"), ("nonfood", "80000", "group"), ("apparel", "20000", "group"),
    ("housing", "30000", "group"), ("medical", "40000", "group"), ("transport", "50000", "group"),
    ("recreation", "60000", "group"), ("tobacco", "70000", "group"),
    ("food_home", "11000", "driver"), ("rice", "11110", "driver"), ("meat", "11210", "driver"),
    ("poultry", "11220", "driver"), ("fish", "11230", "driver"), ("eggs", "11310", "driver"),
    ("vegetables", "11411", "driver"), ("fruit", "11421", "driver"), ("oils", "11521", "driver"),
    ("prepared_food", "12000", "driver"), ("food_away", "12200", "driver"),
    ("rent", "31100", "driver"), ("electricity", "32100", "driver"), ("household_fuel", "32200", "driver"),
    ("water", "32300", "driver"), ("medical_care", "41000", "driver"), ("personal_care", "42000", "driver"),
    ("public_transport", "51000", "driver"), ("vehicles", "52110", "driver"), ("vehicle_fuel", "52200", "driver"),
    ("communication", "54000", "driver"), ("education", "62000", "driver"),
]
AREA_SERIES = {"bangkok": ["all", "core", "food", "fresh_food", "energy"], "lowincome": ["all", "core", "food"]}
YOY_TOL = 0.06  # published y/y vs the published index (2 decimals), 2023 base, Jan 2024 on


def _names():
    return {r["code"]: r["name_en"] for r in csv.DictReader(open(HERE / "names.csv", encoding="utf-8"))}


def _weights():
    return {r["code"]: float(r["weight"]) for r in csv.DictReader(open(HERE / "weights_2566.csv", encoding="utf-8"))}


def _depth(code):
    return 0 if code == "00000" else len(code.rstrip("0"))


def _shift(ym, k):
    y, m = int(ym[:4]), int(ym[5:7]) - k
    while m < 1:
        y, m = y - 1, m + 12
    return f"{y}-{m:02d}"


def load_store():
    if STORE.exists():
        return json.load(gzip.open(STORE, "rt", encoding="utf-8"))
    return {}


def save_store(store):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(STORE, "wt", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, separators=(",", ":"))


def fetch(store, latest, masters, force=False):
    """Fetch what is missing or due; returns {set key: {ym: rows}} of new responses."""
    new = {}
    for (fam, typ), start in SETS.items():
        key = f"{fam}:{typ}"
        have = store.get(key, {})
        if isinstance(start, int):
            want = tpso.month_range(_shift(latest, start - 1), latest)
        else:
            first = start or tpso.first_period(masters[fam], BASE_BE)
            want = tpso.month_range(first, latest)
        recent = set(tpso.month_range(_shift(latest, 2), latest))
        todo = [ym for ym in want if ym not in have or ym in recent or force]
        if not todo:
            continue
        got = tpso.months(fam, typ, BASE_BE, todo)
        new[key] = got
        have.update(got)
        # keep only the wanted window for the regional sets
        store[key] = {ym: have[ym] for ym in sorted(have) if ym in set(want)}
    return new


def _num(v):
    return None if v is None else float(v)


def build(store, latest):
    names, weights = _names(), _weights()
    by = {}  # (set key, code, ym) -> (index, yoy, mom, created)
    created = {}
    for key, months in store.items():
        for ym, rows in months.items():
            for r in rows:
                by[(key, r["commodityCode"], ym)] = (_num(r.get("index")), _num(r.get("changeYear")),
                                                     _num(r.get("change")))
                if key == "Cpig:TG" and r["commodityCode"] == "00000":
                    created[ym] = r.get("createdAt")
    series = []
    order = 0
    keymap = {k: c for k, c, _g in SERIES}

    def add(area, setkey, key, code, group):
        nonlocal order
        lab = names.get(code, code)
        if area == "lowincome":
            lab = "Low-income households: " + lab[0].lower() + lab[1:] if code != "00000" else "Low-income households"
        elif area == "bangkok":
            lab = "Bangkok and vicinity: " + lab[0].lower() + lab[1:] if code != "00000" else "Bangkok and vicinity"
        for ym in sorted(store.get(setkey, {})):
            v = by.get((setkey, code, ym))
            if not v or (v[0] is None and v[1] is None):
                continue
            series.append({"date": ym + "-01", "area": area, "series": key, "code": code, "label": lab,
                           "group": group, "order": order, "index": v[0], "yoy": v[1], "mom": v[2],
                           "weight": weights.get(code) if area == "national" else None})
        order += 1

    for key, code, group in SERIES:
        add("national", "Cpig:TG", key, code, group)
    for area, setkey in (("bangkok", "Cpig:10"), ("lowincome", "Cpil:TL")):
        for key in AREA_SERIES[area]:
            add(area, setkey, key, keymap[key], "area")

    # every published series, whole country, latest 25 months
    tg = store.get("Cpig:TG", {})
    # series of the latest two months: TPSO sometimes loads a month in parts (Oct 2026: 175 of 194 series on 6 Nov)
    codes = sorted({r["commodityCode"] for ym in (_shift(latest, 1), latest) for r in tg.get(ym, [])})
    latest_codes = {r["commodityCode"] for r in tg.get(latest, [])}
    first = _shift(latest, 24)
    items = []
    for ym in sorted(tg):
        if ym < first:
            continue
        for c in codes:
            v = by.get(("Cpig:TG", c, ym))
            if v:
                items.append({"date": ym + "-01", "code": c, "name": names.get(c, c), "level": _depth(c),
                              "order": codes.index(c), "index": v[0], "yoy": v[1], "mom": v[2]})
    weight_rows = [{"code": c, "name": names.get(c, c), "level": _depth(c), "order": i, "weight": weights.get(c)}
                   for i, c in enumerate(codes)]
    # regions: all-items y/y, latest 25 months
    reg = []
    for i, (typ, lab) in enumerate(REGIONS):
        for ym, rows in store.get(f"Cpig:{typ}", {}).items():
            if ym < first:
                continue
            v = by.get((f"Cpig:{typ}", "00000", ym))
            if v and v[1] is not None:
                reg.append({"date": ym + "-01", "region": lab, "type": typ, "order": i, "yoy": v[1], "index": v[0]})
    series.sort(key=lambda r: (r["date"], r["area"], r["order"]))
    items.sort(key=lambda r: (r["date"], r["order"]))
    reg.sort(key=lambda r: (r["date"], r["order"]))
    return {"series": series, "items": items, "weights": weight_rows, "regions": reg, "by": by,
            "created": created, "codes": codes, "latest_codes": latest_codes, "weights_map": weights}


def check(b, state, latest):
    errors, warnings = [], []
    if state.get("latest_month") and latest + "-01" < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one already stored ({state['latest_month']})")
    have = {(r["area"], r["series"]) for r in b["series"] if r["date"] == latest + "-01" and r["yoy"] is not None}
    need = [("national", k) for k, _c, g in SERIES if g in ("headline", "group")] + \
        [("national", "fresh_food"), ("national", "energy"), ("national", "ex_food_energy")] + \
        [("bangkok", "all"), ("bangkok", "core")]
    for a, k in need:
        if (a, k) not in have:
            errors.append(f"{a} {k}: no y/y for {latest}")
    # TPSO may load a month in parts: written as far as published, flagged, and re-fetched on every run until complete
    if ("lowincome", "all") not in have:
        warnings.append(f"PARTIAL: low-income CPI not yet published for {latest}")
    n = len(b["latest_codes"])
    if n < 150:
        errors.append(f"only {n} series for {latest} (194 expected)")
    elif n < 190:
        missing = sorted(set(b["codes"]) - b["latest_codes"])
        warnings.append(f"PARTIAL: {n} of {len(b['codes'])} series published for {latest}; missing {missing}")
    if {r["region"] for r in b["regions"] if r["date"] == latest + "-01"} != {lab for _t, lab in REGIONS}:
        errors.append(f"regions missing for {latest}")
    # no gaps in headline y/y from its first month
    dates = sorted(r["date"][:7] for r in b["series"] if r["area"] == "national" and r["series"] == "all"
                   and r["yoy"] is not None)
    gaps = [ym for ym in tpso.month_range(dates[0], latest) if ym not in set(dates)]
    if gaps:
        errors.append(f"headline y/y missing for {len(gaps)} months, e.g. {gaps[:5]}")
    # published y/y vs published index on the 2023 base
    by = b["by"]
    bad = []
    for (key, code, ym), (ix, yy, _mm) in by.items():
        if key != "Cpig:TG" or ym < "2024-01" or yy is None or ix is None:
            continue
        prev = by.get((key, code, f"{int(ym[:4]) - 1}{ym[4:]}"))
        if prev and prev[0]:
            calc = (ix / prev[0] - 1) * 100
            if abs(calc - yy) > YOY_TOL:
                bad.append(f"{code} {ym}: published {yy}, index gives {calc:.2f}")
    if len(bad) > 5:
        errors.append(f"{len(bad)} published y/y rates differ from the index by more than {YOY_TOL}pp, e.g. {bad[:3]}")
    elif bad:
        warnings.append("y/y vs index: " + "; ".join(bad))
    # published weights: groups sum to 100; core + fresh food + energy = 100
    w = b["weights_map"]
    if abs(sum(w[c] for c in GROUPS) - 100) > 0.011:
        errors.append(f"group weights sum to {sum(w[c] for c in GROUPS):.2f}, not 100")
    if abs(w["93000"] + w["91000"] + w["92000"] - 100) > 0.011:
        errors.append("core, fresh food and energy weights do not sum to 100")
    # weighted group indices against the all-items index, 2023 basket (Jan 2025 on): report only
    worst = 0
    for ym in tpso.month_range("2025-01", latest):
        tot = by.get(("Cpig:TG", "00000", ym))
        parts = [by.get(("Cpig:TG", c, ym)) for c in GROUPS]
        if tot and all(parts):
            worst = max(worst, abs(sum(p[0] * w[c] for p, c in zip(parts, GROUPS)) / 100 - tot[0]))
    if worst > 0.15:
        warnings.append(f"weighted group indices miss the all-items index by up to {worst:.2f} (Jan 2025 on): "
                        "TPSO's index is not a fixed-weight average of the published group indices at these weights")
    for r in b["series"]:
        if r["index"] is not None and not 0 < r["index"] < 1000:
            errors.append(f"{r['series']} {r['date']} index {r['index']} out of range")
            break
    return errors, warnings


def _write_csv(path, rows, cols):
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f, lineterminator="\n")
        wr.writerow(cols)
        for r in rows:
            wr.writerow(["" if r.get(c) is None else r[c] for c in cols])


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    masters = {"Cpig": tpso.master("Cpig"), "Cpil": tpso.master("Cpil")}
    latest = tpso.latest_period(masters["Cpig"], BASE_BE)
    if not latest:
        raise CheckFailed([f"MasterData lists no months on base {BASE_BE}"])
    store = load_store()
    complete = all(f"{f}:{t}" in store for f, t in SETS)
    if latest + "-01" == state.get("latest_month") and complete and not state.get("partial") and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    new = fetch(store, latest, masters, force=force)
    save_store(store)  # raw responses kept even if the checks below fail, so a rerun does not refetch them
    b = build(store, latest)
    errors, warnings = check(b, state, latest)
    if errors:
        raise CheckFailed(errors)
    dest = RAWDIR / latest
    dest.mkdir(parents=True, exist_ok=True)
    for key, months in new.items():
        recent = {ym: rows for ym, rows in months.items() if ym >= _shift(latest, 2)}
        if recent:
            with gzip.open(dest / f"{key.replace(':', '_')}.json.gz", "wt", encoding="utf-8") as f:
                json.dump(recent, f, ensure_ascii=False)
    partial = any(w.startswith("PARTIAL") for w in warnings)
    code = f"C{latest}" + ("p" if partial else "")
    _write_csv(OUT / "th_cpi.csv", b["series"],
               ["date", "area", "series", "code", "label", "group", "order", "index", "yoy", "mom", "weight"])
    _write_csv(OUT / "th_cpi_items.csv", b["items"], ["date", "code", "name", "level", "order", "index", "yoy", "mom"])
    _write_csv(OUT / "th_cpi_weights.csv", b["weights"], ["code", "name", "level", "order", "weight"])
    _write_csv(OUT / "th_cpi_regions.csv", b["regions"], ["date", "region", "type", "order", "index", "yoy"])
    label = f"{MONTHS[int(latest[5:7]) - 1]} {latest[:4]}"

    def long_rows():
        for r in b["series"]:
            for meas, unit in (("index", "index, 2023 = 100"), ("yoy", "%"), ("mom", "% m/m")):
                yield {"country": "TH", "indicator": "cpi", "series": r["series"], "label": r["label"], "measure": meas,
                       "area": r["area"], "freq": "M", "date": r["date"], "value": r[meas], "unit": unit,
                       "source": "Trade Policy and Strategy Office, Ministry of Commerce", "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    fingerprint = hashlib.sha256(json.dumps(b["series"][-600:], sort_keys=True).encode()).hexdigest()[:16]
    if state.get("code") == code and not partial:
        warnings.append("same month re-fetched (forced run or revision)")
    release = {"code": code, "label": label, "latest_month": latest + "-01", "published_at": b["created"].get(latest),
               "table": "TPSO Open API: Cpig (types TG, 10, CC, NN, EE, SS) and Cpil (TL), base 2023 (BE 2566)",
               "partial": partial}
    write_release(OUT, release, warnings, len(b["series"]), {"fingerprint": fingerprint, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{label}: {len(b['series'])} rows, "
            f"{sum(len(v) for v in new.values())} months fetched", "warnings": warnings}
