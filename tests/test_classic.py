"""Métodos clássicos: assinaturas, backtrack, execute_tasks e macros (sem tocar na tela)."""

import inspect

import pytest

import pyvizion
from pyvizion import Region, Vizion
from pyvizion.core.classic_keys import tokenize_sendtext

SIGNATURES = {
    "find_text": ["text", "region", "filter_type", "confidence_threshold", "occurrence",
                  "max_attempts", "backtrack", "wait_until_found", "wait_until_disappears",
                  "wait_timeout"],
    "click_text": ["text", "region", "filter_type", "delay", "mouse_button", "occurrence",
                   "backtrack", "max_attempts", "sendtext", "confidence_threshold", "show_overlay",
                   "wait_until_found", "wait_until_disappears", "wait_timeout"],
    "find_image": ["image_path", "region", "confidence", "max_attempts", "backtrack", "specific",
                   "wait_until_found", "wait_until_disappears", "wait_timeout", "scales"],
    "click_image": ["image_path", "region", "confidence", "delay", "mouse_button", "max_attempts",
                    "backtrack", "specific", "sendtext", "show_overlay", "wait_until_found",
                    "wait_until_disappears", "wait_timeout"],
    "click_at": ["location", "mouse_button", "delay", "show_overlay"],
    "find_relative_image": ["anchor_image", "target_image", "max_distance", "confidence",
                            "target_region", "wait_until_found", "wait_until_disappears",
                            "wait_timeout"],
    "click_relative_image": ["anchor_image", "target_image", "max_distance", "confidence",
                             "target_region", "delay", "mouse_button", "backtrack", "max_attempts",
                             "sendtext", "wait_until_found", "wait_until_disappears",
                             "wait_timeout"],
    "click_coordinates": ["x", "y", "delay", "mouse_button", "backtrack"],
    "type_text": ["text", "interval", "delay", "backtrack"],
    "keyboard_command": ["command", "delay", "backtrack"],
    "execute_tasks": ["tasks"],
    "extract_text_from_region": ["region", "filter_type", "confidence_threshold",
                                 "return_full_data", "max_attempts", "backtrack"],
    "get_last_extracted_text": [],
}


@pytest.mark.parametrize("method,params", SIGNATURES.items())
def test_assinaturas(method, params):
    sig = inspect.signature(getattr(Vizion, method))
    positional = [p.name for p in sig.parameters.values()
                  if p.kind == p.POSITIONAL_OR_KEYWORD and p.name != "self"]
    assert positional == params
    assert callable(getattr(pyvizion, method))


class Scripted:
    """Resolver falso: {rótulo: [Region|None, ...]}"""

    def __init__(self, script):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls = []
        self.last_choice = None

    def find_once(self, spec, attempt=0):
        label = spec.label()
        self.calls.append(label)
        seq = self.script.get(label, [None])
        value = seq.pop(0) if len(seq) > 1 else seq[0]
        return Region(*value) if value else None

    def find_all(self, spec):
        found = self.find_once(spec)
        return [found] if found else []

    def area(self, area):
        return area


@pytest.fixture
def vz(fake_gui, tmp_path):
    return Vizion({"retry_delay": 0})


def script(vz, mapping):
    vz._ctx.resolver = Scripted(mapping)
    vz._ctx._classic_session = None
    return vz._ctx.resolver


def test_click_image_sendtext_e_botoes(vz, fake_gui):
    calls, _ = fake_gui
    script(vz, {"ok.png": [(100, 100, 20, 10)]})
    assert vz.click_image("ok.png", mouse_button="right", sendtext="abc{enter}")
    assert vz.click_image("ok.png", mouse_button="double")
    assert vz.click_image("ok.png", mouse_button="move_to")
    clicks = [c for c in calls if c[0] == "click"]
    assert clicks[0] == ("click", (110, 105), {"button": "right"})
    assert clicks[1][2]["clicks"] == 2 and len(clicks) == 2
    assert ("press", ("enter",), {}) in calls


def test_nao_encontrado_retorna_false(vz):
    script(vz, {})
    assert vz.click_image("nada.png", max_attempts=1) is False
    assert vz.find_text("Nada") is None


def test_backtrack_entre_metodos(vz):
    resolver = script(vz, {"a.png": [(0, 0, 5, 5)], "Salvar": [None, None, None, (1, 1, 5, 5)]})
    assert vz.click_image("a.png", backtrack=True)
    assert vz.click_text("Salvar", backtrack=True, max_attempts=3)
    assert resolver.calls == ["a.png", "Salvar", "Salvar", "Salvar", "a.png", "Salvar"]
    assert vz.end_task_session() == (2, 2)


def test_execute_tasks_com_backtrack_required_e_optional(vz, fake_gui):
    resolver = script(vz, {"menu.png": [(0, 0, 5, 5)], "Vendas": [None, (5, 5, 5, 5)],
                           "aviso.png": [None], "Salvar": [None]})
    results = vz.execute_tasks([
        {"image": "menu.png"},
        {"text": "Vendas", "backtrack": True, "max_attempts": 1},
        {"image": "aviso.png", "optional": True, "max_attempts": 1},
        {"type": "keyboard_command", "command": "Ctrl+S"},
        {"type": "type_text", "text": "Olá{tab}"},
        {"text": "Salvar", "required": True, "max_attempts": 1},
        {"type": "click", "x": 1, "y": 1},
    ])
    assert [r.success for r in results] == [True, True, False, True, True, False, False]
    assert results[1].recoveries == 1 and results[2].optional
    assert results[6].error == "não executada"
    assert resolver.calls[:4] == ["menu.png", "Vendas", "menu.png", "Vendas"]


def test_macros_classicas():
    assert tokenize_sendtext("admin{tab}senha{enter}") == [
        ("text", "admin"), ("keys", (["tab"], 1)), ("text", "senha"), ("keys", (["enter"], 1))]
    assert tokenize_sendtext("{ctrl}a{del}novo") == [
        ("keys", (["ctrl", "a"], 1)), ("keys", (["delete"], 1)), ("text", "novo")]
    assert tokenize_sendtext("{tab*3}{wait 1}") == [("keys", (["tab"], 3)), ("wait", 1.0)]


def test_keyboard_command(vz, fake_gui):
    calls, _ = fake_gui
    assert vz.keyboard_command("Ctrl+S") and vz.keyboard_command("F7")
    assert not vz.keyboard_command("Tecla Inventada")
    assert calls[:2] == [("hotkey", ("ctrl", "s"), {}), ("press", ("f7",), {})]
    assert len(vz.get_available_keyboard_commands()) >= 100


def test_config_chaves_antigas(tmp_path):
    vz = Vizion({"confidence_threshold": 80, "tesseract_lang": "por", "typing_mode": "type",
                 "tessdata_path": "C:/tess", "image_folders": ["imgs"]})
    s = vz._ctx.settings
    assert (s.text_confidence, s.language, s.typing, s.tessdata, s.image_dirs) == (80, "por", "keys", "C:/tess", ["imgs"])
    vz.config.set("confidence_threshold", 60)
    assert vz._ctx.settings.text_confidence == 60 and vz.config.get("confidence_threshold") == 60
    path = vz.config.save(tmp_path / "cfg.json")
    assert Vizion(str(path)).config.get("tesseract_lang") == "por"


def test_overlay(vz):
    vz.configure_overlay(enabled=True, color="blue", duration=500, width=3)
    assert vz.get_overlay_config() == {"enabled": True, "show_overlay": True, "color": "blue",
                                       "duration": 500, "width": 3}
    assert vz._ctx.settings.highlight
    with pytest.raises(ValueError):
        vz.configure_overlay(color="rosa")


def test_click_any(vz, fake_gui):
    script(vz, {"v2.png": [(10, 10, 10, 10)]})
    assert vz.click_any(["v1.png", "v2.png", "Novo"]) == 1


def test_excecoes_especificas():
    from pyvizion import (
        ConfigurationError,
        ImageNotFoundError,
        InvalidRegionError,
        SettingsError,
        TargetNotFound,
        TesseractNotFoundError,
        TextNotFoundError,
        VizionError,
    )
    from pyvizion.exceptions import InvalidArea, OCRUnavailable

    assert issubclass(ImageNotFoundError, TargetNotFound)
    assert issubclass(TextNotFoundError, TargetNotFound)
    assert issubclass(TesseractNotFoundError, VizionError)
    assert issubclass(OCRUnavailable, TesseractNotFoundError)
    assert issubclass(InvalidRegionError, InvalidArea)
    assert issubclass(ConfigurationError, SettingsError)
    err = ImageNotFoundError("ok.png")
    assert isinstance(err, TargetNotFound)


def test_tesseract_obrigatorio_no_init(monkeypatch):
    from pyvizion.core import tesseract
    from pyvizion.exceptions import TesseractNotFoundError

    def boom(executable=None):
        raise TesseractNotFoundError("sumiu")

    monkeypatch.setattr(tesseract, "locate", boom)
    with pytest.raises(TesseractNotFoundError, match="sumiu"):
        Vizion({"retry_delay": 0})


def test_virtual_mouse_nao_move_cursor(vz, fake_gui, monkeypatch):
    calls, _ = fake_gui
    vz.config.set("use_virtual_mouse", True)
    assert vz._ctx.settings.virtual_mouse
    vz._ctx.mouse.virtual_available = True
    monkeypatch.setattr("pyvizion.core.mouse._click_virtual_windows", lambda *a, **k: True)
    script(vz, {"ok.png": [(10, 10, 8, 8)]})
    assert vz.click_image("ok.png")
    assert not any(c[0] in ("click", "moveTo") for c in calls)


def test_exports():
    assert [n for n in pyvizion.__all__ if not hasattr(pyvizion, n)] == []
    for gone in ("Key", "Locator", "Flow", "Field", "Window"):
        assert not hasattr(pyvizion, gone)
    assert pyvizion.limpar_texto("  123abc!  ", "numbers") == "123"
    assert pyvizion.clean_text("  123abc!  ", "letters") == "abc"
    assert pyvizion.type_text_standalone is pyvizion.type_text


def _positional(cls, name):
    return [p.name for p in inspect.signature(getattr(cls, name)).parameters.values()
            if p.kind == p.POSITIONAL_OR_KEYWORD and p.name != "self"]


def test_assinaturas_iguais_ao_bot_vision_suite():
    pytest.importorskip("bot_vision")
    from bot_vision import BotVision

    for name in SIGNATURES:
        assert _positional(Vizion, name) == _positional(BotVision, name), name


def test_wait_until_found_e_timeout(vz, fake_gui, monkeypatch):
    calls, _ = fake_gui
    resolver = script(vz, {"ok.png": [None, None, (20, 20, 10, 10)],
                           "Salvar": [None, (30, 30, 8, 8)]})
    assert vz.find_image("ok.png", wait_until_found=True, wait_timeout=5) == Region(20, 20, 10, 10)
    assert vz.click_text("Salvar", timeout=5)
    assert resolver.calls == ["ok.png", "ok.png", "ok.png", "Salvar", "Salvar"]
    assert any(c[0] == "click" for c in calls)

    script(vz, {})
    ticks = {"n": 0}

    def mono():
        ticks["n"] += 1
        return float(ticks["n"])

    monkeypatch.setattr("pyvizion.classic.time.monotonic", mono)
    assert vz.find_image("sumiu.png", timeout=2) is None
    assert vz.click_image("sumiu.png", wait_until_found=True, wait_timeout=2) is False


def test_extract_text_from_region(vz, monkeypatch):
    from PIL import Image as PILImage

    from pyvizion.core.reader import TextHit

    class FakeReader:
        def words(self, img, kind="any"):
            return [TextHit("OK", 90, (1, 2, 10, 8)), TextHit("x", 20, (0, 0, 1, 1))]

    monkeypatch.setattr("pyvizion.classic.grab_screen",
                        lambda area: (PILImage.new("RGB", (10, 10)), (5, 5)))
    vz._ctx.reader = FakeReader()
    texts = vz.extract_text_from_region((0, 0, 100, 40), confidence_threshold=50)
    assert texts == ["OK"]
    assert vz.get_last_extracted_text() == ["OK"]
    full = vz.extract_text_from_region((0, 0, 100, 40), return_full_data=True, confidence_threshold=50)
    assert full[0]["text"] == "OK" and full[0]["absolute_box"] == (6, 7, 10, 8)
    assert vz.execute_tasks([{"type": "extract_text", "region": (0, 0, 100, 40)}])[0]


def test_config_timeout(vz):
    vz.config.set("timeout", 25)
    assert vz._ctx.settings.timeout == 25
    vz.config.set("wait_timeout", 8)
    assert vz._ctx.settings.timeout == 8
    assert vz._appear_seconds(wait_until_found=True) == 8
    assert vz._appear_seconds(timeout=3) == 3
    assert vz._appear_seconds(wait_until_found=True, wait_timeout=12, timeout=3) == 12
    assert vz._appear_seconds() is None
    assert vz._appear_seconds(wait_until_disappears=True, wait_timeout=60) is None
    assert vz._gone_seconds(wait_timeout=60) == 60
    assert vz._gone_seconds() == 8


def test_wait_until_disappears(vz, fake_gui, monkeypatch):
    script(vz, {"ampulheta.png": [(1, 1, 5, 5), (1, 1, 5, 5), None]})
    assert vz.find_image("ampulheta.png", wait_until_disappears=True, wait_timeout=5) == Region(1, 1, 5, 5)

    script(vz, {"ok.png": [(10, 10, 8, 8), (10, 10, 8, 8), None]})
    assert vz.click_image("ok.png", wait_until_disappears=True, wait_timeout=5)

    script(vz, {"Aviso": [(2, 2, 6, 6), None]})
    assert vz.find_text("Aviso", wait_until_disappears=True, wait_timeout=5) == Region(2, 2, 6, 6)

    script(vz, {"preso.png": [(1, 1, 5, 5)]})
    ticks = {"n": 0}

    def mono():
        ticks["n"] += 1
        return float(ticks["n"])

    monkeypatch.setattr("pyvizion.classic.time.monotonic", mono)
    assert vz.find_image("preso.png", wait_until_disappears=True, wait_timeout=2) is None

    script(vz, {"ok.png": [(10, 10, 8, 8)]})
    ticks["n"] = 0
    assert vz.click_image("ok.png", wait_until_disappears=True, wait_timeout=2) is True
