"""
Vizion - Leitor de texto (OCR com Tesseract)

- várias versões tratadas da imagem × modos do Tesseract, em **paralelo**;
- para assim que encontra o texto com confiança suficiente;
- **consenso**: leituras repetidas no mesmo lugar ganham pontos;
- comparação tolerante: acentos, maiúsculas, confusões (0/O, 1/l, 5/S), leitura
  aproximada e palavras coladas/quebradas;
- ocorrências distintas em ordem de leitura (``nth``);
- ``read`` devolve o texto de uma área.
"""

import logging
import os
import statistics
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import List, Optional, Tuple

from PIL import Image

from ..exceptions import OCRUnavailable
from ..settings import Settings
from . import tesseract
from .enhance import Enhancer
from .text import check_kind, normalize, similarity

logger = logging.getLogger(__name__)

_SETUP_LOCK = threading.Lock()
EXACT_RATIO = 0.96
CONSENSUS_BONUS = 3.0

_DIGITS = "-c tessedit_char_whitelist=0123456789./-:,"


def tesseract_modes(single_line: bool, numeric: bool) -> List[str]:
    """
    Modos de segmentação do Tesseract a testar, conforme o formato da região.

    - região de uma linha: linha única (7) e texto esparso (11);
    - região maior: texto esparso (11) — típico de telas com campos soltos — e bloco (6).
    Para alvos numéricos, cada modo também roda restrito a dígitos.
    """
    psms = (7, 11) if single_line else (11, 6)
    modes = [f"--oem 3 --psm {p}" for p in psms]
    if numeric:
        modes = [f"{m} {_DIGITS}" for m in modes] + modes
    return modes


class TextHit:
    """Texto lido: valor, confiança (0–100+) e caixa ``(x, y, largura, altura)`` relativa à imagem."""

    def __init__(self, text: str, confidence: float, box: Tuple[int, int, int, int],
                 method_index: int = 0, config_index: int = 0, ratio: float = 1.0):
        self.text = text
        self.confidence = confidence
        self.box = box
        self.method_index = method_index
        self.config_index = config_index
        self.ratio = ratio

    def __repr__(self):
        return f"TextHit(text='{self.text}', confidence={self.confidence:.2f}, box={self.box})"


class TextReader:
    """
    Leitor de texto da tela.

        >>> reader = TextReader(Settings(language="por"))
        >>> hits, early = reader.find(imagem, "Salvar")
        >>> reader.read(imagem)
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        self.enhancer = Enhancer(self.settings.ocr_quality)
        self._info = None

    # ------------------------------------------------------------------
    # Tesseract
    # ------------------------------------------------------------------
    def _setup(self) -> None:
        if self._info is not None:
            return
        with _SETUP_LOCK:
            if self._info is None:
                self._info = tesseract.prepare(self.settings)

    @property
    def language(self):
        self._setup()
        return self._info["language"]

    def _image_to_data(self, img, config):
        import pytesseract

        kwargs = {"output_type": pytesseract.Output.DICT, "config": config}
        if self._info and self._info.get("language"):
            kwargs["lang"] = self._info["language"]
        return pytesseract.image_to_data(img, **kwargs)

    def _workers(self) -> int:
        workers = max(1, int(self.settings.ocr_threads or min(4, os.cpu_count() or 1)))
        if workers > 1:
            # Evita que cada processo do Tesseract abra N threads OpenMP.
            os.environ.setdefault("OMP_THREAD_LIMIT", "1")
        return workers

    def _upscale_factor(self, img: Image.Image) -> float:
        factor = float(self.settings.ocr_upscale or 1.0)
        if factor <= 1.0:
            return 1.0
        # Não amplia capturas grandes (tela cheia): custo alto, ganho pequeno.
        if max(img.width, img.height) > 1400 or img.width * img.height > 1_200_000:
            return 1.0
        return factor

    # ------------------------------------------------------------------
    # Busca de texto
    # ------------------------------------------------------------------
    def find(self, region_img: Image.Image, target_text: str, kind: str = "text",
             confidence: Optional[float] = None, nth: int = 1,
             exact: bool = False) -> Tuple[List[TextHit], bool]:
        """
        Procura um texto (uma ou mais palavras) na imagem.

        Returns:
            (hits, antecipado): ocorrências distintas em ordem de leitura e se a busca
            terminou antes por ter achado com confiança suficiente.
        """
        self._setup()
        kind = check_kind(kind)
        wanted = max(1, int(nth or 1))
        min_confidence = float(self.settings.text_confidence if confidence is None
                                           else confidence)
        fuzzy_min = 0.0 if exact else float(self.settings.fuzzy)
        target = [normalize(w, kind) for w in str(target_text).split()]
        target = [w for w in target if w]
        if not target:
            logger.warning(f"Texto '{target_text}' fica vazio com kind='{kind}'.")
            return [], False

        try:
            factor = self._upscale_factor(region_img)
            base = Enhancer.upscale(region_img.convert("RGB"), factor)
            methods = None
            if base.width * base.height > 1_500_000:
                # Tela inteira: cada chamada do Tesseract custa ~1 s; usa as variações
                # mais eficazes. Para precisão máxima, informe uma área.
                methods = self.settings.ocr_quality_fullscreen
            variants = self.enhancer.variants(base, methods)
        except Exception as e:
            raise OCRUnavailable(f"Falha ao preparar a imagem para OCR: {e}") from e

        numeric = kind == "digits" or all(w.isdigit() for w in target)
        single_line = base.height <= 110 * max(factor, 1.0)
        modes = tesseract_modes(single_line, numeric)
        jobs = [(img_index, img, mode)
                for img_index, img in enumerate(variants)
                for mode in modes]

        logger.debug(f"Procurando '{target_text}' ({len(variants)} variações × {len(modes)} modos)")
        collected: List[TextHit] = []

        def run(job):
            img_index, img, mode = job
            found = self._process_single_image(img, target, kind, mode, img_index, factor,
                                               fuzzy_min)
            for r in found:
                r.config_index = modes.index(mode)
            return found

        def satisfied():
            # Só encerra cedo com correspondência exata (fuzzy nunca antecipa).
            strong = [r for r in collected
                      if r.confidence >= min_confidence and r.ratio >= EXACT_RATIO]
            if not strong:
                return False
            if wanted == 1:
                return True
            return len(_dedupe(strong)) >= wanted

        early = False
        workers = self._workers()
        if workers == 1:
            for job in jobs:
                collected.extend(run(job))
                if satisfied():
                    early = True
                    break
        else:
            executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pyvizion-ocr")
            try:
                pending = set()
                job_iter = iter(jobs)

                def fill():
                    while len(pending) < workers * 2:
                        try:
                            pending.add(executor.submit(run, next(job_iter)))
                        except StopIteration:
                            return

                fill()
                while pending:
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for fut in done:
                        try:
                            collected.extend(fut.result())
                        except Exception as e:
                            logger.debug(f"Falha em job de OCR: {e}")
                    if satisfied():
                        early = True
                        break
                    fill()
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        if any(r.ratio >= EXACT_RATIO for r in collected):
            # Havendo correspondência exata, aproximações são descartadas
            # (evita "Data Inicial" contar como ocorrência de "Data Final").
            collected = [r for r in collected if r.ratio >= EXACT_RATIO]
        results = _reading_order(_dedupe(collected))
        if early and wanted == 1:
            best = max(results, key=lambda r: r.confidence)
            logger.debug(f"'{target_text}' lido com {best.confidence:.1f}% de confiança")
        return results, early

    def _process_single_image(self, img, target_words, kind, mode,
                              img_index, factor, fuzzy_min) -> List[TextHit]:
        try:
            data = self._image_to_data(img, mode)
        except ImportError:
            raise OCRUnavailable("pytesseract não está instalado") from None
        except Exception as e:
            logger.debug(f"Erro em OCR com modo {mode}: {e}")
            return []

        results = []
        for line in _lines(data):
            results.extend(self._match_line(line, target_words, kind, img_index, factor,
                                            fuzzy_min))
        return results

    def _match_line(self, line, target, kind, img_index, factor, fuzzy_min):
        fuzzy = fuzzy_min > 0
        words = []
        for w in line:
            plain = normalize(w["text"], kind)
            if plain:
                fixed = normalize(w["text"], kind, fix=True)
                words.append((w, plain, fixed))
        if not words:
            return []

        n = len(target)
        target_joined = "".join(target)
        found = []
        i = 0
        while i < len(words):
            best = None  # (ratio, span)
            window = words[i:i + n]
            if len(window) == n:
                if all(window[k][1] == target[k] for k in range(n)):
                    best = (1.0, n)
                elif all(window[k][2] == target[k] for k in range(n)):
                    best = (0.97, n)
            if best is None:
                # Palavras coladas ("SalvarDados") ou quebradas ("Sal var").
                for span in sorted({max(1, n - 1), n, n + 1}):
                    part = words[i:i + span]
                    if len(part) != span:
                        continue
                    joined = "".join(p[1] for p in part)
                    joined_fixed = "".join(p[2] for p in part)
                    if joined == target_joined:
                        best = (0.99, span)
                        break
                    if joined_fixed == target_joined:
                        best = (0.96, span)
                        break
                    if fuzzy and len(target_joined) >= 4:
                        ratio = max(similarity(joined, target_joined),
                                    similarity(joined_fixed, target_joined))
                        needed = fuzzy_min if len(target_joined) > 5 else max(fuzzy_min, 0.85)
                        if span == n and n > 1:
                            # Frases: cada palavra precisa se parecer com a esperada.
                            per_word = min(similarity(part[k][1], target[k]) for k in range(n))
                            if per_word < 0.7:
                                continue
                        if ratio >= needed and (best is None or ratio > best[0]):
                            best = (ratio, span)
            if best is None:
                i += 1
                continue

            ratio, span = best
            part = [p[0] for p in words[i:i + span]]
            found.append(self._hit(part, img_index, factor, ratio))
            i += span
        return found

    def _hit(self, part, img_index, factor, ratio):
        confs = [w["conf"] for w in part if w["conf"] > 0]
        avg_conf = sum(confs) / len(confs) if confs else 0.0
        left = min(w["left"] for w in part)
        top = min(w["top"] for w in part)
        right = max(w["left"] + w["width"] for w in part)
        bottom = max(w["top"] + w["height"] for w in part)
        box = (
            int(round(left / factor)),
            int(round(top / factor)),
            max(1, int(round((right - left) / factor))),
            max(1, int(round((bottom - top) / factor))),
        )
        # Aproximações (fuzzy) perdem pontos proporcionalmente à diferença.
        confidence = avg_conf - (1.0 - ratio) * 100.0
        return TextHit(
            text=" ".join(w["text"] for w in part),
            confidence=confidence,
            box=box,
            method_index=img_index,
            ratio=ratio,
        )

    # ------------------------------------------------------------------
    # Extração / leitura
    # ------------------------------------------------------------------
    def words(self, img: Image.Image, kind: str = "any") -> List[TextHit]:
        """Todas as palavras lidas na imagem, com caixas relativas à imagem."""
        self._setup()
        kind = check_kind(kind)
        factor = self._upscale_factor(img)
        prepared = _auto_invert(Enhancer.upscale(img.convert("RGB"), factor).convert("L"))
        data = self._image_to_data(prepared, r"--oem 3 --psm 11")

        results = []
        for line in _lines(data):
            for w in line:
                cleaned = normalize(w["text"], kind)
                if not cleaned:
                    continue
                box = (int(w["left"] / factor), int(w["top"] / factor),
                       max(1, int(w["width"] / factor)), max(1, int(w["height"] / factor)))
                results.append(TextHit(text=w["text"], confidence=w["conf"], box=box))
        return results

    def read(self, img: Image.Image, line: bool = False) -> str:
        """Lê o texto de uma imagem; testa algumas variações e fica com a mais confiável."""
        self._setup()
        factor = self._upscale_factor(img)
        base = Enhancer.upscale(img.convert("RGB"), factor)
        variants = [_auto_invert(base.convert("L"))]
        variants += self.enhancer.variants(base, ["clahe", "sharpen", "color_distance"])
        psm = "7" if line else "6"

        best_text, best_score = "", -1.0
        for variant in variants:
            try:
                data = self._image_to_data(variant, f"--oem 3 --psm {psm}")
            except Exception as e:
                logger.debug(f"read: {e}")
                continue
            lines = _lines(data)
            confs = [w["conf"] for row in lines for w in row if w["conf"] > 0]
            if not confs:
                continue
            score = statistics.mean(confs)
            if score > best_score:
                best_score = score
                best_text = "\n".join(" ".join(w["text"] for w in row) for row in lines)
            if score >= 90:
                break
        return best_text.strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lines(data):
    """Agrupa palavras do Tesseract por linha, preservando a ordem."""
    lines = {}
    order = []
    texts = data.get("text", [])
    for i, text in enumerate(texts):
        if not str(text).strip():
            continue
        if "level" in data and int(data["level"][i]) != 5:
            continue
        key = (data.get("block_num", [0] * len(texts))[i],
               data.get("par_num", [0] * len(texts))[i],
               data.get("line_num", [0] * len(texts))[i])
        if key not in lines:
            lines[key] = []
            order.append(key)
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        lines[key].append({
            "text": str(text).strip(),
            "conf": conf,
            "left": int(data["left"][i]),
            "top": int(data["top"][i]),
            "width": int(data["width"][i]),
            "height": int(data["height"][i]),
        })
    return [lines[k] for k in order]


def _auto_invert(gray: Image.Image) -> Image.Image:
    """Texto claro em fundo escuro → inverte (Tesseract prefere texto escuro)."""
    from PIL import ImageOps, ImageStat

    if ImageStat.Stat(gray).mean[0] < 110:
        return ImageOps.invert(gray)
    return gray


def _box_iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    if inter == 0:
        return 0.0
    return inter / float(aw * ah + bw * bh - inter)


def _same_place(a, b):
    if _box_iou(a, b) >= 0.4:
        return True
    acx, acy = a[0] + a[2] / 2, a[1] + a[3] / 2
    bx, by, bw, bh = b
    return bx <= acx <= bx + bw and by <= acy <= by + bh


def _dedupe(results: List[TextHit]) -> List[TextHit]:
    """
    Agrupa detecções da mesma posição e mantém a de maior confiança.

    Consenso: cada variação/modo extra que leu o mesmo texto no mesmo lugar soma
    ``CONSENSUS_BONUS`` pontos (até 5 votos), o que favorece leituras estáveis.
    """
    groups: List[List[TextHit]] = []
    for r in sorted(results, key=lambda r: r.confidence, reverse=True):
        for group in groups:
            head = group[0]
            if _same_place(r.box, head.box) or _same_place(head.box, r.box):
                group.append(r)
                break
        else:
            groups.append([r])
    kept = []
    for group in groups:
        best = group[0]
        votes = len({(g.method_index, g.config_index) for g in group})
        kept.append(TextHit(best.text, best.confidence + CONSENSUS_BONUS * (min(votes, 6) - 1),
                              best.box, best.method_index, best.config_index, best.ratio))
    return kept


def _reading_order(results: List[TextHit]) -> List[TextHit]:
    """Ordena de cima para baixo e da esquerda para a direita."""
    if not results:
        return []
    items = sorted(results, key=lambda r: r.box[1] + r.box[3] / 2)
    rows, current, row_y = [], [], None
    for r in items:
        cy = r.box[1] + r.box[3] / 2
        tolerance = max(6, r.box[3] * 0.6)
        if row_y is None or abs(cy - row_y) <= tolerance:
            current.append(r)
            row_y = cy if row_y is None else (row_y + cy) / 2
        else:
            rows.append(current)
            current, row_y = [r], cy
    rows.append(current)
    return [r for row in rows for r in sorted(row, key=lambda r: r.box[0])]
