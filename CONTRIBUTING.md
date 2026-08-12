# Como contribuir

## O ambiente

```bash
uv sync --extra dev --extra onnx --extra ocr
```

Isso instala o pacote em modo editável e traz `pytest`, `ruff` e `mypy`. Requer Python 3.10.
Os dois últimos extras são opcionais: sem `onnx` os testes da S-30 pulam, sem `ocr` pulam os
de contrato de motor da S-42 (`InstalledEngineContractTests`). Atenção: `uv sync` com um
subconjunto de extras **desinstala** o que os outros trouxeram, então repita os três.

**Se você mover o diretório do projeto, rode `uv sync` de novo.** O ponteiro da instalação
editável guarda o caminho absoluto, e um caminho morto quebra os `cvoff-*` e o
`app_tkinter.py`. A suíte sobrevive — `pythonpath = ["src"]` no `pyproject.toml` —, e é
`tests/test_environment.py` que avisa que a instalação ficou para trás; sem ele o sintoma
seriam 33 erros de coleta que não dizem o que fazer (S-37).

## As três verificações

São as mesmas que a CI roda, e é razoável rodar as três antes de abrir um PR:

```bash
uv run ruff check .    # lint e ordenação de imports
uv run mypy            # tipos (cobre src/)
uv run pytest          # testes
```

`ruff check --fix .` conserta o que é seguro consertar sozinho.

A suíte roda em um clone limpo: os testes que dependem de `data/samples/` são pulados
quando a pasta está vazia, e os de ONNX quando o extra não está instalado. Se a sua
alteração precisa de dados que não existem no repositório, o teste tem de pular — não
falhar.

## O que este projeto espera de um teste

Testes aqui não existem para atingir cobertura. Eles existem para travar **decisões**, e o
nome do teste é onde a decisão fica escrita:

```python
def test_the_deciding_metric_comes_before_the_flattering_one(self) -> None:
    """`val_board_exact_acc` decide qual época é salva; `val_acc/casa` fica ~0,999 sempre."""
```

Três hábitos que valem mais que o número de testes:

- **Teste o que a medição decidiu, não o que o código faz.** Se a ordem de dois rótulos na
  tela foi escolhida por um motivo, esse motivo merece um teste; o *getter* que devolve o
  rótulo, não.
- **Escreva o motivo no docstring.** Vários testes deste projeto existem porque um número
  contradisse a intuição. Sem o motivo registrado, o próximo a passar por ali desfaz.
- **Quando um comportamento não pôde ser medido, diga isso** em vez de escrever um teste que
  finge medi-lo. Há exemplos no ROADMAP de critérios de aceite declarados como não
  atingidos, e isso é preferível a um número inventado.

## Rodar a interface sem clicar

Muita coisa deste projeto só falha quando a janela é dirigida. Um roteiro headless que
reconhece uma página e navega entre diagramas pega o que a suíte não pega — foi assim que
um `AttributeError` de navegação apareceu depois de 509 testes verdes:

```python
import tkinter as tk
from pathlib import Path
import app_tkinter as app

root = tk.Tk(); root.withdraw()
janela = app.ChessOcrTkApp(root)
janela.load_pdf(Path("PDF/seu_livro.pdf"))
janela.pdf_panel.page_index_var.set(20)

def começar():
    janela.pdf_panel.on_page_spin()
    janela.ocr_all()
    root.after(200, esperar)

def esperar(tentativas=[0]):
    tentativas[0] += 1
    if janela._is_running_ocr and tentativas[0] < 900:
        root.after(200, esperar)
        return
    print(len(janela.result_panel.items), "diagramas")
    janela.result_panel.next_diagram()      # é aqui que os defeitos costumam aparecer
    print(janela.status_var.get())
    root.quit()

root.after(100, começar)
root.mainloop()
```

Use `mainloop()` e não um laço de `update()`: `root.after` de outra thread falha com
"main thread is not in main loop" fora do loop de eventos de verdade, e o erro parece um
defeito do código quando é do roteiro.

Para a demonstração Streamlit (`examples/streamlit_demo.py`), `streamlit.testing.v1.AppTest`
roda o script inteiro sem navegador. Ela é exemplo e não interface (S-54): um defeito ali
não bloqueia entrega, mas ela importa o `OcrService` e por isso quebra quando a fachada
muda — o que é exatamente o alarme que se quer de um exemplo.

## Adicionar amostras ao dataset

O caminho normal é pela interface: reconhecer, corrigir no tabuleiro, `Ctrl+S`. Quem quiser
fazer isso por código usa `OcrService.save_sample`, que anexa a procedência da S-19 — de que
PDF, que página, que diagrama e por qual fonte de detecção ele foi achado.

Depois de acrescentar amostras:

```bash
cvoff-audit            # legalidade, duplicatas, órfãos, distribuição de classes
cvoff-train --fresh    # o split é estável: amostra nova não muda o que já era 'test'
cvoff-eval --split test
cvoff-field            # e o que de fato importa: a taxa de exportação em página real
```

**Nunca ajuste nada olhando para o split `test`.** Ele existe para responder uma pergunta
uma vez, e um número olhado repetidamente deixa de ser honesto. Compare no `val`.

**E não pare no `cvoff-eval`.** O split de teste são recortes que um humano já aprovou; o
produto lê páginas de PDF. A Fase 7 mediu um fator de 18× entre os dois, e desde então
`cvoff-field` é a métrica primária. Quatro variantes de modelo treinadas em 2026-08-11 deram
taxas de exportação idênticas com acurácias de validação diferentes — é o tipo de coisa que só
o conjunto de campo mostra.

## Comparar dois modelos honestamente

Um checkpoint só é comparável a outro treinado sobre o **mesmo dataset, mesma semente, mesmo
regime de aumento e mesmo número de épocas**. Comparar contra `models/piece_classifier.pt`
compara também os meses de amostras que entraram desde que ele foi treinado.

```bash
cvoff-train --fresh --seed 42 --model models/controle.pt              # o controle
cvoff-train --fresh --seed 42 --coords --model models/variante.pt     # a variante
cvoff-field --model models/controle.pt --json docs/metrics/controle.json
cvoff-field --model models/variante.pt --json docs/metrics/variante.json
```

O relatório do `cvoff-field` traz as três medidas que um item de modelo precisa: taxa de
exportação, casas que o `decode.py` teve de reparar, e custo por diagrama.

## Convenções de código

- **pt-BR na interface, com acento.** Há teste para isso (`tests/test_strings.py`); a lista
  de palavras está em `ui/strings.py`. Identificadores e nomes de teste ficam em inglês.
- **Nada de OCR fora de `src/`.** Se você está escrevendo lógica dentro de
  `app_tkinter.py`, ela provavelmente pertence a `service.py` ou a um painel de `ui/`.
- **`logging`, nunca `print`,** exceto na saída de um comando `cvoff-*`, que é a interface
  daquele programa.
- **Escrita de arquivo de trabalho passa por `atomic_io`.** O `labels.csv` é trabalho
  humano acumulado, e a interface o regrava inteiro a cada correção.
- **O `labels.csv` só é tocado pelo `labels.LabelStore` (S-51).** Nada de `pd.read_csv` ou
  `to_csv` sobre ele em outro módulo — há teste que varre a árvore e falha. Precisa de várias
  alterações? `with store.transaction():` grava uma vez no fim. Se o esquema precisar de uma
  coluna, ela entra em `LABEL_COLUMNS`, num lugar só.
- **Comentário explica o *porquê*.** O *o quê* está no código, e um comentário que o repete
  envelhece sozinho.

## Documentação

- Mudança que altera um número: [BASELINE.md](docs/BASELINE.md) ou
  [EXPERIMENTS.md](docs/EXPERIMENTS.md).
- Mudança que fecha um item de fase: [ROADMAP.md](docs/ROADMAP.md), com **o que foi medido**
  — inclusive quando o resultado desaconselhou a mudança.
- Mudança que move responsabilidade entre módulos: [ARCHITECTURE.md](docs/ARCHITECTURE.md).

O ROADMAP registra o que **não** funcionou com o mesmo cuidado do que funcionou. Isso é
deliberado: os pesos de classe da S-27, a calibração da S-28, o TTA da S-29 e as
arquiteturas alternativas foram implementados, medidos e mantidos desligados. Saber que
algo já foi tentado e por que não entrou vale tanto quanto o código que entrou.
