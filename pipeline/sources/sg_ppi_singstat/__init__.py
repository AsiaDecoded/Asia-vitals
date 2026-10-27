"""Singapore producer and trade prices: SingStat, 2023 base, via the Table Builder API (no key).

Overall indices of the Singapore Manufactured Products Price Index (producer prices), the Domestic Supply
Price Index, and import and export prices, with their non-oil versions. SingStat publishes monthly indices
only (its percent-change tables are annual), so y/y is calculated from the index.
"""
import csv
import gzip
import hashlib
import json

from core import singstat
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "sg_ppi_singstat"
DESCRIPTION = "Singapore producer, domestic supply, import and export prices (SingStat, 2023 base)"
OUT = DATA / "sg" / "ppi"
RAWDIR = RAW / "sg" / "ppi_singstat"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MON = {m: i + 1 for i, m in enumerate(MONTHS)}

# key, label, table, seriesNo
SERIES = [
    ("ppi", "Producer prices (Singapore manufactured products)", "M213431", "1"),
    ("ppi_non_oil", "Producer prices, non-oil", "M213431", "2"),
    ("dspi", "Domestic supply prices", "M213381", "1"),
    ("dspi_non_oil", "Domestic supply prices, non-oil", "M213381", "2"),
    ("import", "Import prices", "M213241", "1"),
    ("import_non_oil", "Import prices, non-oil", "M213241", "2"),
    ("export", "Export prices", "M213291", "1"),
    ("export_non_oil", "Export prices, non-oil", "M213291", "2"),
]
REQUIRED = ["ppi", "dspi", "import", "export"]


def _shift(d, months):
    y, m = int(d[:4]), int(d[5:7]) - 1 + months
    return f"{y + m // 12}-{m % 12 + 1:02d}-01"


def update(**_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    tables = sorted({t for _, _, t, _ in SERIES})
    metas = {t: singstat.metadata(t) for t in tables}
    stamp = json.dumps({t: [m.get("dataLastUpdated"), m.get("endPeriod")] for t, m in metas.items()}, sort_keys=True)
    fingerprint = hashlib.sha256(stamp.encode()).hexdigest()[:16]
    if fingerprint == state.get("fingerprint"):
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('latest_month')})"}
    raw = {t: singstat.table(t) for t in tables}
    tidy = {}
    for key, lab, t, no in SERIES:
        row = next((r for r in raw[t]["rows"] if r["seriesNo"] == no), None)
        if not row:
            continue
        s = {}
        for c in row["columns"]:
            try:
                y, m = c["key"].split()
                s[f"{y}-{MON[m]:02d}-01"] = float(c["value"])
            except (ValueError, KeyError):
                pass
        tidy[key] = s
    errors = []
    latest = max(tidy.get("ppi", {}) or {"": 0})
    if not latest:
        raise CheckFailed(["no producer price data"])
    for k in REQUIRED:
        if k not in tidy or not tidy[k]:
            errors.append(f"{k} missing")
    if state.get("latest_month") and latest < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one already stored ({state['latest_month']})")
    for k, s in tidy.items():
        for d, v in s.items():
            if not 0 < v < 1000:
                errors.append(f"{k} {d} = {v} out of range")
    if errors:
        raise CheckFailed(errors)
    order = {k: i for i, (k, *_r) in enumerate(SERIES)}
    labels = {k: lab for k, lab, *_r in SERIES}
    rows = []
    for k, s in tidy.items():
        for d in sorted(s):
            p = s.get(_shift(d, -12))
            rows.append({"date": d, "series": k, "label": labels[k], "order": order[k], "index": s[d],
                         "yoy": round((s[d] / p - 1) * 100, 1) if p else None})
    rows.sort(key=lambda r: (r["date"], r["order"]))
    cols = ["date", "series", "label", "order", "index", "yoy"]
    with open(OUT / "sg_ppi.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r[c] is None else r[c] for c in cols])
    code = f"P{latest[:7]}"
    label = f"{MONTHS[int(latest[5:7]) - 1]} {latest[:4]}"

    def long_rows():
        for r in rows:
            for meas, unit in (("index", "index, 2023 = 100"), ("yoy", "%")):
                yield {"country": "SG", "indicator": "ppi", "series": r["series"], "label": r["label"], "measure": meas,
                       "area": "national", "freq": "M", "date": r["date"], "value": r[meas], "unit": unit,
                       "source": "Singapore Department of Statistics", "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    RAWDIR.mkdir(parents=True, exist_ok=True)
    (RAWDIR / f"{code}_{fingerprint}.json.gz").write_bytes(gzip.compress(json.dumps(raw, ensure_ascii=False).encode()))
    release = {"code": code, "label": label, "latest_month": latest, "table": "SingStat " + ", ".join(tables) + " (2023 base)"}
    write_release(OUT, release, [], len(rows), {"fingerprint": fingerprint, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{label}: {len(rows)} rows"}
