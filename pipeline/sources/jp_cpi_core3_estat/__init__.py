"""Japan CPI less food and non-alcoholic beverages and energy ("Core 2" on the dashboard): Asia Decoded calculation.

The cross-country core: all items less food and non-alcoholic beverages (COICOP 01) and energy, keeping
alcohol and restaurant meals. Parts, all published by the Statistics Bureau:
  all items (0001) and energy (0167: electricity, city and LP gas, kerosene, gasoline; matches COICOP
  04.5 + 07.2.2) from the e-Stat database table of each base; food and non-alcoholic beverages from the
  Bureau's COICOP classification index (category 01, raw file kept by jp_cpi_food_estat).
Weights per 10,000, published: COICOP 01 2,083 (2020 base, annual report appendix 5) and 2,163 (2025 base);
energy 712 (2020 base) and 749 (2025 base), Table 5 of the monthly report.

Within one base Japan's CPI is a fixed-weight index, so
    Core 2 index = (10000 x I_all - w01 x I_01 - wE x I_energy) / (10000 - w01 - wE)
and its y/y combines the parts' published y/y rates, each weighted by weight x index a year earlier, on the base
the Bureau uses for that month's official rates (2020 base for 2021-2025, 2025 base from 2026), the same
convention as the Bureau's own aggregates. COICOP 01 levels on the 2020 base are the COICOP table's linked
2020-2024 values divided by their 2020 average (the link is a constant rescaling). y/y from Jan 2021, the first
month the COICOP table allows. Check: where both months are on one base, y/y from the combined index agrees within 0.2pp.
"""
import csv
import gzip
import hashlib
import json
import re

from core import estat
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "jp_cpi_core3_estat"
DESCRIPTION = "Japan CPI less food and non-alcoholic beverages and energy (Core 2), calculated from published series"
OUT = DATA / "jp" / "cpi_core3"
FOOD_RAW = RAW / "jp" / "cpi_food"
MONTH_RE = re.compile(r"^(\d{4})00(0[1-9]|1[0-2])\2$")  # e.g. 2026000909 = Sep 2026
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# base: (e-Stat table, COICOP 01 weight, energy weight, first and last y/y month on this base)
BASES = {
    2020: ("0003427113", 2083, 712, "2021-01-01", "2025-12-01"),
    2025: ("0004052037", 2163, 749, "2026-01-01", "9999-12-01"),
}


def _shift(d, months):
    y, m = int(d[:4]), int(d[5:7]) - 1 + months
    return f"{y + m // 12}-{m % 12 + 1:02d}-01"


def _fetch(table):
    """{key: {date: {index, yoy}}} for all items and energy, national."""
    vals = estat.get_values(table, cdArea="00000", cdTab="1,3", cdCat01="0001,0167")
    out = {}
    for v in vals:
        m = MONTH_RE.match(v.get("time", ""))
        if not m:
            continue
        try:
            x = float(v.get("value"))
        except (TypeError, ValueError):
            continue
        k = {"0001": "all", "0167": "energy"}[v["cat01"]]
        out.setdefault(k, {}).setdefault(f"{m.group(1)}-{m.group(2)}-01", {})["index" if v["tab"] == "1" else "yoy"] = x
    return out


def _coicop():
    """COICOP 01 {date: {index, yoy}} (index 2025 = 100, linked before 2025) and weight, from the kept raw file."""
    from sources.jp_cpi_food_estat import parse
    files = sorted(FOOD_RAW.glob("*.gz"))
    if not files:
        raise CheckFailed(["no COICOP raw file (run jp_cpi_food_estat first)"])
    return parse(gzip.decompress(files[-1].read_bytes()))


def update(**_):
    state = read_json(OUT / "release.json", {}) or {}
    data = {b: _fetch(t) for b, (t, *_r) in BASES.items()}
    c01, w01_file = _coicop()
    fp = hashlib.sha256(json.dumps([data, c01], sort_keys=True).encode()).hexdigest()[:16]
    if fp == state.get("fingerprint"):
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('latest_month')})"}

    errors, warnings = [], []
    if w01_file != BASES[2025][1]:
        errors.append(f"COICOP 01 weight in the table {w01_file}, expected {BASES[2025][1]}")
    groups = DATA / "jp" / "cpi_contrib" / "jp_cpi_groups.csv"
    if groups.exists():
        ew = {r["date"]: float(r["weight"]) for r in csv.DictReader(open(groups)) if r["series"] == "energy" and r["weight"]}
        for b, (_t, _w, we, *_r) in BASES.items():
            got = {w for d, w in ew.items() if d >= ("2021-07-01" if b == 2020 else "2026-07-01") and (b == 2025 or d < "2026-07-01")}
            if got and got != {float(we)}:
                errors.append(f"{b} base energy weight in Table 5 {got}, expected {we}")
    # COICOP 01 on each base: 2025 values as they are; 2020-2024 rescaled to 2020 = 100
    lv20 = [c01[d]["index"] for d in c01 if d.startswith("2020-") and c01[d].get("index")]
    if len(lv20) != 12:
        errors.append(f"COICOP 01: {len(lv20)} months of 2020 index, need 12")
    k = sum(lv20) / len(lv20) / 100 if lv20 else 1
    i01 = {2020: {d: v["index"] / k for d, v in c01.items() if v.get("index") and d < "2025-01-01"},
           2025: {d: v["index"] for d, v in c01.items() if v.get("index") and d >= "2025-01-01"}}
    if errors:
        raise CheckFailed(errors)

    rows, worst = [], 0.0
    for base, (_t, w01, we, first, last) in BASES.items():
        A, E = data[base].get("all", {}), data[base].get("energy", {})
        rest = 10000 - w01 - we

        def idx(d):
            try:
                return (10000 * A[d]["index"] - w01 * i01[base][d] - we * E[d]["index"]) / rest
            except KeyError:
                return None
        for d in sorted(c01):
            if not (first <= d <= last) or c01[d].get("yoy") is None:
                continue
            p = _shift(d, -12)
            try:
                sa, s1, se = 10000 * A[p]["index"], w01 * i01[base][p], we * E[p]["index"]
                ya, y1, ye = A[d]["yoy"], c01[d]["yoy"], E[d]["yoy"]
            except KeyError as e:
                errors.append(f"{d[:7]} ({base} base): missing {e}")
                continue
            yoy = (sa * ya - s1 * y1 - se * ye) / (sa - s1 - se)
            i_d, i_p = idx(d), idx(p)
            if i_d is not None and i_p is not None:
                g = abs((i_d / i_p - 1) * 100 - yoy)
                worst = max(worst, g)
                if g > 0.2:
                    errors.append(f"{d[:7]}: y/y {yoy:.2f} vs from index {(i_d / i_p - 1) * 100:.2f}")
            rows.append({"date": d, "base": base, "index": None if i_d is None else round(i_d, 3), "yoy": round(yoy, 2),
                         "all_yoy": ya, "food_nab_yoy": y1, "energy_yoy": ye})
    dates = [r["date"] for r in rows]
    if not dates or dates[0] != "2021-01-01":
        errors.append(f"y/y starts {dates[0][:7] if dates else '-'}, expected 2021-01")
    for x, y in zip(dates, dates[1:]):
        if _shift(x, 1) != y:
            errors.append(f"gap between {x[:7]} and {y[:7]}")
    nat = (read_json(DATA / "jp" / "cpi" / "release.json", {}) or {}).get("national_month")
    if dates and nat != dates[-1]:
        errors.append(f"latest month {dates[-1][:7]} is not the latest national CPI month ({nat})")
    if errors:
        raise CheckFailed(errors[:40])
    warnings.append(f"y/y vs combined index, same base: max gap {worst:.2f}pp")

    latest = dates[-1]
    code = f"K{latest[:7]}"
    OUT.mkdir(parents=True, exist_ok=True)
    cols = ["date", "base", "index", "yoy", "all_yoy", "food_nab_yoy", "energy_yoy"]
    with open(OUT / "jp_cpi_core3.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r[c] is None else r[c] for c in cols])
    nlong = write_long(({"country": "JP", "indicator": "cpi", "series": "core3",
                         "label": "Less food and non-alcoholic beverages and energy", "measure": "yoy",
                         "area": "national", "freq": "M", "date": r["date"], "value": r["yoy"], "unit": "%",
                         "source": "Asia Decoded calculation from Statistics Bureau of Japan data", "release": code}
                        for r in rows), OUT / "long.csv")
    release = {"code": code, "label": f"{MONTHS[int(latest[5:7]) - 1]} {latest[:4]}", "latest_month": latest,
               "weights": {str(b): {"coicop01": v[1], "energy": v[2]} for b, v in BASES.items()}}
    write_release(OUT, release, warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{release['label']}: {len(rows)} months", "warnings": warnings}
