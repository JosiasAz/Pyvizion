"""
Vizion - Normalização de texto para comparação tolerante

Tipos de conteúdo (``kind``):

- ``"text"``     letras e dígitos (padrão)
- ``"letters"``  só letras (qualquer alfabeto, com acentos)
- ``"digits"``   só dígitos
- ``"any"``      qualquer coisa (só remove pontuação das pontas)
"""

import string
import unicodedata
from difflib import SequenceMatcher

KINDS = ("text", "letters", "digits", "any")

_EDGES = string.punctuation + string.whitespace + "“”‘’«»–—…·•"
_KEEP = {"text": str.isalnum, "letters": str.isalpha, "digits": str.isdigit}

# Confusões clássicas do OCR em telas de sistemas legados.
_TO_DIGITS = str.maketrans({
    "O": "0", "o": "0", "Q": "0", "D": "0",
    "I": "1", "l": "1", "|": "1", "i": "1", "!": "1",
    "Z": "2", "z": "2", "S": "5", "s": "5", "G": "6", "b": "6",
    "T": "7", "B": "8", "g": "9", "q": "9",
})
_TO_LETTERS = str.maketrans({"0": "o", "1": "l", "5": "s", "8": "b", "|": "l", "$": "s", "@": "a"})


def check_kind(kind: str) -> str:
    kind = (kind or "text").lower()
    if kind not in KINDS:
        from ..exceptions import SettingsError

        raise SettingsError(f"kind deve ser um de {KINDS} (recebido: {kind!r})")
    return kind


def clean(text: str, kind: str = "text") -> str:
    """Mantém apenas os caracteres do tipo pedido."""
    if not isinstance(text, str):
        return ""
    keep = _KEEP.get(kind)
    if keep is None:
        return text.strip(_EDGES)
    return "".join(ch for ch in text if keep(ch))


def strip_accents(text: str) -> str:
    """'Usuário' -> 'Usuario'."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def fix_lookalikes(text: str, kind: str) -> str:
    """Corrige confusões do OCR conforme o tipo esperado (dígitos ou letras)."""
    if kind == "digits":
        return text.translate(_TO_DIGITS)
    if kind == "letters":
        return text.translate(_TO_LETTERS)
    return text


def normalize(text: str, kind: str = "text", fix: bool = False) -> str:
    """Token pronto para comparar: (confusões) → filtro → sem acentos → minúsculo."""
    if not isinstance(text, str):
        return ""
    if fix:
        text = fix_lookalikes(text, kind)
    return strip_accents(clean(text, kind)).casefold()


def similarity(a: str, b: str) -> float:
    """Similaridade 0.0–1.0."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()
