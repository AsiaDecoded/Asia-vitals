"""Indonesia central government finance and government securities, as republished by Bank Indonesia in SEKI
chapter IV (Ministry of Finance data). As published, nothing calculated.

  IV.1 Government revenue and grants, IV.2 government expenditure, IV.3 government financing: annual, Rp billion,
       budget (APBN) and actual (realisasi), the current sheet's years (2008 on), every row.
       Earlier sheets, actual totals only (revenue and grants, expenditure, surplus/deficit; added 30 Oct 2026 for the growth
       chart): 2001-2007 (calendar years) and 1990-2000 (SEKI's 1990 = fiscal year April 1990-March 1991, ...;
       2000 = the nine-month transition April-December 2000) -> id_fiscal_hist.csv.
  IV.4 Government securities (SBN) outstanding, Rp billion, by type and holder: end-December 2008 and 2009, then
       monthly from January 2010.

Year to date: the monthly outturn comes from id_fiscal_kemenkeu (data/id/fiscal/id_fiscal_monthly.csv). An optional
hand-entered ytd.csv in this folder (removed 30 Oct 2026) would still be read as basis "ytd".

Files: bi.go.id/SEKI/tabel/TABEL4_<n>.xls (no key). The workbook's own English row labels (the ITEMS column) are kept.
Bank Indonesia updates SEKI some weeks after the Ministry of Finance publishes; new data detected by the latest
period of IV.4 and of IV.1-IV.3.
"""
import csv
import hashlib
import json
import re
from pathlib import Path

from core import seki
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "id_fiscal_seki"
DESCRIPTION = "Indonesia central government budget and actual (annual) and SBN outstanding (monthly), SEKI chapter IV"
OUT = DATA / "id" / "fiscal"
RAWDIR = RAW / "id" / "fiscal_seki"
SOURCE = "Bank Indonesia SEKI (Ministry of Finance data)"
TABLES = {"4_1": "revenue", "4_2": "expenditure", "4_3": "financing"}
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "mei": 5, "jun": 6, "jul": 7, "aug": 8, "agu": 8, "ags": 8,
          "sep": 9, "oct": 10, "okt": 10, "nov": 11, "dec": 12, "des": 12}


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    return float(s) if re.fullmatch(r"-?\d+(\.\d+)?", s) else None


def _items_col(sh, hdr_row):
    row = sh.row_values(hdr_row)
    return next((c for c, v in enumerate(row) if str(v).strip().upper() == "ITEMS"), None)


def read_annual(sh):
    """[(section, item, label_id, label_en, {year: value})]: section 'budget' from the APBN row down to the
    Realisasi row, 'actual' below it; item = position within the section (aligns budget and actual)."""
    hdr = next(r for r in range(min(10, sh.nrows)) if str(sh.cell_value(r, 2)).strip().upper() == "KETERANGAN")
    ic = _items_col(sh, hdr)
    cols, seen = {}, set()
    for c, v in enumerate(sh.row_values(hdr)[3:ic], start=3):
        y = int(v) if isinstance(v, float) and 1990 < v < 2100 else None
        if y is None:
            continue
        if y in seen or (seen and y < max(seen)):   # duplicated year columns at the right of the sheet
            break
        seen.add(y)
        cols[c] = y
    out, section, item = [], None, 0
    for r in range(hdr + 1, sh.nrows):
        lab = str(sh.cell_value(r, 2)).strip()
        eng = str(sh.cell_value(r, ic)).strip() if ic is not None else ""
        if re.match(r"(?i)^apbn", lab):
            section, item = "budget", 0
            continue
        if re.match(r"(?i)^realisasi", lab):
            section, item = "actual", 0
            continue
        if not section or not lab:
            continue
        vals = {y: _num(sh.cell_value(r, c)) for c, y in cols.items()}
        vals = {y: v for y, v in vals.items() if v is not None}
        item += 1
        out.append((section, item, re.sub(r"\s+", " ", lab), re.sub(r"\s+", " ", eng), vals))
    return out


def read_sbn(sh):
    """[(item, label_id, label_en, {YYYY-MM-01: value})] for IV.4 (year row, month row below it)."""
    hdr = next(r for r in range(min(10, sh.nrows)) if str(sh.cell_value(r, 2)).strip().upper() == "KETERANGAN")
    ic = _items_col(sh, hdr)
    years, months = sh.row_values(hdr), sh.row_values(hdr + 1)
    # Year labels sit on varying columns (the January or the December of a year, or the last month shown), so the
    # year is rolled forward at each January (and at a December following a December: 2008 and 2009 show December
    # only), starting from the first label; every label must then agree with the rolled year.
    first = next(int(v) for v in years[3:ic] if isinstance(v, float) and 1990 < v < 2100)
    cols, y, prev = {}, first, None
    for c in range(3, ic):
        m = MONTHS.get(str(months[c]).strip().lower()[:3])
        if not m:
            continue           # the blank column after each December repeats December (annual position)
        if prev is not None and (m == 1 and prev == 12 or m == 12 and prev == 12):
            y += 1
        elif prev is not None and m != prev + 1:
            raise ValueError(f"IV.4: month sequence breaks at column {c} ({prev} -> {m})")
        lab = years[c]
        if isinstance(lab, float) and 1990 < lab < 2100 and int(lab) != y:
            raise ValueError(f"IV.4: year label {int(lab)} at column {c} where the months give {y}")
        cols[c] = f"{y}-{m:02d}-01"
        prev = m
    out, item = [], 0
    for r in range(hdr + 2, sh.nrows):
        lab = str(sh.cell_value(r, 2)).strip()
        if not lab or lab.startswith("*"):
            continue
        vals = {d: _num(sh.cell_value(r, c)) for c, d in cols.items()}
        vals = {d: v for d, v in vals.items() if v is not None}
        if not vals:
            continue
        item += 1
        out.append((item, re.sub(r"\s+", " ", lab), re.sub(r"\s+", " ", str(sh.cell_value(r, ic)).strip()), vals))
    return out


HIST = {"revenue": r"^Pendapatan Negara dan Hibah$", "expenditure": r"^Belanja Negara$", "financing": r"^Surplus\s*/\s*Defisit$"}


def read_hist(sh):
    """Totals from an older IV.1-IV.3 sheet: {("actual", year): value} for the table's total row (HIST). Actual only
    (the 1990-2000 budget block in IV.3 is not laid out like the others)."""
    yr = next(r for r in range(min(12, sh.nrows)) if sum(isinstance(v, float) and 1989 < v < 2008 for v in sh.row_values(r)[3:]) >= 5)
    cols = {}
    for c, v in enumerate(sh.row_values(yr)[3:], start=3):
        if isinstance(v, float) and 1989 < v < 2008 and int(v) not in cols.values():
            cols[c] = int(v)
        elif cols:
            break
    out, section = {}, None
    for r in range(yr + 1, sh.nrows):
        lab = re.sub(r"\s+", " ", " ".join(str(sh.cell_value(r, c)).strip() for c in (1, 2)).strip())
        if re.match(r"(?i)^apbn$", lab):
            section = "budget"
        elif re.match(r"(?i)^realisasi$", lab):
            section = "actual"
        elif section == "actual" and any(re.match(pat, lab, re.I) for pat in HIST.values()):
            if any(k[0] == section for k in out):
                continue   # first match per section is the total
            for c, y in cols.items():
                v = _num(sh.cell_value(r, c))
                if v is not None:
                    out[(section, y)] = v
    return out


def period_label(y):
    return f"Apr {y}-Mar {y + 1}" if y < 2000 else ("Apr-Dec 2000" if y == 2000 else str(y))


def checks(ann, sbn):
    errors, warnings = [], []
    a = {(t, s, it): v for t, rows in ann.items() for s, it, _l, _e, v in rows}
    lab = {(t, s, it): l for t, rows in ann.items() for s, it, l, _e, _v in rows}

    def find(t, s, pat, n=1):
        ks = [k for k in lab if k[0] == t and k[1] == s and re.search(pat, lab[k], re.I)]
        return ks[n - 1] if len(ks) >= n else None

    years = sorted({y for v in a.values() for y in v})
    if not years:
        return ["no annual values read"], warnings
    for s in ("budget", "actual"):
        rev, dom, gr = find("revenue", s, r"^Pendapatan Negara"), find("revenue", s, r"^Penerimaan Dalam Negeri"), find("revenue", s, r"^Hibah")
        exp, cen, trf = find("expenditure", s, r"^Belanja Negara"), find("expenditure", s, r"^Belanja Pemerintah Pusat"), find("expenditure", s, r"^Transfer Ke Daerah")
        sus = find("expenditure", s, r"^Suspen")
        defi = find("financing", s, r"^Surplus")
        if None in (rev, dom, gr, exp, cen, trf, defi):
            errors.append(f"{s}: a total row was not found ({[rev, dom, gr, exp, cen, trf, defi]})")
            continue
        for y in years:
            g = lambda k: a[k].get(y)  # noqa: E731
            if None not in (g(rev), g(dom), g(gr)) and abs(g(dom) + g(gr) - g(rev)) > 2:
                warnings.append(f"{y} {s}: domestic revenue + grants {g(dom) + g(gr):,.0f} vs revenue {g(rev):,.0f}")
            sv = (a[sus].get(y) or 0.0) if sus else 0.0   # actual expenditure includes a suspense item
            if None not in (g(exp), g(cen), g(trf)) and abs(g(cen) + g(trf) + sv - g(exp)) > 2:
                warnings.append(f"{y} {s}: central + transfers (+ suspense) {g(cen) + g(trf) + sv:,.0f} vs expenditure {g(exp):,.0f}")
            if None not in (g(rev), g(exp), g(defi)) and abs(g(rev) - g(exp) - g(defi)) > 2:
                errors.append(f"{y} {s}: revenue - expenditure {g(rev) - g(exp):,.0f} vs published surplus/deficit {g(defi):,.0f}")
    for t in TABLES.values():
        if not any(k[0] == t and k[1] == "actual" and years[-1] in v for k, v in a.items()):
            errors.append(f"{t}: no actual for the latest year {years[-1]}")
    # SBN: totals agree with their parts
    s = {l: v for _i, l, _e, v in sbn}
    dates = sorted({d for _i, _l, _e, v in sbn for d in v})
    if not dates:
        errors.append("IV.4: no values read")
        return errors, warnings
    by = {}
    for i, l, e, v in sbn:
        by.setdefault(l, []).append(v)
    sun, ob, spn = by.get("SURAT UTANG NEGARA (SUN)", [None])[0], by.get("Obligasi Negara", [None])[0], by.get("Surat Perbendaharaan Negara (SPN)", [None])[0]
    if None in (sun, ob, spn):
        errors.append("IV.4: SUN, Obligasi Negara or SPN row not found")
    else:
        bad = [d for d in dates if None not in (sun.get(d), ob.get(d), spn.get(d)) and abs(ob[d] + spn[d] - sun[d]) > 2]
        if bad:
            errors.append(f"IV.4: Obligasi + SPN differ from SUN in {bad[:6]}")
        if dates[-1] not in sun:
            errors.append(f"IV.4: SUN missing for the latest month {dates[-1]}")
    months = [d for d in dates if d >= "2010-01-01"]
    want = [f"{y}-{m:02d}-01" for y in range(2010, int(dates[-1][:4]) + 1) for m in range(1, 13) if f"{y}-{m:02d}-01" <= dates[-1]]
    gaps = [d for d in want if d not in months]
    if gaps:
        errors.append(f"IV.4: months missing {gaps[:6]}")
    return errors, warnings


def update(force=False, **_):
    import xlrd  # noqa: PLC0415
    OUT.mkdir(parents=True, exist_ok=True)
    RAWDIR.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    books, stamps = {}, {}
    for n in list(TABLES) + ["4_4"]:
        b, lm = seki.download(n)
        books[n], stamps[n] = b, lm
    ann, hist = {}, {}
    for n, t in TABLES.items():
        wb = xlrd.open_workbook(file_contents=books[n])
        ann[t] = read_annual(wb.sheet_by_index(wb.nsheets - 1))
        for i in range(wb.nsheets - 1):
            for k, v in read_hist(wb.sheet_by_index(i)).items():
                hist.setdefault(k, {})[t] = v
    wb = xlrd.open_workbook(file_contents=books["4_4"])
    sbn = read_sbn(wb.sheet_by_index(wb.nsheets - 1))
    latest_m = max(d for _i, _l, _e, v in sbn for d in v)
    latest_y = max(y for rows in ann.values() for _s, _i, _l, _e, v in rows for y in v)
    ytd_text = Path(__file__).with_name("ytd.csv").read_text(encoding="utf-8") if Path(__file__).with_name("ytd.csv").exists() else ""
    fp = hashlib.sha256(json.dumps([ann, sbn, ytd_text, sorted((list(k), v) for k, v in hist.items())], sort_keys=True,
                                   default=str).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    errors, warnings = checks(ann, sbn)
    hyears = sorted({k[1] for k in hist})
    if hyears != list(range(1990, 2008)):
        errors.append(f"older sheets: years read {hyears[:3]}..{hyears[-3:]}, expected 1990-2007")
    for k, v in sorted(hist.items()):
        if set(v) != set(TABLES.values()):
            errors.append(f"older sheets {k}: missing {set(TABLES.values()) - set(v)}")
        elif abs(v["revenue"] - v["expenditure"] - v["financing"]) > 2:
            errors.append(f"older sheets {k}: revenue - expenditure {v['revenue'] - v['expenditure']:,.0f} vs surplus/deficit {v['financing']:,.0f}")
    if state.get("latest_month") and latest_m < state["latest_month"]:
        errors.append(f"IV.4 latest month {latest_m} is before the one stored ({state['latest_month']})")
    if errors:
        raise CheckFailed(errors)
    for n, b in books.items():
        (RAWDIR / f"TABEL{n}.xls").write_bytes(b)

    arows = []
    for t, rows in ann.items():
        for s, it, l, e, v in rows:
            for y, val in sorted(v.items()):
                arows.append({"year": y, "table": t, "basis": s, "item": it, "label": e or l, "label_id": l, "value": val})
    actual_years = {r["year"] for r in arows if r["basis"] == "actual"}
    ytd_path = Path(__file__).with_name("ytd.csv")
    ytd = [r for r in csv.DictReader(open(ytd_path, encoding="utf-8"))] if ytd_path.exists() else []
    for r in ytd:
        y = int(r["year"])
        if y in actual_years:
            warnings.append(f"ytd.csv: {y} now has a full-year actual in SEKI; the year-to-date row is dropped")
            continue
        arows.append({"year": y, "table": r["table"], "basis": "ytd", "item": 0, "label": r["label"],
                      "label_id": r["label_id"], "value": float(r["value"]), "through": r["through"],
                      "released": r["released"], "note": r["source"]})
    yt = {r["table"]: r["value"] for r in arows if r["basis"] == "ytd"}
    if len(yt) == 3 and abs(yt["revenue"] - yt["expenditure"] - yt["financing"]) > 1000:
        errors.append(f"ytd.csv: revenue - expenditure {yt['revenue'] - yt['expenditure']:,.0f} vs deficit {yt['financing']:,.0f}")
        raise CheckFailed(errors)
    arows.sort(key=lambda r: (r["year"], list(TABLES.values()).index(r["table"]), r["basis"], r["item"]))
    acols = ["year", "table", "basis", "item", "label", "label_id", "value", "through", "released", "note"]
    with open(OUT / "id_fiscal_annual.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(acols)
        for r in arows:
            w.writerow([r.get(c, "") for c in acols])
    hcols = ["year", "period", "basis", "revenue", "expenditure", "balance"]
    with open(OUT / "id_fiscal_hist.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(hcols)
        for (b, y), v in sorted(hist.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            w.writerow([y, period_label(y), b, v["revenue"], v["expenditure"], v["financing"]])
    srows = [{"date": d, "item": i, "label": e or l, "label_id": l, "value": val}
             for i, l, e, v in sbn for d, val in sorted(v.items())]
    srows.sort(key=lambda r: (r["date"], r["item"]))
    scols = ["date", "item", "label", "label_id", "value"]
    with open(OUT / "id_sbn.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(scols)
        for r in srows:
            w.writerow([r[c] for c in scols])

    code = f"F{latest_y}-{latest_m[:7]}"
    mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(latest_m[5:7]) - 1]
    label = f"budget and actual to {latest_y}; SBN to {mon} {latest_m[:4]}"

    def long_rows():
        for r in arows:
            yield {"country": "ID", "indicator": "fiscal", "series": f"{r['table']}{r['item']:02d}", "label": r["label"],
                   "measure": r["basis"], "area": "central government", "freq": "A", "date": f"{r['year']}-01-01",
                   "value": r["value"], "unit": "Rp billion", "source": SOURCE, "release": code}
        for r in srows:
            yield {"country": "ID", "indicator": "sbn", "series": f"sbn{r['item']:02d}", "label": r["label"],
                   "measure": "outstanding", "area": "central government", "freq": "M", "date": r["date"],
                   "value": r["value"], "unit": "Rp billion", "source": SOURCE, "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    write_release(OUT, {"code": code, "label": label, "latest_year": latest_y, "latest_month": latest_m,
                        "last_modified": stamps, "table": "Bank Indonesia SEKI IV.1-IV.4"},
                  warnings, len(arows) + len(srows), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{label}; {len(arows)} annual and {len(srows)} SBN rows",
            "warnings": warnings}
