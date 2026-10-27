"""Japan CPI less food (excl. alcohol) and energy, plus eating out ("Core 3"): Asia Decoded calculation.

Built to match India's core definition (RBI core: CPI excluding food and beverages and fuel), which
keeps meals outside the home (COICOP division 11, including canteens). Japan publishes "all items
less food (excl. alcoholic beverages) and energy" (code 0168), which drops all of Food, eating out
included. Core 3 adds eating out (外食, code 0042, school lunches included) back.

Calculation: Japan's CPI is a fixed-weight Laspeyres index, so within one base an aggregate is the
weight-average of its parts' indices. For each base:
    Core 3 index = (w0168 x I0168 + w0042 x I0042) / (w0168 + w0042)
with the Statistics Bureau's published weights per 10,000 (Table 5 of the monthly report):
    2015 base: 6713, 521   2020 base: 6781, 460   2025 base: 6609, 508
y/y is the 12-month change in that index on the base the Bureau uses for that month's official rates:
2015 base for 2016-2020, 2020 base for 2021-2025, 2025 base from 2026. Indices come from the e-Stat
API tables for each base (national, monthly), so both months of every y/y are on the same base.
Checked: the same method applied to code 0168 alone reproduces its published y/y.
"""
import csv
import hashlib
import json
import re

from core import estat
from core.common import DATA, CheckFailed, read_json, write_long, write_release

NAME = "jp_cpi_core3_estat"
DESCRIPTION = "Japan CPI less food and energy plus eating out (Core 3), calculated from e-Stat"
OUT = DATA / "jp" / "cpi_core3"
MONTH_RE = re.compile(r"^(\d{4})00(0[1-9]|1[0-2])\2$")  # e.g. 2026000909 = Sep 2026
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# base: (e-Stat table, weight of 0168, weight of 0042, first and last y/y month on this base)
BASES = {
    2015: ("0003143513", 6713, 521, "2016-01-01", "2020-12-01"),
    2020: ("0003427113", 6781, 460, "2021-01-01", "2025-12-01"),
    2025: ("0004052037", 6609, 508, "2026-01-01", "9999-12-01"),
}


def _shift(d, months):
    y, m = int(d[:4]), int(d[5:7]) - 1 + months
    return f"{y + m // 12}-{m % 12 + 1:02d}-01"


def _fetch(table):
    """{code: {date: {index, yoy}}} for 0168 and 0042, national."""
    vals = estat.get_values(table, cdArea="00000", cdTab="1,3", cdCat01="0168,0042")
    out = {}
    for v in vals:
        m = MONTH_RE.match(v.get("time", ""))
        if not m:
            continue
        try:
            x = float(v.get("value"))
        except (TypeError, ValueError):
            continue
        d = f"{m.group(1)}-{m.group(2)}-01"
        out.setdefault(v["cat01"], {}).setdefault(d, {})["index" if v["tab"] == "1" else "yoy"] = x
    return out


def update(**_):
    state = read_json(OUT / "release.json", {}) or {}
    data = {b: _fetch(t) for b, (t, *_r) in BASES.items()}
    fp = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
    if fp == state.get("fingerprint"):
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('latest_month')})"}

    rows, errors, warnings = [], [], []
    for base, (table, wa, wb, first, last) in BASES.items():
        a, b = data[base].get("0168", {}), data[base].get("0042", {})
        idx = {d: (wa * a[d]["index"] + wb * b[d]["index"]) / (wa + wb)
               for d in a if "index" in a[d] and "index" in b.get(d, {})}
        for d in sorted(idx):
            if not (first <= d <= last):
                continue
            p = _shift(d, -12)
            if p not in idx:
                errors.append(f"{base} base: no index for {p[:7]} (needed for {d[:7]})")
                continue
            yoy = round((idx[d] / idx[p] - 1) * 100, 2)
            # method check: the same calculation on 0168 alone should give its published y/y
            pub = a[d].get("yoy")
            own = (a[d]["index"] / a[p]["index"] - 1) * 100 if a.get(p, {}).get("index") else None
            if pub is not None and own is not None and abs(own - pub) > 0.15:
                errors.append(f"{d[:7]}: 0168 y/y from index {own:.2f} vs published {pub}")
            rows.append({"date": d, "base": base, "index": round(idx[d], 3), "yoy": yoy,
                         "ex_food_energy_yoy": pub, "eating_out_yoy": b[d].get("yoy")})
    rows.sort(key=lambda r: r["date"])
    if not rows:
        errors.append("no Core 3 months calculated")
    dates = [r["date"] for r in rows]
    for x, y in zip(dates, dates[1:]):
        if _shift(x, 1) != y:
            errors.append(f"gap between {x[:7]} and {y[:7]}")
    for r in rows:
        if r["ex_food_energy_yoy"] is not None and abs(r["yoy"] - r["ex_food_energy_yoy"]) > 2:
            errors.append(f"{r['date'][:7]}: Core 3 {r['yoy']} far from less food and energy {r['ex_food_energy_yoy']}")
    if errors:
        raise CheckFailed(errors[:40])

    latest = dates[-1]
    code = f"K{latest[:7]}"
    OUT.mkdir(parents=True, exist_ok=True)
    cols = ["date", "base", "index", "yoy", "ex_food_energy_yoy", "eating_out_yoy"]
    with open(OUT / "jp_cpi_core3.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r[c] is None else r[c] for c in cols])
    nlong = write_long(({"country": "JP", "indicator": "cpi", "series": "core3",
                         "label": "Less food (excl. alcohol) and energy, plus eating out", "measure": "yoy",
                         "area": "national", "freq": "M", "date": r["date"], "value": r["yoy"], "unit": "%",
                         "source": "Asia Decoded calculation from Statistics Bureau of Japan data", "release": code}
                        for r in rows), OUT / "long.csv")
    release = {"code": code, "label": f"{MONTHS[int(latest[5:7]) - 1]} {latest[:4]}", "latest_month": latest}
    write_release(OUT, release, warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{release['label']}: {len(rows)} months", "warnings": warnings}
