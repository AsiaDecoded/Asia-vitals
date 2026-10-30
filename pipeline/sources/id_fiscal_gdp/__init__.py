"""Indonesia central government revenue, expenditure and surplus/deficit as % of GDP: CALCULATED (asked for on
30 Oct 2026), plus the Ministry of Finance's own published year-to-date deficit ratio for the current year.

  Annual, calculated: SEKI IV.1-IV.3 actual (Rp billion; data/id/fiscal/id_fiscal_annual.csv, from id_fiscal_seki)
  divided by BPS annual nominal GDP, 2010 series (Rp billion, current prices; data/id/gdp/id_gdp_annual.csv, code
  800, from id_gdp_bps), × 100. From 2010, the first year of BPS's current GDP series.
  Current year, published: the deficit as % of GDP, year to date, as printed in the Ministry's APBN KiTa deck
  (data/id/fiscal/id_fiscal_monthly.csv, from id_fiscal_kemenkeu), latest month, for a year with no full-year actual.
  The Ministry divides by its own full-year GDP estimate, which is not published as a figure, so revenue and
  expenditure ratios are not formed for that year.

Runs after id_gdp_bps, id_fiscal_seki and id_fiscal_kemenkeu; reads their files only (no downloads).
"""
import csv
import hashlib
import json

from core.common import DATA, CheckFailed, read_json, write_long, write_release

NAME = "id_fiscal_gdp"
DESCRIPTION = "Indonesia budget revenue, expenditure and balance as % of GDP (calculated; current year: MoF published deficit ratio)"
OUT = DATA / "id" / "fiscal_gdp"
SOURCE = "Asia Decoded calculation from Ministry of Finance (SEKI) and BPS data; current year Ministry of Finance"
LABELS = {"revenue": "Pendapatan Negara dan Hibah", "expenditure": "Belanja Negara", "balance": "Surplus / Defisit"}
TABLE = {"revenue": "revenue", "expenditure": "expenditure", "balance": "financing"}


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    gdp = {}
    for r in csv.DictReader(open(DATA / "id" / "gdp" / "id_gdp_annual.csv", encoding="utf-8")):
        if r["code"] == "800" and r["nominal_level"]:
            gdp[int(r["date"][:4])] = float(r["nominal_level"])
    fis = {}
    for r in csv.DictReader(open(DATA / "id" / "fiscal" / "id_fiscal_annual.csv", encoding="utf-8")):
        if r["basis"] != "actual":
            continue
        for k, lab in LABELS.items():
            if r["table"] == TABLE[k] and r["label_id"] == lab and r["value"] != "":
                fis.setdefault(int(r["year"]), {}).setdefault(k, float(r["value"]))
    monthly = list(csv.DictReader(open(DATA / "id" / "fiscal" / "id_fiscal_monthly.csv", encoding="utf-8")))
    errors, warnings, rows = [], [], []
    years = sorted(y for y in fis if y in gdp)
    if not years:
        errors.append("no year with both a SEKI actual and BPS annual nominal GDP")
    for y in years:
        f = fis[y]
        if not all(k in f for k in LABELS):
            errors.append(f"{y}: revenue, expenditure or balance missing in SEKI")
            continue
        g = gdp[y]
        row = {"year": y, "basis": "actual", "through": "", "gdp": g, **{f"{k}_pct": round(f[k] / g * 100, 3) for k in LABELS},
               **{k: f[k] for k in LABELS}, "method": "calculated: SEKI actual / BPS annual nominal GDP"}
        if abs(row["revenue_pct"] - row["expenditure_pct"] - row["balance_pct"]) > 0.01:
            errors.append(f"{y}: ratios do not add up ({row['revenue_pct']} - {row['expenditure_pct']} vs {row['balance_pct']})")
        rows.append(row)
    missing = sorted(y for y in fis if y >= 2010 and y not in gdp)
    if missing:
        warnings.append(f"SEKI actual with no BPS annual GDP yet: {missing}")
    done = {r["year"] for r in rows}
    latest = {}
    for r in monthly:
        y = int(r["date"][:4])
        if r.get("balance_pct_gdp") and (y not in latest or r["date"] > latest[y]["date"]):
            latest[y] = r
    for y, r in sorted(latest.items()):
        if y in done or y in fis:
            continue
        rows.append({"year": y, "basis": "ytd", "through": r["date"][:7], "gdp": "", "revenue_pct": "", "expenditure_pct": "",
                     "balance_pct": float(r["balance_pct_gdp"]), "revenue": float(r["revenue"]) * 1000,
                     "expenditure": float(r["expenditure"]) * 1000, "balance": float(r["balance"]) * 1000,
                     "method": "published: Ministry of Finance APBN KiTa, deficit % of GDP, year to date"})
    if errors:
        raise CheckFailed(errors)
    rows.sort(key=lambda r: r["year"])
    cols = ["year", "basis", "through", "revenue_pct", "expenditure_pct", "balance_pct", "revenue", "expenditure", "balance", "gdp", "method"]
    fp = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    with open(OUT / "id_fiscal_gdp.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])
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
