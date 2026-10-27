"""Probe SingStat's Table Builder API for Singapore price tables.

  python -I pipeline/tools/singstat_discover.py OUTDIR

Round 2: full data (all rows, all periods) of the tables the Singapore CPI source needs, gzipped,
plus keyword searches for CPI weights.
"""
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import singstat  # noqa: E402

TABLES = ["M213751", "M213752", "M213781", "M213771", "M213792", "M213891", "M213431", "M213381"]
KEYWORDS = ["weights", "weighting", "CPI weight", "expenditure weights"]


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    found = {}
    for kw in KEYWORDS:
        for rec in singstat.search(kw):
            found[rec.get("id")] = rec.get("title")
    (out / "weights_search.json").write_text(json.dumps(found, indent=1, ensure_ascii=False))
    for t in TABLES:
        try:
            d = singstat.table(t)
            with gzip.open(out / f"{t}.json.gz", "wt", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            print(t, len(d["rows"]), "rows")
        except Exception as e:  # noqa: BLE001
            (out / f"{t}.error.txt").write_text(repr(e))
            print(t, "ERROR", e)


if __name__ == "__main__":
    main(sys.argv[1])
