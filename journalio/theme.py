"""Adaptive theme: hue -> palette (done in the page), motif -> hand-built SVG illustration, style -> typography.
The model spends ~15 tokens choosing {hue, motif, style}; a keyword classifier is the zero-token fallback."""
import math
import re

# motif -> (default hue, keywords)
MOTIF_INFO = {
    "matrix": (222, "attention matrix query key value transformer softmax linear algebra eigen tensor embedding token"),
    "wave": (195, "signal fourier frequency sampling nyquist filter spectrum oscillat wave audio convolution modulation"),
    "distribution": (265, "probability distribution entropy random variance bayes likelihood gaussian statistic expectation sampling"),
    "network": (285, "neural network neuron layer perceptron backprop activation graph node edge gnn"),
    "bits": (170, "bit information channel coding communication capacity compression shannon code noise redundancy"),
    "landscape": (28, "optimization gradient descent loss minimum convex learning rate momentum adam objective"),
    "circuit": (48, "circuit voltage current resistor capacitor inductor transistor amplifier rc rlc impedance"),
    "optics": (55, "light lens optic refraction reflection photon laser wavelength diffraction interference"),
    "orbit": (210, "orbit quantum atom electron energy level physics momentum particle gravity planet spin"),
    "tree": (140, "tree search decision recursion hierarchy algorithm sort heap binary dynamic programming"),
    "flow": (190, "flow queue throughput pipeline fluid traffic markov transition rate system feedback"),
    "geometry": (330, "vector projection angle geometry distance norm cosine similarity rotation kernel space"),
    "molecule": (160, "molecule chemical reaction bond enzyme protein kinetics concentration chemistry"),
    "cells": (95, "cell automaton population growth epidemic sir biology simulation agent grid life"),
    "gear": (15, "control pid controller robot mechanical torque dynamics servo feedback gain stability"),
}
STYLES = ("classic", "modern", "technical")


def classify(text):
    t = text.lower()
    best, score = "flow", 0
    for m, (_, kw) in MOTIF_INFO.items():
        sc = sum(t.count(w) for w in kw.split())
        if sc > score:
            best, score = m, sc
    return best


def resolve(spec, case):
    """Return a valid theme dict, filling anything missing for free."""
    th = spec.get("theme") if isinstance(spec.get("theme"), dict) else {}
    motif = str(th.get("motif", "")).lower().strip()
    src = "model"
    if motif not in MOTIF_INFO:
        motif = classify(" ".join([case.get("focus", ""), str(spec.get("title", "")), str(spec.get("intro", {}).get("what", ""))]))
        src = "keywords"
    try:
        hue = int(float(th.get("hue"))) % 360
    except (TypeError, ValueError):
        hue = MOTIF_INFO[motif][0]
    style = str(th.get("style", "")).lower()
    if style not in STYLES:
        try:
            year = int(re.findall(r"\d{4}", str(spec.get("paper", {}).get("year", "")))[0])
        except (IndexError, ValueError):
            year = 2020
        style = "classic" if year < 1985 else "modern"
    return {"hue": hue, "motif": motif, "style": style, "source": src}


# ------------------------------------------------------------------ SVG motifs (240x140, themed by CSS vars)
def _f(x):
    return ("%.1f" % x).rstrip("0").rstrip(".")


def _poly(pts):
    return " ".join("%s,%s" % (_f(x), _f(y)) for x, y in pts)


def _matrix():
    o = []
    vals = [[.9, .2, .4, .1], [.3, .8, .2, .5], [.1, .4, .9, .3], [.6, .1, .3, .7]]
    for i, r in enumerate(vals):
        for j, v in enumerate(r):
            o.append('<rect x="%d" y="%d" width="22" height="22" rx="3" class="f" fill-opacity="%.2f"/>' % (60 + j * 25, 18 + i * 25, .12 + .8 * v))
    o.append('<path d="M20 30 h30 M20 55 h30 M20 80 h30 M20 105 h30" class="a" stroke-width="3" stroke-linecap="round"/>')
    o.append('<path d="M168 66 h30" class="a" stroke-width="2.5" marker-end="url(#mh)"/>')
    o += ['<rect x="206" y="%d" width="18" height="22" rx="3" class="f2" fill-opacity="%.2f"/>' % (18 + i * 25, .3 + .15 * i) for i in range(4)]
    return "".join(o)


def _wave():
    a = _poly([(10 + x, 70 - 38 * math.sin(x / 22)) for x in range(0, 221, 4)])
    b = _poly([(10 + x, 70 - 18 * math.sin(x / 9 + 1)) for x in range(0, 221, 4)])
    st = "".join('<line x1="%s" y1="70" x2="%s" y2="%s" class="m"/><circle cx="%s" cy="%s" r="3.5" class="f2"/>' % (
        _f(10 + x), _f(10 + x), _f(70 - 38 * math.sin(x / 22)), _f(10 + x), _f(70 - 38 * math.sin(x / 22))) for x in range(0, 221, 20))
    return '<line x1="8" y1="70" x2="232" y2="70" class="l"/><polyline points="%s" class="a" stroke-width="3" fill="none"/><polyline points="%s" class="a" stroke-width="1.5" fill="none" opacity=".45"/>%s' % (a, b, st)


def _distribution():
    xs = [math.exp(-((i - 4.5) / 2.2) ** 2) for i in range(10)]
    bars = "".join('<rect x="%d" y="%s" width="17" height="%s" rx="2" class="f" fill-opacity=".75"/>' % (22 + i * 20, _f(120 - 95 * v), _f(95 * v)) for i, v in enumerate(xs))
    curve = _poly([(30 + t, 120 - 100 * math.exp(-(((t / 20) - 4.1) / 2.2) ** 2)) for t in range(0, 185, 3)])
    return '<line x1="14" y1="121" x2="228" y2="121" class="l"/>%s<polyline points="%s" class="a2" stroke-width="3" fill="none"/>' % (bars, curve)


def _network():
    layers = [[35, 70, 105], [30, 57, 84, 111], [50, 90]]
    xs = [40, 120, 200]
    o = []
    for li in range(2):
        for y1 in layers[li]:
            for y2 in layers[li + 1]:
                o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" class="m"/>' % (xs[li], y1, xs[li + 1], y2))
    for li, ys in enumerate(layers):
        for y in ys:
            o.append('<circle cx="%d" cy="%d" r="10" class="%s"/>' % (xs[li], y, "f" if li != 1 else "f2"))
    return "".join(o)


def _bits():
    bits = "10110010"
    o = ['<rect x="%d" y="20" width="22" height="26" rx="3" class="%s"/><text x="%d" y="38" class="%s">%s</text>' % (12 + i * 27, "f" if b == "1" else "fl", 23 + i * 27, "tx" if b == "1" else "tx0", b) for i, b in enumerate(bits)]
    o.append('<polyline points="%s" class="a" stroke-width="2.5" fill="none"/>' % _poly([(12 + x, 95 - (16 if bits[min(int(x / 27), 7)] == "1" else -16) + 4 * math.sin(x * 1.3)) for x in range(0, 214, 3)]))
    o.append('<path d="M120 52 v14" class="a" stroke-width="2" marker-end="url(#mh)"/>')
    return "".join(o)


def _landscape():
    o = ['<ellipse cx="135" cy="74" rx="%d" ry="%d" class="m" fill="none" opacity="%.2f"/>' % (r, r * .55, .3 + .12 * k) for k, r in enumerate([98, 78, 58, 39, 20])]
    path = [(22, 18), (60, 34), (90, 52), (110, 64), (124, 70), (133, 73)]
    o.append('<polyline points="%s" class="a2" stroke-width="2.5" fill="none" stroke-dasharray="5 3"/>' % _poly(path))
    o += ['<circle cx="%d" cy="%d" r="%s" class="f2"/>' % (x, y, 4.5 if i == len(path) - 1 else 3) for i, (x, y) in enumerate(path)]
    o.append('<circle cx="135" cy="74" r="4" class="f"/>')
    return "".join(o)


def _circuit():
    zig = _poly([(70, 30)] + [(78 + 8 * i, 22 if i % 2 == 0 else 38) for i in range(7)] + [(134, 30)])
    return ('<path d="M20 30 H70 M134 30 H200 V60 M200 80 V110 H20 V30" class="a" stroke-width="2.5" fill="none"/>'
            '<polyline points="%s" class="a" stroke-width="2.5" fill="none"/>'
            '<path d="M185 60 H215 M185 80 H215" class="a2" stroke-width="4"/>'
            '<circle cx="20" cy="70" r="16" class="fl"/><path d="M12 70 q4 -10 8 0 t8 0" class="a" fill="none" stroke-width="2"/>'
            '<path d="M95 110 v10 M86 120 h18 M90 125 h10 M93 130 h4" class="a" stroke-width="2"/>' % zig)


def _optics():
    o = ['<path d="M110 15 Q132 70 110 125 Q88 70 110 15 Z" class="fl" stroke="var(--acc)" stroke-width="2"/>',
         '<line x1="10" y1="70" x2="232" y2="70" class="l"/>']
    for y in (30, 50, 90, 110):
        o.append('<polyline points="10,%d 110,%d 190,70" class="a2" stroke-width="2" fill="none"/>' % (y, y))
        o.append('<line x1="190" y1="70" x2="228" y2="%s" class="a2" stroke-width="1.5" opacity=".5"/>' % _f(70 + (70 - y) * .48))
    o.append('<circle cx="190" cy="70" r="4" class="f"/>')
    return "".join(o)


def _orbit():
    return ('<ellipse cx="120" cy="70" rx="95" ry="28" class="a" fill="none" stroke-width="2"/>'
            '<ellipse cx="120" cy="70" rx="66" ry="22" class="a" fill="none" stroke-width="2" transform="rotate(60 120 70)"/>'
            '<ellipse cx="120" cy="70" rx="66" ry="22" class="a" fill="none" stroke-width="2" transform="rotate(-60 120 70)"/>'
            '<circle cx="120" cy="70" r="12" class="f"/><circle cx="215" cy="70" r="6" class="f2"/>'
            '<circle cx="87" cy="127" r="6" class="f2"/><circle cx="153" cy="13" r="6" class="f2"/>')


def _tree():
    nodes = {(0, 0): (120, 20)}
    o = []
    for d in range(1, 4):
        for k in range(2 ** d):
            x = 240 * (k + .5) / 2 ** d
            y = 20 + d * 36
            px, py = nodes[(d - 1, k // 2)]
            o.append('<line x1="%s" y1="%d" x2="%s" y2="%d" class="m"/>' % (_f(px), py, _f(x), y))
            nodes[(d, k)] = (x, y)
    hl = [(0, 0), (1, 1), (2, 2), (3, 5)]
    for (d, k), (x, y) in nodes.items():
        o.append('<circle cx="%s" cy="%d" r="%d" class="%s"/>' % (_f(x), y, 9 - d, "f2" if (d, k) in hl else "f"))
    return "".join(o)


def _flow():
    o = []
    for i, x in enumerate([14, 92, 170]):
        o.append('<rect x="%d" y="45" width="56" height="40" rx="8" class="%s"/>' % (x, "f" if i != 1 else "f2"))
    o.append('<path d="M70 65 H88 M148 65 H166" class="a" stroke-width="2.5" marker-end="url(#mh)"/>')
    o.append('<path d="M198 88 C198 125 42 125 42 92" class="a" stroke-width="2" fill="none" stroke-dasharray="5 4" marker-end="url(#mh)"/>')
    o.append('<path d="M42 42 C42 12 120 12 120 40" class="m" fill="none"/>')
    return "".join(o)


def _geometry():
    return ('<path d="M30 120 H225 M30 120 V12" class="l" stroke-width="1.5"/>'
            '<line x1="30" y1="120" x2="200" y2="40" class="a" stroke-width="3" marker-end="url(#mh)"/>'
            '<line x1="30" y1="120" x2="210" y2="100" class="a2" stroke-width="3" marker-end="url(#mh2)"/>'
            '<line x1="200" y1="40" x2="190" y2="103" class="m" stroke-dasharray="4 3"/>'
            '<path d="M80 114 A52 52 0 0 0 76 99" class="a" fill="none" stroke-width="2"/>'
            '<circle cx="190" cy="103" r="4" class="f2"/>')


def _molecule():
    cx, cy, r = 100, 70, 34
    pts = [(cx + r * math.cos(math.pi / 3 * k + math.pi / 6), cy + r * math.sin(math.pi / 3 * k + math.pi / 6)) for k in range(6)]
    o = ['<polygon points="%s" class="a" fill="none" stroke-width="3"/>' % _poly(pts),
         '<polygon points="%s" class="a" fill="none" stroke-width="1.5" opacity=".5"/>' % _poly([(cx + .75 * (x - cx), cy + .75 * (y - cy)) for x, y in pts])]
    for (x, y), (ex, ey) in [(pts[0], (180, 100)), (pts[4], (100, 12)), (pts[2], (30, 100))]:
        o.append('<line x1="%s" y1="%s" x2="%d" y2="%d" class="a" stroke-width="3"/><circle cx="%d" cy="%d" r="10" class="f2"/>' % (_f(x), _f(y), ex, ey, ex, ey))
    o += ['<circle cx="%s" cy="%s" r="5" class="f"/>' % (_f(x), _f(y)) for x, y in pts]
    return "".join(o)


def _cells():
    live = {(1, 2), (2, 3), (3, 1), (3, 2), (3, 3), (5, 5), (5, 6), (6, 5), (6, 6), (1, 8), (2, 8), (3, 8)}
    return "".join('<rect x="%d" y="%d" width="17" height="17" rx="3" class="%s"/>' % (12 + c * 22, 6 + r * 22 - 6, "f" if (r, c) in live else "fl")
                   for r in range(6) for c in range(10))


def _gear(cx, cy, r, n, cls):
    pts = []
    for k in range(n * 2):
        a = math.pi * k / n
        rr = r if k % 2 == 0 else r * .78
        pts += [(cx + rr * math.cos(a - .12), cy + rr * math.sin(a - .12)), (cx + rr * math.cos(a + .12), cy + rr * math.sin(a + .12))]
    return '<polygon points="%s" class="%s"/><circle cx="%s" cy="%s" r="%s" fill="var(--card)"/>' % (_poly(pts), cls, _f(cx), _f(cy), _f(r * .3))


def _gears():
    return _gear(85, 72, 50, 10, "f") + _gear(168, 52, 32, 7, "f2") + '<path d="M150 110 a25 25 0 0 0 40 0" class="a" fill="none" stroke-width="2" marker-end="url(#mh)"/>'


DRAW = {"matrix": _matrix, "wave": _wave, "distribution": _distribution, "network": _network, "bits": _bits,
        "landscape": _landscape, "circuit": _circuit, "optics": _optics, "orbit": _orbit, "tree": _tree,
        "flow": _flow, "geometry": _geometry, "molecule": _molecule, "cells": _cells, "gear": _gears}


def motif_svg(name):
    body = DRAW.get(name, _flow)()
    defs = ('<defs><marker id="mh" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            '<path d="M0,0L10,5L0,10z" fill="var(--acc)"/></marker><marker id="mh2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
            'markerHeight="6" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="var(--s2)"/></marker></defs>')
    return '<svg class="motif" viewBox="0 0 240 140" role="img" aria-label="decorative %s illustration">%s%s</svg>' % (name, defs, body)
