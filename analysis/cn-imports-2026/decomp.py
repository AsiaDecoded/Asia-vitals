"""Decomposition of China's Jan-Sep 2026 import growth (US$) from GACC bulletin levels: Jan-Sep 2026 (Sep 2026 page,
year-to-date column) against Jan-Sep 2025 (Sep 2025 page, year-to-date column; where GACC's cell overflows (#####),
the sum of the nine monthly figures). Contribution (pp) = change / total Jan-Sep 2025 imports * 100.
Table 14: volume effect = (Q26/Q25 - 1) * V25; price (unit value) effect = change in value - volume effect."""
import sys, json, gzip, csv, collections, re
sys.path.insert(0, '/home/claude/asia-vitals/pipeline')
from sources import trade_cn as t
ROOT = '/home/claude/asia-vitals'; OUT = sys.argv[1]; M = int(sys.argv[2]) if len(sys.argv) > 2 else 9
d = json.load(gzip.open(f'{ROOT}/raw/trade/cn/store.json.gz', 'rt'))
mon = collections.defaultdict(dict)
for r in csv.DictReader(open(f'{ROOT}/data/trade/cn/trade_cn.csv')):
    mon[(r['flow'], r['partner'], r['product'])][r['date'][:7]] = (float(r['value']), r['unit'])
def monsum(flow, p, prod, y):
    s = mon.get((flow, p, prod), {}); ms = [f'{y}-{i:02d}' for i in range(1, M + 1)]
    return sum(s[m][0] for m in ms) if all(m in s for m in ms) else None
SCALE = {'T': ('t', 1), '10000T': ('t', 1e4), 'KG': ('t', 1e-3), 'N': ('n', 1), '10000N': ('n', 1e4), 'MN': ('n', 1e6),
         '100MN': ('n', 1e8), '10000CUM': ('m3', 1e4), 'CUM': ('m3', 1), '10000L': ('l', 1e4), 'L': ('l', 1)}
def table(tab, y, word, groups):
    rows = t.frame(d[f'{tab}:{y}-{M:02d}']); lab, hdr, first = t.layout(rows, word); c = t.columns(rows, hdr, M, groups)
    return rows, lab, first, c
res = {}
for y in (2025, 2026):
    # partners
    rows, lab, first, c = table('2', y, 'Country', ['Imports'])
    for r in rows[first:]:
        iso = next((cc for pat, cc in t.COUNTRY if re.search(pat, r[lab].replace('，', ',').lower())), None)
        if iso:
            v = t.num(r[c['Imports']['ytd']]); v = v / 1000 if v is not None else monsum('imports', iso, 'TOTAL', y)
            res.setdefault(('partner', iso), {'name': r[lab]})[y] = (v, None, None)
    # HS
    rows, lab, first, c = table('4', y, 'HS Section', ['Imports'])
    for r in rows[first:]:
        code = 'TOTAL' if r[lab].upper() == 'TOTAL' else t.section_code(r[lab])
        if code:
            v = t.num(r[c['Imports']['ytd']]); v = v / 1000 if v is not None else monsum('imports', 'WLD', code, y)
            res.setdefault(('hs', code), {'name': re.sub(r'^\S+\s+', '', r[lab])[:70]})[y] = (v, None, None)
    # table 14
    rows, lab, first, c = table('14', y, 'Commodity', ['Quantity', 'Value'])
    seen = set()
    for r in rows[first:]:
        name = r[lab]
        if not name or re.match(r'^(of which|note)', name, re.I) or name == r[lab + 1]: continue
        code = t.product14(name)
        if code in seen: continue
        seen.add(code)
        v = t.num(r[c['Value']['ytd']]); q = t.num(r[c['Quantity']['ytd']]); u = r[lab + 1]
        v = v / 1000 if v is not None else monsum('imports', 'WLD', code, y)
        res.setdefault(('c14', code), {'name': name})[y] = (v, q, u)
tot25 = res[('hs', 'TOTAL')][2025][0]; tot26 = res[('hs', 'TOTAL')][2026][0]
out = []
for (tab, code), x in res.items():
    if 2025 not in x or 2026 not in x or x[2025][0] is None or x[2026][0] is None: continue
    v25, q25, u25 = x[2025]; v26, q26, u26 = x[2026]
    row = dict(table=tab, code=code, name=x['name'], v25=round(v25, 1), v26=round(v26, 1), chg=round(v26 - v25, 1),
               growth=round((v26 / v25 - 1) * 100, 1) if v25 else None, contrib_pp=round((v26 - v25) / tot25 * 100, 2),
               share25=round(v25 / tot25 * 100, 2), share26=round(v26 / tot26 * 100, 2))
    if tab == 'c14' and q25 and q26 and u25 in SCALE and u26 in SCALE and SCALE[u25][0] == SCALE[u26][0]:
        Q25 = q25 * SCALE[u25][1]; Q26 = q26 * SCALE[u26][1]
        vol = (Q26 / Q25 - 1) * v25; pri = (v26 - v25) - vol
        row.update(qty_unit=SCALE[u26][0], q25=Q25, q26=Q26, q_growth=round((Q26 / Q25 - 1) * 100, 1),
                   uv_growth=round(((v26 / Q26) / (v25 / Q25) - 1) * 100, 1), vol_pp=round(vol / tot25 * 100, 2),
                   price_pp=round(pri / tot25 * 100, 2), unit_note='' if u25 == u26 else f'unit {u25} (2025) vs {u26} (2026), converted')
    out.append(row)
cols = ['table', 'code', 'name', 'v25', 'v26', 'chg', 'growth', 'contrib_pp', 'share25', 'share26', 'qty_unit', 'q25', 'q26',
        'q_growth', 'uv_growth', 'vol_pp', 'price_pp', 'unit_note']
with open(OUT, 'w', newline='') as f:
    w = csv.DictWriter(f, cols, extrasaction='ignore'); w.writeheader(); [w.writerow(r) for r in out]
print(f'total Jan-{M} 2025 {tot25:,.0f}  2026 {tot26:,.0f}  growth {(tot26/tot25-1)*100:.1f}%  change {tot26-tot25:,.0f}')
