"""China imports by every partner in GACC bulletin table (2): Jan-Sep 2026 vs Jan-Sep 2025 (each year's Sep page,
year-to-date column, US$ million). Where GACC's 2025 cell overflows (#####) or is blank, the 2025 level is the 2026
level divided by (1 + GACC's published year-to-date change), flagged in v25_source."""
import sys, json, gzip, csv
sys.path.insert(0, '/home/claude/asia-vitals/pipeline')
from sources import trade_cn as t
d = json.load(gzip.open('/home/claude/asia-vitals/raw/trade/cn/store.json.gz', 'rt'))
AGG = {'TOTAL', 'Asia:', 'Africa:', 'Europe:', 'Latin America:', 'North America:', 'Oceania:', 'ASEAN', 'EU', 'APEC', 'RCEP', 'BRI'}
def read(y):
    rows = t.frame(d[f'2:{y}-09']); lab, hdr, first = t.layout(rows, 'Country'); c = t.columns(rows, hdr, 9, ['Imports'])
    pc = [j for j in range(len(rows[0])) if 'ercent' in ' '.join(rows[h][j] for h in hdr) and rows[hdr[-1]][j] == 'Imports'][0]
    return {r[lab].replace('，', ', ').strip(): (t.num(r[c['Imports']['ytd']]), t.num(r[pc])) for r in rows[first:]
            if r[lab] and not r[lab].lower().startswith('note')}
a, b = read(2025), read(2026)
tot25 = 1904707.7
out = []
for n, (v26, g) in b.items():
    if v26 is None:
        continue
    v25, src = a.get(n, (None, None))[0], 'Sep 2025 page'
    v26 /= 1000
    if v25 is None:
        if g is None or g <= -99.9:
            continue
        v25, src = v26 / (1 + g / 100), 'Sep 2026 level / (1 + published change)'
    else:
        v25 /= 1000
    out.append(dict(partner=n, aggregate='y' if n in AGG else '', v25=round(v25, 1), v26=round(v26, 1), chg=round(v26 - v25, 1),
                    growth=round((v26 / v25 - 1) * 100, 1) if v25 else '', contrib_pp=round((v26 - v25) / tot25 * 100, 2),
                    gacc_growth=g, v25_source=src))
with open(sys.argv[1], 'w', newline='') as f:
    w = csv.DictWriter(f, list(out[0])); w.writeheader(); w.writerows(out)
