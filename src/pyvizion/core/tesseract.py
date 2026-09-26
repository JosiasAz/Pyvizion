"""
Vizion - Localização e configuração do Tesseract (sob demanda)
"""

import logging
import os
import platform
import shutil
import subprocess
import threading
from pathlib import Path

from ..exceptions import OCRUnavailable, TesseractNotFoundError

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_CACHE = {}


def _candidates():
    system = platform.system().lower()
    if system == "windows":
        local = os.getenv("LOCALAPPDATA", "")
        paths = [r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                 r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"]
        if local:
            paths += [os.path.join(local, "Tesseract-OCR", "tesseract.exe"),
                      os.path.join(local, "Programs", "Tesseract-OCR", "tesseract.exe")]
    elif system == "darwin":
        paths = ["/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract", "/usr/bin/tesseract"]
    else:
        paths = ["/usr/bin/tesseract", "/usr/local/bin/tesseract", "/snap/bin/tesseract"]
    found = shutil.which("tesseract")
    if found:
        paths.append(found)
    return paths


def _works(path):
    if not path or not os.path.isfile(path):
        return False
    try:
        result = subprocess.run([path, "--version"], capture_output=True, timeout=10,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return result.returncode == 0
    except Exception:
        return False


def _tessdata_for(exe):
    folder = Path(exe).parent
    for candidate in (folder / "tessdata", folder.parent / "tessdata",
                      folder.parent / "share" / "tessdata",
                      Path("/usr/share/tesseract-ocr/5/tessdata"),
                      Path("/usr/share/tesseract-ocr/4/tessdata"),
                      Path("/usr/share/tessdata"), Path("/usr/local/share/tessdata"),
                      Path("/opt/homebrew/share/tessdata")):
        if candidate.is_dir():
            return str(candidate.resolve())
    return None


def locate(executable=None):
    """Caminho do executável do Tesseract. Levanta ``TesseractNotFoundError``."""
    with _LOCK:
        if executable:
            if executable in _CACHE or _works(executable):
                _CACHE[executable] = True
                return executable
            logger.warning(f"Tesseract informado não funciona: {executable}. Procurando outro.")
        if "auto" in _CACHE:
            return _CACHE["auto"]
        for path in _candidates():
            if _works(path):
                _CACHE["auto"] = path
                logger.debug(f"Tesseract: {path}")
                return path
    raise TesseractNotFoundError(
        "Tesseract OCR não encontrado. Instale antes de criar Vizion():\n"
        "  Windows: https://github.com/UB-Mannheim/tesseract/wiki (inglês já vem no instalador)\n"
        "  Linux:   sudo apt-get install tesseract-ocr\n"
        "  macOS:   brew install tesseract\n"
        "ou informe tesseract_path=r'C:\\...\\tesseract.exe'."
    )


def installed_languages(tessdata):
    if not tessdata or not os.path.isdir(tessdata):
        return []
    return sorted(p.stem for p in Path(tessdata).glob("*.traineddata"))


def prepare(settings):
    """
    Configura o pytesseract conforme ``settings``.

    Returns:
        dict: {"exe", "tessdata", "language", "languages"}
    """
    try:
        import pytesseract
    except ImportError:
        raise OCRUnavailable("pytesseract não instalado: pip install pytesseract") from None

    exe = locate(settings.tesseract)
    pytesseract.pytesseract.tesseract_cmd = exe
    tessdata = settings.tessdata or _tessdata_for(exe)
    if tessdata:
        os.environ["TESSDATA_PREFIX"] = tessdata
    languages = installed_languages(tessdata)
    return {"exe": exe, "tessdata": tessdata, "languages": languages,
            "language": _pick_language(settings.language, languages)}


def _pick_language(wanted, installed):
    if not installed:
        return wanted
    if not wanted:
        for choice in ("eng", "por+eng", "por"):
            if all(part in installed for part in choice.split("+")):
                return choice
        return None
    parts = [p for p in str(wanted).split("+") if p]
    usable = [p for p in parts if p in installed]
    missing = [p for p in parts if p not in installed]
    if missing:
        key = f"warned:{wanted}"
        if key not in _CACHE:
            _CACHE[key] = True
            logger.warning(f"Idioma do OCR não instalado: {', '.join(missing)} "
                           f"(instalados: {', '.join(installed)})")
    if usable:
        return "+".join(usable)
    return "eng" if "eng" in installed else None
