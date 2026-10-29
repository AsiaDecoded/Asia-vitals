"""Vietnam CPI as published by the National Statistics Office (NSO, formerly GSO).

Monthly CPI workbook for each release (Dec 2021 on, Vietnamese, reference month only, every comparison base,
national, urban, rural, regions and provinces m/m, core inflation), the PX-Web yearbook tables for the
history (m/m 1995 on, y/y 2010 on, vs December 2002 on, base period 2020 on) and the IMF's headline index as
a separately labelled long series. Every figure as published; nothing is chained, converted or derived.
Where a workbook and PX-Web both cover a month, the workbook value (as first published) is used.

Release: 3rd of the following month, ~09:00 Hanoi (Decree 13/2026, from Apr 2026 data). New data is detected
with one WordPress REST call (CPI workbooks uploaded since the last one processed).
"""
import csv
import gzip
import json
import time
from pathlib import Path

from core import imf, nso_vn as N
from core.common import DATA, RAW, CheckFailed, now, read_json, write_long, write_release

NAME = "vn_cpi_nso"
DESCRIPTION = "Vietnam CPI and core inflation (NSO: monthly workbooks Dec 2021-, PX-Web history), IMF headline"
OUT = DATA / "vn" / "cpi"
RAWDIR = RAW / "vn" / "cpi_nso"
HERE = Path(__file__).resolve().parent
PX_TABLES = ["E11.01.px", "E11.02.px", "E11.03.px", "E11.04.px", "E11.05.px", "E11.06.px", "E11.07.px", "E11.08.px"]
PX_MAX_AGE_DAYS = 31          # PX-Web is updated once a year (with the yearbook); re-export at most monthly
INDEX_BASES = ("base_period", "yoy", "prev_dec", "prev_month", "qtr_avg", "ytd_avg")
MEASURE = {"base_period": "index", "yoy": "yoy", "prev_dec": "vs_dec", "prev_month": "mom", "qtr_avg": "qtr_avg",
           "ytd_avg": "ytd_avg"}
BREAKS = {"2020-01-01": "first month on 2019 = 100", "2025-11-01": "2024 basket (775 items, 2024 = 100) in the releases"}
IMF_FLOW, IMF_KEYS = "IMF.STA,CPI", {"index": "VNM.CPI._T.IX.M", "yoy": "VNM.CPI._T.YOY_PCH_PA_PT.M"}


def _shift(d, k):
    y, m = int(d[:4]), int(d[5:7]) - 1 + k
    return f"{y + m // 12}-{m % 12 + 1:02d}-01"


def _months(a, b):
    out, d = [], a
    while d <= b:
        out.append(d)
        d = _shift(d, 1)
    return out


# ---------------------------------------------------------------- fetch

def _post_dates(post_ids):
    dates = {}
    ids = sorted({p for p in post_ids if p})
    for i in range(0, len(ids), 100):
        items, _ = N.wp("posts", include=",".join(map(str, ids[i:i + 100])), per_page=100, _fields="id,date,link")
        for x in items:
            dates[x["id"]] = x["date"]
    return dates


def _workbooks(state, force):
    """Download the CPI workbooks not yet stored; returns {ref month: (bytes, meta)} for every stored one."""
    folder = RAWDIR / "releases"
    folder.mkdir(parents=True, exist_ok=True)
    index = read_json(RAWDIR / "releases.json", {}) or {}
    after = None if force or not index else max(v["uploaded"] for v in index.values())
    media = N.cpi_workbooks(after=after)
    new = [m for m in media if m["url"] not in {v["url"] for v in index.values()}]
    dates = _post_dates([m["post"] for m in new])
    for m in new:
        try:
            body, _ = N.get(m["url"])
            rows, meta = N.read_cpi_workbook(body)
        except Exception as e:  # noqa: BLE001 - a listed attachment can be gone (404) or unreadable; others cover it
            print(f"   skipped {m['url']}: {e}")
            continue
        if not meta.get("ref") or not rows:
            continue
        ref = meta["ref"]
        prev = index.get(ref)
        # duplicates for a month (re-uploads, "-1" copies): keep the last one uploaded before or on the release day
        if prev and prev["uploaded"] > m["date"]:
            continue
        fn = f"{ref}_{N.sha(body)}.xlsx"
        (folder / fn).write_bytes(body)
        index[ref] = {"url": m["url"], "uploaded": m["date"], "posted": dates.get(m["post"]), "post": m["post"], "file": fn}
        time.sleep(0.5)
    (RAWDIR / "releases.json").write_text(json.dumps(dict(sorted(index.items())), ensure_ascii=False, indent=1) + "\n")
    return index, new


def _px(force):
    folder = RAWDIR / "px"
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for t in PX_TABLES:
        p = folder / f"{t}.gz"
        fresh = p.exists() and (time.time() - p.stat().st_mtime) < PX_MAX_AGE_DAYS * 86400
        if force or not fresh:
            try:
                p.write_bytes(gzip.compress(N.px_export(t)))
            except Exception as e:  # noqa: BLE001 - keep the stored copy if the export fails
                if not p.exists():
                    raise
                print(f"   PX-Web {t}: export failed ({e}); using stored copy")
        out[t] = gzip.decompress(p.read_bytes())
    return out


def _imf():
    out = {}
    for k, key in IMF_KEYS.items():
        series = imf.parse(imf.fetch(IMF_FLOW, key, start="1990"))
        if len(series) != 1:
            raise CheckFailed([f"IMF {key}: expected 1 series, got {len(series)}"])
        out[k] = {f"{p[:4]}-{int(p[6:]):02d}-01": v for p, v, _ in series[0][1] if v is not None}
    return out


# ---------------------------------------------------------------- assemble

def _assemble(index, px):
    """{(date, area, series, base, base_year): row} with workbook values over PX-Web values."""
    store, px_meta, unknown = {}, {}, set()
    for t, body in px.items():
        if t in N.PX_MONTHLY:
            rows, meta, unk = N.px_monthly_rows(t, body)
            unknown |= set(unk)
        elif t == "E11.01.px":
            rows, meta = N.px_headline_mom(body)
            rows = [r for r in rows if r["date"] < "2002-01-01"]    # E11.02 carries 2002 on, with the groups
        else:
            continue
        upd = meta.get("LAST-UPDATED", "")
        px_meta[t] = {"title": meta.get("TITLE"), "last_updated": upd}
        for r in rows:
            if r["base"] == "base_period" and r["date"] >= "2025-01-01":
                r["base_year"] = 2024   # E11.07 is titled "base period 2019" but its 2025 row is on 2024 = 100
            r.update(source="nso_pxweb", table=t, release_date=f"{upd[:4]}-{upd[4:6]}-{upd[6:8]}" if upd else "")
            store[(r["date"], r["area"], r["series"], r["base"], r["base_year"])] = r
    regions = []
    for ref, info in sorted(index.items()):
        rows, _ = N.read_cpi_workbook((RAWDIR / "releases" / info["file"]).read_bytes())
        rel = (info.get("posted") or info["uploaded"])[:10]
        for r in rows:
            r.update(source="nso_release", table=info["url"].rsplit("/", 1)[-1], release_date=rel)
            if r["area"].startswith(("region:", "province:")):
                regions.append(r)
                continue
            key = (r["date"], r["area"], r["series"], r["base"], r["base_year"])
            old = store.get(key)
            if old and old["source"] == "nso_pxweb":
                r["px_value"] = old["value"]
            store[key] = r
    return store, regions, px_meta, sorted(unknown)


def _rate(r):
    if r["series"] == "core":
        return r["value"]                                  # core is published as a % change
    if r["base"] == "base_period":
        return None
    return round(r["value"] - 100, 6)                      # "105.08" is published as "up 5.08%"


# ---------------------------------------------------------------- checks

def _expected_bases(d):
    m = int(d[5:7])
    b = {"base_period", "yoy", "prev_dec", "prev_month"}
    if m in (3, 6, 9, 12):
        b.add("qtr_avg")
    if m not in (1, 3):
        b.add("ytd_avg")
    return b


def _checks(store, index, imfd, weights, state):
    errors, warnings = [], []
    rel = {k: v for k, v in store.items() if v["source"] == "nso_release"}
    latest = max(k[0] for k in rel)
    if state.get("latest_month") and latest < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one stored ({state['latest_month']})")
    # latest month: headline, core, 11 groups, every comparison base published for that month; urban and rural
    have = {(k[1], k[2], k[3]) for k in rel if k[0] == latest}
    for s in ["all"] + N.CPI_GROUPS:
        for b in _expected_bases(latest):
            if ("national", s, b) not in have:
                errors.append(f"{latest}: {s} {b} missing")
    for a in ("urban", "rural"):
        for b in ("yoy", "prev_month", "base_period"):
            if (a, "all", b) not in have:
                errors.append(f"{latest}: {a} all items {b} missing")
    for b in ("yoy", "prev_month") + (("ytd_avg",) if int(latest[5:7]) not in (1, 3) else ()):
        if ("national", "core", b) not in have:
            errors.append(f"{latest}: core {b} missing")
    # no gaps: headline y/y Jan 2010 -> latest, m/m Jan 1995 -> latest; core y/y from the first workbook
    for s, b, start in (("all", "yoy", "2010-01-01"), ("all", "prev_month", "1995-01-01"),
                        ("core", "yoy", min(k[0] for k in rel if k[2] == "core"))):
        miss = [d for d in _months(start, latest) if not any((d, "national", s, b, by) in store for by in (None,))]
        if miss:
            errors.append(f"{s} {b}: {len(miss)} months missing from {start[:7]} (first {miss[0][:7]})")
    # base-period index vs published y/y, same base, within rounding
    worst, nb = 0.0, 0
    for (d, a, s, b, by), r in store.items():
        if b != "base_period":
            continue
        p, y = store.get((_shift(d, -12), a, s, "base_period", by)), store.get((d, a, s, "yoy", None))
        if p and y:
            nb += 1
            dif = abs(r["value"] / p["value"] * 100 - y["value"])
            worst = max(worst, dif)
            if dif > 0.06:
                errors.append(f"{d} {a} {s}: base-period index ({by}) and y/y disagree by {dif:.3f}pp")
    # year-to-date average vs base-period indices on one base: all items exact (error), groups as warnings
    ny, wg = 0, []
    for (d, a, s, b, _), r in store.items():
        if b != "ytd_avg" or a != "national" or s == "core":
            continue
        y, m = int(d[:4]), int(d[5:7])
        for B in (2019, 2024):
            cur = [store.get((f"{y}-{i:02d}-01", a, s, "base_period", B)) for i in range(1, m + 1)]
            pre = [store.get((f"{y - 1}-{i:02d}-01", a, s, "base_period", B)) for i in range(1, m + 1)]
            if all(cur) and all(pre):
                ny += 1
                dif = abs(sum(x["value"] for x in cur) / sum(x["value"] for x in pre) * 100 - r["value"])
                if dif > 0.06:
                    (errors.append if s == "all" else wg.append)(f"{d} {s}: YTD average {r['value']:.3f} vs base indices {dif:.3f}pp")
    if wg:
        warnings.append(f"YTD average differs from the base-period indices by more than 0.06pp in {len(wg)} group cases "
                        f"(NSO aggregates these from lower levels), e.g. {wg[0]}")
    # where both a workbook and PX-Web give a month: y/y and vs-December within rounding; m/m as warnings
    nm, mm = 0, []
    for k, r in rel.items():
        if "px_value" in r:
            nm += 1
            dif = abs(r["px_value"] - r["value"])
            if dif > 0.01:
                (errors.append if k[3] in ("yoy", "prev_dec") else mm.append)(
                    f"{k[0][:7]} {k[1]} {k[2]} {k[3]}: PX-Web {r['px_value']:.3f} vs workbook {r['value']:.3f}")
    if mm:
        warnings.append(f"PX-Web and the workbooks differ in {len(mm)} cases (workbook kept): " + "; ".join(mm[:8]))
    # values in range
    for (d, a, s, b, by), r in store.items():
        v = r["value"]
        lo, hi = ((-30, 60) if s == "core" else (10, 2000) if b == "base_period" else (50, 250))
        if not lo < v < hi:
            errors.append(f"{d} {a} {s} {b}: {v} out of range")
    # IMF: its index should be NSO's 2024 = 100 index (warning only)
    if imfd:
        diffs = [(d, abs(imfd["index"][d] - r["value"])) for (d, a, s, b, by), r in store.items()
                 if a == "national" and s == "all" and b == "base_period" and by == 2024 and d in imfd["index"]]
        bad = [x for x in diffs if x[1] > 0.02]
        if bad:
            warnings.append(f"IMF index differs from NSO's 2024 = 100 index by more than 0.02 in {len(bad)} months, e.g. {bad[0]}")
    # weights: 11 groups sum to 100 per basket; sub-groups not above their group
    for basket, rows in weights.items():
        tot = sum(w for s, w in rows.items() if s in N.CPI_GROUPS)
        if abs(tot - 100) > 0.02:
            errors.append(f"{basket} weights: 11 groups sum to {tot:.2f}")
        for sub, grp in (("cereals", "food_catering"), ("foodstuff", "food_catering"), ("eating_out", "food_catering"),
                         ("health_services", "health"), ("education_services", "education")):
            if sub in rows and rows[sub] > rows[grp]:
                errors.append(f"{basket} weights: {sub} above {grp}")
    return errors, warnings, latest, {"base_vs_yoy": nb, "base_vs_yoy_worst_pp": round(worst, 4), "ytd_checks": ny,
                                      "px_overlap": nm}


def _weights():
    out = {}
    for p in sorted(HERE.glob("weights_*.csv")):
        basket = p.stem.split("_")[1]
        out[basket] = {r["series"]: float(r["weight_pct"]) for r in csv.DictReader(open(p))}
    return out


# ---------------------------------------------------------------- write

def _write(store, regions, imfd, weights, latest, index, px_meta, extra):
    OUT.mkdir(parents=True, exist_ok=True)
    cols = ["date", "area", "series", "label", "comparison_base", "base_year", "value", "rate", "unit", "source",
            "table", "release_date", "base_break"]
    rows = []
    for (d, a, s, b, by), r in store.items():
        brk = 1 if d in BREAKS or (b == "base_period" and by == 2024 and d == "2025-01-01") else 0
        rows.append({"date": d, "area": a, "series": s, "label": N.LABEL[s], "comparison_base": b,
                     "base_year": by or "", "value": round(r["value"], 6), "rate": "" if _rate(r) is None else round(_rate(r), 6),
                     "unit": "%" if s == "core" else ("index, %d = 100" % by if b == "base_period" else "index, comparison period = 100"),
                     "source": r["source"], "table": r["table"], "release_date": r["release_date"], "base_break": brk})
    rows.sort(key=lambda r: (r["date"], r["area"], N.ORDER[r["series"]], r["comparison_base"]))
    with open(OUT / "vn_cpi.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    # dashboard copy: rates for every base, the index as published, the IMF series apart
    dcols = ["date", "area", "series", "measure", "value", "base_year", "source"]
    dash = []
    for r in rows:
        if r["area"] not in ("national", "urban", "rural"):
            continue
        m = MEASURE[r["comparison_base"]]
        v = r["value"] if m == "index" else r["rate"]
        dash.append({"date": r["date"], "area": r["area"], "series": r["series"], "measure": m, "value": v,
                     "base_year": r["base_year"], "source": r["source"]})
    for d, v in sorted(imfd.get("index", {}).items()):
        dash.append({"date": d, "area": "national", "series": "imf_all", "measure": "index", "value": v, "base_year": 2024, "source": "imf"})
    for d, v in sorted(imfd.get("yoy", {}).items()):
        dash.append({"date": d, "area": "national", "series": "imf_all", "measure": "yoy", "value": round(v, 6), "base_year": "", "source": "imf"})
    with open(OUT / "vn_cpi_dash.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=dcols, lineterminator="\n")
        w.writeheader()
        w.writerows(dash)
    # regions and provinces (m/m, previous month = 100, as published), every workbook month
    with open(OUT / "vn_cpi_regions.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "kind", "name", "series", "label", "value", "mom", "release_date"])
        for r in sorted(regions, key=lambda r: (r["date"], r["area"], N.ORDER[r["series"]])):
            k, nm = r["area"].split(":", 1)
            w.writerow([r["date"], k, nm, r["series"], N.LABEL[r["series"]], r["value"], round(r["value"] - 100, 6), r["release_date"]])
    # weights as published (% of CPI)
    with open(OUT / "vn_cpi_weights.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["basket", "used_from", "series", "label", "weight_pct", "source"])
        for p in sorted(HERE.glob("weights_*.csv")):
            for r in csv.DictReader(open(p)):
                w.writerow([r["basket"], r["used_from"], r["series"], N.LABEL[r["series"]], r["weight_pct"], r["source"]])
    # latest month for the tiles
    def g(d, s, b, a="national"):
        r = store.get((d, a, s, b, None))
        return None if r is None else round(_rate(r), 2)
    prev = _shift(latest, -1)
    lat = {"date": latest, "release_date": index[latest[:7]].get("posted", "")[:10] if latest[:7] in index else ""}
    for s in ["all", "core", "food_catering", "foodstuff", "cereals", "eating_out", "transport", "housing"]:
        lat[f"{s}_yoy"], lat[f"{s}_yoy_prev"] = g(latest, s, "yoy"), g(prev, s, "yoy")
    lat.update(all_mom=g(latest, "all", "prev_month"), all_vs_dec=g(latest, "all", "prev_dec"),
               all_ytd=g(latest, "all", "ytd_avg"), core_mom=g(latest, "core", "prev_month"), core_ytd=g(latest, "core", "ytd_avg"),
               urban_yoy=g(latest, "all", "yoy", "urban"), rural_yoy=g(latest, "all", "yoy", "rural"),
               gold_yoy=g(latest, "gold", "yoy"), usd_yoy=g(latest, "usd", "yoy"))
    bi = store.get((latest, "national", "all", "base_period", 2024))
    lat["all_index"] = round(bi["value"], 3) if bi else None
    with open(OUT / "vn_cpi_latest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(lat), lineterminator="\n")
        w.writeheader()
        w.writerow(lat)
    code = f"C{latest[:7]}"

    def long_rows():
        for r in rows:
            if r["area"] not in ("national", "urban", "rural"):
                continue
            m = MEASURE[r["comparison_base"]]
            yield {"country": "VN", "indicator": "cpi", "series": r["series"], "label": r["label"], "measure": m,
                   "area": r["area"], "freq": "M", "date": r["date"], "value": r["value"] if m == "index" else r["rate"],
                   "unit": r["unit"] if m == "index" else "%", "source": N.SOURCE if r["source"] != "imf" else "IMF", "release": code}
        for d, v in sorted(imfd.get("yoy", {}).items()):
            yield {"country": "VN", "indicator": "cpi", "series": "imf_all", "label": "All items (IMF CPI dataset)", "measure": "yoy",
                   "area": "national", "freq": "M", "date": d, "value": round(v, 6), "unit": "%", "source": "IMF", "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    release = {"code": code, "label": time.strftime("%B %Y", time.strptime(latest[:7], "%Y-%m")), "latest_month": latest,
               "table": "NSO monthly CPI workbooks (Vietnamese), PX-Web E11.01-E11.08, IMF.STA,CPI VNM",
               "workbooks": len(index), "px": px_meta}
    return rows, nlong, release


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    index, new = _workbooks(state, force)
    if not new and state.get("latest_month") and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no new workbook (latest {state['latest_month'][:7]})"}
    px = _px(force)
    store, regions, px_meta, unknown = _assemble(index, px)
    try:
        imfd = _imf()
        RAWDIR.mkdir(parents=True, exist_ok=True)
        (RAWDIR / "imf.json.gz").write_bytes(gzip.compress(json.dumps(imfd).encode()))
    except Exception as e:  # noqa: BLE001 - the fallback series must not stop NSO's data
        imfd, unknown = {}, unknown + [f"IMF fetch failed: {e}"]
    weights = _weights()
    errors, warnings, latest, extra = _checks(store, index, imfd, weights, state)
    if unknown:
        warnings.append(f"PX-Web labels not mapped: {unknown}")
    if errors:
        raise CheckFailed(errors)
    rows, nlong, release = _write(store, regions, imfd, weights, latest, index, px_meta, extra)
    write_release(OUT, release, warnings, len(rows), {"long_rows": nlong, "checks": extra, "processed": now()})
    (OUT / "vn_cpi_checks.json").write_text(json.dumps({"checks": extra, "warnings": warnings}, ensure_ascii=False, indent=1) + "\n")
    return {"updated": True, "code": release["code"], "summary": f"{release['label']}: {len(rows)} rows, {len(index)} workbooks",
            "warnings": warnings}
