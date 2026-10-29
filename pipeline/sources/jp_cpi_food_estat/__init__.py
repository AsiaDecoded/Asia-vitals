"""Japan CPI food and non-alcoholic beverages (COICOP division 01): Asia Decoded calculation.

Japan's Food group (食料, code 0002) also contains alcoholic beverages (酒類, 0041) and eating out
(外食, 0042, school lunches included), which COICOP puts in divisions 02 and 11. Food and
non-alcoholic beverages is Food less those two, the cross-Asia comparable food measure.

Calculation: Japan's CPI is a fixed-weight Laspeyres index, so within one base an aggregate is the
weight-average of its parts and a part can be removed by subtraction:
    index = (wF x I_food - wA x I_alcohol - wE x I_eating_out) / (wF - wA - wE)
y/y combines the three parts' published y/y rates, weighted by weight x index a year earlier
(the aggregation rule for a fixed-weight index; the published rates are calculated from unrounded
indices), and is checked against the 12-month change in the combined index. Because parts are
subtracted, rounding in the one-decimal inputs can move the result by up to about 0.1pp.

Weights per 10,000, as published by the Statistics Bureau: 2010 and 2015 bases from the e-Stat
database tables (weight field), checked for 2015 against Table 5 of the monthly report; 2020 and
2025 bases from Table 5 (Food 2626 and 2754, alcohol 119 and 111, eating out 460 and 508).
y/y uses the base the Bureau uses for that month's official rates: 2010 base for 2011-2015,
2015 base for 2016-2020, 2020 base for 2021-2025, 2025 base from 2026.
"""
import csv
import hashlib
import json
import re

from core import estat
from core.common import DATA, CheckFailed, read_json, write_long, write_release

NAME = "jp_cpi_food_estat"
DESCRIPTION = "Japan CPI food and non-alcoholic beverages (COICOP 01), calculated from e-Stat"
OUT = DATA / "jp" / "cpi_food"
MONTH_RE = re.compile(r"^(\d{4})00(0[1-9]|1[0-2])\2$")  # e.g. 2026000909 = Sep 2026
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
CODES = {"0002": "food", "0041": "alcohol", "0042": "eating_out"}
# base: (e-Stat table, published weights from Table 5 or None to read the table's weight field,
#        first and last y/y month on this base)
BASES = {
    2010: ("0003036792", None, "2011-01-01", "2015-12-01"),
    2015: ("0003143513", None, "2016-01-01", "2020-12-01"),
    2020: ("0003427113", {"food": 2626, "alcohol": 119, "eating_out": 460}, "2021-01-01", "2025-12-01"),
    2025: ("0004052037", {"food": 2754, "alcohol": 111, "eating_out": 508}, "2026-01-01", "9999-12-01"),
}
TABLE5_2015 = {"food": 2623, "alcohol": 119, "eating_out": 521}  # check for the 2015 table's weights


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
        if v.get("tab") == "5":
            weights[key] = x
            continue
        m = MONTH_RE.match(v.get("time", ""))
        if not m or key is None:
            continue
        d = f"{m.group(1)}-{m.group(2)}-01"
        series.setdefault(key, {}).setdefault(d, {})["index" if v["tab"] == "1" else "yoy"] = x
    return series, weights


def update(**_):
    state = read_json(OUT / "release.json", {}) or {}
    data = {}
    for b, (table, w, *_r) in BASES.items():
        s, wt = _fetch(table, w is None)
        data[b] = {"series": s, "weights": w or wt}
    fp = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
    if fp == state.get("fingerprint") and (OUT / "jp_cpi_food.csv").exists():
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('latest_month')})"}

    errors, warnings, rows = [], [], []
    w15 = data[2015]["weights"]
    if any(abs(w15.get(k, -1) - v) > 0.5 for k, v in TABLE5_2015.items()):
        errors.append(f"2015-base weights in the e-Stat table {w15} differ from Table 5 {TABLE5_2015}")
    for base, (_t, _w, first, last) in BASES.items():
        w, s = data[base]["weights"], data[base]["series"]
        if set(w) != set(CODES.values()):
            errors.append(f"{base} base: weights missing ({w})")
            continue
        wf = w["food"] - w["alcohol"] - w["eating_out"]
        F, A, E = s.get("food", {}), s.get("alcohol", {}), s.get("eating_out", {})
        months = sorted(d for d in F if first <= d <= last)
        for d in months:
            p = _shift(d, -12)
            try:
                i_d = {k: x[d]["index"] for k, x in (("food", F), ("alcohol", A), ("eating_out", E))}
                i_p = {k: x[p]["index"] for k, x in (("food", F), ("alcohol", A), ("eating_out", E))}
                y = {k: x[d]["yoy"] for k, x in (("food", F), ("alcohol", A), ("eating_out", E))}
            except KeyError as e:
                errors.append(f"{d[:7]} ({base} base): missing {e}")
                continue
            sh = {k: w[k] * i_p[k] for k in w}
            denom = sh["food"] - sh["alcohol"] - sh["eating_out"]
            yoy = (sh["food"] * y["food"] - sh["alcohol"] * y["alcohol"] - sh["eating_out"] * y["eating_out"]) / denom
            idx = lambda i: (w["food"] * i["food"] - w["alcohol"] * i["alcohol"] - w["eating_out"] * i["eating_out"]) / wf
            from_index = (idx(i_d) / idx(i_p) - 1) * 100
            if abs(from_index - yoy) > 0.3:
                errors.append(f"{d[:7]}: food y/y {yoy:.2f} vs from index {from_index:.2f}")
            rows.append({"date": d, "base": base, "index": round(idx(i_d), 3), "yoy": round(yoy, 2),
                         "food_group_yoy": y["food"], "alcohol_yoy": y["alcohol"], "eating_out_yoy": y["eating_out"],
                         "weight": round(wf, 1)})
    rows.sort(key=lambda r: r["date"])
    if not rows:
        errors.append("no months calculated")
    dates = [r["date"] for r in rows]
    for x, y2 in zip(dates, dates[1:]):
        if _shift(x, 1) != y2:
            errors.append(f"gap between {x[:7]} and {y2[:7]}")
    if dates and dates[0] != "2011-01-01":
        errors.append(f"series starts {dates[0][:7]}, expected 2011-01")
    if errors:
        raise CheckFailed(errors[:40])

    latest = dates[-1]
    code = f"F{latest[:7]}"
    OUT.mkdir(parents=True, exist_ok=True)
    cols = ["date", "base", "weight", "index", "yoy", "food_group_yoy", "alcohol_yoy", "eating_out_yoy"]
    with open(OUT / "jp_cpi_food.csv", "w", newline="") as f:
        wr = csv.writer(f, lineterminator="\n")
        wr.writerow(cols)
        for r in rows:
            wr.writerow([r[c] for c in cols])
    nlong = write_long(({"country": "JP", "indicator": "cpi", "series": "food_nab",
                         "label": "Food and non-alcoholic beverages (COICOP 01)", "measure": "yoy",
                         "area": "national", "freq": "M", "date": r["date"], "value": r["yoy"], "unit": "%",
                         "source": "Asia Decoded calculation from Statistics Bureau of Japan data", "release": code}
                        for r in rows), OUT / "long.csv")
    release = {"code": code, "label": f"{MONTHS[int(latest[5:7]) - 1]} {latest[:4]}", "latest_month": latest,
               "weights": {str(b): data[b]["weights"] for b in BASES}}
    write_release(OUT, release, warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{release['label']}: {len(rows)} months", "warnings": warnings}
