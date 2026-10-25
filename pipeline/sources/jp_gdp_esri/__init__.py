"""Japan GDP, Cabinet Office (ESRI) Quarterly Estimates.

New releases are found by working out the next release code from the last one
(first preliminary -> second preliminary -> next quarter's first) and checking
whether ESRI has published its tables yet.
"""
import shutil
import tempfile
from pathlib import Path

from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release
from . import build, checks, esri

NAME = "jp_gdp_esri"
DESCRIPTION = "Japan GDP (ESRI quarterly estimates)"
OUT = DATA / "jp" / "gdp"
RAWDIR = RAW / "jp" / "gdp_esri"

UNITS = {
    "real_level": "JPY bn, SAAR, chained 2020 prices", "nominal_level": "JPY bn, SAAR",
    "real_level_orig": "JPY bn, quarterly, chained 2020 prices", "nominal_level_orig": "JPY bn, quarterly",
    "deflator_index": "index, 2020 = 100",
    "contrib_qoq": "pp", "contrib_yoy": "pp",
}


def _download(code, dest):
    dest.mkdir(parents=True, exist_ok=True)
    for stem in esri.TABLES:
        url = esri.table_url(code, stem)
        body = esri.fetch(url)
        if body is None:
            raise RuntimeError(f"{code}: {stem} not found at {url} (release only partly published?)")
        (dest / f"{stem}{esri.suffix(code)}.csv").write_bytes(body)


def _load(code, folder):
    return {key: esri.parse_table((folder / f"{stem}{esri.suffix(code)}.csv").read_bytes())
            for stem, key in esri.TABLES.items()}


def _find_new(current):
    found, code = None, current
    for _ in range(2):
        code = esri.next_code(code)
        if esri.fetch(esri.table_url(code, "gaku-jk")) is None:
            break
        found = code
    return found


def _long_rows(tables, release):
    by = {col: {r["date"]: r for r in tables[key]["data"]} for col, key in build.MEASURES}
    for col, _ in build.MEASURES:
        for d, row in by[col].items():
            for key, label in build.COMPONENTS:
                yield {"country": "JP", "indicator": "gdp", "series": key, "label": label,
                       "measure": col, "area": "national", "freq": "Q", "date": d,
                       "value": row.get(key), "unit": UNITS.get(col, "%"),
                       "source": "Cabinet Office (ESRI)", "release": release["code"]}


def update(code=None, from_dir=None, **_):
    state = read_json(OUT / "release.json", {}) or {}
    if not code:
        if not state.get("code"):
            raise RuntimeError("no current ESRI release recorded; run once with --code")
        code = _find_new(state["code"])
        if not code:
            return {"updated": False, "code": state["code"],
                    "summary": f"no release after {state['code']} yet"}

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(from_dir) if from_dir else Path(tmp) / code
        if not from_dir:
            _download(code, folder)
        tables = _load(code, folder)
        errors, warnings = checks.run(tables, code, esri.ref_date(code), OUT / "jp_gdp.csv")
        if errors:
            raise CheckFailed(errors)
        dest = RAWDIR / code
        if folder.resolve() != dest.resolve():
            dest.mkdir(parents=True, exist_ok=True)
            for f in folder.glob("*.csv"):
                shutil.copy2(f, dest / f.name)

    release = {"code": code, "label": esri.label(code), "ref_quarter": esri.ref_date(code),
               "menu_url": esri.menu_url(code)}
    rows = build.write_combined(tables, OUT / "jp_gdp.csv")
    build.write_json(tables, release, OUT / "json")
    nlong = write_long(_long_rows(tables, release), OUT / "long.csv")
    write_release(OUT, release, warnings, rows, {"long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{release['label']}: {rows} rows",
            "warnings": warnings}
