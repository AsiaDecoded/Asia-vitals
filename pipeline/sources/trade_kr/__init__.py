"""South Korea merchandise trade: Korea Customs Service, as published on its trade statistics site (tradedata.go.kr,
수출입무역통계; the site's own query service, no key), customs-acceptance basis (수리일 기준), thousand US$.

  totals and partners: 국가별 (by country), one query per month: the month's total (World) and every country;
                       the dump keeps US, CN, JP, TW, HK, SG, IN, MY, ID, TH, PH, VN
  EU:                  경제권별 EU (KCS's own EU aggregate)
  HS lines:            품목별 HS2 85 (exports) and HS4 8419, 8470, 8471, 8472, 8473 (exports), 2709, 2710 (imports)
KCS's site serves from January 2000. Before that, 1990-1999 partner figures come from the Bank of Korea's ECOS
(901Y121, KCS figures republished; World is not in ECOS before 2000). Monthly queries are stored in
raw/trade/kr/store.json.gz and backfilled over runs; the last four months are re-fetched each run.
"""
import http.cookiejar
import json
import time
import urllib.parse
import urllib.request

from core import ecos, trade
from core.common import CheckFailed, write_release

NAME = "trade_kr"
DESCRIPTION = "South Korea merchandise trade (KCS tradedata.go.kr, US$): totals, partners, EU, HS lines; 1990s partners via ECOS"
SITE = "https://tradedata.go.kr"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
KCS_FIRST = "2000-01"
ECOS_FIRST = "1990-01"
PARTNERS = {"US", "CN", "JP", "TW", "HK", "SG", "IN", "MY", "ID", "TH", "PH", "VN"}
HS_EXP = ["8419", "8470", "8471", "8472", "8473"]
HS_IMP = ["2709", "2710"]
FLOW = {"T002": "exports", "T004": "imports"}
BUDGET = 120
BASE = {"priodKind": "MON", "statsBase": "acptDd", "ttwgTpcd": "1000", "selectPaging": "1", "showPagingLine": "1000",
        "sortColumn": "", "sortOrder": ""}


class Site:
    def __init__(self):
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.ready = False

    def _open(self, path, data=None, xhr=True):
        h = {"User-Agent": UA, "Referer": SITE + "/cts/index.do", "Accept": "*/*", "Accept-Language": "ko"}
        if xhr:
            h["X-Requested-With"] = "XMLHttpRequest"
        if data is not None:
            h["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        with self.op.open(urllib.request.Request(SITE + path, data=data, headers=h), timeout=120) as r:
            return r.read()

    def query(self, **params):
        err = None
        for i in range(4):
            try:
                if not self.ready:
                    self._open("/cts/index.do", xhr=False)
                    self._open("/cts/hmpg/openETS0100019Q.do", data=b"menuId=ETS_MNK_10200000")
                    self.ready = True
                js = json.loads(self._open("/cts/hmpg/retrieveTrade.do", data=urllib.parse.urlencode(dict(BASE, **params)).encode()))
                if js.get("searchresult") != "OK":
                    raise RuntimeError(str(js)[:200])
                return js.get("items") or []
            except Exception as e:  # noqa: BLE001
                err = e
                self.ready = False
                time.sleep(5 * (i + 1))
        raise RuntimeError(f"KCS retrieveTrade {params.get('tradeKind')} {params.get('priodFr')}: {repr(err)[:200]}")


def num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return None


def ym_of(title):
    t = str(title or "").strip()
    return f"{t[:4]}-{t[5:7]}" if len(t) == 7 and t[4] == "." else None


def row(flow, partner, product, ym, v, series):
    return {"economy": "KR", "flow": flow, "partner": partner, "product": product, "date": ym + "-01", "value": v,
            "unit": "USD thousand", "usd_mn": round(v / 1000, 6), "usd_calculated": "", "series": series}


def kcs_rows(st):
    rows = []
    for key, items in st.data.items():
        kind = key.split(":")[0]
        if kind == "D":                                     # one month, every country
            ym = key.split(":")[1]
            for it in items or []:
                cc = it.get("cntyCd")
                if it.get("priodTitle") == "총계" and not cc:
                    partner = "WLD"
                elif cc in PARTNERS:
                    partner = cc
                else:
                    continue
                for flow, f in (("exports", "expUsdAmt"), ("imports", "impUsdAmt")):
                    v = num(it.get(f))
                    if v is not None:
                        rows.append(row(flow, partner, "TOTAL", ym, v, f"KCS 국가별 {it.get('cntyNm') or '총계'}"))
        elif kind == "EU":
            for it in items or []:
                ym = ym_of(it.get("priodTitle"))
                if ym and it.get("cntnEbkNm") == "EU":
                    for flow, f in (("exports", "expUsdAmt"), ("imports", "impUsdAmt")):
                        v = num(it.get(f))
                        if v is not None:
                            rows.append(row(flow, "EU", "TOTAL", ym, v, "KCS 경제권별 EU"))
        elif kind in ("HS2", "HS4"):
            for it in items or []:
                ym, code = ym_of(it.get("priodTitle")), it.get("hsSgn")
                if not ym or not code:
                    continue
                flow, f = ("imports", "impUsdAmt") if code in HS_IMP else ("exports", "expUsdAmt")
                v = num(it.get(f))
                if v is not None:
                    rows.append(row(flow, "WLD", f"HS{code}", ym, v, f"KCS 품목별 HS {code} {it.get('korePrlstNm') or ''}".strip()))
    return rows


def ecos_rows(st):
    rows = []
    for key, data in st.data.items():
        if not key.startswith("121:"):
            continue
        ym = key.split(":")[1]
        for r in data or []:
            codes = [r.get("ITEM_CODE1"), r.get("ITEM_CODE2")]
            flow = next((FLOW[c] for c in codes if c in FLOW), None)
            partner = next((c for c in codes if c and c not in FLOW), None)
            v = num(r.get("DATA_VALUE"))
            if flow and partner in PARTNERS and v is not None:
                rows.append(row(flow, partner, "TOTAL", ym, v, f"BoK ECOS 901Y121 {r.get('ITEM_NAME1', '')} {r.get('ITEM_NAME2', '')} (KCS)"))
    return rows


def update(force=False, **_):
    st = trade.Store("kr")
    # drop ECOS months the KCS site now covers (store keys from the earlier ECOS-only version)
    for k in [k for k in st.data if (k.startswith("121:") and k[4:] >= KCS_FIRST) or k.startswith("118:")]:
        del st.data[k]
    site = Site()
    today = time.strftime("%Y-%m")
    last_pub = trade.shift(today, -1)
    recent = set(trade.months(trade.shift(today, -4), last_pub))
    warn = []
    try:
        for ym in reversed(trade.months(KCS_FIRST, last_pub)):
            p = ym.replace("-", "")
            st.get(f"D:{ym}", lambda: site.query(tradeKind="ETS_MNK_1020000D", priodFr=p, priodTo=p, cntyNm=""),
                   refresh=ym in recent, budget=BUDGET)
        for y in range(int(last_pub[:4]), int(KCS_FIRST[:4]) - 1, -1):
            fr, to = f"{y}01", min(f"{y}12", last_pub.replace("-", ""))
            this = y >= int(last_pub[:4]) - (1 if last_pub[5:] <= "04" else 0)
            st.get(f"EU:{y}", lambda: site.query(tradeKind="ETS_MNK_1020000I", priodFr=fr, priodTo=to, cntnEbkUnfcClsfCd="EU"),
                   refresh=this, budget=BUDGET)
            st.get(f"HS2:{y}", lambda: site.query(tradeKind="ETS_MNK_1020000A", priodFr=fr, priodTo=to, hsSgnGrpCol="HS2_SGN",
                                                  hsSgnWhrCol="HS2_SGN", hsSgn="85", subHsSgn=""), refresh=this, budget=BUDGET)
            st.get(f"HS4:{y}", lambda: site.query(tradeKind="ETS_MNK_1020000A", priodFr=fr, priodTo=to, hsSgnGrpCol="HS4_SGN",
                                                  hsSgnWhrCol="HS4_SGN", hsSgn=",".join(HS_EXP + HS_IMP), subHsSgn=""),
                   refresh=this, budget=BUDGET)
    except Exception as e:  # noqa: BLE001
        warn.append(str(e)[:300])
    for ym in reversed(trade.months(ECOS_FIRST, trade.shift(KCS_FIRST, -1))):
        e = ym.replace("-", "")
        try:
            st.get(f"121:{ym}", lambda: ecos.month_all("901Y121", e), budget=BUDGET + 40)
        except Exception as ex:  # noqa: BLE001
            warn.append(f"ECOS {ym}: {str(ex)[:150]}")
            break
    st.save()
    rows = kcs_rows(st) + ecos_rows(st)
    if not rows:
        raise CheckFailed(["KCS and ECOS: no trade rows"] + warn[:3])
    last = trade.latest(rows)
    need = [f"D:{ym}" for ym in trade.months(KCS_FIRST, last_pub)] + [f"121:{ym}" for ym in trade.months(ECOS_FIRST, "1999-12")]
    complete = all(k in st.data for k in need)
    folder = trade.write("kr", rows)
    code = f"T{last[:7]}" + ("" if complete else f"b{len(st.data)}")
    write_release(folder, {"code": code, "label": last[:7], "latest_month": last, "source": NAME, "backfill_complete": complete,
                           "table": "KCS tradedata.go.kr retrieveTrade (국가별, 경제권별, 품목별); BoK ECOS 901Y121 for 1990-1999"},
                  warn[:20], len(rows), {"fetched": st.fetched})
    return {"updated": True, "code": code, "warnings": warn[:5],
            "summary": f"{last[:7]}: {len(rows)} rows, {st.fetched} queries" + ("" if complete else " (backfill continuing)")}
