"""Vietnam producer, input, transport, export and import prices as published by NSO.

NSO publishes no all-economy PPI and no monthly producer prices. Quarterly: PPI for agriculture, forestry and
fishing, industry and services (with sub-sectors), input prices for production, transport prices, export and
import prices (USD) and terms of trade, each against the same quarter last year, the previous quarter and the
year to date; from the socio-economic report tables ("Biểu") released with the CPI in quarter-end months,
Q1 2020 on. Annual (previous year = 100) from the PX-Web yearbook database. Nothing is calculated.
"""
import csv
import datetime as dt
import gzip
import json
import time
from pathlib import Path

from core import nso_vn as N
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "vn_ppi_nso"
DESCRIPTION = "Vietnam quarterly PPI by sector, input, export and import prices (NSO report tables, PX-Web annual)"
OUT = DATA / "vn" / "ppi"
RAWDIR = RAW / "vn" / "ppi_nso"
FIRST_Q = (2020, 1)
PX_ANNUAL = {"E11.15.px": "input", "E11.17.px": "ppi_agriculture", "E11.19.px": "ppi_industry", "E11.21.px": "ppi_services",
             "E11.23.px": "export", "E11.25.px": "import", "E11.27.px": "tot"}
TABLE_LABEL = {"ppi": "Producer prices", "input": "Input prices for production", "transport": "Transport and storage prices",
               "export": "Export prices (USD)", "import": "Import prices (USD)", "tot": "Terms of trade"}
REQUIRED = [("ppi", "agriculture"), ("ppi", "industry"), ("ppi", "services"), ("input", "all"), ("export", "all"), ("import", "all")]


def _quarters(today):
    y, q = FIRST_Q
    out = []
    while (y, q) <= (today.year, (today.month - 1) // 3 + 1):
        out.append((y, q))
        y, q = (y, q + 1) if q < 4 else (y + 1, 1)
    return out


def _window(y, q):
    """Upload window for the quarter's report tables: from the 20th of its last month to the 10th of the next."""
    m = q * 3
    a = dt.date(y, m, 20)
    b = dt.date(y + (m == 12), m % 12 + 1, 10)
    return f"{a}T00:00:00", f"{b}T00:00:00"


def _books(force):
    folder = RAWDIR / "books"
    folder.mkdir(parents=True, exist_ok=True)
    index = read_json(RAWDIR / "books.json", {}) or {}
    new = []
    today = dt.date.today()
    for y, q in _quarters(today):
        key = f"{y}-Q{q}"
        if key in index and not force:
            continue
        a, b = _window(y, q)
        if a[:10] > today.isoformat():
            continue
        found = None
        cands = N.report_workbooks(a, b)
        cands += [c for c in N.report_workbooks_search(q * 3, y) if c["url"] not in {x["url"] for x in cands}]
        for m in cands:   # Vietnamese, last upload first; English as a fallback; then a search by file name
            body, _ = N.get(m["url"])
            try:
                rows = N.read_quarter_book(body, m["url"])
            except Exception:  # noqa: BLE001 - some old .xls files cannot be read (xlrd UTF-16 error); try the next
                continue
            if any(r["quarter"] == key and r["table"] == "ppi" for r in rows):
                found = (m, body)
                break
            time.sleep(0.3)
        if not found:
            continue
        m, body = found
        fn = f"{key}_{N.sha(body)}{Path(m['url']).suffix}"
        (folder / fn).write_bytes(body)
        index[key] = {"url": m["url"], "uploaded": m["date"], "file": fn, "language": "en" if m.get("en") else "vi"}
        new.append(key)
    (RAWDIR / "books.json").write_text(json.dumps(dict(sorted(index.items())), ensure_ascii=False, indent=1) + "\n")
    return index, new


def _px(force):
    folder = RAWDIR / "px"
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for t in PX_ANNUAL:
        p = folder / f"{t}.gz"
        if force or not p.exists() or (time.time() - p.stat().st_mtime) > 31 * 86400:
            try:
                p.write_bytes(gzip.compress(N.px_export(t)))
            except Exception as e:  # noqa: BLE001
                if not p.exists():
                    raise
                print(f"   PX-Web {t}: export failed ({e}); using stored copy")
        out[t] = gzip.decompress(p.read_bytes())
    return out


def _qdate(key):
    y, q = int(key[:4]), int(key[-1])
    return f"{y}-{q * 3:02d}-01"     # dated at the quarter's last month (the release month)


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    index, new = _books(force)
    if not new and state.get("latest_quarter") and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no new quarter (latest {state['latest_quarter']})"}
    rows, errors, warnings = [], [], []
    for key, info in sorted(index.items()):
        body = (RAWDIR / "books" / info["file"]).read_bytes()
        got = [r for r in N.read_quarter_book(body, info["file"]) if r["quarter"] == key]
        labels = {}
        for r in got:
            labels.setdefault(r["table"], N.labels_for(r["table"]))
            rows.append({"date": _qdate(key), "period": key, "freq": "Q", "table": r["table"], "series": r["series"],
                         "label": labels[r["table"]].get(r["series"], r["series"]), "comparison_base": r["base"],
                         "value": round(r["value"], 6), "rate": round(r["value"] - 100, 6), "source": "nso_report",
                         "release_date": info["uploaded"][:10]})
    px = _px(force)
    for t, body in px.items():
        arows, meta = N.px_annual_rows(t, body)
        upd = meta.get("LAST-UPDATED", "")
        tab = PX_ANNUAL[t]
        for r in arows:
            rows.append({"date": f"{r['year']}-12-01", "period": str(r["year"]), "freq": "A", "table": tab,
                         "series": N.re.sub(r"[^a-z0-9]+", "_", r["item"].strip().lower()).strip("_")[:60],
                         "label": r["item"].strip(), "comparison_base": "prev_year", "value": round(r["value"], 6),
                         "rate": round(r["value"] - 100, 6), "source": "nso_pxweb",
                         "release_date": f"{upd[:4]}-{upd[4:6]}-{upd[6:8]}" if upd else ""})
    q = [r for r in rows if r["freq"] == "Q"]
    if not q:
        raise CheckFailed(["no quarterly price tables found"])
    latest = max(r["period"] for r in q)
    if state.get("latest_quarter") and latest < state["latest_quarter"]:
        errors.append(f"latest quarter {latest} is before the one stored ({state['latest_quarter']})")
    have = {(r["period"], r["table"], r["series"], r["comparison_base"]) for r in q}
    for t, s in REQUIRED:
        for b in ("yoy", "prev_quarter"):
            if (latest, t, s, b) not in have:
                errors.append(f"{latest}: {t} {s} {b} missing")
    allq = [f"{y}-Q{qq}" for y, qq in _quarters(dt.date(int(latest[:4]), int(latest[-1]) * 3, 1))]
    miss = [k for k in allq if (k, "ppi", "industry", "yoy") not in have]
    if miss:
        errors.append(f"industry PPI y/y missing for {miss}")
    for r in rows:
        if not 40 < r["value"] < 250:
            errors.append(f"{r['period']} {r['table']} {r['series']} {r['comparison_base']}: {r['value']} out of range")
    # quarter y/y in the report tables vs the PX-Web annual: Q4 'year vs previous year' equals the annual figure
    ann = {(r["table"], r["label"], r["period"]): r["value"] for r in rows if r["freq"] == "A"}
    for r in q:
        if r["period"].endswith("Q4") and r["comparison_base"] == "ytd_avg" and r["table"] == "ppi" and r["series"] == "industry":
            a = next((v for (t, lab, p), v in ann.items() if t == "ppi_industry" and lab.upper().startswith("GENERAL") and p == r["period"][:4]), None)
            if a is not None and abs(a - r["value"]) > 0.05:
                warnings.append(f"{r['period']} industry PPI: report {r['value']:.2f} vs PX-Web annual {a:.2f}")
    if errors:
        raise CheckFailed(errors)
    rows.sort(key=lambda r: (r["freq"], r["date"], r["table"], r["series"], r["comparison_base"]))
    cols = ["date", "period", "freq", "table", "series", "label", "comparison_base", "value", "rate", "source", "release_date"]
    with open(OUT / "vn_ppi.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    with open(OUT / "vn_ppi_dash.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "period", "table", "series", "label", "measure", "value"], lineterminator="\n")
        w.writeheader()
        for r in q:
            w.writerow({"date": r["date"], "period": r["period"], "table": r["table"], "series": f"{r['table']}_{r['series']}", "label": r["label"],
                        "measure": {"yoy": "yoy", "prev_quarter": "qoq", "ytd_avg": "ytd_avg"}[r["comparison_base"]], "value": r["rate"]})
    code = f"P{latest}"

    def long_rows():
        for r in rows:
            yield {"country": "VN", "indicator": "ppi", "series": f"{r['table']}_{r['series']}", "label": f"{TABLE_LABEL.get(r['table'], r['table'])}: {r['label']}",
                   "measure": r["comparison_base"], "area": "national", "freq": r["freq"], "date": r["date"], "value": r["rate"],
                   "unit": "%", "source": N.SOURCE, "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    with open(OUT / "asia.csv", "w", newline="") as f:   # ppi_yoy left empty: NSO publishes no all-economy PPI (decision 3)
        csv.writer(f, lineterminator="\n").writerow(["country", "concept", "series_id", "date", "value", "unit", "basis", "source",
                                                     "base_break", "release_date", "comparison_base"])
    release = {"code": code, "label": latest.replace("-", " "), "latest_quarter": latest,
               "table": "NSO socio-economic report tables (quarterly price indices), PX-Web E11.15-E11.27", "books": len(index)}
    write_release(OUT, release, warnings, len(rows), {"long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{latest}: {len(rows)} rows, {len(index)} quarterly workbooks", "warnings": warnings}
