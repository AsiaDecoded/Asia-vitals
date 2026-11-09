"""Thailand merchandise trade: Ministry of Commerce (MOC) trade report API (tradereport.moc.go.th, customs basis),
as published, US$ (the API also gives baht).

  /api/summarycountries?year=&month=&limit=           exports and imports by country, one row per country
  /api/exportharmonizecountries?hs_code=&year=&month= exports of an HS heading/chapter by country
  /api/importharmonizecountries?hs_code=&year=&month= imports of an HS heading by country
World = sum of all country rows (MOC publishes no world row); EU = sum of the 27 current members (calculated).
HS lines as in the CEIC set: 85, 8419, 8470, 8471, 8472, 8473 (exports, from 2012); imports HS 2709 (crude oil) and
2710 (petroleum products), from 2010. Months whose rows are all zero (placeholders before MOC fills them) are skipped.
Backfill: raw responses are stored (raw/trade/th/store.json.gz); each run fetches up to BUDGET missing months and
re-fetches the latest three.
"""
import json
import time
import urllib.request

from core import trade
from core.common import CheckFailed, read_json, write_release

NAME = "trade_th"
DESCRIPTION = "Thailand merchandise trade (MOC trade report API, US$): totals, partners, HS lines, oil imports"
API = "https://tradereport.moc.go.th/api/"
UA = {"User-Agent": "Mozilla/5.0 (asia-vitals data pipeline; github.com/AsiaDecoded)", "Accept": "application/json"}
FIRST, HS_FIRST, OIL_FIRST = "1990-01", "2012-01", "2010-01"
HS_EXP = ["85", "8419", "8470", "8471", "8472", "8473"]
HS_IMP = ["2709", "2710"]
BUDGET = 900


def call(path, tries=4):
    err = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(API + path, headers=UA), timeout=60) as r:
                return json.loads(r.read().decode("utf-8") or "[]")
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"MOC {path}: {err!r}")


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def row(flow, partner, product, d, usd, series):
    return {"economy": "TH", "flow": flow, "partner": partner, "product": product, "date": d, "value": round(usd / 1e6, 6),
            "unit": "USD million", "usd_mn": round(usd / 1e6, 6), "usd_calculated": "", "series": series}


def update(force=False, **_):
    folder = trade.OUT / "th"
    state = read_json(folder / "release.json", {}) or {}
    st = trade.Store("th")
    today = time.strftime("%Y-%m")
    recent = set(trade.months(trade.shift(today, -4), today))
    for ym in reversed(trade.months(FIRST, today)):          # latest first, so recent months are never starved
        y, m = int(ym[:4]), int(ym[5:7])
        q = f"year={y}&month={m}&limit=10000"
        st.get(f"sum:{ym}", lambda: call(f"summarycountries?{q}"), refresh=ym in recent, budget=BUDGET)
        if ym >= HS_FIRST:
            for hs in HS_EXP:
                st.get(f"exp:{hs}:{ym}", lambda: call(f"exportharmonizecountries?hs_code={hs}&{q}"), refresh=ym in recent, budget=BUDGET)
        if ym >= OIL_FIRST:
            for hs in HS_IMP:
                st.get(f"imp:{hs}:{ym}", lambda: call(f"importharmonizecountries?hs_code={hs}&{q}"), refresh=ym in recent, budget=BUDGET)
    st.save()
    rows = []
    for key, resp in st.data.items():
        if not resp:
            continue
        kind, ym = key.split(":")[0], key.rsplit(":", 1)[1]
        d = ym + "-01"
        if kind == "sum":
            for flow, fld in (("exports", "value_usd_export"), ("imports", "value_usd_import")):
                tot = sum(f(x.get(fld)) for x in resp)
                if not tot:
                    continue
                rows.append(row(flow, "WLD", "TOTAL", d, tot, "summarycountries: sum of all countries"))
                for x in resp:
                    c = (x.get("country_code") or "").upper()
                    if c in trade.PARTNERS or c in trade.EU27:
                        rows.append(row(flow, c, "TOTAL", d, f(x.get(fld)), f"summarycountries {c} {x.get('country_name_en', '')}"))
        else:
            hs = key.split(":")[1]
            flow = "exports" if kind == "exp" else "imports"
            tot = sum(f(x.get("value_usd")) for x in resp)
            if tot:
                rows.append(row(flow, "WLD", f"HS{hs}", d, tot, f"{'export' if kind == 'exp' else 'import'}harmonizecountries hs_code={hs}: sum of all countries"))
    rows = [r for r in rows if r["partner"] != "WLD" or r["value"]]
    rows += trade.eu_sum(rows, [])
    if not rows:
        raise CheckFailed(["no data"])
    last = trade.latest(rows)
    errors = []
    for ym in trade.months("1995-01", last[:7]):
        if not any(r["date"] == ym + "-01" and r["partner"] == "WLD" and r["product"] == "TOTAL" for r in rows):
            errors.append(f"total missing for {ym}")
            break
    complete = not any(k for k in [f"sum:{ym}" for ym in trade.months(FIRST, last[:7])] if k not in st.data)
    folder = trade.write("th", rows)
    code = f"T{last[:7]}" + ("" if complete else f"b{len(st.data)}")
    write_release(folder, {"code": code, "label": last[:7], "latest_month": last, "source": NAME, "backfill_complete": complete,
                           "table": "MOC tradereport API: summarycountries, exportharmonizecountries, importharmonizecountries"},
                  errors, len(rows), {"fetched": st.fetched})
    return {"updated": True, "code": code, "summary": f"{last[:7]}: {len(rows)} rows, {st.fetched} calls" + ("" if complete else " (backfill continuing)")}
