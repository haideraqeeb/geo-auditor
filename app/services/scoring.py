import logging
from dataclasses import dataclass

from models import EvaluatorOutput

logger = logging.getLogger(__name__)

TRUST_WEIGHT = 47.5
CONTENT_WEIGHT = 42.5
TECHNICAL_WEIGHT = 10.0
SCHEMA_TECHNICAL_WEIGHT = 0.5


@dataclass
class ScoreBreakdown:
    """
    Final GEO scoring breakdown.
    """

    trust: float
    content: float
    technical: float
    geo: float


class ScoringService:
    """
    Computes the final GEO score from
    individual evaluator outputs.
    """

    @staticmethod
    def calculate(
        *,
        citation: EvaluatorOutput,
        evidence: EvaluatorOutput,
        readability: EvaluatorOutput,
        entity: EvaluatorOutput,
        freshness: EvaluatorOutput,
        faq: EvaluatorOutput,
        schema: EvaluatorOutput,
        technical: EvaluatorOutput,
    ) -> ScoreBreakdown:

        trust = (
            (
                citation.score +
                evidence.score
            ) / 10
        ) * TRUST_WEIGHT

        content = (
            (
                readability.score +
                entity.score +
                freshness.score +
                faq.score
            ) / 15
        ) * CONTENT_WEIGHT

        weighted_schema_score = schema.score * SCHEMA_TECHNICAL_WEIGHT
        technical_score = (
            (
                weighted_schema_score +
                technical.score
            ) / 5
        ) * TECHNICAL_WEIGHT

        geo = (
            trust +
            content +
            technical_score
        )

        breakdown = ScoreBreakdown(
            trust=round(trust, 2),
            content=round(content, 2),
            technical=round(technical_score, 2),
            geo=round(geo, 2),
        )
        logger.info(
            "Calculated scores: trust=%.2f content=%.2f technical=%.2f geo=%.2f",
            breakdown.trust,
            breakdown.content,
            breakdown.technical,
            breakdown.geo,
        )
        return breakdown
