"""India consumer prices: MoSPI CPI (general index), all-India, combined/rural/urban, Jan 2011 on.

One spliced index per sector, 2024 = 100:
- Jan 2025 on: MoSPI's 2024-base series.
- Jan 2013 to Dec 2024: MoSPI's back series on the 2024 base (the 2012-base general index
  rescaled by MoSPI's linking factors, overlap year 2025), as published.
- Jan 2011 to Dec 2012: MoSPI's 2010-base general index, linked here to the back series by the
  ratio of the two indices' annual geometric means in the overlap year 2013 (the method MoSPI
  uses to link its own bases). This link is an Asia Decoded calculation.
y/y (column yoy) is calculated from the spliced index, from Jan 2012. MoSPI's published rates are
kept alongside (column yoy_published: 2010-base rates for 2012-2013, 2012-base for 2014-2025,
2024-base from Jan 2026) for comparison. They differ before 2026: the back series is published to
one decimal, and the links match annual averages, not each month.
MoSPI revises the latest (provisional) month a month later, so any change in the data counts
as an update; a new month gives a new release code.
"""
import csv
import datetime as dt
import gzip
import hashlib
import json

from core import mospi
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "in_cpi_mospi"
DESCRIPTION = "India CPI general index, all-India, 2024 base with linked back series (MoSPI)"
OUT = DATA / "in" / "cpi"
RAWDIR = RAW / "in" / "cpi_mospi"
FIRST = "2011-01-01"          # first month of the spliced index
BACK_START = "2013-01-01"     # first month of MoSPI's 2024-base back series
LINK_YEAR = "2013"            # overlap year for linking the 2010 base
YOY_FIRST = "2012-01-01"
CURRENT_START = "2025-01-01"
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SECTORS = [("Combined", "combined", "CPI, combined"),
           ("Rural", "rural", "CPI, rural"),
           ("Urban", "urban", "CPI, urban")]
GENERAL = "CPI (General)"


def _shift(d, months):
    y, m = int(d[:4]), int(d[5:7]) - 1 + months
    return f"{y + m // 12}-{m % 12 + 1:02d}-01"


def _num(x):
    if x is None or str(x).strip() in ("", "-", "NA"):
        return None
    return float(x)


def _fetch():
    back, n_back = mospi.cpi("Back", state_code=1)
    years = list(range(2025, dt.date.today().year + 1))
    cur, n_cur = mospi.cpi("Current", years=years, state_code=1, division_code=0)
    old, n_old = mospi.cpi_2012([2024, 2025], state_code=99)
    old = [r for r in old if r.get("group") == "General"]
    old10, n_old10 = mospi.cpi_2010([2011, 2012, 2013], state_code=99)
    old10 = [r for r in old10 if r.get("group") == "General"]
    return {"back": back, "current": cur, "old2012": old, "old2010": old10,
            "totals": {"back": n_back, "current": n_cur, "old2012": n_old, "old2010": n_old10}}


def _old(raw, part="old2012"):
    """Older-base general index, all-India: {key: {date: {index, yoy}}} (2012 base: 2024-2025; 2010 base: 2012-2013)."""
    keys = {s: k for s, k, _ in SECTORS}
    out = {}
    for r in raw.get(part, []):
        if r.get("state") != "All India" or r.get("sector") not in keys:
            continue
        date = f"{int(r['year'])}-{mospi.month_number(r['month']):02d}-01"
        out.setdefault(keys[r["sector"]], {})[date] = {"index": _num(r.get("index")),
                                                       "yoy": _num(r.get("inflation"))}
    return out


def _gm(vals):
    import math
    return math.exp(sum(math.log(v) for v in vals) / len(vals))


def _tidy(raw):
    """{key: {date: {index, yoy, yoy_published, basis}}} and the 2010-base link factors."""
    keys = {s: k for s, k, _ in SECTORS}
    out, stray = {}, 0
    for basis in ("back", "current"):
        for r in raw[basis]:
            if (r.get("division") != GENERAL or r.get("group") or r.get("item")
                    or r.get("state") != "All India" or r.get("sector") not in keys):
                stray += 1
                continue
            date = f"{int(r['year'])}-{mospi.month_number(r['month']):02d}-01"
            out.setdefault(keys[r["sector"]], {})[date] = {
                "index": _num(r.get("index")), "yoy_published": _num(r.get("inflation")), "basis": basis}
    old = _old(raw)
    old10 = _old(raw, "old2010")
    factors = {}
    for key, series in out.items():
        # MoSPI's published rates: 2012 base for 2025 (no 2024-base rates that year), 2010 base for 2012-2013.
        for d, v in series.items():
            if CURRENT_START <= d < "2026-01-01":
                v["yoy_published"] = old.get(key, {}).get(d, {}).get("yoy")
        o10 = old10.get(key, {})
        overlap = [d for d in o10 if d[:4] == LINK_YEAR]
        if len(overlap) == 12 and all(series.get(d, {}).get("index") and o10[d]["index"] for d in overlap):
            f = _gm([series[d]["index"] for d in overlap]) / _gm([o10[d]["index"] for d in overlap])
            factors[key] = f
            for d, v10 in o10.items():
                if d < BACK_START and v10["index"] is not None:
                    series[d] = {"index": round(v10["index"] * f, 4), "yoy_published": v10["yoy"], "basis": "2010 base, linked"}
        for d, v10 in o10.items():
            if d[:4] == LINK_YEAR and d in series:
                series[d]["yoy_published"] = v10["yoy"]
        for d, v in series.items():
            prev = series.get(_shift(d, -12), {}).get("index")
            v["yoy"] = round((v["index"] / prev - 1) * 100, 2) if prev and v["index"] is not None else None
    return out, stray, factors


def _checks(tidy, factors, state):
    errors, notes = [], {}
    if not tidy:
        return ["no CPI rows returned"], None, notes
    latest = max(d for s in tidy.values() for d in s)
    if state.get("latest_month") and latest < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one already stored ({state['latest_month']})")
    for _, key, _ in SECTORS:
        s = tidy.get(key, {})
        if key not in factors:
            errors.append(f"{key}: 2010-base index incomplete for {LINK_YEAR}; cannot link")
        elif not 0.3 < factors[key] < 0.8:
            errors.append(f"{key}: link factor {factors[key]:.4f} out of range")
        d = FIRST
        while d <= latest:
            if s.get(d, {}).get("index") is None:
                errors.append(f"{key}: index missing for {d}")
            if d >= YOY_FIRST and s.get(d, {}).get("yoy") is None:
                errors.append(f"{key}: y/y missing for {d}")
            d = _shift(d, 1)
        for d, v in s.items():
            want = "2010 base, linked" if d < BACK_START else "back" if d < CURRENT_START else "current"
            if v["basis"] != want:
                errors.append(f"{key} {d}: came from the {v['basis']} series")
            if v["index"] is not None and not 30 < v["index"] < 300:
                errors.append(f"{key} index {d} = {v['index']} out of range")
        # Calculated y/y against MoSPI's published rates: the same index from 2026 (rounding, ±0.15pp);
        # earlier, the links and one-decimal back series move them apart, so only a gross gap (>1.5pp) fails.
        diffs = []
        for d, v in s.items():
            if v.get("yoy") is None or v.get("yoy_published") is None:
                continue
            gap = v["yoy"] - v["yoy_published"]
            diffs.append((abs(gap), d, gap))
            if d >= "2026-01-01" and abs(gap) > 0.15:
                errors.append(f"{key} y/y {d}: calculated {v['yoy']}, published {v['yoy_published']}")
            elif abs(gap) > 1.5:
                errors.append(f"{key} y/y {d}: calculated {v['yoy']}, published {v['yoy_published']} (gap > 1.5pp)")
        if diffs:
            top = max(diffs)
            notes[key] = {"max_gap_pp": round(top[2], 2), "month": top[1][:7],
                          "mean_abs_gap_pp": round(sum(x[0] for x in diffs) / len(diffs), 3)}
        if s.get(latest, {}).get("yoy") is None:
            errors.append(f"{key}: y/y missing for latest month {latest}")
    return errors, latest, notes


def _write(tidy, release):
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for order, (_, key, label) in enumerate(SECTORS):
        s = tidy[key]
        for d in sorted(s):
            v = s[d]
            rows.append({"date": d, "series": key, "label": label, "order": order,
                         "index": v["index"], "yoy": v["yoy"], "yoy_published": v.get("yoy_published"),
                         "basis": v["basis"]})
    rows.sort(key=lambda r: (r["date"], r["order"]))
    cols = ["date", "series", "label", "order", "index", "yoy", "yoy_published", "basis"]
    with open(OUT / "in_cpi.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r[c] is None else r[c] for c in cols])

    def long_rows():
        for r in rows:
            for meas, unit in (("index", "index, 2024 = 100"), ("yoy", "%"), ("yoy_published", "%")):
                yield {"country": "IN", "indicator": "cpi", "series": r["series"], "label": r["label"],
                       "measure": meas, "area": "all-India", "freq": "M", "date": r["date"],
                       "value": r[meas], "unit": unit, "source": "MoSPI", "release": release["code"]}
    nlong = write_long(long_rows(), OUT / "long.csv")

    jd = OUT / "json"
    jd.mkdir(exist_ok=True)
    keys = [k for _, k, _ in SECTORS]
    dates = sorted({d for k in keys for d in tidy[k]})
    for meas, title, units in (("yoy", "India consumer inflation", "% y/y"),
                               ("index", "India consumer price index", "index, 2024 = 100")):
        data = [{"date": d, **{k: tidy[k].get(d, {}).get(meas) for k in keys}} for d in dates]
        slug = f"in-cpi-{meas}"
        (jd / f"{slug}.json").write_text(json.dumps(
            {"slug": slug, "title": title, "units": units, "freq": "monthly",
             "source": f"MoSPI, Consumer Price Index (2024 base; 2013-2024 back series; 2011-2012 2010 base, linked by Asia Decoded), {release['label']}.",
             "release": release["code"], "columns": keys, "data": data}, ensure_ascii=False, indent=1) + "\n")
    return len(rows), nlong


RELEASE_DAY = 12  # MoSPI publishes each month's CPI on the 12th of the next month


def _due(state):
    """Latest month MoSPI should have published by today; nothing to fetch if we already have it."""
    import datetime as dt
    t = dt.date.today()
    back = 1 if t.day >= RELEASE_DAY else 2
    y, m = t.year, t.month - back
    if m < 1:
        y, m = y - 1, m + 12
    return f"{y}-{m:02d}-01"


def update(from_file=None, **_):
    state = read_json(OUT / "release.json", {}) or {}
    if not from_file and state.get("latest_month", "") >= _due(state):
        return {"updated": False, "code": state.get("code"),
                "summary": f"not due (have {state.get('latest_month')}; next release on the {RELEASE_DAY}th)"}
    if from_file:
        raw = json.loads(gzip.decompress(open(from_file, "rb").read()) if from_file.endswith(".gz") else open(from_file).read())
    else:
        raw = _fetch()
    tidy, stray, factors = _tidy(raw)
    compact = sorted([k, d, v["index"], v.get("yoy_published")] for k, s in tidy.items() for d, v in s.items())
    fingerprint = hashlib.sha256(json.dumps(compact).encode()).hexdigest()[:16]
    if fingerprint == state.get("fingerprint") and not from_file:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('latest_month')})"}

    errors, latest, notes = _checks(tidy, factors, state)
    if errors:
        raise CheckFailed(errors)
    warnings = []
    if stray:
        warnings.append(f"{stray} rows other than the all-India general index were returned and skipped")
    code = f"M{latest[:7]}"
    if state.get("code") == code:
        warnings.append("recent months revised (no new month)")
    release = {"code": code, "label": f"{MON[int(latest[5:7]) - 1]} {latest[:4]}", "latest_month": latest,
               "table": "MoSPI CPI, 2024 base (getCPIData: Current from Jan 2025, Back Jan 2013-Dec 2024); 2010 base (getCPIIndex) Jan 2011-Dec 2012, linked",
               "link_factors_2010": {k: round(v, 6) for k, v in factors.items()}, "link_year": LINK_YEAR}
    RAWDIR.mkdir(parents=True, exist_ok=True)
    (RAWDIR / f"{code}_{fingerprint}.json.gz").write_bytes(gzip.compress(json.dumps(raw).encode()))
    rows, nlong = _write(tidy, release)
    write_release(OUT, release, warnings, rows, {"fingerprint": fingerprint, "long_rows": nlong,
                                                 "calculated_vs_published": notes})
    return {"updated": True, "code": code, "summary": f"{release['label']}: {rows} rows", "warnings": warnings}
