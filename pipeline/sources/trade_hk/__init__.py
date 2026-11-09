"""Hong Kong merchandise trade: Census and Statistics Department, Trade-IDDS API (tradeidds.censtatd.gov.hk), as
published, HK$ thousand. The API answers only within a browsing session: the source first opens the site for its
cookies.

  imports (ttype 1, by origin co), domestic exports (2), re-exports (3), total exports (4) (by consignment cc):
  world (no country), the 12 partner countries/territories (codes as ISO-2: CN = the Mainland), and region EU
  (C&SD's E.U. grouping). HS lines (HKHS): total exports of HS 85, 8419, 8470, 8471, 8472, 8473; domestic exports of
  SITC 75, 76, 77; imports of HS 2710 (petroleum products). US$: BIS monthly average HK$ rate (calculated).
Backfill by calendar year, stored in raw/trade/hk/store.json.gz; each run fetches up to BUDGET missing years and
re-fetches the current and previous year.
"""
import http.cookiejar
import json
import time
import urllib.parse
import urllib.request

from core import trade
from core.common import CheckFailed, read_json, write_release

NAME = "trade_hk"
DESCRIPTION = "Hong Kong merchandise trade (C&SD Trade-IDDS): totals, partners incl. EU, domestic and re-exports, HS lines"
SITE = "https://tradeidds.censtatd.gov.hk/"
API = SITE + "api/get?"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept": "application/json", "Referer": SITE}
FIRST, HS_FIRST = 1990, 2012
FLOWS = {1: "imports", 2: "domestic_exports", 3: "re_exports", 4: "exports"}
PARTNERS = ["US", "CN", "JP", "TW", "KR", "IN", "ID", "MY", "PH", "SG", "TH", "VN"]
BUDGET = 150
_OP = None


def opener():
    global _OP
    if _OP is None:
        cj = http.cookiejar.CookieJar()
        _OP = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        _OP.open(urllib.request.Request(SITE, headers=UA), timeout=60).read()
    return _OP


def call(params, tries=4):
    url = API + urllib.parse.urlencode({"lang": "EN", "sv": "VCm", "freq": "M", **params})
    err = None
    for i in range(tries):
        try:
            with opener().open(urllib.request.Request(url, headers=UA), timeout=120) as r:
                js = json.loads(r.read().decode("utf-8"))
            code = js.get("header", {}).get("status", {}).get("code")
            if code == 0:
                return js.get("dataSet") or []
            if code == 1:                          # validation error, e.g. period before the series starts
                return []
            err = js.get("header", {}).get("status")
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"IDDS {params}: {err!r}")


def requests(y):
    end = 12 if y < int(time.strftime("%Y")) else max(1, int(time.strftime("%m")) - 2)
    p = {"period": f"{y}01,{y}{end:02d}"}
    out = []
    for t in FLOWS:
        side = ("coclass", "co") if t == 1 else ("ccclass", "cc")
        out.append((f"{t}:WLD:{y}", {**p, "ttype": t}))
        out.append((f"{t}:C:{y}", {**p, "ttype": t, side[0]: "C", side[1]: ",".join(PARTNERS)}))
        out.append((f"{t}:EU:{y}", {**p, "ttype": t, side[0]: "R", side[1]: "EU"}))
    if y >= HS_FIRST:
        out.append((f"4:HS4:{y}", {**p, "ttype": 4, "codeclass": "HKHS4", "code": "8419,8470,8471,8472,8473"}))
        out.append((f"4:HS2:{y}", {**p, "ttype": 4, "codeclass": "HKHS2", "code": "85"}))
        out.append((f"2:SITC2:{y}", {**p, "ttype": 2, "codeclass": "SITC2", "code": "75,76,77"}))
        out.append((f"1:HS4:{y}", {**p, "ttype": 1, "codeclass": "HKHS4", "code": "2710"}))
    return out


def update(force=False, **_):
    folder = trade.OUT / "hk"
    state = read_json(folder / "release.json", {}) or {}
    st = trade.Store("hk")
    this = int(time.strftime("%Y"))
    for y in range(this, FIRST - 1, -1):
        for key, params in requests(y):
            st.get(key, lambda: call(params), refresh=y >= this - 1, budget=BUDGET)
    st.save()
    rows = []
    for key, data in st.data.items():
        t, kind, _y = key.split(":")
        flow = FLOWS[int(t)]
        for x in data:
            p = x.get("period", "")
            try:
                v = float(x.get("figure"))
            except (TypeError, ValueError):
                continue
            d = f"{p[:4]}-{p[4:6]}-01"
            if kind == "WLD":
                partner, product, series = "WLD", "TOTAL", f"IDDS ttype {t}"
            elif kind == "C":
                c = x.get("co") or x.get("cc")
                if c not in PARTNERS:
                    continue
                partner, product, series = c, "TOTAL", f"IDDS ttype {t} {c}"
            elif kind == "EU":
                partner, product, series = "EU", "TOTAL", f"IDDS ttype {t} region E.U. (C&SD grouping)"
            else:
                code = x.get("code") or ""
                partner, product = "WLD", ("SITC" if kind == "SITC2" else "HS") + code
                series = f"IDDS ttype {t} {kind} {code} {x.get('codeDescEN', '')[:60]}"
            rows.append({"economy": "HK", "flow": flow, "partner": partner, "product": product, "date": d, "value": v,
                         "unit": "HKD thousand", "usd_mn": None, "usd_calculated": "", "series": series})
    if not rows:
        raise CheckFailed(["no data from Trade-IDDS"])
    trade.to_usd(rows, "hk", 1000)
    last = trade.latest(rows)
    errors = []
    got = {r["partner"] for r in rows if r["flow"] == "exports" and r["date"] == last}
    if set(PARTNERS + ["WLD", "EU"]) - got:
        errors.append(f"exports {last}: partners missing {sorted(set(PARTNERS + ['WLD', 'EU']) - got)}")
    if errors:
        raise CheckFailed(errors)
    complete = all(k in st.data for y in range(FIRST, this + 1) for k, _ in requests(y))
    folder = trade.write("hk", rows)
    code = f"T{last[:7]}" + ("" if complete else f"b{len(st.data)}")
    write_release(folder, {"code": code, "label": last[:7], "latest_month": last, "source": NAME, "backfill_complete": complete,
                           "table": "C&SD Trade-IDDS API"}, [], len(rows), {"fetched": st.fetched})
    return {"updated": True, "code": code, "summary": f"{last[:7]}: {len(rows)} rows, {st.fetched} calls" + ("" if complete else " (backfill continuing)")}
