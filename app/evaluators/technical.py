import logging
from collections import Counter
from datetime import datetime
import time
from models import (
    EvaluatorOutput,
    Finding,
    Evidence,
    EvidenceType,
    Severity,
    EvaluatorMetadata,
)

from evaluators.base import BaseEvaluator
from cwr.models import CanonicalWebsiteRepresentation

logger = logging.getLogger(__name__)


class TechnicalEvaluator(BaseEvaluator):
    """
    Evaluates technical discoverability signals that help
    search engines and LLMs discover and understand a website.
    """

    name = "technical"
    prompt_file = "technical.md"

    def evaluate(
        self,
        cwr: CanonicalWebsiteRepresentation,
    ) -> EvaluatorOutput:
        start_time = time.time()

        findings = []

        score = 0.0
        max_score = 3
        logger.info("Running evaluator %s", self.name)

        # --------------------------------------------------
        # robots.txt
        # --------------------------------------------------

        if cwr.crawl_resources.robots_txt.exists:
            score += 0.5
        else:
            findings.append(
                Finding(
                    title="Missing robots.txt",
                    description="robots.txt was not found.",
                    severity=Severity.HIGH,
                    evidence=[
                        Evidence(
                            type=EvidenceType.ROBOTS_RULE,
                            value="/robots.txt",
                            explanation="robots.txt was not found at the site root",
                        )
                    ]
                )
            )

        # --------------------------------------------------
        # sitemap.xml
        # --------------------------------------------------

        if cwr.crawl_resources.sitemap.exists:
            score += 0.5
        else:
            findings.append(
                Finding(
                    title="Missing sitemap.xml",
                    description="No sitemap.xml was discovered.",
                    severity=Severity.MEDIUM,
                    evidence=[
                        Evidence(
                            type=EvidenceType.SITEMAP_ENTRY,
                            value="/sitemap.xml",
                            explanation="sitemap.xml was not discovered or returned no URLs",
                        )
                    ]
                )
            )

        # --------------------------------------------------
        # llms.txt
        # --------------------------------------------------

        if cwr.crawl_resources.llms_txt.exists:
            score += 0.5
        else:
            findings.append(
                Finding(
                    title="Missing llms.txt",
                    description=(
                        "No llms.txt file found. "
                        "This reduces discoverability "
                        "for AI systems."
                    ),
                    severity=Severity.MEDIUM,
                    evidence=[
                        Evidence(
                            type=EvidenceType.LLMS_TXT,
                            value="/llms.txt",
                            explanation="llms.txt file not found at site root",
                        )
                    ]
                )
            )

        # --------------------------------------------------
        # Metadata
        # --------------------------------------------------

        total_pages = len(cwr.metadata)

        title_count = 0
        description_count = 0
        canonical_count = 0

        for page in cwr.metadata:

            if page.title:
                title_count += 1

            if page.description:
                description_count += 1

            if page.canonical:
                canonical_count += 1

        if total_pages:

            title_ratio = title_count / total_pages
            description_ratio = description_count / total_pages
            canonical_ratio = canonical_count / total_pages

            score += title_ratio * 0.5
            score += description_ratio * 0.5
            score += canonical_ratio * 0.5

            if title_ratio < 1:

                findings.append(
                    Finding(
                        title="Missing page titles",
                        description=(
                            f"{total_pages-title_count} pages "
                            "are missing title tags."
                        ),
                        severity=Severity.MEDIUM,
                            evidence=[
                                Evidence(
                                    type=EvidenceType.META_TAG,
                                    value=f"{title_count}/{total_pages}",
                                    explanation="Ratio of pages that include a title tag",
                                )
                            ]
                    )
                )

            if description_ratio < 1:

                findings.append(
                    Finding(
                        title="Missing meta descriptions",
                        description=(
                            f"{total_pages-description_count} pages "
                            "are missing descriptions."
                        ),
                        severity=Severity.LOW,
                            evidence=[
                                Evidence(
                                    type=EvidenceType.META_TAG,
                                    value=f"{description_count}/{total_pages}",
                                    explanation="Ratio of pages that include a meta description",
                                )
                            ]
                    )
                )

            if canonical_ratio < 1:

                findings.append(
                    Finding(
                        title="Missing canonical URLs",
                        description=(
                            f"{total_pages-canonical_count} pages "
                            "do not specify canonical URLs."
                        ),
                        severity=Severity.LOW,
                            evidence=[
                                Evidence(
                                    type=EvidenceType.META_TAG,
                                    value=f"{canonical_count}/{total_pages}",
                                    explanation="Ratio of pages that specify a canonical URL",
                                )
                            ]
                    )
                )

        structured_data_entries = getattr(cwr, "structured_data", [])
        if structured_data_entries:
            schema_counter = Counter()
            pages_with_schema = 0

            for page in structured_data_entries:
                if not page.schema:
                    continue

                pages_with_schema += 1

                for item in page.schema:
                    schema_type = item.get("@type")

                    if isinstance(schema_type, list):
                        schema_counter.update(schema_type)
                    elif isinstance(schema_type, str):
                        schema_counter[schema_type] += 1

            if pages_with_schema:
                coverage = pages_with_schema / len(structured_data_entries)
                required_schemas = {
                    "Organization",
                    "WebSite",
                    "Article",
                    "BreadcrumbList",
                }
                required_count = sum(
                    1 for schema in required_schemas if schema in schema_counter
                )
                schema_component = (
                    (coverage * 0.25) +
                    ((required_count / len(required_schemas)) * 0.25)
                )
                score += min(schema_component, 0.5)

        score = min(score, max_score)
        score = round(score, 2)

        exec_ms = int((time.time() - start_time) * 1000)
        metadata = EvaluatorMetadata(
            evaluator=self.name,
            model=getattr(self.llm, "model", "none"),
            evaluation_timestamp=datetime.utcnow().isoformat(),
            execution_time_ms=exec_ms,
        )

        return EvaluatorOutput(
            evaluator=self.name,
            score=score,
            confidence=10.0,
            max_score=max_score,
            findings=findings,
            summary=(
                "Technical discoverability evaluation "
                "completed successfully."
            ),
            metadata=metadata,
        )