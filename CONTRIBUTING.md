# Como contribuir

## O ambiente

```bash
uv sync --extra dev --extra onnx --extra ocr
```

Isso instala o pacote em modo editável e traz `pytest`, `ruff` e `mypy`. Requer Python 3.10 a 3.13 (a CI prova as duas pontas).
Os dois últimos extras são opcionais: sem `onnx` os testes da S-30 pulam e sem `ocr` pulam os
de contrato de motor da S-42 (`InstalledEngineContractTests`). O `qt` **deixou de ser extra** no
corte do Tk (S-506): o PyQt6 é dependência de base, porque a janela é ele. Atenção: `uv sync` com
um subconjunto de extras **desinstala** o que os outros trouxeram, então repita os três.

**Se você mover o diretório do projeto, rode `uv sync` de novo.** O ponteiro da instalação
editável guarda o caminho absoluto, e um caminho morto quebra os `cvoff-*` e o
`app_pyqt.py`. A suíte sobrevive — `pythonpath = ["src"]` no `pyproject.toml` —, e é
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
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"   # sem tela: o roteiro roda no terminal

from pathlib import Path
from PyQt6.QtWidgets import QApplication
from chess_diagram_ocr.qt.janela import JanelaPrincipal

app = QApplication([])
janela = JanelaPrincipal()
janela.abrir_pdf(Path("PDF/seu_livro.pdf"))
janela.pdf.ir_para_pagina(20)
app.processEvents()

janela.marcar_diagramas()
app.processEvents()
print(janela.rodape.mensagem())
```

Sob `offscreen` o Qt monta a janela inteira sem abrir nada, e `processEvents()` é o que faz a
fila de sinais girar -- o `root.after` do outro lado. Uma tarefa em thread (`ler_pagina`,
varredura, treino) precisa de um giro a mais depois de ela terminar.

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

## Republicar um relatório de campo

O relatório declara **com que código e com que modelo** foi medido (S-218/S-219), e
`test_todo_relatorio_corrente_mediu_o_codigo_de_hoje` reprova quando o caminho de medição mudou
desde que ele foi gravado. Mexeu em `atomic_io`, `board_detection`, `decode`, `detection`,
`preprocess`, `service` ou em qualquer um dos 30 que `measured_modules` lista? Os quatro de
`docs/metrics/` venceram, e remedir é a única saída — o relatório antigo não descreve mais o programa.

**Remeça num worktree limpo, no commit que vai carregar os JSON.** A receita acima grava em
`docs/metrics/` do checkout onde se trabalha, e ali quase nunca há commit limpo: o resultado sai
com `dirty: true` e com o digest da árvore como ela estava naquele minuto — inclusive o que outra
pessoa tem sem commitar. Um relatório assim não reproduz, e remedir de novo produz outro igual.

```bash
git worktree add --detach /tmp/medicao <commit-que-vai-carregar-os-json>
mkdir -p /tmp/medicao/models
ln models/*.pt /tmp/medicao/models/            # veja a segunda armadilha
cd /tmp/medicao
python -m chess_diagram_ocr.cli.field \
    --pdf-dir <checkout-principal>/PDF \
    --model models/controle_20260816.pt \
    --json /tmp/relatorios/controle.json       # veja a primeira armadilha
git status --porcelain                          # tem de sair vazio ENTRE as rodadas
```

O `.pt` e o `PDF/` não existem no worktree e vêm por caminho explícito; `data/field_set.jsonl`,
`labels.csv` e `splits.csv` vêm do próprio worktree, que é onde eles estão **como o commit os
tem** — que é o que o relatório deve medir.

**As duas armadilhas, e as duas mordem em silêncio.**

*Gravar o relatório dentro da árvore medida suja a medição seguinte.* Com `--json
docs/metrics/...` do worktree, o primeiro relatório sai `dirty: false` e do segundo em diante o
`git status` deixou de ser vazio por causa do JSON do primeiro. Os três seguintes saem com o
mesmo defeito que se foi consertar, e nada avisa. O `--json` aponta para **fora** da árvore, e
os arquivos são copiados para `docs/metrics/` no fim.

*Caminho absoluto de modelo publica a raiz do disco.* `measurement.model.path` guarda o que se
passou em `--model`, e `--model /home/alguem/projeto/models/x.pt` entra no arquivo versionado.
`test_nenhum_relatorio_publica_a_raiz_do_disco` acusa — ele existe para isso. Por isso o `ln`
acima: os `.pt` entram no worktree como hardlink (`models/**/*.pt` é ignorado, então a árvore
continua limpa) e o `--model` passa a ser relativo, que é o que `config.caminho_para_relatorio`
sabe encurtar. `--pdf-dir` e `--set` podem seguir absolutos: nenhum dos dois entra no relatório.

**Reproduza antes de republicar.** Remeça primeiro os relatórios cujo modelo **não** mudou: eles
têm de sair iguais ao arquivado, número por número. Três dos quatro reproduzindo exato é o
controle de que o conjunto, os parâmetros e a detecção são os mesmos — sem ele não há como saber
se a diferença do quarto é do modelo ou da montagem. E `detected`, `matched` e
`false_positives` não podem se mover entre modelos: detecção não depende de classificador, e um
quarteto em que eles divergem é impossível numa medição sã (foi o achado da S-219).

## Mexer em detecção

`cvoff-eval` e `cvoff-field` medem **leitura**. Nenhum dos dois vê o detector errar: um
recorte que nunca deveria ter existido entra nos dois como mais um diagrama difícil. Foi assim
que o glifo de cavalo do cabeçalho do `Secrets of Chess Training` entrou como diagrama em 71
páginas, deslocou a numeração do PGN em 14 delas, e sobreviveu a 509 testes verdes — é visível
a olho nu e invisível em relatório (`docs/ANALISE_DETECCAO.md`).

Então, antes e depois de tocar em `detection/`, `board_detection.py` ou qualquer limiar delas:

```bash
cvoff-census --csv /tmp/antes.csv                     # ou reaproveite docs/metrics/deteccao_base.csv
# ... a mudança ...
cvoff-census --csv /tmp/depois.csv --baseline /tmp/antes.csv --fail-on-loss
```

O diff casa candidatos pelo **canto do bbox**, não pelo índice: quando um falso positivo sai,
o diagrama que era o #1 vira #0, e casar por índice leria uma remoção como remoção mais
substituição.

A linha que decide é `das quais acima do limiar`. Perder suspeito é o objetivo; perder
candidato do tamanho de um diagrama impresso precisa de justificativa **um por um**, olhando a
página. O censo não sabe o que é diagrama — não existe rótulo humano de detecção no acervo —,
então ele não aprova nada sozinho. Ele diz onde olhar.

## Convenções de código

- **pt-BR na interface, com acento.** Há teste para isso (`tests/test_strings.py`); a lista
  de palavras está em `ui/strings.py`. Identificadores e nomes de teste ficam em inglês.
- **Nada de OCR fora de `src/`.** Se você está escrevendo lógica dentro de `qt/janela.py`,
  ela provavelmente pertence a `service.py`, a um painel de `qt/` ou à camada pura de `ui/`.
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
- Mudança que fecha um item de fase: **o documento da fase daquele item**, com **o que foi
  medido** — inclusive quando o resultado desaconselhou a mudança. Qual documento é, a tabela
  "Onde mora a spec de cada item" do [README](README.md#onde-mora-a-spec-de-cada-item-s-nn)
  responde, e ela é conferida por teste.
- Mudança que move responsabilidade entre módulos: [ARCHITECTURE.md](docs/ARCHITECTURE.md).

> Esta linha já dizia "[ROADMAP.md](docs/ROADMAP.md)", que fecha na Fase 6 (S-36). Foi a causa
> mecânica de duas entregas ficarem três meses sem spec em documento nenhum — S-76 e S-77, ver
> a S-133. Hoje `tests/test_docs.py` falha nomeando o identificador e o commit, então o
> esquecimento deixou de depender de alguém lembrar (S-134).

O ROADMAP registra o que **não** funcionou com o mesmo cuidado do que funcionou. Isso é
deliberado: os pesos de classe da S-27, a calibração da S-28, o TTA da S-29 e as
arquiteturas alternativas foram implementados, medidos e mantidos desligados. Saber que
algo já foi tentado e por que não entrou vale tanto quanto o código que entrou.
