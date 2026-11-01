// Inflation tab: Philippines CPI (PSA, 2018 = 100) and PPI for manufacturing (PSA, 2018 = 100), all as published.

dash.calc('cpi_series', {
  title: 'CPI series',
  description: 'Every CPI row (national, NCR, areas outside NCR, bottom 30%) with its cells read as numbers.',
  inputs: ['ph_cpi'],
  fn: (ph_cpi) => {
    const n = (v) => (v === '' || v == null ? null : Number(v));
    return ph_cpi.map((r) => ({
      date: r.date, area: r.area, series: r.series, label: r.label, group: r.group,
      order: Number(r.order), index: n(r.index), yoy: n(r.yoy), weight: n(r.weight),
    }));
  },
});

dash.calc('cpi_latest', {
  title: 'Latest month and the one before',
  description: 'y/y for the latest month and the month before (all items, core, food, bottom 30% households as published; energy and CPI less food and energy as calculated) and the published seasonally adjusted m/m change in all items.',
  inputs: ['cpi_series', 'ph_cpi_sa'],
  fn: (cpi_series, ph_cpi_sa) => {
    const pair = (area, series) => {
      const s = cpi_series.filter((r) => r.area === area && r.series === series && r.yoy != null)
        .sort((a, b) => (a.date < b.date ? -1 : 1));
      return [s[s.length - 1], s[s.length - 2]];
    };
    const row = {};
    [['all', 'all'], ['core', 'core'], ['food', 'food'], ['energy', 'energy'], ['xfe', 'ex_food_energy'], ['b30', 'b30_all']].forEach(([f, k]) => {
      const [a, b] = pair('national', k);
      row[f + '_yoy'] = a ? a.yoy : null;
      row[f + '_yoy_prev'] = b ? b.yoy : null;
      if (f === 'all') row.date = a ? a.date : null;
    });
    const sa = ph_cpi_sa.filter((r) => r.area === 'national' && r.series === 'all' && r.sa_mom !== '' && r.sa_mom != null)
      .sort((a, b) => (a.date < b.date ? -1 : 1));
    const s0 = sa[sa.length - 1], s1 = sa[sa.length - 2];
    row.sa_mom = s0 ? Number(s0.sa_mom) : null;
    row.sa_mom_prev = s1 ? Number(s1.sa_mom) : null;
    row.sa_date = s0 ? s0.date : null;
    return [row];
  },
});

dash.calc('cpi_div', {
  title: 'CPI by division',
  description: 'All items, core, CPI less food and energy (calculated), energy (calculated) and the 13 divisions: published 2018 weight (% of CPI), y/y in the latest four months and the published seasonally adjusted m/m in the latest month.',
  inputs: ['cpi_series', 'ph_cpi_sa'],
  fn: (cpi_series, ph_cpi_sa) => {
    const nat = cpi_series.filter((r) => r.area === 'national' && (r.group === 'division' || r.series === 'all' || r.series === 'core' || r.series === 'ex_food_energy' || r.series === 'energy'));
    const months = Array.from(new Set(nat.filter((r) => r.series === 'all' && r.yoy != null).map((r) => r.date))).sort().slice(-4);
    const sa = new Map();
    ph_cpi_sa.forEach((r) => { if (r.area === 'national' && r.date === months[3] && r.sa_mom !== '') sa.set(r.series, Number(r.sa_mom)); });
    const by = new Map();
    nat.forEach((r) => {
      if (!by.has(r.series)) by.set(r.series, { name: r.label, series: r.series, order: r.order, weight: r.weight, sa_mom: sa.has(r.series) ? sa.get(r.series) : null });
      const i = months.indexOf(r.date);
      if (i >= 0) by.get(r.series)['m' + (3 - i)] = r.yoy;
    });
    const top = ['all', 'core', 'ex_food_energy', 'energy'];
    const rank = (r) => (top.includes(r.series) ? top.indexOf(r.series) - 10 : r.order);
    return Array.from(by.values()).sort((a, b) => rank(a) - rank(b))
      .map((r) => ({ name: r.name, weight: r.weight, m3: r.m3 ?? null, m2: r.m2 ?? null, m1: r.m1 ?? null, m0: r.m0 ?? null, sa_mom: r.sa_mom, d0: months[3], d1: months[2], d2: months[1], d3: months[0] }));
  },
});

dash.calc('cpi_groups', {
  title: 'CPI by commodity group',
  description: 'Every commodity group in the CPI with its published 2018 weight (% of CPI) and published y/y in the latest three months and a year before the latest.',
  inputs: ['ph_cpi_items', 'ph_cpi_weights'],
  fn: (ph_cpi_items, ph_cpi_weights) => {
    const months = Array.from(new Set(ph_cpi_items.map((r) => r.date))).sort();
    const m0 = months[months.length - 1];
    const ago = (k) => { const d = new Date(Date.UTC(+m0.slice(0, 4), +m0.slice(5, 7) - 1 - k, 1)); return d.toISOString().slice(0, 10); };
    const want = { y0: m0, y1: ago(1), y2: ago(2), y12: ago(12) };
    const y = new Map();
    ph_cpi_items.forEach((r) => { if (r.yoy !== '') y.set(r.code + '|' + r.date, Number(r.yoy)); });
    return ph_cpi_weights.map((w) => {
      const row = { code: w.code, name: w.name, level: Number(w.level), weight: w.weight === '' ? null : Number(w.weight), order: Number(w.order) };
      Object.entries(want).forEach(([k, d]) => { row[k] = y.has(w.code + '|' + d) ? y.get(w.code + '|' + d) : null; row['d_' + k] = d; });
      return row;
    }).sort((a, b) => a.order - b.order);
  },
});

dash.calc('ppi_series', {
  title: 'PPI series',
  description: 'Every producer price row (manufacturing and its divisions) with its cells read as numbers.',
  inputs: ['ph_ppi'],
  fn: (ph_ppi) => ph_ppi.map((r) => ({
    date: r.date, series: r.series, label: r.label, order: Number(r.order),
    index: r.index === '' ? null : Number(r.index), yoy: r.yoy === '' ? null : Number(r.yoy),
  })),
});

dash.calc('ppi_latest', {
  title: 'Latest producer prices',
  description: 'PPI for manufacturing, published y/y for the latest month and the month before.',
  inputs: ['ppi_series'],
  fn: (ppi_series) => {
    const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const p = ppi_series.filter((r) => r.series === 'manufacturing' && r.yoy != null).sort((a, b) => (a.date < b.date ? -1 : 1));
    const a = p[p.length - 1], b = p[p.length - 2];
    return [{ date: a ? a.date : null, label: a ? MON[+a.date.slice(5, 7) - 1] + ' ' + a.date.slice(0, 4) : null,
      ppi_yoy: a ? a.yoy : null, ppi_yoy_prev: b ? b.yoy : null }];
  },
});

(() => {
  const J = window.JG;
  const S = { sa: 'all', groupsLevel: 2, groupsQuery: '' };
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const mLabel = (d) => (d ? MONTHS[+d.slice(5, 7) - 1] + ' ' + d.slice(0, 4) : '');
  const visible = () => !document.getElementById('inflation').hidden;
  const pct = (v) => (v == null ? '—' : J.f1(v) + '%');
  const failed = (st) => st === 'error' || st === 'connect' || st === 'declined';
  const sortD = (a, b) => (a.date < b.date ? -1 : 1);

  // Default window for long series: the slider starts at this date (the reader can drag back to the start).
  const START = { 'ppi-cpi': '2010-01-01', 'cpi-measures': '2010-01-01', 'cpi-areas': '2010-01-01', 'cpi-food': '2015-01-01', 'cpi-energy': '2015-01-01' };
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

  // Published seasonally adjusted m/m change, as bars.
  function saChart() {
    const box = document.getElementById('cpi-sa-chart');
    const D = dash.data('ph_cpi_sa');
    if (failed(D.status)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    const NAMES = { all: 'All items', d01: 'Food and non-alcoholic beverages', nonfood: 'Non-food' };
    let rows = D.data.filter((r) => r.area === 'national' && r.series === S.sa && r.sa_mom !== '' && r.sa_mom != null)
      .map((r) => ({ date: r.date, v: Number(r.sa_mom) })).sort(sortD);
    rows = J.slice(rows, 'cpi-sa');
    if (!rows.length) { box.replaceChildren(); return; }
    const W = box.clientWidth, H = 280;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const y = d3.scaleLinear([Math.min(0, d3.min(rows, (r) => r.v)), Math.max(0, d3.max(rows, (r) => r.v))], [H - 24, 10]).nice();
    const ticks = y.ticks(5);
    const fmt = d3.format('.1f');
    const ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    const x = d3.scaleBand(rows.map((r) => r.date), [ml, W - 8]).padding(0.2);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - 8).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).tickValues(J.yearTicks(rows.map((r) => r.date), W - ml)).tickSize(0).tickFormat((d) => d.slice(0, 4))));
    const color = J.PAL[0];
    svg.append('g').selectAll('rect').data(rows).join('rect').attr('fill', color)
      .attr('x', (r) => x(r.date)).attr('width', x.bandwidth())
      .attr('y', (r) => y(Math.max(0, r.v))).attr('height', (r) => Math.abs(y(r.v) - y(0)));
    legend('cpi-sa-legend', [{ name: NAMES[S.sa], color, bar: true }]);
    const card = document.getElementById('cpi-sa'), tip = J.tip(card);
    const hl = svg.append('rect').attr('fill', 'var(--color-fg)').attr('opacity', 0.06).attr('display', 'none');
    svg.append('rect').attr('x', ml).attr('width', W - ml - 8).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const i = Math.max(0, Math.min(rows.length - 1, Math.floor((d3.pointer(ev)[0] - ml) / x.step())));
        const r = rows[i];
        hl.attr('display', null).attr('x', x(r.date) - x.step() * x.paddingInner() / 2).attr('width', x.step()).attr('y', 0).attr('height', H - 22);
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, mLabel(r.date), [[color, NAMES[S.sa], pct(r.v)]], ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { hl.attr('display', 'none'); tip.style.display = 'none'; });
  }

  // Latest y/y by region as horizontal bars; a tick marks the rate a year earlier.
  function regionsChart() {
    const box = document.getElementById('cpi-regions-chart');
    const D = dash.data('ph_cpi_regions');
    if (failed(D.status)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    const dates = Array.from(new Set(D.data.map((r) => r.date))).sort();
    const d0 = dates[dates.length - 1];
    const dY = `${+d0.slice(0, 4) - 1}${d0.slice(4)}`;
    const ago = new Map(D.data.filter((r) => r.date === dY).map((r) => [r.region, Number(r.yoy)]));
    const rows = D.data.filter((r) => r.date === d0 && r.yoy !== '')
      .map((r) => ({ region: r.region, v: Number(r.yoy), a: ago.has(r.region) ? ago.get(r.region) : null, agg: Number(r.order) <= 2 }))
      .sort((a, b) => (b.agg - a.agg) || (b.v - a.v));
    document.getElementById('cpi-regions-units').textContent = `% y/y, ${mLabel(d0)}`;
    const W = box.clientWidth, rowH = 22, H = rows.length * rowH + 28;
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
    svg.append('g').selectAll('text').data(rows).join('text').attr('x', (r) => x(Math.max(0, r.v)) + 4).attr('y', (r) => yb(r.region) + yb.bandwidth() / 2).attr('dy', '0.35em')
      .attr('font-size', 12).attr('fill', 'var(--ad-ink)').text((r) => J.f1(r.v));
    legend('cpi-regions-legend', [{ name: mLabel(d0), color: cNow, bar: true }, { name: `Philippines, NCR and areas outside NCR, ${mLabel(d0)}`, color: J.PAL[1], bar: true }, { name: mLabel(dY), color: cAgo }]);
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
    td.textContent = v == null ? '' : (f === 'weight' && v < 1 ? v.toFixed(2) : J.f1(v));
    if (v != null && v < 0 && f !== 'weight') td.classList.add('neg');
    return td;
  };

  function divTable() {
    const tb = document.querySelector('#cpi-div-table tbody');
    const D = dash.data('cpi_div');
    if (failed(D.status)) { tb.replaceChildren(); const td = tb.insertRow().insertCell(); td.colSpan = 7; J.fail(td); return; }
    if (D.status !== 'ok' || !D.data.length) return;
    const r0 = D.data[0];
    const th = document.querySelectorAll('#cpi-div-table thead th');
    [r0.d3, r0.d2, r0.d1, r0.d0].forEach((d, i) => { th[2 + i].textContent = mLabel(d); });
    th[6].textContent = `m/m SA, ${mLabel(r0.d0)}`;
    tb.replaceChildren();
    D.data.forEach((r, i) => {
      const tr = tb.insertRow(); tr.dataset.key = r.name;
      if (i < 4) tr.className = 'agg'; if (i === 4) tr.className = 'sep';
      cell(tr, r.name, 'text');
      cell(tr, r.weight, 'weight');
      ['m3', 'm2', 'm1', 'm0'].forEach((k, j) => { const td = cell(tr, r[k]); if (j < 2) td.classList.add('hide-narrow'); });
      cell(tr, r.sa_mom);
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
      const tr = tb.insertRow(); tr.dataset.key = r.code; tr.className = 'l' + r.level;
      const td = cell(tr, r.code === '0' ? 'All items' : (r.name === r.name.toUpperCase() ? r.name.charAt(0) + r.name.slice(1).toLowerCase() : r.name), 'text');
      td.className = 'l' + r.level;
      if (r.level === 0) tr.className = 'l1';
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
      if (P.status === 'ok' && P.data.length) parts.push(`${mLabel(P.data[0].date)} PPI`);
      hm.textContent = parts.join(', ');
    }
    [['ppi_release'], ['cpi_release']].forEach(([id]) => {
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
    t('. Core inflation was '); p.append(mk('core_yoy')); pc();
    if (a.xfe_yoy != null) { t(' (excluding food and energy, calculated: '); p.append(mk('xfe_yoy')); pc(); t(')'); } t(' and food inflation '); p.append(mk('food_yoy')); pc();
    if (a.energy_yoy != null) { t(', and energy (calculated) '); p.append(mk('energy_yoy')); pc(); }
    t('. For the bottom 30% of households it was '); p.append(mk('b30_yoy')); pc(); t('.');
    if (a.sa_mom != null && a.sa_date === a.date) { t(' Seasonally adjusted, prices changed by '); p.append(mk('sa_mom')); pc(); t(' on the month.'); }
    const P = dash.data('ppi_latest');
    if (P.status === 'ok' && P.data.length && P.data[0].ppi_yoy != null) {
      const q = P.data[0];
      t(' Manufacturing producer prices were up '); p.append(mk('ppi_yoy', 'ppi_latest', q)); pc(); t(' y/y in ' + mLabel(q.date) + '.');
    }
  }

  document.getElementById('cpi-sa-seg').addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    S.sa = b.dataset.k;
    e.currentTarget.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    saChart();
  });
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
      { key: 'ppi', name: 'Producer prices, manufacturing (PPI)', color: C[0] },
      { key: 'cpi', name: 'Consumer prices (CPI)', color: C[1] },
    ], 280, {
      ids: ['cpi_series', 'ppi_series'],
      rows: (cpi, ppi) => {
        const by = new Map();
        const put = (d, k, v) => { if (v == null) return; if (!by.has(d)) by.set(d, { date: d }); by.get(d)[k] = v; };
        ppi.forEach((r) => { if (r.series === 'manufacturing') put(r.date, 'ppi', r.yoy); });
        const first = Array.from(by.keys()).sort()[0];
        cpi.forEach((r) => { if (r.area === 'national' && r.series === 'all' && r.date >= first) put(r.date, 'cpi', r.yoy); });
        const all = Array.from(by.values()).sort(sortD);
        startAt('ppi-cpi', all);
        return J.slice(all, 'ppi-cpi');
      },
    });
    lineChart('cpi-measures', [
      { key: 'all', name: 'CPI', color: C[1] },
      { key: 'core', name: 'Core CPI (PSA)', color: C[3] },
      { key: 'ex_food_energy', name: 'Excl. food and energy (calculated)', color: C[2] },
      { key: 'b30_all', name: 'Bottom 30% households', color: C[0], dash: true },
    ], 280);
    lineChart('cpi-areas', [
      { key: 'ncr', area: 'ncr', series: 'all', name: 'NCR', color: C[0] },
      { key: 'aoncr', area: 'aoncr', series: 'all', name: 'Areas outside NCR', color: C[1] },
    ], 280);
    lineChart('cpi-food', [
      { key: 'food', name: 'Food', color: C[1] },
      { key: 'rice', name: 'Rice', color: C[4] },
      { key: 'vegetables', name: 'Vegetables, tubers and pulses', color: C[5] },
      { key: 'fish', name: 'Fish and seafood', color: C[0] },
      { key: 'meat', name: 'Meat', color: C[6] },
    ], 280);
    lineChart('cpi-energy', [
      { key: 'energy', name: 'Energy (calculated)', color: C[1] },
      { key: 'electricity', name: 'Electricity', color: C[4] },
      { key: 'lpg', name: 'LPG', color: C[2] },
      { key: 'fuels_transport', name: 'Fuels for personal transport', color: C[6] },
      { key: 'transport_services', name: 'Passenger transport services', color: C[0] },
    ], 280);
    saChart();
    regionsChart();
  };

  dash.onData(() => { tiles(); takeaway(); divTable(); groupsTable(); J.redrawCpi(); });
  J.redrawCpi();
})();

// Financial tab: peso per US dollar, daily, BIS bilateral exchange rate series (WS_XRU), from national sources,
// as published; full history. Nothing calculated.
(() => {
  const J = window.JG;
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const failed = (st) => st === 'error' || st === 'connect' || st === 'declined';
  const dt = (s) => new Date(Date.UTC(Number(s.slice(0, 4)), Number(s.slice(5, 7)) - 1, Number(s.slice(8, 10)) || 1));
  const dLabel = (s) => `${Number(s.slice(8, 10))} ${MON[Number(s.slice(5, 7)) - 1]} ${s.slice(0, 4)}`;
  const visible = () => { const p = document.getElementById('financial'); return p && !p.hidden; };
  const ID = 'fx-daily', RED = '#BD1B21', H = 300;
  const vfmt = d3.format(',.2f');

  function fxChart() {
    const box = document.getElementById(ID + '-chart');
    if (!box) return;
    const D = dash.data('ph_fx_daily');
    if (failed(D.status)) { J.fail(box); return; }
    if (D.status !== 'ok' || !D.data.length) { box.replaceChildren(); return; }
    const all = D.data.map((r) => ({ date: String(r.date).slice(0, 10), v: Number(r.rate) }))
      .filter((r) => r.date && r.v > 0).sort((a, b) => (a.date < b.date ? -1 : 1));
    if (!J.range[ID]) J.range[ID] = [0, 1]; // full history by default
    const rows = J.slice(all, ID);
    if (!rows.length) { box.replaceChildren(); return; }
    rows.forEach((r) => { r.t = dt(r.date); });
    const W = box.clientWidth;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const y = d3.scaleLinear([0, d3.max(rows, (r) => r.v)], [H - 24, 10]).nice();
    const ticks = y.ticks(5);
    const fmt = d3.format(`,.${d3.precisionFixed(ticks.length > 1 ? ticks[1] - ticks[0] : 1)}f`);
    const ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    const x = d3.scaleUtc([rows[0].t, rows[rows.length - 1].t], [ml, W - 8]);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - 8).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).ticks(Math.max(2, Math.round((W - ml) / 70))).tickSize(0).tickFormat(d3.utcFormat('%Y'))));
    svg.append('path').attr('d', d3.line().x((r) => x(r.t)).y((r) => y(r.v))(rows))
      .attr('fill', 'none').attr('stroke', RED).attr('stroke-width', 1.4).attr('stroke-linejoin', 'round');
    const card = document.getElementById(ID), tip = J.tip(card);
    const rule = svg.append('line').attr('y1', 8).attr('y2', H - 22).attr('stroke', 'var(--cds-chart-reference)').attr('display', 'none');
    const dot = svg.append('circle').attr('r', 3.5).attr('fill', RED).attr('display', 'none');
    const bis = d3.bisector((r) => r.t).center;
    svg.append('rect').attr('x', ml).attr('width', W - ml).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const r = rows[bis(rows, x.invert(d3.pointer(ev)[0]))]; if (!r) return;
        const px = x(r.t);
        rule.attr('display', null).attr('x1', px).attr('x2', px);
        dot.attr('display', null).attr('cx', px).attr('cy', y(r.v));
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, dLabel(r.date), [[RED, 'Peso per US$', vfmt(r.v)]], ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); dot.attr('display', 'none'); tip.style.display = 'none'; });
  }

  J.redrawFx = () => { if (visible()) fxChart(); };
  dash.onData(() => J.redrawFx());
  J.redrawFx();
})();
