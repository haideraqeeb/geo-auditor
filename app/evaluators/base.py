from abc import ABC, abstractmethod

from cwr.models import CanonicalWebsiteRepresentation
from models import EvaluatorOutput
from services.llm import LLMService


class BaseEvaluator(ABC):
    """
    Base class for all evaluators.
    """

    name: str = ""

    def __init__(
        self,
        llm: LLMService | None = None,
    ):
        self.llm = llm

    @abstractmethod
    def evaluate(
        self,
        cwr: CanonicalWebsiteRepresentation,
    ) -> EvaluatorOutput:
        """
        Evaluate the supplied Canonical Website Representation.
        """
        pass