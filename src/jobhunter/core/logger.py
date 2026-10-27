import logging

from rich.logging import RichHandler


def setup_logging(level: str = "INFO") -> None:
  """Configures global application logging using Rich."""
  numeric_level = getattr(logging, level.upper(), logging.INFO)

  logging.basicConfig(
    level=numeric_level,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[
      RichHandler(
        rich_tracebacks=True,
        tracebacks_show_locals=False,
        markup=True,
      )
    ],
    force=True,
  )

  for noisy_logger in ("httpx", "httpcore", "urllib3"):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)
