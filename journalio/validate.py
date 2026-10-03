"""Executes the generated spec in an embedded JS engine (same core as the page) and reports problems.

The spec is passed through a UTF-8 temp file (never through console encodings, which differ on Windows)
and executed in a separate, killable process so generated code can never hang the agent.
Engine/infrastructure failures are reported separately from spec errors so they never trigger an LLM repair.
"""
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
import io, json, os, sys
assets, spec_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
def done(obj):
    with io.open(out_path, "w", encoding="utf-8") as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj))
    os._exit(0)
try:
    from py_mini_racer import MiniRacer
    ctx = MiniRacer()
    for name in ("core.js", "validator.js"):
        with io.open(os.path.join(assets, name), encoding="utf-8") as f:
            ctx.eval(f.read())
    with io.open(spec_path, encoding="utf-8") as f:
        src = f.read()
except Exception as e:
    done({"__infra__": "%s: %s" % (type(e).__name__, str(e)[:300])})
try:
    done(ctx.eval("JSON.stringify(jValidate(%s))" % src, timeout_sec=12))
except Exception as e:
    name = type(e).__name__
    if "Timeout" in name:
        done({"ok": False, "errors": ["generated JavaScript did not finish within 12 s (infinite loop?)"], "states": 0})
    if name.startswith("JS"):
        done({"ok": False, "errors": ["JavaScript error while executing the spec: %s" % str(e)[:300]], "states": 0})
    done({"__infra__": "%s: %s" % (name, str(e)[:300])})
"""


def _tmp(text, suffix):
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _with_mini_racer(spec_json):
    import importlib.util
    if importlib.util.find_spec("py_mini_racer") is None:
        raise RuntimeError("mini-racer not installed")
    spec_path = _tmp(spec_json, ".json")
    out_path = _tmp("", ".json")
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        try:
            proc = subprocess.run([sys.executable, "-c", WORKER, ASSETS, spec_path, out_path],
                                  capture_output=True, timeout=45, env=env)
        except subprocess.TimeoutExpired:
            return {"ok": False, "errors": ["validation timed out: generated JavaScript probably contains an infinite loop"], "states": 0}
        with open(out_path, encoding="utf-8") as f:
            txt = f.read().strip()
        if not txt:
            raise RuntimeError("worker produced no result: " + proc.stderr.decode("utf-8", "replace")[-300:])
        res = json.loads(txt)
        if "__infra__" in res:
            raise RuntimeError(res["__infra__"])
        return res
    finally:
        for p in (spec_path, out_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def _with_node(spec_json):
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node not found")
    script = _read("core.js") + "\n" + _read("validator.js") + \
        "\nvar fs=require('fs');fs.writeFileSync(process.argv[3], JSON.stringify(jValidate(JSON.parse(fs.readFileSync(process.argv[2],'utf8')))),'utf8');"
    js_path = _tmp(script, ".js")
    spec_path = _tmp(spec_json, ".json")
    out_path = _tmp("", ".json")
    try:
        try:
            proc = subprocess.run([node, js_path, spec_path, out_path], capture_output=True, timeout=45)
        except subprocess.TimeoutExpired:
            return {"ok": False, "errors": ["validation timed out: generated JavaScript probably contains an infinite loop"], "states": 0}
        with open(out_path, encoding="utf-8") as f:
            txt = f.read().strip()
        if not txt:
            err = proc.stderr.decode("utf-8", "replace")
            if "Error" in err and "jValidate" not in err[:50]:
                return {"ok": False, "errors": ["JavaScript error while executing the spec: " + err.strip().splitlines()[-1][:300]], "states": 0}
            raise RuntimeError("node produced no result: " + err[-300:])
        return json.loads(txt)
    finally:
        for p in (js_path, spec_path, out_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def static_checks(spec):
    """Python-side checks that need no JS engine."""
    errs = []
    if not isinstance(spec, dict):
        return ["spec is not a JSON object"]
    comp = str(spec.get("compute", ""))
    if "return" not in comp and "=>" not in comp:
        errs.append("compute must be JavaScript code that returns an object of outputs")
    for bad in ("fetch(", "XMLHttpRequest", "import(", "document.", "window.", "localStorage"):
        if bad in comp:
            errs.append("compute must be pure math: remove '%s'" % bad)
    if "Math.random" in comp:
        errs.append("compute must be deterministic: remove Math.random")
    return errs


def validate(spec):
    """Return dict(ok, errors, warnings, engine, infra_errors, ...). Only `errors` are spec problems."""
    errs = static_checks(spec)
    spec_json = json.dumps(spec, ensure_ascii=True)  # pure ASCII: immune to any console/file encoding
    report = None
    engine = None
    infra = []
    for name, fn in (("mini-racer(V8)", _with_mini_racer), ("node", _with_node)):
        try:
            report = fn(spec_json)
            engine = name
            break
        except Exception as e:  # engine unavailable or crashed: try the next one
            infra.append("%s: %s" % (name, str(e)[:300]))
    if report is None:
        report = {"ok": not errs, "errors": [], "warnings": ["no JS engine available; only static checks ran"], "states": 0}
    report["errors"] = errs + list(report.get("errors", []))
    report["ok"] = not report["errors"]
    report["engine"] = engine or "none"
    report["infra_errors"] = infra
    return report
