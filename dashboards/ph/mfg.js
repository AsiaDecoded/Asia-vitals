// Philippines Manufacturing tab: PSA MISSI (volume of production index, capacity utilisation) and national accounts
// (manufacturing GVA), as published. The 3mma and YTD on Chart 3 are calculated in the pipeline (ph_mfg_psa) and flagged;
// nothing is calculated here: the calcs only pick rows.

dash.calc('mfg_latest', {
  title: 'Latest MISSI month',
  description: 'The latest month of the PSA volume of production index, picked from the published rows.',
  inputs: ['ph_vopi_div'],
  fn: (ph_vopi_div) => {
    const r = ph_vopi_div.find((x) => x.code === 'C');
    if (!r) return [];
    const M = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    return [{ date: r.date, label: `${M[Number(r.date.slice(5, 7)) - 1]} ${r.date.slice(0, 4)}` }];
  },
});

(() => {
  const J = window.JG;
  const N = (v) => (v === '' || v == null ? null : Number(v));
  const visible = () => !document.getElementById('manufacturing').hidden;
  const failed = (st) => st === 'error' || st === 'connect' || st === 'declined';
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const mLab = (d) => `${MON[+d.slice(5, 7) - 1]} ${d.slice(0, 4)}`;
  const qLab = (d) => `Q${Math.ceil(+d.slice(5, 7) / 3)} ${d.slice(0, 4)}`;
  const fmt0 = (v) => d3.format('.0f')(v);
  const sortD = (a, b) => (a.date < b.date ? -1 : 1);
  const SHORT = (n) => String(n || '').replace(/^Manufacture of /, '').replace(/^./, (c) => c.toUpperCase());

  function legend(id, series) {
    const el = document.getElementById(id); if (!el) return;
    el.replaceChildren();
    series.forEach((s) => {
      const span = document.createElement('span'), ln = document.createElement('span');
      ln.className = s.bar ? 'sw' : 'ln'; ln.style.background = s.color;
      span.append(ln, document.createTextNode(s.name)); el.appendChild(span);
    });
  }
  function status(box, ids) {
    const st = ids.map((i) => dash.data(i).status);
    if (st.some(failed)) { box.classList.remove('dash-skeleton'); J.fail(box); return false; }
    if (st.some((s) => s !== 'ok')) { box.replaceChildren(); box.classList.add('dash-skeleton'); return false; }
    box.classList.remove('dash-skeleton');
    return true;
  }
  // Default window for the monthly VoPI charts: from Jan 2022 (2020-21 rates run from -82% to +534%); the slider reaches back.
  const START = { 'mfg-va': '2022-01-01', 'mfg-elec': '2022-01-01' };
  const started = {};
  function startAt(id, all) {
    if (started[id] || !START[id] || !all.length || J.range[id]) return;
    started[id] = true;
    const i = all.findIndex((r) => r.date >= START[id]); if (i <= 0) return;
    const f = i / (all.length - 1); J.range[id] = [f, 1];
    const card = document.getElementById(id), inp = card && card.querySelector('.ad-slider input'), sel = card && card.querySelector('.ad-slider-sel');
    if (inp) inp.value = Math.round(f * 1000);
    if (sel) sel.style.left = `${f * 100}%`;
  }
  // Every month from the first to the last, so a month with no figure is a gap in the line.
  function months(rows) {
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
    const ticks = y.ticks(5), ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    const x = d3.scaleUtc([J.date(rows[0].date), J.date(rows[rows.length - 1].date)], [ml, W - mr]);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - mr).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (zero && v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
    const y0 = +rows[0].date.slice(0, 4), y1 = +rows[rows.length - 1].date.slice(0, 4);
    const step = [1, 2, 5, 10].find((k) => (y1 - y0 + 1) / k <= Math.max(1, Math.round((W - ml - mr) / 56))) || 10;
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).ticks(d3.utcYear.every(step)).tickSize(0).tickFormat(d3.utcFormat('%Y'))));
    return { svg, x, y, W, ml };
  }
  function tipper(svg, card, x, rows, H, ml, right, head, lines, dots) {
    const tip = J.tip(card);
    const rule = svg.append('line').attr('y1', 8).attr('y2', H - 22).attr('stroke', 'var(--cds-chart-reference)').attr('display', 'none');
    const bis = d3.bisector((r) => J.date(r.date)).center;
    svg.append('rect').attr('x', ml).attr('width', Math.max(0, right - ml)).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const r = rows[bis(rows, x.invert(d3.pointer(ev)[0]))], px = x(J.date(r.date));
        rule.attr('display', null).attr('x1', px).attr('x2', px);
        if (dots) dots(r, px);
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, head(r), lines(r), ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); if (dots) dots(null); tip.style.display = 'none'; });
  }
  // Line chart over wide rows [{date, <key>: v}]; series [{key, name, color, thin, dotted}].
  function lineChart(id, S, all, opt = {}) {
    const box = document.getElementById(id + '-chart');
    startAt(id, all);
    const rows = J.slice(all, id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 300, mr = 8;
    const vals = rows.flatMap((r) => S.map((s) => r[s.key])).filter((v) => v != null);
    const { svg, x, y, W, ml } = frame(box, rows, H, vals, opt.fmt || fmt0, opt.zero !== false, mr);
    S.forEach((s) => {
      const pts = rows.filter((r) => s.sparse ? r[s.key] != null : true);
      svg.append('path').attr('d', d3.line().defined((r) => r[s.key] != null).x((r) => x(J.date(r.date))).y((r) => y(r[s.key]))(pts))
        .attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', s.thin ? 1.5 : 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    });
    const dots = S.map((s) => svg.append('circle').attr('r', 3.5).attr('fill', s.color).attr('display', 'none'));
    tipper(svg, document.getElementById(id), x, rows, H, ml, W - mr, (r) => (opt.q ? qLab(r.date) : mLab(r.date)),
      (r) => S.filter((s) => !s.sparse || r[s.key] != null).map((s) => [s.color, s.name, r[s.key] == null ? 'n/a' : (opt.tip || ((v) => v.toFixed(1) + '%'))(r[s.key])]),
      (r, px) => S.forEach((s, k) => (!r || r[s.key] == null ? dots[k].attr('display', 'none') : dots[k].attr('display', null).attr('cx', px).attr('cy', y(r[s.key])))));
  }
  const vopi = (code) => dash.data('ph_vopi').data.filter((r) => r.code === code && N(r.yoy) != null).map((r) => ({ date: r.date, v: N(r.yoy) }));
  function wide(list) {
    const by = new Map();
    list.forEach(({ key, rows }) => rows.forEach((r) => { if (!by.has(r.date)) by.set(r.date, { date: r.date }); by.get(r.date)[key] = r.v; }));
    return Array.from(by.values()).sort(sortD);
  }
  const gva = (pred) => dash.data('ph_mfg_gva').data.filter(pred).map((r) => ({ date: r.date, v: N(r.value), code: r.code, industry: r.industry }));

  // Chart 1: manufacturing GVA, real y/y, quarterly (national accounts), and the volume of production index y/y, monthly
  // (MISSI: backcast 2002-2017, 2018 base from 2019; no y/y published for 2018).
  function chart1() {
    const id = 'mfg-va', box = document.getElementById(id + '-chart');
    const S = [{ key: 'vopi', name: 'Volume of production index (VoPI)', color: 'var(--ad-c1)', thin: true },
      { key: 'gva', name: 'Manufacturing GVA, real (quarterly)', color: 'var(--ad-c2)', sparse: true }];
    legend(id + '-legend', S);
    if (!status(box, ['ph_vopi', 'ph_mfg_gva'])) return;
    const all = months(wide([{ key: 'vopi', rows: vopi('C') },
      { key: 'gva', rows: gva((r) => r.code === 'C' && r.measure === 'yoy' && r.date >= '2002-01-01') }]));
    lineChart(id, S, all);
  }
  // Chart 2: manufacturing and industry as % of GDP, current prices, quarterly.
  function chart2() {
    const id = 'mfg-share', box = document.getElementById(id + '-chart');
    const S = [{ key: 'industry', name: 'Industry', color: 'var(--ad-c1)' }, { key: 'C', name: 'Manufacturing', color: 'var(--ad-c2)' }];
    legend(id + '-legend', S);
    if (!status(box, ['ph_mfg_gva'])) return;
    const all = wide(S.map((s) => ({ key: s.key, rows: gva((r) => r.measure === 'share_gdp' && r.code === s.key) })));
    lineChart(id, S, all, { q: true, zero: true });
  }
  // Chart 3: VoPI by PSIC division: 3mma and calendar year to date, y/y (calculated in ph_mfg_psa). Manufacturing on top,
  // then the divisions sorted by the 3mma.
  function chart3() {
    const id = 'mfg-div', box = document.getElementById(id + '-chart');
    const S = [{ key: 'm3', name: '3mma', color: 'var(--ad-c2)', bar: true }, { key: 'ytd', name: 'YTD', color: 'var(--ad-c1)', bar: true }];
    if (!status(box, ['ph_vopi_div'])) { legend(id + '-legend', []); return; }
    const D = dash.data('ph_vopi_div').data.map((r) => ({ ...r, m3: N(r.m3), ytd: N(r.ytd) }));
    if (!D.length) { box.replaceChildren(); return; }
    const head = D.find((r) => r.code === 'C');
    S[1].name = `YTD (${head ? head.ytd_months : ''})`;
    legend(id + '-legend', S);
    const rows = [head].filter(Boolean).concat(D.filter((r) => r.code !== 'C').sort((a, b) => (b.m3 ?? -1e9) - (a.m3 ?? -1e9)));
    const W = box.clientWidth, rowH = 26, top = 6, H = top + rows.length * rowH + 22;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const lw = Math.min(260, Math.max(140, W * 0.36));
    const vals = rows.flatMap((r) => [r.m3, r.ytd]).filter((v) => v != null);
    const x = d3.scaleLinear([Math.min(0, d3.min(vals)), Math.max(0, d3.max(vals))], [lw + 8, W - 44]).nice();
    x.ticks(5).forEach((t) => {
      svg.append('line').attr('x1', x(t)).attr('x2', x(t)).attr('y1', top).attr('y2', H - 20).attr('stroke', t === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)');
      svg.append('text').attr('x', x(t)).attr('y', H - 6).attr('text-anchor', 'middle').attr('font-size', 11).attr('fill', 'var(--ad-ink)').text(fmt0(t));
    });
    const bh = (rowH - 8) / 2;
    rows.forEach((r, i) => {
      const y0 = top + i * rowH;
      const lab = r.code === 'C' ? 'Manufacturing' : `${SHORT(r.name)} (${r.code})`;
      const t = svg.append('text').attr('x', lw).attr('y', y0 + rowH / 2).attr('dy', '0.35em').attr('text-anchor', 'end').attr('font-size', 12)
        .attr('fill', 'var(--ad-ink)').attr('font-weight', r.code === 'C' ? 700 : null).text(lab);
      const full = lab;
      let s = lab; while (t.node().getComputedTextLength() > lw - 4 && s.length > 8) { s = s.slice(0, -2); t.text(s + '…'); }
      t.append('title').text(full);
      S.forEach((sr, k) => {
        const v = r[sr.key]; if (v == null) return;
        svg.append('rect').attr('x', Math.min(x(0), x(v))).attr('width', Math.abs(x(v) - x(0))).attr('y', y0 + 4 + k * bh).attr('height', bh - 1).attr('fill', sr.color);
      });
      if (i === 0) svg.append('line').attr('x1', 0).attr('x2', W).attr('y1', y0 + rowH).attr('y2', y0 + rowH).attr('stroke', 'var(--ad-grid)');
    });
    const card = document.getElementById(id), tip = J.tip(card);
    svg.append('rect').attr('x', 0).attr('width', W).attr('y', top).attr('height', rows.length * rowH).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [, my] = d3.pointer(ev), r = rows[Math.max(0, Math.min(rows.length - 1, Math.floor((my - top) / rowH)))];
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, `${SHORT(r.name)} (${r.code})`, S.map((s) => [s.color, s.name, r[s.key] == null ? 'n/a' : r[s.key].toFixed(1) + '%'])
          .concat([[null, `${mLab(r.date)}, published`, r.yoy === '' ? 'n/a' : Number(r.yoy).toFixed(1) + '%']]), ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { tip.style.display = 'none'; });
  }
  // Chart 4: computer, electronic and optical products (C26) and electrical equipment (C27), VoPI y/y, with all manufacturing.
  function chart4() {
    const id = 'mfg-elec', box = document.getElementById(id + '-chart');
    const S = [{ key: 'C26', name: 'Computer, electronic and optical (C26)', color: 'var(--ad-c1)' },
      { key: 'C27', name: 'Electrical equipment (C27)', color: 'var(--ad-c6)' },
      { key: 'C', name: 'All manufacturing', color: 'var(--ad-c2)', thin: true }];
    legend(id + '-legend', S);
    if (!status(box, ['ph_vopi'])) return;
    const all = months(wide(S.map((s) => ({ key: s.key, rows: vopi(s.key).filter((r) => r.date >= '2019-01-01') }))));
    lineChart(id, S, all);
  }
  // Chart 5: average capacity utilisation rate, all manufacturing, monthly.
  function chart5() {
    const id = 'mfg-capu', box = document.getElementById(id + '-chart');
    const S = [{ key: 'C', name: 'All manufacturing', color: 'var(--ad-c2)' }];
    legend(id + '-legend', []);
    if (!status(box, ['ph_capu'])) return;
    const all = months(dash.data('ph_capu').data.filter((r) => r.code === 'C').map((r) => ({ date: r.date, C: N(r.rate) })).sort(sortD));
    lineChart(id, S, all, { zero: false });
  }
  // Chart 6: industries' shares of manufacturing GVA, current prices, quarterly: the six largest in the latest quarter.
  function chart6() {
    const id = 'mfg-gvash', box = document.getElementById(id + '-chart');
    if (!status(box, ['ph_mfg_gva'])) { legend(id + '-legend', []); return; }
    const rows = gva((r) => r.measure === 'share');
    if (!rows.length) { box.replaceChildren(); legend(id + '-legend', []); return; }
    const last = rows.reduce((m, r) => (r.date > m ? r.date : m), '');
    const top = rows.filter((r) => r.date === last).sort((a, b) => b.v - a.v).slice(0, 6);
    const COL = ['var(--ad-c1)', 'var(--ad-c2)', 'var(--ad-c5)', 'var(--ad-c6)', 'var(--ad-c7)', 'var(--ad-c4)'];
    const S = top.map((r, k) => ({ key: r.code, name: SHORT(r.industry), color: COL[k] }));
    legend(id + '-legend', S);
    lineChart(id, S, wide(S.map((s) => ({ key: s.key, rows: rows.filter((r) => r.code === s.key) }))), { q: true, zero: true });
  }
  // Heat table: VoPI y/y by division, the latest 12 months, as published; each row coloured on its own range.
  function heat() {
    const tb = document.getElementById('mfg-heat-table'); if (!tb) return;
    const D = dash.data('ph_vopi');
    tb.replaceChildren();
    if (D.status !== 'ok') return;
    const dates = Array.from(new Set(D.data.map((r) => r.date))).sort().slice(-12);
    const by = new Map();
    D.data.forEach((r) => { if (!dates.includes(r.date)) return; if (!by.has(r.code)) by.set(r.code, { code: r.code, name: r.name, order: +r.order, v: {} }); by.get(r.code).v[r.date] = N(r.yoy); });
    const head = tb.createTHead().insertRow();
    const th0 = document.createElement('th'); th0.textContent = 'Division'; head.appendChild(th0);
    dates.forEach((d) => { const th = document.createElement('th'); th.textContent = mLab(d); head.appendChild(th); });
    const body = tb.createTBody();
    Array.from(by.values()).sort((a, b) => a.order - b.order).forEach((r) => {
      const tr = body.insertRow(); tr.dataset.key = r.code;
      const c0 = tr.insertCell(); c0.textContent = r.code === 'C' ? 'Manufacturing' : `${SHORT(r.name)} (${r.code})`;
      if (r.code === 'C') c0.style.fontWeight = '700';
      const vs = dates.map((d) => r.v[d]).filter((v) => v != null), lo = d3.min(vs), hi = d3.max(vs);
      dates.forEach((d) => {
        const c = tr.insertCell(), v = r.v[d]; c.textContent = v == null ? '—' : v.toFixed(1);
        if (v != null && hi > lo) {
          const f = (v - lo) / (hi - lo);
          c.style.background = d3.interpolateRgb('rgba(146,208,80,0.55)', 'rgba(189,27,33,0.55)')(f);
        }
      });
    });
  }
  function pageHead() {
    const L = dash.data('mfg_latest'), el = document.getElementById('mfg-month'); if (!el) return;
    el.textContent = L.status === 'ok' && L.data[0] ? `MISSI: ${L.data[0].label}` : '—';
    el.classList.toggle('dash-skeleton', L.status !== 'ok');
  }
  J.redrawMfg = () => {
    pageHead();
    if (!visible()) return;
    chart1(); chart2(); chart3(); chart4(); chart5(); chart6(); heat();
  };
  dash.onData(() => J.redrawMfg());
})();
