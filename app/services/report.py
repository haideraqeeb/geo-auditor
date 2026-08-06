import logging
from datetime import datetime
from pathlib import Path

from services.scoring import ScoreBreakdown
from models import EvaluatorOutput

logger = logging.getLogger(__name__)


class ReportService:
    """
    Generates a human-readable audit report.
    """

    @staticmethod
    def generate(
        *,
        website: str,
        scores: ScoreBreakdown,
        evaluators: dict[str, EvaluatorOutput],
        output_dir: str = "reports",
    ) -> Path:

        output_dir = Path(output_dir)
        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        filename = (
            website.replace("https://", "")
            .replace("http://", "")
            .replace("/", "_")
        )

        report_path = (
            output_dir /
            f"{filename}_{timestamp}.txt"
        )

        lines = []

        lines.append("=" * 80)
        lines.append("GEO AUDIT REPORT")
        lines.append("=" * 80)
        lines.append("")

        lines.append(f"Website : {website}")
        lines.append(
            f"Generated : {datetime.now()}"
        )
        lines.append("")

        lines.append("-" * 80)
        lines.append("OVERALL SCORE")
        lines.append("-" * 80)

        lines.append(
            f"GEO Score      : {scores.geo:.2f}/100"
        )
        lines.append(
            f"Trust          : {scores.trust:.2f}/47.50"
        )
        lines.append(
            f"Content        : {scores.content:.2f}/42.50"
        )
        lines.append(
            f"Technical      : {scores.technical:.2f}/10.00"
        )

        lines.append("")

        for name, result in evaluators.items():

            lines.append("=" * 80)
            lines.append(name.upper())
            lines.append("=" * 80)

            lines.append(
                f"Score      : {result.score:.2f}"
            )
            confidence_text = (
                "N/A"
                if result.confidence is None
                else f"{result.confidence:.2f}"
            )
            lines.append(
                f"Confidence : {confidence_text}"
            )

            lines.append("")
            lines.append("Summary")
            lines.append(result.summary)
            lines.append("")

            if not result.findings:

                lines.append(
                    "No findings."
                )

            else:

                lines.append("Findings")

                for idx, finding in enumerate(
                    result.findings,
                    start=1,
                ):

                    lines.append("")
                    lines.append(
                        f"{idx}. {finding.title}"
                    )

                    lines.append(
                        f"Severity : {finding.severity.value}"
                    )

                    lines.append(
                        f"Description : {finding.description}"
                    )

                    if finding.recommendation:

                        lines.append(
                            f"Recommendation : {finding.recommendation}"
                        )

                    if finding.evidence:

                        lines.append(
                            "Evidence:"
                        )

                        for evidence in finding.evidence:

                            lines.append(
                                f"  - [{evidence.type.value}] {evidence.value}"
                            )

                            lines.append(
                                f"    {evidence.explanation}"
                            )

            lines.append("")

        report_path.write_text(
            "\n".join(lines),
            encoding="utf-8",
        )

        return report_path