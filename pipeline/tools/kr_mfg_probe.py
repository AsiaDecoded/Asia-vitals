"""Korea Manufacturing tab: source probe (5 Nov 2026, Korea chat).

Run from GitHub Actions (agency sites block the Claude sandbox):
  python -I pipeline/tools/kr_mfg_probe.py discovery/kr_mfg

1. ECOS table list, filtered for production, shipments, inventories, capacity, operating ratio, semiconductors,
   special classifications; item lists of the matches and of 200Y101 / 200Y102.
2. ECOS 901Y032 sample values (production, shipments, inventories) for manufacturing and semiconductors if listed.
3. Statistics Korea's monthly industrial activity release (산업활동동향, Sep 2026, via KDI EIEC and the
   agency's board): PDF, text of every page, and the pages that print weights (가중치).
Saves everything plus summary.txt under the output folder.
"""
import json
import re
import sys
import traceback
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import ecos  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "discovery/kr_mfg")
OUT.mkdir(parents=True, exist_ok=True)
LOG = []
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
KEYS = ["가동", "생산능력", "반도체", "재별", "출하", "재고", "제조업", "광공업", "생산지수", "ICT", "국내공급", "산업활동"]


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.append(s)


def save(name, data):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    elif isinstance(data, bytes):
        p.write_bytes(data)
    else:
        p.write_text(str(data))


def fetch(url, timeout=90):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read(), r.headers.get("Content-Type", "")


def step(fn):
    say(f"\n===== {fn.__name__}")
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        say(f"  FAILED {type(e).__name__}: {str(e)[:300]}")
        save(f"{fn.__name__}_error.txt", traceback.format_exc())


def tables():
    rows = ecos._paged("StatisticTableList", [])
    save("ecos_tables.json", rows)
    say(f"  {len(rows)} tables")
    hits = [r for r in rows if any(k in (r.get("STAT_NAME") or "") for k in KEYS)]
    save("ecos_tables_hits.json", hits)
    codes = []
    for r in hits:
        say(f"  {r.get('STAT_CODE')} | {r.get('STAT_NAME')} | {r.get('CYCLE')} | srch={r.get('SRCH_YN')} | {r.get('ORG_NAME')}")
        if r.get("SRCH_YN") == "Y":
            codes.append(r["STAT_CODE"])
    for c in sorted(set(codes) | {"200Y101", "200Y102"}):
        try:
            its = ecos.items(c)
            save(f"items_{c}.json", its)
            seen = []
            for it in its:
                k = (it.get("GRP_NAME"), it.get("ITEM_CODE"), it.get("ITEM_NAME"))
                if k not in seen:
                    seen.append(k)
            say(f"  -- {c}: {len(its)} item rows; " + "; ".join(f"{g}:{i} {n}" for g, i, n in seen[:60]))
        except Exception as e:  # noqa: BLE001
            say(f"  -- {c}: {e!r}"[:300])


def samples():
    for grp in ("1", "3", "5"):
        rs = ecos._paged("StatisticSearch", ["901Y032", "M", "202601", "202612", "I11AC", grp])
        save(f"sample_901Y032_I11AC_{grp}.json", rs)
        say(f"  901Y032 I11AC grp {grp}: " + ", ".join(f"{r['TIME']}={r['DATA_VALUE']}" for r in rs))


def release():
    pages = ["https://eiec.kdi.re.kr/policy/materialView.do?num=288806"]
    pdfs = []
    for u in pages:
        html, _ = fetch(u)
        html = html.decode("utf-8", "replace")
        save("eiec_page.html", html)
        for h in re.findall(r"""(?:href|onclick)=["']([^"']*callDownload[^"']*)["']""", html):
            pdfs.append(urllib.parse.urljoin(u, h.replace("&amp;", "&")))
        for m in re.findall(r"callDownload\.do\?[^\"'\s<>]+", html):
            pdfs.append(urllib.parse.urljoin(u, m.replace("&amp;", "&")))
    pdfs = list(dict.fromkeys(pdfs))
    say(f"  links: {pdfs}")
    for i, u in enumerate(pdfs[:3]):
        try:
            b, ct = fetch(u, 180)
            say(f"  {u}: {len(b)} bytes, {ct}, starts {b[:5]!r}")
            if b[:4] == b"%PDF":
                save(f"release_{i}.pdf", b)
                extract(OUT / f"release_{i}.pdf", i)
        except Exception as e:  # noqa: BLE001
            say(f"  {u}: {e!r}"[:300])


def extract(path, i):
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        allt = []
        for n, p in enumerate(pdf.pages, 1):
            t = p.extract_text() or ""
            allt.append(f"\n\n##### page {n}\n{t}")
            if "가중치" in t:
                say(f"  page {n} prints 가중치")
                save(f"weights_p{n:03d}.txt", t)
                try:
                    save(f"weights_p{n:03d}_tables.json", p.extract_tables())
                except Exception as e:  # noqa: BLE001
                    say(f"  tables p{n}: {e!r}")
        save(f"release_{i}.txt", "".join(allt))
        say(f"  {len(pdf.pages)} pages")


CODES = ["I11A", "I11AA", "I11AB", "I11AC", "I11AD"] + [f"I11AC{c}" for c in "ABCDEFGHIJKLMNOPQRSTUVWX"]


def series2():
    """Round 2: every 901Y032 production index, monthly 2019-, plus use-based, operating ratio, inventory ratio."""
    out = {}
    for c in CODES:
        rs = ecos._paged("StatisticSearch", ["901Y032", "M", "201901", "203012", c, "1"])
        out[c] = {r["TIME"]: r["DATA_VALUE"] for r in rs}
    save("r2_901Y032_prod.json", out)
    say(f"  901Y032 production: {len(out)} items, " + ", ".join(f"{k}:{len(v)}" for k, v in out.items()))
    extra = {}
    for t, c, g in [("901Y034", "I31AA", "I10A"), ("901Y034", "I31AC", "I10A"), ("901Y035", "I32A", "I11B"),
                    ("901Y035", "I32AO1", "I11B"), ("901Y035", "I32A", "I11A"), ("901Y025", "I31A", None),
                    ("901Y026", "I33A", None)]:
        args = [t, "M", "202501", "203012", c] + ([g] if g else [])
        try:
            rs = ecos._paged("StatisticSearch", args)
            extra[f"{t}_{c}_{g}"] = [(r["TIME"], r["DATA_VALUE"], r.get("UNIT_NAME"), r.get("ITEM_NAME2")) for r in rs]
            say(f"  {t} {c} {g}: " + ", ".join(f"{r['TIME']}={r['DATA_VALUE']}" for r in rs[-4:]) + f" unit {rs[-1].get('UNIT_NAME') if rs else ''}")
        except Exception as e:  # noqa: BLE001
            say(f"  {t} {c} {g}: {e!r}"[:300])
    save("r2_extra.json", extra)


def archive():
    """Round 2: earlier monthly releases on KDI EIEC (for each year's weights)."""
    for q in ["산업활동동향", "1월 산업활동동향"]:
        for pg in (1, 2, 3, 4, 5):
            u = ("https://eiec.kdi.re.kr/policy/materialList.do?pp=50&pg=%d&search_txt=" % pg) + urllib.parse.quote(q)
            try:
                html, _ = fetch(u)
                html = html.decode("utf-8", "replace")
                save(f"r2_eiec_list_{q[:2]}_{pg}.html", html)
                hits = re.findall(r"materialView\.do\?num=(\d+)[^>]*>\s*([^<]*산업활동동향[^<]*)<", html)
                say(f"  {u}: {len(hits)} hits: " + "; ".join(f"{n} {t.strip()}" for n, t in hits[:50]))
            except Exception as e:  # noqa: BLE001
                say(f"  {u}: {e!r}"[:300])


def weights_years():
    """Fetch releases listed in r2_nums.txt (num per year) and keep page text that prints 가중치."""
    f = Path(__file__).with_name("kr_mfg_probe_nums.txt")
    if not f.exists():
        return
    for line in f.read_text().split():
        num = line.strip()
        u = f"https://eiec.kdi.re.kr/policy/materialView.do?num={num}"
        html, _ = fetch(u)
        html = html.decode("utf-8", "replace")
        ls = [urllib.parse.urljoin(u, m.replace("&amp;", "&")) for m in re.findall(r"callDownload\.do\?[^\"'\s<>]+", html)]
        for i, l in enumerate(ls[:2]):
            b, _ = fetch(l, 180)
            if b[:4] != b"%PDF":
                continue
            p = OUT / f"r2_rel_{num}_{i}.pdf"
            p.write_bytes(b)
            import pdfplumber
            with pdfplumber.open(p) as pdf:
                for n, pg in enumerate(pdf.pages, 1):
                    t = pg.extract_text() or ""
                    if "업종별 생산" in t and "가중치" in t:
                        save(f"r2_w_{num}_p{n:03d}.txt", t)
                        say(f"  {num}: weights on page {n}: " + t[:120].replace(chr(10), " "))
            p.unlink()


ROUND = sys.argv[2] if len(sys.argv) > 2 else "1"
for fn in ((tables, samples, release) if ROUND == "1" else (series2, archive, weights_years)):
    step(fn)
say(f"\nECOS key: {'sample' if ecos.KEY == 'sample' else 'secret'}; calls {ecos.CALLS['n']}")
save("summary.txt", "\n".join(LOG))
