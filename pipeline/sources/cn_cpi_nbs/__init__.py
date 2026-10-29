"""China CPI: National Bureau of Statistics (NBS) data portal, as published (no key).

NBS publishes no index levels: every CPI figure is a relative index with the comparison period = 100,
one decimal: same month last year = 100 (y/y), same period last year = 100 (year to date) and
previous month = 100 (m/m). 100.9 is NBS's "up 0.9%". This source stores the published value and
the same figure as a percentage change (value - 100, exactly the rate in NBS's release); nothing is
calculated from the data.

Coverage (national): all items, urban, rural, food, non-food, consumer goods, services, CPI excluding
food and energy, the 8 categories and NBS's published subcategories; y/y, YTD and m/m. Provinces:
all items and the 8 categories for 31 provinces. NBS's 2025-base category weights (published
11 Feb 2026) are in weights_2025.csv, shown as % of CPI. NBS's "impact on CPI (percentage points)"
statements in its monthly release and its statistician's interpretation are parsed from the HTML
pages on stats.gov.cn (cn_cpi_impacts.csv): published contributions, not a complete decomposition.
"""
import csv
import gzip
import hashlib
import json
import time
import re

from core import nbs
from core.common import DATA, RAW, ROOT, CheckFailed, read_json, write_long, write_release

NAME = "cn_cpi_nbs"
DESCRIPTION = "China CPI (NBS data portal and releases, as published)"
OUT = DATA / "cn" / "cpi"
RAWDIR = RAW / "cn" / "cpi_nbs"
HERE = ROOT / "pipeline" / "sources" / "cn_cpi_nbs"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
LONGMONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
              "October", "November", "December"]

MEASURES = {"6021702000021": "yoy", "6021702000022": "ytd", "6021702000023": "mom"}
SCOPES = {"106320100002": "urban", "107900106542": "rural"}
# NBS category code -> (key, English name, group, order). Names follow NBS's English release.
CATS = {
    "": ("all", "CPI", "headline", 0),
    "6067101000036": ("core", "CPI excluding food and energy", "headline", 1),
    "6039803100002": ("food", "Food", "headline", 2),
    "601300100001": ("food", "Food", "headline", 2),
    "6067101000030": ("tobacco_liquor_old", "Tobacco, liquor and articles (to 2015)", "category_old", 90),
    "6067101000034": ("non_food", "Non-food", "headline", 3),
    "6067101000035": ("goods", "Consumer goods", "headline", 4),
    "6067101000033": ("services", "Services", "headline", 5),
    "6039802100001": ("food_tobacco_liquor", "Food, tobacco, liquor and dining out", "category", 10),
    "6039802100082": ("clothing", "Clothing", "category", 20),
    "6039802100117": ("residence", "Residence", "category", 30),
    "6039802100148": ("household", "Household facilities, articles and services", "category", 40),
    "6039802100213": ("transport_telecom", "Transportation and telecommunication", "category", 50),
    "6039802100249": ("education_culture", "Education, culture and recreation", "category", 60),
    "6039802100296": ("health_care", "Health care and medical services", "category", 70),
    "6039802100342": ("other", "Miscellaneous goods and services", "category", 80),
    "119530247202": ("other", "Miscellaneous goods and services", "category", 80),
    "6039803100069": ("tobacco_liquor_old", "Tobacco, liquor and articles (to 2015)", "category_old", 90),
    "6040001046861": ("household_old", "Household facilities, articles and maintenance services (to 2015)", "category_old", 91),
    # subcategories
    "6039804100003": ("grain", "Grain", "food", 11),
    "6039804100013": ("edible_oil", "Edible oil and fats", "food", 12),
    "6039805100017": ("fresh_vegetables", "Fresh vegetables", "food", 13),
    "6039804100020": ("livestock_meat", "Meat of livestock", "food", 14),
    "6039805100021": ("pork", "Pork", "food", 15),
    "6039805100022": ("beef", "Beef", "food", 16),
    "6039805100023": ("mutton", "Mutton", "food", 17),
    "6039804100026": ("meat_poultry", "Meat, poultry and products", "food", 18),
    "124740210994": ("meat_poultry", "Meat, poultry and products", "food", 18),
    "6039804100030": ("aquatic", "Aquatic products", "food", 19),
    "6039804100035": ("eggs", "Eggs", "food", 19.1),
    "6039804100038": ("dairy", "Milk and other dairy products", "food", 19.2),
    "6039805100044": ("fresh_fruit", "Fresh fruits", "food", 19.3),
    "6039805100071": ("cigarettes", "Cigarettes", "food", 19.4),
    "6039804100072": ("liquor", "Liquor", "food", 19.5),
    "6039803100083": ("garments", "Garments", "clothing", 21),
    "6039803100110": ("footwear", "Footwear", "clothing", 22),
    "6039803100118": ("rent", "Rent of rental housing", "residence", 31),
    "6039803100136": ("water_power_fuel", "Water, electricity and fuels", "residence", 32),
    "6039803100160": ("home_appliances", "Home appliances", "household", 41),
    "6039803100208": ("household_services", "Household services", "household", 42),
    "6039804100215": ("automobiles", "Automobiles", "transport_telecom", 51),
    "6039804100221": ("vehicle_fuel", "Energy for transport facilities", "transport_telecom", 52),
    "6039804100225": ("vehicle_use", "Use and maintenance of transport facilities", "transport_telecom", 53),
    "6039804100240": ("comm_equipment", "Communication facilities", "transport_telecom", 54),
    "6039804100243": ("telecom_services", "Telecommunication services", "transport_telecom", 55),
    "6039804100247": ("postal", "Postal services", "transport_telecom", 56),
    "6039804100256": ("education_services", "Education services", "education_culture", 61),
    "6039804100293": ("travel_services", "Travel agencies and other touring services", "education_culture", 62),
    "6039804100298": ("tcm", "Traditional Chinese medicines", "health_care", 71),
    "6039804100301": ("western_medicines", "Western medicines", "health_care", 72),
    "6039803100322": ("medical_services", "Medical services", "health_care", 73),
}
PROVINCES = {
    "11": "Beijing", "12": "Tianjin", "13": "Hebei", "14": "Shanxi", "15": "Inner Mongolia", "21": "Liaoning",
    "22": "Jilin", "23": "Heilongjiang", "31": "Shanghai", "32": "Jiangsu", "33": "Zhejiang", "34": "Anhui",
    "35": "Fujian", "36": "Jiangxi", "37": "Shandong", "41": "Henan", "42": "Hubei", "43": "Hunan",
    "44": "Guangdong", "45": "Guangxi", "46": "Hainan", "50": "Chongqing", "51": "Sichuan", "52": "Guizhou",
    "53": "Yunnan", "54": "Tibet", "61": "Shaanxi", "62": "Gansu", "63": "Qinghai", "64": "Ningxia",
    "65": "Xinjiang",
}
# CPI base periods rotate every five years; the first month on each base.
BASE_STARTS = {"2001-01": "2000", "2006-01": "2005", "2011-01": "2010", "2016-01": "2015", "2021-01": "2020",
               "2026-01": "2025"}


def base_of(period):
    b = ""
    for start, base in sorted(BASE_STARTS.items()):
        if period >= start:
            b = base
    return b


def parse_ek(ek):
    """'106320100002-6021702000021-6039802100001|<id>' -> (scope, measure, category code)."""
    codes = (ek or "").split("|")[0].split("-")
    measure = next((MEASURES[c] for c in codes if c in MEASURES), None)
    scope = next((SCOPES[c] for c in codes if c in SCOPES), "national")
    rest = [c for c in codes if c not in MEASURES and c not in SCOPES]
    return scope, measure, rest[0] if rest else ""


def _keep_cpi(path, name):
    return "居民消费价格" in name or "居民消费价格" in path


def _tidy(rows, prov=False, warnings=None):
    out = {}
    unknown = set()
    for r in rows:
        scope, measure, code = parse_ek(r["ek"])
        if measure is None:
            continue
        if code not in CATS:
            unknown.add((code, r["name"]))
            continue
        key, label, group, order = CATS[code]
        if prov:
            pc = (r["area"] or "")[:2]
            if pc not in PROVINCES:
                continue
            area, area_name = pc, PROVINCES[pc]
        else:
            area, area_name = scope, {"national": "China", "urban": "Urban", "rural": "Rural"}[scope]
        v = float(r["value"])
        k = (r["period"], area, key, measure)
        if k in out and abs(out[k]["value"] - v) > 1e-9:
            if warnings is not None:
                warnings.append(f"{key} {measure} {area} {r['period']}: two catalogs disagree ({out[k]['value']} vs {v})")
            continue
        out[k] = {"date": r["period"] + "-01", "area": area, "area_name": area_name, "series": key, "label": label,
                  "group": group, "order": order, "measure": measure, "value": v, "pct": round(v - 100, 1),
                  "base": base_of(r["period"]), "ek": r["ek"].split("|")[0]}
    if unknown and warnings is not None:
        warnings.append("series not mapped (left out): " + "; ".join(f"{c or 'all'} {n}" for c, n in sorted(unknown))[:600])
    return out


def _shift(p, months):
    y, m = int(p[:4]), int(p[5:7]) - 1 + months
    return f"{y + m // 12}-{m % 12 + 1:02d}"


def _months(a, b):
    out, p = [], a
    while p <= b:
        out.append(p)
        p = _shift(p, 1)
    return out


def _check(tidy, impacts, latest, state, warnings):
    errors = []
    lp = latest[:7]
    need = [("all", "national"), ("core", "national"), ("food", "national"), ("goods", "national"),
            ("services", "national"), ("all", "urban"), ("all", "rural")]
    for key, area in need:
        for m in ("yoy", "mom"):
            if not any(v["date"][:7] == lp and v["series"] == key and v["area"] == area and v["measure"] == m
                       for v in tidy.values()):
                errors.append(f"latest month {lp}: {area} {key} {m} missing")
    if state.get("latest_month") and latest < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one stored ({state['latest_month']})")
    # No gaps in headline y/y over the full history
    hl = sorted(v["date"][:7] for v in tidy.values() if v["series"] == "all" and v["area"] == "national" and v["measure"] == "yoy")
    if hl:
        missing = sorted(set(_months(hl[0], hl[-1])) - set(hl))
        if missing:
            errors.append(f"headline y/y has gaps: {missing[:12]}")
    # Range
    for v in tidy.values():
        if not 0 < v["value"] < 400:
            errors.append(f"{v['area']} {v['series']} {v['measure']} {v['date'][:7]} = {v['value']} out of range")
    # Consistency of y/y, m/m and YTD (published to one decimal): YTD in January equals y/y; YTD is the
    # average of the year's y/y rates, within rounding (NBS averages unrounded rates, so 0.15pp).
    get = {(v["date"][:7], v["area"], v["series"], v["measure"]): v["value"] for v in tidy.values()}
    bad_jan, bad_avg, tested = [], [], 0
    for (p, area, key, meas), val in get.items():
        if meas != "ytd" or area not in ("national", "urban", "rural"):
            continue
        # Exact only for broad aggregates; for volatile items (pork) YTD, a ratio of cumulative
        # indices, departs from the simple average of y/y rates.
        if key not in ("all", "core", "non_food", "goods", "services", "food_tobacco_liquor", "clothing",
                       "residence", "household", "transport_telecom", "education_culture", "health_care", "other"):
            continue
        y, m = int(p[:4]), int(p[5:7])
        yoys = [get.get((f"{y}-{i:02d}", area, key, "yoy")) for i in range(1, m + 1)]
        if any(x is None for x in yoys):
            continue
        tested += 1
        if m == 1 and abs(val - yoys[0]) > 0.051 and p >= "2001":
            bad_jan.append(f"{area} {key} {p}: YTD {val} vs y/y {yoys[0]}")
        avg = sum(yoys) / len(yoys)
        if abs(val - avg) > 0.15:
            bad_avg.append(f"{area} {key} {p}: YTD {val} vs average y/y {avg:.2f}")
    if bad_jan:
        errors.append(f"January YTD differs from y/y ({len(bad_jan)}): {bad_jan[:5]}")
    if len(bad_avg) > max(3, tested // 100):
        errors.append(f"YTD differs from the average of y/y by more than 0.15 ({len(bad_avg)} of {tested}): {bad_avg[:5]}")
    elif bad_avg:
        warnings.append(f"YTD vs average y/y beyond 0.15 in {len(bad_avg)} of {tested} cases: {bad_avg[:3]}")
    # m/m vs y/y: the 12 published m/m over a year compound to the published y/y, within rounding
    # (12 one-decimal rounding errors: allow 0.4pp). Reported only; NBS's m/m and y/y differ at base changes.
    off, n = [], 0
    for (p, area, key, meas), val in get.items():
        if meas != "yoy" or area != "national" or key not in ("all", "core", "food", "goods", "services", "non_food"):
            continue
        moms = [get.get((_shift(p, -i), area, key, "mom")) for i in range(12)]
        if any(x is None for x in moms):
            continue
        n += 1
        c = 1.0
        for x in moms:
            c *= x / 100
        if abs(c * 100 - val) > 0.4:
            off.append(f"{key} {p}: y/y {val} vs m/m compounded {c * 100:.2f}")
    if off:
        warnings.append(f"m/m compounded over 12 months differs from y/y by more than 0.4pp in {len(off)} of {n} months "
                        f"(rounding and base changes): {off[:3]}")
    # Published impacts: where NBS states the four components (food, energy, industrial consumer goods
    # excluding energy, services), they add up to the headline y/y within rounding.
    for imp in impacts:
        if imp.get("check") is not None:
            c = imp["check"]
            if abs(c["sum"] - c["headline"]) > 0.11:
                errors.append(f"published impacts {imp['date']}: parts sum {c['sum']:.2f} vs CPI y/y {c['headline']}")
    return errors


def _write_csv(path, cols, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r.get(c) is None else r.get(c) for c in cols])


def update(**opts):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    warnings = []
    cats = nbs.catalogs("1", nbs.ROOT_MONTHLY, _keep_cpi)
    if not cats:
        raise CheckFailed(["no CPI catalogs found in the NBS portal's monthly tree (portal changed?)"])
    current = [c for c, m in cats.items() if "(2026-)" in m["name"] and "上年同月" in m["name"] and m["path"].endswith("居民消费价格分类指数 (上年同月=100)")]
    latest_p = nbs.latest(current[0]) if current else None
    if latest_p and state.get("latest_month") == f"{latest_p[:4]}-{latest_p[4:6]}-01" and not opts.get("force"):
        return {"updated": False, "code": state.get("code"), "summary": f"no new month (latest {state.get('latest_month')[:7]})"}
    raw, rows = {}, []
    t0 = time.time()

    def fetch(cid):
        inds = nbs.indicators(cid)
        return (cid,) + (nbs.table(cid, [x["_id"] for x in inds]) if inds else ([], []))
    for cid, r, data in nbs.parallel(fetch, list(cats)):
        raw[cid] = {"meta": cats[cid], "data": data}
        rows += r
    timing = {"national_s": round(time.time() - t0)}
    tidy = _tidy(rows, warnings=warnings)
    # Provinces: y/y for every base period and food items, m/m and YTD for the current base
    # (one call per province and table)
    pcats = {c: m for c, m in nbs.catalogs("4", nbs.ROOT_PROVINCE, _keep_cpi).items()
             if "上年同月" in m["name"] or "(2026-)" in m["name"]}
    prov_rows = []
    for cid, meta in pcats.items():
        inds = nbs.indicators(cid)
        if not inds:
            continue
        try:
            r, data = nbs.province_rows(cid, [x["_id"] for x in inds])
        except nbs.NBSError as e:
            warnings.append(f"provinces, {meta['name']}: {e}")
            continue
        raw["prov_" + cid] = {"meta": meta, "data": data}
        prov_rows += r
    ptidy = _tidy(prov_rows, prov=True, warnings=warnings)
    timing["province_s"] = round(time.time() - t0) - timing["national_s"]
    latest = max(v["date"] for v in tidy.values() if v["series"] == "all" and v["area"] == "national")
    # NBS releases (HTML): published impacts on CPI, and release dates
    try:
        rel = nbs.cpi_releases(since="2025-01")
    except Exception as e:  # noqa: BLE001 - impacts are an extra; the data stand without them
        rel = []
        warnings.append(f"NBS release pages not read: {e!r}"[:300])
    timing["total_s"] = round(time.time() - t0)
    impacts = []
    for r in rel:
        head = next((v["pct"] for v in tidy.values() if v["date"][:7] == r["month"] and v["area"] == "national"
                     and v["series"] == "all" and v["measure"] == "yoy"), None)
        rec = {"date": r["month"] + "-01", "release_date": r["date"], "items": r["impacts"], "check": None}
        parts = {i["key"]: i["pp"] for i in r["impacts"] if i["measure"] == "yoy" and i["source"] == "interpretation"}
        if head is not None and all(k in parts for k in ("food", "energy", "goods_ex_energy", "services")):
            rec["check"] = {"sum": round(sum(parts[k] for k in ("food", "energy", "goods_ex_energy", "services")), 2),
                            "headline": head}
        impacts.append(rec)
    errors = _check(tidy, impacts, latest, state, warnings)
    if not ptidy:
        errors.append("no provincial CPI rows")
    else:
        pl = max(v["date"] for v in ptidy.values())
        if pl < latest:
            warnings.append(f"provincial CPI latest {pl[:7]} is behind national {latest[:7]}")
        np_ = len({v["area"] for v in ptidy.values() if v["date"] == pl and v["series"] == "all" and v["measure"] == "yoy"})
        if np_ < 31:
            errors.append(f"provincial CPI y/y for {pl[:7]}: {np_} provinces, expected 31")
    tested = [i for i in impacts if i["check"]]
    if not tested:
        warnings.append("published impacts: no month states all four parts (food, energy, industrial consumer goods "
                        "ex energy, services), so the sum check could not run")
    if errors:
        raise CheckFailed(errors)

    # ---- write
    rel_dates = {r["month"]: r["date"] for r in rel}
    cols = ["date", "area", "area_name", "series", "label", "group", "order", "measure", "value", "pct", "base",
            "base_break", "release_date", "ek"]
    out_rows = sorted(list(tidy.values()) + list(ptidy.values()),
                      key=lambda r: (r["date"], r["area"] not in ("national", "urban", "rural"), r["area"], r["order"], r["measure"]))
    for r in out_rows:
        r["base_break"] = 1 if r["date"][:7] in BASE_STARTS else 0
        r["release_date"] = rel_dates.get(r["date"][:7], "")
    _write_csv(OUT / "cn_cpi.csv", cols, [r for r in out_rows if r["area"] in ("national", "urban", "rural")])
    _write_csv(OUT / "cn_cpi_provinces.csv", cols, [r for r in out_rows if r["area"] not in ("national", "urban", "rural")])
    # Slim copies for the dashboard (same figures, fewer columns; provinces y/y only)
    dcols = ["date", "area", "series", "label", "group", "measure", "pct", "base_break"]
    _write_csv(OUT / "cn_cpi_dash.csv", dcols, [r for r in out_rows if r["area"] in ("national", "urban", "rural")])
    _write_csv(OUT / "cn_cpi_provinces_dash.csv", ["date", "area", "area_name", "series", "measure", "pct"],
               [r for r in out_rows if r["area"] not in ("national", "urban", "rural") and r["measure"] == "yoy"])
    wt = list(csv.DictReader(open(HERE / "weights_2025.csv")))
    _write_csv(OUT / "cn_cpi_weights.csv", ["key", "name_zh", "name_en", "weight_pct"], wt)
    irows = []
    for rec in impacts:
        for i in rec["items"]:
            irows.append({"date": rec["date"], "release_date": rec["release_date"], **i})
    _write_csv(OUT / "cn_cpi_impacts.csv", ["date", "release_date", "source", "measure", "key", "name", "rate", "pp", "text"], irows)

    code = f"C{latest[:7]}"
    label = f"{LONGMONTHS[int(latest[5:7]) - 1]} {latest[:4]}"
    src = "National Bureau of Statistics of China"

    def long_rows():
        for r in out_rows:
            yield {"country": "CN", "indicator": "cpi", "series": f"{r['series']}_{r['measure']}", "label": r["label"],
                   "measure": r["measure"], "area": r["area"], "freq": "M", "date": r["date"], "value": r["pct"],
                   "unit": "%", "source": src, "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    # latest-month row for the dashboard
    RAWDIR.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(raw, ensure_ascii=False).encode()
    fp = hashlib.sha256(blob).hexdigest()[:12]
    (RAWDIR / f"{code}_{fp}.json.gz").write_bytes(gzip.compress(blob))
    release = {"code": code, "label": label, "latest_month": latest, "release_date": rel_dates.get(latest[:7], ""),
               "table": "NBS data portal (data.stats.gov.cn), monthly CPI catalogs; releases on stats.gov.cn"}
    write_release(OUT, release, warnings, len(out_rows),
                  {"long_rows": nlong, "catalogs": len(cats), "province_catalogs": len(pcats),
                   "impact_months": len(impacts), "impacts_checked": len(tested)})
    return {"updated": True, "code": code, "summary": f"{label}: {len(tidy)} national and {len(ptidy)} provincial rows; timing {timing}",
            "warnings": warnings}
