"""Extract article blocks and select query-relevant passages from public pages."""

import re
from html.parser import HTMLParser

_IGNORED = {"script", "style", "noscript", "template", "nav", "footer", "aside", "form", "svg"}
_BLOCKS = set(
    "p div section article main h1 h2 h3 h4 h5 h6 li tr br blockquote pre dl dt dd".split()
)
_VOID = set("area base br col embed hr img input link meta param source track wbr".split())
_MAIN = {"main", "article"}
_BOILERPLATE = re.compile(
    r"(^|[\s_-])(nav(?:igation)?|sidebar|footer|cookie|menu|breadcrumb|advertisement)([\s_-]|$)",
    re.I,
)
_TOKENS = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]+")
_STOP = set(
    "the and for with from who what which was were winner won best award awards result results final".split()
)
_CHARSET = re.compile(rb"<meta\b[^>]*\bcharset\s*=\s*['\"]?([a-z0-9._-]+)", re.I)


class _ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.blocks = []
        self.stack = []
        self.hidden = self.main = 0

    def flush(self):
        block = " ".join("".join(self.parts).split())
        if block:
            self.blocks.append((block, bool(self.main)))
        self.parts.clear()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = (
            tag in _IGNORED
            or "hidden" in attrs
            or attrs.get("aria-hidden") == "true"
            or attrs.get("role") in {"navigation", "banner", "complementary", "contentinfo"}
            or bool(_BOILERPLATE.search(f"{attrs.get('id') or ''} {attrs.get('class') or ''}"))
        )
        main = tag in _MAIN or attrs.get("role") == "main"
        if tag in _BLOCKS or hidden or main:
            self.flush()
        if tag not in _VOID:
            self.stack.append((tag, hidden, main))
            self.hidden += hidden
            self.main += main

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                if tag in _BLOCKS or any(hidden or main for _, hidden, main in self.stack[index:]):
                    self.flush()
                for _, hidden, main in self.stack[index:]:
                    self.hidden -= hidden
                    self.main -= main
                del self.stack[index:]
                return

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def decode_page(body, declared_encoding, *, html):
    if body.startswith(b"\xef\xbb\xbf"):
        return body.decode("utf-8-sig", errors="replace")
    if body.startswith((b"\xff\xfe", b"\xfe\xff")):
        return body.decode("utf-16", errors="replace")
    match = _CHARSET.search(body[:8192]) if html else None
    encoding = match[1].decode("ascii") if match else declared_encoding
    for candidate in dict.fromkeys((encoding, "utf-8", "windows-1252")):
        if candidate and candidate.lower() not in {"iso-8859-1", "latin-1"}:
            try:
                return body.decode(candidate)
            except (LookupError, UnicodeDecodeError):
                pass
    return body.decode("windows-1252", errors="replace")


def _terms(text):
    terms = set()
    for token in _TOKENS.findall(text.casefold()):
        if token[0].isascii():
            if len(token) > 1 and token not in _STOP:
                terms.add(token)
        else:
            terms.update(token[i : i + 2] for i in range(max(1, len(token) - 1)))
    return terms


def relevant_passages(text, *, html, queries, limit):
    if html:
        parser = _ArticleParser()
        parser.feed(text)
        parser.close()
        parser.flush()
        main = [block for block, in_main in parser.blocks if in_main]
        blocks = main if sum(map(len, main)) >= 120 else [block for block, _ in parser.blocks]
    else:
        blocks = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    blocks = list(dict.fromkeys(blocks))
    if sum(len(block) + 1 for block in blocks) <= limit:
        return "\n".join(blocks)
    # Overlapping windows let a match late in a long paragraph survive truncation.
    width = min(700, limit)
    windows = []
    for block in blocks:
        windows.append(block[:width])
        for start in range(max(1, width * 3 // 4), len(block), max(1, width * 3 // 4)):
            if start - max(1, width * 3 // 4) + width >= len(block):
                break
            windows.append(block[start : start + width])
    query_terms = _terms(" ".join(queries))
    ranked = sorted(windows, key=lambda block: -len(query_terms & _terms(block)))
    return "\n".join(ranked)[:limit].rstrip()
