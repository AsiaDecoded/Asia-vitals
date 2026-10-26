"""India consumer prices: MoSPI CPI (general index), 2024 base, all-India, Jan 2013 on.

One continuous series per sector (combined, rural, urban):
- Jan 2013 to Dec 2024: MoSPI's back series on the 2024 base (the 2012-base general index
  rescaled by MoSPI's linking factors, overlap year 2025). General index only.
- Jan 2025 on: the 2024-base series itself.
Index and MoSPI's published y/y rate; m/m is computed from the index (not seasonally adjusted).
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
FIRST = "2013-01-01"
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
    return {"back": back, "current": cur, "totals": {"back": n_back, "current": n_cur}}


def _tidy(raw):
    """{key: {date: {index, yoy, basis}}}; general index, all-India only."""
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
                "index": _num(r.get("index")), "yoy": _num(r.get("inflation")), "basis": basis}
    return out, stray


def _checks(tidy, raw, state):
    errors = []
    if not tidy:
        return ["no CPI rows returned"], None
    latest = max(d for s in tidy.values() for d in s)
    if state.get("latest_month") and latest < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one already stored ({state['latest_month']})")
    for _, key, _ in SECTORS:
        s = tidy.get(key, {})
        # every month from Jan 2013 to the latest, no gaps
        d = FIRST
        while d <= latest:
            v = s.get(d)
            if not v or v["index"] is None:
                errors.append(f"{key}: index missing for {d}")
            d = _shift(d, 1)
        # the two parts meet where they should
        for d, v in s.items():
            if (d < CURRENT_START) != (v["basis"] == "back"):
                errors.append(f"{key} {d}: came from the {v['basis']} series")
        # Published y/y agrees with the linked index: ±0.15pp (rounding) from Jan 2025 on.
        # Back-series y/y are the rates published at the time on the 2012 base; three months
        # in 2014 (Mar combined and rural, Oct urban) differ from the linked index by ~0.15-0.17pp,
        # so the back period is held to ±0.5pp, which still catches a wrong or shifted month.
        for d, v in s.items():
            prev = s.get(_shift(d, -12), {}).get("index")
            if v["yoy"] is None or not prev or v["index"] is None:
                continue
            implied = (v["index"] / prev - 1) * 100
            tol = 0.15 if d >= CURRENT_START else 0.5
            if abs(implied - v["yoy"]) > tol:
                errors.append(f"{key} y/y {d}: published {v['yoy']}, from index {implied:.2f}")
        for d, v in s.items():
            if v["index"] is not None and not 30 < v["index"] < 300:
                errors.append(f"{key} index {d} = {v['index']} out of range")
        lv = s.get(latest, {})
        if lv.get("yoy") is None:
            errors.append(f"{key}: y/y missing for latest month {latest}")
    return errors, latest


def _write(tidy, release):
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for order, (_, key, label) in enumerate(SECTORS):
        s = tidy[key]
        for d in sorted(s):
            v = s[d]
            prev = s.get(_shift(d, -1), {}).get("index")
            mom = round((v["index"] / prev - 1) * 100, 2) if prev and v["index"] is not None else None
            rows.append({"date": d, "series": key, "label": label, "order": order,
                         "index": v["index"], "yoy": v["yoy"], "mom": mom, "basis": v["basis"]})
    rows.sort(key=lambda r: (r["date"], r["order"]))
    cols = ["date", "series", "label", "order", "index", "yoy", "mom", "basis"]
    with open(OUT / "in_cpi.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r[c] is None else r[c] for c in cols])

    def long_rows():
        for r in rows:
            for meas, unit in (("index", "index, 2024 = 100"), ("yoy", "%"), ("mom", "%")):
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
             "source": f"MoSPI, Consumer Price Index (2024 base; Jan 2013-Dec 2024 linked back series), {release['label']}.",
             "release": release["code"], "columns": keys, "data": data}, ensure_ascii=False, indent=1) + "\n")
    return len(rows), nlong


def update(from_file=None, **_):
    state = read_json(OUT / "release.json", {}) or {}
    if from_file:
        raw = json.loads(gzip.decompress(open(from_file, "rb").read()) if from_file.endswith(".gz") else open(from_file).read())
    else:
        raw = _fetch()
    tidy, stray = _tidy(raw)
    compact = sorted([k, d, v["index"], v["yoy"]] for k, s in tidy.items() for d, v in s.items())
    fingerprint = hashlib.sha256(json.dumps(compact).encode()).hexdigest()[:16]
    if fingerprint == state.get("fingerprint") and not from_file:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('latest_month')})"}

    errors, latest = _checks(tidy, raw, state)
    if errors:
        raise CheckFailed(errors)
    warnings = []
    if stray:
        warnings.append(f"{stray} rows other than the all-India general index were returned and skipped")
    code = f"M{latest[:7]}"
    if state.get("code") == code:
        warnings.append("recent months revised (no new month)")
    release = {"code": code, "label": f"{MON[int(latest[5:7]) - 1]} {latest[:4]}", "latest_month": latest,
               "table": "MoSPI CPI, 2024 base (getCPIData: Current from Jan 2025, Back Jan 2013-Dec 2024)"}
    RAWDIR.mkdir(parents=True, exist_ok=True)
    (RAWDIR / f"{code}_{fingerprint}.json.gz").write_bytes(gzip.compress(json.dumps(raw).encode()))
    rows, nlong = _write(tidy, release)
    write_release(OUT, release, warnings, rows, {"fingerprint": fingerprint, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{release['label']}: {rows} rows", "warnings": warnings}
