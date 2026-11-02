// Vietnam GDP tab: GDP by industry (current and constant prices) and the industrial production index by VSIC
// division, as published by NSO. Nothing here calculates a figure: the calcs only pick rows and reshape them
// (levels are shown in VND trillion, NSO's VND billion / 1,000).

dash.calc('gdp_latest', {
  title: 'Latest GDP quarter',
  description: 'NSO real GDP and manufacturing figures for the latest quarter and the one before, picked from the published rows.',
  inputs: ['vn_gdp', 'vn_iip'],
  fn: (vn_gdp, vn_iip) => {
    const N = (v) => (v === '' || v == null ? null : Number(v));
    const pick = (code, priceKind, measure, span) => vn_gdp
      .filter((r) => r.code === code && String(r.price).startsWith(priceKind) && r.measure === measure && r.span === span)
      .sort((a, b) => (a.date < b.date ? -1 : 1));
    const real = pick('total', 'constant', 'yoy', 'Q');
    if (!real.length) return [];
    const a = real[real.length - 1], b = real.length > 1 ? real[real.length - 2] : null;
    const q = Number(a.period.slice(-1)), y = a.period.slice(0, 4);
    const ytdSpan = ({ 1: 'Q', 2: '6M', 3: '9M', 4: 'Y' })[q];
    const at = (rows, period) => { const r = rows.find((x) => x.period === period); return r || null; };
    const ytdPeriod = ({ 1: `${y}-Q1`, 2: `${y}-H1`, 3: `${y}-9M`, 4: y })[q];
    const ytd = at(pick('total', 'constant', 'yoy', ytdSpan), ytdPeriod);
    const mfg = pick('manufacturing', 'constant', 'yoy', 'Q'), sh = pick('manufacturing', 'current', 'share', 'Q');
    const nom = pick('total', 'current', 'level', 'Q'), nomY = at(pick('total', 'current', 'level', ytdSpan), ytdPeriod);
    const iip = vn_iip.filter((r) => r.code === 'c').sort((x, z) => (x.date < z.date ? -1 : 1));
    const iA = iip.find((r) => r.period === a.period), iB = b ? iip.find((r) => r.period === b.period) : null;
    const ST = { estimate: 'NSO estimate', preliminary: 'preliminary' };
    return [{
      period: a.period, prev_period: b ? b.period : '', date: a.date,
      label: `Q${q} ${y}${ST[a.status] ? ' (' + ST[a.status] + ')' : ''}`,
      real_yoy: N(a.rate), real_yoy_prev: b ? N(b.rate) : null,
      real_ytd: ytd ? N(ytd.rate) : null, ytd_label: ({ 1: 'first quarter', 2: 'first half', 3: 'first nine months', 4: 'full year' })[q] + ' ' + y,
      mfg_yoy: N((at(mfg, a.period) || {}).rate), mfg_yoy_prev: b ? N((at(mfg, b.period) || {}).rate) : null,
      mfg_share: N((at(sh, a.period) || {}).value), mfg_share_prev: b ? N((at(sh, b.period) || {}).value) : null,
      iip_mfg: iA ? N(iA.rate) : null, iip_mfg_prev: iB ? N(iB.rate) : null,
      nominal_trn: at(nom, a.period) ? N(at(nom, a.period).value) / 1000 : null, nominal_ytd_trn: nomY ? N(nomY.value) / 1000 : null,
    }];
  },
});

dash.calc('gdp_table', {
  title: 'GDP by industry, latest quarter',
  description: 'NSO GDP by industry for the latest quarter: current-price level (VND trillion), % of GDP, real y/y, prior quarter and year to date, picked from the published rows.',
  inputs: ['vn_gdp'],
  fn: (vn_gdp) => {
    const N = (v) => (v === '' || v == null ? null : Number(v));
    const real = vn_gdp.filter((r) => r.code === 'total' && String(r.price).startsWith('constant') && r.measure === 'yoy' && r.span === 'Q')
      .sort((a, b) => (a.date < b.date ? -1 : 1));
    if (!real.length) return [];
    const p = real[real.length - 1].period, pp = real.length > 1 ? real[real.length - 2].period : '';
    const q = Number(p.slice(-1)), y = p.slice(0, 4);
    const ytdP = ({ 1: `${y}-Q1`, 2: `${y}-H1`, 3: `${y}-9M`, 4: y })[q];
    const get = (code, priceKind, measure, period) => vn_gdp.find((r) => r.code === code && String(r.price).startsWith(priceKind) && r.measure === measure && r.period === period);
    const codes = []; vn_gdp.forEach((r) => { if (r.period === p && r.span === 'Q' && !codes.includes(r.code)) codes.push(r.code); });
    return codes.map((code) => {
      const any = get(code, 'current', 'level', p) || {};
      const lv = get(code, 'current', 'level', p), sh = get(code, 'current', 'share', p);
      const ry = get(code, 'constant', 'yoy', p), rp = pp ? get(code, 'constant', 'yoy', pp) : null, rt = get(code, 'constant', 'yoy', ytdP);
      return { code, period: p, industry: any.industry, isic: any.isic, level: Number(any.level),
        nominal_trn: lv ? N(lv.value) / 1000 : null, share: sh ? N(sh.value) : null,
        real_yoy: ry ? N(ry.rate) : null, real_yoy_prev: rp ? N(rp.rate) : null, real_ytd: rt ? N(rt.rate) : null };
    });
  },
});

(() => {
  const J = window.JG;
  const V = J.vn;
  const { legend, frame, hover, status, failed, win, qLab, f2, num, fmt0 } = V;
  const visible = () => !document.getElementById('gdp').hidden;
  const mfgVisible = () => !document.getElementById('manufacturing').hidden;
  const REBASE = '2026-03-01';   // first quarter on 2020 constant prices (and the revised current-price scale)
  const REVAL = '2021-03-01';    // first quarter on the scale after NSO's 2021 revaluation (levels only)
  const SPAN_YTD = { 3: 'Q', 6: '6M', 9: '9M', 12: 'Y' };
  const SEC = [['agri', 'Agriculture, forestry and fishing', 'var(--ad-c6)'], ['ind_constr', 'Industry and construction', 'var(--ad-c1)'],
    ['services', 'Services', 'var(--ad-c5)'], ['taxes', 'Taxes on products less subsidies', 'var(--ad-c4)']];
  let growthBasis = 'real', levelBasis = 'current', srcPick = 'nso', usdPick = 'NY.GDP.MKTP.KD', pcPick = 'NY.GDP.PCAP.KD';
  ['gdp-sectors', 'gdp-structure', 'gdp-mfg', 'gdp-mfg-share', 'gdp-exp', 'gdp-exp-share'].forEach((id) => { J.period[id] = 0; });

  const G = () => dash.data('vn_gdp');
  // Published quarterly rows for one industry: [{date, v, price, status, period}], sorted.
  function series(code, priceKind, measure, span = 'Q', field) {
    const D = G(); if (D.status !== 'ok') return [];
    return D.data.filter((r) => r.code === code && String(r.price).startsWith(priceKind) && r.measure === measure && r.span === span)
      .map((r) => ({ date: r.date, period: r.period, price: r.price, status: r.status, v: num(field ? r[field] : (measure === 'yoy' ? r.rate : r.value)) }))
      .filter((r) => r.v != null).sort((a, b) => (a.date < b.date ? -1 : 1));
  }
  // Year to date: each quarter's three-, six-, nine- or twelve-month figure, dated at the quarter.
  function ytdSeries(code) {
    const D = G(); if (D.status !== 'ok') return [];
    return D.data.filter((r) => r.code === code && String(r.price).startsWith('constant') && r.measure === 'yoy' && SPAN_YTD[Number(r.date.slice(5, 7))] === r.span)
      .map((r) => ({ date: r.date, v: num(r.rate), period: r.period, price: r.price })).filter((r) => r.v != null).sort((a, b) => (a.date < b.date ? -1 : 1));
  }
  function merge(list) {   // [{key, rows}] -> [{date, q: true, <key>: v}]
    const by = new Map();
    list.forEach(({ key, rows }) => rows.forEach((r) => { if (!by.has(r.date)) by.set(r.date, { date: r.date, q: true }); by.get(r.date)[key] = r.v; }));
    return Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
  }
  function rebaseLine(svg, x, rows, H, levels) {
    (levels === 'nominal' ? [REVAL] : levels ? [REVAL, REBASE] : [REBASE]).forEach((b) => {
      if (rows[0].date < b && rows[rows.length - 1].date >= b) {
        const sx = x(J.date(b.slice(0, 5) + '01-01'));
        svg.append('line').attr('x1', sx).attr('x2', sx).attr('y1', 12).attr('y2', H - 24).attr('stroke', 'var(--ad-axis)').attr('stroke-dasharray', '3 3');
      }
    });
  }

  function qLines(cardId, S, opt = {}) {
    const box = document.getElementById(cardId + '-chart');
    legend(cardId + '-legend', S);
    if (!status(box, opt.ds || ['vn_gdp'])) return;
    const all = merge(S.map((s) => ({ key: s.key, rows: s.rows }))).filter((r) => !opt.start || r.date >= opt.start);
    const rows = win(all, cardId);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = opt.H || 280, mr = 8;
    const fmt = opt.fmt || fmt0;
    const { svg, x, y, W, ml } = frame(box, rows, H, rows.flatMap((r) => S.map((s) => r[s.key])).filter((v) => v != null), fmt, opt.zero !== false, mr);
    rebaseLine(svg, x, rows, H, opt.levels);
    S.forEach((s) => {
      svg.append('path').attr('d', d3.line().defined((r) => r[s.key] != null).x((r) => x(J.date(r.date))).y((r) => y(r[s.key]))(rows))
        .attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', s.thin ? 1.75 : 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round')
        .attr('stroke-dasharray', s.dash ? '6 4' : null);
    });
    const card = document.getElementById(cardId);
    const dots = S.map((s) => svg.append('circle').attr('r', 3.5).attr('fill', s.color).attr('display', 'none'));
    const extras = hover(svg, card, x, rows, H, ml, W - mr, (r, px) => {
      dots.forEach((d, i) => { const v = r[S[i].key]; d.attr('display', v == null ? 'none' : null).attr('cx', px).attr('cy', v == null ? 0 : y(v)); });
      return S.filter((s) => r[s.key] != null || !s.hideNull).map((s) => [s.color, s.name, r[s.key] == null ? 'n/a' : (opt.tipFmt || ((v) => v.toFixed(2) + '%'))(r[s.key])]);
    });
    extras.push(...dots);
  }

  // Chart 3: quarterly real growth (bars), or the year-to-date figure.
  // Base periods of NSO's constant prices: a dashed line where the base changes, labelled with the new base.
  const BASE_LABEL = (price) => (/constant_(\d{4})/.exec(price) || [])[1] ? `${/constant_(\d{4})/.exec(price)[1]} prices` : '';
  function baseMarks(svg, x, rows, H) {
    for (let k = 1; k < rows.length; k += 1) {
      if (!rows[k].price || !rows[k - 1].price || rows[k].price === rows[k - 1].price) continue;
      const sx = (x(J.date(rows[k - 1].date)) + x(J.date(rows[k].date))) / 2;
      svg.append('line').attr('x1', sx).attr('x2', sx).attr('y1', 14).attr('y2', H - 24).attr('stroke', 'var(--ad-axis)').attr('stroke-dasharray', '3 3');
      svg.append('text').attr('x', sx).attr('y', 10).attr('text-anchor', 'middle').attr('font-size', 11)
        .attr('fill', 'var(--ad-ink)').text(BASE_LABEL(rows[k].price));
    }
  }

  const START = '2018-01-01';   // Chart 3 from 2018 (single quarters in NSO's tables from Q2 2018)

  // Chart 3: GDP growth on the same quarter a year earlier, single quarters from 2018. Real: NSO's, as published on
  // each base (dashed line at a base change). Nominal: calculated in the pipeline from NSO's current-price levels.
  function growth() {
    const id = 'gdp-growth', box = document.getElementById(id + '-chart');
    if (!status(box, ['vn_gdp'])) return;
    const src = series('total', growthBasis === 'real' ? 'constant' : 'current', 'yoy').filter((r) => r.date >= START);
    const rows = J.slice(src.map((r) => ({ date: r.date, q: true, v: r.v, price: r.price, period: r.period })), id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280, mr = 8;
    const { svg, x, y, W, ml } = frame(box, rows, H, rows.map((r) => r.v), (v) => d3.format('.0f')(v), true, mr);
    if (growthBasis === 'real') baseMarks(svg, x, rows, H);
    const step = (W - ml - mr) / Math.max(1, rows.length);
    const bw = Math.max(1.5, Math.min(22, step * 0.62));
    const col = growthBasis === 'real' ? 'var(--ad-c2)' : 'var(--ad-c1)';
    rows.forEach((r) => {
      svg.append('rect').attr('x', x(J.date(r.date)) - bw / 2).attr('width', bw).attr('y', y(Math.max(0, r.v))).attr('height', Math.abs(y(r.v) - y(0)))
        .attr('fill', col);
    });
    const card = document.getElementById(id);
    hover(svg, card, x, rows, H, ml, W - mr, (r) => (growthBasis === 'real'
      ? [[col, 'Real GDP, y/y', r.v.toFixed(2) + '%'], [null, 'Prices of', BASE_LABEL(r.price).replace(' prices', '')]]
      : [[col, 'Nominal GDP, y/y (calculated)', r.v.toFixed(2) + '%']]));
  }

  // Chart 7: published shares of GDP at current prices, stacked.
  function structure() {
    const id = 'gdp-structure', box = document.getElementById(id + '-chart');
    const S = SEC.map(([code, name, color]) => ({ code, name, color, bar: true }));
    legend(id + '-legend', S.slice().reverse());
    if (!status(box, ['vn_gdp'])) return;
    const all = merge(S.map((s) => ({ key: s.code, rows: series(s.code, 'current', 'share') }))).filter((r) => S.every((s) => r[s.code] != null));
    const rows = win(all, id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280, mr = 8;
    const { svg, x, y, W, ml } = frame(box, rows, H, [0, 100], (v) => d3.format('.0f')(v), true, mr);
    rebaseLine(svg, x, rows, H);
    const step = (W - ml - mr) / Math.max(1, rows.length);
    const bw = Math.max(2, Math.min(22, step * 0.7));
    rows.forEach((r) => {
      let base = 0;
      S.forEach((s) => {
        const v = r[s.code];
        svg.append('rect').attr('x', x(J.date(r.date)) - bw / 2).attr('width', bw).attr('y', y(base + v)).attr('height', Math.max(0, y(base) - y(base + v))).attr('fill', s.color);
        base += v;
      });
    });
    const card = document.getElementById(id);
    hover(svg, card, x, rows, H, ml, W - mr, (r) => S.slice().reverse().map((s) => [s.color, s.name, r[s.code].toFixed(2) + '%']));
  }

  // Table: GDP by industry, latest quarter.
  function indTable() {
    const tb = document.querySelector('#gdp-ind-table tbody');
    const T = dash.data('gdp_table');
    if (failed(T.status)) { tb.replaceChildren(); const td = tb.insertRow().insertCell(); td.colSpan = 7; J.fail(td); return; }
    if (T.status !== 'ok' || !T.data.length) return;
    document.getElementById('gdp-ind-q').textContent = qLab(`${T.data[0].period.slice(0, 4)}-${String(Number(T.data[0].period.slice(-1)) * 3).padStart(2, '0')}-01`);
    tb.replaceChildren();
    const fx = (v, d = 1) => (v == null ? '' : v.toFixed(d));
    T.data.forEach((r) => {
      const tr = tb.insertRow(); tr.dataset.key = r.code;
      if (r.level <= 1) tr.className = r.level === 0 ? 'gdp' : 'sep';
      [r.industry, r.isic, r.nominal_trn == null ? '' : d3.format(',.1f')(r.nominal_trn), fx(r.share), fx(r.real_yoy, 2), fx(r.real_yoy_prev, 2), fx(r.real_ytd, 2)].forEach((v, i) => {
        const td = tr.insertCell(); td.textContent = v;
        if (i === 0 && r.level >= 2) td.style.paddingLeft = r.level === 3 ? '2.2rem' : '1.1rem';
        if (i === 1) td.className = 'hide-narrow';
        if (i === 5) td.className = 'hide-narrow';
        if (i >= 4 && v.startsWith('-')) td.classList.add('neg');
      });
    });
  }

  const STOPS = [[0, [99, 190, 123]], [0.5, [255, 235, 132]], [1, [248, 105, 107]]];
  const heatColor = (t) => {
    const i = t > 0.5 ? 1 : 0; const [t0, c0] = STOPS[i], [t1, c1] = STOPS[i + 1], f = (t - t0) / (t1 - t0);
    return `rgb(${c0.map((c, k) => Math.round(c + (c1[k] - c) * f)).join(',')})`;
  };
  // Heat table: rows [{key, name, cls, vals: Map(date -> v)}], last 12 quarters.
  function heat(tblId, rowsDef, dates) {
    const tbl = document.getElementById(tblId);
    tbl.replaceChildren();
    const head = tbl.createTHead().insertRow();
    [''].concat(dates.map((d) => `Q${Math.ceil(+d.slice(5, 7) / 3)} ${d.slice(2, 4)}`)).forEach((t) => { const th = document.createElement('th'); th.textContent = t; head.appendChild(th); });
    const tb = tbl.createTBody();
    rowsDef.forEach(({ name, cls, vals, indent }) => {
      const vs = dates.map((d) => vals.get(d)).filter((v) => v != null);
      if (!vs.length) return;
      const tr = tb.insertRow(); if (cls) tr.className = cls;
      const c0 = tr.insertCell(); c0.textContent = name; if (indent) c0.style.paddingLeft = `${indent * 1.1}rem`;
      const lo = Math.min(...vs), hi = Math.max(...vs);
      dates.forEach((d) => {
        const td = tr.insertCell(); const v = vals.get(d);
        if (v == null) return;
        td.textContent = J.f1(v) === '-0.0' ? '0.0' : J.f1(v);
        td.className = 'heat'; td.style.background = heatColor(hi > lo ? (v - lo) / (hi - lo) : 0.5); td.style.color = '#1a1a1a';
      });
    });
  }
  function gdpHeat() {
    const D = G(); const tbl = document.getElementById('gdp-heat-table');
    if (failed(D.status)) { tbl.replaceChildren(); return; }
    if (D.status !== 'ok') return;
    const rows = D.data.filter((r) => r.span === 'Q' && String(r.price).startsWith('constant') && r.measure === 'yoy');
    const dates = Array.from(new Set(rows.filter((r) => r.code === 'total').map((r) => r.date))).sort().slice(-12);
    const codes = []; rows.forEach((r) => { if (!codes.find((c) => c.code === r.code)) codes.push({ code: r.code, name: r.industry, level: Number(r.level) }); });
    heat('gdp-heat-table', codes.map((c) => ({
      name: c.name, cls: c.level === 0 ? 'lead' : (c.level === 1 ? 'grp1' : ''), indent: Math.max(0, c.level - 1),
      vals: new Map(rows.filter((r) => r.code === c.code && dates.includes(r.date)).map((r) => [r.date, num(r.rate)])),
    })), dates);
  }
  function iipHeat() {
    const D = dash.data('vn_iip'); const tbl = document.getElementById('iip-heat-table');
    if (failed(D.status)) { tbl.replaceChildren(); return; }
    if (D.status !== 'ok') return;
    const dates = Array.from(new Set(D.data.filter((r) => r.code === 'all').map((r) => r.date))).sort().slice(-12);
    const codes = []; D.data.forEach((r) => { if (!codes.find((c) => c.code === r.code)) codes.push({ code: r.code, name: (r.vsic && /^\d/.test(r.vsic) ? r.vsic + ' ' : '') + r.industry, level: Number(r.level) }); });
    heat('iip-heat-table', codes.map((c) => ({
      name: c.name, cls: c.level === 0 ? 'lead' : (c.level === 1 ? 'grp1' : ''), indent: c.level === 2 ? 1 : 0,
      vals: new Map(D.data.filter((r) => r.code === c.code && dates.includes(r.date)).map((r) => [r.date, num(r.rate)])),
    })), dates);
  }

  // Chart 7: IIP y/y by manufacturing division, latest quarter.
  function iipBars() {
    const id = 'iip-div', box = document.getElementById(id + '-chart');
    if (!status(box, ['vn_iip'])) return;
    const D = dash.data('vn_iip').data;
    const last = D.reduce((m, r) => (r.date > m ? r.date : m), '');
    const tot = D.find((r) => r.date === last && r.code === 'c');
    const rows = D.filter((r) => r.date === last && /^c\d\d$/.test(r.code) && num(r.rate) != null)
      .map((r) => ({ name: `${r.vsic} ${r.industry}`, v: num(r.rate) })).sort((a, b) => b.v - a.v);
    document.getElementById(id + '-units').textContent = `industrial production index, % y/y, ${qLab(last)}; manufacturing ${tot ? Number(tot.rate).toFixed(1) + '%' : 'n/a'}`;
    if (!rows.length) { box.replaceChildren(); return; }
    const W = box.clientWidth, rh = 18, H = rows.length * rh + 28;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const lw = Math.min(W * 0.5, J.textWidth(svg, rows.map((r) => r.name)) + 10);
    const x = d3.scaleLinear([Math.min(0, d3.min(rows, (r) => r.v)), Math.max(0, d3.max(rows, (r) => r.v))], [lw, W - 34]).nice();
    const ticks = x.ticks(5);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', x).attr('x2', x).attr('y1', 4).attr('y2', H - 22)
      .attr('stroke', (v) => (v === 0 ? 'var(--cds-chart-reference)' : 'var(--ad-grid)'));
    if (tot) {
      const tx = x(Number(tot.rate));
      svg.append('line').attr('x1', tx).attr('x2', tx).attr('y1', 4).attr('y2', H - 22).attr('stroke', 'var(--ad-c2)').attr('stroke-dasharray', '4 3');
    }
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 18})`).call(d3.axisBottom(x).tickValues(ticks).tickSize(0).tickFormat(fmt0)));
    const card = document.getElementById(id), tip = J.tip(card);
    rows.forEach((r, i) => {
      const yy = 6 + i * rh;
      svg.append('text').attr('x', lw - 6).attr('y', yy + rh / 2 + 1).attr('text-anchor', 'end').attr('dominant-baseline', 'middle')
        .attr('font-size', 11.5).attr('fill', 'var(--ad-ink)').text(r.name);
      const b = svg.append('rect').attr('x', x(Math.min(0, r.v))).attr('width', Math.max(1, Math.abs(x(r.v) - x(0))))
        .attr('y', yy + 2).attr('height', rh - 5).attr('fill', r.v < 0 ? 'var(--ad-c1)' : 'var(--ad-c8)');
      svg.append('text').attr('x', r.v < 0 ? x(r.v) - 3 : x(r.v) + 3).attr('y', yy + rh / 2 + 1).attr('dominant-baseline', 'middle')
        .attr('text-anchor', r.v < 0 ? 'end' : 'start').attr('font-size', 11).attr('fill', 'var(--ad-ink)').text(J.f1(r.v));
      b.on('mousemove', (ev) => { const cr = card.getBoundingClientRect(); J.showTip(card, tip, r.name, [[null, 'IIP, y/y', r.v.toFixed(2) + '%']], ev.clientX - cr.left, ev.clientY - cr.top); })
        .on('mouseleave', () => { tip.style.display = 'none'; });
    });
  }

  // Annual (yearbook) rows: [{date, v}] for one table, item, price and measure.
  function annual(table, code, price, measure) {
    const D = dash.data('vn_gdp_annual'); if (D.status !== 'ok') return [];
    return D.data.filter((r) => r.table === table && r.code === code && r.price === price && r.measure === measure)
      .map((r) => ({ date: r.date, v: num(measure === 'yoy' ? r.rate : r.value), status: r.status })).filter((r) => r.v != null)
      .sort((a, b) => (a.date < b.date ? -1 : 1));
  }
  function aLines(cardId, S, opt = {}) {
    const box = document.getElementById(cardId + '-chart');
    legend(cardId + '-legend', S);
    if (!status(box, ['vn_gdp_annual'])) return;
    const by = new Map();
    S.forEach((s) => s.rows.forEach((r) => { if (!by.has(r.date)) by.set(r.date, { date: r.date }); by.get(r.date)[s.key] = r.v; }));
    // opt.ytd: each series' latest year-to-date real growth (NSO's quarterly tables, s.code) for the year after its last
    // annual figure, an open circle at that year; the x-axis runs on to it and labels it YTD (as in Charts 1 and 3).
    const ytd = {};
    if (opt.ytd) S.forEach((s) => {
      const last = Math.max(...s.rows.map((r) => Number(r.date.slice(0, 4))));
      const y = ytdSeries(s.code).filter((r) => Number(r.date.slice(0, 4)) > last && r.period.slice(5) !== '').pop();
      if (!y) return; const d = `${y.date.slice(0, 4)}-12-01`; ytd[s.key] = y;
      if (!by.has(d)) by.set(d, { date: d }); by.get(d)[s.key + '_ytd'] = y.v;
    });
    const sorted = Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
    const rows = opt.ytd ? sorted : win(sorted, cardId);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280, mr = 8;
    const { svg, x, y, W, ml } = frame(box, rows, H, rows.flatMap((r) => S.flatMap((s) => [r[s.key], r[s.key + '_ytd']])).filter((v) => v != null), fmt0, opt.zero !== false, mr);
    const isYtd = (r) => S.every((s) => r[s.key] == null) && S.some((s) => r[s.key + '_ytd'] != null);
    if (opt.ytd) {
      svg.selectAll(`g[transform="translate(0,${H - 20})"]`).remove();
      const n = rows.length, room = Math.max(1, Math.floor((W - ml - mr) / 44));
      const stepY = [1, 2, 5, 10].find((k) => n / k <= room) || 10;
      rows.forEach((r, k) => {
        if ((n - 1 - k) % stepY !== 0) return;
        const px = x(J.date(r.date));
        svg.append('text').attr('x', px).attr('y', H - 20).attr('dy', '0.71em').attr('font-size', 12).attr('fill', 'var(--ad-ink)')
          .attr('text-anchor', px > W - mr - 16 ? 'end' : px < ml + 16 ? 'start' : 'middle').text(isYtd(r) ? 'YTD' : r.date.slice(0, 4));
      });
    }
    const bar = S.find((s) => s.bar);
    if (bar) {
      const step = (W - ml - mr) / Math.max(1, rows.length), bw = Math.max(2, Math.min(22, step * 0.62));
      rows.forEach((r) => { const v = r[bar.key]; if (v == null) return; svg.append('rect').attr('x', x(J.date(r.date)) - bw / 2).attr('width', bw).attr('y', y(Math.max(0, v))).attr('height', Math.abs(y(v) - y(0))).attr('fill', bar.color); });
    }
    S.filter((s) => !s.bar).forEach((s) => {
      svg.append('path').attr('d', d3.line().defined((r) => r[s.key] != null).x((r) => x(J.date(r.date))).y((r) => y(r[s.key]))(rows))
        .attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', s.thin ? 1.75 : 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round')
        .attr('stroke-dasharray', s.dash ? '6 4' : null);
    });
    S.forEach((s) => rows.filter((r) => r[s.key + '_ytd'] != null).forEach((r) => {
      svg.append('circle').attr('cx', x(J.date(r.date))).attr('cy', y(r[s.key + '_ytd'])).attr('r', s.thin ? 3.5 : 4.5)
        .attr('fill', 'var(--color-panel)').attr('stroke', s.color).attr('stroke-width', 2);
    }));
    const YTD_LABEL = { Q1: 'Jan–Mar', H1: 'Jan–Jun', '9M': 'Jan–Sep' };
    const card = document.getElementById(cardId);
    const tip = J.tip(card);
    const rule = svg.append('line').attr('y1', 8).attr('y2', H - 22).attr('stroke', 'var(--cds-chart-reference)').attr('display', 'none');
    const bis = d3.bisector((r) => J.date(r.date)).center;
    svg.append('rect').attr('x', ml).attr('width', Math.max(0, W - mr - ml)).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [mx] = d3.pointer(ev); const r = rows[bis(rows, x.invert(mx))]; const px = x(J.date(r.date));
        rule.attr('display', null).attr('x1', px).attr('x2', px);
        const cr = card.getBoundingClientRect();
        const head = isYtd(r) ? (() => { const y0 = Object.values(ytd)[0]; return `YTD (${YTD_LABEL[y0.period.slice(5)] || 'year to date'} ${r.date.slice(0, 4)}, ${String(y0.price).replace('constant_', '')} prices)`; })() : r.date.slice(0, 4);
        J.showTip(card, tip, head, S.map((s) => { const v = isYtd(r) ? r[s.key + '_ytd'] : r[s.key]; return [s.color, s.name, v == null ? 'n/a' : v.toFixed(2) + '%']; }), ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); tip.style.display = 'none'; });
  }


  // Chart 5: real GDP growth, annual: NSO's yearbook and the World Bank's WDI.
  function sources() {
    const id = 'gdp-src', box = document.getElementById(id + '-chart');
    const S = [{ key: 'nso', name: 'NSO', color: 'var(--ad-c2)' }, { key: 'wb', name: 'World Bank', color: 'var(--ad-c2)' }].filter((s) => s.key === srcPick);
    if (!status(box, ['vn_gdp_annual', 'vn_gdp_intl', 'vn_gdp'])) { legend(id + '-legend', []); return; }
    const by = new Map();
    const put = (date, k, v) => { if (v == null) return; if (!by.has(date)) by.set(date, { date }); by.get(date)[k] = v; };
    annual('sector', 'total', 'constant_2010', 'yoy').forEach((r) => put(r.date, 'nso', r.v));
    dash.data('vn_gdp_intl').data.filter((r) => r.source === 'wb_wdi').forEach((r) => put(r.date, 'wb', num(r.value)));
    // The current year so far: NSO's latest year-to-date real growth (quarterly tables), for a year with no annual figure yet.
    const lastYear = Math.max(...Array.from(by.values()).filter((r) => r[srcPick] != null).map((r) => Number(r.date.slice(0, 4))));
    const ytdRow = ytdSeries('total').filter((r) => Number(r.date.slice(0, 4)) > lastYear && r.period.slice(5) !== '').pop();
    const YTD_LABEL = { Q1: 'Jan–Mar', H1: 'Jan–Jun', '9M': 'Jan–Sep' };
    if (ytdRow) put(`${ytdRow.date.slice(0, 4)}-12-01`, 'ytd', ytdRow.v);
    const ytdName = ytdRow ? `NSO, ${YTD_LABEL[ytdRow.period.slice(5)] || 'year to date'} ${ytdRow.date.slice(0, 4)}` : '';
    legend(id + '-legend', []);
    const rows = Array.from(by.values()).filter((r) => r[srcPick] != null || r.ytd != null).sort((a, b) => (a.date < b.date ? -1 : 1));
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280, mr = 8;
    const { svg, x, y, W, ml } = frame(box, rows, H, rows.flatMap((r) => S.map((s) => r[s.key]).concat([r.ytd])).filter((v) => v != null), fmt0, true, mr);
    S.forEach((s) => {
      svg.append('path').attr('d', d3.line().defined((r) => r[s.key] != null).x((r) => x(J.date(r.date))).y((r) => y(r[s.key]))(rows))
        .attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', s.thin ? 1.75 : 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    });
    // x-axis: one label per point at a regular step counted back from the last point, which reads YTD when it is
    // the year to date (as in Chart 3, the axis simply runs on to it).
    svg.selectAll(`g[transform="translate(0,${H - 20})"]`).remove();
    const n = rows.length, room = Math.max(1, Math.floor((W - ml - mr) / 44));
    const stepY = [1, 2, 5, 10].find((k) => n / k <= room) || 10;
    rows.forEach((r, k) => {
      if ((n - 1 - k) % stepY !== 0) return;
      const px = x(J.date(r.date)), lab = r.ytd != null && r[srcPick] == null ? 'YTD' : r.date.slice(0, 4);
      svg.append('text').attr('x', px).attr('y', H - 20).attr('dy', '0.71em').attr('font-size', 12).attr('fill', 'var(--ad-ink)')
        .attr('text-anchor', px > W - mr - 16 ? 'end' : px < ml + 16 ? 'start' : 'middle').text(lab);
    });
    rows.filter((r) => r.ytd != null).forEach((r) => {
      svg.append('circle').attr('cx', x(J.date(r.date))).attr('cy', y(r.ytd)).attr('r', 4.5).attr('fill', 'var(--color-panel)')
        .attr('stroke', 'var(--ad-c2)').attr('stroke-width', 2);
    });
    const card = document.getElementById(id), tip = J.tip(card);
    const rule = svg.append('line').attr('y1', 8).attr('y2', H - 22).attr('stroke', 'var(--cds-chart-reference)').attr('display', 'none');
    const bis = d3.bisector((r) => J.date(r.date)).center;
    svg.append('rect').attr('x', ml).attr('width', Math.max(0, W - mr - ml)).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [mx] = d3.pointer(ev); const r = rows[bis(rows, x.invert(mx))]; const px = x(J.date(r.date));
        rule.attr('display', null).attr('x1', px).attr('x2', px);
        const cr = card.getBoundingClientRect();
        const lines = S.filter((s) => r[s.key] != null).map((s) => [s.color, s.name, r[s.key].toFixed(2) + '%'])
          .concat(r.ytd != null ? [['var(--ad-c2)', `YTD (${ytdName.replace('NSO, ', '')}, 2020 prices)`, r.ytd.toFixed(2) + '%']] : []);
        J.showTip(card, tip, r.date.slice(0, 4), lines, ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); tip.style.display = 'none'; });
  }


  // Charts 1 and 2: GDP and GDP per capita in US dollars, annual, World Bank WDI, as published (GDP shown in US$ billion,
  // the World Bank's US$ / 1e9; per capita in US$).
  const USD = {
    'gdp-usd': { div: 1e9, unit: 'US$ billion', tipUnit: ' bn', fmt: ',.1f', names: { 'NY.GDP.MKTP.CD': 'GDP, current US$', 'NY.GDP.MKTP.KD': 'GDP, constant 2015 US$' } },
    'gdp-pc': { div: 1, unit: 'US$', tipUnit: '', fmt: ',.0f', names: { 'NY.GDP.PCAP.CD': 'GDP per capita, current US$', 'NY.GDP.PCAP.KD': 'GDP per capita, constant 2015 US$' } },
  };
  function usd(id, pick) {
    const C = USD[id], box = document.getElementById(id + '-chart'), nominal = /\.CD$/.test(pick);
    document.getElementById(id + '-units').textContent = `${C.unit}, ${nominal ? 'current prices' : 'constant 2015 prices'}`;
    if (!status(box, ['vn_gdp_intl'])) return;
    const rows = dash.data('vn_gdp_intl').data.filter((r) => r.series === pick && num(r.value) != null)
      .map((r) => ({ date: r.date, v: num(r.value) / C.div })).sort((a, b) => (a.date < b.date ? -1 : 1));
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280, mr = 8, col = nominal ? 'var(--ad-c1)' : 'var(--ad-c2)';
    const { svg, x, y, W, ml } = frame(box, rows, H, rows.map((r) => r.v).concat([0]), (v) => d3.format(',.0f')(v), true, mr);
    svg.append('path').attr('d', d3.line().x((r) => x(J.date(r.date))).y((r) => y(r.v))(rows))
      .attr('fill', 'none').attr('stroke', col).attr('stroke-width', 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    // CAGR, calculated on this page (asked for 2 Nov 2026): (value in 2025 / value in the start year)^(1 / years) - 1,
    // from the World Bank figures drawn, for the series shown.
    const at = (yr) => rows.find((r) => r.date.slice(0, 4) === String(yr));
    const END = 2025, cagr = [2010, 2015].map((s) => { const a0 = at(s), a1 = at(END); return a0 && a1 && a0.v > 0 ? { s, v: (Math.pow(a1.v / a0.v, 1 / (END - s)) - 1) * 100 } : null; }).filter(Boolean);
    if (cagr.length) {
      // Placed just above and left of the line at 2015: the line rises to the right, so the block clears it.
      const p = at(2015) || at(END), lh = 16, n = cagr.length + 1;
      const t = svg.append('text').attr('font-size', 12).attr('fill', 'var(--ad-ink)').attr('text-anchor', 'end');
      t.append('tspan').attr('font-weight', 700).text('CAGR');
      cagr.forEach((c) => t.append('tspan').attr('dy', lh).text(`${c.s}–${String(END).slice(2)}: ${c.v.toFixed(1)}% a year`));
      const bw = t.node().getBBox().width;
      const tx = Math.max(ml + 8 + bw, x(J.date(p.date)) - 10);
      const ty = Math.max(16, y(p.v) - 12 - (n - 1) * lh);
      t.attr('x', tx).attr('y', ty); t.selectAll('tspan').attr('x', tx);
    }
    const card = document.getElementById(id), tip = J.tip(card);
    const rule = svg.append('line').attr('y1', 8).attr('y2', H - 22).attr('stroke', 'var(--cds-chart-reference)').attr('display', 'none');
    const dot = svg.append('circle').attr('r', 3.5).attr('fill', col).attr('display', 'none');
    const bis = d3.bisector((r) => J.date(r.date)).center;
    svg.append('rect').attr('x', ml).attr('width', Math.max(0, W - mr - ml)).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [mx] = d3.pointer(ev); const r = rows[bis(rows, x.invert(mx))]; const px = x(J.date(r.date));
        rule.attr('display', null).attr('x1', px).attr('x2', px); dot.attr('display', null).attr('cx', px).attr('cy', y(r.v));
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, r.date.slice(0, 4), [[col, C.names[pick], d3.format(C.fmt)(r.v) + C.tipUnit]], ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); dot.attr('display', 'none'); tip.style.display = 'none'; });
  }

  function tiles() {
    const L = dash.data('gdp_latest');
    document.querySelectorAll('#gdp-headline [data-source], #gdp-q, #mfg-q').forEach((el) => {
      if (L.status !== 'ok' || !L.data.length) { el.textContent = '—'; return; }
      el.classList.remove('dash-skeleton');
      const v = L.data[0][el.dataset.field];
      if (el.id === 'gdp-q' || el.id === 'mfg-q' || el.dataset.kind === 'text') el.textContent = v || '';
      else if (/_trn$/.test(el.dataset.field)) el.textContent = v == null ? '—' : d3.format(',.0f')(v);
      else el.textContent = f2(num(v));
    });
  }

  function takeaway() {
    const p = document.getElementById('gdp-takeaway');
    const L = dash.data('gdp_latest');
    if (L.status !== 'ok' || !L.data.length) { if (failed(L.status)) p.replaceChildren(); return; }
    const a = L.data[0];
    const mk = (field, v) => { const b = document.createElement('b'); b.dataset.source = 'gdp_latest'; b.dataset.field = field; b.dataset.row = '0'; b.textContent = f2(num(v)) + '%'; return b; };
    const t = (x) => p.append(document.createTextNode(x));
    const ql = (per) => `Q${per.slice(-1)} ${per.slice(0, 4)}`;
    p.replaceChildren();
    t(`Real GDP grew `); p.append(mk('real_yoy', a.real_yoy)); t(` on a year earlier in ${ql(a.period)}`);
    if (a.prev_period) { t(', against '); p.append(mk('real_yoy_prev', a.real_yoy_prev)); t(` in ${ql(a.prev_period)}`); }
    t(`; `); p.append(mk('real_ytd', a.real_ytd)); t(` in the ${a.ytd_label}. Manufacturing value added grew `); p.append(mk('mfg_yoy', a.mfg_yoy));
    t(' in real terms and manufacturing output '); p.append(mk('iip_mfg', a.iip_mfg)); t('.');
  }

  function redrawMfg() {
    if (!mfgVisible()) return;
    qLines('gdp-mfg', [
      { key: 'va', name: 'Manufacturing value added, real', color: 'var(--ad-c1)', rows: series('manufacturing', 'constant', 'yoy') },
      { key: 'iip', name: 'Manufacturing output (IIP)', color: 'var(--ad-c8)', dash: true, rows: (dash.data('vn_iip').status === 'ok' ? dash.data('vn_iip').data : []).filter((r) => r.code === 'c').map((r) => ({ date: r.date, v: num(r.rate) })) },
      { key: 'gdp', name: 'Real GDP', color: 'var(--ad-c2)', thin: true, rows: series('total', 'constant', 'yoy') },
    ], { ds: ['vn_gdp', 'vn_iip'] });
    qLines('gdp-mfg-share', [
      { key: 'ind', name: 'Industry (B to E)', color: 'var(--ad-c8)', rows: series('industry', 'current', 'share') },
      { key: 'mfg', name: 'Manufacturing (C)', color: 'var(--ad-c1)', rows: series('manufacturing', 'current', 'share') },
    ], { zero: false });
    iipBars();
  }

  J.redrawGdp = () => {
    redrawMfg();
    if (!visible()) return;
    growth();
    sources();
    qLines('gdp-sectors', [{ key: 'gdp', name: 'GDP', color: 'var(--ad-c2)', rows: series('total', 'constant', 'yoy') }]
      .concat(SEC.slice(0, 3).map(([code, name, color]) => ({ key: code, name, color, thin: true, rows: series(code, 'constant', 'yoy') }))), { start: START });
    usd('gdp-usd', usdPick);
    usd('gdp-pc', pcPick);
    structure();
    aLines('gdp-annual', [{ key: 'gdp', code: 'total', name: 'Real GDP', color: 'var(--ad-c2)', rows: annual('sector', 'total', 'constant_2010', 'yoy') }]
      .concat(SEC.slice(0, 3).map(([code, name, color]) => ({ key: code, code, name, color, thin: true, rows: annual('sector', code, 'constant_2010', 'yoy') }))), { ytd: true });
    aLines('gdp-exp', [
      { key: 'gdp', name: 'GDP', color: 'var(--ad-c2)', rows: annual('expenditure', 'total', 'constant_2010', 'yoy') },
      { key: 'hh', name: 'Household final consumption', color: 'var(--ad-c5)', rows: annual('expenditure', 'fc_household', 'constant_2010', 'yoy') },
      { key: 'gov', name: 'Government final consumption', color: 'var(--ad-c6)', thin: true, rows: annual('expenditure', 'fc_state', 'constant_2010', 'yoy') },
      { key: 'gfcf', name: 'Gross fixed capital formation', color: 'var(--ad-c1)', rows: annual('expenditure', 'gfcf', 'constant_2010', 'yoy') },
    ]);
    aLines('gdp-exp-share', [
      { key: 'hh', name: 'Household final consumption', color: 'var(--ad-c5)', rows: annual('expenditure', 'fc_household', 'current', 'share') },
      { key: 'gov', name: 'Government final consumption', color: 'var(--ad-c6)', rows: annual('expenditure', 'fc_state', 'current', 'share') },
      { key: 'gfcf', name: 'Gross fixed capital formation', color: 'var(--ad-c1)', rows: annual('expenditure', 'gfcf', 'current', 'share') },
      { key: 'tb', name: 'Balance of trade (goods and services)', color: 'var(--ad-c8)', dash: true, rows: annual('expenditure', 'trade_balance', 'current', 'share') },
    ]);
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

  dash.onData(() => { tiles(); takeaway(); indTable(); gdpHeat(); iipHeat(); J.redrawGdp(); });
})();
