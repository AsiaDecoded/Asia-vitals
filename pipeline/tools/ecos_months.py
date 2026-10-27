"""Fetch every item of one ECOS table month by month for a range, into a partial store file.

  python -I pipeline/tools/ecos_months.py TABLE FROM_YM TO_YM OUTFILE
  python -I pipeline/tools/ecos_months.py series TABLE:ITEM:FROM_YM[,...] OUTFILE   # item by item
"""
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import ecos  # noqa: E402


def series(spec, out):
    store = {"_items": {}}
    for part in spec.split(","):
        table, item, a = part.split(":")
        if table not in store["_items"]:
            try:
                its = ecos.items(table)
                store["_items"][table] = [{k: r.get(k) for k in ("ITEM_CODE", "ITEM_NAME", "P_ITEM_CODE", "GRP_CODE", "START_TIME", "UNIT_NAME", "WEIGHT")}
                                          for r in its if r.get("CYCLE") == "M"]
            except Exception as e:  # noqa: BLE001
                print("items FAILED", table, e, flush=True)
        try:
            n = ecos.put(store, table, ecos.series(table, item, a, "202612"))
            print(table, item, n, flush=True)
        except Exception as e:  # noqa: BLE001
            print("FAILED", table, item, e, flush=True)
    with gzip.open(out, "wt") as f:
        json.dump(store, f, ensure_ascii=False)


def main(table, a, b=None, out=None):
    if table == "series":
        return series(a, b)
    store = {}
    y, m = int(a[:4]), int(a[4:])
    while f"{y}{m:02d}" <= b:
        ym = f"{y}{m:02d}"
        try:
            rows = ecos.month_all(table, ym)
            ecos.put(store, table, rows)
            print(ym, len(rows), flush=True)
        except Exception as e:  # noqa: BLE001
            print("FAILED", ym, e, flush=True)
        m += 1
        if m > 12:
            y, m = y + 1, 1
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt") as f:
        json.dump(store, f, ensure_ascii=False)


if __name__ == "__main__":
    main(*sys.argv[1:])
