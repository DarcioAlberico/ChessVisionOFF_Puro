# Especificação das melhorias — ChessVisionOFF_Puro

Base: [ANALISE.md](ANALISE.md). Sequenciamento: [ROADMAP.md](ROADMAP.md).

> Este documento cobre **S-01 a S-36** (Fases 0 a 6), sequenciado em
> [ROADMAP.md](ROADMAP.md).
>
> **Onde mora a spec de cada item (S-NN).** A spec está em cinco arquivos, e essa dispersão
> custou duas entregas — a S-76 e a S-77 ficaram três meses em documento nenhum (S-133).
> `tests/test_docs.py` confere esta tabela contra o disco (S-134): item entregue sem seção e
> seção no arquivo errado fazem a suíte falhar.
>
> | itens | arquivo |
> |---|---|
> | S-01 a S-36 | [SPEC.md](SPEC.md) |
> | S-37 a S-77 | [SPEC_FASE7.md](SPEC_FASE7.md) |
> | S-78 a S-82, S-143 | [ANALISE_DETECCAO.md](ANALISE_DETECCAO.md) |
> | S-83 a S-94 | [PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md) |
> | S-95 a S-142, S-171 a S-174, S-218, S-219, S-220, S-221 | [SPEC_FASE14.md](SPEC_FASE14.md) |
> | S-144 a S-170 | [SPEC_UI.md](SPEC_UI.md) |

Cada item tem **Problema** (com referência ao arquivo/linha atual), **Solução**, **Interface proposta**, **Critério de aceite** e **Testes**. Os itens são independentes o suficiente para serem implementados em ordem diferente, exceto onde há dependência declarada.

Convenção: nomes de módulos novos são sugestões; o que importa é a fronteira de responsabilidade.

---

# Fase 0 — Higienização

## S-01 · Repositório versionado e limpo

**Problema.** `git log` falha: nenhum commit existe. `.gitignore` cobre apenas `__pycache__/`, `build/`, `dist/`, `*.egg-info`, `.venv`. Um `git add .` versionaria 2,7 GB (`data/samples/`), 584 MB de livros protegidos (`PDF/`) e 57 MB de código de terceiro vendorizado.

**Solução.**

`.gitignore` alvo:

```gitignore
# Python
__pycache__/
*.py[oc]
build/
dist/
wheels/
*.egg-info
.venv/
.mypy_cache/
.ruff_cache/
.pytest_cache/

# Dados e artefatos (grandes / não versionáveis)
data/samples/
data/app_tkinter_state.json
models/*.pt
models/*.onnx

# Material de origem protegido por direito autoral
PDF/

# Saída gerada
PGN/

# Terceiros e lixo de execução
Python-Easy-Chess-GUI-master/
pecg_log.txt
pecg_user.json
teste-001.*
```

`data/labels.csv` **permanece versionado** (é texto, ~250 KB, e é a verdade do projeto). Adicionar `data/samples/.gitkeep` e `models/.gitkeep`.

Remover da árvore: `Python-Easy-Chess-GUI-master/` (nenhum módulo do projeto o importa — verificado), `pecg_log.txt`, `pecg_user.json`, `teste-001.ini`, `teste-001.pgn`.

**Critério de aceite.** `git status --short` vazio após o commit inicial; `git count-objects -vH` reportando repositório abaixo de 5 MB; clone novo + `pip install -e .` + `pytest` verde.

---

## S-02 · Pacote instalável, sem gambiarra de `sys.path`

**Problema.** `import chess_diagram_ocr` falha no `.venv` do projeto — o pacote nunca foi instalado. `pyproject.toml` não tem `[build-system]`. Os quatro entrypoints (`app_tkinter.py:24-26`, `app_streamlit.py:15-17`, `train_model.py:7-10`, `infer_pdf.py:7-10`, `export_pdf_pgn.py:7-10`) repetem `sys.path.insert(0, str(SRC_DIR))`. `requires-python = "==3.10.*"` convive com markers `python_full_version < '3.9'` que nunca são satisfeitos.

**Solução.** Adicionar ao `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]

[project.scripts]
cvoff-train  = "chess_diagram_ocr.cli.train:main"
cvoff-infer  = "chess_diagram_ocr.cli.infer:main"
cvoff-export = "chess_diagram_ocr.cli.export_pgn:main"
cvoff-audit  = "chess_diagram_ocr.cli.audit:main"
cvoff-eval   = "chess_diagram_ocr.cli.evaluate:main"

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.6", "mypy>=1.11", "types-Pillow"]
```

Limpar as dependências: remover todos os markers `python_full_version < '3.9'` (mortos sob `==3.10.*`) e as restrições duplicadas de `numpy`/`opencv-python`/`pandas`.

Mover os CLIs de raiz para `src/chess_diagram_ocr/cli/` mantendo scripts finos na raiz por compatibilidade (ou remover, documentando os novos comandos). Apagar os cinco blocos de `sys.path.insert`.

**Critério de aceite.** Em venv novo: `pip install -e ".[dev]"` → `python -c "import chess_diagram_ocr"` funciona → `cvoff-infer "PDF/1937 Kemeri.pdf" --page 0` funciona de qualquer diretório de trabalho.

---

## S-03 · Lint, tipos e CI

**Problema.** Sem linter, sem type checker, sem CI. O código é bem anotado (`from __future__ import annotations` em todos os módulos), então o retorno de `mypy` é imediato.

**Solução.** `[tool.ruff]` com `line-length = 120` e regras `E,F,I,UP,B`. `[tool.mypy]` em modo não-estrito no início, com `strict = true` apenas para `src/chess_diagram_ocr/` (excluir `app_*.py` inicialmente). Workflow `.github/workflows/ci.yml`: matriz em Python 3.10, passos `ruff check`, `mypy src`, `pytest`.

**Critério de aceite.** CI verde no commit inicial. `ruff check .` sem erros.

---

## S-04 · Logging e strings em pt-BR consistente

**Problema.** Diagnóstico é `print` + strings de status na GUI. `training.py:175` imprime `[Early Stopping] Model did not improve...` em inglês dentro de uma UI em português. Textos sem acentuação em todo o projeto ("posicao", "deteccao", "Configuracao", "Epocas"). Exceções silenciadas em `app_tkinter.py:271-273, 464-465, 488-489, 727-728, 1273-1274` sem registro.

**Solução.** `logging.getLogger(__name__)` nos módulos de `src/`; handler configurado uma vez nos entrypoints, com `--verbose` nos CLIs e arquivo rotativo em `logs/`. Substituir `except Exception: pass` por `logger.warning(..., exc_info=True)` mantendo o comportamento tolerante onde ele é intencional. Centralizar textos de UI em `src/chess_diagram_ocr/ui/strings.py` com acentuação correta.

**Critério de aceite.** Nenhum `print` em `src/`; nenhum `except Exception: pass` sem log; `grep -rn "posicao\|deteccao\|Configuracao"` sem resultados em strings de usuário.

---

# Fase 1 — Verdade e medição

## S-05 · Validação de legalidade real

**Problema.** `fen_utils.is_valid_fen()` (`fen_utils.py:17`) só verifica sintaxe. Verificado: aceita `8/8/8/3R4/8/3K4/nQ2p2b/1K6` (dois reis brancos), `8/8/8/8/8/8/PPPPPPPP/PPPPPPPP` (16 peões, peões na 1ª fila) e `8/8/8/8/8/8/8/8` (vazio). É usado como gate em `dataset.append_training_sample:119`, `BoardFenDataset._load_entries:53`, e em todos os frontends antes de salvar.

**Solução.** Separar os dois conceitos, com nomes que não deixem confundir:

```python
# src/chess_diagram_ocr/fen_utils.py

def is_syntactically_valid_fen(fen: str) -> bool:
    """A FEN é parseável. NÃO garante posição legal."""

@dataclass(frozen=True)
class PositionCheck:
    is_legal: bool
    status: chess.Status
    problems: tuple[str, ...]      # rótulos em pt-BR para a UI
    is_fatal: bool                 # impede treino/exportação
    is_soft: bool                  # só OPPOSITE_CHECK → provável lado a jogar invertido

def check_position(fen: str) -> PositionCheck: ...
def describe_status(status: chess.Status) -> tuple[str, ...]: ...
```

Classificação dos status:

- **Fatal** (bloqueia salvar como rótulo e bloqueia exportação normal): `NO_WHITE_KING`, `NO_BLACK_KING`, `TOO_MANY_KINGS`, `TOO_MANY_WHITE_PIECES`, `TOO_MANY_BLACK_PIECES`, `TOO_MANY_WHITE_PAWNS`, `TOO_MANY_BLACK_PAWNS`, `PAWNS_ON_BACKRANK`, `EMPTY`.
- **Suave** (aceita, mas sinaliza): `OPPOSITE_CHECK` — em posição de diagrama sem lado a jogar conhecido, isso quase sempre significa que é a vez do outro lado. Ver S-17.
- Ignorar: `BAD_CASTLING_RIGHTS`, `INVALID_EP_SQUARE` quando derivados do preenchimento padrão `w - - 0 1`.

`describe_status` devolve texto humano: `NO_BLACK_KING` → `"falta o rei preto"`, `TOO_MANY_KINGS` → `"mais de um rei da mesma cor"`.

**Critério de aceite.** Salvar rótulo com posição fatalmente ilegal é rejeitado com mensagem específica. `BoardFenDataset` recusa e **conta** linhas fatais em vez de aceitá-las silenciosamente.

**Testes.** Tabela cobrindo cada status fatal, cada status suave, e posições legais de fronteira (8 peões por lado; rei+rei; promoção com 9 peças pesadas).

---

## S-06 · Auditoria e saneamento do dataset

**Problema.** Medido em `data/labels.csv`: **100 rótulos ilegais de 3.244 (3,1%)** — 51 `OPPOSITE_CHECK`, 20 sem rei branco, 17 sem rei preto, 10 com peões na 1ª fila, 7 com reis demais, 2 peças demais, 2 peões demais, 1 vazio. Também **283 FENs duplicados**. Não existe ferramenta para inspecionar ou corrigir; o CSV é append-only e a única saída é editar à mão.

**Solução.** CLI `cvoff-audit`:

```
cvoff-audit                       # relatório: ilegais por status, duplicatas, órfãos, distribuição de classes
cvoff-audit --fix-soft            # OPPOSITE_CHECK → marca lado a jogar preto (ver S-19)
cvoff-audit --quarantine          # move rótulos fatais para data/quarantine.csv, remove do labels.csv
cvoff-audit --dedupe              # remove duplicatas por hash da imagem, mantendo a primeira
cvoff-audit --prune-orphans       # remove linhas cujo PNG não existe / PNGs sem linha
```

Relatório inclui: total, ilegais por status com exemplos, duplicatas por hash de imagem vs por FEN (distinguir os dois casos — FEN igual em livros diferentes é legítimo), imagens órfãs, contagem por classe de peça (para expor desbalanceamento), e histograma de tamanho de arquivo.

Deduplicação por **hash perceptual** (dHash de 64 bits sobre 9×8 em cinza) e não por hash de bytes: recortes ligeiramente diferentes do mesmo diagrama têm bytes diferentes. Distância de Hamming ≤ 3 = duplicata.

Toda escrita cria backup `labels.csv.bak-<timestamp>` antes.

**Critério de aceite.** Após `--quarantine --dedupe`, `cvoff-audit` reporta zero rótulos fatalmente ilegais e zero duplicatas de imagem. `data/quarantine.csv` preserva o que foi retirado, para recorreção pela UI da S-23.

**Testes.** CSV sintético com um caso de cada categoria; verificar contagens e o conteúdo pós-fix.

---

## S-07 · Split treino/validação/teste persistido

**Problema.** `training._split_square_indices_by_board` (`training.py:42`) sorteia com `torch.Generator().manual_seed(42)` sobre `len(dataset.entries)`. Quando o dataset cresce de 3.244 para 3.300 entradas, a permutação muda inteira: um tabuleiro que era validação passa a ser treino. Como `train_model` sempre retoma o checkpoint anterior (`training.py:85`), o modelo **já viu** os tabuleiros que hoje são validação. Métricas de validação e early stopping ficam contaminados de forma crescente e invisível. Não existe conjunto de teste.

**Solução.** Split determinístico e estável por **identidade da amostra**, não por índice:

```python
# src/chess_diagram_ocr/splits.py
Split = Literal["train", "val", "test"]

def assign_split(filename: str, *, val_pct: int = 10, test_pct: int = 10, salt: str = "cvoff-v1") -> Split:
    """Hash estável do nome do arquivo → bucket 0..99. Novas amostras não movem as antigas."""

def load_splits(path: Path) -> dict[str, Split]: ...
def save_splits(path: Path, splits: dict[str, Split]) -> None: ...
def ensure_splits(csv_path: Path, splits_path: Path) -> dict[str, Split]:
    """Atribui split a amostras novas; nunca altera as existentes."""
```

Arquivo `data/splits.csv` (`filename,split`) **versionado no git**. `BoardFenDataset` recebe `split: Split | None`. O conjunto de teste é reservado: nunca usado em treino nem em early stopping.

Para diagramas do mesmo livro, considerar agrupamento por livro de origem no futuro (evitar que páginas quase idênticas caiam em splits diferentes) — registrar a origem em `labels.csv` na migração da S-19 viabiliza isso.

**Critério de aceite.** Adicionar 100 amostras novas não muda o split de nenhuma amostra existente (teste automatizado). `data/splits.csv` cobre 100% das linhas de `labels.csv`.

---

## S-08 · Harness de avaliação e baseline honesto

**Problema.** `training._accuracy` (`training.py:30`) mede acurácia por casa. Com 76% de casas vazias, um modelo trivial marca 76%. A métrica que importa — quantos diagramas saem **sem nenhuma correção manual** — não é medida em lugar nenhum. Sem matriz de confusão, classes raras (`q`, `n`, `b`) são invisíveis. Não há baseline registrado.

**Solução.** CLI `cvoff-eval`:

```
cvoff-eval --split test [--model models/piece_classifier.pt] [--json out.json]
```

Métricas reportadas:

| Métrica | Definição |
|---|---|
| `square_accuracy` | casas corretas / total |
| **`board_exact_accuracy`** | tabuleiros com 64/64 corretas — **métrica primária** |
| `board_near_accuracy` | tabuleiros com ≤1 erro (mede custo de correção) |
| `per_class_recall` / `per_class_precision` | por classe de peça |
| `confusion_matrix` | 13×13 |
| `illegal_rate` | fração de predições fatalmente ilegais (S-05) |
| `calibration` | conf. média quando acerta vs quando erra; ECE |
| `confidence_auc` | AUC da confiança por casa como detector de erro (mede a S-10) |

Saída em tabela para terminal e JSON para comparação entre execuções. `docs/BASELINE.md` registra os números com data, commit, tamanho do dataset e split.

**Referência medida hoje (em dados de treino, portanto otimista — serve como teto, não como baseline):** `square_accuracy` 0,9996; `board_exact_accuracy` 0,976; conf. média 0,9991 acertando vs 0,8288 errando.

**Critério de aceite.** `cvoff-eval --split test` produz relatório completo; `docs/BASELINE.md` com o primeiro número honesto do projeto.

---

## S-09 · Cobertura de testes onde falta

**Problema.** 8 testes: 4 em `board_detection`, 4 em `pdf_to_pgn`. Zero em `fen_utils` (onde está o bug da S-05), `dataset`, `training`, `inference`, `model`. `test_detect_boards_still_finds_real_sample` (`tests/test_board_detection.py:33`) usa `next(glob("*.png"))` — depende da ordem do sistema de arquivos, não de um fixture fixo.

**Solução.**

- Migrar para `pytest` (mantendo compatibilidade com `unittest`, já que os testes existentes passam).
- `tests/fixtures/`: 4 a 6 páginas PDF pequenas construídas para teste (ou recortes com licença clara) + FENs esperados em `expected.json`. Pequenas o bastante para versionar (< 2 MB no total).
- Novos módulos de teste: `test_fen_utils.py` (tabela de legalidade), `test_dataset.py` (rótulo ilegal rejeitado, cache, dedupe), `test_splits.py` (estabilidade sob crescimento), `test_inference.py` (formato da distribuição por casa), `test_constrained_decode.py` (S-11), `test_pdf_text.py` (S-16).
- `test_regression_accuracy.py`: roda o pipeline nos fixtures e falha se `board_exact_accuracy` cair abaixo do valor gravado em `tests/fixtures/baseline.json`, com tolerância declarada.
- Substituir o `glob` frágil por caminho de fixture explícito.

**Critério de aceite.** `pytest` verde; cobertura de `src/chess_diagram_ocr/` acima de 70%; teste de regressão detecta uma piora deliberada de acurácia.

---

# Fase 2 — Precisão do OCR

## S-10 · Confiança por casa em vez de média

**Problema.** `inference.predict_fen_from_board` (`inference.py:55`) retorna `conf.mean()` sobre as 64 casas. Como ~76% são vazias e triviais, a média é dominada por elas. Medido: quando o modelo erra uma casa, a confiança **daquela casa** é ~0,83, mas a média do tabuleiro fica ~0,97 — indistinguível de um tabuleiro perfeito. Saída real com posição ilegal (dois reis brancos) reportou confiança 0,972.

**Solução.** Novo retorno estruturado, mantendo a função antiga como wrapper fino para não quebrar chamadores:

```python
@dataclass(frozen=True)
class BoardPrediction:
    probs: np.ndarray              # (64, 13) — a informação que hoje é jogada fora
    class_indices: list[int]       # argmax por casa
    fen_board: str
    mean_confidence: float
    min_confidence: float          # sinal útil de verdade
    mean_entropy: float
    uncertain_squares: list[int]   # casas abaixo do limiar, ordenadas por confiança
    position: PositionCheck        # S-05

def predict_board(board_rgb, model, device, *, rotate_180: bool = False) -> BoardPrediction: ...
```

Propagar `min_confidence` e `position.is_legal` para `DiagramPosition` (`pdf_to_pgn.py:18`) e para os headers do PGN. Substituir `torch.no_grad()` por `torch.inference_mode()`.

**Critério de aceite.** `confidence_auc` da S-08 usando `min_confidence` supera materialmente a de `mean_confidence` — medido, não presumido. UI exibe as duas.

---

## S-11 · Decodificação com restrições de legalidade

**Problema.** A decodificação é argmax independente por casa: `fen_from_class_indices(pred.max(dim=1))`. Nada impede o resultado de violar as regras do xadrez. Casos reais medidos no `1937 Kemeri.pdf`:

```
pg24  8/Q3N3/1P1r4/8/5kr1/8/6P1/8      NO_WHITE_KING   ← correto é K em a7
pg24  8/8/8/3R4/8/3K4/nQ2p2b/1K6       NO_BLACK_KING   ← correto é k em b1
pg25  1r1k4/3b2R1/p1n1pN2/P2pP3/...    NO_WHITE_KING
```

Em fonte figurina alemã, K e Q se confundem sistematicamente. A informação para corrigir **já está nas probabilidades** — só está sendo descartada pelo argmax.

**Solução.** Decodificação como otimização restrita sobre a matriz `probs` (64×13) da S-10.

```python
# src/chess_diagram_ocr/decode.py

@dataclass(frozen=True)
class DecodeResult:
    class_indices: list[int]
    fen_board: str
    log_prob: float
    changed_squares: list[tuple[int, int, int]]   # (casa, classe_argmax, classe_final)
    constraints_satisfied: bool

def decode_constrained(probs: np.ndarray, *, max_changes: int = 6) -> DecodeResult: ...
```

Restrições impostas (todas verificáveis sem saber o lado a jogar):

1. Exatamente um `K` e exatamente um `k`.
2. Nenhum peão (`P`/`p`) na 1ª ou 8ª fila.
3. `P` ≤ 8, `p` ≤ 8.
4. Total de peças brancas ≤ 16, pretas ≤ 16.
5. `P + N + B + R + Q ≤ 15` por cor (e coerência com promoções: `peões + excedente de peças ≤ 8`).

Algoritmo — busca em melhor-primeiro sobre trocas de menor custo, que é suficiente e barato para 64 casas:

```
1. Começar do argmax. Se satisfaz tudo, retornar.
2. Para cada restrição violada, gerar candidatos de reparo:
   - falta rei: para cada casa, custo = log p(casa=K) - log p(casa=argmax).
     Escolher a casa de menor custo (tipicamente a que o modelo leu como Q).
   - reis demais: reclassificar o rei excedente para a 2ª classe mais provável.
   - peão na fila inválida / peões demais: reclassificar para a 2ª classe mais provável.
3. Busca A* limitada: heap de estados, custo = soma dos deltas de log-prob,
   limite de `max_changes` trocas e de 5.000 estados expandidos.
4. Se nada satisfizer, devolver o melhor estado parcial com constraints_satisfied=False.
```

Registrar `changed_squares` — é ouro para diagnóstico e para a fila de revisão (S-22).

**Critério de aceite.** Nos três casos medidos acima, a decodificação restrita produz a posição legal correta. `illegal_rate` (S-08) cai a ~0 no conjunto de teste. `board_exact_accuracy` não regride — se regredir em algum caso, `max_changes` está alto demais e deve ser calibrado por medição.

**Testes.** Matriz `probs` sintética em que o argmax viola cada restrição, com a correção esperada; teste de que uma posição já legal passa intacta (`changed_squares == []`).

---

## S-12 · Detecção híbrida: imagem embutida + contorno

**Problema.** `detect_boards` (`board_detection.py:273`) usa exclusivamente contornos com heurísticas afinadas à mão (`_contour_geometry_score`, `_board_pattern_score`, `_periodic_peak_score`). Isso ignora que os PDFs **já contêm o diagrama como imagem embutida com bounding box exato**. Medido:

| Livro | Diagramas por página | Dimensão | Observação |
|---|---|---|---|
| `1937 Kemeri.pdf` | 1–2 | 590×590 | + 1 scan de fundo 1633×2468 a ignorar |
| `AAGAARD - Practical Chess Defence.pdf` | 2–3 | 616×616 | às vezes 620×704 (inclui legenda) |
| `1001 Winning Chess Sacrifices` | 1 | 350×350 | |

Falsos positivos do contorno também foram medidos: página 40 do Kemeri produz um "tabuleiro" que rende `8/8/8/8/8/8/8/8` com confiança 0,891.

Ponto crítico apurado na medição: **nenhum dos dois caminhos domina o outro.** A imagem embutida às vezes traz moldura/legenda e desloca a grade (Aagaard pg21, 620×704 → `TOO_MANY_KINGS`); o contorno às vezes recorta o retângulo errado. Mas quando discordam, a legalidade desempata corretamente em todos os casos observados.

**Solução.** Detector de duas fontes com arbitragem.

```python
# src/chess_diagram_ocr/detection/embedded.py
@dataclass(frozen=True)
class DiagramCandidate:
    board_rgb: np.ndarray
    bbox_pdf: tuple[float, float, float, float]   # coordenadas do PDF, para associar texto (S-16)
    source: Literal["embedded", "contour"]
    detector_score: float
    native_size: tuple[int, int]

def candidates_from_embedded_images(page: fitz.Page, *, min_side: int = 120,
                                   aspect_tolerance: float = 0.20) -> list[DiagramCandidate]: ...
def trim_to_grid(image_rgb: np.ndarray) -> tuple[np.ndarray, bool]: ...

# src/chess_diagram_ocr/detection/hybrid.py
def detect_diagrams(page: fitz.Page, page_rgb: np.ndarray, *, max_boards: int = 8,
                    reading_order: ReadingOrder = "column") -> list[DiagramCandidate]: ...
```

`candidates_from_embedded_images`: filtra por lado mínimo e aspecto próximo de 1, e descarta imagens que cobrem >70% da página (o scan de fundo do Kemeri).

`trim_to_grid` resolve o problema da moldura/legenda: detecta as 9 linhas de grade por projeção de gradiente (a mesma ideia já presente em `_periodic_peak_score`) e recorta exatamente na borda do tabuleiro. Retorna `(imagem, confiou_no_recorte)`.

`detect_diagrams`: gera candidatos das duas fontes, funde por IoU > 0,5, e para pares em conflito produz **as duas leituras**, deixando a arbitragem para o classificador + legalidade:

```
para cada grupo de candidatos sobrepostos:
    predizer FEN de cada variante (embutida-recortada, contorno)
    se exatamente uma é legal          → escolher essa
    se ambas legais e FEN idêntica     → escolher a de maior resolução nativa
    se ambas legais e FEN diferente    → escolher maior min_confidence, marcar needs_review
    se nenhuma legal                   → aplicar S-11 nas duas, escolher a de maior log-prob
```

A concordância entre as duas fontes é um sinal de confiança **muito melhor** que o softmax, e sai de graça.

Vantagem adicional medida: a imagem embutida do Kemeri é 590×590 nativo contra ~430 px do render a 220 DPI. Mais resolução por casa sem aumentar o DPI da página.

**Critério de aceite.** Nos 27 PDFs: número de diagramas detectados ≥ o atual; zero detecções que rendam posição vazia; falso positivo da página 40 do Kemeri eliminado; `board_exact_accuracy` melhora no conjunto de teste.

**Testes.** Fixture com PDF de imagem embutida + PDF sem imagem embutida (só vetorial/scan) para garantir o fallback para contorno.

---

## S-13 · Auto-orientação do diagrama

**Problema.** `rotate_180` é um checkbox global (`app_tkinter.py:106`, `--rotate-180` nos CLIs) aplicado a todos os diagramas de uma vez. Se um livro mistura orientações (diagramas do ponto de vista das pretas), não há solução — e o usuário precisa saber de antemão qual usar.

**Solução.** Decidir por diagrama, testando as duas orientações e escolhendo por plausibilidade:

```python
def predict_with_orientation(board_rgb, model, device, *,
                             mode: Literal["auto", "0", "180"] = "auto") -> tuple[BoardPrediction, int]: ...
```

Pontuação de plausibilidade para desempate (em ordem de peso):

1. Posição legal (S-05) — critério dominante.
2. `min_confidence` da S-10.
3. Prior estrutural: peões brancos concentrados nas filas baixas e peões pretos nas altas; reis mais provavelmente na 1ª/8ª fila do próprio lado. Peso pequeno, só desempate.

Se as duas orientações forem legais e a diferença de score for menor que uma margem, marcar `needs_review` em vez de escolher silenciosamente.

Melhoria complementar de baixo custo: quando o diagrama tem legendas de coordenada visíveis (Aagaard tem), a orientação sai da leitura das coordenadas — mas isso requer OCR de texto, então fica como opção futura.

**Critério de aceite.** Com `mode="auto"`, acurácia em conjunto de teste rotacionado artificialmente em 180° iguala a do conjunto original. O checkbox global passa a ser tri-estado (auto / 0° / 180°) com `auto` como padrão.

---

## S-14 · Ordenação de leitura unificada

**Problema.** `detect_boards` tem `reading_order: ReadingOrder = "row"` como padrão (`board_detection.py:278`), mas `pdf_to_pgn.scan_pdf_positions` passa `"column"` (`pdf_to_pgn.py:58`). Os frontends chamam sem o parâmetro, ficando em `"row"`. Numa página de duas colunas, o "diagrama 2" da GUI não é o "diagrama 2" do PGN — o header `[Diagram "2"]` aponta para outra posição, quebrando a rastreabilidade justamente quando o usuário quer conferir uma correção.

**Solução.** Um único padrão (`"column"`, que é o correto para a maioria dos livros de xadrez em duas colunas) definido em `config.py` como `DEFAULT_READING_ORDER`. Expor como configuração na GUI e como `--reading-order` em todos os CLIs, com o mesmo valor efetivo. Registrar a ordem usada no header PGN (`[ReadingOrder "column"]`) para que um PGN antigo continue interpretável.

**Critério de aceite.** Mesma página processada pela GUI e por `cvoff-export` produz a mesma numeração de diagramas — teste automatizado que compara as duas rotas.

---

## S-15 · Gate de qualidade na exportação

**Problema.** `save_pdf_positions_to_pgn` (`pdf_to_pgn.py:141`) escreve tudo que sair do modelo, incluindo posições ilegais e falsos positivos. O usuário só descobre abrindo o PGN num visualizador que reclama.

**Solução.** Classificar cada posição na exportação e separar as saídas:

```python
@dataclass(frozen=True)
class ExportReport:
    accepted: list[DiagramPosition]
    needs_review: list[DiagramPosition]
    rejected: list[tuple[DiagramPosition, str]]
    pages_scanned: int
    output_path: Path
    review_path: Path | None
```

Regras:

- **Aceito**: posição legal (após S-11) e `min_confidence ≥ limiar_aceite` (padrão 0,80, calibrado pela S-28).
- **Revisar**: legal mas com baixa confiança, ou fontes de detecção discordantes (S-12), ou orientação ambígua (S-13) → `<nome>.review.pgn`, com header `[Review "low-confidence"]` explicando o motivo.
- **Rejeitado**: ilegal mesmo após decodificação restrita, ou tabuleiro vazio → não vai para PGN; entra no relatório.

Headers adicionais em todas as posições: `[MinSquareConfidence]`, `[DetectionSource]`, `[LegalityStatus]`.

Resumo impresso ao fim: `312 aceitos, 18 para revisão, 4 rejeitados em 289 páginas`.

**Critério de aceite.** Exportar os 27 PDFs: `*.pgn` sem nenhuma posição ilegal; tudo que foi excluído aparece no relatório ou no `*.review.pgn` — nada desaparece em silêncio.

---

# Fase 3 — Semântica

## S-16 · Lado a jogar e metadados a partir do texto do PDF

**Problema.** Medido: **0 dos 3.244 rótulos** têm lado a jogar preto, e `_normalize_fen` (`fen_utils.py:10`) completa toda FEN com `w - - 0 1` fixo. Num livro de táticas, ~50% dos exercícios são "pretas jogam" — hoje **todos** saem como brancas. Os 51 rótulos `OPPOSITE_CHECK` são a assinatura disso.

E a informação está disponível: os PDFs têm camada de texto real. Medido no Aagaard pg20: `"The Defensive Thinking Frame / 23 / Hickl - Yusupov / Bremen 1998 / In thi..."` — jogadores, evento, ano e número do exercício, todos ao lado do diagrama.

**Solução.**

```python
# src/chess_diagram_ocr/pdf_text.py

@dataclass(frozen=True)
class DiagramContext:
    caption: str                       # texto associado, já limpo
    side_to_move: chess.Color | None
    side_to_move_source: Literal["text", "legality", "default"]
    exercise_number: int | None
    players: tuple[str, str] | None
    event: str | None
    year: int | None

def blocks_near(page: fitz.Page, bbox: tuple[float, float, float, float],
                *, radius_pt: float = 60.0) -> list[str]:
    """Blocos de texto próximos ao diagrama, ordenados por distância. Prioriza abaixo do bbox."""

def parse_context(caption: str) -> DiagramContext: ...
```

Padrões de lado a jogar, multilíngue (os livros do repositório estão em inglês, português e alemão):

```
pt:  "brancas jogam", "pretas jogam", "brancas a jogar", "vez das pretas", "as negras jogam"
en:  "white to move", "black to move", "white to play", "black plays", "white wins"
de:  "weiß am zug", "schwarz am zug", "weiß zieht", "schwarz zieht"
símbolos: ◻ □ ⬜ (brancas) · ◼ ■ ⬛ (pretas)
```

Normalizar removendo acentos e caixa antes de casar; ancorar os padrões para não casar "white" no meio de um nome de jogador.

Número do exercício: buscar inteiro isolado próximo ao diagrama, distinguindo do número de página (que aparece na margem, fora do raio). Jogadores: padrão `Nome - Nome` com evento/ano na linha seguinte.

Nota apurada na medição: o `1001 Winning Chess Sacrifices` tem camada de texto só com o número de página (`nblocks=1`). Para livros assim, a extração de contexto falha e o fallback da S-17 é o que sobra. O código deve degradar de forma limpa, nunca inventar.

**Critério de aceite.** Em amostra manual de 50 exercícios do Aagaard e 50 do `400 Quebra-cabeças`, lado a jogar correto em ≥95% dos casos em que existe texto; número do exercício correto em ≥90%.

**Testes.** Tabela de legendas nos três idiomas, incluindo casos-armadilha ("White won the game" não é indicação de lado a jogar; "Black to move and win" é).

---

## S-17 · Inferência de lado a jogar e roque por legalidade

**Problema.** Quando não há texto (caso do `1001 Winning Chess Sacrifices`, verificado), não há como saber o lado a jogar. Mas a própria posição frequentemente responde.

**Solução.** Cascata de decisão, com a fonte sempre registrada:

```python
def infer_side_to_move(board_placement: str, ctx: DiagramContext | None) -> tuple[chess.Color, str]:
    """1. texto (S-16) → 2. legalidade → 3. heurística → 4. padrão (brancas), sinalizado."""
```

Regra de legalidade — decisiva e barata: se com `w` as pretas estão em xeque (`OPPOSITE_CHECK`), então **é a vez das pretas**, porque o lado que não joga não pode estar em xeque. Isso explica e resolve os 51 rótulos afetados do dataset atual. Se ambos os lados aparecem em xeque, a posição está errada — sinalizar para revisão.

Heurística fraca (só quando as duas orientações são legais): num livro de táticas, o lado com material a ganhar/ameaça imediata costuma ser o que joga. Requer motor — deixar para a S-33 e não usar por padrão.

Direitos de roque: derivar da posição — `K` em e1 com `R` em h1 → `K` disponível; e assim para os quatro casos. Conservador por natureza (a posição não diz se as peças já se moveram), mas melhor que `-` sempre: em posições de meio-jogo com reis já castelados o resultado é correto, e em finais é irrelevante. Registrar em `[CastlingSource "inferred"]`.

**Critério de aceite.** Aplicado ao dataset atual, os 51 `OPPOSITE_CHECK` passam todos a legais com lado a jogar preto. Nenhuma posição legal é alterada.

---

## S-18 · PGN enriquecido e deduplicado

**Problema.** `build_pgn_games` (`pdf_to_pgn.py:100`) emite headers fixos: `White "?"`, `Black "?"`, `Round "pagina.diagrama"`. Toda a semântica do exercício é perdida. Diagramas repetidos entre páginas (comum: enunciado e solução) geram jogos duplicados.

**Solução.** Preencher com o contexto da S-16 quando disponível, mantendo os padrões quando não:

```
[Event "Bremen 1998"]              ← extraído, senão o --event
[White "Hickl"] [Black "Yusupov"]  ← extraído, senão "?"
[Date "1998.??.??"]                ← extraído
[FEN "... b - - 0 1"]              ← com lado a jogar da S-16/S-17
[SetUp "1"]
[Annotator "ChessVisionOFF"]
[SourcePDF "..."] [Page "24"] [Diagram "1"]
[ExerciseNumber "23"]              ← novo
[SideToMoveSource "text"]          ← novo, rastreabilidade
[MinSquareConfidence "0.912"]      ← novo (S-10)
[DetectionSource "embedded"]       ← novo (S-12)
[LegalityStatus "ok"]              ← novo (S-05)
[Caption "In this position Black must find..."]   ← novo, comentário do exercício
```

Deduplicação: agrupar posições com a mesma placement de peças dentro do mesmo PDF; manter a primeira ocorrência e adicionar `[DuplicateOf "página.diagrama"]` nas demais, ou omiti-las sob `--dedupe`. Cuidado: a mesma posição pode legitimamente aparecer em exercícios diferentes — por isso o padrão é anotar, não remover.

Extensão possível (não obrigatória): quando o texto da solução for extraível, converter os lances SAN em movimentos reais do PGN, transformando o arquivo de "lista de posições" em "exercícios com solução". Alto valor, mas depende de parsing de notação com muitas variações tipográficas — tratar como item exploratório separado.

**Critério de aceite.** PGN do Aagaard com nomes de jogadores e números de exercício preenchidos; PGN importável no SCID/ChessBase sem avisos.

---

## S-19 · Esquema do dataset com lado a jogar e origem

**Problema.** `labels.csv` tem só `filename,fen`. Não registra o lado a jogar (perdido, S-16), nem de que PDF/página a amostra veio — o que impede agrupamento por livro no split (S-07), auditoria por fonte, e re-recorte a partir do original.

**Solução.** Esquema estendido, com leitura compatível com o antigo:

```csv
filename,fen,side_to_move,source_pdf,source_page,source_diagram,detection_source,created_at,corrected_by
```

`dataset.BoardFenDataset` aceita CSV antigo (colunas ausentes → valores padrão) para não quebrar os 3.244 rótulos existentes. `append_training_sample` passa a receber os campos novos. Script `tools/migrate_labels.py` que preenche o que é inferível (`side_to_move` pela regra da S-17) e deixa o resto vazio, com backup.

**Critério de aceite.** CSV antigo carrega sem erro; CSV novo carrega; após a migração, os 51 casos `OPPOSITE_CHECK` têm `side_to_move=b`.

---

# Fase 4 — Produtividade humana

## S-20 · Editor de posição por clique

**Problema.** Corrigir um diagrama hoje significa editar uma string FEN em `ttk.Entry` (`app_tkinter.py:251`). Para um erro de uma peça, o usuário precisa contar casas e reescrever a linha. É o gargalo de tempo do projeto — e é irônico, porque o app **já tem** um editor de tabuleiro com arraste funcionando na aba "Análise" (`on_study_board_press`/`_drag`/`_release`, linhas 1742–1787).

**Solução.** Extrair o widget de tabuleiro interativo do painel de estudo para um componente reutilizável e usá-lo no painel de resultado, em modo de **edição de posição** (não de lances legais):

```python
# src/chess_diagram_ocr/ui/board_widget.py
class InteractiveBoard:
    def __init__(self, parent, *, mode: Literal["play", "edit"], on_change: Callable[[str], None]): ...
    def set_position(self, fen: str) -> None: ...
    def set_uncertainty(self, per_square_conf: Sequence[float]) -> None: ...   # S-21
```

Em `mode="edit"`: clique em peça seleciona, clique em casa move sem validar legalidade; botão direito remove; paleta lateral de 12 peças para inserir; a FEN é atualizada a cada mudança e o campo de texto continua funcionando como entrada alternativa.

Atalhos para o ciclo de correção: `←`/`→` diagrama anterior/próximo, `Ctrl+S` salvar amostra, `Ctrl+Shift+S` salvar todos, `Ctrl+R` rodar OCR na página, `Del` remover peça selecionada.

**Critério de aceite.** Corrigir um erro de uma peça leva ≤3 ações de mouse (hoje: selecionar texto, contar casas, digitar). Medir tempo para 20 diagramas antes/depois; alvo ≥50% de redução.

---

## S-21 · Heatmap de incerteza e painel de legalidade

**Problema.** O usuário não tem ideia de onde o modelo está inseguro. Com a média de confiança em 0,97 mesmo havendo erro (S-10), a única forma de encontrar o erro é comparar as 64 casas visualmente com o PDF.

**Solução.** Usando `BoardPrediction.probs` da S-10:

- **Heatmap**: casas com confiança abaixo do limiar recebem borda/sombra graduada (amarelo → vermelho). Toggle para ligar/desligar.
- **Tooltip por casa**: passar o mouse mostra as 3 classes mais prováveis com percentuais — o usuário vê que a casa lida como `Q` tinha 42% de `K`.
- **Casas alteradas pela S-11**: marcação distinta (contorno azul), com o motivo ("ajustado para satisfazer: exatamente um rei branco").
- **Painel de legalidade**: `PositionCheck.problems` em pt-BR claro — "falta o rei preto", "há peão na primeira fila" — em vez de `Status.NO_BLACK_KING`.

**Critério de aceite.** Num diagrama com um erro conhecido, a casa errada está entre as três mais destacadas do heatmap em ≥80% dos casos de teste.

---

## S-22 · Fila de revisão por aprendizado ativo

**Problema.** O fluxo é página por página, manual. O usuário não tem como saber quais diagramas do livro merecem atenção — e o valor de cada correção é muito desigual: corrigir um diagrama que o modelo já acerta com 0,999 não ensina nada.

**Solução.** Varredura em lote que produz uma fila ordenada por valor de informação:

```python
@dataclass(frozen=True)
class ReviewItem:
    pdf_path: Path
    page_index: int
    diagram_index: int
    board_rgb_ref: str          # caminho do cache, não a imagem em memória
    prediction: BoardPrediction
    priority: float
    reasons: tuple[str, ...]    # "ilegal", "confiança baixa", "fontes discordantes", "orientação ambígua"
```

Prioridade: ilegal após S-11 > fontes de detecção discordantes (S-12) > `min_confidence` baixa > entropia média alta > classe rara presente. Fila persistida em `data/review_queue.json` para sobreviver ao fechamento do app. UI: lista navegável com miniatura, motivo e ação "corrigir agora" que abre o editor da S-20 já na casa suspeita.

Isto muda o loop de "varrer o livro inteiro" para "corrigir os 30 diagramas que importam" — em 289 páginas de Kemeri com ~1,5 diagramas/página, é a diferença entre 430 revisões e ~30.

**Critério de aceite.** Após varredura de um livro completo, os itens do topo da fila têm taxa de erro real materialmente maior que a média — validado corrigindo os 20 primeiros e os 20 aleatórios e comparando.

---

## S-23 · Navegador e editor do dataset

**Problema.** `labels.csv` é append-only. Não existe forma de listar, filtrar, recorrigir ou remover uma amostra. Os 100 rótulos ilegais medidos só podem ser consertados editando CSV na mão. Também não há visão da distribuição de classes.

**Solução.** Nova aba "Dataset" no Tkinter:

- Tabela paginada: miniatura, FEN, status de legalidade, lado a jogar, PDF/página de origem, data.
- Filtros: só ilegais, só duplicatas, por classe presente, por livro de origem, por split.
- Ações: abrir no editor da S-20 e regravar; remover amostra (imagem + linha); mover para quarentena; re-rodar OCR na amostra e comparar com o rótulo (encontra rótulos humanos errados).
- Painel de estatísticas: contagem por classe, por split, por livro; alerta de desbalanceamento.

**Critério de aceite.** Corrigir os 100 rótulos ilegais inteiramente pela UI, sem tocar no CSV.

---

## S-24 · Exportação cancelável e retomável

**Problema.** `_export_pdf_to_pgn_worker` (`app_tkinter.py:897`) roda até o fim sem cancelamento. Num livro de 1.121 páginas (`1001 Winning Chess Sacrifices` tem 1.121), a única forma de parar é fechar o app e perder o progresso.

**Solução.** `threading.Event` de cancelamento propagado por `scan_pdf_positions` (checado a cada página), botão "Cancelar" na UI, e checkpoint incremental: gravar as posições encontradas em `<saida>.partial.jsonl` a cada N páginas. Ao reiniciar a mesma exportação, detectar o parcial e oferecer retomar da última página concluída.

Aproveitar para paralelizar: render de página e detecção são independentes entre páginas e liberam o GIL parcialmente (PyMuPDF e OpenCV). Um `ThreadPoolExecutor` de 2 a 4 workers para render+detecção, com inferência serializada no modelo. Medir antes de assumir ganho — o pipeline já roda a 0,18 s/página.

**Critério de aceite.** Cancelar no meio de um livro de 1.121 páginas responde em <2 s e preserva o parcial; retomar produz o mesmo PGN que uma execução sem interrupção.

---

## S-25 · Persistência de estado robusta

**Problema.** `_save_app_state` (`app_tkinter.py:467`) faz read-modify-write sem atomicidade: interrupção no meio corrompe `data/app_tkinter_state.json`. `_load_app_state` retorna `False` silenciosamente em qualquer erro (`app_tkinter.py:464`), então o usuário perde o último PDF/página sem entender por quê. `load_pdf` relê o mesmo arquivo de estado por conta própria (`app_tkinter.py:833`), duplicando a lógica.

**Solução.** Módulo `src/chess_diagram_ocr/ui/state.py` com dataclass tipada, escrita atômica (`tempfile` no mesmo diretório + `os.replace`), versionamento do esquema (`{"version": 1, ...}`) com migração, e log em nível `warning` quando o estado é descartado. Uma única fonte de leitura/escrita, consumida por `load_pdf`.

**Critério de aceite.** Matar o processo durante a gravação não corrompe o arquivo (teste com escrita repetida + kill). Estado inválido gera aviso no log, não silêncio.

---

# Fase 5 — Modelo e desempenho

## S-26 · Cache do dataset limitado e carregamento paralelo

**Problema.** `BoardFenDataset._board_cache` (`dataset.py:37`) guarda cada tabuleiro como array 800×800×3 e nunca libera. Como `index_map` percorre as 64 casas de cada tabuleiro, uma época carrega todos: **3.244 × 800 × 800 × 3 = 5,80 GiB** (aritmética sobre a contagem real de entradas). Cresce linearmente com o dataset — que é feito para crescer. `DataLoader` roda com `num_workers=0`, serializando decode PNG + `cvtColor` + `resize` com o passo de otimização.

**Solução.**

1. `functools.lru_cache` (ou `OrderedDict` com limite) de tamanho configurável — padrão 256 tabuleiros (~470 MiB). Parâmetro `cache_size` no construtor; `0` desliga.
2. Amostrador que agrupa as 64 casas do mesmo tabuleiro no mesmo lote, transformando o acesso aleatório em quase sequencial — o cache pequeno passa a ter taxa de acerto alta.
3. `num_workers` configurável (padrão `min(4, os.cpu_count()//2)`), com `persistent_workers=True`. Atenção: cache por processo, então o item 2 é o que faz isso funcionar.
4. ~~Armazenar amostras em resolução reduzida.~~ **Descartado por decisão do projeto (2026-07-25):** as amostras permanecem em 800×800 para preservar resolução caso o modelo passe a usar entrada maior que 64 px por casa (ver S-29). O ganho de RAM vem inteiramente dos itens 1 e 2; o custo é 2,7 GB de disco que seguem sem cópia remota.

**Critério de aceite.** Época completa em <2 GiB de RSS, medido. Tempo por época igual ou melhor.

---

## S-27 · Treino reprodutível e métricas corretas

**Problema.** Três defeitos em `training.py`:

1. Retoma sempre o checkpoint existente (`training.py:85`) sem opção de treinar do zero, com `strict=False` — pesos incompatíveis são descartados em silêncio se a arquitetura mudar.
2. Split re-sorteado a cada execução (ver S-07): validação contaminada de forma crescente.
3. `_accuracy` (`training.py:30`) mede acurácia por casa, dominada pelos 76% de casas vazias; sem métrica por tabuleiro, sem métrica por classe, sem peso de classe para o desbalanceamento (classes `q`/`n`/`b` têm ~1% da frequência de `empty`).

**Solução.**

```python
def train_model(csv_path, samples_dir, model_path, *, epochs=5, batch_size=128, lr=1e-3,
                fresh: bool = False,              # ignora checkpoint existente
                class_weights: Literal["none", "balanced"] = "balanced",
                seed: int = 42, cache_size: int = 256, num_workers: int | None = None,
                progress_cb=None) -> TrainingRun: ...
```

- `fresh=True` → não carrega checkpoint. `strict=True` sempre: incompatibilidade de arquitetura deve **falhar alto**.
- Split via `splits.py` (S-07), estável.
- Checkpoint grava metadados: `{"model_state", "arch_version", "class_names", "seed", "split_hash", "dataset_size", "metrics", "timestamp", "git_commit"}`. `load_model` valida `class_names` e `arch_version` e recusa incompatível.
- Métricas por época: `train_loss`, `train_square_acc`, `val_square_acc`, **`val_board_exact_acc`** (a que importa), `val_per_class_recall`. Early stopping em `val_board_exact_acc`, não em `val_loss`.
- `CrossEntropyLoss(weight=...)` com pesos inversos à frequência quando `class_weights="balanced"`.
- Mensagem de early stopping em pt-BR via `logging`.

**Critério de aceite.** Duas execuções com a mesma semente e mesmo dataset produzem métricas idênticas. Checkpoint de arquitetura antiga é rejeitado com mensagem clara. `val_board_exact_acc` aparece no histórico.

---

## S-28 · Calibração de confiança

**Problema.** Medido: confiança 0,9991 quando acerta, 0,8288 quando erra — separação existe, mas a escala não é interpretável como probabilidade. Os limiares da S-15 e S-22 dependem disso para não serem arbitrários.

**Solução.** Temperature scaling: aprender um único escalar `T` no conjunto de validação minimizando NLL, gravado no checkpoint e aplicado no `softmax` da inferência. Reportar ECE antes e depois na S-08. Com `T` calibrado, "confiança 0,90" passa a significar de fato ~90% de acerto, e os limiares deixam de ser palpite.

**Critério de aceite.** ECE no conjunto de teste abaixo de 0,05. Limiares da S-15 derivados da curva de calibração, com o número documentado.

---

## S-29 · Experimentos de arquitetura e TTA

**Problema.** `PieceClassifier` (`model.py:11`) converte para cinza (`preprocess_cell_to_tensor:42`) e usa 64×64. Nenhuma dessas escolhas foi medida contra alternativas. A camada `Linear(128*8*8, 256)` concentra 2,1 M dos 2,19 M parâmetros — muito para a tarefa.

**Importante:** a análise mostra que o classificador **não é** o gargalo atual (99,96% em dados vistos; os erros vêm de recorte, restrições e semântica). Este item é de baixa prioridade e deve ser conduzido como experimento medido, não como refatoração especulativa.

**Solução.** Grade de experimentos com o harness da S-08, um fator por vez, decidindo por número:

| Fator | Variantes |
|---|---|
| Canais | cinza (atual) vs RGB (importa em livros com diagramas coloridos) |
| Resolução | 32 vs 48 vs 64 px |
| Cabeça | `Linear(8192,256)` atual vs `GlobalAvgPool + Linear(128,13)` (~150 k params) |
| Backbone | CNN atual vs MobileNetV3-Small pré-treinada |
| Aumento de dados | atual vs + ruído de compressão JPEG + simulação de meio-tom de scan |

TTA leve: predizer com deslocamentos de ±2 px e escalas 0,98/1,02, somar as probabilidades. Isso combina bem com a S-11 (probabilidades mais estáveis → decodificação restrita melhor) e com a S-12 (mais um sinal de concordância). Custo: ~5× inferência, que a 50 ms/tabuleiro continua irrelevante.

**Critério de aceite.** Cada fator com resultado registrado em `docs/EXPERIMENTS.md` — inclusive os que não ajudaram. Mudança de arquitetura só entra se melhorar `board_exact_accuracy` no conjunto de teste além do ruído medido.

---

## S-30 · Aceleração: CUDA e ONNX

**Problema.** torch instalado é `2.10.0+cpu` (verificado) — sem CUDA. Treino e inferência presos à CPU mesmo havendo GPU na máquina.

**Solução.** Documentar a instalação da wheel CUDA correspondente e detectar/reportar o dispositivo em uso na inicialização (hoje `load_model` decide em silêncio). Exportação ONNX opcional (`cvoff-export-onnx`) com ONNX Runtime como backend alternativo — em CPU costuma render 2–4× sobre torch eager, o que importa para o modo interativo e para máquinas sem GPU. Quantização int8 como opção para a distribuição empacotada (S-36).

**Critério de aceite.** Barra de status/log informa `cuda:0` ou `cpu` explicitamente. Se ONNX for adotado, saída idêntica ao torch em tolerância de 1e-4 sobre o conjunto de teste.

---

# Fase 6 — Consolidação

## S-31 · Camada de serviço e decomposição da UI

**Problema.** `app_tkinter._detect_and_predict_items` (linha 1071) e `app_streamlit.run_ocr_for_boards` (linha 63) implementam o mesmo fluxo de forma independente; `save_current`/`save_all` também estão duplicados. O Streamlit já divergiu: não tem "Corrigir Net", seleção de área nem aba de análise. Cada melhoria de precisão precisa ser aplicada duas vezes.

`ChessOcrTkApp` tem 2.137 linhas e ~60 atributos de instância, misturando layout, estado de OCR, tabuleiro de estudo/PGN, orquestração de threads e persistência. Está legível, mas é intestável em unidade e é a causa da divergência entre frontends.

**Solução.** Camada de serviço sem nenhuma dependência de UI:

```python
# src/chess_diagram_ocr/service.py
class OcrService:
    def open_pdf(self, path: Path) -> PdfHandle: ...
    def render_page(self, handle: PdfHandle, page: int, dpi: int) -> np.ndarray: ...
    def recognize_page(self, handle, page, *, max_boards, options) -> list[RecognizedDiagram]: ...
    def recognize_image(self, image_rgb, *, max_boards, options) -> list[RecognizedDiagram]: ...
    def recognize_region(self, handle, page, bbox, *, options) -> list[RecognizedDiagram]: ...
    def save_sample(self, diagram: RecognizedDiagram, fen: str, side_to_move) -> Path: ...
    def export_pdf(self, handle, output, *, options, cancel: Event, progress) -> ExportReport: ...
    def train(self, *, options, progress) -> TrainingRun: ...
```

`RecognizedDiagram` carrega tudo que a UI precisa: imagem, quad/bbox, `BoardPrediction` (S-10), `DecodeResult` (S-11), `DiagramContext` (S-16), fonte de detecção (S-12).

Decomposição do Tkinter em `src/chess_diagram_ocr/ui/`: `board_widget.py` (S-20), `pdf_panel.py`, `result_panel.py`, `study_panel.py`, `dataset_panel.py` (S-23), `review_panel.py` (S-22), `training_dialog.py`, `state.py` (S-25), `strings.py` (S-04). `app_tkinter.py` fica sendo montagem e roteamento de eventos.

Corrigir também, no caminho: `reload_model()` é chamada da thread de treino (`app_tkinter.py:2110`) e zera `_model_cache` enquanto uma thread de OCR pode estar usando — o serviço deve serializar acesso ao modelo com um lock. E `_set_status` chama `root.update_idletasks()` dentro de callback de evento (`app_tkinter.py:500`), reentrando no loop de eventos: remover.

**Critério de aceite.** `app_tkinter.py` abaixo de 600 linhas; zero lógica de OCR fora de `src/`; Streamlit com paridade de funcionalidades; `OcrService` testável sem Tk.

---

## S-32 · "Corrigir Net" opt-in e configurável

**Problema.** `app_tkinter.py:54` fixa `NET_CORRECT_URL = "https://helpman.komtera.lt/predict"`. O botão faz upload da imagem do tabuleiro para um host de terceiro, sem opt-in, sem configuração e sem menção no README. É um serviço sem contrato, que pode sair do ar ou mudar de comportamento.

**Solução.** Desabilitado por padrão. Habilitar exige configuração explícita (`data/settings.json` ou variável de ambiente) com o endpoint declarado pelo usuário. Primeira utilização mostra diálogo dizendo com clareza que a imagem será enviada para `<host>`, com opção "não perguntar novamente". Documentar no README, incluindo que o recurso é opcional e o projeto funciona inteiramente offline sem ele. Timeout e mensagens de erro já existem (`_predict_fen_via_net`) e devem ser preservados.

Generalizar como provedor plugável: interface `RemoteFenProvider` para que outros serviços (ou um segundo modelo local) possam ser usados como segunda opinião, alimentando o sinal de concordância da S-12.

**Critério de aceite.** Sem configuração, o botão está desabilitado com tooltip explicativo. Nenhuma requisição de rede parte do app em uso padrão — verificável por teste.

---

## S-33 · Motor de análise opcional

**Problema.** A aba "Análise" permite navegar variantes e salvar PGN, mas não avalia nada. Para um livro de exercícios, a pergunta natural do usuário — "minha solução está certa?" — não tem resposta no app.

**Solução.** Integração opcional com Stockfish via `chess.engine.SimpleEngine` (a dependência `python-chess` já está no projeto, e o `Python-Easy-Chess-GUI-master` de referência mostra o padrão de uso). Caminho do binário configurável, recurso desabilitado se ausente. UI: avaliação em centipawns, melhor lance, barra de vantagem, análise em thread separada com profundidade/tempo configuráveis.

Ganho secundário relevante: a avaliação do motor é um **validador de plausibilidade** para o OCR. Numa posição de livro de táticas, se o motor não encontra nada e a avaliação é bizarra (ex.: +15 sem razão), a probabilidade de erro de reconhecimento é alta. Pode alimentar a prioridade da fila da S-22.

**Critério de aceite.** Sem Stockfish instalado, o app funciona normalmente com o recurso oculto. Com Stockfish, avaliação aparece em <2 s e não bloqueia a UI.

---

## S-34 · Processamento em lote de múltiplos PDFs

**Problema.** `cvoff-export` processa um PDF por vez. Há 27 livros no repositório e o `PDF/Andamento.txt` (arquivo de controle manual, mantido à mão) mostra que o acompanhamento de progresso por livro está sendo feito num txt.

**Solução.** `cvoff-batch`:

```
cvoff-batch PDF/ --output PGN/ [--skip-existing] [--workers 2] [--report batch_report.json]
```

Relatório consolidado por livro: páginas, diagramas aceitos/revisão/rejeitados, confiança média, tempo. Substitui o `Andamento.txt` manual por estado versionável. `--skip-existing` permite retomar a varredura da biblioteca inteira.

**Critério de aceite.** Processar os 27 PDFs numa execução, com relatório e sem perder progresso se um livro falhar.

---

## S-35 · Documentação

**Problema.** O README documenta comandos que não funcionam como escrito: `pip install -e .` não instala nada de útil (S-02) e `python -m unittest discover -s tests` falha com o Python do sistema (verificado: `ModuleNotFoundError: No module named 'numpy'` com Python 3.14.5). A seção "Estrutura" está desatualizada (não lista `pdf_to_pgn.py`, `webview2_panel.py`, `export_pdf_pgn.py`). Não há documentação do formato do `labels.csv`, do fluxo de retreino, nem de resolução de problemas.

**Solução.** README reescrito com: instalação verificada passo a passo, os comandos reais, o fluxo de trabalho recomendado com capturas de tela, formato dos dados, e seção de resolução de problemas (WebView2 ausente, torch sem CUDA, PDF sem camada de texto, PDF sem imagem embutida). Somar `CONTRIBUTING.md` (lint, tipos, testes, como adicionar amostras) e `docs/ARCHITECTURE.md` com o diagrama de fluxo. Manter `ANALISE.md`/`ROADMAP.md`/`SPEC.md` como o registro de decisões.

**Critério de aceite.** Alguém em máquina limpa segue o README e chega a um PGN exportado sem precisar ler código.

---

## S-36 · Empacotamento para Windows

**Problema.** Usar o programa exige Python 3.10, venv e `pip install`. O público natural (estudantes e treinadores de xadrez) não tem isso.

**Solução.** PyInstaller com `--onedir` (mais rápido e mais confiável que `--onefile` para torch). Pontos de atenção conhecidos: torch é grande (usar a build CPU ou ONNX Runtime da S-30 reduz muito o instalador); `assets/piece_images/` precisa entrar nos dados; o modelo `.pt` deve ser embutido ou baixado no primeiro uso; o `webview2_panel.py` depende de `pythonnet`/`clr` e do runtime WebView2, que precisa de detecção e mensagem clara quando ausente (já existe `EmbeddedWebView2.is_supported`, aproveitar).

**Critério de aceite.** Executável roda em Windows limpo (sem Python) e completa o fluxo: abrir PDF → OCR → corrigir → exportar PGN.

---

# Apêndice · Índice de referências cruzadas

| Item | Título | Fase | Depende de |
|---|---|---|---|
| S-01 | Repositório versionado e limpo | 0 | — |
| S-02 | Pacote instalável | 0 | S-01 |
| S-03 | Lint, tipos e CI | 0 | S-02 |
| S-04 | Logging e strings pt-BR | 0 | — |
| S-05 | Validação de legalidade real | 1 | — |
| S-06 | Auditoria e saneamento do dataset | 1 | S-05 |
| S-07 | Split persistido | 1 | — |
| S-08 | Harness de avaliação e baseline | 1 | S-05, S-07 |
| S-09 | Cobertura de testes | 1 | S-02 |
| S-10 | Confiança por casa | 2 | S-05 |
| S-11 | Decodificação com restrições | 2 | S-10 |
| S-12 | Detecção híbrida | 2 | S-10, S-11 |
| S-13 | Auto-orientação | 2 | S-10, S-11 |
| S-14 | Ordenação unificada | 2 | — |
| S-15 | Gate de exportação | 2 | S-10, S-11, S-12 |
| S-16 | Lado a jogar via texto | 3 | S-12 (bbox) |
| S-17 | Lado a jogar e roque por legalidade | 3 | S-05, S-16 |
| S-18 | PGN enriquecido | 3 | S-16, S-17 |
| S-19 | Esquema do dataset | 3 | S-06, S-17 |
| S-20 | Editor de posição por clique | 4 | S-31 (parcial) |
| S-21 | Heatmap e painel de legalidade | 4 | S-10, S-11, S-20 |
| S-22 | Fila de revisão (aprendizado ativo) | 4 | S-10, S-12, S-15 |
| S-23 | Navegador do dataset | 4 | S-06, S-19, S-20 |
| S-24 | Exportação cancelável | 4 | S-15 |
| S-25 | Persistência de estado robusta | 4 | — |
| S-26 | Cache limitado e paralelismo | 5 | — |
| S-27 | Treino reprodutível e métricas | 5 | S-07, S-08 |
| S-28 | Calibração de confiança | 5 | S-08, S-27 |
| S-29 | Experimentos de arquitetura e TTA | 5 | S-08, S-27 |
| S-30 | CUDA e ONNX | 5 | S-27 |
| S-31 | Camada de serviço e decomposição | 6 | S-10 a S-17 |
| S-32 | "Corrigir Net" opt-in | 6 | S-31 |
| S-33 | Motor de análise | 6 | S-31 |
| S-34 | Lote de múltiplos PDFs | 6 | S-15, S-24 |
| S-35 | Documentação | 6 | todas |
| S-36 | Empacotamento Windows | 6 | S-02, S-30 |
