import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from crawler.crawler import Crawler
from cwr.builder import build_cwr

from evaluators.citation import CitationEvaluator
from evaluators.evidence import EvidenceEvaluator
from evaluators.readability import ReadabilityEvaluator
from evaluators.entity import EntityEvaluator
from evaluators.freshness import FreshnessEvaluator
from evaluators.faq import FAQEvaluator
from evaluators.technical import TechnicalEvaluator

from models import EvaluatorOutput

logger = logging.getLogger(__name__)

from services.llm import LLMService
from services.report import ReportService
from services.scoring import ScoringService

logger = logging.getLogger(__name__)


class AuditPipeline:
    """
    End-to-end GEO auditing pipeline.
    """

    def __init__(self):

        self.llm = LLMService()

        self.evaluators = {
            "citation": CitationEvaluator(self.llm),
            "evidence": EvidenceEvaluator(self.llm),
            "readability": ReadabilityEvaluator(self.llm),
            "entity": EntityEvaluator(self.llm),
            "freshness": FreshnessEvaluator(self.llm),
            "faq": FAQEvaluator(self.llm),
            "technical": TechnicalEvaluator(),
        }

    def run(
        self,
        url: str,
        *,
        max_depth: int = 2,
        max_pages: int = 20,
    ):

        logger.info(
            "Starting audit pipeline for %s (max_depth=%d, max_pages=%d)",
            url,
            max_depth,
            max_pages,
        )

        # Crawl website
        crawler = Crawler(
            root_url=url,
            max_depth=max_depth,
            max_pages=max_pages,
        )

        crawl_result = crawler.crawl()
        logger.info(
            "Crawl complete: %d pages fetched, %d skipped",
            len(crawl_result.pages),
            len(crawl_result.skipped),
        )

        # Build Canonical Website Representation
        cwr = build_cwr(
            crawl_result,
            session=crawler.session,
        )
        logger.info(
            "Built CWR: %d content entries, %d metadata entries, %d structured_data entries, %d temporal entries",
            len(cwr.content),
            len(cwr.metadata),
            len(cwr.structured_data),
            len(cwr.temporal),
        )

        # Run evaluators in parallel where possible
        results: dict[str, EvaluatorOutput] = {}
        future_to_name = {}

        with ThreadPoolExecutor(max_workers=len(self.evaluators)) as executor:
            for name, evaluator in self.evaluators.items():
                future = executor.submit(evaluator.evaluate, cwr)
                future_to_name[future] = name

            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    results[name] = future.result()
                    logger.info(
                        "Evaluator %s completed: score=%.2f",
                        name,
                        results[name].score,
                    )
                except Exception as exc:
                    logger.error("Evaluator %s failed: %s", name, exc)
                    raise

        # Calculate scores
        scores = ScoringService.calculate(
            citation=results["citation"],
            evidence=results["evidence"],
            readability=results["readability"],
            entity=results["entity"],
            freshness=results["freshness"],
            faq=results["faq"],
            technical=results["technical"],
        )

        # Generate report
        report = ReportService.generate(
            website=url,
            scores=scores,
            evaluators=results,
        )

        logger.info("Report generated at %s", report["html_path"])

        return {
            "crawl_result": crawl_result,
            "cwr": cwr,
            "scores": scores,
            "evaluations": results,
            "report": report,
        }