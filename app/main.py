from logging_config import configure_logging
from services.pipeline import AuditPipeline


def main():

    configure_logging()

    url = input(
        "Enter website URL: "
    ).strip()

    pipeline = AuditPipeline()

    result = pipeline.run(url)

    print("\nAudit completed successfully!\n")

    print(f"Report saved to: {result['report']}")

    print(
        f"GEO Score: {result['scores'].geo:.2f}/100"
    )


if __name__ == "__main__":
    main()