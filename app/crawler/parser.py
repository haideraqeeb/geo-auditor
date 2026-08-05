"""
parser.py

Turns raw crawled HTML into the clean {title, content} shape the CWR needs,
plus lightweight structural info (headings, language) that downstream
evaluators (readability, entity coverage) want.

Primary extraction is done with trafilatura (handles boilerplate removal,
nav/footer/ad stripping, etc. far better than hand-rolled heuristics).
A bs4-based fallback kicks in on the rare page where trafilatura returns
nothing useful (e.g. heavily JS-rendered pages with almost no static text).

This module does NOT touch:
    - meta tags / open graph / twitter cards / structured data -> extractor.py
    - token counting                                            -> cwr/builder.py
"""


import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse
from typing import Iterable, List, Optional

import trafilatura
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

# Below this many characters, we treat trafilatura's output as "not useful"
# and fall back to the bs4 heuristic extractor.
MIN_TRAFILATURA_CONTENT_LENGTH = 200

# Tags stripped entirely before the bs4 fallback extraction runs.
NOISE_TAGS = {
    "script", "style", "noscript", "template", "svg", "iframe",
    "nav", "header", "footer", "aside", "form",
    "button", "select", "option", "input", "label",
}

# Class/id substrings that usually indicate boilerplate/chrome, not content.
# Used only by the bs4 fallback path.
NOISE_HINTS = (
    "cookie", "consent", "banner", "advert", "sidebar", "breadcrumb",
    "social-share", "newsletter", "popup", "modal", "subscribe",
    "site-header", "site-footer", "skip-link", "back-to-top",
)

BLOCK_TAGS = ("p", "li", "blockquote", "td", "th", "dt", "dd", "pre", "figcaption")
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")


# --------------------------------------------------------------------------- #
# Data models
# --------------------------------------------------------------------------- #

@dataclass
class Heading:
    level: int          # 1-6
    text: str


@dataclass
class ParsedPage:
    url: str
    title: str
    language: Optional[str]
    content: str
    headings: List[Heading] = field(default_factory=list)
    word_count: int = 0
    extraction_method: str = "trafilatura"  # or "fallback"

    def to_cwr_entry(self) -> dict:
        """Shape matching CWR content[] entries."""
        return {
            "type": "page",
            "url": self.url,
            "title": self.title,
            "content": self.content,
        }


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def parse_page(html: str, url: str) -> ParsedPage:
    """Parse a single page's raw HTML into a ParsedPage."""
    if not html or not html.strip():
        return ParsedPage(url=url, title=_title_from_url(url), language=None, content="")

    soup = BeautifulSoup(html, "lxml")

    title = _extract_title(soup, url)
    language = _extract_language(soup)
    headings = _extract_headings(soup)

    content, method = _extract_content(html, url, soup)
    word_count = len(content.split())

    return ParsedPage(
        url=url,
        title=title,
        language=language,
        content=content,
        headings=headings,
        word_count=word_count,
        extraction_method=method,
    )


def parse_pages(crawled_pages: Iterable) -> List[ParsedPage]:
    """
    Convenience batch wrapper.

    Accepts anything with .html and .url attributes (i.e. CrawledPage
    instances from crawler.py), so this stays decoupled from that module.
    """
    parsed: List[ParsedPage] = []
    for page in crawled_pages:
        try:
            parsed.append(parse_page(page.html, page.url))
        except Exception as exc:  # pragma: no cover - defensive, one bad page shouldn't kill the batch
            logger.warning("Failed to parse %s: %s", page.url, exc)
    return parsed


def to_cwr_content(parsed_pages: List[ParsedPage]) -> List[dict]:
    """Build the CWR `content` list from parsed pages."""
    return [p.to_cwr_entry() for p in parsed_pages]


# --------------------------------------------------------------------------- #
# Title / language / headings
# --------------------------------------------------------------------------- #

def _extract_title(soup: BeautifulSoup, url: str) -> str:
    if soup.title and soup.title.string and soup.title.string.strip():
        return _clean_whitespace(soup.title.string)

    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return _clean_whitespace(h1.get_text())

    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content", "").strip():
        return _clean_whitespace(og_title["content"])

    return _title_from_url(url)


def _title_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return urlparse(url).netloc
    last_segment = path.split("/")[-1]
    return last_segment.replace("-", " ").replace("_", " ").strip() or urlparse(url).netloc


def _extract_language(soup: BeautifulSoup) -> Optional[str]:
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        return html_tag["lang"].strip()

    og_locale = soup.find("meta", attrs={"property": "og:locale"})
    if og_locale and og_locale.get("content"):
        return og_locale["content"].strip()

    return None


def _extract_headings(soup: BeautifulSoup) -> List[Heading]:
    headings: List[Heading] = []
    for tag in soup.find_all(HEADING_TAGS):
        text = _clean_whitespace(tag.get_text())
        if not text:
            continue
        level = int(tag.name[1])
        headings.append(Heading(level=level, text=text))
    return headings


# --------------------------------------------------------------------------- #
# Main content extraction
# --------------------------------------------------------------------------- #

def _extract_content(html: str, url: str, soup: BeautifulSoup) -> tuple[str, str]:
    """Returns (content, method_used)."""
    extracted = trafilatura.extract(
        html,
        url=url,
        output_format="txt",
        include_comments=False,
        include_tables=True,
        favor_recall=True,   # GEO wants comprehensive coverage, not just a tight article body
    )

    if extracted and len(extracted.strip()) >= MIN_TRAFILATURA_CONTENT_LENGTH:
        return _clean_whitespace(extracted, collapse_newlines=True), "trafilatura"

    logger.info("trafilatura returned insufficient content for %s, using fallback extractor", url)
    return _fallback_extract(soup), "fallback"


def _fallback_extract(soup: BeautifulSoup) -> str:
    """
    Heuristic bs4 extractor used only when trafilatura comes up short
    (e.g. heavily JS-rendered pages with little static text).
    """
    working = BeautifulSoup(str(soup), "lxml")

    for tag in working.find_all(NOISE_TAGS):
        tag.decompose()

    for tag in working.find_all(True):
        identifiers = " ".join([tag.get("class", []) and " ".join(tag.get("class")) or "", tag.get("id", "") or ""]).lower()
        if any(hint in identifiers for hint in NOISE_HINTS):
            tag.decompose()

    main = working.find("main") or working.find("article") or working.find(attrs={"role": "main"}) or working.body
    if main is None:
        return ""

    blocks = []
    for tag in main.find_all(list(BLOCK_TAGS) + list(HEADING_TAGS)):
        text = _clean_whitespace(tag.get_text())
        if text:
            blocks.append(text)

    if not blocks:
        # last resort: just grab whatever text is left
        return _clean_whitespace(main.get_text(separator=" "))

    return "\n\n".join(blocks)


# --------------------------------------------------------------------------- #
# Text cleanup
# --------------------------------------------------------------------------- #

def _clean_whitespace(text: str, collapse_newlines: bool = False) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    if collapse_newlines:
        text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return text.strip()