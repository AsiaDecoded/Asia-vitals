"""BPS WebAPI and Bank Indonesia SEKI probe for the Indonesia GDP and trade tabs.

  BPS_KEY=... python -I pipeline/tools/bps_gdp_trade_probe.py OUTDIR

Saves: every national variable (dynamic table) with its subject; the ones on GDP and trade with their periods
and the latest data; static tables and press releases on GDP and trade (titles, dates); the latest GDP and
trade release PDFs as text; the SEKI GDP and trade workbooks (sheet names, header rows, first labels).
The key never appears in the output.
"""
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bps_api_discover import KEY, get, rows_of  # noqa: E402

GDP = re.compile(r"(?i)produk domestik bruto|\bPDB\b|pertumbuhan ekonomi|gross domestic|\bGDP\b|pengeluaran.*konsumsi|"
                 r"pembentukan modal|lapangan usaha")
TRADE = re.compile(r"(?i)ekspor|impor|export|import|neraca perdagangan|trade balance|nilai tukar perdagangan|terms of trade")


def scrub(s):
    return s.replace(KEY, "***") if KEY else s


def listall(path, limit=400):
    out, page = [], 1
    while page <= limit:
        st, d, s = get(f"{path}/page/{page}")
        paging, rows = rows_of(d)
        out += rows
        if not paging or page >= int(paging.get("pages", 1)):
            break
        page += 1
    return out


def pdf_text(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "asia-vitals/1.0"}), timeout=180) as r:
        b = r.read()
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(b)
        f.flush()
        return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, check=True).stdout.decode("utf-8", "replace")


def bps(out):
    log = []
    allvars = listall("list/model/var/domain/0000/lang/ind")
    keep = [{k: v.get(k) for k in ("var_id", "title", "sub_id", "sub_name", "subcsa_name", "def", "notes", "vertical", "unit", "graph_id")}
            for v in allvars]
    (out / "vars_all.json").write_text(json.dumps(keep, ensure_ascii=False, indent=1))
    hits = [v for v in keep if GDP.search(v["title"] or "") or TRADE.search(v["title"] or "")]
    (out / "vars_hits.json").write_text(json.dumps(hits, ensure_ascii=False, indent=1))
    print(len(keep), "vars;", len(hits), "GDP/trade", flush=True)
    for v in hits[:120]:
        vid = v["var_id"]
        st, d, s = get(f"list/model/th/domain/0000/var/{vid}")
        _, ths = rows_of(d)
        years = sorted(int(t["th"]) for t in ths if str(t.get("th", "")).isdigit())
        ids = {int(t["th"]): t["th_id"] for t in ths if str(t.get("th", "")).isdigit()}
        rec = {"var_id": vid, "title": v["title"], "years": [years[0], years[-1]] if years else None, "n_years": len(years)}
        if years:
            last = ids[years[-1]]
            st, d, s = get(f"list/model/data/domain/0000/var/{vid}/th/{last}")
            (out / f"data_{vid}_{years[-1]}.json").write_text(scrub(json.dumps(d, ensure_ascii=False))[:400000])
            rec["status"] = st
        log.append(rec)
        (out / "vars_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
    tabs = listall("list/model/statictable/domain/0000/lang/ind")
    tk = [{k: t.get(k) for k in ("table_id", "title", "subj_id", "subj", "updt_date", "excel")} for t in tabs
          if GDP.search(t.get("title") or "") or TRADE.search(t.get("title") or "")]
    (out / "static_hits.json").write_text(scrub(json.dumps(tk, ensure_ascii=False, indent=1)))
    print(len(tabs), "static tables;", len(tk), "GDP/trade", flush=True)
    rels = listall("list/model/pressrelease/domain/0000/lang/ind", limit=300)
    rk = [{k: r.get(k) for k in ("brs_id", "subj", "title", "rl_date", "pdf")} for r in rels
          if GDP.search(r.get("title") or "") or TRADE.search(r.get("title") or "")]
    (out / "releases_hits.json").write_text(scrub(json.dumps(rk, ensure_ascii=False, indent=1)))
    print(len(rels), "releases;", len(rk), "GDP/trade", flush=True)
    for name, pat in (("gdp", r"(?i)pertumbuhan ekonomi indonesia"), ("trade", r"(?i)ekspor.*impor|neraca perdagangan")):
        got = [r for r in rk if re.search(pat, r["title"] or "") and r.get("pdf")][:3]
        for i, r in enumerate(got):
            try:
                (out / f"brs_{name}_{i}.txt").write_text(pdf_text(r["pdf"]))
                (out / f"brs_{name}_{i}.meta.json").write_text(json.dumps({"title": r["title"], "rl_date": r["rl_date"]}, ensure_ascii=False))
            except Exception as e:  # noqa: BLE001
                (out / f"brs_{name}_{i}.error.txt").write_text(scrub(repr(e)))


def seki(out):
    import xlrd  # noqa: PLC0415
    ua = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}
    res = {}
    names = [f"{a}_{b}" for a in (5, 6, 7) for b in range(1, 16)]
    for n in names:
        url = f"https://www.bi.go.id/SEKI/tabel/TABEL{n}.xls"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=ua), timeout=90) as r:
                b = r.read()
            if not b.startswith(b"\xd0\xcf\x11\xe0"):
                res[n] = {"error": f"not xls: {b[:60]!r}"}
                continue
            (out / "seki").mkdir(exist_ok=True)
            (out / "seki" / f"TABEL{n}.xls").write_bytes(b)
            wb = xlrd.open_workbook(file_contents=b)
            info = []
            for sh in wb.sheets():
                head = [[str(x)[:40] for x in sh.row_values(r)[:14]] for r in range(min(sh.nrows, 10))]
                labels = [str(sh.cell_value(r, 0))[:60] + " | " + str(sh.cell_value(r, 1) if sh.ncols > 1 else "")[:60]
                          for r in range(min(sh.nrows, 60))]
                info.append({"sheet": sh.name, "rows": sh.nrows, "cols": sh.ncols, "head": head, "labels": labels,
                             "last_header": [str(x)[:20] for x in sh.row_values(min(6, sh.nrows - 1))[-6:]]})
            res[n] = {"bytes": len(b), "sheets": info}
        except Exception as e:  # noqa: BLE001
            res[n] = {"error": repr(e)}
        print("SEKI", n, "error" if "error" in res[n] else len(res[n]["sheets"]), flush=True)
    (out / "seki.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        seki(out)
    except Exception as e:  # noqa: BLE001
        (out / "seki_error.txt").write_text(repr(e))
    if not KEY:
        (out / "bps_error.txt").write_text("BPS_KEY not set")
        return
    bps(out)


if __name__ == "__main__":
    main(sys.argv[1])
