"""Indonesia merchandise trade, national sources, as published (US$).

  Bank Indonesia SEKI (bi.go.id/SEKI, BPS data): V.11 exports by destination (FOB) and V.20 imports by origin (CIF),
      thousand US$, monthly from Jan 2005: world (Jumlah), Uni Eropa (EU, BI's grouping), US, HK, IN, JP, KR, CN, TW
      and the ASEAN members.
  BPS WebAPI dataexim (key BPS_KEY): exports and imports by HS code, port and country, US$, for the years BPS serves:
      exports HS chapter 85 (jenishs 1) and the 8-digit codes of chapter 84 summed to 8419, 8470, 8471, 8472, 8473;
      imports 8-digit codes of chapter 27 summed to 2709 (crude oil) and 2710 (petroleum products). World = sum over
      ports and countries (calculated).
Totals before 2005 are not in either source (BPS's WebAPI monthly totals start in 2017).
"""
import re
import time

from core import bps, seki, trade
from core.common import CheckFailed, read_json, write_release

NAME = "trade_id"
DESCRIPTION = "Indonesia merchandise trade (BI SEKI V.11, V.20; BPS dataexim by HS): totals, partners, HS lines, oil"
SEKI_NAMES = {"Jumlah": "WLD", "Uni Eropa": "EU", "Amerika Serikat": "US", "Hong Kong": "HK", "India": "IN", "Jepang": "JP",
              "Korea Selatan": "KR", "Republik Rakyat": "CN", "Taiwan": "TW", "Filipina": "PH", "Malaysia": "MY",
              "Singapura": "SG", "Thailand": "TH", "Vietnam": "VN"}
HS84 = ["8419", "8470", "8471", "8472", "8473"]
BUDGET = 40


def seki_rows(n, flow):
    import xlrd  # noqa: PLC0415
    wb = xlrd.open_workbook(file_contents=seki.download(n))
    vals = {}
    for sh in wb.sheets():
        try:
            rows = seki.read(sh)
        except ValueError:
            continue
        for _r, label, _eng, v in rows:
            lab = re.sub(r"\s+", " ", label).strip()
            iso = next((c for k, c in SEKI_NAMES.items() if lab.startswith(k)), None)
            if iso and "lainnya" not in lab.lower():
                for ym, x in v.items():
                    vals[(iso, ym)] = (x, lab)
    out = []
    for (iso, ym), (x, lab) in vals.items():
        out.append({"economy": "ID", "flow": flow, "partner": iso, "product": "TOTAL", "date": ym + "-01", "value": x,
                    "unit": "USD thousand", "usd_mn": round(x / 1000, 6), "usd_calculated": "", "series": f"SEKI V.{n} {lab}"})
    return out


def dataexim(src, hs, jenis, year):
    js = bps.call(f"dataexim/sumber/{src}/kodehs/{hs}/jenishs/{jenis}/tahun/{year}/periode/1")
    return js.get("data") or [] if js.get("data-availability") == "available" else []


def hs_rows(st, this):
    out = []
    for y in range(this, 2011, -1):
        refresh = y >= this - 1
        for key, args in ((f"x85:{y}", (1, "85", 1)), (f"x84:{y}", (1, "84", 2)), (f"m27:{y}", (2, "27", 2))):
            st.get(key, lambda: dataexim(*args, y), refresh=refresh, budget=BUDGET)
    for key, data in st.data.items():
        kind, y = key.split(":")
        acc = {}
        for x in data or []:
            m = re.match(r"\[(\d+)\]", x.get("bulan") or "")
            code = re.match(r"\[(\d+)\]", x.get("kodehs") or "")
            if not m or not code:
                continue
            d = f"{y}-{int(m.group(1)):02d}-01"
            c = code.group(1)
            if kind == "x85":
                prods = ["HS85"]
            elif kind == "x84":
                prods = [f"HS{p}" for p in HS84 if c.startswith(p)]
            else:
                prods = [f"HS{p}" for p in ("2709", "2710") if c.startswith(p)]
            for p in prods:
                acc[(p, d)] = acc.get((p, d), 0.0) + float(x.get("value") or 0)
        flow = "imports" if kind == "m27" else "exports"
        for (p, d), v in acc.items():
            out.append({"economy": "ID", "flow": flow, "partner": "WLD", "product": p, "date": d, "value": round(v / 1e6, 6),
                        "unit": "USD million", "usd_mn": round(v / 1e6, 6), "usd_calculated": "",
                        "series": f"BPS dataexim {p}: sum over ports and countries"})
    return out


def update(force=False, **_):
    folder = trade.OUT / "id"
    state = read_json(folder / "release.json", {}) or {}
    rows = seki_rows(11, "exports") + seki_rows(20, "imports")
    if not rows:
        raise CheckFailed(["SEKI V.11/V.20: nothing read"])
    st = trade.Store("id")
    warnings = []
    try:
        rows += hs_rows(st, int(time.strftime("%Y")))
    except Exception as e:  # noqa: BLE001
        warnings.append(f"BPS dataexim: {type(e).__name__}: {str(e)[:150]}")
    st.save()
    last = trade.latest(rows)
    missing = set(SEKI_NAMES.values()) - {r["partner"] for r in rows if r["date"] == last}
    if missing:
        raise CheckFailed([f"partners missing in {last}: {sorted(missing)}"])
    folder = trade.write("id", rows)
    code = f"T{last[:7]}h{len(st.data)}"
    write_release(folder, {"code": code, "label": last[:7], "latest_month": last, "source": NAME,
                           "table": "BI SEKI V.11, V.20; BPS WebAPI dataexim"}, warnings, len(rows), {"fetched": st.fetched})
    return {"updated": True, "code": code, "summary": f"{last[:7]}: {len(rows)} rows", "warnings": warnings}
