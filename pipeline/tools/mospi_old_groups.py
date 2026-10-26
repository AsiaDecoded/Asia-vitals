"""Download every group and subgroup index on MoSPI's older CPI bases (all-India; rural, urban, combined)
and rebuild raw/in/cpi_core/core2012_inputs.json (adds the CFPI).

  python -I pipeline/tools/mospi_old_groups.py <out dir>

Saves <out>/groups2012_<year>.json.gz (2012-2025) and <out>/groups2010_<year>.json.gz (2011-2014), one
file per year so a failure keeps what was fetched, and <out>/core2012_inputs.json.
"""
import gzip
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import mospi  # noqa: E402
from tools.mospi_core2012_inputs import GROUPS, ITEMS  # noqa: E402

ITEMS_FILE = Path(__file__).resolve().parents[2] / "raw" / "in" / "cpi_old" / "items2012.json.gz"


def pull(base, year, out):
    f = out / f"groups{base}_{year}.json.gz"
    for attempt in range(3):
        try:
            rows, total = mospi.paged("/api/cpi/getCPIIndex", {"base_year": base, "series": "Current", "year": str(year),
                                                                "state_code": "99"}, max_pages=80)
            f.write_bytes(gzip.compress(json.dumps(rows).encode()))
            print(base, year, len(rows), total, flush=True)
            return rows
        except Exception:  # noqa: BLE001
            print(f"{base} {year} attempt {attempt + 1} failed:\n{traceback.format_exc()}", flush=True)
    return []


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    series = {k: {} for k in list(GROUPS.values()) + list(ITEMS.values())}
    for y in range(2012, 2026):
        for r in pull("2012", y, out):
            if y >= 2014 and r.get("sector") == "Combined" and r.get("subgroup") in GROUPS and r.get("index") not in (None, ""):
                series[GROUPS[r["subgroup"]]][f"{y}-{mospi.month_number(r['month']):02d}"] = float(r["index"])
    for y in range(2011, 2015):
        pull("2010", y, out)
    for r in json.loads(gzip.decompress(ITEMS_FILE.read_bytes())):
        if r.get("item") in ITEMS and r.get("index") not in (None, "") and r["year"] >= 2014:
            series[ITEMS[r["item"]]][f"{r['year']}-{mospi.month_number(r['month']):02d}"] = float(r["index"])
    print({k: len(v) for k, v in series.items()}, flush=True)
    (out / "core2012_inputs.json").write_text(json.dumps({"source": "MoSPI API, CPI base 2012=100, all-India combined",
                                                          "series": series}, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
