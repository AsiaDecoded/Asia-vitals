"""Merchandise trade from national sources: shared definitions and writer for the trade_<cc> sources (9 Nov 2026).

Every trade source writes data/trade/<cc>/trade_<cc>.csv in one long format:

  economy, flow, partner, product, date, value, unit, usd_mn, usd_calculated, series

  flow      exports | imports | domestic_exports | re_exports
  partner   WLD (world) | ISO-2 code of the partner (US, CN, HK, JP, TW, KR, IN, ID, MY, PH, SG, TH, VN and EU members)
            | EU (European Union: as published where the agency publishes it, otherwise the sum of the 27 current
            members, calculated)
  product   TOTAL | HS<code> (an HS heading, chapter or subheading, e.g. HS85, HS8471, HS2709) | <agency grouping>
  value     as published, in `unit`
  usd_mn    US$ million: as published where the agency publishes US$; otherwise value converted at the BIS monthly
            average exchange rate (mean of the BIS daily rates in data/<cc>/fx/<cc>_fx_daily.csv), usd_calculated = y
  series    the agency's own name or code for the series

Agencies' figures are used as published (valuation fob/cif and trade system as each agency compiles them).
"""
import csv
from pathlib import Path

from .common import DATA

OUT = DATA / "trade"
PARTNERS = ["WLD", "US", "CN", "HK", "JP", "EU", "TW", "KR", "IN", "ID", "MY", "PH", "SG", "TH", "VN"]
EU27 = ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU",
        "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"]
COLS = ["economy", "flow", "partner", "product", "date", "value", "unit", "usd_mn", "usd_calculated", "series"]
FX_FILE = {"jp": ("jp_fx_daily.csv", "rate"), "kr": ("kr_fx_daily.csv", "rate"), "tw": ("tw_fx_daily.csv", "rate"),
           "hk": ("hk_fx_daily.csv", "rate"), "sg": ("sg_fx_daily.csv", "rate"), "cn": ("cn_fx_daily.csv", "rate"),
           "my": ("my_fx_daily.csv", "rate"), "th": ("th_fx_daily.csv", "rate"), "ph": ("ph_fx_daily.csv", "rate"),
           "in": ("in_fx_daily.csv", "rate"), "id": ("id_fx_daily.csv", "usd_idr")}


def fx_monthly(cc):
    """{'YYYY-MM': local currency per US$}, the mean of the BIS daily rates in each month (calculated)."""
    name, col = FX_FILE[cc]
    acc = {}
    with open(DATA / cc / "fx" / name, newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                v = float(r[col])
            except (TypeError, ValueError):
                continue
            a = acc.setdefault(r["date"][:7], [0.0, 0])
            a[0] += v
            a[1] += 1
    return {m: s / n for m, (s, n) in acc.items() if n}


def to_usd(rows, cc, scale):
    """Fill usd_mn for rows in local currency: value * scale (to units of currency) / rate / 1e6."""
    fx = fx_monthly(cc)
    for r in rows:
        if r.get("usd_mn") in (None, "") and r.get("value") not in (None, ""):
            rate = fx.get(r["date"][:7])
            if rate:
                r["usd_mn"] = round(float(r["value"]) * scale / rate / 1e6, 4)
                r["usd_calculated"] = "y"
    return rows


def eu_sum(rows, members_present, series="sum of the 27 current EU members (calculated)"):
    """Add partner EU = sum over EU27 members for each (economy, flow, product, date) where all listed members exist."""
    acc = {}
    for r in rows:
        if r["partner"] in EU27 and r["value"] not in (None, ""):
            k = (r["economy"], r["flow"], r["product"], r["date"], r["unit"])
            a = acc.setdefault(k, [0.0, 0.0, set(), r.get("usd_calculated", "")])
            a[0] += float(r["value"])
            a[1] += float(r["usd_mn"] or 0)
            a[2].add(r["partner"])
    out = []
    for (e, f, p, d, u), (v, usd, have, calc) in acc.items():
        if have >= set(members_present):
            out.append({"economy": e, "flow": f, "partner": "EU", "product": p, "date": d, "value": round(v, 4), "unit": u,
                        "usd_mn": round(usd, 4), "usd_calculated": calc, "series": series})
    return out


def write(cc, rows):
    folder = OUT / cc
    folder.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda r: (r["flow"], r["product"], PARTNERS.index(r["partner"]) if r["partner"] in PARTNERS else 99,
                                       r["partner"], r["date"]))
    with open(folder / f"trade_{cc}.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, COLS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in COLS})
    return folder


def read(cc):
    p = OUT / cc / f"trade_{cc}.csv"
    if not p.exists():
        return []
    with open(p, newline="") as fh:
        return list(csv.DictReader(fh))


def latest(rows, flow="exports", partner="WLD", product="TOTAL"):
    ds = [r["date"] for r in rows if r["flow"] == flow and r["partner"] == partner and r["product"] == product and r["value"] != ""]
    return max(ds) if ds else None
