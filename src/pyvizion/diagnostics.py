"""
Vizion - Diagnóstico do ambiente (``python -m pyvizion doctor``)
"""

import importlib
import platform
import sys


def run_doctor():
    """Verifica dependências, Tesseract, idiomas e telas. Retorna dict com os achados."""
    report = {"python": sys.version.split()[0], "platform": platform.platform(), "modules": {}}

    for module, attr in (("cv2", "__version__"), ("numpy", "__version__"), ("PIL", "__version__"),
                         ("pyautogui", "__version__"), ("pytesseract", None), ("pyperclip", None),
                         ("mss", "__version__"), ("yaml", "__version__")):
        try:
            mod = importlib.import_module(module)
            report["modules"][module] = getattr(mod, attr, "ok") if attr else "ok"
        except ImportError:
            report["modules"][module] = None

    from .core import tesseract
    from .settings import Settings

    try:
        info = tesseract.prepare(Settings())
        report["tesseract"] = info["exe"]
        report["tessdata"] = info["tessdata"]
        report["languages"] = info["languages"]
    except Exception as e:
        report["tesseract"] = None
        report["tesseract_error"] = str(e).splitlines()[0]
        report["languages"] = []

    try:
        from .core.screen import enable_dpi_awareness, primary_screen_size, virtual_screen_bounds

        enable_dpi_awareness()
        report["primary_screen"] = primary_screen_size()
        report["virtual_screen"] = tuple(virtual_screen_bounds())
    except Exception as e:
        report["screen_error"] = str(e)
    return report


def format_report(report):
    ok, bad = "✔", "✘"
    lines = [f"pyvizion doctor — Python {report['python']} ({report['platform']})", ""]
    for module, version in report["modules"].items():
        mark = ok if version else bad
        lines.append(f"  {mark} {module:<12} {version or 'não instalado — reinstale: pip install pyvizion'}")
    lines.append("")
    if report.get("tesseract"):
        lines.append(f"  {ok} Tesseract    {report['tesseract']}")
        langs = report.get("languages") or []
        lines.append(f"    idiomas: {', '.join(langs) or '?'}")
        if "eng" not in langs:
            lines.append("    dica: o padrão do OCR é 'eng' — instale esse idioma no Tesseract.")
        elif "por" not in langs:
            lines.append("    dica: para textos em português, instale 'por' e use tesseract_lang='por'.")
    else:
        lines.append(f"  {bad} Tesseract    {report.get('tesseract_error', 'não encontrado')}")
        lines.append("    (necessário só para alvos de texto e read())")
    if "primary_screen" in report:
        lines.append(f"  {ok} Tela principal {report['primary_screen'][0]}x{report['primary_screen'][1]}, "
                     f"área virtual {report['virtual_screen']}")
    return "\n".join(lines)
