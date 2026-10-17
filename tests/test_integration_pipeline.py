"""Integração: cena sintética → match → clique (sem tocar na tela real)."""

import time

import cv2
import numpy as np
from PIL import Image

from conftest import requires_tesseract
from pyvizion import Vizion
from pyvizion.core.matcher import ImageMatcher
from pyvizion.core.reader import TextReader
from pyvizion.settings import Settings


def _patch_grab(monkeypatch, scene_bgr):
    pil = Image.fromarray(cv2.cvtColor(scene_bgr, cv2.COLOR_BGR2RGB))

    def fake_grab(region=None):
        if region is None:
            return pil, (0, 0)
        x, y, w, h = region if not hasattr(region, "x") else (region.x, region.y, region.width, region.height)
        crop = pil.crop((x, y, x + w, y + h))
        return crop, (x, y)

    for mod in (
        "pyvizion.core.screen.grab_screen",
        "pyvizion.core.matcher.grab_screen",
        "pyvizion.core.resolver.grab_screen",
        "pyvizion.core.reader.grab_screen",
    ):
        try:
            monkeypatch.setattr(mod, fake_grab)
        except Exception:
            pass
    return fake_grab


def test_pipeline_imagem_find_e_click(tmp_path, fake_gui, monkeypatch):
    scene = np.full((300, 400, 3), 240, np.uint8)
    btn = np.full((36, 90, 3), 30, np.uint8)
    cv2.putText(btn, "GO", (20, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    scene[100:136, 150:240] = btn
    png = tmp_path / "go.png"
    cv2.imencode(".png", btn)[1].tofile(str(png))

    _patch_grab(monkeypatch, scene)
    bot = Vizion({"retry_delay": 0, "show_overlay": False, "failsafe": False})

    box = bot.find_image(str(png), max_attempts=1)
    assert box is not None
    assert abs(box[0] - 150) <= 2 and abs(box[1] - 100) <= 2

    assert bot.click_image(str(png), max_attempts=1) is True
    calls, _ = fake_gui
    clicks = [c for c in calls if c[0] == "click"]
    assert clicks
    cx, cy = clicks[0][1]
    assert 150 <= cx <= 240 and 100 <= cy <= 136


@requires_tesseract
def test_pipeline_region_acelera_ocr(render_text):
    """Com region, OCR processa bem menos pixels — base do claim ~6x."""
    img = render_text([("Confirmar", (40, 40)), ("Cancelar", (40, 120))], size=(1200, 800))
    reader = TextReader(Settings(language="eng", ocr_threads=1))

    t0 = time.perf_counter()
    full, _ = reader.find(img, "Confirmar")
    t_full = time.perf_counter() - t0

    crop = img.crop((20, 20, 280, 100))
    t0 = time.perf_counter()
    part, _ = reader.find(crop, "Confirmar")
    t_part = time.perf_counter() - t0

    assert full and part
    # region deve ser claramente mais rápida (margem larga: ≥1.5x)
    assert t_part < t_full / 1.5, f"full={t_full:.3f}s region={t_part:.3f}s"
    speedup = t_full / max(t_part, 1e-6)
    assert speedup >= 1.5


def test_bench_matcher_em_cena_grande():
    """Matching multi-escala em cena 1080p sintética (tempos relativos, CI-friendly)."""
    rng = np.random.default_rng(0)
    scene = np.full((1080, 1920, 3), 220, np.uint8)
    template = rng.integers(40, 200, (48, 64, 3), dtype=np.uint8)
    scene[400:448, 900:964] = template

    matcher = ImageMatcher()
    t0 = time.perf_counter()
    m = matcher.in_image(template, scene, precision=0.9, scales=(1.0, 0.95, 1.05))
    elapsed = time.perf_counter() - t0

    assert m is not None
    assert abs(m.region.x - 900) <= 2
    # sanity: matching local em memória deve ficar bem abaixo de 1s em máquina razoável
    assert elapsed < 2.0, f"match demorou {elapsed:.3f}s"
