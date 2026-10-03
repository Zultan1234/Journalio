"""Source text for the model, extracted from case.json's source_url as cheaply as possible.

case.json needs only three fields: source_url, focus, audience.
  1. Fetch the source once (shared with the figure extractor): arXiv -> its HTML version (sectioned, equations kept as
     LaTeX), PDFs (direct, IEEE Xplore stamp pages, DOI redirects, or a PDF saved next to case.json) -> PyMuPDF text,
     other pages -> stripped HTML. Hard time budget; never blocks the run.
  2. Send the model only what it needs: the paper's title/author line plus the SECTION the brief names
     ("Section 3.2.1", "Sec. 6", "Section II"). If no section is named or found, keep the paragraphs that best match
     the brief, within a small character budget (no LLM call is spent on extraction).
  If the source cannot be reached (e.g. network limited to OpenRouter), the model works from the brief alone and is
  told so. An "excerpt" field, if a case happens to include one, is used instead of downloading (optional).
"""
import html as htmllib
import re
import threading
import time

KNOWN = {"source_url", "focus", "audience", "pdf"}
OPTIONAL_EXCERPT_KEYS = ("excerpt", "paper_excerpt", "source_excerpt", "source_text", "text", "passage", "context")
SECTION_BUDGET = 7000      # chars of the named section (~1.8k tokens)
KEYWORD_BUDGET = 6000      # chars when falling back to keyword-matched paragraphs
HEADER_CHARS = 300         # title / authors line
FETCH_BUDGET_S = 12

STOP = set("the a an of and or to in on for with by is are be as at from that this it its into using use show let learner "
           "learners their how what why which can should must about between explain small each two one".split())
ROMAN = r"(?:X{0,3}(?:IX|IV|V?I{0,3}))"


def _strip_html(s):
    s = re.sub(r"(?is)<(script|style|nav|header|footer|noscript|head)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?is)<math[^>]*alttext=\"([^\"]*)\"[^>]*>.*?</math>", r" \1 ", s)  # arXiv HTML keeps LaTeX in alttext
    s = re.sub(r"(?is)<(h[1-6])[^>]*>(.*?)</\1>", lambda m: "\n\n" + re.sub(r"<[^>]+>", " ", m.group(2)) + "\n\n", s)
    s = re.sub(r"(?s)<(br|p|div|li|tr|section|figcaption)[^>]*>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = htmllib.unescape(s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _arxiv_html(url):
    m = re.search(r"arxiv\.org/(?:abs|pdf|html)/([0-9]{4}\.[0-9]{4,5}|[a-z\-]+/[0-9]{7})(v[0-9]+)?", url or "")
    return "https://arxiv.org/html/%s%s" % (m.group(1), m.group(2) or "") if m else None


def fetch_text(case, case_dir, trace, budget=FETCH_BUDGET_S):
    """Return (text, kind). Runs under a hard time budget in a worker thread."""
    out = {"text": "", "kind": "none"}

    def work():
        import requests
        from . import figures, pdffigs
        deadline = time.time() + budget - 1
        url = case.get("source_url", "")
        a = _arxiv_html(url)
        if a:  # arXiv HTML: sectioned, equations as LaTeX
            try:
                r = requests.get(a, timeout=(3, 8), headers=figures.UA)
                if r.status_code == 200 and "<html" in r.text[:2000].lower():
                    out.update(text=_strip_html(r.text), kind="arxiv-html")
                    return
            except Exception as e:
                trace.log("source", "fetch_html", "failed (%s)" % type(e).__name__, url=a)
        if pdffigs.available():  # PDFs: local file next to case.json, direct link, IEEE stamp, DOI redirect
            data, origin = figures.get_pdf(case, case_dir, trace, deadline)
            if data:
                out.update(text=pdffigs.text_of(pdffigs.open_pdf(data)), kind="pdf")
                return
        if url.startswith("http") and time.time() < deadline:  # any other web page
            try:
                r = requests.get(url, timeout=(3, max(2, deadline - time.time())), headers=figures.UA)
                if r.status_code == 200 and "html" in r.headers.get("content-type", ""):
                    out.update(text=_strip_html(r.text), kind="html")
            except Exception as e:
                trace.log("source", "fetch_html", "failed (%s)" % type(e).__name__, url=url)

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(budget)
    if t.is_alive():
        trace.log("source", "fetch", "time budget exceeded (%ss)" % budget)
        return "", "timeout"
    return out["text"], out["kind"]


# ------------------------------------------------------------------ section-targeted extraction
def section_refs(focus):
    refs = re.findall(r"(?:section|sec\.?|§)\s*(\d+(?:\.\d+)*|" + ROMAN + r")\b", focus, re.I)
    return [r for r in refs if r]


def _heading_num(line):
    """'3.2.1 Scaled Dot-Product Attention' -> '3.2.1'; '6. CHOICE, UNCERTAINTY' -> '6'; 'II. THEORY' -> 'II'."""
    line = line.strip()
    if not (4 <= len(line) <= 110):
        return None
    m = re.match(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+([A-Z][^\n]{2,})$", line)
    if m and not (len(m.group(2)) > 60 and m.group(2).rstrip().endswith(".")):  # a heading, not a numbered sentence
        return m.group(1)
    m = re.match(r"^(" + ROMAN + r")\.\s+([A-Z][^\n]{2,})$", line)
    if m and m.group(1):
        return m.group(1).upper()
    return None


def find_section(text, ref):
    """Text of section `ref` up to the next heading that is not one of its subsections."""
    lines = text.split("\n")
    start = None
    for i, ln in enumerate(lines):
        if _heading_num(ln) == (ref if ref[0].isdigit() else ref.upper()):
            start = i
            break
    if start is None:
        return ""
    is_roman = not ref[0].isdigit()
    end = len(lines)
    for j in range(start + 1, len(lines)):
        n = _heading_num(lines[j])
        if not n:
            continue
        if is_roman:
            if not n[0].isdigit():
                end = j
                break
        elif n[0].isdigit() and not n.startswith(ref + "."):
            end = j
            break
    return "\n".join(lines[start:end]).strip()


def select_relevant(text, focus, limit=KEYWORD_BUDGET):
    """Fallback: keep the paragraphs most related to the brief, in original order, within a char budget."""
    if len(text) <= limit:
        return text
    words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", focus.lower()) if w not in STOP]
    anchors = re.findall(r"\b(?:theorem|algorithm|eq\.?|equation|fig\.?|figure|table)\s*\(?\d+", focus.lower())
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    scored = []
    for i, p in enumerate(paras):
        pl = p.lower()
        sc = sum(pl.count(w) for w in set(words)) + 6 * sum(1 for a in anchors if a in pl)
        scored.append((sc / (1 + len(p) / 1500.0), i))
    keep, total = set(), 0
    for sc, i in sorted(scored, reverse=True):
        if sc <= 0 and keep:
            break
        if total + len(paras[i]) > limit:
            continue
        keep.add(i)
        total += len(paras[i])
    return "\n\n".join(paras[i] for i in sorted(keep))


def _header(text):
    """Title/author lines: everything before the first section heading (capped)."""
    out = []
    for ln in text.split("\n")[:40]:
        if _heading_num(ln):
            break
        if ln.strip():
            out.append(ln.strip())
    h = re.sub(r"\s+", " ", " ".join(out)).strip()
    return h[:HEADER_CHARS]


def _parent_lead(text, ref, limit=900):
    """For a subsection like 3.2.1, the short lead-in of its parent (3.2) before the first child heading."""
    if "." not in ref:
        return ""
    parent = ref.rsplit(".", 1)[0]
    sec = find_section(text, parent)
    if not sec:
        return ""
    lines = sec.split("\n")
    lead = [lines[0]]
    for ln in lines[1:]:
        if _heading_num(ln):
            break
        lead.append(ln)
    lead = "\n".join(lead).strip()
    return lead if len(lead) <= limit else ""


def condense(text, focus, trace):
    """Title line + the named section (with its parent's lead-in), or the best-matching paragraphs."""
    header = _header(text)
    parts, used = [], []
    for ref in dict.fromkeys(section_refs(focus)):  # every named section, in brief order, no duplicates
        if any(ref.startswith(u + ".") for u in used):
            continue  # already inside a parent section we took
        sec = find_section(text, ref)
        if len(sec) >= 200:
            lead = _parent_lead(text, ref)
            parts.append(((lead + "\n\n") if lead else "") + sec)
            used.append(ref)
    if parts:
        body = "\n\n".join(parts)[:SECTION_BUDGET]
        trace.log("source", "extract_section", "Section(s) %s" % ", ".join(used), chars_doc=len(text), chars_sent=len(body))
        return "[Paper] " + header + "\n\n" + body
    body = select_relevant(text, focus)
    trace.log("source", "extract_keywords", "no named section found: best-matching paragraphs", chars_doc=len(text), chars_sent=len(body))
    return "[Paper] " + header + "\n\n" + body


def gather(case, trace, case_dir=None):
    """Return (source_text, extra_fields). Uses only source_url/focus/audience."""
    focus = case.get("focus", "")
    for k in OPTIONAL_EXCERPT_KEYS:  # optional: a supplied excerpt avoids any download
        v = case.get(k)
        if isinstance(v, str) and len(v.strip()) >= 200:
            trace.log("source", "excerpt_field", "using optional field '%s' (no download needed)" % k, chars=len(v))
            return (v.strip() if len(v) <= SECTION_BUDGET + KEYWORD_BUDGET else condense(v, focus, trace)), {}
    text, kind = fetch_text(case, case_dir, trace)
    if not text.strip():
        trace.log("source", "fetch", "source unavailable: the model will work from the brief alone", kind=kind)
        return "", {}
    trace.log("source", "fetch", "ok", kind=kind, chars=len(text))
    return condense(text, focus, trace), {}
