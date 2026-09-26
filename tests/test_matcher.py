import cv2
import numpy as np
import pytest

from pyvizion.core.matcher import DEFAULT_WIDE_SCALES, ImageMatcher
from pyvizion.core.screen import load_image


def _scene_and_template():
    rng = np.random.default_rng(42)
    scene = np.full((400, 600, 3), 235, np.uint8)
    template = rng.integers(0, 255, (40, 60, 3), dtype=np.uint8)
    cv2.putText(template, "OK", (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    return scene, template


def test_locate_exato():
    scene, template = _scene_and_template()
    scene[100:140, 200:260] = template
    m = ImageMatcher().in_image(template, scene, precision=0.9)
    assert m is not None
    assert tuple(m.region) == (200, 100, 60, 40)
    assert m.score > 0.99


def test_locate_com_origem_de_tela():
    scene, template = _scene_and_template()
    scene[10:50, 20:80] = template
    m = ImageMatcher().in_image(template, scene, precision=0.9, origin=(-1920, 0))
    assert (m.region.x, m.region.y) == (-1900, 10)


def test_locate_com_escala_diferente():
    scene, template = _scene_and_template()
    scaled = cv2.resize(template, (54, 36), interpolation=cv2.INTER_AREA)  # 0.9x
    scene[200:236, 300:354] = scaled
    matcher = ImageMatcher()
    assert matcher.in_image(template, scene, precision=0.9, scales=(1.0,)) is None
    m = matcher.in_image(template, scene, precision=0.85, scales=DEFAULT_WIDE_SCALES)
    assert m is not None and abs(m.region.x - 300) <= 3 and abs(m.region.y - 200) <= 3
    assert m.scale == pytest.approx(0.9)


def test_locate_all_sem_duplicatas():
    scene, template = _scene_and_template()
    for x in (20, 200, 400):
        scene[50:90, x:x + 60] = template
    boxes = sorted(m.region.x for m in ImageMatcher().all_in_image(template, scene, precision=0.9))
    assert boxes == [20, 200, 400]


def test_template_de_cor_solida_compara_cor():
    scene = np.full((100, 100, 3), 255, np.uint8)
    scene[40:60, 40:60] = (0, 0, 200)
    red = np.zeros((10, 10, 3), np.uint8)
    red[:] = (0, 0, 200)
    black = np.zeros((10, 10, 3), np.uint8)
    m = ImageMatcher(grayscale=False).in_image(red, scene, precision=0.9)
    assert m is not None and 40 <= m.region.x <= 50 and 40 <= m.region.y <= 50
    assert ImageMatcher(grayscale=False).in_image(black, scene, precision=0.9) is None


def test_template_maior_que_cena():
    scene = np.zeros((20, 20, 3), np.uint8)
    template = np.zeros((40, 40, 3), np.uint8)
    assert ImageMatcher().in_image(template, scene, precision=0.5) is None


def test_carrega_caminho_com_acentos(tmp_path):
    folder = tmp_path / "Área de Trabalho"
    folder.mkdir()
    path = folder / "botão.png"
    _, template = _scene_and_template()
    ok, data = cv2.imencode(".png", template)
    data.tofile(str(path))
    img = load_image(str(path))
    assert img.shape == template.shape


def test_arquivo_inexistente_da_erro_claro():
    from pyvizion.exceptions import ImageFileError

    with pytest.raises(ImageFileError, match="não encontrado"):
        load_image("nao_existe_123.png")


def test_image_dirs(tmp_path):
    _, template = _scene_and_template()
    cv2.imencode(".png", template)[1].tofile(str(tmp_path / "salvar.png"))
    assert load_image("salvar.png", folders=[str(tmp_path)]).shape == template.shape


def test_png_com_transparencia(tmp_path):
    rgba = np.zeros((20, 20, 4), np.uint8)
    rgba[5:15, 5:15] = (0, 0, 255, 255)
    path = tmp_path / "alpha.png"
    cv2.imencode(".png", rgba)[1].tofile(str(path))
    img = load_image(str(path))
    assert img.shape == (20, 20, 3)
    assert tuple(img[0, 0]) == (128, 128, 128)
