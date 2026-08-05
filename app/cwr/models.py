from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WebsiteInfo(BaseModel):
    url: str
    domain: str


class PageContent(BaseModel):
    type: str = "page"

    url: str
    title: str

    content: str


class LinkCollection(BaseModel):
    internal: List[str] = Field(default_factory=list)
    external: List[str] = Field(default_factory=list)


class OpenGraphMetadata(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    url: Optional[str] = None
    site_name: Optional[str] = None
    type: Optional[str] = None


class TwitterMetadata(BaseModel):
    card: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None


class PageMetadata(BaseModel):
    url: str

    title: Optional[str] = None
    description: Optional[str] = None

    canonical: Optional[str] = None
    robots: Optional[str] = None

    open_graph: OpenGraphMetadata = Field(default_factory=OpenGraphMetadata)
    twitter: TwitterMetadata = Field(default_factory=TwitterMetadata)


class StructuredDataItem(BaseModel):
    url: str

    schema: List[Dict[str, Any]] = Field(default_factory=list)


class RobotsTxt(BaseModel):
    exists: bool
    content: Optional[str] = None


class Sitemap(BaseModel):
    exists: bool
    urls: List[str] = Field(default_factory=list)


class LLMsTxt(BaseModel):
    exists: bool
    content: Optional[str] = None


class CrawlResources(BaseModel):
    robots_txt: RobotsTxt

    sitemap: Sitemap

    llms_txt: LLMsTxt


class TemporalMetadata(BaseModel):
    url: str

    published: Optional[str] = None
    modified: Optional[str] = None

    last_modified_header: Optional[str] = None


class CanonicalWebsiteRepresentation(BaseModel):
    website: WebsiteInfo

    content: List[PageContent] = Field(default_factory=list)

    links: LinkCollection = Field(default_factory=LinkCollection)

    metadata: List[PageMetadata] = Field(default_factory=list)

    structured_data: List[StructuredDataItem] = Field(default_factory=list)

    crawl_resources: CrawlResources

    temporal: List[TemporalMetadata] = Field(default_factory=list)