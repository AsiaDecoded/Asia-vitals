"""Vietnam National Statistics Office (NSO, formerly GSO; nso.gov.vn) client and readers.

Three routes, all without a key, all reachable from GitHub Actions (not from the Claude sandbox):
  - WordPress REST API on www.nso.gov.vn (/wp-json/wp/v2): finds each month's CPI release post and its
    Excel attachments, and the socio-economic report tables ("Biểu") with the quarterly price indices.
  - The monthly CPI workbook (Vietnamese, "Số liệu CPI ..."): reference month only, every comparison base.
  - PX-Web (pxweb.nso.gov.vn, the statistical yearbook database, updated once a year): monthly CPI history
    by comparison base and annual producer and trade price indices. The PxWeb API does not serve the price
    database (404), so tables are exported through the web form (all values, PC-Axis format).
gso.gov.vn has no DNS record any more (NXDOMAIN from Actions, 29 Oct 2026).

Comparison bases (NSO's own terms) are kept apart; nothing is converted from one base to another:
  base_period  index, base year = 100 (2019 = 100 to Oct 2025, 2024 = 100 from Nov 2025)
  yoy          same month of the previous year = 100
  prev_dec     December of the previous year = 100
  prev_month   previous month = 100
  qtr_avg      average of the quarter vs the same quarter of the previous year = 100 (quarter-end months)
  ytd_avg      average of the months to date vs the same period of the previous year = 100
Core inflation is published as % changes (y/y, m/m, year-to-date average y/y), not as an index.
"""
import datetime as dt
import hashlib
import html as _html
import http.cookiejar
import io
import itertools
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) asia-vitals/0.1 (+https://github.com/AsiaDecoded/asia-vitals)",
      "Accept": "*/*", "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8"}
WP = "https://www.nso.gov.vn/wp-json/wp/v2"
PXWEB = "https://pxweb.nso.gov.vn/pxweb"
PX_DB = ("en", "E 11. CPI", "E 11. CPI__Px_E_11")
SOURCE = "National Statistics Office of Viet Nam (NSO)"


def _q(url):
    return urllib.parse.quote(url, safe=":/?&=%#+,;@!$'()*~")


def get(url, data=None, headers=None, tries=4, timeout=120, opener=None):
    req = urllib.request.Request(_q(url), data=data, headers={**UA, **(headers or {})})
    last = None
    for i in range(tries):
        try:
            with (opener.open(req, timeout=timeout) if opener else urllib.request.urlopen(req, timeout=timeout)) as r:
                return r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code != 429:
                raise RuntimeError(f"NSO HTTP {e.code} for {url}") from e
            last = e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"NSO unreachable after {tries} tries: {url}: {last}")


def wp(path, **params):
    """One WordPress REST call; returns (json, headers)."""
    url = f"{WP}/{path}?" + urllib.parse.urlencode(params)
    body, hd = get(url)
    return json.loads(body.decode("utf-8-sig")), hd


# ---------------------------------------------------------------- release discovery

CPI_FILE = re.compile(r"(CPI|cpi)", re.I)
VI_HINT = re.compile(r"Bieu|So-lieu|CPI-thang|CPI-T\d|CPI-Thang|CPI-gia-vang|CPI-Ky", re.I)


def cpi_workbooks(after=None, before=None):
    """Vietnamese monthly CPI workbooks attached to the NSO site, oldest first: [{date, url, post}]."""
    out, page = [], 1
    while True:
        params = {"search": "CPI", "per_page": 100, "page": page, "_fields": "id,date,source_url,post,mime_type"}
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        items, hd = wp("media", **params)
        for x in items:
            u = x["source_url"]
            name = u.rsplit("/", 1)[-1]
            if not name.lower().endswith(".xlsx") or "Eng" in name or "_EN" in name or "-EN" in name:
                continue
            if CPI_FILE.search(name) and VI_HINT.search(name):
                out.append({"date": x["date"], "url": u, "post": x.get("post")})
        if page >= int(hd.get("X-WP-TotalPages", hd.get("x-wp-totalpages", 1)) or 1):
            break
        page += 1
    out.sort(key=lambda x: x["date"])
    return out


def report_workbooks(after, before):
    """Socio-economic report tables ('Biểu') uploaded in a date window (quarterly price tables live there).
    Vietnamese workbooks first (latest upload first), English ones after as a fallback."""
    items, _ = wp("media", after=after, before=before, per_page=100, _fields="id,date,source_url,post,mime_type")
    out = []
    for x in items:
        u = x["source_url"]
        name = u.rsplit("/", 1)[-1]
        if name.lower().endswith((".xlsx", ".xls")) and re.search(r"Bieu|So-lieu-\d", name) and \
                not re.search(r"CPI|IIP|Lao-dong|XHKD|KTTG|SCOLI|ksms|KSMS|Chuyen-de|TH\.xlsx", name):
            en = bool(re.search(r"Eng|[-_.]EN[-_.]|_En", name))
            out.append({"date": x["date"], "url": u, "post": x.get("post"), "en": en})
    return sorted(out, key=lambda x: (x["en"], [-ord(c) for c in x["date"]]))


def report_workbooks_search(month, year):
    """Fallback when a quarter's tables were uploaded outside the release window: search by file name."""
    items, _ = wp("media", search=f"Bieu {month}.{year}", per_page=100, _fields="id,date,source_url,post,mime_type")
    out = []
    for x in items:
        name = x["source_url"].rsplit("/", 1)[-1]
        if name.lower().endswith((".xlsx", ".xls")) and re.search(rf"Bieu.*\b{month}[.-]{year}", name):
            out.append({"date": x["date"], "url": x["source_url"], "post": x.get("post"),
                        "en": bool(re.search(r"Eng|[-_.]EN[-_.]|_En", name))})
    return sorted(out, key=lambda x: (x["en"], [-ord(c) for c in x["date"]]))


# ---------------------------------------------------------------- labels

# (series id, English label, Vietnamese row pattern, English PX label patterns)
GROUPS = [
    ("all", "All items", r"^CHỈ SỐ GIÁ TIÊU DÙNG", r"^Consumer price index$"),
    ("food_catering", "Food and catering services", r"^I[\.\s]+Hàng ăn", r"^Food and foodstuffs?$"),
    ("cereals", "Cereals (lương thực)", r"Lương thực", r"^Food$"),
    ("foodstuff", "Foodstuff (thực phẩm)", r"Thực phẩm", r"^Foodstuffs$"),
    ("eating_out", "Eating out", r"Ăn uống ngoài", r"^(Eating out|Meals and drinking out)$"),
    ("beverages_tobacco", "Beverages and tobacco", r"^II[\.\s]+Đồ uống", r"^Beverage\s+and\s+cigarette$"),
    ("clothing", "Garments, hats and footwear", r"^III[\.\s]+May mặc", r"^Garment, hat, footwear$"),
    ("housing", "Housing, electricity, water, fuel and construction materials", r"^IV[\.\s]+Nhà ở",
     r"^Housing(, electricity.*| and construction materials)$"),
    ("household", "Household equipment and goods", r"^V[\.\s]+Thiết bị", r"^Household equipment and goods$"),
    ("health", "Medicine and health care", r"^VI[\.\s]+Thuốc", r"^Medicine and health care services$"),
    ("health_services", "of which: health care services", r"Dịch vụ y tế", r"^(Of|In) which: Health care services$"),
    ("transport_comm", "Transport and communication (to 2009)", r"^$^", r"^Mean of transport & communication$"),
    ("transport", "Transport", r"^VII[\.\s]+Giao thông", r"^Transport$"),
    ("communication", "Information and communication (post and telecommunications before Nov 2025)",
     r"^VIII[\.\s]+(Thông tin|Bưu chính)", r"^(Infomation and Communication|Information and Communication|Post and Communication)$"),
    ("education", "Education", r"^IX[\.\s]+Giáo dục", r"^Education$"),
    ("education_services", "of which: education services", r"Dịch vụ giáo dục", r"^(Of|In) which: Education services$"),
    ("culture", "Culture, entertainment and tourism", r"^X[\.\s]+Văn ho", r"^Culture, entertainments? and tourism$"),
    ("other", "Other goods and services", r"^XI[\.\s]+Hàng hoá|^XI[\.\s]+Hàng hóa", r"^Other consumer goods & services$"),
    ("gold", "Gold price index (not in the CPI)", r"^CHỈ SỐ GIÁ VÀNG", r"^Gold price index$"),
    ("usd", "US dollar price index (not in the CPI)", r"^CHỈ SỐ GIÁ ĐÔ", r"^USD price index$"),
    ("core", "Core inflation (NSO: CPI excl. food and fresh foodstuff, energy and State-managed items incl. "
             "health and education services)", r"^Lạm phát cơ bản", r"^Core inf[i]?lation$"),
]
LABEL = {g[0]: g[1] for g in GROUPS}
ORDER = {g[0]: i for i, g in enumerate(GROUPS)}
CPI_GROUPS = ["food_catering", "beverages_tobacco", "clothing", "housing", "household", "health", "transport",
              "communication", "education", "culture", "other"]


def vi_series(label):
    lab = re.sub(r"\s+", " ", str(label or "")).strip()
    if re.match(r"^Lạm phát cơ bản", lab, re.I):
        return "core"
    for sid, _, vpat, _ in GROUPS:
        if re.search(vpat, lab, re.I if sid in ("cereals", "foodstuff", "eating_out", "health_services",
                                                 "education_services") else 0):
            return sid
    return None


def px_series(label):
    lab = re.sub(r"\s+", " ", str(label or "")).strip()
    for sid, _, _, epat in GROUPS:
        if re.match(epat, lab, re.I):
            return sid
    return None


# ---------------------------------------------------------------- monthly CPI workbook

VI_MONTH = re.compile(r"Tháng\s*(\d{1,2})\s*(?:năm)?\s*(\d{4})", re.I)


def _cell(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _ref_month(rows):
    for row in rows[:8]:
        for c in row:
            if isinstance(c, str) and not re.search(r"so với|SO VỚI", c):
                m = re.search(r"^\s*Tháng\s*(\d{1,2})\s*năm\s*(\d{4})\s*$", c.strip(), re.I)
                if m:
                    return int(m.group(2)), int(m.group(1))
    for row in rows[:8]:
        for c in row:
            if isinstance(c, str):
                m = re.search(r"THÁNG\s*(\d{1,2})\s*NĂM\s*(\d{4})\s*SO VỚI", c, re.I)
                if m:
                    return int(m.group(2)), int(m.group(1))
    return None


def _columns(rows, ref):
    """{column index: [comparison bases]} from the two header rows above the first data row."""
    y, m = ref
    prev = (y, m - 1) if m > 1 else (y - 1, 12)
    first = next(i for i, r in enumerate(rows) if r and isinstance(r[0], str) and vi_series(r[0]) in ("all", "core")
                 and any(_cell(c) is not None for c in r[1:]))
    cols = {}
    for hr in rows[max(0, first - 3):first]:
        for j, c in enumerate(hr):
            if not isinstance(c, str) or j == 0:
                continue
            t = re.sub(r"\s+", " ", c).strip()
            if re.search(r"(CHỈ SỐ GIÁ|LẠM PHÁT CƠ BẢN).*SO VỚI", t, re.I) or t in ("MÃ SỐ", "Mã số"):
                continue
            if re.search(r"[Kk]ỳ gốc", t):
                by = re.search(r"(\d{4})", t)
                cols[j] = [("base_period", int(by.group(1)) if by else None)]
            elif re.search(r"Bình quân quý", t, re.I):
                cols[j] = [("qtr_avg", None)]
            elif re.search(r"Bình quân|\d+\s*tháng.*so với|^Năm \d{4}\s*so với", t, re.I):
                cols[j] = [("ytd_avg", None)]
            else:
                mm = VI_MONTH.search(t)
                if mm:
                    k = (int(mm.group(2)), int(mm.group(1)))
                    bases = []
                    if k == (y - 1, m):
                        bases.append(("yoy", None))
                    if k == (y - 1, 12):
                        bases.append(("prev_dec", None))
                    if k == prev:
                        bases.append(("prev_month", None))
                    if bases:
                        cols.setdefault(j, [])
                        cols[j] = [b for b in cols[j] if b[0] not in [x[0] for x in bases]] + bases
    # December: the y/y column is also the vs-December column, and the YTD column is the annual average
    return first, cols


AREA_TITLES = [("urban", r"THÀNH THỊ"), ("rural", r"NÔNG THÔN"), ("national", r"CẢ NƯỚC")]


def _blocks(rows):
    """Split a sheet into tables ('Biểu n'), each with its area."""
    starts = [i for i, r in enumerate(rows) if r and isinstance(r[0], str) and re.match(r"^\s*Biểu\s*\d", r[0])]
    if not starts:
        starts = [0]
    out = []
    for a, b in zip(starts, starts[1:] + [len(rows)]):
        block = rows[a:b]
        title = " ".join(str(c) for r in block[:6] for c in r if isinstance(c, str))
        area = next((ar for ar, pat in AREA_TITLES if re.search(pat, title, re.I)), "national")
        out.append((area, block))
    return out


def read_cpi_workbook(data):
    """Rows {date, area, series, base, base_year, value} for the reference month of one NSO CPI workbook,
    plus regions and provinces (m/m) and core inflation (rates in %). value is as published (index, or % for core)."""
    import openpyxl  # noqa: PLC0415
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    out, ref, meta = [], None, {"sheets": wb.sheetnames}
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        name = ws.title.strip().lower()
        if not rows:
            continue
        if re.search(r"lạm phát", name):
            r = _ref_month(rows) or ref
            first, cols = _columns(rows, r)
            for j, bases in cols.items():
                v = _cell(rows[first][j]) if j < len(rows[first]) else None
                if v is not None:
                    for b, _ in bases:
                        out.append({"date": f"{r[0]}-{r[1]:02d}-01", "area": "national", "series": "core",
                                    "base": b, "base_year": None, "value": v, "unit": "%"})
            continue
        if re.search(r"vùng|vung|địa phương|dia phuong", name):
            for area_kind, block in _blocks(rows):
                hdr_i = next((i for i, rr in enumerate(block) if rr and any(isinstance(c, str) and
                              re.search(r"Hà Nội|Đồng bằng|Trung du|Hồng", c) for c in rr)), None)
                if hdr_i is None:
                    continue
                r = _ref_month(block) or ref
                names = {j: re.sub(r"\s+", " ", c).strip() for j, c in enumerate(block[hdr_i]) if isinstance(c, str) and j > 0
                         and c.strip() not in ("Mã số",)}
                kind = "region" if re.search(r"vùng|vung", name) else "province"
                for rr in block[hdr_i + 1:]:
                    sid = vi_series(rr[0]) if rr else None
                    if not sid:
                        continue
                    for j, nm in names.items():
                        v = _cell(rr[j]) if j < len(rr) else None
                        if v is not None:
                            out.append({"date": f"{r[0]}-{r[1]:02d}-01", "area": f"{kind}:{nm}", "series": sid,
                                        "base": "prev_month", "base_year": None, "value": v, "unit": "index"})
            continue
        if name in ("00000000", "sheet1"):
            continue
        for area, block in _blocks(rows):
            r = _ref_month(block)
            if not r:
                continue
            ref = ref or r
            try:
                first, cols = _columns(block, r)
            except StopIteration:
                continue
            for rr in block[first:]:
                sid = vi_series(rr[0]) if rr else None
                if not sid:
                    continue
                for j, bases in cols.items():
                    v = _cell(rr[j]) if j < len(rr) else None
                    if v is None:
                        continue
                    for b, by in bases:
                        out.append({"date": f"{r[0]}-{r[1]:02d}-01", "area": area, "series": sid, "base": b,
                                    "base_year": by, "value": v, "unit": "index"})
    meta["ref"] = f"{ref[0]}-{ref[1]:02d}" if ref else None
    return out, meta


# ---------------------------------------------------------------- PX-Web (yearbook database)

def parse_px(b):
    t = b.decode("utf-8") if b[:3] == b"\xef\xbb\xbf" else b.decode("cp1252", "replace")
    i = t.index("DATA=")
    head, data = t[:i], t[i + 5:].replace("\x00", "").strip().rstrip(";")

    def kv(key):
        out = {}
        for m in re.finditer(r"^" + key + r'(?:\("([^"]*)"\))?=(.*?);\s*$', head, re.M | re.S):
            out[m.group(1)] = m.group(2)
        return out

    def lst(s):
        return [x.strip() for x in re.findall(r'"((?:[^"]|"")*)"', s)]
    stub, heading = lst(kv("STUB").get(None, "")), lst(kv("HEADING").get(None, ""))
    vals = {k: lst(v) for k, v in kv("VALUES").items()}
    dims = stub + heading
    tok = re.findall(r'"[^"]*"|[^\s]+', data)
    nums = [None if x.strip('"') in ("", ".", "..", "...", "-", "....") else float(x.strip('"')) for x in tok]
    combos = list(itertools.product(*[vals[d] for d in dims]))
    if len(combos) != len(nums):
        raise ValueError(f"PX cell count {len(nums)} != {len(combos)}")
    meta = {k: (kv(k).get(None) or "").strip().strip('"') for k in ("TITLE", "LAST-UPDATED", "UNITS", "CONTENTS")}
    return meta, dims, [dict(zip(dims, c), value=v) for c, v in zip(combos, nums)]


PX_DB_NA = ("en", "E 03. National Accounts and State budget", "E 03. National Accounts and State budget__Px_E_03")


def px_export(table, fmt="FileTypePX", db=None):
    """Every value of every variable of one PX-Web table, through the web form (the API does not serve it).
    db: (lang, database, folder); default the price database."""
    lang, db, folder = db or PX_DB
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    url = f"{PXWEB}/{lang}/{db}/{folder}/{table}/"
    page = get(url, opener=op)[0].decode("utf-8", "replace")
    fields = []
    for m in re.finditer(r'<input[^>]*type="hidden"[^>]*>', page):
        n, v = re.search(r'name="([^"]+)"', m.group(0)), re.search(r'value="([^"]*)"', m.group(0))
        if n:
            fields.append((_html.unescape(n.group(1)), _html.unescape(v.group(1)) if v else ""))
    for m in re.finditer(r'<select[^>]*name="([^"]+ValuesListBox)"[^>]*>(.*?)</select>', page, re.S):
        for v in re.findall(r'<option[^>]*value="([^"]*)"', m.group(2)):
            fields.append((_html.unescape(m.group(1)), _html.unescape(v)))
    fmt_name = re.search(r'<select[^>]*name="([^"]+OutputFormatDropDownList)"', page).group(1)
    btn = re.search(r'<input[^>]*type="submit"[^>]*name="([^"]+ButtonViewTable)"[^>]*value="([^"]*)"', page)
    fields += [(_html.unescape(fmt_name), fmt), (_html.unescape(btn.group(1)), btn.group(2))]
    body, _ = get(url, data=urllib.parse.urlencode(fields, doseq=True).encode(), opener=op, timeout=240,
                  headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": _q(url)})
    if b"DATA=" not in body[:400000]:
        raise RuntimeError(f"PX-Web {table}: no PC-Axis file returned ({len(body)} bytes)")
    return body


MON_EN = {"jan": 1, "feb": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7,
          "july": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12, "january": 1, "february": 2,
          "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}


def _month(s):
    return MON_EN.get(s.strip().rstrip(".").lower())


# table -> (comparison base, area, base year)
PX_MONTHLY = {"E11.02.px": ("prev_month", "national", None), "E11.03.px": ("prev_month", "urban", None),
              "E11.04.px": ("prev_month", "rural", None), "E11.05.px": ("prev_dec", "national", None),
              "E11.06.px": ("yoy", "national", None), "E11.07.px": ("base_period", "national", 2019)}


def px_monthly_rows(table, body):
    base, area, by = PX_MONTHLY[table]
    meta, dims, rows = parse_px(body)
    ydim = next(d for d in dims if d.lower().startswith("year"))
    mdim = next(d for d in dims if d.lower().startswith("month"))
    idim = next(d for d in dims if d not in (ydim, mdim))
    out, unknown = [], set()
    for r in rows:
        if r["value"] is None:
            continue
        sid = px_series(r[idim])
        if not sid:
            unknown.add(r[idim])
            continue
        mo = _month(r[mdim])
        out.append({"date": f"{int(r[ydim])}-{mo:02d}-01", "area": area, "series": sid, "base": base, "base_year": by,
                    "value": r["value"], "unit": "index"})
    return out, meta, sorted(unknown)


def px_headline_mom(body):
    """E11.01: all-items m/m (previous month = 100) by month, 1995 on."""
    meta, dims, rows = parse_px(body)
    out = []
    for r in rows:
        mo = _month(r["Months"]) if r["Months"] else None
        if mo and r["value"] is not None:
            out.append({"date": f"{int(r['Year'])}-{mo:02d}-01", "area": "national", "series": "all",
                        "base": "prev_month", "base_year": None, "value": r["value"], "unit": "index"})
    return out, meta


def px_annual_rows(table, body, base="prev_year"):
    """Annual tables (previous year = 100 or 2010 = 100): {year, item, value}."""
    meta, dims, rows = parse_px(body)
    ydim = next(d for d in dims if d.lower().startswith("year"))
    idim = next(d for d in dims if d != ydim)
    return [{"year": int(r[ydim]), "item": r[idim], "base": base, "value": r["value"]} for r in rows
            if r["value"] is not None], meta


# ---------------------------------------------------------------- quarterly price tables (socio-economic report)

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4}
QTABLES = [("ppi", r"Chỉ số giá sản xuất(?! công nghiệp)|^\s*\d+\.\s*Producer price"),
           ("input", r"nguyên liệu, nhiên liệu|materials used for production|Input"),
           ("transport", r"giá vận tải|Transport.*price|price.*transport"), ("export", r"giá xuất khẩu|Export price"),
           ("import", r"giá nhập khẩu|Import price"), ("tot", r"Tỷ giá thương mại|[Tt]erms of trade")]
EN_Q = re.compile(r"(\d)(?:st|nd|rd|th)\s+quarter\s+of\s+(\d{4})", re.I)


def _qparse(t):
    m = re.search(r"Quý\s+(I{1,3}V?|IV)\s+năm\s+(\d{4})", t)
    if m:
        return int(m.group(2)), ROMAN[m.group(1)]
    m = EN_Q.search(t)
    return (int(m.group(2)), int(m.group(1))) if m else None
PPI_ROWS = [
    ("agriculture", "Agriculture, forestry and fishing", r"^Nông nghiệp, lâm nghiệp và thủy sản|^Nông, lâm nghiệp và thu[ỷỷ] sản|^Nông, lâm nghiệp và thủy sản|^Agriculture, forestry and fish"),
    ("agri_crops", "Agriculture and related services", r"^Nông nghiệp và dịch vụ|^Agriculture\s*$|^Agriculture and related"),
    ("forestry", "Forestry and related services", r"^Lâm nghiệp|^Forestry"),
    ("fishery", "Fishing and aquaculture", r"^Thủy sản|^Thuỷ sản|^Fisher"),
    ("industry", "Industry", r"^Công nghiệp\s*$|^Industry\s*$"),
    ("mining", "Mining and quarrying", r"^Khai khoáng|^Mining"),
    ("manufacturing", "Manufacturing", r"^Công nghiệp chế biến|^Manufactur"),
    ("electricity", "Electricity, gas, steam and air conditioning", r"^Điện, khí đốt|^Electricity"),
    ("water", "Water supply, sewerage and waste management", r"^Nước tự nhiên|^Cung cấp nước|^Water"),
    ("services", "Services", r"^Dịch vụ\s*$|^Services\s*$"),
    ("svc_transport", "Transport and storage", r"^Vận tải|^Transport"),
    ("svc_accommodation", "Accommodation and food services", r"^Dịch vụ lưu trú|^Accommodation"),
    ("svc_info", "Information and communication", r"^Thông tin và truyền thông|^Information"),
    ("svc_education", "Education and training", r"^Giáo dục|^Education"),
    ("svc_health", "Health and social work", r"^Y tế|^Health"),
    ("svc_arts", "Arts, entertainment and recreation", r"^Nghệ thuật|^Arts"),
]
TRADE_ROWS = [("all", "All items", r"^CHỈ SỐ CHUNG|^GENERAL INDEX|^General index"), ("agri_food", "Agricultural products and food", r"^Nông sản|^Agricultur"),
              ("fuel", "Fuels", r"^Nhiên liệu|^Fuel"), ("manufactured", "Other manufactured goods", r"^Hàng hóa chế biến|^Hàng hoá chế biến|^Other manufactur|^Processed")]
INPUT_ROWS = [("all", "All items", r"^CHỈ SỐ CHUNG|^Chỉ số chung|^GENERAL INDEX|^General index"),
              ("for_agri", "Used for agriculture, forestry and fishing", r"nông nghiệp|agricultur"),
              ("for_manuf", "Used for manufacturing", r"chế biến|manufactur"),
              ("for_constr", "Used for construction", r"xây dựng|construction")]


def _sheets(data, name):
    if name.lower().endswith(".xls"):
        import xlrd  # noqa: PLC0415
        wb = xlrd.open_workbook(file_contents=data)
        for sh in wb.sheets():
            yield sh.name, [sh.row_values(i) for i in range(sh.nrows)]
    else:
        import openpyxl  # noqa: PLC0415
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        for ws in wb.worksheets:
            yield ws.title, [list(r) for r in ws.iter_rows(values_only=True)]


def read_quarter_book(data, name):
    """Quarterly price tables from one socio-economic report workbook (Vietnamese): rows
    {quarter, table, series, base, value} with base yoy (same quarter last year = 100), prev_quarter, ytd_avg."""
    out = []
    for sname, rows in _sheets(data, name):
        title = " ".join(str(c) for r in rows[:2] for c in r if isinstance(c, str))
        kind = next((k for k, pat in QTABLES if re.search(pat, title, re.I)), None)
        if not kind:
            continue
        hdr = " ".join(str(c) for r in rows[:6] for c in r if isinstance(c, str))
        m = re.search(r"(Quý\s+(?:I{1,3}V?|IV)\s+năm\s+\d{4}|\d(?:st|nd|rd|th)\s+quarter\s+of\s+\d{4})\s+(?:so với|versus)", hdr, re.I)
        if not m:
            continue
        y, q = _qparse(m.group(1))
        first = next((i for i, r in enumerate(rows) if r and isinstance(r[0], str) and r[0].strip() and
                      any(isinstance(c, (int, float)) for c in r[1:4])), None)
        if first is None:
            continue
        # column meaning from the header cells: same quarter last year -> yoy; previous quarter -> prev_quarter; rest -> ytd
        cols = {}
        lines = rows[max(0, first - 3):first]
        for j in range(1, 6):
            t = " ".join(str(r[j]) for r in lines if j < len(r) and r[j] not in (None, ""))
            t = re.sub(r"\s+", " ", t)
            k = _qparse(t)
            if k:
                if k == (y - 1, q):
                    cols[j] = "yoy"
                elif k == ((y, q - 1) if q > 1 else (y - 1, 4)):
                    cols[j] = "prev_quarter"
            elif re.search(r"cùng kỳ|năm \d{4}|so với|same period|versus|of \d{4}", t) and j > 1 and j not in cols:
                cols[j] = "ytd_avg"
        if "yoy" not in cols.values():  # Q1 layout: the quarter and year sit on separate header rows
            cols = {1: "yoy", 2: "prev_quarter"}
        table_rows = PPI_ROWS if kind == "ppi" else INPUT_ROWS if kind == "input" else TRADE_ROWS if kind in ("export", "import") else [("all", "All items", r".")]
        seen = set()
        for r in rows[first:]:
            if not r or not isinstance(r[0], str):
                continue
            lab = re.sub(r"\s+", " ", r[0]).strip()
            sid = next((s for s, _, pat in table_rows if re.search(pat, lab, re.I)), None)
            if not sid or sid in seen:
                continue
            seen.add(sid)
            for j, b in cols.items():
                v = _cell(r[j]) if j < len(r) else None
                if v is not None:
                    out.append({"quarter": f"{y}-Q{q}", "table": kind, "series": sid, "base": b, "value": v})
            if kind == "tot":
                break
    return out


# --- GDP by industry (report tables 1 and 2, or the combined Q1 table) and industrial production by VSIC division

GDP_ROWS = [  # (code, ISIC section, English label, level, Vietnamese label pattern)
    ("total", "", "GDP", 0, r"^TỔNG SỐ"),
    ("agri", "A", "Agriculture, forestry and fishing", 1, r"^Nông,? lâm nghiệp và th[uủ]y sản"),
    ("agriculture", "A01", "Agriculture", 2, r"^Nông nghiệp\s*$"),
    ("forestry", "A02", "Forestry", 2, r"^Lâm nghiệp\s*$"),
    ("fishery", "A03", "Fishing and aquaculture", 2, r"^Th[uủ]y sản\s*$"),
    ("ind_constr", "B-F", "Industry and construction", 1, r"^Công nghiệp và xây dựng"),
    ("industry", "B-E", "Industry", 2, r"^Công nghiệp\s*$"),
    ("mining", "B", "Mining and quarrying", 3, r"^Khai khoáng"),
    ("manufacturing", "C", "Manufacturing", 3, r"^Công nghiệp chế biến,? chế tạo"),
    ("electricity", "D", "Electricity, gas, steam and air conditioning", 3, r"^Sản xuất và phân phối điện"),
    ("water", "E", "Water supply, sewerage and waste management", 3, r"^Cung cấp nước"),
    ("construction", "F", "Construction", 2, r"^Xây dựng"),
    ("services", "G-T", "Services", 1, r"^Dịch vụ\s*$"),
    ("trade", "G", "Wholesale and retail trade; repair of motor vehicles", 2, r"^Bán buôn và bán lẻ"),
    ("transport", "H", "Transport and storage", 2, r"^Vận tải,? kho bãi"),
    ("accommodation", "I", "Accommodation and food services", 2, r"^Dịch vụ lưu trú và ăn uống"),
    ("info_comm", "J", "Information and communication", 2, r"^Thông tin và truyền thông"),
    ("finance", "K", "Financial, banking and insurance activities", 2, r"^Hoạt động tài chính"),
    ("real_estate", "L", "Real estate activities", 2, r"^Hoạt động kinh doanh bất động sản"),
    ("professional", "M", "Professional, scientific and technical activities", 2, r"^Hoạt động chuyên môn"),
    ("admin_support", "N", "Administrative and support services", 2, r"^Hoạt động hành chính"),
    ("public_admin", "O", "Communist Party, socio-political organisations, public administration and defence; "
                          "compulsory social security", 2, r"^Hoạt động của Đảng"),
    ("education", "P", "Education and training", 2, r"^Giáo dục"),
    ("health", "Q", "Health and social work", 2, r"^Y tế"),
    ("arts", "R", "Arts, entertainment and recreation", 2, r"^Nghệ thuật"),
    ("other_services", "S", "Other service activities", 2, r"^Hoạt động dịch vụ khác"),
    ("households", "T", "Activities of households as employers and own-use production", 2, r"^Hoạt động làm thuê"),
    ("taxes", "", "Taxes on products less subsidies on products", 1, r"^Thuế sản phẩm"),
]


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _period(t, year, ref_q):
    t = t.lower()
    m = re.search(r"quý\s+(iv|i{1,3})\b", t)
    if m:
        return f"{year}-Q{ROMAN[m.group(1).upper()]}", "Q"
    if re.search(r"6\s*tháng", t):
        return f"{year}-H1", "6M"
    if re.search(r"9\s*tháng", t):
        return f"{year}-9M", "9M"
    if re.search(r"cả\s*năm|\bcả\b", t):
        return str(year), "Y"
    return None, None


def read_gdp_book(data, name, ref):
    """GDP by industry from one quarter-end report workbook. ref = 'YYYY-Qn' (the reference quarter).
    Rows {period, span, code, price, measure, status, value, as_published} with price current|constant_2010|constant_2020,
    measure level (VND bn) | share (% of GDP at current prices) | yoy (same period last year = 100, or % growth where
    NSO prints the growth rate). Nothing is calculated; as_published is 'index' or 'pct'."""
    year, ref_q = int(ref[:4]), int(ref[-1])
    out = []
    for sname, rows in _sheets(data, name):
        title = _norm(" ".join(str(c) for r in rows[:3] for c in r if isinstance(c, str)))
        if not re.search(r"Tổng sản phẩm trong nước", title) or re.search(r"địa bàn|GRDP", title):
            continue
        first = next((i for i, r in enumerate(rows) if any(isinstance(c, str) and re.match(r"\s*TỔNG SỐ", c) for c in r[:2])), None)
        if first is None:
            continue
        ncol = max(len(r) for r in rows[:first + 1])
        filled = []   # header rows, merged labels carried right
        for r in rows[1:first]:
            row, last = [], ""
            for j in range(ncol):
                c = r[j] if j < len(r) else None
                if isinstance(c, str) and c.strip():
                    last = _norm(c)
                row.append(last if j >= 2 else "")
            filled.append(row)
        raw_hdr = [[_norm(r[j]) if j < len(r) and isinstance(r[j], str) else "" for j in range(ncol)] for r in rows[1:first]]
        base_m = re.search(r"giá so sánh (\d{4})", title)
        title0 = _norm(" ".join(str(c) for c in rows[0] if isinstance(c, str)))
        combined = not re.search(r"giá hiện hành|giá so sánh", title0)   # Q1: one table, both price bases
        cols = {}
        for j in range(2, ncol):
            if rows[first][j] is None or _cell(rows[first][j]) is None:
                continue
            own = " ".join(h[j] for h in raw_hdr)
            carried = " ".join(h[j] for h in filled)
            if combined:
                bm = re.search(r"giá so sánh (\d{4})", carried)
                price = f"constant_{bm.group(1)}" if bm else "current" if "hiện hành" in carried else None
                period, span = f"{year}-Q1", "Q"
                status = "estimate"
            else:
                price = f"constant_{base_m.group(1)}" if base_m else "current"
                period, span = _period(own, year, ref_q)
                status = "preliminary" if "Sơ bộ" in carried else "estimate" if "Ước tính" in carried else ""
            if not price or not period:
                continue
            if re.search(r"Cơ cấu", carried):
                measure, pub = "share", "pct"
            elif re.search(r"So với cùng kỳ|phát triển|Tốc độ", carried, re.I):
                measure = "yoy"
                pub = "pct" if re.search(r"Tốc độ tăng", carried, re.I) else "index"
            else:
                measure, pub = "level", "level"
            cols[j] = (price, period, span, measure, status, pub)
        # status of a share or growth column = that of the level column for the same period
        lev = {(p, per): st for p, per, _, m, st, _ in cols.values() if m == "level"}
        seen = set()
        for r in rows[first:]:
            lab = _norm(next((c for c in r[:2] if isinstance(c, str) and c.strip()), ""))
            code = next((c for c, _, _, _, pat in GDP_ROWS if re.search(pat, lab)), None)
            if not code or code in seen:
                continue
            seen.add(code)
            for j, (price, period, span, measure, status, pub) in cols.items():
                v = _cell(r[j]) if j < len(r) else None
                if v is None:
                    continue
                st = status if measure == "level" else lev.get(("current" if measure == "share" else price, period), status)
                out.append({"period": period, "span": span, "code": code, "price": price, "measure": measure,
                            "status": st, "value": v, "as_published": pub, "label_vi": lab})
    return out


IIP_ROWS_SKIP = re.compile(r"^%$|^Đơn vị|^Ngành", re.I)


def read_iip_book(data, name, ref):
    """Quarterly industrial production index by VSIC section and division (same quarter last year = 100) from one
    quarter-end report workbook: the quarterly IIP table (Q2-Q4 books), or the Q1 book's single IIP table (its
    'Quý I ... so với cùng kỳ' column). Rows {period, label_vi, order, value}."""
    year = int(ref[:4])
    out = []
    for sname, rows in _sheets(data, name):
        title = _norm(" ".join(str(c) for r in rows[:2] for c in r if isinstance(c, str)))
        if not re.search(r"Chỉ số sản xuất công nghiệp", title) or re.search(r"lao động|địa phương", title, re.I):
            continue
        quarterly = re.search(r"các quý", title)
        first = next((i for i, r in enumerate(rows) if r and isinstance(r[0], str) and re.match(r"\s*Toàn ngành", r[0])), None)
        if first is None:
            continue
        ncol = max(len(r) for r in rows[:first + 1])
        hdr = [" ".join(_norm(r[j]) for r in rows[1:first] if j < len(r) and isinstance(r[j], str)) for j in range(ncol)]
        cols = {}
        for j in range(1, ncol):
            m = re.search(r"Quý\s+(IV|I{1,3})\b", hdr[j], re.I)
            if not m:
                continue
            if quarterly or re.search(r"cùng kỳ", hdr[j]):
                cols[j] = f"{year}-Q{ROMAN[m.group(1)]}"
        if not quarterly and not cols:
            continue
        if not quarterly and ref.endswith("Q1"):
            cols = {j: p for j, p in cols.items() if p.endswith("Q1")}
        elif not quarterly:
            continue   # monthly table in a Q2-Q4 book: the quarterly table is used
        prev = ""
        for k, r in enumerate(rows[first:]):
            lab = _norm(r[0]) if r and isinstance(r[0], str) else ""
            if not lab or IIP_ROWS_SKIP.search(lab):
                continue
            if lab[0].islower() and prev:   # a label wrapped onto the next row (values on the second row)
                lab = f"{prev} {lab}"
            prev = lab
            for j, p in cols.items():
                v = _cell(r[j]) if j < len(r) else None
                if v is not None:
                    out.append({"period": p, "label_vi": lab, "order": k, "value": v})
    return out


def labels_for(kind):
    rows = PPI_ROWS if kind == "ppi" else INPUT_ROWS if kind == "input" else TRADE_ROWS if kind in ("export", "import") else [("all", "All items", "")]
    return {s: lab for s, lab, _ in rows}


def sha(b):
    return hashlib.sha256(b).hexdigest()[:16]


def today():
    return dt.date.today().isoformat()
