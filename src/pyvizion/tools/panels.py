"""
Painéis flutuantes (estilo MouseInfo) para os comandos CLI interativos.

Usados por: position, ocr, print, windows.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pyautogui

from ..core.screen import enable_dpi_awareness, save_screenshot
from .pick_region import (
    _DragSelectOverlay,
    _monitor_rects,
    _place_panel,
    _tk_available,
)


def _copy(text: str) -> bool:
    try:
        import pyperclip

        pyperclip.copy(text)
        return True
    except Exception:
        return False


def _setup_root(title: str) -> tk.Tk:
    enable_dpi_awareness()
    root = tk.Tk()
    root.title(title)
    root.attributes("-topmost", True)
    root.resizable(False, False)
    return root


def _place_near_mouse(root: tk.Tk, *, pad_right: int = 40, pad_bottom: int = 80) -> None:
    root.update_idletasks()
    ww, wh = root.winfo_reqwidth(), root.winfo_reqheight()
    try:
        mx, my = pyautogui.position()
    except Exception:
        mx, my = 100, 100
    host = _monitor_rects()[0]
    for mon in _monitor_rects():
        if mon.left <= mx < mon.left + mon.width and mon.top <= my < mon.top + mon.height:
            host = mon
            break
    x = host.left + max(20, host.width - ww - pad_right)
    y = host.top + max(20, host.height - wh - pad_bottom)
    _place_panel(root, x, y)


# ---------------------------------------------------------------------------
# position
# ---------------------------------------------------------------------------


_COPY_CHOICES = ("Region", "XY", "RGB", "Tudo")


def _mouse_left_down() -> bool:
    try:
        import ctypes

        return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
    except Exception:
        return False


class _PositionWindow:
    """XY ao vivo. Region → overlay (clique/arraste); XY/RGB/Tudo → próximo clique."""

    def __init__(self):
        self.root = _setup_root("pyvizion position")
        self._xy = tk.StringVar(value="x=0  y=0")
        self._region = tk.StringVar(value="region = (0, 0, 1, 1)")
        self._rgb = tk.StringVar(value="RGB —")
        self._copy_what = tk.StringVar(value="Region")
        self._status = tk.StringVar(
            value="Region: overlay (clique ou arraste) · Outros: próximo clique na tela"
        )

        self._last_xy = (0, 0)
        self._last_rgb = (0, 0, 0)
        self._selected_region = None
        self._rgb_tick = 0
        self._busy = False
        self._armed = False
        self._wait_release = False

        frm = ttk.Frame(self.root, padding=(16, 14))
        frm.grid(row=0, column=0, sticky="nsew")
        frm.columnconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, textvariable=self._xy, font=("Consolas", 18, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(frm, textvariable=self._region, font=("Consolas", 10)).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 8)
        )

        color_row = ttk.Frame(frm)
        color_row.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self._swatch = tk.Canvas(
            color_row, width=22, height=22, highlightthickness=1, highlightbackground="#999"
        )
        self._swatch.pack(side="left")
        self._swatch.create_rectangle(0, 0, 22, 22, fill="#000000", outline="", tags="swatch")
        ttk.Label(color_row, textvariable=self._rgb, font=("Consolas", 10)).pack(side="left", padx=(8, 0))

        choice_row = ttk.Frame(frm)
        choice_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(choice_row, text="Copiar").pack(side="left")
        combo = ttk.Combobox(
            choice_row,
            textvariable=self._copy_what,
            values=_COPY_CHOICES,
            state="readonly",
            width=12,
        )
        combo.pack(side="left", padx=(8, 0))
        combo.bind("<<ComboboxSelected>>", self._on_copy_choice)

        ttk.Button(frm, text="Copiar no próximo clique", command=self._on_main_action).grid(
            row=4, column=0, columnspan=2, sticky="ew"
        )

        ttk.Label(frm, textvariable=self._status, wraplength=320).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(10, 8)
        )
        ttk.Button(frm, text="Fechar", command=self.root.destroy).grid(
            row=6, column=0, columnspan=2, sticky="ew"
        )

        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self._tick()
        _place_near_mouse(self.root)

    def run(self) -> None:
        print("pyvizion position — janela flutuante aberta")
        print("  Region → overlay (clique = ponto, arraste = área)")
        print("  XY / RGB / Tudo → próximo clique na tela\n")
        self.root.mainloop()

    def _on_copy_choice(self, _event=None):
        self._armed = False
        if self._copy_what.get() == "Region":
            self._status.set("Region: clique no botão → overlay (clique ou arraste)")
        else:
            self._status.set(f"{self._copy_what.get()}: clique no botão, depois clique na tela")

    def _on_main_action(self):
        """Region abre overlay; demais opções armam o próximo clique."""
        if self._copy_what.get() == "Region":
            self._start_region_overlay()
        else:
            self._arm_click()

    def _point_data(self):
        if self._selected_region is not None:
            x, y, w, h = self._selected_region
            cx, cy = x + w // 2, y + h // 2
            return (cx, cy), self._selected_region, self._last_rgb
        x, y = self._last_xy
        return (x, y), (x, y, 1, 1), self._last_rgb

    def _format_payload(self) -> str:
        (x, y), region, (r, g, b) = self._point_data()
        rx, ry, rw, rh = region
        what = self._copy_what.get()
        if what == "XY":
            return f"{x}, {y}"
        if what == "RGB":
            return f"({r}, {g}, {b})"
        if what == "Tudo":
            return (
                f"xy = ({x}, {y})\n"
                f"region = ({rx}, {ry}, {rw}, {rh})\n"
                f"rgb = ({r}, {g}, {b})  #{r:02X}{g:02X}{b:02X}"
            )
        return f"({rx}, {ry}, {rw}, {rh})"

    def _do_copy(self) -> None:
        text = self._format_payload()
        what = self._copy_what.get()
        ok = _copy(text)
        preview = text.replace("\n", " | ")
        if len(preview) > 80:
            preview = preview[:77] + "..."
        label = "copiado" if ok else "clipboard falhou"
        self._status.set(f"{what} {label}: {preview}")
        print(f"  -> [{what}] {text.replace(chr(10), ' | ')}")

    def _sample_rgb_at(self, x: int, y: int) -> None:
        try:
            from ..core.screen import grab_screen

            img, _ = grab_screen((x, y, 1, 1))
            r, g, b = img.getpixel((0, 0))
            self._last_rgb = (r, g, b)
            self._rgb.set(f"RGB ({r}, {g}, {b})  #{r:02X}{g:02X}{b:02X}")
            self._swatch.itemconfig("swatch", fill=f"#{r:02x}{g:02x}{b:02x}")
        except Exception:
            self._rgb.set("RGB —")

    def _start_region_overlay(self):
        """Region: overlay automático — clique = ponto, arraste = área."""
        if self._busy:
            return
        self._armed = False
        self._busy = True
        self._status.set("Overlay… clique = ponto · arraste = área")
        self.root.withdraw()
        self.root.update_idletasks()
        self.root.after(120, self._run_region_overlay)

    def _run_region_overlay(self):
        region = None
        try:
            region = _DragSelectOverlay(self.root, allow_click=True).run()
        except Exception as exc:
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
            self._status.set("Cancelado. Tente de novo.")
            return

        x, y, w, h = [int(v) for v in tuple(region)[:4]]
        self._selected_region = (x, y, w, h)
        cx, cy = x + w // 2, y + h // 2
        self._last_xy = (cx, cy)
        if w <= 1 and h <= 1:
            self._xy.set(f"x={x}  y={y}")
        else:
            self._xy.set(f"x={cx}  y={cy}  (centro)")
        self._region.set(f"region = ({x}, {y}, {w}, {h})")
        self._sample_rgb_at(cx, cy)
        self._do_copy()

    def _arm_click(self):
        """XY / RGB / Tudo: copia no próximo clique na tela."""
        self._selected_region = None
        self._armed = True
        self._wait_release = _mouse_left_down()
        what = self._copy_what.get()
        self._status.set(f"Aguardando clique… vai copiar {what}")

    def _on_capture_click(self):
        self._armed = False
        self._wait_release = False
        # amostra RGB no ponto do clique antes de copiar
        x, y = self._last_xy
        self._sample_rgb_at(x, y)
        self._do_copy()

    def _tick(self):
        if self._busy:
            try:
                if self.root.winfo_exists():
                    self.root.after(30, self._tick)
            except tk.TclError:
                pass
            return
        try:
            x, y = pyautogui.position()
            x, y = int(x), int(y)
            self._last_xy = (x, y)
            if self._selected_region is None:
                self._xy.set(f"x={x}  y={y}")
                self._region.set(f"region = ({x}, {y}, 1, 1)")

            if self._armed:
                down = _mouse_left_down()
                if self._wait_release:
                    if not down:
                        self._wait_release = False
                elif down:
                    self._on_capture_click()

            self._rgb_tick += 1
            if self._rgb_tick >= 3 and self._selected_region is None:
                self._rgb_tick = 0
                self._sample_rgb_at(x, y)
        except Exception:
            pass
        try:
            if self.root.winfo_exists():
                self.root.after(30, self._tick)
        except tk.TclError:
            pass


def run_position_gui() -> None:
    if not _tk_available():
        from .pick_region import run_position_live

        run_position_live(terminal=True)
        return
    _PositionWindow().run()


# ---------------------------------------------------------------------------
# ocr
# ---------------------------------------------------------------------------


class _OcrResultWindow:
    def __init__(self, region, text: str):
        self.root = _setup_root("pyvizion ocr")
        x, y, w, h = tuple(region)[:4]
        frm = ttk.Frame(self.root, padding=(16, 14))
        frm.grid(row=0, column=0, sticky="nsew")
        frm.columnconfigure(0, weight=1)

        ttk.Label(frm, text=f"region = ({x}, {y}, {w}, {h})", font=("Consolas", 10)).grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )

        box = tk.Text(frm, width=48, height=10, wrap="word", font=("Consolas", 10), relief="solid", borderwidth=1)
        box.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        box.insert("1.0", text or "(nenhum texto detectado)")
        box.configure(state="disabled")
        self._text = text or ""

        status = tk.StringVar(value="")
        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        btns.columnconfigure(0, weight=1)
        btns.columnconfigure(1, weight=1)

        def copy_text():
            status.set("Texto copiado" if _copy(self._text) else "Nada para copiar")

        def copy_region():
            status.set("region copiada" if _copy(f"({x}, {y}, {w}, {h})") else "")

        ttk.Button(btns, text="Copiar texto", command=copy_text).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(btns, text="Copiar region", command=copy_region).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        ttk.Label(frm, textvariable=status).grid(row=3, column=0, sticky="w", pady=(0, 8))
        ttk.Button(frm, text="Fechar", command=self.root.destroy).grid(row=4, column=0, sticky="ew")
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        _place_near_mouse(self.root)

    def run(self):
        self.root.mainloop()


def run_ocr_gui(region=None) -> int:
    enable_dpi_awareness()
    if region is None:
        if not _tk_available():
            print("uso: pyvizion ocr x y largura altura")
            return 2
        root = _setup_root("pyvizion ocr")
        root.withdraw()
        print("pyvizion ocr — marque a região no overlay\n")
        try:
            region = _DragSelectOverlay(root, allow_click=True).run()
        finally:
            try:
                root.update_idletasks()
                root.destroy()
            except tk.TclError:
                pass
        if region is None:
            print("cancelado.")
            return 130

    from ..vizion import Vizion

    x, y, w, h = [int(v) for v in tuple(region)[:4]]
    try:
        text = Vizion().read_text((x, y, w, h), single_line=False)
    except Exception as exc:
        text = f"(OCR indisponível: {exc})"

    print(f"region = ({x}, {y}, {w}, {h})")
    print(text or "(nenhum texto detectado)")

    # nova raiz limpa para o resultado (evita after órfão da captura)
    if _tk_available():
        _OcrResultWindow((x, y, w, h), text).run()
    return 0


# ---------------------------------------------------------------------------
# print
# ---------------------------------------------------------------------------


class _PrintResultWindow:
    def __init__(self, path: str, *, region=None):
        self.root = _setup_root("pyvizion print")
        self.path = str(Path(path).resolve())
        frm = ttk.Frame(self.root, padding=(16, 14))
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text="Print salvo", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(frm, text=self.path, wraplength=360, font=("Consolas", 9)).grid(
            row=1, column=0, sticky="w", pady=(6, 8)
        )
        if region is not None:
            x, y, w, h = tuple(region)[:4]
            ttk.Label(frm, text=f"region = ({x}, {y}, {w}, {h})", font=("Consolas", 9)).grid(
                row=2, column=0, sticky="w", pady=(0, 10)
            )
        status = tk.StringVar(value="")

        def copy_path():
            status.set("Caminho copiado" if _copy(self.path) else self.path)

        ttk.Button(frm, text="Copiar caminho", command=copy_path).grid(row=3, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(frm, textvariable=status).grid(row=4, column=0, sticky="w", pady=(0, 8))
        ttk.Button(frm, text="Fechar", command=self.root.destroy).grid(row=5, column=0, sticky="ew")
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        _place_near_mouse(self.root)

    def run(self):
        self.root.mainloop()


class _PrintChooserWindow:
    """Escolhe: tela completa ou área (overlay)."""

    def __init__(self, path: str | None = None):
        self.path_arg = path
        self.saved: str | None = None
        self.region = None
        self._busy = False

        self.root = _setup_root("pyvizion print")
        self._status = tk.StringVar(value="Escolha o tipo de captura")
        self._path_var = tk.StringVar(value=path or "")

        frm = ttk.Frame(self.root, padding=(16, 14))
        frm.grid(row=0, column=0, sticky="nsew")
        frm.columnconfigure(0, weight=1)

        ttk.Label(frm, text="Arquivo (opcional)", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self._path_var, width=42).grid(row=1, column=0, sticky="ew", pady=(2, 12))
        ttk.Label(frm, text="Deixe vazio para nome automático (.png)", font=("Segoe UI", 8)).grid(
            row=2, column=0, sticky="w", pady=(0, 10)
        )

        ttk.Button(frm, text="Tela completa", command=self._full).grid(row=3, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(frm, text="Selecionar área", command=self._area).grid(row=4, column=0, sticky="ew")

        ttk.Label(frm, textvariable=self._status, wraplength=340).grid(
            row=5, column=0, sticky="w", pady=(12, 8)
        )
        ttk.Button(frm, text="Fechar", command=self._cancel).grid(row=6, column=0, sticky="ew")
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)
        _place_near_mouse(self.root)

    def run(self) -> tuple[str | None, object]:
        print("pyvizion print — escolha na janela: tela completa ou área\n")
        self.root.mainloop()
        return self.saved, self.region

    def _target_path(self) -> str | None:
        raw = self._path_var.get().strip()
        return raw or None

    def _save(self, region=None) -> bool:
        from ..exceptions import VizionError

        try:
            self.saved = save_screenshot(self._target_path(), region=region)
            self.region = region
            print(self.saved)
            return True
        except VizionError as exc:
            self._status.set(str(exc).splitlines()[0])
            print(f"erro: {exc}", file=sys.stderr)
            return False
        except Exception as exc:
            self._status.set(f"Erro: {exc}")
            print(f"erro ao salvar print: {exc}", file=sys.stderr)
            return False

    def _full(self):
        if self._busy:
            return
        self._status.set("Capturando tela completa…")
        self.root.withdraw()
        self.root.update_idletasks()
        self.root.after(150, self._do_full)

    def _restore_panel(self):
        try:
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self.root.lift()
        except tk.TclError:
            pass

    def _close_panel(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _do_full(self):
        if self._save(region=None):
            self._close_panel()
        else:
            self._restore_panel()

    def _area(self):
        if self._busy:
            return
        self._busy = True
        self._status.set("Overlay… clique ou arraste a área")
        self.root.withdraw()
        self.root.update_idletasks()
        self.root.after(120, self._do_area)

    def _do_area(self):
        region = None
        try:
            region = _DragSelectOverlay(self.root, allow_click=True).run()
        except Exception as exc:
            self._status.set(f"Erro no overlay: {exc}")
            self._busy = False
            self._restore_panel()
            return
        finally:
            self._busy = False

        if region is None:
            self._restore_panel()
            self._status.set("Cancelado. Escolha de novo.")
            return

        if self._save(region=region):
            self._close_panel()
        else:
            self._restore_panel()

    def _cancel(self):
        self.saved = None
        self._close_panel()


def run_screenshot_gui(path: str | None = None) -> int:
    enable_dpi_awareness()
    if not _tk_available():
        from ..exceptions import VizionError

        try:
            out = save_screenshot(path)
        except VizionError as exc:
            print(f"erro: {exc}", file=sys.stderr)
            return 2
        print(out)
        return 0

    saved, region = _PrintChooserWindow(path).run()
    if not saved:
        print("cancelado.")
        return 130
    _PrintResultWindow(saved, region=region).run()
    return 0


# ---------------------------------------------------------------------------
# windows
# ---------------------------------------------------------------------------


class _WindowsListWindow:
    def __init__(self, titles: list[str]):
        self.root = _setup_root("pyvizion windows")
        self.root.resizable(True, True)
        frm = ttk.Frame(self.root, padding=(16, 14))
        frm.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(0, weight=1)

        list_frm = ttk.Frame(frm)
        list_frm.grid(row=0, column=0, sticky="nsew")
        list_frm.columnconfigure(0, weight=1)
        list_frm.rowconfigure(0, weight=1)
        scroll = ttk.Scrollbar(list_frm)
        scroll.grid(row=0, column=1, sticky="ns")
        self._list = tk.Listbox(
            list_frm, width=56, height=16, font=("Segoe UI", 10), yscrollcommand=scroll.set
        )
        self._list.grid(row=0, column=0, sticky="nsew")
        scroll.configure(command=self._list.yview)
        for title in titles:
            self._list.insert("end", title)

        status = tk.StringVar(value=f"{len(titles)} janela(s)")
        btns = ttk.Frame(frm)
        btns.grid(row=1, column=0, sticky="ew", pady=(10, 6))
        btns.columnconfigure(0, weight=1)
        btns.columnconfigure(1, weight=1)

        def copy_sel():
            sel = self._list.curselection()
            if not sel:
                status.set("Selecione um título")
                return
            text = self._list.get(sel[0])
            status.set("Título copiado" if _copy(text) else text)

        def copy_all():
            status.set("Lista copiada" if _copy("\n".join(titles)) else "")

        ttk.Button(btns, text="Copiar selecionado", command=copy_sel).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(btns, text="Copiar todos", command=copy_all).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        ttk.Label(frm, textvariable=status).grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Button(frm, text="Fechar", command=self.root.destroy).grid(row=3, column=0, sticky="ew")
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        _place_near_mouse(self.root)

    def run(self):
        self.root.mainloop()


def run_windows_gui() -> int:
    from ..core.windows import list_windows

    titles = [title for _, title in list_windows() if title and title.strip()]
    for t in titles:
        print(t)
    if _tk_available():
        _WindowsListWindow(titles).run()
    return 0
