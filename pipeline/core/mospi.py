"""MoSPI API client (api.mospi.gov.in): CPI and WPI. No key needed.

MoSPI's server still needs legacy TLS renegotiation, which OpenSSL 3 refuses by default;
certificate checks stay on, only that flag is relaxed. Pages are capped at 100 rows for CPI.
"""
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.mospi.gov.in"
UA = {"User-Agent": "asia-vitals/0.1 (+https://github.com/AsiaDecoded/asia-vitals)",
      "Accept": "application/json"}
CTX = ssl.create_default_context()
CTX.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
PAGE = 100
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def _get(path, params, tries=4):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90, context=CTX) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code < 500:
                raise RuntimeError(f"MoSPI {e.code} for {url}: {e.read()[:300]!r}") from e
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def paged(path, params, max_pages=60):
    """All rows of a query, page by page. Returns (rows, total_records)."""
    rows, page, total = [], 1, None
    while True:
        res = _get(path, {**params, "limit": str(PAGE), "page": str(page), "Format": "JSON"})
        data = res.get("data") or []
        meta = res.get("meta_data") or {}
        total = meta.get("totalRecords", total)
        rows.extend(data)
        pages = meta.get("totalPages") or 1
        if page >= pages or not data:
            break
        page += 1
        if page > max_pages:
            raise RuntimeError(f"{path}: more than {max_pages} pages ({total} records); query too broad")
        time.sleep(0.5)
    return rows, total


def cpi(series, years=None, max_pages=60, **filters):
    """CPI on the 2024 base. series: "Current" or "Back"."""
    params = {"base_year": "2024", "series": series, **{k: str(v) for k, v in filters.items()}}
    if years:
        params["year"] = ",".join(str(y) for y in years)
    return paged("/api/cpi/getCPIData", params, max_pages=max_pages)


def month_number(name):
    return MONTHS.index(str(name).strip().capitalize()) + 1


def cpi_2012(years, **filters):
    """CPI on the old 2012 base (to Dec 2025): groups and subgroups, published y/y."""
    params = {"base_year": "2012", "series": "Current", "year": ",".join(str(y) for y in years),
              **{k: str(v) for k, v in filters.items()}}
    return paged("/api/cpi/getCPIIndex", params)

