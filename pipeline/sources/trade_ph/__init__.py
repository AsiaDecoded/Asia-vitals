"""Philippines merchandise trade: Philippine Statistics Authority, OpenSTAT (PXWeb), as published, US$.

One table per year, commodity x country x month: exports FOB (DB/2L/IMT/FOB, 1991-) and imports CIF (DB/2L/IMT/CIF).
  totals and partners: Commodity eliminated (sum), every country; world = sum of all countries (calculated);
                       EU = sum of the 27 current members (calculated)
  HS lines: commodity codes starting with 85, 8419, 8470, 8471, 8472, 8473 (exports, from 2012) and 2709, 2710
            (imports, from 2010), Country eliminated (all countries)
Values in US$ (PSA tables are in US$); scaled to US$ million.
Backfill by year, stored in raw/trade/ph/store.json.gz; each run fetches up to BUDGET missing tables and re-fetches the
current and previous year.
"""
import json
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
BUDGET = 60
COUNTRY = {"United States Of America": "US", "People'S Republic Of China": "CN", "Hong Kong, China": "HK", "Hong Kong": "HK", "Japan": "JP",
           "Republic Of China (Taiwan)": "TW", "Republic Of Korea": "KR", "India": "IN", "Indonesia": "ID", "Malaysia": "MY",
           "Singapore": "SG", "Thailand": "TH", "Vietnam": "VN",
           "Austria": "AT", "Belgium": "BE", "Bulgaria": "BG", "Croatia": "HR", "Cyprus": "CY", "Czech Republic (Czechoslovakia)": "CZ", "Czech Republic": "CZ",
           "Denmark": "DK", "Estonia": "EE", "Finland": "FI", "France": "FR", "Germany": "DE", "Greece": "GR", "Hungary": "HU",
           "Ireland": "IE", "Italy": "IT", "Latvia": "LV", "Lithuania": "LT", "Luxembourg": "LU", "Malta": "MT",
           "Netherlands": "NL", "Poland": "PL", "Portugal": "PT", "Romania": "RO", "Slovak Republic (Slovakia)": "SK", "Slovakia": "SK", "Slovenia": "SI",
           "Spain": "ES", "Sweden": "SE"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def req(url, body=None, tries=4):
    err = None
    for i in range(tries):
        try:
            data = json.dumps(body).encode() if body is not None else None
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=UA), timeout=300) as r:
                return json.loads(r.read().decode("utf-8-sig"))
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(4 * (i + 1))
    raise RuntimeError(f"OpenSTAT {url}: {err!r}")


def tables():
    out = {}
    for flow, folder in (("exports", "FOB"), ("imports", "CIF")):
        for x in req(BASE + folder):
            y = "".join(ch for ch in x["text"][-5:] if ch.isdigit())
            if x.get("type") == "t" and len(y) == 4:
                out[(flow, int(y))] = f"{folder}/{x['id']}"
    return out


def query(path, by_country, prefixes=None):
    meta = req(BASE + path)
    q = []
    for v in meta["variables"]:
        code = v["code"]
        if code.lower().startswith("commodity"):
            if prefixes:
                q.append({"code": code, "selection": {"filter": "all", "values": [p + "*" for p in prefixes]}})
        elif code.lower() == "country":
            if by_country:
                q.append({"code": code, "selection": {"filter": "all", "values": ["*"]}})
        else:
            q.append({"code": code, "selection": {"filter": "all", "values": ["*"]}})
    return req(BASE + path, {"query": q, "response": {"format": "json-stat2"}})


def cells(js):
    """[(dims dict label, value)] from json-stat2."""
    ids, size = js["id"], js["size"]
    labels = [[None] * n for n in size]
    for k, d in enumerate(ids):
        cat = js["dimension"][d]["category"]
        for code, pos in cat["index"].items():
            labels[k][pos] = (code, cat.get("label", {}).get(code, code))
    vals = js["value"]
    out = []
    for i, v in enumerate(vals if isinstance(vals, list) else []):
        if v is None:
            continue
        rem, idx = i, []
        for n in reversed(size):
            idx.append(rem % n)
            rem //= n
        idx.reverse()
        out.append(({ids[k]: labels[k][idx[k]] for k in range(len(ids))}, v))
    return out


def update(force=False, **_):
    folder = trade.OUT / "ph"
    state = read_json(folder / "release.json", {}) or {}
    st = trade.Store("ph")
    tabs = tables()
    this = max(y for _, y in tabs)
    for (flow, y), path in sorted(tabs.items(), key=lambda kv: -kv[0][1]):
        refresh = y >= this - 1
        st.get(f"{flow}:C:{y}", lambda: query(path, True), refresh=refresh, budget=BUDGET)
        if flow == "exports" and y >= 2012:
            st.get(f"{flow}:HS:{y}", lambda: {p: query(path, False, [p]) for p in HS_EXP}, refresh=refresh, budget=BUDGET)
        if flow == "imports" and y >= 2010:
            st.get(f"{flow}:HS:{y}", lambda: {p: query(path, False, [p]) for p in HS_IMP}, refresh=refresh, budget=BUDGET)
    st.save()
    rows = []
    for key, js in st.data.items():
        flow, kind, y = key.split(":")
        parts = js.items() if kind == "HS" else [(None, js)]
        for hs, j in parts:
            acc = {}
            for dims, v in cells(j):
                per = next((lab for d, (c, lab) in dims.items() if d.lower() == "period"), None)
                if per not in MONTHS:
                    continue
                d = f"{y}-{MONTHS.index(per) + 1:02d}-01"
                if kind == "C":
                    cname = next((lab for dd, (c, lab) in dims.items() if dd.lower() == "country"), "")
                    acc[d] = acc.get(d, 0.0) + v
                    iso = COUNTRY.get(cname)
                    if iso:
                        rows.append({"economy": "PH", "flow": flow, "partner": iso, "product": "TOTAL", "date": d,
                                     "value": round(v / 1e6, 6), "unit": "USD million", "usd_mn": round(v / 1e6, 6),
                                     "usd_calculated": "", "series": f"OpenSTAT {flow} {cname}"})
                else:
                    acc[d] = acc.get(d, 0.0) + v
            for d, tot in acc.items():
                rows.append({"economy": "PH", "flow": flow, "partner": "WLD", "product": "TOTAL" if kind == "C" else f"HS{hs}",
                             "date": d, "value": round(tot / 1e6, 6), "unit": "USD million", "usd_mn": round(tot / 1e6, 6),
                             "usd_calculated": "", "series": f"OpenSTAT {flow}: sum of all " + ("countries" if kind == "C" else f"commodity codes {hs}*")})
    if not rows:
        raise CheckFailed(["no data from OpenSTAT"])
    rows += trade.eu_sum(rows, [])
    last = trade.latest(rows)
    complete = all(f"{f}:C:{y}" in st.data for f, y in tabs)
    folder = trade.write("ph", rows)
    code = f"T{last[:7]}" + ("" if complete else f"b{len(st.data)}")
    write_release(folder, {"code": code, "label": last[:7], "latest_month": last, "source": NAME, "backfill_complete": complete,
                           "table": "PSA OpenSTAT DB/2L/IMT/FOB and CIF yearly tables"}, [], len(rows), {"fetched": st.fetched})
    return {"updated": True, "code": code, "summary": f"{last[:7]}: {len(rows)} rows, {st.fetched} tables" + ("" if complete else " (backfill continuing)")}
