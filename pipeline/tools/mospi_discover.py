"""Probe MoSPI's API (api.mospi.gov.in) for India CPI (2024 base) and WPI (2022-23 base).

  python -I pipeline/tools/mospi_discover.py discovery/mospi

Saves each raw response as <out>/<name>.json (or .txt) and a summary.json listing,
for every call: URL, HTTP status, record count, the keys of the first record and the
latest year/month seen. No key or token: this tests what an unauthenticated client gets.
"""
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://api.mospi.gov.in"
# MoSPI's server still needs legacy TLS renegotiation, which OpenSSL 3 refuses by default.
# Certificate checks stay on; only the renegotiation flag is relaxed.
CTX = ssl.create_default_context()
CTX.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
UA = {"User-Agent": "asia-vitals/0.1 (+https://github.com/AsiaDecoded/asia-vitals)",
      "Accept": "application/json"}

CALLS = [
    # CPI metadata
    ("cpi_base_years", "/api/cpi/getCpiBaseYear", {}),
    ("cpi_filters_2024_group", "/api/cpi/getCpiFilterByLevelAndBaseYear",
     {"base_year": "2024", "level": "Group", "series_code": "Current"}),
    ("cpi_filters_2024_item", "/api/cpi/getCpiFilterByLevelAndBaseYear",
     {"base_year": "2024", "level": "Item", "series_code": "Current"}),
    ("cpi_filters_2024_back", "/api/cpi/getCpiFilterByLevelAndBaseYear",
     {"base_year": "2024", "level": "Group", "series_code": "Back"}),
    # CPI data, 2024 base: all-India, all sectors, latest year; then the limit ceiling
    ("cpi2024_allindia_2026", "/api/cpi/getCPIData",
     {"base_year": "2024", "series": "Current", "year": "2026", "state_code": "99",
      "limit": "100", "page": "1", "Format": "JSON"}),
    ("cpi2024_limit1000", "/api/cpi/getCPIData",
     {"base_year": "2024", "series": "Current", "year": "2026", "limit": "1000",
      "page": "1", "Format": "JSON"}),
    ("cpi2024_items_2026", "/api/cpi/getCPIData",
     {"base_year": "2024", "series": "Current", "level": "Item", "year": "2026",
      "limit": "100", "page": "1", "Format": "JSON"}),
    ("cpi2024_back_2015", "/api/cpi/getCPIData",
     {"base_year": "2024", "series": "Back", "year": "2015", "limit": "100",
      "page": "1", "Format": "JSON"}),
    ("cpi2024_csv", "/api/cpi/getCPIData",
     {"base_year": "2024", "series": "Current", "year": "2026", "state_code": "99",
      "limit": "100", "page": "1", "Format": "CSV"}),
    # Old series (2012 base) for history
    ("cpi2012_allindia_2025", "/api/cpi/getCPIIndex",
     {"base_year": "2012", "series": "Current", "year": "2025", "state_code": "99",
      "limit": "100", "page": "1", "Format": "JSON"}),
    # WPI
    ("wpi_base_years", "/api/wpi/getWpiBaseYear", {}),
    ("wpi_filters_2223", "/api/wpi/getWpiData", {"base_year": "2022-23"}),
    ("wpi2223_2026", "/api/wpi/getWpiRecords",
     {"base_year": "2022-23", "year": "2026", "limit": "100", "page": "1", "Format": "JSON"}),
    ("wpi2223_limit1000", "/api/wpi/getWpiRecords",
     {"base_year": "2022-23", "year": "2026", "limit": "1000", "page": "1", "Format": "JSON"}),
]


def get(path, params):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
            return url, r.status, r.read()
    except urllib.error.HTTPError as e:
        return url, e.code, e.read()
    except Exception as e:  # noqa: BLE001
        return url, None, str(e).encode()


def records(obj):
    """Find the first list of row objects anywhere near the top of a response."""
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("data", "records", "rows", "result", "results"):
            v = obj.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                inner = records(v)
                if inner:
                    return inner
    return []


def latest(rows):
    best = None
    for r in rows:
        if not isinstance(r, dict):
            continue
        y = r.get("year") or r.get("Year")
        m = r.get("month_code") or r.get("month") or r.get("Month")
        key = (str(y), str(m))
        if y and (best is None or key > best):
            best = key
    return best


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    for name, path, params in CALLS:
        url, status, body = get(path, params)
        entry = {"name": name, "url": url, "status": status, "bytes": len(body)}
        try:
            obj = json.loads(body)
            (out / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=1)[:3_000_000])
            rows = records(obj)
            entry["records"] = len(rows)
            if isinstance(obj, dict):
                entry["top_keys"] = sorted(obj.keys())
                for k in ("totalRecords", "total", "count", "meta_data", "msg", "message", "statusCode"):
                    if k in obj:
                        entry[k] = obj[k]
            if rows and isinstance(rows[0], dict):
                entry["row_keys"] = sorted(rows[0].keys())
                entry["first_row"] = rows[0]
                entry["latest"] = latest(rows)
        except ValueError:
            (out / f"{name}.txt").write_bytes(body[:3_000_000])
            entry["text_head"] = body[:400].decode("utf-8", "replace")
        summary.append(entry)
        print(json.dumps({k: entry.get(k) for k in ("name", "status", "records", "latest")}))
        time.sleep(1)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main(*sys.argv[1:])
