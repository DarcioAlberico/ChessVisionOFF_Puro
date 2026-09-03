# Arquitetura — ChessVisionOFF_Puro

Como uma página de PDF vira uma FEN, e onde cada decisão mora. Para o *porquê* de cada
escolha, [ROADMAP.md](ROADMAP.md); para os números, [BASELINE.md](BASELINE.md) e
[EXPERIMENTS.md](EXPERIMENTS.md).

---

## A regra que organiza tudo

**Nenhuma lógica de reconhecimento vive numa interface.** `app_pyqt.py` é apresentação: lê
widgets, chama o serviço, desenha o resultado. Isso não é gosto arquitetural — é consequência
de um defeito medido. Até a Fase 6 havia **duas** telas, e cada uma implementava o pipeline de
forma independente: cinco entregas das Fases 2 e 3 nunca chegaram ao Streamlit sem que nada
acusasse.

A segunda tela saiu na S-54 e virou exemplo em `examples/`; na S-137 o `streamlit` deixou de
ser dependência obrigatória. **A regra sobreviveu à tela que a motivou**, e é o que permite
testar o pipeline sem abrir janela nenhuma.

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
| `detection_census.py` | Conta o que o **detector aceita**, livro a livro, e faz o diff contra a corrida anterior (`cvoff-census`, S-82). Sem modelo e sem rótulo humano: é distribuição, não acurácia. Existe porque `cvoff-eval` e `cvoff-field` medem leitura e são cegos a um recorte que nunca deveria ter existido. |
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

### O texto da página (`src/chess_diagram_ocr/text/`)

**Cinquenta módulos, e este documento não os citava** (S-410). O pacote nasceu na Fase 25 e cresceu
por sete fases; descrever a arquitetura deste projeto sem ele é descrever um terço do código como
se não existisse — e é o mesmo modo de falha que a S-135 mediu nos números: o documento envelhece
onde ninguém o lê contra o disco.

**A fronteira que organiza o pacote é a mesma do resto**: quem lê pixel não sabe o que é uma
palavra, e quem monta parágrafo não sabe o que é um pixel.

| módulo | responsabilidade |
|---|---|
| `leitor.py` | **A fachada.** `ler_pagina` faz a página inteira: linhas, colunas, blocos e a montagem. É quem chama todo o resto, e o único que a interface e os CLIs importam. |
| `boxes.py` · `linhas.py` · `colunas.py` | Da imagem para a geometria: caixas de caractere, a linha que as reúne e a coluna que as linhas formam. |
| `modelo.py` · `classes.py` · `recognizer.py` | O classificador de caractere: os pesos pinados ao `char_meta.json`, as 314 classes e o leitor de faixa. |
| `leitura_de_linha.py` · `colados.py` · `empilhados.py` | Ler a linha em vez do caractere (S-188), separar glifo colado (S-186) e desempilhar o que a binarização juntou. |
| `dicionario.py` · `lexico.py` | O léxico que **desempata** entre os candidatos do modelo, e nunca aproxima da palavra mais parecida (S-209). |
| `caixa_alta.py` · `italico.py` · `negrito.py` · `numero.py` · `notacao.py` | As correções que dependem do que a letra **é**: altura, pendor, peso da fonte, dígito e lance. |
| `paragrafos.py` · `grade.py` · `tabela.py` · `vertical.py` | O que a página tem além de prosa: parágrafo, grade de exercício, tabela e texto girado. |
| `camada.py` · `pdf_pesquisavel.py` | A camada de texto do próprio PDF — como referência (S-194) e como saída invisível sobre a página (S-210). |
| `documento.py` · `exportacao.py` · `rico.py` | O documento do editor: o `.cvtxt`, o HTML e o texto com formato. |
| `busca.py` · `paleta.py` · `semelhanca.py` | Achar no texto, colorir por confiança e "aplicar a todos os semelhantes" (S-213). |
| `treino.py` · `dataset.py` · `coleta.py` · `dedupe.py` · `conflitos.py` · `procedencia.py` | A base de caractere: coletar, inventariar, treinar, e o que fazer com a mesma imagem sob dois rótulos (S-202). |
| `custo.py` · `transcricao.py` · `calibracao.py` | Quanto o texto custa por página (S-215), a transcrição humana de referência (S-183) e a calibração do classificador. |

Os outros doze são operações de imagem e utilidades da mesma cadeia: `binarizacao.py`,
`trama.py`, `negativo.py`, `marca_fina.py`, `aumento.py`, `duas_linhas.py`, `correcao.py`,
`lado.py`, `pagina.py`, `rascunho.py`, `fila.py` e `arquivo.py`.

### A interface (`src/chess_diagram_ocr/ui/`)

| módulo | responsabilidade |
|---|---|
| `pdf_panel.py` | Exibir o PDF, navegar, zoom, seleção de área, modo leitura, e os diagramas marcados sobre a página (S-68). |
| `page_overlay.py` | Onde estão os diagramas da página, o que um clique neles acerta e o que ele significa (S-68), e quais o usuário tirou da tela (S-177). **Sem Tk.** |
| `viewport.py` | O que a roda faz, para onde o zoom puxa e quanto cabe na largura (S-70). **Sem Tk.** |
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

`qt/janela.py` monta esses painéis e liga um ao outro. Nada mais.

**Os seis módulos sem Tk não são organização.** `editor_model`, `board_model`, `busy`,
`board_edit`, `page_overlay` e `viewport` são onde mora a regra que, dentro de um widget, só se testava dirigindo a
janela — e um teste que precisa de janela é um teste que quase não se escreve. `tests/` tem
uma varredura de importação em cada um: se um toolkit voltar a entrar ali, a suíte reprova.

---

## A escolha de framework, e o gatilho que a muda

A interface é Tkinter + `ttk` + `ttkbootstrap`, ~2.900 linhas em 18 módulos, com roteiro
headless. Depois da Fase 6 ela não tem lógica de negócio dentro, e depois da S-49/S-50 nem
estado. **A recomendação é ficar no Tk**, e a decisão de sair está amarrada a evento
observável e não a gosto (S-53).

Três lugares onde a escolha já cobra, e os três são mensuráveis:

- `DatasetPanel` **pagina** por uma premissa que a S-118 mediu e derrubou: *"3.195 linhas de
  uma vez travam o `Treeview` do Tk"*. Medido com `Treeview` real e as mesmas 8 colunas,
  **inserir 3.936 linhas custa 53 ms**; o que custava eram os 689 ms do `load_rows` que vinha
  antes (S-116). A paginação cobra o que não mitiga: filtro e ordenação valem por página, e
  até a S-118 ela também perdia o lugar de quem corrigia rótulo a rótulo. Ela fica — remover
  é uma segunda decisão, e ela precisa da medição refeita quando o `labels.csv` dobrar.
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

Hoje o `labels.csv` tem **5.321** linhas — 53% do gatilho (medido em 2026-09-01; o número é
conferido por `tests/test_docs.py`, S-135). Quando a hora chegar, `Qt` dá
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
| legenda lida por motor de terceiros (S-43) | `ocr` | a camada calou **naquele diagrama** e há motor | 25 de 645 |
| legenda lida pelo classificador de casa (S-207) | `glifo` | idem, com `--ocr-engine glifo` | 3 de 146 assumidos, em 10 livros (2026-08-26) |
| cabeçalho da página, camada de texto (S-43) | `text-page-scope` | a legenda calou e a faixa de margem declara | 9 de 645 |
| cabeçalho da página, por motor de terceiros (S-43) | `ocr-page-scope` | idem, sem camada de texto | **45 de 645** — quase todos do `Reinfeld` |
| cabeçalho da página, pelo classificador de casa (S-207) | `glifo-page-scope` | idem, com `--ocr-engine glifo` | 0 na amostra de 2026-08-26 |
| legalidade (S-17) | `legality` | quem não joga está em xeque | 27 de 645 |
| padrão "brancas" | `default` | nenhuma das anteriores | 498 de 645 (77,2%) |

Os números vêm de `cvoff-sides`, 12 páginas por livro nos 32 livros do acervo, em 2026-08-11.
Sem motor de OCR o `default` fica em **87,8%**; com ele, em **77,2%**. Reproduzir:
`cvoff-sides --ocr rapidocr`.

As duas linhas do `glifo` são de outra medição, e a coluna diz qual: `cvoff-texto-lado`, 10 livros
e 8 páginas com diagrama de cada, em 2026-08-26 (`docs/metrics/texto_lado.json`). **Ele acrescenta
2,1% dos diagramas que saíam `default`**, e o motivo de não ser mais está na tabela e não no motor:
os livros que declaram o lado por diagrama já têm camada de texto, e ali o motor nem é chamado.

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

**Doze** threads rodam fora da thread da interface, e todas voltam por **sinal** -- que é o
`root.after` do lado que saiu: um `QThread` que tocasse widget direto derruba o processo sem
exceção. Nove são operações longas e estão no `BusyRegistry`; as outras duas são declaradas em
`tests/test_busy.py::SEM_REGISTRO`, com o motivo de cada uma (S-112).

A contagem é conferida por `tests/test_docs.py` contra `qt/*.py` (S-410/S-506). **Ela conta duas
formas**: `threading.Thread(`, que veio do Tk, e `Tarefa(`, o `QThread` de `qt/trabalho.py`.
Contar só a primeira deixaria de fora a leitura da página, que é o laço interno do programa.

| operação | onde | cancelável | perde trabalho ao fechar | empresta o modelo do serviço |
|---|---|---|---|---|
| marcar e reconhecer a página | `qt/janela.py::_rodar` | não (é rápido) | — declarada | sim (S-31) |
| marcar a página que acabou de aparecer (S-68) | `qt/trabalho.py::DeteccaoDeFundo`, sem trancar nada; só o último pedido espera | não (é rápido) | — declarada | não (o detector não usa o modelo) |
| exportação de um livro | `qt/exportador.py` | sim, entre páginas (S-24) | não, tem parcial | sim (S-57) |
| treino | `qt/dialogos.py::ControladorDeTreino` | sim, entre épocas (S-60) | sim, desde a melhor época | escreve o `.pt` |
| varredura do livro — Galeria **e** fila de revisão (S-119) | `qt/painel_da_galeria.py`, com o `SumidouroDeRevisao` de `qt/painel_de_revisao.py` | sim, entre páginas | não, retoma de onde parou (S-120) | sim (S-57) |
| busca por nome na base | `qt/painel_da_galeria.py` | sim, entre partidas | não, é curta | não |
| busca por posição na base | `qt/painel_da_galeria.py` | sim, entre pedaços | **sim**, a passada inteira | não |
| detecção de duplicatas | `qt/painel_do_dataset.py` | não | não, é derivada | não |
| leitura do texto da página | `qt/painel_de_texto.py` | sim, entre páginas | não, o `.cvtxt` já está em disco | não (é o classificador de caractere) |
| exportação do texto lido | `qt/painel_de_texto.py` | não | **sim**, o destino fica pela metade | não |
| avaliação do motor sobre a posição | `qt/painel_de_estudo.py` | não | — declarada | não (é o Stockfish) |

O modelo é compartilhado entre elas e fica **sob lock durante o uso**, não só durante a
carga: o treino reescreve o mesmo `.pt` que uma leitura concorrente estaria lendo (S-31).

Até a S-57 essa frase valia para **uma** delas. A exportação e a varredura da fila
chamavam `load_model` por conta própria, fora do lock — e são justamente as duas longas, as
que de fato coexistem com um treino. Hoje as duas recebem `model_session` do `OcrService`; o
único `load_model` que sobrou em `pdf_to_pgn.py` está em `_own_model_session`, o caminho dos
CLIs, onde não há serviço nem treino concorrente.

Fechar a janela consulta `ui/busy.py` antes de destruir: `BusyRegistry` sabe o que está
rodando e **o que se perde**, que não é a mesma coisa em todas — a exportação tem checkpoint
parcial e sobrevive, o treino perde o progresso desde a última época melhor (S-60).

A lista de quem se registra é travada por teste, e não por convenção: `test_busy.py` varre
`qt/*.py` por `threading.Thread(` e `Tarefa(` e exige que cada uma ou registre, ou esteja na
lista de exceções **com o motivo escrito**. No corte do Tk (S-506) a varredura quase ficou
apontada para `ui/`, que já não abre thread nenhuma -- uma guarda verde sobre zero threads. Sem isso, a S-60 cobriu duas operações
e as dez seguintes entraram em silêncio — inclusive a mais cara do programa (S-112).

---

## Formatos e persistência

A tabela é conferida por `tests/test_docs.py` **nos dois sentidos** (S-135): artefato em `data/`
sem linha aqui, e linha aqui apontando para um caminho que não existe e não está marcado como
**sob demanda**, fazem a suíte falhar. Ela já esteve com 8 dos 16 artefatos, o `splits.csv`
duplicado e uma linha para um arquivo que este repositório nunca teve.

| arquivo | o que guarda | versionado |
|---|---|---|
| `data/labels.csv` | rótulos: imagem, FEN, lado a jogar, origem, split, e a confirmação de ilegalidade deliberada (`illegal_ok`) | sim |
| `data/splits.csv` | partição treino/validação/teste, estável sob crescimento, atribuída às amostras novas pelo próprio treino (S-56) | sim |
| `data/samples/` | os PNGs 800×800 dos tabuleiros | não (5,0 GB) |
| `data/field_set.jsonl` | as páginas reais anotadas à mão: a régua de campo (S-41, S-77, S-95) | **sim** |
| `data/quarantine.csv` | as linhas que o `cvoff-audit --fix` tirou do `labels.csv`, com o motivo | não — `.gitignore:28` |
| `data/settings.json` | preferências do usuário, incluindo o endpoint remoto | não |
| `data/janela.json` | o que a janela lembra entre execuções: último livro, página, zoom, geometria, divisor, aba, pele, densidade e conjunto de peças (S-25/S-156) | não — **sob demanda**: nasce no primeiro fechamento da janela |
| `data/app_tkinter_state.json` | o mesmo arquivo com o nome de antes do corte (S-506). É **lido uma vez**, quando o `janela.json` ainda não existe, e nunca reescrito: ele guarda o histórico de 50 livros com a página de cada um, e renomear sem lê-lo apagaria meses de "onde eu parei neste livro?" | não |
| `data/review_queue.json` | a fila de revisão | não |
| `data/review_cache/` | os recortes das páginas já varridas, para a fila não reabrir o PDF | não (10,4 GB — o maior artefato do projeto) |
| `data/orphans/` | os PNGs cujo rótulo sumiu do `labels.csv`, guardados em vez de apagados (S-63) | não |
| `data/gallery/<livro>.json` | as anotações de exportação por diagrama: lance, vez, link, headers e a partida escolhida (S-67) | **não** — descreve o conteúdo de um livro protegido, como o `review_cache` |
| `data/gallery/<livro>.index.json` | onde estão os diagramas daquele livro e o recorte de cada um | não — derivado do PDF, refeito varrendo o livro |
| `data/gallery_human.jsonl` | **o extrato do que uma pessoa digitou ou escolheu** na galeria (S-115) | **sim** |
| `data/games_index.sqlite` | o índice por nome e por posição da base de partidas (S-72, S-73) | não (490 MB — reconstruível a partir do `pgn_database/`) |
| `data/games_positions.sqlite` | o cache de posições da varredura, **uma linha por colocação** (S-84, S-113, S-140) | não — **sob demanda**: nasce na primeira vez que alguém abre o cache |
| `data/games_positions__<bases>.sqlite` | o mesmo cache, **de um conjunto de bases que não é a pasta inteira** — `ui/database_choice.store_path_for` nomeia o arquivo pelos `.pgn` escolhidos, para que experimentar uma base não descarte o cache da outra | não — **sob demanda**: um por conjunto que alguém selecionar |
| `data/games_positions.json` | o mesmo cache no formato anterior. Lido **uma vez** e renomeado; depois disso não é lido por nada | não — **sob demanda**: só em quem usou o programa antes da S-140 |
| `data/games_positions.json.migrado` | o anterior, já dentro do SQLite. Renomear em vez de apagar porque apagar o que era do usuário não é da alçada de uma migração | não — **sob demanda**: aparece quando o SQLite é criado |
| `data/games_matches.json` | os casamentos livro↔partida, formato v1 | não |
| `data/games_matches_v2.json` | os mesmos, formato v2 — o artefato dos 104 minutos de 2026-08-13 (S-128) | não |
| `data/provenance_index.jsonl` | dHash de cada diagrama do acervo, para recuperar procedência (S-52) | não — **sob demanda**: só existe depois de `cvoff-provenance`, e são horas |
| `data/texto_conflitos.json` | **o julgamento humano dos 83 grupos em que a mesma imagem está arquivada sob dois caracteres** (S-202): o hash do recorte, os rótulos em disputa, quem venceu e **por quê** — inclusive as 50 fichas em que ninguém consegue decidir, e a razão | **sim** — é trabalho humano, e é o que `cvoff-texto-conflitos --aplicar` obedece |
| `data/estudos/` | **a sala de estudo de cada livro** (S-271): um `.pgn` por PDF, com uma partida por diagrama analisado e `SourcePDF`/`Page`/`Diagram` nos headers. É PGN de verdade -- abre no ChessBase e no Scid como base de partidas | não -- é análise de uma pessoa sobre um livro que nem está no repositório, e a chave do arquivo carrega o caminho dele |
| `data/rascunhos/` | **o rascunho automático da aba de texto** (S-255): um `.cvtxt` por folha de cada livro, gravado alguns segundos depois da última tecla e apagado quando alguém salva ou recupera. É a rede que impede uma tarde de correção de morrer com a janela | não — **sob demanda**: nasce na primeira folha editada, tem teto de oito por livro e o mais antigo sai primeiro |
| `data/quarentena_texto/` | os recortes que saíram da base por rótulo contraditório, na pasta da classe de origem, mais o manifesto que `--desfazer` lê de volta | não — **sob demanda**: nasce no primeiro `cvoff-texto-conflitos --aplicar`. São os mesmos PNGs de `training_data/`, e a pasta existe para que a poda seja reversível |
| `data/faixas_para_transcrever/` | os PNGs das 123 faixas de legenda exportados por `cvoff-texto-placar --exportar`, um por linha da referência, mais o `indice.json` que liga número a livro e página — **a imagem que os motores leem**, para a transcrição humana da S-183 | não — **sob demanda**: nasce no `--exportar` e é refeito a partir de `docs/metrics/texto_faixa_referencia.jsonl`. São recortes de PDF protegido, como o `review_cache` |
| `models/*.pt` | checkpoints, com semente, split e métrica gravados | não |
| `PGN/<livro>.pgn` | as posições aceitas | não |
| `PGN/<livro>.review.pgn` | as rejeitadas e as de baixa confiança, com o motivo | não |
| `PGN/<livro>.partial.jsonl` | checkpoint da exportação, apagado ao concluir | não |

**A galeria entra pela metade, e a metade é escolhida** (S-115). São 15,3 MB e 15.412 anotações,
das quais o que a base preencheu volta com `cvoff-games --apply` a partir do cache de posições
— o que **não** volta é a vez a jogar que alguém conferiu na legenda impressa e as 23 partidas
escolhidas a mão na lista de candidatas (S-86). O crivo é o `filled_fields`, que já responde a
pergunta campo a campo, e o extrato são ~214 KB:

```bash
cvoff-gallery --census          # quanto há, e quanto disso é irrecuperável
cvoff-gallery --export-human    # data/gallery/ -> data/gallery_human.jsonl
cvoff-gallery --import-human    # o caminho de volta; o que é da pessoa vence o da base
```

Toda escrita de arquivo de trabalho passa por `atomic_io`: grava num temporário e troca. O
`labels.csv` é 5.321 rótulos de trabalho humano acumulado, e a interface o regrava inteiro a
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
infere tipo — `source_page` tem 84,1% de células vazias, a coluna virava `float64` e `20`
voltava `20.0`, e como a gravação relê o arquivo inteiro antes de acrescentar uma linha, uma
amostra nova reescrevia todas as antigas nesse formato. Com `csv.DictReader` não há tipo a
inferir: todas as colunas do esquema são texto. O defeito deixou de ser evitado e passou a não
existir.
