"""Asia Manufacturing tab: access probe for manufacturing GVA and production-index sources (4 Nov 2026).

Run from GitHub Actions (the agencies block the Claude sandbox):
  python -I pipeline/tools/mfg_probe.py discovery/mfg

Each economy is probed on its own; a failure is logged and the rest continue. Saves raw responses and
summary.txt (what was reachable, table ids, industries, periods) under the output folder.
"""
import csv
import io
import json
import re
import sys
import traceback
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "discovery/mfg")
OUT.mkdir(parents=True, exist_ok=True)
LOG = []
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.append(s)


def save(name, data):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1)[:5_000_000])
    elif isinstance(data, bytes):
        p.write_bytes(data)
    else:
        p.write_text(str(data))


def fetch(url, timeout=90, ctx=None):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()


def links(html, base, pat):
    out = []
    for h in re.findall(r'href="([^"]+)"', html):
        if re.search(pat, h, re.I):
            out.append(urllib.request.urljoin(base, h))
    return list(dict.fromkeys(out))


def probe(name):
    def deco(fn):
        def run():
            say(f"\n===== {name}")
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                say(f"  FAILED {type(e).__name__}: {str(e)[:300]}")
                save(f"{name}_error.txt", traceback.format_exc())
        PROBES.append(run)
        return fn
    return deco


PROBES = []


def page_and_files(tag, url, pat, n=12):
    html = fetch(url).decode("utf-8", "replace")
    save(f"{tag}/page.html", html)
    ls = links(html, url, pat)
    say(f"  {url}: {len(ls)} links matching {pat}")
    for u in ls[:n]:
        try:
            b = fetch(u)
            save(f"{tag}/" + re.sub(r"[^A-Za-z0-9._-]", "_", u.split("/")[-1])[:120], b)
            say(f"    ok {u} {len(b)}")
        except Exception as e:  # noqa: BLE001
            say(f"    failed {u} {e}")
    return ls


@probe("JP")
def jp():
    page_and_files("jp/meti", "https://www.meti.go.jp/statistics/tyo/iip/b2020_result-2.html", r"\.(csv|xlsx?)$", 20)
    page_and_files("jp/esri_qna", "https://www.esri.cao.go.jp/jp/sna/data/data_list/seisanqna/index.html", r"\.(csv|xlsx?)$", 10)
    try:
        from core import estat
        d = estat._call("getStatsList", {"statsCode": "00550300", "limit": 200})
        save("jp/estat_statslist.json", d)
        tl = (((d.get("GET_STATS_LIST") or {}).get("DATALIST_INF") or {}).get("TABLE_INF")) or []
        tl = tl if isinstance(tl, list) else [tl]
        say(f"  e-Stat IIP tables: {len(tl)}")
        for t in tl[:40]:
            title = t.get("TITLE")
            title = title.get("$") if isinstance(title, dict) else title
            say(f"    {t.get('@id')} {title} {t.get('SURVEY_DATE')}")
    except Exception as e:  # noqa: BLE001
        say(f"  e-Stat failed {e}")


@probe("KR")
def kr():
    from core import ecos
    say(f"  ECOS key: {'own' if ecos.KEY != 'sample' else 'sample (10 rows per call)'}")
    for t in ("901Y032", "901Y033", "200Y104", "200Y106", "200Y102", "200Y123", "200Y105", "200Y108"):
        try:
            it = ecos.items(t)
            save(f"kr/items_{t}.json", it)
            names = sorted({(r.get("ITEM_CODE"), r.get("ITEM_NAME"), r.get("CYCLE"), r.get("START_TIME"), r.get("END_TIME"))
                            for r in it}, key=str)
            say(f"  {t}: {len(it)} items; {it[0].get('STAT_NAME') if it else ''}")
            for n in names[:60]:
                say(f"    {n}")
        except Exception as e:  # noqa: BLE001
            say(f"  {t} failed {e}")


@probe("TW")
def tw():
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE   # probe only: ws.dgbas.gov.tw sends an incomplete chain (see core/dgbas.py)
    for u in ["https://ws.dgbas.gov.tw/001/Upload/463/relfile/10315/2711/%E7%94%9F%E7%94%A2%E5%B8%B3_%E5%AD%A3_%E5%B0%8D%E5%A4%96%E7%99%BC%E5%B8%83%E7%89%88%28060a%29.xlsx",
              "https://ws.dgbas.gov.tw/001/Upload/463/relfile/10315/2711/%E7%94%9F%E7%94%A2%E5%B8%B3_%E5%B9%B4_%E5%B0%8D%E5%A4%96%E7%99%BC%E5%B8%83%E7%89%88%28056%29.xlsx"]:
        try:
            b = fetch(u, ctx=ctx)
            save("tw/" + ("gdp_q.xlsx" if "%E5%AD%A3" in u else "gdp_a.xlsx"), b)
            say(f"  ok DGBAS GDP by industry {len(b)}")
        except Exception as e:  # noqa: BLE001
            say(f"  failed {u[:80]} {e}")
    for ds in ("146531", "67171"):
        try:
            d = json.loads(fetch(f"https://data.gov.tw/api/v2/rest/dataset/{ds}"))
            save(f"tw/datagov_{ds}.json", d)
            res = (d.get("result") or {}).get("distribution") or []
            say(f"  data.gov.tw {ds}: {(d.get('result') or {}).get('title')} {len(res)} files")
            for r in res[:4]:
                u = r.get("resourceDownloadUrl")
                say(f"    {r.get('resourceDescription')} {r.get('resourceFormat')} {u}")
                try:
                    b = fetch(u)
                    save(f"tw/datagov_{ds}_" + re.sub(r"[^A-Za-z0-9._-]", "_", u.split("/")[-1])[:60], b)
                    say(f"      ok {len(b)}")
                except Exception as e:  # noqa: BLE001
                    say(f"      failed {e}")
        except Exception as e:  # noqa: BLE001
            say(f"  data.gov.tw {ds} failed {e}")
    try:
        b = fetch("https://dmz26.moea.gov.tw/GMWeb/investigate/InvestigateDA.aspx")
        save("tw/moea_gmweb.html", b)
        say(f"  MOEA GMWeb page ok {len(b)}")
    except Exception as e:  # noqa: BLE001
        say(f"  MOEA GMWeb failed {e}")


@probe("CN")
def cn():
    from core import nbs
    found = []
    for code in ("1", "2", "3"):
        roots = nbs.tree(code)
        save(f"cn/tree_{code}.json", roots)
        say(f"  tree {code}: {[r.get('_name') or r.get('name') for r in roots][:20]}")
        queue = [(r["_id"], r.get("_name") or r.get("name") or "") for r in roots]
        n = 0
        while queue and n < 120:
            pid, path = queue.pop(0)
            if not re.search(r"工业|国内生产总值|GDP|季度|月度|年度", path):
                continue
            n += 1
            for c in nbs.tree(code, pid):
                nm = (c.get("_name") or c.get("name") or "").strip()
                p = f"{path} > {nm}"
                if c.get("isLeaf"):
                    if re.search(r"工业|增加值|国内生产总值", p):
                        found.append({"tree": code, "cid": c["_id"], "path": p, "sdate": c.get("sdate"), "edate": c.get("edate")})
                else:
                    queue.append((c["_id"], p))
    save("cn/catalogs.json", found)
    say(f"  catalogs matching industry/GDP: {len(found)}")
    for f in found[:60]:
        say(f"    {f['tree']} {f['cid']} {f['path']} {f['sdate']}-{f['edate']}")
    for f in found[:25]:
        try:
            ind = nbs.indicators(f["cid"])
            save(f"cn/ind_{f['cid']}.json", ind)
            say(f"    {f['path']}: {len(ind)} indicators, e.g. {[i.get('i_showname') for i in ind[:6]]}")
        except Exception as e:  # noqa: BLE001
            say(f"    indicators {f['cid']} failed {e}")


@probe("HK")
def hk():
    from core import censtatd
    for tid in ("610-65001", "310-34501", "310-34101", "310-34201"):
        try:
            h, rows = censtatd.table(tid)
            save(f"hk/{tid}.json", {"header": h, "rows": rows[:20000]})
            keys = [k for k in (rows[0] if rows else {}) if k.endswith("Desc")]
            cats = {k: sorted({r.get(k) for r in rows})[:40] for k in keys}
            per = sorted({r.get("period") for r in rows})
            say(f"  {tid}: {h.get('title') if isinstance(h, dict) else ''} rows {len(rows)} periods {per[:1]}..{per[-1:]}")
            for k, v in cats.items():
                say(f"    {k}: {v}")
        except Exception as e:  # noqa: BLE001
            say(f"  {tid} failed {e}")


@probe("SG")
def sg():
    from core import singstat
    seen = {}
    for kw in ("industrial production", "index of industrial production", "manufacturing", "gross domestic product at current prices",
               "gross domestic product in chained", "value added manufacturing"):
        try:
            recs = singstat.search(kw)
            for r in recs:
                seen[r.get("id")] = r.get("title")
        except Exception as e:  # noqa: BLE001
            say(f"  search {kw} failed {e}")
    save("sg/search.json", seen)
    say(f"  tables found: {len(seen)}")
    for k, v in sorted(seen.items()):
        if re.search(r"industrial production|manufactur|gross domestic product|value added", v or "", re.I):
            say(f"    {k} {v}")
    for tid in ("M355381", "M015661", "M015651"):
        try:
            m = singstat.metadata(tid)
            save(f"sg/meta_{tid}.json", m)
            say(f"  {tid}: {m.get('title')} {m.get('frequency')} {m.get('startPeriod')}-{m.get('endPeriod')}")
            for r in (m.get("row") or [])[:60]:
                say(f"    {r.get('seriesNo')} {r.get('rowText')}")
        except Exception as e:  # noqa: BLE001
            say(f"  {tid} failed {e}")


@probe("MY")
def my():
    from core import dosm
    for path in ("ipi/ipi_2d.csv", "ipi/ipi.csv", "ipi/ipi_1d.csv", "gdp/gdp_qtr_real_supply.csv", "gdp/gdp_qtr_nominal_supply.csv",
                 "gdp/gdp_lookup.csv", "gdp/gdp_qtr_real_supply_sub.csv"):
        try:
            b = dosm.raw_csv(path)
            save("my/" + path.replace("/", "__"), b[:3_000_000])
            rows = dosm.rows(b)
            cols = list(rows[0]) if rows else []
            dates = sorted({r.get("date") for r in rows if r.get("date")})
            say(f"  {path}: {len(rows)} rows, cols {cols}, {dates[:1]}..{dates[-1:]}")
            for c in cols:
                if c not in ("date", "value", "index", "index_sa") and len({r[c] for r in rows}) < 80:
                    say(f"    {c}: {sorted({r[c] for r in rows})}")
        except Exception as e:  # noqa: BLE001
            say(f"  {path} failed {e}")


@probe("ID")
def id_():
    from core import bps
    for vid in (2077, 2084):
        try:
            ys = bps.var_years(vid)
            say(f"  var {vid}: years {sorted(ys)[:1]}..{sorted(ys)[-1:]}")
            meta, rows = bps.var_data(vid, years=set(sorted(ys)[-2:]))
            save(f"id/var_{vid}.json", {"meta": meta, "rows": rows})
            say(f"    {((meta or {}).get('var') or {}).get('label')} unit {((meta or {}).get('var') or {}).get('unit')} last_update {(meta or {}).get('last_update')}")
            say(f"    vervar: {sorted({(r['vervar'], r['vervar_label']) for r in rows})[:40]}")
            say(f"    periods: {sorted({(r['year'], r['turtahun_label']) for r in rows})}")
        except Exception as e:  # noqa: BLE001
            say(f"  var {vid} failed {e}")


@probe("TH_OIE_method")
def th():
    page_and_files("th/oie", "https://www.oie.go.th/view/1/%E0%B8%94%E0%B8%B1%E0%B8%8A%E0%B8%99%E0%B8%B5%E0%B8%AD%E0%B8%B8%E0%B8%95%E0%B8%AA%E0%B8%B2%E0%B8%AB%E0%B8%81%E0%B8%A3%E0%B8%A3%E0%B8%A1/TH-TH",
                   r"(method|metadata|manual|\.pdf$)", 6)


if __name__ == "__main__":
    for run in PROBES:
        run()
    save("summary.txt", "\n".join(LOG))
