"""Hong Kong CPI: Census and Statistics Department (C&SD), as published. Nothing is calculated.

Four CPI series (Composite, CPI(A), CPI(B), CPI(C); Oct 2019 - Sep 2020 = 100), headline and underlying
(net of the Government's one-off relief measures):
- web tables 510-60001 (all items), 510-60001A (9 sections), 510-60002/60002A (underlying), 510-60003
  (13 COICOP 2018 divisions), 510-60004 (seasonally adjusted, average monthly change over the latest 3 months);
- Table E501 (CSV zip published with each release): sections incl. meals out and basic food, and the 75
  commodity/service groups (+ private and public housing rent), index, y/y and m/m;
- the web Monthly Report on the CPI: contributions of the sections to Composite CPI y/y (Table 3.05, one month
  per issue; every web issue from Jun 2023 is kept), seasonally adjusted index and m/m for all items and food
  (3.08, 3.09; 36-month window of the latest issue) and the SA 3-month averages incl. underlying (3.06, 3.07);
- CPI expenditure weights, % of CPI, by section and group (Annex 1 to the monthly report: the 2025 reference year,
  used from Apr 2026, and 2024, Apr 2025 - Mar 2026).

New data: the latest issue of the monthly report (B1060001<yyyy>MM<mm>) in C&SD's product index.
"""
import csv
import gzip
import hashlib
import io
import json
import re

from core import censtatd
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "hk_cpi_censtatd"
DESCRIPTION = "Hong Kong CPI (C&SD): Composite, A, B, C; headline and underlying; sections, groups, COICOP, SA, contributions, weights"
OUT = DATA / "hk" / "cpi"
RAWDIR = RAW / "hk" / "cpi_censtatd"
SRC = "Census and Statistics Department, Hong Kong"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

INDICES = {"CC": "composite", "A": "a", "B": "b", "C": "c"}  # C&SD stat-var prefix -> our key
INDEX_LABEL = {"composite": "Composite CPI", "a": "CPI(A)", "b": "CPI(B)", "c": "CPI(C)"}
E501_SHEETS = {"E501-1": ("composite", "section"), "E501-2": ("a", "section"), "E501-3": ("b", "section"),
               "E501-4": ("c", "section"), "E501-5": ("composite", "group"), "E501-6": ("a", "group"),
               "E501-7": ("b", "group"), "E501-8": ("c", "group")}
# Sections: C&SD code in E501 / in 510-60001A (S1..S9) / Annex 1 heading -> key, label
SECTIONS = [("0", "", "ALL ITEMS", "all", "All items"), ("1", "S1", "FOOD", "food", "Food"),
            ("1.1", "", "Meals out and takeaway food", "meals_out", "Meals out and takeaway food"),
            ("1.2", "", "Basic food", "basic_food", "Basic food"),
            ("2", "S2", "HOUSING", "housing", "Housing"), ("3", "S3", "ELECTRICITY, GAS AND WATER", "egw", "Electricity, gas and water"),
            ("4", "S4", "ALCOHOLIC DRINKS AND TOBACCO", "alcohol_tobacco", "Alcoholic drinks and tobacco"),
            ("5", "S5", "CLOTHING AND FOOTWEAR", "clothing", "Clothing and footwear"),
            ("6", "S6", "DURABLE GOODS", "durables", "Durable goods"), ("7", "S7", "MISCELLANEOUS GOODS", "misc_goods", "Miscellaneous goods"),
            ("8", "S8", "TRANSPORT", "transport", "Transport"), ("9", "S9", "MISCELLANEOUS SERVICES", "misc_services", "Miscellaneous services")]
SEC_BY_E501 = {c: (k, lab) for c, _s, _a, k, lab in SECTIONS}
SEC_BY_S = {s: (k, lab) for _c, s, _a, k, lab in SECTIONS if s}
NINE = [k for _c, s, _a, k, _l in SECTIONS if s]
COICOP = {"1": "Food and non-alcoholic beverages", "2": "Alcoholic beverages and tobacco", "3": "Clothing and footwear",
          "4": "Housing, water, electricity, gas and other fuels", "5": "Furnishings, household equipment and routine household maintenance",
          "6": "Health", "7": "Transport", "8": "Information and communication", "9": "Recreation, sport and culture",
          "10": "Education services", "11": "Restaurants and accommodation services", "12": "Insurance and financial services",
          "13": "Personal care, social protection and miscellaneous goods and services"}
MEAS = {"Index": "index", "Month-to-month % change": "mom", "Year-on-year % change": "yoy"}
# Documented breaks: y/y from the 2019/20-based series from Oct 2020; new expenditure weights in Apr 2025 and
# Apr 2026 (2024/25 HES and a new group classification). Earlier weight vintages are not flagged here.
BREAKS = {"2020-10-01", "2025-04-01", "2026-04-01"}
# Composite groups the dashboard charts over time (food and energy, housing, heat table); the rest only in hk_cpi.csv
DASH_GROUPS = {"g23_1", "g23_2", "g24", "g25", "g26", "g57", "g66", "g69"}

# Release figures to check against (C&SD press release, 22 Oct 2026, September 2026)
RELEASE_SEP_2026 = {("composite", "headline", "all", "yoy"): 1.9, ("composite", "headline", "all", "index"): 111.2,
                    ("a", "headline", "all", "yoy"): 1.4, ("b", "headline", "all", "yoy"): 2.0, ("c", "headline", "all", "yoy"): 2.3,
                    ("composite", "underlying", "all", "yoy"): 2.1, ("a", "underlying", "all", "yoy"): 1.7,
                    ("b", "underlying", "all", "yoy"): 2.2, ("c", "underlying", "all", "yoy"): 2.4,
                    ("composite", "headline", "egw", "yoy"): 12.9, ("composite", "headline", "misc_services", "yoy"): 5.3,
                    ("composite", "headline", "transport", "yoy"): 5.2, ("composite", "headline", "misc_goods", "yoy"): 2.1,
                    ("composite", "headline", "durables", "yoy"): 1.1, ("composite", "headline", "meals_out", "yoy"): 1.0,
                    ("composite", "headline", "clothing", "yoy"): 0.3, ("composite", "headline", "housing", "yoy"): 0.2,
                    ("composite", "headline", "alcohol_tobacco", "yoy"): -0.4, ("composite", "headline", "basic_food", "yoy"): -0.2}


def _d(period):
    p = str(period)
    return f"{p[:4]}-{p[4:6]}-01" if len(p) == 6 else None


def _shift(d, k):
    y, m = int(d[:4]), int(d[5:7]) - 1 + k
    return f"{y + m // 12}-{m % 12 + 1:02d}-01"


def _f(v):
    return None if v in ("", None) else float(v)


def _write_csv(path, cols, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r.get(c) is None else r[c] for c in cols])


def _group_key(code):
    return "g" + code.replace(".", "_")


def _web(tid, basis, store, level):
    """Rows of a 510-600xx table into store[(index_type, basis, series, date)] = {measure: value}, plus labels."""
    hdr, rows = censtatd.table(tid)
    labels = {}
    for r in rows:
        if r.get("freq") != "M":
            continue
        d = _d(r["period"])
        sv = r["sv"]
        it = INDICES.get(re.sub(r"^U", "", sv).split("_")[0])
        meas = MEAS.get(r.get("svDesc"))
        if not d or not it or not meas or r.get("figure") in ("", None):
            continue
        if "GROUP" in r:
            g = r.get("GROUP") or ""
            if g == "":
                key, lab = "all", "All items"
            elif g in SEC_BY_S:
                key, lab = SEC_BY_S[g]
            else:
                continue
        elif "COICOP" in r:
            c = str(r.get("COICOP") or "")
            if c == "":
                continue  # total = all items, taken from 510-60001
            key, lab = f"coicop_{int(c):02d}", COICOP.get(c, r.get("COICOPDesc"))
        else:
            key, lab = "all", "All items"
        labels[key] = (lab, level if key != "all" else "all")
        store.setdefault((it, basis, key, d), {})[meas] = float(r["figure"])
    return hdr, labels


def _mdt(text):
    return list(csv.DictReader(io.StringIO(text)))


def _contrib_issue(code):
    """Published contributions from one web report issue: {code, table, labels, csv} or None."""
    d = f"{censtatd.BASE}/wbr/B1060001/{code}/data/"
    tids = censtatd.get_json(f"{d}en/wbr.json").get("tb_code_list") or []
    tid = "CPI_R_3_05" if "CPI_R_3_05" in tids else None
    if not tid:
        for t in tids:
            if "Contribution" in (censtatd.get_json(f"{d}en/table_{t}_lang.json").get("tb_title") or ""):
                tid = t
                break
    if not tid:
        return None
    t = censtatd.report(code, tables=[tid])["tables"][tid]
    return {"code": code, "table": tid, "labels": censtatd.class_labels(t["lang"]), "csv": next(iter(t["data"].values()))}


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    RAWDIR.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    reps = censtatd.issues("B1060001", n=2)
    web = [r for r in reps if r["web"] and r["code"]]
    if not web:
        raise CheckFailed(["no web issue of the Monthly Report on the CPI found"])
    code = web[0]["code"]
    if code == state.get("report_code") and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no new report (latest {code})"}
    warnings, errors = [], []

    # 1. Web tables
    store, labels = {}, {}
    hdrs = {}
    for tid, basis, level in (("510-60001", "headline", "all"), ("510-60001A", "headline", "section"),
                              ("510-60002", "underlying", "all"), ("510-60002A", "underlying", "section"),
                              ("510-60003", "headline", "coicop")):
        h, lab = _web(tid, basis, store, level)
        hdrs[tid] = h.get("title")
        labels.update(lab)
    _, sa_rows = censtatd.table("510-60004")
    sa3 = {}
    for r in sa_rows:
        d, it = _d(r["period"]), INDICES.get(r["sv"][1:].split("_")[0])
        if d and it and r.get("figure") not in ("", None):
            sa3[(it, d)] = float(r["figure"])

    # 2. Table E501, latest issue
    e_issues = censtatd.issues("D5600001", n=1)
    e_code = e_issues[0]["code"]
    sheets, e_raw = censtatd.e501(e_code)
    (RAWDIR / f"{e_code}.zip").write_bytes(e_raw)
    e501 = {}
    for sh, (it, kind) in E501_SHEETS.items():
        if sh not in sheets:
            errors.append(f"E501 sheet {sh} missing")
            continue
        p = sheets[sh]
        for c in p["codes"]:
            if kind == "section":
                key, lab = SEC_BY_E501.get(c, (None, None))
                if not key:
                    errors.append(f"E501 {sh}: unknown section code {c}")
                    continue
                labels.setdefault(key, (lab, "section" if key != "all" else "all"))
                if key in ("meals_out", "basic_food"):
                    labels[key] = (lab, "subsection")
            else:
                key = _group_key(c)
                labels[key] = (p["names"][c], "subgroup" if "." in c else "group")
        for d, c, idx, yoy, mom in p["rows"]:
            key = SEC_BY_E501[c][0] if kind == "section" else _group_key(c)
            if not key:
                continue
            e501[(it, "headline", key, d)] = {k: v for k, v in (("index", idx), ("yoy", yoy), ("mom", mom)) if v is not None}
    # Sections in both sources must agree; E501 adds meals out, basic food and the groups
    nmis = 0
    for k, v in e501.items():
        if k[2] in NINE or k[2] == "all":
            w = store.get(k)
            if w is None:
                continue
            for m in ("index", "yoy", "mom"):
                if m in v and m in w and abs(v[m] - w[m]) > 0.051:
                    nmis += 1
                    if nmis <= 5:
                        errors.append(f"E501 and table 510-60001/60001A differ: {k} {m} {v[m]} vs {w[m]}")
        else:
            store[k] = v
    if nmis > 5:
        errors.append(f"... {nmis} differences between E501 and the web tables in all")

    # 3. Latest report issue: contributions, SA series, weights annex
    rep = censtatd.report(code, tables=["CPI_R_3_06", "CPI_R_3_07", "CPI_R_3_08", "CPI_R_3_09"])
    sa = []
    for tid, t in rep["tables"].items():
        for (sv, sp), text in t["data"].items():
            und = sv.startswith("US")
            it = INDICES.get(re.sub(r"^U?S", "", sv).split("_")[0])
            meas = {"Raw_1dp_idx_n": "sa_index", "MoM_1dp_%_s": "sa_mom", "MoM3ma_1dp_%_s": "sa_mom3"}.get(sp)
            for r in _mdt(text):
                g = r.get("GROUP", "")
                series = "all" if g == "" else ("food" if g == "S1" else None)
                if not series or not it or not meas or r.get("obs_value") in ("", None):
                    continue
                sa.append({"date": f"{int(r['CCYY']):04d}-{int(r['MM']):02d}-01", "index_type": it,
                           "basis": "underlying" if und else "headline", "series": series, "measure": meas,
                           "value": round(float(r["obs_value"]), 1), "vintage": code, "table": tid})
    for (it, d), v in sa3.items():
        sa.append({"date": d, "index_type": it, "basis": "headline", "series": "all", "measure": "sa_mom3_long",
                   "value": v, "vintage": code, "table": "510-60004"})
    links = censtatd.annex_links(rep["wbr"])
    annex = next((u for t, u in links.items() if t.startswith("Annex 1")), None)
    weights = []
    if not annex:
        errors.append("Annex 1 (expenditure weights) link not found in the report")
    else:
        import openpyxl  # installed by the workflow
        xbytes = censtatd.get(annex)
        (RAWDIR / "annex1_weights.xlsx").write_bytes(xbytes)
        wb = openpyxl.load_workbook(io.BytesIO(xbytes), read_only=True, data_only=True)
        for ws in wb.worksheets:
            m = re.match(r"(\d{4}) CPI weights", ws.title)
            if not m:
                continue
            ref = m.group(1)
            rows = list(ws.iter_rows(values_only=True))
            adopted = next((str(r[0]) for r in rows if r and isinstance(r[0], str) and r[0].startswith("(Adopted")), "")
            section = None
            for r in rows:
                if len(r) < 7 or not isinstance(r[3], (int, float)):
                    continue
                name = (r[2] or "").strip()
                if r[0] is None:
                    sec = next(((k, lab) for c, _s, a, k, lab in SECTIONS if a == name), None)
                    if name.startswith("Basic food"):
                        key, level, lab = "basic_food", "subsection", "Basic food"
                    elif sec:
                        key, lab = sec
                        level = "all" if key == "all" else "section"
                        section = key
                    else:
                        continue
                else:
                    code_g = str(r[0]).rstrip("0").rstrip(".") if isinstance(r[0], float) else str(r[0])
                    key, level, lab = _group_key(code_g), "subgroup" if "." in code_g else "group", name
                    if code_g == "1":
                        key, level = "meals_out", "subsection"
                for it, col in (("composite", 3), ("a", 4), ("b", 5), ("c", 6)):
                    if isinstance(r[col], (int, float)):
                        weights.append({"reference_year": ref, "adopted": adopted, "index_type": it, "series": key,
                                        "label": lab, "level": level, "section": section if level not in ("all", "section") else key,
                                        "weight_pct": round(float(r[col]), 2)})
        # weights add up (as published, to two decimals)
        for ref in sorted({w["reference_year"] for w in weights}):
            for it in INDICES.values():
                W = [w for w in weights if w["reference_year"] == ref and w["index_type"] == it]
                secs = sum(w["weight_pct"] for w in W if w["level"] == "section")
                grps = sum(w["weight_pct"] for w in W if w["level"] in ("group", "subsection") and w["series"] != "basic_food")
                if abs(secs - 100) > 0.06:
                    errors.append(f"weights {ref} {it}: sections sum to {secs:.2f}")
                if abs(grps - 100) > 0.06:
                    errors.append(f"weights {ref} {it}: groups sum to {grps:.2f}")
        if not {"2024", "2025"} <= {w["reference_year"] for w in weights}:
            errors.append("Annex 1: 2024 and 2025 weights not both found")

    # 4. Published contributions, one per web issue (cached in raw/)
    cdir = RAWDIR / "contrib"
    cdir.mkdir(parents=True, exist_ok=True)
    all_issues = censtatd.issues("B1060001", n=80)
    contrib = []
    for it_ in all_issues:
        if not it_["web"] or not it_["code"]:
            continue
        f = cdir / f"{it_['code']}.json.gz"
        if f.exists() and it_["code"] != code:
            rec = json.loads(gzip.decompress(f.read_bytes()))
        else:
            rec = _contrib_issue(it_["code"])
            if rec is None:
                warnings.append(f"{it_['code']}: no contribution table")
                continue
            f.write_bytes(gzip.compress(json.dumps(rec, ensure_ascii=False).encode()))
        for r in _mdt(rec["csv"]):
            if r.get("obs_value") in ("", None):
                continue
            g = r.get("GROUP", "")
            if g == "":
                part, lab = "all", "All items"
            elif g in SEC_BY_S:
                part, lab = SEC_BY_S[g]
            else:
                lab = rec["labels"].get(g, g)
                part = {"Meals out and takeaway food": "meals_out", "Basic food": "basic_food"}.get(lab, "")
                if not part:
                    continue
            contrib.append({"date": f"{int(r['CCYY']):04d}-{int(r['MM']):02d}-01", "series": part, "label": lab,
                            "contrib_pp": round(float(r["obs_value"]), 1), "issue": rec["code"]})

    # Checks
    latest = f"{code[8:12]}-{code[14:16]}-01"
    if state.get("latest_month") and latest < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one stored ({state['latest_month']})")
    req = [("composite", "headline", "all", m) for m in ("index", "yoy", "mom")]
    req += [(it, b, "all", "yoy") for it in INDICES.values() for b in ("headline", "underlying")]
    req += [("composite", "headline", k, "yoy") for k in NINE + ["meals_out", "basic_food"]]
    req += [("composite", "headline", f"coicop_{i:02d}", "yoy") for i in range(1, 14)]
    for k in req:
        if k[3] not in store.get(k[:3] + (latest,), {}):
            errors.append(f"latest month {latest}: {k} missing")
    ngroups = len({k[2] for k in store if k[0] == "composite" and k[3] == latest and k[2].startswith("g") and "yoy" in store[k]})
    if ngroups < 75:
        errors.append(f"latest month: {ngroups} groups with y/y, expected at least 75")
    if ("composite", latest) not in sa3:
        errors.append("latest month: SA 3-month average (510-60004) missing")
    if not any(r["date"] == latest and r["series"] == "all" for r in contrib):
        errors.append("latest month: published contributions missing")
    # no gaps in headline y/y over the full history
    for it, first in (("composite", "1981-10-01"), ("a", "1975-07-01"), ("b", "1975-07-01"), ("c", "1975-07-01")):
        d, gaps = first, []
        while d <= latest:
            if "yoy" not in store.get((it, "headline", "all", d), {}):
                gaps.append(d[:7])
            d = _shift(d, 1)
        if gaps:
            errors.append(f"{it} y/y gaps: {', '.join(gaps[:8])}{' …' if len(gaps) > 8 else ''} ({len(gaps)} months)")
    # published rates against published indices (same base: y/y from Oct 2020, m/m from Nov 2019); indices are
    # rounded to one decimal, C&SD's rates come from unrounded indices
    worst, nbig = (0, None), 0
    for (it, b, s, d), v in store.items():
        if s.startswith("g") or "index" not in v:
            continue
        for m, k, start in (("yoy", -12, "2020-10-01"), ("mom", -1, "2019-11-01")):
            p = store.get((it, b, s, _shift(d, k)), {}).get("index")
            if m in v and p and d >= start:
                diff = abs((v["index"] / p - 1) * 100 - v[m])
                if diff > worst[0]:
                    worst = (diff, (it, b, s, d[:7], m))
                if diff > 0.2:
                    nbig += 1
    if nbig:
        errors.append(f"{nbig} published rates more than 0.2pp from the published indices; worst {worst[0]:.2f} {worst[1]}")
    # published contributions: sections sum to the published all-items figure, and that equals published y/y
    by = {}
    for r in contrib:
        by.setdefault(r["date"], {})[r["series"]] = r["contrib_pp"]
    cmax = 0
    for d, parts in by.items():
        s = sum(parts.get(k, 0) for k in NINE)
        tot = parts.get("all")
        y = store.get(("composite", "headline", "all", d), {}).get("yoy")
        if tot is None or any(k not in parts for k in NINE):
            errors.append(f"contributions {d[:7]}: incomplete")
            continue
        cmax = max(cmax, abs(s - tot))
        if abs(s - tot) > 0.25:
            errors.append(f"contributions {d[:7]}: sections sum to {s:.1f}, all items {tot}")
        if y is not None and abs(tot - y) > 0.05:
            errors.append(f"contributions {d[:7]}: all items {tot} vs published y/y {y}")
    # release figures (September 2026)
    if latest >= "2026-09-01":
        for (it, b, s, m), v in RELEASE_SEP_2026.items():
            got = store.get((it, b, s, "2026-09-01"), {}).get(m)
            if got is None or abs(got - v) > 0.001:
                errors.append(f"Sep 2026 {it} {b} {s} {m}: {got} vs release {v}")
    if errors:
        raise CheckFailed(errors)

    # Release dates (C&SD schedule) for each reference month
    rel = {}
    try:
        for r in censtatd.schedule():
            m = re.match(r"Consumer Price Ind(?:ex|ices) for (\w+) (\d{4})$", (r["title"] or "").strip())
            if m and m.group(1) in MONTHS:
                rel[f"{m.group(2)}-{MONTHS.index(m.group(1)) + 1:02d}-01"] = r["date"]
    except Exception as e:  # noqa: BLE001
        warnings.append(f"release schedule not read: {e}")
    upcoming = sorted((d, k) for k, d in rel.items() if k > latest)[:6]

    # Write
    order = {k: i for i, (_c, _s, _a, k, _l) in enumerate(SECTIONS)}
    def ordkey(s):
        if s in order:
            return order[s]
        if s.startswith("coicop_"):
            return 100 + int(s[7:])
        if s.startswith("g"):
            parts = s[1:].split("_")
            return 200 + int(parts[0]) + (int(parts[1]) / 10 if len(parts) > 1 else 0)
        return 999
    rows = []
    for (it, b, s, d), v in store.items():
        lab, level = labels.get(s, (s, ""))
        rows.append({"date": d, "index_type": it, "basis": b, "series": s, "label": lab, "level": level,
                     "order": ordkey(s), "index": v.get("index"), "mom": v.get("mom"), "yoy": v.get("yoy"),
                     "base_break": 1 if d in BREAKS else "", "release_date": rel.get(d, "")})
    rows.sort(key=lambda r: (r["date"], r["index_type"], r["basis"], r["order"]))
    cols = ["date", "index_type", "basis", "series", "label", "level", "order", "index", "mom", "yoy", "base_break", "release_date"]
    _write_csv(OUT / "hk_cpi.csv", cols, rows)
    # dashboard copy: all four indices for all items; Composite sections and COICOP divisions; from 2015, the Composite
    # groups the page charts over time (DASH_GROUPS). The latest month of every Composite group goes to hk_cpi_groups.csv.
    dash = [r for r in rows if r["level"] == "all"
            or (r["index_type"] == "composite" and r["level"] in ("section", "subsection", "coicop"))
            or (r["index_type"] == "composite" and r["series"] in DASH_GROUPS and r["date"] >= "2015-01-01")]
    _write_csv(OUT / "hk_cpi_dash.csv", cols, dash)
    glatest = [r for r in rows if r["index_type"] == "composite" and r["basis"] == "headline"
               and r["level"] == "group" and r["date"] == latest]
    _write_csv(OUT / "hk_cpi_groups.csv", cols, glatest)
    sa.sort(key=lambda r: (r["measure"], r["index_type"], r["basis"], r["series"], r["date"]))
    _write_csv(OUT / "hk_cpi_sa.csv", ["date", "index_type", "basis", "series", "measure", "value", "vintage", "table"], sa)
    contrib.sort(key=lambda r: (r["date"], order.get(r["series"], 99)))
    _write_csv(OUT / "hk_cpi_contrib.csv", ["date", "series", "label", "contrib_pp", "issue"], contrib)
    _write_csv(OUT / "hk_cpi_weights.csv", ["reference_year", "adopted", "index_type", "series", "label", "level", "section", "weight_pct"], weights)

    label = f"{MONTHS[int(latest[5:7]) - 1]} {latest[:4]}"
    rcode = f"C{latest[:7]}"

    def long_rows():
        for r in rows:
            if r["series"].startswith("g"):
                continue  # groups stay in hk_cpi.csv; the common long file carries all items, sections and COICOP
            for m, unit in (("index", "index, Oct 2019-Sep 2020 = 100"), ("yoy", "%"), ("mom", "%")):
                yield {"country": "HK", "indicator": "cpi" if r["basis"] == "headline" else "cpi_underlying",
                       "series": f"{r['index_type']}_{r['series']}", "label": f"{INDEX_LABEL[r['index_type']]}: {r['label']}",
                       "measure": m, "area": "national", "freq": "M", "date": r["date"], "value": r[m], "unit": unit,
                       "source": SRC, "release": rcode}
    nlong = write_long(long_rows(), OUT / "long.csv")
    # latest-month row
    def g(it, b, s, d, m="yoy"):
        return store.get((it, b, s, d), {}).get(m)
    prev = _shift(latest, -1)
    lr = {"date": latest, "month": label, "prev_month": MONTHS[int(prev[5:7]) - 1], "release_date": rel.get(latest, ""),
          "next_release": upcoming[0][0] if upcoming else ""}
    for k in ["all", "food", "meals_out", "basic_food", "housing", "egw", "transport", "misc_services"]:
        lr[f"{k}_yoy"], lr[f"{k}_yoy_prev"] = g("composite", "headline", k, latest), g("composite", "headline", k, prev)
    lr["underlying_yoy"], lr["underlying_yoy_prev"] = g("composite", "underlying", "all", latest), g("composite", "underlying", "all", prev)
    lr["all_mom"] = g("composite", "headline", "all", latest, "mom")
    lr["sa3"], lr["sa3_prev"] = sa3.get(("composite", latest)), sa3.get(("composite", prev))
    for it in ("a", "b", "c"):
        lr[f"{it}_yoy"] = g(it, "headline", "all", latest)
    _write_csv(OUT / "hk_cpi_latest.csv", list(lr), [lr])

    blob = json.dumps({"titles": hdrs, "e501": e_code, "report": code}, ensure_ascii=False).encode()
    (RAWDIR / f"{rcode}_{hashlib.sha256(blob).hexdigest()[:10]}.json.gz").write_bytes(gzip.compress(blob))
    release = {"code": rcode, "label": label, "latest_month": latest, "release_date": rel.get(latest, ""),
               "report_code": code, "e501_code": e_code,
               "table": "C&SD web tables 510-60001/60001A/60002/60002A/60003/60004, Table E501, Monthly Report on the CPI (web), Annex 1"}
    write_release(OUT, release, warnings, len(rows),
                  {"long_rows": nlong, "contribution_months": len(by), "contribution_max_gap_pp": round(cmax, 2),
                   "worst_rate_vs_index_pp": round(worst[0], 3), "groups_latest": ngroups,
                   "upcoming_releases": [{"ref_month": k[:7], "date": d} for d, k in upcoming]})
    (OUT / "release_row.json").write_text(json.dumps([{**release, "upcoming": upcoming[0][0] if upcoming else ""}], indent=1) + "\n")
    return {"updated": True, "code": rcode,
            "summary": f"{label}: {len(rows)} rows, {ngroups} groups, {len(by)} months of published contributions, "
                       f"{len(weights)} weights; rates vs indices worst {worst[0]:.2f}pp; contributions max gap {cmax:.1f}pp",
            "warnings": warnings}
