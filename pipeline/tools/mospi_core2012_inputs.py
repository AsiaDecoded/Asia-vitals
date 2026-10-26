"""Build the fixed inputs for 2012-base core CPI (all-India, combined), Jan 2014 to Dec 2025, from MoSPI's API.

  python -I pipeline/tools/mospi_core2012_inputs.py raw/in/cpi_core/core2012_inputs.json

General index, Food and beverages and Fuel and light groups (getCPIIndex, base 2012, sector Combined) and the
items Petrol for Vehicle, Diesel for Vehicle, Gold and Silver (getItemIndex, base 2012). The 2012 base ended in
Dec 2025, so this file is built once.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import mospi  # noqa: E402

GROUPS = {"General-Overall": "general", "Food and Beverages-Overall": "food_bev", "Fuel and Light-Overall": "fuel_light"}
ITEMS = {"Petrol for Vehicle": "petrol", "Diesel for Vehicle": "diesel", "Gold": "gold", "Silver": "silver"}


def main(out):
    series = {k: {} for k in list(GROUPS.values()) + list(ITEMS.values())}
    for y in range(2014, 2026):
        rows, _ = mospi.paged("/api/cpi/getCPIIndex", {"base_year": "2012", "series": "Current", "year": str(y), "state_code": "99"}, max_pages=50)
        for r in rows:
            if r.get("sector") == "Combined" and r.get("subgroup") in GROUPS and r.get("index") not in (None, ""):
                series[GROUPS[r["subgroup"]]][f"{y}-{mospi.month_number(r['month']):02d}"] = float(r["index"])
        rows, _ = mospi.paged("/api/cpi/getItemIndex", {"base_year": "2012", "year": str(y)}, max_pages=50)
        for r in rows:
            if r.get("item") in ITEMS and r.get("index") not in (None, ""):
                series[ITEMS[r["item"]]][f"{y}-{mospi.month_number(r['month']):02d}"] = float(r["index"])
        print(y, {k: len(v) for k, v in series.items()}, flush=True)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({"source": "MoSPI API, CPI base 2012=100, all-India combined",
                                     "series": series}, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
