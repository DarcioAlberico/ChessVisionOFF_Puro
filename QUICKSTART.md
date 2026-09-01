# Comece aqui

O `README.md` responde *por que* cada decisao foi tomada e o que ela custou, e e por isso que ele
e longo. Este arquivo responde so *como comecar*, em cinco minutos. Quando a duvida for "por que
assim", volte para o README -- a resposta esta la.

## 1. Instalar

```bash
uv sync --extra dev
```

Requer Python 3.10 a 3.13; o `uv` baixa o interpretador se faltar.

## 2. Por os arquivos no lugar

Nada disso vem no repositorio -- sao livros protegidos e trabalho humano acumulado:

| Onde | O que | Sem isso |
|---|---|---|
| `PDF/` | os livros a ler | o programa abre e nao tem o que ler |
| `models/piece_classifier.pt` | o modelo treinado | o programa abre e nao le diagrama nenhum |
| `data/labels.csv` + `data/samples/` | os rotulos que voce corrigiu | nasce vazio e cresce com o uso |

## 3. Abrir

```bash
uv run python app_pyqt.py
```

Conferir a instalacao sem abrir janela -- ele le uma pagina e diz o que achou:

```bash
uv run python app_pyqt.py --selftest
```

Codigos de saida: `0` ok, `2` sem PDF (ou PDF que nao abre), `3` sem checkpoint (ou checkpoint que
nao carrega), `1` falha ao reconhecer, `4` le mas nao treina, `5` alguma aparencia nao monta, `6`
sem PyQt6. O que ele achou vai para `logs/chessvisionoff.log`.

## 4. O ciclo que da valor ao projeto

**corrigir -> salvar -> treinar.** Abra o livro, va a uma pagina com diagrama, confira a posicao
que o programa leu, arraste as pecas que ele errou, salve. Cada correcao entra em
`data/labels.csv`; quando houver um punhado delas, **Treinar modelo** aprende com elas. E este
laco -- e nao o leitor sozinho -- que faz o acerto subir no *seu* acervo.

## 5. Dois avisos que economizam uma hora

- **O executavel nao e assinado.** O SmartScreen avisa na primeira execucao. Resolver isso exige
  um certificado de assinatura de codigo.
- **`data/`, `models/`, `PDF/` e `PGN/` ficam ao lado do executavel, e nao dentro dele.** E de
  proposito: reinstalar nao pode apagar o `labels.csv`. Backup e copiar a pasta.

## Depois disso

- `uv run cvoff-infer --help` e os outros comandos de linha -- o README os lista com o que cada
  um decide, e `tests/test_docs.py` confere a contagem contra o `pyproject.toml`.
- `CONTRIBUTING.md` para mexer no codigo (ruff, mypy e pytest, os tres verdes antes do commit).
- `docs/ARCHITECTURE.md` para o mapa dos modulos.
