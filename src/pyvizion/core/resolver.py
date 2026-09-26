"""
Vizion - Localizador: transforma alvos (Image, Text, Near, AnyOf, At) em regiões da tela.
"""

import logging
import math
import time

from ..exceptions import ImageFileError, InvalidArea
from . import windows
from .matcher import DEFAULT_NEAR_SCALES, ImageMatcher, wide_scales
from .reader import TextReader
from .screen import Region, as_region, grab_screen, monitor_scales, normalize_region, virtual_screen_bounds
from .specs import AnyOf, At, Image, Near, Target, Text, as_target

logger = logging.getLogger(__name__)


class Resolver:
    def __init__(self, settings, reader=None):
        self.settings = settings
        self.matcher = ImageMatcher(grayscale=settings.grayscale, image_dirs=settings.image_dirs)
        self.reader = reader or TextReader(settings)
        self.last_choice = None  # índice escolhido no último AnyOf

    # ------------------------------------------------------------------
    # Áreas
    # ------------------------------------------------------------------
    def area(self, area):
        """Tupla/Region/título de janela -> Region (ou None = tela inteira)."""
        if area is None:
            return None
        if isinstance(area, str):
            rect = windows.window_rect(area)
            if rect is None:
                from ..exceptions import WindowNotFound

                titles = " | ".join(t for _, t in windows.list_windows()[:15])
                raise WindowNotFound(f"Janela '{area}' não encontrada"
                                     + (f"\n  janelas abertas: {titles}" if titles else ""))
            return normalize_region(rect)
        if isinstance(area, Target):
            found = self.find_once(area)
            if found is None:
                raise InvalidArea(f"Área {area.label()} não encontrada na tela")
            return found
        return normalize_region(as_region(area))

    # ------------------------------------------------------------------
    # Busca
    # ------------------------------------------------------------------
    def find(self, target, timeout=None, attempts=None):
        """Procura até achar, esgotar as tentativas e o tempo. Retorna Region ou None."""
        target = as_target(target)
        timeout = self.settings.timeout if timeout is None else float(timeout)
        attempts = max(1, int(attempts or 1))
        deadline = time.monotonic() + max(0.0, timeout)
        attempt = 0
        while True:
            found = self.find_once(target, attempt)
            if found is not None:
                return found
            attempt += 1
            if attempt >= attempts and time.monotonic() >= deadline:
                return None
            time.sleep(self.settings.retry_pause)

    def find_once(self, target, attempt=0):
        target = as_target(target)
        if isinstance(target, At):
            return Region(target.x, target.y, 1, 1)
        if isinstance(target, Image):
            return self._image(target, attempt)
        if isinstance(target, Text):
            hits = self._text_hits(target)
            if not hits:
                return None
            if target.nth:
                return hits[target.nth - 1][0] if len(hits) >= target.nth else None
            return max(hits, key=lambda h: h[1])[0]
        if isinstance(target, Near):
            return self._near(target, attempt)
        if isinstance(target, AnyOf):
            for index, option in enumerate(target.options):
                found = self.find_once(option, attempt)
                if found is not None:
                    self.last_choice = index
                    return found
            return None
        raise TypeError(f"Alvo não suportado: {target!r}")

    def find_all(self, target):
        """Todas as ocorrências de uma imagem ou texto, em ordem de leitura."""
        target = as_target(target)
        if isinstance(target, Image):
            area = self.area(target.area)
            matches = self.matcher.all_on_screen(
                target.source, area, self._precision(target, 0), self._scales(target, area),
                grayscale=not target.color)
            return _reading_order([m.region for m in matches])
        if isinstance(target, Text):
            return [region for region, _ in self._text_hits(target, want=50)]
        if isinstance(target, AnyOf):
            return [r for option in target.options for r in self.find_all(option)]
        found = self.find_once(target)
        return [found] if found else []

    def wait_gone(self, target, timeout=10.0):
        target = as_target(target)
        deadline = time.monotonic() + max(0.0, float(timeout))
        while True:
            try:
                present = self.find_once(target) is not None
            except ImageFileError:
                raise
            if not present:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(self.settings.retry_pause)

    # ------------------------------------------------------------------
    # Imagens
    # ------------------------------------------------------------------
    def _precision(self, target, attempt):
        wanted = float(target.precision or self.settings.precision)
        floor = min(float(self.settings.min_precision), wanted)
        return max(floor, wanted - 0.05 * attempt)

    def _scales(self, target, area):
        if target.scales:
            base = target.scales
        else:
            base = wide_scales(self.settings) if target.flexible else DEFAULT_NEAR_SCALES
        if not self.settings.monitor_scaling:
            return tuple(base)
        extra = []
        for factor in monitor_scales(area):
            if abs(factor - 1.0) < 0.01:
                continue
            for value in (factor, factor * 0.95, factor * 1.05, 1.0 / factor):
                value = round(value, 3)
                if all(abs(value - s) > 0.02 for s in list(base) + extra):
                    extra.append(value)
        return tuple(base) + tuple(extra)

    def _image(self, target, attempt):
        area = self.area(target.area)
        areas = [area, None] if (target.flexible and area is not None) else [area]
        precision = self._precision(target, attempt)
        for where in areas:
            match = self.matcher.on_screen(
                target.source, where, precision, self._scales(target, where),
                edge_fallback=self.settings.edge_matching, grayscale=not target.color)
            if match:
                logger.debug(f"{target.label()} em {tuple(match.region)} "
                             f"(semelhança {match.score:.3f}, escala {match.scale})")
                return match.region
        return None

    # ------------------------------------------------------------------
    # Texto
    # ------------------------------------------------------------------
    def _text_hits(self, target, want=None):
        area = self.area(target.area)
        img, origin = grab_screen(area)
        hits, _ = self.reader.find(img, target.value, target.kind, target.confidence,
                                   want or target.nth or 1, target.exact)
        return [(Region(origin[0] + h.box[0], origin[1] + h.box[1], h.box[2], h.box[3]), h.confidence)
                for h in hits]

    # ------------------------------------------------------------------
    # Âncora + alvo
    # ------------------------------------------------------------------
    def _near(self, target, attempt):
        anchor = self.find_once(target.anchor, attempt)
        if anchor is None:
            logger.debug(f"Âncora {target.anchor.label()} não encontrada")
            return None
        c = anchor.center
        if target.area is not None:
            search = self.area(target.area)
        else:
            margin = target.radius + 200
            try:
                search = normalize_region((c.x - margin, c.y - margin, 2 * margin, 2 * margin))
            except InvalidArea:
                search = virtual_screen_bounds()

        inner = target.target
        if isinstance(inner, Image):
            candidates = [m.region for m in self.matcher.all_on_screen(
                inner.source, search, self._precision(inner, attempt), self._scales(inner, search),
                grayscale=not inner.color)]
        elif isinstance(inner, Text):
            scoped = Text(inner.value, search, inner.kind, None, inner.confidence, inner.exact)
            candidates = [r for r, _ in self._text_hits(scoped, want=20)]
        else:
            found = self.find_once(inner, attempt)
            candidates = [found] if found else []

        best, best_distance = None, float("inf")
        for region in candidates:
            if _overlap(region, anchor) > 0.6:
                continue  # é a própria âncora
            p = region.center
            distance = math.hypot(p.x - c.x, p.y - c.y)
            if distance <= target.radius and distance < best_distance:
                best, best_distance = region, distance
        return best


def _overlap(a, b):
    ix = max(0, min(a.right, b.right) - max(a.x, b.x))
    iy = max(0, min(a.bottom, b.bottom) - max(a.y, b.y))
    smaller = min(a.width * a.height, b.width * b.height) or 1
    return ix * iy / smaller


def _reading_order(regions):
    return sorted(regions, key=lambda r: (r.y // max(1, r.height // 2 or 1), r.x))
