"""
extractor.py

Extracts everything about a page EXCEPT its body text:
    - meta tags (description, canonical, robots, Open Graph, Twitter cards)
    - JSON-LD structured data
    - temporal signals (published / modified dates)

Maps directly onto three sections of the CWR:
    metadata[]         <- extract_metadata()
    structured_data[]  <- extract_structured_data()
    temporal[]         <- extract_temporal()

This module does NOT touch:
    - body/main content extraction         -> parser.py
    - robots.txt / sitemap.xml / llms.txt  -> these are site-level resources
      (crawl_resources.* in the CWR), fetched explicitly, not per-page here.

Dependency note: `last_modified_header` requires the HTTP response headers,
which `crawler.CrawledPage` does not currently store (only content_type is
kept). Pass headers in explicitly if you have them; otherwise that field
will be None.
"""

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Data models
# --------------------------------------------------------------------------- #

@dataclass
class MetaTags:
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    canonical: Optional[str] = None
    robots: Optional[str] = None
    open_graph: Dict[str, str] = field(default_factory=dict)
    twitter: Dict[str, str] = field(default_factory=dict)

    def to_cwr_entry(self) -> dict:
        return asdict(self)


@dataclass
class StructuredDataEntry:
    url: str
    schema: List[dict] = field(default_factory=list)  # raw parsed JSON-LD objects

    def to_cwr_entry(self) -> dict:
        return {"url": self.url, "schema": self.schema}


@dataclass
class TemporalInfo:
    url: str
    published: Optional[str] = None
    modified: Optional[str] = None
    last_modified_header: Optional[str] = None

    def to_cwr_entry(self) -> dict:
        return asdict(self)


@dataclass
class PageSignals:
    """Bundled output of all three extractors for a single page."""
    metadata: MetaTags
    structured_data: StructuredDataEntry
    temporal: TemporalInfo


# --------------------------------------------------------------------------- #
# Public API — single page
# --------------------------------------------------------------------------- #

def extract_page_signals(
    html: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
) -> PageSignals:
    """Run all three extractors for one page in a single pass."""
    logger.info("Extracting page signals for %s", url)
    if not html or not html.strip():
        return PageSignals(
            metadata=MetaTags(url=url),
            structured_data=StructuredDataEntry(url=url),
            temporal=TemporalInfo(url=url, last_modified_header=_get_last_modified(headers)),
        )

    soup = BeautifulSoup(html, "lxml")

    metadata = extract_metadata(soup, url)
    structured_data = extract_structured_data(soup, url)
    temporal = extract_temporal(soup, url, structured_data=structured_data, headers=headers)

    return PageSignals(metadata=metadata, structured_data=structured_data, temporal=temporal)


def extract_metadata(soup: BeautifulSoup, url: str) -> MetaTags:
    title = _text_or_none(soup.title.string) if soup.title else None

    description = _meta_content(soup, "name", "description")
    canonical = _link_href(soup, "canonical")
    robots = _meta_content(soup, "name", "robots")

    open_graph = _collect_meta_family(soup, attr="property", prefix="og:")
    twitter = _collect_meta_family(soup, attr="name", prefix="twitter:")

    return MetaTags(
        url=url,
        title=title,
        description=description,
        canonical=canonical,
        robots=robots,
        open_graph=open_graph,
        twitter=twitter,
    )


def extract_structured_data(soup: BeautifulSoup, url: str) -> StructuredDataEntry:
    """
    Parse every <script type="application/ld+json"> block on the page.

    Handles:
      - a single JSON object per script tag
      - a JSON array of objects per script tag
      - the schema.org @graph pattern (flattened into individual entries)

    Full objects are kept (not just @type) so the structured data evaluator
    can assess completeness/relevance, not just presence.
    """
    entries: List[dict] = []

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Malformed JSON-LD on %s: %s", url, exc)
            continue

        entries.extend(_flatten_json_ld(parsed))

    return StructuredDataEntry(url=url, schema=entries)


def extract_temporal(
    soup: BeautifulSoup,
    url: str,
    structured_data: Optional[StructuredDataEntry] = None,
    headers: Optional[Dict[str, str]] = None,
) -> TemporalInfo:
    """
    Looks for published/modified dates in priority order:
      1. JSON-LD datePublished / dateModified
      2. <meta property="article:published_time" / "article:modified_time">
      3. <meta name="date" / "last-modified">
      4. <time datetime="..."> with a pubdate/itemprop hint
    last_modified_header comes straight from HTTP response headers, if given.
    """
    published = None
    modified = None

    if structured_data is not None:
        published, modified = _dates_from_json_ld(structured_data.schema)

    if published is None:
        published = _meta_content(soup, "property", "article:published_time")
    if modified is None:
        modified = _meta_content(soup, "property", "article:modified_time")

    if published is None:
        published = _meta_content(soup, "name", "date")
    if modified is None:
        modified = _meta_content(soup, "name", "last-modified")

    if published is None:
        published = _time_tag_datetime(soup, hint_attrs={"pubdate": None, "itemprop": "datePublished"})
    if modified is None:
        modified = _time_tag_datetime(soup, hint_attrs={"itemprop": "dateModified"})

    return TemporalInfo(
        url=url,
        published=published,
        modified=modified,
        last_modified_header=_get_last_modified(headers),
    )


# --------------------------------------------------------------------------- #
# Public API — batch
# --------------------------------------------------------------------------- #

def extract_all(crawled_pages: Iterable) -> Dict[str, List[dict]]:
    """
    Batch entry point. Accepts anything with .html, .url attributes
    (i.e. CrawledPage instances from crawler.py) and an optional .headers
    attribute if you add one.

    Returns CWR-ready lists:
        {"metadata": [...], "structured_data": [...], "temporal": [...]}
    """
    metadata_list: List[dict] = []
    structured_data_list: List[dict] = []
    temporal_list: List[dict] = []

    for page in crawled_pages:
        headers = getattr(page, "headers", None)
        try:
            signals = extract_page_signals(page.html, page.url, headers=headers)
        except Exception as exc:  # pragma: no cover - defensive, one bad page shouldn't kill the batch
            logger.warning("Failed to extract signals for %s: %s", page.url, exc)
            continue
        logger.debug("Extracted metadata/structured/temporal signals for %s", page.url)

        metadata_list.append(signals.metadata.to_cwr_entry())
        structured_data_list.append(signals.structured_data.to_cwr_entry())
        temporal_list.append(signals.temporal.to_cwr_entry())

    return {
        "metadata": metadata_list,
        "structured_data": structured_data_list,
        "temporal": temporal_list,
    }


# --------------------------------------------------------------------------- #
# Internals — meta tag helpers
# --------------------------------------------------------------------------- #

def _meta_content(soup: BeautifulSoup, attr: str, value: str) -> Optional[str]:
    tag = soup.find("meta", attrs={attr: value})
    if tag and tag.get("content"):
        return _clean(tag["content"])
    return None


def _link_href(soup: BeautifulSoup, rel: str) -> Optional[str]:
    tag = soup.find("link", attrs={"rel": rel})
    if tag and tag.get("href"):
        return tag["href"].strip()
    return None


def _collect_meta_family(soup: BeautifulSoup, attr: str, prefix: str) -> Dict[str, str]:
    """
    Collect all <meta attr="prefix*" content="..."> tags into a dict keyed
    by the part after the prefix, e.g. og:title -> {"title": "..."}.
    """
    collected: Dict[str, str] = {}
    for tag in soup.find_all("meta", attrs={attr: re.compile(rf"^{re.escape(prefix)}")}):
        key = tag.get(attr, "")[len(prefix):]
        content = tag.get("content")
        if key and content:
            # og:image / twitter:image etc. can appear multiple times;
            # keep the first occurrence (typically the primary one).
            collected.setdefault(key, _clean(content))
    return collected


def _text_or_none(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    cleaned = _clean(text)
    return cleaned or None


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _get_last_modified(headers: Optional[Dict[str, str]]) -> Optional[str]:
    if not headers:
        return None
    # header names can come back in any casing depending on the source
    for key, value in headers.items():
        if key.lower() == "last-modified":
            return value
    return None


# --------------------------------------------------------------------------- #
# Internals — JSON-LD
# --------------------------------------------------------------------------- #

def _flatten_json_ld(parsed: Any) -> List[dict]:
    """
    Normalize the various shapes JSON-LD can come in into a flat list of
    schema objects:
      - a bare object                     -> [object]
      - a list of objects                 -> objects
      - an object with "@graph": [...]    -> the @graph entries (graph
        wrapper itself dropped, since it carries no @type of its own)
    """
    if isinstance(parsed, dict):
        if "@graph" in parsed and isinstance(parsed["@graph"], list):
            flattened = []
            for item in parsed["@graph"]:
                if isinstance(item, dict):
                    flattened.append(item)
            return flattened
        return [parsed]

    if isinstance(parsed, list):
        flattened = []
        for item in parsed:
            flattened.extend(_flatten_json_ld(item))
        return flattened

    return []


def _dates_from_json_ld(schema: List[dict]) -> tuple[Optional[str], Optional[str]]:
    published = None
    modified = None
    for obj in schema:
        if not isinstance(obj, dict):
            continue
        if published is None and obj.get("datePublished"):
            published = str(obj["datePublished"])
        if modified is None and obj.get("dateModified"):
            modified = str(obj["dateModified"])
        if published and modified:
            break
    return published, modified


def _time_tag_datetime(soup: BeautifulSoup, hint_attrs: Dict[str, Optional[str]]) -> Optional[str]:
    """
    Looks for a <time> tag matching any of the given attribute hints
    (e.g. {"itemprop": "datePublished"} or {"pubdate": None} meaning
    "attribute present, any value").
    """
    for attr, value in hint_attrs.items():
        if value is None:
            tag = soup.find("time", attrs={attr: True})
        else:
            tag = soup.find("time", attrs={attr: value})
        if tag and tag.get("datetime"):
            return tag["datetime"].strip()
    return None