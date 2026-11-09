"""Malaysia merchandise trade: Department of Statistics Malaysia, OpenDOSM trade_headline (storage.dosm.gov.my), as
published, RM: exports (gross, FOB), domestic exports, re-exports, imports (CIF), monthly from Jan 1990.
US$: BIS monthly average ringgit rate (calculated).
HS lines (world): DOSM METS Online back-end API (metsonline.dosm.gov.my/api/Trade/classification-query), RM, monthly:
exports HS 85 (HS2) and 8419, 8470, 8471, 8472, 8473 (HS4) from 2012; imports 2709, 2710 (HS4) from 2010.
Partners: METS query format for the partner dimension still being worked out (to add).
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
FIELDS = {"exports": "exports", "exports_domestic": "domestic_exports", "re_exports": "re_exports", "imports": "imports"}


def mets(flow, hs, codes, years):
    body = {"tradeClass": "classification", "hsType": hs, "flowTypes": [flow], "frequencyType": "MONTHLY",
            "years": [str(y) for y in years], "months": [f"{m:02d}" for m in range(1, 13)],
            "products": [{"codeValue": c, "codeName": ""} for c in codes]}
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
    rows += hs_rows(int(trade.latest(rows)[:4]))
    trade.to_usd(rows, "my", 1)
    last = trade.latest(rows)
    folder = trade.write("my", rows)
    code = f"T{last[:7]}"
    write_release(folder, {"code": code, "label": last[:7], "latest_month": last, "source": NAME, "table": "OpenDOSM trade_headline"},
                  WARN[:10], len(rows), {"fingerprint": fp, "hs": 1})
    return {"updated": True, "code": code, "summary": f"{last[:7]}: {len(rows)} rows", "warnings": WARN[:5]}
