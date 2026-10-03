"""trace.jsonl writer: one JSON object per event (stage, action, result, ...). Never logs credentials."""
import json
import time


class Trace:
    def __init__(self, path):
        self.path = path
        self.t0 = time.time()
        self.f = open(path, "w", encoding="utf-8")

    def log(self, stage, action, result, **extra):
        ev = {"t": round(time.time() - self.t0, 3), "stage": stage, "action": action, "result": result}
        ev.update(extra)
        self.f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        self.f.flush()
        print("[%6.1fs] %-10s %-22s %s" % (ev["t"], stage, action, str(result)[:110]), flush=True)

    def close(self):
        self.f.close()
