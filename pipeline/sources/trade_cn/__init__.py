"""China merchandise trade: General Administration of Customs (GACC), monthly bulletin tables on english.customs.gov.cn
(statics/report/monthly.html and monthly<year>.html, 2018 on), as published, US$ thousand.

  (2)  imports and exports by country (region): world (Total), EU, US, HK, JP, TW, KR, IN, ID, MY, PH, SG, TH, VN
  (4)  imports and exports by HS section and division: exports of chapter 85
  (14) major import commodities in quantity and value: crude oil, refined petroleum products
Tables give the cumulative year to date (and, where shown, the month). Monthly values are taken from the month column
where published, otherwise year to date minus the previous month's year to date (calculated). GACC's interactive
database (stats.customs.gov.cn, HS 4-digit) refuses requests from outside China; earlier years are not on the bulletin
pages.
"""
import io
import re
import time
import urllib.request

from core import trade
from core.common import CheckFailed, read_json, write_release

NAME = "trade_cn"
DESCRIPTION = "China merchandise trade (GACC monthly bulletin, US$, 2018-): totals, partners, HS 85, oil imports"
SITE = "http://english.customs.gov.cn"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
COUNTRY = [(r"^total$", "WLD"), (r"^(eu|european union)$", "EU"), (r"^united states( of america)?$", "US"),
           (r"^hong kong(, ?china)?$", "HK"), (r"^japan$", "JP"), (r"^taiwan(, ?china)?$", "TW"),
           (r"^(republic of korea|korea, ?rep\.?)$", "KR"), (r"^india$", "IN"), (r"^indonesia$", "ID"), (r"^malaysia$", "MY"),
           (r"^philippines$", "PH"), (r"^singapore$", "SG"), (r"^thailand$", "TH"), (r"^viet ?nam$", "VN")]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
BUDGET = 60
DIAG = []


def get(url, tries=4):
    err = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"GACC {url}: {err!r}")


def listing(year, current):
    url = f"{SITE}/statics/report/monthly.html" if year == current else f"{SITE}/statics/report/monthly{year}.html"
    h = get(url)
    out = {}
    for num, cells in re.findall(r"（(\d+)）[^<]*</td>(.*?)</tr>", h, re.S):
        if num not in ("2", "4", "14"):
            continue
        for link, mon in re.findall(r"href=(http[^ >]+)>\s*([A-Z][a-z]{2})\.?\s*<", cells):
            if mon in MONTHS:
                out[(num, MONTHS.index(mon) + 1)] = link
    return out


def frame(html):
    import pandas as pd  # noqa: PLC0415
    t = pd.read_html(io.StringIO(html))[0]
    return [[("" if str(x) == "nan" else str(x).strip()) for x in row] for row in t.values.tolist()]


def num(s):
    s = (s or "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def pick_cols(rows, month, labels):
    """For each label (e.g. 'Exports'), the column of the single month (header == str(month)) if present, else of the
    year to date ('1-m' or '1to m'); returns {label: (col, is_month)}."""
    hdr = rows[:6]
    out = {}
    for lab in labels:
        cands = [j for j in range(len(hdr[0])) if any((r[j] or "").strip().lower() == lab.lower() for r in hdr)]
        best = None
        for j in cands:
            per = " ".join(r[j] for r in hdr[1:])
            if re.search(rf"(^|\s){month}(\s|$)", per) and not re.search(r"\d+\s*-\s*\d+|1to", per):
                best = (j, True) if month != 1 else (j, True)
                break
        if best is None:
            ytd = [j for j in cands if re.search(rf"1\s*-\s*{month}\b|1to{month}\b", " ".join(r[j] for r in hdr[1:]))]
            if ytd:
                best = (ytd[0], False)
            elif cands:
                best = (cands[0], month == 1)
        if best:
            out[lab] = best
    return out


def update(force=False, **_):
    folder = trade.OUT / "cn"
    st = trade.Store("cn")
    DIAG.clear()
    current = int(time.strftime("%Y"))
    links = {}
    for y in range(2018, current + 1):
        try:
            for (tab, m), url in listing(y, current).items():
                links[(tab, y, m)] = url
        except Exception as e:  # noqa: BLE001
            DIAG.append(f"listing {y}: {e}")
    for (tab, y, m), url in sorted(links.items(), key=lambda kv: (-kv[0][1], -kv[0][2])):
        st.get(f"{tab}:{y}-{m:02d}", lambda: get(url), refresh=y == current and m >= int(time.strftime("%m")) - 3, budget=BUDGET)
    st.save()
    vals = {}          # (flow, partner, product, y, m) -> (value, is_month, series)
    for key, html in st.data.items():
        tab, ym = key.split(":")
        y, m = int(ym[:4]), int(ym[5:7])
        try:
            rows = frame(html)
        except Exception as e:  # noqa: BLE001
            DIAG.append(f"{key}: {e}")
            continue
        if tab == "2":
            cols = pick_cols(rows, m, ["Exports", "Imports"])
            for r in rows:
                name = re.sub(r"\s+", " ", (r[0] or "").replace("，", ",")).strip().lower()
                iso = next((c for pat, c in COUNTRY if re.search(pat, name)), None)
                if not iso:
                    continue
                for lab, flow in (("Exports", "exports"), ("Imports", "imports")):
                    if lab in cols and num(r[cols[lab][0]]) is not None:
                        vals.setdefault((flow, iso, "TOTAL", y, m), (num(r[cols[lab][0]]), cols[lab][1], f"bulletin (2) {r[0]}"))
        elif tab == "4":
            cols = pick_cols(rows, m, ["Exports"])
            for r in rows:
                if re.match(r"^85\b", r[0] or "") or re.match(r"^85\b", r[1] if len(r) > 1 else ""):
                    if "Exports" in cols and num(r[cols["Exports"][0]]) is not None:
                        vals.setdefault(("exports", "WLD", "HS85", y, m), (num(r[cols["Exports"][0]]), cols["Exports"][1], "bulletin (4) chapter 85"))
        elif tab == "14":
            vcols = [j for j in range(1, len(rows[0])) if any((rr[j] or "").strip().lower().startswith("value") for rr in rows[:6])]
            for r in rows:
                name = (r[0] or "").lower()
                prod = "crude_oil" if name.startswith("crude oil") else ("petroleum_products" if "refined petroleum" in name else None)
                if prod and vcols and num(r[vcols[0]]) is not None:
                    hdr = " ".join(rr[vcols[0]] for rr in rows[:6])
                    is_month = not re.search(r"1\s*-\s*\d+|1to\d+", hdr) or m == 1
                    vals.setdefault(("imports", "WLD", prod, y, m), (num(r[vcols[0]]), is_month, f"bulletin (14) {r[0]}"))
    rows_out = []
    for (flow, p, prod, y, m), (v, is_month, s) in vals.items():
        if not is_month and m > 1:
            prev = vals.get((flow, p, prod, y, m - 1))
            if not prev or prev[1]:     # need the previous month's year to date too
                continue
            v, s = v - prev[0], s + " (year to date less previous month, calculated)"
        rows_out.append({"economy": "CN", "flow": flow, "partner": p, "product": prod, "date": f"{y}-{m:02d}-01",
                         "value": round(v / 1000, 6), "unit": "USD million", "usd_mn": round(v / 1000, 6),
                         "usd_calculated": "", "series": s})
    if not rows_out:
        raise CheckFailed(["GACC bulletin: nothing read"] + DIAG[:5])
    last = trade.latest(rows_out)
    folder = trade.write("cn", rows_out)
    code = f"T{last[:7]}h{len(st.data)}"
    write_release(folder, {"code": code, "label": last[:7], "latest_month": last, "source": NAME,
                           "table": "GACC monthly bulletin tables (2), (4), (14)"}, DIAG[:20], len(rows_out), {"fetched": st.fetched})
    return {"updated": True, "code": code, "summary": f"{last[:7]}: {len(rows_out)} rows, {st.fetched} pages", "warnings": DIAG[:5]}
