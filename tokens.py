#!/usr/bin/env python3
"""Token usage per run, read from trace.jsonl (no API calls).

    python tokens.py                                   # every examples/*/out/trace.jsonl
    python tokens.py examples/adam/out                 # one run (folder or trace.jsonl path)
    python tokens.py out --calls                       # also list each API call
"""
import glob
import json
import os
import sys


def load(path):
    if os.path.isdir(path):
        path = os.path.join(path, "trace.jsonl")
    with open(path, encoding="utf-8") as f:
        return path, [json.loads(l) for l in f if l.strip()]


def summarize(events):
    calls = [e for e in events if e.get("stage") == "llm" and e.get("action") == "call"]
    failed = [e for e in events if e.get("stage") == "llm" and e.get("action") == "call_failed"]
    end = next((e for e in events if e.get("stage") == "end"), {})
    p = sum(c.get("prompt_tokens") or 0 for c in calls)
    c_ = sum(c.get("completion_tokens") or 0 for c in calls)
    return {"calls": calls, "failed": len(failed), "prompt": p, "completion": c_, "total": p + c_,
            "reasoning": sum(c.get("reasoning_tokens") or 0 for c in calls),
            "cost": sum(c.get("cost") or 0 for c in calls),
            "seconds": end.get("elapsed_s"), "ok": end.get("validation_ok"), "repairs": end.get("revisions")}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show_calls = "--calls" in sys.argv
    paths = args or sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples", "*", "out", "trace.jsonl")))
    if not paths:
        sys.exit("No trace.jsonl found. Run the agent first, or pass an output folder.")
    rows, grand = [], {"prompt": 0, "completion": 0, "total": 0, "cost": 0.0}
    print("%-34s %8s %8s %8s %5s %7s %8s %9s" % ("run", "prompt", "complet.", "TOTAL", "calls", "repairs", "seconds", "cost($)"))
    print("-" * 94)
    for p in paths:
        try:
            path, ev = load(p)
        except (OSError, ValueError) as e:
            print("%-34s  (unreadable: %s)" % (p, e))
            continue
        s = summarize(ev)
        name = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(path)))) + "/" + os.path.basename(os.path.dirname(os.path.abspath(path)))
        print("%-34s %8d %8d %8d %5d %7s %8s %9.5f" % (name[-34:], s["prompt"], s["completion"], s["total"], len(s["calls"]),
                                                    s["repairs"], s["seconds"], s["cost"]))
        if show_calls:
            for c in s["calls"]:
                print("    #%-2s %-16s prompt=%-6s completion=%-6s reasoning=%-5s %5ss  finish=%s" % (
                    c.get("request_no"), c.get("purpose"), c.get("prompt_tokens"), c.get("completion_tokens"),
                    c.get("reasoning_tokens") or 0, c.get("elapsed_s"), c.get("finish_reason")))
            if s["failed"]:
                print("    (+%d failed request(s) with no tokens)" % s["failed"])
        rows.append(s)
        for k in grand:
            grand[k] += s[k]
    if len(rows) > 1:
        n = len(rows)
        print("-" * 94)
        print("%-34s %8d %8d %8d %5s %7s %8s %9.5f" % ("TOTAL (%d runs)" % n, grand["prompt"], grand["completion"], grand["total"], "", "", "", grand["cost"]))
        print("%-34s %8d %8d %8d" % ("AVERAGE per run", grand["prompt"] / n, grand["completion"] / n, grand["total"] / n))


if __name__ == "__main__":
    main()
