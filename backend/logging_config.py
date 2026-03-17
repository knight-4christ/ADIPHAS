"""
Centralized logging configuration for ADIPHAS.

Import this module FIRST in main.py to ensure all loggers
inherit the file + console handlers before they emit anything.
"""
import logging
import os
from logging.handlers import RotatingFileHandler

# Ensure log directory exists
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "adiphas.log")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

def setup_logging():
    """Configure root logger with file + console handlers."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Avoid adding duplicate handlers on reload
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return

    # File handler — rotates at 5 MB, keeps 3 backups
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))

    root.addHandler(file_handler)
    root.addHandler(console_handler)


# Run on import so it takes effect before any other module logs
setup_logging()
