"""
CLI do Vizion.
"""

from __future__ import annotations

import sys


def _print_help() -> None:
    from . import __version__

    print(
        f"""pyvizion {__version__} — automação de interface por imagem e texto

Uso:
  pyvizion <comando> [opções]

Comandos (interface flutuante):
  pick [--save arq.png] [--no-ocr] [--terminal]
      Marca uma região (overlay). Captura na hora por padrão.
      Atraso opcional: 5/10/15s ou personalizado.

  position [--terminal]
      Coordenadas do mouse ao vivo (janela estilo MouseInfo).

  ocr [x y largura altura]
      Sem argumentos: marca a região no overlay e mostra o texto.
      Com x y w h: lê essa região e abre o resultado na janela.

  print [arquivo.png]
      Janela: tela completa ou selecionar área (clique/arraste).
      (alias: screenshot)

  windows
      Lista títulos das janelas abertas (com copiar).

Comandos (terminal):
  doctor     Diagnóstico do ambiente
  version    Versão instalada
  help       Este tutorial

Exemplos:
  pyvizion pick
  pyvizion position
  pyvizion ocr
  pyvizion ocr 120 400 200 30
  pyvizion print tela.png
  pyvizion windows

No script Python:
  from pyvizion import Vizion
  bot = Vizion()
  bot.click_image("imagem1.png", region=(x, y, w, h))
  bot.click_text("OK", region=(x, y, w, h))
"""
    )


def _run_doctor() -> int:
    from .diagnostics import format_report, run_doctor

    print(format_report(run_doctor()))
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv:
        _print_help()
        print("--- ambiente ---")
        print()
        return _run_doctor()

    command = argv[0]

    if command in ("--help", "-h", "help"):
        _print_help()
        return 0

    if command in ("--version", "-V", "version"):
        from . import __version__

        print(f"pyvizion {__version__}")
        return 0

    if command == "doctor":
        return _run_doctor()

    if command in ("print", "screenshot"):
        from .tools.panels import run_screenshot_gui

        return run_screenshot_gui(argv[1] if len(argv) > 1 else None)

    if command == "position":
        from .tools.pick_region import run_position_live

        terminal = len(argv) > 1 and argv[1] in ("--terminal", "-t")
        run_position_live(terminal=terminal)
        return 0

    if command == "pick":
        from .tools.pick_region import main_pick

        return main_pick(argv[1:])

    if command == "windows":
        from .tools.panels import run_windows_gui

        return run_windows_gui()

    if command == "ocr":
        from .tools.panels import run_ocr_gui

        if len(argv) == 1:
            return run_ocr_gui()
        if len(argv) != 5:
            print("uso: pyvizion ocr")
            print("     pyvizion ocr x y largura altura")
            return 2
        region = tuple(int(v) for v in argv[1:5])
        return run_ocr_gui(region)

    print(f"comando desconhecido: {command!r}")
    print()
    _print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
