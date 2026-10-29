"""South Korea producer prices: Bank of Korea Producer Price Index (2020 = 100), ECOS table 404Y014, and
Domestic Supply Price Index (2020 = 100), ECOS table 405Y006.

PPI: all items and the five major groups (basic classification). DSPI: all items (prices of goods and
services supplied to the domestic market, domestically produced and imported). ECOS publishes index levels only; y/y is
calculated from the index (the Bank of Korea derives its published rates the same way). The latest
months are re-fetched on every run because the Bank of Korea revises the previous month's index.
"""
import csv
import hashlib
import json

from core import ecos
from core.common import DATA, CheckFailed, read_json, write_long, write_release

NAME = "kr_ppi_ecos"
DESCRIPTION = "South Korea producer prices (Bank of Korea PPI via ECOS)"
OUT = DATA / "kr" / "ppi"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
TABLE = "404Y014"
DSPI_TABLE = "405Y006"
SERIES = [("ppi", "*AA", "Producer prices (all items)"), ("agri", "1AA", "Agricultural, forestry and fishery products"),
          ("mining", "2AA", "Mining products"), ("manufacturing", "3AA", "Manufactured products"),
          ("utilities", "4AA", "Electricity, gas, water and waste"), ("services", "5AA", "Services")]


def _shift(ym, k):
    y, m = int(ym[:4]), int(ym[4:]) - 1 + k
    return f"{y + m // 12}{m % 12 + 1:02d}"


def update(**_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    store = ecos.load_store()
    t = store.get(TABLE, {})
    if "*AA" not in t:
        raise CheckFailed(["ECOS store has no PPI: run tools/ecos_backfill.py"])
    have = max(t["*AA"]["values"])
    for _k, code, _l in SERIES:
        ecos.put(store, TABLE, ecos.series(TABLE, code, _shift(have, -3), _shift(have, 3)))
    # Domestic Supply Price Index: all items (the top item of 405Y006). Full history the first time, then recent months.
    d = store.get(DSPI_TABLE, {})
    if not d:
        items = [r for r in ecos.items(DSPI_TABLE) if r.get("CYCLE") == "M"]
        top = next((r for r in items if not r.get("P_ITEM_CODE")), None)
        if not top:
            raise CheckFailed([f"ECOS {DSPI_TABLE}: no top-level monthly item in the item list"])
        store.setdefault("_items", {})[DSPI_TABLE] = [{k: r.get(k) for k in ("ITEM_CODE", "ITEM_NAME", "P_ITEM_CODE", "START_TIME", "UNIT_NAME", "WEIGHT")} for r in items]
        ecos.put(store, DSPI_TABLE, ecos.series(DSPI_TABLE, top["ITEM_CODE"], top["START_TIME"], _shift(have, 3)))
    else:
        code = next(iter(d))
        ecos.put(store, DSPI_TABLE, ecos.series(DSPI_TABLE, code, _shift(max(d[code]["values"]), -3), _shift(have, 3)))
    errors = []
    t = store[TABLE]
    latest = max(t["*AA"]["values"])
    if state.get("latest_month") and f"{latest[:4]}-{latest[4:]}-01" < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one already stored ({state['latest_month']})")
    if t["*AA"].get("unit") != "2020=100":
        errors.append(f"ACTION: PPI unit is now '{t['*AA'].get('unit')}' (was 2020=100): rebased; check kr_ppi_ecos")
    for key, code, _l in SERIES:
        if code not in t or latest not in t[code]["values"]:
            errors.append(f"{key} ({code}) missing for {latest}")
    for key, code, _l in SERIES:
        for ym, v in (t.get(code, {}).get("values") or {}).items():
            if not 0 < v < 1000:
                errors.append(f"{key} {ym} = {v} out of range")
    if errors:
        raise CheckFailed(errors)
    rows = []
    for o, (key, code, lab) in enumerate(SERIES):
        v = t[code]["values"]
        for ym in sorted(v):
            p = v.get(_shift(ym, -12))
            rows.append({"date": f"{ym[:4]}-{ym[4:]}-01", "series": key, "label": lab, "order": o, "index": v[ym],
                         "yoy": round((v[ym] / p - 1) * 100, 1) if p else None})
    dd = store.get(DSPI_TABLE, {})
    if len(dd) != 1:
        errors.append(f"DSPI: expected one series from {DSPI_TABLE}, found {len(dd)}")
    else:
        v = next(iter(dd.values()))["values"]
        if latest not in v and _shift(latest, -1) not in v:
            errors.append(f"DSPI: no data for {latest} or the month before")
        for ym in sorted(v):
            p = v.get(_shift(ym, -12))
            rows.append({"date": f"{ym[:4]}-{ym[4:]}-01", "series": "dspi", "label": "Domestic supply prices (all items)",
                         "order": len(SERIES), "index": v[ym], "yoy": round((v[ym] / p - 1) * 100, 1) if p else None})
    if errors:
        raise CheckFailed(errors)
    rows.sort(key=lambda r: (r["date"], r["order"]))
    fingerprint = hashlib.sha256(json.dumps(rows[-600:], sort_keys=True).encode()).hexdigest()[:16]
    ecos.save_store(store)
    code = f"P{latest[:4]}-{latest[4:]}"
    if fingerprint == state.get("fingerprint"):
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    cols = ["date", "series", "label", "order", "index", "yoy"]
    with open(OUT / "kr_ppi.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r[c] is None else r[c] for c in cols])
    label = f"{MONTHS[int(latest[4:]) - 1]} {latest[:4]}"

    def long_rows():
        for r in rows:
            for meas, unit in (("index", "index, 2020 = 100"), ("yoy", "%")):
                yield {"country": "KR", "indicator": "ppi", "series": r["series"], "label": r["label"], "measure": meas,
                       "area": "national", "freq": "M", "date": r["date"], "value": r[meas], "unit": unit,
                       "source": "Bank of Korea", "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    warnings = []
    if state.get("code") == code:
        warnings.append("recent months revised")
    release = {"code": code, "label": label, "latest_month": f"{latest[:4]}-{latest[4:]}-01",
               "table": "ECOS 404Y014, 405Y006 (Bank of Korea PPI and DSPI, 2020 = 100)"}
    write_release(OUT, release, warnings, len(rows), {"fingerprint": fingerprint, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{label}: {len(rows)} rows", "warnings": warnings}
