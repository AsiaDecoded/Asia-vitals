"""Indonesia CPI from BPS-Statistics Indonesia itself, through the BPS WebAPI (key: repository secret BPS_KEY).

Everything is as published by BPS; nothing is calculated here.
  - Monthly CPI press release (Berita Resmi Statistik, BRS), January 2020 on: the PDF that the WebAPI links,
    read with pdftotext.
      Table 1: CPI and the 11 expenditure groups (COICOP 2018): index, m/m, year to date, y/y, and contributions
               (andil) to m/m and y/y.
      Table 9: CPI by component: core (inti), administered prices (harga diatur pemerintah), volatile food
               (bergejolak), and the energy and food (bahan makanan) groupings: the same eight figures.
    A month is kept only if its published rates agree with its published indices (y/y and year to date within
    0.02, or 0.06 where the index is far below 100), so a table read wrongly from an older layout is dropped,
    not stored. Base: 2022 = 100 from January 2024, 2018 = 100 for 2020-2023.
  - Static table 908 (Inflasi Umum, Inti, Harga Diatur Pemerintah, dan Bergejolak Nasional, M-to-M dan Y-to-D):
    m/m for CPI, core, administered and volatile food from January 2009, for the months before the press
    releases read here.

New data is detected from the newest CPI press release in the WebAPI's list. The text of every release read
is kept in raw/id/cpi_bps/brs/<YYYY-MM>.txt.gz (the PDFs are not kept), so only new releases are downloaded.
"""
import csv
import gzip
import hashlib
import html
import json
import re

from core import bps
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "id_cpi_bps"
DESCRIPTION = "Indonesia CPI (BPS WebAPI): core, administered, volatile food, energy, food, groups with y/y and contributions"
OUT = DATA / "id" / "cpi_bps"
RAWDIR = RAW / "id" / "cpi_bps"
FIRST = "2020-01"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SOURCE = "BPS-Statistics Indonesia (WebAPI)"
# Table 1 rows in order
GROUPS = [
    ("all", "CPI, all items"), ("food", "Food, beverages and tobacco"), ("clothing", "Clothing and footwear"),
    ("housing", "Housing, water, electricity and household fuels"),
    ("household", "Household equipment and routine maintenance"), ("health", "Health"), ("transport", "Transport"),
    ("communication", "Information, communication and financial services"),
    ("recreation", "Recreation, sport and culture"), ("education", "Education"),
    ("restaurants", "Food and beverage services (restaurants)"), ("personal", "Personal care and other services"),
]
# Table 9 rows by label
COMPONENTS = [
    ("core", r"^inti\b", "Core"), ("administered", r"diatur", "Administered prices"),
    ("volatile", r"bergejolak", "Volatile food"), ("energy", r"^energi", "Energy"),
    ("food_component", r"bahan makanan", "Food (bahan makanan)"),
]
FIELDS = ["idx_year_ago", "idx_dec", "index", "mom", "ytd", "yoy", "contrib_mom", "contrib_yoy"]
STATIC = 908


def _ym_title(title):
    m = re.search(r"(?i)(januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember)\s+(\d{4})", title or "")
    return f"{m.group(2)}-{bps.MONTHS_ID[m.group(1).lower()]:02d}" if m else None


def releases():
    """{YYYY-MM: (brs_id, pdf url)} for CPI press releases from FIRST on (newest listing first)."""
    out = {}
    for r in bps.rows("list/model/pressrelease/domain/0000/lang/ind",
                       stop=lambda r: (r.get("rl_date") or "9999") < FIRST):
        t = r.get("title") or ""
        if not re.search(r"(?i)inflasi|deflasi", t) or re.search(r"(?i)perdagangan besar|ihpb|produsen|petani|grosir", t):
            continue
        ym = _ym_title(t)
        if ym and ym >= FIRST and ym not in out and r.get("pdf"):
            out[ym] = (r.get("brs_id"), r["pdf"])
    return out


def _ok(f):
    """Published rates agree with the published indices."""
    tol = lambda base: 0.02 + (0.04 if base < 80 else 0)  # noqa: E731
    if min(f["idx_year_ago"], f["idx_dec"], f["index"]) <= 0:
        return False
    yoy = (f["index"] / f["idx_year_ago"] - 1) * 100
    ytd = (f["index"] / f["idx_dec"] - 1) * 100
    return abs(yoy - f["yoy"]) <= tol(f["idx_year_ago"]) and abs(ytd - f["ytd"]) <= tol(f["idx_dec"])


def parse_release(text):
    """{series: {field: value}} from one release's text, or {} where a table fails its check."""
    out = {}
    t1 = bps.table_rows(text, r"^\s*Tabel 1\b", r"^\s*Catatan")
    if len(t1) == len(GROUPS):
        rows = {k: dict(zip(FIELDS, ns)) for (k, _l), (_lab, ns) in zip(GROUPS, t1)}
        if all(_ok(v) for v in rows.values()):
            out.update(rows)
    t9 = None
    for m in re.finditer(r"(?m)^\s*Tabel \d+\b", text):
        rows = bps.table_rows(text[m.start():], r"Tabel", r"^\s*Catatan")
        if any(re.search(r"(?i)^inti\b", lab) for lab, _ in rows):
            t9 = rows
            break
    if t9:
        for k, pat, _l in COMPONENTS:
            hit = [ns for lab, ns in t9 if re.search(r"(?i)" + pat, lab)]
            if hit and _ok(dict(zip(FIELDS, hit[0]))):
                out[k] = dict(zip(FIELDS, hit[0]))
    return out


def static_mom():
    """{series: {YYYY-MM: m/m}} from static table 908 (CPI, core, administered, volatile)."""
    d = bps.call(f"view/model/statictable/domain/0000/lang/ind/id/{STATIC}")["data"]
    t = html.unescape(d["table"])
    out = {k: {} for k in ("all", "core", "administered", "volatile")}
    year = None
    for r in re.findall(r"(?s)<tr[^>]*>(.*?)</tr>", t):
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"(?s)<t[dh][^>]*>(.*?)</t[dh]>", r)]
        if not cells:
            continue
        if re.fullmatch(r"\d{4}", cells[0]):
            year = int(cells[0])
            continue
        if year and len(cells) >= 6 and cells[1].lower() in bps.MONTHS_ID:
            ym = f"{year}-{bps.MONTHS_ID[cells[1].lower()]:02d}"
            for k, c in zip(("all", "core", "administered", "volatile"), cells[2:6]):
                ns = bps.numbers(c)
                if len(ns) == 1:
                    out[k][ym] = ns[0]
    return out, d.get("updt_date")


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    (RAWDIR / "brs").mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    rel = releases()
    if not rel:
        raise CheckFailed(["no CPI press releases found in the WebAPI list"])
    latest = max(rel)
    if state.get("latest_month") == latest + "-01" and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    warnings, errors = [], []
    data, read = {}, 0
    for ym in sorted(rel):
        path = RAWDIR / "brs" / f"{ym}.txt.gz"
        if path.exists() and not force:
            text = gzip.open(path, "rt", encoding="utf-8").read()
        else:
            try:
                text = bps.pdf_text(bps.download(rel[ym][1]))
            except Exception as e:  # noqa: BLE001
                warnings.append(f"{ym}: release not read ({e})")
                continue
            hm = bps.month_of(text)
            if hm and hm != ym:
                warnings.append(f"{ym}: the release text is for {hm}; skipped")
                continue
            with gzip.open(path, "wt", encoding="utf-8") as f:
                f.write(text)
            read += 1
        got = parse_release(text)
        for k, v in got.items():
            data.setdefault(k, {})[ym] = v
        missing = [k for k, _l in GROUPS + [(c, l) for c, _p, l in COMPONENTS] if k not in got]
        if missing and ym >= "2024-01":
            warnings.append(f"{ym}: not read from the release: {', '.join(missing)}")
    smom, static_updated = static_mom()

    # checks
    for k, _l in GROUPS:
        if latest not in data.get(k, {}):
            errors.append(f"{k}: nothing for {latest}")
    for k, _p, _l in COMPONENTS[:3]:
        if latest not in data.get(k, {}):
            errors.append(f"{k}: nothing for {latest}")
    gaps = [ym for ym in sorted(rel) if ym >= "2024-01" and ym not in data.get("core", {})]
    if gaps:
        errors.append(f"core missing for {gaps[:6]}")
    if state.get("latest_month") and latest + "-01" < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one already stored ({state['latest_month']})")
    # components' contributions add up to the headline (published, rounded to 2 decimals)
    for ym, a in data.get("all", {}).items():
        parts = [data.get(k, {}).get(ym) for k in ("core", "administered", "volatile")]
        if all(parts):
            s = sum(p["contrib_yoy"] for p in parts)
            if abs(s - a["yoy"]) > 0.05:
                warnings.append(f"{ym}: component contributions sum to {s:.2f}, CPI y/y {a['yoy']}")
    # static table m/m against the releases
    bad = [f"{k} {ym}: static {v}, release {data[k][ym]['mom']}" for k, d in smom.items() for ym, v in d.items()
           if ym in data.get(k, {}) and abs(v - data[k][ym]["mom"]) > 0.011]
    if len(bad) > 3:
        errors.append(f"static table 908 m/m differs from the releases: {bad[:4]}")
    elif bad:
        warnings.append("static table 908 vs releases: " + "; ".join(bad))
    if errors:
        raise CheckFailed(errors)

    labels = dict(GROUPS) | {k: l for k, _p, l in COMPONENTS}
    kind = {k: "group" for k, _l in GROUPS} | {k: "component" for k, _p, _l in COMPONENTS} | {"all": "headline"}
    order = {k: i for i, k in enumerate([k for k, _l in GROUPS[:1]] + [k for k, _p, _l in COMPONENTS] + [k for k, _l in GROUPS[1:]])}
    rows = []
    for k in order:
        months = set(data.get(k, {})) | set(smom.get(k, {}))
        for ym in sorted(months):
            f = data.get(k, {}).get(ym)
            r = {"date": ym + "-01", "series": k, "label": labels[k], "kind": kind[k], "order": order[k],
                 "base": "2022 = 100" if ym >= "2024-01" else ("2018 = 100" if ym >= "2020-01" else ""),
                 "source_table": "release" if f else "static 908"}
            if f:
                r.update({c: f[c] for c in ("index", "mom", "ytd", "yoy", "contrib_mom", "contrib_yoy")})
            else:
                r["mom"] = smom[k][ym]
            rows.append(r)
    rows.sort(key=lambda r: (r["date"], r["order"]))
    cols = ["date", "series", "label", "kind", "order", "base", "index", "mom", "ytd", "yoy", "contrib_mom", "contrib_yoy", "source_table"]
    with open(OUT / "id_cpi_bps.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r.get(c) is None else r[c] for c in cols])
    code = "C" + latest

    def long_rows():
        for r in rows:
            for meas, unit in (("index", "index, " + r["base"]), ("mom", "% m/m"), ("ytd", "% YTD"), ("yoy", "%"),
                               ("contrib_mom", "pp of CPI m/m"), ("contrib_yoy", "pp of CPI y/y")):
                yield {"country": "ID", "indicator": "cpi", "series": r["series"], "label": r["label"], "measure": meas,
                       "area": "national", "freq": "M", "date": r["date"], "value": r.get(meas), "unit": unit,
                       "source": SOURCE, "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    label = f"{MONTHS[int(latest[5:7]) - 1]} {latest[:4]}"
    fp = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
    release = {"code": code, "label": label, "latest_month": latest + "-01", "brs_id": rel[latest][0],
               "static_908_updated": static_updated, "table": "BPS WebAPI: CPI press releases (Tables 1 and 9), static table 908"}
    write_release(OUT, release, warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    core = data["core"][latest]
    return {"updated": True, "code": code, "summary": f"{label}: CPI {data['all'][latest]['yoy']}% y/y, core {core['yoy']}%; "
            f"{read} releases read, {len(rows)} rows", "warnings": warnings}
