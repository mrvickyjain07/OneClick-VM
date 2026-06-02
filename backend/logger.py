import logging
import logging.handlers
import os
from . import config

def get_logger(name="OneClickVM"):
    """
    Configure and return a logger instance with rotating file handler.
    Logs are saved to logs/app.log.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid adding handlers multiple times
    if logger.hasHandlers():
        return logger

    # Ensure log directory exists
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = config.LOG_DIR / "app.log"

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # File Handler (Rotating)
    # 5MB = 5 * 1024 * 1024 bytes
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
