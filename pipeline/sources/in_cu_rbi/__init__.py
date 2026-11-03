"""India manufacturing capacity utilisation, RBI OBICUS (Order Books, Inventories and Capacity Utilisation Survey),
quarterly, as published (non-seasonally adjusted; RBI's seasonally adjusted figure kept alongside, not shown).

RBI's servers cannot be reached by the pipeline (rbidocs.rbi.org.in serves a bot challenge; DBIE needs an encrypted
browser session), so this source reads the RBI's OBICUS workbook placed by hand in raw/in/obicus/ (the newest
OBICUS*.xlsx, e.g. OBICUS07102026.xlsx from the release of 7 Oct 2026, sheet "Capacity Utilisation", Table 1).
Add the new workbook after each quarterly release (about two quarters' lag) and rerun.

Quarters are RBI's fiscal quarters (Q1:2026-27 = Apr-Jun 2026), dated at their first month. Values rounded to one
decimal, as RBI publishes (one cell in the workbook carries extra digits). Needs openpyxl.
"""
import csv
import hashlib
import json
import re

from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "in_cu_rbi"
DESCRIPTION = "India manufacturing capacity utilisation, RBI OBICUS, quarterly, as published (from the RBI workbook in raw/in/obicus)"
OUT = DATA / "in" / "cu"
SRC = RAW / "in" / "obicus"


def latest_book():
    books = sorted(SRC.glob("OBICUS*.xlsx"), key=lambda p: (p.stem[-4:], p.stem[-6:-4], p.stem[-8:-6]))
    if not books:
        raise CheckFailed([f"no OBICUS*.xlsx in {SRC}"])
    return books[-1]


def read(path):
    import openpyxl
    ws = openpyxl.load_workbook(path, data_only=True, read_only=True)["Capacity Utilisation"]
    rows = []
    for r in ws.iter_rows(values_only=True):
        if len(r) < 5 or not isinstance(r[1], str):
            continue
        m = re.match(r"Q([1-4]):(\d{4})-(\d{2})$", r[1].strip())
        if not m:
            continue
        q, y = int(m.group(1)), int(m.group(2))
        mon = 4 + 3 * (q - 1)
        yr = y + (1 if mon > 12 else 0)
        mon = (mon - 1) % 12 + 1
        rows.append({"date": f"{yr}-{mon:02d}-01", "quarter": r[1].strip(), "round": r[0], "respondents": r[2],
                     "cu": round(float(r[3]), 1), "cu_sa": round(float(r[4]), 1) if r[4] is not None else None})
    return rows


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    book = latest_book()
    rows = read(book)
    errors = []
    ds = [r["date"] for r in rows]
    if not rows or ds[0] > "2008-04-01" or ds != sorted(set(ds)):
        errors.append(f"OBICUS: {len(rows)} quarters from {ds[:1]}; duplicates or out of order")
    for a, b in zip(ds, ds[1:]):
        y, m = int(a[:4]), int(a[5:7]); y, m = (y + 1, 1) if m == 10 else (y, m + 3)
        if b != f"{y}-{m:02d}-01":
            errors.append(f"OBICUS: gap between {a} and {b}")
    for r in rows:
        if not 30 < r["cu"] < 100:
            errors.append(f"OBICUS {r['quarter']}: CU {r['cu']} out of range")
    if errors:
        raise CheckFailed(errors)
    fp = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change ({state.get('label')})"}
    with open(OUT / "in_cu.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) + ["source"], lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "source": f"RBI, OBICUS ({book.name})"})
    last = rows[-1]
    code = last['quarter']
    label = f"{last['quarter']}: capacity utilisation {last['cu']}% (SA {last['cu_sa']}%), {book.name}"
    nlong = write_long(({"country": "IN", "indicator": "cu", "series": "obicus_cu", "label": "Capacity utilisation, manufacturing (RBI OBICUS)",
                         "measure": "level", "area": "national", "freq": "Q", "date": r["date"], "value": r["cu"], "unit": "%",
                         "source": "RBI, OBICUS", "release": code} for r in rows), OUT / "long.csv")
    write_release(OUT, {"code": code, "label": label, "latest_quarter": last["quarter"], "book": book.name}, [], len(rows),
                  {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": label}
