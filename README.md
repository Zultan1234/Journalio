# Journalio — Paper → Playground agent

Journalio turns a focused research-paper excerpt and a learning brief into a **self-contained interactive lab** (`out/index.html`) that teaches one mechanism to an engineering undergraduate. It also writes an execution trace (`out/trace.jsonl`).

**Team:** Mahdi Slim, Amir Darwich

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

Only the paper's title/author line and the section(s) named in `focus` are sent to the model, for example "Section 3.2.1" (including the parent section's short lead-in), "Sec. 6" or "Section II", capped at about 1.8k tokens. If no section is named, the agent sends the paragraphs that best match the brief. If the source cannot be reached, for example when the network is limited to OpenRouter, the model works from the brief alone and the trace says so. If a case happens to include an `excerpt` field, it is used instead of downloading.

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
  ▼  real bugs left? (calculation errors, NaN, failing invariants, missing teaching blocks)
[LLM repair ≤2]     short dedicated repair prompt; only failing keys are sent     only the failing keys + validator messages are sent back; a JSON patch is merged
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

**Text economy.** The page is meant to be much shorter than the paper. "What can I change?" and "What should I watch?" are generated from the controls and views, not written by the model. Every text field has a word limit.

**Images from the paper's PDF.** `pdffigs.py` uses PyMuPDF to read the PDF's text layer and find figure captions ("Fig. 3.", "Figure 2:"). It locates each figure's region next to its caption, bounded by the paragraphs around it and tightened to the actual ink, so it works for born-digital vector plots, embedded images and scanned papers with an OCR layer. It renders just that region as a compressed JPEG (typically 15–60 KB), scores captions against the brief and the figures named in the excerpt, and embeds the best one or two with their caption and PDF page number. The PDF is taken from a local file if one is provided (a `"pdf"` field in case.json, or any `.pdf` next to case.json), otherwise downloaded from `source_url`. Downloads handle direct PDF links, arXiv, IEEE Xplore stamp pages (needs a network with IEEE access) and DOI redirects. When a case has no excerpt, the same PDF supplies the text. All of this runs in a background thread during the LLM call and costs 0 tokens. When no PDF is reachable (e.g. during grading, where only OpenRouter is reachable) it is skipped in under a second, and the page relies on its live charts and topic illustration.

**Interface.** Every page gets a topic-specific design. A curated three-colour palette per topic family is picked deterministically from the paper title, so different papers look different. The page has an interactive animated background matched to the mechanism: a rippling grid for matrices, flowing waves for signals, a Galton board for probability, a node network for graphs, bit rain for information, a flow field for optimisation, current pulses for circuits, a refracting lens for optics, orbits, a swaying tree, a vector field, the Game of Life and meshing gears. It reacts to the cursor and clicks, and pulses whenever the lab recomputes. Cards are translucent glass, with gradient headings, a sticky section nav with reading progress, a light/dark/auto switch and a motion switch. `prefers-reduced-motion` is respected, and the animation pauses in background tabs. All of this costs 0 tokens: the model only names the topic family.

**Budgets.** The client enforces the assessment limits: at most 10 requests, at most 30,000 completion tokens and a 570 s deadline. A typical run makes **1 request** (2–3 only if repair is needed). Validator infrastructure problems never trigger a repair call, and TLS errors are retried only once. Hidden reasoning is turned off by default to save tokens. Set `JOURNALIO_REASONING=low|medium|high` to turn it on.

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
| `tokens.py` | token usage per run from trace.jsonl (`python tokens.py`, add `--calls` for per-call detail) |
| `rerender.py` | re-applies the current design to existing pages (no API calls) |
| `journalio/assets/bg.js` | interactive animated backgrounds and page chrome |
| `run_examples.py` | runs all or selected examples; writes summary.md and a gallery |
| `examples/` | example inputs (and generated outputs) |

## Examples

Ten practice cases live in `examples/<name>/case.json`. They have the same shape and scope as the assessment cases: a focused brief plus a short excerpt. The excerpts are paraphrased from the papers for practice.

| folder | paper and section | mechanism |
|---|---|---|
| `attention` | Vaswani et al. 2017, §3.2.1 | scaled dot-product attention |
| `entropy` | Shannon 1948, §6 | discrete entropy |
| `positional` | Vaswani et al. 2017, §3.5 | sinusoidal positional encoding |
| `batchnorm` | Ioffe & Szegedy 2015, §3 / Alg. 1 | batch normalization |
| `adam` | Kingma & Ba 2015, Alg. 1 and §3 | moment estimates and bias correction |
| `distillation` | Hinton et al. 2015, §2 | softmax temperature |
| `dropout` | Hinton et al. 2012 | dropout and the "mean network" |
| `pagerank` | Brin & Page 1998, §2.1.1 | PageRank with damping |
| `sampling` | Shannon 1949, Theorem 1 | sampling theorem and aliasing |
| `klopfenstein` | Klopfenstein 1956 (Proc. IRE) | optimum equal-ripple impedance taper |

Run one example:

```bash
python agent.py --input examples/entropy/case.json --output examples/entropy/out --model deepseek/deepseek-v4.1-flash
```

Run all of them, or a subset, and get a cost and speed summary plus a gallery page:

```bash
python run_examples.py                       # all, one after another
python run_examples.py --jobs 3              # 3 at a time (faster)
python run_examples.py --only adam pagerank  # selected cases
```

`run_examples.py` writes each page to `examples/<name>/out/` and creates `examples/summary.md`, a table of tokens, seconds, requests, repairs and check results. It also creates `examples/index.html`, a gallery linking to every generated page.

## Credits and reuse

- [requests](https://pypi.org/project/requests/) (Apache-2.0): HTTP client.
- [mini-racer](https://pypi.org/project/mini-racer/) (ISC): embedded V8, used to execute and validate the generated JavaScript at build time.
- [PyMuPDF](https://pypi.org/project/PyMuPDF/) (AGPL-3.0, Artifex): PDF text extraction and figure rendering.
- All page runtime code (SVG charts, controls, layout) was written for this project with the help of an AI coding assistant (Claude). It has no external JS/CSS libraries, CDNs or fonts.
- Practice excerpts are short quotations from Vaswani et al. (2017), *Attention Is All You Need*, and Shannon (1948), *A Mathematical Theory of Communication*.
