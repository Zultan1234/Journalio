#!/usr/bin/env python3
"""Journalio — Paper to Playground agent.

python agent.py --input case.json --output out --model MODEL_ID

Pipeline:  SOURCE -> PLAN+SPEC (1 LLM call) -> NORMALIZE -> EXECUTE & VALIDATE (embedded V8)
           -> REPAIR (targeted LLM patch, only if needed, <=2) -> DEGRADE (deterministic last resort)
           -> RENDER (self-contained HTML) -> trace.jsonl
"""
import argparse
import copy
import json
import os
import sys
import time

T_START = time.time()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from journalio import prompts  # noqa: E402
from journalio.llm import LLM, BudgetError, parse_json  # noqa: E402
from journalio.render import render  # noqa: E402
from journalio.source import gather  # noqa: E402
from journalio.trace import Trace  # noqa: E402
from journalio.validate import validate  # noqa: E402

MAX_REPAIRS = 2
MAIN_MAX_TOKENS = 14000
REPAIR_MAX_TOKENS = 7000
TAGS = {"PAPER": "PAPER", "DERIVED": "DERIVED", "PLAYGROUND": "PLAYGROUND", "TOY": "PLAYGROUND", "SOURCE": "PAPER"}


# ----------------------------------------------------------------------------- normalization
def normalize(spec, case, trace):
    """Deterministic, content-preserving fixes. Returns list of applied fixes."""
    fixes = []
    if not isinstance(spec, dict):
        return fixes
    spec.setdefault("paper", {})
    if not isinstance(spec["paper"], dict):
        spec["paper"] = {"title": str(spec["paper"])}
    if not spec["paper"].get("url") and case.get("source_url"):
        spec["paper"]["url"] = case["source_url"]
        fixes.append("paper.url filled from case")
    for k in ("symbols", "equations", "claims"):
        for item in spec.get(k) or []:
            if isinstance(item, dict):
                t = str(item.get("tag", "PLAYGROUND")).upper().strip("[] ")
                nt = TAGS.get(t, "PLAYGROUND")
                if nt != item.get("tag"):
                    item["tag"] = nt
    ids = set()
    for c in spec.get("controls") or []:
        if not isinstance(c, dict):
            continue
        ids.add(c.get("id"))
        if c.get("type") == "slider":
            try:
                c["min"], c["max"] = float(c["min"]), float(c["max"])
                if c["min"] > c["max"]:
                    c["min"], c["max"] = c["max"], c["min"]
                    fixes.append("slider %s min/max swapped" % c["id"])
                d = c.get("default")
                if not isinstance(d, (int, float)) or not (c["min"] <= d <= c["max"]):
                    c["default"] = min(max(float(d) if isinstance(d, (int, float)) else (c["min"] + c["max"]) / 2, c["min"]), c["max"])
                    fixes.append("slider %s default clamped" % c["id"])
                for key in ("min", "max"):
                    if float(c[key]).is_integer():
                        c[key] = int(c[key])
            except (KeyError, TypeError, ValueError):
                pass
        if c.get("type") == "checkbox":
            c["type"] = "toggle"
            fixes.append("control %s: checkbox->toggle" % c.get("id"))
        if c.get("type") in ("number", "range"):
            fixes.append("control %s: %s->slider" % (c.get("id"), c.get("type")))
            c["type"] = "slider"
    # presets referencing unknown controls
    holders = list(spec.get("explorations") or []) + [spec.get("limitation"), spec.get("first_action")]
    for h in holders:
        if isinstance(h, dict) and isinstance(h.get("preset"), dict):
            bad = [k for k in h["preset"] if k not in ids]
            for k in bad:
                del h["preset"][k]
            if bad:
                fixes.append("removed unknown preset keys %s" % bad)
    ex = spec.get("explorations")
    if isinstance(ex, list) and len(ex) > 2:
        spec["explorations"] = ex[:2]
        fixes.append("kept first 2 explorations")
    for i, v in enumerate(spec.get("views") or []):
        if isinstance(v, dict) and not v.get("id"):
            v["id"] = "v%d" % (i + 1)
    if isinstance(spec.get("checks"), list):
        spec["checks"] = [c if isinstance(c, dict) else {"name": str(c)[:60], "expr": str(c)} for c in spec["checks"]]
        spec["checks"] = [c for c in spec["checks"] if c.get("expr")]
    if fixes:
        trace.log("normalize", "auto_fix", "%d fix(es)" % len(fixes), fixes=fixes)
    return fixes


RELEVANT_ORDER = ["compute", "checks", "views", "readouts", "stages", "controls", "explorations", "limitation", "first_action", "claims"]


def relevant_keys(errors):
    text = " ".join(errors).lower()
    keys = set()
    if any(w in text for w in ("compute", "non-finite", "threw", "no effect", "returned keys", "deterministic", "check '")):
        keys.update(["compute", "controls"])
    if "check" in text:
        keys.add("checks")
    if "view" in text:
        keys.update(["views", "compute"])
    if "readout" in text:
        keys.add("readouts")
    if "stage" in text:
        keys.add("stages")
    if "control" in text or "slider" in text or "select" in text:
        keys.add("controls")
    if "exploration" in text:
        keys.add("explorations")
    if "limitation" in text:
        keys.add("limitation")
    if "first_action" in text:
        keys.add("first_action")
    if "claim" in text:
        keys.add("claims")
    if "missing field" in text:
        for e in errors:
            if "missing field" in e:
                keys.add(e.split("'")[1])
    if not keys:
        keys.update(["compute", "checks"])
    return [k for k in RELEVANT_ORDER if k in keys] + [k for k in keys if k not in RELEVANT_ORDER]


def degrade(spec, report, trace):
    """Last resort without LLM: drop elements that still fail so the page stays correct and usable."""
    errs = report.get("errors", [])
    removed = []
    failing_checks = {e.split("'")[1] for e in errs if e.startswith("check '")}
    if failing_checks:
        spec["checks"] = [c for c in spec.get("checks", []) if c.get("name") not in failing_checks]
        removed.append("checks %s" % sorted(failing_checks))
    bad_views = {e.split(" ")[1] for e in errs if e.startswith("view ")}
    if bad_views and len(spec.get("views", [])) > len(bad_views):
        spec["views"] = [v for v in spec["views"] if str(v.get("id")) not in bad_views]
        removed.append("views %s" % sorted(bad_views))
    bad_ro = [e for e in errs if e.startswith("readout ")]
    if bad_ro:
        keys = set(report.get("default_out_keys") or [])
        spec["readouts"] = [r for r in spec.get("readouts", []) if str(r.get("key", "")).split(".")[0] in keys]
        removed.append("readouts with missing keys")
    if any(e.startswith("stage ") for e in errs):
        keys = set(report.get("default_out_keys") or [])
        for s in spec.get("stages", []):
            s["keys"] = [k for k in s.get("keys", []) if str(k).split(".")[0] in keys]
        removed.append("stage keys not returned by compute")
    if removed:
        trace.log("degrade", "remove_failing_parts", "applied", removed=removed)
    return bool(removed)


def score(report):
    return len(report.get("errors", []))


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Journalio: paper excerpt -> interactive explanation")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--model", required=True)
    args = ap.parse_args()

    os.makedirs(args.output, exist_ok=True)
    trace = Trace(os.path.join(args.output, "trace.jsonl"))
    trace.log("start", "args", "ok", model=args.model, input=os.path.basename(args.input), python=sys.version.split()[0])

    # ---- stage 0: read task
    try:
        with open(args.input, encoding="utf-8-sig") as f:
            case = json.load(f)
        if not isinstance(case, dict):
            raise ValueError("case.json must contain a JSON object")
    except Exception as e:
        trace.log("input", "read_case", "failed", error=str(e)[:200])
        trace.close()
        return 2
    missing = [k for k in ("source_url", "focus", "audience") if not str(case.get(k, "")).strip()]
    trace.log("input", "read_case", "ok" if not missing else "missing fields %s" % missing, fields=sorted(case.keys()))
    case.setdefault("audience", "engineering undergraduate")

    # ---- stage 1: evidence
    excerpt, extra = gather(case, trace)
    trace.log("source", "evidence_ready", "ok", excerpt_chars=len(excerpt), extra_fields=sorted(extra.keys()))

    llm = LLM(args.model, trace, T_START)
    if not llm.key:
        trace.log("llm", "auth", "failed: OPENROUTER_API_KEY not set")
        trace.close()
        print("ERROR: set OPENROUTER_API_KEY", file=sys.stderr)
        return 3

    # ---- stage 2: plan + spec generation (single call; the plan is folded into the structured spec)
    messages = [{"role": "system", "content": prompts.SYSTEM},
                {"role": "user", "content": prompts.user_prompt(case, excerpt, extra)}]
    spec = None
    for attempt in range(2):
        try:
            content, finish = llm.chat(messages, MAIN_MAX_TOKENS, purpose="generate_spec" if attempt == 0 else "regenerate_spec")
        except (BudgetError, RuntimeError) as e:
            trace.log("generate", "llm_call", "failed", error=str(e)[:200])
            break
        try:
            spec = parse_json(content)
            if not isinstance(spec, dict):
                raise ValueError("top-level JSON is not an object")
            trace.log("generate", "parse_spec", "ok", keys=sorted(spec.keys()), finish_reason=finish)
            break
        except ValueError as e:
            trace.log("generate", "parse_spec", "failed", error=str(e)[:200], finish_reason=finish, revision=True)
            spec = None
            messages = messages[:2] + [{"role": "user", "content": "Your previous answer was not a complete valid JSON object (%s%s). Output ONLY the spec JSON, more concise (< 4500 tokens)." % (str(e)[:80], ", truncated" if finish == "length" else "")}]
    if spec is None:
        trace.log("end", "summary", "failed: no spec", requests=llm.requests, prompt_tokens=llm.prompt_tokens,
                  completion_tokens=llm.completion_tokens, total_tokens=llm.prompt_tokens + llm.completion_tokens,
                  elapsed_s=round(time.time() - T_START, 2))
        trace.close()
        return 4

    # ---- stage 3: normalize + execute/validate + repair
    normalize(spec, case, trace)
    report = validate(spec)
    trace.log("validate", "execute_spec", "pass" if report["ok"] else "%d error(s)" % len(report["errors"]),
              engine=report.get("engine"), states=report.get("states"), checks=report.get("checks"),
              control_effect=report.get("control_effect"), errors=report["errors"][:12], warnings=report.get("warnings"))
    best_spec, best_report = copy.deepcopy(spec), report
    revisions = 0
    while not report["ok"] and revisions < MAX_REPAIRS:
        keys = relevant_keys(report["errors"])
        current = {k: spec.get(k) for k in keys}
        if "controls" not in current:
            current["controls(read-only context)"] = [{k: c.get(k) for k in ("id", "type", "min", "max", "default", "length_from")} for c in spec.get("controls", []) if isinstance(c, dict)]
        msg = prompts.REPAIR % ("\n".join("- " + e for e in report["errors"][:15]), json.dumps(current, ensure_ascii=False))
        rmessages = [{"role": "system", "content": prompts.SYSTEM}, {"role": "user", "content": msg}]
        try:
            content, finish = llm.chat(rmessages, REPAIR_MAX_TOKENS, purpose="repair_%d" % (revisions + 1), temperature=0.2)
            patch = parse_json(content)
        except (BudgetError, RuntimeError, ValueError) as e:
            trace.log("repair", "llm_patch", "failed", error=str(e)[:200])
            break
        revisions += 1
        patch = {k: v for k, v in patch.items() if not k.startswith("controls(")}
        spec.update(patch)
        normalize(spec, case, trace)
        report = validate(spec)
        trace.log("repair", "apply_patch", "pass" if report["ok"] else "%d error(s)" % len(report["errors"]),
                  revision=revisions, patched_keys=sorted(patch.keys()), errors=report["errors"][:12])
        if score(report) <= score(best_report):
            best_spec, best_report = copy.deepcopy(spec), report
    spec, report = best_spec, best_report

    if not report["ok"]:
        if degrade(spec, report, trace):
            report = validate(spec)
            trace.log("validate", "after_degrade", "pass" if report["ok"] else "%d error(s)" % len(report["errors"]), errors=report["errors"][:12])

    # ---- stage 4: render
    usable = not any(("compute threw at state [defaults]" in e) or ("compute: syntax error" in e) for e in report["errors"])
    build = {"validation": {k: report.get(k) for k in ("ok", "errors", "states", "checks", "engine")}, "revisions": revisions,
             "model": args.model}
    html = render(spec, build)
    out_html = os.path.join(args.output, "index.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    trace.log("render", "write_html", "ok", bytes=len(html.encode("utf-8")), self_contained=("<script src" not in html and "<link" not in html))

    elapsed = round(time.time() - T_START, 2)
    trace.log("end", "summary", "success" if usable else "page written but compute unusable",
              validation_ok=report["ok"], revisions=revisions, requests=llm.requests,
              prompt_tokens=llm.prompt_tokens, completion_tokens=llm.completion_tokens,
              total_tokens=llm.prompt_tokens + llm.completion_tokens, elapsed_s=elapsed)
    trace.close()
    return 0 if usable else 5


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles
        except Exception:
            pass
    try:
        code = main()
    except KeyboardInterrupt:
        code = 130
    sys.stdout.flush()
    sys.stderr.flush()
    sys.exit(code)
