"""
Ferramenta de autorização: marca uma região na tela e sugere trechos para o script.

Janela flutuante (estilo MouseInfo) controlada por clique — sem atalhos de teclado.
Fluxo principal: clica em «Selecionar região» → overlay congela a(s) tela(s) → arrasta.
"""

from __future__ import annotations

import re
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pyautogui

from ..core.highlight import highlight
from ..core.screen import (
    Region,
    enable_dpi_awareness,
    grab_screen,
    normalize_region,
    save_screenshot,
    virtual_screen_bounds,
)


_DELAY_CHOICES = ("Sem atraso", "5 segundos", "10 segundos", "15 segundos", "Personalizado")
_DELAY_PRESET = {"5 segundos": 5, "10 segundos": 10, "15 segundos": 15}


def _monitor_rects() -> list[Region]:
    """Retângulos de cada monitor físico (não a área virtual unificada)."""
    enable_dpi_awareness()
    try:
        import mss

        sct = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
        mons = sct.monitors[1:]
        if mons:
            return [Region(m["left"], m["top"], m["width"], m["height"]) for m in mons]
    except Exception:
        pass
    return [virtual_screen_bounds()]


def _force_window_rect(win: tk.Misc, x: int, y: int, w: int, h: int) -> None:
    """Posiciona overlay (sem borda) em coords virtuais, incl. monitores negativos."""
    win.geometry(f"{w}x{h}+{x}+{y}")
    win.update_idletasks()
    if sys.platform != "win32":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = win.winfo_id()
        parent = user32.GetParent(hwnd)
        if parent:
            hwnd = parent
        HWND_TOPMOST = -1
        SWP_SHOWWINDOW = 0x0040
        user32.SetWindowPos(hwnd, HWND_TOPMOST, int(x), int(y), int(w), int(h), SWP_SHOWWINDOW)
    except Exception:
        pass


def _place_panel(win: tk.Misc, x: int, y: int) -> None:
    """Só move o painel (não redefine o tamanho — evita cortar título/conteúdo)."""
    win.geometry(f"+{int(x)}+{int(y)}")
    win.update_idletasks()
    if sys.platform != "win32":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = win.winfo_id()
        parent = user32.GetParent(hwnd)
        if parent:
            hwnd = parent
        # SWP_NOSIZE | SWP_SHOWWINDOW — move sem redimensionar
        user32.SetWindowPos(hwnd, -1, int(x), int(y), 0, 0, 0x0001 | 0x0040)
    except Exception:
        pass


def _region_from_corners(p1: tuple[int, int], p2: tuple[int, int]) -> Region:
    x1, y1 = p1
    x2, y2 = p2
    left, top = min(x1, x2), min(y1, y2)
    width, height = abs(x2 - x1), abs(y2 - y1)
    if width < 2 or height < 2:
        raise ValueError("Região muito pequena — afaste os dois cantos.")
    return normalize_region((left, top, width, height))


def _next_image_path(directory: Path | None = None) -> Path:
    """Próximo nome livre: imagem1.png, imagem2.png, …"""
    folder = directory or Path.cwd()
    pattern = re.compile(r"^imagem(\d+)\.png$", re.IGNORECASE)
    highest = 0
    try:
        for path in folder.iterdir():
            match = pattern.match(path.name)
            if match:
                highest = max(highest, int(match.group(1)))
    except OSError:
        pass
    return folder / f"imagem{highest + 1}.png"


def _print_and_finish(region: Region, *, save_crop: str | None = None, ocr: bool = True) -> Region:
    """Destaca, salva recorte, OCR e imprime trecho pronto para colar."""
    highlight(region, "lime", 4, 1200, wait=True)

    x, y, w, h = tuple(region)
    out = Path(save_crop) if save_crop else _next_image_path()
    save_screenshot(str(out), region)

    text_preview = ""
    if ocr:
        try:
            from ..vizion import Vizion

            text_preview = Vizion().read_text(region, single_line=False).strip()
        except Exception as exc:
            text_preview = f"(OCR indisponível: {exc})"

    snippet = ""
    if text_preview and not text_preview.startswith("(OCR"):
        snippet = text_preview.splitlines()[0].replace('"', "'").strip()[:50]

    width = 56

    def _row(text: str = "") -> str:
        body = text[: width - 2]
        return f"│{body}{' ' * (width - 2 - len(body))}│"

    bar = "─" * (width - 2)
    print()
    print(f"┌{bar}┐")
    print(_row("  pyvizion pick"))
    print(f"├{bar}┤")
    print(_row(f"  region  ({x}, {y}, {w}, {h})"))
    print(_row(f"  imagem  {out.name}"))
    if text_preview:
        ocr_show = text_preview.replace("\n", " · ")
        if len(ocr_show) > 42:
            ocr_show = ocr_show[:39] + "..."
        print(_row(f"  ocr     {ocr_show}"))
    print(f"├{bar}┤")
    print(_row("  # cole no seu script"))
    print(_row())
    print(_row("  from pyvizion import Vizion"))
    print(_row("  bot = Vizion()"))
    print(_row())
    print(_row(f"  region = ({x}, {y}, {w}, {h})"))
    if snippet:
        print(_row(f'  bot.click_text("{snippet}", region=region)'))
    print(_row("  bot.read_text(region=region)"))
    print(_row(f'  bot.click_image("{out.name}", region=region)'))
    print(f"└{bar}┘")

    try:
        import pyperclip

        pyperclip.copy(f"({x}, {y}, {w}, {h})")
        print("  ✓  region copiada para a área de transferência")
    except Exception:
        pass
    print()

    return region


# ---------------------------------------------------------------------------
# Overlay: congela cada monitor — seleção só por clique/arraste
# ---------------------------------------------------------------------------

TOAST_MS = 1200  # popup central some em ~1,2s


def _show_center_toast(master: tk.Misc, text: str, ms: int = TOAST_MS) -> None:
    """Popup no centro do monitor do mouse; some sozinho antes do print."""
    try:
        mx, my = pyautogui.position()
    except Exception:
        mx, my = 100, 100
    host = _monitor_rects()[0]
    for mon in _monitor_rects():
        if mon.left <= mx < mon.left + mon.width and mon.top <= my < mon.top + mon.height:
            host = mon
            break

    toast = tk.Toplevel(master)
    toast.withdraw()
    toast.overrideredirect(True)
    try:
        toast.attributes("-topmost", True)
    except tk.TclError:
        pass
    frm = tk.Frame(toast, bg="#1e1e1e", padx=28, pady=18)
    frm.pack()
    tk.Label(
        frm,
        text=text,
        bg="#1e1e1e",
        fg="#ffffff",
        font=("Segoe UI", 13, "bold"),
    ).pack()
    toast.update_idletasks()
    tw, th = toast.winfo_reqwidth(), toast.winfo_reqheight()
    x = host.left + (host.width - tw) // 2
    y = host.top + (host.height - th) // 2
    toast.deiconify()
    _force_window_rect(toast, x, y, tw, th)
    toast.lift()

    done = tk.BooleanVar(master=master, value=False)

    def _close():
        try:
            toast.destroy()
        except tk.TclError:
            pass
        done.set(True)

    master.after(ms, _close)
    master.wait_variable(done)


class _DragSelectOverlay:
    """Uma janela fullscreen por monitor com a captura congelada.

    Args:
        allow_click: se True, um clique sem arrastar vira region 1×1 no ponto.
        point_only: se True, qualquer clique registra só o ponto (para Canto 1/2).
    """

    def __init__(self, master: tk.Tk, *, allow_click: bool = False, point_only: bool = False):
        self._master = master
        self._allow_click = allow_click or point_only
        self._point_only = point_only
        self.result: Region | None = None
        self._done = False
        self._start_screen: tuple[int, int] | None = None
        self._wins: list[tk.Toplevel] = []
        self._canvases: dict[int, tuple[tk.Canvas, Region]] = {}
        self._photos: list = []
        self._rects: dict[int, int] = {}
        self._active_cid: int | None = None

    def run(self) -> Region | None:
        enable_dpi_awareness()
        from PIL import ImageTk

        # aviso central curto — some antes do print (não cobre o topo da tela)
        _show_center_toast(self._master, "Capturando tela…", ms=900)

        monitors = _monitor_rects()
        print(f"  overlay em {len(monitors)} monitor(es)…")
        if self._point_only:
            hint = "Só clique no canto (não arraste)  ·  Esc = cancelar"
        elif self._allow_click:
            hint = "Clique = ponto  ·  Arraste = área"
        else:
            hint = "Arraste para marcar a região"

        for mon in monitors:
            try:
                img, origin = grab_screen(mon)
            except Exception as exc:
                print(f"  falha ao capturar monitor {tuple(mon)}: {exc}")
                continue

            left, top = int(origin[0]), int(origin[1])
            w, h = int(img.width), int(img.height)

            win = tk.Toplevel(self._master)
            win.withdraw()
            win.overrideredirect(True)
            try:
                win.attributes("-topmost", True)
            except tk.TclError:
                pass
            win.configure(cursor="crosshair", bg="#000000")
            self._wins.append(win)

            photo = ImageTk.PhotoImage(img, master=win)
            self._photos.append(photo)

            canvas = tk.Canvas(win, width=w, height=h, highlightthickness=0, cursor="crosshair", bg="#000")
            canvas.pack(fill="both", expand=True)
            canvas.create_image(0, 0, anchor="nw", image=photo)

            # toast central no overlay (some sozinho; não fica faixa no topo)
            self._draw_toast(canvas, w, h, hint)

            # Cancelar discreto no canto inferior direito
            btn = tk.Button(
                win,
                text="Cancelar",
                command=self._cancel,
                bg="#2a2a2a",
                fg="#dddddd",
                activebackground="#444444",
                activeforeground="#ffffff",
                relief="flat",
                padx=10,
                pady=2,
                cursor="hand2",
            )
            canvas.create_window(w - 56, h - 28, window=btn)

            cid = id(canvas)
            self._canvases[cid] = (canvas, Region(left, top, w, h))
            canvas.bind("<ButtonPress-1>", lambda e, c=cid: self._on_press(e, c))
            canvas.bind("<B1-Motion>", lambda e, c=cid: self._on_drag(e, c))
            canvas.bind("<ButtonRelease-1>", lambda e, c=cid: self._on_release(e, c))
            canvas.bind("<ButtonPress-3>", lambda _e: self._cancel())
            win.bind("<Escape>", lambda _e: self._cancel())
            win.protocol("WM_DELETE_WINDOW", self._cancel)

            win.deiconify()
            _force_window_rect(win, left, top, w, h)
            win.lift()
            try:
                win.attributes("-topmost", True)
            except tk.TclError:
                pass

        if not self._wins:
            print("  nenhum overlay pôde ser aberto.")
            return None

        self._master.update()
        self._master.wait_variable(self._wait_var())
        self._cancel_watch()
        self._close_all()
        return self.result

    def _draw_toast(self, canvas: tk.Canvas, w: int, h: int, text: str) -> None:
        pad_x, pad_y = 36, 18
        # mede texto
        tid = canvas.create_text(w // 2, h // 2, text=text, fill="#ffffff", font=("Segoe UI", 13, "bold"), tags="toast")
        bbox = canvas.bbox(tid)
        if bbox:
            x1, y1, x2, y2 = bbox
            rect = canvas.create_rectangle(
                x1 - pad_x,
                y1 - pad_y,
                x2 + pad_x,
                y2 + pad_y,
                fill="#1e1e1e",
                outline="#444444",
                width=1,
                tags="toast",
            )
            canvas.tag_raise(tid, rect)
        def _drop_toast():
            try:
                canvas.delete("toast")
            except tk.TclError:
                pass

        canvas.after(TOAST_MS, _drop_toast)

    def _wait_var(self) -> tk.Variable:
        self._var = tk.BooleanVar(master=self._master, value=False)
        self._watch_after = None

        def _watch():
            self._watch_after = None
            if self._done or not self._wins:
                try:
                    self._var.set(True)
                except tk.TclError:
                    pass
                return
            for win in self._wins:
                try:
                    if win.winfo_exists():
                        win.attributes("-topmost", True)
                except tk.TclError:
                    pass
            try:
                self._watch_after = self._master.after(200, _watch)
            except tk.TclError:
                pass

        _watch()
        return self._var

    def _cancel_watch(self):
        job = getattr(self, "_watch_after", None)
        if job is not None:
            try:
                self._master.after_cancel(job)
            except (tk.TclError, Exception):
                pass
            self._watch_after = None

    def _finish(self):
        self._done = True
        self._cancel_watch()
        try:
            self._var.set(True)
        except Exception:
            pass

    def _to_screen(self, cid: int, event_x: int, event_y: int) -> tuple[int, int]:
        _, region = self._canvases[cid]
        return region.left + int(event_x), region.top + int(event_y)

    def _on_press(self, event, cid: int):
        # não inicia seleção em cima do botão Cancelar (canto inferior direito)
        canvas, region = self._canvases[cid]
        if event.x > region.width - 120 and event.y > region.height - 56:
            return
        # some o toast ao começar a arrastar
        canvas.delete("toast")
        self._active_cid = cid
        self._start_screen = self._to_screen(cid, event.x, event.y)
        for other, rid in list(self._rects.items()):
            other_canvas, _ = self._canvases[other]
            try:
                other_canvas.delete(rid)
            except tk.TclError:
                pass
        self._rects.clear()

    def _on_drag(self, event, cid: int):
        if self._point_only:
            return  # canto 1/2: só clique, sem arrastar
        if self._start_screen is None or cid != self._active_cid:
            return
        canvas, region = self._canvases[cid]
        x0 = self._start_screen[0] - region.left
        y0 = self._start_screen[1] - region.top
        if cid in self._rects:
            canvas.delete(self._rects[cid])
        self._rects[cid] = canvas.create_rectangle(
            x0, y0, event.x, event.y, outline="#39FF14", width=3, fill="#39FF14", stipple="gray25"
        )

    def _on_release(self, event, cid: int):
        if self._start_screen is None or cid != self._active_cid:
            return
        # modo canto: ponto = onde apertou (clique simples; arraste ignorado)
        if self._point_only:
            sx, sy = self._start_screen
            self.result = normalize_region((sx, sy, 1, 1), clamp=True)
            self._finish()
            return
        p2 = self._to_screen(cid, event.x, event.y)
        dx = abs(p2[0] - self._start_screen[0])
        dy = abs(p2[1] - self._start_screen[1])
        # clique sem arrastar → ponto 1×1 (só se allow_click)
        if self._allow_click and dx < 4 and dy < 4:
            sx, sy = self._start_screen
            self.result = normalize_region((sx, sy, 1, 1), clamp=True)
            self._finish()
            return
        try:
            self.result = _region_from_corners(self._start_screen, p2)
        except ValueError:
            self._start_screen = None
            msg = "Clique ou arraste a área" if self._allow_click else "Área muito pequena — arraste de novo"
            self._status_hint(cid, msg)
            return
        self._finish()

    def _status_hint(self, cid: int, text: str):
        canvas, region = self._canvases[cid]
        canvas.create_text(
            region.width // 2,
            region.height // 2,
            text=text,
            fill="#ff6666",
            font=("Segoe UI", 11, "bold"),
            tags="hint",
        )
        canvas.after(1200, lambda: canvas.delete("hint"))

    def _cancel(self):
        self.result = None
        self._finish()

    def _close_all(self):
        for win in list(self._wins):
            try:
                win.destroy()
            except tk.TclError:
                pass
        self._wins.clear()
        self._photos.clear()


# ---------------------------------------------------------------------------
# Painel flutuante — só clique
# ---------------------------------------------------------------------------


class _PickWindow:
    """Painel always-on-top: XY ao vivo + botões (sem atalhos)."""

    def __init__(self, *, save_crop: str | None = None, ocr: bool = True):
        self.save_crop = save_crop
        self.ocr = ocr
        self.region: Region | None = None
        self._corner1: tuple[int, int] | None = None
        self._countdown_job: str | None = None
        self._busy = False

        enable_dpi_awareness()
        self.root = tk.Tk()
        self.root.title("pyvizion pick")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        self._xy = tk.StringVar(value="x=0  y=0")
        self._status = tk.StringVar(value="Clique em «Selecionar região» — captura na hora.")
        self._delay_choice = tk.StringVar(value="Sem atraso")
        self._custom_delay = tk.StringVar(value="5")
        self._c1_label = tk.StringVar(value="Canto 1: —")
        self._c2_label = tk.StringVar(value="Canto 2: —")

        frm = ttk.Frame(self.root, padding=(16, 14))
        frm.grid(row=0, column=0, sticky="nsew")
        frm.columnconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, textvariable=self._xy, font=("Consolas", 16, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        delay_row = ttk.Frame(frm)
        delay_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Label(delay_row, text="Atraso").pack(side="left")
        self._delay_combo = ttk.Combobox(
            delay_row,
            textvariable=self._delay_choice,
            values=_DELAY_CHOICES,
            state="readonly",
            width=14,
        )
        self._delay_combo.pack(side="left", padx=(8, 4))
        self._delay_combo.bind("<<ComboboxSelected>>", self._on_delay_choice)
        self._custom_spin = ttk.Spinbox(
            delay_row,
            from_=1,
            to=120,
            textvariable=self._custom_delay,
            width=5,
            state="disabled",
        )
        self._custom_spin.pack(side="left")
        ttk.Label(delay_row, text="s").pack(side="left", padx=(2, 0))

        ttk.Button(frm, text="Selecionar região", command=self._start_drag).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(10, 8)
        )

        ttk.Separator(frm).grid(row=3, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Label(frm, text="Ou dois cantos (botão → depois clique na tela)").grid(
            row=4, column=0, columnspan=2, sticky="w"
        )
        ttk.Button(frm, text="Canto 1", command=lambda: self._schedule_corner(1)).grid(
            row=5, column=0, sticky="ew", padx=(0, 4), pady=4
        )
        ttk.Button(frm, text="Canto 2", command=lambda: self._schedule_corner(2)).grid(
            row=5, column=1, sticky="ew", padx=(4, 0), pady=4
        )
        ttk.Label(frm, textvariable=self._c1_label).grid(row=6, column=0, sticky="w", pady=2)
        ttk.Label(frm, textvariable=self._c2_label).grid(row=6, column=1, sticky="w", pady=2)

        ttk.Separator(frm).grid(row=7, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Label(frm, textvariable=self._status, wraplength=300).grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        ttk.Button(frm, text="Fechar", command=self._cancel).grid(
            row=9, column=0, columnspan=2, sticky="ew"
        )

        self.root.protocol("WM_DELETE_WINDOW", self._cancel)
        self._tick_xy()
        self._place_near_mouse()

    def run(self) -> Region | None:
        print("pyvizion pick — use os botões da janela (clique)")
        print("  1) Clique em «Selecionar região» e arraste a área")
        print("  2) Ou: «Canto 1» → clique na tela → «Canto 2» → clique na tela")
        print("  3) Opcional: atraso 5/10/15s antes de abrir o overlay\n")
        self.root.mainloop()
        return self.region

    def _on_delay_choice(self, _event=None):
        custom = self._delay_choice.get() == "Personalizado"
        self._custom_spin.configure(state="normal" if custom else "disabled")

    def _delay_seconds(self) -> int:
        choice = self._delay_choice.get()
        if choice == "Sem atraso":
            return 0
        if choice in _DELAY_PRESET:
            return _DELAY_PRESET[choice]
        try:
            return max(1, min(120, int(self._custom_delay.get())))
        except (TypeError, ValueError):
            return 5

    def _place_near_mouse(self):
        self.root.update_idletasks()
        ww = self.root.winfo_reqwidth()
        wh = self.root.winfo_reqheight()
        try:
            mx, my = pyautogui.position()
        except Exception:
            mx, my = 100, 100
        host = _monitor_rects()[0]
        for mon in _monitor_rects():
            if mon.left <= mx < mon.left + mon.width and mon.top <= my < mon.top + mon.height:
                host = mon
                break
        x = host.left + max(20, host.width - ww - 40)
        y = host.top + max(20, host.height - wh - 80)
        _place_panel(self.root, x, y)

    def _tick_xy(self):
        try:
            x, y = pyautogui.position()
            self._xy.set(f"x={int(x)}  y={int(y)}")
        except Exception:
            pass
        try:
            if self.root.winfo_exists():
                self.root.after(50, self._tick_xy)
        except tk.TclError:
            pass

    def _cancel_countdown(self):
        if self._countdown_job is not None:
            try:
                self.root.after_cancel(self._countdown_job)
            except Exception:
                pass
            self._countdown_job = None

    def _after_delay(self, action, label: str):
        if self._busy:
            return
        self._cancel_countdown()
        seconds = self._delay_seconds()
        if seconds <= 0:
            action()
            return

        remaining = {"n": seconds}

        def tick():
            n = remaining["n"]
            if n <= 0:
                self._countdown_job = None
                self._status.set(label)
                action()
                return
            self._status.set(f"{label} em {n}s… vá até a tela alvo.")
            remaining["n"] = n - 1
            self._countdown_job = self.root.after(1000, tick)

        tick()

    def _start_drag(self):
        def do():
            if self._busy:
                return
            self._busy = True
            self._status.set("Abrindo overlay…")
            # esconde o painel para não aparecer no print / atrapalhar
            self.root.withdraw()
            self.root.update_idletasks()
            self.root.after(150, self._run_drag)

        self._after_delay(do, "Congelando tela")

    def _run_drag(self):
        region = None
        try:
            region = _DragSelectOverlay(self.root).run()
        except Exception as exc:
            print(f"  erro no overlay: {exc}")
            self._status.set(f"Erro no overlay: {exc}")
        finally:
            self._busy = False
            try:
                self.root.deiconify()
                self.root.attributes("-topmost", True)
                self.root.lift()
            except tk.TclError:
                pass

        if region is None:
            self._status.set("Seleção cancelada. Clique de novo em «Selecionar região».")
            return
        self._done(region)

    def _schedule_corner(self, which: int):
        """Abre overlay e espera o próximo clique na tela (não usa a posição do botão)."""

        def do():
            if self._busy:
                return
            self._busy = True
            self._status.set(f"Clique na tela no canto {which}…")
            self.root.withdraw()
            self.root.update_idletasks()
            self.root.after(150, lambda: self._run_corner(which))

        self._after_delay(do, f"Preparando canto {which}")

    def _run_corner(self, which: int):
        region = None
        try:
            region = _DragSelectOverlay(self.root, point_only=True).run()
        except Exception as exc:
            print(f"  erro ao marcar canto {which}: {exc}")
            self._status.set(f"Erro no canto {which}: {exc}")
        finally:
            self._busy = False
            try:
                self.root.deiconify()
                self.root.attributes("-topmost", True)
                self.root.lift()
            except tk.TclError:
                pass

        if region is None:
            self._status.set(f"Canto {which} cancelado. Clique de novo em «Canto {which}».")
            return

        pt = (int(region.left), int(region.top))
        if which == 1:
            self._corner1 = pt
            self._c1_label.set(f"Canto 1: {pt}")
            self._status.set(f"Canto 1 = {pt}. Agora clique em «Canto 2» e marque o outro canto.")
            print(f"  -> canto 1: x={pt[0]}, y={pt[1]}")
            return

        self._c2_label.set(f"Canto 2: {pt}")
        print(f"  -> canto 2: x={pt[0]}, y={pt[1]}")
        if self._corner1 is None:
            self._status.set("Marque o canto 1 antes (botão «Canto 1»).")
            return
        try:
            done = _region_from_corners(self._corner1, pt)
        except ValueError as exc:
            self._status.set(str(exc))
            return
        self._done(done)

    def _done(self, region: Region):
        self.region = region
        self._cancel_countdown()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _cancel(self):
        self.region = None
        self._cancel_countdown()
        try:
            self.root.destroy()
        except tk.TclError:
            pass


# ---------------------------------------------------------------------------
# Fluxo legado (Enter no terminal) e API pública
# ---------------------------------------------------------------------------


def _read_point(prompt: str) -> tuple[int, int]:
    input(prompt)
    x, y = pyautogui.position()
    print(f"  -> x={x}, y={y}")
    return int(x), int(y)


def run_pick_terminal(*, save_crop: str | None = None, ocr: bool = True) -> Region:
    """Fluxo antigo: dois Enters no terminal."""
    enable_dpi_awareness()
    print("pyvizion pick — marque uma região pelo terminal\n")
    print("  1) Leve o mouse ao canto SUPERIOR ESQUERDO e pressione Enter")
    print("  2) Leve o mouse ao canto INFERIOR DIREITO e pressione Enter\n")

    p1 = _read_point("Enter no canto 1... ")
    p2 = _read_point("Enter no canto 2... ")
    region = _region_from_corners(p1, p2)
    return _print_and_finish(region, save_crop=save_crop, ocr=ocr)


def run_pick(*, save_crop: str | None = None, ocr: bool = True, terminal: bool = False) -> Region:
    """
    Marca uma região na tela.

    Por padrão: janela flutuante + overlay por clique/arraste.
    Use ``terminal=True`` para o fluxo antigo com Enter.
    """
    if terminal or not _tk_available():
        return run_pick_terminal(save_crop=save_crop, ocr=ocr)

    win = _PickWindow(save_crop=save_crop, ocr=ocr)
    region = win.run()
    if region is None:
        raise KeyboardInterrupt
    return _print_and_finish(region, save_crop=save_crop, ocr=ocr)


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:
        return False


def run_position_live(*, terminal: bool = False) -> None:
    """Posição do mouse ao vivo — janela flutuante (ou terminal com ``terminal=True``)."""
    if not terminal and _tk_available():
        from .panels import run_position_gui

        run_position_gui()
        return

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
    terminal = False
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
        if argv[i] in ("--terminal", "-t"):
            terminal = True
            i += 1
            continue
        print(f"argumento desconhecido: {argv[i]!r}")
        print("uso: pyvizion pick [--save recorte.png] [--no-ocr] [--terminal]")
        return 2
    try:
        run_pick(save_crop=save, ocr=not no_ocr, terminal=terminal)
    except (KeyboardInterrupt, EOFError):
        print("\ncancelado.")
        return 130
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0
