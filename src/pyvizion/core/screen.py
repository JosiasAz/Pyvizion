"""
Vizion - Captura de tela e utilidades de coordenadas

- Ativa DPI awareness no Windows (screenshot e clique no mesmo sistema de pixels,
  evitando cliques deslocados em telas com escala 125%/150%).
- Captura em memória de todos os monitores (coordenadas virtuais, inclusive
  negativas quando há monitor à esquerda do principal).
- Carrega imagens de qualquer caminho (inclusive com acentos no Windows),
  objetos PIL e arrays NumPy.
"""

import logging
import os
import sys
import threading
from collections import namedtuple
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from ..exceptions import ActionError, ImageFileError, InvalidArea

logger = logging.getLogger(__name__)

class Point(namedtuple("Point", "x y")):
    """Ponto de tela (x, y)."""

    def shift(self, dx=0, dy=0):
        return Point(self.x + int(dx), self.y + int(dy))


class Region(namedtuple("Region", "x y width height")):
    """
    Retângulo de tela ``(x, y, largura, altura)`` — é também uma tupla.

        >>> r = Region(100, 200, 80, 20)
        >>> r.center                 # Point(x=140, y=210)
        >>> r.right_of(250)          # área de 250px à direita (o campo ao lado do rótulo)
        >>> r.grow(10)               # 10px de folga em volta
    """

    @property
    def left(self):
        return self.x

    @property
    def top(self):
        return self.y

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height

    @property
    def center(self):
        return Point(self.x + self.width // 2, self.y + self.height // 2)

    def shift(self, dx=0, dy=0):
        return Region(self.x + int(dx), self.y + int(dy), self.width, self.height)

    def grow(self, px=0, py=None):
        py = px if py is None else py
        return Region(self.x - int(px), self.y - int(py), self.width + 2 * int(px), self.height + 2 * int(py))

    def right_of(self, width, gap=0):
        return Region(self.right + int(gap), self.y, int(width), self.height)

    def left_of(self, width, gap=0):
        return Region(self.x - int(gap) - int(width), self.y, int(width), self.height)

    def below(self, height, gap=0):
        return Region(self.x, self.bottom + int(gap), self.width, int(height))

    def above(self, height, gap=0):
        return Region(self.x, self.y - int(gap) - int(height), self.width, int(height))

    def contains(self, point):
        px, py = point[:2]
        return self.x <= px < self.right and self.y <= py < self.bottom


def as_region(value):
    """Converte tupla/lista (x, y, w, h) em Region (None continua None)."""
    if value is None or isinstance(value, Region):
        return value
    try:
        x, y, w, h = [int(round(float(v))) for v in tuple(value)[:4]]
    except Exception:
        raise InvalidArea(f"Área inválida: {value!r}. Use (x, y, largura, altura).") from None
    return Region(x, y, w, h)

_DPI_DONE = False
_CAPTURE_LOCK = threading.Lock()
_MSS_LOCAL = threading.local()


def enable_dpi_awareness():
    """
    Torna o processo DPI-aware por monitor (Windows). Idempotente e silencioso.

    Precisa acontecer antes de qualquer outra biblioteca definir o modo (o
    ``import pyautogui`` fixa o modo "sistema"), por isso o ``import pyvizion``
    já chama esta função. Defina ``PYVIZION_NO_DPI=1`` para desativar.
    """
    global _DPI_DONE
    if _DPI_DONE or sys.platform != "win32" or os.environ.get("PYVIZION_NO_DPI"):
        _DPI_DONE = True
        return
    _DPI_DONE = True
    try:
        import ctypes

        try:
            # PER_MONITOR_AWARE_V2
            if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                return
        except Exception:
            pass
        try:
            if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
                return
        except Exception:
            pass
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception as e:  # pragma: no cover - depende do SO
        logger.debug(f"Não foi possível ativar DPI awareness: {e}")
    finally:
        _warn_if_not_per_monitor()


def dpi_awareness():
    """Modo atual: 0 = sem DPI, 1 = sistema, 2 = por monitor (ou None fora do Windows)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        user32 = ctypes.windll.user32
        user32.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        user32.GetAwarenessFromDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        return int(user32.GetAwarenessFromDpiAwarenessContext(user32.GetThreadDpiAwarenessContext()))
    except Exception:
        return None


def ensure_thread_dpi():
    """
    Garante o modo DPI por monitor na thread atual (Windows 10 1607+).

    Resolve o caso em que o processo já foi fixado em modo "sistema" por outra
    biblioteca (ex.: ``import pyautogui`` antes de ``import pyvizion``).
    """
    if sys.platform != "win32" or os.environ.get("PYVIZION_NO_DPI"):
        return
    if dpi_awareness() == 2:
        return
    try:
        import ctypes

        ctypes.windll.user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass


def _warn_if_not_per_monitor():
    ensure_thread_dpi()
    mode = dpi_awareness()
    if mode is None or mode == 2:
        return
    try:
        scales = monitor_scales()
    except Exception:
        return
    if len(scales) > 1:
        logger.warning(
            "Monitores com escalas diferentes (%s) e o processo não está em modo DPI por "
            "monitor: cliques/capturas podem sair deslocados no monitor secundário. "
            "Faça 'import pyvizion' antes de 'import pyautogui' (ou de outras libs de GUI).",
            ", ".join(f"{int(s * 100)}%" for s in scales),
        )


def center(location):
    """Centro de (x, y, w, h)."""
    x, y, w, h = [int(v) for v in location[:4]]
    return Point(x + w // 2, y + h // 2)


def virtual_screen_bounds():
    """(left, top, width, height) da área que cobre todos os monitores."""
    if sys.platform == "win32":
        ensure_thread_dpi()
        try:
            import ctypes

            user32 = ctypes.windll.user32
            left = user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
            top = user32.GetSystemMetrics(77)    # SM_YVIRTUALSCREEN
            width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
            height = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
            if width > 0 and height > 0:
                return Region(left, top, width, height)
        except Exception:
            pass
    mss_bounds = _mss_bounds()
    if mss_bounds:
        return mss_bounds
    import pyautogui

    size = pyautogui.size()
    return Region(0, 0, int(size.width), int(size.height))


def monitor_scales(region=None):
    """
    Fatores de escala (DPI/96) dos monitores que intersectam a região (ou de todos).

    Apps legados sem suporte a DPI são "esticados" pelo Windows em monitores com
    escala 125%/150%; incluir esses fatores na busca evita falhas de matching.
    """
    if sys.platform != "win32":
        return [1.0]
    enable_dpi_awareness()
    ensure_thread_dpi()
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        shcore = ctypes.windll.shcore
    except Exception:
        return [1.0]

    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HMONITOR, wintypes.HDC,
                        ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    def _cb(hmon, _hdc, rect, _lparam):
        r = rect.contents
        if region is not None:
            x, y, w, h = region[:4]
            if r.right <= x or r.left >= x + w or r.bottom <= y or r.top >= y + h:
                return True
        dpi_x, dpi_y = ctypes.c_uint(), ctypes.c_uint()
        try:
            if shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) == 0:
                found.append(round(dpi_x.value / 96.0, 3))
        except Exception:
            pass
        return True

    try:
        user32.EnumDisplayMonitors(0, 0, _cb, 0)
    except Exception:
        return [1.0]
    return sorted(set(found)) or [1.0]


def primary_screen_size():
    import pyautogui

    size = pyautogui.size()
    return int(size.width), int(size.height)


def _get_mss():
    try:
        import mss  # captura rápida (~5 ms por área); PIL fica como reserva
    except ImportError:
        return None
    inst = getattr(_MSS_LOCAL, "inst", None)
    if inst is None:
        try:
            inst = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
        except Exception:
            return None
        _MSS_LOCAL.inst = inst
    return inst


def _mss_bounds():
    sct = _get_mss()
    if sct is None:
        return None
    mon = sct.monitors[0]
    return Region(mon["left"], mon["top"], mon["width"], mon["height"])


def normalize_region(region, clamp=True):
    """Valida (x, y, w, h) e recorta à área visível dos monitores."""
    if region is None:
        return None
    try:
        x, y, w, h = [int(round(float(v))) for v in tuple(region)[:4]]
    except Exception:
        raise InvalidArea(f"Região inválida: {region!r}. Use (x, y, largura, altura).")
    if w <= 0 or h <= 0:
        raise InvalidArea(f"Região com largura/altura inválida: {region!r}")
    if not clamp:
        return Region(x, y, w, h)
    bounds = virtual_screen_bounds()
    x1, y1 = max(x, bounds.left), max(y, bounds.top)
    x2 = min(x + w, bounds.left + bounds.width)
    y2 = min(y + h, bounds.top + bounds.height)
    if x2 - x1 < 1 or y2 - y1 < 1:
        raise InvalidArea(f"Região {region!r} está fora da tela {tuple(bounds)}")
    if (x1, y1, x2 - x1, y2 - y1) != (x, y, w, h):
        logger.debug(f"Região {region} ajustada para {(x1, y1, x2 - x1, y2 - y1)}")
    return Region(x1, y1, x2 - x1, y2 - y1)


def grab_screen(region=None):
    """
    Captura a tela (ou uma região) em memória.

    Args:
        region: (x, y, w, h) em coordenadas absolutas de tela, ou None para todos os monitores.

    Returns:
        tuple: (PIL.Image RGB, (left, top)) — origem da imagem em coordenadas de tela.
    """
    enable_dpi_awareness()
    ensure_thread_dpi()
    box = normalize_region(region) if region is not None else virtual_screen_bounds()
    with _CAPTURE_LOCK:
        try:
            img = _grab_mss(box)
            if img is None:
                img = _grab_pil(box)
        except Exception as e:
            raise ActionError(f"Erro na captura de tela: {e}")
    if img is None or img.width < 1 or img.height < 1:
        raise ActionError(f"Falha ao capturar região {tuple(box)}")
    return img, (box.left, box.top)


def _grab_mss(box):
    sct = _get_mss()
    if sct is None:
        return None
    shot = sct.grab({"left": box.left, "top": box.top, "width": box.width, "height": box.height})
    return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def _grab_pil(box):
    from PIL import ImageGrab

    if sys.platform == "win32":
        vb = virtual_screen_bounds()
        full = ImageGrab.grab(all_screens=True)
        # A imagem de all_screens começa no canto superior esquerdo virtual.
        left = box.left - vb.left
        top = box.top - vb.top
        img = full.crop((left, top, left + box.width, top + box.height))
    else:
        img = ImageGrab.grab(bbox=(box.left, box.top, box.left + box.width, box.top + box.height))
    return img.convert("RGB")


def save_screenshot(path=None, region=None):
    """Salva um screenshot e retorna o caminho."""
    img, _ = grab_screen(region)
    if path is None:
        import time

        path = f"pyvizion_screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png"
    path = str(path)
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    img.save(path)
    return path


# ---------------------------------------------------------------------------
# Carregamento de imagens
# ---------------------------------------------------------------------------

_TEMPLATE_CACHE = {}
_TEMPLATE_CACHE_LOCK = threading.Lock()


def resolve_image_path(image_path, folders=()):
    """Resolve o caminho de uma imagem procurando nas pastas configuradas."""
    candidate = Path(os.path.expanduser(str(image_path)))
    if candidate.is_file():
        return str(candidate)
    if not candidate.is_absolute():
        search = list(folders or [])
        main = sys.modules.get("__main__")
        main_file = getattr(main, "__file__", None)
        if main_file:
            search.append(os.path.dirname(os.path.abspath(main_file)))
        for folder in search:
            path = Path(folder) / candidate
            if path.is_file():
                return str(path)
    raise ImageFileError(
        f"Arquivo de imagem não encontrado: '{image_path}'. "
        f"Verifique o caminho ou configure Settings(image_dirs=[...])."
    )


def load_image(source, folders=()):
    """Carrega imagem como array BGR (uint8). Aceita caminho, PIL.Image ou ndarray."""
    if isinstance(source, np.ndarray):
        return _to_bgr(source)
    if isinstance(source, Image.Image):
        return pil_to_bgr(source)
    if not isinstance(source, (str, Path)):
        raise ImageFileError(f"Tipo de imagem não suportado: {type(source)}")

    path = resolve_image_path(source, folders)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0
    key = (path, mtime)
    with _TEMPLATE_CACHE_LOCK:
        cached = _TEMPLATE_CACHE.get(key)
    if cached is not None:
        return cached

    # np.fromfile + imdecode suporta caminhos com acentos no Windows.
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED) if data.size else None
    if img is None:
        try:
            img = pil_to_bgr(Image.open(path))
        except Exception:
            raise ImageFileError(f"Não foi possível ler a imagem: '{path}'")
    img = _to_bgr(img)
    with _TEMPLATE_CACHE_LOCK:
        if len(_TEMPLATE_CACHE) > 256:
            _TEMPLATE_CACHE.clear()
        _TEMPLATE_CACHE[key] = img
    return img


def pil_to_bgr(img):
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    arr = np.array(img)
    if arr.ndim == 2:
        return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    if arr.shape[2] == 4:
        return _flatten_alpha(arr, rgb=True)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def _to_bgr(arr):
    arr = np.asarray(arr)
    if arr.dtype == np.uint16:
        arr = (arr // 257).astype(np.uint8)
    elif arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    if arr.ndim == 2:
        return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    if arr.shape[2] == 4:
        return _flatten_alpha(arr, rgb=False)
    return arr


def _flatten_alpha(arr, rgb):
    """Remove o canal alfa compondo sobre cinza médio (neutro para o matching)."""
    color = arr[:, :, :3].astype(np.float32)
    alpha = arr[:, :, 3:4].astype(np.float32) / 255.0
    flat = (color * alpha + 128.0 * (1.0 - alpha)).astype(np.uint8)
    return cv2.cvtColor(flat, cv2.COLOR_RGB2BGR) if rgb else flat


def clear_image_cache():
    with _TEMPLATE_CACHE_LOCK:
        _TEMPLATE_CACHE.clear()
