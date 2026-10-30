"""BPS-Statistics Indonesia WebAPI (webapi.bps.go.id): client and readers for what the Indonesia dashboard uses.

The key is the repository secret BPS_KEY (environment variable). It is never written to any output.
  - list/model/...: JSON lists (variables, static tables, press releases), paged as {"data": [paging, [rows]]}.
  - view/model/statictable: one static table as HTML.
  - Press release (BRS) PDFs come from download.php links the API returns; they are read with pdftotext -layout
    (poppler-utils), and only the text is kept.
"""
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

API = "https://webapi.bps.go.id/v1/api"
UA = {"User-Agent": "asia-vitals/1.0 (research dashboard)", "Accept": "application/json"}
MONTHS_ID = {"januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6, "juli": 7, "agustus": 8,
             "september": 9, "oktober": 10, "november": 11, "desember": 12}
NUM = re.compile(r"~\s?0|-?\d+[.,]\d+|(?<![\w.,])-?\d+(?![\w.,])")


class KeyMissing(RuntimeError):
    pass


def key():
    k = os.environ.get("BPS_KEY", "").strip()
    if not k:
        raise KeyMissing("BPS_KEY is not set")
    return k


def call(path, tries=3):
    k = key()
    url = f"{API}/{path.strip('/')}/key/{k}/"
    err = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                d = json.loads(r.read())
            if d.get("status") != "OK":
                raise ValueError(f"status {d.get('status')}: {str(d)[:200]}")
            return d
        except (urllib.error.URLError, ValueError, TimeoutError, json.JSONDecodeError) as e:  # noqa: PERF203
            err = str(e).replace(k, "***")
            time.sleep(4 * (i + 1))
    raise RuntimeError(f"BPS WebAPI {path}: {err}")


def rows(path, stop=None):
    """All rows of a paged list call; with stop(row), stops after the page where a row meets it
    (press releases are listed newest first)."""
    out, page = [], 1
    while True:
        d = call(f"{path}/page/{page}")
        data = d.get("data")
        if not isinstance(data, list) or len(data) < 2:
            return out
        paging, rs = data
        out += rs
        if page >= int(paging.get("pages", 1)) or (stop and any(stop(r) for r in rs)):
            return out
        page += 1
        time.sleep(0.2)


def download(url, tries=3):
    err = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]}), timeout=180) as r:
                b = r.read()
            if not b.startswith(b"%PDF"):
                raise ValueError(f"not a PDF: {b[:60]!r}")
            return b
        except (urllib.error.URLError, ValueError, TimeoutError) as e:  # noqa: PERF203
            err = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"download failed: {err}")


def pdf_text(b):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(b)
        f.flush()
        return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, check=True).stdout.decode("utf-8", "replace")


def num(tok):
    t = tok.replace(" ", "")
    if t.startswith("~"):
        return 0.0
    return float(t.replace(",", "."))


def numbers(line):
    return [num(m.group(0)) for m in NUM.finditer(line)]


def month_of(text):
    """'YYYY-MM' of a CPI release from its running header ('Perkembangan Indeks Harga Konsumen September 2026')."""
    m = re.search(r"Perkembangan Indeks Harga Konsumen\s+([A-Za-z]+)\s+(\d{4})", text)
    if not m or m.group(1).lower() not in MONTHS_ID:
        return None
    return f"{m.group(2)}-{MONTHS_ID[m.group(1).lower()]:02d}"


def table_rows(text, start, stop, width=(8,)):
    """Numeric rows (exactly `width` numbers) between a line matching `start` and the next matching `stop`,
    with the label text collected since the previous numeric row."""
    lines = text.splitlines()
    i0 = next((i for i, l in enumerate(lines) if re.search(start, l)), None)
    if i0 is None:
        return []
    out, label = [], []
    for l in lines[i0 + 1:]:
        if re.search(stop, l):
            break
        ns = numbers(l)
        words = re.sub(NUM, " ", l).strip()
        if len(ns) in width:
            out.append((" ".join(label + [words]).strip(), ns))
            label = []
        elif ns and words == "":
            continue
        elif words and not ns:
            label.append(words)
        elif words:
            label = [words]
    return out


# --- Dynamic tables (variables): GDP and trade -------------------------------------------------------------------

def var_years(vid):
    """{year: th_id} for a variable (the WebAPI's own year codes; the list is paged)."""
    out = {}
    for t in rows(f"list/model/th/domain/0000/var/{vid}"):
        y = str(t.get("th", "")).strip()
        if y.isdigit():
            out[int(y)] = t["th_id"]
    return out


def var_data(vid, years=None):
    """Every value of a variable, as published: (meta, [{vervar, vervar_label, turvar, turvar_label, year,
    turtahun, turtahun_label, value, unit}]). unit is the
    variable's unit as stated in that year's answer (BPS changes it between years for some trade tables). Years are fetched one call each; keys of the WebAPI's datacontent are
    vervar + var + turvar + th + turtahun, rebuilt here from the listed dimensions (never split)."""
    ids = var_years(vid)
    meta, out = None, []
    for y in sorted(ids):
        if years and y not in years:
            continue
        d = call(f"list/model/data/domain/0000/var/{vid}/th/{ids[y]}")
        dc = d.get("datacontent") or {}
        if not isinstance(dc, dict) or not dc:
            continue
        meta = {"var": (d.get("var") or [{}])[0], "vervar": d.get("vervar") or [], "turvar": d.get("turvar") or [],
                "turtahun": d.get("turtahun") or [], "last_update": d.get("last_update")}
        th = d["tahun"][0]["val"] if d.get("tahun") else ids[y]
        unit = ((d.get("var") or [{}])[0].get("unit") or "").strip()
        for vv in d.get("vervar") or []:
            for tv in d.get("turvar") or [{"val": "0", "label": ""}]:
                for tt in d.get("turtahun") or []:
                    k = f"{vv['val']}{vid}{tv['val']}{th}{tt['val']}"
                    if k in dc and dc[k] not in ("", None):
                        try:
                            v = float(dc[k])
                        except (TypeError, ValueError):
                            continue
                        out.append({"vervar": vv["val"], "vervar_label": vv["label"], "turvar": tv["val"],
                                    "turvar_label": tv["label"], "year": y, "turtahun": tt["val"],
                                    "turtahun_label": tt["label"], "value": v, "unit": unit})
        time.sleep(0.2)
    return meta, out


QUARTER_ID = {"triwulan i": 1, "triwulan ii": 2, "triwulan iii": 3, "triwulan iv": 4}


def period_of(rec):
    """('Q', 'YYYY-MM-01') for a quarter (first month), ('M', ...) for a month, ('A', 'YYYY-01-01') for a year."""
    lab = re.sub(r"\s+", " ", (rec["turtahun_label"] or "").strip().lower())
    y = rec["year"]
    if lab in QUARTER_ID:
        return "Q", f"{y}-{3 * QUARTER_ID[lab] - 2:02d}-01"
    if lab in MONTHS_ID:
        return "M", f"{y}-{MONTHS_ID[lab]:02d}-01"
    if lab in ("tahunan", "tahun", "jumlah"):
        return "A", f"{y}-01-01"
    return None, None
