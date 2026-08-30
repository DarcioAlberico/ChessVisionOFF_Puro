# Plano · A escolha da partida, e a base que responde em segundos (S-83 a S-94)

> Sucessor da Fase 13. Medido em 2026-08-15 sobre `data/games_matches.json` — a varredura de
> 2026-08-13, quatro livros, 1.641 casamentos — e sobre `pgn_database/PGN_Database.pgn`
> (10,3 GB). Os scripts das medições estão em [Como reproduzir](#7-como-reproduzir-as-medições).

> **Onde mora a spec de cada item (S-NN).** `tests/test_docs.py` confere esta tabela contra o
> disco (S-134): item entregue sem seção e seção no arquivo errado fazem a suíte falhar.
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
> | S-235 a S-267, S-291 a S-293 | [SPEC_EDITOR.md](SPEC_EDITOR.md) |
> | S-268 a S-290 | [SPEC_ESTUDO.md](SPEC_ESTUDO.md) |
> | S-296 a S-323, S-325 a S-430, S-452 (menos S-324) | [SPEC_REVISAO.md](SPEC_REVISAO.md) |

---

## 1. O problema, com número

O pedido é "quando várias partidas têm a mesma posição, listar e eu escolho". Medido, isso não
é um caso de borda: é **22,7% de tudo que a base reconhece**.

| partidas com a posição | diagramas | o que a tela faz hoje |
|---|---|---|
| 1 | 1.268 | preenche, e está certo |
| 2 | 78 | **preenche a mais antiga, sem perguntar** |
| 3 – 5 | 63 | **preenche a mais antiga, sem perguntar** |
| 6 – 20 | 93 | confirma a leitura e **não preenche nada** |
| 21 – 100 | 68 | idem |
| > 100 | 71 | idem |
| **total** | **1.641** | **373 diagramas sem a partida certa** |

São dois defeitos diferentes, e o segundo é o pior:

1. **141 diagramas preenchidos por desempate cego.** O critério de `PositionIndex.sort` é a
   data mais antiga — ele existe para a varredura ser determinística (S-73), não porque a
   partida mais antiga seja a que o livro cita. Onde há duas candidatas, é cara ou coroa com
   procedência gravada como se fosse resposta.
2. **232 diagramas onde a base sabe e a tela cala.** `apply_matches` confirma a leitura e para,
   porque acima de `max_games=5` o casamento não identifica a partida. A informação para
   resolver **existe na memória do processo** e é descartada.

**E a saída automática não alcança.** A ideia óbvia — desempatar pelos nomes da legenda —
foi medida: dos 373 ambíguos, só **47 têm os dois jogadores na legenda** (12,6%). Os outros 326
só uma pessoa resolve, e para resolver ela precisa **ver a lista**. É o que o pedido está
dizendo.

### 1.1 · O desempate cego erra, e dá para provar com o que já está no disco

Nos 47 ambíguos que têm nomes na legenda, dá para conferir a escolha contra o que o livro
declara. E é preciso um **controle**, senão o número não significa nada: os casamentos de
partida única, onde a posição identifica o jogo sozinha e a escolha não é escolha.

| | legenda confere | não confere | |
|---|---|---|---|
| **controle** — posição em 1 partida só | 239 | 86 | **73,5%** de acordo (n=325) |
| **ambíguos** — 2+ partidas, desempate pela data | 13 | 34 | **27,7%** de acordo (n=47) |

O piso de ruído é 26,5% (variação de grafia, legenda de um diagrama vizinho, o livro escrevendo
o nome de outro jeito). O desempate cego discorda **72,3%** das vezes — quase três vezes o
ruído. Em números redondos: dos 47, algo entre **20 e 34 estão preenchidos com a partida
errada**, com procedência gravada como se fossem resposta.

E esses 47 são justamente os que **têm** como ser conferidos. Nos outros 326 não há legenda
para discordar — não há razão nenhuma para supor que estejam melhores.

**É isto que responde ao seu "se der precisão".** A lista não é conforto de interface: o
automático de hoje, quando há empate, erra a maioria das vezes.

### 1.2 · A inicial colada, que apaga um quinto da busca por nome

Ao montar a medição acima, o comparador reprovou "K. Spicak" contra `Spicak, Krzysztof` — e o
comparador estava certo em reprovar, porque é exatamente o que `surname()` faz hoje:

```python
def surname(name: str) -> str:
    return fold(str(name).split(",")[0]).strip()   # "K. Spicak" -> "k. spicak"
```

A base escreve `Sobrenome, Nome` e o livro escreve `K. Spicak` ou `De. Wagner`. A vírgula é
tratada, a inicial colada não. Medido no acervo:

| livro | pares na legenda | com inicial colada |
|---|---|---|
| `400 Quebra-cabeças de Estratégia` | 315 | **104 (33%)** |
| `Secrets of Chess Training` | 178 | 5 (3%) |
| **acervo** | **494** | **109 (22,1%)** |

**Um quinto dos pares que o livro declara nunca casa no caminho por nome** — e não casa em
silêncio, porque `scan_by_players` simplesmente não os encontra. É a correção mais barata do
plano inteiro e é pré-requisito de usar a legenda para desempatar.

### O que é jogado fora hoje

A lista de candidatas é calculada e descartada três vezes ao longo do caminho:

| onde | o que acontece | `games_db.py` |
|---|---|---|
| varredura | guarda até **8** partidas por posição… | `MAX_HITS_PER_POSITION` |
| casamento | …e `match_positions` usa `registros[0]`, descarta as outras 7 | linha 485 |
| gravação | `--save-matches` grava só a vencedora | `_matches_to_json` |

Consequência prática: **refazer a escolha custa 104 minutos de varredura**, porque o artefato
que sobrevive já vem decidido.

---

## 2. A medição que mudou o desenho da performance

O outro lado do pedido é a base ser rápida. Medi de onde vem o custo, em 3.000 partidas reais
da base (213.830 lances, 71 por partida):

| etapa | tempo | extrapolado a 10,5 M partidas, 1 processo |
|---|---|---|
| tokenizar o movetext | 0,09 s | 5 min |
| `+ push_san` (reproduzir os lances) | 1,99 s | 116 min |
| `+ board_fen()` a cada lance | 7,88 s | **460 min** |

**`board_fen()` é 75% do custo da varredura.** O replay em si é o quarto do trabalho; o resto é
construir uma string de 64 casas por lance para comparar contra um conjunto — 213.830 strings
para 152 comparações que interessam.

### O porteiro de ocupação

`chess.Board.occupied` é um inteiro de 64 bits que o `python-chess` **já mantém
incrementalmente** a cada lance: um bit por casa ocupada. Ocupação igual é *condição
necessária* para colocação igual — então ele filtra antes, e o `board_fen()` só é chamado no
punhado que passa. Medido contra os 3.143 alvos reais do acervo:

| | tempo | casamentos | `board_fen()` chamado |
|---|---|---|---|
| hoje | 7,80 s | 152 | 213.830 vezes |
| com o porteiro | **2,15 s** | **152** | **152 vezes** |

**3,6×, e o resultado é idêntico — não é aproximação.** O que o porteiro deixa passar por
engano (mesma ocupação, peças diferentes) o `board_fen()` seguinte recusa, como sempre recusou.

### Confirmado na base de verdade (2026-08-15, depois de implementada)

O ensaio acima é de 3.000 partidas escolhidas do início do arquivo. Refeito num pedaço de
**304 MB da base, 332.823 partidas**, com os 3.143 alvos reais do acervo:

| | tempo | partidas | posições casadas | ocorrências |
|---|---|---|---|---|
| sem porteiro (S-73) | 928,2 s | 332.823 | 516 | 20.758 |
| com porteiro (S-85) | **262,3 s** | 332.823 | **516** | **20.758** |

**3,54×**, e os mesmos lances, a mesma vez e os mesmos headers, campo a campo. A projeção para
a passada inteira é **~30 min** contra os 104 de 2026-08-13 — projeção, e não medida: o número
que vale é o da próxima varredura do acervo, e é ele que fecha o critério de aceite da §5.

E o corolário que destrava a S-83: **guardar todas as candidatas é de graça**. Só as posições
que casaram alocam alguma coisa, e elas são 1.641 num acervo de 3.563 diagramas.

---

## 3. As entregas

| # | entrega | destrava | custo | estado |
|---|---|---|---|---|
| S-90 | a inicial colada no sobrenome (§1.2) | 22,1% dos pares do acervo | mínimo | ✅ 2026-08-15 |
| S-85 | o porteiro de ocupação (3,6×) | revarrer sem pagar 104 min | pequeno | ✅ 2026-08-15 |
| S-83 | as candidatas sobrevivem à varredura | tudo o mais | pequeno | ✅ 2026-08-15 |
| S-84 | o artefato passa a ser por posição, e vira cache | reaplicar em segundos | médio | ✅ 2026-08-15 |
| S-91 | a legenda desempata antes da data (§1.1) | a precisão do automático | pequeno | ✅ 2026-08-15 |
| S-86 | a lista na tela, e a escolha que vira procedência | **o pedido** | grande | ✅ 2026-08-15 |
| S-89 | censo da ambiguidade | provar que melhorou | pequeno | ✅ 2026-08-15 |
| S-88 | desempate pela vizinhança — **medir antes** | menos escolhas à mão | médio | ❌ **a medição reprovou**; virou dica de ordenação |
| S-87 | índice por nome em SQLite: busca por diagrama | precisão + alcance + segundos | grande | ✅ 2026-08-15 |
| S-92 | a busca por posição vira botão da Galeria | os 53,9% que a legenda não alcança | pequeno | ✅ 2026-08-16 |
| S-93 | a base é a pasta, e não o maior arquivo dela | +10,3 M partidas que eram invisíveis | médio | ✅ 2026-08-16 |
| S-94 | limpar os headers de um diagrama | desfazer o que o automático errou | mínimo | ✅ 2026-08-16 |

*(a tabela está na ordem de execução da §4, não na numérica)*

### S-83 · As candidatas sobrevivem à varredura ✅ implementada (2026-08-15)

`DiagramMatch` passa a carregar a lista, não só a vencedora:

```python
@dataclass(frozen=True)
class GameCandidate:
    move_number: int
    side_to_move: str
    headers: dict[str, str]

    @property
    def key(self) -> str:
        """White|Black|Date|Round|Event — a identidade estável da partida, para a escolha
        humana sobreviver a uma revarredura que reordene a lista."""

@dataclass(frozen=True)
class DiagramMatch:
    ...                                    # tudo o que já existe continua igual
    candidates: tuple[GameCandidate, ...] = ()
```

- `move_number`, `side_to_move` e `headers` continuam sendo **a primeira candidata**. Nada do
  que consome `DiagramMatch` hoje muda de comportamento — `apply_matches`, `_report`, `_apply`
  e os testes seguem valendo.
- `MAX_HITS_PER_POSITION` sobe de 8 para **32**. Não é "mais é melhor": 32 é uma lista que uma
  pessoa lê rolando uma vez. Acima disso quem resolve é o filtro da tela, não a rolagem.
- `PositionIndex.counts` continua sendo a verdade sobre **quantas existem** — a tela precisa
  dizer "32 de 147", nunca deixar a lista truncada passar por completa.
- `sort()` continua sendo a garantia de determinismo da S-73, e agora com um segundo papel:
  ela define a ordem em que a lista aparece.

**O que a implementação mudou em relação a este desenho.** Não existe `GameCandidate`: quem faz
esse papel é o `PositionHit`, que já era exatamente isso e ganhou `key`, `to_dict` e
`from_dict`. Dois tipos quase iguais divergiriam, e a tela teria de saber ler os dois.

E uma mudança de comportamento que não estava prevista aqui: **no caminho por nome, a primeira
candidata passou a ser a resposta do casamento**. Antes ele respondia com "a primeira partida
que a base guardou" e a lista sairia ordenada por data — a tela mostraria uma marcada como
escolhida e a anotação diria outra. Agora os dois caminhos concordam sobre qual é a escolha
padrão, que é a mais antiga, pelo critério da S-73.

### S-84 · O artefato deixa de ser por livro e vira cache por posição ✅ implementada (2026-08-15)

Hoje `--save-matches` grava `livro → casamentos`. A chave certa é a **colocação**, porque é ela
que a base responde — o livro é só quem pergunta.

```
data/games_positions.json        # placement → {candidatas[≤32], count}
                                 # + fingerprint da base: nome, tamanho em bytes, mtime
```

- Reaplicar em qualquer livro, com qualquer `--max-games`, com a regra de preenchimento
  corrigida: **segundos**, sem abrir o `.pgn`.
- Uma revarredura só precisa das colocações **ausentes do cache**. Isso importa agora: a
  detecção mudou (S-78 a S-82) e os recortes vão mudar, então parte dos alvos será nova e
  parte não.
- **Guarda:** se o fingerprint da base não bate, o cache inteiro é descartado. Uma base trocada
  torna as contagens mentira, e contagem é o que decide se preencher é honesto.
- `--from-matches` continua lendo o formato v1 (é o artefato dos 104 minutos de 2026-08-13).
  Conferido no acervo real: reproduz os mesmos 1.641 casamentos, livro a livro.

**O que a implementação acrescentou ao desenho.** Mora em `games_cache.py`, e não em
`games_db.py`: guardar o que a base respondeu é responsabilidade diferente de perguntar a ela.
O comando ganhou `--cache` e `--no-cache` — o segundo existe para o cache poder ser **auditado
contra a base**, senão um cache errado seria inauditável. E a decisão que os testes cobrem
primeiro: **a pergunta sem resposta fica registrada** (`count: 0`). Sem isso, as 1.922 posições
do acervo que a base não conhece voltariam ao conjunto-alvo de toda varredura futura, para
sempre — e elas são a maioria.

### S-85 · O porteiro de ocupação ✅ implementada (2026-08-15)

Em `_scan_positions_chunk` e `GameRecord.positions`, o alvo deixa de ser um `frozenset[str]` e
passa a ser `(frozenset[int], frozenset[str])` — ocupações e colocações:

```python
if tabuleiro.occupied in ocupacoes_alvo:      # inteiro que o push já atualizou
    colocacao = tabuleiro.board_fen()          # a string só aqui
    if colocacao in colocacoes_alvo:
        ...
```

Testes: (a) a base pequena de `test_games_db.py` dá exatamente os mesmos casamentos; (b) um
teste que prova que ocupação igual com peças diferentes **não** vira casamento — é a garantia
de que o porteiro é filtro e não critério.

**O que a implementação mudou em relação a este desenho.** O parâmetro chama-se `occupancies`
(`occupancy` sombreava a função do módulo), `occupancy()` lê os bits direto da string em vez de
montar um `Board` — com um teste que confere o número contra `Board.occupied`, porque a
numeração é a parte fácil de errar: a colocação escreve a **oitava** fila primeiro. O conjunto
é calculado uma vez em `scan_by_positions` e viaja pronto para os dez processos; recalculá-lo
em cada filho seria o mesmo trabalho dez vezes.

### S-86 · A lista na tela, e a escolha que vira procedência ✅ implementada (2026-08-15)

O pedido. Na Galeria, ao lado da linha verde de procedência:

```
┌ Partidas da base ─────────────────────────────────────────────┐
│ filtro: [karpov          ]                    32 de 147       │
├───────────┬─────────────┬─────────────┬──────────┬─────┬──────┤
│ Data      │ Brancas     │ Pretas      │ Evento   │ Lance│ Vez │
│ 1974.09.12│ Karpov, A.  │ Korchnoi, V.│ Cand fin │  24  │  b  │  ← escolhida
│ 1981.10.06│ Kasparov, G.│ Timman, J.  │ Tilburg  │  31  │  w  │
└───────────┴─────────────┴─────────────┴──────────┴─────┴──────┘
       [ Aplicar ]   [ Aplicar aos vizinhos… ]   [ Fechar ]
```

Regras, e cada uma tem um porquê que já é do projeto:

1. **A escolha grava `chosen_game` na anotação** (a `key` da S-83). Uma revarredura, ou um
   `cvoff-games --apply` depois, **respeita a escolha**: ela vence a candidata[0]. Sem isto o
   trabalho da pessoa é apagado pela próxima execução, que é exatamente o defeito que a S-77
   consertou no conjunto de campo.
2. **A escolha humana pode sobrescrever o que a base escreveu** — mesma origem, versão melhor.
   Mas **pergunta antes de tocar no que a pessoa digitou**: a regra da S-17 ("a base é uma
   fonte a mais, não a autoridade") vale para a base automática; um humano corrigindo o próprio
   trabalho é outro caso, e ele merece a pergunta, não o silêncio.
3. **`filled_fields` ganha a marca da escolha** — os campos aplicados por escolha humana não são
   `manual` (ninguém conferiu o livro) nem `base` (a base não decidiu sozinha). É uma terceira
   procedência, e o PGN precisa saber dizer isso, pela razão da S-74.
4. **O filtro no topo é o que torna 147 candidatas utilizável.** Digitar "karpov" ou "1974"
   corta a lista; sem ele, os 71 diagramas com >100 partidas continuam sem resposta prática.
5. **"Aplicar aos vizinhos"** é a produtividade real: um capítulo analisa uma partida em cinco
   ou seis diagramas seguidos. Aplica a mesma partida aos vizinhos **que a têm entre as
   candidatas** — nunca aos que não a têm. É o "aplicar a todos" da S-76 com a trava que faltou
   lá.

O painel lê o cache da S-84 — **não abre a base**. Abrir com a lista já em disco é o que
permite que isso seja um clique e não uma janela travada.

**O que a implementação acrescentou ao desenho.**

- **A janela é `ui/games_dialog.py` e não sabe decidir nada.** Filtrar, escolher, checar
  conflito e espalhar aos vizinhos são métodos do `GalleryModel`, que se testa sem abrir um Tk
  — a mesma divisão que organizou a Fase 6, e pela mesma razão: é na lógica, não na janela, que
  os defeitos aparecem. São 13 testes de modelo e 6 de widget.
- **O botão traz a contagem antes do clique** ("Partidas da base (47)"). Um diagrama com 47
  candidatas e um com uma só pedem gestos diferentes, e descobrir isso depois de abrir a janela
  é tarde.
- **Duas marcas na lista, e nenhuma delas é coluna:** negrito para a partida já escolhida,
  verde para as que a legenda confirma. São as duas informações que decidem o clique, e
  qualquer uma delas como coluna empurraria os nomes para fora da tela.
- **`ApplyReport.respected`** conta os diagramas em que uma escolha humana já existia e foi
  preservada. Não é trabalho poupado nem trabalho feito: é trabalho **não desfeito**, e um
  número alto numa varredura avisa que ela está passando por cima de um livro já revisado.
- **Cada vizinho recebe o lance dele**, não o do diagrama de origem — é a mesma partida em
  outro momento dela, e copiar o número seria escrever o dado errado com a confiança de quem
  acertou a partida.

### S-90 · A inicial colada no sobrenome ✅ implementada (2026-08-15)

Uma função, quatro linhas, e 22,1% dos pares do acervo (§1.2):

```python
def surname(name: str) -> str:
    """`De Castellvi, Francisco` -> `de castellvi`; `K. Spicak` -> `spicak`."""
    tokens = fold(str(name).split(",")[0]).split()
    while len(tokens) > 1 and (tokens[0].endswith(".") or len(tokens[0]) == 1):
        tokens = tokens[1:]          # inicial colada: "K.", "De.", "A"
    return " ".join(tokens)
```

**A partícula sobrevive e a inicial não**, e a diferença é o ponto: `De Castellvi` continua
inteiro porque `De` não tem ponto nem é letra solta; `De. Wagner` vira `wagner` porque tem.
O `while` guarda `len(tokens) > 1` para nunca esvaziar um nome que é só uma inicial.

Testes: os quatro casos acima, e o de regressão — `Coull` continua `coull`.

Isto entra **primeiro**, sozinho, porque melhora o caminho por nome de hoje sem depender de
nada e porque a S-91 não pode ser medida com o comparador quebrado.

### S-91 · A legenda desempata antes da data ✅ implementada (2026-08-15)

Onde a legenda nomeia os jogadores e **exatamente uma** candidata bate com ela, ela é a
escolha — a data deixa de decidir:

```python
def rank_candidates(candidates, caption_pair):
    """Ordena as candidatas pondo primeiro as que a legenda confirma.

    Não filtra, ordena: uma legenda pode ser do diagrama vizinho (medido: 26,5% de ruído no
    controle da §1.1), e descartar candidatas por causa dela tiraria da lista a partida certa.
    """
```

- **Uma bate → preenche.** Substitui um desempate que erra 72,3% por um que a legenda confirma.
- **Nenhuma ou várias batem → a ordem por data continua**, e a lista da S-86 fica com as
  concordantes no topo, marcadas.
- **A procedência diz qual foi.** Um campo preenchido por concordância com a legenda não é a
  mesma coisa que um preenchido por partida única, e o `filled_fields` precisa distinguir —
  senão a S-89 não consegue medir se a S-91 melhorou nada.
- **Risco declarado:** legenda misturada com a do diagrama vizinho pode confirmar a candidata
  errada. É estritamente melhor que hoje (a data não olha para nada), mas não é verdade — por
  isso ordena, marca e não silencia a lista.

Depende da S-90: sem ela, um terço das legendas do `400 Quebra-cabeças` não bate com candidata
nenhuma e a S-91 não teria com o que desempatar.

**O que a implementação acrescentou ao desenho.**

1. **A legenda destrava o preenchimento acima do teto**, e este é o ganho maior — não estava
   escrito assim aqui. Uma posição em 47 partidas não identifica partida nenhuma *pela
   contagem*, mas identifica se a legenda nomeia exatamente uma delas: são os **232 diagramas
   que hoje ficam confirmados e vazios**, e não só os 141 mal desempatados.
2. **A ordem das cores não é exigida.** O livro escreve "Coull - Stanciu" sem prometer quem
   tinha as brancas, e o `parse_context` devolve os nomes na ordem em que aparecem. Exigir a
   ordem reprovaria metade dos acertos por uma informação que a legenda não deu.
3. **`DiagramAnnotation.filled_rule`** grava *por que* aquela partida: `unique`, `caption`,
   `date` ou `human`. `filled_from` já dizia *de que* partida veio o preenchimento, que é outra
   pergunta. Sem este campo os 141 preenchidos às cegas são indistinguíveis de dado conferido,
   e o censo da S-89 não teria como listá-los para revisão.
4. **A linha verde da tela diz a regra**: "da base (lance, vez): Karpov x Korchnoi — a mais
   antiga entre várias". Mostrar um desempate por data com a mesma cara de uma partida única
   seria mentir por omissão.

#### Medida no acervo, e ela rende menos do que este plano previa

Rodada sobre o cache da varredura de 2026-08-15 (os 3.143 alvos, 1.641 casamentos):

| | |
|---|---|
| ambíguos | 373 |
| **resolvidos pela legenda** | **23** |
| — estavam confirmados e **vazios** (>5 partidas) | 8 |
| — estavam preenchidos às cegas (≤5 partidas) | 15 |
| — e destes, a legenda **trocou** a partida escolhida | **13** |
| seguem sem saída automática | **350** |

E a concordância com a legenda, nos 47 ambíguos que têm nomes:

| | concorda | |
|---|---|---|
| antes (desempate por data) | 12 | 25,5% |
| **depois (S-91)** | **25** | **53,2%** |

**O critério de aceite escrito na §5 estava errado, e o erro é meu.** Eu previa chegar "perto
dos 73,5% do controle", e o teto real é **53,2%** — porque em **22 dos 47 (46,8%) nenhuma
candidata bate com a legenda**, e a legenda não pode desempatar entre zero. Abrindo esses 22:

| causa | quantos | o que resolve |
|---|---|---|
| a lista está completa e a legenda é que não bate | 13 | nada automático — é o ruído de 26,5% medido na §1.1 |
| **a lista foi truncada em 32 e a partida certa pode ter ficado de fora** | **9** | **a S-87**: perguntar por nome não tem lista para truncar |

**O que isto reordena.** A S-91 conserta 23 diagramas, 13 deles demonstravelmente errados — é
pouco, e é precisão, que era o critério. Mas os **350 restantes** dizem em números o que o
pedido original já dizia: **quem resolve isso é a lista da S-86**, e nenhum automático vai
resolver por ela.

### S-87 · O índice por nome — precisão, alcance e segundos ✅ implementada (2026-08-15)

**Aprovada.** E a medição da §1.1 muda o argumento dela: não é só velocidade.

| o que ela dá | por quê |
|---|---|
| **alcance** | 1.922 diagramas do acervo **não casaram por posição** (53,9%). Para os que têm nomes na legenda, a base ainda tem a resposta — o que falta é como perguntar sem varrer 10,3 GB |
| **precisão** | a partida escolhida pode ser **verificada**: reproduzida do offset, a posição do diagrama tem de aparecer nela, e no lance que a anotação diz. Um oráculo contra a escolha errada, e o que torna a S-91 conferível |
| **a lista truncada** | medido em 2026-08-15: em **9** dos 22 casos em que a legenda não acha candidata nenhuma, a lista foi cortada em 32 e a partida certa pode estar fora dela. Perguntar por nome não tem lista para truncar — e este é o único caminho que os alcança |
| **segundos** | uma pessoa parada num diagrama não paga 150 s por pergunta |

#### A linha "alcance" desta tabela estava errada, e a medição a corrigiu

**O erro de raciocínio:** a varredura por posição é *exaustiva sobre a base inteira*. Se
nenhuma partida das 10,5 milhões contém aquela posição, então nenhuma partida **daquele par**
contém — perguntar por nome não pode achar o que a passada completa não achou. Medido, e é
exatamente zero:

| grupo | diagramas | com nomes na legenda | a busca por nome acha a posição |
|---|---|---|---|
| perguntada, a base não conhece a posição | 1.983 | 123 | **0** — impossível, por construção |
| nunca perguntada (livro varrido depois) | 4.864 | 17 | 0 |
| **lista truncada em 32** | 117 | 10 | **3** |

Como ferramenta de achar a posição, a S-87 vale **3 diagramas**. É pouco, e está medido.

**O que a medição encontrou no lugar, e que vale mais.** Dos 140 diagramas cuja legenda nomeia
os jogadores e cuja posição não casou, **68 (49%) têm partidas daquele par na base**. A base
não pode dizer em que lance aquela posição acontece — ela não tem aquela posição —, mas tem
**evento, local, data, rodada, resultado e ECO** daquelas partidas. Que é justamente o trabalho
de preencher headers do pedido original.

Por isso `PositionHit` ganhou `verified`. Uma candidata não verificada aparece na lista com
travessão nas colunas Lance e Vez, o rótulo diz "posição não confere", e `choose_game`
**preenche os headers e não toca no lance nem na vez** — eles vêm da posição, e sem posição
seriam invenção. Conferido num diagrama real do `400 Quebra-cabeças` ("Ganguly – Adhiban"): 10
partidas do par, 8 headers preenchidos, lance intacto.

O `games_db.py` registrou a condição, em 2026-08-13:

> *"Um índice por nome custaria ~1 GB no disco (…) para poupar 150 s por livro — e livro se
> varre uma vez. **O dia em que a busca virar por diagrama e não por livro, o índice passa a
> valer.**"*

É esse dia. Uma pessoa parada num diagrama, querendo perguntar à base agora, não pode pagar
150 s por pergunta.

```
data/games_index.sqlite     # pair_hash INTEGER, offset INTEGER  |  ~10,5 M linhas
```

- Construção: **uma passada de cabeçalhos** (~150 s de leitura + gravação), com `sqlite3` da
  biblioteca padrão — sem dependência nova.
- Consulta: par de sobrenomes → até 40 offsets → `seek` + replay das 40 partidas →
  **milissegundos**.
- Efeito na tela: um botão "procurar esta partida" que responde antes de o clique acabar, em
  vez do "Buscar na base" de hoje, que varre o livro inteiro.
- Fora do git, ao lado da base, como todo material derivado dela.

**O que a implementação mediu e mudou.**

| | previsto | medido na base inteira (2026-08-15) |
|---|---|---|
| construção | ~150 s + gravação | **8,4 min**, 10.547.415 partidas |
| tamanho | ~500 MB | **431 MB** |
| consulta | milissegundos | **0,5 a 2,7 ms** (Karpov x Kasparov: 40 partidas em 2,7 ms) |
| consulta + replay das partidas | — | **27 ms** |

- **A chave não pode ser o `hash()` do Python.** Ele é aleatorizado por processo desde a 3.3:
  um índice gravado hoje responderia **zero** amanhã, sem erro nenhum. É `blake2b` de 64 bits,
  e há um teste que roda um interpretador separado — que é onde isso apareceria.
- **Colisão de hash não vira resposta errada**, porque a consulta lê a partida e confere os
  sobrenomes: uma colisão custa uma leitura descartada.
- **O fingerprint da base é obrigatório aqui, mais até que no cache**: offsets são do arquivo, e
  numa base diferente cada um aponta para o meio de outra partida — a leitura devolveria
  movetext cortado com cara de partida. Não bate, a consulta devolve vazio e avisa como refazer.
- **Consulta os dois lados por padrão.** "Coull - Stanciu" é como o autor escreveu, não uma
  declaração de quem tinha as brancas.
- **Na tela, a busca por nome junta à lista, não substitui.** O que a varredura mediu sobre a
  posição continua valendo; a busca por nome acrescenta o que ela não podia guardar. As novas
  aparecem em roxo, e a janela passa a abrir mesmo em diagrama **sem candidata nenhuma**, desde
  que a legenda nomeie os jogadores — que é como ela alcança os 1.922 diagramas do acervo cuja
  posição não casou.

### S-88 · Desempate pela vizinhança ❌ **reprovada como regra** — vive como dica (2026-08-15)

**Hipótese:** diagramas vizinhos vêm da mesma partida; a partida que explica o diagrama *k-1* e
o *k+1* é a que explica o *k*.

**O critério foi fixado antes de medir:** implementa se resolver >20% dos 373 ambíguos.
Medido sobre o cache do acervo, em cinco raios:

| raio | resolve (candidata única em comum) | % dos 373 | acerta, conferindo contra a legenda |
|---|---|---|---|
| 1 | 49 | 13,1% | 1 de 2 |
| 2 | 56 | 15,0% | 2 de 3 |
| **3** | **62** | **16,6%** | 2 de 3 |
| 5 | 61 | 16,4% | 2 de 3 |
| 8 | 62 | 16,6% | 2 de 3 |

**Reprovada, e não por pouco.** O teto é 16,6% contra os 20% pedidos, e aumentar o raio não
ajuda — de 3 para 8 o número não se move, porque o que limita não é a distância, é que em
**243 dos 373** nenhuma candidata é compartilhada com vizinho nenhum.

**E o que a reprova de vez não é o rendimento: é a impossibilidade de conferir.** Dos 62 que
ela resolveria, só **3** têm legenda com nomes para checar a resposta — 2 certos de 3, uma
amostra que não sustenta nada. Ela preencheria procedência em 62 diagramas sem que exista modo
de saber se acerta, e procedência inventada é pior que campo vazio. É a mesma reprovação da
S-80, pelo mesmo tipo de razão.

**O que sobrou dela, e vale.** Como **ordenação da lista** a hipótese não pode errar: no pior
caso põe a candidata errada em segundo lugar numa lista que a pessoa está lendo de qualquer
forma. A tela marca em azul as candidatas que os vizinhos também têm, e a ordem final da lista
tem três critérios, do mais forte ao mais fraco: **a legenda confirma** (S-91), **os vizinhos
também a têm** (S-88), **a data** (S-73). Nenhum deles descarta candidata.

### S-89 · O censo da ambiguidade ✅ implementada (2026-08-15)

`cvoff-games --census`: a distribuição da tabela da §1, por livro, mais quantos diagramas foram
resolvidos à mão, quantos pela vizinhança e quantos sobraram. Existe pela razão da S-82: sem
instrumento, "melhorou" é opinião — e a tabela da §1 foi escrita à mão hoje justamente porque
ele não existe.

**Não abre a base**, e sai antes da checagem dela: um instrumento que precisasse de 30 minutos
para dizer o estado do acervo não seria consultado, e o que não se consulta não mede nada.

**O que a implementação acrescentou: `inferred_rule`.** Rodado a primeira vez, o censo relatou
**1.413 diagramas "de regra desconhecida" e zero a revisar** — porque o acervo inteiro foi
preenchido pela varredura de 2026-08-13, antes de `filled_rule` existir. Zero por ignorância
não é zero, e essa era a leitura mais perigosa que o instrumento podia dar.

A regra daqueles preenchimentos é **dedutível** do cache, e não chutada: aquele código
preenchia se, e só se, a posição estivesse em até `max_games` partidas, escolhendo sempre a
primeira da lista ordenada por data. Então uma partida só é `unique`, e duas ou mais é `date`.
Com a dedução, o censo do acervo hoje:

| | |
|---|---|
| partida única na base | **1.268** |
| **a mais antiga entre várias — a revisar** | **145** |
| confirmada pela legenda / escolhida por uma pessoa | 0 / 0 *(ainda)* |
| ambíguos sem resposta, que só a lista alcança | **373** |

O relatório diz quantos desses números vieram de dedução (1.413 dos 1.413), porque um total que
mistura o medido com o deduzido sem dizer qual é qual é o tipo de número pelo qual a S-80 foi
reprovada.

### S-92 · A busca por posição vira botão ✅ implementada (2026-08-16)

**O pedido:** *"o programa procura a informação que está na legenda para buscar no banco de
dados; gostaria que ele também procurasse pelo FEN da posição."*

Ele estava certo sobre a tela: dos dois caminhos da §2, só o **por nome** tinha botão. O por
posição — o que alcança **todo** diagrama, inclusive os 53,9% do acervo sem nome nenhum na
legenda — só existia como `cvoff-games --positions`, e quem estava anotando um livro na Galeria
não tinha como perguntar.

A razão de ele não ser botão está escrita no `games_db.py` e continua verdadeira: *"meia hora
atrás de um botão é uma janela travada que ninguém entende"*. O que mudou não foi o custo, foi
o que cerca o botão — e são quatro coisas, nenhuma opcional:

1. **Diz o preço antes.** A caixa informa quantas posições faltam de quantas, que a passada
   custa cerca de meia hora e que as outras saem do cache. Sem isso o clique é uma armadilha.
2. **Mostra em que pedaço está**, pelo `progress` que a varredura já tinha e ninguém via.
3. **Dá para cancelar**, e o cancelamento é notado **enquanto os pedaços rodam** — conferi-lo
   entre pedaços concluídos seria a passada dividida por dez, minutos depois do clique.
4. **A segunda vez custa segundos**, porque a resposta vai para o cache da S-84.

**O livro inteiro, e não o diagrama aberto** — que era a alternativa óbvia e é a errada. O
custo é da passada pela base, não do alvo: perguntar por uma posição custa os mesmos ~29 min
que perguntar pelas 1.400 do livro. É a economia da S-61 e da S-73, aqui de novo.

**Cancelar descarta a passada inteira, e isso é a parte que não pode ser negociada.** Uma
varredura interrompida viu parte da base, e a contagem de partidas por posição é justamente o
que decide se preencher um header é honesto (S-74). Uma posição achada em um dos dez pedaços
sairia com `count=1` — a marca de *partida única*, que preenche tudo — quando a base pode ter
47 partidas com ela. Meia varredura no cache seria procedência inventada, que é pior que campo
vazio. Nem como *perguntada* ela é registrada: a pergunta não chegou a ser feita.

**O que a implementação acrescentou ao desenho.**

- **O rótulo do botão antigo mudou.** "Buscar na base" não distinguia mais nada com dois
  botões que buscam na base; hoje são **"Buscar por nome"** e **"Buscar pela posição"**, e o
  critério está no rótulo.
- **A espera do pool passou a ter prazo** (`CANCEL_POLL_SECONDS`, 0,5 s). Era um `for` sobre
  `imap_unordered`, que só devolve o controle quando um pedaço termina — e um pedaço é a
  varredura inteira dividida pelo número de processos.
- **A lista de candidatas acende no mesmo gesto**: a varredura acaba de descobrir as candidatas
  de cada diagrama, e mandar reabrir o livro para vê-las seria esconder o que se pagou meia
  hora para ter.
- **`_busy()`**, um lugar só para ligar e desligar os três botões que disputam a única thread
  longa da aba. Eram três `configure` repetidos em seis lugares, e este seria o quarto.

### S-93 · A base é a pasta, e não um arquivo ✅ implementada (2026-08-16)

**O pedido:** *"pode adicionar o arquivo `LumbrasGigaBase_OTB_Complete.pgn` pra fazer parte nas
buscas."*

O arquivo já estava em `pgn_database/` — 8,6 GB, ao lado do `PGN_Database.pgn` de 10,3 GB — e
era **invisível**, porque `default_database_path()` devolvia *o maior* `.pgn` da pasta. A razão
escrita para isso ("quem baixa uma gigabase costuma deixar ao lado dela o PGN de um torneio")
estava certa sobre o risco e errada sobre a saída: o arquivo ao lado também tem partidas.

**O que estava sendo jogado fora, medido em 2026-08-16:** 10.355.488 partidas — praticamente
outra base inteira. E a prova de que isso custava respostas: a partida
`Hutchings x Keene, Hexagon North Devon, Woolacombe, 1973.10.11`, procurada na base "oficial"

| por onde | resposta da base "oficial" |
|---|---|
| pelo par de nomes, no índice | 2 partidas, de 1974 e 1975 — nenhuma é essa |
| por Hutchings em 1973 | 13 partidas, Eastbourne e Islington — nenhuma em outubro |
| pelas 64 casas, entre as 1.134 partidas de Keene | melhor casamento **4 de 44** posições |

está na Lumbras, com **as 44 posições batendo, inclusive a final**.

**O que mudou.**

- `database_paths()` devolve **todos** os `.pgn` da pasta, ordenados **por nome**. A ordem
  virou identidade: o índice grava a posição nesta lista como número de arquivo.
- `scan_by_positions` põe os pedaços de **todos** os arquivos na mesma fila de tarefas — os
  processos não ficam ociosos esperando o arquivo grande, o progresso é um só e o cancelamento
  vale para o conjunto. O `mp.Pool` passou a ser `min(processos, pedaços)`: com duas bases a
  lista dobrou, e um processo por pedaço abriria vinte numa máquina de doze núcleos.
- `scan_by_players` percorre um arquivo por vez, com o teto por par valendo para o **conjunto**.
- O índice por nome ganhou a coluna `file` e a tabela `files`. **É a correção que não podia
  faltar:** o byte 4.000.000 existe nas duas bases e começa partidas diferentes; sem ela, o
  offset da segunda seria lido na primeira, a conferência de nomes descartaria o que leu, e a
  base recém-acrescentada responderia **zero em silêncio** — o mesmo sintoma que originou a
  S-93. (Partida *errada* só sairia se o outro arquivo tivesse, naquele mesmo byte, uma partida
  do mesmo par; é raro, e a conferência de nomes é o que sobra contra isso.)
- O índice ganhou **versão declarada** (`INDEX_VERSION = 2`). Com uma base só, o fingerprint da
  v1 é *idêntico* ao da v2, então um índice antigo passaria pela conferência e quebraria no
  `SELECT ... file`. Versão declarada transforma isso num aviso com instrução.
- O fingerprint do cache virou uma lista de arquivos. **Acrescentar uma base descarta o cache
  inteiro**, e tem de ser assim: a posição que estava em uma partida pode estar em três, e é a
  contagem que autoriza preencher header (S-74).

**O que a segunda base comprou, medido em 2026-08-16** — o artefato da varredura anterior
(`games_matches_v2.json`, base "oficial" sozinha) contra o cache novo, diagrama a diagrama, nos
mesmos 4 livros:

| livro | diagramas | casavam | casam | **novos** | 1→2+ |
|---|---|---|---|---|---|
| 1001 Winning Chess Sacrifices | 1.003 | 288 | 460 | **+172** | 231 |
| 400 Quebra-cabeças | 1.120 | 589 | 655 | **+66** | 271 |
| Niemeijer, Zwarte Magie | 32 | 0 | 0 | 0 | 0 |
| Secrets of Chess Training | 1.408 | 764 | 989 | **+225** | 479 |
| **total** | **3.563** | **1.641** | **2.104** | **+463** | **981** |

**46,1% → 59,1% do acervo**, e 463 diagramas que nenhuma busca alcançava. (O acervo cresceu
desde então; a varredura de agora cobriu 6 livros, 8.633 diagramas, 5.748 casamentos.)

**O custo, medido e não estimado.** Partida repetida nas duas bases **conta duas vezes**, e
**981 diagramas deixaram de ser "partida única"**. Das 854 posições distintas por trás deles:

| | |
|---|---|
| a mesma partida, repetida nas duas bases | **542 (63,5%)** |
| partidas de fato diferentes | 207 (24,2%) |
| mistura das duas coisas | 105 (12,3%) |

*(critério: mesmos dois sobrenomes, mesmo resultado, mesmo ano e mesmo lance)*

Então **dois terços do custo são ruído puro** — a mesma partida com o evento escrito de outro
jeito em cada base:

```
Golombek x Broadbent   | BCF Ch 38th 1951.08.30  ×  British CF-38 Championship 1951.08.30
Najdorf x Hounie       | Mar del Plata 1946.03.01 × Mar del Plata International-09 1946.03.23
```

Esses 542 passam a preencher pela regra `date` em vez de `unique`, e o censo da S-89 vai
listá-los como *a revisar* — sendo que a candidata "concorrente" é a própria partida. **Não há
deduplicação, e ela não é óbvia:** a chave frouxa acima funde partidas *diferentes* dos mesmos
jogadores, no mesmo ano, com o mesmo resultado, quando a posição é de abertura — que é
exatamente onde as contagens já são altas. Fica registrado como o próximo candidato a medir.

**O custo de acrescentar uma base:** reconstruir o índice por nome e pagar uma varredura por
posição nova. Medidos nesta máquina, com 18,9 GB e 20.902.903 partidas:

| | |
|---|---|
| `--build-index` | 20.902.903 partidas, **885 MB** (eram 431) |
| varredura por posição, 8.034 alvos, 20 pedaços | **56 min 10 s** |

Não é opcional nem é desperdício: é o que separa uma resposta conferida de um número que
parece conferido.

### S-94 · Limpar os headers de um diagrama ✅ implementada (2026-08-16)

**O pedido:** *"se por ventura o diagrama não estiver preenchido corretamente, deveria ter um
botão para limpar todos os campos dos headers daquele diagrama."*

O plano inteiro até aqui empurra dado para dentro da anotação — a busca por nome, a busca por
posição, a lista de candidatas, o "aplicar aos vizinhos". **Nenhum deles tem o gesto inverso**,
e ele é necessário justamente porque o preenchimento automático erra de um jeito conhecido e
medido: onde a posição está em várias partidas, quem escolhe é o desempate por data, e ele
discorda da legenda **72,3%** das vezes (§1.1). Quando erra, são até oito campos para limpar um
a um, saindo de cada `Entry` para o `<FocusOut>` gravar. Ninguém faz isso oito vezes; deixa
errado — e um header errado com cara de conferido é pior que campo vazio.

**O que ele apaga, e o que não apaga.** Só os headers, e só deste diagrama:

| fica | sai |
|---|---|
| o lance e a vez | os 8 headers da tela **e** os livres |
| a partida escolhida (`chosen_game`) | a procedência dos headers (`filled_fields`) |
| `confirmed_from` — as 64 casas bateram, e limpar header não desfaz isso (S-74) | `filled_from`/`filled_rule`, se não sobrar campo nenhum da base |

O lance e a vez ficam porque costumam ter sido **contados no livro à mão**, e apagar trabalho
humano que ninguém mandou apagar é o defeito que a S-76 custou caro para aprender. Quem quer
trocar a partida inteira usa a lista de candidatas, que reescreve tudo de uma vez.

**Não há semântica nova:** é o mesmo que apagar campo a campo, inclusive na procedência. Um
botão que limpasse "de outro jeito" criaria dois estados possíveis para a mesma tela.

**O que a implementação encontrou de quebra.** `filled_rule` sobrevivia a uma limpeza que
apagava tudo — `filled_from` era zerado quando não sobrava campo da base, e a regra não. Os
dois são um par (*de que* partida veio, e *por que* foi ela), e a regra sozinha faria o censo
da S-89 contar como "preenchido pelo desempate por data" um diagrama sem nada preenchido. A
conta virou `_provenance_after`, usada nos quatro lugares onde ela aparecia — editar um campo,
apagar um header, desfazer a cópia e limpar tudo.

**A pergunta nomeia os valores que vão sair**, como a do "copiar para todos" e pela mesma razão
(§S-76): o que se apaga aqui pode ser meia hora de digitação de quem tinha o livro na mão. Não
há desfazer, e a caixa diz isso — um segundo botão "desfazer" ao lado do que já existe criaria
a dúvida de qual dos dois desfaz o quê, no momento em que a pessoa está com pressa.

---

## 4. A ordem, e por que ela é essa

| | entrega | por que aqui |
|---|---|---|
| 1 | **S-90** inicial colada | quatro linhas, e nada mede certo antes dela — inclusive a S-91 |
| 2 | **S-85** porteiro | toda revarredura daqui em diante custa 29 min, não 104 |
| 3 | **S-83 + S-84** candidatas + cache | para a *próxima* varredura já gravar o que a tela vai ler |
| 4 | *uma varredura do acervo (~29 min)* | o único custo longo do plano; produz o cache |
| 5 | **S-91** legenda desempata | agora há candidatas para desempatar e legendas que casam |
| 6 | **S-86** a lista na tela | **o pedido**; lê o cache, não abre a base |
| 7 | **S-89** censo → **S-88** vizinhança (medida) | medir, depois decidir se implementa |
| 8 | **S-87** índice por nome | independente; entra quando quiser |

**A inversão que importa:** passos 1 a 4 antes de qualquer revarredura. Fazer na ordem inversa
é pagar 104 minutos por gosto e depois descobrir que o artefato ainda não guarda as candidatas.

A S-87 não é pré-requisito de nada e é a de mais código (esquema, construção, invalidação) —
por isso fica por último, apesar de ser a que mais muda o dia a dia depois de pronta.

**Executado nesta ordem em 2026-08-15**, e a inversão se pagou: a única varredura longa do
plano rodou uma vez, com o porteiro já ligado e o cache já gravando candidatas — 28,7 min em
vez dos 104 que a mesma resposta custava, e o artefato saiu pronto para a tela ler.

---

## 5. Critérios de aceite

| critério | | estado |
|---|---|---|
| um diagrama com 12 candidatas sai preenchido em **≤3 cliques**, e a anotação diz **qual** partida e que a escolha foi **humana** | S-86 | ✅ duplo clique aplica; `chosen_game` + `filled_rule="human"` |
| `cvoff-games --apply` rodado depois **não desfaz nenhuma escolha** | S-86 | ✅ `ApplyReport.respected`, com teste |
| a varredura por posição do acervo mede **≤35 min** (era 104) | S-85 | ✅ **28,7 min** medidos, mesmos 1.641 casamentos |
| com o porteiro ligado, **os mesmos 1.641 casamentos**, dígito a dígito | S-85 | ✅ conferido na passada inteira |
| reaplicar em todos os livros a partir do cache: **<10 s**, sem abrir o `.pgn` | S-84 | ✅ segunda execução não abre a base, com teste |
| busca por nome de um diagrama: **<1 s**, e a partida escolhida é **verificada** contra a posição | S-87 | ✅ **2,7 ms** a consulta, 27 ms com replay; `verified` diz quando a posição não confere |
| os **373 ambíguos** viram um número que cai a cada sessão, e o censo mostra | S-89 | ✅ `cvoff-games --census`, e ele achou os **145 a revisar** |
| os 109 pares com inicial colada passam a casar | S-90 | ✅ zero restantes no acervo |
| nos ambíguos com legenda, a concordância sobe dos **25,5%** para **53,2%** — e não para os 73,5% do controle, porque em 46,8% deles nenhuma candidata bate | S-91 | ✅ medido; o critério original estava errado |

---

## 6. Riscos, e o que cada um exige

| risco | o que ele quebra | trava |
|---|---|---|
| **a chave do índice não ser estável entre processos** (S-87) | o índice responde zero no dia seguinte, **sem erro nenhum** | `blake2b` no lugar de `hash()`, com teste que roda outro interpretador |
| offset de uma base que não é mais a mesma (S-87) | leitura devolve movetext cortado com cara de partida | fingerprint no próprio índice; não bate, devolve vazio e diz como refazer |
| colisão de hash no índice (S-87) | a partida de outro par entra na lista | a consulta lê a partida e confere os sobrenomes |
| cache velho de uma base trocada | contagens mentem, e é a contagem que autoriza preencher | fingerprint (nome, bytes, mtime); não bateu, descarta |
| lista truncada em 32 passando por completa | a pessoa escolhe achando que viu tudo | a tela mostra sempre "32 de 147" |
| a escolha humana sobrescrevendo o que foi digitado | perde trabalho, e a ferramenta deixa de ser usada | pergunta antes; campo da base sobrescreve calado |
| `data/games_index.sqlite` (~500 MB) | repositório | fora do git, ao lado da base |
| ocupação igual com peças diferentes | nada — o `board_fen()` seguinte recusa | teste explícito na S-85 |
| revarredura com a detecção nova (S-78…S-82) | os alvos mudam, o cache cobre só parte | é o caso normal do cache: varre o que falta |
| legenda do diagrama vizinho confirmando a candidata errada (S-91) | preenche errado, com cara de conferido | ordena e marca, não filtra; a lista continua inteira e a procedência diz "concordou com a legenda" |
| os **141 já preenchidos** pelo desempate cego de 2026-08-13 | ficam errados no disco, e a S-91 não os revisita | o censo da S-89 os lista como *a revisar*; a S-86 permite trocar a partida com um clique |
| `surname()` mais agressiva (S-90) | um nome que é só uma inicial viraria vazio | o `while` guarda `len(tokens) > 1`; teste de regressão com `Coull` |

---

## 7. Como reproduzir as medições

**A tabela da §1** — distribuição de `games_matched` no artefato de 2026-08-13:

```python
import json, collections
d = json.load(open('data/games_matches.json', encoding='utf-8'))
c = collections.Counter()
for itens in d['books'].values():
    for it in itens:
        n = it.get('games_matched', 1)
        c['1' if n == 1 else '2' if n == 2 else '3-5' if n <= 5 else
          '6-20' if n <= 20 else '21-100' if n <= 100 else '>100'] += 1
print(c, sum(c.values()))
```

**Os 47 de 373 com nomes na legenda** — cruza os ambíguos com `pair_from_caption` sobre o
`caption` do índice da Galeria (`load_index`, `data/gallery/*.index.json`).

**A tabela da §1.1** — o mesmo cruzamento, comparando `{surname(White), surname(Black)}` da
partida gravada com o par da legenda, **normalizando a inicial colada dos dois lados** (a mesma
regra da S-90 — sem ela o controle mede 52,3% e o número não é da legenda, é do comparador).
Separa em dois grupos por `games_matched == 1`, que é o controle.

**A tabela da §1.2** — `pair_from_caption` em todas as entradas dos índices, contando os pares
em que o primeiro token de algum dos dois sobrenomes termina em ponto ou tem uma letra só.

**As duas tabelas da §2** — 3.000 partidas lidas do início de `pgn_database/PGN_Database.pgn`,
tokenizadas pelo `_RE_BRACES`/`_RE_SAN` do `games_db.py`, cronometradas em três variantes
(tokenizar / `+push_san` / `+board_fen`), e depois `board_fen` incondicional contra
`if b.occupied in ocupacoes` — com os 3.143 `placement` reais dos quatro índices da Galeria
como alvo.

---

## 8. As decisões, tomadas

| decisão | resolvida em 2026-08-15 |
|---|---|
| teto de candidatas guardadas | **32**. É uma constante; subir depois não quebra o cache, só o reescreve |
| **S-87, índice SQLite (~500 MB)** | **entra.** A justificativa deixou de ser velocidade: ela dá o alcance dos 1.922 diagramas que a posição não casou, e a **verificação** da partida escolhida contra a posição do diagrama |

O critério que você deu — *"se der precisão ao preencher, automático ou sugerindo os
candidatos"* — é o que a §1.1 mediu e o que ordena o plano: **S-90** conserta o comparador,
**S-91** troca um desempate que erra 72,3% por um que a legenda confirma, **S-86** entrega a
lista onde nenhum automático alcança, e **S-87** verifica o que foi escolhido.
