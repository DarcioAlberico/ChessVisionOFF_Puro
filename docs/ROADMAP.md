# Roadmap — ChessVisionOFF_Puro

Base: [ANALISE.md](ANALISE.md). Detalhes de implementação: [SPEC.md](SPEC.md).

Estimativas em dias de trabalho focado de uma pessoa. As fases são sequenciais por dependência: cada uma depende de algo que a anterior estabelece.

---

## Visão geral

```
Fase 0  Higienização do repositório          1–2 d   ▸ desbloqueia tudo, custo cresce se atrasar
Fase 1  Verdade e medição                    3–5 d   ▸ sem isso "melhorou" é indemonstrável
Fase 2  Precisão do OCR                      5–8 d   ▸ maior ganho de qualidade do projeto
Fase 3  Semântica: lado a jogar e metadados  4–6 d   ▸ metade dos exercícios está errada hoje
Fase 4  Produtividade humana                 5–8 d   ▸ ataca o gargalo real (tempo do usuário)
Fase 5  Modelo e desempenho                  4–6 d   ▸ só faz sentido depois da Fase 1
Fase 6  Consolidação do produto              5–8 d   ▸ unificação, i18n, empacotamento
```

Total: ~27 a 43 dias. As Fases 0 a 2 (9 a 15 dias) entregam a maior parte do valor.

---

## Fase 0 — Higienização do repositório (1–2 dias)

**Por que primeiro:** é o único item cujo custo aumenta com o tempo. Depois do primeiro commit, 3,3 GB de PNGs e PDFs ficam no histórico do git para sempre.

| # | Entrega | Ref. spec |
|---|---|---|
| 0.1 | `.gitignore` cobrindo `data/samples/`, `PDF/`, `PGN/`, `models/*.pt`, `Python-Easy-Chess-GUI-master/`, lixo de raiz | S-01 |
| 0.2 | Remover `Python-Easy-Chess-GUI-master/`, `pecg_*`, `teste-001.*` da árvore | S-01 |
| 0.3 | Commit inicial com árvore limpa | S-01 |
| 0.4 | `pyproject.toml`: `[build-system]`, `[tool.setuptools]` src-layout, `[project.scripts]`, deps de dev, remover markers `<3.9` mortos | S-02 |
| 0.5 | `pip install -e .` funcionando; remover as 4 gambiarras de `sys.path` | S-02 |
| 0.6 | `ruff` + `mypy` configurados; CI no GitHub Actions rodando lint + testes | S-03 |
| 0.7 | `logging` no lugar de `print`; strings em pt-BR **com acento** | S-04 |

**Critério de saída:** `git status` limpo, `pip install -e .` seguido de `pytest` verde em máquina nova, CI verde.

---

## Fase 1 — Verdade e medição (3–5 dias)

**Por que agora:** hoje não existe conjunto de teste. Qualquer mudança da Fase 2 em diante seria adivinhação.

| # | Entrega | Ref. spec |
|---|---|---|
| 1.1 | `fen_utils.is_legal_position()` usando `Board.status()`; `is_valid_fen` passa a ser explicitamente sintática | S-05 |
| 1.2 | CLI `tools/audit_dataset.py`: relatório de rótulos ilegais, duplicatas, imagens órfãs | S-06 |
| 1.3 | Sanear os 100 rótulos ilegais (49 corrigir/remover; 51 `OPPOSITE_CHECK` → marcar lado a jogar preto) | S-06 |
| 1.4 | Deduplicação por hash perceptual da imagem | S-06 |
| 1.5 | Split treino/validação/teste **persistido em arquivo**, estável sob crescimento do dataset | S-07 |
| 1.6 | `tools/evaluate.py`: acurácia por casa, **exata por tabuleiro**, por classe, matriz de confusão, taxa de posição ilegal | S-08 |
| 1.7 | Baseline registrado em `docs/BASELINE.md` (número honesto, em conjunto de teste) | S-08 |
| 1.8 | Testes de `fen_utils`, `dataset`, `inference`; fixtures versionados; teste de regressão de acurácia | S-09 |

**Critério de saída:** `python -m tools.evaluate --split test` imprime acurácia exata por tabuleiro; nenhum rótulo ilegal em `labels.csv`; baseline documentado.

---

## Fase 2 — Precisão do OCR (5–8 dias)

**Por que é o núcleo:** ganho de precisão sem retreinar o modelo. Todos os itens exploram informação que já existe e está sendo descartada.

| # | Entrega | Ref. spec |
|---|---|---|
| 2.1 | `predict_board()` retorna distribuição por casa, não só o argmax | S-10 |
| 2.2 | Confiança = mínimo/entropia por casa em vez de média; `min_square_confidence` no `DiagramPosition` | S-10 |
| 2.3 | **Decodificação com restrições**: busca sobre as probabilidades por casa sujeita às regras (1 rei de cada cor, ≤8 peões, nada na 1ª/8ª fila, ≤16 peças) | S-11 |
| 2.4 | Extração de diagrama por **imagem embutida** do PDF (`page.get_image_info`) com recorte da moldura/legenda | S-12 |
| 2.5 | Detector híbrido: candidatos embutidos + contorno, desempate por legalidade e concordância | S-12 |
| 2.6 | Auto-orientação por tentativa (0°/180°) escolhendo a mais plausível; `rotate_180` deixa de ser global | S-13 |
| 2.7 | Unificar `reading_order` entre GUI e export (padrão único, configurável) | S-14 |
| 2.8 | Gate de exportação: posições ilegais ou de baixa confiança vão para `*.review.pgn` separado | S-15 |

**Critério de saída:** zero posições ilegais no PGN exportado dos 27 PDFs; acurácia exata por tabuleiro no conjunto de teste ≥ baseline + margem medida; erros K↔Q do `1937 Kemeri.pdf` corrigidos.

---

## Fase 3 — Semântica: lado a jogar e metadados (4–6 dias)

**Por que:** hoje 100% dos exercícios saem como "brancas jogam"; em livros de tática ~50% está errado. É o maior erro semântico do produto.

| # | Entrega | Ref. spec |
|---|---|---|
| 3.1 | Extração do texto vizinho ao diagrama via `page.get_text("blocks")` + associação por proximidade geométrica | S-16 |
| 3.2 | Classificador de lado a jogar por padrões multilíngue ("White to move", "Brancas jogam", "Weiß am Zug", "Schwarz zieht", "◻/◼") | S-16 |
| 3.3 | Inferência de lado a jogar por legalidade quando não há texto (se pretas estão em xeque, é vez das pretas) | S-17 |
| 3.4 | Inferência de direitos de roque a partir da posição de reis/torres | S-17 |
| 3.5 | Metadados no PGN: número do exercício, jogadores, evento, ano quando extraíveis da legenda | S-18 |
| 3.6 | Campo `side_to_move` no `labels.csv` e na UI de correção (migração compatível) | S-19 |
| 3.7 | Deduplicação de diagramas repetidos entre páginas no PGN exportado | S-18 |

**Critério de saída:** em amostra manual de 50 exercícios do `1001 Winning Chess Sacrifices`, lado a jogar correto em ≥95%; headers de PGN com número do exercício.

---

## Fase 4 — Produtividade humana (5–8 dias)

**Por que:** com a Fase 2 pronta, o gargalo passa a ser o tempo do usuário corrigindo. Hoje corrigir significa editar uma string FEN à mão.

| # | Entrega | Ref. spec |
|---|---|---|
| 4.1 | **Editor de posição por clique/arraste** na aba de resultado (reaproveitar o código de arraste do tabuleiro de estudo) | S-20 |
| 4.2 | **Heatmap de incerteza**: casas de baixa confiança destacadas no tabuleiro reconhecido | S-21 |
| 4.3 | Painel de legalidade: mostra o `Board.status()` em linguagem clara ("faltando rei preto") | S-21 |
| 4.4 | Fila de revisão ordenada por incerteza (aprendizado ativo) atravessando páginas | S-22 |
| 4.5 | Navegador/editor do dataset: listar, filtrar por status, recorrigir, remover amostras | S-23 |
| 4.6 | Exportação com cancelamento e retomada (checkpoint por página) | S-24 |
| 4.7 | Atalhos de teclado para o ciclo corrigir→salvar→próximo | S-20 |
| 4.8 | Escrita atômica do estado da app; parar de silenciar exceções | S-25 |

**Critério de saída:** medir tempo para corrigir 20 diagramas antes e depois; alvo de redução ≥50%.

---

## Fase 5 — Modelo e desempenho (4–6 dias)

**Por que só agora:** sem a Fase 1 não há como saber se uma mudança de modelo ajudou. E a análise mostra que o classificador **não é** o gargalo atual — este é o item de menor prioridade relativa.

| # | Entrega | Ref. spec |
|---|---|---|
| 5.1 | Cache do dataset limitado (LRU) — resolve os 5,8 GiB de RAM | S-26 |
| 5.2 | `num_workers` configurável; amostras armazenadas em resolução reduzida | S-26 |
| 5.3 | Treino reprodutível: `--fresh`, `strict=True`, semente e split registrados no checkpoint | S-27 |
| 5.4 | Métricas de treino corretas: exata por tabuleiro, por classe, pesos de classe para o desbalanceamento | S-27 |
| 5.5 | Calibração de confiança (temperature scaling) no conjunto de validação | S-28 |
| 5.6 | Experimento controlado: entrada em cor vs cinza, 32/48/64 px, backbone alternativo — decidir por medição | S-29 |
| 5.7 | TTA leve (deslocamentos de ±2 px) com voto | S-29 |
| 5.8 | Instalar torch com CUDA; exportação ONNX opcional para CPU rápida | S-30 |

**Critério de saída:** treino de época completa sem exceder 2 GiB de RAM; métricas reprodutíveis entre execuções; ganho ou não-ganho de cada experimento registrado.

---

## Fase 6 — Consolidação do produto (5–8 dias)

| # | Entrega | Ref. spec |
|---|---|---|
| 6.1 | **Camada de serviço** `src/chess_diagram_ocr/service.py` — Tkinter e Streamlit passam a ser só apresentação | S-31 |
| 6.2 | Quebrar `app_tkinter.py` em módulos (`ui/pdf_panel.py`, `ui/result_panel.py`, `ui/study_panel.py`, `ui/state.py`) | S-31 |
| 6.3 | "Corrigir Net" opt-in, endpoint configurável, documentado, com aviso de envio externo | S-32 |
| 6.4 | Centralizar strings; pt-BR acentuado e consistente | S-04 |
| 6.5 | Engine (Stockfish) opcional na aba de análise: avaliação e melhor lance | S-33 |
| 6.6 | Processamento em lote de vários PDFs com relatório consolidado | S-34 |
| 6.7 | README reescrito (fluxos reais, resolução de problemas) + `CONTRIBUTING.md` | S-35 |
| 6.8 | Empacotamento Windows (PyInstaller) para uso sem Python instalado | S-36 |

**Critério de saída:** Streamlit e Tkinter com paridade de funcionalidades; `app_tkinter.py` abaixo de 600 linhas; executável rodando em máquina sem Python.

---

## Sequenciamento sugerido de curto prazo

Se o tempo disponível for uma semana, o corte de maior retorno é:

1. **Dia 1** — Fase 0 completa (0.1 a 0.5). Repositório versionado e instalável.
2. **Dia 2** — S-05 (legalidade real) + S-06 (auditoria e saneamento do dataset).
3. **Dia 3** — S-07 (split persistido) + S-08 (harness de avaliação e baseline honesto).
4. **Dias 4–5** — S-10 (confiança por casa) + S-11 (decodificação com restrições). Aqui vem o salto de qualidade.
5. **Dia 6** — S-15 (gate de exportação) + S-14 (ordenação unificada). Rodar os 27 PDFs e comparar com o baseline.
6. **Dia 7** — S-21 (heatmap + painel de legalidade). O usuário passa a ver onde o modelo está inseguro.

Ao fim da semana o PGN exportado deixa de conter posições ilegais, os erros K↔Q estão corrigidos, existe um número de acurácia confiável, e o repositório tem histórico.

---

## Riscos e decisões que precisam do dono do projeto

| Risco / decisão | Observação |
|---|---|
| **Os PDFs são material protegido** | Nunca versionar `PDF/`. Se o projeto for publicado, os livros não vão com ele. Decisão sobre distribuição é sua. |
| **`data/samples` com 2,7 GB** | Precisa de estratégia: git-lfs, release de dados, ou reduzir resolução (Fase 5.2 corta >10×). Recomendo reduzir e usar release. |
| **Reduzir resolução das amostras é irreversível** | Fazer com script que preserve os originais em backup externo até validar. |
| **Migração do `labels.csv`** | Adicionar `side_to_move` (Fase 3.6) muda o esquema. Script de migração com backup, e `dataset.py` aceitando os dois formatos por um período. |
| **`Python-Easy-Chess-GUI-master/`** | Presumo que seja referência de estudo, não dependência — nenhum código do projeto o importa (verificado). Se estiver errado, me avise antes de remover. |
| **Endpoint `helpman.komtera.lt`** | Serviço de terceiro sem contrato. Pode sair do ar. Tratar como opcional, nunca como dependência do fluxo principal. |
| **Sem GPU no ambiente atual** | torch é `+cpu`. Se houver GPU na máquina, instalar a wheel CUDA acelera treino em ~10×. Vale verificar antes da Fase 5. |
