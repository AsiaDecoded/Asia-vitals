"""India core CPI measures (Asia Decoded calculation), all-India combined, 2024 base.

MoSPI publishes no core measure. These follow the RBI's two published measures:
- core1: CPI excluding food and beverages (division 01) and fuel (group 04.5 electricity, gas
  and other fuels; class 07.2.2 fuels and lubricants for personal transport equipment).
- core2: core1 also excluding gold/diamond/platinum jewellery and silver jewellery
  (items 13.2.1.1.1.01 and .02).

Calculation: MoSPI's CPI is a Young (modified Laspeyres) index, so an aggregate is the
weight-averaged item index. Each core index is the average of MoSPI's published item indices
(all-India, combined) over the items kept, weighted by MoSPI's published item weights
(Expert Group report, Annex 5.3d: an item's all-India combined weight is the sum of its
state x sector shares). y/y is the 12-month change in that index, from Jan 2026 (the first
month with a 2024-base year earlier). Checked against the RBI's published figures for
Jun-Aug 2026 (core1 3.9, 3.9, 4.2; core2 2.5, 2.7, 2.9): all match to one decimal.

Runs only when the MoSPI headline data (in_cpi_mospi) has changed, since it pages through
every item for every month.
"""
import csv
import gzip
import hashlib
import json
from collections import defaultdict

from core import mospi
from core.common import DATA, RAW, ROOT, CheckFailed, read_json, write_long, write_release

NAME = "in_cpi_core"
DESCRIPTION = "India core CPI 1 and 2 (excl. food and fuel; and precious metals), calculated from MoSPI items"
OUT = DATA / "in" / "cpi_core"
RAWDIR = RAW / "in" / "cpi_core"
WEIGHTS = ROOT / "raw" / "in" / "cpi_weights" / "Annex_5.3_CPI2024_weights.xlsx"
HEADLINE_RELEASE = DATA / "in" / "cpi" / "release.json"
FIRST_YEAR = 2025
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

PRECIOUS = {"13.2.1.1.1.01", "13.2.1.1.1.02"}  # gold/diamond/platinum jewellery; silver jewellery
MEASURES = [
    ("core1", "Core 1 (CPI excluding food and fuel)"),
    ("core2", "Core 2 (CPI excluding food, fuel and precious metals)"),
]


def _food_fuel(code):
    return code.startswith("01.") or code.startswith("04.5.") or code.startswith("07.2.2.")


def _excluded(measure, code):
    return _food_fuel(code) or (measure == "core2" and code in PRECIOUS)


def item_weights():
    """{item code: (name, all-India combined weight)} from Annex 5.3d; weights sum to 100."""
    import openpyxl
    wb = openpyxl.load_workbook(WEIGHTS, read_only=True, data_only=True)
    ws = wb["5.3d"]
    w, names = defaultdict(float), {}
    header = None
    for row in ws.iter_rows(values_only=True):
        if header is None:
            if row and row[0] == "State":
                header = [str(c).strip() if c else c for c in row]
            continue
        if not row or row[0] is None or row[4] is None:
            continue
        code = str(row[4]).strip()
        w[code] += float(row[13])
        names[code] = str(row[3]).strip()
    return {k: (names[k], w[k]) for k in w}


def _month(r):
    return f"{int(r['year'])}-{mospi.month_number(r['month']):02d}-01"


def _prev_year(d):
    return f"{int(d[:4]) - 1}{d[4:]}"


def update(from_file=None, **_):
    state = read_json(OUT / "release.json", {}) or {}
    head = read_json(HEADLINE_RELEASE, {}) or {}
    trigger = head.get("fingerprint")
    if not from_file and trigger and trigger == state.get("headline_fingerprint"):
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('latest_month')})"}

    weights = item_weights()
    if from_file:
        rows = json.loads(gzip.decompress(open(from_file, "rb").read()))
    else:
        import datetime as dt
        years = list(range(FIRST_YEAR, dt.date.today().year + 1))
        rows, _ = mospi.cpi("Current", years=years, state_code=1, sector_code=3, max_pages=600)

    items, general = defaultdict(dict), {}
    for r in rows:
        if r.get("state") != "All India" or r.get("sector") != "Combined":
            continue
        if r.get("item"):
            items[r["code"]][_month(r)] = float(r["index"]) if r.get("index") not in (None, "") else None
        elif r.get("division") == "CPI (General)":
            general[_month(r)] = float(r["index"])

    errors, warnings = [], []
    if not general:
        raise CheckFailed(["no general index returned"])
    months = sorted(general)
    latest = months[-1]
    total_w = sum(w for _, w in weights.values())
    if abs(total_w - 100) > 0.001:
        errors.append(f"item weights sum to {total_w:.4f}, expected 100")
    if set(items) != set(weights):
        errors.append(f"items in data and weights differ: {len(set(items) - set(weights))} not weighted, "
                      f"{len(set(weights) - set(items))} weighted but missing")
    for m in months:
        missing = [k for k in weights if items.get(k, {}).get(m) is None]
        if missing:
            errors.append(f"{m}: {len(missing)} item indices missing")
    if errors:
        raise CheckFailed(errors)
    # The weighted items must reproduce MoSPI's published general index (rounding: ±0.02).
    for m in months:
        agg = sum(w * items[k][m] for k, (_, w) in weights.items()) / total_w
        if abs(agg - general[m]) > 0.02:
            errors.append(f"{m}: items give {agg:.3f}, published general index {general[m]}")
    if state.get("latest_month") and latest < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one already stored ({state['latest_month']})")
    if errors:
        raise CheckFailed(errors)

    out = {}
    for key, _ in MEASURES:
        keep = {k: w for k, (_, w) in weights.items() if not _excluded(key, k)}
        sw = sum(keep.values())
        idx = {m: sum(w * items[k][m] for k, w in keep.items()) / sw for m in months}
        out[key] = {"weight": sw, "index": idx,
                    "yoy": {m: (idx[m] / idx[_prev_year(m)] - 1) * 100 for m in months if _prev_year(m) in idx}}

    code = f"M{latest[:7]}"
    if state.get("code") == code:
        warnings.append("recent months revised (no new month)")
    release = {"code": code, "label": f"{MON[int(latest[5:7]) - 1]} {latest[:4]}", "latest_month": latest,
               "table": "Calculated from MoSPI CPI 2024 item indices (all-India, combined) and Annex 5.3d item weights",
               "weights": {k: round(v["weight"], 4) for k, v in out.items()}}

    OUT.mkdir(parents=True, exist_ok=True)
    labels = dict(MEASURES)
    csv_rows = []
    for order, (key, label) in enumerate(MEASURES):
        for m in months:
            y = out[key]["yoy"].get(m)
            csv_rows.append({"date": m, "series": key, "label": label, "order": order,
                             "index": round(out[key]["index"][m], 3), "yoy": None if y is None else round(y, 2)})
    csv_rows.sort(key=lambda r: (r["date"], r["order"]))
    cols = ["date", "series", "label", "order", "index", "yoy"]
    with open(OUT / "in_cpi_core.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in csv_rows:
            w.writerow(["" if r[c] is None else r[c] for c in cols])

    def long_rows():
        for r in csv_rows:
            for meas, unit in (("index", "index, 2024 = 100"), ("yoy", "%")):
                yield {"country": "IN", "indicator": "cpi_core", "series": r["series"], "label": labels[r["series"]],
                       "measure": meas, "area": "all-India", "freq": "M", "date": r["date"], "value": r[meas],
                       "unit": unit, "source": "Asia Decoded calculation from MoSPI", "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    fingerprint = hashlib.sha256(json.dumps(out, sort_keys=True).encode()).hexdigest()[:16]
    RAWDIR.mkdir(parents=True, exist_ok=True)
    (RAWDIR / f"{code}_{fingerprint}.json.gz").write_bytes(gzip.compress(json.dumps(rows).encode()))
    write_release(OUT, release, warnings, len(csv_rows),
                  {"fingerprint": fingerprint, "headline_fingerprint": trigger, "long_rows": nlong})
    lv = {k: out[k]["yoy"].get(latest) for k in out}
    return {"updated": True, "code": code,
            "summary": f"{release['label']}: core1 {lv['core1']:.2f}%, core2 {lv['core2']:.2f}% y/y",
            "warnings": warnings}
