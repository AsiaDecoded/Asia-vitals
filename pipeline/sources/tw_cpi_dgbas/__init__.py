"""Taiwan CPI: DGBAS Macro Database and monthly price releases, as published (no key).

Macro Database (nstatdb.dgbas.gov.tw), 2021 = 100, two decimals: index, % change on the previous month
and % change on the same month a year earlier for the basic groups (7 groups and their subgroups,
1981-), goods and services, special groups (DGBAS core = CPI excluding fruit, vegetables and energy;
energy; CPI excluding food and energy on DGBAS's food definition ...), purchase frequency, income
groups, elderly households (2018-) and DGBAS's seasonally adjusted CPI and core; the 368 priced items
(Jan 2013-). The all-items index before 1981 (from Jan 1959) comes from DGBAS's linked CPI file
(cpispl.xls). Monthly release tables (stat.gov.tw): table 1 gives that month's group weights (per mille,
shown here as % of CPI) and DGBAS's contributions to the m/m, y/y and year-to-date change
("對總指數影響", pp); table 14 the item weights (% of CPI). Both as first published, from Aug 2023.

Nothing is calculated: every value is a DGBAS figure. The checks compare DGBAS's rates with its index
and its weights with its headline; they write nothing.
"""
import csv
import gzip
import hashlib
import io
import json

from core import dgbas
from core.common import DATA, RAW, ROOT, CheckFailed, read_json, write_long, write_release

NAME = "tw_cpi_dgbas"
DESCRIPTION = "Taiwan CPI (DGBAS Macro Database and monthly releases, as published)"
OUT = DATA / "tw" / "cpi"
RAWDIR = RAW / "tw" / "cpi_dgbas"
HERE = ROOT / "pipeline" / "sources" / "tw_cpi_dgbas"
LONGMONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
              "October", "November", "December"]
CPISPL = "https://ws.dgbas.gov.tw/001/Upload/463/relfile/10315/2703/cpispl.xls"
# (table, first month, group, modes)
TABLES = [
    ("A030101015", "1981-01", "basic", ("00", "1", "2")),
    ("A030102015", "1981-01", "goods_services", ("00", "1", "2")),
    ("A030103015", "1981-01", "special", ("00", "1", "2")),
    ("A030105015", "1981-01", "purchase_frequency", ("00", "1", "2")),
    ("A030106015", "2018-01", "elderly", ("00", "1", "2")),
    ("A030601015", "1981-01", "seasonally_adjusted", ("00", "1")),
]
ITEMS = ("A030101025", "2013-01")
INCOME = ("A030104015", "1981-01")
INCOME_AREAS = {"全體家庭": "all_households", "最低20%所得家庭": "lowest20", "中間60%所得家庭": "middle60",
                "最高20%所得家庭": "highest20"}
GROUPS7 = ["food", "clothing", "housing", "transport_comm", "health", "education_entertainment", "miscellaneous"]
# Classification rebases (first month on the new base); weights are also re-linked every December
# since the 2016 base (open decision on flagging those).
BASE_STARTS = {"2023-01": "2021"}
# Release table 1 labels -> series keys
T1_KEYS = {
    "總指數": "all", "一.食物類": "food", "穀類及其製品": "cereals", "肉類": "meat", "蛋類": "eggs", "水產品": "fish",
    "蔬菜": "vegetables", "水果": "fruit", "調理食品": "cooked_food", "二.衣著類": "clothing", "成衣": "garments",
    "三.居住類": "housing", "房租": "rent", "家庭用品": "household_goods", "家庭管理費用": "household_operations",
    "燃氣": "gas", "電費": "electricity", "四.交通及通訊類": "transport_comm", "交通工具": "vehicles",
    "通訊設備": "comm_equipment", "油料費": "fuels", "運輸費": "transport_fees",
    "交通工具零件及維修費": "vehicle_parts_repair", "五.醫藥保健類": "health", "醫療費用": "medical_services",
    "醫療保健器材": "medical_supplies", "六.教養娛樂類": "education_entertainment", "教養費用": "education",
    "娛樂費用": "entertainment", "七.雜項類": "miscellaneous", "香菸及檳榔": "tobacco", "美容及衛生用品": "cosmetics",
    "個人隨身用品": "personal_effects", "個人照顧服務費": "nursing_care", "一.商品類": "goods",
    "核心商品(商品不含蔬果及能源)": "core_goods", "非耐久性消費品": "nondurable", "半耐久性消費品": "semidurable",
    "耐久性消費品": "durable", "二.服務類": "services", "外食費": "services_eating_out",
    "交通及通訊服務": "services_transport_comm", "教養服務": "services_education", "娛樂服務": "services_entertainment",
    "總指數(不含設算租金)": "ex_imputed_rent", "每月至少購買1次": "pf_monthly", "每季(不含每月)至少購買1次": "pf_quarterly",
    "每季購買不到1次": "pf_less_often", "總指數(不含蔬菜水果)": "ex_fruit_veg",
    "核心CPI(總指數不含蔬果及能源)": "core", "最低20％所得家庭CPI總指數": "lowest20", "中間60％所得家庭CPI總指數": "middle60",
    "最高20％所得家庭CPI總指數": "highest20", "高齡家庭CPI總指數": "elderly",
}


def _names():
    out = {}
    for r in csv.DictReader(open(HERE / "names.csv", encoding="utf-8")):
        out[(r["table"], r["field"])] = r
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


def _cpispl(blob):
    """DGBAS linked CPI file: all-items index (sheet 1) and y/y (sheet 2), ROC year rows x 12 months."""
    import xlrd
    book = xlrd.open_workbook(file_contents=blob)
    out = {}
    for sh, meas in zip(book.sheets()[:2], ("index", "yoy")):
        for r in range(sh.nrows):
            row = sh.row_values(r)
            try:
                y = int(float(row[0]))
            except (TypeError, ValueError):
                continue
            for m in range(1, 13):
                v = row[m] if m < len(row) else ""
                if isinstance(v, (int, float)) and v != "":
                    out[(f"{y + 1911}-{m:02d}", meas)] = float(v)
    return out


def _income(first, last, raw, warnings):
    """Income-group table: fields are household groups, codes the 7 groups; the CSV has one column per
    (group, household) pair. Returns {(area, series, measure): {period: value}}."""
    funid = INCOME[0]
    d = dgbas.definition(funid)
    codes = d.get("codName0") or []
    fields = d.get("fldName") or []
    keys = {"總指數": "all", "一.食物類": "food", "二.衣著類": "clothing", "三.居住類": "housing",
            "四.交通及通訊類": "transport_comm", "五.醫藥保健類": "health", "六.教養娛樂類": "education_entertainment",
            "七.雜項類": "miscellaneous"}
    out = {}
    for mode, meas in (("00", "index"), ("1", "mom"), ("2", "yoy")):
        header, rows, text = dgbas.csv_table(funid, first, last, mode)
        raw[f"{funid}_{mode}"] = text
        for j, h in enumerate(header):
            area = next((INCOME_AREAS[a] for a in INCOME_AREAS if a in h), None)
            code = next((keys[c] for c in sorted(keys, key=len, reverse=True) if c in h), None)
            if area is None and len(header) == len(codes) * len(fields):
                # header gives one dimension only: columns run code-major, field-minor
                area = INCOME_AREAS.get(fields[j % len(fields)])
                code = keys.get(codes[j // len(fields)])
            if area is None or code is None:
                continue
            s = {p: v[j] for p, v in rows.items() if j < len(v) and v[j] is not None}
            if s:
                out[(area, code, meas)] = s
    if not out:
        warnings.append(f"income groups: CSV layout not recognised (header {header[:6]})")
    return out


def _release_archive(warnings):
    """Release tables 1 and 14 for every month listed on stat.gov.tw (from Aug 2023), kept as originals
    under raw/tw/cpi_dgbas/releases/; only months not yet stored are downloaded."""
    store = RAWDIR / "releases"
    store.mkdir(parents=True, exist_ok=True)
    index = read_json(store / "index.json", {}) or {}
    try:
        listed = dgbas.releases(since="2023-01")
    except dgbas.DGBASError as e:
        warnings.append(f"release list not read: {e}"[:300])
        listed = []
    for rel in listed:
        m = rel["month"]
        rec = index.get(m)
        if rec and (store / rec.get("t1", "-")).exists() and (store / rec.get("t14", "-")).exists():
            continue
        try:
            page = dgbas.release_page(rel["url"])
            tag = f"t{int(m[:4]) - 1911}{m[5:7]}"
            rec = {"url": rel["url"], "title": rel["title"], "date": page["date"]}
            for t in ("1", "14"):
                fname = f"{tag}_{t}.xlsx"
                if fname not in page["files"]:
                    raise dgbas.DGBASError(f"{fname} not on the release page")
                (store / f"{m}_t{t}.xlsx").write_bytes(dgbas.get(page["files"][fname]))
                rec[f"t{t}"] = f"{m}_t{t}.xlsx"
            index[m] = rec
        except dgbas.DGBASError as e:
            warnings.append(f"release {m}: {e}"[:300])
    (store / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    t1, t14 = {}, {}
    for m, rec in sorted(index.items()):
        try:
            t1[m] = dgbas.read_t1((store / rec["t1"]).read_bytes())
            t1[m]["release_date"] = rec.get("date", "")
            t14[m] = dgbas.read_t14((store / rec["t14"]).read_bytes())
        except Exception as e:  # noqa: BLE001
            warnings.append(f"release {m}: tables not read ({e!r})"[:300])
    return t1, t14


def _bound(i0, i1):
    """Largest y/y (or m/m) error, in pp, from two indices each rounded to 0.01 and a rate rounded to 0.01."""
    return 100 * (0.005 / i0 + 0.005 * i1 / i0 ** 2) + 0.0051


def _check(get, t1, t14, latest, state, warnings):
    errors = []
    for key in ("all", "core", "food", "energy", "goods", "services"):
        for meas in ("index", "mom", "yoy"):
            if get(("national", key, meas), latest) is None:
                errors.append(f"latest month {latest}: {key} {meas} missing")
    if state.get("latest_month") and latest < state["latest_month"][:7]:
        errors.append(f"latest month {latest} is before the one stored ({state['latest_month'][:7]})")
    return errors


def update(**opts):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    warnings = []
    latest = dgbas.latest("A030101015")
    if state.get("latest_month", "")[:7] == latest and not opts.get("force"):
        return {"updated": False, "code": state.get("code"), "summary": f"no new month (latest {latest})"}
    names = _names()
    raw = {}
    data = {}  # (area, series, measure) -> {period: value}
    meta = {}  # series -> name row
    unknown = []
    for funid, first, group, modes in TABLES:
        s, r = dgbas.series(funid, first, latest, modes)
        raw.update(r)
        for (field, meas), vals in s.items():
            nm = names.get((funid, field))
            if nm is None:
                if funid != "A030601015":
                    unknown.append(f"{funid} {field}")
                continue
            key = nm["key"]
            if funid == "A030601015":
                meas = {"index": "index", "mom": "mom"}[meas]
                key, meas = key.replace("_sa", ""), "sa_" + meas
            area = "elderly" if group == "elderly" else "national"
            if area == "elderly":
                key = {"elderly": "all"}.get(key, key.replace("elderly_", ""))
            data[(area, key, meas)] = vals
            meta.setdefault(key if area == "national" else key, {**nm, "group": group})
    if unknown:
        warnings.append(f"fields not mapped (left out): {unknown[:12]}")
    data.update(_income(INCOME[1], latest, raw, warnings))
    # Items (Jan 2013-): index, m/m, y/y
    items, r = dgbas.series(ITEMS[0], ITEMS[1], latest, ("00", "1", "2"))
    raw.update(r)
    item_rows = []
    for (field, meas), vals in items.items():
        code = field.split()[0]
        if not code.isdigit():
            continue
        for p, v in vals.items():
            item_rows.append({"date": p + "-01", "code": int(code), "name": field.split(None, 1)[1] if " " in field else field,
                              "measure": meas, "value": v})
    n_items = len({r["code"] for r in item_rows})
    # Long all-items history from the linked file (1959-1980; checked against the database from 1981)
    blob = dgbas.get(CPISPL)
    raw["cpispl.xls"] = None
    (RAWDIR).mkdir(parents=True, exist_ok=True)
    spl = _cpispl(blob)
    head_i, head_y = data[("national", "all", "index")], data[("national", "all", "yoy")]
    diff = [abs(spl[(p, "index")] - v) for p, v in head_i.items() if (p, "index") in spl]
    if diff and max(diff) > 0.011:
        warnings.append(f"linked file vs database, all-items index 1981-: max difference {max(diff):.3f}")
    for (p, meas), v in spl.items():
        target = head_i if meas == "index" else head_y
        if p not in target:  # before the database's first month (index 1981, y/y 1982)
            target[p] = v
    t1, t14 = _release_archive(warnings)

    def get(k, p):
        return data.get(k, {}).get(p)

    errors = _check(get, t1, t14, latest, state, warnings)
    # No gaps in headline y/y over the full history
    hy = sorted(head_y)
    missing = sorted(set(_months(hy[0], hy[-1])) - set(hy))
    if missing:
        errors.append(f"headline y/y has gaps: {missing[:12]}")
    # Published rates agree with the published index within rounding
    stats = {"tested": 0, "outside": 0, "max": 0.0}
    strict = {"all", "core", "food", "energy", "goods", "services"}
    bad_strict, bad_other = [], []
    for (area, key, meas), vals in data.items():
        if meas not in ("yoy", "mom"):
            continue
        idx = data.get((area, key, "index"), {})
        for p, v in vals.items():
            p0 = _shift(p, -12 if meas == "yoy" else -1)
            if p in idx and p0 in idx and idx[p0] > 0:
                if key == "all" and area == "national" and p < "1982-01":
                    continue  # linked-file years: rates published on older bases
                c = (idx[p] / idx[p0] - 1) * 100
                d = abs(c - v)
                stats["tested"] += 1
                stats["max"] = max(stats["max"], d)
                if d > _bound(idx[p0], idx[p]) + 0.01:
                    stats["outside"] += 1
                    (bad_strict if key in strict and area == "national" else bad_other).append(
                        f"{area} {key} {meas} {p}: published {v} vs index {c:.3f}")
    if bad_strict:
        errors.append(f"published rate differs from the index beyond rounding ({len(bad_strict)}): {bad_strict[:6]}")
    if bad_other:
        warnings.append(f"rate vs index beyond rounding in {len(bad_other)} of {stats['tested']} cases (other series): {bad_other[:4]}")
    # Weights (release table 1): 7 groups sum to 1000 per mille and, chained from the previous December
    # (I = I_Dec x sum w (I_g / I_g,Dec) / 1000), reproduce the published headline index. Table 1 shows
    # the year's weights; DGBAS gives fresh fruit and vegetables month-specific weights inside food, which
    # it does not publish in table 1, so the group-level identity holds to about 0.05 index points, not
    # to rounding (limit 0.06; the largest gap is reported).
    wcheck = []
    for m, t in sorted(t1.items()):
        rows = {T1_KEYS.get(r["label"]): r for r in t["rows"] if T1_KEYS.get(r["label"])}
        if t.get("month") and t["month"] != m:
            errors.append(f"release table 1 for {m} is labelled {t['month']}")
        if not all(g in rows for g in GROUPS7 + ["all"]):
            errors.append(f"release table 1 {m}: groups missing ({[g for g in GROUPS7 if g not in rows]})")
            continue
        wsum = sum(rows[g]["weight_pm"] for g in GROUPS7)
        if abs(wsum - 1000) > 0.06:
            errors.append(f"release table 1 {m}: group weights sum to {wsum:.2f} per mille")
        dec = f"{int(m[:4]) - 1}-12"
        ih_dec = get(("national", "all", "index"), dec)
        ig_dec = {g: get(("national", g, "index"), dec) for g in GROUPS7}
        if ih_dec and all(ig_dec.values()):
            rep = ih_dec * sum(rows[g]["weight_pm"] * rows[g]["index"] / ig_dec[g] for g in GROUPS7) / 1000
            wcheck.append({"month": m, "published": rows["all"]["index"], "from_weights": round(rep, 3),
                           "diff": round(rep - rows["all"]["index"], 3), "weight_sum_pm": round(wsum, 2)})
        # Published contributions to y/y: the 7 groups add up to the headline y/y within rounding
        cs = sum(rows[g]["yoy_pp"] for g in GROUPS7)
        if abs(cs - rows["all"]["yoy"]) > 0.05:
            errors.append(f"release table 1 {m}: group contributions sum to {cs:.2f}pp vs CPI y/y {rows['all']['yoy']}")
        if abs(rows["goods"]["yoy_pp"] + rows["services"]["yoy_pp"] - rows["all"]["yoy"]) > 0.03:
            errors.append(f"release table 1 {m}: goods + services contributions differ from CPI y/y")
    if wcheck:
        mx = max(abs(w["diff"]) for w in wcheck)
        if mx > 0.06:
            errors.append(f"weights do not reproduce the headline index within 0.06 (max {mx:.3f}): "
                          f"{[w for w in wcheck if abs(w['diff']) > 0.06][:4]}")
    else:
        errors.append("no release table 1 read: weights check could not run")
    wsum14 = {m: round(sum(i["weight_pct"] for i in it.values()), 3) for m, it in t14.items()}
    for m, s in wsum14.items():
        if not 99.0 <= s <= 100.02:
            warnings.append(f"release table 14 {m}: item weights sum to {s}% ({len(t14[m])} items listed)")
    if n_items < 360:
        errors.append(f"items: {n_items} found, expected 368")
    for (area, key, meas), vals in data.items():
        for p, v in vals.items():
            if meas in ("index", "sa_index") and not 0 < v < 10000:  # communication equipment ~2600 in 1991
                errors.append(f"{area} {key} {meas} {p} = {v} out of range")
    if errors:
        raise CheckFailed(errors)

    # ---- write
    rel_dates = {m: t.get("release_date", "") for m, t in t1.items()}
    labels = {r["key"]: r for r in names.values()}
    area_names = {"national": "Taiwan", "elderly": "Elderly households", "all_households": "All households",
                  "lowest20": "Lowest 20% income", "middle60": "Middle 60% income", "highest20": "Highest 20% income"}
    rows = []
    for (area, key, meas), vals in data.items():
        nm = labels.get(key, {})
        for p, v in vals.items():
            rows.append({"date": p + "-01", "area": area, "area_name": area_names.get(area, area), "series": key,
                         "label": nm.get("label", key), "group": meta.get(key, {}).get("group", "basic"),
                         "level": nm.get("level", ""), "parent": nm.get("parent", ""), "measure": meas, "value": v,
                         "base_break": 1 if p in BASE_STARTS else 0, "release_date": rel_dates.get(p, "")})
    rows.sort(key=lambda r: (r["date"], r["area"] != "national", r["area"], r["group"], r["series"], r["measure"]))
    cols = ["date", "area", "area_name", "series", "label", "group", "level", "parent", "measure", "value",
            "base_break", "release_date"]
    _write_csv(OUT / "tw_cpi.csv", cols, rows)
    dash_keys = set(GROUPS7) | {"all", "core", "energy", "goods", "services", "core_goods", "noncore_goods",
                                "ex_food_energy", "ex_fruit_veg", "vegetables", "fruit", "eating_out", "fuels",
                                "electricity", "gas", "rent", "durable", "semidurable", "nondurable"}
    _write_csv(OUT / "tw_cpi_dash.csv", ["date", "area", "series", "measure", "value"],
               [r for r in rows if r["series"] in dash_keys and r["date"] >= "1960-01-01"])
    item_rows.sort(key=lambda r: (r["date"], r["code"], r["measure"]))
    _write_csv(OUT / "tw_cpi_items.csv", ["date", "code", "name", "measure", "value"], item_rows)
    # Published weights (% of CPI) and contributions (pp), as first released
    wrows, crows = [], []
    for m, t in sorted(t1.items()):
        for r in t["rows"]:
            k = T1_KEYS.get(r["label"])
            if not k:
                continue
            crows.append({"date": m + "-01", "series": k, "label": labels.get(k, {}).get("label", r["label"]),
                          "label_zh": r["label"], "weight_pct": round(r["weight_pm"] / 10, 4), "index": r["index"],
                          "mom": r["mom"], "mom_pp": r["mom_pp"], "yoy": r["yoy"], "yoy_pp": r["yoy_pp"],
                          "ytd": r["ytd"], "ytd_pp": r["ytd_pp"], "release_date": t.get("release_date", "")})
            if k in GROUPS7 or k in ("all",) or r["weight_pm"] < 1000:
                wrows.append({"date": m + "-01", "level": "group", "key": k, "label": labels.get(k, {}).get("label", r["label"]),
                              "weight_pct": round(r["weight_pm"] / 10, 4), "source": "release table 1"})
    for m, it in sorted(t14.items()):
        for code, i in sorted(it.items()):
            wrows.append({"date": m + "-01", "level": "item", "key": code, "label": i["name"],
                          "weight_pct": i["weight_pct"], "source": "release table 14"})
    _write_csv(OUT / "tw_cpi_contrib.csv", ["date", "series", "label", "label_zh", "weight_pct", "index", "mom", "mom_pp",
                                            "yoy", "yoy_pp", "ytd", "ytd_pp", "release_date"], crows)
    _write_csv(OUT / "tw_cpi_weights.csv", ["date", "level", "key", "label", "weight_pct", "source"], wrows)
    (OUT / "tw_cpi_checks.json").write_text(json.dumps({"rates_vs_index": stats, "weights_vs_headline": wcheck,
                                                       "item_weight_sums": wsum14}, indent=1) + "\n")
    code = f"C{latest}"
    label = f"{LONGMONTHS[int(latest[5:7]) - 1]} {latest[:4]}"
    src = "DGBAS"

    def long_rows():
        for r in rows:
            unit = "index 2021=100" if r["measure"] in ("index", "sa_index") else "%"
            yield {"country": "TW", "indicator": "cpi", "series": f"{r['series']}_{r['measure']}", "label": r["label"],
                   "measure": r["measure"], "area": r["area"], "freq": "M", "date": r["date"], "value": r["value"],
                   "unit": unit, "source": src, "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    # Asia tab: concepts DGBAS publishes on a matching definition (food and CPI ex food and energy are
    # open decisions: DGBAS's food includes eating out and alcohol)
    asia = []
    for r in rows:
        if r["area"] == "national" and r["measure"] == "yoy" and r["series"] in ("all", "energy"):
            asia.append({"country": "TW", "concept": {"all": "headline_yoy", "energy": "energy_yoy"}[r["series"]],
                         "series_id": f"tw.cpi.{r['series']}.yoy", "date": r["date"], "value": r["value"],
                         "unit": "% y/y", "basis": "published", "source": "DGBAS", "base_break": r["base_break"],
                         "release_date": r["release_date"]})
    _write_csv(OUT / "asia.csv", ["country", "concept", "series_id", "date", "value", "unit", "basis", "source",
                                  "base_break", "release_date"], asia)
    payload = json.dumps({k: v for k, v in raw.items() if v}, ensure_ascii=False).encode()
    fp = hashlib.sha256(payload).hexdigest()[:12]
    (RAWDIR / f"{code}_{fp}.json.gz").write_bytes(gzip.compress(payload))
    (RAWDIR / "cpispl.xls").write_bytes(blob)
    release = {"code": code, "label": label, "latest_month": latest + "-01", "release_date": rel_dates.get(latest, ""),
               "table": "DGBAS Macro Database (nstatdb) price tables; monthly releases on stat.gov.tw"}
    write_release(OUT, release, warnings, len(rows),
                  {"long_rows": nlong, "items": n_items, "release_months": len(t1),
                   "rate_checks": stats, "weights_max_diff": max((abs(w["diff"]) for w in wcheck), default=None)})
    return {"updated": True, "code": code,
            "summary": f"{label}: {len(rows)} rows, {n_items} items, {len(t1)} release tables; "
                       f"rates vs index {stats['tested']} tested, max {stats['max']:.3f}; "
                       f"weights vs headline max {max((abs(w['diff']) for w in wcheck), default=0):.3f}",
            "warnings": warnings}


def _write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r.get(c) is None else r.get(c) for c in cols])
