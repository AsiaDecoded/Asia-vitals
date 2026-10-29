"""Indonesia wholesale prices: BPS Indeks Harga Perdagangan Besar (IHPB), 2023 = 100, from the monthly WPI press
release (BRS) linked in the BPS WebAPI (key: repository secret BPS_KEY).

As published, nothing calculated: Table 1 of each release, January 2025 on (the first month on the 2023 base):
the general (Umum Nasional) index and its five sections: index, m/m, year to date, y/y, and contributions (andil)
to m/m and y/y. A month is kept only if its published m/m and y/y agree with its published indices (within 0.02).
Released with the CPI, on the first working day of the following month.
Text of every release read (kept, so later runs download only new releases): raw/id/wpi_bps/brs/<YYYY-MM>.txt.gz.
"""
import csv
import gzip
import hashlib
import json
import re

from core import bps
from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "id_wpi_bps"
DESCRIPTION = "Indonesia wholesale prices (BPS IHPB, 2023 = 100): general index and five sections, as published"
OUT = DATA / "id" / "ppi"
RAWDIR = RAW / "id" / "wpi_bps"
FIRST = "2025-01"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SOURCE = "BPS-Statistics Indonesia (WebAPI)"
ROWS = [
    ("wpi", "WPI, general"), ("agriculture", "Agriculture, forestry and fishery products"),
    ("ores_utilities", "Ores and minerals; electricity, gas and water"),
    ("food_textiles", "Food, beverages and tobacco; textiles, apparel and leather"),
    ("other_goods", "Other transportable goods, except metal products and machinery"),
    ("metal_machinery", "Metal products, machinery and equipment"),
]
FIELDS = ["idx_year_ago", "idx_prev", "index", "mom", "ytd", "yoy", "contrib_mom", "contrib_yoy"]


def releases():
    out = {}
    for r in bps.rows("list/model/pressrelease/domain/0000/lang/ind",
                       stop=lambda r: (r.get("rl_date") or "9999") < FIRST):
        t = r.get("title") or ""
        if not re.search(r"(?i)perdagangan\s*besar|ihpb", t):
            continue
        m = re.search(r"(?i)(januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember)\s+(\d{4})", t)
        if not m:
            continue
        ym = f"{m.group(2)}-{bps.MONTHS_ID[m.group(1).lower()]:02d}"
        if ym >= FIRST and ym not in out and r.get("pdf"):
            out[ym] = (r.get("brs_id"), r["pdf"])
    return out


def _ok(f):
    """Published m/m (and y/y, where the year-ago index is printed) agree with the published indices."""
    if min(f["idx_prev"], f["index"]) <= 0:
        return False
    mom = (f["index"] / f["idx_prev"] - 1) * 100
    if abs(mom - f["mom"]) > 0.02:
        return False
    if f["idx_year_ago"] is None:  # January releases print December and January only
        return True
    return abs((f["index"] / f["idx_year_ago"] - 1) * 100 - f["yoy"]) <= 0.02


def parse_release(text, ym):
    rows = bps.table_rows(text, r"^\s*Tabel 1\b", r"^\s*(Catatan|Tabel)", width=(7, 8))
    i = next((i for i, (lab, _ns) in enumerate(rows) if re.search(r"(?i)umum", lab)), None)
    rows = [(lab, ns if len(ns) == 8 else [None] + ns) for lab, ns in rows[i:]][:len(ROWS)] if i is not None else []
    if len(rows) != len(ROWS):
        return {}
    hd = re.search(r"Tabel 1[\s\S]{0,400}?\(2023=100\),\s*([A-Za-z]+)\s+(\d{4})", text)
    if not hd or f"{hd.group(2)}-{bps.MONTHS_ID.get(hd.group(1).lower(), 0):02d}" != ym:
        return {}
    out = {k: dict(zip(FIELDS, ns)) for (k, _l), (_lab, ns) in zip(ROWS, rows)}
    return out if all(_ok(v) for v in out.values()) else {}


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    (RAWDIR / "brs").mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    rel = releases()
    if not rel:
        raise CheckFailed(["no WPI press releases found in the WebAPI list"])
    latest = max(rel)
    if state.get("latest_month") == latest + "-01" and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    data, warnings, read = {}, [], 0
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
            with gzip.open(path, "wt", encoding="utf-8") as f:
                f.write(text)
            read += 1
        got = parse_release(text, ym)
        if got:
            data[ym] = got
        else:
            warnings.append(f"{ym}: Table 1 not read or failed its check")
    errors = []
    if latest not in data:
        errors.append(f"nothing read for the latest month {latest}")
    gaps = [ym for ym in sorted(rel) if ym not in data]
    if len(gaps) > 2:
        errors.append(f"months not read: {gaps}")
    if state.get("latest_month") and latest + "-01" < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one already stored ({state['latest_month']})")
    for ym, d in data.items():
        s = sum(d[k]["contrib_yoy"] for k, _l in ROWS[1:])
        if abs(s - d["wpi"]["yoy"]) > 0.06:
            warnings.append(f"{ym}: section contributions sum to {s:.2f}, WPI y/y {d['wpi']['yoy']}")
    if errors:
        raise CheckFailed(errors)
    rows = []
    for ym in sorted(data):
        for i, (k, label) in enumerate(ROWS):
            f = data[ym][k]
            rows.append({"date": ym + "-01", "series": k, "label": label, "order": i, "index": f["index"],
                         "mom": f["mom"], "ytd": f["ytd"], "yoy": f["yoy"], "contrib_mom": f["contrib_mom"],
                         "contrib_yoy": f["contrib_yoy"]})
    cols = ["date", "series", "label", "order", "index", "mom", "ytd", "yoy", "contrib_mom", "contrib_yoy"]
    with open(OUT / "id_ppi.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])
    code = "P" + latest

    def long_rows():
        for r in rows:
            for meas, unit in (("index", "index, 2023 = 100"), ("mom", "% m/m"), ("ytd", "% YTD"), ("yoy", "%"),
                               ("contrib_mom", "pp of WPI m/m"), ("contrib_yoy", "pp of WPI y/y")):
                yield {"country": "ID", "indicator": "ppi", "series": r["series"], "label": r["label"], "measure": meas,
                       "area": "national", "freq": "M", "date": r["date"], "value": r[meas], "unit": unit,
                       "source": SOURCE, "release": code}
    nlong = write_long(long_rows(), OUT / "long.csv")
    label = f"{MONTHS[int(latest[5:7]) - 1]} {latest[:4]}"
    fp = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
    release = {"code": code, "label": label, "latest_month": latest + "-01", "brs_id": rel[latest][0],
               "table": "BPS WebAPI: WPI (IHPB) press releases, Table 1"}
    write_release(OUT, release, warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{label}: WPI {data[latest]['wpi']['yoy']}% y/y; "
            f"{read} releases read, {len(rows)} rows", "warnings": warnings}
