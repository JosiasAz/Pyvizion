import os
import shutil

import pytest
from PIL import Image, ImageDraw, ImageFont


def _font(size):
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


@pytest.fixture
def render_text():
    """Gera uma imagem com textos em posições conhecidas: [(texto, (x, y)), ...]."""

    def _render(items, size=(600, 200), font_size=28, bg="white", fg="black"):
        img = Image.new("RGB", size, bg)
        draw = ImageDraw.Draw(img)
        font = _font(font_size)
        for text, pos in items:
            draw.text(pos, text, fill=fg, font=font)
        return img

    return _render


def _has_tesseract():
    from pyvizion.core import tesseract
    from pyvizion.settings import Settings

    try:
        tesseract.prepare(Settings())
        return True
    except Exception:
        return False


requires_tesseract = pytest.mark.skipif(
    not (_has_tesseract() or shutil.which("tesseract") or os.environ.get("PYVIZION_FORCE_OCR")),
    reason="Tesseract não instalado",
)


@pytest.fixture
def fake_gui(monkeypatch):
    """Substitui pyautogui/pyperclip por gravadores de chamadas."""
    import pyautogui
    import pyperclip

    calls = []
    clipboard = {"value": "anterior"}

    for name in ("press", "hotkey", "write", "typewrite", "click", "doubleClick", "tripleClick",
                 "moveTo", "mouseDown", "mouseUp", "scroll", "dragTo"):
        monkeypatch.setattr(pyautogui, name,
                            lambda *a, _n=name, **k: calls.append((_n, a, k)))
    monkeypatch.setattr(pyautogui, "position", lambda: type("P", (), {"x": 1, "y": 2})())
    monkeypatch.setattr(pyperclip, "copy", lambda v: clipboard.__setitem__("value", v))
    monkeypatch.setattr(pyperclip, "paste", lambda: clipboard["value"])
    monkeypatch.setattr("time.sleep", lambda s: None)
    return calls, clipboard
