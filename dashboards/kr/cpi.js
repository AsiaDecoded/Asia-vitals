// Inflation tab: South Korea CPI (Ministry of Data and Statistics, 2020 = 100, 2022 weights) and producer prices
// (Bank of Korea PPI and DSPI), via ECOS. No seasonally adjusted CPI is published, so there is no momentum chart.

dash.calc('cpi_series', {
  title: 'CPI series',
  description: 'Every CPI row with its cells read as numbers.',
  inputs: ['kr_cpi'],
  fn: (kr_cpi) => {
    const n = (v) => (v === '' || v == null ? null : Number(v));
    return kr_cpi.map((r) => ({
      date: r.date, area: r.area, series: r.series, label: r.label, group: r.group,
      order: Number(r.order), index: n(r.index), yoy: n(r.yoy),
    }));
  },
});

dash.calc('cpi_latest', {
  title: 'Latest month and the one before',
  description: 'Year-on-year rates for the latest month and the month before: all items, CPI excluding food and energy (core), food and non-alcoholic beverages, energy (calculated), goods and services.',
  inputs: ['cpi_series'],
  fn: (cpi_series) => {
    const pair = (area, series) => {
      const s = cpi_series.filter((r) => r.area === area && r.series === series && r.yoy != null)
        .sort((a, b) => (a.date < b.date ? -1 : 1));
      return [s[s.length - 1], s[s.length - 2]];
    };
    const row = {};
    ['all', 'ex_food_energy', 'div_A', 'energy', 'goods', 'services'].forEach((k) => {
      const [a, b] = pair('national', k);
      row[k + '_yoy'] = a ? a.yoy : null;
      row[k + '_yoy_prev'] = b ? b.yoy : null;
      if (k === 'all') row.date = a ? a.date : null;
    });
    return [row];
  },
});

dash.calc('cpi_movers', {
  title: 'Item contributions, 3- and 6-month averages',
  description: 'For each individual CPI item: its published 2022 weight (per 1,000) and y/y in the latest month, and the average of its contribution to the all-items y/y (calculated from the published weights) over the latest 3 and 6 months.',
  inputs: ['kr_cpi_items'],
  fn: (kr_cpi_items) => {
    const n = (v) => (v === '' || v == null ? null : Number(v));
    const months = Array.from(new Set(kr_cpi_items.map((r) => r.date))).sort();
    const latest = months[months.length - 1];
    const last = (k) => months.slice(-k);
    const by = new Map();
    kr_cpi_items.forEach((r) => {
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
  description: 'Every producer price (all items and major groups) and domestic supply price row with its cells read as numbers.',
  inputs: ['kr_ppi'],
  fn: (kr_ppi) => kr_ppi.map((r) => ({
    date: r.date, series: r.series, label: r.label, order: Number(r.order),
    index: r.index === '' ? null : Number(r.index), yoy: r.yoy === '' ? null : Number(r.yoy),
  })),
});

dash.calc('ppi_latest', {
  title: 'Latest producer prices',
  description: 'Producer prices (all items) y/y for the latest month and the month before.',
  inputs: ['ppi_series'],
  fn: (ppi_series) => {
    const s = (k) => ppi_series.filter((r) => r.series === k && r.yoy != null).sort((a, b) => (a.date < b.date ? -1 : 1));
    const p = s('ppi');
    const a = p[p.length - 1], b = p[p.length - 2];
    return [{ date: a ? a.date : null, ppi_yoy: a ? a.yoy : null, ppi_yoy_prev: b ? b.yoy : null }];
  },
});

dash.calc('cpi_heat', {
  title: 'CPI inflation by measure and division, y/y',
  description: 'y/y (calculated from the published index, as the ministry does) with the published 2022 basket weights per 1,000, for all items, the published core measures, energy (calculated from its nine items) and selected items, the 12 divisions, and the published goods and services split, from Jan 2026.',
  inputs: ['cpi_series', 'kr_cpi_series_weights'],
  fn: (cpi_series, kr_cpi_series_weights) => {
    const W = new Map(kr_cpi_series_weights.map((r) => [r.series, Number(r.weight)]));
    const ROWS = ['all', 'ex_food_energy', 'ex_agri_oil', 'living', 'fresh', 'energy', 'petroleum', 'petrol', 'diesel', 'electricity', 'city_gas', 'district_heating', 'utilities',
      'div_A', 'div_B', 'div_C', 'div_D', 'div_E', 'div_F', 'div_G', 'div_H', 'div_I', 'div_J', 'div_K', 'div_L',
      'goods', 'agri', 'industrial', 'processed_food', 'services', 'rent', 'jeonse', 'monthly_rent', 'public', 'personal', 'eating_out', 'personal_ex_eating_out'];
    return cpi_series.filter((r) => ROWS.includes(r.series) && r.date >= '2026-01-01' && r.yoy != null)
      .map((r) => ({ date: r.date, series: r.series, name: r.label, yoy: r.yoy, order: ROWS.indexOf(r.series), weight: W.has(r.series) ? W.get(r.series) : null }));
  },
});

(() => {
  const J = window.JG;
  const S = { months: 120, movers: 3, svc: 'rent', fe: 'food' };
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
  const mseg = document.getElementById('cpi-movers-seg');
  mseg.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    S.movers = Number(b.dataset.n);
    mseg.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    moversTable();
  });
  seg('cpi-svc-seg', 'svc', 's', String);
  seg('cpi-fe-seg', 'fe', 's', String);

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
    const cardEl = document.getElementById(cardId), room = cardEl && cardEl.dataset.headroom ? Number(cardEl.dataset.headroom) : 1;
    const vmin = Math.min(0, d3.min(vals)), vmax = Math.max(0, d3.max(vals));
    const y = d3.scaleLinear([vmin, vmin + (vmax - vmin) * room], [H - 24, 10]).nice(8);
    const ticks = y.ticks(5);
    const ml = J.textWidth(svg, ticks.map((v) => d3.format('.0f')(v))) + 10;
    const x = d3.scaleUtc([J.date(rows[0].date), J.date(rows[rows.length - 1].date)], [ml, W - 8]);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - 8).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(d3.format('.0f'))));
    const short = !(build && build.yearly) && rows.length <= 36;
    const xax = d3.axisBottom(x).tickSize(0);
    if (short) xax.ticks(d3.utcMonth.every(rows.length > 18 ? 3 : rows.length > 9 ? 2 : 1)).tickFormat(d3.utcFormat('%b %y'));
    else xax.ticks(Math.max(2, Math.round((W - ml) / 70))).tickFormat(d3.utcFormat('%Y'));
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(xax));
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
        J.showTip(card, tip, build && build.label ? build.label(r.date) : mLabel(r.date), series.map((s) => [s.color, s.name, pct(r[s.key])]), ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); dots.forEach((d) => d.attr('display', 'none')); tip.style.display = 'none'; });
  }

  // Contributions to the y/y change in all items (calculated from the published indices; see Methodology).
  function contribChart(opt) {
    // stacked from zero: services, industrial products excl. petroleum, then the parts specific to Korea's split
    opt = opt || { id: 'cpi-contrib', pre: '', line: 'CPI, y/y', keys: ['services', 'industrial_ex_oil', 'agri', 'petroleum', 'utilities'] };
    const box = document.getElementById(opt.id + '-chart');
    const D = dash.data('kr_cpi_contrib');
    if (failed(D.status)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    const ALL = [
      { key: 'services', name: 'Services', color: '#FFC000', bar: true },
      { key: 'industrial_ex_oil', name: 'Industrial products excl. petroleum', color: '#1F4E79', bar: true },
      { key: 'agri', name: 'Agricultural, livestock and fishery', color: '#A6A6A6', bar: true },
      { key: 'petroleum', name: 'Petroleum products', color: '#EE6631', bar: true },
      { key: 'utilities', name: 'Electricity, gas and water', color: '#0C84FF', bar: true },
    ];
    // stacked in the order of opt.keys: the first sits next to zero
    const PARTS = opt.keys ? opt.keys.map((k) => ALL.find((p) => p.key === k)).filter(Boolean) : ALL;
    const by = new Map();
    D.data.forEach((r) => {
      const v = r.contrib_yoy === '' || r.contrib_yoy == null ? null : Number(r.contrib_yoy);
      if (!by.has(r.date)) by.set(r.date, { date: r.date });
      by.get(r.date)[r.series.slice(opt.pre.length)] = v;
    });
    let rows = Array.from(by.values()).filter((r) => r.all != null).sort((a, b) => (a.date < b.date ? -1 : 1));
    rows = J.slice(rows, opt.id);
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
    const lineColor = '#BD1B21';
    svg.append('path').attr('d', d3.line().x((r) => cx(r.date)).y((r) => y(r.all))(rows))
      .attr('fill', 'none').attr('stroke', lineColor).attr('stroke-width', 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    legend(opt.id + '-legend', [{ key: 'all', name: opt.line, color: lineColor }].concat(PARTS.slice().reverse()));  // top of the stack first
    const card = document.getElementById(opt.id), tip = J.tip(card);
    const hl = svg.append('rect').attr('fill', 'var(--color-fg)').attr('opacity', 0.06).attr('display', 'none');
    const sg = (v) => (v == null ? '—' : (v > 0 ? '+' : '') + J.f1(v) + 'ppt');
    svg.append('rect').attr('x', ml).attr('width', W - ml - 8).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const i = Math.max(0, Math.min(rows.length - 1, Math.floor((d3.pointer(ev)[0] - ml) / x.step())));
        const r = rows[i];
        hl.attr('display', null).attr('x', x(r.date) - x.step() * x.paddingInner() / 2).attr('width', x.step()).attr('y', 0).attr('height', H - 22);
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, mLabel(r.date), [[lineColor, opt.line, pct(r.all)]].concat(PARTS.map((p) => [p.color, p.name, sg(r[p.key])])),
          ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { hl.attr('display', 'none'); tip.style.display = 'none'; });
  }

  // Services: one published series per tab; the rent tab shows jeonse and monthly rent (published item indices). y/y.
  function svcChart() {
    if (!document.getElementById('cpi-svc-chart')) return;
    const btn = document.querySelector(`#cpi-svc-seg [data-s="${S.svc}"]`);
    const series = S.svc === 'rent'
      ? [{ key: 'jeonse', name: 'Jeonse', color: C[0] }, { key: 'monthly_rent', name: 'Monthly rent', color: C[1] }]
      : [{ key: S.svc, name: btn ? btn.dataset.name : '', color: C[0] }];
    lineChart('cpi-svc-chart', 'cpi-svc', 'cpi-svc-legend', 'national', series, 280);
  }

  // Goods and services CPI, the ministry's published split; y/y.
  function gsChart() {
    if (!document.getElementById('gs-yoy-chart')) return;
    lineChart('gs-yoy-chart', 'gs-yoy', 'gs-yoy-legend', 'national', [
      { key: 'goods', name: 'Goods', color: J.PAL[1] },
      { key: 'services', name: 'Services', color: J.PAL[0] },
      { key: 'personal_ex_eating_out', name: 'Personal services excl. eating out', color: J.PAL[4] },
    ], 280);
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
    document.getElementById('cpi-movers-units').textContent = date ? `weight % of CPI; %, ppt, ${S.movers}-month average to ${mLabel(date)}` : '%, ppt';
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
          td.textContent = v == null ? '' : (f === 'weight' ? d3.format('.2f')(v / 10) : (f === k ? d3.format('.2f')(v) : J.f1(v)));
          if (v != null && v < 0 && f !== 'weight') td.classList.add('neg');
        });
      });
    });
  }


  // Division heat table: published y/y by month, each row coloured on its own range (green low, amber middle, red high).
  function heat() {
    const tbl = document.getElementById('cpi-heat-table');
    const D = dash.data('cpi_heat');
    if (failed(D.status)) { tbl.replaceChildren(); return; }
    if (D.status !== 'ok') return;
    const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const dates = Array.from(new Set(D.data.map((r) => r.date))).sort();
    const keys = Array.from(new Set(D.data.map((r) => r.series)))
      .sort((p, q) => D.data.find((r) => r.series === p).order - D.data.find((r) => r.series === q).order);
    const val = new Map(D.data.map((r) => [`${r.series}|${r.date}`, r]));
    const STOPS = [[0, [99, 190, 123]], [0.5, [255, 235, 132]], [1, [248, 105, 107]]];
    const color = (t) => {
      const i = t > 0.5 ? 1 : 0; const [t0, c0] = STOPS[i], [t1, c1] = STOPS[i + 1], f = (t - t0) / (t1 - t0);
      return `rgb(${c0.map((c, k) => Math.round(c + (c1[k] - c) * f)).join(',')})`;
    };
    const NAMES = { energy: 'Energy', all: 'CPI', ex_food_energy: 'Core (CPI excl. food and energy)', ex_agri_oil: 'CPI excl. agricultural products and oil', living: 'Living cost index', jeonse: 'Jeonse', personal_ex_eating_out: 'Personal services excl. eating out' };
    tbl.replaceChildren();
    const head = tbl.createTHead().insertRow();
    ['', 'Weight'].concat(dates.map((d) => `${MON[+d.slice(5, 7) - 1]} ${d.slice(2, 4)}`)).forEach((t) => {
      const th = document.createElement('th'); th.textContent = t; head.appendChild(th);
    });
    const tb = tbl.createTBody();
    const CHILDREN = { energy: ['petroleum', 'electricity', 'city_gas', 'district_heating'], petroleum: ['petrol', 'diesel'], goods: ['agri', 'industrial', 'processed_food'],
      services: ['rent', 'public', 'personal', 'eating_out', 'personal_ex_eating_out'], rent: ['jeonse', 'monthly_rent'] };
    const PARENT = {}; Object.entries(CHILDREN).forEach(([p, cs]) => cs.forEach((c) => { PARENT[c] = p; }));
    const OPEN = (J.state.heatOpen = J.state.heatOpen || {});
    keys.forEach((k) => {
      if (k === 'div_A' || k === 'goods') { const sp = tb.insertRow(); sp.className = 'spacer'; sp.insertCell().colSpan = dates.length + 2; }
      const tr = tb.insertRow();
      const label = NAMES[k] || D.data.find((r) => r.series === k).name;
      const nc = tr.insertCell(); nc.dataset.label = label;
      if (CHILDREN[k]) {
        const open = !!OPEN[k];
        const b = document.createElement('button'); b.type = 'button'; b.className = 'heat-tog';
        b.setAttribute('aria-expanded', String(open));
        const ar = document.createElement('span'); ar.className = 'heat-arrow'; ar.textContent = open ? '\u25BE' : '\u25B8';
        b.append(document.createTextNode(label + ' '), ar);
        b.addEventListener('click', () => { OPEN[k] = !OPEN[k]; heat(); });
        nc.appendChild(b);
      } else nc.textContent = label;
      // hidden while any ancestor is closed
      for (let p = PARENT[k]; p; p = PARENT[p]) if (!OPEN[p]) { tr.hidden = true; break; }
      const wt = D.data.find((r) => r.series === k).weight;
      const wc = tr.insertCell(); wc.className = 'wt'; wc.textContent = wt == null ? '' : d3.format('.1f')(wt / 10);
      if (['all', 'ex_food_energy', 'ex_agri_oil', 'living', 'fresh', 'energy', 'utilities', 'goods', 'services'].includes(k)) tr.className = 'lead';
      if (PARENT[k]) tr.className = 'sub';
      if (k === 'div_A') tr.className = 'gap';
      const vs = dates.map((d) => (val.get(`${k}|${d}`) || {}).yoy).filter((v) => v != null);
      const lo = Math.min(...vs), hi = Math.max(...vs);
      dates.forEach((d) => {
        const td = tr.insertCell(); const r = val.get(`${k}|${d}`);
        if (!r) return;
        td.textContent = J.f1(r.yoy) === '-0.0' ? '0.0' : J.f1(r.yoy);
        td.className = 'heat';
        td.style.background = color(hi > lo ? (r.yoy - lo) / (hi - lo) : 0.5);
        td.style.color = '#1a1a1a';
      });
    });
    heatScroll();
  }

  // Table 1 scrolls sideways under the month columns only: the label and weight columns stay put (sticky) and a
  // scroll bar drawn beneath the heatmap drives the table (and follows it when the table is swiped).
  const heatRO = {};
  function heatScroll(id = 'cpi-heat-table', sk = 'heatScrolled') {
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
      // starts at the latest months (right); once the reader scrolls, their position is kept
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
        // start at the latest months, with the first visible month column whole (not cut by the sticky columns)
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
    t('In '); mb(a.date); t(', CPI inflation was '); p.append(mk('all_yoy')); pc(); t(' y/y. Core inflation (CPI excluding food and energy) was ');
    p.append(mk('ex_food_energy_yoy')); pc(); t('.');
    const P = dash.data('ppi_latest');
    if (P.status === 'ok' && P.data.length && P.data[0].ppi_yoy != null) {
      const q = P.data[0];
      const b = document.createElement('b'); b.dataset.source = 'ppi_latest'; b.dataset.field = 'ppi_yoy'; b.dataset.row = '0'; b.textContent = J.f1(q.ppi_yoy);
      t(' Producer price inflation was '); p.append(b); pc(); t(' y/y in '); mb(q.date); t('.');
    }
  }

  const C = J.PAL;
  J.redrawCpi = () => {
    if (!visible()) return;
    lineChart('cpi-measures-chart', 'cpi-measures', 'cpi-measures-legend', 'national', [
      { key: 'all', name: 'CPI', color: C[1] },
      { key: 'ex_food_energy', name: 'Core (CPI excl. food and energy)', color: C[4] },
      { key: 'ex_agri_oil', name: 'CPI excl. agricultural products and oil', color: C[0] },
    ], 280);
    lineChart('ppi-cpi-chart', 'ppi-cpi', 'ppi-cpi-legend', 'national', [
      { key: 'ppi', name: 'PPI', color: C[0] },
      { key: 'dspi', name: 'DSPI', color: C[4] },
      { key: 'cpi', name: 'CPI', color: C[1] },
    ], 280, {
      ids: ['cpi_series', 'ppi_series'],
      rows: (cpi, ppi) => {
        const by = new Map();
        const put = (d, k, v) => { if (v == null) return; if (!by.has(d)) by.set(d, { date: d }); by.get(d)[k] = v; };
        cpi.forEach((r) => { if (r.area === 'national' && r.series === 'all') put(r.date, 'cpi', r.yoy); });
        ppi.forEach((r) => { if (r.series === 'ppi' || r.series === 'dspi') put(r.date, r.series, r.yoy); });
        const out = Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
        return J.slice(out, 'ppi-cpi');
      },
    });
    lineChart('cpi-drivers-chart', 'cpi-drivers', 'cpi-drivers-legend', 'national', S.fe === 'energy'
      ? [{ key: 'energy', name: 'Energy', color: C[7] }, { key: 'electricity', name: 'Electricity', color: C[1] }, { key: 'city_gas', name: 'City gas', color: C[4] },
        { key: 'petrol', name: 'Petrol', color: C[0] }, { key: 'diesel', name: 'Diesel', color: C[5] }]
      : [{ key: 'div_A', name: 'Food and non-alcoholic beverages', color: C[0] }, { key: 'eating_out', name: 'Eating out', color: C[1] },
        { key: 'fresh', name: 'Fresh food', color: C[0], dash: true }], 280);
    lineChart('cpi-diffusion-chart', 'cpi-diffusion', 'cpi-diffusion-legend', 'national', [
      { key: 'diffusion', name: 'Diffusion index (rising minus falling)', color: C[1] },
      { key: 'share_rising', name: 'Rising', color: C[5] },
      { key: 'share_falling', name: 'Falling', color: C[0] },
    ], 280, {
      ids: ['kr_cpi_diffusion'],
      rows: (d) => {
        const out = d.map((r) => ({ date: r.date, diffusion: Number(r.diffusion), share_rising: Number(r.share_rising), share_falling: Number(r.share_falling) }))
          .sort((a, b) => (a.date < b.date ? -1 : 1));
        return J.slice(out, 'cpi-diffusion');
      },
    });
    contribChart();
    gsChart();
    svcChart();
  };

  dash.onData(() => { tiles(); takeaway(); heat(); moversTable(); J.redrawCpi(); });
  J.redrawCpi();
})();
