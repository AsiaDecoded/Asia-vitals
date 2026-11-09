"""South Korea merchandise trade: Korea Customs Service figures as republished by the Bank of Korea, ECOS
(customs-clearance basis), as published, thousand US$.

  901Y118  exports and imports, total (from 2000)
  901Y121  exports and imports by country (from 1966): US, CN, JP, TW, HK, SG, IN, MY, ID, TH, PH, VN (and DE, NL, FR,
           IT, PL; ECOS carries no EU total and too few members to sum one)
World before 2000 is not in these tables. HS-line exports, KCS's electronic products grouping and crude oil and fuel
imports are in KCS's own API on data.go.kr (needs a free key), not in ECOS: not collected yet.
ECOS is read with the repository key if set, else ECOS's public sample key (10 rows per call): each month is one
query, stored in raw/trade/kr/store.json.gz and backfilled over runs (BUDGET months per run).
"""
import time

from core import ecos, trade
from core.common import CheckFailed, read_json, write_release

NAME = "trade_kr"
DESCRIPTION = "South Korea merchandise trade (KCS via BoK ECOS, US$): totals, partners"
FIRST = "1990-01"
PARTNERS = {"US", "CN", "JP", "TW", "HK", "SG", "IN", "MY", "ID", "TH", "PH", "VN"}
FLOW = {"T002": "exports", "T004": "imports"}
BUDGET = 120


def update(force=False, **_):
    folder = trade.OUT / "kr"
    st = trade.Store("kr")
    today = time.strftime("%Y-%m")
    recent = set(trade.months(trade.shift(today, -3), today))
    for ym in reversed(trade.months(FIRST, today)):
        e = ym.replace("-", "")
        st.get(f"121:{ym}", lambda: ecos.month_all("901Y121", e), refresh=ym in recent, budget=BUDGET)
        if ym >= "2000-01":
            st.get(f"118:{ym}", lambda: ecos.month_all("901Y118", e), refresh=ym in recent, budget=BUDGET)
    st.save()
    rows = []
    for key, data in st.data.items():
        tab, ym = key.split(":")
        for r in data or []:
            codes = [r.get("ITEM_CODE1"), r.get("ITEM_CODE2")]
            flow = next((FLOW[c] for c in codes if c in FLOW), None)
            other = next((c for c in codes if c and c not in FLOW), None)
            try:
                v = float(r.get("DATA_VALUE"))
            except (TypeError, ValueError):
                continue
            if not flow:
                continue
            if tab == "118":
                partner, s = "WLD", "901Y118 " + (r.get("ITEM_NAME1") or "")
            else:
                partner = other
                if partner not in PARTNERS:
                    continue
                s = f"901Y121 {r.get('ITEM_NAME1', '')} {r.get('ITEM_NAME2', '')}"
            unit = r.get("UNIT_NAME") or "천달러"
            scale = 1e-3 if "천" in unit else (1e-6 if unit in ("달러", "US$") else 1.0)
            rows.append({"economy": "KR", "flow": flow, "partner": partner, "product": "TOTAL", "date": ym + "-01", "value": v,
                         "unit": f"USD ({unit})", "usd_mn": round(v * scale, 6), "usd_calculated": "", "series": s})
    if not rows:
        raise CheckFailed(["ECOS: no trade rows"])
    last = trade.latest(rows, partner="US")
    complete = all(f"121:{ym}" in st.data for ym in trade.months(FIRST, today))
    folder = trade.write("kr", rows)
    code = f"T{last[:7]}" + ("" if complete else f"b{len(st.data)}")
    write_release(folder, {"code": code, "label": last[:7], "latest_month": last, "source": NAME, "backfill_complete": complete,
                           "table": "BoK ECOS 901Y118, 901Y121 (KCS)"}, [], len(rows), {"fetched": st.fetched})
    return {"updated": True, "code": code, "summary": f"{last[:7]}: {len(rows)} rows, {st.fetched} months" + ("" if complete else " (backfill continuing)")}
