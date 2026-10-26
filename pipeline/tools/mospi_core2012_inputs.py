"""Build the fixed inputs for 2012-base core CPI (all-India, combined), Jan 2014 to Dec 2025, from MoSPI's API.

  python -I pipeline/tools/mospi_core2012_inputs.py raw/in/cpi_core/core2012_inputs.json

General index, Food and beverages, Fuel and light and Consumer Food Price (CFPI) groups (getCPIIndex, base 2012, sector Combined) and the
items Petrol for Vehicle, Diesel for Vehicle, Gold and Silver (getItemIndex, base 2012). The 2012 base ended in
Dec 2025, so this file is built once. Also saves every 2012-base group and subgroup index (all-India, rural,
urban and combined, 2012-2025) as groups2012.json.gz, and the 2010-base ones (2011-2014)
as groups2010.json.gz, next to it.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import mospi  # noqa: E402

GROUPS = {"General-Overall": "general", "Food and Beverages-Overall": "food_bev", "Fuel and Light-Overall": "fuel_light",
          "Consumer Food Price-Overall": "food"}
ITEMS = {"Petrol for Vehicle": "petrol", "Diesel for Vehicle": "diesel", "Gold": "gold", "Silver": "silver"}


def main(out):
    series = {k: {} for k in list(GROUPS.values()) + list(ITEMS.values())}
    allgroups = []  # every group and subgroup index, all sectors, 2012-2025, saved alongside
    for y in range(2012, 2026):
        rows, _ = mospi.paged("/api/cpi/getCPIIndex", {"base_year": "2012", "series": "Current", "year": str(y), "state_code": "99"}, max_pages=50)
        allgroups.extend(rows)
        for r in rows:
            if y >= 2014 and r.get("sector") == "Combined" and r.get("subgroup") in GROUPS and r.get("index") not in (None, ""):
                series[GROUPS[r["subgroup"]]][f"{y}-{mospi.month_number(r['month']):02d}"] = float(r["index"])
        if y < 2014:
            continue
        rows, _ = mospi.paged("/api/cpi/getItemIndex", {"base_year": "2012", "year": str(y)}, max_pages=50)
        for r in rows:
            if r.get("item") in ITEMS and r.get("index") not in (None, ""):
                series[ITEMS[r["item"]]][f"{y}-{mospi.month_number(r['month']):02d}"] = float(r["index"])
        print(y, {k: len(v) for k, v in series.items()}, flush=True)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    import gzip
    (Path(out).parent / "groups2012.json.gz").write_bytes(gzip.compress(json.dumps(allgroups).encode()))
    old = []
    for y in range(2011, 2015):
        rows, _ = mospi.paged("/api/cpi/getCPIIndex", {"base_year": "2010", "series": "Current", "year": str(y), "state_code": "99"}, max_pages=50)
        old.extend(rows)
    (Path(out).parent / "groups2010.json.gz").write_bytes(gzip.compress(json.dumps(old).encode()))
    Path(out).write_text(json.dumps({"source": "MoSPI API, CPI base 2012=100, all-India combined",
                                     "series": series}, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
