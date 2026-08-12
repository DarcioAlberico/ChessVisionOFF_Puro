# Arquitetura — ChessVisionOFF_Puro

Como uma página de PDF vira uma FEN, e onde cada decisão mora. Para o *porquê* de cada
escolha, [ROADMAP.md](ROADMAP.md); para os números, [BASELINE.md](BASELINE.md) e
[EXPERIMENTS.md](EXPERIMENTS.md).

---

## A regra que organiza tudo

**Nenhuma lógica de reconhecimento vive numa interface.** `app_tkinter.py` e
`app_streamlit.py` são apresentação: leem widgets, chamam o serviço, desenham o resultado.
Isso não é gosto arquitetural — é consequência de um defeito medido. Até a Fase 6 as duas
telas implementavam o pipeline de forma independente, e cinco entregas das Fases 2 e 3
nunca chegaram ao Streamlit sem que nada acusasse.

O corolário prático: **o que dá para testar não fica na janela.**

---

## O caminho de uma página

```
PDF ──► pdf_io.render_pdf_page ──► imagem RGB da página
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼                                       ▼
        detection/embedded.py                      board_detection.py
        (imagem embutida do PDF)                   (contorno, OpenCV)
                    └───────────────────┬───────────────────┘
                                        ▼
                            detection/hybrid.py  (S-12)
                    bbox localiza · contorno alinha · um recorte por candidato
                                        │
                                        ▼
                          inference.predict_with_orientation  (S-13)
                     lê a 0° e a 180°, escolhe por legalidade → confiança → peões
                                        │
                                        ▼
                            inference.board_probabilities
                        64 casas → matriz (64, 13) de probabilidades
                                        │
                                        ▼
                                 decode.py  (S-11)
                  argmax sujeito às regras: 1 rei de cada cor, ≤8 peões,
                  nada na 1ª/8ª fila. Reescreve no máximo 6 casas.
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼                                       ▼
            pdf_text.py  (S-16)                    semantics.py  (S-17)
       legenda ao lado do diagrama            "quem não joga não pode estar
       → lado a jogar, nº, jogadores           em xeque" → lado a jogar
                    └───────────────────┬───────────────────┘
                                        ▼
                            fen_utils.check_position  (S-05)
                     legal · ilegal por turno · ilegal fatal (três estados)
                                        │
                                        ▼
                     service.RecognizedDiagram  ── o que a UI recebe
```

Da FEN em diante o caminho se divide em três, e todos partem do mesmo `RecognizedDiagram`:

| destino | módulo | gate |
|---|---|---|
| PGN do livro | `pdf_to_pgn.py` | S-15: ilegal ou confiança baixa vai para `.review.pgn` |
| dataset de treino | `service.save_sample` → `dataset.py` | posição fatalmente ilegal é recusada |
| fila de revisão | `review_queue.py` | S-22: ordena por valor de informação |

---

## Os módulos, por responsabilidade

### O pipeline (`src/chess_diagram_ocr/`)

| módulo | responsabilidade |
|---|---|
| `service.py` | **A fachada.** `OcrService` orquestra o pipeline; `RecognizedDiagram` é o que sai. Modelo carregado uma vez, sob lock. |
| `board_detection.py` | Acha tabuleiros por contorno e faz o warp de perspectiva. |
| `detection/` | Detector híbrido: imagem embutida do PDF localiza, contorno alinha. O recorte é aparado pela grade, ou pela **moldura impressa** quando não há grade desenhada (S-64). |
| `inference.py` | Carrega o modelo e prevê as 64 casas, nas duas orientações. Quem **decide** é o `orientation.py`. |
| `orientation.py` | A cascata de regras que escolhe a orientação (S-48). A ordem é a decisão, e `explain()` diz o que cada regra falou. |
| `decode.py` | Decodificação sujeita às regras do xadrez. |
| `semantics.py` | Lado a jogar e direitos de roque, deduzidos da posição. |
| `pdf_io.py` | Abrir, contar e renderizar página. `OpenPdf` é o empréstimo da S-61: uma varredura abre o documento **uma vez** e o passa adiante, em vez de três aberturas por página. |
| `pdf_text.py` | Legenda e metadados da camada de texto do PDF. |
| `ocr.py` | Motor de OCR opcional e plugável (S-42). Sem o extra, `build_recognizer` devolve `None`. |
| `ocr_caption.py` | Lê **a faixa em volta do diagrama**, não a página, e devolve a mesma `TextLine` da S-16 (S-43). A faixa de cabeçalho tem altura própria (`SCOPE_BAND`), porque a de descarte cortava a linha ao meio. |
| `side_survey.py` | Conta de onde veio o lado a jogar, livro a livro — o critério de saída da Fase 8, medido por `cvoff-sides`. |
| `fen_utils.py` | Sintaxe **e** legalidade — duas coisas distintas, ver o README. |
| `pdf_to_pgn.py` | Varredura de um livro, gate de exportação, checkpoint parcial. |
| `batch.py` | Varredura da biblioteca inteira, com relatório consolidado. |
| `review_queue.py` | Fila ordenada por valor de informação. |
| `labels.py` | **A porta única do `labels.csv`** (S-51): esquema, leitura, escrita atômica, transação. |
| `provenance.py` | Recupera de que livro e página veio cada amostra órfã, por hash perceptual (S-52). |
| `dataset.py` · `splits.py` · `audit.py` | Dados de treino: leitura, partição estável, auditoria. |
| `training.py` · `model.py` · `checkpoint.py` | Treino, arquitetura e persistência. `Trainer` roda em etapas nomeadas e `BestEpochPolicy` decide sozinha quando gravar (S-47). `ArchConfig` ganhou os canais de coordenada e a cabeça por tabuleiro (S-62); os dois mudam a `arch_version`, e um checkpoint de um não carrega no outro. |
| `calibration.py` · `evaluation.py` · `experiments.py` | Medição. |
| `engine.py` | Motor UCI opcional (Stockfish). |
| `net_correction.py` · `settings.py` | Segunda opinião externa, e a configuração que a autoriza. |
| `atomic_io.py` | Escrita que não deixa arquivo pela metade. |

### A interface (`src/chess_diagram_ocr/ui/`)

| módulo | responsabilidade |
|---|---|
| `pdf_panel.py` | Exibir o PDF, navegar, zoom, seleção de área, modo leitura, e os diagramas marcados sobre a página (S-68). |
| `page_overlay.py` | Onde estão os diagramas da página, o que um clique neles acerta e o que ele significa (S-68). **Sem Tk.** |
| `result_panel.py` | O editor **desenhado**: widgets, diálogos e gravação. O estado é do `editor_model`. |
| `editor_model.py` | As três listas paralelas, o índice e o vínculo — e o que `Ctrl+S` significa (S-49). **Sem Tk.** |
| `study_panel.py` | Tabuleiro de estudo, árvore de variantes, PGN, motor. |
| `review_panel.py` · `dataset_panel.py` | As abas de revisão e de dataset. |
| `board_model.py` | O que está no tabuleiro e o que um clique significa (S-50). **Sem Tk.** |
| `board_render.py` | Pinta um `BoardModel` no canvas. `draw_dirty` redesenha só as casas que mudaram. |
| `board_widget.py` · `board_edit.py` | A casca Tk (canvas, eventos, arraste, tooltip) e a edição sem regra de lance. |
| `net_button.py` | O botão "Corrigir Net": consentimento, thread e ciclo de vida do envio (S-32). |
| `theme.py` | O tema `ttkbootstrap`, com degradação para o `ttk` puro (S-53). |
| `legality.py` | Legalidade em pt-BR, com as casas culpadas. |
| `page_results.py` | Cache do reconhecimento por página. |
| `export_controller.py` · `training_dialog.py` | As duas operações longas e seus diálogos. |
| `state.py` · `strings.py` · `shortcuts.py` · `tooltip.py` | Estado, vocabulário, atalhos, dicas. |
| `busy.py` | O que está rodando e o que se perde ao fechar a janela (S-60). Sem Tk. |

`app_tkinter.py` monta esses painéis e liga um ao outro. Nada mais.

**Os cinco módulos sem Tk não são organização.** `editor_model`, `board_model`, `busy`,
`board_edit` e `page_overlay` são onde mora a regra que, dentro de um widget, só se testava dirigindo a
janela — e um teste que precisa de janela é um teste que quase não se escreve. `tests/` tem
uma varredura de importação em cada um: se `tkinter` voltar a entrar ali, a suíte reprova.

---

## A escolha de framework, e o gatilho que a muda

A interface é Tkinter + `ttk` + `ttkbootstrap`, ~2.900 linhas em 18 módulos, com roteiro
headless. Depois da Fase 6 ela não tem lógica de negócio dentro, e depois da S-49/S-50 nem
estado. **A recomendação é ficar no Tk**, e a decisão de sair está amarrada a evento
observável e não a gosto (S-53).

Três lugares onde a escolha já cobra, e os três são mensuráveis:

- `DatasetPanel` **pagina** porque, nas palavras do próprio código, *"3.195 linhas de uma vez
  travam o `Treeview` do Tk"*. A paginação custa o que mitiga: filtro e ordenação valem por
  página, não pelo conjunto.
- O tabuleiro redesenhava-se inteiro a cada mudança. A S-50 aliviou (`draw_dirty` toca 2
  casas ao arrastar), não eliminou: mudança de geometria ainda refaz as 64.
- As sobreposições que a Fase 8 vai querer — bbox de texto reconhecido sobre a página, com
  confiança em cor e edição no lugar — são o caso de uso natural de uma cena gráfica, e
  trabalho manual de coordenadas no canvas do Tk.

**Portar para PySide6/Qt custa ~3–4 semanas mais licença LGPL.** Vale quando um destes
disparar, e não antes:

| gatilho | por que este |
|---|---|
| a Fase 8 exigir sobreposição **editável** sobre a página renderizada | é onde o canvas do Tk deixa de ser desconforto e vira trabalho desproporcional |
| o `labels.csv` passar de **10 mil linhas** | a paginação da S-23 deixa de ser mitigação e vira obstáculo ao fluxo |

Hoje o `labels.csv` tem **3.313** linhas — 33% do gatilho. Quando a hora chegar, `Qt` dá
`QTableView` com modelo virtual (30 mil linhas sem paginar), `QGraphicsScene` para tabuleiro
e sobreposições, `QThread` + sinais no lugar de `root.after`, `QPdfView` nativo, DPI correto
por monitor e `QAction` para atalhos.

E o porte é **menor do que parece**, por construção: o pipeline saiu das telas na Fase 6, o
estado saiu dos widgets na S-49 e na S-50, e `board_render.py` é o único arquivo de desenho.
Portar a UI passou a ser portar UI.

`CustomTkinter` foi considerado e recusado: não tem equivalente decente de `Treeview`, então
a aba Dataset continuaria em `ttk` e a tela ficaria com dois visuais.

---

## As fontes de verdade sobre o lado a jogar

É a decisão de projeto mais consequente do produto, porque até a Fase 3 **100% dos
exercícios saíam como "brancas jogam"** e em livro de tática cerca de metade está errada.

| fonte | `[SideToMoveSource]` | quando responde | alcance medido |
|---|---|---|---|
| legenda na camada de texto (S-16) | `text` | há legenda ao lado do diagrama | 41 de 645 diagramas amostrados |
| legenda lida por OCR (S-43) | `ocr` | a camada calou **naquele diagrama** e há motor | 25 de 645 |
| cabeçalho da página, camada de texto (S-43) | `text-page-scope` | a legenda calou e a faixa de margem declara | 9 de 645 |
| cabeçalho da página, por OCR (S-43) | `ocr-page-scope` | idem, sem camada de texto | **45 de 645** — quase todos do `Reinfeld` |
| legalidade (S-17) | `legality` | quem não joga está em xeque | 27 de 645 |
| padrão "brancas" | `default` | nenhuma das anteriores | 498 de 645 (77,2%) |

Os números vêm de `cvoff-sides`, 12 páginas por livro nos 32 livros do acervo, em 2026-08-11.
Sem motor de OCR o `default` fica em **87,8%**; com ele, em **77,2%**. Reproduzir:
`cvoff-sides --ocr rapidocr`.

O PGN grava `[SideToMoveSource]` **sempre**. A maioria do acervo cai no padrão, e um palpite
precisa parecer um palpite — é essa a diferença entre um dado e uma suposição herdada. As
quatro procedências textuais existem separadas pelo mesmo motivo: "está escrito na legenda
deste diagrama, no arquivo" e "um motor leu com 0,62 de confiança num cabeçalho que vale
para a página inteira" não são o mesmo dado. Quando quem decide é o OCR, o header
`[SideToMoveConfidence]` acompanha.

Duas regras de precedência, e as duas foram escolhidas para que ligar o OCR não possa
piorar um livro que já funciona:

- **Por diagrama, e só onde a camada calou.** O motor não roda para um diagrama que já tem
  linha de texto por perto — o que também é a economia que o custo medido na S-61 exige.
- **A legenda vence o cabeçalho.** A declaração de escopo de página só preenche o diagrama
  que ficou sem resposta.

---

## Threads

Quatro operações longas rodam fora da thread da interface, e todas voltam por `root.after`:

| operação | onde | cancelável | empresta o modelo do serviço |
|---|---|---|---|
| OCR de uma página | `app_tkinter._ocr_worker` | não (é rápido) | sim (S-31) |
| exportação de um livro | `ui/export_controller.py` | sim, entre páginas (S-24) | sim (S-57) |
| varredura da fila de revisão | `ui/review_panel.py` | sim, entre páginas | sim (S-57) |
| treino | `ui/training_dialog.py` | sim, entre épocas (S-60) | escreve o `.pt` |

O modelo é compartilhado entre elas e fica **sob lock durante o uso**, não só durante a
carga: o treino reescreve o mesmo `.pt` que uma leitura concorrente estaria lendo (S-31).

Até a S-57 essa frase valia para **uma** das quatro. A exportação e a varredura da fila
chamavam `load_model` por conta própria, fora do lock — e são justamente as duas longas, as
que de fato coexistem com um treino. Hoje as duas recebem `model_session` do `OcrService`; o
único `load_model` que sobrou em `pdf_to_pgn.py` está em `_own_model_session`, o caminho dos
CLIs, onde não há serviço nem treino concorrente.

Fechar a janela consulta `ui/busy.py` antes de destruir: `BusyRegistry` sabe o que está
rodando e **o que se perde**, que não é a mesma coisa em todas — a exportação tem checkpoint
parcial e sobrevive, o treino perde o progresso desde a última época melhor (S-60).

---

## Formatos e persistência

| arquivo | o que guarda | versionado |
|---|---|---|
| `data/labels.csv` | rótulos: imagem, FEN, lado a jogar, origem, split | sim |
| `data/splits.csv` | partição treino/validação/teste, estável sob crescimento | sim |
| `data/samples/` | os PNGs 800×800 dos tabuleiros | não (2,7 GB) |
| `data/settings.json` | preferências do usuário, incluindo o endpoint remoto | não |
| `data/app_tkinter_state.json` | último PDF, página, zoom | não |
| `data/review_queue.json` | a fila de revisão | não |
| `data/provenance_index.jsonl` | dHash de cada diagrama do acervo, para recuperar procedência (S-52) | não (horas para reconstruir, mas derivável dos PDFs) |
| `models/*.pt` | checkpoints, com semente, split e métrica gravados | não |
| `data/splits.csv` | partição, atribuída às amostras novas pelo próprio treino (S-56) | sim |
| `PGN/<livro>.pgn` | as posições aceitas | não |
| `PGN/<livro>.review.pgn` | as rejeitadas e as de baixa confiança, com o motivo | não |
| `PGN/<livro>.partial.jsonl` | checkpoint da exportação, apagado ao concluir | não |

Toda escrita de arquivo de trabalho passa por `atomic_io`: grava num temporário e troca. O
`labels.csv` é 3.313 rótulos de trabalho humano acumulado, e a interface o regrava inteiro a
cada correção. Desde a S-57 o `.pt` também passa por ali — era o maior dos arquivos, o mais
demorado de escrever, e o único cuja escrita acontece numa thread de fundo enquanto outra
pode estar lendo o mesmo caminho.

**O `labels.csv` tem uma porta só: `labels.LabelStore` (S-51).** Antes eram cinco módulos com
pandas, cada um conhecendo o esquema por conta própria — e elas não concordavam: três
caminhos do `audit.py`, todos alcançáveis por `cvoff-audit --fix`, gravavam com `to_csv`
direto no destino, sem escrita atômica e sem a normalização de inteiro da S-58. O `splits.csv`
tinha o mesmo defeito de escrita, e ele carrega uma decisão irreversível na prática.

A regra é verificada por teste (`tests/test_labels.py`), e não por disciplina: a suíte varre a
árvore e falha se `read_csv` ou `to_csv` reaparecerem fora do `labels.py`. Foi essa varredura
que encontrou a **sexta** porta, em `review_queue.rare_classes_from_labels`, que nenhum
levantamento tinha listado.

`LabelStore` usa o `csv` da biblioteca padrão e não pandas. A S-58 existe porque o pandas
infere tipo — `source_page` tem 98,6% de células vazias, a coluna virava `float64` e `20`
voltava `20.0`, e como a gravação relê o arquivo inteiro antes de acrescentar uma linha, uma
amostra nova reescrevia todas as antigas nesse formato. Com `csv.DictReader` não há tipo a
inferir: todas as colunas do esquema são texto. O defeito deixou de ser evitado e passou a não
existir.
