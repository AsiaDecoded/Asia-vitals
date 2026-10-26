"""India consumer prices, long history: IMF Consumer Price Index dataset (formerly IFS), all items.

Series IMF.STA:CPI IND.CPI._T.IX.M (monthly, Jan 1957 on) and IND.CPI._T.IX.A (annual, 1957 on),
both with reference period 2024 = 100, and the IMF's own y/y rates for each
(IND.CPI._T.YOY_PCH_PA_PT.M and .A), as the IMF publishes them. The IMF joins India's indices
at overlaps (series attribute OVERLAP="OL"); it publishes no splice dates. Compared with MoSPI,
2025 on matches the 2024-base combined CPI and 2013-2024 the 2012-base combined CPI; earlier
years appear to be CPI for Industrial Workers (not confirmed against Labour Bureau data).
Index levels and y/y as published by the IMF; nothing is calculated here.
"""
import csv
import gzip
import hashlib
import json

from core import imf
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "in_cpi_imf"
DESCRIPTION = "India CPI all items, monthly and annual from 1957, 2024 = 100 (IMF CPI dataset)"
OUT = DATA / "in" / "cpi_imf"
RAWDIR = RAW / "in" / "cpi_imf"
FLOW = "IMF.STA,CPI"
KEYS = {"M": "IND.CPI._T.IX.M", "A": "IND.CPI._T.IX.A",
        "M_yoy": "IND.CPI._T.YOY_PCH_PA_PT.M", "A_yoy": "IND.CPI._T.YOY_PCH_PA_PT.A"}
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _fetch():
    return {f: imf.fetch(FLOW, k).decode("utf-8") for f, k in KEYS.items()}


def _tidy(raw):
    """{"M": {"YYYY-MM-01": value}, "A": {"YYYY": value}}, plus series attributes."""
    out, attrs = {}, {}
    for freq, xml in raw.items():
        series = imf.parse(xml.encode("utf-8"))
        if len(series) != 1:
            raise CheckFailed([f"{freq}: expected 1 series, got {len(series)}"])
        sattr, obs = series[0]
        attrs[freq] = sattr
        vals = {}
        for period, v, oattr in obs:
            if v is None:
                continue
            if not freq.endswith("_yoy") and oattr.get("REFERENCE_PERIOD") not in (None, "2024A"):
                raise CheckFailed([f"{freq} {period}: reference period {oattr.get('REFERENCE_PERIOD')}, expected 2024A"])
            if freq.startswith("M"):
                y, m = period.split("-M")
                vals[f"{y}-{int(m):02d}-01"] = v
            else:
                vals[period] = v
        out[freq] = vals
    return out, attrs


def _next_month(d):
    y, m = int(d[:4]), int(d[5:7])
    return f"{y + m // 12}-{m % 12 + 1:02d}-01"


def _checks(tidy, attrs, state):
    errors, warnings = [], []
    m, a = tidy.get("M", {}), tidy.get("A", {})
    if not m or not a:
        return ["no monthly or no annual data returned"], warnings, None
    my, ay = tidy.get("M_yoy", {}), tidy.get("A_yoy", {})
    if not my or not ay:
        errors.append("no monthly or no annual y/y returned")
    # The IMF's y/y should agree with its own index (both as published; ±0.05pp).
    for idx, yoy, lag, f in ((m, my, lambda d: f"{int(d[:4]) - 1}{d[4:]}", "M"), (a, ay, lambda y: str(int(y) - 1), "A")):
        for k, v in yoy.items():
            p = idx.get(lag(k))
            if p and k in idx and abs((idx[k] / p - 1) * 100 - v) > 0.05:
                errors.append(f"{f} y/y {k}: IMF rate {v:.2f} does not match its index")
        latest_idx = max(idx) if idx else None
        if latest_idx and yoy and max(yoy) != latest_idx:
            warnings.append(f"{f}: latest y/y {max(yoy)} differs from latest index {latest_idx}")
    for f in ("M", "A"):
        ref = attrs[f].get("COMMON_REFERENCE_PERIOD")
        if ref != "2024A":
            errors.append(f"{f}: reference period {ref}, expected 2024A")
    first, latest = min(m), max(m)
    d = first
    while d <= latest:
        if d not in m:
            errors.append(f"monthly value missing for {d}")
        d = _next_month(d)
    years = sorted(a)
    for y0, y1 in zip(years, years[1:]):
        if int(y1) != int(y0) + 1:
            errors.append(f"annual values missing between {y0} and {y1}")
    for f, s in (("M", m), ("A", a)):
        for k, v in s.items():
            if not 0 < v < 1000:
                errors.append(f"{f} {k} = {v} out of range")
    if state.get("latest_month") and latest < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one already stored ({state['latest_month']})")
    # 2024 = 100: the 2024 annual value should be close to 100.
    if "2024" in a and abs(a["2024"] - 100) > 1:
        errors.append(f"2024 annual index {a['2024']}, expected about 100")
    # Cross-check with MoSPI's combined CPI from Jan 2025 (warning only: the IMF may lag MoSPI revisions).
    mos = DATA / "in" / "cpi" / "in_cpi.csv"
    if mos.exists():
        diffs = []
        for r in csv.DictReader(open(mos)):
            if r["series"] == "combined" and r["date"] >= "2025-01-01" and r["date"] in m and r["index"]:
                if abs(float(r["index"]) - m[r["date"]]) > 0.02:
                    diffs.append(f"{r['date'][:7]} IMF {m[r['date']]} vs MoSPI {r['index']}")
        if diffs:
            warnings.append("differs from MoSPI combined CPI: " + "; ".join(diffs[:6]))
    return errors, warnings, latest


def _write(tidy, release):
    OUT.mkdir(parents=True, exist_ok=True)
    m, a, my, ay = tidy["M"], tidy["A"], tidy["M_yoy"], tidy["A_yoy"]
    with open(OUT / "in_cpi_imf_m.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "index", "yoy"])
        for d in sorted(m):
            w.writerow([d, m[d], "" if my.get(d) is None else my[d]])
    with open(OUT / "in_cpi_imf_a.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["year", "index", "yoy"])
        for y in sorted(a):
            w.writerow([y, a[y], "" if ay.get(y) is None else ay[y]])

    def long_rows():
        for freq, meas, unit, s in (("M", "index", "index, 2024 = 100", m), ("A", "index", "index, 2024 = 100", a),
                                    ("M", "yoy", "%", my), ("A", "yoy", "%", ay)):
            for k in sorted(s):
                yield {"country": "IN", "indicator": "cpi_long", "series": "all_items", "label": "CPI, all items (IMF)",
                       "measure": meas, "area": "all-India", "freq": freq,
                       "date": k if freq == "M" else f"{k}-01-01", "value": s[k], "unit": unit,
                       "source": "IMF, Consumer Price Index dataset", "release": release["code"]}
    nlong = write_long(long_rows(), OUT / "long.csv")
    return len(m) + len(a), nlong


def update(from_file=None, **_):
    state = read_json(OUT / "release.json", {}) or {}
    if from_file:
        raw = json.loads(gzip.decompress(open(from_file, "rb").read()))
    else:
        raw = _fetch()
    tidy, attrs = _tidy(raw)
    fingerprint = hashlib.sha256(json.dumps(tidy, sort_keys=True).encode()).hexdigest()[:16]
    if fingerprint == state.get("fingerprint") and not from_file:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('latest_month')})"}
    errors, warnings, latest = _checks(tidy, attrs, state)
    if errors:
        raise CheckFailed(errors)
    code = f"M{latest[:7]}"
    if state.get("code") == code:
        warnings.append("recent values revised (no new month)")
    release = {"code": code, "label": f"{MON[int(latest[5:7]) - 1]} {latest[:4]}", "latest_month": latest,
               "first_month": min(tidy["M"]), "first_year": min(tidy["A"]), "latest_year": max(tidy["A"]),
               "table": f"IMF {FLOW} {KEYS['M']} and {KEYS['A']} (2024 = 100)"}
    RAWDIR.mkdir(parents=True, exist_ok=True)
    (RAWDIR / f"{code}_{fingerprint}.json.gz").write_bytes(gzip.compress(json.dumps(raw).encode()))
    rows, nlong = _write(tidy, release)
    write_release(OUT, release, warnings, rows, {"fingerprint": fingerprint, "long_rows": nlong})
    return {"updated": True, "code": code,
            "summary": f"{release['label']}: monthly {release['first_month'][:7]} on, annual {release['first_year']}-{release['latest_year']}",
            "warnings": warnings}
