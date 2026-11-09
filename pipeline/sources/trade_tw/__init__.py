"""Taiwan merchandise trade: Ministry of Finance, Department of Statistics, trade statistics database
(web02.mof.gov.tw/njswww, general trade system), as published, US$ (the database also gives NT$).

Same query software as DGBAS's Macro Database: ?sys=220&funid=<table>&ymf=&ymt=&kind=21&type=0&cycle=1&outmode=12
&outkind=1&deflst=2&compmode=00 returns every series of the table as CSV (months in ROC years).
  i9111  exports and imports by country/area, thousand US$, from Jan 1981
  i9121  exports by main commodity group, million US$, from 2001 (incl. 電子零組件 electronic parts, 電機產品
         electrical machinery products, 資通與視聽產品 ICT and audio-video products, 家用電器 domestic appliances)
  i9122  imports by main commodity group, million US$, from 2001 (incl. 原油 crude oil)
  i8151  exports and imports by SITC, thousand US$, from 2001 (SITC 75, 76, 77)
  i9162  imports by detailed commodity, thousand US$, from 2001 (汽油, 柴油, 燃料油, 石油腦, 液化天然氣 ...)
EU = sum of the 27 current members (calculated); MOF publishes no EU aggregate in i9111.
"""
import csv
import hashlib
import io
import re
import time
import urllib.request

from core import trade
from core.common import CheckFailed, read_json, write_release

NAME = "trade_tw"
DESCRIPTION = "Taiwan merchandise trade (MOF statistics database, US$): totals, partners, main commodities, SITC, oil"
DB = "https://web02.mof.gov.tw/njswww/WebMain.aspx"
UA = {"User-Agent": "Mozilla/5.0 (asia-vitals data pipeline; github.com/AsiaDecoded)"}
COUNTRY = {"總計": "WLD", "中國大陸": "CN", "香港": "HK", "日本": "JP", "南韓": "KR", "新加坡": "SG", "馬來西亞": "MY", "印尼": "ID",
           "越南": "VN", "泰國": "TH", "菲律賓": "PH", "印度": "IN", "美國": "US",
           "奧地利": "AT", "比利時": "BE", "保加利亞": "BG", "克羅埃西亞": "HR", "塞普勒斯": "CY", "捷克": "CZ", "丹麥": "DK",
           "愛沙尼亞": "EE", "芬蘭": "FI", "法國": "FR", "德國": "DE", "希臘": "GR", "匈牙利": "HU", "愛爾蘭": "IE", "義大利": "IT",
           "拉脫維亞": "LV", "立陶宛": "LT", "盧森堡": "LU", "馬爾他": "MT", "荷蘭": "NL", "波蘭": "PL", "葡萄牙": "PT",
           "羅馬尼亞": "RO", "斯洛伐克": "SK", "斯洛維尼亞": "SI", "西班牙": "ES", "瑞典": "SE"}
EXP_GROUPS = {"總計": None, "(1)電子零組件": "electronic_parts", "(3)電機產品": "electrical_machinery_products",
              "(4)資通與視聽產品": "ict_av_products", "(5)家用電器": "domestic_appliances", "16.機械及電機設備": "machinery_electrical_equipment"}
IMP_GROUPS = {"(1)原油": "crude_oil", "5.礦產品": "mineral_products"}
SITC = {"75": "SITC75", "76": "SITC76", "77": "SITC77"}
IMP_DETAIL = {"汽油": "gasoline", "柴油": "diesel", "燃料油": "fuel_oil", "石油腦": "naphtha", "液化天然氣": "lng", "原油": "crude_oil_detail"}


def roc(ym):
    return f"{int(ym[:4]) - 1911}{ym[5:7]}"


def fetch(funid, first, last, tries=3):
    url = (f"{DB}?sys=220&funid={funid}&ymf={roc(first)}&ymt={roc(last)}&kind=21&type=0&cycle=1&outmode=12&outkind=1"
           f"&deflst=2&compmode=00")
    err = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
                t = r.read().decode("utf-8-sig", "replace")
            if t.startswith('"'):
                return t
            err = t[:80]
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(5 * (i + 1))
    raise CheckFailed([f"MOF {funid}: {err!r}"])


def parse(text):
    """[(date, [header parts], value)] for US$ columns."""
    rows = list(csv.reader(io.StringIO(text)))
    hdr = rows[0]
    out = []
    for r in rows[1:]:
        m = re.match(r"\s*(\d+)年\s*(\d+)月", r[0] if r else "")
        if not m:
            continue
        d = f"{int(m.group(1)) + 1911}-{int(m.group(2)):02d}-01"
        for j, h in enumerate(hdr[1:], 1):
            parts = [p.strip() for p in h.split("/")]
            if not parts[0].startswith("按美元計算") or j >= len(r):
                continue
            v = r[j].replace(",", "").strip()
            try:
                out.append((d, parts, float(v)))
            except ValueError:
                pass
    return out


def scale(parts):
    return 1e-3 if "千美元" in parts[0] else 1.0      # to US$ million


def row(flow, partner, product, d, usd_mn, series):
    return {"economy": "TW", "flow": flow, "partner": partner, "product": product, "date": d, "value": round(usd_mn, 6),
            "unit": "USD million", "usd_mn": round(usd_mn, 6), "usd_calculated": "", "series": series}


def update(force=False, **_):
    folder = trade.OUT / "tw"
    state = read_json(folder / "release.json", {}) or {}
    today = time.strftime("%Y-%m")
    texts = {"i9111": fetch("i9111", "1981-01", today), "i9121": fetch("i9121", "2001-01", today),
             "i9122": fetch("i9122", "2001-01", today), "i8151": fetch("i8151", "2001-01", today),
             "i9162": fetch("i9162", "2001-01", today)}
    fp = hashlib.sha256("".join(texts.values()).encode()).hexdigest()[:16]
    if fp == state.get("fingerprint") and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    rows = []
    for d, parts, v in parse(texts["i9111"]):
        if len(parts) >= 3 and parts[1] in COUNTRY and parts[2] in ("出口", "進口"):
            rows.append(row("exports" if parts[2] == "出口" else "imports", COUNTRY[parts[1]], "TOTAL", d, v * scale(parts), f"i9111 {parts[1]} {parts[2]}"))
    for fid, flow, groups in (("i9121", "exports", EXP_GROUPS), ("i9122", "imports", IMP_GROUPS)):
        for d, parts, v in parse(texts[fid]):
            g = groups.get(parts[1]) if len(parts) > 1 else None
            if g:
                rows.append(row(flow, "WLD", g, d, v * scale(parts), f"{fid} {parts[1]}"))
    for d, parts, v in parse(texts["i8151"]):
        flow = next((x for x in parts if x in ("出口", "進口")), None)
        code = next((re.match(r"(\d{2})\b", x).group(1) for x in parts[1:] if re.match(r"(\d{2})\b", x)), None)
        if flow and code in SITC and len(code) == 2:
            rows.append(row("exports" if flow == "出口" else "imports", "WLD", SITC[code], d, v * scale(parts), f"i8151 {' '.join(parts[1:])}"))
    for d, parts, v in parse(texts["i9162"]):
        g = IMP_DETAIL.get(parts[1]) if len(parts) > 1 else None
        if g:
            rows.append(row("imports", "WLD", g, d, v * scale(parts), f"i9162 {parts[1]}"))
    rows = [r for r in rows if not (r["value"] == 0 and r["date"] > "2026-01-01" and r["partner"] == "WLD")]
    rows += trade.eu_sum(rows, trade.EU27)
    got = {(r["partner"]) for r in rows if r["product"] == "TOTAL"}
    errors = [f"partner missing: {p}" for p in set(trade.PARTNERS) - got]
    prods = {r["product"] for r in rows}
    errors += [f"product missing: {p}" for p in ["electronic_parts", "ict_av_products", "crude_oil", "SITC76"] if p not in prods]
    if errors:
        raise CheckFailed(errors)
    last = trade.latest(rows)
    folder = trade.write("tw", rows)
    code = f"T{last[:7]}"
    write_release(folder, {"code": code, "label": last[:7], "latest_month": last, "source": NAME,
                           "table": "MOF trade statistics database i9111, i9121, i9122, i8151, i9162"}, [], len(rows), {"fingerprint": fp})
    return {"updated": True, "code": code, "summary": f"{last[:7]}: {len(rows)} rows"}
