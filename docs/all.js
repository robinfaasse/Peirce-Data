/* "All manuscripts" tab: timeline, stacked histogram and feature map of all
 * Peirce manuscripts, with a model selector and a category filter.
 * Data: model/manuscripts.json, written by code/dating/export_web.py. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const fmt = (n) => n.toLocaleString("en-US");
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const MODELS = { hybrid_gbm: "hybrid_gbm (best)", tfidf_ridge: "tfidf_ridge", style_gbm: "style_gbm" };
  const WHICH = { both: "Dated and undated", dated: "Dated only", undated: "Undated only" };
  const Y0 = 1850, Y1 = 1915;

  const state = { model: "hybrid_gbm", which: "both", cats: null, split: true,
                  tlDom: null, mapDom: null, tlMode: "zoom", mapMode: "zoom" };   // zoom domains (null = everything)
  let data = null, cats = [], W = 760, lastKey = "";

  // ----------------------------------------------------------------- data
  // Year shown for a manuscript: catalogue date if dated, else the estimate.
  const year = (m) => (m.dated ? m.date[0] : m.m[state.model][0]);
  const range = (m) => (m.dated ? [m.date[1], m.date[2] + 1] : [m.m[state.model][1], m.m[state.model][2]]);
  const visible = () => data.filter((m) => state.cats.has(m.cat) &&
    (state.which === "both" || (state.which === "dated") === m.dated));

  // Deterministic jitter per manuscript (no flicker between redraws).
  function jitter(id) {
    let h = 2166136261;
    for (let i = 0; i < id.length; i++) { h ^= id.charCodeAt(i); h = Math.imul(h, 16777619); }
    return ((h >>> 0) % 1000) / 1000;
  }

  // Year colour: one blue hue, light -> dark (light mode) or dark -> light (dark mode).
  const RAMP_LIGHT = ["#84b9f3", "#519ced", "#257de0", "#1b64be", "#0f4a96", "#0e3d7e"];
  const RAMP_DARK = ["#1b64be", "#257de0", "#338ced", "#6aabf1", "#9dc8f7", "#cce3fd"];
  const dark = () => window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches &&
    document.documentElement.dataset.theme !== "light";
  // Colour domain 1875-1912: almost all manuscripts fall here, earlier ones get the first step.
  const C0 = 1875, C1 = 1912;
  function yearColor(y) {
    const ramp = dark() ? RAMP_DARK : RAMP_LIGHT;
    const t = Math.min(Math.max((y - C0) / (C1 - C0), 0), 1) * (ramp.length - 1);
    const i = Math.min(Math.floor(t), ramp.length - 2), f = t - i;
    const a = hex(ramp[i]), b = hex(ramp[i + 1]);
    return `rgb(${a.map((v, k) => Math.round(v + (b[k] - v) * f)).join(",")})`;
  }
  const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));

  // -------------------------------------------------------------- tooltip
  let tip;
  function showTip(html, e) {
    if (!tip) { tip = document.createElement("div"); tip.className = "tip"; document.body.appendChild(tip); }
    tip.innerHTML = html;
    tip.style.display = "block";
    tip.style.whiteSpace = "normal";
    tip.style.maxWidth = "300px";
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.min(e.clientX + 14, window.innerWidth - w - 8) + "px";
    tip.style.top = (e.clientY - h - 12 < 4 ? e.clientY + 16 : e.clientY - h - 12) + "px";
  }
  const hideTip = () => { if (tip) tip.style.display = "none"; };

  const manuscriptUrl = (m) => "manuscript.html?id=" + encodeURIComponent(m.id);

  function describe(m) {
    const [p, lo, hi] = m.m[state.model];
    let s = `<b>${esc(m.title)}</b><br>${esc(m.id)} · ${esc(m.cat)} · ${fmt(m.words)} words`;
    if (m.dated) {
      const d = m.date[1] === m.date[2] ? `${m.date[1]}` : `${m.date[1]}-${m.date[2]}`;
      s += `<br>Catalogue date: <b>${d}</b>`;
      s += `<br>${esc(state.model)}${m.train ? " (cross-validated)" : ""}: ${Math.round(p)} (80%: ${Math.floor(lo)}-${Math.ceil(hi)})`;
    } else {
      s += `<br>Undated. ${esc(state.model)} estimate: <b>${Math.round(p)}</b><br>80% range: ${Math.floor(lo)}-${Math.ceil(hi)}`;
    }
    return s;
  }

  // Nearest point under the pointer, within 10px.
  function hover(svg, points, onHit) {
    const pt = svg.createSVGPoint();
    svg.addEventListener("pointermove", (e) => {
      pt.x = e.clientX; pt.y = e.clientY;
      const p = pt.matrixTransform(svg.getScreenCTM().inverse());
      const scale = svg.getBoundingClientRect().width / svg.viewBox.baseVal.width;
      let best = null, bd = (10 / scale) ** 2;
      for (const q of points) {
        const d = (q.x - p.x) ** 2 + (q.y - p.y) ** 2;
        if (d < bd) { bd = d; best = q; }
      }
      onHit(best);
      svg.style.cursor = best ? "pointer" : "default";
      current = best;
      if (best) showTip(describe(best.m) + `<br><i>Click to open the manuscript</i>`, e); else hideTip();
    });
    // Click (or tap) a dot: open the manuscript page in a new tab.
    let current = null;
    svg.addEventListener("click", (e) => {
      if (svg.dataset.dragged) return;                 // end of a zoom/pan drag, not a click
      svg.dispatchEvent(new PointerEvent("pointermove", { clientX: e.clientX, clientY: e.clientY }));
      if (current) window.open(manuscriptUrl(current.m), "_blank", "noopener");
    });
    svg.addEventListener("pointerleave", () => { onHit(null); hideTip(); });
  }

  // ------------------------------------------------------------ controls
  function pills(el, options, isOn, onClick, role) {
    el.innerHTML = Object.entries(options).map(([k, label]) =>
      `<button type="button" data-k="${esc(k)}" ${role === "radio" ? `role="radio" aria-checked="${isOn(k)}"` : `aria-pressed="${isOn(k)}"`}>${label}</button>`).join("");
    el.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => onClick(b.dataset.k)));
  }

  function renderControls() {
    pills($("all-model"), MODELS, (k) => state.model === k, (k) => { state.model = k; update(); }, "radio");
    pills($("all-which"), WHICH, (k) => state.which === k, (k) => { state.which = k; update(); }, "radio");
    const counts = {};
    for (const m of data) counts[m.cat] = (counts[m.cat] || 0) + 1;
    const opts = { __all: `All<span class="c">${fmt(data.length)}</span>` };
    for (const c of cats) opts[c] = `${esc(c)}<span class="c">${counts[c]}</span>`;
    const allOn = state.cats.size === cats.length;
    pills($("all-cats"), opts, (k) => (k === "__all" ? allOn : !allOn && state.cats.has(k)), (k) => {
      if (k === "__all") state.cats = new Set(cats);
      else if (allOn) state.cats = new Set([k]);          // first click: only this category
      else {
        state.cats.has(k) ? state.cats.delete(k) : state.cats.add(k);
        if (!state.cats.size) state.cats = new Set(cats);
      }
      update();
    });
  }

  // --------------------------------------------------------------- charts
  function niceStep(span) {
    for (const st of [1, 2, 5, 10, 20]) if (span / st <= (W < 560 ? 6 : 10)) return st;
    return 20;
  }

  function timeline(rows) {
    const left = W < 560 ? 92 : 150, right = 10, top = 6, axis = 24;
    const [a, b] = state.tlDom || [Y0, Y1];
    const x = (v) => left + (v - a) / (b - a) * (W - left - right);
    // Per category: one row each. Together: all selected categories in one row.
    const groups = state.split
      ? cats.filter((c) => state.cats.has(c)).map((c) => ({ c, ms: rows.filter((m) => m.cat === c) })).filter((g) => g.ms.length)
      : (rows.length ? [{ c: state.cats.size === cats.length ? "All" : `${state.cats.size} categor${state.cats.size === 1 ? "y" : "ies"}`, ms: rows }] : []);
    let y = top;
    for (const g of groups) {
      g.h = state.split ? Math.min(Math.max(g.ms.length * 0.4, 26), 150) : Math.min(Math.max(g.ms.length * 0.3, 60), 460);
      g.y = y; y += g.h + 6;
    }
    const H = y + axis;
    let s = `<svg class="viz" viewBox="0 0 ${W} ${H}" role="img" aria-label="Timeline of manuscripts">
      <clipPath id="tl-clip"><rect x="${left}" y="0" width="${W - left - right}" height="${H}"/></clipPath>`;
    const step = niceStep(b - a);
    for (let t = Math.ceil(a / step) * step; t <= b; t += step) {
      s += `<line x1="${x(t)}" x2="${x(t)}" y1="${top}" y2="${H - axis}" style="stroke:var(--grid)"/>`;
      s += `<text x="${x(t)}" y="${H - 8}" text-anchor="middle">${t}</text>`;
    }
    const points = [];
    let lines = "", dots = "";
    for (const g of groups) {
      const lab = W < 560 && g.c.length > 13 ? g.c.slice(0, 12) + "…" : g.c;
      s += `<text class="ink" x="${left - 8}" y="${g.y + g.h / 2 + 4}" text-anchor="end">${esc(lab)}</text>`;
      s += `<line x1="${left}" x2="${W - right}" y1="${g.y + g.h + 3}" y2="${g.y + g.h + 3}" style="stroke:var(--grid)"/>`;
      for (const m of g.ms) {
        const py = g.y + 4 + jitter(m.id) * (g.h - 8), px = x(year(m)), [lo, hi] = range(m);
        if (hi < a || lo > b) continue;                    // outside the zoomed window
        const col = m.dated ? "var(--s1)" : "var(--s2)";
        if (hi - lo > 1) lines += `<line x1="${x(lo)}" x2="${x(hi)}" y1="${py}" y2="${py}" style="stroke:${col}" stroke-opacity="${m.dated ? 0.5 : 0.18}" stroke-width="1"/>`;
        if (px < left - 1 || px > W - right + 1) continue;
        dots += `<circle class="dot" cx="${px}" cy="${py}" r="3" style="fill:${col}"/>`;
        points.push({ x: px, y: py, m, lo: Math.max(x(lo), left), hi: Math.min(x(hi), W - right) });
      }
    }
    s += `<g class="content"><g clip-path="url(#tl-clip)">${lines}</g>${dots}</g><g class="hlg"></g><g class="zoomg"></g></svg>`;
    const plot = { x0: left, x1: W - right, y0: top, y1: H - axis };
    return { svg: s, points, plot, toData: (px) => a + (px - left) / (W - left - right) * (b - a) };
  }

  function histogram(rows) {
    const H = W < 560 ? 200 : 240, left = 40, bottom = 26, top = 8;
    const years = []; for (let y = Y0; y < Y1; y++) years.push(y);
    const dated = years.map(() => 0), und = years.map(() => 0);
    for (const m of rows) {
      const i = Math.min(Math.max(Math.floor(year(m)) - Y0, 0), years.length - 1);
      (m.dated ? dated : und)[i]++;
    }
    const tot = years.map((_, i) => dated[i] + und[i]);
    const maxV = Math.max(1, ...tot);
    const p = Math.pow(10, Math.floor(Math.log10(maxV)));
    const max = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].map((k) => k * p).find((v) => v >= maxV);
    const slot = (W - left) / years.length, bw = Math.max(slot - 2, 1);
    const yy = (v) => v / max * (H - bottom - top);
    let s = `<svg class="viz" viewBox="0 0 ${W} ${H}" role="img" aria-label="Manuscripts per year">`;
    for (let t = 0; t <= 4; t++) {
      const gy = H - bottom - yy(max * t / 4);
      s += `<line x1="${left}" x2="${W}" y1="${gy}" y2="${gy}" style="stroke:var(--grid)"/>`;
      s += `<text x="${left - 8}" y="${gy + 4}" text-anchor="end">${fmt(max * t / 4)}</text>`;
    }
    years.forEach((y, i) => {
      const bx = left + i * slot + (slot - bw) / 2, base = H - bottom;
      const hd = yy(dated[i]), hu = yy(und[i]);
      const tipTxt = `<b>${y}</b><br>Dated: ${dated[i]}<br>Undated, estimated: ${und[i]}`;
      s += `<g class="row" data-tip="${esc(tipTxt)}"><rect class="hit" x="${left + i * slot}" y="${top}" width="${slot}" height="${H - bottom - top}"/>`;
      // dated at the baseline, undated on top with a 2px gap; rounded top on the topmost segment only
      if (hd > 0) s += `<path d="${bar(bx, base, bw, hd, und[i] === 0)}" style="fill:var(--s1)"/>`;
      if (hu > 0) s += `<path d="${bar(bx, base - hd - (hd > 0 ? 2 : 0), bw, hu, true)}" style="fill:var(--s2)"/>`;
      s += `</g>`;
      if (y % (W < 560 ? 20 : 10) === 0) s += `<text x="${left + i * slot + slot / 2}" y="${H - 8}" text-anchor="middle">${y}</text>`;
    });
    return s + `</svg>`;
  }
  function bar(x, base, w, h, round) {
    const r = round ? Math.min(3, w / 2, h) : 0;
    return `M${x},${base}v-${h - r}` + (r ? `a${r},${r} 0 0 1 ${r},-${r}h${w - 2 * r}a${r},${r} 0 0 1 ${r},${r}` : `h${w}`) + `v${h - r}z`;
  }

  function map(rows) {
    const side = Math.min(W, 640), H = side, pad = 10;
    const [x0, x1, y0, y1] = state.mapDom || mapExtent();
    const ox = (W - side) / 2;
    const sx = (v) => ox + pad + (v - x0) / (x1 - x0) * (side - 2 * pad);
    const sy = (v) => pad + (y1 - v) / (y1 - y0) * (H - 2 * pad);
    let s = `<svg class="viz" viewBox="0 0 ${W} ${H}" role="img" aria-label="Map of manuscripts by text features">`;
    s += `<rect x="${(W - side) / 2}" y="0" width="${side}" height="${H}" rx="8" style="fill:none;stroke:var(--grid)"/>`;
    const points = [];
    s += `<clipPath id="map-clip"><rect x="${ox}" y="0" width="${side}" height="${H}" rx="8"/></clipPath><g clip-path="url(#map-clip)"><g class="content">`;
    // undated (rings) first, dated (filled) on top
    const sorted = rows.slice().sort((a, b) => a.dated - b.dated);
    for (const m of sorted) {
      const px = sx(m.xy[0]), py = sy(m.xy[1]), c = yearColor(year(m));
      if (px < ox + 2 || px > ox + side - 2 || py < 2 || py > H - 2) continue;   // outside the zoomed window
      s += m.dated ? `<circle class="dot" cx="${px}" cy="${py}" r="3.5" style="fill:${c}"/>`
                   : `<circle cx="${px}" cy="${py}" r="3.2" style="fill:var(--surface);stroke:${c}" stroke-width="1.6"/>`;
      points.push({ x: px, y: py, m });
    }
    s += `</g></g><g class="hlg"></g><g class="zoomg"></g></svg>`;
    const plot = { x0: ox, x1: ox + side, y0: 0, y1: H };
    const toData = (px, py) => [x0 + (px - ox - pad) / (side - 2 * pad) * (x1 - x0), y1 - (py - pad) / (H - 2 * pad) * (y1 - y0)];
    return { svg: s, points, plot, toData };
  }

  // Square frame around all manuscripts (t-SNE axes have no units; keep them equal).
  function mapExtent() {
    const xs = data.map((m) => m.xy[0]), ys = data.map((m) => m.xy[1]);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    const r = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) / 2;
    return [cx - r, cx + r, cy - r, cy + r];
  }

  function rampCss() {
    const ramp = dark() ? RAMP_DARK : RAMP_LIGHT;
    return `background:linear-gradient(90deg,${ramp.join(",")})`;
  }

  // --------------------------------------------------------------- render
  function update() {
    renderControls();
    lastKey = "";
    render();
  }

  function render() {
    W = Math.max(300, Math.floor($("all-body").clientWidth - 42));
    const key = [W, state.model, state.which, state.split, [...state.cats].join("|")].join("/");
    if (key === lastKey) return;
    lastKey = key;
    const rows = visible();
    const nd = rows.filter((m) => m.dated).length, nu = rows.length - nd;
    currentRows = rows;
    const legend = `<div class="legend"><span style="--c:var(--s1)">Dated: catalogue date (line: source range)</span>
      <span style="--c:var(--s2)">Undated: ${esc(state.model)} estimate (line: 80% range)</span></div>`;
    let h = `<div class="tiles">
      <div class="tile"><div class="num">${fmt(rows.length)}</div><div class="lab">manuscripts shown</div></div>
      <div class="tile"><div class="num">${fmt(nd)}</div><div class="lab">dated</div></div>
      <div class="tile"><div class="num">${fmt(nu)}</div><div class="lab">undated, estimated by ${esc(state.model)}</div></div>
    </div>`;
    h += `<div class="block"><h2>Timeline</h2>
      <div class="ctl" style="margin:6px 0 8px"><span class="ctl-lab">Categories</span><div class="pills" id="all-split" role="radiogroup" aria-label="Timeline layout">
        <button type="button" role="radio" data-k="1" aria-checked="${state.split}">Each in its own row</button>
        <button type="button" role="radio" data-k="0" aria-checked="${!state.split}">All together</button></div></div>
      <p class="lead">One dot per manuscript${state.split ? ", grouped by category" : ""}. Hover a dot for its title, category and range; click it to open the manuscript.
      The undated estimates are pulled towards the 1890s, as in cross-validation.</p>${legend}${zoomBar("tl")}<div id="all-tl"></div></div>`;
    h += `<div class="block"><h2>Manuscripts per year</h2><p class="lead">Dated manuscripts by catalogue year, with the estimated years of the undated ones stacked on top.</p>
      <div class="legend"><span style="--c:var(--s1)">Dated</span><span style="--c:var(--s2)">Undated (estimated by ${esc(state.model)})</span></div>
      <div id="all-hist">${histogram(rows)}</div></div>`;
    h += `<div class="block"><h2>Map of the manuscripts</h2><p class="lead">t-SNE map of the text features (style + topics of the hybrid model): manuscripts that are close
      write in a similar style about similar subjects. Colour is the year; filled dots are dated, rings are undated (coloured by the estimate).
      Clusters with one colour suggest the features carry date information. Click a dot to open the manuscript.</p>
      <div class="legend" style="align-items:center">≤${C0}<span class="ramp" style="${rampCss()}"></span>≥${C1}
      <span style="--c:var(--muted)">filled: dated</span><span style="--c:transparent;">○ ring: undated</span></div>
      ${zoomBar("map")}<div id="all-map"></div></div>`;
    h += `<details class="block" id="all-table"><summary>Show the ${fmt(rows.length)} manuscripts as a table</summary></details>`;
    $("all-body").innerHTML = h;
    $("all-split").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      state.split = b.dataset.k === "1";
      lastKey = "";
      render();
    }));

    drawTl();
    drawMap();
    wireZoomBar("tl");
    wireZoomBar("map");
    histTips($("all-hist").querySelector("svg"));
    $("all-table").addEventListener("toggle", (e) => { if (e.target.open) table(e.target, rows); }, { once: true });
  }

  // ----------------------------------------------------------------- zoom
  // Timeline: zoom on the years (x). Map: zoom on both axes, kept square.
  // Drag a box to zoom (or drag to pan in Pan mode), Ctrl/Cmd + scroll or the
  // +/- buttons to zoom around a point, Reset to see everything again.
  let currentRows = [];
  const FULL_TL = [Y0, Y1];

  function drawTl() {
    const tl = timeline(currentRows);
    $("all-tl").innerHTML = tl.svg;
    const svg = $("all-tl").querySelector("svg");
    wire(svg, tl.points, (q) => q && q.lo < q.hi - 1
      ? `<line x1="${q.lo}" x2="${q.hi}" y1="${q.y}" y2="${q.y}" class="hl"/><circle cx="${q.x}" cy="${q.y}" r="5" class="hl" style="fill:none"/>`
      : q ? `<circle cx="${q.x}" cy="${q.y}" r="5" class="hl" style="fill:none"/>` : "");
    zoomable(svg, tl, "tl");
    zoomLabel("tl");
  }

  function drawMap() {
    const mp = map(currentRows);
    $("all-map").innerHTML = mp.svg;
    const svg = $("all-map").querySelector("svg");
    wire(svg, mp.points, (q) => q ? `<circle cx="${q.x}" cy="${q.y}" r="6" class="hl" style="fill:none"/>` : "");
    zoomable(svg, mp, "map");
    zoomLabel("map");
  }

  function zoomBar(kind) {
    const mode = kind === "tl" ? state.tlMode : state.mapMode;
    return `<div class="zoombar" id="zb-${kind}">
      <button type="button" data-z="in" aria-label="Zoom in">+</button>
      <button type="button" data-z="out" aria-label="Zoom out">&minus;</button>
      <button type="button" data-z="reset">Reset</button>
      <span class="zsep"></span>
      <span class="zlab">Drag to</span>
      <div class="pills" role="radiogroup" aria-label="Drag mode">
        <button type="button" role="radio" data-mode="zoom" aria-checked="${mode === "zoom"}">zoom to a box</button>
        <button type="button" role="radio" data-mode="pan" aria-checked="${mode === "pan"}">pan</button>
      </div>
      <span class="zlab zhint">Ctrl/⌘ + scroll also zooms</span>
      <span class="zlab zstate" id="zs-${kind}"></span>
    </div>`;
  }

  function wireZoomBar(kind) {
    const bar = $("zb-" + kind);
    bar.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.mode) {
        state[kind + "Mode"] = b.dataset.mode;
        bar.querySelectorAll("[data-mode]").forEach((x) => x.setAttribute("aria-checked", x.dataset.mode === b.dataset.mode));
        return;
      }
      if (b.dataset.z === "reset") setDom(kind, null);
      else zoomAround(kind, null, b.dataset.z === "in" ? 0.5 : 2);
    });
  }

  function zoomLabel(kind) {
    const el = $("zs-" + kind);
    if (!el) return;
    if (kind === "tl") {
      const d = state.tlDom;
      el.textContent = d ? `Showing ${Math.round(d[0])}–${Math.round(d[1])}` : "";
    } else {
      el.textContent = state.mapDom ? `Zoomed ${(fullSpan() / (state.mapDom[1] - state.mapDom[0])).toFixed(1)}×` : "";
    }
  }

  const fullSpan = () => { const e = mapExtent(); return e[1] - e[0]; };

  function setDom(kind, dom) {
    if (kind === "tl") {
      if (dom) {
        let [a, b] = dom;
        if (b - a < 2) { const c = (a + b) / 2; a = c - 1; b = c + 1; }
        if (b - a >= Y1 - Y0) dom = null;
        else {
          if (a < Y0) { b += Y0 - a; a = Y0; }
          if (b > Y1) { a -= b - Y1; b = Y1; }
          dom = [a, b];
        }
      }
      state.tlDom = dom;
      drawTl();
    } else {
      if (dom) {
        // keep the window square and at least 2% of the full map
        const full = mapExtent(), fs = full[1] - full[0];
        let cx = (dom[0] + dom[1]) / 2, cy = (dom[2] + dom[3]) / 2;
        let r = Math.max(dom[1] - dom[0], dom[3] - dom[2], fs * 0.02) / 2;
        if (2 * r >= fs) dom = null;
        else {
          cx = Math.min(Math.max(cx, full[0] + r), full[1] - r);
          cy = Math.min(Math.max(cy, full[2] + r), full[3] - r);
          dom = [cx - r, cx + r, cy - r, cy + r];
        }
      }
      state.mapDom = dom;
      drawMap();
    }
  }

  // factor < 1 zooms in. center: data coordinate ([x] or [x, y]) or null for the middle.
  function zoomAround(kind, center, factor) {
    if (kind === "tl") {
      const [a, b] = state.tlDom || FULL_TL;
      const c = center ? center[0] : (a + b) / 2;
      setDom("tl", [c - (c - a) * factor, c + (b - c) * factor]);
    } else {
      const [x0, x1, y0, y1] = state.mapDom || mapExtent();
      const cx = center ? center[0] : (x0 + x1) / 2, cy = center ? center[1] : (y0 + y1) / 2;
      setDom("map", [cx - (cx - x0) * factor, cx + (x1 - cx) * factor, cy - (cy - y0) * factor, cy + (y1 - cy) * factor]);
    }
  }

  function zoomable(svg, chart, kind) {
    const g = svg.querySelector(".zoomg"), content = svg.querySelector(".content"), P = chart.plot;
    const pt = svg.createSVGPoint();
    const toSvg = (e) => { pt.x = e.clientX; pt.y = e.clientY; return pt.matrixTransform(svg.getScreenCTM().inverse()); };
    const inPlot = (p) => p.x >= P.x0 && p.x <= P.x1 && p.y >= P.y0 && p.y <= P.y1;
    const clampX = (x) => Math.min(Math.max(x, P.x0), P.x1), clampY = (y) => Math.min(Math.max(y, P.y0), P.y1);
    const data = (x, y) => (kind === "tl" ? [chart.toData(x)] : chart.toData(x, y));
    let start = null, dragging = false;

    svg.style.touchAction = "pan-y";
    svg.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      const p = toSvg(e);
      if (!inPlot(p)) return;
      start = p; dragging = false;
      svg.setPointerCapture(e.pointerId);
    });
    svg.addEventListener("pointermove", (e) => {
      if (!start) return;
      const p = toSvg(e);
      if (!dragging && Math.hypot(p.x - start.x, p.y - start.y) < 5) return;
      dragging = true;
      hideTip();
      const mode = state[kind + "Mode"];
      if (mode === "pan") {
        const dx = p.x - start.x, dy = kind === "tl" ? 0 : p.y - start.y;
        content.setAttribute("transform", `translate(${dx},${dy})`);
      } else {
        const x0 = clampX(Math.min(start.x, p.x)), x1 = clampX(Math.max(start.x, p.x));
        const y0 = kind === "tl" ? P.y0 : clampY(Math.min(start.y, p.y)), y1 = kind === "tl" ? P.y1 : clampY(Math.max(start.y, p.y));
        g.innerHTML = `<rect class="zbox" x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}"/>`;
      }
    });
    const finish = (e) => {
      if (!start) return;
      const p = toSvg(e), s0 = start;
      start = null;
      if (!dragging) return;
      svg.dataset.dragged = "1";
      setTimeout(() => { delete svg.dataset.dragged; }, 0);
      if (state[kind + "Mode"] === "pan") {
        const a = data(s0.x, s0.y), b = data(p.x, p.y);
        if (kind === "tl") {
          const [d0, d1] = state.tlDom || FULL_TL, d = a[0] - b[0];
          setDom("tl", [d0 + d, d1 + d]);
        } else {
          const [x0, x1, y0, y1] = state.mapDom || mapExtent(), dx = a[0] - b[0], dy = a[1] - b[1];
          setDom("map", [x0 + dx, x1 + dx, y0 + dy, y1 + dy]);
        }
      } else {
        g.innerHTML = "";
        if (Math.abs(p.x - s0.x) < 6 && (kind === "tl" || Math.abs(p.y - s0.y) < 6)) return;
        const a = data(clampX(Math.min(s0.x, p.x)), clampY(Math.max(s0.y, p.y)));
        const b = data(clampX(Math.max(s0.x, p.x)), clampY(Math.min(s0.y, p.y)));
        setDom(kind, kind === "tl" ? [a[0], b[0]] : [a[0], b[0], a[1], b[1]]);
      }
    };
    svg.addEventListener("pointerup", finish);
    svg.addEventListener("pointercancel", () => { start = null; g.innerHTML = ""; content.removeAttribute("transform"); });
    svg.addEventListener("wheel", (e) => {
      if (!(e.ctrlKey || e.metaKey)) return;           // plain scrolling keeps scrolling the page
      const p = toSvg(e);
      if (!inPlot(p)) return;
      e.preventDefault();
      zoomAround(kind, data(p.x, p.y), e.deltaY < 0 ? 0.8 : 1.25);
    }, { passive: false });
  }

  function wire(svg, points, highlight) {
    const g = svg.querySelector(".hlg");
    hover(svg, points, (q) => { g.innerHTML = highlight(q); });
  }

  function histTips(svg) {
    svg.addEventListener("pointermove", (e) => {
      const row = e.target.closest("[data-tip]");
      if (row) showTip(row.dataset.tip, e); else hideTip();
    });
    svg.addEventListener("pointerleave", hideTip);
  }

  function table(el, rows) {
    const sorted = rows.slice().sort((a, b) => year(a) - year(b));
    let t = `<table><tr><th>Manuscript</th><th>Title</th><th>Category</th><th class="n">Year</th><th class="n">Range</th><th>Status</th></tr>`;
    for (const m of sorted) {
      const [lo, hi] = m.dated ? [m.date[1], m.date[2]] : [Math.floor(m.m[state.model][1]), Math.ceil(m.m[state.model][2])];
      t += `<tr><td><a href="${manuscriptUrl(m)}" target="_blank" rel="noopener">${esc(m.id)}</a></td><td>${esc(m.title)}</td><td>${esc(m.cat)}</td><td class="n">${Math.round(year(m))}</td>
        <td class="n">${lo}-${hi}</td><td>${m.dated ? "dated" : "estimated"}</td></tr>`;
    }
    el.insertAdjacentHTML("beforeend", t + `</table>`);
  }

  // ----------------------------------------------------------------- init
  async function show() {
    if (data) { render(); return; }
    try {
      const res = await fetch("model/manuscripts.json");
      if (!res.ok) throw new Error("HTTP " + res.status);
      data = await res.json();
    } catch (err) {
      $("all-body").innerHTML = `<div class="note err">Could not load the manuscripts: ${esc(err.message)}</div>`;
      return;
    }
    const counts = {};
    for (const m of data) counts[m.cat] = (counts[m.cat] || 0) + 1;
    cats = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
    state.cats = new Set(cats);
    update();
  }

  let timer;
  window.addEventListener("resize", () => {
    clearTimeout(timer);
    timer = setTimeout(() => { if (data && !$("view-all").classList.contains("hidden")) render(); }, 150);
  });
  window.PeirceAll = { show };
})();
