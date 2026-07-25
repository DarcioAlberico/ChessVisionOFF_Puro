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
# Treino
cvoff-train --epochs 12 --batch-size 128 --lr 0.001

# Inferencia em uma pagina
cvoff-infer "PDF\1937 Kemeri.pdf" --page 0

# Varredura completa do PDF para PGN
cvoff-export "PDF\1937 Kemeri.pdf"
```

Os scripts `train_model.py`, `infer_pdf.py` e `export_pdf_pgn.py` na raiz continuam
funcionando como invocadores equivalentes (`uv run python infer_pdf.py ...`).

`cvoff-export` percorre todas as paginas, detecta os diagramas encontrados e salva um
jogo PGN por posicao. Sem `--output`, o arquivo vai para `PGN\<nome-do-pdf>.pgn`.

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
  board_detection.py    deteccao do tabuleiro na pagina (OpenCV)
  checkpoint.py         leitura de checkpoints .pt
  config.py             classes de pecas, tamanhos e caminhos padrao
  dataset.py            dataset de treino e gravacao de amostras
  fen_utils.py          conversao e validacao de FEN
  inference.py          carga do modelo e predicao de FEN
  logging_setup.py      configuracao de logging
  model.py              arquitetura do classificador de pecas
  pdf_io.py             render de paginas de PDF (PyMuPDF)
  pdf_to_pgn.py         varredura de PDF e exportacao PGN
  training.py           loop de treino
  webview2_panel.py     painel WebView2 embutido (Windows)
  cli/                  entrypoints cvoff-train, cvoff-infer, cvoff-export
app_tkinter.py          interface desktop
app_streamlit.py        interface web
tests/                  suite de testes
docs/                   analise tecnica, roadmap e especificacao
data/labels.csv         rotulos (versionado)
data/samples/           imagens dos tabuleiros (nao versionado)
models/                 checkpoints (nao versionado)
PDF/                    livros de origem (nao versionado)
PGN/                    saida gerada (nao versionado)
```

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
