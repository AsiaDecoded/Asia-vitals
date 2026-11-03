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
    ("2011-12", "Annually", 1, "level"),   # GVA levels by industry, for the calculated services series
]
COLS = ["date", "freq", "period", "fy", "fq", "base_year", "code", "industry", "subindustry", "approach", "measure",
        "price", "value", "unit", "revision", "rev_rank", "calculated"]


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


def shown(rows, warnings=None):
    """Rows the page shows: quarterly 2022-23 base; annual latest vintage, 2011-12 base to 2022-23, then 2022-23 base.

    Where the latest vintage of a year holds more than one differing value (MoSPI's API returns three "Additional
    Revision" rows for 2012-13 and 2013-14, with no field telling them apart), the year is left out for that row and
    listed in warnings, rather than one value being picked.
    """
    out, best, clash = [], {}, set()
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
            clash.discard(k)
        elif r["rev_rank"] == best[k]["rev_rank"] and r["value"] != best[k]["value"]:
            clash.add(k)
    for k in sorted(clash):
        if warnings is not None:
            vals = sorted({x["value"] for x in rows if x["freq"] == "A" and (x["fy"], x["code"], x["measure"], x["price"]) == k
                           and x["rev_rank"] == best[k]["rev_rank"] and x["base_year"] == best[k]["base_year"]})
            warnings.append(f"{k[0]} {k[1]} {k[3]} {k[2]}: {best[k]['revision']} has {len(vals)} values {vals}; left out")
        del best[k]
    return out + sorted(best.values(), key=lambda r: (r["date"], r["code"], r["measure"], r["price"]))


SERVICES = ["trade_transport", "finance_re", "public_other"]


def services(rows, sh, warnings):
    """Services (tertiary sector), calculated (user, 3 Nov 2026): the sum of MoSPI's published GVA levels for trade,
    hotels, transport, communication and broadcasting; financial, real estate and professional services; and public
    administration, defence and other services, at constant and current prices. Growth = sum / sum a year earlier - 1,
    in %, rounded to one decimal as MoSPI publishes; always within one base. Quarterly: the 2022-23 base, levels as
    shown. Annual: each base's latest-vintage level for each year (years whose latest vintage has conflicting values
    are skipped); 2011-12 base for 2012-13 to 2022-23, 2022-23 base from 2023-24, as for the published series.
    """
    out = []

    def add(levels, freq, prev_of, pick):
        for (d, price), tot in sorted(levels.items()):
            p = levels.get((prev_of(d), price))
            if p is None or not pick(d):
                continue
            ref = tot["row"]
            out.append({**{k: ref[k] for k in ("date", "freq", "period", "fy", "fq", "base_year")}, "code": "services",
                        "industry": "Services (tertiary sector, calculated)", "subindustry": "", "approach": "",
                        "measure": "yoy", "price": price, "value": round((tot["v"] / p["v"] - 1) * 100, 1), "unit": "%",
                        "revision": ref["revision"], "rev_rank": ref["rev_rank"], "calculated": "y"})

    # quarterly
    lv = {}
    for r in sh:
        if r["freq"] == "Q" and r["measure"] == "level" and r["code"] in SERVICES:
            lv.setdefault((r["date"], r["price"]), {})[r["code"]] = r
    q = {k: {"v": sum(x["value"] for x in v.values()), "row": next(iter(v.values()))} for k, v in lv.items() if len(v) == 3}
    add(q, "Q", lambda d: f"{int(d[:4]) - 1}{d[4:]}", lambda d: True)
    # annual, per base
    for base, pick in (("2011-12", lambda d: d < "2023-04-01"), ("2022-23", lambda d: d >= "2023-04-01")):
        best, clash = {}, set()
        for r in rows:
            if r["freq"] != "A" or r["measure"] != "level" or r["code"] not in SERVICES or r["base_year"] != base:
                continue
            if r["approach"] not in ("", "Production Approach", "Production"):
                continue
            k = (r["date"], r["price"], r["code"])
            if k not in best or r["rev_rank"] > best[k]["rev_rank"]:
                best[k] = r; clash.discard(k)
            elif r["rev_rank"] == best[k]["rev_rank"] and r["value"] != best[k]["value"]:
                clash.add(k)
        for k in clash:
            del best[k]
        lv = {}
        for (d, price, code), r in best.items():
            lv.setdefault((d, price), {})[code] = r
        a = {k: {"v": sum(x["value"] for x in v.values()), "row": next(iter(v.values()))} for k, v in lv.items() if len(v) == 3}
        add(a, "A", lambda d: f"{int(d[:4]) - 1}{d[4:]}", pick)
    if not any(r["freq"] == "Q" for r in out):
        raise CheckFailed(["services: no quarterly growth calculated"])
    return out


def mfg_share(rows):
    """Manufacturing share of GVA and of GDP, % at current prices, annual, calculated (user, 3 Nov 2026): manufacturing
    GVA / total GVA (measure "share") and / GDP (measure "share_gdp"), MoSPI's published current-price levels, latest
    vintage of each year, on each base separately: 2011-12 base (2011-12 to its latest year) and 2022-23 base (from
    2022-23). Years whose latest vintage has conflicting values are skipped."""
    out = []
    for base in ("2011-12", "2022-23"):
        best, clash = {}, set()
        for r in rows:
            if r["freq"] != "A" or r["measure"] != "level" or r["price"] != "current" or r["base_year"] != base \
                    or r["code"] not in ("manufacturing", "gva", "gdp") or r["approach"] not in ("", "Production Approach", "Production"):
                continue
            k = (r["fy"], r["code"])
            if k not in best or r["rev_rank"] > best[k]["rev_rank"]:
                best[k] = r; clash.discard(k)
            elif r["rev_rank"] == best[k]["rev_rank"] and r["value"] != best[k]["value"]:
                clash.add(k)
        for k in clash:
            best.pop(k, None)
        for fy in sorted({k[0] for k in best}):
            m = best.get((fy, "manufacturing"))
            for den, measure, unit in (("gva", "share", "% of GVA"), ("gdp", "share_gdp", "% of GDP")):
                d = best.get((fy, den))
                if m and d and d["value"] > 0:
                    out.append({"date": m["date"], "freq": "A", "period": fy, "fy": fy, "fq": "", "base_year": base,
                                "code": "manufacturing", "industry": "Manufacturing", "subindustry": "", "approach": "",
                                "measure": measure, "price": "current", "value": round(m["value"] / d["value"] * 100, 2),
                                "unit": unit, "revision": m["revision"], "rev_rank": m["rev_rank"], "calculated": "y"})
    return out


def gdp_2011base(rows):
    """Real GDP growth on the 2011-12 base for every year MoSPI published it (2012-13 to its last year, 2025-26),
    latest vintage of each year, as published (code gdp_2011base; user, 3 Nov 2026: shown dashed beside the 2022-23
    base on the GDP tab's Chart 5 so the overlapping years can be compared). Conflicting latest vintages are skipped."""
    best, clash = {}, set()
    for r in rows:
        if r["freq"] != "A" or r["code"] != "gdp" or r["measure"] != "yoy" or r["price"] != "constant" or r["base_year"] != "2011-12":
            continue
        k = r["fy"]
        if k not in best or r["rev_rank"] > best[k]["rev_rank"]:
            best[k] = r; clash.discard(k)
        elif r["rev_rank"] == best[k]["rev_rank"] and r["value"] != best[k]["value"]:
            clash.add(k)
    return [{**best[k], "code": "gdp_2011base", "industry": "Gross Domestic Product (2011-12 base, all years)", "calculated": ""}
            for k in sorted(best) if k not in clash]


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
        lim = (-90, 200) if "." in r["code"] else (-40, 60)   # sub-rows (e.g. air transport) swing far more
        if r["measure"] == "yoy" and not lim[0] < r["value"] < lim[1]:
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
    clashes = []
    sh = shown(rows, clashes)
    warnings = clashes + check(rows, sh)
    for r in rows + sh:
        r.setdefault("calculated", "")
    sh = sh + services(rows, sh, warnings)
    sh = sh + mfg_share(rows)
    sh = sh + gdp_2011base(rows)
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
