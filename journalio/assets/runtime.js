/* Journalio runtime: renders a validated spec into an interactive lab. No network, no libraries. */
(function () {
  "use strict";
  var SPEC = JSON.parse(document.getElementById("spec-data").textContent);
  var BUILD = JSON.parse(document.getElementById("build-data").textContent);
  var C = JCore;
  var comp = C.compile(SPEC);
  var state = { inp: C.fixInputs(SPEC, {}), out: null, prev: null, lastControl: null, lastOld: null };
  var ctrlById = {};
  (SPEC.controls || []).forEach(function (c) { ctrlById[c.id] = c; });

  // ---------------- helpers ----------------
  function $(id) { return document.getElementById(id); }
  function el(tag, attrs, kids) {
    var e = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === "html") e.innerHTML = attrs[k];
      else if (k === "text") e.textContent = attrs[k];
      else if (k.slice(0, 2) === "on") e.addEventListener(k.slice(2), attrs[k]);
      else e.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach(function (k) { if (k !== null && k !== undefined) e.appendChild(typeof k === "string" ? document.createTextNode(k) : k); });
    return e;
  }
  var ALLOWED = /&lt;(\/?)(sub|sup|b|i|em|strong|code|br|u|small)\s*\/?&gt;/g;
  function rich(s) {
    if (s === undefined || s === null) return "";
    s = String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    return s.replace(ALLOWED, "<$1$2>").replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  }
  function tag(t) {
    t = (t || "PLAYGROUND").toUpperCase();
    var label = { PAPER: "PAPER", DERIVED: "DERIVED", PLAYGROUND: "PLAYGROUND", TOY: "PLAYGROUND" }[t] || t;
    return '<span class="tag tag-' + label.toLowerCase() + '" title="' + ({ PAPER: "Directly supported by the source excerpt", DERIVED: "Follows mathematically from the source", PLAYGROUND: "Simplified toy example chosen for teaching" }[label] || "") + '">' + label + "</span>";
  }
  function fmt(v, d) { return C.fmt(v, d); }
  function val(key) { return C.getPath(state.out || {}, key); }
  function labelsFor(spec, n) {
    var l = spec;
    if (typeof l === "string") l = val(l);
    if (!Array.isArray(l)) { l = []; for (var i = 0; i < n; i++) l.push(String(i + 1)); }
    return l.map(String);
  }
  var SVGNS = "http://www.w3.org/2000/svg";
  function svg(tagName, attrs, text) {
    var e = document.createElementNS(SVGNS, tagName);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function niceRange(lo, hi) {
    if (!isFinite(lo) || !isFinite(hi)) { lo = 0; hi = 1; }
    if (lo === hi) { hi = lo + (lo === 0 ? 1 : Math.abs(lo) * 0.5); lo = lo - (lo === 0 ? 0 : Math.abs(lo) * 0.5); }
    var span = hi - lo, step = Math.pow(10, Math.floor(Math.log10(span / 4)));
    var err = span / 4 / step;
    if (err >= 5) step *= 5; else if (err >= 2) step *= 2;
    return { lo: Math.floor(lo / step) * step, hi: Math.ceil(hi / step) * step, step: step };
  }
  var PAL = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)"];

  // ---------------- static sections ----------------
  function renderStatic() {
    var P = SPEC.paper || {};
    document.title = SPEC.title || "Interactive explanation";
    $("title").innerHTML = rich(SPEC.title);
    $("subtitle").innerHTML = rich(SPEC.subtitle || "");
    var cite = [P.authors, P.year ? "(" + P.year + ")" : "", P.title ? "<i>" + rich(P.title) + "</i>" : ""].filter(Boolean).join(" ");
    $("cite").innerHTML = "Source: " + cite + (P.section ? " — <b>" + rich(P.section) + "</b>" : "") +
      (P.url ? ' — <a href="' + encodeURI(P.url) + '" target="_blank" rel="noopener">' + rich(P.url) + "</a>" : "");

    var I = SPEC.intro || {};
    [["what", "What is this?"], ["why", "Why does it matter?"], ["change", "What can I change?"], ["watch", "What should I watch?"]].forEach(function (p) {
      $("intro").appendChild(el("div", { "class": "card q" }, [el("h3", { text: p[1] }), el("p", { html: rich(I[p[0]]) })]));
    });
    var F = SPEC.first_action;
    if (F) {
      var box = $("first");
      box.innerHTML = '<div class="tw"><div><b>TRY THIS FIRST:</b> ' + rich(F.try) + '</div><div><b>WATCH:</b> ' + rich(F.watch) + '</div><div><b>WHY:</b> ' + rich(F.why) + "</div></div>";
      if (F.preset && Object.keys(F.preset).length) box.appendChild(el("button", { "class": "btn", text: "Set it up for me", onclick: function () { applyPreset(F.preset, "first action"); } }));
    } else $("first").style.display = "none";

    // symbols
    var st = $("symbols");
    (SPEC.symbols || []).forEach(function (s) {
      st.appendChild(el("tr", null, [el("td", { "class": "sym", html: rich(s.sym) }), el("td", { html: rich(s.meaning) }), el("td", { html: tag(s.tag) })]));
    });
    // equations
    var eq = $("equations");
    (SPEC.equations || []).forEach(function (e) {
      eq.appendChild(el("div", { "class": "eq" }, [
        el("div", { "class": "eqx", html: rich(e.expr) }),
        el("div", { "class": "eqm", html: tag(e.tag) + " " + rich(e.ref || "") + (e.note ? ' — <span class="muted">' + rich(e.note) + "</span>" : "") })
      ]));
    });
    // scope
    var S = SPEC.scope || {};
    $("scope").innerHTML = (S["in"] ? "<p><b>In scope:</b> " + rich(S["in"]) + "</p>" : "") + (S.out ? "<p><b>Out of scope:</b> " + rich(S.out) + "</p>" : "");

    // explorations
    (SPEC.explorations || []).forEach(function (x, i) {
      var card = el("div", { "class": "card expl" }, [
        el("h3", { html: "Exploration " + (i + 1) + ": " + rich(x.title) }),
        el("p", { html: "<b>WHAT TO CHANGE:</b> " + rich(x.change) }),
        el("p", { html: "<b>WHAT TO OBSERVE:</b> " + rich(x.observe) }),
        el("details", null, [el("summary", { text: "WHY IT HAPPENS (predict first, then reveal)" }), el("p", { html: rich(x.why) })])
      ]);
      if (x.preset && Object.keys(x.preset).length) card.insertBefore(el("button", { "class": "btn", text: "Load this setup into the lab ↑", onclick: function () { applyPreset(x.preset, "exploration " + (i + 1)); } }), card.children[1]);
      $("explorations").appendChild(card);
    });
    // limitation
    var L = SPEC.limitation || {};
    var lk = (L.kind || "limitation").toLowerCase();
    var lbox = $("limitation");
    lbox.appendChild(el("h3", { html: (lk.indexOf("mis") >= 0 ? "Common misconception: " : "Assumption / limitation: ") + rich(L.title) }));
    lbox.appendChild(el("p", { html: "<b>" + (lk.indexOf("mis") >= 0 ? "MISCONCEPTION" : "ASSUMPTION") + ":</b> " + rich(L.claim) }));
    lbox.appendChild(el("p", { html: "<b>TRY THIS:</b> " + rich(L.try) }));
    if (L.preset && Object.keys(L.preset).length) lbox.appendChild(el("button", { "class": "btn warn", text: "Push the model there", onclick: function () { applyPreset(L.preset, "limitation lab"); } }));
    lbox.appendChild(el("p", { html: "<b>OBSERVE:</b> " + rich(L.observe) }));
    lbox.appendChild(el("details", null, [el("summary", { text: "Correct interpretation" }), el("p", { html: rich(L.explain) })]));

    // claims
    var cl = $("claims");
    (SPEC.claims || []).forEach(function (c) {
      cl.appendChild(el("li", { html: tag(c.tag) + " " + rich(c.text) + (c.ref ? ' <span class="ref">[' + rich(c.ref) + "]</span>" : "") }));
    });
    // build checks
    var bv = BUILD.validation || {};
    $("buildinfo").innerHTML = "<p>This page was generated by an agent and machine-checked before publishing: <b>" +
      (bv.states || 0) + "</b> input states (defaults, control extremes, equal/dominant cases, every preset) were executed; outputs were checked for NaN/∞, every control was verified to change a computed quantity, and the invariants below were tested in every state. Result: <b>" +
      (bv.ok ? "all passed" : "issues remained (" + (bv.errors || []).length + ")") + "</b>" + (BUILD.revisions ? ", after " + BUILD.revisions + " automatic revision(s)" : "") + ".</p>" +
      (bv.ok ? "" : "<ul class='errs'>" + (bv.errors || []).map(function (e) { return "<li>" + rich(e) + "</li>"; }).join("") + "</ul>");
  }

  // ---------------- mechanism map ----------------
  function renderMap() {
    var m = $("mechmap");
    var stages = SPEC.stages || [];
    stages.forEach(function (s, i) {
      var node = el("button", { "class": "stage", id: "stage-" + s.id, title: "Click to inspect this intermediate quantity", onclick: function () { inspect(s.id); } }, [
        el("div", { "class": "sl", html: rich(s.label) }),
        el("div", { "class": "sx", html: rich(s.expr || "") }),
        el("div", { "class": "sv", id: "sv-" + s.id })
      ]);
      m.appendChild(node);
      if (i < stages.length - 1) m.appendChild(el("div", { "class": "arrow", text: "→" }));
    });
  }
  function inspect(id) {
    var s = (SPEC.stages || []).filter(function (x) { return x.id === id; })[0];
    if (!s) return;
    document.querySelectorAll(".stage").forEach(function (n) { n.classList.toggle("sel", n.id === "stage-" + id); });
    var html = "<b>" + rich(s.label) + "</b>" + (s.expr ? " &nbsp;<code class='ex'>" + rich(s.expr) + "</code>" : "") + "<p>" + rich(s.desc || "") + "</p>";
    (s.keys || []).forEach(function (k) { html += "<div class='kv'><span class='k'>" + rich(k) + "</span> = " + valueHtml(val(k)) + "</div>"; });
    $("inspect").innerHTML = html;
    $("inspect").dataset.stage = id;
  }
  function miniViz(v) {
    if (typeof v === "number") return '<span class="mv">' + fmt(v, 3) + "</span>";
    if (typeof v === "boolean") return '<span class="mv">' + v + "</span>";
    if (!Array.isArray(v) || !v.length) return "";
    var w = 84, h = 24, out = '<svg class="spark" viewBox="0 0 ' + w + " " + h + '" width="' + w + '" height="' + h + '">';
    if (Array.isArray(v[0])) {
      var r = v.length, c = v[0].length, flat = [].concat.apply([], v).filter(isFinite);
      var mx = Math.max.apply(null, flat.map(Math.abs)) || 1, cw = Math.min(w / c, 14), ch = h / r;
      v.forEach(function (row, i) { row.forEach(function (x, j) { out += '<rect x="' + (j * cw) + '" y="' + (i * ch) + '" width="' + (cw - 1) + '" height="' + (ch - 1) + '" fill="' + (x < 0 ? "var(--s2)" : "var(--s1)") + '" fill-opacity="' + (0.12 + 0.88 * Math.abs(x) / mx).toFixed(2) + '"/>'; }); });
    } else {
      var nums = v.map(Number).filter(isFinite);
      if (!nums.length) return "";
      var m2 = Math.max.apply(null, nums.map(Math.abs)) || 1, n = Math.min(v.length, 40), bw = w / n;
      var hasNeg = nums.some(function (x) { return x < 0; }), base = hasNeg ? h / 2 : h;
      for (var i = 0; i < n; i++) { var x = Number(v[i]); if (!isFinite(x)) continue; var bh = Math.abs(x) / m2 * (hasNeg ? h / 2 : h); out += '<rect x="' + (i * bw + 0.5) + '" y="' + (x >= 0 ? base - bh : base) + '" width="' + Math.max(bw - 1.5, 1) + '" height="' + Math.max(bh, 0.6) + '" fill="var(--s1)"/>'; }
    }
    return out + "</svg>";
  }
  function renderStageValues() {
    (SPEC.stages || []).forEach(function (s) {
      var box = $("sv-" + s.id); if (!box) return;
      var keys = (s.keys || []).filter(function (k) { return val(k) !== undefined; }).slice(0, 2);
      box.innerHTML = keys.map(function (k) { return miniViz(val(k)); }).join(" ");
    });
  }
  function valueHtml(v) {
    if (Array.isArray(v)) {
      if (v.length && Array.isArray(v[0])) return "<table class='mini'>" + v.map(function (r) { return "<tr>" + r.map(function (x) { return "<td>" + fmt(x) + "</td>"; }).join("") + "</tr>"; }).join("") + "</table>";
      return "[" + v.map(function (x) { return fmt(x); }).join(", ") + "]";
    }
    return "<b>" + fmt(v, 4) + "</b>";
  }

  // ---------------- controls ----------------
  function renderControls() {
    var box = $("controls");
    box.innerHTML = "";
    (SPEC.controls || []).forEach(function (c) {
      var wrap = el("div", { "class": "ctrl", id: "ctrl-" + c.id });
      var head = el("label", { "class": "cl", html: rich(c.label || c.id) });
      wrap.appendChild(head);
      if (c.type === "slider") {
        var out = el("output", { "class": "cv", id: "cv-" + c.id });
        head.appendChild(out);
        head.appendChild(el("button", { "class": "anim", type: "button", title: "Animate: sweep this input from min to max and watch everything downstream", "aria-label": "Animate " + (c.label || c.id), text: anim.id === c.id ? "■" : "▶", onclick: function (ev) { ev.preventDefault(); toggleAnim(c); } }));
        var r = el("input", { type: "range", min: c.min, max: c.max, step: c.step || (c.max - c.min) / 100, value: state.inp[c.id], "aria-label": c.label || c.id });
        r.addEventListener("input", function () { setInput(c.id, Number(r.value)); });
        wrap.appendChild(r);
        wrap.appendChild(el("div", { "class": "range", html: "<span>" + fmt(c.min) + "</span><span>" + fmt(c.max) + "</span>" }));
      } else if (c.type === "toggle") {
        var cb = el("input", { type: "checkbox", "aria-label": c.label || c.id });
        cb.checked = !!state.inp[c.id];
        cb.addEventListener("change", function () { setInput(c.id, cb.checked); });
        head.insertBefore(cb, head.firstChild);
        head.classList.add("tog");
      } else if (c.type === "select") {
        var sel = el("select", { "aria-label": c.label || c.id });
        (c.options || []).forEach(function (o) {
          var v = (o && typeof o === "object") ? o.value : o, l = (o && typeof o === "object") ? (o.label || o.value) : o;
          var op = el("option", { value: String(v), text: String(l) });
          if (String(v) === String(state.inp[c.id])) op.selected = true;
          sel.appendChild(op);
        });
        sel.addEventListener("change", function () {
          var o = (c.options || []).map(function (o) { return (o && typeof o === "object") ? o.value : o; }).filter(function (v) { return String(v) === sel.value; })[0];
          setInput(c.id, o);
        });
        wrap.appendChild(sel);
      } else if (c.type === "vector") {
        var g = el("div", { "class": "vec" });
        var labs = labelsFor(c.labels, state.inp[c.id].length);
        state.inp[c.id].forEach(function (v, i) {
          var row = el("div", { "class": "vrow" });
          row.appendChild(el("span", { "class": "vl", html: rich(labs[i] !== undefined ? labs[i] : String(i + 1)) }));
          var rr = el("input", { type: "range", min: C.isNum(c.min) ? c.min : 0, max: C.isNum(c.max) ? c.max : 1, step: c.step || 0.01, value: v, "aria-label": (c.label || c.id) + " " + (i + 1) });
          var num = el("input", { type: "number", min: C.isNum(c.min) ? c.min : "", max: C.isNum(c.max) ? c.max : "", step: c.step || 0.01, value: v, "class": "num" });
          rr.addEventListener("input", function () { num.value = rr.value; setVec(c.id, i, Number(rr.value)); });
          num.addEventListener("change", function () { setVec(c.id, i, Number(num.value)); });
          row.appendChild(rr); row.appendChild(num);
          g.appendChild(row);
        });
        wrap.appendChild(g);
      } else if (c.type === "matrix") {
        var m = state.inp[c.id];
        var rl = labelsFor(c.row_labels, m.length), cl = labelsFor(c.col_labels, (m[0] || []).length);
        var t = el("table", { "class": "mat" });
        t.appendChild(el("tr", null, [el("th")].concat(cl.map(function (x) { return el("th", { html: rich(x) }); }))));
        m.forEach(function (row, i) {
          var tr = el("tr", null, [el("th", { html: rich(rl[i]) })]);
          row.forEach(function (v, j) {
            var inp = el("input", { type: "number", step: c.step || 0.1, value: v, min: C.isNum(c.min) ? c.min : "", max: C.isNum(c.max) ? c.max : "", "aria-label": (c.label || c.id) + "[" + (i + 1) + "," + (j + 1) + "]" });
            inp.addEventListener("input", function () { if (inp.value !== "" && isFinite(Number(inp.value))) setMat(c.id, i, j, Number(inp.value)); });
            tr.appendChild(el("td", null, [inp]));
          });
          t.appendChild(tr);
        });
        wrap.appendChild(t);
      }
      if (c.desc) wrap.appendChild(el("div", { "class": "cd", html: rich(c.desc) }));
      box.appendChild(wrap);
    });
    syncControlLabels();
  }
  var anim = { id: null, timer: null };
  function toggleAnim(c) {
    var was = anim.id;
    stopAnim();
    if (was === c.id) return;
    anim.id = c.id;
    var steps = isIntSlider(c) ? Math.round(c.max - c.min) : 60, k = 0, delay = isIntSlider(c) ? Math.max(350, 3000 / Math.max(steps, 1)) : 55;
    state.animating = true;
    renderControls();
    anim.timer = setInterval(function () {
      var x = c.min + (c.max - c.min) * k / steps;
      setInput(c.id, x);
      var r = document.querySelector("#ctrl-" + c.id + " input[type=range]"); if (r) r.value = x;
      if (++k > steps) { stopAnim(); }
    }, delay);
  }
  function stopAnim() {
    if (anim.timer) clearInterval(anim.timer);
    var had = anim.id; anim.id = null; anim.timer = null; state.animating = false;
    if (had) renderControls();
  }
  function syncControlLabels() {
    (SPEC.controls || []).forEach(function (c) {
      if (c.type === "slider") { var o = $("cv-" + c.id); if (o) o.textContent = fmt(state.inp[c.id], 4) + (c.unit ? " " + c.unit : ""); }
    });
  }
  function needsRebuild(id) {
    return (SPEC.controls || []).some(function (c) { return c.length_from === id || c.rows_from === id || c.cols_from === id; });
  }
  function setInput(id, v) {
    var old = state.inp[id];
    var next = C.clone(state.inp); next[id] = v;
    state.inp = C.fixInputs(SPEC, next);
    state.lastControl = id; state.lastOld = old;
    if (needsRebuild(id)) renderControls(); else syncControlLabels();
    update();
  }
  function setVec(id, i, v) { var a = C.clone(state.inp[id]); a[i] = v; setInput(id, a); }
  function setMat(id, i, j, v) { var a = C.clone(state.inp[id]); a[i][j] = v; setInput(id, a); }
  function applyPreset(p, why) {
    var next = Object.assign(C.fixInputs(SPEC, {}), C.clone(p || {}));
    state.inp = C.fixInputs(SPEC, next);
    state.lastControl = "__preset"; state.lastOld = why;
    renderControls(); update();
    $("lab").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---------------- views ----------------
  function renderViewShells() {
    var box = $("views");
    (SPEC.views || []).forEach(function (v, i) {
      v._id = v.id || ("v" + i);
      var card = el("figure", { "class": "card view", id: "view-" + v._id }, [
        el("figcaption", { "class": "vt", html: rich(v.title || "") + (v.stage ? ' <span class="vs">stage: ' + rich(stageLabel(v.stage)) + "</span>" : "") }),
        el("div", { "class": "vb", id: "vb-" + v._id }),
        v.caption ? el("div", { "class": "vc", html: "<b>WATCH:</b> " + rich(v.caption) }) : null
      ]);
      box.appendChild(card);
    });
  }
  function stageLabel(id) { var s = (SPEC.stages || []).filter(function (x) { return x.id === id; })[0]; return s ? s.label.replace(/<[^>]+>/g, "") : id; }
  function drawViews() {
    (SPEC.views || []).forEach(function (v) {
      var b = $("vb-" + v._id);
      try {
        b.innerHTML = "";
        ({ bars: drawBars, line: drawLine, heatmap: drawHeat, scatter: drawScatter, table: drawTable, canvas: drawCanvas, sweep: drawSweep, stacked: drawStacked }[v.type] || function () {})(b, v);
      } catch (e) { b.innerHTML = "<div class='err'>View error: " + rich(e.message) + "</div>"; }
    });
  }
  var W = 560;
  function axes(g, x0, y0, w, h, yr, ylabel, xlabel) {
    for (var t = yr.lo; t <= yr.hi + yr.step * 1e-6; t += yr.step) {
      var y = y0 + h - (t - yr.lo) / (yr.hi - yr.lo) * h;
      g.appendChild(svg("line", { x1: x0, x2: x0 + w, y1: y, y2: y, "class": "grid" }));
      g.appendChild(svg("text", { x: x0 - 6, y: y + 4, "text-anchor": "end", "class": "tick" }, fmt(t, 3)));
    }
    g.appendChild(svg("line", { x1: x0, x2: x0, y1: y0, y2: y0 + h, "class": "axis" }));
    if (ylabel) g.appendChild(svg("text", { x: 12, y: y0 + h / 2, transform: "rotate(-90 12 " + (y0 + h / 2) + ")", "text-anchor": "middle", "class": "alabel" }, ylabel));
    if (xlabel) g.appendChild(svg("text", { x: x0 + w / 2, y: y0 + h + 38, "text-anchor": "middle", "class": "alabel" }, xlabel));
  }
  function drawBars(b, v) {
    var series = v.series || [{ key: v.key, label: v.label || "" }];
    var data = series.map(function (s) { return (val(s.key) || []).map(Number); });
    var n = Math.max.apply(null, data.map(function (d) { return d.length; }).concat([0]));
    var labs = labelsFor(v.labels, n);
    var all = [].concat.apply([], data);
    var lo = C.isNum(v.ymin) ? v.ymin : Math.min(0, Math.min.apply(null, all));
    var hi = C.isNum(v.ymax) ? v.ymax : Math.max(0, Math.max.apply(null, all));
    var yr = niceRange(lo, hi); if (C.isNum(v.ymin)) yr.lo = v.ymin; if (C.isNum(v.ymax)) yr.hi = v.ymax;
    var H = 250, x0 = 52, y0 = 14, w = W - x0 - 10, h = H - 70;
    var s = svg("svg", { viewBox: "0 0 " + W + " " + H, "class": "chart", role: "img", "aria-label": v.title || "bar chart" });
    axes(s, x0, y0, w, h, yr, v.ylabel, v.xlabel);
    var hl = typeof v.highlight === "string" ? val(v.highlight) : v.highlight;
    var gw = w / Math.max(n, 1), bw = Math.min(60, gw * 0.8 / series.length);
    var yz = y0 + h - (Math.max(yr.lo, Math.min(yr.hi, 0)) - yr.lo) / (yr.hi - yr.lo) * h;
    for (var i = 0; i < n; i++) {
      var cx = x0 + gw * (i + 0.5);
      data.forEach(function (d, si) {
        var dv = d[i]; if (!C.isNum(dv)) return;
        var yv = y0 + h - (Math.max(yr.lo, Math.min(yr.hi, dv)) - yr.lo) / (yr.hi - yr.lo) * h;
        var x = cx - bw * series.length / 2 + si * bw;
        var cls = "bar" + ((hl === i) ? " hl" : "");
        s.appendChild(svg("rect", { x: x + 1, y: Math.min(yv, yz), width: Math.max(bw - 2, 1), height: Math.max(Math.abs(yz - yv), 0.5), "class": cls, fill: PAL[si % PAL.length] }));
        if (n * series.length <= 16) s.appendChild(svg("text", { x: x + bw / 2, y: Math.min(yv, yz) - 4, "text-anchor": "middle", "class": "bv" }, fmt(dv, v.digits !== undefined ? v.digits : 3)));
      });
      s.appendChild(svg("text", { x: cx, y: y0 + h + 16, "text-anchor": "middle", "class": "tick" }, labs[i] !== undefined ? labs[i] : ""));
    }
    if (C.isNum(v.ref_line)) { var yl = y0 + h - (v.ref_line - yr.lo) / (yr.hi - yr.lo) * h; s.appendChild(svg("line", { x1: x0, x2: x0 + w, y1: yl, y2: yl, "class": "refl" })); }
    b.appendChild(s);
    if (series.length > 1) b.appendChild(legend(series));
  }
  function legend(series) {
    return el("div", { "class": "legend", html: series.map(function (s, i) { return '<span><i style="background:' + PAL[i % PAL.length] + '"></i>' + rich(s.label || s.key) + "</span>"; }).join("") });
  }
  function arr(x) { return Array.isArray(x) ? x : (x === undefined || x === null ? [] : [x]); }
  function drawLine(b, v) {
    var xs = arr(val(v.x)).map(Number);
    var series = (v.series || []).map(function (sr) { return { label: sr.label, dashed: sr.dashed, y: arr(val(sr.key)).map(Number) }; });
    var pts = [];
    (v.points || []).forEach(function (p) {
      var px = val(p.x), py = val(p.y);
      if (Array.isArray(px) && Array.isArray(py)) {
        var labs = labelsFor(p.labels, px.length);
        px.forEach(function (x, i) { pts.push({ x: Number(x), y: Number(py[i]), label: (p.label ? p.label + " " : "") + labs[i] }); });
      } else pts.push({ x: Number(px), y: Number(py), label: p.label });
    });
    var vl = (v.vlines || []).map(function (l) { return { v: Number(val(l.key)), label: l.label }; });
    var hl = (v.hlines || []).map(function (l) { return { v: Number(val(l.key)), label: l.label }; });
    lineChart(b, v, xs, series, pts, vl, hl);
  }
  /* generic line chart: xs, series [{label,y,dashed}], points [{x,y,label}], vlines/hlines [{v,label}] */
  function lineChart(b, v, xs, series, pts, vlines, hlines, opts) {
    opts = opts || {};
    pts = pts.filter(function (p) { return isFinite(p.x) && isFinite(p.y); });
    var allY = [].concat.apply([], series.map(function (s) { return s.y; })).concat(pts.map(function (p) { return p.y; })).filter(isFinite);
    hlines.forEach(function (l) { if (isFinite(l.v)) allY.push(l.v); });
    if (!allY.length) allY = [0, 1];
    var xsF = xs.filter(isFinite).concat(pts.map(function (p) { return p.x; }));
    var xmin = C.isNum(v.xmin) ? v.xmin : Math.min.apply(null, xsF), xmax = C.isNum(v.xmax) ? v.xmax : Math.max.apply(null, xsF);
    if (!isFinite(xmin) || !isFinite(xmax)) { xmin = 0; xmax = 1; }
    if (!(xmax > xmin)) { xmax = xmin + 1; }
    var yr = niceRange(C.isNum(v.ymin) ? v.ymin : Math.min.apply(null, allY), C.isNum(v.ymax) ? v.ymax : Math.max.apply(null, allY));
    if (C.isNum(v.ymin)) yr.lo = v.ymin; if (C.isNum(v.ymax)) yr.hi = v.ymax;
    var H = 260, x0 = 56, y0 = 14, w = W - x0 - 14, h = H - 74;
    var X = function (x) { return x0 + (x - xmin) / (xmax - xmin) * w; };
    var Y = function (y) { return y0 + h - (Math.max(yr.lo, Math.min(yr.hi, y)) - yr.lo) / (yr.hi - yr.lo) * h; };
    var s = svg("svg", { viewBox: "0 0 " + W + " " + H, "class": "chart", role: "img", "aria-label": v.title || "line chart" });
    axes(s, x0, y0, w, h, yr, v.ylabel, v.xlabel);
    var xr = niceRange(xmin, xmax);
    for (var t = xr.lo; t <= xr.hi + 1e-9; t += xr.step) { if (t < xmin - 1e-9 || t > xmax + 1e-9) continue; s.appendChild(svg("text", { x: X(t), y: y0 + h + 16, "text-anchor": "middle", "class": "tick" }, fmt(t, 3))); }
    s.appendChild(svg("line", { x1: x0, x2: x0 + w, y1: y0 + h, y2: y0 + h, "class": "axis" }));
    hlines.forEach(function (l) { if (!isFinite(l.v)) return; s.appendChild(svg("line", { x1: x0, x2: x0 + w, y1: Y(l.v), y2: Y(l.v), "class": "refl" })); s.appendChild(svg("text", { x: x0 + w - 4, y: Y(l.v) - 4, "text-anchor": "end", "class": "rl" }, (l.label || "") + " " + fmt(l.v))); });
    vlines.forEach(function (l) { if (!isFinite(l.v)) return; s.appendChild(svg("line", { x1: X(l.v), x2: X(l.v), y1: y0, y2: y0 + h, "class": "refl" })); s.appendChild(svg("text", { x: X(l.v) + 4, y: y0 + 12, "class": "rl" }, (l.label || "") + " " + fmt(l.v))); });
    series.forEach(function (sr, si) {
      var d = "";
      for (var i = 0; i < Math.min(xs.length, sr.y.length); i++) { if (!isFinite(sr.y[i]) || !isFinite(xs[i])) { d += ""; continue; } d += (d ? "L" : "M") + X(xs[i]).toFixed(1) + "," + Y(sr.y[i]).toFixed(1); }
      s.appendChild(svg("path", { d: d, "class": "ln", stroke: PAL[si % PAL.length], "stroke-dasharray": sr.dashed ? "6 4" : "" }));
      if (opts.markers) for (var j = 0; j < Math.min(xs.length, sr.y.length); j++) if (isFinite(sr.y[j])) s.appendChild(svg("circle", { cx: X(xs[j]), cy: Y(sr.y[j]), r: 3, fill: PAL[si % PAL.length] }));
    });
    var many = pts.length > 3;
    pts.forEach(function (p, i) {
      if (opts.dropLines !== false) s.appendChild(svg("line", { x1: X(p.x), x2: X(p.x), y1: Y(p.y), y2: y0 + h, "class": "drop" }));
      s.appendChild(svg("circle", { cx: X(p.x), cy: Y(p.y), r: many ? 5 : 6, "class": "pt", fill: p.color || (many ? PAL[i % PAL.length] : "") }));
      var ly = many ? Y(p.y) - 8 - (i % 2) * 12 : (i % 2 ? Y(p.y) + 18 : Y(p.y) - 8);
      s.appendChild(svg("text", { x: X(p.x) + 8, y: ly, "class": "rl" }, (p.label ? p.label + " " : "") + (many ? "" : "(" + fmt(p.x) + ", " + fmt(p.y) + ")")));
    });
    b.appendChild(s);
    var legendItems = series.filter(function (sr) { return sr.label; });
    if (legendItems.length > 1 || (legendItems.length === 1 && !opts.noLegend)) b.appendChild(legend(series));
  }

  /* sweep: vary one slider across its range with everything else fixed, recompute with the real model */
  function drawSweep(b, v) {
    var c = ctrlById[v.control];
    if (!c || c.type !== "slider") throw new Error("sweep needs a slider control");
    var ys = (v.y || []).map(function (y) { return typeof y === "string" ? { key: y } : y; });
    var integer = isIntSlider(c);
    var n = integer ? Math.min(Math.round(c.max - c.min) + 1, 200) : (v.samples || 81);
    var xs = [], series = ys.map(function (y) { return { label: y.label || y.key, dashed: y.dashed, y: [] }; });
    for (var i = 0; i < n; i++) {
      var x = integer ? c.min + i : c.min + (c.max - c.min) * i / (n - 1);
      var inp = C.clone(state.inp); inp[c.id] = x;
      var o;
      try { o = C.run(comp, C.fixInputs(SPEC, inp)); } catch (e) { o = {}; }
      xs.push(x);
      ys.forEach(function (y, k) { var yy = Number(C.getPath(o, y.key)); series[k].y.push(isFinite(yy) ? yy : NaN); });
    }
    var cur = state.inp[c.id];
    var pts = ys.map(function (y, k) { return { x: cur, y: Number(val(y.key)), label: "now", color: PAL[k % PAL.length] }; });
    var vv = Object.assign({}, v, { xlabel: v.xlabel || stripTags(c.label || c.id), ylabel: v.ylabel || (ys.length === 1 ? stripTags(ys[0].label || ys[0].key) : "") });
    lineChart(b, vv, xs, series, pts, [], (v.hlines || []).map(function (l) { return { v: Number(val(l.key)), label: l.label }; }), { markers: integer && n <= 25, dropLines: true, noLegend: ys.length === 1 });
  }
  function stripTags(x) { return String(x || "").replace(/<[^>]+>/g, ""); }
  function isIntSlider(c) { return !!(c.integer || (C.isNum(c.step) && c.step >= 1 && Math.round(c.step) === c.step && Math.round(c.min) === c.min)); }

  /* stacked: parts of a total laid end to end (accumulation), optional maximum reference */
  function drawStacked(b, v) {
    var parts = arr(val(v.key)).map(Number);
    var labs = labelsFor(v.labels, parts.length);
    var total = parts.reduce(function (a, x) { return a + (isFinite(x) ? Math.max(0, x) : 0); }, 0);
    var ref = v.max_key ? Number(val(v.max_key)) : NaN;
    var scaleMax = Math.max(total, isFinite(ref) ? ref : 0) || 1;
    var H = 120, x0 = 14, w = W - 28, y0 = 30, bh = 40;
    var s = svg("svg", { viewBox: "0 0 " + W + " " + H, "class": "chart", role: "img", "aria-label": v.title || "stacked contributions" });
    var x = x0;
    parts.forEach(function (p, i) {
      if (!(p > 0)) return;
      var ww = p / scaleMax * w;
      s.appendChild(svg("rect", { x: x, y: y0, width: Math.max(ww - 1, 0.5), height: bh, fill: PAL[i % PAL.length], "class": "seg-r" }));
      if (ww > 34) s.appendChild(svg("text", { x: x + ww / 2, y: y0 + bh / 2 + 4, "text-anchor": "middle", "class": "inbar" }, labs[i]));
      if (ww > 34) s.appendChild(svg("text", { x: x + ww / 2, y: y0 + bh + 14, "text-anchor": "middle", "class": "tick" }, fmt(p, v.digits !== undefined ? v.digits : 3)));
      x += ww;
    });
    s.appendChild(svg("line", { x1: x0 + total / scaleMax * w, x2: x0 + total / scaleMax * w, y1: y0 - 10, y2: y0 + bh + 2, "class": "axis" }));
    s.appendChild(svg("text", { x: Math.min(x0 + total / scaleMax * w, W - 120), y: y0 - 14, "class": "rl" }, (v.total_label || "total") + " = " + fmt(total, 4) + (v.unit ? " " + v.unit : "")));
    if (isFinite(ref)) {
      var xr = x0 + ref / scaleMax * w;
      s.appendChild(svg("rect", { x: x0, y: y0, width: ref / scaleMax * w, height: bh, "class": "maxbox" }));
      s.appendChild(svg("text", { x: Math.max(xr - 4, 60), y: y0 + bh + 30, "text-anchor": "end", "class": "rl" }, (v.max_label || "maximum") + " = " + fmt(ref, 4)));
    }
    b.appendChild(s);
  }
  function heatColor(t, div) {
    if (div) { // diverging blue-white-red, t in [-1,1]
      var a = Math.min(1, Math.abs(t));
      return t >= 0 ? "rgba(214,72,60," + (0.08 + 0.8 * a) + ")" : "rgba(52,110,214," + (0.08 + 0.8 * a) + ")";
    }
    return "rgba(52,110,214," + (0.06 + 0.86 * Math.max(0, Math.min(1, t))) + ")";
  }
  function drawHeat(b, v) {
    var m = val(v.key) || [];
    var rl = labelsFor(v.row_labels, m.length), cl = labelsFor(v.col_labels, (m[0] || []).length);
    var flat = [].concat.apply([], m).filter(isFinite);
    var lo = C.isNum(v.vmin) ? v.vmin : Math.min.apply(null, flat), hi = C.isNum(v.vmax) ? v.vmax : Math.max.apply(null, flat);
    var amax = Math.max(Math.abs(lo), Math.abs(hi)) || 1;
    var div = v.diverging || lo < 0;
    var t = el("table", { "class": "heat" });
    t.appendChild(el("tr", null, [el("th", { html: rich(v.corner || "") })].concat(cl.map(function (x) { return el("th", { html: rich(x) }); }))));
    m.forEach(function (row, i) {
      var tr = el("tr", null, [el("th", { html: rich(rl[i]) })]);
      row.forEach(function (x) {
        var tt = div ? x / amax : (hi > lo ? (x - lo) / (hi - lo) : 0.5);
        var td = el("td", { text: fmt(x, v.digits !== undefined ? v.digits : 3) });
        td.style.background = heatColor(tt, div);
        if (Math.abs(tt) > 0.6) td.style.color = "#fff";
        tr.appendChild(td);
      });
      if (v.row_sums) tr.appendChild(el("td", { "class": "rs", text: "Σ=" + fmt(row.reduce(function (a, b) { return a + b; }, 0), 4) }));
      t.appendChild(tr);
    });
    b.appendChild(t);
  }
  function drawScatter(b, v) {
    var pts = (val(v.key) || []).filter(function (p) { return Array.isArray(p) && isFinite(p[0]) && isFinite(p[1]); });
    var segs = typeof v.segments === "string" ? (val(v.segments) || []) : [];
    var xsAll = pts.map(function (p) { return p[0]; }), ysAll = pts.map(function (p) { return p[1]; });
    segs.forEach(function (s) { xsAll.push(s[0], s[2]); ysAll.push(s[1], s[3]); });
    if (v.arrows) { xsAll.push(0); ysAll.push(0); }
    var xr = niceRange(C.isNum(v.xmin) ? v.xmin : Math.min.apply(null, xsAll), C.isNum(v.xmax) ? v.xmax : Math.max.apply(null, xsAll));
    var yr = niceRange(C.isNum(v.ymin) ? v.ymin : Math.min.apply(null, ysAll), C.isNum(v.ymax) ? v.ymax : Math.max.apply(null, ysAll));
    if (v.equal_axes) { var lo = Math.min(xr.lo, yr.lo), hi = Math.max(xr.hi, yr.hi); xr = niceRange(lo, hi); yr = xr; }
    var H = 300, x0 = 56, y0 = 14, w = W - x0 - 14, h = H - 74;
    var X = function (x) { return x0 + (x - xr.lo) / (xr.hi - xr.lo) * w; };
    var Y = function (y) { return y0 + h - (y - yr.lo) / (yr.hi - yr.lo) * h; };
    var s = svg("svg", { viewBox: "0 0 " + W + " " + H, "class": "chart", role: "img", "aria-label": v.title || "scatter" });
    s.appendChild(svg("defs", {})).innerHTML = '<marker id="ah-' + v._id + '" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="currentColor"/></marker>';
    axes(s, x0, y0, w, h, yr, v.ylabel, v.xlabel);
    for (var t = xr.lo; t <= xr.hi + 1e-9; t += xr.step) s.appendChild(svg("text", { x: X(t), y: y0 + h + 16, "text-anchor": "middle", "class": "tick" }, fmt(t, 3)));
    s.appendChild(svg("line", { x1: x0, x2: x0 + w, y1: Y(Math.max(yr.lo, Math.min(yr.hi, 0))), y2: Y(Math.max(yr.lo, Math.min(yr.hi, 0))), "class": "axis" }));
    segs.forEach(function (sg) { s.appendChild(svg("line", { x1: X(sg[0]), y1: Y(sg[1]), x2: X(sg[2]), y2: Y(sg[3]), "class": "seg" })); });
    var labs = labelsFor(v.labels, pts.length);
    pts.forEach(function (p, i) {
      var col = PAL[i % PAL.length];
      if (v.arrows) s.appendChild(svg("line", { x1: X(0), y1: Y(0), x2: X(p[0]), y2: Y(p[1]), stroke: col, "stroke-width": 2.5, style: "color:" + col, "marker-end": "url(#ah-" + v._id + ")" }));
      else s.appendChild(svg("circle", { cx: X(p[0]), cy: Y(p[1]), r: 5, fill: col }));
      s.appendChild(svg("text", { x: X(p[0]) + 7, y: Y(p[1]) - 7, "class": "rl" }, labs[i]));
    });
    b.appendChild(s);
  }
  function drawTable(b, v) {
    var cols = v.columns || [];
    var data = cols.map(function (c) { return val(c.key) || []; });
    var n = Math.max.apply(null, data.map(function (d) { return d.length; }).concat([0]));
    var t = el("table", { "class": "dt" });
    t.appendChild(el("tr", null, cols.map(function (c) { return el("th", { html: rich(c.label || c.key) }); })));
    for (var i = 0; i < n; i++) t.appendChild(el("tr", null, cols.map(function (c, j) { return el("td", { text: fmt(data[j][i], c.digits) }); })));
    if (v.total_row) t.appendChild(el("tr", { "class": "tot" }, cols.map(function (c, j) {
      if (j === 0) return el("td", { text: "Σ" });
      var col = data[j]; return el("td", { text: col.every(function (x) { return typeof x === "number"; }) ? fmt(col.reduce(function (a, b) { return a + b; }, 0), c.digits) : "" });
    })));
    b.appendChild(t);
  }
  var drawFns = comp.draws;
  function drawCanvas(b, v) {
    var H = v.height || 260;
    var cv = el("canvas", { width: W * 2, height: H * 2, "class": "chart", role: "img", "aria-label": v.title || "diagram" });
    b.appendChild(cv);
    var ctx = cv.getContext("2d");
    ctx.scale(2, 2);
    var cs = getComputedStyle(document.body);
    ctx.fillStyle = cs.getPropertyValue("--fg"); ctx.strokeStyle = cs.getPropertyValue("--fg");
    ctx.font = "12px system-ui, sans-serif";
    drawFns[v._id](ctx, state.out, C.clone(state.inp), W, H);
  }

  // ---------------- readouts, why-panel, checks ----------------
  function renderReadouts(changed) {
    var box = $("readouts");
    box.innerHTML = "";
    (SPEC.readouts || []).forEach(function (r) {
      var v = val(r.key);
      var ch = changed.indexOf(r.key.split(".")[0]) >= 0;
      box.appendChild(el("div", { "class": "ro" + (ch && !state.animating ? " flash" : "") }, [
        el("div", { "class": "rk", html: rich(r.label || r.key) }),
        el("div", { "class": "rv", html: Array.isArray(v) ? valueHtml(v) : fmt(v, r.digits !== undefined ? r.digits : 4) + (r.unit ? ' <span class="u">' + rich(r.unit) + "</span>" : "") })
      ]));
    });
  }
  function describeVal(v) { if (Array.isArray(v)) return Array.isArray(v[0]) ? "matrix" : "[" + v.map(function (x) { return fmt(x, 3); }).join(", ") + "]"; return fmt(v, 4); }
  function whyPanel(changed) {
    var box = $("why");
    var stages = (SPEC.stages || []);
    var hit = stages.filter(function (s) { return (s.keys || []).some(function (k) { return changed.indexOf(k.split(".")[0]) >= 0; }); });
    document.querySelectorAll(".stage").forEach(function (n) { n.classList.remove("hot"); void n.offsetWidth; });
    if (!state.animating) hit.forEach(function (s) { var n = $("stage-" + s.id); if (n) n.classList.add("hot"); });
    (SPEC.views || []).forEach(function (v) {
      var keys = [v.key, v.x, v.max_key].concat((v.series || []).map(function (s) { return s.key; })).concat((v.points || []).map(function (p) { return p.y; })).concat((v.columns || []).map(function (c) { return c.key; })).filter(Boolean);
      var on = keys.some(function (k) { return changed.indexOf(String(k).split(".")[0]) >= 0; }) || ((v.type === "canvas" || v.type === "sweep") && changed.length);
      var n = $("view-" + v._id); if (n) { n.classList.remove("hot"); void n.offsetWidth; if (on && !state.animating) n.classList.add("hot"); }
    });
    if (!state.lastControl) {
      box.innerHTML = "<b>Why did this change?</b><p class='muted'>Move any control. This panel will trace the causal chain: control → changed intermediate quantities → visual.</p>";
      return;
    }
    var html = "<b>Why did this change?</b>";
    if (state.lastControl === "__preset") html += "<p>Loaded the setup for <b>" + rich(state.lastOld) + "</b>.</p>";
    else {
      var c = ctrlById[state.lastControl] || {};
      html += "<p>You changed <b>" + rich(c.label || c.id) + "</b>" + (c.type === "slider" || c.type === "toggle" || c.type === "select" ? " from <code>" + rich(describeVal(state.lastOld)) + "</code> to <code>" + rich(describeVal(state.inp[c.id])) + "</code>" : "") + ".</p>";
      if (c.effect) html += "<p>" + rich(c.effect) + "</p>";
    }
    if (hit.length) html += "<div class='chain'>" + hit.map(function (s) { return "<span>" + rich(s.label) + "</span>"; }).join(" → ") + "</div>";
    else html += "<p class='muted'>No intermediate quantity changed (this input is outside the active path for the current settings).</p>";
    var deltas = (SPEC.readouts || []).filter(function (r) { return changed.indexOf(r.key.split(".")[0]) >= 0 && !Array.isArray(val(r.key)); }).map(function (r) {
      return "<li>" + rich(r.label || r.key) + ": " + fmt(C.getPath(state.prev || {}, r.key), 4) + " → <b>" + fmt(val(r.key), 4) + "</b></li>";
    });
    if (deltas.length) html += "<ul class='deltas'>" + deltas.join("") + "</ul>";
    box.innerHTML = html;
  }
  function renderChecks() {
    var res = C.evalChecks(comp, state.out, state.inp);
    $("livechecks").innerHTML = res.map(function (r, i) {
      var sp = (SPEC.checks || [])[i] || {};
      return "<li class='" + (r.ok ? "ok" : "bad") + "'>" + (r.ok ? "✓" : "✗") + " " + rich(r.name) + (sp.why ? " <span class='muted'>— " + rich(sp.why) + "</span>" : "") + "</li>";
    }).join("");
    var nOk = res.filter(function (r) { return r.ok; }).length;
    $("checkbadge").textContent = nOk + "/" + res.length + " invariants hold";
    $("checkbadge").className = "badge " + (nOk === res.length ? "ok" : "bad");
  }

  function update() {
    var err = $("runerr");
    try {
      var out = C.run(comp, state.inp);
      state.prev = state.out; state.out = out; err.style.display = "none";
    } catch (e) { err.style.display = "block"; err.textContent = "Calculation error: " + e.message; return; }
    var changed = state.prev ? C.changedKeys(state.prev, state.out) : [];
    renderReadouts(changed);
    renderStageValues();
    drawViews();
    whyPanel(changed);
    renderChecks();
    if ($("inspect").dataset.stage) inspect($("inspect").dataset.stage);
  }

  function init() {
    renderStatic();
    renderMap();
    renderControls();
    renderViewShells();
    $("reset").addEventListener("click", function () { state.inp = C.fixInputs(SPEC, {}); state.lastControl = "__preset"; state.lastOld = "defaults (reset)"; renderControls(); update(); });
    if (comp.errors.length) { $("runerr").style.display = "block"; $("runerr").textContent = comp.errors.join("; "); }
    update();
    if ((SPEC.stages || [])[0]) inspect(SPEC.stages[0].id);
    window.__journalio = { spec: SPEC, state: state, setInput: setInput, applyPreset: applyPreset };
  }
  init();
})();
