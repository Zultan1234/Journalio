# Journalio — Paper → Playground agent

Journalio turns a focused research-paper excerpt and a learning brief into a **self-contained interactive lab** (`out/index.html`) that teaches one mechanism to an engineering undergraduate. It also writes an execution trace (`out/trace.jsonl`).

**Team:** _add team member names here_

## Quick start

```bash
python -m pip install -r requirements.txt
export OPENROUTER_API_KEY=sk-or-...        # Windows PowerShell: $env:OPENROUTER_API_KEY="sk-or-..."
python agent.py --input examples/entropy/case.json --output out --model deepseek/deepseek-v4.1-flash
```

**MODEL_ID:** `deepseek/deepseek-v4.1-flash` (DeepSeek V4.1 Flash on OpenRouter). Any OpenRouter model ID works.

Requirements: Python 3.11+, no GPU, no system packages, no build step. The generated page needs no internet or API key. Open `out/index.html` directly or serve it with `python -m http.server`.

## Input format

`case.json` (UTF-8) has three required string fields: `source_url`, `focus` (the concept and required learning outcomes) and `audience`.

The source text is extracted from `source_url` without any LLM call, under a 12 s time budget:

- arXiv links use the paper's HTML version, which is sectioned and keeps equations as LaTeX.
- PDFs use PyMuPDF text. This covers direct links, IEEE Xplore stamp pages, DOI redirects, or a PDF saved next to case.json for paywalled papers.
- Other pages are stripped to plain text.

Only the paper's title/author line and the section(s) named in `focus` are sent to the model. If a section is longer than the budget, it is trimmed by priority rather than cut off: the heading and every paragraph containing equations, definitions or assumptions are kept first, the least informative paragraphs are dropped, and gaps are marked [...]. Recognised references include "Section 3.2.1" (sent with its parent section's short lead-in), "Sec. 6" and "Section II"; the extracted text is capped at about 1.8k tokens. If no section is named, the agent sends the paragraphs that best match the brief. If the source cannot be reached, for example when the network is limited to OpenRouter, the model works from the brief alone and the trace says so. If a case happens to include an `excerpt` field, it is used instead of downloading.

## Architecture

The model doesn't write a whole HTML page. It writes a compact **JSON spec** of the lab, with repeated items as positional arrays and word limits on every text field (about 1–2k completion tokens): the mechanism stages, the controls, a pure JavaScript `compute(inp)` function, the visual bindings, the explorations, source-tagged claims and invariant checks. A fixed, pre-tested runtime turns that spec into the page. This keeps the output small (fewer tokens, lower latency) and makes the result **executable and checkable**.

```
case.json
  │  source.py      excerpt from case (or fetched URL) → relevant-paragraph selection (≤14k chars)
  ▼
  │  figures.py     (background thread, 0 tokens) fetch the paper's HTML (e.g. arXiv), pick the figure
  │                 the brief/excerpt refers to, embed it as a data URI; fails fast when offline
[LLM call 1]        prompts.SYSTEM (~1k tokens): scope → evidence (P/D/T tags) → mechanism chain → minimal
  │                 executable model → controls/presets → invariants → theme {hue, motif, style}  ⇒ compact spec
  ▼
spec.py             expands the compact positional format (also accepts the verbose form)
  ▼
normalize           deterministic fixes (tags, slider ranges, unknown preset keys, ids; accepts compute written as
                    a body, function(inp){…} or an arrow function)
  ▼
validate.py         runs the SAME core.js the page uses, inside embedded V8 (mini-racer, killable subprocess,
  │                 UTF-8 temp files so it behaves identically on Windows/Linux). Every control is varied
  │                 from every base state (defaults, each preset, uneven vectors): slider min/mid/max,
  │                 toggles, select options, equal / one-hot / ramp / all-zero vectors, matrix patterns
  │                 → typically 40–110 executed states
  │                 • compute never throws, no NaN/∞ anywhere
  │                 • every key used by stages/readouts/views exists and has the right shape
  │                 • every control changes at least one computed quantity (no decorative controls)
  │                 • model-written invariants hold in every state; determinism
  │                 • structure: ≥2 controls, exactly 2 explorations, PAPER + PLAYGROUND claims, …
  ▼  errors?
auto-fix            unambiguous mistakes fixed without the LLM (e.g. a line plot over a scalar slider value
  │                 becomes a "sweep" of that slider)
  ▼  errors?
triage              free fixes for cosmetic problems: drop decorative controls/faulty extra views/readouts
  ▼  real problems left? (wrong maths, failing mechanism checks, NaN in any valid state, a guided
  │                 exploration whose preset changes nothing, missing predictions / Q&A / limitation)
[LLM repair ≤2]     short repair prompt with only the failing keys. The model answers with exact-match edits
  │                 {"key","find","replace"}: an edit whose `find` does not occur exactly once is rejected and the
  │                 rejection is reported in the next round. Full key replacement is allowed for larger fixes.
  │                 Every patch is re-validated.     only the failing keys + validator messages are sent back; a JSON patch is merged
  ▼  still errors?
degrade             drop still-failing checks/views/readouts so the page stays correct and usable
  ▼
enrich              no-token visual enrichment: if no sweep view exists, add one for the slider that moves the
  │                 headline readouts most (chosen from measured effects); kept only if it validates
  ▼
theme.py            hue → full light/dark palette (pure CSS hsl), motif → hand-built SVG illustration (15 topics),
  │                 style → typography (classic serif for old theory papers / modern / technical);
  │                 keyword classifier as zero-token fallback
render.py           template.html + core.js + runtime.js + spec + figures → single offline index.html
```

**Runtime features (generic, in `journalio/assets/`).** The orientation cards answer *what / why / what can I change / what should I watch*, followed by a "try this first" box. A clickable mechanism map shows a **live mini-chart of each intermediate quantity inside each stage** and lets the learner inspect its exact values. Controls can be sliders, toggles, selects, vectors (with variable length) or editable matrices. The visuals are SVG bars; function curves with the current operating point(s) marked; **sweeps**, where the page re-runs the model across a slider's range and marks the current value; **stacked contributions** that add up to a total, with a theoretical maximum; heatmaps with row sums; scatter plots and vectors; contribution tables; and an optional canvas. Every slider has a **▶ animate** button that drives it across its range while all downstream stages update. A **"Why did this change?"** panel traces the chain control → changed stages → readout deltas, and the changed stages and views are highlighted. The page also includes two guided explorations with one-click presets and predict-then-reveal explanations, a limitation/misconception lab, source-grounding labels (PAPER / DERIVED / PLAYGROUND), live invariant checks and a summary of the build-time verification.

**Math helpers.** Generated code calls a small library `F` (`sum`, `dot`, `matmul`, `transpose`, `softmax` with temperature, `normalize` (all-zero → uniform), `entropy` (0·log 0 = 0), `linspace`, `interp`, `integrate` (Simpson), `trapz`, `sinc`, `normalPdf`, `approx`; specialised `besselI0`/`besselI1`). It shortens the code the model writes and removes common numerical bugs. The helpers are unit-tested against reference values: `python tests/test_helpers.py`.

**Checks.** Two layers. The validator runs automatic checks: the maths runs in every tested state, there is no NaN/∞, every control changes an output, every guided exploration's preset changes the outputs, chart data has the right shape, and results are deterministic. The model also writes 2–4 mechanism-specific scientific checks: an equation recomputed independently, normalization of probability outputs, a known special or limiting case, a conservation law. Both layers are tested in all 40–110 states and logged in the trace. If a check still fails after the repair budget, it is removed and the page says so explicitly instead of showing "all passed".

**Teaching blocks.** Each guided exploration has, in order: what to change, a **prediction question**, a button that loads the setup, what to observe, and why it happens, all visible. A short **"Check your understanding"** section has 2–3 questions with answers. "Try this first" is derived from exploration 1, so the model does not write it twice.

**Text economy.** The page is meant to be much shorter than the paper. "What can I change?" and "What should I watch?" are generated from the controls and views, not written by the model. Every text field has a word limit.

**Images from the paper's PDF.** `pdffigs.py` uses PyMuPDF to read the PDF's text layer and find figure captions ("Fig. 3.", "Figure 2:"). It locates each figure's region next to its caption, bounded by the paragraphs around it and tightened to the actual ink, so it works for born-digital vector plots, embedded images and scanned papers with an OCR layer. It renders just that region as a compressed JPEG (typically 15–60 KB), scores captions against the brief and the figures named in the excerpt, and embeds the best one or two with their caption and PDF page number. The PDF is taken from a local file if one is provided (a `"pdf"` field in case.json, or any `.pdf` next to case.json), otherwise downloaded from `source_url`. Downloads handle direct PDF links, arXiv, IEEE Xplore stamp pages (needs a network with IEEE access) and DOI redirects. When a case has no excerpt, the same PDF supplies the text. All of this runs in a background thread during the LLM call and costs 0 tokens. When no PDF is reachable (e.g. during grading, where only OpenRouter is reachable) it is skipped in under a second, and the page relies on its live charts and topic illustration.

**Interface.** Every page gets a topic-specific design. A curated three-colour palette per topic family is picked deterministically from the paper title, so different papers look different. The page has an interactive animated background matched to the mechanism: a rippling grid for matrices, flowing waves for signals, a Galton board for probability, a node network for graphs, bit rain for information, a flow field for optimisation, current pulses for circuits, a refracting lens for optics, orbits, a swaying tree, a vector field, the Game of Life and meshing gears. It reacts to the cursor and clicks, and pulses whenever the lab recomputes. Cards are translucent glass, with gradient headings, a sticky section nav with reading progress, a light/dark/auto switch and a motion switch. `prefers-reduced-motion` is respected, and the animation pauses in background tabs. All of this costs 0 tokens: the model only names the topic family.

**Budgets.** The client enforces the assessment limits: at most 10 requests, at most 30,000 completion tokens and a 570 s deadline. A typical run makes **1 request** (2–3 only if repair is needed). Validator infrastructure problems never trigger a repair call, and TLS errors are retried only once. Hidden reasoning is turned off by default to save tokens. Temperature defaults to 0 (`JOURNALIO_TEMPERATURE` to experiment). This makes output more predictable, but not guaranteed identical or correct. Set `JOURNALIO_REASONING=low|medium|high` to turn it on.

**Trace.** `trace.jsonl` records one event per line with `t`, `stage`, `action` and `result`. LLM calls also log `prompt_tokens`, `completion_tokens`, `reasoning_tokens`, `elapsed_s` and the generation id. It also logs validator results (states tested, checks, control effects, errors), repairs, the final totals and the exit status. Credentials are never logged.

Exit codes: `0` success · `2` bad input · `3` no API key · `4` no spec from the model · `5` page written but the calculation is unusable.

## Files

| File | Role |
|---|---|
| `agent.py` | CLI and orchestration (generate → validate → repair → render) |
| `journalio/prompts.py` | system prompt with the spec schema; repair prompt |
| `journalio/llm.py` | OpenRouter client (requests) with budget enforcement and usage logging |
| `journalio/source.py` | reads the excerpt, optional fetch, relevance trimming |
| `journalio/validate.py` | runs `validator.js` in embedded V8 (falls back to `node` if present) |
| `journalio/render.py` | builds the single-file HTML |
| `journalio/spec.py` | compact → full spec expansion |
| `journalio/theme.py` | adaptive theme and SVG illustration library |
| `journalio/figures.py` | obtains the paper PDF (local file or download) in the background |
| `journalio/pdffigs.py` | finds, crops and embeds captioned figures from the PDF |
| `journalio/assets/core.js` | pure functions shared by the page and the validator |
| `journalio/assets/runtime.js`, `template.html` | generic page runtime and layout (no paper-specific content) |
| `tests/test_helpers.py` | unit tests for the math helpers used by generated code |
| `tokens.py` | token usage per run from trace.jsonl (`python tokens.py`, add `--calls` for per-call detail) |
| `rerender.py` | re-applies the current design to existing pages (no API calls) |
| `journalio/assets/bg.js` | interactive animated backgrounds and page chrome |
| `run_examples.py` | runs all or selected examples; writes summary.md and a gallery |
| `examples/` | example inputs (and generated outputs) |

## Examples

Two practice cases live in `examples/<name>/case.json`: the two public examples from the assignment brief, each with the three required fields (`source_url`, `focus`, `audience`).

| folder | paper and section | mechanism |
|---|---|---|
| `attention` | Vaswani et al. 2017, §3.2.1 | scaled dot-product attention |
| `entropy` | Shannon 1948, §6 | discrete entropy |

Run one example:

```bash
python agent.py --input examples/entropy/case.json --output examples/entropy/out --model deepseek/deepseek-v4.1-flash
```

Run all of them, or a subset, and get a cost and speed summary plus a gallery page:

```bash
python run_examples.py                       # all, one after another
python run_examples.py --jobs 3              # 3 at a time (faster)
python run_examples.py --only entropy        # one case
```

`run_examples.py` writes each page to `examples/<name>/out/` and creates `examples/summary.md`, a table of tokens, seconds, requests, repairs and check results. It also creates `examples/index.html`, a gallery linking to every generated page.

### Example results

These are the latest runs of both public examples with `deepseek/deepseek-v4.1-flash`; the outputs are in `examples/*/out/`. Graded outputs are generated fresh, so numbers will vary from run to run.

| Example | API calls | Prompt tokens | Completion tokens | Total tokens | Time | Checks |
|---|---|---|---|---|---|---|
| attention | 1 | 1,846 | 1,792 | 3,638 | 12.1 s | all passed |
| entropy | 1 | 1,723 | 1,439 | 3,162 | 6.2 s | all passed |

In both runs the agent read the named section from `source_url`: Section 3.2.1 from the arXiv HTML (2,240 characters sent) and Section 6 from Shannon's PDF (1,924 characters). It embedded two figures extracted from each paper's PDF and needed no repair calls. Small inconsistencies, such as a mechanism step pointing to an output that was never computed, were fixed in code at no token cost. In the attention run, one bar chart whose data had the wrong shape was removed, and the remaining charts were kept. Reproduce with `python run_examples.py` and `python tokens.py`.

## Requirements compliance

Each item below was checked against the code on a clean Python 3.11 install from `requirements.txt`. The checks used test runs (a local stand-in for OpenRouter for the failure cases) and Chromium.

| Requirement | How it is met |
|---|---|
| Reusable generator; identify, plan, generate, check, revise | One spec-generation call, execution in V8 across 40–110 input states, and targeted repairs. No paper-specific answers in the code. |
| Python 3.11, `agent.py` at the root, pinned `requirements.txt`, no GPU, server or system packages | `requests`, `mini-racer`, `PyMuPDF` (all pure pip wheels) |
| Command `python agent.py --input case.json --output out --model MODEL_ID` | Exactly this interface; MODEL_ID is given above |
| `case.json` with `source_url`, `focus`, `audience` | Only these three fields are required. The source text is extracted from `source_url`. |
| All model calls through OpenRouter with the supplied MODEL_ID; key from `OPENROUTER_API_KEY` | Hard-coded `https://openrouter.ai/api/v1/chat/completions` with Bearer auth. The key is never written to the trace, the page or the console. |
| ≤ 10 minutes, ≤ 10 requests including retries, ≤ 30,000 completion tokens | Enforced in `llm.py` (request counter, completion-token budget including reasoning tokens, 570 s deadline). Tested with garbage output (stops after 2 requests) and an outage (stops after 3). |
| `out/index.html`: single self-contained file, works offline in Chromium, no CDN, fonts or remote images | All CSS/JS and figures are embedded. Served locally, the page makes no outside requests. |
| `out/trace.jsonl`: stage/action/result per event, per-call tokens, seconds, checks, failures, revisions; no credentials or hidden reasoning | Every call also logs OpenRouter's generation id, so usage can be verified. Reasoning is disabled and model text is not logged. |
| Exit 0 on success, non-zero on failure | `0` success, `2` bad input, `3` no key, `4` no usable spec, `5` unusable calculation |
| Page: idea, why it matters, symbols for the audience | Orientation cards, symbol table, equations with references |
| A meaningful visual of the mechanism | Mechanism map with live values, charts chosen per mechanism, live sweeps, the paper's own figures |
| At least two meaningful controls updating computed results; intermediate values | The validator rejects a spec unless every control changes an output. All numbers are computed live. |
| Two guided explorations (change, observe, why) and one limitation or misconception | Each exploration has what to change, a prediction question, a setup button, what to observe and why it happens. The validator checks that each preset really changes the outputs. A testable limitation lab is included. |
| Source grounding; separate statements from the excerpt from examples and simplifications; no implied reproduction of results | PAPER / DERIVED / PLAYGROUND labels, section/equation references, and an explicit note that toy values are not the paper's results |
| README with team, architecture, setup, credits, MODEL_ID, and one example pair | This file, plus `examples/attention` and `examples/entropy` with their outputs |

## Development history

How the generator reached its current version, step by step. Token figures come from the traces of real runs unless marked otherwise.

1. **First version.** A single LLM call writes a JSON spec of the lab rather than raw HTML. A fixed, pre-tested page engine renders it. The spec's JavaScript is executed in embedded V8 on many input states, and failures are repaired. Output is a self-contained page and `trace.jsonl`.
2. **First live run (entropy): 9,964 tokens and 5 requests.** It exposed four bugs, all fixed:
   - the model wrote compute as `function(inp){…}`, so the page showed no numbers (all function forms are now accepted);
   - a Windows encoding crash in the validator wasted a repair call (UTF-8 temp files; engine problems never trigger repairs);
   - repeated SSL retries on an intercepting network (SSL errors are retried once);
   - a false "decorative control" error (every control is now tested from several base states).

   Richer visuals were added: live mini-charts inside the mechanism map, sweeps computed by re-running the model, stacked contributions, curves with marked points, and slider animation.
3. **Token reduction, round 1.** The model now writes a compact positional spec, and the system prompt went from about 2,000 to about 1,040 tokens. The page builds "What can I change / watch" itself. Cosmetic issues are fixed in code instead of by repair, and a repair uses a short dedicated prompt. A topic theme (palette, illustration, typography) costs about 15 tokens. A nine-case batch then averaged **4,506 tokens** per run.
4. **Interface.** Each topic family gets a curated palette chosen from the paper title, colourful light and dark modes, and an interactive animated background (13 engines) that reacts to the pointer and to lab updates. Also: glass cards, gradient headings, sticky navigation with reading progress, and theme/motion toggles. Fixes found on real outputs: a double-nested limitation, HTML entities shown as text, imprecise axis ticks, and sections isolated so one bad field cannot blank the page.
5. **Figures from the paper's PDF.** Captions are located in the PDF text layer. Each figure is cropped next to its caption, tightened to the ink, embedded, and enlarges on click. This works for born-digital and scanned PDFs. Navigation scrolls smoothly and highlights the current section.
6. **Requirements audit.**
   - The OpenRouter endpoint is hard-coded.
   - Inputs were reduced to the three required fields.
   - Extraction from `source_url` is section-targeted: only the title line and the section(s) the brief names are sent. For the attention page, this cut the source text in the prompt from about 7,800 to about 800 characters (local test page).
   - `tokens.py` reports usage per run.
7. **Token reduction, round 2 (quality first).**
   - Generated code calls a library of unit-tested math helpers (`tests/test_helpers.py`, 35/35 passing). On test specs, code written by the model was 37–47% shorter.
   - Controls use a compact format, and "try this first" is derived from exploration 1.
   - Repairs use exact-match edits: ambiguous edits are rejected, and every patch is re-validated.
   - Every scientific or teaching failure is still repaired: wrong maths, failing mechanism checks, NaN in any valid state, broken explorations.
   - Long sections are trimmed by priority, keeping equations, definitions and assumptions.
   - Temperature is 0 and remains configurable.
   - Prediction questions and a "Check your understanding" Q&A were added.
   - On a phone, the controls panel no longer gets covered.

   Result on the same two cases:

| Case | Before (round 1) | Current version |
|---|---|---|
| attention | 5,447 tokens, 2 calls (1 repair) | **3,638 tokens, 1 call** |
| entropy | 3,250 tokens, 1 call | **3,162 tokens, 1 call** |

## Credits and reuse

- [requests](https://pypi.org/project/requests/) (Apache-2.0): HTTP client.
- [mini-racer](https://pypi.org/project/mini-racer/) (ISC): embedded V8, used to execute and validate the generated JavaScript at build time.
- [PyMuPDF](https://pypi.org/project/PyMuPDF/) (AGPL-3.0, Artifex): PDF text extraction and figure rendering.
- All page runtime code (SVG charts, controls, layout) was written for this project with the help of an AI coding assistant (Claude). It has no external JS/CSS libraries, CDNs or fonts.
- Practice cases are based on the two public examples: Vaswani et al. (2017), *Attention Is All You Need*, and Shannon (1948), *A Mathematical Theory of Communication*.
