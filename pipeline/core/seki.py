"""Bank Indonesia SEKI tables (Statistik Ekonomi dan Keuangan Indonesia), as published Excel workbooks.

SEKI chapter VIII republishes BPS price data: VIII.1 (TABEL8_1.xls, CPI) and VIII.2 (TABEL8_2.xls, WPI).
Each workbook has one sheet per period (bases change between sheets); months run along the columns, with an
annual column after each December. This module downloads a table and reads a sheet into
{row number: (label, english label, {YYYY-MM: value})}.
"""
import datetime as dt
import re
import time
import urllib.error
import urllib.request

URL = "https://www.bi.go.id/SEKI/tabel/TABEL{n}.xls"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/vnd.ms-excel,*/*;q=0.8"}
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "may": 5, "jun": 6, "jul": 7, "ags": 8, "agu": 8,
          "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "des": 12, "dec": 12}


def download(n, tries=3):
    """TABEL<n>.xls as bytes (n like '8_1'), with its Last-Modified header."""
    err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(URL.format(n=n), headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
                if not body.startswith(b"\xd0\xcf\x11\xe0"):
                    raise ValueError(f"TABEL{n}.xls is not an Excel file ({body[:60]!r})")
                return body, r.headers.get("Last-Modified")
        except (urllib.error.URLError, ValueError, TimeoutError) as e:  # noqa: PERF203
            err = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"SEKI TABEL{n}.xls: {err}")


def _month(v):
    if isinstance(v, str):
        k = v.strip().lower()[:3]
        return MONTHS.get(k)
    return None


def _year(v):
    if isinstance(v, (int, float)) and 1900 < v < 2100 and float(v).is_integer():
        return int(v)
    if isinstance(v, str) and re.fullmatch(r"\s*(19|20)\d\d\s*", v):
        return int(v)
    return None


def columns(sh):
    """{column: 'YYYY-MM'} for a sheet. Month names (Indonesian or English) along one header row, the first year
    label above them, year rolled forward at each January (SEKI sometimes puts a year label on the wrong column);
    or Excel serial dates along one row. Columns without a month (annual averages) are left out."""
    import xlrd  # noqa: PLC0415
    for r in range(min(sh.nrows, 12)):
        row = sh.row_values(r)
        serial = [(c, v) for c, v in enumerate(row) if isinstance(v, float) and 20000 < v < 60000]
        if len(serial) >= 6:
            out = {}
            for c, v in serial:
                d = xlrd.xldate.xldate_as_datetime(v, 0)
                out[c] = f"{d.year}-{d.month:02d}"
            return out
        months = [(c, _month(v)) for c, v in enumerate(row) if _month(v)]
        if len(months) >= 6:
            first_c = months[0][0]
            year = None
            for rr in range(r - 1, -1, -1):
                ys = [(c, _year(v)) for c, v in enumerate(sh.row_values(rr)) if _year(v)]
                if ys:
                    # the year label for the first month column: the last label at or before it, else the first one
                    before = [y for c, y in ys if c <= first_c]
                    year = before[-1] if before else ys[0][1]
                    break
            if year is None:
                raise ValueError(f"sheet {sh.name}: no year label above the month row")
            out, prev = {}, None
            for c, m in months:
                if prev is not None and m <= prev:
                    year += 1
                if prev is not None and m != (prev % 12) + 1:
                    raise ValueError(f"sheet {sh.name}: month sequence breaks at column {c} ({prev} -> {m})")
                out[c] = f"{year}-{m:02d}"
                prev = m
            return out
    raise ValueError(f"sheet {sh.name}: no month header found")


def num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", ".")
        if re.fullmatch(r"-?\d+(\.\d+)?", s):
            return float(s)
    return None


def read(sh):
    """[(row, label, english label, {YYYY-MM: value})] for every row with at least one number."""
    cols = columns(sh)
    first = min(cols)
    out = []
    for r in range(sh.nrows):
        row = sh.row_values(r)
        vals = {}
        for c, ym in cols.items():
            v = num(row[c]) if c < len(row) else None
            if v is not None:
                vals[ym] = v
        label = " ".join(str(x).strip() for x in row[:first] if isinstance(x, str) and x.strip())
        eng = ""
        tail = [x for x in row[max(cols) + 1:] if isinstance(x, str) and x.strip()]
        if tail:
            eng = tail[0].strip()
        if vals or label:
            out.append((r, label, eng, vals))
    return out


def sheet_dates(sh):
    c = columns(sh)
    return min(c.values()), max(c.values())


def today_sgt():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
