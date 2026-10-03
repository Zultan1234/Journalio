"""Expands the compact (positional) spec written by the model into the full structure used by the
runtime and validator. Accepts both compact and verbose forms, so repairs may use either."""

TAGS = {"P": "PAPER", "PAPER": "PAPER", "SOURCE": "PAPER", "D": "DERIVED", "DERIVED": "DERIVED",
        "T": "PLAYGROUND", "TOY": "PLAYGROUND", "PLAYGROUND": "PLAYGROUND"}


def tag(t):
    return TAGS.get(str(t or "T").upper().strip("[] "), "PLAYGROUND")


def _row(x, names, defaults=None):
    """list -> dict by position; dict passes through."""
    if isinstance(x, dict):
        return dict(x)
    if not isinstance(x, (list, tuple)):
        x = [x]
    d = dict(defaults or {})
    for i, n in enumerate(names):
        if i < len(x) and x[i] is not None:
            d[n] = x[i]
    return d


def _rows(xs, names, defaults=None):
    return [_row(x, names, defaults) for x in (xs or []) if x is not None]


def _pairs(xs, a="key", b="label"):
    out = []
    for x in xs or []:
        if isinstance(x, str):
            out.append({a: x})
        else:
            out.append(_row(x, [a, b, "dashed"]))
    return out


def _unwrap(x):
    """[[a, b, ...]] -> [a, b, ...] (models sometimes add a level of nesting)."""
    while isinstance(x, list) and len(x) == 1 and isinstance(x[0], (list, dict)):
        x = x[0]
    return x


LIMIT_NAMES = ["kind", "title", "claim", "try", "observe", "explain", "preset"]
FIRST_NAMES = ["try", "watch", "why", "preset"]


def expand(s):
    if not isinstance(s, dict):
        return s
    for k in ("first", "limit", "first_action", "limitation"):
        if k in s:
            s[k] = _unwrap(s[k])
    # repair blocks that were mis-expanded earlier (a whole positional row landed in the first field)
    for k, names in (("limitation", LIMIT_NAMES), ("first_action", FIRST_NAMES)):
        blk = s.get(k)
        if isinstance(blk, dict) and isinstance(blk.get(names[0]), list) and len(blk[names[0]]) >= 3:
            s[k] = _row(blk[names[0]], names)
    # intro
    intro = s.get("intro") if isinstance(s.get("intro"), dict) else {}
    for k in ("what", "why", "change", "watch"):
        if s.get(k) and not intro.get(k):
            intro[k] = s.pop(k)
    s["intro"] = intro
    if isinstance(s.get("scope"), str):
        s["scope"] = {"out": s["scope"]}
    s["symbols"] = _rows(s.get("symbols"), ["sym", "meaning", "tag"])
    s["equations"] = _rows(s.get("equations"), ["expr", "ref", "tag"])
    for k in ("symbols", "equations"):
        for it in s[k]:
            it["tag"] = tag(it.get("tag"))
    s["stages"] = _rows(s.get("stages"), ["id", "label", "expr", "keys", "desc"])
    for st in s["stages"]:
        if isinstance(st.get("keys"), str):
            st["keys"] = [st["keys"]]
        st["id"] = str(st.get("id", ""))
    s["readouts"] = _rows(s.get("readouts"), ["key", "label", "unit", "digits"])
    # controls
    for c in s.get("controls") or []:
        if isinstance(c, dict) and isinstance(c.get("options"), list):
            c["options"] = [o if isinstance(o, dict) else (_row(o, ["value", "label"]) if isinstance(o, (list, tuple)) else {"value": o, "label": str(o)}) for o in c["options"]]
    # views
    for v in s.get("views") or []:
        if not isinstance(v, dict):
            continue
        if "series" in v:
            v["series"] = _pairs(v["series"])
        if "y" in v and v.get("type") == "sweep":
            v["y"] = _pairs(v["y"] if isinstance(v["y"], list) else [v["y"]])
        if "columns" in v:
            v["columns"] = _pairs(v["columns"])
        if "points" in v:
            v["points"] = [p if isinstance(p, dict) else _row(p, ["x", "y", "label"]) for p in v["points"] or []]
        for k in ("hlines", "vlines"):
            if k in v:
                v[k] = _pairs(v[k])
    # teaching blocks
    if "first" in s and "first_action" not in s:
        s["first_action"] = _row(s.pop("first"), FIRST_NAMES)
    if "explore" in s and "explorations" not in s:
        s["explorations"] = _rows(s.pop("explore"), ["title", "change", "observe", "why", "preset"])
    elif isinstance(s.get("explorations"), list):
        s["explorations"] = _rows(s["explorations"], ["title", "change", "observe", "why", "preset"])
    if "limit" in s and "limitation" not in s:
        s["limitation"] = _row(s.pop("limit"), LIMIT_NAMES)
    # text fields must be strings
    for blk in [s.get("first_action"), s.get("limitation")] + list(s.get("explorations") or []):
        if isinstance(blk, dict):
            for kk, vv in list(blk.items()):
                if kk != "preset" and isinstance(vv, (list, dict)):
                    blk[kk] = " ".join(str(x) for x in vv) if isinstance(vv, list) else str(vv)
    s["claims"] = _rows(s.get("claims"), ["text", "tag", "ref"])
    for c in s["claims"]:
        c["tag"] = tag(c.get("tag"))
    s["checks"] = _rows(s.get("checks"), ["name", "expr", "why"])
    for blk in [s.get("first_action"), s.get("limitation")] + list(s.get("explorations") or []):
        if isinstance(blk, dict) and not isinstance(blk.get("preset"), dict):
            blk["preset"] = {}
    return s
