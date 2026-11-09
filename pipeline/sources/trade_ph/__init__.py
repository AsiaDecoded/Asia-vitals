"""Philippines merchandise trade: Philippine Statistics Authority, OpenSTAT (PXWeb, DB/2L/IMT), as published, US$.

  totals:    SUM/0012L4DFTS0 "Philippine Total Trade, Imports, Exports ... by Month and Year: 1991-" (US$ million)
  partners:  the yearly tables FOB (exports, commodity x country of destination x month) and CIF (imports, x country of
             origin), US$; one query per year for all commodities and the partner countries, summed over commodities;
             EU = sum of the 27 current members (calculated; only where all 27 appear in that year's table)
  HS lines:  the same yearly tables, commodity codes (AHTN, 11 digits) starting with 85, 8419, 8470, 8471, 8472, 8473
             (exports, from 2012) and 2709, 2710 (imports, from 2010), summed over codes and all countries (calculated)
The tables' commodity dimension is a running index whose labels are the AHTN codes; the index comes from the order of
the codes in the partner query. CSV responses are used (the server's json-stat2 output carries no values).
Backfill by year in raw/trade/ph/store.json.gz (aggregates only); the current and previous year are re-fetched each run.
"""
import csv
import io
import json
import re
import time
import urllib.request

from core import trade
from core.common import CheckFailed, read_json, write_release

NAME = "trade_ph"
DESCRIPTION = "Philippines merchandise trade (PSA OpenSTAT, US$): totals, partners, HS lines, oil imports"
BASE = "https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/2L/IMT/"
UA = {"User-Agent": "Mozilla/5.0 (asia-vitals data pipeline; github.com/AsiaDecoded)", "Content-Type": "application/json"}
HS_EXP = ["85", "8419", "8470", "8471", "8472", "8473"]
HS_IMP = ["2709", "2710"]
BUDGET = 40
CHUNK = 7        # countries per all-commodity query (14 is over the cell limit for the larger import tables)
PATTERNS = [("US", r"^united states"), ("CN", r"^people'?s republic of china"), ("TW", r"taiwan"), ("KR", r"^republic of korea"),
            ("HK", r"^hong kong"), ("JP", r"^japan"), ("TH", r"^thailand"), ("SG", r"^singapore"), ("ID", r"^indonesia"),
            ("MY", r"^malaysia"), ("IN", r"^india$"), ("VN", r"^viet ?nam"),
            ("AT", r"^austria"), ("BE", r"^belgium$"), ("BG", r"^bulgaria"), ("HR", r"^croatia"), ("CY", r"^cyprus"),
            ("CZ", r"^czech"), ("DK", r"^denmark"), ("EE", r"^estonia"), ("FI", r"^finland"), ("FR", r"^france"),
            ("DE", r"^germany"), ("GR", r"^greece"), ("HU", r"^hungary"), ("IE", r"^ireland"), ("IT", r"^italy"),
            ("LV", r"^latvia"), ("LT", r"^lithuania"), ("LU", r"^luxembourg$"), ("MT", r"^malta"), ("NL", r"^netherlands$"),
            ("PL", r"^poland"), ("PT", r"^portugal"), ("RO", r"^romania"), ("SK", r"^slovak"), ("SI", r"^slovenia"),
            ("ES", r"^spain"), ("SE", r"^sweden")]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
WARN = []


def req(url, body=None, tries=4, raw=False):
    err = None
    for i in range(tries):
        try:
            data = json.dumps(body).encode() if body is not None else None
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=UA), timeout=300) as r:
                b = r.read()
                try:
                    t = b.decode("utf-8-sig")
                except UnicodeDecodeError:
                    t = b.decode("cp1252", "replace")
                return t if raw else json.loads(t)
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(4 * (i + 1))
    raise RuntimeError(f"OpenSTAT {url}: {repr(err)[:200]}")


def csv_query(path, query):
    t = req(BASE + path, {"query": query, "response": {"format": "csv"}}, raw=True)
    r = list(csv.reader(io.StringIO(t)))
    hdr = r[0]
    cols = {}
    for j, h in enumerate(hdr):
        m = re.match(r"(\d{4}) ([A-Za-z]+?)P?$", h.strip())
        if m and m.group(2) in MONTHS:
            cols[j] = f"{m.group(1)}-{MONTHS.index(m.group(2)) + 1:02d}"
    return hdr, r[1:], cols


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def tables():
    out = {}
    for flow, folder in (("exports", "FOB"), ("imports", "CIF")):
        for x in req(BASE + folder):
            y = "".join(ch for ch in x["text"][-5:] if ch.isdigit())
            if x.get("type") == "t" and len(y) == 4:
                out[(flow, int(y))] = f"{folder}/{x['id']}"
    return out


def year_aggregates(flow, year, path):
    meta = req(BASE + path)
    var = {v["code"]: v for v in meta["variables"]}
    com = next(c for c in var if c.lower().startswith("commodity"))
    per = next(c for c in var if c.lower() == "period")
    yr = [c for c in var if c.lower() == "year"]
    cv = var["Country"]
    iso_of = {}
    for code, text in zip(cv["values"], cv["valueTexts"]):
        name = re.sub(r"\s+", " ", text).strip().lower()
        iso = next((i for i, p in PATTERNS if re.search(p, name)), None)
        if iso and iso not in iso_of.values():
            iso_of[code] = iso
    base_q = [{"code": per, "selection": {"filter": "all", "values": ["*"]}}] + \
             [{"code": c, "selection": {"filter": "all", "values": ["*"]}} for c in yr]
    partners, order = {}, []
    codes = list(iso_of)
    name_iso = {re.sub(r"\s+", " ", t).strip(): iso_of[c] for c, t in zip(cv["values"], cv["valueTexts"]) if c in iso_of}
    for k in range(0, len(codes), CHUNK):
        hdr, rows, cols = csv_query(path, [{"code": com, "selection": {"filter": "all", "values": ["*"]}},
                                           {"code": "Country", "selection": {"filter": "item", "values": codes[k:k + CHUNK]}}] + base_q)
        for x in rows:
            if len(x) < 2:
                continue
            iso = name_iso.get(re.sub(r"\s+", " ", x[1]).strip())
            if k == 0 and (not order or order[-1] != x[0]):
                order.append(x[0])
            if not iso:
                continue
            acc = partners.setdefault(iso, {})
            for j, ym in cols.items():
                v = num(x[j]) if j < len(x) else None
                if v is not None:
                    acc[ym] = acc.get(ym, 0.0) + v
    hs = {}
    prefixes = HS_EXP if flow == "exports" else HS_IMP
    if year >= (2012 if flow == "exports" else 2010):
        idx = {p: [str(i) for i, c in enumerate(order) if c.startswith(p)] for p in prefixes}
        for p, ids in idx.items():
            if not ids:
                WARN.append(f"{flow} {year}: no commodity codes starting {p}")
                continue
            acc = hs.setdefault(p, {})
            for k in range(0, len(ids), 250):
                hdr, rows, cols = csv_query(path, [{"code": com, "selection": {"filter": "item", "values": ids[k:k + 250]}},
                                                   {"code": "Country", "selection": {"filter": "all", "values": ["*"]}}] + base_q)
                for x in rows:
                    if x and not x[0].startswith(p):
                        raise CheckFailed([f"{flow} {year}: commodity index mismatch ({x[0]} for prefix {p})"])
                    for j, ym in cols.items():
                        v = num(x[j]) if j < len(x) else None
                        if v is not None:
                            acc[ym] = acc.get(ym, 0.0) + v
    return {"partners": partners, "hs": hs, "n_codes": len(order)}



def totals():
    t = req(BASE + "SUM/0012L4DFTS0.px", {"query": [], "response": {"format": "csv"}}, raw=True)
    r = list(csv.reader(io.StringIO(t)))
    out = []
    mon = {m[:3]: i + 1 for i, m in enumerate(MONTHS)}
    for x in r[1:]:
        if len(x) < 4 or x[1] not in mon:
            continue
        for flow, j in (("exports", 2), ("imports", 3)):
            v = num(x[j])
            if v is not None:
                out.append({"economy": "PH", "flow": flow, "partner": "WLD", "product": "TOTAL", "date": f"{x[0][:4]}-{mon[x[1]]:02d}-01",
                            "value": v, "unit": "USD million", "usd_mn": v, "usd_calculated": "",
                            "series": f"OpenSTAT SUM/0012L4DFTS0 {r[0][j]}"})
    return out


def update(force=False, **_):
    folder = trade.OUT / "ph"
    WARN.clear()
    rows = totals()
    if not rows:
        raise CheckFailed(["OpenSTAT SUM/0012L4DFTS0: no rows"])
    st = trade.Store("ph")
    tabs = tables()
    this = max(y for _, y in tabs)
    for (flow, y), path in sorted(tabs.items(), key=lambda kv: -kv[0][1]):
        try:
            st.get(f"{flow}:{y}", lambda: year_aggregates(flow, y, path), refresh=y >= this - 1, budget=BUDGET)
        except CheckFailed:
            raise
        except Exception as e:  # noqa: BLE001
            WARN.append(f"{flow} {y}: {str(e)[:250]}")
    st.save()
    for key, agg in st.data.items():
        flow, y = key.split(":")
        for iso, s in (agg or {}).get("partners", {}).items():
            for ym, v in s.items():
                rows.append({"economy": "PH", "flow": flow, "partner": iso, "product": "TOTAL", "date": ym + "-01",
                             "value": round(v / 1e6, 6), "unit": "USD million", "usd_mn": round(v / 1e6, 6), "usd_calculated": "",
                             "series": f"OpenSTAT {'FOB' if flow == 'exports' else 'CIF'} {y}: sum over commodities"})
        for p, s in (agg or {}).get("hs", {}).items():
            for ym, v in s.items():
                rows.append({"economy": "PH", "flow": flow, "partner": "WLD", "product": f"HS{p}", "date": ym + "-01",
                             "value": round(v / 1e6, 6), "unit": "USD million", "usd_mn": round(v / 1e6, 6), "usd_calculated": "",
                             "series": f"OpenSTAT {'FOB' if flow == 'exports' else 'CIF'} {y}: codes {p}*, all countries (calculated)"})
    rows += trade.eu_sum(rows, sorted(trade.EU27))
    last = trade.latest(rows)
    complete = all(f"{f}:{y}" in st.data for f, y in tabs)
    folder = trade.write("ph", rows)
    code = f"T{last[:7]}" + ("" if complete else f"b{len(st.data)}")
    write_release(folder, {"code": code, "label": last[:7], "latest_month": last, "source": NAME, "backfill_complete": complete,
                           "table": "PSA OpenSTAT DB/2L/IMT SUM/0012L4DFTS0, FOB and CIF yearly tables"}, WARN[:20], len(rows),
                  {"fetched": st.fetched})
    return {"updated": True, "code": code, "warnings": WARN[:5],
            "summary": f"{last[:7]}: {len(rows)} rows, {st.fetched} year tables" + ("" if complete else " (backfill continuing)")}
