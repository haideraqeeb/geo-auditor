import logging

from cwr.models import CanonicalWebsiteRepresentation
from evaluators.base import BaseEvaluator
from models import EvaluatorOutput
from utils.html import extract_document_structure

logger = logging.getLogger(__name__)


class ReadabilityEvaluator(BaseEvaluator):
    """
    Evaluates readability, organization and information
    structure of the website content.
    """

    name = "readability"

    def evaluate(
        self,
        cwr: CanonicalWebsiteRepresentation,
    ) -> EvaluatorOutput:

        logger.info("Running evaluator %s on %d pages", self.name, len(cwr.content))

        pages = []

        for page in cwr.content:

            pages.append(
                {
                    "url": page.url,
                    "title": page.title,
                    "document": extract_document_structure(
                        page.content
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