"""Malaysia merchandise trade: Department of Statistics Malaysia, OpenDOSM trade_headline (storage.dosm.gov.my), as
published, RM: exports (gross, FOB), domestic exports, re-exports, imports (CIF), monthly from Jan 1990.
US$: BIS monthly average ringgit rate (calculated).
HS lines (world): DOSM METS Online back-end API (metsonline.dosm.gov.my/api/Trade/classification-query), RM, monthly:
exports HS 85 (HS2) and 8419, 8470, 8471, 8472, 8473 (HS4) from 2012; imports 2709, 2710 (HS4) from 2010.
Partners: METS, HS2 x every partner country x month, one query per flow and year, summed over chapters (calculated);
partner names mapped to ISO codes (DOSM uses several spellings over time); EU from METS's own economic grouping "EU".
Partner years are backfilled over runs in raw/trade/my/store.json.gz; the current and previous year are re-fetched.
"""
import csv
import hashlib
import io
import json
import re
import time
import urllib.request

from core import trade
from core.common import CheckFailed, read_json, write_release

NAME = "trade_my"
DESCRIPTION = "Malaysia merchandise trade (OpenDOSM trade_headline, RM): exports, domestic exports, re-exports, imports"
URL = "https://storage.dosm.gov.my/trade/trade_headline.csv"
UA = {"User-Agent": "Mozilla/5.0 (asia-vitals data pipeline; github.com/AsiaDecoded)"}
METS = "https://metsonline.dosm.gov.my/api/Trade/classification-query"
HS_EXP = (("HS2_digit", ["85"]), ("HS4_digit", ["8419", "8470", "8471", "8472", "8473"]))
HS_IMP = (("HS4_digit", ["2709", "2710"]),)
MON = {m: i + 1 for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
WARN = []
PARTNERS = {"UNITED STATES": "US", "UNITED STATES OF AMERICA": "US", "CHINA": "CN", "CHINA, PEOPLE'S REPUBLIC OF": "CN",
            "HONG KONG": "HK", "HONG KONG, SAR": "HK", "JAPAN": "JP", "TAIWAN": "TW", "TAIWAN, PROVINCE OF CHINA": "TW",
            "KOREA, REPUBLIC OF": "KR", "INDIA": "IN", "INDONESIA": "ID", "PHILIPPINES": "PH", "SINGAPORE": "SG",
            "THAILAND": "TH", "VIET NAM": "VN", "VIETNAM, SOCIALIST REP. OF": "VN"}
BUDGET = 30
FIELDS = {"exports": "exports", "exports_domestic": "domestic_exports", "re_exports": "re_exports", "imports": "imports"}


def mets(flow, hs, codes, years, **extra):
    body = {"tradeClass": "classification", "hsType": hs, "flowTypes": [flow], "frequencyType": "MONTHLY",
            "years": [str(y) for y in years], "months": [f"{m:02d}" for m in range(1, 13)],
            "products": [{"codeValue": c, "codeName": ""} for c in codes], **extra}
    err = None
    for i in range(3):
        try:
            rq = urllib.request.Request(METS, data=json.dumps(body).encode(), headers={**UA, "Content-Type": "application/json",
                                        "Accept": "application/json"})
            with urllib.request.urlopen(rq, timeout=180) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"METS {flow} {hs} {codes[:2]} {years[0]}-{years[-1]}: {err!r}")


def hs_rows(last_year):
    rows = []
    for flow, specs, first in (("exports", HS_EXP, 2012), ("imports", HS_IMP, 2010)):
        for hs, codes in specs:
            for y0 in range(first, last_year + 1, 5):
                try:
                    js = mets(flow.capitalize(), hs, codes, list(range(y0, min(y0 + 5, last_year + 1))))
                except Exception as e:  # noqa: BLE001
                    WARN.append(str(e))
                    continue
                cols = js.get("columns") or []
                for it in js.get("items") or []:
                    code = str(it[0])
                    for j, c in enumerate(cols):
                        m = re.match(r"([A-Z][a-z]{2})_(\d{4})_", c)
                        if not m or j >= len(it) or it[j] in (None, ""):
                            continue
                        v = float(it[j])
                        if v == 0:
                            continue   # METS fills months not yet published with 0
                        rows.append({"economy": "MY", "flow": flow, "partner": "WLD", "product": f"HS{code}",
                                     "date": f"{m.group(2)}-{MON[m.group(1)]:02d}-01", "value": v, "unit": "MYR", "usd_mn": None,
                                     "usd_calculated": "", "series": f"METS {hs} {code} {flow}"})
    return rows


def partner_year(flow, y):
    """{iso or EU: {yyyy-mm: RM}} for one flow and year."""
    out = {}
    for extra, col in (({"partnerCountry": sorted(PARTNERS)}, "partner_country_name"), ({"partnerCountry": ["EU"], "PGEGrouping": "ECONOMICGROUPING"}, "economic_grouping")):
        js = mets(flow.capitalize(), "HS2_digit", [], [y], **extra)
        cols = js.get("columns") or []
        if not js.get("items"):
            continue
        if col not in cols:
            raise RuntimeError(f"METS partners {flow} {y}: no column {col} in {cols[:4]}")
        pc = cols.index(col)
        for it in js.get("items") or []:
            iso = "EU" if col == "economic_grouping" and it[pc] == "EU" else PARTNERS.get(str(it[pc]).strip().upper())
            if not iso:
                continue
            acc = out.setdefault(iso, {})
            for j, c in enumerate(cols):
                m = re.match(r"([A-Z][a-z]{2})_(\d{4})_", c)
                if m and j < len(it) and it[j] not in (None, ""):
                    ym = f"{m.group(2)}-{MON[m.group(1)]:02d}"
                    acc[ym] = acc.get(ym, 0.0) + float(it[j])
    return out


def update(force=False, **_):
    folder = trade.OUT / "my"
    state = read_json(folder / "release.json", {}) or {}
    with urllib.request.urlopen(urllib.request.Request(URL, headers=UA), timeout=120) as r:
        text = r.read().decode("utf-8")
    fp = hashlib.sha256(text.encode()).hexdigest()[:16]
    if fp == state.get("fingerprint") and state.get("hs") and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    rows = []
    for x in csv.DictReader(io.StringIO(text)):
        if x.get("series") != "abs":
            continue
        for fld, flow in FIELDS.items():
            try:
                v = float(x[fld])
            except (KeyError, TypeError, ValueError):
                continue
            rows.append({"economy": "MY", "flow": flow, "partner": "WLD", "product": "TOTAL", "date": x["date"][:10],
                         "value": v, "unit": "MYR", "usd_mn": None, "usd_calculated": "", "series": f"OpenDOSM trade_headline {fld}"})
    if not rows:
        raise CheckFailed(["trade_headline: no rows"])
    WARN.clear()
    last_year = int(trade.latest(rows)[:4])
    rows += hs_rows(last_year)
    st = trade.Store("my")
    for y in range(last_year, 1999, -1):
        for flow in ("exports", "imports"):
            try:
                st.get(f"P:{flow}:{y}", lambda: partner_year(flow, y), refresh=y >= last_year - 1, budget=BUDGET)
            except Exception as e:  # noqa: BLE001
                WARN.append(str(e))
    st.save()
    have = {(r["date"][:7], r["flow"]) for r in rows if r["partner"] == "WLD" and r["product"] == "TOTAL"}
    for key, agg in st.data.items():
        _, flow, y = key.split(":")
        for iso, s_ in (agg or {}).items():
            for ym, v in s_.items():
                if v and (ym, flow) in have:      # METS fills unpublished months with 0
                    rows.append({"economy": "MY", "flow": flow, "partner": iso, "product": "TOTAL", "date": ym + "-01",
                                 "value": v, "unit": "MYR", "usd_mn": None, "usd_calculated": "",
                                 "series": "METS EU economic grouping" if iso == "EU" else "METS HS2 x partner, sum over chapters (calculated)"})
    trade.to_usd(rows, "my", 1)
    last = trade.latest(rows)
    folder = trade.write("my", rows)
    code = f"T{last[:7]}"
    write_release(folder, {"code": code, "label": last[:7], "latest_month": last, "source": NAME, "table": "OpenDOSM trade_headline"},
                  WARN[:10], len(rows), {"fingerprint": fp, "hs": 1, "fetched": st.fetched})
    return {"updated": True, "code": code, "summary": f"{last[:7]}: {len(rows)} rows", "warnings": WARN[:5]}
