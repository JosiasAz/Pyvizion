![pyvizion](https://files.catbox.moe/skh0jr.png)

**Biblioteca Python para automação de interface por imagem e texto**

![PyPI v1.0.9](https://img.shields.io/badge/PyPI-v1.0.9-146B43)![Python](https://img.shields.io/badge/python-3.9%2B-0B3D2C)![MIT](https://img.shields.io/badge/licença-MIT-1F7A4D)

[PyPI](https://pypi.org/project/pyvizion/) | [Começar](#começar) | [Como funciona](#como-funciona)

---

O **pyvizion** é uma biblioteca Python: localiza um botão ou um texto na tela, clica e digita. Se o passo falhar, o backtrack refaz a ação anterior e tenta de novo.

Serve para aplicativos desktop sem API: ERP, Oracle Forms, Delphi, Citrix. Só Windows. Linux e macOS têm limitação: sem clique virtual, sem foco de janela e sem o mesmo suporte de tela.

```python
from pyvizion import Vizion

bot = Vizion()
bot.click_image("menu.png", backtrack=True)
bot.click_text("Relatórios", backtrack=True)
bot.click_text("Confirmar", sendtext="{enter}")
```

A versão publicada é a **1.0.9**. As versões 0.3.x no PyPI são outra API.

---



## Começar

```bash
pip install pyvizion
python -m pyvizion doctor
```

**Tesseract** é necessário só para texto/OCR (`click_text`, `find_text`, `read_text`, …).  
`click_image`, `find_image`, teclado e janelas funcionam **sem** Tesseract — o `Vizion()` sobe normalmente.


| Sistema                  | Instalação do Tesseract (se for usar OCR)                                                         |
| ------------------------ | ------------------------------------------------------------------------------------------------- |
| Windows (suportado)      | [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki) em `C:\Program Files\Tesseract-OCR\` |
| Linux / macOS (limitado) | `tesseract-ocr` / `brew install tesseract`. Sem clique virtual e sem foco de janela.              |


Idioma padrão do OCR: `eng`. Tela em português: `Vizion({"tesseract_lang": "por"})` e o pacote `por`.

---



## Como funciona

Você chama `click_image("ok.png")` ou `click_text("Salvar")`. A biblioteca tira um print, procura o alvo e clica no meio dele.

1. **Tira o print:** `mss` em memória (multi-monitor).
2. **Acha a imagem:** recorte **só o botão/ícone** (PNG pequeno e único), passe o caminho. Multi-escala tolera zoom 125%/150%.
3. **Acha o texto:** Tesseract. **Sempre passe** `region` — OCR em **tela cheia** é lento e frágil.
4. **Clica e digita:** no centro do alvo. `use_virtual_mouse` no Windows não mexe o cursor.
5. **Se falhar:** com `backtrack=True`, refaz o passo anterior. Também espera aparecer ou sumir.

Se o alvo não estiver na tela, devolve `False` ou `None`. Vale `if not bot.click_text("OK")`.  
Erro de ambiente: `TesseractNotFoundError` **só** ao usar OCR; `ImageFileError` se o PNG não existir.

### Diferenciais

|                     | pyvizion |
| ------------------- | -------- |
| Print da tela       | `mss` em memória, multi-monitor |
| Busca de imagem     | Multi-escala (tolera zoom 125% / 150%) |
| Busca de texto      | OCR com `region` (bem mais rápido que tela cheia) |
| Esperas             | `wait_until_found` / `wait_until_disappears` |
| Zoom / 2 monitores  | Clique alinhado aos pixels reais |
| Alvo sumiu          | `False` / `None` — sem exception |
| Extras              | janelas, `click_any`, `doctor`, mouse virtual, CLI |

Quem quiser medir tempos no próprio PC (opcional): `python scripts/bench_pipeline.py`.

---



## Uso



### Backtrack e esperas

```python
bot = Vizion()
bot.click_image("menu.png", backtrack=True)
bot.click_text("Relatórios", backtrack=True)
bot.click_image("salvar.png", wait_until_found=True, wait_timeout=15)
bot.find_image("ampulheta.png", wait_until_disappears=True, wait_timeout=60)
bot.click_image("ok.png", wait_until_disappears=True, wait_timeout=10)
```

`wait_until_disappears` no `find_*` devolve a caixa se o alvo sumiu, `None` se ainda estiver visível. No `click_*`, o clique **já valeu**: devolve `True` mesmo se o alvo continuar na tela.

### Sessão

```python
bot.start_task_session()
bot.click_image("button1.png", backtrack=True)
bot.click_text("Clientes", backtrack=True)
ok, total = bot.end_task_session()
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

Para automações novas, use o **núcleo** (`pyvizion.CORE_API`). O restante é avançado / legado.

### Núcleo (comece por aqui)


| Método                             | Resultado      | Precisa Tesseract?        |
| ---------------------------------- | -------------- | ------------------------- |
| `click_image` / `find_image`       | `bool` / caixa | Não                       |
| `click_text` / `find_text`         | `bool` / caixa | Sim                       |
| `type_text`                        | —              | Não                       |
| `wait_for_image` / `wait_for_text` | caixa / texto  | texto: sim                |
| `focus_window`                     | `bool`         | Não                       |
| `execute_tasks`                    | resultados     | só se a tarefa usar texto |

### Demais métodos

`click_relative_image`, `find_relative_image`, `click_at`, `click_coordinates`, `keyboard_command`, `extract_text_from_region`, `get_last_extracted_text`, `execute_with_backtrack_between_tasks`, `start_task_session` / `end_task_session`, overlay, `wait_until_gone`, `image_exists`, `text_exists`, `find_all_images`, `click_any`, `find_any`, `read_text`, `wait_window`, `window_region`, `list_windows`, `press`, `hotkey`, `scroll`, `drag`, `screenshot`, `click_image_near_text`.

Também como funções: `from pyvizion import click_image, find_text, execute_tasks`.  
Aliases `*_standalone` existem, mas emitem `DeprecationWarning`.

**Parâmetros que importam**

- `region=(x, y, largura, altura)`: **obrigatório na prática** para OCR e recomendado para imagem. `bot.window_region("Título")` ajuda.
- `specific=False`: tenta a região e depois a tela, em várias escalas.
- `mouse_button`: `"left"`, `"right"`, `"double"`, `"move_to"`.
- `filter_type`: `"letters"`, `"numbers"`, `"both"`. `occurrence=2` é a segunda na ordem de leitura.
- `wait_timeout`: segundos da espera (padrão da config: **30**).

`click_*` / `find_*` **não levantam** se o alvo sumiu. Ambiente quebrado: `TesseractNotFoundError` ao usar OCR sem Tesseract; `ImageFileError` se o PNG não existe.

---



## Campos (`sendtext`)

Texto digitado logo após o clique. `{chave}` é tecla.

```python
bot.click_text("Usuário", sendtext="admin{tab}senha123{enter}")
```


| Quero                    | `sendtext`                    |
| ------------------------ | ----------------------------- |
| campo vazio              | `"12345"`                     |
| substituir o que está lá | `"{ctrl}a{del}12345"`         |
| ir ao próximo            | `"12345{tab}"`                |
| confirmar                | `"12345{enter}"`              |
| dois campos              | `"01/01/2026{tab}31/01/2026"` |
| pular                    | `"{tab*3}"`                   |
| pausa                    | `"12345{tab}{wait 1}"`        |


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
bot = Vizion({
    "tesseract_lang": "eng",
    "image_folders": ["./imagens"],
    "use_virtual_mouse": False,
    "show_overlay": False,
})
bot.config.set("show_overlay", True)
bot = Vizion("pyvizion.json")
```


| Chave                              | Padrão    | Uso                                 |
| ---------------------------------- | --------- | ----------------------------------- |
| `confidence_threshold`             | `75.0`    | limiar OCR (0–100)                  |
| `default_confidence`               | `0.9`     | imagem                              |
| `tesseract_lang`                   | `eng`     | `"por"`, `"por+eng"`                |
| `tesseract_path` / `tessdata_path` | auto      | executável e tessdata               |
| `timeout` (`wait_timeout`)         | `30`      | espera padrão                       |
| `use_virtual_mouse`                | `False`   | clique sem mover o cursor (Windows) |
| `typing_mode`                      | `"paste"` | `"type"` no Citrix                  |
| `image_folders`                    | `[]`      | onde achar PNG relativo             |
| `show_overlay`                     | `False`   | retângulo de depuração              |
| `save_failure_screenshots`         | `False`   | print a cada miss                   |
| `stop_on_failure`                  | `False`   | para a lista no primeiro erro       |
| `failsafe`                         | `True`    | canto superior esquerdo aborta      |


Demais chaves (escalas, OCR, overlay, backtrack): veja `src/pyvizion/config.py`.

---



## Linha de comando (ferramenta oficial)

O auxiliar oficial do pacote é o **CLI** (não há app `.exe` separado):

```bash
pyvizion                  # help dos comandos + doctor
pyvizion pick             # marca região + gera PNG (imagem1.png, …) e snippet
pyvizion pick --terminal  # fluxo antigo (2× Enter)
pyvizion position         # XY + RGB ao vivo
pyvizion ocr              # OCR de uma área
pyvizion print            # screenshot (tela ou área)
pyvizion windows
pyvizion doctor
```

Use `pick` para obter `region` e PNGs bons antes de escrever o script.

---



## Prática

1. **Region quase sempre:** OCR sem `region` é lento e erra mais; imagem também ganha.
2. **PNG pequeno e único:** recorte o ícone/botão, não o formulário inteiro (`pyvizion pick`).
3. Prefira `wait_until_gone` / `wait_until_found` a `delay` fixo.
4. Comece com `focus_window("Título")` (ou `window_region`).
5. Para parar: mouse no canto superior esquerdo (`failsafe`).

OCR depende de fonte, tema e escala — trate `region` + PNG de qualidade como regra, não como otimização.

---



## Desenvolvimento

```bash
pip install -e .[dev]
pytest
# opcional — só para medir desempenho na sua máquina:
python scripts/bench_pipeline.py
```

O site estático fica em `docs/`. Para ver localmente:

```bash
python -m http.server 8765 --directory docs
```

Abra http://127.0.0.1:8765/ (a porta 8080 costuma conflitar com outros apps).

---



## Licença

MIT. Texto em [LICENSE](LICENSE).

Copyright © 2026 Josias Azevedo da Silva.

Os métodos públicos acompanham o [bot-vision-suite](https://github.com/matheuszwilk/bot-vision-suite) (MIT). São pacotes distintos no PyPI.