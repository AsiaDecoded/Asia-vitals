// Malaysia dashboard: CPI and PPI (DOSM), all figures as published.

const MY_MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

dash.calc('cpi_series', {
  title: 'CPI series',
  description: 'Every DOSM CPI row (all items, core, divisions) with its cells read as numbers.',
  inputs: ['my_cpi'],
  fn: (my_cpi) => {
    const n = (v) => (v === '' || v == null ? null : Number(v));
    return my_cpi.map((r) => ({ date: r.date, series: r.series, label: r.label, order: Number(r.order), index: n(r.index), yoy: n(r.yoy), mom: n(r.mom) }));
  },
});

dash.calc('ppi_series', {
  title: 'PPI series',
  description: 'Every DOSM PPI row (total and sections) with its cells read as numbers.',
  inputs: ['my_ppi'],
  fn: (my_ppi) => {
    const n = (v) => (v === '' || v == null ? null : Number(v));
    return my_ppi.map((r) => ({ date: r.date, series: r.series, label: r.label, index: n(r.index), yoy: n(r.yoy), mom: n(r.mom), index_sa: n(r.index_sa), mom_sa: n(r.mom_sa) }));
  },
});

dash.calc('cpi_latest', {
  title: 'Latest month and the one before',
  description: 'DOSM published y/y for all-items CPI, core CPI and food and beverages in the latest month and the month before.',
  inputs: ['cpi_series'],
  fn: (cpi_series) => {
    const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    const last = cpi_series.filter((r) => r.series === 'overall' && r.yoy != null).reduce((m, r) => (r.date > m ? r.date : m), '');
    const y = Number(last.slice(0, 4)), mo = Number(last.slice(5, 7));
    const prev = mo === 1 ? `${y - 1}-12-01` : `${y}-${String(mo - 1).padStart(2, '0')}-01`;
    const get = (d, s) => { const r = cpi_series.find((x) => x.date === d && x.series === s); return r ? r.yoy : null; };
    const row = { date: last, prev_date: prev, month: `${MONTHS[mo - 1]} ${y}` };
    [['cpi', 'overall'], ['core', 'core_overall'], ['food', '01']].forEach(([k, s]) => { row[`${k}_yoy`] = get(last, s); row[`${k}_yoy_prev`] = get(prev, s); });
    return [row];
  },
});

dash.calc('ppi_latest', {
  title: 'Latest PPI',
  description: 'DOSM published PPI y/y and seasonally adjusted m/m in the latest month and the month before.',
  inputs: ['ppi_series'],
  fn: (ppi_series) => {
    const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const t = ppi_series.filter((r) => r.series === 'total' && r.yoy != null).sort((a, b) => (a.date < b.date ? -1 : 1)).slice(-2);
    const [p, c] = t.length === 2 ? t : [null, t[0]];
    return [{ ppi_month: c ? `${MON[+c.date.slice(5, 7) - 1]} ${c.date.slice(0, 4)}` : '', ppi_yoy: c ? c.yoy : null, ppi_yoy_prev: p ? p.yoy : null,
      ppi_mom_sa: c ? c.mom_sa : null, ppi_mom_sa_prev: p ? p.mom_sa : null }];
  },
});

dash.calc('div_heat', {
  title: 'CPI inflation by division, y/y',
  description: 'DOSM published y/y for all-items CPI, core CPI and the 13 divisions, latest 12 months.',
  inputs: ['cpi_series'],
  fn: (cpi_series) => {
    const keep = (s) => s === 'overall' || s === 'core_overall' || /^\d\d$/.test(s);
    const dates = Array.from(new Set(cpi_series.filter((r) => r.series === 'overall' && r.yoy != null).map((r) => r.date))).sort().slice(-12);
    return cpi_series.filter((r) => keep(r.series) && r.yoy != null && dates.includes(r.date))
      .map((r) => ({ date: r.date, code: r.series, name: r.series === 'overall' ? 'CPI' : r.series === 'core_overall' ? 'Core CPI' : r.label, yoy: r.yoy,
        order: r.series === 'overall' ? 0 : r.series === 'core_overall' ? 1 : 2 + Number(r.series) }));
  },
});

dash.calc('ppi_cpi', {
  title: 'Producer and consumer price inflation',
  description: 'DOSM published PPI y/y (local production) and all-items CPI y/y, from the first month with a published PPI y/y.',
  inputs: ['ppi_series', 'cpi_series'],
  fn: (ppi_series, cpi_series) => {
    const p = ppi_series.filter((r) => r.series === 'total' && r.yoy != null).map((r) => ({ date: r.date, series: 'ppi', yoy: r.yoy }));
    const first = p.length ? p.reduce((m, r) => (r.date < m ? r.date : m), p[0].date) : '9999';
    const c = cpi_series.filter((r) => r.series === 'overall' && r.yoy != null && r.date >= first).map((r) => ({ date: r.date, series: 'cpi', yoy: r.yoy }));
    return p.concat(c);
  },
});

dash.calc('cpi_measures', {
  title: 'CPI, core and food, y/y',
  description: 'DOSM published y/y for all-items CPI, core CPI and food and beverages, from the first month with a published core y/y.',
  inputs: ['cpi_series'],
  fn: (cpi_series) => {
    const first = cpi_series.filter((r) => r.series === 'core_overall' && r.yoy != null).reduce((m, r) => (r.date < m ? r.date : m), '9999');
    const name = { overall: 'cpi', core_overall: 'core', '01': 'food' };
    return cpi_series.filter((r) => name[r.series] && r.yoy != null && r.date >= first).map((r) => ({ date: r.date, series: name[r.series], yoy: r.yoy }));
  },
});

dash.calc('ppi_sectors', {
  title: 'PPI by sector, y/y',
  description: 'DOSM published PPI y/y for the total and its five sections.',
  inputs: ['ppi_series'],
  fn: (ppi_series) => ppi_series.filter((r) => r.yoy != null).map((r) => ({ date: r.date, series: r.series, yoy: r.yoy })),
});

dash.calc('cpi_long_m', {
  title: 'All-items CPI y/y, monthly',
  description: 'DOSM published all-items CPI y/y, monthly, from January 1981.',
  inputs: ['cpi_series'],
  fn: (cpi_series) => cpi_series.filter((r) => r.series === 'overall' && r.yoy != null).map((r) => ({ date: r.date, yoy: r.yoy })),
});

dash.calc('cpi_long_a', {
  title: 'All-items CPI y/y, annual',
  description: 'DOSM published annual all-items CPI inflation (change in the annual average), from 1961.',
  inputs: ['my_cpi_annual'],
  fn: (my_cpi_annual) => my_cpi_annual.filter((r) => r.series === 'overall' && r.yoy !== '' && r.yoy != null).map((r) => ({ year: r.year, yoy: Number(r.yoy) })),
});

(() => {
  const J = window.JG;
  J.theme();
  J.addSliders(() => { J.redrawCpi(); if (J.redrawFx) J.redrawFx(); });
  dash.onData(() => J.theme());
  const MON = MY_MON;
  const mLabel = (d) => (d ? MON[+d.slice(5, 7) - 1] + ' ' + d.slice(0, 4) : '');
  const failed = (st) => st === 'error' || st === 'connect' || st === 'declined';
  const visible = () => !document.getElementById('inflation').hidden;
  const f1 = (v) => (v == null ? '—' : J.f1(v));
  const pct = (v) => (v == null ? 'n/a' : J.f1(v) + '%');
  const fmt0 = (v) => d3.format('.0f')(v);
  const win = (rows, id) => J.slice(rows, id);

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
    svg.selectAll('g.tick text').each(function () {
      const t = this, g = t.parentNode, m = /translate\(([-\d.]+)/.exec(g.getAttribute('transform') || '');
      if (!m || g.parentNode.getAttribute('transform') !== `translate(0,${H - 20})`) return;
      const px = Number(m[1]), w = t.getComputedTextLength();
      if (px + w / 2 > W - 2) t.setAttribute('text-anchor', 'end');
      else if (px - w / 2 < 2) t.setAttribute('text-anchor', 'start');
    });
    return { svg, x, y, W, ml };
  }

  function hover(svg, card, x, rows, H, ml, right, onMove, label) {
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
        J.showTip(card, tip, label ? label(r) : mLabel(r.date), onMove(r, px, extras), ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); extras.forEach((d) => d.attr('display', 'none')); tip.style.display = 'none'; });
    return extras;
  }

  // Line chart of one measure for several series; months a series lacks are gaps.
  function lines(cardId, dsId, field, series, H, anyStart) {
    const box = document.getElementById(cardId + '-chart');
    const D = dash.data(dsId);
    legend(cardId + '-legend', series);
    if (failed(D.status)) { box.classList.remove('dash-skeleton'); J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); box.classList.add('dash-skeleton'); return; }
    box.classList.remove('dash-skeleton');
    const all = wide(D.data, field);
    const start = all.findIndex((r) => (anyStart ? series.some((s) => r[s.key] != null) : series.every((s) => r[s.key] != null)));
    let end = all.length;
    while (end > 0 && series.every((s) => all[end - 1][s.key] == null)) end -= 1;
    const rows = start < 0 ? [] : win(all.slice(start, end), cardId);
    if (!rows.length) { box.replaceChildren(); return; }
    const mr = 8;
    const { svg, x, y, W, ml } = frame(box, rows, H, rows.flatMap((r) => series.map((s) => r[s.key])).filter((v) => v != null), fmt0, true, mr);
    series.forEach((s) => {
      svg.append('path').attr('d', d3.line().defined((r) => r[s.key] != null).x((r) => x(J.date(r.date))).y((r) => y(r[s.key]))(rows))
        .attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', s.thin ? 1.75 : 2.5).attr('stroke-linecap', s.dash ? 'butt' : 'round').attr('stroke-linejoin', 'round')
        .attr('stroke-dasharray', s.dash ? '6 4' : null);
    });
    const card = document.getElementById(cardId);
    const dots = series.map((s) => svg.append('circle').attr('r', 3.5).attr('fill', s.color).attr('display', 'none'));
    const extras = hover(svg, card, x, rows, H, ml, W - mr, (r, px) => {
      dots.forEach((d, i) => { const v = r[series[i].key]; d.attr('display', v == null ? 'none' : null).attr('cx', px).attr('cy', v == null ? 0 : y(v)); });
      return series.map((s) => [s.color, s.name, pct(r[s.key])]);
    });
    extras.push(...dots);
  }

  // PPI y/y (line, left axis) and seasonally adjusted m/m (bars, right axis), both as published, zero lines aligned.
  function ymChart() {
    const cardId = 'ppi-ym', box = document.getElementById(cardId + '-chart');
    const D = dash.data('ppi_series');
    const series = [
      { key: 'yoy', name: 'y/y (left axis)', color: 'var(--ad-c1)' },
      { key: 'mom', name: 'm/m, seasonally adjusted (right axis)', color: 'var(--ad-c5)', bar: true },
    ];
    legend(cardId + '-legend', series);
    if (failed(D.status)) { box.classList.remove('dash-skeleton'); J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); box.classList.add('dash-skeleton'); return; }
    box.classList.remove('dash-skeleton');
    let rows = D.data.filter((r) => r.series === 'total' && r.mom_sa != null).map((r) => ({ date: r.date, yoy: r.yoy, mom: r.mom_sa }))
      .sort((a, b) => (a.date < b.date ? -1 : 1));
    rows = win(rows, cardId);
    if (!rows.length) { box.replaceChildren(); return; }
    const W = box.clientWidth, H = 280;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const yv = rows.map((r) => r.yoy).filter((v) => v != null), mv = rows.map((r) => r.mom).filter((v) => v != null);
    const ext = (v) => [Math.min(0, d3.min(v) ?? 0), Math.max(0, d3.max(v) ?? 0)];
    const [ylo, yhi] = ext(yv), [mlo, mhi] = ext(mv);
    const k = mv.length ? Math.max(Math.abs(ylo), yhi, 0.1) / Math.max(Math.abs(mlo), mhi, 0.05) : 1;
    const y = d3.scaleLinear([Math.min(ylo, mlo * k), Math.max(yhi, mhi * k)], [H - 24, 10]).nice();
    const yR = d3.scaleLinear(y.domain().map((v) => v / k), y.range());
    const ticks = y.ticks(5), rticks = yR.ticks(5);
    const rfmt = d3.format(rticks.some((v) => !Number.isInteger(v)) ? '.1f' : '.0f');
    const ml = J.textWidth(svg, ticks.map(fmt0)) + 10;
    const mr = J.textWidth(svg, rticks.map(rfmt)) + 10;
    const x = d3.scaleBand(rows.map((r) => r.date), [ml, W - mr]).padding(0.2);
    const cx = (d) => x(d) + x.bandwidth() / 2;
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - mr).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt0)));
    J.axisStyle(svg.append('g').attr('transform', `translate(${W - mr + 4},0)`).call(d3.axisRight(yR).tickValues(rticks).tickSize(0).tickFormat(rfmt)));
    const years = Array.from(new Set(rows.map((r) => r.date.slice(0, 4))));
    const nMonths = rows.length;
    if (nMonths <= 24) {
      const room = Math.max(1, Math.floor((W - ml - mr) / 52));
      const mstep = [1, 2, 3, 6].find((s) => nMonths / s <= room) || 6;
      const xt = rows.map((r) => r.date).filter((d, i) => i % mstep === 0);
      J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).tickValues(xt).tickSize(0).tickFormat((d) => `${MON[+d.slice(5, 7) - 1]} ${d.slice(2, 4)}`)));
    } else {
      const step = [1, 2, 5, 10].find((n) => years.length / n <= Math.max(1, (W - ml - mr) / 56)) || 10;
      const xt = rows.map((r) => r.date).filter((d) => d.slice(5, 7) === '01' && +d.slice(0, 4) % step === 0);
      J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).tickValues(xt).tickSize(0).tickFormat((d) => d.slice(0, 4))));
    }
    svg.append('g').selectAll('rect').data(rows.filter((r) => r.mom != null)).join('rect')
      .attr('x', (r) => x(r.date)).attr('width', x.bandwidth())
      .attr('y', (r) => yR(Math.max(0, r.mom))).attr('height', (r) => Math.max(0.5, Math.abs(yR(r.mom) - yR(0))))
      .attr('fill', series[1].color);
    svg.append('path').attr('d', d3.line().defined((r) => r.yoy != null).x((r) => cx(r.date)).y((r) => y(r.yoy))(rows))
      .attr('fill', 'none').attr('stroke', series[0].color).attr('stroke-width', 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    const card = document.getElementById(cardId), tip = J.tip(card);
    const rule = svg.append('line').attr('y1', 8).attr('y2', H - 22).attr('stroke', 'var(--cds-chart-reference)').attr('display', 'none');
    const dot = svg.append('circle').attr('r', 3.5).attr('fill', series[0].color).attr('display', 'none');
    svg.append('rect').attr('x', ml).attr('width', Math.max(0, W - ml - mr)).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const i = Math.max(0, Math.min(rows.length - 1, Math.floor((d3.pointer(ev)[0] - ml) / x.step())));
        const r = rows[i], px = cx(r.date);
        rule.attr('display', null).attr('x1', px).attr('x2', px);
        if (r.yoy == null) dot.attr('display', 'none'); else dot.attr('display', null).attr('cx', px).attr('cy', y(r.yoy));
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, mLabel(r.date), [[series[0].color, 'y/y', pct(r.yoy)], [series[1].color, 'm/m, seasonally adjusted', pct(r.mom)]], ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); dot.attr('display', 'none'); tip.style.display = 'none'; });
  }

  // Long-term all-items y/y: monthly (date) or annual (year).
  function longChart(cardId, dsId, annual) {
    const box = document.getElementById(cardId + '-chart');
    const D = dash.data(dsId);
    if (failed(D.status)) { box.classList.remove('dash-skeleton'); J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); box.classList.add('dash-skeleton'); return; }
    box.classList.remove('dash-skeleton');
    const all = D.data.map((r) => ({ date: annual ? `${r.year}-01-01` : r.date, label: annual ? String(r.year) : mLabel(r.date), v: r.yoy }))
      .sort((p, q) => (p.date < q.date ? -1 : 1));
    const rows = win(all, cardId);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280, mr = 8, color = 'var(--ad-c2)';
    const { svg, x, y, W, ml } = frame(box, rows, H, rows.map((r) => r.v), fmt0, true, mr);
    svg.append('path').attr('d', d3.line().x((r) => x(J.date(r.date))).y((r) => y(r.v))(rows))
      .attr('fill', 'none').attr('stroke', color).attr('stroke-width', annual ? 2.5 : 1.75).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    const card = document.getElementById(cardId);
    const dot = svg.append('circle').attr('r', 3.5).attr('fill', color).attr('display', 'none');
    const extras = hover(svg, card, x, rows, H, ml, W - mr, (r, px) => {
      dot.attr('display', null).attr('cx', px).attr('cy', y(r.v));
      return [[null, 'y/y', pct(r.v)]];
    }, (r) => r.label);
    extras.push(dot);
  }

  function takeaway() {
    const p = document.getElementById('cpi-takeaway');
    const L = dash.data('cpi_latest');
    if (L.status !== 'ok' || !L.data.length) { if (failed(L.status)) p.replaceChildren(); return; }
    const a = L.data[0];
    const mk = (field) => { const b = document.createElement('b'); b.dataset.source = 'cpi_latest'; b.dataset.field = field; b.dataset.row = '0'; b.textContent = J.f1(a[field]) + '%'; return b; };
    const t = (x) => p.append(document.createTextNode(x));
    p.replaceChildren();
    t(`In ${mLabel(a.date)}, consumer prices were `); p.append(mk('cpi_yoy')); t(' higher than a year earlier, against ');
    p.append(mk('cpi_yoy_prev')); t(` in ${mLabel(a.prev_date)}. Core inflation was `); p.append(mk('core_yoy'));
    t(' and food and beverages '); p.append(mk('food_yoy')); t('.');
  }

  function tiles() {
    const hm = document.getElementById('cpi-month');
    document.querySelectorAll('#cpi-headline [data-source], #cpi-month').forEach((el) => {
      const L = dash.data(el.dataset.source);
      if (L.status !== 'ok' || !L.data.length) { el.textContent = '—'; return; }
      el.classList.remove('dash-skeleton');
      const v = L.data[0][el.dataset.field];
      el.textContent = el === hm || el.dataset.text != null ? (v || '') : f1(v);
    });
  }

  // Division heat table: published y/y, each row coloured on its own range (green lowest, red highest).
  function divHeat() {
    const tbl = document.getElementById('div-heat-table');
    const D = dash.data('div_heat');
    if (failed(D.status)) { tbl.replaceChildren(); return; }
    if (D.status !== 'ok') return;
    const dates = Array.from(new Set(D.data.map((r) => r.date))).sort();
    const codes = Array.from(new Set(D.data.map((r) => r.code))).sort((p, q) => {
      const o = (c) => (D.data.find((r) => r.code === c) || {}).order;
      return o(p) - o(q);
    });
    const val = new Map(D.data.map((r) => [`${r.code}|${r.date}`, r]));
    const STOPS = [[0, [99, 190, 123]], [0.5, [255, 235, 132]], [1, [248, 105, 107]]];
    const color = (t) => {
      const i = t > 0.5 ? 1 : 0; const [t0, c0] = STOPS[i], [t1, c1] = STOPS[i + 1], f = (t - t0) / (t1 - t0);
      return `rgb(${c0.map((c, k) => Math.round(c + (c1[k] - c) * f)).join(',')})`;
    };
    tbl.replaceChildren();
    const head = tbl.createTHead().insertRow();
    ['Division'].concat(dates.map((d) => `${MON[+d.slice(5, 7) - 1]} ${d.slice(2, 4)}`)).forEach((t) => {
      const th = document.createElement('th'); th.textContent = t; head.appendChild(th);
    });
    const tb = tbl.createTBody();
    codes.forEach((c) => {
      const tr = tb.insertRow();
      tr.insertCell().textContent = (D.data.find((r) => r.code === c) || {}).name || '';
      const vs = dates.map((d) => (val.get(`${c}|${d}`) || {}).yoy).filter((v) => v != null);
      const lo = Math.min(...vs), hi = Math.max(...vs);
      if (c === 'overall' || c === 'core_overall') tr.className = 'lead';
      dates.forEach((d) => {
        const td = tr.insertCell(); const r = val.get(`${c}|${d}`);
        if (!r) return;
        td.textContent = J.f1(r.yoy) === '-0.0' ? '0.0' : J.f1(r.yoy);
        td.className = 'heat';
        td.style.background = color(hi > lo ? (r.yoy - lo) / (hi - lo) : 0.5);
        td.style.color = '#1a1a1a';
      });
    });
  }

  J.redrawCpi = () => {
    if (!visible()) return;
    lines('ppi-cpi', 'ppi_cpi', 'yoy', [
      { key: 'ppi', name: 'PPI', color: 'var(--ad-c1)' },
      { key: 'cpi', name: 'CPI', color: 'var(--ad-c2)' },
    ], 280);
    lines('cpi-measures', 'cpi_measures', 'yoy', [
      { key: 'cpi', name: 'CPI', color: 'var(--ad-c2)' },
      { key: 'food', name: 'Food and beverages', color: 'var(--ad-c5)' },
      { key: 'core', name: 'Core', color: 'var(--ad-c6)' },
    ], 280);
    ymChart();
    lines('ppi-sectors', 'ppi_sectors', 'yoy', [
      { key: 'total', name: 'PPI', color: 'var(--ad-c1)' },
      { key: 'A', name: 'Agriculture', color: 'var(--ad-c6)', thin: true },
      { key: 'B', name: 'Mining', color: 'var(--ad-c4)', thin: true },
      { key: 'C', name: 'Manufacturing', color: 'var(--ad-c3)', thin: true },
      { key: 'D', name: 'Electricity and gas', color: 'var(--ad-c5)', thin: true },
      { key: 'E', name: 'Water', color: 'var(--ad-c7)', thin: true },
    ], 280, true);
    longChart('cpi-long-m', 'cpi_long_m', false);
    longChart('cpi-long-a', 'cpi_long_a', true);
  };

  const tabs = document.querySelectorAll('.jg-tabs [data-tab]');
  const show = (id) => {
    if (!document.getElementById(id)) return;
    tabs.forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === id)));
    document.querySelectorAll('.jg-page').forEach((pg) => { pg.hidden = pg.id !== id; });
    dash.setLink(id);
    if (id === 'inflation') J.redrawCpi();
    if (id === 'financial' && J.redrawFx) J.redrawFx();
  };
  J.show = show;
  tabs.forEach((b) => b.addEventListener('click', () => show(b.dataset.tab)));
  if (['methodology', 'financial'].includes(location.hash.slice(1))) show(location.hash.slice(1));

  dash.onData(() => { tiles(); takeaway(); divHeat(); J.redrawCpi(); });
})();

// Financial tab: Ringgit per US$ (BIS bilateral exchange rates WS_XRU, from national sources), daily, full history, as
// published. Nothing calculated.
(() => {
  const J = window.JG;
  const bad = (D) => D.status === 'error' || D.status === 'connect' || D.status === 'declined';
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const dt = (s) => new Date(Date.UTC(Number(s.slice(0, 4)), Number(s.slice(5, 7)) - 1, Number(s.slice(8, 10)) || 1));
  const dLabel = (s) => `${Number(s.slice(8, 10))} ${MON[Number(s.slice(5, 7)) - 1]} ${s.slice(0, 4)}`;
  const vis = () => { const p = document.getElementById('financial'); return p && !p.hidden; };

  function dailyChart() {
    const box = document.getElementById('fx-daily-chart');
    const D = dash.data('my_fx_daily');
    if (bad(D)) { J.fail(box); return; }
    if (D.status !== 'ok' || !D.data.length) { box.replaceChildren(); return; }
    let rows = D.data.map((r) => ({ date: String(r.date), v: Number(r.rate) })).filter((r) => r.v > 0 && r.date)
      .sort((a, b) => (a.date < b.date ? -1 : 1));
    rows = J.slice(rows, 'fx-daily');
    if (!rows.length) { box.replaceChildren(); return; }
    rows.forEach((r) => { r.t = dt(r.date); });
    const H = 300, W = box.clientWidth;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const y = d3.scaleLinear([0, d3.max(rows, (r) => r.v)], [H - 24, 10]).nice();
    const ticks = y.ticks(5), tf = y.tickFormat(5);
    const ml = J.textWidth(svg, ticks.map(tf)) + 10;
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - 8).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(tf)));
    const x = d3.scaleUtc([rows[0].t, rows[rows.length - 1].t], [ml, W - 8]);
    const span = (rows[rows.length - 1].t - rows[0].t) / (365.25 * 864e5);
    const room = Math.max(1, Math.floor((W - ml - 8) / 56));
    if (span < 2) {
      J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`)
        .call(d3.axisBottom(x).ticks(Math.max(2, room)).tickSize(0).tickFormat(d3.utcFormat('%b %y'))));
    } else {
      const step = [1, 2, 5, 10, 20].find((s) => span / s <= room) || 20;
      J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`)
        .call(d3.axisBottom(x).ticks(d3.utcYear.every(step)).tickSize(0).tickFormat(d3.utcFormat('%Y'))));
    }
    svg.append('path').attr('d', d3.line().x((r) => x(r.t)).y((r) => y(r.v))(rows))
      .attr('fill', 'none').attr('stroke', '#BD1B21').attr('stroke-width', 1.4).attr('stroke-linejoin', 'round');
    const card = document.getElementById('fx-daily'), tip = J.tip(card);
    const rule = svg.append('line').attr('y1', 10).attr('y2', H - 24).attr('stroke', 'var(--cds-chart-reference)').attr('display', 'none');
    const dot = svg.append('circle').attr('r', 3.5).attr('fill', '#BD1B21').attr('display', 'none');
    const bis = d3.bisector((r) => r.t).center;
    const vf = d3.format('.4f');
    svg.append('rect').attr('x', ml).attr('width', Math.max(0, W - 8 - ml)).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const r = rows[bis(rows, x.invert(d3.pointer(ev)[0]))]; if (!r) return;
        const px = x(r.t);
        rule.attr('display', null).attr('x1', px).attr('x2', px);
        dot.attr('display', null).attr('cx', px).attr('cy', y(r.v));
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, dLabel(r.date), [['#BD1B21', 'Ringgit per US$', vf(r.v)]], ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); dot.attr('display', 'none'); tip.style.display = 'none'; });
  }

  J.redrawFx = () => { if (vis()) dailyChart(); };
  dash.onData(() => J.redrawFx());
  J.redrawFx();
})();
