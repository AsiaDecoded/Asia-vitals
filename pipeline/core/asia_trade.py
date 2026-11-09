"""Asia merchandise trade: one file for the 12 economies from the trade_<cc> sources, and the same data in the layout
of the CEIC dump it replaces (APAC_trade_data.xlsx, sheet "Raw data": one row per series, one column per month).

  data/asia/trade/asia_trade.csv        economy, flow, partner, product, date, usd_mn, usd_calculated, series, unit, value
  data/asia/trade/APAC_trade_data.xlsx  CEIC series list (pipeline/core/trade_ceic_series.csv) mapped to national series;
                                        US$ million; a series with no national source is kept as an empty row, and the
                                        "Source" column says why
  data/asia/trade/coverage.csv          per CEIC series: national series used, first and last month
  release_row.json                      code = hash of the files
"""
import csv
import hashlib
import json
from pathlib import Path

from . import trade
from .common import DATA, read_json, write_release

OUT = DATA / "asia" / "trade"
HERE = Path(__file__).resolve().parent
ECON = ["CN", "HK", "TW", "JP", "KR", "IN", "ID", "MY", "PH", "SG", "TH", "VN"]
NAMES = {"CN": "China", "HK": "Hong Kong SAR (China)", "TW": "Taiwan (China)", "JP": "Japan", "KR": "South Korea", "IN": "India",
         "ID": "Indonesia", "MY": "Malaysia", "PH": "Philippines", "SG": "Singapore", "TH": "Thailand", "VN": "Vietnam"}


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for cc in ECON:
        rows += trade.read(cc.lower())
    rows = [r for r in rows if r.get("usd_mn") not in (None, "")]
    cols = ["economy", "flow", "partner", "product", "date", "usd_mn", "usd_calculated", "series", "unit", "value"]
    with open(OUT / "asia_trade.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    idx = {}
    for r in rows:
        idx.setdefault((r["economy"], r["flow"], r["partner"], r["product"]), {})[r["date"][:7]] = (float(r["usd_mn"]), r["series"])
    spec = list(csv.DictReader(open(HERE / "trade_ceic_series.csv", newline="", encoding="utf-8")))
    months = sorted({d for s in idx.values() for d in s})
    months = [m for m in months if m >= "1990-01"]
    cov = []
    import openpyxl  # noqa: PLC0415
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Raw data"
    ws.append(["Series (as in the CEIC file)", "Region", "Unit", "National source"] + [f"{m}" for m in months])
    for sp in spec:
        key = (sp["economy"], sp["flow"], sp["partner"], sp["product"])
        s = idx.get(key, {})
        src = sorted({v[1] for v in s.values()})
        label = src[-1] if src else (sp.get("note") or "no national series collected")
        ws.append([sp["ceic_series"], NAMES.get(sp["economy"], sp["economy"]), "USD mn", label] +
                  [round(s[m][0], 3) if m in s else None for m in months])
        have = sorted(s)
        cov.append({**sp, "national_series": label, "first": have[0] if have else "", "last": have[-1] if have else "",
                    "months": len(have)})
    notes = wb.create_sheet("Notes")
    for line in [
        "Built by the AsiaDecoded/asia-vitals pipeline from national sources (core/asia_trade.py; sources trade_<economy>).",
        "Values in US$ million. Where an agency publishes only its own currency, converted at the BIS monthly average rate",
        "(mean of BIS daily rates), flagged usd_calculated = y in asia_trade.csv. EU: as published where the agency publishes",
        "an EU total, otherwise the sum of the 27 current members (calculated). Series with no national source are left empty.",
    ]:
        notes.append([line])
    wb.save(OUT / "APAC_trade_data.xlsx")
    with open(OUT / "coverage.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, list(cov[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(cov)
    fp = hashlib.sha256((OUT / "asia_trade.csv").read_bytes()).hexdigest()[:10]
    state = read_json(OUT / "release.json", {}) or {}
    if state.get("code") == f"R{fp}":
        return {"updated": False, "summary": "Asia trade unchanged", "warnings": []}
    filled = sum(1 for c in cov if c["months"])
    write_release(OUT, {"code": f"R{fp}", "label": f"{filled} of {len(cov)} CEIC series filled", "source": "core.asia_trade"},
                  [], len(rows))
    return {"updated": True, "summary": f"{len(rows)} rows; {filled} of {len(cov)} CEIC series filled", "warnings": []}
