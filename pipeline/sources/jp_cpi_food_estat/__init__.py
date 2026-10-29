"""Japan CPI food and non-alcoholic beverages (COICOP 01): published from 2021, calculated 2011-2020.

Published (y/y Jan 2021-): the Statistics Bureau's COICOP classification index, category 01 (2025 base: Table 15,
"COICOP分類指数_月次"), one Excel file per month on e-Stat, found through the file catalogue (needs ESTAT_APP_ID).
The latest file carries index (2025 = 100) from Jan 2020 and m/m and y/y as published (2020 base for 2021-2025,
2025 base from 2026). Kept as published.

Calculated (y/y Jan 2011-Dec 2020), on the Bureau's own item-to-COICOP assignment (品目から類への合算表（COICOP分類）,
2020 and 2025 bases): COICOP 01 is Japan's Food group less alcoholic beverages and eating out, plus the
health-supplement items (in medical care in Japan's groups, in COICOP 01.1.9), less the few beverage items the Bureau
counts as alcoholic. The same items get the same assignment on the 2010 and 2015 bases:
    2010 base: + サプリメント (6090)
    2015 base: + 健康保持用摂取品Ａ, Ｂ (6090, 6094)
    2020 base: + 健康保持用摂取品Ａ, Ｂ; - ノンアルコールビール (1952)   [used only for the check below]
Within one base Japan's CPI is a fixed-weight index, so
    I_01 = (wF I_food - wA I_alcohol - wE I_eating_out + sum w_add I_add - sum w_sub I_sub) / W01
with published weights (2010, 2015: the e-Stat tables' weight field; 2020: Table 5). y/y combines the parts' published
y/y rates, each weighted by weight x index a year earlier, on the base the Bureau uses for that month's official rates
(2010 base for 2011-2015, 2015 base for 2016-2020): Japan's convention for its own aggregates.

Checks (errors stop the source): the same calculation on the 2020 base reproduces the published COICOP 01 y/y for
2021-2025 within 0.15pp (max gap reported) and its weight (2,083) within 3; y/y from the combined index agrees
within 0.2pp; no gaps from Jan 2011; latest month equals the latest national CPI month.

Writes data/jp/cpi_food/jp_cpi_food.csv (date, basis, base, weight, index, mom, yoy; index and m/m only where
published) and jp_cpi_food_bases.csv (the calculated COICOP 01 index on each base, every month that base's table
holds from its base year: used by jp_cpi_core3_estat). Keeps the Excel file under raw/jp/cpi_food/.
"""
import csv
import gzip
import re

from core import estat
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "jp_cpi_food_estat"
DESCRIPTION = "Japan CPI food and non-alcoholic beverages (COICOP 01), Statistics Bureau, as published"
OUT = DATA / "jp" / "cpi_food"
RAWDIR = RAW / "jp" / "cpi_food"
CODE = "01"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SHEETS = {"指数": "index", "前月比": "mom", "前年同月比": "yoy"}
MONTH_RE = re.compile(r"^(\d{4})00(0[1-9]|1[0-2])\2$")  # e.g. 2026000909 = Sep 2026
# Calculated history. base: (e-Stat table, weights (None = the table's weight field), added items, removed items,
#   first month of the base's own index, first and last y/y month taken from it (None = check only))
HIST = {
    2010: ("0003036792", None, ["6090"], [], "2010-01-01", "2011-01-01", "2015-12-01"),
    2015: ("0003143513", None, ["6090", "6094"], [], "2015-01-01", "2016-01-01", "2020-12-01"),
    2020: ("0003427113", {"0002": 2626, "0041": 119, "0042": 460, "6090": 19, "6094": 19, "1952": 3},
           ["6090", "6094"], ["1952"], "2020-01-01", None, None),
}
HIST_VERSION = 1
W01_2020 = 2083  # published COICOP 01 weight, 2020 base (annual report appendix 5)


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


def _fetch_base(table, codes, weights_in_table):
    vals = estat.get_values(table, cdArea="00000", cdTab="1,3,5" if weights_in_table else "1,3", cdCat01=",".join(codes))
    series, weights = {}, {}
    for v in vals:
        try:
            x = float(v.get("value"))
        except (TypeError, ValueError):
            continue
        c = v.get("cat01")
        if v.get("tab") == "5":
            weights[c] = x
            continue
        m = MONTH_RE.match(v.get("time", ""))
        if m:
            series.setdefault(c, {}).setdefault(f"{m.group(1)}-{m.group(2)}-01", {})["index" if v["tab"] == "1" else "yoy"] = x
    return series, weights


def _history(errors):
    """Calculated COICOP 01: ({date: y/y} for the official-rate months, [(date, base, index)], {base: W01}, 2020 check y/y)."""
    yoys, levels, w01s, check = {}, [], {}, {}
    for base, (table, wts, add, sub, start, first, last) in HIST.items():
        codes = ["0002", "0041", "0042"] + add + sub
        s, w = _fetch_base(table, codes, wts is None)
        w = wts or w
        miss = [c for c in codes if c not in w or c not in s]
        if miss:
            errors.append(f"{base} base: no data or weight for {', '.join(miss)}")
            continue
        sign = {"0002": 1, "0041": -1, "0042": -1, **{c: 1 for c in add}, **{c: -1 for c in sub}}
        W = sum(sign[c] * w[c] for c in codes)
        w01s[base] = W

        def idx(d):
            try:
                return sum(sign[c] * w[c] * s[c][d]["index"] for c in codes) / W
            except KeyError:
                return None
        for d in sorted(s["0002"]):
            if d >= start and idx(d) is not None:
                levels.append((d, base, idx(d)))
        lo, hi = (first, last) if first else ("2021-01-01", "2025-12-01")
        for d in sorted(s["0002"]):
            if not lo <= d <= hi:
                continue
            p = _shift(d, -12)
            try:
                sh = {c: sign[c] * w[c] * s[c][p]["index"] for c in codes}
                y = sum(sh[c] * s[c][d]["yoy"] for c in codes) / sum(sh.values())
            except (KeyError, TypeError):
                errors.append(f"{d[:7]} ({base} base): an index or y/y is missing")
                continue
            i_d, i_p = idx(d), idx(p)
            if i_d and i_p and abs((i_d / i_p - 1) * 100 - y) > 0.2:
                errors.append(f"{d[:7]} ({base} base): y/y {y:.2f} vs from index {(i_d / i_p - 1) * 100:.2f}")
            (yoys if first else check)[d] = y
    return yoys, levels, w01s, check


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
        if sid == state.get("stat_inf_id") and state.get("hist_version") == HIST_VERSION and (OUT / "jp_cpi_food.csv").exists():
            return {"updated": False, "code": state.get("code"), "summary": f"no change (report {month})"}
        data = download(sid)
        for p in RAWDIR.glob("*.gz"):
            p.unlink()
        (RAWDIR / f"{month}_{sid}.gz").write_bytes(gzip.compress(data))
    series, weight = parse(data)

    errors, warnings = [], []
    pub = [{"date": d, "basis": "published", "base": 2025 if d >= "2026-01-01" else 2020, "weight": weight,
            **{k: v.get(k) for k in ("index", "mom", "yoy")}}
           for d, v in sorted(series.items()) if v.get("yoy") is not None]
    if not pub or pub[0]["date"] != "2021-01-01":
        errors.append(f"published y/y starts {pub[0]['date'][:7] if pub else '-'}, expected 2021-01")
    hist, levels, w01s, check = _history(errors)
    if errors:
        raise CheckFailed(errors[:40])
    # the calculation reproduces the published series where both exist (2020 base, 2021-2025)
    gaps = [(abs(check[d] - series[d]["yoy"]), d) for d in check if series.get(d, {}).get("yoy") is not None]
    worst = max(gaps) if gaps else (None, None)
    if not gaps or worst[0] > 0.15:
        errors.append(f"calculated vs published COICOP 01 y/y, 2021-2025: max gap {worst[0]} ({worst[1]})")
    if abs(w01s.get(2020, 0) - W01_2020) > 3:
        errors.append(f"2020-base COICOP 01 weight {w01s.get(2020)}, published {W01_2020}")
    rows = [{"date": d, "basis": "calculated", "base": 2010 if d < "2016-01-01" else 2015,
             "weight": round(w01s[2010 if d < "2016-01-01" else 2015], 1), "index": None, "mom": None, "yoy": round(y, 2)}
            for d, y in sorted(hist.items())] + pub
    dates = [r["date"] for r in rows]
    if dates[0] != "2011-01-01":
        errors.append(f"y/y starts {dates[0][:7]}, expected 2011-01")
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
    warnings.append(f"published y/y vs index on the 2025 base: max gap {gap:.2f}pp")
    warnings.append(f"calculated vs published y/y on the 2020 base, 2021-2025: max gap {worst[0]:.2f}pp ({worst[1][:7]}); "
                    f"weights {', '.join(f'{b} {w:g}' for b, w in w01s.items())}")

    latest = dates[-1]
    code = f"F{latest[:7]}"
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "jp_cpi_food_bases.csv", "w", newline="") as f:
        wr = csv.writer(f, lineterminator="\n")
        wr.writerow(["date", "base", "weight", "index"])
        for d, b, i in levels:
            wr.writerow([d, b, w01s[b], round(i, 4)])
    cols = ["date", "basis", "base", "weight", "index", "mom", "yoy"]
    with open(OUT / "jp_cpi_food.csv", "w", newline="") as f:
        wr = csv.writer(f, lineterminator="\n")
        wr.writerow(cols)
        for r in rows:
            wr.writerow(["" if r[c] is None else r[c] for c in cols])
    nlong = write_long(({"country": "JP", "indicator": "cpi", "series": "food_nab",
                         "label": "Food and non-alcoholic beverages (COICOP 01)", "measure": "yoy",
                         "area": "national", "freq": "M", "date": r["date"], "value": r["yoy"], "unit": "%",
                         "source": ("Statistics Bureau of Japan, COICOP classification index" if r["basis"] == "published"
                                    else "Asia Decoded calculation from Statistics Bureau of Japan data"), "release": code}
                        for r in rows), OUT / "long.csv")
    release = {"code": code, "label": f"{MONTHS[int(latest[5:7]) - 1]} {latest[:4]}", "latest_month": latest,
               "basis": "calculated 2011-2020, published from 2021",
               "series_id": "JP COICOP 01: Statistics Bureau COICOP classification index from 2021; before, Food less alcohol and eating out, plus health supplements",
               "check": {"vs_published_2021_2025_max_pp": round(worst[0], 3), "weights": w01s},
               "report": month, "weight_2025": weight}
    write_release(OUT, release, warnings, len(rows), {"stat_inf_id": sid, "long_rows": nlong, "hist_version": HIST_VERSION})
    return {"updated": True, "code": code, "summary": f"{release['label']}: {len(rows)} months (from {dates[0][:7]}; published from 2021)",
            "warnings": warnings}
