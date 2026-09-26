"""Estado compartilhado pelos métodos (interno)."""

import logging
import os
import time

from .core.mouse import Mouse
from .core.resolver import Resolver
from .core.screen import enable_dpi_awareness, save_screenshot

logger = logging.getLogger("pyvizion")


class Context:
    def __init__(self, settings):
        enable_dpi_awareness()
        self.settings = settings
        from .core import tesseract

        tesseract.locate(settings.tesseract)
        self.resolver = Resolver(settings)
        self.reader = self.resolver.reader
        self.mouse = Mouse(settings)

    def failure_shot(self, name):
        if not self.settings.failure_shots:
            return None
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(name))[:60].strip("_")
        path = os.path.join(self.settings.failure_dir, f"{time.strftime('%Y%m%d_%H%M%S')}_{safe}.png")
        try:
            path = os.path.abspath(save_screenshot(path))
            logger.info(f"Print da falha: {path}")
            return path
        except Exception as e:
            logger.debug(f"Não foi possível salvar o print da falha: {e}")
            return None
