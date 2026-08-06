import logging
from collections import Counter
from datetime import datetime
import time

from cwr.models import CanonicalWebsiteRepresentation
from evaluators.base import BaseEvaluator
from models import (
    EvaluatorOutput,
    Finding,
    Evidence,
    EvidenceType,
    EvaluatorMetadata,
    Severity,
)

logger = logging.getLogger(__name__)


class SchemaEvaluator(BaseEvaluator):
    """
    Evaluates structured data (Schema.org / JSON-LD)
    present across the crawled website.
    """

    name = "schema"
    prompt_file = "schema.md"

    REQUIRED_SCHEMAS = {
        "Organization",
        "WebSite",
        "Article",
        "BreadcrumbList",
    }

    def evaluate(
        self,
        cwr: CanonicalWebsiteRepresentation,
    ) -> EvaluatorOutput:

        start_time = time.time()

        findings = []

        score = 0.0
        max_score = 4

        total_pages = len(cwr.structured_data)
        logger.info("Running evaluator %s with %d structured_data entries", self.name, total_pages)

        if total_pages == 0:

            findings.append(
                Finding(
                    title="No structured data found",
                    description="No Schema.org JSON-LD was detected.",
                    severity=Severity.HIGH,
                    evidence=[
                        Evidence(
                            type=EvidenceType.SCHEMA,
                            value="0 pages",
                            explanation="No JSON-LD structured data detected on the site",
                        )
                    ],
                )
            )

            return EvaluatorOutput(
                evaluator=self.name,
                score=0,
                confidence=10.0,
                max_score=max_score,
                findings=findings,
                summary="No structured data found.",
                metadata=EvaluatorMetadata(
                    evaluator=self.name,
                    model=getattr(self.llm, "model", "none"),
                    evaluation_timestamp=datetime.utcnow().isoformat(),
                    execution_time_ms=int((time.time() - start_time) * 1000),
                ),
            )

        schema_counter = Counter()

        pages_with_schema = 0

        for page in cwr.structured_data:

            if not page.schema:
                continue

            pages_with_schema += 1

            for item in page.schema:

                schema_type = item.get("@type")

                if isinstance(schema_type, list):
                    schema_counter.update(schema_type)

                elif isinstance(schema_type, str):
                    schema_counter[schema_type] += 1

        coverage = pages_with_schema / total_pages

        required_count = 0
        for schema in self.REQUIRED_SCHEMAS:

            if schema in schema_counter:

                required_count += 1

            else:

                findings.append(
                    Finding(
                        title=f"Missing {schema} schema",
                        description=f"No {schema} schema was detected.",
                        severity=Severity.LOW,
                        evidence=[
                            Evidence(
                                type=EvidenceType.SCHEMA,
                                value=schema,
                                explanation=f"Required schema type {schema} not found",
                            )
                        ],
                    )
                )

        if pages_with_schema:
            score = 1.0
            score += coverage * 1.5
            score += (required_count / len(self.REQUIRED_SCHEMAS)) * 1.5
            score = min(score, max_score)

        if coverage < 1:

            findings.append(
                Finding(
                    title="Missing structured data",
                    description=(
                        f"{total_pages-pages_with_schema} pages "
                        "do not contain JSON-LD."
                    ),
                    severity=Severity.MEDIUM,
                    evidence=[
                        Evidence(
                            type=EvidenceType.SCHEMA,
                            value=f"{pages_with_schema}/{total_pages}",
                            explanation="Pages with at least one JSON-LD structured data block",
                        )
                    ],
                )
            )

        duplicate_types = [
            schema
            for schema, count in schema_counter.items()
            if count > total_pages
        ]

        if duplicate_types:

            findings.append(
                Finding(
                    title="Duplicate schema types detected",
                    description=(
                        "Some schema types appear multiple times "
                        "across pages."
                    ),
                    severity=Severity.LOW,
                        evidence=[
                            Evidence(
                                type=EvidenceType.SCHEMA,
                                value=", ".join(duplicate_types),
                                explanation="Schema types appearing multiple times across pages",
                            )
                        ],
                )
            )

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
            summary="Structured data evaluation completed.",
            metadata=metadata,
        )