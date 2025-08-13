####################
### utils/logger.py
####################

"""Настройка логгера для всего проекта"""
import logging
from logging.handlers import RotatingFileHandler

def get_logger(name: str) -> logging.Logger:
    
    """Создает и настраивает логгер с консольным и файловым выводом"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        f"{name}.log", maxBytes=5 * 1024 * 1024, backupCount=3
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger
