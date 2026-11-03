// Thailand Manufacturing tab, Charts 1-7: OIE manufacturing production index (MPI) and capacity utilisation, NESDC
// manufacturing value added and shares of GDP. Calculated in the pipeline and flagged calculated = y (asked for
// 3 Nov 2026): MPI y/y (OIE publishes only the latest month's and quarter's rates) and shares of GDP. The MPI's two
// bases are shown as published, not linked: 2016 = 100 to Dec 2021, chain-linked 2021 = 100 from Jan 2022.

(() => {
  const J = window.JG;
  const num = J.num;
  const { legend, status, frame, tipLayer, line, qLab, failed, fmt0 } = J.th;
  const visible = () => !document.getElementById('manufacturing').hidden;
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const mLab = (d) => `${MON[+d.slice(5, 7) - 1]} ${d.slice(0, 4)}`;
  const SWITCH = '2022-01-01';   // first y/y on the chain-linked index (2021 = 100)
  const BASE_NAME = { 2016: '2016 = 100', 2021: 'chain-linked, 2021 = 100' };
  const BIG = [['10', 'var(--ad-c6)'], ['19', 'var(--ad-c4)'], ['20', 'var(--ad-c5)'], ['26', 'var(--ad-c1)'], ['29', 'var(--ad-c2)']];
  const STOPS = [[0, [99, 190, 123]], [0.5, [255, 235, 132]], [1, [248, 105, 107]]];
  const heatColor = (t) => {
    const i = t > 0.5 ? 1 : 0; const [t0, c0] = STOPS[i], [t1, c1] = STOPS[i + 1], f = (t - t0) / (t1 - t0);
    return `rgb(${c0.map((c, k) => Math.round(c + (c1[k] - c) * f)).join(',')})`;
  };

  const M = () => dash.data('th_mpi');
  // MPI y/y for one industry and frequency: the 2016 base before the switch, the 2021 base from it.
  function mpi(code, freq) {
    const D = M(); if (D.status !== 'ok') return [];
    return D.data.filter((r) => r.code === code && r.measure === 'yoy' && r.freq === freq
      && ((r.base === '2016' && r.date < SWITCH) || (r.base === '2021' && r.date >= SWITCH)))
      .map((r) => ({ date: r.date, v: num(r.value), base: r.base })).filter((r) => r.v != null).sort((a, b) => (a.date < b.date ? -1 : 1));
  }
  function nesdc(code, measure) {
    const D = dash.data('th_gdp'); if (D.status !== 'ok') return [];
    return D.data.filter((r) => r.code === code && r.span === 'Q' && r.measure === measure && r.price === (measure === 'share' ? 'current' : 'cvm_2002'))
      .map((r) => ({ date: r.date, v: num(r.rate) })).filter((r) => r.v != null).sort((a, b) => (a.date < b.date ? -1 : 1));
  }
  function wide(S) {
    const by = new Map();
    S.forEach((s) => s.rows.forEach((r) => { if (!by.has(r.date)) by.set(r.date, { date: r.date }); const o = by.get(r.date); o[s.key] = r.v; if (r.base) o.base = r.base; }));
    return Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
  }
  function breakLine(svg, x, rows, H, label) {
    if (!(rows[0].date < SWITCH && rows[rows.length - 1].date >= SWITCH)) return;
    const sx = x(J.date(SWITCH));
    svg.append('line').attr('x1', sx).attr('x2', sx).attr('y1', 18).attr('y2', H - 24).attr('stroke', 'var(--ad-axis)').attr('stroke-dasharray', '3 3');
    const t = svg.append('text').attr('y', 12).attr('font-size', 12).attr('fill', 'var(--ad-ink)').text(label);
    const w = t.node().getComputedTextLength(); t.attr('x', Math.max(0, sx - w / 2));
  }
  // Line chart of y/y (or %) series; opt.q quarterly labels, opt.brk the MPI base switch, opt.dp decimals.
  function lines(id, S, ds, opt = {}) {
    const box = document.getElementById(id + '-chart');
    legend(id + '-legend', S.length > 1 ? S : []);
    if (!status(box, ds)) return;
    const rows = J.slice(wide(S).filter((r) => !opt.start || r.date >= opt.start), id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280;
    const { svg, x, y, W, ml, mr } = frame(box, rows, H, rows.flatMap((r) => S.map((s) => r[s.key])).filter((v) => v != null), fmt0, opt.zero !== false);
    if (opt.brk) breakLine(svg, x, rows, H, 'Chain-linked index');
    S.slice().reverse().forEach((s) => {
      const p = line(svg, x, y, rows, s.key, s.color, s.thin);
      if (s.dash) p.attr('stroke-dasharray', '6 4');
    });
    const dots = S.map((s) => svg.append('circle').attr('r', 3.5).attr('fill', s.color).attr('display', 'none'));
    const ex = tipLayer(svg, document.getElementById(id), x, rows, H, ml, W - mr, (r) => (opt.q ? qLab(r.date) : mLab(r.date)), (r, px) => {
      dots.forEach((d, i) => { const v = r[S[i].key]; d.attr('display', v == null ? 'none' : null).attr('cx', px).attr('cy', v == null ? 0 : y(v)); });
      const out = S.map((s) => [s.color, s.name, r[s.key] == null ? 'n/a' : r[s.key].toFixed(opt.dp != null ? opt.dp : 1) + (opt.unit || '%')]);
      if (opt.brk && r.base) out.push([null, 'MPI index', BASE_NAME[r.base]]);
      if (opt.note) out.push([null, opt.note, '']);
      return out;
    });
    ex.push(...dots);
  }

  // Chart 3: MPI y/y by industry, latest month, with OIE's weights.
  function bars() {
    const id = 'mfg-div', box = document.getElementById(id + '-chart');
    if (!status(box, ['th_mpi'])) return;
    const D = M().data.filter((r) => r.base === '2021' && r.freq === 'M' && r.measure === 'yoy');
    const last = D.reduce((m, r) => (r.date > m ? r.date : m), '');
    const tot = D.find((r) => r.date === last && r.code === 'all');
    const rows = D.filter((r) => r.date === last && /^\d\d$/.test(r.code) && num(r.value) != null)
      .map((r) => ({ name: `${r.industry} (${Number(r.weight).toFixed(1)}%)`, v: num(r.value) })).sort((a, b) => b.v - a.v);
    document.getElementById(id + '-units').textContent = `% y/y, ${mLab(last)} (weight, % of the index); manufacturing ${tot ? Number(tot.value).toFixed(1) + '%' : 'n/a'}`;
    if (!rows.length) { box.replaceChildren(); return; }
    const W = box.clientWidth, rh = 18, H = rows.length * rh + 28;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const lw = Math.min(W * 0.5, J.textWidth(svg, rows.map((r) => r.name)) + 10);
    const x = d3.scaleLinear([Math.min(0, d3.min(rows, (r) => r.v)), Math.max(0, d3.max(rows, (r) => r.v))], [lw, W - 34]).nice();
    const ticks = x.ticks(5);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', x).attr('x2', x).attr('y1', 4).attr('y2', H - 22)
      .attr('stroke', (v) => (v === 0 ? 'var(--cds-chart-reference)' : 'var(--ad-grid)'));
    if (tot) {
      const tx = x(Number(tot.value));
      svg.append('line').attr('x1', tx).attr('x2', tx).attr('y1', 4).attr('y2', H - 22).attr('stroke', 'var(--ad-c2)').attr('stroke-dasharray', '4 3');
    }
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 18})`).call(d3.axisBottom(x).tickValues(ticks).tickSize(0).tickFormat(fmt0)));
    const card = document.getElementById(id), tip = J.tip(card);
    rows.forEach((r, i) => {
      const yy = 6 + i * rh;
      svg.append('text').attr('x', lw - 6).attr('y', yy + rh / 2 + 1).attr('text-anchor', 'end').attr('dominant-baseline', 'middle')
        .attr('font-size', 11.5).attr('fill', 'var(--ad-ink)').text(r.name);
      const b = svg.append('rect').attr('x', x(Math.min(0, r.v))).attr('width', Math.max(1, Math.abs(x(r.v) - x(0))))
        .attr('y', yy + 2).attr('height', rh - 5).attr('fill', r.v < 0 ? 'var(--ad-c1)' : 'var(--ad-c8)');
      svg.append('text').attr('x', r.v < 0 ? x(r.v) - 3 : x(r.v) + 3).attr('y', yy + rh / 2 + 1).attr('dominant-baseline', 'middle')
        .attr('text-anchor', r.v < 0 ? 'end' : 'start').attr('font-size', 11).attr('fill', 'var(--ad-ink)').text(J.f1(r.v));
      b.on('mousemove', (ev) => { const cr = card.getBoundingClientRect(); J.showTip(card, tip, r.name, [[null, 'MPI, y/y (calculated)', r.v.toFixed(2) + '%']], ev.clientX - cr.left, ev.clientY - cr.top); })
        .on('mouseleave', () => { tip.style.display = 'none'; });
    });
  }

  // Chart 7: heat table, MPI y/y by industry, last 13 months (chain-linked index).
  function heat() {
    const tbl = document.getElementById('mfg-heat-table');
    const D = M();
    if (failed(D.status)) { tbl.replaceChildren(); return; }
    if (D.status !== 'ok') return;
    const R = D.data.filter((r) => r.base === '2021' && r.freq === 'M' && r.measure === 'yoy');
    const dates = Array.from(new Set(R.filter((r) => r.code === 'all').map((r) => r.date))).sort().slice(-13);
    const codes = []; R.forEach((r) => { if (!codes.find((c) => c.code === r.code)) codes.push({ code: r.code, name: r.industry, w: num(r.weight) }); });
    codes.sort((a, b) => (a.code === 'all' ? -1 : b.code === 'all' ? 1 : b.w - a.w));
    tbl.replaceChildren();
    const head = tbl.createTHead().insertRow();
    ['', 'Weight'].concat(dates.map((d) => `${MON[+d.slice(5, 7) - 1]} ${d.slice(2, 4)}`)).forEach((t) => { const th = document.createElement('th'); th.textContent = t; head.appendChild(th); });
    const tb = tbl.createTBody();
    codes.forEach((c) => {
      const vals = new Map(R.filter((r) => r.code === c.code && dates.includes(r.date)).map((r) => [r.date, num(r.value)]));
      const vs = Array.from(vals.values()).filter((v) => v != null);
      if (!vs.length) return;
      const tr = tb.insertRow(); if (c.code === 'all') tr.className = 'lead';
      tr.insertCell().textContent = c.name;
      const wt = tr.insertCell(); wt.className = 'wt'; wt.textContent = c.w == null ? '' : c.w.toFixed(1);
      const lo = Math.min(...vs), hi = Math.max(...vs);
      dates.forEach((d) => {
        const td = tr.insertCell(); const v = vals.get(d);
        if (v == null) return;
        td.textContent = J.f1(v) === '-0.0' ? '0.0' : J.f1(v);
        td.className = 'heat'; td.style.background = heatColor(hi > lo ? (v - lo) / (hi - lo) : 0.5); td.style.color = '#1a1a1a';
      });
    });
  }

  function capu() {
    const D = M();
    const rows = D.status === 'ok' ? D.data.filter((r) => r.code === 'all' && r.measure === 'capu')
      .map((r) => ({ date: r.date, v: num(r.value), base: r.base })).filter((r) => r.v != null)
      .sort((a, b) => (a.date < b.date ? -1 : 1)) : [];
    if (rows.some((r) => r.date < '2024-01-01') && rows.some((r) => r.date >= '2025-01-01')) rows.push({ date: '2024-06-01', v: null });
    rows.sort((a, b) => (a.date < b.date ? -1 : 1));
    // the 2016-base file runs to Dec 2023, the current one from Jan 2025: 2024 is a gap (not in OIE's files)
    const S = [{ key: 'cu', name: 'Capacity utilisation', color: 'var(--ad-c1)', rows }];
    lines('mfg-capu', S, ['th_mpi'], { zero: false, dp: 2 });
  }

  J.redrawMfg = () => {
    if (!visible()) return;
    lines('mfg-mpi', [{ key: 'mpi', name: 'Manufacturing production index', color: 'var(--ad-c2)', rows: mpi('all', 'M') }], ['th_mpi'],
      { brk: true, note: 'y/y calculated from OIE’s index' });
    lines('mfg-va', [
      { key: 'va', name: 'Manufacturing value added, real', color: 'var(--ad-c1)', rows: nesdc('manufacturing', 'yoy') },
      { key: 'mpi', name: 'Manufacturing production index', color: 'var(--ad-c8)', dash: true, rows: mpi('all', 'Q') },
      { key: 'gdp', name: 'Real GDP', color: 'var(--ad-c2)', thin: true, rows: nesdc('total', 'yoy') },
    ], ['th_gdp', 'th_mpi'], { q: true, brk: true, start: '2017-01-01' });
    bars();
    const D = M();
    const name = (c) => (D.status === 'ok' ? (D.data.find((r) => r.code === c && r.base === '2021') || {}).industry : c) || c;
    lines('mfg-big', BIG.map(([c, color]) => ({ key: 'd' + c, name: name(c), color, rows: mpi(c, 'M') })), ['th_mpi'],
      { brk: true, start: '2017-01-01' });
    lines('mfg-share', [
      { key: 'ind', name: 'Industrial (B–E)', color: 'var(--ad-c8)', rows: nesdc('industrial', 'share') },
      { key: 'mfg', name: 'Manufacturing (C)', color: 'var(--ad-c1)', rows: nesdc('manufacturing', 'share') },
    ], ['th_gdp'], { q: true, zero: false, unit: '% of GDP', note: 'calculated from NESDC’s current-price levels' });
    capu();
  };

  dash.onData(() => { heat(); J.redrawMfg(); });
})();
