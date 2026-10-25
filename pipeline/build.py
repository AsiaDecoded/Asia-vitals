"""Build outputs from parsed ESRI tables.

  data/jp_gdp.csv          one row per quarter per component, every measure (the dashboard's dataset)
  data/json/<slug>.json    one file per chart, Econvitals-style: metadata + columns + data + latest
"""
import csv
import json
from pathlib import Path

COMPONENTS = [
    ("gdp", "GDP"),
    ("private_consumption", "Private consumption"),
    ("residential", "Private residential investment"),
    ("business_investment", "Private non-residential investment"),
    ("private_inventories", "Change in private inventories"),
    ("government_consumption", "Government consumption"),
    ("public_investment", "Public investment"),
    ("public_inventories", "Change in public inventories"),
    ("net_exports", "Net exports"),
    ("exports", "Exports"),
    ("imports", "Imports"),
    ("domestic_demand", "Domestic demand"),
    ("private_demand", "Private demand"),
    ("public_demand", "Public demand"),
]
CONTRIB = ["private_consumption", "residential", "business_investment", "private_inventories",
           "government_consumption", "public_investment", "public_inventories", "net_exports"]

# output column -> (basis, measure) in the parsed tables
MEASURES = [
    ("real_level", ("real", "level_saar")),
    ("nominal_level", ("nominal", "level_saar")),
    ("real_level_orig", ("real", "level_orig")),
    ("nominal_level_orig", ("nominal", "level_orig")),
    ("real_qoq", ("real", "qoq")),
    ("real_qoq_ann", ("real", "qoq_ann")),
    ("real_yoy", ("real", "yoy")),
    ("nominal_qoq", ("nominal", "qoq")),
    ("nominal_qoq_ann", ("nominal", "qoq_ann")),
    ("nominal_yoy", ("nominal", "yoy")),
    ("contrib_qoq", ("real", "contrib_qoq")),
    ("contrib_yoy", ("real", "contrib_yoy")),
    ("deflator_index", ("deflator", "index_sa")),
    ("deflator_qoq", ("deflator", "qoq")),
    ("deflator_yoy", ("deflator", "yoy")),
]

SOURCE = "Cabinet Office of Japan, ESRI, Quarterly Estimates of GDP"


def _index(tables):
    return {col: {r["date"]: r for r in tables[key]["data"]} for col, key in MEASURES}


def write_combined(tables, out):
    by = _index(tables)
    dates = [r["date"] for r in tables[("real", "level_saar")]["data"]]
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "component", "order"] + [c for c, _ in MEASURES])
        for d in dates:
            for i, (key, name) in enumerate(COMPONENTS):
                vals = [by[c].get(d, {}).get(key) for c, _ in MEASURES]
                w.writerow([d, name, i] + ["" if v is None else v for v in vals])
    return len(dates) * len(COMPONENTS)


def _chart(slug, title, units, freq, columns, data, release):
    latest = {}
    for c in columns:
        pts = [r for r in data if r.get(c) is not None]
        if pts:
            latest[c] = {"date": pts[-1]["date"], "value": pts[-1][c]}
    return {"slug": slug, "title": title, "units": units, "freq": freq,
            "source": f"{SOURCE}, {release['label']}.", "release": release["code"],
            "columns": columns, "data": data, "latest": latest}


def write_json(tables, release, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    by = _index(tables)
    dates = [r["date"] for r in tables[("real", "level_saar")]["data"]]
    g = lambda col, d, k="gdp": by[col].get(d, {}).get(k)
    trn = lambda v: None if v is None else round(v / 1000, 1)
    charts = [
        _chart("jp-gdp-growth", "Japan GDP growth", "Percent", "quarterly",
               ["real_qoq", "real_qoq_ann", "real_yoy", "nominal_qoq", "nominal_qoq_ann", "nominal_yoy"],
               [{"date": d, **{c: g(c, d) for c in ["real_qoq", "real_qoq_ann", "real_yoy", "nominal_qoq", "nominal_qoq_ann", "nominal_yoy"]}} for d in dates], release),
        _chart("jp-gdp-levels-sa", "Japan GDP level, seasonally adjusted",
               "¥ trillion, seasonally adjusted annual rate; real in chained 2020 yen", "quarterly",
               ["real", "nominal"], [{"date": d, "real": trn(g("real_level", d)), "nominal": trn(g("nominal_level", d))} for d in dates], release),
        _chart("jp-gdp-levels-orig", "Japan GDP level, original series",
               "¥ trillion per quarter, not seasonally adjusted; real in chained 2020 yen", "quarterly",
               ["real", "nominal"], [{"date": d, "real": trn(g("real_level_orig", d)), "nominal": trn(g("nominal_level_orig", d))} for d in dates], release),
        _chart("jp-gdp-deflator", "Japan GDP deflator", "Index 2020 = 100 (seasonally adjusted); percent change", "quarterly",
               ["index", "qoq", "yoy"], [{"date": d, "index": g("deflator_index", d), "qoq": g("deflator_qoq", d), "yoy": g("deflator_yoy", d)} for d in dates], release),
        _chart("jp-gdp-contributions-qoq", "Contributions to real GDP growth, q/q", "Percentage points", "quarterly",
               ["gdp"] + CONTRIB, [{"date": d, **{k: g("contrib_qoq", d, k) for k in ["gdp"] + CONTRIB}} for d in dates], release),
        _chart("jp-gdp-contributions-yoy", "Contributions to real GDP growth, y/y", "Percentage points", "quarterly",
               ["gdp"] + CONTRIB, [{"date": d, **{k: g("contrib_yoy", d, k) for k in ["gdp"] + CONTRIB}} for d in dates], release),
    ]
    last = dates[-1]
    comp_cols = ["real_level_trn", "real_qoq", "real_qoq_ann", "real_yoy", "nominal_yoy", "deflator_yoy", "contrib_qoq", "contrib_yoy"]
    comp_rows = [{"component": name, "real_level_trn": trn(g("real_level", last, k)),
                  **{c: g(c, last, k) for c in comp_cols[1:]}} for k, name in COMPONENTS]
    table = {"slug": "jp-gdp-components-latest", "title": "Japan GDP components, latest quarter",
             "units": "Growth in percent; contributions in percentage points; level in ¥ trillion (SAAR)",
             "source": f"{SOURCE}, {release['label']}.", "release": release["code"], "date": last,
             "columns": ["component"] + comp_cols, "data": comp_rows}
    for c in charts + [table]:
        (outdir / f"{c['slug']}.json").write_text(json.dumps(c, ensure_ascii=False, indent=1) + "\n")
    return [c["slug"] for c in charts + [table]]
