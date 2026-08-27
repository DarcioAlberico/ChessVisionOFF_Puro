# Especificação das melhorias — Fases 7 a 13 (S-37 a S-77)

Continuação de [SPEC.md](SPEC.md), que cobre S-01 a S-36. Sequenciamento e a medição que
motiva cada item: [ROADMAP_FASE7.md](ROADMAP_FASE7.md).

> **Onde mora a spec de cada item (S-NN).** A spec está em cinco arquivos, e essa dispersão
> custou duas entregas — a S-76 e a S-77 ficaram três meses em documento nenhum, e as duas
> eram deste arquivo (S-133). `tests/test_docs.py` confere esta tabela contra o disco (S-134):
> item entregue sem seção e seção no arquivo errado fazem a suíte falhar.
>
> | itens | arquivo |
> |---|---|
> | S-01 a S-36 | [SPEC.md](SPEC.md) |
> | S-37 a S-77 | [SPEC_FASE7.md](SPEC_FASE7.md) |
> | S-78 a S-82, S-143, S-175 | [ANALISE_DETECCAO.md](ANALISE_DETECCAO.md) |
> | S-83 a S-94 | [PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md) |
> | S-95 a S-142, S-218, S-219 | [SPEC_FASE14.md](SPEC_FASE14.md) |
> | S-144 a S-170 | [SPEC_UI.md](SPEC_UI.md) |
> | S-178 a S-217 | [SPEC_TEXTO.md](SPEC_TEXTO.md) |
> | S-220 a S-234, S-324 | [SPEC_APARENCIA.md](SPEC_APARENCIA.md) |
> | S-235 a S-267, S-291 a S-293 | [SPEC_EDITOR.md](SPEC_EDITOR.md) |
> | S-268 a S-290 | [SPEC_ESTUDO.md](SPEC_ESTUDO.md) |
> | S-296 a S-323, S-325 a S-327 | [SPEC_REVISAO.md](SPEC_REVISAO.md) |

> **Ressalva de 2026-08-16.** Quatro itens deste documento — **S-38b, S-40, S-62a e S-62b** —
> foram reprovados pela taxa de exportação do conjunto de campo. A avaliação registrada em
> [ROADMAP_FASE14.md](ROADMAP_FASE14.md) mostrou que essa métrica **mede confiança e não
> correção**: 1 de 39 diagramas anotados carrega FEN de referência, e essa uma é uma alucinação
> do próprio modelo sobre uma capa (S-95, S-96). Isso não torna os quatro vereditos errados —
> torna-os **não tomados**. Reabri-los depende da Fase 14.

Os itens **S-56 a S-61** vêm primeiro no documento porque são **defeitos abertos hoje**, não
melhorias. A numeração é maior porque foram encontrados na segunda passada da análise, depois
de S-37 a S-55 já estarem escritos.

Os itens **S-64 a S-71** são posteriores ao fechamento das Fases 7 a 11 e não saíram de
varredura: saíram de uso. Cada um nasceu de alguém trabalhando com o produto e esbarrando em
algo — daí eles serem escritos *depois* de implementados, ao contrário de todos os anteriores.
Os quatro últimos formam a **Fase 12**, no fim deste documento.

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

## S-61 · O custo de uma varredura: duas ineficiências estruturais ✅ implementada e medida (2026-08-11)

> **Entregue as duas.** (a) A orientação automática manda as duas leituras num único
> `forward` de 128 casas: **−24,5%** na inferência de uma página de 6 diagramas. (b) `OpenPdf`
> em `pdf_io.py` — uma abertura por varredura em vez de três por página: no
> `Secrets of Chess Training`, **143,0 s → 0,040 s**.
>
> Os dois critérios de aceite estão travados por teste: uma varredura de 3 páginas faz **1**
> abertura, e as dez métricas do conjunto de campo são idênticas antes e depois, dígito a
> dígito. O atalho por coordenadas da parte (a) **não** entrou, porque a S-45 foi adiada por
> medição — o que sobra é o quarto que a fusão de lote dá de graça.
>
> **A decisão que o item obrigou a tomar:** o empréstimo não levanta quando o arquivo não
> abre. Ele é otimização, não validação, e quem falha continua sendo `_render_pdf_page`, com
> a mensagem que sempre deu.


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

## S-64 · O recorte embutido que traz o rodapé junto ✅ implementada e medida (2026-08-09)

> **Fora de fase, como a 7.0.** Não é melhoria: é recorte deslocado produzindo **posição
> errada**, e uma delas passava pelo gate de exportação. Entrou antes dos itens abertos pelo
> mesmo motivo que os seis defeitos da segunda análise entraram.

**Problema.** A imagem que o PDF embute não é sempre só o tabuleiro: no `Karpov 1` ela inclui
a faixa de avaliação (`△`, `+−`) abaixo dele. `split_board_into_cells` divide a imagem em
oito filas iguais, e num recorte de 712 px cujo tabuleiro tem 630 cada fila lida mede 89 px
onde a real mede 79. O desvio acumula para baixo e passa de uma casa inteira na fila 1.

Medido no `Karpov 1`, páginas 70-99, 173 diagramas: **14 chegavam ao classificador como
recorte cru**, e **8 entregavam posição errada** — uma delas com confiança 0,9385, acima do
gate da S-15, indo para o PGN principal como se estivesse certa.

**As três guardas que deviam ter pego, e por que cada uma calou.** É o que o item mais
ensina, porque nenhuma delas estava quebrada:

| guarda | por que calou |
|---|---|
| `trim_to_grid` | procura as 7 linhas internas da grade no gradiente. Em casa **hachurada** elas não existem: a fronteira clara/escura é textura, não traço |
| `refine_candidate_with_contour` | achou um quad pior, e a S-38a corretamente o descartou — restando o recorte cru |
| `board_texture_score` | 0,3607 no recorte errado contra 0,3897 no certo: **0,03**, quase cego ao alinhamento da grade |

A terceira é a que delimita a S-38a: o sinal com que ela julga um recorte quase não vê a
única coisa que decide se a leitura está certa. Ela continua pegando o trapézio de texto, que
é outra ordem de erro; não pega deslocamento de uma casa.

E `trim_to_grid` **não falha por limiar**: desiste em `_board_span`, antes de avaliar a
periodicidade. O passo mediano entre picos sai 9 px e 32 px onde a casa tem 82 e 88 — o que
ela acha é a moldura e as bordas das peças. Afrouxar `min_periodicity` não muda nada, e há
teste que trava essa premissa para que ninguém tente.

**Solução.** `detection/embedded.trim_to_frame`, segunda tentativa com um sinal que existe
nessas imagens: a **moldura impressa**, uma linha reta escura atravessando a imagem inteira.

```python
# src/chess_diagram_ocr/detection/embedded.py
def trim_to_frame(image_rgb, *, dark_level=128, min_fill=0.80,
                  min_coverage=0.55, aspect_tolerance=0.10, inset=3) -> tuple[np.ndarray, bool]: ...
```

Mesmo contrato de `trim_to_grid`: sem confiança, a imagem volta inalterada. Roda **só quando
a primeira não confiou** — a primeira usa o sinal mais específico e continua tendo
precedência, e há teste que confere que ela não é sequer consultada quando a grade responde.

Três guardas próprias, e cada uma fecha um jeito de errar: o que sobra dentro da moldura tem
de ser quase quadrado (senão uma tarja ou um sublinhado vira "moldura"), tem de cobrir a
maior parte da imagem, e a moldura não pode ser a própria borda do recorte (aí não há o que
aparar, e dizer que aparou inflaria o `detector_score`). O `min_fill` de 0,80 não precisa de
calibração por livro porque o vale é largo: peças pretas chegam a ~0,45, moldura passa de
0,95.

**Medido em 606 diagramas de 6 livros**, com o "antes" obtido desligando a função:

| livro | diagramas | conf. média | abaixo do gate | FENs corrigidas |
|---|---|---|---|---|
| **Karpov 1** | 173 | 0,9635 → **0,9889** | 14 → **4** | **10** |
| **Kemeri 1937** | 15 | 0,9330 → **0,9661** | 2 → **1** | 0 |
| Karpov 2 | 114 | 0,9493 → 0,9493 | 10 → 10 | 0 |
| Polgar 5334 | 108 | 1,0000 → 1,0000 | 0 → 0 | 0 |
| Aagaard Endgame | 120 | 1,0000 → 1,0000 | 0 → 0 | 0 |
| Reinfeld ES | 76 | 0,8449 → 0,8449 | 21 → 21 | 0 |

Zero regressão: nenhum diagrama piorou, e nos quatro livros sem o defeito nada se moveu.

**Critério de aceite — atingido.** Contra o conjunto de campo da S-41: taxa de exportação
**0,6842 → 0,7368**, com recall (0,9211) e precisão de detecção (0,9722) **inalterados**. O
regime vetorial fechou em 1,000 (14/14). É o primeiro item desde a S-38a a mover a métrica
primária da Fase 7. `docs/metrics/field_20260809_s64_moldura.json`.

**O que isto deixa em aberto.** O sinal que separava os 14 defeituosos com precisão perfeita
era gratuito e ninguém olhava: **os 159 recortes corretos eram exatamente quadrados e os 14
defeituosos não.** Depois desta correção o aparo pela moldura devolve algo quase quadrado
(proporção ~0,96), então a regra "não quadrado é suspeito" perdeu o gume — mas a observação
fica registrada, porque um candidato que chega ao classificador sem ter passado nem por warp
nem por aparo é um candidato cuja grade ninguém conferiu, e hoje nada o marca como tal.

---

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

> **(a) implementada (2026-08-09); (b) adiada por medição.**
>
> A parte (a) — o refino não pode piorar o recorte — está em
> `detection/hybrid.refine_candidate_with_contour`. Medida no conjunto de campo: os
> detectados que produzem posição legal foram de **33 para 35 de 35**, e a taxa de
> exportação **não se moveu** (0,6842), porque as leituras que substituíram as ilegais saem
> a 0,664 e 0,467 — abaixo do gate. Em todo o conjunto, 2 refinos foram descartados,
> exatamente os previstos.
>
> A parte (b) — o piso de textura para todo candidato — **não foi feita, e a medição diz
> para não fazer agora**: a precisão de detecção é 0,9722 (um falso positivo em 36), então
> um piso tem um a ganhar e 35 a arriscar. Dos 12 diagramas que não chegam ao PGN, **9 são
> confiança abaixo do gate** e 3 são não-detecção; nenhum é ilegalidade. Quem ataca os 9 é a
> S-39 e a S-40. A parte (b) segue especificada abaixo, e continua certa como arquitetura.

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

## S-40 · Aumento de dados dirigido ao acervo ✅ implementada · ⏸ **não entra** (medida 2026-08-11)

> **Medida a 8 e a 16 épocas, contra o `aug0` retreinado com a mesma semente.** A taxa de
> exportação não se moveu — 0,7368 nas duas rodadas — e **pela letra do critério de aceite o
> item não entra**, porque ele pede ganho no conjunto de campo.
>
> **A 16 épocas, porém, o dirigido domina o controle em tudo o mais**: reparo do decodificador
> de 15 para **9** (−40%), `val_board_exact_acc` 0,9820 contra 0,9790, mesmo custo. E o
> controle está **convergido, verificado**: oito épocas extras não superaram a sétima e o
> checkpoint no disco não chegou a ser tocado.
>
> **O espelhamento sozinho piorou a métrica primária** (0,7105) — a transformação que esta
> spec chamava de "a duplicação de dataset mais barata disponível".
>
> **E a medição encontrou um defeito no instrumento, não só no aumento.** A distribuição de
> confiança do conjunto de campo é bimodal com a vizinhança do gate **vazia**: 27 dos 36
> diagramas acima de 0,99, nada entre 0,60 e 0,80, e os 8 barrados abaixo de 0,43. Nenhuma
> mudança de modelo pode ganhar um diagrama ali; só perder. Ver 7.7 do
> [ROADMAP_FASE7.md](ROADMAP_FASE7.md).
>
> `models/s40_mhsp_16ep.pt` fica como **candidato** ao próximo retreino de produção. O padrão
> de `AugmentConfig()` não foi trocado: essa decisão precisa de um conjunto de campo com poder
> de resolução.


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

## S-42 · `TextRecognizer` — motor de OCR opcional e plugável ✅ implementada (2026-08-09)

> **Estado.** `src/chess_diagram_ocr/ocr.py`, extra `ocr` no `pyproject.toml`, seção `ocr` no
> `data/settings.json`, `CVOFF_OCR_ENABLED`/`CVOFF_OCR_ENGINE`, e a opção `--ocr` em
> `cvoff-field` e `cvoff-export`. Três provedores: RapidOCR (padrão), EasyOCR e Tesseract.
> **Nenhum está instalado nesta máquina**, então o que está medido é o contrato — que a
> ausência devolve `None` em vez de levantar, e que importar o módulo não carrega motor
> nenhum — e não a acurácia de nenhum deles. Ver [EXPERIMENTS_FASE7.md](EXPERIMENTS_FASE7.md).

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

## S-43 · `CaptionReader` — OCR da faixa de legenda, não da página ✅ implementada (2026-08-09)

> **Estado.** `src/chess_diagram_ocr/ocr_caption.py`, com a decisão **por diagrama** (o motor
> só roda onde a camada de texto calou naquela vizinhança), a faixa de margem lida à parte por
> `pdf_text.page_scope_declaration`, e a procedência em `DiagramContext.side_to_move_origin` →
> `[SideToMoveSource]` / `[SideToMoveConfidence]`.
>
> **O que foi medido:** com `--ocr off`, o conjunto de campo dá 0,6842 — idêntico à S-38a — e
> as 15 páginas produzem **0** declarações de escopo pela camada de texto, o que prova que o
> caminho novo está inerte sem motor.
>
> **Medido em 2026-08-11, com o extra instalado — e o critério de aceite principal falhava.**
> A página 40 do `Reinfeld` **não** saía declarada: `page_scope_declaration` lia a faixa de
> `MARGIN_BAND` (7% da altura), que naquela página são 34,6 pt e cortam a linha do cabeçalho
> ao meio. O RapidOCR devolvia `TIEAANDDIVEDA` **com 0,71 de confiança** — um motor não avisa
> quando recebe meia linha, e o limiar de 0,3 da S-42 não tinha como pegar isso.
>
> A correção é uma constante separada, `ocr_caption.SCOPE_BAND = 0,12`, porque as duas frações
> respondem a perguntas diferentes: `MARGIN_BAND` decide o que **descartar** como cabeçalho
> corrente e apertá-la erra para o lado seguro; `SCOPE_BAND` é o que o **motor vê**. Com ela,
> os diagramas da página saem em `ocr-page-scope` e os números de exercício aparecem.
>
> **O que isso vale no acervo, medido por `cvoff-sides`:** o `Reinfeld_1001` sai de **40 de 41
> diagramas assumidos para 0 de 41**. São ~1.900 exercícios em 320 páginas, metade deles de
> pretas — até aqui o livro inteiro saía como `default` = brancas.
>
> Custo medido: **2,0 a 3,4 s por diagrama** cuja vizinhança a camada de texto deixou vazia.
>
> **Uma correção ao texto abaixo:** a spec propunha que a faixa de margem "passa a ser testada
> contra os padrões antes de ser descartada". Ela é testada, mas **fora** do fluxo normal e só
> como último escalão — a legenda do diagrama decide antes, sempre. Foi o que o levantamento
> de 2026-08-09 recomendou ao mostrar que uma das 6 declarações da faixa é o
> `2.1 White to Move #2` do `Polgar`, cabeçalho de seção e declaração verdadeira ao mesmo
> tempo. Reinseri-la no fluxo normal a poria competindo com legendas que já funcionam.

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
  topo e do rodapé, como cabeçalho corrente. **Medido (2026-08-09): vale 6 declarações
  contra as 150 que a S-16 já vê, em 3 livros** -- e uma das 6 é o `2.1 White to Move #2` do
  `Polgar`, um cabeçalho de seção que é ao mesmo tempo uma declaração de escopo verdadeira.
  Distinguir "cabeçalho que declara" de "cabeçalho que repete" não é a mudança de uma linha
  que o parágrafo abaixo sugere. Medido: a página 40 do
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

> **Medido (2026-08-09): a parte (a) não tem o que ler, e a (b) alcança um livro.**
>
> Varridas as linhas de 1 a 3 caracteres na vizinhança de 380 diagramas em 19 livros com
> camada de texto: **nenhum marcador `W`/`B`**. Os 5 livros que o levantamento acusou são
> falso positivo dele mesmo -- glifos da fonte de xadrez sobrepostos ao tabuleiro (`+` ×382,
> `P`/`O`/`R` ×78). E o único livro do acervo que **tem** o marcador impresso, o `GALLAGHER`,
> não tem camada de texto.
>
> A parte (a) descrita abaixo -- padrão de letra isolada na camada de texto -- portanto
> **não entra**: alcance 0 de 27. A parte (b), o classificador de glifo, continua sendo o
> único caminho e precisa de um dataset anotado à mão para alcançar **1 livro**.
> Ver docs/EXPERIMENTS_FASE7.md.

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

> **Medido (2026-08-09): 13,7% de cobertura, e a pendência que ela fecharia pode não existir.**
>
> Em 380 diagramas com camada de texto, **52 (13,7%)** têm as filas legíveis e **2 (0,5%)**
> têm as colunas. Dos 52, **48 são do `Polgar 5334`** -- que já lê a 1,000 no conjunto de
> campo. E dos 49 conclusivos, **49 são do ponto de vista das brancas e 0 das pretas**.
>
> A pendência da S-13 que este item existe para fechar não apareceu uma vez em 49 diagramas
> com evidência. O item **não entra agora**; o benefício de registro de grade continua real
> e continua limitado a onde há coordenada. Ver docs/EXPERIMENTS_FASE7.md.

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

## S-46 · A solução em notação algébrica como validador cruzado ⏸ **adiada por medição** (2026-08-11)

> **Não implementada, e o motivo é um número.** Medido em 239 diagramas de 32 livros: 21,3%
> têm algo com forma de lance no texto vizinho, e **apenas 13,7% desses são legais na posição
> lida**. O texto perto de um diagrama é a continuação da partida, não a solução dele — os
> livros que mais disparam o padrão são de análise (`A Matter of Endgame Technique`,
> `Euwe Band 7`, `Practical Chess Defence`), não de exercício.
>
> Com esse sinal, 44 dos 51 casos virariam "discordância" e iriam para a fila da S-22, que
> existe para ser seletiva. Ver [EXPERIMENTS_FASE7.md](EXPERIMENTS_FASE7.md).
>
> A ideia continua certa; o que falta é a associação exercício↔solução por editora, que é
> exatamente o trabalho que o parágrafo "por que é opcional" abaixo previu.


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

## S-47 · `Trainer` — quebrar `train_model` ✅ implementada (2026-08-09)

> **Estado.** `TrainingPlan` (com `DataPlan`/`OptimPlan`/`OutputPlan`), `BestEpochPolicy` e
> `Trainer` em `training.py`. `train_model` mantém a assinatura -- são trinta chamadores -- e
> o corpo dela são 25 linhas: montar o plano e chamar `Trainer.fit()`.
>
> **O critério de aceite literal ("`train_model` abaixo de 40 linhas") mede a coisa errada, e
> o número honesto é outro.** A função tem 76 linhas, das quais 24 são a assinatura de 18
> parâmetros e 26 são o docstring que descreve `splits_path`, `assign_splits`, `fresh` e
> `cancel_event`. Encurtar qualquer uma das duas seria piorar a interface para satisfazer uma
> contagem. O que o item prometia -- que a decisão de "melhor época" deixasse de exigir um
> treino para ser exercitada -- está em `tests/test_training.py::BestEpochPolicyTests`.
>
> **Métricas idênticas, verificado.** `test_rodar_as_etapas_a_mao_da_o_mesmo_que_fit` compara
> `Trainer(plan).fit()` com `prepare → resume → run_epoch → run_epoch → finish` sob a mesma
> semente e exige igualdade até o último dígito em `train_loss`, `train_square_acc`,
> `val_loss`, `val_board_exact_acc`, `is_best` e temperatura. A ordem das operações aleatórias
> foi preservada de propósito: `set_seed` primeiro, modelo antes de qualquer loader, e todo
> sorteio posterior com gerador explícito.


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

## S-48 · `OrientationPolicy` — a cascata de quatro regras vira estratégia ✅ implementada (2026-08-09)

> **Estado.** `src/chess_diagram_ocr/orientation.py`. `OrientedPrediction` mudou de casa junto
> (é o resultado da **decisão**, não da inferência) e `inference` a reexporta, então nenhum
> chamador mudou. `predict_with_orientation` ficou com o que só ela pode fazer: rodar o modelo
> duas vezes.
>
> **Uma alteração de contrato em relação a esta spec.** `decide` devolve um
> `OrientationVerdict` de três campos e não a `tuple[bool, str]` desenhada aqui, porque
> `ambiguous` é **por regra** e a tupla o perderia: legalidade que discorda da confiança é
> ambígua por definição, margem decisiva não é, e o desempate final é ambíguo sempre.
> Derivá-lo fora da regra exigiria que a política soubesse qual regra decidiu -- o acoplamento
> que o item desfaz.
>
> **`CoordinateRule` está na cascata e cala em 100% dos diagramas**, porque nada produz
> `BoardCoordinates` -- a S-45 foi medida e adiada. É por isso que o resultado é idêntico ao
> de antes, que é o critério de aceite. O que ela compra por vinte linhas: quando a S-45
> voltar, ela vira um problema de produzir o dado, não de mexer na política.
>
> **`explain()` virou teste.** `tests/test_orientation.py` exercita cada regra isolada com
> `BoardPrediction` sintético e sem torch, e o teste que mais diz sobre o item resolve o mesmo
> par de leituras com duas ordens de cascata e recebe duas respostas.


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

## S-49 · `DiagramEditorModel` — o estado do editor fora do widget ✅ implementada (2026-08-09)

> **Estado.** `src/chess_diagram_ocr/ui/editor_model.py`, sem `import tkinter` (há teste que
> varre a árvore de importação -- e sobre a árvore, não sobre o texto, porque o docstring cita
> `import tkinter` para dizer que ele não existe ali).
>
> **O item era organização; o que ele encontrou era conserto** -- de novo, como na S-51.
> `save_all` **nunca olhava o vínculo**: com uma linha da aba Dataset aberta, "Salvar todos"
> criava uma amostra nova da mesma imagem em vez de regravar o rótulo. É exatamente o defeito
> que a S-23 fechou no caminho do `Ctrl+S`, e que continuava aberto ao lado. Só apareceu
> porque `save_target()` passou a ser uma pergunta feita uma vez e respondida em dois lugares.
>
> **`load()` recusa estado impossível em vez de confiar em quem chama.** Um vínculo sem a
> âncora correspondente, ou duas âncoras ao mesmo tempo, levantam `ValueError`. Era o defeito
> latente dos quatro caminhos antigos: cada um zerava dois campos e escrevia o terceiro por
> conta própria, e esquecer de zerar um produzia um editor que grava a linha do dataset **e**
> fecha um item da fila que ninguém corrigiu.
>
> **`ResultPanel` ficou em 648 linhas, não abaixo de 400.** A spec foi escrita quando ele
> tinha 672 e ele já estava em 800 quando o item começou. O que saiu foi o que o item existe
> para tirar -- zero linhas de regra de edição sobrevivem ali -- mais o botão "Corrigir Net",
> que virou `ui/net_button.py`. O resto é layout (~95 linhas de `_build`), repasse ao modelo e
> caixas de diálogo; cortar mais seria separar um widget da própria construção.


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

## S-50 · `BoardModel` + `BoardRenderer` — quebrar `InteractiveBoard` ✅ implementada (2026-08-09)

> **Estado.** `ui/board_model.py` (sem tkinter, com teste de árvore de importação),
> `ui/board_render.py` (só desenho, mais `BoardGeometry` e `PieceImages`), e
> `ui/board_widget.py` reduzido à casca Tk: canvas, eventos, pixels de arraste, tooltip e
> paleta. `InteractiveBoard` foi de 606 para **390** linhas; a API pública não mudou.
>
> **`draw_dirty` existe e tem um limite honesto.** Cada casa desenha com a tag `sq{índice}`, e
> `BoardChange.dirty` diz quais refazer -- arrastar uma peça toca 2 casas. Mas o parcial vale
> **só em `mode="edit"`**: em modo de jogo o conjunto de alvos legais muda a cada seleção e
> não está em `dirty`, então ali o redesenho total continua. O modo de edição é o que importa
> para o custo, porque é onde o arraste acontece.
>
> **Um detalhe que só apareceu ao escrever o código.** Uma edição invalida os sinais do modelo
> (confiança, probabilidades, casas reparadas), e as casas que **perderam** o contorno azul
> também precisam ser redesenhadas -- senão o contorno de uma casa que ninguém tocou fica na
> tela. `_apply_placement` junta essas casas ao `dirty`, e há teste para isso.
>
> **`promotion_chooser` é uma `Callable` no modelo, não um diálogo.** Em teste é um
> `lambda: chess.QUEEN`, e o modelo continua sem saber que existe uma janela.


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

## S-51 · `LabelStore` — uma porta para o `labels.csv` ✅ implementada (2026-08-09)

> **Estado.** `src/chess_diagram_ocr/labels.py`. Os cinco módulos migrados, mais um **sexto**
> que a varredura do critério de aceite encontrou e que nenhum levantamento tinha listado:
> `review_queue.rare_classes_from_labels`.
>
> **Três defeitos que a migração fechou, e que não eram o objetivo do item.** Os três
> caminhos de escrita do `audit.py` -- `apply_side_to_move_fixes`, `quarantine_fatal_labels` e
> `remove_duplicate_labels`, todos alcançáveis por `cvoff-audit --fix` -- gravavam com
> `to_csv` direto no destino: **sem escrita atômica** (o `atomic_io` promete cobrir este
> arquivo) e **sem a normalização de inteiro da S-58** (o `--fix` reintroduzia o `20.0` que a
> S-58 tinha acabado de corrigir). O `save_splits` tinha o mesmo defeito de atomicidade, num
> arquivo que carrega a fronteira entre treino e teste.
>
> **Uma decisão que a spec não previa: `csv` da biblioteca padrão, não pandas.** A S-58 existe
> porque o pandas infere tipo, e a correção de lá era uma disciplina (`dtype=str,
> keep_default_na=False`) que precisava ser lembrada em cinco lugares. Com `csv.DictReader`
> não há tipo a inferir. O defeito deixou de ser evitado e passou a não existir.
>
> **Medido:** a saída do `LabelStore` é **byte a byte idêntica** à do `_write_labels` que ele
> substituiu, verificado sobre o `data/labels.csv` real de 3.313 linhas e sobre o
> `data/splits.csv` de 3.311 -- e idêntica também aos arquivos versionados, que não mudaram um
> byte.

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

## S-52 · Recuperar a procedência dos 3.195 rótulos órfãos ✅ implementada, não medida no acervo (2026-08-09)

> **Estado.** O item tem duas metades independentes, e as duas foram implementadas.
>
> **Feita: `corrected_by` deixou de ser coluna morta.** Estava preenchida em **0 de 3.313**
> linhas. Agora toda amostra nova sai com o caminho pelo qual chegou ao rótulo --
> `ocr-aceito`, `ocr-corrigido`, `fila-revisao`, `dataset-recorrigido` ou `net-remoto` --, nas
> duas telas. A regra de precedência mora em `labels.label_route`, e não no painel, para poder
> ser testada sem abrir uma janela. `dataset_browser.route_distribution` a torna legível, e as
> 3.313 linhas anteriores saem em `caminho não registrado`: é esse número encolhendo que dirá
> se a coluna passou a valer alguma coisa.
>
> Um detalhe que só apareceu ao escrever: o painel gravava `corrected_by="tkinter"` num
> caminho -- o nome da **tela**, que é a informação sem valor que a spec avisa para não
> guardar. Virou `dataset-recorrigido`.
>
> **Feita depois: `provenance.py` + `cvoff-provenance`.** O índice é JSONL incremental (um
> livro por vez, um livro reindexado substitui o que havia dele) e o casamento é vetorizado --
> 3.195 amostras contra dezenas de milhares de diagramas são centenas de milhões de distâncias
> de Hamming, e em Python puro isso levaria horas.
>
> **Medido em 2026-08-09, contra verdade de referência.** As amostras salvas depois da S-31
> têm procedência gravada, então dá para conferir o casamento sem depender de opinião. Índice
> das 20 primeiras páginas do `1937 Kemeri`:
>
> | sonda | resultado |
> |---|---|
> | 12 amostras daquelas páginas, com procedência conhecida | **12 de 12**, todas a distância 0, todas na **página certa** |
> | os 3.195 órfãos contra o mesmo índice | **0** casamentos; impostor mais próximo a **7 bits** |
>
> **E o resultado pede cautela, não confiança.** Um recorte deslocado em 6 px num tabuleiro de
> 800 custa 6 bits — exatamente o limiar. O impostor mais próximo estava a 7. A folga é de um
> bit, com um índice de **11** entradas; com o acervo inteiro ela só encolhe. Por isso o
> `cvoff-provenance` não grava por padrão: relata a taxa e o histograma, e gravar é um segundo
> comando.
>
> **Não feito: a varredura do acervo.** Indexar os 27 PDFs (~12 mil páginas) é horas de CPU e
> uma decisão de quando, como a medição da S-40. Sem ela não há taxa real sobre os 3.195.

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

## S-53 · A decisão de framework, por gatilho e não por gosto ✅ implementada (2026-08-09)

> **Estado.** `ui/theme.py`, aplicado em `ChessOcrTkApp.__init__` antes do primeiro widget --
> trocar tema com a árvore montada refaz o layout e aparece como um piscar. Padrão
> `bootstrap-light`, trocável por `CVOFF_TTK_THEME`. A parte (b) -- os dois gatilhos do porte
> para Qt -- está no `ARCHITECTURE.md`, onde a próxima pessoa os procura.
>
> **O que precisou de teste foi a degradação, não o tema.** Sem `ttkbootstrap`, com um nome de
> tema errado ou num bundle que não o incluiu, a janela abre em `ttk` puro e o log diz por
> quê. `apply_theme` nunca levanta: aparência não pode ser motivo de a ferramenta não abrir.
>
> **Dois detalhes que a spec não previa.** O `tb.Style` não aceita `master` -- ele se prende ao
> root **padrão** do Tk --, então `apply_theme` recebe a janela para documentar a pré-condição
> real. E os nomes de tema clássicos (`litera`, `flatly`) emitem `DeprecationWarning` na 2.x e
> saem na 3.0; o padrão é um nome da era 2.0 por isso.


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

## S-65 · A paleta de edição: imagens, pincel visível e clique que desfaz ✅ implementada (2026-08-09)

**Problema.** Os 12 botões de peça desenhavam os símbolos Unicode `♙♘♗`. Isso tem três
defeitos, e nenhum é estético:

1. **Depende de a máquina ter uma fonte que os desenhe.** No Windows a `Segoe UI Symbol` os
   renderiza pequenos, finos e de altura irregular, e as seis peças brancas quase somem no
   fundo claro do botão -- num painel cujo trabalho é escolher qual peça inserir.
2. **O pincel ativo era invisível.** Pincel é um **modo**, e a única forma de saber qual peça
   estava carregada era clicar numa casa e ver o que saía -- ou seja, executar a ação
   destrutiva que se queria conferir antes.
3. **Desfazer custava três gestos.** Pôr a peça errada exigia largar o pincel, clicar com o
   botão direito e pegar o pincel de volta. Corrigir leitura de OCR é uma sequência de
   acertos e desacertos, e esse é o caminho mais percorrido da aba.

**Solução.**

- **As peças de `assets/piece_images/`**, as mesmas que aparecem no tabuleiro, por
  `PieceImages.icon(symbol, size, background=...)`. A paleta passa a mostrar exatamente o que
  o clique vai colocar.
- **Pincel visível**: os botões viraram `Radiobutton` com estado ligado. Clicar no botão já
  aceso **larga** o pincel, que é o gesto natural de quem terminou de pintar.
- **`BoardModel.paint` alterna**: clicar de novo na mesma peça apaga. Pôr e tirar passam a
  ser o mesmo gesto. A alternância vale só para pincel de peça -- com o pincel "apagar",
  alternar significaria *criar*, que é o oposto do que o botão diz.

**Três decisões que a implementação impôs, e a medição que as justifica.**

**`tk.Radiobutton` e não `ttk.Radiobutton`.** Nenhuma variante de `Toolbutton` do tema em uso
(`Toolbutton`, `primary.`, `info.`, `*.Outline.`) desenha estado selecionado quando o botão
tem imagem e não tem texto: renderizado lado a lado, o selecionado e o não selecionado saem
**idênticos**, e o pincel volta a ser invisível. O `Radiobutton` clássico com
`indicatoron=False` desenha, e é o único caminho em que o `selectcolor` é escolhido em vez de
herdado.

**As cores saem do tema, não de hexadecimal fixo.** `ttkbootstrap` traz 30 temas e metade é
escura; um `#ffffff` cravado deixaria a paleta como um retângulo branco no meio de uma janela
preta. Fundo vem de `TFrame`, e os outros dois são o texto do tema misturado ao fundo -- a
mesma conta dá contraste no claro e no escuro.

**O ícone vai sobre uma casa clara.** Os PNGs são traço com transparência, e nos temas
escuros as seis peças pretas somem no fundo da janela. Sobre a cor da casa clara elas
aparecem em qualquer tema -- e é assim que elas se parecem no tabuleiro, que é o que a paleta
está prometendo. Como o ícone ficou opaco, o botão ganhou 4 px de margem para o `selectcolor`
ter onde aparecer; sem ela o botão aceso ficaria igual aos outros onze.

**Degradação.** Sem `assets/piece_images/` -- um checkout incompleto, um PNG corrompido -- a
paleta volta ao Unicode. Uma peça faltando não pode impedir a aba de abrir.

**Critério de aceite.** Os 12 botões com imagem e sem texto; o pincel ativo distinguível em
tema claro e escuro; alternância coberta por teste sem janela (`tests/test_board_model.py`) e
paleta coberta por teste com janela (`tests/test_board_palette.py`). Conferido também no
roteiro headless do CONTRIBUTING, sobre a página 80 do `Karpov 1`.

---

## S-54 · O Streamlit precisa de uma decisão ✅ **aposentado** (2026-08-09)

> **A escolha foi aposentar.** `app_streamlit.py` → `examples/streamlit_demo.py`, e o README
> parou de chamá-lo de "interface web alternativa". Assumir custaria ~1 semana (editor por
> clique no navegador, painel de legalidade, fila de revisão) e só se paga com uso remoto
> real, que não existe.
>
> **Ele continua rodando e continua testado,** e por um motivo que não é inércia: ele importa
> o `OcrService` e quebra quando a fachada muda. É o alarme que se quer de um exemplo.
> Conferido com `streamlit.testing.v1.AppTest` depois da mudança de pasta.
>
> **A ressalva do `resolve_num_workers` sobreviveu à mudança**, e o docstring dela foi
> atualizado: continua sendo um script de topo sem guarda `if __name__ == "__main__"`, e é por
> isso que o padrão de `train_model` é 0 worker.


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

## S-55 · Empacotamento para Windows *(S-36 reaberta)* ✅ implementada e medida (2026-08-09)

> **Estado.** `packaging/cvoff.spec` + `packaging/build_windows.py`, PyInstaller `--onedir`.
> **696 MB, 5.247 arquivos.** Build completo -- leitor **e** treinador --, porque o ciclo que
> dá valor ao projeto é *corrigir → salvar → treinar* e um bundle só de leitura entregaria um
> programa sem o botão "Treinar modelo". O caminho para o build leve está na spec.
>
> **O defeito que o item nomeia, corrigido e verificado no bundle real.**
> `config.PROJECT_ROOT` usava `parents[2]`, que num bundle aponta para dentro do pacote. Agora
> há ramo `sys.frozen`, e um `BUNDLE_ROOT` novo separa recurso do programa (`assets/`, dentro)
> de dado do usuário (`data/`, `models/`, `PDF/`, `PGN/`, ao lado). Conferido: o `.exe` gravou
> `dist/ChessVisionOFF/data/app_tkinter_state.json`.
>
> **`--selftest`, que a spec não pedia e o critério de aceite exige.** Um `.exe` sem console
> não tem como dizer "aqui funciona". `ChessVisionOFF.exe --selftest --page 80` abre o PDF,
> reconhece e escreve as FENs no log -- e depois confere que o caminho de **treino** monta,
> porque ler não prova treinar e um bundle incompleto só falharia quando o usuário clicasse
> "Treinar modelo", já com dezenas de correções feitas. Códigos de saída distintos para faltas
> distintas.
>
> Medido contra o mesmo comando no checkout, página 80 do `Karpov 1`: **6 diagramas, as seis
> FENs idênticas, as seis confianças mínimas idênticas**, caminho de treino monta nos dois.
>
> **O que não foi entregue, e é decisão do dono.** O executável não é assinado (SmartScreen
> avisa na primeira execução; resolver exige certificado de assinatura de código) e não há
> instalador -- o produto é uma pasta que se descompacta.


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
  degrada bem sem ele. *(Deixou de valer na S-69: a aba saiu, e com ela `pythonnet` e
  `pywebview`. Não há runtime a checar.)*
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

## S-62 · Modelo por tabuleiro em vez de 64 decisões independentes ✅ implementada (2026-08-11)

> **Entregue, os dois degraus.** (a) `ArchConfig(coords=True)` acrescenta três planos
> constantes — paridade, fila e coluna — à entrada da casa, com `arch_version` própria
> (`...-coords`) e teste de **paridade numérica**: com os pesos das entradas novas zerados, a
> saída é bit a bit a do modelo de hoje. (b) `ArchConfig(head="board")` troca a cabeça linear
> por dois blocos de auto-atenção sobre as 64 casas, e `BoardUnitDataset` faz do tabuleiro a
> unidade de lote. A cabeça devolve **logits achatados** `(N, 13)` para que loss, acurácia
> exata, calibração e `board_probabilities` continuem sendo o mesmo código.
>
> **Medida, e reprovada nos próprios critérios.** Dois de três falham nas três variantes
> (a, b, a+b): o reparo do decodificador cai um terço em vez de metade na melhor delas, e a
> taxa de exportação não sobe em nenhuma. **O item não entra.**
>
> **As três não falham igual, e a diferença decide o que reabrir.** A (a) é a única variante
> do projeto que fez o que a S-62 existia para fazer: **−33% de reparo com 864 parâmetros a
> mais** (+0,04%), inferência mais barata que o controle e validação idêntica a ele. A (b)
> custa 1,07 M de parâmetros, **aumenta** o reparo em 27% e 1,46× o tempo. Os dois juntos
> perdem um diagrama e produzem a única leitura fatalmente ilegal de todas as variantes.
>
> **A ironia:** a métrica de aceite deste item foi mais bem satisfeita pelo aumento de dados
> da S-40 (−40% de reparo) do que pelos dois degraus arquiteturais que ele propõe. Dado, não
> arquitetura. Ver [EXPERIMENTS_FASE7.md](EXPERIMENTS_FASE7.md).
>
> **Duas coisas que a implementação ensinou.** O `BoardGroupedSampler` da S-26 **sai** neste
> regime: ele existia para aproximar "as casas do mesmo tabuleiro no mesmo lote" sem pagar o
> preço, e com o tabuleiro como unidade a aproximação perde o sentido. E `boards_per_batch=4`
> é escolha nova, não herdada: são 256 casas por passo, o dobro das 128 de hoje, vindas de 4
> posições em vez de 2 — exatamente a decisão que a S-26 pediu para ser remedida.


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

## S-63 · Higiene do dataset: órfãos, ausentes e o que a auditoria só relata ✅ implementada (2026-08-11)

> **Entregue.** `cvoff-audit --drop-missing` e `--prune-orphans`, mais o teto de redundância
> (`DUPLICATE_SHARE_CEILING = 0,10`) que alerta quando a fração passa do limite. O critério de
> aceite — `data/samples/` e `labels.csv` com o mesmo conjunto de nomes — é conferido pelo
> próprio comando ao final, e travado por teste.
>
> **Nenhuma das duas ações apaga nada, e a segunda mudou de desenho por causa da medição.** A
> poda move os PNGs para `data/orphans/<data>/`: órfão é quase sempre linha removida por engano
> pela aba Dataset. E o `--drop-missing`, que a spec descrevia como "remove a linha", passou a
> mandá-la para a **quarentena** — rodado no dataset real, os 5 rótulos nesse estado têm
> **todos** procedência preenchida, ou seja, a imagem é reextraível do livro e a FEN é trabalho
> humano que sobreviveria ao reencontro. Apagar seria jogar fora a metade cara do par para
> limpar a metade barata.
>
> **Duas correções aos números da spec**, medidos em 2026-08-11: são **5** rótulos sem imagem
> (não 1) e os 49 órfãos pesam **41,4 MiB** (não ~90).


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

# Fase 12 — Depois do fechamento: o que o uso pediu

Os seis itens abaixo vieram de trabalhar com o produto, não de analisar o código. Dois deles
(**S-66**, **S-67**) nasceram ainda dentro das Fases 9 e 10 e ficaram sem spec na época; os
quatro seguintes (**S-68** a **S-71**) são a Fase 12 e têm um só assunto: **a página exibida
deixa de ser uma figura e passa a ser onde se trabalha.**

## S-66 · O leitor externo como segunda opinião **local** ✅ implementada (2026-08-09)

**Problema.** Conferir um diagrama é olhar 64 casas. Quem captura um livro novo faz isso
diagrama a diagrama, e é esse custo humano — não o tempo de máquina, que é de décimos de
segundo — que limita quantas amostras entram no `labels.csv`. E há livros em que o
classificador local simplesmente afunda: no `Niemeijer - Zwarte Magie (1945)` a confiança
mínima média é 0,25 e **nenhum** dos 20 diagramas passa do gate.

**Solução.** Um adaptador para o `Chess_diagram_to_FEN` (MIT, Jost Triller), que satisfaz o
`RemoteFenProvider` da S-32 — que é `Protocol` justamente para isto: aquele docstring já dizia
que um segundo modelo local satisfaria a mesma interface. E `second_opinion.py` compara as duas
leituras e devolve **as casas em que elas discordam**.

Medido nos mesmos 20 diagramas:

| | leitor local | externo |
|---|---|---|
| coerentes com o tema do livro (1 rei de cada, ≥1 dama preta, sem peão na borda) | 12/20 | **18/20** |
| `p6_d0` / `p6_d1` / `p13_d2`, conferidos casa a casa | 60 / 41 / 23 de 64 | **64 / 64 / 64** |
| mediana de casas em desacordo entre os dois | — | **4,5** |

Nos três diagramas conferidos à mão, o conjunto em desacordo era **exatamente** o conjunto de
erros do leitor local — 4 de 4, 23 de 23, 41 de 41. Nenhum erro fora dele. Olhar 4,5 casas em
vez de 64 não perdia nada.

**Três decisões.**

- **Local quer dizer local, e por isso este caminho não passa pelo consentimento da S-32.**
  Nada sai da máquina. Ele existe em boa parte para tornar aquele desnecessário.
- **A saída é uma marcação, não uma correção automática.** A segunda leitura erra também: 2
  dos 20 saíram com dois reis brancos e nenhum preto. Quem decide continua sendo quem olha.
- **Só dois dos cinco modelos do pacote.** `existence` e `quad` respondem "há tabuleiro?" e
  "onde estão os cantos?", que o `board_detection` já respondeu antes de chegar ali. A poda
  para `position` + `orientation` (232,8 MiB, −21%) não custou leitura, e o que se perde — a
  guarda de imagem deitada — não faz falta num recorte que já vem alinhado pelo detector.

As duas asperezas do projeto de origem (`requires-python >=3.11` e o `render_config` que
resolve recursos relativo ao diretório corrente) são tratadas no adaptador, e não num clone de
terceiro que o usuário vai atualizar.

**Critério de aceite.** Com o clone ausente, o botão não existe e nada quebra. Com ele, as
casas divergentes aparecem marcadas no tabuleiro. Nenhuma requisição de rede em nenhum dos
dois casos.

**Testes.** `tests/test_second_opinion.py` (a comparação, sem Tk).

---

## S-67 · A aba Galeria: a anotação que o pipeline não tem como saber ✅ implementada (2026-08-09)

**Problema.** Há informação que só quem está com o livro aberto sabe: de quem é a vez quando o
texto não diz, em que lance a posição acontece, os headers de PGN do exercício. O produto não
tinha onde guardá-la — o `labels.csv` é dataset de treino, e uma anotação de exportação não é
uma amostra.

**Solução.** Uma aba que percorre os diagramas do livro, um por vez, sincronizada com a página
exibida, gravando em `data/gallery/<livro>.json`.

**Não é um segundo editor.** A unidade de trabalho aqui é a *anotação*, e por isso o que
aparece no centro é **o recorte original do livro**, não o tabuleiro redesenhado a partir da
FEN: quem digita "lance 24" está lendo a legenda impressa.

**Quatro decisões.**

- **Um arquivo por livro, e não colunas no `labels.csv`.** Os dois falam dos mesmos diagramas
  e têm vidas diferentes. Misturá-los faria uma anotação de exportação criar linha de dataset,
  ou obrigaria a salvar uma amostra só para poder dizer "este é o lance 24" — e a maioria dos
  diagramas de um livro nunca vira amostra de treino.
- **Ausente significa "faça como sempre".** Anotação vazia não é gravada. `side_to_move=None`
  é "use o que a S-17 deduziu"; `"w"` é "eu conferi". A segunda tem de vencer a dedução, senão
  anotar não serviria para nada. `lichess_link` é tri-estado pelo mesmo motivo.
- **A chave é `(page_index, diagram_index)`**, e ela depende da ordem de leitura (S-14). Por
  isso a ordem usada fica gravada no arquivo e `load_annotations` avisa quando não bate —
  trocar `reading_order` renumeraria os diagramas e deslocaria todas as anotações.
- **`FEN` e `SetUp` são os únicos headers reservados**, e o critério é estreito: contradizer o
  diagrama. `Result` não está na lista, porque um problema de mate anunciado tem resultado
  declarável e `"*"` é o padrão de quem não declarou.

**A sincronia anda nos dois sentidos sem que nenhum arraste o outro:** página sem diagrama não
move a galeria.

**Critério de aceite.** A anotação sobrevive a fechar o programa; a exportação a lê; navegar
até o fim da lista, trocar de diagrama com o campo pela metade e "aplicar a todos" fazem o que
dizem.

**Testes.** `tests/test_gallery.py` (o arquivo e a URL), `tests/test_gallery_model.py` (a
regra, sem Tk), `tests/test_gallery_panel.py` (a aba).

---

## S-68 · Os diagramas da página viram alvo de clique ✅ implementada (2026-08-12)

**Problema.** O visualizador mostrava a página e nada mais. Descobrir onde estavam os
diagramas exigia rodar o OCR da página inteira, e escolher *um* deles exigia arrastar o mouse
em volta dele à mão. Só que quem sabe onde eles estão é o detector da S-12, e **ele já
rodava** — o resultado ia direto para o reconhecimento e nunca chegava à tela.

**Solução.** `ui/page_overlay.py`: a parte disso que se verifica sem abrir janela — ponto do
PDF → pixel de canvas, qual retângulo um clique acertou, o que aquele clique significa, e de
qual fonte as caixas vêm. Desenho e eventos ficam no `ui/pdf_panel.py`.

**As decisões que o módulo registra.**

- **A menor caixa vence o clique.** O empate acontece de verdade: o caminho por contorno às
  vezes acha a moldura do exercício *e* o tabuleiro dentro dela. Devolver a maior faria o
  clique no tabuleiro abrir a moldura — que é o candidato que o modelo lê pior.
- **Clicar num diagrama não lido reconhece a página inteira**, não só ele. Ler o recorte
  isolado sairia da página rasterizada em vez da imagem embutida — 590×590 nativos contra ~430
  px a 220 DPI no Kemeri (S-12) — e sem o contexto de texto que decide o lado a jogar
  (S-16/S-17). Seria um diagrama lido pior que pelo botão "OCR todos diagramas", sem que nada
  na tela dissesse por quê. Paga-se a página uma vez; dali em diante todo clique nela é
  instantâneo.
- **"OCR melhor diagrama" não apaga as outras caixas.** Ele lê um, e o detector achou seis.
  Ficam as seis, nenhuma marcada como lida: com `max_boards=1` o caminho por contorno devolve
  o candidato de maior *score*, e não o primeiro em ordem de leitura, então prometer que a
  caixa restante é a de número 1 seria falso.
- **A caixa viaja em pontos do PDF, e o DPI vem dos parâmetros da rasterização**, não do
  spinbox. Ler o spinbox na hora de desenhar produziria retângulos deslocados no intervalo
  entre mudar o DPI e a página ser rasterizada de novo — e retângulo deslocado é pior que
  nenhum, porque afirma que o diagrama está onde não está.
- **O índice sai do detector, não é renumerado.** O "3" do retângulo tem de abrir o diagrama 3
  do editor; renumerar aqui recriaria, entre a tela e ela mesma, o desencontro que a S-14
  corrigiu entre a tela e o PGN.

**Critério de aceite.** Numa página com diagramas, os retângulos aparecem antes de qualquer
OCR, e o número deles bate com o do seletor "Selecionado" depois do OCR.

**Testes.** `tests/test_page_overlay.py` (conversão, *hit test*, decisão do clique),
`tests/test_pdf_panel.py` (o desenho e os eventos).

---

## S-69 · A aba "Leitura" (WebView2) sai ✅ implementada (2026-08-12)

**Problema.** A aba embutia o visualizador do Edge por `SetParent`, e foi a S-68 que a
condenou: um HWND nativo filho pinta acima de qualquer item do canvas, o leitor interno do
Edge não aceita JS injetado e não informa em que página está. Naquela aba não havia como
desenhar os retângulos, capturar o clique nem saber o que o usuário estava vendo — a sincronia
entre as duas abas era, **por construção**, de mão única e cega.

**Solução.** Sai `webview2_panel.py`, e com ele `pythonnet` e `pywebview`. Não sobra
dependência de plataforma nenhuma no projeto. Para ler o livro com rolagem contínua e busca de
texto, o botão **Abrir no leitor do sistema** entrega o PDF ao leitor padrão da máquina.

**O que isto custou, e onde foi devolvido.** A rolagem contínua e o zoom do leitor do Edge
eram reais, e sumiram. A S-70 os devolve no canvas do projeto, que é onde os retângulos
existem.

**Critério de aceite.** Nenhum `import` condicional de plataforma no projeto, e o README
dizendo o que aconteceu com a aba, na tabela de resolução de problemas.

**Testes.** Os que existiam para o painel saíram junto. A CI continua em `windows-latest`,
mas agora por um motivo diferente e escrito no arquivo: é a máquina de desenvolvimento e os
testes de Tk precisam de *display* — não mais o WebView2. E `packaging/cvoff.spec` deixou de
carregar a ressalva do runtime do Edge: o bundle parou de depender de algo do sistema.

---

## S-70 · A leitura de volta no visualizador: roda, arrasto e zoom ancorado ✅ implementada (2026-08-12)

**Problema.** A S-69 deixou um canvas com duas barras de rolagem: suficiente para recortar e
reconhecer, pouco para **ler**.

**Solução.** `ui/viewport.py`, sem Tk, com as três decisões que só se percebem errando ao usar:

- **A roda rola o que está sob o ponteiro**, com o foco onde estiver — `bind_all`, e não um
  bind no canvas, porque no Windows o `<MouseWheel>` vai para o widget com **foco**: ligada só
  no canvas, ela não rolaria nada enquanto o cursor de texto estivesse no campo de FEN.
- **Na borda, a roda vira a página**, que entra pelo topo descendo e pelo rodapé subindo, com
  carência de 350 ms. Não é *anti-bounce* teórico: uma roda inercial entrega uma rajada de
  eventos por giro, e sem carência um giro pularia quatro páginas. A caixa "Roda vira a
  página" desliga, e o estado lembra.
- **`Ctrl+roda` amplia ancorado no ponteiro, com passo multiplicativo.** Aditivo de 0,1 dá
  salto de 33% em 0,3 e de 5% em 1,9 — a mesma tecla com efeitos diferentes. E zoom sem âncora
  joga fora o lugar que a pessoa estava olhando, que é justamente o que ela quer aumentar.
- **Arrastar com o botão esquerdo desloca a página**, convivendo com o clique no diagrama pela
  mesma folga de 4 px que já separava clique de arrasto (S-68); com o botão do meio, funciona
  até durante a seleção de área. Mais "Ajustar à largura" (`Ctrl+0`), `PageUp`/`PageDown` e
  `Shift+roda` na horizontal.

**O defeito que só a janela real mostrou.** A primeira versão perguntava ao `winfo_containing`
se o ponteiro estava sobre a página. No Windows ele resolve pelo `WindowFromPoint` do sistema,
então devolve `None` sempre que *outra* janela cobre aquele ponto: medido com a janela do app
atrás do terminal, `winfo_containing(951, 346)` deu `None` num canvas de 909×740 posicionado
exatamente ali — e a roda simplesmente não fazia nada, sem erro nenhum na tela. Um tooltip
aberto por cima daria a mesma falha em uso normal. Agora é aritmética com as coordenadas do
próprio widget, que não depende de empilhamento, com teste de regressão.

**Critério de aceite.** Ler um livro do começo ao fim sem tocar na barra de rolagem; o zoom
mantendo sob o ponteiro o que estava sob o ponteiro; a roda funcionando com o foco num campo
de texto.

**Testes.** `tests/test_viewport.py` (as três decisões, sem Tk), `tests/test_pdf_panel.py`
(os eventos, inclusive o gerado sobre outro widget).

---

## S-71 · O número do lance ao lado da vez, e o verde de "já salvo" ✅ implementada (2026-08-12)

**Problema.** Duas coisas que a mesma leitura da legenda resolve, e que estavam em lugares
diferentes: o lado a jogar ficava na aba Resultado e o número do lance só na Galeria. E, ao
reabrir um livro trabalhado semana passada, nada na tela respondia **"onde eu parei?"**.

**Solução, parte 1 — o campo Lance.** Fica ao lado do "Lado a jogar" porque é a mesma leitura:
os dois saem da legenda impressa, e quem está com o livro aberto declara os dois de uma vez.

- **Grava na mesma anotação que a Galeria edita** e que a exportação lê. Duas cópias em memória
  do `data/gallery/<livro>.json` divergiriam, e a última a gravar apagaria o que a outra
  tivesse escrito; por isso o dono continua sendo a Galeria, e a aba Resultado pergunta a ela.
- **Em branco apaga a declaração**, pela regra que já valia na Galeria: não declarar e declarar
  vazio são coisas diferentes, e só a primeira deixa a exportação decidir.
- **O campo fica cinza quando o que está no editor não é o diagrama de uma página** — item da
  fila, amostra do dataset, recorte de área —, porque ali gravar apontaria para o diagrama
  errado.

**Solução, parte 2 — o verde.** A cor da caixa passa a dizer em que ponto do trabalho o
diagrama está: **azul** localizado, **âmbar** lido e não salvo, **verde** com amostra no
`labels.csv`. Quem responde é a procedência gravada no CSV (`source_pdf`/`source_page`/
`source_diagram`, da S-19), e não a memória — então o verde aparece ao abrir um livro já
trabalhado, **antes de qualquer OCR**, e responde "onde eu parei?" sem custar uma leitura.

**O carimbo é aplicado na hora de desenhar, e não no cache de detecção.** Salvar precisa
pintar de verde o diagrama que acabou de ser salvo, e não na próxima visita àquela página.

**Dois defeitos que isto encontrou.**

- A Galeria só conhecia o livro **depois de uma varredura**: sem varrer, `pdf_path` era `None`
  e `save()` descartava em silêncio — o número digitado sumiria. Agora o livro é carregado ao
  abrir o PDF, sem pedir a página do primeiro diagrama, que jogaria fora a página que a S-25
  acabou de restaurar.
- O caminho de **gravar amostra nova** não avisava ninguém; só o de regravar linha avisava. A
  aba Dataset não via a amostra recém-salva.

**A seleção deixou de ser uma cor.** Ela era laranja, o que apagava justamente o estado do
diagrama que se acabou de abrir. Virou traço grosso. A primeira versão a preenchia com hachura
`gray12`, e os pontinhos caíam sobre as casas que se está tentando conferir — que é para o que
a caixa existe; não há hachura mais rala entre as do Tk, então o preenchimento saiu inteiro, e
a seleção passou a ser borda de 4 px mais uma segunda borda **por fora** da caixa. Por fora
porque a caixa encosta no diagrama: uma borda interna cairia sobre a primeira fila de casas e
trocaria um estorvo por outro.

**Critério de aceite.** Azul antes do OCR, âmbar depois, verde ao salvar — e o verde
sobrevivendo a virar a página e voltar. Conferido de ponta a ponta no app com `labels.csv` e
galeria temporários.

**Testes.** `tests/test_labels.py` (a consulta de procedência), `tests/test_page_overlay.py`
(o carimbo), `tests/test_result_panel.py` (o campo e o estado cinza — o primeiro teste de
widget daquela aba), `tests/test_pdf_panel.py` (a seleção que não pinta sobre o tabuleiro).

---

# Fase 13 — A base de partidas, e a primeira verdade que não vem de gente

## S-72 · A base de partidas como terceira fonte de verdade ✅ implementada e medida (2026-08-13)

**Problema.** A legenda diz `Coull - Stanciu` e mais nada. O número do lance e a vez a jogar —
os dois campos que a Galeria pede — a pessoa preenche **contando à mão no livro**, e em 24 dos
27 livros do acervo a vez a jogar continua sendo o palpite que a Fase 3 registrou como palpite.

Medido no `Secrets of Chess Training` (1.408 diagramas), o que a camada de texto entrega
sozinha:

| | |
|---|---|
| diagramas com legenda | 1.362 — 96,7% |
| dos quais rendem os **jogadores** | 178 — 12,6% |
| rendem o **evento** | 15 — 1,1% |
| rendem o **ano** | 16 — 1,1% |

O texto dá o nome e cala sobre o resto. É esse buraco que a base preenche.

**Solução.** `games_db.py`: uma passada pela base colhendo as partidas dos pares que as
legendas nomeiam, e o cruzamento com as posições lidas. Um botão **Buscar na base** na Galeria.

**O que isto é, e que nada aqui era antes.** Toda verdade do projeto vem de humano — o
`labels.csv` é trabalho humano, o lado a jogar da S-16 é texto que um humano escreveu no livro,
a fila da S-22 ordena para um humano olhar. Um casamento contra a base é o primeiro **oráculo
externo**: 64 casas contra 64 casas de um lance de uma partida registrada. Não é opinião, e não
é confiança do modelo.

**Três decisões, e as duas primeiras são economia medida.**

- **Casar pela colocação de peças, nunca pela FEN inteira.** Roque e *en passant* são inferidos
  (S-17), o contador de lances é o que se quer descobrir, e a vez costuma ser palpite. Comparar
  a FEN completa faria todo casamento falhar por campos que o projeto **sabe** que não conhece.
- **Uma passada por livro, não por diagrama.** Ler a base custa ~150 s; os pares vão todos
  juntos. Perguntar por diagrama custaria os mesmos 150 s cada — a economia da S-61.
- **Sem índice no disco.** ~1 GB de índice por nome para poupar 150 s por livro não se paga
  enquanto a busca for por livro. No dia em que ela virar por diagrama, passa a valer.

**Preenche só o que está vazio, e nunca sobrescreve** — a regra que a S-17 estabeleceu para o
lado a jogar. Se a pessoa digitou `Event` e a base discorda, quem está com o livro na mão é
ela. E **posição que casa com mais de cinco partidas não preenche nada**: um final de rei e
peão aparece em centenas, com número de lance diferente em cada uma, e procedência inventada é
pior que campo vazio — o campo vazio ninguém confunde com dado conferido.

`DiagramAnnotation.filled_from` guarda a **evidência**, não só a origem — `"Ljubojevic x
Browne, IBM 1972"` em vez de `"base"` —, pelo desenho do `side_to_move_evidence` da S-16: quem
discorda precisa saber de quê está discordando.

**Resultado medido.** 167 pares distintos, **84 achados** na base, 91 diagramas cobertos,
**61 casamentos exatos** — 67% dos cobertos. Zero ambíguos.

**A hipótese que morreu.** A proposta original previa usar a base para **reparar** leitura
errada: se a posição lida estivesse a 1 ou 2 casas de um lance da partida, a base apontaria o
erro do OCR. **Zero em 91.** O casamento é binário. Neste livro quase todo diagrama sai com
confiança 1,000, então não havia erro a reparar — a hipótese não foi refutada, ficou sem chance
de aparecer. E há um problema estrutural atrás disso: os livros onde o OCR erra são os de scan
puro, que não têm legenda com nomes. Fica registrada como **não medida**, não como descartada.

**Critério de aceite.** Sem base no disco, o botão explica onde pôr uma e nada quebra. Com
ela, o que a pessoa digitou sobrevive à busca. Conferido de ponta a ponta contra a base real.

**Testes.** `tests/test_games_db.py` (sobrenome, colheita, casamento, teto por par — com um
PGN de três partidas escrito na hora, sem a base de 9,7 GB), `tests/test_gallery_model.py` (o
preenchimento e o que ele recusa), `tests/test_gallery_panel.py` (a aba, com a base remendada
para o teste não depender de ela existir na máquina).

---

## S-73 · A busca por posição, que alcança o diagrama sem legenda ✅ implementada e medida (2026-08-13)

**Problema.** A S-72 chega a 12,6% dos diagramas. Os outros 87,4% têm posição lida e nenhum
nome — e a posição, sozinha, é informação suficiente: ou aquelas 64 casas aparecem numa partida
registrada, ou não.

**Solução.** `cvoff-games --positions`: reproduz os lances das partidas da base e confere cada
posição contra o conjunto-alvo.

**A busca é invertida, e é o que a torna viável.** O caminho óbvio — indexar as ~800 milhões de
posições da base — custaria dezenas de GB no disco e horas de construção. Aqui quem vai para a
memória são as **nossas** posições, que são milhares, e a base passa uma vez.

| | |
|---|---|
| custo | **104 min** em dez processos (10.547.416 partidas) |
| num processo só | 7,5 h (392 partidas/s, 24,6 mil lances/s) |
| posições distintas do livro que casaram | **761 de 1.404 — 54,2%** |
| com **uma única** partida | 487 |
| diagramas preenchíveis pela regra dos ≤5 | **581** de 1.408 |
| o caminho por nome, no mesmo livro | 61 |

**O custo é por varredura, não por livro.** O conjunto-alvo cabe na memória sejam 1.400
posições ou 40 mil: `--all` varre os 32 livros pelo preço de um. Rodar `--book` cinco vezes
paga cinco vezes por uma resposta que sai de uma.

**Comando de linha, e não botão.** 104 minutos atrás de um botão é uma janela travada que
ninguém entende — e o paralelismo com `spawn` exige um `__main__` guardado, que um CLI tem e um
callback de widget não garante.

**O cruzamento que vale mais que teste.** Nos 61 diagramas que os dois caminhos alcançam:
**61/61 no número do lance e 61/61 na partida.** Duas rotas sem código em comum chegando ao
mesmo lugar.

**Dois defeitos que só a execução de verdade mostrou.**

1. **`tell()` em modo texto não é byte, é um *cookie* opaco** com o estado do decodificador.
   Comparado contra o fim do pedaço, encerrava o laço cedo: **5 partidas lidas de 2.000**, sem
   erro nenhum na tela. Em binário o `tell()` é o byte, que é o que os limites do pedaço
   significam. O teste de regressão usa 300 partidas — com três, o cookie ainda é pequeno.
2. **`spawn` reimporta o `__main__` do pai** (S-26). Chamado de um script sem guarda, cada
   filho reexecutava o script e criava mais filhos; travou a máquina uma vez aqui. Agora um
   marcador vai no ambiente **antes** de o `Pool` existir, e o filho que reimportar responde
   com um processo só — fica lento num uso que já estava errado, em vez de derrubar tudo.

**O que não foi medido, e é a ressalva honesta.** O livro medido é do Dvoretsky, feito de
partidas reais: é o melhor caso possível. Um livro de estudos compostos ou de problemas vai
casar muito menos, e o 54,2% **não** deve ser lido como taxa do acervo. Medir um segundo livro
de outro gênero custa uma varredura de Galeria e entra na mesma passada.

**Critério de aceite.** Dividir a base em N processos não muda a resposta (conferido: 2.000
partidas, contagem idêntica em 1 e em 4 processos); `--apply` não sobrescreve nada; sem
`--apply`, nada é gravado.

**Testes.** `tests/test_games_db.py` — a varredura por posição, o corte em pedaços, a
equivalência entre um e vários processos, a guarda contra a recursão do `spawn`, e o comando.

---

## S-74 · O diagrama que a base confirmou sai da fila de revisão ✅ implementada (2026-08-13)

**Problema.** A fila da S-22 ordena por **estimativa de erro**: confiança mínima, entropia,
casa reescrita pela decodificação restrita, classe rara. São todas aproximações do que não se
sabe. Quando as 64 casas batem com um lance de uma partida registrada, não há o que estimar —
existe a resposta, e a fila continua perguntando.

O número que dá a medida: no `1937 Kemeri` a fila pega **30 dos 47 diagramas**, e a própria
Fase 4 registrou que ali o ganho dela é a ordem, não o corte. O corte é isto.

**Solução.** `priority_for(..., confirmed_by_database=...)`, alimentado pelas anotações do
livro. Confirmado, o diagrama não vira item.

**Confirmar e preencher passaram a ser coisas diferentes, e por isso são dois campos.** Uma
posição que aparece em 300 partidas não diz *qual* partida é, então não preenche header nenhum
(S-72) — mas responde a pergunta da fila, porque aquelas 64 casas aconteceram num tabuleiro de
verdade. `DiagramAnnotation.confirmed_from` guarda a partida quando ela é única e a contagem
quando não é, e **conta como anotação não-vazia**: descartá-la por parecer vazia faria a fila
reencher a cada varredura.

**A confirmação cala tudo que é sobre a leitura, e nada do que é sobre a vez a jogar.** A mesma
colocação aparece com brancas e com pretas a jogar em partidas diferentes — então a
discordância entre texto e legalidade (S-16/S-17) e o xeque invertido continuam valendo, e o
motivo registrado vira "posição confirmada pela base (...); resta a vez a jogar".

**O risco, nomeado.** Uma leitura errada que por acaso componha *outra* posição real. Com 64
casas isso exige coincidência estrutural, e o caso em que ela é plausível — final de poucas
peças que aparece em centenas de partidas — é justamente o que `apply_matches` recusa
preencher.

**A fonte é o arquivo de anotações**, e não um arquivo próprio da fila: quem grava é o
`cvoff-games`, e um segundo lugar para essa verdade morar só teria como divergir do primeiro —
a decisão que a S-34 tomou no `--skip-existing`.

**Critério de aceite.** Um diagrama confirmado não entra na fila; o mesmo diagrama sem
confirmação entra. Rodar a busca duas vezes não muda a fila.

**Testes.** `tests/test_review_queue.py` (a prioridade e o item), `tests/test_gallery_model.py`
(o que confirma sem preencher).

---

## S-75 · A quarta cor: "não precisa" ✅ implementada (2026-08-13)

**Problema.** As três cores da S-71 formam um eixo — azul localizado, âmbar lido, verde salvo:
em que ponto do **seu** trabalho aquele diagrama está. A S-74 criou um estado que não cabe
nesse eixo e vale mais que todos: a base reconheceu a posição, então ele **não precisa de olho
nenhum**. Sem uma marca, essa informação só existia dentro do arquivo de anotações.

**Solução.** `DiagramBox.confirmed` + `mark_confirmed`, e violeta entre o âmbar e o verde.

Como o verde, vem do disco e não da memória — as anotações da galeria —, então aparece ao abrir
um livro casado ontem, **antes de qualquer OCR**. Num livro como o `400 Quebra-cabeças`, que
casou 52,6%, é metade da página respondida sem uma leitura.

**`mark_confirmed` é função separada da `mark_saved`**, e não um parâmetro a mais nela, porque
as duas respondem perguntas independentes: uma diz que você trabalhou aquele diagrama, a outra
que ele não precisa ser trabalhado. Um diagrama pode ter as duas marcas, uma só, ou nenhuma —
e juntá-las numa chamada faria parecer que uma implica a outra.

**Precedência: salvo > confirmado > lido > localizado.** Salvo vem antes porque é trabalho seu
já feito: ao olhar a página, o que interessa saber daquele diagrama é que ele já rendeu amostra.

**Critério de aceite.** Abrir um livro já casado e ver o violeta antes de rodar qualquer coisa;
a linha de status contando quantos são.

**Testes.** `tests/test_page_overlay.py` (o carimbo e a convivência com o verde).

---

# Depois da Fase 13 — os dois itens que vieram do uso (2026-08-14)

> Registrados em 2026-08-17 pela **S-133**, e o atraso é o item. Os dois foram entregues em
> 2026-08-14, entre o fechamento da Fase 13 e a abertura da 14, e caíram na fenda entre este
> arquivo (que parava em S-75) e o `ANALISE_DETECCAO.md` (que começa em S-78). Ficaram três
> dias em produção sem critério de aceite escrito em lugar nenhum, citados de passagem quatro
> vezes no `PLANO_BASE_PARTIDAS.md` e especificados em nenhum.
>
> O conteúdo abaixo é transcrição das mensagens de commit (`dd33644` e `11235da`), que são
> longas e boas — não é arqueologia. O que **não** é transcrição está marcado como tal: são as
> duas notas de "o que aconteceu depois", que só existem porque hoje se sabe mais.
>
> A causa mecânica da fenda — o `CONTRIBUTING` apontando para o `ROADMAP.md`, que fecha na
> Fase 6, e a ausência de índice — é a **S-134**, e é ela que impede a repetição.

## S-76 · "Aplicar a todos" espalhou quatro campos por 1.405 diagramas ✅ implementada (2026-08-14)

**Problema.** Relato de uso, e o defeito é do **desenho do botão**: *"Aplicar a todos"* foi lido
como *"salvar os headers deste diagrama"*. A leitura é razoável — os campos não têm botão de
salvar próprio (eles gravam ao sair do campo), então o único botão ali parecia ser o de gravar.

O clique copiou `Ljubojevic / Browne / Amsterdam / 1972` para **1.405 dos 1.408** diagramas do
`Secrets of Chess Training`, sobrescrevendo o que houvesse.

**Solução.** Três mudanças, e a primeira é a que importa:

- **Pergunta antes, nomeando os valores e contando os diagramas.** A ação sobrescreve o mesmo
  campo em centenas de anotações e o valor anterior deixa de existir — uma confirmação que não
  diz o que vai acontecer é obstáculo, não proteção. O padrão do diálogo é **Cancelar**.
- **O rótulo diz a direção**: "Copiar headers para todos". O tooltip diz, em letra, que os
  campos já se salvam sozinhos e que este botão não é para salvar.
- **Desfazer** (`gallery_model.revert_headers`), que apaga **pelo valor e não pela chave**:
  apagar todo `Event` do livro levaria junto o que a base preencheu certo em cada diagrama e o
  que foi digitado um a um. Ele **não** recupera o que a cópia sobrescreveu — e por isso a
  pergunta vale mais que ele, o que está escrito no tooltip e no docstring.

O desfazer é **da sessão**. Depois de fechar a janela ele some, e isso é honesto: o que ele
promete é reverter *aquele gesto*, não manter histórico do arquivo.

**Critério de aceite.** O botão pergunta antes, nomeando os valores e a contagem; o padrão do
diálogo é Cancelar; desfazer apaga só onde o valor bate.

**O que foi medido — e o conserto do dado já gravado.** Feito à parte, com backup datado: 1.405
diagramas limpos pelo `revert_headers`, e a reaplicação dos casamentos preencheu os nomes certos
de cada um — Dolmatov × Beliavsky, Taimanov × Fischer, Bareev × Kasparov. O livro saiu de 1.501
anotações para **867**: as outras 634 só existiam por causa da cópia.

**Testes.** `tests/test_gallery_model.py` e `tests/test_gallery_panel.py` (10 novos).

**Nota posterior, que não é transcrição.** A regra que faltava aqui virou desenho no
`PLANO_BASE_PARTIDAS.md` §S-88: o preenchimento automático só toca diagramas **sem** o campo,
nunca os que já o têm. É "o aplicar a todos da S-76 com a trava que faltou", e está dito lá com
essas palavras.

---

## S-77 · Anotar o conjunto de campo na própria página ✅ implementada (2026-08-14)

**Problema.** **As Fases 7 e 11 estavam com o código completo e o critério de saída aberto, e
travavam no mesmo lugar.** A 7.7 mediu por quê: com 38 diagramas, a distribuição de confiança é
bimodal e a vizinhança do gate está **vazia** — 27 acima de 0,99, **nada entre 0,60 e 0,80**, 8
abaixo de 0,43. Nesse conjunto nenhuma mudança de modelo pode ganhar um diagrama, e perder um
basta para derrubar um dos 27. Seis variantes deram 27 ou 28 de 38, sempre.

Quatro itens de spec foram julgados por essa métrica sem resolução: **S-38b, S-40, S-62a e
S-62b**. A Fase 11 registra isso na própria conclusão — *"quando reabrir: a (a), quando o
conjunto de campo crescer"*.

Crescer o conjunto era **editar JSONL à mão**, e por isso ele parou em 15 páginas das 60
planejadas. Mas o visualizador já desenha onde estão os diagramas (S-68) e a precisão do
detector é 0,9722: **na maioria das páginas, anotar é confirmar.**

**Solução.** `ui/field_draft.py`, e os gestos na própria página:

- **Anotar página** grava as caixas da tela como verdade de referência, revisada.
- **Sem diagrama** é o caminho mais rápido, e essas páginas são obrigatórias: são as únicas que
  medem **falso positivo** (S-41).
- **Tirar o selecionado** remove o falso positivo; anotar de novo **substitui** a linha em vez
  de acrescentar — duas linhas do mesmo par fariam `evaluate_field` contar a página duas vezes,
  com pesos diferentes.
- Ao virar a página, a barra diz se ela já está anotada.

`reviewed=True` só aparece em `FieldDraft.to_page`, e é o ponto do módulo: **quem confirma é
gente.** O rascunho da S-41 grava `False` porque é a saída do modelo, e medir o modelo contra a
própria saída dá 1,000 em tudo.

**O que ele não faz, e não pode fazer**, está escrito no docstring: decidir **quantos**
diagramas a página tem. Essa é a única informação do projeto que não existe senão no olho de
quem abre o livro.

**Critério de aceite.** Anotar uma página com N caixas grava **uma** linha com N diagramas;
anotar de novo substitui; "sem diagrama" grava a página vazia; a barra diz o estado ao virar.

**O que foi medido.** Conferido dirigindo a janela de verdade, na página 80 do `Karpov 1`: 6
caixas detectadas, anotadas com regime; tirar uma deixa 5; anotar de novo continua **uma**
linha; e a página 3 entra como `sem-diagrama`.

O roteiro precisou de `mainloop` e não de laço de `update()` — a detecção volta por
`root.after`, que sem o laço morre em *"main thread is not in main loop"*, e o erro parece do
código quando é do roteiro (a armadilha que o `CONTRIBUTING` nomeia).

**Testes.** `tests/test_field_draft.py` (14 novos).

**Nota posterior, que não é transcrição, e é a razão de esta seção não ser só história.** Este
item torna o gesto humano barato — e por três meses ele gravou a coisa errada. A anotação era
montada a partir de `item.placement`, que é **o que o modelo leu**; a correção humana morava em
`fen_edits`, uma lista paralela. Corrigir o tabuleiro e clicar "Anotar página" gravava a leitura
do modelo como verdade de referência. Quem for crescer o conjunto de campo precisa ler a
**S-95**, que é onde isso foi consertado, e não só esta seção.

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
| S-64 recorte com rodapé | S-12 | S-41 |
| S-65 paleta de edição | S-50, S-53 | — |
| S-66 segunda opinião local | S-32 (o `Protocol`), S-12 | — |
| S-67 Galeria | S-14 (a chave depende da ordem), S-18 | S-71 |
| S-68 diagramas clicáveis | S-12, S-14, S-41 (a caixa em pontos) | S-69, S-70, S-71 |
| S-69 saída do WebView2 | S-68 (é quem a condenou) | S-70, S-55 |
| S-70 roda, arrasto e zoom | S-69 | — |
| S-71 lance e "já salvo" | S-67 (dona da anotação), S-19 (a procedência), S-51 | — |
| S-72 base por nome | S-16 (o `parse_context`), S-67, S-17 (a regra de não sobrescrever) | S-73 |
| S-73 base por posição | S-72, S-26 (a armadilha do `spawn`), S-61 (a economia da passada) | S-13, S-17 (dão vez a jogar com procedência), S-74 |
| S-74 confirmação na fila | S-73, S-22 | S-75 |
| S-75 a quarta cor | S-74, S-71 (o eixo de cores), S-68 | — |
| S-76 copiar headers | S-67 (dona da anotação), S-72 (é o que preenche certo na reaplicação) | S-88 (a trava que faltou) |
| S-77 anotar na página | S-41 (o formato do conjunto), S-68 (as caixas na tela) | S-95 (corrige de onde vem a verdade), S-99 |
