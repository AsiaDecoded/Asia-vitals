"""Japan merchandise trade: Ministry of Finance, Trade Statistics of Japan (customs.go.jp), as published.

Files (no key; "suii" time-series CSVs, Shift-JIS, thousand yen, monthly from 1979):
  d41ma.csv            world: Exp-Total, Imp-Total
  d42ma001..009.csv    by region, one column pair per country (MOF country codes): partners
  d42ma010.csv         EU member countries (EU = sum of the 27 current members, calculated)
  d61ma.csv            imports by principal commodity, from 1988: 原油及び粗油 (30301, crude oil) and
                       石油製品 (30303, petroleum products); value in thousand yen
US$: converted at the BIS monthly average yen rate (calculated). HS-line exports (block 3) are not in these files
(9-digit commodity files on e-Stat; to add).
"""
import csv
import hashlib
import io
import json
import urllib.request

from core import trade
from core.common import CheckFailed, read_json, write_release

NAME = "trade_jp"
DESCRIPTION = "Japan merchandise trade (MOF customs CSVs): totals, partners, crude and petroleum product imports"
BASE = "https://www.customs.go.jp/toukei/suii/html/data/"
UA = {"User-Agent": "Mozilla/5.0 (asia-vitals data pipeline; github.com/AsiaDecoded)"}
CODES = {"103": "KR", "105": "CN", "106": "TW", "108": "HK", "110": "VN", "111": "TH", "112": "SG", "113": "MY",
         "117": "PH", "118": "ID", "123": "IN", "304": "US"}
EU_NAMES = {"SWEDEN": "SE", "DENMARK": "DK", "IRELAND": "IE", "NETHLDS": "NL", "BELGIUM": "BE", "LUXMBRG": "LU",
            "FRANCE": "FR", "GERMANY": "DE", "PORTUGL": "PT", "SPAIN": "ES", "ITALY": "IT", "MALTA": "MT", "FINLAND": "FI",
            "POLAND": "PL", "AUSTRIA": "AT", "HUNGARY": "HU", "GREECE": "GR", "ROMANIA": "RO", "BULGAR": "BG", "CYPRUS": "CY",
            "ESTONIA": "EE", "LATVIA": "LV", "LITHUAN": "LT", "CROATIA": "HR", "SLOVENI": "SI", "CZECH": "CZ", "SLOVAK": "SK"}
UNIT = "JPY thousand"


def fetch(name, tries=3):
    err = None
    for _ in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(BASE + name, headers=UA), timeout=90) as r:
                return r.read().decode("cp932", "replace")
        except Exception as e:  # noqa: BLE001
            err = e
    raise CheckFailed([f"MOF {name}: {err!r}"])


def num(v):
    v = (v or "").strip().replace(",", "")
    try:
        return float(v)
    except ValueError:
        return None


def ym(s):
    s = s.strip()
    return f"{s[:4]}-{s[5:7]}-01" if len(s) >= 7 and s[4] == "/" and s[:4].isdigit() else None


def pairs(text):
    """{(code, 'exports'|'imports'): {date: value}} from a d4* file; names {code: name} from the row under the codes."""
    rows = list(csv.reader(io.StringIO(text)))
    hi = next(i for i, r in enumerate(rows) if r and r[0].strip() == "Years/Months")
    hdr, names = rows[hi], rows[hi + 1]
    out, nm = {}, {}
    for j, h in enumerate(hdr):
        h = h.strip()
        if h[:4] in ("Exp-", "Imp-"):
            code = h[4:]
            flow = "exports" if h.startswith("Exp") else "imports"
            if code != "Total" and j < len(names):
                nm[code] = names[j].strip()
            series = out.setdefault((code, flow), {})
            for r in rows[hi + 2:]:
                d = ym(r[0]) if r else None
                if d and j < len(r):
                    series[d] = num(r[j])
    return out, nm


def row(flow, partner, product, d, v, series):
    return {"economy": "JP", "flow": flow, "partner": partner, "product": product, "date": d, "value": v, "unit": UNIT,
            "usd_mn": None, "usd_calculated": "", "series": series}


def update(force=False, **_):
    folder = trade.OUT / "jp"
    folder.mkdir(parents=True, exist_ok=True)
    state = read_json(folder / "release.json", {}) or {}
    texts = {n: fetch(n + ".csv") for n in ["d41ma"] + [f"d42ma{i:03d}" for i in range(1, 11)] + ["d61ma"]}
    fp = hashlib.sha256(json.dumps(texts, sort_keys=True).encode()).hexdigest()[:16]
    if fp == state.get("fingerprint") and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    world, _ = pairs(texts["d41ma"])
    live = {d for d, v in world[("Total", "exports")].items() if v}      # future months are published as 0
    rows = []
    for flow in ("exports", "imports"):
        rows += [row(flow, "WLD", "TOTAL", d, v, f"d41ma {flow[:3].title()}-Total") for d, v in sorted(world[("Total", flow)].items()) if d in live]
    found = set()
    for i in range(1, 11):
        data, names = pairs(texts[f"d42ma{i:03d}"])
        for (code, flow), s in data.items():
            if i == 10:
                iso = EU_NAMES.get(names.get(code, ""))
            else:
                iso = CODES.get(code)
            if not iso or code == "Total":
                continue
            found.add(iso)
            rows += [row(flow, iso, "TOTAL", d, v, f"d42ma{i:03d} {code} {names.get(code, '')}") for d, v in sorted(s.items())
                     if d in live and v is not None]
    miss = (set(CODES.values()) | set(trade.EU27)) - found
    if miss:
        raise CheckFailed([f"partners not found in MOF files: {sorted(miss)}"])
    # oil: principal commodity imports (value columns)
    r61 = list(csv.reader(io.StringIO(texts["d61ma"])))
    ci = next(i for i, r in enumerate(r61) if r and r[0].strip() == "概況品コード")
    codes, kinds = r61[ci], r61[ci + 1]
    for code, prod, label in (("'30301'", "crude_oil", "原油及び粗油 (30301)"), ("'30303'", "petroleum_products", "石油製品 (30303)")):
        k = next((k for k, c in enumerate(codes) if c.strip() == code), None)
        # labels sit one column left of their value column (金額, thousand yen), except the first
        j = None if k is None else (k if kinds[k].strip() == "金額" else k + 1)
        if j is None or kinds[j].strip() != "金額":
            raise CheckFailed([f"d61ma: column {code} not found"])
        for r in r61[ci + 2:]:
            d = ym(r[0]) if r else None
            if d and d in live and j < len(r) and num(r[j]) is not None:
                rows.append(row("imports", "WLD", prod, d, num(r[j]), f"d61ma {label}"))
    trade.to_usd(rows, "jp", 1000)
    rows += trade.eu_sum(rows, trade.EU27)
    # checks
    errors = []
    last = max(live)
    for flow in ("exports", "imports"):
        tot = next(float(r["value"]) for r in rows if r["flow"] == flow and r["partner"] == "WLD" and r["product"] == "TOTAL" and r["date"] == last)
        part = sum(float(r["value"]) for r in rows if r["flow"] == flow and r["partner"] in trade.PARTNERS[1:] and r["partner"] != "EU"
                   and r["product"] == "TOTAL" and r["date"] == last)
        if not 0.3 < part / tot < 1:
            errors.append(f"{flow} {last}: listed partners are {part / tot:.0%} of the total")
    if any(r["usd_mn"] in (None, "") for r in rows if r["date"] >= "1980-01-01"):
        errors.append("US$ conversion missing for some months (BIS yen rate)")
    if errors:
        raise CheckFailed(errors)
    folder = trade.write("jp", rows)
    code = f"T{last[:7]}"
    label = f"{last[:7]}"
    write_release(folder, {"code": code, "label": label, "latest_month": last, "source": NAME,
                           "table": "MOF customs suii CSVs d41ma, d42ma001-010, d61ma"}, [], len(rows), {"fingerprint": fp})
    return {"updated": True, "code": code, "summary": f"{label}: {len(rows)} rows"}
