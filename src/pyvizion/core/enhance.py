"""
Vizion - Pré-processamento de imagem para OCR

Gera versões da captura que destacam o texto em situações comuns de telas
corporativas antigas: fundo colorido, degradê, texto claro sobre escuro,
fontes pequenas/serrilhadas, ruído de compressão (Citrix/RDP).

Técnicas (``ALL_METHODS``, em ordem de prioridade):

- ``original``        tons de cinza, invertido automaticamente se o fundo for escuro
- ``otsu``            binarização global automática (Otsu)
- ``color_distance``  distância de cada pixel à cor de fundo predominante
- ``clahe``           equalização local de contraste + Otsu
- ``max_channel``     maior canal RGB (texto colorido sobre fundo claro)
- ``adaptive``        limiar adaptativo (iluminação/degradê irregular)
- ``sharpen``         máscara de nitidez (unsharp mask) para fontes borradas
- ``tophat``          realce morfológico de traços finos sobre fundo irregular
- ``denoise``         filtro de mediana + Otsu (artefatos de compressão)

Qualidades: ``"fast"``, ``"balanced"`` e ``"all"``.
"""

import logging
from typing import List, Union

import cv2
import numpy as np
from PIL import Image

from ..exceptions import SettingsError

logger = logging.getLogger(__name__)

ALL_METHODS = [
    "original",
    "otsu",
    "color_distance",
    "clahe",
    "max_channel",
    "adaptive",
    "sharpen",
    "tophat",
    "denoise",
]

QUALITIES = {
    "all": ALL_METHODS,
    "balanced": ["original", "otsu", "color_distance", "clahe", "adaptive", "sharpen"],
    "fast": ["original", "color_distance", "clahe"],
}


def _polarity(gray: np.ndarray) -> np.ndarray:
    """Garante texto escuro sobre fundo claro (o que o Tesseract prefere)."""
    return 255 - gray if float(np.median(gray)) < 110 else gray


def _otsu(gray: np.ndarray) -> np.ndarray:
    _, out = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Otsu não sabe qual lado é texto: a maioria dos pixels é fundo -> branco.
    if np.count_nonzero(out) < out.size / 2:
        out = 255 - out
    return out


def _background_color(rgb: np.ndarray) -> np.ndarray:
    """Cor mais frequente da imagem (quantizada), usada como fundo."""
    quant = (rgb // 16).reshape(-1, 3).astype(np.int32)
    keys = quant[:, 0] * 256 + quant[:, 1] * 16 + quant[:, 2]
    dominant = np.bincount(keys).argmax()
    return rgb.reshape(-1, 3)[keys == dominant].mean(axis=0)


class Enhancer:
    """
    Processador de imagens para OCR.

    Examples:
        >>> variants = Enhancer("balanced").variants(Image.open("tela.png"))
    """

    def __init__(self, methods: Union[str, List[str]] = "all"):
        self.methods = methods
        self.available_methods = list(ALL_METHODS)

    def _selected(self, methods=None):
        methods = self.methods if methods is None else methods
        if isinstance(methods, str):
            if methods.lower() not in QUALITIES:
                raise SettingsError(
                    f"Qualidade de OCR inválida '{methods}'. Use: {', '.join(QUALITIES)}"
                )
            return list(QUALITIES[methods.lower()])
        unknown = [m for m in methods if m not in ALL_METHODS]
        if unknown:
            raise SettingsError(f"Métodos desconhecidos: {unknown}. Disponíveis: {ALL_METHODS}")
        return [m for m in ALL_METHODS if m in methods]

    @staticmethod
    def upscale(img: Image.Image, factor: float) -> Image.Image:
        """Amplia a imagem — o Tesseract rende muito melhor com letras de 20px ou mais."""
        if not factor or factor <= 1.0:
            return img
        return img.resize((int(img.width * factor), int(img.height * factor)), Image.LANCZOS)

    def variants(self, img: Image.Image, methods=None) -> List[Image.Image]:
        """
        Gera as variações para OCR, na ordem de prioridade.

        Returns:
            list[PIL.Image]: imagens em tons de cinza (modo 'L').
        """
        try:
            selected = self._selected(methods)
            rgb = np.array(img.convert("RGB"))
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            out = []
            for name in selected:
                result = getattr(self, f"_m_{name}")(rgb, gray)
                if result is not None:
                    out.append(Image.fromarray(result))
            logger.debug(f"{len(out)} variações de pré-processamento geradas")
            return out
        except SettingsError:
            raise
        except Exception as e:
            logger.debug(f"Falha no pré-processamento: {e}")
            return [Image.fromarray(_polarity(np.array(img.convert("L"))))]

    # --- técnicas ------------------------------------------------------
    @staticmethod
    def _m_original(rgb, gray):
        return _polarity(gray)

    @staticmethod
    def _m_otsu(rgb, gray):
        return _otsu(gray)

    @staticmethod
    def _m_color_distance(rgb, gray):
        bg = _background_color(rgb)
        dist = np.linalg.norm(rgb.astype(np.float32) - bg, axis=2)
        peak = float(dist.max())
        if peak < 1.0:
            return None
        dist = (dist * (255.0 / peak)).astype(np.uint8)
        return _otsu(255 - dist)

    @staticmethod
    def _m_clahe(rgb, gray):
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
        return _otsu(clahe.apply(_polarity(gray)))

    @staticmethod
    def _m_max_channel(rgb, gray):
        return _polarity(rgb.max(axis=2).astype(np.uint8))

    @staticmethod
    def _m_adaptive(rgb, gray):
        block = max(15, (min(gray.shape[:2]) // 8) | 1)
        return cv2.adaptiveThreshold(_polarity(gray), 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, block, 10)

    @staticmethod
    def _m_sharpen(rgb, gray):
        base = _polarity(gray)
        blur = cv2.GaussianBlur(base, (0, 0), 1.2)
        return cv2.addWeighted(base, 1.8, blur, -0.8, 0)

    @staticmethod
    def _m_tophat(rgb, gray):
        base = _polarity(gray)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        strokes = cv2.morphologyEx(base, cv2.MORPH_BLACKHAT, kernel)
        return _otsu(255 - strokes)

    @staticmethod
    def _m_denoise(rgb, gray):
        return _otsu(cv2.medianBlur(_polarity(gray), 3))
