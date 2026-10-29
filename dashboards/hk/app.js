// Hong Kong dashboard: CPI, producer and trade prices as published by C&SD.
// Nothing here calculates a figure: the code only picks published rows and reshapes them for the charts.

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
  const qLabel = (d) => `Q${Math.floor((+d.slice(5, 7) - 1) / 3) + 1} ${d.slice(0, 4)}`;
  const failed = (st) => st === 'error' || st === 'connect' || st === 'declined';
  const visible = () => !document.getElementById('inflation').hidden;
  const num = (v) => (v === '' || v == null ? null : Number(v));
  const f1 = (v) => (v == null ? '—' : J.f1(v));
  const pct = (v) => (v == null ? 'n/a' : (J.f1(v) === '-0.0' ? '0.0' : J.f1(v)) + '%');
  const win = (rows, id) => J.slice(J.window(rows, id), id);
  const fmt0 = (v) => d3.format('.0f')(v);
  const fmt1 = (v) => d3.format('.1~f')(v);
  const addM = (d, k) => { const t = J.date(d); return new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth() + k, 1)).toISOString().slice(0, 10); };

  // Contribution colours: the standing scheme from the Singapore pages (line red; services yellow at the bottom,
  // retail and other goods mid-dark blue, food and beverage serving services green, then the measure's own parts).
  const CC = { line: '#BD1B21', services: '#FFC000', goods: '#1F4E79', fbss: '#92D050', grey: '#A6A6A6', bright: '#0C84FF' };

  // Published rows of one dataset, indexed once per load.
  const cache = new Map();
  function rowsOf(ds) {
    const D = dash.data(ds);
    if (D.status !== 'ok') return null;
    let c = cache.get(ds);
    if (c && c.src === D.data) return c;
    c = { src: D.data, by: new Map() };
    D.data.forEach((r) => {
      const k = ds === 'hk_cpi' ? `${r.index_type}|${r.basis}|${r.series}` : ds === 'hk_cpi_sa' ? `${r.index_type}|${r.basis}|${r.series}|${r.measure}`
        : ds === 'hk_ppi' ? r.series : r.series;
      if (!c.by.has(k)) c.by.set(k, []);
      c.by.get(k).push(r);
    });
    cache.set(ds, c);
    return c;
  }
  // A series spec: {key, name, color, ds, it, basis, series, measure ('yoy' | 'mom' | 'index' | SA measure), shift (months)}
  function pts(s) {
    const c = rowsOf(s.ds); if (!c) return [];
    const k = s.ds === 'hk_cpi' ? `${s.it || 'composite'}|${s.basis || 'headline'}|${s.series}`
      : s.ds === 'hk_cpi_sa' ? `${s.it || 'composite'}|${s.basis || 'headline'}|${s.series}|${s.measure}` : s.series;
    const col = s.ds === 'hk_cpi_sa' ? 'value' : (s.measure || 'yoy');
    return (c.by.get(k) || []).map((r) => ({ date: s.shift ? addM(r.date, s.shift) : r.date, v: num(r[col]) })).filter((p) => p.v != null);
  }
  function wide(series) {
    const by = new Map();
    series.forEach((s) => pts(s).forEach((p) => {
      if (!by.has(p.date)) by.set(p.date, { date: p.date });
      by.get(p.date)[s.key] = p.v;
    }));
    return Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
  }
  function fill(rows) {
    if (!rows.length) return rows;
    const by = new Map(rows.map((r) => [r.date, r])), out = [];
    for (let d = J.date(rows[0].date); d <= J.date(rows[rows.length - 1].date); d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1))) {
      const k = d.toISOString().slice(0, 10); out.push(by.get(k) || { date: k });
    }
    return out;
  }

  function legend(id, series) {
    const el = document.getElementById(id);
    if (!el) return;
    el.replaceChildren();
    series.forEach((s) => {
      const span = document.createElement('span'); const ln = document.createElement('span');
      ln.className = s.bar ? 'sw' : 'ln';
      if (s.dash) ln.style.background = `repeating-linear-gradient(90deg, ${s.color} 0 5px, transparent 5px 8px)`; else ln.style.background = s.color;
      span.append(ln, document.createTextNode(s.name)); el.appendChild(span);
    });
  }

  function frame(box, rows, H, vals, fmt, zero, mr) {
    const W = box.clientWidth;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    let lo = d3.min(vals), hi = d3.max(vals);
    if (zero) { lo = Math.min(0, lo); hi = Math.max(0, hi); }
    if (lo === hi) { lo -= 1; hi += 1; }
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
    if (span <= 3 && nMonths <= 40) {
      const room = Math.max(1, Math.floor((W - ml - mr) / 52));
      const mstep = [1, 2, 3, 6, 12].find((s) => nMonths / s <= room) || 12;
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

  function hover(svg, card, x, rows, H, ml, right, onMove, title) {
    const tip = J.tip(card);
    const rule = svg.append('line').attr('y1', 8).attr('y2', H - 22).attr('stroke', 'var(--cds-chart-reference)').attr('display', 'none');
    const bis = d3.bisector((r) => J.date(r.date)).center;
    const extras = [];
    svg.append('rect').attr('x', ml).attr('width', Math.max(0, right - ml)).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [mx] = d3.pointer(ev);
        const i = bis(rows, x.invert(mx)), r = rows[i];
        const px = x(J.date(r.date));
        rule.attr('display', null).attr('x1', px).attr('x2', px);
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, (title || mLabel)(r.date), onMove(r, px, i), ev.clientX - cr.left, ev.clientY - cr.top);
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

  // Lines over months. A series with sparse: true (quarterly) is joined across the months it has no figure for.
  function lines(cardId, seriesIn, opt = {}) {
    // opt.sparse: every series is quarterly (dated by the quarter's first month, plotted at its middle month)
    const series = opt.sparse ? seriesIn.map((s) => Object.assign({ sparse: true, shift: 1 }, s)) : seriesIn;
    const box = document.getElementById(cardId + '-chart');
    legend(cardId + '-legend', series);
    if (!status(box, Array.from(new Set(series.map((s) => s.ds))))) return;
    const all = fill(wide(series));
    const lead0 = series.filter((s) => !s.sparse && !s.late), lead = lead0.length ? lead0 : series;
    const start = all.findIndex((r) => (opt.anyStart ? series.some((s) => r[s.key] != null) : lead.every((s) => r[s.key] != null)));
    let end = all.length;
    while (end > 0 && series.every((s) => all[end - 1][s.key] == null)) end -= 1;
    const rows = start < 0 ? [] : win(all.slice(start, end), cardId);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = opt.H || 280, mr = 8;
    const { svg, x, y, W, ml } = frame(box, rows, H, rows.flatMap((r) => series.map((s) => r[s.key])).filter((v) => v != null), opt.fmt || fmt0, true, mr);
    series.forEach((s) => {
      const data = s.sparse ? rows.filter((r) => r[s.key] != null) : rows;
      svg.append('path').attr('d', d3.line().defined((r) => r[s.key] != null).x((r) => x(J.date(r.date))).y((r) => y(r[s.key]))(data))
        .attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', s.thin ? 1.75 : 2.5).attr('stroke-linecap', s.dash ? 'butt' : 'round').attr('stroke-linejoin', 'round')
        .attr('stroke-dasharray', s.dash ? '6 4' : null);
    });
    // For sparse series, the tooltip shows the latest figure at or before the month (within the quarter).
    const near = (s, i) => {
      if (!s.sparse) return rows[i][s.key];
      for (let j = i; j >= Math.max(0, i - 2); j -= 1) if (rows[j][s.key] != null) return rows[j][s.key];
      return null;
    };
    const card = document.getElementById(cardId);
    const dots = series.map((s) => svg.append('circle').attr('r', 3.5).attr('fill', s.color).attr('display', 'none'));
    const extras = hover(svg, card, x, rows, H, ml, W - mr, (r, px, i) => {
      dots.forEach((d, k) => { const v = r[series[k].key]; d.attr('display', v == null ? 'none' : null).attr('cx', px).attr('cy', v == null ? 0 : y(v)); });
      return series.map((s) => [s.color, s.name + (s.sparse ? ' (quarter)' : ''), pct(near(s, i))]);
    });
    extras.push(...dots);
  }

  // Line plus bars (y/y and m/m; or SA index and SA m/m).
  function lineBars(cardId, L, B, opt = {}) {
    const box = document.getElementById(cardId + '-chart');
    legend(cardId + '-legend', [B, L]);
    if (!status(box, Array.from(new Set([L.ds, B.ds])))) return;
    const all = fill(wide([L, B]));
    const start = all.findIndex((r) => r[B.key] != null);
    const rows = start < 0 ? [] : (opt.all ? all.slice(start) : win(all.slice(start), cardId));
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280, mr = opt.right ? 40 : 8;
    const bvals = rows.map((r) => r[B.key]).filter((v) => v != null);
    const { svg, x, y, W, ml } = frame(box, rows, H, opt.right ? bvals : bvals.concat(rows.map((r) => r[L.key]).filter((v) => v != null)), fmt1, true, mr);
    let yl = y;
    if (opt.right) {
      const lv = rows.map((r) => r[L.key]).filter((v) => v != null);
      yl = d3.scaleLinear([d3.min(lv), d3.max(lv)], [H - 24, 12]).nice();
      J.axisStyle(svg.append('g').attr('transform', `translate(${W - mr + 4},0)`).call(d3.axisRight(yl).ticks(5).tickSize(0).tickFormat(fmt0)));
    }
    const step = (W - ml - mr) / Math.max(1, rows.length);
    const bw = Math.max(1, Math.min(14, step * 0.6));
    rows.forEach((r) => {
      if (r[B.key] == null) return;
      svg.append('rect').attr('x', x(J.date(r.date)) - bw / 2).attr('width', bw)
        .attr('y', y(Math.max(0, r[B.key]))).attr('height', Math.abs(y(r[B.key]) - y(0))).attr('fill', B.color);
    });
    svg.append('path').attr('d', d3.line().defined((r) => r[L.key] != null).x((r) => x(J.date(r.date))).y((r) => yl(r[L.key]))(rows))
      .attr('fill', 'none').attr('stroke', L.color).attr('stroke-width', 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    const card = document.getElementById(cardId);
    const dot = svg.append('circle').attr('r', 3.5).attr('fill', L.color).attr('display', 'none');
    const extras = hover(svg, card, x, rows, H, ml, W - mr, (r, px) => {
      dot.attr('display', r[L.key] == null ? 'none' : null).attr('cx', px).attr('cy', r[L.key] == null ? 0 : yl(r[L.key]));
      return [[L.color, L.name, opt.right ? f1(r[L.key]) : pct(r[L.key])], [B.color, B.name, pct(r[B.key])]];
    });
    extras.push(dot);
  }

  // Horizontal bars of published y/y in the latest month.
  function hbars(cardId, items, unitsText) {
    const box = document.getElementById(cardId + '-chart');
    document.getElementById(cardId + '-units').textContent = unitsText;
    if (!items.length) { box.replaceChildren(); return; }
    const W = box.clientWidth, rh = 18, gap = items.some((r) => r.gap) ? 10 : 0, H = items.length * rh + 28 + gap;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const lw = Math.min(W * 0.5, J.textWidth(svg, items.map((r) => r.name)) + 10);
    const x = d3.scaleLinear([Math.min(0, d3.min(items, (r) => r.v)), Math.max(0, d3.max(items, (r) => r.v))], [lw, W - 34]).nice();
    const ticks = x.ticks(5);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', x).attr('x2', x).attr('y1', 4).attr('y2', H - 22)
      .attr('stroke', (v) => (v === 0 ? 'var(--cds-chart-reference)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 18})`).call(d3.axisBottom(x).tickValues(ticks).tickSize(0).tickFormat(fmt0)));
    const card = document.getElementById(cardId), tip = J.tip(card);
    let off = 6;
    items.forEach((r) => {
      if (r.gap) off += gap;
      const yy = off; off += rh;
      svg.append('text').attr('x', lw - 6).attr('y', yy + rh / 2 + 1).attr('text-anchor', 'end').attr('dominant-baseline', 'middle')
        .attr('font-size', 11.5).attr('fill', 'var(--ad-ink)').attr('font-weight', r.bold ? 700 : null).text(r.name);
      const b = svg.append('rect').attr('x', x(Math.min(0, r.v))).attr('width', Math.max(1, Math.abs(x(r.v) - x(0))))
        .attr('y', yy + 2).attr('height', rh - 5).attr('fill', r.v < 0 ? 'var(--ad-c1)' : 'var(--ad-c2)');
      svg.append('text').attr('x', r.v < 0 ? x(r.v) - 3 : x(r.v) + 3).attr('y', yy + rh / 2 + 1).attr('dominant-baseline', 'middle')
        .attr('text-anchor', r.v < 0 ? 'end' : 'start').attr('font-size', 11).attr('fill', 'var(--ad-ink)').text(J.f1(r.v));
      b.on('mousemove', (ev) => {
        const cr = card.getBoundingClientRect();
        const lines = [[null, 'y/y', pct(r.v)]]; if (r.w != null) lines.push([null, 'Weight, % of CPI', J.f1(r.w)]);
        J.showTip(card, tip, r.name, lines, ev.clientX - cr.left, ev.clientY - cr.top);
      }).on('mouseleave', () => { tip.style.display = 'none'; });
    });
  }

  function latestDate() {
    const c = rowsOf('hk_cpi'); if (!c) return null;
    const a = c.by.get('composite|headline|all') || [];
    return a.reduce((m, r) => (r.yoy !== '' && r.date > m ? r.date : m), '');
  }
  function weights() {
    const W = dash.data('hk_cpi_weights');
    if (W.status !== 'ok') return new Map();
    const ref = W.data.reduce((m, r) => (r.reference_year > m ? r.reference_year : m), '');
    return new Map(W.data.filter((r) => r.reference_year === ref && r.index_type === 'composite').map((r) => [r.series, num(r.weight_pct)]));
  }

  function tiles() {
    const hm = document.getElementById('cpi-month');
    document.querySelectorAll('#cpi-headline [data-source], #cpi-month').forEach((el) => {
      const L = dash.data(el.dataset.source);
      if (L.status !== 'ok' || !L.data.length) { el.textContent = '—'; return; }
      el.classList.remove('dash-skeleton');
      const v = L.data[0][el.dataset.field];
      el.textContent = (el === hm || ['month', 'quarter'].includes(el.dataset.field)) ? (v || '') : f1(num(v));
    });
  }

  function takeaway() {
    const p = document.getElementById('cpi-takeaway');
    const L = dash.data('hk_cpi_latest');
    if (L.status !== 'ok' || !L.data.length) { if (failed(L.status)) p.replaceChildren(); return; }
    const a = L.data[0];
    const mk = (field) => { const b = document.createElement('b'); b.dataset.source = 'hk_cpi_latest'; b.dataset.field = field; b.dataset.row = '0'; b.textContent = pct(num(a[field])); return b; };
    const t = (x) => p.append(document.createTextNode(x));
    p.replaceChildren();
    t(`In ${a.month}, the CPI was `); p.append(mk('all_yoy'));
    t(` higher than a year earlier, against `); p.append(mk('all_yoy_prev'));
    t(` in ${a.prev_month}. Netting out the Government's one-off relief measures, underlying inflation was `); p.append(mk('underlying_yoy'));
    t('. Seasonally adjusted, prices rose by an average of '); p.append(mk('sa3')); t(' a month over the latest three months.');
  }

  // Heat table: published y/y for the latest 13 months, each row on its own colour range; 2025 weights.
  const HEAT = [
    ['all', 'CPI', 'lead'], ['under', 'Underlying CPI', 'lead'],
    ['food', 'Food', ''], ['meals_out', 'Meals out and takeaway food', 'sub'], ['basic_food', 'Basic food', 'sub'],
    ['housing', 'Housing', ''], ['g23_1', 'Private housing rent', 'sub'], ['g23_2', 'Public housing rent', 'sub'],
    ['egw', 'Electricity, gas and water', ''], ['g25', 'Electricity', 'sub'],
    ['alcohol_tobacco', 'Alcoholic drinks and tobacco', ''], ['clothing', 'Clothing and footwear', ''],
    ['durables', 'Durable goods', ''], ['misc_goods', 'Miscellaneous goods', ''],
    ['transport', 'Transport', ''], ['g57', 'Fuels for personal transport equipment', 'sub'], ['g66', 'Inbound and outbound transport fares', 'sub'],
    ['misc_services', 'Miscellaneous services', ''], ['g69', 'Package holidays', 'sub'],
  ];
  const STOPS = [[0, [99, 190, 123]], [0.5, [255, 235, 132]], [1, [248, 105, 107]]];
  const heatColor = (t) => {
    const i = t > 0.5 ? 1 : 0; const [t0, c0] = STOPS[i], [t1, c1] = STOPS[i + 1], f = (t - t0) / (t1 - t0);
    return `rgb(${c0.map((c, k) => Math.round(c + (c1[k] - c) * f)).join(',')})`;
  };
  function divHeat() {
    const tbl = document.getElementById('div-heat-table');
    const D = dash.data('hk_cpi');
    if (failed(D.status)) { tbl.replaceChildren(); return; }
    if (D.status !== 'ok') return;
    const wt = weights();
    const last = latestDate();
    const dates = []; for (let k = 12; k >= 0; k -= 1) dates.push(addM(last, -k));
    const get = (key, d) => {
      const s = key === 'under' ? { ds: 'hk_cpi', basis: 'underlying', series: 'all' } : { ds: 'hk_cpi', series: key };
      const p = pts(s).find((x) => x.date === d); return p ? p.v : null;
    };
    tbl.replaceChildren();
    const head = tbl.createTHead().insertRow();
    ['', 'Weight'].concat(dates.map((d) => `${MON[+d.slice(5, 7) - 1]} ${d.slice(2, 4)}`)).forEach((t) => {
      const th = document.createElement('th'); th.textContent = t; head.appendChild(th);
    });
    const tb = tbl.createTBody();
    HEAT.forEach(([key, name, cls]) => {
      const vals = dates.map((d) => get(key, d)), vs = vals.filter((v) => v != null);
      if (!vs.length) return;
      const tr = tb.insertRow(); tr.className = cls;
      tr.insertCell().textContent = name;
      const cw = tr.insertCell(); cw.className = 'wt'; cw.textContent = key !== 'under' && wt.has(key) ? d3.format('.2f')(wt.get(key)) : '';
      const lo = Math.min(...vs), hi = Math.max(...vs);
      vals.forEach((v) => {
        const td = tr.insertCell();
        if (v == null) return;
        td.textContent = J.f1(v) === '-0.0' ? '0.0' : J.f1(v);
        td.className = 'heat'; td.style.background = heatColor(hi > lo ? (v - lo) / (hi - lo) : 0.5); td.style.color = '#1a1a1a';
      });
    });
  }

  // Published contributions: parts from the top of the stack down, as in the legend.
  const PARTS = [
    ['egw', 'Electricity, gas and water', CC.bright], ['transport', 'Transport', 'var(--ad-c3)'], ['housing', 'Housing', 'var(--ad-c7)'],
    ['basic_food', 'Basic food', CC.grey], ['meals_out', 'Meals out and takeaway food', CC.fbss],
    ['misc_goods', 'Miscellaneous goods', CC.goods], ['durables', 'Durable goods', CC.goods],
    ['clothing', 'Clothing and footwear', CC.goods], ['alcohol_tobacco', 'Alcoholic drinks and tobacco', CC.goods],
    ['misc_services', 'Miscellaneous services', CC.services],
  ];
  function contribRows() {
    const D = dash.data('hk_cpi_contrib');
    if (D.status !== 'ok') return null;
    const by = new Map();
    D.data.forEach((r) => { if (!by.has(r.date)) by.set(r.date, { date: r.date }); by.get(r.date)[r.series] = num(r.contrib_pp); });
    return Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
  }
  function ctab() {
    const tbl = document.getElementById('ctab-table');
    const D = dash.data('hk_cpi_contrib');
    if (failed(D.status)) { tbl.replaceChildren(); return; }
    const rows = contribRows(); if (!rows) return;
    const last = rows.slice(-13);
    tbl.replaceChildren();
    const head = tbl.createTHead().insertRow();
    [''].concat(last.map((r) => `${MON[+r.date.slice(5, 7) - 1]} ${r.date.slice(2, 4)}`)).forEach((t) => { const th = document.createElement('th'); th.textContent = t; head.appendChild(th); });
    const tb = tbl.createTBody();
    const order = [['all', 'CPI, y/y', 'lead'], ['food', 'Food', ''], ['meals_out', 'Meals out and takeaway food', 'sub'], ['basic_food', 'Basic food', 'sub'],
      ['housing', 'Housing', ''], ['egw', 'Electricity, gas and water', ''], ['alcohol_tobacco', 'Alcoholic drinks and tobacco', ''],
      ['clothing', 'Clothing and footwear', ''], ['durables', 'Durable goods', ''], ['misc_goods', 'Miscellaneous goods', ''],
      ['transport', 'Transport', ''], ['misc_services', 'Miscellaneous services', '']];
    order.forEach(([k, name, cls]) => {
      const tr = tb.insertRow(); if (cls === 'lead') tr.className = 'lead';
      const c0 = tr.insertCell(); c0.textContent = name; if (cls === 'sub') c0.className = 'sub';
      last.forEach((r) => { const td = tr.insertCell(); const v = r[k]; td.textContent = v == null ? '' : (J.f1(v) === '-0.0' ? '0.0' : J.f1(v)); if (v != null && v < 0) td.classList.add('neg'); });
    });
    // Composite y/y row last, matching the stacked chart's line
    tb.appendChild(tb.rows[0]);
  }
  function contribChart() {
    const id = 'cpi-contrib', box = document.getElementById(id + '-chart');
    const leg = [{ name: 'CPI, y/y', color: CC.line }].concat(PARTS.filter((p, i) => !(p[2] === CC.goods && PARTS[i - 1] && PARTS[i - 1][2] === CC.goods))
      .map(([k, n, c]) => ({ name: c === CC.goods ? 'Alcohol and tobacco, clothing, durables, misc. goods' : n, color: c, bar: true })));
    legend(id + '-legend', leg);
    if (!status(box, ['hk_cpi_contrib'])) return;
    const rows = contribRows();
    if (!rows || !rows.length) { box.replaceChildren(); return; }
    const W = box.clientWidth, H = 300, mr = 8;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const stackOrder = PARTS.slice().reverse(); // bottom first
    const ext = rows.map((r) => {
      let p = 0, n = 0; stackOrder.forEach(([k]) => { const v = r[k] || 0; if (v > 0) p += v; else n += v; });
      return [n, p, r.all == null ? 0 : r.all];
    });
    const y = d3.scaleLinear([Math.min(0, d3.min(ext, (e) => Math.min(e[0], e[2]))), Math.max(0, d3.max(ext, (e) => Math.max(e[1], e[2])))], [H - 24, 12]).nice();
    const ticks = y.ticks(5);
    const ml = J.textWidth(svg, ticks.map(fmt1)) + 10;
    const xb = d3.scaleBand(rows.map((r) => r.date), [ml, W - mr]).padding(0.25);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - mr).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (v === 0 ? 'var(--cds-chart-reference)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt1)));
    const room = Math.max(1, Math.floor((W - ml - mr) / 52));
    const every = [1, 2, 3, 6, 12].find((s) => rows.length / s <= room) || 12;
    const tickDates = rows.map((r) => r.date).filter((d, i) => (rows.length - 1 - i) % every === 0);
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(xb).tickValues(tickDates).tickSize(0).tickFormat((d) => `${MON[+d.slice(5, 7) - 1]} ${d.slice(2, 4)}`)));
    rows.forEach((r) => {
      let p = 0, n = 0;
      stackOrder.forEach(([k, , c]) => {
        const v = r[k]; if (!v) return;
        const a = v > 0 ? p : n, b = a + v; if (v > 0) p = b; else n = b;
        svg.append('rect').attr('x', xb(r.date)).attr('width', xb.bandwidth()).attr('y', y(Math.max(a, b))).attr('height', Math.max(0, Math.abs(y(a) - y(b))))
          .attr('fill', c).attr('stroke', c === CC.goods ? 'var(--color-panel)' : null).attr('stroke-width', c === CC.goods ? 0.5 : null);
      });
    });
    const cx = (r) => xb(r.date) + xb.bandwidth() / 2;
    svg.append('path').attr('d', d3.line().defined((r) => r.all != null).x(cx).y((r) => y(r.all))(rows))
      .attr('fill', 'none').attr('stroke', CC.line).attr('stroke-width', 2.5).attr('stroke-linejoin', 'round');
    const card = document.getElementById(id), tip = J.tip(card);
    const dot = svg.append('circle').attr('r', 3.5).attr('fill', CC.line).attr('display', 'none');
    svg.append('rect').attr('x', ml).attr('width', W - mr - ml).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [mx] = d3.pointer(ev);
        const i = Math.max(0, Math.min(rows.length - 1, Math.floor((mx - ml) / xb.step()))), r = rows[i];
        dot.attr('display', r.all == null ? 'none' : null).attr('cx', cx(r)).attr('cy', r.all == null ? 0 : y(r.all));
        const lines = [[CC.line, 'CPI, y/y', pct(r.all)]].concat(PARTS.map(([k, n, c]) => [c, n, r[k] == null ? 'n/a' : (J.f1(r[k]) === '-0.0' ? '0.0' : J.f1(r[k]))]));
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, mLabel(r.date), lines, ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { dot.attr('display', 'none'); tip.style.display = 'none'; });
  }

  function coicop() {
    const box = document.getElementById('cpi-coicop-chart');
    if (!status(box, ['hk_cpi'])) return;
    const last = latestDate();
    const items = [];
    for (let i = 1; i <= 13; i += 1) {
      const key = `coicop_${String(i).padStart(2, '0')}`;
      const c = rowsOf('hk_cpi').by.get(`composite|headline|${key}`) || [];
      const r = c.find((x) => x.date === last);
      if (r && num(r.yoy) != null) items.push({ name: r.label, v: num(r.yoy) });
    }
    items.sort((a, b) => b.v - a.v);
    hbars('cpi-coicop', items, `% y/y, ${mLabel(last)}`);
  }

  function groups() {
    const box = document.getElementById('cpi-groups-chart');
    if (!status(box, ['hk_cpi'])) return;
    const last = latestDate(), wt = weights();
    const c = rowsOf('hk_cpi');
    const all = [];
    c.by.forEach((rs, k) => {
      const [it, b, s] = k.split('|');
      if (it !== 'composite' || b !== 'headline' || !/^g\d+$/.test(s)) return;
      const r = rs.find((x) => x.date === last);
      if (r && num(r.yoy) != null) all.push({ name: r.label, v: num(r.yoy), w: wt.has(s) ? wt.get(s) : null });
    });
    all.sort((a, b) => b.v - a.v);
    const n = Math.min(10, Math.floor(all.length / 2));
    const items = all.slice(0, n).concat(all.slice(-n).map((r, i) => (i === 0 ? Object.assign({ gap: true }, r) : r)));
    hbars('cpi-groups', items, `% y/y, ${mLabel(last)}: ten largest increases and ten largest falls of ${all.length} groups`);
  }

  let momIt = 'composite', saS = 'all';
  document.getElementById('cpi-mom-seg').addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return; momIt = b.dataset.s;
    e.currentTarget.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    J.redrawCpi();
  });
  document.getElementById('cpi-sa-seg').addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return; saS = b.dataset.s;
    e.currentTarget.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    J.redrawCpi();
  });

  J.redrawCpi = () => {
    if (!visible()) return;
    const C = (series, key, name, color, extra) => Object.assign({ ds: 'hk_cpi', it: 'composite', basis: 'headline', series, key, name, color, measure: 'yoy' }, extra || {});
    const IT = { composite: 'CPI', a: 'CPI(A)', b: 'CPI(B)', c: 'CPI(C)' };
    lines('cpi-measures', [C('all', 'cpi', 'CPI', 'var(--ad-c2)'),
      C('all', 'und', 'Underlying CPI', 'var(--ad-c1)', { basis: 'underlying', dash: true })]);
    lines('cpi-momentum', [
      { ds: 'hk_cpi_sa', it: momIt, series: 'all', measure: 'sa_mom3_long', key: 'h', name: IT[momIt], color: 'var(--ad-c2)' },
      { ds: 'hk_cpi_sa', it: momIt, basis: 'underlying', series: 'all', measure: 'sa_mom3', key: 'u', name: `Underlying ${IT[momIt]}`, color: 'var(--ad-c1)', dash: true, late: true },
    ], { fmt: fmt1 });
    lineBars('cpi-ym', C('all', 'yoy', 'CPI, y/y', 'var(--ad-c2)'), C('all', 'mom', 'CPI, m/m', 'var(--ad-c1)', { measure: 'mom', bar: true }));
    lineBars('cpi-sa', { ds: 'hk_cpi_sa', series: saS, measure: 'sa_index', key: 'i', name: `SA index (right), ${saS === 'all' ? 'all items' : 'food'}`, color: 'var(--ad-c2)' },
      { ds: 'hk_cpi_sa', series: saS, measure: 'sa_mom', key: 'm', name: 'SA m/m', color: 'var(--ad-c1)', bar: true }, { all: true, right: true });
    lines('cpi-hh', [C('all', 'cc', 'CPI', 'var(--ad-c2)'), C('all', 'a', 'CPI(A)', 'var(--ad-c5)', { it: 'a', thin: true }),
      C('all', 'b', 'CPI(B)', 'var(--ad-c6)', { it: 'b', thin: true }), C('all', 'c', 'CPI(C)', 'var(--ad-c1)', { it: 'c', thin: true })]);
    lines('cpi-fe', [C('food', 'f', 'Food', 'var(--ad-c5)'), C('meals_out', 'mo', 'Meals out and takeaway food', CC.fbss, { thin: true }),
      C('basic_food', 'bf', 'Basic food', CC.grey, { thin: true }), C('g25', 'el', 'Electricity', CC.bright),
      C('g26', 'tg', 'Towngas', 'var(--ad-c7)', { thin: true }), C('g57', 'mf', 'Fuels for personal transport', 'var(--ad-c3)', { dash: true })], { anyStart: true });
    lines('cpi-housing', [C('housing', 'h', 'Housing', 'var(--ad-c7)'), C('g23_1', 'pr', 'Private housing rent', 'var(--ad-c2)', { thin: true }),
      C('g23_2', 'pu', 'Public housing rent', 'var(--ad-c1)', { thin: true }), C('g24', 'mf', 'Management fees and other housing expenses', 'var(--ad-c8)', { dash: true })], { anyStart: true });
    lines('cpi-sections', [C('food', 'f', 'Food', 'var(--ad-c5)'), C('housing', 'h', 'Housing', 'var(--ad-c7)'),
      C('egw', 'e', 'Electricity, gas and water', CC.bright, { thin: true }), C('alcohol_tobacco', 'a', 'Alcohol and tobacco', 'var(--ad-c4)', { thin: true }),
      C('clothing', 'c', 'Clothing and footwear', 'var(--ad-c8)', { thin: true }), C('durables', 'd', 'Durable goods', CC.goods, { thin: true }),
      C('misc_goods', 'g', 'Miscellaneous goods', 'var(--ad-c6)', { thin: true }), C('transport', 't', 'Transport', 'var(--ad-c3)'),
      C('misc_services', 's', 'Miscellaneous services', 'var(--ad-c2)')], { anyStart: true });
    coicop();
    groups();
    contribChart();
    const P = (series, key, name, color, extra) => Object.assign({ ds: 'hk_ppi', series, key, name, color }, extra || {});
    lines('ppi-parts', [P('manufacturing', 'm', 'Manufacturing', 'var(--ad-c2)'), P('ind_10-12', 'f', 'Food, beverages and tobacco', 'var(--ad-c5)', { thin: true }),
      P('ind_24-30', 'e', 'Metal, electronic products, machinery', 'var(--ad-c1)', { thin: true }), P('ind_17_18', 'p', 'Paper and printing', 'var(--ad-c8)', { thin: true }),
      P('ind_13_14', 't', 'Textiles and apparel', 'var(--ad-c7)', { thin: true })], { anyStart: true, sparse: true });
    lines('trade-prices', [P('import_uvi', 'i', 'Import prices', 'var(--ad-c1)'), P('export_uvi', 'x', 'Export prices', 'var(--ad-c3)'),
      C('all', 'cpi', 'CPI', 'var(--ad-c2)', { thin: true })]);
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

  dash.onData(() => { tiles(); takeaway(); divHeat(); ctab(); J.redrawCpi(); });
})();
