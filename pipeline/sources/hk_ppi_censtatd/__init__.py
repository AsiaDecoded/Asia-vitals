"""Hong Kong producer and trade prices: C&SD, as published. Nothing is calculated.

- 520-62001: producer price indices for manufacturing and waste management (quarterly, 2015 = 100): index, y/y.
- 520-63001: producer price indices of selected service industries (quarterly, 2015 = 100): index, y/y.
- 410-51001/51002/51003: merchandise trade index numbers (monthly, 2024 = 100): unit value indices of imports and
  total exports, and terms of trade: index, y/y. C&SD publishes no monthly PPI; the unit value indices are its
  monthly measure of import and export prices.

Quarters are dated by their first month (Q2 2026 = 2026-04-01).
"""
import csv
import gzip
import hashlib
import json

from core import censtatd
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "hk_ppi_censtatd"
DESCRIPTION = "Hong Kong producer prices (quarterly) and import/export unit value indices (monthly), C&SD"
OUT = DATA / "hk" / "ppi"
RAWDIR = RAW / "hk" / "ppi_censtatd"
SRC = "Census and Statistics Department, Hong Kong"
TABLES = {"520-62001": ("ppi", "Q", "2015 = 100"), "520-63001": ("sppi", "Q", "2015 = 100"),
          "410-51001": ("trade", "M", "2024 = 100"), "410-51002": ("trade", "M", "2024 = 100"),
          "410-51003": ("trade", "M", "2024 = 100")}
TRADE = {"UVI_IM": ("import_uvi", "Import prices (unit value index)"), "UVI_TX": ("export_uvi", "Export prices (unit value index, total exports)"),
         "TOT": ("terms_of_trade", "Terms of trade")}
PPI_KEYS = {"ind_PPI_IND_C": "manufacturing"}
QUARTERS = ["Q1", "Q2", "Q3", "Q4"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
# Q2 2026 as published in 520-62001 when the source was built (28 Oct 2026): a regression check
RELEASE_Q2_2026 = {("manufacturing", "2026-04-01", "yoy"): 13.1, ("manufacturing", "2026-04-01", "index"): 140.2}


def _date(period, freq):
    p = str(period)
    if len(p) != 6:
        return None
    m = int(p[4:])
    if freq == "Q":
        m = m - 2
    return f"{p[:4]}-{m:02d}-01"


def _key(code):
    return PPI_KEYS.get(code) or code.replace("ind_", "").replace("QSIP_", "").replace("PPI_", "").lower()


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    RAWDIR.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    raw, store, labels = {}, {}, {}
    for tid, (grp, freq, base) in TABLES.items():
        hdr, rows = censtatd.table(tid)
        raw[tid] = rows
        for r in rows:
            if r.get("freq") != freq or r.get("figure") in ("", None):
                continue
            d = _date(r["period"], freq)
            meas = {"Index": "index", "Year-on-year % change": "yoy"}.get(r.get("svDesc"))
            if not d or not meas:
                continue
            if grp == "trade":
                if r["sv"] not in TRADE:
                    continue
                key, lab = TRADE[r["sv"]]
            else:
                key, lab = (("sppi_" if grp == "sppi" else "") + _key(r["IND"])), r["INDDesc"]
            labels[key] = (lab, grp, freq, base, tid)
            store.setdefault((key, d), {})[meas] = float(r["figure"])
    fp = hashlib.sha256(json.dumps(sorted((k[0], k[1], sorted(v.items())) for k, v in store.items())).encode()).hexdigest()[:16]
    if fp == state.get("fingerprint") and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (PPI {state.get('latest_quarter')}, trade {state.get('latest_month')})"}
    errors, warnings = [], []
    lq = max((d for (k, d) in store if k == "manufacturing"), default=None)
    lm = max((d for (k, d) in store if k == "import_uvi"), default=None)
    if not lq or not lm:
        raise CheckFailed(["manufacturing PPI or import unit value index missing"])
    for k in [k for k, v in labels.items() if v[1] == "ppi"]:
        if "yoy" not in store.get((k, lq), {}):
            errors.append(f"PPI {k} {lq}: y/y missing")
    for k in ("import_uvi", "export_uvi", "terms_of_trade"):
        if "index" not in store.get((k, lm), {}):
            errors.append(f"{k} {lm}: index missing")
    for k in ("import_uvi", "export_uvi"):
        if "yoy" not in store.get((k, lm), {}):
            errors.append(f"{k} {lm}: y/y missing")
    if state.get("latest_quarter") and lq < state["latest_quarter"]:
        errors.append(f"latest quarter {lq} before the stored {state['latest_quarter']}")
    if state.get("latest_month") and lm < state["latest_month"]:
        errors.append(f"latest month {lm} before the stored {state['latest_month']}")
    # no gaps in the manufacturing PPI (y/y from Q1 2006) or import prices (y/y from Jan 1983)
    for key, first, step in (("manufacturing", "2006-01-01", 3), ("import_uvi", "1983-01-01", 1)):
        last = lq if step == 3 else lm
        d, gaps = first, []
        while d <= last:
            if "yoy" not in store.get((key, d), {}):
                gaps.append(d[:7])
            y, m = int(d[:4]), int(d[5:7]) - 1 + step
            d = f"{y + m // 12}-{m % 12 + 1:02d}-01"
        if gaps:
            errors.append(f"{key} y/y gaps: {', '.join(gaps[:6])} ({len(gaps)})")
    if lq >= "2026-04-01":
        for (k, d, m), v in RELEASE_Q2_2026.items():
            got = store.get((k, d), {}).get(m)
            if got is None or abs(got - v) > 0.001:
                errors.append(f"Q2 2026 {k} {m}: {got} vs release {v}")
    if errors:
        raise CheckFailed(errors)

    rows = []
    for (k, d), v in store.items():
        lab, grp, freq, base, tid = labels[k]
        rows.append({"date": d, "freq": freq, "group": grp, "series": k, "label": lab, "index": v.get("index"),
                     "yoy": v.get("yoy"), "base": base, "table": tid})
    rows.sort(key=lambda r: (r["group"], r["series"], r["date"]))
    cols = ["date", "freq", "group", "series", "label", "index", "yoy", "base", "table"]
    with open(OUT / "hk_ppi.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r[c] is None else r[c] for c in cols])
    qlabel = f"{QUARTERS[(int(lq[5:7]) - 1) // 3]} {lq[:4]}"
    mlabel = f"{MONTHS[int(lm[5:7]) - 1]} {lm[:4]}"
    code = f"P{lq[:4]}Q{(int(lq[5:7]) - 1) // 3 + 1}-T{lm[:7]}"

    def long_rows():
        for r in rows:
            for m, unit in (("index", f"index, {r['base']}"), ("yoy", "%")):
                yield {"country": "HK", "indicator": "ppi" if r["group"] != "trade" else "trade_prices", "series": r["series"],
                       "label": r["label"], "measure": m, "area": "national", "freq": r["freq"], "date": r["date"],
                       "value": r[m], "unit": unit, "source": SRC, "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    asia = [{"country": "HK", "concept": "ppi_yoy", "series_id": "hk.ppi.manufacturing.yoy", "date": r["date"], "value": r["yoy"],
             "unit": "% y/y, quarterly", "basis": "published", "source": "C&SD", "base_break": "", "release_date": ""}
            for r in rows if r["series"] == "manufacturing" and r["yoy"] is not None]
    with open(OUT / "asia.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["country", "concept", "series_id", "date", "value", "unit", "basis", "source", "base_break", "release_date"], lineterminator="\n")
        w.writeheader()
        w.writerows(asia)
    g = lambda k, d, m="yoy": store.get((k, d), {}).get(m)  # noqa: E731
    pq = f"{int(lq[:4]) - (1 if lq[5:7] == '01' else 0)}-{(int(lq[5:7]) - 3 - 1) % 12 + 1:02d}-01"
    pm = f"{int(lm[:4]) - (1 if lm[5:7] == '01' else 0)}-{(int(lm[5:7]) - 2) % 12 + 1:02d}-01"
    latest = {"quarter": qlabel, "quarter_date": lq, "month": mlabel, "month_date": lm,
              "ppi_yoy": g("manufacturing", lq), "ppi_yoy_prev": g("manufacturing", pq),
              "import_yoy": g("import_uvi", lm), "import_yoy_prev": g("import_uvi", pm),
              "export_yoy": g("export_uvi", lm), "export_yoy_prev": g("export_uvi", pm)}
    with open(OUT / "hk_ppi_latest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(latest), lineterminator="\n")
        w.writeheader()
        w.writerow(latest)
    (RAWDIR / f"{code}_{fp}.json.gz").write_bytes(gzip.compress(json.dumps(raw, ensure_ascii=False).encode()))
    release = {"code": code, "label": f"PPI {qlabel}; trade prices {mlabel}", "latest_quarter": lq, "latest_month": lm,
               "table": "C&SD web tables 520-62001, 520-63001, 410-51001, 410-51002, 410-51003"}
    write_release(OUT, release, warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"PPI {qlabel}, trade prices {mlabel}: {len(rows)} rows", "warnings": warnings}
