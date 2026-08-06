"""
cwr/builder.py

Assembles the Canonical Website Representation (CWR) from:
    - crawler.CrawlResult          (already-fetched pages)
    - parser.parse_page()          (title/content/headings per page)
    - extractor.extract_page_signals()  (meta tags/structured data/temporal per page)
    - robots.txt / sitemap.xml / llms.txt, fetched explicitly here (site-level
      resources, not part of the BFS crawl)

Output is a validated cwr.models.CanonicalWebsiteRepresentation, ready to be
handed to the evaluators. Token budgeting (the 80k tiktoken limit) happens
downstream of this -- this module only assembles content, it doesn't trim it.
"""

import logging
import re
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import requests

from crawler.crawler import Crawler, CrawlResult, DEFAULT_MAX_DEPTH, DEFAULT_MAX_PAGES
from crawler.extractor import MetaTags, extract_page_signals
from crawler.parser import parse_page

from cwr.models import (
    CanonicalWebsiteRepresentation,
    CrawlResources,
    LinkCollection,
    LLMsTxt,
    OpenGraphMetadata,
    PageContent,
    PageMetadata,
    RobotsTxt,
    Sitemap,
    StructuredDataItem,
    TemporalMetadata,
    TwitterMetadata,
    WebsiteInfo,
)

logger = logging.getLogger(__name__)


DEFAULT_RESOURCE_TIMEOUT_SECONDS = 10
DEFAULT_USER_AGENT = "GEOAuditorBot/0.1 (+https://example.com/bot)"

# Sitemap index files can nest further sitemaps; cap how many we'll follow
# so a pathological site can't turn this into an unbounded crawl.
MAX_SITEMAPS_TO_FOLLOW = 5
MAX_SITEMAP_URLS = 500

XML_NAMESPACE_RE = re.compile(r"\{.*\}")  # strips XML namespace prefixes from tag names


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def build_cwr(
    crawl_result: CrawlResult,
    session: Optional[requests.Session] = None,
    resource_timeout: int = DEFAULT_RESOURCE_TIMEOUT_SECONDS,
) -> CanonicalWebsiteRepresentation:
    """
    Build a CWR from an already-completed crawl.

    Parsing/extraction failures on individual pages are logged and skipped
    rather than failing the whole build -- a few bad pages shouldn't sink
    the audit.
    """
    logger.info(
        "Building CWR from crawl result: %d pages fetched, %d skipped",
        len(crawl_result.pages),
        len(crawl_result.skipped),
    )
    session = session or _new_session()

    website = WebsiteInfo(url=crawl_result.root_url, domain=crawl_result.domain)

    content: List[PageContent] = []
    metadata: List[PageMetadata] = []
    structured_data: List[StructuredDataItem] = []
    temporal: List[TemporalMetadata] = []

    for page in crawl_result.pages:
        try:
            parsed = parse_page(page.html, page.url)
            content.append(PageContent(url=parsed.url, title=parsed.title, content=parsed.content, html=page.html))
        except Exception as exc:  # noqa: BLE001 - one bad page shouldn't kill the build
            logger.warning("parser failed for %s: %s", page.url, exc)

        try:
            signals = extract_page_signals(page.html, page.url, headers=page.headers)
            metadata.append(_to_page_metadata(signals.metadata))
            structured_data.append(
                StructuredDataItem(url=signals.structured_data.url, schema=signals.structured_data.schema)
            )
            temporal.append(TemporalMetadata(**signals.temporal.to_cwr_entry()))
        except Exception as exc:  # noqa: BLE001
            logger.warning("extractor failed for %s: %s", page.url, exc)

    links = LinkCollection(
        internal=sorted(crawl_result.all_internal_links),
        external=sorted(crawl_result.all_external_links),
    )

    crawl_resources = _build_crawl_resources(crawl_result.root_url, session, resource_timeout)
    logger.info(
        "CWR assembled: content=%d metadata=%d structured_data=%d temporal=%d",
        len(content),
        len(metadata),
        len(structured_data),
        len(temporal),
    )

    return CanonicalWebsiteRepresentation(
        website=website,
        content=content,
        links=links,
        metadata=metadata,
        structured_data=structured_data,
        crawl_resources=crawl_resources,
        temporal=temporal,
    )


def build_cwr_from_url(
    url: str,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> CanonicalWebsiteRepresentation:
    """Convenience one-shot: crawl a site and build its CWR in a single call."""
    crawler = Crawler(root_url=url, max_depth=max_depth, max_pages=max_pages)
    crawl_result = crawler.crawl()
    return build_cwr(crawl_result, session=crawler.session)


# --------------------------------------------------------------------------- #
# Internals -- metadata mapping (extractor's flat dicts -> CWR's typed models)
# --------------------------------------------------------------------------- #

def _to_page_metadata(meta: MetaTags) -> PageMetadata:
    return PageMetadata(
        url=meta.url,
        title=meta.title,
        description=meta.description,
        canonical=meta.canonical,
        robots=meta.robots,
        open_graph=_to_open_graph(meta.open_graph),
        twitter=_to_twitter(meta.twitter),
    )


def _to_open_graph(og: Dict[str, str]) -> OpenGraphMetadata:
    # Only the fields the CWR model actually declares; anything else
    # extractor.py picked up (og:image:width, og:locale, etc.) is dropped
    # here rather than silently relying on pydantic's extra-field handling.
    return OpenGraphMetadata(
        title=og.get("title"),
        description=og.get("description"),
        image=og.get("image"),
        url=og.get("url"),
        site_name=og.get("site_name"),
        type=og.get("type"),
    )


def _to_twitter(tw: Dict[str, str]) -> TwitterMetadata:
    return TwitterMetadata(
        card=tw.get("card"),
        title=tw.get("title"),
        description=tw.get("description"),
        image=tw.get("image"),
    )


# --------------------------------------------------------------------------- #
# Internals -- site-level resources (robots.txt / sitemap.xml / llms.txt)
# --------------------------------------------------------------------------- #

def _new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": DEFAULT_USER_AGENT})
    return session


def _build_crawl_resources(root_url: str, session: requests.Session, timeout: int) -> CrawlResources:
    parsed = urlparse(root_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    logger.info("Fetching site-level crawl resources for %s", base)

    robots_txt = _fetch_robots_txt(base, session, timeout)
    sitemap = _fetch_sitemap(base, robots_txt, session, timeout)
    llms_txt = _fetch_llms_txt(base, session, timeout)

    return CrawlResources(robots_txt=robots_txt, sitemap=sitemap, llms_txt=llms_txt)


def _fetch_robots_txt(base: str, session: requests.Session, timeout: int) -> RobotsTxt:
    logger.info("Fetching robots.txt from %s", urljoin(base, "/robots.txt"))
    text = _fetch_text_resource(urljoin(base, "/robots.txt"), session, timeout, expect_plain_text=True)
    if text is None:
        return RobotsTxt(exists=False, content=None)
    return RobotsTxt(exists=True, content=text)


def _fetch_llms_txt(base: str, session: requests.Session, timeout: int) -> LLMsTxt:
    # Presence is worth a small score bump per the rubric; we don't do any
    # deep parsing of llms.txt content here, just store what's there.
    logger.info("Fetching llms.txt from %s", urljoin(base, "/llms.txt"))
    text = _fetch_text_resource(urljoin(base, "/llms.txt"), session, timeout, expect_plain_text=True)
    if text is None:
        return LLMsTxt(exists=False, content=None)
    return LLMsTxt(exists=True, content=text)


def _fetch_sitemap(base: str, robots_txt: RobotsTxt, session: requests.Session, timeout: int) -> Sitemap:
    sitemap_url = _sitemap_url_from_robots(robots_txt.content) or urljoin(base, "/sitemap.xml")
    logger.info("Fetching sitemap from %s", sitemap_url)

    urls = _collect_sitemap_urls(sitemap_url, session, timeout, seen_sitemaps=set())
    if not urls:
        return Sitemap(exists=False, urls=[])
    return Sitemap(exists=True, urls=urls[:MAX_SITEMAP_URLS])


def _sitemap_url_from_robots(robots_content: Optional[str]) -> Optional[str]:
    if not robots_content:
        return None
    for line in robots_content.splitlines():
        line = line.strip()
        if line.lower().startswith("sitemap:"):
            return line.split(":", 1)[1].strip()
    return None


def _collect_sitemap_urls(
    sitemap_url: str,
    session: requests.Session,
    timeout: int,
    seen_sitemaps: Set[str],
    depth: int = 0,
) -> List[str]:
    """
    Fetch a sitemap and return page URLs.

    Handles both a plain <urlset> (page URLs directly) and a <sitemapindex>
    (URLs pointing to further sitemaps), following nested sitemaps up to
    MAX_SITEMAPS_TO_FOLLOW to bound the work.
    """
    if sitemap_url in seen_sitemaps or len(seen_sitemaps) >= MAX_SITEMAPS_TO_FOLLOW:
        return []
    seen_sitemaps.add(sitemap_url)

    xml_text = _fetch_text_resource(sitemap_url, session, timeout, expect_plain_text=False)
    if xml_text is None:
        return []

    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        logger.info("Could not parse sitemap XML at %s: %s", sitemap_url, exc)
        return []

    loc_values = [
        (elem.text or "").strip()
        for elem in root.iter()
        if XML_NAMESPACE_RE.sub("", elem.tag) == "loc" and elem.text
    ]

    is_index = XML_NAMESPACE_RE.sub("", root.tag) == "sitemapindex"
    if not is_index:
        return loc_values

    # sitemap index: loc_values are further sitemap URLs, follow them
    collected: List[str] = []
    for child_sitemap_url in loc_values:
        collected.extend(_collect_sitemap_urls(child_sitemap_url, session, timeout, seen_sitemaps, depth + 1))
        if len(collected) >= MAX_SITEMAP_URLS:
            break
    return collected


def _fetch_text_resource(
    url: str,
    session: requests.Session,
    timeout: int,
    expect_plain_text: bool,
) -> Optional[str]:
    """
    Fetch a text resource (robots.txt / sitemap.xml / llms.txt) and return its
    body, or None if it doesn't really exist.

    Guards against the common false-positive where a site returns HTTP 200
    with its normal HTML page (a soft-404) for a path that doesn't actually
    exist, rather than a real 404.
    """
    try:
        response = session.get(url, timeout=timeout)
    except requests.RequestException as exc:
        logger.info("Could not fetch %s: %s", url, exc)
        return None

    try:
        if response.status_code != 200:
            return None

        content_type = response.headers.get("Content-Type", "").lower()
        text = response.text

        if _looks_like_html(text):
            # Soft-404: server served the normal site HTML instead of a real 404.
            return None

        if expect_plain_text and content_type and "html" in content_type:
            return None

        return text
    finally:
        response.close()


def _looks_like_html(text: str) -> bool:
    sample = text[:1000].strip().lower()
    return sample.startswith("<!doctype html") or "<html" in sample