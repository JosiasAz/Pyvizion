"""
Vizion - Mouse

Clique físico (PyAutoGUI) ou virtual no Windows (mensagem à janela, cursor parado).
"""

import ctypes
import logging
import sys
import time

from ..exceptions import ActionError
from .screen import ensure_thread_dpi

logger = logging.getLogger(__name__)

BUTTONS = ("left", "right", "middle")

_WM_MOUSEMOVE = 0x0200
_WM_LBUTTONDOWN = 0x0201
_WM_LBUTTONUP = 0x0202
_WM_RBUTTONDOWN = 0x0204
_WM_RBUTTONUP = 0x0205
_WM_MBUTTONDOWN = 0x0207
_WM_MBUTTONUP = 0x0208
_MK_LBUTTON = 0x0001
_MK_RBUTTON = 0x0002
_MK_MBUTTON = 0x0010


def _gui():
    import pyautogui

    return pyautogui


def is_emergency_stop(exc) -> bool:
    """True para a parada de emergência (mouse no canto superior esquerdo)."""
    return type(exc).__name__ == "FailSafeException"


def _makelong(low, high):
    return (int(high) << 16) | (int(low) & 0xFFFF)


def _window_from_point(x, y):
    user32 = ctypes.windll.user32
    point = ctypes.wintypes.POINT(int(x), int(y))
    user32.WindowFromPoint.argtypes = [ctypes.wintypes.POINT]
    user32.WindowFromPoint.restype = ctypes.wintypes.HWND
    return user32.WindowFromPoint(point)


def _screen_to_client(hwnd, x, y):
    user32 = ctypes.windll.user32
    point = ctypes.wintypes.POINT(int(x), int(y))
    user32.ScreenToClient.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.POINT)]
    user32.ScreenToClient.restype = ctypes.wintypes.BOOL
    if not user32.ScreenToClient(hwnd, ctypes.byref(point)):
        return None
    return int(point.x), int(point.y)


def _post_mouse(hwnd, message, wparam, lparam):
    user32 = ctypes.windll.user32
    user32.PostMessageW.argtypes = [
        ctypes.wintypes.HWND, ctypes.wintypes.UINT, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
    user32.PostMessageW.restype = ctypes.wintypes.BOOL
    return bool(user32.PostMessageW(hwnd, message, wparam, lparam))


def _virtual_available():
    return sys.platform == "win32"


def _click_virtual_windows(x, y, button, times, hold):
    """Envia o clique à janela sob o ponto, sem mover o cursor. ``True`` se enviou."""
    hwnd = _window_from_point(x, y)
    if not hwnd:
        return False
    client = _screen_to_client(hwnd, x, y)
    if client is None:
        return False
    cx, cy = client
    lparam = _makelong(cx, cy)
    if button == "right":
        down, up, mark = _WM_RBUTTONDOWN, _WM_RBUTTONUP, _MK_RBUTTON
    elif button == "middle":
        down, up, mark = _WM_MBUTTONDOWN, _WM_MBUTTONUP, _MK_MBUTTON
    else:
        down, up, mark = _WM_LBUTTONDOWN, _WM_LBUTTONUP, _MK_LBUTTON
    _post_mouse(hwnd, _WM_MOUSEMOVE, 0, lparam)
    pause = max(float(hold), 0.05)
    for _ in range(max(1, int(times))):
        if not _post_mouse(hwnd, down, mark, lparam):
            return False
        time.sleep(pause)
        if not _post_mouse(hwnd, up, 0, lparam):
            return False
        time.sleep(0.05)
    logger.info(f"Clique virtual ({button} ×{times}) em ({int(x)}, {int(y)}) hwnd={hwnd}")
    return True


class Mouse:
    def __init__(self, settings):
        self.settings = settings
        gui = _gui()
        gui.FAILSAFE = bool(settings.emergency_stop)
        gui.PAUSE = 0.05
        self.virtual_available = _virtual_available()
        if settings.virtual_mouse and not self.virtual_available:
            logger.warning("use_virtual_mouse=True, mas o clique virtual só existe no Windows — "
                           "usando o mouse físico")

    def move(self, point):
        ensure_thread_dpi()
        x, y = int(point[0]), int(point[1])
        _gui().moveTo(x, y, duration=float(self.settings.move_time))
        time.sleep(float(self.settings.settle))
        return x, y

    def click(self, point, button="left", times=1):
        """Clica ``times`` vezes (1 simples, 2 duplo, 3 triplo). ``times=0`` só move."""
        if button not in BUTTONS:
            raise ActionError(f"Botão inválido '{button}'. Use: {', '.join(BUTTONS)}")
        try:
            if times <= 0:
                x, y = self.move(point)
                logger.info(f"Mouse em ({x}, {y})")
                return
            if self.settings.virtual_mouse:
                if self._click_virtual(point, button, times):
                    return
                logger.warning("Clique virtual falhou — usando o mouse físico e devolvendo o cursor")
                self._click_physical_restore(point, button, times)
                return
            self._click_physical(point, button, times)
        except Exception as e:
            if is_emergency_stop(e):
                raise
            raise ActionError(f"Falha no mouse: {e}") from e

    def _click_virtual(self, point, button, times):
        if not self.virtual_available:
            return False
        ensure_thread_dpi()
        x, y = int(point[0]), int(point[1])
        return _click_virtual_windows(x, y, button, times, self.settings.click_hold)

    def _click_physical(self, point, button, times):
        x, y = self.move(point)
        gui = _gui()
        hold = float(self.settings.click_hold)
        if hold > 0:
            for _ in range(times):
                gui.mouseDown(x, y, button=button)
                time.sleep(hold)
                gui.mouseUp(x, y, button=button)
                time.sleep(0.05)
        elif times == 1:
            gui.click(x, y, button=button)
        else:
            gui.click(x, y, clicks=times, interval=0.08, button=button)
        names = {1: "Clique", 2: "Clique duplo", 3: "Clique triplo"}
        logger.info(f"{names.get(times, f'{times} cliques')} ({button}) em ({x}, {y})")

    def _click_physical_restore(self, point, button, times):
        gui = _gui()
        here = gui.position()
        self._click_physical(point, button, times)
        gui.moveTo(int(here[0]), int(here[1]), duration=0)

    def scroll(self, amount, point=None):
        ensure_thread_dpi()
        kwargs = {} if point is None else {"x": int(point[0]), "y": int(point[1])}
        _gui().scroll(int(amount), **kwargs)

    def drag(self, start, end, duration=0.5, button="left"):
        self.move(start)
        _gui().dragTo(int(end[0]), int(end[1]), duration=duration, button=button)
