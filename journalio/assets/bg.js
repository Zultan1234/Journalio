/* Journalio interactive background + page chrome (theme toggle, motion toggle, scroll progress).
   One generative animation per topic family, drawn in the paper's palette. Reacts to the pointer,
   to clicks, and pulses whenever the lab recomputes (JBG.pulse). Respects prefers-reduced-motion,
   pauses in background tabs, caps resolution. No libraries, no network. */
var JBG = (function () {
  "use strict";
  var root = document.documentElement;
  var cv = document.getElementById("bg");
  if (!cv || !cv.getContext) return { pulse: function () {} };
  var ctx = cv.getContext("2d");
  var engineName = root.getAttribute("data-engine") || "network";
  var W = 0, H = 0, DPR = 1, t = 0, last = 0, energy = 0, raf = null;
  var mouse = { x: -1e4, y: -1e4, on: false, vx: 0, vy: 0 };
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var motion = !reduce;
  var HUES = [0, 0, 0], dark = false;

  function readTheme() {
    var cs = getComputedStyle(root);
    HUES = [parseFloat(cs.getPropertyValue("--h")) || 220, parseFloat(cs.getPropertyValue("--h2")) || 280, parseFloat(cs.getPropertyValue("--h3")) || 180];
    dark = cs.getPropertyValue("--is-dark").trim() === "1";
  }
  function col(i, a, light) {
    var h = HUES[((i % 3) + 3) % 3];
    var l = light !== undefined ? light : (dark ? 64 : 52);
    return "hsla(" + h + "," + (dark ? 85 : 78) + "%," + l + "%," + a + ")";
  }
  function rnd(a, b) { return a + Math.random() * (b - a); }
  function resize() {
    DPR = Math.min(window.devicePixelRatio || 1, 1.5);
    W = window.innerWidth; H = window.innerHeight;
    cv.width = Math.round(W * DPR); cv.height = Math.round(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    if (E && E.init) E.init();
  }
  function fade(a) { // trail effect on a transparent canvas
    ctx.globalCompositeOperation = "destination-out";
    ctx.fillStyle = "rgba(0,0,0," + a + ")";
    ctx.fillRect(0, 0, W, H);
    ctx.globalCompositeOperation = "source-over";
  }
  function clear() { ctx.clearRect(0, 0, W, H); }

  // ------------------------------------------------------------------ engines
  var engines = {};

  engines.network = (function () { // nodes + proximity links; cursor attracts and connects
    var P = [], hex = false;
    return {
      init: function () {
        hex = root.getAttribute("data-motif") === "molecule";
        var n = Math.round(Math.max(45, Math.min(130, W * H / 8000))); P = [];
        for (var i = 0; i < n; i++) P.push({ x: rnd(0, W), y: rnd(0, H), vx: rnd(-.3, .3), vy: rnd(-.3, .3), r: rnd(1.5, 3.5), c: i % 3 });
      },
      frame: function (dt) {
        clear();
        var sp = 1 + energy * 4, R = 130;
        P.forEach(function (p) {
          var dx = mouse.x - p.x, dy = mouse.y - p.y, d2 = dx * dx + dy * dy;
          if (mouse.on && d2 < 200 * 200) { p.vx += dx / 9000; p.vy += dy / 9000; }
          p.vx *= .99; p.vy *= .99;
          p.x += p.vx * sp * dt; p.y += p.vy * sp * dt;
          if (p.x < 0 || p.x > W) p.vx *= -1; if (p.y < 0 || p.y > H) p.vy *= -1;
        });
        for (var i = 0; i < P.length; i++) for (var j = i + 1; j < P.length; j++) {
          var a = P[i], b = P[j], dx = a.x - b.x, dy = a.y - b.y, d = Math.sqrt(dx * dx + dy * dy);
          if (d < R) { ctx.strokeStyle = col(a.c, (1 - d / R) * .45); ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }
        }
        P.forEach(function (p) {
          var dx = mouse.x - p.x, dy = mouse.y - p.y, d = Math.sqrt(dx * dx + dy * dy);
          if (mouse.on && d < 180) { ctx.strokeStyle = col(2, (1 - d / 180) * .7); ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(mouse.x, mouse.y); ctx.stroke(); }
          ctx.fillStyle = col(p.c, .8);
          if (hex) { ctx.beginPath(); for (var k = 0; k < 6; k++) { var an = k * Math.PI / 3 + t / 3000; ctx.lineTo(p.x + p.r * 2.2 * Math.cos(an), p.y + p.r * 2.2 * Math.sin(an)); } ctx.closePath(); ctx.fill(); }
          else { ctx.beginPath(); ctx.arc(p.x, p.y, p.r * (1 + energy), 0, 6.283); ctx.fill(); }
        });
      }
    };
  })();

  engines.waves = (function () { // layered travelling waves; cursor height sets amplitude, x sets frequency
    return {
      init: function () {},
      frame: function () {
        clear();
        var amp = 30 + (mouse.on ? (1 - mouse.y / H) * 70 : 25) + energy * 60;
        var fr = .006 + (mouse.on ? mouse.x / W * .01 : .004);
        for (var k = 0; k < 6; k++) {
          ctx.beginPath();
          var y0 = H * (.25 + k * .11), ph = t / (900 + k * 260) + k;
          for (var x = 0; x <= W; x += 6) {
            var y = y0 + Math.sin(x * fr * (1 + k * .18) + ph) * amp * (1 - k * .1) + Math.sin(x * fr * 2.7 - ph * 1.3) * amp * .25;
            if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
          }
          ctx.strokeStyle = col(k, .42 - k * .04); ctx.lineWidth = 2.2 - k * .2; ctx.stroke();
        }
        for (var s = 0; s < W; s += 48) { // sample points on the first wave
          var yy = H * .25 + Math.sin(s * fr + t / 900) * amp + Math.sin(s * fr * 2.7 - t / 900 * 1.3) * amp * .25;
          ctx.fillStyle = col(2, .55); ctx.beginPath(); ctx.arc(s, yy, 2.6, 0, 6.283); ctx.fill();
        }
      }
    };
  })();

  engines.ripplegrid = (function () { // matrix of cells lit by expanding ripples (cursor, clicks, lab updates)
    var rip = [], next = 0;
    return {
      init: function () {},
      ripple: function (x, y, s) { rip.push({ x: x, y: y, r: 0, s: s || 1 }); if (rip.length > 14) rip.shift(); },
      frame: function (dt) {
        clear();
        if (t > next) { this.ripple(rnd(0, W), rnd(0, H), .6); next = t + 1800; }
        if (mouse.on && Math.random() < .06) this.ripple(mouse.x, mouse.y, .8);
        rip.forEach(function (r) { r.r += dt * .25; }); rip = rip.filter(function (r) { return r.r < Math.max(W, H); });
        var g = 30;
        for (var x = g / 2; x < W; x += g) for (var y = g / 2; y < H; y += g) {
          var v = .05 + .05 * Math.sin(x * .02 + t / 1500) * Math.cos(y * .02 - t / 1700);
          for (var i = 0; i < rip.length; i++) { var d = Math.abs(Math.hypot(x - rip[i].x, y - rip[i].y) - rip[i].r); if (d < 40) v += (1 - d / 40) * .5 * rip[i].s * (1 - rip[i].r / Math.max(W, H)); }
          if (v < .03) continue;
          ctx.fillStyle = col((x / g + y / g) | 0, Math.min(.65, v));
          ctx.fillRect(x - g * .36, y - g * .36, g * .72, g * .72);
        }
      }
    };
  })();

  engines.galton = (function () { // balls bounce through pegs and stack into a bell-shaped histogram
    var balls = [], bins = [], nb = 0;
    return {
      init: function () { nb = Math.max(12, Math.round(W / 40)); bins = new Array(nb).fill(0); balls = []; },
      frame: function (dt) {
        clear();
        var src = mouse.on ? mouse.x : W / 2, rate = 1 + energy * 6;
        for (var k = 0; k < rate; k++) if (balls.length < 220) balls.push({ x: src + rnd(-4, 4), y: -10, vx: 0, vy: rnd(1, 2), c: (Math.random() * 3) | 0 });
        ctx.fillStyle = col(1, .18);
        for (var py = 90; py < H * .6; py += 34) for (var px = (py / 34 % 2) * 20; px < W; px += 40) { ctx.beginPath(); ctx.arc(px, py, 2, 0, 6.283); ctx.fill(); }
        balls.forEach(function (b) {
          b.vy += .05 * dt / 16; b.y += b.vy * dt / 16; b.x += b.vx * dt / 16;
          if (b.y < H * .6 && Math.random() < .08) b.vx = (Math.random() < .5 ? -1 : 1) * rnd(.6, 1.4);
          b.vx *= .96;
        });
        balls = balls.filter(function (b) {
          if (b.y > H - 4) { var i = Math.min(nb - 1, Math.max(0, Math.floor(b.x / W * nb))); bins[i] += 1; return false; }
          ctx.fillStyle = col(b.c, .75); ctx.beginPath(); ctx.arc(b.x, b.y, 3.2, 0, 6.283); ctx.fill(); return true;
        });
        var mx = Math.max.apply(null, bins.concat([1])), bw = W / nb;
        for (var i = 0; i < nb; i++) {
          bins[i] *= .9995;
          var h = bins[i] / mx * H * .32;
          ctx.fillStyle = col(i, .32); ctx.fillRect(i * bw + 2, H - h, bw - 4, h);
        }
      }
    };
  })();

  engines.rain = (function () { // streams of bits; brighter near the cursor
    var cols = [], fs = 16;
    return {
      init: function () { cols = []; for (var x = 0; x < W; x += fs * 1.4) cols.push({ x: x, y: rnd(-H, 0), v: rnd(.05, .14), c: (Math.random() * 3) | 0 }); },
      frame: function (dt) {
        fade(.12);
        ctx.font = "600 " + fs + "px ui-monospace,Consolas,monospace";
        cols.forEach(function (c) {
          c.y += c.v * dt * (1 + energy * 3);
          if (c.y > H + 20) { c.y = rnd(-200, 0); c.v = rnd(.05, .14); }
          var near = mouse.on ? Math.max(0, 1 - Math.hypot(c.x - mouse.x, c.y - mouse.y) / 220) : 0;
          ctx.fillStyle = col(c.c, .35 + near * .6, dark ? 70 + near * 20 : 45);
          ctx.fillText(Math.random() < .5 ? "0" : "1", c.x, c.y);
        });
      }
    };
  })();

  engines.flowfield = (function () { // particles following a smooth vector field; cursor creates a vortex
    var P = [];
    function ang(x, y) {
      var a = Math.sin(x * .004 + t / 4000) * 1.6 + Math.cos(y * .005 - t / 5000) * 1.6;
      if (mouse.on) { var dx = x - mouse.x, dy = y - mouse.y, d = Math.hypot(dx, dy); if (d < 220) a = a * (d / 220) + (Math.atan2(dy, dx) + 1.9) * (1 - d / 220); }
      return a;
    }
    return {
      init: function () { P = []; var n = Math.round(Math.min(700, W * H / 2600)); for (var i = 0; i < n; i++) P.push({ x: rnd(0, W), y: rnd(0, H), c: i % 3, life: rnd(50, 300) }); clear(); },
      frame: function (dt) {
        fade(.05);
        var sp = (.9 + energy * 3) * dt / 16;
        ctx.lineWidth = 1.2;
        P.forEach(function (p) {
          var a = ang(p.x, p.y), nx = p.x + Math.cos(a) * sp * 1.6, ny = p.y + Math.sin(a) * sp * 1.6;
          ctx.strokeStyle = col(p.c, .4); ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(nx, ny); ctx.stroke();
          p.x = nx; p.y = ny; p.life -= 1;
          if (p.life < 0 || p.x < 0 || p.x > W || p.y < 0 || p.y > H) { p.x = rnd(0, W); p.y = rnd(0, H); p.life = rnd(80, 300); }
        });
      }
    };
  })();

  engines.circuit = (function () { // orthogonal traces with travelling current pulses
    var paths = [], pulses = [];
    return {
      init: function () {
        paths = []; pulses = [];
        var g = 40, n = Math.round(W * H / 26000);
        for (var i = 0; i < n; i++) {
          var x = Math.round(rnd(0, W) / g) * g, y = Math.round(rnd(0, H) / g) * g, pts = [[x, y]], dir = (Math.random() * 4) | 0;
          for (var k = 0; k < 6; k++) { var L = g * ((rnd(1, 4)) | 0); if (dir === 0) x += L; else if (dir === 1) y += L; else if (dir === 2) x -= L; else y -= L; pts.push([x, y]); dir = (dir + (Math.random() < .5 ? 1 : 3)) % 4; }
          paths.push({ pts: pts, c: i % 3 });
        }
      },
      spawn: function (near) {
        var best = paths[(Math.random() * paths.length) | 0];
        if (near && mouse.on) { var bd = 1e9; paths.forEach(function (p) { var d = Math.hypot(p.pts[0][0] - mouse.x, p.pts[0][1] - mouse.y); if (d < bd) { bd = d; best = p; } }); }
        if (best) pulses.push({ p: best, s: 0 });
      },
      frame: function (dt) {
        clear();
        if (Math.random() < .05 + energy * .5) this.spawn(Math.random() < .5);
        paths.forEach(function (p) {
          ctx.strokeStyle = col(p.c, .2); ctx.lineWidth = 2; ctx.beginPath();
          p.pts.forEach(function (q, i) { if (i) ctx.lineTo(q[0], q[1]); else ctx.moveTo(q[0], q[1]); }); ctx.stroke();
          ctx.fillStyle = col(p.c, .4); ctx.beginPath(); ctx.arc(p.pts[0][0], p.pts[0][1], 3.5, 0, 6.283); ctx.fill();
        });
        pulses = pulses.filter(function (u) {
          u.s += dt * .25;
          var pts = u.p.pts, rem = u.s;
          for (var i = 1; i < pts.length; i++) {
            var L = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
            if (rem <= L) { var f = rem / L, x = pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f, y = pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f;
              ctx.fillStyle = col(u.p.c + 1, .9); ctx.shadowColor = col(u.p.c + 1, .9); ctx.shadowBlur = 12; ctx.beginPath(); ctx.arc(x, y, 3.5, 0, 6.283); ctx.fill(); ctx.shadowBlur = 0; return true; }
            rem -= L;
          }
          return false;
        });
      }
    };
  })();

  engines.orbits = (function () { // particles on elliptical orbits around the centre and the cursor
    var P = [];
    return {
      init: function () { P = []; for (var i = 0; i < 140; i++) P.push({ a: rnd(40, Math.max(W, H) * .55), e: rnd(.25, .65), ph: rnd(0, 6.283), w: rnd(.00008, .0004), tilt: rnd(0, 3.14), c: i % 3, m: Math.random() < .25 }); },
      frame: function (dt) {
        fade(.18);
        var cx = W * .5, cy = H * .45;
        P.forEach(function (p) {
          p.ph += p.w * dt * (1 + energy * 4) * (300 / p.a);
          var ox = p.m && mouse.on ? mouse.x : cx, oy = p.m && mouse.on ? mouse.y : cy, a = p.m ? p.a * .3 : p.a, b = a * p.e;
          var x = Math.cos(p.ph) * a, y = Math.sin(p.ph) * b, ct = Math.cos(p.tilt), st = Math.sin(p.tilt);
          ctx.fillStyle = col(p.c, .7); ctx.beginPath(); ctx.arc(ox + x * ct - y * st, oy + x * st + y * ct, p.m ? 2.2 : 1.8, 0, 6.283); ctx.fill();
        });
        ctx.fillStyle = col(0, .5); ctx.beginPath(); ctx.arc(cx, cy, 8 + energy * 10, 0, 6.283); ctx.fill();
      }
    };
  })();

  engines.vectors = (function () { // vector field of arrows turning toward the cursor
    return {
      init: function () {},
      frame: function () {
        clear();
        var g = 46, tx = mouse.on ? mouse.x : W / 2 + Math.cos(t / 2500) * W * .3, ty = mouse.on ? mouse.y : H / 2 + Math.sin(t / 3100) * H * .3;
        for (var x = g / 2; x < W; x += g) for (var y = g / 2; y < H; y += g) {
          var dx = tx - x, dy = ty - y, d = Math.hypot(dx, dy) || 1, a = Math.atan2(dy, dx) + Math.sin(t / 2000 + x * .01) * .3;
          var L = Math.max(6, Math.min(20, 2600 / d)) * (1 + energy);
          var c = d < 160 ? 2 : ((x + y) / g | 0) % 2;
          ctx.strokeStyle = col(c, .22 + Math.min(.5, 60 / d)); ctx.lineWidth = 1.6;
          var ex = x + Math.cos(a) * L, ey = y + Math.sin(a) * L;
          ctx.beginPath(); ctx.moveTo(x - Math.cos(a) * L * .4, y - Math.sin(a) * L * .4); ctx.lineTo(ex, ey);
          ctx.lineTo(ex - Math.cos(a - .5) * 5, ey - Math.sin(a - .5) * 5); ctx.moveTo(ex, ey); ctx.lineTo(ex - Math.cos(a + .5) * 5, ey - Math.sin(a + .5) * 5); ctx.stroke();
        }
      }
    };
  })();

  engines.life = (function () { // Conway's Game of Life; the cursor paints live cells
    var g = 14, cw = 0, ch = 0, A = null, age = null, acc = 0;
    function seed() { for (var i = 0; i < A.length; i++) A[i] = Math.random() < .14 ? 1 : 0; }
    return {
      init: function () { cw = Math.ceil(W / g); ch = Math.ceil(H / g); A = new Uint8Array(cw * ch); age = new Uint16Array(cw * ch); seed(); },
      paint: function (x, y) { var i = Math.floor(x / g), j = Math.floor(y / g); for (var a = -1; a <= 1; a++) for (var b = -1; b <= 1; b++) { var ii = i + a, jj = j + b; if (ii >= 0 && jj >= 0 && ii < cw && jj < ch && Math.random() < .6) A[jj * cw + ii] = 1; } },
      frame: function (dt) {
        acc += dt;
        if (mouse.on) this.paint(mouse.x, mouse.y);
        if (acc > 130) {
          acc = 0;
          var B = new Uint8Array(cw * ch), alive = 0;
          for (var y = 0; y < ch; y++) for (var x = 0; x < cw; x++) {
            var n = 0;
            for (var a = -1; a <= 1; a++) for (var b = -1; b <= 1; b++) if (a || b) n += A[((y + a + ch) % ch) * cw + (x + b + cw) % cw];
            var i = y * cw + x, v = A[i] ? (n === 2 || n === 3) : n === 3;
            B[i] = v ? 1 : 0; age[i] = v ? Math.min(age[i] + 1, 60) : 0; alive += B[i];
          }
          A = B;
          if (alive < cw * ch * .02) seed();
        }
        clear();
        for (var k = 0; k < A.length; k++) if (A[k]) { ctx.fillStyle = col(age[k] < 3 ? 2 : age[k] < 12 ? 0 : 1, .5); ctx.fillRect((k % cw) * g + 1, Math.floor(k / cw) * g + 1, g - 2, g - 2); }
      }
    };
  })();

  engines.gears = (function () { // meshing gears; cursor proximity and lab updates speed them up
    var G = [], spin = 0;
    function draw(x, y, r, n, a, c) {
      ctx.beginPath();
      for (var k = 0; k < n * 2; k++) { var an = a + Math.PI * k / n, rr = k % 2 ? r * .82 : r; ctx.lineTo(x + rr * Math.cos(an - .12), y + rr * Math.sin(an - .12)); ctx.lineTo(x + rr * Math.cos(an + .12), y + rr * Math.sin(an + .12)); }
      ctx.closePath(); ctx.fillStyle = col(c, .22); ctx.fill(); ctx.strokeStyle = col(c, .5); ctx.lineWidth = 1.5; ctx.stroke();
      ctx.beginPath(); ctx.arc(x, y, r * .25, 0, 6.283); ctx.strokeStyle = col(c, .6); ctx.stroke();
    }
    return {
      init: function () {
        G = []; var x = -40, y = H * .35, r = 70, dir = 1;
        while (x < W + 100) { var n = Math.round(r / 6); G.push({ x: x, y: y, r: r, n: n, dir: dir, c: G.length % 3 }); var r2 = rnd(40, 95); var an = rnd(-.7, .7); x += (r + r2) * .9 * Math.cos(an); y = Math.min(H - 60, Math.max(60, y + (r + r2) * .9 * Math.sin(an))); r = r2; dir *= -1; }
      },
      frame: function (dt) {
        clear();
        var near = mouse.on ? Math.max(0, 1 - Math.abs(mouse.y - H * .4) / H) : 0;
        spin += dt * .0004 * (1 + energy * 6 + near * 2);
        G.forEach(function (g) { draw(g.x, g.y, g.r, g.n, spin * g.dir * 70 / g.r, g.c); });
      }
    };
  })();

  engines.tree = (function () { // recursive branching tree swaying in a cursor-driven wind
    function br(x, y, len, a, d, wind) {
      if (d === 0 || len < 4) return;
      var x2 = x + Math.cos(a) * len, y2 = y + Math.sin(a) * len;
      ctx.strokeStyle = col(d % 3, .25 + d * .04); ctx.lineWidth = d * .9; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x2, y2); ctx.stroke();
      if (d <= 2) { ctx.fillStyle = col(2, .45); ctx.beginPath(); ctx.arc(x2, y2, 2.5, 0, 6.283); ctx.fill(); }
      var s = .42 + Math.sin(t / 1400 + d) * .05 + wind * .06;
      br(x2, y2, len * .74, a - s + wind * .12, d - 1, wind);
      br(x2, y2, len * .74, a + s + wind * .12, d - 1, wind);
    }
    return {
      init: function () {},
      frame: function () {
        clear();
        var wind = (mouse.on ? (mouse.x / W - .5) * 2 : Math.sin(t / 3000)) + energy;
        [.18, .5, .82].forEach(function (f, i) { br(W * f, H + 10, H * (.17 + .04 * i), -Math.PI / 2, 9, wind); });
      }
    };
  })();

  engines.rays = (function () { // parallel rays refracted by a lens that follows the cursor
    return {
      init: function () {},
      frame: function () {
        clear();
        var lx = mouse.on ? mouse.x : W * .5 + Math.sin(t / 3000) * W * .15, cy = H * .5, f = 160 + energy * 120 + (mouse.on ? (mouse.y / H) * 220 : 80);
        ctx.strokeStyle = col(0, .35); ctx.lineWidth = 2;
        ctx.beginPath(); ctx.ellipse(lx, cy, 18, H * .36, 0, 0, 6.283); ctx.stroke();
        for (var k = -9; k <= 9; k++) {
          var y = cy + k * H * .036, c = (k + 30) % 3;
          ctx.strokeStyle = col(c, .45); ctx.lineWidth = 1.4; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(lx, y);
          var fx = lx + f, ex = W, ey = y + (cy - y) * (ex - lx) / f; ctx.lineTo(ex, ey); ctx.stroke();
        }
        ctx.fillStyle = col(2, .8); ctx.beginPath(); ctx.arc(lx + f, cy, 4 + energy * 4, 0, 6.283); ctx.fill();
      }
    };
  })();

  var E = engines[engineName] || engines.network;

  function loop(ts) {
    var dt = Math.min(50, ts - (last || ts)); last = ts; t += dt;
    energy *= Math.pow(.96, dt / 16);
    if (W) E.frame(dt);
    raf = motion ? requestAnimationFrame(loop) : null;
  }
  function start() { if (!raf && motion) { last = 0; raf = requestAnimationFrame(loop); } }
  function stop() { if (raf) cancelAnimationFrame(raf); raf = null; }

  // ------------------------------------------------------------------ interaction
  window.addEventListener("pointermove", function (e) { mouse.on = true; mouse.x = e.clientX; mouse.y = e.clientY; }, { passive: true });
  document.addEventListener("pointerleave", function () { mouse.on = false; });
  window.addEventListener("pointerdown", function (e) {
    if (e.target.closest && e.target.closest("button,input,select,a,summary,label,table")) return;
    energy = Math.min(1.5, energy + .6);
    if (E.ripple) E.ripple(e.clientX, e.clientY, 1.2);
    if (E.paint) for (var i = 0; i < 6; i++) E.paint(e.clientX + rnd(-30, 30), e.clientY + rnd(-30, 30));
    if (E.spawn) for (var k = 0; k < 4; k++) E.spawn(true);
  });
  window.addEventListener("resize", function () { resize(); if (!motion) E.frame(16); });
  document.addEventListener("visibilitychange", function () { if (document.hidden) stop(); else start(); });

  // ------------------------------------------------------------------ chrome: theme + motion toggles, progress bar
  var themeBtn = document.getElementById("themeBtn"), motionBtn = document.getElementById("motionBtn");
  var modes = ["auto", "light", "dark"], mode = 0;
  function applyTheme() {
    if (modes[mode] === "auto") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", modes[mode]);
    if (themeBtn) themeBtn.textContent = { auto: "◐ Auto", light: "☀ Light", dark: "☾ Dark" }[modes[mode]];
    readTheme(); if (!motion) { E.init && E.init(); for (var i = 0; i < 40; i++) E.frame(16); }
  }
  if (themeBtn) themeBtn.addEventListener("click", function () { mode = (mode + 1) % 3; applyTheme(); });
  if (motionBtn) {
    motionBtn.textContent = motion ? "❚❚ Motion" : "▶ Motion";
    motionBtn.addEventListener("click", function () { motion = !motion; motionBtn.textContent = motion ? "❚❚ Motion" : "▶ Motion"; if (motion) start(); else stop(); });
  }
  if (window.matchMedia) { var mq = window.matchMedia("(prefers-color-scheme: dark)"); if (mq.addEventListener) mq.addEventListener("change", readTheme); }
  // smooth section navigation + scroll-spy (no content is ever hidden, so full-page screenshots stay complete)
  var links = [].slice.call(document.querySelectorAll("#topbar nav a"));
  function arrive(el) {
    var h = el.tagName === "H2" ? el : (el.previousElementSibling && el.previousElementSibling.tagName === "H2" ? el.previousElementSibling : el.querySelector("h2"));
    if (!h) return;
    h.classList.remove("arrive"); void h.offsetWidth; h.classList.add("arrive");
  }
  links.forEach(function (a) {
    a.addEventListener("click", function (e) {
      var id = a.getAttribute("href").slice(1), el = document.getElementById(id);
      if (!el) return;
      e.preventDefault();
      el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
      if (history.replaceState) history.replaceState(null, "", "#" + id);
      setTimeout(function () { arrive(el); }, reduce ? 0 : 450);
    });
  });
  function spy() {
    var y = 90, cur = null;
    links.forEach(function (a) { var el = document.getElementById(a.getAttribute("href").slice(1)); if (el && el.getBoundingClientRect().top <= y) cur = a; });
    links.forEach(function (a) { a.classList.toggle("active", a === cur); });
  }
  window.addEventListener("scroll", spy, { passive: true });
  spy();
  var bar = document.getElementById("progress");
  window.addEventListener("scroll", function () {
    var h = document.documentElement.scrollHeight - innerHeight;
    if (bar) bar.style.transform = "scaleX(" + (h > 0 ? scrollY / h : 0) + ")";
  }, { passive: true });

  readTheme(); resize();
  if (motion) start(); else for (var i = 0; i < 60; i++) E.frame(16); // reduced motion: one settled still frame

  return {
    pulse: function (s) { energy = Math.min(1.5, energy + (s || .5)); if (E.ripple) E.ripple(W * rnd(.3, .7), H * rnd(.3, .7), 1); if (E.spawn) E.spawn(false); if (!motion) E.frame(16); },
    engine: engineName
  };
})();
