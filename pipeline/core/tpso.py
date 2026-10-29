"""Client for the Trade Policy and Strategy Office's Open API (Thailand, Ministry of Commerce), no key.

Documented at index.tpso.go.th/document: base https://index-api.tpso.go.th
  GET  /OpenApi/<Family>/Month/MasterData  -> types (regions or index sets), commodities, dataAvailablePeriods
  POST /OpenApi/<Family>/Month  {yearBase, year, month, type, commodities: []}  -> every commodity for one month
Families: Cpig (CPI, general), Cpil (low-income households), Cpiu (non-municipal areas), Ppi (types CPA, SOP),
Imex (types EXI, IMI). Years are Buddhist Era (CE + 543), both in requests and responses.
Rows: type, typeName, commodityCode, commodityNameTH, month, year, yearBase, index, change (m/m %),
changeYear (y/y %), changeAVG (year-to-date average on a year earlier, %), level, createdAt (UTC).
Calls take one to two seconds each.
"""
import concurrent.futures as cf
import json
import time
import urllib.error
import urllib.request

BASE = "https://index-api.tpso.go.th"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,th;q=0.8",
    "Origin": "https://index.tpso.go.th",
    "Referer": "https://index.tpso.go.th/",
}
BE = 543
WORKERS = 3


def _request(path, body=None, tries=4):
    data = json.dumps(body).encode() if body is not None else None
    hdr = {**HEADERS, **({"Content-Type": "application/json"} if data else {})}
    last = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(BASE + path, data=data, headers=hdr), timeout=90) as r:
                raw = r.read().decode("utf-8-sig")
            try:
                return json.loads(raw)
            except json.JSONDecodeError as e:  # the API answers some bad requests with a Thai sentence
                raise RuntimeError(f"TPSO {path} {body}: not JSON: {raw[:200]!r}") from e
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"TPSO {e.code} for {path} {body}: {e.read()[:300]!r}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"TPSO failed for {path} {body}: {last!r}")


def master(family):
    return _request(f"/OpenApi/{family}/Month/MasterData")


def month(family, typ, year_base_be, year, mon):
    """Every commodity for one month (year in CE). Returns the API's rows unchanged."""
    return _request(f"/OpenApi/{family}/Month", {"yearBase": year_base_be, "year": year + BE, "month": mon,
                                                  "type": typ, "commodities": []})


def months(family, typ, year_base_be, ym_list):
    """{'YYYY-MM': rows} for many months, a few calls at a time."""
    def one(ym):
        y, m = int(ym[:4]), int(ym[5:7])
        return ym, month(family, typ, year_base_be, y, m)
    out = {}
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        for ym, rows in ex.map(one, ym_list):
            out[ym] = rows
    return out


def month_range(first, last):
    """['YYYY-MM', ...] from first to last inclusive."""
    y, m = int(first[:4]), int(first[5:7])
    out = []
    while f"{y}-{m:02d}" <= last:
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def latest_period(m, year_base_be, typ=None):
    """Latest 'YYYY-MM' (CE) in a MasterData answer for that base (and type, for families that list them per type)."""
    blocks = m if isinstance(m, list) else [m]
    best = None
    for b in blocks:
        if typ and isinstance(m, list) and b.get("type") != typ:
            continue
        for p in b.get("dataAvailablePeriods", []):
            if p.get("yearBase") == year_base_be and p.get("periodType") == "month":
                ym = f"{p['endYear'] - BE}-{p['endPeriod']:02d}"
                best = max(best or ym, ym)
    return best


def first_period(m, year_base_be, typ=None):
    blocks = m if isinstance(m, list) else [m]
    best = None
    for b in blocks:
        if typ and isinstance(m, list) and b.get("type") != typ:
            continue
        for p in b.get("dataAvailablePeriods", []):
            if p.get("yearBase") == year_base_be and p.get("periodType") == "month":
                ym = f"{p['startYear'] - BE}-{p['startPeriod']:02d}"
                best = min(best or ym, ym)
    return best
