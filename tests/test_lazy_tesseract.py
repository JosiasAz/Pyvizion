"""Vizion sobe sem Tesseract; OCR só falha ao usar texto."""

from unittest.mock import patch

import cv2
import numpy as np
import pytest

from pyvizion import Vizion
from pyvizion.exceptions import TesseractNotFoundError


def _button_scene(tmp_path):
    scene = np.full((240, 320, 3), 230, np.uint8)
    btn = np.full((30, 80, 3), 40, np.uint8)
    cv2.putText(btn, "OK", (18, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    scene[80:110, 120:200] = btn
    path = tmp_path / "ok.png"
    cv2.imencode(".png", btn)[1].tofile(str(path))
    return scene, str(path)


def test_vizion_cria_sem_tesseract():
    with patch("pyvizion.core.tesseract.locate", side_effect=TesseractNotFoundError("sem tess")):
        # Context não chama locate na criação — patch só garante que prepare falharia
        bot = Vizion({"retry_delay": 0, "show_overlay": False})
        assert bot is not None


def test_click_image_sem_tesseract(tmp_path, fake_gui, monkeypatch):
    from PIL import Image

    from pyvizion.core import screen as screen_mod

    scene, png = _button_scene(tmp_path)
    pil = Image.fromarray(cv2.cvtColor(scene, cv2.COLOR_BGR2RGB))

    def fake_grab(region=None):
        return pil, (0, 0)

    monkeypatch.setattr(screen_mod, "grab_screen", fake_grab)
    monkeypatch.setattr("pyvizion.core.matcher.grab_screen", fake_grab)
    monkeypatch.setattr("pyvizion.core.resolver.grab_screen", fake_grab)

    with patch("pyvizion.core.tesseract.prepare", side_effect=TesseractNotFoundError("sem tess")):
        bot = Vizion({"retry_delay": 0, "show_overlay": False, "failsafe": False})
        assert bot.click_image(png, max_attempts=1) is True

    calls, _ = fake_gui
    clicks = [c for c in calls if c[0] == "click"]
    assert clicks, "deveria ter clicado no centro do botão"
    x, y = clicks[0][1]
    assert 120 <= x <= 200 and 80 <= y <= 110


def test_click_text_exige_tesseract(fake_gui):
    bot = Vizion({"retry_delay": 0, "show_overlay": False, "failsafe": False})
    with patch("pyvizion.core.tesseract.prepare", side_effect=TesseractNotFoundError("sem tess")):
        bot._ctx.reader._info = None  # força nova tentativa de setup
        with pytest.raises(TesseractNotFoundError):
            bot.click_text("Salvar", max_attempts=1)
