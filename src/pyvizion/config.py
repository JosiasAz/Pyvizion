"""
pyvizion - Configuração

    >>> vz = Vizion(config={"confidence_threshold": 80, "tesseract_lang": "por"})
    >>> vz.config.get("confidence_threshold")
    80
    >>> vz.config.set("show_overlay", True)
    >>> vz.config.update({"retry_delay": 0.3})
"""

import json
import logging
from pathlib import Path

from .exceptions import SettingsError
from .settings import Settings

logger = logging.getLogger("pyvizion")

DEFAULTS = {
    "confidence_threshold": 75.0,     # limiar do OCR (0–100)
    "default_confidence": 0.9,        # confiança padrão de imagens nas tarefas
    "min_confidence": 0.7,            # piso ao reduzir a confiança entre tentativas
    "grayscale": True,                # matching em tons de cinza
    "scales": None,                   # escalas para specific=False (padrão 0,8–1,2)
    "dpi_scales": True,               # inclui a escala de cada monitor (125%, 150%)
    "edge_fallback": False,           # matching por bordas (tema claro/escuro)
    "image_folders": [],              # pastas onde procurar imagens
    "tesseract_path": None,
    "tesseract_data_path": None,
    "tesseract_lang": "eng",          # "eng", "por", "por+eng"
    "image_processing_methods": "all",       # "all", "balanced", "fast" ou lista
    "ocr_large_image_methods": "fast",       # técnicas usadas na tela inteira
    "preprocessing_enabled": True,
    "ocr_upscale": 2.0,
    "ocr_workers": None,
    "ocr_fuzzy": True,
    "ocr_fuzzy_threshold": 0.8,
    "retry_delay": 0.5,
    "timeout": 30.0,                  # espera padrão de wait_until_found / wait_until_disappears (s)
    "typing_mode": "paste",           # "paste" (clipboard) ou "type" (tecla a tecla)
    "restore_clipboard": True,
    "typing_interval": 0.02,
    "click_hold": 0.0,
    "move_pause": 0.15,
    "movement_duration": 0.1,
    "failsafe": True,                 # mouse no canto superior esquerdo interrompe
    "use_virtual_mouse": False,       # clique sem mover o cursor (Windows)
    "show_overlay": False,            # retângulo sobre o alvo antes do clique
    "overlay_enabled": True,
    "overlay_color": "red",
    "overlay_duration": 1000,
    "overlay_width": 4,
    "save_failure_screenshots": False,
    "failure_screenshot_dir": "pyvizion_failures",
    "stop_on_failure": False,
    "max_backtrack_attempts": 2,
    "log_level": "INFO",
}

ALIASES = {"tessdata_path": "tesseract_data_path", "wait_timeout": "timeout"}


class Config:
    """Configuração do pyvizion (dict com ``get``/``set``/``update``/``to_dict``)."""

    def __init__(self, values=None, on_change=None):
        self._values = dict(DEFAULTS)
        self._on_change = None
        if values:
            self.update(values)
        self._on_change = on_change

    # --- acesso ---------------------------------------------------------
    def get(self, key, default=None):
        return self._values.get(ALIASES.get(key, key), default)

    def set(self, key, value):
        self.update({key: value})

    def update(self, values):
        for key, value in dict(values).items():
            key = ALIASES.get(key, key)
            if key not in DEFAULTS:
                logger.warning(f"Configuração desconhecida ignorada: '{key}'")
                continue
            self._values[key] = value
        self.to_settings()  # valida já
        if self._on_change:
            self._on_change(self)

    def to_dict(self):
        return dict(self._values)

    def __getitem__(self, key):
        return self._values[ALIASES.get(key, key)]

    def __setitem__(self, key, value):
        self.set(key, value)

    def __getattr__(self, name):
        values = self.__dict__.get("_values")
        if values is not None and name in values:
            return values[name]
        raise AttributeError(f"Configuração '{name}' não existe")

    def __repr__(self):
        return f"Config({self._values!r})"

    # --- arquivo --------------------------------------------------------
    @classmethod
    def load(cls, path):
        """Lê um arquivo .json ou .yaml."""
        path = Path(path)
        if not path.is_file():
            raise SettingsError(f"Arquivo de configuração não encontrado: {path}")
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            data = json.loads(text)
        elif path.suffix.lower() in (".yml", ".yaml"):
            import yaml

            data = yaml.safe_load(text) or {}
        else:
            raise SettingsError(f"Formato não suportado: {path.suffix} (use .json ou .yaml)")
        return cls(data)

    def save(self, path):
        path = Path(path)
        path.write_text(json.dumps(self._values, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    # --- conversão para os motores -------------------------------------
    def to_settings(self) -> Settings:
        v = self._values
        methods = v["image_processing_methods"] if v["preprocessing_enabled"] else ["original"]
        try:
            return Settings(
                text_confidence=float(v["confidence_threshold"]),
                precision=float(v["default_confidence"]),
                min_precision=float(v["min_confidence"]),
                grayscale=bool(v["grayscale"]),
                scales=v["scales"],
                monitor_scaling=bool(v["dpi_scales"]),
                edge_matching=bool(v["edge_fallback"]),
                image_dirs=list(v["image_folders"] or []),
                tesseract=v["tesseract_path"],
                tessdata=v["tesseract_data_path"],
                language=v["tesseract_lang"],
                ocr_quality=methods,
                ocr_quality_fullscreen=v["ocr_large_image_methods"],
                ocr_upscale=float(v["ocr_upscale"]),
                ocr_threads=v["ocr_workers"],
                fuzzy=float(v["ocr_fuzzy_threshold"]) if v["ocr_fuzzy"] else 0.0,
                timeout=float(v["timeout"]),
                retry_pause=float(v["retry_delay"]),
                typing="keys" if v["typing_mode"] == "type" else "paste",
                keep_clipboard=bool(v["restore_clipboard"]),
                key_interval=float(v["typing_interval"]),
                click_hold=float(v["click_hold"]),
                settle=float(v["move_pause"]),
                move_time=float(v["movement_duration"]),
                emergency_stop=bool(v["failsafe"]),
                virtual_mouse=bool(v["use_virtual_mouse"]),
                highlight=bool(v["show_overlay"]) and bool(v["overlay_enabled"]),
                highlight_color=str(v["overlay_color"]).lower(),
                highlight_ms=int(v["overlay_duration"]),
                highlight_width=int(v["overlay_width"]),
                failure_shots=bool(v["save_failure_screenshots"]),
                failure_dir=str(v["failure_screenshot_dir"]),
                stop_on_failure=bool(v["stop_on_failure"]),
                recoveries=int(v["max_backtrack_attempts"]),
                log_level=str(v["log_level"]),
            )
        except (TypeError, ValueError) as e:
            raise SettingsError(f"Configuração inválida: {e}") from e
