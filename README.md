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

`case.json` (UTF-8) needs `source_url`, `focus` and `audience`. An excerpt field (`excerpt`, `text`, `paper_excerpt`, `context`…) is used as the primary source when present. Any other short string fields (for example `title` or `section`) are passed to the model as context. If there's no excerpt, the agent tries to fetch `source_url`; it moves on without it if the network is blocked.

## Architecture

The model doesn't write a whole HTML page. It writes a compact **JSON spec** of the lab: the mechanism stages, the controls, a pure JavaScript `compute(inp)` function, the visual bindings, the explorations, source-tagged claims and invariant checks. A fixed, pre-tested runtime turns that spec into the page. This keeps the output small (fewer tokens, lower latency) and makes the result **executable and checkable**.

```
case.json
  │  source.py      excerpt from case (or fetched URL) → relevant-paragraph selection (≤14k chars)
  ▼
[LLM call 1]        prompts.SYSTEM: scope → evidence (PAPER/DERIVED/PLAYGROUND) → mechanism chain
  │                 → minimal executable model → controls/presets → invariants   ⇒ spec JSON
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
[LLM repair ≤2]     only the failing keys + validator messages are sent back; a JSON patch is merged
  ▼  still errors?
degrade             drop still-failing checks/views/readouts so the page stays correct and usable
  ▼
enrich              no-token visual enrichment: if no sweep view exists, add one for the slider that moves the
  │                 headline readouts most (chosen from measured effects); kept only if it validates
  ▼
render.py           template.html + core.js + runtime.js + spec → single offline index.html
```

**Runtime features (generic, in `journalio/assets/`).** The orientation cards answer *what / why / what can I change / what should I watch*, followed by a "try this first" box. A clickable mechanism map shows a **live mini-chart of each intermediate quantity inside each stage** and lets the learner inspect its exact values. Controls can be sliders, toggles, selects, vectors (with variable length) or editable matrices. The visuals are SVG bars; function curves with the current operating point(s) marked; **sweeps**, where the page re-runs the model across a slider's range and marks the current value; **stacked contributions** that add up to a total, with a theoretical maximum; heatmaps with row sums; scatter plots and vectors; contribution tables; and an optional canvas. Every slider has a **▶ animate** button that drives it across its range while all downstream stages update. A **"Why did this change?"** panel traces the chain control → changed stages → readout deltas, and the changed stages and views are highlighted. The page also includes two guided explorations with one-click presets and predict-then-reveal explanations, a limitation/misconception lab, source-grounding labels (PAPER / DERIVED / PLAYGROUND), live invariant checks and a summary of the build-time verification.

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
| `journalio/assets/core.js` | pure functions shared by the page and the validator |
| `journalio/assets/runtime.js`, `template.html` | generic page runtime and layout (no paper-specific content) |
| `examples/` | example inputs (and generated outputs) |

## Example

`examples/entropy/case.json` and `examples/attention/case.json` are practice inputs built from the two public examples. The generated pages and traces are in `examples/*/out/`. To regenerate one:

```bash
python agent.py --input examples/entropy/case.json --output examples/entropy/out --model deepseek/deepseek-v4.1-flash
```

## Credits and reuse

- [requests](https://pypi.org/project/requests/) (Apache-2.0): HTTP client.
- [mini-racer](https://pypi.org/project/mini-racer/) (ISC): embedded V8, used to execute and validate the generated JavaScript at build time.
- [pypdf](https://pypi.org/project/pypdf/) (BSD): optional PDF text extraction when no excerpt is given.
- All page runtime code (SVG charts, controls, layout) was written for this project with the help of an AI coding assistant (Claude). It has no external JS/CSS libraries, CDNs or fonts.
- Practice excerpts are short quotations from Vaswani et al. (2017), *Attention Is All You Need*, and Shannon (1948), *A Mathematical Theory of Communication*.
