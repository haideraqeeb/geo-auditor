import logging
import math
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

from models import EvaluatorOutput
from services.llm import LLMService
from services.scoring import ScoreBreakdown

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


class Evidence(BaseModel):
    location: str
    observed: str
    note: str


class Fix(BaseModel):
    steps: str
    copy_paste: str | None = None


class ReportFinding(BaseModel):
    title: str
    source_category: str
    severity: str
    why_it_matters: str
    evidence: list[Evidence]
    fix: Fix
    priority_rank: int


class LLMReportPayload(BaseModel):
    executive_summary: str
    findings: list[ReportFinding]


class Report(BaseModel):
    website: str
    generated_at: str
    scores: ScoreBreakdown
    executive_summary: str
    findings: list[ReportFinding]


class ReportService:
    _llm = LLMService()

    _jinja_env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "jinja"]),
    )
    _jinja_env.globals.update(
        cos=math.cos,
        sin=math.sin,
        pi=math.pi,
    )

    @staticmethod
    def generate(
        *,
        website: str,
        scores: ScoreBreakdown,
        evaluators: dict[str, EvaluatorOutput],
        output_dir: str = "reports",
        template_name: str = "report.html.jinja",
    ) -> dict:
        payload = ReportService._synthesize(scores, evaluators)

        report = Report(
            website=website,
            generated_at=datetime.now().strftime("%B %-d, %Y"),
            scores=scores,
            executive_summary=payload.executive_summary,
            findings=payload.findings,
        )

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = (
            website.replace("https://", "")
            .replace("http://", "")
            .replace("/", "_")
        )
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"{filename}_{timestamp}"

        # Save report JSON
        json_path = output_dir / f"{base}.json"
        json_path.write_text(
            report.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Render HTML
        template = ReportService._jinja_env.get_template(template_name)
        html = template.render(**report.model_dump())

        # Save HTML
        html_path = output_dir / f"{base}.html"
        html_path.write_text(
            html,
            encoding="utf-8",
        )

        logger.info("Report written to %s (data: %s)", html_path, json_path)

        return {
            "html": html,
            "html_path": str(html_path),
            "json_path": str(json_path),
        }

    @staticmethod
    def _synthesize(
        scores: ScoreBreakdown,
        evaluators: dict[str, EvaluatorOutput],
    ) -> LLMReportPayload:
        payload_in = {
            "scores": scores.model_dump(),
            "evaluators": {
                name: e.model_dump()
                for name, e in evaluators.items()
            },
        }

        return ReportService._llm.evaluate(
            prompt_name="report",
            input_data=payload_in,
            response_model=LLMReportPayload,
        )