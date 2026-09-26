"""
Vizion - Janelas (Windows)

Trazer a janela certa para frente antes de procurar imagens/texto elimina uma
das causas mais comuns de falha em automações de sistemas legados (popup,
outra aplicação ou o próprio terminal por cima). Sem dependências extras.
"""

import logging
import sys
import time

logger = logging.getLogger(__name__)


def _user32():
    if sys.platform != "win32":
        return None
    import ctypes

    from .screen import ensure_thread_dpi

    ensure_thread_dpi()

    return ctypes.windll.user32


def list_windows():
    """Lista (hwnd, título) das janelas visíveis com título."""
    user32 = _user32()
    if user32 is None:
        return []
    import ctypes
    from ctypes import wintypes

    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                found.append((int(hwnd), buf.value))
        return True

    user32.EnumWindows(_enum, 0)
    return found


def find_window(title):
    """hwnd da primeira janela cujo título contém ``title`` (sem diferenciar caixa)."""
    needle = str(title).casefold()
    exact = [h for h, t in list_windows() if t.casefold() == needle]
    if exact:
        return exact[0]
    for hwnd, text in list_windows():
        if needle in text.casefold():
            return hwnd
    return None


def window_rect(title):
    """(x, y, largura, altura) da janela — útil como ``region``."""
    user32 = _user32()
    hwnd = find_window(title) if user32 else None
    if not hwnd:
        return None
    from ctypes import byref, wintypes

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, byref(rect))
    return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


def focus_window(title, timeout=5.0):
    """
    Traz para frente a janela cujo título contém ``title``, esperando até ``timeout`` s.

    Returns:
        bool: True se a janela ficou em primeiro plano.
    """
    user32 = _user32()
    if user32 is None:
        logger.warning("focus_window só está disponível no Windows.")
        return False
    if not title:
        return False

    deadline = time.time() + max(0.0, float(timeout))
    while True:
        hwnd = find_window(title)
        if hwnd:
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            # Truque do ALT: o Windows só permite SetForegroundWindow ao processo
            # que recebeu a última entrada; um toque em ALT libera a troca.
            user32.keybd_event(0x12, 0, 0, 0)
            user32.keybd_event(0x12, 0, 2, 0)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            time.sleep(0.2)
            if user32.GetForegroundWindow() == hwnd:
                logger.info(f"Janela '{title}' em primeiro plano")
                return True
        if time.time() >= deadline:
            logger.warning(f"Janela '{title}' não encontrada/focada em {timeout}s")
            return False
        time.sleep(0.3)


def wait_window(title, timeout=30.0):
    """Espera uma janela com esse título existir. Retorna True/False."""
    deadline = time.time() + max(0.0, float(timeout))
    while time.time() < deadline:
        if find_window(title):
            return True
        time.sleep(0.3)
    return bool(find_window(title))


_SHOW = {"maximize": 3, "minimize": 6, "restore": 9}


def show_window(title, how="restore"):
    """Maximiza, minimiza ou restaura a janela. Retorna False se não existir."""
    user32 = _user32()
    hwnd = find_window(title) if user32 else None
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, _SHOW[how])
    time.sleep(0.2)
    return True


def close_window(title):
    """Pede para a janela fechar (WM_CLOSE). Retorna False se não existir."""
    user32 = _user32()
    hwnd = find_window(title) if user32 else None
    if not hwnd:
        return False
    user32.PostMessageW(hwnd, 0x0010, 0, 0)
    return True
