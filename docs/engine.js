/* Peirce manuscript dating: the three trained models, in JavaScript.
 *
 * A port of the Python pipeline (clean_data.py cleaning, features.py
 * preprocessing and style features, sklearn TF-IDF, ridge, SVD and
 * HistGradientBoosting prediction). The model files in model/ are written by
 * code/dating/export_web.py. Works in the browser (window.PeirceEngine) and in
 * Node (require) so it can be checked against the Python predictions.
 */
(function (root) {
  "use strict";

  // ---------------------------------------------------------------- cleaning
  // Same steps as clean_data.py: remove deleted text, then tags.
  function removeDeleted(text) {
    const DEL = /\[del\][\s\S]*?\[\/del\]|<del>[\s\S]*?<\/del>/gi;
    for (;;) {
      const next = text.replace(DEL, "");
      if (next === text) break;
      text = next;
    }
    text = text.replace(/[ \t]{2,}/g, " ");
    return text.replace(/ +([.,;:!?])/g, "$1");
  }

  function removeTags(text) {
    text = text.replace(/[\[<](pn|fig)[\]>][\s\S]*?[\[<]\/\1[\]>]/gi, " ");
    text = text.replace(/^```[a-z]*\s*$/gm, "");
    text = text.replace(/\[\/?[A-Za-z]+\]|<\/?[A-Za-z]+>/g, "");
    text = text.replace(/[ \t]{2,}/g, " ");
    text = text.replace(/ +([.,;:!?])/g, "$1");
    text = text.replace(/[ \t]+\n/g, "\n");
    text = text.replace(/\n{3,}/g, "\n\n");
    return text.trim() ? text.trim() + "\n" : "";
  }

  const cleanPage = (t) => removeTags(removeDeleted(t)).trim();
  const collapse = (t) => t.split(/\s+/).filter(Boolean).join(" ");

  // seq2 before seq10, R-1_0009 before R-1_0010; hou..._seq1 pages last.
  function pageKey(name) {
    return { special: name.startsWith("hou") ? 1 : 0,
             nums: (name.match(/\d+/g) || []).map(Number), name };
  }
  function comparePages(a, b) {
    const x = pageKey(a), y = pageKey(b);
    if (x.special !== y.special) return x.special - y.special;
    for (let i = 0; i < Math.min(x.nums.length, y.nums.length); i++) {
      if (x.nums[i] !== y.nums[i]) return x.nums[i] - y.nums[i];
    }
    if (x.nums.length !== y.nums.length) return x.nums.length - y.nums.length;
    return x.name < y.name ? -1 : x.name > y.name ? 1 : 0;
  }

  /* pages: [{path: "MS-x/iiif/seq1.txt", text}] -> {text, source, nPages}.
   * As clean_data.py: iiif and microfilm cover the same pages, so only the
   * source with the most non-empty pages is used (iiif when equal). */
  function textFromPages(pages) {
    const groups = { iiif: [], microfilm: [], other: [] };
    for (const p of pages) {
      const parts = p.path.replace(/\\/g, "/").split("/");
      const dirs = parts.slice(0, -1);
      const source = dirs.includes("iiif") ? "iiif" : dirs.includes("microfilm") ? "microfilm" : "other";
      groups[source].push({ name: parts[parts.length - 1], text: p.text });
    }
    const joined = (items) => items.sort((a, b) => comparePages(a.name, b.name))
      .map((it) => cleanPage(it.text)).filter(Boolean);
    const iiif = joined(groups.iiif), microfilm = joined(groups.microfilm);
    let source, used;
    if (iiif.length || microfilm.length) {
      [source, used] = iiif.length >= microfilm.length && iiif.length ? ["iiif", iiif] : ["microfilm", microfilm];
    } else {
      [source, used] = ["uploaded files", joined(groups.other)];
    }
    return { text: collapse(used.join(" ")), source, nPages: used.length };
  }

  // ----------------------------------------------------------- preprocess
  // features.preprocess: first MAX_WORDS words, years 1800-1929 -> "yearnum".
  function preprocess(text, maxWords) {
    const words = text.split(/\s+/).filter(Boolean);
    if (words.length > maxWords) text = words.slice(0, maxWords).join(" ");
    return text.replace(/(?<![\p{L}\p{N}_])(?:1[89][0-9]{2}|19[0-2][0-9])(?![\p{L}\p{N}_])/gu, " yearnum ");
  }

  // ------------------------------------------------------- style features
  const DIGIT = /[\p{Nd}²³¹⁰⁴-⁹₀-₉①-⑨]/u;

  function styleVector(text, meta) {
    const words = text.match(/[A-Za-z]+(?:'[A-Za-z]+)?/g) || [];
    const lower = words.map((w) => w.toLowerCase());
    const nWords = Math.max(words.length, 1);
    const chars = Array.from(text);
    const nChars = Math.max(chars.length, 1);
    const counts = new Map();
    for (const w of lower) counts.set(w, (counts.get(w) || 0) + 1);

    const f = {};
    let fwTotal = 0;
    for (const w of meta.function_words) {
      const c = counts.get(w) || 0;
      f["fw_" + w] = c / nWords;
      fwTotal += c;
    }
    for (const [name, ch] of Object.entries(meta.punctuation)) {
      let c = 0;
      for (const x of chars) if (x === ch) c++;
      f["punct_" + name] = c / nChars * 1000;
    }
    const lengths = words.length ? words.map((w) => w.length) : [0];
    const sentences = (text.match(/[.!?]+/g) || []).length;
    const first = lower.slice(0, 1000);
    let digits = 0;
    for (const x of chars) if (DIGIT.test(x)) digits++;
    f.mean_word_len = lengths.reduce((a, b) => a + b, 0) / lengths.length;
    f.long_word_share = lengths.filter((l) => l >= 8).length / lengths.length;
    f.mean_sentence_len = nWords / Math.max(sentences, 1);
    f.type_token_1000 = new Set(first).size / Math.max(first.length, 1);
    f.capital_share = words.filter((w) => w[0] >= "A" && w[0] <= "Z").length / nWords;
    f.digit_rate = digits / nChars * 1000;
    f.function_word_share = fwTotal / nWords;
    f.log_n_words = Math.log1p(words.length);
    return meta.style_names.map((n) => f[n]);
  }

  // --------------------------------------------------------------- TF-IDF
  // sklearn TfidfVectorizer(lowercase, token_pattern \b\w\w+\b, ngram (1,2),
  // sublinear_tf, l2 norm). Returns sparse {index: weight}.
  function tfidfVector(text, model) {
    const tokens = text.toLowerCase().match(/[\p{L}\p{N}_]{2,}/gu) || [];
    const tf = new Map();
    const add = (term) => {
      const j = model.index.get(term);
      if (j !== undefined) tf.set(j, (tf.get(j) || 0) + 1);
    };
    for (let i = 0; i < tokens.length; i++) {
      add(tokens[i]);
      if (i + 1 < tokens.length) add(tokens[i] + " " + tokens[i + 1]);
    }
    let norm = 0;
    const vec = new Map();
    for (const [j, c] of tf) {
      const w = (1 + Math.log(c)) * model.idf[j];
      vec.set(j, w);
      norm += w * w;
    }
    norm = Math.sqrt(norm) || 1;
    for (const [j, w] of vec) vec.set(j, w / norm);
    return vec;
  }

  // ------------------------------------------------------ float16 decode
  function halfToFloat(h) {
    const s = h & 0x8000 ? -1 : 1, e = (h >> 10) & 0x1f, m = h & 0x3ff;
    if (e === 0) return s * Math.pow(2, -14) * (m / 1024);
    if (e === 31) return m ? NaN : s * Infinity;
    return s * Math.pow(2, e - 15) * (1 + m / 1024);
  }

  // ---------------------------------------------------- gradient boosting
  function gbmPredict(gbm, x) {
    let raw = gbm.baseline;
    for (const t of gbm.trees) {
      let n = 0;
      while (!t.leaf[n]) n = x[t.f[n]] <= t.t[n] ? t.l[n] : t.r[n];
      raw += t.v[n];
    }
    return raw;
  }

  // ---------------------------------------------------------------- model
  const MODELS = {
    tfidf_ridge: "Word TF-IDF + ridge regression (content)",
    style_gbm: "Function words, punctuation, sentence length + gradient boosting (style)",
    hybrid_gbm: "Style features + 100 TF-IDF topics + gradient boosting (both)",
  };

  /* load(name, kind) must return parsed JSON (kind "json") or an ArrayBuffer
   * (kind "bin"). Returns a model object for predict(). */
  async function init(load) {
    const [meta, vocab, idf, coef, svd, style, hybrid] = await Promise.all([
      load("meta.json", "json"), load("vocab.json", "json"), load("idf.f32", "bin"),
      load("ridge_coef.f32", "bin"), load("svd.f16", "bin"),
      load("style_gbm.json", "json"), load("hybrid_gbm.json", "json"),
    ]);
    const index = new Map(vocab.map((t, i) => [t, i]));
    return { meta, index, idf: new Float32Array(idf), coef: new Float32Array(coef),
             svd: new Uint16Array(svd), style, hybrid };
  }

  function clip(v) { return Math.min(Math.max(v, 1850), 1914); }

  /* text: one cleaned manuscript text (whitespace collapsed). */
  function predict(model, rawText) {
    const meta = model.meta;
    const text = preprocess(rawText, meta.max_words);
    const vec = tfidfVector(text, model);
    const styleX = styleVector(text, meta);

    let ridge = meta.ridge_intercept;
    for (const [j, w] of vec) ridge += model.coef[j] * w;

    const K = meta.n_topics, V = meta.n_vocab, topics = new Array(K).fill(0);
    for (const [j, w] of vec) {
      for (let k = 0; k < K; k++) topics[k] += w * halfToFloat(model.svd[k * V + j]);
    }
    const preds = {
      tfidf_ridge: ridge,
      style_gbm: gbmPredict(model.style, styleX),
      hybrid_gbm: gbmPredict(model.hybrid, styleX.concat(topics)),
    };
    const out = {};
    for (const [name, p] of Object.entries(preds)) {
      const hw = meta.half_widths[name];
      out[name] = { pred: clip(p), lo80: clip(p - hw["80"]), hi80: clip(p + hw["80"]),
                    lo95: clip(p - hw["95"]), hi95: clip(p + hw["95"]),
                    description: MODELS[name], cv: meta.cv[name] || {} };
    }
    return out;
  }

  const api = { init, predict, textFromPages, cleanPage, collapse, preprocess,
                styleVector, tfidfVector, MODELS };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.PeirceEngine = api;
})(typeof self !== "undefined" ? self : this);
