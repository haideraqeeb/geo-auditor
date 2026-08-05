from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvidenceType(str, Enum):
    CITATION = "citation"
    SOURCE = "source"
    CLAIM = "claim"
    STATISTIC = "statistic"
    ENTITY = "entity"
    DATE = "date"
    META_TAG = "meta_tag"
    SCHEMA = "schema"
    ROBOTS_RULE = "robots_rule"
    SITEMAP_ENTRY = "sitemap_entry"
    LLMS_TXT = "llms_txt"
    HEADING = "heading"
    CONTENT_SAMPLE = "content_sample"
    INTERNAL_LINK = "internal_link"
    EXTERNAL_LINK = "external_link"
    OTHER = "other"


class Evidence(BaseModel):
    """
    Atomic piece of evidence supporting a finding.
    """

    type: EvidenceType

    value: str

    explanation: str

    page_url: Optional[str] = None

    location: Optional[str] = None


class Finding(BaseModel):
    """
    A single observation made by an evaluator.
    """

    title: str

    severity: Severity

    description: str

    evidence: List[Evidence] = Field(default_factory=list)

    recommendation: Optional[str] = None


class EvaluatorMetadata(BaseModel):
    """
    Metadata about the evaluation itself.
    """

    evaluator: str

    model: str

    evaluation_timestamp: Optional[str] = None

    execution_time_ms: Optional[int] = None


class EvaluatorOutput(BaseModel):
    """
    Standardized output for every GEO evaluator.
    """

    score: float = Field(
        ...,
        ge=0,
        le=5,
        description="Evaluator score between 0 and 5."
    )

    confidence: Optional[float] = Field(
        None,
        ge=0,
        le=10,
        description="Confidence between 0 and 10."
    )

    summary: str

    findings: List[Finding] = Field(default_factory=list)

    metadata: EvaluatorMetadata