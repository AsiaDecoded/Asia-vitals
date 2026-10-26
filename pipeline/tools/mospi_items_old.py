"""Download every item index on MoSPI's older CPI bases (all-India): 2010 base (2011-2014) and 2012 base (2014-2025).

  python -I pipeline/tools/mospi_items_old.py <out dir>

Saves <out>/items2010.json.gz and <out>/items2012.json.gz (all rows, as returned), one year per request.
"""
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import mospi  # noqa: E402

PLAN = {"2010": range(2011, 2015), "2012": range(2014, 2026)}


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for base, years in PLAN.items():
        rows = []
        for y in years:
            part, total = mospi.paged("/api/cpi/getItemIndex", {"base_year": base, "year": str(y)}, max_pages=200)
            print(base, y, len(part), total, flush=True)
            rows.extend(part)
        (out / f"items{base}.json.gz").write_bytes(gzip.compress(json.dumps(rows).encode()))
        print(base, "total", len(rows), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
