# Especificação da sala de estudo — Fases 43 a 50 (S-268 a S-290)

Base: [ROADMAP_ESTUDO.md](ROADMAP_ESTUDO.md), que traz a medição da aba de hoje, a leitura da pasta
`Ideias para o board da aba de análise/`, os doze achados, a segunda leitura e o sequenciamento.

A fundação de interface é a das Fases 20 a 24 ([SPEC_UI.md](SPEC_UI.md)) e das Fases 32 a 35
([SPEC_APARENCIA.md](SPEC_APARENCIA.md)); o documento rico que os comentários reaproveitam é o da
Fase 36 ([SPEC_EDITOR.md](SPEC_EDITOR.md)); a base de partidas que a Fase 48 consulta é a de
[PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md).

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
> | S-296 a S-323, S-325 a S-385 (menos S-324) | [SPEC_REVISAO.md](SPEC_REVISAO.md) |

Cada item tem **Problema** (com arquivo:linha do estado atual), **Solução**, **Critério de aceite**
e **Testes**. Nome de módulo é sugestão; o que importa é a fronteira de responsabilidade.

**Sete regras valem para toda esta spec.**

1. **O estudo é dado; a aba é um desenho dele.** Nenhuma informação de análise — lance, variante,
   comentário, símbolo, seta, avaliação — pode existir só como estado de um `ttk.Frame`. É a regra 1
   da SPEC_EDITOR aplicada a partida em vez de a texto, e o que ela custa está medido no achado 2 do
   roadmap: hoje `_set_board_state` descarta `self.game` inteiro sem perguntar.
2. **O formato de saída é PGN, e o PGN é o de todo mundo.** Nada de contêiner nosso para o que a
   notação já sabe dizer. Seta e casa marcada vão em `[%cal]`/`[%csl]`, avaliação em `[%eval]`,
   símbolo em NAG — porque é isso que o ChessBase, o Scid e o Lichess leem. O que só nós temos —
   livro, página, diagrama — vai em **header**, com os mesmos nomes que `pdf_to_pgn.py:698-732` já
   escreve.
3. **A árvore é recursiva, sempre.** Variante dentro de variante é o caso normal de um livro, não
   um extra. Nenhum item pode assumir profundidade 1 — é a limitação do plugin da pasta de ideias, e
   o pedido usa a palavra *subvariante*.
4. **Nenhum item crava cor, fonte ou espaçamento fora dos módulos que os decidem** (`ui/tokens.py`,
   `ui/tipografia.py`, `ui/estilos.py`). É a regra 1 da SPEC_UI e a regra 3 da SPEC_APARENCIA, e
   aqui ela tem clientes novos: a lista de lances, os símbolos de avaliação e a cor das setas.
5. **Todo comando da sala entra em `ui/comandos.py`, e toda tecla em `ui/atalhos.py`.** Um recurso
   que não é comando fica invisível para as três peles e para a paleta da S-231 — que é a S-161
   outra vez, e o achado 12 do roadmap mede o tamanho do buraco: 0 comandos de 90.
6. **O que o programa já sabe não se readivinha.** Vez a jogar é da S-17, número de lance é da S-67,
   recorte do diagrama é da S-12, busca por posição é da S-73. A sala **consome**; ela não refaz.
7. **Perder análise humana pede confirmação; perder leitura de máquina, não.** É a régua que
   `RecognizedDiagram.edited_by_hand` já aplica ao cache de páginas: releitura custa segundos de CPU,
   trabalho humano custa a tarde de alguém.

---

# Fase 43 — A sala, e o estudo que sobrevive ao clique seguinte

> Ao fim dela a aba está quase igual na tela. O que mudou é que existe um estudo com nome, endereço
> no livro e vez certa; que trocar de diagrama troca de estudo em vez de apagar um; e que fechar o
> programa deixa de custar a análise da tarde.

## S-268 · O estudo como dado, fora do `tkinter` ✅ implementada (2026-08-26)

**Problema.** Não existe um estudo. Existe um `ttk.Frame` com três atributos:

```python
self.board = chess.Board()
self.game = chess.pgn.Game()
self.current_node: chess.pgn.GameNode = self.game     # ui/study_panel.py:64-67
```

Tudo o que decide alguma coisa sobre eles está dentro do widget: qual variante entrar
(`_selected_variation_index`, `:264`), o que a lista mostra (`_update_moves_text`, `:271`), o que
"ir para o fim" significa (`go_to_end_of_line`, `:398`). Nada disso é afirmável sem abrir janela, e
é por isso que quase nada disso tem teste.

E há três coisas que nem dentro do widget existem:

- **o endereço do estudo no livro.** O painel recebe `current_fen: Callable[[], str]` e mais nada
  (`app_tkinter.py:389-397`). Não sabe o livro, a página nem o diagrama.
- **um identificador de nó.** Para uma lista clicável (S-274) é preciso ir de um clique ao nó. Os
  objetos `GameNode` não sobrevivem a recarregar o PGN, e um `id()` não sobrevive a nada.
- **a separação entre o comentário e os comandos dele.** Medido com `python-chess` 1.11.2: depois de
  `set_arrows` e `set_eval`, `node.comment` vale
  `'[%csl Rd4][%cal Gf3g5] roque curto [%eval 0.35,18]'`. A biblioteca lê os comandos de volta e
  **não os remove** do texto. Mostrar isso numa caixa de comentário seria mostrar o encanamento.

**Solução.** `src/chess_diagram_ocr/estudo.py`, sem `import tkinter`, com quatro peças.

**1 · A âncora — o endereço do estudo no livro.**

```python
@dataclass(frozen=True)
class Ancora:
    documento: str = ""      # caminho do PDF, como o `document_key` da janela o escreve
    pagina: int = -1         # índice 0-based, como o resto do programa conta página
    diagrama: int = -1       # índice do diagrama na página, na ordem de leitura
    titulo: str = ""         # a legenda, quando o livro deu uma

    @property
    def valida(self) -> bool: ...
    def chave(self) -> str: ...          # estável, para achar o estudo de volta
```

`pagina` é **0-based** porque é assim que `page_index` corre pelo programa inteiro, e o header
`Page` do PGN é 1-based porque é assim que `pdf_to_pgn.py:711` já o escreve. As duas convenções
existem, colidem, e a conversão fica num lugar só.

**2 · O caminho — o identificador de nó que não gasta um byte de arquivo.**

```python
Caminho = tuple[int, ...]     # (), (0,), (0, 3, 1)
def no_em(jogo: chess.pgn.Game, caminho: Caminho) -> chess.pgn.GameNode | None: ...
def caminho_de(no: chess.pgn.GameNode) -> Caminho: ...
```

`()` é a raiz — a posição do diagrama, que **é** um item navegável e que o plugin da pasta de ideias
registra como pendência no próprio `main.tsx` (*"TODO: Allow to show the root position"*).

**A armadilha, e ela é o motivo de o caminho ser derivado e nunca guardado:** promover ou apagar uma
variante **muda os índices**. Um caminho guardado passa a apontar para outro lance — é a mesma forma
de defeito que a S-262 registrou (*a pilha do Tk guarda índice, não conteúdo*). Por isso a regra é:
**quem opera sobre a árvore trabalha com o nó e recalcula o caminho no fim**, nunca o contrário.

**3 · O comentário separado dos comandos.**

```python
def texto_do_comentario(comentario: str) -> str: ...      # sem [%...]
def comandos_do_comentario(comentario: str) -> dict[str, str]: ...
def com_texto(comentario: str, texto: str) -> str: ...    # troca o texto, preserva os comandos
```

`com_texto` é a que impede o defeito óbvio: editar a frase de um lance não pode apagar as setas dele.

**4 · O estudo, e o PGN que ele é.**

```python
@dataclass
class Estudo:
    jogo: chess.pgn.Game
    ancora: Ancora = Ancora()
    invertido: bool = False

    @classmethod
    def de_posicao(cls, fen, *, ancora=Ancora(), lance=None) -> Estudo: ...
    @classmethod
    def de_pgn(cls, texto: str) -> Estudo | None: ...
    def para_pgn(self) -> str: ...
    def vazio(self) -> bool: ...        # sem lance, sem comentário, sem NAG, sem seta
```

Os headers são os de `pdf_to_pgn`, e a lista é fechada: `Event`, `Site`, `Round` (`página.diagrama`),
`Result` (`*`), `Annotator` (`ChessVisionOFF`), `SetUp`, `FEN`, `SourcePDF`, `Page`, `Diagram`, mais
`Orientation` (`white`/`black`) que é nosso e não conflita com nada do padrão.

**`vazio()` é o que decide o que se guarda** (S-270 e S-271): um livro tem ~1.500 diagramas, e um
estudo por diagrama clicado seria uma coleção de posições vazias com aparência de trabalho.

**Critério de aceite.**

- `Estudo.de_pgn(e.para_pgn())` devolve a mesma árvore, os mesmos comentários, os mesmos NAGs, as
  mesmas setas e a mesma âncora, para um estudo com variante dentro de variante;
- `caminho_de(no_em(jogo, c)) == c` para todo caminho válido da árvore, incluindo `()`;
- `texto_do_comentario('[%csl Rd4][%cal Gf3g5] roque curto [%eval 0.35,18]') == 'roque curto'`, e
  `com_texto(mesmo, 'outra frase')` preserva os três comandos;
- um estudo sem lance e sem anotação é `vazio()`; um com só um comentário na raiz, não;
- o PGN gerado é lido de volta por `chess.pgn.read_game` sem erro em `read_game.errors`.

**Testes.** `test_o_pgn_do_estudo_volta_com_a_arvore_inteira`;
`test_o_caminho_e_derivado_e_sobrevive_a_ida_e_volta`;
`test_editar_o_texto_do_comentario_nao_apaga_as_setas`;
`test_estudo_sem_lance_e_sem_anotacao_e_vazio`.

---

## S-269 · O estudo nasce com a vez, o roque e o número que o livro diz ✅ implementada (2026-08-26)

**Problema.** O painel recebe isto:

```python
current_fen=lambda: self.result_panel.fen_var.get() if self.result_panel else ""
```
`app_tkinter.py:393`

E `fen_var` **não é uma FEN**. É `model.fen_at(idx)`, que é `fen_edits[idx]`, que nasce de
`[d.placement for d in items]` (`ui/editor_model.py:157`) — o campo de peças que
`fen_utils.fen_from_class_indices` devolve, sem vez, sem roque, sem contador. O lado a jogar mora na
lista irmã `side_edits` (`:158`) e não é passado. `board_from_fen` completa com `_normalize_fen`, que
crava `w - - 0 1` (`fen_utils.py:165-172`).

Medido, com uma posição do acervo:

```
placement       r1bq1rk1/pp2bppp/2n1pn2/3p4/3P4/2NBPN2/PP3PPP/R1BQ1RK1
FEN do estudo   r1bq1rk1/pp2bppp/2n1pn2/3p4/3P4/2NBPN2/PP3PPP/R1BQ1RK1 w - - 0 1
vez             brancas       <- mesmo quando a S-17 leu "pretas jogam" na legenda
roque           nenhum        <- e-1-g-1 recusado como lance ilegal
```

São três perdas, e as três têm dono no programa:

- **a vez** é a Fase 3 inteira — S-16, S-17, S-19, `SideToMoveSource`, o conflito texto×legalidade.
  A sala a joga fora na porta. O botão "Trocar vez" (`ui/study_panel.py:91`) é o remendo manual;
- **o roque** nunca foi deduzido por ninguém, e `pdf_to_pgn.py:727` já registra o que fazer com essa
  incerteza: `CastlingSource: inferred`;
- **o número do lance** é anotação da Galeria desde a S-67 e editável no Resultado desde a S-71
  (`move_number_of`, `app_tkinter.py:150`). Um estudo de uma posição do lance 23 numera a partir de 1,
  e a lista de lances da Fase 44 mostraria números que não batem com a página impressa.

**Solução.** A âncora da S-268 ganha companhia: a aba passa a receber uma **posição de estudo**
completa, e não uma `str`.

```python
@dataclass(frozen=True)
class PosicaoDeEstudo:
    placement: str
    vez: str = "w"                 # 'w' | 'b', como side_edits o escreve
    lance: int | None = None       # o número impresso, quando a Galeria o anotou
    roque: str = ""                # "" = deduzir; senão o campo da FEN, literal
    ancora: Ancora = Ancora()

    def fen(self) -> str: ...
```

E a dedução de roque, que é o único julgamento novo e por isso é explícito e conservador:

```python
def roque_provavel(placement: str) -> str:
    """Só concede o roque cujo rei E torre estão na casa de origem."""
```

**Por que conceder, e não negar.** As duas escolhas erram, e não erram igual: negar torna **ilegal um
lance legal**, e o usuário não tem como saber por quê — o botão não existe, a peça não anda, e nada
explica. Conceder torna **legal um lance que talvez não fosse**, e isso o usuário vê e corrige, porque
ele está olhando a página. A régua é a mesma do achado da S-208: os dois custos não são simétricos.

E a procedência disso fica escrita: o header `CastlingSource` sai como `inferred` quando o roque foi
deduzido, e não sai quando veio pronto — que é a regra da S-04 aplicada a mais um campo.

**Critério de aceite.**

- estudo aberto de um diagrama com `side_to_move == "b"` abre com as pretas a jogar;
- posição com rei em e1 e torres em a1/h1 abre com `KQ`; com a torre de h1 noutra casa, só `Q`;
- `Orientation` do estudo segue a vez quando o usuário não escolheu — quem estuda uma posição de
  pretas quer o tabuleiro de pretas;
- estudo com número de lance 23 e pretas a jogar imprime `23...` no primeiro lance da lista;
- placement inválido não abre estudo e diz por quê no rodapé, sem `messagebox` — é a regra da S-164.

**Testes.** `test_a_vez_do_diagrama_chega_ao_estudo`;
`test_o_roque_e_concedido_so_com_rei_e_torre_em_casa`;
`test_o_numero_de_lance_da_galeria_numera_a_lista`;
`test_placement_invalido_nao_abre_estudo_e_diz_no_rodape`.

---

## S-270 · Um estudo por diagrama, e trocar de diagrama não apaga nada ✅ implementada (2026-08-26)

**Problema.** É o achado 2 do roadmap, e o caminho tem três linhas:

```python
def sync_with_ocr(self, force=False):     ...  self._load_position(fen, ...)          # :421
def _load_position(self, fen, ...):       ...  self._set_board_state(board, ...)      # :309
def _set_board_state(self, board, ...):        self.game = self._new_game(board)      # :296
```

`self.game` é a árvore inteira. `follow_ocr_var` nasce em `True` (`:73`), então **a configuração
padrão é a destrutiva**: clicar no retângulo do diagrama seguinte na página descarta o que se estava
analisando, sem uma pergunta, sem um aviso, sem um desfazer. "Posição inicial" (`:349`), "Aplicar
FEN" (`:353`) e "Trocar vez" (`:371`) fazem o mesmo pelo mesmo caminho.

Isso é o oposto da regra 7 desta spec, e o programa **já sabe** aplicá-la: `edited_by_hand` existe
para que o cache de página avise antes de descartar correção humana.

**Solução.** `Sala`, em `estudo.py`: uma coleção de estudos com chave de âncora.

```python
class Sala:
    def em(self, ancora: Ancora) -> Estudo | None: ...
    def abrir(self, posicao: PosicaoDeEstudo) -> Estudo: ...   # devolve o guardado, ou cria
    def guardar(self, estudo: Estudo) -> bool: ...             # só o que não é vazio()
    def descartar(self, ancora: Ancora) -> bool: ...
    def estudos(self) -> tuple[Estudo, ...]: ...               # em ordem de página, diagrama
```

`abrir` é o item inteiro: **se já há estudo naquela âncora, ele volta como estava** — árvore, nó
corrente, orientação. Se não há, nasce um da posição. Trocar de diagrama deixa de ser "recomeçar" e
passa a ser "ir para a outra mesa".

Três decisões:

- **estudo vazio não é guardado.** Um livro tem ~1.500 diagramas; clicar em todos criaria 1.500
  posições sem análise, e depois um arquivo com 1.500 partidas de zero lance. `vazio()` da S-268 é a
  régua, e ela é reavaliada na saída de cada estudo, não na entrada.
- **a chave é a âncora, nunca a FEN.** Duas páginas com o mesmo diagrama são dois estudos; o mesmo
  diagrama relido com correção de OCR diferente continua sendo um.
- **sem âncora válida não há sala.** Uma FEN digitada à mão ou uma posição inicial não pertence a
  livro nenhum: ela abre um estudo avulso, que existe enquanto a aba o mostra e não entra na coleção.
  Guardá-lo num nome inventado criaria trabalho que ninguém acha de volta — é a mesma decisão de
  `text/rascunho.gravar`, que devolve `None` para documento sem folha de origem.

E o que **continua** destrutivo passa a perguntar: "Posição inicial" e "Aplicar FEN" sobre um estudo
não-vazio são as duas ações que abandonam a mesa, e elas usam a mesma pergunta de três respostas que
`save_pgn` já usa para o arquivo existente.

**Critério de aceite.**

- abrir o diagrama 2, jogar três lances, abrir o diagrama 1 e voltar ao 2 devolve os três lances e o
  nó em que se estava;
- abrir o diagrama 2 e não jogar nada não deixa estudo na sala;
- a sala responde por âncora, e duas âncoras de páginas diferentes com a mesma FEN são dois estudos;
- FEN digitada à mão abre estudo sem âncora, e ele não entra na coleção;
- "Posição inicial" sobre um estudo com lances pergunta antes; sobre um estudo vazio, não pergunta.

**Testes.** `test_voltar_ao_diagrama_devolve_a_analise`;
`test_estudo_sem_lance_nao_ocupa_lugar_na_sala`;
`test_a_chave_e_a_ancora_e_nao_a_fen`;
`test_posicao_inicial_sobre_estudo_com_lances_pergunta_antes`.

---

## S-271 · O rascunho do estudo, e o PGN por livro ✅ implementada (2026-08-26)

**Problema.** Nenhum dos 20 campos do `AppState` é do estudo (`ui/state.py:62-146`), e a única
saída é `save_pgn`, que abre um `filedialog` e depende de o usuário lembrar. Fechar o programa —
ou o Tk cair numa thread, que é o caso que `BusyRegistry.loses_work` já trata — perde tudo.

A aba de texto resolveu isto para si na S-255, e o desenho está pronto para copiar:
`text/rascunho.py` grava por **inatividade** (não por relógio), só quando está sujo, com
`atomic_write_text`, com chave estável derivada do caminho **resolvido**, com poda por documento, e
**oferece** na abertura em vez de aplicar.

**Solução.** `estudo_arquivo.py`, com uma diferença de desenho que é o item: onde o texto grava **um
rascunho por folha**, o estudo grava **um PGN por livro, com um estudo por partida**.

```python
PASTA_PADRAO = PROJECT_ROOT / "data" / "estudos"
ESPERA_SEGUNDOS = 4.0

def chave_de(documento: str | Path) -> str: ...            # nome legível + 10 hex do caminho resolvido
def caminho_de(documento, *, pasta=None) -> Path: ...      # <nome>_<impressao>.pgn
def gravar(sala: Sala, documento, *, pasta=None) -> Path | None: ...
def carregar(documento, *, pasta=None) -> Sala: ...
```

**Por que um arquivo por livro, e não um por diagrama.** São três razões, e a terceira é a que
decide:

1. dezenas de arquivos por livro numa pasta é depósito, não coleção;
2. a pergunta que se faz depois é *"o que eu já estudei neste livro?"*, e ela se responde abrindo um
   arquivo;
3. **um PGN com muitas partidas é o que o ChessBase e o Scid chamam de base**, e o arquivo que sai
   daqui abre nos dois, com `SourcePDF`/`Page`/`Diagram` dizendo de onde cada estudo veio. É a regra
   2 desta spec levada até o fim: o formato não é nosso.

O custo é reescrever o arquivo inteiro a cada gravação. Medido pelo tamanho: 50 estudos de 30
meios-lances com comentário dão ~90 KB, e `atomic_write_text` escreve isso em milissegundos. Se um
dia não der, o conserto é gravar por lote e não trocar de formato.

**E a recuperação não é uma pergunta.** Aqui o rascunho **é** o arquivo do estudo, não uma cópia de
segurança dele: abrir o livro carrega a sala. A S-255 pergunta porque lá o rascunho concorre com uma
releitura que sai de graça; aqui não há releitura — não existe outro lugar de onde a análise possa
vir. Perguntar seria oferecer apagar o trabalho.

`AppState` ganha o campo `estudo_aberto` (a chave da âncora) e a versão vai a **6**. Um arquivo de
versão anterior abre sem perder nada: o campo que falta cai no padrão, que é "nenhum estudo aberto".

`data/estudos/` entra no `.gitignore`, ao lado de `data/rascunhos/`: é trabalho do usuário sobre o
livro dele, e o livro nem está no repositório.

**Critério de aceite.**

- gravar e carregar a sala devolve os mesmos estudos, com árvore, anotação e âncora;
- o arquivo é um PGN válido com uma partida por estudo, e `chess.pgn.read_game` o percorre inteiro
  sem erro;
- dois livros de mesmo nome em pastas diferentes têm arquivos diferentes (chave pelo caminho
  resolvido, como `ui/state._history_key`);
- a gravação é atômica: interromper no meio não deixa arquivo truncado por cima do anterior;
- fechar o programa **grava** o estudo por gravar, em vez de avisar sobre ele;
- `AppState` de qualquer versão anterior abre sem erro e sem estudo aberto.

> **O aviso de fechamento virou gravação, e a troca é deliberada.** A spec pedia o
> `BusyRegistry.loses_work`, e ele não serve aqui: aquele mecanismo fala de *operação em
> andamento* -- treino, varredura, exportação --, e um estudo por gravar não é uma operação, é um
> documento. `_on_close` chama `salvar_agora()` antes de destruir a janela, e assim não há o que
> avisar. Perguntar "quer salvar?" sobre um arquivo que o programa sabe gravar sozinho é a caixa
> modal que a S-164 existe para tirar da frente. `tem_trabalho_por_gravar()` fica no painel para
> quem precisar da pergunta -- e é o que os testes usam.

**Testes.** `test_a_sala_volta_do_disco_com_tudo`;
`test_o_arquivo_do_livro_e_um_pgn_de_muitas_partidas`;
`test_dois_livros_de_mesmo_nome_nao_se_misturam`;
`test_o_estudo_do_livro_vai_para_o_disco_e_volta`;
`test_sala_que_esvaziou_apaga_o_arquivo`.

---

## S-272 · A aba deixa de se chamar "Análise" ✅ implementada (2026-08-26)

**Problema.** O pedido é explícito — *"na verdade deve ser um 'Tabuleiro de estudo' ou 'Sala de
estudo'"* — e o nome de hoje descreve o que a aba **fazia** quando tinha só o motor: analisar uma
posição. A partir da Fase 43 ela guarda estudos, e "Análise" passa a nomear a menor parte do que ela
é.

E há a armadilha que o próprio `ui/abas.py` documenta:

> "O `AppState` guarda a aba aberta pelo **rótulo** desde a S-156, e um rótulo que agora carrega
> número deixaria de casar assim que a contagem mudasse -- a sessão seguinte cairia na primeira aba,
> em silêncio."

Vale igual para o rename: `rolagem.selecionar_aba` compara `abas.nome_base(...)`, não acha "Análise"
em lugar nenhum, devolve `False`, e a janela abre na primeira aba sem dizer nada.

**Solução.** `abas.ANALISE` vira `abas.ESTUDO = "Estudo"`, e o módulo ganha a tradução:

```python
RENOMEADAS: dict[str, str] = {"Análise": ESTUDO}

def nome_atual(guardado: str) -> str:
    """O nome de hoje da aba que a sessão anterior guardou. `abas.RENOMEADAS` é a única memória
    de que uma aba já se chamou outra coisa."""
```

`rolagem.selecionar_aba` passa por `nome_atual` antes de comparar. O mapa é para sempre: ele custa
uma linha e é a única coisa que impede o rename de virar um defeito silencioso três meses depois,
quando ninguém mais lembra.

**Por que "Estudo" e não "Sala de estudo" nem "Tabuleiro de estudo".** As outras seis abas são
substantivos de uma palavra — Resultado, Revisão, Texto, Dataset, Galeria, Configuração — e a faixa
de abas é onde a S-150 mediu o aperto de largura. "Estudo" é a palavra do pedido, no formato da
barra. A **sala** é o conceito, e ela aparece por inteiro no `docstring` do painel e no roadmap.

O arquivo continua `ui/study_panel.py` e a classe continua `StudyPanel`: nome de arquivo não é
interface, e renomeá-lo custaria diff em `app_tkinter.py` e em seis testes sem mudar nada para quem
usa o programa.

**Critério de aceite.**

- a barra mostra "Estudo" na posição em que mostrava "Análise", entre Resultado e Revisão;
- `AppState` com `active_tab == "Análise"` abre a aba Estudo, e não a primeira;
- `AppState` com um rótulo que não existe nem depois da tradução deixa a janela onde já estava, como
  antes;
- nenhuma pele esconde a aba — é a regra 2 da SPEC_APARENCIA, e `abas.ABAS` continua sendo a tupla
  com que o teste compara a barra montada.

**Testes.** `test_a_aba_analise_guardada_abre_a_aba_estudo`;
`test_rotulo_desconhecido_continua_sem_efeito`;
`test_a_barra_tem_sete_abas_e_estudo_esta_entre_resultado_e_revisao`.

---

# Fase 44 — A lista de lances é a navegação

> A fase do pedido: **lista de lances, variantes e subvariantes**. Ao fim dela a lista é a superfície
> por onde se anda no estudo, e a variante é uma coisa que se vê, se entra, se promove e se apaga.

## S-273 · A lista de lances desenhada como dado ✅ implementada (2026-08-26)

**Problema.** A lista é isto:

```python
exporter = chess.pgn.StringExporter(headers=False, variations=True, comments=True)
texto = self.game.accept(exporter).strip() or "Sem lances."
self.moves_text.insert("1.0", texto)          # ui/study_panel.py:271-277
```

Um parágrafo. Com variantes ele vira `1. e4 e5 2. Nf3 ( 2. Bc4 Bc5 ) Nc6` corrido, e não há como
saber qual lance é o corrente, nem clicar em nenhum, nem distinguir linha principal de subvariante.

**E a parte difícil não é desenhar: é numerar.** A regra do PGN é que o primeiro lance de qualquer
variante imprime o número (com `...` se for das pretas); dentro dela, brancas imprimem `N.` e pretas
não imprimem nada — **exceto** logo depois de um comentário ou de uma subvariante, onde as pretas
voltam a imprimir `N...`. O plugin da pasta de ideias resolve isso com quatro condicionais aninhadas
(`PgnViewer/index.tsx:120-145`) e mesmo assim só cobre profundidade 1.

**Solução.** `ui/estudo_lista.py`, sem `import tkinter`: a lista como uma sequência de trechos.

```python
RAIZ = "raiz"; NUMERO = "numero"; LANCE = "lance"; NAG = "nag"
COMENTARIO = "comentario"; ABRE = "abre"; FECHA = "fecha"; ESPACO = "espaco"

@dataclass(frozen=True)
class Trecho:
    texto: str
    papel: str                       # um dos sete acima
    caminho: Caminho | None = None   # o nó a que um clique leva; None = pontuação
    nivel: int = 0                   # 0 = linha principal; 1+ = variante, subvariante...

def trechos(estudo: Estudo) -> tuple[Trecho, ...]: ...
def texto_de(trechos) -> str: ...
```

`nivel` é o que faz **subvariante** existir na tela: o widget o traduz em recuo e em cor, e a
tradução mora em `ui/tokens.py` como manda a regra 4. O recuo satura em quatro níveis — mais que
isso e a linha some pela direita —, mas a **numeração** não satura nunca, porque ela é a informação.

**E a trava que torna o item seguro:** `texto_de(trechos(e))` tem de ser igual, palavra a palavra, ao
que `chess.pgn.StringExporter(headers=False, variations=True, comments=True)` produz para o mesmo
estudo. Não é elegância: é que a numeração de variante é a parte que todo visualizador de PGN erra, e
o `StringExporter` acerta há anos. Enquanto a igualdade valer, não estamos adivinhando. É a mesma
trava que a S-235 usou para o `para_texto()` do documento rico.

**Critério de aceite.**

- `texto_de(trechos(e))` é igual ao `StringExporter` para: linha simples, variante das brancas,
  variante das pretas, subvariante de terceiro nível, comentário no meio da linha, NAG, e estudo com
  raiz de FEN e primeiro lance das pretas;
- todo trecho de papel `LANCE` tem `caminho` que resolve para um nó, e `caminho_de(no)` devolve o
  mesmo caminho;
- o `nivel` de um lance é a profundidade de variante dele, e o de linha principal é 0;
- estudo sem lance nenhum devolve só o trecho `RAIZ`.

**Testes.** `test_o_texto_da_lista_e_o_do_string_exporter`;
`test_a_subvariante_ganha_nivel_dois`;
`test_todo_lance_da_lista_tem_caminho_que_resolve`;
`test_estudo_sem_lance_tem_so_a_raiz`.

---

## S-274 · A lista clicável, com o lance corrente à vista ✅ implementada (2026-08-26)

**Problema.** Com os trechos da S-273 desenhados, falta o que os torna navegação: clicar num lance
tem de ir até ele, o lance corrente tem de estar visível e marcado, e a **raiz** tem de ser um item —
que é a pendência que o plugin da pasta registra no próprio código (*"TODO: Allow to show the root
position"*, `main.tsx:31`).

**Solução.** O `tk.Text` de 5 linhas vira o desenho dos `Trecho`, com uma tag por trecho de lance.

`tk.Text` e não `ttk.Treeview` por três razões medidas neste projeto: a lista de lances **flui** (as
variantes são parágrafos indentados, não linhas de tabela); as tags já resolvem cor, negrito e recuo
sem cravá-los, o que a `Treeview` não faz; e `ui/texto_panel.py` já provou o desenho por tag aqui
dentro.

Três comportamentos, e o terceiro é o que a S-262 obriga:

- **clique num lance** vai ao nó daquele caminho — que é resolvido **no momento do clique**, e não
  guardado na tag, porque promover ou apagar variante muda os índices;
- **o corrente** aparece com o papel de destaque do tema e é rolado para a vista com
  `see(...)` — o equivalente Tk do `scrollIntoView({block: 'nearest'})` do plugin;
- **redesenhou, remapeia.** As tags do Tk guardam índice de caractere, e um redesenho as invalida.
  A regra é a mesma do editor: refez a lista, refez o mapa de tags. Nada de índice sobrevivendo a
  redesenho — é a S-262 outra vez.

**Critério de aceite.**

- clicar num lance da linha principal, de uma variante e de uma subvariante leva ao nó certo nos três
  casos;
- o lance corrente está marcado e visível depois de qualquer navegação, inclusive quando ele está
  numa variante fora da vista;
- clicar na raiz volta à posição do diagrama;
- depois de promover uma variante, clicar no mesmo texto na tela leva ao mesmo lance — e não ao que
  ocupou o índice antigo.

**Testes.** `test_clicar_num_lance_de_subvariante_leva_ao_no`;
`test_o_lance_corrente_fica_marcado_e_visivel`;
`test_a_raiz_e_clicavel_e_volta_a_posicao_do_diagrama`;
`test_promover_variante_nao_troca_o_destino_dos_cliques`.

---

## S-275 · Entrar, promover, rebaixar e apagar variante ✅ implementada (2026-08-26)

**Problema.** A navegação por variante é um combobox e um botão:

```python
self.variation_combo = ttk.Combobox(variation_row, textvariable=self.variation_var, state="readonly")
ttk.Button(variation_row, text="Entrar", command=self.redo_move)      # ui/study_panel.py:114-126
```

Ele lista os filhos do nó atual e desce um nível. Não se vê variante dois lances à frente; não se
promove; não se rebaixa; não se apaga. E `go_to_end_of_line` carrega uma esquisitice que o próprio
comentário admite: segue a variante escolhida no **primeiro** passo e a principal daí em diante
(`:404-406`).

Pior: **um lance errado fica na árvore para sempre.** `undo_move` só anda para trás (`:377`) — não
remove. Clicou na casa errada, o lance ficou, e não há desfazer.

`python-chess` já traz as quatro operações: `promote`, `promote_to_main`, `demote`,
`remove_variation`.

**Solução.** O combobox sai. Entram cinco comandos sobre o nó corrente, com a semântica do ChessBase
e do Scid:

| comando | o que faz |
|---|---|
| promover a principal | `promote_to_main` — a variante vira a linha, e a linha vira variante |
| promover um nível | `promote` — sobe uma posição entre as irmãs |
| rebaixar | `demote` |
| apagar variante | remove o nó e tudo abaixo dele, e volta ao pai |
| apagar daqui em diante | remove só a continuação, e mantém o nó |

Três decisões:

- **apagar pergunta quando há o que perder.** Apagar um nó folha é o desfazer de um clique errado, e
  perguntar ali seria atrito. Apagar uma subárvore com comentário ou com mais de um lance é perder
  trabalho: pergunta. É a regra 7 desta spec.
- **a operação trabalha com o nó, e o caminho é recalculado no fim.** É a armadilha da S-268, e é
  aqui que ela morde: promover reordena as irmãs, e um caminho guardado antes da operação aponta para
  outro lance depois dela.
- **o desfazer é o da janela, e não um novo.** A S-243 já decidiu quem recebe `Ctrl+Z` conforme o
  foco, com `ui/desfazivel.Desfazivel`. A sala se registra como o terceiro desfazível — se criar a
  própria pilha, `Ctrl+Z` na aba de estudo mexerá no tabuleiro de outra aba, que é o defeito que
  aquele item mediu com as setas.

A pilha guarda o **PGN do estudo**, e não uma sequência de operações inversas: o estudo inteiro cabe
em alguns kilobytes de texto, gravar antes de cada operação destrutiva é uma linha, e desfazer é
recarregar. Reimplementar o inverso de `promote_to_main` seria refazer, com bugs, o que a
serialização já dá de graça — é a mesma decisão que `ui/historico.py` tomou para o tabuleiro.

**Critério de aceite.**

- promover a principal troca a linha e a variante, e a árvore continua com os mesmos lances;
- apagar uma variante folha não pergunta; apagar uma com comentário ou com dois lances, pergunta;
- apagar o nó corrente deixa o estudo no pai dele, e nunca num nó que não existe mais;
- desfazer depois de apagar devolve a variante inteira, com comentário e setas;
- `Ctrl+Z` com o foco no editor de texto de outra aba não toca no estudo — é a S-243 valendo.

**Testes.** `test_promover_a_principal_troca_as_duas_linhas`;
`test_apagar_variante_com_comentario_pergunta_antes`;
`test_apagar_o_no_corrente_deixa_no_pai`;
`test_desfazer_devolve_a_variante_apagada`.

---

## S-276 · A sala tem duas colunas ✅ implementada (2026-08-26)

**Problema.** O layout é uma pilha vertical: três linhas de botão, a linha do combobox, dois rótulos,
o campo de FEN, o tabuleiro, a caixa de lances de 5 linhas e a seção do motor
(`ui/study_panel.py:84-183`). O tabuleiro fica com o que sobrar, e a lista fica com 5 linhas — que
com a Fase 44 passa a ser a superfície principal e não cabe.

Todo programa de xadrez usa a mesma repartição, e a captura `imgs/chess-study-variants.png` da pasta
de ideias mostra por quê: **tabuleiro à esquerda, lances à direita, anotação embaixo.** Lê-se a linha
com o olho ao lado do tabuleiro, e não abaixo dele.

**Solução.** Um `ttk.PanedWindow` horizontal: tabuleiro à esquerda, lista à direita, com o divisor
lembrado no `AppState` pelo mesmo desenho de `sash_fraction` que a janela já usa (`ui/state.py:98`).

**Critério de aceite.**

- tabuleiro e lista dividem a largura, e o divisor volta onde estava na sessão seguinte
  (`AppState.estudo_divisor`, gravado por `fracao_do_divisor` e reposto por `posicionar_divisor`);
- fração `0.0` -- "nunca guardada" -- deixa o peso do `PanedWindow` decidir, e não crava 0,6;
- a lista rola sozinha, com barra própria;
- nenhuma cor, fonte ou espessura crava aqui: tudo vem de `ui/tokens.py` e `ui/tipografia.py`, e as
  tags são refeitas em `theme.ao_repintar` quando a pele muda.

**Testes.** `test_o_divisor_volta_onde_estava`; `test_fracao_zero_deixa_o_peso_decidir`.

---

# Fase 45 — A anotação, que é o que o livro tem

> Ao fim dela um lance carrega o que o livro carrega: um símbolo, uma frase e um desenho. E tudo isso
> sai num PGN que o ChessBase, o Scid e o Lichess leem.

## S-277 · O comentário do lance ✅ implementada (2026-08-26)

**Problema.** Não há onde escrever. Um livro de xadrez é anotação, e um estudo sem comentário é um
tabuleiro com histórico. O plugin da pasta de ideias — um projeto de hobby — tem comentário por
lance desde a versão 1.0.0, com editor de texto rico e sincronia ao navegar
(`CommentSection/index.tsx`).

**Solução.** Uma caixa de comentário sob a lista, ligada ao **nó corrente**: navegar troca o
conteúdo, sair do lance grava no nó.

Duas decisões:

- **o texto é o texto, e os comandos ficam.** `com_texto` da S-268 é a única porta de escrita, e é ela
  que impede o defeito óbvio — reescrever a frase de um lance apagando as setas dele.
- **o comentário é `str` no PGN, e por enquanto só isso.** O `DocumentoRico` da S-235 é a estrutura
  certa para quando o comentário receber um parágrafo do livro com o itálico que ele tinha (Fase 47,
  S-283), e a fronteira já existe: `rico.para_texto()` é o que vai para o PGN. Guardar rico **antes**
  de haver de onde colar rico seria formato sem cliente — é o achado 1 da SPEC_EDITOR pelo avesso.

**Critério de aceite.**

- navegar troca o comentário mostrado, e o que foi digitado fica gravado no nó em que foi escrito;
- escrever um comentário num lance que tem setas preserva as setas;
- comentário vai e volta pelo PGN, inclusive com acentos;
- comentário na raiz é o comentário da posição do diagrama, e sai no PGN antes do primeiro lance.

**Testes.** `test_o_comentario_segue_o_no_corrente`;
`test_escrever_comentario_preserva_as_setas`;
`test_comentario_da_raiz_sai_antes_do_primeiro_lance`.

---

## S-278 · Os símbolos de avaliação (NAG) ✅ implementada (2026-08-26)

**Problema.** `!`, `?`, `!?`, `?!`, `⩲`, `±`, `∞` são o vocabulário do livro — e são justamente o que
`text/notacao.py` já reconhece no sufixo de um lance impresso (`_SUFIXO = r"[+#!?±∓⩲⩱=]*"`,
`notacao.py:73`). O estudo não tem onde pô-los.

**Solução.** Os NAGs de `chess.pgn`, num conjunto fechado e pequeno, com o símbolo que o livro imprime
e o nome em português:

| NAG | símbolo | nome |
|---|---|---|
| 1 | `!` | bom lance |
| 2 | `?` | lance fraco |
| 3 | `!!` | lance excelente |
| 4 | `??` | erro grave |
| 5 | `!?` | lance interessante |
| 6 | `?!` | lance duvidoso |
| 10 | `=` | posição equilibrada |
| 13 | `∞` | posição obscura |
| 14 / 15 | `⩲` / `⩱` | ligeira vantagem |
| 16 / 17 | `±` / `∓` | vantagem clara |
| 18 / 19 | `+-` / `-+` | vantagem decisiva |

Duas regras: **os de lance são exclusivos entre si e os de posição também**, e um lance pode ter um de
cada — que é como o livro escreve (`13.♗g5!? ⩲`). E o desenho do símbolo na lista é papel de
`ui/tokens.py`, não hexadecimal (regra 4).

**Critério de aceite.**

- pôr `!` num lance que já tem `?` troca, não soma; pôr `±` num lance que tem `!` soma;
- o símbolo aparece na lista imediatamente depois do lance, e entra no `texto_de` que a S-273 compara
  com o `StringExporter`;
- os NAGs vão e voltam pelo PGN;
- NAG desconhecido lido de um PGN de fora não quebra a lista — é mostrado como `$NN`.

**Testes.** `test_nag_de_lance_e_exclusivo_e_nag_de_posicao_soma`;
`test_o_simbolo_entra_no_texto_que_o_string_exporter_confere`;
`test_nag_desconhecido_de_pgn_alheio_nao_quebra`.

---

## S-279 · As setas e as casas marcadas ✅ implementada (2026-08-26)

**Problema.** Um livro desenha sobre o diagrama: a seta do plano, o círculo na casa fraca. O
tabuleiro não sabe desenhar nada disso — `BoardRenderer` faz casas, peças, coordenadas, heatmap e
contornos, e mais nada (`ui/board_render.py:358-566`).

E o gesto está livre: o botão direito em modo de jogo não faz nada, porque `BoardModel.erase` começa
com `if self.mode != "edit": return BoardChange()` (`board_model.py:322`).

**Solução.** Arrastar com o botão direito desenha seta; clicar com o botão direito marca a casa; o
mesmo gesto de novo apaga. É o gesto do Lichess, do Chess.com e do ChessBase, e ele não disputa nada
com o botão esquerdo, que continua jogando.

**E elas moram no PGN**, não num arquivo nosso: `[%cal Gf3g5]` para seta e `[%csl Rd4]` para casa, que
é o que `node.set_arrows()` já grava e o que Lichess, ChessBase e Scid leem. Medido, ida e volta com
`python-chess` 1.11.2:

```
grava   4. O-O $1 { [%csl Rd4][%cal Gf3g5] roque curto [%eval 0.35,18] } *
lê      [Arrow(D4, D4, color='red'), Arrow(F3, G5, color='green')]
```

As cores são as quatro do padrão — verde, vermelho, amarelo, azul —, escolhidas por modificador
(`Shift`, `Alt`, `Ctrl`) como nos três programas, e desenhadas com o papel de `ui/tokens.py` para
que sobrevivam à troca de tema.

**Critério de aceite.**

- arrastar com o direito de f3 a g5 desenha a seta e a grava no nó corrente; repetir o gesto apaga;
- navegar troca as setas na tela — elas são do lance, não do tabuleiro;
- as setas vão e voltam pelo PGN e são lidas por `node.arrows()`;
- desenhar seta não altera o texto do comentário do lance;
- a seta é desenhada sobre as peças e não as esconde.

**Testes.** `test_a_seta_do_botao_direito_vai_para_o_no`;
`test_navegar_troca_as_setas_na_tela`;
`test_a_seta_sobrevive_a_ida_e_volta_pelo_pgn`;
`test_desenhar_seta_nao_mexe_no_texto_do_comentario`.

---

# Fase 46 — A aba é do programa

> Nenhum item desta fase acrescenta xadrez. Todos existem porque a sala, depois das Fases 43 a 45,
> tem uns vinte comandos e **nenhum deles existe** para o resto da janela — que é o achado 12 do
> roadmap, e é a S-161 pela terceira vez.

## S-280 · Os comandos do estudo no catálogo ✅ implementada (2026-08-26)

**Problema.** Medido no roadmap: 13 botões na aba, **0** dos 90 comandos de `ui/comandos.py`. Logo,
0 na paleta de comandos (S-231), 0 na legenda de atalhos (S-165), 0 itens de menu, e nenhuma das
três peles (S-221/S-223) consegue desenhar um controle da aba — porque uma pele desenha o
**catálogo**, e o que não está nele não existe para ela.

Depois das Fases 43 a 45 são mais de vinte comandos fora do registro, não treze.

**Solução.** Todo comando da sala entra em `CATALOGO`, no grupo que a pergunta do grupo decide.
`ui/comandos.py` já corta `OCR` (age sobre a página aberta) de `ACERVO` (age sobre o livro ou sobre o
modelo). O estudo abre um terceiro caso — *age sobre a análise da posição* —, e a decisão é entre
criar o grupo `ESTUDO` e distribuir os comandos pelos seis que existem.

**Cria-se o grupo.** O conjunto de seis é fechado *hoje* porque ele é "os cinco menus com Ferramentas
partido em dois", e a sala não é nenhum dos cinco: promover variante não é `EDICAO` (que é edição de
texto e de tabuleiro), não é `VISUALIZACAO` (que não muda dado) e não é `OCR`. Distribuí-los faria a
fita da S-227 mostrar "promover variante" debaixo de "Edição", ao lado de "colar" — o que é
exatamente o tipo de vizinhança que a S-324 existe para impedir.

**Critério de aceite.**

- todo comando da sala tem entrada no catálogo, com rótulo, grupo, papel e ícone;
- `comandos.acoes_fora_do_catalogo` das ações que o painel liga devolve lista vazia;
- a paleta de comandos acha cada um pelo nome;
- nenhuma pele esconde comando da sala — é a regra 2 da SPEC_APARENCIA, e o inventário da S-233 é o
  que a confere.

**Testes.** `test_toda_acao_da_sala_esta_no_catalogo`;
`test_o_grupo_estudo_e_exatamente_a_tabela_da_aba`; `test_o_grupo_tem_rotulo_legivel`;
`test_todo_metodo_declarado_existe_no_painel`; `test_a_paleta_de_comandos_lista_e_executa_cada_um`.
### O que entrou, e as duas decisões que a implementação mudou

**O grupo `ESTUDO` é o sétimo, e o conjunto continua fechado.** O critério para abrir um grupo ficou
escrito em `ui/comandos.GRUPOS`: **haver uma pergunta que nenhum dos outros responde** -- e não
haver comandos demais num deles. `OCR` age sobre a página aberta, `ACERVO` sobre o livro ou sobre o
modelo, `ESTUDO` sobre a análise da posição. São **24 comandos**, e a tabela que os ata aos métodos
é `study_panel.COMANDOS_DA_ABA`: a janela gera as ligações dela, como já fazia com as do editor, e
não há um `lambda p: p.promover_variante()` no `app_tkinter.py`.

**Os dois interruptores não viraram `Checkbutton`, e a razão é de alcance.** "Mostrar o recorte" e
"Análise contínua" são estado, e o desenho óbvio seria uma caixa marcável na barra -- como
`modo_bloco` na aba de texto. Mas um `Checkbutton` **não é comando**: o estado dele vive no widget,
e o mesmo comando disparado pela paleta da S-231 ou pelo menu não teria onde ler o valor de antes --
o clique de lá seria uma alternância cega, ou nada. Os dois entraram como **comando que troca o
próprio texto** (`Comando.rotulo_alternado`, que existe desde a S-222 justamente para isto), e
`alternar_recorte` é uma função só que as três portas chamam.

O preço, dito: `test_ui_comandos.test_so_alterna_quem_precisa` deixou de ser "um, e é o único" e
passou a ser três. O `modo_bloco` continua sendo `Checkbutton` -- trocá-lo seria mexer numa aba que
ninguém pediu para mexer, e a divergência fica registrada aqui em vez de ser descoberta depois.

---

## S-281 · As teclas do estudo, e o fim do `bind` no canvas ✅ implementada (2026-08-26)

**Problema.** A aba liga quatro teclas por fora da tabela da S-161:

```python
canvas.bind("<Left>",  lambda _e: self.undo_move())
canvas.bind("<Right>", lambda _e: self.redo_move())
canvas.bind("<Home>",  lambda _e: self.go_to_start_of_line())
canvas.bind("<End>",   lambda _e: self.go_to_end_of_line())      # ui/study_panel.py:141-144
```

Três consequências, e a terceira já custou um item:

1. **as teclas só funcionam depois de clicar no tabuleiro**, porque o canvas só ganha foco no
   `_on_press`. Quem abre a aba e aperta `←` muda de diagrama;
2. **elas não aparecem em lugar nenhum** — nem na legenda da S-165, nem no menu, nem num tooltip;
3. **elas sombreiam `←`/`→` globais**, e `shortcuts.owns_key` existe justamente por causa deste
   `bind`: a docstring dele cita este arquivo pelo nome. O conserto de lá foi tornar a colisão
   inofensiva; o conserto certo é não a ter.

**Solução.** As teclas da sala entram em `ui/atalhos.py`, como as do editor entraram em
`TECLAS_DO_EDITOR`, e o painel declara `ACOES_PROPRIAS` — que é o mecanismo da S-244: *"a aba atende
esta ação global enquanto tem o foco"*. `←`/`→` continuam sendo "diagrama anterior/próximo" em toda a
janela e passam a ser "lance anterior/próximo" **enquanto a aba de estudo está em foco**, com
`atalhos.conferir_dono` cobrando a declaração na montagem.

**Critério de aceite.**

- `←`/`→` na aba de estudo andam pelos lances sem exigir clique prévio no tabuleiro;
- `←`/`→` nas outras abas continuam trocando de diagrama;
- toda tecla da sala aparece na legenda de atalhos;
- `test_ui_legenda` continua sem achar literal `<Control...>` fora de `ui/atalhos.py`.

**Testes.** `test_a_aba_declara_e_atende_as_quatro`;
`test_as_quatro_acoes_andam_pelo_estudo`; `test_a_legenda_conta_os_dois_destinos`;
`test_a_seta_e_da_caixa_de_comentario_enquanto_o_cursor_esta_nela`;
`test_o_canvas_do_tabuleiro_nao_declara_mais_tecla_nenhuma`.
### O que entrou: quatro teclas saíram do canvas, e duas nasceram fora dele

Os quatro `canvas.bind` sumiram. `study_panel.ACOES_PROPRIAS` declara as quatro ações, `atender`
diz qual método atende cada uma, e `atalhos.conferir_dono` cobra a declaração na montagem.

**Duas coisas mudaram em relação ao que a spec previa, e as duas melhoraram o resto do programa.**

**1 · `Home` e `End` viraram comandos globais, e é isso que os deixou entrar.** A spec supunha que
bastava reusar teclas existentes. `←` e `→` existiam (`diagrama_anterior`, `proximo_diagrama`);
`Home` e `End` **não existiam em lugar nenhum**, e aqui não entra tecla sem comando global -- a
tabela da S-161 recusa. A pergunta virou então *o que Home e End fazem no resto da janela?*, e a
resposta óbvia estava faltando desde a S-70: `Page Up` e `Page Down` viram **uma** página, e nada
levava à primeira ou à última. `primeira_pagina` e `ultima_pagina` entraram no catálogo, no menu Ver
e na tabela de atalhos, e a sala as toma para si quando tem o foco.

`Atalho` ganhou `na_sala`, irmão de `no_editor`, e a legenda passou a mostrar **três** destinos por
tecla em vez de dois -- num laço, para o quarto entrar sem ninguém editar `legenda._descricao`.

**2 · O foco vem com a aba.** Declarar as ações não bastava: `atalhos.destino` sobe pelo `master` a
partir do widget em foco, e quem acabou de trocar de aba tem o foco no `Notebook` -- que não é filho
do painel. A aba passou a dar o foco ao canvas do tabuleiro ao ser mapeada (`self.bind("<Map>", ...)`),
e é isso que faz "abrir a aba e apertar `←`" andar pelo estudo em vez de trocar de diagrama.

**E a caixa de comentário continua com as setas dela.** `acoes_proprias` devolve **vazio** enquanto o
cursor está lá dentro. Sem essa pergunta, escrever um comentário moveria o estudo a cada seta -- e a
guarda de `shortcuts.ignores_widget` não salvaria, porque `guard` consulta o dono **antes** de ceder
ao widget de texto. É o caso em que o mecanismo da S-244 precisa ser dinâmico, e não uma constante.

---

# Fase 47 — O livro entra na sala

> É a fase que só este programa pode escrever. Nenhum visualizador de PGN do mundo tem a página ao
> lado.

## S-282 · O recorte do diagrama ao lado do tabuleiro ✅ implementada (2026-08-26)

**Problema.** Estuda-se uma posição que **um modelo leu de uma imagem**, com 0,99 de acurácia por
casa e bem menos por tabuleiro (`docs/BASELINE.md`). Conferir o que está no tabuleiro contra o que
está impresso é o gesto mais frequente de quem usa este programa — e exige trocar de aba.

`RecognizedDiagram.board_rgb` é o recorte, e ele já está carregado na memória quando a aba de
Resultado o mostra.

**Solução.** Uma miniatura do recorte ao lado do tabuleiro, do tamanho de um terço dele, com clique
para ampliar. A aba de texto já resolveu o problema técnico de manter a referência viva
(`ui/texto_panel.py:117-119`, *"o Tk não segura a imagem"*).

**Critério de aceite.** A miniatura é a do diagrama âncora do estudo; estudo sem âncora não mostra
miniatura nem espaço vazio; trocar de estudo troca a miniatura; a imagem não é recarregada do disco a
cada navegação de lance.
**Testes.** `test_o_recorte_e_o_do_diagrama_ancora`; `test_a_imagem_nao_e_refeita_a_cada_lance`;
`test_trocar_de_diagrama_troca_o_recorte`; `test_sem_ancora_nao_ha_recorte_nem_espaco_reservado`;
`test_o_clique_amplia_no_tamanho_em_que_o_modelo_leu`.

### O que entrou (2026-08-26)

A miniatura mora na coluna do tabuleiro e **não reserva espaço quando não há o que mostrar**:
estudo sem âncora não desenha retângulo vazio. Ela é reconstruída quando a **âncora** muda, e não a
cada lance -- navegar redesenha o tabuleiro dezenas de vezes por minuto, e reamostrar o recorte
junto seria trabalho por nada; o teste afirma isso contando quantas vezes o recorte foi *pedido*.

Quem sabe qual recorte é o certo é `study_panel.recorte_do_painel`, e ele devolve `None` quando o
editor está mostrando **outra** página. A distinção é o item: mostrar o recorte do diagrama
selecionado *agora* ao lado da posição de um estudo *de outro diagrama* seria pôr duas posições
diferentes lado a lado dizendo que são a mesma -- exatamente o defeito que a miniatura existe para
impedir.

O clique amplia numa janela própria, no tamanho em que o modelo leu (~400 px contra os 220 da
coluna). Janela e não zoom no lugar: a comparação que se está fazendo é com o tabuleiro ao lado, e
uma imagem grande na coluna empurraria o tabuleiro para fora.

---

## S-283 · A linha impressa vira variante — e é o que fecha a S-208 ✅ implementada (2026-08-26)

**Problema.** A S-208 está **parcial** desde 2026-08-24, e a spec dela diz exatamente o que falta:

> "Não entra `validar` -- a legalidade pela posição, com o `chess`, e o `.review.pgn` de quem não
> fecha. Por isso o item fica **parcial** e não implementado. [...] a metade que valida é a que dá o
> PGN de partida."

`fatiar` já separa lance de prosa; o que não existe é quem diga se `♘d7` é possível *nesta* posição.
E o item registra um falso positivo que **só a legalidade separa**: `Capablanca` p72, `7` + `2` →
`72`, "estruturalmente idêntico ao caso que se quer consertar".

A sala de estudo é onde essa metade tem cliente: a linha impressa ao lado do diagrama 3 é uma
variante da posição do diagrama 3, e a posição do diagrama 3 é a raiz do estudo.

**Solução.** `text/notacao.validar(fatias, tabuleiro)`, com o contrato da S-15 — **propõe, marca, não
reescreve calado**: lance que fecha vira `chess.Move`; lance que não fecha sai com o motivo, e a
linha para ali. Do lado da sala, um comando que lê o parágrafo ligado ao diagrama (a S-249 já ata
linha a diagrama) e o oferece como variante, mostrando onde parou quando parou.

A ambiguidade branca/preta das figurinas continua sendo o que a S-208 diz que é: insolúvel
visualmente, resolvida pela paridade do número de lance.

**Critério de aceite.** Linha sintética com figurinas vira lances válidos com o lado certo por
paridade; lance ilegal na posição corrente não é reescrito e sai com o motivo; a variante entra como
variante da raiz e não sobrescreve a linha que já estava; e a S-208 passa de **parcial** a
**implementada**, com a seção dela em `SPEC_TEXTO.md` registrando o que entrou.
**Testes.** Do lado do núcleo, `tests/test_notacao_validar.py` -- entre eles
`test_o_lado_sai_da_posicao_e_nao_do_glifo`, `test_lance_ilegal_para_a_linha_e_nomeia_o_motivo` e
`test_numero_de_lance_que_nao_bate_com_a_posicao_e_acusado`. Do lado da sala,
`test_a_linha_impressa_entra_na_arvore`, `test_a_linha_que_nao_fecha_para_e_diz_onde`,
`test_a_procedencia_da_linha_fica_escrita_no_pgn` e `test_a_linha_entra_a_partir_do_no_corrente`.

### O que entrou (2026-08-26)

`text/notacao.validar(tokens, board)` devolve uma `LinhaValidada`: os lances que fecharam, e **onde
parou** quando parou. O detalhe da S-208 que a implementação afinou está escrito lá: o lado da
figurina sai da **posição**, e não da paridade -- a paridade era o que sobrava quando não havia
tabuleiro, e aqui há.

Do lado da aba, o comando lê o parágrafo que a S-249 ata àquele diagrama
(`texto_panel.notacao_do_diagrama`) e joga a linha **a partir do nó corrente**: quem aperta o botão
depois de andar três lances quer a continuação dali. Lance que já existe é seguido em vez de
duplicado, pela mesma regra de `push_move`, e a procedência fica no PGN como comentário de entrada
da variante -- "linha impressa no livro".

**Duas ausências, ditas.** O `.review.pgn` não entrou, e a razão está na seção da S-208 em
`SPEC_TEXTO.md`: quem consome `validar` hoje é uma aba, que mostra o lance que travou e o motivo no
rodapé com os anteriores já na árvore. E o comando **exige a folha lida na aba Texto** -- ler custa
de 1 s a 40 s, e disparar isso de dentro da sala transformaria um clique de análise numa espera sem
aviso. A aba diz o que fazer em vez de decidir por quem estuda.

---

## S-284 · Voltar para a página de onde o estudo veio ✅ implementada (2026-08-26)

**Problema.** O estudo sabe o livro, a página e o diagrama desde a S-268, e não há como usar isso
para ir até lá. Quem estuda uma posição quer reler o parágrafo.

**Solução.** Um comando que abre o PDF na página da âncora, com o diagrama marcado — o mesmo caminho
que a aba Galeria já usa (`on_page_request`). Vale também no sentido inverso: o retângulo do
diagrama na página diz se já há estudo nele.

**Critério de aceite.** O comando diz por que não quando não há âncora; o livro que não está mais
no lugar diz isso no rodapé e não levanta.

**Testes.** `test_o_comando_leva_a_pagina_da_ancora`; `test_sem_ancora_ele_diz_por_que_nao`;
`test_livro_que_saiu_do_lugar_diz_no_rodape_e_nao_levanta`.

### O que entrou, e o que **não** entrou (2026-08-26)

Entrou o sentido sala → página: o comando leva o visualizador à página da âncora, e recusa quando o
livro aberto não é aquele -- `_abrir_pagina_do_estudo` compara o `document_key` antes de navegar.

**Não entrou o sentido inverso** -- "o retângulo do diagrama na página diz se já há estudo nele". Ele
é uma cor a mais no visualizador, e depois da S-158 o tabuleiro e a página não têm matiz livre: azul,
violeta, vermelho, verde e azeitona já têm dono, e escolher a sexta sem medir contraste contra as
outras cinco é o que aquele item existe para impedir. Fica registrado como não feito, e o que ele
custa é uma medição de matiz -- não um desenho novo.

**E o comando fica ativo sem âncora, em vez de cinza.** A spec pedia cinza; a S-165 mediu o que
custa um controle cinza sem explicação, e aqui a explicação cabe numa frase de rodapé: *"este estudo
não veio de um diagrama do livro"*. Botão que responde é melhor que botão que não responde.

---

# Fase 48 — O motor, e a base de partidas

## S-285 · A análise contínua, e a avaliação que fica no lance ✅ implementada (2026-08-26)

**Problema.** `analyse()` é um tiro único: aperta-se o botão, uma thread roda `movetime` e o
resultado vai para dois `StringVar` (`ui/study_panel.py:186-215`). Navegar apaga. Voltar exige
analisar de novo. E há um defeito de ordem que a Fase 43 torna visível: a thread guarda a posição,
mas o `after(0, ...)` não confere se o estudo ainda é o mesmo — trocar de diagrama durante uma
análise escreve a avaliação da posição anterior sobre a nova.

**Solução.** Análise que segue o nó corrente, com cancelamento ao navegar, e `node.set_eval()`
gravando `[%eval 0.35,18]` no PGN. A avaliação passa a ser do lance, como a seta e o comentário; e
como ela mora no PGN padrão, o Lichess e o ChessBase a leem.

**Critério de aceite.** Navegar descarta a resposta atrasada e nenhuma escreve na posição errada; a
avaliação gravada volta pelo PGN; sem motor a seção continua não existindo (S-33).

**Testes.** `test_a_resposta_atrasada_da_posicao_anterior_e_descartada`;
`test_a_avaliacao_fica_no_lance_e_volta_pelo_pgn`;
`test_a_avaliacao_nao_entra_na_pilha_de_desfazer`;
`test_a_avaliacao_sozinha_nao_cria_estudo_na_sala`; `test_a_secao_do_motor_nao_e_montada`.

### O que entrou, e a consequência que só apareceu na implementação (2026-08-26)

**A guarda é uma geração, e não um cancelamento.** Cancelar um `analyse` no meio exigiria interromper
a conversa UCI, e `EngineAnalyzer` serializa o acesso com um lock justamente porque duas threads
falando com o mesmo processo embaralham as respostas. O que se cancela é o **efeito**: `_geracao`
cresce a cada mudança de nó -- em `refresh`, que é o único ponto por onde toda navegação passa --, e
a resposta que chega com geração velha não escreve nada.

**E gravar a avaliação no nó teve dois efeitos colaterais, os dois consertados aqui.**

1. **A pilha de desfazer.** `[%eval]` no lance marca o estudo como sujo, e o desenho da S-275 registra
   o PGN na pilha a cada mudança. Com a análise contínua ligada, `Ctrl+Z` passaria a desfazer números
   que o motor escreveu sozinho. `_marcar_sujo(historico=False)` é o desvio: grava e não empilha.
2. **`Estudo.vazio()`.** A avaliação mora dentro de `comment`, então navegar com o motor ligado
   deixaria todo nó visitado com comentário -- e *passar o olho* num diagrama criaria um estudo dele
   na sala do livro. `vazio()` passou a perguntar por `texto_do_comentario` e pelas setas, e não por
   `comment`: **o que a máquina escreveu não conta como trabalho humano.**

---

## S-286 · Os lances candidatos, e o que vira variante ✅ implementada (2026-08-26)

**Problema.** O motor devolve uma linha. Um estudo quer as três ou quatro melhores, que é o que
transforma "o motor prefere isto" em "estas são as opções".

**Solução.** `MultiPV` no `EngineAnalyzer`, os candidatos na tela em ordem, e um comando que põe a
linha escolhida na árvore como variante — com a procedência dizendo que ela é do motor, e não de
quem estuda. **A procedência é a regra 2 da SPEC_EDITOR aplicada a lance:** o que a máquina sugeriu e
o que a pessoa jogou não podem ficar indistinguíveis no arquivo.

**Critério de aceite.** O motor devolve até três linhas em ordem; motor que não aceita `MultiPV`
devolve uma em vez de erro; a linha escolhida entra como variante do nó corrente, sem duplicar lance
que já estava; e o PGN diz que ela é do motor.

**Testes.** `test_os_candidatos_aparecem_em_ordem`;
`test_a_linha_do_motor_vira_variante_com_a_procedencia`;
`test_sem_resposta_do_motor_ele_diz_isso_em_vez_de_inventar`.

### O que entrou, e onde a procedência foi parar (2026-08-26)

`EngineAnalyzer.analyse_multi` é o par de `analyse`, e as duas montam a `Evaluation` pelo mesmo
`_avaliacao_de` -- duas cópias do desmonte divergiriam no primeiro campo novo. Motor que recusa
`MultiPV` devolve uma linha em vez de erro, pela mesma degradação que `start` já aplica a `Threads`.

**A procedência não foi para `Annotator`, e a spec estava errada sobre isso.** `Annotator` é header
de **partida**: pô-lo ali diria que o estudo inteiro é do motor, quando o que é do motor é uma
variante. O lugar padrão para dizer de onde vem uma linha é o **comentário de entrada** dela --
`starting_comment` --, que o ChessBase e o Lichess mostram antes do primeiro lance da variante. Sai
como `motor.exe: +0,35`, com o nome do binário e a avaliação que o fez sugerir aquilo.

---

## S-287 · Que partidas chegaram a esta posição ✅ implementada (2026-08-26)

**Problema.** `games_db.scan_by_positions`, `PositionIndex` e `match_positions` já respondem isso —
é o que a S-72/S-73 usa para preencher os headers do PGN exportado, e `games_index.build_index` já
mantém o índice SQLite. Do tabuleiro de estudo não há botão, e é o gesto mais usado do ChessBase.

**Solução.** Um comando que consulta a base do usuário pela posição corrente e lista as partidas, com
os lances jogados dali e a frequência de cada um. A base é do usuário, mora em `pgn_database/`, está
fora do repositório e nada sai da máquina — como já vale para a S-73.

**Critério de aceite.** Sem base indexada, o comando diz o que fazer em vez de ficar cinza; a consulta
não trava a janela; e a posição com mais partidas do que o cache guarda **diz que a lista é menor**.

**Testes.** `tests/test_estudo_partidas.py` inteiro -- entre eles
`test_posicao_nunca_perguntada_diz_isso_e_ensina_o_comando` e
`test_lista_menor_que_a_contagem_diz_que_e_menor` --, mais
`test_com_partidas_a_janela_lista_o_que_a_base_guardou` do lado da aba.

### O que entrou, e o que **não** entrou (2026-08-26)

`estudo_partidas.consultar` lê o cache de posições (`games_cache.PositionStore`) e **nunca** a base.
O motivo está medido em `cvoff-games`: reproduzir os lances da base inteira custa ~104 min em dez
processos, e *"o custo é da PASSADA, não do livro"* -- perguntar por uma posição custa o mesmo que
perguntar por todas. Um botão que fizesse isso travaria a janela por uma hora.

**A consequência é uma limitação honesta, e o módulo existe para dizê-la em vez de escondê-la.** São
**quatro** estados e não dois: sem base, **não perguntada**, perguntada e sem partida, e achou.
Colapsar o segundo no terceiro responderia "nenhuma partida chega aqui" sobre uma pergunta que
ninguém fez -- e a raiz de um estudo costuma estar no cache (é um diagrama do livro), enquanto a
posição depois de três lances de análise nunca está.

**Não entrou "os lances jogados dali e a frequência de cada um"**, que é a segunda metade da janela
de aberturas do ChessBase. Não é escolha de escopo: `CachedPosition` guarda contagem e cabeçalhos e
**não guarda a continuação**, e derivá-la exigiria reproduzir as partidas -- a passada de uma hora,
outra vez. O que a janela mostra é a lista de partidas com lance e vez, que é o outro painel daquele
programa.

---

# Fase 49 — Entrada e saída

## S-288 · Colar PGN/FEN e abrir um `.pgn` ✅ implementada (2026-08-26)

**Problema.** Não há entrada. `apply_fen` lê o campo da própria aba, e é tudo. O plugin da pasta de
ideias **começa** por aí: o gesto de abertura dele é um modal de colar PGN
(`ChessStringModal.ts`), e ele aceita PGN ou FEN no mesmo campo, decidindo por
`chessStringTrimmed.includes('/')`.

**Solução.** Um comando "colar posição ou partida" que aceita os dois e decide pelo conteúdo, e
abrir um `.pgn` do disco. PGN com muitas partidas abre a coleção; PGN de uma abre o estudo.

**Critério de aceite.** PGN malformado diz o que estava errado e onde, e não descarta o estudo aberto;
FEN inválida idem; colar sobre um estudo com lances pergunta antes (regra 7).

**Testes.** `ColarTests` inteiro em `tests/test_estudo.py`, e do lado da aba
`test_pgn_com_lance_que_nao_fecha_diz_qual_e_nao_descarta_o_aberto`,
`test_a_colecao_do_livro_volta_para_a_sala` e
`test_um_pgn_de_muitas_partidas_de_fora_abre_a_lista`.

### O que entrou, e a régua que substituiu a do plugin (2026-08-26)

**Um campo só para os dois**, como no `ChessStringModal` de referência -- mas a régua dele **não**
foi copiada. Lá a decisão é `chessString.includes('/')`, e ela erra dos dois lados: um comentário de
PGN com uma data tem barra, e o campo de peças que o OCR desta casa produz tem **sete** barras e não
oito. `estudo.colar` pergunta outra coisa, e é a que o dado responde: *o `chess` monta um tabuleiro
com isto?* Se sim, é posição; se não, tenta-se partida.

**Três respostas para três arquivos**, e a diferença não é de tamanho:

| o arquivo | o que acontece |
|---|---|
| um `.pgn` que este programa gravou (`SourcePDF`, `Page`, `Diagram`) | as partidas entram **na sala** -- é o caminho de volta de quem editou a coleção no ChessBase |
| um `.pgn` de uma partida | abre como estudo avulso |
| um `.pgn` de muitas partidas sem âncora | abre a lista, que é o que uma base de partidas é |

Quem separa os dois primeiros é `Sala.guardar`, que já recusava estudo sem âncora válida desde a
S-270: não houve regra nova, só um segundo cliente para a que existia.

**E o motivo do erro é o do `chess.pgn`, e nunca "PGN inválido".** `1. e4 e5 2. Qh8` sai como
*"o PGN colado tem lance que não fecha: illegal san: 'Qh8' in ..."*, que nomeia o lance e a posição.

**Um cego, dito.** `2. Nf9` não é acusado: o tokenizador do `python-chess` não reconhece o token como
lance e o descarta em silêncio, sem registrar nada em `Game.errors` -- medido. Detectá-lo exigiria
retokenizar o texto por fora e comparar contagens, com comentários, variantes e resultado no meio;
até haver medição que diga que isso vale, o item declara o buraco em vez de tapá-lo com heurística.

---

## S-289 · O estudo exportado como o livro o mostraria ✅ implementada (2026-08-26)

**Problema.** `save_pgn` grava a árvore e pronto. Um estudo de livro tem outras saídas naturais: o
diagrama com as setas desenhadas, a linha em notação, o comentário.

**Solução.** As mesmas saídas que a Fase 39 deu ao editor de texto — `.md`, `.html`, `.rtf` —
alimentadas pelo estudo em vez de pelo documento, mais o PGN que já existe. E o inverso do S-283: o
estudo pode voltar para a aba de texto como um parágrafo de notação.

**Critério de aceite.** O estudo vira `DocumentoRico` e os três formatos o aceitam; a marca
`[Diagrama 1]` nunca desaparece; o recorte é gravado ao lado e o arquivo o aponta; e a linha levada
para a aba de texto é a mesma que a lista mostra.

**Testes.** `tests/test_estudo_saida.py` inteiro, e do lado da aba
`test_o_recorte_e_gravado_ao_lado_e_o_markdown_o_aponta`, `test_os_tres_formatos_gravam` e
`ParaOTextoTests`.

### O que entrou (2026-08-26)

**Não entrou um exportador: entrou uma conversão.** `estudo_saida.para_documento` devolve um
`DocumentoRico`, e daí em diante quem decide o que cada formato faz continua sendo
`text/exportacao.py` -- o módulo que existe porque *"quatro exportadores escritos separadamente
dariam quatro respostas, e três estariam erradas em silêncio"*. Um `.md` de estudo escrito à mão
seria o quinto exportador, e estaria errado em três das quatro perguntas no dia seguinte.

A conversão usa os estilos que a S-249 já nomeou e não inventa nenhum: o endereço no livro vira
`titulo`, a linha vira `notacao`, o comentário vira `prosa`, e a posição vira uma corrida de
**diagrama**. E `notacao` -- o único estilo da S-249 **sem derivação automática**, porque lá a régua
que separa lance de prosa não foi medida -- aqui não precisa de régua: o que sai de `estudo_lista`
**é** notação, por construção.

**Este é o primeiro cliente de `recortes=`.** O parâmetro existe em `exportacao.exportar` desde a
S-250 e nunca teve quem o usasse -- a aba de texto exporta sem imagem. É o mesmo caso de `validar` na
S-208: a peça estava pronta e faltava a pergunta.

**A linha sai no `texto` do trecho, e não no `pgn`.** O arquivo PGN escreve `$5` e `{ a italiana }`;
um parágrafo que alguém vai ler escreve `!?` e a frase solta, que é como o livro imprime. Quem quiser
a forma de arquivo já tem uma, e ela não perde nada: `salvar_estudo`.

**O que não vai junto: a seta e a casa marcada.** Elas moram em `[%cal]`/`[%csl]`, e nenhum dos
quatro formatos tem como desenhá-las -- fazê-lo exigiria compor uma imagem do tabuleiro com as setas
por cima, que é um renderizador e não um exportador. Ficam no PGN, que é onde o ChessBase e o Lichess
as leem.

---

# Fase 50 — Treinar

## S-290 · Adivinhar o lance ✅ implementada (2026-08-26)

**Problema.** A razão de estudar um livro de xadrez é acertar o lance antes de virar a página. Hoje a
lista mostra a continuação inteira, sempre.

**Solução.** O modo de treino do Scid e a "training annotation" do ChessBase: a linha some, o
tabuleiro cobra o lance da linha principal, e a resposta diz se acertou. O estudo já tem tudo de que
isso precisa — a linha é a árvore, e o gabarito é o nó seguinte.

**Critério de aceite.** O modo não altera a árvore; errar não cria variante (a menos que se peça);
o acerto e o erro ficam fora do arquivo, porque desempenho de quem estuda não é anotação da partida.

**Testes.** `TreinoTests` inteiro em `tests/test_estudo_aba.py`, e o corte puro em
`CorteDoTreinoTests` (`tests/test_estudo_lista.py`).

### O que entrou, e a decisão de forma que ele obrigou (2026-08-26)

O item é uma função de sete linhas (`_treinar`) e um corte de lista, e é isso porque **o estudo já
tinha tudo**: a linha é a árvore e o gabarito é o nó seguinte. Nada é guardado -- o placar mora em
dois inteiros do painel e some quando o treino desliga.

**O corte é `estudo_lista.ate`, e ele corta em vez de filtrar.** Filtrar os descendentes do nó
corrente deixaria parênteses órfãos na tela -- um `(` de variante cujo conteúdo sumiu --, e um `)`
sem par lido como notação é pior que a linha inteira à mostra. Cortar no último trecho do lance
corrente diz a mesma coisa e não tem esse problema. O símbolo e o comentário **do lance corrente**
ficam: eles são dele, e não da continuação.

**"A menos que se peça" virou uma frase, e não uma caixa.** O erro diz *"desligue o treino para
guardá-lo como variante"*. Um "quer guardar?" a cada erro transformaria o exercício numa fila de
caixas modais -- e a resposta certa quase sempre é não, que é exatamente o critério da S-164 para o
que **não** deve ser modal.
