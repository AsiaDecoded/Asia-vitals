// Inflation tab: Indonesia CPI and WPI, all as published by BPS-Statistics Indonesia.
//   id_cpi: CPI via Bank Indonesia SEKI table VIII.1 (all items from 1966, group indices and m/m from 2020).
//   id_cpi_bps: BPS WebAPI: press-release tables (groups and components with y/y and contributions, 2020 on) and
//     static table 908 (m/m of CPI, core, administered and volatile food from 2009).
//   id_ppi: WPI (IHPB, 2023 = 100) from the WPI press releases, 2025 on.

const inum = (v) => (v === '' || v == null ? null : Number(v));

dash.calc('cpi_series', {
  title: 'CPI series (SEKI)',
  description: 'CPI rows from Bank Indonesia SEKI (all items from 1966, the 11 expenditure groups from 2020) with cells read as numbers.',
  inputs: ['id_cpi'],
  fn: (id_cpi) => id_cpi.map((r) => ({
    date: r.date, series: r.series, label: r.label, order: Number(r.order),
    index: inum(r.index), mom: inum(r.mom), ytd: inum(r.ytd), yoy: inum(r.yoy),
  })),
});

dash.calc('bps_series', {
  title: 'CPI series (BPS)',
  description: 'CPI rows from the BPS WebAPI (groups and components: y/y, m/m, contributions) with cells read as numbers.',
  inputs: ['id_cpi_bps'],
  fn: (id_cpi_bps) => id_cpi_bps.map((r) => ({
    date: r.date, series: r.series, label: r.label, kind: r.kind, order: Number(r.order),
    index: inum(r.index), mom: inum(r.mom), ytd: inum(r.ytd), yoy: inum(r.yoy),
    contrib_mom: inum(r.contrib_mom), contrib_yoy: inum(r.contrib_yoy),
  })),
});

dash.calc('ppi_series', {
  title: 'WPI series',
  description: 'Wholesale price index rows (general and five sections) with cells read as numbers.',
  inputs: ['id_ppi'],
  fn: (id_ppi) => id_ppi.map((r) => ({
    date: r.date, series: r.series, label: r.label, order: Number(r.order),
    index: inum(r.index), mom: inum(r.mom), yoy: inum(r.yoy), contrib_yoy: inum(r.contrib_yoy),
  })),
});

dash.calc('cpi_latest', {
  title: 'Latest month and the one before',
  description: 'Published y/y for CPI, core, administered prices and volatile food, and CPI m/m: latest month and the month before.',
  inputs: ['bps_series'],
  fn: (bps_series) => {
    const row = {};
    [['all', 'yoy'], ['core', 'yoy'], ['administered', 'yoy'], ['volatile', 'yoy'], ['all', 'mom']].forEach(([k, m]) => {
      const s = bps_series.filter((r) => r.series === k && r[m] != null && r.index != null).sort((a, b) => (a.date < b.date ? -1 : 1));
      const a = s[s.length - 1], b = s[s.length - 2];
      row[`${k}_${m}`] = a ? a[m] : null;
      row[`${k}_${m}_prev`] = b ? b[m] : null;
      if (k === 'all' && m === 'yoy') row.date = a ? a.date : null;
    });
    return [row];
  },
});

dash.calc('ppi_latest', {
  title: 'Latest WPI month',
  description: 'Published WPI y/y for the latest month and the month before.',
  inputs: ['ppi_series'],
  fn: (ppi_series) => {
    const s = ppi_series.filter((r) => r.series === 'wpi' && r.yoy != null).sort((a, b) => (a.date < b.date ? -1 : 1));
    const a = s[s.length - 1], b = s[s.length - 2];
    return [{ date: a ? a.date : null, wpi_yoy: a ? a.yoy : null, wpi_yoy_prev: b ? b.yoy : null }];
  },
});

dash.calc('cpi_heat', {
  title: 'CPI by component and group, y/y',
  description: 'Published y/y for CPI, its components and the 11 expenditure groups, January 2025 on.',
  inputs: ['bps_series'],
  fn: (bps_series) => bps_series.filter((r) => r.date >= '2025-01-01' && r.yoy != null && r.index != null)
    .map((r) => ({ date: r.date, series: r.series, name: r.series === 'all' ? 'CPI' : r.label, order: r.order, kind: r.kind, yoy: r.yoy })),
});

dash.calc('cpi_ctab', {
  title: 'Contributions to CPI y/y',
  description: 'Published contributions (andil, percentage points) of the components and the 11 expenditure groups to CPI y/y, January 2025 on; the CPI row is CPI y/y.',
  inputs: ['bps_series'],
  fn: (bps_series) => bps_series.filter((r) => r.date >= '2025-01-01' && r.contrib_yoy != null)
    .map((r) => ({ date: r.date, series: r.series, name: r.series === 'all' ? 'CPI' : r.label, order: r.order, kind: r.kind, contrib: r.contrib_yoy })),
});

(() => {
  const J = window.JG;
  const S = { grp: 'food', comp: 'core' };
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const mLabel = (d) => (d ? MONTHS[+d.slice(5, 7) - 1] + ' ' + d.slice(0, 4) : '');
  const visible = () => !document.getElementById('inflation').hidden;
  const pct = (v) => (v == null ? '—' : J.f1(v) + '%');
  const pct2 = (v) => (v == null ? '—' : d3.format('.2f')(v) + '%');
  const failed = (st) => st === 'error' || st === 'connect' || st === 'declined';
  const C = J.PAL;
  const NAMES = { all: 'CPI', core: 'Core', administered: 'Administered prices', volatile: 'Volatile food', energy: 'Energy', food_component: 'Food (bahan makanan)' };

  const seg = (id, key) => {
    const el = document.getElementById(id);
    el.addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b) return;
      S[key] = b.dataset.s;
      el.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      J.redrawCpi();
    });
  };
  seg('cpi-grp-seg', 'grp');
  seg('cpi-comp-seg', 'comp');

  function legend(id, series) {
    const el = document.getElementById(id);
    el.replaceChildren();
    series.forEach((s) => {
      const span = document.createElement('span'); const ln = document.createElement('span');
      ln.className = s.bar ? 'sw' : 'ln'; ln.style.background = s.color;
      span.append(ln, document.createTextNode(s.name)); el.appendChild(span);
    });
  }

  // Wide rows by date from several datasets: pick = [[name, dataset rows, series, measure]].
  function wide(pick, id, keep) {
    const by = new Map();
    pick.forEach(([name, rows, series, meas]) => rows.forEach((r) => {
      if (r.series !== series || r[meas] == null) return;
      if (!by.has(r.date)) by.set(r.date, { date: r.date });
      by.get(r.date)[name] = r[meas];
    }));
    const out = Array.from(by.values()).filter(keep || (() => true)).sort((a, b) => (a.date < b.date ? -1 : 1));
    return J.slice(out, id);
  }

  // Load the datasets a chart needs; null (and the box cleared or marked failed) until all are ready.
  function ready(box, ids) {
    const ds = ids.map((i) => dash.data(i));
    if (ds.some((d) => failed(d.status))) { J.fail(box); return null; }
    if (ds.some((d) => d.status !== 'ok')) { box.replaceChildren(); return null; }
    return ds.map((d) => d.data);
  }

  function xAxisBand(svg, rows, x, ml, W, H) {
    const years = Array.from(new Set(rows.map((r) => r.date.slice(0, 4))));
    let xt, xf;
    if (years.length <= 3) {
      const every = rows.length > 18 ? 3 : rows.length > 9 ? 2 : 1;
      xt = rows.map((r) => r.date).filter((d) => (+d.slice(5, 7) - 1) % every === 0);
      xf = (d) => `${MONTHS[+d.slice(5, 7) - 1]} ${d.slice(2, 4)}`;
    } else {
      const step = [1, 2, 5, 10].find((n) => years.length / n <= Math.max(1, (W - ml) / 56)) || 10;
      xt = rows.map((r) => r.date).filter((d) => d.slice(5, 7) === '01' && +d.slice(0, 4) % step === 0);
      xf = (d) => d.slice(0, 4);
    }
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).tickValues(xt).tickSize(0).tickFormat(xf)));
  }

  // Line chart.
  function lineChart(cardId, ids, series, rowsOf, H = 280) {
    const box = document.getElementById(cardId + '-chart');
    const ds = ready(box, ids); if (!ds) return;
    const rows = rowsOf(...ds);
    if (!rows.length) { box.replaceChildren(); return; }
    const keys = series.map((s) => s.key);
    const W = box.clientWidth;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const vals = rows.flatMap((r) => keys.map((k) => r[k])).filter((v) => v != null);
    const y = d3.scaleLinear([Math.min(0, d3.min(vals)), Math.max(0, d3.max(vals))], [H - 24, 10]).nice(8);
    const ticks = y.ticks(5);
    const fmt = d3.format(ticks.some((v) => !Number.isInteger(v)) ? '.1f' : '.0f');
    const ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    const x = d3.scaleUtc([J.date(rows[0].date), J.date(rows[rows.length - 1].date)], [ml, W - 8]);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - 8).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
    const xax = d3.axisBottom(x).tickSize(0);
    if (rows.length <= 36) xax.ticks(d3.utcMonth.every(rows.length > 18 ? 3 : rows.length > 9 ? 2 : 1)).tickFormat(d3.utcFormat('%b %y'));
    else xax.ticks(Math.max(2, Math.round((W - ml) / 70))).tickFormat(d3.utcFormat('%Y'));
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(xax));
    series.forEach((s) => {
      svg.append('path').attr('d', d3.line().defined((r) => r[s.key] != null).x((r) => x(J.date(r.date))).y((r) => y(r[s.key]))(rows))
        .attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
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

  // Line (left axis) and bars (right axis, or the same axis) with the zero lines aligned.
  function barLine(cardId, ids, line, bar, rowsOf, H = 280) {
    const box = document.getElementById(cardId + '-chart');
    const ds = ready(box, ids); if (!ds) return;
    const rows = rowsOf(...ds);
    if (!rows.length) { box.replaceChildren(); return; }
    const W = box.clientWidth;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const yv = rows.map((r) => r[line.key]).filter((v) => v != null), mv = rows.map((r) => r[bar.key]).filter((v) => v != null);
    const ext = (v) => [Math.min(0, d3.min(v) ?? 0), Math.max(0, d3.max(v) ?? 0)];
    const [ylo, yhi] = ext(yv), [mlo, mhi] = ext(mv);
    const k = line.sameAxis || !yv.length ? 1 : Math.max(Math.abs(ylo), yhi, 0.1) / Math.max(Math.abs(mlo), mhi, 0.05);
    const y = d3.scaleLinear([Math.min(ylo, mlo * k), Math.max(yhi, mhi * k)], [H - 24, 10]).nice();
    const yR = d3.scaleLinear(y.domain().map((v) => v / k), y.range());
    const ticks = y.ticks(5), rticks = yR.ticks(5);
    const fmtOf = (t) => d3.format(t.some((v) => !Number.isInteger(v)) ? '.1f' : '.0f');
    const fmt = fmtOf(ticks), rfmt = fmtOf(rticks);
    const ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    const mr = line.sameAxis ? 8 : J.textWidth(svg, rticks.map(rfmt)) + 10;
    const x = d3.scaleBand(rows.map((r) => r.date), [ml, W - mr]).padding(0.2);
    const cx = (d) => x(d) + x.bandwidth() / 2;
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - mr).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
    if (!line.sameAxis) J.axisStyle(svg.append('g').attr('transform', `translate(${W - mr + 4},0)`).call(d3.axisRight(yR).tickValues(rticks).tickSize(0).tickFormat(rfmt)));
    xAxisBand(svg, rows, x, ml, W, H);
    svg.append('g').selectAll('rect').data(rows.filter((r) => r[bar.key] != null)).join('rect')
      .attr('x', (r) => x(r.date)).attr('width', x.bandwidth())
      .attr('y', (r) => yR(Math.max(0, r[bar.key]))).attr('height', (r) => Math.max(0.5, Math.abs(yR(r[bar.key]) - yR(0))))
      .attr('fill', bar.color);
    svg.append('path').attr('d', d3.line().defined((r) => r[line.key] != null).x((r) => cx(r.date)).y((r) => y(r[line.key]))(rows))
      .attr('fill', 'none').attr('stroke', line.color).attr('stroke-width', 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    legend(cardId + '-legend', [line, { ...bar, bar: true }]);
    const card = document.getElementById(cardId), tip = J.tip(card);
    const rule = svg.append('line').attr('y1', 8).attr('y2', H - 22).attr('stroke', 'var(--cds-chart-reference)').attr('display', 'none');
    const dot = svg.append('circle').attr('r', 3.5).attr('fill', line.color).attr('display', 'none');
    svg.append('rect').attr('x', ml).attr('width', W - ml - mr).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const i = Math.max(0, Math.min(rows.length - 1, Math.floor((d3.pointer(ev)[0] - ml) / x.step())));
        const r = rows[i], px = cx(r.date);
        rule.attr('display', null).attr('x1', px).attr('x2', px);
        if (r[line.key] == null) dot.attr('display', 'none'); else dot.attr('display', null).attr('cx', px).attr('cy', y(r[line.key]));
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, mLabel(r.date), [[line.color, line.name, (line.two ? pct2 : pct)(r[line.key])], [bar.color, bar.name, pct2(r[bar.key])]], ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); dot.attr('display', 'none'); tip.style.display = 'none'; });
  }

  // Contributions to CPI y/y (stacked bars) with CPI y/y (line), all as published.
  function contribChart() {
    const id = 'cpi-contrib', box = document.getElementById(id + '-chart');
    const ds = ready(box, ['bps_series']); if (!ds) return;
    // stacked from zero: core, then administered prices, then volatile food
    const PARTS = [
      { key: 'core', name: 'Core', color: '#FFC000', bar: true },
      { key: 'administered', name: 'Administered prices', color: '#1F4E79', bar: true },
      { key: 'volatile', name: 'Volatile food', color: '#92D050', bar: true },
    ];
    const lineColor = '#BD1B21';
    const rows = wide([['all', ds[0], 'all', 'yoy']].concat(PARTS.map((p) => [p.key, ds[0], p.key, 'contrib_yoy'])), id,
      (r) => r.all != null && PARTS.every((p) => r[p.key] != null));
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
    const fmt = d3.format(ticks.some((v) => !Number.isInteger(v)) ? '.1f' : '.0f');
    const ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    const x = d3.scaleBand(rows.map((r) => r.date), [ml, W - 8]).padding(0.15);
    const cx = (d) => x(d) + x.bandwidth() / 2;
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - 8).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
    xAxisBand(svg, rows, x, ml, W, H);
    svg.append('g').selectAll('g').data(stack).join('g').attr('fill', (s, i) => PARTS[i].color)
      .selectAll('rect').data((s) => s).join('rect')
      .attr('x', (d) => x(d.data.date)).attr('width', x.bandwidth())
      .attr('y', (d) => y(Math.max(d[0], d[1]))).attr('height', (d) => Math.abs(y(d[0]) - y(d[1])));
    svg.append('path').attr('d', d3.line().x((r) => cx(r.date)).y((r) => y(r.all))(rows))
      .attr('fill', 'none').attr('stroke', lineColor).attr('stroke-width', 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    legend(id + '-legend', [{ name: 'CPI, y/y', color: lineColor }].concat(PARTS.slice().reverse()));
    const card = document.getElementById(id), tip = J.tip(card);
    const hl = svg.append('rect').attr('fill', 'var(--color-fg)').attr('opacity', 0.06).attr('display', 'none');
    const sg = (v) => (v == null ? '—' : (v > 0 ? '+' : '') + d3.format('.2f')(v) + 'ppt');
    svg.append('rect').attr('x', ml).attr('width', W - ml - 8).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const i = Math.max(0, Math.min(rows.length - 1, Math.floor((d3.pointer(ev)[0] - ml) / x.step())));
        const r = rows[i];
        hl.attr('display', null).attr('x', x(r.date) - x.step() * x.paddingInner() / 2).attr('width', x.step()).attr('y', 0).attr('height', H - 22);
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, mLabel(r.date), [[lineColor, 'CPI, y/y', pct2(r.all)]].concat(PARTS.slice().reverse().map((p) => [p.color, p.name, sg(r[p.key])])),
          ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { hl.attr('display', 'none'); tip.style.display = 'none'; });
  }

  function tiles() {
    const L = dash.data('cpi_latest'), P = dash.data('ppi_latest');
    const fill = (D, sel) => document.querySelectorAll(sel).forEach((s) => {
      const f = s.dataset.field, two = /_mom/.test(f);
      if (D.status === 'ok' && D.data.length) { s.classList.remove('dash-skeleton'); const v = D.data[0][f]; s.textContent = v == null ? '—' : (two ? d3.format('.2f')(v) : J.f1(v)); }
      else if (D.status !== 'loading') { s.classList.remove('dash-skeleton'); s.textContent = '—'; }
    });
    fill(L, '#cpi-headline [data-source="cpi_latest"]');
    fill(P, '#cpi-headline [data-source="ppi_latest"]');
    const hm = document.getElementById('cpi-month');
    if (L.status !== 'loading' && P.status !== 'loading') {
      hm.classList.remove('dash-skeleton');
      const parts = [];
      if (L.status === 'ok' && L.data.length) parts.push(`${mLabel(L.data[0].date)} CPI`);
      if (P.status === 'ok' && P.data.length) parts.push(`${mLabel(P.data[0].date)} WPI`);
      hm.textContent = parts.join(', ');
    }
    [['cpi_release', 'cpi'], ['bps_release', 'bps'], ['ppi_release', 'ppi']].forEach(([id]) => {
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
    const mk = (src, field, v) => {
      const b = document.createElement('b'); b.dataset.source = src; b.dataset.field = field; b.dataset.row = '0';
      b.textContent = J.f1(v); return b;
    };
    const t = (x) => p.append(document.createTextNode(x));
    const pc = () => { const b = document.createElement('b'); b.textContent = '%'; p.append(b); };
    p.replaceChildren();
    t(`In ${mLabel(a.date)}, CPI inflation was `); p.append(mk('cpi_latest', 'all_yoy', a.all_yoy)); pc();
    t(' y/y and core inflation '); p.append(mk('cpi_latest', 'core_yoy', a.core_yoy)); pc();
    t('. Volatile food prices were up '); p.append(mk('cpi_latest', 'volatile_yoy', a.volatile_yoy)); pc();
    t(' and administered prices '); p.append(mk('cpi_latest', 'administered_yoy', a.administered_yoy)); pc(); t('.');
    const P = dash.data('ppi_latest');
    if (P.status === 'ok' && P.data.length && P.data[0].wpi_yoy != null) {
      t(` Wholesale prices rose `); p.append(mk('ppi_latest', 'wpi_yoy', P.data[0].wpi_yoy)); pc(); t(` y/y in ${mLabel(P.data[0].date)}.`);
    }
  }

  // Heat tables: one value per month, each row coloured on its own range (green low, amber middle, red high).
  function heatTable(tblId, calcId, field, fmt, sk) {
    const tbl = document.getElementById(tblId);
    const D = dash.data(calcId);
    if (failed(D.status)) { tbl.replaceChildren(); return; }
    if (D.status !== 'ok') return;
    const dates = Array.from(new Set(D.data.map((r) => r.date))).sort();
    const keys = Array.from(new Set(D.data.map((r) => r.series)))
      .sort((p, q) => D.data.find((r) => r.series === p).order - D.data.find((r) => r.series === q).order);
    const val = new Map(D.data.map((r) => [`${r.series}|${r.date}`, r]));
    const STOPS = [[0, [99, 190, 123]], [0.5, [255, 235, 132]], [1, [248, 105, 107]]];
    const color = (t) => {
      const i = t > 0.5 ? 1 : 0; const [t0, c0] = STOPS[i], [t1, c1] = STOPS[i + 1], f = (t - t0) / (t1 - t0);
      return `rgb(${c0.map((c, k) => Math.round(c + (c1[k] - c) * f)).join(',')})`;
    };
    tbl.replaceChildren();
    const head = tbl.createTHead().insertRow();
    ['', ''].concat(dates.map((d) => `${MONTHS[+d.slice(5, 7) - 1]} ${d.slice(2, 4)}`)).forEach((t) => {
      const th = document.createElement('th'); th.textContent = t; head.appendChild(th);
    });
    const tb = tbl.createTBody();
    let prevKind = null;
    keys.forEach((k) => {
      const r0 = D.data.find((r) => r.series === k);
      if (prevKind && r0.kind !== prevKind && r0.kind === 'group') { const sp = tb.insertRow(); sp.className = 'spacer'; sp.insertCell().colSpan = dates.length + 2; }
      prevKind = r0.kind;
      const tr = tb.insertRow();
      if (k === 'all' || k === 'core') tr.className = 'lead';
      if (k === 'energy' || k === 'food_component') tr.className = 'sub';
      const nc = tr.insertCell(); nc.textContent = NAMES[k] || r0.name;
      tr.insertCell().className = 'wt';
      const vs = dates.map((d) => (val.get(`${k}|${d}`) || {})[field]).filter((v) => v != null);
      const lo = Math.min(...vs), hi = Math.max(...vs);
      dates.forEach((d) => {
        const td = tr.insertCell(); const r = val.get(`${k}|${d}`);
        if (!r || r[field] == null) return;
        const s = fmt(r[field]);
        td.textContent = /^-0\.0+$/.test(s) ? s.slice(1) : s;
        td.className = 'heat';
        td.style.background = color(hi > lo ? (r[field] - lo) / (hi - lo) : 0.5);
        td.style.color = '#1a1a1a';
      });
    });
    heatScroll(tblId, sk);
  }

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

  const GROUP_NAME = { food: 'Food, beverages and tobacco', housing: 'Housing, water, electricity and fuels', transport: 'Transport',
    restaurants: 'Food and beverage services', personal: 'Personal care and other services', education: 'Education', health: 'Health' };

  J.redrawCpi = () => {
    if (!visible()) return;
    lineChart('ppi-cpi', ['cpi_series', 'ppi_series'], [{ key: 'wpi', name: 'WPI', color: C[0] }, { key: 'cpi', name: 'CPI', color: C[1] }],
      (cpi, ppi) => wide([['cpi', cpi, 'all', 'yoy'], ['wpi', ppi, 'wpi', 'yoy']], 'ppi-cpi'));
    lineChart('cpi-measures', ['bps_series'], [
      { key: 'all', name: 'CPI', color: C[1] }, { key: 'core', name: 'Core', color: C[4] },
      { key: 'administered', name: 'Administered prices', color: C[0] }, { key: 'volatile', name: 'Volatile food', color: C[5] },
    ], (b) => wide(['all', 'core', 'administered', 'volatile'].map((k) => [k, b.filter((r) => r.index != null), k, 'yoy']), 'cpi-measures'));
    lineChart('cpi-long', ['cpi_series'], [{ key: 'cpi', name: 'CPI', color: C[1] }],
      (c) => wide([['cpi', c, 'all', 'yoy']], 'cpi-long'));
    barLine('cpi-ym', ['cpi_series'], { key: 'yoy', name: 'CPI, y/y (left)', color: C[1] }, { key: 'mom', name: 'CPI, m/m (right)', color: C[0] },
      (c) => wide([['yoy', c, 'all', 'yoy'], ['mom', c, 'all', 'mom']], 'cpi-ym'));
    barLine('cpi-comp', ['bps_series'], { key: 'yoy', name: `${NAMES[S.comp]}, y/y (left)`, color: C[1] }, { key: 'mom', name: `${NAMES[S.comp]}, m/m (right)`, color: C[0] },
      (b) => wide([['yoy', b.filter((r) => r.index != null), S.comp, 'yoy'], ['mom', b, S.comp, 'mom']], 'cpi-comp'));
    contribChart();
    lineChart('cpi-fe', ['bps_series'], [{ key: 'food', name: 'Food (bahan makanan)', color: C[5] }, { key: 'energy', name: 'Energy', color: C[0] }],
      (b) => wide([['food', b, 'food_component', 'yoy'], ['energy', b, 'energy', 'yoy']], 'cpi-fe'));
    barLine('cpi-grp', ['bps_series'], { key: 'yoy', name: `${GROUP_NAME[S.grp]}, y/y (left)`, color: C[1] }, { key: 'mom', name: 'm/m (right)', color: C[0] },
      (b) => wide([['yoy', b, S.grp, 'yoy'], ['mom', b, S.grp, 'mom']], 'cpi-grp', (r) => r.yoy != null));
    lineChart('ppi-sec', ['ppi_series'], [
      { key: 'wpi', name: 'WPI', color: C[1] }, { key: 'agriculture', name: 'Agriculture, forestry, fishery', color: C[5] },
      { key: 'ores_utilities', name: 'Ores, minerals, utilities', color: C[3] }, { key: 'food_textiles', name: 'Food, textiles, leather', color: C[4] },
      { key: 'other_goods', name: 'Other transportable goods', color: C[0] }, { key: 'metal_machinery', name: 'Metals, machinery', color: C[6] },
    ], (p) => wide(['wpi', 'agriculture', 'ores_utilities', 'food_textiles', 'other_goods', 'metal_machinery'].map((k) => [k, p, k, 'yoy']), 'ppi-sec'));
  };

  dash.onData(() => {
    tiles(); takeaway();
    heatTable('cpi-heat-table', 'cpi_heat', 'yoy', (v) => J.f1(v), 'heatScrolled');
    heatTable('cpi-ctab-table', 'cpi_ctab', 'contrib', (v) => d3.format('.2f')(v), 'ctabScrolled');
    J.redrawCpi();
  });
  J.redrawCpi();
})();
