"""World oil balance: US EIA Short-Term Energy Outlook (STEO), table 3a "World Petroleum and Other Liquid Fuels
Production, Consumption, and Inventories", million barrels per day, monthly, as published.

Source: https://www.eia.gov/outlooks/steo/xls/STEO_m.xlsx (the current STEO's monthly tables; no key). The workbook
covers January four years before the forecast year to December of the year after (2022-2027 in the November 2026
STEO). Months after EIA's last historical month are EIA forecasts (forecast = y). The last historical month for the
international tables is read from the workbook's Dates sheet.

Output: data/asia/energy/eia_steo_3a.csv (every row of table 3a), with
  series (EIA id), label, section (production, consumption, inventory withdrawals, inventories), date, value,
  unit, forecast, steo (the STEO month)
and data/asia/energy/world_oil_balance.csv for the dashboard: date, supply (papr_world), demand (patc_world),
balance (supply - demand, calculated), stock_change (EIA's net inventory withdrawals, t3_stchange_world), forecast, steo.
"""
import csv
import hashlib
import io
import re
import urllib.request

from core.common import DATA, CheckFailed, read_json, write_release

NAME = "oil_eia"
DESCRIPTION = "World oil supply, demand and inventories (EIA STEO table 3a, mb/d, history and EIA forecast)"
URL = "https://www.eia.gov/outlooks/steo/xls/STEO_m.xlsx"
OUT = DATA / "asia" / "energy"
UA = {"User-Agent": "Mozilla/5.0 (asia-vitals data pipeline; github.com/AsiaDecoded)"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SECTIONS = [("production", "production"), ("consumption", "consumption"), ("withdrawal", "inventory_withdrawals"),
            ("inventories", "inventories")]


def _yyyymm(v):
    s = str(v or "").strip()
    return f"{s[:4]}-{s[4:6]}" if re.fullmatch(r"\d{6}", s) else None


def last_historical(wb, warnings):
    """International tables' last historical month from the Dates sheet; else the domestic one, with a warning."""
    rows = [[c for c in r] for r in wb["Dates"].iter_rows(values_only=True)]
    domestic = None
    for r in rows:
        if r and isinstance(r[0], str) and r[0].startswith("Last Historical Month"):
            domestic = _yyyymm(next((c for c in r[1:] if c is not None), None))
    intl = False
    for i, r in enumerate(rows):
        lab = str(r[0] or "") if r else ""
        if "international" in lab.lower():
            intl = True
        if intl and lab.strip().lower() == "historical":
            dates = next((rows[j] for j in range(i - 1, -1, -1) if str(rows[j][0] or "").startswith("AAAA_DATEX")), None)
            if dates:
                hist = [_yyyymm(d) for d, h in zip(dates[1:], r[1:]) if h == 1 and _yyyymm(d)]
                if hist:
                    return max(hist)
    if domestic:
        return domestic          # the workbook has one history marker for all tables
    raise CheckFailed(["Dates sheet: no last historical month"])


def parse(blob):
    import openpyxl  # noqa: PLC0415
    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    warnings = []
    steo = next((str(next((c for c in r[1:] if c is not None), "")) for r in wb["Dates"].iter_rows(values_only=True)
                 if r and str(r[0] or "").startswith("Forecast Month")), "")
    rows = list(wb["3atab"].iter_rows(values_only=True))
    yr_row = next(i for i, r in enumerate(rows) if any(isinstance(c, int) and 2000 < c < 2100 for c in r[2:]))
    years, y = [], None
    for c in rows[yr_row][2:]:
        y = c if isinstance(c, int) else y
        years.append(y)
    mons = rows[yr_row + 1][2:]
    dates = [f"{yy}-{MONTHS.index(m) + 1:02d}" if yy and m in MONTHS else None for yy, m in zip(years, mons)]
    last_hist = last_historical(wb, warnings)
    out, section, seen, unit = [], None, set(), "mb/d"
    for r in rows[yr_row + 2:]:
        sid, label = r[0], r[1]
        if sid is None and isinstance(label, str):
            low = label.lower()
            section = next((s for k, s in SECTIONS if k in low), section)
            unit = "million barrels" if "million barrels)" in low and "per day" not in low else "mb/d"
            continue
        if not (isinstance(sid, str) and re.fullmatch(r"[a-z0-9_]+", sid)) or sid in seen:
            continue
        seen.add(sid)
        for d, v in zip(dates, r[2:]):
            if d and isinstance(v, (int, float)):
                out.append({"series": sid, "label": str(label).strip(), "section": section, "date": d + "-01",
                            "value": round(float(v), 6), "unit": unit, "forecast": "y" if d > last_hist else "",
                            "steo": steo})
    return out, last_hist, steo, warnings


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(URL, headers=UA), timeout=120) as r:
        blob = r.read()
    fp = hashlib.sha256(blob).hexdigest()[:16]
    old = read_json(OUT / "release.json", {}) or {}
    if fp == old.get("fingerprint") and not force:
        return {"updated": False, "summary": f"no change ({old.get('steo')} STEO)"}
    rows, last_hist, steo, warnings = parse(blob)
    by = {}
    for x in rows:
        by.setdefault(x["series"], {})[x["date"]] = x
    errors = [f"table 3a: no {s}" for s in ("papr_world", "patc_world", "t3_stchange_world") if s not in by]
    if errors:
        raise CheckFailed(errors)
    # identity check: production - consumption = net withdrawals with the sign EIA uses (withdrawals negative when
    # stocks build), within rounding
    worst = max(abs(by["papr_world"][d]["value"] - by["patc_world"][d]["value"] + by["t3_stchange_world"][d]["value"])
                for d in by["papr_world"] if d in by["patc_world"] and d in by["t3_stchange_world"])
    if worst > 0.05:
        raise CheckFailed([f"production - consumption differs from EIA's inventory withdrawals by up to {worst:.3f} mb/d"])
    with (OUT / "eia_steo_3a.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    bal = []
    for d in sorted(by["papr_world"]):
        s, c = by["papr_world"][d]["value"], by["patc_world"].get(d, {}).get("value")
        if c is None:
            continue
        bal.append({"date": d, "supply": s, "demand": c, "balance": round(s - c, 6),
                    "stock_change": by["t3_stchange_world"].get(d, {}).get("value"),
                    "forecast": by["papr_world"][d]["forecast"], "steo": steo})
    with (OUT / "world_oil_balance.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(bal[0]))
        w.writeheader()
        w.writerows(bal)
    m = re.match(r"([A-Za-z]+) (\d{4})", steo)
    code = f"S{m.group(2)}-{['January','February','March','April','May','June','July','August','September','October','November','December'].index(m.group(1)) + 1:02d}" if m else f"S{fp[:8]}"
    write_release(OUT, {"code": code, "label": f"EIA STEO {steo}", "steo": steo, "last_historical": last_hist,
                        "source": NAME, "table": "EIA STEO table 3a (STEO_m.xlsx)"}, warnings, len(rows),
                  {"fingerprint": fp, "identity_worst_mbd": round(worst, 4)})
    h = [x for x in bal if not x["forecast"]][-1]
    return {"updated": True, "code": code, "warnings": warnings,
            "summary": f"{steo} STEO: history to {last_hist[:7]}; {h['date'][:7]} supply {h['supply']:.2f}, demand {h['demand']:.2f} mb/d"}
