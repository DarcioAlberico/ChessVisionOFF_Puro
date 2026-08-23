# Chess Diagram OCR (OpenCV + PyTorch)

Projeto para extrair diagramas de xadrez em PDF, converter para FEN e melhorar a acuracia com treino incremental.

## Stack

- OpenCV: deteccao de tabuleiro e recorte por perspectiva.
- PyTorch: classificador de pecas por casa (13 classes: vazio + 12 pecas).
- python-chess: validacao e representacao de FEN/board.
- Tkinter + ttkbootstrap: **a** interface do produto (`app_tkinter.py`).
- Streamlit: demonstracao do servico no navegador (`examples/streamlit_demo.py`), nao e
  uma interface alternativa -- veja abaixo.
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

Nao ha dependencia de plataforma: a aba "Leitura" (WebView2, so-Windows) saiu na S-69, e com
ela o `pythonnet` e o `pywebview`. Para ler o livro com rolagem continua e busca de texto, o
botao **Abrir no leitor do sistema** entrega o PDF ao leitor padrao da maquina.

## Gerar o programa para Windows (sem Python)

```bash
uv sync --extra dev --extra packaging
uv run python packaging/build_windows.py
```

Sai em `dist/ChessVisionOFF/`. Zipe a pasta inteira: ela roda numa maquina Windows limpa,
sem Python e sem `uv`.

**Tamanho: o build grava em [docs/metrics/bundle.json](docs/metrics/bundle.json), e o numero
citado aqui e conferido contra esse arquivo por `tests/test_docs.py` (S-135).** A ultima
medida registrada e de **684 MB, 4.275 arquivos**, do build de 2026-08-18 (commit `9a683d1`).
Ela substitui a de 2026-08-09, que estava obsoleta -- e refaze-la achou uma coisa: o
`streamlit` de fato tinha saido, mas o `pythonnet` e o `clr_loader` **continuavam dentro do
bundle**, muito depois de a S-69 ter removido o codigo que os usava. O PyInstaller coleta o
que esta *instalado*, e nao o que o `pyproject.toml` declara; os dois entraram para os
`excludes` de `packaging/cvoff.spec`. 696 -> 685 (streamlit) -> **684 MB** (os dois).

E o build **completo** -- leitor *e* treinador. O peso vem quase todo do torch, e o torch
esta ali porque o ciclo que da valor ao projeto e *corrigir, salvar, treinar*: um bundle so
de leitura seria ~5x menor e nao teria o botao "Treinar modelo". O caminho para faze-lo esta
descrito em `packaging/cvoff.spec`, e e uma decisao de produto, nao de empacotamento.

O que fica **ao lado** do executavel, e nao dentro dele: `data/`, `models/`, `PDF/` e `PGN/`.
Isso e proposital -- o `labels.csv` e trabalho humano acumulado, e reinstalar nao pode
apaga-lo. Faca backup copiando a pasta.

Conferir uma instalacao nova, sem abrir a janela:

```bash
set CVOFF_LOG_DIR=logs
ChessVisionOFF.exe --selftest --page 80
```

Ele abre o primeiro PDF de `PDF/`, reconhece a pagina, escreve as FENs no log e confere que
o caminho de treino tambem montou. Codigos de saida: `0` ok, `2` sem PDF, `3` sem
checkpoint, `4` le mas nao treina, `1` falha ao reconhecer. Funciona igual num checkout
(`uv run python app_tkinter.py --selftest`).

Uma ressalva honesta:

- **O executavel nao e assinado.** O SmartScreen vai avisar na primeira execucao. Resolver
  isso exige um certificado de assinatura de codigo.

## Demonstracao no navegador (Streamlit)

```bash
uv run streamlit run examples/streamlit_demo.py
```

**Isto nao e uma segunda interface, e sim um exemplo.** Ela abre um PDF, reconhece os
diagramas e mostra a FEN e a legalidade -- tudo pelo mesmo `OcrService` que o Tkinter usa,
sem uma linha de reconhecimento propria. Serve para **ver** o resultado e para provar que o
pipeline nao depende de janela.

O que ela nao tem, e nunca teve: editor de posicao por clique, painel de legalidade com as
casas culpadas, fila de revisao e aba de dataset. Os quatro sao widgets de Tk, e sao onde
mora o fluxo de valor do produto -- *corrigir, salvar, treinar*. Ate a Fase 10 este README
a chamava de "interface web alternativa", o que prometia uma paridade que nao existe; a
S-54 escolheu desfazer a promessa em vez de perseguir ~1 semana de trabalho por um uso
remoto que ninguem pediu ainda.

## Comandos de linha

Depois da instalacao, **23 comandos** ficam disponiveis no ambiente -- a contagem sai de
`[project.scripts]` e e conferida por `tests/test_docs.py` (S-135). Todos aceitam `-v` para
log em nivel DEBUG, e todos falham em pt-BR com codigo de saida por classe (S-126). Os mais
usados estao abaixo; `--help` lista o resto.

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
# Higiene (S-63). Nenhuma das duas apaga nada: a linha cujo PNG sumiu vai para a quarentena
# (a FEN e trabalho humano e a imagem e reextraivel do livro), e o PNG sem linha e aposentado
# em data/orphans/<data>/. Depois delas, data/samples/ e labels.csv tem os mesmos nomes.
cvoff-audit --drop-missing --prune-orphans

# Migracao do labels.csv para o esquema com lado a jogar e origem. Cria backup;
# deduz o lado a jogar so onde a posicao o impoe, e deixa vazio o resto.
cvoff-migrate-labels

# Recuperar a procedencia dos rotulos orfaos (S-52): 98,6% do dataset nao sabe de que livro
# veio, e sem isso o split nao pode ser agrupado por livro. Casa cada PNG contra os diagramas
# dos PDFs por hash perceptual. Tres passos, e o terceiro e o unico que escreve.
cvoff-provenance --build --book "1937 Kemeri.pdf"   # indexa um livro. Caro: horas para o acervo
cvoff-provenance --match                            # relata taxa e histograma, sem gravar nada
cvoff-provenance --match --apply                    # grava a procedencia recuperada (com backup)

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

# Casar os diagramas com uma base de partidas em PGN (S-72/S-73). Preenche lance, vez e
# headers -- SO onde estiver vazio, e nunca sobrescreve o que voce digitou. Posicao que casa
# com mais de 5 partidas nao preenche nada: ali ela deixou de identificar qual partida e.
# A base e sua, fica em pgn_database/ e fora do repositorio. Nada sai da maquina.
# Exige o livro ja varrido na aba Galeria -- e dela que saem as posicoes e as legendas.
cvoff-games --all                         # relata, sem gravar nada
cvoff-games --all --apply                 # grava nas anotacoes da Galeria
cvoff-games --book "Karpov" --names       # so o caminho por nome: ~150 s, alcanca 12,6%
# O padrao (--positions) reproduz os lances da base inteira: ~104 min em dez processos, e
# alcanca todo diagrama. O custo e da PASSADA, nao do livro -- por isso `--all` de uma vez,
# e nao um `--book` por livro, que pagaria 32 vezes pela mesma varredura.

# Procedencia do lado a jogar no acervo (criterio de saida da Fase 8): amostra paginas de
# cada PDF e conta de onde veio o [SideToMoveSource] -- texto, OCR, legalidade ou assumido.
# Rodar com e sem --ocr responde em dois numeros o que o motor da S-43 entregou.
cvoff-sides
cvoff-sides --ocr rapidocr --json docs/metrics/sides_com_ocr.json

# Censo de deteccao (S-82): o que o detector ACEITA no acervo, contado por livro. Nao
# carrega modelo e nao pede rotulo humano -- e distribuicao, nao acuracia. Existe porque
# o projeto media leitura e nao media deteccao, e foi assim que o glifo de cavalo do
# cabecalho do "Secrets" entrou como diagrama em 71 paginas sem aparecer em relatorio
# nenhum. Ver docs/ANALISE_DETECCAO.md.
cvoff-census --csv docs/metrics/deteccao_base.csv
cvoff-census --pdf "PDF/1937 Kemeri.pdf" --all-pages
# O comando que decide se uma mudanca em deteccao presta: o que sumiu, e algum dos que
# sumiram era diagrama de verdade? --fail-on-loss transforma isso em portao.
cvoff-census --csv nova.csv --baseline docs/metrics/deteccao_base.csv --fail-on-loss

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

# O que do plano de reconhecimento de texto (S-178 a S-217) ja existe no disco.
# Olha o disco -- arquivo no lugar, simbolo definido, extra declarado --, e nao o
# documento; quem compara os dois e tests/test_text_status.py.
cvoff-texto-status                  # tudo, agrupado por fase
cvoff-texto-status --fase 25        # so uma fase
cvoff-texto-status --pendentes      # so o que falta
cvoff-texto-status --sondas         # cada sonda, e o que ela respondeu
cvoff-texto-status --json           # para a CI
cvoff-texto-status --exigir S-181   # portao: codigo 1 se o item nao esta inteiro

# A regua da ordem de leitura (S-194). A referencia e a ordem em que o proprio PDF emite os
# spans, independente da nossa medicao. Pagina cuja camada emite blocos fora da ordem de
# leitura e contada a parte, nao descartada.
cvoff-texto-ordem --por-livro 5
cvoff-texto-ordem --baseline docs/metrics/texto_ordem.json   # regressao de ordem e regressao

# A direcao em que cada livro numera a grade de exercicios (S-216). A referencia e o numero
# impresso na pagina, e nao a ordem de emissao: nos livros de grade do acervo a camada e do
# Adobe Acrobat Paper Capture, e ela erra a direcao em 1 pagina de grade a cada 7.
# O livro sem numeracao legivel (o Yusupov) e calibrado pela camada mesmo, e sai marcado
# "hipotese": true -- fora do acerto que o --baseline trava, e com o tau em duas colunas.
cvoff-texto-grade --por-livro 40
cvoff-texto-grade --baseline docs/metrics/texto_grade.json   # falha se o acerto cair
```

Os scripts `train_model.py`, `infer_pdf.py` e `export_pdf_pgn.py` na raiz continuam
funcionando como invocadores equivalentes (`uv run python infer_pdf.py ...`).

`cvoff-export` percorre todas as paginas, detecta os diagramas encontrados e salva um
jogo PGN por posicao. Sem `--output`, o arquivo vai para `PGN\<nome-do-pdf>.pgn`.

A exportacao e cancelavel e retomavel: a cada 5 paginas ela grava
`PGN\<nome>.partial.jsonl`, e uma execucao interrompida oferece retomar da pagina seguinte
a ultima concluida -- desde que os parametros sejam os mesmos. Concluir apaga o parcial.

O lado a jogar sai da legenda do PDF quando ela declara, da legalidade da posicao quando
ela impoe (o lado que nao joga nao pode estar em xeque), da partida que a base casou, da
escolha de quem estava com o livro aberto, e do padrao "brancas" quando nenhuma das outras
responde. O header `[SideToMoveSource]` diz **qual das 8** foi, sempre -- a maioria dos livros
do acervo nao declara nada, e um palpite precisa parecer um palpite.

| valor | de onde veio |
|---|---|
| `text` | declarado no texto do PDF |
| `ocr` | lido por OCR da legenda (S-42/S-43) |
| `text-page-scope` | declarado no cabecalho da pagina |
| `ocr-page-scope` | lido por OCR do cabecalho da pagina |
| `legality` | deduzido da legalidade da posicao |
| `database` | da partida que a base casou (S-72) |
| `manual` | escolhido a mao na Galeria |
| `default` | ninguem respondeu: "brancas", e o header marca o palpite como palpite |

A lista sai de `SideSource`, em `semantics.py`, e `tests/test_docs.py` falha se a tabela e o
`Literal` divergirem (S-135) -- ela ja disse "tres" enquanto o codigo declarava oito.

Para gravar o log em arquivo num checkout, defina `CVOFF_LOG_DIR`:

```bash
set CVOFF_LOG_DIR=logs
```

**No `.exe` isso nao e preciso**: o executavel nao tem console, e por isso grava sozinho em
`logs\chessvisionoff.log`, na pasta ao lado dele -- junto com `data\`, `models\`, `PDF\` e
`PGN\`. E o primeiro lugar a olhar quando a janela nao abre (S-127). A variavel continua
mandando se estiver definida, no `.exe` tambem.

## Recursos opcionais (e o que o projeto faz sem eles)

**O projeto funciona inteiramente offline.** Nada sai da sua maquina no uso padrao. As
integracoes abaixo sao desligadas por padrao e nao afetam o reconhecimento.

### Base de partidas (S-72/S-73)

Um ou mais `.pgn` que voce poe em `pgn_database/`. Com eles, a Galeria preenche **numero do
lance, vez a jogar e headers** dos diagramas cuja posicao aparece numa partida registrada -- e
a vez a jogar deixa de ser o palpite que a Fase 3 registrou como palpite.

**Todos os arquivos da pasta entram nas buscas (S-93).** Ate aqui era so o maior, e o custo
disso foi medido: numa pasta com duas gigabases, as 10,3 M partidas da segunda nunca eram
consultadas -- e a partida procurada estava la. Acrescentar um `.pgn` invalida o indice por
nome e o cache de posicoes, que avisam como refazer:

```bash
cvoff-games --build-index     # o indice por nome, sobre todas as bases da pasta
```

E **local**: o arquivo e lido do disco, nada e consultado na rede. Sem ele, os botoes "Buscar
por nome" e "Buscar pela posicao" dizem onde por um e o resto do produto segue igual.

Medido numa base de 10.547.416 partidas, no `Secrets of Chess Training` (1.408 diagramas):
**61 diagramas** pelo caminho por nome (~150 s) e **581** pelo caminho por posicao (~29 min
desde a S-85, eram 104).

Com as duas gigabases da pasta (18,9 GB, 20.902.903 partidas), medido em 2026-08-16 sobre os
mesmos 4 livros: os casamentos por posicao vao de **1.641 para 2.104** em 3.563 diagramas
(46,1% -> 59,1%), e a passada custa **56 min**. O preco esta declarado no plano: 981 diagramas
deixaram de ser "partida unica", e **63,5% disso e a mesma partida repetida nas duas bases**.

Os dois caminhos sao botao da Galeria e comando de linha. O por nome usa o que a legenda
declara; o por posicao (S-92) pergunta pelas **64 casas lidas** e por isso alcanca diagrama
sem nome nenhum impresso -- 53,9% do acervo, onde a legenda nao tinha o que oferecer. Ele
custa uma passada pelo arquivo inteiro, avisa disso antes, mostra em que pedaco esta e da para
cancelar. A resposta fica em `data/games_positions.sqlite`, **uma linha por colocacao**: a
segunda vez custa segundos, um livro novo custa so as posicoes que ele trouxer, e abrir um
livro le as colocacoes daquele livro e nao o acervo (S-140). Cancelar no meio **descarta a passada
inteira** -- meia base lida da contagens que nao valem, e e a contagem que decide se preencher
um header e honesto.

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

### Segunda opiniao: o botao "2a opiniao" (S-66)

Manda o **mesmo recorte** que esta no editor para um segundo leitor, local, e mostra a FEN
que ele devolve ao lado da sua. Serve para o diagrama em que voce nao tem certeza: duas
leituras independentes concordando valem mais que uma, e discordando dizem exatamente onde
olhar.

**Sao tres coisas separadas, e as tres precisam existir**: o extra, um clone do
[tsoj/Chess_diagram_to_FEN](https://github.com/tsoj/Chess_diagram_to_FEN) fora deste
repositorio (~232,8 MiB, incluindo o modelo), e o caminho dele nas preferencias.

```bash
uv sync --extra second-opinion
```

```jsonc
// data/settings.json
{
  "local_reader": {
    "path": "C:/caminho/para/Chess_diagram_to_FEN"
  }
}
```

**Sem qualquer uma das tres, o botao nao aparece** -- e quando aparece e falha, `tsoj_reader`
diz em pt-BR qual das tres falta. Opcional pelo mesmo motivo do `ocr`: quem ja tem dado do
proprio acervo corrige mais rapido no editor do que pedindo opiniao, e 232,8 MiB de clone e um
preco que so quem quer o recurso deve pagar.

**O que o produto faz sem ele:** tudo, menos este botao. A segunda opiniao nunca grava nada
sozinha -- adotar a leitura dela e um clique seu, e a procedencia registra que veio dali.

### OCR da legenda (S-42/S-43)

Le o texto **em volta do diagrama** nas paginas que nao tem camada de texto. Medido em
2026-08-14, quando o acervo tinha 27 livros: **7 deles sao scan puro** e saem inteiros como
`[SideToMoveSource "default"]`, mesmo quando a pagina tem `LAS BLANCAS JUEGAN PRIMERO`
impresso no topo. (Hoje o acervo tem 39 PDFs; os 12 que entraram depois nao foram
classificados, e por isso o denominador aqui continua 27.) Outros 5 livros tem
camada de texto que falha em parte das paginas.

Vem **desligado**, e para os outros 20 daqueles 27 deve continuar assim: onde a camada de texto
existe, ela responde melhor e de graca.

```bash
uv sync --extra ocr        # ~15 MB de modelos, que vem no wheel
```

```jsonc
// data/settings.json
{
  "ocr": {
    "enabled": true,
    "engine": "rapidocr",              // ou "easyocr", ou "tesseract"
    "languages": ["pt", "en", "es", "de"]
  }
}
```

Ou por linha de comando, que vence o arquivo:

```bash
cvoff-field  --ocr rapidocr            # mede o efeito contra o conjunto de campo
cvoff-export "PDF/livro.pdf" --ocr rapidocr
```

**O RapidOCR e o padrao porque nao baixa nada.** Os modelos vem no wheel, e ele roda no
`onnxruntime` que o extra `onnx` ja traz -- a promessa de "nada sai da sua maquina no uso
padrao" continua valendo com ele ligado. O **EasyOCR baixa ~100 MB de modelo na primeira
execucao**: e uma escolha legitima, le mais idiomas, e por isso mesmo precisa ser sua e nao
do padrao. O Tesseract usa o binario que voce ja tenha instalado.

**O quarto motor e de casa: `glifo` (S-181).** E o classificador de 292 classes portado do
`PyBoxEditor_Tkinter` -- digitos, caixa alta e baixa, acentuacao latina, ligaduras tipograficas
(`fi`, `ffl`), casas de xadrez coladas (`e4`, `xf6`), figurinas (`♔♕♖♗♘♙`) e simbolos de
avaliacao (`±`, `∓`, `⩲`, `∞`). Ele nao baixa nada, e e o unico que aplica o `allowlist` no
**decodificador** em vez de filtrar a saida: pedir `WB` faz o `B` vencer o `8` em vez de apagar
o `8` depois de escolhido.

Os pesos (2,6 MB) **nao vem no repositorio** -- `*.pt` e ignorado. O metadado que descreve as
classes vem (`models/char_meta.json`). Aponte o arquivo assim:

```bash
CVOFF_OCR_GLYPH_MODEL=/caminho/custom_model.pth cvoff-field --ocr glifo
```

ou grave `"glyph_model"` na secao `ocr` do `data/settings.json`. Sem os pesos o motor nao sobe,
o log diz onde apontar, e a varredura segue sem OCR -- o contrato de sempre.

O plano completo do reconhecimento de texto (colunas, tabelas, tarjas, PDF pesquisavel) esta em
[docs/ROADMAP_TEXTO.md](docs/ROADMAP_TEXTO.md), e `cvoff-texto-status` diz o que dele ja existe.

Tres coisas que o recurso **nao** faz, de proposito:

- nao roda na pagina inteira -- so na faixa em volta do diagrama, com o interior do tabuleiro
  apagado antes de o motor ver a imagem;
- nao roda onde a camada de texto respondeu, diagrama a diagrama;
- nao se disfarca de camada de texto: o PGN sai com `[SideToMoveSource "ocr"]` e, quando o
  motor nao teve certeza, com `[SideToMoveConfidence]` ao lado.

## Resolucao de problemas

| sintoma | causa provavel | o que fazer |
|---|---|---|
| Sumiu a aba **Leitura** do visualizador | saiu na S-69, junto com o WebView2 | o botao **Abrir no leitor do sistema** faz o mesmo, no leitor padrao da maquina. A pagina no app continua sendo a que reconhece, marca e recorta diagramas |
| Treino muito lento (~9 min por epoca) | `torch` `+cpu`, sem CUDA | ver [Desempenho](#desempenho-cpu-gpu-e-onnx). A barra de status diz qual dispositivo esta em uso |
| Todo diagrama sai como "brancas jogam" | o PDF nao tem camada de texto que declare o lado | e o esperado em 24 dos 27 livros medidos em 2026-08-14. O header `[SideToMoveSource "default"]` marca o palpite como palpite. Para os 7 livros de scan puro, ver [OCR da legenda](#ocr-da-legenda-s-42s-43) |
| `--ocr rapidocr` avisa que "o OCR pedido nao esta disponivel" | o extra nao esta instalado | `uv sync --extra ocr`. O comando segue sem OCR em vez de falhar, mas a saida nao tem legenda lida |
| `--ocr glifo` diz que os pesos "nao estao em models/char_classifier.pt" | os 2,6 MB do classificador de caracteres nao vem no repositorio | apontar o arquivo em `CVOFF_OCR_GLYPH_MODEL` ou em `ocr.glyph_model` no `data/settings.json`. O metadado das 292 classes ja esta em `models/char_meta.json` |
| `--ocr glifo` diz que o `.pt` "nao e o modelo descrito por char_meta.json" | os pesos e o metadado sao de rodadas de treino diferentes | e o esperado, e a recusa e o recurso: indices de outro treino apontam para as letras erradas **sem erro nenhum**. Repor o par completo |
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
3. Rodar OCR (melhor diagrama ou todos), **ou clicar direto no diagrama** que interessa: o
   visualizador marca com um retangulo numerado cada diagrama que o detector achou na pagina.
4. Corrigir a posicao no proprio tabuleiro: arrastar move a peca, botao direito apaga,
   a paleta insere. As casas em que o modelo esta inseguro aparecem tingidas de amarelo a
   vermelho, e o painel abaixo diz o que esta ilegal e em que casas. Ao lado do **Lado a
   jogar** ha o campo **Lance**, para o numero do lance impresso na legenda: ele grava na
   mesma anotacao que a aba **Galeria** edita e que a exportacao le, entao os dois lugares
   mostram sempre o mesmo numero. Em branco **apaga** a declaracao, em vez de gravar zero.
5. Salvar exemplos corrigidos.
6. Treinar modelo.
7. Repetir ciclo para reduzir correcoes manuais.

**Rolagem e zoom no visualizador.** A roda do mouse rola a pagina que estiver **sob o
ponteiro** -- nao importa onde esteja o foco do teclado. Chegando ao fim da pagina, insistir
na roda vai para a seguinte, que entra pelo topo (e para tras, pelo rodape); a caixa **Roda
vira a pagina** desliga isso para quem prefere que a roda so role. `Shift+roda` rola na
horizontal, `Ctrl+roda` amplia **ancorado no ponteiro** -- o ponto sob o cursor fica parado,
que e o que evita cacar de volta, na barra de rolagem, o diagrama que voce estava tentando
ver de perto. Arrastar com o botao esquerdo desloca a pagina (a mao do leitor); com o botao
do meio, funciona ate durante a selecao de area. **Ajustar a largura** (ou `Ctrl+0`) faz a
pagina caber na janela.

**Os diagramas marcados na pagina.** Ao trocar de pagina, o detector roda em segundo plano e
desenha um retangulo numerado sobre cada diagrama; o numero e o mesmo do seletor
"Selecionado" da aba **Resultado**. Clicar num retangulo abre aquele diagrama no editor --
lendo a pagina primeiro, se ela ainda nao tiver sido lida. O retangulo do diagrama que esta
aberto fica destacado, e ele acompanha as setas `←`/`→`: e ele que responde "qual desses eu
estou vendo?". A caixa **Marcar diagramas** desliga tudo isso para quem esta lendo o texto do
livro, e a escolha sobrevive ao fechamento da janela.

A **cor diz em que ponto do trabalho** aquele diagrama esta: azul e localizado pelo detector,
ambar e lido pelo OCR e ainda nao salvo, **violeta e a base de partidas reconheceu a posicao**
(S-75) e **verde e ja tem amostra no `labels.csv`**. O verde vem da procedencia gravada no CSV
e o violeta das anotacoes da galeria -- nenhum dos dois vem da memoria, entao os dois aparecem
assim que voce abre um livro que ja trabalhou antes, e respondem "onde eu parei?" sem custar
uma leitura. O violeta diz uma coisa que nenhuma outra marca da tela sabe dizer: **aquele
diagrama nao precisa de olho humano**, porque as 64 casas dele bateram com um lance de uma
partida registrada. O diagrama
aberto no editor e marcado por **borda dupla e mais grossa**, e nao por cor, justamente para
nao esconder o estado dele -- e nada e pintado por cima do tabuleiro, que e o que se esta
tentando conferir.

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
| `PageUp` / `PageDown` | pagina anterior / proxima do PDF |
| `Ctrl+0` | ajustar o zoom a largura da pagina |
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
  orientation.py        a cascata de regras que decide a orientacao do diagrama
  training.py           loop de treino (Trainer, TrainingPlan, BestEpochPolicy)
  detection/            detector hibrido: imagem embutida + contorno
  ui/                   paineis da interface: PDF, resultado, estudo, revisao, dataset
  cli/                  entrypoints cvoff-*
app_tkinter.py          interface desktop (--selftest confere uma instalacao sem abrir janela)
examples/               demonstracoes: streamlit_demo.py roda o servico no navegador
packaging/              cvoff.spec e build_windows.py: o .zip para Windows (S-55)
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
    primeira fila). Quase sempre sao erro real de reconhecimento, e ficam fora do treino.
  - **de turno**, que dependem de quem joga. Num diagrama de livro o lado a jogar nao
    esta na imagem e e preenchido como "brancas"; quando isso torna a posicao ilegal,
    quase sempre significa que era a vez das pretas. As pecas estao certas.

**"Quase sempre", e nao "sempre".** Um livro nao e feito so de posicoes jogaveis: um
capitulo sobre estrutura de peoes desenha o esqueleto sem rei nenhum, um estudo de final
mostra tres pecas, um tabuleiro vazio ilustra as coordenadas. Ler qualquer um desses
**corretamente** produz uma FEN fatalmente ilegal, e ate a fase anterior o programa se
recusava a grava-la -- perdendo justamente o rotulo certo.

Hoje ele pergunta, em vez de recusar. Salvar uma posicao fatalmente ilegal abre uma caixa
que diz o problema e as casas culpadas; **"sim"** grava a linha com a coluna `illegal_ok`
marcada, e **"nao"** cancela sem gravar nada. Quem sabe de qual dos dois casos se trata e
a pessoa que esta com o PDF aberto do lado.

A marca vale para o arquivo inteiro, e nao so para a caixa de dialogo: a amostra marcada
**entra no treino** (o classificador le casa a casa, e as 64 casas de um diagrama de
estrutura estao rotuladas certas), o `cvoff-audit` a lista a parte em vez de chama-la de
problema, e o `cvoff-audit --fix` nao a manda para a quarentena. Sem isso, o "sim" seria
uma pergunta sem consequencia: o comando seguinte tiraria a linha do arquivo. Corrigir o
rotulo depois, ja com os dois reis no lugar, limpa a marca sozinho.

## Dados e artefatos

O repositorio versiona apenas codigo, documentacao e `data/labels.csv`. Ficam de fora,
por tamanho ou por direito autoral:

| Caminho | Conteudo | Por que fora |
|---|---|---|
| `PDF/` | livros de origem | material protegido por direito autoral |
| `data/samples/` | 4.508 PNGs de tabuleiros, 3,9 GB | tamanho |
| `models/*.pt` | checkpoint treinado, ~8,7 MB | binario que muda a cada treino |
| `PGN/` | saida gerada | reproduzivel a partir dos PDFs |
| `pgn_database/` | sua base de partidas em PGN (as duas gigabases medidas aqui tem 18,9 GB) | material de terceiro, e o GitHub recusa acima de 100 MB |

Em um clone novo e preciso trazer seus proprios PDFs para `PDF/` e treinar o modelo
(`cvoff-train`) ou obter um checkpoint por outro meio.

## Documentacao tecnica

### Onde mora a spec de cada item (S-NN)

A spec deste projeto esta espalhada por cinco arquivos, e essa dispersao ja custou duas
entregas: a S-76 e a S-77 ficaram tres meses em documento nenhum, porque caiam na fenda entre
dois deles. Esta tabela e o indice, e `tests/test_docs.py` a confere contra o disco (S-134) --
tanto o item entregue sem secao quanto a secao no arquivo errado fazem a suite falhar.

| itens | arquivo |
|---|---|
| S-01 a S-36 | [docs/SPEC.md](docs/SPEC.md) |
| S-37 a S-77 | [docs/SPEC_FASE7.md](docs/SPEC_FASE7.md) |
| S-78 a S-82, S-143, S-175 | [docs/ANALISE_DETECCAO.md](docs/ANALISE_DETECCAO.md) |
| S-83 a S-94 | [docs/PLANO_BASE_PARTIDAS.md](docs/PLANO_BASE_PARTIDAS.md) |
| S-95 a S-142 | [docs/SPEC_FASE14.md](docs/SPEC_FASE14.md) |
| S-144 a S-170 | [docs/SPEC_UI.md](docs/SPEC_UI.md) |
| S-178 a S-217 | [docs/SPEC_TEXTO.md](docs/SPEC_TEXTO.md) |

A faixa da `ANALISE_DETECCAO` nao e contigua de proposito: **item de deteccao mora com os
outros de deteccao**, e nao com o numero vizinho. Foi assim que a S-143 entrou ali, ao lado da
S-80, que e a medicao que ela corrige.

Os arquivos de medicao -- `EXPERIMENTS.md`, `EXPERIMENTS_FASE7.md`, `BASELINE.md` -- tambem tem
secoes `S-NN`, e elas **nao** substituem a spec: trazem o que foi medido daquele item, nao o
criterio de aceite dele. A tabela acima e sobre a spec.

### Os documentos

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) -- como uma pagina vira uma FEN, e onde
  cada decisao mora
- [CONTRIBUTING.md](CONTRIBUTING.md) -- ambiente, verificacoes, como dirigir a interface
  sem clicar e o que se espera de um teste aqui
- [docs/ANALISE.md](docs/ANALISE.md) -- diagnostico do estado atual, com medicoes
- [docs/ROADMAP.md](docs/ROADMAP.md) -- fases de evolucao planejadas (Fases 0 a 6)
- [docs/SPEC.md](docs/SPEC.md) -- especificacao detalhada das melhorias (S-01 a S-36)
- [docs/ROADMAP_FASE7.md](docs/ROADMAP_FASE7.md) -- Fases 7 a 13, com a medicao de campo que
  as motiva: o gate rejeita 17 de 101 diagramas de pagina real contra 3 de 320 no split de teste
- [docs/SPEC_FASE7.md](docs/SPEC_FASE7.md) -- especificacao das Fases 7 a 13 (S-37 a S-75),
  incluindo os defeitos da Fase 7.0 e a Fase 12, que saiu de uso e nao de varredura
- [docs/ANALISE_DETECCAO.md](docs/ANALISE_DETECCAO.md) -- o glifo do cabecalho reconhecido
  como diagrama, os quatro danos medidos e o censo de candidatos (S-78 a S-82)
- [docs/PLANO_BASE_PARTIDAS.md](docs/PLANO_BASE_PARTIDAS.md) -- a base de partidas como fonte
  de verdade: o indice por nome, a busca por posicao e a escolha que vira procedencia
  (S-83 a S-94)
- [docs/ROADMAP_FASE14.md](docs/ROADMAP_FASE14.md) -- **Fases 14 a 19**, com a avaliacao de
  2026-08-16 que as motiva: as duas reguas do projeto -- o split de teste e o conjunto de
  campo -- estao contaminadas pelo que deveriam julgar, e a metrica primaria mede confianca
  e nao correcao
- [docs/SPEC_FASE14.md](docs/SPEC_FASE14.md) -- especificacao das Fases 14 a 19 (S-95 a
  S-142), com o indice de onde mora cada item da spec
- [docs/ROADMAP_UI.md](docs/ROADMAP_UI.md) -- **Fases 20 a 24**, a avaliacao de interface de
  2026-08-17 em tres passadas: o tema `ttkbootstrap` esta instalado e nenhum widget pede estilo,
  abaixo de ~1500x840 a janela apaga controles (em 1100x760 a fila de salvar fica inalcancavel),
  e azul e violeta significam coisas diferentes na pagina e no tabuleiro
- [docs/SPEC_UI.md](docs/SPEC_UI.md) -- especificacao das Fases 20 a 24 (S-144 a S-170):
  tokens de cor e tipografia, o piso da janela, cor com um significado so, barra de menus e
  rodape de janela, vocabulario e estados vazios
- [docs/ROADMAP_TEXTO.md](docs/ROADMAP_TEXTO.md) -- **Fases 25 a 31**, o plano de reconhecimento
  de texto: o levantamento dos dois projetos, a decisao de portar o classificador de 292 classes
  do PyBoxEditor_Tkinter em vez de depender dele ou reescrever, e os seis riscos que precisam de
  decisao do dono -- entre eles a procedencia das 608.407 imagens de caractere
- [docs/SPEC_TEXTO.md](docs/SPEC_TEXTO.md) -- especificacao das Fases 25 a 31 (S-178 a S-217):
  a fronteira e a prova de vida, segmentacao ate a linha, a coluna achada na imagem, os cinco
  casos que apagam texto (tarja, trama, texto girado, box de duas linhas, tabela), a base de
  608 mil, o que o texto lido serve e o laco que faz a base crescer. Cada item traz uma **sonda**,
  e `cvoff-texto-status` responde quais ja existem no disco
- [docs/BASELINE.md](docs/BASELINE.md) -- o numero de referencia sobre recortes rotulados
  (0,9906 exata por tabuleiro) e como reproduzi-lo. Para o numero sobre paginas reais, que e
  outro e bem mais baixo, `cvoff-field` e `docs/metrics/field_*.json`
- [docs/EXPERIMENTS_FASE7.md](docs/EXPERIMENTS_FASE7.md) -- o que foi medido na Fase 7:
  o refino do contorno, e a normalizacao de tabuleiro que **nao** entrou (S-38, S-39)
- [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) -- o que foi medido na Fase 5, incluindo o
  que nao ajudou (memoria, workers, pesos de classe, arquitetura, TTA, ONNX)
