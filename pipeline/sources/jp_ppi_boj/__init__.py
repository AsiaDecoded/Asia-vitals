"""Japan producer prices: Bank of Japan Corporate Goods Price Index (CGPI), 2020 base, via the BoJ API.

Producer Price Index (domestic), export and import price indices. Index levels and the BoJ's
published y/y rates. The BoJ revises recent months regularly, so any change in the data counts
as an update; a new month gives a new release code.
"""
import csv
import gzip
import hashlib
import json

from core import boj
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "jp_ppi_boj"
DESCRIPTION = "Japan producer, export and import prices (BoJ CGPI)"
DB = "PR01"
BASE_START = "2020-01-01"  # first month of the 2020 base
OUT = DATA / "jp" / "ppi"
RAWDIR = RAW / "jp" / "ppi_boj"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# index code, key, label, has a published y/y series (code + '%')
SERIES = [
    ("PRCG20_2200000000", "ppi", "Producer prices, all commodities", True),
    ("PRCG20_22G2200000", "ppi_ex_summer_elec", "Producer prices excl. summer electricity surcharge (reference)", False),
    ("PRCG20_1200000000", "ppi_ex_tax", "Producer prices excl. consumption tax", False),
    ("PRCG20_2400000000", "export_yen", "Export prices, yen basis", True),
    ("PRCG20_2300000000", "export_ccy", "Export prices, contract currency basis", False),
    ("PRCG20_2600000000", "import_yen", "Import prices, yen basis", True),
    ("PRCG20_2500000000", "import_ccy", "Import prices, contract currency basis", False),
]
REQUIRED = ["ppi", "export_yen", "import_yen"]


def _codes():
    out = []
    for code, _, _, has_yoy in SERIES:
        out.append(code)
        if has_yoy:
            out.append(code + "%")
    return out


def _tidy(resultset):
    """{key: {date: {index, yoy}}}"""
    by_code = {c: (k, lab, i) for i, (c, k, lab, _) in enumerate(SERIES)}
    out = {}
    for s in resultset:
        code = s["SERIES_CODE"]
        meas = "yoy" if code.endswith("%") else "index"
        base = code.rstrip("%")
        if base not in by_code:
            continue
        key = by_code[base][0]
        v = s.get("VALUES") or {}
        for d, val in zip(v.get("SURVEY_DATES", []), v.get("VALUES", [])):
            date = f"{str(d)[:4]}-{str(d)[4:6]}-01"
            out.setdefault(key, {}).setdefault(date, {})[meas] = val
    return out


def _shift(d, months):
    y, m = int(d[:4]), int(d[5:7]) - 1 + months
    return f"{y + m // 12}-{m % 12 + 1:02d}-01"


def _checks(tidy, state):
    errors = []
    latest = max((d for d, v in tidy.get("ppi", {}).items() if v.get("index") is not None), default=None)
    if not latest:
        return ["no PPI data returned"], None
    for key in REQUIRED:
        v = tidy.get(key, {}).get(latest, {})
        for meas in ("index", "yoy"):
            if v.get(meas) is None:
                errors.append(f"{key} {meas} missing for {latest}")
    if state.get("latest_month") and latest < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one already stored ({state['latest_month']})")
    # Published y/y agrees with the index where both months are on the 2020 base (rounded: ±0.15pp).
    for key, series in tidy.items():
        for d, v in series.items():
            start = _shift(d, -12)
            if start < BASE_START or v.get("yoy") is None or v.get("index") is None:
                continue
            prev = series.get(start, {}).get("index")
            if prev:
                implied = (v["index"] / prev - 1) * 100
                if abs(implied - v["yoy"]) > 0.15:
                    errors.append(f"{key} yoy {d}: published {v['yoy']}, from index {implied:.2f}")
    for key, series in tidy.items():
        for d, v in series.items():
            if v.get("index") is not None and not 0 < v["index"] < 1000:
                errors.append(f"{key} index {d} = {v['index']} out of range")
    return errors, latest


def _write(tidy, release):
    OUT.mkdir(parents=True, exist_ok=True)
    order = {k: i for i, (_, k, _, _) in enumerate(SERIES)}
    labels = {k: lab for _, k, lab, _ in SERIES}
    rows = [{"date": d, "series": k, "label": labels[k], "order": order[k],
             "index": v.get("index"), "yoy": v.get("yoy")}
            for k, s in tidy.items() for d, v in s.items()]
    rows.sort(key=lambda r: (r["date"], r["order"]))
    cols = ["date", "series", "label", "order", "index", "yoy"]
    with open(OUT / "jp_ppi.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r[c] is None else r[c] for c in cols])

    def long_rows():
        for r in rows:
            for meas, unit in (("index", "index, 2020 = 100"), ("yoy", "%")):
                yield {"country": "JP", "indicator": "ppi", "series": r["series"], "label": r["label"],
                       "measure": meas, "area": "national", "freq": "M", "date": r["date"],
                       "value": r[meas], "unit": unit, "source": "Bank of Japan", "release": release["code"]}
    nlong = write_long(long_rows(), OUT / "long.csv")

    jd = OUT / "json"
    jd.mkdir(exist_ok=True)
    keys = ["ppi", "export_yen", "import_yen"]
    dates = sorted({d for k in keys for d in tidy.get(k, {})})
    data = [{"date": d, **{k: tidy.get(k, {}).get(d, {}).get("yoy") for k in keys}} for d in dates]
    (jd / "jp-ppi-yoy.json").write_text(json.dumps(
        {"slug": "jp-ppi-yoy", "title": "Japan producer, export and import prices", "units": "% y/y",
         "freq": "monthly", "source": f"Bank of Japan, Corporate Goods Price Index (2020 base), {release['label']}.",
         "release": release["code"], "columns": keys, "data": data}, ensure_ascii=False, indent=1) + "\n")
    return len(rows), nlong


def update(from_file=None, **_):
    state = read_json(OUT / "release.json", {}) or {}
    if from_file:
        raw = json.loads(gzip.decompress(open(from_file, "rb").read()) if from_file.endswith(".gz") else open(from_file).read())
    else:
        raw = boj.series(DB, _codes())
    compact = sorted([[s["SERIES_CODE"], (s.get("VALUES") or {}).get("SURVEY_DATES", []),
                       (s.get("VALUES") or {}).get("VALUES", [])] for s in raw])
    fingerprint = hashlib.sha256(json.dumps(compact).encode()).hexdigest()[:16]
    if fingerprint == state.get("fingerprint") and not from_file:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('latest_month')})"}

    tidy = _tidy(raw)
    errors, latest = _checks(tidy, state)
    if errors:
        raise CheckFailed(errors)
    warnings = []
    code = f"M{latest[:7]}"
    if state.get("code") == code:
        warnings.append("recent months revised (no new month)")
    release = {"code": code, "label": f"{MONTHS[int(latest[5:7]) - 1]} {latest[:4]}", "latest_month": latest,
               "table": f"BoJ {DB} (CGPI, 2020 base)"}
    RAWDIR.mkdir(parents=True, exist_ok=True)
    (RAWDIR / f"{code}_{fingerprint}.json.gz").write_bytes(gzip.compress(json.dumps(raw).encode()))
    rows, nlong = _write(tidy, release)
    write_release(OUT, release, warnings, rows, {"fingerprint": fingerprint, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{release['label']}: {rows} rows", "warnings": warnings}
