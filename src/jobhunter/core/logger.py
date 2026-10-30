import logging
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

console = Console()


def setup_logging(level: str = "INFO", log_file: str = "logs/jobhunter.log") -> None:
  """Configures global application logging to output to both the console (Rich) and a log file."""
  numeric_level = getattr(logging, level.upper(), logging.INFO)

  log_path = Path(log_file)
  log_path.parent.mkdir(parents=True, exist_ok=True)

  # 1. Rich Console Handler (Terminal UI & Tracebacks)
  console_handler = RichHandler(
    console=console,
    rich_tracebacks=True,
    tracebacks_show_locals=False,
    markup=True,
  )
  # hide normal logger.info() from the terminal and only show errors!
  console_handler.setLevel(logging.CRITICAL)

  # 2. Standard File Handler (For debugging history)
  file_handler = logging.FileHandler(log_path, encoding="utf-8")
  file_handler.setLevel(numeric_level)
  file_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
  )
  file_handler.setFormatter(file_formatter)

  logging.basicConfig(
    level=numeric_level,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[console_handler, file_handler],
    force=True,
  )

  # 3. Suppress Noisy Third-Party Loggers
  noisy_prefixes = ("openai", "httpx", "httpcore", "urllib3", "ddgs", "primp")

  # Direct suppression
  for noisy_logger in noisy_prefixes:
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

  # Aggressive sub-logger suppression loop
  for name, logger in logging.root.manager.loggerDict.items():
    if any(name.startswith(prefix) for prefix in noisy_prefixes) and isinstance(logger, logging.Logger):
      logger.setLevel(logging.WARNING)
