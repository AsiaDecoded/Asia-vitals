"""Probe the Philippine Statistics Authority's OpenSTAT (PXWeb) API for price tables.

  python -I pipeline/tools/psa_discover.py OUTDIR

Round 2: data of the CPI, core CPI, seasonally adjusted CPI, bottom-30% CPI and manufacturing PPI tables
the Philippines inflation source needs (national, NCR/AONCR and regions), as tidy rows, gzipped.
"""
import gzip
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import psa  # noqa: E402

C = "2M/PI/CPI/2018NEW/"
REGIONS = lambda t: not t.startswith("....")  # PH, NCR, AONCR and the 17 regions  # noqa: E731
LEVEL = lambda n: (lambda t: len(t.split(" - ")[0].split(".")) <= n)  # noqa: E731
JOBS = [
    ("cpi_index_ph", C + "0012M4ACP22.px", {"Geolocation": ["PHILIPPINES"]}),
    ("cpi_yoy_ph", C + "0012M4ACP23.px", {"Geolocation": ["PHILIPPINES"]}),
    ("cpi_index_reg", C + "0012M4ACP22.px", {"Geolocation": REGIONS, "Commodity Description": LEVEL(1)}),
    ("cpi_yoy_reg", C + "0012M4ACP23.px", {"Geolocation": REGIONS, "Commodity Description": LEVEL(1)}),
    ("cpi_weights", C + "0012M4ACP25.px", {"Geolocation": REGIONS}),
    ("cpi_index_1957", C + "0012M4ACP26.px", {"Geolocation": ["PHILIPPINES"]}),
    ("cpi_yoy_1958", C + "0012M4ACP27.px", {"Geolocation": ["PHILIPPINES"]}),
    ("cpi_index_back", C + "0012M4ACP28.px", {"Geolocation": ["PHILIPPINES", "National Capital Region (NCR)", "Areas Outside National Capital Region (AONCR)"], "Commodity Description": LEVEL(2)}),
    ("cpi_yoy_back", C + "0012M4ACP29.px", {"Geolocation": REGIONS, "Commodity Description": LEVEL(1)}),
    ("core_index", C + "0012M4ACP30.px", {}),
    ("core_yoy", C + "0012M4ACP31.px", {}),
    ("core_weights", C + "0012M4ACP32.px", {}),
    ("core_index_back", C + "0012M4ACP33.px", {}),
    ("core_yoy_back", C + "0012M4ACP34.px", {}),
    ("sa_index", "2M/PI/SACPI/0012M4ASAC1.px", {}),
    ("sa_mom", "2M/PI/SACPI/0012M4ASAC2.px", {}),
    ("sa_mom_0022", "2M/PI/SACPI/0022M4ASAC2.px", {}),
    ("b30_index", "2M/PI/BIH/2018NEW/0022M4ABIR1.px", {"Geolocation": ["PHILIPPINES", "NCR", "AONCR"], "Commodity Description": LEVEL(2)}),
    ("b30_yoy", "2M/PI/BIH/2018NEW/0022M4ABIR2.px", {"Geolocation": ["PHILIPPINES", "NCR", "AONCR"], "Commodity Description": LEVEL(2)}),
    ("b30_weights", "2M/PI/BIH/2018NEW/0022M4ABIR3.px", {"Geolocation": ["PHILIPPINES"]}),
    ("ppim", "2M/PI/PPI/PPIM/0012M4CPPI2.px", {}),
    ("ppim_back", "2M/PI/PPI/PPIM/0022M4CPPI1.px", {}),
    ("ppia", "2M/PI/PPI/PPIA/0062M4APPI1.px", {}),
]


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for name, path, sel in JOBS:
        try:
            rows = psa.get(path, sel)
            with gzip.open(out / f"{name}.json.gz", "wt", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False)
            summary[name] = {"path": path, "rows": len(rows), "nonnull": sum(r["value"] is not None for r in rows),
                             "sample": rows[:2]}
            print(name, len(rows))
        except Exception as e:  # noqa: BLE001
            summary[name] = {"path": path, "error": repr(e)[:500]}
            print(name, "ERROR", e)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
