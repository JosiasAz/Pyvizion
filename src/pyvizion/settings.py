"""
pyvizion - Configurações internas dos motores.

O usuário configura pelo dict ``config`` (chaves em ``config.py``); este módulo
é a forma validada que os motores leem.
"""

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from .exceptions import SettingsError

HIGHLIGHT_COLORS = ("red", "blue", "green", "yellow", "purple", "orange",
                    "cyan", "magenta", "white", "black")
OCR_QUALITIES = ("fast", "balanced", "all")


@dataclass
class Settings:
    # --- imagens ---------------------------------------------------------
    precision: float = 0.9
    """Semelhança mínima (0–1) para aceitar uma imagem."""
    min_precision: float = 0.7
    """Piso: a cada nova tentativa a precisão cai 0.05 até este valor."""
    grayscale: bool = True
    """Compara em tons de cinza (tolera hover/seleção/cores levemente diferentes)."""
    scales: Optional[Tuple[float, ...]] = None
    """Escalas testadas em ``Image(flexible=True)``. Padrão: 0.80 a 1.20."""
    monitor_scaling: bool = True
    """Inclui a escala de cada monitor (125%, 150%...) na busca."""
    edge_matching: bool = False
    """Último recurso por bordas (troca de tema claro/escuro)."""
    image_dirs: List[str] = field(default_factory=list)
    """Pastas onde procurar arquivos de imagem com caminho relativo."""

    # --- texto (OCR) -----------------------------------------------------
    text_confidence: float = 70.0
    """Confiança mínima (0–100) para aceitar um texto de imediato."""
    tesseract: Optional[str] = None
    """Caminho do executável do Tesseract (detectado automaticamente)."""
    tessdata: Optional[str] = None
    """Pasta ``tessdata`` (detectada automaticamente)."""
    language: Optional[str] = "eng"
    """Idioma(s) do OCR. Padrão: ``"eng"``. Use ``"por"`` ou ``"por+eng"`` se precisar."""
    ocr_quality: str = "all"
    """Quantas variações de imagem testar: ``"fast"``, ``"balanced"`` ou ``"all"``."""
    ocr_quality_fullscreen: str = "fast"
    """Qualidade usada quando a busca é na tela inteira (captura grande)."""
    ocr_upscale: float = 2.0
    """Ampliação de áreas pequenas antes do OCR."""
    ocr_threads: Optional[int] = None
    """Chamadas simultâneas ao Tesseract (padrão: até 4)."""
    fuzzy: float = 0.8
    """Similaridade mínima para aceitar leitura aproximada (0 desliga)."""

    # --- tentativas e esperas -------------------------------------------
    timeout: float = 30.0
    """Espera padrão (s) quando a chamada usa ``wait_until_found=True`` sem
    ``wait_timeout``/``timeout``. Por chamada: ``click_image(..., timeout=3)``."""
    retry_pause: float = 0.25
    """Intervalo entre verificações da tela durante a espera (s)."""
    recoveries: int = 2
    """Backtrack: quantas vezes refazer a ação anterior quando uma ação falha."""
    stop_on_failure: bool = False
    """``execute_tasks`` para na primeira tarefa que falhar."""

    # --- mouse e teclado -------------------------------------------------
    typing: str = "paste"
    """Como escrever texto: ``"paste"`` (área de transferência) ou ``"keys"`` (tecla a tecla)."""
    keep_clipboard: bool = True
    """Restaura a área de transferência depois de colar."""
    key_interval: float = 0.02
    """Intervalo entre teclas no modo ``"keys"``."""
    move_time: float = 0.1
    """Duração do movimento do mouse até o alvo."""
    settle: float = 0.15
    """Pausa entre chegar ao alvo e clicar (telas lentas)."""
    click_hold: float = 0.0
    """Segura o botão por N s (apps que ignoram cliques rápidos)."""
    emergency_stop: bool = True
    """Levar o mouse ao canto superior esquerdo interrompe a automação."""
    virtual_mouse: bool = False
    """Clica sem mover o cursor (Windows). Se falhar, usa o mouse físico e devolve o cursor."""

    # --- destaque visual -------------------------------------------------
    highlight: bool = False
    """Desenha um retângulo no alvo antes de agir (útil para depurar)."""
    highlight_color: str = "red"
    highlight_ms: int = 800
    highlight_width: int = 3

    # --- diagnóstico -----------------------------------------------------
    failure_shots: bool = False
    """Salva um print da tela a cada falha."""
    failure_dir: str = "pyvizion_failures"
    log_level: str = "INFO"

    def __post_init__(self):
        self.validate()

    # ------------------------------------------------------------------
    def validate(self) -> "Settings":
        def between(name, low, high):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not low <= value <= high:
                raise SettingsError(f"'{name}' deve estar entre {low} e {high} (recebido: {value!r})")

        between("precision", 0.1, 1.0)
        between("min_precision", 0.1, 1.0)
        between("text_confidence", 0, 100)
        between("fuzzy", 0.0, 1.0)
        between("ocr_upscale", 1.0, 4.0)
        between("timeout", 0, 3600)
        if self.typing not in ("paste", "keys"):
            raise SettingsError("'typing' deve ser 'paste' ou 'keys'")
        for name in ("ocr_quality", "ocr_quality_fullscreen"):
            value = getattr(self, name)
            if isinstance(value, (list, tuple)):
                setattr(self, name, list(value))
            elif value not in OCR_QUALITIES:
                raise SettingsError(f"'{name}' deve ser um de {OCR_QUALITIES} ou uma lista de técnicas")
        if self.highlight_color not in HIGHLIGHT_COLORS:
            raise SettingsError(f"'highlight_color' deve ser um de {HIGHLIGHT_COLORS}")
        if isinstance(self.image_dirs, (str, Path)):
            self.image_dirs = [str(self.image_dirs)]
        self.image_dirs = [str(p) for p in self.image_dirs]
        if self.scales is not None:
            self.scales = tuple(float(s) for s in self.scales)
        return self

    def replace(self, **changes) -> "Settings":
        """Cópia com alterações: ``s.replace(highlight=True)``."""
        unknown = set(changes) - {f.name for f in dataclasses.fields(self)}
        if unknown:
            raise SettingsError(f"Configurações desconhecidas: {', '.join(sorted(unknown))}")
        return dataclasses.replace(self, **changes)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        unknown = set(data) - {f.name for f in dataclasses.fields(cls)}
        if unknown:
            raise SettingsError(f"Configurações desconhecidas: {', '.join(sorted(unknown))}")
        return cls(**data)

    @classmethod
    def load(cls, path) -> "Settings":
        """Lê configurações de um arquivo ``.json`` ou ``.yaml``/``.yml``."""
        path = Path(path)
        if not path.is_file():
            raise SettingsError(f"Arquivo de configuração não encontrado: {path}")
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            data = json.loads(text)
        elif path.suffix.lower() in (".yml", ".yaml"):
            try:
                import yaml
            except ImportError:
                raise SettingsError("PyYAML ausente: reinstale com pip install pyvizion") from None
            data = yaml.safe_load(text) or {}
        else:
            raise SettingsError(f"Formato não suportado: {path.suffix} (use .json ou .yaml)")
        return cls.from_dict(data)

    def save(self, path) -> Path:
        """Grava as configurações em JSON."""
        path = Path(path)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path
