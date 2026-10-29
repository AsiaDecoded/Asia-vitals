"""Rebuild the Asia table (data/asia/table/) from the country outputs on this branch.

  python -I pipeline/tools/asia_table.py

run.py does this automatically after any source updates. Nothing is fetched or calculated:
see pipeline/core/asia.py for which series fill each column.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.asia import build  # noqa: E402

if __name__ == "__main__":
    res = build()
    print(("UPDATED" if res["updated"] else "unchanged") + ": " + res["summary"])
    for w in res["warnings"]:
        print("WARNING:", w)
