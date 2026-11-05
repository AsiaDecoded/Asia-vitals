"""Manufacturing production indices and manufacturing GVA for the Asia dashboard's Manufacturing tab, for the economies
with no manufacturing source of their own in the repo: Japan, South Korea, Taiwan, Malaysia, Singapore, Hong Kong (asked for
4 Nov 2026, Taiwan 5 Nov; definitions in the project doc claude/asia-mfg-definitions.md). India, Thailand, Vietnam, the Philippines
and Indonesia are read from their own sources' files by pipeline/core/asia_mfg.py, not fetched here.

Agencies' sites are reachable from GitHub's runners only. Each economy is fetched and checked on its own; one that
fails keeps its previous rows and is reported as a warning.

Writes data/asia/mfg/:
  src_iip.csv  economy, freq (M/Q), date (first day of the period), industry, index, yoy, yoy_calculated, note
               industry: mfg, 19, 20, 21, 23, 24, 26, 27, elec (ISIC 26), nonelec (manufacturing less 26) (codes are ISIC Rev. 4 divisions; the national
               industry each maps to is in `note`). index as published; yoy as published where the agency publishes
               it, otherwise index / index a year earlier - 1 (yoy_calculated = y). elec where published or
               constructed (Japan, Taiwan, Singapore cluster); nonelec where the agency publishes weights (Japan) or
               implied weights can be recovered from the published divisions (Taiwan, Korea, Malaysia, Singapore).
  src_gva.csv  economy, freq (Q/A), period (YYYY-Qn or YYYY), real_yoy (%), share (% of GDP, current prices),
               real_yoy_calculated, share_calculated, note
  long.csv, release.json, release_row.json (code F<hash>)

Sources:
  Japan     METI Indices of Industrial Production, 2020 = 100, original index, value-added weights (b2020_gom1j.xlsx).
            Pharma (21) = 化学工業 less 化学工業（除．医薬品） at METI's weights; elec (ISIC 26) = 電子部品・デバイス + 情報通信機械
            (electrical machinery, ISIC 27, left out: decision 5 Nov 2026);
            27 = 電気機械工業; nonelec = 製造工業 less elec, at METI's weights (calculated). GVA: not yet (ESRI production-side QNA).
  Korea     Statistics Korea mining and manufacturing production index (2020 = 100, original), Bank of Korea ECOS
            901Y032 by KSIC division (ISIC 27 = KSIC 28 전기장비). GVA: ECOS 200Y106 (real, original) and 200Y105
            (nominal), manufacturing and GDP. nonelec = 제조업 less KSIC 26 at implied weights (24 divisions,
            three-year windows; weights re-set yearly).
  Taiwan    MOEA industrial production index, 2021 = 100, chain-linked, NSA (data.gov.tw 6607, d.csv, by TSIC):
            mfg = 製造業; elec = 資訊電子工業 (TSIC 26 + 27 = ISIC 26, published); 19 = TSIC 17; 21 = TSIC 20; 23; 24;
            27 = TSIC 28. Constructed at MOEA's implicit weights (each year's group index is an exact linear combination
            of its divisions; weights recovered by least squares per year from 2009, chain-linked at December):
            nonelec = 製造業 less 資訊電子工業; 20 = TSIC 18 + 19 (check: rebuilding 化學工業 this way is within 0.24 pp of
            the published y/y on average, 0.9 pp at most; 製造業 within 0.05 pp). GVA: DGBAS production-side
            quarterly national accounts (生產帳_季 xlsx, linked from stat.gov.tw cp.aspx?n=2674): C 製造業 chained
            2021 dollars (y/y calculated); share = nominal C / GDP.
  Malaysia  DOSM Industrial Production Index, 2015 = 100 (OpenDOSM ipi_2d by MSIC division, ipi_1d section C).
            GVA: OpenDOSM gdp_qtr_real_supply and gdp_qtr_nominal_supply, sector p3. nonelec = section C less MSIC 26 at implied
            fixed (2015) weights (exact fit).
  Singapore EDB IIP by industry cluster, 2025 = 100, NSA (SingStat M355381): mfg = Total, elec = Electronics cluster,
            19 = Petroleum segment, 20 = Petrochemicals segment, 21 = Pharmaceuticals segment (clusters, not ISIC);
            nonelec = Total less Electronics cluster at implied cluster weights (exact per year from 2011).
            GVA: SingStat M015661 (chained 2015 dollars) and M015651 (current prices).
  Hong Kong C&SD Index of Industrial Production, 2015 = 100, quarterly (610-65001), manufacturing only.
            GVA: 310-34501 real y/y (quarterly), 310-34101 % contribution to GDP (annual, basic prices).
"""
import csv
import hashlib
import io
import json
import re
import urllib.parse
import urllib.request

from core.common import DATA, CheckFailed, read_json, write_long, write_release

NAME = "mfg_asia"
DESCRIPTION = "Manufacturing production indices and GVA for the Asia Manufacturing tab: JP, KR, TW, MY, SG, HK"
OUT = DATA / "asia" / "mfg"
IIP_COLS = ["economy", "freq", "date", "industry", "index", "yoy", "yoy_calculated", "note"]
GVA_COLS = ["economy", "freq", "period", "real_yoy", "share", "real_yoy_calculated", "share_calculated", "note"]
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}


def fetch(url, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def f(x):
    try:
        v = float(str(x).replace(",", ""))
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def calc_yoy(rows):
    """Fill yoy from index a year earlier where the agency publishes none (same freq, industry)."""
    ix = {(r["economy"], r["freq"], r["industry"], r["date"]): r["index"] for r in rows if r["index"] is not None}
    for r in rows:
        if r.get("yoy") is None and r["index"] is not None:
            p = f"{int(r['date'][:4]) - 1}{r['date'][4:]}"
            b = ix.get((r["economy"], r["freq"], r["industry"], p))
            if b:
                r["yoy"], r["yoy_calculated"] = round((r["index"] / b - 1) * 100, 2), "y"
    return rows


def row(economy, freq, date, industry, index, yoy=None, note=""):
    return {"economy": economy, "freq": freq, "date": date, "industry": industry, "index": index, "yoy": yoy,
            "yoy_calculated": "", "note": note}


# ---------- Japan ----------
JP_URL = "https://www.meti.go.jp/statistics/tyo/iip/xls/b2020_gom1j.xlsx"
JP_ROWS = {"mfg": "製造工業", "19": "石油・石炭製品工業", "20": "化学工業（除．医薬品）", "23": "窯業・土石製品工業",
           "24": "鉄鋼・非鉄金属工業", "26a": "電子部品・デバイス工業", "e2": "情報通信機械工業", "chem": "化学工業",
           "27": "電気機械工業"}


def japan():
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(fetch(JP_URL)), read_only=True, data_only=True)
    ws = [w for w in wb.worksheets if w.title == "生産"] or wb.worksheets[1:2]
    rows = list(ws[0].iter_rows(values_only=True))
    hdr = next(r for r in rows if r and r[0] == "品目番号")
    periods = [re.sub(r"\D", "", str(h)) for h in hdr]
    by = {r[1]: r for r in rows if r and r[1] in JP_ROWS.values()}
    miss = [n for n in JP_ROWS.values() if n not in by]
    if miss:
        raise CheckFailed([f"JP: rows not found {miss}"])
    w = {k: float(by[n][2]) for k, n in JP_ROWS.items()}
    series = {}
    for k, n in JP_ROWS.items():
        series[k] = {f"{p[:4]}-{p[4:6]}-01": float(v) for p, v in zip(periods, by[n]) if len(p) == 6 and isinstance(v, (int, float))}
    out = []
    note = {"mfg": "製造工業", "19": "石油・石炭製品工業", "20": "化学工業（除．医薬品）", "23": "窯業・土石製品工業",
            "24": "鉄鋼・非鉄金属工業 (ISIC 24)", "27": "電気機械工業 (JSIC 29; ~ISIC 27, includes electrical measuring instruments)", "21": "医薬品 = 化学工業 less 化学工業（除．医薬品）, METI weights (calculated)",
            "elec": "ISIC 26: 電子部品・デバイス + 情報通信機械, METI weights (calculated)",
            "nonelec": "製造工業 less ISIC 26 electronics and 電気機械工業 (27), METI weights (calculated)"}
    for d in sorted(series["mfg"]):
        s = {k: series[k].get(d) for k in series}
        if None in s.values():
            continue
        for k in ("mfg", "19", "20", "23", "24", "27"):
            out.append(row("JP", "M", d, k, s[k], note=note[k]))
        out.append(row("JP", "M", d, "21", round((w["chem"] * s["chem"] - w["20"] * s["20"]) / (w["chem"] - w["20"]), 3), note=note["21"]))
        we = w["26a"] + w["e2"]
        el = (w["26a"] * s["26a"] + w["e2"] * s["e2"]) / we
        out.append(row("JP", "M", d, "elec", round(el, 3), note=note["elec"]))
        out.append(row("JP", "M", d, "nonelec", round((w["mfg"] * s["mfg"] - we * el - w["27"] * s["27"]) / (w["mfg"] - we - w["27"]), 3), note=note["nonelec"]))
    if len(out) < 500:
        raise CheckFailed([f"JP: only {len(out)} rows"])
    return out, []


# ---------- Korea ----------
KR_ITEMS = {"mfg": ("I11AC", "제조업"), "19": ("I11ACJ", "코크스, 연탄 및 석유정제품"), "20": ("I11ACK", "화학물질 및 화학제품; 의약품 제외"),
            "21": ("I11ACL", "의료용 물질 및 의약품"), "23": ("I11ACN", "비금속 광물제품"), "24": ("I11ACO", "1차 금속"),
            "26": ("I11ACQ", "전자부품, 컴퓨터, 영상 음향 및 통신장비 (KSIC 26)"), "27": ("I11ACS", "전기장비 (KSIC 28)")}

KR_DIVS = [f"I11AC{c}" for c in "ABCDEFGHIJKLMNOPQRSTUVWX"]   # the 24 KSIC manufacturing divisions (10-33)


def korea():
    from core import ecos
    out = []
    for k, (code, name) in KR_ITEMS.items():
        rs = ecos._paged("StatisticSearch", ["901Y032", "M", "201501", "203012", code, "1"])
        for r in rs:
            v = f(r.get("DATA_VALUE"))
            t = r.get("TIME", "")
            if v is not None and len(t) == 6:
                out.append(row("KR", "M", f"{t[:4]}-{t[4:]}-01", k, v, note=name))
    # rest: manufacturing less KSIC 26 (electronics column) and 28 (= ISIC 27) at Statistics Korea's implied weights. Weights are
    # re-set each year and ECOS has one decimal, so each year is fitted on that year and its neighbours (24 divisions);
    # check 5 Nov 2026: manufacturing rebuilt this way is within 0.1 pp of the published y/y (median), 0.6 pp at most.
    S = {"MFG": {(int(x["date"][:4]), int(x["date"][5:7])): x["index"] for x in out if x["industry"] == "mfg"}}
    for c in KR_DIVS:
        for r in ecos._paged("StatisticSearch", ["901Y032", "M", "201501", "203012", c, "1"]):
            v, t = f(r.get("DATA_VALUE")), r.get("TIME", "")
            if v is not None and len(t) == 6:
                S.setdefault(c, {})[(int(t[:4]), int(t[4:]))] = v
    if len(S) < 25:
        raise CheckFailed([f"KR: only {len(S) - 1} of 24 divisions"])
    coef = implied_weights(S, "MFG", KR_DIVS, 2015, win=1, min_months=1, tol=1.5, label="KR")
    out += implied_rows("KR", S, coef, [c for c in KR_DIVS if c not in ("I11ACQ", "I11ACS")], "nonelec",
                        "제조업 less KSIC 26 and 28 (ISIC 26, 27), implied weights fitted over three years, chain-linked (calculated)", 2020)
    gva = []
    real = {r["TIME"]: f(r["DATA_VALUE"]) for r in ecos._paged("StatisticSearch", ["200Y106", "Q", "2014Q1", "2030Q4", "1103"])}
    nom = {r["TIME"]: f(r["DATA_VALUE"]) for r in ecos._paged("StatisticSearch", ["200Y105", "Q", "2014Q1", "2030Q4", "1103"])}
    gdp = {r["TIME"]: f(r["DATA_VALUE"]) for r in ecos._paged("StatisticSearch", ["200Y105", "Q", "2014Q1", "2030Q4", "1400"])}
    for t in sorted(real):
        p = f"{int(t[:4]) - 1}{t[4:]}"
        ry = round((real[t] / real[p] - 1) * 100, 2) if real.get(p) and real.get(t) else None
        sh = round(nom[t] / gdp[t] * 100, 2) if nom.get(t) and gdp.get(t) else None
        gva.append({"economy": "KR", "freq": "Q", "period": f"{t[:4]}-{t[4:]}", "real_yoy": ry, "share": sh,
                    "real_yoy_calculated": "y", "share_calculated": "y",
                    "note": "BoK ECOS 200Y106 (real, chained 2020, original) and 200Y105 (nominal), item 1103 manufacturing, 1400 GDP"})
    if len(out) < 500:
        raise CheckFailed([f"KR: only {len(out)} index rows"])
    return out, gva


# ---------- Malaysia ----------
def malaysia():
    from core import dosm
    out = []
    names = {"19": "MSIC 19", "20": "MSIC 20", "21": "MSIC 21", "23": "MSIC 23", "24": "MSIC 24", "26": "MSIC 26", "27": "MSIC 27"}
    rows2 = dosm.rows(dosm.raw_csv("ipi/ipi_2d.csv"))
    for r in rows2:
        if r["series"] == "abs" and r["division"] in names:
            out.append(row("MY", "M", r["date"], r["division"], f(r["index"]), note=names[r["division"]]))
    for r in dosm.rows(dosm.raw_csv("ipi/ipi_1d.csv")):
        if r["series"] == "abs" and r["section"] == "C":
            out.append(row("MY", "M", r["date"], "mfg", f(r["index"]), note="Section C, manufacturing"))
    # rest: section C less MSIC 26 and 27 at DOSM's implied weights (fixed 2015 weights: one fit over all years)
    S = {}
    for r in rows2:
        if r["series"] == "abs" and r["division"].isdigit() and 10 <= int(r["division"]) <= 33 and f(r["index"]) is not None:
            S.setdefault(r["division"], {})[(int(r["date"][:4]), int(r["date"][5:7]))] = f(r["index"])
    S["C"] = {(int(x["date"][:4]), int(x["date"][5:7])): x["index"] for x in out if x["industry"] == "mfg"}
    divs = sorted(k for k in S if k != "C")
    coef = implied_weights(S, "C", divs, 2015, win=50, min_months=1, tol=0.05, label="MY")
    out += implied_rows("MY", S, coef, [d_ for d_ in divs if d_ not in ("26", "27")], "nonelec",
                        "Section C less MSIC 26 and 27, DOSM implied weights (calculated)", 2015)
    gva = []
    real = {r["date"]: f(r["value"]) for r in dosm.rows(dosm.raw_csv("gdp/gdp_qtr_real_supply.csv")) if r["series"] == "abs" and r["sector"] == "p3"}
    ry = {r["date"]: f(r["value"]) for r in dosm.rows(dosm.raw_csv("gdp/gdp_qtr_real_supply.csv")) if r["series"] == "growth_yoy" and r["sector"] == "p3"}
    nom = {}
    for r in dosm.rows(dosm.raw_csv("gdp/gdp_qtr_nominal_supply.csv")):
        if r["series"] == "abs" and r["sector"] in ("p0", "p3"):
            nom.setdefault(r["date"], {})[r["sector"]] = f(r["value"])
    for d in sorted(real):
        q = (int(d[5:7]) - 1) // 3 + 1
        n = nom.get(d, {})
        gva.append({"economy": "MY", "freq": "Q", "period": f"{d[:4]}-Q{q}", "real_yoy": ry.get(d),
                    "share": round(n["p3"] / n["p0"] * 100, 2) if n.get("p3") and n.get("p0") else None,
                    "real_yoy_calculated": "", "share_calculated": "y",
                    "note": "DOSM gdp_qtr_real_supply (constant 2015 prices) and gdp_qtr_nominal_supply, sector p3"})
    if len(out) < 500:
        raise CheckFailed([f"MY: only {len(out)} index rows"])
    return out, gva


# ---------- Singapore ----------
MON = {m: i + 1 for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
SG_ROWS = {"Total": "mfg", "Electronics Cluster": "elec", "Petroleum": "19", "Petrochemicals": "20", "Pharmaceuticals": "21"}


def singapore():
    from core import singstat
    out = []
    t = singstat.table("M355381")
    for r in t["rows"]:
        k = SG_ROWS.get((r["rowText"] or "").strip())
        if not k:
            continue
        for c in r["columns"]:
            y, m = c["key"].split()
            out.append(row("SG", "M", f"{y}-{MON[m]:02d}-01", k, f(c["value"]),
                           note=f"EDB cluster/segment: {r['rowText'].strip()} (not ISIC)"))
    # non-electronics: Total less Electronics cluster, at EDB's implied cluster weights (re-set each year)
    S = {}
    for r in t["rows"]:
        if r.get("seriesNo") in ("1", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6"):
            for c in r["columns"]:
                y, m = c["key"].split()
                if f(c["value"]) is not None:
                    S.setdefault(r["seriesNo"], {})[(int(y), MON[m])] = f(c["value"])
    cl = ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6"]
    coef = implied_weights(S, "1", cl, 2011, min_months=6, tol=0.1, label="SG")
    out += implied_rows("SG", S, coef, cl[1:], "nonelec", "Total less Electronics cluster, EDB implied cluster weights, chain-linked (calculated)", 2025)

    def q(tid, text):
        for r in singstat.table(tid)["rows"]:
            if (r["rowText"] or "").strip() == text:
                return {c["key"]: f(c["value"]) for c in r["columns"]}
        raise CheckFailed([f"SG: {text} not in {tid}"])
    real, nom, gdp = q("M015661", "Manufacturing"), q("M015651", "Manufacturing"), q("M015651", "GDP At Current Market Prices")
    gva = []
    for k in sorted(real, key=lambda s: (s[:4], s[5])):
        y, qq = k.split()
        p = f"{int(y) - 1} {qq}"
        gva.append({"economy": "SG", "freq": "Q", "period": f"{y}-Q{qq[0]}",
                    "real_yoy": round((real[k] / real[p] - 1) * 100, 2) if real.get(p) and real.get(k) else None,
                    "share": round(nom[k] / gdp[k] * 100, 2) if nom.get(k) and gdp.get(k) else None,
                    "real_yoy_calculated": "y", "share_calculated": "y",
                    "note": "SingStat M015661 (chained 2015 dollars) and M015651 (current prices), Manufacturing"})
    if len(out) < 500:
        raise CheckFailed([f"SG: only {len(out)} index rows"])
    return out, gva


# ---------- Hong Kong ----------
def hongkong():
    from core import censtatd
    out = []
    _, rows = censtatd.table("610-65001")
    ix = {r["period"]: f(r["figure"]) for r in rows if r.get("IND") == "ind_QSIP_C" and r["freq"] == "Q" and r["sv"] == "IP_INDEX" and r["svDesc"] == "Index"}
    yy = {r["period"]: f(r["figure"]) for r in rows if r.get("IND") == "ind_QSIP_C" and r["freq"] == "Q" and r["sv"] == "IP_INDEX" and r["svDesc"].startswith("Year-on-year")}
    for p, v in sorted(ix.items()):
        m = int(p[4:6]) - 2
        out.append(row("HK", "Q", f"{p[:4]}-{m:02d}-01", "mfg", v, yy.get(p), note="C&SD 610-65001, manufacturing, quarterly"))
    _, g = censtatd.table("310-34501")
    gva = []
    for r in g:
        if r.get("ACTIVITY") == "SECT_C" and r["freq"] == "Q" and r["svDesc"].startswith("Year-on-year"):
            gva.append({"economy": "HK", "freq": "Q", "period": f"{r['period'][:4]}-Q{int(r['period'][4:6]) // 3}", "real_yoy": f(r["figure"]),
                        "share": None, "real_yoy_calculated": "", "share_calculated": "",
                        "note": "C&SD 310-34501, chained (2024) dollars, y/y as published"})
    _, s = censtatd.table("310-34101")
    for r in s:
        if r.get("ACTIVITY") == "SECT_C" and r["freq"] == "Y" and r["svDesc"].startswith("% contribution"):
            gva.append({"economy": "HK", "freq": "A", "period": r["period"], "real_yoy": None, "share": f(r["figure"]),
                        "real_yoy_calculated": "", "share_calculated": "",
                        "note": "C&SD 310-34101, % contribution to GDP at basic prices, annual"})
    if len(out) < 40:
        raise CheckFailed([f"HK: only {len(out)} index rows"])
    return out, gva


# ---------- Taiwan ----------
TW_IPI = "https://service.moea.gov.tw/EE520/opendata/d.csv"      # data.gov.tw 6607 工業生產 (MOEA), 生產指數, 110年=100
TW_GDP_PAGE = "https://www.stat.gov.tw/cp.aspx?n=2674"           # DGBAS national accounts tables (生產帳_季 xlsx)
TW_PUBLISHED = {"mfg": ("C", "製造業"), "elec": ("I2", "資訊電子工業 = TSIC 26 電子零組件 + 27 電腦、電子產品及光學製品 (= ISIC 26)"),
                "19": ("17", "石油及煤製品製造業 (TSIC 17)"), "21": ("20", "藥品及醫用化學製品製造業 (TSIC 20)"),
                "23": ("23", "非金屬礦物製品製造業 (TSIC 23)"), "24": ("24", "基本金屬製造業 (TSIC 24)"),
                "27": ("28", "電力設備及配備製造業 (TSIC 28)")}
TW_I3 = ["13", "15", "16", "17", "18", "19", "20", "21", "22"]   # TSIC divisions in MOEA's 化學工業 group (I3)


def implied_weights(S, target, parts, start, win=0, min_months=12, tol=0.1, label=""):
    """Implied weights of `parts` in `target` for each calendar year from `start`, for agencies that publish no
    weights (checked 5 Nov 2026): within a year (chain-linked yearly) or over the whole base (fixed weights) the
    manufacturing index is a linear combination of its divisions' indices. Least squares on the months of years
    y - win .. y + win, non-negative (the most negative division is dropped and the fit repeated). A year with fewer
    than min_months months takes the previous year's weights. Fails if the fit misses by more than tol index points."""
    import numpy as np
    out, last = {}, None
    for y in sorted({k[0] for k in S[target] if k[0] >= start}):
        n_y = sum(1 for m in range(1, 13) if (y, m) in S[target] and all((y, m) in S[c] for c in parts))
        if n_y >= min_months:
            ks = [k for k in S[target] if y - win <= k[0] <= y + win and all(k in S[c] for c in parts)]
            use = list(parts)
            while True:
                A = np.array([[S[c][k] for c in use] for k in ks])
                b = np.array([S[target][k] for k in ks])
                w = np.linalg.lstsq(A, b, rcond=None)[0]
                if (w >= 0).all():
                    break
                use.pop(int(np.argmin(w)))
            if float(np.abs(A @ w - b).max()) > tol:
                raise CheckFailed([f"{label}: {target} is not a fixed combination of its parts around {y} (miss {float(np.abs(A @ w - b).max()):.2f})"])
            last = {c: 0.0 for c in parts}
            last.update(dict(zip(use, (float(x) for x in w))))
        if last:
            out[y] = last
    return out


def implied_chain(S, coef, use, base_year=None):
    """Index of the divisions in `use` at each year's implied weights, chain-linked at December; base_year = 100."""
    ix, first = {}, True
    for y in sorted(coef):
        w = coef[y]
        raw = lambda k: sum(w[c] * S[c][k] for c in use) if all(k in S[c] for c in use) else None  # noqa: E731
        months = [(y, m) for m in range(1, 13) if raw((y, m))]
        if not months:
            continue
        if first:
            ix.update({k: raw(k) for k in months})
            first = False
        else:
            dec = (y - 1, 12)
            if dec not in ix or not raw(dec):
                break
            ix.update({k: ix[dec] * raw(k) / raw(dec) for k in months})
    base = [v for k, v in ix.items() if k[0] == base_year]
    return {k: v / (sum(base) / len(base)) * 100 for k, v in ix.items()} if len(base) == 12 else ix


def implied_rows(eco, S, coef, use, ind, note, base_year=None):
    return [row(eco, "M", f"{k[0]}-{k[1]:02d}-01", ind, round(v, 3), note=note)
            for k, v in sorted(implied_chain(S, coef, use, base_year).items())]


def taiwan():
    import collections
    import openpyxl
    S = collections.defaultdict(dict)
    for x in list(csv.reader(io.StringIO(fetch(TW_IPI, 180).decode("utf-8-sig"))))[1:]:
        if len(x) >= 5 and x[0] == "生產指數" and f(x[4]) is not None and re.fullmatch(r"\d{5}", x[3]):
            S[x[1].strip()][(int(x[3][:3]) + 1911, int(x[3][3:]))] = f(x[4])
    miss = [c for c in ["C", "I1", "I2", "I3", "I4", "18", "19"] + [v[0] for v in TW_PUBLISHED.values()] + TW_I3 if not S.get(c)]
    if miss:
        raise CheckFailed([f"TW: industries not found {miss}"])
    d = lambda k: f"{k[0]}-{k[1]:02d}-01"  # noqa: E731
    out = []
    for k, (code, note) in TW_PUBLISHED.items():
        out += [row("TW", "M", d(p), k, v, note=f"MOEA IPI 2021 = 100: {note}") for p, v in sorted(S[code].items())]
    # rest = 製造業 less 資訊電子工業 and TSIC 28; chemicals (ISIC 20) = TSIC 18 + 19; both at implicit weights
    i1 = ["24", "25", "28", "29", "30", "31", "34"]          # 金屬機電工業 (I1) divisions; TSIC 28 = ISIC 27
    g = implied_weights(S, "C", ["I2", "I3", "I4"] + i1, 2009, min_months=12, label="TW")
    out += implied_rows("TW", S, g, ["I3", "I4"] + [c_ for c_ in i1 if c_ != "28"], "nonelec",
                        "製造業 less 資訊電子工業 (ISIC 26) and TSIC 28 電力設備 (ISIC 27), MOEA implied weights, chain-linked (calculated)", 2021)
    c = implied_weights(S, "I3", TW_I3, 2009, min_months=12, label="TW")
    out += implied_rows("TW", S, c, ["18", "19"], "20", "TSIC 18 化學材料及肥料 + 19 其他化學製品 (= ISIC 20), MOEA implied weights, chain-linked (calculated)", 2021)
    # GVA: DGBAS production-side national accounts, quarterly (file name changes with each release: found on the page)
    from core import dgbas
    page = dgbas.get(TW_GDP_PAGE).decode("utf-8", "replace")
    link = next((l for l in re.findall(r'href="([^"]+\.xlsx)"', page) if "生產帳_季" in urllib.parse.unquote(l)), None)
    if not link:
        raise CheckFailed(["TW: 生產帳_季 xlsx not linked on the DGBAS page"])
    p = urllib.parse.urlsplit(urllib.parse.unquote(link))
    wb = openpyxl.load_workbook(io.BytesIO(dgbas.get(urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(p.path), "", "")))),
                                read_only=True, data_only=True)

    def sheet(name):
        rows = list(wb[name].iter_rows(values_only=True))
        hdr = next(r for r in rows if r and r[1] == 1981)
        lab = {str(r[0]).replace("　", "").strip(): r for r in rows if r and r[0]}
        return {str(h): f(v) for h, v in zip(hdr, lab["C 製造業"])}, {str(h): f(v) for h, v in zip(hdr, lab["GDP"])}
    real, _ = sheet("實質1981~")
    nom, gdp = sheet("名目1981~")
    gva = []
    for q in sorted(k for k in real if re.fullmatch(r"\d{4}Q\d", k)):
        pq = f"{int(q[:4]) - 1}{q[4:]}"
        gva.append({"economy": "TW", "freq": "Q", "period": q.replace("Q", "-Q"),
                    "real_yoy": round((real[q] / real[pq] - 1) * 100, 2) if real.get(q) and real.get(pq) else None,
                    "share": round(nom[q] / gdp[q] * 100, 2) if nom.get(q) and gdp.get(q) else None,
                    "real_yoy_calculated": "y", "share_calculated": "y",
                    "note": "DGBAS production-side national accounts (2008 SNA): C 製造業, chained 2021 dollars; share of GDP, current prices"})
    if len(out) < 3000:
        raise CheckFailed([f"TW: only {len(out)} index rows"])
    return out, gva


ECONOMIES = {"JP": japan, "KR": korea, "TW": taiwan, "MY": malaysia, "SG": singapore, "HK": hongkong}


def read(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        rs = list(csv.DictReader(fh))
    for r in rs:
        for k in ("index", "yoy", "real_yoy", "share"):
            if k in r:
                r[k] = f(r[k])
    return rs


def write(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def update(force=False, only=None, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    iip, gva = read(OUT / "src_iip.csv"), read(OUT / "src_gva.csv")
    done, warnings, errors = [], [], []
    for cc, fn in ECONOMIES.items():
        try:
            a, b = fn()
        except Exception as e:  # noqa: BLE001
            errors.append(f"{cc}: {type(e).__name__}: {str(e)[:200]}")
            continue
        a = calc_yoy(a)
        iip = [r for r in iip if r["economy"] != cc] + a
        if b:
            gva = [r for r in gva if r["economy"] != cc] + b
        last = max(r["date"] for r in a)
        done.append(f"{cc} to {last}")
    if not done:
        raise CheckFailed(errors)
    warnings += [f"not updated: {e}" for e in errors]
    iip.sort(key=lambda r: (r["economy"], r["industry"], r["freq"], r["date"]))
    gva.sort(key=lambda r: (r["economy"], r["freq"], r["period"]))
    fp = hashlib.sha256(json.dumps([iip, gva], sort_keys=True, default=str).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": "no change; " + "; ".join(done), "warnings": warnings}
    write(OUT / "src_iip.csv", IIP_COLS, iip)
    write(OUT / "src_gva.csv", GVA_COLS, gva)
    code = f"F{fp[:8]}"
    nlong = write_long(({"country": r["economy"], "indicator": "mfg_iip", "series": f"{r['industry']}_{r['freq']}", "label": r["note"],
                         "measure": "index", "area": "", "freq": r["freq"], "date": r["date"], "value": r["index"], "unit": "index",
                         "source": "mfg_asia", "release": code} for r in iip if r["index"] is not None), OUT / "long.csv")
    write_release(OUT, {"code": code, "label": "Manufacturing sources: " + "; ".join(done), "economies": " ".join(sorted({r['economy'] for r in iip}))},
                  warnings, len(iip), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": "; ".join(done), "warnings": warnings}
