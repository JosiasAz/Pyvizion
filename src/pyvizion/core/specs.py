"""
Vizion - Alvos

Um alvo descreve *o que* procurar na tela. Todas as ações (``click``, ``find``,
``wait``...) aceitam um alvo — ou um atalho que vira alvo automaticamente:

    "salvar.png"                 -> Image("salvar.png")      (termina com extensão de imagem)
    "Confirmar"                  -> Text("Confirmar")
    ["ok_v1.png", "OK"]          -> AnyOf(Image("ok_v1.png"), Text("OK"))
    (500, 300)                   -> At(500, 300)

Onde procurar (``area``): uma tupla ``(x, y, largura, altura)``, uma ``Region``
ou o **título de uma janela** (``area="Oracle Applications"``).
"""

import os
from pathlib import Path

from ..exceptions import SettingsError
from .text import check_kind

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp")


class Target:
    """Base de todos os alvos."""

    area = None

    def label(self) -> str:
        return repr(self)


class Image(Target):
    """
    Uma imagem (recorte PNG da tela).

    Args:
        source: caminho do arquivo, ``PIL.Image`` ou array NumPy
        area: onde procurar (tupla, Region ou título de janela)
        precision: semelhança mínima 0–1 (padrão: ``Settings.precision``)
        flexible: se não achar na área, procura na tela inteira e em escalas 0.8–1.2
        scales: escalas específicas a testar
        color: compara em cores (padrão: tons de cinza)
    """

    def __init__(self, source, area=None, precision=None, flexible=False, scales=None, color=False):
        self.source = source
        self.area = area
        self.precision = precision
        self.flexible = flexible
        self.scales = tuple(scales) if scales else None
        self.color = color

    def label(self):
        if isinstance(self.source, (str, os.PathLike)):
            return os.path.basename(str(self.source))
        return f"<{type(self.source).__name__}>"

    def __repr__(self):
        return f"Image({self.label()!r})"


class Text(Target):
    """
    Um texto na tela (lido por OCR).

    Args:
        value: palavra ou frase
        area: onde procurar (recomendado: bem mais rápido e preciso)
        kind: ``"text"`` (letras e dígitos), ``"letters"``, ``"digits"`` ou ``"any"``
        nth: qual ocorrência em ordem de leitura (1 = primeira); padrão: a mais nítida
        confidence: confiança mínima 0–100 (padrão: ``Settings.text_confidence``)
        exact: desliga a leitura aproximada
    """

    def __init__(self, value, area=None, kind="text", nth=None, confidence=None, exact=False):
        if not str(value).strip():
            raise SettingsError("Text precisa de um valor")
        self.value = str(value)
        self.area = area
        self.kind = check_kind(kind)
        self.nth = int(nth) if nth else None
        self.confidence = confidence
        self.exact = exact

    def label(self):
        return self.value

    def __repr__(self):
        return f"Text({self.value!r})"


class Near(Target):
    """
    O alvo mais próximo de uma âncora — para quando o mesmo botão aparece várias
    vezes (lupas, "Editar" em cada linha de uma grade...).

        Near("lupa.png", anchor="Cliente")               # lupa ao lado do rótulo
        Near("editar.png", anchor="linha_0042.png", radius=300)
    """

    def __init__(self, target, anchor, radius=200, area=None):
        self.target = as_target(target)
        self.anchor = as_target(anchor)
        self.radius = int(radius)
        self.area = area

    def label(self):
        return f"{self.target.label()} perto de {self.anchor.label()}"

    def __repr__(self):
        return f"Near({self.target!r}, anchor={self.anchor!r}, radius={self.radius})"


class AnyOf(Target):
    """O primeiro que aparecer dentre várias alternativas (versões diferentes da tela)."""

    def __init__(self, *options):
        if len(options) == 1 and isinstance(options[0], (list, tuple)):
            options = tuple(options[0])
        if not options:
            raise SettingsError("AnyOf precisa de pelo menos uma opção")
        self.options = [as_target(o) for o in options]

    def label(self):
        return " | ".join(o.label() for o in self.options)

    def __repr__(self):
        return f"AnyOf({', '.join(map(repr, self.options))})"


class At(Target):
    """Uma posição fixa da tela."""

    def __init__(self, x, y):
        self.x, self.y = int(x), int(y)

    def label(self):
        return f"({self.x}, {self.y})"

    def __repr__(self):
        return f"At({self.x}, {self.y})"


def _looks_like_image(value) -> bool:
    return str(value).lower().endswith(IMAGE_EXTENSIONS)


def as_target(value, **options) -> Target:
    """
    Converte atalhos em alvos. ``options`` (area, precision, kind, nth...) são
    aplicadas quando o atalho é convertido.
    """
    if isinstance(value, Target):
        return value
    if isinstance(value, Path) or (isinstance(value, str) and _looks_like_image(value)):
        return Image(value, **_pick(options, "area", "precision", "flexible", "scales", "color"))
    if isinstance(value, str):
        return Text(value, **_pick(options, "area", "kind", "nth", "confidence", "exact"))
    if isinstance(value, dict):
        return _from_dict(value, options)
    if isinstance(value, tuple) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value):
        return At(*value)
    if isinstance(value, (list, tuple)):
        return AnyOf(*[as_target(v, **options) for v in value])
    if hasattr(value, "shape") or hasattr(value, "mode"):  # ndarray / PIL
        return Image(value, **_pick(options, "area", "precision", "flexible", "scales", "color"))
    raise SettingsError(f"Não sei procurar por {value!r}")


def _pick(options, *names):
    return {k: options[k] for k in names if options.get(k) is not None}


def _from_dict(spec, options):
    spec = {**options, **spec}
    if "near" in spec:
        return Near(as_target(spec["target"], **_rest(spec, "near", "target", "radius")),
                    as_target(spec["near"]), spec.get("radius", 200))
    if "any" in spec:
        return AnyOf(*[as_target(v, **_rest(spec, "any")) for v in spec["any"]])
    if "image" in spec:
        return as_target(Path(spec["image"]) if isinstance(spec["image"], str) else spec["image"],
                         **_rest(spec, "image"))
    if "text" in spec:
        return Text(spec["text"], **_pick(spec, "area", "kind", "nth", "confidence", "exact"))
    if "x" in spec and "y" in spec:
        return At(spec["x"], spec["y"])
    raise SettingsError(f"Alvo inválido: {spec!r} (use image, text, near, any ou x/y)")


def _rest(spec, *drop):
    return {k: v for k, v in spec.items() if k not in drop}
