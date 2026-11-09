"""Trade probe round 2 (9 Nov 2026): follow-ups on round 1: tests national trade endpoints for the 12 economies from GitHub Actions.

  python -I pipeline/tools/trade_probe2.py discovery/trade2

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

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "discovery/trade2")
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

# Korea: ECOS item lists (sample key if no secret)
try:
    from core import ecos
    for t in ("901Y118", "901Y119", "901Y121", "901Y092"):
        it = ecos.items(t)
        (OUT / f"kr_items_{t}.json").write_text(json.dumps(it, ensure_ascii=False, indent=0))
        LOG.append(f"OK   kr_items_{t}: {len(it)} items; e.g. {[(i.get('ITEM_CODE'), i.get('ITEM_NAME'), i.get('START_TIME'), i.get('CYCLE')) for i in it[:6]]}")
    r = ecos._paged("StatisticSearch", ["901Y118", "M", "199001", "199003"])
    LOG.append(f"     kr 901Y118 1990: {len(r)} rows, e.g. {[(x.get('ITEM_NAME1'), x.get('TIME'), x.get('DATA_VALUE'), x.get('UNIT_NAME')) for x in r[:4]]}")
except Exception as e:  # noqa: BLE001
    LOG.append(f"FAIL kr ecos: {e}")

test("jp_estat_catalog", "https://api.e-stat.go.jp/rest/3.0/app/json/getDataCatalog?appId={ESTAT_APP_ID}&statsCode=00350300&limit=100&searchWord=%E5%93%81%E5%88%A5%E5%9B%BD%E5%88%A5")
test("jp_estat_list", "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsList?appId={ESTAT_APP_ID}&statsCode=00350300&limit=100")

T = "https://web02.mof.gov.tw/njswww/"
for n, u in [("tw_menu100", "webMain.aspx?sys=100&kind=10&type=1&funid=defjsp7"), ("tw_menu220", "webMain.aspx?sys=220&kind=21&type=1&funid=defjsp7"),
             ("tw_i8411_form", "webMain.aspx?sys=220&funid=i8411"), ("tw_i7000", "webMain.aspx?sys=100&kind=10&type=1&funid=i7000"),
             ("tw_menu210", "webMain.aspx?sys=210&kind=21&type=1&funid=defjsp7")]:
    test(n, T + u)

# Hong Kong Trade-IDDS: visit the site first for cookies, then the API
test("hk_idds_home", "https://tradeidds.censtatd.gov.hk/", opener=OP)
test("hk_idds_index", "https://tradeidds.censtatd.gov.hk/Index/b0f2e1f4c6eb4c6b8e4e8d0c4b2c9d0f", opener=OP)
test("hk_idds_ex", "https://tradeidds.censtatd.gov.hk/api/get?lang=EN&sv=VCm&freq=M&period=201805,201806&ttype=4&ccclass=C&cc=CN", opener=OP,
     headers={"Referer": "https://tradeidds.censtatd.gov.hk/", "Accept": "application/json"})
LOG.append(f"     hk cookies: {[c.name for c in cj]}")
for tid in ("410-50002", "410-50003", "410-50011", "410-50012", "410-50013", "410-50021", "410-50022"):
    test(f"hk_wt_{tid}", f"https://www.censtatd.gov.hk/api/get.php?id={tid}&lang=en&full_series=1")

S = "https://tablebuilder.singstat.gov.sg/api/table/"
for n, q in [("a", "tabledata/T010001?tradeType=EXPORTS&market=WORLD&hs2Product=85"), ("b", "tabledata/T010001?seriesNoORrowNo=1"),
             ("c", "tabledata/T010001"), ("d", "detailedtradedata/T010001?tradeType=EXPORTS&market=WORLD"),
             ("e", "tabledata/T010001?tradeTypes=EXPORTS&markets=WORLD&hs2Products=85"), ("f", "tabledata/T010001?timeFilter=2026%20Sep")]:
    test(f"sg_T010001_{n}", S + q)
for kw in ("Imports By Region", "Exports By Region", "Domestic Exports By Region", "By Market"):
    test("sg_search_" + kw.replace(" ", "_"), S + "resourceid?keyword=" + urllib.parse.quote(kw) + "&searchOption=all")

for n, u in [("cn_t2_jan2026", "http://english.customs.gov.cn/Statics/6e9d4074-409f-46a1-883c-3278c5b5b31c.html"),
             ("cn_monthly2018", "http://english.customs.gov.cn/statics/report/monthly2018.html"),
             ("cn_monthly2020", "http://english.customs.gov.cn/statics/report/monthly2020.html"),
             ("cn_monthly2015", "http://english.customs.gov.cn/statics/report/monthly2015.html"),
             ("cn_prelim", "http://english.customs.gov.cn/statics/report/preliminary.html"),
             ("cn_stats_en", "http://stats.customs.gov.cn/indexEn")]:
    test(n, u)

b = test("my_mets_js", "https://metsonline.dosm.gov.my/static/js/main.72197225.js", cap=20_000_000)
if b:
    t = b.decode("utf-8", "replace")
    urls = sorted(set(re.findall(r'["\'`](https?://[^"\'`\s]{6,120}|/api/[^"\'`\s]{2,120})["\'`]', t)))
    LOG.append(f"     my_mets urls: {urls[:80]}")
    (OUT / "my_mets_urls.txt").write_text("\n".join(urls))

L = "https://tradereport.moc.go.th/api/"
for n in ("exportcountries", "importcountries", "summarycountries", "exportharmonizecountries?hs_code=85", "importharmonizecountries?hs_code=2709",
          "exporthscountries?hs_code=85", "exportcountry", "summarycountry", "exportcommodity", "importcommoditycountries?com_code=301010000"):
    sep = "&" if "?" in n else "?"
    test("th_legacy_" + re.sub(r"\W", "_", n)[:40], L + n + sep + "year=2026&month=7&limit=1000")
test("th_legacy_1995", L + "exportcommoditycountries?year=1995&month=1&com_code=203030300&limit=1000")
test("th_moc_root", "https://tradereport.moc.go.th/api/")

B = "https://webapi.bps.go.id/v1/api/"
test("id_dataexim_85_2024", B + "dataexim/sumber/1/kodehs/85/jenishs/1/tahun/2024/periode/1/key/{BPS_KEY}/")
test("id_dataexim_85_2014p2", B + "dataexim/sumber/1/kodehs/85/jenishs/1/tahun/2014/periode/2/key/{BPS_KEY}/")
test("id_dataexim_27_2014", B + "dataexim/sumber/2/kodehs/27/jenishs/1/tahun/2014/periode/1/key/{BPS_KEY}/")
for n in list(range(1, 11)) + list(range(26, 41)):
    test(f"id_seki_5_{n}", f"https://www.bi.go.id/SEKI/tabel/TABEL5_{n}.xls")

test("vn_nso_trade", "https://www.nso.gov.vn/wp-json/wp/v2/search?search=xu%E1%BA%A5t%20kh%E1%BA%A9u&per_page=20")
test("vn_customs_en", "https://www.customs.gov.vn/index.jsp?pageId=3&cid=1203", )

# India TradeStat: commodity-wise (HS4 8471) and country-wise all commodities for an old month
I = "https://tradestat.commerce.gov.in/meidb/"
for path in ("commoditywise_export", "commodity_wise_all_countries_export", "countrywise_export", "country_wise_all_commodities_import", "commoditywise_import"):
    test("in_form_" + path, I + path, opener=OP)
f = (OUT / "in_form_commodity_wise_all_countries_export.html")
if f.exists():
    h = f.read_bytes()
    LOG.append(f"     in commodity_wise_all_countries fields: {sorted(set(re.findall(rb'name=\"([a-zA-Z_]+)\"', h)))}")
    LOG.append(f"     in selects: {re.findall(rb'<select[^>]*name=\"([^\"]+)\"', h)}; years: {sorted(set(re.findall(rb'<option value=\"(20[0-9][0-9])\"', h)))[:12]}")

(OUT / "summary.txt").write_text("\n".join(LOG))
print("\n".join(LOG))
