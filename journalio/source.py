"""Collects the source text. Primary: excerpt fields inside case.json (assessment has network only to OpenRouter).
Fallback (development only): fetch source_url with a short timeout."""
import html as htmllib
import io
import re

KNOWN = {"source_url", "focus", "audience"}
EXCERPT_KEYS = ("excerpt", "paper_excerpt", "source_excerpt", "text", "source_text", "paper_text", "context", "content", "passage")
MAX_CHARS = 14000

STOP = set("the a an of and or to in on for with by is are be as at from that this it its into using use show let learner learners their how what why which can should must about between".split())


def _strip_html(s):
    s = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?is)<math[^>]*alttext=\"([^\"]*)\"[^>]*>.*?</math>", r" \1 ", s)  # arXiv HTML keeps LaTeX in alttext
    s = re.sub(r"(?s)<(br|p|div|h\d|li|tr|section)[^>]*>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = htmllib.unescape(s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()


def _fetch(url, trace):
    try:
        import requests
        r = requests.get(url, timeout=8, headers={"User-Agent": "journalio/1.0"})
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if "pdf" in ctype or url.lower().endswith(".pdf"):
            try:
                from pypdf import PdfReader
                rd = PdfReader(io.BytesIO(r.content))
                txt = "\n".join((p.extract_text() or "") for p in rd.pages[:30])
            except Exception as e:
                trace.log("source", "pdf_parse", "failed: %s" % str(e)[:120])
                return ""
        else:
            txt = _strip_html(r.text)
        trace.log("source", "fetch_url", "ok", chars=len(txt))
        return txt
    except Exception as e:
        trace.log("source", "fetch_url", "unavailable (%s)" % type(e).__name__, detail=str(e)[:160])
        return ""


def select_relevant(text, focus, limit=MAX_CHARS):
    """Keep the paragraphs most related to the focus, in original order, within a char budget."""
    if len(text) <= limit:
        return text
    words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", focus.lower()) if w not in STOP]
    nums = re.findall(r"\b\d+(?:\.\d+)+\b|\b(?:section|sec\.?|eq\.?|equation)\s*\(?\d+", focus.lower())
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    scored = []
    for i, p in enumerate(paras):
        pl = p.lower()
        sc = sum(pl.count(w) for w in set(words))
        sc += 6 * sum(1 for n in nums if n in pl)
        sc = sc / (1 + len(p) / 1500.0)
        scored.append((sc, i))
    keep = set()
    total = 0
    for sc, i in sorted(scored, reverse=True):
        if sc <= 0 and keep:
            break
        if total + len(paras[i]) > limit:
            continue
        keep.add(i)
        total += len(paras[i])
        # include immediate neighbour for context when cheap
        if i + 1 < len(paras) and total + len(paras[i + 1]) < limit * 0.9 and sc > 1:
            keep.add(i + 1)
            total += len(paras[i + 1])
    return "\n\n".join(paras[i] for i in sorted(keep))


def gather(case, trace):
    excerpt = ""
    for k in EXCERPT_KEYS:
        v = case.get(k)
        if isinstance(v, str) and v.strip():
            excerpt = v.strip()
            trace.log("source", "read_excerpt", "field '%s'" % k, chars=len(excerpt))
            break
    # any other unknown string fields (e.g. title, section, id) are passed as context
    extra = {k: v for k, v in case.items() if isinstance(v, str) and k not in KNOWN and k not in EXCERPT_KEYS and len(v) < 2000}
    long_unknown = [k for k, v in case.items() if isinstance(v, str) and k not in KNOWN and k not in EXCERPT_KEYS and len(v) >= 2000]
    if not excerpt and long_unknown:
        excerpt = case[long_unknown[0]]
        trace.log("source", "read_excerpt", "field '%s'" % long_unknown[0], chars=len(excerpt))
    if len(excerpt) < 300 and case.get("source_url"):
        fetched = _fetch(case["source_url"], trace)
        if fetched:
            excerpt = (excerpt + "\n\n" + fetched).strip()
    before = len(excerpt)
    excerpt = select_relevant(excerpt, case.get("focus", ""))
    if len(excerpt) < before:
        trace.log("source", "select_relevant", "trimmed", chars_before=before, chars_after=len(excerpt))
    return excerpt, extra
