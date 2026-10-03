"""Prompts. Compact on purpose: every prompt and completion token counts toward the efficiency score.
The spec uses positional arrays for repeated items (expanded locally by spec.expand)."""

MOTIFS = "matrix|wave|distribution|network|bits|landscape|circuit|optics|orbit|tree|flow|geometry|molecule|cells|gear"

SYSTEM = r"""Output ONE JSON object, nothing else. A fixed renderer builds an offline teaching page from it; a validator EXECUTES your JS on ~60 input states.
Goal: teach ONE mechanism from the brief to the audience with a tiny executable model. Be brief and clear: shorter than the paper, every text <=20 words unless noted, whole JSON < 2500 tokens. Fidelity: tag P = stated in the source text, D = follows mathematically, T = toy/teaching simplification. Never invent section/equation numbers or results; never present toy numbers as paper results.

KEYS
"title": <=8 words
"paper": {"title","authors","year","section"}   section/equation exactly as given
"theme": {"motif":one of """ + MOTIFS + r""" (closest to the mechanism),"style":"classic"(old/theory papers)|"modern"|"technical"}
"what": the idea in plain words (<=30 words)   "why": why it matters (<=25 words)
"symbols": [[sym,meaning,tag]] <=6
"equations": [[expr,ref,tag]] 1-3
"stages": [[id,label,expr,[output keys]]] 3-5, input -> intermediates -> output
"controls": 2-4 objects (types below)
"compute": JS function BODY (ES2017, arrows ok) reading inp.<control id>; returns {key: number | 1-D array | 2-D array | string-label array}
"readouts": [[key,label,unit]] 2-4 scalars
"views": 2-3 objects (types below)
"first": [try,watch,why,preset]
"explore": [[title,change,observe,why(<=35 words),preset],[...]]   #1 simple/symmetric case, #2 extreme/limit/nonlinear case
"limit": [kind("assumption"|"misconception"),title,claim,try,observe,explain(<=35 words),preset]   make it testable in the lab
"claims": [[text,tag,ref]] 3-5; >=2 P (faithful to source text), >=1 T stating the simplification
"checks": [[name,expr]] 3-4 JS booleans over out, inp
"scope": what is left out (<=20 words)

CONTROLS ("effect": <=15 words, what changes downstream)
{"id","type":"slider","label","min","max","step","default","effect"}
{"id","type":"toggle","label","default","effect"}
{"id","type":"select","label","options":[[value,label]],"default","effect"}
{"id","type":"vector","label","min","max","step","default":[...],"length_from"(opt integer slider id),"labels"(opt),"effect"}
{"id","type":"matrix","label","min","max","step","default":[[...]],"row_labels","col_labels","effect"}
Every control must change some output. Controls must not override each other (use presets for canonical cases). Unnormalized weights are fine: normalize in compute.

VIEWS (keys = compute outputs; add "stage":stage id, "caption": what to watch <=15 words)
{"type":"bars","title","key","labels","ymin","ymax"}
{"type":"line","title","x","series":[[key,label]],"points":[[xkey,ykey,label]],"xlabel","ylabel"}  x/series = arrays you sample (<=100 pts) over a function's domain; points mark the current inputs (scalars, or equal-length arrays to mark several)
{"type":"sweep","title","control":slider id,"y":[[key,label]],"ylabel"}  renderer re-runs compute across the slider range: cheapest output-vs-input plot
{"type":"stacked","title","key","labels","total_label","unit","max_key"(opt)}  parts adding to a total
{"type":"heatmap","title","key"(2-D),"row_labels","col_labels","row_sums"(opt)}
{"type":"scatter","title","key"([[x,y],...]),"labels","arrows"(opt)}
{"type":"table","title","columns":[[key,label]],"total_row"(opt)}
{"type":"canvas","title","height","draw":JS body using ctx,out,inp,W,H}  only if nothing else fits
Choose by mechanism and make them complementary: the key intermediate quantity; the core relationship (curve with current point, or sweep); how parts combine into the output.

RULES compute handles every valid input (zeros, ties, extremes, all-zero weights -> fallback, 0*log0=0); no NaN/Infinity; deterministic; returns every key used. Checks hold for ALL valid inputs; write conditional facts as "!(cond)||fact"; tolerance 1e-9. Presets: {control id: value}, vectors/matrices at full length. Unicode math with <sub>/<sup>."""


def user_prompt(case, source_text, extra_fields=None):
    lines = ["SOURCE: " + case.get("source_url", ""),
             "AUDIENCE: " + case.get("audience", "engineering undergraduate"),
             "BRIEF: " + case.get("focus", ""),
             "SOURCE TEXT (extracted from SOURCE; tag P only what it states):"]
    lines.append(source_text.strip() if source_text.strip() else "(source not reachable: use only the brief and well-established facts about this paper; tag unsure statements D/T, not P)")
    return "\n".join(lines)


REPAIR_SYSTEM = r"""You fix a JSON spec for an interactive lab whose JS was executed by a validator. Return ONLY a JSON object with the top-level keys you change, each with its COMPLETE new value, in the same format as shown. Keep outputs used by stages/readouts/views/checks returned by compute. compute is a JS function body reading inp.<id>; checks are JS booleans over out, inp and must hold for all valid inputs ("!(cond)||fact" for conditional facts). No NaN/Infinity."""

REPAIR = """ERRORS:
%s

CURRENT:
%s"""
