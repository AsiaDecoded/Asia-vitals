"""Indonesia central government budget outturn, year to date, monthly: the Ministry of Finance's APBN KiTa press-
conference deck (Paparan / Konpers), as published. Nothing calculated.

Where it comes from: the Ministry's site lists APBN KiTa publications through its content API
(POST https://media.kemenkeu.go.id/SinglePage/Filter, path=/Pages/Home/Informasi-Terbaru/APBN-Kita, param1=<year>);
each item links a PDF on media.kemenkeu.go.id/getmedia/... . The monthly deck carries a page headed
summary of the year-to-date outturn in up to three forms (front-page box "KINERJA APBN HINGGA <month>", summary
table "A. PENDAPATAN NEGARA ... D. SURPLUS/(DEFISIT)", page "REALISASI APBN S.D. <date>", and a month-by-month table of the year so far): state revenue
(Pendapatan Negara), state expenditure (Belanja Negara), surplus/deficit (and % of GDP) and primary balance
(Keseimbangan Primer), Rp trillion, one decimal. Every form present is read; they must agree or the source stops.
The reference month is read from the deck, not from the list's titles or dates (they do not always match the file). Decks from 2025 on (the press-conference format); earlier monthly reports use
other layouts and are not read.

Text of every deck read is kept (raw/id/fiscal_kemenkeu/<file id>.txt.gz), so later runs download only new files.
Released about a week into the month after the reference month (Sep 2026 outturn: 9 Oct 2026).
"""
import csv
import gzip
import hashlib
import json
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from core.common import DATA, RAW, CheckFailed, now, read_json, write_long

NAME = "id_fiscal_kemenkeu"
DESCRIPTION = "Indonesia budget outturn year to date, monthly (Ministry of Finance APBN KiTa deck), as published"
OUT = DATA / "id" / "fiscal"
RAWDIR = RAW / "id" / "fiscal_kemenkeu"
SOURCE = "Ministry of Finance of Indonesia (APBN KiTa)"
API = "https://media.kemenkeu.go.id/SinglePage/Filter"
LIST_PATH = "/Pages/Home/Informasi-Terbaru/APBN-Kita"
FIRST_YEAR = 2025
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json,text/plain,*/*", "Origin": "https://www.kemenkeu.go.id", "Referer": "https://www.kemenkeu.go.id/"}
MONTHS = {"januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6, "juli": 7, "agustus": 8,
          "september": 9, "oktober": 10, "november": 11, "desember": 12}
MON_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
NUM = r"\(?-?\s*Rp\s?([\d.]+,\d)\s*T\)?"


def _num(s):
    return float(s.replace(".", "").replace(",", "."))


def list_decks(year, tries=3):
    """[(file url, file id, title, published)] for the year's press-conference decks (CategoryApbn 'Paparan', or a
    'Konpers' file name)."""
    url = API + "?" + urllib.parse.urlencode({"path": LIST_PATH, "lang": "id-id", "hassubcategory": "true", "param1": str(year)})
    err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=b"", headers=UA, method="POST")
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read())
            break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:  # noqa: PERF203
            err = e
            time.sleep(5 * (i + 1))
    else:
        raise RuntimeError(f"APBN KiTa list {year}: {err}")
    out = []
    for c in ((d.get("Data") or {}).get("Content") or []):
        f = (c.get("File") or "").strip()
        if not f.lower().split("?")[0].endswith(".pdf") and "ext=.pdf" not in f.lower():
            continue
        if (c.get("CategoryApbn") or "") == "Paparan" or re.search(r"(?i)konpers", f):
            fid = re.search(r"/getmedia/([0-9a-f\-]{36})/", f)
            if fid:
                out.append((f.replace("http://", "https://"), fid.group(1), c.get("Title") or "", c.get("DocumentPublishFrom") or ""))
    return out


def pdf_text(url, tries=3):
    err = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]}), timeout=300) as r:
                b = r.read()
            if b[:4] != b"%PDF":
                raise ValueError(f"not a PDF: {b[:60]!r}")
            with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
                f.write(b)
                f.flush()
                return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, check=True).stdout.decode("utf-8", "replace")
        except (urllib.error.URLError, ValueError, TimeoutError) as e:  # noqa: PERF203
            err = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"download failed: {err}")


MON_ABBR = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "jun": 6, "jul": 7, "agt": 8, "agu": 8, "ags": 8,
            "sep": 9, "okt": 10, "nov": 11, "des": 12}
AMT = re.compile(r"(\()?(-)?Rp\s?([\d.]+,\d)\s*T\)?")
TNUM = re.compile(r"\(?-?[\d.]+,\d+\)?")


def _signed(tok):
    neg = tok.startswith("(") or tok.startswith("-")
    v = _num(tok.strip("()-"))
    return -v if neg else v


def _month_word(word, year):
    w = word.lower()
    m = MONTHS.get(w) or MON_ABBR.get(w[:3])
    return f"{year}-{m:02d}" if m else None


def parse_table(text):
    """Summary table (A. PENDAPATAN NEGARA ... D. SURPLUS/(DEFISIT), % thd PDB): the current year's latest
    'Real s.d.' column is the third number from the right on each row (real, % of budget, growth)."""
    lines = text.splitlines()
    i = next((k for k, l in enumerate(lines) if re.match(r"\s*A\.\s+PENDAPATAN NEGARA\s+[\d(]", l)), None)
    if i is None:
        return None
    row, bal_pos = {}, None
    for k in range(i, min(i + 30, len(lines))):
        l = lines[k]
        for key, pat in (("revenue", r"^\s*A\.\s+PENDAPATAN NEGARA"), ("expenditure", r"^\s*B\.\s+BELANJA NEGARA"),
                         ("primary_balance", r"^\s*C\.\s+KESEIMBANGAN PRIMER"), ("balance", r"^\s*D\.\s+SURPLUS")):
            lm = re.match(pat, l)
            if lm and key not in row:
                s1 = lm.end() + re.match(r"[\s/]*(\((?:DEFISIT|SURPLUS)\))?", l[lm.end():], re.I).end()  # "/ (DEFISIT)"
                cut = re.search(r"[A-Za-z\u25b2\u25bc%]", l[s1:])
                end = s1 + cut.start() if cut else len(l)
                toks = [(m.start() + s1, m.group()) for m in TNUM.finditer(l[s1:end])]
                if len(toks) >= 8:
                    row[key] = _signed(toks[-3][1])
                    if key == "balance":
                        bal_pos = toks[-3][0]
        # % of GDP: the value standing under the deficit figure used (the row can carry extra columns)
        if re.match(r"^\s*% thd PDB", l) and "balance_pct_gdp" not in row and bal_pos is not None:
            s1 = l.index("PDB") + 3
            cut = re.search(r"[A-Za-z]", l[s1:])
            end = s1 + cut.start() if cut else len(l)
            toks = [(m.start() + s1, m.group()) for m in TNUM.finditer(l[s1:end])]
            if toks:
                pos, tok = min(toks, key=lambda t: abs(t[0] - bal_pos))
                if abs(pos - bal_pos) <= 6:
                    row["balance_pct_gdp"] = _signed(tok)
    if not all(k in row for k in ("revenue", "expenditure", "balance")):
        return None
    head = "\n".join(lines[max(0, i - 15): i])
    ds = re.findall(r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|Mei|Jun|Jul|Agt|Agu|Ags|Sep|Sept|Okt|Nov|Des)[a-z]*\b", head)
    yr = re.findall(r"\b(20\d\d)\b", head)
    if not ds or not yr:
        return None
    row["month"] = _month_word(ds[-1][1], max(yr))
    return row if row["month"] else None


def parse_front(text):
    """Front-page box: KINERJA APBN PER/HINGGA <MONTH> <YEAR>, then PENDAPATAN NEGARA, BELANJA NEGARA, DEFISIT APBN
    (with % PDB) and KESEIMBANGAN PRIMER in columns; amounts matched to the nearest column heading."""
    m = re.search(r"KINERJA APBN (?:PER|HINGGA|S\.?\s?D\.?)\s+([A-Za-z]+)\s+(\d{4})", text[:6000])
    if not m:
        return None
    month = _month_word(m.group(1), m.group(2))
    lines = text[m.end():m.end() + 3000].splitlines()[:30]
    h = next((k for k, l in enumerate(lines) if "PENDAPATAN NEGARA" in l and "BELANJA NEGARA" in l), None)
    if h is None or not month:
        return None
    cols = {"revenue": lines[h].index("PENDAPATAN"), "expenditure": lines[h].index("BELANJA")}
    dm = re.search(r"(DEFISIT|SURPLUS) APBN", lines[h])
    if not dm:
        return None
    cols["balance"] = dm.start()
    got, kp = {}, None
    for k in range(h + 1, len(lines)):
        l = lines[k]
        if "KESEIMBANGAN PRIMER" in l:
            kp = l.index("KESEIMBANGAN PRIMER")
            continue
        for a in AMT.finditer(l):
            pos = a.start()
            near = min(cols, key=lambda c: abs(cols[c] - pos))
            key = "primary_balance" if (kp is not None and abs(kp - pos) < 25) else near
            if key not in got:
                v = _num(a.group(3))
                got[key] = v
    if not all(k in got for k in ("revenue", "expenditure", "balance")):
        return None
    got["balance"] = -got["balance"] if dm.group(1) == "DEFISIT" else got["balance"]
    pct = re.search(r"\((-?)(\d+,\d+)\s*%\s*PDB\)", "\n".join(lines))
    if pct:
        got["balance_pct_gdp"] = -_num(pct.group(2)) if (pct.group(1) or got["balance"] < 0) else _num(pct.group(2))
    if "primary_balance" in got:
        intro = text[m.end():m.end() + 400].lower()
        if re.search(r"keseimbangan primer (negatif|defisit)", intro):
            got["primary_balance"] = -got["primary_balance"]
        elif not re.search(r"keseimbangan primer (positif|surplus)", intro):
            got.pop("primary_balance")      # sign not stated: leave it to the other readers
    got["month"] = month
    return got


def parse_realisasi(text):
    """'REALISASI APBN S.D. <day> <MONTH> <YEAR>' page: Pendapatan Negara, Belanja Negara, (Defisit APBN),
    Keseimbangan Primer Surplus/Defisit, amounts in the right-hand column."""
    m = re.search(r"REALISASI APBN S\.?\s?D\.?\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text, re.I)
    if not m:
        return None
    month = _month_word(m.group(2), m.group(3))
    block = text[m.end():m.end() + 3000]
    block = re.split(r"\n\s*Pendapatan\s*\n\s*Negara\s*\n", block)[0]
    got = {}
    for key, lab in (("revenue", r"Pendapatan[ \t]+(\(?-?Rp[\d.]+,\d[ \t]*T\)?)"),
                     ("expenditure", r"Belanja[ \t]+(\(?-?Rp[\d.]+,\d[ \t]*T\)?)"),
                     ("balance", r"(\(?-?Rp[\d.]+,\d[ \t]*T\)?)[^\n]*\n[ \t]*(?:Defisit|Surplus)[ \t]+APBN"),
                     ("primary_balance", r"Keseimbangan[ \t]+(\(?-?Rp[\d.]+,\d[ \t]*T\)?)")):
        lm = re.search(lab, block)
        if not lm:
            continue
        a = AMT.search(lm.group(1))
        v = _num(a.group(3))
        got[key] = -v if (a.group(1) or a.group(2)) else v
    if not all(k in got for k in ("revenue", "expenditure", "balance")):
        return None
    dl = re.search(r"(Defisit|Surplus)\s+APBN", block)
    if dl and dl.group(1) == "Defisit":
        got["balance"] = -abs(got["balance"])
    pw = re.search(r"Primer\s+(Surplus|Defisit)", block)
    if "primary_balance" in got:
        if pw:
            got["primary_balance"] = abs(got["primary_balance"]) * (1 if pw.group(1) == "Surplus" else -1)
        else:
            got.pop("primary_balance")
    pct = re.search(r"(\d+,\d+)\s*%\s*PDB", block)
    if pct:
        got["balance_pct_gdp"] = _num(pct.group(1)) * (-1 if got["balance"] < 0 else 1)
    got["month"] = month
    return got if month else None


def parse_progression(text):
    """Month-by-month table ('Real s.d. 31 Maret | Growth | Real s.d. 30 April | ...' under one year heading, rows
    A. PENDAPATAN NEGARA, B. BELANJA NEGARA, C. KESEIMBANGAN PRIMER, D. SURPLUS/(DEFISIT), % SURPLUS/(DEFISIT)-PDB):
    {YYYY-MM: {revenue, expenditure, primary_balance, balance, balance_pct_gdp}} for every month column."""
    out = {}
    lines = text.splitlines()
    for i, l in enumerate(lines):
        dates = re.findall(r"\b(\d{1,2})\s+(Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)\b", l)
        if len(dates) < 2 or not re.search(r"\bAPBN\b", " ".join(lines[max(0, i - 4): i + 1])):
            continue
        yr = re.findall(r"\b(20\d\d)\b", " ".join(lines[max(0, i - 6): i + 1]))
        if not yr:
            continue
        months = [f"{yr[-1]}-{MONTHS[m.lower()]:02d}" for _d, m in dates]
        rows = {}
        for k in range(i + 1, min(i + 40, len(lines))):
            r = lines[k]
            for key, pat in (("revenue", r"^\s*A\.\s+PENDAPATAN NEGARA"), ("expenditure", r"^\s*B\.\s+BELANJA NEGARA"),
                             ("primary_balance", r"^\s*C\.\s+KESEIMBANGAN PRIMER"), ("balance", r"^\s*D\.\s+SURPLUS"),
                             ("balance_pct_gdp", r"^\s*%\s*SURPLUS")):
                lm = re.match(pat, r)
                if lm and key not in rows:
                    rest = re.sub(r"^[\s/]*(\((?:DEFISIT|SURPLUS)\))?(-PDB)?", "", r[lm.end():], flags=re.I)
                    toks = TNUM.findall(rest)
                    rows[key] = toks
        if not all(k in rows for k in ("revenue", "expenditure", "balance")):
            continue
        n = len(months)
        for j, mth in enumerate(months):
            rec = {}
            for key, toks in rows.items():
                if key == "balance_pct_gdp":
                    idx = 1 + j                      # APBN, then one value per month
                else:
                    idx = 1 + 2 * j                  # APBN, then (real, growth) per month
                need = (1 + n) if key == "balance_pct_gdp" else (1 + 2 * n)
                if len(toks) >= need - (1 if key != "balance_pct_gdp" else 0) and idx < len(toks):
                    try:
                        rec[key] = _signed(toks[idx].rstrip(","))
                    except ValueError:
                        pass
            if all(k in rec for k in ("revenue", "expenditure", "balance")):
                out[mth] = rec
        if out:
            return out
    return out


def parse(text):
    """Year-to-date outturn, Rp trillion, from whichever of the deck's three summary forms are present; where more
    than one is read they must agree (revenue, expenditure, balance within 0.05) or the deck is rejected.
    Returns (row or None, readers used, disagreement or None)."""
    reads = {n: f(text) for n, f in (("table", parse_table), ("front", parse_front), ("realisasi", parse_realisasi))}
    reads = {n: r for n, r in reads.items() if r}
    if not reads:
        return None, [], None
    names = list(reads)
    base = reads[names[0]]
    for n in names[1:]:
        r = reads[n]
        if r["month"] != base["month"] or any(abs(r[k] - base[k]) > 0.05 for k in ("revenue", "expenditure", "balance")):
            return None, names, f"{names[0]} {base} vs {n} {r}"
    out = {"month": base["month"]}
    for k in ("revenue", "expenditure", "balance", "balance_pct_gdp", "primary_balance"):
        vals = [r[k] for r in reads.values() if r.get(k) is not None]
        if k == "primary_balance" and len({round(v, 1) for v in vals}) > 1:
            return None, names, f"primary balance differs between readers: {vals}"
        out[k] = vals[0] if vals else None
    return out, names, None


def update(force=False, **_):
    OUT.mkdir(parents=True, exist_ok=True)
    RAWDIR.mkdir(parents=True, exist_ok=True)
    state = read_json(OUT / "release_monthly.json", {}) or {}
    this_year = int(now()[:4])
    decks = []
    for y in range(FIRST_YEAR, this_year + 1):
        decks += list_decks(y)
    if not decks:
        raise CheckFailed(["no APBN KiTa press-conference decks listed"])
    rows, warnings, read, errors_pre, prog = {}, [], 0, [], {}
    for url, fid, title, pub in decks:
        path = RAWDIR / f"{fid}.txt.gz"
        if path.exists() and not force:
            text = gzip.open(path, "rt", encoding="utf-8").read()
        else:
            try:
                text = pdf_text(url)
            except Exception as e:  # noqa: BLE001
                warnings.append(f"{title}: deck not read ({e})")
                continue
            with gzip.open(path, "wt", encoding="utf-8") as f:
                f.write(text)
            read += 1
        got, used, clash = parse(text)
        if clash:
            errors_pre.append(f"{title} ({fid}): summary forms disagree: {clash}")
            continue
        if not got:
            warnings.append(f"{title} ({fid}): no outturn summary read")
            continue
        got["readers"] = "+".join(used)
        # month-by-month table (earlier months of the same year): fills months no deck's summary gave
        for mth, rec in parse_progression(text).items():
            if mth == got["month"]:
                if any(abs(rec[k] - got[k]) > 0.05 for k in ("revenue", "expenditure", "balance")):
                    errors_pre.append(f"{title} ({fid}): month-by-month table disagrees with the summary for {mth}: {rec} vs {got}")
                continue
            prog.setdefault(mth, []).append({**rec, "month": mth, "readers": "progression", "file": url, "title": title, "listed": pub})
        got.update({"file": url, "title": title, "listed": pub})
        prev = rows.get(got["month"])
        if prev and any(abs((prev[k] or 0) - (got[k] or 0)) > 0.05 for k in ("revenue", "expenditure", "balance")):
            warnings.append(f"{got['month']}: two decks disagree ({prev['title']} vs {title}); first kept")
            continue
        rows.setdefault(got["month"], got)
    for mth, recs in sorted(prog.items()):
        base = rows.get(mth) or recs[0]
        for r in recs:
            if any(abs(r[k] - base[k]) > 0.05 for k in ("revenue", "expenditure", "balance")):
                errors_pre.append(f"{mth}: month-by-month table in {r['title']} disagrees with {base.get('title')}: {r} vs {base}")
        if mth not in rows:
            rec = dict(recs[0])
            for k in ("balance_pct_gdp", "primary_balance"):
                rec.setdefault(k, None)
            rows[mth] = rec
    errors = list(errors_pre)
    if not rows:
        errors.append("no month read from any deck")
    for mth, r in sorted(rows.items()):
        if abs(r["revenue"] - r["expenditure"] - r["balance"]) > 0.15:
            errors.append(f"{mth}: revenue {r['revenue']} - expenditure {r['expenditure']} vs balance {r['balance']}")
    latest = max(rows) if rows else None
    if state.get("latest_month") and latest and latest < state["latest_month"]:
        errors.append(f"latest month {latest} is before the one stored ({state['latest_month']})")
    if errors:
        raise CheckFailed(errors)
    months = sorted(rows)
    want = [f"{y}-{m:02d}" for y in range(int(months[0][:4]), int(latest[:4]) + 1) for m in range(1, 13)
            if months[0] <= f"{y}-{m:02d}" <= latest]
    gaps = [m for m in want if m not in rows]
    if gaps:
        warnings.append(f"months with no deck read: {gaps}")
    fp = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
    if state.get("fingerprint") == fp and not force:
        return {"updated": False, "code": state.get("code"), "summary": f"no change (latest {state.get('label')})"}
    cols = ["date", "revenue", "expenditure", "balance", "balance_pct_gdp", "primary_balance", "readers", "title", "file"]
    with open(OUT / "id_fiscal_monthly.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cols)
        for mth in months:
            r = rows[mth]
            w.writerow([mth + "-01"] + ["" if r.get(c) is None else r[c] for c in cols[1:]])
    code = "K" + latest
    label = f"year to date to end-{MON_EN[int(latest[5:7]) - 1]} {latest[:4]}"

    def long_rows():
        for mth in months:
            for k, unit in (("revenue", "Rp trillion, year to date"), ("expenditure", "Rp trillion, year to date"),
                            ("balance", "Rp trillion, year to date"), ("balance_pct_gdp", "% of GDP, year to date"),
                            ("primary_balance", "Rp trillion, year to date")):
                yield {"country": "ID", "indicator": "fiscal_ytd", "series": k, "label": k.replace("_", " "), "measure": "ytd",
                       "area": "central government", "freq": "M", "date": mth + "-01", "value": rows[mth].get(k),
                       "unit": unit, "source": SOURCE, "release": code}
    nlong = write_long(long_rows(), OUT / "long_monthly.csv")
    # release record kept apart from id_fiscal_seki's release.json in the same folder
    rel = {"code": code, "label": label, "latest_month": latest, "file": rows[latest]["file"],
           "table": "Ministry of Finance APBN KiTa press-conference deck, 'Realisasi APBN s.d.' page"}
    old = read_json(OUT / "release_monthly.json", {}) or {}
    hist = [h for h in old.get("history", []) if h.get("code") != code] + [{"code": code, "processed_at": now()}]
    (OUT / "release_monthly.json").write_text(json.dumps({**rel, "processed_at": now(), "rows": len(months), "warnings": warnings,
                                                          "fingerprint": fp, "long_rows": nlong, "history": hist[-60:]},
                                                         ensure_ascii=False, indent=1) + "\n")
    (OUT / "release_monthly_row.json").write_text(json.dumps([{**rel, "processed_at": now()}], ensure_ascii=False, indent=1) + "\n")
    r = rows[latest]
    return {"updated": True, "code": code, "summary": f"{label}: revenue Rp{r['revenue']} T, expenditure Rp{r['expenditure']} T, "
            f"balance Rp{r['balance']} T; {len(months)} months, {read} decks read", "warnings": warnings}
