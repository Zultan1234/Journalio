"""Executes the generated spec in an embedded JS engine (same core as the page) and reports problems."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ASSETS = os.path.join(os.path.dirname(__file__), "assets")


def _read(name):
    with open(os.path.join(ASSETS, name), encoding="utf-8") as f:
        return f.read()


WORKER = r"""
import json, os, sys
from py_mini_racer import MiniRacer
d = sys.argv[1]
src = sys.stdin.read()
ctx = MiniRacer()
ctx.eval(open(os.path.join(d, "core.js"), encoding="utf-8").read())
ctx.eval(open(os.path.join(d, "validator.js"), encoding="utf-8").read())
try:
    res = ctx.eval("JSON.stringify(jValidate(%s))" % src, timeout_sec=12)
    sys.stdout.write(res)
except Exception as e:
    sys.stdout.write(json.dumps({"ok": False, "errors": ["JS engine error (infinite loop or crash in generated code?): %s: %s" % (type(e).__name__, str(e)[:300])], "states": 0}))
sys.stdout.flush()
os._exit(0)
"""


def _with_mini_racer(spec_json):
    import importlib.util
    if importlib.util.find_spec("py_mini_racer") is None:
        raise RuntimeError("mini-racer not installed")
    # isolated, killable subprocess: generated code can never hang the agent
    try:
        out = subprocess.run([sys.executable, "-c", WORKER, ASSETS], input=spec_json, capture_output=True,
                             text=True, encoding="utf-8", timeout=40)
    except subprocess.TimeoutExpired:
        return {"ok": False, "errors": ["validation timed out: generated JS probably contains an infinite loop"], "states": 0}
    if not out.stdout.strip():
        raise RuntimeError("worker failed: " + out.stderr[-300:])
    return json.loads(out.stdout)


def _with_node(spec_json):
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node not found")
    script = _read("core.js") + "\n" + _read("validator.js") + "\nprocess.stdout.write(JSON.stringify(jValidate(" + spec_json + ")));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(script)
        path = f.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, encoding="utf-8", timeout=40)
        if out.returncode != 0:
            raise RuntimeError(out.stderr[-500:])
        return json.loads(out.stdout)
    finally:
        os.unlink(path)


def static_checks(spec):
    """Python-side checks that need no JS engine."""
    errs = []
    if not isinstance(spec, dict):
        return ["spec is not a JSON object"]
    if not isinstance(spec.get("compute"), str) or "return" not in spec.get("compute", ""):
        errs.append("compute must be a JS function body string containing a return statement")
    for bad in ("fetch(", "XMLHttpRequest", "import(", "document.", "window.", "localStorage"):
        if bad in str(spec.get("compute", "")):
            errs.append("compute must be pure math: remove '%s'" % bad)
    if "Math.random" in str(spec.get("compute", "")):
        errs.append("compute must be deterministic: remove Math.random")
    return errs


def validate(spec):
    """Return dict(ok, errors, warnings, engine, ...)."""
    errs = static_checks(spec)
    spec_json = json.dumps(spec, ensure_ascii=False).replace("</", "<\\/")
    report = None
    engine = None
    for name, fn in (("mini-racer(V8)", _with_mini_racer), ("node", _with_node)):
        try:
            report = fn(spec_json)
            engine = name
            break
        except Exception as e:  # engine unavailable or crashed
            last = "%s: %s" % (name, str(e)[:300])
            if "JSException" in type(e).__name__ or "SyntaxError" in str(e):
                errs.append("JS error while validating: " + str(e)[:300])
                engine = name
                break
    if report is None:
        report = {"ok": not errs, "errors": [], "warnings": ["no JS engine available; only static checks ran (%s)" % (locals().get("last", ""))], "states": 0}
    report["errors"] = errs + list(report.get("errors", []))
    report["ok"] = not report["errors"]
    report["engine"] = engine or "none"
    return report
