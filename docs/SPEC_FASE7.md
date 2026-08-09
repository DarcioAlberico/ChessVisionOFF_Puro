# Especificação das melhorias — Fases 7 a 11 (S-37 a S-63)

Continuação de [SPEC.md](SPEC.md), que cobre S-01 a S-36. Sequenciamento e a medição que
motiva cada item: [ROADMAP_FASE7.md](ROADMAP_FASE7.md).

Os itens **S-56 a S-61** vêm primeiro no documento porque são **defeitos abertos hoje**, não
melhorias. A numeração é maior porque foram encontrados na segunda passada da análise, depois
de S-37 a S-55 já estarem escritos.

Mesma convenção da SPEC.md: cada item tem **Problema** (com referência ao arquivo e à linha
de hoje), **Solução**, **Interface proposta**, **Critério de aceite** e **Testes**. Nomes de
módulo são sugestão; o que importa é a fronteira de responsabilidade.

Toda medição citada foi feita em 2026-08-09 sobre o commit `ee308dd`, com
`models/piece_classifier.pt` e os 27 PDFs de `PDF/`.

---

# Fase 7.0 — Defeitos

Os seis itens abaixo não são melhorias. São coisas quebradas hoje, e três delas anulam
garantias que a documentação afirma.

## S-56 · `ensure_splits` nunca é chamada: a amostra salva não chega ao treino

**Problema.** `splits.ensure_splits:132` existe, está correta, tem teste, e faz exatamente o
que o docstring diz: *"Carrega os splits existentes e atribui split apenas às amostras
novas."* **Nenhum código de produção a chama.** Verificado por varredura da árvore: todos os
consumidores usam `load_splits`, que só lê —

```
training.train_model:391      splits_map = load_splits(Path(splits_path)) ...
cli/evaluate.py:176           splits = load_splits(args.splits)
cli/experiment.py:41          splits = load_splits(args.splits)
cli/export_onnx.py:87         splits = load_splits(args.splits)
dataset_browser.py:111        splits = load_splits(splits_path) ...
```

A cadeia do defeito:

1. O usuário corrige um diagrama e salva → `dataset.append_training_sample` grava a linha no
   `labels.csv`. **Nenhum split é atribuído.**
2. O usuário clica "Treinar modelo" → `train_model(splits_path=...)` → `load_splits`.
3. `dataset.BoardFenDataset._load_entries:168`:
   ```python
   if self.splits.get(filename) != self.split:
       continue
   ```
   `None != "train"` → a amostra é descartada.

Medido em 2026-08-09:

```
data/splits.csv : train 2.569 · val 306 · test 320   = 3.195
data/labels.csv : 3.240 rótulos utilizáveis
                                                       -------
invisíveis ao treino por falta de split:                   45
```

As 45 são as únicas com procedência preenchida (`source_pdf`, `source_page`,
`detection_source`) — as mais recentes, salvas depois da S-31, e as que mais custaram
trabalho.

O descarte é mudo em três níveis: `_load_entries` avisa sobre imagem ausente e rótulo ilegal
e **não** sobre este caso; o log do treino diz *"Split persistido em uso: 2.569 tabuleiros de
treino"*, número que já as exclui; e a aba Dataset as mostra normalmente, porque
`dataset_browser` não filtra por split.

A intenção do código está certa — *"para que uma amostra nova nunca entre por acidente no
conjunto de teste"*. Sem ninguém atribuindo o split, "nunca entra por acidente" virou "nunca
entra". Isto anula os passos 5→6→7 do fluxo recomendado do README.

**Solução.** Três partes, e as três são necessárias:

1. **`train_model` passa a chamar `ensure_splits`**, não `load_splits`, com os nomes do
   `labels.csv` e os grupos de duplicata (`audit.find_duplicate_groups`) — que é a assinatura
   que `ensure_splits` já pede e que garante que membros do mesmo grupo caiam juntos.
   Amostra nova recebe split **antes** do treino, e `save_splits` grava.
2. **`_load_entries` passa a avisar.** Toda entrada descartada por falta de split vira um
   `warning` com a contagem e os três primeiros nomes — o mesmo padrão que já existe para
   imagem ausente (`dataset.py:189`) e rótulo ilegal (`dataset.py:198`). Silêncio foi o que
   deixou isso passar por semanas.
3. **`cvoff-audit` passa a reportar** `amostras sem split registrado` como uma linha própria
   do relatório, ao lado de "imagens órfãs" e "amostras redundantes".

**A ressalva que o item precisa carregar.** Atribuir split é irreversível na prática: por
desenho da S-07 o bucket vem do hash do nome, e uma amostra que cair no `test` fica lá para
sempre. Rodar `ensure_splits` sobre as 45 manda ~4 ou 5 delas para um conjunto de teste que
nunca poderá ser treino. É o comportamento correto — mas o CLI deve **listar o que vai
atribuir e pedir confirmação** na primeira vez, como `cvoff-audit` já faz para suas correções.

**Interface proposta.**

```python
# training.py
splits_map = ensure_splits(
    filenames=[e.filename for e in LabelStore(csv_path).read()],   # S-51
    splits_path=Path(splits_path),
    groups=find_duplicate_groups(csv_path, samples_dir),
) if splits_path is not None else None

# cli/train.py
--assign-splits / --no-assign-splits   # padrão: atribui, e diz quantas atribuiu
```

**Critério de aceite.** Depois de salvar uma amostra nova, um treino subsequente a inclui —
verificável contando `len(dataset.entries)` antes e depois. As 45 amostras atuais entram, e o
relatório diz para que split cada uma foi. Nenhuma amostra já registrada muda de split
(garantia da S-07, e é o teste que a protege).

**Testes.** CSV com 10 amostras e `splits.csv` com 8: o dataset de treino vê as novas depois
de `ensure_splits` e não vê antes. Uma amostra de grupo redundante herda o split do grupo.
Um teste de regressão que **falha** se algum módulo de produção voltar a chamar `load_splits`
onde deveria chamar `ensure_splits`.

---

## S-57 · O lock do modelo cobre um caminho dos três, e o checkpoint não é atômico

**Problema.** O `ARCHITECTURE.md` afirma que o modelo *"fica sob lock durante o uso, não só
durante a carga"*. Verificado: vale para **um** dos três caminhos longos.

| operação | thread | como obtém o modelo |
|---|---|---|
| OCR de uma página | `app_tkinter._ocr_worker` | `OcrService.model_session` — **sob lock** ✅ |
| exportação | `ui/export_controller:192` → `save_pdf_positions_to_pgn` → `pdf_to_pgn.iter_pdf_diagrams:410` | `load_model()` direto ❌ |
| varredura da fila | `ui/review_panel:256` → `build_review_queue` → o mesmo `iter_pdf_diagrams:410` | `load_model()` direto ❌ |
| treino | `ui/training_dialog:199` | reescreve o `.pt` ❌ |

O outro lado da corrida: `checkpoint.save_checkpoint:121` chama `torch.save(payload, path)`
direto no destino. O módulo `atomic_io` existe para isso e o docstring dele lista os três
arquivos que protege — estado da app, fila de revisão e `labels.csv`. **O checkpoint não está
na lista**, e é o maior dos quatro (8,7 MB), o mais demorado de escrever e o único cuja
escrita acontece numa thread de fundo enquanto outra o lê.

Ironia útil: o caminho **rápido** (OCR de uma página, ~2 s) é o protegido; os **longos** —
exportação de um livro de 1.121 páginas, varredura de fila — não são, e são justamente os que
coexistem com um treino.

**Solução.**

1. **`iter_pdf_diagrams` aceita um modelo já carregado.** Assinatura ganha
   `model_session: AbstractContextManager[tuple[Any, str]] | None`. Quando informado, usa; sem
   ele, cai no `load_model` de hoje (os CLIs continuam funcionando sem serviço).
   `ExportController` e `ReviewPanel` passam `service.model_session()`.
2. **`save_checkpoint` passa pelo `atomic_io`**: `torch.save` para um `io.BytesIO`, e
   `atomic_write_bytes` no destino. Três linhas, e o módulo já existe.
3. **`ARCHITECTURE.md` corrigido** — hoje a tabela de threads afirma algo que o código não
   faz, e uma documentação errada é pior que ausente.

4. **`ScanParams` passa a identificar o modelo, não o caminho.** `export_checkpoint.ScanParams`
   guarda `model_path` para decidir se um parcial pode ser retomado, e o docstring do módulo
   promete que retomar "com outro modelo" descarta o parcial. Ele compara o **caminho**. Como
   o treino reescreve sempre o mesmo `models/piece_classifier.pt`, a sequência realista —
   exportar metade de um livro, cancelar, treinar, retomar — produz um PGN com metade das
   posições lidas pelo modelo antigo e metade pelo novo, **sem aviso**. `ScanParams` ganha a
   identidade do checkpoint (tamanho + mtime, ou o `best_metric`/`git_commit` que a S-27 já
   grava nos metadados), e retomar com identidade diferente descarta o parcial como já faz
   para DPI diferente.

**Critério de aceite.** Nenhum `load_model` fora de `inference.py`, `service.py` e dos CLIs —
verificável por teste de varredura. Um `save_checkpoint` interrompido no meio deixa o arquivo
anterior intacto (testável escrevendo com um `torch.save` que levanta no meio). Exportação e
OCR concorrentes carregam **um** modelo, não dois.

**Testes.** Duas threads, uma em `model_session` e outra chamando `invalidate_model`: a
segunda espera. `save_checkpoint` que falha no meio → o `.pt` anterior continua carregável.

---

## S-58 · `source_page` e `source_diagram` viram `float` no round-trip

**Problema.** `append_training_sample:421` grava `str(source_page)` de um `int` — sai `20`. Na
gravação seguinte, `_write_labels:438` faz `pd.read_csv` do arquivo inteiro; como a coluna tem
célula vazia em 98,6% das linhas, o pandas a tipa como `float64`, e `20` volta como `20.0`.

O diff atual do `data/labels.csv` mostra o sintoma:

```diff
-...,A Matter of Endgame Technique.pdf,20,1,contour,...
+...,A Matter of Endgame Technique.pdf,20.0,1.0,contour,...
```

E o arquivo hoje tem os **dois** formatos: a última linha traz `8,6` e as anteriores
`8.0,6.0`.

Três consequências: o arquivo tem dois formatos para a mesma coluna; toda gravação suja linhas
alheias (ruído de diff num arquivo de 3.241 rótulos de trabalho humano); e
`DatasetEntry.source_page` é a string `"20.0"`, que a aba Dataset exibe e que a S-52 teria de
normalizar antes de casar qualquer coisa.

**Solução.** `_write_labels` (ou `LabelStore` depois da S-51) lê com
`dtype=str, keep_default_na=False`. É a leitura correta para este arquivo: **todas** as
colunas são texto, e o único motivo de o pandas inferir tipo aqui é que ninguém lhe disse o
contrário. Resolve de passagem o `_cell:27`, que existe só para lidar com o `NaN` que
`keep_default_na=False` impede de existir.

Migração: um passe único que normaliza `N.0` → `N` nas duas colunas, com backup — o mesmo
padrão de `migrate_labels_csv`.

**Critério de aceite.** Gravar uma amostra nova produz um diff de **exatamente uma linha**.
Nenhum valor `N.0` no arquivo depois da migração. `DatasetEntry.source_page` de uma amostra da
página 20 é `"20"`.

**Testes.** Round-trip: ler e regravar um CSV sem alterações produz bytes idênticos — é o
teste que pega qualquer coerção futura. Um CSV com `source_page` vazio em algumas linhas e
preenchido em outras não converte nenhuma.

---

## S-59 · O consentimento da S-32 não sobrevive a um redirect

**Problema.** A S-32 promete que o aviso antes do primeiro envio "nomeia o host de destino" e
que o consentimento fica gravado **por endereço** — trocar o endpoint volta a perguntar. Dois
buracos:

1. **`predict_fen_via_net:161`** usa `urllib.request.urlopen`, que segue redirects por padrão.
   Um `302` manda a imagem do tabuleiro para um host que o usuário nunca aprovou, e nada no
   log registra o desvio. O log diz `"Enviando tabuleiro para correcao externa em %s"` com a
   URL configurada, que passa a não ser o destino real.
2. **`HttpFenProvider.__init__:65`** só verifica que a string não é vazia. `file://`, `ftp://`
   e `data:` são esquemas que `urlopen` aceita; com `CVOFF_REMOTE_FEN_URL=file:///C:/...`, o
   "provedor remoto" lê um arquivo local e tenta interpretá-lo como JSON.

Nenhum dos dois é explorável de fora — o endpoint é declarado pelo usuário, e o retorno tem de
ser um JSON com `results[0].fen`. Mas os dois enfraquecem exatamente a garantia que a S-32
existe para dar, e o custo de fechá-los é de poucas linhas.

**Solução.**

```python
ALLOWED_SCHEMES = frozenset({"http", "https"})

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError(
            f"O serviço redirecionou para {urlsplit(newurl).netloc}, que não é o host "
            f"autorizado. Nada foi enviado para lá."
        )
```

`HttpFenProvider` valida o esquema na construção — falhar ali, e não no envio, é a mesma
decisão que o construtor já toma para URL vazia, e pela mesma razão: um provedor inválido não
deveria chegar a existir, porque é a existência dele que faz a UI oferecer o botão.

**Critério de aceite.** Endpoint com esquema diferente de `http`/`https` é recusado na
construção, com mensagem em pt-BR. Um redirect aborta o envio e nomeia o host de destino.

**Testes.** `HttpFenProvider("file:///etc/passwd")` levanta. Um servidor de teste que responde
`302` produz `RuntimeError` nomeando o host, e o corpo **não** chega ao destino do redirect.

---

## S-60 · Fechar a janela durante treino ou exportação descarta em silêncio

**Problema.** `app_tkinter._on_close:390` grava o estado, destrói o leitor WebView2, fecha o
motor de análise e chama `root.destroy()`. Não pergunta nada.

As oito threads do app são `daemon=True` e nenhuma é aguardada. Um treino de ~9 min por época
em CPU, ou uma exportação de um livro de 1.121 páginas, morre no `destroy` sem uma palavra. O
treino **não tem cancelamento** (o `ARCHITECTURE.md` registra isso na tabela de threads), então
fechar a janela é o único jeito de pará-lo — e é o jeito que pode corromper o `.pt`, pela
S-57.

A exportação tem checkpoint parcial (S-24) e sobrevive; o treino não tem nada equivalente.

**Solução.** Um registro de operações longas no app, e `_on_close` consultando-o:

```python
class BusyRegistry:
    """O que está rodando agora, e se dá para interromper sem perder trabalho."""
    def register(self, name: str, *, cancellable: bool, loses_work: bool) -> Token: ...
    def running(self) -> list[BusyOperation]: ...
```

Fechar com operação registrada abre um diálogo que **nomeia** o que está rodando e o que se
perde: "Um treino está em andamento (época 3 de 8). Fechar agora descarta o progresso desde a
última época melhor." Três respostas — cancelar o fechamento, fechar mesmo assim, ou (quando
cancelável) pedir o cancelamento e esperar.

Junto: o treino ganha `cancel_event`, conferido entre épocas — o mesmo desenho que
`iter_pdf_diagrams:414` já usa entre páginas, e pela mesma razão. O pior caso de resposta ao
cancelamento passa a ser uma época.

**Critério de aceite.** Fechar durante o treino pergunta. Cancelar o treino entre épocas
preserva o melhor checkpoint gravado até ali. Fechar sem operação em curso continua imediato.

**Testes.** `BusyRegistry` testável sem Tk. `train_model` com `cancel_event` já setado no
início devolve um `TrainingRun` vazio sem tocar no `.pt`.

---

## S-61 · O custo de uma varredura: duas ineficiências estruturais

**Problema.** Perfil de uma página do Karpov 1 (6 diagramas, 220 DPI, CPU):

| etapa | tempo |
|---|---|
| `render_pdf_page` | 0,043 s |
| `detect_diagrams_in_pdf_page` | 0,562 s |
| `contexts_for_pdf_page` | 0,104 s |
| inferência dos 6 diagramas (`auto`) | **2,237 s** |
| total | **~2,95 s/página** |

Extrapolado, ~10 h para o acervo inteiro (~12 mil páginas). Duas ineficiências aparecem:

**(a) A orientação automática custa exatamente o dobro.** Medido no mesmo diagrama:
`predict_with_orientation(mode="auto")` = 0,104 s contra `mode="0"` = 0,050 s. Ela roda o
modelo duas vezes, sempre. Como a inferência é 76% do tempo de página, **cerca de metade de
toda varredura é gasta lendo cada diagrama de cabeça para baixo.**

**(b) Três aberturas de documento por página.** `render_pdf_page`,
`detect_diagrams_in_pdf_page` e `contexts_for_pdf_page` chamam `_open_document` cada uma. Os
docstrings de `detect_diagrams_in_pdf_page:189` e `contexts_for_pdf_page:898` chamam isso de
irrelevante ao lado do render. Medido, depende muito do livro:

| livro | páginas | `fitz.open` | custo total numa varredura |
|---|---|---|---|
| Polgar 5334 | 1.184 | 1,16 ms | 4,1 s |
| Karpov 1 | 402 | 5,25 ms | 6,3 s |
| **Yusupov (todos os volumes)** | **2.612** | **28,80 ms** | **225,7 s** |

Para quase todo o acervo o docstring está certo. Para o maior livro são quase 4 minutos de
parsing de xref, e a diferença entre o melhor e o pior caso é de **50×**.

**Solução.**

**(a)** Duas medidas, e a segunda depende da S-45:
- **Lote único.** As duas orientações vão num único `forward` de 128 casas em vez de dois de
  64. Não corta a computação, corta o overhead por lote — que em CPU não é desprezível.
- **Atalho por coordenadas.** Quando a S-45 lê as coordenadas, a orientação está decidida e a
  segunda leitura não acontece. `OrientationPolicy` (S-48) é onde esse atalho mora, porque a
  regra das coordenadas vem antes de todas.

**(b)** Um objeto de documento aberto, passado pelo pipeline em vez de um caminho:

```python
@dataclass
class OpenPdf:
    """Documento aberto uma vez, emprestado ao pipeline de uma página.

    Existe porque `_open_document` era chamado três vezes por página. As assinaturas por
    caminho ficam -- são a porta dos CLIs -- e passam a delegar.
    """
    source: PdfSource
    doc: fitz.Document
    def page(self, index: int) -> fitz.Page: ...
```

`iter_pdf_diagrams` abre uma vez por varredura e empresta. As funções por caminho continuam
existindo e passam a ser invólucros — nenhum chamador quebra.

**Critério de aceite.** Uma abertura por página (verificável instrumentando
`_open_document`). Nenhuma mudança de resultado: as FENs de uma varredura antes e depois são
idênticas. Ganho reportado no EXPERIMENTS.md, por livro — incluindo os em que não houve.

**Testes.** Um contador de aberturas num teste de varredura de 3 páginas: 3, não 9.
Comparação de FEN antes/depois num PDF sintético.

---

# Fase 7 — Ler o acervo que existe

## S-37 · O ambiente não pode desligar 611 testes em silêncio

**Problema.** `.venv/Lib/site-packages/__editable__.chessvisionoff_puro-0.1.0.pth` contém
`C:\PythonChess\ChessVisionOFF_Puro\src` — o caminho de onde o projeto foi movido, e que não
existe mais. Resultado hoje:

```
$ pytest -q
33 errors during collection    # ModuleNotFoundError: No module named 'chess_diagram_ocr'
$ mypy
error: uv trampoline failed to canonicalize script path
$ PYTHONPATH=src pytest -q
611 passed, 498 subtests passed in 32.99s
```

O código está inteiro. O que quebrou foi o ponteiro do ambiente, e **nada no repositório
notou**: não há `tests/conftest.py`, e `[tool.pytest.ini_options]` só declara `testpaths`. A
suíte depende inteiramente de o pacote estar instalado em modo editável. Um clone movido, um
`.venv` copiado entre máquinas ou um checkout em outro caminho desligam 611 testes, e o
sintoma — 33 arquivos com `ImportError` — parece muito pior do que é.

O CI não pega: `uv sync --frozen` num runner limpo instala sempre no caminho certo.

**Solução.** Duas guardas independentes, porque resolvem falhas diferentes:

1. **`pythonpath` no pytest** — a suíte passa a rodar num checkout sem instalação:
   ```toml
   [tool.pytest.ini_options]
   testpaths = ["tests"]
   pythonpath = ["src"]
   ```
   Não substitui a instalação editável: o CI continua verificando que o pacote é importável
   de fora do diretório (passo que já existe no workflow). Garante só que **a suíte** não
   dependa dela.

2. **Teste de sanidade do ambiente** — um teste que falha com mensagem em pt-BR quando o
   `.pth` aponta para um caminho inexistente, dizendo o comando que conserta:
   ```
   O ambiente aponta para C:\PythonChess\... , que não existe.
   O projeto foi movido? Rode: uv sync --extra dev
   ```
   Um teste que falha explicando vale mais que 33 que falham em `ImportError`.

Aproveitar para acrescentar ao CI uma matriz mínima: hoje roda só `windows-latest`. O código
não tem nada de específico de Windows fora do WebView2 (que já é `sys_platform == 'win32'`) e
de `os.linesep` em `dataset._write_labels` — um job `ubuntu-latest` que pule os testes de Tk
custa 2 min e pega regressão de portabilidade.

**Interface proposta.** `tests/conftest.py` novo, com o teste de sanidade e nada mais.

**Critério de aceite.** `pytest` verde num clone recém-movido, **sem** `uv sync`. `mypy`
volta a rodar. Um `.pth` quebrado produz uma falha nomeada, não 33 `ImportError`.

**Testes.** O próprio teste de sanidade; e um teste que verifica que `pyproject.toml` declara
`pythonpath`, para que a guarda não seja removida sem intenção.

---

## S-38 · `BoardVerifier` — um candidato precisa parecer um tabuleiro

**Problema.** Nenhuma das duas fontes de candidato exige que o recorte pareça um tabuleiro.

No caminho de contorno, `board_detection._extract_candidate_quads:249` combina geometria e
textura assim:

```python
score = geom_score * (0.55 + 0.45 * pattern_score)
```

`_board_pattern_score` é um bom sinal — medido, dá **1,0000** num tabuleiro real de casas
hachuradas (Euwe Band 1-2, p25) e **0,2252** numa coluna de texto corrido (Karpov 1, p80).
Mas ele nunca é gate: com `pattern_score = 0` o candidato ainda fica com 55% da nota de
geometria, e o piso de aceite é `min_score = max(0,06, top_score × 0,25)`.

**A hipótese acima está pela metade, e foi a S-41 que mostrou onde.** A análise atribuía o
lixo do `Karpov 1` p80 -- `1q1KK1q1/3KK1P1/3PP3/qP2K1Pq/3KKP1P/2n1Kp1q/P1qP3P/K1R2k1K`, oito
reis brancos, confiança 0,0004 -- ao detector escolhendo uma região errada. Não é isso: as
seis caixas daquela página estão **corretas**, sobre os seis diagramas reais.

O que produz o lixo é `detection/hybrid.refine_candidate_with_contour`, que roda o contorno
**dentro** do bbox já correto para alinhar o recorte e, quando acha o quad errado, troca um
recorte perfeito por um trapézio de texto. Medido nos seis candidatos, `_board_pattern_score`
do recorte cru contra o refinado:

| candidato | cru | refinado | |
|---|---|---|---|
| #0 | 0,3138 | 0,6042 | melhora |
| #1 | 0,2000 | 0,4616 | melhora |
| #2 | 0,3511 | **0,2388** | **piora** |
| #3 | 0,2000 | 0,4271 | melhora |
| #4 | 0,2892 | **0,2252** | **piora — é o dos oito reis** |
| #5 | 0,3306 | 0,5059 | melhora |

O refino ajuda em quatro e atrapalha em dois, e num dos dois o estrago é total. O docstring
dele já tem o raciocínio certo -- *"devolve o candidato original quando o contorno não acha
nada na região, caso em que o recorte cru é o melhor que se tem, e não há razão para
piorá-lo"* --, só que ele confere se achou **alguma coisa** e nunca se o que achou é
**melhor**.

Isso torna a S-38 mais barata e mais precisa: a primeira metade dela deixa de ser um gate
novo e passa a ser uma comparação de `BoardEvidence` antes e depois do refino.

No caminho embutido é pior: `detection/embedded.candidates_from_embedded_images:277-314`
filtra por **tamanho nativo mínimo, proporção e cobertura da página**, e nunca olha os
pixels. Uma imagem quadrada de 400×400 que seja foto, logotipo ou selo entra com
`detector_score` até 1,0.

O gate de exportação da S-15 pega o resultado — vai para `.review.pgn`. Mas o falso positivo
já consumiu uma vaga de `max_boards`, entrou na numeração `[Diagram "n"]` (que a S-14 existe
para manter estável) e apareceu no editor como um diagrama a conferir.

**Solução, em duas metades.** A primeira é a que a S-41 revelou e sai quase de graça; a
segunda é a que estava especificada.

**(a) O refino não pode piorar.** `refine_candidate_with_contour` compara a evidência do
recorte cru com a do refinado e fica com o melhor. Uma linha de decisão, e ela resolve o caso
patológico inteiro. Faz sentido medi-la **isolada** antes da parte (b): se ela sozinha levar a
taxa de exportação de 0,6842 para perto do alvo, o piso da parte (b) pode ser mais
conservador, e piso conservador perde menos diagrama verdadeiro.

**(b) Um verificador único no fim.** Extrair a verificação para uma classe, aplicada **uma
vez, no fim de `detect_diagrams`, a todo candidato independentemente da fonte**. Isso é o
oposto de espalhar o filtro: hoje há meio filtro numa fonte e nenhum na outra.

Sinais, todos já calculáveis a partir do recorte 320×320 que a verificação renderiza:

| sinal | o que é | por que |
|---|---|---|
| `checker` | contraste médio entre casas de paridade oposta | já existe em `_board_pattern_score` |
| `grid` | periodicidade dos picos de gradiente em 1/8 do lado | já existe |
| `ink_balance` | fração de pixels escuros por casa, e o desvio entre casas | coluna de texto tem tinta uniforme; tabuleiro tem casas vazias |
| `border` | presença de uma moldura fechada nos 4 lados | separa diagrama de recorte de página |

O veredito é um **piso**, não um peso — é a mudança que importa. Piso inicial sugerido:
`pattern_score ≥ 0,30`, que no caso medido mata o falso positivo (0,2252) e preserva o pior
diagrama real da mesma página (0,34). O número precisa ser **derivado** do conjunto de campo
da S-41, não fixado por este exemplo; e o piso é configurável para que a S-41 possa varrê-lo.

**Interface proposta.**

```python
# src/chess_diagram_ocr/detection/verify.py

@dataclass(frozen=True)
class BoardEvidence:
    checker: float
    grid: float
    ink_balance: float
    border: float
    score: float
    """Combinação; é o que substitui o antigo `_board_pattern_score`."""

    def rejected_because(self, floor: float) -> str:
        """Motivo em pt-BR, ou "" se passou. Vai para o log e para o painel de detecção."""

class BoardVerifier:
    def __init__(self, *, floor: float = BOARD_SCORE_FLOOR) -> None: ...
    def evidence(self, board_rgb: np.ndarray) -> BoardEvidence: ...
    def accepts(self, board_rgb: np.ndarray) -> bool: ...
    def filter(self, candidates: Sequence[DiagramCandidate]) -> list[DiagramCandidate]:
        """Descarta o que não passa, e **loga cada descarte com os quatro sinais**."""
```

O log de descarte não é zelo: é o mesmo raciocínio do aviso de `max_boards` da Fase 5 — cortar
candidato em silêncio foi o que fez o nono diagrama do Aagaard sumir sem que nada dissesse.

`DiagramCandidate` ganha `evidence: BoardEvidence | None`, que a `RecognizedDiagram` carrega
até a UI. A barra de status passa a poder dizer *por que* um candidato foi recusado.

**Critério de aceite.**
- O falso positivo da Karpov 1 p80 é recusado, e os 6 diagramas reais da mesma página passam.
- Sobre o conjunto de campo da S-41: **zero perda de diagrama verdadeiro** e redução mensurável
  de falso positivo. Se um diagrama verdadeiro cair, o piso está errado e o item não fecha.
- Nenhum candidato, de nenhuma fonte, chega ao classificador sem passar pelo verificador.

**Testes.** Recorte sintético de tabuleiro (casas alternadas) passa; recorte de ruído
uniforme, de gradiente e de linhas horizontais (texto) é recusado. Um teste com o recorte real
do falso positivo, versionado como fixture pequena. Um teste que garante que
`candidates_from_embedded_images` passa pelo verificador — hoje ele não passa por nada.

---

## S-39 · `BoardNormalizer` — o pré-processamento tem de conhecer o papel

**Problema.** `model.preprocess_cell_to_tensor:158` é todo o pré-processamento que existe:

```python
image = cv2.cvtColor(cell_rgb, cv2.COLOR_RGB2GRAY)
resized = cv2.resize(image, (arch.image_size, arch.image_size), interpolation=cv2.INTER_AREA)
normalized = resized.astype(np.float32) / 255.0
```

Sem normalização de iluminação, sem equalização local, sem supressão de trama, sem correção
de rotação residual, sem normalização por tabuleiro. O acervo tem, medido nas páginas
renderizadas:

| degradação | onde | efeito |
|---|---|---|
| casas escuras **hachuradas** com linhas diagonais | Euwe Band 1-2, Kemeri | textura de alta frequência que sobrevive ao resize para 64×64 |
| **transparência do verso** (texto do outro lado da folha) | Kemeri | manchas de tinta dentro de casas vazias |
| papel amarelado, fundo não branco | todos os scans de 1956–1980 | desloca a média de brilho de todo o tabuleiro |
| marca d'água | Kemeri (`DIGAR`, azul) | tinta forte fora do domínio |
| granulação e artefato de JPEG | scans de baixa qualidade | ruído sal-e-pimenta |

O caso decisivo: **Euwe Band 1-2, página 25.** O recorte está perfeito — grade alinhada,
tabuleiro inteiro, `_board_pattern_score` de 1,0000 — e a leitura sai com `min_confidence` de
**0,0000** e posição errada. Não é problema de detecção nem de capacidade do modelo. É que a
casa hachurada não existe no domínio de treino.

**Solução.** Uma classe que normaliza o **tabuleiro inteiro** antes do corte em casas — no
tabuleiro, e não na casa, porque iluminação e trama são propriedades da página, e estimá-las
sobre 100×100 px de uma casa é estimar sobre ruído.

Ordem das etapas, cada uma com razão:

1. **Correção de rotação residual** pela orientação dominante das linhas da grade
   (`cv2.HoughLines` sobre o gradiente, ou o pico do espectro de Radon). O warp da S-12
   corrige perspectiva, não sobra de 0,5–2°, e é essa sobra que faz a casa da borda pegar
   pedaço da vizinha.
2. **Campo plano (flat-field)**: dividir pela própria imagem com desfoque gaussiano de raio
   ~1/4 do lado da casa. Remove papel amarelado e gradiente de iluminação de scanner sem tocar
   no traço da peça.
3. **Supressão de trama** por abertura morfológica com elemento **direcional** na orientação
   da hachura (estimada por FFT ou pelo mesmo Hough do passo 1). A hachura é um padrão
   periódico e direcional; a peça não é.
4. **CLAHE** com `clipLimit` moderado, sobre o tabuleiro inteiro.

Os quatro passos são desligáveis individualmente, e o padrão precisa ser **medido**, não
suposto: se a normalização piorar os livros que hoje vão bem (Polgar em 1,000, Schiller em
0,927), ela não entra ligada.

**A armadilha que este item precisa evitar.** Normalizar na inferência e não no treino cria
um segundo desencontro de domínio — o inverso do atual. As amostras de `data/samples/` foram
gravadas **cruas**. Duas saídas, e a spec escolhe a segunda:

- normalizar as 3.289 amostras no disco (destrutivo, e perde o original);
- **normalizar na leitura**, em `BoardFenDataset._load_board`, com os mesmos parâmetros da
  inferência. O disco continua com o original, e trocar de normalização é retreinar, não
  re-anotar.

E a consequência que **não pode passar em silêncio**: um checkpoint treinado com normalização
e outro sem são incompatíveis, e `ArchConfig.version` não distingue os dois. Isso reintroduz
exatamente o defeito que a S-27 corrigiu (`load_state_dict(strict=False)` descartando metade
dos pesos). Portanto **`ArchConfig` ganha o identificador da normalização**, e
`arch_version` passa a ser, por exemplo, `cnn-gray-64-linear-norm2`. Um checkpoint antigo, sem
o sufixo, carrega como `norm0` — que é o que ele é.

**Interface proposta.**

```python
# src/chess_diagram_ocr/preprocess.py

@dataclass(frozen=True)
class NormalizerConfig:
    deskew: bool = True
    flat_field: bool = True
    hatch_suppression: bool = True
    clahe: bool = True
    clahe_clip: float = 2.0

    @property
    def version(self) -> str:
        """Entra em `ArchConfig.version`. `norm0` = nenhuma etapa (o de hoje)."""

class BoardNormalizer:
    def __init__(self, config: NormalizerConfig = DEFAULT_NORMALIZER) -> None: ...
    def normalize(self, board_rgb: np.ndarray) -> np.ndarray: ...
    def estimate_skew(self, board_rgb: np.ndarray) -> float:
        """Graus. Exposto separado porque a S-45 usa o mesmo cálculo."""
```

**Critério de aceite.**
- Euwe Band 1-2 p25: `min_confidence` sai de 0,0000 para **≥ 0,50**, com a posição correta.
- Nos livros que já iam bem (Polgar, Schiller, Reinfeld ES), `min_confidence` média **não cai**.
- No conjunto de campo da S-41, a taxa de diagramas acima do gate sobe.
- Um checkpoint `norm0` carregado num pipeline `norm2` **falha alto**, com as duas versões na
  mensagem — igual ao que a S-27 fez para arquitetura.

**Testes.** Tabuleiro sintético com hachura diagonal aplicada: a normalização remove a trama e
preserva as peças (medido por diferença absoluta contra o sintético limpo). Tabuleiro girado
1,5°: `estimate_skew` devolve entre 1,0 e 2,0. Compatibilidade: `ArchConfig.from_version`
aceita nome com e sem sufixo de normalização.

---

## S-40 · Aumento de dados dirigido ao acervo

**Problema.** `training.build_train_transform:101`:

```python
v2.RandomApply([v2.GaussianBlur(kernel_size=3, sigma=(0.1, 1.0))], p=0.3)
v2.ColorJitter(brightness=0.3, contrast=0.3)
v2.RandomAffine(degrees=2, translate=(0.05, 0.05), scale=(0.95, 1.05))
```

É um conjunto genérico e razoável, e não contém **nenhuma** das degradações listadas na S-39.
O modelo é treinado para tolerar desfoque e mudança de brilho — dois problemas que o acervo
quase não tem — e nunca vê hachura, transparência do verso nem inversão.

Falta também `RandomHorizontalFlip`, que neste domínio é **rótulo-preservante por casa**: o
classificador decide `casa → peça`, e um cavalo espelhado continua sendo um cavalo. É a
duplicação de dataset mais barata disponível, e está fora.

**Solução.** Transformações que reproduzem o que os scans têm, cada uma nomeada e desligável,
implementadas como `nn.Module` picláveis (a nota de `_clamp01:90` sobre `spawn` no Windows
vale para todas):

| transformação | parâmetro | reproduz |
|---|---|---|
| `RandomHatch` | ângulo, período, amplitude | casa hachurada do Euwe e do Kemeri |
| `RandomShowThrough` | mistura com um recorte deslocado e invertido | transparência do verso |
| `RandomPaperTint` | ganho por canal + gradiente suave | papel amarelado |
| `RandomSpeckle` | sal-e-pimenta + gaussiano | granulação de scan |
| `RandomJpeg` | qualidade 30–90 | artefato de compressão |
| `RandomInvert` | p baixo | diagramas de contraste invertido |
| `RandomHorizontalFlip` | p = 0,5 | (rótulo-preservante, dobra o dataset) |
| `RandomGridJitter` | ±3 px na casa | desalinhamento residual da grade |

**Medir separado.** A Fase 5 mostrou que aumento e arquitetura enganam quando medidos juntos:
o TTA "melhorou" e custou 6× o tempo por um tabuleiro em 320, e os pesos de classe pioraram
por um motivo que só a decomposição do erro revelou. Aqui vale a mesma disciplina: uma grade
como a da `experiments.py`, uma transformação por vez, comparadas **no conjunto de campo da
S-41** e não só no split de teste — porque é justamente o split de teste que não representa o
problema.

**Interface proposta.**

```python
# src/chess_diagram_ocr/augment.py

@dataclass(frozen=True)
class AugmentConfig:
    hatch: float = 0.25
    show_through: float = 0.15
    paper_tint: float = 0.30
    speckle: float = 0.20
    jpeg: float = 0.20
    invert: float = 0.05
    hflip: float = 0.50
    grid_jitter: float = 0.30
    """Probabilidades. 0,0 desliga. Os defaults são chute e a S-40 os substitui por medição."""

def build_train_transform(config: AugmentConfig = DEFAULT_AUGMENT) -> Callable: ...
```

`AugmentConfig` vai para os metadados do checkpoint, ao lado de `seed` e `split_hash` — pela
mesma razão da S-27: sem isso, "o modelo A é melhor que o B" pode estar comparando dois
regimes de aumento.

**Critério de aceite.** Ganho no conjunto de campo, medido, com o efeito de cada
transformação isolado numa tabela do EXPERIMENTS.md — **incluindo as que não ajudaram**. A
Fase 5 estabeleceu que registrar o que não funcionou é parte da entrega.

**Testes.** Cada transformação é determinística sob semente fixa. Todas são picláveis
(`pickle.dumps` do `Compose` inteiro), porque `num_workers > 0` no Windows depende disso.
`RandomHorizontalFlip` sobre uma casa não muda o rótulo — teste explícito, porque é a única
do conjunto cuja validade depende do domínio.

---

## S-41 · Conjunto de avaliação de campo, e a métrica que falta ✅ implementada (2026-08-09)

> **Entregue.** `src/chess_diagram_ocr/field_eval.py`, `cvoff-field`, e
> `data/field_set.jsonl` com **15 páginas anotadas à mão, 38 diagramas, 3 páginas sem
> diagrama**, em cinco regimes. Linha de base: **taxa de exportação 0,6842 (26/38)**, recall
> 0,9211, precisão 0,9722 — em `docs/metrics/field_20260809.json`.
>
> Dois desvios do que está especificado abaixo, e os dois deliberados:
>
> - **15 páginas, não 60.** As 15 cobrem os cinco regimes e já produzem números por regime
>   que separam (1,000 no Polgar contra 0,429 no scan puro). Estender é rodar
>   `cvoff-field --draft` e conferir; o custo por página caiu do que a spec supunha, porque
>   anotar virou corrigir.
> - **Anotação sem `placement`.** Anotar a caixa é olhar a página; conferir a posição é ler
>   64 casas. A taxa de exportação -- a métrica primária -- não depende da FEN, e
>   `conditional_exact` reporta `—` em vez de fingir um número. `--no-placement` existe para
>   isso.
>
> E o item já se pagou: a primeira medição **corrigiu a hipótese da S-38** (ver acima).

**Problema.** Todas as métricas do projeto medem sobre **o que foi encontrado**:
`evaluation.evaluate_dataset` avalia recortes já rotulados; `batch.BookResult.acceptance_rate`
é sobre o que a varredura produziu; a fila de revisão ordena o que entrou nela.

Nenhuma responde: **dos diagramas que a página tem, quantos saíram?** Sem esse número, um
ajuste que corte 20% dos falsos positivos e 5% dos verdadeiros aparece como melhora em todos
os painéis (confiança média sobe, ilegais caem) e é uma piora no produto.

E o conjunto de teste atual não descreve o campo: 17 de 101 diagramas de página real ficam
abaixo do gate (16,8%), contra 3 de 320 no split de teste (0,94%). Fator de **18×**.

**Solução.** Um conjunto de páginas anotadas à mão, versionado (é texto, cabe no git):

```jsonc
// data/field_set.jsonl — uma linha por página
{"pdf": "1937 Kemeri.pdf", "page": 80, "diagrams": [
   {"bbox": [212, 545, 905, 1240], "fen": "6r1/...", "side": "w", "side_evidence": "nenhuma"}
]}
```

Composição alvo: **60 páginas**, 3 de cada um dos 20 livros distintos, escolhidas para cobrir
os regimes — scan hachurado, scan limpo, vetorial, tabuleiro em fonte, página sem diagrama,
página de soluções, página com fotografia. As páginas **sem** diagrama são obrigatórias: são
elas que medem falso positivo, e nenhuma métrica atual as vê.

Métricas novas, num relatório próprio:

| métrica | definição | por que |
|---|---|---|
| **recall de detecção** | diagramas anotados que foram detectados (IoU > 0,5) | a que falta |
| **precisão de detecção** | detectados que existem | pega o falso positivo da S-38 |
| **taxa de exportação** | diagramas anotados que saem detectados, legais e acima do gate | **a métrica primária do produto** |
| exatidão condicional | FEN exata entre os detectados | comparável com a de hoje |

O número de referência, medido em 2026-08-09 sobre 40 páginas amostradas (não é ainda o
conjunto anotado, mas é o ponto de partida): **84 de 101 diagramas acima do gate — 83,2%**.

**Interface proposta.**

```python
# src/chess_diagram_ocr/field_eval.py
@dataclass(frozen=True)
class FieldPage:
    pdf: Path
    page: int
    diagrams: tuple[AnnotatedDiagram, ...]

@dataclass
class FieldReport:
    detection_recall: float
    detection_precision: float
    export_rate: float
    conditional_exact: float
    per_book: dict[str, "FieldReport"]
    def as_dict(self) -> dict[str, Any]: ...

def evaluate_field(pages: Sequence[FieldPage], *, options: RecognitionOptions) -> FieldReport: ...
```

CLI: `cvoff-field --set data/field_set.jsonl --json docs/metrics/field_<data>.json`.

**Ferramenta de anotação.** Não escrever uma. A aba **Resultado** já abre um diagrama, permite
corrigir por clique e salvar; um botão "anotar para o conjunto de campo" reaproveita tudo, e o
bbox já está em `RecognizedDiagram.quad`. O que falta anotar à mão é o que o detector
**perdeu** — e para isso a seleção de área do `PdfPanel` (S-20) já serve.

**Critério de aceite.** O conjunto existe, é versionado, e `cvoff-field` produz o relatório.
A partir daí, **nenhum item das Fases 7 e 8 fecha sem número neste conjunto** — a mesma regra
que a S-08 estabeleceu para o baseline.

**Testes.** Um conjunto de campo sintético de 3 páginas (imagens geradas, não PDF do acervo)
que exercita recall, precisão e página-sem-diagrama. O conjunto real depende de `PDF/`, que
não é versionado, então o teste **pula** quando a pasta está vazia — o mesmo padrão de
`data/samples/`.

---

# Fase 8 — OCR de verdade

## S-42 · `TextRecognizer` — motor de OCR opcional e plugável

**Problema.** 7 dos 27 livros (2.654 páginas) não têm camada de texto. Para eles
`pdf_text.contexts_for_pdf_page` devolve `DiagramContext()` vazio, sempre: sem lado a jogar,
sem número de exercício, sem jogadores. A informação está impressa na página e o projeto não
tem como lê-la.

Mais 5 livros estão num terceiro regime que a S-16 não distingue: a camada de texto existe e
**falha em parte das páginas** — `Gaprindashvili` e `Vishy Anand` têm texto em 14 de 30
páginas amostradas, `400 Quebra-cabeças` e `Yusupov` em 22, `La Combinación` em 26. São scans
com OCR parcial do distribuidor. Para eles a decisão não pode ser por livro: tem de ser por
página, usando a camada onde ela existe e o OCR onde ela falta.

**Solução.** Uma interface, e provedores atrás dela — o mesmo desenho da S-32 para
`RemoteFenProvider`, e pelo mesmo motivo: o recurso é opcional, o projeto funciona sem ele, e
a escolha de motor não pode vazar para o resto do código.

**A decisão de qual motor é o padrão não é sobre acurácia.** Os critérios que este projeto já
declarou — funciona offline, nada sai da máquina no uso padrão, Windows, CPU, instalação por
`uv sync` — eliminam a maioria antes de comparar qualidade:

| motor | peso | offline na 1ª execução | veredito |
|---|---|---|---|
| **RapidOCR (`rapidocr-onnxruntime`)** | ~15 MB, roda no `onnxruntime` que o extra `onnx` da S-30 já traz | **sim** — modelos vêm no wheel | **padrão** |
| EasyOCR | ~100 MB baixados no primeiro uso | **não** | suportado, opt-in explícito |
| PaddleOCR | PaddlePaddle, ~500 MB, instalação frágil no Windows | com cache prévio | não |
| Tesseract (`pytesseract`) | binário externo | sim | suportado se já instalado |

RapidOCR é o padrão porque é o único que **não muda a natureza do projeto**: nenhum download
na primeira execução, nenhuma runtime nova, e o extra fica em
`[project.optional-dependencies] ocr` do mesmo jeito que `onnx`.

EasyOCR fica disponível trocando uma linha de `settings.json`. Mas não pode ser o padrão
enquanto o README prometer que nada sai da máquina no uso padrão — baixar 100 MB de modelo na
primeira execução é tráfego que o usuário não pediu, e a promessa da S-32 vale para a rede
inteira, não só para a correção remota.

**Interface proposta.**

```python
# src/chess_diagram_ocr/ocr.py

@dataclass(frozen=True)
class TextBox:
    text: str
    bbox: tuple[float, float, float, float]   # em pixels da imagem passada
    confidence: float

class TextRecognizer(Protocol):
    def read(self, image_rgb: np.ndarray, *, allowlist: str = "") -> list[TextBox]: ...
    @property
    def name(self) -> str: ...

def build_recognizer(settings: OcrSettings) -> TextRecognizer | None:
    """`None` quando desabilitado ou quando o extra não está instalado.

    Não achar o motor é caminho normal, não erro -- igual ao `find_engine` da S-33.
    """
```

`allowlist` não é detalhe: restringir o vocabulário a `"WB"` ou a `"12345678"` melhora
muito a leitura de glifo único, e os três motores suportam isso de formas diferentes. A
interface esconde a diferença.

Configuração, no mesmo `data/settings.json` da S-32:

```jsonc
{ "ocr": { "enabled": false, "engine": "rapidocr", "languages": ["pt", "en", "es", "de"] } }
```

**Critério de aceite.** Sem o extra instalado, o projeto funciona exatamente como hoje e os
testes de OCR pulam. Com o extra, nenhuma requisição de rede parte na primeira execução —
verificável por teste, do mesmo jeito que a S-32 verifica para a correção remota.

**Testes.** Um `FakeRecognizer` que devolve `TextBox` fixos, usado por toda a S-43 e a S-44.
Um teste que garante que `build_recognizer` devolve `None` — e não levanta — quando o extra
falta. Um teste de contrato por motor instalado, pulado quando ausente.

---

## S-43 · `CaptionReader` — OCR da faixa de legenda, não da página

**Problema.** Mesmo com um motor de OCR disponível, rodá-lo na página inteira é errado por
três razões, e as três já estão documentadas na S-16:

1. **Custo.** Uma página a 220 DPI é ~1.100×1.700; o detector de texto é a parte cara.
2. **Falso positivo.** A armadilha nº 3 da S-16 — *"prosa não é legenda"* — piora com OCR,
   porque o reconhecimento erra e um erro vira padrão que casa: `"Weiß"` lido como `"Weiss"`
   passa, mas `"...spielt Weiß"` no meio de um parágrafo também.
3. **O tabuleiro vira texto.** O OCR lê as peças como caracteres, e o filtro
   `_is_diagram_font_row` — feito para o Polgar, cujo tabuleiro **é** texto — não foi
   desenhado para isso.

**Solução.** Ler **só a vizinhança do `bbox_pdf`** que a S-12 já carrega em cada
`DiagramCandidate`, e devolver `TextLine` — a mesma estrutura que `page_text_lines` devolve.
Assim **todo o aparato da S-16 continua valendo sem uma linha de mudança**: agrupamento por
coluna, `dominant_placement`, `assign_lines_to_diagrams`, os tiers de legenda e vizinhança, o
filtro de prosa.

Isso é a decisão de projeto do item: o OCR não é uma via alternativa, é **uma segunda fonte de
`TextLine`**.

```
     ┌──────────── faixa superior (radius_pt acima do bbox)
     │  ┌────────┐
faixa│  │diagrama│  faixa lateral (para o marcador W/B da S-44)
     │  └────────┘
     └──────────── faixa inferior
```

Duas correções que a S-43 traz junto, e que valem **também** para os livros com camada de
texto:

- **`MARGIN_BAND` descarta declaração de escopo de página.** `pdf_text:85` joga fora 7% do
  topo e do rodapé, como cabeçalho corrente. Medido: a página 40 do
  `Reinfeld_1001_Sacrificios_y_Combinaciones_Brillantes_1977.pdf` tem
  **`LAS BLANCAS JUEGAN PRIMERO`** exatamente nessa faixa, e é uma declaração que vale para os
  seis diagramas da página. A faixa de margem passa a ser **testada contra os padrões de lado
  a jogar antes de ser descartada**; casando, vira uma declaração de escopo de página, com
  precedência menor que a legenda do diagrama e maior que o padrão "brancas".
- **`DiagramContext` ganha procedência.** `side_to_move_evidence` existe; falta dizer se o
  trecho veio da camada de texto ou do OCR, e com que confiança. Um lado a jogar decidido por
  OCR com 0,62 de confiança não é o mesmo dado que um lido da camada de texto — e o
  `[SideToMoveSource]` do PGN, que a Fase 3 criou justamente para que um palpite pareça um
  palpite, precisa distinguir `"text"` de `"ocr"`.

**Interface proposta.**

```python
# src/chess_diagram_ocr/ocr_caption.py

class CaptionReader:
    def __init__(self, recognizer: TextRecognizer, *, radius_pt: float = DEFAULT_RADIUS_PT) -> None: ...

    def lines_around(self, page: fitz.Page, bbox_pdf: tuple[float, ...]) -> list[TextLine]:
        """`TextLine` no mesmo formato de `pdf_text.page_text_lines`, em coordenadas do PDF."""

    def page_scope_declaration(self, page: fitz.Page) -> tuple[chess.Color, str] | None:
        """Declaração na faixa de margem que vale para a página inteira."""
```

E em `pdf_text`, um parâmetro novo em vez de um caminho novo:

```python
def contexts_for_page(page, bboxes, *, radius_pt=..., page_number=None,
                      caption_reader: CaptionReader | None = None) -> list[DiagramContext]:
    """Com `caption_reader`, as linhas do OCR entram **junto** com as da camada de texto.
    Página que tem as duas usa as duas: a camada de texto é mais confiável e vence no empate.
    """
```

A decisão é **por página, não por livro** — é o que os 5 livros de OCR parcial exigem. O
critério: se `page_text_lines` devolve linhas na vizinhança do diagrama, a camada respondeu e
o OCR não roda (economia real, dado o custo medido na S-61); se não devolve nada, o OCR entra.
Decidir por livro deixaria metade das páginas do `Gaprindashvili` sem legenda.

**Critério de aceite.**
- Reinfeld ES p40: os 6 diagramas saem com `side_to_move = WHITE`, procedência
  `"ocr-page-scope"`, e `exercise_number` 193 a 198.
- Nos 17 livros que **têm** camada de texto, ligar o OCR **não muda nenhum resultado** — a
  camada de texto vence. Verificável rodando o conjunto de campo com e sem.
- O custo por página com OCR ligado é reportado no log; se passar de ~2× o custo do
  reconhecimento, o item precisa de recorte mais apertado antes de fechar.

**Testes.** Com `FakeRecognizer`, uma página sintética com legenda acima e outra com legenda
abaixo produzem o mesmo `DiagramContext` que a camada de texto produziria — é este o teste que
prova que o OCR entra pela porta da S-16 e não por uma paralela. Faixa de margem com
`"LAS BLANCAS JUEGAN PRIMERO"` produz declaração de escopo; com `"142"`, não.

---

## S-44 · O marcador `W`/`B` e o número do diagrama, sem depender de OCR

**Problema.** `pdf_text._match_side_symbol:268` conhece `◻□▫⬜◽⚪` e `◼■▪⬛◾⚫`. Não conhece
`W` e `B` — a convenção tipográfica mais comum da literatura inglesa de xadrez (Batsford,
Cadogan, Everyman): uma letra isolada colada à borda do diagrama.

Medido: `GALLAGHER - Winning With the King's Gambit.pdf`, página 80. À esquerda do diagrama,
dois glifos empilhados: **`76`** (número do diagrama) e **`B`** (pretas jogam). O livro não
tem camada de texto, e a página tem a informação impressa com clareza.

A lacuna é dupla, e a segunda metade é a que surpreende: **o `W`/`B` também não é lido nos
livros que têm camada de texto**, porque nenhum padrão de `_WHITE_PATTERNS` casa com uma letra
isolada, e casar `\bW\b` na página inteira produziria falso positivo em toda notação.

**Solução.** Duas partes, deliberadamente separadas porque têm dependências diferentes:

**(a) Sem OCR — na camada de texto.** Um padrão para letra isolada, válido **só** quando a
linha tem 1 ou 2 caracteres **e** está lateralmente adjacente ao diagrama (`placement` em
`"left"` ou `"right"`, distância < 20 pt). O contexto geométrico é o que torna o padrão
seguro: um `B` solto no meio de um parágrafo não está a 8 pt da borda esquerda de um
diagrama. Isso já funciona hoje para qualquer livro com camada de texto, e não precisa da
S-42.

**(b) Sem OCR — nas páginas de scan.** Aqui está a decisão de projeto que evita uma
dependência: para um vocabulário de **duas classes** (`W`, `B`) numa região que o `bbox_pdf`
localiza, um classificador de recorte é mais preciso, mais rápido e mais barato que qualquer
OCR de propósito geral — e **o projeto já tem toda a maquinaria**: o laço de treino da S-27,
o split estável da S-07, a calibração da S-28, a fila de revisão da S-22 e um editor para
corrigir rótulo.

O mesmo vale para o número do diagrama, com vocabulário de 10 classes e segmentação por
componentes conexos.

Isso importa por uma razão de arquitetura, não de desempenho: **o caminho crítico — lado a
jogar — deixa de depender de um extra opcional.** O OCR da S-42/S-43 fica para texto livre
(jogadores, evento, ano), onde não há alternativa.

**Interface proposta.**

```python
# src/chess_diagram_ocr/glyph.py

Vocabulary = Literal["side", "digit"]

@dataclass(frozen=True)
class GlyphReading:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]

class GlyphClassifier:
    """Classificador de glifo em vocabulário fechado, na vizinhança do diagrama.

    Mesma forma do `PieceClassifier`: recorte pequeno, entrada em tons de cinza, cabeça
    linear, temperatura no checkpoint. A `ArchConfig` é reaproveitada com outro
    `num_classes` -- e é por isso que ela já é parametrizável.
    """
    def __init__(self, model_path: Path, vocabulary: Vocabulary) -> None: ...
    def read_side_marker(self, page_rgb, bbox_px) -> GlyphReading | None: ...
    def read_number(self, page_rgb, bbox_px) -> GlyphReading | None: ...
```

**A ordem de trabalho que este item impõe.** Não há dataset de glifo hoje. O caminho é o mesmo
que o projeto já percorreu para as peças, e é ele que torna o item viável em dias e não em
semanas: rodar o recorte da faixa lateral em N páginas, mandar para a **fila de revisão**
(S-22) ordenada por incerteza, rotular no editor, treinar. Uma pessoa rotula ~200 glifos em
meia hora, e 200 exemplos de 2 classes bastam com folga.

**Critério de aceite.**
- Gallagher p80: `side_to_move = BLACK`, procedência `"glyph"`, evidência `"B"`.
- Nos livros com camada de texto, a parte (a) não produz **nenhum** falso positivo no conjunto
  de campo — é a métrica que decide o item, porque um `W` errado inverte a posição.
- O classificador reporta confiança calibrada, e abaixo do limiar devolve `None`. Não
  responder é resposta válida; inventar não é. É a mesma regra da S-16.

**Testes.** Página sintética com `W` a 8 pt à esquerda do diagrama → brancas; o mesmo `W` a
300 pt → `None`. Um `B` dentro de um parágrafo → `None`. Recorte de dígito sintético em três
fontes → o número certo.

---

## S-45 · Coordenadas do tabuleiro: orientação, ponto de vista das pretas e registro da grade

**Problema.** A S-13 deixou uma pendência nomeada no ROADMAP: **diagrama impresso do ponto de
vista das pretas**. Ali as peças estão desenhadas para cima e o que muda é o mapeamento
casa→índice, não os pixels. Girar a imagem estraga a leitura, e nenhum sinal de imagem
resolve — porque a imagem é legítima nas duas interpretações. A cascata de quatro regras de
`predict_with_orientation` decide entre 0° e 180°, e essa é uma pergunta diferente.

**Solução.** Ler as coordenadas impressas na borda. Se a coluna à esquerda lê `8 7 6 5 4 3 2 1`
de cima para baixo, é ponto de vista das brancas; se lê `1 2 3 4 5 6 7 8`, das pretas. Oito
classificações de dígito com vocabulário de 8 classes — o mesmo `GlyphClassifier` da S-44.

**Ganho secundário, e talvez maior que o primário.** As posições dos oito rótulos dão o
**registro exato da grade**. Se o detector achou os cantos com 3 px de erro, os centros dos
rótulos dizem onde as linhas realmente estão, e o warp pode ser corrigido antes de cortar as
casas — que é o mesmo problema que a S-12 atacou pelo lado do contorno e que a medição do
`hybrid.py` mostrou ser o que mais derruba a confiança (Schiller: 0,137 cru contra 0,360 com
warp).

**A ressalva, e ela precisa estar no item.** Nem todo livro imprime coordenadas. Nas páginas
inspecionadas: Aagaard e Karpov têm; Reinfeld, Gallagher e Euwe não têm. **Este item começa
por medir a cobertura no conjunto de campo**, e só continua se ela justificar. Um item que
alcança 3 livros não vale o mesmo que um que alcança 15, e a S-16 já ensinou essa lição — ela
supôs legenda abaixo do diagrama e a medição achou acima em 3 de 4 livros.

**Interface proposta.**

```python
# src/chess_diagram_ocr/coordinates.py

@dataclass(frozen=True)
class BoardCoordinates:
    files: tuple[str, ...]      # ('a'..'h') na ordem lida da esquerda para a direita
    ranks: tuple[str, ...]      # ('8'..'1') de cima para baixo
    confidence: float
    grid_lines_px: tuple[tuple[float, ...], tuple[float, ...]] | None
    """As 9 linhas verticais e as 9 horizontais, em pixels, quando os rótulos as determinam."""

    @property
    def point_of_view(self) -> chess.Color | None:
        """BLACK quando as filas sobem de cima para baixo. `None` se não deu para ler."""

class CoordinateReader:
    def __init__(self, glyphs: GlyphClassifier) -> None: ...
    def read(self, page_rgb: np.ndarray, quad: np.ndarray) -> BoardCoordinates | None: ...
```

Consumidores:
- `OrientationPolicy` (S-47) ganha uma regra nova, **acima** da legalidade, porque quando as
  coordenadas respondem elas não são um prior — são a resposta;
- `RecognizedDiagram` ganha `point_of_view`, e a FEN é transposta quando ele é `BLACK`;
- `BoardNormalizer` (S-39) usa `grid_lines_px` para refinar o warp quando disponível.

**Critério de aceite.** Um relatório de cobertura no conjunto de campo (quantos diagramas têm
coordenadas legíveis, por livro) **antes** de qualquer mudança de comportamento. Nos que têm,
o ponto de vista é lido corretamente em ≥ 95% — e, quando lido, nenhum diagrama de ponto de
vista das brancas é marcado como das pretas. O erro nesta direção inverte a posição inteira e
é pior que não responder.

**Testes.** Tabuleiro sintético com coordenadas nas quatro bordas, nas duas orientações.
Tabuleiro sem coordenadas → `None`. Tabuleiro com coordenadas parcialmente cortadas pelo
recorte → confiança baixa, não palpite.

---

## S-46 · A solução em notação algébrica como validador cruzado *(opcional)*

**Problema.** Nos livros de exercícios, a solução está impressa — no rodapé, na página
seguinte ou no fim do livro: `31.♖:c5! ♛e4 32.♖c1 1:0`. É informação sobre a posição que o
projeto ignora inteiramente.

**Solução.** Quando a solução do exercício *n* é localizável e o diagrama *n* foi reconhecido,
tentar aplicar o primeiro lance à posição lida. Um lance que é legal na posição reconhecida é
evidência forte de que a leitura está certa; um que é ilegal aponta a casa envolvida — e é
exatamente o tipo de sinal que a fila de revisão da S-22 ordena.

Vale também para o lado a jogar: se `31.♖:c5` é lance das brancas e a posição lida só o admite
com as pretas na vez, o lado está invertido.

**Por que é opcional.** Depende de localizar a solução, que é um problema de estrutura de
livro — varia por editora, e a S-16 já mostrou quanto trabalho isso dá. O ganho é real mas o
alcance é incerto, e ele não deve bloquear nada da Fase 8.

**Critério de aceite.** Nos livros em que a associação exercício↔solução funcionar, a
concordância entra como sinal na prioridade da S-22 e como header `[SolutionCheck]` no PGN.
Discordância **nunca** reescreve a posição automaticamente — vira item de revisão.

---

# Fase 9 — Classes especializadas

Os cinco itens abaixo não mudam comportamento. Cada um tem uma consequência concreta
declarada; extração sem consequência não entra nesta spec.

## S-47 · `Trainer` — quebrar `train_model`

**Problema.** `training.train_model:358` tem **259 linhas e 18 parâmetros**, e faz sete coisas:
montar dataset e loaders, resolver split, retomar checkpoint, rodar o laço de época, decidir
a melhor época, parar antecipadamente, calibrar e gravar.

A parte que mais custa não é o tamanho — é que **a política de "melhor época" é intestável
sem treinar**. Ela já teve um defeito real e caro: retomar zerava o controle de melhor época
e a primeira época da retomada sobrescrevia o checkpoint mesmo se fosse pior. O ROADMAP
registra que "a primeira versão da 5.3 estava errada, e foi o uso que mostrou" — porque não
havia como perguntar à política sem rodar um treino.

**Solução.**

```python
# src/chess_diagram_ocr/training.py

@dataclass(frozen=True)
class TrainingPlan:
    """Os 18 parâmetros, agrupados por assunto e validados uma vez."""
    data: DataPlan          # csv, samples, splits, cache, workers
    model: ArchConfig
    optim: OptimPlan        # epochs, batch, lr, patience, class_weights, seed
    output: OutputPlan      # model_path, calibrate, fresh

class BestEpochPolicy:
    """Quando gravar por cima. Testável sem treinar -- era a S-27 que não podia."""
    def __init__(self, metric_name: str, incumbent: float) -> None: ...
    def accepts(self, metric: float) -> bool: ...
    def should_stop(self, epochs_without_improvement: int) -> bool: ...

class Trainer:
    def __init__(self, plan: TrainingPlan, *, progress: Callable[[dict], None] | None = None) -> None: ...
    def prepare(self) -> None:      """datasets, loaders, amostrador, pesos, otimizador"""
    def resume(self) -> Checkpoint | None: ...
    def run_epoch(self, epoch: int) -> dict[str, Any]: ...
    def validate(self) -> ValidationMetrics: ...
    def finish(self) -> TrainingRun:  """calibração + metadados"""
    def fit(self) -> TrainingRun:     """prepare → resume → laço → finish"""
```

`train_model(...)` permanece como função fina sobre `Trainer.fit()`. São 30 chamadores entre
CLI, `ui/training_dialog.py`, `experiments.py` e testes; quebrá-los não é parte deste item.

**Consequência concreta.** `BestEpochPolicy` testável isolada; `run_epoch` chamável em teste
com 2 lotes sintéticos; e a porta por onde validação a cada N passos entra sem tocar no resto.

**Critério de aceite.** `train_model` abaixo de 40 linhas. Métricas idênticas às de hoje sob a
mesma semente — comparação bit a bit do histórico, porque este item **não pode** mudar
resultado.

---

## S-48 · `OrientationPolicy` — a cascata de quatro regras vira estratégia

**Problema.** `inference.predict_with_orientation:335` tem 112 linhas com a cascata de
decisão, os dois limiares, a explicação em pt-BR e a tabela de medição no docstring. A cascata
**já mudou uma vez** — a S-13 supunha que a legalidade decidiria e a medição mostrou que ela
só decide em 16% dos casos, e que a confiança vira ruído quando a leitura é ruim. Vai mudar
de novo: a S-45 acrescenta as coordenadas, que quando respondem respondem melhor que todas.

Cada mudança hoje exige editar uma função de 112 linhas que também faz a inferência.

**Solução.** Separar a **decisão** da **inferência**:

```python
# src/chess_diagram_ocr/orientation.py

@dataclass(frozen=True)
class OrientationEvidence:
    upright: BoardPrediction
    flipped: BoardPrediction
    coordinates: BoardCoordinates | None = None   # S-45

class OrientationRule(Protocol):
    name: str
    def decide(self, ev: OrientationEvidence) -> tuple[bool, str] | None:
        """(escolheu_de_pe, motivo em pt-BR) ou None quando a regra cala."""

class OrientationPolicy:
    """Cascata ordenada. A ordem é a decisão, e ela é medível regra a regra."""
    DEFAULT: tuple[OrientationRule, ...] = (
        CoordinateRule(),          # S-45: quando responde, é resposta e não prior
        SingleLegalRule(),         # decide em 16%, nunca errou
        ConfidenceMarginRule(),    # 100% de acerto acima de 0,20 de margem
        PawnPriorRule(),           # o regime de leitura ruim
    )
    def resolve(self, ev: OrientationEvidence) -> OrientedPrediction: ...
    def explain(self, ev: OrientationEvidence) -> list[tuple[str, str | None]]:
        """O que cada regra disse. Para o painel de diagnóstico e para a S-41."""
```

**Consequência concreta.** A tabela de medição do docstring vira um teste que roda: cada regra
avaliada isolada contra o conjunto de campo, com acerta/erra/empata. Acrescentar a regra das
coordenadas passa a ser uma linha na tupla.

**Critério de aceite.** Resultado idêntico ao de hoje no split de teste e no conjunto de
campo, com `CoordinateRule` desligada. `explain()` reproduz a tabela do docstring atual.

---

## S-49 · `DiagramEditorModel` — o estado do editor fora do widget

**Problema.** `ui/result_panel.ResultPanel` tem **672 linhas e 41 métodos**, e o docstring
descreve com precisão o que ele guarda: três listas paralelas (`items`, `fen_edits`,
`side_edits`), o índice selecionado, e **três vínculos mutuamente exclusivos** —
`page_key`, `review_position`, `editing_sample`. Distingui-los é o que faz `Ctrl+S` gravar
amostra nova num caso e regravar a linha existente no outro.

É a regra de negócio mais delicada da interface, e ela mora dentro de um `ttk.Frame`. Só é
testável dirigindo a janela — que é o que o roteiro headless faz, e foi ele que pegou o
defeito de navegação que 509 testes verdes não pegaram. Um teste que precisa de janela é um
teste que quase não se escreve.

**Solução.**

```python
# src/chess_diagram_ocr/ui/editor_model.py   (sem import de tkinter)

class EditorBinding(str, Enum):
    NONE = "none"
    PAGE = "page"
    REVIEW = "review"
    SAMPLE = "sample"

@dataclass
class DiagramEditorModel:
    items: list[RecognizedDiagram] = field(default_factory=list)
    fen_edits: list[str] = field(default_factory=list)
    side_edits: list[str] = field(default_factory=list)
    selected: int = 0

    binding: EditorBinding = EditorBinding.NONE
    page_key: tuple[str, int] | None = None
    review_position: int | None = None
    editing_sample: str | None = None

    def load(self, items, *, binding: EditorBinding, **anchor) -> None:
        """Ponto único de troca de vínculo. Hoje há quatro caminhos que fazem isso."""
    def select(self, index: int) -> None: ...
    def apply_placement(self, placement: str) -> None: ...
    def set_side(self, side: str, *, source: str = "manual") -> None: ...
    def save_target(self) -> SaveTarget:
        """Amostra nova, regravar linha do dataset, ou fechar item da fila. A regra que hoje
        está espalhada por `_save_one`, `_rewrite_dataset_row` e `_settle`."""
    @property
    def has_hand_edits(self) -> bool: ...
```

`ResultPanel` passa a observar o modelo e desenhar. Deve cair para ~350 linhas.

**Consequência concreta.** `save_target()` testável sem Tk: abrir item da fila → corrigir →
salvar não pode criar amostra nova; abrir linha do dataset → salvar tem de regravar a mesma
linha. São duas asserções de três linhas cada, hoje impossíveis sem janela.

**Critério de aceite.** `ResultPanel` abaixo de 400 linhas; `DiagramEditorModel` sem nenhum
import de `tkinter`; as quatro origens (OCR, imagem local, fila, dataset) cobertas por teste
sem janela.

---

## S-50 · `BoardModel` + `BoardRenderer` — quebrar `InteractiveBoard`

**Problema.** `ui/board_widget.InteractiveBoard`: **606 linhas, 43 métodos**, e três
responsabilidades num objeto só — estado (posição, seleção, pincel, arrasto), sinais de
diagnóstico (heatmap, casas mudadas, casas problemáticas, tooltip de 3 classes) e desenho
(`redraw()` com 79 linhas de canvas).

Consequência prática: as funções puras de edição já foram extraídas para `ui/board_edit.py`
(bom), mas o **estado** que as usa não, então nada acima delas é testável sem janela. E
`redraw()` reconstrói o canvas inteiro a cada mudança, o que é o custo que aparece ao arrastar
uma peça num tabuleiro grande.

**Solução.**

```python
# src/chess_diagram_ocr/ui/board_model.py    (sem tkinter)
@dataclass
class BoardModel:
    placement: str
    side_to_move: chess.Color = chess.WHITE
    selected: int | None = None
    brush: str | None = None
    flipped: bool = False
    confidences: tuple[float, ...] = ()
    probs: np.ndarray | None = None
    changed: frozenset[int] = frozenset()
    problems: frozenset[int] = frozenset()

    def press(self, index: int) -> BoardChange: ...
    def drop(self, index: int) -> BoardChange: ...
    def erase(self, index: int) -> BoardChange: ...
    def top_classes(self, index: int, count: int = 3) -> list[tuple[str, float]]: ...

# src/chess_diagram_ocr/ui/board_render.py   (só desenho)
class BoardRenderer:
    def draw(self, canvas: tk.Canvas, model: BoardModel, geometry: BoardGeometry) -> None: ...
    def draw_dirty(self, canvas, model, geometry, squares: Iterable[int]) -> None:
        """Redesenha só as casas afetadas. `BoardChange` diz quais são."""
```

**Consequência concreta.** Duas. `draw_dirty` elimina o redesenho total — arrastar uma peça
toca 2 casas, não 64. E `BoardRenderer` vira o **único** arquivo a reescrever numa eventual
troca de framework (S-53): o modelo serve a Tk, a Qt e ao Streamlit igualmente.

**Critério de aceite.** `BoardModel` sem import de `tkinter`; a interação
clique→arrasta→solta testada sem janela; nenhuma mudança visual.

---

## S-51 · `LabelStore` — uma porta para o `labels.csv`

**Problema.** O `labels.csv` é lido e escrito com pandas em **cinco módulos**: `dataset.py`
(`_load_entries`, `append_training_sample`, `_write_labels`, `migrate_labels_csv`),
`audit.py` (`_read_rows`, e as três funções de correção), `dataset_browser.py` (`load_rows`,
`update_row`, `delete_rows`, `quarantine_rows`), `splits.py` (indiretamente, pela lista de
nomes) e `cli/migrate_labels.py`.

Cada um conhece o esquema da S-19 por conta própria. `LABEL_COLUMNS` mora em `dataset.py` e
`_write_labels` é privado dele — então `dataset_browser.update_row` reimplementa a gravação, e
as duas precisam concordar sobre ordem de coluna, `fillna("")` e `lineterminator=os.linesep`
sem que nada garanta que concordem.

São 3.241 rótulos de trabalho humano acumulado atrás de cinco portas.

**Solução.**

```python
# src/chess_diagram_ocr/labels.py

class LabelStore:
    """A única porta para o labels.csv. Escrita sempre atômica (S-25)."""
    def __init__(self, csv_path: Path) -> None: ...

    def read(self) -> list[DatasetEntry]: ...
    def append(self, entry: DatasetEntry) -> None: ...
    def update(self, filename: str, **fields: Any) -> None: ...
    def remove(self, filenames: Collection[str]) -> int: ...
    def rewrite(self, entries: Sequence[DatasetEntry]) -> None: ...

    @contextmanager
    def transaction(self) -> Iterator["LabelStore"]:
        """Uma única gravação no fim. Hoje a aba Dataset regrava o arquivo inteiro a cada
        correção -- 3.241 linhas por clique."""

    def backup(self) -> Path: ...
    @property
    def schema_version(self) -> int: ...
```

**Consequência concreta.** Três. A `transaction` acaba com a regravação por clique. O esquema
passa a ter um dono, e o próximo campo (a S-52 quer um) entra em um lugar. E o dia em que
3.241 virar 30.000, trocar CSV por SQLite é reescrever uma classe — hoje seria reescrever
cinco módulos.

**Critério de aceite.** Nenhum `pd.read_csv` ou `to_csv` sobre `labels.csv` fora de
`labels.py` — verificável por teste que varre a árvore. Comportamento idêntico: o CSV gravado
por `LabelStore` é byte a byte igual ao de hoje para a mesma entrada.

---

## S-52 · Recuperar a procedência dos 3.195 rótulos órfãos

**Problema.** Medido no `data/labels.csv` de 3.241 linhas:

| coluna | preenchida | vazia |
|---|---|---|
| `source_pdf` / `source_page` | 46 (1,4%) | **3.195 (98,6%)** |
| `detection_source` | 40 (1,2%) | 3.201 |
| `side_to_move` | 189 (5,8%) | **3.052 (94,2%)** |
| `corrected_by` | **0 (0%)** | 3.241 |

A S-19 criou as colunas e a S-31 as preenche, mas só para amostras salvas **depois** dela. As
3.195 anteriores foram gravadas quando a origem não era registrada.

Três consequências:

1. **A S-07 não pode agrupar o split por livro.** Hoje o split é por hash do nome do arquivo,
   agrupado por diagrama duplicado. Agrupar por livro — o que impede o teste de medir "quão
   bem o modelo lê *este* livro" em vez de generalização — precisa de `source_pdf`.
2. **A auditoria por fonte de detecção não tem dados** (40 linhas em 3.241).
3. **`corrected_by` é coluna morta.** Está no esquema, no `LABEL_COLUMNS`, no CSV e na
   assinatura de `append_training_sample`. Nenhum chamador jamais passa um valor.

**Solução.** A procedência é recuperável, e por um caminho que o projeto já tem: casar cada
PNG de `data/samples/` contra os diagramas detectados nos 27 PDFs por **hash perceptual**.
`audit.dhash` e `audit.hamming_distance` existem e já são usados para achar duplicatas.

```python
# src/chess_diagram_ocr/provenance.py

@dataclass(frozen=True)
class ProvenanceMatch:
    filename: str
    source_pdf: str
    source_page: int
    source_diagram: int
    distance: int
    """Hamming do dHash. 0 é idêntico; acima de ~8 não é a mesma imagem."""

def build_index(pdf_dir: Path, *, dpi: int = 220, progress=None) -> dict[int, list[ProvenanceMatch]]:
    """Varre os PDFs uma vez e indexa o dHash de cada diagrama detectado.
    Caro (~27 livros × N páginas), e por isso o índice é gravado em disco."""

def match_samples(samples_dir, index, *, max_distance: int = 6) -> list[ProvenanceMatch]: ...
```

**O item precisa reportar a taxa, não prometer 100%.** Amostras vindas de imagem local, de PDF
que saiu do acervo, ou recortadas à mão com enquadramento diferente não casam. Recuperação
parcial já destrava o split por livro para a parte casada, e o relatório diz quanto sobrou.

E `corrected_by`: ou passa a ser preenchida, ou sai do esquema. O valor útil **não é o nome do
usuário** — é como a amostra chegou ao rótulo: `ocr-aceito`, `ocr-corrigido`, `fila-revisao`,
`dataset-recorrigido`, `net-remoto`. Isso responde a uma pergunta que hoje ninguém pode fazer:
*as amostras que vieram corrigidas à mão treinam melhor que as aceitas direto do OCR?* Uma
coluna que ninguém escreve é pior que nenhuma, porque parece um dado.

**Critério de aceite.** Relatório com a taxa de casamento por livro. O split por livro passa a
ser possível para a parte casada, e a S-07 ganha o modo `group_by="book"`. `corrected_by`
preenchida em toda amostra nova, ou removida do esquema por migração.

**Testes.** Índice sintético: um PNG recortado de uma página conhecida casa com distância 0;
o mesmo PNG com ruído casa abaixo do limiar; um PNG não relacionado não casa. Teste da
migração que preserva as 46 procedências já corretas.

---

# Fase 10 — Interface e entrega

## S-53 · A decisão de framework, por gatilho e não por gosto

**Problema.** A UI é Tkinter + `ttk`, ~2.500 linhas em 14 módulos, com roteiro headless. Depois
da Fase 6 não tem lógica de negócio dentro. Funciona, e reescrever por estética seria errado.

Mas há três lugares onde a escolha já cobra, e os três são mensuráveis:

- **`DatasetPanel` pagina** porque, nas palavras do próprio código, *"3.195 linhas de uma vez
  travam o Treeview do Tk"*. A paginação custa o que mitiga: filtro e ordenação valem por
  página, não pelo conjunto.
- **`InteractiveBoard.redraw()`** tem 79 linhas de desenho manual e refaz o canvas inteiro a
  cada mudança (a S-50 alivia, não elimina).
- **As sobreposições que a Fase 8 vai querer** — bbox de texto reconhecido sobre a página, com
  confiança em cor e edição no lugar — são o caso de uso natural de uma cena gráfica, e
  trabalho manual de coordenadas no canvas do Tk.

**Solução.** Duas decisões separadas:

**(a) Fazer agora: `ttkbootstrap`.** Tema moderno, **mesma API de widget**, `ttk.Treeview`
intacto. Custo ~1 dia, risco quase nulo, e não fecha nenhuma porta. `CustomTkinter` fica de
fora por um motivo objetivo: não tem equivalente decente de `Treeview`, então a aba Dataset
continuaria em `ttk` e o resultado seria uma tela com dois visuais.

**(b) Decidir por gatilho: PySide6/Qt.** A Fase 6 tornou o porte afordável pela primeira vez —
com o pipeline em `service.py`, portar UI é portar UI. O que Qt daria, concretamente:
`QTableView` com modelo virtual (3.241 linhas sem paginar, e 30.000 também), `QGraphicsScene`
para tabuleiro e sobreposições, `QThread` + sinais no lugar de `root.after`, `QPdfView`
nativo, DPI correto por monitor, `QAction` para atalhos.

Custo real: ~3–4 semanas, mais licença LGPL. **A recomendação é não fazer agora**, e amarrar a
decisão a um de dois eventos observáveis:

| gatilho | por que este |
|---|---|
| a Fase 8 exigir sobreposição **editável** sobre a página renderizada | é onde o canvas do Tk deixa de ser desconforto e vira trabalho desproporcional |
| o `labels.csv` passar de **10 mil linhas** | a paginação da S-23 deixa de ser mitigação e vira obstáculo ao fluxo |

Enquanto nenhum disparar, Tk é a escolha certa e a migração é otimização prematura.

Este item entrega **a decisão escrita e o gatilho**, não o porte. A S-50 já reduz o custo de
um porte futuro ao isolar `BoardRenderer`.

**Critério de aceite.** `ttkbootstrap` aplicado, sem regressão no roteiro headless. Os
gatilhos registrados no ARCHITECTURE.md, onde a próxima pessoa os encontre.

---

## S-54 · O Streamlit precisa de uma decisão

**Problema.** O fechamento da Fase 6 registra com honestidade o que a paridade não entregou: o
Streamlit tem o mesmo *pipeline* e não tem o editor por clique (S-20), o painel de legalidade
(S-21), a fila de revisão (S-22) nem a aba de dataset (S-23).

São **588 linhas** mantidas, testadas junto e citadas no README, que servem para **ver** o
resultado e não para **trabalhar** nele. O fluxo de valor do produto é corrigir → salvar →
treinar, e ele não existe ali.

Há também um detalhe técnico que a documentação já nomeia e que o custo de manutenção
carrega: `resolve_num_workers:146` explica que o `app_streamlit.py` não pode ter guarda
`if __name__ == "__main__"`, então `num_workers > 0` reexecutaria a página inteira dentro de
cada processo — e é por isso que o padrão da biblioteca é 0.

**Solução.** Escolher. A pior saída é continuar sem escolher.

- **Aposentar** — mover para `examples/streamlit_demo.py`, dizer no README que é demonstração
  do `OcrService`, e parar de chamá-la de "interface web alternativa". Custo: 1 h. Ganho:
  588 linhas saem do caminho e o README para de prometer paridade que não existe.
- **Assumir** — editor de posição no navegador (`streamlit-drawable-canvas` ou componente
  próprio), painel de legalidade e fila de revisão. Custo: ~1 semana. Faz sentido se houver
  uso remoto real.

**Critério de aceite.** A escolha registrada no ROADMAP, e o README dizendo o que a tela é.

---

## S-55 · Empacotamento para Windows *(S-36 reaberta)*

**Problema.** A S-36 nunca foi feita. Usar o projeto exige Python 3.10, `uv` e linha de
comando. Com a Fase 6 fechada e a interface estável, é o item que transforma "meu projeto" em
"programa que outra pessoa usa".

**Solução.** PyInstaller em modo `--onedir` (não `--onefile`: o `--onefile` extrai para temp a
cada execução e o torch torna isso lento demais). Pontos que este projeto específico impõe:

- **`torch` e `torchvision` dominam o tamanho.** Um build com `+cpu` fica em ~500 MB–1 GB.
  Alternativa real: **empacotar só o `onnxruntime` e o `.onnx` da S-30**, e deixar o torch
  fora. A inferência não precisa de torch; o **treino** precisa. Isso divide o produto em
  "leitor" (leve) e "leitor + treinador" (pesado), e é uma decisão de produto, não técnica.
- `data/`, `models/` e `assets/piece_images/` precisam de caminho gravável ao lado do
  executável, não dentro dele. `config.PROJECT_ROOT` usa `Path(__file__).resolve().parents[2]`,
  que num bundle aponta para dentro do pacote — precisa de um ramo para `sys.frozen`.
- WebView2 é runtime do sistema, não empacotável. O instalador checa e avisa; a aba Leitura já
  degrada bem sem ele.
- Stockfish (S-33) continua opcional e fora do bundle.

**Critério de aceite.** Um `.zip` ou instalador que roda numa máquina Windows limpa, sem
Python, e abre um PDF e reconhece um diagrama. O tamanho declarado no README, com a nota sobre
o que o build leve não faz.

---

# Fase 11 — O modelo, quando ele for o gargalo

**Esta fase tem uma pré-condição, e ela é o item.** Hoje o classificador não é o gargalo: a
medição de campo mostra que o problema está no que chega até ele (S-38), em como chega (S-39)
e no que a página diz em texto (S-42 a S-45). Só depois que a Fase 7 fechar e o conjunto de
campo da S-41 disser que o erro restante é de classificação é que estes dois itens valem o
custo de retreinar tudo.

Ficam especificados agora porque a decisão de *não* fazê-los precisa ser tão explícita quanto
a de fazê-los — a Fase 5 já gastou uma grade de experimentos para descobrir que a arquitetura
não era o problema.

## S-62 · Modelo por tabuleiro em vez de 64 decisões independentes

**Problema.** `PieceClassifier` decide 64 vezes, cada casa isolada da vizinhança e da posição
que ela ocupa. É por isso que `decode.py` existe: o argmax não tem nenhuma obrigação de
produzir posição legal, e a decodificação com restrições é uma busca **posterior** que
conserta o que o modelo não sabia que estava errado.

A informação que falta ao modelo é justamente a que o decodificador usa depois:

- **Quantos há de cada.** Um rei branco em e1 torna outro rei branco em g3 impossível, e o
  modelo que olha g3 não sabe de e1.
- **Onde a casa está.** Peão na 1ª ou 8ª fila é impossível, e o modelo não recebe a
  coordenada. Também não recebe a **paridade da casa** — e uma peça branca em casa escura tem
  contraste oposto ao da mesma peça em casa clara, que é informação de aparência, não só de
  regra.
- **A vizinhança.** Estrutura de peões, rei encastelado ao lado da torre: correlações que o
  domínio tem e o modelo não pode ver.

**Solução.** Dois degraus, do mais barato ao mais caro, e o primeiro pode não precisar do
segundo:

**(a) Canais de coordenada e paridade.** Somar 2 ou 3 canais de entrada ao recorte da casa:
paridade (claro/escuro), fila normalizada, coluna normalizada. Custo: ~1% de parâmetros, um
retreino, e nenhuma mudança de arquitetura. Ganho esperado: a confusão peão-na-1ª-fila
desaparece por construção, e a normalização de contraste por paridade fica implícita.

Isso muda `ArchConfig` (mais um fator, mais uma versão) e por isso depende da mesma disciplina
que a S-39: o checkpoint tem de dizer o que ele espera receber.

**(b) Cabeça por tabuleiro.** As 64 saídas do tronco convolucional viram uma sequência de 64
embeddings, e uma cabeça leve — dois blocos de auto-atenção, ou uma GRU bidirecional sobre a
ordem de leitura — decide as 64 classes **conjuntamente**. É o mesmo tronco, o mesmo dataset,
e um lote passa a ser um tabuleiro em vez de 128 casas soltas.

Consequência que precisa estar clara antes de começar: **isso muda o `BoardGroupedSampler` e
o regime de BatchNorm da S-26.** O amostrador por janela existe justamente porque um lote de
2 tabuleiros deixava o BatchNorm ruidoso; com o tabuleiro como unidade, o lote passa a ser N
tabuleiros por construção e a decisão da S-26 precisa ser remedida, não herdada.

**A relação com o `decode.py`.** O decodificador **não** sai. Ele continua sendo a garantia
dura — um modelo que aprende a preferir posições legais ainda pode emitir uma ilegal, e a
busca com restrições é o que impede isso de chegar ao PGN. O que muda é a frequência com que
ele precisa reparar, e `DecodeResult.changed_squares` já mede exatamente isso: é a métrica
deste item.

**Critério de aceite.** Medido no conjunto de campo da S-41, não no split de teste:

- casas reparadas por `decode_constrained` cai pelo menos pela metade;
- a taxa de exportação sobe;
- o custo de inferência por diagrama não passa de 1,5× o de hoje — acima disso o item compete
  com a S-61, que quer cortar o custo pela metade.

Se qualquer um dos três falhar, o item **não entra**, e o resultado negativo vai para o
EXPERIMENTS.md junto com o TTA, os pesos de classe e a temperatura calibrada. É a regra da
Fase 5, e ela é o que faz este projeto poder dizer "medido" em vez de "melhorado".

**Testes.** Paridade numérica: com os canais extras zerados, (a) reproduz a saída do modelo
de hoje. Um checkpoint sem os canais carregado num pipeline com eles falha alto, com as duas
versões na mensagem.

---

## S-63 · Higiene do dataset: órfãos, ausentes e o que a auditoria só relata

**Problema.** `cvoff-audit`, rodado em 2026-08-09:

```
  Linhas no CSV .................. 3241
  Rótulos utilizáveis ............ 3240
    Imagem ausente ............... 1
    Amostras redundantes ......... 248 em 227 grupos
    Imagens órfãs ................ 49
```

As 49 imagens órfãs são PNGs em `data/samples/` sem linha no CSV — restos de linhas removidas
pela aba Dataset (`dataset_browser.delete_rows` apaga a linha, não o arquivo). A ~1,8 MiB cada,
são ~90 MiB de disco que nada referencia.

A linha com imagem ausente é o inverso: um rótulo apontando para um PNG que sumiu. Ela é
descartada em silêncio no carregamento (`_load_entries` avisa, mas por `warnings.warn`, que no
uso pela GUI ninguém vê).

E as redundâncias cresceram: o BASELINE.md registra 234 em 220 grupos; hoje são **248 em 227**.
Continuam todas no mesmo split (verificado: 0 grupos espalhados), então a garantia da S-07
está de pé — mas o crescimento não é monitorado por nada.

**Solução.** `cvoff-audit` ganha as ações que hoje faltam, no mesmo padrão das que já tem
(relatar por padrão, agir só com flag, sempre com backup):

```
cvoff-audit --prune-orphans      # apaga PNG sem linha no CSV, listando antes
cvoff-audit --drop-missing       # remove linha cujo PNG sumiu
```

E um alerta quando a fração de redundantes passar de um teto — é o tipo de crescimento que
não dói até doer, e que corrói a validação se um dia um grupo se dividir.

**Critério de aceite.** Depois de `--prune-orphans`, `data/samples/` e `labels.csv` têm o
mesmo conjunto de nomes. Nenhuma ação destrutiva sem backup e sem listar o que vai fazer.

---

# Apêndice · Índice de referências cruzadas

| item | depende de | referenciado por |
|---|---|---|
| S-56 splits | S-07 | S-51, e todo treino futuro |
| S-57 lock e checkpoint | S-31, S-25 (`atomic_io`) | S-60 |
| S-58 float no CSV | S-19 | S-51, S-52 |
| S-59 redirect e esquema | S-32 | — |
| S-60 fechar durante operação longa | S-24, S-57 | — |
| S-61 custo da varredura | — | S-45, S-48, S-34 |
| S-37 ambiente | — | todos |
| S-38 `BoardVerifier` | S-41 (para derivar o piso) | S-41 |
| S-39 `BoardNormalizer` | S-27 (versionar arquitetura) | S-40, S-45 |
| S-40 aumento | S-39 | S-41 |
| S-41 conjunto de campo | S-08 (a disciplina do baseline) | S-38, S-39, S-40, S-44, S-45, S-48 |
| S-42 `TextRecognizer` | S-30 (`onnxruntime`), S-32 (o desenho de opt-in) | S-43 |
| S-43 `CaptionReader` | S-16, S-42 | S-46 |
| S-44 glifo `W`/`B` | S-22 (fila para rotular), S-27 (laço de treino) | S-45 |
| S-45 coordenadas | S-44 | S-13 (fecha a pendência), S-48 |
| S-46 solução | S-43 | S-22 |
| S-47 `Trainer` | — | S-40 |
| S-48 `OrientationPolicy` | S-13 | S-45 |
| S-49 `DiagramEditorModel` | S-31 | S-53 |
| S-50 `BoardModel`/`Renderer` | S-20 | S-53 |
| S-51 `LabelStore` | S-19, S-25 | S-52 |
| S-52 procedência | S-51, S-06 (`dhash`) | S-07 (split por livro) |
| S-53 framework | S-50 | S-54 |
| S-54 Streamlit | S-31 | — |
| S-55 empacotamento | S-30 (ONNX para o build leve) | — |
| S-62 modelo por tabuleiro | S-41 (é a pré-condição), S-26, S-27 | S-11 (reduz o reparo, não o substitui) |
| S-63 higiene do dataset | S-06 | S-52 |
