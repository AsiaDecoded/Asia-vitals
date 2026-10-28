// Inflation tab: Thailand CPI (TPSO, 2023 = 100), PPI (2021 = 100), export and import prices (2012 = 100), all as published.

const tnum = (v) => (v === '' || v == null ? null : Number(v));

dash.calc('cpi_series', {
  title: 'CPI series',
  description: 'Every CPI row (whole country, Bangkok and vicinity, low-income households) with its cells read as numbers.',
  inputs: ['th_cpi'],
  fn: (th_cpi) => th_cpi.map((r) => ({
    date: r.date, area: r.area, series: r.series, code: r.code, label: r.label, group: r.group,
    order: Number(r.order), index: r.index === '' ? null : Number(r.index), yoy: r.yoy === '' ? null : Number(r.yoy),
    weight: r.weight === '' ? null : Number(r.weight),
  })),
});

dash.calc('cpi_latest', {
  title: 'Latest month and the one before',
  description: 'Published y/y for the latest month and the month before: all items, core, CPI excluding food and energy, fresh food, energy, low-income households, Bangkok and vicinity.',
  inputs: ['cpi_series'],
  fn: (cpi_series) => {
    const row = {};
    [['all', 'national', 'all'], ['core', 'national', 'core'], ['ex_food_energy', 'national', 'ex_food_energy'],
      ['fresh_food', 'national', 'fresh_food'], ['energy', 'national', 'energy'], ['low', 'lowincome', 'all'], ['bkk', 'bangkok', 'all']].forEach(([f, area, k]) => {
      const s = cpi_series.filter((r) => r.area === area && r.series === k && r.yoy != null).sort((a, b) => (a.date < b.date ? -1 : 1));
      const a = s[s.length - 1], b = s[s.length - 2];
      row[f + '_yoy'] = a ? a.yoy : null;
      row[f + '_yoy_prev'] = b ? b.yoy : null;
      if (f === 'all') row.date = a ? a.date : null;
    });
    return [row];
  },
});

dash.calc('cpi_div', {
  title: 'CPI by group',
  description: 'All items, TPSO special aggregates and the eight groups: published 2023 weight (% of CPI) and published y/y in the latest four months.',
  inputs: ['cpi_series'],
  fn: (cpi_series) => {
    const keep = ['all', 'core', 'ex_food_energy', 'fresh_food', 'energy', 'food', 'nonfood', 'apparel', 'housing', 'medical', 'transport', 'recreation', 'tobacco'];
    const nat = cpi_series.filter((r) => r.area === 'national' && keep.includes(r.series));
    const months = Array.from(new Set(nat.filter((r) => r.series === 'all' && r.yoy != null).map((r) => r.date))).sort().slice(-4);
    const by = new Map();
    nat.forEach((r) => {
      if (!by.has(r.series)) by.set(r.series, { name: r.label, series: r.series, weight: r.weight });
      const i = months.indexOf(r.date);
      if (i >= 0) by.get(r.series)['m' + (3 - i)] = r.yoy;
    });
    return keep.filter((k) => by.has(k)).map((k) => by.get(k))
      .map((r) => ({ name: r.name, series: r.series, weight: r.weight, m3: r.m3 ?? null, m2: r.m2 ?? null, m1: r.m1 ?? null, m0: r.m0 ?? null, d0: months[3], d1: months[2], d2: months[1], d3: months[0] }));
  },
});

dash.calc('cpi_groups', {
  title: 'CPI by item group',
  description: 'Every series TPSO publishes for the whole country with its published 2023 weight where TPSO gives one (% of CPI) and published y/y in the latest three months and a year before the latest.',
  inputs: ['th_cpi_items', 'th_cpi_weights'],
  fn: (th_cpi_items, th_cpi_weights) => {
    const months = Array.from(new Set(th_cpi_items.map((r) => r.date))).sort();
    const m0 = months[months.length - 1];
    const ago = (k) => { const d = new Date(Date.UTC(+m0.slice(0, 4), +m0.slice(5, 7) - 1 - k, 1)); return d.toISOString().slice(0, 10); };
    const want = { y0: m0, y1: ago(1), y2: ago(2), y12: ago(12) };
    const y = new Map();
    th_cpi_items.forEach((r) => { if (r.yoy !== '') y.set(r.code + '|' + r.date, Number(r.yoy)); });
    return th_cpi_weights.map((w) => {
      const row = { code: w.code, name: w.name, level: Number(w.level), weight: w.weight === '' ? null : Number(w.weight), order: Number(w.order) };
      Object.entries(want).forEach(([k, d]) => { row[k] = y.has(w.code + '|' + d) ? y.get(w.code + '|' + d) : null; row['d_' + k] = d; });
      return row;
    }).sort((a, b) => a.order - b.order);
  },
});

dash.calc('ppi_series', {
  title: 'PPI series',
  description: 'Every producer price row (by product and by stage of processing) with its cells read as numbers.',
  inputs: ['th_ppi'],
  fn: (th_ppi) => th_ppi.map((r) => ({
    date: r.date, type: r.type, series: r.series, label: r.label, order: Number(r.order),
    index: tnum(r.index), yoy: tnum(r.yoy),
  })),
});

dash.calc('xmpi_series', {
  title: 'Export and import price series',
  description: 'Export and import price rows (all items and main groups) with their cells read as numbers.',
  inputs: ['th_xmpi'],
  fn: (th_xmpi) => th_xmpi.map((r) => ({
    date: r.date, type: r.type, series: r.series, label: r.label, order: Number(r.order),
    index: tnum(r.index), yoy: tnum(r.yoy),
  })),
});

dash.calc('ppi_latest', {
  title: 'Latest producer, export and import prices',
  description: 'PPI (all items), export and import prices: published y/y for the latest month and the month before.',
  inputs: ['ppi_series', 'xmpi_series'],
  fn: (ppi_series, xmpi_series) => {
    const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const two = (rows, k) => { const p = rows.filter((r) => r.series === k && r.yoy != null).sort((a, b) => (a.date < b.date ? -1 : 1)); return [p[p.length - 1], p[p.length - 2]]; };
    const [a, b] = two(ppi_series, 'ppi');
    const [x, x1] = two(xmpi_series, 'export');
    const [m, m1] = two(xmpi_series, 'import');
    const lab = (r) => (r ? MON[+r.date.slice(5, 7) - 1] + ' ' + r.date.slice(0, 4) : null);
    return [{ date: a ? a.date : null, label: lab(a), ppi_yoy: a ? a.yoy : null, ppi_yoy_prev: b ? b.yoy : null,
      xm_date: x ? x.date : null, xm_label: lab(x), export_yoy: x ? x.yoy : null, export_yoy_prev: x1 ? x1.yoy : null,
      import_yoy: m ? m.yoy : null, import_yoy_prev: m1 ? m1.yoy : null }];
  },
});

(() => {
  const J = window.JG;
  const S = { groupsLevel: 2, groupsQuery: '' };
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const mLabel = (d) => (d ? MONTHS[+d.slice(5, 7) - 1] + ' ' + d.slice(0, 4) : '');
  const visible = () => !document.getElementById('inflation').hidden;
  const pct = (v) => (v == null ? '—' : J.f1(v) + '%');
  const failed = (st) => st === 'error' || st === 'connect' || st === 'declined';
  const sortD = (a, b) => (a.date < b.date ? -1 : 1);

  // Default window for long series: the slider starts at this date (the reader can drag back to the start).
  const START = { 'ppi-cpi': '2016-01-01', 'cpi-measures': '2010-01-01', 'cpi-areas': '2010-01-01', 'cpi-fe': '2010-01-01', 'cpi-food': '2015-01-01', 'cpi-energy': '2015-01-01', 'ppi-sop': '2010-01-01' };
  const started = {};
  function startAt(id, all) {
    if (started[id] || !START[id] || !all.length || J.range[id]) return;
    started[id] = true;
    const i = all.findIndex((r) => r.date >= START[id]);
    if (i <= 0) return;
    const f = i / (all.length - 1);
    J.range[id] = [f, 1];
    const card = document.getElementById(id);
    const inp = card && card.querySelector('.ad-slider input');
    const sel = card && card.querySelector('.ad-slider-sel');
    if (inp) inp.value = Math.round(f * 1000);
    if (sel) sel.style.left = `${f * 100}%`;
  }

  function wide(rows, area, keys, id, areaOf) {
    const by = new Map();
    rows.forEach((r) => {
      const a = areaOf ? areaOf(r) : area;
      if (a == null || r.area !== a.area || r.series !== a.series || r.yoy == null) return;
      if (!by.has(r.date)) by.set(r.date, { date: r.date });
      by.get(r.date)[a.key] = r.yoy;
    });
    const all = Array.from(by.values()).sort(sortD);
    startAt(id, all);
    return J.slice(all, id);
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

  // series: [{key, name, color, area?, series?, dash?}]; rows come from cpi_series unless build is given.
  function lineChart(cardId, series, H, build) {
    const box = document.getElementById(cardId + '-chart');
    const ids = build ? build.ids : ['cpi_series'];
    const sts = ids.map((id) => dash.data(id));
    if (sts.some((d) => failed(d.status))) { J.fail(box); return; }
    if (sts.some((d) => d.status !== 'ok')) { box.replaceChildren(); return; }
    const keys = series.map((s) => s.key);
    const map = new Map(series.map((s) => [(s.area || 'national') + '|' + (s.series || s.key), s]));
    const rows = build ? build.rows(...sts.map((d) => d.data))
      : wide(sts[0].data, null, keys, cardId, (r) => { const s = map.get(r.area + '|' + r.series); return s ? { area: r.area, series: r.series, key: s.key } : null; });
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
    legend(cardId + '-legend', series);
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
        J.showTip(card, tip, mLabel(r.date), series.map((s) => [s.color, s.name, pct(r[s.key])]), ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); dots.forEach((d) => d.attr('display', 'none')); tip.style.display = 'none'; });
  }

  // Latest y/y by region as horizontal bars; a tick marks the rate a year earlier.
  function regionsChart() {
    const box = document.getElementById('cpi-regions-chart');
    const D = dash.data('th_cpi_regions');
    if (failed(D.status)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    const dates = Array.from(new Set(D.data.map((r) => r.date))).sort();
    const d0 = dates[dates.length - 1];
    const dY = `${+d0.slice(0, 4) - 1}${d0.slice(4)}`;
    const ago = new Map(D.data.filter((r) => r.date === dY).map((r) => [r.region, Number(r.yoy)]));
    const rows = D.data.filter((r) => r.date === d0 && r.yoy !== '')
      .map((r) => ({ region: r.region, v: Number(r.yoy), a: ago.has(r.region) ? ago.get(r.region) : null, agg: r.type === 'TG' }))
      .sort((a, b) => (b.agg - a.agg) || (b.v - a.v));
    document.getElementById('cpi-regions-units').textContent = `% y/y, ${mLabel(d0)}`;
    const W = box.clientWidth, rowH = 30, H = rows.length * rowH + 28;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const lw = Math.min(W * 0.42, J.textWidth(svg, rows.map((r) => r.region)) + 12);
    const vals = rows.flatMap((r) => [r.v, r.a]).filter((v) => v != null);
    const x = d3.scaleLinear([Math.min(0, d3.min(vals)), Math.max(0, d3.max(vals))], [lw, W - 40]).nice();
    const yb = d3.scaleBand(rows.map((r) => r.region), [4, H - 24]).padding(0.25);
    const ticks = x.ticks(Math.max(2, Math.round((W - lw) / 80)));
    svg.append('g').selectAll('line').data(ticks).join('line').attr('y1', 0).attr('y2', H - 24).attr('x1', x).attr('x2', x)
      .attr('stroke', (v) => (v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).tickValues(ticks).tickSize(0).tickFormat(d3.format('.0f'))));
    svg.append('g').selectAll('text').data(rows).join('text').attr('x', lw - 8).attr('y', (r) => yb(r.region) + yb.bandwidth() / 2).attr('dy', '0.35em')
      .attr('text-anchor', 'end').attr('font-size', 12).attr('fill', 'var(--ad-ink)').attr('font-weight', (r) => (r.agg ? 700 : null)).text((r) => r.region);
    const cNow = J.PAL[0], cAgo = J.PAL[3];
    svg.append('g').selectAll('rect').data(rows).join('rect')
      .attr('fill', (r) => (r.agg ? J.PAL[1] : cNow))
      .attr('x', (r) => x(Math.min(0, r.v))).attr('width', (r) => Math.abs(x(r.v) - x(0)))
      .attr('y', (r) => yb(r.region)).attr('height', yb.bandwidth());
    svg.append('g').selectAll('line').data(rows.filter((r) => r.a != null)).join('line')
      .attr('x1', (r) => x(r.a)).attr('x2', (r) => x(r.a)).attr('y1', (r) => yb(r.region) - 2).attr('y2', (r) => yb(r.region) + yb.bandwidth() + 2)
      .attr('stroke', cAgo).attr('stroke-width', 2.5);
    svg.append('g').selectAll('text.v').data(rows).join('text').attr('x', (r) => x(Math.max(0, r.v)) + 4).attr('y', (r) => yb(r.region) + yb.bandwidth() / 2).attr('dy', '0.35em')
      .attr('font-size', 12).attr('fill', 'var(--ad-ink)').text((r) => J.f1(r.v));
    legend('cpi-regions-legend', [{ name: mLabel(d0), color: cNow, bar: true }, { name: `Thailand, ${mLabel(d0)}`, color: J.PAL[1], bar: true }, { name: mLabel(dY), color: cAgo }]);
    const card = document.getElementById('cpi-regions'), tip = J.tip(card);
    svg.append('rect').attr('x', 0).attr('width', W).attr('height', H - 24).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const py = d3.pointer(ev)[1];
        const r = rows[Math.max(0, Math.min(rows.length - 1, Math.floor((py - 4) / yb.step())))];
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, r.region, [[cNow, mLabel(d0), pct(r.v)], [cAgo, mLabel(dY), pct(r.a)]], ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { tip.style.display = 'none'; });
  }

  const cell = (tr, v, f) => {
    const td = tr.insertCell();
    if (f === 'text') { td.textContent = v; return td; }
    td.textContent = v == null ? '' : (f === 'weight' ? v.toFixed(2) : J.f1(v));
    if (v != null && v < 0 && f !== 'weight') td.classList.add('neg');
    return td;
  };

  function divTable() {
    const tb = document.querySelector('#cpi-div-table tbody');
    const D = dash.data('cpi_div');
    if (failed(D.status)) { tb.replaceChildren(); const td = tb.insertRow().insertCell(); td.colSpan = 6; J.fail(td); return; }
    if (D.status !== 'ok' || !D.data.length) return;
    const r0 = D.data[0];
    const th = document.querySelectorAll('#cpi-div-table thead th');
    [r0.d3, r0.d2, r0.d1, r0.d0].forEach((d, i) => { th[2 + i].textContent = mLabel(d); });
    tb.replaceChildren();
    D.data.forEach((r, i) => {
      const tr = tb.insertRow(); tr.dataset.key = r.name;
      if (i < 5) tr.className = 'agg'; if (i === 5) tr.className = 'sep';
      cell(tr, r.name, 'text');
      cell(tr, r.weight, 'weight');
      ['m3', 'm2', 'm1', 'm0'].forEach((k, j) => { const td = cell(tr, r[k]); if (j < 2) td.classList.add('hide-narrow'); });
    });
  }

  function groupsTable() {
    const tb = document.querySelector('#cpi-groups-table tbody');
    const D = dash.data('cpi_groups');
    if (failed(D.status)) { tb.replaceChildren(); const td = tb.insertRow().insertCell(); td.colSpan = 6; J.fail(td); return; }
    if (D.status !== 'ok' || !D.data.length) return;
    const r0 = D.data[0];
    const th = document.querySelectorAll('#cpi-groups-table thead th');
    [r0.d_y12, r0.d_y2, r0.d_y1, r0.d_y0].forEach((d, i) => { th[2 + i].textContent = mLabel(d); });
    const q = S.groupsQuery.trim().toLowerCase();
    const rows = D.data.filter((r) => (q ? r.name.toLowerCase().includes(q) : r.level <= S.groupsLevel));
    tb.replaceChildren();
    rows.forEach((r) => {
      const tr = tb.insertRow(); tr.dataset.key = r.code;
      const lv = Math.min(4, Math.max(1, r.level));
      tr.className = 'l' + lv;
      const td = cell(tr, r.name, 'text');
      td.className = 'l' + lv;
      cell(tr, r.weight, 'weight');
      ['y12', 'y2', 'y1', 'y0'].forEach((k, j) => { const c = cell(tr, r[k]); if (j < 2) c.classList.add('hide-narrow'); });
    });
  }

  function tiles() {
    const L = dash.data('cpi_latest');
    document.querySelectorAll('#cpi-headline [data-source="cpi_latest"]').forEach((s) => {
      if (L.status === 'ok' && L.data.length) { s.classList.remove('dash-skeleton'); s.textContent = J.f1(L.data[0][s.dataset.field]); }
      else if (L.status !== 'loading') { s.classList.remove('dash-skeleton'); s.textContent = '—'; }
    });
    const P = dash.data('ppi_latest');
    document.querySelectorAll('#cpi-headline [data-source="ppi_latest"]').forEach((s) => {
      if (P.status === 'ok' && P.data.length) { s.classList.remove('dash-skeleton'); const v = P.data[0][s.dataset.field]; s.textContent = typeof v === 'number' ? J.f1(v) : (v || ''); }
      else if (P.status !== 'loading') { s.classList.remove('dash-skeleton'); s.textContent = '—'; }
    });
    const hm = document.getElementById('cpi-month');
    if (L.status !== 'loading' && P.status !== 'loading') {
      hm.classList.remove('dash-skeleton');
      const parts = [];
      if (L.status === 'ok' && L.data.length) parts.push(`${mLabel(L.data[0].date)} CPI`);
      if (P.status === 'ok' && P.data.length) { parts.push(`${mLabel(P.data[0].date)} PPI`); if (P.data[0].xm_date) parts.push(`${mLabel(P.data[0].xm_date)} export and import prices`); }
      hm.textContent = parts.join(', ');
    }
    ['ppi_release', 'cpi_release', 'xmpi_release'].forEach((id) => {
      const R = dash.data(id);
      document.querySelectorAll(`[data-source="${id}"][data-field="label"]`).forEach((s) => {
        if (R.status === 'ok' && R.data.length) { s.classList.remove('dash-skeleton'); s.textContent = R.data[0].label; }
        else if (R.status !== 'loading') { s.classList.remove('dash-skeleton'); s.textContent = ''; }
      });
    });
  }

  function takeaway() {
    const p = document.getElementById('cpi-takeaway');
    const L = dash.data('cpi_latest');
    if (L.status !== 'ok' || !L.data.length) { if (failed(L.status)) p.replaceChildren(); return; }
    const a = L.data[0];
    const mk = (field, src, row) => { const b = document.createElement('b'); b.dataset.source = src || 'cpi_latest'; b.dataset.field = field; b.dataset.row = '0'; b.textContent = J.f1((row || a)[field]); return b; };
    const t = (x) => p.append(document.createTextNode(x));
    const pc = () => { const b = document.createElement('b'); b.textContent = '%'; p.append(b); };
    p.replaceChildren();
    const dir = (now, prev) => (now > prev ? ', up from ' : now < prev ? ', down from ' : ', the same as ');
    t('In ' + mLabel(a.date) + ', CPI inflation was '); p.append(mk('all_yoy')); pc(); t(' y/y');
    if (a.all_yoy_prev != null) { t(dir(a.all_yoy, a.all_yoy_prev)); p.append(mk('all_yoy_prev')); pc(); t(' the month before'); }
    t('. Core inflation (excluding fresh food and energy) was '); p.append(mk('core_yoy')); pc();
    t('; energy prices were '); p.append(mk('energy_yoy')); pc(); t(' and fresh food prices '); p.append(mk('fresh_food_yoy')); pc(); t(' higher than a year earlier');
    t('. For low-income households inflation was '); p.append(mk('low_yoy')); pc(); t('.');
    const P = dash.data('ppi_latest');
    if (P.status === 'ok' && P.data.length && P.data[0].ppi_yoy != null) {
      const q = P.data[0];
      t(' Producer prices were up '); p.append(mk('ppi_yoy', 'ppi_latest', q)); pc(); t(' y/y in ' + mLabel(q.date));
      if (q.import_yoy != null) { t(', and import prices '); p.append(mk('import_yoy', 'ppi_latest', q)); pc(); t(' in ' + mLabel(q.xm_date)); }
      t('.');
    }
  }

  document.getElementById('cpi-groups-seg').addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    S.groupsLevel = Number(b.dataset.l);
    e.currentTarget.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    groupsTable();
  });
  document.getElementById('cpi-groups-search').addEventListener('input', (e) => { S.groupsQuery = e.target.value; groupsTable(); });

  const C = J.PAL;
  J.redrawCpi = () => {
    if (!visible()) return;
    lineChart('ppi-cpi', [
      { key: 'import', name: 'Import prices', color: C[2], dash: true },
      { key: 'ppi', name: 'Producer prices (PPI)', color: C[0] },
      { key: 'cpi', name: 'Consumer prices (CPI)', color: C[1] },
    ], 280, {
      ids: ['cpi_series', 'ppi_series', 'xmpi_series'],
      rows: (cpi, ppi, xm) => {
        const by = new Map();
        const put = (d, k, v) => { if (v == null) return; if (!by.has(d)) by.set(d, { date: d }); by.get(d)[k] = v; };
        ppi.forEach((r) => { if (r.series === 'ppi') put(r.date, 'ppi', r.yoy); });
        const first = Array.from(by.keys()).sort()[0];
        xm.forEach((r) => { if (r.series === 'import' && r.date >= first) put(r.date, 'import', r.yoy); });
        cpi.forEach((r) => { if (r.area === 'national' && r.series === 'all' && r.date >= first) put(r.date, 'cpi', r.yoy); });
        const all = Array.from(by.values()).sort(sortD);
        startAt('ppi-cpi', all);
        return J.slice(all, 'ppi-cpi');
      },
    });
    lineChart('cpi-measures', [
      { key: 'all', name: 'CPI', color: C[1] },
      { key: 'core', name: 'Core CPI (excl. fresh food and energy)', color: C[3] },
      { key: 'ex_food_energy', name: 'CPI excl. food and energy', color: C[0], dash: true },
    ], 280);
    lineChart('cpi-fe', [
      { key: 'fresh_food', name: 'Fresh food', color: C[5] },
      { key: 'energy', name: 'Energy', color: C[0] },
      { key: 'all', name: 'CPI', color: C[1] },
    ], 280);
    lineChart('cpi-areas', [
      { key: 'all', name: 'Thailand', color: C[1] },
      { key: 'bkk', area: 'bangkok', series: 'all', name: 'Bangkok and vicinity', color: C[0] },
      { key: 'low', area: 'lowincome', series: 'all', name: 'Low-income households', color: C[3], dash: true },
    ], 280);
    lineChart('cpi-food', [
      { key: 'food', name: 'Food and non-alcoholic beverages', color: C[1] },
      { key: 'rice', name: 'Rice', color: C[4] },
      { key: 'vegetables', name: 'Fresh vegetables', color: C[5] },
      { key: 'meat', name: 'Meat', color: C[6] },
      { key: 'food_away', name: 'Food away from home', color: C[0] },
    ], 280);
    lineChart('cpi-energy', [
      { key: 'vehicle_fuel', name: 'Vehicle fuel', color: C[1] },
      { key: 'electricity', name: 'Electricity', color: C[4] },
      { key: 'household_fuel', name: 'Household fuel', color: C[2] },
      { key: 'public_transport', name: 'Public transport fares', color: C[0] },
    ], 280);
    lineChart('ppi-sop', [
      { key: 'finished', name: 'Finished goods', color: C[1] },
      { key: 'intermediate', name: 'Intermediate goods', color: C[0] },
      { key: 'raw', name: 'Raw materials', color: C[3] },
    ], 280, {
      ids: ['ppi_series'],
      rows: (ppi) => {
        const by = new Map();
        ppi.forEach((r) => { if (r.type === 'SOP' && ['finished', 'intermediate', 'raw'].includes(r.series) && r.yoy != null) { if (!by.has(r.date)) by.set(r.date, { date: r.date }); by.get(r.date)[r.series] = r.yoy; } });
        const all = Array.from(by.values()).sort(sortD);
        startAt('ppi-sop', all);
        return J.slice(all, 'ppi-sop');
      },
    });
    regionsChart();
  };

  dash.onData(() => { tiles(); takeaway(); divTable(); groupsTable(); J.redrawCpi(); });
  J.redrawCpi();
})();
