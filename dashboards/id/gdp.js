// GDP tab: BPS quarterly GDP, 2010 series, as published (id_gdp_bps in AsiaDecoded/asia-vitals).
//   id_gdp: expenditure side, levels, growth, deflator growth, shares and contributions (sources of growth).
//   id_gdp_industry: production side, same measures by industry.
// BPS publishes no seasonally adjusted GDP: q/q rates are on the original series.

const gnum = (v) => (v === '' || v == null ? null : Number(v));
const GF = ['real_level', 'nominal_level', 'real_qoq', 'real_yoy', 'real_ctc', 'deflator_qoq', 'deflator_yoy',
  'share_nominal', 'contrib_qoq', 'contrib_yoy', 'contrib_ctc'];
const gread = (r) => {
  const o = { date: r.date, code: Number(r.code), component: r.component, level: Number(r.level), order: Number(r.order) };
  GF.forEach((f) => { o[f] = gnum(r[f]); });
  return o;
};

dash.calc('gdp_series', {
  title: 'GDP series',
  description: 'The GDP rows of the expenditure table (code 800), with cells read as numbers.',
  inputs: ['id_gdp'],
  fn: (id_gdp) => id_gdp.filter((r) => r.code === '800').map((r) => {
    const o = { date: r.date };
    ['real_level', 'nominal_level', 'real_qoq', 'real_yoy', 'real_ctc', 'deflator_qoq', 'deflator_yoy'].forEach((f) => { o[f] = r[f] === '' ? null : Number(r[f]); });
    return o;
  }).sort((a, b) => (a.date < b.date ? -1 : 1)),
});

dash.calc('gdp_latest', {
  title: 'Latest quarter and the one before',
  description: 'Published GDP and component growth rates in the latest quarter and the quarter before, for the headline figures.',
  inputs: ['id_gdp'],
  fn: (id_gdp) => {
    const dates = Array.from(new Set(id_gdp.filter((r) => r.code === '800' && r.real_yoy !== '').map((r) => r.date))).sort();
    const a = dates[dates.length - 1], b = dates[dates.length - 2];
    const get = (date, code, f) => { const r = id_gdp.find((x) => x.date === date && x.code === code); return r && r[f] !== '' ? Number(r[f]) : null; };
    const row = { date: a };
    [['gdp_yoy', '800', 'real_yoy'], ['gdp_qoq', '800', 'real_qoq'], ['gdp_ctc', '800', 'real_ctc'], ['defl_yoy', '800', 'deflator_yoy'],
      ['hh_yoy', '100', 'real_yoy'], ['gfcf_yoy', '400', 'real_yoy']].forEach(([k, c, f]) => {
      row[k] = get(a, c, f); row[k + '_prev'] = get(b, c, f);
    });
    return [row];
  },
});

dash.calc('components_latest', {
  title: 'Expenditure components, latest quarter',
  description: 'Every expenditure row in the latest quarter: real level in Rp trillion (Rp billion ÷ 1,000, one decimal) and the published rates, shares and contributions.',
  inputs: ['id_gdp'],
  fn: (id_gdp) => {
    const last = id_gdp.reduce((m, r) => (r.date > m ? r.date : m), '');
    const n = (v) => (v === '' ? null : Number(v));
    return id_gdp.filter((r) => r.date === last).sort((x, y) => Number(x.order) - Number(y.order)).map((r) => ({
      component: r.component, code: Number(r.code), level: Number(r.level), date: r.date,
      real_level_trn: r.real_level === '' ? null : Math.round(Number(r.real_level) / 100) / 10,
      real_qoq: n(r.real_qoq), real_yoy: n(r.real_yoy), deflator_yoy: n(r.deflator_yoy),
      share_nominal: n(r.share_nominal), contrib_yoy: n(r.contrib_yoy),
    }));
  },
});

dash.calc('industry_latest', {
  title: 'Industries, latest quarter',
  description: 'GDP by industry in the latest quarter: the 17 categories, taxes less subsidies on products and GDP, with published real growth, share of nominal GDP and contribution to GDP y/y.',
  inputs: ['id_gdp_industry'],
  fn: (id_gdp_industry) => {
    const last = id_gdp_industry.reduce((m, r) => (r.date > m ? r.date : m), '');
    const n = (v) => (v === '' ? null : Number(v));
    return id_gdp_industry.filter((r) => r.date === last && Number(r.level) <= 1).sort((x, y) => Number(x.order) - Number(y.order))
      .map((r) => ({ component: r.component, code: Number(r.code), date: r.date, real_yoy: n(r.real_yoy), real_qoq: n(r.real_qoq),
        share_nominal: n(r.share_nominal), contrib_yoy: n(r.contrib_yoy) }));
  },
});

(() => {
  const J = window.JG;
  J.state.gGrowth = 'yoy'; J.state.gLevel = 'real'; J.state.gContrib = 'yoy';
  const seg = (id, key, attr) => {
    const el = document.getElementById(id); if (!el) return;
    el.addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b) return;
      J.state[key] = b.dataset[attr];
      el.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      J.redrawGdp();
    });
  };
  seg('g-growth-seg', 'gGrowth', 'g');
  seg('g-level-seg', 'gLevel', 'b');
  seg('g-contrib-seg', 'gContrib', 'c');

  // Contribution stack: BPS's sources of growth by expenditure. Imports are published as their own
  // contribution (positive when imports grow); GDP subtracts them, so they are drawn below zero when positive.
  const PARTS = [
    { code: 100, name: 'Household consumption', color: '#FFC000' },
    { code: 200, name: 'NPISH consumption', color: '#A6A6A6' },
    { code: 300, name: 'Government consumption', color: '#92D050' },
    { code: 400, name: 'Fixed investment', color: '#1F4E79' },
    { code: 500, name: 'Inventories', color: '#954F72' },
    { code: 600, name: 'Exports', color: '#0C84FF' },
    { code: 700, name: 'Imports (subtracted)', color: '#EE6631', sign: -1 },
    { code: 790, name: 'Statistical discrepancy', color: '#44546A' },
  ];
  const pct = (v) => (v == null ? '—' : J.f1(v) + '%');
  const qlab = (d) => `Q${Math.floor((Number(d.slice(5, 7)) - 1) / 3) + 1} ${d.slice(0, 4)}`;
  const bad = (D) => D.status === 'error' || D.status === 'connect' || D.status === 'declined';

  function tiles() {
    const L = dash.data('gdp_latest');
    document.querySelectorAll('#g-headline [data-source="gdp_latest"]').forEach((s) => {
      if (L.status === 'ok' && L.data.length) { s.classList.remove('dash-skeleton'); s.textContent = J.f1(L.data[0][s.dataset.field]); }
      else if (L.status !== 'loading') { s.classList.remove('dash-skeleton'); s.textContent = '—'; }
    });
    const R = dash.data('gdp_release');
    document.querySelectorAll('[data-source="gdp_release"][data-field="label"]').forEach((s) => {
      if (R.status === 'ok' && R.data.length) { s.classList.remove('dash-skeleton'); s.textContent = R.data[0].label; }
      else if (R.status !== 'loading') { s.classList.remove('dash-skeleton'); s.textContent = ''; }
    });
  }

  function takeaway() {
    const p = document.getElementById('g-takeaway');
    const L = dash.data('gdp_latest'), C = dash.data('components_latest');
    if (L.status !== 'ok' || C.status !== 'ok' || !L.data.length) { if (bad(L) || bad(C)) p.textContent = ''; return; }
    const a = L.data[0];
    const mk = (src, field, where) => {
      const s = document.createElement('b'); s.dataset.source = src; s.dataset.field = field;
      if (where) s.dataset.where = 'component=' + encodeURIComponent(where); else s.dataset.row = '0';
      return s;
    };
    p.replaceChildren();
    const t = (x) => p.append(document.createTextNode(x));
    const v1 = mk('gdp_latest', 'gdp_yoy'); v1.textContent = J.f1(Math.abs(a.gdp_yoy));
    const v0 = mk('gdp_latest', 'gdp_yoy_prev'); v0.textContent = J.f1(a.gdp_yoy_prev);
    t(`In ${qlab(a.date)}, real GDP ${a.gdp_yoy >= 0 ? 'grew' : 'shrank'} `); p.append(v1); t('% y/y (prior quarter '); p.append(v0); t('%). ');
    const hh = C.data.find((r) => r.code === 100), inv = C.data.find((r) => r.code === 400);
    if (hh && hh.contrib_yoy != null) {
      const s = mk('components_latest', 'contrib_yoy', hh.component); s.textContent = J.f1(hh.contrib_yoy);
      t('Household consumption contributed '); p.append(s); t('ppt');
      if (inv && inv.contrib_yoy != null) {
        const s2 = mk('components_latest', 'contrib_yoy', inv.component); s2.textContent = J.f1(inv.contrib_yoy);
        t(' and fixed investment '); p.append(s2); t('ppt');
      }
      t('.');
    }
  }

  function axes(svg, y, ticks, ml, W, H, fmt) {
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - 8).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
  }

  function legend(id, items) {
    const lg = document.getElementById(id); if (!lg) return;
    lg.replaceChildren();
    items.forEach(([cls, col, txt]) => {
      const sp = document.createElement('span'), m = document.createElement('span'); m.className = cls; m.style.background = col;
      sp.append(m, document.createTextNode(txt)); lg.appendChild(sp);
    });
  }

  function growthChart() {
    const box = document.getElementById('g-growth-chart');
    const D = dash.data('gdp_series');
    if (bad(D)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    const k = 'real_' + J.state.gGrowth;
    const rows = J.slice(D.data.filter((r) => r[k] != null), 'g-growth');
    if (!rows.length) { box.replaceChildren(); return; }
    const W = box.clientWidth, H = 280;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const vals = rows.map((r) => r[k]);
    const y = d3.scaleLinear([Math.min(0, d3.min(vals)), Math.max(0, d3.max(vals))], [H - 24, 10]).nice();
    const ticks = y.ticks(5);
    const ml = J.textWidth(svg, ticks.map((v) => d3.format('.0f')(v))) + 10;
    const x = d3.scaleBand(rows.map((r) => r.date), [ml, W - 8]).padding(0.2);
    axes(svg, y, ticks, ml, W, H, d3.format('.0f'));
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).tickValues(J.yearTicks(rows.map((r) => r.date), W - ml)).tickSize(0).tickFormat((d) => d.slice(0, 4))));
    const col = J.PAL[0], lc = J.PAL[1];
    svg.append('g').selectAll('rect').data(rows).join('rect')
      .attr('x', (r) => x(r.date)).attr('width', x.bandwidth())
      .attr('y', (r) => y(Math.max(0, r[k]))).attr('height', (r) => Math.abs(y(r[k]) - y(0))).attr('fill', col);
    if (J.state.gGrowth === 'yoy') {
      const line = d3.line().defined((r) => r.real_ctc != null).x((r) => x(r.date) + x.bandwidth() / 2).y((r) => y(r.real_ctc));
      svg.append('path').attr('d', line(rows)).attr('fill', 'none').attr('stroke', lc).attr('stroke-width', 2.5).attr('stroke-linejoin', 'round');
    }
    legend('g-growth-legend', J.state.gGrowth === 'yoy'
      ? [['sw', col, 'y/y'], ['ln', lc, 'year to date (c-to-c)']]
      : [['sw', col, 'q/q, not seasonally adjusted']]);
    const hl = svg.append('rect').attr('fill', 'var(--color-fg)').attr('opacity', 0.06).attr('display', 'none');
    const card = document.getElementById('g-growth'), tip = J.tip(card);
    svg.append('rect').attr('x', ml).attr('width', W - ml).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [mx] = d3.pointer(ev);
        const r = rows[Math.max(0, Math.min(rows.length - 1, Math.floor((mx - ml) / x.step())))];
        hl.attr('display', null).attr('x', x(r.date) - x.step() * x.paddingInner() / 2).attr('width', x.step()).attr('height', H - 22);
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, qlab(r.date), [[col, 'y/y', pct(r.real_yoy)], [lc, 'year to date', pct(r.real_ctc)], [null, 'q/q', pct(r.real_qoq)]],
          ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { hl.attr('display', 'none'); tip.style.display = 'none'; });
  }

  function lineChart(boxId, cardId, rowsAll, series, fmt, zero, extra) {
    const box = document.getElementById(boxId);
    const rows = J.slice(rowsAll.filter((r) => series.every((s) => r[s.key] != null)), cardId);
    if (!rows.length) { box.replaceChildren(); return; }
    const W = box.clientWidth, H = 260, mr = 8;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const vals = rows.flatMap((r) => series.map((s) => r[s.key]));
    let lo = d3.min(vals), hi = d3.max(vals);
    if (zero) { lo = Math.min(0, lo); hi = Math.max(0, hi); }
    const y = d3.scaleLinear([lo, hi], [H - 24, 12]).nice();
    const ticks = y.ticks(4);
    const ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    const x = d3.scaleUtc([J.date(rows[0].date), J.date(rows[rows.length - 1].date)], [ml, W - mr]);
    axes(svg, y, ticks, ml, W, H, fmt);
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).ticks(Math.max(1, Math.round((W - ml) / 56))).tickSize(0).tickFormat(d3.utcFormat('%Y'))));
    series.forEach((s) => {
      svg.append('path').attr('d', d3.line().x((r) => x(J.date(r.date))).y((r) => y(r[s.key]))(rows))
        .attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', 2.5).attr('stroke-linejoin', 'round');
    });
    const card = document.getElementById(cardId), tip = J.tip(card);
    const rule = svg.append('line').attr('y1', 8).attr('y2', H - 22).attr('stroke', 'var(--cds-chart-reference)').attr('display', 'none');
    const bis = d3.bisector((r) => J.date(r.date)).center;
    svg.append('rect').attr('x', ml).attr('width', W - ml - mr).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const r = rows[bis(rows, x.invert(d3.pointer(ev)[0]))];
        const px = x(J.date(r.date)); rule.attr('display', null).attr('x1', px).attr('x2', px);
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, qlab(r.date), series.map((s) => [series.length > 1 ? s.color : null, s.name, fmt(r[s.key])]).concat(extra ? extra(r) : []),
          ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); tip.style.display = 'none'; });
  }

  function levelChart() {
    const box = document.getElementById('g-level-chart');
    const D = dash.data('gdp_series');
    if (bad(D)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    const b = J.state.gLevel;
    const rows = D.data.map((r) => ({ date: r.date, v: r[b + '_level'] == null ? null : r[b + '_level'] / 1000, yoy: b === 'real' ? r.real_yoy : null }));
    lineChart('g-level-chart', 'g-level', rows, [{ key: 'v', name: b === 'real' ? 'Real (2010 prices)' : 'Nominal', color: b === 'real' ? J.PAL[0] : J.PAL[1] }],
      (v) => 'Rp' + d3.format(',.0f')(v), false, (r) => (b === 'real' ? [[null, 'y/y', pct(r.yoy)]] : []));
  }

  function deflatorChart() {
    const box = document.getElementById('g-deflator-chart');
    const D = dash.data('gdp_series');
    if (bad(D)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    lineChart('g-deflator-chart', 'g-deflator', D.data, [{ key: 'deflator_yoy', name: 'y/y', color: J.PAL[0] }], (v) => d3.format('.1f')(v) + '%', true);
  }

  function contribChart() {
    const box = document.getElementById('g-contrib-chart');
    const D = dash.data('id_gdp');
    if (bad(D)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    const k = 'contrib_' + J.state.gContrib, gk = 'real_' + J.state.gContrib;
    const by = d3.group(D.data, (r) => r.date);
    let rows = Array.from(by, ([date, rs]) => {
      const o = { date };
      rs.forEach((r) => {
        const c = Number(r.code);
        if (c === 800) o.GDP = gnum(r[gk]);
        const p = PARTS.find((q) => q.code === c);
        if (p) { const v = gnum(r[k]); o['p' + c] = v; o['s' + c] = v == null ? null : v * (p.sign || 1); }
      });
      return o;
    }).filter((o) => o.GDP != null && o.s100 != null).sort((a, b) => (a.date < b.date ? -1 : 1));
    rows = J.slice(rows, 'g-contrib');
    if (!rows.length) { box.replaceChildren(); return; }
    const W = box.clientWidth, H = 300;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const keys = PARTS.map((p) => 's' + p.code);
    const stack = d3.stack().keys(keys).value((d, key) => d[key] || 0).offset(d3.stackOffsetDiverging)(rows);
    const lo = Math.min(d3.min(stack, (s) => d3.min(s, (d) => d[0])), d3.min(rows, (r) => r.GDP));
    const hi = Math.max(d3.max(stack, (s) => d3.max(s, (d) => d[1])), d3.max(rows, (r) => r.GDP));
    const y = d3.scaleLinear([Math.min(0, lo), Math.max(0, hi)], [H - 24, 10]).nice();
    const ticks = y.ticks(5);
    const ml = J.textWidth(svg, ticks.map((v) => d3.format('.0f')(v))) + 10;
    const x = d3.scaleBand(rows.map((r) => r.date), [ml, W - 8]).padding(0.2);
    axes(svg, y, ticks, ml, W, H, d3.format('.0f'));
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).tickValues(J.yearTicks(rows.map((r) => r.date), W - ml)).tickSize(0).tickFormat((d) => d.slice(0, 4))));
    svg.append('g').selectAll('g').data(stack).join('g').attr('fill', (s, i) => PARTS[i].color)
      .selectAll('rect').data((s) => s).join('rect')
      .attr('x', (d) => x(d.data.date)).attr('width', x.bandwidth())
      .attr('y', (d) => y(Math.max(d[0], d[1]))).attr('height', (d) => Math.abs(y(d[0]) - y(d[1])));
    svg.append('path').attr('d', d3.line().x((r) => x(r.date) + x.bandwidth() / 2).y((r) => y(r.GDP))(rows))
      .attr('fill', 'none').attr('stroke', '#BD1B21').attr('stroke-width', 2.5).attr('stroke-linejoin', 'round');
    const hl = svg.append('rect').attr('fill', 'var(--color-fg)').attr('opacity', 0.06).attr('display', 'none');
    const card = document.getElementById('g-contrib'), tip = J.tip(card);
    svg.append('rect').attr('x', ml).attr('width', W - ml).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [mx] = d3.pointer(ev);
        const r = rows[Math.max(0, Math.min(rows.length - 1, Math.floor((mx - ml) / x.step())))];
        hl.attr('display', null).attr('x', x(r.date) - x.step() * x.paddingInner() / 2).attr('width', x.step()).attr('height', H - 22);
        const cr = card.getBoundingClientRect();
        const lines = [['#BD1B21', 'GDP, ' + (J.state.gContrib === 'qoq' ? 'q/q' : 'y/y'), pct(r.GDP)]]
          .concat(PARTS.slice().reverse().map((p) => [p.color, p.name + (p.sign ? ' (BPS: ' + J.f1(r['p' + p.code]) + ')' : ''),
            r['s' + p.code] == null ? '—' : (r['s' + p.code] > 0 ? '+' : '') + J.f1(r['s' + p.code]) + 'ppt']));
        J.showTip(card, tip, qlab(r.date), lines, ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { hl.attr('display', 'none'); tip.style.display = 'none'; });
    legend('g-contrib-legend', [['ln', '#BD1B21', 'GDP growth']].concat(PARTS.slice().reverse().map((p) => ['sw', p.color, p.name])));
  }

  function table(id, src, cols, cls) {
    const tb = document.querySelector(`#${id} tbody`);
    const C = dash.data(src);
    if (bad(C)) { tb.replaceChildren(); const td = tb.insertRow().insertCell(); td.colSpan = cols.length; J.fail(td); return; }
    if (C.status !== 'ok') return;
    tb.replaceChildren();
    C.data.forEach((r) => {
      const tr = tb.insertRow();
      tr.dataset.key = String(r.code);
      const c = cls(r); if (c) tr.className = c;
      cols.forEach((c2) => {
        const td = tr.insertCell();
        if (c2 === 'component') { td.textContent = r.component; return; }
        const v = r[c2];
        td.textContent = v == null ? '' : (c2 === 'real_level_trn' ? d3.format(',.1f')(v) : J.f1(v));
        if (v != null && v < 0 && c2 !== 'real_level_trn') td.classList.add('neg');
      });
    });
  }

  function tables() {
    const C = dash.data('components_latest');
    if (C.status === 'ok' && C.data.length) document.getElementById('g-table-q').textContent = qlab(C.data[0].date);
    table('g-comp-table', 'components_latest', ['component', 'real_level_trn', 'real_qoq', 'real_yoy', 'deflator_yoy', 'share_nominal', 'contrib_yoy'],
      (r) => (r.code === 800 ? 'gdp' : r.level >= 2 ? 'sub' + (r.level === 3 ? ' sub2' : '') : ''));
    const I = dash.data('industry_latest');
    if (I.status === 'ok' && I.data.length) document.getElementById('g-ind-q').textContent = qlab(I.data[0].date);
    table('g-ind-table', 'industry_latest', ['component', 'real_qoq', 'real_yoy', 'share_nominal', 'contrib_yoy'],
      (r) => (/produk domestik bruto/i.test(r.component) ? 'gdp' : ''));
  }

  J.redrawGdp = () => {
    const pg = document.getElementById('gdp');
    if (!pg || pg.hidden) return;
    growthChart(); levelChart(); deflatorChart(); contribChart();
  };
  dash.onData(() => { tiles(); takeaway(); tables(); J.redrawGdp(); });
})();
