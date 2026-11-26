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

  const state = { model: "hybrid_gbm", which: "both", cats: null };
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
      if (best) showTip(describe(best.m), e); else hideTip();
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
  function timeline(rows) {
    const left = W < 560 ? 92 : 150, right = 10, top = 6, axis = 24;
    const x = (v) => left + (v - Y0) / (Y1 - Y0) * (W - left - right);
    const groups = cats.filter((c) => state.cats.has(c)).map((c) => ({ c, ms: rows.filter((m) => m.cat === c) }))
      .filter((g) => g.ms.length);
    let y = top;
    for (const g of groups) { g.h = Math.min(Math.max(g.ms.length * 0.4, 26), 150); g.y = y; y += g.h + 6; }
    const H = y + axis;
    let s = `<svg class="viz" viewBox="0 0 ${W} ${H}" role="img" aria-label="Timeline of manuscripts">`;
    for (let t = 1850; t <= 1910; t += 10) {
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
        const col = m.dated ? "var(--s1)" : "var(--s2)";
        if (hi - lo > 1) lines += `<line x1="${x(lo)}" x2="${x(hi)}" y1="${py}" y2="${py}" style="stroke:${col}" stroke-opacity="${m.dated ? 0.5 : 0.18}" stroke-width="1"/>`;
        dots += `<circle class="dot" cx="${px}" cy="${py}" r="3" style="fill:${col}"/>`;
        points.push({ x: px, y: py, m, lo: x(lo), hi: x(hi) });
      }
    }
    s += lines + dots + `<g class="hlg"></g></svg>`;
    return { svg: s, points };
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
    const xs = data.map((m) => m.xy[0]), ys = data.map((m) => m.xy[1]);   // fixed frame: all manuscripts
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const sx = (v) => (W - side) / 2 + pad + (v - x0) / (x1 - x0) * (side - 2 * pad);
    const sy = (v) => pad + (y1 - v) / (y1 - y0) * (H - 2 * pad);
    let s = `<svg class="viz" viewBox="0 0 ${W} ${H}" role="img" aria-label="Map of manuscripts by text features">`;
    s += `<rect x="${(W - side) / 2}" y="0" width="${side}" height="${H}" rx="8" style="fill:none;stroke:var(--grid)"/>`;
    const points = [];
    // undated (rings) first, dated (filled) on top
    const sorted = rows.slice().sort((a, b) => a.dated - b.dated);
    for (const m of sorted) {
      const px = sx(m.xy[0]), py = sy(m.xy[1]), c = yearColor(year(m));
      s += m.dated ? `<circle class="dot" cx="${px}" cy="${py}" r="3.5" style="fill:${c}"/>`
                   : `<circle cx="${px}" cy="${py}" r="3.2" style="fill:var(--surface);stroke:${c}" stroke-width="1.6"/>`;
      points.push({ x: px, y: py, m });
    }
    s += `<g class="hlg"></g></svg>`;
    return { svg: s, points };
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
    const key = [W, state.model, state.which, [...state.cats].join("|")].join("/");
    if (key === lastKey) return;
    lastKey = key;
    const rows = visible();
    const nd = rows.filter((m) => m.dated).length, nu = rows.length - nd;
    const tl = timeline(rows), mp = map(rows);
    const legend = `<div class="legend"><span style="--c:var(--s1)">Dated: catalogue date (line: source range)</span>
      <span style="--c:var(--s2)">Undated: ${esc(state.model)} estimate (line: 80% range)</span></div>`;
    let h = `<div class="tiles">
      <div class="tile"><div class="num">${fmt(rows.length)}</div><div class="lab">manuscripts shown</div></div>
      <div class="tile"><div class="num">${fmt(nd)}</div><div class="lab">dated</div></div>
      <div class="tile"><div class="num">${fmt(nu)}</div><div class="lab">undated, estimated by ${esc(state.model)}</div></div>
    </div>`;
    h += `<div class="block"><h2>Timeline</h2><p class="lead">One dot per manuscript, grouped by category. Hover a dot for its title and range.
      The undated estimates are pulled towards the 1890s, as in cross-validation.</p>${legend}<div id="all-tl">${tl.svg}</div></div>`;
    h += `<div class="block"><h2>Manuscripts per year</h2><p class="lead">Dated manuscripts by catalogue year, with the estimated years of the undated ones stacked on top.</p>
      <div class="legend"><span style="--c:var(--s1)">Dated</span><span style="--c:var(--s2)">Undated (estimated by ${esc(state.model)})</span></div>
      <div id="all-hist">${histogram(rows)}</div></div>`;
    h += `<div class="block"><h2>Map of the manuscripts</h2><p class="lead">t-SNE map of the text features (style + topics of the hybrid model): manuscripts that are close
      write in a similar style about similar subjects. Colour is the year; filled dots are dated, rings are undated (coloured by the estimate).
      Clusters with one colour suggest the features carry date information.</p>
      <div class="legend" style="align-items:center">≤${C0}<span class="ramp" style="${rampCss()}"></span>≥${C1}
      <span style="--c:var(--muted)">filled: dated</span><span style="--c:transparent;">○ ring: undated</span></div>
      <div id="all-map">${mp.svg}</div></div>`;
    h += `<details class="block" id="all-table"><summary>Show the ${fmt(rows.length)} manuscripts as a table</summary></details>`;
    $("all-body").innerHTML = h;

    wire($("all-tl").querySelector("svg"), tl.points, (q) => q && q.lo < q.hi - 1
      ? `<line x1="${q.lo}" x2="${q.hi}" y1="${q.y}" y2="${q.y}" class="hl"/><circle cx="${q.x}" cy="${q.y}" r="5" class="hl" style="fill:none"/>`
      : q ? `<circle cx="${q.x}" cy="${q.y}" r="5" class="hl" style="fill:none"/>` : "");
    wire($("all-map").querySelector("svg"), mp.points, (q) => q ? `<circle cx="${q.x}" cy="${q.y}" r="6" class="hl" style="fill:none"/>` : "");
    histTips($("all-hist").querySelector("svg"));
    $("all-table").addEventListener("toggle", (e) => { if (e.target.open) table(e.target, rows); }, { once: true });
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
      t += `<tr><td>${esc(m.id)}</td><td>${esc(m.title)}</td><td>${esc(m.cat)}</td><td class="n">${Math.round(year(m))}</td>
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
