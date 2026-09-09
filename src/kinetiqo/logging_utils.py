import logging


DEFAULT_LOG_LEVEL = "INFO"
LOG_LEVEL_CHOICES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def resolve_log_level(log_level: str | None, default: str = DEFAULT_LOG_LEVEL) -> int:
    """Return a numeric logging level for a user-provided level name."""
    level_name = (log_level or default).upper()
    level = getattr(logging, level_name, None)
    if isinstance(level, int):
        return level
    fallback = getattr(logging, default.upper(), logging.INFO)
    return fallback if isinstance(fallback, int) else logging.INFO


def configure_logging(log_level: str | None, *, force_basic: bool = False) -> int:
    """Configure the application logger and return the numeric level used."""
    level = resolve_log_level(log_level)
    root = logging.getLogger()

    if force_basic or not root.handlers:
        logging.basicConfig(
            level=level,
            format='%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )
    else:
        root.setLevel(level)

    logging.getLogger("kinetiqo").setLevel(level)
    logging.getLogger("kinetiqo.web").setLevel(level)

    # Keep noisy dependencies quiet unless the application specifically raises
    # their level elsewhere.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    return level
