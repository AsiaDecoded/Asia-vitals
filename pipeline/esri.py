"""ESRI Quarterly GDP Estimates: release codes, URLs and CSV parsing.

Release codes follow ESRI's folder names:
  qe262    = Apr-Jun 2026, first preliminary   -> table files end in 2621
  qe262_2  = Apr-Jun 2026, second preliminary  -> table files end in 2622
Folders sit under files/<reference year>/, e.g. files/2026/qe262_2/tables/.
"""
import csv
import io
import re
import urllib.error
import urllib.request

BASE = "https://www.esri.cao.go.jp/jp/sna/data/data_list/sokuhou/files"
MENU = "https://www.esri.cao.go.jp/en/sna/data/sokuhou/files"

# table stem -> (basis, measure). Section I, expenditure side.
TABLES = {
    "gaku-jk": ("real", "level_saar"),
    "gaku-mk": ("nominal", "level_saar"),
    "gaku-jg": ("real", "level_orig"),
    "gaku-mg": ("nominal", "level_orig"),
    "ritu-jk": ("real", "qoq"),
    "ritu-mk": ("nominal", "qoq"),
    "nritu-jk": ("real", "qoq_ann"),
    "nritu-mk": ("nominal", "qoq_ann"),
    "ritu-jg": ("real", "yoy"),
    "ritu-mg": ("nominal", "yoy"),
    "kiyo-jk": ("real", "contrib_qoq"),
    "kiyo-jg": ("real", "contrib_yoy"),
    "def-qk": ("deflator", "index_sa"),
    "rdef-qk": ("deflator", "qoq"),
    "rdef-qg": ("deflator", "yoy"),
}

# English header in the CSV (whitespace removed) -> our component key
COLUMNS = {
    "GDP(ExpenditureApproach)": "gdp",
    "PrivateConsumption": "private_consumption",
    "PrivateResidentialInvestment": "residential",
    "PrivateNon-Resi.Investment": "business_investment",
    "ChangeinPrivateInventories": "private_inventories",
    "GovernmentConsumption": "government_consumption",
    "PublicInvestment": "public_investment",
    "ChangeinPublicInventories": "public_inventories",
    "NetExports": "net_exports",
    "Exports": "exports",
    "Imports": "imports",
    "DomesticDemand": "domestic_demand",
    "PrivateDemand": "private_demand",
    "PublicDemand": "public_demand",
}

QUARTER_NAMES = {1: "Jan–Mar", 2: "Apr–Jun", 3: "Jul–Sep", 4: "Oct–Dec"}
CODE_RE = re.compile(r"^qe(\d{2})([1-4])(_2)?$")
ROW_RE = re.compile(r"^\s*(?:(\d{4})/)?\s*(\d{1,2})-\s*(\d{1,2})\.\s*$")


# ---------- release codes ----------

def parse_code(code):
    m = CODE_RE.match(code)
    if not m:
        raise ValueError(f"not an ESRI release code: {code}")
    return 2000 + int(m.group(1)), int(m.group(2)), 2 if m.group(3) else 1


def make_code(year, q, est):
    return f"qe{year % 100:02d}{q}" + ("_2" if est == 2 else "")


def next_code(code):
    """The release after `code`: first preliminary -> second; second -> next quarter's first."""
    year, q, est = parse_code(code)
    if est == 1:
        return make_code(year, q, 2)
    return make_code(year + (q == 4), 1 if q == 4 else q + 1, 1)


def suffix(code):
    year, q, est = parse_code(code)
    return f"{year % 100:02d}{q}{est}"


def ref_date(code):
    """First day of the release's reference quarter, e.g. qe262_2 -> 2026-04-01."""
    year, q, _ = parse_code(code)
    return f"{year}-{3 * q - 2:02d}-01"


def label(code):
    year, q, est = parse_code(code)
    return f"{QUARTER_NAMES[q]} {year}, {'first' if est == 1 else 'second'} preliminary estimate"


def table_url(code, stem):
    year, _, _ = parse_code(code)
    return f"{BASE}/{year}/{code}/tables/{stem}{suffix(code)}.csv"


def menu_url(code):
    year, _, _ = parse_code(code)
    return f"{MENU}/{year}/{code}/gdemenuea.html"


# ---------- fetching ----------

def fetch(url, timeout=60):
    """Return bytes, or None if the file doesn't exist (404). Other errors raise."""
    req = urllib.request.Request(url, headers={"User-Agent": "asia-vitals/1.0 (+https://github.com/AsiaDecoded/asia-vitals)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            if b"<html" in body[:500].lower():
                return None  # an error page served with 200
            return body
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


# ---------- parsing ----------

def _num(cell):
    s = cell.strip().replace(",", "")
    if s in ("", "***"):
        return None
    return float(s)


def parse_table(raw_bytes):
    """Parse one ESRI table (CP932 CSV) into {title, units, data: [{date, <component>: value}]}.

    Layout: 2 title rows, Japanese headers (rows 3-5), English headers (rows 6-7),
    quarter rows "1994/ 1- 3." then "4- 6." (year carried forward), footnotes "＊...".
    Columns are matched by English header because their order differs between tables.
    """
    rows = list(csv.reader(io.StringIO(raw_bytes.decode("cp932"))))
    keys = {}
    width = max(len(rows[5]), len(rows[6]))
    for i in range(1, width):
        h6 = rows[5][i] if i < len(rows[5]) else ""
        h7 = rows[6][i] if i < len(rows[6]) else ""
        name = re.sub(r"\s+", "", h7 or h6)
        if name in COLUMNS:
            keys[i] = COLUMNS[name]
    missing = sorted(set(COLUMNS.values()) - set(keys.values()))
    data, year = [], None
    for r in rows[7:]:
        if not r:
            continue
        m = ROW_RE.match(r[0])
        if not m:
            continue
        if m.group(1):
            year = int(m.group(1))
        rec = {"date": f"{year}-{int(m.group(2)):02d}-01"}
        for i, k in keys.items():
            rec[k] = _num(r[i]) if i < len(r) else None
        data.append(rec)
    return {
        "title": rows[1][0].strip(),
        "units": next((c.strip() for c in rows[1] if c.strip().startswith("(")), ""),
        "missing_columns": missing,
        "data": data,
    }
