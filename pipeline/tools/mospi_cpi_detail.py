"""Download every 2024-base CPI row (all levels, divisions to items) for all-India, one sector per file.

  python -I pipeline/tools/mospi_cpi_detail.py <out dir> [combined|rural|urban ...]

Saves <out>/cpi2024_<sector>.json.gz: all rows for Jan 2025 to the latest month.
"""
import datetime as dt
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import mospi  # noqa: E402

SECTORS = {"rural": 1, "urban": 2, "combined": 3}


def main(out, *names):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    years = list(range(2025, dt.date.today().year + 1))
    for name in names or SECTORS:
        rows, total = mospi.cpi("Current", years=years, max_pages=1000, state_code=1, sector_code=SECTORS[name])
        (out / f"cpi2024_{name}.json.gz").write_bytes(gzip.compress(json.dumps(rows).encode()))
        print(name, len(rows), total, flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
