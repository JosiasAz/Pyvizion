"""
Exemplo básico do pyvizion.

Coloque os recortes PNG na pasta "imagens" ao lado deste arquivo.
"""

from pyvizion import Vizion

vz = Vizion({"image_folders": ["imagens"], "tesseract_lang": "por"})

vz.click_image("menu.png", backtrack=True)
vz.click_text("Relatórios", backtrack=True)
vz.click_text("Vendas", backtrack=True)

ok, total = vz.end_task_session()
print(f"Sucesso: {ok}/{total}")
