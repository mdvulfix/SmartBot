# === file: utils.py ===
import logging

from logging import Logger
from logging.handlers import RotatingFileHandler

class Utils:
    @staticmethod
    def get_logger(name) -> Logger:

        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        file_handler = RotatingFileHandler(f"{name}.log", maxBytes=5 * 1024 * 1024, backupCount=3)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        return logger
    
    def __new__(cls, *args, **kwargs):
        raise TypeError("This class cannot be instantiated")