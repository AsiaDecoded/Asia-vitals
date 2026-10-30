// Fiscal tab: central government budget (APBN) and actual (annual), as % of GDP (id_fiscal_gdp, calculated), and government securities (SBN) outstanding
// (monthly), as published: Ministry of Finance data republished by Bank Indonesia in SEKI tables IV.1-IV.4
// (id_fiscal_seki in AsiaDecoded/asia-vitals). Rp billion in the data; shown in Rp trillion (÷ 1,000).

dash.calc('fiscal_years', {
  title: 'Budget and actual by year',
  description: 'SEKI IV.1-IV.3 rows turned into one row per year and basis (budget, actual) with a column per published item used on the page, Rp billion; plus, for a year with no full-year actual yet, the Ministry of Finance year-to-date outturn for the latest month from its APBN KiTa deck (basis ytd; Rp trillion × 1,000).',
  inputs: ['id_fiscal', 'id_fiscal_monthly'],
  fn: (id_fiscal, id_fiscal_monthly) => {
    const ITEMS = {
      revenue: { rev: 'Pendapatan Negara dan Hibah', tax: 'Penerimaan Perpajakan', pph: 'Pajak Penghasilan (PPh)', ppn: 'Pajak Pertambahan Nilai (PPN)', pbb: 'Pajak Bumi dan Bangunan (PBB)', bphtb: 'Bea Perolehan Hak Atas Tanah dan Bangunan (BPHTB)1', cukai: 'Cukai', othtax: 'Pajak Lainnya', trade: 'Pajak Perdagangan Internasional', pnbp: 'Penerimaan Negara Bukan Pajak', grant: 'Hibah' },
      expenditure: { exp: 'Belanja Negara', central: 'Belanja Pemerintah Pusat', pers: 'Belanja Pegawai', goods: 'Belanja Barang', capex: 'Belanja Modal', interest: 'Pembayaran Bunga Utang', subsidy: 'Subsidi', grantx: 'Belanja Hibah', social: 'Bantuan Sosial', othx: 'Belanja Lainnya', transfer: 'Transfer Ke Daerah dan Dana Desa', suspen: 'Suspen' },
      financing: { balance: 'Surplus / Defisit', financing: 'Pembiayaan Bersih', sbn_net: 'Surat Berharga Negara (Neto)' },
    };
    const out = {};
    id_fiscal.forEach((r) => {
      if (r.basis !== 'budget' && r.basis !== 'actual') return;
      const map = ITEMS[r.table]; if (!map) return;
      const key = Object.keys(map).find((k) => map[k] === r.label_id); if (!key) return;
      const o = (out[r.year + r.basis] = out[r.year + r.basis] || { year: Number(r.year), basis: r.basis, through: null });
      if (!(key in o)) o[key] = r.value === '' ? null : Number(r.value);
    });
    const done = new Set(Object.values(out).filter((o) => o.basis === 'actual').map((o) => o.year));
    const latest = {};
    id_fiscal_monthly.forEach((r) => { const y = Number(r.date.slice(0, 4)); if (!latest[y] || r.date > latest[y].date) latest[y] = r; });
    Object.values(latest).forEach((r) => {
      const y = Number(r.date.slice(0, 4)); if (done.has(y)) return;
      const n = (v) => (v === '' || v == null ? null : Number(v) * 1000);
      out[y + 'ytd'] = { year: y, basis: 'ytd', through: r.date.slice(0, 7), rev: n(r.revenue), exp: n(r.expenditure), balance: n(r.balance) };
    });
    return Object.values(out).sort((a, b) => a.year - b.year || (a.basis < b.basis ? -1 : 1));
  },
});

dash.calc('fiscal_latest', {
  title: 'Latest year, actual and budget',
  description: 'Revenue, expenditure, surplus/deficit and tax revenue, actual and budget, for the latest year with an actual, and the actual a year earlier; Rp trillion (Rp billion ÷ 1,000).',
  inputs: ['fiscal_years'],
  fn: (fiscal_years) => {
    const act = fiscal_years.filter((r) => r.basis === 'actual' && r.rev != null);
    const a = act[act.length - 1], p = act[act.length - 2];
    const b = fiscal_years.find((r) => r.basis === 'budget' && r.year === a.year) || {};
    const t = (v) => (v == null ? null : v / 1000);
    return [{ year: a.year, rev: t(a.rev), rev_prev: t(p.rev), rev_budget: t(b.rev), exp: t(a.exp), exp_prev: t(p.exp), exp_budget: t(b.exp),
      balance: t(a.balance), balance_prev: t(p.balance), balance_budget: t(b.balance), tax: t(a.tax), tax_prev: t(p.tax), tax_budget: t(b.tax) }];
  },
});

dash.calc('sbn_wide', {
  title: 'Government securities by month',
  description: 'SEKI IV.4 rows turned into one row per month: government bonds (Obligasi Negara), treasury bills (SPN), Islamic securities (SBSN) and the holders of government bonds, Rp billion as published.',
  inputs: ['id_sbn'],
  fn: (id_sbn) => {
    const KEY = { 1: 'sun', 2: 'bonds', 10: 'h_govbank', 11: 'h_privbank', 12: 'h_joint', 13: 'h_foreignbank', 14: 'h_regional', 15: 'h_bi', 16: 'h_nonbank', 17: 'h_other', 18: 'spn', 27: 'sbsn' };
    const by = {};
    id_sbn.forEach((r) => { const k = KEY[Number(r.item)]; if (!k) return; (by[r.date] = by[r.date] || { date: r.date })[k] = r.value === '' ? null : Number(r.value); });
    return Object.values(by).sort((a, b) => (a.date < b.date ? -1 : 1));
  },
});

dash.calc('sbn_latest', {
  title: 'Latest SBN month and the month before',
  description: 'Government debt securities (SUN) and Islamic securities (SBSN) outstanding, and Bank Indonesia holdings of government bonds, latest month and the month before, Rp trillion (Rp billion ÷ 1,000).',
  inputs: ['sbn_wide'],
  fn: (sbn_wide) => {
    const rows = sbn_wide.filter((r) => r.sun != null);
    const a = rows[rows.length - 1], b = rows[rows.length - 2];
    const t = (v) => (v == null ? null : v / 1000);
    return [{ date: a.date, sun: t(a.sun), sun_prev: t(b.sun), sbsn: t(a.sbsn), sbsn_prev: t(b.sbsn), h_bi: t(a.h_bi), h_bi_prev: t(b.h_bi) }];
  },
});

(() => {
  const J = window.JG;
  J.state.fBasis = 'actual';
  const segEl = document.getElementById('f-mix-seg');
  if (segEl) segEl.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    J.state.fMix = b.dataset.m;
    segEl.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    J.redrawFiscal();
  });
  J.state.fMix = 'revenue';
  const bad = (D) => D.status === 'error' || D.status === 'connect' || D.status === 'declined';
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const trn = (v) => (v == null ? '—' : 'Rp' + d3.format(',.1f')(v / 1000) + 'trn');
  const REV = [['pph', 'Income tax', '#1F4E79'], ['ppn', 'Value added tax', '#0C84FF'], ['cukai', 'Excise', '#954F72'],
    ['pbb', 'Land and building tax', '#ADB5BD'], ['bphtb', 'Land acquisition duty', '#D9D9D9'], ['othtax', 'Other domestic taxes', '#A6A6A6'],
    ['trade', 'International trade taxes', '#EE6631'], ['pnbp', 'Non-tax revenue', '#FFC000'], ['grant', 'Grants', '#92D050']];
  const EXP = [['pers', 'Personnel', '#1F4E79'], ['goods', 'Goods and services', '#0C84FF'], ['capex', 'Capital', '#92D050'],
    ['interest', 'Interest', '#BD1B21'], ['subsidy', 'Subsidies', '#EE6631'], ['social', 'Social assistance', '#FFC000'],
    ['grantx', 'Grants', '#C9E3A6'], ['othx', 'Other', '#A6A6A6'], ['transfer', 'Transfers to regions and villages', '#954F72']];
  const HOLD = [['h_bi', 'Bank Indonesia', '#BD1B21'], ['h_govbank', 'State banks', '#1F4E79'], ['h_privbank', 'Private domestic banks', '#0C84FF'],
    ['h_foreignbank', 'Foreign banks', '#ADB5BD'], ['h_joint', 'Joint-venture banks', '#D9D9D9'], ['h_regional', 'Regional development banks', '#954F72'],
    ['h_nonbank', 'Non-bank holders (nasabah)', '#FFC000'], ['h_other', 'Other institutions', '#A6A6A6']];

  function tiles() {
    [['fiscal_latest', '#f-headline [data-source="fiscal_latest"]'], ['sbn_latest', '#f-headline [data-source="sbn_latest"]']].forEach(([id, sel]) => {
      const L = dash.data(id);
      document.querySelectorAll(sel).forEach((s) => {
        if (L.status === 'ok' && L.data.length) { s.classList.remove('dash-skeleton'); const v = L.data[0][s.dataset.field]; s.textContent = v == null ? '—' : d3.format(',.1f')(v); }
        else if (L.status !== 'loading') { s.classList.remove('dash-skeleton'); s.textContent = '—'; }
      });
    });
    const L = dash.data('fiscal_latest');
    document.querySelectorAll('.f-year').forEach((s) => { if (L.status === 'ok' && L.data.length) s.textContent = String(L.data[0].year); });
    const S = dash.data('sbn_latest');
    const m = document.getElementById('f-sbn-month');
    if (m && S.status === 'ok' && S.data.length) m.textContent = MON[Number(S.data[0].date.slice(5, 7)) - 1] + ' ' + S.data[0].date.slice(0, 4);
    ['fiscal_release', 'fiscal_monthly_release'].forEach((id) => {
      const R = dash.data(id);
      document.querySelectorAll(`[data-source="${id}"][data-field="label"]`).forEach((s) => {
        if (R.status === 'ok' && R.data.length) { s.classList.remove('dash-skeleton'); s.textContent = R.data[0].label; }
        else if (R.status !== 'loading') { s.classList.remove('dash-skeleton'); s.textContent = ''; }
      });
    });
  }

  function legend(id, items) {
    const lg = document.getElementById(id); if (!lg) return;
    lg.replaceChildren();
    items.forEach(([cls, col, txt]) => {
      const sp = document.createElement('span'), m = document.createElement('span'); m.className = cls; m.style.background = col;
      if (cls === 'dot') { m.style.background = 'var(--color-panel)'; m.style.border = '2px solid var(--ad-ink, var(--color-fg-muted))'; m.style.boxSizing = 'border-box'; }
      sp.append(m, document.createTextNode(txt)); lg.appendChild(sp);
    });
  }

  function frame(box, keys, H, lo, hi, band) {
    const W = box.clientWidth;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const y = d3.scaleLinear([Math.min(0, lo), Math.max(0, hi)], [H - 24, 10]).nice();
    const ticks = y.ticks(5);
    const fmt = d3.format(',.0f');
    const ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - 8).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (v === 0 ? 'var(--ad-axis)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
    const x = d3.scaleBand(keys, [ml, W - 8]).padding(band);
    return { svg, x, y, W, ml };
  }

  function hover(f, rows, key, H, cardId, title, lines) {
    const hl = f.svg.append('rect').attr('fill', 'var(--color-fg)').attr('opacity', 0.06).attr('display', 'none');
    const card = document.getElementById(cardId), tip = J.tip(card);
    f.svg.append('rect').attr('x', f.ml).attr('width', f.W - f.ml).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [mx] = d3.pointer(ev);
        const r = rows[Math.max(0, Math.min(rows.length - 1, Math.floor((mx - f.ml) / f.x.step())))];
        hl.attr('display', null).attr('x', f.x(key(r)) - f.x.step() * f.x.paddingInner() / 2).attr('width', f.x.step()).attr('height', H - 22);
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, title(r), lines(r), ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { hl.attr('display', 'none'); tip.style.display = 'none'; });
  }

  function yearAxis(f, H, rows) {
    const every = Math.max(1, Math.ceil(rows.length / Math.max(1, Math.floor((f.W - f.ml) / 40))));
    J.axisStyle(f.svg.append('g').attr('transform', `translate(0,${H - 20})`)
      .call(d3.axisBottom(f.x).tickValues(rows.map((r) => String(r.year)).filter((_, i) => (rows.length - 1 - i) % every === 0)).tickSize(0)
        .tickFormat((y) => (rows.some((r) => String(r.year) === y && r.basis === 'ytd') ? 'YTD' : y))));
  }

  function balanceChart() {
    const box = document.getElementById('f-balance-chart');
    const D = dash.data('fiscal_years');
    if (bad(D)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    const act = D.data.filter((r) => r.basis === 'actual' && r.rev != null && r.exp != null);
    const done = new Set(act.map((r) => r.year));
    // The Ministry's announced year-to-date outturn for a year with no full-year actual yet: drawn apart, not joined.
    const ytd = D.data.filter((r) => r.basis === 'ytd' && r.rev != null && r.exp != null && !done.has(r.year));
    const rows = act.concat(ytd).sort((a, b) => a.year - b.year);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280, t = (v) => v / 1000;
    const thru = (r) => (r.basis === 'ytd' && r.through ? `${r.year}, Jan–${MON[Number(r.through.slice(5, 7)) - 1]}` : `${r.year}, actual`);
    const vals = rows.flatMap((r) => [t(r.rev), t(r.exp), t(r.balance || 0)]);
    const f = frame(box, rows.map((r) => String(r.year)), H, d3.min(vals), d3.max(vals), 0.25);
    yearAxis(f, H, rows);
    const cx = (r) => f.x(String(r.year)) + f.x.bandwidth() / 2;
    f.svg.append('g').selectAll('rect').data(rows.filter((r) => r.balance != null)).join('rect')
      .attr('x', (r) => f.x(String(r.year))).attr('width', f.x.bandwidth())
      .attr('y', (r) => f.y(Math.max(0, t(r.balance)))).attr('height', (r) => Math.abs(f.y(t(r.balance)) - f.y(0)))
      .attr('fill', (r) => (r.basis === 'ytd' ? 'none' : '#A6A6A6')).attr('stroke', (r) => (r.basis === 'ytd' ? '#A6A6A6' : 'none'))
      .attr('stroke-width', 1.5).attr('stroke-dasharray', (r) => (r.basis === 'ytd' ? '3 2' : null));
    [['rev', '#0C84FF'], ['exp', '#BD1B21']].forEach(([k, c]) => {
      f.svg.append('path').attr('d', d3.line().x(cx).y((r) => f.y(t(r[k])))(act)).attr('fill', 'none').attr('stroke', c).attr('stroke-width', 2.5).attr('stroke-linejoin', 'round');
      f.svg.append('g').selectAll('circle').data(ytd).join('circle').attr('cx', cx).attr('cy', (r) => f.y(t(r[k])))
        .attr('r', 4).attr('fill', 'var(--color-panel)').attr('stroke', c).attr('stroke-width', 2);
    });
    const items = [['ln', '#0C84FF', 'Revenue and grants'], ['ln', '#BD1B21', 'Expenditure'], ['sw', '#A6A6A6', 'Fiscal balance']];
    legend('f-balance-legend', items);
    hover(f, rows, (r) => String(r.year), H, 'f-balance', thru,
      (r) => [['#0C84FF', 'Revenue and grants', trn(r.rev)], ['#BD1B21', 'Expenditure', trn(r.exp)], ['#A6A6A6', 'Fiscal balance', trn(r.balance)]]);
  }

  function gdpChart() {
    const box = document.getElementById('f-balance-gdp-chart');
    const D = dash.data('id_fiscal_gdp');
    if (bad(D)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    const n = (v) => (v === '' || v == null ? null : Number(v));
    const rows = D.data.map((r) => ({ year: Number(r.year), basis: r.basis, through: r.through, rev: n(r.revenue_pct), exp: n(r.expenditure_pct), bal: n(r.balance_pct) }))
      .filter((r) => r.bal != null).sort((a, b) => a.year - b.year);
    if (!rows.length) { box.replaceChildren(); return; }
    const act = rows.filter((r) => r.basis === 'actual');
    const H = 280;
    const vals = rows.flatMap((r) => [r.rev, r.exp, r.bal].filter((v) => v != null));
    const f = frame(box, rows.map((r) => String(r.year)), H, d3.min(vals), d3.max(vals), 0.25);
    yearAxis(f, H, rows);
    const cx = (r) => f.x(String(r.year)) + f.x.bandwidth() / 2;
    f.svg.append('g').selectAll('rect').data(rows).join('rect')
      .attr('x', (r) => f.x(String(r.year))).attr('width', f.x.bandwidth())
      .attr('y', (r) => f.y(Math.max(0, r.bal))).attr('height', (r) => Math.abs(f.y(r.bal) - f.y(0)))
      .attr('fill', (r) => (r.basis === 'ytd' ? 'none' : '#A6A6A6')).attr('stroke', (r) => (r.basis === 'ytd' ? '#A6A6A6' : 'none'))
      .attr('stroke-width', 1.5).attr('stroke-dasharray', (r) => (r.basis === 'ytd' ? '3 2' : null));
    [['rev', '#0C84FF'], ['exp', '#BD1B21']].forEach(([k, c]) => {
      f.svg.append('path').attr('d', d3.line().x(cx).y((r) => f.y(r[k]))(act.filter((r) => r[k] != null))).attr('fill', 'none').attr('stroke', c).attr('stroke-width', 2.5).attr('stroke-linejoin', 'round');
    });
    const ytd = rows.filter((r) => r.basis === 'ytd');
    const items = [['ln', '#0C84FF', 'Revenue and grants'], ['ln', '#BD1B21', 'Expenditure'], ['sw', '#A6A6A6', 'Fiscal balance']];
    const lab = (r) => (r.basis === 'ytd' && r.through ? `${r.year}, Jan–${MON[Number(r.through.slice(5, 7)) - 1]} (Ministry of Finance)` : `${r.year}, actual (calculated)`);
    legend('f-balance-gdp-legend', items);
    const pc = (v) => (v == null ? '—' : J.f1(v) + '%');
    hover(f, rows, (r) => String(r.year), H, 'f-balance-gdp', lab,
      (r) => [['#0C84FF', 'Revenue and grants', pc(r.rev)], ['#BD1B21', 'Expenditure', pc(r.exp)], ['#A6A6A6', 'Fiscal balance', pc(r.bal)]]);
  }

  function budgetChart() {
    const box = document.getElementById('f-budget-chart');
    const D = dash.data('fiscal_years');
    if (bad(D)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    const by = {};
    D.data.forEach((r) => { (by[r.year] = by[r.year] || { year: r.year })[r.basis] = r.balance; });
    const rows = Object.values(by).filter((r) => r.budget != null || r.actual != null).sort((a, b) => a.year - b.year);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 260, t = (v) => v / 1000;
    const vals = rows.flatMap((r) => [r.budget, r.actual].filter((v) => v != null).map(t));
    const f = frame(box, rows.map((r) => String(r.year)), H, d3.min(vals), d3.max(vals), 0.2);
    yearAxis(f, H, rows);
    const bw = f.x.bandwidth() / 2;
    [['budget', '#ADB5BD', 0], ['actual', '#1F4E79', 1]].forEach(([k, c, j]) => {
      f.svg.append('g').selectAll('rect').data(rows.filter((r) => r[k] != null)).join('rect')
        .attr('x', (r) => f.x(String(r.year)) + j * bw).attr('width', bw)
        .attr('y', (r) => f.y(Math.max(0, t(r[k])))).attr('height', (r) => Math.abs(f.y(t(r[k])) - f.y(0))).attr('fill', c);
    });
    legend('f-budget-legend', [['sw', '#ADB5BD', 'Budget (APBN)'], ['sw', '#1F4E79', 'Actual']]);
    hover(f, rows, (r) => String(r.year), H, 'f-budget', (r) => String(r.year), (r) => [['#ADB5BD', 'Budget', trn(r.budget)], ['#1F4E79', 'Actual', trn(r.actual)]]);
  }

  function mixChart() {
    const box = document.getElementById('f-mix-chart');
    const D = dash.data('fiscal_years');
    if (bad(D)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    const parts = J.state.fMix === 'revenue' ? REV : EXP;
    const total = J.state.fMix === 'revenue' ? 'rev' : 'exp';
    const rows = D.data.filter((r) => r.basis === 'actual' && r[total] != null);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 300;
    const stack = d3.stack().keys(parts.map((p) => p[0])).value((d, k) => (d[k] || 0) / 1000).offset(d3.stackOffsetDiverging)(rows);
    const lo = d3.min(stack, (s) => d3.min(s, (d) => d[0])), hi = d3.max(stack, (s) => d3.max(s, (d) => d[1]));
    const f = frame(box, rows.map((r) => String(r.year)), H, lo, hi, 0.2);
    yearAxis(f, H, rows);
    f.svg.append('g').selectAll('g').data(stack).join('g').attr('fill', (s, i) => parts[i][2])
      .selectAll('rect').data((s) => s).join('rect')
      .attr('x', (d) => f.x(String(d.data.year))).attr('width', f.x.bandwidth())
      .attr('y', (d) => f.y(Math.max(d[0], d[1]))).attr('height', (d) => Math.abs(f.y(d[0]) - f.y(d[1])));
    legend('f-mix-legend', parts.slice().reverse().map((p) => ['sw', p[2], p[1]]));
    hover(f, rows, (r) => String(r.year), H, 'f-mix', (r) => `${r.year}, actual`,
      (r) => [[null, J.state.fMix === 'revenue' ? 'Revenue and grants' : 'Expenditure', trn(r[total])]].concat(parts.slice().reverse().map((p) => [p[2], p[1], trn(r[p[0]])])));
  }

  function sbnStack(boxId, cardId, legendId, parts, filter) {
    const box = document.getElementById(boxId);
    const D = dash.data('sbn_wide');
    if (bad(D)) { J.fail(box); return; }
    if (D.status !== 'ok') { box.replaceChildren(); return; }
    let rows = D.data.filter((r) => r[parts[0][0]] != null && (!filter || filter(r)));
    rows = J.slice(rows, cardId);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280;
    const stack = d3.stack().keys(parts.map((p) => p[0])).value((d, k) => (d[k] || 0) / 1000)(rows);
    const f = frame(box, rows.map((r) => r.date), H, 0, d3.max(stack[stack.length - 1], (d) => d[1]), 0.12);
    J.axisStyle(f.svg.append('g').attr('transform', `translate(0,${H - 20})`).call(d3.axisBottom(f.x).tickValues(J.yearTicks(rows.map((r) => r.date), f.W - f.ml)).tickSize(0).tickFormat((d) => d.slice(0, 4))));
    f.svg.append('g').selectAll('g').data(stack).join('g').attr('fill', (s, i) => parts[i][2])
      .selectAll('rect').data((s) => s).join('rect')
      .attr('x', (d) => f.x(d.data.date)).attr('width', f.x.bandwidth())
      .attr('y', (d) => f.y(d[1])).attr('height', (d) => Math.abs(f.y(d[0]) - f.y(d[1])));
    legend(legendId, parts.slice().reverse().map((p) => ['sw', p[2], p[1]]));
    hover(f, rows, (r) => r.date, H, cardId, (r) => MON[Number(r.date.slice(5, 7)) - 1] + ' ' + r.date.slice(0, 4),
      (r) => parts.slice().reverse().map((p) => [p[2], p[1], trn(r[p[0]])]));
  }

  J.redrawFiscal = () => {
    const pg = document.getElementById('fiscal');
    if (!pg || pg.hidden) return;
    balanceChart(); gdpChart(); budgetChart(); mixChart();
    sbnStack('f-sbn-chart', 'f-sbn', 'f-sbn-legend', [['bonds', 'Government bonds (Obligasi Negara)', '#1F4E79'], ['spn', 'Treasury bills (SPN)', '#0C84FF'], ['sbsn', 'Islamic securities (SBSN)', '#92D050']]);
    sbnStack('f-hold-chart', 'f-hold', 'f-hold-legend', HOLD);
  };
  dash.onData(() => { tiles(); J.redrawFiscal(); });
})();
