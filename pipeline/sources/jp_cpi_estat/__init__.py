"""Japan CPI, Statistics Bureau (MIC), via the e-Stat API, 2025-base database table.

National and Tokyo ward area: headline, core measures, goods and services, the 10 major groups,
and the seasonally adjusted series. Index, m/m and y/y are the Bureau's published figures.

A new release is anything that changes the data: a new national month, a new Tokyo month
(Tokyo comes out about four weeks earlier) or a revision.
"""
import csv
import gzip
import hashlib
import json
import re
from pathlib import Path

from core import estat
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "jp_cpi_estat"
DESCRIPTION = "Japan CPI (Statistics Bureau, e-Stat API)"
TABLE = "0004052037"  # 消費者物価指数（2025年基準）
OUT = DATA / "jp" / "cpi"
RAWDIR = RAW / "jp" / "cpi_estat"

BASE_START = "2025-01-01"  # first month of the 2025 base
AREAS = {"00000": "national", "13100": "tokyo"}
TABS = {"1": "index", "2": "mom", "3": "yoy"}

# code, key, English label, group
SERIES = [
    ("0001", "all", "All items", "headline"),
    ("0161", "core", "All items less fresh food (core)", "headline"),
    ("0178", "core_core", "All items less fresh food and energy", "headline"),
    ("0168", "ex_food_energy", "All items less food (excl. alcohol) and energy", "headline"),
    ("0157", "fresh_food", "Fresh food", "drivers"),
    ("0167", "energy", "Energy", "drivers"),
    ("0172", "food_ex_fresh", "Food less fresh food", "drivers"),
    ("0202", "goods", "Goods", "goods_services"),
    ("0241", "goods_ex_fresh", "Goods less fresh food", "goods_services"),
    ("0220", "services", "Services", "goods_services"),
    ("0242", "services_ex_rent", "Services less imputed rent", "goods_services"),
    ("0240", "public_charges", "Public service charges", "goods_services"),
    ("0002", "food", "Food", "groups"),
    ("0045", "housing", "Housing", "groups"),
    ("0054", "fuel_light_water", "Fuel, light and water charges", "groups"),
    ("0060", "furniture", "Furniture and household utensils", "groups"),
    ("0082", "clothing", "Clothes and footwear", "groups"),
    ("0107", "medical", "Medical care", "groups"),
    ("0111", "transport_comm", "Transportation and communication", "groups"),
    ("0118", "education", "Education", "groups"),
    ("0122", "culture_recreation", "Culture and recreation", "groups"),
    ("0145", "miscellaneous", "Miscellaneous", "groups"),
    ("0901", "all_sa", "All items, seasonally adjusted", "sa"),
    ("0902", "core_sa", "Core, seasonally adjusted", "sa"),
    ("0906", "core_core_sa", "Less fresh food and energy, seasonally adjusted", "sa"),
    ("0921", "goods_sa", "Goods, seasonally adjusted", "sa"),
    ("0924", "services_sa", "Services, seasonally adjusted", "sa"),
]
BY_CODE = {c: (k, lab, g, i) for i, (c, k, lab, g) in enumerate(SERIES)}
REQUIRED = {"national": ["all", "core", "core_core", "ex_food_energy", "goods", "services", "food", "energy"],
            "tokyo": ["all", "core", "core_core"]}
MONTH_RE = re.compile(r"^(\d{4})00(0[1-9]|1[0-2])\2$")  # e.g. 2026000909 = Sep 2026
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None  # '-', '…', '***' etc.


def _fetch():
    return estat.get_values(TABLE, cdArea=",".join(AREAS), cdTab=",".join(TABS),
                            cdCat01=",".join(c for c, *_ in SERIES))


def _compact(values):
    """Keep only monthly observations, as [tab, cat01, area, time, value] lists (the raw archive)."""
    rows = [[v.get("tab"), v.get("cat01"), v.get("area"), v.get("time"), v.get("value")]
            for v in values if MONTH_RE.match(v.get("time", ""))]
    return sorted(rows)


def _tidy(compact):
    """{(area, key): {date: {index, mom, yoy}}}"""
    out = {}
    for tab, cat, area, time, value in compact:
        m = MONTH_RE.match(time or "")
        if not m or cat not in BY_CODE or area not in AREAS or tab not in TABS:
            continue  # annual / fiscal-year averages and anything not requested
        date = f"{m.group(1)}-{m.group(2)}-01"
        key = BY_CODE[cat][0]
        out.setdefault((AREAS[area], key), {}).setdefault(date, {})[TABS[tab]] = _num(value)
    return out


def _latest(tidy, area, key="all"):
    pts = [d for d, v in tidy.get((area, key), {}).items() if v.get("index") is not None]
    return max(pts) if pts else None


def _mlabel(d):
    return f"{MONTHS[int(d[5:7]) - 1]} {d[:4]}"


def _shift(d, months):
    y, m = int(d[:4]), int(d[5:7]) - 1 + months
    return f"{y + m // 12}-{m % 12 + 1:02d}-01"


def _checks(tidy, state):
    errors, warnings = [], []
    nat, tok = _latest(tidy, "national"), _latest(tidy, "tokyo")
    if not nat or not tok:
        return [f"no data for national ({nat}) or Tokyo ({tok})"], warnings
    # 1. Required series present in the latest month.
    for area, latest in (("national", nat), ("tokyo", tok)):
        for key in REQUIRED[area]:
            v = tidy.get((area, key), {}).get(latest, {})
            for meas in ("index", "mom", "yoy"):
                if v.get(meas) is None:
                    errors.append(f"{area} {key} {meas} missing for {latest}")
    # 2. Never go backwards.
    if state.get("national_month") and nat < state["national_month"]:
        errors.append(f"latest national month {nat} is before the one already stored ({state['national_month']})")
    if state.get("tokyo_month") and tok < state["tokyo_month"]:
        errors.append(f"latest Tokyo month {tok} is before the one already stored ({state['tokyo_month']})")
    # 3. Published y/y and m/m agree with the index (rounded indices: ±0.15pp), but only where both
    #    months are on the 2025 base. Rates spanning the base change are the officially published ones
    #    from the old base and can't be recomputed from the rescaled old-base index.
    for (area, key), series in tidy.items():
        if key.endswith("_sa"):
            continue
        for d, v in series.items():
            if v.get("index") is None:
                continue
            for meas, lag in (("yoy", 12), ("mom", 1)):
                start = _shift(d, -lag)
                if start < BASE_START:
                    continue
                prev = series.get(start, {}).get("index")
                if v.get(meas) is None or not prev:
                    continue
                implied = (v["index"] / prev - 1) * 100
                if abs(implied - v[meas]) > 0.15:
                    errors.append(f"{area} {key} {meas} {d}: published {v[meas]}, from index {implied:.2f}")
    # 4. Plausible index levels (series start in 1970, when some groups were near 10).
    for (area, key), series in tidy.items():
        for d, v in series.items():
            if v.get("index") is not None and not 0 < v["index"] < 1000:
                errors.append(f"{area} {key} index {d} = {v['index']} out of range")
    return errors, warnings


def _write_outputs(tidy, release):
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for (area, key), series in tidy.items():
        code = next(c for c, (k, *_r) in BY_CODE.items() if k == key)
        _, label, group, order = BY_CODE[code]
        for d, v in series.items():
            rows.append({"date": d, "area": area, "series": key, "label": label, "group": group,
                         "order": order, **{m: v.get(m) for m in ("index", "mom", "yoy")}})
    rows.sort(key=lambda r: (r["date"], r["area"], r["order"]))
    with open(OUT / "jp_cpi.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        cols = ["date", "area", "series", "label", "group", "order", "index", "mom", "yoy"]
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r[c] is None else r[c] for c in cols])

    def long_rows():
        for r in rows:
            for meas, unit in (("index", "index, 2025 = 100"), ("mom", "%"), ("yoy", "%")):
                yield {"country": "JP", "indicator": "cpi", "series": r["series"], "label": r["label"],
                       "measure": meas, "area": r["area"], "freq": "M", "date": r["date"],
                       "value": r[meas], "unit": unit, "source": "Statistics Bureau (MIC)",
                       "release": release["code"]}
    nlong = write_long(long_rows(), OUT / "long.csv")

    # Per-chart JSON (Econvitals-style).
    jd = OUT / "json"
    jd.mkdir(exist_ok=True)
    src = f"Statistics Bureau of Japan, Consumer Price Index (2025 base), {release['label']}."

    def chart(slug, title, area, keys, meas, units):
        dates = sorted({d for k in keys for d in tidy.get((area, k), {})})
        data = [{"date": d, **{k: tidy.get((area, k), {}).get(d, {}).get(meas) for k in keys}} for d in dates]
        latest = {k: next(({"date": r["date"], "value": r[k]} for r in reversed(data) if r[k] is not None), None)
                  for k in keys}
        (jd / f"{slug}.json").write_text(json.dumps(
            {"slug": slug, "title": title, "units": units, "freq": "monthly", "area": area,
             "source": src, "release": release["code"], "columns": keys, "data": data, "latest": latest},
            ensure_ascii=False, indent=1) + "\n")

    head = ["all", "core", "core_core", "ex_food_energy"]
    chart("jp-cpi-headline-yoy", "Japan CPI inflation, national", "national", head, "yoy", "% y/y")
    chart("jp-cpi-tokyo-yoy", "Tokyo CPI inflation", "tokyo", head, "yoy", "% y/y")
    chart("jp-cpi-goods-services-yoy", "Japan CPI, goods and services", "national",
          ["goods", "goods_ex_fresh", "services", "services_ex_rent"], "yoy", "% y/y")
    chart("jp-cpi-groups-yoy", "Japan CPI by major group", "national",
          [k for _, k, _, g in SERIES if g == "groups"], "yoy", "% y/y")
    chart("jp-cpi-sa-mom", "Japan CPI, seasonally adjusted", "national",
          [k for _, k, _, g in SERIES if g == "sa"], "mom", "% m/m")
    return len(rows), nlong


def update(from_file=None, **_):
    state = read_json(OUT / "release.json", {}) or {}
    if from_file:
        p = Path(from_file)
        raw = gzip.decompress(p.read_bytes()) if p.suffix == ".gz" else p.read_bytes()
        compact = json.loads(raw)
    else:
        compact = _compact(_fetch())
    fingerprint = hashlib.sha256(json.dumps(compact).encode()).hexdigest()[:16]
    tidy = _tidy(compact)
    nat, tok = _latest(tidy, "national"), _latest(tidy, "tokyo")
    if fingerprint == state.get("fingerprint") and not from_file:
        return {"updated": False, "code": state.get("code"),
                "summary": f"no change (national {nat}, Tokyo {tok})"}

    errors, warnings = _checks(tidy, state)
    if errors:
        raise CheckFailed(errors)

    code = f"N{nat[:7]}_T{tok[:7]}"
    revised = state.get("code") == code  # same months, different numbers
    if revised:
        warnings.append("data revised without a new month (seasonal factors or corrections)")
    release = {"code": code, "label": f"National {_mlabel(nat)}, Tokyo {_mlabel(tok)}",
               "national_month": nat, "tokyo_month": tok,
               "table": f"e-Stat {TABLE} (2025 base)"}
    RAWDIR.mkdir(parents=True, exist_ok=True)
    (RAWDIR / f"{code}_{fingerprint}.json.gz").write_bytes(gzip.compress(json.dumps(compact).encode()))
    rows, nlong = _write_outputs(tidy, release)
    write_release(OUT, release, warnings, rows, {"fingerprint": fingerprint, "long_rows": nlong,
                                                 "national_month": nat, "tokyo_month": tok})
    return {"updated": True, "code": code, "summary": f"{release['label']}: {rows} rows",
            "warnings": warnings}
