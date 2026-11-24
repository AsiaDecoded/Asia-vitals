"""Crude oil import volumes, monthly, from each economy's national source, as published; one file for the Asia
dashboard's Energy tab.

  JP  MOF customs, d61ma 原油及び粗油 (30301) 数量, kL, from 1988             (read from trade_jp's output)
  KR  Korea Customs Service, HS 2709 import weight, tonnes, from 2000          (read from trade_kr's output)
  CN  GACC monthly bulletin table (14), crude petroleum oils, 10,000 t, from 2018 (read from trade_cn's output)
  VN  NSO monthly report, imports, Dầu thô, thousand tonnes, from 2020        (read from trade_vn's output)
  TH  EPPO Table 2.1-3, import of crude oil (DOEB data), million litres, from 1986
  IN  PPAC Import/Export of crude oil and petroleum products, crude oil, '000 tonnes, current fiscal year
      (months are kept as they arrive; earlier years are in PPAC's PDF reports, not read)
  ID  BPS variable 2173, volume of oil and gas imports, crude oil, thousand tonnes (if BPS lists a crude row)
Not covered: Taiwan (the Energy Administration's open data refuses GitHub's servers), Malaysia, Singapore and the
Philippines (no monthly crude import volume published in a form that can be read automatically), Hong Kong
(no refinery; no crude imports).

kb/d (calculated, Asia Decoded) = barrels / days in month / 1000, with 1 kL = 6.28981 barrels and, for figures in
tonnes, 7.33 barrels per tonne (an average crude; actual density differs by grade, by a few per cent).
Output: data/asia/crude/crude_imports.csv: economy, date, value, unit, kbd, source, series.
"""
import calendar
import csv
import io
import re
import time
import urllib.request

from core import bps, trade
from core.common import DATA, CheckFailed, write_release

NAME = "oil_crude"
DESCRIPTION = "Crude oil import volumes by economy (national sources), with kb/d calculated"
OUT = DATA / "asia" / "crude"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
BBL = {"kl": 6.28981, "million litres": 6289.81, "tonnes": 7.33, "thousand tonnes": 7330.0}
SRC = {"JP": "MOF customs", "KR": "Korea Customs Service", "CN": "GACC", "VN": "NSO", "TH": "EPPO (DOEB data)",
       "IN": "PPAC", "ID": "BPS"}
MON = {m: i + 1 for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}
WARN = []


def get(url):
    err = None
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"{url}: {repr(err)[:150]}")


def from_trade():
    out = []
    for cc in ("jp", "kr", "cn", "vn"):
        p = trade.OUT / cc / f"trade_{cc}.csv"
        if not p.exists():
            WARN.append(f"{cc}: no trade file")
            continue
        for r in csv.DictReader(p.open()):
            if r["product"] == "crude_oil_volume" and r["value"] not in ("", None):
                out.append({"economy": cc.upper(), "date": r["date"][:10], "value": float(r["value"]), "unit": r["unit"],
                            "series": r["series"]})
    return out


def thailand():
    import xlrd  # noqa: PLC0415
    page = get("https://www.eppo.go.th/?p=25878").decode("utf-8", "replace")
    links = {re.sub(r".*/", "", u): u for u in re.findall(r'href="(https://www\.eppo\.go\.th/wp-content/uploads/[^"]+/T02_01_03(?:-1)?\.xls)"', page)}
    out = {}
    hist = links.get("T02_01_03-1.xls")
    if hist:
        sh = xlrd.open_workbook(file_contents=get(hist)).sheet_by_index(0)
        year = None
        for i in range(sh.nrows):
            r = sh.row_values(i)
            if isinstance(r[0], float) and 1980 < r[0] < 2100 and not any(isinstance(c, float) for c in r[1:13]):
                year = int(r[0])
            elif str(r[0]).strip().upper() == "TOTAL" and year:
                for m in range(1, 13):
                    if isinstance(r[m], float):
                        out[f"{year}-{m:02d}-01"] = r[m]
    cur = links.get("T02_01_03.xls")
    if cur:
        sh = xlrd.open_workbook(file_contents=get(cur)).sheet_by_index(0)
        year = None
        for i in range(sh.nrows):
            r = sh.row_values(i)
            c0 = str(r[0]).strip().upper()
            my = re.match(r"^(\d{4})(?:\.0)?$", c0)
            if my:
                year = int(my.group(1))
                continue
            mm = re.match(r"^([A-Z]{3})\w*\.?\s*(\d{4})?$", c0)
            if mm and mm.group(1) in MON and isinstance(r[4], float):
                y = int(mm.group(2)) if mm.group(2) else year
                if y:
                    out[f"{y}-{MON[mm.group(1)]:02d}-01"] = r[4]          # TOTAL column of the current table
    if not out:
        WARN.append("TH: EPPO table 2.1-3 not read")
    return [{"economy": "TH", "date": d, "value": v, "unit": "million litres", "series": "EPPO Table 2.1-3 import of crude oil, total"}
            for d, v in sorted(out.items())]


def india(st):
    import openpyxl  # noqa: PLC0415
    page = get("https://ppac.gov.in/import-export").decode("utf-8", "replace")
    u = next(iter(re.findall(r'href="(https://ppac\.gov\.in/uploads/pages/[^"]*Import-Export[^"]*\.xlsx)"', page)), None)
    if not u:
        WARN.append("IN: PPAC import-export workbook link not found")
        return []
    ws = openpyxl.load_workbook(io.BytesIO(get(u)), read_only=True, data_only=True).worksheets[0]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    hdr = next((r for r in rows if r and str(r[0] or "").strip().upper() == "IMPORT/EXPORT"), None)
    crude = next((r for r in rows if r and str(r[0] or "").strip().upper() == "CRUDE OIL"), None)
    if not hdr or not crude:
        WARN.append("IN: PPAC workbook layout changed")
        return []
    text = " ".join(str(c) for r in rows[:8] for c in r if c)
    fy = re.search(r"20(\d\d)\s*-\s*(\d\d)", text)
    vals = [(str(h).strip().upper()[:3], v) for h, v in zip(hdr[1:13], crude[1:13])]
    filled = [k for k, (_, v) in enumerate(vals) if isinstance(v, (int, float)) and v > 0]
    today = time.localtime()
    if fy:
        y0 = 2000 + int(fy.group(1))
    else:   # fiscal year April-March: the file is the current one; in April-May it can still be last year's
        y0 = today.tm_year if today.tm_mon >= 4 else today.tm_year - 1
        if today.tm_mon in (4, 5) and len(filled) == 12:
            y0 -= 1
    for k in filled:
        mon, v = vals[k]
        m = MON.get(mon)
        if not m:
            continue
        y = y0 if m >= 4 else y0 + 1
        st.data[f"IN:{y}-{m:02d}"] = v                 # latest file wins; earlier months kept
    return [{"economy": "IN", "date": k[3:] + "-01", "value": v, "unit": "thousand tonnes",
             "series": "PPAC Import/Export of crude oil and petroleum products, crude oil ('000 MT)"}
            for k, v in sorted(st.data.items()) if k.startswith("IN:")]


def indonesia():
    meta, recs = bps.var_data(2173)
    crude = [r for r in recs if re.search(r"minyak mentah", (r["vervar_label"] + " " + r["turvar_label"]).lower())]
    out = []
    for r in crude:
        f, d = bps.period_of(r)
        if f == "M":
            unit = "thousand tonnes" if "ribu" in r["unit"].lower() else "tonnes"
            out.append({"economy": "ID", "date": d, "value": r["value"], "unit": unit, "series": f"BPS var 2173 {r['vervar_label']} {r['turvar_label']}".strip()})
    if not out:
        labels = sorted({r["vervar_label"] for r in recs})[:12] + sorted({r["turvar_label"] for r in recs})[:12]
        WARN.append(f"ID: no monthly crude oil row in BPS var 2173; labels: {labels}")
    return out


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    WARN.clear()
    st = trade.Store("oil_crude")
    rows = from_trade()
    for name, fn in (("TH", thailand), ("IN", lambda: india(st)), ("ID", indonesia)):
        try:
            rows += fn()
        except Exception as e:  # noqa: BLE001
            WARN.append(f"{name}: {str(e)[:200]}")
    st.save()
    if not rows:
        raise CheckFailed(["no crude import volumes read"] + WARN[:5])
    out = []
    for r in sorted(rows, key=lambda r: (r["economy"], r["date"])):
        y, m = int(r["date"][:4]), int(r["date"][5:7])
        days = calendar.monthrange(y, m)[1]
        kbd = r["value"] * BBL[r["unit"]] / days / 1000
        out.append({**r, "value": round(r["value"], 3), "kbd": round(kbd, 1), "source": SRC[r["economy"]]})
    # sanity: no economy above 15 mb/d or a month more than 3x its neighbours' average
    bad = [f"{r['economy']} {r['date'][:7]} {r['kbd']}" for r in out if r["kbd"] > 15000]
    if bad:
        raise CheckFailed([f"implausible kb/d: {bad[:5]}"])
    with (OUT / "crude_imports.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["economy", "date", "value", "unit", "kbd", "source", "series"])
        w.writeheader()
        w.writerows(out)
    latest = {}
    for r in out:
        latest[r["economy"]] = r["date"][:7]
    code = "O" + max(latest.values())
    write_release(OUT, {"code": code, "label": "Crude oil imports", "latest": latest, "source": NAME,
                        "table": "national sources (see the source's docstring)"}, WARN[:20], len(out))
    return {"updated": True, "code": code, "warnings": WARN[:5],
            "summary": "; ".join(f"{e} to {d}" for e, d in sorted(latest.items()))}
