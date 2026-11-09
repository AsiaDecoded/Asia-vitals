"""Trade probe round 3 (9 Nov 2026): follow-ups on round 1: tests national trade endpoints for the 12 economies from GitHub Actions.

  python -I pipeline/tools/trade_probe3.py discovery/trade3

Each test: GET (or POST) a URL, record status, size, content type and the first bytes; save the body (capped).
Keys come from the environment (BPS_KEY, ECOS_KEY, ESTAT_APP_ID) and are never written out.
"""
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "discovery/trade3")
OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
KEYS = {k: os.environ.get(k, "") for k in ("BPS_KEY", "ECOS_KEY", "ESTAT_APP_ID")}
LOG = []


def enc(u):
    p = urllib.parse.urlsplit(u)
    return urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(p.path, safe="/%:@()"),
                                    urllib.parse.quote(p.query, safe="=&%,:+/"), ""))


def hide(s):
    for v in KEYS.values():
        if v:
            s = s.replace(v, "<key>")
    return s


def test(name, url, data=None, headers=None, opener=None, cap=3_000_000):
    for k, v in KEYS.items():
        url = url.replace("{" + k + "}", v)
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
    h.update(headers or {})
    t0 = time.time()
    try:
        req = urllib.request.Request(enc(url), data=data, headers=h)
        with (opener or urllib.request.build_opener()).open(req, timeout=90) as r:
            b = r.read(cap)
            ct = r.headers.get("Content-Type", "")
            st = r.status
    except Exception as e:  # noqa: BLE001
        LOG.append(f"FAIL {name}: {hide(str(e))[:200]} ({time.time() - t0:.0f}s) {hide(url)[:160]}")
        return None
    ext = "json" if "json" in ct else "html" if "html" in ct else "xlsx" if "sheet" in ct else "pdf" if "pdf" in ct else "csv" if "csv" in ct else "bin"
    (OUT / f"{name}.{ext}").write_bytes(b)
    head = re.sub(r"\s+", " ", b[:300].decode("utf-8", "replace"))
    LOG.append(f"OK   {name}: {st} {len(b)} bytes {ct[:40]} ({time.time() - t0:.0f}s) | {hide(head)[:220]}")
    return b




sys.path.insert(0, "pipeline")
cj = http.cookiejar.CookieJar()
OP = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# Korea: ECOS table list, trade tables
try:
    from core import ecos
    tl = ecos._paged("StatisticTableList", [])
    hits = [t for t in tl if any(k in (t.get("STAT_NAME") or "") for k in ("수출", "수입", "무역", "통관"))]
    (OUT / "kr_tables_trade.json").write_text(json.dumps(hits, ensure_ascii=False, indent=0))
    LOG.append(f"OK   kr tables: {len(tl)} total, {len(hits)} trade: {[(t.get('STAT_CODE'), t.get('STAT_NAME'), t.get('CYCLE')) for t in hits][:60]}")
except Exception as e:  # noqa: BLE001
    LOG.append(f"FAIL kr tables: {e}")

# Taiwan MOF: table definitions and full CSVs
T = "https://web02.mof.gov.tw/njswww/WebMain.aspx"
for f in ("i9101", "i9111", "i9112", "i9121", "i9122", "i8141", "i8142", "i9161"):
    test(f"tw_def_{f}", f"{T}?sys=212&x=2100&funid={f}&plus=0&r=1")
for f in ("i9111", "i9121", "i9122", "i8141"):
    test(f"tw_csv_{f}", f"{T}?sys=220&funid={f}&ymf=11401&ymt=11508&kind=21&type=0&cycle=1&outmode=12&outkind=1&deflst=2&compmode=00")

# Malaysia METS Online back-end
M = "https://metsonline.dosm.gov.my/api/"
for n, u in [("my_hstypes", "Trade/get-all-hstypes"), ("my_years", "Trade/get-years-list?tradeClass=classification"),
             ("my_partners", "Trade/get-advanced-search-list/PartnerCountry?tradeClass=classification"),
             ("my_summary", "trade-summary/summary?period=2026-07")]:
    test(n, M + u, headers={"Accept": "application/json", "Referer": "https://metsonline.dosm.gov.my/"})
body_q = json.dumps({"hsType": "HS2", "products": [{"codeValue": "85"}], "flowTypes": ["Export"], "frequencyType": "Monthly",
                     "months": ["7"], "years": ["2026"], "quarters": [], "PGEGrouping": "All", "partnerCountry": [],
                     "pagination": {"offset": 0, "limit": 150}, "advancedSearch": {"enabled": False}, "isEmbargo": False,
                     "isDataChecking": False}).encode()
test("my_classq", M + "Trade/classification-query", data=body_q, headers={"Content-Type": "application/json", "Accept": "application/json",
                                                                       "Referer": "https://metsonline.dosm.gov.my/"})

# Singapore detailed dataset filters, and by-market tables
S = "https://tablebuilder.singstat.gov.sg/api/table/"
for n, q in [("a", "timeFilter=2026%20Sep&market=WORLD"), ("b", "timeFilter=2026%20Sep&markets=WORLD"),
             ("c", "timeFilter=2013%20Jan&tradeType=EXPORTS"), ("d", "timeFilter=2026%20Sep&hs2Products=85%20-%20ELECTRICAL%20MACHINERY")]:
    test(f"sg_T010001_{n}", S + "tabledata/T010001?" + q, cap=400_000)
for t in ("M451491", "M451501", "M450251"):
    test(f"sg_meta_{t}", S + "metadata/" + t)

# Indonesia dataexim availability by year
B = "https://webapi.bps.go.id/v1/api/"
for y in (2015, 2016, 2017, 2018, 2019, 2020):
    test(f"id_dataexim_27_{y}", B + f"dataexim/sumber/2/kodehs/27/jenishs/1/tahun/{y}/periode/1/key/{{BPS_KEY}}/", cap=200_000)

# China: archive pages and one table each
for n, u in [("cn_monthly2019", "http://english.customs.gov.cn/statics/report/monthly2019.html"),
             ("cn_monthly2017", "http://english.customs.gov.cn/statics/report/monthly2017.html"),
             ("cn_monthly2016", "http://english.customs.gov.cn/statics/report/monthly2016.html")]:
    test(n, u)

# India: commodity-wise all countries (HS4 8471, Apr 2018)
I = "https://tradestat.commerce.gov.in/meidb/"
page = test("in_cwac_form", I + "commodity_wise_all_countries_export", opener=OP)
tok = re.search(rb'name="_token"\s+value="([^"]+)"', page or b"")
if tok:
    body = urllib.parse.urlencode({"_token": tok.group(1).decode(), "cwacexHSCODE": "8471", "cwacexMonth": "4", "cwacexYear": "2018",
                                   "cwacexReportVal": "1", "cwacexReportYear": "2", "hscode_value": "8471", "description_value": ""}).encode()
    test("in_cwac_post", I + "commodity_wise_all_countries_export", data=body, opener=OP,
         headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": I + "commodity_wise_all_countries_export"})

# Philippines: query one yearly table, total commodity x all countries x months
P = "https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/2L/IMT/FOB/0012L4DXVD5.px"
meta = test("ph_meta", P)
if meta:
    m = json.loads(meta)
    q = {"query": [], "response": {"format": "json-stat2"}}
    for v in m["variables"]:
        vals = v["values"]
        if v["code"].lower().startswith("commodity"):
            sel = [x for x, t in zip(vals, v["valueTexts"]) if "total" in t.lower()][:1] or vals[:1]
        else:
            sel = vals
        q["query"].append({"code": v["code"], "selection": {"filter": "item", "values": sel}})
    test("ph_total_by_country", P, data=json.dumps(q).encode(), headers={"Content-Type": "application/json"})
    LOG.append(f"     ph variables: {[(v['code'], len(v['values']), v['valueTexts'][:4]) for v in m['variables']]}")

(OUT / "summary.txt").write_text("\n".join(LOG))
print("\n".join(LOG))
