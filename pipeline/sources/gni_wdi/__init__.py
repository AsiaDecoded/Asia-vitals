"""GNI per capita (Atlas method, current US$) and World Bank income classifications, for the Asia-dashboard economies.
Central dataset: asked for 2 Nov 2026 for an Asia GDP-page chart (GNI per capita indexed to the year each economy
became middle income); country dashboards can read the same files.

Sources (no key; GitHub's runners only, the workspace cannot reach the World Bank):
  WDI NY.GNP.PCAP.CD via api.worldbank.org/v2, as published. Taiwan is not in the World Bank's data.
  WDI NY.GNP.ATLS.CD (GNI, Atlas method, current US$, total), as published: added 3 Nov 2026 for the India GDP tab
  (Chart 1, GNI beside GDP); any dashboard can read it. If it fails, the other files still update (warning).
  World Bank historical income classifications (OGHIST.xlsx, "Country Analytical History"): the group each economy was
  assigned for each data year (L, LM, UM, H), from data year 1987 (fiscal year 1989).

t (calculated rule, asked for): the first data year an economy is classified lower-middle income or above after being
low income ("first crossing", so Indonesia's first, before it fell back to low income after the Asian financial crisis).
Data year, not the year the classification was announced (the World Bank reclassifies each July on the previous year's GNI).
Economies already lower-middle income when the classifications began (data year 1987: Thailand, Malaysia, the Philippines)
take that first year as t (asked for, 2 Nov 2026: "start of the series is correct"); column t_rule says which rule applied.
Economies upper-middle or high income from the start have no t.

Writes data/asia/gni/:
  asia_gni_pc.csv        economy, name, year, gni_pc (US$, as published)
  asia_income_class.csv  economy, name, data_year, fiscal_year, income_group (as published)
  asia_gni_index.csv     economy, name, t_year, t_rule, year, k (= year - t), gni_pc, index (= 100 at t; calculated)
  asia_gni_latest.csv    economy, name, year, gni_pc, income_group (for that data year), group_fiscal_year
  asia_gni_thresholds.csv data_year, low_max, lm_min, um_min, h_min (US$, as published in OGHIST "Thresholds", from 1987)
  asia_gni_atlas.csv     economy, name, year, gni_atlas (US$, total, as published)
  long.csv, release.json, release_row.json (code W<latest year>-<hash>)
The classification file used is the newest (by last data year) of the download and any OGHIST*.xlsx in raw/asia/gni/.
"""
import csv
import hashlib
import io
import json
import time
import urllib.request

from core.common import DATA, CheckFailed, read_json, write_long, write_release

NAME = "gni_wdi"
DESCRIPTION = "GNI per capita (Atlas, WDI) and World Bank income classifications, Asia-dashboard economies"
OUT = DATA / "asia" / "gni"
ECON = {"JP": ("JPN", "Japan"), "KR": ("KOR", "South Korea"), "HK": ("HKG", "Hong Kong"), "CN": ("CHN", "China"),
        "IN": ("IND", "India"), "ID": ("IDN", "Indonesia"), "TH": ("THA", "Thailand"), "MY": ("MYS", "Malaysia"),
        "SG": ("SGP", "Singapore"), "PH": ("PHL", "Philippines"), "VN": ("VNM", "Vietnam")}
WDI = "https://api.worldbank.org/v2/country/{}/indicator/{}?format=json&per_page=5000&date=1960:2100"
OGHIST = [
    "https://datacatalogfiles.worldbank.org/ddh-published/0037712/DR0090754/OGHIST.xlsx",
    "https://datacatalogfiles.worldbank.org/ddh-published/0037712/DR0090755/OGHIST.xlsx",
    "https://ddh-openapi.worldbank.org/resources/DR0090754/download",
]
SOURCE = "World Bank, WDI (NY.GNP.PCAP.CD, Atlas method) and historical income classifications (OGHIST)"


def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 asia-vitals"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(4 * (i + 1))
    raise last


def wdi(code="NY.GNP.PCAP.CD"):
    js = json.loads(get(WDI.format(";".join(v[0] for v in ECON.values()), code)))
    out = {}
    iso = {v[0]: k for k, v in ECON.items()}
    for r in js[1] or []:
        k = iso.get(r["countryiso3code"])
        if k and r["value"] is not None:
            out.setdefault(k, {})[int(r["date"])] = float(r["value"])
    return out, js[0].get("lastupdated")


def _parse(wb):
    """(classes {econ: {data_year: (group, fiscal_year)}}, thresholds {data_year: {...}}, latest data year)."""
    ws = next((wb[n] for n in wb.sheetnames if "analytical" in n.lower()), wb[wb.sheetnames[0]])
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    yr_row = next((r for r in rows if any(isinstance(c, str) and "calendar year" in c.lower() for c in r if c)), None)
    fy_row = next((r for r in rows if any(isinstance(c, str) and c.strip().upper().startswith("FY") for c in r if c)), None)
    if not yr_row:
        raise ValueError("no 'Data for calendar year' row")
    cols = {i: int(c) for i, c in enumerate(yr_row) if isinstance(c, (int, float)) or (isinstance(c, str) and c.strip().isdigit())}
    fys = {i: str(fy_row[i]).strip() for i in cols} if fy_row else {}
    iso = {v[0]: k for k, v in ECON.items()}
    out = {}
    for r in rows:
        code = str(r[0]).strip() if r and r[0] else ""
        if code in iso:
            for i, y in cols.items():
                v = str(r[i]).strip() if i < len(r) and r[i] is not None else ""
                if v in ("L", "LM", "LM*", "UM", "H"):
                    out.setdefault(iso[code], {})[y] = (v.rstrip("*"), fys.get(i, ""))
    thr = {}
    if "Thresholds" in wb.sheetnames:
        trows = [list(r) for r in wb["Thresholds"].iter_rows(values_only=True)]
        ty = next((r for r in trows if r and isinstance(r[0], str) and "calendar year" in r[0].lower()), None)
        lab = {str(r[0]).strip(): r for r in trows if r and isinstance(r[0], str)}
        num = lambda x: int("".join(ch for ch in str(x) if ch.isdigit())) if x is not None and any(ch.isdigit() for ch in str(x)) else None  # noqa: E731
        if ty and "Low income" in lab and "High income" in lab:
            for i, y in enumerate(ty):
                if isinstance(y, (int, float)) and lab["Low income"][i] is not None:
                    lm = str(lab["Lower middle income"][i]).replace(" ", "").split("-")
                    um = str(lab["Upper middle income"][i]).replace(" ", "").split("-")
                    thr[int(y)] = {"low_max": num(lab["Low income"][i]), "lm_min": num(lm[0]), "um_min": num(um[0]), "h_min": num(lab["High income"][i])}
    return out, thr, max(cols.values())


def oghist():
    """Historical classifications: the newest of the World Bank download and the copy kept in raw/asia/gni/ (a copy of
    OGHIST supplied on 2 Nov 2026, July 2026 release, data to 2025; the download URLs serve an older release)."""
    import openpyxl  # noqa: PLC0415
    errs, got = [], []
    for u in OGHIST:
        try:
            got.append((u, _parse(openpyxl.load_workbook(io.BytesIO(get(u)), read_only=True, data_only=True))))
            break
        except Exception as e:  # noqa: BLE001
            errs.append(f"{u}: {type(e).__name__}: {str(e)[:100]}")
    for f in sorted((DATA.parent / "raw" / "asia" / "gni").glob("OGHIST*.xlsx")):
        try:
            got.append((f"raw/asia/gni/{f.name}", _parse(openpyxl.load_workbook(f, read_only=True, data_only=True))))
        except Exception as e:  # noqa: BLE001
            errs.append(f"{f.name}: {type(e).__name__}: {str(e)[:100]}")
    if not got:
        raise CheckFailed(["historical classifications not reachable"] + errs)
    src, (cls, thr, last) = max(got, key=lambda g: g[1][2])
    return cls, thr, last, src, errs


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    gni, wdi_updated = wdi()
    try:
        atlas, _ = wdi("NY.GNP.ATLS.CD")
    except Exception as e:  # noqa: BLE001
        atlas, atlas_err = {}, f"NY.GNP.ATLS.CD: {type(e).__name__}: {e}"
    else:
        atlas_err = ""
    cls, thr, cls_last, cls_src, cls_errs = oghist()
    errors, warnings = [], []
    for k in ECON:
        if k not in gni:
            errors.append(f"{k}: no WDI GNI per capita")
        if k not in cls:
            errors.append(f"{k}: not in the historical classifications")
    if cls and not (1990 <= min(min(v) for v in cls.values()) <= 1990 or min(min(v) for v in cls.values()) == 1987):
        warnings.append(f"classifications start {min(min(v) for v in cls.values())}")
    if errors:
        raise CheckFailed(errors)
    t, rule = {}, {}
    for k, c in cls.items():
        ys = sorted(c)
        if c[ys[0]][0] == "LM":      # lower-middle income when the classifications began (asked for, 2 Nov 2026: Thailand)
            t[k], rule[k] = ys[0], "lower-middle income when the classifications began"
            continue
        for a, b in zip(ys, ys[1:]):
            if c[a][0] == "L" and c[b][0] in ("LM", "UM", "H"):
                t[k], rule[k] = b, "first year classified lower-middle income after low income"
                break
    latest = max(max(v) for v in gni.values())
    if cls_last < latest:
        warnings.append(f"classifications end at data year {cls_last} ({cls_src}); WDI has {latest}: add the newer OGHIST to raw/asia/gni/")
    rows_latest = []
    for k in ECON:
        y = max(gni[k])
        g = cls.get(k, {}).get(y, ("", ""))[0]
        rows_latest.append({"economy": k, "name": ECON[k][1], "year": y, "gni_pc": round(gni[k][y]), "income_group": g,
                            "group_fiscal_year": cls.get(k, {}).get(y, ("", ""))[1]})
    rows_thr = [{"data_year": y, **v} for y, v in sorted(thr.items())]
    if atlas_err:
        warnings.append(f"GNI (Atlas) not updated: {atlas_err}")
    missing = [k for k in ECON if k not in atlas]
    if atlas and missing:
        warnings.append(f"GNI (Atlas): no data for {', '.join(missing)}")
    if any(v <= 0 for a in atlas.values() for v in a.values()):
        warnings.append("GNI (Atlas): non-positive values; not updated")
        atlas = {}
    rows_atlas = [{"economy": k, "name": ECON[k][1], "year": y, "gni_atlas": round(v)} for k in ECON for y, v in sorted(atlas.get(k, {}).items())]
    rows_pc = [{"economy": k, "name": ECON[k][1], "year": y, "gni_pc": round(v)} for k in ECON for y, v in sorted(gni[k].items())]
    rows_cls = [{"economy": k, "name": ECON[k][1], "data_year": y, "fiscal_year": f, "income_group": g}
                for k in ECON for y, (g, f) in sorted(cls[k].items())]
    rows_ix = []
    for k, ty in t.items():
        if ty not in gni[k]:
            warnings.append(f"{k}: no GNI per capita for t = {ty}")
            continue
        for y, v in sorted(gni[k].items()):
            rows_ix.append({"economy": k, "name": ECON[k][1], "t_year": ty, "t_rule": rule[k], "year": y, "k": y - ty,
                            "gni_pc": round(v), "index": round(v / gni[k][ty] * 100, 1)})
    fp = hashlib.sha256(json.dumps([rows_pc, rows_cls, rows_ix, rows_latest, rows_thr] + ([rows_atlas] if rows_atlas else []), sort_keys=True).encode()).hexdigest()[:16]
    summary = "t: " + ", ".join(f"{k} {t[k]}" for k in ECON if k in t) + "; no t (upper-middle or high income from the start): " + \
              ", ".join(f"{k} ({cls[k][min(cls[k])][0]} in {min(cls[k])})" for k in ECON if k not in t)
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change; {summary}", "warnings": warnings}
    for name, rows in (("asia_gni_pc.csv", rows_pc), ("asia_income_class.csv", rows_cls), ("asia_gni_index.csv", rows_ix),
                       ("asia_gni_latest.csv", rows_latest), ("asia_gni_thresholds.csv", rows_thr)) + \
                      ((("asia_gni_atlas.csv", rows_atlas),) if rows_atlas else ()):
        with open(OUT / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    code = f"W{latest}-{fp[:6]}"
    nlong = write_long(({"country": r["economy"], "indicator": "gni_pc", "series": "NY.GNP.PCAP.CD", "label": "GNI per capita, Atlas method",
                         "measure": "level", "area": "", "freq": "A", "date": f"{r['year']}-01-01", "value": r["gni_pc"], "unit": "US$",
                         "source": SOURCE, "release": code} for r in rows_pc), OUT / "long.csv")
    if rows_atlas:
        write_long(({"country": r["economy"], "indicator": "gni", "series": "NY.GNP.ATLS.CD", "label": "GNI, Atlas method",
                     "measure": "level", "area": "", "freq": "A", "date": f"{r['year']}-01-01", "value": r["gni_atlas"], "unit": "US$",
                     "source": "World Bank, WDI (NY.GNP.ATLS.CD, Atlas method)", "release": code} for r in rows_atlas), OUT / "long_atlas.csv")
    write_release(OUT, {"code": code, "label": f"WDI GNI per capita to {latest}", "latest_year": latest, "wdi_updated": wdi_updated,
                        "t_years": t, "classifications": cls_src, "classifications_last_year": cls_last}, warnings, len(rows_pc), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": summary, "warnings": warnings}
