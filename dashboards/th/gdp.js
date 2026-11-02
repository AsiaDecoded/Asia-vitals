// Thailand GDP tab, Charts 1-6: GDP and GDP per capita in US dollars (World Bank WDI), quarterly growth (NESDC),
// annual growth by source and by sector. Figures are as published, except three calculated in the pipeline and
// flagged calculated = y in th_gdp (nominal y/y; the year to date for the latest year) and the CAGRs below.

// CAGR on Charts 1 and 2, calculated on this page: (value in the end year / value in the start year) ^ (1 / years) - 1,
// for each World Bank series drawn. Two periods (asked for 2 Nov 2026): 1986 to 1996, fixed, and 1997 to the
// latest WDI year. The dashed line stays at 1987, the year Thailand became lower-middle income (data year).
dash.calc('gdp_cagr', {
  title: 'GDP compound annual growth (CAGR)',
  description: 'Compound annual growth, 1986 to 1996 and 1997 to the latest World Bank year, for each GDP, GDP per capita and GNI per capita series shown in Charts 1 and 2.',
  inputs: ['th_gdp_intl', 'asia_gni_pc'],
  fn: (th_gdp_intl, asia_gni_pc) => {
    const PERIODS = [[1986, 1996], [1997, null]];   // null: the latest year of the series
    const by = {};
    th_gdp_intl.forEach((r) => { if (r.measure === 'level') (by[r.series] = by[r.series] || {})[Number(r.year)] = Number(r.value); });
    asia_gni_pc.forEach((r) => { if (r.economy === 'TH') (by['NY.GNP.PCAP.CD'] = by['NY.GNP.PCAP.CD'] || {})[Number(r.year)] = Number(r.gni_pc); });
    return Object.entries(by).flatMap(([series, v]) => PERIODS.map(([start, e]) => {
      const end = e == null ? Math.max(...Object.keys(v).map(Number)) : e;
      if (!(v[start] > 0) || !(v[end] > 0) || end <= start) return null;
      return { key: `${series}|${start}`, series, start, end, cagr: (Math.pow(v[end] / v[start], 1 / (end - start)) - 1) * 100 };
    })).filter(Boolean);
  },
});

(() => {
  const J = window.JG;
  const num = J.num;
  const visible = () => !document.getElementById('gdp').hidden;
  const failed = (st) => st === 'error' || st === 'connect' || st === 'declined';
  const qLab = (d) => `Q${Math.ceil(+d.slice(5, 7) / 3)} ${d.slice(0, 4)}`;
  const fmt0 = (v) => d3.format('.0f')(v);
  const LMI = 1987;          // lower-middle income from 1987 (data year): dashed line on Charts 1 and 2, CAGR start
  const START = '1994-01-01';  // NESDC y/y from Q1 1994
  const SEC = [['agri', 'Agriculture', 'var(--ad-c6)'], ['industrial', 'Industrial (B–E)', 'var(--ad-c1)'],
    ['services', 'Services (incl. construction)', 'var(--ad-c5)']];
  const YTD_LABEL = { '6M': 'Jan–Jun', '9M': 'Jan–Sep' };
  let growthBasis = 'real', srcPick = 'nesdc', usdPick = 'NY.GDP.MKTP.KD', pcPick = 'NY.GDP.PCAP.KD';

  function legend(id, series) {
    const el = document.getElementById(id); if (!el) return;
    el.replaceChildren();
    series.forEach((s) => {
      const span = document.createElement('span'); const ln = document.createElement('span');
      ln.className = s.bar ? 'sw' : 'ln'; ln.style.background = s.color;
      span.append(ln, document.createTextNode(s.name)); el.appendChild(span);
    });
  }
  function status(box, ids) {
    const st = ids.map((i) => dash.data(i).status);
    if (st.some(failed)) { box.classList.remove('dash-skeleton'); J.fail(box); return false; }
    if (st.some((s) => s !== 'ok')) { box.replaceChildren(); box.classList.add('dash-skeleton'); return false; }
    box.classList.remove('dash-skeleton');
    return true;
  }
  // Plot frame: y grid and labels, x as years. Annual rows (opt.annual) are labelled at their own points, every few
  // years counted back from opt.anchor (or the last point), and the last reads YTD when opt.ytd says so.
  function frame(box, rows, H, vals, fmt, zero, opt = {}) {
    const W = box.clientWidth, mr = 8;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    let lo = d3.min(vals), hi = d3.max(vals);
    if (zero) { lo = Math.min(0, lo); hi = Math.max(0, hi); }
    const y = d3.scaleLinear([lo, hi], [H - 24, 18]).nice();
    const ticks = y.ticks(5);
    const ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    const x = d3.scaleUtc([J.date(rows[0].date), J.date(rows[rows.length - 1].date)], [ml, W - mr]);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - mr).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (zero && v === 0 ? 'var(--cds-chart-reference)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
    const room = Math.max(1, Math.floor((W - ml - mr) / 44));
    const text = (px, t) => svg.append('text').attr('x', px).attr('y', H - 20).attr('dy', '0.71em').attr('font-size', 12).attr('fill', 'var(--ad-ink)')
      .attr('text-anchor', px > W - mr - 16 ? 'end' : px < ml + 16 ? 'start' : 'middle').text(t);
    if (opt.annual) {
      const n = rows.length, step = [1, 2, 5, 10].find((k) => n / k <= room) || 10;
      const anchor = opt.anchor != null ? opt.anchor : Number(rows[n - 1].date.slice(0, 4));
      rows.forEach((r, k) => {
        const yr = Number(r.date.slice(0, 4));
        const isY = opt.ytd && opt.ytd(r);
        if (!isY && (((yr - anchor) % step) + step) % step !== 0) return;
        if (isY && k !== n - 1) return;
        text(x(J.date(r.date)), isY ? 'YTD' : String(yr));
      });
    } else {
      const y0 = Number(rows[0].date.slice(0, 4)), y1 = Number(rows[rows.length - 1].date.slice(0, 4));
      const step = [1, 2, 5, 10].find((s) => (y1 - y0 + 1) / s <= Math.max(1, Math.round((W - ml - mr) / 56))) || 10;
      for (let yr = Math.ceil(y0 / step) * step; yr <= y1; yr += step) {
        const d = J.date(`${yr}-01-01`); if (d < x.domain()[0]) continue; text(x(d), String(yr));
      }
    }
    return { svg, x, y, W, ml, mr };
  }
  function tipLayer(svg, card, x, rows, H, ml, right, head, onMove) {
    const tip = J.tip(card);
    const rule = svg.append('line').attr('y1', 8).attr('y2', H - 22).attr('stroke', 'var(--cds-chart-reference)').attr('display', 'none');
    const bis = d3.bisector((r) => J.date(r.date)).center;
    const extras = [];
    svg.append('rect').attr('x', ml).attr('width', Math.max(0, right - ml)).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [mx] = d3.pointer(ev); const r = rows[bis(rows, x.invert(mx))]; const px = x(J.date(r.date));
        rule.attr('display', null).attr('x1', px).attr('x2', px);
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, head(r), onMove(r, px, extras), ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); extras.forEach((d) => d.attr('display', 'none')); tip.style.display = 'none'; });
    return extras;
  }
  const line = (svg, x, y, rows, key, color, thin) => svg.append('path')
    .attr('d', d3.line().defined((r) => r[key] != null).x((r) => x(J.date(r.date))).y((r) => y(r[key]))(rows))
    .attr('fill', 'none').attr('stroke', color).attr('stroke-width', thin ? 1.75 : 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');

  // NESDC rows from th_gdp: one industry, price basis, span; [{date, period, v, status, calculated}], sorted.
  function series(code, price, span) {
    const D = dash.data('th_gdp'); if (D.status !== 'ok') return [];
    return D.data.filter((r) => r.code === code && r.price === price && r.measure === 'yoy' && r.span === span)
      .map((r) => ({ date: r.date, period: r.period, v: num(r.rate), status: r.status, calc: r.calculated === 'y' }))
      .filter((r) => r.v != null).sort((a, b) => (a.date < b.date ? -1 : 1));
  }
  // The latest year to date (calculated from NESDC's chain volume levels) for a year with no annual figure yet.
  function ytdRow(code, lastYear) {
    const D = dash.data('th_gdp'); if (D.status !== 'ok') return null;
    const r = D.data.filter((x) => x.code === code && x.price === 'cvm_2002' && x.measure === 'yoy' && YTD_LABEL[x.span] && Number(x.date.slice(0, 4)) > lastYear)
      .sort((a, b) => (a.date < b.date ? -1 : 1)).pop();
    return r ? { date: `${r.date.slice(0, 4)}-12-01`, v: num(r.rate), span: r.span, year: r.date.slice(0, 4) } : null;
  }
  const ytdName = (y) => `YTD (NESDC, ${YTD_LABEL[y.span]} ${y.year}, calculated)`;
  const ST = { p1: 'preliminary', p: 'preliminary', r: 'revised' };

  // Chart 3: GDP growth on the same quarter a year earlier, from Q1 1994. Real: NESDC, chain volume (2002), as
  // published. Nominal: calculated in the pipeline from NESDC's current-price levels.
  function growth() {
    const id = 'gdp-growth', box = document.getElementById(id + '-chart');
    if (!status(box, ['th_gdp'])) return;
    const src = series('total', growthBasis === 'real' ? 'cvm_2002' : 'current', 'Q').filter((r) => r.date >= START);
    const rows = J.slice(src.map((r) => ({ ...r })), id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280;
    const { svg, x, y, W, ml, mr } = frame(box, rows, H, rows.map((r) => r.v), fmt0, true);
    const step = (W - ml - mr) / Math.max(1, rows.length), bw = Math.max(1.2, Math.min(22, step * 0.62));
    const col = growthBasis === 'real' ? 'var(--ad-c2)' : 'var(--ad-c1)';
    rows.forEach((r) => svg.append('rect').attr('x', x(J.date(r.date)) - bw / 2).attr('width', bw)
      .attr('y', y(Math.max(0, r.v))).attr('height', Math.abs(y(r.v) - y(0))).attr('fill', col));
    tipLayer(svg, document.getElementById(id), x, rows, H, ml, W - mr, (r) => qLab(r.date) + (ST[r.status] ? ` (${ST[r.status]})` : ''),
      (r) => [[col, growthBasis === 'real' ? 'Real GDP, y/y' : 'Nominal GDP, y/y (calculated)', r.v.toFixed(growthBasis === 'real' ? 1 : 2) + '%']]);
  }

  // Chart 4: real growth by sector, quarterly, NESDC's groups as published.
  function sectors() {
    const id = 'gdp-sectors', box = document.getElementById(id + '-chart');
    const S = [{ key: 'total', name: 'GDP', color: 'var(--ad-c2)' }].concat(SEC.map(([key, name, color]) => ({ key, name, color, thin: true })));
    legend(id + '-legend', S);
    if (!status(box, ['th_gdp'])) return;
    const by = new Map();
    S.forEach((s) => series(s.key, 'cvm_2002', 'Q').forEach((r) => { if (r.date < START) return; if (!by.has(r.date)) by.set(r.date, { date: r.date }); by.get(r.date)[s.key] = r.v; }));
    const rows = J.slice(Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1)), id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280;
    const { svg, x, y, W, ml, mr } = frame(box, rows, H, rows.flatMap((r) => S.map((s) => r[s.key])).filter((v) => v != null), fmt0, true);
    S.slice().reverse().forEach((s) => line(svg, x, y, rows, s.key, s.color, s.thin));
    const dots = S.map((s) => svg.append('circle').attr('r', 3.5).attr('fill', s.color).attr('display', 'none'));
    const ex = tipLayer(svg, document.getElementById(id), x, rows, H, ml, W - mr, (r) => qLab(r.date), (r, px) => {
      dots.forEach((d, i) => { const v = r[S[i].key]; d.attr('display', v == null ? 'none' : null).attr('cx', px).attr('cy', v == null ? 0 : y(v)); });
      return S.map((s) => [s.color, s.name, r[s.key] == null ? 'n/a' : r[s.key].toFixed(1) + '%']);
    });
    ex.push(...dots);
  }

  // Charts 5 and 6: annual real growth, with the latest year to date as an open circle (calculated).
  function annual(id, S, ds) {
    const box = document.getElementById(id + '-chart');
    legend(id + '-legend', S.length > 1 ? S : []);
    if (!status(box, ds)) return;
    const by = new Map();
    const put = (date, k, v) => { if (v == null) return; if (!by.has(date)) by.set(date, { date }); by.get(date)[k] = v; };
    S.forEach((s) => s.rows().forEach((r) => put(r.date, s.key, r.v)));
    const yt = {};
    S.forEach((s) => {
      if (!s.ytd) return;
      const last = Math.max(...s.rows().map((r) => Number(r.date.slice(0, 4))));
      const r = ytdRow(s.ytd, last); if (r) { yt[s.key] = r; put(r.date, s.key + '_ytd', r.v); }
    });
    const all = Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
    const rows = J.slice(all, id);
    if (!rows.length) { box.replaceChildren(); return; }
    const isY = (r) => S.every((s) => r[s.key] == null) && S.some((s) => r[s.key + '_ytd'] != null);
    const H = 280;
    const { svg, x, y, W, ml, mr } = frame(box, rows, H, rows.flatMap((r) => S.flatMap((s) => [r[s.key], r[s.key + '_ytd']])).filter((v) => v != null),
      fmt0, true, { annual: true, ytd: isY });   // labels counted back from the last point (YTD when shown)
    S.slice().reverse().forEach((s) => line(svg, x, y, rows, s.key, s.color, s.thin));
    S.forEach((s) => rows.filter((r) => r[s.key + '_ytd'] != null).forEach((r) => svg.append('circle').attr('cx', x(J.date(r.date))).attr('cy', y(r[s.key + '_ytd']))
      .attr('r', s.thin ? 3.5 : 4.5).attr('fill', 'var(--color-panel)').attr('stroke', s.color).attr('stroke-width', 2)));
    const anyY = Object.values(yt)[0];
    tipLayer(svg, document.getElementById(id), x, rows, H, ml, W - mr, (r) => (isY(r) && anyY ? ytdName(anyY) : r.date.slice(0, 4)),
      (r) => S.map((s) => { const v = isY(r) ? r[s.key + '_ytd'] : r[s.key]; return [s.color, s.name, v == null ? 'n/a' : v.toFixed(s.dp || 1) + '%']; }));
  }
  const nesdcY = (code) => () => series(code, 'cvm_2002', 'Y').map((r) => ({ date: r.date, v: r.v }));
  function sources() {
    const wb = () => (dash.data('th_gdp_intl').status === 'ok' ? dash.data('th_gdp_intl').data : [])
      .filter((r) => r.series === 'NY.GDP.MKTP.KD.ZG').map((r) => ({ date: r.date, v: num(r.value) })).filter((r) => r.v != null);
    const S = srcPick === 'nesdc'
      ? [{ key: 'nesdc', name: 'NESDC', color: 'var(--ad-c2)', rows: nesdcY('total'), ytd: 'total' }]
      : [{ key: 'wb', name: 'World Bank', color: 'var(--ad-c2)', rows: wb, ytd: 'total', dp: 2 }];
    annual('gdp-src', S, ['th_gdp', 'th_gdp_intl']);
  }

  // Charts 1 and 2: GDP and GDP per capita in US dollars, annual, World Bank WDI, as published (GDP in US$ billion,
  // the World Bank's US$ / 1e9). Real: constant 2015 US$. Nominal: current US$; on Chart 2 with GNI per capita, Atlas
  // method (central dataset, the series behind the income classification). Total GNI (Atlas) for Chart 1 is not in
  // the central dataset yet (asked of the main chat).
  const USD = {
    'gdp-usd': { div: 1e9, unit: 'US$ billion', tipUnit: ' bn', fmt: ',.1f',
      real: [{ key: 'NY.GDP.MKTP.KD', name: 'GDP', color: 'var(--ad-c2)' }],
      nominal: [{ key: 'NY.GDP.MKTP.CD', name: 'GDP', color: 'var(--ad-c1)' }] },
    'gdp-pc': { div: 1, unit: 'US$', tipUnit: '', fmt: ',.0f',
      real: [{ key: 'NY.GDP.PCAP.KD', name: 'GDP per capita', color: 'var(--ad-c2)' }],
      nominal: [{ key: 'NY.GDP.PCAP.CD', name: 'GDP per capita', color: 'var(--ad-c1)' }, { key: 'NY.GNP.PCAP.CD', name: 'GNI per capita, Atlas method', color: 'var(--ad-c2)' }] },
  };
  function usd(id, pick) {
    const C = USD[id], box = document.getElementById(id + '-chart'), nominal = /\.CD$/.test(pick), S = nominal ? C.nominal : C.real;
    document.getElementById(id + '-units').textContent = `${C.unit}, ${nominal ? 'current prices' : 'constant 2015 prices'}`;
    legend(id + '-legend', S.length > 1 ? S : []);
    const ds = ['th_gdp_intl'].concat(S.some((s) => s.key === 'NY.GNP.PCAP.CD') ? ['asia_gni_pc'] : []);
    if (!status(box, ds)) return;
    const by = new Map();
    const put = (date, k, v) => { if (v == null) return; if (!by.has(date)) by.set(date, { date }); by.get(date)[k] = v / C.div; };
    dash.data('th_gdp_intl').data.forEach((r) => { if (S.some((s) => s.key === r.series)) put(r.date, r.series, num(r.value)); });
    if (ds.includes('asia_gni_pc')) dash.data('asia_gni_pc').data.forEach((r) => { if (r.economy === 'TH') put(`${r.year}-12-01`, 'NY.GNP.PCAP.CD', num(r.gni_pc)); });
    const rows = J.slice(Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1)), id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280;
    const { svg, x, y, W, ml, mr } = frame(box, rows, H, rows.flatMap((r) => S.map((s) => r[s.key])).filter((v) => v != null).concat([0]),
      (v) => d3.format(',.0f')(v), true, { annual: true, anchor: LMI });
    S.forEach((s) => line(svg, x, y, rows, s.key, s.color));
    if (rows[0].date.slice(0, 4) < String(LMI) && rows[rows.length - 1].date.slice(0, 4) > String(LMI)) {
      const lx = x(J.date(`${LMI}-12-01`));
      svg.append('line').attr('x1', lx).attr('x2', lx).attr('y1', 18).attr('y2', H - 24).attr('stroke', 'var(--ad-axis)').attr('stroke-dasharray', '3 3');
      svg.append('text').attr('x', lx).attr('y', 12).attr('font-size', 12).attr('fill', 'var(--ad-ink)').attr('text-anchor', 'middle').text('Lower-middle income');
    }
    const G = dash.data('gdp_cagr');
    // one line per series and period, earlier period first
    const cagr = G.status === 'ok' ? G.data.filter((r) => S.some((s) => s.key === r.series)).sort((p, q) => p.start - q.start || S.findIndex((s) => s.key === p.series) - S.findIndex((s) => s.key === q.series))
      .map((c) => ({ s: S.find((s) => s.key === c.series), c })) : [];
    if (cagr.length) {
      const lh = 16, tx = W - mr - 8, ty = H - 40 - (cagr.length - 1) * lh;
      const t = svg.append('text').attr('font-size', 12).attr('font-weight', 700).attr('fill', 'var(--ad-ink)').attr('text-anchor', 'end').attr('x', tx).attr('y', ty);
      cagr.forEach((o, k) => t.append('tspan').attr('x', tx).attr('dy', k ? lh : 0).attr('fill', S.length > 1 ? o.s.color : null)
        .text(`${o.c.start}–${o.c.end} CAGR: ${o.c.cagr.toFixed(1)}% p.a.`));
    }
    const dots = S.map((s) => svg.append('circle').attr('r', 3.5).attr('fill', s.color).attr('display', 'none'));
    const ex = tipLayer(svg, document.getElementById(id), x, rows, H, ml, W - mr, (r) => r.date.slice(0, 4), (r, px) => {
      S.forEach((s, k) => (r[s.key] == null ? dots[k].attr('display', 'none') : dots[k].attr('display', null).attr('cx', px).attr('cy', y(r[s.key]))));
      return S.map((s) => [s.color, s.name, r[s.key] == null ? 'n/a' : d3.format(C.fmt)(r[s.key]) + C.tipUnit]);
    });
    ex.push(...dots);
  }

  J.redrawGdp = () => {
    if (!visible()) return;
    usd('gdp-usd', usdPick);
    usd('gdp-pc', pcPick);
    growth();
    sectors();
    sources();
    annual('gdp-annual', [{ key: 'total', name: 'GDP', color: 'var(--ad-c2)', rows: nesdcY('total'), ytd: 'total' }]
      .concat(SEC.map(([key, name, color]) => ({ key, name, color, thin: true, rows: nesdcY(key), ytd: key }))), ['th_gdp']);
  };

  const seg = (id, attr, set) => {
    const el = document.getElementById(id);
    el.addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b) return;
      set(b.dataset[attr]);
      el.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      J.redrawGdp();
    });
  };
  seg('gdp-growth-seg', 's', (v) => { growthBasis = v; });
  seg('gdp-src-seg', 'src', (v) => { srcPick = v; });
  seg('gdp-usd-seg', 'u', (v) => { usdPick = v; });
  seg('gdp-pc-seg', 'u', (v) => { pcPick = v; });

  dash.onData(() => J.redrawGdp());
})();
