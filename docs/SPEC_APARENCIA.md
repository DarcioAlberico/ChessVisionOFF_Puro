# Especificação da aparência — Fases 32 a 35 (S-324 a S-234)

Base: [ROADMAP_APARENCIA.md](ROADMAP_APARENCIA.md), que traz a leitura das duas propostas de
`Proposta de interface/`, os sete achados e o sequenciamento. A fundação visual que esta spec usa
— tokens, tipografia, estilos, barra, menu, atalhos — é a das Fases 20 a 24, em
[SPEC_UI.md](SPEC_UI.md).

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

Cada item tem **Problema** (com arquivo:linha do estado atual), **Solução**, **Critério de
aceite** e **Testes**. Nome de módulo é sugestão; o que importa é a fronteira de responsabilidade.

**Cinco regras valem para toda esta spec.**

1. **A pele clássica é o padrão e não muda.** Quem nunca abrir `Ver ▸ Aparência` tem, pixel a
   pixel, a janela de hoje. Um item que só possa ser feito mexendo na clássica está mal escrito.
2. **Pele é apresentação, nunca conjunto menor de comandos.** Um comando pode mudar de lugar,
   ganhar ícone ou virar item de menu; não pode ficar inalcançável. A S-233 mede isso por
   inventário, e é ela que autoriza a pele "Foco" a esconder 60 controles.
3. **Nenhum item crava cor, fonte ou espaçamento fora dos módulos que os decidem** (`ui/tokens.py`,
   `ui/tipografia.py`, `ui/estilos.py`). É a regra 1 da SPEC_UI, e agora ela tem três clientes em
   vez de um — o que a torna mais necessária, não menos.
4. **O contrato de degradação de `ui/theme.py:12-15` ganha um dono a mais.** Nem tema ausente, nem
   pele desconhecida, nem ícone que não desenhou podem impedir a janela de abrir. S-234.
5. **O que decide mora em função pura; o que monta widget não decide nada.** Catálogo, arranjo,
   geometria de ícone, orçamento de altura e inventário de alcance são todos afirmáveis sem abrir
   janela — e é isso que faz cada critério abaixo caber num `assertEqual`.

---

# Fase 32 — O catálogo, o ícone e a pele

> A fundação. Ao fim dela a janela é a de hoje, sem diferença visível, e `Ver ▸ Aparência` lista
> uma opção. A fundação se prova quando ela não muda nada.

## S-324 · O catálogo de comandos, declarado como dado ✅ implementada (2026-08-24)

**Problema.** Os comandos da janela estavam declarados em **três lugares que não se conheciam**, e
nenhum deles era a lista completa:

| onde | o que declara | quantos |
|---|---|---|
| `ui/menu.py:63-134` | rótulo e posição na barra de menus | 27 |
| `ui/atalhos.py:48-58` | tecla e como ela se escreve | 10 |
| `ui/pdf_panel.py:299-382` | o botão, montado à mão, com o rótulo em literal | 21 |

O nome do comando (`"ler_pagina"`, `"salvar"`) é o que liga os três, e ele já existia — foi a S-161
que o introduziu. O que não existia era o **registro**: nada dizia que `ler_pagina` tem rótulo "Ler
esta página", pertence ao grupo OCR, é a ação primária dessa barra, e se desenha com tal ícone.

**E o defeito era pior que duplicação — era divergência já consumada.** O rótulo do botão estava
em `pdf_panel.py` e o do menu em `menu.py`, e eles **não eram o mesmo texto**: `ler_pagina` se
chamava "Ler esta página" no menu e "OCR todos diagramas" no botão. Medido na implementação, isso
valia para **11 dos 35 comandos**. Nada no programa comparava os dois.

Com uma pele isso é dívida tolerável. Com três, é o defeito que a S-161 nomeou de outro jeito:
*"o que não era botão não existia"* — porque cada pele teria a sua ideia de o que existe.

**Solução.** `ui/comandos.py`: **um registro por comando**, e nada de `tkinter` no módulo.

```python
@dataclass(frozen=True)
class Comando:
    acao: str          # o nome que ata tudo: "ler_pagina". Já é o de menu.py e atalhos.py.
    rotulo: str        # "Ler esta página" -- o de menu.py, agora com um dono só
    grupo: str         # ARQUIVO | OCR | EDICAO | VISUALIZACAO | ACERVO | AJUDA
    papel: str         # estilos.PRIMARIO | DESTRUTIVO | NEUTRO
    icone: str = ""    # nome no catálogo da S-220; "" = comando sem ícone
    destaque: bool = False   # entra na fila curta da pele "Foco" (S-223)
    rotulo_alternado: str = ""   # o texto do botão enquanto ligado, para quem alterna (S-222)
    rotulo_curto: str = ""   # o texto do botão, quando ele difere do rótulo do menu
```

> **`rotulo_alternado` entrou depois, na S-222**, e o motivo é um buraco desta guarda: o
> `selecionar_area` troca o próprio texto por `configure(text="Cancelar seleção")`, e a varredura
> abaixo só olhava o `text=` do **construtor**. Dois literais escritos à mão passavam por limpos.
> A varredura agora olha também o `self.btn_*.configure(text=...)`.

**`rotulo_curto` não estava no desenho, e entrou por causa do achado 1 do roadmap:** *nenhum item
desta fase troca o rótulo de comando nenhum.* Com um campo só, "OCR todos diagramas" viraria "Ler
esta página" na barra — mudança visível na pele clássica, que a regra 1 desta spec proíbe, e ainda
com custo de largura numa `BarraFluida` que quebra por item. Com dois campos numa linha só, o
ganho é o que faltava: os dois textos passam a ser **comparáveis**, e
`test_os_rotulos_que_divergem_do_menu_estao_registrados` congela os 11 casos para que um décimo
segundo não entre em silêncio.

Os seis grupos não são invenção: são os cinco menus de `menu.MENUS` com `Ferramentas` partido em
`OCR` e `ACERVO` — que é a divisão que a Imagem 2 faz e que o menu já insinuava com o separador de
`menu.py:113`. O corte entre os dois virou uma pergunta, e não um gosto: **`OCR` age sobre a página
aberta; `ACERVO` age sobre o livro inteiro ou sobre o modelo que o lê.**

**O catálogo não substitui `menu.MENUS`**, e essa fronteira é o item. O menu decide *onde na barra
de menus*; o catálogo decide *o que o comando é*. `MENUS` passou a referenciar o catálogo em vez de
repetir o rótulo — `Item("ler_pagina")` no lugar de `Item("Ler esta página", "ler_pagina")` — e
`Item.rotulo` virou propriedade derivada, o que manteve os consumidores de pé. `montar` ganhou a
trava no sentido que faltava: **item cujo `acao` não está no catálogo levanta**, como já levantava
o item que ninguém amarrou a uma função.

**Como ficou.** 35 comandos, e a distribuição pelos seis grupos é esta:

| grupo | comandos | primário |
|---|---:|---|
| ARQUIVO | 6 | — |
| EDICAO | 7 | `salvar` |
| VISUALIZACAO | 10 | — |
| OCR | 3 | `ler_melhor` |
| ACERVO | 6 | `anotar_pagina` |
| AJUDA | 3 | — |

Consomem o catálogo: `ui/menu.py` (os 29 itens), `ui/pdf_panel.py` (os 16 botões e interruptores
das duas barras) e `app_tkinter._build_field_row` (os 3 da linha de conjunto de campo). Nenhum
rótulo mudou — o teste compara os 29 do menu com os do registro, e a barra continua com o texto de
antes.

**Três achados, e nenhum deles vira mudança nesta fase.**

1. **O primário do grupo OCR contradiz o critério do próprio `ui/estilos.py`.** Lá está escrito
   que primário é *"a ação que o atalho de teclado também faz"*, e `Ctrl+R` é `ler_pagina` — mas o
   botão em ênfase é `ler_melhor` ("OCR melhor diagrama"). O catálogo registra a janela como ela
   é: trocar a ênfase é mudar a pele clássica. Fica para a S-223, que é quem decide a fila de
   ações — ou `Ctrl+R` ganha o botão primário, ou o critério de `estilos.PRIMARIO` é que está
   errado e é ele que muda.
2. **O `destaque` da S-223 não fecha com a regra que a própria S-223 escreve.** Os quatro da
   Imagem 1 estão declarados (`ler_pagina`, `proximo_diagrama`, `aplicar_fen`, `exportar_pgn`),
   mas o texto da S-223 diz que eles são *"quatro dos dez que já têm atalho de teclado"* e **dois
   não têm**: `aplicar_fen` e `exportar_pgn` não estão em `atalhos.ATALHOS`. O critério
   `test_destaque_exige_atalho` reprovaria os dois. Ou eles ganham tecla, ou a regra cai — e a
   decisão é da S-223, não desta.
3. **`icone` nasceu vazio em todos os 35, de propósito.** O repositório não tem um único ícone
   (achado 6 do roadmap), e nome de ícone que ninguém desenha é a mesma promessa que a S-161
   registra como defeito em item de menu sem comando. A S-220 é quem preenche.

**O que ficou de fora, e onde está registrado.** Os controles de dentro de uma aba — Galeria,
Dataset, Revisão, Configuração — não são comandos da *janela*: pertencem ao painel que os desenha
e não mudam de lugar quando a pele muda. É a mesma linha que `menu.MENUS` já traçava. O caso de
fronteira é `ui/result_panel.py`: os três botões dele ("Aplicar FEN", "Salvar posição
reconhecida", "Salvar todos") **são** comandos da janela e estão no catálogo, mas o painel ainda
escreve os rótulos à mão — por isso os três não declaram `rotulo_curto`, que seria promessa não
cumprida. É o único lugar onde a fenda antiga continua aberta, e quem a fecha é o inventário da
S-233.

**O que custou.** `app_tkinter.py` foi de 1.800 para 1.808 linhas, e a catraca de
`test_packaging.TamanhoDaJanelaTests` subiu junto, com a conta escrita lá:
`comandos.rotulo_de_botao("tirar_do_campo")` é mais largo que `"Tirar o selecionado"`, e dois
botões que cabiam em uma e em três linhas passaram a caber em seis cada. O import não cresceu —
`estilos` saiu e `comandos` entrou no lugar.

**Critério de aceite.**

- todo `acao` de `menu.MENUS` está no catálogo, e todo `acao` de `atalhos.ATALHOS` também;
- todo comando montado como botão em `pdf_panel` e na linha de campo vem do catálogo — o teste
  varre a árvore sintática e falha se sobrar rótulo escrito à mão, inclusive f-string;
- `papel` de cada comando é um de `estilos.PAPEIS_DE_BOTAO`; papel desconhecido levanta `KeyError`,
  como em `estilos.estilo_de_botao`;
- **no máximo um `PRIMARIO` por grupo** — a regra de `ui/estilos.py:31-36` aplicada ao catálogo,
  onde ela finalmente é verificável sem abrir janela. `test_ui_estilos` deixou de contar literais
  em `comandos.py` por isso: ali a propriedade é afirmável, e proxy sobre o registro mediria o
  arquivo inteiro em vez de uma barra;
- `grupo` de todo comando é um dos seis; o conjunto dos grupos é fechado;
- o módulo não importa `tkinter` (o mesmo teste que a S-145 faz para `tokens`).

**Testes.** `tests/test_ui_comandos.py`, 13 casos: `test_todo_item_de_menu_esta_no_catalogo`;
`test_todo_atalho_esta_no_catalogo`; `test_o_menu_mostra_o_rotulo_do_catalogo`;
`test_nenhum_rotulo_de_botao_escrito_a_mao`;
`test_os_rotulos_que_divergem_do_menu_estao_registrados`; `test_um_primario_por_grupo`;
`test_papel_desconhecido_levanta`; `test_grupo_desconhecido_levanta`;
`test_o_grupo_de_todo_comando_e_um_dos_seis`; `test_comando_desconhecido_levanta`;
`test_os_grupos_cobrem_o_catalogo_inteiro`; `test_todo_grupo_tem_rotulo_legivel`;
`test_o_catalogo_nao_importa_tkinter`.

---

## S-220 · O ícone que nasce do token, e não do disco ✅ implementada (2026-08-24)

**Problema.** `assets/` tem 12 PNGs de peça e um `.ico`, e mais nada. As duas propostas são
dirigidas a ícone — 4 na Imagem 1, 13 na Imagem 2 —, e não existia um.

Um conjunto de PNG resolve uma proposta e quebra a outra. Os PNGs de peça deste projeto são traço
preto com transparência, e `PieceImages.icon` documenta exatamente o que acontece com eles quando
o fundo escurece (`ui/board_render.py:196-199`): *"num dos 15 temas escuros do `ttkbootstrap` as
seis peças pretas somem no fundo da janela"*. A pele "Foco" é escura. Um PNG de traço escuro nela
é um botão sem ícone, e um PNG de traço claro na pele "Fita" é o mesmo defeito espelhado.

É o mesmo defeito que a S-146 mediu no tabuleiro — cor cravada contra fundo variável —, agora
numa família de arte nova.

**Solução.** `ui/icones.py`: o ícone é **traço declarado numa caixa 0..100**, e o desenho é
derivado.

```python
ICONES: dict[str, tuple[Traco, ...]] = {
    "abrir_pdf": (Poli((10, 30), (40, 30), (48, 40), (90, 40), (90, 82), (10, 82), fechado=True),),
    "zoom_mais": (Arco((44, 44), 28), Poli((64, 64), (88, 88)),
                  Poli((44, 32), (44, 56)), Poli((32, 44), (56, 44))),
    ...
}
```

Dois primitivos bastam: `Poli(*pontos, fechado=False)` e `Arco(centro, raio, inicio, fim)`. Ambos
respondem `limites()`, e é sobre isso que a guarda de caixa se afirma sem desenhar nada.

`icone(nome, tamanho, cor)` desenha com a Pillow e devolve `ImageTk.PhotoImage`, com cache por
`(nome, tamanho, cor)` — o mesmo padrão de `PieceImages._cache`, e pela mesma razão: a fita
redesenha treze ícones a cada mudança de densidade. `imagem(...)` é a mesma coisa **sem** o Tk, e
existe para que o desenho seja conferível sem abrir janela.

**A cor não é parâmetro do desenho, é do chamador, e o chamador pergunta ao token.** Quem monta a
fita pede `tokens.cor(tokens.TEXTO_PADRAO, style)` e passa; quem monta a fila da pele "Foco" pede o
mesmo papel resolvido contra o cromo escuro. Nenhum ícone tem cor própria — e é isso que faz o
mesmo `abrir_pdf` funcionar nas três peles sem uma segunda arte.

**Por que não SVG.** Traria dependência (`cairosvg` ou similar) para desenhar catorze formas de
traço único. O `ImageDraw.line` com `joint="curve"` faz o que estas formas precisam, e a Pillow já
é dependência obrigatória.

**Como ficou: catorze, e a conta é das duas imagens.** A Imagem 1 pede quatro e a Imagem 2 pede
treze; a união, **restrita ao que existe como comando hoje**, dá treze:

| grupo | ícones |
|---|---|
| ARQUIVO | `abrir_pdf`, `salvar`, `exportar_pgn` |
| OCR | `ler_pagina`, `ler_melhor`, `selecionar_area` |
| EDICAO | `aplicar_fen`, `apagar_casa`, `diagrama_anterior`, `proximo_diagrama` |
| VISUALIZACAO | `zoom_mais`, `zoom_menos`, `ajustar_largura`, `ajustar_pagina` |

O décimo quarto é `diagrama_anterior`: a Imagem 1 desenha só o "próximo", e uma seta que existe num
sentido só deixa metade do grupo de fita sem ícone (S-228). **Os três da Imagem 2 que não entraram
são os que não existem** — Desfazer e Refazer não têm implementação nenhuma (achado 4 do roadmap; é
a S-229 que os cria), e a "Limpar" dela é a `apagar_casa` daqui, que já está na lista.

A chave de `ICONES` é o nome do comando, e `Comando.icone` guarda essa chave. É redundante de
propósito: a string presente **é** a declaração de que aquele comando tem ícone, e é o que permite
a ponte ser conferida nos dois sentidos. `ui/comandos.py` continua sem importar `PIL`, e
`ui/icones.py` não conhece comando nenhum — quem os liga é o teste.

**Duas decisões de desenho que a spec não previa, e as duas foram medidas.**

1. **A cor entra por máscara, e não no traço.** Desenhar colorido e reduzir faz a `LANCZOS`
   interpolar os três canais junto com o alfa: pedindo `#101010` a 32 px, **31 dos 42 pixels
   opacos saíam `#111111`** e um saía `#121212`. Num ícone escuro sobre fundo claro isso não se
   vê; num ícone claro sobre o cromo escuro da pele "Foco" é halo em volta do traço — o defeito
   que este item existe para não ter. O traço passa a ser desenhado numa máscara `L`, a redução
   acontece nela, e a cor entra chapada por baixo. O resultado devolve **exatamente** o
   hexadecimal que o token resolveu, com toda a suavização no alfa.
2. **Desenha-se a 4× e reduz-se.** A `ImageDraw` não suaviza traço. Sem a superamostragem a
   diagonal do "visto" a 20 px vira escada e o círculo da lupa vira um octógono — justamente no
   tamanho em que o ícone é a única coisa que se lê no botão.

**E uma terceira, que é a razão de a caixa ser um intervalo fechado.** O traço é centrado no
caminho, então um ponto em `0` desenharia metade fora da imagem. A caixa `0..100` é mapeada para
`[largura/2, lado - largura/2]`, e por isso **toda** coordenada válida cabe — a guarda pode cobrar
`0..100` fechado em vez de uma margem escolhida a olho.

**Critério de aceite.**

- todo comando do catálogo com `icone` preenchido tem entrada em `ICONES`, e vice-versa: ícone
  órfão falha;
- toda coordenada de todo traço está em `0..100` — um traço que vaza a caixa desenha cortado, e o
  teste o pega sem abrir janela;
- `icone` devolve imagem do tamanho **exato** pedido, em qualquer tamanho de 16 a 48;
- a mesma chamada duas vezes devolve o mesmo objeto (cache), e trocar a cor **ou o tamanho**
  devolve outro;
- o pixel opaco do traço é o hexadecimal pedido, sem desvio de canal;
- ícone desconhecido devolve `None` e registra `warning` — **não levanta**: um ícone que falta vira
  botão só com texto, e não uma janela que não abre (regra 4).

**Testes.** `tests/test_ui_icones.py`, 14 casos: `test_todo_comando_com_icone_tem_traco`;
`test_nenhum_icone_orfao`; `test_sao_catorze_e_a_conta_e_das_duas_imagens`;
`test_todo_traco_cabe_na_caixa`; `test_todo_icone_tem_ao_menos_um_traco`;
`test_poli_recusa_um_ponto_so`; `test_o_traco_na_borda_da_caixa_nao_sai_da_imagem`;
`test_o_traco_sai_na_cor_pedida`; `test_a_mesma_forma_em_duas_cores_sao_dois_desenhos`;
`test_o_tamanho_pedido_e_o_entregue`; `test_o_cache_devolve_o_mesmo_objeto`;
`test_trocar_a_cor_ou_o_tamanho_devolve_outro`; `test_limpar_cache_esquece_tudo`;
`test_icone_desconhecido_nao_levanta`.

**O que ainda não acontece.** Nenhum widget mostra ícone: os catorze existem, são conferidos e não
são desenhados em lugar nenhum da janela. É de propósito — a pele clássica não muda (regra 1), e
quem põe ícone em botão é a fila da S-223 e a fita da S-228. Até lá o valor entregue é o registro,
como na S-324.

---

## S-221 · A pele como estado da janela, e a clássica como padrão ✅ implementada (2026-08-24)

**Problema.** Não havia onde guardar "qual aparência". `AppState` (`ui/state.py:57-101`) guardava
PDF, página, zoom, geometria, aba aberta e dois interruptores de visualização — e nada sobre cromo.
O único eixo de aparência que existe é o tema, e ele é **variável de ambiente** (`CVOFF_TTK_THEME`,
`ui/theme.py:51`): escolhido antes de o programa abrir, invisível de dentro dele.

**Solução.** `ui/pele.py`, com o mesmo formato de `menu.MENUS` — declaração, não classe por pele:

```python
@dataclass(frozen=True)
class Pele:
    nome: str                          # "classica" -- a chave, e o que vai para o disco
    rotulo: str                        # "Clássica" -- o que a pessoa lê no menu
    montar_cromo: str                  # o nome da montagem; quem a executa é o painel
    densidade: str = CONFORTAVEL       # ui/tipografia, S-232
    cromo_escuro: bool = False         # S-224
```

`AppState` ganhou `skin`, com `STATE_VERSION` indo a 3 — e a regra de `ui/state.py:19-22` já cobre
o resto: estado de versão futura é descartado, não adivinhado. `CVOFF_SKIN` acompanha
`CVOFF_TTK_THEME` para quem dirige o programa por script.

O menu ganhou `Ver ▸ Aparência` com um `radiobutton` por pele registrada — montado do registro, e
não listado à mão.

**O eixo pele e o eixo tema ficam separados de propósito.** Pele decide arranjo e densidade; tema
decide cor. Amarrá-los faria "a fita clara com o tabuleiro escuro" ser impossível sem que ninguém
tivesse decidido isso.

**Como ficou: uma pele registrada, e é o item.** A fundação se prova quando não muda nada. `PELES`
tem uma linha — a clássica —, e o submenu mostra uma opção marcada. Registrar "Foco" e "Fita" antes
de elas existirem seria oferecer no menu uma escolha que não faz nada, que é exatamente o defeito
que `menu.montar` recusa desde a S-161. Quem acrescenta linha ali é a S-223 e a S-227.

Fora do submenu, **nada na janela mudou**: mesmos widgets, mesma ordem, mesma geometria.

**Quatro decisões que a spec não fixava, e o porquê de cada uma.**

1. **`skin` nasce vazio, e não `"classica"`.** A spec escreveu o segundo. O nome da pele padrão é
   de `ui/pele.py`, e cravá-lo em `ui/state.py` o declararia num segundo lugar — a fenda que a
   S-324 acabou de fechar para os comandos, reaberta no arquivo ao lado. Vazio já quer dizer "cai
   no padrão", e é o que `active_tab`, `window_geometry` e `review_queue_path` **neste mesmo
   arquivo** já significam. Quem responde "qual pele, então?" é `pele.escolhida`.
2. **O ambiente ganha da guardada**, e isso é o inverso de `theme.apply_theme`, onde o argumento
   explícito ganha da variável. Lá o argumento é de quem chama, no código; aqui a guardada é do
   disco, e uma variável de ambiente que o disco vencesse não serviria para o que ela existe —
   abrir o programa numa aparência a partir de um roteiro.
3. **`montar` passou a levantar quando um item de `APARENCIA` não traz o `StringVar`.** É a mesma
   disciplina do item de menu sem comando, e pelo mesmo motivo medido: um `radiobutton` sem
   variável desenha as opções **sem nenhuma marcada**, e quem clicar conclui que a escolha não
   pegou. Custou passar `escolhas=` nos seis pontos de montagem de `test_ui_menu`, e é o tipo de
   custo que a trava existe para cobrar.
4. **O submenu é montado uma vez, e não no `postcommand`.** A spec o comparou a
   `_submenu_recentes`, e a analogia vale para "montado do registro"; não vale para *quando*. O
   acervo muda enquanto o programa roda — daí os recentes se refazerem a cada abertura —, e o
   registro de peles é fixo na importação. O que varia é a **marca**, e disso quem cuida é o
   `StringVar`.

**Uma ordem que a implementação descobriu.** O menu é montado em `_build_menu`, e o estado só é
lido em `_restore_state_or_default_pdf`, **depois**. Então a variável nasce com o que o ambiente
diz e a restauração a corrige com o que estava no disco — duas linhas, e a segunda é fácil de
esquecer: sem ela, a pele escolhida na sessão anterior seria mostrada como clássica no menu,
enquanto o disco guardava outra coisa.

**Critério de aceite.**

- sem `skin` no disco, sem a variável e sem mexer no menu, a pele é `classica` — e a janela
  montada é **idêntica** à de hoje: mesmos widgets, mesma ordem, mesma geometria;
- pele desconhecida (disco ou variável) cai em `classica` com um `warning` que a **nomeia**, e não
  levanta — e nome vazio não avisa nada, porque "nunca escolheu" não é erro;
- `Ver ▸ Aparência` lista exatamente as peles registradas, com a atual marcada, e o `value` do
  `radiobutton` é o nome de disco, não o rótulo lido;
- a pele escolhida sobrevive a fechar e reabrir, e `STATE_VERSION=3` lê o arquivo da versão 2 sem
  perder nenhum dos treze campos dela.

**Testes.** `tests/test_ui_pele.py`, 16 casos: `test_a_pele_padrao_e_a_classica`;
`test_hoje_ha_uma_pele_registrada`; `test_toda_pele_tem_nome_de_chave_e_rotulo_de_gente`;
`test_pele_desconhecida_cai_na_classica_com_aviso`; `test_nome_vazio_nao_avisa_nada`;
`test_registrada_levanta_para_quem_ja_devia_saber`; `test_o_ambiente_ganha_da_guardada`;
`test_densidade_desconhecida_levanta`; `test_a_pele_sobrevive_ao_fechamento`;
`test_estado_da_versao_2_e_lido_sem_perda`; `test_a_pele_gravada_volta_no_json`;
`test_pele_de_tipo_errado_cai_no_padrao`; `test_o_menu_lista_as_peles_registradas`;
`test_a_pele_atual_vem_marcada`; `test_escolher_dispara_o_comando_amarrado`;
`test_montar_recusa_item_de_aparencia_sem_variavel`.

**O que custou.** `app_tkinter.py` foi de 1.808 para 1.821 linhas, e a catraca subiu junto com a
conta escrita em `test_packaging`. As treze são amarração — o `StringVar`, a entrada em
`_comandos`, o `escolhas=` e o `_escolher_pele`, que é o único lugar que tem o `AppState` **e** a
variável ao mesmo tempo. O registro em si não está lá, e é o que faz a subida ser de treze e não
de cinquenta.

---

## S-222 · Trocar de pele sem fechar a janela, e sem perder o lugar ✅ implementada (2026-08-24)

**Problema.** Escolher aparência reiniciando o programa é escolher no escuro: quem compara três
peles reabre três vezes e compara de memória. E há um segundo custo, maior: reabrir perde o
**contexto de trabalho** — a página, o zoom, o diagrama selecionado, a FEN em edição, a aba aberta.
Quem estava no meio de uma correção não vai trocar de pele para ver.

A docstring de `theme.registrar_estilos` (`ui/theme.py:210-213`) já previu isto por escrito:
*"trocar de tema em execução — o que `CVOFF_TTK_THEME` permite entre execuções e um menu de
preferências vai permitir dentro de uma — precisa reaplicá-la"*. A troca agora a reaplica.

**Solução.** A troca **remonta o cromo e não toca o conteúdo**. É viável porque a fronteira já foi
paga duas vezes: a Fase 6 tirou o pipeline das telas, e a S-49/S-50 tiraram o estado dos widgets.
O que se destrói e refaz são as duas barras do painel de PDF, a linha de conjunto de campo e a
barra de menus; o `PanedWindow`, os painéis e o `DiagramEditorModel` continuam de pé.

`ui/pdf_panel.remontar_cromo` faz o trabalho; `ChessOcrTkApp.remontar_cromo` faz a ordem — estilos,
cache de ícones, painel, menu. São quatro linhas de código na janela, porque tudo o que exige
saber de widget mora junto de quem os criou.

**A descoberta é a primeira linha da tabela abaixo, e ela apaga a tabela.**

| preservar | como ficou |
|---|---|
| PDF aberto e página | **não é preservado: é intocado** |
| zoom do PDF e do tabuleiro | idem — os `Var` são do painel, e o painel sobrevive |
| diagrama selecionado e FEN em edição | idem — a remontagem nem alcança o painel de resultado |
| aba aberta | idem — o `Notebook` não é cromo de pele |
| posição do divisor | idem — o `PanedWindow` também não |
| a frase do rodapé | idem — `ui/rodape.py` não é tocado |

Os seis itens que a spec mandava preservar **não precisam de nenhuma máquina de salvar e
restaurar**. Um `Contexto` que os fotografasse antes e os devolvesse depois teria sido código
morto de nascença — e, pior, teria escondido o fato que interessa: a fronteira certa é a que faz a
pergunta desaparecer. Os seis viraram **asserções**, não mecanismo.

**E a spec estava errada sobre as ligações — de um jeito que, seguido à letra, produziria o
defeito que ela mesma proíbe.** Estava escrito que os `bind_all` de roda e atalho precisam ser
**refeitos**. Refazê-los é exatamente o que quebra o critério seguinte: `_bind_wheel` usa
`bind_all` com `add="+"`, que **acumula**, e N trocas deixariam N cópias da mesma tecla. E não
adianta desligar antes: `unbind_all("<MouseWheel>")` tira a ligação de **todo mundo**, inclusive
a das abas roláveis que o `add="+"` da S-150 existe para preservar.

A resposta certa é não religar. A roda é do painel e o painel sobrevive à troca; os dez atalhos
são da janela, que também sobrevive. O que a linha da spec descreve é o perigo de uma remontagem
que destrua **painel**, e é por isso que ela não destrói: `remontar_cromo` só alcança os filhos do
`LabelFrame`, e o docstring dela diz isso para quem for escrever a pele "Fita".

**O que precisa mesmo ser devolvido, e não estava na tabela.** Os `Var` sobrevivem à destruição
dos widgets, mas o que é escrito por `config` na hora do evento, não:

| devolvido | por quê |
|---|---|
| o `state` dos seis botões da barra | "Cancelar exportação" só fica ativo durante uma exportação, e os três de OCR ficam cinzas enquanto um roda — uma troca no meio devolveria os seis ao estado de janela recém-aberta |
| o nome do livro e o teto do `Spinbox` | escritos em `_open_pdf`, não guardados em `Var` |
| o rótulo de quem estava ligado | o `selecionar_area` mostra "Cancelar seleção" enquanto a seleção corre |

O `state` é lido dos próprios botões antes de eles serem destruídos e devolvido depois — mais
curto e mais exato que manter bandeiras espelhando o que o widget já sabe.

**Duas armadilhas de montagem, e as duas têm teste.** As barras refeitas precisam de
`pack(before=self.field_row)`: sem isso elas nascem **abaixo** do canvas, porque o `pack` empilha
quem chega por último. E a linha de conjunto de campo precisa ser esvaziada antes de refeita, ou
duplica a cada troca.

**Um buraco na guarda da S-324, achado por este item.** O `selecionar_area` troca o próprio rótulo
por `configure(text="Cancelar seleção")`, e a varredura de `test_nenhum_rotulo_de_botao_escrito_a_mao`
só olhava o `text=` do **construtor** — dois literais escritos à mão passavam por limpos. O
catálogo ganhou `rotulo_alternado`, o painel passou a pedi-lo, e a varredura agora olha também o
`self.btn_*.configure(text=...)`. O crivo é o prefixo `btn_`: `lbl_pdf` e `lbl_zoom` também
recebem `config(text=...)`, e o texto deles é **dado** — o nome do livro, a porcentagem do zoom —,
não rótulo de comando.

**Critério de aceite.**

- trocar de pele preserva os seis itens da tabela, e o teste os afirma um a um — inclusive o
  painel de resultado, cujo dublê levanta em **qualquer** atributo tocado;
- depois de N trocas, o número de ligações de cada sequência de tecla é 1 — não N;
- a troca não reabre o PDF nem re-renderiza a página: o `PhotoImage` é o mesmo objeto, e
  `render_current_page` não é chamada;
- a troca grava a escolha no `AppState` na hora, e não só no fechamento;
- escolher a pele que já está valendo **não** remonta — a primeira escolha da vida do programa é
  a clássica sobre a clássica, e remontar ali seria um piscar sem motivo.

**Testes.** `tests/test_ui_troca_de_pele.py`, 14 casos. No painel:
`test_a_troca_preserva_a_pagina_e_o_zoom`; `test_a_troca_nao_re_renderiza_a_pagina`;
`test_a_troca_nao_duplica_ligacao_de_tecla`; `test_a_troca_preserva_o_estado_dos_botoes`;
`test_a_troca_preserva_o_rotulo_de_quem_estava_ligado`; `test_as_barras_voltam_acima_da_pagina`;
`test_a_linha_de_campo_e_refeita_e_nao_duplicada`. Na janela:
`test_a_troca_grava_a_escolha_na_hora`; `test_escolher_a_pele_que_ja_esta_valendo_nao_remonta`;
`test_pele_invalida_no_menu_cai_na_classica_e_a_variavel_acompanha`;
`test_a_troca_refaz_o_menu_e_a_linha_de_campo`; `test_a_troca_esvazia_o_cache_de_icones`;
`test_a_troca_reaplica_os_estilos_nomeados`; `test_a_troca_preserva_o_diagrama_e_a_fen`.

**O que ainda não acontece.** Com uma pele registrada, a troca que o programa faz é nenhuma: o
`radiobutton` não tem para onde mudar, e `_escolher_pele` só grava. A máquina é exercida pelos
catorze testes, e quem a liga de verdade é a S-223, ao registrar a segunda pele. É o mesmo
combinado da S-220 — a fundação se prova quando não muda nada.

**O que custou.** `app_tkinter.py` foi de 1.821 para 1.843 linhas, com a conta em `test_packaging`.

---

# Fase 33 — A pele "Foco" (Imagem 1)

> Cromo escuro, uma fila só de ações, o documento ocupando tudo o mais. É a proposta mais radical
> das duas, e a que mais depende da regra 2 para ser segura.

## S-223 · A fila única de ações, e o resto onde ele já estava ✅ implementada (2026-08-24)

**Problema.** A Imagem 1 mostra **quatro** comandos onde a janela tem 21 nas duas barras do PDF,
mais 6 na linha de campo. Desenhá-la ao pé da letra apaga 23 controles.

Mas a imagem não está errada — está incompleta. O que ela acerta é o diagnóstico: numa fila de 21
botões de peso igual, o olho não encontra a ação do minuto a minuto. É o mesmo argumento de
`ui/estilos.py:12-16`, agora sobre quantidade em vez de ênfase.

**Solução.** A fila da pele "Foco" é **gerada** dos comandos com `destaque=True` no catálogo
(S-324), agrupados por `grupo`, com um separador vertical entre grupos — que é exatamente o que a
imagem desenha entre a 2ª e a 3ª pílula. `ui/fila.py` monta; `comandos.fila_de_destaque()` decide.

**O separador não é um item da lista, e é o que torna a regra estrutural.** `fila_de_destaque`
devolve uma tupla **por grupo**, e não uma lista plana com marcas. Assim "separador só entre
grupos, nunca na ponta" deixa de ser regra a cobrar: quem desenha põe uma barra entre tuplas
consecutivas, e não sobra onde pôr uma.

**Os quatro em destaque não são os quatro da imagem, e a diferença foi medida.**

| a imagem | a fila | por quê |
|---|---|---|
| ler | `ler_pagina` | igual |
| próximo diagrama | `proximo_diagrama` | igual |
| aplicar FEN | `aplicar_fen` | igual, **e ganhou tecla** |
| exportar | `salvar` | **trocado** |

A regra desta S é que `destaque` exige atalho de teclado, pela mesma lógica com que
`estilos.PRIMARIO` é definido como *"a ação que o atalho também faz"*. A spec afirmava que os
quatro da imagem eram "quatro dos dez que já têm atalho"; a S-324 mediu e **dois não tinham**. Os
dois lados cederam, cada um por uma razão própria:

1. **`aplicar_fen` ganhou `Ctrl+Enter`** — o décimo primeiro atalho. Ele fecha o ciclo
   corrigir → salvar e não tinha tecla: quem digitava uma FEN à mão era obrigado a largar o
   teclado para aplicá-la, com as mãos já dentro do campo. É a mesma situação de notebook que a
   S-150 mediu para o `Ctrl+S`.
2. **`exportar_pgn` saiu e `salvar` entrou.** A imagem desenhou "exportar" e **omitiu "salvar"**,
   e a medida do fluxo inverte os dois: exporta-se uma vez por livro e salva-se uma vez por
   diagrama. Uma fila dimensionada por importância em vez de frequência é a barra de 21 botões
   outra vez — que é o defeito de que este item veio tirar a janela.

**A ordem é a do catálogo, e não a da imagem.** A Imagem 1 começa por "ler"; a fila começa pela
Edição, porque é a ordem de `GRUPOS`, que é a da barra de menus. Reordenar seria declarar pela
segunda vez em que ordem os comandos vivem, e é disso que a S-324 tirou o programa. Medido a
1100 px, a fila fica assim, em **uma** linha:

```
[ Aplicar a FEN digitada ] [ Salvar a posição ] [ Próximo diagrama ] │ [ OCR todos diagramas ]
       0..164                   170..302            308..453        459     466..629
```

**Os outros 23 controles não somem: eles vão para o menu**, que a S-161 construiu e que a própria
Imagem 1 mostra intacto no topo. Três deles **não tinham** item de menu — "Cancelar exportação" e
os dois botões de zoom —, e ganharam um. A conta fecha em dois destinos e não em três, e agora há
um teste que cobra isso: todo comando do catálogo está no menu **ou** em
`comandos.NA_LINHA_DE_CAMPO`.

**A linha do conjunto de campo é a exceção, e ela fica.** A S-77 a pôs junto da página exibida de
propósito: ela anota *aquela* página, e um comando de menu que age sobre a página exibida sem que
ela esteja à vista é o tipo de gesto que grava verdade de referência errada. Os três comandos dela
são a única exceção declarada — e existir como lista é o que permite ao teste cobrar que não haja
uma segunda.

**Na pele "Foco" os 21 controles são criados e não empacotados.** Parece desperdício e é o
contrário: `set_ocr_controls_enabled`, `_open_pdf` e `update_zoom_label` escrevem nesses widgets o
tempo todo, e fazê-los existir mantém o painel com um caminho só. **O que a pele decide é o que
aparece na tela, não o que o painel sabe fazer.**

**Uma decisão de desenho que a implementação teve de tomar.** A guarda de foco de
`ui/shortcuts.py` cede **qualquer** atalho a um campo de texto — e é dentro do campo de FEN que
`Ctrl+Enter` mais faz sentido. Quem liga a tecla ali é o próprio campo, pelo caminho que a S-117
abriu (`owns_key`: quem declarou a tecla fica com ela), lendo a sequência de `ui/atalhos.py`. Uma
declaração, duas ligações.

> **E um achado que não vira mudança aqui.** A mesma guarda cede **os onze** atalhos dentro de
> qualquer `Entry`, inclusive `Ctrl+S`, `Ctrl+R` e `Ctrl+N`, que campo de texto nenhum usa. O
> docstring dela só justifica `←`, `→` e `Del`. Digitar uma FEN e apertar `Ctrl+S` não salva hoje,
> e ninguém registrou isso. Fica anotado para um item próprio: mexer na guarda muda o
> comportamento dos onze, e não é o que "a fila única de ações" autoriza.

**Critério de aceite.**

- a fila é gerada do catálogo: acrescentar `destaque=True` a um comando o faz aparecer, sem tocar
  na montagem;
- todo comando com `destaque=True` tem atalho em `atalhos.ATALHOS`; sem atalho, falha;
- **no máximo 6 comandos em destaque** — acima disso a fila deixa de ser fila e vira a barra que
  ela veio substituir;
- os separadores caem entre grupos, e nunca na ponta — garantido pela forma do dado, não por
  regra;
- os controles que saem da tela têm item de menu **ou** estão em `NA_LINHA_DE_CAMPO` — nenhum
  terceiro destino;
- em 1100×760, a largura em que a S-151 mediu o defeito original, a fila cabe em **uma** linha;
- a pílula recusa comando não amarrado, como `menu.montar`: uma pílula grande com ícone que não
  faz nada é pior que a ausência dela.

**Testes.** `tests/test_ui_fila.py`, 14 casos: `test_a_fila_sai_do_catalogo`;
`test_destaque_exige_atalho`; `test_no_maximo_seis_em_destaque`;
`test_a_fila_vem_agrupada_e_sem_grupo_vazio`; `test_a_ordem_e_a_do_catalogo_e_nao_a_da_imagem`;
`test_nenhum_comando_tem_terceiro_destino`; `test_separador_so_entre_grupos`;
`test_o_separador_tem_a_altura_das_pilulas`; `test_a_fila_cabe_em_uma_linha_em_1100`;
`test_a_fila_recusa_comando_sem_funcao`; `test_clicar_na_pilula_chama_o_comando`;
`test_cada_pilula_traz_o_icone_do_comando`;
`test_a_foco_esta_registrada_e_a_classica_continua_primeira`; `test_a_foco_ainda_nao_e_escura`.
Em `test_ui_troca_de_pele.py`, mais dois:
`test_na_pele_foco_as_barras_saem_da_tela_e_os_controles_continuam` e
`test_voltar_para_a_classica_devolve_as_barras`.

**O que esta S ainda não faz.** A pele "Foco" está registrada e desenha a fila, e **o cromo dela
continua claro**: a Imagem 1 é escura e quem escurece é a S-224. `Pele.cromo_escuro` segue `False`
de propósito — declarar `True` antes disso seria a pele dizendo que é escura enquanto desenha
claro, a mesma promessa não cumprida que a S-220 recusou ao deixar `icone` vazio. Faltam também o
deslizador de zoom (S-225) e a faixa de abas discreta (S-226).

**O que custou.** `app_tkinter.py` foi de 1.843 para 1.859 linhas, com a conta em
`test_packaging`. A fila em si é `ui/fila.py`, que não conhece a janela.

---

## S-224 · Cromo escuro, documento claro, marcações remedidas ✅ implementada (2026-08-24)

**Problema.** A Imagem 1 é escura, e `ui/theme.py:37-50` argumenta contra tema escuro **por
escrito**, com um argumento bom: o produto é comparar diagrama impresso em papel branco com o que o
modelo leu, e pôr a página renderizada sobre preto faz o olho corrigir contraste em vez de posição.

Só que a imagem não contradiz isso. **A página dela continua branca.** O que escurece é o cromo — a
moldura, as barras, o fundo em volta.

Há um segundo problema, e é o que deu trabalho. As marcações deste projeto têm contraste **medido**
contra as superfícies de hoje (S-146, S-158, S-159). Escurecer o cromo cria uma superfície nova, e
nada garantia que os papéis sobrevivessem a ela. **Não sobreviveram:** cinco dos sete pares de
texto reprovaram o piso AA sobre o cromo escuro, e um deles obrigou a separar dois papéis que
carregavam significados diferentes com um nome só.

**Solução — a fronteira.** `tokens.SUPERFICIES_DE_DOCUMENTO` (`SUPERFICIE_PAGINA`,
`SUPERFICIE_TABULEIRO`, `MOLDURA`) mantêm a paleta medida **em qualquer pele**;
`tokens.NO_CROMO_ESCURO` dá o valor de cromo escuro aos que são cromo. `cor()` ganhou
`cromo_escuro=`, e ele faz duas coisas opostas de propósito: escurece o cromo e **prende** o
documento. Trocar de *tema* continua movendo as superfícies, como desde a S-147 — tema é o eixo de
cor, e essa escolha é de quem a faz.

**A pele sugere o tema; a variável continua mandando.** `apply_theme` escolhe nesta ordem: o
argumento explícito, `CVOFF_TTK_THEME`, o padrão da pele (`bootstrap-dark` para quem declara
`cromo_escuro`), o padrão do programa. É o que mantém possível a combinação que a S-221 quis
preservar — a pele escura com o tema claro, se alguém decidir isso.

**A conta que a pele escura obrigou a assinar.** Sobre `#1f2124`, os valores escolhidos contra um
fundo claro dão:

| papel | claro | sobre o cromo escuro | ficou |
|---|---|---:|---|
| `PRONTO_TEXTO` | `#146c43` | **2,50:1** | `#1ea466` — 5,04:1 |
| `PROBLEMA_TEXTO` | `#c0392b` | **2,97:1** | `#dd7065` — 5,06:1 |
| `ATENCAO` | `#8a5a00` | **2,72:1** | `#c78200` — 5,09:1 |
| `DIVERGENTE_TEXTO` | `#8e44ad` | **2,75:1** | `#b37acb` — 5,04:1 |
| `VIZINHA_TEXTO` | `#1565c0` | **2,81:1** | `#4492eb` — 5,04:1 |

**A matiz é preservada nos cinco, e isso foi medido**: o desvio máximo é de 0,2°. O que muda é a
luminosidade, o mínimo para cruzar 5,0:1 — com folga sobre o piso de 4,5, porque um valor que passa
por 0,04 é um valor que a próxima mexida derruba sem avisar.

**O achado que a tabela esconde: `PROBLEMA` e `DIVERGENTE` eram dois papéis com um nome.** Os dois
fazem duas coisas — contorno de casa no tabuleiro e letra sobre o cromo. Na paleta clara isso
passou despercebido porque **o mesmo valor serve aos dois**: `#c0392b` dá 3,96:1 sobre a casa clara
e 4,77:1 sobre o cinza do cromo. Sobre um cromo escuro os dois usos pedem valores **opostos**: a
letra precisa clarear para ser lida, e o contorno precisa não clarear, porque ele é medido contra
as casas, que não seguem pele nenhuma.

Nasceram daí `PROBLEMA_TEXTO` e `DIVERGENTE_TEXTO`, pelo mesmo caminho que a S-146 abriu com
`PRONTO`/`PRONTO_TEXTO`. É a S-158 outra vez — *um papel, um significado* —, encontrada por um
caminho novo. Na pele clássica os dois pares têm o **mesmo valor de propósito**: separar os nomes
não muda um pixel de hoje, e é o que permite que só a pele escura os afaste. O
`test_dois_papeis_de_significado_diferente_nao_compartilham_hex` já previa o caso por escrito — *"se
um dia duas entradas precisarem da mesma cor, o par entra aqui com o motivo"* —, e foi o que se fez.

**O segundo achado: a paleta tinha desvios.** Trinta leituras diretas de `tokens.RESERVA[...]`
espalhadas pelos painéis, contornando `cor()`. Para **marcação** isso está certo — o documento é
preso e a marcação não deve seguir tema nem pele. Para **texto sobre o cromo** eram oito rótulos
cravados na paleta clara, e todos ficariam ilegíveis na pele escura. Os oito passaram a perguntar
ao papel, por `theme.pintar`.

**O terceiro, e é o que teria custado caro:** `tb.Style` é um singleton, e o `theme=` do construtor
leva do claro ao escuro e **não leva de volta**. Sem `theme_use`, escolher "Foco" e voltar para
"Clássica" deixaria a janela escura para sempre. Só a troca de pele expôs isso, porque até a S-222
ninguém trocava de tema com a janela aberta.

**`theme.ao_repintar` e `theme.pintar`.** Seis pontos liam a cor **na construção** e a guardavam no
widget — o fundo do canvas do PDF, o do tabuleiro, o do quadro rolável e três rótulos. Reaplicar o
estilo nomeado não alcança quem pintou fora do `Style`, e a docstring de `registrar_estilos` já
previa por escrito que trocar de tema em execução *"precisa reaplicá-la"*. Agora quem pinta se
registra na mesma linha em que pinta, e quem troca a pele chama um lugar só. Uma repintura que
falha é descartada com aviso: aparência não derruba ferramenta.

> **Três marcações que já reprovavam, e continuam.** `ALVO`, `PROBLEMA` e `DIVERGENTE` são
> desenhados como **contorno** de casa e dão 1,53:1, 1,73:1 e 1,86:1 sobre a casa escura — a mesma
> família do defeito que a S-158 mediu e consertou para o `CORRIGIDO`, em três papéis que ela não
> olhou. Estão em `REPROVAS_ANTERIORES_A_S224`, **como registro e não como perdão**: o que esta S
> cobra é que nenhuma pele acrescente um quarto. Corrigi-los é item próprio — mexer nessas cores é
> mexer numa paleta escolhida por eliminação de matiz.

**Critério de aceite.**

- na pele "Foco", `SUPERFICIE_PAGINA` e `SUPERFICIE_TABULEIRO` são as mesmas de hoje — e a
  identidade do tabuleiro também;
- os papéis de marcação atingem `AA_GRAFICO` sobre as superfícies em que são desenhados, em cada
  pele registrada — e o conjunto dos que reprovam é **idêntico** entre peles;
- os papéis de texto atingem `AA_TEXTO` sobre a superfície do cromo escuro — os sete pares, nas
  duas peles;
- nenhum par de papéis desenhados na mesma superfície fica abaixo de 40° de matiz, em nenhuma pele;
- a matiz de todo papel sobrevive à troca de pele: o que muda é luminosidade;
- o mesmo teste, sem alteração, falha se alguém registrar uma pele que quebre qualquer um desses.

**Testes.** `tests/test_ui_cromo_da_pele.py`, 15 casos:
`test_o_documento_nao_escurece_com_a_pele`; `test_a_identidade_do_tabuleiro_nao_segue_pele_nenhuma`;
`test_o_cromo_escuro_nao_toca_marcacao_nenhuma`; `test_todo_texto_atinge_aa_texto_em_toda_pele`;
`test_toda_marcacao_atinge_aa_grafico_em_toda_pele`; `test_a_separacao_de_matiz_vale_em_toda_pele`;
`test_a_matiz_do_papel_sobrevive_a_troca_de_pele`; `test_uma_pele_que_quebra_o_contraste_falha`;
`test_a_pele_escura_pede_o_tema_escuro`; `test_o_argumento_e_a_variavel_ganham_da_pele`;
`test_trocar_de_pele_volta_do_escuro_para_o_claro`;
`test_o_documento_nao_muda_ao_trocar_de_pele_na_janela`;
`test_pintar_aplica_agora_e_de_novo_depois`; `test_a_repintura_de_widget_morto_sai_da_lista`;
`test_uma_repintura_que_falha_nao_derruba_as_outras`. Em `test_ui_tokens.py`, mais um:
`test_o_par_declarado_deixa_de_coincidir_no_cromo_escuro`.

**O que custou.** `app_tkinter.py` foi de 1.859 para 1.862 linhas: três linhas, porque a paleta
inteira é `ui/tokens.py` e a escolha de tema é `ui/theme.py`.

---

## S-225 · O deslizador de zoom, sem tirar o teclado nem os botões de enquadrar ✅ implementada (2026-08-24)

**Problema.** O zoom do PDF eram cinco controles em fila: `-`, `+`, o rótulo `70%`, "Ajustar à
largura" e "Ajustar à página". Cada clique movia 0,1 — ir de 70% para 150% eram **oito cliques**. E
os cinco ocupavam metade da barra da vista, que é a que a S-151 mediu sumindo em 1100 de largura.

**Solução.** O deslizador que a Imagem 1 desenha no rodapé do painel, ligado ao mesmo
`viewport.clamp_zoom` de hoje, com escala **logarítmica**.

**Por que logarítmica, com número.** A faixa é 25% a 200%. Numa escala linear o meio do curso seria
112,5%, e a metade que importa — a de enquadrar um diagrama pequeno — se espremeria nos primeiros
milímetros. Na logarítmica o meio é a **média geométrica**, 70,7%: exatamente o zoom em que a
janela abre. A propriedade que isso compra tem teste próprio: **passos iguais movem razões iguais**,
em qualquer ponto do curso.

E ela faz o deslizador concordar com a roda **por construção**. `viewport.zoomed` já era
multiplicativo (`ZOOM_STEP = 1.15`); um giro de roda passa a mover o deslizador sempre a mesma
distância, esteja ele em 30% ou em 180%. Numa escala linear o mesmo giro moveria oito vezes mais no
fim do curso que no começo.

**O que ele não substitui, e é aqui que o item podia dar errado.** Ele substitui **três** controles
e não cinco: `-`, `+` e o rótulo, que ele passa a dizer. `Ctrl+0` (S-165) e a roda com `Ctrl`
continuam; "Ajustar à largura" e "Ajustar à página" continuam existindo, porque enquadrar não é um
valor de zoom — é uma pergunta sobre a página que o deslizador não sabe responder. Nesta pele as
duas moram no menu, como os outros dezoito controles (S-223). **E todos movem o deslizador**: quem
sincroniza é `update_zoom_label`, que já era chamada por todos eles.

**Três coisas que a implementação teve de resolver.**

1. **O laço.** `Scale.set` dispara o `command`, e o `command` chama `apply_zoom`, que chama
   `update_zoom_label`, que chama `Scale.set`. Sem uma guarda isso não termina. Tem teste: um
   arrasto chama `apply_zoom` **uma** vez.
2. **A ordem da montagem.** O rodapé de zoom precisa ser montado **depois** das barras, e não
   antes: `update_zoom_label` escreve no `lbl_zoom`, que é criado com elas — montar o rodapé
   primeiro escrevia no rótulo da montagem anterior, que a remontagem tinha acabado de destruir.
   O `TclError` apareceu no primeiro teste de troca de pele.
3. **O rótulo tinha dois donos em potencial.** O texto era um `f"{int(zoom * 100)}%"` cravado no
   painel, e a pele "Foco" o mostraria num segundo rótulo. Passou a vir de `formato.porcentagem`,
   e o rótulo "Zoom PDF" virou `strings.ZOOM_DA_PAGINA` — uma declaração, dois clientes. É a S-324
   aplicada a um controle que não é comando.

**Critério de aceite.**

- o deslizador cobre a mesma faixa de `clamp_zoom`, e nunca a ultrapassa — as pontas são exatamente
  `MIN_ZOOM` e `MAX_ZOOM`, e posição fora da faixa é grampeada nos dois sentidos;
- arrastar preserva o ponto de referência: o que está no centro da vista continua lá, como
  `apply_zoom` já fazia para `+` e `-`;
- `Ctrl+0`, a roda com `Ctrl` e os dois botões de enquadrar continuam funcionando, e movem o
  deslizador;
- o valor aparece em texto ao lado, na mesma forma de hoje (`70%`), lido por `ui/formato.py`;
- na pele clássica nada muda: o deslizador é da pele "Foco", e voltar para a clássica o leva embora.

**Testes.** `tests/test_ui_deslizador.py`, 12 casos. Puros:
`test_o_deslizador_respeita_o_clamp`; `test_a_conversao_volta_no_mesmo_lugar`;
`test_a_escala_e_logaritmica`; `test_passos_iguais_movem_razoes_iguais`. Com janela:
`test_a_pele_classica_nao_ganha_deslizador`; `test_arrastar_move_o_zoom_pela_escala`;
`test_enquadrar_move_o_deslizador`; `test_a_roda_com_ctrl_tambem_o_move`;
`test_o_deslizador_preserva_a_ancora`; `test_arrastar_nao_entra_em_laco`;
`test_o_rotulo_e_o_mesmo_texto_nos_dois_lugares`;
`test_voltar_para_a_classica_leva_o_deslizador_embora`.

**O que custou.** Zero linhas em `app_tkinter.py`: a aritmética é `ui/viewport.py` e o widget é
`ui/pdf_panel.py`, que já era quem sabia de zoom.

---

## S-226 · A faixa de abas discreta, e o rodapé que não pode sumir ✅ implementada (2026-08-24)

**Problema.** A Imagem 1 não tem faixa de abas nem rodapé. As abas são painéis inteiros, e a S-162
as reordenou de propósito, separando o que é do diagrama aberto do que é do acervo.

O rodapé é pior de perder. Depois da S-163 ele é onde mora o **cancelamento** da varredura, da
exportação e do treino, além do progresso e do estado do documento. Uma pele sem rodapé é uma pele
em que uma varredura de dez horas não pode ser interrompida.

**Este item é o que dá sentido à regra 2 da spec**, porque é onde a tentação de seguir a imagem à
risca é maior e o dano é o mais concreto: a varredura que não para.

**Correção de número: são sete abas, e não seis.** Seis era a conta da S-162; a S-211 acrescentou a
`Texto`, do lado do diagrama aberto — ela responde *"o que está escrito nesta folha?"*, que é a
mesma pergunta de contexto que o `Resultado` e a `Revisão` respondem. A spec ficou com o número
velho, e um número que ninguém reproduz é o mecanismo da S-135.

**Solução — as abas ficam declaradas.** `ui/abas.py` ganhou `DO_DIAGRAMA`, `DO_ACERVO` e
`ABAS = DO_DIAGRAMA + DO_ACERVO`. Os sete rótulos estavam escritos **só** como literais dentro de
`app_tkinter._build_left_panel`, e o corte da S-162 — o lugar em que a barra muda de assunto —
existia apenas como comentário. Agora ele é dado, e é sobre ele que o teste compara a barra
montada, em cada pele registrada.

> **E isso quase deixou um teste cego.** `test_as_do_diagrama_vem_antes_das_do_acervo` procurava
> `"Resultado"` no código do `app_tkinter`. Trocado o literal pela constante, ele encontraria zero
> abas e **passaria** as duas afirmações sobre listas vazias. Foi reescrito para seguir a constante
> — e ganhou um irmão, `test_a_janela_monta_as_abas_declaradas_na_ordem_declarada`, que reprova uma
> aba nova que entre no painel sem entrar na declaração.

**Solução — o peso da faixa.** `theme.ESTILO_DE_ABAS_DISCRETO` tira a moldura em relevo do
`ttk.Notebook` e deixa a barra ser sete palavras, das quais uma está acesa. A janela o aplica na
pele "Foco" e o remove na clássica, na mesma remontagem da S-222.

**A aba ativa se separa por cor e por negrito, e não por sublinhado.** A spec pedia sublinhado, e
ele exigiria um `layout` de elemento próprio para a aba — escrito por tema, e quebrado em cada um
dos trinta do `ttkbootstrap`. Cor e peso de fonte são opções que todo tema aceita, e dizem a mesma
coisa por **dois** canais em vez de um. O registro fica num `try` próprio: um tema que recuse o
estilo de abas não pode levar junto a tipografia, que é de outro item.

**O rodapé fica inteiro, e agora está medido.** A troca de pele remonta o cromo do painel, a fila e
o menu — e não alcança o rodapé, que é filho da janela. Isso já era verdade desde a S-222; o que
faltava era alguém afirmá-lo. O teste percorre as peles registradas e cobra, em cada uma, que o
rodapé continue no layout e que o botão de cancelar apareça habilitado com uma operação cancelável
em curso.

> **`winfo_manager` e não `winfo_ismapped`.** Numa suíte que não levanta janela, nada está
> "mapeado" — um teste que dependesse disso passaria a verde por não medir nada. O que se afirma é
> que o widget continua empacotado.

**Critério de aceite.**

- as **sete** abas existem em todas as peles, na ordem da S-162 com a `Texto` da S-211;
- o rodapé existe em todas as peles, com o botão de cancelamento presente e habilitado sempre que
  há operação cancelável em curso;
- a faixa de abas da pele "Foco" atinge `AA_TEXTO` sobre o cromo escuro, aba ativa e inativa —
  medido no que o `Style` de fato guardou, e não nos papéis que se pretendia usar;
- a contagem em cada rótulo continua vindo de `ui/abas.py` — nenhuma pele a formata por conta;
- uma aba que entre no painel sem entrar em `abas.ABAS` falha.

**Testes.** `tests/test_ui_faixa_e_rodape.py`, 8 casos: `test_sao_sete_e_nao_seis`;
`test_o_corte_entre_os_dois_niveis_e_declarado`; `test_nenhum_nome_se_repete`;
`test_a_contagem_no_rotulo_e_de_abas_e_de_mais_ninguem`;
`test_a_faixa_de_abas_e_legivel_no_cromo_escuro`; `test_a_aba_ativa_se_separa_por_dois_canais`;
`test_o_rodape_existe_em_toda_pele`; `test_o_cancelamento_esta_alcancavel_em_toda_pele`. Em
`test_ui_troca_de_pele.py`, mais dois: `test_as_sete_abas_existem_em_toda_pele` e
`test_a_faixa_de_abas_muda_de_peso_e_nao_de_conteudo`. E em `test_ui_abas.py`, o novo
`test_a_janela_monta_as_abas_declaradas_na_ordem_declarada`.

**O que custou.** `app_tkinter.py` foi de 1.862 para 1.865 linhas — três, e os sete rótulos não
custaram nenhuma: eles já estavam escritos, e o que a S-226 fez foi movê-los para `ui/abas.py`.

---

# Fase 34 — A pele "Fita" (Imagem 2)

> Grupos nomeados, ícone grande com rótulo embaixo. É a proposta mais fácil de desenhar e a mais
> fácil de errar, porque ela custa altura — e altura foi o defeito da S-151.

## S-227 · A fita de grupos nomeados, gerada do catálogo ✅ implementada (2026-08-24)

**Problema.** A Imagem 2 mostra quatro grupos com cabeçalho — Arquivo, OCR, Edição, Visualização —
e 13 comandos distribuídos entre eles. Quando esta spec foi escrita não existia agrupamento
declarado em lugar nenhum: as duas barras do PDF eram duas listas planas, e o único agrupamento
que existia era o separador visual de `menu.py:113`, que só o menu conhecia. **A S-324 declarou os
seis grupos, e esta é a primeira pele que os desenha.**

**Solução.** A fita é uma sequência de `GrupoDeFita`, cada um gerado dos comandos do catálogo com
aquele `grupo`. O cabeçalho é o rótulo do grupo; o corpo, os comandos em ordem de declaração.

**A fita mostra quem tem ícone, e a regra não é arbitrária.** Um botão de fita é ícone **com**
rótulo (S-228); um comando sem ícone não tem como ser um. Os catorze da S-220 caem exatamente nos
quatro grupos da imagem:

| grupo | na fita | fora |
|---|---:|---|
| Arquivo | 2 | abrir recente, abrir no leitor, cancelar exportação, sair |
| Edição | 5 | salvar todos, próximo da fila |
| Visualização | 4 | página anterior/próxima, marcar, tirar/devolver caixa, roda, aparência |
| OCR | 3 | — |
| Acervo | **0** | os seis: varrer, recarregar, treinar e os três de conjunto de campo |
| Ajuda | **0** | os três |

ACERVO e AJUDA ficam vazios e **não desenham cabeçalho** — um título solto é pior que a ausência
dele: promete um grupo e entrega uma faixa em branco. Os vinte e dois comandos de fora continuam
alcançáveis pelo menu, e há teste cobrando isso: nenhum comando some sem destino.

**O grupo é a unidade de quebra, e a fita não escreve uma segunda implementação.** `ui/barra.py`
quebra por item e afirma que *nenhum item é descartado*; a fita usa a **mesma** `BarraFluida`, com
os grupos como itens. Um grupo partido ao meio não é um grupo, e como os itens **são** os grupos,
não há onde partir um — a regra deixa de precisar de guarda e vira consequência da forma, como o
separador da S-223.

**O `ttk.Button` não aceita `wraplength`, e isso mudou o desenho.** Sem quebra de linha, "Apagar a
peça da casa selecionada" vira um botão de 230 px e a fita inteira pede mais de 2.000 — ela
nasceria em duas linhas em qualquer tela, o que a derrota antes de a S-228 chegar. `wraplength` é
opção de `tk.Button` e de `Label`, não de `ttk.Button`, então quem reparte é `fita.quebrar_rotulo`,
que é pura e tem teste. **Nenhuma palavra é encurtada** (achado 1 do roadmap): as mesmas, noutra
quebra, em até duas linhas equilibradas. Medido: a fita cabe em **uma** linha a partir de 1.400 px,
e a 1.100 são duas — que é a largura em que a S-228 vai precisar do modo compacto.

> ## O achado: o primeiro item de toda `BarraFluida` estava invisível
>
> Fotografar a fita para conferir o desenho mostrou o grupo **Arquivo em branco** — os dois botões
> existiam, estavam mapeados e tinham posição, e não apareciam. A causa é do `pack`, e vale para
> toda barra do programa:
>
> `pack(in_=outro)` muda **quem arruma** o widget, e não **quem é o pai** dele. As molduras de
> linha da `BarraFluida` continuam sendo **irmãs** dos itens, e entre irmãos quem foi criado
> depois desenha por cima. A primeira moldura nasce dentro do primeiro `adicionar` — isto é,
> **depois** do item de índice 0 e **antes** de todos os outros. Ela cobria exatamente um item: o
> primeiro.
>
> **Isso vale desde a S-151, e a janela clássica tem dois casos:** "Abrir PDF" na barra do livro e
> "Página anterior" na barra da vista, invisíveis. O teste da S-151 afirma que *nenhum item é
> descartado* — e ele estava certo: nenhum era descartado do **arranjo**. Ninguém tinha olhado o
> empilhamento.
>
> O conserto é uma linha (`item.lift()` depois do `pack`) e tem regressão própria em
> `test_ui_barra.py`: nenhum item pode ficar atrás de uma moldura de linha, medido pela ordem de
> `winfo_children`, que é a ordem de empilhamento. **A pele clássica ganhou dois botões que
> deviam estar lá desde sempre** — é a única mudança visível dela em toda a Fase 32 a 34, e é
> correção, não aparência.

**Critério de aceite.**

- os grupos e a ordem dentro deles saem do catálogo; acrescentar comando **com ícone** o faz
  aparecer na fita, sem tocar na montagem;
- a quebra é sempre entre grupos, nunca dentro de um — garantido pela forma: os itens da barra
  são os grupos;
- em nenhuma largura um grupo é descartado — a propriedade da S-151, aplicada a grupos, medida de
  120 a 1.700 px;
- grupo vazio não desenha cabeçalho;
- a fita usa `ui/barra.arranjo` (via `BarraFluida`), e não uma segunda implementação de quebra;
- o rótulo quebra sem perder palavra, em até duas linhas equilibradas;
- o que a fita não mostra, o menu alcança.

**Testes.** `tests/test_ui_fita.py`, 16 casos. Puros: `test_a_fita_sai_do_catalogo`;
`test_os_quatro_grupos_sao_os_da_imagem`; `test_grupo_vazio_nao_desenha_cabecalho`;
`test_o_que_a_fita_nao_mostra_o_menu_alcanca`; `test_o_cabecalho_e_o_rotulo_do_grupo`;
`test_o_rotulo_quebra_sem_perder_palavra`; `test_uma_palavra_so_nao_quebra`;
`test_a_quebra_equilibra_as_duas_linhas`; `test_todo_comando_da_fita_tem_traco_desenhado`. Com
janela: `test_a_fita_usa_a_barra_e_nao_uma_segunda_quebra`; `test_a_quebra_e_sempre_entre_grupos`;
`test_nenhum_grupo_e_descartado`; `test_a_fita_recusa_comando_sem_funcao`;
`test_cada_grupo_traz_o_cabecalho_e_os_botoes`; `test_clicar_no_botao_chama_o_comando`;
`test_a_fita_esta_registrada_como_pele`. E em `test_ui_barra.py`, a regressão do achado:
`test_nenhum_item_fica_atras_da_moldura_de_linha`.

**O que custou.** `app_tkinter.py` foi de 1.865 para 1.868 linhas: o `import` e o `elif` que manda
montar a fita na mesma faixa em que a "Foco" monta a fila. **É a medida do que as S-324 a S-222
compraram** — a primeira pele custou dezesseis linhas na janela; a terceira custou três.

---

## S-228 · Ícone grande com rótulo, e o orçamento de altura que ele respeita ✅ implementada (2026-08-25)

> Esta seção foi escrita pela sessão da SPEC_APARENCIA lendo o que a implementação deixou no
> disco, e não por quem a fez. Cada número abaixo foi **medido aqui** antes de ser escrito; onde a
> razão de uma escolha está no docstring do módulo, ela é citada como tal.

**Problema.** A S-151 mediu o defeito que esta pele arrisca recriar: cinco barras empilhadas =
~200 px, **20% da altura da janela**, sobre o painel cuja única razão de existir é mostrar a página
grande. A fita da Imagem 2 — cabeçalho de grupo, ícone grande, rótulo embaixo — volta pela porta da
frente.

E a fita é pior que a barra num aspecto: **ela não quebra barato**. Quebrar uma barra custa ~28 px;
quebrar uma fita custa outra linha de fita.

**Solução.** Um orçamento em pixel, declarado em `fita.ORCAMENTO`, e dois modos:

| modo | ícone | rótulo | cabeçalho | orçamento | **medido** |
|---|---:|---|---|---:|---:|
| pleno | 32 px | 2 linhas, embaixo | à vista | ≤ 120 px | **99 px** |
| compacto | 20 px | 2 linhas, ao lado | vira dica | ≤ 64 px | **44 px** |

**A linha do compacto diverge do que esta spec escreveu, e o achado abaixo é a razão.** O texto
original pedia rótulo em **uma** linha; medido, isso deixa a fita mais larga e não mais estreita.
As outras três decisões do modo — ícone de 20 px, rótulo ao lado, cabeçalho na dica — ficaram como
escritas, e são elas que entregam os 44 px.

Os dois orçamentos não são gosto: 120 px é 12% de uma janela de 1000 de altura — abaixo dos 20% que
a S-151 chamou de defeito, e acima dos ~56 px das duas barras de hoje, que é o que a fita custa a
mais em troca de legibilidade. 64 px é o que cabe sem a fita competir com a página num 1366×768.

**A altura é função pura, e é isso que faz o orçamento existir.** `altura_da_fita(modo, *,
linha_de_texto, linha_de_apoio, densidade)` recebe o `linespace` das fontes de `CORPO` e
`AUXILIAR` — o que o Tk reporta — e devolve o número. Quem lê as fontes do Tk é `altura_atual`;
quem as passa à mão é o teste, e é assim que o orçamento se afirma em 9, 10 e 12 pt **sem trocar a
fonte do Windows**. Nada de `winfo_height` no critério: um orçamento medido no widget montado só
falha depois de a janela estar errada, e numa largura que o teste por acaso tenha escolhido.

Modo e densidade desconhecidos levantam `KeyError`, como `tokens.cor` — um modo escrito errado que
caísse no pleno devolveria um número plausível para o orçamento errado.

**Três constantes do `ttk.Button` são medidas, e não estimativas.** O docstring delas registra o
método: montar o botão e ler `winfo_reqheight` nos três tamanhos de ícone (20, 24 e 32) e nas duas
contagens de linha, com o tema padrão. A conta fecha exata nas seis combinações — e é por isso que
`altura_da_fita` pode prometer **2 px** de tolerância contra o widget montado, em vez de "mais ou
menos".

> ## O achado da S-228: "rótulo ao lado" é **mais largo**, e não mais estreito
>
> A intuição da tabela é que uma linha de texto ocupa menos que duas. Ela ocupa menos **altura** e
> muito mais **largura** — e a fita paga em largura, porque largura vira linha de fita, e linha de
> fita vira altura. Medido com os 17 comandos com ícone, na fonte padrão do sistema:
>
> | forma | largura de uma linha | linhas em 1366 | altura em 1366 |
> |---|---:|---:|---:|
> | pleno: ícone 32 em cima, rótulo em 2 linhas, cabeçalho | 1.375 px | 2 | 200 px |
> | compacto com o rótulo em **uma** linha, como a spec pedia | 2.317 px | **3** | 106 px |
> | compacto com o rótulo em **duas** linhas, como ficou | 1.726 px | 2 | **90 px** |
>
> Seguir a spec ao pé da letra daria um modo compacto que pede **três** linhas de fita na tela em
> que ele foi inventado para servir — e que custaria mais altura que o modo que ele substitui.
> `LINHAS_DO_ROTULO` continua sendo um número só, e não um por modo, porque a medição não deixou
> os dois modos divergirem: o docstring dele carrega a tabela acima.
>
> **E o compacto é mais largo que o pleno mesmo com a quebra em duas linhas** — 1.726 contra 1.375.
> Não é anomalia, é a forma: o rótulo sai de baixo do ícone e vai para o lado dele, e **o que era
> altura vira largura**. O modo compacto compra altura e paga em largura. Dito assim, manter as
> duas linhas deixa de parecer detalhe de implementação e vira a única saída — e é a frase que
> impede alguém de "otimizar" o compacto para uma linha daqui a seis meses.
>
> (Duas sessões mediram estes números por caminhos diferentes e chegaram a 1.357 e 1.708 contra
> 1.375 e 1.726. A diferença são os três vãos de 6 px entre grupos, que uma das contas somou e a
> outra não; a ordem de grandeza e a conclusão são as mesmas. Quem for remedir: `winfo_children()`
> da barra traz as molduras **de linha** junto com as de grupo, e depois do `lift()` da S-227 elas
> vêm primeiro — filtre por ter filhos, como faz o `_molduras` do `test_ui_fita.py`.)
>
> **O critério de 1366 muda de redação e não de sentido.** Ele pede que a fita entre em compacto
> *antes* de precisar de segunda linha, e é o que acontece — o limiar é a largura que a fita plena
> precisa para caber em uma, lida do próprio widget. O que a spec supunha **de passagem** era que o
> compacto coubesse numa linha ali; isso não sobrevive a 17 comandos sem encurtar rótulo, e
> encurtar rótulo é o que o achado 1 do roadmap proíbe. O teste mudou de nome junto —
> `test_em_1366_a_fita_fica_compacta_antes_de_dobrar` — e afirma o que é verdade: naquela tela a
> fita fica compacta e custa **90 px** contra os 200 que a plena gastaria, que é o defeito da
> S-151 de volta.

**A histerese, que a spec não previa.** `HISTERESE = 24` px é quanto a janela precisa ter **a mais**
para a fita voltar ao pleno. Sem ela a troca é reversível no mesmo pixel: uma janela arrastada até a
vizinhança do limiar troca de modo a cada pixel de tremor, e cada troca **destrói e recria os
dezessete botões**. Vinte e quatro pixels é mais que o tremor de um arrasto e menos que um botão.

**E a primeira justificativa escrita para ela estava errada**, o que vale registrar porque a
correção veio da medição e não de uma releitura. Ela dizia que sem a histerese há um laço — *"o
compacto pede menos largura, o recipiente encolhe até a largura pedida, e a largura pedida volta a
autorizar o pleno"*. A premissa é falsa: o compacto pede **mais** largura que o pleno, pelo motivo
do achado acima. O laço descrito não existe; a histerese fica pela razão do parágrafo anterior, que
é outra.

**Critério de aceite.**

- `altura_da_fita` é pura e devolve o mesmo que o widget montado mede, com tolerância de 2 px;
- no modo pleno a altura fica ≤ 120 px na fonte padrão e na densidade confortável — **medido: 99**;
- no modo compacto fica ≤ 64 px — **medido: 44**;
- em 1366×768 a fita entra em compacto **antes** de precisar de segunda linha — e ali ela ocupa
  duas linhas de 44 px, contra as duas de 99 que a plena ocuparia (ver o achado acima);
- a troca de modo não descarta comando nenhum, em nenhuma largura.

**Testes.** `tests/test_ui_fita.py` passou de 16 para **30 casos** com esta S. Os do orçamento:
`test_a_altura_e_pura_e_acompanha_a_fonte_do_sistema`; `test_o_orcamento_do_modo_pleno`;
`test_o_orcamento_do_modo_compacto`; `test_o_compacto_e_de_fato_mais_baixo`;
`test_a_densidade_entra_na_conta`; `test_modo_e_densidade_desconhecidos_levantam`;
`test_a_altura_calculada_bate_com_a_medida`. Os da troca: `test_a_fita_larga_fica_plena`;
`test_em_1366_a_fita_fica_compacta_antes_de_dobrar`;
`test_a_troca_acontece_antes_de_precisar_de_segunda_linha`;
`test_nenhuma_largura_descarta_comando`; `test_o_compacto_esconde_o_cabecalho_e_o_poe_na_dica`;
`test_o_compacto_e_mais_estreito_que_o_pleno_nao_seria`;
`test_o_icone_do_compacto_e_menor_e_fica_ao_lado`.

---

## S-229 · Desfazer e refazer, que a fita promete e o programa não tem ✅ implementada (2026-08-25)

> Seção escrita pela sessão da SPEC_APARENCIA lendo o que a implementação deixou no disco. O que
> está afirmado abaixo foi conferido no código e nos testes; as razões de desenho são as que o
> docstring de `ui/historico.py` dá.

**Problema.** A Imagem 2 põe **Desfazer, Refazer e Limpar** no grupo Edição. Quando esta spec foi
escrita, `grep -rn 'undo' src/` devolvia zero linhas de implementação — os únicos acertos eram
comentários, entre eles o de `ui/board_edit.py:167`, que descreve `apply_edits` como *"útil para
desfazer em bloco"*.

Não era descuido da proposta: era a função que faltava. E o registro do que custa não tê-la já
existia neste projeto — a **S-76**, em que um clique sobrescreveu **1.405 diagramas** de trabalho
humano. Uma edição errada no tabuleiro só se desfazia reeditando casa a casa, ou recarregando o
diagrama e perdendo o resto junto.

**Solução.** `ui/historico.py`: uma pilha de **posições** (`placement`, a string de 64 casas), e
não de gestos.

A escolha é o item, e o argumento está no módulo: uma pilha de gestos precisa saber inverter
**cada** operação — pôr, tirar, mover, arrastar, aplicar FEN, aplicar segunda opinião, aplicar
correção de rede, limpar — e cada operação nova precisa lembrar de registrar o seu inverso. É o
tipo de contrato que se cumpre nas sete primeiras e se esquece na oitava, e **o sintoma de esquecer
é um desfazer que devolve uma posição que nunca existiu**. Uma pilha de estados precisa saber uma
coisa: a posição de antes.

O custo de memória não é argumento contra: `placement` é uma string de ~70 bytes, e o teto de
`TETO = 100` estados dá 7 KB. O custo de correção é decisivo a favor.

**Como ficou.** `Historico` é uma classe pura — sem `tkinter`, sem `PIL` — com `registrar`,
`desfazer`, `refazer`, `zerar` e as perguntas `pode_desfazer`/`pode_refazer`/`profundidade`/
`por_refazer`. Dois comportamentos que a spec não pedia e que os testes fixam:

- **posição repetida não entra na pilha.** Registrar a mesma posição duas vezes gastaria um estado
  do teto para não poder desfazer nada — e faria `Ctrl+Z` parecer travado por um clique.
- **nas pontas ele recusa em vez de inventar**: `desfazer` na base devolve `None`, e quem chama
  desabilita o botão em vez de repintar o tabuleiro com o que já estava lá.

`Ctrl+Z` e `Ctrl+Y` entraram em `atalhos.ATALHOS`, que subiu de 11 para **13** — e daí para o menu
Editar, para a legenda e para o catálogo **sem ninguém escrevê-los lá**, que é a propriedade que a
S-161 e a S-324 existem para dar. Há teste com esse nome.

Os três comandos novos ganharam ícone (`ui/icones.py` foi de 14 para **17**) e, por isso, entraram
na fita da S-227 — o grupo Edição passou de 5 para 8 botões sem ninguém tocar em `ui/fita.py`.

**Critério de aceite.**

- desfazer devolve exatamente a posição anterior, para as origens de mudança;
- refazer devolve o que o desfazer tirou, e uma edição nova **descarta** a pilha de refazer;
- trocar de diagrama zera as duas pilhas — desfazer para dentro de outra posição é pior que não
  desfazer;
- a pilha nunca passa de 100 estados;
- **salvar não é desfazível pelo histórico** — gravar em `labels.csv` é outra ação, e confundir as
  duas é como se perderiam 1.405 linhas de novo;
- os botões ficam cinzas quando não há o que desfazer, com dica que diz por quê e traz a tecla —
  a regra da S-165, que achou 13 controles desabiláveis sem tooltip.

**Testes.** `tests/test_ui_historico.py`, **20 casos**, em duas camadas. A pilha, sem janela:
`test_desfazer_devolve_a_posicao_anterior`; `test_refazer_devolve_o_que_o_desfazer_tirou`;
`test_edicao_nova_descarta_o_refazer`; `test_nas_pontas_ele_recusa_em_vez_de_inventar`;
`test_a_posicao_repetida_nao_entra`; `test_o_teto_de_cem_estados`;
`test_zerar_esquece_as_duas_pilhas`; `test_teto_zero_nao_e_pilha`. A ponte com o catálogo:
`test_os_tres_estao_no_grupo_edicao`; `test_ctrl_z_e_ctrl_y_aparecem_sem_ninguem_escreve_los_la`;
`test_limpar_nao_e_apagar_casa`. E o painel: `test_trocar_de_diagrama_zera_o_historico`;
`test_salvar_nao_entra_no_historico`; `test_desfazer_sem_o_que_desfazer_diz_e_nao_estraga`;
`test_limpar_esvazia_as_64_casas`; `test_os_botoes_ficam_cinzas_e_dizem_por_que`;
`test_a_dica_traz_a_tecla`.

---

## S-230 · O conjunto de peças como escolha, e não como pasta cravada ✅ implementada (2026-08-25)

> Seção escrita pela sessão da SPEC_APARENCIA lendo o que a implementação deixou no disco. Os
> testes citados foram rodados antes de escrita: 19 casos, verdes.

**Problema.** `PieceImages` recebia um diretório e o chamador passava sempre o mesmo:
`assets/piece_images/`. Doze PNGs, um conjunto, sem alternativa — e trocá-lo era sobrescrever os
arquivos, o que muda o conjunto de todo mundo e não tem volta.

A Imagem 2 mostra peças fotográficas de um tabuleiro de madeira real. **Isso não entrou**, e a
razão é de produto: o tabuleiro da janela é onde se *corrige* a leitura, casa a casa, contra um
diagrama impresso — sombra, perspectiva e madeira atrapalham exatamente essa comparação. O que
entrou da imagem é a ideia de que **o conjunto é uma escolha**.

**Solução.** `ui/conjuntos.py`, com a mesma forma do registro de peles: `padrao`, `traco` e
`pasta`, com `valida`, `escolhido`, `registrado` e `CVOFF_PIECES` acompanhando `CVOFF_SKIN`. Nada
de `tkinter` nem de `PIL` no módulo — quem abre arquivo é `ui/board_render.PieceImages`.

**O segundo conjunto é derivado, e não uma segunda arte** — e a implementação acertou o lugar da
derivação, que é onde ela podia dar errado:

1. **Engrossa depois de reduzir, e não na fonte.** A paleta de edição e a Galeria desenham as peças
   a 20-24 px, e é a redução que apaga o contorno fino: as seis peças brancas — contorno preto com
   miolo branco — viram manchas parecidas entre si. Engrossar antes seria engrossar a linha no
   tamanho original e perdê-la de novo na mesma redução. `engrossar_traco` é aplicado ao `resized`.
2. **Dilata a máscara de traço, e não o alfa.** Crescer a região opaca engordaria a silhueta
   inteira e transformaria o peão branco numa mancha — que é o defeito que o conjunto veio
   consertar. A máscara sai de uma luminância (`LIMIAR_DE_TRACO = 160`, e não 128, porque a
   antialiasing da redução produz cinzas intermediários que um limiar no meio da escala deixaria
   de fora, justamente na borda esmaecida).

Doze arquivos novos resolveriam o mesmo e teriam de ser desenhados, versionados e mantidos em par
com os primeiros. É o argumento do achado 6 do ROADMAP_APARENCIA sobre ícone em PNG, aplicado a
peça: **arte de arquivo não sobrevive a uma segunda condição de exibição.**

**O conjunto entra na chave do cache, e não numa segunda instância.** `PieceImages` já era cache
por `(chave, tamanho, fundo)`; virou `(conjunto, chave, tamanho, fundo)`. Trocar de conjunto com
uma segunda `PieceImages` jogaria fora o cache do primeiro — e quem compara dois conjuntos os
**alterna**, que é exatamente o caso em que o cache paga. Por isso `usar_conjunto` não limpa o
cache: voltar ao anterior é instantâneo.

**Pasta incompleta avisa e usa o que houver.** O `warning` nomeia as peças ausentes, e cada uma
cai no símbolo Unicode peça a peça — que é o que `PieceImages.icon` já fazia quando o arquivo
faltava. Recusar a pasta inteira por causa de um arquivo trocaria uma degradação suave por uma
dura. Conjunto do usuário **sem** pasta escolhida também não é erro: é configuração incompleta.

**O estado foi à versão 4**, com `piece_set` e `piece_dir`. Os dois nascem **vazios** e não
`"padrao"`, pela mesma razão de `skin`: o nome do conjunto padrão é de `ui/conjuntos.py`, e cravá-lo
no estado o declararia num segundo lugar. E a pasta é guardada **junto** com o nome, e não em lugar
dele — quem experimenta a pasta própria, volta ao padrão e depois a quer de novo não deve ter de
reencontrá-la no disco. É a decisão de `sash_fraction`, onde "não guardado" e "guardado" são
estados diferentes.

**Critério de aceite.**

- o conjunto padrão é o de hoje, e a pele clássica com ele desenha o tabuleiro **idêntico** ao
  atual — verdadeiro por construção: `padrao` tem `engrossa=False` e nenhuma transformação roda;
- o conjunto é eixo próprio: qualquer conjunto vale com qualquer pele;
- pasta com arquivo faltando registra `warning` nomeando as ausentes, e desenha o resto;
- o cache não confunde conjuntos: a mesma peça, no mesmo tamanho, em dois conjuntos, são duas
  imagens que convivem;
- o conjunto escolhido sobrevive a fechar e reabrir, e um estado de versão anterior abre no padrão.

**Testes.** `tests/test_ui_conjuntos.py`, **19 casos**. O registro:
`test_o_padrao_e_o_primeiro_e_nao_engrossa_nem_e_do_usuario`; `test_todo_conjunto_tem_rotulo_legivel`;
`test_nome_invalido_cai_no_padrao_e_diz_qual_era`; `test_o_vazio_nao_reclama`;
`test_o_ambiente_ganha_do_guardado`; `test_registrado_levanta_e_valida_nao`;
`test_as_doze_pecas_sao_as_do_repositorio`; `test_pasta_incompleta_nomeia_o_que_falta`;
`test_a_pasta_de_verdade_esta_completa`. Os eixos e o disco:
`test_conjunto_e_pele_sao_eixos_independentes`; `test_qualquer_combinacao_de_pele_e_conjunto_vale`;
`test_o_conjunto_e_a_pasta_vao_e_voltam_do_disco`; `test_estado_de_versao_anterior_abre_no_padrao`.
E o desenho: `test_o_conjunto_padrao_e_o_de_hoje`; `test_o_cache_separa_conjuntos`;
`test_o_traco_grosso_e_mesmo_mais_grosso`; `test_pasta_incompleta_avisa_e_desenha_o_resto`;
`test_conjunto_do_usuario_sem_pasta_nao_levanta`;
`test_conjunto_invalido_na_construcao_cai_no_padrao`.

---

# Fase 35 — O que as três peles ganham juntas

> Os quatro itens que só fazem sentido depois de existir mais de uma pele. Dois deles são o preço
> de ter três; dois são o troco.

## S-231 · A paleta de comandos, que sai de graça do catálogo ✅ implementada (2026-08-25)

**Problema.** A pele "Foco" tira 23 controles da tela e os põe no menu. Cinco menus com 27 itens já
é um mapa que se decora; 50 itens é um mapa em que se procura — e procurar comando em menu é o
gesto que a S-161 descreveu ao contrário: *"o que não era botão não existia"* vira "o que não está
no menu que eu abri, eu não acho".

**Solução.** `Ctrl+Shift+P`: um campo, uma lista filtrada, Enter executa. `ui/paleta_de_comandos.py`,
com a metade que decide separada da que desenha — `filtrar` é `(consulta, entradas) → entradas`,
sem `tkinter` e sem estado.

**O item foi barato, e a medida disso é a janela:** `app_tkinter.py` cresceu **onze linhas** —
o `import`, a entrada em `_comandos` e o método que abre a paleta passando o mesmo mapa que o menu
e os atalhos já recebem. Nada aqui declara comando: o catálogo da S-324 é a lista, e a paleta o
percorre por `comandos.GRUPOS`.

**O nome do módulo é longo porque `paleta` já era duas coisas** — a paleta de peças do editor e
`tokens.paleta`, a de cores. É a mesma disciplina que fez `ui/menu.py` apelidar o próprio import.

### As três decisões que a implementação teve de tomar, e a medida de cada uma

**1 · A ordem, e os três degraus que só se acertam medindo.** A spec pedia *"casamento por
subsequência, com o comando de atalho subindo"*, e a ordem entre as metades é o item inteiro. A
chave ficou: **vão** do casamento; início; casou no rótulo antes de casou no grupo; habilitado
antes de cinza; tem tecla; ordem do catálogo. As três tentativas anteriores, e o caso que derrubou
cada uma:

- **a tecla acima da qualidade do casamento inverte o resultado.** `"l"` casa em início 0 e vão 0
  em "Ler esta página" (`Ctrl+R`) e em "Limpar o tabuleiro" (sem tecla) — é aí que ela decide, e
  decide bem. Posta acima do vão, ela traria "Ajustar à largura" (`Ctrl+0`, que casa no `l` da
  décima letra) na frente das duas.
- **"casou no rótulo" acima do vão também inverte.** Medido no catálogo de hoje: `"ocr"` casa no
  *rótulo* de "Devolver as caixas tiradas desta página" — o…c…r espalhado por 26 letras — e no
  *grupo* de "Ler esta página", cravado em três. Com o rótulo acima do vão, a primeira subia.
- **E vale o melhor dos dois casamentos, nunca "o rótulo se ele casar"** — corrigido durante a
  S-234, quando o catálogo cresceu e o caso apareceu: "Folha da página aberta" **é** do grupo OCR,
  e o rótulo dela casa `"ocr"` espalhado por dezoito letras. Preferindo o rótulo por existir, ela
  ia para trás de um comando que não é do grupo. É por isso que a regra é "o melhor", e "casou no
  rótulo" é só o desempate entre dois igualmente apertados.
- **"desabilitado sempre no fim" é a leitura literal de "Enter executa o primeiro", e ela custa o
  item vizinho.** Com ela, `"anotar"` trazia "Desfazer a última mudança no tabuleiro" — a…n…o…t…a…r
  espalhado pela frase — **acima** de "Anotar página", que é a resposta à pergunta. A linha cinza
  existe para ser **achada** e dizer por quê; enterrá-la sob casamento ruim desfaz isso. Ela desce
  **entre iguais** (`"tirar"` → "Tirar a caixa" antes de "Tirar o selecionado"), e quem garante
  que nada dispare por engano é o Enter, que sobre linha cinza não faz nada e não fecha.

**O grupo casa por trecho contíguo, e o rótulo por subsequência.** Não é inconsistência: o rótulo é
frase e o grupo é palavra, e uma palavra curta casa qualquer coisa por subsequência. Medido: `"sal"`
é subsequência de "visualizacao" — o *s*, o *a* e o *l* —, e a régua única trazia os catorze
comandos daquele grupo atrás de "Salvar a posição". Por trecho, `"ocr"`, `"arquivo"` e `"edicao"`
continuam achando o grupo, que é o que alguém digita quando quer o grupo.

**2 · O motivo é o estado, e não um campo ao lado.** O critério de aceite pede que o comando
desabilitado apareça *"cinza e com o motivo, e não some"*. `Entrada.habilitado` é `not motivo`:
não há como construir uma linha cinza e muda. É a mesma forma de `comandos.fila_de_destaque`, que
devolve grupos para que não haja onde pôr um separador sobrando.

**3 · Nem todo comando não-executável é falta de amarração**, e chamar os cinco de "indisponível"
seria a paleta mentindo sobre a janela. Os motivos saem de **declaração alheia**, e nenhuma lista
é reescrita no módulo:

| comando | motivo | quem declara |
|---|---|---|
| `abrir_recente`, `aparencia` | é um submenu: a escolha está na barra de menus | `menu.MENUS`, pelo `tipo` do item |
| os três de anotação | fica na linha de conjunto de campo, junto da página exibida | `comandos.NA_LINHA_DE_CAMPO` (S-77) |
| qualquer outro não amarrado | esta janela não amarra este comando a nenhuma função | o próprio mapa de `_comandos` |

`aparencia` é o caso que obriga o motivo declarado a **ganhar** da amarração: ela tem função ligada
e mesmo assim não é executável daqui — disparada fora do gesto do `radiobutton`, reaplica a pele
que já vale. Mostrá-la preta seria prometer um clique que não faz nada, que é o defeito que
`menu.montar` recusa desde a S-161, na outra ponta.

**O que ficou registrado e não entrou.** A paleta **não** conta para o inventário da S-233. Se
contasse, o teste de lá passaria por construção: ela cobre o catálogo inteiro por definição, e
"todo comando alcançável" viraria uma tautologia em vez de uma medição. A paleta é atalho para
quem sabe o nome; o mapa de quem procura é o menu.

**Critério de aceite.**

- ✅ o filtro é puro e testado sem janela — consulta vazia devolve tudo, em ordem de grupo, e há
  varredura por `ast` afirmando que nenhuma função pura do módulo alcança `tk` ou `ttk`;
- ✅ comando desabilitado aparece cinza (`tag_configure` com `TEXTO_SECUNDARIO`) e com o motivo na
  coluna do rótulo, e não some — a lista tem sempre as 40 linhas do catálogo;
- ✅ Enter executa o primeiro; setas navegam sem dar a volta na ponta; Esc fecha sem executar.
  **Com a exceção medida acima:** quando o primeiro é uma linha cinza, o Enter não faz nada e não
  fecha — o critério que importa é que nada dispare por engano, e não que a primeira linha seja
  sempre executável ao preço de esconder a resposta;
- ✅ a paleta existe nas três peles: a barra de menus é uma declaração só, e `bind_shortcuts` não
  sabe qual pele está valendo;
- ✅ `Ctrl+Shift+P` entra em `atalhos.ATALHOS` — que passa a ter **catorze** teclas —, e daí para a
  legenda e o acelerador do menu Ajuda de graça. `<Control-P>` e não `<Control-Shift-p>`, pela
  mesma razão do `Ctrl+Shift+S` da S-20: é a maiúscula que o Tk entrega no Windows.

**Como a janela é testada sem dirigir o Tk.** A S-117 já registrou que `event_generate` numa suíte
mede o roteamento de evento do Tk, e não a decisão: sem foco de verdade a tecla não chega, e com
`focus_force` o teste passa a depender do gerenciador de janelas. Então `executar`, `mover` e
`fechar` são públicos e chamados direto, e o que sobra — que a tecla chega neles — é uma pergunta
própria, `ligada("<Return>")`.

**Testes.** `tests/test_ui_paleta_de_comandos.py`, **31 casos**. O filtro, sem janela:
`test_o_filtro_e_puro`; `test_o_filtro_nao_toca_tkinter`;
`test_consulta_vazia_devolve_tudo_em_ordem_de_grupo`; `test_a_paleta_cobre_o_catalogo_inteiro`;
`test_o_acento_nao_e_cobrado_de_quem_digita`; `test_o_espaco_da_consulta_nao_precisa_casar`;
`test_o_casamento_e_por_subsequencia_e_nao_por_prefixo`;
`test_o_vao_ordena_antes_do_rotulo_e_o_ocr_e_a_medida`; `test_a_tecla_desempata_e_so_desempata`;
`test_o_grupo_casa_por_trecho_e_nao_por_subsequencia`;
`test_comando_desabilitado_aparece_com_motivo`; `test_o_motivo_declarado_ganha_da_amarracao`;
`test_os_motivos_declarados_saem_de_declaracao_alheia`;
`test_a_linha_cinza_desce_so_no_empate_e_o_anotar_e_a_medida`;
`test_consulta_que_nao_acha_nada_devolve_vazio_e_nao_tudo`. As portas:
`test_a_paleta_existe_nas_tres_peles`; `test_a_tecla_e_ctrl_shift_p_e_a_maiuscula`;
`test_a_paleta_esta_no_catalogo_e_no_menu_ajuda`; `test_a_paleta_nao_entra_na_fila_de_destaque`.
E a janela: `test_a_janela_desenha_o_que_o_filtro_devolve`;
`test_a_linha_cinza_leva_a_marca_e_o_motivo_na_coluna`;
`test_a_coluna_da_direita_e_o_grupo_e_a_do_meio_e_a_tecla`;
`test_as_teclas_da_paleta_estao_ligadas_no_campo`; `test_enter_executa_o_primeiro`;
`test_a_paleta_fecha_ao_executar`; `test_as_setas_navegam_e_o_enter_executa_o_selecionado`;
`test_a_seta_nao_passa_da_ponta`; `test_esc_fecha_sem_executar`;
`test_enter_sobre_linha_cinza_nao_faz_nada_e_nao_fecha`;
`test_consulta_sem_resultado_nao_tem_selecao_e_o_enter_nao_estoura`;
`test_abrir_duas_vezes_traz_a_mesma_janela`.

---

## S-232 · Densidade: compacta ou confortável ✅ implementada (2026-08-25)

**Problema.** A S-151 mediu o defeito em **1100×760**, e a solução dela — quebrar em vez de cortar
— resolve o descarte mas não o aperto: em 1366×768, que é a tela de notebook mais comum, as duas
barras quebram em quatro linhas e a página fica com o que sobrar. A fita da S-228 piora isso, e por
isso já nasce com um modo compacto — mas o modo compacto é decisão da fita, não da janela.

**Solução.** Densidade como eixo da janela, com dois valores, derivada de `ui/tipografia.py` — que
já escala pela fonte do sistema (`theme.fonte_base`), e é por isso que uma escala de números fixos
não serviria aqui.

### O espaço virou dado, e ele já estava escrito

`tipografia.FOLGAS` declara quatro papéis de espaço, e os quatro valores **são os números que já
estavam na janela**: 14 é o `padding` da legenda de atalhos, 10 e 6 são o `padx`/`pady` da faixa de
cromo, 2 é o `padx` entre dois botões de fita que a S-228 mediu. `ALTURA_DE_LINHA_NA_BASE = 20` é a
altura de linha de fábrica do `Treeview`, medida.

**É o que torna "na densidade confortável nada muda" verdadeiro por construção**, e não por
coincidência: a confortável não *parece* a janela de hoje, ela **é** — o mesmo movimento que a
S-324 fez com os rótulos, virar dado sem virar outro texto. `folga(FOLGA, base=9)` devolve 10
porque 10 é o que estava lá.

| densidade | espaçamento | altura de linha de tabela | ícone da fita |
|---|---|---|---|
| confortável | ×1,0 (14 / 10 / 6 / 2) | `linespace + 5` = 20 | 32 px (modo pleno) |
| compacta | ×0,7 (10 / 7 / 4 / 1) | `×0,8`, com piso | 20 px (modo compacto) |

**Dois fatores e não um, e a diferença é o conteúdo.** Espaço vazio encolhe até sumir sem custo;
altura de linha carrega texto, e abaixo do `linespace` ela corta a perna do `g`. Daí `0,8` contra
`0,7`, e daí os dois pisos: `folga` nunca desce de **1 px** — dois vizinhos colados viram um
controle só para o olho — e `altura_de_linha` nunca desce de `linespace + 1`.

**O piso da altura de linha não é teórico: ele já morde na fonte 12.** Com `linespace` 20 a
compacta calcula 20 e o piso responde 21. Ou seja, **da fonte 12 para cima a densidade compacta
deixa de encolher a tabela**, porque não há o que encolher sem cortar letra. É a resposta certa, e
fica dita aqui em vez de virar um relato de "a compacta não faz nada nesta máquina".

### A pele sugere, a pessoa decide — e o vazio é o que guarda a diferença

`pele.densidade_em_vigor(pele, guardada)` resolve na ordem `CVOFF_DENSITY` → escolha guardada →
sugestão da pele. A fita passa a sugerir **compacta** (é a pele que gasta ~99 px de altura por
linha de cromo, contra ~28 de uma barra); a clássica e a "Foco" sugerem confortável.

**`AppState.densidade` nasce vazio, e o vazio carrega o item inteiro:** ele é a diferença entre
*não decidi* e *decidi o que a pele sugeria*. Quem nunca abriu o menu recebe a sugestão de cada
pele ao trocar; quem escolheu confortável continua confortável **também na fita**, que sugere o
contrário. Cravar `"confortavel"` no estado apagaria essa diferença no primeiro salvamento — é a
mesma decisão de `skin` e `piece_set`, com uma consequência a mais.

**Inválida e não escolhida caem em lugares diferentes.** Não escolhida cai na sugestão da pele.
Inválida cai em `confortavel` com um `warning` que a nomeia, que é o que a tabela de degradação da
S-234 declara — quem escreveu um nome errado não pediu nada apertado.

### Duas decisões que a implementação teve de tomar

**1 · A densidade compacta crava o modo compacto da fita, e não inventa um terceiro ícone.** A
tabela deste item pede 20 px na compacta, e o modo compacto da S-228 **é** o ícone de 20. O que
muda é quem decide: o modo sai da largura disponível, a densidade sai da pessoa, e quando ela pede
compacta a largura deixa de ter voto — senão um monitor largo devolveria o ícone de 32 px a quem
acabou de pedir o de 20.

**2 · O caminho ficou `Ver ▸ Densidade`, e não `Ver ▸ Aparência ▸ Densidade`.** A spec escreveu o
segundo; aninhar custaria a disciplina que vale mais. Neste programa toda linha de menu é um `Item`
de `menu.MENUS`, contável por `acoes_declaradas` — que é de onde a **S-233** vai tirar o inventário
de alcance. Um comando montado por dentro do submenu de outro não aparece em lista nenhuma, e a
S-233 mediria um catálogo com um buraco. Os dois eixos ficam irmãos no menu Ver, e `_submenu_de_escolha`
é um montador só para os dois: peles e densidades são a mesma linha de menu com outra lista atrás.

### O que foi medido em 1366×768, e o que a medição refutou

**A metade "a fita cabe em uma linha" é falsa, e a S-228 já dizia por quê.** O modo compacto pede
**1.726 px** de largura — *mais* que os 1.375 do pleno, porque o rótulo sai de baixo do ícone e vai
para o lado dele. Em 1366 a fita quebra em duas linhas nos dois modos. Não é uma falha desta
implementação: é uma premissa que já estava refutada quando o critério foi escrito.

A metade que importa acontece. Medido com a fonte de referência, em 768 de altura:

    fita                  altura     documento
    plena, 2 linhas       198 px     61,7%
    compacta, 2 linhas     88 px     76,0%
    ganho                 110 px     +14,3 pontos

Os 60% são atendidos nos dois — e **o confortável passa por 1,7 ponto**, a uma linha de cromo de
reprovar. O que a compacta devolve ao documento são 110 px.

`geometria.fracao_do_documento` é pura, e a razão é a de `fita.altura_da_fita`: um orçamento medido
no widget montado só falha depois de a janela já estar errada, numa largura que o teste por acaso
escolheu. **O que ela não modela está declarado no docstring** — as barras do próprio painel de PDF
e a linha de conjunto de campo entram por `CHROME_VERTICAL`, que é estimativa; a fração devolvida é
um **teto**.

**Critério de aceite.**

- ✅ a densidade deriva da fonte do sistema: os quatro papéis de folga e a altura de linha sobem
  todos de base 9 para base 12, nas duas densidades;
- ◐ **nenhum espaçamento é escrito fora de `ui/tipografia.py`** — verdadeiro para o espaçamento que
  a densidade controla (a faixa de cromo da janela, os dois vãos da fita e a altura de linha do
  `Treeview`), e **falso como afirmação global**: os `padx`/`pady` dos painéis continuam literais.
  Movê-los todos é a decomposição do `ROADMAP_UI`, e não cabia aqui; fica registrado como dívida em
  vez de virar um ✅ que ninguém consegue reproduzir;
- ⬜ **em 1366×768 a fita cabe em uma linha** — MEDIDO E REFUTADO, ver acima;
- ✅ em 1366×768, densidade compacta, o painel do PDF fica com **76,0%** da altura (≥ 60%);
- ✅ a escolha explícita sobrepõe a sugestão da pele, e sobrevive à troca de pele — afirmado na
  resolução pura e na janela, com os métodos reais de `remontar_cromo`;
- ✅ na densidade confortável com a pele clássica, nada muda em relação a hoje: os quatro valores de
  folga e a altura de linha na base de referência são exatamente os de antes.

**Testes.** `tests/test_ui_densidade.py`, **22 casos**. A escala:
`test_a_densidade_deriva_da_fonte_do_sistema`;
`test_a_compacta_e_menor_que_a_confortavel_nos_dois_valores`;
`test_a_classica_confortavel_e_identica_a_hoje`; `test_a_folga_nunca_chega_a_zero`;
`test_a_altura_de_linha_nunca_corta_a_letra`; `test_papel_e_densidade_desconhecidos_levantam`.
A sugestão e a escolha: `test_a_fita_sugere_compacta_e_as_outras_confortavel`;
`test_sem_escolha_cada_pele_traz_a_sugestao_dela`; `test_a_escolha_explicita_sobrepoe_a_pele`;
`test_o_ambiente_ganha_da_guardada`; `test_densidade_invalida_cai_na_confortavel_e_diz_qual_era`;
`test_todo_rotulo_de_densidade_e_legivel`; `test_a_densidade_vai_e_volta_do_disco`;
`test_estado_de_versao_anterior_abre_sem_densidade_escolhida`. A fita e o documento:
`test_a_densidade_compacta_crava_o_modo_compacto_da_fita`;
`test_em_1366_compacta_o_pdf_fica_com_60_por_cento`; `test_a_fracao_nunca_e_negativa_nem_estoura`;
`test_a_fita_continua_dentro_do_orcamento_nas_duas_densidades`. E a janela:
`test_a_altura_de_linha_entra_no_estilo_do_treeview`; `test_o_menu_ver_tem_o_submenu_de_densidade`;
`test_o_submenu_lista_as_densidades_registradas`;
`test_montar_recusa_item_de_densidade_sem_variavel`.

E três em `tests/test_ui_troca_de_pele.py`, com os métodos reais da janela:
`test_sem_escolha_cada_pele_traz_a_densidade_que_ela_sugere`;
`test_a_escolha_de_densidade_sobrevive_a_troca_de_pele`;
`test_escolher_a_densidade_que_a_pele_sugeria_ainda_a_torna_explicita`.

---

## S-233 · Nenhuma pele esconde um comando: o inventário de alcance ✅ implementada (2026-08-25)

**Problema.** É o risco central de todo este plano, e ele não é técnico: **três peles convidam a
resolver rápido só numa delas.** Um comando novo entra na fita porque foi lá que quem o escreveu
estava trabalhando, e some da "Foco" e da clássica — e ninguém descobre até alguém que usa a pele
errada precisar dele. A regra 2 — *pele é apresentação, nunca conjunto menor* — não vale nada sem
uma máquina que a cobre.

**Solução.** `ui/alcance.py`: para cada pele registrada, o conjunto de comandos **alcançáveis**, e
a afirmação de que ele é igual ao catálogo inteiro. `perdidos()` devolve `pele → o que ela perdeu`
e `relato()` transforma isso na mensagem de falha.

### A terceira forma não conta, e é a decisão que faz o módulo medir alguma coisa

"Alcançável" tem três formas: um controle na tela daquela pele, um item de `menu.MENUS`, ou uma
entrada da paleta de comandos (S-231). **A paleta percorre `comandos.CATALOGO`** — incluí-la faria
`alcancaveis(pele) == catálogo` ser verdade por definição, e o teste passaria para sempre sem olhar
para nada.

A prova de que ela está fora não é uma afirmação no docstring: é `test_a_paleta_nao_conta_para_o_inventario`,
que zera as duas formas restantes e cobra que o inventário **acuse as três peles**. Um inventário
que não sabe falhar é uma tautologia com nome de teste.

### O que o inventário encontrou hoje

    catálogo ......................... 41 comandos
    alcançáveis pelo menu ............ 38  (a mesma declaração para as três peles)
    fora do menu ..................... 3   -- exatamente `comandos.NA_LINHA_DE_CAMPO`

    na tela, por pele:   clássica 19   |   "Foco" 7   |   "Fita" 20

**A barra de menus é a rede de segurança da regra 2**, e o número diz por quê: `menu.MENUS` é uma
declaração só, nenhuma montagem de cromo a filtra, e ela sozinha cobre 38 dos 41. É o que permite à
"Foco" tirar 23 controles da tela sem esconder um único comando.

**Os três que sobram são a linha de conjunto de campo**, e ela é de todas as peles — `remontar_cromo`
a refaz em toda troca, e a S-77 a pôs junto da página exibida de propósito. São a única forma 1 que
hoje decide alguma coisa no inventário, e é por isso que `test_a_linha_de_campo_e_a_unica_casa_dos_tres_de_anotacao`
existe: no dia em que um deles ganhar item de menu, ou em que um quarto comando sair do menu, o
número muda e alguém precisa saber.

### Reflexão sobre a declaração, e a única declaração que pode mentir

Nada aqui abre janela. Cada forma tem um dono que já declara o que desenha — `fila.acoes_da_fila`,
`fita.acoes_da_fita`, `menu.acoes_declaradas`, `comandos.NA_LINHA_DE_CAMPO`. Foi preciso acrescentar
**uma**: `comandos.NAS_BARRAS_DO_PDF`, os dezesseis comandos que as duas barras de `ui/pdf_panel.py`
desenham na pele clássica.

**Ela é escrita à mão, e `_montar_barras` também — então elas podem divergir, e a divergência seria
silenciosa *e favorável*:** uma lista maior que a realidade faria o inventário afirmar que a
clássica alcança um comando que ela não desenha. É a mesma família de defeito que a S-324 mediu nos
rótulos, e a resposta é a mesma: `test_a_declaracao_das_barras_bate_com_o_que_o_painel_desenha`
varre aquela função por `ast` e compara os dois conjuntos.

Transformar `_montar_barras` numa tabela — dezesseis botões com `state`, dica e `command`
diferentes — é a decomposição que o `ROADMAP_UI` persegue, e não cabia neste item. **O que cabia
foi declarar a lista onde o inventário possa lê-la, e travar a distância entre as duas.**

**E `na_tela` levanta para montagem de cromo desconhecida**, como `tokens.cor`: um nome escrito
errado que caísse na clássica devolveria um inventário plausível para a pele errada — e um
inventário que erra a pele é pior que nenhum, porque ele passa em verde.

**Critério de aceite.**

- ✅ para cada pele registrada, `alcancaveis(pele) == set(catalogo)` — as três, 41 de 41;
- ✅ a mensagem de falha **nomeia** a pele e os comandos que ela perdeu, e não devolve um booleano:
  `relato` sai como `"classica: comando_x; foco: comando_x"`;
- ✅ acrescentar um comando ao catálogo sem lhe dar casa em alguma pele falha a suíte — simulado
  com um catálogo sintético, e o inventário acusa as três;
- ✅ remover um comando da fita da "Fita" sem lhe dar item de menu falha a suíte — e o teste
  também cobra o outro lado, que é o que mantém a regra 2 aplicável: tirar da fita um comando que
  **tem** menu não é perda, e é assim que a "Foco" esconde 23 controles sem violar nada;
- ✅ o teste não abre janela, e a afirmação é direta: `tk.Tk` e `tk.Toplevel` passam a levantar
  durante a conta. Quem trocar a reflexão por uma varredura de árvore de widgets é avisado.

**Testes.** `tests/test_ui_alcance.py`, **11 casos**. O inventário:
`test_toda_pele_alcanca_o_catalogo_inteiro`; `test_a_falha_nomeia_a_pele_e_o_comando`;
`test_comando_novo_sem_casa_falha`; `test_remover_da_fita_um_comando_sem_item_de_menu_falha`;
`test_a_paleta_nao_conta_para_o_inventario`; `test_montagem_desconhecida_levanta`;
`test_o_relato_e_vazio_quando_nao_ha_falta`. Sem janela: `test_o_inventario_nao_abre_janela`.
A declaração das barras: `test_a_declaracao_das_barras_bate_com_o_que_o_painel_desenha`;
`test_toda_acao_declarada_nas_barras_esta_no_catalogo`;
`test_a_linha_de_campo_e_a_unica_casa_dos_tres_de_anotacao`.

E `alcance.py` entra em `SEM_TKINTER` (S-137), que é a lista dos módulos de `ui/` que decidiram não
importar `tkinter` — sem ela, um módulo novo sem Tk não é vigiado.

---

## S-234 · A pele não derruba a janela: o contrato de degradação nas três ✅ implementada (2026-08-25)

**Problema.** `ui/theme.py:12-15` estabelece o contrato: *"um checkout sem o extra, um bundle que
não o incluiu ou um tema com nome errado não podem impedir o app de abrir — tema é aparência, e
aparência não derruba ferramenta"*. `apply_theme` o cumpre. Esta fase acrescentou quatro eixos —
pele, densidade, ícone, conjunto de peças — e cada eixo é um modo de falha novo, todos na abertura,
que é o pior momento: uma exceção ali não degrada nada, ela apaga o programa antes de ele existir.

**Solução.** `ui/degradacao.py`, com três coisas: o contrato **como dado** (`QUEDAS`), o "registra
uma vez" (`avisar_uma_vez`), e a prova de que as três peles montam (`abrir_cromo_de_prova`).

### As seis quedas, e o que já existia

Quatro das seis já estavam cumpridas quando o item começou — `pele.valida` (S-221),
`pele.densidade_em_vigor` (S-232), `conjuntos.valida` e `PieceImages` (S-230). **O que faltava não
era o comportamento: era a tabela ser dado e o "uma vez" ser verdade.**

| falha | queda | quem cumpre |
|---|---|---|
| pele desconhecida | `classica` | `pele.valida` |
| densidade desconhecida | `confortavel` | `pele.densidade_em_vigor` |
| ícone sem traço | botão só com texto | `icones.imagem` |
| Pillow indisponível ou desenho falho | botão só com texto | `icones.imagem` |
| pasta de peças ausente ou incompleta | símbolo Unicode, peça a peça | `board_render.PieceImages` |
| conjunto de peças desconhecido | conjunto `padrao` | `conjuntos.valida` |

Enquanto o contrato foi prosa em quatro docstrings, "as seis quedas funcionam" era uma frase.
Declarado, ele virou o que `test_as_seis_quedas` percorre — **e `test_toda_queda_declarada_tem_reproducao`
cobra que a tabela e o teste não divirjam**, porque uma linha nova sem caso viraria uma promessa
que ninguém confere.

### O "uma vez" era falso, e a fita é quem o tornava caro

`icones.imagem` registrava o aviso **a cada chamada** — ou seja, uma vez por botão. A fita desenha
dezessete botões e os redesenha a cada troca de pele e a cada mudança de densidade: um nome de
ícone errado escrevia dezessete linhas iguais por remontagem, e um log que se repete assim deixa de
ser lido, que é o mesmo custo de não registrar nada.

`avisar_uma_vez(logger, chave, ...)` resolve, e **duas decisões dele são o item**:

- **o `logger` é do chamador.** Um aviso de ícone que saísse como `ui.degradacao` mandaria quem o
  lê procurar no módulo errado. É a mesma razão de `icones.icone` receber a cor em vez de perguntá-la.
- **a chave carrega o valor, e não só o assunto.** `("icone", "abrir_pdf")` cala o segundo botão
  que pede o mesmo ícone que faltou, e **não** cala um ícone diferente que também falte — o segundo
  nome é informação nova.

Os quatro validadores de valor continuam avisando **por evento** (uma abertura, uma troca de pele),
e isso é o comportamento certo: quem escolhe um valor inválido de novo merece saber de novo. O
"uma vez por widget" era o defeito, e é ele que a guarda fecha.

### O import da Pillow ficou guardado, e o que isso **não** promete

`ui/fila.py` e `ui/fita.py` importam `ui/icones.py`, e um `ImportError` no topo dele apaga o
programa antes de ele existir. O import passou a ser guardado, e o desenho também: cor inválida,
Pillow ausente ou `PhotoImage` recusada caem no botão só com texto, com aviso.

**E fica dito o que isso não promete:** que o programa inteiro abra sem a Pillow.
`ui/board_render.py` a importa sem guarda porque as peças são o **documento** e não cromo — um
tabuleiro que não desenha não é uma janela degradada, é uma janela sem produto. O contrato de
degradação é da aparência, e esta linha é a parte dele que cabe aqui. Registrado como limite, e não
escondido atrás de um ✅.

### O auto-teste passa pelo cromo

`--selftest` já era o roteiro headless que o `CONTRIBUTING` manda usar para dirigir a interface sem
clicar, e ele não passava por widget nenhum. Ganhou um passo final: **uma prova de cromo por pele
registrada**, com o código de saída **5** quando alguma não monta.

`abrir_cromo_de_prova` monta exatamente o que as peles diferem em montar — o tema (que escolhe o
`ttkbootstrap` da pele e a altura de linha da densidade), a faixa de cromo e a barra de menus, numa
`Toplevel` retirada que é destruída no fim. **Não monta os painéis**: eles são conteúdo, e a regra 2
diz que são os mesmos nas três.

**O laço mora em `ui/degradacao.py` e não no auto-teste**, e isso é o que torna a afirmação
testável: `provar_as_peles(root)` recebe a raiz, então a suíte pergunta a mesma coisa com a raiz
compartilhada do processo em vez de criar uma segunda — que é o que `tests/tk_root.py` documenta
como não confiável no Windows.

**Critério de aceite.**

- ✅ cada uma das seis falhas produz a queda descrita, sem levantar — e o teste cobra as três
  coisas juntas: o degrau certo, o aviso, e a ausência de exceção;
- ✅ cada uma registra **uma** vez e não uma por widget: dezessete chamadas ao mesmo ícone que
  falta produzem **uma** linha de log;
- ✅ o `selftest` roda nas três peles e devolve 0 nas três (o passo novo; o auto-teste completo
  continua exigindo checkpoint e PDF, como sempre);
- ✅ com a Pillow presente mas sem `ttkbootstrap`, as três peles abrem em `ttk` puro — medido com
  `sys.modules["ttkbootstrap"] = None`, que é o `ImportError` que um checkout sem o extra dá;
- ✅ nenhum caminho de aparência aparece num `traceback` de abertura, em nenhuma combinação de
  pele, tema e densidade — nove combinações, com o tema recusado por nome inválido em todas.

**Testes.** `tests/test_ui_degradacao.py`, **12 casos**. A tabela:
`test_toda_queda_declarada_tem_reproducao`; `test_as_seis_quedas`;
`test_a_falha_nomeia_o_valor_que_a_causou`; `test_nenhuma_queda_levanta`. O aviso:
`test_o_aviso_sai_uma_vez_so`; `test_um_nome_novo_nao_e_calado`;
`test_esquecer_avisos_devolve_a_voz`. E as três peles: `test_o_selftest_roda_nas_tres_peles`;
`test_cada_pele_monta_o_cromo_dela`;
`test_pele_desconhecida_volta_como_problema_e_nao_como_excecao`;
`test_as_tres_peles_abrem_sem_ttkbootstrap`;
`test_nenhum_caminho_de_aparencia_aparece_num_traceback`.

---

# O que esta spec deliberadamente não faz

Registrado aqui para que a ausência seja decisão e não esquecimento.

**Não muda a interface de hoje.** A pele clássica é o padrão e é intocada. Um item que só pudesse
ser feito mexendo nela está mal escrito, e é assim que "o programa deve ter a opção da interface
atual" deixa de ser uma promessa e vira uma propriedade da suíte.

**Não porta para Qt.** Os dois gatilhos do `ARCHITECTURE.md:163-168` seguem valendo e nenhum
disparou — `labels.csv` está em 3.936 das 10 mil linhas. Três peles em Tk custam ~3 semanas; o
porte custa 3 a 4 e não entrega pele nenhuma.

**Não redesenha as seis abas por dentro.** Resultado, Análise, Revisão, Dataset, Galeria e
Configuração continuam como estão. As peles mudam o cromo em volta delas, e a S-226 garante que
nenhuma some.

**Não traz o tabuleiro fotográfico da Imagem 2.** Sombra e perspectiva atrapalham a comparação casa
a casa contra um diagrama impresso, que é o gesto que o tabuleiro da janela existe para servir. O
que entra é a escolha de conjunto (S-230).

**Não troca rótulo de comando nenhum.** Os textos das duas imagens são ruído de renderização
("Arfiro", "Prónimto diagrama", "Visualicão"), e o vocabulário que vale é o de `ui/strings.py` e
`ui/menu.py`, fixado pela S-166.

**Não amarra tema a pele.** São dois eixos, e `CVOFF_TTK_THEME` já dá 30 temas. Amarrá-los tornaria
combinações legítimas impossíveis sem que ninguém tivesse decidido isso.

**Não faz uma quarta pele "alto contraste".** Ela quase sai de graça depois da S-224 — os limiares
já estão medidos —, mas quase não é de graça, e ninguém pediu. Fica registrada como o próximo
passo barato, se alguém pedir.

---

## S-294 · A guarda de foco cede a tecla, e não o teclado ✅ implementada (2026-08-26)

**Problema.** A S-223 anotou isto por escrito e não consertou, porque não era o que "a fila única de
ações" autorizava:

> A mesma guarda cede **os onze** atalhos dentro de qualquer `Entry`, inclusive `Ctrl+S`, `Ctrl+R` e
> `Ctrl+N`, que campo de texto nenhum usa. O docstring dela só justifica `←`, `→` e `Del`. Digitar
> uma FEN e apertar `Ctrl+S` não salva hoje, e ninguém registrou isso. Fica anotado para um item
> próprio.

São dezoito atalhos hoje, e **nove morriam** com o cursor num campo de texto: `Ctrl+S`,
`Ctrl+Shift+S`, `Ctrl+N`, `Ctrl+P`, `Ctrl+0`, `Ctrl+Enter`, `Ctrl+R`, `Ctrl+F` e `Ctrl+H`. Nenhum
faz coisa alguma dentro de um `Entry`: a tecla sumia, e o usuário concluía que o programa não fazia
aquilo.

**Solução.** A pergunta certa é sobre a **tecla**, e não sobre o widget. `ignores_widget` respondia
*"é campo de texto?"* e, se fosse, cedia tudo; `cede_a_tecla` responde sobre o par (widget, tecla).

| tecla | quem fica com ela num campo |
|---|---|
| `←` `→` `↑` `↓` `Home` `End` `Del` `Backspace` | o campo — cada uma tem comportamento de fábrica ali |
| `Ctrl+Z` `Ctrl+Y` | o campo — é o desfazer do próprio widget |
| `PgUp` `PgDn` | só quem **rola**: num campo de uma linha elas não fazem nada |
| as outras nove | a janela |

**As cedidas são declaradas por ação, e não por sequência.** Só `ui/atalhos.py` escreve tecla neste
projeto — é o que `test_ui_legenda.test_so_a_tabela_escreve_sequencia_de_tecla` cobra —, e a regra é
a certa: remapear `desfazer` lá e esquecer aqui deixaria a guarda cedendo uma tecla que já não é a
do desfazer. Aqui se diz o significado; a tecla sai da tabela.

**O que não muda, e é o que mantém a S-117 e a S-267 de pé.** Tecla que o widget declarou para si
continua dele, por `owns_key` — e é por ali que `Ctrl+R` segue sendo "alinhar à direita" dentro do
editor e `Ctrl+Enter` segue sendo do campo de FEN. A entrada `CEDIDA_PELA_GUARDA` de
`SOBREPOSICOES_NO_EDITOR` continua com o mesmo valor, e o docstring dela passou a dizer **quem**
cede: era o cobertor, agora é a declaração. A diferença aparece se alguém tirar a tecla do editor —
antes ela continuaria morta ali, agora volta a ser da janela.

**Critério de aceite.**

- `Ctrl+S` com o cursor no campo de FEN salva, e o teste o afirma pelo caminho que a janela usa;
- `←` no campo de FEN continua movendo o cursor — o que a guarda existe para proteger desde a S-20;
- nenhuma sequência de tecla é escrita fora de `ui/atalhos.py`;
- toda tecla cedida ou é atalho da janela, ou é tecla de edição declarada — cedida que não existe
  em lugar nenhum é linha morta.

**Testes.** `test_o_ctrl_s_no_campo_de_fen_passa_a_salvar`;
`test_a_seta_no_campo_de_fen_continua_do_campo`; `test_a_rolagem_e_so_de_quem_rola`;
`test_a_tecla_declarada_pelo_widget_continua_dele`;
`test_toda_tecla_cedida_e_um_atalho_da_janela_ou_uma_tecla_de_edicao`.
---

## S-295 · Os quatro contornos que somem na casa em que são desenhados ✅ implementada (2026-08-26)

**Problema.** `REPROVAS_ANTERIORES_A_S224` guardava quatro pares abaixo do piso `AA_GRAFICO` (3,0),
medidos em 2026-08-24 e registrados **como registro e não como perdão**:

    ALVO sobre CASA_ESCURA           1,53
    ALVO sobre CASA_ULTIMO_LANCE     2,99
    PROBLEMA sobre CASA_ESCURA       1,73
    DIVERGENTE sobre CASA_ESCURA     1,86

É a mesma família do defeito que a S-158 mediu e consertou para o `CORRIGIDO` — *"uma borda
desenhada e invisível em metade das casas"* —, em três papéis que ela não olhou. A nota da S-224
dizia que corrigi-los era item próprio, e apontava para a S-257 — que acabou virando outro assunto.
Os quatro continuaram reprovando por dois dias e meio.

**Solução.** A via que a S-158 já tinha aberto: **luminosidade, com matiz e saturação intactas**. É
o mesmo movimento que `tokens.paleta(cromo_escuro=True)` faz para o cromo, e a razão é a mesma —
`PROBLEMA` continua sendo o vermelho de posição ilegal.

| papel | era | é | pior par |
|---|---|---|---|
| `ALVO` | `#3f7f4c` | `#24482b` | 1,53 → **3,27** |
| `PROBLEMA` | `#c0392b` | `#77231b` | 1,73 → **3,27** |
| `DIVERGENTE` | `#8e44ad` | `#5b2c6f` | 1,86 → **3,28** |

O melhor par de cada um foi de ~4 para ~7,5. **Nenhuma matiz se moveu** — 132,2°, 5,6° e 282,3°
continuam onde estavam —, então a regra dos 40° da S-158 sai de graça e nenhuma faixa nova é
disputada. Era essa a objeção registrada: *"mexer no vermelho de posição ilegal é mexer numa cor
que a S-158 escolheu por eliminação de matiz"*. Mexer na **luminosidade** dela não é.

### O conserto desenterrou um papel com dois significados

`texto_panel.PAPEL_DA_FAIXA` pintava a faixa `revisar` da aba Texto com `tokens.PROBLEMA` — que
`tokens.SIGNIFICADO` declara como marcação de **tabuleiro**, contorno de casa. Escurecer o contorno
teria escurecido a letra daquela aba junto, sem que nada tivesse pedido.

É o defeito da S-158 outra vez — *um papel, um significado* —, e a peça que faltava já existia:
`PROBLEMA_TEXTO` nasceu na S-224 exatamente para isso. Na pele clássica os dois valiam o mesmo, e
por isso ninguém tinha notado que a aba usava o papel errado.

Com a troca, **`COINCIDEM_DE_PROPOSITO` ficou vazia**: ela era a exceção que permitia aos dois pares
compartilharem cor na paleta clara, e a S-224 a justificava com *"inventar uma diferença na paleta
clara só para separar os nomes mudaria pixel de hoje sem nenhuma medida pedindo"*. A medida chegou.
No lugar dela entrou uma afirmação mais forte: contorno e letra do mesmo significado **não
compartilham valor em paleta nenhuma**.

**Critério de aceite.**

- `REPROVAS_ANTERIORES_A_S224` está vazio, e com ele vazio o teste da S-224 passa a afirmar que
  nenhum par de marcação reprova em pele nenhuma;
- a matiz de cada papel é a mesma de antes, e a regra dos 40° continua valendo em toda pele;
- nenhum papel de **texto** mudou de valor: os sete pares da S-146 saem intactos;
- a faixa da aba Texto usa papel de texto, e o teste que compara as duas declarações prova.

**Testes.** `test_toda_marcacao_atinge_aa_grafico_em_toda_pele` (a lista vazia);
`test_o_contorno_e_a_letra_do_mesmo_significado_nao_compartilham_valor`;
`test_a_lista_de_papeis_de_faixa_e_a_do_painel`.
