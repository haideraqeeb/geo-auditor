import logging


DEFAULT_LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"
DEFAULT_LOG_LEVEL = logging.INFO


def configure_logging(level: int = DEFAULT_LOG_LEVEL, fmt: str = DEFAULT_LOG_FORMAT) -> None:
    """Configure basic logging for the GEO Auditor."""
    logging.basicConfig(level=level, format=fmt)
