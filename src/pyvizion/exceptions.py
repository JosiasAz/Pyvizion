"""
pyvizion - Erros

Todos herdam de ``VizionError``.

Os métodos clássicos (``click_*``, ``find_*``) devolvem ``False``/``None`` quando
o alvo não está na tela — isso deixa o backtrack e as tarefas ``optional``
funcionarem. As classes ``ImageNotFoundError`` e ``TextNotFoundError`` existem
para quem quiser capturar ou relançar; o ambiente (Tesseract ausente, arquivo
inexistente, área inválida) **sempre** levanta exceção.
"""


class VizionError(Exception):
    """Base de todos os erros do pyvizion."""


class TargetNotFound(VizionError):
    """
    O alvo não apareceu dentro do tempo limite.

    Attributes:
        target: descrição do localizador
        scope: onde foi procurado (tela, janela, área)
        timeout: tempo de espera (s)
        best: melhor candidato encontrado, se houver: ``(semelhança, Region)``
        screenshot: caminho do print salvo no momento da falha (ou ``None``)
    """

    def __init__(self, target, scope, timeout, best=None, screenshot=None, reason=None):
        self.target = target
        self.scope = scope
        self.timeout = timeout
        self.best = best
        self.screenshot = screenshot
        lines = [f"{target} não encontrado em {scope} após {timeout:g}s"]
        if reason:
            lines.append(f"  motivo: {reason}")
        if best:
            score, region = best
            lines.append(f"  melhor candidato: semelhança {score:.2f} em {tuple(region)}")
        if screenshot:
            lines.append(f"  print: {screenshot}")
        super().__init__("\n".join(lines))


class ImageNotFoundError(TargetNotFound):
    """Imagem não encontrada na tela."""

    def __init__(self, target, scope="tela", timeout=0, best=None, screenshot=None, reason=None):
        super().__init__(target, scope, timeout, best, screenshot, reason)


class TextNotFoundError(TargetNotFound):
    """Texto não encontrado na região."""

    def __init__(self, target, scope="tela", timeout=0, best=None, screenshot=None, reason=None):
        super().__init__(target, scope, timeout, best, screenshot, reason)


class TesseractNotFoundError(VizionError):
    """Tesseract OCR não encontrado no sistema."""


class OCRUnavailable(TesseractNotFoundError):
    """Tesseract ou pytesseract ausente (necessário para texto e campos)."""


class WindowNotFound(VizionError):
    """Nenhuma janela com esse título."""


class ImageFileError(VizionError):
    """O arquivo de imagem não existe ou não pôde ser lido."""


class InvalidArea(VizionError):
    """Área inválida ou fora dos monitores."""


class InvalidRegionError(InvalidArea):
    """Região inválida (mesmo sentido de ``InvalidArea``)."""


class ActionError(VizionError):
    """Falha ao executar uma ação de mouse ou teclado."""


class SettingsError(VizionError):
    """Configuração ou uso inválido."""


class ConfigurationError(SettingsError):
    """Erro na configuração da biblioteca."""


class TaskExecutionError(VizionError):
    """Falha ao executar uma tarefa de ``execute_tasks``."""


class OCRProcessingError(VizionError):
    """Falha no processamento OCR."""


class ImageProcessingError(VizionError):
    """Falha no processamento de imagem."""


__all__ = [
    "VizionError",
    "TargetNotFound",
    "ImageNotFoundError",
    "TextNotFoundError",
    "TesseractNotFoundError",
    "OCRUnavailable",
    "WindowNotFound",
    "ImageFileError",
    "InvalidArea",
    "InvalidRegionError",
    "ActionError",
    "SettingsError",
    "ConfigurationError",
    "TaskExecutionError",
    "OCRProcessingError",
    "ImageProcessingError",
]
