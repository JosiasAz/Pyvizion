from conftest import requires_tesseract
from pyvizion.core.enhance import ALL_METHODS, Enhancer
from pyvizion.core.reader import TextHit, TextReader, _dedupe, _reading_order
from pyvizion.settings import Settings


def _reader(**extra):
    return TextReader(Settings(ocr_quality="fast", **extra))


def test_enhancer_gera_variacoes(render_text):
    img = render_text([("Teste", (10, 10))])
    variants = Enhancer("all").variants(img)
    assert len(variants) == len(ALL_METHODS)
    assert all(v.mode == "L" for v in variants)
    assert len(Enhancer("fast").variants(img)) < len(variants)


def test_dedupe_consenso_e_ordem_de_leitura():
    a = TextHit("x", 80, (300, 10, 50, 20), method_index=0)
    a_dup = TextHit("x", 70, (302, 11, 50, 20), method_index=1)
    b = TextHit("x", 60, (10, 12, 50, 20))
    c = TextHit("x", 90, (10, 100, 50, 20))
    ordered = _reading_order(_dedupe([a, a_dup, b, c]))
    assert [h.box[:2] for h in ordered] == [(10, 12), (300, 10), (10, 100)]
    assert ordered[1].confidence > 80  # duas leituras concordaram


@requires_tesseract
def test_encontra_palavra(render_text):
    img = render_text([("Cancelar", (20, 40)), ("Salvar", (300, 40))])
    hits, _ = _reader().find(img, "Salvar")
    assert hits
    x, y, _, _ = max(hits, key=lambda h: h.confidence).box
    assert 290 <= x <= 320 and 30 <= y <= 60


@requires_tesseract
def test_frase_nao_confunde_parecida(render_text):
    img = render_text([("Data Inicial:", (20, 40)), ("Data Final:", (20, 120))])
    hits, _ = _reader().find(img, "Data Final")
    assert hits and all(100 <= h.box[1] <= 140 for h in hits)


@requires_tesseract
def test_ignora_acentos_e_caixa(render_text):
    img = render_text([("USUÁRIO", (20, 40))])
    assert _reader().find(img, "usuario")[0]


@requires_tesseract
def test_ocorrencias_distintas(render_text):
    img = render_text([("Editar", (20, 40)), ("Editar", (20, 120))], size=(400, 200))
    hits, _ = _reader().find(img, "Editar", nth=2)
    tops = sorted(h.box[1] for h in hits)
    assert len(hits) == 2 and tops[1] - tops[0] > 50


@requires_tesseract
def test_texto_claro_em_fundo_escuro(render_text):
    img = render_text([("Confirmar", (20, 40))], bg=(40, 40, 40), fg=(230, 230, 230))
    assert _reader().find(img, "Confirmar")[0]


@requires_tesseract
def test_texto_pequeno(render_text):
    img = render_text([("Pesquisar", (5, 5))], size=(120, 30), font_size=12)
    assert _reader().find(img, "Pesquisar")[0]


@requires_tesseract
def test_read(render_text):
    img = render_text([("Pedido 4521", (10, 10))], size=(300, 60))
    assert "4521" in _reader().read(img, line=True)


@requires_tesseract
def test_texto_ausente(render_text):
    img = render_text([("Cancelar", (20, 40))])
    hits, early = _reader().find(img, "Imprimir")
    assert hits == [] and not early
