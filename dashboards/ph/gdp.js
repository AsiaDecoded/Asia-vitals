// Philippines GDP tab, Charts 1-6: PSA national accounts (2018 prices) and World Bank WDI, as published. The calcs only
// pick rows; the one calculated series (the current year's year-to-date real growth) is calculated in the pipeline and
// flagged there. CAGR on Charts 1 and 2 is calculated on this page from the WDI values drawn.

dash.calc('gdp_latest', {
  title: 'Latest GDP quarter',
  description: 'The latest quarter in the PSA quarterly national accounts, picked from the published rows.',
  inputs: ['ph_gdp'],
  fn: (ph_gdp) => {
    const q = ph_gdp.filter((r) => r.freq === 'Q' && r.code === 'gdp' && r.price === 'constant_2018' && r.measure === 'yoy')
      .sort((a, b) => (a.date < b.date ? -1 : 1));
    if (!q.length) return [];
    const a = q[q.length - 1];
    return [{ period: a.period, label: `Q${a.period.slice(-1)} ${a.period.slice(0, 4)}`, real_yoy: Number(a.value) }];
  },
});

(() => {
  const J = window.JG;
  const N = (v) => (v === '' || v == null ? null : Number(v));
  const visible = () => !document.getElementById('gdp').hidden;
  const failed = (st) => st === 'error' || st === 'connect' || st === 'declined';
  const qLab = (d) => `Q${Math.ceil(+d.slice(5, 7) / 3)} ${d.slice(0, 4)}`;
  const fmt0 = (v) => d3.format('.0f')(v);
  const SEC = [['agri', 'Agriculture, forestry and fishing', 'var(--ad-c6)'], ['industry', 'Industry', 'var(--ad-c1)'],
    ['services', 'Services', 'var(--ad-c5)']];
  const pick = { usd: 'NY.GDP.MKTP.KD', pc: 'NY.GDP.PCAP.KD', growth: 'real', src: 'psa' };

  function legend(id, series) {
    const el = document.getElementById(id); if (!el) return;
    el.replaceChildren();
    series.forEach((s) => {
      const span = document.createElement('span'), ln = document.createElement('span');
      ln.className = s.bar ? 'sw' : 'ln';
      ln.style.background = s.open ? 'transparent' : s.color;
      if (s.open) { ln.style.border = `2px solid ${s.color}`; ln.style.borderRadius = '50%'; ln.style.width = '8px'; ln.style.height = '8px'; }
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
  function frame(box, rows, H, vals, fmt, zero, mr) {
    const W = box.clientWidth;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    let lo = d3.min(vals), hi = d3.max(vals);
    if (zero) { lo = Math.min(0, lo); hi = Math.max(0, hi); }
    const y = d3.scaleLinear([lo, hi], [H - 24, 22]).nice();
    const ticks = y.ticks(5);
    const ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    const x = d3.scaleUtc([J.date(rows[0].date), J.date(rows[rows.length - 1].date)], [ml, W - mr]);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - mr).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (zero && v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
    return { svg, x, y, W, ml };
  }
  // x-axis labels at the points themselves (annual points are dated 1 December), every few years, counted from `anchor`.
  function yearAxis(svg, x, rows, H, W, ml, mr, anchor, lab) {
    const y0 = Number(rows[0].date.slice(0, 4)), y1 = Number(rows[rows.length - 1].date.slice(0, 4));
    const room = Math.max(1, Math.floor((W - ml - mr) / 44));
    const step = [1, 2, 5, 10, 20].find((k) => (y1 - y0 + 1) / k <= room) || 20;
    const seen = new Set();
    rows.forEach((r) => {
      const yr = Number(r.date.slice(0, 4)); if (seen.has(yr) || (((yr - anchor) % step) + step) % step !== 0) return;
      seen.add(yr);
      const px = x(J.date(r.date));
      svg.append('text').attr('x', px).attr('y', H - 20).attr('dy', '0.71em').attr('font-size', 12).attr('fill', 'var(--ad-ink)')
        .attr('text-anchor', px > W - mr - 16 ? 'end' : px < ml + 16 ? 'start' : 'middle').text(lab ? lab(r) : yr);
    });
  }
  function tipper(svg, card, x, rows, H, ml, right, head, lines, dots) {
    const tip = J.tip(card);
    const rule = svg.append('line').attr('y1', 8).attr('y2', H - 22).attr('stroke', 'var(--cds-chart-reference)').attr('display', 'none');
    const bis = d3.bisector((r) => J.date(r.date)).center;
    svg.append('rect').attr('x', ml).attr('width', Math.max(0, right - ml)).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const r = rows[bis(rows, x.invert(d3.pointer(ev)[0]))], px = x(J.date(r.date));
        rule.attr('display', null).attr('x1', px).attr('x2', px);
        if (dots) dots(r, px);
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, head(r), lines(r), ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); if (dots) dots(null); tip.style.display = 'none'; });
  }
  const G = () => dash.data('ph_gdp');
  // Published PSA rows for one code: [{date, period, span, v, calculated}], sorted.
  function rowsOf(freq, code, price, measure) {
    const D = G(); if (D.status !== 'ok') return [];
    return D.data.filter((r) => r.freq === freq && r.code === code && r.price === price && r.measure === measure)
      .map((r) => ({ date: r.date, period: r.period, span: r.span, v: N(r.value), calc: r.calculated === 'y' }))
      .filter((r) => r.v != null).sort((a, b) => (a.date < b.date ? -1 : 1));
  }
  const YTD_LABEL = { Q1: 'Jan–Mar', H1: 'Jan–Jun', '9M': 'Jan–Sep' };

  // Charts 1 and 2: GDP and GDP per capita in US dollars, WDI, as published. Nominal adds GNI (Atlas method): the total from
  // WDI (fetched by this page's pipeline), per capita from the central GNI dataset (data/asia/gni/asia_gni_pc.csv).
  const USD = {
    'gdp-usd': { div: 1e9, unit: 'US$ billion', tipUnit: ' bn', fmt: ',.1f', ds: ['ph_gdp_intl'],
      real: [{ key: 'NY.GDP.MKTP.KD', name: 'GDP', color: 'var(--ad-c2)' }],
      nominal: [{ key: 'NY.GDP.MKTP.CD', name: 'GDP', color: 'var(--ad-c1)' }, { key: 'NY.GNP.ATLS.CD', name: 'GNI, Atlas method', color: 'var(--ad-c2)' }] },
    'gdp-pc': { div: 1, unit: 'US$', tipUnit: '', fmt: ',.0f', ds: ['ph_gdp_intl', 'asia_gni_pc'],
      real: [{ key: 'NY.GDP.PCAP.KD', name: 'GDP per capita', color: 'var(--ad-c2)' }],
      nominal: [{ key: 'NY.GDP.PCAP.CD', name: 'GDP per capita', color: 'var(--ad-c1)' }, { key: 'gni_pc', name: 'GNI per capita, Atlas method', color: 'var(--ad-c2)' }] },
  };
  const LMI = 1987, UMI = 2025, CAGR_START = 1987;   // income-group lines and CAGR start (user, 2 Nov 2026)
  function usd(id) {
    const C = USD[id], p = pick[id === 'gdp-usd' ? 'usd' : 'pc'], nominal = /\.CD$/.test(p), S = nominal ? C.nominal : C.real;
    const box = document.getElementById(id + '-chart');
    document.getElementById(id + '-units').textContent = `${C.unit}, ${nominal ? 'current prices' : 'constant 2015 prices'}`;
    legend(id + '-legend', S.length > 1 ? S : []);
    const ds = nominal ? C.ds : ['ph_gdp_intl'];
    if (!status(box, ds)) return;
    const by = new Map();
    const put = (date, k, v) => { if (v == null) return; if (!by.has(date)) by.set(date, { date }); by.get(date)[k] = v; };
    dash.data('ph_gdp_intl').data.forEach((r) => { if (S.some((s) => s.key === r.series)) put(r.date, r.series, N(r.value) / C.div); });
    if (S.some((s) => s.key === 'gni_pc')) dash.data('asia_gni_pc').data.forEach((r) => { if (r.economy === 'PH') put(`${r.year}-12-01`, 'gni_pc', N(r.gni_pc)); });
    const rows = J.slice(Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1)), id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 300, mr = 8;
    const { svg, x, y, W, ml } = frame(box, rows, H, rows.flatMap((r) => S.map((s) => r[s.key])).filter((v) => v != null).concat([0]), (v) => d3.format(',.0f')(v), true, mr);
    yearAxis(svg, x, rows, H, W, ml, mr, LMI);
    S.forEach((s) => svg.append('path').attr('d', d3.line().defined((r) => r[s.key] != null).x((r) => x(J.date(r.date))).y((r) => y(r[s.key]))(rows))
      .attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round'));
    // Income groups: lower-middle income when the classifications began (1987 data), upper-middle income on 2025 GNI.
    const first = Number(rows[0].date.slice(0, 4)), last = Number(rows[rows.length - 1].date.slice(0, 4));
    let umX = null;
    [[LMI, 'Lower-middle income', 'start'], [UMI, 'Upper-middle income', 'end']].forEach(([yr, lab, anchor]) => {
      if (yr < first || yr > last) return;
      const lx = x(J.date(`${yr}-12-01`));
      if (yr === UMI) umX = lx;
      svg.append('line').attr('x1', lx).attr('x2', lx).attr('y1', 18).attr('y2', H - 24).attr('stroke', 'var(--ad-axis)').attr('stroke-dasharray', '3 3');
      const ax = anchor === 'start' && lx < ml + 70 ? 'start' : anchor === 'end' && lx > W - mr - 70 ? 'end' : 'middle';
      svg.append('text').attr('x', lx + (ax === 'start' ? 3 : ax === 'end' ? -3 : 0)).attr('y', 12).attr('font-size', 12).attr('fill', 'var(--ad-ink)')
        .attr('text-anchor', ax).text(lab);
    });
    // CAGR (calculated on this page): (latest-year value / 1987 value)^(1 / years) - 1, per series drawn, from the full data
    // (not the slider window); the end year moves on as WDI adds years.
    const full = Array.from(by.values());
    const cagr = S.map((s) => {
      const have = full.filter((r) => r[s.key] != null).sort((a, b) => (a.date < b.date ? -1 : 1)); if (!have.length) return null;
      const end = have[have.length - 1], a0 = have.find((r) => r.date.slice(0, 4) === String(CAGR_START));
      const yrs = Number(end.date.slice(0, 4)) - CAGR_START;
      return a0 && yrs > 0 && a0[s.key] > 0 ? { s, END: end.date.slice(0, 4), v: (Math.pow(end[s.key] / a0[s.key], 1 / yrs) - 1) * 100 } : null;
    }).filter(Boolean);
    if (cagr.length) {
      const lh = 16, tx = (umX != null ? umX : W - mr) - 8, ty = H - 40 - (cagr.length - 1) * lh;
      const t = svg.append('text').attr('font-size', 12).attr('font-weight', 700).attr('fill', 'var(--ad-ink)').attr('text-anchor', 'end');
      cagr.forEach((c, k) => t.append('tspan').attr('x', tx).attr('y', ty + k * lh).attr('fill', S.length > 1 ? c.s.color : null)
        .text(`${CAGR_START}–${c.END} CAGR: ${c.v.toFixed(1)}% p.a.`));
    }
    const card = document.getElementById(id);
    const dots = S.map((s) => svg.append('circle').attr('r', 3.5).attr('fill', s.color).attr('display', 'none'));
    tipper(svg, card, x, rows, H, ml, W - mr, (r) => r.date.slice(0, 4),
      (r) => S.map((s) => [s.color, s.name, r[s.key] == null ? 'n/a' : d3.format(C.fmt)(r[s.key]) + C.tipUnit]),
      (r, px) => S.forEach((s, k) => (!r || r[s.key] == null ? dots[k].attr('display', 'none') : dots[k].attr('display', null).attr('cx', px).attr('cy', y(r[s.key])))));
  }

  // Chart 3: GDP growth against the same quarter a year earlier, from Q1 1982, PSA as published (real: 2018 prices;
  // nominal: current prices).
  function growth() {
    const id = 'gdp-growth', box = document.getElementById(id + '-chart');
    if (!status(box, ['ph_gdp'])) return;
    const real = pick.growth === 'real';
    const rows = J.slice(rowsOf('Q', 'gdp', real ? 'constant_2018' : 'current', 'yoy'), id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 300, mr = 8;
    const { svg, x, y, W, ml } = frame(box, rows, H, rows.map((r) => r.v), fmt0, true, mr);
    yearAxis(svg, x, rows.filter((r) => r.date.slice(5, 7) === '03'), H, W, ml, mr, 2000);
    const step = (W - ml - mr) / Math.max(1, rows.length), bw = Math.max(1, Math.min(22, step * 0.7));
    const col = real ? 'var(--ad-c2)' : 'var(--ad-c1)';
    rows.forEach((r) => svg.append('rect').attr('x', x(J.date(r.date)) - bw / 2).attr('width', bw)
      .attr('y', y(Math.max(0, r.v))).attr('height', Math.abs(y(r.v) - y(0))).attr('fill', col));
    tipper(svg, document.getElementById(id), x, rows, H, ml, W - mr, (r) => qLab(r.date),
      (r) => [[col, real ? 'Real GDP, y/y' : 'Nominal GDP, y/y', r.v.toFixed(1) + '%']]);
  }

  // Chart 4: real growth by sector, y/y, from Q1 1982, PSA as published.
  function sectors() {
    const id = 'gdp-sectors', box = document.getElementById(id + '-chart');
    const S = SEC.map(([key, name, color]) => ({ key, name, color }));
    legend(id + '-legend', S);
    if (!status(box, ['ph_gdp'])) return;
    const by = new Map();
    S.forEach((s) => rowsOf('Q', s.key, 'constant_2018', 'yoy').forEach((r) => { if (!by.has(r.date)) by.set(r.date, { date: r.date }); by.get(r.date)[s.key] = r.v; }));
    const rows = J.slice(Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1)), id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 300, mr = 8;
    const { svg, x, y, W, ml } = frame(box, rows, H, rows.flatMap((r) => S.map((s) => r[s.key])).filter((v) => v != null), fmt0, true, mr);
    yearAxis(svg, x, rows.filter((r) => r.date.slice(5, 7) === '03'), H, W, ml, mr, 2000);
    S.forEach((s) => svg.append('path').attr('d', d3.line().defined((r) => r[s.key] != null).x((r) => x(J.date(r.date))).y((r) => y(r[s.key]))(rows))
      .attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', 1.75).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round'));
    const dots = S.map((s) => svg.append('circle').attr('r', 3.5).attr('fill', s.color).attr('display', 'none'));
    tipper(svg, document.getElementById(id), x, rows, H, ml, W - mr, (r) => qLab(r.date),
      (r) => S.map((s) => [s.color, s.name, r[s.key] == null ? 'n/a' : r[s.key].toFixed(1) + '%']),
      (r, px) => S.forEach((s, k) => (!r || r[s.key] == null ? dots[k].attr('display', 'none') : dots[k].attr('display', null).attr('cx', px).attr('cy', y(r[s.key])))));
  }

  // Annual lines with the current year's year-to-date point (calculated in the pipeline from PSA's quarterly levels).
  function annualChart(id, S, ids, rowsFor) {
    const box = document.getElementById(id + '-chart');
    if (!status(box, ids)) { legend(id + '-legend', []); return; }
    const by = new Map();
    const put = (date, k, v) => { if (v == null) return; if (!by.has(date)) by.set(date, { date }); by.get(date)[k] = v; };
    let ytdSpan = null;
    S.forEach((s) => rowsFor(s).forEach((r) => {
      if (r.span === 'Y' || r.span == null) put(r.date, s.key, r.v); else { put(r.date, s.key + '_ytd', r.v); ytdSpan = r.span; }
    }));
    // a YTD point only for a year with no annual figure
    Array.from(by.values()).forEach((r) => S.forEach((s) => { if (r[s.key] != null) delete r[s.key + '_ytd']; }));
    const all = Array.from(by.values()).filter((r) => S.some((s) => r[s.key] != null || r[s.key + '_ytd'] != null)).sort((a, b) => (a.date < b.date ? -1 : 1));
    const rows = J.slice(all, id);
    const ytdYear = rows.length && S.some((s) => rows[rows.length - 1][s.key + '_ytd'] != null) ? rows[rows.length - 1].date.slice(0, 4) : null;
    const ytdName = ytdYear ? `${YTD_LABEL[ytdSpan] || 'Year to date'} ${ytdYear} (calculated)` : '';
    legend(id + '-legend', (S.length > 1 ? S : []).concat(ytdYear ? [{ name: `YTD: ${ytdName}`, color: 'var(--ad-ink)', open: true }] : []));
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 300, mr = 8;
    const { svg, x, y, W, ml } = frame(box, rows, H, rows.flatMap((r) => S.flatMap((s) => [r[s.key], r[s.key + '_ytd']])).filter((v) => v != null), fmt0, true, mr);
    const lastYr = Number(rows[rows.length - 1].date.slice(0, 4));
    yearAxis(svg, x, rows, H, W, ml, mr, lastYr, (r) => (S.every((s) => r[s.key] == null) ? 'YTD' : r.date.slice(0, 4)));
    S.forEach((s) => svg.append('path').attr('d', d3.line().defined((r) => r[s.key] != null).x((r) => x(J.date(r.date))).y((r) => y(r[s.key]))(rows))
      .attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', s.thin ? 1.75 : 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round'));
    rows.forEach((r) => S.forEach((s) => {
      const v = r[s.key + '_ytd']; if (v == null) return;
      svg.append('circle').attr('cx', x(J.date(r.date))).attr('cy', y(v)).attr('r', 4.5).attr('fill', 'var(--color-panel)').attr('stroke', s.color).attr('stroke-width', 2);
    }));
    const isYtd = (r) => S.every((s) => r[s.key] == null);
    tipper(svg, document.getElementById(id), x, rows, H, ml, W - mr, (r) => (isYtd(r) ? `YTD: ${ytdName}` : r.date.slice(0, 4)),
      (r) => S.map((s) => { const v = isYtd(r) ? r[s.key + '_ytd'] : r[s.key]; return [s.color, s.name, v == null ? 'n/a' : v.toFixed(isYtd(r) ? 2 : 1) + '%']; }));
  }
  // Chart 5: real GDP growth, annual: PSA (1947 on) or the World Bank's WDI (1961 on); YTD from PSA in both views.
  function sources() {
    const id = 'gdp-src', psa = pick.src === 'psa';
    const S = [{ key: 'v', name: psa ? 'PSA' : 'World Bank', color: 'var(--ad-c2)' }];
    annualChart(id, S, ['ph_gdp', 'ph_gdp_intl'], () => {
      const ytd = rowsOf('A', 'gdp', 'constant_2018', 'yoy').filter((r) => r.span !== 'Y');
      if (psa) return rowsOf('A', 'gdp', 'constant_2018', 'yoy');
      return dash.data('ph_gdp_intl').data.filter((r) => r.series === 'NY.GDP.MKTP.KD.ZG')
        .map((r) => ({ date: r.date, span: 'Y', v: N(r.value) })).concat(ytd);
    });
  }
  // Chart 6: real growth by sector, annual, PSA, 1947 on (agriculture from 1948), with GDP.
  function annualSectors() {
    const S = [{ key: 'gdp', name: 'GDP', color: 'var(--ad-c2)' }].concat(SEC.map(([key, name, color]) => ({ key, name, color, thin: true })));
    annualChart('gdp-annual', S, ['ph_gdp'], (s) => rowsOf('A', s.key, 'constant_2018', 'yoy'));
  }

  function pageHead() {
    const L = dash.data('gdp_latest'), el = document.getElementById('gdp-q');
    if (!el) return;
    el.textContent = L.status === 'ok' && L.data[0] ? L.data[0].label : '—';
    el.classList.toggle('dash-skeleton', L.status !== 'ok');
  }

  const segs = [['gdp-usd-seg', 'u', (v) => { pick.usd = v; }], ['gdp-pc-seg', 'u', (v) => { pick.pc = v; }],
    ['gdp-growth-seg', 's', (v) => { pick.growth = v; }], ['gdp-src-seg', 'src', (v) => { pick.src = v; }]];
  segs.forEach(([segId, attr, set]) => {
    const seg = document.getElementById(segId); if (!seg) return;
    seg.addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b) return;
      set(b.dataset[attr]);
      seg.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      J.redrawGdp();
    });
  });

  J.redrawGdp = () => {
    pageHead();
    if (!visible()) return;
    usd('gdp-usd'); usd('gdp-pc'); growth(); sectors(); sources(); annualSectors();
  };
  dash.onData(() => J.redrawGdp());
})();
