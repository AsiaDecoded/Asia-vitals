"""Asia table: the figures the Asia inflation tab shows, picked from the country outputs.

Nothing is calculated here. Each row of SPEC names one series already written by a
country source (published by the statistics office, or calculated in that country's
pipeline) and copies its monthly values from START. Economies whose data is not on
this branch yet are skipped and listed in release.json.

Columns of the Asia table (definitions set by Asia Decoded):
  cpi            headline CPI, % y/y
  food           food and non-alcoholic beverages (COICOP 01), % y/y
  energy         energy, % y/y
  core           CPI excluding food and non-alcoholic beverages and energy, % y/y
  official_core  the core measure the statistics office or central bank publishes, % y/y
  ppi            producer prices, % y/y

Output: data/asia/table/asia_table.csv, release.json, release_row.json.
"""
import csv
import hashlib
import json

from core.common import DATA, read_json, write_release

START = "2015-01-01"
OUT = DATA / "asia" / "table"

ECONOMIES = ["JP", "KR", "TW", "HK", "CN", "IN", "ID", "TH", "MY", "SG", "PH", "VN"]
NAMES = {"JP": "Japan", "KR": "South Korea", "TW": "Taiwan", "HK": "Hong Kong", "CN": "China",
         "IN": "India", "ID": "Indonesia", "TH": "Thailand", "MY": "Malaysia",
         "SG": "Singapore", "PH": "Philippines", "VN": "Vietnam"}

PUB, CALC = "published", "calculated"

# economy, column, file, filters, value column, basis, label
SPEC = [
    # Japan
    ("JP", "cpi", "jp/cpi/jp_cpi.csv", {"area": "national", "series": "all"}, "yoy", PUB, "All items"),
    ("JP", "food", "jp/cpi_food/jp_cpi_food.csv", {}, "yoy", PUB, "Food and non-alcoholic beverages (COICOP 01)"),
    ("JP", "energy", "jp/cpi/jp_cpi.csv", {"area": "national", "series": "energy"}, "yoy", PUB, "Energy"),
    ("JP", "core", "jp/cpi_core3/jp_cpi_core3.csv", {}, "yoy", CALC, "Core 2: less food (excl. alcohol) and energy, plus eating out"),
    ("JP", "official_core", "jp/cpi/jp_cpi.csv", {"area": "national", "series": "core"}, "yoy", PUB, "All items less fresh food"),
    ("JP", "ppi", "jp/ppi/jp_ppi.csv", {"series": "ppi"}, "yoy", PUB, "PPI (CGPI)"),
    # South Korea (y/y calculated from the published index in the Korea pipeline)
    ("KR", "cpi", "kr/cpi/kr_cpi.csv", {"area": "national", "series": "all"}, "yoy", CALC, "All items"),
    ("KR", "food", "kr/cpi/kr_cpi.csv", {"area": "national", "series": "div_A"}, "yoy", CALC, "Food and non-alcoholic beverages"),
    ("KR", "energy", "kr/cpi/kr_cpi.csv", {"area": "national", "series": "energy"}, "yoy", CALC, "Energy: the ministry's nine energy items at published weights (Dec 2023-)"),
    ("KR", "core", "kr/cpi/kr_cpi.csv", {"area": "national", "series": "ex_food_energy"}, "yoy", CALC, "Excl. food and energy"),
    # Official core: the Bank of Korea's measure (excl. food and energy), the same series as core
    ("KR", "official_core", "kr/cpi/kr_cpi.csv", {"area": "national", "series": "ex_food_energy"}, "yoy", CALC, "Excl. food and energy (Bank of Korea's core)"),
    ("KR", "ppi", "kr/ppi/kr_ppi.csv", {"series": "ppi"}, "yoy", CALC, "PPI"),
    # Taiwan
    ("TW", "cpi", "tw/cpi/tw_cpi.csv", {"area": "national", "series": "all", "measure": "yoy"}, "value", PUB, "All items"),
    ("TW", "food", "tw/cpi/tw_cpi.csv", {"area": "national", "series": "food01", "measure": "yoy"}, "value", CALC, "Food and non-alcoholic beverages (COICOP 01): DGBAS food excl. alcohol and eating out"),
    ("TW", "energy", "tw/cpi/tw_cpi.csv", {"area": "national", "series": "energy", "measure": "yoy"}, "value", PUB, "Energy"),
    ("TW", "core", "tw/cpi/tw_cpi.csv", {"area": "national", "series": "core1", "measure": "yoy"}, "value", CALC, "Core 1: excl. food and non-alcoholic beverages (COICOP 01) and energy"),
    ("TW", "official_core", "tw/cpi/tw_cpi.csv", {"area": "national", "series": "core", "measure": "yoy"}, "value", PUB, "Core (excl. fruit, vegetables and energy)"),
    ("TW", "ppi", "tw/ppi/tw_ppi.csv", {"series": "ppi_all", "measure": "yoy"}, "value", PUB, "PPI"),
    # Hong Kong
    ("HK", "cpi", "hk/cpi/hk_cpi.csv", {"index_type": "composite", "basis": "headline", "series": "all"}, "yoy", PUB, "Composite CPI"),
    ("HK", "food", "hk/cpi/hk_cpi.csv", {"index_type": "composite", "basis": "headline", "series": "coicop_01"}, "yoy", PUB, "Food and non-alcoholic beverages (COICOP 01)"),
    ("HK", "energy", "hk/cpi/hk_cpi.csv", {"index_type": "composite", "basis": "headline", "series": "energy"}, "yoy", CALC, "Energy: electricity, towngas, LPG and other fuel, motor fuel groups at published weights, chained each April"),
    ("HK", "official_core", "hk/cpi/hk_cpi.csv", {"index_type": "composite", "basis": "underlying", "series": "all"}, "yoy", PUB, "Underlying Composite CPI"),
    # China (NBS food excludes beverages: not COICOP 01, so no food column)
    ("CN", "cpi", "cn/cpi/cn_cpi.csv", {"area": "national", "series": "all", "measure": "yoy"}, "pct", PUB, "CPI"),
    ("CN", "official_core", "cn/cpi/cn_cpi.csv", {"area": "national", "series": "core", "measure": "yoy"}, "pct", PUB, "CPI excluding food and energy"),
    ("CN", "ppi", "cn/ppi/cn_ppi.csv", {"area": "national", "series": "ppi", "measure": "yoy"}, "pct", PUB, "PPI (ex-factory prices)"),
    # India
    ("IN", "cpi", "in/cpi/in_cpi.csv", {"series": "combined"}, "yoy_published", PUB, "CPI, combined"),
    ("IN", "food", "in/cpi_core/in_cpi_food_energy.csv", {"series": "food_bev"}, "yoy", CALC, "Food and beverages (division 01)"),
    ("IN", "energy", "in/cpi_core/in_cpi_food_energy.csv", {"series": "energy"}, "yoy", CALC, "Energy"),
    ("IN", "core", "in/cpi_core/in_cpi_core.csv", {"series": "core1"}, "yoy", CALC, "Core 1 (excl. food and fuel)"),
    ("IN", "ppi", "in/ppi/in_ppi_spliced.csv", {}, "yoy", CALC, "Output PPI, linked to WPI"),
    # Indonesia (BPS food group includes tobacco: no food column)
    # CPI from SEKI (BPS figures republished by Bank Indonesia, y/y from 1967); the BPS WebAPI file
    # has y/y only from Oct 2022 and is identical where both exist
    ("ID", "cpi", "id/cpi/id_cpi.csv", {"series": "all"}, "yoy", PUB, "CPI, all items (BPS, via Bank Indonesia SEKI)"),
    ("ID", "energy", "id/cpi_bps/id_cpi_bps.csv", {"series": "energy"}, "yoy", PUB, "Energy"),
    ("ID", "official_core", "id/cpi_bps/id_cpi_bps.csv", {"series": "core"}, "yoy", PUB, "Core"),
    ("ID", "ppi", "id/ppi/id_ppi.csv", {"series": "wpi"}, "yoy", PUB, "WPI, general"),
    # Thailand (TPSO food includes prepared food: no food or core column)
    ("TH", "cpi", "th/cpi/th_cpi.csv", {"area": "national", "series": "all"}, "yoy", PUB, "All items"),
    ("TH", "energy", "th/cpi/th_cpi.csv", {"area": "national", "code": "92000"}, "yoy", PUB, "Energy"),
    ("TH", "official_core", "th/cpi/th_cpi.csv", {"area": "national", "code": "93000"}, "yoy", PUB, "Core (excl. fresh food and energy)"),
    ("TH", "ppi", "th/ppi/th_ppi.csv", {"series": "ppi"}, "yoy", PUB, "PPI, all items"),
    # Malaysia
    ("MY", "cpi", "my/cpi/my_cpi.csv", {"series": "overall"}, "yoy", PUB, "CPI, all items"),
    ("MY", "food", "my/cpi/my_cpi.csv", {"series": "01"}, "yoy", PUB, "Food & beverages (division 01)"),
    ("MY", "official_core", "my/cpi/my_cpi.csv", {"series": "core_overall"}, "yoy", PUB, "Core"),
    ("MY", "ppi", "my/ppi/my_ppi.csv", {"series": "total"}, "yoy", PUB, "PPI, local production"),
    # Singapore
    ("SG", "cpi", "sg/cpi/sg_cpi.csv", {"area": "national", "series": "all"}, "yoy", PUB, "All items"),
    ("SG", "food", "sg/cpi/sg_cpi.csv", {"area": "national", "series": "food_ex_fbss"}, "yoy", PUB, "Food excl. food and beverage serving services"),
    ("SG", "energy", "sg/cpi/sg_cpi.csv", {"area": "national", "series": "fuel"}, "yoy", CALC, "Fuel (electricity, gas, petrol, other fuels)"),
    ("SG", "core", "sg/cpi/sg_cpi.csv", {"area": "national", "series": "ex_food_energy"}, "yoy", CALC, "CPI less food (excl. serving services) and energy"),
    ("SG", "official_core", "sg/cpi/sg_cpi.csv", {"area": "national", "series": "core"}, "yoy", PUB, "MAS core"),
    ("SG", "ppi", "sg/ppi/sg_ppi.csv", {"series": "ppi"}, "yoy", CALC, "Manufactured products price index"),
    # Philippines
    ("PH", "cpi", "ph/cpi/ph_cpi.csv", {"area": "national", "series": "all"}, "yoy", PUB, "All items"),
    ("PH", "food", "ph/cpi/ph_cpi.csv", {"area": "national", "series": "d01"}, "yoy", PUB, "Food and non-alcoholic beverages"),
    ("PH", "official_core", "ph/cpi/ph_cpi.csv", {"area": "national", "series": "core"}, "yoy", PUB, "Core (PSA definition)"),
    ("PH", "ppi", "ph/ppi/ph_ppi.csv", {"series": "manufacturing"}, "yoy", PUB, "PPI, manufacturing"),
    # Vietnam
    ("VN", "cpi", "vn/cpi/vn_cpi.csv", {"area": "national", "series": "all", "comparison_base": "yoy"}, "rate", PUB, "All items"),
    ("VN", "official_core", "vn/cpi/vn_cpi.csv", {"area": "national", "series": "core", "comparison_base": "yoy"}, "rate", PUB, "Core inflation (NSO)"),
]

COLUMNS = ["economy", "name", "column", "label", "date", "value", "basis", "file"]


def _rows(econ, col, rel, filt, vcol, basis, label):
    path = DATA / rel
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if any(r.get(k) != v for k, v in filt.items()):
                continue
            d, v = r.get("date", ""), r.get(vcol, "")
            if d < START or v in ("", None):
                continue
            out[d] = round(float(v), 2)
    return [{"economy": econ, "name": NAMES[econ], "column": col, "label": label, "date": d,
             "value": out[d], "basis": basis, "file": f"data/{rel}"} for d in sorted(out)]


def build():
    """Write the Asia table. Returns {"updated", "code", "summary", "warnings"}."""
    rows, warnings, missing, inputs = [], [], [], {}
    for econ, col, rel, filt, vcol, basis, label in SPEC:
        path = DATA / rel
        if not path.exists():
            missing.append(f"{econ} {col}")
            continue
        got = _rows(econ, col, rel, filt, vcol, basis, label)
        if not got:
            warnings.append(f"{econ} {col}: no values found in data/{rel}")
            continue
        rows += got
        rr = read_json(path.parent / "release_row.json", [{}]) or [{}]
        inputs[f"data/{rel}"] = rr[0].get("code", "")
    content = "".join(f"{r['economy']}{r['column']}{r['date']}{r['value']}" for r in rows)
    code = "A" + hashlib.sha1(content.encode()).hexdigest()[:10]
    old = read_json(OUT / "release_row.json", [{}]) or [{}]
    if old and old[0].get("code") == code:
        return {"updated": False, "code": code, "summary": "Asia table unchanged", "warnings": warnings}
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "asia_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    have = sorted({r["economy"] for r in rows}, key=ECONOMIES.index)
    latest = {e: max(r["date"] for r in rows if r["economy"] == e and r["column"] == "cpi")
              for e in have if any(r["economy"] == e and r["column"] == "cpi" for r in rows)}
    release = {"code": code, "label": "Asia table", "economies": " ".join(have),
               "latest_cpi_month": max(latest.values()) if latest else ""}
    write_release(OUT, release, warnings, len(rows),
                  extra={"missing": missing, "inputs": inputs, "latest_cpi": latest})
    return {"updated": True, "code": code, "warnings": warnings,
            "summary": f"{len(rows)} rows, {len(have)} economies ({' '.join(have)}); not on this branch: {len({m.split()[0] for m in missing})}"}
