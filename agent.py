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
from journalio.figures import FigureFetcher  # noqa: E402
from journalio.render import render  # noqa: E402
from journalio.spec import expand  # noqa: E402
from journalio import theme as themes  # noqa: E402
from journalio.source import gather  # noqa: E402
from journalio.trace import Trace  # noqa: E402
from journalio.validate import validate  # noqa: E402

MAX_REPAIRS = 2
MAIN_MAX_TOKENS = 9000
REPAIR_MAX_TOKENS = 5000
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


def fix_from_report(spec, report, trace):
    """Deterministic fixes for common, unambiguous mistakes found by the validator (saves a repair call)."""
    fixes = []
    sliders = {c.get("id") for c in spec.get("controls", []) if isinstance(c, dict) and c.get("type") == "slider"}
    scalars = set(report.get("scalar_keys") or [])
    for v in spec.get("views", []):
        if not isinstance(v, dict) or v.get("type") != "line":
            continue
        x = v.get("x")
        if any(("view %s (line): x '%s' must be a 1-D" % (v.get("id"), x)) in e for e in report.get("errors", [])) and x in sliders:
            ys = [s_.get("key") for s_ in v.get("series", []) if s_.get("key") in scalars and s_.get("key") != x]
            if ys:
                new = {"id": v.get("id"), "type": "sweep", "control": x, "title": v.get("title"), "stage": v.get("stage"),
                       "caption": v.get("caption"), "xlabel": v.get("xlabel"), "ylabel": v.get("ylabel"),
                       "y": [{"key": s_.get("key"), "label": s_.get("label"), "dashed": s_.get("dashed")} for s_ in v.get("series", []) if s_.get("key") in ys]}
                v.clear()
                v.update({k: val for k, val in new.items() if val is not None})
                fixes.append("view %s: line over scalar '%s' converted to a sweep of slider '%s'" % (new["id"], x, x))
    if fixes:
        trace.log("normalize", "auto_fix_from_validation", "%d fix(es)" % len(fixes), fixes=fixes)
    return bool(fixes)


def enrich(spec, report, trace):
    """Add a model-driven 'sweep' plot (output vs a slider, computed live by the real model) if none exists.
    Costs no tokens; shows cause and effect across the whole input range."""
    views = spec.setdefault("views", [])
    if any(isinstance(v, dict) and v.get("type") == "sweep" for v in views) or len(views) >= 5:
        return None
    effects = report.get("sweep_effects") or {}
    readouts = [r for r in spec.get("readouts", []) if isinstance(r, dict) and r.get("key") in set(report.get("scalar_keys") or [])]
    best = None
    for c in spec.get("controls", []):
        if not isinstance(c, dict) or c.get("type") != "slider":
            continue
        moved = [r for r in readouts if r["key"] in effects.get(c.get("id"), []) and r["key"] != c.get("id")]
        if moved and (best is None or len(moved) > len(best[1])):
            best = (c, moved)
    if not best:
        return None
    c, moved = best
    unit = moved[0].get("unit")
    ys = [r for r in moved if r.get("unit") == unit][:2]
    label = lambda x: str(x or "")
    stage = None
    for st in spec.get("stages", []):
        if isinstance(st, dict) and ys[0]["key"] in (st.get("keys") or []):
            stage = st.get("id")
    view = {"id": "auto_sweep", "type": "sweep", "control": c["id"],
            "title": "%s as %s varies" % (label(ys[0].get("label") or ys[0]["key"]), label(c.get("label") or c["id"])),
            "y": [{"key": r["key"], "label": label(r.get("label") or r["key"])} for r in ys],
            "ylabel": (unit or "") if len(ys) > 1 else label(ys[0].get("label") or ys[0]["key"]) + (" (%s)" % unit if unit else ""),
            "caption": "Computed by re-running the model across the whole range of %s with every other input fixed; the dot marks the current setting." % label(c.get("label") or c["id"])}
    if stage:
        view["stage"] = stage
    views.append(view)
    trace.log("enrich", "add_sweep_view", "added", control=c["id"], y=[r["key"] for r in ys])
    return view


def triage(spec, report, trace):
    """Free, deterministic handling of cosmetic problems so LLM repairs are spent only on real bugs."""
    changed = []
    eff = report.get("control_effect") or {}
    deco = [k for k, v in eff.items() if not v]
    if deco and sum(1 for v in eff.values() if v) >= 2:
        spec["controls"] = [c for c in spec.get("controls", []) if c.get("id") not in deco]
        for blk in [spec.get("first_action"), spec.get("limitation")] + list(spec.get("explorations") or []):
            if isinstance(blk, dict) and isinstance(blk.get("preset"), dict):
                for k in deco:
                    blk["preset"].pop(k, None)
        changed.append("removed decorative control(s) %s" % deco)
    errs = report.get("errors", [])
    views = spec.get("views", [])
    bad = {e.split(" ")[1] for e in errs if e.startswith("view ")}
    if bad and len(views) - len(bad) >= 2:
        spec["views"] = [v for v in views if str(v.get("id")) not in bad]
        changed.append("dropped faulty view(s) %s" % sorted(bad))
    keys = set(report.get("default_out_keys") or [])
    if keys and any(e.startswith("readout ") for e in errs):
        spec["readouts"] = [r for r in spec.get("readouts", []) if str(r.get("key", "")).split(".")[0] in keys]
        changed.append("dropped readouts with missing keys")
    if keys and any(e.startswith("stage ") for e in errs):
        for st in spec.get("stages", []):
            st["keys"] = [k for k in st.get("keys", []) if str(k).split(".")[0] in keys]
        changed.append("stripped stage keys not returned by compute")
    if changed:
        trace.log("triage", "free_fixes", "%d fix(es)" % len(changed), fixes=changed)
    return bool(changed)


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
    figs = FigureFetcher(case, excerpt, trace).start()  # runs while the model writes; no tokens

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
            spec = expand(spec)
            trace.log("generate", "parse_spec", "ok", keys=sorted(spec.keys()), finish_reason=finish, response_chars=len(content))
            break
        except ValueError as e:
            trace.log("generate", "parse_spec", "failed", error=str(e)[:200], finish_reason=finish, revision=True)
            spec = None
            messages = messages[:2] + [{"role": "user", "content": "Your previous answer was not a complete valid JSON object (%s%s). Output ONLY the spec JSON, more concise (< 2500 tokens)." % (str(e)[:80], ", truncated" if finish == "length" else "")}]
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
              engine=report.get("engine"), states=report.get("states"), distinct_states=report.get("distinct_states"),
              checks=report.get("checks"), control_effect=report.get("control_effect"), errors=report["errors"][:12],
              warnings=report.get("warnings"), engine_issues=report.get("infra_errors") or None)
    if not report["ok"] and fix_from_report(spec, report, trace):
        report = validate(spec)
        trace.log("validate", "after_auto_fix", "pass" if report["ok"] else "%d error(s)" % len(report["errors"]), errors=report["errors"][:12])
    if not report["ok"] and triage(spec, report, trace):
        report = validate(spec)
        trace.log("validate", "after_triage", "pass" if report["ok"] else "%d error(s)" % len(report["errors"]), errors=report["errors"][:12])
    best_spec, best_report = copy.deepcopy(spec), report
    revisions = 0
    while not report["ok"] and revisions < MAX_REPAIRS:
        keys = relevant_keys(report["errors"])
        current = {k: spec.get(k) for k in keys}
        if "controls" not in current:
            current["controls(read-only context)"] = [{k: c.get(k) for k in ("id", "type", "min", "max", "default", "length_from")} for c in spec.get("controls", []) if isinstance(c, dict)]
        msg = prompts.REPAIR % ("\n".join("- " + e for e in report["errors"][:15]), json.dumps(current, ensure_ascii=False, separators=(",", ":")))
        rmessages = [{"role": "system", "content": prompts.REPAIR_SYSTEM}, {"role": "user", "content": msg}]
        try:
            content, finish = llm.chat(rmessages, REPAIR_MAX_TOKENS, purpose="repair_%d" % (revisions + 1), temperature=0.2)
            patch = parse_json(content)
        except (BudgetError, RuntimeError, ValueError) as e:
            trace.log("repair", "llm_patch", "failed", error=str(e)[:200])
            break
        revisions += 1
        patch = {k: v for k, v in patch.items() if not k.startswith("controls(")}
        spec.update(patch)
        spec = expand(spec)
        normalize(spec, case, trace)
        report = validate(spec)
        if not report["ok"] and fix_from_report(spec, report, trace):
            report = validate(spec)
        if not report["ok"] and triage(spec, report, trace):
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

    # ---- stage 3b: deterministic visual enrichment (no tokens), kept only if it validates
    added = enrich(spec, report, trace)
    if added is not None:
        r2 = validate(spec)
        if score(r2) <= score(report):
            report = r2
        else:
            spec["views"] = [v for v in spec["views"] if v is not added]
            trace.log("enrich", "add_sweep_view", "reverted (validation)")

    # ---- stage 4: render
    usable = not any(("compute threw at state [defaults]" in e) or ("compute: syntax error" in e) for e in report["errors"])
    build = {"validation": {k: report.get(k) for k in ("ok", "errors", "states", "checks", "engine")}, "revisions": revisions,
             "model": args.model}
    theme = themes.resolve(spec, case)
    trace.log("theme", "resolve", "ok", **theme)
    figures = figs.collect(wait=1.0)
    html = render(spec, build, theme, figures)
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
