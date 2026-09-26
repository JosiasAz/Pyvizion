"""
Cadastro em um ERP legado (Oracle Forms / Delphi / Citrix): foco de janela,
esperas, alternativas, âncoras e lista de tarefas com backtrack.
"""

from pyvizion import Vizion

vz = Vizion({
    "image_folders": ["imagens"],
    "tesseract_lang": "por",
    "save_failure_screenshots": True,   # print de cada falha em ./pyvizion_failures
})

JANELA = "Oracle Applications"

if not vz.focus_window(JANELA, timeout=10):
    raise SystemExit(f"Janela '{JANELA}' não encontrada")
area = vz.window_region(JANELA)

# O botão "Novo" muda de aparência conforme a versão do sistema
if vz.click_any(["novo_v1.png", "novo_v2.png", "Novo"], timeout=10, region=area) is None:
    raise SystemExit("Botão 'Novo' não encontrado")

vz.wait_until_gone("ampulheta.png", timeout=60, region=area)

resultado = vz.execute_tasks([
    {"text": "Código", "region": area, "sendtext": "{ctrl}a{del}12345", "backtrack": True},
    {"text": "Nome", "region": area, "sendtext": "{ctrl}a{del}José da Conceição"},
    {"type": "relative_image", "anchor_text": "Cidade", "target_image": "lupa.png", "max_distance": 250},
    {"text": "Manaus", "region": area, "mouse_button": "double", "backtrack": True},
    {"image": "popup_aviso.png", "optional": True, "sendtext": "{enter}", "max_attempts": 1},
    {"type": "keyboard_command", "command": "Ctrl+S", "required": True},
    {"type": "wait_text", "text": "Registro salvo", "region": area, "timeout": 20},
])

rotulo = vz.find_text("Protocolo", region=area)
if rotulo:
    x, y, w, h = rotulo
    print("Protocolo:", vz.read_text((x + w + 5, y - 4, 220, h + 8), single_line=True))
print("Tarefas:", [r.success for r in resultado])
