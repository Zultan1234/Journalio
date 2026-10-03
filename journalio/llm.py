"""Minimal OpenRouter client with hard budget enforcement (requests, completion tokens, wall time)."""
import json
import os
import re
import time

import requests

URL = os.environ.get("JOURNALIO_API_URL", "https://openrouter.ai/api/v1/chat/completions")  # override only for offline tests
MAX_REQUESTS = 10
MAX_COMPLETION_TOKENS = 30000
DEADLINE_S = 570  # hard limit is 600 s; keep a safety margin


class BudgetError(RuntimeError):
    pass


class LLM:
    def __init__(self, model, trace, t_start):
        self.model = model
        self.trace = trace
        self.t_start = t_start
        self.key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        self.requests = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.reasoning_param = True  # try to disable hidden reasoning (saves tokens); dropped if provider rejects it

    def remaining_completion(self):
        return MAX_COMPLETION_TOKENS - self.completion_tokens

    def time_left(self):
        return DEADLINE_S - (time.time() - self.t_start)

    def chat(self, messages, max_tokens, purpose, json_mode=True, temperature=0.3):
        if not self.key:
            raise BudgetError("OPENROUTER_API_KEY is not set")
        last_err = None
        for attempt in range(3):
            if self.requests >= MAX_REQUESTS:
                raise BudgetError("request budget exhausted")
            max_tokens = min(max_tokens, self.remaining_completion() - 200)
            if max_tokens < 800:
                raise BudgetError("completion-token budget exhausted")
            tl = self.time_left()
            if tl < 25:
                raise BudgetError("time budget exhausted")
            body = {"model": self.model, "messages": messages, "max_tokens": max_tokens,
                    "temperature": temperature, "usage": {"include": True}}
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            effort = os.environ.get("JOURNALIO_REASONING", "off").lower()
            if self.reasoning_param:
                body["reasoning"] = {"enabled": False} if effort == "off" else {"effort": effort, "exclude": True}
            self.requests += 1
            t0 = time.time()
            try:
                r = requests.post(URL, headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json",
                                                "X-Title": "Journalio Paper-to-Playground"},
                                  data=json.dumps(body), timeout=max(20, min(300, tl - 10)))
                dt = round(time.time() - t0, 2)
                if r.status_code != 200:
                    txt = r.text[:300]
                    self.trace.log("llm", "call_failed", "HTTP %d" % r.status_code, purpose=purpose, attempt=attempt + 1,
                                   elapsed_s=dt, detail=txt, request_no=self.requests)
                    last_err = "HTTP %d: %s" % (r.status_code, txt)
                    if r.status_code == 400 and (self.reasoning_param or json_mode):
                        # some providers reject optional params: drop them and retry
                        if self.reasoning_param:
                            self.reasoning_param = False
                        else:
                            json_mode = False
                        continue
                    if r.status_code in (401, 402, 403):
                        break
                    time.sleep(min(2 * (attempt + 1), 6))
                    continue
                data = r.json()
            except (requests.RequestException, ValueError) as e:
                dt = round(time.time() - t0, 2)
                last_err = str(e)[:300]
                self.trace.log("llm", "call_failed", "exception", purpose=purpose, attempt=attempt + 1, elapsed_s=dt,
                               detail=last_err, request_no=self.requests)
                time.sleep(2)
                continue
            if "error" in data and not data.get("choices"):
                last_err = str(data["error"])[:300]
                self.trace.log("llm", "call_failed", "api error", purpose=purpose, detail=last_err, elapsed_s=dt,
                               request_no=self.requests)
                continue
            usage = data.get("usage") or {}
            pt = int(usage.get("prompt_tokens") or 0)
            ct = int(usage.get("completion_tokens") or 0)
            self.prompt_tokens += pt
            self.completion_tokens += ct
            choice = (data.get("choices") or [{}])[0]
            content = (choice.get("message") or {}).get("content") or ""
            details = usage.get("completion_tokens_details") or {}
            self.trace.log("llm", "call", "ok", purpose=purpose, model=data.get("model", self.model),
                           generation_id=data.get("id"), request_no=self.requests,
                           prompt_tokens=pt, completion_tokens=ct,
                           reasoning_tokens=details.get("reasoning_tokens"),
                           cached_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
                           cost=usage.get("cost"), total_tokens=pt + ct, finish_reason=choice.get("finish_reason"),
                           elapsed_s=dt, response_chars=len(content),
                           cumulative_tokens=self.prompt_tokens + self.completion_tokens)
            return content, choice.get("finish_reason")
        raise RuntimeError("LLM call failed: %s" % last_err)


def parse_json(text):
    """Tolerant JSON extraction (code fences, leading prose, trailing commas)."""
    if not text:
        raise ValueError("empty response")
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```\s*$", "", t)
    try:
        return json.loads(t)
    except ValueError:
        pass
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("no JSON object found")
    s = t[i:j + 1]
    try:
        return json.loads(s)
    except ValueError:
        s2 = re.sub(r",\s*([}\]])", r"\1", s)
        return json.loads(s2)
