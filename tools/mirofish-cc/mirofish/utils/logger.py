from __future__ import annotations

import logging
import sys
from pathlib import Path


def get_logger(name: str = "mirofish", log_file: str | None = None) -> logging.Logger:
    """Get or create a logger with console + optional file output.

    Console: INFO level, format: "[TIMESTAMP] LEVEL - MESSAGE"
    File: DEBUG level, format includes module name

    Uses singleton pattern — same name returns same logger.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if not any(isinstance(handler, logging.StreamHandler) and getattr(handler, "stream", None) is sys.stdout for handler in logger.handlers):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(console_handler)

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        has_same_file_handler = any(
            isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == log_path.resolve()
            for handler in logger.handlers
        )
        if not has_same_file_handler:
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(
                logging.Formatter(
                    "[%(asctime)s] %(levelname)s %(name)s %(module)s - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            logger.addHandler(file_handler)

    return logger


def setup_logging(log_dir: str | None = None, level: str = "INFO") -> None:
    """Configure root logger for the application.
    Creates log directory if needed.
    Sets UTF-8 encoding for handlers (important for Chinese text).
    """
    root_logger = logging.getLogger()
    root_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(root_level)

    root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(root_level)
    console_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    root_logger.addHandler(console_handler)

    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        app_log_file = log_path / "mirofish.log"
        file_handler = logging.FileHandler(app_log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] %(levelname)s %(name)s %(module)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root_logger.addHandler(file_handler)
