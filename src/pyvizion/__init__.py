"""
pyvizion — biblioteca Python para automação de interface por imagem e texto.

    >>> from pyvizion import Vizion
    >>> bot = Vizion()
    >>> bot.click_image("button1.png", backtrack=True)
    >>> bot.click_text("Save", backtrack=True)  # precisa de Tesseract
    >>> bot.execute_tasks([{"image": "ok.png"}, {"text": "Fechar"}])

Núcleo do dia a dia (comece por aqui)::

    click_image, find_image, click_text, find_text, type_text,
    wait_for_image, wait_for_text, focus_window, execute_tasks, doctor

O restante da API é avançado ou legado.
Tesseract só é exigido em operações de texto/OCR — não na criação do ``Vizion``.
"""

import logging
import warnings

# Antes de tudo: modo DPI por monitor (outras libs de GUI fixariam o modo "sistema").
from .core.screen import enable_dpi_awareness as _enable_dpi_awareness

_enable_dpi_awareness()

from .classic import TaskResult, clean_text, limpar_texto
from .config import Config
from .core.screen import Point, Region
from .exceptions import (
    ActionError,
    ConfigurationError,
    ImageFileError,
    ImageNotFoundError,
    ImageProcessingError,
    InvalidArea,
    InvalidRegionError,
    OCRProcessingError,
    OCRUnavailable,
    SettingsError,
    TargetNotFound,
    TaskExecutionError,
    TesseractNotFoundError,
    TextNotFoundError,
    VizionError,
    WindowNotFound,
)
from .vizion import Vizion

__version__ = "1.0.9"
__author__ = "Josias Azevedo da Silva"


class _SafeStreamHandler(logging.StreamHandler):
    """Não quebra em consoles legados (cp1252/cp850): troca o que não couber por '?'."""

    def emit(self, record):
        try:
            msg = self.format(record)
            encoding = getattr(self.stream, "encoding", None) or "utf-8"
            self.stream.write(msg.encode(encoding, errors="replace").decode(encoding, errors="replace")
                              + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


def _setup_logging():
    lib = logging.getLogger("pyvizion")
    if not lib.handlers and not logging.getLogger().handlers:
        handler = _SafeStreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [pyvizion] %(message)s", "%H:%M:%S"))
        lib.addHandler(handler)
        lib.setLevel(logging.INFO)
        lib.propagate = False


_setup_logging()


# ---------------------------------------------------------------------------
# Funções clássicas sem instância (usam um Vizion padrão, criado na 1ª chamada)
# ---------------------------------------------------------------------------

_DEFAULT = None


def _default():
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Vizion()
    return _DEFAULT


def _classic(name):
    import functools

    method = getattr(Vizion, name)

    @functools.wraps(method)
    def function(*args, **kwargs):
        return getattr(_default(), name)(*args, **kwargs)

    import inspect

    sig = inspect.signature(method)
    function.__signature__ = sig.replace(parameters=list(sig.parameters.values())[1:])
    function.__qualname__ = name
    return function


_CLASSIC_FUNCTIONS = [
    "find_image", "click_image", "find_all_images", "image_exists",
    "find_text", "click_text", "text_exists", "read_text",
    "extract_text_from_region", "get_last_extracted_text",
    "find_relative_image", "click_relative_image", "click_image_near_text",
    "click_at", "click_coordinates", "type_text", "keyboard_command",
    "get_available_keyboard_commands", "wait_for_image", "wait_for_text", "wait_until_gone",
    "click_any", "find_any", "focus_window", "wait_window", "window_region", "screenshot",
    "execute_tasks", "execute_with_backtrack_between_tasks",
    "start_task_session", "end_task_session",
    "configure_overlay", "get_overlay_config", "get_available_overlay_colors",
    "test_overlay_colors",
]
for _name in _CLASSIC_FUNCTIONS:
    globals()[_name] = _classic(_name)
del _name


def doctor():
    """Diagnóstico do ambiente (dependências, Tesseract, monitores). Retorna dict."""
    from .diagnostics import run_doctor

    return run_doctor()


__all__ = [
    "Vizion",
    "Config",
    "TaskResult",
    "Region",
    "Point",
    "VizionError",
    "TargetNotFound",
    "ImageNotFoundError",
    "TextNotFoundError",
    "TesseractNotFoundError",
    "OCRUnavailable",
    "WindowNotFound",
    "ImageFileError",
    "InvalidArea",
    "InvalidRegionError",
    "OCRProcessingError",
    "ImageProcessingError",
    "TaskExecutionError",
    "ActionError",
    "SettingsError",
    "ConfigurationError",
    "doctor",
    "limpar_texto",
    "clean_text",
    "__version__",
    *_CLASSIC_FUNCTIONS,
]

# Aliases legados — preferir type_text / keyboard_command / …
def _legacy_alias(fn, alias_name: str):
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        warnings.warn(
            f"{alias_name} é legado; use {fn.__name__}()",
            DeprecationWarning,
            stacklevel=2,
        )
        return fn(*args, **kwargs)

    wrapper.__name__ = alias_name
    wrapper.__qualname__ = alias_name
    return wrapper


type_text_standalone = _legacy_alias(type_text, "type_text_standalone")
keyboard_command_standalone = _legacy_alias(keyboard_command, "keyboard_command_standalone")
extract_text_from_region_standalone = _legacy_alias(
    extract_text_from_region, "extract_text_from_region_standalone"
)
__all__ += [
    "type_text_standalone",
    "keyboard_command_standalone",
    "extract_text_from_region_standalone",
]

# Métodos recomendados para automações novas (o resto é compatibilidade).
CORE_API = (
    "click_image",
    "find_image",
    "click_text",
    "find_text",
    "type_text",
    "wait_for_image",
    "wait_for_text",
    "focus_window",
    "execute_tasks",
    "doctor",
)
__all__ += ["CORE_API"]
