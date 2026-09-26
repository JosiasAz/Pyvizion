"""
CLI do Vizion.

    python -m pyvizion doctor              # diagnóstico do ambiente
    python -m pyvizion --version
    python -m pyvizion screenshot [arq]    # salva um print (para recortar imagens)
    python -m pyvizion position            # posição do mouse em tempo real (x, y)
    python -m pyvizion pick [--save recorte.png]  # marca região (2 cantos) + OCR + trechos
    python -m pyvizion windows             # títulos das janelas abertas
    python -m pyvizion ocr x y w h         # lê o texto de uma região
"""

import sys


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0] if argv else "doctor"

    if command in ("--version", "-V", "version"):
        from . import __version__

        print(f"pyvizion {__version__}")
        return 0

    if command == "doctor":
        from .diagnostics import format_report, run_doctor

        print(format_report(run_doctor()))
        return 0

    if command == "screenshot":
        from .core.screen import save_screenshot

        print(save_screenshot(argv[1] if len(argv) > 1 else None))
        return 0

    if command == "position":
        from .tools.pick_region import run_position_live

        run_position_live()
        return 0

    if command == "pick":
        from .tools.pick_region import main_pick

        return main_pick(argv[1:])

    if command == "windows":
        from .core.windows import list_windows

        for _, title in list_windows():
            print(title)
        return 0

    if command == "ocr":
        if len(argv) != 5:
            print("uso: python -m pyvizion ocr x y largura altura")
            return 2
        from .vizion import Vizion

        region = tuple(int(v) for v in argv[1:5])
        print(Vizion().read_text(region))
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
