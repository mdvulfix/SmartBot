
import logging
from logging.handlers import RotatingFileHandler

class Logger():
    def __init__(self):
        self._manager = logging.getLogger("SmartBot_v1")
        self._formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        self._steam_handler = logging.StreamHandler()
        self._file_handler = RotatingFileHandler("SmartBot_v1.log", maxBytes=5 * 1024 * 1024, backupCount=3)
        self.configure()
 
    def configure(self):
        self._manager.setLevel(logging.INFO)
        self._steam_handler.setFormatter(self._formatter)
        self._manager.addHandler(self._steam_handler)
        self._file_handler.setFormatter(self._formatter)
        self._manager.addHandler(self._file_handler) 

    def manager(self):
        return self._manager