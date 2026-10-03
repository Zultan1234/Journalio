"""Best-effort retrieval of the paper's OWN figure(s) relevant to the brief, embedded as data URIs.

Runs in a background thread while the LLM call is in flight (zero added latency, zero tokens).
Works when the paper's HTML is reachable (e.g. arXiv HTML); if the network is restricted it fails
fast and the page simply relies on its live charts and the theme illustration."""
import base64
import html as htmllib
import re
import threading
import time
from urllib.parse import urljoin

MAX_IMG_BYTES = 700_000
MAX_FIGS = 2
DEADLINE_S = 14
STOP = set("the a an of and or to in on for with by is are be as at from that this it its into using use show let learner "
           "learners their how what why which can should must about between explain small each two one".split())


def _arxiv_html(url):
    m = re.search(r"arxiv\.org/(?:abs|pdf|html)/([0-9]{4}\.[0-9]{4,5}|[a-z\-]+/[0-9]{7})(v[0-9]+)?", url or "")
    if not m:
        return None
    return "https://arxiv.org/html/%s%s" % (m.group(1), m.group(2) or "")


def _text(s):
    s = re.sub(r"(?s)<math[^>]*alttext=\"([^\"]*)\"[^>]*>.*?</math>", r" \1 ", s)
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"(?s)<[^>]+>", " ", s))).strip()


def find_figures(page_html, page_url, focus, excerpt):
    """Return candidate figures [{src, caption, label, score}] sorted by relevance."""
    want_nums = set(re.findall(r"\b(?:fig(?:ure)?\.?)\s*(\d+)", (focus + " " + excerpt).lower()))
    words = {w for w in re.findall(r"[a-z][a-z0-9\-]{2,}", focus.lower()) if w not in STOP}
    cands = []
    for blk in re.findall(r"(?is)<figure\b[^>]*>(.*?)</figure>", page_html):
        imgs = re.findall(r"(?is)<img\b[^>]*\bsrc=\"([^\"]+)\"", blk)
        if not imgs:
            continue
        cap_m = re.search(r"(?is)<figcaption\b[^>]*>(.*?)</figcaption>", blk)
        cap = _text(cap_m.group(1)) if cap_m else ""
        num_m = re.search(r"(?i)\b(?:figure|fig\.?)\s*(\d+)", cap)
        num = num_m.group(1) if num_m else None
        capl = cap.lower()
        score = 10 if num and num in want_nums else 0
        score += sum(1 for w in words if w in capl)
        cap_short = re.sub(r"(?i)^\s*(?:figure|fig\.?)\s*\d+\s*[:.]\s*", "", cap)
        cands.append({"src": urljoin(page_url, imgs[0]), "caption": cap_short[:260], "label": ("Figure " + num) if num else "Figure", "score": score})
    cands.sort(key=lambda c: -c["score"])
    return [c for c in cands if c["score"] >= 3][:MAX_FIGS]


class FigureFetcher:
    def __init__(self, case, excerpt, trace):
        self.case, self.excerpt, self.trace = case, excerpt, trace
        self.result = []
        self.t0 = time.time()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def _left(self):
        return DEADLINE_S - (time.time() - self.t0)

    def _run(self):
        try:
            import requests
        except ImportError:
            return
        url = self.case.get("source_url", "")
        page_url = _arxiv_html(url) or (url if url.startswith("http") and not url.lower().endswith(".pdf") else None)
        if not page_url:
            self.trace.log("figures", "skip", "no HTML version of the source (e.g. PDF only)")
            return
        try:
            r = requests.get(page_url, timeout=(2.5, 6), headers={"User-Agent": "journalio/1.0"})
            r.raise_for_status()
            cands = find_figures(r.text, r.url, self.case.get("focus", ""), self.excerpt)
            self.trace.log("figures", "scan_page", "%d relevant figure(s)" % len(cands), page=page_url,
                           candidates=[{"label": c["label"], "score": c["score"]} for c in cands])
            out = []
            for c in cands:
                if self._left() < 2:
                    break
                im = requests.get(c["src"], timeout=(2.5, min(6, self._left())), headers={"User-Agent": "journalio/1.0"})
                ctype = im.headers.get("content-type", "").split(";")[0].strip()
                if im.status_code != 200 or not ctype.startswith("image/") or len(im.content) > MAX_IMG_BYTES:
                    continue
                out.append({"data": "data:%s;base64,%s" % (ctype, base64.b64encode(im.content).decode("ascii")),
                            "caption": c["caption"], "label": c["label"], "url": page_url})
            self.result = out
            self.trace.log("figures", "embed", "%d figure(s)" % len(out), bytes=sum(len(f["data"]) for f in out))
        except Exception as e:
            self.trace.log("figures", "fetch", "unavailable (%s)" % type(e).__name__)

    def collect(self, wait=1.0):
        self.thread.join(timeout=max(0.0, wait))
        if self.thread.is_alive():
            self.trace.log("figures", "collect", "not ready, skipped")
            return []
        return self.result
