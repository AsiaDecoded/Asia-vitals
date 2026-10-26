// India dashboard: CPI (MoSPI), all-India general index, Jan 2013 on.

dash.calc('cpi_series', {
  title: 'CPI series',
  description: 'Every CPI row with its cells read as numbers.',
  inputs: ['in_cpi'],
  fn: (in_cpi) => {
    const n = (v) => (v === '' || v == null ? null : Number(v));
    return in_cpi.map((r) => ({
      date: r.date, series: r.series, label: r.label, order: Number(r.order),
      index: n(r.index), yoy: n(r.yoy), yoy_published: n(r.yoy_published), basis: r.basis,
    }));
  },
});

dash.calc('cpi_latest', {
  title: 'Latest month and the one before',
  description: 'MoSPI published y/y for combined, rural and urban CPI in the latest month and the month before.',
  inputs: ['cpi_series'],
  fn: (cpi_series) => {
    const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    const last = cpi_series.reduce((m, r) => (r.date > m ? r.date : m), '');
    const y = Number(last.slice(0, 4)), mo = Number(last.slice(5, 7));
    const prev = mo === 1 ? `${y - 1}-12-01` : `${y}-${String(mo - 1).padStart(2, '0')}-01`;
    const get = (d, s, f) => { const r = cpi_series.find((x) => x.date === d && x.series === s); return r ? r[f] : null; };
    const row = { date: last, prev_date: prev, month: `${MONTHS[mo - 1]} ${y}`, prev_month: MONTHS[(mo + 10) % 12] };
    ['combined', 'rural', 'urban'].forEach((s) => {
      row[`${s}_yoy`] = get(last, s, 'yoy_published'); row[`${s}_yoy_prev`] = get(prev, s, 'yoy_published');
    });
    return [row];
  },
});


dash.calc('core_series', {
  title: 'CPI and core, y/y',
  description: 'Combined CPI y/y and core 1 and core 2 y/y, from the first month with core figures, months without a core figure are left blank.',
  inputs: ['cpi_series', 'in_cpi_core'],
  fn: (cpi_series, in_cpi_core) => {
    const core = in_cpi_core.map((r) => ({ date: r.date, series: r.series, yoy: r.yoy === '' || r.yoy == null ? null : Number(r.yoy) }));
    const first = core.filter((r) => r.yoy != null).reduce((m, r) => (m && m < r.date ? m : r.date), null);
    const cpi = cpi_series.filter((r) => r.series === 'combined' && first && r.date >= first)
      .map((r) => ({ date: r.date, series: 'cpi', yoy: r.yoy }));
    return cpi.concat(core.filter((r) => first && r.date >= first));
  },
});

dash.calc('cpi_movers', {
  title: 'Item contributions, 3- and 6-month averages',
  description: 'For each CPI item (2024 base, all-India combined): its weight and MoSPI published y/y in the latest month, and the average of its contribution to CPI y/y over the latest 3 and 6 months (items present in every month of the window).',
  inputs: ['in_cpi_items'],
  fn: (in_cpi_items) => {
    const n = (v) => (v === '' || v == null ? null : Number(v));
    const months = Array.from(new Set(in_cpi_items.map((r) => r.date))).sort();
    const latest = months[months.length - 1];
    const by = new Map();
    in_cpi_items.forEach((r) => {
      if (!by.has(r.code)) by.set(r.code, { code: r.code, months: {} });
      by.get(r.code).months[r.date] = { name: r.name, weight: n(r.weight), yoy: n(r.yoy), c: n(r.contrib_yoy) };
    });
    const avg = (it, k) => {
      const ms = months.slice(-k);
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
dash.calc('diffusion_series', {
  title: 'CPI diffusion index',
  description: 'Diffusion index (share of items rising minus share falling) and the shares rising and falling, % of items, one row per month and series, from Jan 2026 (2024 base).',
  inputs: ['in_cpi_diffusion'],
  fn: (in_cpi_diffusion) => {
    const by = new Map(in_cpi_diffusion.map((r) => [r.date, r]));
    const ds = Array.from(by.keys()).filter((d) => d >= '2026-01-01').sort();
    const out = [];
    if (!ds.length) return out;
    for (let d = new Date(ds[0] + 'T00:00:00Z'); d <= new Date(ds[ds.length - 1] + 'T00:00:00Z'); d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1))) {
      const k = d.toISOString().slice(0, 10), r = by.get(k);
      ['diffusion', 'share_rising', 'share_falling'].forEach((f) => out.push({ date: k, series: f, value: r && r[f] !== '' ? Number(r[f]) : null }));
    }
    return out;
  },
});

dash.calc('gs_series', {
  title: 'Goods and services CPI, y/y',
  description: 'Goods and services CPI y/y (2024 base), one row per month and series, from Jan 2026.',
  inputs: ['in_cpi_goods_services'],
  fn: (rows) => rows.filter((r) => r.yoy !== '' && r.yoy != null)
    .map((r) => ({ date: r.date, series: r.series, yoy: Number(r.yoy) })),
});

dash.calc('fe_series', {
  title: 'Food, food and beverages, and energy CPI, y/y',
  description: 'Food, food and beverages, and energy CPI y/y from the linked index, one row per month and series, months without a figure are blank.',
  inputs: ['in_cpi_food_energy'],
  fn: (rows) => rows.map((r) => ({ date: r.date, series: r.series, yoy: r.yoy === '' || r.yoy == null ? null : Number(r.yoy) })),
});

dash.calc('ppi_cpi', {
  title: 'Producer and consumer price inflation',
  description: 'Spliced output PPI y/y (WPI 2011-12 linked before Apr 2023) and combined CPI y/y (chart 2), from Apr 2013.',
  inputs: ['in_ppi_spliced', 'cpi_series'],
  fn: (ppi, cpi_series) => {
    const p = ppi.filter((r) => r.yoy !== '' && r.yoy != null).map((r) => ({ date: r.date, series: 'ppi', yoy: Number(r.yoy) }));
    const first = p.length ? p[0].date : '9999';
    const c = cpi_series.filter((r) => r.series === 'combined' && r.yoy != null && r.date >= first)
      .map((r) => ({ date: r.date, series: 'cpi', yoy: r.yoy }));
    return p.concat(c);
  },
});

(() => {
  const J = window.JG;
  J.theme();
  J.addPeriods();
  dash.onData(() => J.theme());

  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const mLabel = (d) => (d ? MON[+d.slice(5, 7) - 1] + ' ' + d.slice(0, 4) : '');
  const failed = (st) => st === 'error' || st === 'connect' || st === 'declined';
  const visible = () => !document.getElementById('inflation').hidden;
  const f1 = (v) => (v == null ? '—' : J.f1(v));
  const pct = (v) => (v == null ? '—' : J.f1(v) + '%');
  const SECTORS = [
    { key: 'combined', name: 'CPI', color: 'var(--ad-c2)' },
    { key: 'rural', name: 'Rural', color: 'var(--ad-c5)' },
    { key: 'urban', name: 'Urban', color: 'var(--ad-c1)', dash: true },
  ];
  const defPeriod = (id) => { const c = document.getElementById(id); return c && c.dataset.def != null ? Number(c.dataset.def) : 120; };
  const win = (rows, id) => { const n = J.periodOf(id, defPeriod(id)); return n ? rows.slice(-n) : rows; };

  function legend(id, series) {
    const el = document.getElementById(id);
    el.replaceChildren();
    series.forEach((s) => {
      const span = document.createElement('span'); const ln = document.createElement('span');
      ln.className = s.bar ? 'sw' : 'ln';
      if (s.dash) { ln.style.background = `repeating-linear-gradient(90deg, ${s.color} 0 5px, transparent 5px 8px)`; } else { ln.style.background = s.color; }
      span.append(ln, document.createTextNode(s.name)); el.appendChild(span);
    });
  }

  // {date, combined, rural, urban} rows for one measure.
  function wide(rows, field) {
    const by = new Map();
    rows.forEach((r) => {
      if (!by.has(r.date)) by.set(r.date, { date: r.date });
      by.get(r.date)[r.series] = r[field];
    });
    return Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
  }

  function frame(box, rows, H, vals, fmt, zero, mr) {
    const W = box.clientWidth;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    let lo = d3.min(vals), hi = d3.max(vals);
    if (zero) { lo = Math.min(0, lo); hi = Math.max(0, hi); }
    const y = d3.scaleLinear([lo, hi], [H - 24, 12]).nice();
    const ticks = y.ticks(5);
    const ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    const x = d3.scaleUtc([J.date(rows[0].date), J.date(rows[rows.length - 1].date)], [ml, W - mr]);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - mr).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (zero && v === 0 ? 'var(--cds-chart-reference)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
    const nYears = Math.max(1, Math.round((W - ml - mr) / 56));
    const span = Number(rows[rows.length - 1].date.slice(0, 4)) - Number(rows[0].date.slice(0, 4)) + 1;
    const nMonths = (Number(rows[rows.length - 1].date.slice(0, 4)) - Number(rows[0].date.slice(0, 4))) * 12 + Number(rows[rows.length - 1].date.slice(5, 7)) - Number(rows[0].date.slice(5, 7)) + 1;
    if (span <= 2 && nMonths <= 24) {
      const room = Math.max(1, Math.floor((W - ml - mr) / 52));
      const mstep = [1, 2, 3, 6].find((s) => nMonths / s <= room) || 6;
      J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).ticks(d3.utcMonth.every(mstep)).tickSize(0).tickFormat(d3.utcFormat('%b %y'))));
    } else {
      const step = [1, 2, 5, 10, 20, 25, 50].find((s) => span / s <= nYears) || 50;
      J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).ticks(d3.utcYear.every(step)).tickSize(0).tickFormat(d3.utcFormat('%Y'))));
    }
    // Keep the end labels of the x axis inside the chart.
    svg.selectAll('g.tick text').each(function () {
      const t = this, g = t.parentNode, m = /translate\(([-\d.]+)/.exec(g.getAttribute('transform') || '');
      if (!m || g.parentNode.getAttribute('transform') !== `translate(0,${H - 20})`) return;
      const px = Number(m[1]), w = t.getComputedTextLength();
      if (px + w / 2 > W - 2) t.setAttribute('text-anchor', 'end');
      else if (px - w / 2 < 2) t.setAttribute('text-anchor', 'start');
    });
    return { svg, x, y, W, ml };
  }

  function hover(svg, card, x, rows, H, ml, right, onMove) {
    const tip = J.tip(card);
    const rule = svg.append('line').attr('y1', 8).attr('y2', H - 22).attr('stroke', 'var(--cds-chart-reference)').attr('display', 'none');
    const bis = d3.bisector((r) => J.date(r.date)).center;
    const extras = [];
    svg.append('rect').attr('x', ml).attr('width', Math.max(0, right - ml)).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [mx] = d3.pointer(ev);
        const r = rows[bis(rows, x.invert(mx))];
        const px = x(J.date(r.date));
        rule.attr('display', null).attr('x1', px).attr('x2', px);
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, mLabel(r.date), onMove(r, px, extras), ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); extras.forEach((d) => d.attr('display', 'none')); tip.style.display = 'none'; });
    return extras;
  }

  function lines(boxId, cardId, legendId, field, series, fmt, H, zero, splice, dsId, anyStart) {
    const box = document.getElementById(boxId);
    const D = dash.data(dsId || 'cpi_series');
    legend(legendId, series);
    if (failed(D.status)) { box.classList.remove('dash-skeleton'); J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); box.classList.add('dash-skeleton'); return; }
    box.classList.remove('dash-skeleton');
    // Rows from the first month every series has; a month a series lacks is a gap in its line.
    const all = wide(D.data, field);
    const start = all.findIndex((r) => (anyStart ? series.some((s) => r[s.key] != null) : series.every((s) => r[s.key] != null)));
    let end = all.length;
    while (end > 0 && series.every((s) => all[end - 1][s.key] == null)) end -= 1;
    const rows = start < 0 ? [] : win(all.slice(start, end), cardId);
    if (!rows.length) { box.replaceChildren(); return; }
    const mr = 8;
    const { svg, x, y, W, ml } = frame(box, rows, H, rows.flatMap((r) => series.map((s) => r[s.key])).filter((v) => v != null), fmt, zero, mr);
    const spLabel = splice && typeof splice === 'object' ? splice.label : '2024 base';
    if (splice && typeof splice === 'object') splice = splice.date;
    if (splice && rows[0].date < splice && rows[rows.length - 1].date >= splice) {
      const sx = x(J.date(splice));
      svg.append('line').attr('x1', sx).attr('x2', sx).attr('y1', 12).attr('y2', H - 24)
        .attr('stroke', 'var(--ad-axis)').attr('stroke-dasharray', '3 3');
      const t = svg.append('text').attr('y', 16).attr('font-size', 11).attr('fill', 'var(--ad-ink)').text(spLabel);
      const tw = t.node().getComputedTextLength();
      t.attr('x', sx + 4 + tw > W - mr ? sx - 4 - tw : sx + 4);
    }
    series.forEach((s) => {
      svg.append('path').attr('d', d3.line().defined((r) => r[s.key] != null).x((r) => x(J.date(r.date))).y((r) => y(r[s.key]))(rows))
        .attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', 2.5).attr('stroke-linecap', s.dash ? 'butt' : 'round').attr('stroke-linejoin', 'round')
        .attr('stroke-dasharray', s.dash ? '6 4' : null);
    });
    const card = document.getElementById(cardId);
    const dots = series.map((s) => svg.append('circle').attr('r', 3.5).attr('fill', s.color).attr('display', 'none'));
    const extras = hover(svg, card, x, rows, H, ml, W - mr, (r, px) => {
      dots.forEach((d, i) => { const v = r[series[i].key]; d.attr('display', v == null ? 'none' : null).attr('cx', px).attr('cy', v == null ? 0 : y(v)); });
      return series.map((s) => [s.color, s.name, r[s.key] == null ? 'n/a' : fmt(r[s.key])]);
    });
    extras.push(...dots);
  }



  // Contributions to CPI y/y: stacked bars (food, fuel, ex food and fuel) and the CPI y/y line.
  function contribChart(cardId, dsId, showBreak) {
    const box = document.getElementById(cardId + '-chart');
    const D = dash.data(dsId);
    const PARTS = [
      { key: 'core', name: 'CPI excluding food and fuel', color: 'var(--ad-c5)', bar: true },
      { key: 'food', name: 'Food and beverages', color: 'var(--ad-c6)', bar: true },
      { key: 'fuel', name: 'Fuel', color: 'var(--ad-c1)', bar: true },
    ];
    const LINE = { key: 'cpi', name: 'CPI (y/y, %)', color: 'var(--ad-c2)' };
    legend(cardId + '-legend', [LINE].concat(PARTS));
    if (failed(D.status)) { box.classList.remove('dash-skeleton'); J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); box.classList.add('dash-skeleton'); return; }
    box.classList.remove('dash-skeleton');
    const n = (v) => (v === '' || v == null ? null : Number(v));
    const all = D.data.map((r) => ({ date: r.date, cpi: n(r.cpi_yoy), food: n(r.food), fuel: n(r.fuel), core: n(r.core), base: r.base || r.basis }))
      .sort((p, q) => (p.date < q.date ? -1 : 1));
    // One row per month, so months with no figures show as gaps rather than joining across them.
    const full = [];
    if (all.length) {
      const byDate = new Map(all.map((r) => [r.date, r]));
      for (let d = J.date(all[0].date); d <= J.date(all[all.length - 1].date); d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1))) {
        const k = d.toISOString().slice(0, 10);
        full.push(byDate.get(k) || { date: k, cpi: null, food: null, fuel: null, core: null, base: null });
      }
    }
    const rows = win(full, cardId);
    if (!rows.length) { box.replaceChildren(); return; }
    rows.forEach((r) => {
      let pos = 0, neg = 0;
      r.stack = PARTS.map((p) => { const v = r[p.key] || 0; const y0 = v >= 0 ? pos : neg; if (v >= 0) pos += v; else neg += v; return { p, y0, y1: y0 + v }; });
      r.lo = neg; r.hi = pos;
    });
    const H = 300, mr = 8;
    const vals = rows.flatMap((r) => [r.lo, r.hi, r.cpi]).filter((v) => v != null);
    const { svg, x, y, W, ml } = frame(box, rows, H, vals, (v) => d3.format('.0f')(v), true, mr);
    const step = (W - ml - mr) / Math.max(1, rows.length);
    const bw = Math.max(1, Math.min(14, step * 0.75));
    rows.forEach((r) => {
      const cx = x(J.date(r.date));
      r.stack.forEach((s) => {
        if (s.y1 === s.y0) return;
        svg.append('rect').attr('x', cx - bw / 2).attr('width', bw)
          .attr('y', y(Math.max(s.y0, s.y1))).attr('height', Math.abs(y(s.y0) - y(s.y1))).attr('fill', s.p.color);
      });
    });
    svg.append('path').attr('d', d3.line().defined((r) => r.cpi != null).x((r) => x(J.date(r.date))).y((r) => y(r.cpi))(rows))
      .attr('fill', 'none').attr('stroke', LINE.color).attr('stroke-width', 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    const brk = showBreak && rows.find((r, i) => i > 0 && r.base && rows[i - 1].base && r.base !== rows[i - 1].base);
    if (brk) {
      const sx = x(J.date(brk.date)) - step / 2;
      svg.append('line').attr('x1', sx).attr('x2', sx).attr('y1', 12).attr('y2', H - 24)
        .attr('stroke', 'var(--ad-ink)').attr('stroke-dasharray', '4 3');
      const t = svg.append('text').attr('y', 16).attr('font-size', 11).attr('fill', 'var(--ad-ink)').text('2024 base');
      const tw = t.node().getComputedTextLength();
      t.attr('x', sx + 4 + tw > W - mr ? sx - 4 - tw : sx + 4);
    }
    const card = document.getElementById(cardId);
    const dot = svg.append('circle').attr('r', 3.5).attr('fill', LINE.color).attr('display', 'none');
    const fmt2 = (v) => (v == null ? 'n/a' : v.toFixed(2));
    const extras = hover(svg, card, x, rows, H, ml, W - mr, (r, px) => {
      dot.attr('display', r.cpi == null ? 'none' : null).attr('cx', px).attr('cy', r.cpi == null ? 0 : y(r.cpi));
      return [[LINE.color, 'CPI, y/y %', r.cpi == null ? 'n/a' : r.cpi.toFixed(2)]]
        .concat(PARTS.slice().reverse().map((p) => [p.color, p.name + ', pp', fmt2(r[p.key])]));
    });
    extras.push(dot);
  }

  // IMF long-term y/y: one series, monthly (date) or annual (year).
  function longChart(boxId, cardId, dsId, annual) {
    const box = document.getElementById(boxId);
    const D = dash.data(dsId);
    if (failed(D.status)) { box.classList.remove('dash-skeleton'); J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); box.classList.add('dash-skeleton'); return; }
    box.classList.remove('dash-skeleton');
    const all = D.data.filter((r) => r.yoy !== '' && r.yoy != null)
      .map((r) => ({ date: annual ? `${r.year}-01-01` : r.date, label: annual ? String(r.year) : mLabel(r.date), v: Number(r.yoy) }))
      .sort((p, q) => (p.date < q.date ? -1 : 1));
    const n = J.periodOf(cardId, 0);
    const rows = n ? all.slice(-n) : all;
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280, mr = 8, color = 'var(--ad-c1)';
    const { svg, x, y, W, ml } = frame(box, rows, H, rows.map((r) => r.v), (v) => d3.format('.0f')(v), true, mr);
    svg.append('path').attr('d', d3.line().x((r) => x(J.date(r.date))).y((r) => y(r.v))(rows))
      .attr('fill', 'none').attr('stroke', color).attr('stroke-width', annual ? 2.5 : 1.75).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    const card = document.getElementById(cardId), tip = J.tip(card);
    const dot = svg.append('circle').attr('r', 3.5).attr('fill', color).attr('display', 'none');
    const rule = svg.append('line').attr('y1', 8).attr('y2', H - 22).attr('stroke', 'var(--cds-chart-reference)').attr('display', 'none');
    const bis = d3.bisector((r) => J.date(r.date)).center;
    svg.append('rect').attr('x', ml).attr('width', Math.max(0, W - mr - ml)).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [mx] = d3.pointer(ev);
        const r = rows[bis(rows, x.invert(mx))];
        const px = x(J.date(r.date));
        rule.attr('display', null).attr('x1', px).attr('x2', px);
        dot.attr('display', null).attr('cx', px).attr('cy', y(r.v));
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, r.label, [[null, 'y/y', pct(r.v)]], ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); dot.attr('display', 'none'); tip.style.display = 'none'; });
  }

  function takeaway() {
    const p = document.getElementById('cpi-takeaway');
    const L = dash.data('cpi_latest');
    if (L.status !== 'ok' || !L.data.length) { if (failed(L.status)) p.replaceChildren(); return; }
    const a = L.data[0];
    const mk = (field) => { const b = document.createElement('b'); b.dataset.source = 'cpi_latest'; b.dataset.field = field; b.dataset.row = '0'; b.textContent = J.f1(a[field]) + '%'; return b; };
    const t = (x) => p.append(document.createTextNode(x));
    p.replaceChildren();
    t(`In ${mLabel(a.date)}, consumer prices were `); p.append(mk('combined_yoy')); t(` higher than a year earlier, against `);
    p.append(mk('combined_yoy_prev')); t(` in ${mLabel(a.prev_date)}. Rural inflation was `); p.append(mk('rural_yoy'));
    t(' and urban '); p.append(mk('urban_yoy')); t('.');
  }

  function tiles() {
    const L = dash.data('cpi_latest');
    const hm = document.getElementById('cpi-month');
    document.querySelectorAll('#inflation [data-source="cpi_latest"]').forEach((el) => {
      if (el.closest('#cpi-takeaway')) return;
      if (L.status !== 'ok' || !L.data.length) { el.textContent = '—'; return; }
      el.classList.remove('dash-skeleton');
      const v = L.data[0][el.dataset.field];
      el.textContent = el === hm ? v : f1(v);
    });
  }

  // Biggest contributors to CPI y/y: five largest positive and negative item contributions, 3- or 6-month average.
  let moversN = 3;
  function moversTable() {
    const tb = document.querySelector('#cpi-movers-table tbody');
    const M = dash.data('cpi_movers');
    if (failed(M.status)) { tb.replaceChildren(); const td = tb.insertRow().insertCell(); td.colSpan = 4; J.fail(td); return; }
    if (M.status !== 'ok') return;
    const k = moversN === 6 ? 'avg6' : 'avg3';
    const rows = M.data.filter((r) => r[k] != null);
    const up = rows.slice().sort((a, b) => b[k] - a[k] || b.yoy - a.yoy).slice(0, 5);
    const down = rows.slice().sort((a, b) => a[k] - b[k] || a.yoy - b.yoy).slice(0, 5);
    const date = M.data.length ? M.data[0].date : null;
    document.getElementById('cpi-movers-units').textContent = date ? `%, ppt, ${moversN}-month average to ${mLabel(date)}` : '%, ppt';
    document.getElementById('cpi-movers-avg').textContent = `Contribution, ${moversN}m avg.`;
    tb.replaceChildren();
    [['Largest positive contributions', up], ['Largest negative contributions', down]].forEach(([g, list], gi) => {
      const gr = tb.insertRow(); gr.className = 'grp' + (gi ? ' sep' : '');
      const gtd = gr.insertCell(); gtd.colSpan = 4; gtd.textContent = g;
      list.forEach((r) => {
        const tr = tb.insertRow(); tr.dataset.key = r.name;
        [['name', r.name], ['weight', r.weight], ['yoy', r.yoy], [k, r[k]]].forEach(([f, v]) => {
          const td = tr.insertCell();
          if (f === 'name') { td.textContent = v; return; }
          td.textContent = v == null ? '' : (f === 'yoy' ? J.f1(v) : d3.format('.2f')(v));
          if (v != null && v < 0 && f !== 'weight') td.classList.add('neg');
        });
      });
    });
  }
  const mseg = document.getElementById('cpi-movers-seg');
  mseg.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    moversN = Number(b.dataset.n);
    mseg.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    moversTable();
  });

  J.redrawCpi = () => {
    if (!visible()) return;
    lines('cpi-sectors-chart', 'cpi-sectors', 'cpi-sectors-legend', 'yoy', SECTORS, (v) => d3.format('.0f')(v), 280, true);
    lines('cpi-core-chart', 'cpi-core', 'cpi-core-legend', 'yoy', [
      { key: 'cpi', name: 'CPI', color: 'var(--ad-c1)' },
      { key: 'core1', name: 'Core 1 (CPI excluding food and fuel)', color: 'var(--ad-c2)' },
      { key: 'core2', name: 'Core 2 (CPI excluding food, fuel and precious metals)', color: 'var(--ad-c3)' },
    ], (v) => d3.format('.1f')(v), 280, false, null, 'core_series');
    contribChart('cpi-contrib-linked', 'in_cpi_contrib_linked', false);
    lines('cpi-fe-chart', 'cpi-fe', 'cpi-fe-legend', 'yoy', [
      { key: 'food', name: 'Food', color: 'var(--ad-c3)' },
      { key: 'energy', name: 'Energy (electricity, gas and other fuels, petrol, diesel and CNG)', color: 'var(--ad-c1)' },
    ], (v) => d3.format('.0f')(v), 280, true, null, 'fe_series');
    lines('cpi-gs-chart', 'cpi-gs', 'cpi-gs-legend', 'yoy', [
      { key: 'goods', name: 'Goods', color: 'var(--ad-c1)' },
      { key: 'services', name: 'Services', color: 'var(--ad-c2)' },
    ], (v) => d3.format('.0f')(v), 280, true, null, 'gs_series');
    lines('cpi-diffusion-chart', 'cpi-diffusion', 'cpi-diffusion-legend', 'value', [
      { key: 'diffusion', name: 'Diffusion index (rising minus falling)', color: 'var(--ad-c2)' },
      { key: 'share_rising', name: 'Rising', color: 'var(--ad-c6)' },
      { key: 'share_falling', name: 'Falling', color: 'var(--ad-c1)' },
    ], (v) => d3.format('.0f')(v), 280, true, null, 'diffusion_series');
    lines('ppi-cpi-chart', 'ppi-cpi', 'ppi-cpi-legend', 'yoy', [
      { key: 'ppi', name: 'PPI', color: 'var(--ad-c1)' },
      { key: 'cpi', name: 'CPI', color: 'var(--ad-c2)' },
    ], (v) => d3.format('.0f')(v), 280, true, null, 'ppi_cpi');
    longChart('cpi-long-m-chart', 'cpi-long-m', 'in_cpi_imf_m', false);
    longChart('cpi-long-a-chart', 'cpi-long-a', 'in_cpi_imf_a', true);
  };

  // Tabs: one page at a time; charts on a hidden page are drawn when it is shown.
  const tabs = document.querySelectorAll('.jg-tabs [data-tab]');
  const show = (id) => {
    if (!document.getElementById(id)) return;
    tabs.forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === id)));
    document.querySelectorAll('.jg-page').forEach((pg) => { pg.hidden = pg.id !== id; });
    dash.setLink(id);
    if (id === 'inflation') J.redrawCpi();
  };
  J.show = show;
  tabs.forEach((b) => b.addEventListener('click', () => show(b.dataset.tab)));
  if (location.hash.slice(1) === 'methodology') show('methodology');

  dash.onData(() => { tiles(); takeaway(); moversTable(); J.redrawCpi(); });
})();
