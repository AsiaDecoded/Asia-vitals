"""DGBAS (Taiwan) price statistics: Macro Database (nstatdb) client and monthly release reader.

Macro Database, no key (https://nstatdb.dgbas.gov.tw/dgbasAll/webMain.aspx):
  ?sys=212&x=2100&funid=<table>&plus=0&r=1   table definition (JSON): field names, first/last month
  ?sys=220&funid=<table>&ymf=<yyymm>&ymt=<yyymm>&kind=21&type=0&cycle=1&outmode=12&outkind=1&deflst=2&compmode=<m>
                                             CSV (UTF-8 BOM), one row per month ("115年9月"), one column per field;
                                             compmode 00 = index, 1 = % change on previous month, 2 = % change on
                                             same month a year earlier. Periods are ROC years (CE - 1911).
Monthly price release (Chinese), https://www.stat.gov.tw/News.aspx?n=3703: one page per month with tables
t<yyymm>_1..14 (.xlsx). Table 1: CPI by group with weights (per mille) and DGBAS's contributions
("對總指數影響", pp); table 14: every priced item with its weight (% of CPI), index and changes.
Files on ws.dgbas.gov.tw: the server sends an incomplete certificate chain, so the TWCA intermediate
(public certificate, from the leaf's AIA URL, valid to 2033) is pinned here and added to the default
trust store; verification stays on.
"""
import csv
import html
import io
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

NSTAT = "https://nstatdb.dgbas.gov.tw/dgbasAll/webMain.aspx"
NEWS = "https://www.stat.gov.tw/News.aspx?n=3703&sms=10980&_CSN=133&page=1&PageSize=200"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) asia-vitals/0.1 (+https://github.com/AsiaDecoded/asia-vitals)",
      "Accept": "*/*", "Accept-Language": "zh-TW,en;q=0.8"}
TWCA_SSL_CA = """-----BEGIN CERTIFICATE-----
MIIG1DCCBLygAwIBAgIQQAE0sE8AAAAAAAAAA+MkrDANBgkqhkiG9w0BAQwFADBQ
MQswCQYDVQQGEwJUVzESMBAGA1UEChMJVEFJV0FOLUNBMRAwDgYDVQQLEwdSb290
IENBMRswGQYDVQQDExJUV0NBIENZQkVSIFJvb3QgQ0EwHhcNMjMwMjIzMDcyMjI0
WhcNMzMwMjIzMTU1OTU5WjBhMQswCQYDVQQGEwJUVzESMBAGA1UEChMJVEFJV0FO
LUNBMRMwEQYDVQQLEwpTU0wgU3ViLUNBMSkwJwYDVQQDEyBUV0NBIFNTTCBDZXJ0
aWZpY2F0aW9uIEF1dGhvcml0eTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoC
ggIBAMquxiSlMrxfOO29yqxCo/BIYBswnE7snZnuZDPcx8N9WhOdNGDsF024VjXK
nXoVaZBcv56eFsU+w9Mcq+uIVYzjVrBoe5u8ZLE0hPSkluH8URhcxtSQJ+gXcB0L
JHsseAeXVcgqoxTSJ6/n0xTCeXEnGwSRAzrqTvjS2gbd3TILxsfIHwRgwwPjBDgm
tjzbHHOFTJB3GCtH65T9A0viM2B/IW9Wz73jkz02AVMrZBHQ67IJ2W9CoIjd5mdG
eIV36U9NXl+wZa/D90pLRsFVbItKgLXgF71CQ92vS/biTx8fA6UUCU2ToNczP5Ur
A/mDXCBCLakwa1I3ylRkgFwluJw9DqiYh56MRgsEABa+ZPrm1Qb9njQZK4Y4V+ML
IvGM3xVoHIlvaSN29ubTueLpTeuAwN2VTiRzfOyCRKTcMBCtlMw1WCJNAMiNWDWS
BMnY9SlKv1oujmjS/ti0ptcipMymIoeWpVuQt3Mj8lYlKRpd6Zg8MbljMwQRSClK
6O6MSwpM3Xy5uJGh2cY5oYmKtxfyHSuKtKsk+daAPV1lpWYp9bNrbsLUPwmSY+zk
VgkZdiWBF//RP/72/esANONINy5hkWjkVd0NLjA5TAgk+DVVmnPtQIj1vBgtk8ak
Y9CczIbEgKBonkHWn+GX2ycR6jadg2P+xrBFg4MGjomkb2gtAgMBAAGjggGXMIIB
kzAfBgNVHSMEGDAWgBSdhWEUfMFib5do5E83QOGt4A1WNzAdBgNVHQ4EFgQU8ijU
+dQcfhprFoLl75Mpae3KFSAwDgYDVR0PAQH/BAQDAgEGMBMGA1UdJQQMMAoGCCsG
AQUFBwMBMEoGA1UdIARDMEEwNQYLKwYBBAGCvyUBARUwJjAkBggrBgEFBQcCARYY
aHR0cHM6Ly93d3cudHdjYS5jb20udHcvMAgGBmeBDAECAjBNBgNVHR8ERjBEMEKg
QKA+hjxodHRwOi8vUm9vdENBLnR3Y2EuY29tLnR3L1RXQ0FSQ0EvY3liZXJfcm9v
dF9yZXZva2VfMjAyMi5jcmwwEgYDVR0TAQH/BAgwBgEB/wIBADB9BggrBgEFBQcB
AQRxMG8wQwYIKwYBBQUHMAKGN2h0dHA6Ly9zc2xzZXJ2ZXIudHdjYS5jb20udHcv
Y2FjZXJ0L2N5YmVyX3Jvb3RfMjAyMi5jcnQwKAYIKwYBBQUHMAGGHGh0dHA6Ly9y
b290b2NzcC50d2NhLmNvbS50dy8wDQYJKoZIhvcNAQEMBQADggIBAIFF/6Gnvu8L
3xQDIampB8QVgoKS2bcjte0uJBbCrQHpzcGTuVTkZaiA86LwVz6SAU7TVgVYRXmt
x8l29WzfKI6wOAzmvlGZxSYAdN0I6YBkJK1nmDs0+TSw5lCzb+UOpajNOaMdJ5SN
YTN87yRwl82AFrwUmSLaMV4tN7W49N0SsELWs/d4uNHSMM0mBjd0hLDIWJFwOkuD
yOWahnCVfPlCwSVWpUntOGgOHOA02IUE+JNX+spIV1SwAMYaEVyHe316YUgiGA5y
k3liTa3vuv06eE1J2yiWrs9booW2VTHD+amzucFFNN1KvSLjSbYxG1t/FclHEN/y
6hGM3bkjRC31A0jzpv93D3MUQTdJascicPa0H4i8hviRriyetaC6HC4q8FQUTo2A
cEpxicNGgyHhDV+YdbnS6GZL+f3bsmMM8ZFYZ77mDTS9mRO1VnIwkjiN4vpzh67a
KTpoD9TQzZcGQiJy6Pi+PCSFiqjK7UD/63L/Pt0hpoNKvZLrz4ngrlpyzpx8KjeS
A5cjKcc6vlHm0Kk07k5djhJsaqQELso5r+UXi9qC+nwqPuR/w5kJZv4fz0ND4UhY
5y3qd+iCikkF3WzOzey7jUH9URKb3iZnRAHZvmyLK57UI0FwP+5xZEByvwXDtxbe
914Hj3cSUrmKT3g/ZlOQQ1THeu48MA79
-----END CERTIFICATE-----
"""
CTX = ssl.create_default_context()
CTX.load_verify_locations(cadata=TWCA_SSL_CA)


class DGBASError(Exception):
    pass


def get(url, tries=3, timeout=90):
    url = urllib.parse.quote(url, safe=":/?&=%#+,;@!$'()*~")
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} {e.reason}"
            if e.code in (400, 403, 404):
                break
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        time.sleep(3 * (i + 1))
    raise DGBASError(f"{url[:160]}: {last}")


# ---------------------------------------------------------------- periods
def roc(period):
    """'2026-09' -> '11509'."""
    return f"{int(period[:4]) - 1911}{period[5:7]}"


def ce(rocym):
    """'115年9月' or '11509' -> '2026-09'."""
    m = re.match(r"\s*(\d{2,3})年\s*(\d{1,2})月", rocym)
    if m:
        y, mm = int(m.group(1)), int(m.group(2))
    else:
        s = str(rocym).strip()
        y, mm = int(s[:-2]), int(s[-2:])
    return f"{y + 1911}-{mm:02d}"


# ---------------------------------------------------------------- Macro Database
def definition(funid):
    d = json.loads(get(f"{NSTAT}?sys=212&x=2100&funid={funid}&plus=0&r=1").decode("utf-8"))
    if not d.get("funname"):
        raise DGBASError(f"{funid}: empty table definition")
    return d


def latest(funid):
    """Latest month in a table, e.g. '2026-09' (one small call)."""
    return ce(str(definition(funid)["dataYMT"]))


def csv_table(funid, first, last, compmode="00"):
    """Returns (header, rows, raw text): header = field names, rows = {period: [values or None]}."""
    url = (f"{NSTAT}?sys=220&funid={funid}&ymf={roc(first)}&ymt={roc(last)}&kind=21&type=0&cycle=1"
           f"&outmode=12&outkind=1&deflst=2&compmode={compmode}")
    text = get(url).decode("utf-8-sig", "replace")
    if not text.startswith('"'):
        raise DGBASError(f"{funid} compmode {compmode}: not a CSV ({text[:80]!r})")
    lines = list(csv.reader(io.StringIO(text)))
    header = [h.strip() for h in lines[0][1:]]
    rows = {}
    for ln in lines[1:]:
        if not ln or not re.match(r"\s*\d{2,3}年\s*\d{1,2}月", ln[0]):
            continue
        vals = []
        for v in ln[1:]:
            v = v.strip().replace(",", "")
            try:
                vals.append(float(v))
            except ValueError:
                vals.append(None)  # '-' or blank: not published
        rows[ce(ln[0])] = vals
    return header, rows, text


def series(funid, first, last, modes=("00", "1", "2")):
    """{(field name, measure): {period: value}}, measure index | mom | yoy, plus the raw CSV texts."""
    meas = {"00": "index", "1": "mom", "2": "yoy"}
    out, raw = {}, {}
    for m in modes:
        header, rows, text = csv_table(funid, first, last, m)
        raw[f"{funid}_{m}"] = text
        for j, name in enumerate(header):
            s = {p: v[j] for p, v in rows.items() if j < len(v) and v[j] is not None}
            if s:
                out[(name, meas[m])] = s
    return out, raw


# ---------------------------------------------------------------- monthly releases
def releases(since="2023-01"):
    """CPI releases listed on stat.gov.tw: [{month, url, title, date}], newest first."""
    text = get(NEWS).decode("utf-8", "replace")
    out, seen = [], set()
    for href, label in re.findall(r'<a\b[^>]*?href="([^"]*News_Content\.aspx\?n=3703&(?:amp;)?s=\d+)"[^>]*>(.*?)</a>', text, re.S):
        lab = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", label))).strip()
        m = re.match(r"(\d{2,3})年(\d{1,2})月消費者物價指數", lab)
        if not m:
            continue
        month = f"{int(m.group(1)) + 1911}-{int(m.group(2)):02d}"
        if month < since or month in seen:
            continue
        seen.add(month)
        out.append({"month": month, "title": lab, "url": urllib.parse.urljoin(NEWS, html.unescape(href))})
    return out


def release_page(url):
    """{'date': 'YYYY-MM-DD', 'files': {name: url}} for one release page."""
    text = get(url).decode("utf-8", "replace")
    files = {}
    for href in re.findall(r'href="([^"]+\.(?:xlsx|xls|ods|pdf))"', text, re.I):
        u = urllib.parse.urljoin(url, html.unescape(href))
        files[urllib.parse.unquote(u.rsplit("/", 1)[-1])] = u
    m = re.search(r"張貼日期[^0-9]*(\d{2,3})-(\d{2})-(\d{2})", re.sub(r"<[^>]+>", " ", text))
    date = f"{int(m.group(1)) + 1911}-{m.group(2)}-{m.group(3)}" if m else ""
    return {"date": date, "files": files}


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def read_t1(blob):
    """Release table 1 -> {'month', 'rows': [{label, section, weight_pm, index, mom, mom_pp, yoy, yoy_pp, ytd_index, ytd, ytd_pp}]}."""
    import openpyxl
    ws = openpyxl.load_workbook(io.BytesIO(blob), data_only=True).worksheets[0]
    month, rows, section = None, [], ""
    for r in ws.iter_rows(values_only=True):
        cells = [c for c in r if c not in (None, "")]
        if not cells:
            continue
        joined = "".join(str(c) for c in cells)
        if month is None:
            m = re.search(r"民國(\d{2,3})年(\d{1,2})月", joined.replace(" ", ""))
            if m:
                month = f"{int(m.group(1)) + 1911}-{int(m.group(2)):02d}"
        texts = [str(c).replace("\n", "").replace(" ", "").replace("　", "") for c in cells if isinstance(c, str)]
        nums = [_num(c) for c in cells if _num(c) is not None]
        if not texts or len(nums) not in (6, 9):
            continue  # 9 numbers; January tables have no year-to-date columns (6)
        label = texts[-1]
        if len(texts) > 1:
            section = texts[0]
        w, idx, mom, mompp, yoy, yoypp, ytdi, ytd, ytdpp = (nums + [None, None, None])[:9]
        rows.append({"label": label, "section": section, "weight_pm": w, "index": idx, "mom": mom, "mom_pp": mompp,
                     "yoy": yoy, "yoy_pp": yoypp, "ytd_index": ytdi, "ytd": ytd, "ytd_pp": ytdpp})
    return {"month": month, "rows": rows}


ITEM = re.compile(r"^[◎△▲×\s]*(\d{1,3})\s*$")


def read_t14(blob):
    """Release table 14 -> {code: {name, weight_pct, index, mom|yoy|ytd}}: every priced item listed, its weight
    (% of CPI, this month's), index and the changes shown in each sheet."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(blob), data_only=True)
    items = {}
    for ws in wb.worksheets:
        title = ws.title
        meas = "mom" if "上月" in title else "yoy" if "同月" in title else "ytd" if "同期" in title else title
        for r in ws.iter_rows(values_only=True):
            r = list(r)
            j = 0
            while j < len(r):
                c = r[j]
                m = ITEM.match(str(c)) if isinstance(c, (str, int)) and not isinstance(c, bool) else None
                if m and j + 1 < len(r) and isinstance(r[j + 1], str) and r[j + 1].strip():
                    name = r[j + 1].strip()
                    nums, k = [], j + 2
                    while k < len(r) and len(nums) < 3:
                        v = _num(r[k])
                        if v is not None:
                            nums.append(v)
                        elif isinstance(r[k], str) and r[k].strip():
                            break
                        k += 1
                    if len(nums) == 3:
                        code = int(m.group(1))
                        it = items.setdefault(code, {"name": name})
                        it["weight_pct"], it["index"], it[meas] = nums
                        j = k
                        continue
                j += 1
    return items
