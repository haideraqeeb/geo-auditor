import logging

from cwr.models import CanonicalWebsiteRepresentation
from evaluators.base import BaseEvaluator
from models import EvaluatorOutput

logger = logging.getLogger(__name__)


class FreshnessEvaluator(BaseEvaluator):
    """
    Evaluates how current and up-to-date the content is.
    """

    name = "freshness"

    def evaluate(
        self,
        cwr: CanonicalWebsiteRepresentation,
    ) -> EvaluatorOutput:

        logger.info("Running evaluator %s on %d pages", self.name, len(cwr.content))

        pages = []

        for page in cwr.content:

            temporal = next(
                (
                    t
                    for t in cwr.temporal
                    if t.url == page.url
                ),
                None,
            )

            pages.append(
                {
                    "url": page.url,
                    "title": page.title,
                    "content": page.content,
                    "temporal": (
                        temporal.model_dump()
                        if temporal
                        else {}
                    ),
                }
            )

        return self.llm.evaluate(
            prompt_name=self.name,
            input_data={
                "website": cwr.website.model_dump(),
                "pages": pages,
            },
            response_model=EvaluatorOutput,
        )