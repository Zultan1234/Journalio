"""Paper figures for the page, extracted from the paper's PDF itself (see pdffigs.py). 0 tokens.

PDF sources, in order:
  1. a local PDF: case.json field "pdf" (path relative to case.json), or a PDF file next to case.json
  2. the source URL: direct PDF links, arXiv (abs/html -> pdf), IEEE Xplore stamp pages (resolves the
     embedded PDF; needs a network/IP with IEEE access), DOI links that redirect to a PDF.
Runs in a background thread while the LLM call is in flight, so it adds no latency. If no PDF can be
obtained (e.g. network limited to OpenRouter during assessment) it fails fast and the page relies on
its live charts and theme illustration.
"""
import glob
import os
import re
import threading
import time
from urllib.parse import urljoin

from . import pdffigs

DEADLINE_S = 20
MAX_PDF_BYTES = 40_000_000
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) journalio/1.0", "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8"}

_cache = {}


def local_pdf(case, case_dir):
    cands = []
    if case.get("pdf"):
        cands.append(case["pdf"] if os.path.isabs(case["pdf"]) else os.path.join(case_dir or ".", case["pdf"]))
    url = case.get("source_url", "")
    if url.lower().endswith(".pdf") and not url.lower().startswith("http"):
        cands.append(url[7:] if url.startswith("file://") else url)
    if case_dir:
        cands += sorted(glob.glob(os.path.join(case_dir, "*.pdf")))
    for p in cands:
        if os.path.isfile(p):
            return p
    return None


def _pdf_urls(url):
    m = re.search(r"arxiv\.org/(?:abs|pdf|html)/([0-9]{4}\.[0-9]{4,5}|[a-z\-]+/[0-9]{7})(v[0-9]+)?", url or "")
    if m:
        return ["https://arxiv.org/pdf/%s%s" % (m.group(1), m.group(2) or "")]
    m = re.search(r"ieeexplore\.ieee\.org/.*?arnumber=(\d+)", url or "") or re.search(r"ieeexplore\.ieee\.org/document/(\d+)", url or "")
    if m:
        a = m.group(1)
        return [url, "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=%s" % a,
                "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=%s" % a]
    return [url] if url.startswith("http") else []


def fetch_pdf(url, trace, deadline):
    """Download a PDF, following one level of HTML wrapper (iframe/embed/meta citation_pdf_url)."""
    import requests
    sess = requests.Session()
    tried = set()
    queue = _pdf_urls(url)
    while queue and time.time() < deadline:
        u = queue.pop(0)
        if u in tried:
            continue
        tried.add(u)
        try:
            r = sess.get(u, headers=UA, timeout=(3, max(2, min(10, deadline - time.time()))), allow_redirects=True)
        except Exception as e:
            trace.log("figures", "pdf_download", "failed (%s)" % type(e).__name__, url=u)
            continue
        body = r.content[:MAX_PDF_BYTES]
        if body[:5] == b"%PDF-":
            trace.log("figures", "pdf_download", "ok", url=u, bytes=len(body))
            return body
        if r.status_code == 200 and b"<" in body[:2000]:
            html = body.decode("utf-8", "replace")
            for pat in (r'<iframe[^>]+src="([^"]+)"', r'<embed[^>]+src="([^"]+)"', r'citation_pdf_url"\s+content="([^"]+)"',
                        r'"(https?://[^"]+\.pdf[^"]*)"', r'"(/stampPDF/getPDF\.jsp[^"]*)"'):
                for m in re.findall(pat, html, re.I):
                    queue.append(urljoin(r.url, m.replace("&amp;", "&")))
        trace.log("figures", "pdf_download", "no PDF at this URL (HTTP %d)" % r.status_code, url=u)
    return None


def get_pdf(case, case_dir, trace, deadline):
    key = (case.get("source_url"), case.get("pdf"), case_dir)
    if key in _cache:
        return _cache[key]
    data, origin = None, None
    p = local_pdf(case, case_dir)
    if p:
        with open(p, "rb") as f:
            data = f.read()
        origin = os.path.basename(p)
        trace.log("figures", "pdf_local", "ok", file=origin, bytes=len(data))
    elif case.get("source_url", "").startswith("http"):
        data = fetch_pdf(case["source_url"], trace, deadline)
        origin = case["source_url"]
    _cache[key] = (data, origin)
    return data, origin


class FigureFetcher:
    def __init__(self, case, excerpt, trace, case_dir=None):
        self.case, self.excerpt, self.trace, self.case_dir = case, excerpt, trace, case_dir
        self.result = []
        self.t0 = time.time()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def _run(self):
        if not pdffigs.available():
            self.trace.log("figures", "skip", "PyMuPDF not installed")
            return
        try:
            data, origin = get_pdf(self.case, self.case_dir, self.trace, self.t0 + DEADLINE_S)
            if not data:
                self.trace.log("figures", "skip", "no PDF available (offline or access-restricted)")
                return
            figs, found = pdffigs.extract(data, self.case.get("focus", ""), self.excerpt)
            for f in figs:
                f["url"] = origin
            self.result = figs
            self.trace.log("figures", "extract_from_pdf", "%d of %d captioned figure(s) embedded" % (len(figs), len(found)),
                           found=found, embedded=[{"label": f["label"], "page": f["page"], "bytes": f["bytes"]} for f in figs])
        except Exception as e:
            self.trace.log("figures", "extract_from_pdf", "failed (%s: %s)" % (type(e).__name__, str(e)[:120]))

    def collect(self, wait=1.5):
        self.thread.join(timeout=max(0.0, wait))
        if self.thread.is_alive():
            self.trace.log("figures", "collect", "not ready, skipped")
            return []
        return self.result
