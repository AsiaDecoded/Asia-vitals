window.JG = {
  state: { basis: 'real', origBasis: 'real', levelBasis: 'real', quarters: 40, contrib: 'qoq' },
  num,
  qLabel(d) {
    const m = Number(d.slice(5, 7));
    return ({ 1: 'Jan–Mar', 4: 'Apr–Jun', 7: 'Jul–Sep', 10: 'Oct–Dec' })[m] + ' ' + d.slice(0, 4);
  },
  date(d) { return new Date(Date.UTC(Number(d.slice(0, 4)), Number(d.slice(5, 7)) - 1, 1)); },
  f1(v) { return v == null || Number.isNaN(v) ? '' : v.toFixed(1); },
  fail(el) {
    el.replaceChildren();
    const d = document.createElement('div'); d.className = 'jg-fail'; d.textContent = 'Failed to load'; el.appendChild(d);
  },
  // Period per chart: number of points to show (0 = all), set by each chart's own buttons.
  period: {},
  periodOf(id, def) { return id in this.period ? this.period[id] : def; },
  window(rows, id) { const n = this.periodOf(id, 40); return n ? rows.slice(-n) : rows; },
  // Range slider per chart: the selected share of the chart's full date range, [from, to] in 0..1.
  range: {},
  slice(rows, id) {
    const [lo, hi] = this.range[id] || [0, 1];
    if (!rows.length) return rows;
    const n = rows.length - 1, i0 = Math.round(lo * n), i1 = Math.max(i0, Math.round(hi * n));
    const out = rows.slice(i0, i1 + 1);
    const card = document.getElementById(id), lbl = card && card.querySelector('.ad-slider-lbl');
    if (lbl && out.length) {
      const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      const f = (d) => (card.dataset.periods === 'a' ? d.slice(0, 4) : MON[Number(d.slice(5, 7)) - 1] + ' ' + d.slice(0, 4));
      lbl.textContent = `${f(out[0].date)} to ${f(out[out.length - 1].date)}`;
    }
    return out;
  },
  addSliders(redraw) {
    document.querySelectorAll('.jg-card').forEach((card) => {
      const chart = card.querySelector(':scope > .jg-chart'); if (!chart || !card.id) return;
      const wrap = document.createElement('div'); wrap.className = 'ad-slider';
      const track = document.createElement('div'); track.className = 'ad-slider-track';
      const sel = document.createElement('div'); sel.className = 'ad-slider-sel'; track.appendChild(sel);
      const mk = (v, label) => { const i = document.createElement('input'); i.type = 'range'; i.min = 0; i.max = 1000; i.step = 1; i.value = v; i.setAttribute('aria-label', label); return i; };
      const a = mk(0, 'Start date'), b = mk(1000, 'End date');
      const lbl = document.createElement('div'); lbl.className = 'ad-slider-lbl';
      wrap.append(track, a, b);
      let raf = 0;
      const upd = (moved) => {
        let lo = Number(a.value), hi = Number(b.value);
        if (hi - lo < 20) { if (moved === a) { lo = hi - 20; a.value = lo; } else { hi = lo + 20; b.value = hi; } }
        sel.style.left = `${lo / 10}%`; sel.style.right = `${100 - hi / 10}%`;
        JG.range[card.id] = [lo / 1000, hi / 1000];
        cancelAnimationFrame(raf); raf = requestAnimationFrame(() => redraw());
      };
      a.addEventListener('input', () => upd(a)); b.addEventListener('input', () => upd(b));
      chart.after(wrap, lbl);
      sel.style.left = '0%'; sel.style.right = '0%';
    });
  },
  addPeriods() {
    const SETS = { q: [['5Y', 20], ['10Y', 40], ['All', 0]], m: [['3Y', 36], ['5Y', 60], ['10Y', 120], ['All', 0]], ml: [['10Y', 120], ['30Y', 360], ['All', 0]], a: [['20Y', 20], ['40Y', 40], ['All', 0]] };
    document.querySelectorAll('.jg-card').forEach((card) => {
      const chart = card.querySelector('.jg-chart'); if (!chart) return;
      if (card.dataset.periods === 'none') return;
      const page = card.closest('.jg-page'); const kind = card.dataset.periods || (page && page.id === 'gdp' ? 'q' : 'm');
      const def = card.dataset.def != null ? Number(card.dataset.def) : (kind === 'q' ? 40 : 120);
      const seg = document.createElement('div'); seg.className = 'jg-seg ad-period'; seg.setAttribute('role', 'group'); seg.setAttribute('aria-label', 'Period');
      SETS[kind].forEach(([lab, n]) => {
        const b = document.createElement('button'); b.type = 'button'; b.textContent = lab; b.dataset.n = n;
        b.setAttribute('aria-pressed', String(n === def)); seg.appendChild(b);
      });
      seg.addEventListener('click', (e) => {
        const b = e.target.closest('button'); if (!b) return;
        JG.period[card.id] = Number(b.dataset.n);
        seg.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
        const p = page ? page.id : 'gdp';
        if (p === 'gdp') (JG.redrawGdp || JG.redraw) && (JG.redrawGdp || JG.redraw)(); else if (p === 'inflation') JG.redrawCpi && JG.redrawCpi(); else JG.redrawTrade && JG.redrawTrade();
      });
      let head = card.querySelector(':scope > .jg-cardhead');
      if (!head) {
        const h2 = card.querySelector(':scope > h2');
        head = document.createElement('div'); head.className = 'jg-cardhead';
        const left = document.createElement('div'); h2.replaceWith(head); left.appendChild(h2); head.appendChild(left);
      }
      let right = head.querySelector(':scope > .ad-controls');
      if (!right) {
        right = document.createElement('div'); right.className = 'ad-controls';
        const segs = Array.from(head.querySelectorAll(':scope > .jg-seg'));
        segs.forEach((x) => right.appendChild(x)); head.appendChild(right);
      }
      right.appendChild(seg);
    });
  },
  // Measure text widths so margins fit the labels actually drawn.
  textWidth(svg, labels) {
    const g = svg.append('g').attr('opacity', 0);
    let w = 0;
    labels.forEach((t) => { const n = g.append('text').attr('font-size', 12).text(t).node(); w = Math.max(w, n.getComputedTextLength()); });
    g.remove();
    return w;
  },
  yearTicks(dates, width) {
    const years = Array.from(new Set(dates.map((d) => d.slice(0, 4))));
    const room = Math.max(1, Math.floor(width / 48));
    const step = [1, 2, 4, 5, 10].find((s) => years.length / s <= room) || 10;
    return dates.filter((d) => d.slice(5, 7) === '01' && Number(d.slice(0, 4)) % step === 0);
  },
  tip(card) {
    let t = card.querySelector(':scope > .jg-tip');
    if (!t) { t = document.createElement('div'); t.className = 'jg-tip'; card.appendChild(t); }
    return t;
  },
  showTip(card, tip, title, lines, px, py) {
    tip.replaceChildren();
    const h = document.createElement('div'); h.className = 't'; h.textContent = title; tip.appendChild(h);
    lines.forEach(([color, name, value]) => {
      const r = document.createElement('div'); r.className = 'r';
      const k = document.createElement('span'); k.className = 'k';
      if (color) { const i = document.createElement('i'); i.style.background = color; k.appendChild(i); }
      const s = document.createElement('span'); s.textContent = name; k.appendChild(s);
      const v = document.createElement('span'); v.textContent = value;
      r.append(k, v); tip.appendChild(r);
    });
    tip.style.display = 'block';
    const cw = card.clientWidth, tw = tip.offsetWidth;
    let left = px + 14; if (left + tw > cw - 8) left = px - tw - 14; if (left < 8) left = 8;
    tip.style.left = left + 'px'; tip.style.top = Math.max(8, py - 10) + 'px';
  },
  // Asia Decoded palette; the two dark greys lighten on a dark background.
  PAL: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => `var(--ad-c${i})`),
  theme() {
    const root = document.querySelector('#dash-root .jg') || document.querySelector('.jg');
    if (!root) return;
    const bg = getComputedStyle(root).getPropertyValue('--color-bg').trim() || getComputedStyle(document.body).backgroundColor;
    const probe = document.createElement('span'); probe.style.color = bg; root.appendChild(probe);
    const col = getComputedStyle(probe).color; probe.remove();
    const n = (col.match(/[\d.]+%?/g) || ['255', '255', '255']);
    let dark;
    if (/^(ok)?l(ab|ch)/.test(col)) { let L = parseFloat(n[0]); if (n[0].endsWith('%') || L > 1) L /= 100; dark = L < 0.5; }
    else { const v = n.map(parseFloat); dark = (0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]) < 128; }
    const v = { '--ad-c1': '#0C84FF', '--ad-c2': '#BD1B21', '--ad-c3': '#EE6631', '--ad-c4': dark ? '#ADB5BD' : '#495057',
      '--ad-c5': '#FFC000', '--ad-c6': '#92D050', '--ad-c7': '#954F72', '--ad-c8': dark ? '#8496B0' : '#44546A',
      '--ad-ink': dark ? 'var(--color-fg-muted)' : '#495057', '--ad-grid': dark ? 'var(--cds-chart-grid)' : '#D9D9D9',
      '--ad-axis': dark ? 'var(--cds-chart-axis)' : '#A6A6A6' };
    Object.entries(v).forEach(([k, x]) => root.style.setProperty(k, x));
  },
  axisStyle(g) {
    g.attr('font-size', null).attr('font-family', null);
    g.selectAll('text').attr('fill', 'var(--ad-ink)').attr('font-size', 12);
    g.selectAll('line').attr('stroke', 'var(--ad-axis)');
    g.select('.domain').remove();
  },
};