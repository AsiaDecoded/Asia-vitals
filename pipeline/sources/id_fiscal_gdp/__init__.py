"""Indonesia central government revenue, expenditure and surplus/deficit as % of GDP: CALCULATED (asked for on
30 Oct 2026), plus the Ministry of Finance's own published year-to-date deficit ratio for the current year.

  Annual, calculated: SEKI IV.1-IV.3 actual (Rp billion; data/id/fiscal/id_fiscal_annual.csv, from id_fiscal_seki)
  divided by BPS annual nominal GDP, 2010 series (Rp billion, current prices; data/id/gdp/id_gdp_annual.csv, code
  800, from id_gdp_bps), × 100. From 2010, the first year of BPS's current GDP series.
  Current year (no full-year actual yet), calculated (asked for 30 Oct 2026): the Ministry's year-to-date outturn
  (data/id/fiscal/id_fiscal_monthly.csv, from id_fiscal_kemenkeu) at the end of the latest quarter for which BPS has
  published quarterly nominal GDP, divided by the sum of that year's quarterly nominal GDP to that quarter
  (data/id/gdp/id_gdp.csv, code 800). So 2026 runs to June until Q3 GDP is published. This is not the Ministry's own
  ratio, which divides the year-to-date deficit by its full-year GDP estimate; that published ratio for the latest month
  is kept as mof_balance_pct (month in mof_through) and is what the dashboard shows for the current year's balance
  (asked for 30 Oct 2026: deficit as published).

  Before 2010 (asked for 30 Oct 2026): the same SEKI actuals (2001 on) divided by the IMF World Economic Outlook's
  nominal GDP (data/id/gdp_imf/id_gdp_imf.csv, from id_gdp_imf), which equals BPS from 2010 and links BPS's earlier
  bases to the 2010 level (the IMF's splice, published). Used in place of World Bank WDI, which does not link them.
  Fiscal years before 2001 ran April-March, so they are not divided by calendar-year GDP.

Runs after id_gdp_bps, id_gdp_imf, id_fiscal_seki and id_fiscal_kemenkeu; reads their files only (no downloads).
"""
import csv
import hashlib
import json

from core.common import DATA, CheckFailed, read_json, write_long, write_release

NAME = "id_fiscal_gdp"
DESCRIPTION = "Indonesia budget revenue, expenditure and balance as % of GDP (calculated; 2001-2009 on IMF WEO GDP; current year to the latest quarter with GDP)"
OUT = DATA / "id" / "fiscal_gdp"
SOURCE = "Ministry of Finance (SEKI, APBN KiTa), BPS"
LABELS = {"revenue": "Pendapatan Negara dan Hibah", "expenditure": "Belanja Negara", "balance": "Surplus / Defisit"}
TABLE = {"revenue": "revenue", "expenditure": "expenditure", "balance": "financing"}


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    gdp = {}
    for r in csv.DictReader(open(DATA / "id" / "gdp" / "id_gdp_annual.csv", encoding="utf-8")):
        if r["code"] == "800" and r["nominal_level"]:
            gdp[int(r["date"][:4])] = float(r["nominal_level"])
    wdi = {}   # pre-2010 denominator: IMF WEO nominal GDP
    pw = DATA / "id" / "gdp_imf" / "id_gdp_imf.csv"
    if pw.exists():
        for r in csv.DictReader(open(pw, encoding="utf-8")):
            if not r["imf_projection"]:
                wdi[int(r["year"])] = float(r["gdp_nominal_rp_bn"])
    fis = {}
    for r in csv.DictReader(open(DATA / "id" / "fiscal" / "id_fiscal_annual.csv", encoding="utf-8")):
        if r["basis"] != "actual":
            continue
        for k, lab in LABELS.items():
            if r["table"] == TABLE[k] and r["label_id"] == lab and r["value"] != "":
                fis.setdefault(int(r["year"]), {}).setdefault(k, float(r["value"]))
    monthly = list(csv.DictReader(open(DATA / "id" / "fiscal" / "id_fiscal_monthly.csv", encoding="utf-8")))
    errors, warnings, rows = [], [], []
    years = sorted(y for y in fis if y in gdp or (y >= 2001 and y in wdi))
    if not years:
        errors.append("no year with both a SEKI actual and BPS annual nominal GDP")
    for y in years:
        f = fis[y]
        if not all(k in f for k in LABELS):
            errors.append(f"{y}: revenue, expenditure or balance missing in SEKI")
            continue
        g = gdp.get(y) or wdi[y]
        how = "BPS annual nominal GDP" if y in gdp else "IMF WEO nominal GDP (linked to the 2010 base)"
        row = {"year": y, "basis": "actual", "through": "", "gdp": g, **{f"{k}_pct": round(f[k] / g * 100, 3) for k in LABELS},
               **{k: f[k] for k in LABELS}, "method": f"calculated: SEKI actual / {how}"}
        if abs(row["revenue_pct"] - row["expenditure_pct"] - row["balance_pct"]) > 0.01:
            errors.append(f"{y}: ratios do not add up ({row['revenue_pct']} - {row['expenditure_pct']} vs {row['balance_pct']})")
        rows.append(row)
    missing = sorted(y for y in fis if y >= 2010 and y not in gdp)
    nowdi = sorted(y for y in fis if 2001 <= y < 2010 and y not in wdi)
    if nowdi:
        warnings.append(f"no IMF GDP for {nowdi}")
    if missing:
        warnings.append(f"SEKI actual with no BPS annual GDP yet: {missing}")
    done = {r["year"] for r in rows}
    qgdp = {}
    for r in csv.DictReader(open(DATA / "id" / "gdp" / "id_gdp.csv", encoding="utf-8")):
        if r["code"] == "800" and r["nominal_level"]:
            qgdp[r["date"][:7]] = float(r["nominal_level"])
    mon = {r["date"][:7]: r for r in monthly}
    for y in sorted({int(m[:4]) for m in mon}):
        if y in done or y in fis:
            continue
        # latest quarter of year y with quarterly GDP for every quarter so far and an outturn at its last month
        best = None
        for q in (1, 2, 3, 4):
            qs = [f"{y}-{3 * k - 2:02d}" for k in range(1, q + 1)]
            end = f"{y}-{3 * q:02d}"
            if all(x in qgdp for x in qs) and end in mon:
                best = (q, end, sum(qgdp[x] for x in qs))
        if not best:
            warnings.append(f"{y}: no quarter-end outturn with quarterly GDP to match; year left out")
            continue
        q, end, g = best
        m = mon[end]
        latest = max(x for x in mon if x.startswith(str(y)))
        rv, ex, bl = (float(m[k]) * 1000 for k in ("revenue", "expenditure", "balance"))
        row = {"year": y, "basis": "ytd", "through": end, "gdp": g, "revenue_pct": round(rv / g * 100, 3),
               "expenditure_pct": round(ex / g * 100, 3), "balance_pct": round(bl / g * 100, 3),
               "revenue": rv, "expenditure": ex, "balance": bl,
               "mof_through": latest, "mof_balance_pct": float(mon[latest]["balance_pct_gdp"]) if mon[latest].get("balance_pct_gdp") else "",
               "method": f"calculated: Ministry of Finance outturn Jan-{end[5:]} / BPS nominal GDP Q1-Q{q}"}
        if abs(row["revenue_pct"] - row["expenditure_pct"] - row["balance_pct"]) > 0.02:
            errors.append(f"{y} year to date: ratios do not add up")
        rows.append(row)
        later = sorted(x for x in mon if x.startswith(str(y)) and x > end)
        if later:
            warnings.append(f"{y}: outturn published to {later[-1]}, ratio stops at {end} (quarterly GDP to Q{q})")
    if errors:
        raise CheckFailed(errors)
    rows.sort(key=lambda r: r["year"])
    cols = ["year", "basis", "through", "revenue_pct", "expenditure_pct", "balance_pct", "revenue", "expenditure", "balance", "gdp",
            "mof_through", "mof_balance_pct", "method"]
    fp = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    with open(OUT / "id_fiscal_gdp.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])
    last_a = max(r["year"] for r in rows if r["basis"] == "actual")
    ytd = [r for r in rows if r["basis"] == "ytd"]
    code = f"R{last_a}" + (f"-{ytd[-1]['through']}" if ytd else "")
    label = f"to {last_a}" + (f"; {ytd[-1]['year']} deficit to {ytd[-1]['through']}" if ytd else "")

    def long_rows():
        for r in rows:
            for k in ("revenue_pct", "expenditure_pct", "balance_pct"):
                if r[k] == "":
                    continue
                yield {"country": "ID", "indicator": "fiscal_gdp", "series": k, "label": k.replace("_pct", "") + ", % of GDP",
                       "measure": r["basis"], "area": "central government", "freq": "A", "date": f"{r['year']}-01-01",
                       "value": r[k], "unit": "% of GDP", "source": SOURCE, "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    write_release(OUT, {"code": code, "label": label, "latest_year": last_a,
                        "table": "calculated from data/id/fiscal/id_fiscal_annual.csv and data/id/gdp/id_gdp_annual.csv; "
                                 "current year from data/id/fiscal/id_fiscal_monthly.csv"},
                  warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    a = [r for r in rows if r["year"] == last_a][0]
    return {"updated": True, "code": code, "summary": f"{last_a}: revenue {a['revenue_pct']:.2f}%, expenditure {a['expenditure_pct']:.2f}%, "
            f"balance {a['balance_pct']:.2f}% of GDP; {len(rows)} years", "warnings": warnings}
