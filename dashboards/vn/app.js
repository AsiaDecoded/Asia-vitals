// Vietnam dashboard: CPI, core inflation, producer and trade prices as published by NSO (and the IMF's
// headline series, labelled). Nothing here calculates a figure: the calcs below only pick rows and reshape them.

dash.calc('cpi_month', {
  title: 'Latest month',
  description: 'The month of the latest NSO CPI release, as a label.',
  inputs: ['vn_cpi_latest'],
  fn: (vn_cpi_latest) => {
    const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    const d = vn_cpi_latest.length ? String(vn_cpi_latest[0].date) : '';
    return d ? [{ date: d, month: `${MONTHS[Number(d.slice(5, 7)) - 1]} ${d.slice(0, 4)}` }] : [];
  },
});

dash.calc('ppi_latest', {
  title: 'Latest industry PPI',
  description: 'NSO industry PPI y/y (same quarter last year = 100, less 100) in the latest quarter and the one before.',
  inputs: ['vn_ppi'],
  fn: (vn_ppi) => {
    const s = vn_ppi.filter((r) => r.series === 'ppi_industry' && r.measure === 'yoy' && r.value !== '').sort((a, b) => (a.date < b.date ? -1 : 1));
    if (!s.length) return [];
    const a = s[s.length - 1], b = s.length > 1 ? s[s.length - 2] : null;
    return [{ period: a.period.replace('-', ' '), date: a.date, ind_yoy: Number(a.value), ind_yoy_prev: b ? Number(b.value) : null }];
  },
});

dash.calc('weights_wide', {
  title: 'Weights by basket',
  description: 'NSO published CPI weights (% of CPI) for the 2014 and 2024 baskets, side by side.',
  inputs: ['vn_cpi_weights'],
  fn: (vn_cpi_weights) => {
    const by = new Map();
    vn_cpi_weights.forEach((r) => {
      if (!by.has(r.series)) by.set(r.series, { series: r.series, label: r.label, w2014: null, w2024: null });
      by.get(r.series)['w' + r.basket] = Number(r.weight_pct);
    });
    return Array.from(by.values());
  },
});

(() => {
  const J = window.JG;
  J.theme();
  document.querySelectorAll('#inflation .jg-card').forEach((c) => {
    if (c.id && c.querySelector('.jg-chart') && c.dataset.periods !== 'none') J.period[c.id] = c.dataset.def != null ? Number(c.dataset.def) : 120;
  });
  J.addPeriods();
  J.addSliders(() => { J.redrawCpi(); if (J.redrawGdp) J.redrawGdp(); });
  dash.onData(() => J.theme());

  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const qLab = (d) => `Q${Math.ceil(+d.slice(5, 7) / 3)} ${d.slice(0, 4)}`;
  const mLabel = (d) => (d ? MON[+d.slice(5, 7) - 1] + ' ' + d.slice(0, 4) : '');
  const failed = (st) => st === 'error' || st === 'connect' || st === 'declined';
  const visible = () => !document.getElementById('inflation').hidden;
  const f1 = (v) => (v == null ? '—' : J.f1(v));
  const f2 = (v) => (v == null ? '—' : v.toFixed(2));
  const num = (v) => (v === '' || v == null ? null : Number(v));
  const win = (rows, id) => J.slice(J.window(rows, id), id);
  const fmt0 = (v) => d3.format('.0f')(v);
  const BASES = ['2020-01-01', '2025-11-01'];
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
        J.showTip(card, tip, r.q ? qLab(r.date) : mLabel(r.date), onMove(r, px, extras), ev.clientX - cr.left, ev.clientY - cr.top);
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
    const all = opt.noFill ? wide(series).map((r) => Object.assign(r, { q: true })) : fill(wide(series));
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
    const S = [{ key: 'yoy', name: 'CPI, y/y', color: 'var(--ad-c2)', ds: 'vn_cpi', series: 'all', measure: 'yoy' },
      { key: 'mom', name: 'CPI, m/m', color: 'var(--ad-c1)', ds: 'vn_cpi', series: 'all', measure: 'mom', bar: true }];
    legend(id + '-legend', S);
    if (!status(box, ['vn_cpi'])) return;
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
  function hbars(cardId, ds, pick, nameOf, color, unitsId, what, valOf, unitWord) {
    const box = document.getElementById(cardId + '-chart');
    if (!status(box, [ds])) return;
    const D = dash.data(ds).data.filter(pick);
    const last = D.reduce((m, r) => (r.date > m ? r.date : m), '');
    const rows = D.filter((r) => r.date === last && (valOf ? valOf(r) : num(r.value)) != null).map((r) => ({ name: nameOf(r), v: valOf ? valOf(r) : num(r.value) }))
      .sort((a, b) => b.v - a.v);
    document.getElementById(unitsId).textContent = `% ${unitWord || 'y/y'}, ${mLabel(last)}${what ? ', ' + what : ''}`;
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
      b.on('mousemove', (ev) => { const cr = card.getBoundingClientRect(); J.showTip(card, tip, r.name, [[null, unitWord || 'y/y', r.v.toFixed(2) + '%']], ev.clientX - cr.left, ev.clientY - cr.top); })
        .on('mouseleave', () => { tip.style.display = 'none'; });
    });
  }

  function takeaway() {
    const p = document.getElementById('cpi-takeaway');
    const L = dash.data('vn_cpi_latest'), P = dash.data('ppi_latest');
    if (L.status !== 'ok' || !L.data.length) { if (failed(L.status)) p.replaceChildren(); return; }
    const a = L.data[0];
    const mk = (src, field, v) => { const b = document.createElement('b'); b.dataset.source = src; b.dataset.field = field; b.dataset.row = '0'; b.textContent = f2(num(v)) + '%'; return b; };
    const t = (x) => p.append(document.createTextNode(x));
    const prev = (() => { const y = +a.date.slice(0, 4), m = +a.date.slice(5, 7); return m === 1 ? `${y - 1}-12-01` : `${y}-${String(m - 1).padStart(2, '0')}-01`; })();
    p.replaceChildren();
    t(`In ${mLabel(a.date)}, consumer prices were `); p.append(mk('vn_cpi_latest', 'all_yoy', a.all_yoy));
    t(' higher than a year earlier, against '); p.append(mk('vn_cpi_latest', 'all_yoy_prev', a.all_yoy_prev));
    t(` in ${mLabel(prev)}, and changed by `); p.append(mk('vn_cpi_latest', 'all_mom', a.all_mom));
    t(' on the month. NSO core inflation was '); p.append(mk('vn_cpi_latest', 'core_yoy', a.core_yoy)); t('.');
    if (P.status === 'ok' && P.data.length && P.data[0].ind_yoy != null) {
      t(` Industrial producer prices were `); p.append(mk('ppi_latest', 'ind_yoy', P.data[0].ind_yoy)); t(` higher than a year earlier in ${P.data[0].period}.`);
    }
  }

  function tiles() {
    const hm = document.getElementById('cpi-month');
    document.querySelectorAll('#cpi-headline [data-source], #cpi-month').forEach((el) => {
      const L = dash.data(el.dataset.source);
      if (L.status !== 'ok' || !L.data.length) { el.textContent = '—'; return; }
      el.classList.remove('dash-skeleton');
      const v = L.data[0][el.dataset.field];
      el.textContent = el === hm || el.dataset.field === 'period' ? (v || '') : f2(num(v));
    });
  }

  // Heat table: published y/y for the latest 13 months, each row on its own colour range; NSO 2024 weights.
  const HEAT = [
    ['all', 'CPI', 'lead'], ['core', 'Core inflation (NSO)', 'lead'],
    ['food_catering', 'Food and catering services', 'cat'], ['cereals', 'Cereals', 'sub'], ['foodstuff', 'Foodstuff', 'sub'], ['eating_out', 'Eating out', 'sub'],
    ['beverages_tobacco', 'Beverages and tobacco', 'cat'], ['clothing', 'Garments, hats, footwear', 'cat'],
    ['housing', 'Housing, electricity, water, fuel, construction materials', 'cat'], ['household', 'Household equipment and goods', 'cat'],
    ['health', 'Medicine and health care', 'cat'], ['health_services', 'Health care services', 'sub'], ['transport', 'Transport', 'cat'],
    ['communication', 'Information and communication', 'cat'], ['education', 'Education', 'cat'], ['education_services', 'Education services', 'sub'],
    ['culture', 'Culture, entertainment and tourism', 'cat'], ['other', 'Other goods and services', 'cat'],
  ];
  function divHeat() {
    const tbl = document.getElementById('div-heat-table');
    const D = dash.data('vn_cpi'), Wt = dash.data('vn_cpi_weights');
    if (failed(D.status)) { tbl.replaceChildren(); return; }
    if (D.status !== 'ok') return;
    const wt = new Map((Wt.status === 'ok' ? Wt.data : []).filter((r) => String(r.basket) === '2024').map((r) => [r.series, num(r.weight_pct)]));
    document.getElementById('div-heat-units').textContent = '% y/y; weight, % of CPI (2024 basket)';
    const rows = D.data.filter((r) => r.area === 'national' && r.measure === 'yoy' && r.source !== 'imf');
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
      const cw = tr.insertCell(); cw.className = 'wt'; const w = wt.get(key); cw.textContent = w == null ? '' : J.f1(w);
      const lo = Math.min(...vs), hi = Math.max(...vs);
      dates.forEach((d) => {
        const td = tr.insertCell(); const v = val.get(`${key}|${d}`);
        if (v == null) return;
        td.textContent = J.f1(v) === '-0.0' ? '0.0' : J.f1(v);
        td.className = 'heat'; td.style.background = color(hi > lo ? (v - lo) / (hi - lo) : 0.5); td.style.color = '#1a1a1a';
      });
    });
  }

  function weightsTable() {
    const tb = document.querySelector('#weights-table tbody');
    const M = dash.data('weights_wide');
    if (failed(M.status)) { tb.replaceChildren(); const td = tb.insertRow().insertCell(); td.colSpan = 3; J.fail(td); return; }
    if (M.status !== 'ok') return;
    tb.replaceChildren();
    const SUB = ['cereals', 'foodstuff', 'eating_out', 'health_services', 'education_services'];
    M.data.forEach((r) => {
      const tr = tb.insertRow(); tr.dataset.key = r.series;
      [r.label, r.w2014 == null ? '' : r.w2014.toFixed(2), r.w2024 == null ? '' : r.w2024.toFixed(2)].forEach((v, i) => {
        const td = tr.insertCell(); td.textContent = v; if (i === 0 && SUB.includes(r.series)) td.style.paddingLeft = '1.1rem';
      });
    });
  }

  J.redrawCpi = () => {
    if (!visible()) return;
    const C = (series, key, name, color, extra) => Object.assign({ ds: 'vn_cpi', series, key, name, color, measure: 'yoy', area: 'national' }, extra || {});
    const P = (series, key, name, color, extra) => Object.assign({ ds: 'vn_ppi', series, key, name, color, measure: 'yoy' }, extra || {});
    lines('cpi-long', [C('all', 'cpi', 'CPI, NSO', 'var(--ad-c2)'), C('imf_all', 'imf', 'CPI, IMF CPI dataset', 'var(--ad-c8)', { dash: true, thin: true })], { anyStart: true });
    ymChart();
    lines('cpi-bases', [C('all', 'yoy', 'Same month a year earlier', 'var(--ad-c2)'), C('all', 'dec', 'December of the previous year', 'var(--ad-c6)', { measure: 'vs_dec' }),
      C('all', 'ytd', 'Year-to-date average, y/y', 'var(--ad-c5)', { measure: 'ytd_avg', dash: true })], { anyStart: true });
    lines('cpi-core', [C('all', 'cpi', 'CPI', 'var(--ad-c2)'), C('core', 'core', 'Core inflation (NSO definition)', 'var(--ad-c6)')]);
    lines('cpi-ur', [C('all', 'urban', 'Urban', 'var(--ad-c2)', { area: 'urban' }), C('all', 'rural', 'Rural', 'var(--ad-c5)', { area: 'rural' })]);
    lines('cpi-fe', [C('food_catering', 'f', 'Food and catering services', 'var(--ad-c5)'), C('cereals', 'c', 'Cereals', 'var(--ad-c7)', { thin: true }),
      C('foodstuff', 's', 'Foodstuff', 'var(--ad-c1)', { thin: true }), C('eating_out', 'e', 'Eating out', 'var(--ad-c8)', { dash: true })], { anyStart: true });
    lines('ppi-parts', [P('ppi_industry', 'ind', 'Industry', 'var(--ad-c1)'), P('ppi_agriculture', 'agri', 'Agriculture, forestry and fishing', 'var(--ad-c5)'),
      P('ppi_services', 'svc', 'Services', 'var(--ad-c2)'), P('input_all', 'inp', 'Input prices for production', 'var(--ad-c8)', { dash: true })], { anyStart: true, noFill: true });
    lines('trade', [P('import_all', 'imp', 'Import prices (USD)', 'var(--ad-c1)'), P('export_all', 'exp', 'Export prices (USD)', 'var(--ad-c2)'),
      P('tot_all', 'tot', 'Terms of trade', 'var(--ad-c8)', { dash: true, thin: true })], { anyStart: true, noFill: true });
    lines('cpi-cats', [
      C('food_catering', 'f', 'Food and catering', 'var(--ad-c5)'), C('housing', 'h', 'Housing and utilities', 'var(--ad-c8)'), C('transport', 't', 'Transport', 'var(--ad-c1)'),
      C('health', 'm', 'Health', 'var(--ad-c3)', { thin: true }), C('education', 'e', 'Education', 'var(--ad-c6)'), C('clothing', 'c', 'Garments', 'var(--ad-c7)', { thin: true }),
      C('communication', 'i', 'Information and communication', 'var(--ad-c2)', { thin: true }),
    ], { anyStart: true, bases: true });
    lines('gold-usd', [C('gold', 'gold', 'Gold price index', 'var(--ad-c3)'), C('usd', 'usd', 'US dollar price index', 'var(--ad-c2)')], { anyStart: true });
    const mom = (r) => num(r.mom);
    hbars('region', 'vn_cpi_regions', (r) => r.kind === 'region' && r.series === 'all', (r) => r.name, 'var(--ad-c2)', 'region-units', 'all items', mom, 'm/m');
    hbars('province', 'vn_cpi_regions', (r) => r.kind === 'province' && r.series === 'all', (r) => r.name, 'var(--ad-c2)', 'province-units', 'all items', mom, 'm/m');
  };

  // Shared with gdp.js (GDP tab): drawing helpers only.
  J.vn = { legend, frame, hover, status, failed, fill, win, qLab, f2, num, fmt0 };

  const tabs = document.querySelectorAll('.jg-tabs [data-tab]');
  const show = (id) => {
    if (!document.getElementById(id)) return;
    tabs.forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === id)));
    document.querySelectorAll('.jg-page').forEach((pg) => { pg.hidden = pg.id !== id; });
    dash.setLink(id);
    if (id === 'inflation') J.redrawCpi();
    if ((id === 'gdp' || id === 'manufacturing') && J.redrawGdp) J.redrawGdp();
  };
  J.show = show;
  tabs.forEach((b) => b.addEventListener('click', () => show(b.dataset.tab)));
  if (['manufacturing', 'methodology', 'inflation'].includes(location.hash.slice(1))) show(location.hash.slice(1));

  dash.onData(() => { tiles(); takeaway(); divHeat(); weightsTable(); J.redrawCpi(); });
})();
