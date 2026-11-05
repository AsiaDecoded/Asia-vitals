"""Probe (5 Nov 2026): all manufacturing divisions for Korea (ECOS 901Y032, original) and all rows of Singapore's
M355381, to test whether manufacturing is a fixed combination of its parts (implied weights for non-electronics).

  python -I pipeline/tools/nonelec_probe.py discovery/nonelec
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, "pipeline")
from core import ecos, singstat  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "discovery/nonelec")
OUT.mkdir(parents=True, exist_ok=True)
items = json.loads(Path("items.json").read_text()) if Path("items.json").exists() else None
codes = ["I11AC"] + [f"I11AC{c}" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
with open(OUT / "kr_901Y032.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["code", "name", "time", "value"])
    for c in codes:
        try:
            rs = ecos._paged("StatisticSearch", ["901Y032", "M", "201501", "203012", c, "1"])
        except Exception as e:  # noqa: BLE001
            print(c, "failed", e)
            continue
        for r in rs:
            w.writerow([c, r.get("ITEM_NAME1"), r.get("TIME"), r.get("DATA_VALUE")])
        print(c, len(rs), rs[0].get("ITEM_NAME1") if rs else "")
with open(OUT / "kr_200Y105.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["code", "name", "time", "value"])
    for c in ["1103"] + [f"1103{i:02d}" for i in range(1, 14)]:
        for r in ecos._paged("StatisticSearch", ["200Y105", "A", "2010", "2030", c]):
            w.writerow([c, r.get("ITEM_NAME1"), r.get("TIME"), r.get("DATA_VALUE")])
        print(c, "NA ok")
t = singstat.table("M355381")
with open(OUT / "sg_M355381.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["series", "row", "key", "value"])
    for r in t["rows"]:
        for c in r["columns"]:
            w.writerow([r.get("seriesNo"), (r.get("rowText") or "").strip(), c["key"], c["value"]])
print("sg rows", len(t["rows"]), [((r.get("seriesNo"), r.get("rowText"))) for r in t["rows"]])
