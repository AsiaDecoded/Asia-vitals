// PNG export of any chart card, in the Asia Decoded house style on a white background.
(() => {
  const J = window.JG;
  const LIGHT = { '--ad-c1': '#0C84FF', '--ad-c2': '#BD1B21', '--ad-c3': '#EE6631', '--ad-c4': '#495057',
    '--ad-c5': '#FFC000', '--ad-c6': '#92D050', '--ad-c7': '#954F72', '--ad-c8': '#44546A',
    '--ad-ink': '#495057', '--ad-grid': '#D9D9D9', '--ad-axis': '#A6A6A6' };
  const INK = '#495057', FONT = 'Arial, Helvetica, sans-serif', SCALE = 2;

  // A colour as written in the page ('var(--ad-c1)', 'var(--color-fg)', '#fff') -> a plain colour for the export.
  const resolve = (val, el) => {
    if (!val) return val;
    const m = String(val).match(/var\((--[\w-]+)/);
    if (!m) return val;
    if (LIGHT[m[1]]) return LIGHT[m[1]];
    if (m[1] === '--color-fg' || m[1] === '--color-fg-muted') return INK;
    if (m[1] === '--color-panel' || m[1] === '--color-bg') return '#FFFFFF';
    const probe = document.createElement('span'); probe.style.color = val; (el || document.body).appendChild(probe);
    const c = getComputedStyle(probe).color; probe.remove(); return c;
  };

  function svgImage(svg) {
    const clone = svg.cloneNode(true);
    const vb = svg.viewBox.baseVal;
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    clone.setAttribute('width', vb.width); clone.setAttribute('height', vb.height);
    clone.querySelectorAll('[display="none"]').forEach((n) => n.remove());
    clone.querySelectorAll('rect[fill="transparent"]').forEach((n) => n.remove());
    clone.querySelectorAll('*').forEach((n) => {
      ['fill', 'stroke'].forEach((a) => { const v = n.getAttribute(a); if (v && v.includes('var(')) n.setAttribute(a, resolve(v, svg)); });
      if (n.style && n.style.length) {
        ['fill', 'stroke', 'color', 'background'].forEach((p) => { const v = n.style.getPropertyValue(p); if (v && v.includes('var(')) n.style.setProperty(p, resolve(v, svg)); });
      }
      if (n.tagName === 'text') { n.setAttribute('font-family', FONT); if (!n.getAttribute('fill') || n.getAttribute('fill').includes('var(')) n.setAttribute('fill', INK); }
    });
    clone.querySelectorAll('g[fill]').forEach((g) => { const v = g.getAttribute('fill'); if (v.includes('var(')) g.setAttribute('fill', resolve(v, svg)); });
    const xml = new XMLSerializer().serializeToString(clone);
    return new Promise((ok, bad) => {
      const img = new Image();
      img.onload = () => ok({ img, w: vb.width, h: vb.height });
      img.onerror = bad;
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(xml);
    });
  }

  function wrap(ctx, text, width) {
    const words = text.split(/\s+/), lines = []; let line = '';
    words.forEach((w) => { const t = line ? line + ' ' + w : w; if (ctx.measureText(t).width > width && line) { lines.push(line); line = w; } else line = t; });
    if (line) lines.push(line);
    return lines;
  }

  async function render(card) {
    const svg = card.querySelector('.jg-chart svg');
    if (!svg) return null;
    const { img, w, h } = await svgImage(svg);
    const pad = 18, W = w + pad * 2;
    const title = (card.querySelector('h2') || {}).textContent || '';
    const top = card.querySelector('.ad-top');
    const units = top ? top.querySelector('.ad-units:not(.r)').textContent.trim() : '';
    const unitsR = top ? (top.querySelector('.ad-units.r') || {}).textContent || '' : '';
    const legend = top ? Array.from(top.querySelectorAll('.jg-legend > span')).map((s) => {
      const m = s.querySelector('span');
      const dash = m && m.dataset.dash === '1';
      return { text: s.textContent.trim(), kind: m ? m.className : 'ln', dash, color: m ? resolve(dash ? m.dataset.color : (m.style.background || 'var(--color-fg)'), s) : INK };
    }) : [];
    const src = (card.querySelector('.ad-foot > span') || {}).textContent || '';
    const meas = document.createElement('canvas').getContext('2d');
    meas.font = `11px ${FONT}`;
    const srcLines = wrap(meas, src.trim(), W - pad * 2 - 110);
    // legend rows
    meas.font = `13px ${FONT}`;
    const legRows = []; let row = [], rw = 0; const maxLeg = W - pad * 2 - (units ? meas.measureText(units).width + 24 : 0) - (unitsR.trim() ? meas.measureText(unitsR.trim()).width + 24 : 0);
    legend.forEach((l) => { const iw = 26 + meas.measureText(l.text).width + 18; if (rw + iw > maxLeg && row.length) { legRows.push(row); row = []; rw = 0; } row.push({ ...l, iw }); rw += iw; });
    if (row.length) legRows.push(row);
    const titleH = 34, topH = Math.max(1, legRows.length) * 20 + 6, footH = srcLines.length * 14 + 12;
    const H = pad + titleH + topH + h + footH + pad;
    const cv = document.createElement('canvas'); cv.width = W * SCALE; cv.height = H * SCALE;
    const ctx = cv.getContext('2d'); ctx.scale(SCALE, SCALE);
    ctx.fillStyle = '#FFFFFF'; ctx.fillRect(0, 0, W, H);
    ctx.textBaseline = 'alphabetic';
    let y = pad + 22;
    ctx.fillStyle = INK; ctx.font = `bold 21px ${FONT}`; ctx.fillText(title, pad, y);
    y += titleH - 22 + 14;
    ctx.font = `13px ${FONT}`; ctx.fillStyle = INK;
    ctx.fillText(units, pad, y);
    if (unitsR) { ctx.textAlign = 'right'; ctx.fillText(unitsR.trim(), W - pad, y); ctx.textAlign = 'left'; }
    const legX = pad + (units ? ctx.measureText(units).width + 24 : 0);
    legRows.forEach((r, i) => {
      let x = legX; const ly = y + i * 20;
      r.forEach((l) => {
        ctx.fillStyle = l.color;
        if (l.kind === 'sw') ctx.fillRect(x, ly - 10, 11, 11);
        else if (l.kind === 'dot') { ctx.beginPath(); ctx.arc(x + 5, ly - 4.5, 4, 0, Math.PI * 2); ctx.fill(); }
        else if (l.dash) { ctx.fillRect(x, ly - 6, 6, 3); ctx.fillRect(x + 9, ly - 6, 6, 3); ctx.fillRect(x + 18, ly - 6, 4, 3); }
        else ctx.fillRect(x, ly - 6, 22, 3);
        ctx.fillStyle = INK; ctx.fillText(l.text, x + (l.kind === 'ln' ? 26 : 16), ly);
        x += l.iw;
      });
    });
    y += topH - 14;
    ctx.drawImage(img, pad, y, w, h);
    y += h + 18;
    ctx.font = `11px ${FONT}`; ctx.fillStyle = INK;
    srcLines.forEach((l, i) => ctx.fillText(l, pad, y + i * 14));
    ctx.font = `bold 11px ${FONT}`; ctx.fillStyle = '#EE6600'; ctx.textAlign = 'right';
    ctx.fillText('Asia Decoded', W - pad, y + (srcLines.length - 1) * 14);
    return cv;
  }

  async function renderTable(card) {
    const table = card.querySelector('table');
    if (!table) return null;
    const head = Array.from(table.querySelectorAll('thead th')).map((th) => th.textContent.trim());
    const body = Array.from(table.querySelectorAll('tbody tr')).filter((tr) => !tr.classList.contains('spacer') && !tr.hidden).map((tr) => ({
      bold: (tr.classList.contains('gdp') && table.id !== 'cpi-table') || tr.classList.contains('grp') || tr.classList.contains('lead'),
      muted: tr.classList.contains('agg'), sep: tr.classList.contains('sep'), sub: tr.classList.contains('sub'), gap: tr.classList.contains('gap'),
      cells: Array.from(tr.cells).map((td) => ({ text: td.dataset.label || td.textContent, neg: td.classList.contains('neg'), bg: td.style.background || '' })),
    }));
    if (!body.length) return null;
    const heat = table.id === 'cpi-heat-table';
    const pad = 18, cpad = 10, lineH = 24, gapH = 10, indent = 14;
    const centre = table.id === 'cpi-table' || table.id === 'cpi-movers-table' || heat;
    const m = document.createElement('canvas').getContext('2d');
    m.font = `14px ${FONT}`;
    const colW = head.map((h, j) => {
      const cellW = Math.max(...body.map((r) => (r.cells[j] ? m.measureText(r.cells[j].text).width + (j === 0 && r.sub ? indent : 0) : 0)));
      const hw = j === 0 ? m.measureText(h).width : Math.max(56, Math.min(m.measureText(h).width, 96));
      return Math.ceil(Math.max(cellW, hw) + cpad * 2);
    });
    const headLines = head.map((h, j) => (j === 0 ? [h] : wrap(m, h, colW[j] - cpad * 2)));
    const headH = Math.max(...headLines.map((l) => l.length)) * 17 + 10;
    const tableW = colW.reduce((a, b) => a + b, 0);
    const W = Math.max(tableW + pad * 2, 560);
    const title = (card.querySelector('h2') || {}).textContent || '';
    const units = ((card.querySelector('.ad-top .ad-units') || {}).textContent || '').trim();
    const src = ((card.querySelector('.ad-foot > span') || {}).textContent || '').trim();
    m.font = `11px ${FONT}`;
    const srcLines = wrap(m, src, W - pad * 2 - 110);
    const gaps = body.filter((r) => r.gap).length * gapH;
    const H = pad + 34 + (units ? 22 : 8) + (heat ? 6 : 0) + headH + body.length * lineH + gaps + 14 + srcLines.length * 14 + 12 + pad;
    const cv = document.createElement('canvas'); cv.width = W * SCALE; cv.height = H * SCALE;
    const ctx = cv.getContext('2d'); ctx.scale(SCALE, SCALE);
    ctx.fillStyle = '#FFFFFF'; ctx.fillRect(0, 0, W, H);
    let y = pad + 22;
    ctx.fillStyle = INK; ctx.font = `bold 21px ${FONT}`; ctx.fillText(title, pad, y);
    const xs = []; colW.reduce((x, w) => { xs.push(x); return x + w; }, pad);
    if (heat) { ctx.fillStyle = INK; ctx.fillRect(pad, y + 9, tableW, 1.2); }
    if (units) { y += 26; ctx.font = `13px ${FONT}`; ctx.fillText(units, pad, y); y += 10; } else { y += 12; }
    ctx.font = `bold 14px ${FONT}`;
    headLines.forEach((ls, j) => {
      const off = headH - 10 - ls.length * 17;
      ls.forEach((l, k) => {
        ctx.textAlign = j === 0 ? 'left' : (centre ? 'center' : 'right');
        ctx.fillText(l, j === 0 ? xs[j] + 2 : (centre ? xs[j] + colW[j] / 2 : xs[j] + colW[j] - cpad), y + off + 14 + k * 17);
      });
    });
    y += headH;
    if (!heat) { ctx.fillStyle = INK; ctx.fillRect(pad, y - 1, tableW, 1.2); }
    body.forEach((r) => {
      if (r.gap) y += gapH;
      if (r.sep) { ctx.fillStyle = '#A6A6A6'; ctx.fillRect(pad, y, tableW, 1); }
      ctx.font = `${r.bold ? 'bold ' : ''}14px ${FONT}`;
      r.cells.forEach((c, j) => {
        if (c.bg && j > 0) { ctx.fillStyle = c.bg; ctx.fillRect(xs[j] + 1, y + 1, colW[j] - 2, lineH - 2); }
        ctx.fillStyle = c.bg ? '#1a1a1a' : (c.neg ? '#BD1B21' : (r.muted && j === 0 ? '#868E96' : INK));
        ctx.textAlign = j === 0 ? 'left' : (centre ? 'center' : 'right');
        const x0 = xs[j] + 2 + (j === 0 && r.sub ? indent : 0);
        ctx.fillText(c.text, j === 0 ? x0 : (centre ? xs[j] + colW[j] / 2 : xs[j] + colW[j] - cpad), y + 16);
      });
      y += lineH;
      if (!heat) { ctx.fillStyle = '#D9D9D9'; ctx.fillRect(pad, y - 1, tableW, 1); }
    });
    if (heat) { y += 6; ctx.fillStyle = INK; ctx.fillRect(pad, y, tableW, 1.2); }
    ctx.textAlign = 'left';
    y += 18; ctx.font = `11px ${FONT}`; ctx.fillStyle = INK;
    srcLines.forEach((l, i) => ctx.fillText(l, pad, y + i * 14));
    ctx.font = `bold 11px ${FONT}`; ctx.fillStyle = '#EE6600'; ctx.textAlign = 'right';
    ctx.fillText('Asia Decoded', W - pad, y + (srcLines.length - 1) * 14);
    return cv;
  }

  function show(card, url) {
    const box = document.createElement('div'); box.className = 'ad-shot-box';
    const bar = document.createElement('div'); bar.className = 'ad-shot-bar';
    const note = document.createElement('span'); note.textContent = 'Right-click the image (or long-press on a phone) and choose Save image or Copy image.';
    const right = document.createElement('span'); right.style.display = 'flex'; right.style.gap = '8px';
    const copy = document.createElement('button'); copy.type = 'button'; copy.textContent = 'Copy image';
    copy.addEventListener('click', async () => {
      try {
        const bin = atob(url.split(',')[1]); const buf = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
        const blob = new Blob([buf], { type: 'image/png' });
        await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
        copy.textContent = 'Copied';
      } catch (err) {
        copy.textContent = 'Copy blocked: use right-click';
      }
      setTimeout(() => { copy.textContent = 'Copy image'; }, 3000);
    });
    const close = document.createElement('button'); close.type = 'button'; close.textContent = 'Close';
    right.append(copy, close); bar.append(note, right);
    const img = document.createElement('img'); img.src = url; img.alt = (card.querySelector('h2') || {}).textContent || 'Chart';
    box.append(bar, img);
    // Shown inside the card itself, so it appears where the chart is, wherever the page is scrolled.
    card.querySelectorAll(':scope > .ad-shot-box').forEach((n) => n.remove());
    const done = () => box.remove();
    close.addEventListener('click', done);
    document.addEventListener('keydown', function esc(e) { if (e.key === 'Escape') { done(); document.removeEventListener('keydown', esc); } });
    card.appendChild(box);
    try { box.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } catch (err) { /* older browsers */ }
  }

  document.querySelectorAll('.jg-card').forEach((card) => {
    const isTable = !card.querySelector('.jg-chart') && card.querySelector('table');
    if (!card.querySelector('.jg-chart') && !isTable) return;
    const foot = card.querySelector('.ad-foot'), brand = foot && foot.querySelector('.ad-brand');
    if (!brand) return;
    const right = document.createElement('span'); right.className = 'ad-right';
    const b = document.createElement('button'); b.className = 'ad-png'; b.type = 'button'; b.textContent = 'PNG';
    b.setAttribute('aria-label', isTable ? 'Download this table as a PNG' : 'Download this chart as a PNG');
    brand.replaceWith(right); right.append(b, brand);
    b.addEventListener('click', async () => {
      b.disabled = true;
      try { const cv = isTable ? await renderTable(card) : await render(card); if (cv) show(card, cv.toDataURL('image/png')); }
      catch (e) { b.textContent = 'PNG failed'; setTimeout(() => { b.textContent = 'PNG'; }, 2500); }
      finally { b.disabled = false; }
    });
  });
})();
