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

  console_handler = RichHandler(
    console=console,
    rich_tracebacks=True,
    tracebacks_show_locals=False,
    markup=True,
  )
  console_handler.setLevel(numeric_level)

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

  for noisy_logger in ("ddgs", "primp", "httpx", "httpcore", "urllib3"):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def get_logger(name: str, log_to_console: bool = True, log_file: str = "logs/jobhunter.log") -> logging.Logger:
  """Gets a logger with an optional toggle to disable console output for this specific module."""
  logger = logging.getLogger(name)

  if not log_to_console:
    logger.propagate = False

    if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
      log_path = Path(log_file)
      log_path.parent.mkdir(parents=True, exist_ok=True)
      file_handler = logging.FileHandler(log_path, encoding="utf-8")
      file_handler.setFormatter(
        logging.Formatter(
          "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
          datefmt="%Y-%m-%d %H:%M:%S",
        )
      )
      logger.addHandler(file_handler)

  return logger
