"""Indonesia stock market: Jakarta Composite Index (IHSG), end of month, points, as republished by Bank Indonesia in
SEKI table III.3 (Transaksi dan Indeks Harga Saham di Bursa Efek Indonesia), from July 1995. Asked for 1 Nov 2026
(Financial tab). The IDX's own site blocks automated access; the IMF's equity index for Indonesia (2010 = 100) starts
in the same month and is not used.

The workbook has three sheets (1990-2003, 2004-2009 extended, current from 2010); each has a year row and a month row
over the columns and an "IHSG" row. Later sheets win where they overlap. Months with 0 or "-" are blank. SEKI III.3 has no months between Dec 2003 and Jan 2006 other than Dec 2004 and Dec 2005;
those months are left out (warning), not filled.
"""
import csv
import hashlib
import json
import re

from core import seki
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "id_jci_seki"
DESCRIPTION = "Indonesia Jakarta Composite Index, end of month, SEKI III.3"
OUT = DATA / "id" / "jci"
RAWDIR = RAW / "id" / "jci_seki"
SOURCE = "Bank Indonesia SEKI table III.3 (Indonesia Stock Exchange data)"
MON = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "mei": 5, "jun": 6, "jul": 7, "aug": 8, "agu": 8, "ags": 8,
       "sep": 9, "oct": 10, "okt": 10, "nov": 11, "dec": 12, "des": 12}


def read_sheet(sh):
    """{YYYY-MM: points} from one sheet: find the IHSG row and the year/month header rows above the data."""
    row = next((r for r in range(sh.nrows) if any(str(sh.cell_value(r, c)).strip().upper().startswith("IHSG") for c in range(min(4, sh.ncols)))), None)
    if row is None:
        return {}
    mrow = next((r for r in range(min(15, sh.nrows)) if sum(str(sh.cell_value(r, c)).strip()[:3].lower() in MON for c in range(sh.ncols)) >= 6), None)
    if mrow is None or mrow == 0:
        return {}
    # The year label sits at the start of a year's run of months in older sheets and at its end in the current one, so
    # split the month columns into runs (a new run when the month does not increase) and give each run the year label
    # found inside it.
    runs, cur, last = [], [], 0
    for c in range(2, sh.ncols):
        m = str(sh.cell_value(mrow, c)).strip().rstrip("*").lower()[:3]
        if m not in MON:
            continue
        if MON[m] <= last:
            runs.append(cur)
            cur = []
        cur.append((c, MON[m]))
        last = MON[m]
    runs.append(cur)
    out = {}
    for run in runs:
        ys = set()
        for c, _ in run:
            yv = sh.cell_value(mrow - 1, c)
            if isinstance(yv, float) and 1980 < yv < 2100:
                ys.add(int(yv))
            elif isinstance(yv, str) and re.fullmatch(r"(19|20)\d\d", yv.strip()):
                ys.add(int(yv.strip()))
        if len(ys) != 1:
            continue
        y = ys.pop()
        for c, m in run:
            v = sh.cell_value(row, c)
            if isinstance(v, float) and v > 0:
                out[f"{y}-{m:02d}"] = v
    return out


def update(force=False, **_):
    import xlrd  # noqa: PLC0415
    OUT.mkdir(parents=True, exist_ok=True)
    RAWDIR.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    b, lm = seki.download("3_3")
    wb = xlrd.open_workbook(file_contents=b)
    s = {}
    for i in range(wb.nsheets):
        s.update(read_sheet(wb.sheet_by_index(i)))   # later sheets win
    ms = sorted(s)
    errors, warnings = [], []
    if not ms or ms[0] > "1996-01":
        errors.append(f"series starts {ms[:1]}")
    want = []
    if ms:
        y, m = int(ms[0][:4]), int(ms[0][5:])
        while f"{y}-{m:02d}" <= ms[-1]:
            want.append(f"{y}-{m:02d}")
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    gaps = [k for k in want if k not in s]
    if [g for g in gaps if g >= "2006-01"]:
        errors.append(f"months missing: {[g for g in gaps if g >= '2006-01'][:6]}")
    if gaps:   # SEKI III.3 shows only Dec 2004 and Dec 2005 between Dec 2003 and Jan 2006
        warnings.append(f"{len(gaps)} months not in SEKI III.3: {gaps[0]}..{gaps[-1]}")
    if not (200 < s.get("1998-09", 0) < 400):
        errors.append(f"Sep 1998 value {s.get('1998-09')} outside 200-400 (layout?)")
    jumps = [b2 for a, b2 in zip(ms, ms[1:]) if not 0.6 < s[b2] / s[a] < 1.6]
    if jumps:
        warnings.append(f"monthly moves beyond -40%/+60%: {jumps[:5]}")
    if state.get("latest_month") and ms and ms[-1] < state["latest_month"]:
        errors.append(f"latest month {ms[-1]} before the stored {state['latest_month']}")
    if errors:
        raise CheckFailed(errors)
    fp = hashlib.sha256(json.dumps(s, sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    (RAWDIR / "TABEL3_3.xls").write_bytes(b)
    with open(OUT / "id_jci.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["date", "jci"])
        for k in ms:
            w.writerow([f"{k}-01", round(s[k], 2)])
    code = f"J{ms[-1]}"
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    label = f"JCI to {names[int(ms[-1][5:]) - 1]} {ms[-1][:4]} (SEKI III.3)"
    nlong = write_long(({"country": "ID", "indicator": "jci", "series": "ihsg", "label": "Jakarta Composite Index, end of month",
                         "measure": "level", "area": "", "freq": "M", "date": f"{k}-01", "value": round(s[k], 2), "unit": "index points",
                         "source": SOURCE, "release": code} for k in ms), OUT / "long.csv")
    write_release(OUT, {"code": code, "label": label, "latest_month": ms[-1], "last_modified": lm, "table": "SEKI III.3"},
                  warnings, len(ms), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{ms[0]}..{ms[-1]}; latest {s[ms[-1]]:,.2f}", "warnings": warnings}
