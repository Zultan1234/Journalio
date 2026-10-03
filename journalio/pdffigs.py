"""Figures (plots, diagrams, photos) and text extracted from the paper's PDF itself.

Cheap and model-free: PyMuPDF reads the PDF's text layer to locate captions ("Fig. 3.", "Figure 2:"),
infers the figure region next to each caption (works for born-digital PDFs with vector plots, embedded
images, and scanned papers with an OCR text layer), renders just that region to a compressed JPEG and
embeds it as a data URI. Relevance to the brief picks which figures to show. 0 tokens.
"""
import base64
import re

try:
    import pymupdf  # PyMuPDF >= 1.24
except ImportError:  # pragma: no cover
    try:
        import fitz as pymupdf  # older name
    except ImportError:
        pymupdf = None

CAPTION_RE = re.compile(r"^\s*(fig(?:ure)?\.?|FIG\.?)\s*(\d+)\s*[.:\-—–]?\s*", re.I)
STOP = set("the a an of and or to in on for with by is are be as at from that this it its into using use show let learner "
           "learners their how what why which can should must about between explain small each two one see".split())
MAX_W_PX = 1100
JPEG_Q = 72


def available():
    return pymupdf is not None


def open_pdf(data):
    return pymupdf.open(stream=data, filetype="pdf")


def text_of(doc, max_pages=40):
    return "\n\n".join(doc[i].get_text("text") for i in range(min(len(doc), max_pages)))


def _blocks(page):
    out = []
    for b in page.get_text("blocks"):
        x0, y0, x1, y1, txt, _no, btype = b[:7]
        if btype == 0 and txt.strip():
            out.append((pymupdf.Rect(x0, y0, x1, y1), " ".join(txt.split())))
    return out


def _ink_bbox(page, rect, zoom=1.0, thresh=215):
    """Tight box around non-white pixels inside rect (works for vector, raster and scanned pages)."""
    if rect.is_empty or rect.width < 5 or rect.height < 5:
        return None
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=rect, colorspace=pymupdf.csGRAY, alpha=False)
    w, h, buf, stride = pix.width, pix.height, pix.samples, pix.stride
    rows = [sum(1 for x in range(0, w, 2) if buf[y * stride + x] < thresh) for y in range(h)]
    if not any(rows):
        return None
    cols = [0] * w
    for y in range(0, h, 2):
        off = y * stride
        for x in range(w):
            if buf[off + x] < thresh:
                cols[x] += 1
    noise_r, noise_c = max(1, w // 400), max(1, h // 400)
    ys = [y for y, c in enumerate(rows) if c > noise_r]
    xs = [x for x, c in enumerate(cols) if c > noise_c]
    if not ys or not xs:
        return None
    return pymupdf.Rect(rect.x0 + xs[0] / zoom, rect.y0 + ys[0] / zoom, rect.x0 + (xs[-1] + 1) / zoom, rect.y0 + (ys[-1] + 1) / zoom)


def _region(page, cap_rect, blocks, below=False):
    """Figure area next to the caption: bounded vertically by the nearest paragraph that overlaps the caption's
    span, horizontally by page margins and by paragraphs running alongside (other column), then tightened
    to the actual ink."""
    W, H = page.rect.width, page.rect.height
    paras = [r for r, t in blocks if r != cap_rect and len(t) > 60]  # body text, not axis labels
    span = [r for r in paras if min(r.x1, cap_rect.x1) - max(r.x0, cap_rect.x0) > 10]
    if not below:
        top = max([r.y1 for r in span if r.y1 <= cap_rect.y0 + 2] + [H * 0.04])
        y0, y1 = top + 2, cap_rect.y0 - 1
    else:
        bot = min([r.y0 for r in span if r.y0 >= cap_rect.y1 - 2] + [H * 0.96])
        y0, y1 = cap_rect.y1 + 1, bot - 2
    if y1 - y0 < 30:
        return pymupdf.Rect(0, 0, 0, 0)
    cx = (cap_rect.x0 + cap_rect.x1) / 2
    x_lo, x_hi = W * 0.04, W * 0.96
    for r in paras:  # paragraphs alongside the band act as walls
        ov = min(r.y1, y1) - max(r.y0, y0)
        if ov > 0.4 * (y1 - y0):
            if r.x0 >= cx:
                x_hi = min(x_hi, r.x0 - 3)
            elif r.x1 <= cx:
                x_lo = max(x_lo, r.x1 + 3)
    band = pymupdf.Rect(x_lo, y0, x_hi, y1)
    ink = _ink_bbox(page, band)
    if ink is None:
        return pymupdf.Rect(0, 0, 0, 0)
    pad = 5
    return pymupdf.Rect(ink.x0 - pad, ink.y0 - pad, ink.x1 + pad, ink.y1 + pad) & page.rect


def find_figures(doc, max_pages=30):
    """All captioned figures: [{page, num, caption, rect}]."""
    figs, seen = [], set()
    for pno in range(min(len(doc), max_pages)):
        page = doc[pno]
        blocks = _blocks(page)
        for rect, txt in blocks:
            m = CAPTION_RE.match(txt)
            if not m or len(txt) > 700:
                continue
            num = m.group(2)
            if num in seen:  # in-text mention like "Fig. 2 shows" appears before; keep the first caption-like block
                continue
            # captions are short-ish and usually start the block; skip running text "Fig. 3 shows that ..."
            if re.match(r"^\s*fig(?:ure)?\.?\s*\d+\s+(shows|illustrates|depicts|gives|is|presents)\b", txt, re.I):
                continue
            reg = _region(page, rect, blocks)
            if reg.height < 60:
                reg = _region(page, rect, blocks, below=True)
            if reg.height < 60 or reg.width < 80:
                continue
            seen.add(num)
            figs.append({"page": pno, "num": num, "caption": CAPTION_RE.sub("", txt, count=1).strip(), "rect": reg})
    return figs


def score(fig, focus, excerpt):
    want = set(re.findall(r"\b(?:fig(?:ure)?\.?)\s*(\d+)", (focus + " " + excerpt).lower()))
    words = {w for w in re.findall(r"[a-z][a-z0-9\-]{2,}", focus.lower()) if w not in STOP}
    cap = fig["caption"].lower()
    s = 10 if fig["num"] in want else 0
    s += sum(1 for w in words if w in cap)
    return s


def render(doc, fig):
    page = doc[fig["page"]]
    zoom = min(3.0, MAX_W_PX / max(fig["rect"].width, 1))
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=fig["rect"], alpha=False)
    try:
        data = pix.tobytes("jpg", jpg_quality=JPEG_Q)
        mime = "image/jpeg"
    except Exception:
        data = pix.tobytes("png")
        mime = "image/png"
    return "data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii")), len(data)


def extract(pdf_bytes, focus, excerpt, max_figs=2, min_score=2):
    """Return (figures for the page, all captions found)."""
    doc = open_pdf(pdf_bytes)
    figs = find_figures(doc)
    for f in figs:
        f["score"] = score(f, focus, excerpt)
    ranked = sorted(figs, key=lambda f: (-f["score"], f["page"]))
    chosen = [f for f in ranked if f["score"] >= min_score][:max_figs]
    out = []
    for f in sorted(chosen, key=lambda f: int(f["num"])):
        uri, nbytes = render(doc, f)
        out.append({"data": uri, "label": "Fig. %s" % f["num"], "caption": f["caption"][:300],
                    "page": f["page"] + 1, "bytes": nbytes, "score": f["score"], "source": "pdf"})
    found = [{"label": "Fig. %s" % f["num"], "page": f["page"] + 1, "score": f["score"]} for f in figs]
    return out, found
