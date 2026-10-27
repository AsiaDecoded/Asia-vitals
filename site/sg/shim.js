// Stand-in for the claude.ai dashboard runtime: loads the CSV/JSON files next to the page
// and runs the page's calculations, so the same page code works on any static host.
(() => {
  const SRC = {
    sg_cpi: 'data/sg_cpi.csv', sg_cpi_contrib: 'data/sg_cpi_contrib.csv', sg_cpi_diffusion: 'data/sg_cpi_diffusion.csv',
    sg_cpi_items: 'data/sg_cpi_items.csv', sg_ppi: 'data/sg_ppi.csv',
    cpi_release: 'data/cpi_release.json', ppi_release: 'data/ppi_release.json',
  };
  const store = {}, calcs = {}, subs = [];
  let queued = false;
  const notify = () => {
    if (queued) return; queued = true;
    requestAnimationFrame(() => { queued = false; subs.forEach((fn) => { try { fn(); } catch (e) { console.error(e); } }); });
  };
  const reset = () => Object.values(calcs).forEach((c) => { c.cache = null; });
  function load(id) {
    if (store[id]) return;
    store[id] = { status: 'loading', data: [] };
    fetch(SRC[id], { cache: 'no-cache' })
      .then((r) => { if (!r.ok) throw new Error(r.status); return SRC[id].endsWith('.json') ? r.json() : r.text().then((t) => d3.csvParse(t)); })
      .then((d) => { store[id] = { status: 'ok', data: Array.isArray(d) ? d : (d.rows || d.data || []) }; })
      .catch((e) => { console.error(id, e); store[id] = { status: 'error', data: [] }; })
      .finally(() => { reset(); notify(); });
  }
  function run(id) {
    const c = calcs[id];
    if (c.cache) return c.cache;
    const ins = c.inputs.map((i) => data(i));
    if (ins.some((x) => x.status === 'error' || x.status === 'missing')) return (c.cache = { status: 'error', data: [] });
    if (ins.some((x) => x.status !== 'ok')) return { status: 'loading', data: [] };
    try { c.cache = { status: 'ok', data: c.fn(...ins.map((x) => x.data)) }; } catch (e) { console.error(id, e); c.cache = { status: 'error', data: [] }; }
    return c.cache;
  }
  function data(id) {
    if (calcs[id]) return run(id);
    if (!SRC[id]) return { status: 'missing', data: [] };
    load(id);
    return store[id];
  }
  let lastW = window.innerWidth;
  window.addEventListener('resize', () => { if (window.innerWidth !== lastW) { lastW = window.innerWidth; notify(); } });
  window.dash = {
    data,
    calc(id, def) { calcs[id] = { inputs: def.inputs, fn: def.fn, cache: null }; },
    onData(fn) { subs.push(fn); try { fn(); } catch (e) { console.error(e); } },
    setLink(name) { try { history.replaceState(null, '', '#' + name); } catch (e) { /* ignore */ } },
    params: () => ({}), setParams() {}, resetParams() {}, refresh() {},
    colors: ['#0C84FF', '#BD1B21', '#EE6631', '#495057', '#FFC000', '#92D050', '#954F72', '#44546A'],
  };
})();
