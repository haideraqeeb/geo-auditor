import logging
from dataclasses import asdict, dataclass

from models import EvaluatorOutput

logger = logging.getLogger(__name__)

TRUST_WEIGHT = 47.5
CONTENT_WEIGHT = 42.5
TECHNICAL_WEIGHT = 10.0
TRUST_COMPONENTS = 2
CONTENT_COMPONENTS = 4
TECHNICAL_COMPONENTS = 3
TRUST_RELEVANCE_TOTAL = 10
CONTENT_RELEVANCE_TOTAL = 15


@dataclass
class ScoreBreakdown:
    """
    Final GEO scoring breakdown.
    """

    trust: float
    content: float
    technical: float
    geo: float

    def model_dump(self) -> dict:
        return asdict(self)


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
        technical: EvaluatorOutput,
    ) -> ScoreBreakdown:

        trust = (
            (
                (citation.score / 5) * 5 +
                (evidence.score / 5) * 5
            ) / TRUST_RELEVANCE_TOTAL
        ) * TRUST_WEIGHT

        content = (
            (
                (readability.score / 5) * 4 +
                (entity.score / 5) * 4 +
                (freshness.score / 5) * 4 +
                (faq.score / 5) * 3
            ) / CONTENT_RELEVANCE_TOTAL
        ) * CONTENT_WEIGHT

        technical_score = (
            technical.score / TECHNICAL_COMPONENTS
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
