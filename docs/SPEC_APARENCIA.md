# Especificação da aparência — Fases 32 a 35 (S-219 a S-234)

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
> | S-95 a S-142, S-218 | [SPEC_FASE14.md](SPEC_FASE14.md) |
> | S-144 a S-170 | [SPEC_UI.md](SPEC_UI.md) |
> | S-178 a S-217 | [SPEC_TEXTO.md](SPEC_TEXTO.md) |
> | S-219 a S-234 | [SPEC_APARENCIA.md](SPEC_APARENCIA.md) |

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

## S-219 · O catálogo de comandos, declarado como dado ⬜ planejada

**Problema.** Os comandos da janela estão declarados em **três lugares que não se conhecem**, e
nenhum deles é a lista completa:

| onde | o que declara | quantos |
|---|---|---|
| `ui/menu.py:63-134` | rótulo e posição na barra de menus | 27 |
| `ui/atalhos.py:48-58` | tecla e como ela se escreve | 10 |
| `ui/pdf_panel.py:299-382` | o botão, montado à mão, com o rótulo em literal | 21 |

O nome do comando (`"ler_pagina"`, `"salvar"`) é o que liga os três, e ele já existe — foi a S-161
que o introduziu. O que não existe é o **registro**: nada diz que `ler_pagina` tem rótulo "Ler
esta página", pertence ao grupo OCR, é a ação primária dessa barra, e se desenha com tal ícone.
Hoje o rótulo do botão está em `pdf_panel.py:309` e o do menu em `menu.py:110`, escritos duas
vezes, e nada os compara.

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
```

Os seis grupos não são invenção: são os cinco menus de `menu.MENUS` com `Ferramentas` partido em
`OCR` e `ACERVO` — que é a divisão que a Imagem 2 faz e que o menu já insinua com o separador de
`menu.py:113`.

**O catálogo não substitui `menu.MENUS`**, e essa fronteira é o item. O menu decide *onde na barra
de menus*; o catálogo decide *o que o comando é*. `MENUS` passa a referenciar o catálogo em vez de
repetir o rótulo, e ganha a mesma trava que já tem para comando sem função: **item de menu cujo
`acao` não está no catálogo levanta** — a disciplina de `menu.comandos_faltando`, agora nos dois
sentidos.

**Critério de aceite.**

- todo `acao` de `menu.MENUS` está no catálogo, e todo `acao` de `atalhos.ATALHOS` também;
- todo comando montado como botão em `pdf_panel` e na linha de campo vem do catálogo — o teste
  varre os literais e falha se sobrar rótulo escrito à mão;
- `papel` de cada comando é um de `estilos.PAPEIS_DE_BOTAO`; papel desconhecido levanta `KeyError`,
  como em `estilos.estilo_de_botao`;
- **no máximo um `PRIMARIO` por grupo** — a regra de `ui/estilos.py:42` aplicada ao catálogo, onde
  ela finalmente é verificável sem abrir janela;
- `grupo` de todo comando é um dos seis; o conjunto dos grupos é fechado;
- o módulo não importa `tkinter` (o mesmo teste que a S-145 faz para `tokens`).

**Testes.** `test_todo_item_de_menu_esta_no_catalogo`;
`test_todo_atalho_esta_no_catalogo`;
`test_nenhum_rotulo_de_botao_escrito_a_mao`;
`test_um_primario_por_grupo`;
`test_papel_desconhecido_levanta`;
`test_o_catalogo_nao_importa_tkinter`.

---

## S-220 · O ícone que nasce do token, e não do disco ⬜ planejada

**Problema.** `assets/` tem 12 PNGs de peça e um `.ico`, e mais nada. As duas propostas são
dirigidas a ícone — 4 na Imagem 1, 13 na Imagem 2 —, e não existe um.

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
    "abrir_pdf": (Poli((10, 30), (40, 30), (48, 40), (90, 40), (90, 82), (10, 82)),),
    "ler_pagina": (Poli((20, 20), (20, 80), (80, 80), (80, 20), fechado=True), Arco(...)),
    ...
}
```

`icone(nome, tamanho, cor)` desenha com a Pillow e devolve `ImageTk.PhotoImage`, com cache por
`(nome, tamanho, cor)` — o mesmo padrão de `PieceImages._cache`, e pela mesma razão: a fita redesenha
13 ícones a cada mudança de densidade.

**A cor não é parâmetro do desenho, é do chamador, e o chamador pergunta ao token.** Quem monta a
fita pede `tokens.cor(tokens.TEXTO_PADRAO, style)` e passa; quem monta a fila da pele "Foco" pede o
mesmo papel resolvido contra o cromo escuro. Nenhum ícone tem cor própria — e é isso que faz o
mesmo `abrir_pdf` funcionar nas três peles sem uma segunda arte.

**Por que não SVG.** Traria dependência (`cairosvg` ou similar) para desenhar 20 formas de traço
único. O `ImageDraw.line` com `joint="curve"` faz o que estas formas precisam, e a Pillow já é
dependência obrigatória.

**Critério de aceite.**

- todo comando do catálogo com `icone` preenchido tem entrada em `ICONES`, e vice-versa: ícone
  órfão falha;
- toda coordenada de todo traço está em `0..100` — um traço que vaza a caixa desenha cortado, e o
  teste o pega sem abrir janela;
- `icone` devolve imagem do tamanho **exato** pedido, em qualquer tamanho de 16 a 48;
- a mesma chamada duas vezes devolve o mesmo objeto (cache), e trocar a cor devolve outro;
- ícone desconhecido devolve `None` e registra `warning` — **não levanta**: um ícone que falta vira
  botão só com texto, e não uma janela que não abre (regra 4).

**Testes.** `test_todo_comando_com_icone_tem_traco`;
`test_nenhum_icone_orfao`;
`test_todo_traco_cabe_na_caixa`;
`test_o_tamanho_pedido_e_o_entregue`;
`test_o_cache_devolve_o_mesmo_objeto`;
`test_icone_desconhecido_nao_levanta`.

---

## S-221 · A pele como estado da janela, e a clássica como padrão ⬜ planejada

**Problema.** Não há onde guardar "qual aparência". `AppState` (`ui/state.py:57-101`) guarda PDF,
página, zoom, geometria, aba aberta e dois interruptores de visualização — e nada sobre cromo. O
único eixo de aparência que existe é o tema, e ele é **variável de ambiente** (`CVOFF_TTK_THEME`,
`ui/theme.py:51`): escolhido antes de o programa abrir, invisível de dentro dele.

**Solução.** `ui/pele.py`, com o mesmo formato de `menu.MENUS` — declaração, não classe por pele:

```python
@dataclass(frozen=True)
class Pele:
    nome: str            # "classica" | "foco" | "fita"
    rotulo: str          # "Clássica" | "Foco" | "Fita"
    montar_cromo: str    # o nome da montagem; quem a executa é o painel
    densidade: str       # ui/tipografia, S-232
    cromo_escuro: bool   # S-224
```

`AppState` ganha `skin: str = "classica"`, com `STATE_VERSION` indo a 3 — e a regra de
`ui/state.py:19-22` já cobre o resto: estado de versão futura é descartado, não adivinhado.
`CVOFF_SKIN` acompanha `CVOFF_TTK_THEME` para quem dirige o programa por script.

O menu ganha `Ver ▸ Aparência` com um `radiobutton` por pele registrada — montado do registro, não
listado à mão, pelo mesmo motivo de `_submenu_recentes` ser montado no `postcommand`.

**O eixo pele e o eixo tema ficam separados de propósito.** Pele decide arranjo e densidade; tema
decide cor. Amarrá-los faria "a fita clara com o tabuleiro escuro" ser impossível sem que ninguém
tivesse decidido isso.

**Critério de aceite.**

- sem `skin` no disco, sem a variável e sem menu, a pele é `classica` — e a janela montada é
  **idêntica** à de hoje: mesmos widgets, mesma ordem, mesma geometria;
- pele desconhecida (disco ou variável) cai em `classica` com um `warning` que a **nomeia**, e não
  levanta;
- `Ver ▸ Aparência` lista exatamente as peles registradas, com a atual marcada;
- a pele escolhida sobrevive a fechar e reabrir, e `STATE_VERSION=3` lê o arquivo da versão 2 sem
  perder nada.

**Testes.** `test_a_pele_padrao_e_a_classica`;
`test_pele_desconhecida_cai_na_classica_com_aviso`;
`test_o_menu_lista_as_peles_registradas`;
`test_a_pele_sobrevive_ao_fechamento`;
`test_estado_da_versao_2_e_lido_sem_perda`.

---

## S-222 · Trocar de pele sem fechar a janela, e sem perder o lugar ⬜ planejada

**Problema.** Escolher aparência reiniciando o programa é escolher no escuro: quem compara três
peles reabre três vezes e compara de memória. E há um segundo custo, maior: reabrir perde o
**contexto de trabalho** — a página, o zoom, o diagrama selecionado, a FEN em edição, a aba aberta.
Quem estava no meio de uma correção não vai trocar de pele para ver.

A docstring de `theme.registrar_estilos` (`ui/theme.py:212-214`) já previu isto por escrito:
*"trocar de tema em execução — o que `CVOFF_TTK_THEME` permite entre execuções e um menu de
preferências vai permitir dentro de uma — precisa reaplicá-la"*.

**Solução.** A troca **remonta o cromo e não toca o conteúdo**. É viável porque a fronteira já foi
paga duas vezes: a Fase 6 tirou o pipeline das telas, e a S-49/S-50 tiraram o estado dos widgets.
O que se destrói e refaz são as barras, a fita e a faixa de abas; o `PanedWindow`, os painéis e o
`DiagramEditorModel` continuam de pé.

O que precisa ser explicitamente preservado, porque é o que se perde numa remontagem ingênua:

| preservar | de onde vem |
|---|---|
| PDF aberto e página | `pdf_panel`, `AppState.last_page` |
| zoom do PDF e do tabuleiro | `AppState.pdf_zoom` / `board_zoom` |
| diagrama selecionado e FEN em edição | `DiagramEditorModel` |
| aba aberta | `AppState.active_tab` (S-156) |
| posição do divisor | `AppState.sash_fraction` |
| a frase do rodapé, se ainda não expirou | `ui/rodape.py` |

E o que precisa ser **refeito**, porque senão sobra da pele anterior: os `bind_all` de roda e
atalho (`ui/pdf_panel.py:439` e o `add="+"` da S-150 — sem religar, uma troca de pele deixa duas
ligações da mesma tecla), os estilos nomeados (`theme.registrar_estilos`) e o cache de ícones da
S-220, que é por cor.

**Critério de aceite.**

- trocar de pele preserva os seis itens da tabela acima, e o teste os afirma um a um;
- depois de N trocas, o número de ligações de cada sequência de tecla é 1 — não N;
- a troca não reabre o PDF nem re-renderiza a página do zero (o `PhotoImage` da página é
  reaproveitado);
- a troca grava a escolha no `AppState` na hora, e não só no fechamento.

**Testes.** `test_a_troca_preserva_a_pagina_e_o_zoom`;
`test_a_troca_preserva_o_diagrama_e_a_fen`;
`test_a_troca_nao_duplica_ligacao_de_tecla`;
`test_a_troca_nao_re_renderiza_a_pagina`;
`test_a_troca_grava_a_escolha_na_hora`.

---

# Fase 33 — A pele "Foco" (Imagem 1)

> Cromo escuro, uma fila só de ações, o documento ocupando tudo o mais. É a proposta mais radical
> das duas, e a que mais depende da regra 2 para ser segura.

## S-223 · A fila única de ações, e o resto onde ele já estava ⬜ planejada

**Problema.** A Imagem 1 mostra **quatro** comandos onde a janela tem 21 nas duas barras do PDF,
mais 6 na linha de campo. Desenhá-la ao pé da letra apaga 23 controles.

Mas a imagem não está errada — está incompleta. O que ela acerta é o diagnóstico: numa fila de 21
botões de peso igual, o olho não encontra a ação do minuto a minuto. É o mesmo argumento de
`ui/estilos.py:12-16`, agora sobre quantidade em vez de ênfase.

**Solução.** A fila da pele "Foco" é **gerada** dos comandos com `destaque=True` no catálogo
(S-219), agrupados por `grupo`, com um separador vertical entre grupos — que é exatamente o que a
imagem desenha entre a 2ª e a 3ª pílula.

Os quatro da imagem viram a proposta de partida do `destaque`: `ler_pagina` (OCR),
`proximo_diagrama` (Edição), `aplicar_fen` (Edição), `exportar_pgn` (Arquivo). São quatro dos dez
que já têm atalho de teclado — e essa coincidência é o critério, não o gosto: **`destaque` exige
atalho**, pela mesma lógica com que `estilos.PRIMARIO` é definido como *"a ação que o atalho de
teclado também faz"*.

**Os outros 23 controles não somem: eles vão para o menu**, que a S-161 construiu e que a própria
Imagem 1 mostra intacto no topo. Os que ainda não têm item de menu — os 6 da linha de campo e os de
enquadrar — ganham um, e é a S-233 que garante que nenhum ficou de fora.

**A linha do conjunto de campo é a exceção, e ela fica.** A S-77 a pôs junto da página exibida de
propósito: ela anota *aquela* página, e um comando de menu que age sobre a página exibida sem que
ela esteja à vista é o tipo de gesto que grava verdade de referência errada. Na pele "Foco" ela
recolhe para uma linha só, com os rótulos elididos por `ui/texto.py` — não para o menu.

**Critério de aceite.**

- a fila é gerada do catálogo: acrescentar `destaque=True` a um comando o faz aparecer, sem tocar
  na montagem;
- todo comando com `destaque=True` tem atalho em `atalhos.ATALHOS`; sem atalho, falha;
- **no máximo 6 comandos em destaque** — acima disso a fila deixa de ser fila e vira a barra que
  ela veio substituir;
- os separadores caem entre grupos, e nunca na ponta;
- os 23 controles que saíram da tela têm item de menu **ou** estão na linha de campo — nenhum
  terceiro destino;
- em 1100×760, a largura em que a S-151 mediu o defeito original, a fila cabe em **uma** linha.

**Testes.** `test_a_fila_sai_do_catalogo`;
`test_destaque_exige_atalho`;
`test_no_maximo_seis_em_destaque`;
`test_separador_so_entre_grupos`;
`test_a_fila_cabe_em_uma_linha_em_1100`.

---

## S-224 · Cromo escuro, documento claro, marcações remedidas ⬜ planejada

**Problema.** A Imagem 1 é escura, e `ui/theme.py:37-50` argumenta contra tema escuro **por
escrito**, com um argumento bom: o produto é comparar diagrama impresso em papel branco com o que o
modelo leu, e pôr a página renderizada sobre preto faz o olho corrigir contraste em vez de posição.

Só que a imagem não contradiz isso. **A página dela continua branca.** O que escurece é o cromo — a
moldura, as barras, o fundo em volta. E o tabuleiro dela está em cinzas frios, não em preto.

Há um segundo problema, e é o que dá trabalho. As marcações deste projeto têm contraste **medido**
contra as superfícies de hoje (S-146, S-158, S-159), e a S-158 encontrou defeitos reais nessa
medição — `CORRIGIDO` dava 1,31:1 sobre a casa escura, uma borda desenhada e invisível em metade
das casas. Escurecer o cromo cria uma superfície nova, e nada garante que os 12 papéis de marcação
sobrevivam a ela.

**Solução.** Duas decisões, e a segunda é a que vira teste.

**1 · A fronteira: cromo segue a pele, documento não.** `tokens.SUPERFICIE_PAGINA` e
`tokens.SUPERFICIE_TABULEIRO` são superfícies de *documento* e mantêm a paleta medida em qualquer
pele. `tokens.SUPERFICIE_PADRAO` e `SUPERFICIE_DICA` são cromo e seguem a pele. A fronteira já
existe no módulo — a S-159 a criou ao separar as quatro superfícies —, e este item apenas a torna
consequente.

**2 · Os testes de contraste passam a rodar por pele.** `test_ui_semantica_cor.py` e
`test_ui_superficies.py` hoje afirmam `AA_TEXTO` (4,5:1) e `AA_GRAFICO` (3,0:1) contra uma paleta;
passam a parametrizar sobre `pele.REGISTRO`. **Registrar uma pele nova é assinar essa conta**, e é
assim que a "Foco" não pode entrar quebrando o que a S-158 consertou.

A regra de `SEPARACAO_MINIMA_DE_MATIZ` (40°, `ui/tokens.py:471`) vale igual: foi ela que achou o
terceiro par que a S-158 não tinha listado.

**Critério de aceite.**

- na pele "Foco", `SUPERFICIE_PAGINA` e `SUPERFICIE_TABULEIRO` são as mesmas de hoje — a página
  renderizada e o tabuleiro não escurecem;
- os 12 papéis de marcação atingem `AA_GRAFICO` sobre **todas** as superfícies em que são
  desenhados, em cada pele registrada;
- os papéis de texto atingem `AA_TEXTO` sobre a superfície do cromo escuro;
- nenhum par de papéis desenhados na mesma superfície fica abaixo de 40° de matiz, em nenhuma pele;
- o mesmo teste, sem alteração, falha se alguém registrar uma pele que quebre qualquer um desses.

**Testes.** `test_o_documento_nao_escurece_com_a_pele`;
`test_toda_marcacao_atinge_aa_grafico_em_toda_pele`;
`test_todo_texto_atinge_aa_texto_em_toda_pele`;
`test_a_separacao_de_matiz_vale_em_toda_pele`;
`test_uma_pele_que_quebra_o_contraste_falha`.

---

## S-225 · O deslizador de zoom, sem tirar o teclado nem os botões de enquadrar ⬜ planejada

**Problema.** O zoom do PDF hoje são cinco controles em fila: `-`, `+`, o rótulo `70%`, "Ajustar à
largura" e "Ajustar à página" (`ui/pdf_panel.py:346-360`). Cada clique move 0,1 — ir de 70% para
150% são **oito cliques**. E os cinco ocupam metade da barra da vista, que é a que a S-151 mediu
sumindo em 1100 de largura.

**Solução.** O deslizador que a Imagem 1 desenha no rodapé do painel, ligado ao mesmo
`viewport.clamp_zoom` de hoje, com escala logarítmica — porque a diferença entre 40% e 50% importa
muito mais que entre 240% e 250%.

**O que ele não substitui, e é aqui que o item pode dar errado:** `Ctrl+0` (S-165) e a roda com
`Ctrl` (`ui/pdf_panel.py:439`) continuam; "Ajustar à largura" e "Ajustar à página" continuam,
porque enquadrar não é um valor de zoom — é uma pergunta sobre a página que o deslizador não sabe
responder. O que sai são `-`, `+` e o rótulo, que o próprio deslizador passa a dizer.

**Critério de aceite.**

- o deslizador cobre a mesma faixa de `clamp_zoom`, e nunca a ultrapassa;
- arrastar preserva o ponto de referência, como `anchor_after_zoom` já faz para a roda;
- `Ctrl+0`, a roda com `Ctrl` e os dois botões de enquadrar continuam funcionando, e movem o
  deslizador;
- o valor aparece em texto ao lado, na mesma forma de hoje (`70%`), lido por `ui/formato.py`;
- na pele clássica nada muda: o deslizador é da pele "Foco".

**Testes.** `test_o_deslizador_respeita_o_clamp`;
`test_o_deslizador_preserva_a_ancora`;
`test_enquadrar_move_o_deslizador`;
`test_a_pele_classica_nao_ganha_deslizador`.

---

## S-226 · A faixa de abas discreta, e o rodapé que não pode sumir ⬜ planejada

**Problema.** A Imagem 1 não tem faixa de abas nem rodapé. As seis abas
(`app_tkinter.py:311-399`) são Resultado, Análise, Revisão, Dataset, Galeria e Configuração — e a
S-162 as reordenou de propósito, separando o que é do diagrama aberto do que é do acervo.

O rodapé é pior de perder. Depois da S-163 ele é onde mora o **cancelamento** da varredura, da
exportação e do treino, além do progresso e do estado do documento. Uma pele sem rodapé é uma pele
em que uma varredura de 10 horas não pode ser interrompida.

**Solução.** As abas ficam; o que muda é o peso. A faixa vira texto sublinhado sobre o cromo
escuro, sem a moldura em relevo do `ttk.Notebook` padrão, com a contagem que `ui/abas.py` já gera.
O rodapé fica **inteiro** e sem exceção — e é a S-234 que impede uma pele futura de tentar
removê-lo.

**Este item é o que dá sentido à regra 2 da spec**, porque é onde a tentação de seguir a imagem à
risca é maior e o dano é o mais concreto: a varredura que não para.

**Critério de aceite.**

- as seis abas existem em todas as peles, na ordem da S-162;
- o rodapé existe em todas as peles, com o botão de cancelamento presente sempre que há operação
  em curso;
- a faixa de abas da pele "Foco" atinge `AA_TEXTO` sobre o cromo escuro, aba ativa e inativa;
- a contagem em cada rótulo continua vindo de `ui/abas.py` — nenhuma pele a formata por conta.

**Testes.** `test_as_seis_abas_existem_em_toda_pele`;
`test_o_rodape_existe_em_toda_pele`;
`test_o_cancelamento_esta_alcancavel_em_toda_pele`;
`test_a_faixa_de_abas_e_legivel_no_cromo_escuro`.

---

# Fase 34 — A pele "Fita" (Imagem 2)

> Grupos nomeados, ícone grande com rótulo embaixo. É a proposta mais fácil de desenhar e a mais
> fácil de errar, porque ela custa altura — e altura foi o defeito da S-151.

## S-227 · A fita de grupos nomeados, gerada do catálogo ⬜ planejada

**Problema.** A Imagem 2 mostra quatro grupos com cabeçalho — Arquivo, OCR, Edição, Visualização —
e 13 comandos distribuídos entre eles. Hoje não existe agrupamento declarado em lugar nenhum: as
duas barras do PDF são duas listas planas, e o único agrupamento que existe é o separador visual
de `menu.py:113`, que só o menu conhece.

**Solução.** A fita é uma sequência de `GrupoDeFita`, cada um gerado dos comandos do catálogo com
aquele `grupo` (S-219). O cabeçalho é o rótulo do grupo; o corpo, os comandos em ordem de
declaração.

**O grupo é a unidade de quebra, e é isso que a distingue da `BarraFluida`.** `ui/barra.py` quebra
por item, e a propriedade que ela afirma é *"nenhum item é descartado"*. A fita herda isso — usa a
mesma `arranjo` — mas com os **grupos** como itens: um grupo partido ao meio não é um grupo, e a
única quebra aceitável é entre grupos. A `arranjo` já serve a isso sem mudança, porque ela opera
sobre larguras e não sobre widgets.

Quando nem um grupo cabe, a fita entra em modo compacto (S-228). Ela nunca esconde grupo — a regra
2 vale aqui como em todo lugar.

**Critério de aceite.**

- os grupos e a ordem dentro deles saem do catálogo; acrescentar comando ao catálogo o faz aparecer
  na fita;
- a quebra é sempre entre grupos, nunca dentro de um;
- em nenhuma largura um grupo é descartado — a propriedade da S-151, aplicada a grupos;
- grupo vazio não desenha cabeçalho (um grupo sem comando visível não é um título solto);
- a fita usa `ui/barra.arranjo`, e não uma segunda implementação de quebra.

**Testes.** `test_a_fita_sai_do_catalogo`;
`test_a_quebra_e_sempre_entre_grupos`;
`test_nenhum_grupo_e_descartado`;
`test_grupo_vazio_nao_desenha_cabecalho`.

---

## S-228 · Ícone grande com rótulo, e o orçamento de altura que ele respeita ⬜ planejada

**Problema.** A S-151 mediu o defeito que esta pele arrisca recriar: cinco barras empilhadas =
~200 px, **20% da altura da janela**, sobre o painel cuja única razão de existir é mostrar a página
grande. A fita da Imagem 2 — cabeçalho de grupo, ícone grande, rótulo embaixo — mede ~110 a 130 px
numa linha só. É metade do que a S-151 removeu, e volta pela porta da frente.

E a fita é pior que a barra num aspecto: ela não quebra barato. Quebrar uma barra custa ~28 px;
quebrar uma fita custa outra linha de fita, que é ~110.

**Solução.** Um **orçamento em pixel**, declarado e verificado, e um modo compacto abaixo de uma
largura medida.

| modo | quando | forma | altura alvo |
|---|---|---|---|
| pleno | largura ≥ o que couber em uma linha de fita | ícone 32 px, rótulo embaixo, cabeçalho de grupo | ≤ 120 px |
| compacto | abaixo disso | ícone 20 px, rótulo ao lado, cabeçalho vira `tooltip` | ≤ 64 px |

Os dois números não são gosto: 120 px é 12% de uma janela de 1000 de altura — abaixo dos 20% que a
S-151 chamou de defeito, e acima dos ~56 px das duas barras de hoje, que é o que a fita custa a
mais em troca de legibilidade. 64 px é o que cabe sem a fita competir com a página num 1366×768.

A altura é calculada por função pura a partir da tipografia e do tamanho de ícone — nada de
`winfo_height` no critério —, e é isso que faz o orçamento ser afirmável na suíte.

**Critério de aceite.**

- `altura_da_fita(modo, densidade, tipografia)` é pura e devolve o mesmo que o widget montado
  mede, com tolerância de 2 px;
- no modo pleno a altura fica ≤ 120 px na fonte padrão do sistema e na densidade confortável;
- no modo compacto fica ≤ 64 px;
- em 1366×768 com o divisor no padrão, a fita entra em compacto **antes** de precisar de segunda
  linha;
- a troca de modo não descarta comando nenhum, e o teste percorre as larguras de 800 a 2560
  afirmando isso.

**Testes.** `test_a_altura_calculada_bate_com_a_medida`;
`test_o_orcamento_do_modo_pleno`;
`test_o_orcamento_do_modo_compacto`;
`test_em_1366_a_fita_fica_compacta_e_nao_dobra`;
`test_nenhuma_largura_descarta_comando`.

---

## S-229 · Desfazer e refazer, que a fita promete e o programa não tem ⬜ planejada

**Problema.** A Imagem 2 põe **Desfazer, Refazer e Limpar** no grupo Edição. `grep -rn 'undo' src/`
devolve zero linhas de implementação — os únicos acertos são comentários, entre eles o de
`ui/board_edit.py:167`, que descreve `apply_edits` como *"útil para desfazer em bloco"*.

Não é descuido da proposta: é a função que falta. E o registro do que custa não tê-la já existe
neste projeto — a **S-76**, em que um clique sobrescreveu **1.405 diagramas** de trabalho humano.
Hoje, uma edição errada no tabuleiro só se desfaz reeditando casa a casa, ou recarregando o
diagrama e perdendo o resto.

**Solução.** `ui/historico.py`: uma pilha de posições (`placement`, a string de 64 casas), não de
gestos.

A escolha é o item. Uma pilha de gestos precisa saber inverter cada operação — pôr, tirar, mover,
arrastar, aplicar FEN, aplicar segunda opinião, aplicar correção de rede — e cada operação nova
precisa lembrar de registrar o seu inverso. Uma pilha de estados precisa saber **uma** coisa: a
posição de antes. `board_edit` é puro e `placement` é uma string de ~70 bytes; 100 estados são 7
KB. O custo de memória não é argumento contra, e o custo de correção é decisivo a favor.

- teto de 100 estados por diagrama, e a pilha é **por diagrama**: trocar de diagrama a zera,
  porque desfazer para dentro de outra posição é pior que não desfazer;
- `Ctrl+Z` e `Ctrl+Y` entram em `atalhos.ATALHOS`, e daí para o menu Editar e o catálogo de graça;
- "Limpar" (o terceiro botão da imagem) é o `clear` que já existe em `DiagramEditorModel:196` —
  ele apenas ganha entrada no histórico, e passa a ser desfazível;
- os botões ficam desabilitados quando não há o que desfazer, com `tooltip` que diz por quê — a
  regra da S-165, que achou 13 controles desabiláveis sem tooltip.

**Critério de aceite.**

- desfazer devolve exatamente a posição anterior, para as sete origens de mudança (mão, FEN,
  arraste, apagar casa, limpar, segunda opinião, correção de rede);
- refazer devolve o que o desfazer tirou, e uma edição nova **descarta** a pilha de refazer;
- trocar de diagrama zera as duas pilhas;
- a pilha nunca passa de 100 estados;
- salvar não é desfazível pelo histórico — gravar em `labels.csv` é outra ação, e confundir as
  duas é como se perderiam 1.405 linhas de novo;
- `Ctrl+Z`/`Ctrl+Y` aparecem na legenda de atalhos e no menu Editar sem ninguém escrevê-los lá.

**Testes.** `test_desfazer_devolve_a_posicao_anterior` (parametrizado nas sete origens);
`test_refazer_devolve_o_que_o_desfazer_tirou`;
`test_edicao_nova_descarta_o_refazer`;
`test_trocar_de_diagrama_zera_o_historico`;
`test_o_teto_de_cem_estados`;
`test_salvar_nao_entra_no_historico`.

---

## S-230 · O conjunto de peças como escolha, e não como pasta cravada ⬜ planejada

**Problema.** `PieceImages` recebe um diretório (`ui/board_render.py:163`) e o chamador passa
sempre o mesmo: `assets/piece_images/`. Doze PNGs, um conjunto, sem alternativa — e trocá-lo hoje é
sobrescrever os arquivos, o que muda o conjunto de todo mundo e não tem volta.

A Imagem 2 mostra peças fotográficas de um tabuleiro de madeira real. **Isso não entra**, e a razão
é de produto: o tabuleiro da janela é onde se *corrige* a leitura, casa a casa, contra um diagrama
impresso — sombra, perspectiva e madeira atrapalham exatamente essa comparação. O que entra da
imagem é a ideia de que o conjunto é uma escolha.

**Solução.** Um registro de conjuntos, com a mesma forma do registro de peles:

- **`padrao`** — os 12 PNGs de hoje, e continua sendo o padrão;
- **`traco`** — um segundo conjunto de traço mais grosso, para quem trabalha com o tabuleiro
  pequeno (a paleta de edição e a Galeria os desenham a 20–24 px, onde o traço de hoje some);
- **pasta do usuário** — um caminho em `Configuração`, validado por `ui/campos.py`, que carrega os
  12 arquivos por nome (`wk.png`, `bq.png`, …).

`PieceImages` quase não muda: ele já é cache por `(chave, tamanho, fundo)` e já degrada para
símbolo Unicode quando o arquivo falta (`ui/board_render.py:186`). O que entra é a chave do
conjunto no cache, e um aviso quando a pasta do usuário tem menos de 12 arquivos — **avisar e usar
o que houver**, e não recusar: um conjunto incompleto cai no Unicode peça a peça, que é o
comportamento que já existe.

**Critério de aceite.**

- o conjunto padrão é o de hoje, e a pele clássica com o conjunto padrão desenha o tabuleiro
  idêntico ao atual;
- o conjunto é eixo próprio: qualquer conjunto vale com qualquer pele;
- pasta de usuário com arquivo faltando registra `warning` nomeando as peças ausentes, e desenha o
  resto;
- o cache não confunde conjuntos: a mesma peça, no mesmo tamanho, em dois conjuntos, são duas
  imagens;
- o conjunto escolhido sobrevive a fechar e reabrir.

**Testes.** `test_o_conjunto_padrao_e_o_de_hoje`;
`test_conjunto_e_pele_sao_eixos_independentes`;
`test_pasta_incompleta_avisa_e_desenha_o_resto`;
`test_o_cache_separa_conjuntos`.

---

# Fase 35 — O que as três peles ganham juntas

> Os quatro itens que só fazem sentido depois de existir mais de uma pele. Dois deles são o preço
> de ter três; dois são o troco.

## S-231 · A paleta de comandos, que sai de graça do catálogo ⬜ planejada

**Problema.** A pele "Foco" tira 23 controles da tela e os põe no menu. Cinco menus com 27 itens já
é um mapa que se decora; 50 itens é um mapa em que se procura. E procurar comando em menu é o
gesto que a S-161 descreveu ao contrário: *"o que não era botão não existia"* — vira "o que não
está no menu que eu abri, eu não acho".

**Solução.** `Ctrl+Shift+P`: um campo, uma lista filtrada, Enter executa.

**O item é barato porque o catálogo da S-219 já é a lista.** Rótulo, grupo, atalho e estado
(habilitado ou não) estão todos lá; o que falta é o filtro e a janela. O filtro é função pura sobre
`(consulta, catálogo) → lista ordenada` — casamento por subsequência, com o comando de atalho
subindo, e o grupo mostrado à direita como o menu faz.

**Isto é o que torna segura a regra 2 na pele "Foco".** Esconder comando é aceitável quando há um
caminho de um gesto até qualquer comando; sem paleta, "está no menu" é uma promessa que se cumpre
em três cliques e cinco menus.

**Critério de aceite.**

- o filtro é puro e testado sem janela: consulta vazia devolve tudo, em ordem de grupo;
- comando desabilitado aparece **cinza e com o motivo**, e não some — sumir é o defeito que a S-165
  registrou nos 13 controles sem tooltip;
- Enter executa o primeiro; setas navegam; Esc fecha sem executar;
- a paleta existe nas três peles — ela não é da "Foco";
- `Ctrl+Shift+P` entra em `atalhos.ATALHOS`, e daí para a legenda e o menu Ajuda de graça.

**Testes.** `test_o_filtro_e_puro`;
`test_consulta_vazia_devolve_tudo_em_ordem_de_grupo`;
`test_comando_desabilitado_aparece_com_motivo`;
`test_a_paleta_existe_nas_tres_peles`.

---

## S-232 · Densidade: compacta ou confortável ⬜ planejada

**Problema.** A S-151 mediu o defeito em **1100×760**, e a solução dela — quebrar em vez de cortar
— resolve o descarte mas não o aperto: em 1366×768, que é a tela de notebook mais comum, as duas
barras quebram em quatro linhas e a página fica com o que sobrar. A fita da S-228 piora isso, e por
isso já nasce com um modo compacto — mas o modo compacto é decisão da fita, não da janela.

**Solução.** Densidade como eixo da janela, com dois valores, derivado de `ui/tipografia.py` —
que já escala pela fonte do sistema (`theme.fonte_base`), e é por isso que uma escala de números
fixos não serviria aqui.

| densidade | espaçamento | altura de linha de tabela | ícone da fita |
|---|---|---|---|
| confortável | como hoje | como hoje | 32 px |
| compacta | ×0,7 | ×0,8 | 20 px |

A densidade é **sugerida** pela pele (`Pele.densidade`, S-221) e **decidida** por quem usa: a fita
sugere compacta, a "Foco" sugere confortável, e `Ver ▸ Aparência ▸ Densidade` sobrepõe as duas.

**Critério de aceite.**

- a densidade deriva da fonte do sistema; aumentar a fonte do Windows aumenta os dois valores;
- nenhum espaçamento é escrito fora de `ui/tipografia.py`;
- em 1366×768, densidade compacta, a fita cabe em uma linha e o painel do PDF fica com ≥ 60% da
  altura;
- a escolha explícita da pessoa sobrepõe a sugestão da pele, e sobrevive à troca de pele;
- na densidade confortável com a pele clássica, nada muda em relação a hoje.

**Testes.** `test_a_densidade_deriva_da_fonte_do_sistema`;
`test_a_escolha_explicita_sobrepoe_a_pele`;
`test_em_1366_compacta_o_pdf_fica_com_60_por_cento`;
`test_a_classica_confortavel_e_identica_a_hoje`.

---

## S-233 · Nenhuma pele esconde um comando: o inventário de alcance ⬜ planejada

**Problema.** É o risco central de todo este plano, e ele não é técnico: **três peles convidam a
resolver rápido só numa delas.** Um comando novo entra na fita porque foi lá que quem o escreveu
estava trabalhando, e some da "Foco" e da clássica — e ninguém descobre até alguém que usa a pele
errada precisar dele.

A regra 2 desta spec — *pele é apresentação, nunca conjunto menor* — não vale nada sem uma máquina
que a cobre.

**Solução.** Um inventário: para cada pele registrada, o conjunto de comandos **alcançáveis**, e a
afirmação de que ele é igual ao catálogo inteiro.

"Alcançável" tem três formas, e só três:

1. um controle na tela daquela pele (fila, fita, barra, linha de campo, painel);
2. um item de `menu.MENUS`;
3. uma entrada da paleta de comandos (S-231) — que, por construção, cobre o catálogo inteiro.

A terceira forma sozinha tornaria o teste trivial, e por isso ela **não conta para o inventário**:
o critério é que todo comando esteja em (1) **ou** (2) em cada pele. A paleta é atalho para quem
sabe o nome, não o mapa de quem procura.

O inventário é montado por reflexão sobre a declaração de cada pele — não abrindo janela e
varrendo widget —, e é isso que o torna barato o bastante para rodar em toda execução da suíte.

**Critério de aceite.**

- para cada pele registrada, `alcancaveis(pele) == set(catalogo)`;
- a mensagem de falha **nomeia** a pele e os comandos que ela perdeu, e não devolve um booleano;
- acrescentar um comando ao catálogo sem lhe dar casa em alguma pele **falha a suíte**;
- remover um comando da fita da "Fita" sem lhe dar item de menu falha a suíte;
- o teste não abre janela.

**Testes.** `test_toda_pele_alcanca_o_catalogo_inteiro`;
`test_a_falha_nomeia_a_pele_e_o_comando`;
`test_comando_novo_sem_casa_falha`;
`test_o_inventario_nao_abre_janela`.

---

## S-234 · A pele não derruba a janela: o contrato de degradação nas três ⬜ planejada

**Problema.** `ui/theme.py:12-15` estabelece o contrato: *"um checkout sem o extra, um bundle que
não o incluiu ou um tema com nome errado não podem impedir o app de abrir — tema é aparência, e
aparência não derruba ferramenta"*. `apply_theme` o cumpre: tema recusado cai no padrão, padrão
recusado cai no `ttk` puro, e nada levanta.

Esta fase acrescenta **três** modos de falha novos que o contrato ainda não cobre: pele
desconhecida no disco ou na variável de ambiente; ícone que não desenhou; conjunto de peças cuja
pasta sumiu. Os três acontecem exatamente na abertura, que é o pior momento.

E há um quarto, específico do bundle: `packaging/cvoff.spec` empacota `assets/`, e o catálogo de
ícones da S-220 é código — mas o conjunto de peças da S-230 é dado, e uma pasta de usuário
apontando para fora do bundle é o caso normal, não o excepcional.

**Solução.** O contrato estendido, com a mesma forma de `apply_theme`: cair um degrau, registrar
uma vez, nunca levantar.

| falha | queda | registro |
|---|---|---|
| pele desconhecida | `classica` | `warning` nomeando a pele pedida e as registradas |
| ícone sem traço | botão só com texto | `warning` uma vez por nome |
| Pillow indisponível ou desenho falho | botão só com texto | `warning` uma vez |
| pasta de peças ausente | conjunto `padrao` | `warning` com o caminho |
| conjunto padrão ausente (bundle quebrado) | símbolo Unicode | `warning`, e o tabuleiro desenha |
| densidade desconhecida | `confortavel` | `warning` |

E o `selftest` (`app_tkinter.py:1636`) passa a rodar **uma vez por pele registrada**. Ele já é o
roteiro headless que o `CONTRIBUTING` manda usar para dirigir a interface sem clicar; estendê-lo é
o que faz "as três peles abrem" ser uma afirmação verificada e não uma esperança.

**Critério de aceite.**

- cada uma das seis falhas da tabela produz a queda descrita, sem levantar;
- cada uma registra **uma** vez, e não uma por widget;
- o `selftest` roda nas três peles e devolve 0 nas três;
- com a Pillow presente mas sem `ttkbootstrap`, as três peles abrem em `ttk` puro;
- nenhum caminho de aparência aparece num `traceback` de abertura, em nenhuma combinação de pele,
  tema, densidade e conjunto.

**Testes.** `test_as_seis_quedas` (parametrizado);
`test_o_aviso_sai_uma_vez_so`;
`test_o_selftest_roda_nas_tres_peles`;
`test_as_tres_peles_abrem_sem_ttkbootstrap`.

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
