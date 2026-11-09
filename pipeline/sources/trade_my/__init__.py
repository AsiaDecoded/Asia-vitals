"""Malaysia merchandise trade: Department of Statistics Malaysia, OpenDOSM trade_headline (storage.dosm.gov.my), as
published, RM: exports (gross, FOB), domestic exports, re-exports, imports (CIF), monthly from Jan 1990.
US$: BIS monthly average ringgit rate (calculated).
Partners and HS lines are in DOSM's METS Online (metsonline.dosm.gov.my) back-end API, reachable from GitHub; its query
format is being worked out (to add).
"""
import csv
import hashlib
import io
import urllib.request

from core import trade
from core.common import CheckFailed, read_json, write_release

NAME = "trade_my"
DESCRIPTION = "Malaysia merchandise trade (OpenDOSM trade_headline, RM): exports, domestic exports, re-exports, imports"
URL = "https://storage.dosm.gov.my/trade/trade_headline.csv"
UA = {"User-Agent": "Mozilla/5.0 (asia-vitals data pipeline; github.com/AsiaDecoded)"}
FIELDS = {"exports": "exports", "exports_domestic": "domestic_exports", "re_exports": "re_exports", "imports": "imports"}


def update(force=False, **_):
    folder = trade.OUT / "my"
    state = read_json(folder / "release.json", {}) or {}
    with urllib.request.urlopen(urllib.request.Request(URL, headers=UA), timeout=120) as r:
        text = r.read().decode("utf-8")
    fp = hashlib.sha256(text.encode()).hexdigest()[:16]
    if fp == state.get("fingerprint") and not force:
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
    trade.to_usd(rows, "my", 1)
    last = trade.latest(rows)
    folder = trade.write("my", rows)
    code = f"T{last[:7]}"
    write_release(folder, {"code": code, "label": last[:7], "latest_month": last, "source": NAME, "table": "OpenDOSM trade_headline"},
                  [], len(rows), {"fingerprint": fp})
    return {"updated": True, "code": code, "summary": f"{last[:7]}: {len(rows)} rows"}
