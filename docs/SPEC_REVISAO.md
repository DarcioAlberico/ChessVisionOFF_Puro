# Especificação da revisão geral — Fases 52 a 65 (S-296 em diante)

Base: [ROADMAP_REVISAO.md](ROADMAP_REVISAO.md), que traz o método da revisão, o placar dos 181
achados e o porquê da ordem das fases.

Esta spec não introduz recurso novo. Cada item é um defeito, um atrito ou um custo **medido no
código que já existe**, e a fundação continua sendo a das fases anteriores: a interface é a das
Fases 20 a 24 ([SPEC_UI.md](SPEC_UI.md)) e 32 a 35 ([SPEC_APARENCIA.md](SPEC_APARENCIA.md)); o
documento rico é o da Fase 36 ([SPEC_EDITOR.md](SPEC_EDITOR.md)); o estudo é o das Fases 43 a 50
([SPEC_ESTUDO.md](SPEC_ESTUDO.md)); o texto é o das Fases 25 a 31 ([SPEC_TEXTO.md](SPEC_TEXTO.md)).

> **Onde mora a spec de cada item (S-NN).**
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
> | S-296 a S-323, S-325 a S-327, S-368 a S-385 | [SPEC_REVISAO.md](SPEC_REVISAO.md) |

Cada item tem **Problema** (com arquivo:linha do estado atual), **Solução**, **Critério de aceite**
e **Testes**. Nome de módulo é sugestão; o que importa é a fronteira de responsabilidade.

**Cinco regras valem para toda esta spec.**

1. **Nenhum item muda o que o programa faz de certo.** Isto é uma revisão, e a régua de sucesso é
   que a suíte continue verde *e* passe a cobrir o caminho que o item conserta. Item que precisa
   trocar comportamento correto por outro comportamento correto não pertence aqui.
2. **Toda ação que substitui trabalho humano faz uma de três coisas:** pergunta nomeando o que
   será perdido, grava um backup recuperável, ou entra numa pilha de desfazer. Nunca zero das
   três. É a regra que organiza a Fase 53 inteira.
3. **Botão "Cancelar" que não cancela é defeito, e não acabamento.** Ou o `Event` é conferido
   dentro do laço, ou o botão não existe.
4. **Nenhum `# type: ignore` e nenhum `# noqa` sem o motivo escrito na mesma linha.** Ferramenta
   silenciada sem justificativa é a Fase 52 recomeçando.
5. **Número publicado em documento é conferido contra o disco, ou não é publicado.** Quem não tem
   como conferir escreve a data da medição ao lado. É a S-135 aplicada ao que a Fase 64 encontrou.

---

# Fase 52 — O portão que nunca foi aberto

A fase que vem antes de todas: enquanto a CI não roda no ramo onde o trabalho acontece, nenhuma
das outras treze fases é verificada por ninguém.

## S-296 · A CI roda no ramo em que se trabalha

**Problema.** `.github/workflows/ci.yml` disparava em `main`:

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
```

O trabalho deste projeto acontece em ramos de fase (`fase-5-modelo-desempenho`) e em ramos
`claude/*`; a integração em `main` é rara. O `push` de um ramo de trabalho não casava com o
filtro, e o `pull_request` só contava quando o **alvo** era `main`. Resultado medido em
2026-08-27: as Fases 41 a 51 e a sala de estudo inteira — onze fases, oito commits — entraram
sem que nenhuma das três verificações rodasse uma única vez, e havia **4 erros de `ruff` e 30 de
`mypy`** acumulados em silêncio.

Não é uma guarda que reprovou e foi ignorada. É uma guarda que nunca foi convidada, e por isso
este item vem antes do conserto do que ela teria pego.

**Solução.** `push:` sem filtro de ramo. O `pull_request` continua preso a `main` de propósito:
um PR do próprio repositório para `main` dispara os dois eventos e roda duas vezes, e pagar isso
só no PR de integração é mais barato que perder a verificação em todos os ramos de trabalho. O
motivo fica escrito no próprio arquivo, porque quem for apertar o filtro de novo vai ler ali.

**Critério de aceite.** Um `push` para um ramo qualquer dispara o job `check`, e ele roda os três
passos — `ruff check .`, `mypy`, `pytest -v` — com os três extras (`dev`, `onnx`, `ocr`) e
`fetch-depth: 0`.

**Testes.** Não há teste unitário de arquivo de CI que valha a pena: o que prova o item é a
execução. O que **é** testável, e entra na S-299, é a outra guarda que não olhava onde o trabalho
estava.

## S-297 · As quatro linhas que o `ruff` cobrava

**Problema.** Quatro erros, e os quatro estavam no código entregue nas duas últimas fases:

| erro | arquivo | o que era |
|---|---|---|
| `I001` | `cli/editor_inventario.py:17` | bloco de import fora de ordem |
| `F401` | `cli/editor_inventario.py:32` | `comandos` importado e nunca usado |
| `B905` | `text/rico.py:698` | `zip()` sem `strict=` |
| `I001` | `ui/texto_busca.py:26` | `from . import comandos, texto as texto_ui` numa linha só |

**Solução.** Os três primeiros são mecânicos. O `B905` merece uma linha de comentário e não um
`# noqa`: `zip(cortes, cortes[1:])` é um `pairwise`, e a segunda sequência tem por construção um
elemento a menos — `strict=False` é a resposta certa, e escrever *por quê* impede que o próximo
a passar por ali "conserte" para `strict=True` e quebre `_fatiado`.

**Critério de aceite.** `uv run ruff check .` sai com `All checks passed!`.

**Testes.** A própria ferramenta, agora que a S-296 a faz rodar.

## S-298 · Os trinta erros que o `mypy` cobrava, e os que eram falsos

**Problema.** Trinta erros em 8 arquivos. **Nenhum deles era defeito de execução** — e é isso que
torna o item interessante, porque a saída fácil (`# type: ignore` em trinta linhas) teria
apagado a única informação útil que eles carregavam: onde o código diz menos do que sabe.

Três famílias:

- **Seis `Cannot infer type of lambda`** em `ui/texto_panel.py` — o idioma `lambda n=nome:` dentro
  de laço, que existe para capturar o valor e não a variável.
- **Onze `**dict[str, object]`** em `ui/pdf_panel.py:386-387` e duas em `ui/texto_panel.py` — um
  dicionário montado para ir por `**` a uma assinatura de `tkinter` feita de `Literal`.
- **O resto**: `tuple[str, ...]` onde o `tag_configure` aceita `list`, `str` onde a assinatura
  pede `Literal["camada", "glifo"]`, e um `Callable[[], None]` estreito demais para `configure`.

**Solução.** Item a item, e cada um diz uma coisa verdadeira que faltava:

- As `lambda` de laço viram `functools.partial`. O que o `partial` diz e a `lambda` não dizia é
  que o valor é **ligado agora**, e não capturado depois.
- A `lambda` de tecla (`lambda _e, f=funcao: (f(), "break")[1]`) vira `_tecla_que_para(funcao)`,
  uma função nomeada com docstring — e o docstring registra o motivo do `"break"`, que é impedir
  o `tk.Text` de rodar **também** a ligação de classe dele e inserir um caractere de controle
  depois de aplicar o negrito.
- `dict[str, object]` vira `dict[str, Any]` **com o motivo na linha de cima**: `Any` aqui não é
  desistência, é a constatação de que nenhum tipo mais estreito satisfaz um mosaico de `Literal`.
- `JUSTIFICACAO_DO_ALINHAMENTO` passa a ser `dict[str, Literal["left", "right", "center"]]` — que
  é o que ele sempre foi.
- `_fonte_do_trecho` devolve `list[str]` em vez de `tuple[str, ...]`: `list` é uma das formas que
  o `tag_configure` aceita, e a tupla que o Tk aceita de verdade (família, corpo, extras) não é
  exprimível como `tuple[str, ...]` em Python 3.10.
- `theme.ao_repintar` passa a aceitar `Callable[[], object]`. O retorno é ignorado de propósito:
  `Label.configure` devolve um dicionário e `Canvas.configure` não devolve nada, e exigir `None`
  fazia a mesma `lambda` passar num painel e falhar no outro.
- `text/pdf_pesquisavel.py` troca um `# type: ignore[union-attr]` (que já nem cobria o erro certo)
  por três `cast` que declaram, uma vez, o formato dos dicionários aninhados do `get_text("dict")`.

**Critério de aceite.** `uv run mypy` sai com `Success: no issues found in 216 source files`, e o
número de `# type: ignore` no repositório **não aumenta**.

**Testes.** A ferramenta, mais a suíte inteira — as trocas de `lambda` por `partial` e de tupla
por lista atravessam a montagem da aba Texto, que `tests/test_ui_texto_editor.py` exercita.

## S-299 · A guarda de caminho passa a conhecer o checkout principal

**Problema.** A guarda da S-219 (`tests/test_docs.py`, "nenhum relatório publica a raiz do
disco") comparava o caminho publicado contra `RAIZ`, que é a árvore **atual**:

```python
raiz = str(RAIZ).replace("\\", "/").rstrip("/").lower()
...
if valor.replace("\\", "/").lower().startswith(raiz):
```

Num `git worktree` a árvore atual é `.claude/worktrees/algum-nome`, e um relatório que publicasse
`C:/Python-Chess2/ChessVisionOFF_Puro/models/piece_classifier.pt` — o checkout principal, que é
onde os `.pt` e o `PDF/` de fato moram — **não começava pela raiz atual e passava em verde**.

E esse não é o caso exótico: é o procedimento. Remedir campo a partir de um worktree é o que se
faz, justamente porque os artefatos só existem no checkout principal. A guarda existia, rodava, e
não olhava onde o arquivo defeituoso estava — a mesma classe de problema da S-296.

**Solução.** `_raizes_do_repositorio()` pergunta ao git (`git worktree list --porcelain`) por
**todas** as árvores de trabalho e compara contra a lista inteira. Sem git, ou com um git que
recusa, ela devolve `RAIZ` sozinha: a guarda volta a ser o que era, e não deixa de existir.

**Critério de aceite.** Um relatório com caminho absoluto para dentro de qualquer árvore deste
repositório faz `test_nenhum_relatorio_publica_a_raiz_do_disco` falhar, mesmo quando a suíte roda
noutra árvore.

**Testes.** `test_a_guarda_de_caminho_conhece_o_checkout_principal` trava duas coisas: que a raiz
atual está sempre na lista, e que a lista vem normalizada. Ele **não** afirma que há mais de uma
árvore — num clone simples há uma só, e a lista tem um elemento; o que ele impede é a lista
voltar a ser `RAIZ` cravada.

---

# Fase 53 — O trabalho humano que some

Doze caminhos, e o denominador comum é que **nenhum deles pergunta**. A regra 2 desta spec
nasce daqui: toda ação que substitui trabalho humano faz uma de três coisas -- pergunta
nomeando o que será perdido, grava um backup recuperável, ou entra numa pilha de desfazer.
Nunca zero das três.

## S-300 · Lista vazia nunca é razão para podar o `splits.csv`

**Problema.** `splits.ensure_splits` compara a lista recebida com o que está gravado e retira
do arquivo quem saiu:

```python
removed = set(existing) - set(names)
...
if added or removed:
    save_splits(splits_path, result)
```
`splits.py:265-269`

Com `data/labels.csv` inexistente, `LabelStore._load_rows` devolve `[]`, `training.resolve_splits`
chega aqui com `names` vazio, e `removed` vira o arquivo inteiro. Reproduzido com o `.venv` do
projeto: um `splits.csv` de três amostras voltou a ser `filename,split\n`.

O caminho é alcançável de dois lados. `cli/train.py` libera o caso de propósito
(`if args.force or not Path(args.csv).exists(): return None`), e o botão "Treinar modelo" da
janela não tem portão nenhum: o `--csv` sai de um campo de texto. O único registro era um
`logger.info`, e o `ValueError("Dataset vazio")` que avisaria só aparece **depois**, em
`Trainer.prepare`.

O que se perde não é dado -- é a **fronteira** entre treino e teste, que é o que torna
comparável todo número já publicado em `docs/metrics/`. Apagada, a amostra que era `test` volta
a ser sorteada.

**Solução.** `if not names: return dict(existing)`, com um `logger.warning` dizendo quantos
splits foram preservados. Nada mais: podar um *subconjunto* continua sendo o comportamento
desejado e documentado da função. Uma fração mínima de sobrevivência exigiria uma política que
ninguém tem; "a lista veio vazia" é um fato, não uma escolha.

**Critério de aceite.** `ensure_splits([], caminho)` devolve o que estava gravado e não toca no
arquivo. `ensure_splits(["a.png"], caminho)` continua retirando as outras.

**Testes.** `ListaVaziaNaoPodaTests`, em `tests/test_splits.py` -- os dois casos como par: o que
preserva e o que ainda poda. Sem o segundo, a guarda poderia crescer para "nunca podar" sem que
nada acusasse.

## S-301 · "Sem diagrama" pergunta antes de descartar a anotação da página

**Problema.** `annotate_field_page(empty=True)` é o único caminho que monta o rascunho **do
zero** -- todos os outros passam por `_field_draft`, que retoma o que está gravado:

```python
rascunho = FieldDraft(pdf_name=self.pdf_source.name, page=self.page_index) if empty else self._field_draft()
```
`app_tkinter.py:1383`

E `field_eval.upsert_page` "grava uma página anotada, **substituindo** a anterior do mesmo
(livro, página)". Uma folha com diagramas revisados à mão desaparecia num clique, sem
confirmação, sem desfazer, e sem que a frase de status dissesse o que saiu -- ela só anuncia o
novo estado. O botão fica colado em "Anotar página", na mesma linha.

**Solução.** Perguntar, nomeando quantos diagramas serão descartados, no molde de
`dataset_panel.quarantine_selected`.

**A metade difícil do item é a condição, e não a caixa.** A guarda lê o **arquivo** -- o mesmo
dicionário que `_refresh_field_status` já monta --, e não `_field_draft()`. Sem nada gravado,
`_field_draft` cai no ramo de retorno e devolve um rascunho montado a partir das caixas da
*tela*: usá-lo como condição faria a caixa modal abrir em toda página de prosa que o detector
marcou por engano, isto é, no gesto mais repetido de quem monta o conjunto. Página **sem**
diagrama é obrigatória no conjunto de campo (S-41) -- são as únicas que medem falso positivo --,
e pôr uma pergunta no caminho delas é a fricção que a S-164 removeu de `_on_ocr_empty`.

Pelo mesmo motivo o botão **não** ganha `estilos.DESTRUTIVO`: vermelho permanente no gesto
normal ensina a ignorar vermelho.

**Critério de aceite.** Página com diagrama anotado abre a pergunta, e a pergunta diz o número.
Página nunca anotada, e página já marcada como sem diagrama, não perguntam nada.

**Testes.** `tests/test_field_annotation_guard.py`, cinco casos. Os dois que valem são o par:
um diz que a pergunta aparece, o outro que ela **não** aparece no gesto normal. O `messagebox`
é remendado com `mock.patch.object` -- sem isso a caixa abre de verdade e a suíte fica parada.

## S-302 · O comentário digitado e não confirmado sobrevive ao fechamento

**Problema.** O texto da caixa de comentário da sala de estudo só entra no nó quando ela perde
o foco: os onze chamadores de `gravar_comentario` são todos de navegação e de exportação.
`salvar_agora` -- que é o que `app_tkinter._on_close` chama ao fechar a janela, e o que a
inatividade agenda -- saía em `if not self._sujo` sem olhar a caixa.

Reproduzido no painel real: comentário digitado, `salvar_agora()`, e o texto não estava nem no
arquivo nem no nó.

E o programa não só perdia a nota: **ele afirmava que não havia nada a perder.**
`tem_trabalho_por_gravar` -- o `loses_work` do `BusyRegistry` aplicado à sala -- também lê
`_sujo`, então o aviso de fechamento dizia que estava tudo gravado.

**Solução.** `self.gravar_comentario()` como primeira instrução de `salvar_agora`, **antes** do
teste de `_sujo` -- depois dele não adiantaria, porque é `gravar_comentario` quem liga `_sujo`.
Envolvida em `try/except tk.TclError` pelo caso do `after` disparando com o painel já destruído.

**Critério de aceite.** Texto na caixa, `salvar_agora()`, e ele está no nó. Sala limpa e sem
comentário novo continua devolvendo `None` -- a correção não pode fazer toda inatividade
regravar o arquivo.

**Testes.** `ComentarioNaoConfirmadoTests`, em `tests/test_estudo_aba.py`. O segundo caso é o
que explica por que a correção mora em `salvar_agora` e não numa pergunta a mais no fechamento.

## S-303 · A camada invisível do PDF pesquisável entra uma vez, e não duas

**Problema.** `_corpo_que_cabe` tinha nome de sonda e **gravava**: o `insert_textbox` do PyMuPDF
termina em `if rc >= 0: img.commit(overlay)`. Os dois chamadores -- o de `escrever` e o de
`escrever_camada` -- gravavam de novo logo depois, e toda linha entrava **duas vezes** na
camada. Reproduzido: uma folha com `Nf3 exd5` devolvia `Nf3 exd5\nNf3 exd5\n`.

Nada disso aparece na tela, porque `render_mode=3` não pinta pixel -- e é por isso que os dois
testes que existiam continuavam verdes: um confere que a página não muda um pixel, o outro que
a busca *acha* a palavra. Achar duas vezes também é achar. O defeito só aparece para quem copia
o texto, indexa o arquivo, ou conta caracteres.

**Solução.** Assumir o que a função sempre fez: renomeá-la para `_escrever_no_maior_corpo`,
tirar o `overlay=False` (o padrão é o que a escrita real usava) e apagar o segundo
`insert_textbox` nos dois pontos.

**O que não fazer:** medir com `fitz.get_text_length`. Essa régua não reproduz a quebra de linha
do `insert_textbox` e escolheria um corpo que depois não cabe -- e aí o trecho sumiria sem ser
contado, que é pior que a duplicata.

**Critério de aceite.** `folha.get_text().count(trecho.texto) == 1`, e o relatório continua
contando um trecho -- ele já contava certo; era a camada que tinha duas.

**Testes.** `test_cada_trecho_entra_na_camada_uma_vez_so`, em
`tests/test_texto_pdf_pesquisavel.py`. Contar **ocorrências** e não "achou" é a diferença entre
este teste e o da busca, que passava com o defeito.

## S-304 · A folha que não existe não é rasterizada

**Problema.** `prev_page` e `next_page` grampeavam o índice e mandavam rasterizar de qualquer
jeito. Na última folha, cada giro da roda e cada `Page Down` re-rasterizava a **mesma** página
-- medido: cinco giros, cinco `render_pdf_page(2)` --, e como `render_current_page` termina em
`yview_moveto(0)`, a vista voltava ao topo a cada um.

Quem lia o fim de uma folha larga era jogado para o começo dela, repetidamente, sem que nada
mudasse na tela além da rolagem. A 220 DPI, que é o padrão da janela, cada viagem dessas é uma
rasterização inteira jogada fora, e `_on_page_rendered` ainda grava o estado em disco.

**Solução.** Um `_ir_para(alvo)` só, com a mesma forma que `go_to_page` já tinha: grampeia,
compara, e só rasteriza se mudou. A guarda testa `page_rgb` além do índice de propósito -- só o
índice tiraria também o único jeito de tentar de novo depois de um render que falhou.

**Critério de aceite.** Cinco `next_page` na última folha não chamam `render_current_page`
nenhuma vez, e o índice fica onde estava. Virar para uma folha que existe continua
rasterizando.

**Testes.** `LimiteDoLivroTests`, em `tests/test_pdf_panel_navegacao.py`, com o render
instrumentado. O quarto caso é o que impede a guarda de virar "a virada parou de funcionar".

## S-305 · O número digitado no campo de página navega, e o lixo volta atrás

**Problema.** Dois defeitos na mesma linha. O `command` de um `ttk.Spinbox` só dispara nas
setas: digitar `15` e teclar `Enter` mudava `page_index_var` e não mudava a imagem. Medido num
livro de 20 folhas -- `page_index = 15` com `page_loaded_for_index = 0`, a imagem da folha 1 na
tela, e o rodapé passando a dizer "p. 16 de 20". As caixas de diagrama da folha exibida eram
então recusadas por serem "de outra página", e a detecção passava a falar de uma folha que
ninguém estava vendo.

E texto não numérico derrubava a navegação inteira: `page_index` faz `int(page_index_var.get())`
sobre um `IntVar`, e com `abc` no campo as **cinco** funções que o leem levantam `TclError`. Não
há `report_callback_exception` no projeto, então isso ia para o stderr e o botão simplesmente
não fazia nada.

**Solução.** `<Return>`, `<KP_Enter>` e `<FocusOut>` ligados a um `_on_page_typed` que lê o
texto, tolera lixo e navega.

**A comparação é contra `page_loaded_for_index`, e não contra `page_index`** -- e isso é o item.
O `Spinbox` tem o `page_index_var` como `textvariable`: digitar **já mudou** o índice antes de o
tratador rodar, e `go_to_page`, que compara com `page_index`, recusaria toda digitação por "já
estou nessa página". Quem sabe que folha está na tela é `page_loaded_for_index`.

**O lixo repõe o campo em vez de navegar.** Mandar para a folha 1 escolheria um destino que
ninguém pediu; deixar `abc` no widget manteria a dessincronia que o item conserta. O
`<FocusOut>` com o campo vazio -- que acontece a cada limpeza no meio da edição -- cai no mesmo
caminho.

**Critério de aceite.** `15` + `Enter` rasteriza a folha 15. `abc` não levanta, não navega e
repõe o número da folha que está na tela. `999` vai para a última e o campo mostra a última.

**Testes.** `NumeroDigitadoTests`, em `tests/test_pdf_panel_navegacao.py`.

## S-306 · "Tirar o selecionado" usa a seleção do visualizador

**Problema.** O comando lia `ResultPanel.selected_index`, que é `clamped_index()` e vale **0**
com a lista vazia. A guarda `0 <= 0 < len(caixas.boxes)` passava sempre, a frase "Selecione o
diagrama" nunca aparecia, e o comando tirava do `data/field_set.jsonl` o diagrama nº 1 da
página, que ninguém tinha selecionado.

E havia um segundo desencontro por baixo do primeiro: quando as caixas na tela são as do
detector, o índice do editor **não fala da mesma lista** -- é o que `_sync_selected_box` afirma
para recusar até o simples destaque ("um destaque no diagrama errado é a resposta errada").
Aqui o mesmo índice não destacava: ele removia uma linha da verdade de referência que mede o
pipeline inteiro.

**Solução.** `PdfPanel.selected_box`, um `property` sobre o `_selected_box` privado, e o comando
passa a agir sobre ele. `_selected_box` é escrito exclusivamente por `select_box`, cujo único
chamador é `_sync_selected_box` -- que já aplica as três pré-condições e põe `None` fora delas.
Usar a seleção do visualizador dá de graça as guardas que faltavam, casa a frase da interface
("o selecionado" é o retângulo destacado na folha) e faz os dois comandos de tirar concordarem.

Não foi preciso mudar `ResultPanel.selected_index` para `int | None`, que mexeria em todos os
chamadores dele.

**Critério de aceite.** Sem retângulo selecionado, o comando recusa com a **mesma** frase de
`drop_selected_box` -- dois comandos de tirar não devem ensinar dois gestos.

**Testes.** Os de `tests/test_pdf_panel.py` e `tests/test_box_drop.py` continuam valendo; o
comando fica menos permissivo, não mais.

## S-307 · A sala não carrega um PGN de 10 GB para a memória

**Problema.** `abrir_pgn` lia o arquivo inteiro para a memória, na thread do Tk:

```python
texto = caminho.read_text(encoding="utf-8", errors="replace")
```
`ui/study_panel.py:1494`

E `pgn_database/` é a pasta que `estudo_partidas.py` manda usar -- "ponha os seus arquivos .pgn
lá". Neste repositório ela tem `PGN_Database.pgn` com 10,3 GB e `LumbrasGigaBase_OTB_Complete.pgn`
com 8,6 GB.

Medido: 5,2 MB de PGN custam 18,8 s e 220 MB de pico -- **quarenta vezes** o tamanho do arquivo.
Extrapolado, um arquivo de 62 MB dá ~3,5 min de janela congelada e ~2,5 GB de memória. Nos de
gigabytes o `read_text` nem devolve: levanta `MemoryError`, que **não** é `OSError` e por isso
escapava do `except OSError` da linha seguinte e subia para o laço de eventos do Tk. Não havia
teto, thread, barra nem cancelar, e o comando é botão de barra e item de menu.

**Solução.** Duas linhas de defesa, na ordem de custo:

1. **Teto por bytes antes de ler.** `TAMANHO_MAXIMO_DE_PGN = 20 MB`, conferido com
   `caminho.stat().st_size`. A recusa diz o tamanho do arquivo e para onde ir: base de partidas
   desse porte se consulta pela busca por posição da S-73, que **indexa** em vez de carregar.
   Vinte megabytes é o corte entre "coleção de um livro" e "base de partidas".
2. **Leitura por fluxo.** `estudos_de_pgn` já fazia `io.StringIO(texto)` na primeira linha; ela
   passa a aceitar `str | TextIO`, e `abrir_pgn` entrega o arquivo aberto. O `read_game` do
   `python-chess` consome sob demanda -- é o que ele sempre soube fazer.

**O teto de partidas é parâmetro, e não constante.** `PARTIDAS_MAXIMAS_DE_PGN` mora no painel e
viaja como argumento. Esse detalhe é o item: o **mesmo** laço lê o arquivo da sala em
`estudo_arquivo.carregar`, e um limite global truncaria em silêncio a sala de quem tem mais
estudos que o teto -- perda de análise humana, exatamente o oposto do que este item quer.

**Critério de aceite.** Arquivo acima do teto é recusado antes de qualquer leitura, com o
tamanho na frase. Arquivo dentro do teto é lido por fluxo. `carregar` continua lendo a sala
inteira, sem limite.

**Testes.** `LerPgnSemCarregarTudoTests`, em `tests/test_estudo_arquivo.py`. O quinto caso --
"a sala é lida sem teto" -- é o que trava a decisão: um `LIMITE` global dentro de
`estudos_de_pgn` passaria em todos os outros quatro.

## S-308 · O rascunho recuperado continua sendo trabalho por gravar

**Problema.** `oferecer_rascunho` terminava assim:

```python
self.abrir(doc)
# Recuperado é trabalho que chegou a um lugar melhor -- a tela --, e o arquivo sai.
rascunho.descartar(pagina.documento, pagina.pagina, pasta=self._pasta_de_rascunhos)
```
`ui/texto_panel.py:2178-2186`

O comentário está certo sobre a intenção e errado sobre o efeito. `abrir` termina em
`desenhar_documento`, que zera `_sujo` -- o certo para um documento que veio do disco, e o
errado para este, que veio de um arquivo que a linha seguinte apaga.

Com `_sujo` em `False` e o `.cvtxt` fora do disco, o texto resgatado passava a existir **só na
memória**, e três coisas paravam de funcionar de uma vez: `gravar_rascunho` saía em
`if not self._sujo` e não reescrevia nada; e as duas guardas que perguntam antes de descartar --
`ler` e `abrir_documento` -- liam `_sujo` e passavam direto. Reproduzido com Tk real:
`_sujo` `False`, `rascunho ainda no disco? False`, `gravar_rascunho() → None`, e "Ler folha"
descartando sem perguntar.

O recurso existe para o segundo travamento, e era exatamente o segundo travamento que perdia
tudo.

**Solução.** `self._sujo = True` entre `abrir` e `descartar`. Uma linha, e ela devolve as três
coisas de uma vez.

**O que não fazer:** manter o `.cvtxt` no disco. Isso reprova `test_recuperar_apaga`, e por um
bom motivo -- recuperado é trabalho que chegou a um lugar melhor. E não agendar um novo rascunho
aqui: o próximo toque no editor já agenda sozinho, e agendar aqui faria `test_recuperar_apaga`
depender de o teste não bombear o `after`.

**Critério de aceite.** Depois de recuperar, `gravar_rascunho()` devolve um caminho e o arquivo
volta ao disco. "Ler folha" e "Abrir documento" voltam a perguntar.

**Testes.** `test_o_recuperado_continua_sendo_trabalho_por_gravar`, em
`tests/test_texto_rascunho.py`, ao lado de `test_recuperar_apaga` -- os dois juntos dizem a
regra inteira: o arquivo sai, e a marca fica.

## S-309 · O botão "Cancelar" do treino chega ao treino

**Problema.** Uma linha ausente, com três presenças que a faziam parecer existir. `start`
registrava a operação no `BusyRegistry` como `cancellable=True` e passava o `Event`; `ui/rodape.py`
habilitava o botão por causa disso; e o `Trainer` sabe parar entre épocas desde a S-60. Só que
`_worker(self, pedido, cancel)` recebia o `Event` e **não o repassava**:

```
kwargs de train_model: ['batch_size', 'csv_path', 'epochs', 'fresh', 'lr',
                        'model_path', 'progress_cb', 'samples_dir', 'splits_path']
cancel_event passado? False
```

O botão respondia ao clique, o rodapé dizia que estava cancelando, e as oito épocas rodavam até
o fim -- ~9 min cada em CPU.

**Solução.** `cancel_event=cancel` na chamada, e o desfecho cancelado tratado no mesmo item:
`run.cancelled` passa a existir de verdade, e `"Treino concluído"` sobre uma parada na época 2
de 8 seria a interface mentindo sobre o que ela fez. A frase passa a dizer em que época parou, e
que o checkpoint da melhor época continua valendo -- porque continua: cancelar não é falhar.

**Critério de aceite.** `train_model` recebe o mesmo `Event` que o rodapé aciona. Um `run`
cancelado não produz a frase "concluído".

**Testes.** `CancelarDeVerdadeTests`, em `tests/test_training_dialog.py`, com `train_model`
remendado -- foi assim que o defeito foi reproduzido.

## S-310 · A melhor época é a que `is_best` marca

**Problema.** `summarize_run` indexava o histórico **desta** execução com um número que é do
**checkpoint**:

```python
melhor = run.history[run.best_epoch - 1] if run.history and run.best_epoch else {}
```
`ui/training_dialog.py:82`

Os dois coincidem num treino do zero e divergem em toda retomada. Um treino retomado de um
checkpoint com `best_epoch=7` e parado na segunda época chega aqui com `history` de duas linhas:
`history[6]` estoura `IndexError`, o `except` do `_worker` o apanha, e a interface anuncia
**"Falha no treino"** ao fim de um treino que gravou o que devia gravar. Quando não estoura --
histórico maior que `best_epoch` -- é pior: mostra calado a métrica da época errada.

**Este item e a S-309 tinham de vir juntos.** Ligar o cancelamento torna comum exatamente o caso
`len(history) < best_epoch`.

**Solução.** `run_epoch` já carimba `row["is_best"] = improved` em toda linha. A melhor época
desta execução é a última com essa marca; nenhuma marca é um resultado legítimo -- "nenhuma
época superou o checkpoint que já existia" --, e aí o resumo fica vazio de propósito e quem diz
o que aconteceu é a frase de status.

**Critério de aceite.** `best_epoch=7` sobre um histórico de duas linhas não levanta e mostra a
métrica da época marcada. Histórico sem nenhuma marca devolve `""`.

**Testes.** `test_o_best_epoch_do_checkpoint_nao_indexa_o_historico_desta_execucao` e
`test_nenhuma_epoca_melhor_que_o_incumbente_nao_e_falha`. O fixture de `SummaryTests` passou a
carregar `is_best`, que é o que o `run_epoch` real sempre produziu -- ele modelava um histórico
que o código nunca gerou.

## S-311 · Divisor não mapeado não é divisor medido

**Problema.** `_save_app_state` roda **antes** do `mainloop`, pelo caminho `__init__` →
`_restore_state_or_default_pdf` → `_escolher_conjunto`. Nesse instante o `PanedWindow` ainda não
foi mapeado, e medi-lo dá lixo. Medido nesta máquina: `sash_coord(0)` devolve 521 e
`winfo_width()` devolve **1**, e `fracao_de_divisor(521, 1)` sai **0,85** -- o teto do grampo, não
a escolha de ninguém.

O valor da sessão anterior era sobrescrito na memória **e no disco** antes de qualquer pessoa
tocar em nada. É a regressão que a S-156 diz ter consertado: "quem trabalha com o PDF grande
arrastava o divisor toda sessão e o perdia toda sessão".

Corrobora: `data/app_tkinter_state.json` tinha `sash_fraction = 0.5802…` sobre uma geometria de
1300×800 -- o divisor colado no limite que o `minsize` de 520 impõe, e não uma posição escolhida.

E a linha vizinha, a do divisor da sala de estudo, tinha o mesmo defeito com o outro extremo: um
`ttk.PanedWindow` antes do mapeamento devolve `sashpos 0`, que vira 0,15. O `or
self.state.estudo_divisor` não protege contra isso, porque 0,15 é um número verdadeiro.

Note a assimetria que existia no mesmo método: `window_geometry` **estava** protegido --
`geometria_gravavel("1x1+0+0")` devolve `""` e o `or` preserva o guardado. O divisor não tinha
guarda nenhuma.

**Solução.** `winfo_ismapped()` nas duas linhas. `ismapped` e não `winfo_width() > 1` porque a
pergunta é "este widget já existe na tela?", e é ela que decide se a medida vale.

**O que não fazer:** mudar `fracao_de_divisor` para devolver `0.0` com largura ≤ 1. Isso reprova
`tests/test_ui_geometria.py`, que afirma `fracao_de_divisor(0, 0) == FRACAO_PADRAO_DO_DIVISOR` e
`fracao_de_divisor(0, 1700) == 0.15`, e mudaria o contrato para os dois chamadores.

**Critério de aceite.** Abrir e fechar o programa sem tocar no divisor deixa `sash_fraction`
como estava.

## S-312 · A marca da linha impressa vai no ramo do livro

**Problema.** `jogar_a_linha_do_livro` marcava a procedência assim:

```python
primeiro = no_em(self.estudo.jogo, self.estudo.caminho() + (0,))
```
`ui/study_panel.py:1361`

Isto é "o primeiro filho do nó corrente", e só é a linha do livro quando o nó corrente **não
tinha continuação nenhuma**. Quem já jogou um lance a partir do diagrama recebia
`"linha impressa no livro"` no **seu** lance, e a linha do livro entrava ao lado sem procedência.

Reproduzido pelo painel de verdade: com a linha impressa `4.♘g5 d5`, jogando `d2d4` antes, o PGN
saiu

```
{ linha impressa no livro } 4. d4 ( 4. Ng5 d5 ) *
```

atribuindo ao livro exatamente o que a pessoa jogou -- e essa distinção é o motivo de o item
existir (S-283: "o que a pessoa jogou e o que o livro imprimiu não podem ficar
indistinguíveis").

**Solução.** Guardar o primeiro nó **enquanto ele é criado**, com `primeiro = primeiro or no`
dentro do laço. É o mesmo recurso que o próprio arquivo já usa quinze linhas adiante.

**Critério de aceite.** Com um lance já jogado a partir do diagrama, a marca está no ramo da
linha lida e o ramo jogado continua sem `starting_comment`.

**Testes.** `test_a_marca_vai_no_ramo_do_livro_e_nao_no_que_a_pessoa_jogou`, em
`tests/test_estudo_aba.py`. Os quatro testes que já existiam não pegavam nada porque todos
partem de um diagrama sem continuação -- e `assertIn("linha impressa no livro", pgn)` é verdade
nos dois casos. O que decide é **em qual ramo** a frase está.

## S-313 · A pergunta de documento sobre estilo é feita uma vez por livro

**Problema.** `camada.documento_registra` abre uma amostra de páginas e varre os spans delas. É a
pergunta que separa "aqui não tem itálico" de "este livro não registra itálico", e sem ela a
S-237 não distingue `False` de `None`. Só que `ler_pagina` a fazia **duas vezes por folha** --
uma para o peso, outra para o pendor -- e ela não tinha memória nenhuma.

Medido com o `.venv` do projeto, sobre o acervo:

| livro | folhas | primeira folha | folhas seguintes |
|---|---|---|---|
| `A Matter of Endgame Technique` | 898 | 2.606 ms | 0,110 ms |
| `Excelling at chess calculation` | 193 | 2.197 ms | 0,094 ms |

Contra 0,233 s + 0,166 s da leitura dos spans **da folha em si**: a pergunta sobre o livro custava
mais de dez vezes a leitura da página. Onze dos 45 PDFs do acervo passam de 0,5 s por folha só
nestas duas perguntas. Na varredura de texto do Aagaard, são ~39 min que deixam de ser pagos.

**Solução.** Memória por `(marca, arquivo, mtime, amostra)`.

**Três detalhes fazem a chave, e cada um é uma armadilha evitada:**

- **`marca`.** `e_do_estilo` é uma função, e duas funções não têm chave comum. `negrito` e
  `italico` passam a sua; sem `marca` **não há cache**, que é o padrão -- nenhum chamador ganha
  memória sem pedir.
- **Nome vazio desliga a memória.** `PdfSource` aceita `bytes` e um documento já aberto, e nesses
  casos `doc.name` é vazio: um cache chaveado por nome vazio devolveria a resposta de **outro**
  documento, e a resposta muda o significado de toda linha sem itálico da folha.
- **`mtime` na chave.** Um PDF reescrito no lugar é outro livro com o mesmo nome.

**Critério de aceite.** O mesmo livro perguntado vinte vezes abre páginas uma vez só. Dois
documentos em memória sem nome dão respostas independentes.

**Testes.** `tests/test_texto_memoria_do_documento.py`, com um PDF de mentira que **conta**
quantas páginas foram abertas. Os quatro casos cobrem as três armadilhas mais a separação entre
as duas marcas.

---

# Onde a Fase 53 parou, e o que a medição disse

**Catorze itens entregues, S-300 a S-313** -- e os três últimos não são de perda de trabalho:
a S-311 é a posição do divisor, a S-312 é a procedência da linha impressa e a S-313 é custo. Eles
entraram aqui porque a segunda passada os confirmou como alta severidade e esforço pequeno, e
adiar um conserto barato para respeitar a fronteira de uma fase é organizar documento em vez de
consertar programa. As Fases 55, 57 e 58 herdam o que sobra das áreas deles.

Faltam os quatro caminhos que a Fase 53 lista e ainda não têm item escrito: `cvoff-review`
apagando a fila de outro livro, a fila de revisão fechada por índice posicional, "Salvar todos"
abortando em silêncio no meio do laço, e o `abrir_pgn` que carimba o livro aberto sobre o
`SourcePDF` de cada partida.

**A S-300 obrigou a remedir os quatro relatórios de campo, e o resultado é o melhor possível: os
números não mudaram.** `splits.py` está no caminho de medição da S-219, então a guarda de lista
vazia mudou o digest do módulo e `test_todo_relatorio_corrente_mediu_o_codigo_de_hoje` acusou --
que é a guarda funcionando. Remedidos com os mesmos quatro modelos e o mesmo conjunto de 68
páginas, `controle_20260822` devolveu `export_rate` 0,7913, `exact` 89 e `repaired_squares` 39,
idênticos ao arquivado. Isso **prova** o que o raciocínio só sugeria: uma guarda que só dispara
com a lista vazia não toca em nenhum número de campo.

---

# Fase 54 — O que trava, e o que não cancela

A regra 3 desta spec é a fase inteira: **botão "Cancelar" que não cancela é defeito, e não
acabamento.** Ou o `Event` é conferido dentro do laço, ou o botão não existe.

## S-314 · "Detectar duplicatas" aceita um clique de cada vez

**Problema.** `detect_duplicates` não tinha guarda nenhuma. O segundo clique sobrescrevia
`self._busy_token` com uma chave nova, e a do primeiro ficava registrada **para sempre** --
`_release_busy` só solta a que está no atributo.

O dano não aparece na hora. `BusyRegistry.running()` não filtra por `loses_work`, então a chave
vazada entra na pergunta de fechamento: a janela passa a avisar que há uma operação em andamento
que terminou há horas. É exatamente o que essa pergunta existe para não fazer, e uma pergunta que
mente é uma pergunta que se aprende a ignorar.

E o botão não tinha como ficar cinza: era criado inline (`ttk.Button(toolbar, ...).pack(...)`) e
não guardado em atributo nenhum.

**Solução.** O botão vira atributo e fica cinza enquanto a detecção roda, mais uma saída cedo com
frase de rodapé.

**Botão cinza e não bandeira.** Uma bandeira sozinha deixa o botão vivo e joga a resposta numa
frase que se perde; o botão cinza é a mesma resposta e não depende de a pessoa estar olhando -- e
é o molde que a própria janela já usa na Galeria e na fila de revisão. A frase fica como rede
para quem chegar pela paleta de comandos em vez do botão.

**A reabilitação vai no `finally` que já existe**, e não depois de `_apply_duplicates`: o caminho
de exceção abre um modal e retorna, e reabilitar depois dele deixaria o botão cinza para sempre
-- trocar um travamento por outro.

**Critério de aceite.** Três cliques seguidos registram uma operação só, e o segundo diz "já está
em andamento".

**Testes.** `UmaDeteccaoDeCadaVezTests`, em `tests/test_dataset_panel.py`, com
`find_duplicate_groups` remendado para nunca terminar -- que é o estado que o segundo clique
encontra.

## S-315 · A exportação do PDF pesquisável para de prometer cancelamento

**Problema.** O `Event` era lido **uma vez**, como argumento:

```python
relatorio = pdf_pesquisavel.escrever(doc, Path(destino), seco=self._cancelar_exportacao.is_set())
```
`ui/texto_panel.py:2083`

`is_set()` é avaliado na montagem da chamada -- antes de qualquer pessoa ter tempo de clicar em
nada. Enquanto isso o registro dizia `cancellable=True` e o rodapé acendia o botão: o clique
existia, e não era lido por ninguém.

Havia um segundo erro embutido no primeiro: `seco` sair do evento de cancelamento junta duas
perguntas diferentes. "Simular" é uma escolha de quem chama; "cancelar" é uma interrupção de
quem espera.

**Solução.** Separar as duas, e **parar de prometer**: `cancelavel` vira parâmetro de
`_exportar_em_thread`, e o PDF pesquisável de uma folha passa `False`.

**Por que não implementar o cancelamento em vez de removê-lo.** Escrever a camada de uma folha
não tem ponto de parada com sentido -- o único seria antes do `save`, e cancelar ali economiza
fração de segundo. Um botão aceso sobre uma operação que não para é pior que nenhum botão: ele
ensina que o botão não funciona, e a próxima operação, que para de verdade, herda a descrença.
Se um dia o alvo virar a exportação do **livro inteiro**, aí o cancelamento passa a valer, e o
molde é o de `pdf_to_pgn.iter_pdf_diagrams`.

**O que continua cancelável:** `.txt`, `.rtf` e `.html`, que conferem o evento no ponto certo e
param antes de escrever. `cancelavel` é por chamador justamente para não perder isso.

**Critério de aceite.** O registro do PDF pesquisável tem `cancellable=False` e mantém
`loses_work=True`; o dos irmãos continua cancelável.

**Testes.** `test_o_pdf_pesquisavel_nao_promete_cancelamento`, ao lado de
`test_o_registro_declara_que_perde_trabalho` -- o par é o item.

## S-316 · Um `__all__` só, e é o do topo

**Problema.** `text/dicionario.py` declarava `__all__` **duas vezes** -- na linha 107, logo
depois do bloco de imports, e de novo na 306, no fim do arquivo. O segundo é o que vale, e ele
perdia dois nomes: `PALAVRA` e `PASTA_DO_LEXICO`.

Os dois são reexportados de `text/lexico.py` de propósito, e o comentário acima do import diz por
quê: quem lê o dicionário não deve precisar saber que a régua de palavra mora ao lado, e uma
segunda cópia de `e_palavra` "divergiria no primeiro ajuste".

**Solução.** Um só, no topo, com a união dos dois. O motivo fica escrito na primeira linha da
lista, porque quem acrescentar um nome no fim do arquivo vai fazê-lo de novo.

**Critério de aceite.** `dicionario.__all__` tem 23 nomes, entre eles os dois.

## S-317 · O acento na frase, e o caractere de controle no fonte

**Dois defeitos de escrita, e cada um é invisível de um jeito diferente.**

**O acento.** `"A FEN informada para estudo e inválida."` -- a interface deste projeto é pt-BR
**com** acento, e há teste para isso (`tests/test_strings.py`). Esta escapou porque o teste varre
uma lista de palavras, e `e` sem acento é uma palavra legítima. De passagem, o título da caixa
saiu de `"Erro"` para `"FEN inválida"`: nove caixas do programa têm o título genérico contra
trinta que nomeiam a operação, e o genérico não diz nada a quem está lendo depressa.

**O caractere de controle.** O docstring de `text/italico.py` explica por que a expressão regular
usa `(?![a-z])` "e não ``" -- só que o docstring não é cru, e `` numa string comum é um
**backspace**. O fonte tinha dois bytes `0x08` dentro dele. Nada quebrava: o Python lê, o `ruff`
não reclama, e a explicação continuava legível na tela porque o terminal engole o backspace. Mas
o arquivo tinha um caractere de controle onde deveria haver dois de texto, e a frase dizia o
contrário do que queria -- ela existe justamente para diferenciar `` de `(?![a-z])`.

**Critério de aceite.** Nenhum `0x08` em `src/`, e a frase da FEN com acento.

## S-318 · "Falha ao salvar" só quando a gravação falhou

**Problema.** O `try` de `save_current` cobria cinco coisas, e só a primeira podia falhar por
motivo do usuário:

```python
try:
    path = self._save_one(alvo, ...)      # escreve o PNG e a linha do CSV
    self._on_status(...)
    self._settle(alvo)                    # fecha o item na fila de revisão
    gravada = self._saved_sample(alvo)
    self._on_sample_saved(...)            # -> _reload_dataset_panel: repinta a aba Dataset,
                                          #    marca a caixa de verde, reconta as abas
except Exception as exc:
    messagebox.showerror("Erro", f"Falha ao salvar:
{exc}")
```
`ui/result_panel.py:1102-1120`

Um `AttributeError` em qualquer um dos quatro passos **posteriores à escrita** produzia a caixa
"Falha ao salvar" sobre uma amostra que está no disco.

**E o dano não para no susto.** A pessoa acredita que perdeu a correção, refaz e salva de novo; e
como `append_training_sample` nomeia por timestamp (`board_%Y%m%d_%H%M%S_%f.png`) e sempre chama
`LabelStore.append`, a segunda gravação vira **uma linha e um PNG duplicados** no `labels.csv` --
trabalho humano contado duas vezes, no arquivo que o projeto trata como o mais precioso que tem.

E não sobrava diagnóstico: o módulo tem 1.286 linhas, declara `logger` na linha 55 e **nunca o
usava**. No bundle da S-55 (`console=False`), o `str(exc)` da caixa era o único vestígio no mundo,
e sumia quando ela era fechada.

**Solução.** Dois `try`, com significados diferentes. O primeiro cobre `_save_one` e só ele; o
segundo cobre o acabamento de tela, registra com `logger.exception` e **não mente sobre a
gravação** -- a frase de status passa a dizer "Exemplo salvo … (a tela não pôde ser atualizada --
ver o log)". Mais `logger.exception` antes do modal de erro real, e um título que nomeia a
operação em vez de `"Erro"`.

**Critério de aceite.** `_on_sample_saved` levantando não abre caixa nenhuma e a gravação conta.
`save_sample` levantando continua abrindo a caixa com a causa.

**Testes.** `test_falha_de_tela_nao_e_anunciada_como_falha_de_gravacao` e
`test_falha_de_gravacao_continua_avisando`, em `tests/test_result_panel.py`. O par é o item: o
segundo é o que impede a correção de virar "erro nenhum aparece". O `_ServicoFalso` ganhou um
`erro` para poder produzir as duas falhas.

## S-319 · O consentimento de envio é daquele endereço, e não de qualquer um

**Problema.** `RemoteFenSettings.acknowledged` era um `bool` solto, e o docstring dele afirmava
o contrário do que o código fazia:

> "Fica gravado por endpoint implicitamente: trocar o endereço zera o reconhecimento, porque o
> aviso nomeia o host."

Nenhuma linha do projeto comparava o host consentido com o host atual. `grep -rn acknowledged`
devolvia quatro ocorrências: a declaração, o `to_dict`, o `from_dict` e o
`if not configuracao.acknowledged` de `ui/net_button.py`. E pior: `apply_environment` faz
`replace(remoto, endpoint=url, enabled=True)` e **preservava** o bit.

Quem consentiu uma vez com um endereço passava a mandar a imagem do tabuleiro para qualquer
outro -- posto por `CVOFF_REMOTE_FEN_URL` ou por uma edição em `data/settings.json` -- sem ver
aviso nenhum. A promessa central da S-32 era cumprida pelo comentário e não pelo código, e o
próprio checkbox da janela diz "Não perguntar novamente **para este endereço**".

Este é o único caminho do projeto em que bytes saem da máquina.

**Solução.** O campo passa a ser `acknowledged_host: str`, e `acknowledged` vira um `property`
que compara com o host configurado agora. `apply_environment` continua sem tocar no campo, e a
troca de endereço volta a perguntar de graça -- a comparação passa a existir de verdade.

**O arquivo antigo não é migrado.** Um `acknowledged: true` gravado não diz para qual endereço
valia, e supor que valia para o de hoje seria reintroduzir o defeito **na migração**. A pessoa vê
o aviso uma vez a mais, e isso é o barato.

**Critério de aceite.** Consentir em A e apontar para B reabre a caixa, inclusive pelo caminho da
variável de ambiente. Um `settings.json` com `acknowledged: true` e sem `acknowledged_host` chega
sem consentimento.

**Testes.** `test_o_consentimento_e_daquele_endereco_e_nao_de_qualquer_um` e
`test_o_arquivo_antigo_nao_traz_consentimento_migrado`, em `tests/test_settings.py`.

---

# Fase 55 — O primeiro dia

Os dois itens desta fase saíram da frente **primeiro-dia** da segunda passada: um clone do
repositório, sem `models/*.pt` e sem `data/samples/`, dirigido do zero. É o estado de 100% de
quem instala, e nenhum dos dois defeitos aparece para quem já tem o acervo montado.

## S-320 · Sem o classificador, o programa recusa em vez de inventar

**Problema.** `load_model` caía num modelo **não treinado** e o devolvia como se tivesse
carregado:

```python
if not model_path.exists():
    logger.warning("Checkpoint nao encontrado em %s: usando pesos aleatorios.", model_path)
    model = build_model(arch or DEFAULT_ARCH, pretrained=False)
    ...
    return model, dev
```
`inference.py:90-95`

E `models/*.pt` está no `.gitignore`: **este era o estado de todo clone novo.**

O que sai daí não é uma leitura ruim, é uma leitura inventada. Medido num livro real, página 30:
o rodapé anuncia "OCR pronto. Diagramas detectados: 1" e o tabuleiro mostra
`KKKKKKKK/KKKKKKKK/…` com confiança 0,081. No terminal é pior: `cvoff-infer` sai com **código
0**, manda a FEN falsa para o **stdout** e o aviso para o **stderr** -- quem faz
`cvoff-infer livro.pdf > fen.txt` fica com um arquivo limpo de mentiras. O mesmo caminho serve
`cvoff-export`, `cvoff-batch`, `cvoff-eval` e a Galeria.

A primeira FEN da vida de quem instala era ruído de pesos aleatórios, e nada dizia isso. A
conclusão razoável é "este programa é ruim", e não "falta um arquivo".

**Solução.** Levantar `FileNotFoundError` com a mensagem no molde de `text/modelo.py`, que já
acertou esta: **o que falta, por que não vem no git, e como obter** -- o campo "Modelo (.pt)" da
aba Configuração, ou `cvoff-train` depois de corrigir alguns diagramas e salvá-los.

**Por que não um "modo sem pesos" com marcação.** Porque o valor de saída é uma FEN, e uma FEN
marcada continua sendo copiada, exportada e comparada. O único uso honesto de pesos aleatórios é
testar a mecânica do pipeline, e para isso o teste constrói o modelo explicitamente.

**Critério de aceite.** `cvoff-infer` sem checkpoint sai com código de erro e sem FEN no stdout.

## S-321 · O conserto impresso não pode ser o que destrói o dado

**Problema.** Num clone limpo, `data/labels.csv` vem versionado com 4.454 linhas e
`data/samples/` vem só com um `.gitkeep` -- as imagens são 3,9 GB e ficam fora do git. Então
`cvoff-train` para com:

```
A auditoria reprovou o dataset... 4454 rótulo(s) com PNG ausente
-- conserto: cvoff-audit --drop-missing
```

Seguir a instrução impressa reduz o `labels.csv` de 4.455 para **1 linha** -- só o cabeçalho --
e não destrava nada: os rótulos utilizáveis continuam zero, antes e depois. O texto era gerado
sem olhar **se faltam algumas ou se faltam todas**, e o segundo caso é o de todo recém-chegado.

Há backup automático, o que salva o arquivo e não a confiança de quem acabou de ver 4.454
rótulos virarem um cabeçalho -- no primeiro comando que rodou.

**Solução.** Duas mudanças, nas duas pontas:

- a violação passa a dizer **procedência** quando faltam todas: "as imagens de `data/samples/`
  não vêm no repositório (3,9 GB); traga as suas, ou corrija diagramas na janela e salve com
  `Ctrl+S`" -- e explicitamente **não** manda usar `--drop-missing`;
- `drop_missing_labels` **recusa** quando a poda esvaziaria o arquivo. Poda parcial continua
  sendo o que a função é.

**Critério de aceite.** Com todos os PNGs ausentes, a violação não cita `--drop-missing` e a
função levanta sem tocar no CSV. Com alguns ausentes, tudo como antes.

**Testes.** `test_faltando_todas_as_imagens_a_poda_recusa` e
`test_o_conserto_impresso_muda_quando_faltam_todas`, em `tests/test_audit.py`. E o fixture de
`test_drop_missing_preserves_the_fen_in_quarantine` ganhou uma linha que **fica**: ele modelava
poda parcial com uma linha só, que é justamente o caso que a guarda nova recusa.

## S-322 · Nada é gravado antes de o estado lido chegar aos widgets

**Problema.** `_restore_state_or_default_pdf` lê o disco e, **três linhas depois**, chama
`_escolher_conjunto()` -- que termina em `_save_app_state()`. Nesse instante nenhum widget
recebeu ainda o valor guardado, e `_save_app_state` lê `pdf_panel.zoom_var`, `show_boxes_var`,
`flip_pages_var`, `texto_panel.zoom_da_vista`, `quebra_var`, `result_panel.board_zoom_var` e
`heatmap_var` -- **todos nos padrões de fábrica** -- e os escreve por cima de `self.state`.
`_remember_window_arrangement` faz o mesmo com `active_tab`, que vira a aba 0.

As linhas seguintes, que restauram os widgets, passam então a ler o estado que a linha 693
acabou de zerar. E `save_state` grava isso no disco no mesmo passo: **o valor antigo não volta
nunca**.

O efeito é que nada do que a S-156, a S-221 e a S-291 prometem lembrar sobrevive a fechar a
janela -- zoom do PDF, zoom do tabuleiro, heatmap, marcação de diagramas, roda que vira a página,
zoom e quebra da aba Texto, e a aba aberta. Quem trabalha com o heatmap desligado o desliga toda
sessão. Só `sash_fraction` e `estudo_divisor` escapavam, porque a S-311 lhes tinha dado uma
guarda própria dias antes.

**Solução.** Um sinalizador de ordem, `_estado_aplicado`, ligado no fim do bloco de restauração:
antes disso `_save_app_state` sai cedo com um `logger.debug`.

**Por que não `winfo_ismapped`, como na S-311.** Porque o problema é outro: ali o widget ainda
não existia na tela; aqui ele existe e é o **valor** que ainda não chegou nele. A pergunta certa
é sobre a ordem do arranque, e não sobre o mapeamento.

**Critério de aceite.** Gravar um estado com os oito campos fora do padrão, montar a janela, e
ler os widgets: todos com o valor gravado, e o arquivo em disco intacto.

## S-323 · A cessão de tecla ao campo de texto vem antes da declaração do painel

**Problema.** Dois defeitos que se somam.

Em `shortcuts.guard`, a ordem era: perguntar a `atalhos.destino` se o painel em foco declarou a
ação (S-244) e, **só depois**, perguntar a `cede_a_tecla` se o widget em foco é um campo de texto
(S-20). Com essa ordem, a declaração de um painel atropela a regra que cede `←`, `→`, `Home` e
`End` a todo campo.

E `StudyPanel.acoes_proprias` cedia só quando o foco era **a caixa de comentário** -- mas a sala
tem quatro campos: o `Entry` de FEN e as duas `Text` da lista e da anotação também.

O resultado, com o cursor no campo de FEN: a seta esquerda **move o cursor e desfaz um lance**,
`Home` vai para o início do texto **e** salta para o início da linha do estudo. E o `"break"` não
salva: como `bind_all` roda na bindtag `all`, que é a **última**, a ligação de classe do `Entry`
já moveu o cursor quando ele volta. Quem confere uma FEN à mão perde a posição da árvore sem
nenhum sinal, e o salvar seguinte grava a partir de um nó que ninguém escolheu -- que é
exatamente o defeito que `shortcuts.owns_key` documenta e diz ter fechado.

**Solução.** Inverter as duas perguntas em `guard`, e trocar a pergunta pontual da sala por
`shortcuts.ignores_widget(self.focus_get())`.

**A inversão é a metade que vale mais**, porque tira a obrigação de cada painel lembrar de
excluir os campos dele: a regra da S-20 passa a valer primeiro, sempre, e a declaração da S-244
decide o que sobra. A troca na sala fecha o caso concreto; a inversão fecha a classe.

**Critério de aceite.** Com o foco num `Entry`, `←` não chega ao painel. Fora de campo de texto,
a declaração do painel continua ganhando do comando global.

---

# Fase 56 — O que só a CI podia mostrar

Três itens que **nenhuma execução local podia encontrar**, porque os três só falham fora da
máquina onde a medição e o desenvolvimento acontecem. Eles são a S-296 pagando por si mesma na
primeira hora de vida.

## S-325 · O digest de código normaliza a quebra de linha

**Problema.** `_digest_of` hasheava os bytes crus do arquivo, e o `.gitattributes` declara
`*.py text eol=lf`: o repositório guarda LF e o disco de trabalho fica com o final de linha
nativo. Nesta máquina, 52 dos 414 módulos estão em CRLF -- entre eles `board_detection.py`,
`service.py` e `inference.py`. O mesmo arquivo, no mesmo commit, dava dois digests:

```
CRLF, como está no disco de quem mede    da3d01935c122469
LF,   como está no git e na CI           fd5b4c1ccddd3297
```

Consequência: `test_todo_relatorio_corrente_mediu_o_codigo_de_hoje` **não podia passar** fora da
máquina onde a medição foi feita -- nem na CI, nem em Linux, nem num worktree com outro final de
linha. Ela acusava "o módulo mudou" sobre um arquivo idêntico, e quem obedecesse remediria os
quatro relatórios para ver a mesma acusação de novo.

**Solução.** `
` vira `
` antes de entrar no hash.

**Não é um afrouxamento.** O que a guarda quer saber é se o **código** mudou, e trocar a quebra
de linha não muda código nenhum -- o próprio `git` trata os dois como o mesmo arquivo. Quem
precisa do byte cru é `_digest_file`, que é para artefato binário, e ali normalizar seria
corromper.

**Critério de aceite.** O digest de um módulo é o mesmo no disco CRLF e no checkout LF. Os
quatro relatórios foram remedidos e voltaram idênticos pela sexta vez: 0,7913, 0,7652, 0,7304 e
0,7478.

## S-326 · A largura da fita plena é derivada, e não escolhida

**Problema.** Três testes de `ModoDaFitaTests` montavam a fita em `self._em(2200)` -- 2.200 px é
a largura em que ela cabe numa linha **com as fontes desta máquina**. O runner do Windows
desenhou os mesmos dezessete botões mais largos, 2.200 não bastou, e os três falharam afirmando
`1 != 2`, `1 != 3` e `'pleno' != 'compacto'` sobre um código correto.

**Solução.** `_plena()` monta uma vez para perguntar `largura_de_troca` -- que a própria fita
**mede**, somando os grupos mais o espaço entre eles --, e remonta com folga. O número certo
nunca foi uma constante; o 2.200 era só um jeito de dizê-lo nesta máquina.

`FOLGA_DA_FITA_PLENA = 80` existe porque `largura_de_troca` é o limiar **exato**: montar ali
deixa a fita no fio, e um pixel de arredondamento do gerenciador de geometria a joga para duas
linhas. Oitenta é margem, não medida, e é por isso que ela tem nome.

## S-327 · Sonda de artefato não-versionado pula, e não reprova

**Problema.** As sondas do `cvoff-texto-status` são de dois tipos: `simbolo:` pergunta ao código,
que vem no clone, e `arquivo:` pergunta ao disco -- e alguns dos arquivos que ela procura são
`models/*.pt`, que o `.gitignore` mantém fora. Num clone limpo, a S-182 aparecia como "parcial"
contra uma spec que diz "implementada", e o teste falhava afirmando que o documento mentia sobre
um item que **está** entregue. O que faltava era o binário, não o código.

**Solução.** As divergências causadas por sonda de arquivo ausente saem da conta. É a mesma
regra que o `CONTRIBUTING` já escreve para `data/samples/`: teste que depende de dado
não-versionado pula, não falha.

**O pulo vem depois da afirmação, e só quando o filtro escondeu alguma coisa.** Assim o resto do
item continua cobrado, e uma execução que não pôde olhar tudo não se anuncia como se tivesse
olhado. Verificado dos dois lados: com o `.pt` no disco o teste passa; sem ele, pula nomeando
S-182, S-201 e S-203.

---

# Fase 60 — Os dados e o treino

Nove itens, e **dois já estavam entregues quando a fase chegou**: a poda total do `splits.csv`
saiu na S-300 e o `best_epoch` que indexava o histórico errado, na S-310. Ficam registrados
aqui com o número que o roadmap lhes deu, e a spec deles é a da Fase 53.

## S-368 · A poda total do `splits.csv` — entregue como [S-300](#s-300--lista-vazia-nunca-é-razão-para-podar-o-splitscsv)

## S-369 · O `best_epoch` do checkpoint sobre o histórico desta execução — entregue como [S-310](#s-310--a-melhor-época-é-a-que-is_best-marca)

## S-370 · Métrica de outro nome não é incumbente

**Problema.** `_resolve_best_metric` decidia o que a primeira época da retomada precisa superar
comparando dois números que podem não ser da mesma grandeza:

```python
gravado = resumed.best_metric
mesmo_split = str(resumed.metadata.get("split_hash", "")) == split_hash
if gravado is not None and mesmo_split:
```
`training.py:451`

O nome da métrica estava gravado nos metadados desde a S-105 -- `best_metric_name` é
`"val_board_exact_acc"` com validação e `"train_loss"` sem ela -- e **ninguém o lia**. Um
checkpoint treinado sem validação registra `-0,42`; retomá-lo com validação põe esse `-0,42` na
disputa de um número que vive em `[0, 1]`, e a primeira época grava por cima do que não devia.
No sentido contrário -- checkpoint com validação, retomada sem --, o `0,98` gravado nunca é
superado por um `-train_loss`, e **nenhuma** época grava.

**Solução.** O nome entra na comparação: só reaproveita o número quem foi medido com a mesma
métrica *e* no mesmo split. Nos demais casos vale o que a função já fazia para o checkpoint sem
métrica -- **medir** o modelo recém-carregado na validação atual, ~20 s, e ter o incumbente de
verdade.

**Critério de aceite.** Checkpoint com `best_metric_name="train_loss"` retomado num treino com
validação não devolve o número gravado. Mesmo nome e mesmo split continuam devolvendo `(0.99, 7)`
sem medir nada.

**Testes.** `test_metrica_de_outro_nome_nao_serve_de_incumbente`,
`test_checkpoint_sem_nome_de_metrica_tambem_nao_serve` e
`test_mesmo_split_e_mesma_metrica_reaproveitam_o_numero`, em `tests/test_training.py`.

## S-371 · Vazio não é identidade de partição

**Problema.** Na mesma linha, `str(resumed.metadata.get("split_hash", "")) == split_hash`
respondia **verdadeiro** quando os dois lados eram `""`. Sem arquivo de splits -- que é o caso
de quem treina com `--val-ratio` e nenhum `--splits` -- o `split_hash` é vazio dos dois lados, e
a igualdade dizia "mesma partição" sobre dois sorteios diferentes, feitos em datasets de
tamanhos diferentes. O incumbente vinha de outra partição, e a comparação que decide sobrescrever
8,7 MB de pesos estava medindo outra coisa.

**Solução.** `mesmo_split` exige hash **não vazio** dos dois lados. Vazio quer dizer "não se
sabe", e não se sabe leva à medição.

**Critério de aceite.** Dois `""` não reaproveitam o número gravado; dois hashes iguais e não
vazios continuam reaproveitando.

**Testes.** `test_split_vazio_dos_dois_lados_nao_e_o_mesmo_split`.

## S-372 · O checkpoint declara o lote que governou

**Problema.** Os metadados gravavam `batch_size` sempre, e `boards_per_batch` nunca. Desde a
S-62b há dois regimes: a cabeça por tabuleiro monta o `DataLoader` com `boards_per_batch` e
**ignora** `batch_size`; a cabeça por janela faz o contrário. Dois treinos da cabeça nova com 4
e com 8 tabuleiros por lote saíam com metadados idênticos -- que é exatamente o que a S-105
existiu para acabar, e ela o fechou só para o regime antigo.

**Solução.** `_optim_metadata` passa a receber a `ArchConfig` e grava os dois números mais
`batch_unit`, que diz qual deles governou (`"board"` ou `"square"`).

**Critério de aceite.** `boards_per_batch` 4 e 8 produzem metadados diferentes na cabeça por
tabuleiro; `batch_size` continua saindo com o mesmo valor de antes na cabeça por janela.

**Testes.** `UnidadeDoLoteNosMetadadosTests`, três casos.

## S-373 · `os.replace` recusado diz que o arquivo está aberto

**Problema.** No POSIX, renomear por cima de um arquivo aberto funciona. **No Windows, não:** um
`handle` no destino sem `FILE_SHARE_DELETE` faz o rename falhar com `PermissionError: [WinError 5]
Acesso negado`, e essa frase crua chegava a quem estava na frente da tela. Ela manda procurar
permissão de pasta num problema que é o Excel com o `labels.csv` aberto -- e o Excel é
exatamente o programa em que alguém abriria um CSV de 4.454 linhas. O antivírus produz o mesmo
erro por alguns milissegundos, sem que nada esteja errado.

**Solução.** `atomic_io._substituir` insiste cinco vezes com espera crescente (1,2 s no total) e,
se ainda assim falhar, levanta `PermissionError` com a frase que diz a causa provável, o que
fazer, e que o arquivo anterior continua intacto. Os dois casos ficam atendidos: o antivírus
solta sozinho, e o Excel precisa ser fechado.

**Critério de aceite.** Uma falha seguida de sucesso grava sem ninguém saber. Falha em todas as
tentativas levanta com "aberto em outro programa", o arquivo antigo intacto e nenhum `.tmp`
vizinho para trás.

**Testes.** `SubstituicaoTravadaTests`, em `tests/test_atomic_writes.py`.

## S-374 · O CSV salvo pelo Excel continua legível

**Problema.** O Excel, ao salvar "CSV UTF-8", escreve o BOM `EF BB BF` no começo. `LabelStore`
abria o arquivo com `encoding="utf-8"`, e a primeira coluna passava a se chamar o BOM seguido de
`filename` -- que não é `filename`. `REQUIRED_COLUMNS.issubset` falhava e a mensagem listava dois
conjuntos que **se leem iguais na tela**: `precisa das colunas {'filename', 'fen'}. Encontradas:
{'filename', 'fen', ...}`. O dataset inteiro ficava ilegível por três bytes invisíveis, com um
recado que não dizia a causa.

**Solução.** A leitura passa a `utf-8-sig`, que aceita os dois arquivos. A **escrita** continua
`utf-8` puro: `utf-8-sig` acrescentaria o BOM, e quem lê o `labels.csv` de fora deste módulo
continua vendo o arquivo que sempre existiu.

**Critério de aceite.** Um `labels.csv` com BOM lê as mesmas linhas e as mesmas colunas; reescrevê-lo
não devolve o BOM ao disco.

**Testes.** `BomDoExcelTests`, três casos, em `tests/test_labels.py`.

## S-375 · Backup não escreve por cima de backup

**Problema.** O nome do backup tem resolução de **um segundo**
(`labels.csv.bak-20260828_120000`), e duas cópias no mesmo segundo não são hipótese: `move_to`
faz backup da origem e do destino em sequência. A segunda apagava a primeira -- e a primeira era
justamente o estado anterior que alguém ia querer de volta. Além disso a cópia era um
`write_bytes` direto: interrompida no meio, deixa um `.bak-` truncado, que se parece com um
backup e não é.

**Solução.** O nome é reservado com `O_EXCL` -- e não com um `if exists()`, porque entre a
pergunta e a escrita cabe o outro processo --, e quem perde a corrida acrescenta `-2`, `-3`. O
conteúdo é escrito no descritor reservado, com `fsync`, e o arquivo parcial é apagado no caminho
da exceção.

**Critério de aceite.** Dois backups no mesmo segundo produzem dois arquivos, e o primeiro
mantém o conteúdo dele. Cópia interrompida não deixa `.bak-` nenhum. `labels.py` saiu da lista
`PERMITIDAS` de `tests/test_atomic_writes.py`: não há mais escrita direta no módulo.

**Testes.** `test_dois_backups_no_mesmo_segundo_nao_se_apagam` e
`test_copia_interrompida_nao_deixa_backup_pela_metade`.

## S-376 · `jitter` e `affine` são probabilidades, e a assinatura as vê

**Problema.** `AugmentConfig` declara oito probabilidades. Cinco são lidas por
`build_augmentations`; `blur` é lida por `build_train_transform`; **`jitter` e `affine` não eram
lidas em lugar nenhum** -- `ColorJitter` e `RandomAffine` estavam sempre na lista.
`AugmentConfig(jitter=0.0)` treinava com jitter ligado. E o `version`, que existe para que "o
modelo A é melhor que o B" não compare dois regimes de aumento, só olhava as cinco dirigidas:
os dois regimes saíam ambos como `aug0`, e o checkpoint não guardava nada que os separasse.

**Solução.** As três genéricas passam por `_com_probabilidade`, e o `version` ganha um sufixo
quando alguma delas sai do padrão (`aug0-j0`), mais o período da hachura quando a hachura está
ligada.

**`p >= 1` devolve a etapa crua, e isso não é otimização.** `RandomApply.forward` sorteia um
número antes de decidir, mesmo com `p=1,0`; envolver as duas etapas que hoje são incondicionais
consumiria dois sorteios por casa e mudaria toda a sequência do RNG. **O treino do padrão sai
idêntico ao de antes deste item**, e é isso que o primeiro teste trava.

**Critério de aceite.** `build_train_transform()` monta a mesma lista de sempre, tipo por tipo.
`jitter=0` tira o `ColorJitter`; `jitter=0.5` o envolve em `RandomApply`. `AugmentConfig()`,
`(jitter=0)`, `(affine=0)` e `(blur=0)` têm quatro assinaturas distintas, e a do padrão continua
sendo `aug0` -- os checkpoints que existem foram gravados com ela.

**Testes.** `ProbabilidadeDasGenericasTests` em `tests/test_training.py`; três testes novos em
`tests/test_augment.py`.

---

# Fase 61 — Os quarenta comandos

## S-377 · Todo comando aceita `-v`

**Problema.** O README garante `-v` nos 40 comandos, e a mensagem de erro da S-126 termina com
"Rode de novo com -v para ver o rastro completo". **Doze comandos respondiam `error: unrecognized
arguments: -v`** -- seis deles sem nem a forma longa. Quem seguia a instrução impressa pelo
próprio programa recebia um segundo erro, agora do `argparse`, e código de saída 2 sobre uma
falha que era outra coisa.

E havia a metade invisível: `run_main` lia a bandeira de `argv or []`, e como *console script* o
`main` é chamado **sem argumento nenhum** -- `argv` chega `None`, a lista fica vazia, e no uso
real (o único em que alguém digita `-v`) a bandeira nunca era vista. Nos testes, que passam
`argv`, ela sempre foi vista: é por isso que ninguém percebeu.

**Solução.** `cli.add_verbose(parser)` declara a bandeira num molde só, e os 40 comandos passaram
a usá-lo -- inclusive os 28 que a declaravam à mão. `run_main` cai para `sys.argv[1:]` quando
`argv` é `None`.

**Critério de aceite.** Nenhum módulo de comando declara `-v` por conta própria. Com
`sys.argv = ["cvoff-x", "-v"]` e `argv=None`, a exceção volta em vez de virar código de saída.

**Testes.** `BandeiraVerboseTests`, quatro casos, em `tests/test_entrypoints.py`.

## S-378 · Código de saída é classe, e não número solto

**Problema.** A tabela da S-126 dá três classes de falha -- 1 defeito do programa, 2 entrada
inválida, 3 checkpoint --, e trinta e cinco `return` escreviam o número à mão. Em onze deles o
número dizia a classe errada: `cvoff-evaluate` e `cvoff-experiment` classificavam "o arquivo de
splits que você apontou não existe" como **defeito do programa**; `cvoff-batch`, `cvoff-gallery`,
`cvoff-field`, `cvoff-provenance` (duas vezes), `cvoff-texto-grade`, `cvoff-texto-ordem` e
`cvoff-texto-placar` faziam o mesmo com o caminho vazio ou ausente; e `cvoff-infer` devolvia 1
quando a página apontada simplesmente não tem tabuleiro.

Quem consome isso é script -- `cvoff-scan --all && cvoff-...` --, e para ele "o livro estava
corrompido" e "houve um defeito no programa" têm de ser distinguíveis.

**Solução.** Todos os retornos de falha passam pelas constantes `EXIT_FAILURE`, `EXIT_BAD_INPUT`
e `EXIT_NO_CHECKPOINT`, e os onze foram reclassificados pela tabela. `return 0` continua
permitido como literal: "deu certo" não tem classe para errar.

**Três testes existentes mudaram de número, e é a mudança de interface que este item é:**
`--baseline` inexistente no `texto-grade` e no `texto-ordem`, `--semear` sobre arquivo já
existente no `texto-placar`, e os dois do `cvoff-experiment` -- todos de 1 para 2.

**Critério de aceite.** Nenhum `return` de função `-> int` em `cli/` é um literal 1, 2 ou 3.

**Testes.** `CodigoDeSaidaPelaTabelaTests`, em `tests/test_entrypoints.py`.

## S-379 · Os dois códigos do `cvoff-export-onnx` estavam trocados entre si

**Problema.** O caso que dá nome ao item, e que a S-378 encontrou por varredura:

```python
if not Path(args.model).exists():
    print(f"Checkpoint nao encontrado: {args.model}")
    return 1              # a classe 3 existe exatamente para isto
...
return 0 if report.passes else 2   # paridade reprovada não é entrada inválida
```
`cli/export_onnx.py:79,132`

Checkpoint ausente saía como "falha inesperada", e a paridade numérica reprovada -- que é uma
falha do artefato que o próprio comando acabou de gravar -- saía como "entrada inválida". Um
script que confie nos códigos toma as duas decisões erradas.

**Solução.** 3 para o checkpoint ausente, 1 para a paridade reprovada, 2 para os splits vazios e
para o split sem amostra. Os dois pontos ganharam comentário dizendo o que aconteceu.

**Critério de aceite.** Coberto pela varredura da S-378 mais a leitura do arquivo.

## S-380 · Cinco relatórios saíram da lista de escrita direta

**Problema.** `tests/test_atomic_writes.py` mantém a lista `PERMITIDAS` de escritas que podem
não ser atômicas, com o motivo de cada uma. Cinco relatórios de CLI estavam lá sob o argumento
"artefato derivado, refeito rodando o comando de novo" -- e o argumento não sobrevive ao próprio
critério: o `--save-matches` do `cvoff-games` é o artefato dos **104 minutos** de varredura de
2026-08-13 (`docs/ARCHITECTURE.md`), e o relatório de campo é a régua primária do projeto desde a
Fase 7.

**Solução.** Os cinco passam por `atomic_write_text` e saíram da lista. Mesmo nos baratos a
escrita atômica não custa nada -- são as mesmas linhas --, e um JSON truncado é pior que um JSON
ausente, porque `json.load` falha longe de onde a interrupção aconteceu.

**Critério de aceite.** `PERMITIDAS` não tem mais nenhuma entrada de `cli/`, e a varredura de
escrita direta continua verde.

**Testes.** Os de `tests/test_atomic_writes.py`, que já existiam: a lista **é** o teste.

## S-381 · `--baseline` é conferido antes de medir, não depois

**Problema.** Os cinco comandos de regressão têm o mesmo desenho: medem o acervo e, no fim,
comparam o número com o de um relatório anterior. A conferência do caminho ficava **junto da
comparação**, depois da medição inteira:

```python
relatorio = medir(pdfs, por_livro=args.por_livro)   # o acervo inteiro
...
if args.baseline:
    if not args.baseline.exists():
        logger.error("O baseline %s não existe.", args.baseline)
```
`cli/texto_grade.py:603,651`

Um nome digitado errado custava a varredura completa para então dizer que o arquivo não existe.
No `texto-duas-linhas` e no `texto-vertical` não havia conferência nenhuma: o `json.loads`
estourava `FileNotFoundError` no fim, com o mesmo prejuízo.

**Solução.** `cli.confere_baseline` devolve `EXIT_BAD_INPUT` logo depois do `configure_logging`,
nos cinco comandos. Um caminho que não existe é sabido antes de a primeira página abrir.

**Critério de aceite.** Com `--baseline` inexistente, a função de medição **não é chamada** e o
`--saida` não é escrito.

**Testes.** `test_o_baseline_inexistente_e_recusado_antes_de_medir`, que troca `medir` por um
`side_effect` que falha se for chamado.

## S-382 · A mesma bandeira, nas duas grafias

**Problema.** Três bandeiras existiam nas duas línguas, em comandos irmãos: `--apply` (games,
provenance) contra `--aplicar` (texto-conflitos); `--limit` (batch, review) e `--limit-books`
(scan) contra `--limite` (sete comandos de texto); `--dry-run` (texto-lexico) contra `--seco`
(texto-pesquisavel). Quem usa a linha de comando decora o que digitou ontem, e errar a língua
devolve `unrecognized arguments` -- a mesma parede da S-377, por outro caminho.

**Solução.** **Nenhuma bandeira foi renomeada** -- renomear quebraria script e documento. As duas
grafias passaram a ser a mesma bandeira, declaradas na mesma `add_argument`; o `dest` continua
sendo o da primeira, então nenhum código de leitura mudou.

**Critério de aceite.** `cvoff-texto-grade --limit 3` e `cvoff-batch --limite 2` funcionam, e
`cvoff-games --aplicar` liga `args.apply`.

**Testes.** `VocabularioDasBandeirasTests`, que varre os pares e falha se um comando declarar só
uma das grafias.

## S-383 · O bloco de medição é declarado num lugar só

**Problema.** `--csv`, `--samples`, `--splits`, `--model`, `--dpi` e `--accept-threshold` eram
copiados à mão comando a comando. O caminho da partição estava escrito **seis vezes**, sob dois
nomes (`DEFAULT_SPLITS` e `DEFAULT_SPLITS_PATH`) e por duas fórmulas diferentes
(`PROJECT_ROOT / "data" / "splits.csv"` e `DEFAULT_DATASET_CSV.parent / "splits.csv"`). O DPI era
o literal `220` em doze declarações, e `DEFAULT_DPI` numa décima terceira -- definido dentro de
`provenance.py`.

Iguais hoje, e é aí que mora o defeito: mudar o `labels.csv` de pasta faria metade dos comandos
seguir e a outra metade ficar, e a diferença apareceria como "o `cvoff-eval` mede outro conjunto
que o `cvoff-audit`".

**Solução.** `config.DEFAULT_SPLITS_PATH` e `config.DEFAULT_DPI` passam a ser os donos dos dois
valores, e `cli/__init__.py` ganha `add_dataset_arguments`, `add_model_argument`,
`add_dpi_argument`, `add_splits_argument` e `add_accept_threshold_argument` -- com o `help` que
faltava em todos eles. As seis constantes locais foram apagadas.

**Critério de aceite.** Nenhum módulo de `cli/` declara os seis argumentos à mão nem define um
`DEFAULT_SPLITS*` próprio. O `--csv` do `cvoff-census` está de fora da varredura, com o motivo
escrito: ali ele é **saída**, e não o dataset.

**Testes.** `BlocoDeMedicaoTests`, dois casos.

## S-384 · O `--help` explica os 373 argumentos

**Problema.** Cento e onze argumentos não tinham `help`, e o `--help` os listava como nome e nada
mais. Entre eles `--epochs`, `--batch-size` e `--lr` do `cvoff-train` -- os três que alguém
ajusta antes de um treino de duas horas --, `--orientation`, `--reading-order` e
`--max-boards-per-page`, que decidem o que entra no PGN. Um argumento sem ajuda é um argumento
cujo efeito só se descobre lendo o fonte.

**Solução.** Todos ganharam uma linha dizendo o efeito, e o padrão quando ele não é óbvio. Vinte
e oito deles eram o próprio `-v`, que a S-377 resolveu de uma vez.

**Critério de aceite.** Nenhuma chamada de `add_argument` em `cli/` sem `help=`.

**Testes.** `AjudaDeTodoArgumentoTests`, com a guarda-da-guarda que confere que a varredura
enxerga mais de 300 argumentos -- um scanner cego passaria sempre.

## S-385 · `--paginas` inválido fala português

**Problema.** `intervalo_de_paginas` chamava `int()` direto sobre o pedaço digitado, e
`int("58a")` levanta `invalid literal for int() with base 10: '58a'`. A frase chegava inteira à
tela dentro de `--paginas inválido: ...`. A S-126 tirou o inglês das três falhas mais prováveis;
esta é a quarta, e está no argumento que mais se digita à mão. `"58-"` produzia a mesma frase
sobre uma string vazia.

**Solução.** `_numero_de_pagina` valida antes de converter e levanta em pt-BR dizendo **o que
teria funcionado** -- `58`, `58-62`, `58,60,62` --, porque um erro de digitação em `--paginas` é
quase sempre de forma, e não de intenção.

**Critério de aceite.** Nenhuma mensagem de `--paginas` contém "invalid literal". O intervalo
invertido continua recusado com a frase que já tinha.

**Testes.** `IntervaloDePaginasTests`, quatro casos, em `tests/test_cli_errors.py`.
