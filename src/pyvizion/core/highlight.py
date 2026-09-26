"""
Vizion - Destaque visual

Desenha um retângulo colorido sobre um alvo (para depurar/gravar vídeos).
Roda em processo separado, não bloqueia o robô, não rouba o foco da janela e
deixa o clique atravessar.
"""

import json
import logging
import subprocess
import sys
import threading

logger = logging.getLogger(__name__)

_CHILD_SCRIPT = r"""
import json, sys
cfg = json.loads(globals().get("VIZION_PAYLOAD") or sys.argv[1])
try:
    import ctypes
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass
import tkinter as tk
root = tk.Tk()
root.withdraw()
key = "#010203" if cfg["color"] != "black" else "#fefefe"
wins = []
for (x, y, w, h) in cfg["regions"]:
    b = int(cfg["width"])
    win = tk.Toplevel(root)
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    try:
        win.attributes("-transparentcolor", key)
    except tk.TclError:
        win.attributes("-alpha", 0.5)
    win.configure(bg=key)
    gw, gh = max(int(w) + 2 * b, 2 * b + 2), max(int(h) + 2 * b, 2 * b + 2)
    win.geometry("%dx%d+%d+%d" % (gw, gh, int(x) - b, int(y) - b))
    c = tk.Canvas(win, bg=key, highlightthickness=0, width=gw, height=gh)
    c.pack(fill="both", expand=True)
    c.create_rectangle(b / 2, b / 2, gw - b / 2, gh - b / 2, outline=cfg["color"], width=b)
    wins.append(win)
root.update_idletasks()
if sys.platform == "win32":
    try:
        import ctypes
        u = ctypes.windll.user32
        for win in wins:
            hwnd = u.GetParent(win.winfo_id()) or win.winfo_id()
            ex = u.GetWindowLongW(hwnd, -20)
            # LAYERED | TRANSPARENT (click-through) | TOOLWINDOW | NOACTIVATE
            u.SetWindowLongW(hwnd, -20, ex | 0x80000 | 0x20 | 0x80 | 0x8000000)
    except Exception:
        pass
root.after(int(cfg["duration"]), root.destroy)
root.mainloop()
"""


def highlight(regions, color="red", width=3, ms=800, wait=False):
    """
    Destaca uma ou várias áreas ``(x, y, largura, altura)``.

    Args:
        wait: espera o destaque terminar antes de voltar.
    """
    if regions and not isinstance(regions[0], (tuple, list)):
        regions = [regions]
    boxes = []
    for region in regions:
        try:
            x, y, w, h = [int(v) for v in tuple(region)[:4]]
        except Exception:
            continue
        boxes.append((x, y, max(w, 1), max(h, 1)))
    if not boxes:
        return
    payload = json.dumps({"regions": boxes, "color": color, "width": max(1, int(width)),
                          "duration": max(50, int(ms))})
    if sys.executable and not getattr(sys, "frozen", False):
        try:
            proc = subprocess.Popen(
                [sys.executable, "-c", _CHILD_SCRIPT, payload],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if wait:
                proc.wait(timeout=ms / 1000.0 + 10)
            return
        except Exception as e:
            logger.debug(f"Destaque em processo separado falhou: {e}")

    def run():
        try:
            exec(compile(_CHILD_SCRIPT, "<pyvizion-highlight>", "exec"),
                 {"__name__": "__pyvizion_highlight__", "VIZION_PAYLOAD": payload})
        except Exception as e:
            logger.debug(f"Destaque indisponível: {e}")

    thread = threading.Thread(target=run, daemon=True, name="pyvizion-highlight")
    thread.start()
    if wait:
        thread.join(ms / 1000.0 + 5)
