#!/usr/bin/env python3
"""Re-apply the current page design to already generated pages, reusing the spec stored inside them.
No API calls, no tokens.

    python rerender.py                       # every examples/*/out/index.html
    python rerender.py path/to/out/index.html
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from journalio import theme as themes  # noqa: E402
from journalio.render import render  # noqa: E402
from journalio.spec import expand  # noqa: E402


def blob(page, id_):
    m = re.search(r'id="%s">(.*?)</script>' % id_, page, re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))


def rerender(path):
    with open(path, encoding="utf-8") as f:
        page = f.read()
    spec, build = expand(blob(page, "spec-data")), blob(page, "build-data")
    case_path = os.path.join(os.path.dirname(os.path.dirname(path)), "case.json")
    case = json.load(open(case_path, encoding="utf-8")) if os.path.exists(case_path) else {}
    theme = themes.resolve(spec, case)
    figures = build.pop("figures", [])
    with open(path, "w", encoding="utf-8") as f:
        f.write(render(spec, build, theme, figures))
    print("%-45s %s / %s palette / %s background" % (path, theme["motif"], theme["palette"], theme["engine"]))


if __name__ == "__main__":
    paths = sys.argv[1:] or sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples", "*", "out", "index.html")))
    for p in paths:
        try:
            rerender(p)
        except Exception as e:
            print("skipped %s: %s" % (p, e))
