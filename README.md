# Chess Diagram OCR (OpenCV + PyTorch)

Projeto para extrair diagramas de xadrez em PDF, converter para FEN e melhorar a acuracia com treino incremental.

## Stack

- OpenCV: deteccao de tabuleiro e recorte por perspectiva.
- PyTorch: classificador de pecas por casa (13 classes: vazio + 12 pecas).
- python-chess: validacao e representacao de FEN/board.
- Tkinter: interface desktop principal (`app_tkinter.py`).
- WebView2 embutido: modo de leitura do PDF na interface desktop.
- Streamlit: interface web alternativa (`app_streamlit.py`).
- PyMuPDF (`fitz`): render de paginas PDF para imagem.

## Setup

O projeto usa [uv](https://docs.astral.sh/uv/) e um lockfile (`uv.lock`), que e a forma
recomendada de reproduzir o ambiente exato:

```bash
uv sync                 # ambiente de uso
uv sync --extra dev     # inclui pytest, ruff e mypy
```

Alternativa com pip, se preferir gerenciar o venv manualmente:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

Em qualquer um dos casos o pacote `chess_diagram_ocr` fica instalado em modo editavel,
e os comandos `cvoff-*` passam a existir no PATH do ambiente.

Requer Python 3.10. Os arquivos de dados (`PDF/`, `data/samples/`) e o checkpoint
(`models/piece_classifier.pt`) nao vem no repositorio -- veja
[Dados e artefatos](#dados-e-artefatos).

## Rodar interface desktop (Tkinter)

```bash
uv run python app_tkinter.py
```

No Windows, o modo "Leitura" da interface desktop usa Microsoft Edge WebView2 Runtime.

## Rodar interface web (Streamlit)

```bash
uv run streamlit run app_streamlit.py
```

## Comandos de linha

Depois da instalacao, os tres comandos abaixo ficam disponiveis no ambiente. Todos
aceitam `-v` para log em nivel DEBUG.

```bash
# Treino. Usa data/splits.csv: treina no split 'train', valida em 'val',
# e nunca toca no split 'test'. --fresh treina do zero.
cvoff-train --epochs 12 --batch-size 128 --lr 0.001

# Inferencia em uma pagina
cvoff-infer "PDF\1937 Kemeri.pdf" --page 0

# Varredura completa do PDF para PGN
cvoff-export "PDF\1937 Kemeri.pdf"
cvoff-export "PDF\1937 Kemeri.pdf" --dedupe   # omite posicoes repetidas no mesmo PDF
cvoff-export "PDF\1937 Kemeri.pdf" --no-text  # ignora a legenda do PDF (lado a jogar so por legalidade)

# Auditoria do dataset: posicoes ilegais, duplicatas, orfaos, distribuicao de classes.
# Sem flags, apenas relata. Toda escrita cria backup do CSV.
cvoff-audit
cvoff-audit --fix-side-to-move --quarantine --dedupe

# Migracao do labels.csv para o esquema com lado a jogar e origem. Cria backup;
# deduz o lado a jogar so onde a posicao o impoe, e deixa vazio o resto.
cvoff-migrate-labels

# Avaliacao. A metrica primaria e a acuracia exata por tabuleiro:
# a fracao de diagramas que sai sem nenhuma correcao manual.
cvoff-eval --split test
cvoff-eval --split test --json docs/metrics/atual.json
```

Os scripts `train_model.py`, `infer_pdf.py` e `export_pdf_pgn.py` na raiz continuam
funcionando como invocadores equivalentes (`uv run python infer_pdf.py ...`).

`cvoff-export` percorre todas as paginas, detecta os diagramas encontrados e salva um
jogo PGN por posicao. Sem `--output`, o arquivo vai para `PGN\<nome-do-pdf>.pgn`.

O lado a jogar sai da legenda do PDF quando ela declara, da legalidade da posicao quando
ela impoe (o lado que nao joga nao pode estar em xeque), e do padrao "brancas" quando
nenhuma das duas responde. O header `[SideToMoveSource]` diz qual dos tres foi, sempre --
a maioria dos livros do acervo nao declara nada, e um palpite precisa parecer um palpite.

Para gravar o log em arquivo, defina `CVOFF_LOG_DIR`:

```bash
set CVOFF_LOG_DIR=logs
```

## Testes e verificacoes

```bash
uv run pytest          # testes
uv run ruff check .    # lint
uv run mypy            # tipos
```

Os testes que dependem de `data/samples/` sao pulados automaticamente quando a pasta
esta vazia, entao a suite roda em um clone limpo.

## Fluxo recomendado

1. Abrir PDF.
2. Navegar para a pagina desejada.
3. Rodar OCR (melhor diagrama ou todos).
4. Corrigir FEN.
5. Salvar exemplos corrigidos.
6. Treinar modelo.
7. Repetir ciclo para reduzir correcoes manuais.

## Estrutura

```text
src/chess_diagram_ocr/
  audit.py              auditoria do dataset: legalidade, duplicatas, orfaos
  board_detection.py    deteccao do tabuleiro na pagina (OpenCV)
  checkpoint.py         leitura de checkpoints .pt
  config.py             classes de pecas, tamanhos e caminhos padrao
  dataset.py            dataset de treino e gravacao de amostras
  evaluation.py         metricas de qualidade do reconhecimento
  fen_utils.py          conversao de FEN e checagem de legalidade
  inference.py          carga do modelo e predicao de FEN
  logging_setup.py      configuracao de logging
  model.py              arquitetura do classificador de pecas
  pdf_io.py             render de paginas de PDF (PyMuPDF)
  pdf_to_pgn.py         varredura de PDF e exportacao PGN
  splits.py             divisao treino/validacao/teste estavel
  training.py           loop de treino
  webview2_panel.py     painel WebView2 embutido (Windows)
  cli/                  entrypoints cvoff-*
app_tkinter.py          interface desktop
app_streamlit.py        interface web
tests/                  suite de testes
docs/                   analise tecnica, roadmap, especificacao e baseline
data/labels.csv         rotulos (versionado)
data/splits.csv         particao treino/validacao/teste (versionado)
data/samples/           imagens dos tabuleiros (nao versionado)
models/                 checkpoints (nao versionado)
PDF/                    livros de origem (nao versionado)
PGN/                    saida gerada (nao versionado)
```

## Sobre FEN: sintaxe nao e legalidade

Duas checagens distintas, e confundi-las causava rotulos corrompidos no dataset:

- `is_syntactically_valid_fen(fen)` -- a notacao e interpretavel. Aceita posicoes
  impossiveis, como duas damas brancas sem rei.
- `check_position(fen)` -- aplica as regras do xadrez. Classifica os problemas em:
  - **fatais**, independentes do lado a jogar (rei faltando, pecas demais, peao na
    primeira fila). Sao erro real de reconhecimento e ficam fora do treino.
  - **de turno**, que dependem de quem joga. Num diagrama de livro o lado a jogar nao
    esta na imagem e e preenchido como "brancas"; quando isso torna a posicao ilegal,
    quase sempre significa que era a vez das pretas. As pecas estao certas.

## Dados e artefatos

O repositorio versiona apenas codigo, documentacao e `data/labels.csv`. Ficam de fora,
por tamanho ou por direito autoral:

| Caminho | Conteudo | Por que fora |
|---|---|---|
| `PDF/` | livros de origem | material protegido por direito autoral |
| `data/samples/` | ~3.200 PNGs de tabuleiros, ~2,7 GB | tamanho |
| `models/*.pt` | checkpoint treinado, ~8,7 MB | binario que muda a cada treino |
| `PGN/` | saida gerada | reproduzivel a partir dos PDFs |

Em um clone novo e preciso trazer seus proprios PDFs para `PDF/` e treinar o modelo
(`cvoff-train`) ou obter um checkpoint por outro meio.

## Documentacao tecnica

- [docs/ANALISE.md](docs/ANALISE.md) -- diagnostico do estado atual, com medicoes
- [docs/ROADMAP.md](docs/ROADMAP.md) -- fases de evolucao planejadas
- [docs/SPEC.md](docs/SPEC.md) -- especificacao detalhada das melhorias (S-01 a S-36)
