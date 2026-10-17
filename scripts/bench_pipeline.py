#!/usr/bin/env python
"""Mede tempos do pyvizion nesta máquina (opcional).

Uso:
    python scripts/bench_pipeline.py

Não é necessário para usar a biblioteca — só para ver quanto demora
print, busca de imagem e OCR no seu PC.
"""

from __future__ import annotations

import statistics
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _font(size=28):
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def bench_grab(n=20):
    from pyvizion.core.screen import enable_dpi_awareness, grab_screen

    enable_dpi_awareness()
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        grab_screen()
        times.append((time.perf_counter() - t0) * 1000)
    return times


def bench_match(n=10):
    from pyvizion.core.matcher import ImageMatcher

    rng = np.random.default_rng(1)
    scene = np.full((1080, 1920, 3), 220, np.uint8)
    template = rng.integers(40, 200, (48, 64, 3), dtype=np.uint8)
    scene[400:448, 900:964] = template
    matcher = ImageMatcher()
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        matcher.in_image(template, scene, precision=0.9, scales=(1.0, 0.95, 1.05))
        times.append((time.perf_counter() - t0) * 1000)
    return times


def bench_ocr_region_vs_full():
    from pyvizion.core.reader import TextReader
    from pyvizion.settings import Settings

    img = Image.new("RGB", (1200, 800), "white")
    draw = ImageDraw.Draw(img)
    draw.text((40, 40), "Confirmar", fill="black", font=_font())
    reader = TextReader(Settings(language="eng", ocr_threads=1))

    t0 = time.perf_counter()
    reader.find(img, "Confirmar")
    t_full = (time.perf_counter() - t0) * 1000

    crop = img.crop((20, 20, 280, 100))
    t0 = time.perf_counter()
    reader.find(crop, "Confirmar")
    t_part = (time.perf_counter() - t0) * 1000
    return t_full, t_part


def _ms(times_ms):
    return statistics.median(times_ms)


def main():
    print("Medindo o pyvizion nesta máquina")
    print("(opcional — não faz parte do uso normal)\n")

    grab = bench_grab()
    print(f"1) Tirar print da tela ........ {_ms(grab):.0f} ms")

    match = bench_match()
    print(f"2) Achar imagem (PNG na tela) . {_ms(match):.0f} ms")

    try:
        full, part = bench_ocr_region_vs_full()
        speedup = full / max(part, 0.001)
        print(f"3) Ler texto (OCR) tela inteira  {full:.0f} ms")
        print(f"   Ler texto só numa região ... {part:.0f} ms  ({speedup:.1f}x mais rápido)")
        print("\nConclusão: passe region=... no click_text — OCR fica bem mais rápido.")
    except Exception as exc:
        print(f"3) Ler texto (OCR) ............. pulado ({exc})")
        print("   (instale o Tesseract se quiser medir OCR)")

    print("\nValores mudam conforme PC e resolução. Rode de novo com a máquina")
    print("ociosa se for citar esses números.")


if __name__ == "__main__":
    main()
