# Especificação da sala de estudo no Qt — Fases 73 a 77 (S-507 a S-520)

Base: [ROADMAP_ESTUDO_QT.md](ROADMAP_ESTUDO_QT.md), que traz a medição de 2026-09-01, os oito
achados e o sequenciamento. O que a sala **é** — árvore, âncora no livro, anotação, motor, saída —
está nas Fases 43 a 50 ([SPEC_ESTUDO.md](SPEC_ESTUDO.md), S-268 a S-290), e nenhum item daqui
reabre aquelas decisões. A fundação de aparência é a das Fases 20 a 24 ([SPEC_UI.md](SPEC_UI.md)),
32 a 35 ([SPEC_APARENCIA.md](SPEC_APARENCIA.md)) e 69 a 72 ([SPEC_ACABAMENTO.md](SPEC_ACABAMENTO.md)).

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
> | S-235 a S-267, S-291 a S-293 | [SPEC_EDITOR.md](SPEC_EDITOR.md) |
> | S-268 a S-290 | [SPEC_ESTUDO.md](SPEC_ESTUDO.md) |
> | S-296 a S-323, S-325 a S-430, S-451, S-452 (menos S-324) | [SPEC_REVISAO.md](SPEC_REVISAO.md) |
> | S-431 a S-440 | [SPEC_REVISAO_EXTERNA.md](SPEC_REVISAO_EXTERNA.md) |
> | S-441 a S-450 | [SPEC_ACABAMENTO.md](SPEC_ACABAMENTO.md) |
> | S-507 a S-520 | [SPEC_ESTUDO_QT.md](SPEC_ESTUDO_QT.md) |

Cada item tem **Problema** (com `arquivo:linha` do estado atual), **Solução**, **Critério de
aceite** e **Testes**. Nome de módulo é sugestão; o que importa é a fronteira de responsabilidade.

**Cinco regras valem para toda esta spec.**

1. **Decisão pura não é reescrita no widget.** É a regra que o pacote `qt/` seguiu no porte inteiro
   — *"nada de decisão reescrita"* — e cinco dos catorze itens existem porque ela foi quebrada em
   silêncio. Um item que resolva o defeito escrevendo um número novo no widget está mal escrito:
   o número já existe em `ui/`, e o que falta é a chamada.
2. **Nenhum item troca rótulo, tecla ou tabela de comandos.** `COMANDOS_DA_ABA` de
   `ui/sala_declarada.py` é a mesma antes e depois, e `comandos.acoes_fora_do_catalogo` continua
   vazio — o critério de aceite da S-280 vale para todo rearranjo desta spec.
3. **O vínculo com o OCR continua de mão única.** A sala lê a posição do diagrama e **nunca**
   escreve de volta (S-269). Nenhum item daqui inverte essa seta, e a Fase 74 só conserta o lado
   que já era permitido.
4. **`ui/estudo_lista.py` não é tocado.** A numeração de variante está travada contra o
   `StringExporter` desde a S-273, e os dois defeitos da lista são de desenho. O que muda é como o
   `qt/painel_de_estudo.py` desenha os `Trecho` que ela devolve.
5. **Acabamento não derruba ferramenta.** A regra de degradação vale aqui com dois donos a mais:
   ícone que falta desenha botão só com texto, e coordenada que não coube não impede o tabuleiro.

---

# Fase 73 — o tabuleiro que o corte deixou para trás

## S-507 · A esteira que voltou a não ter fim, e a guarda que morreu com ela — ✅ **implementada em 2026-09-01**

### Problema

`qt/tabuleiro.py:397` pinta o widget inteiro com a esteira:

    pintor.fillRect(self.rect(), QColor(tema.cor_atual(tokens.SUPERFICIE_TABULEIRO)))

É o **mesmo defeito que a S-449 mediu e consertou em 2026-08-30** (`462820e`): a esteira era o
fundo do canvas, o canvas enche o painel, e tudo o que não é tabuleiro vira quase-preto. Aquele
commit tocou `ui/board_render.py` e `ui/board_widget.py` — só o Tk. `qt/tabuleiro.py` entrou na
árvore em 2026-08-31, dentro do commit do corte (`653f88b`), sem a correção.

Medido em 2026-09-01 sobre o retângulo do próprio widget, nas três fotografias:

    760×620    widget 411×376    esteira 12,4% da área    linha do meio 10,5%
    900×800    widget 489×582    esteira 18,7% da área    linha do meio  1,6%
    1250×1000  widget 685×782    esteira 41,5% da área    linha do meio 18,2%

**A fração cresce com a janela**, e é o que torna esta versão pior que a original: o tabuleiro para
em 560 px (S-518) e tudo o que a janela ganha vira esteira. Nas linhas acima e abaixo do tabuleiro
da fotografia grande, 685 de 700 px amostrados são `#312e2b`.

E ninguém acusa: `tests/test_ui_superficies.py` — a guarda que a S-449 reforçou — não existe mais na
árvore. Saiu no corte com os 46 arquivos de teste do Tk, e nada a substituiu.

### Solução

A mesma da S-449, e é isso que a torna barata: a esteira passa a ser um **retângulo com tamanho** —
o tabuleiro mais a margem que a coordenada reserva, lida da **mesma** `margem_de_coordenada()` que a
S-508 devolve ao uso, para as duas não divergirem. O que sobra do widget é `VAZIO_DE_CANVAS`, que já
existe em `ui/tokens.py`, já tem reserva e valor de cromo escuro, e já é usado por `qt/visor.py:113`.

Nenhum papel novo, nenhum hexadecimal novo, nenhuma decisão nova: são duas chamadas a
`tema.cor_atual` no lugar de uma, e um `QRectF` em vez de `self.rect()`.

### Critério de aceite

- Na fotografia de 1250×1000 a esteira cai de **41,5% para menos de 10%** da área do widget, e o
  resto resolve por `VAZIO_DE_CANVAS`. ✅ **Medido: 7,2%.** A 900×800, 18,7% → 11,1%.
- A esteira **encolhe** quando o widget cresce, em vez de crescer com ele. ✅ É o invariante que
  separa este desenho do defeito de origem, e é o que o teste afirma — a fotografia sozinha não
  distingue "esteira menor" de "esteira que ainda é o fundo, num widget menor".
- A margem da esteira sai de `desenho_do_tabuleiro.margem_de_coordenada()`, e não de um literal. ✅
- O critério de contraste é o **reescrito** pela S-449 e não um novo: **pelo menos um** dos três —
  esteira, moldura ou casa clara — passa `AA_GRAFICO` contra o vazio, em toda paleta. Na clara são
  a esteira e a moldura; nas escuras é o próprio tabuleiro.
- `SUPERFICIES_DE_DOCUMENTO` não muda: vazio não é documento (regra da S-224).

### Testes

- `tests/test_qt_tabuleiro.py`: a esteira ocupa o tabuleiro mais a margem, e não o widget — medido
  amostrando pixel num widget deliberadamente maior que `MAX_DO_TABULEIRO`.
- `tests/test_ui_superficies.py` **volta**, traduzida para o Qt: o critério de contraste por paleta,
  uma vez por pele registrada. É a guarda que morreu no corte, e recriá-la é metade deste item.

## S-508 · As coordenadas a–h e 1–8, que o tabuleiro do Qt nunca desenhou — ✅ **implementada em 2026-09-01**

### Problema

`qt/tabuleiro.py:68` declara a margem e diz por escrito o que falta:

    MARGEM = 8
    """Folga em volta. É o mesmo `margin` que `board_widget` passa quando não desenha coordenadas --
    e este tabuleiro não desenha."""

Quem estuda um livro lê `14.Ng3` na página impressa e precisa achar g3 no tabuleiro. Sem
coordenada, conta casas. É a aba em que a leitura da página e o tabuleiro trabalham juntos, e é
justamente ali que falta o que liga um ao outro.

Do lado puro a decisão está inteira e **sem nenhum chamador** em `src/` e `tests/`:
`desenho_do_tabuleiro.margem_de_coordenada` (linha 99), `COORD_FONT` (93), `COORD_OFFSET_PX` (96) e
`COORDINATE_TEXT` (91). `margem_de_coordenada` carrega no docstring a medição que a criou — o
`11` do deslocamento e o `28` do chamador estavam soltos em arquivos diferentes, e a base de
`a b c d e f g h` saía cortada nos **dois** tabuleiros da janela.

### Solução

`TabuleiroQt` desenha as oito letras e os oito números, com a fonte de `COORD_FONT`, a cor de
`tokens.COORDENADA` e a margem de `margem_de_coordenada()` — que passa a ser o `margin` de
`BoardGeometry.fit`, no lugar do `MARGEM = 8`. As coordenadas acompanham a **virada** do tabuleiro:
com as pretas embaixo, `a` fica à direita.

Desenhar coordenadas é uma preferência, e ela já existe do outro lado (`_show_coordinates`). Aqui
ela nasce **ligada** e sem controle: um interruptor a mais nesta aba, que já tem 28 botões, é o
oposto do que a Fase 76 faz. Se um dia alguém pedir para desligá-las, o `MARGEM = 8` continua sendo
a resposta do ramo desligado — é para isso que ele existe no `board_widget`.

### Critério de aceite

- As oito letras e os oito números aparecem **inteiros**, sem corte na base, no piso (240 px) e no
  teto do tabuleiro. ✅ Afirmado por ausência de tinta logo abaixo da esteira, onde o fundo é o
  vazio: se a letra vazasse, ela apareceria ali.
- A margem sai de `margem_de_coordenada()`; zero literal novo no sítio. ✅ `MARGEM` deixou de ser
  `8` e passou a **ser** a chamada — o `8` não ficou como ramo desligado, porque no Qt não há um.
- ~~Virar o tabuleiro (`flip_board`) troca a ordem das duas réguas.~~ **Reescrito: como estava, o
  critério era invencível na bancada.**

> **A plataforma `offscreen` da suíte não tem fonte nenhuma** — `QFontDatabase.families()` devolve
> vazio —, então `a` e `h` desenham o mesmo retângulo. Um teste que comparasse as duas fotografias
> passaria em verde **com a ordem invertida**, que é guarda vácua com outro nome. A ordem virou uma
> decisão pura, `desenho_do_tabuleiro.reguas(virado)`, afirmada na função; o que amarra o widget a
> ela é um `assertIs`, que é a mesma forma que a S-501 usou para a tabela de glifos.
- A cor resolve por `cor()` nas três peles, sobre a esteira — que é o que a S-147 escolheu escura
  para dar 11,03:1 a este texto.

### Testes

- `tests/test_qt_tabuleiro.py`: a margem devolvida por `geometria()` é a de `margem_de_coordenada()`;
  o texto desenhado nos quatro cantos está dentro do widget; virar troca a ordem.
- A guarda de órfãos da S-511 passa a achar `margem_de_coordenada` com chamador.

## S-509 · O último lance, que o modelo sabe e ninguém pinta — ✅ **implementada em 2026-09-01**

### Problema

`ui/board_model.py:88` declara `last_move`, e `:170` calcula as duas casas dele:

    last_move: chess.Move | None = None
    def last_move_squares(self) -> frozenset[int]: ...

Puro, testado, e **nunca recebe valor**. `push_move` não o escreve, e `mostrar_tabuleiro`
(`qt/tabuleiro_de_jogo.py`) faz `tabuleiro.copy(stack=False)`, que descarta a pilha de onde ele
sairia sozinho. O papel de cor existe — `CASA_ULTIMO_LANCE`, com apelido `LAST_MOVE_SQUARE` em
`desenho_do_tabuleiro.py:73` — e tem zero chamadores.

O efeito é diário: navegar a árvore com `←`/`→` redesenha a posição e **não diz qual lance
aconteceu**. Numa linha de dez lances, achar o que mudou é comparar duas telas de memória. É a
marcação que todo programa de xadrez tem, e a única da sala que o modelo já sabia calcular.

### Solução

`mostrar_tabuleiro` ganha o lance como **argumento**, e o painel o passa: quem o tem é
`self.estudo.no.move`, que é a aresta que chegou ao nó corrente. O `copy(stack=False)` continua —
a sala não quer a partida inteira dentro do modelo, quer a última aresta, e passá-la explicitamente
é mais barato e mais claro que carregar a pilha.

O desenho é da base (`TabuleiroQt`) e não do tabuleiro de jogo: quem corrige um OCR também se
beneficia de ver a última casa mexida, e a S-147 já unificou os dois canvas por esse tipo de
argumento. As duas casas são pintadas **abaixo** da peça e **abaixo** da seleção — é fato sobre a
posição, e não anotação humana; a ordem de camadas que `paintEvent` já documenta não muda.

`estudo.no.move` é `None` na raiz, e ali **nada é pintado**: a posição do diagrama não veio de
lance nenhum, e marcar duas casas ali seria inventar uma jogada que o livro não imprimiu.

### Critério de aceite

- Andar um lance pinta exatamente duas casas; voltar à raiz não pinta nenhuma. ✅
- A cor resolve por `cor()` e é `CASA_ULTIMO_LANCE`; zero hexadecimal no sítio. ✅
- A marca sobrevive à virada do tabuleiro (é índice de leitura, e `display_from_index` já converte). ✅
- Desfazer/refazer (`Ctrl+Z`) repõe a marca **do nó em que o desfazer parou**. ✅

> **A frase deste critério dizia "do nó restaurado", e isso é impreciso o bastante para enganar.**
> `_aplicar_pgn` recarrega o estudo e reaplica o caminho anterior — que muitas vezes **não existe
> mais**, e aí `ir_para` cai na raiz, como aquele método já documenta. Desfazer o segundo lance
> deixa o cursor na raiz, e a marca certa ali é **nenhuma**. O invariante que vale, e que o teste
> afirma depois de cada gesto, é mais simples: *a marca é sempre a do nó corrente*.

### Testes

- `tests/test_qt_tabuleiro.py`: duas casas na cor do papel depois de um lance, nenhuma na raiz.
- `tests/test_qt_painel_de_estudo.py`: navegar até um nó e voltar mantém a marca coerente com
  `estudo.no.move` — a afirmação é sobre o modelo, não sobre pixel.

## S-510 · Os três números do desenho que o widget reescreveu — ✅ **implementada em 2026-09-01**

### Problema

`qt/tabuleiro_de_jogo.py` desenha três coisas com números próprios, ao lado de constantes puras que
dizem exatamente aquilo:

    :242   pintor.setBrush(QColor(tema.cor_atual(tokens.CONTORNO_DE_SELECAO)))   # o alvo usa a cor da seleção
    :271   caneta.setWidthF(max(2.0, geo.cell * 0.14))                           # LARGURA_DA_SETA = 0.16
    :265   ponta = geo.cell * 0.34                                               # "a ponta é 2,6 vezes isso"

`desenho_do_tabuleiro.py` declara `TARGET_MARK` (`tokens.ALVO`, linha 75), `LARGURA_DA_SETA = 0.16`
(146) e `LARGURA_DO_CIRCULO = 0.055` (149) — os três com **zero** chamadores. O ponto de "pode ir
aqui" e a casa selecionada saem hoje da **mesma** cor, que é a definição de duas coisas diferentes
pintadas igual — o defeito que a S-145 mediu.

`LARGURA_DO_CIRCULO` não tem cliente porque a casa marcada (`[%csl]`) não é desenhada em lugar
nenhum. Isso é falta de recurso e **não** entra neste item: o `_soltar_seta` já documenta que a
sala não oferece o gesto. Fica registrado aqui para que a guarda da S-511 possa isentá-lo **por
escrito**, em vez de tratá-lo como órfão silencioso.

### Solução

Três substituições, nenhuma decisão nova: o alvo passa a `tokens.ALVO`; a haste da seta passa a
`LARGURA_DA_SETA`; a ponta passa a ser derivada dela pelo fator que o próprio docstring declara
(2,6×), em vez de um segundo literal. `LADO_DO_ALVO = 0.28` continua em `qt/tabuleiro_de_jogo.py`:
ele é o **diâmetro do ponto**, uma medida que o módulo puro não declara, e o docstring dele carrega
a razão de ser ponto e não moldura.

### Critério de aceite

- O alvo e a casa selecionada resolvem por papéis **diferentes**. ✅
- Nenhum dos três números aparece como literal em `qt/`. ✅ Afirmado por varredura de
  `geo.cell * <literal>` sobre o arquivo, e não só pela leitura.
- A haste da seta vai de 0,14 para 0,16 da casa — menos de um pixel numa casa de 60. **A ponta
  muda mais do que este critério previa**: de 0,34 para 0,416, que são ~5 px na mesma casa. É o
  que a proporção declarada manda (`FATOR_DA_PONTA = 2,6`, que estava só na prosa), e o widget
  vinha usando 2,43 sem que nada dissesse por quê.

> **Eram três números e são cinco, e os dois novos são o mesmo achado da S-501 com outro nome.**
>
> **Quarto:** `qt/tabuleiro_de_jogo.COR_DA_SETA` era uma **cópia byte a byte** de
> `desenho_do_tabuleiro.PAPEL_DE_SETA` — quatro pares mantidos em dois lugares, exatamente como a
> tabela de glifos que a S-501 desduplicou neste mesmo pacote, e com um docstring em cada uma
> explicando a mesma decisão. Virou apelido, e o teste é o mesmo `assertIs`.
>
> **Quinto, e fora do tabuleiro de jogo:** a tinta do glifo de reserva, em `qt/tabuleiro.py`, saía
> de `GLIFO_CLARO`/`GLIFO_ESCURO` — que são o valor de `RESERVA`, o hexadecimal de fábrica. Ele
> **não acompanha a troca de pele**: o glifo saía da mesma cor nas três. Passou a sair de
> `tema.cor_atual(tokens.GLIFO_*)`, e os dois apelidos foram junto com os outros dez na S-511.

### Testes

- `tests/test_qt_tabuleiro.py`: o pixel do centro de uma casa-alvo não é a cor do contorno de
  seleção.
- Varredura: nenhum `geo.cell * <literal>` em `qt/tabuleiro*.py` sem constante nomeada — a mesma
  forma das guardas de hexadecimal cru que o corte já traduziu para o Qt.

## S-511 · A conta que faltava: de cada decisão pura de `ui/`, quem a chama? — ✅ **implementada em 2026-09-01**

### Problema

A conta do catálogo pergunta se uma ação tem **dono** e se o dono é **chamável**. `lambda: None`
passa nas duas. E **nada pergunta se um módulo puro de `ui/` ainda tem importador** — módulo órfão
não quebra teste nenhum, porque o teste dele continua verde medindo a decisão sozinha.

Foi assim que sete decisões ficaram sem chamador no corte do Tk e só voltaram um mês depois
(`adda88f`). Quatro dos itens desta spec — S-507, S-508, S-509 e S-510 — são a oitava à décima
primeira, e todas moram no mesmo arquivo. **A instância muda; o mecanismo não.**

Medido em 2026-09-01, sobre `__all__` de todos os módulos puros de `ui/`:

    416 nomes exportados, 51 módulos
    125 sem nenhum uso fora do próprio módulo em src/ (31 módulos)
     48 desses são tocados por algum teste
     77 não são tocados por nada -- nem src/, nem tests/

`desenho_do_tabuleiro.py` sozinho responde por **17 dos 77**, e a causa é uma só: os apelidos
`X = tokens.RESERVA[Y]` existiam para dar **cor literal** ao `tk.Canvas`, que não conhecia papel.
No Qt a cor vem sempre de `tema.cor_atual(papel)`, então o apelido perdeu a função junto com o
toolkit — e ficou.

O número é um **piso**, e não um retrato: a varredura casa o nome em texto cru, então um nome
citado só num docstring conta como usado.

### Solução

Uma guarda paramétrica sobre `__all__`, com **lista de exceções que exige motivo escrito** — a
mesma forma das outras varreduras deste projeto, e a mesma razão: a exceção declarada é a que se
revisa, e a silenciosa é a que apodrece.

    SEM_CHAMADOR: dict[str, str] = {
        "desenho_do_tabuleiro.LARGURA_DO_CIRCULO": "a casa marcada ([%csl]) ainda não é oferecida "
                                                   "pela sala -- ver `_soltar_seta`",
        ...
    }

**Este item não é "conserte os 77".** Ele é: tornar a pergunta *fazível*, triar o que este plano
toca, e travar o resto numa catraca que não sobe. A triagem obrigatória é a de
`desenho_do_tabuleiro.py`, e ela tem **quatro** saídas por nome — **dar chamador** (é o que as
S-508 a S-510 fazem), **apagar** (é o que os apelidos de reserva pedem, pelo mesmo argumento que
aposentou `ui/texto_etiquetas.py`: módulo que perdeu o consumidor sai, e a guarda viva que ele
carregava é reposta **antes** da remoção), **tirar do `__all__`** (o nome é usado, mas dentro do
próprio módulo — exportá-lo era a declaração errada, e não a falta de um cliente), ou **isentar com
motivo**.

> **A quarta saída não estava nesta lista, e a implementação a acrescentou.** `HEATMAP_LOW` e
> `HEATMAP_HIGH` são os extremos da rampa e quem os usa é `heatmap_color`, no mesmo arquivo. Não
> são API, não têm chamador de fora, e nenhuma das outras três saídas os descreve: dar chamador
> seria inventar um, apagar quebraria a rampa, e isentar diria que falta cliente quando o que
> faltava era a declaração estar certa.

O resto entra na catraca com o número medido. Ela desce quando alguém tria um; ela **não sobe**:
exportar um nome novo sem chamador passa a falhar, nomeando o módulo e o nome.

### Critério de aceite

- A guarda roda sobre `__all__` de todo módulo puro de `ui/` e reprova nome exportado sem uso em
  `src/`, salvo entrada em `SEM_CHAMADOR` **com motivo não vazio**.
- Toda entrada de `SEM_CHAMADOR` é conferida: um nome que **ganhou** chamador e continua na lista
  também reprova — senão a lista vira perdão em vez de mapa, que é a regra que `RENUMERADOS` já
  segue em `tests/test_docs.py`.
- Ao fim da Fase 73, `desenho_do_tabuleiro.py` contribui **zero** para a contagem: cada um dos 18
  tem chamador, foi apagado, saiu do `__all__`, ou está isento por escrito. ✅ **Sobrou um**,
  `LARGURA_DO_CIRCULO`, isento com o motivo escrito — os doze apelidos de cor foram apagados, cinco
  ganharam chamador (`COORD_FONT`, `COORD_OFFSET_PX`, `margem_de_coordenada`, `LARGURA_DA_SETA`,
  `PAPEL_DE_SETA`) e dois saíram do `__all__`.
- A catraca dos demais está no arquivo com o número medido e a data. ✅ `TETO_DE_ORFAOS = 136`.

> **O número deste item estava errado, e o instrumento era o culpado — de novo.** A medição de
> abertura usou busca de **texto** sobre `src/`, e ali um nome citado num **docstring** conta como
> uso. Neste projeto os módulos se descrevem uns aos outros em prosa o tempo todo, então a busca de
> texto **subestima**: `margem_de_coordenada` aparecia num docstring de `ui/tokens.py` e não entrou
> nos 125.
>
> Pela varredura de identificador — `ast`, contando `Name`, `Attribute.attr` e `alias`, que é a que
> a guarda usa — eram **153** antes da fase, com **18** em `desenho_do_tabuleiro.py`. Depois são
> **136**. Os dois números medem coisas diferentes e os dois estão certos; o que vale para a
> catraca é o estrito, e é por isso que ele está no arquivo do teste e não só aqui.

### Testes

- `tests/test_ui_orfaos.py` (novo): as três afirmações acima.
- A guarda tem de achar **alguma coisa** para provar que não é vácua — a mesma trava que
  `test_a_varredura_acha_os_links` usa: com a lista de exceções vazia, a contagem é maior que zero.
  É a lição da S-506, em que ~20 varreduras passaram em verde sobre lista vazia.

### O que a triagem dos 134 achou — 2026-09-02, catraca em **zero**

O item deixou 134 perguntas em aberto e a catraca para elas não subir. A triagem respondeu todas
no dia seguinte, em dois lotes, na branch `triagem-dos-orfaos`. A conta das quatro saídas:

| saída | quantos | o que era |
|---|---|---|
| tirar do `__all__` | 74 | nome usado dentro do próprio módulo, pelas funções que são a API — o caso de `HEATMAP_LOW`, repetido em vinte módulos |
| isentar com motivo | 36 | três motivos se repetem, e nenhum é "falta cliente": o **tipo** que o cliente usa sem nomear (`Atalho`, `Geometria`, `Queda`…), o **instrumento** com que uma guarda mede (`razao_de_contraste`, `texto_de`…) e a **tabela** que uma guarda percorre inteira (`CATALOGO`, `SUPERFICIES`, `QUEDAS`, `ICONES`, `SOBREPOSICOES_NO_EDITOR`) |
| apagar | 16 | as quatro cores literais e o `box_color` de `leitura_do_pdf`; `desvio_de_centralizacao` e `regiao_de_rolagem`, que o canvas do Tk pedia e o `QScrollArea` faz por `setAlignment`; `saved_on_page` e `mark_confirmed`, órfãs desde antes do corte; `ligacoes` do `bind_all`; `PONTOS_POR_POLEGADA` do `tk scaling`; `em_destaque`; as duas etiquetas do Tk de `texto_cores`; `ETIQUETA_DO_LEXICO`; e a metade Tk de `ui/icones.py` — `icone`, o cache de `PhotoImage` e `limpar_cache` |
| dar chamador | 8 | todos decisão que perdeu o chamador no porte — e, no caminho deles, três guardas que tinham morrido no corte voltaram. Os onze estão abaixo |

**As onze decisões desligadas que a triagem religou — a instância muda, o mecanismo não.**

1. `leitura_do_pdf.SELECTION_HALO_PX`: `qt/visor.py` a reescrevia como `HALO_DA_SELECAO = 4`. No
   caminho, a cor da caixa saía de `tokens.RESERVA[...]` — o mesmo achado da S-510 sobre o glifo
   de reserva, numa terceira tela — e passou a sair de `tema.cor_atual`, no momento de pintar.
2. `abas.ABAS`: a janela copiava a ordem em seis `addTab`, e a tupla seguiu declarando a aba
   Configuração, que saiu no porte (S-506), por um mês. É o mesmo formato do `NAS_BARRAS_DO_PDF`:
   sem leitor, uma declaração não só perde o chamador, ela **deriva**. A tupla deixou de declarar
   a Configuração, a janela passou a lê-la, e uma aba declarada sem painel reprova na montagem.
3. `page_overlay.frase_de_caixa_tirada` e `frase_de_caixas_devolvidas`: reescritas inline em
   `qt/janela.py`, com outro texto — a versão do Qt não nomeava o caminho de volta.
4. `geometria.FRACAO_PADRAO_DO_DIVISOR`: o padrão da primeira execução (S-156) era, no Qt, um par
   de pixels da montagem.
5. `dispositivos.dispositivos_da_janela`: reescrita em `qt/janela._dispositivos` com `motivo=""`
   cravado — "os pesos não estão no disco" e "o motor é outro" saíam com a mesma palavra no rodapé.
6. `atalhos.conferir_dono`: o critério de aceite da S-244, chamado na montagem de cada painel do
   Tk, só existia como teste no Qt. Voltou aos quatro painéis que declaram ações.
7. `atalhos.TECLAS_DO_EDITOR` e `SOBREPOSICOES_NO_EDITOR`: a tabela veio no porte, o `Text.bind`
   não. **`Ctrl+B` não fazia nada no editor de texto do Qt**, medido em 2026-09-02, e a guarda de
   foco tomava `Ctrl+R` do editor para reler a página. As teclas passaram a ser ligadas por
   `QShortcut` com alcance no editor; `teclas_cedidas_ao_editor` diz à guarda o que ceder, e uma
   tecla que entre nas duas tabelas sem sobreposição declarada reprova na montagem.
8. `degradacao.QUEDAS`: a tabela do contrato de degradação (S-234) ficou sem quem a percorresse —
   `test_ui_degradacao` morreu no corte com a raiz Tk que abria — e a linha `pasta_de_pecas`
   apontava para o `PieceImages`, que não existia mais. No Qt a pasta ausente caía no glifo **em
   silêncio**. O teste voltou, na versão pura; `carregar_pecas` ganhou o aviso; e a troca de pele
   voltou a chamar `esquecer_avisos`.
9. `geometria.fracao_do_documento`: o orçamento da S-232 — o documento fica com pelo menos 60% da
   altura — nunca teve teste nem chamador. Ganhou a guarda em `test_qt_fita`.
10. `viewport` (S-157): a página centrada na vista deixou de ter guarda quando a conta do Tk saiu.
    `test_qt_painel_do_pdf` afirma o `setAlignment` no lugar dela.
11. `abas.contagem_no_rotulo` e os testes puros de `ui/abas.py`: o arquivo de teste inteiro morreu
    no corte porque lia o `app_tkinter.py`. A parte pura voltou.

**Dois achados que não são órfão, e por isso não foram consertados aqui.** Medidos ao ligar as
teclas do editor: (a) **a digitação no editor de texto do Qt não chega ao documento** — o
`QTextEdit` recebe o texto e `documento` fica como estava, então salvar grava a folha sem o que foi
digitado; e (b) o mostrador de corpo (S-292) e as listas de escolha exclusiva (S-259/S-262) não
foram portados. Os cinco nomes que os declaram ficaram em `SEM_CHAMADOR` com o motivo escrito,
como `LARGURA_DO_CIRCULO`: o que falta não é chamador, é o recurso. O (a) é item para a próxima
fase — é o defeito de maior custo que este plano encontrou, e ele não estava na lista dos oito.

**A guarda ganhou o controle que faltava.** `test_uso_em_docstring_nao_conta_e_uso_em_codigo_conta`
afirma o detector contra fonte de mentira, e não contra o arquivo real — a mesma trava da guarda
dos inertes (S-505): ancorado no arquivo, um detector se apaga junto com o defeito.

---

# Fase 74 — os dois fios cortados

## S-512 · "Seguir OCR selecionado" volta a seguir, e só reabre quando a âncora muda — ✅ **implementada em 2026-09-01**

### Problema

A caixa nasce marcada (`qt/painel_de_estudo.py:224`) e **nada chama `sync_with_ocr`**
(`:728`). Os únicos chamadores em `src/` são o próprio `on_follow_ocr_toggle` e um teste.

No Tk o fio existia: `ui/result_panel.py` chamava `on_sync_study` em três pontos — selecionar
diagrama, aplicar posição e editar casa — e `app_tkinter.py:1537` o repassava ao painel. A janela
do Qt liga `painel.selecionou` só ao visualizador (`qt/janela.py:862`).

O efeito é que a promessa da S-270 — *"trocar de diagrama deixa de ser recomeçar e passa a ser ir
para a outra mesa"* — não acontece sozinha: é preciso apertar "Carregar OCR atual" a cada diagrama,
ou desmarcar e remarcar a caixa. **A configuração padrão da aba descreve um comportamento que ela
não tem.**

### Solução

Duas metades, e a segunda é o item.

**A ligação:** um sinal novo, `painel.posicao_mudou`, ligado à sala na `_ligar()` da janela, ao
lado da que já existe entre `selecionou` e o visualizador.

> **Não é `selecionou`, e a diferença é o que a implementação corrigiu nesta spec.** `selecionou`
> tem um significado — *este diagrama passou a estar em edição* — e serve ao visualizador, que
> destaca a caixa. O que a sala precisa saber é outra coisa: *a posição mostrada aqui mudou*, e ela
> muda também por casa corrigida, por FEN aplicada e por desfazer. No Tk eram **três** chamadas a
> `on_sync_study`; aqui as três se encontram em `_atualizar_tudo`, que existe exatamente por isso,
> e o sinal sai de lá. Um sinal com um significado em vez de três chamadas que alguém precisa
> lembrar de acrescentar na quarta origem.

**A guarda de âncora, que é pura.** `_abrir` (`:758`) chama `_historico.zerar()` sem condição
(`:768`). Ligar o sinal cru a ele devolveria o fio e criaria outro defeito: **cada edição de casa
na aba Resultado zeraria a pilha de desfazer do estudo aberto**, e `edicao` é o contador que
`ui/desfazivel.py` lê para decidir de quem é o `Ctrl+Z`.

A decisão é uma comparação de chave — *reabrir só quando `posicao.ancora.chave()` difere da âncora
do estudo aberto* — e mora em `ui/sala_declarada.py`, ao lado de `posicao_de_estudo`, porque é
afirmável sem janela.

**Chaves iguais não é "não faça nada".** É *"atualize a posição de partida se o estudo ainda estiver
vazio"*: corrigir uma casa antes de jogar o primeiro lance tem de chegar ao tabuleiro. Com lance
jogado, a posição de partida **não** muda — o que existe é análise humana sobre ela, e `Sala.abrir`
já devolve o mesmo objeto para a mesma âncora, então isso cai de graça.

**E há uma quarta resposta, que esta spec não previa: âncora inválida também é `NADA`.** Item de
fila e amostra do dataset não têm par no livro (`posicao_de_estudo` os monta com `pagina=-1`), então
a âncora **não identifica mesa**. Seguir uma delas recomeçaria o estudo avulso em curso a cada
atualização — e com o sinal disparando por casa corrigida, isso é a cada tecla. O caminho para
estudá-las continua sendo "Carregar OCR atual", que é explícito e não passa por aqui.

### Critério de aceite

- Selecionar outro diagrama com a caixa marcada troca a mesa, e o `contagem_de_lances()` do estudo
  anterior é anunciado no rodapé, como a S-270 promete. ✅
- Editar uma casa do diagrama **já aberto** não muda `edicao` e não zera a pilha de desfazer. ✅
  Afirmado pelos três: `edicao`, o nó corrente, e um `desfazer()` que ainda devolve a posição.
- Editar uma casa do diagrama já aberto **e vazio** atualiza a posição do tabuleiro de estudo. ✅
- A caixa desmarcada continua não seguindo nada, e marcá-la sincroniza na hora (é o que
  `on_follow_ocr_toggle` já faz). ✅
- A seta continua de mão única: nada na sala escreve no painel de resultado. ✅
- **A atualização silenciosa não fala no rodapé.** ✅ Critério novo, e ele apareceu ao ligar: com o
  sinal disparando por casa corrigida, a frase "Estudo do diagrama selecionado." apareceria a cada
  tecla e enterraria a de quem está corrigindo. `_abrir` passou a aceitar `status=""` como "não
  anuncie"; a **troca de mesa** continua se anunciando, porque ela é um acontecimento.

### Testes

- `tests/test_ui_sala_declarada.py`: a decisão de reabrir, tabelada — mesma âncora, âncora
  diferente, âncora inválida, estudo vazio e estudo com lance.
- `tests/test_qt_painel_de_estudo.py`: `edicao` não sobe quando a sincronia chega com a mesma
  âncora. É a mesma forma da guarda da S-346, em que virar o tabuleiro sequestrava o `Ctrl+Z`.
- `tests/test_qt_janela.py`: o sinal está ligado — afirmado pelo **efeito**, e não por `patch` no
  método, porque depois do `connect` trocar o método não troca quem o sinal chama.

## S-513 · O clique no diagrama da página chega à sala — ✅ **implementada em 2026-09-01**

### Problema

`qt/janela.py:1283` decide o clique num retângulo da página por `page_overlay.decide_box_click`,
que é pura e devolve `SELECT` ou `RECOGNIZE`. No ramo `SELECT`, a janela seleciona a linha na aba
Resultado e **traz aquela aba para a frente**; no `RECOGNIZE`, lê a página. **Nenhum dos dois avisa
a sala.**

Somado à S-512, hoje não há gesto nenhum que leve um diagrama do livro ao tabuleiro de estudo sem
passar pela aba Resultado e apertar um botão — que é o caminho mais longo para o gesto mais comum
de quem estuda um livro.

### Solução

`SELECT` passa a **também** avisar a sala, e continua fazendo o que já fazia. `decide_box_click`
não muda, e é isso que faz este item ser de fiação e não de decisão: o índice já é o do diagrama
certo, e quem monta a posição inteira — campo, vez, número do lance e âncora — é
`painel.posicao_de_estudo`, que a S-269 já escreveu.

Com a caixa "Seguir OCR" marcada, o clique na página põe o diagrama no tabuleiro; desmarcada, ele
não põe — e é a mesma preferência que governa a S-512, não uma segunda.

**Qual aba vem para a frente continua sendo a Resultado**, e é decisão consciente: o clique numa
caixa é o gesto de *conferir o que o modelo leu*, e trocar o destino dele mudaria o que o gesto
significa para quem está corrigindo. Quem quer estudar já está na aba Estudo, e ali o que ele vê é
o tabuleiro trocando — o que é exatamente o pedido.

> **O que foi considerado e recusado.** Um gesto novo — duplo-clique ou `Ctrl`+clique — com uma
> terceira resposta `ESTUDAR` em `decide_box_click`. Foi a primeira ideia, e ela cria uma terceira
> coisa que um clique na página pode significar, num lugar onde o clique simples e o botão direito
> (que dispensa a caixa, S-177) já significam duas. Com a S-512 no lugar, o `SELECT` que já existe
> leva ao diagrama certo: o gesto novo seria cobrar aprendizado por um fio que estava cortado.

### Critério de aceite

- Clicar num retângulo de página já lida põe aquele diagrama no tabuleiro de estudo, com vez,
  direito a roque e número de lance — sem passar por "Carregar OCR atual". ✅
- Clicar num retângulo de página **não** lida continua lendo a página, e o diagrama escolhido chega
  à sala depois da leitura, pelo mesmo caminho. ✅
- `decide_box_click` não muda: mesmos dois valores, mesma decisão, mesmo teste. ✅
- A aba que vem para a frente continua sendo a Resultado. ✅

> **Este item não custou uma linha de código além da S-512**, e é o que a recusa do gesto novo
> previa: o `SELECT` já levava ao diagrama certo, a seleção já repinta o painel, e o repinte agora
> emite. O que existe de próprio aqui são os testes — inclusive o que fixa a aba que vem para a
> frente, que é o critério contra o qual uma "melhoria" futura seria medida.

### Testes

- `tests/test_qt_janela.py`: o clique na caixa chega ao painel de estudo — afirmado pela âncora do
  estudo aberto depois do clique, e não por espião no sinal.
- `tests/test_page_overlay.py`: inalterado, e é o critério — se ele precisou mudar, o item saiu do
  escopo.

---

# Fase 75 — a lista que se lê

## S-514 · O recuo de variante que o Qt descarta — ✅ **implementada em 2026-09-01**

### Problema

`ui/sala_declarada.py:47` declara `RECUO_POR_NIVEL = 18`, e `qt/painel_de_estudo.py:460` o aplica:

    estilo = [f"margin-left:{recuo}px"]

num `<span>`. **O `QTextDocument` descarta margem em elemento inline.** Perguntado ao próprio Qt,
todos os blocos do documento saem com `blockFormat().leftMargin() == 0.0`, e os `<br>` que a lista
emite antes do `(` e depois do `)` viram separador de linha **dentro do mesmo bloco**, e não blocos
novos.

A decisão pura está certa, é testada, e não pinta um pixel: na fotografia, `( 3... Nf6` começa na
mesma coluna de `1. e4`. Uma árvore de variantes sem recuo é uma lista em que o nível some — e o
nível é a única coisa que distingue a linha principal de uma subvariante de terceiro grau.

### Solução

Cada trecho de variante passa a ser emitido como elemento **de bloco** (`<div>`), que é o único a
que o `QTextDocument` aplica `margin-left`. `RECUO_POR_NIVEL` continua sendo 18 e continua morando
em `ui/sala_declarada.py`: o número não muda, muda o elemento.

Os `<br>` antes do `(` e depois do `)` saem junto — eles existiam para produzir a quebra que o bloco
passa a dar sozinho, e mantê-los daria linha em branco entre variantes.

A âncora `corrente` e o `scrollToAnchor` continuam funcionando: `<a name=...>` dentro de bloco é o
caso normal, e é o que o `QTextBrowser` já resolve.

### Critério de aceite

- Uma variante de nível 1 é desenhada 18 px à direita da principal, e uma de nível 2, 36 px —
  medido em `blockFormat().leftMargin()`, e não a olho. ✅
- O recuo satura em `NIVEL_MAXIMO_DE_RECUO` e a numeração não, como `estudo_lista` já manda. ✅
- `scrollToAnchor("corrente")` continua levando ao lance corrente depois de um redesenho. ✅

> **Uma regra a mais apareceu ao desenhar: a variante abre bloco mesmo no mesmo recuo.** Sem ela,
> duas irmãs — `( 2. Bc4 ) ( 2. d4 )` — correriam na mesma linha, porque o recuo delas é igual. Era
> o que os dois `<br>` de antes faziam por acidente; agora é a estrutura que diz, e não uma quebra
> solta no meio do texto.
- `texto_de(trechos(e))` continua igual, token a token, ao `StringExporter` — a trava da S-273 não
  é tocada, porque este item não mexe em `ui/estudo_lista.py`.

### Testes

- `tests/test_qt_painel_de_estudo.py`: a margem de bloco por nível, lida do `QTextDocument` do
  painel montado. É a única forma de afirmar isto: o defeito é o Qt **aceitar** o HTML e ignorar a
  propriedade, então nada que olhe o HTML gerado o pegaria.

## S-515 · A notação que quebra no meio do lance — ✅ **implementada em 2026-09-01**

### Problema

`qt/painel_de_estudo.py:483` troca **todo** espaço por espaço inquebrável:

    texto = html.escape(trecho.texto).replace(" ", "&nbsp;")

Isso tira toda oportunidade de quebra da linha. O `wordWrapMode` de fábrica do `QTextEdit` é
`WrapAtWordBoundaryOrAnywhere`: sem fronteira de palavra, ele quebra **onde couber**. Medido num
documento de 240 px de largura:

    '1. Nf3 Nc6 2. Nf3 N'
    'c6 3. Nf3 Nc6 4. Nf'
    '3 Nc6 5. Nf3 Nc6 6.'

Na fotografia de 760 px o defeito aparece duas vezes na tela: `O-O` sai como `O-` / `O`, e a frase
do comentário sai como `guard` / `am`. Numa lista de notação, `N` / `c6` não é feio — é ilegível, e
o leitor precisa remontar o lance de cabeça.

### Solução

A separação certa é a que a lista **já faz** entre o que se lê e o que se grava: o espaço **dentro**
de um trecho não pode quebrar (`12. ` e `Ba4 ` são uma unidade), o espaço **entre** trechos pode.
Quem sabe onde um trecho acaba é o próprio `Trecho`, e ele está na mão de quem monta o HTML.

O espaço final de cada trecho vira espaço normal; os internos continuam inquebráveis. O comentário
é o caso em que a diferença mais aparece: ele é prosa, e prosa quebra em toda palavra.

**Não é trocar o `wordWrapMode`.** `WrapAnywhere` desligado (`WrapAtWordBoundary` puro) faria a
linha estourar a largura quando um token não coubesse — e o `1250×1000` de hoje viraria rolagem
horizontal numa janela estreita. O modo de fábrica está certo; o que estava errado era não haver
onde quebrar.

### Critério de aceite

- Nenhum token de SAN é partido em duas linhas em nenhuma largura entre 240 e 900 px — afirmado
  sobre o `QTextLayout` do documento, e não a olho. ✅
- O número do lance não se separa do lance: `12.` e `Ba4` não caem em linhas diferentes. ✅
- O texto do comentário quebra em fronteira de palavra. ✅
- `texto_de` continua igual ao `StringExporter`. ✅

> **Os dois primeiros critérios viraram um só, e ele é mais forte que os dois.** O teste afirma que
> **toda** quebra visual cai depois de um espaço comum. Se isso vale, então nenhum token foi
> partido *e* nenhum `&nbsp;` — o que gruda `12.` em `Ba4` e `(` no primeiro lance — foi quebrado.
> Uma afirmação, duas garantias, e nenhuma lista de tokens a manter.
>
> **E a medição precisou de um documento à parte.** `QTextEdit` refaz a largura do documento a
> partir do próprio viewport a cada leiaute, então um `setTextWidth` no documento *dele* é
> sobrescrito: media-se a geometria de um widget que nunca foi mostrado — linhas de 72 px pedindo
> 240. O HTML é o mesmo, e é dele que a quebra depende.

### Testes

- `tests/test_qt_painel_de_estudo.py`: para cada largura de uma tabela (240, 320, 480, 900), toda
  linha visual começa e termina em fronteira de trecho. A afirmação é sobre o layout, que é onde o
  defeito mora.

## S-516 · A árvore que dobra — ✅ **implementada em 2026-09-01**

### Problema

A lista corrida serve bem um estudo de livro — 66 trechos na fotografia, e é o tamanho típico de um
diagrama anotado. Ela deixa de servir quando o estudo passa de umas três dezenas de lances com
subvariantes, que é o que acontece ao abrir uma partida anotada pelo "Abrir PGN…" (o comando aceita
20 MB, `TAMANHO_MAXIMO_DE_PGN`). Ali, achar a linha em que se está exige rolar a lista inteira, e a
subvariante de terceiro grau ocupa a mesma altura da principal.

Medido: 1.606 trechos custam 49 ms por redesenho, e 97 mil custam 3,2 s — mas o custo não é o item.
O item é que **não há como esconder o que não interessa agora**.

### Solução

Um **segundo modo** sobre os mesmos `Trecho`: `nivel`, `caminho` e `papel` é tudo de que uma árvore
precisa, e `estudo_lista` já os entrega. A linha principal é a raiz; cada variante é um nó
dobrável; o lance corrente está sempre visível, com os ancestrais dele abertos.

**Modo, e não substituição.** A lista corrida é a que se lê como a linha impressa se lê — com
comentário no meio e variante entre parênteses —, e é a forma do livro que esta aba serve. Trocá-la
por uma árvore resolveria o recuo por outro caminho e perderia isso. A escolha do modo é da pessoa,
sobrevive à sessão pelo `AppState`, e o padrão é a lista.

O clique num nó da árvore vai ao mesmo lugar que o clique num trecho: o caminho é resolvido **na
hora**, e não guardado na montagem — a armadilha que a S-268 documenta e que promover ou apagar
variante ativa.

### Critério de aceite

- Dobrar uma subvariante não muda a árvore nem o PGN: é vista. `Ctrl+Z` não a enxerga, e `edicao`
  não sobe. ✅
- O lance corrente está sempre visível: navegar para dentro de uma subvariante dobrada a abre. ✅
  E a dobra **continua declarada**: sair dali com a seta a devolve, sem pedir de novo.
- ~~O modo escolhido volta igual depois de fechar e reabrir a janela.~~ **Retirado: não há modo.**
- A lista corrida continua sendo o padrão, e continua sendo o que a S-514 e a S-515 consertaram. ✅

> **Este item não virou um segundo widget, e a spec estava errada ao supor que viraria.**
>
> Ao desenhar o `QTreeView` o custo apareceu: **uma linha por lance** faz de um estudo de 40 lances
> uma coluna de 40 linhas onde a lista corrida usa **três** — e notação se lê como corrida de
> tokens, não como coluna. Foi por isso que a própria spec escreveu, no problema, que o que falta é
> *"não há como esconder o que não interessa agora"* — e esconder não pede outra forma de mostrar.
>
> O dobrar entrou na lista que já existe: o `(` de cada variante responde ao clique, o miolo some,
> e fica `( … )`. Zero widget novo, e as S-514 e S-515 continuam valendo dentro do que sobra.
>
> **Daí os dois critérios que mudaram.** Não há modo para o `AppState` guardar — o que existe é um
> conjunto de dobras, estado de vista, que morre com a sessão como a rolagem morre; e o controle é
> o próprio parêntese, não um `▸`, porque aquele glifo sairia de fonte de queda (é o que a S-508
> mediu nos quatro botões de navegação).
>
> **O que a implementação acrescentou foi um comando** — `dobrar_variantes`, alternante,
> `COMANDOS_DA_ABA` de 31 para 32. Um gesto que só se acha clicando num parêntese não se acha: o
> menu e a paleta são o caminho descobrível, e o clique é o atalho de quem já viu. Ele entrou nas
> duas listas que o catálogo cobra — a dos que alternam e a dos rótulos que divergem do menu.
>
> **A identidade de uma dobra é o caminho do primeiro lance dela, e não o índice do `(`.** Índices
> mudam a cada redesenho, e promover ou apagar variante reordena as irmãs: uma dobra guardada por
> índice mudaria de dona no gesto seguinte, que é a armadilha que a S-268 documenta para a
> navegação. Caminho que deixou de existir não casa com nada, e a dobra some — degradação certa
> para estado de vista.

### Testes

- `tests/test_qt_painel_de_estudo.py`: navegar para um nó dobrado o revela; dobrar não muda
  `pgn_payload()` nem `edicao`.
- `tests/test_ui_estudo_lista.py`: inalterado — se ele precisou mudar, o modo novo trouxe decisão
  para dentro do widget, que é o que a regra 4 desta spec proíbe.

---

# Fase 76 — o arranjo

## S-517 · A navegação sai da barra e vai para baixo do tabuleiro — ✅ **implementada em 2026-09-01**

### Problema

`qt/painel_de_estudo.py:210` monta **quatro** barras acima do conteúdo, com 28 botões (31 quando há
motor). Medido nas fotografias: **130 px de 800** a 900 de largura — 16% da altura da aba — e
**155 px de 620** a 760, que é 25%. O `ROADMAP_ACABAMENTO` já tinha contado, e adiou o item por
escrito: *"são problema de arranjo, não de acabamento… merecem um plano próprio, depois destas"*.

O corte que mais custa é **dentro** da segunda barra: ela mistura navegar — `inicio_da_linha`,
`lance_anterior`, `proximo_lance`, `fim_da_linha`, usados dezenas de vezes por minuto — com
cirurgia de árvore — `promover_variante`, `promover_a_principal`, `rebaixar_variante`,
`apagar_variante`, `apagar_continuacao`, dois deles pintados de destrutivo, e um deles apaga
subárvore anotada. Frequência e risco opostos, encostados.

E os quatro de navegação são os **menores alvos do painel**: ~30 px de largura contra ~100 dos
vizinhos, porque o rótulo é um caractere. O caractere vem de outra fonte — `⏮ ◀ ▶ ⏭`
(`ui/strings.py:129-132`) não existem no Segoe UI: perguntado ao Qt, `QFontMetrics.inFont` responde
`False` para os quatro na fonte da interface e `True` no Segoe UI Symbol e no Segoe UI Emoji. O
Windows resolve por queda de fonte, e resolve com um desenho que não é o da janela.

### Solução

Uma faixa própria **sob o tabuleiro**, com os quatro de navegação em tamanho de alvo confortável,
mais duas informações que hoje não têm lugar: o **lance corrente** (`12. Ba4`), que só existe como
fundo amarelo na lista, e a **vez a jogar**, que só existe como sufixo da frase do rodapé.

É o lugar certo por frequência: são o único grupo cujo uso justifica estar ao lado do olho que já
está no tabuleiro. E tirá-los da segunda barra deixa lá uma barra só de árvore — `Apagar variante`
deixa de estar encostado no `▶`, que é o vizinho mais perigoso que ele podia ter.

**A tabela de comandos não muda.** Os quatro continuam sendo as mesmas quatro ações de
`COMANDOS_DA_ABA`, com os mesmos rótulos e as mesmas teclas; o que muda é onde `_montar` os põe. O
ícone vetorial no lugar do glifo é da S-520, e cai nesta faixa.

As quatro barras passam a três: posição, árvore, e livro/entrada-e-saída fundidas — as duas últimas
são as de menor frequência da aba, e juntas ainda cabem em uma fileira na largura de trabalho.

### Critério de aceite

- As barras superiores caem de quatro fileiras para três, e de 130 px para menos de 100 a 900 de
  largura. ✅ **Medido: 78 px**, 10% da altura da aba (era 16%). A 760 de largura, 155 → 136: ali a
  largura é que manda e a `BarraFluida` quebra, então juntar barras devolve menos.
- A faixa sob o tabuleiro tem os quatro comandos de navegação, o lance corrente e a vez. ✅

> **Faltava uma peça, e sem ela a faixa não ficava embaixo do tabuleiro — ficava embaixo da
> coluna.** O widget do tabuleiro levava toda a altura sobrando e o tabuleiro flutuava no meio
> dela, então a faixa aparecia ~100 px abaixo do desenho a que ela pertence. A resposta é o widget
> declarar `heightForWidth` — altura igual à largura, que é o que um tabuleiro **é** —, e a
> política ser ligada só pela sala: a aba Resultado, onde o tabuleiro divide a coluna com a lista
> de casas e a legenda, continua com o arranjo de sempre.
>
> **E o texto do lance sai dos mesmos trechos que a lista desenha**, por `trecho_do_caminho` — que
> era uma das decisões puras sem chamador. Uma segunda formatação daria `12. Ba4` aqui e `12...Ba4`
> ali no dia em que a numeração de variante mudasse.
- `comandos.acoes_fora_do_catalogo(COMANDOS_DA_ABA)` continua vazio, e nenhum comando sai da aba —
  é o critério de aceite da S-280, e vale para todo rearranjo.
- `estilos.conferir_barra` passa em cada fileira: no máximo uma ênfase primária por barra.
- A `BarraFluida` continua sendo quem quebra as fileiras: nada aqui volta a `QHBoxLayout`, que é o
  defeito que a S-151 mediu e que existe igual no Qt.

### Testes

- `tests/test_qt_painel_de_estudo.py`: os quatro comandos de navegação estão na faixa de baixo, e a
  contagem de fileiras superiores caiu; a tabela de comandos é a mesma de antes.
- `tests/test_ui_comandos.py`: inalterado — o catálogo não é tocado.

## S-518 · O teto do tabuleiro, e o `board_zoom` que nunca teve leitor — ✅ **implementada em 2026-09-01**

### Problema

`qt/tabuleiro.py:60` declara `MAX_DO_TABULEIRO = 560`, herança do produto Tk, onde o canvas do
estudo tinha tamanho fixo e o zoom era um deslizador. `TabuleiroEditavel` e `TabuleiroDeJogo`
herdam `geometria()` de `TabuleiroQt`, então o número vale para os dois tabuleiros da janela.

Numa janela grande o tabuleiro para em 560 px e tudo o que sobra vira esteira — é a metade da S-507
que a S-507 não resolve: lá o vazio deixa de ser quase-preto, aqui ele deixa de existir.

`ui/state.py:69` declara `board_zoom: float = 0.85`. Ele é gravado, é lido do disco, e **não tem
leitor**: o commit que religou o estado da janela registrou *"`board_zoom` fica sem uso de
propósito: o tabuleiro do Qt se ajusta ao painel"* — o que era verdade sobre o piso e não sobre o
teto.

### Solução

O teto passa a ser **argumento** e não constante do módulo — a mesma forma de
`PARTIDAS_MAXIMAS_DE_PGN`, que é argumento de `estudos_de_pgn` justamente para que um limite global
não trunque em silêncio quem tem mais que o teto. `MAX_DO_TABULEIRO` continua sendo o padrão, e a
aba Resultado continua usando-o: ali o tabuleiro divide a coluna com a lista de casas e a legenda, e
crescer tira espaço de quem corrige.

A sala pede o seu, ligado a `AppState.board_zoom`, que ganha o leitor que nunca teve: a fração é do
que o painel oferece, com piso em `LADO_MINIMO`. Zero continua sendo "nunca escolhi", e aí o
tabuleiro cresce até o que a coluna dá — que é o comportamento que a foto de 1250×1000 pede.

### Critério de aceite

- A 1250×1000 o tabuleiro da sala passa de 560 px, e a esteira continua abaixo do piso da S-507. ✅
  **Medido: 651 px**, +16%.
- A aba Resultado desenha o tabuleiro **do mesmo tamanho de hoje**: o padrão não mudou. ✅
- `board_zoom` volta igual depois de fechar e reabrir a janela, e `0.0` significa "não guardado". ✅
- O piso continua sendo `LADO_MINIMO`: nenhuma fração deixa o tabuleiro menor que 240 px. ✅

> **A fração padrão é 1,0, e não os 0,85 que o `AppState` trazia.** Aquele número vinha do
> deslizador do Tk, onde o canvas do estudo era de tamanho fixo e a fração era **do canvas**; aqui
> o tabuleiro *é* a coluna, e `BoardGeometry.fit` já desconta a margem das coordenadas antes de
> enquadrar — a folga já está dentro. Medido: 0,85 dava 415 px a 900×800 contra 455.
>
> **E há uma troca que o critério não previa, medida em vez de escondida.** Numa janela **pequena**
> o tabuleiro **encolhe**: 760×620 vai de ~367 para 308 px. Ali a altura é que manda, e a fase
> gastou altura em duas coisas que valem mais que 59 px de tabuleiro — a margem das coordenadas
> (S-508) e a faixa de navegação (S-517). Numa janela grande a conta inverte, e é onde o defeito
> original estava.

### Testes

- `tests/test_qt_tabuleiro.py`: `geometria()` respeita o teto recebido; sem argumento, o teto é o
  de hoje.
- `tests/test_qt_janela.py`: `board_zoom` sobrevive ao fechamento — junto das guardas de estado que
  a S-322 já cobra (gravar **depois** de aplicar, nunca antes).

## S-519 · A coluna direita que usa um quinto do que ocupa — ✅ **implementada em 2026-09-01**

### Problema

`qt/painel_de_estudo.py:352` dá todo o esticamento vertical à caixa "Lances", e `:358` prende o
comentário em quatro linhas fixas. Medido nas fotografias, com um estudo de 14 lances e duas
variantes:

    900×800    caixa "Lances" 534 px de altura, conteúdo até ~165 px    ~370 px vazios (69%)
    1250×1000  caixa "Lances" 724 px de altura, conteúdo até ~135 px    ~590 px vazios (81%)

Ao mesmo tempo a caixa de comentário — que é onde se escreve a frase do livro, e o motivo de a aba
existir — tem quatro linhas, e a seção do motor aparece e some conforme haja binário, sem que a
repartição mude.

### Solução

Um `QSplitter` vertical na coluna direita: lances, comentário e motor. A fração é da pessoa e
sobrevive à sessão pelo caminho que `estudo_divisor` já abriu (S-276) — e é por isso que este item
não pode vir sozinho: um segundo divisor sem persistência é um controle que se ajusta todo dia.

A altura de fábrica reparte por uso e não por igualdade: a lista continua sendo a maior, o
comentário sobe de quatro linhas para algo que caiba um parágrafo do livro, e o motor fica no
tamanho que a sua seção pede. Sem motor, ele não existe — a S-33 já manda esconder a seção inteira
em vez de deixá-la cinza, e o divisor não pode reservar altura para o que não está lá.

`AppState` ganha um campo, na forma que `estudo_divisor` já tem: `0.0` é "nunca guardado", e não um
padrão disfarçado — a razão está escrita em `sash_fraction` e vale igual aqui.

### Critério de aceite

- A fração do divisor vertical volta igual depois de fechar e reabrir a janela. ✅
- Sem motor, o divisor tem duas partes e não três, e nenhuma altura fica reservada para a seção
  ausente. ✅
- A caixa de comentário cabe um parágrafo sem rolar, na altura de fábrica. ✅ O `setFixedHeight` de
  quatro linhas virou `setMinimumHeight` de três: com o divisor, quem decide a altura é quem lê, e
  o número de antes era o teto e o piso ao mesmo tempo.
- `estudo_divisor` (o horizontal, da S-276) continua funcionando e continua sendo outro campo. ✅
  `STATE_VERSION` foi de 6 para 7.

> **Com o motor são três partes, e a fração guardada é só a da primeira.** As outras duas repartem
> o que sobra na proporção que já tinham — senão mover a alça de cima esmagaria a seção do motor
> sem ninguém ter pedido.

### Testes

- `tests/test_qt_gravacao.py`: o campo novo sobrevive ao fechamento, e `0.0` continua significando
  "não guardado".
- `tests/test_qt_painel_de_estudo.py`: sem `analyzer`, o divisor tem duas partes.

---

# Fase 77 — o acabamento do botão

## S-520 · O botão neutro sem aparência declarada, e os catorze traços que já existem — ✅ **implementada em 2026-09-01**

### Problema

`qt/tema.py:361` declara, para o botão neutro, **só recheio**:

    f"QPushButton {{ padding: {do_tema('QPushButton')}; }}",

Face, borda, raio, `:hover`, `:pressed` e `:disabled` existem para `PRIMARIO` e `DESTRUTIVO` (a
S-444) e não existem para o neutro. Todo o resto do neutro é o estilo da plataforma — que é
`windowsvista` na máquina de quem usa e `fusion` na CI e nas fotografias. **São dois desenhos
diferentes para o mesmo botão, e nenhum dos dois foi escolhido**; é também o que faz a fotografia
da CI não poder ser comparada com a da máquina.

São 28 botões nesta aba e a maioria da janela.

E há desenho pronto sem cliente: `ui/icones.py` declara catorze traços numa caixa de 100×100, puros,
com `qt/icones.py` fazendo a ponte para `QIcon` e cache por `(nome, tamanho, cor)`. Eles servem à
fita e à fila, e não alcançam painel nenhum.

### Solução

**Duas metades, e a segunda é estreita de propósito.**

A folha ganha a aparência do neutro: face, borda de 1 px na moldura, raio, `:hover`, `:pressed`,
`:checked` e `:disabled`, todos por `cor()`. É um arquivo e um ponto de chamada, e alcança a janela
inteira — a mesma razão pela qual a folha de base veio primeiro na Fase 69.

O ícone **não** vai em todo botão. O `ROADMAP_ACABAMENTO` recusou isso, e a recusa continua de pé:
espalhar catorze traços por 99 sítios é decisão de arranjo sem critério. Vai em dois lugares com
critério escrito:

1. **A faixa de navegação da S-517**, onde o ícone substitui um glifo que vem de fonte de queda —
   é o único sítio da aba em que o desenho de hoje não é o da janela.
2. **Os três que alternam** — `mostrar_diagrama`, `analise_continua`, `modo_treino` —, onde o
   desenho reforça o que o rótulo alternado já diz, e o estado ligado passa a ter dois sinais.

### Critério de aceite

- O botão neutro tem a mesma aparência sob `fusion` e sob o estilo da plataforma — e a fotografia
  da CI passa a poder ser comparada com a da máquina. ✅ Quatro estados (face, `:hover`,
  `:pressed`/`:checked`, `:disabled`), todos derivados de `RELEVO_DO_BOTAO` — um número, como
  `REALCE_DE_ENFASE` na S-444.
- Nenhum glifo de navegação sai de fonte de queda. ✅ Os quatro passaram a desenhar **só** o ícone.
- Ícone que falta desenha botão só com texto, e nada impede a janela de abrir (regra 5 desta spec,
  e regra 4 da `SPEC_APARENCIA`). ✅
- `estilos.conferir_barra` continua valendo em toda fileira: uma ênfase por barra, nunca duas. ✅
- Zero hexadecimal cru na folha; tudo resolve por `cor()`. ✅

> **Os três que alternam ficaram sem ícone, e a razão apareceu ao desenhar.** Nos quatro de
> navegação o rótulo **é** um símbolo que a fonte da interface não tem, então o ícone corrige um
> defeito. Nos três que alternam o rótulo é palavra e já troca de texto com o estado: ali o ícone
> seria decoração, e custaria três desenhos novos — que é exatamente o que o `ROADMAP_ACABAMENTO`
> recusou ao dizer não a "ícone em todo botão".
>
> **Nos quatro, o ícone substitui o rótulo em vez de acompanhá-lo**: manter os dois desenharia a
> mesma seta duas vezes, uma da fonte de queda e outra do traço vetorial. O rótulo longo e a tecla
> continuam na dica.
>
> **E o botão passou a carregar a ação que serve**, numa propriedade do Qt. Não é adorno: com o
> rótulo vazio, um teste que perguntasse pelo texto deixaria de achar os quatro — seria a guarda
> medindo o desenho em vez do arranjo.

### Testes

- `tests/test_qt_tema.py`: a folha declara os sete estados do neutro, nas três peles, e nenhum
  hexadecimal cru.
- `tests/test_qt_painel_de_estudo.py`: os botões da faixa de navegação têm ícone e continuam tendo
  o rótulo do catálogo.
- Varredura: nenhum literal de glifo em `qt/` que a fonte da interface não tenha — a mesma pergunta
  que achou o defeito.
