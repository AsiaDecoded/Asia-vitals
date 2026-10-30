// Trade tab: BPS merchandise trade and trade price indices, as published (id_trade_bps in AsiaDecoded/asia-vitals).
//   id_trade: monthly exports (FOB) and imports (CIF), US$ million: totals, balance, oil and gas / non-oil and gas,
//     SITC sections (2022 on), imports by use (consumption goods, raw materials, capital goods).
//   id_trade_prices: quarterly export and import price indices, 2023 = 100, with BPS's q/q and y/y (2024 on).

dash.calc('trade_wide', {
  title: 'Trade by month',
  description: 'Monthly trade rows turned into one row per month with a column per series (US$ million, as published).',
  inputs: ['id_trade'],
  fn: (id_trade) => {
    const by = {};
    id_trade.forEach((r) => { (by[r.date] = by[r.date] || { date: r.date })[r.series] = r.value === '' ? null : Number(r.value); });
    return Object.values(by).sort((a, b) => (a.date < b.date ? -1 : 1));
  },
});

dash.calc('trade_latest', {
  title: 'Latest trade month and the one before',
  description: 'Exports, imports and the trade balance in US$ billion (US$ million ÷ 1,000) for the latest month and the month before, and the latest export and import price index y/y.',
  inputs: ['trade_wide', 'id_trade_prices'],
  fn: (trade_wide, id_trade_prices) => {
    const rows = trade_wide.filter((r) => r.exports_total != null);
    const a = rows[rows.length - 1], b = rows[rows.length - 2];
    const bn = (v) => (v == null ? null : v / 1000);
    const pr = (s) => id_trade_prices.filter((r) => r.series === s && r.yoy !== '').sort((x, y) => (x.date < y.date ? -1 : 1));
    const xp = pr('export_total'), mp = pr('import_total');
    return [{
      date: a.date,
      exports_bn: bn(a.exports_total), exports_bn_prev: bn(b.exports_total),
      imports_bn: bn(a.imports_total), imports_bn_prev: bn(b.imports_total),
      balance_bn: bn(a.balance_total), balance_bn_prev: bn(b.balance_total),
      xp_date: xp.length ? xp[xp.length - 1].date : null,
      xp_yoy: xp.length ? Number(xp[xp.length - 1].yoy) : null, xp_yoy_prev: xp.length > 1 ? Number(xp[xp.length - 2].yoy) : null,
      mp_yoy: mp.length ? Number(mp[mp.length - 1].yoy) : null, mp_yoy_prev: mp.length > 1 ? Number(mp[mp.length - 2].yoy) : null,
    }];
  },
});

(() => {
  const J = window.JG;
  J.state.tMix = 'exports'; J.state.tSitc = 'exports';
  const seg = (id, key, attr) => {
    const el = document.getElementById(id); if (!el) return;
    el.addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b) return;
      J.state[key] = b.dataset[attr];
      el.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      J.redrawTrade();
    });
  };
  seg('t-mix-seg', 'tMix', 'f');
  seg('t-sitc-seg', 'tSitc', 'f');
  const bad = (D) => D.status === 'error' || D.status === 'connect' || D.status === 'declined';
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const mlab = (d) => MON[Number(d.slice(5, 7)) - 1] + ' ' + d.slice(0, 4);
  const qlab = (d) => `Q${Math.floor((Number(d.slice(5, 7)) - 1) / 3) + 1} ${d.slice(0, 4)}`;
  const bnf = (v) => (v == null ? '—' : 'US$' + d3.format(',.2f')(v / 1000) + 'bn');
  const SITC = ['Food and live animals', 'Beverages and tobacco', 'Crude materials', 'Mineral fuels', 'Animal and vegetable oils',
    'Chemicals', 'Manufactured goods by material', 'Machinery and transport equipment', 'Miscellaneous manufactures', 'Other'];
  const SITC_COL = ['#92D050', '#C9E3A6', '#A6A6A6', '#495057', '#FFC000', '#954F72', '#1F4E79', '#0C84FF', '#EE6631', '#D9D9D9'];

  function tiles() {
    const L = dash.data('trade_latest');
    document.querySelectorAll('#t-headline [data-source="trade_latest"]').forEach((s) => {
      if (L.status === 'ok' && L.data.length) {
        s.classList.remove('dash-skeleton');
        const v = L.data[0][s.dataset.field];
        s.textContent = v == null ? '—' : s.dataset.field.includes('yoy') ? J.f1(v) : d3.format('.2f')(v);
      } else if (L.status !== 'loading') { s.classList.remove('dash-skeleton'); s.textContent = '—'; }
    });
    const R = dash.data('trade_release');
    document.querySelectorAll('[data-source="trade_release"][data-field="label"]').forEach((s) => {
      if (R.status === 'ok' && R.data.length) { s.classList.remove('dash-skeleton'); s.textContent = R.data[0].label; }
      else if (R.status !== 'loading') { s.classList.remove('dash-skeleton'); s.textContent = ''; }
    });
    const q = document.getElementById('t-price-q');
    if (q && L.status === 'ok' && L.data.length && L.data[0].xp_date) q.textContent = qlab(L.data[0].xp_date);
  }

  function frame(box, rows, H, vals, fmt, band) {
    const W = box.clientWidth;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const y = d3.scaleLinear([Math.min(0, d3.min(vals)), Math.max(0, d3.max(vals))], [H - 24, 10]).nice();
    const ticks = y.ticks(5);
    const ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - 8).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
    const x = d3.scaleBand(rows.map((r) => r.date), [ml, W - 8]).padding(band);
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(x).tickValues(J.yearTicks(rows.map((r) => r.date), W - ml)).tickSize(0).tickFormat((d) => d.slice(0, 4))));
    return { svg, x, y, W, ml };
  }

  function hover(f, rows, H, cardId, title, lines) {
    const hl = f.svg.append('rect').attr('fill', 'var(--color-fg)').attr('opacity', 0.06).attr('display', 'none');
    const card = document.getElementById(cardId), tip = J.tip(card);
    f.svg.append('rect').attr('x', f.ml).attr('width', f.W - f.ml).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [mx] = d3.pointer(ev);
        const r = rows[Math.max(0, Math.min(rows.length - 1, Math.floor((mx - f.ml) / f.x.step())))];
        hl.attr('display', null).attr('x', f.x(r.date) - f.x.step() * f.x.paddingInner() / 2).attr('width', f.x.step()).attr('height', H - 22);
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, title(r), lines(r), ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { hl.attr('display', 'none'); tip.style.display = 'none'; });
  }

  function legend(id, items) {
    const lg = document.getElementById(id); if (!lg) return;
    lg.replaceChildren();
    items.forEach(([cls, col, txt]) => {
      const sp = document.createElement('span'), m = document.createElement('span'); m.className = cls; m.style.background = col;
      sp.append(m, document.createTextNode(txt)); lg.appendChild(sp);
    });
  }

  function balanceChart() {
    const box = document.getElementById('t-balance-chart');
    const D = dash.data('trade_wide');
    if (bad(D)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    const rows = J.slice(D.data.filter((r) => r.exports_total != null && r.imports_total != null), 't-balance');
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280, bn = (v) => v / 1000;
    const f = frame(box, rows, H, rows.flatMap((r) => [bn(r.exports_total), bn(r.imports_total), bn(r.balance_total || 0)]), d3.format('.0f'), 0.2);
    const cx = (r) => f.x(r.date) + f.x.bandwidth() / 2;
    f.svg.append('g').selectAll('rect').data(rows.filter((r) => r.balance_total != null)).join('rect')
      .attr('x', (r) => f.x(r.date)).attr('width', f.x.bandwidth())
      .attr('y', (r) => f.y(Math.max(0, bn(r.balance_total)))).attr('height', (r) => Math.abs(f.y(bn(r.balance_total)) - f.y(0)))
      .attr('fill', '#A6A6A6');
    [['exports_total', J.PAL[0]], ['imports_total', J.PAL[1]]].forEach(([k, c]) => {
      f.svg.append('path').attr('d', d3.line().x(cx).y((r) => f.y(bn(r[k])))(rows))
        .attr('fill', 'none').attr('stroke', c).attr('stroke-width', 2.5).attr('stroke-linejoin', 'round');
    });
    legend('t-balance-legend', [['ln', J.PAL[0], 'Exports'], ['ln', J.PAL[1], 'Imports'], ['sw', '#A6A6A6', 'Trade balance']]);
    hover(f, rows, H, 't-balance', (r) => mlab(r.date),
      (r) => [[J.PAL[0], 'Exports', bnf(r.exports_total)], [J.PAL[1], 'Imports', bnf(r.imports_total)], ['#A6A6A6', 'Balance', bnf(r.balance_total)]]);
  }

  function stackChart(boxId, cardId, legendId, keys, names, colors, filter) {
    const box = document.getElementById(boxId);
    const D = dash.data('trade_wide');
    if (bad(D)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    const rows = J.slice(D.data.filter((r) => keys.every((k) => r[k] != null) && (!filter || filter(r))), cardId);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280;
    const stack = d3.stack().keys(keys).value((d, k) => d[k] / 1000)(rows);
    const f = frame(box, rows, H, [0, d3.max(stack[stack.length - 1], (d) => d[1])], d3.format('.0f'), 0.15);
    f.svg.append('g').selectAll('g').data(stack).join('g').attr('fill', (s, i) => colors[i])
      .selectAll('rect').data((s) => s).join('rect')
      .attr('x', (d) => f.x(d.data.date)).attr('width', f.x.bandwidth())
      .attr('y', (d) => f.y(d[1])).attr('height', (d) => Math.abs(f.y(d[0]) - f.y(d[1])));
    legend(legendId, keys.map((k, i) => ['sw', colors[i], names[i]]).reverse());
    hover(f, rows, H, cardId, (r) => mlab(r.date), (r) => keys.map((k, i) => [colors[i], names[i], bnf(r[k])]).reverse());
  }

  function mixChart() {
    const fl = J.state.tMix;
    stackChart('t-mix-chart', 't-mix', 't-mix-legend', [`${fl}_nonoilgas`, `${fl}_oilgas`], ['Non-oil and gas', 'Oil and gas'], ['#0C84FF', '#495057']);
  }

  function sitcChart() {
    const fl = J.state.tSitc;
    const keys = SITC.map((_, i) => `${fl}_sitc${i}`);
    stackChart('t-sitc-chart', 't-sitc', 't-sitc-legend', keys, SITC, SITC_COL);
  }

  function useChart() {
    stackChart('t-use-chart', 't-use', 't-use-legend', ['imports_consumer', 'imports_raw', 'imports_capital'],
      ['Consumption goods', 'Raw materials and auxiliary goods', 'Capital goods'], ['#FFC000', '#1F4E79', '#92D050']);
  }

  function priceChart() {
    const box = document.getElementById('t-prices-chart');
    const D = dash.data('id_trade_prices');
    if (bad(D)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    const by = {};
    D.data.forEach((r) => { if (r.yoy !== '') (by[r.date] = by[r.date] || { date: r.date })[r.series] = Number(r.yoy); });
    const rows = Object.values(by).filter((r) => r.export_total != null || r.import_total != null).sort((a, b) => (a.date < b.date ? -1 : 1));
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 260;
    const f = frame(box, rows, H, rows.flatMap((r) => [r.export_total, r.import_total].filter((v) => v != null)), (v) => d3.format('.0f')(v), 0.3);
    const bw = f.x.bandwidth() / 2;
    [['export_total', J.PAL[0], 0], ['import_total', J.PAL[1], 1]].forEach(([k, c, j]) => {
      f.svg.append('g').selectAll('rect').data(rows.filter((r) => r[k] != null)).join('rect')
        .attr('x', (r) => f.x(r.date) + j * bw).attr('width', bw)
        .attr('y', (r) => f.y(Math.max(0, r[k]))).attr('height', (r) => Math.abs(f.y(r[k]) - f.y(0))).attr('fill', c);
    });
    f.svg.selectAll('.tick text').text((d) => qlab(d));
    legend('t-prices-legend', [['sw', J.PAL[0], 'Export prices'], ['sw', J.PAL[1], 'Import prices']]);
    const pc = (v) => (v == null ? '—' : J.f1(v) + '%');
    hover(f, rows, H, 't-prices', (r) => qlab(r.date), (r) => [[J.PAL[0], 'Export prices', pc(r.export_total)], [null, '  oil and gas', pc(r.export_oilgas)],
      [null, '  non-oil and gas', pc(r.export_nonoilgas)], [J.PAL[1], 'Import prices', pc(r.import_total)], [null, '  oil and gas', pc(r.import_oilgas)],
      [null, '  non-oil and gas', pc(r.import_nonoilgas)]]);
  }

  J.redrawTrade = () => {
    const pg = document.getElementById('trade');
    if (!pg || pg.hidden) return;
    balanceChart(); mixChart(); sitcChart(); useChart(); priceChart();
  };
  dash.onData(() => { tiles(); J.redrawTrade(); });
})();
