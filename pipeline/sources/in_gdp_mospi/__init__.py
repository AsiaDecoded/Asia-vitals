"""India GDP and GVA, MoSPI National Accounts Statistics (api.mospi.gov.in, /api/nas/getNASData), as published.

Nothing is calculated here: growth rates are MoSPI's own (indicators 21 GVA growth rate and 22 GDP growth rate, % y/y,
at constant and current prices); levels (indicators 1 GVA and 5 GDP) are kept beside them in Rs crore.

Coverage (decided 2 Nov 2026):
- Quarterly: the 2022-23 base only (from Q1 2022-23; growth rates from Q1 2023-24). The 2011-12-base quarterly series is
  not used (it disagrees with the new base by up to 3pp where they overlap). MoSPI's own back series on the 2022-23 base
  is due by December 2026; add it when it comes.
- Annual: MoSPI's published growth rates, 2011-12 base for 2012-13 to 2022-23 (latest vintage per year), 2022-23 base
  from 2023-24. The 2011-12-base vintages for later years are kept in in_gdp_vintages.csv, not shown.
- Industries: the 8 published GVA industries and total GVA (quarterly); annual also has MoSPI's sub-rows.

Dates: a quarter is dated at its first calendar month (Q1 2026-27 = Apr-Jun 2026 = 2026-04-01), as the India page labels
quarters by calendar months. A fiscal year is dated at its first month (2025-26 = 2025-04-01).
MoSPI's server needs the legacy-TLS flag (core.mospi). About 30 calls, under a minute.
"""
import csv
import hashlib
import json
import re

from core import mospi
from core.common import DATA, CheckFailed, read_json, write_long, write_release

NAME = "in_gdp_mospi"
DESCRIPTION = "India GDP and GVA by industry, quarterly (2022-23 base) and annual, MoSPI NAS, as published"
OUT = DATA / "in" / "gdp"
PATH = "/api/nas/getNASData"

INDUSTRY = {
    "Agriculture, Livestock, Forestry and Fishing": "agri",
    "Mining and Quarrying": "mining",
    "Manufacturing": "manufacturing",
    "Electricity, Gas, Water Supply & Other Utility Services": "utilities",
    "Construction": "construction",
    "Trade, Hotels, Transport, Communication & Services Related to Broadcasting": "trade_transport",
    "Trade, Repair, Hotels and Restaurants": "trade_hotels",
    "Transport, Storage, Communication & Services Related to Broadcasting": "transport_comm",
    "Financial, Real Estate & Professional Services": "finance_re",
    "Financial Services": "financial",
    "Real Estate, Ownership of Dwelling & Professional Services": "real_estate",
    "Public Administration, Defence & Other Services": "public_other",
    "Public Administration and Defence": "public_admin",
    "Other Services": "other_services",
    "Total Gross Value Added": "gva",
}
MAIN8 = ["agri", "mining", "manufacturing", "utilities", "construction", "trade_transport", "finance_re", "public_other"]
# MoSPI's revision names, earliest to latest; the latest vintage of a year is the one shown.
REVISIONS = ["First Advance Estimates", "Second Advance Estimates", "Provisional Estimates", "First Revised Estimates",
             "Second Revised Estimates", "Third Revised Estimates", "Final Estimates", "Additional Revision"]
QUERIES = [  # (base_year, frequency, indicator, measure)
    ("2022-23", "Quarterly", 22, "yoy"), ("2022-23", "Quarterly", 21, "yoy"),
    ("2022-23", "Quarterly", 5, "level"), ("2022-23", "Quarterly", 1, "level"),
    ("2022-23", "Annually", 22, "yoy"), ("2022-23", "Annually", 21, "yoy"),
    ("2022-23", "Annually", 5, "level"), ("2022-23", "Annually", 1, "level"),
    ("2011-12", "Annually", 22, "yoy"), ("2011-12", "Annually", 21, "yoy"), ("2011-12", "Annually", 5, "level"),
]
COLS = ["date", "freq", "period", "fy", "fq", "base_year", "code", "industry", "subindustry", "approach", "measure",
        "price", "value", "unit", "revision", "rev_rank"]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def fetch():
    out = []
    for by, freq, ind, measure in QUERIES:
        rows, total = mospi.paged(PATH, {"base_year": by, "series": "Current", "frequency_code": freq,
                                         "indicator_code": str(ind)})
        if not rows or (total is not None and len(rows) != int(total)):
            raise CheckFailed([f"NAS {by} {freq} indicator {ind}: {len(rows)} rows of {total}"])
        for r in rows:
            out.append((by, freq, ind, measure, r))
    return out


def tidy(raw):
    rows, errors = [], []
    for by, freq, ind, measure, r in raw:
        fy = r["year"]
        start = int(fy[:4])
        if freq == "Quarterly":
            q = int(r["quarter"][1])
            m = (4 + 3 * (q - 1) - 1) % 12 + 1
            yr = start + (1 if q == 4 else 0)
            date, fq, period = f"{yr}-{m:02d}-01", f"{fy} Q{q}", f"{yr}-Q{(m - 1) // 3 + 1}"
        else:
            date, fq, period = f"{start}-04-01", "", fy
        ind_name = r.get("industry") or ""
        if r.get("institutional_sector"):   # GVA by institutional sector (annual): not used on the page
            continue
        if ind in (22, 5):
            code = "gdp"
        elif ind_name in INDUSTRY:
            code = INDUSTRY[ind_name]
        else:
            errors.append(f"unknown industry {ind_name!r}")
            continue
        sub = r.get("subindustry") or ""
        if sub:
            code = f"{code}.{slug(sub)}"
        rev = r.get("revision") or ""
        if rev and rev not in REVISIONS:
            errors.append(f"unknown revision {rev!r}")
        for price, key in (("constant", "constant_price"), ("current", "current_price")):
            v = r.get(key)
            if v in (None, "", "-"):
                continue
            rows.append({"date": date, "freq": "Q" if freq == "Quarterly" else "A", "period": period, "fy": fy, "fq": fq,
                         "base_year": by, "code": code, "industry": ind_name or "Gross Domestic Product",
                         "subindustry": sub, "approach": r.get("approach") or "", "measure": measure, "price": price,
                         "value": float(v), "unit": "%" if measure == "yoy" else "Rs crore", "revision": rev,
                         "rev_rank": REVISIONS.index(rev) if rev in REVISIONS else -1})
    if errors:
        raise CheckFailed(sorted(set(errors)))
    return rows


def shown(rows):
    """Rows the page shows: quarterly 2022-23 base; annual latest vintage, 2011-12 base to 2022-23, then 2022-23 base."""
    out, best = [], {}
    for r in rows:
        if r["freq"] == "Q":
            out.append(r)
            continue
        if r["approach"] not in ("", "Production Approach", "Production"):
            continue
        start = int(r["fy"][:4])
        if (r["base_year"] == "2011-12") != (start <= 2022):
            continue
        k = (r["fy"], r["code"], r["measure"], r["price"])
        if k not in best or r["rev_rank"] > best[k]["rev_rank"]:
            best[k] = r
    return out + sorted(best.values(), key=lambda r: (r["date"], r["code"], r["measure"], r["price"]))


def check(rows, sh):
    errors, warnings = [], []
    q = [r for r in sh if r["freq"] == "Q"]
    gy = sorted(r["date"] for r in q if r["code"] == "gdp" and r["measure"] == "yoy" and r["price"] == "constant")
    if not gy or gy[0] != "2023-04-01":
        errors.append(f"quarterly real GDP growth should start Apr-Jun 2023, got {gy[:1]}")
    want, (y, m) = [], (2023, 4)
    while f"{y}-{m:02d}-01" <= (gy[-1] if gy else ""):
        want.append(f"{y}-{m:02d}-01")
        y, m = (y + 1, 1) if m == 10 else (y, m + 3)
    if gy != want:
        errors.append(f"quarterly real GDP growth has gaps or duplicates: {sorted(set(want) ^ set(gy))[:6]}")
    last = gy[-1] if gy else ""
    for price in ("constant", "current"):
        have = {r["code"] for r in q if r["date"] == last and r["measure"] == "yoy" and r["price"] == price}
        miss = [c for c in MAIN8 + ["gva", "gdp"] if c not in have]
        if miss:
            errors.append(f"{last} {price} growth missing for {miss}")
    for r in sh:
        if r["measure"] == "yoy" and not -40 < r["value"] < 60:
            errors.append(f"{r['fq'] or r['fy']} {r['code']} {r['price']} growth {r['value']} out of range")
        if r["measure"] == "level" and r["value"] <= 0 and r["code"] in ("gdp", "gva"):
            errors.append(f"{r['fq'] or r['fy']} {r['code']} level {r['value']}")
    # Quarterly GVA levels: the 8 industries sum to total GVA (MoSPI's tables add up to rounding).
    for d in sorted({r["date"] for r in q}):
        for price in ("constant", "current"):
            lv = {r["code"]: r["value"] for r in q if r["date"] == d and r["measure"] == "level" and r["price"] == price}
            if "gva" in lv and all(c in lv for c in MAIN8):
                s = sum(lv[c] for c in MAIN8)
                if abs(s / lv["gva"] - 1) > 0.002:
                    warnings.append(f"{d} {price}: industries sum to {s:,.0f}, total GVA {lv['gva']:,.0f}")
    a = [r for r in sh if r["freq"] == "A" and r["code"] == "gdp" and r["measure"] == "yoy" and r["price"] == "constant"]
    yrs = sorted(int(r["fy"][:4]) for r in a)
    if not yrs or yrs[0] > 2012 or yrs != list(range(yrs[0], yrs[-1] + 1)):
        errors.append(f"annual real GDP growth years {yrs[:2]}..{yrs[-2:]} (need every year from 2012-13)")
    if errors:
        raise CheckFailed(errors)
    return warnings


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    rows = tidy(fetch())
    sh = shown(rows)
    warnings = check(rows, sh)
    fp = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change ({state.get('label')})"}
    for name, data in (("in_gdp.csv", sh), ("in_gdp_vintages.csv", rows)):
        with open(OUT / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=COLS, lineterminator="\n")
            w.writeheader()
            for r in sorted(data, key=lambda r: (r["freq"], r["date"], r["base_year"], r["code"], r["measure"], r["price"], r["rev_rank"])):
                w.writerow({k: r[k] for k in COLS})
    q = [r for r in sh if r["freq"] == "Q" and r["code"] == "gdp" and r["measure"] == "yoy"]
    lastq = max(r["date"] for r in q)
    fq = next(r["fq"] for r in q if r["date"] == lastq)
    real = next(r["value"] for r in q if r["date"] == lastq and r["price"] == "constant")
    nom = next(r["value"] for r in q if r["date"] == lastq and r["price"] == "current")
    code = f"Q{fq.replace(' ', '')}"
    label = f"{fq} (2022-23 base): real GDP {real}%, nominal {nom}% y/y"
    nlong = write_long(({"country": "IN", "indicator": "gdp", "series": f"{r['code']}_{r['measure']}_{r['price']}",
                         "label": f"{r['industry']}{', ' + r['subindustry'] if r['subindustry'] else ''}, "
                                  f"{'growth' if r['measure'] == 'yoy' else 'level'}, {r['price']} prices ({r['base_year']} base)",
                         "measure": r["measure"], "area": "national", "freq": r["freq"], "date": r["date"],
                         "value": r["value"], "unit": r["unit"], "source": "MoSPI, National Accounts Statistics",
                         "release": code} for r in sh), OUT / "long.csv")
    write_release(OUT, {"code": code, "label": label, "latest_quarter": fq, "latest_date": lastq},
                  warnings, len(sh), {"fingerprint": fp, "long_rows": nlong, "vintage_rows": len(rows)})
    return {"updated": True, "code": code, "summary": label, "warnings": warnings}
