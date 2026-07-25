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

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

Ou, se preferir usar o lockfile do projeto:

```bash
uv sync
```

## Rodar interface desktop (Tkinter)

```bash
python app_tkinter.py
```

No Windows, o modo "Leitura" da interface desktop usa Microsoft Edge WebView2 Runtime.

## Rodar interface web (Streamlit)

```bash
streamlit run app_streamlit.py
```

## Treino via CLI

```bash
python train_model.py --epochs 12 --batch-size 128 --lr 0.001
```

## Inferencia via CLI

```bash
python infer_pdf.py "PDF\1937 Kemeri.pdf" --page 0
```

## Varredura completa do PDF para PGN

```bash
python export_pdf_pgn.py "PDF\1937 Kemeri.pdf"
```

O comando percorre todas as paginas, detecta todos os diagramas encontrados e salva um jogo PGN por posicao. Se `--output` nao for informado, o arquivo e gerado em `PGN\<nome-do-pdf>.pgn`.

## Testes

```bash
python -m unittest discover -s tests
```

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
  board_detection.py
  config.py
  dataset.py
  fen_utils.py
  inference.py
  model.py
  pdf_io.py
  training.py
app_tkinter.py
app_streamlit.py
train_model.py
infer_pdf.py
data/
  labels.csv
  samples/
models/
```
