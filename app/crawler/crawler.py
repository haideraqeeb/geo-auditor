"""
crawler.py

BFS website crawler for the GEO auditor.

Responsibilities (and ONLY these):
    - fetch pages starting from a root URL
    - enforce crawl boundaries (depth, page count, domain, content-type, status code)
    - discover links on each page so the BFS queue can be expanded
    - hand back raw fetched pages (url, html, headers, depth, discovered links)

NOT this module's job (left to other files in the pipeline):
    - extracting title / body text / readable content        -> parser.py
    - extracting meta tags, structured data, temporal info    -> extractor.py
    - token counting against the 80k CWR budget               -> cwr/builder.py
    - fetching robots.txt / sitemap.xml / llms.txt            -> handled explicitly elsewhere
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse
from typing import Deque, Iterable, List, Optional, Set

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Config / constants
# --------------------------------------------------------------------------- #

DEFAULT_MAX_DEPTH = 2
DEFAULT_MAX_PAGES = 40
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_USER_AGENT = "GEOAuditorBot/0.1 (+https://example.com/bot)"

ALLOWED_CONTENT_TYPE_PREFIX = "text/html"
ALLOWED_SCHEMES = {"http", "https"}

# Schemes/prefixes that show up in <a href> but are never crawlable pages.
NON_CRAWLABLE_HREF_PREFIXES = (
    "mailto:",
    "tel:",
    "javascript:",
    "data:",
    "#",
)


# --------------------------------------------------------------------------- #
# Data models
# --------------------------------------------------------------------------- #

@dataclass
class CrawledPage:
    """A single successfully-fetched HTML page, plus what we found on it."""

    url: str                       # normalized URL actually fetched
    depth: int
    status_code: int
    content_type: str
    html: str
    headers: dict = field(default_factory=dict)   # raw response headers, e.g. for Last-Modified
    internal_links: List[str] = field(default_factory=list)
    external_links: List[str] = field(default_factory=list)
    fetched_at: float = field(default_factory=time.time)


@dataclass
class SkippedURL:
    """Record of a URL we deliberately did not fetch, and why. Useful for debugging/logs."""

    url: str
    reason: str
    depth: int


@dataclass
class CrawlResult:
    """Everything the crawl produced, ready to be handed to cwr/builder.py."""

    root_url: str
    domain: str
    pages: List[CrawledPage] = field(default_factory=list)
    skipped: List[SkippedURL] = field(default_factory=list)
    hit_max_pages: bool = False

    @property
    def all_internal_links(self) -> Set[str]:
        links: Set[str] = set()
        for page in self.pages:
            links.update(page.internal_links)
        return links

    @property
    def all_external_links(self) -> Set[str]:
        links: Set[str] = set()
        for page in self.pages:
            links.update(page.external_links)
        return links


@dataclass
class _QueueItem:
    url: str
    depth: int


# --------------------------------------------------------------------------- #
# URL helpers
# --------------------------------------------------------------------------- #

def normalize_url(url: str) -> str:
    """
    Canonicalize a URL so equivalent URLs dedupe correctly.

    - drops the fragment (#section)
    - lowercases scheme and host
    - strips a trailing slash (except for bare root "/")
    """
    url, _fragment = urldefrag(url)
    parsed = urlparse(url)

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    normalized = parsed._replace(scheme=scheme, netloc=netloc, path=path)
    return normalized.geturl()


def get_domain(url: str) -> str:
    """Registered host, e.g. 'openai.com' or 'docs.openai.com'."""
    return urlparse(url).netloc.lower()


def get_base_domain(url: str) -> str:
    """
    Naive base-domain extraction (last two labels), used to decide whether
    a subdomain belongs to the same site.

    e.g. "docs.openai.com" -> "openai.com"
         "openai.com"      -> "openai.com"
         "openai.co.uk"    -> "co.uk"  (known limitation, see is_same_site below)
    """
    host = get_domain(url)
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    return ".".join(labels[-2:])


def is_same_site(candidate_url: str, root_domain: str) -> bool:
    """
    True if candidate_url is on the same domain as the root, allowing subdomains.

    Comparison is against the *full* root domain (not the naive base-domain
    heuristic) so that "docs.openai.com" matches root "openai.com", but a
    completely different domain like "notopenai.com" does not.
    """
    candidate_domain = get_domain(candidate_url)
    if not candidate_domain:
        return False
    return candidate_domain == root_domain or candidate_domain.endswith("." + root_domain)


def is_crawlable_href(href: str) -> bool:
    if not href:
        return False
    href = href.strip()
    if not href:
        return False
    lowered = href.lower()
    return not lowered.startswith(NON_CRAWLABLE_HREF_PREFIXES)


# --------------------------------------------------------------------------- #
# Crawler
# --------------------------------------------------------------------------- #

class Crawler:
    """
    BFS crawler with boundaries.

    Usage:
        crawler = Crawler(root_url="https://openai.com")
        result = crawler.crawl()
    """

    def __init__(
        self,
        root_url: str,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_pages: int = DEFAULT_MAX_PAGES,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
        session: Optional[requests.Session] = None,
    ):
        self.root_url = normalize_url(root_url)
        self.root_domain = get_domain(self.root_url)

        if not self.root_domain:
            raise ValueError(f"Could not parse a domain from root_url: {root_url!r}")

        self.max_depth = max_depth
        self.max_pages = max_pages
        self.timeout = timeout

        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

        self._visited: Set[str] = set()      # normalized URLs already fetched or queued
        self._queue: Deque[_QueueItem] = deque()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def crawl(self) -> CrawlResult:
        logger.info(
            "Starting crawl for %s with max_depth=%d max_pages=%d",
            self.root_url,
            self.max_depth,
            self.max_pages,
        )
        result = CrawlResult(root_url=self.root_url, domain=self.root_domain)

        self._queue.append(_QueueItem(url=self.root_url, depth=0))
        self._visited.add(self.root_url)

        while self._queue:
            if len(result.pages) >= self.max_pages:
                result.hit_max_pages = True
                logger.info("Reached max_pages=%d, stopping crawl.", self.max_pages)
                break

            item = self._queue.popleft()

            page, skip_reason = self._fetch_and_validate(item.url, item.depth)

            if page is None:
                result.skipped.append(
                    SkippedURL(url=item.url, reason=skip_reason or "unknown", depth=item.depth)
                )
                logger.info(
                    "Skipped URL %s at depth %d: %s",
                    item.url,
                    item.depth,
                    skip_reason,
                )
                continue

            result.pages.append(page)
            logger.info("[%d/%d] depth=%d fetched %s", len(result.pages), self.max_pages, item.depth, page.url)

            # Don't discover/enqueue children beyond max_depth.
            if item.depth >= self.max_depth:
                continue

            for link in page.internal_links:
                normalized = normalize_url(link)
                if normalized in self._visited:
                    continue
                self._visited.add(normalized)
                self._queue.append(_QueueItem(url=normalized, depth=item.depth + 1))

        return result

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _fetch_and_validate(self, url: str, depth: int) -> tuple[Optional[CrawledPage], Optional[str]]:
        """
        Fetch a single URL and apply all boundary checks.
        Returns (CrawledPage, None) on success, or (None, reason) if skipped/failed.
        """
        parsed = urlparse(url)
        if parsed.scheme not in ALLOWED_SCHEMES:
            return None, f"unsupported scheme: {parsed.scheme!r}"

        if not is_same_site(url, self.root_domain):
            return None, f"different domain: {get_domain(url)!r}"

        try:
            response = self.session.get(url, timeout=self.timeout, stream=True, allow_redirects=True)
        except requests.RequestException as exc:
            logger.warning("Request failed for %s: %s", url, exc)
            return None, f"request error: {exc}"

        try:
            if response.status_code != 200:
                return None, f"non-200 status: {response.status_code}"

            content_type = response.headers.get("Content-Type", "")
            if not content_type.lower().startswith(ALLOWED_CONTENT_TYPE_PREFIX):
                return None, f"non-html content-type: {content_type!r}"

            # Redirects can land us on a different (but still in-domain?) URL.
            # Re-validate domain against the final resolved URL.
            final_url = normalize_url(response.url)
            if not is_same_site(final_url, self.root_domain):
                return None, f"redirected off-domain to: {get_domain(final_url)!r}"

            html = response.text
            # requests.Session gives back a CaseInsensitiveDict; snapshot it
            # into a plain dict so CrawledPage doesn't hold a live handle
            # onto the (about-to-be-closed) response object.
            response_headers = dict(response.headers)
        finally:
            response.close()

        internal_links, external_links = self._extract_links(html, base_url=final_url)

        return (
            CrawledPage(
                url=final_url,
                depth=depth,
                status_code=response.status_code,
                content_type=content_type,
                html=html,
                headers=response_headers,
                internal_links=internal_links,
                external_links=external_links,
            ),
            None,
        )

    def _extract_links(self, html: str, base_url: str) -> tuple[List[str], List[str]]:
        """
        Minimal link discovery for BFS purposes only.

        Full content/anchor-text extraction for the CWR's "links" section
        belongs in extractor.py — this just needs enough to keep the queue
        moving and to report internal/external link lists.
        """
        internal: List[str] = []
        external: List[str] = []
        seen: Set[str] = set()

        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to parse HTML for link extraction at %s: %s", base_url, exc)
            return internal, external

        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            if not is_crawlable_href(href):
                continue

            absolute = urljoin(base_url, href)
            absolute, _ = urldefrag(absolute)
            parsed = urlparse(absolute)

            if parsed.scheme not in ALLOWED_SCHEMES:
                continue

            normalized = normalize_url(absolute)
            if normalized in seen:
                continue
            seen.add(normalized)

            if is_same_site(normalized, self.root_domain):
                internal.append(normalized)
            else:
                external.append(normalized)

        return internal, external


# --------------------------------------------------------------------------- #
# Convenience function
# --------------------------------------------------------------------------- #

def crawl_website(
    url: str,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> CrawlResult:
    """Thin functional wrapper around Crawler for simple call sites."""
    crawler = Crawler(root_url=url, max_depth=max_depth, max_pages=max_pages)
    return crawler.crawl()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    res = crawl_website(target)

    print(f"\nCrawled {len(res.pages)} pages from {res.root_url}")
    print(f"Hit max_pages: {res.hit_max_pages}")
    print(f"Skipped: {len(res.skipped)}")
    for p in res.pages:
        print(f"  depth={p.depth}  {p.url}")