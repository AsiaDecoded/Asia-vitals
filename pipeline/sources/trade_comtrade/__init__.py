"""Annual merchandise trade from UN Comtrade (comtradeapi.un.org, data/v1/get/C/A/HS), as reported to the UN by each
economy's statistical agency, US$. 11 reporters (no Taiwan: not a Comtrade reporter).

  flows:    X exports, M imports; DX domestic exports and RX re-exports where the reporter files them (Hong Kong, Singapore)
  partners: World and the dump's partners (US, China, Hong Kong, Japan, Korea, India, Indonesia, Malaysia, Philippines,
            Singapore, Thailand, Vietnam), less the reporter itself. Taiwan is left out ("Other Asia, nes" in Comtrade).
            EU = sum of the 27 current members (calculated; only years where all 27 are present, with Belgium-Luxembourg
            standing in for Belgium and Luxembourg where the reporter used it).
  products: TOTAL by partner; HS 85, 8419, 8470, 8471, 8472, 8473, 2709, 2710 with World.
  values:   primaryValue (exports f.o.b., imports c.i.f. as reported), US$ million.
Re-fetched for a reporter only when Comtrade's lastReleased for its annual data changes (getDA). Monthly data stays with
the national sources (trade_<cc>). Needs the COMTRADE_KEY secret (free Comtrade subscription key).
Output: data/trade/annual/trade_annual.csv.
"""
import csv
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from core import trade
from core.common import CheckFailed, read_json, write_release

NAME = "trade_comtrade"
DESCRIPTION = "Annual trade by partner and HS line, 11 Asian reporters (UN Comtrade, US$)"
BASE = "https://comtradeapi.un.org/data/v1/"
REPORTERS = {"JP": 392, "KR": 410, "HK": 344, "CN": 156, "IN": 699, "ID": 360, "TH": 764, "MY": 458, "SG": 702,
             "PH": 608, "VN": 704}
PARTNERS = {0: "WLD", 842: "US", 156: "CN", 344: "HK", 392: "JP", 410: "KR", 699: "IN", 360: "ID", 458: "MY", 608: "PH",
            702: "SG", 764: "TH", 704: "VN"}
EU = {40: "AT", 56: "BE", 100: "BG", 191: "HR", 196: "CY", 203: "CZ", 208: "DK", 233: "EE", 246: "FI", 251: "FR",
      276: "DE", 300: "GR", 348: "HU", 372: "IE", 380: "IT", 428: "LV", 440: "LT", 442: "LU", 470: "MT", 528: "NL",
      616: "PL", 620: "PT", 642: "RO", 703: "SK", 705: "SI", 724: "ES", 752: "SE"}
BELLUX = 58
HS = ["85", "8419", "8470", "8471", "8472", "8473", "2709", "2710"]
FLOWS = {"X": "exports", "M": "imports", "DX": "domestic_exports", "RX": "re_exports"}
FIRST = 1988
OUT = trade.OUT / "annual"
COLS = ["economy", "flow", "partner", "product", "year", "usd_mn", "calculated", "classification", "series"]


def get(path, **params):
    key = os.environ.get("COMTRADE_KEY", "").strip()
    if not key:
        raise CheckFailed(["COMTRADE_KEY secret is empty"])
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    err = None
    for i in range(5):
        try:
            rq = urllib.request.Request(url, headers={"Ocp-Apim-Subscription-Key": key, "User-Agent": "asia-vitals pipeline"})
            with urllib.request.urlopen(rq, timeout=180) as r:
                js = json.loads(r.read())
            time.sleep(1.2)
            if js.get("error"):
                raise RuntimeError(js["error"])
            return js.get("data") or []
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code}: {e.read()[:200]!r}"
            if e.code not in (429, 500, 502, 503, 504):
                break
        except Exception as e:  # noqa: BLE001
            err = repr(e)[:200]
        time.sleep(10 * (i + 1))
    raise RuntimeError(f"Comtrade {path} {params.get('reporterCode')} {params.get('period', '')[:9]}: {err}")


VERSION = 3
MISSING = {}


def reporter_rows(cc, code, last_year):
    partners = ",".join(str(p) for p in list(PARTNERS) + list(EU) + [BELLUX] if p != code)
    raw = {}
    for y0 in range(FIRST, last_year + 1, 12):
        years = ",".join(str(y) for y in range(y0, min(y0 + 12, last_year + 1)))
        for x in get("get/C/A/HS", reporterCode=code, period=years, partnerCode=partners, cmdCode="TOTAL," + ",".join(HS),
                     flowCode=",".join(FLOWS), partner2Code=0, customsCode="C00", motCode=0):
            k = (x["flowCode"], x["partnerCode"], str(x["cmdCode"]), int(x["period"]))
            if k not in raw or x.get("isOriginalClassification"):
                raw[k] = (x["primaryValue"], x.get("classificationCode", ""))
    rows = []
    for (fl, p, cmd, y), (v, cl) in raw.items():
        if v is None or p not in PARTNERS or (cmd != "TOTAL" and p != 0):
            continue
        rows.append({"economy": cc, "flow": FLOWS[fl], "partner": PARTNERS[p], "product": "TOTAL" if cmd == "TOTAL" else f"HS{cmd}",
                     "year": y, "usd_mn": round(v / 1e6, 6), "calculated": "", "classification": cl,
                     "series": f"UN Comtrade C/A/HS reporter {code} partner {p} cmd {cmd} flow {fl}"})
    # EU-27, calculated
    for fl in FLOWS:
        for y in {k[3] for k in raw if k[0] == fl}:
            got = {p: raw[(fl, p, "TOTAL", y)][0] for p in list(EU) + [BELLUX] if (fl, p, "TOTAL", y) in raw}
            members = {p: v for p, v in got.items() if p in EU}
            if 56 not in members and 442 not in members and BELLUX in got:
                members[56], members[442] = got[BELLUX], 0.0
            if len(members) < len(EU) and y == last_year:
                MISSING[(cc, fl)] = sorted(EU[p] for p in EU if p not in members)
            if len(members) == len(EU) and all(v is not None for v in members.values()):
                rows.append({"economy": cc, "flow": FLOWS[fl], "partner": "EU", "product": "TOTAL", "year": y,
                             "usd_mn": round(sum(members.values()) / 1e6, 6), "calculated": "y", "classification": "",
                             "series": "UN Comtrade: sum of the 27 EU members (calculated)"})
    return rows


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "trade_annual.csv"
    old = list(csv.DictReader(path.open())) if path.exists() else []
    rel = read_json(OUT / "release.json", {}) or {}
    state = rel.get("released", {}) if rel.get("version") == VERSION else {}
    warns, released, keep, fresh = [], {}, [], []
    for cc, code in REPORTERS.items():
        try:
            da = get("getDA/C/A/HS", reporterCode=code)
        except Exception as e:  # noqa: BLE001
            warns.append(str(e))
            da = []
        stamp = max((d.get("lastReleased") or "" for d in da), default="")
        last = max((int(d["period"]) for d in da), default=None)
        released[cc] = stamp or state.get(cc, "")
        mine = [r for r in old if r["economy"] == cc]
        if not da or (stamp == state.get(cc) and mine and not force):
            keep += mine
            continue
        try:
            fresh += reporter_rows(cc, code, last)
        except Exception as e:  # noqa: BLE001
            warns.append(f"{cc}: {e}")
            keep += mine
            released[cc] = state.get(cc, "")
    if not fresh and keep == old and old:
        return {"updated": False, "summary": "no new Comtrade annual releases", "warnings": warns}
    rows = keep + fresh
    if not rows:
        raise CheckFailed(["Comtrade: no rows"] + warns[:5])
    for r in rows:
        r["year"] = int(r["year"])
    rows.sort(key=lambda r: (r["economy"], r["flow"], r["partner"], r["product"], r["year"]))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    have = sorted({r["economy"] for r in rows})
    latest = {cc: max(r["year"] for r in rows if r["economy"] == cc and r["partner"] == "WLD" and r["product"] == "TOTAL")
              for cc in have}
    code = "A" + max(released.values() or [""])[:10]
    write_release(OUT, {"code": code, "label": "UN Comtrade annual", "latest_year": latest, "released": released,
                        "source": NAME, "version": VERSION, "table": "UN Comtrade data/v1/get/C/A/HS",
                        "eu_missing_latest_year": {f"{k[0]} {k[1]}": v for k, v in MISSING.items()}}, warns[:20], len(rows))
    return {"updated": True, "code": code, "warnings": warns[:5],
            "summary": f"{len(rows)} rows; refreshed {sorted({r['economy'] for r in fresh})}; latest years {latest}"}
