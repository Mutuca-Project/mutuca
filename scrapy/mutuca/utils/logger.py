import logging
import sys
from typing import Any, Dict, Optional

from pythonjsonlogger.jsonlogger import JsonFormatter


class Logger:
    """Logger estruturado para os pipelines de dados"""

    def __init__(self, name: str, level: str = "INFO") -> None:
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))

        if not self.logger.handlers:
            self._setup_handler()

    def _setup_handler(
        self,
    ):
        """Configura handler com forato JSON"""
        handler = logging.StreamHandler(sys.stdout)
        formatter = JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s")
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def info(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log de informação"""
        self.logger.info(message, extra=extra or {})

    def error(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log de erro"""
        self.logger.error(message, extra=extra or {})

    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log de erro"""
        self.logger.warning(message, extra=extra or {})


def get_logger(name: str) -> Logger:
    """Factory para crição de logs estruturados"""
    return Logger(name)
