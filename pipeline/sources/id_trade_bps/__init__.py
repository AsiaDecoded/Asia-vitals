"""Indonesia merchandise trade: BPS monthly exports and imports and quarterly export and import price indices,
from the BPS WebAPI dynamic tables (key: repository secret BPS_KEY). As published, nothing calculated.

Monthly (US$ million; exports FOB, imports CIF; volumes in thousand tonnes):
  196 exports, 497 imports, 498 trade balance (Jan 2017 on in the WebAPI);
  1753, 1754 exports and imports by oil and gas / non-oil and gas; 2172, 2173 the same in volume;
  2309, 2359 exports and imports by SITC section (Jan 2022 on);
  2356 imports by broad economic category (consumption goods, raw materials, capital goods and their parts).
Quarterly (2023 = 100, from Q1 2024; BPS rebased from 2010 = 100 in March 2025):
  2487, 2490 export and import price indices (oil and gas, non-oil and gas, total); 2488, 2491 q/q; 2489, 2492 y/y.

Checks against the press release: the title of each monthly release states exports and imports in US$ billion
(two decimals); the latest month must round to those. Releases: monthly, about the 1st to the 15th of the
second month after the reference month (Aug 2026 on 1 Oct 2026), 11:00 Jakarta; price indices quarterly.
"""
import csv
import gzip
import hashlib
import json
import re

from core import bps
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "id_trade_bps"
DESCRIPTION = "Indonesia trade (BPS): monthly exports, imports and balance by oil-gas and SITC; quarterly trade price indices"
OUT = DATA / "id" / "trade"
RAWDIR = RAW / "id" / "trade_bps"
SOURCE = "BPS-Statistics Indonesia (WebAPI)"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SITC = ["Food and live animals", "Beverages and tobacco", "Crude materials, inedible, except fuels",
        "Mineral fuels, lubricants and related materials", "Animal and vegetable oils, fats and waxes",
        "Chemicals and related products", "Manufactured goods classified chiefly by material",
        "Machinery and transport equipment", "Miscellaneous manufactured articles",
        "Commodities and transactions not classified elsewhere"]
UNIT_V, UNIT_T = "US$ million", "thousand tonnes"


def _split(label):
    s = (label or "").lower().replace("-", "").replace(" ", "")
    if s.startswith("nonmigas"):
        return "nonoilgas"
    if s.startswith("migas"):
        return "oilgas"
    if s.startswith("jumlah") or s == "indonesia":
        return "total"
    return None


def monthly_series(raw):
    """{(series, date): (label, unit, value)} for the monthly variables."""
    out = {}

    def put(series, label, unit, r):
        freq, date = bps.period_of(r)
        if freq == "M":
            out[(series, date)] = (label, unit, r["value"])

    for vid, flow in ((196, "exports"), (497, "imports"), (498, "balance")):
        for r in raw[vid][1]:
            put(f"{flow}_total", {"exports": "Exports", "imports": "Imports", "balance": "Trade balance"}[flow], UNIT_V, r)
    for vid, flow, unit, suf in ((1753, "exports", UNIT_V, ""), (1754, "imports", UNIT_V, ""),
                                 (2172, "exports", UNIT_T, "_vol"), (2173, "imports", UNIT_T, "_vol")):
        for r in raw[vid][1]:
            k = _split(r["vervar_label"])
            if not k:
                continue
            lab = {"total": "Total", "oilgas": "Oil and gas", "nonoilgas": "Non-oil and gas"}[k]
            put(f"{flow}_{k}{suf}", f"{flow.capitalize()}: {lab}{' (volume)' if suf else ''}", unit, r)
    for vid, flow in ((2309, "exports"), (2359, "imports")):
        for r in raw[vid][1]:
            m = re.match(r"\s*(\d)\.", r["vervar_label"] or "")
            if m:
                put(f"{flow}_sitc{m.group(1)}", f"{flow.capitalize()}: SITC {m.group(1)} {SITC[int(m.group(1))]}", UNIT_V, r)
            elif _split(r["vervar_label"]) == "total":
                put(f"{flow}_sitc_total", f"{flow.capitalize()}: SITC total", UNIT_V, r)
    for r in raw[2356][1]:
        lab = re.sub(r"\s+", " ", (r["vervar_label"] or "").strip())
        put(f"imports_bec{int(r['vervar']):02d}", f"Imports by use: {lab}", UNIT_V, r)
    return out


BEC_TOTALS = {"konsumsi": ("imports_consumer", "Imports: consumption goods"),
              "bahan baku": ("imports_raw", "Imports: raw materials and auxiliary goods"),
              "barang modal": ("imports_capital", "Imports: capital goods")}


def bec_totals(m):
    """The three 'TOTAL IMPOR ...' rows of variable 2356 under stable names (the rows between them keep BPS's
    Indonesian labels; the dashboard shows only the three totals)."""
    out = {}
    for (s, d), (lab, unit, v) in m.items():
        if not s.startswith("imports_bec") or not lab.lower().startswith("imports by use: total impor"):
            continue
        for key, (name, label) in BEC_TOTALS.items():
            if key in lab.lower():
                out[(name, d)] = (label, unit, v)
    return out


def price_series(raw):
    """{(series, date): {index, qoq, yoy}} for the quarterly export and import price indices."""
    out = {}
    for vid, flow, field in ((2487, "export", "index"), (2488, "export", "qoq"), (2489, "export", "yoy"),
                             (2490, "import", "index"), (2491, "import", "qoq"), (2492, "import", "yoy")):
        for r in raw[vid][1]:
            freq, date = bps.period_of(r)
            if freq != "Q":
                continue
            k = _split(r["vervar_label"]) or "total"
            out.setdefault((f"{flow}_{k}", date), {})[field] = r["value"]
    return out


def release_titles():
    """{YYYY-MM: (exports bn, imports bn, release date)} from the monthly trade release titles."""
    out = {}
    pat = re.compile(r"(?i)ekspor dan impor indonesia\s+([a-z]+)\s+(\d{4}).*?usd\s*([\d.,]+)\s*miliar.*?usd\s*([\d.,]+)\s*miliar")
    for r in bps.rows("list/model/pressrelease/domain/0000/lang/ind", stop=lambda r: (r.get("rl_date") or "9999") < "2024-01"):
        m = pat.search(r.get("title") or "")
        if m and m.group(1).lower() in bps.MONTHS_ID:
            ym = f"{m.group(2)}-{bps.MONTHS_ID[m.group(1).lower()]:02d}"
            out.setdefault(ym, (bps.num(m.group(3)), bps.num(m.group(4)), r.get("rl_date")))
    return out


def checks(m, p, titles):
    errors, warnings = [], []
    dates = sorted({d for s, d in m if s == "exports_total"})
    if not dates:
        return ["no monthly exports"], warnings
    latest = dates[-1]
    for s in ("exports_total", "imports_total", "balance_total", "exports_oilgas", "exports_nonoilgas",
              "imports_oilgas", "imports_nonoilgas", "exports_sitc_total", "imports_sitc_total"):
        if (s, latest) not in m:
            errors.append(f"latest month {latest}: {s} missing")
    y0 = int(dates[0][:4])
    want = [f"{y}-{mm:02d}-01" for y in range(y0, int(latest[:4]) + 1) for mm in range(1, 13) if f"{y}-{mm:02d}-01" <= latest]
    miss = [d for d in want if d >= dates[0] and ("exports_total", d) not in m]
    if miss:
        errors.append(f"exports missing for {miss[:8]}")
    v = lambda s, d: m[(s, d)][2] if (s, d) in m else None  # noqa: E731
    bad = []
    for d in want:
        x, im, b = v("exports_total", d), v("imports_total", d), v("balance_total", d)
        if None not in (x, im, b) and abs(x - im - b) > 0.25:
            bad.append(f"{d} balance {b} vs {x - im:.1f}")
        for flow in ("exports", "imports"):
            t, o, n = v(f"{flow}_total", d), v(f"{flow}_oilgas", d), v(f"{flow}_nonoilgas", d)
            if None not in (t, o, n) and abs(o + n - t) > 0.25:
                bad.append(f"{d} {flow}: oil-gas + non-oil {o + n:.1f} vs {t}")
            st = v(f"{flow}_sitc_total", d)
            secs = [v(f"{flow}_sitc{i}", d) for i in range(10)]
            if st is not None and t is not None and abs(st - t) > 2.0:  # SITC tables are rounded to US$ 1 mn
                bad.append(f"{d} {flow}: SITC total {st} vs {t}")
            if st is not None and None not in secs and abs(sum(secs) - st) > 1.0:
                warnings.append(f"{d} {flow}: SITC sections sum to {sum(secs):.1f}, total {st}")
    if bad:
        errors.append(f"published totals do not add up: {bad[:8]}")
    ym = latest[:7]
    if ym in titles:
        xb, mb, _ = titles[ym]
        if round(v("exports_total", latest) / 1000, 2) != xb or round(v("imports_total", latest) / 1000, 2) != mb:
            errors.append(f"{ym}: WebAPI exports {v('exports_total', latest)}, imports {v('imports_total', latest)} "
                          f"vs release title US$ {xb} bn and {mb} bn")
    else:
        warnings.append(f"{ym}: no release title found to check the latest month against")
    for ymx, (xb, mb, _d) in titles.items():
        x, im = v("exports_total", ymx + "-01"), v("imports_total", ymx + "-01")
        if x is not None and ymx != ym and (abs(x / 1000 - xb) > 0.006 or abs(im / 1000 - mb) > 0.006):
            warnings.append(f"{ymx}: WebAPI {x}/{im} differs from the release title {xb}/{mb} bn (revised since)")
    pq = sorted({d for s, d in p if s == "export_total"})
    if not pq:
        errors.append("no export price index")
    else:
        for s in ("export_total", "import_total"):
            f = p.get((s, pq[-1]), {})
            if "index" not in f or "yoy" not in f:
                errors.append(f"{s} {pq[-1]}: index or y/y missing")
        for (s, d), f in p.items():
            pd_ = f"{int(d[:4]) - 1}{d[4:]}"
            if "yoy" in f and "index" in f and "index" in p.get((s, pd_), {}):
                calc = (f["index"] / p[(s, pd_)]["index"] - 1) * 100
                if abs(calc - f["yoy"]) > 0.02:
                    warnings.append(f"{s} {d}: y/y {f['yoy']} vs index {calc:.2f}")
    return errors, warnings


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    RAWDIR.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    years = bps.var_years(196)
    meta, recs = bps.var_data(196, years={max(years)})
    months = sorted(bps.period_of(r)[1] for r in recs if bps.period_of(r)[0] == "M")
    pyears = bps.var_years(2487)
    pmeta, precs = bps.var_data(2487, years={max(pyears)})
    pq = sorted(bps.period_of(r)[1] for r in precs if bps.period_of(r)[0] == "Q")
    if not months:
        raise CheckFailed(["WebAPI variable 196: no monthly exports in the latest year"])
    latest, platest = months[-1], (pq[-1] if pq else None)
    if (state.get("latest_month") == latest and state.get("latest_quarter_prices") == platest
            and state.get("last_update") == (meta or {}).get("last_update") and not force):
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    raw = {}
    for vid in (196, 497, 498, 1753, 1754, 2172, 2173, 2309, 2359, 2356, 2487, 2488, 2489, 2490, 2491, 2492):
        raw[vid] = bps.var_data(vid)
    m = monthly_series(raw)
    m.update(bec_totals(m))
    p = price_series(raw)
    titles = release_titles()
    errors, warnings = checks(m, p, titles)
    if state.get("latest_month") and latest < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one stored ({state['latest_month']})")
    if errors:
        raise CheckFailed(errors)

    rel = {ym + "-01": d for ym, (_x, _m, d) in titles.items()}
    rows = [{"date": d, "series": s, "label": lab, "unit": unit, "value": val, "release_date": rel.get(d, "")}
            for (s, d), (lab, unit, val) in sorted(m.items(), key=lambda kv: (kv[0][1], kv[0][0]))]
    cols = ["date", "series", "label", "unit", "value", "release_date"]
    with open(OUT / "id_trade.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])
    # dashboard copy: the series the page draws (BEC detail rows left out)
    keep = [r for r in rows if not r["series"].startswith("imports_bec")]
    with open(OUT / "id_trade_dash.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cols[:5])
        for r in keep:
            w.writerow([r[c] for c in cols[:5]])
    plab = {"total": "", "oilgas": ": oil and gas", "nonoilgas": ": non-oil and gas"}
    prow = []
    for (s, d), f in sorted(p.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        flow, k = s.split("_", 1)
        prow.append({"date": d, "series": s, "label": f"{flow.capitalize()} price index{plab[k]}",
                     "index": f.get("index"), "qoq": f.get("qoq"), "yoy": f.get("yoy")})
    pcols = ["date", "series", "label", "index", "qoq", "yoy"]
    with open(OUT / "id_trade_prices.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(pcols)
        for r in prow:
            w.writerow(["" if r[c] is None else r[c] for c in pcols])
    with gzip.open(RAWDIR / "webapi.json.gz", "wt", encoding="utf-8") as fh:
        json.dump({str(k): {"meta": mm, "records": rr} for k, (mm, rr) in raw.items()}, fh, ensure_ascii=False)

    code = "T" + latest[:7]
    label = f"{MONTHS[int(latest[5:7]) - 1]} {latest[:4]}"

    def long_rows():
        for r in rows:
            yield {"country": "ID", "indicator": "trade", "series": r["series"], "label": r["label"], "measure": "value",
                   "area": "national", "freq": "M", "date": r["date"], "value": r["value"], "unit": r["unit"],
                   "source": SOURCE, "release": code}
        for r in prow:
            for f, unit in (("index", "index, 2023 = 100"), ("qoq", "% q/q"), ("yoy", "% y/y")):
                yield {"country": "ID", "indicator": "trade_prices", "series": r["series"], "label": r["label"],
                       "measure": f, "area": "national", "freq": "Q", "date": r["date"], "value": r[f], "unit": unit,
                       "source": SOURCE, "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    fp = hashlib.sha256(json.dumps(rows + prow, sort_keys=True).encode()).hexdigest()[:16]
    x = m[("exports_total", latest)][2]
    im = m[("imports_total", latest)][2]
    write_release(OUT, {"code": code, "label": label, "latest_month": latest, "latest_quarter_prices": platest,
                        "last_update": (meta or {}).get("last_update"),
                        "release_date": rel.get(latest, ""),
                        "table": "BPS WebAPI: exports and imports (196, 497, 498, 1753, 1754, 2172, 2173, 2309, 2359, "
                                 "2356); export and import price indices (2487-2492)"},
                  warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{label}: exports US$ {x:,.1f} mn, imports US$ {im:,.1f} mn; "
            f"prices to {platest}", "warnings": warnings}
