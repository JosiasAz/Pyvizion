"""
pyvizion - Teclado clássico (catálogo de comandos e macros {tab}, {enter}, {ctrl}a...)

Catálogo com mais de 100 comandos nomeados (``"Ctrl+S"``, ``"F7"``, ``"Alt+Tab"``...)
e aceita qualquer outra combinação, como as usadas em Oracle Forms e ERPs.
Recursos:

- busca sem diferenciar maiúsculas/espaços (``"ctrl+s"``, ``"CTRL + S"``);
- qualquer combinação não mapeada é interpretada (``"Ctrl+Shift+F9"``, ``"Alt+X"``);
- macros de ``sendtext`` funcionam em **qualquer posição** do texto:
  ``"admin{tab}senha{enter}"``;
- digitação de acentos/ç sem perda (``typewrite`` do pyautogui descarta não-ASCII);
- modo ``paste`` restaura o conteúdo anterior da área de transferência;
- modo ``type`` (tecla a tecla) para emuladores de terminal/Citrix que não aceitam colar.

Macros suportadas em ``sendtext``/``type_text``::

    {enter} {tab} {esc} {escape} {del} {delete} {backspace} {bs} {space}
    {up} {down} {left} {right} {home} {end} {pgup} {pgdn} {insert}
    {f1} … {f12}
    {ctrl}a  {alt}f  {shift}x  {win}r        -> modificador + próxima tecla
    {ctrl+shift+s} {alt+f4}                  -> combinação completa
    {tab*3} {down 5}                         -> repetição
    {wait 1.5} {sleep:0.5}                   -> pausa (segundos)
    {{ e }}                                  -> chaves literais
"""

import logging
import re
import time
from typing import Callable, Dict, List, Tuple

from ..exceptions import ActionError as TaskExecutionError

logger = logging.getLogger(__name__)


def _pg():
    import pyautogui
    return pyautogui


def _press(key):
    return lambda: _pg().press(key)


def _hotkey(*keys):
    return lambda: _pg().hotkey(*keys)


KEY_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl", "ctl": "ctrl",
    "shift": "shift",
    "alt": "alt", "menu": "alt",
    "win": "win", "windows": "win", "super": "win", "cmd": "command", "command": "command",
    "enter": "enter", "return": "enter", "ret": "enter",
    "tab": "tab",
    "esc": "escape", "escape": "escape",
    "del": "delete", "delete": "delete",
    "backspace": "backspace", "bs": "backspace", "bksp": "backspace",
    "space": "space", "spacebar": "space",
    "up": "up", "arrowup": "up", "down": "down", "arrowdown": "down",
    "left": "left", "arrowleft": "left", "right": "right", "arrowright": "right",
    "home": "home", "end": "end",
    "pgup": "pageup", "pageup": "pageup", "pgdn": "pagedown", "pgdown": "pagedown",
    "pagedown": "pagedown",
    "ins": "insert", "insert": "insert",
    "printscreen": "printscreen", "prtsc": "printscreen", "print": "printscreen",
    "capslock": "capslock", "numlock": "numlock", "scrolllock": "scrolllock",
    "pause": "pause", "apps": "apps", "contextmenu": "apps",
    "volumeup": "volumeup", "volumedown": "volumedown", "volumemute": "volumemute",
    "playpause": "playpause", "nexttrack": "nexttrack", "prevtrack": "prevtrack",
}
for _n in range(1, 25):
    KEY_ALIASES[f"f{_n}"] = f"f{_n}"

MODIFIERS = {"ctrl", "shift", "alt", "win", "command"}


def _canon(name: str) -> str:
    return re.sub(r"[\s_\-]", "", name).lower()


def resolve_key(name: str) -> str:
    """Converte um nome de tecla amigável no nome do pyautogui."""
    key = _canon(name)
    if key in KEY_ALIASES:
        return KEY_ALIASES[key]
    if len(name.strip()) == 1:
        return name.strip().lower()
    raise TaskExecutionError(f"Tecla desconhecida: '{name}'")


_NAMED_KEYS = {
    "Enter": "enter", "Tab": "tab", "Escape": "escape", "Delete": "delete",
    "Backspace": "backspace", "Space": "space", "Insert": "insert",
    "Home": "home", "End": "end", "PageUp": "pageup", "PageDown": "pagedown",
    "Up": "up", "Down": "down", "Left": "left", "Right": "right",
    "PrintScreen": "printscreen", "Apps": "apps",
}
_FKEYS = [f"F{n}" for n in range(1, 13)]


def build_command_catalog() -> Dict[str, List[str]]:
    """
    Gera o catálogo de comandos por composição:
    teclas simples, F1–F12 (puras, com Shift, Ctrl e Ctrl+Shift),
    Ctrl+A…Z, navegação com modificadores e atalhos de sistema.
    """
    catalog: Dict[str, List[str]] = {}

    def add(label, *keys):
        catalog[label] = [k.lower() for k in keys]

    for label, key in _NAMED_KEYS.items():
        add(label, key)
    for fkey in _FKEYS:
        add(fkey, fkey)
        add(f"Shift+{fkey}", "shift", fkey)
        add(f"Ctrl+{fkey}", "ctrl", fkey)
        add(f"Ctrl+Shift+{fkey}", "ctrl", "shift", fkey)
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        add(f"Ctrl+{letter}", "ctrl", letter)
    for label in ("Up", "Down", "Left", "Right", "Home", "End", "Tab", "Enter"):
        add(f"Ctrl+{label}", "ctrl", _NAMED_KEYS[label])
    for label in ("Tab", "Home", "End", "PageUp", "PageDown", "Up", "Down", "Left", "Right", "Delete", "Insert"):
        add(f"Shift+{label}", "shift", _NAMED_KEYS[label])
    for label in ("Left", "Right", "Home", "End", "Tab"):
        add(f"Ctrl+Shift+{label}", "ctrl", "shift", _NAMED_KEYS[label])
    add("Ctrl+Shift+Escape", "ctrl", "shift", "escape")
    for label in ("Tab", "Enter", "Space", "Up", "Down", "Left", "Right"):
        add(f"Alt+{label}", "alt", _NAMED_KEYS[label])
    add("Alt+F4", "alt", "f4")
    add("Alt+PrintScreen", "alt", "printscreen")
    for letter in "DELR":
        add(f"Windows+{letter}", "win", letter)
    add("Windows+Shift+S", "win", "shift", "s")
    return catalog


class KeyboardCommander:
    """
    Executor de comandos de teclado.

    Examples:
        >>> kb = KeyboardCommander()
        >>> kb.execute_command("Ctrl+S")
        >>> kb.process_sendtext_command("{ctrl}a{del}Novo texto{enter}")
    """

    def __init__(self, config=None):
        self.config = config
        self._setup_command_mapping()

    def _setup_command_mapping(self) -> None:
        """Monta o catálogo de comandos nomeados a partir de ``build_command_catalog``."""
        self.command_mapping: Dict[str, Callable] = {}
        for name, keys in build_command_catalog().items():
            self.command_mapping[name] = _press(keys[0]) if len(keys) == 1 else _hotkey(*keys)
        self._lookup = {_canon(k): k for k in self.command_mapping}

    # ------------------------------------------------------------------
    # Comandos
    # ------------------------------------------------------------------
    def parse_combo(self, command: str) -> List[str]:
        """'Ctrl+Shift+S' -> ['ctrl', 'shift', 's']"""
        text = command.strip()
        if text in ("+",):
            return ["+"]
        parts = [p for p in re.split(r"\s*\+\s*", text) if p]
        if text.endswith("++"):
            parts.append("+")
        if not parts:
            raise TaskExecutionError(f"Comando vazio: '{command}'")
        return [resolve_key(p) for p in parts]

    def execute_command(self, command: str) -> bool:
        """
        Executa um comando de teclado (mapeado ou combinação livre).

        Returns:
            bool: True se executado, False se o comando não for reconhecido.
        """
        if not command or not str(command).strip():
            logger.warning("Comando de teclado vazio")
            return False
        name = self._lookup.get(_canon(command))
        try:
            if name:
                logger.info(f"Executando comando de teclado: '{name}'")
                self.command_mapping[name]()
                return True
            keys = self.parse_combo(command)
        except TaskExecutionError as e:
            logger.warning(f"Comando '{command}' não reconhecido: {e}")
            return False
        except Exception as e:
            raise TaskExecutionError(f"Erro ao executar comando '{command}': {e}")

        try:
            logger.info(f"Executando combinação de teclas: {'+'.join(keys)}")
            if len(keys) == 1:
                _pg().press(keys[0])
            else:
                _pg().hotkey(*keys)
            return True
        except Exception as e:
            raise TaskExecutionError(f"Erro ao executar comando '{command}': {e}")

    def get_available_commands(self) -> list:
        """Lista de comandos mapeados (combinações livres também são aceitas)."""
        return list(self.command_mapping.keys())

    def press(self, key: str, presses: int = 1, interval: float = 0.05) -> None:
        _pg().press(resolve_key(key), presses=max(1, int(presses)), interval=interval)

    def hotkey(self, *keys: str) -> None:
        _pg().hotkey(*[resolve_key(k) for k in keys])

    # ------------------------------------------------------------------
    # Digitação
    # ------------------------------------------------------------------
    def _cfg(self, key, default):
        if self.config is None:
            return default
        return self.config.get(key, default)

    def type_text(self, text: str, interval: float = 0.05) -> None:
        """
        Digita texto tecla a tecla. Caracteres fora do ASCII (acentos, ç, emoji)
        são colados pela área de transferência para não se perderem.
        """
        try:
            logger.info(f"Digitando texto: '{_mask(text)}'")
            for chunk, is_ascii in _split_ascii(text):
                if is_ascii:
                    _pg().write(chunk, interval=interval)
                else:
                    self._paste(chunk)
        except Exception as e:
            raise TaskExecutionError(f"Erro ao digitar texto: {e}")

    def write(self, text: str, mode: str = None, interval: float = None) -> None:
        """Escreve texto literal conforme ``typing_mode`` ("paste", "type", "auto")."""
        if not text:
            return
        mode = (mode or self._cfg("typing_mode", "paste")).lower()
        interval = self._cfg("typing_interval", 0.02) if interval is None else interval
        if mode == "type":
            self.type_text(text, interval)
        else:
            self._paste(text)

    def _paste(self, text: str) -> None:
        import pyperclip

        restore = bool(self._cfg("restore_clipboard", True))
        previous = None
        if restore:
            try:
                previous = pyperclip.paste()
            except Exception:
                previous = None
        logger.info(f"Colando texto: '{_mask(text)}'")
        pyperclip.copy(text)
        time.sleep(0.05)
        _pg().hotkey("ctrl", "v")
        time.sleep(0.15)
        if restore and previous is not None:
            try:
                pyperclip.copy(previous)
            except Exception:
                pass

    def process_sendtext_command(self, full_text_command: str, mode: str = None) -> None:
        """
        Processa um texto com macros ({tab}, {enter}, {ctrl}a, {wait 1}...) em
        qualquer posição, executando teclas e digitando os trechos literais.
        """
        if full_text_command is None:
            return
        logger.info(f"Processando sendtext: '{_mask(str(full_text_command))}'")
        try:
            for kind, value in tokenize_sendtext(str(full_text_command)):
                if kind == "text":
                    self.write(value, mode)
                elif kind == "keys":
                    keys, times = value
                    for _ in range(times):
                        if len(keys) == 1:
                            _pg().press(keys[0])
                        else:
                            _pg().hotkey(*keys)
                        time.sleep(0.05)
                    time.sleep(0.05)
                elif kind == "wait":
                    time.sleep(value)
            time.sleep(0.1)
        except TaskExecutionError:
            raise
        except Exception as e:
            raise TaskExecutionError(f"Erro ao processar sendtext: {e}")


# ---------------------------------------------------------------------------
# Parser de macros
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\{\{|\}\}|\{([^{}]*)\}")
_REPEAT_RE = re.compile(r"^(.*?)(?:\s*\*\s*|\s+)(\d+)$")
_WAIT_RE = re.compile(r"^(?:wait|sleep|pause|delay)\s*[:= ]?\s*(\d+(?:[.,]\d+)?)\s*(ms|s)?$", re.I)


def has_macros(text: str) -> bool:
    """True se o texto contém alguma macro reconhecida."""
    return any(kind != "text" for kind, _ in tokenize_sendtext(text or ""))


def tokenize_sendtext(text: str) -> List[Tuple[str, object]]:
    """
    Converte o texto em tokens: ("text", str) | ("keys", ([teclas], vezes)) | ("wait", s).

    Macros desconhecidas são mantidas como texto literal.
    """
    tokens: List[Tuple[str, object]] = []
    buf: List[str] = []
    pending_mods: List[str] = []
    pos = 0

    def flush():
        if buf:
            tokens.append(("text", "".join(buf)))
            buf.clear()

    while pos < len(text):
        m = _TOKEN_RE.search(text, pos)
        literal = text[pos:m.start()] if m else text[pos:]

        if literal:
            if pending_mods:
                # {ctrl}a -> ctrl+a ; o restante segue como texto
                first = literal[0]
                tokens.append(("keys", (pending_mods + [first.lower()], 1)))
                pending_mods = []
                literal = literal[1:]
            buf.append(literal)

        if not m:
            break
        pos = m.end()

        if m.group(0) == "{{":
            buf.append("{")
            continue
        if m.group(0) == "}}":
            buf.append("}")
            continue

        parsed = _parse_macro(m.group(1))
        if parsed is None:
            buf.append(m.group(0))
            continue

        kind, value = parsed
        if kind == "mod":
            flush()
            pending_mods.append(value)
            continue
        flush()
        if kind == "keys" and pending_mods:
            keys, times = value
            value = (pending_mods + keys, times)
            pending_mods = []
        tokens.append((kind, value))

    if pending_mods:
        flush()
        tokens.append(("keys", (pending_mods, 1)))
    flush()
    return [t for t in tokens if not (t[0] == "text" and t[1] == "")]


def _parse_macro(body: str):
    raw = body.strip()
    if not raw:
        return None

    wait = _WAIT_RE.match(raw)
    if wait:
        amount = float(wait.group(1).replace(",", "."))
        if (wait.group(2) or "").lower() == "ms":
            amount /= 1000.0
        return "wait", amount

    times = 1
    rep = _REPEAT_RE.match(raw)
    if rep and rep.group(1).strip():
        raw, times = rep.group(1).strip(), int(rep.group(2))

    parts = [p for p in re.split(r"\s*\+\s*", raw) if p]
    try:
        keys = [resolve_key(p) if len(p) > 1 else p.lower() for p in parts]
    except TaskExecutionError:
        return None
    if len(parts) == 1 and len(parts[0]) == 1:
        return None  # "{a}" -> literal
    if len(keys) == 1 and keys[0] in MODIFIERS and times == 1:
        return "mod", keys[0]
    return "keys", (keys, max(1, times))


def _split_ascii(text: str):
    """Divide o texto em blocos ASCII imprimível / não-ASCII."""
    chunks = []
    for ch in text:
        is_ascii = 32 <= ord(ch) < 127 or ch in "\n\t"
        if chunks and chunks[-1][1] == is_ascii:
            chunks[-1][0].append(ch)
        else:
            chunks.append(([ch], is_ascii))
    return [("".join(c), a) for c, a in chunks]


def _mask(text: str) -> str:
    """Evita logar textos longos inteiros."""
    return text if len(text) <= 60 else text[:57] + "..."
