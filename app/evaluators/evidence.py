import logging

from cwr.models import CanonicalWebsiteRepresentation
from evaluators.base import BaseEvaluator
from models import EvaluatorOutput

logger = logging.getLogger(__name__)


class EvidenceEvaluator(BaseEvaluator):
    """
    Evaluates whether claims are supported by evidence,
    statistics, benchmarks, studies and quantitative data.
    """

    name = "evidence"

    def evaluate(
        self,
        cwr: CanonicalWebsiteRepresentation,
    ) -> EvaluatorOutput:

        logger.info("Running evaluator %s on %d pages", self.name, len(cwr.content))

        pages = [
            {
                "url": page.url,
                "title": page.title,
                "content": page.content,
            }
            for page in cwr.content
        ]

        return self.llm.evaluate(
            prompt_name=self.name,
            input_data={
                "website": cwr.website.model_dump(),
                "pages": pages,
            },
            response_model=EvaluatorOutput,
        )