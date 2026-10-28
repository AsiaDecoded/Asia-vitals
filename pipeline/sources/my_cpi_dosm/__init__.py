"""Malaysia CPI: DOSM, 2010 = 100, from OpenDOSM's catalogue files (no key).

Everything is as DOSM publishes it: monthly index by division (Jan 1980–), y/y and m/m by division
(DOSM's published rates, y/y from Jan 1981), core CPI index and rates by division (Jan 2018–, y/y from
Jan 2019; no core for division 02, whose prices are all administered), and the annual all-items index and
inflation by division (1960–). DOSM publishes no seasonally adjusted CPI. Nothing is calculated here.
"""
import csv
import gzip
import hashlib
import json

from core import dosm
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "my_cpi_dosm"
DESCRIPTION = "Malaysia CPI, core CPI and divisions (DOSM, 2010 base), as published"
OUT = DATA / "my" / "cpi"
RAWDIR = RAW / "my" / "cpi_dosm"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
FILES = {
    "index": "cpi/cpi_2d.csv",
    "rates": "cpi/cpi_2d_inflation.csv",
    "core_index": "cpi/cpi_2d_core.csv",
    "core_rates": "cpi/cpi_2d_core_inflation.csv",
    "annual_index": "cpi/cpi_2d_annual.csv",
    "annual_rates": "cpi/cpi_2d_annual_inflation.csv",
    "mcoicop": "dictionaries/mcoicop.csv",
}
DIVS = ["overall"] + [f"{i:02d}" for i in range(1, 14)]
CORE_DIVS = [d for d in DIVS if d != "02"]
SOURCE = "Department of Statistics Malaysia"


def _shift(d, months):
    y, m = int(d[:4]), int(d[5:7]) - 1 + months
    return f"{y + m // 12}-{m % 12 + 1:02d}-01"


def update(**_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    raw = {k: dosm.raw_csv(p) for k, p in FILES.items()}
    fingerprint = hashlib.sha256(b"".join(raw[k] for k in sorted(raw))).hexdigest()[:16]
    if fingerprint == state.get("fingerprint"):
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('latest_month')})"}
    t = {k: dosm.rows(v) for k, v in raw.items()}
    labels = {r["division"]: r["desc_en"] for r in t["mcoicop"] if r["digits"] in ("1", "2")}

    # series key: division code for headline ("overall", "01".."13"); "core_" + code for core
    ser = {}

    def put(key, d, field, v):
        if v is not None:
            ser.setdefault(key, {}).setdefault(d, {})[field] = v

    for r in t["index"]:
        put(r["division"], r["date"], "index", dosm.num(r["index"]))
    for r in t["rates"]:
        put(r["division"], r["date"], "yoy", dosm.num(r["inflation_yoy"]))
        put(r["division"], r["date"], "mom", dosm.num(r["inflation_mom"]))
    for r in t["core_index"]:
        put("core_" + r["division"], r["date"], "index", dosm.num(r["index"]))
    for r in t["core_rates"]:
        put("core_" + r["division"], r["date"], "yoy", dosm.num(r["inflation_yoy"]))
        put("core_" + r["division"], r["date"], "mom", dosm.num(r["inflation_mom"]))
    annual = {}
    for r in t["annual_index"]:
        annual.setdefault(r["division"], {}).setdefault(r["date"], {})["index"] = dosm.num(r["index"])
    for r in t["annual_rates"]:
        v = dosm.num(r["inflation"])
        if v is not None:
            annual.setdefault(r["division"], {}).setdefault(r["date"], {})["yoy"] = v

    # checks
    errors, warnings = [], []
    if "overall" not in ser:
        raise CheckFailed(["no all-items CPI in cpi_2d"])
    latest = max(d for d, v in ser["overall"].items() if "yoy" in v)
    for k in DIVS + ["core_" + d for d in CORE_DIVS]:
        v = ser.get(k, {}).get(latest, {})
        if v.get("index") is None or v.get("yoy") is None or v.get("mom") is None:
            errors.append(f"{k}: index, y/y or m/m missing for {latest}")
    if state.get("latest_month") and latest < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one already stored ({state['latest_month']})")
    big = []
    for k, s in ser.items():
        for d, v in s.items():
            if v.get("index") is not None and not 5 < v["index"] < 1000:
                errors.append(f"{k} {d} index {v['index']} out of range")
            p = s.get(_shift(d, -12), {}).get("index")
            if v.get("yoy") is not None and v.get("index") and p and d >= "2011-01-01":
                gap = abs((v["index"] / p - 1) * 100 - v["yoy"])
                if gap > 0.5:
                    errors.append(f"{k} {d}: published y/y {v['yoy']} vs index {(v['index'] / p - 1) * 100:.2f}")
                elif gap > 0.15:
                    big.append(f"{k} {d}")
    gaps = [d for d in sorted(ser["overall"]) if d >= "1981-01-01" and ser["overall"][d].get("yoy") is None]
    if gaps:
        errors.append(f"all-items y/y missing for {len(gaps)} months from Jan 1981, first {gaps[0]}")
    if big:
        warnings.append(f"{len(big)} published y/y more than 0.15pp from the rounded index (latest: {big[-1]})")
    if errors:
        raise CheckFailed(errors)

    # monthly file
    keys = DIVS + ["core_" + d for d in CORE_DIVS]
    order = {k: i for i, k in enumerate(keys)}
    rows = []
    for k in keys:
        lab = labels.get(k[5:] if k.startswith("core_") else k, k)
        if k.startswith("core_"):
            lab = "Core CPI" if k == "core_overall" else f"Core, {lab}"
        elif k == "overall":
            lab = "CPI, all items"
        for d in sorted(ser.get(k, {})):
            v = ser[k][d]
            rows.append({"date": d, "series": k, "label": lab, "order": order[k], "index": v.get("index"),
                         "yoy": v.get("yoy"), "mom": v.get("mom")})
    rows.sort(key=lambda r: (r["date"], r["order"]))
    cols = ["date", "series", "label", "order", "index", "yoy", "mom"]
    with open(OUT / "my_cpi.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r[c] is None else r[c] for c in cols])
    arows = []
    for k in DIVS:
        for d in sorted(annual.get(k, {})):
            v = annual[k][d]
            arows.append({"year": d[:4], "series": k, "label": "CPI, all items" if k == "overall" else labels.get(k, k),
                          "index": v.get("index"), "yoy": None if v.get("yoy") is None else round(v["yoy"], 2)})
    with open(OUT / "my_cpi_annual.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        acols = ["year", "series", "label", "index", "yoy"]
        w.writerow(acols)
        for r in arows:
            w.writerow(["" if r[c] is None else r[c] for c in acols])

    code = f"M{latest[:7]}"
    label = f"{MONTHS[int(latest[5:7]) - 1]} {latest[:4]}"

    def long_rows():
        for r in rows:
            for meas, unit in (("index", "index, 2010 = 100"), ("yoy", "%"), ("mom", "%")):
                yield {"country": "MY", "indicator": "cpi", "series": r["series"], "label": r["label"], "measure": meas,
                       "area": "national", "freq": "M", "date": r["date"], "value": r[meas], "unit": unit,
                       "source": SOURCE, "release": code}
        for r in arows:
            for meas, unit in (("index", "index, 2010 = 100"), ("yoy", "%")):
                yield {"country": "MY", "indicator": "cpi", "series": r["series"], "label": r["label"], "measure": meas,
                       "area": "national", "freq": "A", "date": f"{r['year']}-01-01", "value": r[meas], "unit": unit,
                       "source": SOURCE, "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    RAWDIR.mkdir(parents=True, exist_ok=True)
    (RAWDIR / f"{code}_{fingerprint}.json.gz").write_bytes(
        gzip.compress(json.dumps({k: v.decode("utf-8-sig") for k, v in raw.items()}, ensure_ascii=False).encode()))
    m = dosm.meta("cpi_headline")
    release = {"code": code, "label": label, "latest_month": latest,
               "table": "OpenDOSM cpi_headline, cpi_headline_inflation, cpi_core, cpi_core_inflation, cpi_annual, cpi_annual_inflation (2010 base)",
               "dosm_last_updated": m.get("last_updated"), "dosm_next_update": m.get("next_update")}
    if state.get("latest_month") == latest:
        warnings.append("recent values revised")
    write_release(OUT, release, warnings, len(rows), {"fingerprint": fingerprint, "long_rows": nlong})
    o = ser["overall"][latest]
    c = ser["core_overall"][latest]
    return {"updated": True, "code": code, "warnings": warnings,
            "summary": f"{label}: CPI {o['yoy']}% y/y, core {c['yoy']}%; {len(rows)} rows"}
