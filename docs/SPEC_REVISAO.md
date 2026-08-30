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
> | S-78 a S-82, S-143, S-175, S-176, S-454 | [ANALISE_DETECCAO.md](ANALISE_DETECCAO.md) |
> | S-83 a S-94 | [PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md) |
> | S-95 a S-142, S-171 a S-174, S-218, S-219 | [SPEC_FASE14.md](SPEC_FASE14.md) |
> | S-144 a S-170, S-177 | [SPEC_UI.md](SPEC_UI.md) |
> | S-178 a S-217 | [SPEC_TEXTO.md](SPEC_TEXTO.md) |
> | S-220 a S-234, S-294, S-295, S-324 | [SPEC_APARENCIA.md](SPEC_APARENCIA.md) |
> | S-235 a S-267, S-291 a S-293 | [SPEC_EDITOR.md](SPEC_EDITOR.md) |
> | S-268 a S-290 | [SPEC_ESTUDO.md](SPEC_ESTUDO.md) |
> | S-296 a S-323, S-325 a S-430, S-451, S-453 (menos S-324) | [SPEC_REVISAO.md](SPEC_REVISAO.md) |
> | S-431 a S-440 | [SPEC_REVISAO_EXTERNA.md](SPEC_REVISAO_EXTERNA.md) |
> | S-441 a S-450 | [SPEC_ACABAMENTO.md](SPEC_ACABAMENTO.md) |

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

**E medir o limiar não bastou: a janela também tem de caber na tela.** O runner da CI tem 1.024 px
de largura, e uma `Toplevel` não fica mais larga que o monitor -- a fita de 2.200 px que estes
testes pedem simplesmente não existe lá, e quatro deles reprovavam sobre um comportamento correto.
`_coube_ou_pula` é a saída: quando a janela não cresceu até a largura pedida, o teste **pula
dizendo os números** -- largura pedida, limiar medido, largura real, linhas e modo --, e com o
`-ra` da S-417 esse motivo aparece em toda rodada.

**A primeira versão dessa saída falhava do jeito que ela existia para evitar**, e vale registrar:
ela destruía a fita e só então perguntava `winfo_width()` para montar a mensagem, o que levanta
`TclError: bad window path name`. Um `skipTest` que estoura antes de pular é uma falha com outro
nome, e foi a **segunda** execução da CI que mostrou isso. Mede-se antes de destruir.

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

---

# Fase 57 — A folha do livro, o editor, e a sala de estudo

Vinte itens para os vinte e seis achados das três frentes que a revisão manteve juntas: o
visualizador de PDF, o editor de texto e a sala de estudo. Onde um item cobre mais de um achado,
eles são da mesma família e o texto os nomeia.

**Dois achados já estavam entregues quando a fase chegou**: o carimbo da linha impressa no nó
errado saiu na S-312, e a `_pintar_faixas` que esvazia o registro de fontes é a metade de dentro
da S-336.

## S-328 · A folha é contada em base 1 na tela inteira

**Problema.** O campo de página e os rodapés de mensagem diziam base 0; o rodapé de documento, o
título da janela e a anotação de campo diziam base 1. Quem lê a tela inteira via **dois números
para a mesma folha** -- e o docstring de `strings.titulo_da_janela` afirmava, desde a S-167, que
a página é dita "em base 1, **como o campo da tela**", o que era falso justamente sobre o campo.

**Solução.** O `Spinbox` perde o `textvariable` e passa a mostrar `índice + 1`, com faixa `1..n`;
`page_index_var` continua sendo o índice interno base 0 que trinta chamadas leem. Seta e
digitação passam pela mesma porta (`_on_page_typed`), e as mensagens de "Renderizando página" e
"Página N pronta" -- mais as três de `result_panel` e `app_tkinter` -- somam 1.

**Critério de aceite.** Com o índice 2 na tela, o campo diz `3` e o título diz `p. 3 de N`.

**Testes.** `BaseDaFolhaTests`, cinco casos, em `tests/test_pdf_panel_navegacao.py`; os quatro de
`NumeroDigitadoTests` passaram a afirmar a base nova.

## S-329 · Trocar o DPI invalida a folha rasterizada

**Problema.** `render_current_page` devolve cedo quando `page_loaded_for_index` bate com o índice.
Mudar o DPI na aba Configurações não invalidava nada: a imagem continuava rasterizada no DPI
antigo e a detecção passava a medir no novo, então os retângulos de diagrama saíam do lugar sobre
a imagem embaixo deles.

**Solução.** `pdf_panel.observar_dpi(var)` observa o campo e re-rasteriza **depois que ele para de
mudar** -- o `trace` dispara a cada tecla, e `220` digitado à mão passa por `2` e `22`. O `after`
de 400 ms espera, o `after_cancel` impede a fila, e `_dpi_rasterizado` evita o trabalho quando o
valor volta ao que já estava na tela.

**Critério de aceite.** Mudar o DPI e aplicar re-renderiza uma vez; aplicar de novo sem mudar não
re-renderiza. Zoom continua **não** invalidando: ele reescala a mesma imagem, de propósito.

**Testes.** `DpiEZoomTests`, três casos.

## S-330 · O piso da seleção de área é medido na página

**Problema.** `MIN_SELECTION_PX = 12` era comparado com as coordenadas do canvas, que já vêm
multiplicadas pelo zoom: a 25% o piso valia 48 px de página e a 200%, 6 px -- o mesmo arrasto era
"muito pequeno" numa vista e recorte válido na outra, e o recado não dizia nada disso.

**Solução.** A comparação passa a ser feita **depois** da conversão para pixel de página. O que a
constante quer dizer -- "menos que isto não contém casa nenhuma" -- é uma afirmação sobre a folha.

**Critério de aceite.** 20 px de tela a 200% são recusados (10 px de página); os mesmos 20 px a
50% viram o recorte `(0, 0, 40, 40)`.

**Testes.** `test_o_piso_da_selecao_e_medido_na_pagina` e o par a menos zoom.

## S-331 · O PDF protegido por senha não troca o livro por dentro

**Problema.** A S-123 pôs `get_pdf_page_count` como primeira linha de `load_pdf` justamente para
validar antes de mutar. O PDF cifrado passava por ela: `fitz.open` aceita o arquivo, `needs_pass`
fica ligado e `page_count` responde o número certo -- **1**, no teste. O painel então trocava o
livro do programa inteiro (Galeria, resultados, aba de estudo) e só o render falhava, com
`ValueError: document closed or encrypted`, em inglês, e a tela ainda mostrando o livro anterior.

**Solução.** `pdf_io._open_document` recusa o documento cifrado com um `ValueError` em pt-BR que
diz o que fazer. Mora ali, e não no painel, porque **nenhum** caminho deste programa sabe pedir
senha: o `cvoff-scan`, o censo e a exportação encontrariam o mesmo muro três camadas adiante --
e `ValueError` é o que o `cli_errors` da S-126 traduz em código 2.

**Critério de aceite.** Abrir um PDF válido e depois um cifrado deixa o estado no válido, sem
callback nenhum disparado, e a caixa diz "senha" e "bom.pdf continua aberto".

**Testes.** `test_o_pdf_com_senha_nao_troca_o_estado_do_valido`, ao lado do da S-123.

## S-332 · A roda é de quem está por cima

**Problema.** `_pointer_over_canvas` respondia "o ponteiro está na área do canvas", que não é a
mesma coisa que "o canvas é o que está debaixo do ponteiro". Com a paleta de comandos, uma lista
suspensa ou um diálogo sobre a folha, a roda rolava o PDF **atrás** deles e devolvia `"break"`:
quem girava a roda sobre a lista via a página do livro passar.

**Solução.** A conta aritmética continua -- ela existe porque `winfo_containing` devolve `None`
quando uma janela de outro programa cobre o ponto, e isso foi medido --, e o `winfo_containing`
volta como **desempate**: quando ele nomeia um widget desta aplicação, só o canvas (ou um filho
dele) manda na roda; quando devolve `None`, vale o retângulo, como antes.

**Critério de aceite.** Com outro widget sob o ponteiro, a roda não é do canvas; com `None`, é.

**Testes.** Três casos em `DpiEZoomTests`.

## S-333 · O zoom tem tecla, e a dica diz o que a roda faz

**Problema.** Aumentar, diminuir e enquadrar a folha inteira não tinham tecla nenhuma -- `Ctrl+0`
ajustava à largura desde a S-165 e era só. E a dica do botão "Ajustar à largura" prometia que
`Ctrl + roda` "faz o mesmo", quando `Ctrl + roda` aproxima e afasta por passos: são dois gestos,
e a frase juntava os dois.

**Solução.** `Ctrl++`, `Ctrl+-` e `Ctrl+9` entram em `ATALHOS` -- as duas primeiras com destino
declarado no editor, onde elas mexem no corpo do texto (`SOBREPOSICOES_NO_EDITOR`). A dica passa
a dizer as três coisas separadas: o que o botão faz, o que `Ctrl + roda` faz, e o que a roda
sozinha faz.

**Critério de aceite.** `ATALHOS` tem 21 linhas, a legenda e o menu mostram as três novas, e
nenhuma sequência se repete.

**Testes.** `tests/test_ui_menu.py` e `tests/test_ui_atalhos_destino.py`, com o número atualizado
e as três teclas afirmadas por nome.

## S-334 · A formatação entra no desfazer

**Problema.** Negrito, itálico, sublinhado, tachado, cor, realce, "limpar formato" e "limpar cor"
mexem em **etiqueta** e não em caractere -- de propósito, para não mover o cursor. A consequência
é que a pilha do Tk não vê nada disso: o `Ctrl+Z` seguinte desfazia a **digitação anterior** e
deixava o negrito onde estava. Desfazia outra coisa, em silêncio.

**Solução.** As quatro ferramentas de etiqueta guardam um instantâneo do documento antes de
escrever e fecham a marca de edição depois (`_fechar_instantaneo`). E `desfazer` passa a escolher
entre as duas pilhas pela marca do topo: **instantâneo com a contagem de hoje é a ação mais
recente e vai primeiro**; contagem antiga quer dizer que se digitou depois dele.

Antes, a digitação vinha sempre primeiro, e isso bastava enquanto toda ferramenta redesenhava --
o redesenho zera a pilha do Tk, então não havia empate possível.

**Critério de aceite.** `Ctrl+Z` depois de aplicar negrito tira o negrito. Negrito, depois
digitação, depois `Ctrl+Z`: sai a digitação, e o negrito fica.

**Testes.** Quatro casos em `PilhaDoEditorTests`, incluindo a cor e a ordem entre as duas pilhas.

## S-335 · Desfazer e refazer devolvem o lugar

**Problema.** Os dois passam por `desenhar_documento`, que refaz o widget inteiro: cursor no
início, seleção perdida, rolagem no topo. Numa folha de sessenta linhas, desfazer uma substituição
feita no rodapé jogava a pessoa para a primeira linha.

**Solução.** `_lugar_atual` guarda cursor, seleção e topo da rolagem antes do redesenho, e
`_repor_lugar` os devolve depois. Índice que não existe mais -- o documento encolheu -- é
ignorado.

**Critério de aceite.** Desfazer uma substituição com o cursor em `1.5` devolve o cursor a `1.5`.

**Testes.** `test_desfazer_devolve_o_cursor_e_a_rolagem`.

## S-336 · O zoom da vista redimensiona o que tem estilo

**Problema.** Dois defeitos somados, e o segundo escondia o primeiro. `_aplicar_zoom` refaz a
fonte de cada etiqueta de desenho percorrendo `_fontes_desenhadas` -- e chama `_pintar_faixas`
uma linha antes, que termina em `_pintar_estilos`, que **esvazia** esse registro: o laço percorria
um dicionário vazio. E, mesmo cheio, `_fonte_do_trecho` deriva a fonte de um trecho com estilo da
fonte do **sistema**, que o zoom não toca -- só o trecho sem estilo herdava o zoom, por vir da
fonte do editor.

Resultado: aproximar a vista aumentava a prosa comum e deixava título, notação e legenda do mesmo
tamanho.

**Solução.** O registro é guardado antes de `_pintar_faixas` e devolvido depois (esvaziá-lo é
certo no redesenho, onde cada corrida volta a pedir a etiqueta dela, e errado aqui, onde não há
redesenho), e o degrau do zoom entra na conta do trecho com estilo. Degrau de corpo e degrau de
zoom vivem na mesma unidade -- um ponto --, que é o que permite somá-los antes de virar tamanho.

**Critério de aceite.** Aplicar zoom muda a fonte da etiqueta `fonte:titulo:*`, e o registro de
fontes desenhadas sobrevive à chamada.

**Testes.** `ZoomComEstiloTests`, dois casos.

## S-337 · A aba Texto segue a pele e o tema

**Problema.** A aba resolvia cor com `tokens.cor(papel)` **sem estilo**, e `tokens.cor` sem estilo
devolve a reserva clara: a aba Texto era a única superfície da janela congelada no tema de
fábrica, com faixa de confiança, cor de autor e realce iguais em qualquer pele. O mesmo valia
para o HTML exportado, cujo docstring afirma desde a S-251 que as cores saem "contra o tema em
uso".

**Solução.** `theme.cor_atual` nas seis resoluções, e o registro em `theme.ao_repintar` ao lado de
onde se pintou -- sem ele a aba ficaria com a cor de quando nasceu até o próximo redesenho.

**Critério de aceite.** A cor de uma faixa na tela é igual a `theme.cor_atual(papel)`, e
`theme.repintar()` alcança a aba.

**Testes.** `CorDaAbaTests`, dois casos.

## S-338 · A exportação da aba leva os recortes

**Problema.** `exportar(recortes=...)` existe desde a S-250 e a aba Estudo o usa desde a S-289; a
aba de **texto** nunca o passou. Todo diagrama saía como marca sem imagem -- o alvo do
`![Diagrama 1]` vinha vazio --, e `Relatorio.sem_recorte` contava a falta no rodapé desde sempre:
o defeito estava anotado no próprio relatório.

**Solução.** `_gravar_recortes` grava um PNG por diagrama em `diagramas/`, ao lado do arquivo, e
devolve o mapa que `exportar` quer. A conta do recorte saiu de `_miniatura` para
`recorte_do_bloco`, que é numpy puro: a miniatura é do Tk e vive na thread da janela, o PNG é da
thread de trabalho, e a aritmética do DPI não podia ficar escrita duas vezes.

**Critério de aceite.** O `.md` de uma folha com diagrama aponta para
`diagramas/<arquivo>_d1.png`, e o arquivo está lá. Sem folha renderizada, a marca sai sozinha e
nenhuma pasta é criada.

**Testes.** Dois casos em `ExportacaoDaAbaTests`.

## S-339 · O `.md` conta o estilo que ele não escreve

**Problema.** `Markdown.suporta` inclui `"estilo"` por causa do `#` do título, e o Markdown não
tem sintaxe para prosa, notação e legenda: os três saíam como texto comum com o relatório dizendo
"perdido: nada".

**Solução.** O protocolo `Formato` ganhou `suporta_valor(atributo, valor)`, opcional, para o
formato que carrega **alguns** valores de um atributo. O `.md` responde `True` só para `titulo`.

**Critério de aceite.** Uma legenda exportada em `.md` conta perda de `estilo`; um título, não.

**Testes.** `test_o_md_declara_a_perda_do_estilo_que_ele_nao_escreve`.

## S-340 · O `.html` tem regra para cada classe que emite

**Problema.** `_classes` emitia `estilo-titulo`, `estilo-prosa`, `estilo-notacao` e
`estilo-legenda`, e a folha de estilo não tinha regra para nenhuma delas: quatro classes que não
faziam nada, num arquivo que existe para mostrar o que a aba mostrava.

**Solução.** `estilos_do_html` declara como cada estilo se escreve em CSS, e `_classes` só emite
os que estão lá. `titulo` sai como cabeçalho e nunca precisou de classe; `prosa` é o padrão do
documento, e marcá-lo seria dizer "isto é normal" em toda corrida normal da folha. Sobram os dois
que **são** diferentes e que o editor desenha diferente: notação em monoespaçada, legenda em
itálico.

**Critério de aceite.** O conjunto de classes `estilo-*` emitidas é igual ao conjunto que tem
regra -- afirmado nos dois sentidos.

**Testes.** `test_o_html_tem_regra_para_cada_classe_de_estilo_que_emite` e o do arquivo gerado.

## S-341 · O `.rtf` conta o recorte que ele joga fora

**Problema.** `Rtf.diagrama` ignora o `recorte` -- o RTF carregaria a imagem só pelo grupo de
figura, com o PNG em hexadecimal --, e `exportar` contava `sem_recorte` apenas quando o recorte
**faltava**. Passar o recorte ao RTF zerava o contador: o relatório dizia "nenhum diagrama sem
recorte" sobre um arquivo em que nenhum diagrama tem imagem.

**Solução.** `exportar` distingue "não havia recorte" de "havia e o formato não o carrega", pela
declaração de `pasta_de_imagens` do formato, e o segundo caso vira aviso nomeando o formato.

**Critério de aceite.** RTF com recorte: `sem_recorte == 0` e o aviso "não carrega". Markdown com
recorte: nenhum aviso, e o `.png` no conteúdo.

**Testes.** `test_o_rtf_conta_o_recorte_que_ele_joga_fora` e o par no `.md`.

## S-342 · A janela de busca responde a Enter e a Esc

**Problema.** A caixa de achar e substituir tinha os dois botões e nenhuma tecla. Quem digita o
que procurar e aperta `Enter` -- que é o gesto de toda caixa de busca -- não recebia nada, e para
fechá-la era preciso ir ao X do título.

**Solução.** `Enter` acha e `Esc` fecha, ligados no `Toplevel` inteiro: a lista e a caixa de
substituir também recebem foco, e uma tecla que funciona num widget e não no vizinho é pior que
nenhuma. **`Enter` não substitui**, e isso é a regra 2 desta revisão: trocar cento e vinte
ocorrências é a ação destrutiva desta janela, e ela continua exigindo o botão.

**Critério de aceite.** `Enter` enche a lista sem alterar o texto; `Esc` destrói a janela.

**Testes.** `JanelaDeBuscaTests`, quatro casos.

## S-343 · Um comando por rótulo

**Problema.** Dois pares de comandos com rótulo próprio faziam exatamente a mesma coisa.
`salvar_texto` e `salvar_texto_como` chamavam o mesmo método, que **sempre** abre o diálogo: num
ciclo de correção em que se grava a cada trecho conferido, o diálogo repetido é o atrito, e o
rótulo "como…" prometia uma escolha que o outro tomava igual. E `substituir` e `substituir_todos`
abriam a mesma janela -- o segundo prometendo uma troca em massa que ele não fazia.

**Solução.** "Salvar" grava no arquivo já escolhido e só pergunta na primeira vez; "Salvar como…"
pergunta sempre e passa a gravar no novo caminho; abrir um `.cvtxt` adota o caminho dele, e
documento novo o zera. `substituir_todos` sai do menu e do mapa da aba e passa a ser declarado em
`comandos.NA_JANELA_DE_BUSCA`: ele é o **botão** de dentro da janela de busca, e precisa da lista
de ocorrências que só existe ali. A paleta o mostra com o motivo, como já faz com os três da
linha de campo.

**Critério de aceite.** A segunda gravação não pergunta; "Salvar como…" pergunta sempre; a
varredura de alcance da S-233 continua verde com o comando fora do menu.

**Testes.** `SalvarEUmCaminhoSoTests`, três casos, mais as quatro guardas de alcance atualizadas.

## S-344 · A barra de formato acompanha o cursor

**Problema.** Os interruptores de formato seguiam `<<Selection>>`, o clique e as **duas setas
laterais**. O cursor anda de mais seis maneiras: `↑`, `↓`, `Home`, `End`, `PgUp` e `PgDn`. Descer
uma linha de um título para a prosa deixava "Título" aceso, e o clique seguinte no botão decidia
pelo estado errado.

**Solução.** As seis teclas entram na mesma lista de gatilhos. `KeyRelease` e não `KeyPress`,
porque o cursor só está no lugar novo depois que a classe `Text` tratou a tecla.

**Critério de aceite.** As seis sequências estão ligadas no widget de texto.

**Testes.** `BarraDeFormatoSegueOCursorTests`.

## S-345 · A gravação por inatividade dispara com o motor ligado

**Problema.** `_agendar_gravacao` cancela o prazo pendente e marca outro a cada chamada -- que é o
que "gravar depois da inatividade" quer dizer. Com a análise contínua ligada, o motor escreve
`[%eval ...]` no lance a cada ~800 ms e cada escrita passava por ali: o prazo **nunca vencia**, e
a sala nunca chegava ao disco enquanto o motor estivesse ligado. Quem estuda com a análise
contínua -- que é o modo em que ela existe para ser usada -- ficava com o arquivo parado no estado
de antes de ligar o motor.

**Solução.** A inatividade é a do **humano**. `_marcar_sujo(da_maquina=True)` -- só a avaliação do
motor -- entra na sala e no arquivo da próxima gravação sem adiar a que já está marcada; sem
nenhuma marcada, ela marca uma, senão a avaliação de um estudo que ninguém mais tocasse não
chegaria ao disco.

**Critério de aceite.** Depois de uma edição de gente, uma escrita do motor não troca o
identificador do `after` pendente; outra edição de gente troca.

**Testes.** `GravacaoPorInatividadeTests`, três casos.

## S-346 · Virar o tabuleiro é vista, e o PGN é gravado inteiro

**Problema.** Dois achados da mesma sala.

`flip_board` chamava `_marcar_sujo()`, que soma um em `_edicao` -- e é `_edicao` que diz a
`ui/desfazivel.py` **qual painel** recebe o `Ctrl+Z`. A orientação não está no PGN, então
`registrar` devolvia `False` e nada entrava na pilha: virar o tabuleiro sequestrava a tecla, não
desfazia nada, e a edição real de quem estava no editor ao lado ficava sem quem a desfizesse.

E `write_pgn` sobrescrevia com `write_text`, que trunca antes de escrever: interrompido no meio,
ele deixa zero byte no lugar de um PGN que é análise salva de outro dia. A exportação desta mesma
aba passa por `atomic_io` desde a S-254, e a gravação da sala também.

**Solução.** Virar o tabuleiro é `_marcar_sujo(historico=False)` -- continua sujando a sala,
porque `invertido` é gravado com o estudo, e continua empurrando o prazo de gravação, porque é
gesto de gente. E a sobrescrita do PGN passa por `atomic_write_text`; acrescentar continua sendo
um `append`, e a diferença é o modo de falha: ele nunca trunca.

**Critério de aceite.** Virar não muda `edicao` e muda `invertido`. Sobrescrever passa por
`atomic_write_text`; acrescentar preserva o que estava no arquivo. `ui/study_panel.py` saiu da
lista `PERMITIDAS` de `tests/test_atomic_writes.py`.

**Testes.** `VirarTabuleiroTests` e `PgnAtomicoTests`, dois casos cada.

## S-347 · Quatro promessas da sala

**Problema.** Quatro achados pequenos, e cada um é uma coisa que a sala **diz** e não faz.

1. **O comentário da raiz saía duas vezes** em todo `.md`, `.html` e `.rtf`: como parágrafo
   próprio, abaixo da FEN, e outra vez grudado no primeiro lance -- "uma nota da raiz 1. e4" --,
   porque `notacao_do_estudo` não filtrava o comentário de caminho vazio.
2. **`estudo_aberto` era gravado no `AppState` e nunca lido.** O campo existe desde a S-271 com o
   docstring certo -- "voltar ao livro sem voltar ao diagrama devolveria a pessoa à porta da sala
   em vez de à mesa em que ela estava" -- e era exatamente isso que acontecia.
3. **A confirmação de apagar contava a linha principal**, não a subárvore: `len(list(
   no.mainline())) + 1` ignora as subvariantes, e a busca por anotação olhava um nível só. Uma
   variante com sublinhas anotadas anunciava "isto apaga 2 lance(s)" e apagava dezoito.
4. **O botão "Recorte" nunca ficava cinza**, embora a dica prometesse isso desde a S-282 para o
   estudo sem âncora -- e o clique trocava o rótulo para "Esconder recorte" sem nada ter
   aparecido.

**Solução.** (1) `notacao_do_estudo` pula o `COMENTARIO` de caminho vazio: a nota da raiz é sobre
a **posição**, e quem mostra a posição é quem a mostra. (2) `reabrir_por_chave` procura na sala
carregada o estudo daquela chave e abre a mesa; a janela guarda a chave até o livro dela abrir, e
só na **primeira** abertura -- depois disso `estudo_aberto` é o que a pessoa abriu nesta sessão.
(3) `_tamanho_da_subarvore` percorre a subárvore inteira, iterativa porque um estudo longo passa
de mil nós. (4) O botão fica cinza sem âncora, o rótulo não troca, e o clique diz por quê.

**Critério de aceite.** A nota da raiz aparece uma vez; `reabrir_por_chave` volta ao estudo certo
e devolve `False` sem levantar para chave que não existe mais; a contagem inclui as subvariantes e
a anotação de qualquer profundidade; sem âncora o botão está `disabled`.

**Testes.** `ComentarioDaRaizTests` e `ContagemDaSubarvoreTests` em `tests/test_estudo_saida.py`;
`ReabrirAMesaTests` e o par do botão em `tests/test_estudo_aba.py`.

---

# Fase 58 — O texto lido: o que erra e o que custa

Onze achados em dez itens (S-348 a S-357). **Dois já estavam entregues quando a fase chegou**: a
camada pesquisável duplicada saiu na S-303, e a amostragem de negrito e itálico refeita a cada
folha, na S-313 -- as duas na Fase 53, e as duas com a medição registrada lá.

## S-348 · A camada pesquisável duplicada — entregue como [S-303](#s-303--a-camada-invisível-do-pdf-pesquisável-entra-uma-vez-e-não-duas)

## S-349 · Pontuação de borda não é ambiguidade

**Problema.** `dicionario.escolher` recusa corrigir quando **mais de uma** variante é conhecida --
a guarda da ambiguidade, e ela está certa. Só que `conhecida` apara `.,;:!?()[]'"` antes de olhar
o léxico: `black.` e `black,` são a **mesma** resposta do dicionário, e chegavam à guarda como
duas. Uma palavra com o ponto final entre os candidatos da última caixa era recusada por
"ambígua", e a correção era uma só.

**Solução.** A caixa da ambiguidade passa a ser o conjunto dos **núcleos aparados**; um núcleo só
é resposta única. A pontuação que sai é a do **original**, e não a da variante escolhida: o
dicionário decide letra, e trocar `black.` por `black,` seria corrigir o que ninguém pediu.

`Black` e `black` continuam sendo duas respostas -- a comparação é sem `casefold`, de propósito.

**Critério de aceite.** `blaek.` com `.`/`,` entre os candidatos devolve `black.`; `black`/`block`
continua devolvendo `None`.

**Testes.** `PontuacaoNaoEAmbiguidadeTests`, quatro casos.

## S-350 · O pingo procura a base numa janela

**Problema.** `unir_pingos` comparava cada caixa curta com **toda** caixa da folha, e a
comparação começava pela parte cara: `_inclinacao_da_haste` recorta a imagem binária da base para
medir o traço do itálico. Numa folha de duas mil caixas isso é duas mil recortadas por pingo --
quase todas a linhas de distância dele, e todas recusadas depois pelo vão.

**Solução.** Três mudanças, e nenhuma muda a decisão:

- o teste de **vão** (aritmética pura) vem antes do recorte;
- as bases plausíveis saem de duas listas ordenadas por `y1` e `y2`, com busca binária: o pingo
  só se une a quem está a `vao_maximo` dele, acima ou abaixo;
- a janela horizontal é **provada**, e não estimada: `pendor` vive em `[-1, 1]` e `HASTE_ESTREITA`
  garante `largura/altura <= 0,5`, então `|inclinacao| <= 1` e o deslocamento do itálico nunca
  passa de `vao_maximo`.

E o índice da base escolhida passou a ser guardado em vez de reprocurado com `caixas.index(base)`
-- busca linear que, com duas caixas iguais, achava a **primeira** e não a que o pingo escolheu.

**Medido** numa folha sintética de 2.120 caixas com 120 pingos, com imagem binária:

```
antes   133 ms
depois    4,1 ms        os mesmos 120 pingos unidos
```

**Critério de aceite.** O mesmo conjunto de uniões, e a medição da inclinação só nas bases
vizinhas do pingo.

**Testes.** `JanelaDosPingosTests`, dois casos -- um de resultado, um com espião sobre
`_inclinacao_da_haste`.

## S-351 · Uma abertura de documento por folha

**Problema.** `ler_pagina` recebia o **caminho** do PDF e o entregava a três clientes que abrem o
documento cada um: `render_pdf_page`, a leitura da camada e o detector de diagramas. Três
aberturas por folha, numa varredura de 402 páginas.

**Solução.** `opened(pdf_source)` uma vez no topo, e o `OpenPdf` desce para os três. O empréstimo
existe desde a S-61 exatamente para isto e nunca havia chegado ao caminho de texto; é reentrante,
então quem já chega com um documento aberto não paga nada.

**Critério de aceite.** `pdf_io.open_count()` sobe **um** por `ler_pagina`. Medido também num
livro real: 1 abertura, contra as 3 de antes.

**Testes.** `UmaAberturaPorFolhaTests`.

## S-352 · A folha é rasterizada uma vez por leitura

**Problema.** A aba de texto lia a folha numa thread -- `ler_pagina` sem `imagem_rgb`, então ela
rasterizava a página -- e, quando o resultado voltava, `_chegou` rasterizava **a mesma folha de
novo** para as miniaturas. A segunda rasterização roda na thread da janela: ~355 ms de interface
congelada a cada leitura.

**Solução.** A rasterização acontece uma vez, na thread de trabalho, e a imagem viaja com a
página lida: `ler_pagina(imagem_rgb=imagem)` e `_chegou(pagina, imagem, ...)`.

**Critério de aceite.** `_chegou` guarda a imagem que recebeu e não chama `_renderizar`.

**Testes.** `UmaRasterizacaoPorLeituraTests`, dois casos.

## S-353 · A hifenizada da quebra de linha é juntada

**Problema.** `lexico.juntar_hifenizadas` existe desde a S-209, com as três condições medidas --
6 de 6 junções certas, e as 2 que não devem juntar recusadas --, e **nenhum caminho a chamava**.
O texto lido saía `devel- opment` em toda folha em que a diagramação partiu uma palavra. É o
mesmo caso do `validar` na S-208 e do `recortes=` na S-338: a peça estava pronta e faltava a
pergunta.

**Solução.** `montar` recebe o léxico e junta **dentro do parágrafo**, que é onde a quebra de
linha acontece -- a última linha de um parágrafo não continua na primeira do seguinte, e juntar
através da fronteira casaria `Xue-` com o `Fierro` do parágrafo de baixo. A bbox de cada linha
não muda: ela é a geometria do que foi impresso.

Léxico vazio -- ou `dicionario=False` -- não junta nada, que é o comportamento de antes.

**Critério de aceite.** `a nice devel-` + `opment for white` vira `a nice development` +
`for white`; `Xue-` + `Fierro` sobrevive.

**Testes.** `HifenDaQuebraTests`, três casos.

## S-354 · O diagrama que atravessa a calha quebra as duas colunas

**Problema.** `sequencia_de_leitura` trata o elemento transversal desde a S-193 -- tudo o que
está acima dele sai primeiro, depois ele, depois o resto. `montar` então remonta a página **por
coluna**, e ali a regra se perdia: a coluna do diagrama saía de `atribuir_coluna`, que decide
pelo **centro** -- e o centro de um diagrama largo cai dentro da calha, então a coluna era um
desempate de proximidade, esquerda ou direita conforme um pixel. A tira da outra coluna continuava
aberta, e o parágrafo de cima se juntava ao de baixo.

**Solução.** Diagrama que `colunas.atravessa` fecha a tira corrente de **todas** as colunas, e a
coluna dele passa a ser a primeira que ele cobre -- determinística, e a que a leitura alcança
antes.

**O que este item não resolve, e fica registrado:** a `PaginaLida` é uma sequência de colunas, e
não sabe dizer "este bloco não é de coluna nenhuma". Um transversal continua morando numa delas;
o que ele deixou de fazer é juntar parágrafos através de si.

**Critério de aceite.** Com um diagrama cobrindo as duas colunas, nenhuma delas tem parágrafo com
linhas de antes **e** de depois dele.

**Testes.** `test_o_diagrama_que_atravessa_a_calha_fecha_as_duas_colunas`.

## S-355 · A fila de rótulos só sai quando há diagrama perto

**Problema.** `e_fila_de_eixo` é estrutural de propósito -- rótulos de um caractere, do alfabeto
do tabuleiro, distintos --, e é isso que a faz aceitar `1 2 3 4 5 6 7 8`: oito rótulos, todos
distintos. Essa é a linha de cabeçalho de toda tabela de torneio de oito rodadas, e ela era
apagada da página **em silêncio**, sem nada no texto dizendo que faltava uma linha.

**Solução.** Rótulo de eixo é borda de tabuleiro, e borda de tabuleiro fica encostada num
tabuleiro: a fila só sai quando está a duas alturas de linha de um diagrama detectado, com o
centro dela dentro da faixa horizontal dele. Sem diagrama na folha, nada é apagado -- que é a
resposta certa para "não sei onde estão os tabuleiros".

**Critério de aceite.** A mesma fila é apagada junto de um diagrama e preservada longe dele.

**Testes.** `test_a_fila_so_sai_quando_ha_diagrama_perto` e `test_sem_diagrama_nenhum_nada_e_apagado`.

## S-356 · Cabeçalho e rodapé são da camada

**Problema.** `_margens` carimbava as duas linhas com a procedência do **motor da página**: numa
folha lida pelo glifo, o cabeçalho saía marcado como "glifo". Mas ele vem de
`pdf_text.page_margin_lines`, que lê a camada de texto do PDF -- sempre, inclusive nessa folha.

Procedência é a resposta a "de onde veio este texto?", e a interface pinta as duas diferente de
propósito: dizer que o cabeçalho foi **reconhecido** quando ele foi **lido** é a mesma classe de
erro que a S-04 fechou nos rótulos.

**Solução.** `camada`, sempre, com o porquê no docstring. O parâmetro saiu da assinatura: ele só
podia estar errado.

**Critério de aceite.** `_margens` devolve procedência `camada` para as duas linhas.

**Testes.** `MargemVemDaCamadaTests`.

## S-357 · Léxico vazio desliga a conferência

**Problema.** `desconhecidas` pergunta `conhecida(palavra, lexico)` para cada token, e o conjunto
vazio responde `False` para todos: **a folha inteira saía sublinhada**. E o caso não é hipotético
-- é o de um clone sem `assets/lexico/`, onde `carregar` devolve o conjunto vazio de propósito
("ausente não é erro").

**Solução.** Sem lista, a conferência não acende. É a mesma regra que `escolher` e
`juntar_hifenizadas` já seguiam, aplicada à terceira porta do módulo.

**Critério de aceite.** `desconhecidas(texto, frozenset())` devolve `()`; com lista, continua
apontando.

**Testes.** `LexicoVazioDesligaTests`, dois casos.

---

# Fase 59 — O núcleo, revisitado

Sete achados, seis itens (S-358 a S-364) e **um refutado**.

## S-358 · A busca sujeita às regras tem prazo

**Problema.** `decode_constrained` tem teto de **expansões** (5.000) e nenhum de tempo. Num
tabuleiro legal ela nem começa -- o argmax já satisfaz as regras, ~0,1 ms --, e num tabuleiro
ilegal ela gasta as cinco mil para no fim admitir que não achou. Medido aqui, com rei branco como
argmax nas 64 casas: **3,5 s**. E `predict_with_orientation` lê a 0° e a 180°, então são sete
segundos de janela parada num diagrama que vai ser recusado de qualquer jeito.

**Solução.** `max_seconds=0.5`, conferido a cada 64 expansões -- `time.monotonic` custa ~50 ns e
o corpo do laço custa pouco mais que isso, então perguntar as horas cinco mil vezes seria pagar
pelo cronômetro o que se quer economizar na busca.

Meio segundo é quatro mil vezes o caso normal e sete vezes menos que o pior medido: nenhum reparo
que hoje termina é cortado por ele.

**Critério de aceite.** O tabuleiro de 3,5 s termina dentro do prazo, com
`constraints_satisfied=False`; o legal continua saindo sem troca nenhuma.

**Testes.** `PrazoDaBuscaTests`, três casos.

## S-359 · A lápide do candidato removido é `None`

**Problema.** Quando um contorno vence uma união de ladrilhos, o candidato embutido sai da lista e
a caixa dele era marcada com a sentinela `(0, 0, 1, 1)`. Só que **uma sentinela em forma de caixa
continua sendo uma caixa**: `_same_region` a compara como tal, e qualquer contorno ancorado na
origem da página volta a "casar" com ela -- e ancorado na origem não é caso raro, é a moldura da
página inteira. O `candidates.remove` seguinte levantaria sobre um candidato que já não está lá.

**Solução.** `None` é a lápide, e a busca por conflito pula quem já saiu. O prior de tamanho
também passou a ignorar as lápides.

**Critério de aceite.** `mypy` obriga o `None` a ser tratado nos dois pontos que leem a lista;
nenhum contorno casa com um candidato removido.

## S-360 · A `SingleLegalRule` que não dispara — **refutado**

**O achado.** Com `CONSTRAINED_DECODING` ligado, a regra de legalidade da cascata de orientação
nunca decide: a decodificação repara a leitura **antes** de a legalidade ser consultada, e as duas
orientações chegam legais.

**Por que ele cai.** O comportamento é deliberado, medido e **está afirmado por teste**:
`test_constrained_decoding_makes_legality_a_rare_but_harmless_tiebreak` documenta que o filtro
decide em 52 dos 320 tabuleiros do split de teste e que o sinal não se perde -- a casa reparada
fica com a confiança real dela, que é baixa, e a margem de confiança decide a mesma orientação.
"Ligar a S-11 transfere o sinal de ilegalidade para a confiança em vez de perdê-lo, e o veredito
não muda."

A tentativa de conserto foi escrita e desfeita: perguntar a legalidade ao `DecodeResult` -- "esta
leitura precisou de reparo?" -- faz a regra voltar a disparar, e derruba o teste que declara a
decisão. Trocar uma decisão medida por uma não medida não é conserto.

## S-361 · Caractere desconhecido na FEN levanta

**Problema.** `labels_from_fen` fazia `PIECE_TO_IDX.get(peca, PIECE_TO_IDX["empty"])`: qualquer
caractere fora do alfabeto de peça -- um `X` da leitura, uma figurina Unicode -- virava **casa
vazia**, silenciosamente. O pior cliente disso é a segunda opinião: as duas leituras viravam
`empty` na mesma casa e ela anunciava **acordo total** sobre um tabuleiro que nenhuma das duas
leu.

**Solução.** `ValueError` nomeando o caractere e listando os válidos. FEN válida não passa por
aqui: `PIECE_TO_IDX` tem exatamente as doze peças, e o dígito já foi expandido.

**Critério de aceite.** `4k3/.../4X3` levanta nomeando o `X`; a FEN válida continua devolvendo 64
rótulos.

**Testes.** `FenComCaractereEstranhoTests`, três casos.

## S-362 · O teto da página corta o pior, e avisa

**Problema.** Duas coisas na mesma linha. O corte por `max_boards` era aplicado **depois** da
ordenação de leitura: numa página de treze diagramas com teto de doze, o que sumia era o último a
ser lido -- o do canto inferior direito --, e não o de menor score. E era a única recusa sem nada
no log, enquanto `detect_boards` avisa desde a Fase 5.

**Solução.** A seleção é por score; a ordem de leitura continua sendo a da saída, e só deixou de
decidir *quem* fica. O aviso é o mesmo do irmão, com os scores cortados e o do último aceito.

**Critério de aceite.** Numa página em que o pior candidato é o primeiro a ser lido, é ele que
sai. O `rejected` continua recebendo os cortados com o motivo `teto-da-pagina`.

**Testes.** `TetoDaPaginaTests`.

## S-363 · Os quatro cantos do quad, sem repetir

**Problema.** `order_quad_points` ordenava por soma e diferença das coordenadas -- regra que
funciona para quadrilátero de pé e **quebra no quad a 45°**. Num losango de vértices
`(100,0) (200,100) (100,200) (0,100)` o mesmo ponto ganha `argmin(soma)` e `argmin(diferença)`: a
saída tinha três cantos, um repetido, e `getPerspectiveTransform` sobre isso é uma matriz sem
sentido. É justamente o candidato torto que a geometria mais precisa julgar.

**Solução.** Ângulo em torno do centro: quatro pontos distintos de um quadrilátero convexo têm
quatro ângulos distintos. Com `y` crescendo para baixo, o sentido do ângulo crescente é o horário,
que é a ordem que `warp_from_quad` espera; o `roll` só escolhe por onde começar -- o canto de
menor soma, o mesmo critério de superior-esquerdo de antes.

**Critério de aceite.** O losango sai com quatro cantos distintos, e o retângulo sai exatamente na
ordem de antes -- afirmado com os pontos em ordem e fora de ordem.

**Testes.** `QuadA45GrausTests`, três casos.

## S-364 · O censo de recusas grava o contraste que ele mediu

**Problema.** Duas recusas do `hybrid` gravavam `checker=0.0` num ponto em que o recorte **está na
mão**: `perdeu-para-embutido` e `prior-de-tamanho`. E `RejectedQuad.checker` documenta o zero como
"a recusa foi antes de haver recorte" -- então o censo de recusas afirmava que aqueles candidatos
não tinham contraste nenhum, o que é uma afirmação, e falsa.

**Solução.** `board_checker_contrast(board_rgb)` nos dois, como a recusa `faixa-da-pagina` já
fazia quinze linhas acima.

**Critério de aceite.** Nenhuma recusa com recorte disponível grava zero.

---

# Fase 62 — O que sai no `.exe`

Sete achados, seis itens (S-386 a S-391) e **um refutado na segunda passada** -- o extra `onnx`,
que a revisão já registrou: quem importa `onnx` é o exportador do próprio torch, e removê-lo
teria quebrado a S-30.

## Números aposentados: esta fase saiu numerada como S-365 a S-370

O commit `c76b240` entregou a Fase 62 com os números **S-365 a S-370**, e três deles já eram da
Fase 60: `S-368` (a poda do `splits.csv`), `S-369` (o `best_epoch`) e `S-370` (a métrica de outro
nome, que o `training.py` cita). Duas seções com o mesmo `S-NNN` não são um detalhe de arquivo --
a tabela *"Onde mora a spec de cada item"* mapeia número para documento, e um número que aponta
para dois lugares é exatamente o furo que a S-134 existe para tapar.

O conserto foi mover **esta** fase, e não a de lá: a Fase 60 já estava numerada segundo a reserva
do roadmap, e a 62 é que tinha ido buscar o primeiro número livre depois da Fase 59. A reserva
dizia S-386 em diante desde o commit `1ea8f3d`, e é onde ela está agora. As três linhas abaixo
ficam porque `tests/test_docs.py` lê os **assuntos dos commits**: o `c76b240` continua dizendo
"S-365 a S-370" no histórico, e histórico não se reescreve depois de empurrado.

## S-365 · Renumerado para [S-386](#s-386--o-pandas-sai-das-dependências-obrigatórias)

## S-366 · Renumerado para [S-387](#s-387--95-mb-que-ninguém-declarou)

## S-367 · Renumerado para [S-388](#s-388--o-exe-leva-os-três-modelos-ou-diz-o-que-falta)

## S-386 · O `pandas` sai das dependências obrigatórias

**Problema.** `pandas` era dependência obrigatória e **nenhum módulo de produção o importa**.
Quem o importa são quatro arquivos de teste, que o usam como segunda régua do CSV de rótulos --
"o que sai daqui é byte a byte igual ao que o pandas escreveria". Como obrigatório, ele viajava
dentro do `.exe`, e o bundle é o lugar onde peso custa.

**Solução.** Para o extra `dev`, ao lado do `pandas-stubs` que já estava lá. A CI instala
`--extra dev`, então a suíte não muda.

**Critério de aceite.** `dependencies` não tem `pandas`; `dev` tem; nenhum arquivo de
`src/chess_diagram_ocr/` o importa -- e essa última é a guarda que impede a volta.

**Testes.** `DependenciasDoBundleTests`, três casos.

## S-387 · 95 MB que ninguém declarou

**Problema.** `scipy` e `scikit-image` entravam no bundle sem constar de dependência nenhuma:
eles vêm no ambiente por causa do clone de `tsoj/Chess_diagram_to_FEN`, que é a segunda opinião
**local** da S-66. O PyInstaller coleta o que está **instalado**, e não o que o `pyproject.toml`
declara -- é o mesmo modo de falha que a S-137 mediu com o `pythonnet`, com dois zeros a mais.

**Solução.** Os dois entram em `excludes`. A segunda opinião local exige clonar um repositório de
terceiro e baixar 232 MiB de pesos: não é caminho de executável, e agora `tsoj_reader` **diz
isso** em pt-BR quando alguém tenta a opção no `.exe`, em vez de deixar aparecer um
`No module named 'skimage'`.

**Critério de aceite.** `excludes` nomeia os dois; a mensagem do congelado nomeia a razão.

**Testes.** `test_o_que_nao_e_dependencia_nao_entra_no_bundle`.

## S-388 · O `.exe` leva os três modelos, ou diz o que falta

**Problema.** O motor `glifo` precisa dos pesos **e** do metadado -- `carregar_classificador` acha
o `.pt` ao lado do `char_meta.json` --, e `copiar_checkpoint` copiava só `piece_classifier.pt`.
No `.exe`, a aba Texto oferecia o motor `glifo` na caixa e ele nunca subia, nem com os pesos
postos à mão em `models/`.

**Solução.** `MODELOS_QUE_ACOMPANHAM` declara os três e **a consequência de cada ausência**, e o
build avisa nomeando o que falta. Continuam ao lado do executável, e não dentro: um modelo
embutido seria o único que um retreino não consegue trocar.

**Critério de aceite.** Os três estão declarados, na ordem, e cada um com o motivo escrito.

**Testes.** `ModelosAoLadoDoExecutavelTests`.

## S-389 · O log rotaciona, e sem console não há handler de console

**Problema.** Dois defeitos no mesmo arquivo.

`logs/chessvisionoff.log` **crescia para sempre**: o handler é `FileHandler`, o arquivo grava em
DEBUG por decisão da S-126, e DEBUG num programa que lê 402 páginas são dezenas de MB por sessão.

E o bundle da S-55 monta o `.exe` com `console=False`: ali `sys.stderr` é `None`, o
`StreamHandler` nasce sem fluxo e **falha a cada registro** -- o logging tenta escrever o
"--- Logging error ---" no fluxo que não existe, e o que se vê é nada. O arquivo continuava
recebendo, então o defeito era invisível e custava uma exceção por linha de log.

**Solução.** `RotatingFileHandler` com 2 MB e cinco arquivos guardados -- a sessão de ontem cabe e
o disco tem teto --, e o handler de console só é criado quando há `sys.stderr`.

**Critério de aceite.** Um handler rotativo com teto e cópias; nenhum `StreamHandler` quando
`sys.stderr` é `None`, e um registro nessa condição não levanta.

**Testes.** `LogQueNaoCresceParaSempreTests`, quatro casos.

## S-390 · `CVOFF_LOG_DIR` vale para os quarenta e um comandos

**Problema.** `log_file` era um parâmetro que cada comando tinha de lembrar de passar, e **23 dos
41 não passavam** -- entre eles uma janela Tk. Num checkout isso não muda nada, porque sem
`CVOFF_LOG_DIR` a função devolve `None`; num `.exe`, é a diferença entre ter e não ter rastro,
que é exatamente o modo de falha que a S-127 fechou para o congelado.

**Solução.** Sem `log_file`, `configure_logging` usa `default_log_file()`. Deixa de ser uma
lembrança e passa a ser o padrão -- e um comando novo não pode esquecê-lo.

**Critério de aceite.** `configure_logging()` sem argumento, com `CVOFF_LOG_DIR` posto, abre o
arquivo naquela pasta.

**Testes.** `test_sem_destino_o_padrao_e_o_de_default_log_file`.

## S-391 · O `.spec` é lintado

**Problema.** `packaging/cvoff.spec` **não era visto por nenhuma das duas guardas**: `ruff` e
`mypy` olham `.py`, e o arquivo é `.spec`. E as duas coisas que sugeriam o contrário estavam
escritas: o `# noqa: F821` espalhado pelo arquivo -- que só faz sentido se alguém estiver
lintando -- e o comentário do `[tool.mypy]` dizendo que `packaging/` entrava por causa dele.

**Solução.** `extend-include = ["*.spec"]` no `ruff`, que ao ser ligado achou uma declaração de
encoding obsoleta. O `mypy` fica de fora **com a razão escrita**: o PyInstaller executa o `.spec`
injetando `SPECPATH`, `Analysis`, `EXE` e `COLLECT` como globais -- nomes que não existem em
import nenhum, e que o verificador acusaria um por um.

**Critério de aceite.** `ruff check .` cobre o `.spec` e passa.

**Testes.** `test_o_spec_e_lintado`.

---

# Fase 63 — A cor, o foco e a tecla

Doze itens (S-392 a S-403). Três superfícies fora do sistema de cor da S-144, onze diálogos que
não fecham com `Esc`, um modo sem estado visível, quatro teclas que iam para a aba errada, nove
caixas chamadas "Erro" e duas implementações de dica com tempos diferentes.

**O que junta esta fase não é o assunto, é a distância entre o defeito e quem o sofre.** Nenhum
destes doze aparece num teste que falha nem num log: o que eles produzem é um usuário que não sabe
em que estado está, aperta a tecla e não vê nada acontecer, ou vê acontecer noutra aba.

## S-392 · Mensagem de exceção também é interface

**Problema.** A guarda de acentuação da S-146 varre `ui/`, e o texto que um `raise` de módulo de
produto carrega **chega à tela pelos mesmos dois caminhos**: a caixa de erro da janela, que mostra
`str(exc)`, e o `cli_errors` da S-126. "Selecao vazia: o retangulo escolhido nao cobre nenhum
pixel" era o que a janela mostrava a quem arrastava um retângulo vazio -- e a guarda que existe
justamente para isso passava em verde, porque olhava a pasta errada.

**Solução.** A varredura passa a ler o `ast.Raise` de todo módulo de `src/chess_diagram_ocr/`
fora de `ui/` e de `cli/`, e cobra as mesmas palavras. `cli/` fica de fora com a razão escrita: ali
o texto é de terminal, e a convenção do projeto -- a mesma do README -- é escrevê-lo sem acento.
Dez mensagens foram corrigidas em nove módulos.

**Critério de aceite.** Nenhuma mensagem de `raise` fora de `ui/` e `cli/` usa forma sem acento.

**Testes.** `test_nenhuma_excecao_de_produto_usa_forma_sem_acento`.

## S-393 · A mensagem do rodapé é repintada com o tema

**Problema.** O rodapé escolhe a cor da mensagem conforme a severidade -- erro em vermelho, aviso
em âmbar -- e escrevia essa cor **uma vez**, na hora de mostrar. A troca de pele repinta o cromo
inteiro (S-144) e não tocava nela: um erro escrito sob a pele clara continuava preto sobre o cromo
escuro depois da troca, com razão de contraste medida em 1,30:1 -- abaixo dos 4,5:1 que a S-144
exige de todo texto.

**Solução.** O rodapé guarda a **severidade** da mensagem em vigor, e não a cor. `theme.ao_repintar`
recebe uma função que reescreve a cor a partir do token -- é o mesmo par que o canvas da Galeria
passou a usar na S-394, e o mesmo de `board_widget` desde a S-147.

**Critério de aceite.** Trocar de tema com uma mensagem de erro na tela repinta a mensagem.

**Testes.** `RodapeSegueOTemaTests`.

## S-394 · O canvas da Galeria entra no sistema de cor

**Problema.** Era o **único canvas do pacote `ui/` fora da S-144**: nascia com o fundo de fábrica
do Tk e escrevia "sem recorte" num `#888` cravado -- o único hexadecimal literal do pacote. Sob a
pele escura, um retângulo branco no meio da janela.

**Solução.** `bg=theme.cor_atual(tokens.SUPERFICIE_TABULEIRO)` mais `theme.ao_repintar`, e o aviso
passa a `tokens.TEXTO_SECUNDARIO`. É o que o `ui/board_widget.py` -- o canvas irmão -- faz desde a
S-147.

**Critério de aceite.** Nenhum literal de cor sobra em `ui/gallery_panel.py`, e o fundo acompanha a
troca de tema.

**Testes.** `CanvasSegueOPapelTests`, `test_nenhum_modulo_de_ui_crava_cor`.

## S-395 · Onze diálogos passam a fechar com `Esc`

**Problema.** Catorze janelas de diálogo, e **onze não fechavam com `Esc`** -- inclusive a legenda
de atalhos, que é a janela que mais se abre e a que menos tem o que consentir. `Esc` é a saída
que todo diálogo tem em todo programa: sem ela, a única porta é achar o botão de fechar.

**Solução.** `<Escape>` ligado a fechar em cada uma delas, e **em nenhuma ele aplica**: sair sem
consentir é sempre a resposta segura. Nos dois diálogos que promovem uma candidata, `Esc` faz o
que o botão *Cancelar* faz.

**Critério de aceite.** Toda `Toplevel` de diálogo do pacote liga `<Escape>`.

**Testes.** `test_todo_dialogo_fecha_com_esc`.

## S-396 · "Selecionar área" mostra o modo nas três peles

**Problema.** `selecionar_area` é um **modo**: o primeiro clique liga o arrasto sobre a folha e o
segundo desliga. Só a pele clássica dizia isso -- o botão dela troca para "Cancelar seleção" desde
a S-222. As outras duas criam os controles da barra do painel **e não os empacotam** (é o que a
S-223 escolheu de propósito), então o texto trocado ia para uma barra que a pele não mostra:
ligar e desligar tinham o mesmo aspecto, e o único jeito de saber em que estado se estava era
arrastar o mouse sobre a página e ver o que acontecia.

**Solução.** O catálogo ganha um canal de duas funções: `ao_alternar(acao, aplicar)` registra quem
desenha aquele comando, e `alternou(acao, ligado=...)` avisa. Quem vira o modo avisa -- o painel de
PDF em `toggle_area_selection`/`disable_area_selection`, a sala de estudo em `_pintar_alternavel` --
e quem o desenha segue: a fita e a pílula da fila. Recebe **texto e não widget** porque `comandos`
é o catálogo e não importa `tkinter`; esquece o que morreu, com a mesma disciplina de
`theme.repintar`.

**Critério de aceite.** `alternou("selecionar_area", ligado=True)` troca o texto do botão da fita;
ligar e desligar pelo painel avisam; a fita remontada não carrega o seguidor da anterior.

**Testes.** `tests/test_ui_modo_selecionar_area.py` (13).

## S-397 · `_focus_result_tab` nunca funcionou

**Problema.** `left_tabs.select(self.result_panel)` levanta sempre: **o painel de resultado não é
aba do `Notebook`** -- quem é é o `rolagem.aba_rolavel` que o hospeda desde a S-150. O `TclError`
caía num `logger.debug`, então clicar num diagrama da página selecionava o diagrama e não trazia a
aba, sem nada dizer por quê.

**Solução.** `rolagem.selecionar_aba(self.left_tabs, abas.RESULTADO)`, que é o mesmo caminho que a
restauração de estado usa desde a S-156: ele acha a aba pelo **rótulo**, que é o que sobrevive à
moldura de rolagem.

**Critério de aceite.** Pedir o foco da aba Resultado a traz para a frente.

**Testes.** `test_focar_a_aba_de_resultado_a_traz_para_a_frente`.

## S-398 · A contagem das abas é refeita depois da varredura

**Problema.** Os rótulos das abas trazem contagens (S-152), e a varredura do livro é **o gesto que
as muda**: ela é quem confirma diagramas em bloco. Nada as refazia depois dela -- a aba dizia o
número de antes até o próximo gesto que por acaso chamasse `_atualizar_abas`.

**Solução.** `_reload_confirmed_diagrams` passa a atualizá-las, e é o lugar certo: ela é chamada
por todo caminho que muda o conjunto de confirmados, e não só pela varredura.

**Critério de aceite.** Depois de varrer, o rótulo da aba traz a contagem nova.

**Testes.** `test_a_varredura_atualiza_a_contagem_das_abas`.

## S-399 · A troca de pele não vaza barra nem esquece o regime

**Problema.** Dois defeitos do mesmo gesto. `menu.montar` pendurava uma barra de menus nova a cada
troca de pele e **nunca destruía a anterior**: cada troca deixava uma `Menu` inteira viva, com os
`Menu` filhos de todos os grupos. E a linha do conjunto de campo é refeita na remontagem, o que
recriava o `StringVar` do regime -- a escolha de quem estava anotando `scan` voltava ao primeiro
da lista, em silêncio, no meio do trabalho.

**Solução.** A barra anterior é destruída antes de a nova ser pendurada; o `StringVar` do regime
nasce com a janela (`__init__`), e a linha só liga o widget novo a ele. É a mesma regra que o
`pdf_panel` já cumpria: **o cromo é refeito, o estado não**.

**Critério de aceite.** Trocar de pele três vezes não deixa barra órfã, e o regime escolhido
sobrevive à troca.

**Testes.** `test_a_barra_anterior_e_destruida`, `test_o_regime_sobrevive_a_troca_de_pele`.

## S-400 · A Galeria ganha as teclas que os botões dela já tinham

**Problema.** A Galeria tem os quatro botões de navegação desde a S-88 e **nenhuma tecla chegava a
eles**. Pior: `←` e `→` são "diagrama anterior/próximo" da janela inteira, e com a Galeria aberta
eles continuavam mexendo no diagrama do **painel de resultado** -- que não está na tela. É o mesmo
defeito que a S-281 mediu na sala de estudo, sem nada visível para denunciá-lo: percorrer a galeria
com a seta trocava, invisivelmente, o que o `Ctrl+S` seguinte gravaria.

**Solução.** A aba declara as quatro ações como suas (`acoes_proprias`/`atender`, a fundação da
S-244) e ganha o foco ao ser mapeada, como a sala desde a S-281. Não são teclas novas: é a mesma
tecla com destino conforme o foco. Enquanto o cursor está num campo -- o lance, os oito headers, a
legenda selecionável -- a declaração é vazia, e `←` volta a ser do campo.

**Critério de aceite.** `atalhos.conferir_dono` passa para a Galeria; as quatro teclas andam nela e
não no painel de resultado.

**Testes.** `TecladoDaGaleriaTests` (5).

## S-401 · Toda caixa de diálogo nomeia a operação

**Problema.** **Nove das trinta e nove caixas se chamavam "Erro"**, contra trinta que já nomeavam
o gesto. O título é a primeira linha que se lê e muitas vezes a única: *"Erro / Falha ao renderizar
página"* diz duas vezes que houve falha e nenhuma vez qual gesto a produziu. Com três abas abertas
e duas operações em curso, é o título que diz a qual delas responder -- o `messagebox` do Tk não
põe o nome do painel em lugar nenhum.

**Solução.** As nove passam a nomear a operação: "Abrir PDF", "Ler o diagrama", "Mostrar a página",
"Aplicar a FEN", "Salvar PGN", "Exportar o estudo", "Abrir imagem". E uma guarda de varredura
recusa o título genérico, na mesma classe da S-161 e da S-324: o que a janela mostra é declarado
num lugar e conferido de fora.

**Critério de aceite.** Nenhuma das sete chamadas de `messagebox` em `ui/` e no `app_tkinter` tem
título genérico ou vazio.

**Testes.** `TituloDeCaixaTests` (3).

## S-402 · O `after` da dica morre com o widget

**Problema.** `Tooltip` agenda a dica com `after(450)` e cancelava esse agendamento ao sair do
widget e ao clicar -- **e não quando o widget morre**. Sair de uma barra que a troca de pele
destrói no mesmo gesto deixava um relógio marcado para um widget que não existe mais: `_show`
acordava, pedia `winfo_rootx` e o `TclError` subia pelo `report_callback_exception` do Tk, que é um
traceback na saída padrão do programa. O mesmo valia para a dica do tabuleiro.

**Solução.** `<Destroy>` ligado a esquecer o agendamento, nos dois. **Só o próprio widget conta**:
`<Destroy>` sobe dos filhos, e a caixinha da dica é filha do widget -- tratar a morte dela como a
dele apagaria a dica no instante em que aparecesse. E não se destrói a `Toplevel`: ela é filha de
quem está morrendo, e o Tk já a leva junto.

**Critério de aceite.** Destruir o widget com uma dica agendada cancela o agendamento, e nada chega
ao `report_callback_exception`.

**Testes.** `DicaAgendadaMorreComOWidgetTests` (3).

## S-403 · Uma dica só, com um tempo só

**Problema.** Duas implementações de dica na mesma janela: a de `ui/tooltip.py`, que explica um
controle, e a do `ui/board_widget.py`, que diz o que o modelo leu numa casa. Mesma `Toplevel`
retirada, mesmo token de superfície, mesma borda -- e **350 ms contra 450**. Duas dicas com tempos
diferentes não são duas decisões, são uma decisão tomada duas vezes: quem passa o ponteiro da barra
para o tabuleiro vê a segunda aparecer mais cedo sem que nada explique por quê.

**Solução.** `tooltip.janela_de_dica` monta a caixinha -- superfície, letra sobre ela, borda -- e
`TOOLTIP_DELAY_MS` passa a ser o tempo dos dois. O que fica no tabuleiro é o que só ele sabe: qual
casa está sob o ponteiro, o que escrever sobre ela e onde pô-la (ao lado do ponteiro, e não abaixo
de um botão).

**Critério de aceite.** `wm_overrideredirect` aparece num único módulo de `ui/`, e o tabuleiro não
tem tempo próprio.

**Testes.** `UmaDicaSoTests` (4).

---

# Fase 64 — A documentação que envelheceu

Nove itens (S-404 a S-412), e um deles refutado. O que junta esta fase é o mecanismo, e ele é
sempre o mesmo: **um número foi medido uma vez, escrito num documento, e nunca mais comparado com
o disco.** A S-135 já tinha diagnosticado isso e criado a guarda dos "números vivos"; o que esta
fase encontra é o que a guarda **não** olhava -- e, num caso, o que ela olhava de um jeito que
nunca podia falhar.

## S-404 · O índice que não era lido

**Problema.** A tabela *"Onde mora a spec de cada item"* não cobria **oito itens entregues** --
S-171 a S-174 (`SPEC_FASE14.md`), S-176 (`ANALISE_DETECCAO.md`), S-177 (`SPEC_UI.md`) e S-294 e
S-295 (`SPEC_APARENCIA.md`).

E o pior estava no leitor. A célula `S-296 a S-323, S-325 a S-403 (menos S-324)` tem **três**
números na segunda parte, e `faixas_declaradas` descartava em silêncio toda parte que não tivesse
um ou dois. Efeito: as 107 seções do `SPEC_REVISAO.md` -- metade dos itens deste projeto -- não
estavam declaradas em lugar nenhum, e as duas guardas que leem o índice continuavam verdes. Elas
perguntam *"o que está declarado está no lugar certo?"*; nenhuma perguntava se a declaração tinha
sido lida. É a S-134 com o mesmo furo que ela existiu para tapar, agora dentro do próprio índice.

**Solução.** O leitor entende `(menos S-NNN)`, e `celula_ilegivel` acusa o que ele **não** entende
-- descartar em silêncio era o defeito, não o formato. As quatro linhas da tabela ganham os oito
itens, nos dezoito documentos que carregam a cópia dela.

**Critério de aceite.** Nenhuma célula do índice é ilegível; todo item com seção está declarado;
a exceção declarada continua valendo (a S-324 é da aparência, a S-325 é da revisão).

**Testes.** `IndiceNaoEVacuoTests` (3).

## S-405 · O CER que o próprio relatório desmente

**Problema.** O README publicava o CER de página do glifo como **0,1397** e citava, na mesma
linha, `docs/metrics/texto_pagina.json` -- que diz **0,1001**. O número era do corte de parágrafo
antigo, e o relatório registra isso no campo `remedido_por`: a S-258 mudou `RECUO_DE_PARAGRAFO` e
remediu os dois lados. O documento apontava para a medição que o contradizia.

**Solução.** O número passa a ser o do relatório, e a comparação do modo bloco também (33% pior na
média, 0,1001 contra 0,1331 -- e não "22,5% no livro nativo digital", que era do corte antigo). Uma
guarda lê o `resumo` do relatório e o compara com o que o README publica.

**Critério de aceite.** O CER citado no README está a menos de 10% do `cer_glifo_medio` do
relatório que ele cita.

**Testes.** `test_o_cer_de_pagina_citado_bate_com_o_relatorio`.

## S-406 · 292 classes contra as 314 do modelo versionado

**Problema.** O README dizia **292 classes** em três lugares e **314** num quarto, com o
`models/char_meta.json` versionado ao lado dizendo `num_classes: 314`. O 292 é de antes de as
classes de ligadura entrarem -- e o metadado é o arquivo que o próprio README manda apontar quando
os pesos não estão no lugar.

**Solução.** As três menções passam a 314, e a guarda compara todas as menções contra o
`char_meta.json`: um número diferente do outro no mesmo documento é o sintoma que ela pega.

**Critério de aceite.** Toda menção a "classificador de N classes" e "metadado das N classes" bate
com `num_classes`.

**Testes.** `test_as_classes_de_caractere_citadas_batem_com_o_char_meta`.

## S-407 · Refutado: os quarenta comandos e o `-v`

**Achado.** *"O README garante que os 40 comandos aceitam `-v`, e doze recusam."*

**Por que não é item.** Era verdade quando o relatório foi escrito, e deixou de ser na
[S-377](#s-377--todo-comando-aceita--v): os doze passaram a chamar `add_verbose`, e
`test_todo_comando_declara_a_bandeira` trava isso desde então. A contagem também está certa --
`[project.scripts]` tem exatamente 40 chaves, e `test_o_numero_de_comandos_citado_bate_com_project_scripts`
a confere. O que sobra aqui é o registro de que foi conferido, para o próximo leitor não refazer
a checagem.

## S-408 · O dicionário deixou de ser um arquivo

**Problema.** O README descrevia o dicionário como *"um arquivo de 7.588 palavras"* que *"corrige
zero"* e vem **desligado**. Desde a S-209 são **três listas** e 367.163 entradas -- `acervo.txt.gz`
(7.588), `idioma.txt.gz` (10.010) e `nomes.txt.gz` (349.565) --, e ele entrou **ligado** com a
medição que o justifica: 6 correções em 40 páginas de 11 livros, as 6 confirmadas pela camada de
texto, nenhuma palavra certa quebrada, +1,1% de tempo por página. Três afirmações erradas numa
linha, e a última fazia quem lesse desligar o que estava ligado.

**Solução.** O parágrafo passa a descrever as três listas, o total, o padrão de hoje e a razão
dele; a bandeira citada passa a ser `--sem-dicionario`, que é a que existe. A guarda conta as
entradas dos `.gz` e cobra que cada lista seja nomeada.

**Critério de aceite.** O total citado está a menos de 10% do que as listas trazem, e as três são
nomeadas.

**Testes.** `test_o_dicionario_citado_tem_as_listas_que_o_disco_tem`.

## S-409 · O comando do Streamlit não roda num clone novo

**Problema.** O README publica `uv run streamlit run examples/streamlit_demo.py` sem uma palavra
sobre o extra `demo` -- e o `streamlit` saiu das dependências obrigatórias na S-386. Num ambiente
novo o comando falha com `No module named streamlit`.

**E a guarda que devia pegar isso passava por acidente**: ela era `extra not in self.readme`, um
`in` de substring, e `demo` casa dentro de *"demonstracao"*. O extra nunca foi mencionado, e a
guarda dizia que sim.

**Solução.** O bloco ganha o `uv sync --extra demo` e a explicação de por que ele é preciso. A
régua da guarda passa a ser a linha que **instala** -- `--extra <nome>` --, e não o nome solto:
os outros cinco extras já a satisfaziam.

**Critério de aceite.** Todo extra do `pyproject` aparece no README como `uv sync --extra <nome>`.

**Testes.** `test_todo_extra_do_pyproject_aparece_no_README`.

## S-410 · O `ARCHITECTURE.md` e o que ele não contava

**Problema.** Quatro coisas, todas do mesmo mecanismo.

- **Nenhuma linha sobre o pacote `text/`**, que tem **50 módulos** -- um terço do código descrito
  como se não existisse.
- **A seção Threads contava doze**, e há **treze**: as duas da aba Texto entraram depois de o
  parágrafo ser escrito, e a tabela não as tinha.
- **O `labels.csv` aparecia com 4.450 linhas e, 146 linhas depois, com 3.313** -- e 3.313 é
  justamente o número que a S-135 existiu para matar. O disco tem 4.717.
- **Três tamanhos de artefato entre 20% e 80% fora**: `data/samples/` (3,4 contra 4,5 GB),
  `data/review_cache/` (8,3 contra 10,4 GB) e o índice sqlite (884 contra 490 MB). E a galeria,
  com 13 MB e 5.953 anotações contra 15,3 MB e 15.412.

**Solução.** Uma seção nova para o `text/`, com os 50 módulos agrupados por responsabilidade; a
contagem de threads corrigida com as duas linhas que faltavam na tabela; os números remedidos. E
três guardas novas, porque o que não é conferido volta a envelhecer: a das threads varre
`threading.Thread(` como o `test_busy` faz, a dos tamanhos usa a tolerância da S-135, e a dos
rótulos já existia.

**Critério de aceite.** A contagem de threads bate com o código; os três tamanhos estão a menos de
10% do disco; o `text/` tem seção e ela nomeia os 50 módulos.

**Testes.** `test_as_threads_citadas_batem_com_as_do_codigo`,
`test_os_tamanhos_de_artefato_citados_batem_com_o_disco`.

## S-411 · Sete âncoras que não levam a lugar nenhum

**Problema.** Sete links `#ancora` entre documentos apontavam para títulos que não existem. O modo
de falha é o mais silencioso que um documento tem: o GitHub não avisa, e o link simplesmente não
move a página. Quatro deles pararam antes do `✅ implementada (data)` que os títulos do
`ANALISE_DETECCAO.md` ganharam depois; um apontava para `#como-reproduzir` quando a seção virou
`8. Como reproduzir`; um escrevia `ja` onde o título tem `já`; e o último apontava para o título
que a S-348 tinha antes de ser reescrita.

**Solução.** Os sete corrigidos, e uma guarda que reconstrói a âncora pela regra do GitHub --
minúsculas, fora tudo que não é letra, dígito, `_`, espaço ou hífen, espaço vira hífen -- e
compara com os cabeçalhos de cada documento. Link `http` fica de fora: conferir link externo é
pedir rede na suíte.

**Critério de aceite.** Todo link interno com `#` leva a um cabeçalho que existe.

**Testes.** `AncoraInternaTests` (2).

## S-412 · A árvore que listava metade

**Problema.** A árvore *"Estrutura"* do README tinha **30 dos 53 módulos** de primeiro nível.
Entre os 23 ausentes: o `labels.py` -- a porta única do `labels.csv`, que a S-51 criou justamente
para haver uma --, os seis módulos da sala de estudo, os cinco da base de partidas e o pacote
`text/` inteiro. Uma árvore que lista metade não é um mapa: é uma amostra, e quem a lê não sabe
qual metade está vendo.

**Solução.** As 23 linhas que faltavam, cada uma com o que o módulo responde, e a árvore em ordem
alfabética -- com `service.py`, `settings.py` e `atomic_io.py` abrindo a lista, que é como ela já
estava. A guarda lê **o bloco da seção**, e não o README inteiro: `labels.py` aparece em prosa
noutra seção, e comparar contra o documento todo é como esta guarda passaria por acidente.

**Critério de aceite.** Todo `.py` de primeiro nível e todo subpacote aparecem no bloco.

**Testes.** `test_a_arvore_do_README_lista_todo_modulo_do_pacote`.

---

# Fase 65 — A suíte que não pegou nada disso

Oito itens (S-413 a S-420). Quatro mil setecentos e setenta e seis testes verdes sobre setenta
defeitos de correção. A fase não pede cobertura: pede que a suíte passe a alcançar as **três
formas** em que este relatório encontrou defeito.

- **O que vaza**: uma thread, uma pasta temporária, um painel. Nada disso reprova um teste.
- **O que trava**: uma caixa modal de verdade, esperando um clique que ninguém vai dar.
- **O que some**: um teste que pula para sempre, e é contado como verde.

E há um padrão em todos os oito: **a regra já estava escrita**. Em `tests/tk_root.py`, no
docstring de `_painel`, no comentário do `_analyse_worker`. Estar escrita é o que elas eram --
por isso valiam enquanto alguém lembrava.

## S-413 · A thread que vaza de um teste e morre no seguinte

**Problema.** `test_estudo_aba` liga a análise contínua, que sobe uma thread **de verdade** -- o
motor é de mentira, a thread não. O teste termina, o `tearDown` destrói o painel, e a thread
acorda depois para chamar `self.after(0, ...)`: `RuntimeError: main thread is not in main loop`,
levantado dentro de uma thread, que o `unittest` não vê. O pytest o atribui a **quem estiver
rodando na hora** -- e o rastro aparecia no `ExportarEstudoTests`, dois arquivos adiante. O mesmo
acontecia em `test_dataset_panel`, onde o worker fica bloqueado num `Event` que o `addCleanup`
solta ao sair.

**Solução.** Duas *fixtures* no `conftest`, autouse. `sem_thread_vazada` compara as threads antes
e depois de cada teste, espera até dois segundos pelas de trabalho e falha **no teste que a
deixou**. `erro_de_thread_e_do_teste_que_a_criou` instala um `threading.excepthook` e reprova o
teste em que a exceção estourou -- as duas juntas dizem quem criou e onde morreu.

Os dois casos achados foram consertados: a análise roda com a thread síncrona (o `after` sai da
thread principal, que é onde ele é legal) e a detecção de duplicatas é solta **de dentro do laço
do Tk**, esperando o fim da thread.

**Critério de aceite.** Nenhum teste deixa thread viva; exceção em thread reprova um teste.

**Testes.** `sem_thread_vazada` e `erro_de_thread_e_do_teste_que_a_criou`, em `tests/conftest.py`.

## S-414 · A caixa modal que para a suíte

**Problema.** Um `TextoPanel` construído sem `pasta_de_rascunhos` lê `data/rascunhos/` **da
máquina de quem roda a suíte**. Havendo um rascunho ali -- e há, na máquina de quem usa o programa
--, a aba oferece recuperá-lo com um `askyesno`, e a suíte fica parada esperando um clique. Sem
tempo limite, sem mensagem: a CI mataria a corrida por silêncio uma hora depois, e o relatório
não diria qual teste.

**Solução.** As duas metades. A **interrupção**: uma *fixture* autouse troca as sete funções do
`messagebox` por uma que falha na hora, nomeando a caixa e o título -- quem precisa exercitar uma
continua podendo, porque um `mock.patch.object` no próprio teste a sobrescreve. A **prevenção**:
uma varredura que exige `pasta_de_rascunhos=` em todo `TextoPanel` de teste.

**Critério de aceite.** Uma caixa de verdade num teste vira falha imediata com o título dela.

**Testes.** `NenhumaCaixaDeVerdadeTests` (2), e a *fixture* `nenhuma_caixa_modal_de_verdade`.

## S-415 · Cem pastas em `%TEMP%` e 99 painéis vivos

**Problema.** Cada rodada abandonava mais de cem diretórios em `%TEMP%` -- `tempfile.mkdtemp()`
sem remoção em 28 lugares -- e pendurava 99 `TextoPanel` na **raiz compartilhada**, nenhum
destruído. Um painel na raiz vive até o fim da suíte com os `after` agendados, as ligações de
tecla e o `bind_all` dele: não é só memória, é um teste alcançando o evento de outro.

**Solução.** `tests/ambiente_de_teste.py` com `pasta_temporaria(self)` -- que registra a remoção
no `addCleanup` -- e `quadro(self, raiz)`, um `Frame` destruído no fim do teste. As 28 chamadas e
os 10 painéis foram convertidos, e duas varreduras cobram a regra: `mkdtemp` só mora no ajudante,
e nenhum painel tem a raiz como pai.

**Critério de aceite.** Uma rodada completa não deixa pasta `cvoff-*` em `%TEMP%`. Medido: 63
antes, **zero** depois.

**Testes.** `NadaVazaDoTesteTests` (2).

## S-416 · Nove módulos criavam a própria raiz Tk

**Problema.** A regra está escrita em `tests/tk_root.py` desde 2026-07, com a medição junto: duas
raízes vivas são dois interpretadores Tcl, `tkinter._default_root` continua sendo o primeiro, e
uma `PhotoImage` criada sem `master` nasce no interpretador errado -- o Tk recusa a imagem com uma
mensagem que parece coleta de lixo, e foi assim que 20 testes do `test_result_panel` falharam
**só na CI**. Nove módulos criavam a sua assim mesmo, cada um com o mesmo `try/except` copiado.

**Solução.** Os nove passam a chamar `tk_root.raiz()`, e uma varredura recusa `tk.Tk()` em
qualquer módulo de teste. São 24 linhas a menos de `setUpModule`/`tearDownModule` repetido.

**Critério de aceite.** `tk.Tk()` não aparece em teste nenhum fora do `tk_root.py`.

**Testes.** `UmaRaizSoTests` (2).

## S-417 · O pulo que ninguém conta

**Problema.** Os testes de "números vivos" da S-135 -- os que comparam o que o documento diz com
o que o disco tem -- olham `data/samples/`, `PDF/` e `pgn_database/`, que não são versionados.
**Na CI eles pulam sempre.** Um teste que pula para sempre é um teste que não existe, com a
diferença de que ele aparece na contagem de verdes; e um `s` no meio de quatro mil pontos é
literalmente invisível, porque o pytest só lista os pulos quando alguém pede.

**Solução.** As duas metades outra vez. `addopts = ["-ra"]` no `pyproject.toml` faz **todo** pulo
aparecer com o motivo no fim de qualquer rodada. E uma lista declarada do que a suíte lê **e** o
repositório versiona -- os rótulos, a partição, o conjunto de campo, o `char_meta.json`, as três
listas do léxico, o relatório do CER e o `.spec` --, conferida contra o `git ls-files`: se um
deles sair do índice, a guarda que o lê vira pulo permanente na CI, e é isso que passa a falhar.

**Critério de aceite.** Nenhum artefato versionado que uma guarda lê está fora do git, e o motivo
de cada pulo é impresso.

**Testes.** `PuloQueNinguemContaTests` (3).

## S-418 · A janela de achar e substituir não tinha teste nenhum

**Problema.** É a única janela do programa que **edita texto em bloco**: uma troca dela reescreve
dezenas de lugares de uma vez, sobre um documento que alguém passou a tarde corrigindo. A suíte
não a tocava -- nem o `Enter` que **não** substitui (a regra 2 da revisão, S-342), nem o botão que
recusa trocar antes de listar, nem o `casar_figurina`, que é o que separa `♘f3` de `Nf3`.

**Solução.** `tests/test_ui_texto_busca.py`, com onze casos sobre o contrato da janela: achar e
marcar tudo, levar o editor até a ocorrência, agulha vazia que pede o que procurar, `Enter` que
não troca, o primeiro clique que só lista, o segundo que troca as marcadas, nada marcado que não
troca nada, o crivo da lista, a figurina, o `Esc` e o clique na lista.

**Critério de aceite.** O gesto destrutivo desta janela exige duas ações deliberadas, e há teste
que reprova se uma delas sumir.

**Testes.** `JanelaDeBuscaTests` (11).

## S-419 · Quatro subprocessos, quatro jeitos de achar o pacote

**Problema.** Quatro testes lançam Python de fora do pytest, e cada um resolvia o import de um
jeito: **nenhum** (dependendo da instalação editável), `sys.path.insert(0, 'src')` mais diretório
de trabalho, `PYTHONPATH`, e o caminho escrito dentro do roteiro gerado. Três funcionam neste
checkout e nenhum deles funciona nas mesmas condições -- num `git worktree`, com o `.pth`
apontando para o checkout principal, o primeiro importa o pacote **do outro lugar** e mede outro
código. E o quarto, `test_environment`, vira pulo mudo quando a distribuição não está instalada,
que é o caso normal de um worktree.

**Solução.** `tests/subprocesso.py` com `rodar_python` e `rodar_roteiro`, que põem `src/` no
`PYTHONPATH` -- a mesma coisa que o `pythonpath = ["src"]` faz dentro do pytest, então o filho vê
o que o pai vê. Os três convertidos; o `test_environment` continua montando o ambiente à mão,
porque medir a instalação **sem** `PYTHONPATH` é o que ele existe para fazer, e agora isso está
declarado na lista de exceções com o motivo.

**Critério de aceite.** Nenhum teste chama `subprocess` com `sys.executable` fora do ajudante,
salvo os declarados.

**Testes.** `UmSubprocessoSoTests` (2).

## S-420 · Metade da catraca de modais estava folgada

**Problema.** `MODAIS_DE_DECISAO` declara **quantas perguntas** a interface faz, e é a metade
honesta da conta da S-164: *"a contagem cai"* não vale nada se o que caiu foram as decisões. O
número declarado era **14** e o real é **19** -- cinco a mais, todas entradas entre a S-301 e a
S-347. Uma catraca de piso cinco abaixo do chão não trava nada: dava para apagar quatro perguntas
e a suíte continuaria verde.

**Solução.** O piso passa a 19, com as cinco nomeadas no docstring: as três da aba Texto (o
rascunho a recuperar e as duas de sair sem gravar), o "Estudo em andamento" e o `askyesnocancel`
do PGN existente. Nenhuma é notificação disfarçada -- as cinco perguntam antes de apagar trabalho
humano, que é a linha 4 da tabela do arquivo.

**Critério de aceite.** O piso é o número real de perguntas, e baixá-lo exige dizer qual deixou
de existir.

**Testes.** `test_o_que_sobrou_de_pergunta_continua_de_pe`.

---

# Fase 55, o resto — o primeiro dia (S-421 a S-424)

A Fase 55 entregou os dois achados que **mentiam** -- a FEN inventada sem classificador (S-320) e o
conserto impresso que apagava os rótulos (S-321) -- e deixou quatro que **atrapalham**. Eles
estavam sem número desde 2026-08-27, e o motivo de terem sobrevivido é o mesmo dos dois primeiros:
**nenhum deles aparece para quem já tem o acervo montado**, que é toda a gente que já leu este
código. Só existem no estado de 100% de quem instala, e ninguém que trabalha aqui volta a ele.

## S-421 · O log que não existe num checkout

**Problema.** Sete mensagens mandavam olhar "o log": a caixa de erro do OCR, o resumo da varredura
da Galeria, a leitura de texto que falhou, o auto-teste, o resumo do `cvoff-scan` e as duas do
`cli_errors`. **Num checkout não há arquivo de log** -- `default_log_file()` devolve `None` sem
`CVOFF_LOG_DIR`, de propósito, porque ali o terminal é o rastro. Quem tenta seguir a instrução
procura um arquivo que ninguém escreveu, e conclui que perdeu o rastro. Ele nunca existiu.

O programa **já sabia disso** num lugar: `Ajuda ▸ Abrir o arquivo de log` responde *"não há arquivo
de log neste ambiente: defina CVOFF_LOG_DIR"* desde a S-127. A informação estava a uma função de
distância das outras sete mensagens.

**Solução.** `logging_setup.onde_esta_o_rastro()` devolve o caminho quando há um, e o que fazer
para haver quando não há. As sete passam a chamá-la, e uma varredura recusa a frase escrita à mão.

**Critério de aceite.** Nenhuma mensagem promete um log sem perguntar se há um.

**Testes.** `OndeEstaORastroTests` (3).

## S-422 · Dois `--help` não conseguiam ser impressos

**Problema.** `cvoff-texto-pagina --help > ajuda.txt` saía com **código 2** e um arquivo com uma
mensagem de erro dentro. O mesmo em `cvoff-texto-pesquisavel`. A causa é a figurina de xadrez que
os dois trazem na ajuda (`♔`, `♘`): no Windows a saída **redirecionada** não é UTF-8, é a página de
código do sistema (cp1252 aqui), e o `print` do argparse levanta `UnicodeEncodeError`. Medido nos
40 comandos: só estes dois falham, e falham exatamente no gesto de quem quer ler a ajuda com calma.

**Solução.** `saida_que_nao_quebra_em_caractere()`, chamada no `run_main` -- que é por onde os 40
passam --, põe `errors="backslashreplace"` em `stdout` e `stderr`. **Não troca a codificação**:
forçar UTF-8 faria o acento virar mojibake num console cp1252, que é o caso comum e o que hoje
funciona. O que não couber sai como `\\u2654`, e o comando **termina**.

**Critério de aceite.** Os 40 imprimem `--help` inteiro com a saída redirecionada numa página de
código que não tem figurina.

**Testes.** `AjudaComSaidaRedirecionadaTests` (2).

## S-423 · A aba Texto abria com o motor que não pode funcionar

**Problema.** A caixa de motor da aba Texto oferecia `("glifo", "camada", "auto")` e o padrão era o
primeiro. O glifo precisa de `models/char_classifier.pt`, que **não vem no repositório** -- `*.pt`
está no `.gitignore`. Num clone novo, a primeira leitura de texto falhava por falta de um arquivo,
com a escolha certa a um clique de distância e nada dizendo isso.

**Solução.** A ordem passa a ser a de `text/leitor.py`, com `auto` primeiro. `auto` é o glifo **com
a camada como reserva**: com o classificador no lugar lê igual, e sem ele cai na camada de texto do
PDF avisando no log. É a regra do resto do programa -- degradar dizendo, em vez de recusar calado.

**Critério de aceite.** O padrão da aba é `auto`, e os três motores continuam oferecidos.

**Testes.** `MotorPadraoDaAbaTextoTests` (2).

## S-424 · A tabela de problemas cobria o modelo errado

**Problema.** A "Resolução de problemas" do README tinha **duas linhas** sobre o classificador de
**caractere** -- o motor `glifo`, que quase ninguém usa -- e **nenhuma** sobre o classificador de
**peças**, que falta em 100% dos clones e sem o qual não se lê diagrama nenhum. A mensagem que a
S-320 escreveu é boa; a tabela onde se procura por sintoma não a alcançava.

**Solução.** Duas linhas novas, **no topo**, porque numa tabela de sintomas o que acontece com todo
mundo vem primeiro: a do `piece_classifier.pt` ausente -- com o porquê de a recusa ser o recurso --
e a da aba Texto caindo na camada, que é o par da S-423.

**Critério de aceite.** A tabela cita `piece_classifier.pt` e diz como obtê-lo, antes das linhas do
`char_classifier.pt`.

**Testes.** `TabelaDoPrimeiroDiaTests` (2).

---

# Os dois que a execução deixou registrados (S-425 e S-426)

Não vieram de revisor nenhum: vieram de **fazer o trabalho**. O primeiro custou quatro minutos
por comentário corrigido, três vezes num dia; o segundo é uma escolha entre duas implementações
que existiram ao mesmo tempo, e ficou pendurada na integração de dois ramos.

## S-425 · O digest de código conta código, e não comentário

**Problema.** O digest da S-219 é sobre o **conteúdo do arquivo**. Corrigir um acento numa
docstring de `config.py` invalidava os quatro relatórios de campo e pedia uma remedição de quatro
minutos -- por um texto que nenhuma medição lê. Aconteceu **três vezes só nesta revisão**, sempre
com prosa: um comentário reescrito, um docstring com acento, uma explicação acrescentada.

O efeito de segunda ordem é o que dói: quem sabe que comentar custa quatro minutos comenta menos,
e este repositório é escrito ao contrário disso.

**Solução.** O digest passa a ser sobre a **árvore sintática**: `ast.parse` já descarta comentário
-- ele não é nó --, e as docstrings de módulo, classe e função saem daqui. O que sobra é
`ast.dump`, que traz nome, constante, condição, argumento e ordem: **toda** mudança de código
continua entrando, e o que não é código deixou de entrar.

Um arquivo que não compila continua contando byte a byte -- o digest não é o lugar de descobrir
que um módulo está quebrado.

**Critério de aceite.** Comentário, docstring, linha em branco e quebra de linha não mudam o
digest; número, condição, argumento, constante e nome de arquivo mudam.

**Testes.** `DigestSobreAArvoreTests` (10).

**Medição.** Os quatro relatórios foram remedidos uma última vez com o digest novo -- daqui em
diante uma correção de prosa não os invalida. Todos os números de acerto voltaram idênticos.

## S-426 · Decidido: a cessão de tecla continua por significado, e não por classe de widget

**Achado.** *"A `main` derivava a lista das ligações de classe do próprio Tk, separando `Entry` de
`Text`, de `Combobox` e de `Spinbox`; a integração ficou com a versão deste ramo, que deriva do
catálogo de ações e não separa por classe. A da `main` é mais fina."*

**Por que a versão deste ramo fica.** Ela é mais fina onde importa, e a da `main` responde à
pergunta errada. Derivar do `bind_class` cede **toda tecla que a classe liga** -- e ceder por
atacado é exatamente o defeito que a S-294 mediu: com o cursor no campo de FEN, `Ctrl+S` não
salvava, `Ctrl+N` não ia para o próximo da fila e `Ctrl+P` não abria a paleta, porque a guarda
entregava os dezoito atalhos a qualquer campo de texto.

A régua daqui é o **significado**: `ACOES_DO_CAMPO` diz o que um campo de fato executa, e
`ui/atalhos.py` -- o único lugar do projeto que escreve tecla -- traduz para sequência. A
separação por classe que a `main` comprava já está comprada por outro caminho, e agora está sob
teste: `Up`/`Down` chegam a quem incrementa (o `Spinbox`) e a quem escolhe da lista (o
`Combobox`), `PgUp`/`PgDn` só a quem rola, e o que não é do campo não é cedido a classe nenhuma.

**Critério de aceite.** As quatro classes de campo recebem o que usam e nada além; um quinto tipo
de campo entra em `TEXT_ENTRY_WIDGETS` ou perde as teclas dele, e o teste diz isso.

**Testes.** `CessaoPorClasseDeWidgetTests` (5).

---

# O que a segunda execução da CI encontrou (S-427 e S-428)

O PR desta revisão para a `main` foi o primeiro a rodar as três verificações sobre as nove fases
juntas, e ele **reprovou**. Dos oito testes vermelhos, dois eram do `tests/test_ui_fita.py` -- a
medida de largura que depende da fonte da máquina, que a S-326 já vinha atacando --, e os outros
dois são desta revisão. Os dois são da mesma família: **um valor lido do ambiente errado**.

## S-427 · O `-v` do processo não é o `-v` do comando

**Problema.** A S-377 fez `run_main` procurar `-v` no `sys.argv` quando ninguém passa `argv` --
que é o caso do *console script*. Mas `sys.argv` é a linha do **processo**, e nem todo processo é
o comando: a CI roda `uv run pytest -v`, e aquele `-v`, que é do pytest, fazia o `run_main`
**levantar a exceção original** em vez de traduzi-la para pt-BR e devolver o código de saída.

Dois testes de `test_cli_errors` reprovavam só lá, e a razão de ninguém ter visto é a mesma de
sempre: na máquina de desenvolvimento a suíte roda sem `-v`.

E não é defeito só de teste. Qualquer processo que chame um `main` em memória -- outro comando, a
janela no auto-teste, um script -- passa a receber traceback em vez de mensagem se a linha dele
tiver um `-v` por outro motivo.

**Solução.** Pergunta-se a quem parseou. Os 40 comandos chamam
`configure_logging(verbose=args.verbose)` depois do `parse_args`, então `logging_setup` guarda
aquele valor e `verbosidade_pedida()` o devolve. Quando o chamador **passa** `argv`, a resposta é
o que ele passou -- é o caso dos testes, e ali a intenção é explícita.

O registro acontece **antes** do `return` de idempotência do `configure_logging`: o segundo
comando de um mesmo processo não reconfigura o logging, e mesmo assim é ele quem está rodando.

**Critério de aceite.** Com `sys.argv` contendo `-v` por outro motivo, uma falha conhecida vira
código de saída e linha em pt-BR; com o comando tendo pedido `-v`, o traceback sobe.

**Testes.** `test_o_v_do_processo_nao_e_o_do_comando`,
`test_a_bandeira_e_vista_quando_ninguem_passa_argv`.

## S-428 · Existir não é ter o artefato dentro

**Problema.** A guarda de tamanho de artefato da S-410 pulava quando o caminho não existe. Mas
`data/samples/` é **versionado com um `.gitkeep`**: num clone limpo a pasta existe e está vazia,
o `exists()` passava, a soma dava 79 bytes, e a guarda acusava *"o documento diz 4,5 GB e o disco
tem 7,9e-08 -- 5.696.202.431% de diferença"* sobre um checkout perfeitamente correto.

É o inverso exato do defeito que a S-417 cataloga: lá, uma guarda que pula para sempre e ninguém
conta; aqui, uma guarda que **falha** para sempre num ambiente em que ela não tinha o que medir.
As duas vêm de confundir *o caminho existe* com *o artefato está lá*.

**Solução.** Para diretório, o critério passa a ser o conteúdo -- `.gitkeep` não conta --, e a
pasta vazia pula dizendo isso. Para arquivo, `exists()` continua respondendo, porque ali não há
essa distinção.

**Critério de aceite.** Num clone sem `data/samples/` preenchido a guarda pula; com o artefato no
lugar, ela mede.

**Testes.** `test_os_tamanhos_de_artefato_citados_batem_com_o_disco`.
## S-429 · A régua de estilo desce da linha ao caractere

**Problema.** `text/camada.py` responde negrito e itálico **por linha**, pela maioria da largura
que os spans do estilo cobrem (60%). A limitação está declarada desde a S-211 -- *"onde ele é uma
palavra no meio da prosa, é grosso"* --, e o que faltava era o tamanho dela. Medido em 2026-08-28
sobre 8 folhas de cada um dos 45 PDFs de `PDF/` (18.207 linhas de camada):

| estilo | linhas com ele | misturam dentro de si | somem (< 60%) | incham (>= 60%) |
|---|---|---|---|---|
| negrito | 969 | **428 (44,2%)** | 281 (29,0%) | 147 (15,2%) |
| itálico | 407 | **279 (68,6%)** | 241 (59,2%) | 38 (9,3%) |

Não é o caso raro que a limitação sugeria: é o caso comum. A régua erra nos **dois** sentidos --
o lance em negrito no meio da prosa some, e a linha que é quase toda negrito engole as palavras em
pé do fim. E a informação para acertar sempre esteve na mão: o span da camada traz o texto **e** o
bbox, e a linha é a costura deles.

**Solução.** `camada.linhas_com` devolve a linha da camada com um bool **por caractere**, e
`camada.trechos` a casa com o que o leitor leu -- geometria para escolher a linha, `difflib` para
alinhar o texto. `LinhaLida` ganha `negrito_em` e `italico_em`, e `rico._agrupar` passa a cortar o
parágrafo onde a tipografia muda dentro da linha, e não só entre linhas.

Três decisões que a implementação fixou:

- **a palavra é a unidade final, e não o caractere.** O motor de glifo lê `smdy` onde a camada
  escreve `study` (S-186), e marcar caractere a caractere devolveria a palavra rachada. Maioria dos
  caracteres decide a palavra inteira;
- **o campo de linha não muda.** `marcar` continua respondendo o que respondia, e quem o lê --
  `BlocoDeTexto.de_linhas`, `paragrafos.cortar`, `documento.estado_do_negrito` -- não muda uma
  linha. Os intervalos são o detalhe ao lado, e onde não há intervalo é o campo de linha que
  desenha;
- **vazio é "não sei", e devolve o comportamento de antes.** Folha sem camada, página girada
  (`spans_com` também não gira) e camada que discorda demais do que foi lido -- o
  `_OCR_Aprimorar_Aprimorar` do acervo é o palpite de outro OCR -- caem todos em vazio.

A guarda `len(linhas) < 2` de `rico._corridas_do_segmento` caiu junto: ela foi escrita quando a
menor unidade era a linha, e com ela o bloco de uma linha só -- todo título, toda legenda, toda
linha de lances solta -- voltava inteiro e perdia justamente o corte que este item entrega.

**Critério de aceite.** O texto da página não muda um caractere: `de_pagina(pagina).para_texto()`
continua idêntico a `pagina.texto(com_marcas=True)`. Verificado em 8.489 linhas de 48 livros, com
**zero** páginas divergentes. Sobre 178.556 caracteres lidos, 2.089 passam a ter a resposta certa
onde tinham a errada (716 ganham negrito, 561 o perdem, 700 ganham itálico, 112 o perdem).

**Testes.** `tests/test_texto_estilo_fino.py` -- o casamento, a palavra que não sai partida, as
três formas de degradar para o comportamento antigo, o remapeamento pela junção de hífen, o corte
do documento e a ida e volta do `.json`.
### E a contagem da linha de status desceu junto

**O que a S-429 quebrou, e o mesmo item conserta.** `documento.estado_do_negrito` contava
`linha.negrito`, e isso deixou de ser tudo o que a página sabe. Uma folha cujo negrito é sempre uma
palavra no meio da prosa tem **todas** as linhas em `False` -- e a barra dizia *"nada em negrito"*
sobre uma folha cheia dele, enquanto o editor logo acima o desenhava. É exatamente a população que
este item resgata: 281 das 969 linhas com peso do acervo cobrem menos de 60% e saem `False`.

Uma frase de status que contradiz o que está desenhado é pior que status nenhum -- que foi o
argumento que criou esta frase na S-211, voltando contra ela.

A contagem passa a ser de **trechos**: `len(linha.negrito_em)` quando há intervalo, e
`bool(linha.negrito)` quando não há. Trecho e não palavra porque é a unidade que a página tem --
`negrito_em` já vem com as palavras vizinhas unidas, e é ela que vira uma corrida na tela. Uma
linha inteiramente em negrito continua contando **1**, que é o que mantém a frase legível nos
livros de título e variante. A pergunta *"o livro informa?"* também passa a olhar os intervalos,
pelo mesmo motivo: informar por trecho é informar.

Travado por `EstadoContaTrechoTests` em `tests/test_negrito.py`.
### E a via da imagem foi remedida antes de ficar de fora

**A folha de scan não tem camada, e ali `negrito` é `None` para sempre.** A S-211 mediu a via da
imagem e a recusou -- espessura 82,2% contra 82,7% de chutar "normal" --, mas deixou escrito um
erro de método: normalizar pela **mediana da linha** apaga o sinal justamente quando a linha
inteira é negrito. O que ela **não** tentou foi normalizar pela **página**, que é o análogo que não
morre, porque a folha é majoritariamente em peso normal. A pergunta ficou aberta, e um item que
desce a régua ao caractere é a hora de fechá-la.

Remedido em 2026-08-29 com **20.156 palavras de 14 livros** (contra 940 de 3), rotuladas pelo nome
da fonte na camada, sobre a folha renderizada a 220 dpi e binarizada pelo caminho de produção.
População em **palavra**; corte aprendido **fora do livro** em que é testado.

| medida | acerto | F1 | precisão | cobertura |
|---|---|---|---|---|
| chutar "normal" sempre | 0,9227 | — | — | — |
| espessura (área / meio-perímetro) | **0,9594** | 0,654 | 0,661 | 0,647 |
| espessura / mediana da página | 0,9379 | **0,671** | 0,629 | 0,720 |
| 2 × p75 da transformada de distância | 0,9534 | 0,620 | **0,839** | 0,491 |
| densidade / mediana da página | 0,9187 | 0,426 | 0,430 | 0,422 |

**O sinal existe**, e passa do acaso. E foi conferido que não é o tamanho disfarçado -- título é
grande e costuma ser negrito: chutar só pela altura da palavra acerta 0,8889, **abaixo** do acaso,
e a altura mediana é 25 px em negrito contra 23 px em pé.

**E mesmo assim continua fora.** A melhor precisão utilizável é 0,839 -- uma em cada seis palavras
marcadas sairia errada, e negrito errado numa variante muda o que a página diz. E não há como
comprar precisão apertando o corte: ela **cai** de 0,657 para 0,381 conforme o corte sobe, porque a
cauda grossa é de palavra em pé (mancha de digitalização, glifo grande, tinta empastada). Não há
canto seguro nem para uma parte do texto. A régua para aplicar em lote é 0,9929 (S-213), e a regra
5 da [SPEC_EDITOR](SPEC_EDITOR.md) manda entregar o pincel em vez de pintar palpite.

A medição foi feita no **render de PDF nascido digital** -- o único jeito de ter rótulo, porque o
rótulo vem da camada. O scan, que é a população-alvo, é mais difícil; um "não" aqui vale com folga
para ele, e o contrário não valeria.

**Isto não é item novo, e sim a resposta da pergunta que a S-211 deixou aberta**, com a amostra e
o método que faltavam. Fica em `docs/metrics/texto_negrito_imagem.json` e no cabeçalho de
`text/negrito.py`. Nada muda no programa: para a folha sem camada o caminho continua sendo o
pincel manual da S-241.

## S-430 · O pincel de fonte não pintava sobre estilo nem sobre corpo

**Problema.** No Tk uma etiqueta só pode dar **uma** fonte ao trecho, e vence a criada por último.
`alternar` põe a etiqueta `negrito`, criada em `_pintar_faixas`; um trecho que já tenha estilo de
parágrafo ou corpo mudado carrega também uma `fonte:...` criada **depois**, sob demanda, em
`_etiqueta_de_fonte` -- e montada quando o trecho ainda não era negrito. Medido em 2026-08-28 num
`tk.Text` de verdade:

| trecho | o documento gravava | o que a tela desenhava |
|---|---|---|
| sem estilo e sem corpo | negrito | negrito ✔ |
| com corpo +1 | negrito | peso normal ✘ |
| com estilo de legenda | negrito | peso normal ✘ |

Nos dois últimos o botão **não fazia nada visível**, e o arquivo salvo contradizia o que a pessoa
viu -- o pior formato de defeito, e o mesmo achado 1 do `ROADMAP_EDITOR`: "na tela está tudo
certo" é a única forma de erro que nenhum teste sobre o documento acusa. Valia para os quatro
pincéis de fonte e também para `limpar_formato`, que tirava a ênfase do documento e deixava a
fonte gorda na tela.

**Solução.** `_combinar_negrito_italico` -- que refazia só `NEGRITO_ITALICO`, o caso particular de
trecho sem estilo e sem corpo -- vira `_refazer_fontes`, que refaz a etiqueta que
`_etiqueta_de_fonte` decide. É a mesma função que `desenhar_documento` chama, e assim o pincel e o
redesenho não podem divergir.

**Critério de aceite.** Em doze caminhos do pincel -- negrito, itálico, os dois, cada um sobre
corpo mudado e sobre estilo de parágrafo, desligar e limpar formato --, o que o Tk desenha é o que
o documento grava. `estilo_titulo` fica de fora de propósito: o papel `TITULO` de `ui/tipografia.py`
sai em negrito sempre, por ser título.

**Testes.** `PincelSobreEstiloTests` em `tests/test_ui_texto_editor.py` -- sete casos reprovam sem
a correção.
### A miniatura no meio do trecho, e as duas réguas de posição

`_refazer_fontes` anda por duas réguas ao mesmo tempo: `deslocamento_de` conta pelo **documento**,
onde a miniatura do diagrama vale zero caractere, e `indice_de` volta ao índice do **widget**, onde
ela vale um. Se as duas saíssem de fase, a etiqueta de fonte de uma corrida cairia sobre a seguinte
-- e o negrito apareceria uma palavra adiante do que foi pedido.

Pintar uma seleção que **atravessa** o diagrama é o caso que separa as duas, e é o que
`test_a_miniatura_no_meio_do_trecho_nao_desalinha_as_fontes` afirma.

## S-451 · O verde não aparecia, e a página gravada era outra

**Problema.** Relatado do uso, e as duas metades da frase são verdadeiras ao mesmo tempo: *"tem
umas páginas que clico em 'Salvar todos' mas o diagrama não fica verde -- conferi se as imagens
foram salvas mesmo assim, e foram"*. É essa conjunção que localiza o defeito: a gravação acontece,
e o que sai errado é o campo que diz **de onde** a amostra veio.

`DiagramEditorModel.adopt` (`ui/editor_model.py:170`) é o único caminho de carregamento que não
passa por `load` -- é ele que restaura uma página do `PageResultsCache` quando o usuário volta a
ela. Ele escrevia `page_key` e **não** escrevia `origin`; `PageResults` nem guardava a procedência.
O editor voltava sabendo corretamente qual página está mostrando e carregando a origem da **última
página lida** -- ou nenhuma, depois de uma passagem pela fila de revisão ou pela aba Dataset, que
carregam sem origem.

Quem grava amostra lê `origin`, e não `page_key`: `result_panel._save_one` → `service.save_sample`
→ `RecognitionOrigin.sample_fields`. Então salvar depois de voltar a uma página guardada escrevia
no `labels.csv` o `source_page` da página errada, ou o par `source_pdf`/`source_page` vazio. E o
verde da S-71 é esse mesmo campo lido de volta por `saved_diagrams_by_page`: a caixa não pintava
**e reabrir o livro não consertava**, porque o defeito estava na linha gravada. Vale igual para o
`Ctrl+S` -- nunca foi do botão.

Medido em 2026-08-29 sobre as 126 amostras que a árvore tinha por gravar, todas de
`A Matter of Endgame Technique – Jacob Aagaard.pdf`:

| o que a linha declara | quantas |
|---|---|
| procedência correta | 118 |
| `source_pdf` e `source_page` vazios | **8** |

As oito são as posições da página 20 (diagramas 1 a 6) e da 30 (1 e 2), byte a byte as mesmas FENs
das linhas que declaram aquelas páginas -- a segunda tentativa de quem clicou, não viu verde nenhum
e clicou de novo.

**O segundo problema é o mesmo laço.** Nada no caminho de gravação recusa a duplicata:
`append_training_sample` nomeia por timestamp e **sempre acrescenta**. Voltar a uma página já feita
era indistinguível de fazê-la pela primeira vez, e as mesmas 126 linhas trazem **10 excedentes** --
a página 20 gravada duas vezes e a 30, três.

**Solução.** Duas, e a segunda só faz sentido depois da primeira:

1. `PageResults` guarda `origin`, `remember_page_results` a escreve e `adopt` a devolve. Restaurar
   a página passa a ser restaurar a procedência dela.
2. `save_all` pergunta antes de regravar. `ui/page_overlay.saved_on_page` responde quais diagramas
   daquela página já têm amostra, do **mesmo** índice que pinta as caixas de verde: a pergunta tem
   de concordar com a cor que o usuário está vendo, e duas contas separadas para a mesma verdade só
   teriam como divergir. "Sim" regrava tudo, "não" salva apenas os que faltavam, e uma página
   inteiramente salva com "não" não grava nada.

Uma pergunta para a página, e não uma por diagrama -- a régua da pergunta de ilegalidade ao lado,
pela mesma razão: nove caixas iguais treinam a pessoa a clicar "sim" sem ler.

**Onde `saved_on_page` mora, e por quê.** Em `ui/page_overlay.py`, ao lado de `mark_saved`, e não
em `labels.py` com as outras duas funções do mesmo índice. `field_eval.measured_modules` alcança
`labels.py`, e pôr a função lá venceu os quatro relatórios de campo com *"mudou labels"* sem que a
medição chegue a chamá-la -- o digest da S-219 é por **módulo**, e não por função. O fecho da
medição não entra em `ui/`, e é essa fronteira que decide.

**Critério de aceite.** Ler a página 16, ler a 17, voltar para a 16 e salvar grava `source_page`
16, e o aviso de "salvo" nomeia a página 16 -- pelo botão e pelo `Ctrl+S`, que sempre leram a mesma
`origin`. Numa página com dois diagramas já salvos de três, a caixa aparece **uma** vez, nomeia os
dois pelo número do seletor, e "não" grava só o terceiro.

**As duas catracas subiram, com o motivo registrado onde elas moram.** `test_ui_retorno_modal` de
53 para 54 caixas modais -- linha 4 da tabela daquele arquivo, decisão precisa de resposta -- e
`test_packaging` de 2.292 para 2.296 linhas em `app_tkinter.py`: uma no `import` e três na `lambda`
que liga o índice ao painel.

**Testes.** `AdoptTests.test_restaurar_do_cache_traz_a_procedencia_junto` em
`tests/test_editor_model.py`; `ProcedenciaAoVoltarParaAPaginaTests` e `PerguntaDeDiagramaJaSalvoTests`
em `tests/test_result_panel.py`; `SavedOnPageTests` em `tests/test_page_overlay.py`. Onze ao todo, e
nenhum passa sem a correção.

**O que este item não faz.** Não mexe nas linhas já gravadas. As oito sem procedência saíram por
remoção nominal, cada uma conferida contra a gêmea que declara a página, e **não** por
`cvoff-audit --dedupe`. Aquele comando mantém `sorted(grupo)[0]`, o nome de arquivo mais antigo, e
os mais antigos são o lote anterior à S-19 -- justamente os que não têm procedência. Medido sobre
4.858 linhas: ele removeria 367 e, em **277 dos 311 grupos**, deixaria vivo o representante *sem*
procedência matando o que declara a página. É defeito próprio daquele comando, e fica como item à
parte.

---

## S-453 · O relatório que semeava CRLF, e a guarda que faltava do outro lado ✅ implementada (2026-08-30)

**Problema.** A [S-325](#s-325--o-digest-de-código-normaliza-a-quebra-de-linha) consertou o lado
da **leitura**: `_digest_of` normaliza a quebra antes de hashear, então um checkout com CRLF
deixou de dar digest diferente do mesmo commit. O outro lado ficou aberto — **quem grava**.

`Path.write_text` sem `newline` traduz `\n` para `os.linesep`, e no Windows isso é `CR LF`.
Cinco chamadas de `src/` gravavam assim, e três delas escrevem relatório em `docs/metrics/`,
que o `.gitattributes` declara `*.json text eol=lf`:

| chamada | o que grava |
|---|---|
| `detection_census.py:583` · `write_census_json` | `docs/metrics/deteccao_*.json` |
| `experiments.py:191` · `save_results` | a grade de variantes do treino |
| `side_survey.py:205` · `write_survey` | o levantamento de procedência do lado a jogar |

**Não é achado de leitura de código: aconteceu.** Ao remedir o censo para a
[S-454](ANALISE_DETECCAO.md), `cvoff-census` gravou `deteccao_base.csv` e `.json` com CRLF, e os
dois tiveram de ser normalizados à mão antes do commit — com o `git` avisando
`CRLF will be replaced by LF the next time Git touches it`.

**O estrago não aparece no `git status`, e é por isso que dura.** O git normaliza na leitura: um
arquivo com CRLF no disco casa com um blob em LF e a árvore parece limpa. Foi assim que os `.py`
do checkout principal ficaram com CRLF sem ninguém notar, até que a guarda da S-218 passou a
reprovar relatório correto num clone limpo — que é o defeito que a S-325 foi escrita para
consertar. **Semear é a causa; normalizar ao hashear é o curativo.**

**Solução.** As três vão para `atomic_write_text`, que abre o temporário com `newline="\n"`.
O conserto e a escrita atômica são o mesmo movimento, então as três **saem de `PERMITIDAS`** no
mesmo commit: elas não gravam mais direto, e uma exceção que sobrevive ao motivo vira permissão
em branco.

Os dois sítios restantes ficam, declarados em `SEM_LF_DECLARADO` com o motivo: o `.pgn` exportado
e o `.review.pgn` de `pdf_to_pgn.py`. **O padrão PGN especifica CR/LF como terminador**, e nenhum
`.pgn` é versionado neste repositório — a regra do `.gitattributes` não os alcança.

**Critério de aceite.**

- ✅ nenhum `write_text` em `src/` grava a quebra da plataforma, fora do que está declarado;
- ✅ a lista de exceções recusa entrada sem motivo escrito, como a irmã dela já fazia;
- ✅ a lista não guarda arquivo que não existe mais;
- ✅ `PERMITIDAS` encolhe de cinco para dois, e a docstring dela diz por quê.

**A guarda foi conferida contra o código que a motivou**, e não só contra o consertado: rodada
sobre o commit da S-454, ela acusa `detection_census.py:583`, `experiments.py:191` e
`side_survey.py:205`. Uma guarda que só é vista passar não foi vista funcionar.

**Testes.** `tests/test_atomic_writes.py::EscritaAtomicaTests` — `test_todo_write_text_grava_lf`,
`test_a_lista_de_lf_nao_guarda_arquivo_que_nao_existe_mais` e `test_cada_excecao_de_lf_diz_por_que`,
ao lado dos quatro da guarda de escrita atômica, que é a mesma forma pelo mesmo motivo: a decisão
estava sendo tomada por omissão.
