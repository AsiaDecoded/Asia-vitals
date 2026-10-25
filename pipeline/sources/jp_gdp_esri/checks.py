"""Checks run on every release before anything is committed.

Errors stop the run (nothing is committed). Warnings are printed and kept in data/release.json.
"""
import csv

TOL = 0.06  # one-decimal rounding on both sides


def run(tables, code, ref_date, previous_csv=None):
    errors, warnings = [], []
    lv = {b: {r["date"]: r for r in tables[(b, "level_saar")]["data"]} for b in ("real", "nominal")}
    lo = {b: {r["date"]: r for r in tables[(b, "level_orig")]["data"]} for b in ("real", "nominal")}

    # 1. Every table parsed, every component found, same quarters everywhere.
    dates = [r["date"] for r in tables[("real", "level_saar")]["data"]]
    for key, t in tables.items():
        if t["missing_columns"]:
            errors.append(f"{key}: missing columns {t['missing_columns']}")
        if [r["date"] for r in t["data"]] != dates:
            errors.append(f"{key}: quarters differ from real levels")

    # 2. The latest quarter is the one this release covers.
    if dates and dates[-1] != ref_date:
        errors.append(f"latest quarter {dates[-1]} but release {code} covers {ref_date}")

    # 3. Growth rates agree with levels (GDP, every quarter).
    for b in ("real", "nominal"):
        qq = {r["date"]: r["gdp"] for r in tables[(b, "qoq")]["data"]}
        qa = {r["date"]: r["gdp"] for r in tables[(b, "qoq_ann")]["data"]}
        yy = {r["date"]: r["gdp"] for r in tables[(b, "yoy")]["data"]}
        for i, d in enumerate(dates):
            if i >= 1 and qq[d] is not None:
                ratio = lv[b][d]["gdp"] / lv[b][dates[i - 1]]["gdp"]
                if abs((ratio - 1) * 100 - qq[d]) > TOL:
                    errors.append(f"{b} q/q {d}: published {qq[d]}, from levels {(ratio - 1) * 100:.2f}")
                if abs((ratio ** 4 - 1) * 100 - qa[d]) > TOL:
                    errors.append(f"{b} q/q annualised {d}: published {qa[d]}, from levels {(ratio ** 4 - 1) * 100:.2f}")
            if i >= 4 and yy[d] is not None:
                y = (lo[b][d]["gdp"] / lo[b][dates[i - 4]]["gdp"] - 1) * 100
                if abs(y - yy[d]) > TOL:
                    errors.append(f"{b} y/y {d}: published {yy[d]}, from original levels {y:.2f}")

    # 4. Contributions add up to GDP growth (allowing for rounding of eight items).
    parts = ["private_consumption", "residential", "business_investment", "private_inventories",
             "government_consumption", "public_investment", "public_inventories", "net_exports"]
    for key in ("contrib_qoq", "contrib_yoy"):
        for r in tables[("real", key)]["data"]:
            if r["gdp"] is None:
                continue
            gap = abs(sum(r[p] for p in parts) - r["gdp"])
            if gap > 0.35:
                errors.append(f"{key} {r['date']}: components sum differs from GDP by {gap:.2f}")

    # 5. Deflator index agrees with nominal / real levels.
    for r in tables[("deflator", "index_sa")]["data"]:
        d = r["date"]
        implied = lv["nominal"][d]["gdp"] / lv["real"][d]["gdp"] * 100
        if abs(implied - r["gdp"]) > 0.1:
            errors.append(f"deflator {d}: published {r['gdp']}, nominal/real {implied:.2f}")

    # 6. Revisions against the previous release (warnings only: benchmark revisions move everything).
    if previous_csv and previous_csv.exists():
        prev = {row["date"]: float(row["real_level"]) for row in csv.DictReader(open(previous_csv))
                if row["component"] == "GDP" and row["real_level"]}
        big = [d for d in dates if d in prev and abs(lv["real"][d]["gdp"] / prev[d] - 1) > 0.02]
        if big:
            warnings.append(f"real GDP level revised by more than 2% in {len(big)} quarters "
                            f"({big[0]} to {big[-1]}); expected only with a benchmark or annual revision")
        if dates and dates[-1] < max(prev, default=""):
            errors.append("new release ends earlier than the data already in the repo")
    return errors, warnings
