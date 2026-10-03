/* Journalio core: shared by the browser runtime AND the build-time validator.
   Pure functions only (no DOM). */
var JCore = (function () {
  "use strict";

  function clone(x) { return JSON.parse(JSON.stringify(x)); }
  function isNum(x) { return typeof x === "number" && isFinite(x); }

  function getPath(obj, path) {
    if (path === undefined || path === null) return undefined;
    if (typeof path !== "string") return path; // literal value
    var parts = path.split(".");
    var cur = obj;
    for (var i = 0; i < parts.length; i++) {
      if (cur === undefined || cur === null) return undefined;
      cur = cur[parts[i]];
    }
    return cur;
  }

  function clampNum(v, c) {
    v = Number(v);
    if (!isFinite(v)) v = isNum(c.default) ? c.default : (isNum(c.min) ? c.min : 0);
    if (isNum(c.min) && v < c.min) v = c.min;
    if (isNum(c.max) && v > c.max) v = c.max;
    return v;
  }

  function resolveLen(spec, inp, fixed, from, fallback) {
    if (from && inp[from] !== undefined) {
      var n = Math.round(Number(inp[from]));
      if (isFinite(n) && n > 0) return n;
    }
    if (isNum(fixed) && fixed > 0) return Math.round(fixed);
    return fallback;
  }

  function fitVector(arr, n, fill, c) {
    var out = [];
    arr = Array.isArray(arr) ? arr : [];
    for (var i = 0; i < n; i++) {
      var v = i < arr.length ? arr[i] : (fill !== undefined ? fill : (arr.length ? arr[arr.length - 1] : 0));
      out.push(clampNum(v, { min: c.min, max: c.max, default: isNum(fill) ? fill : 0 }));
    }
    return out;
  }

  /* Make an input object valid for the spec: fill defaults, clamp, resize vectors/matrices. */
  function fixInputs(spec, inp) {
    var out = {};
    inp = inp || {};
    var ctrls = spec.controls || [];
    // scalar controls first (vectors may depend on them)
    ctrls.forEach(function (c) {
      var v = inp[c.id] !== undefined ? inp[c.id] : c.default;
      if (c.type === "slider") {
        v = clampNum(v, c);
        if (c.integer || (isNum(c.step) && Math.abs(c.step - Math.round(c.step)) < 1e-12 && Math.abs(Number(c.min || 0) - Math.round(Number(c.min || 0))) < 1e-12)) v = Math.round(v);
        out[c.id] = v;
      } else if (c.type === "toggle") {
        out[c.id] = (v === true || v === "true" || v === 1);
      } else if (c.type === "select") {
        var opts = (c.options || []).map(function (o) { return (o && typeof o === "object") ? o.value : o; });
        var hit = opts.filter(function (o) { return String(o) === String(v); });
        out[c.id] = hit.length ? hit[0] : (opts.length ? opts[0] : v);
      }
    });
    ctrls.forEach(function (c) {
      var v = inp[c.id] !== undefined ? inp[c.id] : c.default;
      if (c.type === "vector") {
        var dflt = Array.isArray(c.default) ? c.default : [];
        var n = resolveLen(spec, out, c.length, c.length_from, dflt.length || 3);
        out[c.id] = fitVector(Array.isArray(v) ? v : dflt, n, c.fill, c);
      } else if (c.type === "matrix") {
        var d = Array.isArray(c.default) ? c.default : [[0]];
        var r = resolveLen(spec, out, c.rows, c.rows_from, d.length || 2);
        var k = resolveLen(spec, out, c.cols, c.cols_from, (d[0] || []).length || 2);
        var src = Array.isArray(v) ? v : d;
        var m = [];
        for (var i = 0; i < r; i++) {
          var row = src[i] !== undefined ? src[i] : (d[i] !== undefined ? d[i] : (src[src.length - 1] || []));
          m.push(fitVector(row, k, c.fill !== undefined ? c.fill : 0, c));
        }
        out[c.id] = m;
      }
    });
    return out;
  }

  /* Accept a bare function body, "function(inp){...}", "function compute(inp){...}" or "(inp)=>{...}". */
  var FN_RE = /^\s*(?:async\s+)?(?:function\b|\(?\s*[A-Za-z_$][\w$]*\s*(?:,\s*[A-Za-z_$][\w$]*\s*)*\)?\s*=>|\(\s*\)\s*=>)/;
  function makeFn(args, src, label, errors) {
    src = String(src || "").trim().replace(/^```(?:js|javascript)?\s*/, "").replace(/\s*```$/, "").replace(/;\s*$/, "");
    var bodies = [];
    if (FN_RE.test(src)) bodies.push("var __f = (" + src + ");\nreturn __f(" + args.join(", ") + ");");
    bodies.push(src);
    var firstErr = null;
    for (var i = 0; i < bodies.length; i++) {
      try { return new Function(args.join(","), '"use strict";\n' + bodies[i]); }
      catch (e) { if (!firstErr) firstErr = e; }
    }
    errors.push(label + ": syntax error: " + (firstErr && firstErr.message));
    return null;
  }

  function compile(spec) {
    var res = { compute: null, draws: {}, checks: [], errors: [] };
    res.compute = makeFn(["inp", "Math"], spec.compute, "compute", res.errors);
    (spec.views || []).forEach(function (v, i) {
      if (v.type === "canvas") {
        var f = makeFn(["ctx", "out", "inp", "W", "H"], v.draw, "view " + (v.id || i) + " draw", res.errors);
        if (f) res.draws[v.id || ("v" + i)] = f;
      }
    });
    (spec.checks || []).forEach(function (c, i) {
      var expr = String(c.expr || "").trim().replace(/;\s*$/, "");
      var src = FN_RE.test(expr) ? expr : (/^return\b/.test(expr) || /;\s*return\b/.test(expr) ? expr : "return (" + expr + ");");
      var errs = [];
      var fn = makeFn(["out", "inp", "Math"], src, "check '" + (c.name || i) + "'", errs);
      errs.forEach(function (e) { res.errors.push(e); });
      res.checks.push({ name: c.name || ("check " + (i + 1)), fn: fn, spec: c });
    });
    return res;
  }

  function run(compiled, inp) {
    if (!compiled.compute) throw new Error("compute not compiled");
    var out = compiled.compute(clone(inp), Math);
    if (!out || typeof out !== "object") throw new Error("compute must return an object");
    return out;
  }

  /* Return list of paths holding NaN/Infinity. */
  function badNumbers(x, path, acc) {
    acc = acc || []; path = path || "out";
    if (typeof x === "number") { if (!isFinite(x)) acc.push(path + "=" + x); }
    else if (Array.isArray(x)) { for (var i = 0; i < x.length && acc.length < 8; i++) badNumbers(x[i], path + "[" + i + "]", acc); }
    else if (x && typeof x === "object") { for (var k in x) if (Object.prototype.hasOwnProperty.call(x, k)) badNumbers(x[k], path + "." + k, acc); }
    return acc;
  }

  function evalChecks(compiled, out, inp) {
    return compiled.checks.map(function (c) {
      if (!c.fn) return { name: c.name, ok: false, err: "syntax" };
      try { var r = c.fn(out, inp, Math); return { name: c.name, ok: !!r }; }
      catch (e) { return { name: c.name, ok: false, err: e.message }; }
    });
  }

  function deepEqualNum(a, b, tol) {
    tol = tol || 1e-9;
    if (typeof a === "number" && typeof b === "number") return Math.abs(a - b) <= tol * Math.max(1, Math.abs(a), Math.abs(b)) || (a !== a && b !== b);
    if (Array.isArray(a) && Array.isArray(b)) {
      if (a.length !== b.length) return false;
      for (var i = 0; i < a.length; i++) if (!deepEqualNum(a[i], b[i], tol)) return false;
      return true;
    }
    if (a && b && typeof a === "object" && typeof b === "object") {
      var ka = Object.keys(a), kb = Object.keys(b);
      if (ka.length !== kb.length) return false;
      for (var j = 0; j < ka.length; j++) if (!deepEqualNum(a[ka[j]], b[ka[j]], tol)) return false;
      return true;
    }
    return a === b;
  }

  function changedKeys(prev, next) {
    var keys = {};
    Object.keys(next || {}).forEach(function (k) { if (!prev || !deepEqualNum(prev[k], next[k])) keys[k] = true; });
    Object.keys(prev || {}).forEach(function (k) { if (!next || !(k in next)) keys[k] = true; });
    return Object.keys(keys);
  }

  function fmt(v, d) {
    if (d === undefined || d === null) d = 3;
    if (typeof v === "boolean") return v ? "true" : "false";
    if (typeof v !== "number") return v === undefined || v === null ? "—" : String(v);
    if (!isFinite(v)) return String(v);
    if (v !== 0 && (Math.abs(v) >= 1e5 || Math.abs(v) < Math.pow(10, -d))) return v.toExponential(Math.max(1, d - 1));
    var s = v.toFixed(d);
    if (s.indexOf(".") >= 0) s = s.replace(/0+$/, "").replace(/\.$/, "");
    if (s === "-0") s = "0";
    return s;
  }

  /* Keys referenced by stages/readouts/views (for validation). */
  function referencedKeys(spec) {
    var refs = [];
    function add(k, where) { if (typeof k === "string" && k) refs.push({ key: k, where: where }); }
    (spec.stages || []).forEach(function (s) { (s.keys || []).forEach(function (k) { add(k, "stage " + s.id); }); });
    (spec.readouts || []).forEach(function (r) { add(r.key, "readout " + (r.label || r.key)); });
    (spec.views || []).forEach(function (v) {
      var w = "view " + (v.id || v.title);
      add(v.key, w); add(v.x, w);
      if (typeof v.labels === "string") add(v.labels, w);
      if (typeof v.row_labels === "string") add(v.row_labels, w);
      if (typeof v.col_labels === "string") add(v.col_labels, w);
      if (typeof v.highlight === "string") add(v.highlight, w);
      (v.series || []).forEach(function (s) { add(s.key, w); });
      (v.points || []).forEach(function (p) { add(p.x, w); add(p.y, w); });
      (v.vlines || []).forEach(function (p) { add(p.key, w); });
      (v.hlines || []).forEach(function (p) { add(p.key, w); });
      (v.columns || []).forEach(function (c) { add(c.key, w); });
      if (typeof v.segments === "string") add(v.segments, w);
      add(v.max_key, w);
      (v.y || []).forEach(function (y) { add(typeof y === "string" ? y : y.key, w); });
      (v.points || []).forEach(function (p) { if (typeof p.labels === "string") add(p.labels, w); });
    });
    return refs;
  }

  return {
    clone: clone, isNum: isNum, getPath: getPath, fixInputs: fixInputs, compile: compile, run: run,
    badNumbers: badNumbers, evalChecks: evalChecks, deepEqualNum: deepEqualNum, changedKeys: changedKeys,
    fmt: fmt, referencedKeys: referencedKeys
  };
})();
