"""Singapore merchandise trade: Enterprise Singapore via SingStat Table Builder (no key), as published, S$ thousand.

  M451001  merchandise trade by commodity section: total exports, domestic exports, re-exports, imports (from 1976)
  M451491  imports by region and market (from 2003)
  M451501  domestic exports by region and market (from 2003)
  M451511  re-exports by region and market (from 2003)
           exports by market = domestic exports + re-exports (calculated); EU = sum of the 27 current members (calc.)
  M450981  domestic exports of major non-oil products: Total Electronic Products (from 1997)
  M451131  re-exports of machinery and equipment: Total Electronic Products (from 1999)
  T010001  trade by commodity and market (detailed dataset, AHTN, from 2013): world imports of HS 2709 and 2710,
           world exports of HS 85, 8419, 8470, 8471, 8472, 8473; one month per request (timeFilter, markets=WORLD)
US$: BIS monthly average S$ rate (calculated). Singapore's trade with Indonesia is not published before 2003.
"""
import hashlib
import json
import re
import time
import urllib.parse

from core import singstat, trade
from core.common import CheckFailed, read_json, write_release

NAME = "trade_sg"
DESCRIPTION = "Singapore merchandise trade (SingStat, S$): totals, partners (2003-), electronics, HS lines and oil (2013-)"
MON = {m: i + 1 for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
MARKETS = {"Total All Markets": "WLD", "United States Of America": "US", "Mainland China": "CN", "Hong Kong": "HK", "Japan": "JP",
           "Taiwan": "TW", "Republic Of Korea": "KR", "India": "IN", "Indonesia": "ID", "Malaysia": "MY", "Philippines": "PH",
           "Thailand": "TH", "Viet Nam": "VN",
           "Austria": "AT", "Belgium": "BE", "Bulgaria": "BG", "Croatia": "HR", "Cyprus": "CY", "Czech Republic": "CZ",
           "Czechia": "CZ", "Denmark": "DK", "Estonia": "EE", "Finland": "FI", "France": "FR", "Germany": "DE", "Greece": "GR",
           "Hungary": "HU", "Republic Of Ireland": "IE", "Ireland": "IE", "Italy": "IT", "Latvia": "LV", "Lithuania": "LT",
           "Luxembourg": "LU", "Malta": "MT", "Netherlands": "NL", "Poland": "PL", "Portugal": "PT", "Romania": "RO",
           "Slovak Republic": "SK", "Slovakia": "SK", "Slovenia": "SI", "Spain": "ES", "Sweden": "SE"}
BY_MARKET = {"M451491": "imports", "M451501": "domestic_exports", "M451511": "re_exports"}
HS_EXP = ["85", "8419", "8470", "8471", "8472", "8473"]
HS_IMP = ["2709", "2710"]
BUDGET = 80


def f(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def series(tid):
    t = singstat.table(tid)
    out = {}
    for r in t["rows"]:
        s = {}
        for c in r["columns"]:
            parts = c["key"].split()
            if len(parts) == 2 and parts[1] in MON and f(c["value"]) is not None:
                s[f"{parts[0]}-{MON[parts[1]]:02d}-01"] = f(c["value"])
        out[(r.get("seriesNo"), (r.get("rowText") or "").strip())] = s
    return out


def row(flow, partner, product, d, v, s):
    return {"economy": "SG", "flow": flow, "partner": partner, "product": product, "date": d, "value": v, "unit": "SGD thousand",
            "usd_mn": None, "usd_calculated": "", "series": s}


def detail_month(ym):
    """World rows of T010001 for one month (all trade types, all HS levels), paged by cursor."""
    y, m = ym[:4], [k for k, v in MON.items() if v == int(ym[5:7])][0]
    rows, cursor = [], None
    base = f"{singstat.BASE}/tabledata/T010001?" + urllib.parse.urlencode({"timeFilter": f"{y} {m}", "markets": "WORLD"})
    for _ in range(20):
        js = singstat._get(base + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else ""))
        d = js.get("Data") or {}
        for r in d.get("rows") or []:
            h2, h4 = (r.get("hs2Products") or "")[:2], (r.get("hs4Products") or "")[:4]
            if r.get("hs6Products") or r.get("hs8Products"):
                continue
            if (h4 and h4 in HS_EXP + HS_IMP) or (not h4 and h2 in ("85",)):
                rows.append({"tt": r.get("tradeType"), "hs": h4 or h2, "v": f(r.get("value"))})
        cursor = d.get("nextCursor") if d.get("isMore") else None
        if not cursor:
            break
    return rows


def update(force=False, **_):
    folder = trade.OUT / "sg"
    state = read_json(folder / "release.json", {}) or {}
    rows = []
    agg = series("M451001")
    names = [t for (_n, t) in agg]
    for (no, text), s in agg.items():
        t = text.lower()
        flow = None
        if "." not in (no or "") or no.count(".") == 0:
            if "re-export" in t:
                flow = "re_exports"
            elif "domestic export" in t and "non-oil" not in t and "oil" not in t:
                flow = "domestic_exports"
            elif "export" in t and "domestic" not in t:
                flow = "exports"
            elif "import" in t:
                flow = "imports"
        if flow and not any(r["flow"] == flow for r in rows):
            rows += [row(flow, "WLD", "TOTAL", d, v, f"M451001 {text}") for d, v in s.items()]
    if len({r["flow"] for r in rows}) < 4:
        raise CheckFailed([f"M451001: total rows not all found; rows are {names[:20]}"])
    by = {}
    for tid, flow in BY_MARKET.items():
        for (no, text), s in series(tid).items():
            iso = MARKETS.get(text)
            if not iso or iso == "WLD":
                continue
            for d, v in s.items():
                rows.append(row(flow, iso, "TOTAL", d, v, f"{tid} {text}"))
                if flow != "imports":
                    by.setdefault((iso, d), {})[flow] = v
    for (iso, d), x in by.items():
        if "domestic_exports" in x and "re_exports" in x:
            rows.append(row("exports", iso, "TOTAL", d, x["domestic_exports"] + x["re_exports"], "M451501 + M451511 (calculated)"))
    for tid, flow in (("M450981", "domestic_exports"), ("M451131", "re_exports")):
        for (no, text), s in series(tid).items():
            if text == "Total Electronic Products":
                rows += [row(flow, "WLD", "electronic_products", d, v, f"{tid} {text}") for d, v in s.items()]
    st = trade.Store("sg")
    today = time.strftime("%Y-%m")
    recent = set(trade.months(trade.shift(today, -3), today))
    for ym in reversed(trade.months("2013-01", today)):
        st.get(f"T010001:{ym}", lambda: detail_month(ym), refresh=ym in recent, budget=BUDGET)
    st.save()
    tt = {"EXPORTS": "exports", "IMPORTS": "imports", "DOMESTIC EXPORTS": "domestic_exports", "RE-EXPORTS": "re_exports"}
    for key, recs in st.data.items():
        d = key.split(":")[1] + "-01"
        for r in recs or []:
            flow = tt.get(r["tt"])
            if r["v"] is None or not flow:
                continue
            if (r["hs"] in HS_IMP and flow == "imports") or (r["hs"] in HS_EXP and flow in ("exports", "domestic_exports", "re_exports")):
                rows.append(row(flow, "WLD", f"HS{r['hs']}", d, r["v"], f"T010001 {r['tt']} WORLD HS {r['hs']}"))
    rows = [r for r in rows if r["value"] is not None]
    trade.to_usd(rows, "sg", 1000)
    rows += trade.eu_sum(rows, [])
    last = trade.latest(rows)
    folder = trade.write("sg", rows)
    code = f"T{last[:7]}h{len(st.data)}"
    write_release(folder, {"code": code, "label": last[:7], "latest_month": last, "source": NAME,
                           "table": "SingStat M451001, M451491, M451501, M451511, M450981, M451131, T010001"}, [], len(rows), {"fetched": st.fetched})
    return {"updated": True, "code": code, "summary": f"{last[:7]}: {len(rows)} rows, {st.fetched} detail months"}
