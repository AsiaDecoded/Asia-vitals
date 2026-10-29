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
    ['all', 'core', 'core_core', 'ex_food_energy', 'fresh_food', 'food_ex_fresh', 'energy', 'goods', 'services'].forEach((k) => {
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
    const SA = [['all', 'All items'], ['core', 'Core (less fresh food)'], ['core_core', 'Core 1 (less fresh food and energy)'], ['goods', 'Goods'], ['services', 'Services']];
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
    // Core 2: Asia Decoded calculation, no seasonally adjusted index, so 12-month only
    const k3 = jp_cpi_core3.find((r) => r.date === nat);
    rows.splice(3, 0, { label: 'Core 2 (less food and energy)', series: 'core3', date: nat, ann1: null, ann2: null, ann3: null, ann6: null,
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

// Heat and contribution tables: Statistics Bureau Table 5 rows (weight, y/y, contribution), from Jan 2026.
const GROUP_NAMES = { all: 'CPI', core: 'Core (less fresh food)', core1: 'Core 1 (less fresh food and energy)', core2: 'Core 2 (less food and energy)' };
const groupRows = (jp_cpi_groups, field) => {
  const n = (v) => (v === '' || v == null ? null : Number(v));
  const latest = jp_cpi_groups.reduce((m, r) => (r.date > m ? r.date : m), '');
  const W = new Map(jp_cpi_groups.filter((r) => r.date === latest).map((r) => [r.series, n(r.weight)]));
  return jp_cpi_groups.filter((r) => r.date >= '2026-01-01' && n(r[field]) != null)
    .map((r) => ({ date: r.date, series: r.series, name: GROUP_NAMES[r.series] || r.label, order: Number(r.order), block: r.block,
      parent: r.parent || null, weight: W.has(r.series) ? W.get(r.series) : null, value: n(r[field]) }));
};

dash.calc('cpi_heat', {
  title: 'CPI inflation by group, y/y',
  description: 'Statistics Bureau published y/y (Table 5 of each monthly report), with published 2025-base weights per 10,000, for all items, the core measures, fresh food, food less fresh food, energy and its five items, the 10 major groups with selected subgroups, and goods and services, from Jan 2026; plus Core 2 (less food and energy, Asia Decoded calculation, no published weight).',
  inputs: ['jp_cpi_groups', 'jp_cpi_core3'],
  fn: (jp_cpi_groups, jp_cpi_core3) => {
    const rows = groupRows(jp_cpi_groups, 'yoy');
    jp_cpi_core3.filter((r) => r.date >= '2026-01-01' && r.yoy !== '').forEach((r) => {
      rows.push({ date: r.date, series: 'core2', name: GROUP_NAMES.core2, order: 2.5, block: 'top', parent: null, weight: null,
        value: Math.round(Number(r.yoy) * 10) / 10 });
    });
    return rows;
  },
});

dash.calc('cpi_ctab', {
  title: 'Contributions to CPI y/y',
  description: 'Statistics Bureau published contributions (ppt) to the all-items y/y (Table 5 of each monthly report), with published 2025-base weights per 10,000, for the same rows as the y/y table (except Core 2), from Jan 2026.',
  inputs: ['jp_cpi_groups'],
  fn: (jp_cpi_groups) => groupRows(jp_cpi_groups, 'contrib_yoy'),
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
  const S = { months: 120, measures: 'national', gs: 'national', drivers: 'national', fe: 'food', svc: 'medical_services', sa: 'all_sa', tmonths: 120, movers: 3 };
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
  seg('cpi-fe-seg', 'fe', 's', String);
  seg('cpi-svc-seg', 'svc', 's', String);

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

  // CPI momentum: 3m/3m annualised change in the seasonally adjusted index (bars), with CPI y/y (line, as published) on the headline tab.
  function saChart() {
    const box = document.getElementById('cpi-sa-chart');
    const D = dash.data('cpi_series');
    if (failed(D.status)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    const k = S.sa;
    // 3m/3m annualised: average of the SA index over the latest three months against the three before, at an annual rate
    const m3 = (key) => {
      const lv = D.data.filter((r) => r.area === 'national' && r.series === key && r.index != null)
        .sort((p, q) => (p.date < q.date ? -1 : 1)).map((r) => [r.date, r.index]);
      const out = new Map();
      for (let i = 5; i < lv.length; i++) {
        const a3 = (lv[i][1] + lv[i - 1][1] + lv[i - 2][1]) / 3, b3 = (lv[i - 3][1] + lv[i - 4][1] + lv[i - 5][1]) / 3;
        out.set(lv[i][0], (Math.pow(a3 / b3, 4) - 1) * 100);
      }
      return out;
    };
    const name = document.querySelector(`#cpi-sa-seg [data-s="${k}"]`).dataset.name;
    const BAR = { key: k, name: name + ', 3m/3m annualised, sa', color: J.PAL[4], vals: m3(k) };
    const LINES = k === 'all_sa'
      ? [{ key: 'yoy', name: 'CPI, y/y', color: J.PAL[1], vals: new Map(D.data.filter((r) => r.area === 'national' && r.series === 'all' && r.yoy != null).map((r) => [r.date, r.yoy])) }]
      : [];
    const all = Array.from(BAR.vals.keys()).sort().map((d) => {
      const r = { date: d };
      [BAR].concat(LINES).forEach((s) => { r[s.key] = s.vals.has(d) ? s.vals.get(d) : null; });
      return r;
    });
    const rows = J.slice(all, 'cpi-momentum');
    if (!rows.length) { box.replaceChildren(); return; }
    legend('cpi-sa-legend', LINES.map((s) => ({ name: s.name, color: s.color })).concat([{ name: BAR.name, color: BAR.color, bar: true }]));
    const W = box.clientWidth, H = 280;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const vals = [];
    rows.forEach((r) => [BAR].concat(LINES).forEach((s) => { if (r[s.key] != null) vals.push(r[s.key]); }));
    const y = d3.scaleLinear([Math.min(0, d3.min(vals)), Math.max(0, d3.max(vals))], [H - 24, 10]).nice();
    const ticks = y.ticks(5);
    const fmt = d3.format(ticks.some((v) => !Number.isInteger(v)) ? '.1f' : '.0f');
    const ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    const x = d3.scaleBand(rows.map((r) => r.date), [ml, W - 8]).padding(0.2);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - 8).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
    const years = Array.from(new Set(rows.map((r) => r.date.slice(0, 4))));
    const step = [1, 2, 5, 10].find((s) => years.length / s <= Math.max(1, (W - ml) / 56)) || 10;
    const xt = rows.map((r) => r.date).filter((d) => d.slice(5, 7) === '01' && +d.slice(0, 4) % step === 0);
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).tickValues(xt).tickSize(0).tickFormat((d) => d.slice(0, 4))));
    svg.append('g').selectAll('rect').data(rows.filter((r) => r[BAR.key] != null)).join('rect')
      .attr('x', (r) => x(r.date)).attr('width', x.bandwidth())
      .attr('y', (r) => y(Math.max(0, r[BAR.key]))).attr('height', (r) => Math.abs(y(r[BAR.key]) - y(0)))
      .attr('fill', BAR.color);
    LINES.forEach((s) => {
      svg.append('path').datum(rows.filter((r) => r[s.key] != null)).attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', 2.5)
        .attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round')
        .attr('d', d3.line().x((r) => x(r.date) + x.bandwidth() / 2).y((r) => y(r[s.key])));
    });
    const card = document.getElementById('cpi-momentum'), tip = J.tip(card);
    svg.append('rect').attr('x', ml).attr('width', W - ml).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const i = Math.max(0, Math.min(rows.length - 1, Math.floor((d3.pointer(ev)[0] - ml) / x.step())));
        const cr = card.getBoundingClientRect();
        const items = LINES.concat([BAR]).map((s) => [s.color, s.name.replace('annualised', 'ann.'), pct(rows[i][s.key])]);
        J.showTip(card, tip, mLabel(rows[i].date), items, ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { tip.style.display = 'none'; });
  }

  // Heat tables (y/y and contributions) by month, Jan 2026 on. Rows with a parent sit under it and open with the arrow.
  // y/y: every row coloured on its own range (green low, yellow middle, red high). Contributions: the 10 major groups only.
  function heatTable(tblId, calcId, openKey, scrollKey, dp, colourAll) {
    const tbl = document.getElementById(tblId);
    if (!tbl) return;
    const D = dash.data(calcId);
    if (failed(D.status)) { tbl.replaceChildren(); return; }
    if (D.status !== 'ok') return;
    const dates = Array.from(new Set(D.data.map((r) => r.date))).sort();
    const info = new Map();
    D.data.forEach((r) => { if (!info.has(r.series)) info.set(r.series, r); });
    const keys = Array.from(info.keys()).sort((p, q) => info.get(p).order - info.get(q).order);
    const val = new Map(D.data.map((r) => [`${r.series}|${r.date}`, r.value]));
    const kids = {};
    keys.forEach((k) => { const p = info.get(k).parent; if (p) (kids[p] = kids[p] || []).push(k); });
    const mix = (c0, c1, f) => `rgb(${c0.map((c, i) => Math.round(c + (c1[i] - c) * f)).join(',')})`;
    const G = [99, 190, 123], Y = [255, 235, 132], R = [248, 105, 107];
    const OPEN = (J.state[openKey] = J.state[openKey] || {});
    const fmt = d3.format(dp === 2 ? '.2f' : '.1f');
    tbl.replaceChildren();
    const head = tbl.createTHead().insertRow();
    ['', 'Weight'].concat(dates.map((d) => `${MONTHS[+d.slice(5, 7) - 1]} ${d.slice(2, 4)}`)).forEach((t) => {
      const th = document.createElement('th'); th.textContent = t; head.appendChild(th);
    });
    const tb = tbl.createTBody();
    let blk = null;
    keys.forEach((k) => {
      const it = info.get(k);
      if (blk && it.block !== blk) { const sp = tb.insertRow(); sp.className = 'spacer'; sp.insertCell().colSpan = dates.length + 2; }
      blk = it.block;
      const tr = tb.insertRow();
      const nc = tr.insertCell(); nc.dataset.label = it.name;
      if (kids[k]) {
        const open = !!OPEN[k];
        const b = document.createElement('button'); b.type = 'button'; b.className = 'heat-tog';
        b.setAttribute('aria-expanded', String(open));
        const ar = document.createElement('span'); ar.className = 'heat-arrow'; ar.textContent = open ? '▾' : '▸';
        b.append(document.createTextNode(it.name + ' '), ar);
        b.addEventListener('click', () => { OPEN[k] = !OPEN[k]; heatTable(tblId, calcId, openKey, scrollKey, dp, colourAll); });
        nc.appendChild(b);
      } else nc.textContent = it.name;
      if (it.parent) { tr.className = 'sub'; if (!OPEN[it.parent]) tr.hidden = true; }
      else if (it.block === 'top') tr.className = 'lead';
      const wc = tr.insertCell(); wc.className = 'wt'; wc.textContent = it.weight == null ? '' : d3.format('.1f')(it.weight / 100);
      const vs = dates.map((d) => val.get(`${k}|${d}`)).filter((v) => v != null);
      const lo = Math.min(...vs), hi = Math.max(...vs);
      const colour = colourAll || it.block === 'div';
      dates.forEach((d) => {
        const td = tr.insertCell(); const v = val.get(`${k}|${d}`);
        if (v == null) return;
        const f = fmt(v);
        td.textContent = /^-0\.0+$/.test(f) ? f.slice(1) : f;
        td.className = 'heat';
        if (!colour) return;
        const t = hi > lo ? (v - lo) / (hi - lo) : 0.5;
        td.style.background = t > 0.5 ? mix(Y, R, (t - 0.5) / 0.5) : mix(G, Y, t / 0.5);
        td.style.color = '#1a1a1a';
      });
    });
    heatScroll(tblId, scrollKey);
  }

  // A heat table scrolls sideways under the month columns only: the label and weight columns stay put (sticky) and a
  // scroll bar drawn beneath the table drives it (and follows it when the table is swiped).
  const heatRO = {};
  function heatScroll(id, sk) {
    const tbl = document.getElementById(id);
    const wrap = tbl && tbl.closest('.jg-tablewrap');
    if (!wrap) return;
    let bw = wrap.nextElementSibling;
    if (!bw || !bw.classList.contains('heat-barwrap')) {
      bw = document.createElement('div'); bw.className = 'heat-barwrap';
      const track = document.createElement('div'); track.className = 'heat-track';
      const thumb = document.createElement('div'); thumb.className = 'heat-thumb';
      track.appendChild(thumb); bw.appendChild(track); wrap.after(bw);
      const max = () => wrap.scrollWidth - wrap.clientWidth;
      const room = () => track.clientWidth - thumb.offsetWidth;
      let drag = null;
      const touched = () => { J.state[sk] = true; };
      ['wheel', 'touchstart', 'keydown'].forEach((ev) => wrap.addEventListener(ev, touched, { passive: true }));
      thumb.addEventListener('pointerdown', (e) => { touched(); drag = { x: e.clientX, s: wrap.scrollLeft }; thumb.setPointerCapture(e.pointerId); e.preventDefault(); });
      thumb.addEventListener('pointermove', (e) => { if (!drag || room() <= 0) return; wrap.scrollLeft = drag.s + (e.clientX - drag.x) * max() / room(); });
      thumb.addEventListener('pointerup', () => { drag = null; });
      thumb.addEventListener('pointercancel', () => { drag = null; });
      track.addEventListener('pointerdown', (e) => {
        if (e.target !== track) return;
        touched();
        const r = track.getBoundingClientRect();
        wrap.scrollLeft = ((e.clientX - r.left - thumb.offsetWidth / 2) / Math.max(1, room())) * max();
      });
      wrap.addEventListener('scroll', () => place());
    }
    const track = bw.firstChild, thumb = track.firstChild;
    function place() {
      const m = wrap.scrollWidth - wrap.clientWidth, r = track.clientWidth - thumb.offsetWidth;
      thumb.style.transform = `translateX(${m > 0 ? (wrap.scrollLeft / m) * r : 0}px)`;
    }
    const fit = () => {
      const row = tbl.tHead && tbl.tHead.rows[0];
      if (!row || row.cells.length < 3) return;
      const w1 = row.cells[0].getBoundingClientRect().width, w2 = row.cells[1].getBoundingClientRect().width;
      tbl.style.setProperty('--heat-c1', `${w1}px`);
      const fixed = w1 + w2, view = wrap.clientWidth - fixed, full = wrap.scrollWidth - fixed;
      track.style.marginLeft = `${fixed}px`;
      track.hidden = wrap.scrollWidth - wrap.clientWidth <= 1;
      thumb.style.width = `${Math.max(24, (view / Math.max(1, full)) * track.clientWidth)}px`;
      if (!J.state[sk]) {
        // start at the latest months, with the first visible month column whole
        tbl.style.marginRight = '0px';
        wrap.scrollLeft = wrap.scrollWidth;
        const cells = Array.from(row.cells).slice(2);
        const first = cells.find((cell) => cell.offsetLeft - fixed >= wrap.scrollLeft - 1);
        if (first && first.offsetLeft - fixed > wrap.scrollLeft + 0.5) {
          tbl.style.marginRight = `${first.offsetLeft - fixed - wrap.scrollLeft}px`;
          wrap.scrollLeft = first.offsetLeft - fixed;
        }
      }
      place();
    };
    fit();
    if (!heatRO[id] && window.ResizeObserver) { heatRO[id] = new ResizeObserver(() => fit()); heatRO[id].observe(wrap); }
  }
  const heat = () => heatTable('cpi-heat-table', 'cpi_heat', 'heatOpen', 'heatScrolled', 1, true);
  const ctab = () => heatTable('cpi-ctab-table', 'cpi_ctab', 'ctabOpen', 'ctabScrolled', 2, false);

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
    p.append(mk('core_yoy')); pc(); t(' and Core 1 (less fresh food and energy) '); p.append(mk('core_core_yoy'));
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
        { key: 'core', name: 'Core', color: C[5] },
        { key: 'core_core', name: 'Core 1', color: C[4] },
      ];
      if (S.measures === 'national') {
        // Core 2 (national only): Asia Decoded calculation
        lineChart('cpi-measures-chart', 'cpi-measures', 'cpi-measures-legend', 'national', ms.concat([{ key: 'core3', name: 'Core 2', color: C[0] }]), 280, {
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
    if (S.fe === 'food' && S.drivers === 'national') {
      // national: adds food and non-alcoholic beverages (Statistics Bureau COICOP 01, published, from 2021)
      lineChart('cpi-drivers-chart', 'cpi-drivers', 'cpi-drivers-legend', 'national', [
        { key: 'fresh_food', name: 'Fresh food', color: C[0] }, { key: 'food_ex_fresh', name: 'Food less fresh food', color: C[5] },
        { key: 'fnab', name: 'Food and non-alcoholic beverages', color: C[1] },
      ], 280, {
        ids: ['cpi_series', 'jp_cpi_food'],
        rows: (cpi, food) => {
          const by = new Map();
          const put = (d, k, v) => { if (v == null) return; if (!by.has(d)) by.set(d, { date: d }); by.get(d)[k] = v; };
          cpi.forEach((r) => { if (r.area === 'national' && (r.series === 'fresh_food' || r.series === 'food_ex_fresh')) put(r.date, r.series, r.yoy); });
          food.forEach((r) => { if (r.yoy !== '') put(r.date, 'fnab', Math.round(Number(r.yoy) * 10) / 10); });
          return J.slice(Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1)), 'cpi-drivers');
        },
      });
    } else {
      lineChart('cpi-drivers-chart', 'cpi-drivers', 'cpi-drivers-legend', S.drivers, S.fe === 'energy'
        ? [{ key: 'electricity', name: 'Electricity', color: C[1] }, { key: 'city_gas', name: 'City gas', color: C[0] },
          { key: 'lp_gas', name: 'LP gas', color: C[2] }, { key: 'kerosene', name: 'Kerosene', color: C[4] }, { key: 'gasoline', name: 'Gasoline', color: C[3] }]
        : [{ key: 'fresh_food', name: 'Fresh food', color: C[0] }, { key: 'food_ex_fresh', name: 'Food less fresh food', color: C[5] }], 280);
    }
    {
      const b = document.querySelector(`#cpi-svc-seg [data-s="${S.svc}"]`);
      lineChart('cpi-svc-chart', 'cpi-svc', 'cpi-svc-legend', 'national', S.svc === 'rent'
        ? [{ key: 'private_rent', name: 'Private rent', color: C[0] }, { key: 'imputed_rent', name: 'Imputed rent', color: C[1] }]
        : [{ key: S.svc, name: b ? b.dataset.name : '', color: C[0] }], 280);
    }
    saChart();
    lineChart('cpi-fe-chart', 'cpi-fe', 'cpi-fe-legend', 'national', [
      { key: 'food', name: 'Food and non-alcoholic beverages', color: C[1] },
      { key: 'energy', name: 'Energy', color: C[0] },
    ], 280, {
      ids: ['cpi_series', 'jp_cpi_food'],
      rows: (cpi, food) => {
        // Food: Statistics Bureau COICOP 01 (published) from Jan 2021; energy as published
        const by = new Map();
        const put = (d, k, v) => { if (v == null) return; if (!by.has(d)) by.set(d, { date: d }); by.get(d)[k] = v; };
        food.forEach((r) => { if (r.yoy !== '') put(r.date, 'food', Math.round(Number(r.yoy) * 10) / 10); });
        const first = food.length ? food.map((r) => r.date).sort()[0] : '9999';
        cpi.forEach((r) => { if (r.area === 'national' && r.series === 'energy' && r.date >= first) put(r.date, 'energy', r.yoy); });
        return J.slice(Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1)), 'cpi-fe');
      },
    });
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

  dash.onData(() => { tiles(); takeaway(); table(); moversTable(); heat(); ctab(); J.redrawCpi(); J.redrawTrade(); });
  if (location.hash.slice(1) === 'inflation') J.redrawCpi();
  if (location.hash.slice(1) === 'trade') J.redrawTrade();
})();
