<p align="center">
  <img src="https://files.catbox.moe/skh0jr.png" alt="pyvizion" width="420">
</p>

<p align="center">
  <strong>Biblioteca Python para automação de interface por imagem e texto</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/pyvizion/"><img src="https://img.shields.io/badge/PyPI-v1.0.8-146B43" alt="PyPI v1.0.8"></a>
  <a href="https://pypi.org/project/pyvizion/"><img src="https://img.shields.io/badge/python-3.9%2B-0B3D2C" alt="Python"></a>
  <img src="https://img.shields.io/badge/licença-MIT-1F7A4D" alt="MIT">
</p>

<p align="center">
  <a href="https://pypi.org/project/pyvizion/">PyPI</a> |
  <a href="#começar">Começar</a> |
  <a href="#como-funciona">Como funciona</a>
</p>

---

O **pyvizion** é uma biblioteca Python: localiza um botão ou um texto na tela, clica e digita. Se o passo falhar, o backtrack refaz a ação anterior e tenta de novo.

Serve para aplicativos desktop sem API: ERP, Oracle Forms, Delphi, Citrix. Só Windows. Linux e macOS têm limitação: sem clique virtual, sem foco de janela e sem o mesmo suporte de tela.

Os nomes e a ordem dos parâmetros seguem o [bot-vision-suite](https://pypi.org/project/bot-vision-suite/) 1.3.0. Quem já usa esses métodos troca o import; a busca na tela é implementação deste pacote.

```python
from pyvizion import Vizion

vz = Vizion()
vz.click_image("menu.png", backtrack=True)
vz.click_text("Relatórios", backtrack=True)
vz.click_text("Confirmar", sendtext="{enter}")
```

A versão publicada é a **1.0.8**. As versões 0.3.x no PyPI são outra API.

---

## Começar

```bash
pip install pyvizion
python -m pyvizion doctor
```

**Tesseract** é obrigatório ao criar `Vizion()`. Sem ele a instância nem sobe (`TesseractNotFoundError`).

| Sistema | Instalação |
| -------- | ---------- |
| Windows (suportado) | [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki) em `C:\Program Files\Tesseract-OCR\` |
| Linux / macOS (limitado) | `tesseract-ocr` / `brew install tesseract`. Sem clique virtual e sem foco de janela. |

Idioma padrão do OCR: **`eng`**. Tela em português: `Vizion({"tesseract_lang": "por"})` e o pacote `por`.

---

## Como funciona

Você chama `click_image("ok.png")` ou `click_text("Salvar")`. A biblioteca tira um print, procura o alvo e clica no meio dele.

1. **Tira o print:** cerca de 5 ms, funciona com dois monitores.
2. **Acha a imagem:** você recorta o botão, salva numa pasta (`imagens/ok.png`) e passa o caminho. A biblioteca procura essa figura na tela. Funciona mesmo se o Windows estiver com a tela aumentada (125% ou 150%).
3. **Acha o texto:** Tesseract (inglês por padrão; `tesseract_lang="por"` se a tela for em português).
4. **Clica e digita:** no centro do alvo. `use_virtual_mouse` no Windows não mexe o cursor.
5. **Se falhar:** com `backtrack=True`, refaz o passo anterior. Também espera aparecer ou sumir.

Se o alvo não estiver na tela, devolve `False` ou `None`. Vale `if not vz.click_text("OK")`. Erro só se faltar Tesseract ou o PNG não existir.

### O que melhorou

Os métodos são os mesmos do bot-vision-suite 1.3.0. O que mudou é o jeito de achar o alvo: mais rápido e mais estável com a tela aumentada e com mais de um monitor.

| | Antes (PyAutoGUI / BVS) | pyvizion |
| --- | --- | --- |
| Tirar o print | Lento (dezenas a centenas de ms) | Cerca de **5 ms** |
| Achar imagem | Falha fácil se a tela estiver aumentada | Acha mesmo com a tela em 125% ou 150% |
| Achar texto | Tela inteira é cara | Com `region`, cerca de **6x** mais rápido |
| Esperar o alvo | Cada tentativa paga o print lento | `wait_until_found` dá para usar de verdade |
| Zoom / 2 monitores | Clique no lugar errado | Clica no lugar certo nos dois monitores |
| Alvo sumiu | `False` / `None` | Igual: `if not vz.click_text("OK")` |
| Extra | (não tinha) | janelas, `click_any`, `doctor`, mouse virtual |

Os "5 ms" e o "6x" vêm do jeito de tirar o print e de ler só a área pedida, não de um teste oficial publicado.

---

## Uso

### Backtrack e esperas

```python
vz = Vizion()
vz.click_image("menu.png", backtrack=True)
vz.click_text("Relatórios", backtrack=True)
vz.click_image("salvar.png", wait_until_found=True, wait_timeout=15)
vz.find_image("ampulheta.png", wait_until_disappears=True, wait_timeout=60)
vz.click_image("ok.png", wait_until_disappears=True, wait_timeout=10)
```

`wait_until_disappears` no `find_*` devolve a caixa se o alvo sumiu, `None` se ainda estiver visível. No `click_*`, o clique **já valeu**: devolve `True` mesmo se o alvo continuar na tela.

### Sessão

```python
vz.start_task_session()
vz.click_image("button1.png", backtrack=True)
vz.click_text("Clientes", backtrack=True)
ok, total = vz.end_task_session()
```

### Lista de tarefas

```python
from pyvizion import execute_tasks

execute_tasks([
    {"image": "button.png", "region": (100, 100, 200, 50), "backtrack": True},
    {"text": "Login", "sendtext": "usuario123{tab}senha{enter}"},
    {"type": "relative_image", "anchor_image": "aviso.png", "target_image": "ok.png"},
    {"type": "keyboard_command", "command": "Ctrl+S"},
])
```

---

## Métodos

Assinaturas posicionais iguais às do bot-vision-suite 1.3.0.

| Método | Resultado |
| ------ | --------- |
| `click_image(...)` | `bool` |
| `find_image(...)` | `(x, y, w, h)` ou `None` |
| `click_text(...)` | `bool` |
| `find_text(...)` | caixa ou `None` |
| `click_relative_image(...)` / `find_relative_image(...)` | alvo mais perto da âncora |
| `click_at` / `click_coordinates` | clique em ponto |
| `type_text` / `keyboard_command` | digitação e atalhos |
| `extract_text_from_region` / `get_last_extracted_text` | OCR da área |
| `execute_tasks` / `execute_with_backtrack_between_tasks` | listas |
| `start_task_session` / `end_task_session` | sessão de backtrack |
| `configure_overlay` / `get_overlay_config` / `test_overlay_colors` | overlay |

Extras: `wait_for_image`, `wait_for_text`, `wait_until_gone`, `image_exists`, `text_exists`, `find_all_images`, `click_any`, `find_any`, `read_text`, `focus_window`, `wait_window`, `window_region`, `list_windows`, `press`, `hotkey`, `scroll`, `drag`, `screenshot`, `click_image_near_text`.

Também como funções: `from pyvizion import click_image, find_text, execute_tasks, limpar_texto`.

**Parâmetros que importam**

- `region=(x, y, largura, altura)`: use sempre que puder. `vz.window_region("Título")` devolve a janela.
- `specific=False`: tenta a região e depois a tela, em várias escalas.
- `mouse_button`: `"left"`, `"right"`, `"double"`, `"move_to"`.
- `filter_type`: `"letters"`, `"numbers"`, `"both"`. `occurrence=2` é a segunda na ordem de leitura.
- `wait_timeout`: segundos da espera (padrão da config: **30**).

`click_*` / `find_*` **não levantam** se o alvo sumiu. Ambiente quebrado sim: `TesseractNotFoundError` no `Vizion()`, `ImageFileError` se o PNG não existe. As classes `ImageNotFoundError` e `TextNotFoundError` existem para quem quiser capturar por nome.

---

## Campos (`sendtext`)

Texto digitado logo após o clique. `{chave}` é tecla.

```python
vz.click_text("Usuário", sendtext="admin{tab}senha123{enter}")
```

| Quero | `sendtext` |
| ----- | ---------- |
| campo vazio | `"12345"` |
| substituir o que está lá | `"{ctrl}a{del}12345"` |
| ir ao próximo | `"12345{tab}"` |
| confirmar | `"12345{enter}"` |
| dois campos | `"01/01/2026{tab}31/01/2026"` |
| pular | `"{tab*3}"` |
| pausa | `"12345{tab}{wait 1}"` |

Macros: `{enter}` `{tab}` `{esc}` `{del}` `{backspace}` setas `{f1}` a `{f12}` `{ctrl}a` `{ctrl+shift+s}` `{tab*3}` `{wait 1.5}` `{{` `}}`.

Citrix/RDP que não cola: `Vizion({"typing_mode": "type"})`.

---

## Tipos de tarefa

```python
tasks = [
    {"type": "focus_window", "title": "Oracle Applications"},
    {"type": "wait_image", "image": "tela.png", "timeout": 30},
    {"text": "Cliente", "sendtext": "12345{enter}", "required": True},
    {"type": "wait_image", "image": "ampulheta.png", "gone": True, "timeout": 60},
    {"image": "popup.png", "optional": True, "sendtext": "{enter}"},
]
```

Tipos: imagem, texto, `relative_image`, `click`, `type_text`, `keyboard_command`, `wait_image` / `wait_text`, `extract_text`, `wait`, `focus_window`, `scroll`.

Chaves comuns: `mouse_button`, `delay`, `sendtext`, `backtrack`, `max_attempts`, `wait_until_found`, `wait_until_disappears`, `wait_timeout`, `optional`, `required`, `show_overlay`.

---

## Configuração

```python
vz = Vizion({
    "tesseract_lang": "eng",
    "image_folders": ["./imagens"],
    "use_virtual_mouse": False,
    "show_overlay": False,
})
vz.config.set("show_overlay", True)
vz = Vizion("pyvizion.json")
```

| Chave | Padrão | Uso |
| ----- | ------ | --- |
| `confidence_threshold` | `75.0` | limiar OCR (0–100) |
| `default_confidence` | `0.9` | imagem |
| `tesseract_lang` | `eng` | `"por"`, `"por+eng"` |
| `tesseract_path` / `tessdata_path` | auto | executável e tessdata |
| `timeout` (`wait_timeout`) | `30` | espera padrão |
| `use_virtual_mouse` | `False` | clique sem mover o cursor (Windows) |
| `typing_mode` | `"paste"` | `"type"` no Citrix |
| `image_folders` | `[]` | onde achar PNG relativo |
| `show_overlay` | `False` | retângulo de depuração |
| `save_failure_screenshots` | `False` | print a cada miss |
| `stop_on_failure` | `False` | para a lista no primeiro erro |
| `failsafe` | `True` | canto superior esquerdo aborta |

Demais chaves (escalas, OCR, overlay, backtrack): veja `src/pyvizion/config.py`.

---

## Linha de comando

```bash
python -m pyvizion doctor
python -m pyvizion screenshot tela.png
python -m pyvizion position
python -m pyvizion pick
python -m pyvizion ocr 100 200 300 40
```

---

## Prática

1. Passe `region` (ou `window_region`) sempre que souber a área.
2. Recorte PNG pequeno e único: o ícone, não o formulário.
3. Prefira `wait_until_gone` a `delay` fixo.
4. Comece com `focus_window("Título")`.
5. Para parar: mouse no canto superior esquerdo.

---

## Desenvolvimento

```bash
pip install -e .[dev]
pytest
```

O site estático fica em `docs/`. Para ver localmente:

```bash
python -m http.server 8080 --directory docs
```

---

## Licença

MIT. Texto em [LICENSE](LICENSE).

Copyright © 2026 Josias Azevedo da Silva.

Os métodos públicos acompanham o [bot-vision-suite](https://github.com/matheuszwilk/bot-vision-suite) (MIT). São pacotes distintos no PyPI.
