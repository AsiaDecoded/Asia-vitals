"""India merchandise trade: Department of Commerce, TradeStat Monthly Export Import Data Bank (tradestat.commerce.gov.in
/meidb), as published, US$ million (provisional figures for the latest months, revised later). From Jan 2018 (the
data bank's first year; national monthly partner and HS data before 2018 are not free).

Each query is a form post (a page token and session cookie first), answered as an HTML table for one month:
  commoditywise_export / commoditywise_import, HS 2-digit level: total, and chapter 85 (exports)
  commoditywise_export, HS 4-digit level: 8413, 8419, 8470, 8471, 8472, 8473
  commoditywise_import, HS 4-digit level: 2709 (crude oil), 2710 (petroleum products)
  country_wise_all_commodities_export / _import, for each of the 12 partners: the "Total" row
Backfill by month, stored in raw/trade/in/store.json.gz; each run fetches up to BUDGET missing queries and re-fetches
the latest four months.
"""
import http.cookiejar
import io
import re
import time
import urllib.parse
import urllib.request

from core import trade
from core.common import CheckFailed, read_json, write_release

NAME = "trade_in"
DESCRIPTION = "India merchandise trade (Commerce TradeStat, US$ million, 2018-): totals, partners, HS lines, oil"
BASE = "https://tradestat.commerce.gov.in/meidb/"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
FIRST = "2018-01"
COUNTRIES = {"US": "423", "CN": "77", "HK": "179", "JP": "205", "TW": "75", "KR": "217", "ID": "187", "MY": "245",
             "PH": "323", "SG": "359", "TH": "397", "VN": "437"}
HS4_EXP = ["8413", "8419", "8470", "8471", "8472", "8473"]
HS4_IMP = ["2709", "2710"]
BUDGET = 400
_S = {}


def session():
    if "op" not in _S:
        cj = http.cookiejar.CookieJar()
        _S["op"] = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    return _S["op"]


def post(page, fields, tries=4):
    err = None
    for i in range(tries):
        try:
            op = session()
            html = op.open(urllib.request.Request(BASE + page, headers=UA), timeout=90).read().decode("utf-8", "replace")
            tok = re.search(r'name="_token"\s+value="([^"]+)"', html)
            if not tok:
                raise RuntimeError("no form token")
            body = urllib.parse.urlencode({"_token": tok.group(1), **fields}).encode()
            h = {**UA, "Content-Type": "application/x-www-form-urlencoded", "Referer": BASE + page}
            return op.open(urllib.request.Request(BASE + page, data=body, headers=h), timeout=120).read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            err = e
            _S.clear()
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"TradeStat {page}: {err!r}")


def table(html):
    """[(hs code, label, value for the month)] from the result table (first value column = the month asked)."""
    import pandas as pd  # noqa: PLC0415
    try:
        t = pd.read_html(io.StringIO(html))[0]
    except ValueError:
        return []
    cols = [str(c) for c in t.columns]
    vcol = next((c for c in cols if re.search(r"\(F\)|\(P\)|\(R\)|-20\d\d", c)), None)
    mcols = [c for c in cols if re.match(r"[A-Z][a-z]{2}-20\d\d", c.strip())]
    if len(mcols) >= 2:
        vcol = mcols[1]                      # [same month last year, this month]
    out = []
    for _, r in t.iterrows():
        try:
            out.append((str(r.get("HSCode", r.iloc[1])).strip(), str(r.iloc[2]).strip(), float(str(r[vcol]).replace(",", ""))))
        except (ValueError, KeyError):
            continue
    return out


def queries(ym):
    y, m = ym[:4], str(int(ym[5:7]))
    out = []
    for flow, page, px in (("exports", "commoditywise_export", "dd"), ("imports", "commoditywise_import", "imdd")):
        for lev in ("2", "4"):
            out.append((f"{flow}:HS{lev}:{ym}", page, {f"{px}Month": m, f"{px}Year": y, f"{px}CommodityLevel": lev,
                                                        f"{px}ReportVal": "1", f"{px}ReportYear": "2", "comlev": "all"}))
    for iso, c in COUNTRIES.items():
        out.append((f"exports:{iso}:{ym}", "country_wise_all_commodities_export",
                    {"cwcexddMonth": m, "cwcexddYear": y, "cwcexallcount": c, "cwcexddCommodityLevel": "2",
                     "cwcexddReportVal": "1", "cwcexddReportYear": "2"}))
        out.append((f"imports:{iso}:{ym}", "country_wise_all_commodities_import",
                    {"cwcimMonth": m, "cwcimYear": y, "cwcimallcount": c, "cwcimCommodityLevel": "2",
                     "cwcimReportVal": "1", "cwcimReportYear": "2"}))
    return out


def update(force=False, **_):
    folder = trade.OUT / "in"
    st = trade.Store("in")
    today = time.strftime("%Y-%m")
    last_avail = trade.shift(today, -2)
    recent = set(trade.months(trade.shift(last_avail, -3), last_avail))
    fails = []
    for ym in reversed(trade.months(FIRST, last_avail)):
        for key, page, fields in queries(ym):
            if len(fails) >= 15:
                break
            try:
                st.get(key, lambda: table(post(page, fields)), refresh=ym in recent, budget=BUDGET)
            except Exception as e:  # noqa: BLE001
                fails.append(f"{key}: {str(e)[:120]}")
    st.save()
    rows = []
    for key, tab in st.data.items():
        flow, kind, ym = key.split(":")
        d = ym + "-01"
        for code, label, v in tab or []:
            if kind in ("HS2", "HS4"):
                if code.lower() == "total" and kind == "HS2":
                    prod = "TOTAL"
                elif (kind == "HS2" and code == "85" and flow == "exports") or (kind == "HS4" and code in (HS4_EXP if flow == "exports" else HS4_IMP)):
                    prod = f"HS{code}"
                else:
                    continue
                rows.append({"economy": "IN", "flow": flow, "partner": "WLD", "product": prod, "date": d, "value": v,
                             "unit": "USD million", "usd_mn": v, "usd_calculated": "", "series": f"TradeStat commoditywise {kind} {code} {label[:50]}"})
            elif code.lower() == "total":
                rows.append({"economy": "IN", "flow": flow, "partner": kind, "product": "TOTAL", "date": d, "value": v,
                             "unit": "USD million", "usd_mn": v, "usd_calculated": "", "series": f"TradeStat country_wise_all_commodities {kind}"})
    if not rows:
        raise CheckFailed(["TradeStat: nothing read"] + fails[:5])
    last = trade.latest(rows)
    complete = all(k in st.data for ym in trade.months(FIRST, last_avail) for k, _, _ in queries(ym))
    folder = trade.write("in", rows)
    code = f"T{last[:7]}" + ("" if complete else f"b{len(st.data)}")
    write_release(folder, {"code": code, "label": last[:7], "latest_month": last, "source": NAME, "backfill_complete": complete,
                           "table": "Commerce TradeStat MEIDB"}, fails[:10], len(rows), {"fetched": st.fetched})
    return {"updated": True, "code": code, "summary": f"{last[:7]}: {len(rows)} rows, {st.fetched} queries" + ("" if complete else " (backfill continuing)")}
