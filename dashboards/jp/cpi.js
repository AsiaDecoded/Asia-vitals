// Inflation tab: Japan CPI (Statistics Bureau, 2025 base), national and Tokyo.

dash.calc('cpi_series', {
  title: 'CPI series',
  description: 'Every CPI row with its cells read as numbers.',
  inputs: ['jp_cpi'],
  fn: (jp_cpi) => {
    const n = (v) => (v === '' || v == null ? null : Number(v));
    return jp_cpi.map((r) => ({
      date: r.date, area: r.area, series: r.series, label: r.label, group: r.group,
      order: Number(r.order), index: n(r.index), mom: n(r.mom), yoy: n(r.yoy),
    }));
  },
});

dash.calc('cpi_latest', {
  title: 'Latest month and the one before',
  description: 'Year-on-year rates for the latest national month and the month before, plus Tokyo core for its latest month.',
  inputs: ['cpi_series'],
  fn: (cpi_series) => {
    const pair = (area, series) => {
      const s = cpi_series.filter((r) => r.area === area && r.series === series && r.yoy != null)
        .sort((a, b) => (a.date < b.date ? -1 : 1));
      return [s[s.length - 1], s[s.length - 2]];
    };
    const row = {};
    ['all', 'core', 'core_core', 'ex_food_energy', 'goods', 'services'].forEach((k) => {
      const [a, b] = pair('national', k);
      row[k + '_yoy'] = a ? a.yoy : null;
      row[k + '_yoy_prev'] = b ? b.yoy : null;
      if (k === 'all') row.date = a ? a.date : null;
    });
    const [t, tp] = pair('tokyo', 'core');
    row.tokyo_date = t ? t.date : null;
    row.tokyo_core_yoy = t ? t.yoy : null;
    row.tokyo_core_yoy_prev = tp ? tp.yoy : null;
    return [row];
  },
});

dash.calc('cpi_table', {
  title: 'Annualised rates, latest month',
  description: 'For the five seasonally adjusted national series: 1-, 2-, 3- and 6-month changes in the SA index, annualised, and the published 12-month change of the unadjusted series.',
  inputs: ['cpi_series', 'jp_cpi_core3'],
  fn: (cpi_series, jp_cpi_core3) => {
    const SA = [['all', 'All items'], ['core', 'Core 1 (less fresh food)'], ['core_core', 'Core 2 (less fresh food and energy)'], ['goods', 'Goods'], ['services', 'Services']];
    const nat = cpi_series.filter((r) => r.area === 'national' && r.series === 'all_sa' && r.index != null)
      .reduce((m, r) => (r.date > m ? r.date : m), '');
    const back = (d, k) => { const y = +d.slice(0, 4), m = +d.slice(5, 7) - 1 - k; const t = new Date(Date.UTC(y, m, 1)); return t.toISOString().slice(0, 10); };
    const at = (series, date) => cpi_series.find((r) => r.area === 'national' && r.series === series && r.date === date);
    const ann = (series, k) => {
      const a = at(series, nat), b = at(series, back(nat, k));
      return a && b && a.index != null && b.index ? Math.round((Math.pow(a.index / b.index, 12 / k) - 1) * 1000) / 10 : null;
    };
    const rows = SA.map(([k, label]) => {
      const y = at(k, nat);
      return { label, series: k, date: nat, ann1: ann(k + '_sa', 1), ann2: ann(k + '_sa', 2), ann3: ann(k + '_sa', 3),
        ann6: ann(k + '_sa', 6), yoy12: y ? y.yoy : null };
    });
    // Core 3: Asia Decoded calculation, no seasonally adjusted index, so 12-month only
    const k3 = jp_cpi_core3.find((r) => r.date === nat);
    rows.splice(3, 0, { label: 'Core 3 (less food and energy)', series: 'core3', date: nat, ann1: null, ann2: null, ann3: null, ann6: null,
      yoy12: k3 && k3.yoy !== '' ? Math.round(Number(k3.yoy) * 10) / 10 : null });
    return rows;
  },
});

dash.calc('cpi_movers', {
  title: 'Item contributions, 3- and 6-month averages',
  description: 'For each individual CPI item: its weight and y/y in the latest month, and the average of its published contribution to the all-items y/y over the latest 3 and 6 months (items present in every month of the window).',
  inputs: ['jp_cpi_items'],
  fn: (jp_cpi_items) => {
    const n = (v) => (v === '' || v == null ? null : Number(v));
    const months = Array.from(new Set(jp_cpi_items.map((r) => r.date))).sort();
    const latest = months[months.length - 1];
    const last = (k) => months.slice(-k);
    const by = new Map();
    jp_cpi_items.forEach((r) => {
      if (!by.has(r.code)) by.set(r.code, { code: r.code, months: {} });
      by.get(r.code).months[r.date] = { name: r.name, weight: n(r.weight), yoy: n(r.yoy), c: n(r.contrib_yoy) };
    });
    const avg = (it, k) => {
      const ms = last(k);
      if (ms.length < k || ms.some((m) => !it.months[m] || it.months[m].c == null)) return null;
      return ms.reduce((a, m) => a + it.months[m].c, 0) / k;
    };
    const out = [];
    by.forEach((it) => {
      const cur = it.months[latest];
      if (!cur || !cur.weight) return;
      out.push({ name: cur.name, date: latest, weight: cur.weight, yoy: cur.yoy, avg3: avg(it, 3), avg6: avg(it, 6) });
    });
    return out;
  },
});

dash.calc('ppi_series', {
  title: 'PPI series',
  description: 'Every producer, export and import price row with its cells read as numbers.',
  inputs: ['jp_ppi'],
  fn: (jp_ppi) => jp_ppi.map((r) => ({
    date: r.date, series: r.series, label: r.label, order: Number(r.order),
    index: r.index === '' ? null : Number(r.index), yoy: r.yoy === '' ? null : Number(r.yoy),
  })),
});

dash.calc('ppi_latest', {
  title: 'Latest producer prices',
  description: 'PPI y/y for the latest month and the month before, with import and export prices (yen basis) y/y.',
  inputs: ['ppi_series'],
  fn: (ppi_series) => {
    const s = (k) => ppi_series.filter((r) => r.series === k && r.yoy != null).sort((a, b) => (a.date < b.date ? -1 : 1));
    const p = s('ppi'), im = s('import_yen'), ex = s('export_yen');
    const a = p[p.length - 1], b = p[p.length - 2];
    return [{ date: a ? a.date : null, ppi_yoy: a ? a.yoy : null, ppi_yoy_prev: b ? b.yoy : null,
      import_yen_yoy: im.length ? im[im.length - 1].yoy : null, export_yen_yoy: ex.length ? ex[ex.length - 1].yoy : null }];
  },
});

(() => {
  const J = window.JG;
  const S = { months: 120, measures: 'national', gs: 'national', drivers: 'national', sa: 'all_sa', tmonths: 120, movers: 3 };
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const mLabel = (d) => (d ? MONTHS[+d.slice(5, 7) - 1] + ' ' + d.slice(0, 4) : '');
  const visible = () => !document.getElementById('inflation').hidden;
  const pct = (v) => (v == null ? '—' : J.f1(v) + '%');

  const seg = (id, key, attr, parse) => {
    const el = document.getElementById(id);
    el.addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b) return;
      S[key] = parse(b.dataset[attr]);
      el.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      J.redrawCpi();
    });
  };
  seg('cpi-measures-seg', 'measures', 'a', String);
  const mseg = document.getElementById('cpi-movers-seg');
  mseg.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    S.movers = Number(b.dataset.n);
    mseg.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    moversTable();
  });
  seg('cpi-gs-seg', 'gs', 'a', String);
  seg('cpi-drivers-seg', 'drivers', 'a', String);
  seg('cpi-sa-seg', 'sa', 's', String);

  const failed = (st) => st === 'error' || st === 'connect' || st === 'declined';

  // Wide rows by date for one area and a set of series.
  const M = (id) => J.periodOf(id, 120);
  function wide(rows, area, keys, meas, id) {
    const by = new Map();
    rows.forEach((r) => {
      if (r.area !== area || !keys.includes(r.series) || r[meas] == null) return;
      if (!by.has(r.date)) by.set(r.date, { date: r.date });
      by.get(r.date)[r.series] = r[meas];
    });
    const out = Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
    return J.slice(out, id);
  }

  function legend(id, series) {
    const el = document.getElementById(id);
    el.replaceChildren();
    series.forEach((s) => {
      const span = document.createElement('span'); const ln = document.createElement('span');
      ln.className = s.bar ? 'sw' : 'ln'; ln.style.background = s.dash ? `repeating-linear-gradient(to right, ${s.color} 0 6px, transparent 6px 9px)` : s.color;
      if (s.dash) { ln.dataset.dash = '1'; ln.dataset.color = s.color; }
      span.append(ln, document.createTextNode(s.name)); el.appendChild(span);
    });
  }

  function lineChart(boxId, cardId, legendId, area, series, H, build) {
    const box = document.getElementById(boxId);
    const ids = build ? build.ids : ['cpi_series'];
    const sts = ids.map((id) => dash.data(id));
    if (sts.some((d) => failed(d.status))) { J.fail(box); return; }
    if (sts.some((d) => d.status !== 'ok')) { box.replaceChildren(); return; }
    const keys = series.map((s) => s.key);
    const rows = build ? build.rows(...sts.map((d) => d.data)) : wide(sts[0].data, area, keys, 'yoy', cardId);
    if (!rows.length) { box.replaceChildren(); return; }
    const W = box.clientWidth;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const vals = rows.flatMap((r) => keys.map((k) => r[k])).filter((v) => v != null);
    const y = d3.scaleLinear([Math.min(0, d3.min(vals)), Math.max(0, d3.max(vals))], [H - 24, 10]).nice();
    const ticks = y.ticks(5);
    const ml = J.textWidth(svg, ticks.map((v) => d3.format('.0f')(v))) + 10;
    const x = d3.scaleUtc([J.date(rows[0].date), J.date(rows[rows.length - 1].date)], [ml, W - 8]);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - 8).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(d3.format('.0f'))));
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).ticks(Math.max(2, Math.round((W - ml) / 70))).tickSize(0).tickFormat(d3.utcFormat('%Y'))));
    series.forEach((s) => {
      svg.append('path').attr('d', d3.line().defined((r) => r[s.key] != null).x((r) => x(J.date(r.date))).y((r) => y(r[s.key]))(rows))
        .attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', s.width || 2.5).attr('stroke-dasharray', s.dash ? '6 4' : null).attr('stroke-linecap', s.dash ? 'butt' : 'round').attr('stroke-linejoin', 'round');
    });
    legend(legendId, series);
    const card = document.getElementById(cardId), tip = J.tip(card);
    const rule = svg.append('line').attr('y1', 8).attr('y2', H - 22).attr('stroke', 'var(--cds-chart-reference)').attr('display', 'none');
    const dots = series.map((s) => svg.append('circle').attr('r', 3.5).attr('fill', s.color).attr('display', 'none'));
    const bis = d3.bisector((r) => J.date(r.date)).center;
    svg.append('rect').attr('x', ml).attr('width', W - ml).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const r = rows[bis(rows, x.invert(d3.pointer(ev)[0]))];
        const px = x(J.date(r.date));
        rule.attr('display', null).attr('x1', px).attr('x2', px);
        dots.forEach((d, i) => (r[series[i].key] == null ? d.attr('display', 'none') : d.attr('display', null).attr('cx', px).attr('cy', y(r[series[i].key]))));
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, mLabel(r.date) + (area === 'tokyo' ? ', Tokyo' : ''), series.map((s) => [s.color, s.name, pct(r[s.key])]), ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); dots.forEach((d) => d.attr('display', 'none')); tip.style.display = 'none'; });
  }

  // CPI all items: y/y (line, as published) and m/m seasonally adjusted (bars, as published).
  function ymChart() {
    const box = document.getElementById('cpi-ym-chart');
    const D = dash.data('cpi_series');
    if (failed(D.status)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    const by = new Map();
    const put = (d, k, v) => { if (v == null) return; if (!by.has(d)) by.set(d, { date: d }); by.get(d)[k] = v; };
    D.data.forEach((r) => {
      if (r.area !== 'national') return;
      if (r.series === 'all') put(r.date, 'yoy', r.yoy);
      if (r.series === 'all_sa') put(r.date, 'mom', r.mom);
    });
    let rows = Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
    rows = J.slice(rows, 'cpi-ym');
    if (!rows.length) { box.replaceChildren(); return; }
    const series = [
      { key: 'yoy', name: 'y/y', color: J.PAL[0] },
      { key: 'mom', name: 'm/m, seasonally adjusted', color: J.PAL[1], bar: true },
    ];
    const W = box.clientWidth, H = 280;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    // Two axes with the zero lines aligned: m/m is drawn on y scaled by k.
    const yv = rows.map((r) => r.yoy).filter((v) => v != null), mv = rows.map((r) => r.mom).filter((v) => v != null);
    const ext = (v) => [Math.min(0, d3.min(v) ?? 0), Math.max(0, d3.max(v) ?? 0)];
    const [ylo, yhi] = ext(yv), [mlo, mhi] = ext(mv);
    const k = mv.length ? Math.max(Math.abs(ylo), yhi, 0.1) / Math.max(Math.abs(mlo), mhi, 0.05) : 1;
    const y = d3.scaleLinear([Math.min(ylo, mlo * k), Math.max(yhi, mhi * k)], [H - 24, 10]).nice();
    const yR = d3.scaleLinear(y.domain().map((v) => v / k), y.range());
    const ticks = y.ticks(5), rticks = yR.ticks(5);
    const fmt = d3.format('.0f'), rfmt = d3.format(rticks.some((v) => !Number.isInteger(v)) ? '.1f' : '.0f');
    const ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    const mr = mv.length ? J.textWidth(svg, rticks.map(rfmt)) + 10 : 8;
    const x = d3.scaleBand(rows.map((r) => r.date), [ml, W - mr]).padding(0.2);
    const cx = (d) => x(d) + x.bandwidth() / 2;
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - mr).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
    if (mv.length) J.axisStyle(svg.append('g').attr('transform', `translate(${W - mr + 4},0)`).call(d3.axisRight(yR).tickValues(rticks).tickSize(0).tickFormat(rfmt)));
    const years = Array.from(new Set(rows.map((r) => r.date.slice(0, 4))));
    const step = [1, 2, 5, 10].find((n) => years.length / n <= Math.max(1, (W - ml) / 56)) || 10;
    const xt = rows.map((r) => r.date).filter((d) => d.slice(5, 7) === '01' && +d.slice(0, 4) % step === 0);
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).tickValues(xt).tickSize(0).tickFormat((d) => d.slice(0, 4))));
    const br = rows.filter((r) => r.mom != null);
    svg.append('g').selectAll('rect').data(br).join('rect')
      .attr('x', (r) => x(r.date)).attr('width', x.bandwidth())
      .attr('y', (r) => yR(Math.max(0, r.mom))).attr('height', (r) => Math.max(0.5, Math.abs(yR(r.mom) - yR(0))))
      .attr('fill', series[1].color);
    svg.append('path').attr('d', d3.line().defined((r) => r.yoy != null).x((r) => cx(r.date)).y((r) => y(r.yoy))(rows))
      .attr('fill', 'none').attr('stroke', series[0].color).attr('stroke-width', 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    legend('cpi-ym-legend', series);
    const card = document.getElementById('cpi-ym'), tip = J.tip(card);
    const rule = svg.append('line').attr('y1', 8).attr('y2', H - 22).attr('stroke', 'var(--cds-chart-reference)').attr('display', 'none');
    const dot = svg.append('circle').attr('r', 3.5).attr('fill', series[0].color).attr('display', 'none');
    svg.append('rect').attr('x', ml).attr('width', W - ml - mr).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const i = Math.max(0, Math.min(rows.length - 1, Math.floor((d3.pointer(ev)[0] - ml) / x.step())));
        const r = rows[i], px = cx(r.date);
        rule.attr('display', null).attr('x1', px).attr('x2', px);
        if (r.yoy == null) dot.attr('display', 'none'); else dot.attr('display', null).attr('cx', px).attr('cy', y(r.yoy));
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, mLabel(r.date), series.map((s) => [s.color, s.name, pct(r[s.key])]), ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); dot.attr('display', 'none'); tip.style.display = 'none'; });
  }

  // Contributions to the y/y change in all items, as published (Statistics Bureau, Table 5).
  function contribChart() {
    const box = document.getElementById('cpi-contrib-chart');
    const D = dash.data('jp_cpi_contrib');
    if (failed(D.status)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    const PARTS = [
      { key: 'services', name: 'Services', color: J.PAL[3], bar: true },
      { key: 'goods_core', name: 'Goods less fresh food and energy', color: J.PAL[4], bar: true },
      { key: 'energy', name: 'Energy', color: J.PAL[0], bar: true },
      { key: 'fresh_food', name: 'Fresh food', color: J.PAL[5], bar: true },
    ];
    const by = new Map();
    D.data.forEach((r) => {
      const v = r.contrib_yoy === '' || r.contrib_yoy == null ? null : Number(r.contrib_yoy);
      if (!by.has(r.date)) by.set(r.date, { date: r.date });
      by.get(r.date)[r.series] = v;
    });
    let rows = Array.from(by.values()).filter((r) => r.all != null).sort((a, b) => (a.date < b.date ? -1 : 1));
    rows = J.slice(rows, 'cpi-contrib');
    if (!rows.length) { box.replaceChildren(); return; }
    const keys = PARTS.map((p) => p.key);
    const W = box.clientWidth, H = 280;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const stack = d3.stack().keys(keys).value((d, k) => d[k] || 0).offset(d3.stackOffsetDiverging)(rows);
    const lo = Math.min(0, d3.min(stack, (s) => d3.min(s, (d) => d[0])), d3.min(rows, (r) => r.all));
    const hi = Math.max(0, d3.max(stack, (s) => d3.max(s, (d) => d[1])), d3.max(rows, (r) => r.all));
    const y = d3.scaleLinear([lo, hi], [H - 24, 10]).nice();
    const ticks = y.ticks(5);
    const fmt = d3.format('.0f');
    const ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    const x = d3.scaleBand(rows.map((r) => r.date), [ml, W - 8]).padding(0.15);
    const cx = (d) => x(d) + x.bandwidth() / 2;
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - 8).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
    const years = Array.from(new Set(rows.map((r) => r.date.slice(0, 4))));
    const step = [1, 2, 5, 10].find((n) => years.length / n <= Math.max(1, (W - ml) / 56)) || 10;
    const xt = rows.map((r) => r.date).filter((d) => d.slice(5, 7) === '01' && +d.slice(0, 4) % step === 0);
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).tickValues(xt).tickSize(0).tickFormat((d) => d.slice(0, 4))));
    svg.append('g').selectAll('g').data(stack).join('g').attr('fill', (s, i) => PARTS[i].color)
      .selectAll('rect').data((s) => s).join('rect')
      .attr('x', (d) => x(d.data.date)).attr('width', x.bandwidth())
      .attr('y', (d) => y(Math.max(d[0], d[1]))).attr('height', (d) => Math.abs(y(d[0]) - y(d[1])));
    const lineColor = J.PAL[1];
    svg.append('path').attr('d', d3.line().x((r) => cx(r.date)).y((r) => y(r.all))(rows))
      .attr('fill', 'none').attr('stroke', lineColor).attr('stroke-width', 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    legend('cpi-contrib-legend', [{ key: 'all', name: 'CPI, y/y', color: lineColor }].concat(PARTS.filter((p) => p.key !== 'services'), PARTS.filter((p) => p.key === 'services')));
    const card = document.getElementById('cpi-contrib'), tip = J.tip(card);
    const hl = svg.append('rect').attr('fill', 'var(--color-fg)').attr('opacity', 0.06).attr('display', 'none');
    const sg = (v) => (v == null ? '—' : (v > 0 ? '+' : '') + J.f1(v) + 'ppt');
    svg.append('rect').attr('x', ml).attr('width', W - ml - 8).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const i = Math.max(0, Math.min(rows.length - 1, Math.floor((d3.pointer(ev)[0] - ml) / x.step())));
        const r = rows[i];
        hl.attr('display', null).attr('x', x(r.date) - x.step() * x.paddingInner() / 2).attr('width', x.step()).attr('y', 0).attr('height', H - 22);
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, mLabel(r.date), [[lineColor, 'CPI, y/y', pct(r.all)]].concat(PARTS.map((p) => [p.color, p.name, sg(r[p.key])])),
          ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { hl.attr('display', 'none'); tip.style.display = 'none'; });
  }

  function saChart() {
    const box = document.getElementById('cpi-sa-chart');
    const D = dash.data('cpi_series');
    if (failed(D.status)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    const k = S.sa;
    const rows = wide(D.data, 'national', [k], 'mom', 'cpi-momentum');
    if (!rows.length) { box.replaceChildren(); return; }
    const W = box.clientWidth, H = 280;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const vals = rows.map((r) => r[k]);
    const y = d3.scaleLinear([Math.min(0, d3.min(vals)), Math.max(0, d3.max(vals))], [H - 24, 10]).nice();
    const ticks = y.ticks(5);
    const fmt = d3.format('.1f');
    const ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    const x = d3.scaleBand(rows.map((r) => r.date), [ml, W - 8]).padding(0.2);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - 8).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
    const years = Array.from(new Set(rows.map((r) => r.date.slice(0, 4))));
    const step = [1, 2, 5, 10].find((s) => years.length / s <= Math.max(1, (W - ml) / 56)) || 10;
    const xt = rows.map((r) => r.date).filter((d) => d.slice(5, 7) === '01' && +d.slice(0, 4) % step === 0);
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).tickValues(xt).tickSize(0).tickFormat((d) => d.slice(0, 4))));
    svg.append('g').selectAll('rect').data(rows).join('rect')
      .attr('x', (r) => x(r.date)).attr('width', x.bandwidth())
      .attr('y', (r) => y(Math.max(0, r[k]))).attr('height', (r) => Math.abs(y(r[k]) - y(0)))
      .attr('fill', J.PAL[0]);
    const card = document.getElementById('cpi-momentum'), tip = J.tip(card);
    const name = document.querySelector(`#cpi-sa-seg [data-s="${k}"]`).textContent;
    svg.append('rect').attr('x', ml).attr('width', W - ml).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const i = Math.max(0, Math.min(rows.length - 1, Math.floor((d3.pointer(ev)[0] - ml) / x.step())));
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, mLabel(rows[i].date), [[null, name + ', m/m SA', pct(rows[i][k])]], ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { tip.style.display = 'none'; });
  }

  function tiles() {
    const L = dash.data('cpi_latest');
    document.querySelectorAll('#cpi-headline [data-source="cpi_latest"]').forEach((s) => {
      if (L.status === 'ok' && L.data.length) { s.classList.remove('dash-skeleton'); s.textContent = J.f1(L.data[0][s.dataset.field]); }
      else if (L.status !== 'loading') { s.classList.remove('dash-skeleton'); s.textContent = '—'; }
    });
    const P = dash.data('ppi_latest');
    const hm = document.getElementById('cpi-month');
    if (L.status !== 'loading' && P.status !== 'loading') {
      hm.classList.remove('dash-skeleton');
      const parts = [];
      if (L.status === 'ok' && L.data.length) parts.push(`${mLabel(L.data[0].date)} CPI`);
      if (P.status === 'ok' && P.data.length) parts.push(`${mLabel(P.data[0].date)} PPI`);
      hm.textContent = parts.join(', ');
    }
    document.querySelectorAll('#cpi-headline [data-source="ppi_latest"]').forEach((s) => {
      if (P.status === 'ok' && P.data.length) { s.classList.remove('dash-skeleton'); s.textContent = J.f1(P.data[0][s.dataset.field]); }
      else if (P.status !== 'loading') { s.classList.remove('dash-skeleton'); s.textContent = '—'; }
    });
    const PR = dash.data('ppi_release');
    document.querySelectorAll('[data-source="ppi_release"][data-field="label"]').forEach((s) => {
      if (PR.status === 'ok' && PR.data.length) { s.classList.remove('dash-skeleton'); s.textContent = PR.data[0].label; }
      else if (PR.status !== 'loading') { s.classList.remove('dash-skeleton'); s.textContent = ''; }
    });
    const R = dash.data('cpi_release');
    document.querySelectorAll('[data-source="cpi_release"][data-field="label"]').forEach((s) => {
      if (R.status === 'ok' && R.data.length) { s.classList.remove('dash-skeleton'); s.textContent = R.data[0].label; }
      else if (R.status !== 'loading') { s.classList.remove('dash-skeleton'); s.textContent = ''; }
    });
  }

  function moversTable() {
    const tb = document.querySelector('#cpi-movers-table tbody');
    const M = dash.data('cpi_movers');
    if (failed(M.status)) { tb.replaceChildren(); const td = tb.insertRow().insertCell(); td.colSpan = 4; J.fail(td); return; }
    if (M.status !== 'ok') return;
    const k = S.movers === 6 ? 'avg6' : 'avg3';
    const rows = M.data.filter((r) => r[k] != null);
    const up = rows.slice().sort((a, b) => b[k] - a[k] || b.yoy - a.yoy).slice(0, 5);
    const down = rows.slice().sort((a, b) => a[k] - b[k] || a.yoy - b.yoy).slice(0, 5);
    const date = M.data.length ? M.data[0].date : null;
    document.getElementById('cpi-movers-units').textContent = date ? `%, ppt, ${S.movers}-month average to ${mLabel(date)}` : '%, ppt';
    document.getElementById('cpi-movers-avg').textContent = `Contribution, ${S.movers}m avg.`;
    tb.replaceChildren();
    [['Largest positive contributions', up], ['Largest negative contributions', down]].forEach(([g, list], gi) => {
      const gr = tb.insertRow(); gr.className = 'grp' + (gi ? ' sep' : '');
      const gtd = gr.insertCell(); gtd.colSpan = 4; gtd.textContent = g;
      list.forEach((r) => {
        const tr = tb.insertRow(); tr.dataset.key = r.name;
        [['name', r.name], ['weight', r.weight], ['yoy', r.yoy], [k, r[k]]].forEach(([f, v]) => {
          const td = tr.insertCell();
          if (f === 'name') { td.textContent = v; return; }
          td.textContent = v == null ? '' : (f === 'weight' ? String(Math.round(v)) : (f === k ? d3.format('.2f')(v) : J.f1(v)));
          if (v != null && v < 0 && f !== 'weight') td.classList.add('neg');
        });
      });
    });
  }


  function takeaway() {
    const p = document.getElementById('cpi-takeaway');
    const L = dash.data('cpi_latest');
    if (L.status !== 'ok' || !L.data.length) { if (failed(L.status)) p.replaceChildren(); return; }
    const a = L.data[0];
    const mk = (field) => { const b = document.createElement('b'); b.dataset.source = 'cpi_latest'; b.dataset.field = field; b.dataset.row = '0'; b.textContent = J.f1(a[field]); return b; };
    const t = (x) => p.append(document.createTextNode(x));
    p.replaceChildren();
    const pc = () => { const b = document.createElement('b'); b.textContent = '%'; p.append(b); };
    const mb = (d) => t(mLabel(d));
    t('In '); mb(a.date); t(', consumer prices were '); p.append(mk('all_yoy')); pc(); t(' higher than a year earlier. Core (less fresh food) was ');
    p.append(mk('core_yoy')); pc(); t(' and less fresh food and energy '); p.append(mk('core_core_yoy'));
    pc(); t('.');
    const P = dash.data('ppi_latest');
    if (P.status === 'ok' && P.data.length && P.data[0].ppi_yoy != null) {
      const q = P.data[0];
      const b = document.createElement('b'); b.dataset.source = 'ppi_latest'; b.dataset.field = 'ppi_yoy'; b.dataset.row = '0'; b.textContent = J.f1(q.ppi_yoy);
      t(` Producer prices were up `); p.append(b); pc(); t(' y/y in '); mb(q.date); t('.');
    }
  }

  function table() {
    const tb = document.querySelector('#cpi-table tbody');
    const C = dash.data('cpi_table');
    if (failed(C.status)) { tb.replaceChildren(); const td = tb.insertRow().insertCell(); td.colSpan = 6; J.fail(td); return; }
    if (C.status !== 'ok') return;
    document.getElementById('cpi-table-units').textContent = C.data.length && C.data[0].date ? `%, ${mLabel(C.data[0].date)}` : '%';
    const cols = ['label', 'ann1', 'ann2', 'ann3', 'ann6', 'yoy12'];
    tb.replaceChildren();
    C.data.forEach((r) => {
      const tr = tb.insertRow();
      if (r.series === 'all') tr.className = 'gdp';
      cols.forEach((col) => {
        const td = tr.insertCell();
        if (col === 'label') { td.textContent = r.label; return; }
        const v = r[col];
        td.textContent = v == null ? '' : J.f1(v);
        if (v != null && v < 0) td.classList.add('neg');
      });
    });
  }


  const C = J.PAL;
  J.redrawCpi = () => {
    if (!visible()) return;
    {
      const ms = [
        { key: 'all', name: 'CPI', color: C[1] },
        { key: 'core', name: 'Less fresh food', color: C[5] },
        { key: 'core_core', name: 'Less fresh food and energy', color: C[4] },
      ];
      if (S.measures === 'national') {
        // Core 3 (national only): Asia Decoded calculation
        lineChart('cpi-measures-chart', 'cpi-measures', 'cpi-measures-legend', 'national', ms.concat([{ key: 'core3', name: 'Less food and energy', color: C[0] }]), 280, {
          ids: ['cpi_series', 'jp_cpi_core3'],
          rows: (cpi, k3) => {
            const by = new Map();
            cpi.forEach((r) => {
              if (r.area !== 'national' || !['all', 'core', 'core_core'].includes(r.series) || r.yoy == null) return;
              if (!by.has(r.date)) by.set(r.date, { date: r.date });
              by.get(r.date)[r.series] = r.yoy;
            });
            k3.forEach((r) => { if (r.yoy !== '' && by.has(r.date)) by.get(r.date).core3 = Math.round(Number(r.yoy) * 10) / 10; });
            return J.slice(Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1)), 'cpi-measures');
          },
        });
      } else {
        lineChart('cpi-measures-chart', 'cpi-measures', 'cpi-measures-legend', S.measures, ms, 280);
      }
    }
    lineChart('ppi-cpi-chart', 'ppi-cpi', 'ppi-cpi-legend', 'national', [
      { key: 'ppi', name: 'Producer prices (PPI)', color: C[0] },
      { key: 'cpi', name: 'Consumer prices (CPI)', color: C[1] },
    ], 280, {
      ids: ['cpi_series', 'ppi_series'],
      rows: (cpi, ppi) => {
        const by = new Map();
        const put = (d, k, v) => { if (v == null) return; if (!by.has(d)) by.set(d, { date: d }); by.get(d)[k] = v; };
        cpi.forEach((r) => { if (r.area === 'national' && r.series === 'all') put(r.date, 'cpi', r.yoy); });
        ppi.forEach((r) => { if (r.series === 'ppi') put(r.date, 'ppi', r.yoy); });
        const out = Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
        return J.slice(out, 'ppi-cpi');
      },
    });
    lineChart('cpi-gs-chart', 'cpi-gs', 'cpi-gs-legend', S.gs, [
      { key: 'goods', name: 'Goods', color: C[0] },
      { key: 'services', name: 'Services', color: C[1] },
      { key: 'services_ex_rent', name: 'Services less imputed rent', color: C[1], dash: true },
    ], 280);
    lineChart('cpi-drivers-chart', 'cpi-drivers', 'cpi-drivers-legend', S.drivers, [
      { key: 'fresh_food', name: 'Fresh food', color: C[0] },
      { key: 'food_ex_fresh', name: 'Food less fresh food', color: C[5] },
      { key: 'energy', name: 'Energy', color: C[1] },
    ], 280);
    saChart();
    lineChart('cpi-diffusion-chart', 'cpi-diffusion', 'cpi-diffusion-legend', 'national', [
      { key: 'diffusion', name: 'Diffusion index (rising minus falling)', color: C[1] },
      { key: 'share_rising', name: 'Rising', color: C[5] },
      { key: 'share_falling', name: 'Falling', color: C[0] },
    ], 280, {
      ids: ['jp_cpi_diffusion'],
      rows: (d) => {
        const out = d.map((r) => ({ date: r.date, diffusion: Number(r.diffusion), share_rising: Number(r.share_rising), share_falling: Number(r.share_falling) }))
          .sort((a, b) => (a.date < b.date ? -1 : 1));
        return J.slice(out, 'cpi-diffusion');
      },
    });
    ymChart();
    contribChart();
  };

  J.redrawTrade = () => {
    if (document.getElementById('trade').hidden) return;
    lineChart('trade-prices-chart', 'trade-prices', 'trade-prices-legend', 'national', [
      { key: 'import_yen', name: 'Import prices', color: C[0] },
      { key: 'export_yen', name: 'Export prices', color: C[1] },
    ], 280, {
      ids: ['ppi_series'],
      rows: (ppi) => {
        const by = new Map();
        ppi.forEach((r) => {
          if (!['import_yen', 'export_yen'].includes(r.series) || r.yoy == null) return;
          if (!by.has(r.date)) by.set(r.date, { date: r.date });
          by.get(r.date)[r.series] = r.yoy;
        });
        const out = Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
        return J.slice(out, 'trade-prices');
      },
    });
  };

  dash.onData(() => { tiles(); takeaway(); table(); moversTable(); J.redrawCpi(); J.redrawTrade(); });
  if (location.hash.slice(1) === 'inflation') J.redrawCpi();
  if (location.hash.slice(1) === 'trade') J.redrawTrade();
})();
