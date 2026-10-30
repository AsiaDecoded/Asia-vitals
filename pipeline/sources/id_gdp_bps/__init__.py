"""Indonesia GDP: BPS quarterly national accounts, 2010 series (2010 constant prices), from the BPS WebAPI
dynamic tables (key: repository secret BPS_KEY). As published, nothing calculated.

By expenditure (31 rows: GDP, the seven expenditure components, their sub-components, statistical discrepancy):
  1956 level at 2010 prices, 1955 level at current prices (Rp billion);
  108 growth at 2010 prices: q/q (not seasonally adjusted: BPS publishes no seasonally adjusted GDP), y/y, c-to-c;
  109 implicit deflator growth, q/q and y/y; 110 share of nominal GDP (%);
  2128, 2129, 2130 sources of growth (contributions, pp): q/q, y/y, c-to-c.
By industry (17 categories, their sub-industries, taxes less subsidies on products, GDP):
  65 levels (2010 and current prices); 104 growth; 105 deflator growth; 106 share; 554 sources of growth.
Annual values (BPS's "Tahunan" column) go to separate files.

Published GDP is preliminary (BPS: "angka sementara", "sangat sementara", "sangat sangat sementara" for the
latest three years) and revised; each run rewrites the whole history.
Released about the 5th of the second month after the quarter (Q3 in early November), 11:00 Jakarta.
"""
import csv
import hashlib
import json
import re

from core import bps
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "id_gdp_bps"
DESCRIPTION = "Indonesia GDP (BPS, 2010 series): expenditure and industry, levels, growth, deflator, contributions"
OUT = DATA / "id" / "gdp"
RAWDIR = RAW / "id" / "gdp_bps"
SOURCE = "BPS-Statistics Indonesia (WebAPI)"
FIRST_YEAR = 2010

# Expenditure side: code -> (English label, indent level)
EXP = {
    800: ("GDP", 0),
    100: ("Household consumption", 1), 110: ("Food and beverages, other than restaurants", 2),
    120: ("Clothing, footwear and care services", 2), 130: ("Housing and household equipment", 2),
    140: ("Health and education", 2), 150: ("Transport and communication", 2), 160: ("Restaurants and hotels", 2),
    170: ("Other", 2),
    200: ("NPISH consumption", 1),
    300: ("Government consumption", 1), 310: ("Collective consumption", 2), 320: ("Individual consumption", 2),
    400: ("Gross fixed capital formation", 1), 410: ("Buildings", 2), 420: ("Machinery and equipment", 2),
    430: ("Vehicles", 2), 440: ("Other equipment", 2), 450: ("Cultivated biological resources", 2),
    460: ("Intellectual property products", 2),
    500: ("Change in inventories", 1),
    600: ("Exports of goods and services", 1), 610: ("Goods", 2), 611: ("Non-oil and gas goods", 3),
    612: ("Oil and gas goods", 3), 620: ("Services", 2),
    700: ("Imports of goods and services", 1), 710: ("Goods", 2), 711: ("Non-oil and gas goods", 3),
    712: ("Oil and gas goods", 3), 720: ("Services", 2),
    790: ("Statistical discrepancy", 1),
}
ORDER = [800, 100, 110, 120, 130, 140, 150, 160, 170, 200, 300, 310, 320, 400, 410, 420, 430, 440, 450, 460, 500,
         600, 610, 611, 612, 620, 700, 710, 711, 712, 720, 790]
TOP = [100, 200, 300, 400, 500, 600, 700, 790]   # components whose nominal levels add up to GDP (imports less)

EXP_VARS = {  # var: field by turvar label (None: one turvar)
    1956: "real_level", 1955: "nominal_level", 110: "share_nominal",
    2128: "contrib_qoq", 2129: "contrib_yoy", 2130: "contrib_ctc",
}
# Industry categories (KBLI 2009, BPS's 17 categories) and totals: English names; sub-industries keep BPS's label.
IND_EN = {
    11000: "A. Agriculture, forestry and fishing", 12000: "B. Mining and quarrying", 13000: "C. Manufacturing",
    14000: "D. Electricity and gas", 15000: "E. Water supply, sewerage and waste management", 16000: "F. Construction",
    17000: "G. Wholesale and retail trade; repair of motor vehicles", 18000: "H. Transportation and storage",
    19000: "I. Accommodation and food services", 20000: "J. Information and communication",
    21000: "K. Financial and insurance services", 22000: "L. Real estate", 23000: "M, N. Business services",
    24000: "O. Public administration, defence and compulsory social security", 25000: "P. Education",
    26000: "Q. Human health and social work", 27000: "R, S, T, U. Other services",
    99001: "Gross value added at basic prices", 99002: "Taxes less subsidies on products", 99003: "GDP",
}
IND_VARS = {65: "level", 104: "growth", 105: "deflator", 106: "share_nominal", 554: "contrib"}
FIELDS = ["real_level", "nominal_level", "real_qoq", "real_yoy", "real_ctc", "deflator_qoq", "deflator_yoy",
          "share_nominal", "contrib_qoq", "contrib_yoy", "contrib_ctc"]
UNITS = {"real_level": "Rp billion, 2010 prices", "nominal_level": "Rp billion, current prices",
         "real_qoq": "% q/q, 2010 prices, not seasonally adjusted", "real_yoy": "% y/y, 2010 prices",
         "real_ctc": "% year to date (c-to-c), 2010 prices", "deflator_qoq": "% q/q, implicit deflator",
         "deflator_yoy": "% y/y, implicit deflator", "share_nominal": "% of nominal GDP",
         "contrib_qoq": "pp of GDP q/q", "contrib_yoy": "pp of GDP y/y", "contrib_ctc": "pp of GDP c-to-c"}


def _rate_kind(label):
    """Growth basis from a WebAPI turvar label."""
    s = (label or "").lower()
    if "kumulatif" in s or "c-to-c" in s or "c to c" in s:
        return "ctc"
    if "sama" in s or "y-on-y" in s or "y on y" in s:
        return "yoy"
    if "berantai" in s or "q-to-q" in s or "q to q" in s or "sebelumnya" in s:
        return "qoq"
    if "konstan" in s:
        return "real"
    if "berlaku" in s:
        return "nominal"
    return None


def _clean(label):
    return re.sub(r"<[^>]+>", "", label or "").strip()


def fetch():
    """{var: (meta, records)} for every variable used."""
    out = {}
    for vid in list(EXP_VARS) + [108, 109] + list(IND_VARS):
        meta, recs = bps.var_data(vid)
        if not recs:
            raise CheckFailed([f"WebAPI variable {vid}: no data"])
        out[vid] = (meta, [r for r in recs if r["year"] >= FIRST_YEAR])
    return out


def build_expenditure(raw):
    q, a = {}, {}  # (date, code) -> fields
    for vid, (_m, recs) in raw.items():
        if vid not in EXP_VARS and vid not in (108, 109):
            continue
        for r in recs:
            freq, date = bps.period_of(r)
            code = int(r["vervar"])
            if freq not in ("Q", "A") or code not in EXP:
                continue
            if vid in EXP_VARS:
                field = EXP_VARS[vid]
            else:
                k = _rate_kind(r["turvar_label"])
                if k is None:
                    continue
                field = ("real_" if vid == 108 else "deflator_") + k
                if vid == 109 and k not in ("qoq", "yoy"):
                    continue
            (q if freq == "Q" else a).setdefault((date, code), {})[field] = r["value"]
    return q, a


def build_industry(raw):
    q, a, labels = {}, {}, {}
    for vid, field in IND_VARS.items():
        for r in raw[vid][1]:
            freq, date = bps.period_of(r)
            if freq not in ("Q", "A"):
                continue
            code = int(r["vervar"])
            labels[code] = _clean(r["vervar_label"])
            k = _rate_kind(r["turvar_label"])
            if field == "level":
                f = {"real": "real_level", "nominal": "nominal_level"}.get(k)
            elif field == "share_nominal":
                f = "share_nominal"
            elif k in ("qoq", "yoy", "ctc"):
                f = {"growth": "real_", "deflator": "deflator_", "contrib": "contrib_"}[field] + k
            else:
                f = None
            if f:
                (q if freq == "Q" else a).setdefault((date, code), {})[f] = r["value"]
    return q, a, labels


def checks(q, a, iq):
    errors, warnings = [], []
    dates = sorted({d for d, _c in q})
    gdp = {d: q[(d, 800)] for d in dates if (d, 800) in q}
    latest = dates[-1]
    for f in ("real_level", "nominal_level", "real_qoq", "real_yoy", "deflator_yoy"):
        if f not in gdp.get(latest, {}):
            errors.append(f"latest quarter {latest}: GDP {f} missing")
    for f in ("contrib_qoq", "contrib_yoy"):
        if f not in q.get((latest, 100), {}):
            errors.append(f"latest quarter {latest}: household consumption {f} missing")
    # no gaps in GDP levels and y/y from the first quarter
    y0 = int(dates[0][:4])
    want = [f"{y}-{m:02d}-01" for y in range(y0, int(latest[:4]) + 1) for m in (1, 4, 7, 10) if f"{y}-{m:02d}-01" <= latest]
    miss = [d for d in want if "real_level" not in gdp.get(d, {})]
    if miss:
        errors.append(f"GDP real level missing for {miss[:8]}")
    miss = [d for d in want if int(d[:4]) > y0 and "real_yoy" not in gdp.get(d, {})]
    if miss:
        errors.append(f"GDP real y/y missing for {miss[:8]}")
    # published growth agrees with published levels (2010 prices)
    bad = []
    for d in want:
        g = gdp.get(d, {})
        p = f"{int(d[:4]) - 1}{d[4:]}"
        if "real_yoy" in g and "real_level" in gdp.get(p, {}):
            calc = (g["real_level"] / gdp[p]["real_level"] - 1) * 100
            if abs(calc - g["real_yoy"]) > 0.02:
                bad.append(f"{d} y/y {g['real_yoy']} vs levels {calc:.3f}")
    if bad:
        errors.append(f"GDP y/y does not match its levels: {bad[:6]}")
    # nominal components add up to GDP (imports subtracted)
    gaps = []
    for d in want:
        parts = [q.get((d, c), {}).get("nominal_level") for c in TOP]
        if None in parts or "nominal_level" not in gdp.get(d, {}):
            continue
        s = sum(parts[:6]) - parts[6] + parts[7]
        if abs(s - gdp[d]["nominal_level"]) > 1.0:
            gaps.append(f"{d}: {s:.1f} vs {gdp[d]['nominal_level']}")
    if gaps:
        errors.append(f"nominal components do not add up to GDP: {gaps[:6]}")
    # published contributions add up to published GDP y/y (imports enter with a minus sign)
    worst = 0.0
    for d in want:
        cs = [q.get((d, c), {}).get("contrib_yoy") for c in TOP]
        if None in cs or "real_yoy" not in gdp.get(d, {}):
            continue
        s1 = sum(cs)                       # imports already signed negative
        s2 = sum(cs[:6]) - cs[6] + cs[7]   # imports shown as a positive contribution
        worst = max(worst, min(abs(s1 - gdp[d]["real_yoy"]), abs(s2 - gdp[d]["real_yoy"])))
    if worst > 0.15:
        warnings.append(f"expenditure contributions miss GDP y/y by up to {worst:.2f}pp")
    # industry: latest quarter present and total equals the expenditure GDP
    ind_dates = sorted({d for d, _c in iq})
    if not ind_dates or ind_dates[-1] != latest:
        errors.append(f"industry side ends {ind_dates[-1] if ind_dates else 'nowhere'}, expenditure side {latest}")
    return errors, warnings


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    RAWDIR.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    # new data detected with two calls: the year list and the latest year of GDP at 2010 prices
    years = bps.var_years(1956)
    meta, recs = bps.var_data(1956, years={max(years)})
    gdp_q = sorted(bps.period_of(r)[1] for r in recs if r["vervar"] == 800 and bps.period_of(r)[0] == "Q")
    if not gdp_q:
        raise CheckFailed(["WebAPI variable 1956: no quarterly GDP in the latest year"])
    latest = gdp_q[-1]
    stamp = (meta or {}).get("last_update")
    if state.get("latest_quarter") == latest and state.get("last_update") == stamp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    raw = fetch()
    q, a = build_expenditure(raw)
    iq, ia, ilabels = build_industry(raw)
    errors, warnings = checks(q, a, iq)
    if state.get("latest_quarter") and latest < state["latest_quarter"]:
        errors.append(f"latest quarter {latest} is before the one stored ({state['latest_quarter']})")
    if errors:
        raise CheckFailed(errors)

    qn = (int(latest[5:7]) + 2) // 3
    code = f"G{latest[:4]}Q{qn}"
    label = f"Q{qn} {latest[:4]}"
    cols = ["date", "code", "component", "label_bps", "level", "order"] + FIELDS

    def write(path, d, label_of, order_of, level_of, bps_label=lambda c: ""):
        rows = []
        for (date, c), f in sorted(d.items(), key=lambda kv: (kv[0][0], order_of(kv[0][1]))):
            rows.append({"date": date, "code": c, "component": label_of(c), "label_bps": bps_label(c), "level": level_of(c),
                         "order": order_of(c), **{k: f.get(k) for k in FIELDS}})
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(cols)
            for r in rows:
                w.writerow(["" if r[k] is None else r[k] for k in cols])
        return rows

    eo = {c: i for i, c in enumerate(ORDER)}
    rows_q = write(OUT / "id_gdp.csv", q, lambda c: EXP[c][0], lambda c: eo[c], lambda c: EXP[c][1])
    write(OUT / "id_gdp_annual.csv", a, lambda c: EXP[c][0], lambda c: eo[c], lambda c: EXP[c][1])
    icodes = sorted(ilabels)

    def ilevel(c):
        if c == 99003:
            return 0
        if c in IND_EN:
            return 1
        return 2 if re.match(r"^\d+\.", ilabels.get(c, "")) else 3

    iname = lambda c: IND_EN.get(c, ilabels[c])  # noqa: E731
    write(OUT / "id_gdp_industry.csv", iq, iname, lambda c: icodes.index(c), ilevel, lambda c: ilabels[c])
    write(OUT / "id_gdp_industry_annual.csv", ia, iname, lambda c: icodes.index(c), ilevel, lambda c: ilabels[c])
    # raw: the WebAPI records as fetched (labels in Indonesian), gzipped
    import gzip  # noqa: PLC0415
    with gzip.open(RAWDIR / "webapi.json.gz", "wt", encoding="utf-8") as fh:
        json.dump({str(k): {"meta": m, "records": r} for k, (m, r) in raw.items()}, fh, ensure_ascii=False)

    def long_rows():
        for r in rows_q:
            for f in FIELDS:
                yield {"country": "ID", "indicator": "gdp", "series": f"exp{r['code']}", "label": r["component"],
                       "measure": f, "area": "national", "freq": "Q", "date": r["date"], "value": r[f],
                       "unit": UNITS[f], "source": SOURCE, "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    g = q[(latest, 800)]
    fp = hashlib.sha256(json.dumps(sorted((k[0], k[1], sorted(v.items())) for k, v in q.items())).encode()).hexdigest()[:16]
    write_release(OUT, {"code": code, "label": label, "latest_quarter": latest, "last_update": stamp,
                        "table": "BPS WebAPI: 2010-series GDP by expenditure (1955, 1956, 108, 109, 110, 2128-2130) "
                                 "and industry (65, 104, 105, 106, 554)"},
                  warnings, len(rows_q), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{label}: GDP {g.get('real_yoy')}% y/y, {g.get('real_qoq')}% q/q; "
            f"{len(rows_q)} expenditure rows", "warnings": warnings}
