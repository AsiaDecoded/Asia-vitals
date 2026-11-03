// India GDP tab, charts 1-6 (headline tiles to come). Figures as published: MoSPI National Accounts Statistics
// (growth rates, % y/y) and the World Bank's WDI (US$ levels and real growth). The page calculates only the CAGR on
// charts 1 and 2. Quarters are dated at their first calendar month and labelled by calendar months (Apr–Jun 2026 is
// MoSPI's Q1 2026-27); fiscal years (April to March) are dated at April and labelled 2025-26.
// IIP biggest contributors (Manufacturing tab): for each part of the general index (23 NIC 2-digit manufacturing
// divisions, mining, electricity and gas, water and waste), its weight and MoSPI's y/y in the latest month, and the
// average of its contribution to general IIP y/y over the latest 3 and 6 months (contributions calculated in
// in_iip_mospi at MoSPI's 2022-23 weights). As the CPI table.
dash.calc('iip_movers', {
  title: 'IIP contributions, 3- and 6-month averages',
  description: 'For each part of the general IIP (2022-23 base): its weight and MoSPI published y/y in the latest month, and the average of its contribution to general IIP y/y over the latest 3 and 6 months.',
  inputs: ['in_iip_contrib_items'],
  fn: (in_iip_contrib_items) => {
    const n = (v) => (v === '' || v == null ? null : Number(v));
    const months = Array.from(new Set(in_iip_contrib_items.map((r) => r.date))).sort();
    const latest = months[months.length - 1];
    const by = new Map();
    in_iip_contrib_items.forEach((r) => {
      if (!by.has(r.code)) by.set(r.code, {});
      by.get(r.code)[r.date] = { name: r.name, weight: n(r.weight), yoy: n(r.yoy), c: n(r.contribution) };
    });
    const avg = (m, k) => {
      const ms = months.slice(-k);
      if (ms.length < k || ms.some((d) => !m[d] || m[d].c == null)) return null;
      return ms.reduce((a, d) => a + m[d].c, 0) / k;
    };
    const out = [];
    by.forEach((m) => {
      const cur = m[latest]; if (!cur) return;
      out.push({ name: cur.name, date: latest, weight: cur.weight, yoy: cur.yoy, avg3: avg(m, 3), avg6: avg(m, 6) });
    });
    return out;
  },
});

(() => {
  const J = window.JG;
  const visible = () => !document.getElementById('gdp').hidden;
  const failed = (st) => st === 'error' || st === 'connect' || st === 'declined';
  const N = (v) => (v === '' || v == null ? null : Number(v));
  const fyLab = (d) => { const y = Number(d.slice(0, 4)); return `${y}-${String((y + 1) % 100).padStart(2, '0')}`; };
  // Charts 1-2, 5-6: FY and the two-digit year the fiscal year ends in (WDI 2025 = 2025-26 = FY26), at the user's request.
  const fyShort = (d) => `FY${String((Number(d.slice(0, 4)) + 1) % 100).padStart(2, '0')}`;
  const BASE_SWITCH = '2023-04-01';   // annual: MoSPI's 2022-23 base from 2023-24 (2011-12 base before)
  const LMI = 2007;                   // lower-middle income on 2007 GNI per capita (World Bank FY09; data/asia/gni)
  // Charts 4 and 6: series picked from a dropdown (user, 3 Nov 2026), in her order (GDP dropped, user 3 Nov 2026): GVA, agriculture,
  // manufacturing, electricity etc., construction, services (calculated), then the other published industries.
  const PICKS = [
    { code: 'gva', name: 'GVA', color: 'var(--ad-c2)' },
    { code: 'agri', name: 'Agriculture', color: 'var(--ad-c6)', thin: true },
    { code: 'manufacturing', name: 'Manufacturing', color: 'var(--ad-c1)', thin: true },
    { code: 'utilities', name: 'Electricity, gas, water', color: 'var(--ad-c7)', thin: true },
    { code: 'construction', name: 'Construction', color: 'var(--ad-c5)', thin: true },
    // Services (tertiary sector): calculated in the pipeline (in_gdp_mospi) from the three service industries' levels.
    { code: 'services', name: 'Services', color: '#00A3A3', thin: true },
    { code: 'mining', name: 'Mining', color: 'var(--ad-c4)', thin: true },
    { code: 'trade_transport', name: 'Trade, hotels, transport, communication', color: 'var(--ad-c3)', thin: true },
    { code: 'finance_re', name: 'Financial, real estate, professional', color: 'var(--ad-c8)', thin: true },
    { code: 'public_other', name: 'Public administration, defence, other', color: '#1F4E79', thin: true },
  ];
  const DEFAULT = ['gva', 'agri', 'manufacturing', 'construction', 'services'];
  const picked = { 'gdp-sectors': new Set(DEFAULT), 'gdp-annual': new Set(DEFAULT) };
  const SEC = (id) => PICKS.filter((s) => picked[id].has(s.code));
  function picker(id) {
    const host = document.getElementById(id + '-pick'); if (!host || host.dataset.built) return;
    host.dataset.built = '1';
    const det = document.createElement('details'); det.className = 'ad-pick';
    const sum = document.createElement('summary');
    const list = document.createElement('div'); list.className = 'ad-pick-list';
    const label = () => { sum.textContent = 'Sectors'; };
    PICKS.forEach((s) => {
      const row = document.createElement('label'); const cb = document.createElement('input'); cb.type = 'checkbox';
      cb.checked = picked[id].has(s.code);
      cb.addEventListener('change', () => { if (cb.checked) picked[id].add(s.code); else picked[id].delete(s.code); label(); J.redrawGdp(); });
      const sw = document.createElement('span'); sw.className = 'ln';
      sw.style.background = s.dash ? `repeating-linear-gradient(90deg, ${s.color} 0 5px, transparent 5px 8px)` : s.color;
      row.append(cb, sw, document.createTextNode(s.name)); list.appendChild(row);
    });
    const btns = document.createElement('div'); btns.className = 'ad-pick-btns';
    [['All', true], ['None', false]].forEach(([t, on]) => {
      const b = document.createElement('button'); b.type = 'button'; b.textContent = t;
      b.addEventListener('click', () => {
        PICKS.forEach((s) => (on ? picked[id].add(s.code) : picked[id].delete(s.code)));
        list.querySelectorAll('input').forEach((cb) => { cb.checked = on; }); label(); J.redrawGdp();
      });
      btns.appendChild(b);
    });
    const panel = document.createElement('div'); panel.className = 'ad-pick-panel'; panel.append(btns, list);
    label(); det.append(sum, panel); host.appendChild(det);
    document.addEventListener('click', (e) => { if (det.open && !det.contains(e.target)) det.open = false; });
  }
  ['gdp-sectors', 'gdp-annual'].forEach(picker);
  let growthPrice = 'constant', srcPick = 'mospi', usdPick = 'NY.GDP.MKTP.KD', pcPick = 'NY.GDP.PCAP.KD';

  function legend(id, series) {
    const el = document.getElementById(id); if (!el) return;
    el.replaceChildren();
    series.forEach((s) => {
      const span = document.createElement('span'); const ln = document.createElement('span');
      ln.className = s.bar ? 'sw' : 'ln';
      ln.style.background = s.dash ? `repeating-linear-gradient(90deg, ${s.color} 0 5px, transparent 5px 8px)` : s.color;
      span.append(ln, document.createTextNode(s.name)); el.appendChild(span);
    });
  }
  // true when every dataset is loaded; otherwise shows the placeholder or the failure.
  function status(box, ids) {
    const st = ids.map((id) => dash.data(id).status);
    if (st.some(failed)) { box.classList.remove('dash-skeleton'); J.fail(box); return false; }
    if (st.some((s) => s !== 'ok')) { box.replaceChildren(); box.classList.add('dash-skeleton'); return false; }
    box.classList.remove('dash-skeleton');
    return true;
  }
  const gdp = () => dash.data('in_gdp').data;
  // MoSPI growth rows for one industry: [{date, v, base, fy}], sorted.
  function series(freq, code, price = 'constant') {
    return gdp().filter((r) => r.freq === freq && r.code === code && r.measure === 'yoy' && r.price === price)
      .map((r) => ({ date: r.date, v: N(r.value), base: r.base_year, fy: r.fy, fq: r.fq })).filter((r) => r.v != null)
      .sort((a, b) => (a.date < b.date ? -1 : 1));
  }
  function merge(list) {
    const by = new Map();
    list.forEach(({ key, rows }) => rows.forEach((r) => { if (!by.has(r.date)) by.set(r.date, { date: r.date }); by.get(r.date)[key] = r.v; }));
    return Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
  }

  // Axes and grid. xLab(row) labels a point; labels every k-th point counted back from the last (or anchored at `anchor`).
  function frame(box, rows, H, vals, zero, xLab, opt = {}) {
    const W = box.clientWidth, mr = 8, fmt = opt.fmt || ((v) => d3.format(',.0f')(v));
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    let lo = d3.min(vals), hi = d3.max(vals);
    if (zero) { lo = Math.min(0, lo); hi = Math.max(0, hi); }
    const y = d3.scaleLinear([lo, hi], [H - 24, opt.top || 12]).nice();
    const ticks = y.ticks(5);
    const ml = J.textWidth(svg, ticks.map(fmt)) + 10;
    const pad = opt.pad || 0;
    const x = d3.scaleUtc([J.date(rows[0].date), J.date(rows[rows.length - 1].date)], [ml + pad, W - mr - pad]);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', ml).attr('x2', W - mr).attr('y1', y).attr('y2', y)
      .attr('stroke', (v) => (zero && v === 0 ? 'var(--cds-chart-reference)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(${ml - 4},0)`).call(d3.axisLeft(y).tickValues(ticks).tickSize(0).tickFormat(fmt)));
    const lw = opt.labelWidth || 44, room = Math.max(1, Math.floor((W - ml - mr) / lw));
    const step = [1, 2, 4, 5, 10].find((k) => rows.length / k <= room) || 10;
    rows.forEach((r, k) => {
      const lab = xLab(r, k); if (lab == null) return;
      if (opt.anchorEvery ? !opt.anchorEvery(r, step) : (rows.length - 1 - k) % step !== 0) return;
      const px = x(J.date(r.date));
      svg.append('text').attr('x', px).attr('y', H - 20).attr('dy', '0.71em').attr('font-size', 12).attr('fill', 'var(--ad-ink)')
        .attr('text-anchor', px > W - mr - 20 ? 'end' : px < ml + 20 ? 'start' : 'middle').text(lab);
    });
    return { svg, x, y, W, ml, mr };
  }
  function vline(svg, x, date, H, label) {
    const sx = x(J.date(date));
    svg.append('line').attr('x1', sx).attr('x2', sx).attr('y1', label ? 18 : 12).attr('y2', H - 24).attr('stroke', 'var(--ad-axis)').attr('stroke-dasharray', '3 3');
    if (label) svg.append('text').attr('x', sx).attr('y', 12).attr('font-size', 11).attr('fill', 'var(--ad-ink)').attr('text-anchor', 'middle').text(label);
  }
  function hover(svg, card, x, rows, H, ml, right, head, onMove) {
    const tip = J.tip(card);
    const rule = svg.append('line').attr('y1', 8).attr('y2', H - 22).attr('stroke', 'var(--cds-chart-reference)').attr('display', 'none');
    const bis = d3.bisector((r) => J.date(r.date)).center;
    const extras = [];
    svg.append('rect').attr('x', ml).attr('width', Math.max(0, right - ml)).attr('height', H).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [mx] = d3.pointer(ev); const r = rows[bis(rows, x.invert(mx))]; if (!r) return;
        const px = x(J.date(r.date));
        rule.attr('display', null).attr('x1', px).attr('x2', px);
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, head(r), onMove(r, px, extras), ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { rule.attr('display', 'none'); extras.forEach((d) => d.attr('display', 'none')); tip.style.display = 'none'; });
    return extras;
  }
  function drawLines(svg, x, y, rows, S) {
    S.forEach((s) => svg.append('path').attr('d', d3.line().defined((r) => r[s.key] != null).x((r) => x(J.date(r.date))).y((r) => y(r[s.key]))(rows))
      .attr('fill', 'none').attr('stroke', s.color).attr('stroke-width', s.thin ? 1.75 : 2.5).attr('stroke-linecap', s.dash ? 'butt' : 'round')
      .attr('stroke-linejoin', 'round').attr('stroke-dasharray', s.dash ? '6 4' : null));
    return S.map((s) => svg.append('circle').attr('r', 3.5).attr('fill', s.color).attr('display', 'none'));
  }
  const qAxis = (r) => (r.date.slice(5, 7) === '01' ? r.date.slice(0, 4) : null);
  const qAnchor = (r) => r.date.slice(5, 7) === '01';
  const pct = (v) => (v == null ? 'n/a' : v.toFixed(1) + '%');

  // Charts 1 and 2: GDP and GDP per capita in US dollars, World Bank WDI, as published (GDP in US$ billion, the World
  // Bank's US$ / 1e9). Real: constant 2015 US$. Nominal: current US$; Chart 2 also GNI per capita, Atlas method, from the
  // central dataset (data/asia/gni/asia_gni_pc.csv). WDI's India years are fiscal years, labelled by their first year.
  const USD = {
    'gdp-usd': { div: 1e9, unit: 'US$ billion', tipUnit: ' bn', fmt: ',.1f',
      real: [{ key: 'NY.GDP.MKTP.KD', name: 'GDP', color: 'var(--ad-c2)' }],
      // GNI, Atlas method (total): from the central dataset asia_gni_atlas (data/asia/gni/asia_gni_atlas.csv: economy,
      // name, year, gni_atlas in US$), once the main chat adds it; until then Chart 1 Nominal shows GDP only.
      nominal: [{ key: 'NY.GDP.MKTP.CD', name: 'GDP', color: 'var(--ad-c2)' },
        { key: 'gni_atlas', name: 'GNI, Atlas method', color: 'var(--ad-c1)', ds: 'asia_gni_atlas', field: 'gni_atlas', optional: true }] },
    'gdp-pc': { div: 1, unit: 'US$', tipUnit: '', fmt: ',.0f',
      real: [{ key: 'NY.GDP.PCAP.KD', name: 'GDP per capita', color: 'var(--ad-c2)' }],
      nominal: [{ key: 'NY.GDP.PCAP.CD', name: 'GDP per capita', color: 'var(--ad-c2)' },
        { key: 'gni_pc', name: 'GNI per capita, Atlas method', color: 'var(--ad-c1)', ds: 'asia_gni_pc', field: 'gni_pc' }] },
  };
  function usd(id, pick) {
    const C = USD[id], box = document.getElementById(id + '-chart'), nominal = /\.CD$/.test(pick);
    // An optional series is drawn only once its dataset exists and has loaded.
    const S = (nominal ? C.nominal : C.real).filter((s) => !s.optional || dash.data(s.ds).status === 'ok');
    document.getElementById(id + '-units').textContent = `${C.unit}, ${nominal ? 'current prices' : 'constant 2015 prices'}`;
    legend(id + '-legend', S.length > 1 ? S : []);
    const ids = ['in_gdp_intl'].concat(S.filter((s) => s.ds).map((s) => s.ds));
    if (!status(box, ids)) return;
    const by = new Map();
    const put = (date, k, v) => { if (v == null) return; if (!by.has(date)) by.set(date, { date }); by.get(date)[k] = v; };
    dash.data('in_gdp_intl').data.forEach((r) => { if (S.some((s) => s.key === r.series)) put(r.date, r.series, N(r.value) / C.div); });
    S.filter((s) => s.ds).forEach((s) => dash.data(s.ds).data.filter((r) => r.economy === 'IN')
      .forEach((r) => put(`${r.year}-04-01`, s.key, N(r[s.field]) == null ? null : N(r[s.field]) / C.div)));
    const rows = Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280;
    const yr = (r) => Number(r.date.slice(0, 4));
    const { svg, x, y, W, ml, mr } = frame(box, rows, H, rows.flatMap((r) => S.map((s) => r[s.key])).filter((v) => v != null).concat([0]), true,
      (r) => fyShort(r.date), { anchorEvery: (r, k) => ((yr(r) - LMI) % k + k) % k === 0, labelWidth: 44, top: 24 });
    if (yr(rows[0]) < LMI) vline(svg, x, `${LMI}-04-01`, H, 'Lower-middle income');
    // CAGR, calculated on this page: (latest value / value in the lower-middle-income year)^(1 / years) - 1, per series shown.
    const at = (k) => rows.find((r) => yr(r) === k);
    const cagr = S.map((s) => {
      const have = rows.filter((r) => r[s.key] != null); if (!have.length) return null;
      const END = yr(have[have.length - 1]), a0 = at(LMI), a1 = at(END);
      return a0 && a1 && a0[s.key] > 0 ? { s, END, v: (Math.pow(a1[s.key] / a0[s.key], 1 / (END - LMI)) - 1) * 100 } : null;
    }).filter(Boolean);
    if (cagr.length) {
      const lh = 16, tx = W - mr - 8, ty = H - 40 - (cagr.length - 1) * lh;
      const t = svg.append('text').attr('font-size', 12).attr('font-weight', 700).attr('fill', 'var(--ad-ink)').attr('text-anchor', 'end');
      cagr.forEach((c, k) => t.append('tspan').attr('x', tx).attr('dy', k ? lh : 0).attr('fill', S.length > 1 ? c.s.color : null)
        .text(`${fyShort(`${LMI}-04-01`)}–${fyShort(`${c.END}-04-01`)} CAGR: ${c.v.toFixed(1)}% p.a.`));
      t.attr('x', tx).attr('y', ty);
    }
    const dots = drawLines(svg, x, y, rows, S);
    const extras = hover(svg, document.getElementById(id), x, rows, H, ml, W - mr, (r) => `${fyShort(r.date)} (${fyLab(r.date)})`, (r, px) => {
      dots.forEach((d, i) => { const v = r[S[i].key]; d.attr('display', v == null ? 'none' : null).attr('cx', px).attr('cy', v == null ? 0 : y(v)); });
      return S.map((s) => [s.color, s.name, r[s.key] == null ? 'n/a' : d3.format(C.fmt)(r[s.key]) + C.tipUnit]);
    });
    extras.push(...dots);
  }

  // Chart 3: GDP growth on the same quarter a year earlier, MoSPI, 2022-23 base (from Apr–Jun 2023), as published.
  function growth() {
    const id = 'gdp-growth', box = document.getElementById(id + '-chart');
    if (!status(box, ['in_gdp'])) return;
    const rows = J.slice(series('Q', 'gdp', growthPrice), id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280;
    const { svg, x, y, W, ml, mr } = frame(box, rows, H, rows.map((r) => r.v), true, qAxis, { anchorEvery: qAnchor, pad: 14 });
    const step = (W - ml - mr - 28) / Math.max(1, rows.length - 1);
    const bw = Math.max(2, Math.min(24, step * 0.62));
    const col = growthPrice === 'constant' ? 'var(--ad-c2)' : 'var(--ad-c1)';
    rows.forEach((r) => svg.append('rect').attr('x', x(J.date(r.date)) - bw / 2).attr('width', bw)
      .attr('y', y(Math.max(0, r.v))).attr('height', Math.abs(y(r.v) - y(0))).attr('fill', col));
    hover(svg, document.getElementById(id), x, rows, H, ml, W - mr, (r) => J.qLabel(r.date), (r) => [
      [col, growthPrice === 'constant' ? 'Real GDP, y/y' : 'Nominal GDP, y/y', pct(r.v)], [null, 'MoSPI quarter', r.fq]]);
  }

  // Chart 4: real growth by sector, quarterly, MoSPI (GDP; GVA and three of its industries), 2022-23 base.
  function sectorsQ() {
    const id = 'gdp-sectors', box = document.getElementById(id + '-chart');
    const S = SEC(id).map((s) => ({ ...s, key: s.code }));
    legend(id + '-legend', S);
    if (!status(box, ['in_gdp'])) return;
    const rows = J.slice(merge(S.map((s) => ({ key: s.key, rows: series('Q', s.code) }))), id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 280;
    const { svg, x, y, W, ml, mr } = frame(box, rows, H, rows.flatMap((r) => S.map((s) => r[s.key])).filter((v) => v != null), true, qAxis, { anchorEvery: qAnchor });
    const dots = drawLines(svg, x, y, rows, S);
    const extras = hover(svg, document.getElementById(id), x, rows, H, ml, W - mr, (r) => J.qLabel(r.date), (r, px) => {
      dots.forEach((d, i) => { const v = r[S[i].key]; d.attr('display', v == null ? 'none' : null).attr('cx', px).attr('cy', v == null ? 0 : y(v)); });
      return S.map((s) => [s.color, s.name, pct(r[s.key])]);
    });
    extras.push(...dots);
  }

  // Year to date for the current fiscal year, for charts 5 and 6: shown only when MoSPI has published it as a growth
  // rate, which (in its quarterly table) is the case for the first quarter only (Q1 = April to June, the year so far).
  function ytd(code, lastAnnual) {
    const q = series('Q', code).filter((r) => r.date >= `${lastAnnual + 1}-04-01`);
    return q.length === 1 && q[0].fq.endsWith('Q1') ? { date: `${q[0].date.slice(0, 4)}-04-01`, v: q[0].v, label: J.qLabel(q[0].date) } : null;
  }
  function annualChart(id, S, opt = {}) {
    const box = document.getElementById(id + '-chart');
    legend(id + '-legend', S.length > 1 ? S : []);
    if (!status(box, opt.ds || ['in_gdp'])) return;
    const all = merge(S.map((s) => ({ key: s.key, rows: s.rows() })));
    if (!all.length) { box.replaceChildren(); return; }
    const lastAnnual = Math.max(...all.map((r) => Number(r.date.slice(0, 4))));
    const yt = S.map((s) => (s.ytd ? ytd(s.ytd, lastAnnual) : null));
    const yd = yt.find(Boolean);
    const rows = yd ? all.concat([{ date: yd.date, ytd: true }]) : all;
    yt.forEach((t, i) => { if (t) rows[rows.length - 1][S[i].key + '_ytd'] = t.v; });
    const H = 280;
    const vals = rows.flatMap((r) => S.flatMap((s) => [r[s.key], r[s.key + '_ytd']])).filter((v) => v != null);
    const { svg, x, y, W, ml, mr } = frame(box, rows, H, vals, true, (r) => (r.ytd ? 'YTD' : fyShort(r.date)), { labelWidth: 44, top: opt.base ? 24 : 12 });
    if (opt.base && rows[0].date < BASE_SWITCH && rows[rows.length - 1].date >= BASE_SWITCH) {
      const k = rows.findIndex((r) => r.date >= BASE_SWITCH);
      const sx = (x(J.date(rows[k - 1].date)) + x(J.date(rows[k].date))) / 2;
      svg.append('line').attr('x1', sx).attr('x2', sx).attr('y1', 18).attr('y2', H - 24).attr('stroke', 'var(--ad-axis)').attr('stroke-dasharray', '3 3');
      svg.append('text').attr('x', sx).attr('y', 12).attr('font-size', 11).attr('fill', 'var(--ad-ink)').attr('text-anchor', 'middle').text('2022-23 base');
    }
    const dots = drawLines(svg, x, y, rows.filter((r) => !r.ytd), S);
    S.forEach((s) => rows.filter((r) => r[s.key + '_ytd'] != null).forEach((r) => svg.append('circle').attr('cx', x(J.date(r.date))).attr('cy', y(r[s.key + '_ytd']))
      .attr('r', s.thin ? 3.5 : 4.5).attr('fill', 'var(--color-panel)').attr('stroke', s.color).attr('stroke-width', 2)));
    const extras = hover(svg, document.getElementById(id), x, rows, H, ml, W - mr,
      (r) => (r.ytd ? `${fyShort(r.date)} so far (${yd.label})` : `${fyShort(r.date)} (${fyLab(r.date)}${opt.headExtra ? opt.headExtra(r) : ''})`), (r, px) => {
        dots.forEach((d, i) => { const v = r.ytd ? r[S[i].key + '_ytd'] : r[S[i].key]; d.attr('display', v == null ? 'none' : null).attr('cx', px).attr('cy', v == null ? 0 : y(v)); });
        return S.map((s) => [s.color, s.name, pct(r.ytd ? r[s.key + '_ytd'] : r[s.key])]);
      });
    extras.push(...dots);
  }
  const baseOf = (r) => { const g = gdp().find((x) => x.freq === 'A' && x.date === r.date && x.code === 'gdp'); return g ? `, ${g.base_year} base` : ''; };

  // Chart 5: real GDP growth, annual: MoSPI (2011-12 base to 2022-23, 2022-23 base from 2023-24, latest estimate of
  // each year) or the World Bank's WDI (from 1961; its year 2025 is fiscal 2025-26).
  function sources() {
    const S = srcPick === 'mospi'
      ? [{ key: 'gdp', name: 'MoSPI', color: 'var(--ad-c2)', ytd: 'gdp', rows: () => series('A', 'gdp') }]
      : [{ key: 'wb', name: 'World Bank', color: 'var(--ad-c2)',
        rows: () => dash.data('in_gdp_intl').data.filter((r) => r.series === 'NY.GDP.MKTP.KD.ZG').map((r) => ({ date: r.date, v: N(r.value) })) }];
    annualChart('gdp-src', S, { ds: ['in_gdp', 'in_gdp_intl'], base: srcPick === 'mospi', headExtra: srcPick === 'mospi' ? baseOf : null });
  }
  // Chart 6: real growth by sector, annual, MoSPI.
  function sectorsA() {
    annualChart('gdp-annual', SEC('gdp-annual').map((s) => ({ ...s, key: s.code, ytd: s.code, rows: () => series('A', s.code) })), { base: true, headExtra: baseOf });
  }

  function quarterNote() {
    const el = document.getElementById('gdp-q');
    if (dash.data('in_gdp').status !== 'ok') { el.textContent = '—'; return; }
    const q = series('Q', 'gdp'); if (!q.length) { el.textContent = '—'; return; }
    const r = q[q.length - 1];
    el.textContent = `${J.qLabel(r.date)} (MoSPI ${r.fq})`;
  }

  // Manufacturing tab, Chart 2 (was Chart 1): manufacturing GVA, real (MoSPI, 2022-23 base, as published) and the IIP, general and
  // manufacturing, linked across the 2011-12 and 2022-23 bases with MoSPI's factors, quarterly averages, y/y (calculated
  // in in_iip_mospi). Dashed line at the IIP base change (April 2023).
  function mfgIip() {
    const id = 'mfg-iip', box = document.getElementById(id + '-chart');
    const S = [
      { key: 'gva', name: 'Manufacturing GVA, real', color: 'var(--ad-c2)' },
      { key: 'iipm', name: 'IIP, manufacturing', color: 'var(--ad-c1)', thin: true },
    ];
    legend(id + '-legend', S);
    if (!status(box, ['in_iip_linked', 'in_gdp'])) return;
    const lk = (ser) => dash.data('in_iip_linked').data.filter((r) => r.freq === 'Q' && r.series === ser && N(r.yoy) != null)
      .map((r) => ({ date: r.date, v: N(r.yoy) }));
    const rows = J.slice(merge([{ key: 'gva', rows: series('Q', 'manufacturing') }, { key: 'iipm', rows: lk('manufacturing') }])
      .filter((r) => r.date >= '2023-01-01'), id);   // from 2023 (user, 3 Nov 2026)
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 300;
    const { svg, x, y, W, ml, mr } = frame(box, rows, H, rows.flatMap((r) => S.map((s) => r[s.key])).filter((v) => v != null), true,
      qAxis, { anchorEvery: qAnchor, top: 24 });
    if (rows[0].date < '2023-04-01' && rows[rows.length - 1].date >= '2023-04-01') vline(svg, x, '2023-04-01', H, 'IIP 2022-23 base');
    const dots = drawLines(svg, x, y, rows, S);
    const extras = hover(svg, document.getElementById(id), x, rows, H, ml, W - mr, (r) => J.qLabel(r.date), (r, px) => {
      dots.forEach((d, i) => { const v = r[S[i].key]; d.attr('display', v == null ? 'none' : null).attr('cx', px).attr('cy', v == null ? 0 : y(v)); });
      return S.map((s) => [s.color, s.name, pct(r[s.key])]);
    });
    extras.push(...dots);
  }
  // Manufacturing tab, Chart 5 (bar chart, below Charts 3-4): IIP by NIC 2-digit manufacturing division, the latest three months y/y (3mma) and the
  // calendar year to date y/y (both ratios of summed indices, calculated in in_iip_mospi). Sorted by the 3mma;
  // manufacturing as a whole on top.
  function mfgDiv() {
    const id = 'mfg-div', box = document.getElementById(id + '-chart');
    if (!status(box, ['in_iip_divisions'])) { legend(id + '-legend', []); return; }
    const D = dash.data('in_iip_divisions').data.map((r) => ({ ...r, yoy: N(r.yoy), m3: N(r.m3), ytd: N(r.ytd) }));
    if (!D.length) { box.replaceChildren(); return; }
    const S = [{ key: 'm3', name: '3mma', color: 'var(--ad-c2)', bar: true }, { key: 'ytd', name: 'YTD', color: 'var(--ad-c1)', bar: true }];
    legend(id + '-legend', S);
    // Manufacturing, electronics and non-electronics (not bold; user, 3 Nov 2026), other industries (bold), all
    // calculated at MoSPI's weights, then the divisions by 3mma.
    const GR = ['E2627', 'X2627', 'OTH'];
    const head = ['C'].concat(GR).map((c) => D.find((r) => r.nic === c)).filter(Boolean);
    const rows = head.concat(D.filter((r) => r.nic !== 'C' && !GR.includes(r.nic)).sort((a, b) => b.m3 - a.m3));
    const W = box.clientWidth, rowH = 26, top = 6, H = top + rows.length * rowH + 22;
    box.replaceChildren();
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const GLAB = { E2627: 'Electronics', X2627: 'Non-electronics', OTH: 'Other industries' };   // short labels (user, 3 Nov 2026)
    const lab = (r) => (r.nic === 'C' ? 'Manufacturing' : GLAB[r.nic] || `${r.name} (${r.nic})`);
    const lw = Math.min(W * 0.42, J.textWidth(svg, rows.map(lab)) + 12);
    const vals = rows.flatMap((r) => [r.m3, r.ytd]).filter((v) => v != null);
    const x = d3.scaleLinear([Math.min(0, d3.min(vals)), Math.max(0, d3.max(vals))], [lw, W - 8]).nice();
    const ticks = x.ticks(Math.max(2, Math.floor((W - lw) / 70)));
    svg.append('g').selectAll('line').data(ticks).join('line').attr('x1', x).attr('x2', x).attr('y1', top).attr('y2', H - 20)
      .attr('stroke', (v) => (v === 0 ? 'var(--cds-chart-reference)' : 'var(--ad-grid)'));
    J.axisStyle(svg.append('g').attr('transform', `translate(0,${H - 18})`).call(d3.axisBottom(x).tickValues(ticks).tickSize(0).tickFormat(d3.format('.0f'))));
    const bh = (rowH - 8) / 2;
    rows.forEach((r, i) => {
      const y0 = top + i * rowH + 4;
      svg.append('text').attr('x', lw - 8).attr('y', y0 + bh).attr('dy', '0.35em').attr('text-anchor', 'end').attr('font-size', 12)
        .attr('font-weight', r.nic === 'C' || r.nic === 'OTH' ? 700 : null).attr('fill', 'var(--ad-ink)').text(lab(r));
      S.forEach((s, k) => {
        const v = r[s.key]; if (v == null) return;
        svg.append('rect').attr('x', x(Math.min(0, v))).attr('width', Math.abs(x(v) - x(0))).attr('y', y0 + k * bh).attr('height', bh - 1).attr('fill', s.color);
      });
    });
    if (rows.length > head.length) svg.append('line').attr('x1', 0).attr('x2', W - 8).attr('y1', top + head.length * rowH).attr('y2', top + head.length * rowH).attr('stroke', 'var(--ad-axis)');
    const card = document.getElementById(id), tip = J.tip(card);
    const hl = svg.append('rect').attr('x', 0).attr('width', W).attr('height', rowH).attr('fill', 'var(--cds-chart-reference)').attr('opacity', 0.12).attr('display', 'none');
    svg.append('rect').attr('x', 0).attr('y', top).attr('width', W).attr('height', rows.length * rowH).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const [, my] = d3.pointer(ev); const i = Math.max(0, Math.min(rows.length - 1, Math.floor((my - top) / rowH))); const r = rows[i];
        hl.attr('display', null).attr('y', top + i * rowH);
        const cr = card.getBoundingClientRect();
        J.showTip(card, tip, r.nic === 'C' || GR.includes(r.nic) ? lab(r) : `NIC ${r.nic}: ${r.industry}`, S.map((s) => [s.color, s.name, pct(r[s.key])]), ev.clientX - cr.left, ev.clientY - cr.top);
      })
      .on('mouseleave', () => { hl.attr('display', 'none'); tip.style.display = 'none'; });
  }
  // Manufacturing tab, Chart 3: electronics and non-electronics manufacturing IIP, y/y, monthly from April 2024
  // (2022-23 base; groups calculated in in_iip_mospi at MoSPI's weights).
  function mfgElec() {
    const id = 'mfg-elec', box = document.getElementById(id + '-chart');
    const S = [
      { key: 'E2627', name: 'Electronics manufacturing', color: 'var(--ad-c1)' },
      { key: 'X2627', name: 'Non-electronics manufacturing', color: 'var(--ad-c2)' },
      { key: 'OTH', name: 'Other industries', color: '#A6A6A6' },
    ];
    legend(id + '-legend', S);
    if (!status(box, ['in_iip_groups'])) return;
    const G = dash.data('in_iip_groups').data;
    const rows = J.slice(merge(S.map((s) => ({ key: s.key, rows: G.filter((r) => r.code === s.key && N(r.yoy) != null && r.date >= '2024-04-01').map((r) => ({ date: r.date, v: N(r.yoy) })) }))), id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 300;
    const mAxis = (r) => (r.date.slice(5, 7) === '01' ? r.date.slice(0, 4) : null);
    const { svg, x, y, W, ml, mr } = frame(box, rows, H, rows.flatMap((r) => S.map((s) => r[s.key])).filter((v) => v != null), true, mAxis,
      { anchorEvery: (r) => r.date.slice(5, 7) === '01' });
    const dots = drawLines(svg, x, y, rows, S);
    const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const extras = hover(svg, document.getElementById(id), x, rows, H, ml, W - mr, (r) => `${MON[Number(r.date.slice(5, 7)) - 1]} ${r.date.slice(0, 4)}`, (r, px) => {
      dots.forEach((d, i) => { const v = r[S[i].key]; d.attr('display', v == null ? 'none' : null).attr('cx', px).attr('cy', v == null ? 0 : y(v)); });
      return S.map((s) => [s.color, s.name, pct(r[s.key])]);
    });
    extras.push(...dots);
  }
  // Manufacturing tab, Chart 1 (added 3 Nov 2026; the earlier charts renumbered 2-4): IIP y/y, monthly, General or
  // Manufacturing. MoSPI's y/y as published on the 2022-23 base from April 2023 (to March 2024 against the 2022-23
  // months normalised to 100, MoSPI's method), and the spliced series (2011-12 index / MoSPI's factor to March 2023,
  // 2022-23 base after; y/y calculated) from April 2013.
  let iipKey = 'general';
  function mfgIipM() {
    const id = 'mfg-iipm', box = document.getElementById(id + '-chart');
    const S = [
      { key: 'mos', name: 'MoSPI', color: 'var(--ad-c2)' },
      { key: 'spl', name: 'Spliced', color: 'var(--ad-c2)', dash: true },
    ];
    legend(id + '-legend', S);
    if (!status(box, ['in_iip_linked'])) return;
    const L = dash.data('in_iip_linked').data.filter((r) => r.freq === 'M' && r.series === iipKey);
    const rows = J.slice(merge([
      { key: 'mos', rows: L.filter((r) => N(r.yoy_mospi) != null).map((r) => ({ date: r.date, v: N(r.yoy_mospi) })) },
      { key: 'spl', rows: L.filter((r) => N(r.yoy) != null).map((r) => ({ date: r.date, v: N(r.yoy) })) },
    ]), id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 300;
    const { svg, x, y, W, ml, mr } = frame(box, rows, H, rows.flatMap((r) => S.map((s) => r[s.key])).filter((v) => v != null), true,
      (r) => (r.date.slice(5, 7) === '01' ? r.date.slice(0, 4) : null), { anchorEvery: (r) => r.date.slice(5, 7) === '01', top: 24 });
    if (rows[0].date < '2023-04-01' && rows[rows.length - 1].date >= '2023-04-01') vline(svg, x, '2023-04-01', H, '2022-23 base');
    const dots = drawLines(svg, x, y, rows, S);
    const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const extras = hover(svg, document.getElementById(id), x, rows, H, ml, W - mr, (r) => `${MON[Number(r.date.slice(5, 7)) - 1]} ${r.date.slice(0, 4)}`, (r, px) => {
      dots.forEach((d, i) => { const v = r[S[i].key]; d.attr('display', v == null ? 'none' : null).attr('cx', px).attr('cy', v == null ? 0 : y(v)); });
      return S.filter((s) => r[s.key] != null).map((s) => [s.color, s.name, pct(r[s.key])]);
    });
    extras.push(...dots);
  }
  document.getElementById('mfg-iipm-seg').addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    iipKey = b.dataset.k;
    document.querySelectorAll('#mfg-iipm-seg button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    J.redrawMfg();
  });
  // Manufacturing tab, Chart 4 (added 3 Nov 2026): contributions to general IIP y/y, pp, monthly from April 2024:
  // weight x change in index / general index a year earlier, at MoSPI's 2022-23 weights (calculated in in_iip_mospi);
  // stacked bars, general IIP y/y (MoSPI, published) as the line. Colours: user's contribution-chart scheme.
  function mfgContrib() {
    const id = 'mfg-contrib', box = document.getElementById(id + '-chart');
    const P = [   // bottom of the stack first
      { key: 'X2627', name: 'Non-electronics manufacturing', color: '#1F4E79', bar: true },
      { key: 'E2627', name: 'Electronics manufacturing', color: '#0C84FF', bar: true },
      { key: 'other', name: 'Other industries', color: '#A6A6A6', bar: true },
    ];
    const LINE = { key: 'g', name: 'General IIP, y/y', color: '#BD1B21' };
    legend(id + '-legend', [LINE].concat(P.slice().reverse()));
    if (!status(box, ['in_iip_contrib'])) return;
    const by = new Map();
    dash.data('in_iip_contrib').data.forEach((r) => {
      if (!by.has(r.date)) by.set(r.date, { date: r.date, g: N(r.general_yoy) });
      by.get(r.date)[r.part] = N(r.contribution);
    });
    const rows = J.slice(Array.from(by.values()).sort((a, b) => (a.date < b.date ? -1 : 1)), id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 300;
    const ext = rows.flatMap((r) => {
      let pos = 0, neg = 0; P.forEach((p) => { const v = r[p.key] || 0; if (v >= 0) pos += v; else neg += v; });
      return [pos, neg, r.g];
    }).filter((v) => v != null);
    const { svg, x, y, W, ml, mr } = frame(box, rows, H, ext, true,
      (r) => (r.date.slice(5, 7) === '01' ? r.date.slice(0, 4) : null), { anchorEvery: (r) => r.date.slice(5, 7) === '01', pad: 10 });
    const step = (W - ml - mr - 20) / Math.max(1, rows.length - 1);
    const bw = Math.max(2, Math.min(22, step * 0.7));
    rows.forEach((r) => {
      let pos = 0, neg = 0;
      P.forEach((p) => {
        const v = r[p.key]; if (v == null) return;
        const y0 = v >= 0 ? pos : neg, y1 = y0 + v;
        svg.append('rect').attr('x', x(J.date(r.date)) - bw / 2).attr('width', bw).attr('y', y(Math.max(y0, y1))).attr('height', Math.abs(y(y0) - y(y1))).attr('fill', p.color);
        if (v >= 0) pos = y1; else neg = y1;
      });
    });
    svg.append('path').attr('d', d3.line().defined((r) => r.g != null).x((r) => x(J.date(r.date))).y((r) => y(r.g))(rows))
      .attr('fill', 'none').attr('stroke', LINE.color).attr('stroke-width', 2.5).attr('stroke-linejoin', 'round');
    const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const dot = svg.append('circle').attr('r', 3.5).attr('fill', LINE.color).attr('display', 'none');
    const extras = hover(svg, document.getElementById(id), x, rows, H, ml, W - mr, (r) => `${MON[Number(r.date.slice(5, 7)) - 1]} ${r.date.slice(0, 4)}`, (r, px) => {
      if (r.g != null) dot.attr('display', null).attr('cx', px).attr('cy', y(r.g));
      return [[LINE.color, LINE.name, pct(r.g)]].concat(P.slice().reverse().map((p) => [p.color, p.name, r[p.key] == null ? 'n/a' : r[p.key].toFixed(2) + ' pp']));
    });
    extras.push(dot);
  }
  // IIP biggest contributors table: largest positive and negative 3m (or 6m) average contributions, five each.
  let iipMoversN = 3;
  const MONS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function iipMovers() {
    const tb = document.querySelector('#iip-movers-table tbody');
    const M = dash.data('iip_movers');
    if (failed(M.status)) { tb.replaceChildren(); const td = tb.insertRow().insertCell(); td.colSpan = 4; J.fail(td); return; }
    if (M.status !== 'ok') return;
    const k = iipMoversN === 6 ? 'avg6' : 'avg3';
    const rows = M.data.filter((r) => r[k] != null);
    const up = rows.slice().sort((a, b) => b[k] - a[k] || b.yoy - a.yoy).slice(0, 5);
    const down = rows.slice().sort((a, b) => a[k] - b[k] || a.yoy - b.yoy).slice(0, 5);
    const date = M.data.length ? M.data[0].date : null;
    document.getElementById('iip-movers-units').textContent = date
      ? `%, ppt, ${iipMoversN}-month average to ${MONS[Number(date.slice(5, 7)) - 1]} ${date.slice(0, 4)}` : '%, ppt';
    document.getElementById('iip-movers-avg').textContent = `Contrib., ${iipMoversN}m`;
    tb.replaceChildren();
    [['Largest positive contributions', up], ['Largest negative contributions', down]].forEach(([g, list], gi) => {
      const gr = tb.insertRow(); gr.className = 'grp' + (gi ? ' sep' : '');
      const gtd = gr.insertCell(); gtd.colSpan = 4; gtd.textContent = g;
      list.forEach((r) => {
        const tr = tb.insertRow(); tr.dataset.key = r.name;
        [['name', r.name], ['weight', r.weight], ['yoy', r.yoy], [k, r[k]]].forEach(([f, v]) => {
          const td = tr.insertCell();
          if (f === 'name') { td.textContent = v; return; }
          td.textContent = v == null ? '' : (f === 'yoy' ? d3.format('.1f')(v) : d3.format('.2f')(v));
          if (v != null && v < 0 && f !== 'weight') td.classList.add('neg');
        });
      });
    });
  }
  const iseg = document.getElementById('iip-movers-seg');
  iseg.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    iipMoversN = Number(b.dataset.n);
    iseg.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    iipMovers();
  });
  dash.onData(() => iipMovers());

  // Manufacturing tab: manufacturing share, % of GDP or % of GVA (toggle), current prices, annual (fiscal years),
  // calculated in in_gdp_mospi from MoSPI's levels on each base: 2011-12 base (dashed) and 2022-23 base (solid).
  let shareMeasure = 'share_gdp';
  function mfgShare() {
    const id = 'mfg-share', box = document.getElementById(id + '-chart');
    document.getElementById(id + '-units').textContent = `% of ${shareMeasure === 'share_gdp' ? 'GDP' : 'GVA'}, current prices`;
    const S = [{ key: 'new', name: '2022-23 base', color: 'var(--ad-c2)' }, { key: 'old', name: '2011-12 base', color: 'var(--ad-c2)', dash: true }];
    legend(id + '-legend', S);
    if (!status(box, ['in_gdp'])) return;
    const sh = (b) => gdp().filter((r) => r.freq === 'A' && r.code === 'manufacturing' && r.measure === shareMeasure && r.base_year === b && r.price === 'current')
      .map((r) => ({ date: r.date, v: N(r.value) }));
    const rows = J.slice(merge([{ key: 'new', rows: sh('2022-23') }, { key: 'old', rows: sh('2011-12') }]), id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 300;
    const { svg, x, y, W, ml, mr } = frame(box, rows, H, rows.flatMap((r) => [r.new, r.old]).filter((v) => v != null), false,
      (r) => fyShort(r.date), { labelWidth: 44, pad: 6 });
    const dots = drawLines(svg, x, y, rows, S);
    const extras = hover(svg, document.getElementById(id), x, rows, H, ml, W - mr, (r) => `${fyShort(r.date)} (${fyLab(r.date)})`, (r, px) => {
      dots.forEach((d, i) => { const v = r[S[i].key]; d.attr('display', v == null ? 'none' : null).attr('cx', px).attr('cy', v == null ? 0 : y(v)); });
      return S.filter((s) => r[s.key] != null).map((s) => [s.color, s.name, r[s.key].toFixed(1) + '%']);
    });
    extras.push(...dots);
  }

  document.getElementById('mfg-share-seg').addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    shareMeasure = b.dataset.p;
    document.querySelectorAll('#mfg-share-seg button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    mfgShare();
  });

  // Manufacturing tab: manufacturing GVA growth, real and nominal, % y/y, MoSPI's published rates. Annual: 2011-12 base
  // to FY23, 2022-23 base from FY24 (dashed line at the base change), latest estimate of each year. Quarterly: 2022-23
  // base from Apr-Jun 2023.
  let mgFreq = 'A';
  function mfgGva() {
    const id = 'mfg-gva', box = document.getElementById(id + '-chart');
    const S = [{ key: 'real', name: 'Real', color: 'var(--ad-c2)' }, { key: 'nom', name: 'Nominal', color: 'var(--ad-c1)' }];
    legend(id + '-legend', S);
    if (!status(box, ['in_gdp'])) return;
    const rows = J.slice(merge([{ key: 'real', rows: series(mgFreq, 'manufacturing', 'constant') },
      { key: 'nom', rows: series(mgFreq, 'manufacturing', 'current') }]), id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 300, ann = mgFreq === 'A';
    const { svg, x, y, W, ml, mr } = frame(box, rows, H, rows.flatMap((r) => [r.real, r.nom]).filter((v) => v != null), true,
      ann ? (r) => fyShort(r.date) : qAxis, ann ? { labelWidth: 44, top: 24, pad: 6 } : { anchorEvery: qAnchor, top: 24 });
    if (ann && rows[0].date < BASE_SWITCH && rows[rows.length - 1].date >= BASE_SWITCH) {
      const k = rows.findIndex((r) => r.date >= BASE_SWITCH);
      const sx = (x(J.date(rows[k - 1].date)) + x(J.date(rows[k].date))) / 2;
      svg.append('line').attr('x1', sx).attr('x2', sx).attr('y1', 18).attr('y2', H - 24).attr('stroke', 'var(--ad-axis)').attr('stroke-dasharray', '3 3');
      svg.append('text').attr('x', sx).attr('y', 12).attr('font-size', 11).attr('fill', 'var(--ad-ink)').attr('text-anchor', 'middle').text('2022-23 base');
    }
    const dots = drawLines(svg, x, y, rows, S);
    const extras = hover(svg, document.getElementById(id), x, rows, H, ml, W - mr,
      (r) => (ann ? `${fyShort(r.date)} (${fyLab(r.date)}${baseOf(r)})` : J.qLabel(r.date)), (r, px) => {
        dots.forEach((d, i) => { const v = r[S[i].key]; d.attr('display', v == null ? 'none' : null).attr('cx', px).attr('cy', v == null ? 0 : y(v)); });
        return S.map((s) => [s.color, s.name, pct(r[s.key])]);
      });
    extras.push(...dots);
  }
  document.getElementById('mfg-gva-seg').addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    mgFreq = b.dataset.f;
    document.querySelectorAll('#mfg-gva-seg button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    mfgGva();
  });

  // Manufacturing tab: capacity utilisation in manufacturing, %, quarterly, RBI OBICUS: as published (red) and RBI's
  // seasonally adjusted series (blue, X-13ARIMA-SEATS), from Apr-Jun 2008; quarters labelled by calendar months.
  function mfgCu() {
    const id = 'mfg-cu', box = document.getElementById(id + '-chart');
    const S = [{ key: 'cu', name: 'As published', color: 'var(--ad-c2)' }, { key: 'sa', name: 'Seasonally adjusted', color: 'var(--ad-c1)' }];
    legend(id + '-legend', S);
    if (!status(box, ['in_cu'])) return;
    const rows = J.slice(dash.data('in_cu').data.map((r) => ({ date: r.date, cu: N(r.cu), sa: N(r.cu_sa), q: r.quarter })).filter((r) => r.cu != null)
      .sort((a, b) => (a.date < b.date ? -1 : 1)), id);
    if (!rows.length) { box.replaceChildren(); return; }
    const H = 300;
    const { svg, x, y, W, ml, mr } = frame(box, rows, H, rows.flatMap((r) => [r.cu, r.sa]).filter((v) => v != null), false, qAxis, { anchorEvery: (r, k) => r.date.slice(5, 7) === '01' && Number(r.date.slice(0, 4)) % (k > 2 ? 4 : 2) === 0 });
    const dots = drawLines(svg, x, y, rows, S);
    const extras = hover(svg, document.getElementById(id), x, rows, H, ml, W - mr, (r) => `${J.qLabel(r.date)} (RBI ${r.q})`, (r, px) => {
      dots.forEach((d, i) => { const v = r[S[i].key]; d.attr('display', v == null ? 'none' : null).attr('cx', px).attr('cy', v == null ? 0 : y(v)); });
      return S.map((s) => [s.color, s.name, r[s.key] == null ? 'n/a' : r[s.key].toFixed(1) + '%']);
    });
    extras.push(...dots);
  }

  J.redrawMfg = () => { if (!document.getElementById('manufacturing').hidden) { mfgIipM(); mfgIip(); mfgDiv(); mfgElec(); mfgContrib(); mfgShare(); mfgGva(); mfgCu(); } };

  J.redrawGdp = () => {
    J.redrawMfg();
    if (!visible()) return;
    quarterNote();
    usd('gdp-usd', usdPick);
    usd('gdp-pc', pcPick);
    growth();
    sectorsQ();
    sources();
    sectorsA();
  };
  const seg = (id, attr, set) => {
    const el = document.getElementById(id);
    el.addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b) return;
      set(b.dataset[attr]);
      el.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      J.redrawGdp();
    });
  };
  seg('gdp-growth-seg', 's', (v) => { growthPrice = v; });
  seg('gdp-src-seg', 'src', (v) => { srcPick = v; });
  seg('gdp-usd-seg', 'u', (v) => { usdPick = v; });
  seg('gdp-pc-seg', 'u', (v) => { pcPick = v; });
  let raf = 0;
  window.addEventListener('resize', () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => J.redrawGdp()); });
  dash.onData(() => J.redrawGdp());
})();
