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
    tiles(); dailyChart(); monthlyChart();
  };
  dash.onData(() => { tiles(); J.redrawFinancial(); });
})();
