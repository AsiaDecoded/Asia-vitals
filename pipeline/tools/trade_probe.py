"""Trade data access probe (9 Nov 2026): tests national trade endpoints for the 12 economies from GitHub Actions.

  python -I pipeline/tools/trade_probe.py discovery/trade

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

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "discovery/trade")
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


TESTS = []  # (name, url) pairs, filled per economy below

J = "https://www.customs.go.jp/toukei/suii/html/data/"
TESTS += [(f"jp_{f}", J + f + ".csv") for f in ("d41ma", "d42ma001", "d42ma010", "d42ma012", "d61ma", "d51ma")]
TESTS += [("jp_estat_catalog", "https://api.e-stat.go.jp/rest/3.0/app/json/getDataCatalog?appId={ESTAT_APP_ID}&statsCode=00350300&limit=200&searchWord=%E7%B5%B1%E8%A8%88%E5%93%81%E5%88%A5%E8%A1%A8")]
E_ = "https://ecos.bok.or.kr/api/StatisticItemList/{ECOS_KEY}/json/kr/1/1000/"
TESTS += [(f"kr_ecos_items_{t}", E_ + t) for t in ("901Y118", "901Y121", "901Y119", "901Y092", "901Y011", "901Y012")]
TESTS += [("kr_ecos_tables", "https://ecos.bok.or.kr/api/StatisticTableList/{ECOS_KEY}/json/kr/1/2000")]
TESTS += [("tw_mof_db", "https://web02.mof.gov.tw/njswww/WebMain.aspx?sys=100&funid=defjsptgl"),
          ("tw_mof_db_220", "https://web02.mof.gov.tw/njswww/WebMain.aspx?sys=220&ym=11501&ymt=11508&kind=21&type=1&funid=i8411&cycle=1&outmode=12"),
          ("tw_openapi", "https://openapi.mof.gov.tw/OAM/v3/api-docs"),
          ("tw_bulletin", "https://service.mof.gov.tw/public/Data/statistic/trade/monthly/11508/電子書.pdf"),
          ("tw_news", "https://service.mof.gov.tw/public/Data/statistic/trade/news/11509/11509_中文新聞稿(上網).pdf"),
          ("tw_portal", "https://portal.sw.nat.gov.tw/APGA/GA30E")]
H = "https://tradeidds.censtatd.gov.hk/api/get?lang=EN&sv=VCm&freq=M"
TESTS += [("hk_idds_spec", "https://tradeidds.censtatd.gov.hk/MetadataLink/ApiSpec/API_eng.pdf"),
          ("hk_idds_1990", H + "&period=199001,199003&ttype=ALL"),
          ("hk_idds_2005", H + "&period=200501,200503&ttype=ALL"),
          ("hk_idds_ctry", H + "&period=202601,202603&ttype=4&ccclass=C&cc=ALL"),
          ("hk_idds_ctry2", H + "&period=202601,202603&ttype=4&coclass=C&co=ALL"),
          ("hk_idds_hs", H + "&period=202601,202603&ttype=4&codeclass=HKHS4&code=8471,8472,8473,8419,8470"),
          ("hk_idds_sitc", H + "&period=202601,202603&ttype=2&codeclass=SITC2&code=75,76,77"),
          ("hk_idds_2710", H + "&period=202601,202603&ttype=1&codeclass=HKHS4&code=2710"),
          ("hk_wt_410_50001", "https://www.censtatd.gov.hk/api/get.php?id=410-50001&lang=en&full_series=1")]
S = "https://tablebuilder.singstat.gov.sg/api/table/"
TESTS += [("sg_search_market", S + "resourceid?keyword=Region%2F%20Market&searchOption=all"),
          ("sg_search_trade", S + "resourceid?keyword=merchandise%20trade&searchOption=all")]
TESTS += [(f"sg_meta_{t}", S + "metadata/" + t) for t in ("M450081", "M450071", "M450091", "M451301", "M451511", "M450981", "M451131", "M451051", "T010001")]
TESTS += [("sg_data_T010001", S + "tabledata/T010001?offset=0&limit=200")]
TESTS += [("cn_stats", "http://stats.customs.gov.cn/"),
          ("cn_en_monthly", "http://english.customs.gov.cn/statics/report/monthly.html"),
          ("cn_zfxxgk", "http://www.customs.gov.cn/customs/302249/zfxxgk/2799825/302274/index.html"),
          ("cn_stats_https", "https://stats.customs.gov.cn/")]
TESTS += [("my_headline", "https://storage.dosm.gov.my/trade/trade_headline.csv"),
          ("my_api_headline", "https://api.data.gov.my/data-catalogue?id=trade_headline&limit=3"),
          ("my_mets", "https://metsonline.dosm.gov.my/"),
          ("my_mets_api", "https://metsonline.dosm.gov.my/api/")]
M = "https://dataapi.moc.go.th/"
TESTS += [("th_summary", M + "summary-countries?year=2026&month=7&limit=0"),
          ("th_summary_1995", M + "summary-countries?year=1995&month=1&limit=0"),
          ("th_exp_hs85", M + "export-harmonize-countries?year=2026&month=7&hs_code=85&limit=1000"),
          ("th_imp_2709", M + "import-harmonize-countries?year=2026&month=7&hs_code=2709&limit=1000"),
          ("th_exp_hs85_2012", M + "export-harmonize-countries?year=2012&month=1&hs_code=85&limit=1000"),
          ("th_legacy", "https://tradereport.moc.go.th/api/exportcommoditycountries?year=2026&month=7&com_code=203030300&limit=1000")]
P = "https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/2L/IMT/"
TESTS += [("ph_fob_list", P + "FOB"), ("ph_cif_list", P + "CIF"),
          ("ph_fob_2026_meta", P + "FOB/0012L4DXVD5.px"), ("ph_cif_2026_meta", P + "CIF/0022L4DMVD5.px"),
          ("ph_fob_1991_meta", P + "FOB/0012L4DXVA0.px")]
B = "https://webapi.bps.go.id/v1/api/"
TESTS += [("id_dataexim_85", B + "dataexim/sumber/1/kodehs/85/jenishs/1/tahun/2014/periode/1/key/{BPS_KEY}/"),
          ("id_dataexim_8471", B + "dataexim/sumber/1/kodehs/8471/jenishs/2/tahun/2024/periode/1/key/{BPS_KEY}/"),
          ("id_dataexim_27imp", B + "dataexim/sumber/2/kodehs/27/jenishs/1/tahun/2024/periode/1/key/{BPS_KEY}/"),
          ("id_dataexim_2012", B + "dataexim/sumber/2/kodehs/27/jenishs/1/tahun/2012/periode/1/key/{BPS_KEY}/"),
          ("id_var2389", B + "list/model/th/domain/0000/var/2389/key/{BPS_KEY}/")]
TESTS += [(f"id_seki_5_{n}", f"https://www.bi.go.id/SEKI/tabel/TABEL5_{n}.xls") for n in range(11, 26)]
TESTS += [("vn_customs", "https://www.customs.gov.vn/"),
          ("vn_stat_list", "https://www.customs.gov.vn/index.jsp?pageId=4&cid=1203"),
          ("vn_2x", "https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2025/11/6/2025-t10-2x(vn-sb).pdf"),
          ("vn_5x_ct", "https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2026/5/18/2025-T12T-5X(VN-CT).pdf"),
          ("vn_5n", "https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2025/5/6/2025-t4-5n(vn-sb).pdf")]
TESTS += [("in_meidb", "https://tradestat.commerce.gov.in/meidb/commoditywise_export"),
          ("in_meidb_legacy", "https://tradestat.commerce.gov.in/meidb/Default.asp"),
          ("in_eidb", "https://tradestat.commerce.gov.in/eidb/default.asp"),
          ("in_tia", "https://trade-analytics.commerce.gov.in/")]

for name, url in TESTS:
    test(name, url)

# India TradeStat MEIDB: GET form for _token and cookie, then POST a country-wise query
try:
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    page = test("in_meidb_cw_form", "https://tradestat.commerce.gov.in/meidb/country_wise_all_commodities_export", opener=op)
    tok = re.search(rb'name="_token"\s+value="([^"]+)"', page or b"")
    LOG.append(f"     in_meidb token found: {bool(tok)}; form fields: {sorted(set(re.findall(rb'name=\"([a-zA-Z_]+)\"', page or b'')))[:30]}")
    if tok:
        body = urllib.parse.urlencode({"_token": tok.group(1).decode(), "cwcexddMonth": "7", "cwcexddYear": "2026",
                                       "cwcexallcount": "423", "cwcexddCommodityLevel": "2", "cwcexddReportVal": "1",
                                       "cwcexddReportYear": "2"}).encode()
        test("in_meidb_cw_post", "https://tradestat.commerce.gov.in/meidb/country_wise_all_commodities_export", data=body, opener=op,
             headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": "https://tradestat.commerce.gov.in/meidb/country_wise_all_commodities_export"})
except Exception as e:  # noqa: BLE001
    LOG.append(f"FAIL in_meidb flow: {e}")

(OUT / "summary.txt").write_text("\n".join(LOG))
print("\n".join(LOG))
