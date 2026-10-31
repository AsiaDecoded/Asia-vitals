// Financial tab: rupiah per US dollar (BIS, from national sources), daily from 1988 and monthly from 1967; the Asian
// financial crisis (July 1997 to December 1998) shaded. All as published.
(() => {
  const J = window.JG;
  const bad = (D) => D.status === 'error' || D.status === 'connect' || D.status === 'declined';
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const AFC = ['1997-07-01', '1998-12-31'];
  const fmt = d3.format(',.0f');
  const dt = (s) => new Date(Date.UTC(Number(s.slice(0, 4)), Number(s.slice(5, 7)) - 1, Number(s.slice(8, 10)) || 1));

  function frame(box, lo, hi, H, d0, d1) {
    const W = box.clientWidth;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const y = d3.scaleLinear([lo, hi], [H - 24, 10]).nice();
    const ticks = y.ticks(5);
    const ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - 8).attr('y1', y).attr('y2', y)
      .attr('stroke', 'var(--ad-grid)');
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
    const x = d3.scaleUtc([dt(d0), dt(d1)], [ml, W - 8]);
    const span = (dt(d1) - dt(d0)) / (365.25 * 864e5);
    const step = span > 30 ? 10 : span > 12 ? 5 : span > 5 ? 2 : 1;
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`)
      .call(d3.axisBottom(x).ticks(d3.utcYear.every(step)).tickSize(0).tickFormat(d3.utcFormat('%Y'))));
    return { svg, x, y, W, ml };
  }

  function afc(f, H) {
    const a = Math.max(f.ml, f.x(dt(AFC[0]))), b = Math.min(f.W - 8, f.x(dt(AFC[1])));
    if (b <= a) return;
    f.svg.insert('rect', ':first-child').attr('x', a).attr('width', b - a).attr('y', 10).attr('height', H - 34)
      .attr('fill', '#FFC000').attr('opacity', 0.18);
    f.svg.append('text').attr('x', (a + b) / 2).attr('y', 22).attr('text-anchor', 'middle').attr('font-size', 11)
      .attr('fill', 'var(--color-fg-muted)').text('AFC');
  }

  function hover(f, rows, H, cardId, title, lines) {
    const card = document.getElementById(cardId), tip = J.tip(card);
    const rule = f.svg.append('line').attr('y1', 10).attr('y2', H - 24).attr('stroke', 'var(--color-fg)').attr('opacity', 0.25).attr('display', 'none');
    const bis = d3.bisector((r) => r.t).center;
    f.svg.append('rect').attr('x', f.ml).attr('width', f.W - f.ml).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [mx] = d3.pointer(ev);
        const r = rows[bis(rows, f.x.invert(mx))]; if (!r) return;
        rule.attr('display', null).attr('x1', f.x(r.t)).attr('x2', f.x(r.t));
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, title(r), lines(r), ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); tip.style.display = 'none'; });
  }

  function slice(rows, id) {
    const card = document.getElementById(id);
    if (card && !card.dataset.start) card.dataset.start = '1900-01-01';
    return J.slice(rows, id);
  }

  function dailyChart() {
    const box = document.getElementById('x-daily-chart');
    const D = dash.data('id_fx_daily');
    if (bad(D)) { J.fail(box); return; }
    if (D.status !== 'ok' || !D.data.length) { box.replaceChildren(); return; }
    let rows = D.data.map((r) => ({ date: r.date, v: Number(r.usd_idr) })).filter((r) => r.v > 0);
    rows = slice(rows, 'x-daily');
    rows.forEach((r) => { r.t = dt(r.date); });
    const H = 300;
    const f = frame(box, 0, d3.max(rows, (r) => r.v), H, rows[0].date, rows[rows.length - 1].date);
    afc(f, H);
    f.svg.append('path').attr('d', d3.line().x((r) => f.x(r.t)).y((r) => f.y(r.v))(rows))
      .attr('fill', 'none').attr('stroke', '#BD1B21').attr('stroke-width', 1.4);
    hover(f, rows, H, 'x-daily', (r) => `${Number(r.date.slice(8, 10))} ${MON[Number(r.date.slice(5, 7)) - 1]} ${r.date.slice(0, 4)}`,
      (r) => [['#BD1B21', 'Rupiah per US$', d3.format(',.1f')(r.v)]]);
  }

  function monthlyChart() {
    const box = document.getElementById('x-monthly-chart');
    const D = dash.data('id_fx_monthly');
    if (bad(D)) { J.fail(box); return; }
    if (D.status !== 'ok' || !D.data.length) { box.replaceChildren(); return; }
    let rows = D.data.map((r) => ({ date: r.date, v: Number(r.avg), e: Number(r.eop) })).filter((r) => r.v > 0);
    rows = slice(rows, 'x-monthly');
    rows.forEach((r) => { r.t = dt(r.date); });
    const H = 300;
    const f = frame(box, 0, d3.max(rows, (r) => Math.max(r.v, r.e || 0)), H, rows[0].date, rows[rows.length - 1].date);
    afc(f, H);
    f.svg.append('path').attr('d', d3.line().x((r) => f.x(r.t)).y((r) => f.y(r.v))(rows))
      .attr('fill', 'none').attr('stroke', '#BD1B21').attr('stroke-width', 2);
    hover(f, rows, H, 'x-monthly', (r) => `${MON[Number(r.date.slice(5, 7)) - 1]} ${r.date.slice(0, 4)}`,
      (r) => [['#BD1B21', 'Monthly average', d3.format(',.1f')(r.v)], [null, 'End of month', r.e ? d3.format(',.1f')(r.e) : '—']]);
  }

  // Episodes: rupiah per US$ indexed to 100 on the first trading day of each episode (calculated), three years on;
  // x = months since the start (calendar days / 30.44). Higher = weaker rupiah.
  const EPIS = [['1997-07-02', 'AFC (2 Jul 1997 = 100)', '#BD1B21'], ['2024-10-20', 'Prabowo term (20 Oct 2024 = 100)', '#0C84FF']];
  function episodeChart() {
    const box = document.getElementById('x-epi-chart');
    const D = dash.data('id_fx_daily');
    if (bad(D)) { J.fail(box); return; }
    if (D.status !== 'ok' || !D.data.length) { box.replaceChildren(); return; }
    const all = D.data.map((r) => ({ date: r.date, v: Number(r.usd_idr) })).filter((r) => r.v > 0);
    const ser = EPIS.map(([d0, name, col]) => {
      const i0 = all.findIndex((r) => r.date >= d0); if (i0 < 0) return null;
      const b = all[i0], t0 = dt(b.date), end = new Date(t0); end.setUTCFullYear(end.getUTCFullYear() + 3);
      const pts = all.slice(i0).filter((r) => dt(r.date) <= end)
        .map((r) => ({ date: r.date, v: r.v, idx: (r.v / b.v) * 100, m: (dt(r.date) - t0) / 864e5 / 30.44 }));
      return { d0, base: b, name, col, pts };
    }).filter(Boolean);
    const H = 300, W = box.clientWidth;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const hi = d3.max(ser, (s) => d3.max(s.pts, (p) => p.idx)), lo = d3.min(ser, (s) => d3.min(s.pts, (p) => p.idx));
    const y = d3.scaleLinear([Math.min(90, lo), hi], [H - 24, 10]).nice();
    const ticks = y.ticks(6), ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - 8).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (v === 100 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
    const x = d3.scaleLinear([0, 36], [ml, W - 8]);
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`)
      .call(d3.axisBottom(x).tickValues([0, 6, 12, 18, 24, 30, 36]).tickSize(0).tickFormat((m) => (m === 0 ? 't' : `t+${m}m`))));
    ser.forEach((s) => svg.append('path').attr('d', d3.line().x((p) => x(p.m)).y((p) => y(p.idx))(s.pts))
      .attr('fill', 'none').attr('stroke', s.col).attr('stroke-width', 1.8));
    const lg = document.getElementById('x-epi-legend');
    if (lg) {
      lg.replaceChildren();
      ser.forEach((s) => { const sp = document.createElement('span'), mk = document.createElement('span'); mk.className = 'ln'; mk.style.background = s.col; sp.append(mk, document.createTextNode(s.name)); lg.appendChild(sp); });
    }
    const card = document.getElementById('x-epi'), tip = J.tip(card);
    const rule = svg.append('line').attr('y1', 10).attr('y2', H - 24).attr('stroke', 'var(--color-fg)').attr('opacity', 0.25).attr('display', 'none');
    const bis = d3.bisector((p) => p.m).center;
    const dd = (s) => `${Number(s.slice(8, 10))} ${MON[Number(s.slice(5, 7)) - 1]} ${s.slice(0, 4)}`;
    svg.append('rect').attr('x', ml).attr('width', W - 8 - ml).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [mx] = d3.pointer(ev), m = x.invert(mx);
        rule.attr('display', null).attr('x1', x(m)).attr('x2', x(m));
        const lines = ser.map((s) => {
          const p = s.pts[bis(s.pts, m)];
          return p && Math.abs(p.m - m) < 0.5 ? [s.col, `${s.name.split(' (')[0]}, ${dd(p.date)}`, `${p.idx.toFixed(1)} (Rp${fmt(p.v)})`] : [s.col, s.name.split(' (')[0], '—'];
        });
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, `t + ${m.toFixed(1)} months`, lines, ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); tip.style.display = 'none'; });
  }

  function tiles() {
    const L = dash.data('fx_latest');
    if (L.status !== 'ok' || !L.data.length) return;
    const r = L.data[0];
    const set = (id, v) => { const e = document.getElementById(id); if (e) { e.textContent = v; e.classList.remove('dash-skeleton'); } };
    set('x-latest', d3.format(',.0f')(Number(r.usd_idr)));
    set('x-latest-date', `${Number(r.date.slice(8, 10))} ${MON[Number(r.date.slice(5, 7)) - 1]} ${r.date.slice(0, 4)}`);
    const pc = (v) => (v === '' || v == null ? '—' : (Number(v) > 0 ? '+' : '') + Number(v).toFixed(1));
    set('x-yoy', pc(r.yoy_pct));
    set('x-ytd', pc(r.ytd_pct));
  }

  J.redrawFinancial = () => {
    const pg = document.getElementById('financial');
    if (!pg || pg.hidden) return;
    tiles(); dailyChart(); monthlyChart(); episodeChart();
  };
  dash.onData(() => { tiles(); J.redrawFinancial(); });
})();
