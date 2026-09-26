"""
pyvizion - Classe principal

    >>> from pyvizion import Vizion
    >>> vz = Vizion()
    >>> vz.click_image("menu.png", backtrack=True)
    >>> vz.click_text("Relatórios", backtrack=True)
    >>> vz.execute_tasks([{"image": "salvar.png"}, {"text": "OK", "sendtext": "{enter}"}])
"""

import logging
import time
from pathlib import Path

from ._context import Context
from .classic import ClassicMixin
from .config import Config
from .core import windows
from .core.highlight import highlight
from .core.screen import Region, as_region, save_screenshot
from .core.specs import Image, Text
from .settings import HIGHLIGHT_COLORS

logger = logging.getLogger("pyvizion")


class Vizion(ClassicMixin):
    """
    Automação de interface por visão (imagem + OCR).

    Args:
        config: ``dict`` com as chaves de configuração, caminho de um .json/.yaml
            ou um ``Config``. Ex.: ``{"confidence_threshold": 80, "tesseract_lang": "por"}``
    """

    _where = None

    def __init__(self, config=None):
        if isinstance(config, Config):
            cfg = Config(config.to_dict())
        elif isinstance(config, (str, Path)):
            cfg = Config.load(config)
        else:
            cfg = Config(config or {})
        self.config = cfg
        self._ctx = Context(cfg.to_settings())
        self._apply_log_level()
        cfg._on_change = self._reload

    def __repr__(self):
        return f"Vizion(config={self.config.to_dict()!r})"

    def _reload(self, cfg):
        session = getattr(self._ctx, "_classic_session", None)
        extracted = getattr(self._ctx, "last_extracted_text", None)
        self._ctx = Context(cfg.to_settings())
        self._ctx._classic_session = session
        self._ctx.last_extracted_text = extracted
        self._apply_log_level()

    def _apply_log_level(self):
        level = str(self.config.get("log_level", "INFO")).upper()
        logging.getLogger("pyvizion").setLevel(getattr(logging, level, logging.INFO))

    # ==================================================================
    # Overlay
    # ==================================================================
    @property
    def show_overlay(self):
        return bool(self.config.get("show_overlay"))

    @show_overlay.setter
    def show_overlay(self, value):
        self.config.set("show_overlay", bool(value))

    @property
    def overlay_enabled(self):
        return bool(self.config.get("overlay_enabled"))

    @overlay_enabled.setter
    def overlay_enabled(self, value):
        self.config.set("overlay_enabled", bool(value))

    def configure_overlay(self, enabled=None, color=None, duration=None, width=None):
        """Configura o retângulo desenhado sobre o alvo antes do clique.

        ``enabled``, ``color``, ``duration`` (ms) e ``width`` (px). Só altera
        o que for passado.
        """
        changes = {}
        if enabled is not None:
            changes.update(show_overlay=bool(enabled), overlay_enabled=bool(enabled))
        if color is not None:
            if str(color).lower() not in HIGHLIGHT_COLORS:
                raise ValueError(f"Cor '{color}' inválida. Opções: {', '.join(HIGHLIGHT_COLORS)}")
            changes["overlay_color"] = str(color).lower()
        for key, value in (("overlay_duration", duration), ("overlay_width", width)):
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                    raise ValueError(f"{key} deve ser um número positivo (recebido: {value!r})")
                changes[key] = int(value)
        if changes:
            self.config.update(changes)

    def get_overlay_config(self):
        """Configuração atual do overlay: enabled, cor, duração e largura."""
        c = self.config
        return {"enabled": c.overlay_enabled, "show_overlay": c.show_overlay,
                "color": c.overlay_color, "duration": c.overlay_duration, "width": c.overlay_width}

    @staticmethod
    def get_available_overlay_colors():
        """Nomes das cores aceitas em ``configure_overlay``."""
        return list(HIGHLIGHT_COLORS)

    def test_overlay_colors(self, duration=1500):
        """Mostra cada cor de overlay no centro da tela principal."""
        from .core.screen import primary_screen_size

        w, h = primary_screen_size()
        region = (w // 2 - 100, h // 2 - 50, 200, 100)
        for color in HIGHLIGHT_COLORS:
            logger.info(f"Overlay: {color}")
            highlight(region, color, 6, duration, wait=True)

    # ==================================================================
    # Alternativas
    # ==================================================================
    def find_any(self, targets, timeout=0, region=None, confidence=0.9):
        """
        Primeiro alvo encontrado dentre várias alternativas (caminhos de imagem e/ou textos).

        Returns:
            tuple: ``(índice, Region)`` ou ``(None, None)``
        """
        area = as_region(region) if region is not None else None
        specs = [Image(t, area, confidence) if _is_image(t) else Text(str(t), area) for t in targets]
        deadline = time.monotonic() + float(timeout or 0)
        while True:
            for index, spec in enumerate(specs):
                found = self._poll(spec, 1)
                if found is not None:
                    return index, found
            if time.monotonic() >= deadline:
                return None, None
            time.sleep(self._ctx.settings.retry_pause)

    def click_any(self, targets, timeout=0, region=None, confidence=0.9, delay=0,
                  mouse_button="left", sendtext=None, show_overlay=None):
        """Clica no primeiro alvo encontrado (imagem ou texto).

        Returns:
            índice do alvo clicado, ou ``None`` se nenhum apareceu.
        """
        index, found = self.find_any(targets, timeout, region, confidence)
        if found is None:
            self._missing("nenhuma das alternativas")
            return None
        self._act(found, mouse_button, delay, sendtext, show_overlay)
        return index

    # ==================================================================
    # Mouse e teclado
    # ==================================================================
    def press(self, key, presses=1, interval=0.05):
        """Pressiona uma tecla N vezes: ``press("tab", 3)``.

        Returns:
            sempre ``True``.
        """
        self._commander.press(key, presses, interval)
        return True

    def hotkey(self, *keys):
        """Atalho: ``hotkey("ctrl", "shift", "s")``.

        Returns:
            sempre ``True``.
        """
        self._commander.hotkey(*keys)
        return True

    def scroll(self, clicks, x=None, y=None):
        """Rola a roda do mouse (positivo = para cima).

        Se ``x`` e ``y`` forem passados, move o mouse até o ponto antes de rolar.

        Returns:
            sempre ``True``.
        """
        self._ctx.mouse.scroll(clicks, (x, y) if x is not None and y is not None else None)
        return True

    def drag(self, start, end, duration=0.5):
        """Arrasta de ``start`` para ``end``.

        Cada ponto é ``(x, y)`` ou uma região ``(x, y, largura, altura)``.

        Returns:
            sempre ``True``.
        """
        def point(p):
            return as_region(p).center if len(p) == 4 else (int(p[0]), int(p[1]))

        self._ctx.mouse.drag(point(start), point(end), duration)
        return True

    # ==================================================================
    # Janelas e tela
    # ==================================================================
    def focus_window(self, title, timeout=5):
        """Traz para frente a janela cujo título contém ``title``.

        Returns:
            ``True`` se achou e focou, ``False`` se o tempo acabar.
        """
        return windows.focus_window(title, timeout)

    def wait_window(self, title, timeout=30):
        """Espera uma janela com esse título existir.

        Returns:
            ``True`` se apareceu, ``False`` se o tempo acabar.
        """
        return windows.wait_window(title, timeout)

    def window_region(self, title):
        """Área da janela: ``(x, y, largura, altura)``. Use como ``region``.

        Returns:
            a caixa, ou ``None`` se a janela não existir.
        """
        rect = windows.window_rect(title)
        return Region(*rect) if rect else None

    def list_windows(self):
        """Títulos das janelas visíveis.

        Returns:
            lista de strings.
        """
        return [title for _, title in windows.list_windows()]

    def screenshot(self, path=None, region=None):
        """Salva um print da tela inteira ou de ``region``.

        Returns:
            caminho do arquivo.
        """
        return save_screenshot(path, as_region(region) if region is not None else None)


def _is_image(target):
    return not isinstance(target, str) or target.lower().endswith(
        (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"))
