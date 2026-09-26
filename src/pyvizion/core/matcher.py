"""
Vizion - Busca de imagens na tela

Template matching OpenCV em memória (sem arquivos temporários):

- várias escalas (independência de resolução/DPI/zoom), sem gravar arquivos;
- tons de cinza por padrão (tolera pequenas variações de cor/hover/seleção);
- fallback opcional por bordas (Canny) para mudança de tema claro/escuro;
- ``all_in_image``/``all_on_screen`` com supressão de duplicatas (NMS) para âncora + alvo.
"""

import logging

import cv2
import numpy as np

from ..exceptions import ActionError
from .screen import Region, grab_screen, load_image, pil_to_bgr

logger = logging.getLogger(__name__)

DEFAULT_WIDE_SCALES = tuple(round(0.80 + i * 0.05, 2) for i in range(9))  # 0.80 … 1.20
DEFAULT_NEAR_SCALES = (1.0, 0.95, 1.05)


class Match:
    """Resultado de um matching: caixa em coordenadas de tela + score."""

    __slots__ = ("region", "score", "scale", "method")

    def __init__(self, region, score, scale=1.0, method="template"):
        self.region = region
        self.score = float(score)
        self.scale = float(scale)
        self.method = method

    def __repr__(self):
        return f"Match(region={tuple(self.region)}, score={self.score:.3f}, scale={self.scale}, method='{self.method}')"


class ImageMatcher:
    """
    Motor de template matching multi-escala.

    Examples:
        >>> matcher = ImageMatcher()
        >>> m = matcher.on_screen("botao.png", precision=0.9)
        >>> if m: print(m.region, m.score)
    """

    def __init__(self, grayscale=True, image_dirs=()):
        self.grayscale = grayscale
        self.image_dirs = list(image_dirs or [])

    # ------------------------------------------------------------------
    # API de tela
    # ------------------------------------------------------------------
    def on_screen(
        self,
        image,
        region=None,
        precision=0.9,
        scales=DEFAULT_NEAR_SCALES,
        edge_fallback=False,
        grayscale=None,
    ):
        """Melhor ocorrência da imagem na tela (ou região). Retorna ``Match`` ou None."""
        shot, origin = grab_screen(region)
        return self.in_image(
            image, shot, precision, scales, origin=origin, edge_fallback=edge_fallback, grayscale=grayscale
        )

    def all_on_screen(
        self, image, region=None, precision=0.9, scales=DEFAULT_NEAR_SCALES, max_results=50, grayscale=None
    ):
        """Todas as ocorrências (sem duplicatas), ordenadas por score."""
        shot, origin = grab_screen(region)
        return self.all_in_image(
            image, shot, precision, scales, origin=origin, max_results=max_results, grayscale=grayscale
        )

    # ------------------------------------------------------------------
    # API de imagem (testável sem tela)
    # ------------------------------------------------------------------
    def in_image(
        self,
        needle,
        haystack,
        precision=0.9,
        scales=DEFAULT_NEAR_SCALES,
        origin=(0, 0),
        edge_fallback=False,
        grayscale=None,
    ):
        scene, template = self._prepare(haystack, needle, grayscale)
        best = self._best(scene, template, scales)
        if best is not None and best[0] >= precision:
            return self._to_match(best, origin, "template")

        if edge_fallback:
            scene_e = cv2.Canny(_gray(scene), 50, 150)
            template_e = cv2.Canny(_gray(template), 50, 150)
            if scene_e.any() and template_e.any():
                edge_best = self._best(scene_e, template_e, scales)
                # Bordas geram scores menores; exige um mínimo fixo alto.
                if edge_best is not None and edge_best[0] >= max(0.6, precision - 0.2):
                    return self._to_match(edge_best, origin, "edges")
        return None

    def all_in_image(
        self,
        needle,
        haystack,
        precision=0.9,
        scales=DEFAULT_NEAR_SCALES,
        origin=(0, 0),
        max_results=50,
        grayscale=None,
    ):
        scene, template = self._prepare(haystack, needle, grayscale)
        candidates = []
        for scale in _ordered(scales):
            resized, result = self._score_map(scene, template, scale)
            if result is None:
                continue
            ys, xs = np.where(result >= precision)
            if len(xs) > 5000:  # template uniforme demais; evita explosão
                order = np.argsort(result[ys, xs])[::-1][:5000]
                ys, xs = ys[order], xs[order]
            h, w = resized.shape[:2]
            for y, x in zip(ys.tolist(), xs.tolist()):
                candidates.append((float(result[y, x]), x, y, w, h, scale))
        candidates.sort(key=lambda c: c[0], reverse=True)
        kept = []
        for cand in candidates:
            if all(_iou(cand, other) < 0.3 for other in kept):
                kept.append(cand)
                if len(kept) >= max_results:
                    break
        return [self._to_match(c, origin, "template") for c in kept]

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _prepare(self, haystack, needle, grayscale):
        use_gray = self.grayscale if grayscale is None else grayscale
        scene = pil_to_bgr(haystack) if hasattr(haystack, "mode") else load_image(haystack)
        template = load_image(needle, self.image_dirs)
        if use_gray:
            return _gray(scene), _gray(template)
        return scene, template

    def _best(self, scene, template, scales):
        best = None
        for scale in _ordered(scales):
            resized, result = self._score_map(scene, template, scale)
            if result is None:
                continue
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if best is None or max_val > best[0]:
                h, w = resized.shape[:2]
                best = (float(max_val), max_loc[0], max_loc[1], w, h, scale)
                if max_val >= 0.99:
                    break
        return best

    @staticmethod
    def _score_map(scene, template, scale):
        th, tw = template.shape[:2]
        w, h = int(round(tw * scale)), int(round(th * scale))
        if w < 3 or h < 3 or h > scene.shape[0] or w > scene.shape[1]:
            return None, None
        if scale == 1.0:
            resized = template
        else:
            interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
            resized = cv2.resize(template, (w, h), interpolation=interp)
        try:
            if _flat(resized):
                # Template de cor sólida: correlação não tem significado (dá 1.0 em
                # qualquer área lisa). Usa a diferença de cor normalizada.
                sq = cv2.matchTemplate(scene.astype(np.float32), resized.astype(np.float32), cv2.TM_SQDIFF)
                result = 1.0 - sq / float(resized.size * 255.0 * 255.0)
                result = 1.0 - np.sqrt(np.clip(1.0 - result, 0.0, 1.0))
            else:
                result = cv2.matchTemplate(scene, resized, cv2.TM_CCOEFF_NORMED)
        except cv2.error as e:
            raise ActionError(f"Falha no template matching: {e}")
        # Templates de cor sólida geram NaN/inf em CCOEFF_NORMED.
        result = np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)
        return resized, result

    @staticmethod
    def _to_match(cand, origin, method):
        score, x, y, w, h, scale = cand
        region = Region(int(x) + int(origin[0]), int(y) + int(origin[1]), int(w), int(h))
        return Match(region, score, scale, method)


def _flat(img):
    """True se o template é praticamente uma cor sólida (em todos os canais)."""
    channels = 1 if img.ndim == 2 else img.shape[2]
    return float(img.reshape(-1, channels).std(axis=0).max()) < 2.0


def _gray(img):
    if img.ndim == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _ordered(scales):
    """Escala 1.0 primeiro (caso mais comum e mais barato)."""
    items = [float(s) for s in (scales or (1.0,))]
    if 1.0 in items:
        items.remove(1.0)
        items.insert(0, 1.0)
    return items


def _iou(a, b):
    _, ax, ay, aw, ah, _ = a
    _, bx, by, bw, bh, _ = b
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    return inter / float(aw * ah + bw * bh - inter)


def wide_scales(settings=None):
    """Escalas usadas em ``Image(flexible=True)``."""
    scales = getattr(settings, "scales", None)
    return tuple(scales) if scales else DEFAULT_WIDE_SCALES
