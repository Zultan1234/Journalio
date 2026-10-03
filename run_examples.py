#!/usr/bin/env python3
"""Run the agent on every example (or a chosen few) and summarize cost, speed and checks.

    python run_examples.py                          # all examples, default model
    python run_examples.py --only entropy adam      # just these
    python run_examples.py --jobs 3                 # 3 cases in parallel
    python run_examples.py --model deepseek/deepseek-v4.1-flash

Writes examples/<name>/out/{index.html,trace.jsonl}, examples/summary.md and a gallery examples/index.html.
"""
import argparse
import concurrent.futures as cf
import html
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
EX = os.path.join(ROOT, "examples")
DEFAULT_MODEL = os.environ.get("JOURNALIO_MODEL", "deepseek/deepseek-v4.1-flash")


def run_one(name, model):
    case = os.path.join(EX, name, "case.json")
    out = os.path.join(EX, name, "out")
    t0 = time.time()
    proc = subprocess.run([sys.executable, os.path.join(ROOT, "agent.py"), "--input", case, "--output", out, "--model", model],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    wall = time.time() - t0
    info = {"name": name, "exit": proc.returncode, "wall_s": round(wall, 1), "log": proc.stdout[-4000:] + proc.stderr[-2000:]}
    trace = os.path.join(out, "trace.jsonl")
    if os.path.exists(trace):
        with open(trace, encoding="utf-8") as f:
            events = [json.loads(l) for l in f if l.strip()]
        for e in events:
            if e.get("stage") == "end":
                info.update({k: e.get(k) for k in ("total_tokens", "prompt_tokens", "completion_tokens", "requests", "revisions", "validation_ok")})
            if e.get("stage") == "theme":
                info["theme"] = "%s/%s" % (e.get("motif"), e.get("style"))
            if e.get("stage") == "figures" and e.get("action") == "embed":
                info["figures"] = e.get("result")
            if e.get("stage") == "validate" and e.get("action") == "execute_spec":
                info["states"] = e.get("states")
    try:
        with open(os.path.join(out, "index.html"), encoding="utf-8") as f:
            page = f.read()
        s = page.find("<title>") + 7
        info["title"] = html.unescape(page[s:page.find("</title>", s)])
    except OSError:
        info["title"] = "(no page)"
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--only", nargs="*", help="example folder names")
    ap.add_argument("--jobs", type=int, default=1, help="cases to run in parallel")
    a = ap.parse_args()
    if not os.environ.get("OPENROUTER_API_KEY"):
        sys.exit("Set OPENROUTER_API_KEY first.")
    names = a.only or sorted(d for d in os.listdir(EX) if os.path.isfile(os.path.join(EX, d, "case.json")))
    print("Running %d example(s) with %s ...\n" % (len(names), a.model))
    results = []
    with cf.ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
        futs = {pool.submit(run_one, n, a.model): n for n in names}
        for fut in cf.as_completed(futs):
            r = fut.result()
            results.append(r)
            ok = "OK " if r["exit"] == 0 else "ERR"
            print("[%s] %-13s %5ss  tokens=%-6s req=%-2s repairs=%-2s checks_ok=%-5s %s" % (
                ok, r["name"], r["wall_s"], r.get("total_tokens"), r.get("requests"), r.get("revisions"), r.get("validation_ok"), r.get("title", "")))
            if r["exit"] != 0:
                print("      last log lines:\n      " + "\n      ".join(r["log"].strip().splitlines()[-6:]))
    results.sort(key=lambda r: r["name"])
    done = [r for r in results if r.get("total_tokens")]
    avg_t = sum(r["total_tokens"] for r in done) / max(1, len(done))
    avg_s = sum(r["wall_s"] for r in done) / max(1, len(done))

    rows = ["| example | exit | seconds | tokens (prompt+completion) | requests | repairs | checks pass | theme | paper figure |",
            "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        rows.append("| [%s](%s/out/index.html) | %s | %s | %s (%s+%s) | %s | %s | %s | %s | %s |" % (
            r["name"], r["name"], r["exit"], r["wall_s"], r.get("total_tokens"), r.get("prompt_tokens"), r.get("completion_tokens"),
            r.get("requests"), r.get("revisions"), r.get("validation_ok"), r.get("theme", ""), r.get("figures", "-")))
    summary = "# Example runs (%s)\n\nAverage: %.0f tokens, %.1f s per case.\n\n%s\n" % (a.model, avg_t, avg_s, "\n".join(rows))
    with open(os.path.join(EX, "summary.md"), "w", encoding="utf-8") as f:
        f.write(summary)

    cards = "".join(
        '<a class="c" href="%s/out/index.html"><b>%s</b><span>%s</span><small>%s tokens · %ss · %s</small></a>' % (
            html.escape(r["name"]), html.escape(r.get("title", "")), html.escape(r["name"]), r.get("total_tokens"), r["wall_s"],
            "checks pass" if r.get("validation_ok") else "see trace")
        for r in results if r["exit"] == 0)
    gallery = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
               "<title>Journalio examples</title><style>body{font:15px system-ui;margin:0;background:#f6f6f3;color:#1d1f24}"
               "main{max-width:980px;margin:auto;padding:24px 16px}.g{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}"
               ".c{display:flex;flex-direction:column;gap:4px;background:#fff;border:1px solid #ddd;border-radius:10px;padding:14px;color:inherit;text-decoration:none}"
               ".c:hover{border-color:#2f62c9}.c span{color:#666;font-size:.85rem}.c small{color:#2f62c9}"
               "@media(prefers-color-scheme:dark){body{background:#15171b;color:#e8e9ec}.c{background:#1e2127;border-color:#363a42}}</style>"
               "<main><h1>Journalio examples</h1><p>Generated by <code>run_examples.py</code> with %s. Average %.0f tokens and %.1f s per case.</p>"
               "<div class=g>%s</div></main>" % (html.escape(a.model), avg_t, avg_s, cards))
    with open(os.path.join(EX, "index.html"), "w", encoding="utf-8") as f:
        f.write(gallery)
    print("\nAverage %.0f tokens, %.1f s per case. Open examples/index.html for the gallery; details in examples/summary.md." % (avg_t, avg_s))
    sys.exit(0 if all(r["exit"] == 0 for r in results) else 1)


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    main()
