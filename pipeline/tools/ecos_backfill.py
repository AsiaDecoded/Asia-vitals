"""One-off: build the ECOS series store for Korea (raw/kr/ecos/store.json.gz).

  python -I pipeline/tools/ecos_backfill.py [START_YM]   # items of 901Y009 month by month from START_YM (default 201501)

Long history for headline and aggregates is fetched item by item; all CPI items month by month.
With the public sample key (10 rows per call) this takes about an hour; resumable (skips months
already complete in the store).
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import ecos  # noqa: E402

END = time.strftime("%Y%m")
LONG = {
    # table: [(item, start)]
    "901Y009": [("0", "196501")] + [(c, "198501") for c in "ABCDEFGHIJKL"],
    "901Y010": [(c, "198501") for c in ["00", "21", "211", "2111", "2112", "2113", "212", "2121", "2122", "2123",
                                         "2124", "2125", "2126", "2127", "2129", "213", "22", "221", "222", "223",
                                         "2231", "2239"]]
               + [(c, "199001") for c in ["10", "11", "12", "13", "20", "QB", "DB"]] + [("110", "199501")],
    "404Y014": [("*AA", "196501"), ("1AA", "196501"), ("2AA", "196501"), ("3AA", "196501"), ("4AA", "196501"), ("5AA", "196501")],
    "401Y015": [("*AA", "197101")],
    "402Y014": [("*AA", "197101")],
}


def main(start_ym="201501"):
    store = ecos.load_store()
    meta = {}
    for table in ["901Y009", "901Y010", "404Y014", "401Y015", "402Y014"]:
        try:
            its = ecos.items(table)
            meta[table] = {r["ITEM_CODE"]: r for r in its if r.get("CYCLE") == "M"}
            store.setdefault("_items", {})[table] = [
                {k: r.get(k) for k in ("ITEM_CODE", "ITEM_NAME", "P_ITEM_CODE", "GRP_NAME", "START_TIME", "END_TIME", "UNIT_NAME", "WEIGHT")}
                for r in its if r.get("CYCLE") == "M"]
            print(table, "items", len(meta[table]), flush=True)
        except Exception as e:  # noqa: BLE001
            print("items failed", table, e, flush=True)
            meta[table] = {}
    for table, lst in LONG.items():
        for item, st in lst:
            try:
                n = ecos.put(store, table, ecos.series(table, item, st, END), meta.get(table))
                print(table, item, n, "calls", ecos.CALLS["n"], flush=True)
            except Exception as e:  # noqa: BLE001
                print("FAILED", table, item, e, flush=True)
        ecos.save_store(store)
    # every CPI item, month by month
    y, m = int(start_ym[:4]), int(start_ym[4:])
    nitems = len(meta.get("901Y009") or {}) or 400
    while f"{y}{m:02d}" <= END:
        ym = f"{y}{m:02d}"
        have = sum(1 for s in store.get("901Y009", {}).values() if ym in s["values"])
        if have < nitems * 0.95:
            try:
                rows = ecos.month_all("901Y009", ym)
                n = ecos.put(store, "901Y009", rows, meta.get("901Y009"))
                print("901Y009", ym, len(rows), n, "calls", ecos.CALLS["n"], flush=True)
            except Exception as e:  # noqa: BLE001
                print("FAILED month", ym, e, flush=True)
            ecos.save_store(store)
        m += 1
        if m > 12:
            y, m = y + 1, 1
    ecos.save_store(store)
    print("done; calls", ecos.CALLS["n"])


if __name__ == "__main__":
    main(*sys.argv[1:])
