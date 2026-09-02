# Roadmap da sala de estudo — Fases 43 a 50

O que a aba **Análise** é hoje, por que ela não é uma sala de estudo, e o plano para transformá-la
numa **sem que nenhuma análise morra no clique seguinte**. Especificação item a item em
[SPEC_ESTUDO.md](SPEC_ESTUDO.md) (S-268 a S-290).

O reconhecimento que alimenta a aba está em [SPEC.md](SPEC.md) e [SPEC_FASE7.md](SPEC_FASE7.md); a
base de partidas que ela vai consultar, em [PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md); a
fundação de interface que este plano usa — tokens, tipografia, catálogo de comandos, atalhos — em
[SPEC_UI.md](SPEC_UI.md) e [SPEC_APARENCIA.md](SPEC_APARENCIA.md); e o documento rico que os
comentários reaproveitam, em [SPEC_EDITOR.md](SPEC_EDITOR.md). **Nenhuma fase daqui treina modelo
nem mexe em detecção.**

**Data da avaliação:** 2026-08-26 · **Ramo:** `fase-5-modelo-desempenho` · **Aba avaliada:**
`src/chess_diagram_ocr/ui/study_panel.py`, 478 linhas · **Fonte de ideias:**
`Ideias para o board da aba de análise/obsidian-chess-study-trunk` (obsidian-chess-study 1.2.0)

> **Onde mora a spec de cada item (S-NN).**
>
> | itens | arquivo |
> |---|---|
> | S-01 a S-36 | [SPEC.md](SPEC.md) |
> | S-37 a S-77 | [SPEC_FASE7.md](SPEC_FASE7.md) |
> | S-78 a S-82, S-143, S-175, S-176 | [ANALISE_DETECCAO.md](ANALISE_DETECCAO.md) |
> | S-83 a S-94 | [PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md) |
> | S-95 a S-142, S-171 a S-174, S-218, S-219 | [SPEC_FASE14.md](SPEC_FASE14.md) |
> | S-144 a S-170, S-177 | [SPEC_UI.md](SPEC_UI.md) |
> | S-178 a S-217 | [SPEC_TEXTO.md](SPEC_TEXTO.md) |
> | S-220 a S-234, S-294, S-295, S-324 | [SPEC_APARENCIA.md](SPEC_APARENCIA.md) |
> | S-235 a S-267, S-291 a S-293, S-521 | [SPEC_EDITOR.md](SPEC_EDITOR.md) |
> | S-268 a S-290 | [SPEC_ESTUDO.md](SPEC_ESTUDO.md) |
> | S-296 a S-323, S-325 a S-430, S-451, S-452 (menos S-324) | [SPEC_REVISAO.md](SPEC_REVISAO.md) |
> | S-431 a S-440 | [SPEC_REVISAO_EXTERNA.md](SPEC_REVISAO_EXTERNA.md) |
> | S-441 a S-450 | [SPEC_ACABAMENTO.md](SPEC_ACABAMENTO.md) |
> | S-507 a S-520 | [SPEC_ESTUDO_QT.md](SPEC_ESTUDO_QT.md) |

---

# O pedido, e a frase que ele esconde

> "A aba 'Análise' na verdade deve ser um 'Tabuleiro de estudo' ou 'Sala de estudo', isto é, nesta
> aba usaremos o board para estudar o PDF. Carregaremos a posição do diagrama ali e teremos muitos
> recursos de análise de xadrez como lista de lances, variantes e subvariante."

Duas palavras do pedido decidem tudo o que vem depois, e nenhuma delas é "variante".

A primeira é **sala**. Uma sala é um lugar onde se *fica*: sai-se dela e volta-se, e o que ficou
sobre a mesa continua lá. Um tabuleiro é um objeto — carrega uma posição de cada vez e não deve
nada a ninguém. A aba de hoje é um tabuleiro, e o defeito não é falta de recursos: é que **clicar
no diagrama seguinte joga fora, sem perguntar, toda a análise do anterior** (achado 2). Enquanto
isso valer, cada recurso novo é mais trabalho a perder no clique seguinte.

A segunda é **PDF**. Não é "estudar xadrez": é estudar *este livro, esta página, este diagrama*. O
que distingue esta sala de qualquer visualizador de PGN do mundo é que ela nasce dentro do livro e
sabe voltar para ele. Hoje o único vínculo entre a aba e o livro é uma `str`:

```python
current_fen=lambda: self.result_panel.fen_var.get() if self.result_panel else ""
```
`app_tkinter.py:393`

E essa `str` não é sequer uma FEN — é só o campo de peças (achado 1). Ela não diz de que livro veio,
de que página, de que diagrama, nem de quem é a vez.

Daí a ordem das fases, que é a mesma disciplina que a Fase 36 impôs ao editor de texto: **o estudo
é dado, e a aba é um desenho dele.** A Fase 43 não entrega um recurso novo de xadrez — e é a fase
sem a qual as outras sete não valem nada.

---

# A aba de hoje, medida

| o que ela tem | onde | quanto |
|---|---|---|
| botões na aba | `ui/study_panel.py:88-169` | **13** |
| comandos no catálogo da S-324 | `ui/comandos.py` | **0 dos 13** — a aba inteira está fora dos 90 do registro |
| atalhos na tabela da S-161 | `ui/atalhos.py` | **0** — e 4 teclas ligadas por fora, no canvas (`:141-144`) |
| linhas na legenda de atalhos (S-165) | — | **0** |
| entradas na paleta de comandos (S-231) | — | **0** |
| formas de anotar um lance | — | **0** — sem comentário, sem NAG, sem seta, sem casa marcada |
| formatos de saída | `ui/study_panel.py:455-478` | **1** — `.pgn`, por `filedialog`, só a mando do usuário |
| formatos de entrada | — | **0** — não existe colar PGN nem abrir `.pgn` |
| o que sobrevive a fechar o programa | — | **nada** — nenhum dos 20 campos do `AppState` é do estudo |
| o que sobrevive a clicar no diagrama seguinte | — | **nada** — ver o achado 2 |
| navegação por variante | `ui/study_panel.py:112-126` | **1 combobox e 1 botão "Entrar"** |
| a lista de lances | `ui/study_panel.py:150-152` | **1 `tk.Text` de 5 linhas, `state=DISABLED`** |
| API de `chess.pgn` usada | — | **4 de 20** — `add_variation`, `variations`, `parent`, `accept` |
| decisões testáveis fora da janela | — | **0** — não há um módulo de estudo; tudo está no `ttk.Frame` |

O que ela **acerta**, e que este plano preserva: o lance ilegal é recusado pelo `BoardModel` e não
pelo painel; a promoção é perguntada; jogar um lance que já existe na linha **segue** a linha em vez
de duplicá-la (`push_move`, `:449`) — que é o comportamento certo e o mesmo do ChessBase; a análise
do motor sai da thread da janela; e sem Stockfish a seção inteira some em vez de ficar cinza (S-33).
**A fundação de xadrez está certa. O que falta é tudo o que se constrói em cima dela.**

---

# A pasta de ideias, lida como código

`obsidian-chess-study` é um plugin de Obsidian: React + `chess.js` + `chessground`, 1.2.0, ~900
linhas de TypeScript. Ele não é um concorrente do ChessBase e não pretende ser — o próprio README
diz *"although it is not a full analysis board"*. O valor dele aqui é outro: é um **desenho mínimo e
completo** de estudo anotado, e cada decisão dele responde a uma pergunta que a nossa aba não fez.

## Quatro ideias que se copiam

**1 · O estudo é um arquivo versionado, não estado de widget.** `ChessStudyFileData` é
`{version, header, moves[], rootFEN}`, gravado em JSON com `CURRENT_STORAGE_VERSION = '0.0.2'` e com
migração escrita para a versão anterior (`if (!jsonData.rootFEN) return {...jsonData, rootFEN}`,
`lib/storage/index.ts:78`). É a nossa regra 1 da SPEC_EDITOR — *o documento é dado* — aplicada a
partida em vez de a texto, e é o que falta à nossa aba por inteiro.

**2 · A anotação mora no lance, e viaja com ele.** Cada `ChessStudyMove` carrega `shapes: DrawShape[]`
e `comment: JSONContent | null`. Navegar carrega as setas daquele lance no tabuleiro
(`ChessStudy.tsx`, `shapes={gameState.currentMove?.shapes || []}`) e o comentário no editor. Não há
"as setas do tabuleiro": há *as setas daquele lance*. É a diferença entre um quadro-negro e um livro.

**3 · A lista de lances é a navegação.** `MoveItem` tem `onMoveItemClick`, marca `active` o lance
corrente e faz `scrollIntoView({block: 'nearest'})` quando ele muda. Nossa lista é um `tk.Text`
desabilitado: não se clica, não se vê onde se está, e com variantes vira uma linha só de parênteses.

**4 · Lance novo no meio da linha vira variante; igual ao que já estava, segue a linha.**
`ADD_MOVE_TO_HISTORY` (`ChessStudy.tsx:200-260`) compara `nextMove.san === newMove.san` antes de
criar variante. Nosso `push_move` já faz o mesmo, por outro caminho. **Confirma o que temos** — vale
registrar, porque é a decisão que mais se erra em visualizador de PGN.

## Três decisões dele que **não** se copiam, e por quê

**1 · Variante de profundidade 1.** `Variant.moves: VariantMove[]` é uma lista plana, e `VariantMove`
não tem campo `variants` — o README anuncia isso como recurso: *"Add support for variants (depth 1)"*,
e a captura `imgs/chess-study-variants.png` traz a frase "Variants are supported with a depth of 1".
**Para um livro de xadrez isso é fatal**, e é exatamente a palavra que o pedido usa: *subvariante*.
A nota típica de um livro é `12...♘f6 13.♗g5 (13.♗e3!? h6 14.♗h4 g5∞) ♕b6`, com variante dentro de
variante. Nós já temos a árvore certa — `chess.pgn.GameNode` é recursiva desde sempre. **Copia-se a
interação, nunca a estrutura.**

**2 · A FEN de antes e a de depois gravadas em cada lance.** O `Move` do `chess.js` traz `before` e
`after`, e o plugin grava os dois no arquivo. São ~180 bytes de FEN por meio-lance, redundantes com o
próprio lance. O formato certo para uma partida anotada já existe há 30 anos e o usuário deste
programa o usa todo dia: **PGN**. A FEN é derivada.

**3 · Um `nanoid` por lance, gravado no arquivo.** O plugin precisa disso porque o React re-renderiza
a lista e um clique tem de voltar ao lance certo. Nós precisamos da mesma coisa e **não podemos
resolver do mesmo jeito**: um identificador gravado no arquivo não sobrevive a exportar para PGN e
reabrir no ChessBase. A resposta é o **caminho** — a tupla de índices de variação da raiz até o nó,
`(0, 3, 1)` —, que é derivada da árvore, serializável, imprimível e não gasta um byte de arquivo.

E há uma armadilha nela que o plugin não tem porque não promove variante: **promover ou apagar uma
variante muda os índices**, e um caminho guardado passa a apontar para outro lance. É a mesma forma
de defeito que a S-262 registrou no editor — *a pilha do Tk guarda índice, não conteúdo* —, e a
spec trata dela explicitamente (S-268).

---

# Doze achados, e o item que cada um vira

**1 · O estudo abre com a vez errada, e sem direito a roque.** O painel recebe
`result_panel.fen_var`, que **não é uma FEN**: é o campo de peças que `fen_from_class_indices`
devolve (`fen_utils.py:272`). O lado a jogar mora noutra lista (`editor_model.side_edits`,
`:158`) e não é passado. `board_from_fen` completa o que falta com `_normalize_fen`, que crava
`w - - 0 1`. Medido, com uma posição do acervo:

```
placement       r1bq1rk1/pp2bppp/2n1pn2/3p4/3P4/2NBPN2/PP3PPP/R1BQ1RK1
FEN do estudo   r1bq1rk1/... w - - 0 1
vez             brancas          <- mesmo quando o livro e a S-17 dizem pretas
roque           nenhum           <- O-O recusado como lance ilegal
```

Toda a Fase 3 do projeto — S-16, S-17, S-19, `SideToMoveSource`, o conflito texto×legalidade — existe
para responder *de quem é a vez*, e a sala de estudo joga a resposta fora na porta de entrada. O
botão "Trocar vez" da aba é o remendo manual disso. → **S-269**

**2 · Trocar de diagrama apaga a análise, sem perguntar.** O caminho é curto e não tem guarda:

```python
def sync_with_ocr(self, force=False): ... self._load_position(fen, ...)
def _load_position(self, fen, ...):    ... self._set_board_state(board_from_fen(fen), ...)
def _set_board_state(self, board, ...): self.game = self._new_game(board)   # :296
```

`self.game` é a árvore inteira. E `follow_ocr_var` nasce em `True` (`:73`), então **a configuração
padrão é a destrutiva**: clicar no retângulo do diagrama seguinte na página descarta o que se
estava analisando. "Posição inicial", "Aplicar FEN" e "Trocar vez" fazem o mesmo. → **S-270**

**3 · Nada sobrevive a fechar o programa.** O `AppState` guarda 20 campos — último PDF, página,
zoom, divisor, aba aberta, pele, conjunto de peças. Nenhum é do estudo. A aba de texto já resolveu
isto para si na S-255 (`text/rascunho.py`), com gravação por inatividade, escrita atômica e oferta
de recuperação na abertura. A sala de estudo não tem nada disso. → **S-271**

**4 · A lista de lances não é lista, é um parágrafo.** `StringExporter` despejado num `tk.Text`
de 5 linhas com `state=DISABLED` (`:150-152`). Não se clica num lance; não se vê qual é o corrente;
com variantes o resultado é `1. e4 e5 2. Nf3 ( 2. Bc4 Bc5 ) Nc6` corrido, e achar onde se está é
impossível. É a superfície que todo programa de xadrez usa como navegação principal — inclusive o
plugin de hobby da pasta de ideias. → **S-273, S-274**

**5 · Variante se navega por combobox.** "Continuações" lista os filhos do nó atual e um botão
"Entrar" desce um nível (`:112-126`). Não se vê que existe variante dois lances à frente; não se
promove; não se rebaixa; não se apaga. E `go_to_end_of_line` tem uma esquisitice que o próprio
comentário admite: segue a variante escolhida no **primeiro** passo e a linha principal daí em
diante (`:404-406`). → **S-275**

**6 · Um lance errado fica na árvore para sempre.** `undo_move` só anda para trás — não remove
(`:377`). Não há "apagar variante", "apagar daqui em diante" nem desfazer. Clicou errado, o lance
ficou. → **S-275**

**7 · Não há como anotar nada.** Sem comentário, sem NAG, sem seta, sem casa marcada. Um livro de
xadrez **é** anotação: `13.♗g5!? h6 14.♗h4 (14.♗xf6 ⩲) g5∞`. Uma sala que não anota é um tabuleiro
com botão de desfazer. E `python-chess` já traz tudo — `node.comment`, `node.nags`, `node.arrows()`,
`node.set_eval()` —, com o detalhe que decide o item: **seta e casa marcada viajam dentro do
comentário PGN**, como `[%cal Gf3g5]` e `[%csl Rd4]`, que é o que Lichess, ChessBase e Scid leem.
Anotar aqui não cria formato nosso: cria PGN interoperável. → **S-277, S-278, S-279**

**8 · O motor é um tiro único sem memória.** Aperta-se "Analisar posição", vem uma linha e uma barra
(`:186-215`). Não há análise contínua enquanto se navega, não há lances candidatos (multipv), não há
como pôr a linha do motor na árvore como variante, e **a avaliação não fica no lance**: sai-se dele e
volta-se, e é preciso analisar de novo. `Evaluation` já carrega `pv_san`, `depth` e `best_move`, e
`node.set_eval()` já grava `[%eval 0.35,18]` no PGN. → **S-285, S-286**

**9 · O livro está do lado e a porta é uma `str`.** A aba não sabe o livro, a página nem o número do
diagrama. Consequências, todas visíveis: o PGN salvo sai com `Event: ChessVisionOFF Study`,
`Site: Local` e nada mais, enquanto `pdf_to_pgn.py:698-732` já escreve `SourcePDF`, `Page`,
`Diagram`, `Round`, `Annotator` e `Caption` para o mesmo diagrama; não há o recorte do diagrama ao
lado do tabuleiro para conferir contra o que se está analisando; não há como voltar à página; e o
**número do lance** — que a aba Galeria anota desde a S-67 e a Resultado edita desde a S-71 — não
chega, então o estudo de uma posição do lance 23 numera a partir de 1. → **S-268, S-282, S-284**

**10 · A linha impressa no livro não pode ser jogada.** `text/notacao.fatiar` já separa lance de
prosa na página lida (S-208), e a spec daquele item diz, com todas as letras, que a metade que falta
— `validar`, a legalidade pela posição — *"é a que dá o PGN de partida"*, e por isso a S-208 está
**parcial**. A sala de estudo é onde essa metade tem cliente: a linha `1...♗xb7 2.♗xb7 ♘d7` impressa
ao lado do diagrama 3 vira uma variante da posição do diagrama 3, ou vai para revisão com o motivo.
→ **S-283** (e é ela que fecha a S-208)

**11 · A busca por posição existe e a sala não a alcança.** `games_db.scan_by_positions`,
`PositionIndex`, `match_positions` e o índice SQLite de `games_index.build_index` já respondem *que
partidas chegaram a esta posição* — é o que a S-72/S-73 usa para preencher os headers do PGN
exportado. Do tabuleiro de estudo, não há botão. É o gesto mais usado do ChessBase. → **S-287**

**12 · A aba está fora do programa.** Treze botões, **zero** comandos no catálogo de 90 da S-324 —
logo, zero na paleta de comandos (S-231), zero na legenda de atalhos (S-165) e nenhuma das três
peles (S-221/S-223) consegue desenhar um só controle dela. É literalmente a S-161 outra vez: *"o que
não era botão não existia"*, agora com uma aba inteira no papel do que não existe. → **S-280, S-281**

---

# A segunda leitura: sete coisas que a primeira passou

A primeira leitura olhou a aba e a pasta de ideias. Esta olhou o que já existe no repositório e
**seria desperdiçado ou quebrado** — que é onde os planos deste projeto costumam falhar.

**13 · As setas na `play` do tabuleiro ainda não existem, e o gesto está livre.** `BoardRenderer`
desenha casas, peças, coordenadas, heatmap e contornos — não desenha seta nenhuma
(`ui/board_render.py:358-566`). E o botão direito, que é o gesto universal de desenhar seta, está
livre em modo de jogo: `BoardModel.erase` começa com `if self.mode != "edit": return BoardChange()`
(`board_model.py:322`). Ou seja, o clique direito no tabuleiro de estudo **hoje não faz nada**, e o
lugar da seta está vago. → detalha a **S-279**

**14 · A numeração de lance em variante é a parte que todo mundo erra — e há um juiz de graça.** A
regra é: o primeiro lance de qualquer variante imprime o número (com `...` se for das pretas); dentro
dela, brancas imprimem `N.` e pretas nada — **exceto** depois de comentário ou de subvariante, onde
as pretas voltam a imprimir `N...`. O plugin da pasta trata isso com quatro condicionais aninhadas
(`PgnViewer/index.tsx:120-145`) e ainda assim só cobre profundidade 1. Nós não precisamos advinhar:
`chess.pgn.StringExporter` já acerta. **O texto puro da nossa lista, com os trechos juntados, tem de
ser igual ao que o `StringExporter` produz para a mesma partida** — é a mesma trava de
não-regressão que a S-235 usou (*"`para_texto()` reproduz byte a byte o que `texto_atual` devolve"*),
e ela transforma a parte mais escorregadia do item numa asserção. → decide a **S-273**

**15 · Renomear a aba derruba a sessão seguinte, em silêncio.** `AppState.active_tab` guarda a aba
aberta **pelo rótulo** desde a S-156, e `abas.py` já avisa que rótulo é identidade. Trocar "Análise"
por "Estudo" faz o guardado não casar com nada e `rolagem.selecionar_aba` devolver `False` sem
ninguém notar: a janela cai na primeira aba. O rename precisa vir com a tradução do valor antigo. →
**S-272**

**16 · O comentário do PGN não é o comentário da pessoa.** `node.comment` traz os comandos
misturados ao texto — depois de gravar seta e avaliação, ele vale
`'[%csl Rd4][%cal Gf3g5] roque curto [%eval 0.35,18]'` (medido, `python-chess` 1.11.2). `python-chess`
lê os comandos de volta (`arrows()`, `eval()`) mas **não os tira do `comment`**. Mostrar isso ao
usuário seria mostrar o encanamento. Separar texto de comando é função pura, e é a primeira coisa
que o módulo de estudo precisa ter. → **S-268**

**17 · O desfazer da janela já tem dono, e o estudo tem de se apresentar a ele.** A S-243 criou
`ui/desfazivel.py`: um `Protocol` com `contem(widget)`, `desfazer()`, `refazer()` e `edicao()`, e a
regra de quem recebe o `Ctrl+Z` conforme o foco. Hoje há dois registrados — o tabuleiro e o editor de
texto. Se a sala de estudo criar a terceira pilha por conta própria, `Ctrl+Z` numa aba mexerá na
outra, que é o defeito exato que aquele item mediu. → **S-275**

**18 · Uma sala com muitos estudos é uma pasta de arquivos, e o formato dela já está escolhido.**
Guardar um `.pgn` por diagrama espalharia dezenas de arquivos por livro. Guardar **um PGN por livro,
com cada estudo como uma partida** e `SourcePDF`/`Page`/`Diagram` nos headers é o modelo de base de
dados que o ChessBase e o Scid usam — e o arquivo resultante abre nos dois. Como bônus, é o mesmo
conjunto de headers que `pdf_to_pgn.py` já escreve, então o estudo e a exportação de posições do
livro falam a mesma língua. → **S-268, S-271**

**19 · Fechar o programa com estudo por gravar precisa avisar, e o aviso já existe.**
`BusyRegistry` tem `loses_work` justamente para isso, e a aba de texto o usa. → **S-271**

---

# As oito fases

> **As oito estão implementadas** (S-268 a S-290). A spec diz o critério de aceite de cada item e
> diz também, item a item, onde a implementação decidiu diferente do plano — e onde ela declarou um
> buraco em vez de tapá-lo com heurística.

## Fase 43 — A sala, e o estudo que sobrevive ao clique seguinte

> Ao fim dela a aba está quase igual na tela. O que mudou é que existe um **estudo** — com nome,
> endereço no livro e vez certa —, que trocar de diagrama passa a trocar de estudo em vez de apagar
> um, e que fechar o programa deixa de custar a tarde de alguém.

| item | o que entrega |
|---|---|
| **S-268** | `estudo.py`: o estudo como dado, fora do `tkinter`. Árvore, caminho estável, comentário separado dos comandos, âncora no livro, ida e volta para PGN |
| **S-269** | O estudo nasce com a vez e o roque que o livro diz, e no número de lance que a Galeria anotou |
| **S-270** | Um estudo por diagrama: trocar de diagrama troca de estudo, e voltar traz a análise de volta |
| **S-271** | O rascunho do estudo, o PGN por livro e a sessão que volta onde parou |
| **S-272** | A aba deixa de se chamar "Análise", e a sessão anterior não cai na primeira aba |

## Fase 44 — A lista de lances é a navegação

> A fase do pedido: **lista de lances, variantes e subvariantes**. Ao fim dela a lista é a superfície
> por onde se anda no estudo, e a variante é uma coisa que se vê, se entra, se promove e se apaga.

| item | o que entrega |
|---|---|
| **S-273** | A lista desenhada como dado: trechos com papel, nível e caminho, sem `tkinter` — e o texto que sai deles é o do `StringExporter`, byte a byte |
| **S-274** | A lista clicável, com o lance corrente à vista e a raiz como primeiro item |
| **S-275** | Entrar, promover, rebaixar e apagar variante — e o desfazer que a S-243 já sabe roteirizar |
| **S-276** | A sala tem duas colunas: tabuleiro e lances lado a lado, com divisor lembrado |

## Fase 45 — A anotação, que é o que o livro tem

> Ao fim dela um lance carrega o que o livro carrega: um símbolo, uma frase e um desenho. E tudo
> isso sai em PGN que o ChessBase e o Lichess leem.

| item | o que entrega |
|---|---|
| **S-277** | O comentário do lance, e por que ele reaproveita o `DocumentoRico` da S-235 |
| **S-278** | Os símbolos de avaliação (NAG), e os que o acervo realmente usa |
| **S-279** | As setas e as casas marcadas — desenhadas com o botão direito, gravadas em `[%cal]`/`[%csl]` |

## Fase 46 — A aba é do programa

> Nenhum item dela acrescenta xadrez. Ao fim, os vinte e quatro comandos da sala existem para o
> menu, para a paleta e para as três peles — e as quatro teclas saíram do canvas do tabuleiro.

| item | o que entrega |
|---|---|
| **S-280** | Os comandos do estudo no catálogo da S-324 — e o **sétimo grupo**, `ESTUDO` |
| **S-281** | As teclas do estudo na tabela da S-161, e o fim do `bind` no canvas. De quebra, `Home` e `End` viraram "primeira/última página do livro", que faltavam desde a S-70 |

## Fase 47 — O livro entra na sala

> A fase que só este programa pode escrever: nenhum visualizador de PGN do mundo tem a página ao
> lado. Ao fim dela a S-208 deixa de ser **parcial**, dois dias depois de ter sido escrita assim.

| item | o que entrega |
|---|---|
| **S-282** | O recorte do diagrama ao lado do tabuleiro, com clique para ampliar |
| **S-283** | A linha impressa vira variante — e é o que fecha a S-208 |
| **S-284** | Voltar para a página de onde o estudo veio |

## Fase 48 — O motor, e a base de partidas

> Ao fim dela o motor acompanha o lance corrente em vez de responder uma vez, a avaliação viaja no
> PGN como `[%eval]`, e a base do usuário responde do tabuleiro.

| item | o que entrega |
|---|---|
| **S-285** | A análise contínua, e a avaliação que fica no lance |
| **S-286** | Os lances candidatos (MultiPV), e o que vira variante |
| **S-287** | Que partidas chegaram a esta posição — e os **quatro** estados dessa resposta |

## Fase 49 — Entrada e saída

> Até aqui a sala só recebia diagrama e só devolvia PGN. Ao fim dela ela aceita o que estiver na área
> de transferência, reabre a coleção que alguém editou no ChessBase, e devolve o estudo nos três
> formatos que a Fase 39 deu ao editor de texto.

| item | o que entrega |
|---|---|
| **S-288** | Colar PGN/FEN e abrir um `.pgn` — com a régua do plugin de referência **trocada** por uma que não erra |
| **S-289** | O estudo exportado em `.md`, `.html` e `.rtf`, e a linha voltando para a aba Texto |

## Fase 50 — Treinar

> A razão de estudar um livro de xadrez é acertar o lance antes de virar a página.

| item | o que entrega |
|---|---|
| **S-290** | Adivinhar o lance: a linha some, e o tabuleiro cobra. Sete linhas de código, porque o estudo já tinha tudo |

---

# O que fica de fora, e por quê

| ideia | por que não |
|---|---|
| relógio, `[%clk]`, tempo por lance | `python-chess` suporta, e nada nesta sala é partida cronometrada. Livro não tem relógio |
| tabuleiro de análise em janela própria | a S-150 mediu o notebook de 1366×768; mais uma janela é mais uma coisa a arrumar na tela |
| motor rodando sozinho no acervo inteiro | é a hipótese que a S-33 registrou como **não medida** — avaliação bizarra sugere erro de OCR. Continua não medida, e continua fora |
| árvore de aberturas / repertório | é outro produto. O que cabe aqui é a busca por posição na base do usuário (S-287) |
| gravar `nanoid` por lance no arquivo | não sobrevive à exportação para PGN. O caminho de variação resolve o mesmo problema sem gastar arquivo (S-268) |
| variante de profundidade 1 | é a limitação do plugin da pasta, e o pedido usa a palavra *subvariante*. `chess.pgn` é recursiva |
| renomear `ui/study_panel.py` | o nome do arquivo não é interface, e o rename custaria diff em `app_tkinter.py` e em seis testes sem mudar nada para quem usa. A classe segue `StudyPanel` |
