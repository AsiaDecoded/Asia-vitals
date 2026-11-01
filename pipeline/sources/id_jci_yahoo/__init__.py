"""Indonesia stock market: Jakarta Composite Index (^JKSE), daily close, points, from Yahoo Finance via the yfinance
library (cookie and crumb; the bare chart API answers 429 to GitHub's runners). Asked for 1 Nov 2026 (Financial tab,
daily chart). Not an official source: Yahoo's pre-2010 history has errors (13 of 352 month-ends differ from SEKI III.3 by
0.5-15%, all 1999-2009; Jan 2002 +15%), and it may revise without notice. The monthly chart stays on SEKI III.3
(id_jci_seki); this feeds the daily chart only.
"""
import csv
import hashlib
import json

from core.common import DATA, CheckFailed, read_json, write_long, write_release

NAME = "id_jci_yahoo"
DESCRIPTION = "Indonesia Jakarta Composite Index, daily close, Yahoo Finance"
OUT = DATA / "id" / "jci"
SOURCE = "Yahoo Finance (^JKSE), not an official source"
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fetch():
    import yfinance as yf  # noqa: PLC0415
    df = yf.Ticker("^JKSE").history(period="max", interval="1d", auto_adjust=False)
    return {ix.strftime("%Y-%m-%d"): float(v) for ix, v in df["Close"].items() if v == v and v > 0}


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release_daily.json", {}) or {}
    s = fetch()
    ds = sorted(s)
    errors, warnings = [], []
    if not ds or ds[0] > "1990-12-31":
        errors.append(f"series starts {ds[:1]}")
    if not (250 < s.get("1998-09-30", 0) < 300):
        errors.append(f"30 Sep 1998 close {s.get('1998-09-30')} outside 250-300")
    if state.get("latest") and ds and ds[-1] < state["latest"]:
        errors.append(f"latest day {ds[-1]} before the stored {state['latest']}")
    if len(ds) < 8000:
        errors.append(f"only {len(ds)} days")
    jumps = [b for a, b in zip(ds, ds[1:]) if not 0.75 < s[b] / s[a] < 1.33]
    if jumps:
        warnings.append(f"daily moves beyond -25%/+33%: {jumps[:5]}")
    if errors:
        raise CheckFailed(errors)
    fp = hashlib.sha256(json.dumps(s, sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {ds[-1]})"}
    with open(OUT / "id_jci_daily.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["date", "close"])
        for k in ds:
            w.writerow([k, round(s[k], 2)])
    last = ds[-1]
    code = f"Y{last}"
    label = f"JCI daily to {int(last[8:])} {MON[int(last[5:7]) - 1]} {last[:4]} (Yahoo Finance)"
    nlong = write_long(({"country": "ID", "indicator": "jci", "series": "jkse_daily", "label": "Jakarta Composite Index, daily close",
                         "measure": "level", "area": "", "freq": "D", "date": k, "value": round(s[k], 2), "unit": "index points",
                         "source": SOURCE, "release": code} for k in ds), OUT / "long_daily.csv")
    # own release file: release.json / release_row.json in this folder belong to id_jci_seki
    meta = {"code": code, "label": label, "latest": last, "fingerprint": fp, "rows": len(ds), "long_rows": nlong, "warnings": warnings}
    (OUT / "release_daily.json").write_text(json.dumps(meta, indent=1))
    with open(OUT / "id_jci_daily_latest.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["date", "close", "label"])
        w.writerow([last, round(s[last], 2), label])
    return {"updated": True, "code": code, "summary": f"{ds[0]}..{last}; {len(ds)} days; latest {s[last]:,.2f}", "warnings": warnings}
