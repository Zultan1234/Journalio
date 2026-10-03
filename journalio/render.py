"""Fills the self-contained HTML template with the spec + runtime."""
import html
import json
import os
import re

ASSETS = os.path.join(os.path.dirname(__file__), "assets")


def _read(name):
    with open(os.path.join(ASSETS, name), encoding="utf-8") as f:
        return f.read()


def _js_safe_json(obj):
    s = json.dumps(obj, ensure_ascii=False)
    return s.replace("</", "<\\/").replace("<!--", "<\\!--").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def render(spec, build_info, theme=None, figures=None):
    from . import theme as th
    theme = theme or {"hue": 220, "motif": "flow", "style": "modern"}
    build_info = dict(build_info, figures=figures or [])
    tpl = _read("template.html")
    title = re.sub(r"<[^>]+>", "", str(spec.get("title", "Interactive explanation")))
    parts = {
        "__TITLE__": html.escape(title),
        "__HUE__": str(int(theme["hue"])),
        "__STYLE__": theme["style"],
        "__MOTIF__": th.motif_svg(theme["motif"]),
        "__SPEC__": _js_safe_json(spec),
        "__BUILD__": _js_safe_json(build_info),
        "__CORE__": _read("core.js"),
        "__RUNTIME__": _read("runtime.js"),
    }
    # single pass replacement so inserted content is never re-scanned
    pattern = re.compile("|".join(re.escape(k) for k in parts))
    return pattern.sub(lambda m: parts[m.group(0)], tpl)
