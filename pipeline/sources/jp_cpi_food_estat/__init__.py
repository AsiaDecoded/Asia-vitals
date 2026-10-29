"""Japan CPI food and non-alcoholic beverages (COICOP division 01): Asia Decoded calculation.

Japan's Food group (食料, code 0002) also contains alcoholic beverages (酒類, 0041) and eating out
(外食, 0042, school lunches included), which COICOP puts in divisions 02 and 11. Food and
non-alcoholic beverages is Food less those two, the cross-Asia comparable food measure.

Index: Japan's CPI is a fixed-base Laspeyres index, so within one base a part is removed by subtraction:
    D = (wF x I_food - wA x I_alcohol - wE x I_eating_out) / (wF - wA - wE)
with each base's published indices and weights. Each base is used for the months whose official rates are
on it (2010 base Jan 2010-Dec 2015, 2015 base 2016-2020, 2020 base 2021-2025, 2025 base from Jan 2026),
and the bases are chained at the official link month, December before each new base takes over
(Dec 2015, Dec 2020, Dec 2025). y/y is the 12-month change in the chained index, from Jan 2011.
base_break = 1 in the first month on new weights (Jan 2016, Jan 2021, Jan 2026): the y/y of that month
and the 11 after it compare months on different weights.

Weights per 10,000, as published by the Statistics Bureau: 2010 and 2015 bases from the e-Stat database
tables (weight field), 2020 and 2025 bases from Table 5 of the monthly report (raw files kept by
jp_cpi_contrib_estat); the 2015 table's weights are checked against Table 5.

Checks (errors stop the source): the 12 food subgroups, with the same weights and formula, reproduce the
published Food index every month (max gap reported; tolerance 0.15 index points, the rounding of
one-decimal indices); subgroup weights sum to the Food weight (within 6 per 10,000: each published weight
is rounded to a whole number; the kept weight is Food less the two excluded weights, so kept + excluded =
Food exactly); no gaps in y/y; latest month equals the
latest national CPI month (data/jp/cpi/release.json).
"""
import csv
import gzip
import hashlib
import json
import re

from core import estat
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "jp_cpi_food_estat"
DESCRIPTION = "Japan CPI food and non-alcoholic beverages (COICOP 01), calculated from e-Stat"
OUT = DATA / "jp" / "cpi_food"
TABLE5_RAW = RAW / "jp" / "cpi_contrib"  # Table 5 files, downloaded by jp_cpi_contrib_estat
MONTH_RE = re.compile(r"^(\d{4})00(0[1-9]|1[0-2])\2$")  # e.g. 2026000909 = Sep 2026
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
FOOD = ("0002", "food", "食料")
# the 12 subgroups of Food (code, key, name in Table 5); alcohol and eating out are the excluded parts
SUBS = [("0003", "cereals", "穀類"), ("0008", "fish", "魚介類"), ("0013", "meat", "肉類"), ("0016", "dairy_eggs", "乳卵類"),
        ("0021", "vegetables", "野菜・海藻"), ("0027", "fruits", "果物"), ("0030", "oils_seasonings", "油脂・調味料"),
        ("0033", "confectionery", "菓子類"), ("0034", "prepared_food", "調理食品"), ("0037", "beverages", "飲料"),
        ("0041", "alcohol", "酒類"), ("0042", "eating_out", "外食")]
EXCLUDED = ("alcohol", "eating_out")
CODES = {c: k for c, k, _ in [FOOD] + SUBS}
# base: (e-Stat table, weights from the table's weight field (True) or Table 5 (False), first and last month on it)
BASES = {
    2010: ("0003036792", True, "2010-01-01", "2015-12-01"),
    2015: ("0003143513", True, "2016-01-01", "2020-12-01"),
    2020: ("0003427113", False, "2021-01-01", "2025-12-01"),
    2025: ("0004052037", False, "2026-01-01", "9999-12-01"),
}
TOL_RECOMBINE = 0.15  # index points
TOL_WEIGHTS = 6  # per 10,000: the 12 published subgroup weights are each rounded to a whole number


def _shift(d, months):
    y, m = int(d[:4]), int(d[5:7]) - 1 + months
    return f"{y + m // 12}-{m % 12 + 1:02d}-01"


def _fetch(table, weights_in_table):
    tabs = "1,3,5" if weights_in_table else "1,3"
    vals = estat.get_values(table, cdArea="00000", cdTab=tabs, cdCat01=",".join(CODES))
    series, weights = {}, {}
    for v in vals:
        key = CODES.get(v.get("cat01"))
        try:
            x = float(v.get("value"))
        except (TypeError, ValueError):
            continue
        if key is None:
            continue
        if v.get("tab") == "5":
            weights[key] = x
            continue
        m = MONTH_RE.match(v.get("time", ""))
        if not m:
            continue
        d = f"{m.group(1)}-{m.group(2)}-01"
        series.setdefault(key, {}).setdefault(d, {})["index" if v["tab"] == "1" else "yoy"] = x
    return series, weights


def _table5_weights():
    """{base: {key: weight}} from the latest Table 5 file on each base."""
    from sources.jp_cpi_contrib_estat import _norm, _sheet_rows
    names = {n: k for _, k, n in [FOOD] + SUBS}
    out = {}
    for p in sorted(TABLE5_RAW.glob("*.gz"), reverse=True):
        rows = _sheet_rows(gzip.decompress(p.read_bytes()))
        head = " ".join(_norm(c) for r in rows[:14] for c in r if isinstance(c, str))
        m = re.search(r"(\d{4})年基準", head)
        base = int(m.group(1)) if m else (2015 if "平成27年" in head else None)
        if base is None or base in out:
            continue
        jw = next((j for r in rows[:20] for j, c in enumerate(r) if _norm(c).startswith("ウエイト")), None)
        if jw is None:
            continue
        w = {}
        for r in rows:
            if len(r) <= jw:
                continue
            for c in r[:jw]:
                k = names.get(_norm(c)) if isinstance(c, str) else None
                if k and k not in w:
                    try:
                        w[k] = float(r[jw])
                    except (TypeError, ValueError):
                        pass
                    break
        out[base] = w
    return out


def update(**_):
    state = read_json(OUT / "release.json", {}) or {}
    t5 = _table5_weights()
    data = {}
    for b, (table, in_table, *_r) in BASES.items():
        s, wt = _fetch(table, in_table)
        data[b] = {"series": s, "weights": wt if in_table else t5.get(b, {})}
    nat = read_json(DATA / "jp" / "cpi" / "release.json", {}) or {}
    fp = hashlib.sha256(json.dumps([data, nat.get("national_month")], sort_keys=True).encode()).hexdigest()[:16]
    if fp == state.get("fingerprint") and (OUT / "jp_cpi_food.csv").exists():
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('latest_month')})"}

    errors, warnings, wgap = [], [], {}
    keys = [FOOD[1]] + [k for _, k, _ in SUBS]
    # weights: complete, subgroups sum to Food, 2015 table agrees with Table 5
    for b in BASES:
        w = data[b]["weights"]
        miss = [k for k in keys if k not in w]
        if miss:
            errors.append(f"{b} base: weights missing for {', '.join(miss)}")
            continue
        tot = sum(w[k] for _, k, _ in SUBS)
        wgap[b] = tot - w["food"]
        if abs(tot - w["food"]) > TOL_WEIGHTS:
            errors.append(f"{b} base: subgroup weights sum to {tot:g}, Food weight {w['food']:g}")
    if 2015 in t5:
        diff = {k: (data[2015]["weights"].get(k), t5[2015].get(k)) for k in keys
                if abs((data[2015]["weights"].get(k) or -1) - (t5[2015].get(k) or -2)) > 0.5}
        if diff:
            errors.append(f"2015-base weights: e-Stat table and Table 5 differ {diff}")
    else:
        errors.append("no 2015-base Table 5 file found for the weight cross-check")
    if errors:
        raise CheckFailed(errors)

    # derived index per base, recombination check, chain at each link month
    chain, meta, max_gap = {}, {}, (0.0, None)
    prev_last = None
    for b, (_t, _i, first, last) in BASES.items():
        w, s = data[b]["weights"], data[b]["series"]
        kept_w = w["food"] - sum(w[k] for k in EXCLUDED)
        link = _shift(first, -1) if prev_last else None
        months = sorted(d for d in s.get("food", {}) if first <= d <= last)
        need = ([link] if link else []) + months
        D = {}
        for d in need:
            try:
                I = {k: s[k][d]["index"] for k in keys}
            except KeyError as e:
                errors.append(f"{d[:7]} ({b} base): index missing for {e}")
                continue
            rec = sum(w[k] * I[k] for _, k, _ in SUBS) / sum(w[k] for _, k, _ in SUBS)
            gap = abs(rec - I["food"])
            if gap > max_gap[0]:
                max_gap = (gap, d)
            if gap > TOL_RECOMBINE:
                errors.append(f"{d[:7]} ({b} base): subgroups give Food {rec:.3f}, published {I['food']}")
            D[d] = (w["food"] * I["food"] - sum(w[k] * I[k] for k in EXCLUDED)) / kept_w
        if not months:
            errors.append(f"{b} base: no months")
            continue
        if link:
            if link not in D or link not in chain:
                errors.append(f"{b} base: link month {link[:7]} missing")
                continue
            factor = chain[link] / D[link]
        else:
            factor = 1.0
        for i, d in enumerate(months):
            if d in D:
                chain[d] = D[d] * factor
                meta[d] = {"base": b, "weight": kept_w, "base_break": 1 if (link and i == 0) else 0}
        prev_last = months[-1]
    if errors:
        raise CheckFailed(errors[:40])

    rows, worst = [], (0.0, None)
    for d in sorted(chain):
        p = _shift(d, -12)
        if p not in chain:
            continue
        yoy = (chain[d] / chain[p] - 1) * 100
        b = meta[d]["base"]
        s, w = data[b]["series"], data[b]["weights"]
        y = {k: s[k].get(d, {}).get("yoy") for k in ("food",) + EXCLUDED}
        # comparison only: the parts' published y/y combined on this month's base (the Bureau's practice for
        # its own aggregates); differs from the chained y/y mainly in the 12 months after a link
        try:
            sh = {k: w[k] * s[k][p]["index"] for k in ("food",) + EXCLUDED}
            same_base = (sh["food"] * y["food"] - sum(sh[k] * y[k] for k in EXCLUDED)) / (sh["food"] - sum(sh[k] for k in EXCLUDED))
            if abs(same_base - yoy) > worst[0]:
                worst = (abs(same_base - yoy), d)
        except (KeyError, TypeError):
            pass
        rows.append({"date": d, "base": b, "base_break": meta[d]["base_break"], "weight": round(meta[d]["weight"], 1),
                     "index": round(chain[d], 3), "yoy": round(yoy, 2), "food_group_yoy": y["food"],
                     "alcohol_yoy": y["alcohol"], "eating_out_yoy": y["eating_out"]})
    dates = [r["date"] for r in rows]
    if not dates:
        raise CheckFailed(["no months calculated"])
    for x, y2 in zip(dates, dates[1:]):
        if _shift(x, 1) != y2:
            errors.append(f"gap in y/y between {x[:7]} and {y2[:7]}")
    if dates[0] != "2011-01-01":
        errors.append(f"y/y starts {dates[0][:7]}, expected 2011-01")
    if nat.get("national_month") != dates[-1]:
        errors.append(f"latest month {dates[-1][:7]} is not the latest national CPI month ({nat.get('national_month')})")
    if errors:
        raise CheckFailed(errors[:40])
    warnings.append("subgroup weights less Food weight, by base: " + ", ".join(f"{b} {g:+g}" for b, g in wgap.items()))
    warnings.append(f"subgroup recombination: max gap {max_gap[0]:.3f} index points ({max_gap[1][:7]}), tolerance {TOL_RECOMBINE}")
    warnings.append(f"chained y/y vs parts' published y/y combined on one base: max difference {worst[0]:.2f}pp ({worst[1][:7] if worst[1] else '-'})")

    latest = dates[-1]
    code = f"F{latest[:7]}"
    OUT.mkdir(parents=True, exist_ok=True)
    cols = ["date", "base", "base_break", "weight", "index", "yoy", "food_group_yoy", "alcohol_yoy", "eating_out_yoy"]
    with open(OUT / "jp_cpi_food.csv", "w", newline="") as f:
        wr = csv.writer(f, lineterminator="\n")
        wr.writerow(cols)
        for r in rows:
            wr.writerow(["" if r[c] is None else r[c] for c in cols])
    nlong = write_long(({"country": "JP", "indicator": "cpi", "series": "food_nab",
                         "label": "Food and non-alcoholic beverages (COICOP 01)", "measure": "yoy",
                         "area": "national", "freq": "M", "date": r["date"], "value": r["yoy"], "unit": "%",
                         "source": "Asia Decoded calculation from Statistics Bureau of Japan data", "release": code}
                        for r in rows), OUT / "long.csv")
    release = {"code": code, "label": f"{MONTHS[int(latest[5:7]) - 1]} {latest[:4]}", "latest_month": latest,
               "series_id": "JP_food_nab: 0002 Food less 0041 alcoholic beverages and 0042 eating out",
               "link_months": [_shift(BASES[b][2], -1) for b in list(BASES)[1:]],
               "weights": {str(b): data[b]["weights"] for b in BASES},
               "checks": {"recombination_max_gap": round(max_gap[0], 3), "recombination_tolerance": TOL_RECOMBINE,
                          "vs_same_base_max_pp": round(worst[0], 2), "subgroup_weight_gaps": wgap}}
    write_release(OUT, release, warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{release['label']}: {len(rows)} months", "warnings": warnings}
