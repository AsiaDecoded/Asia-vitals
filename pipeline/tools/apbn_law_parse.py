"""Original budget laws (UU APBN) 2001-2025: revenue, expenditure and deficit as set in each law, read from the law
texts saved by apbn_law_probe.py (pasal.id copies of the laws, OCR text for recent years). Each figure is read twice:
from the digits (OCR 'O' read as 0) and from the amount in words; the deficit is kept only when both agree, or, where
one is unreadable, when revenue - expenditure equals it. Writes the rows to stdout as JSON.

  python -I pipeline/tools/apbn_law_parse.py DIR_WITH_laws/<year>.html
"""
import re, sys, json
S = sys.argv[1]
def txt(p):
    t = open(p, encoding='utf-8', errors='replace').read()
    t = re.sub(r"(?s)<(script|style).*?</\1>", " ", t); t = re.sub(r"<[^>]+>", " ", t); t = t.replace('&nbsp;', ' ')
    return re.sub(r"\s+", " ", t)
UNITS = {'nol':0,'satu':1,'se':1,'dua':2,'tiga':3,'empat':4,'lima':5,'enam':6,'tujuh':7,'delapan':8,'sembilan':9}
SCALE = {'kuadriliun':10**15,'triliun':10**12,'miliar':10**9,'milyar':10**9,'juta':10**6,'ribu':10**3}
FIX = {'putuh':'puluh','pufuh':'puluh','enarn':'enam','rnilyar':'milyar','rniliar':'miliar','lirna':'lima','sernbilan':'sembilan',
       'trilyun':'triliun', 'trilliun':'triliun', 'tqjuh':'tujuh', 'enarn':'enam','delapanbelas':'delapan belas','tuiuh':'tujuh','juia':'juta','ratrrs':'ratus','ratu s':'ratus'}
def words(w):
    w = w.lower()
    w = re.sub(r"(?<=[a-z]) (?=[a-z] )", "", w)  # 'tril i un' -> partly
    w = re.sub(r"\b(t\s*r\s*i\s*l\s*[i1l]\s*[uy]\s*n)\b", "triliun", w)
    w = re.sub(r"\b(m\s*[i1l]\s*l\s*[i1l]\s*[ay]\s*a?\s*r)\b", "miliar", w)
    for a, b in FIX.items(): w = w.replace(a, b)
    w = re.sub(r"[^a-z ]", " ", w)
    toks = w.split()
    total, group, cur = 0, 0, 0
    for t in toks:
        if t in ('rupiah',): break
        if t.startswith('se') and t[2:] in ('ratus', 'puluh', 'belas', 'ribu', 'juta', 'miliar', 'triliun'):
            t2 = t[2:]
            if t2 == 'ratus': group += 100
            elif t2 == 'puluh': group += 10
            elif t2 == 'belas': group += 11
            else: total += 1 * SCALE[t2]
            continue
        if t in UNITS: cur = UNITS[t]
        elif t == 'sepuluh': group += 10
        elif t == 'sebelas': group += 11
        elif t == 'belas': group += cur + 10; cur = 0
        elif t == 'puluh': group += cur * 10; cur = 0
        elif t == 'ratus': group += cur * 100; cur = 0
        elif t in SCALE: total += (group + cur) * SCALE[t]; group, cur = 0, 0
        elif t in ('dan', 'koma'): pass
        else: return None
    return total + group + cur
def digits(d):
    d = d.replace(' ', '').replace('O', '0').replace('o', '0')
    d = d.split(',')[0].replace('.', '')
    return int(d) if d.isdigit() else None


AMBIG = {"O": "0", "o": "0", "I": "1", "l": "1", "L": "1", "a": "8", "s": "5", "S": "35"}


def digit_variants(d):
    """All readings of an OCR'd amount, trying each ambiguous character's possible digits."""
    d = d.replace(" ", "").split(",")[0].replace(".", "")
    outs = [""]
    for ch in d:
        opts = ch if ch.isdigit() else AMBIG.get(ch, "")
        if not opts:
            return []
        outs = [o + c for o in outs for c in opts][:256]
    return [int(o) for o in outs if o]
def find(t, pats):
    out = []
    for pat in pats:
        for m in re.finditer(pat + r"\s*Rp\s*([0-9OoSIl .]+(?:,[0-9Oo]{0,2})?)\s*\(([^)]{5,400})\)", t, re.I):
            head = m.group(0)[: m.group(0).lower().find(" rp")]
            if pat is not P_DEF[0] and re.search(r"(?i)d[ae][fl][il1]sit", head):
                continue   # a revenue/expenditure pattern that ran into the deficit sentence
            out.append((digits(m.group(1)), words(m.group(2)), m.group(0)[:120], digit_variants(m.group(1))))
    return out
P_REV = [r"pendapatan\s+negara(?:\s+dan\s+hibah)?[^.()]{0,160}?sebesar"]
P_EXP = [r"belanja\s+negara[^.()]{0,160}?sebesar"]
P_DEF = [r"(?:terdapat\s+)?(?:anggaran\s+)?d[ae][fl][il1]sit\s+(?:anggaran\s+)?sebesar"]
LAWS = {2001: "UU 35/2000", 2002: "UU 19/2001", 2003: "UU 29/2002", 2004: "UU 28/2003", 2005: "UU 36/2004", 2006: "UU 13/2005",
        2007: "UU 18/2006", 2008: "UU 45/2007", 2009: "UU 41/2008", 2010: "UU 47/2009", 2011: "UU 10/2010", 2012: "UU 22/2011",
        2013: "UU 19/2012", 2014: "UU 23/2013", 2015: "UU 27/2014", 2016: "UU 14/2015", 2017: "UU 18/2016", 2018: "UU 15/2017",
        2019: "UU 12/2018", 2020: "UU 20/2019", 2021: "UU 9/2020", 2022: "UU 6/2021", 2023: "UU 28/2022", 2024: "UU 19/2023",
        2025: "UU 62/2024"}
res = {}
rows = []
for y in range(2001, 2026):
    t = txt(f"{S}/laws/{y}.html")
    r = {k: find(t, p) for k, p in (('rev', P_REV), ('exp', P_EXP), ('def', P_DEF))}
    def best(c):
        both = [d for d, w, _, _v in c if d and w and abs(d - w) < 1e9]
        if both:
            return both[0], "digits and words"
        one = [d or w for d, w, _, _v in c if (d or w)]
        return (one[0], "one reading") if one else (None, "")

    def cands(c):
        out = set()
        for d, w, _, v in c:
            out.update(x for x in [d, w] + v if x)
        return out
    dv, dh = best(r["def"])
    R, E_ = cands(r["rev"]), cands(r["exp"])
    pair = [(a, b) for a in R for b in E_ if dv and abs(a - b + dv) < 1e6]
    rv = ev = None
    how = ""
    if pair:
        rv, ev = pair[0]
        how = "revenue and expenditure read; revenue - expenditure = deficit"
    elif dv and E_:
        e_ok = [b for d, w, _, v in r["exp"] for b in [w] if w and d and abs(d - w) < 1e9] or [w for d, w, _, v in r["exp"] if w]
        if e_ok:
            ev = e_ok[0]; rv = ev - dv
            how = "expenditure read; revenue = expenditure - deficit, as the law sets"
    ok = dh == "digits and words" or bool(pair)
    rows.append({"year": y, "law": LAWS[y], "revenue": rv, "expenditure": ev, "balance": -dv if (dv and ok) else None,
                 "check": dh if ok else "unconfirmed", "rev_exp": how})
print(json.dumps(rows, indent=1))
