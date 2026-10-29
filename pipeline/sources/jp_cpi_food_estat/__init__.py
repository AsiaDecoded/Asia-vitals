"""Japan CPI food and non-alcoholic beverages (COICOP 01), as published by the Statistics Bureau.

Source: the COICOP classification index table of the monthly CPI report (2025 base: Table 15,
"COICOP分類指数_月次"), one Excel file per month on e-Stat, found through the e-Stat file catalogue
(needs ESTAT_APP_ID). The Bureau re-sorts CPI items into COICOP 2018 categories, each item wholly
to one category. The latest file carries the whole series: index (2025 = 100) from Jan 2020, and
m/m and y/y as published (2020 base for 2021-2025, 2025 base from 2026), so y/y runs from Jan 2021.
Earlier bases have no COICOP table, so the series starts there.

Kept as published; nothing is calculated. Writes data/jp/cpi_food/jp_cpi_food.csv (date, weight, index,
mom, yoy) and keeps the Excel file under raw/jp/cpi_food/.
"""
import csv
import gzip
import re

from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "jp_cpi_food_estat"
DESCRIPTION = "Japan CPI food and non-alcoholic beverages (COICOP 01), Statistics Bureau, as published"
OUT = DATA / "jp" / "cpi_food"
RAWDIR = RAW / "jp" / "cpi_food"
CODE = "01"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SHEETS = {"指数": "index", "前月比": "mom", "前年同月比": "yoy"}


def _shift(d, months):
    y, m = int(d[:4]), int(d[5:7]) - 1 + months
    return f"{y + m // 12}-{m % 12 + 1:02d}-01"


def _catalogue():
    """(YYYY-MM, statInfId) of the latest monthly COICOP table on a base that carries the full series."""
    from sources.jp_cpi_contrib_estat import _as_list, _call, _text
    best, start = None, 1
    while True:
        res = _call("getDataCatalog", {"statsCode": "00200573", "searchWord": "COICOP", "limit": 100, "startPosition": start})
        body = res["GET_DATA_CATALOG"]
        st = body["RESULT"]["STATUS"]
        if st == 1:
            break
        if st != 0:
            raise RuntimeError(f"e-Stat catalogue error {st}: {body['RESULT'].get('ERROR_MSG')}")
        dl = body.get("DATA_CATALOG_LIST_INF", {})
        for d in _as_list(dl.get("DATA_CATALOG_INF")):
            ds = d.get("DATASET", {})
            name = _text(ds.get("TITLE", {}).get("NAME") if isinstance(ds.get("TITLE"), dict) else ds.get("TITLE"))
            m = re.search(r"^(\d{4})年基準.*月報_月次_(\d{4})年(\d{1,2})月$", name)
            if not m or int(m.group(1)) < 2025:
                continue  # 2020-base reports hold one month per sheet; the 2025-base table carries the whole series
            for r in _as_list(d.get("RESOURCES", {}).get("RESOURCE")):
                t = r.get("TITLE", {})
                t = t.get("NAME") if isinstance(t, dict) else t
                if "COICOP分類指数" not in (t or "") or not (t or "").endswith("月次") or r.get("FORMAT") != "XLS":
                    continue
                sid = re.search(r"statInfId=(\d+)", r.get("URL", ""))
                key = f"{m.group(2)}-{int(m.group(3)):02d}"
                if sid and (best is None or key > best[0]):
                    best = (key, sid.group(1))
        nxt = dl.get("RESULT_INF", {}).get("NEXT_KEY")
        if not nxt:
            break
        start = int(nxt)
    return best


def parse(data):
    """{date: {index, mom, yoy}} and the weight for COICOP 01 from one monthly table (2025-base layout)."""
    from sources.jp_cpi_contrib_estat import _norm, _sheet_rows_all
    out, weight = {}, None
    for rows in _sheet_rows_all(data):
        hdr = next((r for r in rows[:20] if any(_norm(c) == "Code" for c in r)), None)
        if hdr is None or CODE not in [_norm(c) for c in hdr]:
            continue
        j = [_norm(c) for c in hdr].index(CODE)
        meas_row = next((r for r in rows[:25] if any(_norm(c) == "表章項目" for c in r)), None)
        meas = next((v for k, v in SHEETS.items() if meas_row and _norm(meas_row[j]).startswith(k)), None)
        if meas is None:
            continue
        for r in rows:
            if len(r) <= j:
                continue
            if weight is None and any(_norm(c).startswith("ウエイト") for c in r[:j] if isinstance(c, str)):
                try:
                    weight = float(r[j])
                except (TypeError, ValueError):
                    pass
            lab = next((c for c in r[:j] if isinstance(c, str) and re.fullmatch(r"\d{4}年\d{1,2}月", c.strip())), None)
            if not lab:
                continue
            y, mo = re.match(r"(\d{4})年(\d{1,2})月", lab.strip()).groups()
            try:
                v = float(r[j])
            except (TypeError, ValueError):
                continue
            out.setdefault(f"{y}-{int(mo):02d}-01", {})[meas] = v
    return out, weight


def update(from_file=None, **_):
    from sources.jp_cpi_contrib_estat import download
    state = read_json(OUT / "release.json", {}) or {}
    RAWDIR.mkdir(parents=True, exist_ok=True)
    if from_file:
        month, sid, data = "file", "file", open(from_file, "rb").read()
    else:
        found = _catalogue()
        if not found:
            raise CheckFailed(["no monthly COICOP table (2025 base or later) in the e-Stat catalogue"])
        month, sid = found
        if sid == state.get("stat_inf_id") and (OUT / "jp_cpi_food.csv").exists():
            return {"updated": False, "code": state.get("code"), "summary": f"no change (report {month})"}
        data = download(sid)
        for p in RAWDIR.glob("*.gz"):
            p.unlink()
        (RAWDIR / f"{month}_{sid}.gz").write_bytes(gzip.compress(data))
    series, weight = parse(data)

    errors, warnings = [], []
    rows = [{"date": d, "weight": weight, **{k: v.get(k) for k in ("index", "mom", "yoy")}}
            for d, v in sorted(series.items()) if v.get("yoy") is not None]
    if not rows:
        raise CheckFailed(["no COICOP 01 y/y parsed"])
    dates = [r["date"] for r in rows]
    if dates[0] != "2021-01-01":
        errors.append(f"y/y starts {dates[0][:7]}, expected 2021-01")
    for x, y2 in zip(dates, dates[1:]):
        if _shift(x, 1) != y2:
            errors.append(f"gap in y/y between {x[:7]} and {y2[:7]}")
    nat = (read_json(DATA / "jp" / "cpi" / "release.json", {}) or {}).get("national_month")
    if nat != dates[-1]:
        errors.append(f"latest month {dates[-1][:7]} is not the latest national CPI month ({nat})")
    if weight is None or not 1500 < weight < 3000:
        errors.append(f"COICOP 01 weight {weight} missing or implausible")
    # published y/y agrees with the index where both months are on the 2025 base (2026 on)
    gap = 0.0
    for d in dates:
        p = _shift(d, -12)
        if p >= "2025-01-01" and series.get(p, {}).get("index"):
            g = abs((series[d]["index"] / series[p]["index"] - 1) * 100 - series[d]["yoy"])
            gap = max(gap, g)
            if g > 0.15:
                errors.append(f"{d[:7]}: published y/y {series[d]['yoy']} vs index {series[d]['index']}/{series[p]['index']}")
    if errors:
        raise CheckFailed(errors[:40])
    warnings.append(f"y/y vs index on the 2025 base: max gap {gap:.2f}pp")

    latest = dates[-1]
    code = f"F{latest[:7]}"
    OUT.mkdir(parents=True, exist_ok=True)
    cols = ["date", "weight", "index", "mom", "yoy"]
    with open(OUT / "jp_cpi_food.csv", "w", newline="") as f:
        wr = csv.writer(f, lineterminator="\n")
        wr.writerow(cols)
        for r in rows:
            wr.writerow(["" if r[c] is None else r[c] for c in cols])
    nlong = write_long(({"country": "JP", "indicator": "cpi", "series": "food_nab",
                         "label": "Food and non-alcoholic beverages (COICOP 01)", "measure": "yoy",
                         "area": "national", "freq": "M", "date": r["date"], "value": r["yoy"], "unit": "%",
                         "source": "Statistics Bureau of Japan, COICOP classification index", "release": code}
                        for r in rows), OUT / "long.csv")
    release = {"code": code, "label": f"{MONTHS[int(latest[5:7]) - 1]} {latest[:4]}", "latest_month": latest,
               "basis": "published", "series_id": "JP Statistics Bureau COICOP classification index, 01",
               "report": month, "weight_2025": weight}
    write_release(OUT, release, warnings, len(rows), {"stat_inf_id": sid, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{release['label']}: {len(rows)} months (from {dates[0][:7]})",
            "warnings": warnings}
