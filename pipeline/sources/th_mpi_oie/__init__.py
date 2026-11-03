"""Thailand Manufacturing Production Index (MPI) and capacity utilisation: Office of Industrial Economics (OIE,
Ministry of Industry), as published in its English index workbooks (oie.go.th, "Industrial index").

- MPI, value-added weights, chain-linked, reference year 2021 = 100 (OIE switched to chain-linking with the
  September 2026 release, 30 Oct 2026): monthly from Jan 2021 and quarterly, not seasonally adjusted; all
  manufacturing and the 22 TSIC 2-digit industries (10-32), with OIE's weights (% of the index).
- The previous MPI, 2016 = 100, monthly Jan 2016 - Dec 2023 (OIE archive index2016_2023.zip), kept as its own
  series (base = 2016), not linked to the new one. Its seasonally adjusted headline is stored too.
- Capacity utilisation, % (all manufacturing and industries): current file Jan 2025 on; previous file 2016-2023.

OIE publishes % changes only for the latest month and quarter. Calculated here (asked for 3 Nov 2026), flagged
calculated = y: y/y for every month and quarter, index / index a year earlier - 1, on each base separately (the
2016 base to Dec 2023, the 2021 base from Jan 2022). The checks compare the latest calculated y/y with OIE's.

Released around the 27th-30th of the following month, about 14:00 Bangkok (15:00 SGT), after the 11:15 SGT run.
"""
import csv
import gzip
import hashlib
import io
import json
import re
import time
import urllib.request
import zipfile

from core.common import DATA, RAW, CheckFailed, read_json, write_long, write_release

NAME = "th_mpi_oie"
DESCRIPTION = "Thailand manufacturing production index and capacity utilisation (OIE)"
OUT = DATA / "th" / "mpi"
RAWDIR = RAW / "th" / "mpi_oie"
BASE = "https://www.oie.go.th/assets/portals/1/fileups/2/files/Industrial%20index/indexes_eng/"
CUR = {"mpi": BASE + "month/Prodidx1_E.xlsx", "capu": BASE + "month/capidx_E.xlsx"}
OLD_ZIP = BASE + "index2016_2023.zip"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept": "*/*"}
SRC = "Office of Industrial Economics (OIE), Thailand"
MON = {m: i + 1 for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}
SHORT = {"10": "Food", "11": "Beverages", "12": "Tobacco", "13": "Textiles", "14": "Wearing apparel", "15": "Leather",
         "16": "Wood", "17": "Paper", "18": "Printing", "19": "Refined petroleum", "20": "Chemicals", "21": "Pharmaceuticals",
         "22": "Rubber and plastics", "23": "Non-metallic minerals", "24": "Basic metals", "25": "Fabricated metals",
         "26": "Computer and electronics", "27": "Electrical equipment", "28": "Machinery", "29": "Motor vehicles",
         "30": "Other transport", "31": "Furniture", "32": "Other manufacturing"}


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                return r.read(), dict(r.headers)
        except Exception:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def num(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def rows_of(data, sheet):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    if sheet not in wb.sheetnames:
        raise CheckFailed([f"workbook: sheet {sheet!r} missing ({wb.sheetnames})"])
    return [list(r) for r in wb[sheet].iter_rows(values_only=True)]


def label_col(rows):
    """Column holding the row labels ('Integrated Index ...', 'TSIC : 10 ...')."""
    for r in rows[4:12]:
        for j, c in enumerate(r[:4]):
            if isinstance(c, str) and c.startswith("Integrated Index"):
                return j
    raise CheckFailed(["workbook: 'Integrated Index' row not found"])


def periods(rows, lc, freq):
    """{column: period} from the two header rows: monthly 'YYYY-MM', quarterly 'YYYY-Qn'."""
    hdr_y, hdr_p = rows[3], rows[4]
    out, year = {}, None
    for j in range(lc + 2, len(hdr_p)):
        y = hdr_y[j] if j < len(hdr_y) else None
        if y not in (None, "") and re.fullmatch(r"\d{4}(\.0)?", str(y).strip()):
            year = int(float(y))
        p = str(hdr_p[j] or "").strip().upper().rstrip(".")
        if freq == "M" and p[:3] in MON and year:
            out[j] = f"{year}-{MON[p[:3]]:02d}"
        elif freq == "Q":
            m = re.fullmatch(r"([1-4])\s*['\u2019]?\s*/\s*(\d{4})", p)   # OIE marks recent quarters 2'/2025
            if m:
                out[j] = f"{m.group(2)}-Q{m.group(1)}"
    return out


def pick(rows, freq):
    """-> ({code: (label, weight)}, {(code, period): value}, published % change of the last column or None).
    code: 'all' (not seasonally adjusted), 'all_sa' (seasonally adjusted, old base only), or a 2-digit TSIC."""
    lc = label_col(rows)
    cols = periods(rows, lc, freq)
    pub = None
    meta, vals = {}, {}
    for r in rows[5:]:
        lab = r[lc] if lc < len(r) else None
        if not isinstance(lab, str):
            continue
        s = re.sub(r"\s+", " ", lab).strip()
        if s.startswith("Integrated Index"):
            code = "all_sa" if "(Seasonally adjusted)" in s else "all"
        else:
            m = re.fullmatch(r"TSIC : (\d{2}) (.+)", s)
            if not m:
                continue
            code = m.group(1)
        if code in meta:
            continue
        meta[code] = (s, num(r[lc + 1]))
        for j, p in cols.items():
            v = num(r[j]) if j < len(r) else None
            if v is not None:
                vals[(code, p)] = v
        if code == "all":
            tail = [num(c) for c in r[max(cols) + 1:max(cols) + 3]] if cols else []
            pub = tail[-1] if tail and tail[-1] is not None else None
    return meta, vals, pub


def prev(p):
    return f"{int(p[:4]) - 1}{p[4:]}"


def pdate(p):
    if "-Q" in p:
        return f"{p[:4]}-{int(p[-1]) * 3:02d}-01"
    return f"{p}-01"


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    RAWDIR.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release.json", {}) or {}
    cur = {k: get(u) for k, u in CUR.items()}
    fp = hashlib.sha256(b"".join(v[0] for v in cur.values())).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force and (OUT / "th_mpi.csv").exists():
        return {"updated": False, "code": state.get("code"), "summary": f"no change ({state.get('label')})"}
    # the 2016-base archive does not change: read once, keep the cells used
    oldp = RAWDIR / "base2016.json.gz"
    if oldp.exists() and not force:
        old = json.loads(gzip.decompress(oldp.read_bytes()))
    else:
        z = zipfile.ZipFile(io.BytesIO(get(OLD_ZIP)[0]))
        names = {n.lower(): n for n in z.namelist()}
        old = {}
        for key, fn, sheet in (("mpi_m", "prodidx1_e.xlsx", "รายเดือน"), ("mpi_q", "prodidx1_e.xlsx", "รายไตรมาส"),
                               ("capu_m", "capidx_e.xlsx", "รายเดือน")):
            rows = rows_of(z.read(names[fn]), sheet)
            lc = label_col(rows)
            keep = rows[:5] + [r for r in rows[5:] if isinstance(r[lc] if lc < len(r) else None, str)
                               and (r[lc].startswith("Integrated") or re.match(r"TSIC : \d{2} ", r[lc]))]
            old[key] = [[c if isinstance(c, (int, float, str)) or c is None else str(c) for c in r] for r in keep]
        oldp.write_bytes(gzip.compress(json.dumps(old, ensure_ascii=False).encode(), 9))

    mpi_m = rows_of(cur["mpi"][0], "รายเดือน")
    mpi_q = rows_of(cur["mpi"][0], "รายไตรมาส")
    capu_m = rows_of(cur["capu"][0], "รายเดือน")
    sets = {("2021", "M"): pick(mpi_m, "M"), ("2021", "Q"): pick(mpi_q, "Q"),
            ("2016", "M"): pick(old["mpi_m"], "M"), ("2016", "Q"): pick(old["mpi_q"], "Q")}
    capu = {"2021": pick(capu_m, "M"), "2016": pick(old["capu_m"], "M")}

    errors, warnings = [], []
    meta, vm, pub_m = sets[("2021", "M")]
    _, vq, pub_q = sets[("2021", "Q")]
    divs = sorted(c for c in meta if c.isdigit())
    if len(divs) < 21:
        errors.append(f"current MPI: {len(divs)} TSIC 2-digit industries (expected 22)")
    w = sum(meta[c][1] or 0 for c in divs)
    if abs(w - 100) > 0.5:
        errors.append(f"current MPI: industry weights sum to {w:.2f}")
    months = sorted(p for (c, p) in vm if c == "all")
    if not months or months[0] != "2021-01":
        errors.append(f"current MPI: months {months[:2]}..")
    latest = months[-1]
    gaps = [c for c in divs if (c, latest) not in vm]
    if gaps:
        errors.append(f"current MPI {latest}: no index for {gaps}")
    quarters = sorted((p for (c, p) in vq if c == "all"), key=lambda p: (p[:4], p[-1]))
    lq = quarters[-1] if quarters else None

    rows = []

    def add(base, freq, code, period, measure, value, calc=""):
        lab, wt = (sets[(base, freq)][0].get(code) or ("", None))
        rows.append({"date": pdate(period), "period": period, "freq": freq, "base": base, "code": code,
                     "industry": "Manufacturing" if code == "all" else "Manufacturing, seasonally adjusted" if code == "all_sa" else SHORT.get(code, lab),
                     "label": lab, "weight": "" if wt is None else round(wt, 4), "measure": measure,
                     "value": round(value, 4), "calculated": calc})

    for (base, freq), (mt, vals, _) in sets.items():
        for (code, p), v in vals.items():
            add(base, freq, code, p, "index", v)
            b = vals.get((code, prev(p)))
            if b and b > 0 and code != "all_sa":
                add(base, freq, code, p, "yoy", (v / b - 1) * 100, "y")
    # calculated y/y against OIE's published latest rates
    cy = vm.get(("all", latest)), vm.get(("all", prev(latest)))
    my = (cy[0] / cy[1] - 1) * 100 if all(cy) else None
    if pub_m is None or my is None or abs(my - pub_m) > 0.01:
        errors.append(f"MPI {latest} y/y: calculated {my} vs OIE {pub_m}")
    if lq:
        qy = vq.get(("all", lq)), vq.get(("all", prev(lq)))
        qq = (qy[0] / qy[1] - 1) * 100 if all(qy) else None
        if pub_q is None or qq is None or abs(qq - pub_q) > 0.01:
            errors.append(f"MPI {lq} y/y: calculated {qq} vs OIE {pub_q}")
        # quarterly index = average of its months (OIE), as a check
        mq = [vm.get(("all", f"{lq[:4]}-{int(lq[-1]) * 3 - k:02d}")) for k in (2, 1, 0)]
        if all(mq) and abs(sum(mq) / 3 - vq[("all", lq)]) > 0.05:
            warnings.append(f"MPI {lq}: quarterly index {vq[('all', lq)]:.3f} vs mean of months {sum(mq) / 3:.3f}")
    for (base, freq), (mt, vals, _) in sets.items():
        for (c, p), v in vals.items():
            if not 5 < v < 400:
                (errors if c in ("all", "all_sa") else warnings).append(f"MPI {base} {freq} {c} {p}: {v} out of range")
    cmeta, cvals, _ = capu["2021"]
    for base, (mt, vals, _) in capu.items():
        for (c, p), v in vals.items():
            if not 0 < v <= 100:
                (errors if c == "all" else warnings).append(f"capacity utilisation {base} {c} {p}: {v} out of range")
            rows.append({"date": pdate(p), "period": p, "freq": "M", "base": base, "code": c,
                         "industry": "Manufacturing" if c == "all" else "Manufacturing, seasonally adjusted" if c == "all_sa" else SHORT.get(c, mt[c][0]),
                         "label": mt[c][0], "weight": "" if mt[c][1] is None else round(mt[c][1], 4), "measure": "capu",
                         "value": round(v, 4), "calculated": ""})
    if ("all", latest) not in cvals:
        warnings.append(f"capacity utilisation: no figure for {latest}")
    if errors:
        raise CheckFailed(errors)

    keep = {}
    for key, rws in (("mpi_m", mpi_m), ("mpi_q", mpi_q), ("capu_m", capu_m)):
        lc = label_col(rws)
        keep[key] = [[c if isinstance(c, (int, float, str)) or c is None else str(c) for c in r] for r in rws[:5] + [
            r for r in rws[5:] if isinstance(r[lc] if lc < len(r) else None, str)
            and (r[lc].startswith("Integrated") or re.match(r"TSIC : \d{2} ", r[lc]))]]
    (RAWDIR / f"{latest}.json.gz").write_bytes(gzip.compress(json.dumps(keep, ensure_ascii=False).encode(), 9))
    cols = ["date", "period", "freq", "base", "code", "industry", "label", "weight", "measure", "value", "calculated"]
    rows.sort(key=lambda r: (r["measure"], r["base"], r["freq"], r["code"], r["date"]))
    with open(OUT / "th_mpi.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        wr.writeheader()
        wr.writerows(rows)
    code = f"M{latest}"
    label = f"{['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][int(latest[5:]) - 1]} {latest[:4]}"
    nlong = write_long(({"country": "TH", "indicator": "mpi", "series": f"{r['code']}_{r['measure']}_{r['freq']}_b{r['base']}",
                         "label": f"{r['industry']}, {'capacity utilisation' if r['measure'] == 'capu' else 'MPI ' + r['base'] + ' base'}"
                                  f"{', y/y (calculated)' if r['measure'] == 'yoy' else ''}",
                         "measure": r["measure"], "area": "national", "freq": r["freq"], "date": r["date"], "value": r["value"],
                         "unit": "%" if r["measure"] != "index" else f"index, {r['base']} = 100", "source": SRC, "release": code}
                        for r in rows), OUT / "long.csv")
    release = {"code": code, "label": label, "latest_month": latest, "latest_quarter": lq, "published_yoy_month": pub_m,
               "published_yoy_quarter": pub_q, "last_modified": cur["mpi"][1].get("Last-Modified", ""),
               "table": "OIE Prodidx1_E.xlsx (MPI, value-added weights, chain-linked 2021 = 100), capidx_E.xlsx; archive index2016_2023.zip"}
    write_release(OUT, release, warnings, len(rows), {"fingerprint": fp, "long_rows": nlong})
    return {"updated": True, "code": code, "summary": f"{label}: MPI {my:+.2f}% y/y (OIE {pub_m:+.2f}); {len(rows)} rows",
            "warnings": warnings}
