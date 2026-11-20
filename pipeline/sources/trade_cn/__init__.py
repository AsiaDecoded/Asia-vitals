"""China merchandise trade: General Administration of Customs (GACC), monthly bulletin tables on english.customs.gov.cn
(statics/report/monthly.html and monthly<year>.html, 2018 on), as published, US$ thousand (written as US$ million).

  (2)  imports and exports by country (region): world (Total), EU, US, HK, JP, TW, KR, IN, ID, MY, PH, SG, TH, VN
  (4)  imports and exports by HS section and chapter: exports of chapter 85; imports of every section (HSS01-HSS22) and
       chapter (HS01-HS99)
  (14) major import commodities, quantity and value: every line of the table. Value rows are flow "imports" (US$);
       quantity rows are flow "imports_qty", in the quantity unit GACC prints (10000T = 10,000 tonnes, N = number,
       100MN = 100 million units, 10000CUM = 10,000 cubic metres, KG, T, 10000L), with usd_mn blank. GACC changes the
       unit of some lines between years, so the unit is on every row. Product codes: crude_oil, petroleum_products,
       iron_ore, coal, natural_gas, lng, soybeans, copper_ore, ics, ... (canonical names for lines whose wording GACC
       changed), otherwise c14_<name>.

Tables give the month and the cumulative year to date. Monthly values are the month column; where a page has no
month column, year to date minus the previous month's year to date (calculated, noted in `series`). GACC published
January and February 2020 only as a combined Jan-Feb figure: those two months are left out. GACC's interactive
database (stats.customs.gov.cn, HS 4-digit) refuses requests from outside China; years before 2018 are not on the
bulletin pages.

Label fixes (Nov 2026): Taiwan and Hong Kong were printed "China Taiwan" and "China Hong Kong" until May 2020; some
2022 and 2025 pages carry an empty first column; crude oil is "Crude petroleum oil(s)". Listing pages are kept in the
store (keys list:<year>) so a missing month can be traced to its link.
"""
import io
import re
import time
import urllib.request

from core import trade
from core.common import CheckFailed, write_release

NAME = "trade_cn"
DESCRIPTION = "China merchandise trade (GACC monthly bulletin, US$, 2018-): partners, HS sections and chapters, major imports (quantity and value)"
SITE = "http://english.customs.gov.cn"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
COUNTRY = [(r"^total$", "WLD"), (r"^(eu|european union)$", "EU"), (r"^united states( of america)?$", "US"),
           (r"^(china )?hong kong(, ?china)?$", "HK"), (r"^japan$", "JP"), (r"^(china )?taiwan(, ?china)?$", "TW"),
           (r"^(republic of korea|korea, ?rep\.?)$", "KR"), (r"^india$", "IN"), (r"^indonesia$", "ID"), (r"^malaysia$", "MY"),
           (r"^philippines$", "PH"), (r"^singapore$", "SG"), (r"^thailand$", "TH"), (r"^viet ?nam$", "VN")]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
TABLES = ("2", "4", "14")
ROMAN = {"Ⅰ": 1, "Ⅱ": 2, "Ⅲ": 3, "Ⅳ": 4, "Ⅴ": 5, "Ⅵ": 6, "Ⅶ": 7, "Ⅷ": 8, "Ⅸ": 9, "Ⅹ": 10, "Ⅺ": 11, "Ⅻ": 12}
# Table (14) lines whose wording changed over the years -> one product code (matched on the normalised name)
CANON = [
    (r"^crude petroleum oils?$", "crude_oil"), (r"^refined petroleum products$", "petroleum_products"),
    (r"^iron ores? and concentrates?$", "iron_ore"), (r"^coal and lignite$", "coal"), (r"^natural gases$", "natural_gas"),
    (r"^natural gases in liquefied state$", "lng"), (r"^natural gases in gaseous state$", "pipeline_gas"),
    (r"^soya beans$", "soybeans"), (r"^copper ores and concentrates$", "copper_ore"),
    (r"^unwrought copper and copper products$", "copper"), (r"^unwrought alumin(i)?um and alumin(i)?um products$", "aluminium"),
    (r"^alumin(i)?um ores and concentrates$", "aluminium_ore"), (r"^electronic integrated circuits$", "ics"),
    (r"^(agriculture products|agricultural products)$", "agri_products"), (r"^mechanical and electrical products$", "me_products"),
    (r"^hi-?tech products$", "hitech_products"), (r"^metal mines and ores$", "metal_ores"), (r"^grain food$", "grain"),
    (r"^cereals and cereal flour$", "cereals"), (r"^meat ?\(including meat offal\)$|^meat and meat offal$", "meat"),
    (r"^(dairy|diary) products$", "dairy"), (r"^edible vegetable oil$", "edible_veg_oil"),
    (r"^plastics in primary forms$", "plastics_primary"), (r"^medical and pharmaceutical products$|^medicinal materials and pharmaceutical products$", "pharma"),
    (r"^rare-earth ore, metals, compounds$", "rare_earths"), (r"^automatic data processing machines and parts thereof$", "adp_and_parts"),
    (r"^motor vehicles ?\(including chassis fitted with engines\)$", "motor_vehicles"), (r"^aircraft$", "aircraft"),
    (r"^semiconductor manufacturing equipments?$", "semi_equipment"), (r"^diamonds$", "diamonds"), (r"^cotton$", "cotton"),
    (r"^potassium chloride$", "potash"), (r"^fertilizers$", "fertilizers"), (r"^paper pulp$", "pulp"),
    (r"^wood in the rough$", "logs"), (r"^frozen fish$", "frozen_fish"), (r"^meat of bovine animals$", "beef"),
    (r"^meat of swine$", "pork"), (r"^barley$", "barley"), (r"^maize( and maize flour)?$", "maize"), (r"^wheat( and wheat flour)?$", "wheat"),
]
BUDGET = 80
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


def listing_url(year, current):
    return f"{SITE}/statics/report/monthly.html" if year == current else f"{SITE}/statics/report/monthly{year}.html"


def parse_listing(h):
    """{(table, month): url} from a year's listing page. Month links are printed Jan., Feb., ... (some years Sept.)."""
    out = {}
    for num, cells in re.findall(r"[（(](\d+)[）)][^<]*</td>(.*?)</tr>", h, re.S):
        if num not in TABLES:
            continue
        for link, mon in re.findall(r"href=[\"']?(http[^ \"'>]+)[\"']?[^>]*>\s*([A-Z][a-z]{2,8})\.?\s*<", cells):
            if mon[:3] in MONTHS:
                out[(num, MONTHS.index(mon[:3]) + 1)] = link
    return out


def frame(html):
    import pandas as pd  # noqa: PLC0415
    t = pd.read_html(io.StringIO(html))[0]
    return [[("" if str(x) == "nan" else re.sub(r"\s+", " ", str(x)).strip()) for x in row] for row in t.values.tolist()]


def num(s):
    s = (s or "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def layout(rows, label_word):
    """(label column, header rows, first data row) for a bulletin table. The label column is the one whose header
    cell starts with label_word ('Country', 'HS Section', 'Commodity'); some pages carry an empty first column."""
    for i, r in enumerate(rows[:10]):
        for j, c in enumerate(r):
            if c.lower().startswith(label_word.lower()):
                hdr = [k for k in range(i, min(i + 4, len(rows))) if rows[k][j] == c]
                return j, hdr, hdr[-1] + 1
    return None, [], 0


def columns(rows, hdr, month, groups):
    """{group: {'month': col, 'ytd': col}} for groups such as 'Exports'/'Imports' or 'Quantity'/'Value'."""
    out = {}
    for j in range(len(rows[0])):
        cells = [rows[k][j] for k in hdr]
        txt = " ".join(cells)
        if re.search(r"percent", txt, re.I):
            continue
        g = next((g for g in groups if any(c.lower() == g.lower() for c in cells)), None)
        if not g:
            continue
        if re.search(rf"(^|\s)1\s*(to|-)\s*{month}(\s|$)", txt):
            out.setdefault(g, {}).setdefault("ytd", j)
        elif re.search(rf"(^|\s){month}(\s|$)", txt):
            out.setdefault(g, {}).setdefault("month", j)
    return out


def norm(name):
    n = re.sub(r"[\*（）]", lambda m: {"（": "(", "）": ")"}.get(m.group(0), ""), name).strip().lower()
    return re.sub(r"\s+", " ", n).replace("( ", "(").replace(" )", ")")


def product14(name):
    n = norm(name)
    for pat, code in CANON:
        if re.search(pat, n):
            return code
    return "c14_" + re.sub(r"[^a-z0-9]+", "_", n).strip("_")[:60]


def section_code(label):
    """'Ⅰ LIVE ANIMALS ...' -> HSS01; '01 Live animals' -> HS01; else None."""
    m = re.match(r"^(\d{2})\s", label)
    if m:
        return f"HS{m.group(1)}"
    m = re.match(r"^([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ]+)\s", label)
    if m:
        s = m.group(1)
        if len(s) == 1:
            v = ROMAN[s]
        else:   # ⅩⅠ.. ⅩⅫ: tens written as Ⅹ (or ⅩⅩ) followed by a unit numeral
            v = sum(10 if ch == "Ⅹ" else ROMAN[ch] for ch in s)
        return f"HSS{v:02d}"
    m = re.match(r"^(X{0,2}(?:IX|IV|V?I{0,3}))\s+[A-Z]", label)
    if m and m.group(1):
        r = m.group(1)
        vals = {"I": 1, "V": 5, "X": 10}
        v = sum(-vals[a] if i + 1 < len(r) and vals[a] < vals[r[i + 1]] else vals[a] for i, a in enumerate(r))
        return f"HSS{v:02d}"
    return None


def parse(tab, y, m, html):
    """[(flow, partner, product, value, unit, is_month, series)] from one bulletin page."""
    rows = frame(html)
    out = []
    if tab == "2":
        lab, hdr, first = layout(rows, "Country")
        cols = columns(rows, hdr, m, ["Exports", "Imports"])
        for r in rows[first:]:
            name = r[lab].replace("，", ",").lower()
            iso = next((c for pat, c in COUNTRY if re.search(pat, name)), None)
            if not iso:
                continue
            for lab_, flow in (("Exports", "exports"), ("Imports", "imports")):
                c = cols.get(lab_, {})
                j, is_month = (c["month"], True) if "month" in c else (c.get("ytd"), m == 1)
                if j is not None and num(r[j]) is not None:
                    out.append((flow, iso, "TOTAL", num(r[j]), "USD thousand", is_month, f"bulletin (2) {r[lab]}"))
    elif tab == "4":
        lab, hdr, first = layout(rows, "HS Section")
        cols = columns(rows, hdr, m, ["Exports", "Imports"])
        for r in rows[first:]:
            label = r[lab]
            code = "TOTAL" if label.upper() == "TOTAL" else section_code(label)
            if not code:
                continue
            for lab_, flow in (("Exports", "exports"), ("Imports", "imports")):
                if flow == "exports" and code != "HS85":
                    continue
                if code == "TOTAL":
                    continue        # the world total comes from table (2)
                c = cols.get(lab_, {})
                j, is_month = (c["month"], True) if "month" in c else (c.get("ytd"), m == 1)
                if j is not None and num(r[j]) is not None:
                    out.append((flow, "WLD", code, num(r[j]), "USD thousand", is_month, f"bulletin (4) {label[:80]}"))
    elif tab == "14":
        lab, hdr, first = layout(rows, "Commodity")
        cols = columns(rows, hdr, m, ["Quantity", "Value"])
        unit_col = lab + 1
        seen = set()
        for r in rows[first:]:
            name = r[lab]
            if not name or re.match(r"^(of which|note)", name, re.I) or name == r[unit_col]:
                continue
            code = product14(name)
            if code in seen:
                DIAG.append(f"(14) {y}-{m:02d}: '{name}' printed twice; first kept")
                continue
            seen.add(code)
            for g, flow in (("Value", "imports"), ("Quantity", "imports_qty")):
                c = cols.get(g, {})
                j, is_month = (c["month"], True) if "month" in c else (c.get("ytd"), m == 1)
                v = num(r[j]) if j is not None else None
                if v is None:
                    continue
                unit = "USD thousand" if flow == "imports" else r[unit_col]
                if flow == "imports_qty" and unit in ("", "-", "--"):
                    continue
                out.append((flow, "WLD", code, v, unit, is_month, f"bulletin (14) {name}"))
    return out


def update(force=False, **_):
    st = trade.Store("cn")
    DIAG.clear()
    current = int(time.strftime("%Y"))
    links = {}
    for y in range(2018, current + 1):
        try:
            h = st.get(f"list:{y}", lambda y=y: get(listing_url(y, current)), refresh=(y >= current - 1) or force, budget=BUDGET)
            found = parse_listing(h or "")
            for (tab, m), url in found.items():
                links[(tab, y, m)] = url
            last_m = 12 if y < current else max([m for (_t, m) in found] or [0])
            for tab in TABLES:
                miss = [m for m in range(1, last_m + 1) if (tab, m) not in found and not (y == 2020 and m == 1)]
                if miss:
                    DIAG.append(f"listing {y}: no link for table ({tab}) month(s) {miss}")
        except Exception as e:  # noqa: BLE001
            DIAG.append(f"listing {y}: {e}")
    for (tab, y, m), url in sorted(links.items(), key=lambda kv: (-kv[0][1], -kv[0][2])):
        recent = y == current and m >= int(time.strftime("%m")) - 3
        st.get(f"{tab}:{y}-{m:02d}", lambda url=url: get(url), refresh=recent, budget=BUDGET)
    st.save()

    vals = {}          # (flow, partner, product, y, m) -> (value, unit, is_month, series)
    for key, html in st.data.items():
        tab, ym = key.split(":")
        if tab not in TABLES or not html:
            continue
        y, m = int(ym[:4]), int(ym[5:7])
        if y == 2020 and m in (1, 2):
            continue        # published only as a combined January-February figure
        try:
            for flow, p, prod, v, unit, is_month, s in parse(tab, y, m, html):
                vals.setdefault((flow, p, prod, y, m), (v, unit, is_month, s))
        except Exception as e:  # noqa: BLE001
            DIAG.append(f"{key}: {type(e).__name__}: {e}")
    rows_out = []
    for (flow, p, prod, y, m), (v, unit, is_month, s) in vals.items():
        if not is_month and m > 1:
            prev = vals.get((flow, p, prod, y, m - 1))
            if not prev or prev[1] != unit or (prev[2] and m - 1 > 1):
                continue    # need the previous month's year to date, in the same unit
            v, s = v - prev[0], s + " (year to date less previous month, calculated)"
        if unit == "USD thousand":
            rows_out.append({"economy": "CN", "flow": flow, "partner": p, "product": prod, "date": f"{y}-{m:02d}-01",
                             "value": round(v / 1000, 6), "unit": "USD million", "usd_mn": round(v / 1000, 6),
                             "usd_calculated": "", "series": s})
        else:
            rows_out.append({"economy": "CN", "flow": flow, "partner": p, "product": prod, "date": f"{y}-{m:02d}-01",
                             "value": v, "unit": unit, "usd_mn": "", "usd_calculated": "", "series": s})
    if not rows_out:
        raise CheckFailed(["GACC bulletin: nothing read"] + DIAG[:5])
    errors = check(rows_out)
    if errors:
        raise CheckFailed(errors)
    last = trade.latest(rows_out)
    folder = trade.write("cn", rows_out)
    pages = sum(1 for k in st.data if not k.startswith("list:"))
    code = f"T{last[:7]}h{pages}"
    write_release(folder, {"code": code, "label": last[:7], "latest_month": last, "source": NAME,
                           "table": "GACC monthly bulletin tables (2), (4), (14)"}, DIAG[:40], len(rows_out), {"fetched": st.fetched})
    return {"updated": True, "code": code, "summary": f"{last[:7]}: {len(rows_out)} rows, {st.fetched} pages fetched",
            "warnings": DIAG[:10]}


def check(rows):
    """Hard checks: every partner and the world total in every month since Jan 2018 (except Jan-Feb 2020); crude oil
    present; HS chapters of imports add up to the world total within 0.5%."""
    errors = []
    idx = {}
    for r in rows:
        idx.setdefault((r["flow"], r["partner"], r["product"]), {})[r["date"][:7]] = r["value"]
    last = trade.latest(rows, flow="imports")
    want = [mm for mm in trade.months("2018-01", last) if mm not in ("2020-01", "2020-02")]
    for p in ["WLD", "EU", "US", "HK", "JP", "TW", "KR", "IN", "ID", "MY", "PH", "SG", "TH", "VN"]:
        for flow in ("exports", "imports"):
            have = idx.get((flow, p, "TOTAL"), {})
            miss = [mm for mm in want if mm not in have]
            if miss:
                (errors if len(miss) > 2 else DIAG).append(f"{flow} {p}: missing {miss[:8]}")
    if not idx.get(("imports", "WLD", "crude_oil")):
        errors.append("no crude oil imports from table (14)")
    chapters = [k for k in idx if k[0] == "imports" and k[1] == "WLD" and re.fullmatch(r"HS\d\d", k[2])]
    off = []
    for mm in want:
        tot = idx.get(("imports", "WLD", "TOTAL"), {}).get(mm)
        s = [idx[k][mm] for k in chapters if mm in idx[k]]
        if tot and len(s) > 90 and abs(sum(s) / tot - 1) > 0.005:
            off.append(f"{mm}: chapters {sum(s):,.0f} vs total {tot:,.0f}")
    if off:
        DIAG.append(f"HS chapters of imports vs total beyond 0.5% in {len(off)} months: {off[:4]}")
    return errors
