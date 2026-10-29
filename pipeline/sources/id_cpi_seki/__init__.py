"""Indonesia CPI: BPS-Statistics Indonesia, as republished by Bank Indonesia in SEKI table VIII.1 (TABEL8_1.xls).

bps.go.id refuses automated requests (Cloudflare challenge) and the BPS WebAPI needs a personal key, so the keyless
route is Bank Indonesia's SEKI workbook, which carries BPS's figures unchanged. Everything is as published:
  - Headline CPI (Umum): index, m/m, calendar-year (YTD) and y/y, from the earliest SEKI sheet (Jakarta, 1966 on)
    to the latest month. Where SEKI's sheets overlap (old bases), the later sheet's figures are kept.
    BPS bases: 2022 = 100 (150 cities) from Jan 2024; 2018 = 100 (90 cities) 2020-2023; 2012 = 100 (82 cities)
    2014-2019; 2007 = 100 (66 cities) Jun 2008-2013; 2002 = 100 (45 cities) 2004-May 2008; older bases before.
  - The 11 expenditure groups (COICOP 2018 classification), Jan 2020 on: index and m/m as published.
    SEKI publishes no y/y or weights for the groups.
Index levels are not linked across bases: each month carries the base it was published on.
Core, administered prices and volatile food are not in SEKI (BPS WebAPI only).

New data is detected from the parsed content (fingerprint). Each new release's workbook is kept unchanged in
raw/id/cpi_seki/<code>/TABEL8_1.xls.
"""
import csv
import hashlib
import json
from pathlib import Path

from core import seki
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "id_cpi_seki"
DESCRIPTION = "Indonesia CPI (BPS via Bank Indonesia SEKI VIII.1): headline from 1966, 11 expenditure groups from 2020"
OUT = DATA / "id" / "cpi"
RAWDIR = RAW / "id" / "cpi_seki"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SOURCE = "BPS-Statistics Indonesia, via Bank Indonesia SEKI"
# key, SEKI label (start, upper case), English label (BPS's own, as SEKI gives it, tidied)
GROUPS = [
    ("food", "MAKANAN, MINUMAN DAN TEMBAKAU", "Food, beverages and tobacco"),
    ("clothing", "PAKAIAN DAN ALAS KAKI", "Clothing and footwear"),
    ("housing", "PERUMAHAN, AIR, LISTRIK", "Housing, water, electricity and household fuels"),
    ("household", "PERLENGKAPAN, PERALATAN", "Household equipment and routine maintenance"),
    ("health", "KESEHATAN", "Health"),
    ("transport", "TRANSPORTASI", "Transport"),
    ("communication", "INFORMASI, KOMUNIKASI", "Information, communication and financial services"),
    ("recreation", "REKREASI, OLAHRAGA", "Recreation, sport and culture"),
    ("education", "PENDIDIKAN", "Education"),
    ("restaurants", "PENYEDIAAN MAKANAN DAN MINUMAN", "Food and beverage services (restaurants)"),
    ("personal", "PERAWATAN PRIBADI", "Personal care and other services"),
]
BASES = [("2024-01", "2022 = 100"), ("2020-01", "2018 = 100"), ("2014-01", "2012 = 100"), ("2008-06", "2007 = 100"),
         ("2004-01", "2002 = 100"), ("1998-01", "1996 = 100"), ("0000-00", "older base")]
TOL = 0.02  # published rates (2 decimals) vs the published index (2 decimals), within one base


def base_of(ym):
    return next(b for start, b in BASES if ym >= start)


def _shift(ym, k):
    y, m = int(ym[:4]), int(ym[5:7]) - k
    while m < 1:
        y, m = y - 1, m + 12
    return f"{y}-{m:02d}"


def _months(a, b):
    out = [a]
    while out[-1] < b:
        y, m = int(out[-1][:4]), int(out[-1][5:7]) + 1
        out.append(f"{y + (m > 12)}-{(m - 1) % 12 + 1:02d}")
    return out


def parse(body):
    """{'all': {measure: {ym: v}}, <group>: {...}}, from every sheet; later sheets overwrite earlier ones."""
    import xlrd  # noqa: PLC0415
    book = xlrd.open_workbook(file_contents=body)
    data = {"all": {"index": {}, "mom": {}, "ytd": {}, "yoy": {}}}
    for g, _s, _e in GROUPS:
        data[g] = {"index": {}, "mom": {}}
    for sh in book.sheets():
        rows = seki.read(sh)
        sheet = {"index": {}, "mom": {}, "ytd": {}, "yoy": {}}
        current = None  # the group whose 'Indeks' / 'Perubahan' rows follow
        old_style = False
        for _r, lab, _eng, vals in rows:
            L = lab.strip()
            u = L.upper()
            low = L.lower()
            # old layout (1966-2003 sheets): numbered headline rows
            if low.startswith("1.1. inflasi bulanan"):
                sheet["mom"].update(vals); old_style = True
            elif low.startswith("1.2. inflasi tahunan"):
                sheet["yoy"].update(vals); old_style = True
            elif low.startswith("1.3. inflasi kumulatif") or low.startswith("a. perubahan harga"):
                if vals:
                    sheet["ytd"].update(vals)
            elif low.startswith("1.1. ihk") or low.startswith("1.1 ihk"):
                sheet["index"].update(vals)
            # new layout (2002 on): group name rows, then Indeks / Perubahan; Umum then Bulanan/Kalender/Tahun
            elif u == "UMUM":
                current = "all"
            elif any(u.startswith(s) for _g, s, _e in GROUPS) and not vals:
                current = next(g for g, s, _e in GROUPS if u.startswith(s))
            elif low == "indeks" and current:
                (sheet["index"] if current == "all" else data[current]["index"]).update(vals)
            elif low.startswith("perubahan") and current and current != "all":
                data[current]["mom"].update(vals)
            elif low == "bulanan" and current == "all":
                sheet["mom"].update(vals)
            elif low.startswith("tahun kalend") and current == "all":
                sheet["ytd"].update(vals)
            elif low.startswith("tahun ke tahun") and current == "all":
                sheet["yoy"].update(vals)
            elif L and not low.startswith(("perubahan", "%", "sumber", "1)", "2)", "3)", "4)", "5)", "6)")):
                current = None  # any other label (an old-classification group): its rows are not kept
        # placeholder zeros: SEKI's 2002-2010 sheet carries 0.0 for months it does not cover
        good = {ym for ym, v in sheet["index"].items() if v and v > 0} if sheet["index"] else None
        for meas, vals in sheet.items():
            for ym, v in vals.items():
                if good is not None and ym not in good:
                    continue
                if not old_style and meas == "index" and v == 0:
                    continue
                data["all"][meas][ym] = v
    for g, _s, _e in GROUPS:  # groups only from the COICOP 2018 classification (2020 on)
        for meas in ("index", "mom"):
            data[g][meas] = {ym: v for ym, v in data[g][meas].items()
                             if ym >= "2020-01" and v is not None and (meas != "index" or v > 0)}
    return data


def check(data, state):
    errors, warnings = [], []
    hl = data["all"]
    latest = max(hl["yoy"])
    for meas in ("index", "mom", "ytd", "yoy"):
        if latest not in hl[meas]:
            errors.append(f"headline {meas}: no value for {latest}")
    for g, _s, _e in GROUPS:
        for meas in ("index", "mom"):
            if latest not in data[g][meas]:
                errors.append(f"{g} {meas}: no value for {latest}")
    if state.get("latest_month") and latest + "-01" < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one already stored ({state['latest_month']})")
    # SEKI has no headline y/y for Mar 1979-Feb 1980 and Apr 1990-Feb 1991 (gaps between its sheets)
    gaps = [ym for ym in _months("1991-03", latest) if ym not in hl["yoy"]]
    if gaps:
        errors.append(f"headline y/y missing for {len(gaps)} months since Mar 1991, e.g. {gaps[:5]}")
    gaps = [ym for ym in _months("2020-01", latest) if any(ym not in data[g]["mom"] for g, _s, _e in GROUPS)]
    if gaps:
        errors.append(f"group m/m missing since 2020, e.g. {gaps[:5]}")
    # published rates against the published index, within the 2022 base
    bad = []
    for key, d in data.items():
        for ym, v in d["mom"].items():
            p = _shift(ym, 1)
            if ym >= "2024-02" and p in d["index"] and ym in d["index"]:
                calc = (d["index"][ym] / d["index"][p] - 1) * 100
                if abs(calc - v) > TOL + 0.005 * 100 / d["index"][p]:
                    bad.append(f"{key} m/m {ym}: published {v}, index gives {calc:.3f}")
    for ym, v in hl["yoy"].items():
        p = _shift(ym, 12)
        if ym >= "2025-01" and p in hl["index"] and ym in hl["index"]:
            calc = (hl["index"][ym] / hl["index"][p] - 1) * 100
            if abs(calc - v) > TOL:
                bad.append(f"headline y/y {ym}: published {v}, index gives {calc:.3f}")
    for ym, v in hl["ytd"].items():
        dec = f"{int(ym[:4]) - 1}-12"
        if ym >= "2025-01" and dec in hl["index"] and ym in hl["index"]:
            calc = (hl["index"][ym] / hl["index"][dec] - 1) * 100
            if abs(calc - v) > TOL:
                bad.append(f"headline YTD {ym}: published {v}, index gives {calc:.3f}")
    if len(bad) > 3:
        errors.append(f"{len(bad)} published rates differ from the index, e.g. {bad[:3]}")
    elif bad:
        warnings.append("rates vs index: " + "; ".join(bad))
    if not (-5 < hl["yoy"][latest] < 30):
        errors.append(f"headline y/y {hl['yoy'][latest]} for {latest} out of range")
    return latest, errors, warnings


def update(force=False, from_file=None, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    if from_file:
        body, modified = Path(from_file).read_bytes(), None
    else:
        body, modified = seki.download("8_1")
    data = parse(body)
    latest, errors, warnings = check(data, state)
    if errors:
        raise CheckFailed(errors)
    rows = []
    order = {"all": 0, **{g: i + 1 for i, (g, _s, _e) in enumerate(GROUPS)}}
    labels = {"all": "CPI, all items", **{g: e for g, _s, e in GROUPS}}
    for key, d in data.items():
        months = sorted(set().union(*[set(v) for v in d.values()]))
        for ym in months:
            rows.append({"date": ym + "-01", "series": key, "label": labels[key], "order": order[key],
                         "base": base_of(ym), "index": d["index"].get(ym), "mom": d["mom"].get(ym),
                         "ytd": d.get("ytd", {}).get(ym), "yoy": d.get("yoy", {}).get(ym)})
    rows.sort(key=lambda r: (r["date"], r["order"]))
    fp = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
    code = "C" + latest
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    dest = RAWDIR / code
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "TABEL8_1.xls").write_bytes(body)
    cols = ["date", "series", "label", "order", "base", "index", "mom", "ytd", "yoy"]
    with open(OUT / "id_cpi.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r.get(c) is None else r[c] for c in cols])

    def long_rows():
        for r in rows:
            for meas, unit in (("index", "index, " + r["base"]), ("mom", "% m/m"), ("ytd", "% YTD"), ("yoy", "%")):
                yield {"country": "ID", "indicator": "cpi", "series": r["series"], "label": r["label"],
                       "measure": meas, "area": "national", "freq": "M", "date": r["date"], "value": r.get(meas),
                       "unit": unit, "source": SOURCE, "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    label = f"{MONTHS[int(latest[5:7]) - 1]} {latest[:4]}"
    release = {"code": code, "label": label, "latest_month": latest + "-01", "seki_modified": modified,
               "table": "Bank Indonesia SEKI VIII.1 (TABEL8_1.xls), BPS CPI"}
    write_release(OUT, release, warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{label}: headline y/y {data['all']['yoy'][latest]}%, "
            f"{len(rows)} rows", "warnings": warnings}
