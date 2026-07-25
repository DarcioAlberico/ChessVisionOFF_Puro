# Análise completa — ChessVisionOFF_Puro

Data da análise: 2026-07-25
Escopo: todo o código próprio do repositório (`src/chess_diagram_ocr/`, `app_tkinter.py`, `app_streamlit.py`, CLIs, `tests/`), dados (`data/`), artefatos (`models/`) e configuração do projeto.

Todas as afirmações quantitativas abaixo foram **medidas** neste repositório, com o `.venv` do projeto (Python 3.10.11, torch 2.10.0+cpu). Os scripts de medição são descartáveis e não foram adicionados ao repositório.

---

## 1. O que o programa é hoje

Pipeline de OCR de diagramas de xadrez em PDF:

```
PDF ──render (PyMuPDF, 220 DPI)──▶ imagem da página
     ──detect_boards (OpenCV, contornos)──▶ N tabuleiros 800×800 (warp de perspectiva)
     ──split 8×8──▶ 64 casas de 100×100
     ──CNN (64×64 cinza, 13 classes)──▶ 64 rótulos ──▶ FEN (só peças)
     ──▶ GUI para correção manual ──▶ labels.csv + PNG ──▶ retreino incremental
     ──▶ export PGN (1 jogo por diagrama, header FEN/SetUp)
```

Três frontends sobre a mesma biblioteca: Tkinter (principal, 2.137 linhas), Streamlit (480 linhas) e três CLIs (`train_model.py`, `infer_pdf.py`, `export_pdf_pgn.py`).

**A arquitetura é boa.** A separação `src/chess_diagram_ocr/` × frontends está correta, o loop humano-no-circuito (corrigir → salvar → retreinar) é a decisão de design certa para este problema, e a divisão treino/validação **por tabuleiro** (não por casa) em `training.py:42` evita o vazamento mais óbvio. O que falta não é reescrita: é fechar lacunas específicas.

### Números do estado atual

| Métrica | Valor medido |
|---|---|
| Amostras rotuladas | 3.244 tabuleiros = 207.616 casas |
| Modelo | CNN própria, 2.193.869 parâmetros, 8,7 MB |
| Acurácia por casa (250 tabuleiros, **dados de treino**) | 99,96% (6 erros em 16.000) |
| Acurácia exata por tabuleiro (mesma amostra) | 97,6% |
| Confiança média quando acerta / erra | 0,9991 / 0,8288 |
| Velocidade ponta a ponta | ~0,18 s/página → ~1 min para livro de 300 páginas (CPU) |
| Inferência | 50 ms por tabuleiro (64 casas em lote) |
| Testes | 8, todos passando em 0,18 s |
| PDFs disponíveis | 27 livros, 584 MB |

O 99,96% é **acurácia de treino** e não deve ser lido como qualidade real: não existe conjunto de teste separado neste projeto. O que a medição realmente mostra é que **o classificador já está saturado no estilo de diagrama que ele viu** — o gargalo passou para outro lugar.

---

## 2. Os cinco problemas que mais custam precisão

Estes não são hipóteses. Cada um está demonstrado com saída real do programa.

### 2.1 Nada valida legalidade — nem na saída, nem nos rótulos

`fen_utils.is_valid_fen()` chama `chess.Board(fen)` e retorna `True` se não houver exceção. Isso é um **teste de sintaxe**, não de legalidade. Verificado:

| FEN | `is_valid_fen()` | `Board.is_valid()` | Status real |
|---|---|---|---|
| `8/8/8/3R4/8/3K4/nQ2p2b/1K6` | ✅ True | ❌ False | NO_BLACK_KING (dois reis brancos) |
| `8/8/8/8/8/8/PPPPPPPP/PPPPPPPP` | ✅ True | ❌ False | 16 peões, peões na 1ª fila, nenhum rei |
| `8/8/8/8/8/8/8/8` | ✅ True | ❌ False | tabuleiro vazio |

Consequências em cadeia:

- **O PGN exportado contém posições ilegais.** Saída real da página 24 do `1937 Kemeri.pdf`: `8/8/8/3R4/8/3K4/nQ2p2b/1K6` com confiança **0,972**. Motores e visualizadores rejeitam.
- **Rótulos ilegais entram no dataset como verdade.** Dos 3.244 rótulos, **100 (3,1%)** são ilegais: 20 sem rei branco, 17 sem rei preto, 7 com reis demais, 10 com peões na primeira fila, 1 vazio. `BoardFenDataset._load_entries` usa `is_valid_fen` para filtrar, então não filtra nada disso — a CNN é treinada para reproduzir esses erros.
- **`detect_boards` produz falsos positivos silenciosos.** Página 40 do Kemeri: um "tabuleiro" detectado que rende `8/8/8/8/8/8/8/8` com confiança 0,891, exportado como um jogo PGN.

### 2.2 A confiança reportada é inútil como sinal de qualidade

`inference.predict_fen_from_board` retorna `conf.mean()` — a média do softmax máximo das 64 casas. Como ~76% das casas são vazias e triviais, a média é dominada por elas. Medido: quando o modelo erra uma casa, a confiança **daquela casa** é 0,83, mas a média do tabuleiro continua ~0,97. Um tabuleiro com um erro é indistinguível de um perfeito.

Isso quebra tudo que depende de priorização: não há como ordenar a fila de revisão manual, não há como decidir o que exportar, não há gate automático.

### 2.3 A informação de lado a jogar é perdida — e isso é metade do valor de um livro de exercícios

`fen_from_class_indices` produz apenas a parte de peças. `_normalize_fen` completa com `w - - 0 1` fixo.

Verificado no dataset: **0 dos 3.244 rótulos** têm lado a jogar preto. Apenas 5 têm direitos de roque. E os **51 rótulos marcados `OPPOSITE_CHECK`** são a assinatura exata do problema: são posições em que as pretas estão em xeque, o que só é legal se for a vez das pretas. Ou seja, ~51 posições "pretas jogam" foram gravadas como "brancas jogam".

Para um livro de táticas (`1001 Winning Chess Sacrifices`, `400 Quebra-cabeças`), aproximadamente metade dos exercícios é "pretas jogam". Hoje **todos** saem no PGN como brancas. O PGN é tecnicamente válido e semanticamente errado na metade dos casos.

### 2.4 O detector de contornos está deixando na mesa a informação exata que o PDF já tem

Medido nos livros do repositório: os diagramas são **imagens raster embutidas**, com bounding box exato disponível via `page.get_image_info()`.

| Livro | Imagens por página | Dimensão do diagrama |
|---|---|---|
| `1937 Kemeri.pdf` | 1–2 diagramas + 1 scan de fundo (1633×2468) | 590×590 |
| `AAGAARD - Practical Chess Defence.pdf` | 2–3 | 616×616 |
| `1001 Winning Chess Sacrifices` | 1 | 350×350 |

Comparação direta entre extrair a imagem embutida e detectar por contorno, na mesma página:

```
Kemeri pg24  embedded  conf=0.984  NO_WHITE_KING   8/Q3N3/1P1r4/8/5kr1/8/6P1/8
             contour   conf=0.986  OK              8/K3N3/1P1r4/8/5kr1/8/6P1/8
Kemeri pg25  embedded  conf=0.982  NO_WHITE_KING   1r1k4/3b2R1/p1n1pN2/P2pP3/n2P4/2p2q2/7P/8
             contour   conf=0.961  OK              1r1k4/3b2R1/p1n1pN2/3pP3/n2P4/2p2q2/7P/6K1
Aagaard pg21 embedded  conf=0.982  TOO_MANY_KINGS  6rk/R7/3pbrb1/3r1krN/P5k1/5P2/6K1/8
             contour   conf=1.000  OK              6rk/R7/4pqp1/3p2RP/5r2/P5Q1/5P2/6K1
```

Duas leituras importantes disso:

1. **Nenhum dos dois caminhos domina o outro.** A imagem embutida às vezes inclui legenda ou moldura (Aagaard pg21: 620×704, não quadrada) e a grade fica deslocada; o contorno às vezes pega o retângulo errado. Mas **os dois discordando é um sinal de altíssimo valor** — e a legalidade resolve o desempate corretamente em todos os casos acima.
2. **O erro K↔Q em fonte figurina alemã é sistemático** (`Q3N3` vs `K3N3`, `1R6` vs `1K6`). Uma checagem "existe exatamente um rei de cada cor" corrige isso sem nenhum retreino.

O que existe hoje é um detector de contorno com heurísticas afinadas à mão (`_contour_geometry_score`, `_board_pattern_score`, `_periodic_peak_score` em `board_detection.py`) que funciona razoavelmente, ignorando metadados exatos que o PDF entrega de graça.

### 2.5 Discrepância de ordenação entre a GUI e o export

`detect_boards` tem `reading_order="row"` como padrão. `pdf_to_pgn.scan_pdf_positions` passa `"column"`. Os frontends chamam sem o parâmetro, ou seja, `"row"`.

Numa página com duas colunas de diagramas, o diagrama nº 2 na GUI não é o diagrama nº 2 no PGN exportado. O header `[Diagram "2"]` e o `[Round "p.2"]` apontam para outra posição. Rastreabilidade quebrada exatamente quando o usuário mais precisa dela (conferir uma correção).

---

## 3. Problemas de engenharia

### 3.1 Repositório sem nenhum commit, prestes a versionar 3,3 GB

`git log` → `your current branch 'master' does not have any commits yet`. Todo o trabalho está apenas no disco, sem histórico.

E o `.gitignore` cobre só `__pycache__/`, `build/`, `dist/`, `*.egg-info`, `.venv`. O primeiro `git add .` versionaria:

| Caminho | Tamanho | Deve ser versionado? |
|---|---|---|
| `data/samples/` (3.244 PNGs de 800×800) | **2,7 GB** | Não — dados, não código |
| `PDF/` (27 livros) | **584 MB** | Não — material protegido por direito autoral |
| `Python-Easy-Chess-GUI-master/` | 57 MB | Não — dependência de terceiro vendorizada |
| `models/piece_classifier.pt` | 8,7 MB | Não em git puro (usar release/LFS) |
| `pecg_log.txt`, `pecg_user.json`, `teste-001.ini`, `teste-001.pgn`, `PGN/` | — | Não — lixo de execução |

Este é o item mais urgente do roadmap, porque é o único que fica **mais caro** com o tempo: depois do primeiro commit, os 3,3 GB ficam no histórico para sempre.

### 3.2 O pacote nunca foi instalado; os quatro entrypoints usam gambiarra de `sys.path`

Verificado: `import chess_diagram_ocr` falha no `.venv` do projeto. O README manda rodar `pip install -e .`, mas `pyproject.toml` **não tem `[build-system]`** nem configuração de pacotes. Cada um dos quatro entrypoints repete:

```python
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
```

Sintoma direto: rodar `python -m unittest discover -s tests` como o README instrui, com o Python do sistema (3.14.5), falha com `ModuleNotFoundError: No module named 'numpy'`. Só funciona com o `.venv` explícito.

Além disso, `pyproject.toml` carrega restrições contraditórias: `requires-python = "==3.10.*"` convivendo com markers `python_full_version < '3.9'` — condições mortas que nunca são satisfeitas.

### 3.3 O cache do dataset consome 5,8 GiB de RAM por época

`dataset.BoardFenDataset._board_cache` guarda cada tabuleiro decodificado como array 800×800×3 e nunca libera. Como `index_map` percorre todas as 64 casas de cada tabuleiro, uma época completa carrega os 3.244:

```
3.244 × 800 × 800 × 3 bytes = 5,80 GiB
```

Medido pela contagem real de entradas do dataset. Em máquina com 8 GB isso sozinho leva a swap ou `MemoryError`. Piora linearmente conforme o dataset cresce — e o dataset **é feito para crescer**, esse é o ponto do projeto.

Agravante: o `DataLoader` roda com `num_workers=0` (padrão), então toda a decodificação PNG + `cvtColor` + `resize` acontece na thread principal, serializada com o passo de otimização.

### 3.4 Retreino incremental sem reprodutibilidade

`training.py` sempre carrega o checkpoint existente se ele existir (`training.py:85`) com `strict=False`, e a divisão treino/validação é `torch.randperm` com semente 42 sobre `len(dataset.entries)`.

O problema: quando o dataset cresce de 3.244 para 3.300, a permutação muda inteira. Um tabuleiro que era validação ontem é treino hoje. Como o modelo é retomado do checkpoint anterior, ele **já viu** os tabuleiros que hoje são validação. As métricas de validação e o early stopping ficam contaminados de forma crescente e invisível. Não há `--fresh` para treinar do zero.

`strict=False` é uma segunda armadilha: se a arquitetura mudar, pesos incompatíveis são silenciosamente descartados e o treino recomeça de um estado parcialmente aleatório sem nenhum aviso.

### 3.5 Métrica de treino não mede o que interessa

`training._accuracy` reporta acurácia por casa. Com 76% das casas vazias, um modelo que só diz "vazio" já marca 76%. A métrica que importa para o usuário é **acurácia exata por tabuleiro** (quantos diagramas saem sem nenhuma correção manual) e ela não é medida em lugar nenhum. Também não há matriz de confusão nem métrica por classe — as classes raras (`q`: 109 casas na amostra de 250 tabuleiros; `n`: 145) são invisíveis no agregado.

### 3.6 `render_pdf_page` devolve array somente-leitura

Verificado: `flags.writeable=False`, `flags.owndata=False`. É uma view sobre o buffer do `Pixmap` do PyMuPDF, criada com `np.frombuffer` (`pdf_io.py:32`). Qualquer escrita in-place levanta `ValueError: assignment destination is read-only`.

O `app_tkinter.py` contorna isso com `np.asarray(self.page_rgb).copy()` em dois lugares, mas é uma armadilha esperando o próximo chamador. `pdf_io` deve devolver um array próprio e gravável.

### 3.7 Duplicação de lógica entre os frontends

`app_tkinter._detect_and_predict_items` e `app_streamlit.run_ocr_for_boards` implementam o mesmo fluxo (detectar → classificar → montar `items` com `index`/`board_rgb`/`quad`/`fen_pred`/`confidence`) de forma independente. `save_current`/`save_all` também estão duplicados. Toda melhoria de precisão precisa ser aplicada duas vezes, e o Streamlit já está atrasado: não tem "Corrigir Net", nem seleção de área, nem aba de análise.

Falta uma camada de serviço em `src/` que os dois frontends consumam.

### 3.8 `app_tkinter.py`: classe-Deus de 2.137 linhas

`ChessOcrTkApp` acumula ~60 atributos de instância no `__init__` e mistura cinco responsabilidades: layout, estado de OCR, tabuleiro de estudo/PGN, orquestração de threads e persistência. Está funcional e legível — não é código ruim — mas é a razão pela qual o Streamlit divergiu, e torna teste de unidade impossível.

Pontos concretos ali:

- `_load_app_state`/`_save_app_state` fazem read-modify-write sem escrita atômica: uma interrupção corrompe o JSON de estado. Ambos silenciam toda exceção com `except Exception: pass` / `return False`, então falhas são invisíveis.
- `_set_status` chama `root.update_idletasks()` dentro de callback de evento — reentrância do loop de eventos.
- `reload_model()` é chamado da thread de treino (`_train_model_worker:2110`) e zera `_model_cache` enquanto uma thread de OCR pode estar usando — corrida real, embora de janela estreita.
- Exportação PDF→PGN não tem cancelamento nem retomada. Num livro de 1.121 páginas, o único jeito de parar é fechar o programa e perder tudo.

### 3.9 Envio de imagens para um serviço externo sem opt-in

`app_tkinter.py:54`:

```python
NET_CORRECT_URL = "https://helpman.komtera.lt/predict"
```

O botão "Corrigir Net" faz upload da imagem do tabuleiro para um host de terceiro fixo no código. Não é configurável, não está documentado no README, e não há confirmação do usuário. Deve ser opt-in explícito, com endpoint configurável e aviso claro de que a imagem sai da máquina.

### 3.10 Cobertura de testes concentrada no lugar errado

8 testes: 4 em `board_detection`, 4 em `pdf_to_pgn`. **Zero** em `fen_utils` (onde está o bug de validação da §2.1), `dataset`, `training`, `inference`, `model`.

`test_detect_boards_still_finds_real_sample` depende de `next((ROOT/"data"/"samples").glob("*.png"))` — qualquer arquivo, não um fixture fixo. O teste passa ou falha conforme a ordem do sistema de arquivos. Não há fixtures versionados nem teste de regressão de acurácia.

### 3.11 Infra ausente

- Sem CI, sem linter (`ruff`/`black`), sem type checker (o código é bem anotado — `mypy` daria retorno imediato).
- Sem dependências de desenvolvimento no `pyproject.toml`.
- `logging` inexistente; diagnóstico é `print` e strings de status na GUI. `training.py:175` imprime early stopping em inglês no meio de uma UI em português.
- torch instalado é `2.10.0+cpu` — sem CUDA. Treino e inferência estão presos à CPU mesmo que a máquina tenha GPU.
- `__pycache__` com bytecode de cpython-38, -310 e -314 misturado: três interpretadores diferentes já rodaram este código.
- Textos misturam português sem acentuação ("posicao", "deteccao", "Configuracao") e inglês, sem centralização de strings.

### 3.12 Qualidade dos dados

- **283 FENs duplicados** em `labels.csv`. Parte é legítima (posições iguais em livros diferentes), parte é `save_all` chamado duas vezes na mesma página. Não há deduplicação por hash de imagem.
- CSV append-only sem ferramenta de revisão: não há como listar, corrigir ou remover uma amostra rotulada errada. Os 100 rótulos ilegais da §2.1 só podem ser consertados editando CSV na mão.
- Cada amostra é um PNG 800×800 (~850 KB). Os 3.244 ocupam 2,7 GB para 207.616 casas de 64×64 que é o que o modelo realmente consome. Guardar as casas recortadas, ou o tabuleiro em 256×256, reduziria isso em mais de 10×.
- Sem divisão treino/validação/**teste** persistida em arquivo. Sem conjunto de teste, "melhorou" é indemonstrável.

---

## 4. Onde vale investir — em ordem de retorno

Ordenado por (impacto na precisão do PGN final) ÷ (esforço):

| # | Melhoria | Esforço | Retorno |
|---|---|---|---|
| 1 | Legalidade real (`Board.is_valid()`) + decodificação com restrições | Baixo | **Muito alto** — corrige erros K/Q hoje existentes, sem retreino |
| 2 | Confiança por casa em vez de média | Muito baixo | **Muito alto** — habilita fila de revisão e gate de qualidade |
| 3 | Saneamento dos 100 rótulos ilegais + conjunto de teste fixo | Baixo | **Muito alto** — sem isso nada é mensurável |
| 4 | `.gitignore` + commit inicial | Muito baixo | **Muito alto** — e o custo só cresce |
| 5 | Detecção híbrida (imagem embutida + contorno) com desempate por legalidade | Médio | **Alto** |
| 6 | Lado a jogar via texto da legenda | Médio | **Alto** — metade dos exercícios está errada hoje |
| 7 | Cache do dataset limitado + `num_workers` | Baixo | Alto — desbloqueia crescimento do dataset |
| 8 | Editor de posição por clique + heatmap de incerteza | Médio | Alto — é o gargalo de tempo humano |
| 9 | Camada de serviço unificando os frontends | Médio | Médio — paga-se na 2ª melhoria em diante |
| 10 | Empacotamento, CI, lint, tipos | Baixo | Médio |

O detalhamento de cada item está em [SPEC.md](SPEC.md); o sequenciamento em fases está em [ROADMAP.md](ROADMAP.md).

---

## 5. Uma observação sobre o diagnóstico

Vale registrar o que a medição mudou em relação à intuição inicial: **o classificador não é o problema.** 2,2 M de parâmetros já saturam o estilo de diagrama conhecido, e melhorar a arquitetura (ResNet, mais resolução, mais aumento de dados) traria pouco.

Os erros que sobram vêm de três lugares completamente diferentes: recorte errado da grade (detecção), ausência de restrição de legalidade na decodificação, e informação semântica que nunca foi capturada (lado a jogar). Nenhum dos três se resolve com mais épocas de treino. É por isso que o roadmap começa em dados e restrições, e só chega em arquitetura de modelo na Fase 5.
