/* Build-time validator. Runs inside an embedded V8 (mini-racer) or node.
   Uses the same JCore functions as the generated page. */
function jValidate(spec) {
  "use strict";
  var errors = [], warnings = [], log = [];
  var ctrls = spec.controls || [];
  var ids = {};
  ctrls.forEach(function (c) { ids[c.id] = c; });

  // ---------- structural checks ----------
  var need = ["title", "paper", "intro", "stages", "controls", "compute", "views", "explorations", "limitation", "claims", "checks"];
  need.forEach(function (k) { if (spec[k] === undefined || spec[k] === null || spec[k] === "") errors.push("missing field '" + k + "'"); });
  var meaningful = ctrls.filter(function (c) { return ["slider", "toggle", "select", "vector", "matrix"].indexOf(c.type) >= 0; });
  if (meaningful.length < 2) errors.push("need at least 2 controls of type slider/toggle/select/vector/matrix (have " + meaningful.length + ")");
  ctrls.forEach(function (c) {
    if (!c.id) errors.push("control without id");
    if (["slider", "toggle", "select", "vector", "matrix"].indexOf(c.type) < 0) errors.push("control " + c.id + ": unknown type '" + c.type + "'");
    if (c.type === "slider" && !(JCore.isNum(c.min) && JCore.isNum(c.max) && c.max > c.min)) errors.push("slider " + c.id + ": needs numeric min < max");
    if (c.type === "select" && !(c.options && c.options.length >= 2)) errors.push("select " + c.id + ": needs >=2 options");
    if (c.length_from && !ids[c.length_from]) errors.push("control " + c.id + ": length_from '" + c.length_from + "' is not a control id");
  });
  if (!Array.isArray(spec.explorations) || spec.explorations.length !== 2) errors.push("need exactly 2 explorations");
  var stageIds = {};
  (spec.stages || []).forEach(function (s) { stageIds[s.id] = true; });
  if ((spec.stages || []).length < 3) warnings.push("mechanism has fewer than 3 stages");
  var tags = { PAPER: 1, DERIVED: 1, PLAYGROUND: 1 };
  (spec.claims || []).forEach(function (c, i) { if (!tags[c.tag]) errors.push("claim " + (i + 1) + ": tag must be PAPER|DERIVED|PLAYGROUND"); });
  var hasPaperClaim = (spec.claims || []).some(function (c) { return c.tag === "PAPER"; });
  var hasToyClaim = (spec.claims || []).some(function (c) { return c.tag === "PLAYGROUND"; });
  if (!hasPaperClaim) errors.push("claims must include at least one PAPER claim");
  if (!hasToyClaim) warnings.push("claims should include a PLAYGROUND statement about simplifications");
  var vtypes = { bars: 1, line: 1, heatmap: 1, scatter: 1, table: 1, canvas: 1, sweep: 1, stacked: 1 };
  (spec.views || []).forEach(function (v) {
    if (!vtypes[v.type]) errors.push("view " + (v.id || v.title) + ": unknown type '" + v.type + "'");
    if (v.type === "sweep") { var sc = ids[v.control]; if (!sc || sc.type !== "slider") errors.push("view " + (v.id || v.title) + " (sweep): 'control' must be the id of a slider control"); }
  });
  if (!(spec.checks || []).length) errors.push("need at least 2 checks (invariants)");

  function presetErr(p, where) {
    if (!p) return;
    Object.keys(p).forEach(function (k) { if (!ids[k]) errors.push(where + " preset uses unknown control '" + k + "'"); });
  }
  (spec.explorations || []).forEach(function (e, i) { presetErr(e.preset, "exploration " + (i + 1)); });
  if (spec.limitation) presetErr(spec.limitation.preset, "limitation");
  if (spec.first_action) presetErr(spec.first_action.preset, "first_action");

  var comp = JCore.compile(spec);
  comp.errors.forEach(function (e) { errors.push(e); });
  if (!comp.compute) return { ok: false, errors: errors, warnings: warnings, log: log, states: 0 };

  // ---------- generate test states ----------
  // bases: defaults, every preset, and an "uneven" variant of each vector/matrix; every control is varied on every base
  var base = JCore.fixInputs(spec, {});
  var bases = [{ name: "defaults", inp: base }];
  function mk(b, patch) { return JCore.fixInputs(spec, Object.assign(JCore.clone(b), patch)); }
  (spec.explorations || []).forEach(function (e, i) { bases.push({ name: "exploration " + (i + 1), inp: mk(base, e.preset || {}) }); });
  if (spec.limitation) bases.push({ name: "limitation", inp: mk(base, spec.limitation.preset || {}) });
  if (spec.first_action) bases.push({ name: "first_action", inp: mk(base, spec.first_action.preset || {}) });
  ctrls.forEach(function (c) {
    var p = {};
    if (c.type === "vector") {
      var lo = JCore.isNum(c.min) ? c.min : 0, hi = JCore.isNum(c.max) ? c.max : 1, n = base[c.id].length;
      p[c.id] = base[c.id].map(function (_, i) { return lo + (hi - lo) * (i + 1) / n; });
      bases.push({ name: c.id + " uneven", inp: mk(base, p) });
    } else if (c.type === "matrix") {
      var hi2 = JCore.isNum(c.max) ? c.max : 2, lo2 = JCore.isNum(c.min) ? c.min : -2;
      p[c.id] = base[c.id].map(function (r, i) { return r.map(function (_, j) { return lo2 + (hi2 - lo2) * (((i * 3 + j * 7) % 5) / 4); }); });
      bases.push({ name: c.id + " uneven", inp: mk(base, p) });
    }
  });
  function variants(c, b) {
    var out = [], p;
    if (c.type === "slider") {
      [c.min, c.max, (c.min + c.max) / 2].forEach(function (v, k) { p = {}; p[c.id] = v; out.push({ tag: c.id + "=" + ["min", "max", "mid"][k] + "(" + JCore.fmt(v) + ")", patch: p }); });
    } else if (c.type === "toggle") {
      p = {}; p[c.id] = !b[c.id]; out.push({ tag: c.id + "=" + (!b[c.id]), patch: p });
    } else if (c.type === "select") {
      (c.options || []).forEach(function (o) { var val = (o && typeof o === "object") ? o.value : o; p = {}; p[c.id] = val; out.push({ tag: c.id + "=" + val, patch: p }); });
    } else if (c.type === "vector") {
      var v = b[c.id], lo = JCore.isNum(c.min) ? c.min : 0, hi = JCore.isNum(c.max) ? c.max : 1, n = v.length;
      p = {}; p[c.id] = v.map(function () { return (lo + hi) / 2 || hi; }); out.push({ tag: c.id + " all equal", patch: p });
      p = {}; p[c.id] = v.map(function (_, i) { return i === 0 ? hi : lo; }); out.push({ tag: c.id + " one dominant/others min", patch: p });
      p = {}; p[c.id] = v.map(function (_, i) { return lo + (hi - lo) * (n - i) / n; }); out.push({ tag: c.id + " ramp", patch: p });
      p = {}; p[c.id] = v.map(function () { return lo; }); out.push({ tag: c.id + " all min", patch: p });
    } else if (c.type === "matrix") {
      var m = b[c.id], hi3 = JCore.isNum(c.max) ? c.max : 2, lo3 = JCore.isNum(c.min) ? c.min : -2;
      p = {}; p[c.id] = m.map(function (r) { return r.map(function () { return Math.max(lo3, Math.min(hi3, 1)); }); }); out.push({ tag: c.id + " all ones", patch: p });
      p = {}; p[c.id] = m.map(function (r, i) { return r.map(function (_, j) { return i === j ? hi3 : Math.max(lo3, 0); }); }); out.push({ tag: c.id + " diagonal max", patch: p });
      p = {}; p[c.id] = m.map(function (r, i) { return r.map(function (_, j) { return ((i + 2 * j) % 3 - 1) * (hi3 - lo3) / 2; }); }); out.push({ tag: c.id + " mixed", patch: p });
    }
    return out;
  }
  var states = [], seen = {};
  function push(name, inp, vary, baseIdx) {
    var key = JSON.stringify(inp);
    if (seen[key] !== undefined) { states.push({ name: name, inp: inp, vary: vary, base: baseIdx, dup: seen[key] }); return; }
    seen[key] = states.length;
    states.push({ name: name, inp: inp, vary: vary, base: baseIdx });
  }
  bases.forEach(function (b) { push(b.name, b.inp, null, null); });
  var nb = states.length;
  bases.forEach(function (b, bi) {
    ctrls.forEach(function (c) {
      variants(c, b.inp).forEach(function (v) { push(b.name + " + " + v.tag, mk(b.inp, v.patch), c.id, bi); });
    });
  });

  // ---------- run ----------
  var refs = JCore.referencedKeys(spec);
  var outs = [];
  var failedChecks = {};
  var stub = makeStubCtx();
  states.forEach(function (s, idx) {
    var out;
    if (s.dup !== undefined) { outs.push(outs[s.dup]); return; }
    try { out = JCore.run(comp, s.inp); }
    catch (e) { errors.push("compute threw at state [" + s.name + "] inputs=" + JSON.stringify(s.inp) + ": " + e.message); outs.push(null); return; }
    outs.push(out);
    var bad = JCore.badNumbers(out);
    if (bad.length) errors.push("non-finite output at state [" + s.name + "]: " + bad.slice(0, 4).join(", "));
    if (idx === 0) {
      refs.forEach(function (r) { if (JCore.getPath(out, r.key) === undefined) errors.push(r.where + " references key '" + r.key + "' which compute() does not return (returned keys: " + Object.keys(out).join(",") + ")"); });
      checkViewShapes(spec, out, errors);
    }
    JCore.evalChecks(comp, out, s.inp).forEach(function (r) {
      if (!r.ok && !failedChecks[r.name]) {
        failedChecks[r.name] = true;
        errors.push("check '" + r.name + "' failed at state [" + s.name + "]" + (r.err ? " (error: " + r.err + ")" : "") + "; inputs=" + JSON.stringify(s.inp).slice(0, 300));
      }
    });
    // canvas draws
    (spec.views || []).forEach(function (v, i) {
      if (v.type !== "canvas") return;
      var fn = comp.draws[v.id || ("v" + i)];
      if (!fn) return;
      try { fn(stub, out, s.inp, 600, v.height || 260); }
      catch (e) { if (!failedChecks["draw" + i]) { failedChecks["draw" + i] = true; errors.push("view " + (v.id || i) + " draw() threw at state [" + s.name + "]: " + e.message); } }
    });
  });

  // ---------- control effect test ----------
  var effect = {};
  ctrls.forEach(function (c) {
    var any = false;
    states.forEach(function (s, i) { if (s.vary === c.id && outs[i] && outs[s.base] && JCore.changedKeys(outs[s.base], outs[i]).length) any = true; });
    effect[c.id] = any;
    if (!any) errors.push("control '" + c.id + "' has no effect on any computed output in any tested state (decorative control): make compute() use inp." + c.id);
  });

  // ---------- metamorphic: determinism ----------
  try {
    var again = JCore.run(comp, base);
    if (outs[0] && !JCore.deepEqualNum(outs[0], again)) errors.push("compute() is not deterministic (do not use Math.random)");
  } catch (e) {}

  // ---------- sweep analysis: which scalar outputs does each slider move? (used for auto visual enrichment) ----------
  var scalarKeys = outs[0] ? Object.keys(outs[0]).filter(function (k) { return typeof outs[0][k] === "number" && isFinite(outs[0][k]); }) : [];
  var sweepEffects = {};
  ctrls.forEach(function (c) {
    if (c.type !== "slider" || !outs[0]) return;
    var vals = {};
    for (var i = 0; i <= 8; i++) {
      var inp = mk(base, (function () { var p = {}; p[c.id] = c.min + (c.max - c.min) * i / 8; return p; })());
      try { var o = JCore.run(comp, inp); scalarKeys.forEach(function (k) { (vals[k] = vals[k] || []).push(o[k]); }); } catch (e) { return; }
    }
    sweepEffects[c.id] = scalarKeys.filter(function (k) {
      var a = vals[k] || []; if (a.length < 9 || !a.every(function (x) { return typeof x === "number" && isFinite(x); })) return false;
      return Math.max.apply(null, a) - Math.min.apply(null, a) > 1e-9 * Math.max(1, Math.abs(a[0]));
    });
  });

  log.push("states tested: " + states.length);
  log.push("checks: " + comp.checks.length + ", failed: " + Object.keys(failedChecks).filter(function (k) { return k.indexOf("draw") !== 0; }).length);
  return {
    ok: errors.length === 0, errors: errors.slice(0, 25), warnings: warnings, log: log,
    states: states.length, distinct_states: Object.keys(seen).length, bases: nb,
    checks: comp.checks.map(function (c) { return c.name; }), control_effect: effect,
    default_out_keys: outs[0] ? Object.keys(outs[0]) : [], scalar_keys: scalarKeys, sweep_effects: sweepEffects
  };
}

function checkViewShapes(spec, out, errors) {
  function is1D(a) { return Array.isArray(a) && a.every(function (x) { return typeof x === "number"; }); }
  function is2D(a) { return Array.isArray(a) && a.length > 0 && a.every(is1D); }
  (spec.views || []).forEach(function (v) {
    var w = "view " + (v.id || v.title) + " (" + v.type + ")";
    var g = function (k) { return JCore.getPath(out, k); };
    if (v.type === "bars") {
      if (v.series) v.series.forEach(function (s) { if (!is1D(g(s.key))) errors.push(w + ": series '" + s.key + "' must be a 1-D number array"); });
      else if (!is1D(g(v.key))) errors.push(w + ": key '" + v.key + "' must be a 1-D number array");
    } else if (v.type === "line") {
      if (!is1D(g(v.x))) errors.push(w + ": x '" + v.x + "' must be a 1-D number array");
      (v.series || []).forEach(function (s) { var y = g(s.key); if (!is1D(y) || (is1D(g(v.x)) && y.length !== g(v.x).length)) errors.push(w + ": series '" + s.key + "' must be a 1-D number array with same length as x"); });
      if (!(v.series || []).length) errors.push(w + ": needs series");
    } else if (v.type === "heatmap") {
      if (!is2D(g(v.key))) errors.push(w + ": key '" + v.key + "' must be a 2-D number array");
    } else if (v.type === "scatter") {
      var pts = g(v.key);
      if (!(Array.isArray(pts) && pts.every(function (p) { return is1D(p) && p.length >= 2; }))) errors.push(w + ": key '" + v.key + "' must be an array of [x,y] pairs");
    } else if (v.type === "sweep") {
      (v.y || []).forEach(function (y) { var k = typeof y === "string" ? y : y.key; if (typeof g(k) !== "number") errors.push(w + ": y '" + k + "' must be a scalar number returned by compute"); });
      if (!(v.y || []).length) errors.push(w + ": needs y");
    } else if (v.type === "stacked") {
      if (!is1D(g(v.key))) errors.push(w + ": key '" + v.key + "' must be a 1-D number array");
    } else if (v.type === "table") {
      (v.columns || []).forEach(function (c) { if (!Array.isArray(g(c.key))) errors.push(w + ": column '" + c.key + "' must be an array"); });
    }
  });
}

function makeStubCtx() {
  var noop = function () {};
  var ctx = {
    canvas: { width: 600, height: 260 },
    measureText: function (t) { return { width: String(t).length * 6 }; },
    createLinearGradient: function () { return { addColorStop: noop }; },
    createRadialGradient: function () { return { addColorStop: noop }; },
    getImageData: function () { return { data: [] }; }, setLineDash: noop, getLineDash: function () { return []; }
  };
  ["beginPath", "closePath", "moveTo", "lineTo", "arc", "arcTo", "rect", "fillRect", "strokeRect", "clearRect", "fill", "stroke",
    "fillText", "strokeText", "save", "restore", "translate", "rotate", "scale", "setTransform", "resetTransform", "quadraticCurveTo",
    "bezierCurveTo", "ellipse", "clip", "drawImage", "putImageData", "roundRect", "transform"].forEach(function (m) {
      ctx[m] = function () {
        for (var i = 0; i < arguments.length; i++) if (typeof arguments[i] === "number" && !isFinite(arguments[i])) throw new Error("ctx." + m + " called with non-finite number");
      };
    });
  return ctx;
}
