"""GNI per capita (Atlas method, current US$) and World Bank income classifications, for the Asia-dashboard economies.
Central dataset: asked for 2 Nov 2026 for an Asia GDP-page chart (GNI per capita indexed to the year each economy
became middle income); country dashboards can read the same files.

Sources (no key; GitHub's runners only, the workspace cannot reach the World Bank):
  WDI NY.GNP.PCAP.CD via api.worldbank.org/v2, as published. Taiwan is not in the World Bank's data.
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
  long.csv, release.json, release_row.json (code W<latest year>-<hash>)
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
WDI = "https://api.worldbank.org/v2/country/{}/indicator/NY.GNP.PCAP.CD?format=json&per_page=5000&date=1960:2100"
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


def wdi():
    js = json.loads(get(WDI.format(";".join(v[0] for v in ECON.values()))))
    out = {}
    iso = {v[0]: k for k, v in ECON.items()}
    for r in js[1] or []:
        k = iso.get(r["countryiso3code"])
        if k and r["value"] is not None:
            out.setdefault(k, {})[int(r["date"])] = float(r["value"])
    return out, js[0].get("lastupdated")


def oghist():
    import openpyxl  # noqa: PLC0415
    errs = []
    for u in OGHIST:
        try:
            raw = get(u)
            wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            break
        except Exception as e:  # noqa: BLE001
            errs.append(f"{u}: {type(e).__name__}: {str(e)[:100]}")
    else:
        raise CheckFailed(["historical classifications not reachable"] + errs)
    ws = next((wb[n] for n in wb.sheetnames if "analytical" in n.lower()), wb[wb.sheetnames[0]])
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    yr_row = next((r for r in rows if any(isinstance(c, str) and "calendar year" in c.lower() for c in r if c)), None)
    fy_row = next((r for r in rows if any(isinstance(c, str) and c.strip().upper().startswith("FY") for c in r if c)), None)
    if not yr_row:
        raise CheckFailed(["OGHIST: no 'Data for calendar year' row"])
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
    return out


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    gni, wdi_updated = wdi()
    cls = oghist()
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
    fp = hashlib.sha256(json.dumps([rows_pc, rows_cls], sort_keys=True).encode()).hexdigest()[:16]
    summary = "t: " + ", ".join(f"{k} {t[k]}" for k in ECON if k in t) + "; no t (upper-middle or high income from the start): " + \
              ", ".join(f"{k} ({cls[k][min(cls[k])][0]} in {min(cls[k])})" for k in ECON if k not in t)
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change; {summary}", "warnings": warnings}
    for name, rows in (("asia_gni_pc.csv", rows_pc), ("asia_income_class.csv", rows_cls), ("asia_gni_index.csv", rows_ix)):
        with open(OUT / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    code = f"W{latest}-{fp[:6]}"
    nlong = write_long(({"country": r["economy"], "indicator": "gni_pc", "series": "NY.GNP.PCAP.CD", "label": "GNI per capita, Atlas method",
                         "measure": "level", "area": "", "freq": "A", "date": f"{r['year']}-01-01", "value": r["gni_pc"], "unit": "US$",
                         "source": SOURCE, "release": code} for r in rows_pc), OUT / "long.csv")
    write_release(OUT, {"code": code, "label": f"WDI GNI per capita to {latest}", "latest_year": latest, "wdi_updated": wdi_updated,
                        "t_years": t}, warnings, len(rows_pc), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": summary, "warnings": warnings}
