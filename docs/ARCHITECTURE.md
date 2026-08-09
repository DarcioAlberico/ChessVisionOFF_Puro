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
| `detection/` | Detector híbrido: imagem embutida do PDF localiza, contorno alinha. |
| `inference.py` | Carrega o modelo, prevê as 64 casas, decide a orientação, aplica TTA. |
| `decode.py` | Decodificação sujeita às regras do xadrez. |
| `semantics.py` | Lado a jogar e direitos de roque, deduzidos da posição. |
| `pdf_text.py` | Legenda e metadados da camada de texto do PDF. |
| `fen_utils.py` | Sintaxe **e** legalidade — duas coisas distintas, ver o README. |
| `pdf_to_pgn.py` | Varredura de um livro, gate de exportação, checkpoint parcial. |
| `batch.py` | Varredura da biblioteca inteira, com relatório consolidado. |
| `review_queue.py` | Fila ordenada por valor de informação. |
| `dataset.py` · `splits.py` · `audit.py` | Dados de treino: leitura, partição estável, auditoria. |
| `training.py` · `model.py` · `checkpoint.py` | Treino, arquitetura e persistência. |
| `calibration.py` · `evaluation.py` · `experiments.py` | Medição. |
| `engine.py` | Motor UCI opcional (Stockfish). |
| `net_correction.py` · `settings.py` | Segunda opinião externa, e a configuração que a autoriza. |
| `atomic_io.py` | Escrita que não deixa arquivo pela metade. |

### A interface (`src/chess_diagram_ocr/ui/`)

| módulo | responsabilidade |
|---|---|
| `pdf_panel.py` | Exibir o PDF, navegar, zoom, seleção de área, modo leitura. |
| `result_panel.py` | O editor: tabuleiro, FEN, lado a jogar, legalidade, gravação. |
| `study_panel.py` | Tabuleiro de estudo, árvore de variantes, PGN, motor. |
| `review_panel.py` · `dataset_panel.py` | As abas de revisão e de dataset. |
| `board_widget.py` · `board_edit.py` | O tabuleiro interativo e a edição sem regra de lance. |
| `legality.py` | Legalidade em pt-BR, com as casas culpadas. |
| `page_results.py` | Cache do reconhecimento por página. |
| `export_controller.py` · `training_dialog.py` | As duas operações longas e seus diálogos. |
| `state.py` · `strings.py` · `shortcuts.py` · `tooltip.py` | Estado, vocabulário, atalhos, dicas. |
| `busy.py` | O que está rodando e o que se perde ao fechar a janela (S-60). Sem Tk. |

`app_tkinter.py` monta esses painéis e liga um ao outro. Nada mais.

---

## As três fontes de verdade sobre o lado a jogar

É a decisão de projeto mais consequente do produto, porque até a Fase 3 **100% dos
exercícios saíam como "brancas jogam"** e em livro de tática cerca de metade está errada.

| fonte | quando responde | alcance medido |
|---|---|---|
| texto do PDF (S-16) | há legenda ao lado do diagrama | **3** dos 27 livros |
| legalidade (S-17) | quem não joga está em xeque | 118 dos 3.195 rótulos |
| padrão "brancas" | nenhuma das duas | o resto |

O PGN grava `[SideToMoveSource]` **sempre**. A maioria do acervo cai no padrão, e um palpite
precisa parecer um palpite — é essa a diferença entre um dado e uma suposição herdada.

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
| `models/*.pt` | checkpoints, com semente, split e métrica gravados | não |
| `data/splits.csv` | partição, atribuída às amostras novas pelo próprio treino (S-56) | sim |
| `PGN/<livro>.pgn` | as posições aceitas | não |
| `PGN/<livro>.review.pgn` | as rejeitadas e as de baixa confiança, com o motivo | não |
| `PGN/<livro>.partial.jsonl` | checkpoint da exportação, apagado ao concluir | não |

Toda escrita de arquivo de trabalho passa por `atomic_io`: grava num temporário e troca. O
`labels.csv` é 3.200 rótulos de trabalho humano acumulado, e a interface o regrava inteiro a
cada correção. Desde a S-57 o `.pt` também passa por ali — era o maior dos arquivos, o mais
demorado de escrever, e o único cuja escrita acontece numa thread de fundo enquanto outra
pode estar lendo o mesmo caminho.

O `labels.csv` é lido por `dataset.read_labels_frame`, que o trata como **texto puro**. Sem
isso o pandas tipava `source_page` como `float64` (98,6% das células estão vazias) e `20`
voltava `20.0`: como a gravação relê o arquivo inteiro antes de acrescentar uma linha, uma
amostra nova reescrevia todas as antigas nesse formato (S-58).
