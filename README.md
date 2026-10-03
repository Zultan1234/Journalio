# Journalio: Paper → Playground agent

Journalio turns a research paper and a short learning brief into a **self-contained interactive lab** (`out/index.html`) that teaches one mechanism to an engineering undergraduate. It also writes an execution trace (`out/trace.jsonl`).

**Team:** Mahdi Slim, Amir Darwich

## Quick start

```bash
python -m pip install -r requirements.txt
export OPENROUTER_API_KEY=sk-or-...        # Windows PowerShell: $env:OPENROUTER_API_KEY="sk-or-..."
python agent.py --input examples/entropy/case.json --output out --model deepseek/deepseek-v4.1-flash
```

**MODEL_ID:** `deepseek/deepseek-v4.1-flash` (DeepSeek V4.1 Flash on OpenRouter).

Requirements: Python 3.11+, no GPU, no system packages, no build step. The generated page needs no internet connection or API key.

## Input

`case.json` (UTF-8) has three required string fields: `source_url`, `focus` (the concept and required learning outcomes) and `audience`.

The source text is extracted from `source_url` without any LLM call, under a 12 s time budget:

- arXiv links use the paper's HTML version, which is sectioned and keeps equations as LaTeX.
- PDFs use PyMuPDF. This covers direct links, IEEE Xplore stamp pages, DOI redirects, or a PDF placed next to `case.json`.
- Other pages are stripped to plain text.

Only the paper's title/author line and the section(s) named in `focus` are sent to the model. Examples of such references are "Section 3.2.1" (sent with its parent section's short lead-in), "Sec. 6" or "Section II". The section text is capped at 7,000 characters. If no section is named, the agent sends the paragraphs that best match the brief. If the source cannot be reached, for example when the network is limited to OpenRouter, the model works from the brief alone and the trace records this. If a case happens to include an `excerpt` field, it is used instead of downloading.

## Architecture

The model writes a compact **JSON spec** of the lab rather than HTML: mechanism stages, controls, a pure JavaScript `compute(inp)` function, chart bindings, explorations, source-tagged claims and checks. A fixed, generic page engine renders it.

```
case.json ── source.py: section-targeted text from source_url (no LLM)
   │        figures.py + pdffigs.py: paper PDF → captioned figures (background thread, 0 tokens)
   ▼
[LLM call 1]  prompts.SYSTEM (~1k tokens) → compact spec (positional rows, word limits)
   ▼
spec.py       expands the compact format; normalize: deterministic fixes (tags, ranges, preset keys, ids)
   ▼
validate.py   runs the SAME core.js the page uses in embedded V8 (mini-racer, killable subprocess). Every control
   │          is varied from several base states (defaults, presets, uneven inputs): typically 40–110 states.
   │          • compute never throws, no NaN/∞
   │          • every key used by stages, readouts and charts exists with the right shape
   │          • every control changes some computed output
   │          • the model's checks hold in every state; determinism; required fields present
   ▼ errors?
auto-fix / triage   free fixes for unambiguous or cosmetic problems (e.g. a line plot over a scalar slider becomes
   │                a sweep; a missing control variable is declared; a faulty extra chart or dangling reference
   │                is removed while the required parts remain)
   ▼ errors left?
[LLM repair ≤2]     short repair prompt with only the failing keys; the patch is merged and re-validated. If after
   │                one repair only checks still fail, no further call is made.
   ▼ still failing?
unresolved          failing checks are NOT deleted: they stay on the page marked ⚠ UNRESOLVED (the equation or the
   │                check may be wrong), the badge counts them as not holding, and the page says
   │                "not fully verified" instead of "all passed". The trace records validation_ok: false.
   ▼
enrich + render     free sweep chart if none exists; topic theme; single self-contained index.html
```

**Page contents.** Each page has:

- orientation cards (what is this / why it matters / what to change / what to watch) and a "try this first" box;
- a mechanism map with a live mini-chart of each intermediate quantity;
- a lab with sliders, toggles, selects, vectors or editable matrices, plus readouts;
- charts chosen per mechanism: bars, curves with the current point marked, sweeps computed by re-running the model across a slider's range, stacked contributions, heatmaps, scatter plots and tables;
- a "Why did this change?" panel tracing control → changed stages → readout changes;
- notation and equations, two guided explorations (what to change, what to observe, and why it happens, shown in an expandable box), and a limitation or misconception lab;
- source-grounding labels PAPER / DERIVED / PLAYGROUND, live checks, and a summary of the build-time verification.

A "Load this setup" button appears when the model provides a preset for an exploration.

**Figures from the paper's PDF.** PyMuPDF locates figure captions ("Fig. 3.", "Figure 2:") in the PDF text layer. Each figure region is cropped next to its caption, bounded by the surrounding paragraphs and tightened to the ink, so this works for born-digital and scanned PDFs. The best-matching one or two figures are embedded as compressed JPEG data URIs with their caption and page number, and clicking a figure enlarges it. This step costs 0 tokens and is skipped within about a second when no PDF is reachable.

**Interface.** Each topic family has a curated three-colour palette, picked deterministically from the paper title. The model names only the topic family, at about 15 tokens. Pages have colourful light and dark modes and an interactive animated background matched to the topic (13 engines). The background reacts to the pointer and pulses on recompute. Other features: glass cards, a sticky section navigation with smooth scrolling and reading progress, and theme/motion toggles. `prefers-reduced-motion` is respected.

**Budgets.** `llm.py` enforces at most 10 requests (including retries), at most 30,000 completion tokens (reasoning tokens included) and a 570 s deadline. A typical run makes one request. Hidden reasoning is disabled; temperature is 0.3. SSL errors are retried only once.

**Trace.** `trace.jsonl` has one JSON object per event, with `t`, `stage`, `action` and `result`. Each LLM call also records `prompt_tokens`, `completion_tokens`, `reasoning_tokens`, `elapsed_s` and the OpenRouter generation id, so usage can be verified. Validator results (states, checks, control effects, errors), repairs, unresolved checks and final totals are also logged. Credentials and model reasoning are never logged.

Exit codes: `0` success · `2` bad input · `3` no API key · `4` no usable spec from the model · `5` page written but the calculation is unusable.

## Files

| File | Role |
|---|---|
| `agent.py` | CLI and orchestration (generate → validate → fix/repair → render) |
| `journalio/prompts.py` | system prompt with the compact spec schema; repair prompt |
| `journalio/llm.py` | OpenRouter client (requests) with budget enforcement and usage logging |
| `journalio/source.py` | section-targeted text extraction from `source_url` |
| `journalio/spec.py` | compact → full spec expansion |
| `journalio/validate.py` | runs `validator.js` in embedded V8 (falls back to `node` if present) |
| `journalio/figures.py`, `journalio/pdffigs.py` | obtain the paper PDF; find, crop and embed captioned figures |
| `journalio/theme.py` | topic palettes and SVG illustrations |
| `journalio/render.py` | builds the single-file HTML |
| `journalio/assets/core.js` | pure functions shared by the page and the validator |
| `journalio/assets/validator.js` | build-time execution checks |
| `journalio/assets/runtime.js`, `template.html`, `bg.js` | generic page engine, layout and interactive background |
| `run_examples.py` | runs the examples; writes `examples/summary.md` and a gallery |
| `tokens.py` | token usage per run from `trace.jsonl` (`--calls` for per-call detail) |
| `rerender.py` | re-applies the current page design to an existing output (no API calls) |
| `examples/` | the two public examples with their inputs and generated outputs |

## Examples

The two public examples from the assignment brief, each with the three required fields:

| folder | paper and section | mechanism |
|---|---|---|
| `attention` | Vaswani et al. 2017, §3.2.1 | scaled dot-product attention |
| `entropy` | Shannon 1948, §6 | discrete entropy |

```bash
python agent.py --input examples/attention/case.json --output examples/attention/out --model deepseek/deepseek-v4.1-flash
python agent.py --input examples/entropy/case.json --output examples/entropy/out --model deepseek/deepseek-v4.1-flash
python tokens.py
```

### Example results

The included outputs come from runs with `deepseek/deepseek-v4.1-flash`. Graded outputs are generated fresh, so numbers vary from run to run.

| Example | API calls | Prompt tokens | Completion tokens | Total tokens | Time | Checks |
|---|---|---|---|---|---|---|
| attention | 1 | 1,846 | 1,792 | 3,638 | 12.1 s | all passed |
| entropy | 1 | 1,723 | 1,439 | 3,162 | 6.2 s | all passed |

Both runs read the named section from `source_url`: Section 3.2.1 from the arXiv HTML (2,240 characters sent) and Section 6 from Shannon's PDF (1,924 characters). Each embedded two figures from the paper's PDF and needed no repair calls. Small inconsistencies, such as a stage pointing to an output that was never computed, were fixed in code at no token cost. In the attention run, one bar chart whose data had the wrong shape was removed, and the remaining charts were kept.

### Known limitations

- **Placeholder text from the model.** The model sometimes copies a field name instead of writing content. In the included outputs, the "try this first" box shows "try / watch / why", and the attention explorations show "observe" under *what to observe*. The validator checks structure and calculations, not whether a text field is meaningful, so this is not caught automatically.
- **Optional presets.** In the included outputs no exploration has a preset, so the pages show no "Load this setup" buttons; the learner follows the written instructions instead.
- **Network during grading.** If only OpenRouter is reachable, no source text or figures can be downloaded. The model then works from the brief alone and the page relies on its computed charts.

## Requirements compliance

Each item below was checked on a clean Python 3.11 install from `requirements.txt` and in Chromium. A local stand-in for OpenRouter was used for the failure cases.

| Requirement | How it is met |
|---|---|
| Reusable generator: identify, plan, generate, check, revise | One spec-generation call, execution in V8 across 40–110 input states, free fixes and up to 2 repairs. No paper-specific answers in the code. |
| Python 3.11, `agent.py` at the root, pinned `requirements.txt`; no GPU, server or system packages | `requests`, `mini-racer`, `PyMuPDF` (pip wheels only) |
| `python agent.py --input case.json --output out --model MODEL_ID` | Exactly this interface; MODEL_ID is given above |
| `case.json` with `source_url`, `focus`, `audience` | Only these three are required; the source text is extracted from `source_url` |
| All calls through OpenRouter with the supplied MODEL_ID; key from `OPENROUTER_API_KEY` | Hard-coded `https://openrouter.ai/api/v1/chat/completions` with Bearer auth. The key is never written to the trace, the page or the console. |
| ≤ 10 minutes, ≤ 10 requests including retries, ≤ 30,000 completion tokens | Enforced in `llm.py`. Tested with garbage model output (stops after 2 requests) and an outage (stops after 3). |
| `out/index.html`: one self-contained file, works offline in Chromium, no CDN, fonts or remote images | All CSS/JS and figures are embedded. Served locally, the page makes no outside requests. |
| `out/trace.jsonl` with stage/action/result, per-call tokens and seconds, checks, failures, revisions; no credentials or hidden reasoning | See *Trace* above |
| Exit code 0 on success, non-zero on failure | See *Exit codes* above |
| Idea, why it matters, main symbols for the audience | Orientation cards, symbol table, equations with references |
| A meaningful visual of the mechanism | Mechanism map with live values, charts chosen per mechanism, sweeps, the paper's own figures |
| At least two controls that update computed results; intermediate values | The validator rejects a spec unless every control changes an output; all numbers are computed live |
| Two guided explorations (change, observe, why) and one limitation or misconception | Required fields of the spec (see *Known limitations* for the placeholder issue) |
| Source grounding; separate excerpt-supported statements from examples and simplifications; no implied reproduction of results | PAPER / DERIVED / PLAYGROUND labels, section/equation references, and an explicit note that toy values are not the paper's results |
| README with team, architecture, setup, credits, MODEL_ID, one example pair | This file and `examples/` |

## Development history

How the generator reached this version. Token figures come from the traces of real runs.

1. **First version.** One LLM call writes a JSON spec, not HTML. A fixed, tested page engine renders it, and the spec's JavaScript is executed in V8 on many input states and repaired on failure.
2. **First live run: 9,964 tokens, 5 requests.** It exposed four bugs, all fixed:
   - a function-wrapped `compute` that the page could not run;
   - a Windows encoding crash in the validator that wasted a repair call;
   - repeated SSL retries on an intercepting network;
   - a false "decorative control" error.

   Richer visuals were added: mini-charts in the mechanism map, sweeps, stacked contributions, curves with marked points, slider animation.
3. **Token reduction.** The model now writes a compact positional spec, and the system prompt went from about 2,000 to about 1,040 tokens. "What can I change / watch" is generated by the page. Cosmetic issues are fixed in code instead of by repair, and a repair uses a short prompt. A nine-case batch then averaged 4,506 tokens per run.
4. **Interface.** Topic palettes chosen from the paper title, colourful light and dark modes, 13 interactive background engines, glass cards and sticky navigation. Bugs fixed: a double-nested limitation block, HTML entities shown as text, axis tick precision, and sections isolated so one bad field cannot blank the page.
5. **Figures from the paper's PDF** with click-to-enlarge, plus smooth scrolling and section highlighting in the navigation.
6. **Requirements audit.**
   - The OpenRouter endpoint is hard-coded.
   - Inputs were reduced to the three required fields.
   - Extraction from `source_url` is section-targeted. For the attention page, this cut the source text sent to the model from about 7,800 to about 800 characters on a local test page.
   - `tokens.py` was added.
7. **An experimental round that was not kept.** Stricter requirements (prediction questions, Q&A, mandatory working presets), helper libraries and patch-style repairs raised measured usage to about 7–9k tokens per run, mostly through extra repair calls. The team kept the version from step 6 (about 3.5k tokens per run).
8. **Honest reporting of unresolved checks.** A check that still fails after repairs is no longer removed. It stays on the page marked unresolved, and the page reports "not fully verified" instead of "all passed".

Result on the two public examples:

| Case | Earlier run | This version |
|---|---|---|
| attention | 5,447 tokens, 2 calls (1 repair) | **3,638 tokens, 1 call** |
| entropy | 3,250 tokens, 1 call | **3,162 tokens, 1 call** |

## Credits and reuse

- [requests](https://pypi.org/project/requests/) (Apache-2.0): HTTP client.
- [mini-racer](https://pypi.org/project/mini-racer/) (ISC): embedded V8, used to execute and validate the generated JavaScript at build time.
- [PyMuPDF](https://pypi.org/project/PyMuPDF/) (AGPL-3.0, Artifex): PDF text extraction and figure rendering.
- All page runtime code (SVG charts, controls, layout, backgrounds) was written for this project with the help of an AI coding assistant (Claude). There are no external JS/CSS libraries, CDNs or fonts.
- The practice cases are the two public examples from the brief: Vaswani et al. (2017), *Attention Is All You Need*, and Shannon (1948), *A Mathematical Theory of Communication*.
