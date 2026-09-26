"""
Ferramenta de autorização: marca uma região na tela e sugere trechos para o script.

Equivalente prático ao fluxo do MouseInfo (coordenadas + região + OCR), via terminal.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pyautogui

from ..core.highlight import highlight
from ..core.screen import Region, enable_dpi_awareness, normalize_region, save_screenshot


def _read_point(prompt: str) -> tuple[int, int]:
    input(prompt)
    x, y = pyautogui.position()
    print(f"  -> x={x}, y={y}")
    return int(x), int(y)


def _region_from_corners(p1: tuple[int, int], p2: tuple[int, int]) -> Region:
    x1, y1 = p1
    x2, y2 = p2
    left, top = min(x1, x2), min(y1, y2)
    width, height = abs(x2 - x1), abs(y2 - y1)
    if width < 2 or height < 2:
        raise ValueError("Região muito pequena — afaste os dois cantos.")
    return normalize_region((left, top, width, height))


def run_pick(*, save_crop: str | None = None, ocr: bool = True) -> Region:
    """Guia o usuário a marcar canto superior-esquerdo e inferior-direito."""
    enable_dpi_awareness()
    print("pyvizion pick — marque uma região (como no MouseInfo, pelo terminal)\n")
    print("  1) Leve o mouse ao canto SUPERIOR ESQUERDO e pressione Enter")
    print("  2) Leve o mouse ao canto INFERIOR DIREITO e pressione Enter\n")

    p1 = _read_point("Enter no canto 1... ")
    p2 = _read_point("Enter no canto 2... ")
    region = _region_from_corners(p1, p2)

    highlight(region, "lime", 4, 1200, wait=True)

    x, y, w, h = tuple(region)
    print(f"\nregion = ({x}, {y}, {w}, {h})")

    if save_crop:
        out = Path(save_crop)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = Path(f"recorte_{stamp}.png")
    save_screenshot(str(out), region)
    print(f"recorte salvo: {out.resolve()}")

    text_preview = ""
    if ocr:
        try:
            from ..vizion import Vizion

            text_preview = Vizion().read_text(region, single_line=False).strip()
            if text_preview:
                print(f"\nOCR na região:\n{text_preview[:500]}")
                if len(text_preview) > 500:
                    print("  ... (truncado)")
            else:
                print("\nOCR: (nenhum texto detectado)")
        except Exception as exc:
            print(f"\nOCR indisponível: {exc}")

    print("\n--- Cole no seu script ---")
    print(f'region = ({x}, {y}, {w}, {h})')
    print(f'vz.click_text("...", region=region)')
    print(f'vz.read_text(region=region)')
    print(f'vz.click_image("{out.name}", region=region)  # após ajustar o PNG')
    if text_preview:
        snippet = text_preview.splitlines()[0].replace('"', "'")[:60]
        print(f'vz.click_text("{snippet}", region=region)')

    try:
        import pyperclip

        pyperclip.copy(f"({x}, {y}, {w}, {h})")
        print("\n(cópia: tupla region na área de transferência)")
    except Exception:
        pass

    return region


def run_position_live() -> None:
    """Posição do mouse em tempo real (Ctrl+C para sair)."""
    import time

    enable_dpi_awareness()
    print("Mova o mouse (Ctrl+C para sair). Coordenadas em pixels de tela.\n")
    try:
        while True:
            x, y = pyautogui.position()
            print(f"\rx={x:<6} y={y:<6}   region_1px=({x}, {y}, 1, 1)", end="", flush=True)
            time.sleep(0.08)
    except KeyboardInterrupt:
        print()


def main_pick(argv: list[str]) -> int:
    save = None
    no_ocr = False
    i = 0
    while i < len(argv):
        if argv[i] in ("--save", "-s") and i + 1 < len(argv):
            save = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--no-ocr":
            no_ocr = True
            i += 1
            continue
        print(f"argumento desconhecido: {argv[i]!r}")
        return 2
    try:
        run_pick(save_crop=save, ocr=not no_ocr)
    except (KeyboardInterrupt, EOFError):
        print("\ncancelado.")
        return 130
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0
