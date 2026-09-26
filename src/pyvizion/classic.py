"""
pyvizion - Métodos clássicos

``find_image``, ``click_image``, ``find_text``, ``click_text``,
``click_relative_image``, ``type_text``, ``keyboard_command``, ``execute_tasks``,
sessões de backtrack... com as assinaturas de sempre (retornam ``bool``/``None``
em vez de levantar erro). Rodam sobre o mesmo motor dos localizadores.

    vz.click_image("salvar.png", backtrack=True)
    vz.click_text("Confirmar", sendtext="{enter}")
"""

import logging
import os
import time

from .core.classic_keys import KeyboardCommander, has_macros
from .core.mouse import is_emergency_stop
from .core.screen import Region, as_region, grab_screen
from .core.specs import Image, Near, Text
from .exceptions import ImageFileError, VizionError

logger = logging.getLogger("pyvizion")

_KINDS = {"numbers": "digits", "letters": "letters", "both": "text"}
_SKIP = "skip"


class TaskResult:
    """Resultado de uma tarefa de ``execute_tasks``."""

    def __init__(self, task_index, success, task_name, location=None, error=None):
        self.task_index = task_index
        self.success = success
        self.task_name = task_name
        self.location = location
        self.error = error
        self.attempts = 0
        self.recoveries = 0
        self.optional = False

    def __bool__(self):
        return bool(self.success)

    def __repr__(self):
        return f"TaskResult(#{self.task_index + 1} {'OK' if self.success else 'FALHOU'} '{self.task_name}')"


class ClassicMixin:
    """Métodos clássicos. Requer ``self._ctx`` e ``self._where`` (escopo)."""

    # ==================================================================
    # Infra
    # ==================================================================
    @property
    def _commander(self):
        """Teclado compartilhado da instância (macros e atalhos)."""
        cmd = getattr(self._ctx, "_classic_keys", None)
        s = self._ctx.settings
        if cmd is None:
            cmd = KeyboardCommander({
                "typing_mode": "type" if s.typing == "keys" else "paste",
                "restore_clipboard": s.keep_clipboard,
                "typing_interval": s.key_interval,
            })
            self._ctx._classic_keys = cmd
        return cmd

    @property
    def _session(self):
        """Estado da sessão de backtrack: ``active`` e ``history``."""
        state = getattr(self._ctx, "_classic_session", None)
        if state is None:
            state = self._ctx._classic_session = {"active": False, "history": []}
        return state

    def _region(self, region):
        """Área da chamada, ou o escopo da instância se ``region`` for ``None``."""
        return as_region(region) if region is not None else self._where

    def _poll(self, spec, attempts):
        """Tenta achar o alvo até ``attempts`` vezes. Devolve a caixa ou ``None``."""
        attempts = max(1, int(attempts))
        for attempt in range(attempts):
            try:
                found = self._ctx.resolver.find_once(spec, min(attempt, 2))
            except ImageFileError:
                raise
            except VizionError as e:
                logger.warning(str(e).splitlines()[0])
                found = None
            if found is not None:
                return found
            if attempt < attempts - 1:
                time.sleep(max(self._ctx.settings.retry_pause, 0.25))
        return None

    def _appear_seconds(self, timeout=None, wait_until_found=False, wait_timeout=None,
                        wait_until_disappears=False):
        """Segundos para o alvo aparecer, ou ``None`` para só tentar ``max_attempts``.

        ``wait_timeout`` só vale na busca quando ``wait_until_found=True``.
        Com ``wait_until_disappears=True`` e sem ``wait_until_found``, o tempo
        fica reservado para esperar o alvo sumir — não para procurá-lo.
        """
        if wait_until_found:
            if wait_timeout is not None:
                return float(wait_timeout)
            if timeout is not None:
                return float(timeout)
            return float(self._ctx.settings.timeout)
        if timeout is not None and not wait_until_disappears:
            return float(timeout)
        return None

    def _gone_seconds(self, timeout=None, wait_timeout=None):
        """Segundos para esperar o alvo sumir (``wait_timeout``, ``timeout`` ou o da config)."""
        if wait_timeout is not None:
            return float(wait_timeout)
        if timeout is not None:
            return float(timeout)
        return float(self._ctx.settings.timeout)

    def _locate(self, spec, attempts=3, timeout=None, wait_until_found=False, wait_timeout=None,
                wait_until_disappears=False):
        """Procura o alvo: espera aparecer, ou tenta até ``attempts`` vezes."""
        seconds = self._appear_seconds(timeout, wait_until_found, wait_timeout,
                                       wait_until_disappears)
        if seconds is not None:
            return self._wait(spec, seconds)
        return self._poll(spec, attempts)

    def _wait_gone(self, spec, timeout):
        """``True`` se o alvo sumiu dentro de ``timeout`` segundos."""
        deadline = time.monotonic() + float(timeout)
        while True:
            try:
                present = self._ctx.resolver.find_once(spec) is not None
            except ImageFileError:
                raise
            except VizionError:
                present = False
            if not present:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(self._ctx.settings.retry_pause)

    def _finish_gone(self, spec, wait_until_disappears, timeout=None, wait_timeout=None):
        """Depois do clique, espera o alvo sumir.

        Se ainda estiver visível no fim do tempo, registra um aviso e mesmo
        assim devolve ``True`` — o clique já aconteceu.
        """
        if not wait_until_disappears:
            return True
        seconds = self._gone_seconds(timeout, wait_timeout)
        if not self._wait_gone(spec, seconds):
            logger.warning(f"{spec.label()} ainda visível após {seconds:g}s — seguindo mesmo assim")
        return True

    def _find_then_gone(self, spec, location, timeout=None, wait_timeout=None):
        """Depois de achar, espera o alvo sumir.

        Devolve a caixa se sumiu; ``None`` se não achou ou se ainda estiver visível.
        """
        if location is None:
            return None
        if self._wait_gone(spec, self._gone_seconds(timeout, wait_timeout)):
            return location
        return None

    def _act(self, location, mouse_button="left", delay=0, sendtext=None, show_overlay=None):
        """Clica no centro do alvo, opcionalmente destaca e envia ``sendtext``."""
        region = as_region(location)
        show = self._ctx.settings.highlight if show_overlay is None else show_overlay
        if show:
            from .core.highlight import highlight

            s = self._ctx.settings
            highlight(region, s.highlight_color, s.highlight_width, s.highlight_ms)
            time.sleep(0.15)
        point = region.center
        button = str(mouse_button or "left").lower().strip()
        if button in ("move_to", "move", "hover"):
            self._ctx.mouse.click(point, "left", 0)
        elif button in ("double", "double left", "double_left"):
            self._ctx.mouse.click(point, "left", 2)
        elif button in ("triple", "triple left"):
            self._ctx.mouse.click(point, "left", 3)
        else:
            self._ctx.mouse.click(point, {"right": "right", "middle": "middle"}.get(button, "left"), 1)
        if sendtext:
            self._commander.process_sendtext_command(str(sendtext))
        if delay:
            time.sleep(float(delay))

    def _missing(self, what):
        """Registra falha, tira print e devolve ``False``."""
        logger.warning(f"{what} não encontrado")
        self._ctx.failure_shot(f"nao_encontrado_{what}")
        return False

    # ==================================================================
    # Sessão de backtrack
    # ==================================================================
    def start_task_session(self):
        """Abre uma sessão de backtrack.

        A partir daqui, ações com ``backtrack=True`` entram no histórico e
        podem ser refeitas se a próxima falhar.
        """
        self._session.update(active=True, history=[])
        logger.info("Sessão de backtrack iniciada")

    def end_task_session(self):
        """Fecha a sessão de backtrack.

        Returns:
            ``(bem_sucedidas, total)`` das ações registradas.
        """
        session = self._session
        session["active"] = False
        ok = sum(1 for step in session["history"] if step["success"])
        logger.info(f"Sessão encerrada: {ok}/{len(session['history'])} ações com sucesso")
        return ok, len(session["history"])

    def _with_backtrack(self, name, func, *args, **kwargs):
        """Executa a ação; se falhar, refaz a anterior e tenta de novo."""
        session = self._session
        if not session["active"]:
            self.start_task_session()
        history = session["history"]
        step = {"name": name, "func": func, "args": args, "kwargs": kwargs, "success": False}
        history.append(step)
        index = len(history) - 1
        step["success"] = bool(func(*args, **kwargs))
        recoveries = 0
        while not step["success"] and index > 0 and recoveries < self._ctx.settings.recoveries:
            recoveries += 1
            previous = history[index - 1]
            logger.info(f"↩ {name} falhou — refazendo {previous['name']} [{recoveries}/"
                        f"{self._ctx.settings.recoveries}]")
            previous["success"] = bool(previous["func"](*previous["args"], **previous["kwargs"]))
            if not previous["success"]:
                break
            time.sleep(0.5)
            step["success"] = bool(func(*args, **kwargs))
        return step["success"]

    # ==================================================================
    # Imagens
    # ==================================================================
    def find_image(self, image_path, region=None, confidence=0.9, max_attempts=3,
                   backtrack=False, specific=True, wait_until_found=False,
                   wait_until_disappears=False, wait_timeout=None, scales=None, *, timeout=None):
        """Procura uma imagem na tela (ou em ``region``).

        ``wait_until_found=True`` espera o alvo aparecer até ``wait_timeout``.
        ``wait_until_disappears=True`` acha e depois espera sumir: devolve a
        caixa se sumiu, ``None`` se ainda estiver visível.

        Returns:
            ``(x, y, largura, altura)`` ou ``None``.
        """
        spec = Image(image_path, self._region(region), confidence, not specific, scales)
        found = self._locate(spec, max_attempts, timeout, wait_until_found, wait_timeout,
                             wait_until_disappears)
        if wait_until_disappears:
            return self._find_then_gone(spec, found, timeout, wait_timeout)
        return found

    def click_image(self, image_path, region=None, confidence=0.9, delay=0, mouse_button="left",
                    max_attempts=3, backtrack=False, specific=True, sendtext=None,
                    show_overlay=None, wait_until_found=False, wait_until_disappears=False,
                    wait_timeout=None, *, timeout=None):
        """Encontra uma imagem e clica no centro.

        ``wait_until_found=True`` espera o alvo aparecer.
        ``wait_until_disappears=True`` espera o alvo sumir depois do clique.
        Se ainda estiver visível, o clique já valeu — retorna ``True`` mesmo assim.

        Returns:
            ``True`` se clicou, ``False`` se não achou.
        """
        if backtrack:
            return self._with_backtrack(
                f"click_image {os.path.basename(str(image_path))}", self.click_image, image_path,
                region, confidence, delay, mouse_button, max_attempts, False, specific, sendtext,
                show_overlay, wait_until_found, wait_until_disappears, wait_timeout,
                timeout=timeout)
        spec = Image(image_path, self._region(region), confidence, not specific)
        location = self._locate(spec, max_attempts, timeout, wait_until_found, wait_timeout,
                                wait_until_disappears)
        if location is None:
            return self._missing(f"imagem '{os.path.basename(str(image_path))}'")
        self._act(location, mouse_button, delay, sendtext, show_overlay)
        return self._finish_gone(spec, wait_until_disappears, timeout, wait_timeout)

    def find_all_images(self, image_path, region=None, confidence=0.9, specific=True):
        """Todas as ocorrências da imagem, em ordem de leitura.

        Returns:
            lista de ``(x, y, largura, altura)``.
        """
        return self._ctx.resolver.find_all(Image(image_path, self._region(region), confidence,
                                                 not specific))

    def image_exists(self, image_path, region=None, confidence=0.9, specific=True):
        """``True`` se a imagem está visível agora (uma tentativa, sem espera)."""
        return self.find_image(image_path, region, confidence, 1, False, specific) is not None

    # ==================================================================
    # Texto
    # ==================================================================
    def find_text(self, text, region=None, filter_type="both", confidence_threshold=75.0,
                  occurrence=1, max_attempts=3, backtrack=False, wait_until_found=False,
                  wait_until_disappears=False, wait_timeout=None, *, timeout=None):
        """Procura um texto na tela (ou em ``region``).

        ``occurrence`` é a N-ésima ocorrência em ordem de leitura.
        ``wait_until_found=True`` espera o texto aparecer.
        ``wait_until_disappears=True`` acha e depois espera sumir: devolve a
        caixa se sumiu, ``None`` se ainda estiver visível.

        Returns:
            ``(x, y, largura, altura)`` ou ``None``.
        """
        threshold = float(confidence_threshold if confidence_threshold is not None
                          else self._ctx.settings.text_confidence)
        kind = _KINDS.get(str(filter_type).lower(), "text")
        nth = occurrence if occurrence and occurrence > 1 else None
        spec = Text(text, self._region(region), kind, nth, threshold)
        seconds = self._appear_seconds(timeout, wait_until_found, wait_timeout,
                                       wait_until_disappears)
        if seconds is not None:
            found = self._wait(spec, seconds)
        else:
            attempts = max(1, int(max_attempts)) if backtrack else 1
            found = None
            for _attempt in range(attempts):
                found = self._poll(spec, 1)
                if found is not None:
                    break
                threshold = max(60.0, threshold - 5.0)
                spec = Text(text, self._region(region), kind, nth, threshold)
        if wait_until_disappears:
            return self._find_then_gone(spec, found, timeout, wait_timeout)
        return found

    def click_text(self, text, region=None, filter_type="both", delay=0, mouse_button="left",
                   occurrence=1, backtrack=False, max_attempts=3, sendtext=None,
                   confidence_threshold=None, show_overlay=None, wait_until_found=False,
                   wait_until_disappears=False, wait_timeout=None, *, timeout=None):
        """Encontra um texto e clica no centro.

        ``wait_until_found=True`` espera o texto aparecer.
        ``wait_until_disappears=True`` espera o texto sumir depois do clique.
        Se ainda estiver visível, o clique já valeu — retorna ``True`` mesmo assim.

        Returns:
            ``True`` se clicou, ``False`` se não achou.
        """
        if backtrack:
            return self._with_backtrack(
                f"click_text '{text}'", self.click_text, text, region, filter_type, delay,
                mouse_button, occurrence, False, max_attempts, sendtext, confidence_threshold,
                show_overlay, wait_until_found, wait_until_disappears, wait_timeout,
                timeout=timeout)
        threshold = confidence_threshold or self._ctx.settings.text_confidence
        spec = Text(text, self._region(region), _KINDS.get(str(filter_type).lower(), "text"),
                    occurrence if occurrence and occurrence > 1 else None, threshold)
        location = self._locate(spec, max_attempts, timeout, wait_until_found, wait_timeout,
                                wait_until_disappears)
        if location is None:
            return self._missing(f"texto '{text}'")
        self._act(location, mouse_button, delay, sendtext, show_overlay)
        return self._finish_gone(spec, wait_until_disappears, timeout, wait_timeout)

    def text_exists(self, text, region=None, filter_type="both", confidence_threshold=None):
        """``True`` se o texto está visível agora (uma tentativa, sem espera)."""
        return self.find_text(text, region, filter_type, confidence_threshold) is not None

    def read_text(self, region=None, single_line=False):
        """Lê o texto de uma área (padrão: o escopo inteiro).

        Returns:
            string com o que o OCR enxergou.
        """
        img, _ = grab_screen(self._ctx.resolver.area(self._region(region)))
        return self._ctx.reader.read(img, line=single_line)

    def extract_text_from_region(self, region=None, filter_type="both", confidence_threshold=50.0,
                                 return_full_data=False, max_attempts=3, backtrack=False):
        """Extrai todo o texto de uma região.

        ``filter_type``: ``"letters"``, ``"numbers"`` ou ``"both"``.
        ``return_full_data=True`` devolve dicts com texto, confiança e caixa.

        Returns:
            lista de strings, ou lista de dicts se ``return_full_data``.
        """
        kind = _KINDS.get(str(filter_type).lower(), "text")
        attempts = max(1, int(max_attempts)) if backtrack else 1
        threshold = float(confidence_threshold)
        hits, origin = [], (0, 0)
        for attempt in range(attempts):
            img, origin = grab_screen(self._ctx.resolver.area(self._region(region)))
            hits = [h for h in self._ctx.reader.words(img, kind) if h.confidence >= threshold]
            if hits or attempt >= attempts - 1:
                break
            threshold = max(30.0, threshold - 10.0)
            time.sleep(0.5)
        if return_full_data:
            data = []
            for hit in hits:
                box = tuple(hit.box)
                data.append({
                    "text": hit.text,
                    "confidence": hit.confidence,
                    "box": box,
                    "absolute_box": (origin[0] + box[0], origin[1] + box[1], box[2], box[3]),
                })
            self._ctx.last_extracted_text = data
            return data
        texts = [hit.text for hit in hits]
        self._ctx.last_extracted_text = texts
        return texts

    def get_last_extracted_text(self):
        """Último resultado de ``extract_text_from_region`` ou da tarefa ``extract_text``.

        Returns:
            lista (strings ou dicts) ou ``None`` se ainda não extraiu nada.
        """
        return getattr(self._ctx, "last_extracted_text", None)

    # ==================================================================
    # Imagem relativa
    # ==================================================================
    def find_relative_image(self, anchor_image, target_image, max_distance=200, confidence=0.9,
                            target_region=None, wait_until_found=False,
                            wait_until_disappears=False, wait_timeout=None, *, timeout=None):
        """Procura o alvo mais próximo de uma imagem âncora.

        ``wait_until_found=True`` espera o par aparecer.
        ``wait_until_disappears=True`` acha e depois espera o alvo sumir:
        devolve a caixa se sumiu, ``None`` se ainda estiver visível.

        Returns:
            caixa do alvo ou ``None`` se não houver dentro de ``max_distance``.
        """
        spec = Near(Image(target_image, None, confidence), Image(anchor_image, self._where, confidence),
                    max_distance, as_region(target_region) if target_region else None)
        found = self._locate(spec, 1, timeout, wait_until_found, wait_timeout, wait_until_disappears)
        if wait_until_disappears:
            return self._find_then_gone(spec, found, timeout, wait_timeout)
        return found

    def click_relative_image(self, anchor_image, target_image, max_distance=200, confidence=0.9,
                             target_region=None, delay=0, mouse_button="left", backtrack=False,
                             max_attempts=3, sendtext=None, wait_until_found=False,
                             wait_until_disappears=False, wait_timeout=None, *,
                             show_overlay=None, timeout=None):
        """Clica no alvo mais próximo de uma imagem âncora.

        ``wait_until_disappears=True`` espera o alvo sumir depois do clique.
        Se ainda estiver visível, o clique já valeu — retorna ``True`` mesmo assim.

        Returns:
            ``True`` se clicou, ``False`` se não achou.
        """
        if backtrack:
            return self._with_backtrack(
                f"click_relative_image {os.path.basename(str(target_image))}",
                self.click_relative_image, anchor_image, target_image, max_distance, confidence,
                target_region, delay, mouse_button, False, max_attempts, sendtext,
                wait_until_found, wait_until_disappears, wait_timeout,
                show_overlay=show_overlay, timeout=timeout)
        spec = Near(Image(target_image, None, confidence),
                    Image(anchor_image, self._where, confidence), max_distance,
                    as_region(target_region) if target_region else None)
        location = self._locate(spec, max_attempts, timeout, wait_until_found, wait_timeout,
                                wait_until_disappears)
        if location is None:
            return self._missing(f"'{os.path.basename(str(target_image))}' perto de "
                                 f"'{os.path.basename(str(anchor_image))}'")
        self._act(location, mouse_button, delay, sendtext, show_overlay)
        return self._finish_gone(spec, wait_until_disappears, timeout, wait_timeout)

    def click_image_near_text(self, anchor_text, target_image, max_distance=200, confidence=0.9,
                              region=None, delay=0, mouse_button="left", backtrack=False,
                              max_attempts=3, *, sendtext=None, show_overlay=None,
                              timeout=None, wait_until_found=False, wait_timeout=None,
                              wait_until_disappears=False):
        """Clica na imagem mais próxima de um texto âncora.

        ``wait_until_disappears=True`` espera o alvo sumir depois do clique.
        Se ainda estiver visível, o clique já valeu — retorna ``True`` mesmo assim.

        Returns:
            ``True`` se clicou, ``False`` se não achou.
        """
        spec = Near(Image(target_image, None, confidence), Text(anchor_text, self._region(region)),
                    max_distance)
        location = self._locate(spec, max_attempts, timeout, wait_until_found, wait_timeout,
                                wait_until_disappears)
        if location is None:
            return self._missing(f"'{os.path.basename(str(target_image))}' perto de '{anchor_text}'")
        self._act(location, mouse_button, delay, sendtext, show_overlay)
        return self._finish_gone(spec, wait_until_disappears, timeout, wait_timeout)

    # ==================================================================
    # Coordenadas, teclado
    # ==================================================================
    def click_at(self, location, mouse_button="left", delay=0, show_overlay=None):
        """Clica numa caixa ``(x, y, largura, altura)`` ou num ponto já resolvido.

        Returns:
            sempre ``True``.
        """
        self._act(location, mouse_button, delay, None, show_overlay)
        return True

    def click_coordinates(self, x, y, delay=0, mouse_button="left", backtrack=False):
        """Clica nas coordenadas ``(x, y)``.

        Returns:
            sempre ``True``.
        """
        if backtrack:
            return self._with_backtrack(f"click_coordinates ({x}, {y})", self.click_coordinates,
                                        x, y, delay, mouse_button, False)
        self._act(Region(int(x), int(y), 1, 1), mouse_button, delay)
        return True

    def type_text(self, text, interval=0.05, delay=0, backtrack=False):
        """Digita texto.

        Aceita macros ``{tab}``, ``{enter}``, ``{ctrl}a``, ``{tab*3}``, ``{wait 1}``.

        Returns:
            sempre ``True``.
        """
        if backtrack:
            return self._with_backtrack("type_text", self.type_text, text, interval, delay, False)
        if has_macros(str(text)):
            self._commander.process_sendtext_command(str(text))
        else:
            self._commander.type_text(str(text), interval)
        if delay:
            time.sleep(float(delay))
        return True

    def keyboard_command(self, command, delay=0, backtrack=False):
        """Executa um atalho: ``"Ctrl+S"``, ``"F7"``, ``"Alt+Tab"``...

        Returns:
            ``True`` se o comando foi enviado.
        """
        if backtrack:
            return self._with_backtrack(f"keyboard_command {command}", self.keyboard_command,
                                        command, delay, False)
        ok = self._commander.execute_command(command)
        if delay:
            time.sleep(float(delay))
        return ok

    def get_available_keyboard_commands(self):
        """Nomes dos atalhos conhecidos (combinações livres também são aceitas)."""
        return self._commander.get_available_commands()

    # ==================================================================
    # Esperas
    # ==================================================================
    def wait_for_image(self, image_path, timeout=10, region=None, confidence=0.9, specific=True):
        """Espera uma imagem aparecer.

        Returns:
            caixa da imagem ou ``None`` se o tempo acabar.
        """
        return self._wait(Image(image_path, self._region(region), confidence, not specific), timeout)

    def wait_for_text(self, text, timeout=10, region=None, filter_type="both",
                      confidence_threshold=None):
        """Espera um texto aparecer.

        Returns:
            caixa do texto ou ``None`` se o tempo acabar.
        """
        spec = Text(text, self._region(region), _KINDS.get(str(filter_type).lower(), "text"), None,
                    confidence_threshold)
        return self._wait(spec, timeout)

    def wait_until_gone(self, image_path=None, text=None, timeout=10, region=None, confidence=0.9):
        """Espera uma imagem ou um texto sumir da tela.

        Informe ``image_path`` ou ``text``.

        Returns:
            ``True`` se sumiu, ``False`` se ainda estiver visível no fim do tempo.
        """
        if image_path is not None:
            spec = Image(image_path, self._region(region), confidence)
        elif text is not None:
            spec = Text(text, self._region(region))
        else:
            raise ValueError("Informe image_path ou text")
        return self._wait_gone(spec, timeout)

    def _wait(self, spec, timeout):
        """Espera o alvo aparecer. Devolve a caixa ou ``None``."""
        deadline = time.monotonic() + float(timeout)
        while True:
            found = self._poll(spec, 1)
            if found is not None or time.monotonic() >= deadline:
                return found
            time.sleep(self._ctx.settings.retry_pause)

    # ==================================================================
    # Listas de tarefas
    # ==================================================================
    def execute_tasks(self, tasks):
        """Executa uma lista de tarefas (dicts).

        Com ``'backtrack': True``, se a tarefa falhar a anterior é refeita e
        ela é tentada de novo. ``wait_until_disappears`` nas tarefas de clique
        espera o alvo sumir; o clique já conta como sucesso.

        Returns:
            ``list[TaskResult]``.
        """
        if not tasks:
            return []
        results = [None] * len(tasks)
        for i, task in enumerate(tasks):
            result = self._run_task(task, i)
            recoveries = 0
            while (not result.success and isinstance(task, dict) and task.get("backtrack")
                   and not task.get("optional") and i > 0
                   and recoveries < self._ctx.settings.recoveries):
                recoveries += 1
                logger.info(f"↩ Tarefa {i + 1} falhou — refazendo a tarefa {i} [{recoveries}]")
                results[i - 1] = self._run_task(tasks[i - 1], i - 1)
                if not results[i - 1].success:
                    break
                result = self._run_task(task, i)
            result.recoveries = recoveries
            results[i] = result
            status = "✓" if result.success else ("–" if result.optional else "✗")
            logger.info(f"{status} [{i + 1}/{len(tasks)}] {result.task_name}")
            required = isinstance(task, dict) and task.get("required")
            if not result.success and not result.optional and (required or self._ctx.settings.stop_on_failure):
                logger.error(f"Lista interrompida na tarefa {i + 1} ({'required' if required else 'stop_on_failure'})")
                for j in range(i + 1, len(tasks)):
                    results[j] = TaskResult(j, False, _task_name(tasks[j], j), error="não executada")
                break
        return [r for r in results if r is not None]

    def _run_task(self, task, index):
        """Roda uma tarefa e devolve o ``TaskResult``."""
        name = _task_name(task, index)
        if not isinstance(task, dict):
            return TaskResult(index, False, name, error="tarefa não é um dicionário")
        result = TaskResult(index, False, name)
        result.optional = bool(task.get("optional"))
        try:
            ok = self._dispatch(task)
            result.success = bool(ok)
            if not ok:
                result.error = "alvo não encontrado"
        except Exception as e:
            if is_emergency_stop(e):
                raise
            result.error = str(e)
            logger.warning(f"Tarefa {index + 1}: {e}")
        return result

    def _dispatch(self, task):
        """Interpreta o dict da tarefa e executa a ação correspondente."""
        kind = str(task.get("type", "")).lower()
        act = {k: task.get(k) for k in ("mouse_button", "delay", "sendtext", "show_overlay")
               if task.get(k) is not None}
        attempts = int(task.get("max_attempts", 3))
        timeout = task.get("timeout", task.get("wait_timeout"))
        wait_until_found = bool(task.get("wait_until_found"))
        wait_until_disappears = bool(task.get("wait_until_disappears"))

        def locate(spec):
            return self._locate(spec, attempts, timeout, wait_until_found,
                                wait_until_disappears=wait_until_disappears)

        if kind == "click":
            return self.click_coordinates(task["x"], task["y"], task.get("delay", 0),
                                          task.get("mouse_button", "left"))
        if kind == "type_text":
            return self.type_text(task.get("text", ""), task.get("interval", 0.05), task.get("delay", 0))
        if kind == "keyboard_command":
            return self.keyboard_command(task.get("command", ""), task.get("delay", 0))
        if kind == "wait":
            time.sleep(float(task.get("seconds", 1)))
            return True
        if kind == "scroll":
            point = (task["x"], task["y"]) if "x" in task and "y" in task else None
            self._ctx.mouse.scroll(int(task.get("clicks", -3)), point)
            return True
        if kind == "extract_text":
            self.extract_text_from_region(
                task.get("region"), task.get("filter_type", "both"),
                task.get("confidence_threshold", 50.0), task.get("return_full_data", False),
                task.get("max_attempts", 3), task.get("backtrack", False))
            return True
        if kind == "focus_window":
            from .core import windows

            return windows.focus_window(task.get("title"), float(task.get("timeout", 5)))
        if kind in ("wait_image", "wait_text", "wait_until_gone"):
            gone = bool(task.get("gone", kind == "wait_until_gone"))
            limit = float(task.get("timeout", 10))
            if gone:
                return self.wait_until_gone(task.get("image"), task.get("text"), limit, task.get("region"),
                                            task.get("confidence", 0.9))
            if "image" in task:
                return self.wait_for_image(task["image"], limit, task.get("region"),
                                           task.get("confidence", 0.9)) is not None
            return self.wait_for_text(task["text"], limit, task.get("region"),
                                      task.get("char_type", "both")) is not None

        if kind == "relative_image":
            target = Image(task["target_image"], None, task.get("confidence", 0.9))
            if task.get("anchor_text"):
                anchor = Text(task["anchor_text"], self._region(task.get("region")))
            else:
                anchor = Image(task["anchor_image"], self._where, task.get("confidence", 0.9))
            region = task.get("target_region")
            spec = Near(target, anchor, task.get("max_distance", 200), as_region(region) if region else None)
        elif "image" in task and kind in ("", "image"):
            spec = Image(task["image"], self._region(task.get("region")),
                         task.get("confidence", 0.9), not task.get("specific", True), task.get("scales"))
        elif "text" in task and kind in ("", "text"):
            occurrence = task.get("occurrence")
            spec = Text(task["text"], self._region(task.get("region")),
                        _KINDS.get(str(task.get("char_type", "both")).lower(), "text"),
                        occurrence if occurrence and occurrence > 1 else None,
                        task.get("confidence_threshold", task.get("early_confidence")))
        else:
            raise VizionError(f"Tarefa sem 'image', 'text' ou 'type' válido: {task!r}")

        location = locate(spec)
        if location is None:
            self._ctx.failure_shot(f"tarefa_{_task_name(task, 0)}")
            return False
        self._act(location, act.get("mouse_button", "left"), act.get("delay", 0),
                  act.get("sendtext"), act.get("show_overlay"))
        return self._finish_gone(spec, wait_until_disappears, timeout)

    def execute_with_backtrack_between_tasks(self, tasks_list):
        """Executa tarefas no formato ``{'type': 'text'|'image'|..., 'params': {...}}``.

        Se uma falhar, refaz a anterior e tenta de novo.

        Returns:
            ``list[bool]`` na ordem das tarefas.
        """
        runners = {"text": self.click_text, "image": self.click_image,
                   "relative_image": self.click_relative_image, "click": self.click_coordinates,
                   "type_text": self.type_text, "keyboard_command": self.keyboard_command}

        def run(i):
            spec = tasks_list[i]
            params = dict(spec.get("params", {}))
            params.pop("backtrack", None)
            runner = runners.get(spec.get("type"))
            return bool(runner(**params)) if runner else False

        results = []
        for i, spec in enumerate(tasks_list):
            results.append(run(i))
            recoveries = 0
            while (not results[i] and i > 0 and spec.get("params", {}).get("backtrack", True)
                   and recoveries < self._ctx.settings.recoveries):
                recoveries += 1
                results[i - 1] = run(i - 1)
                if not results[i - 1]:
                    break
                results[i] = run(i)
        return results


def limpar_texto(texto, filter_type="both"):
    """Remove caracteres do texto conforme o filtro.

    ``"numbers"`` deixa só dígitos, ``"letters"`` só letras,
    ``"both"`` letras e números. Qualquer outro valor só corta pontuação das pontas.
    """
    import re

    if not isinstance(texto, str):
        return ""
    texto = texto.strip()
    if filter_type == "numbers":
        return re.sub(r"[^\d]", "", texto)
    if filter_type == "letters":
        return re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ]", "", texto)
    if filter_type == "both":
        return re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ0-9]", "", texto)
    return re.sub(r"^[\W_]+|[\W_]+$", "", texto)


clean_text = limpar_texto


def _task_name(task, index):
    """Rótulo curto da tarefa para log e ``TaskResult``."""
    if not isinstance(task, dict):
        return f"Tarefa {index + 1}"
    kind = str(task.get("type", "")).lower()
    if kind == "relative_image":
        anchor = task.get("anchor_text") or os.path.basename(str(task.get("anchor_image", "?")))
        return f"{os.path.basename(str(task.get('target_image', '?')))} perto de {anchor}"
    if kind == "click":
        return f"clique ({task.get('x')}, {task.get('y')})"
    if kind == "keyboard_command":
        return f"tecla {task.get('command')}"
    if kind == "type_text":
        return f"digitar '{str(task.get('text', ''))[:25]}'"
    if kind:
        return f"{kind} {task.get('image') or task.get('text') or task.get('title') or ''}".strip()
    if "text" in task:
        return str(task["text"])
    if "image" in task:
        return os.path.basename(str(task["image"]))
    return f"Tarefa {index + 1}"


__all__ = ["ClassicMixin", "TaskResult", "limpar_texto", "clean_text"]
