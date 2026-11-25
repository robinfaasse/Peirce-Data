/* "About the dataset" tab: view switching, numbers and charts.
 * Data: model/dataset.json, written by code/dating/export_web.py. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const fmt = (n) => n.toLocaleString("en-US");
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const NS = "http://www.w3.org/2000/svg";

  // ------------------------------------------------------------ view switch
  function show(view) {
    if (view !== "dataset") view = "estimate";
    document.querySelectorAll(".views a").forEach((a) => {
      if (a.dataset.view === view) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    $("view-estimate").classList.toggle("hidden", view !== "estimate");
    $("view-dataset").classList.toggle("hidden", view !== "dataset");
    if (view === "dataset") load();
  }
  window.addEventListener("hashchange", () => show(location.hash.slice(1)));
  document.addEventListener("DOMContentLoaded", () => show(location.hash.slice(1)));

  // ------------------------------------------------------------- tooltip
  let tip;
  function tooltip(svg) {
    if (!tip) { tip = document.createElement("div"); tip.className = "tip"; document.body.appendChild(tip); }
    svg.addEventListener("pointermove", (e) => {
      const row = e.target.closest("[data-tip]");
      if (!row) { tip.style.display = "none"; return; }
      tip.innerHTML = row.dataset.tip;
      tip.style.display = "block";
      const w = tip.offsetWidth;
      const x = Math.min(e.clientX + 12, window.innerWidth - w - 8);
      tip.style.left = x + "px";
      tip.style.top = (e.clientY - 36) + "px";
    });
    svg.addEventListener("pointerleave", () => { tip.style.display = "none"; });
  }

  // ------------------------------------------------------------- helpers
  function niceMax(v) {
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
    return 10 * p;
  }
  // Bar with 4px rounded data end, square at the baseline.
  function hbarPath(x, y, w, h) {
    const r = Math.min(4, w / 2, h / 2);
    if (w <= 0) return "";
    return `M${x},${y}h${w - r}a${r},${r} 0 0 1 ${r},${r}v${h - 2 * r}a${r},${r} 0 0 1 -${r},${r}h-${w - r}z`;
  }
  function vbarPath(x, base, w, h) {
    const r = Math.min(4, w / 2, h / 2);
    if (h <= 0) return "";
    return `M${x},${base}v-${h - r}a${r},${r} 0 0 1 ${r},-${r}h${w - 2 * r}a${r},${r} 0 0 1 ${r},${r}v${h - r}z`;
  }
  function table(head, rows) {
    return `<details><summary>Show as table</summary><table><tr>${head.map((h, i) => `<th${i ? ' class="n"' : ""}>${esc(h)}</th>`).join("")}</tr>` +
      rows.map((r) => `<tr>${r.map((c, i) => `<td${i ? ' class="n"' : ""}>${typeof c === "number" ? fmt(c) : esc(c)}</td>`).join("")}</tr>`).join("") +
      `</table></details>`;
  }

  /* Horizontal bars, one or two series per row. rows: [{label, values:[...]}]. */
  // Charts are drawn at the container's real width so text stays 12px on phones.
  let W = 760;
  const narrow = () => W < 560;

  function hbars(rows, series, opts = {}) {
    const labelW = narrow() ? 120 : (opts.labelW || 190), valueW = 48, barH = series.length > 1 ? 9 : 16;
    const gap = 2, rowH = series.length * barH + (series.length - 1) * gap + 12;
    const H = rows.length * rowH + 22;
    const max = niceMax(Math.max(...rows.flatMap((r) => r.values)));
    const x = (v) => v / max * (W - labelW - valueW);
    let s = `<svg class="viz" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.aria || "")}">`;
    const ticks = narrow() ? 2 : 4;
    for (let t = 0; t <= ticks; t++) {
      const gx = labelW + x(max * t / ticks);
      s += `<line x1="${gx}" x2="${gx}" y1="0" y2="${H - 18}" style="stroke:var(--grid)"/>`;
      s += `<text x="${gx}" y="${H - 4}" text-anchor="middle">${fmt(max * t / ticks)}</text>`;
    }
    rows.forEach((r, i) => {
      const y0 = i * rowH + 6;
      const tipText = `<b>${esc(r.label)}</b>` + r.values.map((v, k) => `<br>${esc(series[k].name)}: ${fmt(v)}`).join("") + (r.note ? `<br>${esc(r.note)}` : "");
      s += `<g class="row" data-tip="${esc(tipText)}"><rect class="hit" x="0" y="${y0 - 5}" width="${W}" height="${rowH}" rx="4"/>`;
      const lab = narrow() && r.label.length > 17 ? r.label.slice(0, 16) + "…" : r.label;
      s += `<text class="ink" x="${labelW - 8}" y="${y0 + (rowH - 12) / 2 + 4}" text-anchor="end">${esc(lab)}</text>`;
      r.values.forEach((v, k) => {
        const by = y0 + k * (barH + gap);
        s += `<path d="${hbarPath(labelW, by, x(v), barH)}" style="fill:var(${series[k].color})"/>`;
        s += `<text x="${labelW + x(v) + 6}" y="${by + barH / 2 + 4}">${fmt(v)}</text>`;
      });
      s += `</g>`;
    });
    return s + `</svg>`;
  }

  /* Vertical bars, one or two series per category. */
  function vbars(labels, seriesValues, series, opts = {}) {
    const H = narrow() ? 200 : 260, left = 40, bottom = 26, top = 8;
    const n = labels.length, slot = (W - left) / n;
    const groupW = slot * (opts.fill || 0.8), barW = (groupW - (series.length - 1) * 2) / series.length;
    const max = niceMax(Math.max(...seriesValues.flat()));
    const y = (v) => v / max * (H - bottom - top);
    let s = `<svg class="viz" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.aria || "")}">`;
    for (let t = 0; t <= 4; t++) {
      const gy = H - bottom - y(max * t / 4);
      s += `<line x1="${left}" x2="${W}" y1="${gy}" y2="${gy}" style="stroke:var(--grid)"/>`;
      s += `<text x="${left - 8}" y="${gy + 4}" text-anchor="end">${fmt(max * t / 4)}</text>`;
    }
    labels.forEach((lab, i) => {
      const gx = left + i * slot + (slot - groupW) / 2;
      const tipText = `<b>${esc(opts.tipLabel ? opts.tipLabel(lab) : lab)}</b>` + series.map((sr, k) => `<br>${esc(sr.name)}: ${fmt(seriesValues[k][i])}`).join("");
      s += `<g class="row" data-tip="${esc(tipText)}"><rect class="hit" x="${left + i * slot}" y="${top}" width="${slot}" height="${H - bottom - top}"/>`;
      series.forEach((sr, k) => {
        const v = seriesValues[k][i];
        s += `<path d="${vbarPath(gx + k * (barW + 2), H - bottom, barW, y(v))}" style="fill:var(${sr.color})"/>`;
      });
      s += `</g>`;
      const every = opts.every ? opts.every * (narrow() ? 2 : 1) : (narrow() && n > 5 ? 2 : 1);
      if (i % every === 0) {
        s += `<text x="${left + i * slot + slot / 2}" y="${H - 8}" text-anchor="middle">${esc(lab)}</text>`;
      }
    });
    return s + `</svg>`;
  }

  const legend = (series) => `<div class="legend">${series.map((s) => `<span style="--c:var(${s.color})">${esc(s.name)}</span>`).join("")}</div>`;

  // --------------------------------------------------------------- render
  let loaded = false;
  async function load() {
    if (loaded) return;
    loaded = true;
    let d;
    try {
      const res = await fetch("model/dataset.json");
      if (!res.ok) throw new Error("HTTP " + res.status);
      d = await res.json();
    } catch (err) {
      $("dataset").innerHTML = `<div class="note err">Could not load the dataset numbers: ${esc(err.message)}</div>`;
      loaded = false;
      return;
    }
    data = d;
    render();
  }

  let data = null, lastW = 0;
  function render() {
    const d = data;
    W = Math.max(300, Math.floor($("dataset").clientWidth - 42));
    if (W === lastW) return;
    lastW = W;
    const train = { name: "Training (dated)", color: "--s1" };
    const undated = { name: "Undated (to estimate)", color: "--s2" };
    const both = [train, undated];
    const trainN = d.funnel[d.funnel.length - 1].n;
    let h = "";

    h += `<div class="tiles">
      <div class="tile"><div class="num">${fmt(d.n_pages)}</div><div class="lab">transcribed pages with text</div></div>
      <div class="tile"><div class="num">${(d.n_words / 1e6).toFixed(1)}M</div><div class="lab">words in Peirce's manuscripts</div></div>
      <div class="tile"><div class="num">${fmt(trainN)}</div><div class="lab">dated manuscripts to train on</div></div>
      <div class="tile"><div class="num">${fmt(d.undated)}</div><div class="lab">undated manuscripts to estimate</div></div>
    </div>`;

    // Funnel
    h += `<div class="block"><h2>From catalogue to training set</h2>
      <p class="lead">Each step removes records the models cannot use. The ${fmt(d.undated)} undated manuscripts
      are the ones the models are built to date; ${fmt(d.excluded_span)} dated manuscripts were set aside because their sources disagree by 4 years or more.</p>
      ${hbars(d.funnel.map((f) => ({ label: f.label, values: [f.n], note: f.note })), [{ name: "Manuscripts", color: "--s1" }], { labelW: 220, aria: "Filtering funnel" })}
      ${table(["Step", "Manuscripts"], d.funnel.map((f) => [f.label, f.n]))}</div>`;

    // Cleaning
    h += `<div class="block"><h2>How the text was cleaned</h2>
      <p class="lead">The transcriptions are automatic (Google Gemini), mostly not proofread, and marked up with tags. <code>clean_data.py</code> runs five steps:</p>
      <ol>
        <li><b>Remove deleted text.</b> Everything Peirce struck through (<code>[del]...[/del]</code>) is dropped, since it is not part of the final text.</li>
        <li><b>Remove tags.</b> Page numbers (<code>[pn]</code>) and figure descriptions (<code>[fig]</code>) are removed with their content; all other tags (underline, gaps, ...) are removed but their text is kept.</li>
        <li><b>Combine pages.</b> Every manuscript becomes one text. Houghton's colour scans (iiif) and the 1966 microfilm cover the same pages, so only one is used: the source with the most non-empty pages, iiif when equal.</li>
        <li><b>Collect dates.</b> Every date estimate per source (Irvine, Houghton catalogue, Robin catalogue) is reduced to a start year, end year and midpoint.</li>
        <li><b>Link text and dates.</b> One row per manuscript with its metadata, dates and text.</li>
      </ol>
      <p class="lead" style="margin-top:12px">Before modelling, two more things happen. Years written in the text (1800-1929) are replaced by a placeholder, so the model cannot copy a date the cataloguers also used.
      And drafts of the same work (same Robin number, same title nearby, or near-identical text) are kept together, so cross-validation never trains on one draft and tests on another.</p></div>`;

    // Years
    h += `<div class="block"><h2>When the training manuscripts were written</h2>
      <p class="lead">Target year (mean of the source midpoints) of the ${fmt(trainN)} training manuscripts. Median ${Math.round(d.median_year)}.
      Most are from 1890-1910; the early decades have few examples, which is why the models date early manuscripts least well.</p>
      ${vbars(d.years, [d.year_counts], [{ name: "Manuscripts", color: "--s1" }], { every: 10, fill: 0.86, aria: "Training manuscripts per year" })}
      ${table(["Year", "Manuscripts"], d.years.map((y, i) => [String(y), d.year_counts[i]]).filter((r) => r[1] > 0))}</div>`;

    // Lengths
    h += `<div class="block"><h2>Text length</h2>
      <p class="lead">Words per manuscript. The undated manuscripts are much shorter (median ${fmt(d.median_words_undated)} words vs ${fmt(d.median_words_train)}),
      and short texts give less reliable estimates.</p>
      ${legend(both)}
      ${vbars(d.length_labels, [d.length_train, d.length_undated], both, { aria: "Manuscripts by length", tipLabel: (l) => l + " words" })}
      ${table(["Words", train.name, undated.name], d.length_labels.map((l, i) => [l, d.length_train[i], d.length_undated[i]]))}</div>`;

    // Categories
    h += `<div class="block"><h2>Topics (Robin catalogue category)</h2>
      <p class="lead">The training set is dominated by Logic and Mathematics; the undated set has many Reviews and Linguistics manuscripts.
      This is one reason to compare topic-free style features with TF-IDF: a model that learns topic could learn "Reviews" instead of a period.</p>
      ${legend(both)}
      ${hbars(d.categories.map((c, i) => ({ label: c, values: [d.category_train[i], d.category_undated[i]] })), both, { aria: "Manuscripts per category" })}
      ${table(["Category", train.name, undated.name], d.categories.map((c, i) => [c, d.category_train[i], d.category_undated[i]]))}</div>`;

    // Sources
    const ds = d.date_sources;
    h += `<div class="block"><h2>Transcription and date sources</h2>
      <p class="lead">Most text comes from the microfilm, whose transcriptions contain more OCR errors than the colour scans.
      Dates come from up to three sources; where two sources date the same manuscript (${fmt(d.two_sources)} training manuscripts) they mostly agree exactly.</p>
      ${legend(both)}
      ${hbars([{ label: "Colour scans (iiif)", values: [d.source_train[0], d.source_undated[0]] },
               { label: "Microfilm", values: [d.source_train[1], d.source_undated[1]] }], both, { aria: "Transcription source" })}
      <div style="height:16px"></div>
      ${hbars([{ label: "Irvine", values: [ds.irvine] }, { label: "Houghton catalogue", values: [ds.houghton] }, { label: "Robin catalogue", values: [ds.robin] }],
              [{ name: "Training manuscripts dated by this source", color: "--s1" }], { aria: "Date sources" })}
      <div style="height:16px"></div>
      ${hbars(d.span_counts.map((n, k) => ({ label: k === 0 ? "Exact year" : `Range of ${k} year${k > 1 ? "s" : ""}`, values: [n] })),
              [{ name: "Training manuscripts", color: "--s1" }], { aria: "Width of the date range" })}
      <p class="lead" style="margin-top:8px">Last chart: latest end minus earliest start over all sources, for the training set (by construction under 4 years).</p>
      ${table(["", "Manuscripts"], [["iiif (training)", d.source_train[0]], ["microfilm (training)", d.source_train[1]],
        ["iiif (undated)", d.source_undated[0]], ["microfilm (undated)", d.source_undated[1]],
        ["dated by Irvine", ds.irvine], ["dated by Houghton", ds.houghton], ["dated by Robin", ds.robin],
        ...d.span_counts.map((n, k) => [`date range ${k} years`, n])])}</div>`;

    $("dataset").innerHTML = h;
    $("dataset").querySelectorAll("svg.viz").forEach(tooltip);
  }
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (data && !$("view-dataset").classList.contains("hidden")) render(); }, 150);
  });
})();
