# Roadmap da sala de estudo no Qt — Fases 73 a 77

A sala de estudo é a aba em que se **usa** o programa depois que o OCR terminou: um estudo por
diagrama, com árvore de variantes, anotação, motor e o livro ao lado. As decisões que a fazem ser
isso já foram tomadas e estão certas — [ROADMAP_ESTUDO.md](ROADMAP_ESTUDO.md) e
[SPEC_ESTUDO.md](SPEC_ESTUDO.md), Fases 43 a 50, S-268 a S-290. **Este plano não reabre nenhuma
delas.**

O que ele trata são duas coisas, e a medição separa as duas com clareza:

1. **O que o porte para o Qt e o corte do Tk (S-500 a S-506) deixaram para trás.** Seis das oito
   coisas abaixo não são recurso que falta: são decisão que existia, foi medida, foi argumentada e
   **perdeu o chamador** quando o toolkit trocou. Uma delas — a esteira do tabuleiro — foi
   implementada em 30/08 e desfeita em 31/08, sem que nada acusasse.
2. **O arranjo, que o acabamento recusou de propósito.** O `ROADMAP_ACABAMENTO` mediu as quatro
   fileiras de botão desta aba e escreveu, na lista do que não faria: *"são problema de arranjo, não
   de acabamento… merecem um plano próprio, depois destas"*. Este é o plano próprio.

A spec item a item vai em `docs/SPEC_ESTUDO_QT.md`, que nasce com a Fase 73. Para a fundação que
este plano usa — tokens, tipografia, papéis de botão, catálogo de comandos —
[SPEC_UI.md](SPEC_UI.md) e [SPEC_APARENCIA.md](SPEC_APARENCIA.md); para o *como* de hoje,
[ARCHITECTURE.md](ARCHITECTURE.md). Nenhuma fase daqui toca modelo, detecção ou texto.

**Data da medição:** 2026-09-01 · **Ramo:** `religa-as-decisoes-orfas` · **HEAD:** `81d6e5e`
· **Método:** o `PainelDeEstudo` foi montado sob `QT_QPA_PLATFORM=offscreen` com o tema aplicado e
um estudo real carregado (espanhola fechada, 14 lances, duas variantes aninhadas), fotografado com
`grab()` em 760×620, 900×800 e 1250×1000. Cada número deste documento é uma amostra de pixel dessas
fotografias, uma contagem sobre a árvore, uma medição de `perf_counter`, ou uma pergunta feita ao
próprio Qt num processo à parte. O comando que produziu cada um vai no item correspondente da spec.

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

---

# O que foi medido, e o que a medição decide

A pergunta que abriu este plano foi *"a aba Estudo é muito importante para estudar o livro; o que
pode melhorar ali?"*. Isso não é especificação, e a tentação é responder com gosto. A resposta aqui
é a mesma do acabamento: a contagem — porque o gosto não distingue **"falta desenho"** de **"o
desenho existe e foi desligado"**, e as duas doenças têm remédios opostos.

A contagem diz que, das oito, **cinco são a segunda**.

| achado | é falta ou é desligamento? | vira |
|---|---|---|
| a esteira do tabuleiro sem fim | **desligamento** — S-449 implementada em 30/08, não portada em 31/08 | S-507 |
| sem coordenadas a–h / 1–8 | **desligamento** — `margem_de_coordenada` sem chamador | S-508 |
| sem marca do último lance | **desligamento** — `BoardModel.last_move` sem quem o escreva | S-509 |
| alvo, seta e círculo com números próprios | **desligamento** — três constantes puras ignoradas | S-510 |
| "Seguir OCR selecionado" inerte | **desligamento** — `sync_with_ocr` sem chamador | S-512 |
| clique no diagrama não chega à sala | falta | S-513 |
| variantes sem recuo, notação quebrando no meio do lance | falta (mecanismo do Qt) | S-514, S-515 |
| 28 botões em quatro fileiras, navegação na fileira errada | falta (arranjo adiado) | S-517 |

**O padrão dos cinco é o mesmo, e a memória do projeto já o nomeia**: a conta do catálogo pergunta
se a ação tem **dono** e se o dono é **chamável**; nada pergunta se uma decisão pura de `ui/` ainda
tem quem a chame. Foi assim que sete decisões ficaram órfãs no corte e voltaram um mês depois
(`adda88f`). Estas são a oitava em diante, e todas moram no mesmo arquivo:
`ui/desenho_do_tabuleiro.py`.

## Os oito achados, e um nono

**1 · A esteira voltou a não ter fim, e o item que a consertou tem um dia de vida.** A Fase 72
(`462820e`, 30/08) mediu o slab quase-preto em volta do tabuleiro, deu **tamanho** à esteira —
tabuleiro mais a margem que a coordenada já reservava — e criou `VAZIO_DE_CANVAS` para o que sobra.
*62% → 4%*, medido na linha `y=340` da fotografia da pele clássica.

Aquele commit tocou `ui/board_render.py` e `ui/board_widget.py`. **Só o Tk.** `qt/tabuleiro.py`
entrou na árvore no dia seguinte, dentro do próprio commit do corte (`653f88b`), com
`fillRect(self.rect(), SUPERFICIE_TABULEIRO)`: a esteira voltou a ser o fundo do widget inteiro.
Medido nas três fotografias, sobre o retângulo do próprio widget do tabuleiro:

| fotografia | widget do tabuleiro | esteira | na linha do meio |
|---|---|---|---|
| 760×620 | 411×376 | 12,4% da área | 10,5% |
| 900×800 | 489×582 | 18,7% da área | 1,6% |
| 1250×1000 | 685×782 | **41,5% da área** | 18,2% |

A fração **cresce com a janela**, e é isso que a torna pior que o defeito original: o tabuleiro para
em 560 px (ver o achado 6) e tudo o que a janela ganha vira quase-preto. Numa tela grande, a maior
região de cor única da aba é espaço vazio.

E ninguém acusa: `tests/test_ui_superficies.py` — a guarda que a S-449 reforçou — **não existe mais
na árvore**. É o padrão registrado no próprio corte: guarda de varredura que fica verde por passar
sobre lista vazia. `VAZIO_DE_CANVAS` continua vivo e é usado por `qt/visor.py:113`; pelo tabuleiro,
não.

**2 · O tabuleiro do Qt não desenha coordenadas, e o cabeçalho diz isso por escrito.**
`qt/tabuleiro.py:68` declara `MARGEM = 8` com o comentário *"é o mesmo `margin` que `board_widget`
passa quando não desenha coordenadas — e este tabuleiro não desenha"*. Quem estuda livro lê
`14.Ng3` na página impressa e procura g3 contando casas no tabuleiro. Do lado puro, a decisão está
inteira e sem cliente: `margem_de_coordenada`, `COORD_FONT`, `COORD_OFFSET_PX` e `COORDINATE_TEXT`
têm **zero** chamadores em `src/` e `tests/`.

**3 · O último lance não é marcado, e o modelo já sabe qual é.** `ui/board_model.py` declara
`last_move` e `last_move_squares()` — puro, testado, e **nunca recebe valor**: `push_move` não o
escreve e `mostrar_tabuleiro` faz `tabuleiro.copy(stack=False)`, que descarta a pilha de onde ele
sairia sozinho. O papel de cor `LAST_MOVE_SQUARE` existe em `ui/desenho_do_tabuleiro.py` e tem zero
chamadores. Navegar pela árvore com `←`/`→` não diz qual lance acabou de acontecer — que é
exatamente o gesto que a aba existe para servir.

**4 · Três decisões de desenho foram reescritas dentro do widget.** `_desenhar_alvos` pinta o ponto
de "pode ir aqui" com `tokens.CONTORNO_DE_SELECAO`, e não com `tokens.ALVO`, que é o papel que
`TARGET_MARK` nomeia; a seta usa `geo.cell * 0.14` para a haste e `* 0.34` para a ponta, com
`LARGURA_DA_SETA = 0.16` declarada ao lado e ignorada; `LARGURA_DO_CIRCULO` não tem cliente porque
a casa marcada (`[%csl]`) não é desenhada. São números cravados num widget, que é o defeito que o
corte do Tk já pegou uma vez em `qt/tabuleiro.py` — *"2 hexadecimais cravados"*, na lista do que as
guardas traduzidas acharam na hora. O mecanismo é o mesmo; o que mudou foi o tipo do literal.

**5 · "Seguir OCR selecionado" está desligado desde o porte.** A caixa nasce marcada
(`painel_de_estudo.py:224`) e **nada chama `sync_with_ocr`**: os únicos chamadores em `src/` são o
próprio `on_follow_ocr_toggle` e um teste. No Tk, `result_panel.py` chamava `on_sync_study` em três
pontos — selecionar diagrama, aplicar posição e editar casa — e `app_tkinter.py:1537` a repassava
ao painel. A janela do Qt liga `painel.selecionou` só ao visualizador (`janela.py:862`).

O efeito é que a promessa que a S-270 escreveu — *"trocar de diagrama deixa de ser recomeçar e passa
a ser ir para a outra mesa"* — não acontece sozinha: é preciso apertar "Carregar OCR atual" a cada
diagrama, ou desmarcar e remarcar a caixa.

**6 · O tabuleiro para em 560 px, e o `board_zoom` nunca teve leitor.** `MAX_DO_TABULEIRO = 560` é
herança do produto Tk, onde o canvas do estudo tinha tamanho fixo e o zoom era um deslizador. Aqui
o widget se ajusta ao painel — mas até 560, e daí em diante o que sobra vira esteira (achado 1).
`AppState.board_zoom = 0.85` existe, é gravado, é lido do disco e **não tem leitor**: o commit que
religou o estado da janela registrou *"`board_zoom` fica sem uso de propósito: o tabuleiro do Qt se
ajusta ao painel"* — o que era verdade sobre o piso e não sobre o teto.

**7 · A lista de lances não recua as variantes, e quebra no meio do lance.** Dois defeitos
independentes, os dois do mecanismo do Qt, os dois medidos perguntando ao próprio Qt:

- **O recuo não existe.** `RECUO_POR_NIVEL = 18` vira `margin-left:{recuo}px` num `<span>`. O
  `QTextDocument` **descarta** margem em elemento inline: todos os blocos saem com
  `blockFormat().leftMargin() == 0.0`, e os `<br>` viram separador de linha *dentro do mesmo bloco*
  em vez de blocos novos. A decisão pura está certa, testada, e não pinta um pixel — na fotografia,
  `( 3... Nf6` começa na mesma coluna de `1. e4`.
- **A quebra é em qualquer lugar.** `_trecho_em_html` faz `texto.replace(" ", "&nbsp;")`, o que tira
  **toda** oportunidade de quebra; o `wordWrapMode` de fábrica do `QTextEdit` é
  `WrapAtWordBoundaryOrAnywhere`, e sem fronteira de palavra ele quebra onde couber. Medido num
  documento de 240 px: `'1. Nf3 Nc6 2. Nf3 N'` / `'c6 3. Nf3 Nc6 4. Nf'`. Na fotografia de 760 px
  isso aparece duas vezes — `O-O` sai como `O-` / `O`, e a frase do comentário sai como `guard` /
  `am`. Numa lista de notação, `N` / `c6` não é feio: é ilegível.

**8 · Vinte e oito botões em quatro fileiras, e a navegação está na fileira errada.** Contando:
7 + 10 + 4 + 7 = **28** (31 quando há motor). Eles ocupam **130 px de 800** a 900 de largura (16%
da altura da aba) e **155 px de 620** a 760 (25%), antes de qualquer conteúdo. O
`ROADMAP_ACABAMENTO` já tinha contado — *"a aba Estudo empilha 27 botões de peso idêntico em quatro
fileiras, com o último cortado na borda do painel"* — e adiou o item de propósito.

O corte que mais custa é dentro da segunda fileira: ela mistura **navegar** (4 botões, dezenas de
vezes por minuto) com **cirurgia de árvore** (Promover, Principal, Rebaixar, Apagar variante,
Apagar daqui — dois deles vermelhos, e um apaga trabalho anotado). São gestos de frequência e de
risco opostos encostados um no outro. E os quatro de navegação são os **menores alvos do painel**
(~30 px de largura contra ~100 dos vizinhos), com o glifo vindo de outra fonte: `⏮ ◀ ▶ ⏭` não
existem no Segoe UI — perguntado ao Qt, `QFontMetrics.inFont` responde `False` para os quatro, e
`True` no Segoe UI Symbol e no Segoe UI Emoji. O Windows resolve por queda de fonte, e resolve com
um desenho que não é o da interface.

**E um nono, que é de espaço e não de controle:** a caixa "Lances" leva todo o esticamento vertical
da coluna direita e o conteúdo típico enche o terço de cima. Sobram ~370 px vazios a 900×800 e
~590 px a 1250×1000 (81% da caixa), enquanto a caixa de comentário está presa em `setFixedHeight(4 linhas)`
e o tabuleiro está preso em 560.

## O que a medição **absolveu**, e por isso não vira item

Metade de um plano de melhoria é a lista do que não precisa mudar. Medido nesta bancada, com
`perf_counter` sobre o painel montado:

| o quê | custo |
|---|---|
| pintar o tabuleiro a 240 / 400 / 560 px | 0,30 / 0,60 / 0,55 ms por quadro |
| `refresh()` num estudo real de 66 trechos | **4,0 ms** — é o custo de uma seta do teclado |
| `refresh()` na maior partida do acervo PGN (31 trechos) | 3,2 ms |
| `refresh()` numa árvore de 1.606 trechos | 63 ms, dos quais 49 no `setHtml` |
| `refresh()` numa árvore de 97 mil trechos | 3,3 s |

**Não há gargalo no uso real.** As doze peças de 70×70 são reescaladas a cada `paintEvent` sem
cache quando o conjunto é o padrão, e isso custa meio milissegundo — reescrever aquilo seria
otimizar o que não dói. O único ponto que degrada é `_redesenhar_lista`, que reconstrói o HTML
inteiro a cada `refresh`, e ele só aparece acima de ~1.500 trechos: nenhum livro do acervo produz
isso, mas um PGN de base anotado produz, e o comando "Abrir PGN…" aceita 20 MB. **Fica registrado e
não vira item**: se um dia doer, o conserto é redesenhar só a marca do lance corrente em vez do
documento todo, e a S-514 já mexe nesse método.

Três decisões que estão **certas** e que este plano não deve "melhorar" de passagem, porque cada uma
tem um defeito medido atrás dela:

- o recorte do diagrama só é reamostrado quando a **âncora** muda, e não a cada lance (S-282);
- a geração descarta a resposta atrasada do motor, e ela cresce em `refresh`, que é o único ponto
  por onde toda mudança de nó passa (S-285);
- `_agendar_gravacao(adiar=False)` **não** reinicia o relógio, e é o que impede a escrita do motor
  de adiar a gravação para sempre (S-345).

---

# As cinco fases

| fase | itens | o que ela entrega |
|---|---|---|
| **73** — o tabuleiro que o corte deixou para trás | S-507 a S-511 | esteira com fim, coordenadas, último lance, os números do desenho de volta ao módulo puro, e a conta que acha o próximo órfão |
| **74** — os dois fios cortados | S-512 e S-513 | a sala volta a seguir o diagrama selecionado, e o clique na página chega a ela |
| **75** — a lista que se lê | S-514 a S-516 | recuo de variante que aparece, notação que não quebra no meio do lance, e a árvore que dobra |
| **76** — o arranjo | S-517 a S-519 | navegação sob o tabuleiro, tabuleiro que cresce com a janela, e a coluna direita repartida |
| **77** — o acabamento do botão | S-520 | aparência declarada para o botão neutro, e os catorze traços que já existem nos que valem |

A ordem é a de **maior efeito por linha escrita**, e não a da lista de achados. A Fase 73 mexe num
arquivo só, chama decisões puras que já estão escritas e testadas, e é a que muda mais pixel; a 74
são duas ligações de sinal e uma guarda; a 75 e a 76 são as que pedem julgamento; a 77 alcança a
janela inteira e por isso vai por último, quando o arranjo já estiver decidido.

## Fase 73 — o tabuleiro que o corte deixou para trás — ✅ **completa em 2026-09-01**

Vem primeiro pela mesma razão que a folha de base veio primeiro no acabamento: é a única fase em que
**nada precisa ser decidido de novo**. As quatro decisões já existem em `ui/desenho_do_tabuleiro.py`
e em `ui/board_model.py`, já foram medidas, já têm teste — o que falta é o chamador. E é a fase de
maior razão entre pixel mudado e linha escrita: quatro itens dentro de `qt/tabuleiro.py` e
`qt/tabuleiro_de_jogo.py`.

- **S-507** · A esteira que voltou a não ter fim, e a guarda que morreu com ela — ✅ **implementada em 2026-09-01**
- **S-508** · As coordenadas a–h e 1–8, que o tabuleiro do Qt nunca desenhou — ✅ **implementada em 2026-09-01**
- **S-509** · O último lance, que o modelo sabe e ninguém pinta — ✅ **implementada em 2026-09-01**
- **S-510** · Os três números do desenho que o widget reescreveu — ✅ **implementada em 2026-09-01**
- **S-511** · A conta que faltava: de cada decisão pura de `ui/`, quem a chama? — ✅ **implementada em 2026-09-01**

> **Onde a fase está, e as três coisas que a implementação achou.**
>
> **A esteira: 41,5% → 7,2%** da área do widget, medido na mesma fotografia de 1250×1000. A 900×800,
> 18,7% → 11,1% — e a fração agora **encolhe** quando a janela cresce, que é o invariante que o
> teste cobra, porque é ele que separa este desenho do defeito de origem.
>
> **A S-510 tinha um quarto item, e ele é o mesmo achado da S-501 com outro nome.**
> `qt/tabuleiro_de_jogo.COR_DA_SETA` era uma **cópia byte a byte** de
> `desenho_do_tabuleiro.PAPEL_DE_SETA` — quatro pares mantidos em dois lugares, exatamente como a
> tabela de glifos que a S-501 desduplicou neste mesmo pacote. Passou a ser apelido. E um quinto,
> fora da spec: a tinta do glifo de reserva saía de `RESERVA[...]` — o hexadecimal de fábrica, que
> **não acompanha a troca de pele**. Passou a sair de `tema.cor_atual`.
>
> **A conta da S-511 tinha um número errado, e o instrumento era o culpado.** Este roadmap e a spec
> citam 125 nomes sem chamador, medidos por busca de texto sobre `src/` — e ali um nome citado num
> **docstring** conta como uso. Neste projeto os módulos se descrevem uns aos outros em prosa o
> tempo todo, então a busca de texto **subestima**. Pela varredura de identificador, que é a que a
> guarda usa, eram **153**; `margem_de_coordenada` é o exemplo, citada num docstring de
> `ui/tokens.py` e contada como chamada. Depois da fase são **136**, e
> `ui/desenho_do_tabuleiro.py` contribui com **um** — `LARGURA_DO_CIRCULO`, isento por escrito.
>
> **E a triagem tem quatro saídas, e não três.** A spec listava *dar chamador*, *apagar* e *isentar
> com motivo*. Faltava a quarta, que é a que `HEATMAP_LOW` e `HEATMAP_HIGH` pediam: **tirar do
> `__all__`**. Elas são usadas por `heatmap_color`, dentro do próprio módulo — não são API, e
> exportá-las era a declaração errada, não a falta de um cliente.
>
> **A catraca chegou a zero em 2026-09-02.** As 134 perguntas foram respondidas em dois lotes
> (branch `triagem-dos-orfaos`): 74 nomes saíram do `__all__`, 36 ficaram isentos com motivo,
> 16 foram apagados e 8 ganharam chamador — e três guardas mortas no corte voltaram. **Onze
> achados eram decisão desligada no porte**, da cor da caixa que não seguia a pele às teclas do editor de texto, que o Qt nunca
> ligou (`Ctrl+B` não fazia nada). A conta está na S-511 da spec. E a triagem achou o que não é
> órfão: a digitação no editor de texto do Qt não chega ao documento — item para a próxima fase.

**As duas decisões que a fase precisa tomar.** A primeira é *onde a esteira acaba*: a resposta é a
mesma da S-449 — tabuleiro mais `margem_de_coordenada()`, lida da **mesma** função, para as duas não
divergirem —, e ela cai de graça junto com a S-508, que é o que faz aquela margem voltar a ter
motivo. A segunda é *quando o último lance existe*: `mostrar_tabuleiro` recebe o `chess.Board` do
estudo, e o lance que chegou até ele é `estudo.no.move` — o painel o tem, o widget não. O sinal
atravessa como argumento, e não como pilha: `copy(stack=False)` continua certo, porque a sala não
quer a partida inteira dentro do modelo, quer a última aresta.

**Critério de aceite.** (a) Na fotografia de 1250×1000, a esteira cai de 41,5% da área do widget
para menos de 10%, e o resto é `VAZIO_DE_CANVAS`; o critério de contraste é o da S-449 e não um
novo — **pelo menos um** dos três (esteira, moldura, casa clara) passa o piso contra o vazio em toda
paleta. (b) As oito letras e os oito números aparecem inteiros, e a margem que os cabe sai de
`margem_de_coordenada()`. (c) Andar um lance pinta duas casas, e voltar ao nó raiz não pinta
nenhuma. (d) `ui/desenho_do_tabuleiro.py` deixa de ter declaração sem chamador — e é a S-511 que
mede isso, para o dia em que a próxima aparecer.

## Fase 74 — os dois fios cortados — ✅ **completa em 2026-09-01**

Duas ligações de sinal, uma decisão pura e uma armadilha. É a fase mais barata do plano e a que mais
muda o **gesto** de quem estuda: é ela que faz "clicar no diagrama do livro e ele estar no
tabuleiro" acontecer sem passar pela aba Resultado.

- **S-512** · "Seguir OCR selecionado" volta a seguir, e só reabre quando a âncora muda — ✅ **implementada em 2026-09-01**
- **S-513** · O clique no diagrama da página chega à sala — ✅ **implementada em 2026-09-01**

> **Onde a fase está, e por que ela virou uma ligação em vez de duas.**
>
> **A S-513 não custou nada além da S-512.** `decide_box_click` não mudou, o `SELECT` continua
> selecionando o diagrama na aba Resultado, e é a **seleção** que chega à sala — pelo mesmo fio.
> Era o que a spec previa ao recusar o gesto novo, e a implementação confirmou: não havia
> comportamento a acrescentar, havia um sinal sem ouvinte.
>
> **E os três pontos do Tk viraram um.** Lá o `result_panel` chamava `on_sync_study` em três
> lugares — trocar de diagrama, aplicar posição, editar casa. Aqui os três se encontram em
> `_atualizar_tudo`, que existe exatamente por isso, e o painel passou a emitir `posicao_mudou`
> dali. Um sinal com um significado, em vez de três chamadas que alguém precisa lembrar de
> acrescentar na quarta origem.
>
> **A armadilha era real, e a guarda tem teste próprio.** Ligado cru, o fio zeraria a pilha de
> desfazer da sala a **cada casa corrigida** — `posicao_mudou` dispara por edição, e `_abrir`
> chama `_historico.zerar()`. `decidir_sincronia` responde `NADA` ali, e
> `test_corrigir_uma_casa_do_diagrama_aberto_nao_zera_o_desfazer` é quem o afirma.
>
> **A quarta resposta apareceu na implementação: âncora inválida também é `NADA`.** Item de fila e
> amostra do dataset não têm par no livro, então a âncora não identifica mesa — e seguir uma delas
> recomeçaria o estudo avulso em curso a cada atualização. O caminho para estudá-las continua
> sendo "Carregar OCR atual", que é explícito e não passa por `decidir_sincronia`.

**A armadilha, e é o item da S-512.** `_abrir` chama `_historico.zerar()` sem condição. Ligar
`painel.selecionou` cru a ele devolveria o fio e criaria outro defeito: cada edição de casa na aba
Resultado zeraria a pilha de desfazer do estudo aberto. A decisão é uma comparação de chave —
*reabrir só quando `posicao.ancora.chave()` difere da âncora do estudo aberto* — e ela é pura, mora
em `ui/sala_declarada.py` ao lado de `posicao_de_estudo`, e é afirmável sem janela. O caso em que as
chaves são iguais **não** é "não faça nada": é "atualize a posição de partida se o estudo ainda
estiver vazio", porque corrigir uma casa antes de jogar o primeiro lance tem de chegar ao tabuleiro.

**A decisão da S-513 é qual gesto.** `decide_box_click` hoje devolve `SELECT | RECOGNIZE`, e é pura.
Duas saídas foram consideradas; a escolhida é a segunda, e o porquê está em "considerado e
recusado": o `SELECT` continua significando o que significa hoje — selecionar o diagrama na aba
Resultado — e passa a **avisar a sala também**. Com a S-512 no lugar, o gesto que o dono descreveu
já funciona sem gesto novo, sem modificador para aprender e sem uma terceira resposta ao mesmo
clique.

**Critério de aceite.** (a) Selecionar outro diagrama com a caixa marcada troca a mesa, e o
`contagem_de_lances()` do estudo anterior é anunciado no rodapé como a S-270 promete. (b) Editar uma
casa do diagrama **já aberto** não zera a pilha de desfazer da sala — afirmado por `edicao`, que é o
contador que `ui/desfazivel.py` lê. (c) Clicar num retângulo da página lido leva o diagrama ao
tabuleiro de estudo sem que ninguém aperte "Carregar OCR atual".

## Fase 75 — a lista que se lê — ✅ **completa em 2026-09-01**

Os dois primeiros itens são conserto de mecanismo e não mudam decisão nenhuma: `ui/estudo_lista.py`
não é tocado, e a trava que o mantém honesto — `texto_de(trechos(e))` igual, token a token, ao que o
`StringExporter` produz — continua valendo palavra por palavra. O terceiro é recurso, e é o único
desta fase que pede desenho novo.

- **S-514** · O recuo de variante que o Qt descarta — ✅ **implementada em 2026-09-01**
- **S-515** · A notação que quebra no meio do lance — ✅ **implementada em 2026-09-01**
- **S-516** · A árvore que dobra — ✅ **implementada em 2026-09-01**

> **Onde a fase está, e a decisão de arranjo que a S-516 tomou por escrito.**
>
> **O recuo e a quebra saíram como planejados**, e os dois no mesmo método: cada corrida de
> mesmo nível virou um `<div>` — que é o único elemento a que o `QTextDocument` aplica
> `margin-left` — e o `&nbsp;` passou a valer só para `NUMERO` e `ABRE`, os dois que
> **pertencem** ao que vem depois. Todo o resto voltou a ter fronteira de palavra.
>
> **A S-516 não virou um `QTreeWidget`, e a razão é de medida.** A spec falava de um segundo
> modo com uma árvore ao lado da lista. Ao desenhá-la, o custo apareceu: uma linha por lance
> faz de um estudo de 40 lances uma coluna de 40 linhas onde hoje há **três** — e notação se
> lê como corrida de tokens, não como coluna. O que faltava não era outra forma de mostrar a
> árvore; era **poder esconder** o que não interessa agora, que é o que o próprio item diz no
> problema.
>
> Então o dobrar entrou **na lista que já existe**: o `(` de cada variante responde ao clique,
> o miolo some, e fica `( … )`. Zero widget novo, e as S-514 e S-515 continuam valendo dentro
> do que sobra na tela.
>
> **Três consequências dessa escolha.** Não há "modo" para o `AppState` guardar — o que
> existe é um conjunto de dobras, que é estado de vista e morre com a sessão, como a rolagem.
> O controle é o próprio parêntese, e não um `▸`: aquele glifo sairia de fonte de queda, que
> é exatamente o que a S-508 mediu nos quatro botões de navegação. E **um comando novo entrou
> no catálogo** (`dobrar_variantes`), porque um gesto que só se acha clicando num parêntese
> não se acha: o menu e a paleta são o caminho descobrível, e o clique é o atalho de quem já
> viu.
>
> **A dobra que contém o lance corrente não é aplicada** — e continua declarada, então sair
> dali com a seta a devolve. Sem isso, navegar para dentro de uma variante dobrada deixaria o
> tabuleiro mostrando uma posição que a lista não tem.

**S-514 é trocar o elemento, não o número.** `RECUO_POR_NIVEL` continua sendo 18 e continua morando
em `ui/sala_declarada.py`; o que muda é que cada bloco de variante passa a ser emitido como elemento
**de bloco**, que é o único a que o `QTextDocument` aplica `margin-left`. O `<br>` antes do `(` e
depois do `)` sai junto: ele existia para produzir a quebra que o bloco passa a dar sozinho.

**S-515 é devolver a oportunidade de quebra.** O `&nbsp;` foi posto para o espaço entre `12.` e
`Ba4` não sumir na renderização, e o remédio virou pior que a doença: sem nenhuma fronteira de
palavra na linha, o Qt quebra em qualquer caractere. A separação certa é a que a lista já faz entre
o que se lê e o que se grava — o espaço **dentro** de um trecho (`12. `) não pode quebrar, o espaço
**entre** trechos pode. Quem sabe onde um trecho acaba é o `Trecho`, e ele já está na mão.

**S-516 é o item de recurso da fase, e ele tem um gatilho.** A lista corrida serve bem um estudo de
livro — 66 trechos na fotografia, e é o tamanho típico. Ela deixa de servir quando o estudo passa de
umas três dezenas de lances com subvariantes, que é o que acontece ao abrir uma partida anotada pelo
"Abrir PGN…". A rota é um segundo modo sobre **os mesmos `Trecho`** — `nivel`, `caminho` e `papel` é
tudo de que uma árvore precisa —, com a linha principal como raiz e subvariante dobrável. Modo, e
não substituição: a lista corrida é a que se lê como texto, e é a que casa com a página impressa.

**Critério de aceite.** (a) Uma variante de nível 2 é desenhada 36 px à direita da linha principal,
medido em pixel sobre o documento. (b) Nenhum token de SAN é partido em duas linhas em nenhuma
largura entre 240 e 900 px — afirmado sobre o `QTextLayout`, e não a olho. (c) O `texto_de` continua
igual ao `StringExporter`, que é a trava que já existe. (d) Dobrar uma subvariante não muda a
árvore nem o PGN: é vista, e o `Ctrl+Z` não a enxerga.

## Fase 76 — o arranjo — ✅ **completa em 2026-09-01**

É a fase que o `ROADMAP_ACABAMENTO` adiou, e ela vem depois da 73 pela razão que aquele documento
escreveu ao adiá-la: *"depois que a folga e o peso existirem para desenhá-lo"*. Agora existem, e a
73 devolve o tabuleiro à forma em que faz sentido desenhar em volta dele.

- **S-517** · A navegação sai da barra e vai para baixo do tabuleiro — ✅ **implementada em 2026-09-01**
- **S-518** · O teto do tabuleiro, e o `board_zoom` que nunca teve leitor — ✅ **implementada em 2026-09-01**
- **S-519** · A coluna direita que usa um quinto do que ocupa — ✅ **implementada em 2026-09-01**

> **Onde a fase está, e a compra que ela fez de propósito.**
>
> **O topo caiu de 130 px para 78** a 900 de largura — de 16% da altura da aba para 10% — e de
> 155 para 136 a 760. A 760 continuam cinco fileiras porque ali a largura é que manda, e a
> `BarraFluida` quebra: juntar duas barras só devolve altura quando há largura sobrando.
>
> **O tabuleiro precisou de uma terceira peça, e ela não estava na spec.** Tirar o teto não bastou:
> a faixa de navegação aparecia ~100 px **abaixo** do tabuleiro, porque o widget ficava com toda a
> altura sobrando da coluna e o tabuleiro flutuava no meio dela. A resposta é o widget declarar
> `heightForWidth` — altura igual à largura, que é o que um tabuleiro é —, e a política é ligada
> **só** pela sala: a aba Resultado continua com o arranjo de sempre.
>
> **E daí saiu uma troca medida, que vale escrever em vez de esconder.** A 1250×1000 o tabuleiro
> foi de **560 para 651 px**. A 900×800 foi de 489 para 455, e a 760×620 de ~367 para 308 — porque
> numa janela pequena a altura é que manda, e a fase gastou altura em duas coisas: a margem das
> coordenadas (S-508, +26 px) e a própria faixa de navegação (+33). É a compra que o item fez: numa
> janela grande o tabuleiro cresce 16%, numa pequena ele encolhe para pagar coordenada e navegação.
>
> **A fração padrão virou 1,0, e não 0,85.** `AppState.board_zoom` trazia 0,85 do deslizador do Tk,
> onde o canvas do estudo era de tamanho fixo e a fração era **do canvas**. Aqui o tabuleiro *é* a
> coluna, e `BoardGeometry.fit` já desconta a margem das coordenadas antes de enquadrar — então
> "a coluna inteira" já vem com a folga dentro. Medido: 0,85 dava 415 px a 900×800 contra 455.

**S-517 é um corte, e não uma mudança de gosto.** Os quatro botões de navegação são o único grupo
cuja frequência justifica estar ao lado do olho que já está no tabuleiro; tirá-los da segunda
fileira deixa lá uma fileira só de árvore, e `Apagar variante` deixa de estar encostado no `▶`. A
faixa nova sob o tabuleiro leva os quatro, o rótulo do lance corrente — que hoje só existe como
fundo amarelo na lista — e a vez a jogar, que hoje só existe como sufixo da frase do rodapé. **A
tabela de comandos não muda**: os quatro continuam sendo `inicio_da_linha`, `lance_anterior`,
`proximo_lance` e `fim_da_linha`, e continuam vindo de `COMANDOS_DA_ABA`. O que muda é onde a
montagem os põe.

**S-518 tem uma pergunta e uma resposta fácil.** A pergunta é se o teto sai ou vira preferência. Sai
não pode: `MAX_DO_TABULEIRO` é compartilhado com a aba Resultado, onde o tabuleiro divide a coluna
com a lista de casas e a legenda, e crescer ali tira espaço de quem corrige. A resposta é o teto
passar a ser **argumento** e não constante do módulo — como `PARTIDAS_MAXIMAS_DE_PGN` já é —, com a
sala pedindo o seu, e `AppState.board_zoom` ganhando o leitor que nunca teve.

**S-519 é repartir altura.** "Lances" leva todo o esticamento e usa um quinto dele; o comentário tem
quatro linhas fixas e é onde se escreve a frase do livro; a seção do motor aparece e some conforme
haja binário. A repartição é decisão de arranjo e mora num `QSplitter` vertical, cuja fração
sobrevive à sessão pelo caminho que `estudo_divisor` já abriu (S-276) — e é por isso que este item
vem junto e não sozinho: um segundo divisor sem persistência seria um controle que a pessoa ajusta
todo dia.

**Critério de aceite.** (a) A soma das barras superiores cai de quatro fileiras para três, e de
130 px para menos de 100 a 900 de largura. (b) A 1250×1000 o tabuleiro passa de 560 px, e a esteira
continua abaixo do piso da S-507. (c) A fração do divisor vertical volta igual depois de fechar e
reabrir a janela. (d) Nenhum comando sai do catálogo, e `comandos.acoes_fora_do_catalogo` continua
vazio — que é o critério de aceite da S-280 e vale para todo rearranjo.

## Fase 77 — o acabamento do botão — ✅ **completa em 2026-09-01**

Vem por último porque alcança a **janela inteira** de uma vez e porque só faz sentido depois que o
arranjo estiver parado: pintar bem uma fileira que vai mudar de conteúdo é trabalho feito duas
vezes. É a mesma ordem da Fase 69, e pelo mesmo argumento — uma folha de estilo é um arquivo e um
ponto de chamada.

- **S-520** · O botão neutro sem aparência declarada, e os catorze traços que já existem — ✅ **implementada em 2026-09-01**

> **Onde a fase está, e por que os ícones foram para menos botões do que o plano dizia.**
>
> **O botão neutro ganhou os quatro estados**, e todos derivados de um número só: `RELEVO_DO_BOTAO`
> mistura 6% do texto no painel para a face, o dobro para `:hover` e o quádruplo para `:pressed` e
> `:checked`. É o mecanismo que a S-444 já usava para o primário e o destrutivo, aplicado ao caso
> que ela deixou de fora — e agora a fotografia da CI (`fusion`) pode ser comparada com a da
> máquina (`windowsvista`), porque nenhuma das duas escolhe mais sozinha.
>
> **O ícone foi só para os quatro de navegação, e não para os três que alternam.** O plano dizia os
> dois grupos. Ao desenhar, a razão dos quatro se mostrou diferente da dos três: nos quatro o
> rótulo **é** um símbolo que a fonte da interface não tem (`inFont` responde `False` para
> `⏮ ◀ ▶ ⏭` em Segoe UI), então o desenho de hoje já vinha de uma fonte de queda — o ícone corrige
> um defeito. Nos três que alternam o rótulo é palavra, e ele já muda de texto quando o estado
> muda: o ícone seria decoração, e custaria três desenhos novos. Ficaram de fora, e o
> `ROADMAP_ACABAMENTO` já tinha recusado "ícone em todo botão" pelo mesmo argumento.
>
> **Nos quatro, o ícone substitui o rótulo em vez de acompanhá-lo** — manter os dois desenharia a
> mesma seta duas vezes, uma da fonte de queda e outra do traço vetorial. O rótulo longo e a tecla
> continuam na dica, que é onde sempre estiveram.
>
> **Dois ícones novos, e dois reusados.** `inicio_da_linha` e `fim_da_linha` são desenho novo (a
> seta com a barra); `lance_anterior` e `proximo_lance` **apontam para as setas que já existiam** —
> é o mesmo gesto noutra aba, e são o primeiro caso do que o cabeçalho de `ICONES` previa: dois
> comandos na mesma chave. O catálogo de ícones foi de 17 para 19.

**O que está desligado.** `folha_de_estilo` declara aparência para `PRIMARIO` e `DESTRUTIVO` — face,
letra, `:hover`, `:pressed` e `:disabled` — e para o neutro declara **só recheio**. Todo o resto do
neutro é o estilo da plataforma, que é `windowsvista` na máquina de quem usa e `fusion` na CI: dois
desenhos diferentes para o mesmo botão, e nenhum deles escolhido. São 28 botões nesta aba e a
maioria da janela.

**E os ícones.** `ui/icones.py` tem catorze traços declarados numa caixa de 100×100, puros, com
`qt/icones.py` fazendo a ponte para `QIcon` e cache por `(nome, tamanho, cor)`. Eles servem à fita e
à fila e não alcançam painel nenhum. O `ROADMAP_ACABAMENTO` recusou "ícone em todo botão" como
decisão de arranjo — e a recusa continua de pé: **não é todo botão.** É a faixa de navegação da
S-517, onde o ícone substitui um glifo que vem de outra fonte, e são os três que alternam
(Recorte, Análise contínua, Treinar), onde o desenho diz o que o rótulo alternado já diz.

**Critério de aceite.** (a) O botão neutro tem a mesma aparência nas duas plataformas de estilo, e
a fotografia da CI passa a poder ser comparada com a da máquina. (b) Nenhum glifo de navegação sai
de fonte de queda — afirmado por `inFont` sobre a fonte da interface, que é a mesma pergunta que
achou o defeito. (c) `estilos.conferir_barra` continua valendo em toda fileira desta aba: uma
ênfase por barra, nunca duas.

---

# O que foi considerado e recusado

- **Um gesto novo para "estudar este diagrama" (duplo-clique, `Ctrl`+clique).** Foi a primeira
  resposta ao pedido, e ela cria uma terceira coisa que um clique na página pode significar, num
  lugar onde o clique simples e o botão direito já significam duas. Com a S-512 no lugar, o
  `SELECT` que já existe leva ao diagrama certo; o que faltava era a sala escutar. Um gesto novo
  seria pagar aprendizado por um fio que está cortado.
- **A sala escrever de volta no OCR.** O vínculo é de mão única por decisão da S-269, e ela continua
  boa: analisar uma posição não é corrigi-la, e um lance jogado no estudo não é uma correção do
  diagrama. Nada neste plano inverte nenhuma seta.
- **Trocar o `QTextBrowser` por um `QTreeView` como lista única.** Resolveria o recuo por outro
  caminho e perderia o que a lista corrida faz bem: ela se lê como a linha impressa se lê, com
  comentário no meio e variante entre parênteses, que é a forma do livro. A árvore entra como
  **modo** na S-516, ao lado, e não no lugar.
- **Cachear as peças por tamanho no conjunto padrão.** Medido: 0,55 ms por quadro a 560 px. Otimizar
  isso é escrever código para o que não dói, e o cache por tamanho já existe no caminho do traço
  engrossado, que é onde a conta pesava.
- **Redesenhar a lista incrementalmente.** Mesma razão, com número: 4,0 ms num estudo real. O item
  fica registrado no achado da eficiência para o dia em que um PGN de base o torne visível.
- **Mexer em `ui/estudo_lista.py`.** A numeração de variante é a parte que todo visualizador de PGN
  erra, e aquele módulo está travado contra o `StringExporter` desde a S-273. Os dois defeitos da
  lista são de desenho, e o desenho é do lado do Qt.
- **Reabrir a escolha da esteira escura.** A S-147 a escolheu escura porque é ela que dá 11,03:1 às
  coordenadas, e a S-508 devolve as coordenadas — o argumento fica mais forte, não mais fraco. O
  defeito nunca foi a cor: foi a esteira não ter fim.

---

# Custo, risco e ordem

| fase | esforço | risco | o que trava se der errado |
|---|---|---|---|
| 73 | 2 a 3 dias | **baixo** — dois arquivos, quatro decisões já escritas e testadas | o tabuleiro segue no slab, e sem coordenada e sem último lance |
| 74 | 1 a 2 dias | médio — mexe em fiação de janela e na pilha de desfazer | a caixa "Seguir OCR" segue mentindo, e o clique segue parando na aba Resultado |
| 75 | 3 a 4 dias | baixo nos dois primeiros, **médio** na árvore dobrável | a lista segue sem recuo e quebrando lance ao meio |
| 76 | 3 a 4 dias | **médio** — é o único que muda onde as coisas estão | as quatro fileiras seguem comendo um quarto da altura na janela estreita |
| 77 | 1 a 2 dias | médio — alcança a janela inteira de uma vez | o botão neutro segue sendo o que a plataforma quiser |

**Total: 10 a 15 dias.** As fases 74, 75 e 77 são independentes entre si; a 76 depende da 73 (não
adianta decidir o arranjo em volta de um tabuleiro que não cresce), e a 77 depende da 76 (não
adianta pintar a fileira antes de saber o que há nela).

**O risco real deste plano não é técnico, e vale escrever.** Cinco dos catorze itens são decisões
que já existiam e perderam o chamador — e a razão de nenhum ter sido notado em um mês é que **a
suíte não pergunta se uma decisão pura tem quem a chame**. Consertar os cinco sem escrever a S-511 é
consertar a instância e deixar o mecanismo: no próximo corte, ou no próximo porte, a sexta some do
mesmo jeito e pelo mesmo motivo. A S-511 é o item mais barato da lista e o único que impede este
documento de precisar existir de novo.
