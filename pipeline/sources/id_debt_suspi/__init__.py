"""Indonesia central government gross debt, quarterly from Q1 2014, from the Public Sector Debt Statistics of Indonesia
(SUSPI, Statistik Utang Sektor Publik Indonesia), compiled by Bank Indonesia and the Ministry of Finance, as published.
Asked for 30 Oct 2026 (official debt in place of the IMF's).

Each quarterly release on bi.go.id carries a zip with an IDR workbook covering the last eight or nine quarters
(the 2017 release, 2014-2017). Table 1.1 (central government), row "Total gross debt", Rp billion: debt securities and
loans at nominal value plus accrued interest. The latest release is found on the SUSPI index page; earlier quarters
come from each year's Q4 release. Where releases overlap, the later one wins (revisions; the latest quarters are
marked provisional).

% of GDP (calculated, asked for 30 Oct 2026): debt at the end of a quarter / nominal GDP of the four quarters to it
(BPS quarterly, data/id/gdp/id_gdp.csv code 800); for a year-end this is the annual GDP.
"""
import csv
import hashlib
import io
import json
import re
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "id_debt_suspi"
DESCRIPTION = "Indonesia central government gross debt, quarterly, SUSPI (Bank Indonesia and Ministry of Finance)"
OUT = DATA / "id" / "debt"
RAWDIR = RAW / "id" / "debt_suspi"
SOURCE = "Bank Indonesia and Ministry of Finance, Statistik Utang Sektor Publik Indonesia (SUSPI), table 1.1"
BI = "https://www.bi.go.id"
INDEX = BI + "/id/statistik/ekonomi-keuangan/suspi/default.aspx"
PAGE = BI + "/id/statistik/ekonomi-keuangan/suspi/Pages/SUSPI_TW{q}_{y}.aspx"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4}


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url.replace(" ", "%20"), headers=UA), timeout=180) as r:
                return r.read()
        except Exception:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def zip_of(page_url):
    t = get(page_url).decode("utf-8", "replace")
    z = [l for l in re.findall(r'href="([^"#]+\.zip)"', t, re.I) if "metadata" not in l.lower()]
    return urllib.parse.urljoin(page_url, z[0]) if z else None


def read_book(b):
    """{'YYYY-Qn': Rp billion} from table 1.1 of a SUSPI IDR workbook."""
    import openpyxl  # noqa: PLC0415
    wb = openpyxl.load_workbook(io.BytesIO(b), read_only=True, data_only=True)
    ws = next((w for w in wb.worksheets if w.title.strip() in ("1.1",) or re.search(r"(?i)^1\.1\.?\s*central", w.title.strip())), None)
    if ws is None:
        return {}
    rows = [list(r) for r in ws.iter_rows(max_row=90, values_only=True)]
    cols = {}
    for i, r in enumerate(rows[:20]):
        lab = [(j, str(c).strip().rstrip("*")) for j, c in enumerate(r) if c is not None]
        qs = [(j, v) for j, v in lab if re.fullmatch(r"(19|20)\d\dQ[1-4]", v)]
        if len(qs) >= 3:
            cols = {j: f"{v[:4]}-Q{v[-1]}" for j, v in qs}
            break
        qs = [(j, v) for j, v in lab if re.fullmatch(r"Q[1-4]", v)]
        if len(qs) >= 3 and i > 0:
            years = {j: int(float(c)) for j, c in enumerate(rows[i - 1]) if c is not None and re.fullmatch(r"(19|20)\d\d(\.0)?", str(c).strip())}
            y = None
            for j, v in sorted(qs):
                y = years.get(j, y)
                if y:
                    cols[j] = f"{y}-Q{v[-1]}"
            break
    tot = next((r for r in rows if any(isinstance(c, str) and c.strip().lower().startswith("total gross debt") for c in r)), None)
    if not cols or tot is None:
        return {}
    return {q: float(tot[j]) for j, q in cols.items() if j < len(tot) and isinstance(tot[j], (int, float))}


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    RAWDIR.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    idx = get(INDEX).decode("utf-8", "replace")
    rel = sorted({(int(y), ROMAN[q]) for q, y in re.findall(r"SUSPI_TW(IV|III|II|I)_(\d{4})\.aspx", idx)})
    if not rel:
        raise CheckFailed(["SUSPI index: no release pages listed"])
    ly, lq = rel[-1]
    latest = PAGE.format(q={v: k for k, v in ROMAN.items()}[lq], y=ly)
    pages = [PAGE.format(q="IV", y=y) for y in range(2017, ly)] + [latest]
    series, used, errors, warnings = {}, [], [], []
    for p in pages:
        z = zip_of(p)
        if not z:
            warnings.append(f"no zip on {p}")
            continue
        zb = get(z)
        name = re.sub(r"[^A-Za-z0-9._-]", "_", z.rsplit("/", 1)[-1])
        (RAWDIR / name).write_bytes(zb)
        got = {}
        with zipfile.ZipFile(io.BytesIO(zb)) as zf:
            for n in zf.namelist():
                if n.lower().endswith(".xlsx") and "usd" not in n.lower():
                    got.update(read_book(zf.read(n)))
        if not got:
            warnings.append(f"{name}: table 1.1 not read")
            continue
        for q, v in got.items():
            if q in series and abs(series[q] / v - 1) > 0.02:
                warnings.append(f"{q}: {name} revises {series[q]:,.0f} to {v:,.0f}")
            series[q] = v   # later release wins
        used.append({"page": p, "zip": z, "quarters": f"{min(got)}..{max(got)}"})
    qs = sorted(series)
    want = [f"{y}-Q{q}" for y in range(2014, ly + 1) for q in range(1, 5) if (y, q) <= (ly, lq)]
    gaps = [q for q in want if q not in series]
    if gaps:
        errors.append(f"quarters missing: {gaps[:8]}")
    if qs and qs[-1] != f"{ly}-Q{lq}":
        errors.append(f"latest release is {ly}-Q{lq} but the series ends {qs[-1]}")
    jumps = [q for a, q in zip(qs, qs[1:]) if not 0.85 < series[q] / series[a] < 1.25]
    if jumps:
        errors.append(f"quarter-on-quarter change beyond -15%/+25%: {jumps[:5]}")
    if errors:
        raise CheckFailed(errors)
    # GDP, four quarters to each quarter end (calculated)
    gq = {}
    for r in csv.DictReader(open(DATA / "id" / "gdp" / "id_gdp.csv", encoding="utf-8")):
        if r["code"] == "800" and r["nominal_level"]:
            y, m = int(r["date"][:4]), int(r["date"][5:7])
            gq[f"{y}-Q{(m - 1) // 3 + 1}"] = float(r["nominal_level"])

    def prev(q, k):
        y, n = int(q[:4]), int(q[-1]) - k
        while n < 1:
            y, n = y - 1, n + 4
        return f"{y}-Q{n}"
    rows = []
    for q in qs:
        four = [prev(q, k) for k in range(4)]
        g = sum(gq[x] for x in four) if all(x in gq for x in four) else None
        rows.append({"quarter": q, "date": f"{q[:4]}-{int(q[-1]) * 3:02d}-01", "debt": round(series[q], 3),
                     "gdp_4q": round(g, 3) if g else "", "debt_pct_gdp": round(series[q] / g * 100, 3) if g else ""})
    nogdp = [r["quarter"] for r in rows if r["debt_pct_gdp"] == ""]
    if nogdp:
        warnings.append(f"no four-quarter GDP yet for {nogdp}; ratio left blank")
    fp = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    cols = ["quarter", "date", "debt", "gdp_4q", "debt_pct_gdp"]
    with open(OUT / "id_debt.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])
    code = f"S{qs[-1]}"
    label = f"{qs[0]}..{qs[-1]}"

    def long_rows():
        for r in rows:
            yield {"country": "ID", "indicator": "debt", "series": "cg_gross_debt", "label": "Central government gross debt",
                   "measure": "level", "area": "central government", "freq": "Q", "date": r["date"], "value": r["debt"],
                   "unit": "Rp billion", "source": SOURCE, "release": code}
            if r["debt_pct_gdp"] != "":
                yield {"country": "ID", "indicator": "debt", "series": "cg_gross_debt_pct_gdp", "label": "Central government gross debt, % of GDP (calculated)",
                       "measure": "calculated", "area": "central government", "freq": "Q", "date": r["date"], "value": r["debt_pct_gdp"],
                       "unit": "% of GDP", "source": SOURCE + "; BPS GDP", "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    write_release(OUT, {"code": code, "label": label, "latest_quarter": qs[-1], "releases": used, "table": INDEX},
                  warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    last = rows[-1]
    return {"updated": True, "code": code, "summary": f"{label}; {last['quarter']} Rp {last['debt'] / 1000:,.1f} trn"
            f" ({last['debt_pct_gdp']}% of GDP)", "warnings": warnings}
