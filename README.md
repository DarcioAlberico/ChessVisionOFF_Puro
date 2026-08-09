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
# Amostra salva depois do ultimo treino recebe split aqui, antes de o dataset ser montado --
# sem isso ela ficava invisivel ao treino, em silencio (S-56).
# A epoca salva e a de melhor acuracia exata por tabuleiro, nao a de menor val_loss.
# No fim, calibra a temperatura no split de validacao e a grava no checkpoint.
cvoff-train --epochs 12 --batch-size 128 --lr 0.001
cvoff-train --fresh --seed 42            # reproduzivel: mesma semente, mesmas metricas
cvoff-train --num-workers 4              # medido: nao compensa nesta maquina (EXPERIMENTS.md)
# Aumento dirigido ao acervo (S-40): m=espelhar h=hachura s=granulacao p=papel i=inversao.
# Desligado por padrao e AINDA NAO MEDIDO -- ligar muda o modelo. A comparacao honesta e
# treinar as duas variantes com a mesma semente e medir com `cvoff-field`.
cvoff-train --fresh --epochs 3 --seed 42 --augment mhsp --model models/experiments/s40.pt

# Inferencia em uma pagina
cvoff-infer "PDF\1937 Kemeri.pdf" --page 0

# Varredura completa do PDF para PGN
cvoff-export "PDF\1937 Kemeri.pdf"
cvoff-export "PDF\1937 Kemeri.pdf" --dedupe   # omite posicoes repetidas no mesmo PDF
cvoff-export "PDF\1937 Kemeri.pdf" --no-text  # ignora a legenda do PDF (lado a jogar so por legalidade)

# Auditoria do dataset: posicoes ilegais, duplicatas, orfaos, distribuicao de classes e
# amostras sem split (invisiveis ao treino ate o proximo cvoff-train).
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
cvoff-eval --split test --tta                      # soma as 7 vistas do TTA (S-29)
cvoff-eval --split test --calibration-target 0.98  # deriva o limiar de aceite da curva

# Avaliacao de campo (S-41): mede sobre paginas reais anotadas a mao, e nao sobre recortes
# ja aprovados. A metrica primaria e a taxa de exportacao -- dos diagramas que a pagina tem,
# quantos saem detectados, legais e acima do gate. Inclui paginas SEM diagrama, que sao as
# unicas que medem falso positivo.
cvoff-field
cvoff-field --json docs/metrics/atual.json
# Anotar uma pagina nova: o rascunho ja traz o que o pipeline leu, e voce corrige.
cvoff-field --no-placement --regime scan-puro --draft "1937 Kemeri.pdf:80,187"

# Grade de experimentos de arquitetura (S-29): canais, resolucao, cabeca, backbone.
# Cada variante treina do zero com a mesma semente e e comparada no split 'val'
# -- nunca no 'test', que fica para a confirmacao final da vencedora.
cvoff-experiment --epochs 3
cvoff-experiment --only referencia gap --epochs 8

# Exportacao ONNX (S-30): backend alternativo para CPU. Confere paridade numerica
# com o torch em tolerancia de 1e-4 sobre o split de teste antes de dar por bom.
# Requer o extra: uv sync --extra onnx
cvoff-export-onnx --model models/piece_classifier.pt

# Biblioteca inteira de uma vez, com relatorio consolidado. Um livro que falha nao
# derruba a varredura: vira uma linha do relatorio e a varredura segue. Livro cujo PGN
# ja existe e pulado, e e isso que torna a varredura retomavel.
cvoff-batch PDF --output PGN --report PGN/batch_report.json
cvoff-batch PDF --no-skip-existing        # reexporta tudo
cvoff-batch PDF --limit 3                 # so os tres primeiros livros

# Fila de revisao: varre o livro e ordena os diagramas por valor de informacao.
# Ilegal > orientacao incerta > fontes discordantes > confianca baixa > entropia.
# Grava em data/review_queue.json, que a aba "Revisao" do app le.
cvoff-review "PDF\1937 Kemeri.pdf" --start-page 10 --end-page 70
```

Os scripts `train_model.py`, `infer_pdf.py` e `export_pdf_pgn.py` na raiz continuam
funcionando como invocadores equivalentes (`uv run python infer_pdf.py ...`).

`cvoff-export` percorre todas as paginas, detecta os diagramas encontrados e salva um
jogo PGN por posicao. Sem `--output`, o arquivo vai para `PGN\<nome-do-pdf>.pgn`.

A exportacao e cancelavel e retomavel: a cada 5 paginas ela grava
`PGN\<nome>.partial.jsonl`, e uma execucao interrompida oferece retomar da pagina seguinte
a ultima concluida -- desde que os parametros sejam os mesmos. Concluir apaga o parcial.

O lado a jogar sai da legenda do PDF quando ela declara, da legalidade da posicao quando
ela impoe (o lado que nao joga nao pode estar em xeque), e do padrao "brancas" quando
nenhuma das duas responde. O header `[SideToMoveSource]` diz qual dos tres foi, sempre --
a maioria dos livros do acervo nao declara nada, e um palpite precisa parecer um palpite.

Para gravar o log em arquivo, defina `CVOFF_LOG_DIR`:

```bash
set CVOFF_LOG_DIR=logs
```

## Recursos opcionais (e o que o projeto faz sem eles)

**O projeto funciona inteiramente offline.** Nada sai da sua maquina no uso padrao. As duas
integracoes abaixo sao desligadas por padrao e nao afetam o reconhecimento.

### Correcao remota de FEN ("Corrigir Net")

Envia a **imagem do diagrama** para um servico HTTP de terceiro, que devolve uma FEN. Serve
como segunda opiniao quando o modelo local erra.

Vem **desligado, e sem endereco algum embutido**. Habilitar exige declarar o endpoint:

```jsonc
// data/settings.json
{
  "remote_fen": {
    "enabled": true,
    "endpoint": "https://exemplo.invalido/predict",
    "timeout": 30
  }
}
```

Ou por variavel de ambiente, que vence o arquivo:

```bash
set CVOFF_REMOTE_FEN_URL=https://exemplo.invalido/predict
set CVOFF_REMOTE_FEN_ENABLED=0     # forca desligado, mesmo com o arquivo dizendo o contrario
```

Sem configuracao o botao fica desabilitado, e o tooltip diz por que. Na primeira vez que
voce mandar enviar, um aviso nomeia o host de destino e pede confirmacao; "nao perguntar
novamente" fica gravado **por endereco** -- trocar o endpoint volta a perguntar.

O servico que o projeto usava antes (`https://helpman.komtera.lt/predict`) continua
funcionando se voce o escrever ali. Ele e de terceiro e sem contrato: pode sair do ar.

### Motor de analise (Stockfish)

Avalia a posicao na aba **Analise**: pontuacao, melhor lance, linha principal e barra de
vantagem. Sem binario instalado, a secao simplesmente nao aparece -- nao ha botao cinza nem
mensagem de erro.

O projeto procura o binario nesta ordem: o caminho em `settings.json`, a variavel
`CVOFF_ENGINE_PATH`, o `PATH` do sistema, e por fim `engines/` dentro do projeto. Baixar o
Stockfish para `engines/` e a instalacao mais simples.

```jsonc
// data/settings.json
{
  "engine": {
    "path": "C:/Program Files/Stockfish/stockfish.exe",
    "movetime_ms": 800
  }
}
```

## Resolucao de problemas

| sintoma | causa provavel | o que fazer |
|---|---|---|
| A aba **Leitura** diz "WebView2 indisponivel" | falta o Microsoft Edge WebView2 Runtime (so Windows) | instalar o runtime, ou usar a aba **OCR**, que nao depende dele |
| Treino muito lento (~9 min por epoca) | `torch` `+cpu`, sem CUDA | ver [Desempenho](#desempenho-cpu-gpu-e-onnx). A barra de status diz qual dispositivo esta em uso |
| Todo diagrama sai como "brancas jogam" | o PDF nao tem camada de texto que declare o lado | e o esperado em 24 dos 27 livros do acervo. O header `[SideToMoveSource "default"]` marca o palpite como palpite |
| Poucos diagramas detectados numa pagina cheia | o teto "Max diagramas" cortou | o padrao e 12; o log avisa com os scores quando o teto corta candidato aprovado |
| Diagramas de cabeca para baixo | orientacao fixa em 0 ou 180 | usar **Automatica** (padrao). Casos ambiguos entram na fila de revisao marcados |
| "Nenhum tabuleiro foi detectado" numa pagina que tem um | scan de baixo contraste, ou o diagrama nao e imagem embutida | usar **Selecionar area (OCR)** e arrastar em volta do diagrama: ali o recorte e o seu, e o detector nao precisa acertar |
| A exportacao parou no meio | cancelada ou interrompida | exportar de novo para o mesmo arquivo: ele oferece retomar da pagina seguinte a ultima concluida |
| A exportacao recusa retomar e diz que "o arquivo do modelo mudou" | houve treino entre a interrupcao e a retomada | e o esperado: retomar juntaria metade de um PGN lido por um modelo com metade lida por outro. Exportar do zero |
| `cvoff-*` nao existe | ambiente nao instalado em modo editavel | `uv sync --extra dev`, e usar `uv run cvoff-...` |
| `pytest` falha em 33 arquivos com `No module named 'chess_diagram_ocr'` | o projeto foi movido depois de instalado, e o `.pth` do `.venv` aponta para o caminho antigo | `uv sync --extra dev`. A suite em si roda sem instalacao (`pythonpath` no `pyproject.toml`); quem depende dela sao os `cvoff-*` e o `app_tkinter.py` |
| O treino nao aparece no dataset o que voce acabou de salvar | a amostra nao tinha split registrado | resolvido desde a S-56: o proprio `cvoff-train` atribui. `cvoff-audit` mostra quantas estao nesse estado |
| Testes de ONNX pulados | o extra nao esta instalado | `uv sync --extra onnx`, se voce precisa deles |
| Correcoes somem ao navegar entre paginas | o cache guarda 8 paginas | salvar a amostra (`Ctrl+S`) e o que persiste; o cache e conveniencia de navegacao. O log avisa quando descarta pagina com correcao sua |

## Testes e verificacoes

```bash
uv run pytest          # testes
uv run ruff check .    # lint
uv run mypy            # tipos
```

Os testes que dependem de `data/samples/` sao pulados automaticamente quando a pasta
esta vazia, entao a suite roda em um clone limpo. Os testes de ONNX sao pulados quando o
extra `onnx` nao esta instalado.

## Desempenho: CPU, GPU e ONNX

O `torch` das dependencias e `+cpu`. Na inicializacao o log e a barra de status dizem
qual dispositivo esta em uso -- antes essa escolha era feita em silencio, e uma maquina
com placa de video rodava em CPU sem que nada indicasse isso.

**Com GPU NVIDIA**, instalar a wheel CUDA correspondente acelera o treino em cerca de 10x:

```bash
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
uv run python -c "import torch; print(torch.cuda.is_available())"   # tem de imprimir True
```

Nada mais precisa mudar: o codigo ja escolhe `cuda` quando ela existe, e passa a dize-lo.

**Sem GPU**, o ONNX Runtime e uma alternativa para inferencia (nao para treino):

```bash
uv sync --extra onnx
cvoff-export-onnx --model models/piece_classifier.pt
```

O comando so da o `.onnx` por bom depois de conferir que ele produz as mesmas
probabilidades que o torch em tolerancia de 1e-4 sobre todo o split de teste, e que nao ha
nenhuma discordancia de argmax -- um backend mais rapido que divergisse na terceira casa
produziria outras FENs.

Numeros medidos de memoria e tempo estao em [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md).

## Fluxo recomendado

1. Abrir PDF.
2. Navegar para a pagina desejada.
3. Rodar OCR (melhor diagrama ou todos).
4. Corrigir a posicao no proprio tabuleiro: arrastar move a peca, botao direito apaga,
   a paleta insere. As casas em que o modelo esta inseguro aparecem tingidas de amarelo a
   vermelho, e o painel abaixo diz o que esta ilegal e em que casas.
5. Salvar exemplos corrigidos.
6. Treinar modelo.
7. Repetir ciclo para reduzir correcoes manuais.

O reconhecimento fica guardado por pagina: voltar para uma pagina ja reconhecida traz de
volta os diagramas, o diagrama que estava selecionado e as correcoes feitas a mao, sem
rodar o OCR de novo. Sao as 8 paginas mais recentes; alem disso as mais antigas saem para
nao acumular memoria, e o log avisa quando a que saiu tinha correcao sua. Mudar DPI,
modelo, orientacao ou o maximo de diagramas invalida o que estava guardado, porque o
recorte passa a ser outro.

Para livro inteiro, o caminho mais curto e a aba **Revisao**: ela varre o PDF, ordena os
diagramas por valor de informacao e abre cada um no editor ja na casa suspeita. A aba
**Dataset** lista o `labels.csv` com filtros (legalidade, split, livro, duplicatas) e
permite recorrigir, mandar para quarentena ou remover uma amostra sem tocar no CSV.

Atalhos do ciclo de correcao (desligados quando o foco esta num campo de texto):

| tecla | acao |
|---|---|
| `←` / `→` | diagrama anterior / proximo |
| `Ctrl+S` | salvar a amostra atual |
| `Ctrl+Shift+S` | salvar todas |
| `Ctrl+R` | rodar o OCR na pagina de novo |
| `Del` | apagar a peca da casa selecionada |
| `Ctrl+N` | abrir o proximo item da fila de revisao |

## Estrutura

```text
src/chess_diagram_ocr/
  service.py            camada de servico: o pipeline de OCR, sem dependencia de UI
  settings.py           preferencias do usuario (endpoint remoto, motor de analise)
  atomic_io.py          escrita de arquivo que nao deixa arquivo pela metade
  audit.py              auditoria do dataset: legalidade, duplicatas, orfaos
  batch.py              varredura da biblioteca inteira, com relatorio consolidado
  board_detection.py    deteccao do tabuleiro na pagina (OpenCV)
  calibration.py        temperature scaling e curva de confiabilidade
  checkpoint.py         leitura e escrita de checkpoints, com metadados de treino
  config.py             classes de pecas, tamanhos, limiares e caminhos padrao
  dataset.py            dataset de treino, cache limitado e amostrador por tabuleiro
  dataset_browser.py    listar, filtrar, recorrigir e remover amostras
  decode.py             decodificacao sujeita as regras do xadrez
  engine.py             motor UCI opcional (Stockfish)
  evaluation.py         metricas de qualidade do reconhecimento (sobre recortes rotulados)
  field_eval.py         metricas sobre paginas reais anotadas: recall, precisao, exportacao
  experiments.py        grade de experimentos de arquitetura
  export_checkpoint.py  parcial da exportacao, para cancelar e retomar
  fen_utils.py          conversao de FEN e checagem de legalidade
  inference.py          carga do modelo, predicao de FEN e TTA
  logging_setup.py      configuracao de logging
  model.py              arquitetura do classificador, configuravel por ArchConfig
  net_correction.py     cliente da correcao remota de FEN (opcional, opt-in)
  onnx_export.py        exportacao ONNX e conferencia de paridade com o torch
  pdf_io.py             render de paginas de PDF (PyMuPDF)
  pdf_text.py           legenda e metadados da camada de texto do PDF
  pdf_to_pgn.py         varredura de PDF e exportacao PGN
  review_queue.py       fila de revisao ordenada por valor de informacao
  semantics.py          lado a jogar e direitos de roque
  splits.py             divisao treino/validacao/teste estavel
  training.py           loop de treino
  webview2_panel.py     painel WebView2 embutido (Windows)
  detection/            detector hibrido: imagem embutida + contorno
  ui/                   paineis da interface: PDF, resultado, estudo, revisao, dataset
  cli/                  entrypoints cvoff-*
app_tkinter.py          interface desktop
app_streamlit.py        interface web
tests/                  suite de testes
docs/                   analise tecnica, roadmap, especificacao, baseline e experimentos
CONTRIBUTING.md         como rodar as verificacoes e o que este projeto espera de um teste
data/labels.csv         rotulos (versionado)
data/splits.csv         particao treino/validacao/teste (versionado)
data/field_set.jsonl    paginas reais anotadas a mao para a avaliacao de campo (versionado)
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

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) -- como uma pagina vira uma FEN, e onde
  cada decisao mora
- [CONTRIBUTING.md](CONTRIBUTING.md) -- ambiente, verificacoes, como dirigir a interface
  sem clicar e o que se espera de um teste aqui
- [docs/ANALISE.md](docs/ANALISE.md) -- diagnostico do estado atual, com medicoes
- [docs/ROADMAP.md](docs/ROADMAP.md) -- fases de evolucao planejadas (Fases 0 a 6)
- [docs/SPEC.md](docs/SPEC.md) -- especificacao detalhada das melhorias (S-01 a S-36)
- [docs/ROADMAP_FASE7.md](docs/ROADMAP_FASE7.md) -- Fases 7 a 11, com a medicao de campo que
  as motiva: o gate rejeita 17 de 101 diagramas de pagina real contra 3 de 320 no split de teste
- [docs/SPEC_FASE7.md](docs/SPEC_FASE7.md) -- especificacao das Fases 7 a 11 (S-37 a S-63),
  incluindo os defeitos da Fase 7.0
- [docs/BASELINE.md](docs/BASELINE.md) -- o numero de referencia sobre recortes rotulados
  (0,9906 exata por tabuleiro) e como reproduzi-lo. Para o numero sobre paginas reais, que e
  outro e bem mais baixo, `cvoff-field` e `docs/metrics/field_*.json`
- [docs/EXPERIMENTS_FASE7.md](docs/EXPERIMENTS_FASE7.md) -- o que foi medido na Fase 7:
  o refino do contorno, e a normalizacao de tabuleiro que **nao** entrou (S-38, S-39)
- [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) -- o que foi medido na Fase 5, incluindo o
  que nao ajudou (memoria, workers, pesos de classe, arquitetura, TTA, ONNX)
