// Taiwan dashboard: CPI, PPI and import/export prices as published by DGBAS (2021 = 100).
// Nothing here calculates a figure: the calcs below only pick rows and reshape them for the charts.

dash.calc('cpi_latest', {
  title: 'Latest month and the one before',
  description: 'DGBAS published y/y for CPI, core, goods, services, food and energy, and CPI m/m, in the latest month and the month before.',
  inputs: ['tw_cpi'],
  fn: (tw_cpi) => {
    const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    const nat = tw_cpi.filter((r) => r.area === 'national' && r.value !== '' && r.value != null);
    const last = nat.filter((r) => r.series === 'all' && r.measure === 'yoy').reduce((m, r) => (r.date > m ? r.date : m), '');
    const y = Number(last.slice(0, 4)), mo = Number(last.slice(5, 7));
    const prev = mo === 1 ? `${y - 1}-12-01` : `${y}-${String(mo - 1).padStart(2, '0')}-01`;
    const get = (d, s, m) => { const r = nat.find((x) => x.date === d && x.series === s && x.measure === m); return r ? Number(r.value) : null; };
    const row = { date: last, prev_date: prev, month: `${MONTHS[mo - 1]} ${y}`, all_mom: get(last, 'all', 'mom'), all_sa_mom: get(last, 'all', 'sa_mom') };
    ['all', 'core', 'goods', 'services', 'food', 'energy'].forEach((s) => { row[`${s}_yoy`] = get(last, s, 'yoy'); row[`${s}_yoy_prev`] = get(prev, s, 'yoy'); });
    return [row];
  },
});

dash.calc('ppi_latest', {
  title: 'Latest PPI',
  description: 'DGBAS published PPI and import and export prices (US dollars) y/y in the latest month and the month before.',
  inputs: ['tw_ppi'],
  fn: (tw_ppi) => {
    const pick = (s) => tw_ppi.filter((x) => x.series === s && x.measure === 'yoy' && x.value !== '').sort((a, b) => (a.date < b.date ? -1 : 1));
    const v = (a, i) => (a.length >= i ? Number(a[a.length - i].value) : null);
    const ppi = pick('ppi_all'), ipi = pick('ipi_usd_all'), epi = pick('epi_usd_all');
    return [{ date: ppi.length ? ppi[ppi.length - 1].date : '', ppi_yoy: v(ppi, 1), ppi_yoy_prev: v(ppi, 2), ipi_yoy: v(ipi, 1), epi_yoy: v(epi, 1) }];
  },
});

dash.calc('impacts_latest', {
  title: 'Contributions by group, latest month',
  description: 'DGBAS published weights, changes and contributions to CPI (percentage points) for the seven groups, goods and services in the latest release (table 1).',
  inputs: ['tw_cpi_contrib'],
  fn: (rows) => {
    const KEEP = ['all', 'food', 'clothing', 'housing', 'transport_comm', 'health', 'education_entertainment', 'miscellaneous', 'goods', 'services'];
    const last = rows.reduce((m, r) => (r.date > m ? r.date : m), '');
    const out = [];
    rows.filter((r) => r.date === last && KEEP.includes(r.series)).forEach((r) => {
      ['yoy', 'mom'].forEach((m) => out.push({ date: r.date, measure: m, series: r.series, label: r.label, order: KEEP.indexOf(r.series),
        weight_pct: Number(r.weight_pct), rate: Number(r[m]), pp: Number(r[`${m}_pp`]) }));
    });
    return out;
  },
});

(() => {
  const J = window.JG;
  J.theme();
  document.querySelectorAll('#inflation .jg-card').forEach((c) => {
    if (c.id && c.querySelector('.jg-chart') && c.dataset.periods !== 'none') J.period[c.id] = c.dataset.def != null ? Number(c.dataset.def) : 120;
  });
  J.addPeriods();
  J.addSliders(() => J.redrawCpi());
  dash.onData(() => J.theme());

  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const mLabel = (d) => (d ? MON[+d.slice(5, 7) - 1] + ' ' + d.slice(0, 4) : '');
  const failed = (st) => st === 'error' || st === 'connect' || st === 'declined';
  const visible = () => !document.getElementById('inflation').hidden;
  const f1 = (v) => (v == null ? '—' : J.f1(v));
  const f2 = (v) => (v == null ? '—' : v.toFixed(2));
  const num = (v) => (v === '' || v == null ? null : Number(v));
  const win = (rows, id) => J.slice(J.window(rows, id), id);
  const fmt0 = (v) => d3.format('.0f')(v);
  const BASES = ['2023-01-01'];
  // Standing colours for contribution charts (Japan, India, Singapore pages).
  const CC = { line: '#BD1B21', services: '#FFC000', goods: '#1F4E79', fbss: '#92D050', grey: '#A6A6A6', blue: '#0C84FF' };

  function legend(id, series) {
    const el = document.getElementById(id);
    if (!el) return;
    el.replaceChildren();
    series.forEach((s) => {
      const span = document.createElement('span'); const ln = document.createElement('span');
      ln.className = s.bar ? 'sw' : 'ln';
      if (s.dash) { ln.style.background = `repeating-linear-gradient(90deg, ${s.color} 0 5px, transparent 5px 8px)`; } else { ln.style.background = s.color; }
      span.append(ln, document.createTextNode(s.name)); el.appendChild(span);
    });
  }

  // {date, <key>: pct} rows from one dataset; each series is {key, ds, series, area, measure}.
  function wide(series) {
    const by = new Map();
    series.forEach((s) => {
      const D = dash.data(s.ds);
      if (D.status !== 'ok') return;
      D.data.forEach((r) => {
        if (r.series !== s.series || (r.area || 'national') !== (s.area || 'national') || r.measure !== (s.measure || 'yoy')) return;
        const v = num(r.value); if (v == null) return;
        if (!by.has(r.date)) by.set(r.date, { date: r.date });
        by.get(r.date)[s.key] = v;
      });
    });
    return Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
  }

  // Every month from the first to the last, so a month a series lacks is a gap, not a join.
  function fill(rows) {
    if (!rows.length) return rows;
    const by = new Map(rows.map((r) => [r.date, r])), out = [];
    for (let d = J.date(rows[0].date); d <= J.date(rows[rows.length - 1].date); d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1))) {
      const k = d.toISOString().slice(0, 10); out.push(by.get(k) || { date: k });
    }
    return out;
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
    const y0 = Number(rows[0].date.slice(0, 4)), y1 = Number(rows[rows.length - 1].date.slice(0, 4));
    const span = y1 - y0 + 1;
    const nMonths = (y1 - y0) * 12 + Number(rows[rows.length - 1].date.slice(5, 7)) - Number(rows[0].date.slice(5, 7)) + 1;
    if (span <= 2 && nMonths <= 24) {
      const room = Math.max(1, Math.floor((W - ml - mr) / 52));
      const mstep = [1, 2, 3, 6].find((s) => nMonths / s <= room) || 6;
      J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).ticks(d3.utcMonth.every(mstep)).tickSize(0).tickFormat(d3.utcFormat('%b %y'))));
    } else {
      const step = [1, 2, 5, 10, 20, 25, 50].find((s) => span / s <= nYears) || 50;
      J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).ticks(d3.utcYear.every(step)).tickSize(0).tickFormat(d3.utcFormat('%Y'))));
    }
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

  function status(box, ids) {
    const st = ids.map((i) => dash.data(i).status);
    if (st.some(failed)) { box.classList.remove('dash-skeleton'); J.fail(box); return false; }
    if (st.some((s) => s !== 'ok')) { box.replaceChildren(); box.classList.add('dash-skeleton'); return false; }
    box.classList.remove('dash-skeleton');
    return true;
  }

  // Base changes inside the window: dashed vertical lines.
  function baseLines(svg, x, rows, H, show) {
    if (!show) return;
    BASES.forEach((b) => {
      if (rows[0].date < b && rows[rows.length - 1].date >= b) {
        const sx = x(J.date(b));
        svg.append('line').attr('x1', sx).attr('x2', sx).attr('y1', 12).attr('y2', H - 24).attr('stroke', 'var(--ad-axis)').attr('stroke-dasharray', '3 3');
      }
    });
  }

  function lines(cardId, series, opt = {}) {
    const box = document.getElementById(cardId + '-chart');
    legend(cardId + '-legend', series);
    if (!status(box, Array.from(new Set(series.map((s) => s.ds))))) return;
    const all = fill(wide(series));
    const start = all.findIndex((r) => (opt.anyStart ? series.some((s) => r[s.key] != null) : series.every((s) => r[s.key] != null)));
    let end = all.length;
    while (end > 0 && series.every((s) => all[end - 1][s.key] == null)) end -= 1;
    const rows = start < 0 ? [] : win(all.slice(start, end), cardId);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = opt.H || 280, mr = 8;
    const { svg, x, y, W, ml } = frame(box, rows, H, rows.flatMap((r) => series.map((s) => r[s.key])).filter((v) => v != null), fmt0, true, mr);
    baseLines(svg, x, rows, H, opt.bases);
    series.forEach((s) => {
      svg.append('path').attr('d', d3.line().defined((r) => r[s.key] != null).x((r) => x(J.date(r.date))).y((r) => y(r[s.key]))(rows))
        .attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', s.thin ? 1.75 : 2.5).attr('stroke-linecap', s.dash ? 'butt' : 'round').attr('stroke-linejoin', 'round')
        .attr('stroke-dasharray', s.dash ? '6 4' : null);
    });
    const card = document.getElementById(cardId);
    const dots = series.map((s) => svg.append('circle').attr('r', 3.5).attr('fill', s.color).attr('display', 'none'));
    const extras = hover(svg, card, x, rows, H, ml, W - mr, (r, px) => {
      dots.forEach((d, i) => { const v = r[series[i].key]; d.attr('display', v == null ? 'none' : null).attr('cx', px).attr('cy', v == null ? 0 : y(v)); });
      return series.map((s) => [s.color, s.name, r[s.key] == null ? 'n/a' : r[s.key].toFixed(2) + '%']);
    });
    extras.push(...dots);
  }

  // CPI y/y (line) and m/m (bars).
  function ymChart() {
    const id = 'cpi-ym', box = document.getElementById(id + '-chart');
    const S = [{ key: 'yoy', name: 'CPI, y/y', color: 'var(--ad-c2)', ds: 'tw_cpi', series: 'all', measure: 'yoy' },
      { key: 'mom', name: 'CPI, m/m', color: 'var(--ad-c1)', ds: 'tw_cpi', series: 'all', measure: 'mom', bar: true }];
    legend(id + '-legend', S);
    if (!status(box, ['tw_cpi'])) return;
    const all = fill(wide(S));
    const start = all.findIndex((r) => r.yoy != null && r.mom != null);
    const rows = start < 0 ? [] : win(all.slice(start), id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280, mr = 8;
    const { svg, x, y, W, ml } = frame(box, rows, H, rows.flatMap((r) => [r.yoy, r.mom]).filter((v) => v != null), (v) => d3.format('.1~f')(v), true, mr);
    const step = (W - ml - mr) / Math.max(1, rows.length);
    const bw = Math.max(1, Math.min(14, step * 0.6));
    rows.forEach((r) => {
      if (r.mom == null) return;
      svg.append('rect').attr('x', x(J.date(r.date)) - bw / 2).attr('width', bw)
        .attr('y', y(Math.max(0, r.mom))).attr('height', Math.abs(y(r.mom) - y(0))).attr('fill', S[1].color);
    });
    svg.append('path').attr('d', d3.line().defined((r) => r.yoy != null).x((r) => x(J.date(r.date))).y((r) => y(r.yoy))(rows))
      .attr('fill', 'none').attr('stroke', S[0].color).attr('stroke-width', 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    const card = document.getElementById(id);
    const dot = svg.append('circle').attr('r', 3.5).attr('fill', S[0].color).attr('display', 'none');
    const extras = hover(svg, card, x, rows, H, ml, W - mr, (r, px) => {
      dot.attr('display', r.yoy == null ? 'none' : null).attr('cx', px).attr('cy', r.yoy == null ? 0 : y(r.yoy));
      return S.map((s) => [s.color, s.name, r[s.key] == null ? 'n/a' : r[s.key].toFixed(2) + '%']);
    });
    extras.push(dot);
  }

  // Horizontal bars of the latest month's y/y for a set of rows (provinces, industries).
  function hbars(cardId, ds, pick, nameOf, color, unitsId, what) {
    const box = document.getElementById(cardId + '-chart');
    if (!status(box, [ds])) return;
    const D = dash.data(ds).data.filter(pick);
    const last = D.reduce((m, r) => (r.date > m ? r.date : m), '');
    const rows = D.filter((r) => r.date === last && num(r.value) != null).map((r) => ({ name: nameOf(r), v: num(r.value) }))
      .sort((a, b) => b.v - a.v);
    document.getElementById(unitsId).textContent = `% y/y, ${mLabel(last)}${what ? ', ' + what : ''}`;
    if (!rows.length) { box.replaceChildren(); return; }
    const W = box.clientWidth, rh = 17, H = rows.length * rh + 28;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const lw = Math.min(W * 0.48, J.textWidth(svg, rows.map((r) => r.name)) + 10);
    const x = d3.scaleLinear([Math.min(0, d3.min(rows, (r) => r.v)), Math.max(0, d3.max(rows, (r) => r.v))], [lw, W - 34]).nice();
    const ticks = x.ticks(5);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', x).attr('x2', x).attr('y1', 4).attr('y2', H - 22)
      .attr('stroke', (v) => (v === 0 ? 'var(--cds-chart-reference)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 18})`).call(d3.axisBottom(x).tickValues(ticks).tickSize(0).tickFormat(fmt0)));
    const card = document.getElementById(cardId), tip = J.tip(card);
    rows.forEach((r, i) => {
      const yy = 6 + i * rh;
      svg.append('text').attr('x', lw - 6).attr('y', yy + rh / 2 + 1).attr('text-anchor', 'end').attr('dominant-baseline', 'middle')
        .attr('font-size', 11.5).attr('fill', 'var(--ad-ink)').text(r.name);
      const b = svg.append('rect').attr('x', x(Math.min(0, r.v))).attr('width', Math.max(1, Math.abs(x(r.v) - x(0))))
        .attr('y', yy + 2).attr('height', rh - 5).attr('fill', r.v < 0 ? 'var(--ad-c1)' : color);
      svg.append('text').attr('x', r.v < 0 ? x(r.v) - 3 : x(r.v) + 3).attr('y', yy + rh / 2 + 1).attr('dominant-baseline', 'middle')
        .attr('text-anchor', r.v < 0 ? 'end' : 'start').attr('font-size', 11).attr('fill', 'var(--ad-ink)').text(J.f1(r.v));
      b.on('mousemove', (ev) => { const cr = card.getBoundingClientRect(); J.showTip(card, tip, r.name, [[null, 'y/y', r.v.toFixed(2) + '%']], ev.clientX - cr.left, ev.clientY - cr.top); })
        .on('mouseleave', () => { tip.style.display = 'none'; });
    });
  }

  // Contributions to CPI y/y: DGBAS's published goods and services contributions (stacked, services at the
  // bottom) and CPI y/y (line). Legend: the line, then the parts from the top of the stack down.
  function contribChart() {
    const id = 'cpi-contrib', box = document.getElementById(id + '-chart');
    const PARTS = [{ key: 'services', name: 'Services', color: CC.services }, { key: 'goods', name: 'Goods', color: CC.goods }];
    const LINE = { key: 'cpi', name: 'CPI, y/y', color: CC.line };
    legend(id + '-legend', [LINE].concat(PARTS.slice().reverse().map((p) => Object.assign({ bar: true }, p))));
    if (!status(box, ['tw_cpi_contrib'])) return;
    const by = new Map();
    dash.data('tw_cpi_contrib').data.forEach((r) => {
      if (!by.has(r.date)) by.set(r.date, { date: r.date });
      const o = by.get(r.date);
      if (r.series === 'all') o.cpi = num(r.yoy);
      if (r.series === 'goods' || r.series === 'services') o[r.series] = num(r.yoy_pp);
    });
    const rows = win(fill(Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1))), id);
    if (!rows.length) { box.replaceChildren(); return; }
    rows.forEach((r) => {
      let pos = 0, neg = 0;
      r.stack = PARTS.map((p) => { const v = r[p.key] || 0; const y0 = v >= 0 ? pos : neg; if (v >= 0) pos += v; else neg += v; return { p, y0, y1: y0 + v }; });
      r.lo = neg; r.hi = pos;
    });
    const H = 280, mr = 8;
    const { svg, x, y, W, ml } = frame(box, rows, H, rows.flatMap((r) => [r.lo, r.hi, r.cpi]).filter((v) => v != null), (v) => d3.format('.1~f')(v), true, mr);
    const step = (W - ml - mr) / Math.max(1, rows.length);
    const bw = Math.max(1, Math.min(rows.length < 30 ? 30 : 14, step * 0.65));
    rows.forEach((r) => {
      const cx = x(J.date(r.date));
      r.stack.forEach((s) => {
        if (s.y1 === s.y0) return;
        svg.append('rect').attr('x', cx - bw / 2).attr('width', bw).attr('y', y(Math.max(s.y0, s.y1)))
          .attr('height', Math.abs(y(s.y0) - y(s.y1))).attr('fill', s.p.color);
      });
    });
    svg.append('path').attr('d', d3.line().defined((r) => r.cpi != null).x((r) => x(J.date(r.date))).y((r) => y(r.cpi))(rows))
      .attr('fill', 'none').attr('stroke', LINE.color).attr('stroke-width', 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    const card = document.getElementById(id);
    const dot = svg.append('circle').attr('r', 3.5).attr('fill', LINE.color).attr('display', 'none');
    const extras = hover(svg, card, x, rows, H, ml, W - mr, (r, px) => {
      dot.attr('display', r.cpi == null ? 'none' : null).attr('cx', px).attr('cy', r.cpi == null ? 0 : y(r.cpi));
      return [[LINE.color, 'CPI, y/y %', r.cpi == null ? 'n/a' : f2(r.cpi)]]
        .concat(PARTS.slice().reverse().map((p) => [p.color, p.name + ', ppt', r[p.key] == null ? 'n/a' : f2(r[p.key])]));
    });
    extras.push(dot);
  }

  // Seasonally adjusted m/m: CPI and core, grouped bars.
  function saChart() {
    const id = 'cpi-sa', box = document.getElementById(id + '-chart');
    const S = [{ key: 'cpi', name: 'CPI', color: 'var(--ad-c2)', ds: 'tw_cpi', series: 'all', measure: 'sa_mom', bar: true },
      { key: 'core', name: 'Core CPI', color: 'var(--ad-c6)', ds: 'tw_cpi', series: 'core', measure: 'sa_mom', bar: true }];
    legend(id + '-legend', S);
    if (!status(box, ['tw_cpi'])) return;
    const all = fill(wide(S));
    const start = all.findIndex((r) => r.cpi != null);
    const rows = start < 0 ? [] : win(all.slice(start), id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280, mr = 8;
    const { svg, x, y, W, ml } = frame(box, rows, H, rows.flatMap((r) => [r.cpi, r.core]).filter((v) => v != null), (v) => d3.format('.1~f')(v), true, mr);
    const step = (W - ml - mr) / Math.max(1, rows.length);
    const bw = Math.max(1, Math.min(8, step * 0.38));
    rows.forEach((r) => {
      S.forEach((s, i) => {
        const v = r[s.key]; if (v == null) return;
        svg.append('rect').attr('x', x(J.date(r.date)) - bw + i * bw).attr('width', bw)
          .attr('y', y(Math.max(0, v))).attr('height', Math.abs(y(v) - y(0))).attr('fill', s.color);
      });
    });
    const card = document.getElementById(id);
    hover(svg, card, x, rows, H, ml, W - mr, (r) => S.map((s) => [s.color, s.name + ', m/m SA', r[s.key] == null ? 'n/a' : f2(r[s.key]) + '%']));
  }

  function takeaway() {
    const p = document.getElementById('cpi-takeaway');
    const L = dash.data('cpi_latest'), P = dash.data('ppi_latest');
    if (L.status !== 'ok' || !L.data.length) { if (failed(L.status)) p.replaceChildren(); return; }
    const a = L.data[0];
    const mk = (src, field, v) => { const b = document.createElement('b'); b.dataset.source = src; b.dataset.field = field; b.dataset.row = '0'; b.textContent = f2(v) + '%'; return b; };
    const t = (x) => p.append(document.createTextNode(x));
    p.replaceChildren();
    t(`In ${mLabel(a.date)}, consumer prices were `); p.append(mk('cpi_latest', 'all_yoy', a.all_yoy));
    t(' higher than a year earlier, against '); p.append(mk('cpi_latest', 'all_yoy_prev', a.all_yoy_prev));
    t(` in ${mLabel(a.prev_date)}. Core CPI (excluding fruit, vegetables and energy) rose `); p.append(mk('cpi_latest', 'core_yoy', a.core_yoy));
    t('; seasonally adjusted, the CPI changed by '); p.append(mk('cpi_latest', 'all_sa_mom', a.all_sa_mom)); t(' on the month.');
    if (P.status === 'ok' && P.data.length && P.data[0].ppi_yoy != null) {
      t(' Producer prices were '); p.append(mk('ppi_latest', 'ppi_yoy', P.data[0].ppi_yoy)); t(' higher than a year earlier.');
    }
  }

  function tiles() {
    const hm = document.getElementById('cpi-month');
    document.querySelectorAll('#cpi-headline [data-source], #cpi-month').forEach((el) => {
      const L = dash.data(el.dataset.source);
      if (L.status !== 'ok' || !L.data.length) { el.textContent = '—'; return; }
      el.classList.remove('dash-skeleton');
      const v = L.data[0][el.dataset.field];
      el.textContent = el === hm ? (v || '') : f2(v);
    });
  }

  let impM = 'yoy';
  function impactsTable() {
    const tb = document.querySelector('#cpi-impacts-table tbody');
    const M = dash.data('impacts_latest');
    if (failed(M.status)) { tb.replaceChildren(); const td = tb.insertRow().insertCell(); td.colSpan = 4; J.fail(td); return; }
    if (M.status !== 'ok') return;
    const rows = M.data.filter((r) => r.measure === impM).sort((a, b) => a.order - b.order);
    const date = M.data.length ? M.data[0].date : null;
    document.getElementById('cpi-impacts-units').textContent = date ? `%, ppt, ${mLabel(date)}, ${impM === 'yoy' ? 'year on year' : 'month on month'}` : '%, ppt';
    tb.replaceChildren();
    rows.forEach((r) => {
      const tr = tb.insertRow(); tr.dataset.key = r.series;
      if (r.series === 'all') tr.className = 'gdp';
      if (r.series === 'goods') tr.className = 'sep';
      [r.label, J.f1(r.weight_pct), f2(r.rate), f2(r.pp)].forEach((v, i) => {
        const td = tr.insertCell(); td.textContent = v;
        if ((i === 2 && r.rate < 0) || (i === 3 && r.pp < 0)) td.classList.add('neg');
      });
    });
  }
  const iseg = document.getElementById('cpi-impacts-seg');
  iseg.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    impM = b.dataset.m;
    iseg.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    impactsTable();
  });

  // Heat table: published y/y for the latest 13 months, each row on its own colour range; DGBAS weights.
  const HEAT = [
    ['all', 'CPI', 'lead'], ['core1', 'Core 1 (ex food and non-alcoholic beverages and energy; calculated)', 'lead'], ['core', 'Core CPI (ex fruit, vegetables and energy)', 'lead'], ['ex_food_energy', 'CPI ex food and energy (DGBAS definition)', ''],
    ['goods', 'Goods', ''], ['core_goods', 'Core goods', 'sub'], ['services', 'Services', ''], ['energy', 'Energy', ''],
    ['food', 'Food', 'cat'], ['cereals', 'Cereals and products', 'sub'], ['meat', 'Meat', 'sub'], ['vegetables', 'Vegetables', 'sub'],
    ['fruit', 'Fruits', 'sub'], ['eating_out', 'Food away from home', 'sub'],
    ['clothing', 'Clothing', 'cat'], ['housing', 'Housing', 'cat'], ['rent', 'Residential rents', 'sub'], ['electricity', 'Electricity', 'sub'],
    ['transport_comm', 'Transportation and communication', 'cat'], ['fuels', 'Fuels and lubricants', 'sub'], ['transport_fees', 'Transportation fees', 'sub'],
    ['health', 'Health', 'cat'], ['medical_services', 'Medical care services', 'sub'],
    ['education_entertainment', 'Education and entertainment', 'cat'], ['miscellaneous', 'Miscellaneous', 'cat'],
  ];
  // Contribution-table keys whose names differ from the CPI series keys.
  const WKEY = { eating_out: 'services_eating_out' };
  function divHeat() {
    const tbl = document.getElementById('div-heat-table');
    const D = dash.data('tw_cpi'), Wt = dash.data('tw_cpi_contrib');
    if (failed(D.status)) { tbl.replaceChildren(); return; }
    if (D.status !== 'ok') return;
    const wrows = Wt.status === 'ok' ? Wt.data : [];
    const wlast = wrows.reduce((m, r) => (r.date > m ? r.date : m), '');
    const wt = new Map(wrows.filter((r) => r.date === wlast).map((r) => [r.series, num(r.weight_pct)]));
    document.getElementById('div-heat-units').textContent = `% y/y; weight, % of CPI${wlast ? ' (' + wlast.slice(0, 4) + ')' : ''}`;
    const rows = D.data.filter((r) => r.area === 'national' && r.measure === 'yoy');
    const dates = Array.from(new Set(rows.filter((r) => r.series === 'all').map((r) => r.date))).sort().slice(-13);
    const val = new Map(rows.filter((r) => dates.includes(r.date)).map((r) => [`${r.series}|${r.date}`, num(r.value)]));
    const STOPS = [[0, [99, 190, 123]], [0.5, [255, 235, 132]], [1, [248, 105, 107]]];
    const color = (t) => {
      const i = t > 0.5 ? 1 : 0; const [t0, c0] = STOPS[i], [t1, c1] = STOPS[i + 1], f = (t - t0) / (t1 - t0);
      return `rgb(${c0.map((c, k) => Math.round(c + (c1[k] - c) * f)).join(',')})`;
    };
    tbl.replaceChildren();
    const head = tbl.createTHead().insertRow();
    ['', 'Weight'].concat(dates.map((d) => `${MON[+d.slice(5, 7) - 1]} ${d.slice(2, 4)}`)).forEach((t) => {
      const th = document.createElement('th'); th.textContent = t; head.appendChild(th);
    });
    const tb = tbl.createTBody();
    HEAT.forEach(([key, name, cls]) => {
      const vs = dates.map((d) => val.get(`${key}|${d}`)).filter((v) => v != null);
      if (!vs.length) return;
      const tr = tb.insertRow(); tr.className = cls === 'lead' ? 'lead' : (cls === 'sub' ? 'sub' : '');
      const c0 = tr.insertCell(); c0.textContent = name; if (cls === 'sub') c0.style.paddingLeft = '1.1rem';
      const cw = tr.insertCell(); cw.className = 'wt'; const w = wt.get(WKEY[key] || key); cw.textContent = w == null ? '' : J.f1(w);
      const lo = Math.min(...vs), hi = Math.max(...vs);
      dates.forEach((d) => {
        const td = tr.insertCell(); const v = val.get(`${key}|${d}`);
        if (v == null) return;
        td.textContent = J.f1(v) === '-0.0' ? '0.0' : J.f1(v);
        td.className = 'heat'; td.style.background = color(hi > lo ? (v - lo) / (hi - lo) : 0.5); td.style.color = '#1a1a1a';
      });
    });
  }

  J.redrawCpi = () => {
    if (!visible()) return;
    const C = (series, key, name, color, extra) => Object.assign({ ds: 'tw_cpi', series, key, name, color, measure: 'yoy', area: 'national' }, extra || {});
    const P = (series, key, name, color, extra) => Object.assign({ ds: 'tw_ppi', series, key, name, color, measure: 'yoy' }, extra || {});
    lines('ppi-cpi', [P('ppi_all', 'ppi', 'PPI', 'var(--ad-c1)'), C('all', 'cpi', 'CPI', 'var(--ad-c2)')], { anyStart: true });
    ymChart();
    saChart();
    contribChart();
    lines('cpi-core', [C('all', 'cpi', 'CPI', 'var(--ad-c2)'), C('core1', 'core1', 'Core 1 (calculated)', 'var(--ad-c1)'),
      C('core', 'core', 'Core CPI (ex fruit, vegetables and energy)', 'var(--ad-c6)'),
      C('ex_food_energy', 'xfe', 'CPI ex food and energy (DGBAS)', 'var(--ad-c8)', { dash: true })], { anyStart: true });
    lines('cpi-gs', [C('goods', 'goods', 'Goods', 'var(--ad-c1)'), C('services', 'services', 'Services', 'var(--ad-c2)'),
      C('core_goods', 'cg', 'Core goods', 'var(--ad-c6)', { thin: true })], { anyStart: true });
    lines('cpi-fe', [C('food', 'food', 'Food', 'var(--ad-c5)'),
      C('food01', 'f01', 'Food and non-alcoholic beverages (calculated)', 'var(--ad-c3)', { dash: true }),
      C('vegetables', 'veg', 'Vegetables', 'var(--ad-c6)', { thin: true }),
      C('fruit', 'fruit', 'Fruits', 'var(--ad-c7)', { thin: true }), C('energy', 'energy', 'Energy', 'var(--ad-c1)'),
      C('fuels', 'fuel', 'Fuels and lubricants', 'var(--ad-c8)', { dash: true })], { anyStart: true });
    lines('cpi-income', [C('all', 'cpi', 'All households', 'var(--ad-c2)'),
      C('all', 'low', 'Lowest 20%', 'var(--ad-c5)', { area: 'lowest20' }), C('all', 'mid', 'Middle 60%', 'var(--ad-c6)', { area: 'middle60', thin: true }),
      C('all', 'high', 'Highest 20%', 'var(--ad-c1)', { area: 'highest20' }), C('all', 'old', 'Elderly households', 'var(--ad-c8)', { area: 'elderly', dash: true })], { anyStart: true });
    lines('trade', [P('ipi_usd_all', 'ipi', 'Import prices (USD)', 'var(--ad-c1)'), P('epi_usd_all', 'epi', 'Export prices (USD)', 'var(--ad-c2)')]);
    lines('ppi-parts', [P('ppi_all', 'ppi', 'PPI', 'var(--ad-c1)'), P('ppi_agriculture', 'agri', 'Agriculture', 'var(--ad-c5)', { thin: true }),
      P('ppi_mining', 'min', 'Mining', 'var(--ad-c7)', { thin: true }), P('ppi_manufacturing', 'man', 'Manufacturing', 'var(--ad-c3)'),
      P('ppi_utilities', 'util', 'Water, electricity and gas', 'var(--ad-c8)', { dash: true })], { anyStart: true });
    lines('cpi-cats', [
      C('food', 'f', 'Food', 'var(--ad-c5)'), C('clothing', 'c', 'Clothing', 'var(--ad-c7)', { thin: true }), C('housing', 'h', 'Housing', 'var(--ad-c8)'),
      C('transport_comm', 't', 'Transport and communication', 'var(--ad-c1)'), C('health', 'm', 'Health', 'var(--ad-c3)', { thin: true }),
      C('education_entertainment', 'e', 'Education and entertainment', 'var(--ad-c6)'), C('miscellaneous', 'o', 'Miscellaneous', 'var(--ad-c2)', { thin: true }),
    ], { anyStart: true, bases: true });
    const DIV = ['food', 'beverages', 'tobacco', 'textiles', 'apparel', 'leather', 'wood', 'paper', 'petroleum', 'chemicals', 'rubber_plastic',
      'non_metallic', 'basic_metals', 'fabricated_metal', 'electronic_parts', 'computers', 'electrical', 'machinery', 'transport_equipment',
      'furniture', 'misc_manufacturing', 'agriculture', 'mining', 'utilities'].map((k) => 'ppi_' + k);
    const NAMES = { ppi_food: 'Food and feeds', ppi_beverages: 'Beverages', ppi_tobacco: 'Tobacco', ppi_textiles: 'Textiles', ppi_apparel: 'Apparel',
      ppi_leather: 'Leather', ppi_wood: 'Wood and bamboo', ppi_paper: 'Paper and printing', ppi_petroleum: 'Petroleum and coal', ppi_chemicals: 'Chemicals and medicines',
      ppi_rubber_plastic: 'Rubber and plastics', ppi_non_metallic: 'Non-metallic minerals', ppi_basic_metals: 'Basic metals', ppi_fabricated_metal: 'Fabricated metals',
      ppi_electronic_parts: 'Electronic parts', ppi_computers: 'Computers, electronics, optical', ppi_electrical: 'Electrical equipment', ppi_machinery: 'Machinery',
      ppi_transport_equipment: 'Transport equipment', ppi_furniture: 'Furniture', ppi_misc_manufacturing: 'Other manufacturing', ppi_agriculture: 'Agriculture (section)',
      ppi_mining: 'Mining (section)', ppi_utilities: 'Water, electricity, gas (section)' };
    hbars('ppi-ind', 'tw_ppi', (r) => DIV.includes(r.series) && r.measure === 'yoy', (r) => NAMES[r.series] || r.series, 'var(--ad-c3)', 'ppi-ind-units');
  };

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

  dash.onData(() => { tiles(); takeaway(); impactsTable(); divHeat(); J.redrawCpi(); });
})();
