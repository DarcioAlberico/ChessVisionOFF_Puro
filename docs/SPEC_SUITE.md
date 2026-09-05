# Especificação da suíte de treino — Fases 80 a 86 (S-527 a S-580)

Os itens de [ROADMAP_SUITE.md](ROADMAP_SUITE.md), um a um. A faixa S-527 a S-580 está reservada para
este documento; um número sem seção aqui é item ainda não entregue, e não item perdido.

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
> | S-522 a S-526 | [SPEC_REVISAO_EXTERNA_2.md](SPEC_REVISAO_EXTERNA_2.md) |
> | S-500 a S-506, S-527 a S-580 | [SPEC_SUITE.md](SPEC_SUITE.md) |

Cada item tem **Problema** (com `arquivo:linha` do estado em `0cf5492`), **Solução**, **Critério de
aceite**, **Testes** e **O que o crítico recusou** -- o registro das rodadas em que a fotografia da
janela foi comparada lado a lado com o ChessBase e o Lichess, e o que faltava em cada uma.

---

## S-527 · A barra da sala de estudo agrupada por tarefa, com ícones vetoriais e rótulo curto — ✅ **implementada em 2026-09-04**

### Problema

`qt/painel_de_estudo.py:257` (`_barras`), `:342` (`_barra_de_fora`) e `:372` (`_entrada_e_saida`)
montavam três `BarraFluida` com 28 botões de texto (31 com motor) e um `QCheckBox` (`:285`), sem
ícone, sem separador e sem hierarquia. **Medido em 2026-09-04, a 1400×950** (a aba Estudo tem 714 px
de largura): as três barras quebravam em **cinco fileiras** (2 + 1 + 2) e ocupavam **154 px** acima
do divisor; o tabuleiro desenhava com 442 px de lado. Na fotografia `fotos/base/01_Estudo.png` são
quatro fileiras visíveis mais a linha da caixa. "Apagar variante" ficava a um botão de "Símbolo", e
"Carregar OCR atual" -- o único primário -- no meio de vinte e sete iguais.

Um segundo defeito apareceu na medição, e não estava no roadmap: **o clique de mouse em "Treinar"
não ligava o treino**. Um `QPushButton` marcável alterna `checked` antes de emitir `clicked`, e
`alternar_treino` inverte `isChecked()` de novo -- o clique ligava e desligava no mesmo gesto, e só o
menu e a paleta (que chamam o método sem botão) treinavam. Vale igual para "Recorte" e "Análise
contínua"; "Dobrar" escapava porque deriva o estado da lista de dobradas.

### Solução

**Uma decisão pura, `ui/barra_da_sala.py`.** A tabela `ACOES`: trinta e uma ações desde a segunda
rodada (os 29 comandos de `COMANDOS_DA_ABA` menos os quatro de navegação da S-517 -- o vigésimo
nono é `indexar_base` --, mais o interruptor `SEGUIR_OCR` e o agrupador `EXPORTAR_ESTUDO`), cada
uma com **grupo por tarefa** (Posição, Variante, Livro, Base, Motor, Exportar, Treino), nome do
ícone, se é **principal** ou vai para o "Mais", **prioridade** entre as principais, se escreve o
texto ao lado do ícone (`com_texto`), se é interruptor, e a explicação da dica. Rótulo curto, rótulo longo, papel e
tecla **não são reescritos**: vêm de `comandos` e `atalhos`; só o que o catálogo não tem ("Seguir
OCR", "Exportar", "Mais") declara texto ali, uma vez. Três funções puras: `modo(vazio, treinando)` →
`grupos_desligados(modo)` (sem estudo: Variante e Exportar cinza; treinando: Variante cinza);
`dica_de(acao)` (rótulo longo, explicação, `Tecla: X`); e `cabem(itens, disponivel, reserva, ...)`.

**O ícone não entra pelo catálogo, e isto foi decidido contra a letra do pedido.** O item pedia
"ícones desenhados por `QPainter` em `qt/icones.py`"; o projeto já tem o mecanismo -- traço declarado
em `ui/icones.py`, desenhado em PIL, entregue como `QIcon` por `qt/icones.py` (S-220/S-503) -- e um
segundo desenhador para a mesma família seria a divergência que a S-501 fechou. Os 24 traços novos
moram em `icones.ICONES_DA_SALA`, um **segundo dicionário** e não mais chaves em `ICONES`, porque
`medidas_da_fita.grupos()` põe na fita da janela todo comando do catálogo com `icone`: dar ícone aos
trinta pelo catálogo despejaria os trinta no cromo da janela ao lado de "Abrir PDF". Quatro reusam
traços existentes (`salvar`, `abrir_pdf`, `exportar_pgn`, `aplicar_fen`); os três formatos de
exportação não têm traço porque não têm botão.

**O widget, `qt/barra_da_sala.py`.** Uma fila de `QToolButton` chatos (`ToolButtonTextBesideIcon`,
ícone de 16 px), separador `QWidget#separador-da-fila` entre grupos, "Exportar ▾" com `QMenu` dos
três formatos, "Mais ▾" com `QMenu` seccionado por grupo. Cada ação da tabela é **uma `QAction`**,
que é ao mesmo tempo o botão da fila e o item do menu: texto, ícone, marcado e habilitado são um
estado só. É isso que deixa o resto do painel intacto -- `btn_dobra`, `btn_recorte`, `btn_treino`,
`btn_continua` e `seguir_ocr` passam a ser essas `QAction`s, e `setChecked`/`setText`/`setEnabled`/
`isChecked` são os mesmos nomes. Nenhum slot muda; `executar` ganha uma linha para
`METODOS_PROPRIOS`. `lbl_simbolo` e `lbl_placar`, que acompanhavam os botões "Símbolo" e "Treinar",
vão para a faixa sob o tabuleiro, ao lado do lance corrente e da vez.

**Quem cabe é decidido, não sofrido.** A 714 px não cabem quinze botões com rótulo, e a S-151 mediu o
que acontece quando uma barra esconde sem avisar. `cabem` recebe as larguras medidas e devolve, por
prioridade e em prefixo, quem fica; o que não coube **vai para o "Mais"** (antes das secundárias,
sob o cabeçalho do grupo) e volta quando a janela alarga. O `resizeEvent` só mede e pergunta.
**E a barra declara o próprio mínimo**: `minimumSizeHint` responde a largura do "Mais", não a soma
dos botões visíveis, que é o padrão do `QWidget`. Sem isso o pai nunca a estreitava -- medido na
primeira montagem: pedida a 500 px, a fila ficava com 1.387, e `cabem` decidia sobre uma largura
que não mudava. A fronteira com a S-517 também ficou declarada uma vez: `NAVEGACAO` é a tupla
ordenada que `_barra_de_navegacao` percorre, e não mais quatro literais no painel.

**O interruptor alterna uma vez.** Para os quatro marcáveis do catálogo, o `triggered` da `QAction`
devolve o estado que o clique alternou e chama o método, que alterna -- como faz para o menu.
`SEGUIR_OCR` é o contrário (o método lê o estado) e usa `toggled`, como o `QCheckBox` fazia. O
papel chega ao `QToolButton` por regras novas em `qt/tema.py`: primário com face, destrutivo pela
cor (letra e traço em `BOTAO_DESTRUTIVO`; dois blocos vermelhos sólidos numa fila chata pediriam
cuidado o tempo todo), e `:disabled` cinza, pela mesma razão do botão comum.

**Segunda rodada (2026-09-04, depois do crítico -- ver a tabela abaixo).** Cinco decisões, todas
na tabela pura ou na folha, nenhuma no painel:

1. **Dois níveis de botão** (`Acao.com_texto`): ícone e texto para o primário, o interruptor do
   treino e o salvar; **só ícone** para os outros onze, com o rótulo e a tecla na primeira linha da
   dica (`Promover a variante um nível · Ctrl+↑`, `SEPARADOR_DA_TECLA`). O nível chega à folha por
   `tema.PROPRIEDADE_DE_NIVEL`, e o de ícone tem recheio horizontal de 4 px em vez de 10 -- medido:
   com 10 cabiam oito a 702 px, com 5 dez, com 4 onze. "Salvar PGN" virou "Salvar" (o disquete e a
   dica dizem o formato): eram os 26 px que faltavam para as catorze caberem na aba de 804 px.
2. **Prioridades refeitas pela frequência**: 1 carregar, 2 seguir, **3 treinar** (marcado enquanto
   treina, com `QToolButton:checked` na folha -- face funda e moldura na cor de ênfase), **4 o par
   Promover/Rebaixar** (mesma prioridade = bloco em `cabem`: entram e saem juntos), 5 apagar, 6
   símbolo, 7 salvar, 8 exportar, 9 posição inicial, 10 dobrar, 11 recorte, 12 partidas, 13 linha do
   livro, 14 análise contínua. O "Mais" vem **logo depois do último botão**, com o vão à direita.
   E o texto que cresce ("Parar o treino") agenda um rearranjo pelo `changed` da ação: sem isso o
   layout espremia o primário (fotografado elidido).
3. **O cabeçalho do "Mais"** é um item desabilitado em negrito por grupo (`PROPRIEDADE_DE_CABECALHO`),
   e não `addSection`, que no `windows11` desenha só a linha. Os itens que transbordaram saem por
   extenso, como os que nunca tiveram botão -- a `QAction` de um botão só com ícone não escreve o
   rótulo curto em lugar nenhum.
4. **O ícone é desenhado a 16 px**, com traço mínimo de 2 px (`icones.TRACO_MINIMO`) e "simbolo" e
   "mais" redesenhados como quadradinhos cheios; `qt_icones.icone(..., escala=devicePixelRatioF())`
   só nasce maior em tela de alta densidade. A barra se registra em `tema.ao_repintar` e repinta na
   troca de pele. O chevron do "Mais" vai para a linha do texto (`::menu-indicator` em `qt/tema.py`).
5. **As teclas da sala** (`atalhos.TECLAS_DA_SALA`, terceira tabela): `Ctrl+↑` promove, `Ctrl+↓`
   rebaixa, `Ctrl+Del` apaga a variante, `Ctrl+M` abre o símbolo. Setas com o modificador para
   subir/descer a variante (o par que o ChessBase mostra no menu da notação); `Ctrl+Del` como o `Del`
   da casa, com o alvo maior; `Ctrl+M` é decisão nossa -- o ChessBase não tem tecla para o menu de
   símbolos, o símbolo se digita. Ligadas na `QAction` com alcance no painel da sala: desabilitada
   não dispara, então treinando `Ctrl+↑` não faz nada. `acelerador`/`atalho_de` mostram a tecla na
   dica, no menu Estudo (só mostrada) e na legenda; `acao_de` -- o que a guarda de foco lê -- não
   responde por elas.

E a **fiação pendente da S-532**: `indexar_base` entrou no catálogo (menu Estudo), em
`COMANDOS_DA_ABA` e na barra (grupo Base, no "Mais", traço "indexar"); `PainelDeEstudo.indexar_base`
chama `indice_da_base.indexar_com_dialogo(self.window(), bases, busy=...)` com as bases da sala ou
`database_paths()`, e liga `terminou` a `set_status(frase_final(...))` -- que é o rodapé da aba e o
da janela. O `busy` é o da janela (`PainelDeEstudo(busy=...)`, com `window().busy` como reserva para
não crescer `qt/janela.py`). A caixa "Partidas da base" (`qt/dialogos.py`) deixou de mandar rodar
`cvoff-games --build-index`: oferece "Indexar agora" e chama o mesmo indexador.

### Critério de aceite

- A barra do topo é **uma fila** em qualquer largura. ✅ **Medido a 1400×950: 154 px → 38 px**
  acima do divisor (−116 px, 75%); a fila tem 32 px. O tabuleiro foi de 442 para 450 px de lado --
  nesta janela ele é limitado pela **largura** da coluna (484 px), não pela altura, e o que a barra
  devolveu vira coluna livre sob o tabuleiro; ao arrastar o divisor para a direita, a altura deixa de
  ser o teto. **Quem cabe, remedido na segunda rodada (2026-09-04, pele clássica, roteiro do
  crítico):** a 1400×950 a aba Estudo tem 720 px e a barra 702; cabem **onze** das catorze
  principais -- Carregar OCR atual · Seguir OCR · Posição inicial | Promover · Rebaixar · Apagar
  variante · Símbolo · Dobrar | Salvar · Exportar ▾ | Treinar | Mais ▾ -- e Recorte, Linha do livro
  e Partidas estão no "Mais". Treinando, o botão vira "Parar o treino" (+35 px) e Dobrar cede a vez:
  dez. A 1600×1080 (barra 733) são doze; a 1920×1080 a aba abre com 804 px (barra 786) e cabem
  **as catorze**, com o "Mais" logo depois de "Treinar" e o vão à direita dele. A soma das larguras
  medidas (`largura_para_todas()`) é **777 px** na clássica, 725 na "Fita" (fonte menor: treze na
  fila a 702) e 812 treinando. Os números da rodada 1 ("oito a 900, onze a 1200") estavam errados
  -- medidos, eram seis e nove -- e valiam para catorze botões com texto; ver a tabela do crítico.
- Separador entre grupos; ícone vetorial em toda ação que pode virar botão; rótulo curto do
  catálogo ao lado do ícone; dica com rótulo longo, explicação e tecla. ✅
- `.md/.html/.rtf` viram "Exportar ▾"; a caixa "Seguir OCR selecionado" vira ação marcável no
  grupo Posição, nascendo marcada como antes. ✅
- Sem estudo, Variante e Exportar ficam cinza; treinando, Variante fica cinza; Posição e Treino
  nunca desligam. A condição própria da dobra (S-516) e do recorte (S-347) soma-se à do grupo. ✅
- Nenhum slot muda: `comandos.acoes_fora_do_catalogo(COMANDOS_DA_ABA)` continua vazio, a tabela
  cobre a aba inteira menos a navegação, e disparar cada `QAction` chama `executar` com o nome. ✅
- O catálogo continua sem `icone` para os comandos da sala além dos quatro de navegação: a fita da
  janela não muda. ✅ `tests/test_ui_icones.py` inalterado (dezenove em `ICONES`).
- O clique de mouse em "Treinar" liga o treino. ✅ (Defeito pré-existente, fechado de graça.)
- `qt/janela.py` não é tocado; `qt/painel_do_pdf.py` é da S-528. ✅

### Testes

- `tests/test_ui_barra_da_sala.py` (puro): cobertura nos dois sentidos contra `COMANDOS_DA_ABA`;
  método para toda ação e nenhum para o agrupador; ids únicos, nenhum grupo vazio, prioridades
  únicas; principal/Mais/submenu como partição; rótulo e papel lidos do catálogo; dica com tecla;
  quem alterna no método; ponte com `ICONES_DA_SALA` nos dois sentidos, caixa `0..100`, e o catálogo
  sem ícone novo; os três modos; `cabem` por prioridade, em prefixo, com o separador na conta e o
  "Mais" nunca fora; o módulo não importa toolkit.
- `tests/test_qt_barra_da_sala.py`: `QAction` com ícone e dica para toda ação; fila única, estreitar
  manda para o "Mais" e alargar devolve; texto ao lado do ícone; "Exportar ▾" com os três; disparo
  chega ao `executar` com o nome (afirmado pelo efeito, e não por `patch` depois do `connect`); o
  interruptor do catálogo devolve o estado antes de chamar; papel no botão e regras na folha; modo e
  condição se somam; sem motor não há grupo. No painel: o **clique de mouse** em "Treinar" liga uma
  vez; toda ação chega ao método; cinza sem estudo e treinando; os nomes antigos são as ações.
- As guardas gerais: `barra_da_sala.py` entrou em `SEM_TKINTER` (`test_editor_model`); em
  `test_ui_orfaos.SEM_CHAMADOR` entraram, com motivo, a tabela `ACOES`, os três valores de `modo`,
  o agrupador `EXPORTAR_ESTUDO` e `ICONES_DA_SALA`; `principais`/`secundarias` ganharam chamador no
  widget, `NAVEGACAO` no painel, e `EXPORTAR` e `tracos_de` saíram do `__all__` (uso interno).
- `tests/test_qt_painel_de_estudo.py::ArranjoTests`: "três fileiras" virou "uma fila e nenhuma
  `BarraFluida` no topo"; a navegação continua sob o tabuleiro (agora procurando `QPushButton`).
- **Segunda rodada.** Puros: `test_a_unica_prioridade_repetida_e_o_par_promover_rebaixar`,
  `test_tres_com_texto_e_o_resto_so_com_icone`, `test_o_treino_esta_entre_as_tres_primeiras_prioridades`,
  `test_indexar_base_mora_no_mais_sob_o_grupo_base`, `test_a_dica_comeca_pelo_rotulo_longo_com_a_tecla_na_mesma_linha`,
  `test_as_quatro_teclas_da_sala_chegam_a_dica`, `test_a_16_px_todo_traco_tem_pixel_forte_e_glifo_de_12_px`
  (≥ 8 pixels com alfa ≥ 200 e glifo ≥ 12 px; medido: o mais fraco tem 11 e o mais estreito 13),
  `CabemTests::test_itens_de_mesma_prioridade_entram_juntos_ou_nao_entram`; em `test_ui_atalhos`,
  `TabelaDaSalaTests` (as quatro, sem colisão com as outras duas tabelas; `acelerador` responde e
  `acao_de` não). Qt: `test_o_marcado_desenha_diferente_do_desmarcado` (diff de pixels do `grab()`
  com a folha aplicada, sob `offscreen`), `test_o_mais_tem_cabecalho_de_grupo_visivel`,
  `test_o_mais_fica_logo_depois_do_ultimo_botao` (≤ 40 px), `test_o_par_promover_rebaixar_entra_e_sai_junto`
  (varrendo larguras), `test_o_texto_que_cresce_repergunta_a_cabem_sem_resize`,
  `test_a_tecla_da_sala_esta_na_qaction_com_alcance_de_widget`, `test_o_texto_ao_lado_do_icone_so_em_quem_a_tabela_manda`;
  no painel, `test_treinar_fica_na_fila_e_marcado_enquanto_treina`, `test_a_tecla_da_sala_chega_ao_metodo_e_respeita_o_modo`
  (`QTest.keyClick` de `Ctrl+↑` e `Ctrl+Del` com o foco no tabuleiro) e
  `test_indexar_base_chama_o_indexador_com_a_janela_e_o_busy`. Em `test_qt_tema`,
  `test_o_botao_de_ferramenta_marcado_tem_face_e_moldura_de_enfase` nas duas peles; em
  `test_qt_atalhos`, as quatro traduzem; `test_qt_legenda` espera as da sala depois das da janela;
  `test_ui_comandos` registra `indexar_base` entre os rótulos divergentes.

### O que o crítico recusou

**Rodada 1 (2026-09-04), reprovada para AAA.** Os sete achados e o que mudou em resposta:

| # | Achado do crítico (medido) | Resposta (segunda rodada) |
|---|---|---|
| 1 | **Estado marcado invisível**: "Seguir OCR" marcado e "Treinar" ligado desenhavam **0** pixels diferentes do desmarcado -- só havia `:checked` para `QPushButton`. | `QToolButton:checked` na folha: face na mistura mais funda do cromo e moldura de 1 px na cor de ênfase, nas duas peles; `:hover`/`:pressed` e moldura transparente permanente para o conteúdo não se mover. Provado por diff de pixels do `grab()` (`test_o_marcado_desenha_diferente_do_desmarcado`). |
| 2 | **"Mais" sem cabeçalhos**: `addSection` no `windows11` desenha só a linha; "Posição / Variante / …" não apareciam. | Título de cada grupo como **item desabilitado em negrito** (`PROPRIEDADE_DE_CABECALHO`), separador entre grupos; `cabecalhos_do_mais()` e teste que afirma os seis títulos, e os sete quando tudo transborda. Submenu por grupo foi descartado: esconderia a um clique a mais o que o "Mais" existe para deixar a um. |
| 3 | **Densidade e hierarquia**: a 1400×950 só 5 de 14 na fila, a 1920×1080 seis com ~110 px vazios antes do "Mais"; "Treinar", "Exportar", "Salvar", "Posição inicial" no "Mais"; treinando, nada sinalizava o modo; "Promover" sem "Rebaixar". | Dois níveis (`com_texto`: três com texto, onze só ícone, recheio de 4 px no nível de ícone), prioridades pela frequência com Treinar em 3 e marcado enquanto treina, par Promover/Rebaixar em bloco, "Salvar PGN" → "Salvar", "Mais" logo após o último botão, rearranjo quando o texto cresce. **Medido: 1400×950 → 11 na fila (10 treinando); 1920×1080 → as 14, vão de 0 px antes do "Mais".** |
| 4 | Chevron do "Mais" ~8 px abaixo da base do texto. | `QToolButton::menu-indicator` centrado à direita, com recheio reservado no `popupMode` instantâneo; conferido nas fotos (`fotos/executor_s527_r2/zoom_*`). |
| 5 | Ícones esmaecidos: desenhados a 32 e reduzidos a 16; "mais" com 0 pixels fortes. | Desenho no tamanho nativo (`escala` = `devicePixelRatio`), `TRACO_MINIMO` = 2 px, "simbolo" e "mais" como quadradinhos cheios, traço "indexar" novo; repintura na troca de pele. Régua no teste: ≥ 8 pixels fortes e glifo ≥ 12 px em todo traço da barra. |
| 6 | Dica repetia o rótulo e nenhuma ação tinha acelerador. | Primeira linha "rótulo · tecla"; `TECLAS_DA_SALA` (Ctrl+↑, Ctrl+↓, Ctrl+Del, Ctrl+M) ligadas na `QAction`, mostradas na dica, no menu e na legenda; guardas de atalho (`test_ui_atalhos`, `test_qt_atalhos`) estendidas à terceira tabela. |
| 7 | Fiação pendente da S-532 ("Indexar base") e `qt/dialogos.py` mandando rodar `cvoff-games --build-index`. | `indexar_base` no catálogo, no menu, em `COMANDOS_DA_ABA` e no grupo Base do "Mais"; `PainelDeEstudo.indexar_base` → `indexar_com_dialogo(window(), bases, busy=...)` com `terminou` no status; a caixa de "Partidas da base" oferece "Indexar agora". |

Fora do item, registrados como S-551 (vazio sob o tabuleiro) e S-552 (janela que não estreita); a
barra do PDF é da S-528.

## S-528 · A barra do painel do PDF na mesma gramática, e a página com mais área — ✅ **implementada em 2026-09-04**

### Problema

`qt/painel_do_pdf.py:152` e `:184` montavam **duas** `BarraFluida` com dezesseis controles de
texto -- catorze `QPushButton`, dois `QCheckBox` --, mais um `QLabel` com o nome do livro (`:158`)
e o par `QSpinBox` + `QLabel` da página (`:189`, `:193`). Nenhum ícone, nenhum separador, nenhuma
hierarquia, e o ajudante `_botao` (`:268`) ligava seis deles por `lambda` escrito no meio da
montagem.

**Medido em 2026-09-04, com a janela a 1400×950** (o painel do PDF tem 675 px): as duas barras
quebravam em **duas fileiras cada** e somavam **118 px** antes da folha; a 520 px -- que é o piso
do painel, `LARGURA_MINIMA_DO_VISOR` -- eram **três fileiras cada** e **176 px**. A folha ficava
com 621 px de altura a 1400×950 e 536 a 520 px de largura.

Ao lado disso, a sala de estudo recém-refeita (S-527) tem **uma** fila de 32 px com ícones de
16 px agrupados por tarefa. O crítico pôs as duas na mesma foto (`fotos/crit_r2/E_1400x950.png`):
*"a diferença de gramática entre as duas barras incomoda muito ao lado"* -- de um lado traços
agrupados, do outro "OCR todos diagramas" e "Roda vira a página" em caixas de texto que refluem.

### Solução

**A forma foi extraída, e não copiada.** `Acao`, `Item`, `cabem` e `dica_de` -- a linha de tabela,
a conta de quem cabe e a dica -- saíram de `ui/barra_da_sala.py` para `ui/barra.py`, que passa a
ter as **duas** formas de barra deste projeto: a que quebra (S-151) e a que enfileira (S-527). O
que decide qual tabela é qual são três `ClassVar` da subclasse -- `GRUPOS`, `IRMAS` e `METODOS` --,
e é isso que faz a mesma classe servir a duas barras sem que uma enxergue a outra. Do lado do
widget, `qt/barra_da_sala.BarraDaSala` virou `qt/barra.BarraEmFila`, que recebe a tabela e os
registros por argumento; `BarraDaSala` continua existindo como a subclasse de quatro linhas que a
sala e os testes da S-527 chamam pelo nome, e **a suíte da sala não mudou uma linha**.

**A tabela nova, `ui/barra_do_pdf.py`.** As dezesseis ações de `comandos.NAS_BARRAS_DO_PDF`,
inteira e nada além dela, em cinco grupos que são as cinco perguntas de quem lê um livro
digitalizado: **Livro** (abrir, abrir no leitor), **Página** (anterior, próxima), **Vista** (ajustar
à largura, à página, zoom, marcar diagramas, roda vira a página), **Leitura** (OCR do melhor
diagrama, da página, selecionar área, tirar a caixa) e **Exportar** (exportar, cancelar). Não são
os grupos do catálogo -- lá `pagina_anterior` é `VISUALIZACAO` e `ler_melhor` é `OCR`, porque a
pergunta de lá é *em que menu*. Rótulo, papel e tecla continuam vindo de `comandos` e `atalhos`;
nenhum texto é reescrito.

**Cinco decisões próprias desta tabela:**

1. **Duas com texto, e são as pontas do trabalho**: "Abrir PDF" é o que se faz antes de tudo, e
   "OCR melhor diagrama" é o que a tela existe para fazer -- o único `PRIMARIO` do painel, e a
   ênfase vem do catálogo (S-324). As outras oito principais são traço de 16 px com o rótulo e a
   tecla na dica.
2. **O par de página é um par** (mesma prioridade, entra e sai junto), e o campo `[21 de 289]`
   **não é ação**: é um `QSpinBox` pendurado na fila por `BarraEmFila.encaixar`, que o faz aparecer
   e sumir junto com as duas setas e o conta na reserva de `cabem`. O total virou **sufixo** do
   campo em vez de um `QLabel` ao lado -- eram dois widgets para um número, e o de fora não sabia
   sumir junto. As setinhas próprias do `QSpinBox` saíram: os dois botões colados nele fazem
   exatamente isso, com 16 px de traço em vez de duas meias-setas de 6 px.
3. **Os dois botões de zoom vão para o "Mais", e é decisão e não corte.** O deslizador logarítmico
   da S-225 fica logo abaixo da folha, com a porcentagem ao lado: `−` e `+` na fila seriam o
   terceiro controle do mesmo número na mesma tela. Continuam a um clique e em `Ctrl+-`/`Ctrl++`.
4. **Marcar diagramas e roda vira a página são preferências, não gestos**: dois itens marcáveis do
   "Mais" em vez de dois `QCheckBox` de ~230 px permanentes.
5. **O nome do livro sai da barra.** O rodapé da janela já escreve `1937 Kemeri.pdf · p. 21 de 289`
   em toda tela, e o rótulo daqui repetia isso em ~210 px de uma fila que não tinha para onde
   crescer. Quem responde "não há livro" agora é o campo de página com o total zerado e o grupo
   inteiro cinza.

**A regra de quem fica cinza passou a ser modo + condição**, como na sala: `SEM_LIVRO` desliga
Página, Vista, Leitura e Exportar e deixa Livro de pé (abrir é a saída deste modo); `TRANCADO`
desliga tudo **menos Exportar**, que é o que mantém o cancelar vivo -- ele só existe durante a
exportação, que é justamente quando tudo o mais está trancado. As três condições que só o painel
sabe (há livro, está trancado, está exportando) entram por `aplicar_modo`.

**Sete traços novos** em `icones.ICONES_DO_PDF` -- um terceiro dicionário, pela razão do segundo:
a chave de `ICONES` é nome de comando, e `medidas_da_fita.grupos()` põe na fita da janela todo
comando com `icone`. Nove das dezesseis **reusam** os traços que a S-220 desenhou para estes mesmos
comandos.

**`qt/janela.py` não foi tocado.** Os nomes pelos quais ele chama estes controles --
`pdf.marcar_diagramas.setChecked/.isChecked/.toggle`, `pdf.btn_exportar.isEnabled()` -- apontam
agora para as `QAction`s da fila, e `QAction` responde aos mesmos nomes.

### Critério de aceite

- A barra do painel é **uma fila** em qualquer largura, e nada some sem ir para o "Mais".
  ✅ `linhas == 1` a 300, 400, 520, 675, 900 e 1400 px; em toda largura `na_fila | no_mais` é a
  tabela inteira, e o botão "Mais" nunca fica escondido.
- **Altura devolvida à folha, medida em 2026-09-04** (roteiro `probe_fase80.py`, pele clássica):

  | janela | painel do PDF | cromo antes | cromo depois | folha antes | folha depois |
  |---|---|---|---|---|---|
  | 1400×950 | 675 px | 118 px (2+2 fileiras) | **32 px** | 621 px | **717 px** (+96) |
  | 1024 de largura | 520 px | 176 px (3+3) | **32 px** | 536 px | **690 px** (+154) |
  | 1920×1080 | 1014 px | 112 px (2+2) | **32 px** | 757 px | **847 px** (+90) |

  O piso do próprio painel caiu junto: `minimumSizeHint()` foi de `(175, 178)` para `(198, 146)`.
- **Quem cabe:** a 675 px ficam oito das dez principais mais o campo de página -- Abrir PDF |
  ◀ [21 de 289] ▶ | Ajustar à largura · Ajustar à página | OCR melhor diagrama · OCR todos ·
  Selecionar área | Mais ▾ --, com Exportar e Cancelar no "Mais"; a 520 px ficam cinco (o par de
  página, os dois de OCR e Selecionar área); a 1014 px cabem as dez. ✅
- Ícone vetorial em toda ação, dica com rótulo longo e tecla na primeira linha, separador entre
  grupos, "Mais ▾" com cabeçalho de grupo. ✅
- **A barra não registra tecla nenhuma**: as dezesseis são comandos da janela e já têm dono no
  menu; registrá-las de novo aqui daria duas donas para a mesma tecla. ✅ `sequencia_de` devolve
  `""` para todas, e o gancho existe porque na sala é o contrário (`TECLAS_DA_SALA`).
- "Selecionar área" é um **modo marcado**, e não um rótulo que troca: na fila ele desenha só o
  ícone, e um texto que troca onde não há texto não é sinal nenhum. O clique liga uma vez só. ✅
- `comandos.NAS_BARRAS_DO_PDF` continua batendo com o que o painel desenha, e a guarda que o cobra
  foi **traduzida** em vez de apagada: ela varria `_botao(barra, "…")` em `qt/painel_do_pdf.py` e
  agora varre `Acao("…")` em `ui/barra_do_pdf.py`, com um `assertTrue(desenhadas)` na frente para
  que ela não passe em verde sobre lista vazia. ✅
- A suíte da sala continua verde sem uma linha alterada. ✅ `qt/janela.py` não é tocado. ✅
- **Fica de fora**: a linha de anotação de campo (`qt/campo.py`, 50 px), que o crítico contou como
  a quarta fileira. Ela não é cromo do painel do PDF -- é a anotação de conjunto da S-95, que
  afirma coisas sobre a página exibida -- e já é **uma** fila com um seletor e três botões.
  Trazê-la para a gramática é item próprio.

### Testes

- `tests/test_ui_barra_do_pdf.py` (novo, puro): cobertura nos dois sentidos contra
  `NAS_BARRAS_DO_PDF`; método do painel para toda ação; principal/"Mais" como partição; a única
  prioridade repetida é o par de página; duas com texto e uma ênfase só; o zoom e as preferências
  no "Mais"; rótulo e papel do catálogo; dica com a tecla na primeira linha; **`sequencia_de` vazia
  para todas, com um controle que falha se a sala parar de declarar tecla própria**; ponte com
  `ICONES_DO_PDF` nos dois sentidos, caixa `0..100`, nove traços reusados e a régua de 8 pixels
  fortes / glifo de 12 px a 16 px; os três modos e o `EXPORTAR` poupado no `TRANCADO`; e
  `FormaCompartilhadaTests`, que afirma que as duas tabelas não se enxergam -- grupo da sala numa
  ação do PDF levanta, `METODOS` é por tabela, e o agrupador "Exportar ▾" da sala não faz de
  `exportar_pgn` do PDF um menu vazio.
- `tests/test_qt_painel_do_pdf.py::FilaDoPdfTests` (novo): fila única em cinco larguras; nada some
  sem ir para o "Mais"; o campo de página aparece e some com o par de setas; o total como sufixo;
  `QAction` com ícone, dica e `checkable` conforme a tabela; nenhuma tecla registrada; o disparo
  chega ao método **pelo efeito** (e não por `patch` depois do `connect`, que não intercepta); e o
  cromo em 32 px a 520 de largura. Mais `test_o_primario_e_o_ultimo_a_sair_da_fila`, cuja largura
  de corte sai da própria barra -- sob `offscreen` não há a fonte da interface e cada botão mede
  mais.
- Nos testes que já existiam do painel: o estado vazio deixou de perguntar pelo rótulo do livro e
  pergunta pelo sufixo do campo e pelo grupo cinza; o modo de seleção é afirmado pelo **botão
  pressionado** (`test_o_modo_de_selecao_se_ve_no_botao_pressionado`), com
  `test_o_clique_no_botao_de_selecao_liga_o_modo_uma_vez_so` e
  `test_selecionar_sem_livro_nao_deixa_o_botao_pressionado`; o trancamento é medido item a item e
  ganhou `test_o_cancelar_continua_vivo_com_o_painel_trancado`.
- `tests/test_ui_comandos.py`: `_acoes_desenhadas` e o controle dela traduzidos para a forma da
  tabela; `PDF_PANEL` passou a apontar para `ui/barra_do_pdf.py`.
- `tests/test_ui_orfaos.py`: entraram `icones.ICONES_DO_PDF`, `barra_do_pdf.COM_LIVRO`,
  `barra_do_pdf.TRANCADO` e `barra_do_pdf.LEITURA`, com motivo. **`barra_da_sala.ACOES` saiu**, e
  não por ter ganhado chamador: a varredura é por identificador, e `qt/painel_do_pdf.py` passa
  `barra_do_pdf.ACOES` para a fila -- o nome passou a existir fora daquele módulo. É limitação
  conhecida do detector, está escrita lá, e quem continua cobrando a tabela da sala é
  `tests/test_ui_barra_da_sala.py`.

### O que o crítico recusou

_a preencher pelo crítico_

## S-529 · O painel do motor: barra de avaliação vertical, linhas MultiPV clicáveis, profundidade — ✅ **implementada em 2026-09-04**

### Problema

A sala tinha motor e não tinha painel de motor. `qt/painel_de_estudo.py:630` (`_secao_do_motor`)
punha a avaliação num `QProgressBar` **horizontal** de 0 a 100, dentro da seção "Motor" -- que fica
na coluna de leitura, **sob** a caixa de comentário, a ~400 px do tabuleiro. `:636` punha as linhas
do MultiPV num `QLabel` de texto cinza, montado em `:915` (`_mostrar_avaliacao`) como
`f"{indice}. {display}  {' '.join(pv_san)}"`.

Quatro consequências, e nenhuma é de gosto:

1. **A barra não era lida junto com o tabuleiro.** Ela existe para dizer *de quem é a posição* com
   o rabo do olho, e para isso precisa estar ao lado do tabuleiro e ter a altura dele -- é o que o
   Lichess faz e o que a ChessBase faz. Horizontal e a meia tela de distância, ela é um enfeite.
2. **`QLabel` não responde ao clique.** `variante_do_motor` (`:1833`) lê `self._candidatos[0]`
   (`:1843`) e **só** ele: as linhas 2 e 3 apareciam na tela e não havia caminho nenhum para
   pô-las na árvore. Isso anula metade da razão de o MultiPV existir -- a S-286 registra que a
   pergunta de quem estuda um livro é *se o lance que o livro dá está entre os candidatos*, e
   comparar exige poder guardar a comparação.
3. **A profundidade estava escondida e os nós não existiam.** `Evaluation.depth` só aparecia dentro
   de `summary()`, na mesma frase da avaliação e do melhor lance; `nodes` e `nps` não eram lidos do
   UCI. Sem eles não há como ver da tela que a opção `Threads` pegou (S-536).
4. **A variante não era numerada.** `' '.join(pv_san)` dá `Ba4 Nf6 O-O` ao lado de uma lista de
   lances que diz `12. Ba4`: comparar as duas obriga a contar nos dedos onde a linha começa.

### Solução

**A decisão pura, `ui/motor_declarado.py`.** Altura da faixa em pixel (`altura_de_brancas`), a cor
de cada lado (`papel_do_lado`), a numeração da variante (`variante_numerada`, `linhas_do_motor`) e
a frase de desempenho (`frase_de_desempenho`, `numero_curto`). Quatro decisões, e as quatro têm
motivo escrito:

1. **A curva não é escrita ali, e isso é o item.** Ela já existia como
   `Evaluation.advantage_fraction`; virou `engine.fracao_de_vantagem`, função de módulo, porque
   **três** desenhos a usam agora -- a barra, o gráfico da partida inteira (S-537) e o `display` de
   cada linha. Três cópias divergiriam na primeira vez que alguém ajustasse uma, e o sintoma seria
   a barra discordando do número escrito ao lado dela. A curva é `1/(1+10^(-cp/400))`, a expectativa
   de pontuação do Elo; a do Lichess é `2/(1+e^(-0,00368208·cp))-1`. A grade de comparação está no
   cabeçalho de `ui/motor_declarado.py`: a daqui é mais íngreme no miolo (+1,00 dá 0,640 contra
   0,591) e satura antes (+5,00 dá 0,947 contra 0,863). **A diferença é a decisão**: numa sala de
   estudo o que se lê a metro de distância é de quem é a posição, e a curva do Elo é literalmente
   a probabilidade de ganhar aquele final; a do Lichess reserva mais barra para a faixa acima de
   +5, em que a partida já acabou.
2. **Mate em cor própria, e não barra cheia.** A barra cheia já quer dizer +8. O que separa "está
   ganho" de "acaba em três lances" é a cor, e só a faixa de **quem dá** o mate muda -- dois âmbares
   empilhados não diriam quem mateia. A cor é `tokens.ATENCAO`; as duas faixas normais são
   `tokens.GLIFO_CLARO` e `GLIFO_ESCURO`, a tinta das **peças**, que não segue pele: uma faixa "das
   brancas" que escurecesse junto com a janela deixaria de dizer isso.
3. **O clique numa linha insere a variante**, com a procedência no PGN, a partir do lance corrente.
   É o gesto da ChessBase ("arrastar a linha do motor para a notação"), com o clique no lugar do
   arrasto -- e é o caminho que a sala já tinha, generalizado de `[0]` para `[n]`. **A alternativa
   medida e recusada** foi o clique mover o tabuleiro: com a análise contínua ligada o motor
   responde a cada ~800 ms, e um tabuleiro que seguisse a linha sairia da posição, faria o motor
   recomeçar noutra e a lista mudaria debaixo do cursor de quem ia clicar na segunda. **E o lance
   corrente não se move**, que é o outro lado da mesma decisão: quem clica na primeira quase sempre
   quer clicar na segunda em seguida, e as duas ficam na árvore sob a mesma posição.
4. **A numeração começa no lance corrente.** `12. Ba4 Nf6 13. O-O`, com a reticência quando as
   pretas jogam (`12... Nf6 13. Nc3`). A mesma função serve à variante que entra na árvore e à que
   só se lê, e é por isso que ela é uma só.

**O desenho, `qt/motor.py` (novo).** `BarraDeAvaliacao` é um widget de 18 px de largura, à
**esquerda** do tabuleiro, dentro da mesma fileira. Ele ocupa a fileira inteira e pinta a barra
exatamente sobre o quadrado do tabuleiro, perguntando `tabuleiro.geometria()` **no `paintEvent`**:
a primeira redação usava `setFixedHeight` no `resizeEvent` e a barra saiu com 240 px (o piso do
tabuleiro) ao lado de um tabuleiro de 425 -- a geometria de antes. `LinhasDoMotor` é um
`QTextBrowser` com uma âncora por linha, no mesmo mecanismo da lista de lances, e a quebra é
`WordWrap` com o número colado ao lance por `&nbsp;` (a regra da S-515 aplicada aqui: no modo de
fábrica ele partia `Qxg4` ao meio numa coluna de 203 px).

**Dois ajustes que a fotografia pediu.** A seção do motor passou a pesar `2` no divisor vertical
(era `1`): com três linhas e o rodapé de desempenho ela ficava com duas linhas e barra de rolagem
enquanto a lista de lances tinha metade da altura vazia. E `Evaluation` ganhou `nodes` e `nps`,
lidos do `info` do UCI.

**Sem motor, nada disso existe** -- nem a barra, nem a seção, nem o grupo Motor da fila. É o
contrato da S-33, e a barra entrou nele: pixels tomados do tabuleiro para mostrar o que nunca terá
número seriam pixels de promessa.

#### O que a segunda rodada trocou (2026-09-04)

O crítico reprovou o item em três pontos, e os três eram da **barra**. Os consertos:

1. **O mate deixou de ser a faixa e passou a ser o fio.** A barra de mate está cheia por
   construção (`fracao_de_vantagem` devolve 1 ou 0), então "pintar de âmbar a faixa de quem
   mateia" pintava a barra **inteira** de âmbar nos dois casos: `M3` e `-M3` saíam com **zero**
   pixel de diferença. Agora a faixa cheia é da cor **do lado** -- branca em `M3`, preta em `-M3`
   -- e o âmbar é a moldura, com o dobro da espessura. O que ele dizia continua sendo dito; mudou
   onde.
2. **A barra passou de 18 para 26 px e o rótulo perdeu o sinal.** Em Consolas 7pt -- a fonte de
   dado desta janela --, `-12,34` ocupa 30 px e `12,34` ocupa 25. Com 18 px o número saía cortado
   no meio, e um `12` sem sinal nem casas decimais **afirma outra avaliação**. O sinal sai porque
   a posição do número já o diz (embaixo = brancas melhor), que é a regra do Lichess; e o corpo da
   fonte desce de um em um ponto até caber. **O que nem no menor corpo couber não é escrito**:
   o número inteiro continua na seção do motor, e escrever cortado é pior que não escrever.
3. **O fio da barra passou a seguir a pele.** `tokens.MOLDURA` é superfície e escurece junto com o
   cromo: na pele Foco ela dava `#1f1d1b` sobre `#1f2124` -- **1,04:1** --, e a faixa preta dava
   **1,17:1**. A barra inteira sumia da janela escura. O fio agora é a tinta oposta ao fundo:
   `MOLDURA` (14,74:1) na pele clara, `GLIFO_CLARO` (15,20:1) na escura.

E quatro dos "deveria" dele:

4. **A lista MultiPV guarda o lugar.** `setHtml` troca o documento inteiro, e o motor responde a
   cada ~900 ms: quem tinha rolado até a nona linha ou selecionado uma para copiar perdia as duas
   coisas. Agora HTML igual **não** é redesenhado (o caso comum numa posição parada), e quando ele
   muda a rolagem e as pontas da seleção são repostas.
5. **As linhas saem ordenadas pela avaliação.** O MultiPV do Stockfish é a ordem da iteração
   anterior, e com dez linhas o crítico viu `-3,09` acima de `-3,04`. O índice **não** é
   reordenado junto: ele é a âncora do clique, e é a posição na lista que a sala guarda.
6. **A barra espelha com o tabuleiro** (`virado=`), como no Lichess. A sala passa a orientação
   desde 2026-09-04 -- ver a nota das três linhas, abaixo.
7. **`titulo_da_secao`** monta `Motor (Stockfish dev-20230303)` a partir do `id name` do UCI, em
   vez do nome do arquivo, e a seção o usa desde a mesma data.

### Critério de aceite

Medido em 2026-09-04 com o Stockfish desta máquina (`scid_windows_x64/engines/stockfish.exe`,
dev-20230303), roteiro `scratchpad/roteiro_motor.py`, na defesa de Legall após `5. Nxe5`.

- **A barra fica ao lado do tabuleiro e com a altura dele.** ✅ A 1400×950: barra de 18×475 px em
  `x=8`, tabuleiro em `x=36`, os dois quadrados coincidindo; a 1920×1080, 18×475 ao lado de um
  tabuleiro de 509. O custo em largura é **28 px** (18 da barra, 6 de vão, 4 de arredondamento):
  o tabuleiro vai de 488 px sem motor para 460 com barra, na mesma janela.
- **+2,00 e −2,00 desenham diferente**, e o meio da barra troca de cor. ✅ Medido em pixel:
  ≥ 1.000 pixels diferentes numa barra de 18×200, e `cor_em(3, 100)` responde `GLIFO_CLARO` num
  caso e `GLIFO_ESCURO` no outro.
- **Mate pinta em cor própria**, e só a faixa de quem mateia. ✅ `+20,00` e `M3` enchem a barra
  igual e diferem na cor (`GLIFO_CLARO` contra `ATENCAO`).
- **N linhas clicáveis, e o clique põe a variante na árvore.** ✅ Com `MultiPV 3`, as três linhas
  saem numeradas (`+1,63  5... dxe5 6. Qxg4 Nc6 7. d3 Nf6 8. Qf3`), e emitir o sinal da segunda põe
  `Be6` na árvore com `stockfish.exe: +1,78` no comentário de entrada. O lance corrente não muda.
- **Profundidade e nós por segundo visíveis.** ✅ `profundidade 19 · 2,5 MN/s · 3,0 M nós` no rodapé
  da seção. Com `Threads` de 1 para 2 no processo aberto, os nós por segundo vão de **1,34 MN/s**
  para **2,33 MN/s** -- é o número que prova que a opção pegou.
- **Sem motor, tudo some.** ✅ `vantagem is None`, o divisor vertical tem duas partes em vez de
  três, e a fila não tem `analise_continua`. O tabuleiro volta aos 488 px.
- **O que ficou de fora, e é a linha para o relatório**: a barra **não** aparece quando a sala
  ganha um motor pelas preferências no meio da sessão (S-536). A seção e a fila aparecem; a barra
  mora dentro do arranjo da coluna do tabuleiro, e recriá-lo mexeria na repartição que a S-551
  calcula. Ela chega na abertura seguinte.

#### Segunda rodada, medida em 2026-09-04

- **`M3` e `-M3` desenham diferente.** ✅ **6.504 pixels de 7.800** numa barra de 26×300 (era
  **0**), e a barra sozinha, sem rótulo, difere em 6.512. `M3` é `GLIFO_CLARO` de ponta a ponta e
  `-M3` é `GLIFO_ESCURO`; `M3` contra `+20,00` difere em 1.392 pixels, que é o fio âmbar de 2 px.
- **O rótulo cabe.** ✅ `1,61` e `1,72` legíveis dentro da barra nas fotos de 1400×950 e 1920×1080
  (ampliação 6×). O que não cabe não é desenhado: com um rótulo grande demais a barra fica
  **idêntica** à barra sem rótulo, medido em pixel.
- **A barra se vê na pele Foco.** ✅ Fio a **15,20:1** contra o fundo `#1f2124` (era 1,04:1), e a
  foto da sala mostra a barra ao lado do tabuleiro nas três peles. O fio de mate fica em 5,20:1
  (clara) e 5,09:1 (escura) -- os dois acima do piso de 3:1 para objeto gráfico.
- **A lista não volta ao topo.** ✅ Com `MultiPV 10` e a análise contínua: a rolagem fica onde
  estava e a seleção sobrevive (medido pelo reprodutor do crítico -- antes `''`, agora a mesma
  faixa de texto com o número atualizado).
- **As linhas saem ordenadas.** ✅ Na Ruy Lopez após `6...b5`, dez linhas em ordem crescente para
  quem joga; o crítico tinha `-3,09` acima de `-3,04`.
- **O custo do tabuleiro subiu 8 px** com a barra mais larga: de 18 para 26 px de barra.

### Testes

- `tests/test_ui_motor_declarado.py` (novo, puro): a curva é a de `engine` e não uma segunda; a
  barra reparte ao meio no equilíbrio e é simétrica; a escala não é linear, medida; o mate enche e
  pinta só a faixa de quem mateia; as cores são a tinta das peças; a variante sai numerada com e
  sem reticência; a linha sem lance nenhum não vira linha; a frase de desempenho traz os três
  números e omite o que o motor não relatou; `numero_curto` em vírgula decimal.
- `tests/test_qt_motor.py::BarraDeAvaliacaoTests` (novo): os cinco casos em pixel, com
  `renderizar`/`pixels_diferentes`/`cor_em` de `tests/qt_app.py`.
- `tests/test_qt_motor.py::PainelComMotorTests` (novo): a barra fica à esquerda e na altura do
  tabuleiro; a análise enche barra, linhas e desempenho; **o sinal da linha clicada chega à
  árvore**; a procedência entra no PGN; o lance corrente não se move; pedir uma linha que o motor
  não deu vira frase de rodapé.
- `tests/test_engine.py::test_o_mate_ja_dado_aponta_para_quem_o_deu` (novo): ver a S-537 -- o
  defeito era da barra também.

Na segunda rodada, em `tests/test_qt_motor.py::BarraDeAvaliacaoTests`: `M3` e `-M3` diferindo em
mais de metade da barra e cada um na cor do seu lado; o fio de mate em âmbar e com 2 px; o fio
mudando de papel com o cromo, medido no pixel e não na constante; a barra espelhando com o
tabuleiro virado; e o rótulo grande demais **não** sendo desenhado. Em
`tests/test_qt_motor.py::LinhasDoMotorTests` (novo): a rolagem e a seleção sobrevivendo à resposta
seguinte, e o HTML igual não redesenhando (o mesmo `QTextDocument` antes e depois). Em
`tests/test_ui_motor_declarado.py`: o contraste do fio nas duas peles calculado no teste, o rótulo
sem sinal, o título com o nome UCI, a frase do binário que não é motor, e a ordenação das linhas
com o índice **não** reordenado junto.

### O que o crítico recusou

Primeira rodada, 2026-09-04. Reprovada em três pontos; os reprodutores dele estão em
`scratchpad/crit_motor/` (`crit_mate.py`, `crit_barra.py`, `crit_linhas.py`).

| O que ele achou | Como estava | O que mudou |
|---|---|---|
| **`M3` e `−M3` desenham a mesma barra** — 0 px de diferença, âmbar cheio nos dois | o mate pintava a **faixa** de quem mateia, e a faixa de mate é a barra inteira | a faixa cheia passou a ser a cor **do lado**; o âmbar virou o fio, com 2 px. Medido: 6.504 px de 7.800 diferentes |
| **O rótulo sai cortado e perde o sinal** — `−12,34` vira `12` (precisa de 25 a 30 px, há 18) | barra de 18 px e rótulo com sinal, em Consolas 7pt | barra de 26 px, rótulo **sem sinal** (a posição já o diz), corpo que desce até caber, e nada desenhado quando não cabe |
| **Na pele Foco a barra some** — faixa a 1,17:1 e moldura a 1,04:1 contra o fundo | o fio era `tokens.MOLDURA`, que é superfície e escurece com o cromo | o fio segue a pele: `MOLDURA` na clara (14,74:1), `GLIFO_CLARO` na escura (15,20:1) |
| A barra não vira com o tabuleiro | nada perguntava pela orientação | `BarraDeAvaliacao(virado=...)`, perguntado no `paintEvent` como a caixa. A sala passa `lambda: self.estudo.invertido` desde 2026-09-04 — ver abaixo |
| A lista MultiPV volta ao topo a cada resposta (~0,9 s), perdendo rolagem e seleção | `setHtml` a cada resposta | HTML igual não redesenha; quando muda, rolagem e seleção são repostas |
| As linhas não estão ordenadas por avaliação (`−3,09` acima de `−3,04` com MultiPV 10) | a ordem era a que o motor devolveu, que é a da iteração anterior | `linhas_do_motor` ordena pela avaliação do lado que joga, **sem** reordenar o índice (ele é a âncora do clique) |
| Não dá para copiar uma linha (o `setHtml` apaga a seleção) | idem | as pontas da seleção são anotadas e repostas |
| O título diz `Motor (stockfish.exe)` em vez do nome UCI | o título usava `path.name` | `motor_declarado.titulo_da_secao` monta `Motor (Stockfish dev-20230303)`, e a seção o chama desde 2026-09-04 — ver abaixo |

**As linhas que faltavam, escritas em 2026-09-04.** As três moravam em `qt/painel_de_estudo.py`, e
a Fase 83 estava escrevendo naquele arquivo -- o executor da S-529 foi instruído a não abri-lo.
Assim que ele ficou livre elas entraram, e `motor_declarado.titulo_da_secao` saiu de `SEM_CHAMADOR`
em `tests/test_ui_orfaos.py` (a catraca continua em zero):

1. `BarraDeAvaliacao(coluna, caixa=self._caixa_do_tabuleiro, virado=lambda: self.estudo.invertido)`
   em `_esquerda` (a barra espelhar). **Faltava mais que o parâmetro**: `flip_board` não mandava a
   barra repintar, e ela só descobriria a virada na resposta seguinte do motor -- numa sala sem
   análise contínua, nunca. `flip_board` passou a chamar `vantagem.update()`, como o `resizeEvent`
   já fazia.
2. `QGroupBox(motor_declarado.titulo_da_secao(self._analyzer.name, self._analyzer.path.name), pai)`
   em `_secao_do_motor`, e a mesma troca ao trocar de binário. **E uma terceira chamada**, porque o
   nome UCI chega depois da montagem: o processo só sobe na primeira análise (é decisão de
   `motor_das_preferencias`, para não pagar 100 a 300 ms de quem não pediu avaliação), então na
   hora de desenhar a seção `EngineAnalyzer.name` ainda responde o nome do arquivo. Sem o
   `_mostrar_o_titulo_do_motor` no fim da análise, as duas linhas ficariam escritas e o título
   continuaria dizendo `Motor (stockfish.exe)` na sessão inteira.

Testes: `tests/test_qt_motor.py::PainelComMotorTests`
(`test_a_barra_da_sala_espelha_quando_o_tabuleiro_e_virado`, em pixel sobre a barra do painel, e
`test_o_titulo_da_secao_traz_o_nome_que_o_motor_diz`, com o `id name` do motor falso).

## S-530 · O cabeçalho da partida (jogadores, Elo, evento, data, resultado) visível e editável — ✅ **implementada em 2026-09-04**

### Problema

A sala tinha os headers e não os mostrava. `estudo.py:463-478` (`Estudo.de_posicao`) escreve
`Event`, `Site`, `Result`, `Annotator`, `Round`, `SourcePDF`, `Page`, `Diagram` e `Caption`; um
estudo aberto de um `.pgn` traz `White`, `Black`, `WhiteElo`, `BlackElo`, `Date` e `ECO` junto
(`estudo.py:497` `de_jogo`); a busca na base (S-533) devolve partidas com os oito de
`games_db.py:141` (`_KEPT_HEADERS`); e `Estudo.para_pgn` (`estudo.py:511`) exporta todos eles.

Nada disso chegava à tela. `qt/painel_de_estudo.py:344` (`_esquerda`) desenhava tabuleiro, faixa
de navegação, recorte, `lbl_origem`, `lbl_status` e o campo de FEN, e **nenhum dos nove campos**.
Quem abrisse Capablanca–Alekhine na sala via um tabuleiro sem nome, sem torneio e sem resultado --
e, exportando, gravava de volta um PGN cujos headers ele nunca pôde conferir nem corrigir. O
ChessBase põe a linha acima do tabuleiro e abre "Game data" com duplo clique.

### Solução

**A decisão pura, `ui/cabecalho_da_partida.py`.** Nove campos na ordem do "Game data" -- que é a
ordem em que se copia a legenda de um livro, e não a alfabética: Brancas/Elo, Pretas/Elo, Evento,
Local, Data, Rodada, Resultado. Três decisões, e as três são de dado:

1. **Os nove não são os oito de `_KEPT_HEADERS`.** Faltam lá os dois `Elo` -- aquela lista é a do
   que o *índice* guarda por partida, e Elo não é chave de busca ali; na sala eles são metade da
   pergunta "que partida é esta?". `ECO` vai no sentido contrário e fica **fora** do formulário:
   ele é deduzido da posição (S-534) e já aparece na faixa sob o tabuleiro -- um campo editável ao
   lado de uma dedução automática é o par de valores que diverge.
2. **Vazio é o valor de fábrica do formato, e não a ausência da chave.** `del jogo.headers["White"]`
   tira a etiqueta do jogo, e o PGN exportado sai sem ela -- inválido para qualquer leitor. Um
   campo esvaziado grava o vazio **daquele** campo (`?`, `????.??.??`, `*`), e só os dois `Elo`,
   que não são obrigatórios, somem de verdade. `OBRIGATORIOS` é conferido contra o próprio
   `chess.pgn.Game().headers`, e não escrito de novo.
3. **A frase tem duas linhas, e a segunda é a secundária**: `Capablanca, J (2720) — Alekhine, A
   (2690) · 1-0` numa, `Kemeri · Kemeri LAT · 24/06/1937 · rodada 12` na outra. É a hierarquia do
   ChessBase, e é o que faz a faixa caber em 494 px -- a largura da coluna a 1400×950.

Mais duas que a medição pediu: **a data parcial vira o que dá para ler** (`1937.??.??` → `1937`,
`1937.06.??` → `06/1937`), porque a maior parte do acervo só tem o ano e mostrar a sintaxe do
formato não responde nada; e **o que o próprio programa escreveu não conta como dado**.
`Estudo.de_posicao` põe `Event = "ChessVisionOFF Estudo"`, `Site = "Local"` e
`Round = "{página}.{diagrama}"`: acima do tabuleiro isso é ruído com cara de dado -- `rodada 21.1`
num livro de torneio parece a vigésima primeira rodada, e o livro tem catorze. Os três somem da
**frase** e continuam no **formulário**, porque ali a pergunta é outra: o que está gravado no PGN.
Sem essa distinção, "Gravar" sem tocar em nada apagaria o header que o resto do projeto escreve.
O literal `"Local"` ganhou nome (`estudo.LOCAL`) por ter passado a ter dois leitores.

**O desenho, `qt/painel_de_estudo.py`.** Uma faixa acima do tabuleiro com os dois rótulos e um
botão de lápis à direita. Os rótulos são `_RotuloElidido`, um `QLabel` de uma linha que corta o
próprio texto com `…` **no `resizeEvent` dele** -- elidir na hora de escrever não funciona, e foi
medido: `_mostrar_cabecalho` roda dentro de `refresh`, que é chamado na montagem, e ali o rótulo
ainda tem a largura de fábrica; a frase saía como `Jogadores nã...` numa faixa de 494 px. A dica
carrega a frase inteira. Duplo clique em qualquer das duas linhas abre o mesmo diálogo.

**O botão existe porque não há comando.** Editar o cabeçalho ainda não está em `ui/comandos.py`,
então não há item de menu, tecla nem entrada na paleta -- e uma faixa que só responde a duplo
clique é uma função que ninguém acha. O lápis é a afirmação de que aquilo é editável; o traço dele
mora em `ICONES_DA_SALA` com a chave que `cabecalho_da_partida.ICONE` declara, e não com a de um
comando que não existe.

**O diálogo, `_JanelaDoCabecalho`.** Um `QComboBox` para o resultado -- `1:0`, `1-0 ` e `1–0` com
travessão são o que se digita sem querer, e qualquer um faz o PGN ser recusado -- e campo livre
para os outros oito, com os dois `Elo` estreitos na mesma linha do jogador. "Gravar" chama
`_gravar_cabecalho`, que escreve **só o que mudou** (`mudancas`) e trata a mudança como edição da
sala: `_marcar_sujo` empilha o PGN inteiro no histórico e agenda a gravação por inatividade. Com
isso o `Ctrl+Z` que já existia para a árvore devolve o cabeçalho pelo mesmo caminho, sem uma
segunda pilha, e o `salvar_agora` leva os headers junto -- eles já estão em `Estudo.para_pgn`.

### Critério de aceite

- A faixa aparece acima do tabuleiro e mostra o que o PGN tem. ✅ Medido a 1400×950: 38 px de
  altura, duas linhas, e a coluna do tabuleiro continua com 494 px.
- Sem jogadores ela **diz o que falta** em vez de ficar em branco (`Jogadores não informados`), e a
  segunda linha vazia não ocupa altura. ✅ Uma faixa em branco acima do tabuleiro é espaço que
  ninguém sabe que é editável.
- Um estudo aberto de um diagrama do livro não anuncia o programa: `ChessVisionOFF Estudo · Local ·
  rodada 21.1` não aparece. ✅
- Nome longo é elidido à largura de agora e volta ao alargar; a dica traz a frase inteira. ✅
- O diálogo abre com o que está gravado, sem o `?` do padrão nos campos, e grava nos headers. ✅
  Medido no roteiro: `Capablanca, José Raúl (2720) — Alekhine, Alexander (2690) · 1-0` /
  `Kemeri · Kemeri LAT · 24/06/1937 · rodada 12`, e o PGN exportado traz `White`.
- **`Ctrl+Z` desfaz a edição do cabeçalho** e `salvar_agora` a leva ao disco. ✅ `edicao` sobe de
  0 para 1 na gravação, e desfazer devolve `Jogadores não informados`.
- "Gravar" sem tocar em nada **não** cria passo de desfazer. ✅ Afirmado com o jogo recém-criado,
  com o estudo de um diagrama e com uma partida inteira.
- Esvaziar uma das sete etiquetas obrigatórias não tira a chave do jogo; esvaziar um `Elo` tira. ✅
- **Fica de fora, e é a linha para o relatório**: item de menu, tecla e entrada na paleta para
  "Editar o cabeçalho". Isso exige uma linha em `ui/comandos.py`, que outro executor está
  reescrevendo nesta sessão; o gancho está pronto -- basta o comando e uma linha em
  `sala_declarada.COMANDOS_DA_ABA` apontando para `editar_cabecalho`, e a ação entra na barra da
  sala, no menu e na paleta sozinha (S-280).

### Testes

- `tests/test_ui_cabecalho_da_partida.py` (novo, puro): os nove campos e a ordem deles; o que o
  formulário acrescenta a `_KEPT_HEADERS` e o que deixa de fora; só o resultado tem lista fechada;
  `OBRIGATORIOS` conferido contra `chess.pgn.Game().headers`; o vazio de cada campo; **esvaziar uma
  obrigatória não tira a chave**; o `?` não vai para o campo; "Gravar" sem mexer não muda nada, nos
  três estados; o que o programa escreve aparece no formulário e não na frase; as duas linhas com a
  partida inteira; o Elo sozinho e o nome sozinho; a rodada que é coordenada do livro; a data
  parcial nos quatro formatos e a escrita à mão que volta como veio; o que é gravado sobrevive à
  ida e volta pelo PGN; e o módulo sem toolkit.
- `tests/test_qt_painel_de_estudo.py::CabecalhoDaPartidaTests` (novo): a faixa mostra o que o PGN
  tem; sem jogadores ela continua visível e a segunda linha some; o nome longo é elidido e a dica
  traz a frase inteira; o lápis tem traço e dica; o diálogo abre com o gravado; **gravar escreve
  nos headers, aparece na faixa, entra no PGN e entra no desfazer** -- e o `Ctrl+Z` devolve;
  gravar sem mudar nada não cria passo; um editor por campo.
- `tests/test_ui_barra_da_sala.py::test_nenhum_traco_da_sala_e_orfao` passou a contar o traço do
  cabeçalho entre os usados: ele é da sala e quem o pede não é a tabela da barra.

### O que o crítico recusou

_a preencher pelo crítico_

## S-531 · Ler `.pgn.gz`, `.pgn.bz2` e `.zip` de PGN sem descompactar para o disco — ✅ **implementada em 2026-09-04**

### Problema

`games_db.py:189` listava a pasta com `pasta.glob("*.pgn")`: um `.pgn.gz`, um `.pgn.bz2` ou um
`.zip` com PGN dentro eram invisíveis, e a única saída era descompactar -- uma gigabase de 8,6 GB
ocupa ~1,5 GB em `.gz`, e pedir 7 GB de disco por um arquivo que a pessoa já tem é o que este item
existe para não pedir. Os `open()` de PGN estavam espalhados em quatro lugares e com três
decodificações diferentes: `games_db.py:543` (`open("r", encoding="utf-8-sig", errors="replace")`,
a busca por nome), `:726` e `:769` (`open("rb")` com `linha.decode("utf-8", "replace")` nos pedaços
da busca por posição), `games_index.py:183` e `:335` (o índice e a consulta por offset). Nenhum
deles registrava a decisão de codificação, e `Kieseritzky` em Latin-1 -- o comum em PGN antigo e em
boa parte do que circula em `.zip` -- saía `Kieseritzk�` na tela: a conferência de sobrenomes
ainda casava, mas o nome mostrado vinha com o losango.

### Solução

**Um leitor, `games_db.FluxoDePGN`/`abrir_pgn_bytes`/`abrir_pgn`.** O arquivo físico é aberto em
bytes e envolvido num `_ArquivoContado`, que conta o que saiu do disco; por cima dele vai
`gzip.GzipFile`, `bz2.BZ2File`, `zipfile.ZipFile(...).open(membro)` ou, se o pacote opcional
`zstandard` estiver instalado, um `BufferedReader` sobre `ZstdDecompressor().stream_reader`. O
resto do módulo não sabe de onde as linhas vieram: `tell()`/`seek()` são do **fluxo
descompactado**, então um offset gravado no índice vale igual para o mesmo arquivo comprimido, e
`bytes_lidos` é a posição **comprimida** -- a única comparável ao tamanho do arquivo, e por isso a
régua do progresso da S-532. `LinhasDePGN` é o mesmo fluxo em texto, linha a linha.

**Um membro de `.zip` é uma base por si**, com um `Path` da forma `pasta/base.zip/dentro/x.pgn`
que não existe no disco -- e é isso que o distingue de um arquivo (`_membro_de_zip`). `nome_da_base`
devolve `base.zip/dentro/x.pgn`, que é a identidade no índice: dois `.zip` podem ter um `games.pgn`
cada, e um `games.pgn` solto ao lado. `existe_base`, `tamanho_da_base` (bytes **no disco**,
`compress_size` para o membro) e `arquivo_fisico` são o `is_file()`/`stat()` que também valem para
o membro; os `is_file()` de `scan_by_positions`, `lookup_pair` e `cli/games._bases` passaram a
usá-los. `database_paths` enxerga `EXTENSOES_DE_BASE` sem ligar para caixa, expande cada `.zip` nos
seus membros `.pgn`, e deixa `.pgn.zst` de fora com aviso quando não há `zstandard` -- listar o que
não se sabe abrir seria uma base que falha na primeira busca.

**A decisão de codificação, em `decodificar_linha` e registrada no docstring dela.** UTF-8 estrito
primeiro (é o caminho rápido em C, e custa o mesmo que `replace` numa linha válida); só a linha que
falha paga a segunda decodificação, em **cp1252** e não latin-1, porque é o que o Windows gravou: as
aspas tipográficas e o travessão dos comentários são controle em latin-1. Por linha e não por
arquivo, porque a gigabase desta máquina mistura as duas coisas no mesmo `.pgn`. A marca de bytes
(`_BOM`) cai antes. Todo `open()` de PGN do projeto passa por aqui: `_collect_players`,
`_scan_positions_chunk`, `build_index`, `_read_game_at`.

**O preço, dito em `EXTENSOES_DE_BASE`.** Um fluxo comprimido não tem `seek` barato: voltar é
recomeçar do zero. `chunk_bounds` trata a base comprimida como **um pedaço só**, `(0, SEM_FIM)` --
ela ocupa um processo enquanto os outros repartem as soltas --, e `lookup_pair` lê os offsets em
**ordem crescente** para pagar uma descompactação por consulta. Quem consulta muito, descompacta;
quem guarda, comprime. O programa aceita os dois.

### Critério de aceite

- `database_paths` lista `.pgn`, `.pgn.gz`, `.pgn.bz2` e cada membro `.pgn` de um `.zip`, em ordem
  por nome; o `.txt` de dentro do `.zip` fica de fora; `.pgn.zst` só com `zstandard`. ✅
- As linhas saem **idênticas** venham de onde vierem, e a pasta fica como estava depois de ler:
  nada é gravado no disco. ✅
- A busca por nome e a busca por posição leem a base comprimida; a comprimida é um pedaço só. ✅
- Um offset do fluxo descompactado leva à mesma partida no `.bz2` que no arquivo solto. ✅
- `bytes_lidos` é menor que o descompactado e não passa do tamanho do arquivo. ✅
- Linha em cp1252 sai sem losango; UTF-8 continua UTF-8; a BOM cai. ✅
- `.zip` ilegível avisa e fica de fora, sem derrubar a listagem. ✅
- **Medido em 2026-09-04**, `Endgame_Study_Database_VI_...pgn` (62 MB, 93.839 partidas)
  comprimido em `.gz` (17,9 MB): índice do zero em 3,4 s contra 7,6 s solto (este último com o `tracemalloc` ligado, que é o que o deixa mais lento; o `.gz` não custa mais do que o solto); a consulta
  por nome numa base `.gz` paga a descompactação até o offset (192 ms) contra
  2 ms na solta. É o preço registrado acima, e é por isso que a régua de progresso é a
  comprimida.

### Testes

- `tests/test_games_db.py::LeitorDePGNTests`: as quatro formas e o membro do `.zip` na listagem;
  linhas iguais; nada gravado no disco; busca por nome no `.gz`; busca por posição no membro do
  `.zip` num pedaço só; bytes lidos são os do disco; `existe_base`/`tamanho_da_base` para o
  membro; cp1252 sem losango e BOM; offset do fluxo descompactado; `.zst` fora sem o pacote; `.zip`
  quebrado avisa.
- `tests/test_games_index.py::IndiceSobreBaseComprimidaTests`: a consulta lê a partida do `.gz` e
  do membro do `.zip` pelo offset; a base comprimida que mudou é relida inteira; o nome no
  manifesto é `pacote.zip/torneio.pgn`.

### O que o crítico recusou

_a preencher pelo crítico_
## S-532 · Índice incremental: só o que mudou é relido, com progresso e cancelamento na janela — ✅ **implementada em 2026-09-04**

### Problema

`games_index.py:135` (`build_index`) nascia inteiro num `.parcial` (`:155`) e era renomeado no fim
(`:212`): qualquer arquivo novo na pasta -- ou um torneio anexado ao `.pgn` de sempre -- custava a
pasta inteira de novo, 18 GB e mais de vinte minutos nesta máquina, porque `files` (`:181`) só
guardava o nome e o número do arquivo era a posição na lista. O `progress` (`:139`) era
`Callable[[int], None]`, chamado a cada 500 mil partidas, sem dizer de que arquivo nem quanto
falta; não havia `cancel`; e a janela só sabia dizer *"se o índice ainda não foi construído:
cvoff-games --build-index"* (`qt/dialogos.py:610`) -- quem acrescentava um torneio e voltava à sala
de estudo descobria que a busca por nome recusou o índice, e a saída era abrir um terminal.

### Solução

**A tabela `files` virou manifesto (`INDEX_VERSION = 4`).** Por base: `name` (o de `nome_da_base`),
`size`, `mtime`, `head` e `tail` -- o `blake2b` dos primeiros e dos últimos `BYTES_DA_MARCA` = 64 KB
--, e `games`. Tamanho igual não diz que o conteúdo é o mesmo, e `mtime` igual não diz nada num
sync de nuvem (a S-113 registra o antivírus que reescreve o carimbo sem tocar num byte): quem
decide são tamanho e as duas marcas, que custam menos de um milissegundo por arquivo. O que
decide reler, arquivo a arquivo: mesmo tamanho e mesmas marcas → **pulado** (só o `mtime` é
atualizado); cresceu, mesma cabeça sobre os bytes que o manifesto mediu e a cauda antiga ainda no
mesmo lugar → lido **a partir do tamanho antigo**, com os offsets velhos intactos; qualquer outra
diferença, ou base comprimida que mudou → as partidas dele saem e ele é relido inteiro; não está
mais na lista → as partidas dele saem. O número do arquivo vem do manifesto e sobrevive à ordem;
um arquivo novo recebe o próximo livre. Um índice v3 é apagado e refeito, como `--build-index`
sempre significou; o `.parcial` de uma versão anterior interrompida vai junto.

**Uma transação por arquivo, e a marca da base só no fim.** O índice é editado **no lugar**, com
`journal_mode=DELETE` (o `TRUNCATE` deixaria um `-journal` vazio ao lado para sempre, e `data/`
tem guarda contra artefato que ninguém declarou). A `meta.database` é apagada **antes** de qualquer
mudança e regravada só quando a rodada termina: é ela que `lookup_pair` confere, então um índice
em obras recusa a consulta em vez de responder menos do que a base tem -- a S-25 sem `.parcial`.
Cancelar (`cancel: threading.Event`, conferido a cada `_LINHAS_POR_CONFERENCIA` = 16 mil linhas,
~1 MB) desfaz só o arquivo em curso e mantém os anteriores; a rodada seguinte continua deles.
`build_index` devolve `Indexacao(partidas, relidas, arquivos_relidos, arquivos_pulados,
arquivos_removidos, cancelado)` -- o item em forma de número, e é isso que o teste afirma.

**`Progresso = (base, bytes_lidos, bytes_totais, partidas)`**, no máximo a cada
`INTERVALO_DE_PROGRESSO` = 0,1 s dentro de um arquivo, mais um aviso final por arquivo com os bytes
cheios -- **também para o pulado**, para a barra do conjunto andar pelo que não precisou ser lido.
Os bytes são os do disco (comprimidos, se a base for), porque são os únicos comparáveis ao
tamanho. `cli/games.py::_index_progress` reduz isso a uma linha a cada 5 s e uma por arquivo: dez
por segundo é o ritmo de uma barra, não o de um terminal.

**A decisão pura, `ui/indice_da_base.py`.** `Andamento` soma o último aviso de cada arquivo (posição
absoluta, não incremento) sobre o total e devolve `POR_MIL`; `frase_de_progresso` (`Lendo
base.pgn: 1,2 GB de 8,6 GB · 1.234.567 partidas`, ou `base.pgn: sem mudança, não foi relido`);
`frase_de_fim`, que diz **o que não foi relido**; e `perde_trabalho_ao_fechar() == False`, porque
cada arquivo é uma transação -- dizer o contrário treinaria a pessoa a ignorar o aviso quando ele
for verdade (a busca por posição).

**A fiação, `qt/indice_da_base.py`.** `IndexadorDaBase(QObject)` roda `build_index` numa `Tarefa`
(o `QThread` de `qt/trabalho.py`); o `progress` é chamado na thread de trabalho e **só emite**
`progresso(str, int, int, int)`; o slot `_somar`, do lado da interface, soma e emite
`avancou(por_mil)`; `terminou(Indexacao)` e `falhou(str, exc)` são os dois fins, e exatamente um
chega. Registra-se no `BusyRegistry` com `loses_work=False`, `cancellable=True` e o `cancel` do
`Event`. `indexar_com_dialogo(parent, bases, caminho)` monta um `QProgressDialog` modal à janela
com Cancelar em cima dele, que fecha sozinho no fim; `frase_final(resultado)` é o que vai ao
rodapé. O módulo não conhece painel nenhum: **quem o chama é um `connect` na sala ou no menu**, e
essa linha não foi escrita neste item porque `qt/painel_de_estudo.py` está sendo editado pela
S-527 na mesma árvore.

### Critério de aceite

- Segunda rodada sobre a mesma pasta: `relidas == 0`, `arquivos_pulados == n`, e a consulta segue
  respondendo. ✅ **Medido em 2026-09-04** sobre `LumbrasGigaBase_OTB_Complete.pgn` (8,6 GB,
  10.355.488 partidas): do zero 539 s na rodada limpa (6,4 avisos/s) e 1.212 s numa segunda rodada com o `tracemalloc` ligado e a suíte rodando ao lado (índice de 235 MB, 7.266 avisos,
  6,0/s); segunda rodada sem mudança **0,006 s** (< 2 s).
- Arquivo anexado: só a cauda é lida. ✅ Medido numa cópia em pasta temporária do
  `Endgame_Study_Database_VI_...pgn` (62 MB, 93.839 partidas): do zero 7,6 s; depois
  de anexar 1 partida, **0,014 s** e `relidas == 1`; a partida anexada é achada em
  2 ms.
- Arquivo removido sai do índice, sem aviso na consulta; arquivo reescrito é relido inteiro sem
  deixar linha velha; o novo ganha o próximo número e os antigos ficam com o deles. ✅
- Cancelamento honrado em < 1 s: com o pedido aos 0,3 s, a rodada volta antes de 1,3 s, a base
  pequena terminada fica, a grande é desfeita, e `lookup_pair` recusa o índice com a instrução de
  refazer até a rodada seguinte terminar -- que retoma do que ficou. ✅
- Progresso ≤ ~10×/s dentro de um arquivo. ✅ (Medido na gigabase: 6,0/s.)
- Pico de memória do índice do zero: 12,8 MB no `tracemalloc` sobre os 62 MB de referência, e 28 MB sobre os 8,6 GB da gigabase --
  o lote de 200 mil linhas, e nada proporcional ao arquivo.
- O Qt: fim e progresso chegam por sinal; o último valor do conjunto é mil; duas rodadas ao
  mesmo tempo são recusadas; cancelar pela API e pelo botão do diálogo para em < 1,5 s e o
  resultado diz; a falha vira sinal e não exceção; o `BusyRegistry` vê a operação enquanto roda,
  com `loses_work` falso, e a solta no fim. ✅
- Nenhum teste toca `data/`; o índice de medição ficou em pasta temporária. ✅
- `qt/janela.py` não é tocado. ✅

### Testes

- `tests/test_games_index.py::IndiceIncrementalTests`: primeira rodada lê tudo; segunda não relê
  nada e o progresso chega uma vez por arquivo com os bytes cheios; `mtime` sozinho não força;
  anexado relê só a cauda e a consulta acha velhas e nova; reescrito relido inteiro sem linha
  velha; removido sai; o novo ganha o próximo número; v3 é refeito; nem `.parcial` nem `-journal`
  sobram. `CancelamentoDoIndiceTests`: < 1 s, a consulta recusa o índice em obras, a rodada
  seguinte retoma, e ≤ 10 avisos/s. `IndiceSobreBaseComprimidaTests` (S-531).
- `tests/test_ui_indice_da_base.py`: a barra do conjunto anda pelo pulado; posição absoluta e não
  incremento; não passa de mil; arquivo não previsto entra no total; as três frases; fechar não
  perde trabalho.
- `tests/test_qt_indice_da_base.py`: fim por sinal com o resultado; progresso por sinal e somado
  por mil; não começa duas; cancelar para em < 1,5 s; falha vira sinal; registra no `BusyRegistry`
  e solta; o diálogo anda com o índice e fecha no fim; o botão Cancelar do diálogo para o índice.
- `tests/test_editor_model.py::SEM_TKINTER` ganhou `indice_da_base.py`; `docs/ARCHITECTURE.md`
  conta treze threads e a tabela ganhou a linha do índice.

### O que o crítico recusou

_a preencher pelo crítico_
## S-533 · Busca por jogador, torneio, ano, Elo, resultado e ECO, com filtros combinados e lista — ✅ **implementada em 2026-09-04**

### Problema

A base de 18,9 GB respondia a **uma** pergunta, e ela nascia sempre de um diagrama de livro:
`games_index.py:544` (`lookup_pair`, na v4) recebia um `PlayerPair` -- dois sobrenomes -- e nada
mais, porque a linha do índice era `(pair, file, offset)` e só (`games_index.py:249`). A outra
porta, `estudo_partidas.py:102` (`consultar`), respondia pela **posição** do tabuleiro e lia o
cache, que só conhece as posições já perguntadas. Na janela isso era um botão só,
`qt/painel_de_estudo.py:1661` (`partidas_da_posicao`).

Nenhuma das duas responde *as partidas de Carlsen em 2019 com Elo acima de 2700 na Najdorf*, que é
a pergunta que um enxadrista faz à base dez vezes por sessão. Não faltava dado -- `Date`,
`WhiteElo`, `BlackElo`, `Result` e `ECO` estão em todo `.pgn` e `games_db.py:141`
(`_KEPT_HEADERS`) já os lê ao **abrir** uma partida --, faltava eles estarem no índice: sem isso,
"as de 2019" custa a passada de dez minutos sobre 8,6 GB, por pergunta.

### Solução

**A linha do índice ganhou onze colunas, e a versão foi para 5.** `games` é
`(id, pair, file, offset, white, black, event, date, year, welo, belo, elo, result, eco)` com
`UNIQUE (file, offset)`. `white`, `black` e `event` são **números**: os nomes moram em dois
dicionários (`players(id, name, surname)`, `events(id, name, folded)`) e a linha guarda o número.
Dez milhões de linhas com `Carlsen, Magnus` escrito em cada uma seriam 200 MB de repetição; com o
número são 30 MB, e a busca por sobrenome vira uma consulta ao dicionário -- centenas de milhares
de linhas, não dez milhões -- seguida de uma sonda no índice. `elo` é o **menor** dos dois, e zero
se um falta: "Elo mínimo 2700" pergunta pelo nível da partida, e 2835 contra 2180 não é uma
partida de 2700.

**A v5 desfaz a v3, e o motivo é aritmético.** A v3 era `WITHOUT ROWID` com
`PRIMARY KEY (pair, file, offset)` -- uma árvore só, -44% de disco, medido na S-140. Com **seis**
caminhos de busca (`games_pair`, `games_white`, `games_black`, `games_event`, `games_eco`,
`games_year (year, elo)`) a chave composta de 14 bytes seria copiada dentro de cada índice
secundário, e o rowid de 4 bytes sai mais barato: a tabela voltou a ter `id INTEGER PRIMARY KEY`.
As seis árvores são **derrubadas antes de uma rodada grande e refeitas no fim** (`_refaz_os_indices`
decide por bytes: o que vai ser lido contra o que fica); numa rodada pequena -- o torneio anexado
da S-532 -- elas ficam abertas, porque refazer seis árvores de dez milhões de linhas por causa de
trezentas partidas custaria mais que as trezentas partidas.

**A migração é refazer, e não converter.** Um índice v4 não tem nomes, datas nem códigos gravados,
e uma "segunda passada" que os buscasse pelos offsets leria os mesmos bytes que a passada inteira,
na mesma ordem, com um `seek` por partida a mais. `_abrir_para_escrita` apaga o de outra versão e
refaz; até isso acontecer, `buscar` levanta `IndiceIndisponivel` com a instrução, e `lookup_pair`
continua devolvendo vazio (quem o chama tem a lista do cache como caminho alternativo).

**A pergunta é `ui/busca_de_partidas.py`, e ela é pura.** `Filtro` (brancas, pretas, qualquer cor,
evento, ano de–até, Elo mínimo, resultado, ECO de–até, posição), `de_campos` (texto do formulário →
`Filtro`, com `NAO_E_NUMERO` para o campo preenchido que não é número -- vazio e malfeito não são a
mesma coisa), `problemas` (todas as frases de uma vez, não a primeira), `COLUNAS`/`linha` (as oito
colunas, com travessão e não zero na célula sem valor) e `resumo` (`1.234 partidas · Carlsen ·
2015–2020 · B90`). O filtro guarda **o que a pessoa digitou**: quem dobra `Carlsen` em `carlsen` é
`games_db.surname`, do outro lado.

**Uma busca sem filtro que estreite é recusada, e é medida.** `ORDER BY … LIMIT 100` sem cláusula
nenhuma é uma varredura da tabela inteira mais uma ordenação de dez milhões de linhas, para
responder "as cem partidas mais recentes da base" -- que ninguém foi ali procurar. Jogador, evento,
ECO, ano e Elo têm árvore; resultado e posição **não**, e por isso refinam mas não escolhem.

**A ordem é `year DESC, date DESC, id DESC`, e o `year` na frente não é redundância.** A base
escreve o que não sabe com interrogação (`2019.??.??`), e `?` (0x3F) é **maior** que qualquer
dígito: ordenado só pelo texto, `????.??.??` viria antes de `2024.12.31` e a primeira página de
toda busca seria feita das partidas sem data. O `id` desempata para a paginação ser estável.

**A resposta é `Busca(achados, total, total_e_teto, offset, examinadas)`.** O total para em
`TETO_DE_CONTAGEM` = 100.000 e a frase diz *mais de*, porque contar todas as partidas de `1.e4`
custa segundos para dizer um número que ninguém lê até o fim. Com a posição no filtro, ela **não
está no índice** (guardá-la é a varredura de uma hora da S-92): até `TETO_DE_REPLAY` = 2.000
candidatas são lidas pelos offsets e reproduzidas com o porteiro da S-85, e `examinadas` diz
quantas foram -- em vez de fingir que foram todas. `partida_em(caminho, offset)` abre a partida
escolhida com um `seek`, que é o que o índice existe para permitir.

**A janela é `qt/busca_de_partidas.py::DialogoDeBusca`**, não modal: quem procura uma partida quer
o tabuleiro ao lado, e escolher uma na lista abre-a na sala **sem fechar a busca**. A consulta vai
para uma `Tarefa` (o `QThread` de `qt/trabalho.py`) e "Buscar" fica cinza enquanto ela roda; a
tabela é a `TabelaQt` das mesmas `Coluna` da camada pura. Três estados sem tabela, e eles não dizem
a mesma coisa: `Procurando na base…`, `Nenhuma partida · Carlsen · 2019` (com a pergunta ao lado,
porque quase sempre é um ano digitado errado) e a frase de `IndiceIndisponivel`, que já vem com a
instrução e tem ao lado o botão **Indexar base…** -- que emite `indice_pedido` para a sala, dona do
diálogo de progresso da S-532. Duplo clique **e** Enter emitem `partida_escolhida(caminho, offset)`;
o Enter é atalho de widget e não botão padrão do `QDialog`, senão ele refaria a busca em vez de
abrir a linha marcada.

**A fiação:** `buscar_partidas` é comando do catálogo (`ui/comandos.py`), mora no grupo Base da
barra da sala dentro do "Mais" (`ui/barra_da_sala.py`, ícone `filtrar` -- um funil, e não a segunda
lupa do mesmo grupo), tem item no menu Estudo e chama `PainelDeEstudo.buscar_partidas`, que **reusa**
o diálogo entre aberturas (um `QThread` destruído enquanto roda derruba o processo) e só atualiza a
posição. `abrir_partida_da_base` lê a partida pelo offset, a monta em PGN
(`estudo_partidas.como_pgn`) e a põe na mesa por `estudo.colar`, guardando antes o estudo aberto.

### A segunda rodada: o plano da consulta, e não a consulta

O crítico mediu doze consultas em vez das seis da spec, e **seis delas passavam de um segundo** na
gigabase. A causa era uma só, e não estava em nenhum filtro: `ORDER BY year DESC, date DESC,
id DESC LIMIT 100` sobre um filtro que casa milhões é a ordenação de milhões de linhas para
devolver cem. A contagem já parava no teto em dezenas de milissegundos nas mesmas consultas -- o
que custava era ordenar o que se achou, e não achar.

**Duas árvores novas, e a versão foi para 6.**

- **`games_ordem (year, date, id, result)`** é a **ordem em que a busca responde**, e não um
  filtro. Com ela o sqlite anda pela árvore de trás para a frente, confere o filtro linha a linha
  e para na centésima que passa: o custo deixa de ser *quantas casam* e passa a ser *quantas se
  olha até achar cem*. As duas colunas do fim não são ordem: o `id` é o rowid escrito de novo, e é
  o que faz o prefixo `(year, date, id)` ser exatamente o `ORDER BY` (sem ele aparece o
  `USE TEMP B-TREE FOR RIGHT PART OF ORDER BY`); o `result` é o único filtro sem árvore própria, e
  sem ele na folha a contagem de *"1990–2020, vitória das brancas"* era uma sonda na tabela por
  linha -- 1,25 s contra **12 ms** com a folha cobrindo.
- **`games_elo (elo)`**, porque "Elo mínimo 3500" sem mais nada era a varredura de dez milhões de
  linhas para responder *nenhuma*: 1,08 s medidos, e **para zero resultado**.

**A contagem escolhe o plano, e ela já existia.** `buscar` conta primeiro, com `LIMIT
TETO_DE_CONTAGEM + 1` -- e é o número que ela devolve que separa dois planos de custos opostos:

| a contagem diz | o plano | o custo |
|---|---|---|
| passou do teto (o filtro casa milhões) | `_POR_ORDEM`: `INDEXED BY games_ordem`, andando de trás para a frente | quantas se olha até achar cem |
| ficou abaixo (o filtro escolhe) | `_POR_FILTRO`: a árvore mais seletiva, com teto de cem mil, e ordenar o que sobrou | no máximo cem mil linhas ordenadas |

**`INDEXED BY` e não confiança no planejador**, e o motivo é medido: este Python traz um sqlite
**sem `STAT4`** (`PRAGMA compile_options` não o lista), então toda faixa vale a mesma estimativa
de fábrica para ele -- `eco BETWEEN 'A00' AND 'E99'` e `eco = 'B90'` são indistinguíveis para o
custo que ele calcula. O plano certo aqui não depende de estatística nenhuma: a contagem já disse
qual é o caso.

**A v6 é a primeira versão que não manda refazer.** As tabelas são idênticas às da v5 -- o que
falta é árvore, e árvore se cria sobre a tabela pronta. `_VERSOES_QUE_SO_GANHAM_ARVORE` guarda
essa distinção: a regra "migração é refazer" das versões 3, 4 e 5 valia porque faltava **dado
gravado**, e cobrar aqui a passada de dez minutos seria zelo cobrado do usuário. Medido: a v5 da
gigabase virou v6 em **16 s**, com **zero partida relida**.

**Três leituras do campo de nome**, e as duas novas nasceram de buscas que respondiam zero
(`_sobrenomes`): `Magnus Carlsen` na ordem natural passou a achar as mesmas 5.141 partidas que
`Carlsen, Magnus` (respondia **0, em silêncio**), e o sufixo de geração colado no sobrenome --
`Vehre Jr, John L` entra no dicionário como `vehre jr`, e são **338 grafias assim** na gigabase --
entra como forma exata no `IN`: `Vehre` passou de **32** para **419** partidas.

**A tabela ordena pelo cabeçalho** (`TabelaQt(ordenavel=True)`), que é o gesto de toda sessão de
quem usa uma base. A ordenação é **da página**, e não da base. Ligá-la abriu um defeito pior que a
ausência: a escolha da linha era `indexOfTopLevelItem`, que é a altura na tela -- com a lista
ordenada, o duplo clique abriria outra partida, plausível e sem erro nenhum. A posição de chegada
passou a viajar com a linha (`TabelaQt.posicao_de`).

**Cancelar a indexação deixou de custar a rodada inteira.** A transação era por arquivo, e a
gigabase **é** um arquivo: parar no nono minuto desfazia os nove. A cada `_TAMANHO_DO_LOTE`
partidas gravadas, o manifesto anota até que byte o arquivo está lido -- na mesma forma que ele já
usava para o torneio anexado da S-532 --, e a rodada seguinte continua de lá. Base comprimida fica
de fora: ali o byte lido não é o byte do disco.

### Critério de aceite

Todas as medições sobre o índice da **`LumbrasGigaBase_OTB_Complete.pgn` inteira** (8,6 GB,
10.355.488 partidas), melhor de três, na mesma sessão de 2026-09-04. A coluna "v5" é o código da
primeira rodada sobre o índice do crítico; a coluna "v6" é este código sobre o mesmo índice
completado.

| busca | v5 | v6 | o que voltou |
|---|---|---|---|
| Carlsen | 34,2 ms | **29,5 ms** | 5.141 partidas |
| Carlsen × Anand | 57,0 ms | **50,4 ms** | 140 partidas |
| evento "Tata Steel" | 82,7 ms | **79,6 ms** | 5.133 partidas |
| Elo ≥ 2700 em 2019 | 46,1 ms | **44,2 ms** | 1.989 partidas |
| ECO B90 | 36,9 ms | **8,0 ms** | mais de 100.000 |
| Carlsen · 2019 · Elo ≥ 2700 · B90 | 56,6 ms | **50,4 ms** | 5 partidas |
| **ano 2019 sozinho** | **2.823 ms** | **7,0 ms** | mais de 100.000 |
| **faixa ECO A00–E99** | **5.449 ms** | **6,0 ms** | mais de 100.000 |
| **evento `ch-`** | **5.084 ms** | **54,4 ms** | mais de 100.000 |
| **faixa ECO B00–B99** | **1.952 ms** | **6,0 ms** | mais de 100.000 |
| **anos 1990–2020** | **2.318 ms** | **6,9 ms** | mais de 100.000 |
| **Elo ≥ 3500** | **1.084 ms** | **0,8 ms** | nenhuma partida |
| Elo ≥ 2700 sem ano | 451 ms | **149 ms** | 25.555 partidas |
| Ivanov (sobrenome comum) | 281 ms | **137 ms** | 22.045 partidas |
| página 40 de A00–E99 | 5.801 ms | **6,8 ms** | mais de 100.000 |
| 1990–2020 · vitória das brancas | 2.911 ms | **19,6 ms** | mais de 100.000 |

- **As doze da rodada do crítico ficam abaixo de 1 s, e a mais lenta é 54 ms** -- 18× dentro do
  orçamento. Nenhuma consulta medida ficou de fora do critério: as quatro últimas linhas são casos
  que esta rodada procurou de propósito, e passam também. ✅
- O `EXPLAIN QUERY PLAN` das que eram lentas, agora:

  | consulta | plano |
  |---|---|
  | `ano 2019` · página | `SEARCH games USING COVERING INDEX games_ordem (year>? AND year<?)` |
  | `A00–E99` · página | `SCAN games USING INDEX games_ordem` |
  | `Elo ≥ 3500` · contagem | `SEARCH games USING COVERING INDEX games_elo (elo>?)` |
  | `1990–2020 + 1-0` · contagem | `SEARCH games USING COVERING INDEX games_ordem (year>? AND year<?)` |

- **O preço em disco: 1.763 MB → 2.180 MB (+23,7%)**, e o preço em tempo de uma v5 já pronta é
  **16 s de `CREATE INDEX`, sem reler byte nenhum do `.pgn`**. ✅
- `Magnus Carlsen` responde o mesmo que `Carlsen, Magnus` (5.141), e `Vehre` acha as grafias com
  `Jr` coladas (32 → 419). ✅
- A tabela ordena pelo cabeçalho, com a coluna numérica ordenando por magnitude e a célula sem
  valor no fim **nos dois sentidos**; a linha escolhida continua sendo a que está marcada. ✅
- Toda célula de toda `TabelaQt` leva o próprio texto como dica. ✅
- Cancelar a indexação não faz a rodada seguinte reler o arquivo inteiro. ✅
- A janela não trava com dez milhões de partidas: a consulta roda numa `Tarefa`, e o teste afirma
  que ela **começou sem ter terminado**. ✅
- Um índice de outra versão, ausente ou em obras vira frase **com instrução**. ✅
- Paginação estável, formulário malfeito recusado com o nome dos campos. ✅

### O que ficou de fora, e por quê

- **Elo máximo, número de lances e rodada.** O Elo máximo dá para fazer com a coluna que já
  existe, mas ela é o **menor** dos dois Elos -- "Elo máximo 2200" perguntaria pelo jogador mais
  fraco da partida, que é a pergunta errada, e responder a certa é `welo <= ? AND belo <= ?` com o
  zero de "sem Elo" passando por dentro. Número de lances e rodada não estão no índice: são duas
  colunas novas, uma v7 e a passada de dez minutos sobre a gigabase. Nenhum dos três é o defeito
  que esta rodada foi consertar, e os três juntos são um item próprio.
- **O sufixo colado no dicionário.** `Vehre Jr` está corrigido do lado de quem pergunta; o
  dicionário continua gravando `vehre jr`. Consertar `games_db.surname` seria o caminho curto e
  custa a passada inteira: o `pair` de cada uma das 10,3 milhões de linhas é `pair_hash` sobre o
  sobrenome, e mudá-lo invalidaria a coluna.

### Testes

- `tests/test_games_index.py::DoisPlanosDeBuscaTests`: os dois planos dão **a mesma página** para
  seis filtros diferentes e paginam igual (o teto é rebaixado para 2, que é o que faz uma base de
  doze partidas exercitar os dois); a contagem para no teto e a página não.
  `SobrenomeDaBuscaTests`: a ordem natural, a forma inteira que continua valendo, o sufixo de
  geração, e o campo vazio que não vira forma nenhuma.
  `MigracaoDeVersaoTests`: o v5 é **completado e não refeito** (`relidas == 0`, as linhas ficam, as
  árvores aparecem, a versão sobe) e continua recusado pela busca até a rodada acontecer.
  `CancelamentoDoIndiceTests`: o cancelamento no meio do arquivo não faz a rodada seguinte relê-lo
  inteiro -- o que se afirma é o **custo**, porque a resposta final é a mesma nos dois mundos.
- `tests/test_qt_tabela.py::OrdenacaoEDicaTests`: de fábrica a tabela não ordena; a coluna numérica
  ordena por magnitude; a célula sem número vai para o fim nos dois sentidos; a posição de chegada
  sobrevive à ordenação; toda célula leva a própria dica; preencher de novo não multiplica linhas.
- `tests/test_qt_busca_de_partidas.py`: a partida escolhida é a da linha marcada **depois** de
  ordenar, e ordenar não muda o que a busca achou.
- Os testes da primeira rodada continuam valendo e não foram tocados.

### O que o crítico recusou

| o que ele achou | o que mudou |
|---|---|
| `ano 2019` sozinho em **2,55 s**; `A00–E99` em **7,73 s**; evento `ch-` em **5,94 s**; `B00–B99` em **1,40 s**; `1990–2020` em **1,54 s** -- seis consultas acima do "< 1 s" da spec | `games_ordem (year, date, id, result)` e a escolha de plano pela contagem: as cinco caem para **7,0 / 6,0 / 54,4 / 6,0 / 6,9 ms** |
| `Elo ≥ 3500` custando **0,83 s para devolver zero linha** | `games_elo (elo)`: **0,8 ms**, e a contagem passa a ser uma sonda em vez de uma varredura |
| A spec media seis consultas escolhidas e chamava o critério de cumprido | O critério passou a ser medido sobre **dezesseis**, com a coluna "antes" ao lado, e a mais lenta delas está na tabela |
| Tabela sem ordenação por coluna (`setSortingEnabled`) -- gesto de toda sessão no ChessBase | `TabelaQt(ordenavel=True)` na busca, com ordem numérica pela declaração de `Coluna` e a posição de chegada viajando com a linha |
| Nenhuma `TabelaQt` tinha dica de célula | Toda célula leva o próprio texto como dica |
| `Magnus Carlsen` (ordem natural) devolvia **0 em silêncio** | A última palavra entra como segunda forma: 5.141 partidas |
| 264 grafias com sufixo colado (`Vehre Jr, John L` → `vehre jr`) inalcançáveis | As formas com sufixo entram no `IN`: `Vehre` passou de 32 para 419 partidas (338 grafias com sufixo na base) |
| Cancelar a indexação da gigabase perdia tudo (transação por arquivo, e a gigabase é um arquivo) | Transação por lote dentro do arquivo, com o ponto de retomada no manifesto |
| Sem Elo máximo, sem número de lances, sem rodada | Registrado em "O que ficou de fora" com o custo de cada um; nenhum foi feito |


## S-534 · Classificação ECO embutida, gravada no índice e mostrada na sala — ✅ **implementada em 2026-09-04**

### Problema

O código ECO da partida **era lido e jogado fora**. `games_db.py:141` (`_KEPT_HEADERS`) inclui
`"ECO"` desde sempre, então toda partida aberta da base trazia o header dentro de
`GameRecord.headers` -- e a busca de `HEAD` por `ECO` em `src/` não achava mais nada: nenhuma
coluna do índice (`games_index.py:249`, na v4, tinha `pair`, `file` e `offset`), nenhum rótulo na
sala de estudo, nenhum filtro. Um enxadrista profissional identifica uma posição pela abertura
antes de identificá-la pelos nomes, e o programa não sabia dizer em que abertura o tabuleiro
estava.

E não bastaria ler o header: a base exportada de um servidor não traz `[ECO]` em partida nenhuma,
e a `Endgame_Study_Database_VI` não traz em nenhuma das 93.839 (são composições montadas de um
`[FEN]`). Sem tabela embutida, o filtro por ECO da S-533 responderia zero numa base inteira, em
silêncio.

### Solução

**A tabela mora no pacote, em `eco.py`.** O `python-chess` não a traz. São **500 códigos** (A00 a
E99) em 519 linhas -- código, nome e a linha canônica em SAN --, ~30 KB de texto. Código sempre,
**nome em inglês**: *Sicilian, Najdorf*, *Queen's Gambit Declined*, *Ruy Lopez* são consagrados
como estão nos livros e no ChessBase, e traduzir "Nimzo-Indian" inventaria vocabulário que nenhum
enxadrista usa. O código é o que se filtra e o que se compara; o nome é a legenda dele.

**Duas classificações, e a diferença é o custo.**

- `classificar(tabuleiro_ou_lances)` casa **por posição**: cada linha da tabela é reproduzida uma
  vez e guardada pela FEN sem contadores, e a partida é percorrida procurando a posição mais
  profunda que a tabela conhece. **A transposição vale**: `1.Nf3 Nf6 2.c4 e6 3.d4` recebe o mesmo
  E10 de `1.d4 Nf6 2.c4 e6 3.Nf3`. Medido: **~0,5 ms por partida**, com a tabela por posição
  montada uma vez (84 ms) e mantida em cache.
- `classificar_lances(sans)` casa **pela ordem dos lances**, numa árvore de prefixos sem tabuleiro
  nenhum: **~1 µs por consulta**. É o caminho do índice, e ele perde a transposição de propósito --
  a sala reclassifica por posição ao abrir a partida, então o que aparece sob o tabuleiro é sempre
  a leitura completa.

**O código mais profundo vence**, e `None` quando a tabela não alcança nada -- e não "A00", que
seria o número enganoso da S-135. Uma partida que comece na posição inicial **sempre** recebe
algum código (as vinte primeiras jogadas legais têm linha; as catorze menos jogadas ficam em A00,
como na classificação padrão): quem devolve `None` é a posição de onde não se chegou por lance
nenhum -- o estudo montado de um `[FEN]`, que é a `Endgame_Study_Database` inteira, e a raiz de um
estudo aberto de um diagrama de livro.

**No índice o header vence.** `_linha_da_partida` grava `codigo_do_header(cabecalho["ECO"])` --
`C47d` vira `C47`, porque a unidade da classificação são os três caracteres e é neles que a busca
filtra. Só quando não há header **e** a partida não tem `[FEN]` é que as duas primeiras linhas do
movetext viram lances por expressão regular (`lances_do_movetext`, com os comentários fora: um
`{Better was Bf4}` tem um `Bf4` que não foi jogado) e entram em `classificar_lances`. A partida
foi fechada mais tarde na passada por causa disto: até a v4 ela era fechada no header `[Black]`, e
`Result`, `WhiteElo` e `ECO` vêm depois dele -- o movetext, depois de todos.

**Na sala, o header vence igual.** `frase_do_tabuleiro(tabuleiro, header)` põe
`ECO B33 · Sicilian, Sveshnikov` na faixa sob o tabuleiro (`qt/painel_de_estudo._barra_de_navegacao`),
ao lado do lance corrente e da vez, e ela é refeita a cada lance em `_mostrar_lance_corrente`. Sem
header, `classificar` lê a pilha de lances do próprio tabuleiro -- e é aí que a transposição paga.

### A segunda rodada: a regra, o teto e a tabela

O crítico comparou a classificação com o header `[ECO]` da própria base e achou **59,7%** de
acerto em `classificar_lances` e **73,2%** em `classificar`, com 27,6% errando até a letra. E achou
a transposição prometida não acontecendo: `1.Nf3 d5 2.d4 Nf6 3.c4` dava **D02** e
`1.d4 d5 2.c4 Nf6 3.Nf3` dava **D06**, sendo a mesma posição.

**Onde o header existe, e o que isso decide.** Medido em 20.000 partidas colhidas em 200 pontos
aleatórios da gigabase (`scratchpad/eco_medir.py`): **100,000% delas têm `[ECO]`** -- 20.000 de
20.000, e nenhuma com `[FEN]`. Do outro lado, a `Endgame_Study_Database_VI` não traz o header em
**nenhuma** das 93.839, porque são composições montadas de um `[FEN]` e não têm abertura. Então a
tabela embutida **não decide o código de nenhuma partida de base publicada**: ela decide o de
material OCRado, o de partida digitada na sala, o de base exportada de servidor -- e é a legenda
que a sala mostra sob o tabuleiro. É por isso que a comparação com o header é a régua certa mesmo
não sendo o caminho de produção: ela é a única verdade de referência que existe em escala.

**A transposição não era a posição final: era a regra.** `classificar` guardava a linha **mais
longa da tabela** entre todas as que a partida tocou, e cada caminho havia passado por uma
intermediária diferente. Passou a valer a **posição mais tardia que a tabela conhece**, andando
para trás a partir da última -- que é a regra da classificação padrão. Sozinha, ela levou o acerto
de 77,41% para... nada: 77,41% é o número **já com ela**. Contra a medição do crítico (73,2% na
amostra dele), a mudança de regra é a diferença entre as duas.

**O teto de lances era menor que a tabela.** `LANCES_EXAMINADOS` era 24 e a linha mais longa tem
**28** (D69), com outras três em 24 ou mais. **C99 era inalcançável**: as 52 partidas C99 da
amostra erraram **todas as 52**. Trinta cobrem a linha mais longa com folga.

**A tabela cresceu 266 linhas, e cada uma nasceu de um erro contado.** São 785 linhas para os
mesmos 500 códigos -- 519 na tabela padrão, escrita por código, mais `_TABELA_EXTRA`, escrita a
partir da lista de confusões. As três formas de falha que ela conserta:

1. **A porta de transposição que faltava**: `1.Nf3 d5 2.c4 e6` chega à mesma posição de
   `1.c4 e6 2.Nf3 d5`, e a tabela só tinha `A13 = 1.c4 e6` -- cedo demais para a partida ainda
   estar nela. Eram 149 erros de A13 em 178 partidas.
2. **O ponto de bifurcação sem linha**: `C54` era só a linha principal de 11 meios-lances, e quem
   jogasse `4...Nf6 5.d3` caía em `C53`. 102 erros em 103 partidas.
3. **A abertura alcançável por um caminho só**: `B33` existia como a Sveshnikov de 16 meios-lances,
   e a mesma abertura por `5...e6 6.Ndb5` não tinha linha. 95 erros em 398.

Duas linhas foram escritas, medidas e **retiradas** por piorarem o total: `C55` para
`3.Bc4 Nf6 4.d3` (a base chama o mesmo lugar de C50 mais vezes do que de C55) e `D36` para
`5.Bg5 Be7 6.e3`. Estão registradas aqui porque o próximo a mexer na tabela vai querer escrevê-las
de novo.

**O nome mostrado passou a ser o da linha.** `nome(codigo)` é a legenda da **família** e ela
repete: dos 500 códigos, **240 têm um nome que outro código também usa** -- *Ruy Lopez* nomeia
nove, *English* treze, *Sicilian* doze. Sob um tabuleiro que está na Berlim aberta, `ECO C67 ·
Ruy Lopez` diz o que já se via. `frase_da_abertura` usa `Abertura.nome`, que é o nome da **linha
casada**, e são 600 nomes distintos. `frase_do_tabuleiro` classifica a posição mesmo com header:
concordando, a legenda é a da linha; discordando, o código continua sendo o do header e a legenda
volta a ser a da família -- afirmar o nome de uma linha que a partida não percorreu é pior que a
legenda genérica.

### Critério de aceite

Medido em 2026-09-04 sobre **20.000 partidas** colhidas em 200 pontos aleatórios da
`LumbrasGigaBase_OTB_Complete.pgn` (semente 20260904), contra o header `[ECO]` de cada uma. A
amostra é por sorteio de offset porque a base é ordenada por evento e ano, e ler o começo mediria
um recorte.

| | antes desta rodada | agora |
|---|---|---|
| `classificar` (por posição), código exato | 77,41% | **86,39%** |
| `classificar`, mesma letra | 94,48% | **96,63%** |
| `classificar_lances` (por ordem), código exato | 66,17% | **68,88%** |
| `classificar_lances`, mesma letra | 88,39% | **88,48%** |
| erros ao todo | 4.518 | **2.723** (−39,7%) |
| linhas da tabela | 519 | **785** |

**A meta honesta é 86,39%, e não 99%.** Os 13,6% que sobram não são uma tabela pequena: são casos
em que a própria base responde as duas coisas. `1.e4 c5 2.Nf3 e6 3.g3` aparece 179 vezes como A08
(ataque índio do rei) e 283 como B40 (siciliana), da mesma posição; `3.Bc4 Nf6 4.d3` aparece como
C50 e como C55; `4.cxd5 exd5 5.Bg5 Be7 6.e3` como D35 e como D36. Escrever a linha melhora um dos
dois lados e piora o outro na mesma proporção -- foi medido nos três casos, e as duas linhas que
saíram são a prova. A mesma-letra em **96,63%** é o número que diz o que a classificação entrega
na prática: a família da abertura está certa em 19 de cada 20 partidas.

- A transposição do crítico: `1.Nf3 d5 2.d4 Nf6 3.c4` e `1.d4 d5 2.c4 Nf6 3.Nf3` dão **o mesmo
  código**, e mais cinco pares de posições comprovadamente iguais também. ✅
- **O alcance da transposição é o da tabela.** Dois caminhos que chegam a uma posição que a tabela
  não conhece andam para trás cada um pelo seu e podem parar em pontos diferentes. Foi exatamente
  o caso do par do crítico -- a resposta ali não é uma regra melhor, é a linha que faltava. ✅
- A linha mais longa da tabela é alcançável: C98, C99, D68, D69 e D89 classificam nos próprios
  códigos. ✅
- **O custo, medido em 2026-09-04 nesta máquina:**

  | | custo |
  |---|---|
  | `classificar` sobre a pilha de um tabuleiro de 24 meios-lances (o caminho da sala) | **960 µs** |
  | `classificar` sobre uma lista de SAN (o caminho da medição) | **1.108 µs** |
  | `frase_do_tabuleiro` por lance na sala, do 1º ao 24º | **média 521 µs, pior 898 µs** |
  | `classificar_lances` (o caminho do índice) | **1,06 µs** |
  | montar a tabela por posição, uma vez | **100 ms** |

  A primeira rodada dizia "~0,5 ms por partida" para `classificar` e o crítico mediu 1.144 µs.
  **Os dois números estavam certos sobre coisas diferentes**, e a spec citava um no lugar do
  outro: 0,5 ms é o custo **médio por lance** da frase da sala -- os primeiros lances são baratos
  --, e ~1,0 ms é o custo de classificar **uma partida inteira**. A tabela acima diz os dois.
- A classificação por lance continua **três ordens de grandeza** mais barata que a por posição
  (1,06 µs contra 960 µs), que é a razão de haver duas: um replay na passada do índice seria
  +1 ms × 10 milhões ≈ três horas sobre os dez minutos da gigabase. ✅
- O header vence o **código** no índice e na sala; a posição dá o **nome**; a sublinha (`B90a`) é
  cortada; a partida montada de um `[FEN]` não ganha abertura. ✅
- Os 500 códigos continuam cobertos, toda linha continua legal desde a posição inicial, e nenhuma
  posição da tabela é alcançada por dois códigos diferentes na mesma profundidade. ✅

### O que ficou de fora, e por quê

- **`classificar_lances` subiu pouco (66,17% → 68,88%)**, e vai continuar subindo pouco: ela casa
  pela **ordem dos lances**, e as 266 linhas novas são majoritariamente portas de transposição --
  posições alcançadas por outra ordem, que é justamente o que uma árvore de prefixos não vê. Ela é
  o caminho do índice, e na gigabase o índice usa o header em 100% das partidas: o número dela
  pesa numa base exportada de servidor, e ali é a mesma tabela vista pelo lado que não transpõe.
- **A tabela não virou a classificação completa.** A do Informador tem milhares de linhas por
  código; esta tem 785 no total, escritas para os erros que a medição apontou. O caminho para 90%+
  é mais medição e mais linhas, não outra regra.

### Testes

- `tests/test_eco.py::TransposicaoTests`: os seis pares de posições comprovadamente iguais (o teste
  **confere** que são a mesma posição antes de comparar os códigos, senão não prova nada); a regra
  da posição mais tardia contra a da linha mais longa, num caso em que discordam; a linha mais
  longa da tabela alcançável.
- `tests/test_eco.py::NomeDaLinhaTests`: a frase da sala traz o nome da linha e **não** o da
  família; com header que concorda a legenda é a da linha; com header que discorda o código é do
  header e a legenda volta à família; sem posição conhecida o header ainda responde.
- Os testes da primeira rodada (`TabelaTests`, `ClassificarTests`, `HeaderEFraseTests`,
  `MovetextTests`, `CustoTests`) continuam valendo sem mudança.

### O que o crítico recusou

| o que ele achou | o que mudou |
|---|---|
| `classificar_lances` acerta **59,7%** e `classificar` **73,2%** contra o header; 27,6% erram até a letra | 86,39% e 68,88% exatos, 96,63% e 88,48% na letra, medidos em 20.000 partidas com o método escrito |
| A transposição prometida não acontece: `1.Nf3 d5 2.d4 Nf6 3.c4` dá D02 e `1.d4 d5 2.c4 Nf6 3.Nf3` dá D06 | A regra passou a ser a **posição mais tardia** e não a linha mais longa; e a posição final daquele par ganhou linha. Os dois dão D06 |
| A tabela tem 519 linhas para 500 códigos | 785 linhas, e as 266 novas saíram da lista de confusões medida |
| **240 dos 500 nomes repetem** o de outro código (13 dizem `English`, 12 `Sicilian`, 9 `Ruy Lopez`); a sala diz `ECO C67 · Ruy Lopez` onde o ChessBase diz *Berlim, variante aberta* | O nome mostrado passou a ser o da **linha** (`frase_da_abertura`): 600 nomes distintos, e o C67 da Berlim aberta diz *Berlin Defense, Open Variation* |
| Não estava medido em que fração das partidas o header existe | 100,000% em 20.000 partidas da gigabase; 0% nas 93.839 da `Endgame_Study_Database`. A spec passou a dizer que o classificador decide para material OCRado |
| `classificar` custa 1.144 µs e a spec diz "~0,5 ms" | Os dois números são de coisas diferentes e a spec citava um pelo outro. A tabela de custo agora traz os cinco: 960 µs por partida no caminho da sala, 521 µs por lance na frase, 1,06 µs no caminho do índice |
| (não achado por ele) `LANCES_EXAMINADOS` era 24 e a linha mais longa tem 28: **C99 nunca casava** | Teto em 30, e um teste afirma que a linha mais longa é alcançável |


## S-535 · Árvore de aberturas: da posição corrente, cada lance com N, %, Elo médio e ano — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-536 · Opções do motor (Hash, Threads, MultiPV, caminho) nas preferências, sem reiniciar — ✅ **implementada em 2026-09-04**

### Problema

As opções existiam no arquivo e não existiam na janela. `settings.py:175` (`EngineSettings`) tinha
`path`, `movetime_ms:182` e `threads:183` -- e mais nada: nem `Hash`, nem `MultiPV`, nem pasta de
tablebases. `qt/preferencias.py:47` (`motor_das_preferencias`) as lia e montava o `EngineAnalyzer`
(`:68`), e `engine.py:190` mandava ao processo **uma** opção: `configure({"Threads": ...})`.

E não havia diálogo nenhum. Uma varredura por `preferenc|settings` em `src/chess_diagram_ocr/qt/`
devolvia oito ocorrências, todas de leitura: o único caminho para mudar qualquer preferência do
programa era editar `data/settings.json` à mão e **reabrir a janela**. Numa máquina em que a procura
automática não acha o binário -- que era o caso desta, com o Stockfish dentro da instalação do SCID
--, isso quer dizer que a seção do motor nunca aparece e não há como fazê-la aparecer de dentro do
programa.

Um segundo defeito estava no mesmo lugar: `configure` manda o dicionário inteiro e **levanta no
primeiro nome que o motor não conhece**, sem enviar os seguintes. Com duas opções, um motor sem
`Hash` perderia o `Threads` junto.

### Solução

**A decisão pura, `ui/motor_declarado.py`.** A tabela `OPCOES` -- quatro campos, com o nome UCI, o
rótulo em pt-BR, o piso e a dica --, os tetos desta máquina (`teto_de`), a validação em pt-BR
(`validar`, `validar_caminho`, `validar_pasta_de_tablebase`) e **o plano de aplicação**
(`plano_de_aplicacao`). As chaves da tabela *são* os nomes dos campos de `EngineSettings`, e é o que
permite ler e escrever por `getattr`/`replace` em vez de manter uma segunda tabela campo→widget.

**Os tetos não são de gosto, e entram por argumento.** `Hash` é **metade da memória da máquina,
arredondada para baixo à potência de dois** -- metade porque o resto da máquina existe, e potência
de dois porque é como o Stockfish reparte a tabela (pedir 3000 MB gasta 2048 e joga fora 952);
`Threads` é o **número de núcleos**, e não `núcleos-1`, porque quem analisa uma partida inteira quer
a máquina toda e a janela continua respondendo. `MultiPV` para em 10 e o tempo por posição em 60 s,
que são limites de leitura e não de recurso. Quem lê os números da máquina é `qt/preferencias.py`
(`nucleos_da_maquina`, `memoria_da_maquina_mb`), e memória desconhecida devolve zero -- o teto cai
no piso em vez de o diálogo não abrir.

**O plano é a parte que faz "sem reiniciar" ser verdade.** Duas das quatro opções são do processo
(`Hash`, `Threads`, e a `SyzygyPath` da S-538) e vão por `setoption` ao motor **aberto**; as outras
duas (`MultiPV`, tempo) entram em cada chamada de análise, e mudá-las vale na resposta seguinte sem
tocar em processo nenhum. **Só o caminho do binário derruba e sobe outro**: o processo aberto *é* o
motor antigo, e a única forma de falar com outro é abrir outro. E dois jeitos de escrever o mesmo
caminho não são uma troca -- aspas em volta, espaço nas pontas e barra invertida são o que volta de
todo "Copiar como caminho" do Windows, e sem normalizá-los abrir o diálogo e confirmar sem mexer em
nada derrubaria o motor.

**O formulário e a aplicação, `qt/preferencias.py`.** `DialogoDoMotor` desenha os seis campos com a
faixa desta máquina escrita no próprio `QSpinBox` (`256   (até 8192)`) e recusa **na própria
janela**, com a frase ao lado dos campos -- uma segunda caixa custaria dois cliques para corrigir um
caractere. `MotorVivo` aplica: o que não fala com o processo é atribuído na hora (dois inteiros
Python), e o que fala vai para uma `Tarefa` de `qt/trabalho.py`, porque o `close()` de um motor que
está pensando espera ele responder e o `lock` do analisador pode estar tomado por uma análise em
curso.

**O motor é o mesmo objeto antes e depois de trocar de binário** (`EngineAnalyzer.trocar_binario`),
e isso não é economia: a janela guarda uma referência a ele e é ela quem o fecha no `closeEvent`.
Um `EngineAnalyzer` novo a cada troca deixaria o processo da última troca vivo depois de a janela
fechar. O único caso em que nasce objeto novo é o da máquina que abriu **sem** motor, e ali a sala
passa a ser a dona dele -- `qt/janela.py` fecha `self.estudo.analisador`, que é o mesmo objeto
enquanto ninguém troca nada (três linhas trocadas por três; a catraca de 1.905 não subiu).

**O comando existe com e sem motor**, e é o único do grupo Motor que existe sem: `opcoes_do_motor`
entra no catálogo, no menu Estudo e na fila da sala (dentro do "Mais"), com `so_com_motor=False`.
Esconder justamente ele numa máquina sem motor seria escondê-lo de quem precisa dele.

**E o padrão de `Hash` ficou onde a medição o deixou.** A tentação era subir para 128 MB, que não
custam nada. Medido (Stockfish dev-20230303, 1 thread, `scratchpad/medir_hash2.py`): a Imortal a
profundidade 20 custou **37,3 s** com 16 MB, **41,7 s** com 128 e **42,6 s** com 512; uma posição a
profundidade 26 custou **9,4 s** com 16 MB e **13,0 s** com 512. Não há ganho, e a diferença que
aparece é ruído com o sinal trocado -- uma busca de segundos numa thread não enche 16 MB. O padrão
continua sendo o do Stockfish, e a opção existe para quem analisa por minutos com oito threads.

### Critério de aceite

Medido em 2026-09-04, Stockfish dev-20230303, máquina de 12 núcleos e 32.377 MB.

- **Os quatro campos, com a faixa desta máquina.** ✅ `Tabela de transposição 256 (até 8192)`,
  `Núcleos 2 (até 12)`, `Linhas do motor 3 (até 10)`, `Tempo por posição 800 (até 60000)`. O
  diálogo mede 560×318 px e diz `Esta máquina: 12 núcleo(s), 32377 MB de memória`.
- **Trocar `Hash` não derruba o processo.** ✅ `setoption` aceito sobre o motor aberto, com o mesmo
  objeto `SimpleEngine` antes e depois -- afirmado contra o motor falso e medido contra o
  Stockfish (`Hash 512` e `Threads 2` aceitos; os nós por segundo foram de 1,34 M para 2,33 M na
  análise seguinte, no mesmo processo).
- **Trocar o caminho derruba e sobe outro.** ✅ Objeto `SimpleEngine` diferente depois, `path` novo,
  e o motor novo respondendo. Medido: **140 ms** para derrubar e subir (a faixa de 100 a 300 ms que
  a S-33 registra).
- **A janela não congela.** ✅ `aplicar` devolve com o `MotorVivo` ainda **ocupado**: a troca roda
  numa `Tarefa`, e é isso que o teste afirma -- não um cronômetro, que mediria a máquina.
- **`MultiPV` vale na análise seguinte sem tocar o processo.** ✅ De 3 para 1: mesmo objeto, e a
  análise seguinte devolve uma linha.
- **Caminho que não aponta para motor nenhum apaga a seção**, em vez de deixá-la cinza. ✅ É a S-33
  aplicada à troca.
- **Uma sala que abriu sem motor ganha a seção e a fila sem reiniciar.** ✅ A fila é remontada (uma
  `QAction` não muda de barra depois de criada) e o divisor vertical passa de duas para três
  partes. O que **não** aparece nesse caminho é a barra lateral da S-529 -- ver a linha do relatório
  lá.
- **O que muda fica gravado** para a próxima sessão, atomicamente. ✅
- **Validação em pt-BR, na própria janela.** ✅ `Não há arquivo em Z:/nao/existe/stockfish.exe`;
  `Tabela de transposição: o mínimo é 16 MB`; `Núcleos: o máximo nesta máquina é 8`; pasta no lugar
  do binário e binário no lugar da pasta têm frases próprias; caminho entre aspas passa.
- **Uma opção que o motor não conhece não derruba as outras.** ✅ `setoption` é mandado um a um, e
  `reconfigurar` devolve quais pegaram.
- **⚠ Consequência que este item não pode fechar sozinho, e é a linha para o coordenador.** Os três
  campos novos mudam `settings.py`, e `settings.py` está no **fecho de importação da medição de
  campo** (`field_eval.measured_modules`, que parte de `cli.field` e segue os imports). Com isso
  `tests/test_field_eval.py::ImpressaoDaMedicaoTests::test_todo_relatorio_corrente_mediu_o_codigo_de_hoje`
  fica vermelho nos quatro relatórios, com a divergência em **um** módulo: `settings`. Nenhum
  arquivo do caminho de detecção foi tocado -- `preprocess`, `detection` e `detection.embedded`
  batem exato --, e nenhuma preferência de motor entra numa medição de campo (o `--ocr` dela nasce
  `off`). O conserto é remedir os quatro (`~1 min por modelo`), o que escreve em `docs/metrics/`;
  este executor foi instruído a não tocar ali, então a guarda fica vermelha com o motivo escrito
  em vez de com um número reescrito à mão.

### Testes

- `tests/test_ui_motor_declarado.py` (novo, puro): os tetos das quatro opções e o que acontece sem
  memória conhecida; opção desconhecida levanta; as cinco frases de recusa; o caminho vazio e o
  caminho entre aspas; e as seis linhas de `plano_de_aplicacao` -- nada mudou, `Hash`/`Threads` por
  `setoption`, `MultiPV`/tempo por análise, `SyzygyPath` no processo, o binário derrubando, e o
  mesmo caminho escrito diferente **não** derrubando.
- `tests/test_qt_motor.py::OpcoesDoMotorTests` (novo): as sete afirmações do critério, contra o
  motor falso -- que passou a **declarar** opções (`tests/fake_uci_engine.py`), porque `configure`
  recusa o que o motor não anunciou e sem isso o teste mediria o caminho de degradação.
- `tests/test_qt_motor.py::DialogoDoMotorTests` (novo): a faixa de cada campo, o que está gravado
  aparecendo, a recusa na própria janela, e os números da máquina lidos de verdade.
- `tests/test_settings.py` continua valendo sobre os três campos novos (a coerção por campo da
  S-124 não mudou).
- `tests/test_ui_barra_da_sala.py::test_do_grupo_motor_so_as_opcoes_existem_sem_motor` (reescrito):
  era `test_o_motor_so_existe_com_motor`, e a regra ficou mais precisa em vez de mais frouxa --
  sem motor o grupo tem **uma** ação, e o teste diz qual.

### O que o crítico recusou

Primeira rodada, 2026-09-04. **Aprovada com uma ressalva**, e ela era a única coisa que a S-33 não
cobria: o binário que abre e **não fala UCI**.

| O que ele achou | Como estava | O que mudou |
|---|---|---|
| Apontar as preferências para `python.exe` dá dez segundos de espera e depois a frase `TimeoutError`, crua e em inglês | `popen_uci` levanta `TimeoutError`, cujo `str()` é **vazio**; `cli.message_for` cai então no nome da classe | `engine.MotorNaoRespondeu`, com a frase de `motor_declarado.frase_de_motor_que_nao_responde`. Ela nomeia o arquivo, o que falhou e o que sobrou: *"O programa em ... não respondeu ao protocolo UCI em dez segundos. Ou ele não é um motor de xadrez, ou não conseguiu abrir. A sala segue sem motor."* |
| — | — | **E a primeira tentativa de conserto não pegou**, o que virou uma linha de docstring: no Python 3.10 `asyncio.TimeoutError` **não** é o `TimeoutError` embutido (só a partir do 3.11 um é apelido do outro), e capturar o embutido deixava a palavra `TimeoutError` na tela do mesmo jeito. Os dois estão em `engine.FALHAS_AO_ABRIR` |

Ele confirmou o resto: nenhum processo vaza, a janela não congela (653 voltas de linha de eventos
durante os 10 s da espera), a seção some quando o motor não sobe, os tetos e as cinco recusas de
validação estão certos.

- `tests/test_engine.py::test_um_binario_que_nao_fala_uci_levanta_a_frase_em_pt_br` (novo) e
  `tests/test_ui_motor_declarado.py::test_a_frase_do_binario_que_nao_e_motor_nomeia_o_arquivo_e_o_que_sobrou`
  (novo). O teste usa um binário que **morre** em vez de calar -- o caminho de tradução é o mesmo e
  não custa os dez segundos da suíte.

## S-537 · Análise de partida: cada lance avaliado, gráfico de avaliação e erros marcados — ✅ **implementada em 2026-09-04**

### Problema

A sala sabia avaliar **uma** posição desde a S-33 e gravar o número no lance desde a S-285
(`qt/painel_de_estudo.py:923`, `_gravar_avaliacao`, que escreve `[%eval 0.35,18]` no nó corrente).
O que não existia era a passada pela partida inteira: nem em `qt/`, nem em `ui/`, nem na linha de
comando. `analyse` (`:878`) avalia o nó em que se está, e a análise contínua o segue enquanto se
navega -- lance a lance, à mão, e sem nada que junte o resultado.

A pergunta que faltava é a do dia seguinte ao torneio: **em que lance eu perdi?** Respondê-la com o
que havia é apertar `→` quarenta vezes lendo um número no canto da tela. Não havia gráfico, não
havia classificação de erro e não havia marca nenhuma na lista de lances -- os NAGs existiam
(`estudo.NAGS_DE_LANCE`) e só quem os punha era a pessoa, pelo menu de símbolos da S-278.

### Solução

**A decisão pura, `ui/analise_da_partida.py`.** Quanto um lance custou, onde estão os cortes, e onde
o gráfico põe cada ply.

1. **Os cortes são 50, 100 e 300 centipeões de perda**, que é a tabela clássica do Lichess (`lila`,
   `Advice.scala`) e a mesma que o Scid usa: `?!`, `?` e `??`. A perda é medida do ponto de vista de
   **quem jogou** e nunca é negativa -- um lance que melhora a avaliação não é um lance "ganho", é o
   motor tendo mudado de ideia com mais um ply, e registrar isso encheria a partida de `!` que
   ninguém jogou.
2. **Duas regras protegem a partida já decidida, e a segunda foi encontrada medindo.** A primeira é
   o **teto** de ±10 peões antes de qualquer diferença, que é o que o próprio Lichess faz: de +18
   para +12 as duas viram +10 e a perda é zero. A primeira redação parava aí, e a medição mostrou o
   buraco: de +18 para +9 o teto clampa em 1000→900 e sai um "erro" numa posição em que qualquer
   lance ganha. Daí `POSICAO_DECIDIDA` (cinco peões): um lance que **começa e termina** ganho por
   cinco peões não recebe juízo. O Lichess resolve o mesmo caso pela escala de expectativa de
   vitória; adotá-la aqui significaria uma segunda curva no programa, discordando da que a barra
   lateral desenha, e a regra explícita diz a mesma coisa em voz alta. Cair de +6 para +2 continua
   sendo erro grave, que é o outro lado dela.
3. **O símbolo é NAG, e é isso que o torna útil.** `?!` = `$6`, `?` = `$2`, `??` = `$4` -- os
   códigos do padrão PGN, os mesmos que o menu de símbolos já oferece. A lista de lances os desenha
   pelo caminho que já existe, o `Ctrl+Z` os desfaz, e qualquer programa de xadrez lê `12. Bd3?? $4`.
   Uma marca só de tela morreria ao fechar a sala.
4. **O gráfico é a curva da barra girada 90°**, e o eixo do tempo é o **ply** e não o lance: um erro
   das pretas no 24 e um das brancas no 25 são dois pontos vizinhos, e agrupá-los esconderia um dos
   dois. Brancas para cima, e o clique leva ao lance (`indice_no_x`) -- o gráfico existe para achar
   onde a partida virou, e um gráfico que não leva até lá deixa a busca para o dedo.

**A fiação, `qt/analise_da_partida.py` (novo).** Uma `Tarefa` de `qt/trabalho.py` com progresso por
sinal e `threading.Event` de cancelamento, na forma que `qt/indice_da_base.py` já usa -- as duas são
a mesma operação longa com barra e Cancelar, e duas formas para isso seriam duas caixas que se
comportam diferente na mesma janela. **A árvore não atravessa a fronteira de thread**: o worker
recebe as FENs de `percurso` e devolve números; quem escreve nos nós é a sala, depois, na linha de
eventos. Passar `GameNode` para a thread seria lê-los enquanto alguém promove uma variante.

**`percurso` devolve `n+1` posições para `n` lances**, e a conta é o que define o trabalho: a
avaliação "depois" de um lance é a "antes" do seguinte, então analisar par a par pediria `2n` buscas
para responder o mesmo. Só a linha principal: as variantes são o que quem estuda escreveu **sobre**
a partida.

**O gráfico é `QPainter` e nada mais.** Sem biblioteca -- e não por peso: um gráfico com eixos,
legenda e escala automática seria pior aqui, porque o eixo vertical não tem unidade que se escreva
(é fração de vantagem) e o horizontal é o ply, que a lista ao lado nomeia. Duas faixas -- o que está
**abaixo** da curva é das brancas, o que está acima é das pretas, nas mesmas cores da barra --, a
linha do equilíbrio tracejada por cima, e um ponto sobre cada lance julgado. A primeira redação
preenchia só a área entre a curva e o meio, com uma cor: na fotografia o gráfico saiu inteiro claro
e não dava para ver de quem era a partida em ponto nenhum.

#### O que a segunda rodada trocou (2026-09-04)

O crítico reprovou o item em três pontos, e o primeiro derruba a decisão 2 acima.

1. **O juízo passou a ser medido em expectativa de vitória, e a "posição decidida" sumiu.** A
   tabela em centipeões discordava do Lichess em **6 dos 12** juízos de uma partida de torneio
   real, e a razão é estrutural: meio peão não vale o mesmo no equilíbrio e com nove peões de
   vantagem. A escala nova é a **mesma curva** que a barra desenha (`engine.fracao_de_vantagem`),
   em pontos percentuais, e os cortes foram **medidos** e não convertidos: 256 lances de três
   partidas do gigabase, profundidade 16. Ver `_CORTES` para a varredura. Com isso a regra
   `POSICAO_DECIDIDA` deixou de ser necessária -- ela existia para tapar um caso que a escala de
   peões criava, e o crítico tinha achado **o outro lado dela**: com as pretas perdidas, cair de
   -6 para -10 saía como *erro grave*, porque a regra media `min` do ponto de vista de quem jogou
   e só protegia quem estava ganhando. Na escala nova esse lance custa 2,75 pontos de chance, e
   o caso original (+18 → +9) custa 0,24. Uma regra a menos, e a que sumiu era a defeituosa.
2. **O teto por posição passou a escalar com a profundidade, e o que ele trunca é contado.** Pedir
   30 dava, medido pelo crítico, 41 de 46 posições paradas no teto de 3 s e profundidade média de
   23,5: a profundidade que o diálogo oferece **não existia**, e a tela não dizia isso. Agora o
   teto é `3 s × 1,4^(plies-16)`, limitado a 30 s (`teto_por_lance_ms`), e o relatório traz um
   segundo rótulo com quantas posições pararam antes de chegar lá. O 1,4 é medido: ver
   `FATOR_DE_TETO_POR_PLY`.
3. **O relatório ganhou precisão e ACPL**, que eram os dois números que a ChessBase e o Lichess
   põem no topo e que não apareciam em lugar nenhum. A fórmula de precisão é a do Lichess
   (`103,1668·e^(-0,04354·perda) - 3,1669`, média por lance) aplicada à expectativa **daqui**.

E mais três dos "deveria" dele: o progresso conta a partir de **1** e sobre o número de lances (a
tela dizia `lance 0 de 62` numa partida de 61); o gráfico ganhou **marca do lance corrente** (um
fio vertical) e **dica** com o ply, o lance e a avaliação sob o ponteiro; e a lista de lances
deixou de escrever `g6 ?` com espaço -- o símbolo cola no lance, como o EPUB já fazia
(`estudo_paragrafos._COLA_NO_ANTERIOR`), com o espaço guardado em `Trecho.token` para o texto
continuar igual ao do exportador.

**Um defeito de `engine.py` apareceu na fotografia e foi consertado aqui.** `score mate 0` -- o que
o UCI responde na posição em que quem joga está mateado -- **não carrega sinal**: `Mate(0)` e
`MateGiven` respondem `0` a `.mate()`. Sem normalizar, a posição final de toda partida ganha valia
`-M0`, a barra ia para o lado do perdedor e a análise marcava o lance de mate como **erro grave de
quem deu o mate** (`7. Nd5#?? — erro grave (perdeu 20,00)`, na fotografia). `_to_white_pov`
normaliza para `±1`.

### Critério de aceite

Medido em 2026-09-04, Stockfish dev-20230303, 1 thread, `Hash` 128 MB.

- **A partida inteira, com profundidade escolhida.** ✅ A Imortal (45 plies, 46 posições,
  `scratchpad/medir_motor.py`): profundidade 12 em **1,6 s**, 16 em **8,5 s**, 20 em **42,1 s**. As
  três acharam catorze lances com símbolo; profundidade 12 discorda da 16 em **4** juízos e a 20 em
  **3**. Dezesseis é o padrão: cinco vezes o tempo de 12 para trocar quatro juízos, e mais cinco
  vezes para trocar outros três.
- **Progresso e cancelamento.** ✅ Um sinal por posição (`n+1`), com o SAN do lance na frase. O
  Cancelar para em **menos de 1,5 s** (medido: `esperar(1500)` devolve verdadeiro e a `QThread`
  termina), e **não deixa thread viva**. O que já foi avaliado fica: cancelar no meio de 40 lances
  devolve os avaliados até ali. A granularidade é uma posição, limitada por `TETO_POR_LANCE_MS`
  (3 s) além da profundidade.
- **Gráfico com `QPainter`, sem biblioteca.** ✅ 732×140 px no relatório, um ponto por ply, e o
  clique devolve o índice do ply sob o pixel. Nenhuma dependência nova.
- **Os cortes do Lichess, registrados.** ✅ 50 / 100 / 300 centipeões, com o teto de ±10 peões e a
  regra da posição decidida (5 peões dos dois lados).
- **`[%eval]` em cada lance e o símbolo nos erros.** ✅ Na defesa de Legall (13 plies): `13 lance(s)
  avaliados, 4 com símbolo`, e a lista de lances mostra `d6 ?!  Bg4 ?!  g6 ?  Bxd1 ??`. O resumo diz
  `Brancas: sem erro | Pretas: 2 imprecisões, 1 erro, 1 erro grave`.
- **O relatório leva ao lance.** ✅ Clicar no gráfico ou na lista de erros move o tabuleiro para
  aquele ply.
- **A escrita da máquina não entra na pilha de desfazer** e não adia a gravação por inatividade --
  é a regra da S-285/S-345, e a análise da partida passa por ela uma vez, no fim, e não por lance.
- **O plural concorda.** ✅ `2 imprecisões`, e não `2 imprecisão`, que foi o que saiu na primeira
  fotografia.
- **O que ficou de fora, e é a linha para o relatório**: a análise não guarda o resultado entre
  sessões (o `[%eval]` vai para o PGN, o juízo vira NAG, mas o gráfico é recalculado a cada rodada);
  e o Cancelar tem a granularidade de uma posição, porque interromper um `go` no meio exigiria o
  protocolo assíncrono do UCI -- uma segunda forma de falar com o motor por causa de um botão.

#### Segunda rodada, medida em 2026-09-04

Stockfish dev-20230303, 1 thread, `Hash` 16 MB, profundidade 16. A partida do crítico é
`Nouali - Boudechiche, ALG-ch (Women) 2012`, 61 plies, tirada de 55% do gigabase.

- **Os juízos concordam com o Lichess.** ✅ Em 256 lances de três partidas: a tabela em centipeões
  discordava em **14**, a escala de expectativa discorda em **4**. Na partida do crítico, de **6**
  para **2**. Os dois lances que ele nomeou saem certos: `9...O-O` (0,46 → 2,94) agora é `??` como
  no Lichess, e `27...Kh7` (+3,04 → +3,86) deixou de ser marcado.
- **A varredura dos cortes.** ✅ Platô de 4 divergências entre 24 e 26 (erro grave), 15 e 16 (erro)
  e 8 (imprecisão); 25/15/8 é o meio dele. Marcados: 29 lances de 256, contra 28 do Lichess e 32 da
  tabela em peões.
- **A posição decidida, dos dois lados.** ✅ +18 → +9 custa **0,24** ponto de chance; as pretas
  perdidas de −6 → −10 custam **2,75** -- nenhum dos dois recebe símbolo, e agora **sem regra**.
- **O custo de cada profundidade, remedido sem teto** (13 posições da partida, extrapolado para as
  62): **10 s** a 16, **44 s** a 20, **3 min** a 24 e **16 min** a 30 -- 1,4 por ply. O pior caso
  por posição vai de 0,55 s a 16 até 34,2 s a 30. Com o teto novo, as profundidades 16, 20 e 24
  chegam inteiras nas 13 posições; só a 30 trunca uma, e o relatório a conta.
- **Precisão e ACPL no relatório.** ✅ `Brancas: ... — precisão 90%, perda média 30 centipeões |
  Pretas: ... — precisão 86%, perda média 51 centipeões` na partida medida.
- **O progresso conta lances.** ✅ `Analisando o lance 1 de 61 (c4)…` a
  `Analisando o lance 61 de 61 (Rf8+)…` (era `Analisando o lance 0 de 62`).
- **O símbolo cola no lance.** ✅ `9... O-O?? — erro grave (perdeu 2,61)` no relatório, e `g6?` na
  lista de lances; o texto da lista continua igual, token a token, ao do `StringExporter`.
- **O gráfico diz onde a sala está e o que há sob o ponteiro.** ✅ Fio vertical em
  `VIZINHA_TEXTO` -- o único papel da paleta que passa de 3:1 contra as duas faixas (5,46:1 sobre
  a clara, 3,29:1 sobre a escura) -- e a dica `ply 31 · 16. Be3 · avaliação 2,97`.
- **O Cancelar continua parando rápido** na profundidade padrão: **125 ms** medidos, sem thread
  viva. Na profundidade 30 a espera máxima passa a ser o teto de 30 s, e isso é o preço declarado
  de a profundidade 30 existir.
- **O `[%eval]` na posição já matada, ligado em 2026-09-04.** A decisão existia (`grava_avaliacao`,
  e `Avaliado.acabou` sai do tabuleiro, não do motor) e faltava a linha em
  `qt/painel_de_estudo.py::_marcar_os_lances` -- arquivo que a Fase 83 estava escrevendo e que o
  executor da S-537 foi instruído a não abrir. Ela entrou assim que ele ficou livre, e
  `analise_da_partida.grava_avaliacao` saiu de `SEM_CHAMADOR` em `tests/test_ui_orfaos.py`.
  **O que se pula é a avaliação, e não o nó**: a posição que acaba a partida também pode ser um
  afogamento, e afogar no lugar de matar é o `??` que esta passada existe para achar -- o símbolo
  continua sendo escrito no lance que a acabou. Medido no PGN gravado de `1. f3 e5 2. g4 Qh4#`:
  três `[%eval]` em quatro lances, e nenhum no último.

### Testes

- `tests/test_ui_analise_da_partida.py` (novo, puro): os três cortes nos seis limites; a maioria dos
  lances sem símbolo; os NAGs do padrão; a perda das brancas e a das pretas; o lance que melhora não
  vira ganho; o teto apagando a diferença quando os dois lados estouram; **a posição decidida sem
  juízo, e o cair de ganho para melhor com juízo**; mate em 3 e mate em 30 valendo o mesmo; o
  percurso `n+1` só da linha principal; as bordas e o sentido do gráfico; a escala não linear medida
  em pixel; o clique fora da faixa caindo na ponta; o resumo por cor, o plural e as duas frases
  finais.
- `tests/test_qt_motor.py::AnaliseDaPartidaTests` (novo): **o cancelamento em menos de 1,5 s sem
  thread viva** e o que já foi avaliado ficando (com um analisador lento injetado, para o teste
  medir o cancelamento e não a máquina); um sinal de progresso por posição; partida sem lance não
  começa rodada; o gráfico desenha e o clique devolve o ply.
- `tests/test_qt_motor.py::PartidaAnalisadaNaSalaTests` (novo): a gravação de `[%eval]` e do símbolo
  na árvore, com o `??` aparecendo na lista de lances; o relatório levando ao ply; e as duas
  recusas (sem lance, sem motor). Desde 2026-09-04, também
  `test_a_posicao_ja_matada_nao_leva_eval_para_o_pgn`: o PGN gravado sem o `[%eval]` da posição
  final, e o símbolo ficando nela.
- `tests/test_engine.py::test_o_mate_ja_dado_aponta_para_quem_o_deu` (novo): o `mate 0` sem sinal.

Na segunda rodada, em `tests/test_ui_analise_da_partida.py`: os três cortes nos seis limites da
escala nova; a expectativa sendo a curva de `engine` e não uma segunda; **os dois lances que o
crítico nomeou**, pelos números da partida real; a posição ganha e a **posição perdida** sem juízo,
as duas sem regra nenhuma. Em `tests/test_qt_motor.py::AnaliseDaPartidaTests`: o teto crescendo com
a profundidade e parando no teto do teto; a frase de truncamento e o segundo rótulo do relatório;
precisão e perda média no resumo; `grava_avaliacao` recusando a posição já matada, e o laço do
motor marcando `acabou` na posição depois de `Qh4#`; a marca do lance corrente no gráfico (em pixel)
e a dica sob o ponteiro; e o progresso contando de 1 sobre o número de lances.

### O que o crítico recusou

Primeira rodada, 2026-09-04. Reprovada em três pontos; os reprodutores dele estão em
`scratchpad/crit_motor/` (`crit_juizo.py`, `crit_relatorio.py`).

| O que ele achou | Como estava | O que mudou |
|---|---|---|
| **Os cortes discordam do Lichess em 6 de 12 juízos** de uma partida real: `9...O-O` (0,46→2,94) sai `?` e o Lichess dá `??`; `27...Kh7` (+3,04→+3,86) sai `?!` e o Lichess não marca nada | 50/100/300 **centipeões** de perda | 8/15/25 **pontos de expectativa de vitória**, na curva que o programa já tinha. Divergências: 14 → 4 em 256 lances; 6 → 2 nessa partida |
| **"Posição decidida" protege só quem ganha**: pretas perdidas −6→−10 sai `erro grave` | `min(antes, depois)` do ponto de vista de quem jogou | a regra **sumiu**. A escala de expectativa resolve os dois lados sozinha (2,75 pontos, e 0,24 no caso que criou a regra) |
| **A profundidade 30 que o diálogo oferece não existe**: 41 de 46 posições param no teto de 3 s (média 23,5), e 30 custa o mesmo que 24 | teto fixo de 3 s por posição | teto = `3 s × 1,4^(plies-16)`, limitado a 30 s, **e** o relatório conta quantas posições pararam nele. O diálogo passou a dizer o custo medido de cada profundidade |
| Sem precisão (%) nem ACPL no relatório | nenhum dos dois existia | os dois no resumo, por cor. Medido: brancas 90% e 30 cp, pretas 86% e 51 cp |
| O progresso diz "lance **0** de 62" | o índice da posição saía como número de lance | conta de 1 sobre o número de **lances**, e nomeia o lance que está sendo avaliado |
| A lista escreve `g6 ?` com espaço antes do símbolo | o SAN levava sempre um espaço no fim | o espaço vai para `Trecho.token` (o PGN continua `g6 $2`) e o desenho cola o símbolo |
| `[%eval #1]` gravado na posição já matada | `mate 0` é normalizado para `±1`, que a barra precisa | `Avaliado.acabou` + `grava_avaliacao`, e `_marcar_os_lances` os chama desde 2026-09-04 -- ver o critério de aceite |
| Sem marca do lance corrente no gráfico nem dica com ply e avaliação | o gráfico só tinha a curva e os pontos de erro | `GraficoDaPartida.marcar` (fio vertical + anel) e `frase_em`, que troca a dica a cada movimento do ponteiro |

## S-538 · Tablebases Syzygy quando a pasta existir: resultado exato nos finais — ✅ **implementada em 2026-09-04** (segunda rodada: medida contra tabela real)

### Problema

Um motor num final de cinco peças ainda está chutando. `engine.py` -- o módulo inteiro, antes deste
item -- só sabia perguntar ao processo UCI, e `Evaluation.display` (`engine.py:112`) devolvia
`+3,45` numa posição que ou é ganha ou é tábua: não existe `+3,45` ali. Num final de torre contra
bispo ele diz `+0,26` a profundidade 23 sobre uma tábua teórica -- medido na segunda rodada, com a
tabela real ao lado --, e quem estuda finais aprende o número errado.

Nada no projeto mencionava tablebases: nem `settings.py` (`EngineSettings:175` tinha três campos),
nem `engine.py`, nem a sala. E o `python-chess`, que é dependência obrigatória desde sempre, traz
`chess.syzygy` embutido -- a peça que faltava era a **decisão** de quando perguntar e o que dizer.

### Solução

**A pasta é opcional e sem padrão, e é a mesma regra da S-32.** Os arquivos de cinco peças somam
~1 GB e os de seis, ~150 GB: nada disso vem no repositório, nada disso tem caminho presumido, e
sem pasta configurada **nada muda** -- o painel continua mostrando o que o motor disse.
`EngineSettings.syzygy_path` entra pelo mesmo diálogo da S-536.

**A decisão pura, `ui/finais.py`.** Quando vale perguntar (`deve_consultar`: só com pasta, e só até
sete peças -- acima disso não existe arquivo que possa estar lá, e perguntar seria pagar a ida ao
disco em toda posição de meio-jogo), quando a tabela vence o motor (`vence_o_motor`: quando ela
**responde**; `None` é o caso comum de quem tem só os cinco peças), como a resposta se lê
(`frase_do_resultado`) e o que ela faz com a barra (`centipeoes_de`).

**O que Syzygy sabe e o que ele não sabe, e é a decisão que mais custou.** WDL dá o resultado com
jogo perfeito; DTZ dá a distância até a próxima captura ou lance de peão. **Nenhum dos dois é
distância até o mate.** "Mate em N" é o que o *motor* diz quando ele mesmo carrega as tabelas -- e é
por isso que `SyzygyPath` também vai para o processo, por `setoption`, pelo caminho da S-536: as
duas metades da resposta chegam, cada uma de quem a tem. O que este módulo escreve é o resultado
exato e a distância que o arquivo **contém**: `Tábuas (tabela de finais).` ou `Tabela de finais:
vitória das brancas, zeragem em 14.` Chamar a zeragem de "mate em N" poria na tela um número que a
tabela não guarda.

**O sujeito da frase é quem está no lance**, porque é assim que o WDL de Syzygy é definido: `-2` com
as pretas na vez é *derrota das pretas*, e não *vitória das brancas*. Inverter o sinal antes de
escrever seria uma conta a mais no caminho entre o arquivo e a tela, num lugar em que errá-la dá uma
frase que afirma o contrário do arquivo. **E o `±1` tem nome próprio**: é a vitória que a regra dos
50 lances anula -- chamá-la de vitória mentiria sobre o resultado da partida, e chamá-la de tábuas
esconderia que o final é ganho. Ela sai como "vitória teórica", e vale **zero** na barra, porque no
placar da partida ela é tábua.

**O leitor, `src/chess_diagram_ocr/tablebase.py` (novo).** Irmão de `engine.py`, com a mesma forma:
`abrir(pasta)` devolve `None` sem pasta, o diretório é varrido **na primeira consulta** (do mesmo
modo que o processo do motor só sobe na primeira análise) e fica aberto, e **toda falha vira "não
sei"**. Direito de roque é `None` e não erro -- Syzygy não representa roque, e `probe_wdl` levanta
`ValueError` ali.

#### O que a segunda rodada trocou (2026-09-04)

**Há tablebase Syzygy nesta máquina, e a primeira rodada não a viu.** O crítico achou **35
conjuntos** -- todos os de 3 e 4 peças, 4,1 MB, `.rtbw` e `.rtbz` -- dentro do *sdist* do próprio
`python-chess`, no cache do `uv`
(`AppData/Local/uv/cache/sdists-v9/pypi/chess/1.11.2/.../src/data/syzygy/regular`). A primeira
rodada procurou em `C:/Program Files` e no **wheel** instalado, e concluiu que o menor conjunto
útil passa de 1 GB. Passa mesmo, a partir de cinco peças; o que não passa é o conjunto pequeno que
o próprio `python-chess` embarca para os testes dele. **A dívida do item era essa, e ela fecha.**

**E medir de verdade achou um defeito que a injeção não podia achar.** Com `SyzygyPath` no motor, o
Stockfish imprime a vitória por tabela como `cp 20000 - ply` (`UCI::value`), e o painel mostrava
**`+200,00`** -- com `[%eval 200.0]` indo para o arquivo. Duzentos peões não é uma avaliação.
`engine._to_white_pov` passou a reconhecer a faixa (`CP_MINIMO_DE_TABELA`, 150 peões) e a devolver
`Evaluation.tabela = ±1` com o `score_cp` reescrito no teto de dez peões: o `display` vira `1-0` /
`0-1` -- os tokens do PGN que a barra já usava --, a barra vai ao teto, e o arquivo recebe um
número que quer dizer "decidido" em vez de um número inventado.

**Na sala**, a consulta acontece na mesma thread do motor, **antes** dele: ela responde em
microssegundos, e perguntar depois faria a tela mostrar a estimativa e trocá-la um instante depois.
A frase substitui a avaliação e a barra vai para onde o resultado manda (`1-0`, `0-1`, `=` -- os
tokens do PGN, que não têm idioma); **as linhas candidatas continuam sendo as do motor**, porque a
tabela diz o resultado e não a variante.

### Critério de aceite

- **Sem pasta configurada, nada muda.** ✅ `abrir("")` devolve `None`, `deve_consultar` responde
  falso, e a sala mostra o que o motor disse -- afirmado com o Stockfish de verdade num final de
  três peças.
- **Pasta configurada e vazia responde "não sei".** ✅ Contra o `chess.syzygy` **de verdade**
  apontado para um diretório sem arquivo: `get_wdl` devolve `None` em vez de levantar, e o painel
  volta à estimativa. É a máquina de quem configurou a pasta e não baixou as tabelas.
- **Com resposta, o resultado exato chega à tela.** ✅ `Tabela de finais: derrota das pretas,
  zeragem em 12.` no lugar de `+0,35`, e `Tábuas (tabela de finais).` pondo a barra no meio
  (`fracao == 0.5`).
- **Até sete peças pergunta; acima não.** ✅ E a contagem inclui os dois reis, como Syzygy nomeia os
  arquivos.
- **`SyzygyPath` chega ao motor por `setoption`**, sem derrubar o processo. ✅ É a S-536: o plano de
  aplicação o trata como opção de processo, e o Stockfish desta máquina a declara
  (`option name SyzygyPath type string`).
#### Segunda rodada: medido contra tabela real, 2026-09-04

35 conjuntos de 3 e 4 peças (5 + 30), 4,1 MB, copiados para `scratchpad/syzygy345/`; Stockfish
dev-20230303, 1 thread. Roteiros: `scratchpad/r2/medir_finais.py` e `procurar_50.py`.

- **A tabela sabe o que o motor chuta.** ✅ Três casos medidos:

  | final | o que o motor diz | o que a tabela diz |
  |---|---|---|
  | KRvKB, posição de Philidor (`8/8/8/8/8/4kb2/8/4K2R w`) | `+0,26`, profundidade 23 | `wdl 0` → **Tábuas (tabela de finais).** |
  | KBNvK (`8/8/8/4k3/8/8/8/2BNK3 w`) | `+2,31`, profundidade 25 | `wdl +2, dtz 56` → **vitória das brancas, zeragem em 56** |
  | KRvKP com as **pretas** a jogar | `+4,98`, profundidade 24 | `wdl −2, dtz −8` → **derrota das pretas, zeragem em 8** |

- **O sujeito da frase é quem está no lance.** ✅ O terceiro caso acima: `−2` com as pretas na vez
  é *derrota das pretas*, e a barra vai para as brancas (`cp +1000`) sem que ninguém inverta sinal
  no caminho entre o arquivo e a tela.
- **DTZ não é distância até o mate.** ✅ O KBNvK mateia em ~30 lances e a tabela guarda 56 de
  zeragem -- são coisas diferentes, e a frase não as confunde.
- **O tempo de consulta.** ✅ 500 consultas: mediana **123 µs**, p95 **196 µs**, pior 1,1 ms; a
  primeira custa **6,6 ms** (a varredura do diretório). Uma análise a 800 ms é ~6.500 vezes mais
  cara, e é isso que autoriza perguntar antes do motor em toda posição de final.
- **Seis peças degradam.** ✅ `deve_consultar` responde verdadeiro (o teto é sete) e a tabela
  responde `None`: um KRPvKRP não está nesta pasta, e ali a estimativa do motor volta a ser a
  melhor resposta que existe. O mesmo vale para os conjuntos de 5 peças, que esta pasta também não
  traz.
- **Roque continua sendo "não sei".** ✅ `8/8/8/4k3/8/8/8/R3K3 w Q` devolve `None`; a mesma sem o
  direito de roque devolve `wdl +2, dtz 27`.
- **`SyzygyPath` chega ao motor, e o `+200,00` acabou.** ✅ No KBNvK: sem tabela o Stockfish diz
  `+2,26`; com a pasta configurada ele responde `cp 20000` e a tela mostra **`1-0`**, com
  `score_cp` de 1000 e `tabela = +1`. Antes disso a tela dizia `+200,00` e o PGN recebia
  `[%eval 200.0]`.
- **⚠ O que continua sem medição real, e agora é uma dívida pequena e nomeada**: a **vitória
  anulada pela regra dos 50 lances** (`wdl ±1`). Procurada por amostragem em **1,45 milhão** de
  posições sorteadas sobre os 35 conjuntos: `{-2: 449.664, 0: 574.693, +2: 430.327}` e **nenhum
  ±1**; o maior DTZ visto foi **65** (KBNvK com as pretas a jogar). Faz sentido -- o *cursed win*
  precisa de mais de 50 lances até a zeragem, e isso praticamente só aparece de cinco peças em
  diante. A frase e a barra do `±1` continuam afirmadas contra a tabela **injetada**, que é o que
  a injeção existe para permitir.

### Testes

- `tests/test_tablebase.py` (novo): a decisão pura -- sem pasta nunca se pergunta, o teto de sete
  peças, a contagem com os reis, a tabela vencendo o motor só quando responde; as frases -- tábuas,
  o sujeito sendo quem joga nos três casos, a zeragem **não** sendo mate, a vitória teórica, e a
  barra indo para o resultado (com o `±1` valendo zero); e o leitor -- pasta vazia de caminho, pasta
  que não existe, **pasta vazia contra o `chess.syzygy` real**, a resposta inteira com tabela
  injetada, quem só baixou as WDL, o roque virando "não sei" sem nem perguntar, a falha da tabela
  virando "não sei", e o `close`.
- `tests/test_qt_motor.py::TablebaseNaSalaTests` (novo): a tabela vencendo a estimativa do motor na
  sala, as tábuas pondo a barra no meio, sem pasta nada mudando, e as linhas do motor continuando
  a ser as do motor.
- `tests/test_ui_motor_declarado.py::test_a_pasta_de_tablebases_e_opcao_do_processo` e
  `test_pasta_no_lugar_do_binario_e_binario_no_lugar_da_pasta`: a pasta entrando por `setoption` e
  a validação dela.
- `tests/test_tablebase.py::TabelaRealTests` (novo, segunda rodada): a tabela **de verdade**. Ele
  procura a pasta -- `CVOFF_SYZYGY_PATH`, e sem ela o cache do `uv` -- e **pula com o motivo
  escrito** quando não a acha: uma suíte não pode exigir 1 GB de tabela, mas também não pode fingir
  que 4 MB não estão ali. Cinco afirmações: o final que o motor chuta e a tabela resolve, o KBNvK
  com a zeragem que o arquivo guarda (e que **não** é mate), o sujeito da frase sendo quem joga, o
  conjunto ausente virando "não sei", e a consulta em microssegundos.
- `tests/test_engine.py::test_o_score_de_tablebase_do_uci_vira_resultado_e_nao_duzentos_peoes`
  (novo): o `cp 20000` do Stockfish virando `1-0`.

### O que o crítico recusou

Primeira rodada, 2026-09-04. **Aprovada** -- e ele achou o que muda o item: há tabela Syzygy nesta
máquina. Reprodutor: `scratchpad/crit_motor/crit_finais.py`.

| O que ele achou | Como estava | O que mudou |
|---|---|---|
| **Há 35 conjuntos Syzygy reais nesta máquina**, dentro do sdist do `python-chess` no cache do `uv` | o item estava em ⚠ por "nenhuma consulta a uma tabela real", com a busca limitada a `C:/Program Files` e ao wheel instalado | medido de verdade: WDL, DTZ, o sujeito da frase, o tempo de consulta, a degradação em 6 peças e o roque. O item fecha em ✅ |
| **Com `SyzygyPath` no motor, o painel mostra `+200,00` e grava `[%eval 200.0]`** | o `cp` do UCI era lido como centipeões, e o Stockfish usa a faixa acima de 20.000 para a vitória por tabela | `Evaluation.tabela` e `CP_MINIMO_DE_TABELA`: o display vira `1-0`/`0-1`, a barra vai ao teto de dez peões, e é esse número que vai para o arquivo |
| (dele, a conferir) a pasta tem "3 a 5 peças" | — | são **3 e 4**: 5 conjuntos de três peças e 30 de quatro. O maior conjunto ali é `KQRvK`, e nenhum de cinco |

## S-539 · Táticas do próprio acervo: FEN reconhecida + solução impressa vira exercício — ⚠ **implementada e medida em 2026-09-04: 2 exercícios confiáveis em 2.788 diagramas**

### Problema

Depois de uma varredura, um livro de exercícios do acervo é mil FENs e nenhum exercício -- porque
exercício é posição **mais** gabarito. `pdf_to_pgn.py:667` (`build_pgn_games`) escreve o que existia:
*"um jogo por posição, só com headers -- o diagrama é a posição inicial"*, com `SourcePDF`, `Page`,
`Diagram` e `Caption`. A legenda é o que estava **ao lado** do tabuleiro; a solução não é a legenda,
e no livro de táticas ela está numa lista no fim do capítulo, atada ao diagrama pelo **número**.

As duas metades da resposta já existiam e nunca tinham se encontrado. `text/notacao.py:421`
(`validar`) sabe jogar uma linha impressa sobre uma posição e dizer no primeiro lance que ela não
sustenta qual foi; `qt/painel_de_estudo.py:1930` (`jogar_a_linha_do_livro`) faz isso **um diagrama
de cada vez**, à mão, com a folha aberta na aba Texto. O que faltava era a passada pelo livro
inteiro e a régua que diz *qual* linha é a deste diagrama.

### Solução

**Um módulo puro, `taticas.py`**, com quatro decisões, e nenhuma delas abre PDF nem roda modelo
(`de_pdf` é um adaptador de import tardio).

1. **O número impresso é achado pela geometria, e o candidato é a LINHA e não o parágrafo.** Três
   condições contra a caixa do diagrama: o texto é *só* o número (`_SO_NUMERO`), ele cruza a faixa
   horizontal do tabuleiro -- é da mesma coluna --, e a distância vertical cabe em
   `DISTANCIA_DO_NUMERO` (0,45 da altura do tabuleiro). **Perguntar ao parágrafo dava zero**: no
   `Big Book of Combinations` o número e a legenda são um bloco só (`5 / Morphy-De Riviere / Paris,
   1858`), porque a leitura agrupa linhas vizinhas. Perguntando à linha, 95,8% dos 1.005 diagramas
   daquele livro têm número. Uma **corrida** completa os buracos e corrige o intruso: `97 98 ? 100`
   vira `97 98 99 100`, e um `1858` que se passou por número é substituído quando a maioria dos
   outros concorda num deslocamento. Sem maioria, nada é preenchido nem corrigido.
2. **A lista de soluções é lida contra os números que os diagramas reivindicam, e não em branco.**
   Uma varredura cega de `^\d+\.` acha os números de **lance** de dentro de cada solução -- `214.
   Ahues - NN, 1932. 1.Qxh7+!! Kxh7 2.Ng6+` tem quatro números e uma entrada só. `solucoes_da_folha`
   caminha pelos esperados em ordem crescente e só para a frente. A cauda de cada entrada é fatiada
   por `text/notacao.fatiar`, e o gabarito é a **primeira fatia de lance**: o que vem antes é o nome
   dos jogadores e o ano, e o que vem depois é variante entre parênteses. Entrada sem lance nenhum
   não entra -- e é essa condição que faz uma folha de **exercícios**, onde os mesmos números estão
   impressos sozinhos embaixo dos diagramas, não ser lida como folha de soluções. **A folha do
   próprio diagrama não responde por ele**: numa folha de capítulo o número e os lances estão os
   dois ali, e ler aquilo como lista daria o gabarito certo com a etiqueta errada.
3. **A solução decide o lado a jogar, e vence a dedução da S-17.** O diagrama não diz de quem é a
   vez; `semantics.infer_side_to_move` deduz pela legalidade e chuta brancas quando as duas são
   legais. A linha impressa é prova: `validar_solucao` joga a linha nos **dois** lados e fica com o
   que sustenta mais lances, usando o palpite anterior só como desempate. Medido no `Big Book`: dos
   24 exercícios extraídos, **10 saíram com as pretas na vez** -- dez posições em que o PGN de hoje
   diria brancas.
4. **O motor confirma, e não decide.** `confirmar` mede quanto o primeiro lance impresso perde
   contra o que o motor prefere, pela régua da S-537 (abaixo do corte de imprecisão, confirmado). A
   discordância **não apaga o gabarito** -- um livro de 1934 propõe combinações que o Stockfish
   refuta, e trocar a solução pela linha do motor seria treinar o motor e não o livro --, ela
   **marca**. E foi ela que salvou a medição de mentir: ver o critério de aceite.

**A recusa vale tanto quanto o exercício**, e é a metade que costuma sumir: `Extracao.recusas`
carrega a procedência e o motivo de cada diagrama que ficou de fora, e `por_motivo()` é o que
permite dizer **onde** o casamento falhou. Um extrator que devolve só o que deu certo não deixa
medir a própria taxa.

**Persistência atômica, um arquivo por livro** (`taticas_arquivo.py`), com a chave importada de
`estudo_arquivo.chave_de`: um livro tem uma sala e uma coleção, e as duas respondem ao mesmo nome.
JSON e não PGN -- a procedência viraria header de invenção nossa, e o que se ganharia (abrir no
ChessBase) não é o que se faz com um exercício.

**A tela** é `qt/painel_de_treino.JanelaDeTreino` (compartilhada com a S-540): a posição, o lado a
jogar, o lance cobrado, aceita ou recusa, e -- **depois** de o exercício fechar -- a solução por
extenso com o desfecho e a procedência (`Reinfeld 1001, p. 63, exercício 214`). "Dá mate" impresso
ao lado do tabuleiro antes de a pessoa jogar é meia resposta. A extração roda numa `Tarefa` com
barra e Cancelar (comando `taticas_do_livro`, "Táticas do livro"), e passa o motor da sala quando
há um.

### Critério de aceite

**Medido em 2026-09-04 sobre sete livros do acervo, o livro inteiro, `motor="camada"`, 220 dpi,
Stockfish dev-20230303 na confirmação.** O total é 1.729 folhas e 38 minutos de varredura.

| livro | folhas | diagramas | com número | com solução | o motor confirma |
|---|---|---|---|---|---|
| Schiller, *The Big Book of Combinations* (1994) | 292 | 1.005 | **963 (95,8%)** | 24 (2,4%) | **2** de 24 |
| Журавлев, *Manual of Chess Combinations 5* | 122 | 412 | 129 (31,3%) | 10 (2,4%) | **0** de 10 |
| Gaprindashvili, *Imagination in Chess* | 289 | 769 | 0 | 0 | — |
| Anand, *Great Chess Combinations* | 244 | 133 | 0 | 0 | — |
| Koblenz, *El dominio del arte de la combinación* | 70 | 120 | 13 (10,8%) | 0 | — |
| *1937 Kemeri* (torneio, para o caminho "ao lado") | 289 | 186 | 5 | 0 | — |
| Chernev, *Melhores Finais de Capablanca* (finais) | 423 | 163 | 0 | 0 | — |
| **total** | **1.729** | **2.788** | **1.110 (39,8%)** | **34 (1,2%)** | **2 (0,07%)** |

- **⚠ O aproveitamento é 0,07%, e é o resultado do item.** Trinta e quatro diagramas de 2.788
  ganharam gabarito, e o motor recusou trinta e dois deles -- com perda mediana de **7,3 peões** no
  `Big Book` e **14,2 peões** no `Manual of Chess Combinations`. Sem a confirmação, o relatório
  diria "2,4% de aproveitamento" onde há **2,4% de ruído**, e a coleção gravada ensinaria o lance
  errado. É o número honesto deste item, e ele diz que **o mecanismo está pronto e o acervo não
  está**.
- **A primeira metade funciona, e o número é alto.** ✅ Onde a folha de exercício tem camada de
  texto e o número é uma linha, o casamento geométrico acha **95,8%** (963 de 1.005). A régua da
  linha contra a do parágrafo é a diferença entre 963 e **zero** -- foi a primeira medição, e ela
  reescreveu a função.
- **A segunda metade acha as entradas e perde o lance dentro delas.** ✅/⚠ Medido isolando a lista
  de soluções (a caminhada contra os números 1 a 1.399, sem casar com diagrama): **581 entradas** em
  136 folhas do Gaprindashvili, **102** em 68 do Schiller, **62** em 28 do Zhuravlev. A caminhada
  crescente acha a entrada; o que não sobrevive é a **notação** dentro dela -- a camada de texto de
  um scan escreve `l:.d8` onde está `♖d8` e `i.xb4` onde está `♗xb4` (`text/leitor.py` documenta
  isso desde a S-178), e o que resta legível é quase só lance de peão.
- **Onde o casamento falha, ele falha dizendo o nome.** ✅ No `Big Book`, dos 963 números, 149
  acharam entrada na lista e **125 delas deram lance ilegal na posição** -- `Bxh7 não é legal nesta
  posição`, `Rxe6 não é legal nesta posição`, um a um, porque a lista de soluções daquele livro é
  uma **tabela de quatro colunas** e a ordem de leitura intercala o número de um exercício com o
  lance de outro. `text/notacao.validar` recusou cada uma pelo nome, e nenhum gabarito errado foi
  gravado. É o contrato da S-15 -- propõe, marca, não reescreve calado -- valendo aqui.
- **A solução prova o lado a jogar.** ✅ Dos 24 exercícios do `Big Book`, 10 saíram com as pretas na
  vez; dos 10 do `Manual`, 4. É informação que o PGN exportado hoje não tem.
- **Três dos seis livros não têm camada de texto nenhuma nas folhas de exercício.** ⚠ Anand,
  Gaprindashvili e (quase todo) Koblenz: o número não existe para ser achado. No Gaprindashvili
  isso é exato -- das 289 folhas, **só as 136 do fim** (a seção de soluções) têm texto.
- **O leitor de glifo foi tentado, e não resolve por outro motivo.** ⚠ Com `motor="glifo"`
  (`text/leitor.py`, 35 s por folha medidos), a folha de soluções do Gaprindashvili sai legível
  **com figurinas** (`1 d6! ♗xd6 1...♗f8 2 h6!`); mas a folha de **exercícios** dele devolve o
  número das duas colunas numa linha só -- `'7 8'`, `'1 1 1 2'` -- e `numero_junto_ao_diagrama`
  precisa da caixa do número, que a linha não separa. **O que falta é caixa por palavra em
  `LinhaLida`**, e é o item que destravaria esta medição inteira. Registrado.
- **O caminho "ao lado" não inventou um exercício sequer, e é a boa notícia da tabela.** ✅ Nos
  dois livros que **não** são de exercícios -- 349 diagramas de *Kemeri* e do *Capablanca*, onde
  cada tabuleiro tem lances impressos em volta --, `linha_ao_lado` não produziu nenhuma linha:
  `text/notacao.e_linha_de_notacao` exige **maioria** de tokens de notação no parágrafo, e prosa
  com dois lances dentro não passa. Um extrator frouxo teria devolvido trezentos "exercícios" cujo
  gabarito é o comentário do autor. Os quatro do *Kemeri* que chegaram à validação foram recusados
  pelo nome (`La4 não é um lance`, `Sf3 não é um lance`): é notação **alemã**, e `para_ingles` só
  traduz figurina -- a decisão está documentada em `text/notacao.FIGURINAS_DA_LETRA`, e ela vale
  aqui: `L` é *Läufer* em alemão e nada em inglês, e adivinhar a língua trocaria uma peça por outra
  num lance que o tabuleiro aceita.
- **A extração é cancelável e não bloqueia a janela.** ✅ `Tarefa` com `threading.Event` conferido
  entre folhas, progresso por sinal, e o que já foi lido fica.
- **Nada é gravado sem gabarito legal.** ✅ Diagrama sem FEN, sem número, sem entrada na lista ou
  com linha ilegal vira `Recusa` com o motivo, e não um exercício com solução vazia.

### Testes

- `tests/test_taticas.py` (novo, puro; 47 casos): o número como **linha** com as caixas medidas da
  folha 21 do `Big Book`; o número embaixo do diagrama; o teto de distância; a outra coluna; o
  bloco com texto junto; a corrida preenchendo o buraco e corrigindo o ano; a ausência de maioria
  não inventando nada. A lista de soluções: as três entradas com a linha de lances, **o número de
  lance de dentro da solução não abrindo entrada**, o número ausente, e a folha de exercícios não
  sendo lida como folha de soluções. A linha ao lado: o parágrafo atado (S-249), o primeiro abaixo
  na mesma coluna, e a legenda de partida que **não** é linha de lances. A validação: a solução
  provando o lado a jogar, o palpite anterior desempatando, a linha parcial valendo com o motivo
  gravado, a FEN inválida, e os três desfechos. A extração: as duas passadas, a conta fechando
  entre exercícios e recusas, a lista vencendo a linha ao lado, os dois meios-lances mínimos da
  vizinhança, e o resumo dizendo o que o motor recusou. O motor: aprovar, discordar **sem trocar o
  gabarito**, falhar sem estragar o exercício. E o arquivo: ida e volta, a chave igual à da sala de
  estudo, coleção vazia apagando, exercício corrompido não derrubando os outros, esquema do futuro,
  `carregar_tudo`, e a gravação atômica cobrada no próprio fonte.
- `tests/test_qt_painel_de_treino.py::JanelaDeTreinoTests` (novo): a posição, a procedência na tela,
  o tabuleiro virado para quem resolve, o lance certo andando a linha com a resposta jogada
  sozinha, o errado não andando e sendo desfeito no desenho, **o lance ilegal não derrubando o
  processo**, e a solução aparecendo só depois de o exercício fechar.
- `tests/test_qt_painel_de_treino.py::TaticasNaSalaTests` (novo): extrair sem livro aberto recusando
  com frase, a agenda que não abre vazia, e os dois comandos novos no "Mais" do grupo Treino.
- Guardas atualizadas: `tests/test_ui_comandos.py` (os dois rótulos que divergem do menu),
  `tests/test_busy.py::SEM_REGISTRO` (a medição da perda), `tests/test_editor_model.py::SEM_TKINTER`
  e `tests/test_ui_orfaos.py::SEM_CHAMADOR`.
- Reprodução: `scratchpad/medir_taticas.py "<livro>.pdf" --motor 40`, com `PYTHONPATH=src` a partir
  da raiz do worktree.

### O que o crítico recusou

_a preencher pelo crítico_

## S-540 · Repetição espaçada dos estudos e das táticas, com agenda do dia — ✅ **implementada em 2026-09-04**

### Problema

**Não havia agendamento nenhum, e a palavra não aparecia no programa.** `estudo_arquivo.py:104`
(`gravar`) guarda a sala de um livro para sempre, e `qt/painel_de_estudo.py:1397`
(`reabrir_por_chave`) devolve quem abre o livro à mesa em que ele parou -- as duas metades de
*"continuar de onde parei"*. Nenhuma delas responde a outra pergunta, que é a que separa uma suíte
de treino de um leitor de PDF: **o que eu deveria rever hoje?**

Sem ela, o que acontece com um acervo de centenas de livros é o que acontece com todo acervo: a
pessoa revê o que abriu por último, e o que ela aprendeu em março não volta nunca. O Chessable
inteiro é construído em cima dessa pergunta, e o Anki -- que é o programa que a resolveu -- não tem
tabuleiro.

### Solução

**A escolha do algoritmo é o item, e ela é o FSRS** (`revisao_espacada.py`). Os dois candidatos
sérios: o **SM-2** do SuperMemo, que o Anki usou por trinta anos, e o **FSRS** (*Free Spaced
Repetition Scheduler*), que entrou no Anki em 23.10 e passou a ser o recomendado depois. Três
razões, e a terceira decide **para táticas**:

1. **O SM-2 não modela esquecimento; ele multiplica.** O estado dele é um *fator de facilidade*, e
   o intervalo seguinte é `intervalo × fator`. Não existe "qual é a chance de eu ainda lembrar
   disto hoje", então não existe **retenção alvo** -- e é justamente o botão que um profissional
   quer. O FSRS tem uma curva de esquecimento explícita (`retencao`), e por isso *"quero acertar
   90% do que revejo"* é uma frase que ele responde: a `RETENCAO_ALVO` vira intervalo por inversão
   da curva.
2. **A escala de tempo do SM-2 é a repetição, não o calendário.** Ele não usa quanto tempo passou
   de verdade: dois acertos, um com um dia e outro com um ano de intervalo, mexem o fator igual. O
   FSRS come a retrievabilidade do momento (`R`) nas duas fórmulas de estabilidade, e é por isso
   que **sumir por um mês** tem tratamento nativo aqui, e não uma regra especial.
3. **O "inferno de facilidade" do SM-2 é o modo de falha das táticas.** Cada erro tira 0,2 do
   fator, o piso é 1,3, e um acerto devolve quase nada. Numa coleção de combinações -- onde errar
   é o caso normal nas primeiras voltas -- metade dos itens desce ao piso e **nunca sobe**: o
   intervalo trava em 1,3× e o baralho vira uma fila diária que não encolhe. O FSRS separa
   *dificuldade* de *estabilidade*, e o item difícil continua ganhando intervalo quando é acertado.

**O preço está escrito em voz alta: dezessete pesos que este projeto não derivou.** `PESOS` são os
padrões publicados do FSRS-4.5, copiados. A graça do FSRS é **otimizá-los** contra o histórico de
quem usa, e não há histórico nesta máquina para otimizar. É por isso que `Estado` guarda o log
inteiro de revisões (`Revisao`: dia, nota e **dias decorridos**) em vez de só a última: ele é a
entrada do otimizador do dia em que houver o que otimizar, e jogá-lo fora agora fecharia a porta.

**O que não é do algoritmo, e mesmo assim decide o dia.** O FSRS diz *quando* cada item vence; ele
não diz o que fazer quando 400 vencem juntos, que é exatamente o que acontece com quem some por um
mês. A resposta são três decisões de `Agenda`:

- **`TETO_DO_DIA` = 60.** Trezentos itens numa tela não são uma sessão de treino: são o motivo pelo
  qual as pessoas abandonam repetição espaçada. Sessenta táticas a ~40 s são ~40 min.
- **`TETO_DE_NOVOS` = 15, e menor que o outro de propósito.** Cada novo de hoje é revisão de
  amanhã; um baralho que admite cem novos por dia produz a parede acima em duas semanas. E
  **vencidos antes de novos, sempre**: aprender coisa nova enquanto o que já se aprendeu está
  sendo esquecido é o jeito de ter um baralho grande e uma memória pequena.
- **A ordem é por retenção estimada, e não por data de vencimento.** Dois itens vencidos há dez
  dias: um tinha intervalo de três dias e o outro de duzentos. O primeiro já foi esquecido; o
  segundo está praticamente intacto. Ordenar pela data trataria os dois igual e gastaria a sessão
  de hoje no que não corria risco.

**A nota sai do tabuleiro, e não de quatro botões** (`nota_do_treino`). Os quatro botões do Anki
pedem que a pessoa julgue a própria memória; num exercício de tática isso já está medido -- ou o
lance saiu, ou não saiu. Errar ou pedir a solução é `DE_NOVO`; acertar de primeira é `BOM`;
acertar depois de errar é `DIFICIL` (é acerto, com o multiplicador de penalidade `w15`). **`FACIL`
o programa nunca dá sozinho**: ele multiplica a estabilidade por `w16` e produz intervalos muito
longos, e concedê-lo a todo acerto de primeira esvaziaria a fila com base numa inferência que
ninguém fez. É o único botão de julgamento na tela.

**Persistência própria e atômica, num arquivo só para o acervo inteiro** (`revisao_arquivo.py`) --
ao contrário das táticas, que têm um arquivo por livro. A pergunta deste arquivo é *"o que eu tenho
para revisar hoje?"*, e ela é do dia e não do livro: uma sessão de segunda mistura três exercícios
do Reinfeld com dois estudos do Dvoretsky. O vínculo com o livro não se perde porque ele está
**dentro da chave** (`taticas.Procedencia.chave`). **Vazio não apaga o arquivo**, e é a diferença
para `estudo_arquivo`: aqui o vazio pode querer dizer "apaguei o histórico", e deixar o arquivo
antigo o ressuscitaria na abertura seguinte.

**A tela é `qt/painel_de_treino.JanelaDeTreino`**, aberta pelo comando `treinar_agenda` ("Revisar
hoje", no "Mais" do grupo Treino). Duas colunas -- tabuleiro à esquerda, o que se lê à direita --,
que é a repartição da sala de estudo e pela mesma razão. **A agenda é montada uma vez, na
abertura**: refazê-la a cada resposta faria o item recém-acertado sumir da fila no meio da sessão,
e a pessoa perderia a conta de quantos faltam. **O baralho vai para o disco quando a janela
fecha**, e não a cada resposta: uma gravação por item reescreveria o arquivo sessenta vezes numa
sessão, e o que se perde numa queda é uma sessão -- não o histórico.

### Critério de aceite

- **A curva de esquecimento é a de potência do FSRS-4.5, e o intervalo é a inversa dela.** ✅ A
  90% de retenção o intervalo **é** a estabilidade (`intervalo(20.0) == 20`), que é a definição
  dela; pedir 95% encurta todos os intervalos de uma vez, sem mexer no que já foi aprendido.
- **O erro nunca aumenta a estabilidade.** ✅ A trava é explícita (`min(S_lapso, S)`), e vale nos
  cinco valores de estabilidade medidos (0,2 a 30 dias) -- a fórmula de lapso do 4.5 devolve mais
  que a anterior em item muito novo.
- **O item difícil continua ganhando intervalo.** ✅ Um item em `DIFICULDADE_MAXIMA` acertado três
  vezes seguidas cresce nas três. É a propriedade que o SM-2 não tem, e a razão da escolha.
- **Sumir por um mês.** ✅ O mesmo item, acertado em dia e acertado trinta dias depois do
  vencimento, sai com estabilidade **maior** no segundo caso -- é o `1 - R` das duas fórmulas, e
  não uma regra à parte. E a volta não é uma parede: com 300 vencidos, a fila do dia tem 60 e a
  frase diz `Outros 240 ficam para amanhã`.
- **A fila é estável entre dois desenhos da tela.** ✅ Empate de retenção desfeito pela chave: uma
  fila que se embaralha é uma fila em que se perde o lugar.
- **O que já foi revisto hoje não volta hoje.** ✅ E o que vence amanhã não entra: medido pela
  ponte inteira -- o baralho que a sessão anterior gravou é o que a agenda de hoje lê.
- **Mil itens com vinte revisões cada dão 2,1 MB de JSON**, lidos em milissegundos. ✅ É o custo de
  guardar o log inteiro, e ele é o que permite otimizar os pesos um dia.
- **⚠ O que não foi medido, e é a dívida honesta deste item:** **os dezessete pesos não foram
  derivados aqui**, e não há como derivá-los sem um histórico de revisão que ainda não existe. O
  que está afirmado é que o agendamento é o do FSRS-4.5 publicado, com as propriedades acima; o que
  não está é que os pesos sejam os melhores para *este* usuário. Quem quiser calibrá-los tem o log
  gravado desde o primeiro dia.
- **Os estudos da sala ainda não entram na fila**, e é a segunda dívida: a agenda alimenta-se de
  `taticas_arquivo.carregar_tudo`, e um estudo do livro não tem `chave` de exercício. O
  agendamento é agnóstico -- ele agenda **chaves** --, então o que falta é a ponte, não o
  mecanismo. Registrado para quem retomar.

### Testes

- `tests/test_revisao_espacada.py` (novo, puro): a curva de potência e a cauda que a exponencial
  não tem; o intervalo valendo a estabilidade a 90% e encurtando a 95%; o piso de um dia e o teto
  de dez anos; a estabilidade inicial sendo o peso da nota; o erro nunca aumentando a estabilidade,
  nos cinco valores; o item difícil crescendo; a dificuldade revertendo à média sem grudar no
  mínimo; **o acerto depois de um mês valendo mais que o acerto em dia**; a parede de 300 virando
  fila de 60 com 240 adiados; a ordem por retenção contra a ordem por data; vencidos antes de
  novos; o teto de novos; nota fora da escala levantando; a tradução do treino em nota e o `FACIL`
  que o programa nunca dá; e o arquivo -- ida e volta, item corrompido não derrubando os outros,
  esquema do futuro, vazio que não ressuscita o antigo, e os 2,1 MB medidos.
- `tests/test_qt_painel_de_treino.py::JanelaDeTreinoTests` (novo): a agenda montada na abertura; o
  tabuleiro virado para quem resolve; acertar agendando `BOM` e acertar depois de errar agendando
  `DIFICIL`; ver a solução agendando `DE_NOVO`; o `FACIL` só depois de acertar e esticando o
  intervalo de verdade (**uma revisão por exercício**, e não uma por botão apertado); a fila que
  acaba; e o baralho gravado ao fechar.
- `tests/test_qt_painel_de_treino.py::TaticasNaSalaTests` (novo): a agenda que não abre vazia, a
  que abre com o que a extração gravou, e o que vence amanhã ficando de fora da fila de hoje.
- `tests/test_ui_treino_declarado.py::FrasesTests` (novo): a frase da agenda com vencidos, novos e
  **adiados** -- sem a última, quem volta depois de um mês conclui que o programa perdeu 340 itens.

### O que o crítico recusou

_a preencher pelo crítico_

## S-541 · "Adivinhe o lance" com placar persistente e comparação com o motor — ✅ **implementada em 2026-09-04**

### Problema

O modo existia desde a S-290 e cabia em três métodos. `qt/painel_de_estudo.py:2581`
(`alternar_treino`) escondia a continuação e zerava dois inteiros; `:2603` (`_treinar`) comparava o
lance com `self.estudo.no.variations[0]` e somava um a `_acertos` ou a `_erros`; `:2597`
(`_mostrar_placar`) escrevia `treino: 3 certo(s), 1 errado(s)`.

**Três coisas faltavam, e as três aparecem na primeira sessão de verdade.**

1. **O placar morria ao desligar o treino** -- e desligar o treino é o gesto que a própria frase de
   erro declara ("Desligue o treino para guardá-lo como variante"). Meia hora de exercício não
   deixava rastro nenhum: nada no disco, nada por livro, nada entre sessões.
2. **Todo lance que não fosse o da linha era erro.** Treinando sobre uma partida de torneio, isso
   classifica como erro toda transposição e todo lance de igual valor -- o placar passa a medir a
   memória daquela partida em vez do xadrez de quem treina. O motor estava ali ao lado, e ninguém
   perguntava nada a ele.
3. **O lance errado ficava na tela.** `_treinar` não redesenhava no caminho de erro: o modelo do
   widget joga sobre a própria cópia (`BoardModel`), a árvore não muda -- e a pessoa fica olhando
   uma posição que o estudo não tem, com o lance seguinte partindo dela.

### Solução

**Três baldes e não dois** (`placar.py`, `ui/treino_declarado.classificar_o_lance`): *certo*, o
lance do gabarito; *equivalente*, um lance diferente que o motor considera igualmente bom; e
*errado*. Sem o balde do meio, o defeito 2 permanece.

**A régua do "igualmente bom" é `analise_da_partida.julgar`, inteira, e não um número novo.** Ela
recebe as **duas avaliações** -- antes e depois do lance -- e devolve a perda em centipeões e o
juízo; quando ela cala, o lance é `EQUIVALENTE`, e quando ela fala ele é `ERRADO` com o símbolo
(`?!`, `?`, `??`) e a perda em peões na frase. Passar as duas em vez de um número de perda pronto é
o que faz o treino herdar as duas regras que a S-537 mediu -- o teto de dez peões e a **posição já
decidida**: um lance que cai de +18 para +9 não é erro nenhum, e um corte escrito aqui não saberia
disso. **E foi o que salvou este item de uma quebra silenciosa**: a S-537 trocou a escala do juízo
de centipeões para pontos percentuais de expectativa de vitória enquanto este era escrito, e o
treino acompanhou sem uma linha de mudança, porque a régua é uma só.

**O lance do gabarito é certo mesmo quando o motor discorda dele**, e a ordem é a decisão: quem
treina o `1001 Sacrifices` está aprendendo a combinação de Reinfeld, e um Stockfish que prefere
outra coisa não torna errado o lance que o livro pede. A discordância do motor com o **gabarito** é
assunto da extração (`taticas.confirmar`, S-539), e não do lance de quem treina.

**O veredicto chega na hora e o preço chega depois** (`qt/painel_de_treino.PerdaDoLance`). Saber se
o lance é o da linha não custa nada; saber quanto ele perdeu custa duas buscas do motor, e elas não
cabem na linha de eventos. A frase do rodapé é escrita **duas vezes**: primeiro *"d4 não é o lance
da linha: perguntando ao motor quanto custou…"*, depois *"d4? — erro: perde 1,40 contra e4"*. Sem
motor a primeira é a única, e ela continua sendo verdade -- `frase_do_resultado` não promete número
que não existe.

**A avaliação de "antes" é guardada por posição.** Errar três vezes no mesmo exercício não pode
custar seis buscas: a posição antes do lance é a mesma nas três. E um segundo pedido durante o
primeiro é **recusado** em vez de enfileirado -- quem erra três lances em dois segundos quer a nota
do último, não três atrasadas.

**Duas escalas de placar, e as duas fazem falta por razões diferentes** (`placar.py`). A **sessão**
responde *como estou hoje* e é o que muda a decisão de continuar ou parar; ela não é gravada,
porque uma sessão que sobrevive ao fechamento do programa não é uma sessão. O **livro** responde
*como estou neste material*, e é ela que dá sentido a um acervo de centenas de livros -- `79% em
268 lances no Big Book of Combinations` é a frase que diz qual livro reabrir. Essa é gravada, **a
cada lance**: o arquivo tem uma linha por livro e alguns bytes, e o que se perde numa queda é
justamente a sessão que ninguém vai repetir. (É a decisão inversa à do baralho de revisão, e a
diferença é o tamanho do que se grava.)

**A perda é somada e não promediada no arquivo**: a média de duas sessões não é a média das médias,
e recalculá-la a partir da soma é a única forma de o número continuar certo depois de somar o
placar de hoje ao de ontem.

**E o lance errado é desfeito na tela**, na sala e na janela de treino -- uma linha em cada, e é o
defeito 3.

### Critério de aceite

- **O placar do livro sobrevive a desligar o treino.** ✅ Medido no painel: um acerto, desligar,
  ligar de novo -- a sessão zera e o livro continua com 1. E o arquivo já está no disco depois do
  **primeiro** lance.
- **Três baldes, com a régua da S-537.** ✅ O ponto em que o balde do meio vira erro é **procurado**
  no próprio teste, chamando `julgar` até ela falar, e não escrito de novo: quando a S-537 trocou de
  escala no meio deste item, os testes acompanharam sozinhos. E a **posição já decidida** vale aqui
  também: `antes=+18, depois=+9` sai como `EQUIVALENTE`, e não como erro grave.
- **A comparação com o motor volta por sinal, e o veredicto não espera por ela.** ✅ Contra um
  processo UCI de verdade (`tests/fake_uci_engine.py`): a frase de "perguntando ao motor" aparece
  na hora e a nota chega depois; a avaliação de "antes" é reusada na segunda tentativa (medido
  pelo tamanho do cache, não pelo relógio); e um segundo pedido durante o primeiro é recusado.
- **Sem motor, nada quebra e nada é prometido.** ✅ `pedir` devolve falso, o lance é contado na
  hora, e a frase não traz número.
- **O lance errado não fica na tela.** ✅ Na janela de treino, a FEN do widget volta a ser a do
  exercício depois de um erro.
- **O lance ilegal não derruba o processo.** ✅ Achado ao escrever a fotografia: `chess.Board.san`
  devolve `Nf3` para um lance ilegal quando há peça na origem, e **levanta** quando não há -- e uma
  exceção num slot do Qt mata o processo sem mensagem. `jogar` confere a legalidade antes de tudo.
- **A frase do placar cabe na linha.** ✅ Ela mostrava o caminho inteiro do PDF (80 caracteres) e
  empurrava o número para fora da janela; passa a mostrar `taticas.nome_curto`, que é o mesmo corte
  de `Procedencia.frase`.
- **O que ficou de fora:** o placar não separa por **tema** de tática nem por dificuldade (o
  Chessable e o CT-ART fazem), porque nada no acervo etiqueta tema -- seria inventar uma coluna que
  ninguém preenche. E a comparação com o motor **não** grava `[%eval]` no estudo: o treino não é
  edição da árvore, e é a regra da S-290 mantida.

### Testes

- `tests/test_ui_treino_declarado.py` (novo, puro): os três baldes; o corte lido da S-537 nos dois
  lados; o lance do gabarito sendo certo **mesmo com o motor discordando**; sem motor não haver
  balde do meio; o símbolo e o juízo vindo da tabela da S-537; as quatro frases do rodapé; o placar
  vazio que não escreve nada; as duas escalas na mesma linha; e o placar -- zerar a sessão sem
  zerar o livro, o equivalente contando como bom, a posição sem livro contando só na sessão,
  resultado desconhecido levantando, o total somando os livros, e o arquivo (ida e volta, ausente,
  esquema do futuro, JSON quebrado).
- `tests/test_qt_painel_de_treino.py::PerdaDoLanceTests` (novo): sem motor o pedido é recusado; a
  perda volta por sinal e a avaliação de antes é reusada; um segundo pedido durante o primeiro é
  recusado.
- `tests/test_qt_painel_de_treino.py::TreinoNaSalaTests` (novo): o placar do livro sobrevivendo a
  desligar o treino; o arquivo no disco depois do lance; a frase sem motor que não promete número;
  a frase escrita duas vezes com motor; o lance da linha andando; e o fim da linha não cobrando
  lance.
- `tests/test_qt_painel_de_estudo.py::test_o_treino_esconde_a_continuacao_e_nao_muda_a_arvore`
  (ajustado): o placar deixou de contar "errado" e passou a contar `bons de total`.

### O que o crítico recusou

_a preencher pelo crítico_

## S-542 · Exportar estudo e texto para EPUB, com diagramas como SVG — ✅ **implementada em 2026-09-04** (segunda rodada)

### Problema

O editor de materiais converte livro digitalizado em texto corrigido, e a saída parava em quatro
formatos de página solta: `text/exportacao.py:552` (`formato_de`) conhece `.txt`, `.md`, `.html` e
`.rtf`, e nenhum deles é um **livro** -- não tem capítulo, índice nem reflui em tela de 6 polegadas.
O estudo saía pior: `estudo_saida.py:93` (`para_documento`) o devolve como um título, um diagrama e
**uma linha só** com a análise inteira dentro, porque é o que a aba de texto recebe; a variante
recuada, o comentário que corta a linha e o diagrama pedido pelo autor (`[%D]` do ChessBase) não
existiam em saída nenhuma. E o diagrama, quando saía, era o recorte PNG da página
(`exportacao.py:384`): serrilhado no leitor grande, pesado no pequeno, e ausente quando o estudo
veio de um PGN colado, que não tem recorte.

**O que a primeira rodada deixou passar** (e que um editor de xadrez recusa na primeira página): a
linha impressa era a do widget, não a do livro -- `1. Kf2 !` e `( 1... Kf5 ?! 2. Kd4 ⩲ )`; a FEN
saía impressa sob todo diagrama; um PGN sem âncora produzia um sumário com 300 entradas escritas
`Estudo avulso`; o ponto de "as pretas jogam" era `#1f1d1b` sobre moldura `#1f1d1b`, razão **1,0:1**;
e as coordenadas, **2,51:1**. Ver `### O que o crítico recusou`.

### Solução

**Três módulos puros, e nada de biblioteca nova.** `estudo_paragrafos.py` é **a decisão de
paginação**: o estudo vira uma lista de `Paragrafo` (título, diagrama, comentário, lance, variante
com nível), a partir de `ui/estudo_lista.trechos` -- a travessia já conferida contra o `chess.pgn`.
Regras: a variante de primeiro nível vira parágrafo recuado **sem parênteses**; as mais fundas ficam
dentro dela entre parênteses; o comentário da linha principal corta a linha e vira prosa, o da
variante fica dentro; `[%D]` no comentário pede um diagrama **depois** dele com a posição daquele
lance, e o da raiz sai sempre como número 1; `*` não sai. EPUB e DOCX leem **a mesma lista**, e é
isso que os impede de discordar sobre onde a variante começa.

**A tipografia do lance é decidida ali, e é a do livro.** `trechos` é tokenizador de lista clicável:
termina todo trecho em espaço para dois itens não se encostarem na tela. O `_Montador` cola pelo
papel do trecho -- `NUMERO` e `ABRE` colam o próximo, `NAG` e `FECHA` colam no anterior --, e a
mesma linha que a lista desenha `1. Kg7 ! ... ( 1. c7 ? Kb7 ∓ ... )` sai impressa `1.Kg7!` e
`(1.c7? Kb7∓ ...)`. Decidir isso no exportador daria duas tipografias para a mesma partida.

**O título do capítulo tem três origens, nessa ordem**: a âncora no livro (`Secrets.pdf · p. 143 ·
diagrama 2`), o cabeçalho da partida (`Carlsen, M. × Nepomniachtchi, I., Tata Steel, 2021.01.16`,
com o que houver de `White`/`Black`/`Event`/`Date`, e `1921.??.??` valendo `1921`) e, sem jogador
nenhum, `Estudo avulso`. Sem jogador porque `Estudo.de_posicao` grava `Event = "ChessVisionOFF
Estudo"` em toda posição criada aqui dentro. `estudo_saida.para_documento` chama a mesma função:
dois títulos para o mesmo estudo seria o EPUB discordando do `.md`.

`diagrama_svg.py` desenha a posição como SVG a partir da FEN ou do `placement`. **As peças são os
caminhos de `chess.svg.PIECES`** (conjunto Cburnett), que o `python-chess` -- dependência obrigatória
desde a primeira versão -- embute; `assets/piece_images/` são PNG de 70 px, não servem a vetor, e uma
fonte de xadrez por `@font-face` mostra letras no leitor que não a carregar. Um `<g id>` por tipo de
peça **presente** em `<defs>`, um `<use>` por peça; casa de 45 unidades (o quadro dos caminhos), 64
`rect` com `data-casa`; réguas opcionais **na ordem de `ui/desenho_do_tabuleiro.reguas`**; tamanho em
`em` (`18em` padrão) para refluir com o texto -- ou em `cm`, com declaração `<?xml?>`, quando o
destino é o `.docx`, onde o arquivo é uma parte solta do pacote. Cores de `ui/tokens.py`, nenhum
hexadecimal no arquivo. Posição vazia ou ilegível é `PosicaoInvalida`, uma `ValueError` **em pt-BR**
com o texto do `python-chess` entre parênteses, como manda `cli/__init__.message_for`.

**O lado a jogar é uma plaqueta, e ela é lida.** Um quadrado de `CASA_CLARA` na margem direita com o
círculo dentro: cheio (`GLIFO_ESCURO`) para as pretas, vazado (`GLIFO_CLARO` com contorno escuro)
para as brancas -- que é como uma peça branca é desenhada. Fica **do lado em que aquele jogador está
sentado**, e desce com `virado`. A régua sai de `tokens.sobre_superficie(moldura)`, o instrumento da
S-146: a superfície da coordenada do diagrama é a moldura escura, não o fundo do painel.

`epub.py` empacota com `zipfile`: `mimetype` **primeiro e armazenado**, `META-INF/container.xml`,
`OEBPS/content.opf` (EPUB 3.0), `nav.xhtml` com sumário **e marcos**, um XHTML por capítulo,
`estilo.css`, `imagens/`. Metadados: `dc:identifier` `urn:uuid` gerado, `dc:title`, `dc:language`,
`dcterms:modified`, e o que uma loja pede quando vem preenchido -- `dc:date`, `dc:publisher`,
`dc:rights`, o ISBN como segundo `dc:identifier` e a capa como `cover-image`. **`dc:creator` só sai
quando alguém diz quem é o autor**: o programa entra em `dc:contributor` com o papel `bkp` (*book
producer*) do vocabulário MARC, porque o livro é de quem o compilou. Os cinco campos da EPUB
Accessibility 1.1 -- `accessMode`, `accessModeSufficient`, `accessibilityFeature`,
`accessibilityHazard`, `accessibilitySummary` -- saem sempre: sem eles o arquivo é recusado na
ingestão das lojas europeias desde 06/2025 (European Accessibility Act). E `accessModeSufficient:
textual` é uma promessa que se cumpre no `alt`: **`Diagrama 3. As pretas jogam. FEN: ...`**, e não
`Diagrama 3`, que para um leitor de tela é o mesmo que imagem sem alternativa.

`exportar_estudo_epub(estudo, caminho, metadados, com_fen=False)` e `exportar_estudos_epub`;
`exportar_texto_epub(documento, caminho, metadados, imagens=, cores=, corpos=)` e
`exportar_textos_epub`. **A legenda com a FEN é opcional e vem desligada** -- nenhum livro comercial
a imprime; ela é encanamento, e quem a quer é quem vai reconferir a leitura do OCR. No texto, a
formatação inline **é a de `exportacao.Html.corrida`** -- não uma cópia -- e a folha de estilo traz
as mesmas regras por `Html.regras_de_css()`; o que o EPUB acrescenta é `<p>` no lugar de `<br>`, o
primeiro título da folha em `<h1>` e os seguintes em `<h2>` (hierarquia que começa no segundo nível
não tem primeiro), e a figura em arquivo separado no manifesto. O diagrama do texto sai em SVG
quando o bloco tem `placement`, no PNG injetado quando não tem, e como `<p class="marca">[Diagrama
N]</p>` quando não há nem um nem outro -- **a marca nunca desaparece** (S-250) e o `Relatorio` conta
os três casos. `verificar` faz a conferência que o `epubcheck` faria, **nos dois sentidos**:
manifesto → zip e zip → manifesto (um arquivo fora do manifesto é um arquivo que o leitor não abre).

**Fiação pendente (fora deste item):** as ações "Exportar EPUB…" e "Exportar DOCX…" no
`EXPORTAR ▾` de `ui/barra_da_sala.py` e no menu do editor de texto, com o diálogo de arquivo. Os
arquivos são de outro executor nesta rodada; o chamador é uma linha por formato.

### Critério de aceite

- Todo arquivo do zip é XML bem formado, o `mimetype` é o primeiro membro e vai sem compressão,
  toda referência do OPF existe no zip **e todo membro do zip está no OPF**, todo `idref` da espinha
  está no manifesto. ✅ Afirmado nos testes com `zipfile`/`ElementTree` diretamente **e** por
  `verificar`, provado contra quatro defeitos fabricados (mimetype comprimido, imagem prometida e
  ausente, XHTML mal formado, arquivo órfão no zip).
- **`epubcheck` 4.2.6 (`java -jar`, fora do `.venv`): 0 erros e 0 advertências** em `um.epub`,
  `texto.epub`, `hostil.epub`, `d300.epub`, `catalogo.epub` (com autor, data, editora, direitos,
  ISBN e capa) e no `aagaard.epub` de 2.618 capítulos (20,8 s de validação).
- Tipografia: a linha de um estudo conhecido sai **exatamente** `1.Kg7!` / `(1.c7? Kb7∓ as pretas
  ganham (1...Kb6 2.Kg7))` / `1...h4?! 2.Kf6⩲`. ✅ Afirmado como string inteira, e não por `assertIn`.
- Contraste sobre a moldura, medido por `tokens.razao_de_contraste`: régua **13,71:1** (era 2,51:1),
  plaqueta do lado a jogar **12,24:1**, círculo cheio das pretas **13,76:1** sobre a plaqueta (era
  **1,0:1**, invisível). Piso: 4,5:1.
- SVG: 64 casas nomeadas, peça na casa certa, virado espelha peça e casa juntas, réguas na ordem de
  `reguas`, plaqueta do lado a jogar **do lado de quem joga**, `em` no EPUB e `cm`+declaração no
  DOCX. ✅ 21.139 bytes a posição inicial.
- Sumário: `d300.epub` (300 estudos de `10k_studies.pgn`, nenhum com âncora) tem **300 entradas, 201
  distintas** -- `Sifers, Samouc. sahm. igri`, `Drtina, Cas. cesky sah., 1908`. Antes: 300 entradas,
  **1 distinta** (`Estudo avulso`). O `aagaard.epub` tem 2.618 entradas, 2.618 distintas.
- Medido em 2026-09-04 (rodada 2): `PGN/A Matter of Endgame Technique – Jacob Aagaard.pgn` (901 KB,
  **2.618 estudos**) → EPUB de **7.787 KB**, 2.618 capítulos, 2.618 SVG, **3,53 s**, `verificar`
  vazio. Um estudo: 6 KB, 10 ms. `pgn_database/10k_studies.pgn` (300 primeiros): 2.997 parágrafos
  (1.245 lances, 1.147 variantes de nível 1, 5 comentários) → 759 KB, 0,60 s. Texto: `DocumentoRico`
  sintético → 4 KB, 3 diagramas (1 SVG, 1 PNG injetado, 1 só com a marca) e o aviso correspondente.
- Sem dependência nova: `pyproject.toml` inalterado, nenhum extra. ✅

### Testes

- `tests/test_diagrama_svg.py`: bem formado e `viewBox`; tamanho em `em`; FEN no atributo e no
  título; posição vazia é erro; 64 casas por nome; a1 escura e h1 clara de qualquer lado; a1 no
  canto certo normal e virado; 32 peças na casa certa, `translate` do rei; virado espelha peça e
  casa juntas; `use` aponta `g` definido; só presentes em `defs`; `placement` desenha igual à FEN;
  réguas nas duas ordens e ausentes sem margem; plaqueta em cima/embaixo/ausente/imposta; nenhum
  hexadecimal no módulo; cores iguais à reserva de `tokens`. **Novos:** régua e plaqueta acima de
  4,5:1 sobre a moldura e o desenho usando essas tintas; a marca desce com `virado` nas quatro
  combinações; SVG de arquivo com declaração e em `cm`, e o do EPUB sem declaração e em `em`; FEN
  ilegível levanta `PosicaoInvalida` em pt-BR com o texto do `python-chess` junto; `alt` descreve a
  posição e vira o `<title>` do SVG.
- `tests/test_estudo_paragrafos.py`: ordem título → diagrama; título igual ao de `estudo_saida`;
  diagrama 1 com a FEN da raiz e `virado` do estudo; comentário da raiz como parágrafo; comentário
  da principal corta a linha; a linha que continua traz o número; variante recuada sem parênteses;
  comentário da variante fica dentro; subvariante entre parênteses; sem espaço duplo; `[%D]` pede o
  diagrama 2 com a FEN do lance e não vaza como texto; `*` não sai e `1-0` sai; estudo sem lance.
  **Novos:** `TipografiaTests` -- a lista de parágrafos de um estudo de Réti conferida inteira,
  string a string, e nenhuma das seis folgas do widget (` !`, ` ?`, ` ⩲`, ` ∓`, `( `, ` )`) nem
  `\d+\.\s` sobrevivendo; `TituloTests` -- cabeçalho da partida, data incompleta, dois jogadores,
  sem jogador é avulso, âncora ganha do cabeçalho; `MarcaDeDiagramaTests` -- `[%Depth 20]` não pede
  diagrama e `[%D]` continua pedindo.
- `tests/test_epub.py`: mimetype primeiro e armazenado (também pelos bytes 30–38); todo XML bem
  formado; toda referência do manifesto no zip; container → OPF → `dc:` obrigatórios; espinha e nav
  com dois capítulos; `verificar` aprova o que sai e pega os defeitos fabricados; capítulo do
  estudo com `h1`, figura, `p.lance`, `p.comentario`, `p.variante.nivel-1` e escape; `[%D]` vira
  segunda figura com SVG bem formado; relatório e `dc:title` do estudo; texto em `<p>` sem `<br>`;
  `<strong>` e `cor-nota` com a regra na folha; título abre o capítulo ou o nome da folha entra como
  `h1`; SVG/PNG injetado/marca e a contagem dos três; `Metadados` gera `urn:uuid` e data e respeita
  o que veio de fora; os três estilos de livro na folha. **Novos:** `AcessibilidadeTests` -- os cinco
  campos, o resumo em pt-BR, todo `alt` com a FEN no formato `Diagrama N. As … jogam. FEN: …`, o
  capítulo abrindo em `<h1>`, o `nav` de marcos; `CatalogoTests` -- o programa não é `dc:creator` e
  sim `dc:contributor`/`bkp`, o catálogo (autor, data, editora, direitos, ISBN) e a capa opcional;
  `SumarioDoLivroTests` -- dois PGN sem âncora dão dois nomes distintos no sumário;
  `VerificadorNosDoisSentidosTests` -- o arquivo órfão no zip é acusado, e o que o OCF define não é
  órfão. A legenda da FEN virou `test_a_fen_nao_e_impressa_sob_o_diagrama_e_a_legenda_e_opcional`.

### O que o crítico recusou

Rodada 1 (2026-09-04), crítico no papel de editor profissional de material de xadrez (ABBYY
FineReader, Sigil/Calibre, Word). Ele aprovou o encanamento -- `epubcheck` 0/0, SVG conferido casa a
casa, par PNG+SVG do DOCX montado como o Word grava -- e **reprovou a tipografia**. Os seis
bloqueios e o que mudou:

| # | o que ele achou | onde estava | o que mudou |
|---|---|---|---|
| 1 | `1. Kf2 !` -- espaço antes de todo NAG | `estudo_paragrafos._Montador.fechar` normalizava com `" ".join(...split())` sobre tokens de widget | `lance()` recebe o `papel` do trecho e cola por regra; `NAG` e `FECHA` colam no anterior, `NUMERO` e `ABRE` colam o próximo |
| 2 | `( 1... Kf5 ?! 2. Kd4 ⩲ )` -- folga dentro do parêntese, e `1. Kf2` no lugar de `1.Kf2` | idem | idem -- sai `(1...Kf5?! 2.Kd4⩲)` e `1.Kf2` |
| 3 | `FEN: …` impressa sob todo diagrama | `epub.capitulo_do_estudo` passava `legenda=` sempre | `com_fen=False` por padrão nas quatro entradas; a posição fica no `alt`, no `<title>` do SVG e em `data-fen` |
| 4 | sumário com 300 × `Estudo avulso` | `titulo_do_estudo` só conhecia a âncora | cai para `White × Black, Event, Date`; 201 nomes distintos em 300 estudos |
| 6 | ponto de "pretas jogam" invisível, **1,0:1** | `_ponto_do_lado` pintava com `paleta.moldura` sobre a moldura | plaqueta `CASA_CLARA` + círculo `GLIFO_ESCURO`/`GLIFO_CLARO`: 12,24:1 e 13,76:1 |

E os "deveria" que couberam nesta seção: a plaqueta acompanha `virado`; a régua saiu de 2,51:1 para
13,71:1 por `tokens.sobre_superficie`; o capítulo de texto abre em `<h1>`; `MARCA_DE_DIAGRAMA` passou
a casar `[%D]` inteiro (`[%Depth 20]` do Fritz pedia um diagrama por lance analisado); os cinco
campos de acessibilidade e os metadados de catálogo entraram, com `dc:creator` deixando de ser
"ChessVisionOFF"; `verificar` passou a conferir zip → manifesto; a regra vazia `p.comentario { }`
virou espaçamento de prosa; e a FEN ilegível levanta erro em pt-BR.

**O que não mudou, e por quê.** O `nav.xhtml` continua **fora da espinha**: o EPUB 3 não a exige, os
leitores mostram o sumário pela própria interface, e pô-la lá faria a conferência do crítico
(`conferir_pacotes.py`, "a ordem da espinha não é a dos capítulos do manifesto") apontar defeito onde
não há. Os marcos (`landmarks`) entraram, que era a outra metade daquela observação.

## S-543 · Exportar para DOCX — ✅ **implementada em 2026-09-04** (segunda rodada)

### Problema

O mesmo de S-542 pelo lado de quem edita em Word: `text/exportacao.py:552` não tem `.docx`, e o
`.rtf` (`exportacao.py:411`) é o que se oferecia para abrir num processador de texto -- sem estilo
nomeado, sem imagem vetorial, e com o diagrama como recorte da página ou nada. `python -c "import
docx"` falha no `.venv`: não há `python-docx`, e instalá-lo seria o extra que a máquina do editor
não tem.

**O que a primeira rodada deixou passar.** O estilo de título se chamava `Título` -- com acento, sem
número -- e nenhum programa reconhece isso como título: o Calibre relatava *"Auto generated TOC with
0 entries"* sobre um `.docx` com 2.618 títulos, e o painel de navegação do Word ficava vazio. Faltava
também o índice, a numeração de página, o cabeçalho e o rodapé; o SVG embutido ia sem declaração
`<?xml?>` e medido em `em`; e a FEN saía impressa sob todo diagrama. Ver `### O que o crítico
recusou`.

### Solução

**`docx_saida.py` escreve OOXML mínimo com `zipfile`**, sem dependência nova: `[Content_Types].xml`,
`_rels/.rels`, `docProps/core.xml` e `docProps/app.xml`, `word/document.xml`, `word/styles.xml`,
`word/settings.xml`, `word/header1.xml`, `word/footer1.xml`, `word/_rels/document.xml.rels`,
`word/media/`. Mesmas entradas do EPUB: `exportar_estudo_docx`/`exportar_estudos_docx` (quebra de
página entre estudos) e `exportar_texto_docx`/`exportar_textos_docx` (`imagens=`, `cores=`,
`corpos=`), todas com `com_fen=False`.

**Estilos nomeados**, `ESTILOS`: `heading 1` e `heading 2` (`styleId` `Heading1`/`Heading2`,
`outlineLvl`, `next=Normal`, `uiPriority 9`), `Lance` (negrito), `Variante` (itálico, recuo 720
twips) e `Variante 2` (1.440), `Comentário`, `Legenda` (Consolas 8 pt, centrada, para a FEN),
`Diagrama` (centrado, `keepNext`) e `Marca de diagrama`. **O `w:name`, e não o `styleId`, é o que
faz um parágrafo virar título**: é sempre o nome inglês da especificação, e o Word é quem o mostra
localizado ("Título 1") na galeria. O Calibre casa `heading\s+(\d+)$` sobre ele; o campo `TOC` e o
painel de navegação fazem o mesmo. São os mesmos papéis do CSS do EPUB, lidos da mesma lista de
`estudo_paragrafos`, e no texto do livro o primeiro título da folha é `Heading1` e os seguintes
`Heading2`, como lá.

**O documento é um documento**: campo `TOC \o "1-3" \h \z \u` na primeira página (quando há mais de
um estudo -- um sumário de uma linha é uma página a mais para dizer o que a primeira já diz),
`word/settings.xml` com `updateFields` para o Word se oferecer para montá-lo ao abrir, cabeçalho com
o título do livro e rodapé com o campo `PAGE`. As referências de cabeçalho e rodapé **abrem** o
`sectPr`: a ordem dos filhos é imposta pelo esquema, e um `headerReference` depois do `pgSz` faz o
Word recusar o arquivo como ilegível.

**O diagrama vai em par: PNG no `a:blip` e SVG na extensão `asvg:svgBlip`.** Foi a decisão pedida.
O PNG é o que todo leitor de `.docx` desenha (LibreOffice, Google Docs, Word antigo, celular); o SVG
é o que o Word 2016+ prefere e imprime como vetor. É o par que o próprio Word grava ao colar um SVG;
só SVG abre em branco fora do Word novo, só PNG serrilha no papel. **O SVG do pacote é um arquivo**,
não um elemento de XHTML: leva declaração `<?xml?>` e mede em `cm` (`18em` num arquivo solto não tem
corpo de texto a que se referir). O PNG vem de **`diagrama_png.py`**, módulo puro: PIL (dependência
obrigatória) compõe as casas e cola os doze PNGs de `assets/piece_images/` a 70 px por casa
(`BUNDLE_ROOT`, como `qt/tabuleiro.py:57`), réguas e plaqueta do lado a jogar com a mesma geometria e
as mesmas cores do SVG -- inclusive o canto em que a plaqueta cai quando `virado`, ou o Word e o
LibreOffice mostrariam diagramas diferentes do mesmo arquivo. Peça ausente vira letra e um aviso no
log. Sai em paleta de 64 cores: 55 KB em RGB → 20 KB. O teste roda **sem Qt**. Para o diagrama do
texto sem `placement`, o PNG é o recorte injetado (`imagens=`), sem SVG; sem nada, sai a marca.

**Autoria**: `dc:creator` só sai quando alguém diz quem é o autor; o programa vai em
`cp:lastModifiedBy` e em `docProps/app.xml` como `Application`. O `descr` do desenho é a descrição
com a FEN, a mesma do `alt` do EPUB. `verificar`: zip, XML bem formado em toda parte, todo membro com
tipo de conteúdo, toda relação apontando membro existente, todo `r:embed` do documento com relação.

### Critério de aceite

- As partes obrigatórias no zip; todo XML bem formado; toda parte com tipo de conteúdo (inclusive
  `settings.xml`, `header1.xml`, `footer1.xml` e `app.xml`); todo `r:embed` com relação e toda
  relação com parte. ✅ Afirmado direto e por `verificar`, provado contra três defeitos fabricados.
- **O TOC deixou de ser "0 entries".** `ebook-convert` do Calibre (`C:\Program Files\Calibre2`) sobre
  `d300.docx`: *"Generating Table of Contents from headings"*, e o EPUB resultante tem **301 entradas**
  (o sumário e os 300 estudos, nomeados `Sifers, Samouc. sahm. igri`, `Drtina, Cas. cesky sah., 1908`
  …). Rodada 1, no mesmo arquivo: *"Auto generated TOC with 0 entries"*.
- **LibreOffice abre e pagina**: `soffice --headless --convert-to pdf` sobre `um.docx` produz uma
  página com o cabeçalho corrido (título do livro), o número de página no rodapé, o título em
  `Heading1` e o diagrama desenhado **como vetor** (o SVG; `get_images()` = 0, 154 desenhos).
- Estilos `heading 1`/`heading 2`, `Normal`, `Lance` (negrito), `Variante` (itálico recuado),
  `Comentário`, `Legenda` existem e cada parágrafo do estudo sai com o seu; diagrama com PNG no blip
  e SVG na extensão, ambos no `media/`; largura pedida em EMU (`7,6 cm` padrão = os `18em` do EPUB a
  12 pt). ✅
- Medido em 2026-09-04 (rodada 2): um estudo do Aagaard → **21 KB, 40 ms**; os **2.618** →
  **32.855 KB, 44,7 s**, `verificar` vazio. 300 estudos anotados do `10k_studies.pgn` → 2.999
  parágrafos, 2.485 KB, 4,8 s. Texto sintético → 10 KB, 7 parágrafos, 3 diagramas (1 par PNG+SVG,
  1 PNG injetado, 1 marca), 1 aviso.
- Sem `python-docx` e sem extra novo: `pyproject.toml` inalterado. ✅

### Testes

- `tests/test_diagrama_png.py`: assinatura PNG e tamanho 616×616; abaixo de 30 KB; sem réguas nem
  lado não há margem; casa vazia com a cor da paleta; casa com peça sem ela; a1 no canto superior
  direito quando virado e h1 clara; a peça virada acompanha a casa; pasta sem peças desenha letra e
  avisa; a pasta padrão é a do bundle. **Novos:** `PlaquetaTests` -- o pixel do ponto das pretas é
  `GLIFO_ESCURO` sobre plaqueta clara e **não** a cor da moldura; o das brancas é claro sobre a mesma
  plaqueta; a marca desce com `virado`; a régua do PNG usa a mesma tinta medida do SVG.
- `tests/test_docx_saida.py`: partes obrigatórias; todo XML bem formado; raiz → documento e tipos de
  conteúdo; `r:embed` ↔ relação ↔ parte (quatro num estudo com `[%D]`); `verificar` aprova e pega
  três defeitos; estilos com o traço prometido e nomes com acento; cada parágrafo do estudo com o
  estilo do tipo; PNG no blip e SVG bem formado na extensão; `extent` em EMU; relatório e
  `core.xml`; quebra de página entre estudos; texto cortado na quebra de linha com `Heading1`;
  formatação inline com cor/realce/corpo resolvidos de fora e nada quando não vêm; par PNG+SVG /
  marca e contagem; PNG injetado sem SVG; `run` escapa; `_meios_pontos`; `_hex`; nenhum hexadecimal.
  **Novos:** `EstruturaDoWordTests` -- o `w:name` é `heading 1`/`heading 2` e casa a expressão do
  Calibre, o campo `TOC` e o `updateFields` estão lá, cabeçalho e rodapé existem com o campo `PAGE`
  e são as duas primeiras referências do `sectPr`, as partes novas têm tipo de conteúdo declarado, e
  o programa não assina como autor; `SvgEmbutidoTests` -- o SVG do pacote começa em `<?xml ` e mede
  em `cm`, e o `descr` do desenho traz a FEN; `LegendaOpcionalTests` -- a FEN não sai por padrão e
  sai com `com_fen=True`.

### O que o crítico recusou

Rodada 1 (2026-09-04). Ele aprovou o par PNG+SVG -- "montado como o Word grava", `svgBlip` dentro do
`a:blip`, URI da extensão certa, zero formatação direta no corpo -- e reprovou o resto:

| # | o que ele achou | onde estava | o que mudou |
|---|---|---|---|
| 5 | `Título` do DOCX não é heading: o Calibre lê "Auto generated TOC with 0 entries" | `ESTILOS[TITULO] = ("Título", …)`, `styleId="Titulo"` | `styleId="Heading1"` com `w:name="heading 1"`, e `Heading2` para o subtítulo; 301 entradas na conversão |
| 3 | `FEN: …` impressa sob todo diagrama | `_estudo` passava `legenda=` sempre | `com_fen=False` por padrão; a FEN fica no `descr` do desenho e no `<title>` do SVG |
| — | sem campo `TOC`, sem numeração de página, sem cabeçalho nem rodapé | `_documento_xml` tinha só `pgSz`/`pgMar` | `Documento.sumario()`, `word/header1.xml`, `word/footer1.xml` com `PAGE`, `word/settings.xml` com `updateFields`, e as duas referências abrindo o `sectPr` |
| — | SVG dentro do DOCX sem `<?xml?>` e com `width` em `em` | `svg_da_posicao(...).encode()` | `_svg_de_arquivo`: `declaracao=True`, `unidade="cm"` |
| — | `dc:creator` = "ChessVisionOFF" | `_nucleo` escrevia sempre | só com autor de verdade; o programa em `cp:lastModifiedBy` e em `docProps/app.xml` |

Os bloqueios 1, 2, 4 e 6 (tipografia do lance, título do capítulo, contraste da plaqueta) são de
`estudo_paragrafos.py` e de `diagrama_svg.py`/`diagrama_png.py`, e estão descritos na S-542; o DOCX
os herda por ler a mesma lista e desenhar o mesmo diagrama.

**Duas observações do crítico que não viraram mudança.** A primeira: `conferir_pacotes.py` acusa
`"uri da extensao SVG errada: {'{96DAC541-…}', None}"` -- o `None` é o `<a:ext cx= cy=>` de
`pic:spPr`, que é geometria e não tem `uri`; o script recolhe os dois elementos de mesmo nome. Ele
diz o mesmo sobre o artefato da rodada 1. A segunda: o mesmo script conta `PAGE` em
`word/document.xml` e acha zero -- o campo mora em `word/footer1.xml`, que é onde um número de página
mora. As partes que ele lista como "o Word costuma gravar e não estão" (`fontTable`, `theme1`,
`webSettings`, `numbering`, `footnotes`) continuam fora: o Word as cria ao salvar, e nenhuma é
exigida para abrir.

## S-544 · Diagramas em lote como PNG/SVG, no tamanho e na pele escolhidos — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-545 · Imprimir e gerar PDF do estudo com a paginação de livro — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-546 · Fila de PDFs com progresso por livro, cancelável, e o resultado ao lado do nome — ✅ **implementada em 2026-09-04**

### Problema

A varredura da biblioteca inteira existe desde a S-34 -- `batch.py:222` (`run_batch`) --, e a única
porta dela é `cvoff-batch` (`pyproject.toml:102` → `cli/batch.py:122`), um comando de terminal. Na
janela dá para exportar **um** livro: `qt/exportador.py:120` (`Exportador.comecar`) pergunta o
destino num diálogo e chama `save_pdf_positions_to_pgn` uma vez. Quem tem centenas de PDFs abre o
terminal, ou não faz. A varredura em lote existia; o que não existia era como pedi-la de dentro do
programa.

**E ela avisava por livro, e só.** `batch.py:229` declara `on_book_start` e `on_book_done`. O aviso
por **página** que `save_pdf_positions_to_pgn` já emitia -- `pdf_to_pgn.py:610`, o
`progress_callback` que o `qt/exportador.py:170` consome para exportar um livro -- chegava a
`_run_one` (`batch.py:265`) e morria ali, sem chamador. Entre um `on_book_start` e o `on_book_done`
seguinte cabem **2.612 páginas** (`📚Yusupov Artur. Build Up Your Chess`, medido). Uma janela que
fica dezenas de minutos sem mudar um pixel é uma janela travada aos olhos de quem espera.

**E faltava o empréstimo do modelo.** `_run_one` não passa `model_session` (`pdf_to_pgn.py:907`),
então cada livro carrega o próprio `.pt`. Está certo no terminal, onde não há treino concorrente;
na janela há, e o treino reescreve exatamente o arquivo que a fila estaria lendo por horas
(S-31/S-57).

### Solução

**`run_batch` ganhou dois parâmetros, e o terminal não mudou.** `on_page: PageProgress` é
`(livro, páginas feitas, páginas do livro, diagramas lidos até agora)`; `session_factory:
SessionFactory` empresta o modelo do `OcrService` **por livro**, sob o lock da S-31. Por livro e
não pela fila inteira: segurar o lock por uma varredura de cinquenta livros deixaria a própria
janela sem reconhecer a página aberta durante horas -- é a S-57 com a granularidade que a fila
permite. `None` nos dois é o caminho do `cvoff-batch`, e o teste afirma que sem `on_page` a
exportação recebe `progress_callback=None`, e não um callback ligado de graça em toda varredura de
terminal.

**A decisão mora em `ui/fila_de_livros.py`, e é pura.** Seis estados -- `pendente`, `lendo`,
`pronto`, `falhou`, `cancelado`, `pulado` -- e uma tabela `TRANSICOES` dizendo de cada um para
onde se vai. Voltar de `pronto` a `lendo` é o defeito que duplica trabalho e reescreve o PGN; sair
de `pendente` direto para `pronto` é o relatório mentindo; os quatro fins são finais.
`LivroNaFila` é imutável e trocado por `replace`, porque a fila é lida da thread da interface
enquanto a de trabalho escreve, e um registro que mudasse no lugar seria lido pela metade -- sem
exceção nenhuma para acusar. Ao lado: `frase_de_estado`, `linha_da_tabela` (as seis `Coluna` da
S-153, com o nome do livro como única elástica), `frase_de_resumo`, `fracao`, `contagem` e
`totais`.

**`pulado` é alcançável de `pendente` e de `lendo`, e isso não é folga.** O `skip_existing` da S-34
só é descoberto dentro de `_run_one`, **depois** de `on_book_start` já ter avisado que a varredura
chegou naquele livro -- então na fila da janela ele passa por `lendo` por um instante. Recusar
`lendo → pulado` faria a transição levantar dentro de um slot do Qt, que derruba o processo; e
adiar o `comecar` até a primeira página chegar deixaria sem sinal justamente o livro que não tem
página nenhuma.

**O resultado fica ao lado do nome, e não num relatório à parte.** A coluna Situação de um livro
terminado diz `120 diagrama(s), 0 exportado(s), 33 s`. Uma fila que dissesse só "pronto"
obrigaria a abrir o PGN para descobrir que ele saiu vazio -- que é o estado dos cinco livros do
acervo listados em `ROADMAP.md:151`. As contagens ficam **em branco** enquanto o livro não
terminou: um `0` numa coluna de resultado é indistinguível de "leu e não achou nada", e a fila tem
justamente livros em que zero é o resultado de verdade.

**A fração do conjunto conta livro, e não página.** O `page_count` de um PDF grande custa segundos
(S-61), e abrir os cinquenta antes de começar seria pagar isso cinquenta vezes só para desenhar
uma barra. Livro é a unidade que já se conhece no instante em que a fila é montada; o livro em
curso entra pela fração de páginas **dele**, que é o que a torna contínua.

**`qt/fila_de_livros.py` é a fiação, e nada mais.** Uma `Tarefa` -- o `QThread` de
`qt/trabalho.py` -- roda a `run_batch` inteira: **uma** thread, e não uma por livro, que é a
decisão medida da S-34 (a inferência do `torch` já ocupa os núcleos). Os três avisos são chamados
**na thread de trabalho** e só emitem sinal; quem toca a `FilaDeLivros` e a tabela é o slot do
outro lado. O único estado que as duas threads compartilham é um `int` (`_ordem_atual`), atribuído
de uma vez em CPython -- ler a própria `FilaDeLivros` da thread de trabalho, que era a forma
óbvia, seria ler uma lista que a interface reescreve.

**Duas barras, e não uma.** A do conjunto responde *quanto falta para acabar*; a do livro responde
*isto ainda está andando?* -- e num livro de 2.612 páginas só a segunda se mexe por dezenas de
minutos. Uma barra só teria de escolher qual das duas perguntas responder, e a escolhida seria a
errada metade do tempo.

**Cancelar para no fim da página em curso.** O `threading.Event` é conferido antes de cada livro
por `run_batch` e entre páginas por `save_pdf_positions_to_pgn` (S-24): o que já saiu fica
gravado, e o livro interrompido deixa o parcial que a próxima rodada retoma. Os livros que nunca
começaram viram `cancelado` **na hora**, e não quando a thread voltar: deixá-los como "na fila"
prometeria um trabalho que não vai acontecer. No `BusyRegistry` a fila entra com
`loses_work=False` e `cancellable=True` -- cada livro pronto tem o PGN no disco e o em curso tem o
parcial, então fechar custa tempo, não trabalho. A falha da fila inteira vai para o rodapé e não
para uma caixa modal em cima de operação deixada rodando, que é o critério da S-164.

### Critério de aceite

- O aviso por página chega com `(livro, feitas, total, diagramas)` e conta **a partir de um**, que
  é como quem espera lê "página 12 de 70"; sem `on_page`, a exportação recebe `progress_callback=None`. ✅
- O modelo do serviço é pedido **uma vez por livro**, e cada livro recebe a sua sessão. ✅
- Medido em 2026-09-04, varredura de verdade por `run_batch` com o `.pt` de produção, saída numa
  pasta do scratchpad: `Estrin - Bauernopfer` (88 páginas) e `Niemeijer - Zwarte Magie` (32
  páginas) numa fila só → **120 avisos de página em 81,1 s**, um por página, estritamente
  crescentes e sem repetição (88 e 32, `1..88` e `1..32`). Sem o item, a mesma fila emitiria
  **4** avisos ao todo -- dois `on_book_start` e dois `on_book_done` --, e a barra ficaria parada
  62,7 s no primeiro livro e 18,5 s no segundo. A barra do conjunto passa por 0,5 exatamente
  quando o primeiro livro acaba (afirmado no teste).
- E a fila mostra o que o item existe para mostrar: nessa mesma rodada o `Estrin` termina com
  `118 diagrama(s), 116 exportado(s), 2 ilegal(is), 63 s` ao lado do nome, e o `Niemeijer` com
  `51 diagrama(s), 0 exportado(s), 18 s` -- o livro que "processou" e não entregou nada, visível
  sem abrir o PGN.
- Cancelar responde em **menos de 1,5 s** com a fila em curso, o livro em leitura volta
  `cancelado` com o que leu, e os que nunca começaram também. ✅ Afirmado com medição de relógio
  no teste (`time.perf_counter`).
- Nenhuma thread sobrevive ao teste: cada caso espera a `Tarefa` antes de destruir o objeto, em
  LIFO -- um `QThread` destruído rodando derruba o processo. ✅
- Duas rodadas ao mesmo tempo são recusadas (`iniciar` devolve falso), e uma fila sem pendente
  também. ✅
- O `pulado` não vira `pronto` na tela, e o livro que falhou aparece **por nome** no resumo. ✅

### Testes

- `tests/test_batch.py::AvisoPorPaginaTests`: o aviso por página chega com o livro e o total, e
  1-based; sem ele a exportação não recebe `progress_callback`; o modelo do serviço é pedido uma
  vez por livro e cada um recebe a sua sessão.
- `tests/test_ui_fila_de_livros.py` (5 classes, 34 casos, sem Qt): o caminho normal; `pronto` não
  volta a `lendo`; `pendente` não pula para `pronto`; `pulado` alcançável dos dois lados; os
  quatro fins são finais; `concluir` recusa não-fim; `avancar` num livro terminado é ignorado; o
  mesmo livro não entra duas vezes; cancelar marca os pendentes e não o que está lendo; a tradução
  dos quatro `status` do `batch` e o status novo virando `falhou` em vez de exceção; as frases de
  cada estado (na fila, abrindo o livro, lendo a página N de M, o resultado, a falha com motivo, o
  cancelado que nunca começou); a unidade do tempo (s/min/h); a linha com uma célula por coluna, a
  elástica única, as quatro numéricas e as contagens em branco antes do fim; a fração por livro e
  a do livro em curso por página; a fila vazia sem divisão por zero; a contagem com estado zerado;
  um só livro em curso; o resumo somando livros, páginas, diagramas, exportados e ilegais, com a
  falha por nome, o "por fazer", o "já exportado antes" e o "cancelado".
- `tests/test_qt_fila_de_livros.py` (2 classes, 21 casos): a `_VarreduraFalsa` cumpre o contrato
  inteiro de `run_batch` -- os três avisos, a ordem deles e o `cancel_event` conferido antes de
  cada livro e entre páginas --, porque é esse contrato que a fiação consome; uma de verdade
  exigiria PDF, `.pt` e minutos. Afirmam: o resultado ao lado do nome; o progresso por página
  chegando por sinal e a fração terminando em 1; o pulado; a recusa de duas rodadas; o
  cancelamento em < 1,5 s com relógio; a falha da varredura inteira virando sinal e log, não
  exceção; o registro no `BusyRegistry` com `loses_work=False`; o empréstimo do modelo um livro de
  cada vez; e, no diálogo, a fila vazia dizendo o que fazer, o botão que liga, as duas barras
  andando e terminando cheias, a tabela publicando as contagens, o botão Cancelar, a falha no
  rodapé e não numa caixa, o livro falhado por nome, e as colunas declaradas.
- `tests/test_busy.py`: a fila **está** no registro, e por isso não entra em `SEM_REGISTRO`.
- `docs/ARCHITECTURE.md`: a linha da fila na tabela de threads, conferida contra `qt/*.py` por
  `tests/test_docs.py` (S-410/S-506).

### A segunda rodada: a fila passou a ter porta

**O item chamava-se "na janela" e não era alcançável de dentro dela.** `abrir_fila_de_livros` e
`DialogoDaFila` estavam prontos e nenhum dos quatro lugares que abrem coisa na janela os citava --
`ui/comandos.py`, `ui/menu.py`, `qt/janela.py`, `app_pyqt.py`. As três linhas que faltavam foram
escritas:

- `ui/comandos.py`: `Comando("varrer_fila", "Varrer uma fila de livros…", ACERVO, estilos.NEUTRO)`,
  colado no `varrer_livro`. É ACERVO pela mesma pergunta do vizinho -- age sobre livros inteiros --
  e as reticências dizem que ele abre uma janela em vez de começar a varrer.
- `ui/menu.py`: `Item("varrer_fila")` logo depois de `Item("varrer_livro")`. Colado, porque são a
  mesma varredura com um livro e com muitos, e quem procura "varrer" tem de achar as duas juntas.
- `qt/janela.py`: `JanelaPrincipal.abrir_fila_de_livros`, que empresta ao diálogo o serviço (o
  modelo sob o lock da S-31), o `BusyRegistry` e a pasta de livros -- os três objetos que a janela
  tem e o módulo da fila não conhece. O diálogo **não** é guardado em atributo: ele não é modal,
  não é reusado e sabe se fechar, e um segundo dono só criaria divergência sobre quem o destrói.

A catraca de `qt/janela.py` subiu de **1.891 para 1.905** com o motivo escrito no docstring de
`tests/test_packaging.py`: doze das catorze linhas são o método, e ele existe em vez de uma
`lambda` porque uma `lambda` não tem nome para o critério de aceite citar nem lugar onde o
"por que o diálogo não é guardado" possa morar.

**O teste dispara a ação e olha o efeito.** `janela.menu.acoes["varrer_fila"].trigger()`, e depois
procura um `DialogoDaFila` entre os filhos da janela: depois de um `connect`, trocar o método não
troca quem o sinal chama, então um `mock.patch.object` sobre `abrir_fila_de_livros` mediria uma
ligação que já não existe.

**O livro que não leu deixou de mostrar quatro zeros.** A primeira rodada esvaziava as colunas de
quem ainda não tinha terminado; o livro que **falhou** aparecia com `0 / 0 / 0 / 0 s`, e zero ali
não é medição -- é a ausência dela. `LivroNaFila.leu` é a régua: mostra número quem chegou a ler
página (pronto, ou cancelado depois de ter lido), e o resto fica em branco. O caso que a coluna em
branco **não** pode engolir continua aparecendo: o livro lido que achou 51 diagramas e exportou
zero mostra `51 / 0 / 0 / 18 s`, que é o item inteiro numa linha.

**Dá para tirar um livro da fila.** Acrescentar era irreversível, e uma pasta escolhida entra com
todos os PDFs dela (S-34): quem apontasse a pasta errada tinha de fechar o diálogo e montar a fila
de novo. `FilaDeLivros.remover` tira as linhas marcadas -- várias de uma vez, e a tabela passou a
aceitar seleção múltipla --, e o botão fica cinza **enquanto a varredura roda**: a thread de
trabalho guarda a posição de cada livro como um número (`_ordem_atual`), e tirar uma linha de cima
dele faria o resultado do seguinte chegar na linha de outro, em silêncio. A recusa é dupla, no
botão e em `FilaDeLivros.remover`, que nunca tira o livro em `lendo`.

**A tabela da fila ganhou dica de célula e continua sem ordenação por cabeçalho.** A dica é o
conserto do que o crítico viu: dois livros de nome longo ficam visualmente idênticos sob as
reticências do Qt, e a fila põe os dois lado a lado dizendo que um deles falhou. A ordenação é
opt-in (`TabelaQt(ordenavel=…)`) e a fila **não** a liga: a ordem dela é a de execução, e reordenar
faria o livro em leitura saltar de lugar enquanto a barra anda.

### O que mudou no critério de aceite

- O comando existe no catálogo, tem item de menu e tem dono na janela; disparar a ação do menu
  **abre o diálogo**, filho da janela, com o serviço e o registro de ocupação dela. ✅
- O livro que falhou, o pulado e o cancelado antes de começar saem com as quatro colunas de
  resultado **em branco**; o livro que leu e não achou nada continua mostrando os zeros. ✅
- Um livro sai da fila pelo botão; vários saem de uma vez; o que está sendo lido não sai; com a
  varredura em curso a remoção é recusada. ✅
- Toda célula da tabela leva o próprio texto como dica. ✅
- Tudo o que a primeira rodada afirmou continua valendo, e as medições de campo (120 avisos de
  página em 81,1 s, cancelamento em < 1,5 s) não foram refeitas: nada no caminho da varredura
  mudou.

### Testes acrescentados

- `tests/test_qt_janela.py::FilaDeLivrosNaJanelaTests`: a ação do menu abre o diálogo (o **efeito**,
  não a fiação); o comando está no catálogo e tem dono; o diálogo não é guardado na janela.
- `tests/test_ui_fila_de_livros.py::LivroQueNaoLeuTests`: as quatro colunas em branco no falhado, no
  pulado e no cancelado antes de começar; o cancelado que leu mostra o que leu; o lido que não
  achou nada mostra os zeros.
- `tests/test_ui_fila_de_livros.py::RemoverDaFilaTests`: sai um, saem vários na ordem da fila, o
  que está em leitura não sai, índice fora da fila não levanta, e o removido pode voltar.
- `tests/test_qt_fila_de_livros.py::TirarDaFilaTests`: o botão tira a linha marcada, sem marca nada
  sai, o botão nasce desligado, e com a varredura em curso a remoção é recusada.
- `tests/test_qt_tabela.py::OrdenacaoEDicaTests`: a dica em toda célula, e a tabela sem ordenação
  de fábrica.

### O que o crítico recusou

| o que ele achou | o que mudou |
|---|---|
| `abrir_fila_de_livros`/`DialogoDaFila` **sem chamador nenhum**: o item chama-se "na janela" e não é alcançável de dentro dela | As três linhas escritas (`ui/comandos.py`, `ui/menu.py`, `qt/janela.py`), com a catraca da janela subida de 1.891 para 1.905 e o motivo no docstring |
| Livro que falhou mostra `0 / 0 / 0 / 0 s` nas colunas | `LivroNaFila.leu`: mostra número quem leu página; falhado, pulado e cancelado-antes-de-começar ficam em branco |
| Não dá para remover um livro da fila depois de acrescentado | Botão "Tirar da fila", seleção múltipla, e a recusa dupla enquanto a varredura roda |
| Sem tooltip em nenhuma `TabelaQt`: dois livros de nome longo ficam visualmente idênticos | Toda célula leva o próprio texto como dica |
| Tabela da busca sem ordenação por coluna | Ligada na busca (S-533) e deixada **desligada** na fila, com o motivo escrito: a ordem da fila é a de execução |


## S-547 · Caminho para scans puros: binarização e reamostragem antes da detecção — ⚠ **medida em 2026-09-04, sem ganho**

### Problema

**Cinco livros do acervo exportam zero** -- `Koblenz`, `Levenfis`, `Melhores Finais de Capablanca`,
`Niemeijer` e `Stefaniu`, 1.077 páginas somadas (`ROADMAP.md:151`). Não é o gate sendo severo: a
confiança mínima média deles fica entre 0,034 e 0,246, contra 0,99 dos que exportam quase tudo
(`ROADMAP.md:1214`). São livros digitalizados, e `ANALISE_DETECCAO.md:539` já dizia de onde vem:
"o scan velho é cinza" -- meio-tom onde o diagrama impresso é tinta e papel.

**E o pipeline não tinha onde tratar isso.** A normalização que existe é a do **tabuleiro
recortado** -- `preprocess.py:263` (`BoardNormalizer`: deskew, flat-field, supressão de hachura,
CLAHE) --, e ela entra depois da detecção. A página renderizada vai crua de `pdf_to_pgn.py:551`
(`_render_pdf_page`) para `detect_diagrams_in_pdf_page` (`pdf_to_pgn.py:399`): entre o render e a
detecção não há etapa nenhuma. Se o problema for a página, e não o tabuleiro, não havia por onde.

**E não havia como nem perguntar "esta página é um scan?".** A cobertura da maior imagem embutida
era calculada dentro de `candidates_from_embedded_images` (`detection/embedded.py:535`), onde serve
para descartar o scan de fundo contra `MAX_PAGE_COVERAGE` (`embedded.py:96`), e morria no laço.

### Solução

**A porta:** `preprocess.pagina_e_scan(tem_camada_de_texto, cobertura_de_imagem)`, alimentada por
`detection.largest_image_coverage(page)` -- que só publica o número que já era calculado, e devolve
`0.0` (e não exceção) para a página sem imagem, para a vetorial e para aquela que o PyMuPDF recusa
a descrever, porque um XObject malformado não pode derrubar a varredura de um livro inteiro.

**`ou`, e não `e`, e a diferença foi medida:** os 46 PDFs de `PDF/`, 24 páginas amostradas de cada
um. O `ou` seleciona **26 livros**; o `e` selecionaria **11**. Os dois sinais discordam em livro
demais para um `e` valer: o `Koblenz` e o `Gunderam` têm camada de texto nas 24 páginas **e** são
scan de página inteira nas 24 (o OCR de quem digitalizou deixou o texto lá); o `Simple Chess` não
tem camada em página nenhuma e também não tem imagem de página inteira em 23 das 24. Um `e`
deixaria os três de fora.

**O caminho:** `ScanConfig(binarizacao, dpi_alvo)` e `preparar_pagina_de_scan(page_rgb, config,
dpi=…)`. `binarizar_pagina` faz Otsu (global) ou Sauvola (local, `T = m·(1 + k·(s/R − 1))` por
janela deslizante, com média e desvio saindo de dois `boxFilter` -- a forma por imagem integral,
porque uma janela de 55 px numa página de 2.200 seria proibitiva calculada pixel a pixel), e
devolve **três canais**, porque é o que `detect_diagrams`, o recorte do tabuleiro e o
`board_texture_score` esperam; um canal só faria a troca aparecer como erro de forma três camadas
adiante. `reamostrar_pagina` usa `INTER_AREA` para reduzir e `INTER_CUBIC` para ampliar. A
reamostragem vem **antes** da binarização, porque a binarização mede estatísticas em janela de
pixels: fazê-la antes seria decidir o limiar numa escala e usá-lo noutra -- é a mesma ordem, e o
mesmo argumento, do `BoardNormalizer.normalize`.

**E o caminho vem desligado, por medição.** `ScanConfig()` é identidade e `preparar_pagina_de_scan`
devolve **a mesma imagem**. Fica na forma do `NormalizerConfig` ao lado, pelo mesmo motivo dele:
medido, desligado, documentado, e disponível para quem tiver outro acervo.

### Critério de aceite

**O item era medir, e a medição diz que não ligue.** Livro inteiro, sem amostragem, com o `.pt` de
produção de 2026-09-04, `max_boards=12`, ordem de coluna, gate em `ACCEPT_MIN_CONFIDENCE`. As três
colunas são proxies deliberados e comparáveis entre si, porque a mesma regra vale para todas as
variantes: **diagramas** é o que `detect_diagrams` devolve; **FEN legal** é `check_position` com o
lado a jogar assumido branco (e não o resolvido pela S-17); **acima do gate** é a confiança mínima
do tabuleiro contra o limiar -- que é o **teto** do que a exportação aceitaria, já que ela ainda
exige legalidade, orientação certa e o lado a jogar concordando com o texto.

**Os dois livros do acervo que exportam zero:**

| livro | variante | diagramas | FEN legais | acima do gate | conf. mín. média |
|---|---|---|---|---|---|
| `Koblenz` (70 p) | sem o caminho novo | 120 | 64 | **0** | 0,079 |
| | Otsu | 120 | 64 | **0** | 0,148 |
| | Sauvola | 120 | 56 | **0** | 0,113 |
| | 300 DPI | 112 | 74 | **0** | 0,084 |
| `Niemeijer` (32 p) | sem o caminho novo | 51 | 42 | **0** | 0,260 |
| | Otsu | **79** | 57 | **0** | 0,179 |
| | Sauvola | 72 | 55 | **0** | 0,257 |
| | 300 DPI | **18** | 13 | **0** | 0,253 |

**E três que a mesma porta de scan seleciona e que já vão bem, para ver o que se perde:**

| livro | variante | diagramas | FEN legais | acima do gate | conf. mín. média |
|---|---|---|---|---|---|
| `Reinfeld_1001` (320 p) | sem o caminho novo | 995 | 992 | **985** | 0,981 |
| | Otsu | 935 | 930 | **918** | 0,981 |
| | Sauvola | 1.000 | 994 | **984** | 0,983 |
| `Estrin` (88 p) | sem o caminho novo | 118 | 112 | **116** | 0,985 |
| | Otsu | 117 | 112 | **115** | 0,981 |
| | Sauvola | 118 | 112 | **115** | 0,970 |
| | 300 DPI | 118 | 112 | **116** | 0,983 |
| `Euwe Band 7` (56 p) | sem o caminho novo | 80 | 79 | **55** | 0,799 |
| | Otsu | 80 | 78 | **46** | 0,732 |
| | Sauvola | 80 | 79 | **48** | 0,778 |
| | 300 DPI | 80 | 80 | **58** | 0,789 |

**Quatro leituras, e nenhuma delas é "ligue isto":**

1. **A binarização move a detecção e não move a exportação.** No `Niemeijer` o Otsu acha **55% mais
   diagramas** -- 79 contra 51 --, e o livro continua com **zero** acima do gate: nenhum dos novos
   se consegue ler. Achar mais do que não se lê não é ganho. No `Koblenz` a contagem nem se move.
2. **O Otsu custa caro no livro que já vai bem, e o Sauvola custa pouco -- e nenhum dos dois
   compra nada.** O `Reinfeld_1001` perde **67 dos 985** acima do gate com Otsu (985 → 918) e
   apenas 1 com Sauvola; o `Euwe Band 7` perde 9 dos 55 com Otsu e 7 com Sauvola; o `Estrin` perde
   1 dos 116 com qualquer um. Ou seja: o Sauvola é quase inócuo nos bons e o Otsu é caro, e a
   escolha entre os dois **só importaria se algum deles ganhasse alguma coisa nos ruins** -- e
   nenhum ganha. Um caminho que no melhor caso não muda nada e no pior perde 67 posições de um
   livro só não se liga por padrão.
3. **A reamostragem para 300 DPI perde diagrama, e muito:** −8 no `Koblenz` (120 → 112) e −33 no
   `Niemeijer` (51 → 18). O detector de contorno tem limiares em pixel, e uma página maior muda o
   que eles alcançam. A medição **renderizou** a 300 DPI, que é o melhor caso possível: reamostrar
   a partir dos 220 não tem como sair melhor que renderizar direto na resolução alvo.
4. **A porta funciona e não separa o que interessa.** Ela seleciona 26 dos 46 livros, e entre eles
   estão, lado a lado, o `Reinfeld_1001` (985 dos 995 acima do gate) e o `Koblenz` (0 dos 120) --
   os dois medidos no mesmo dia, com o mesmo modelo. "É um scan" e "é um scan que o modelo não lê"
   são perguntas diferentes, e só a primeira tem resposta barata.

**O que fica.** O caminho existe, é testado e vem desligado; `ScanConfig` carrega a tabela acima no
docstring, para que quem for ligá-lo saiba o que já foi tentado. `pagina_e_scan` e
`largest_image_coverage` ficam porque a pergunta "esta página é um scan?" deixou de custar uma
varredura -- e é dela que o próximo item vai precisar, quando a resposta for treinar em vez de
filtrar.

### Testes

- `tests/test_preprocess.py::PortaDoScanTests`: a porta é `ou` e não `e`, nos três casos que a
  medição separou; e o piso de cobertura é **o mesmo número** de `MAX_PAGE_COVERAGE`, porque lá ele
  decide "esta imagem é fundo" e aqui "esta página é scan" -- dois números para a mesma observação
  divergiriam.
- `tests/test_preprocess.py::CaminhoDeScanTests`: o padrão é identidade e devolve **a mesma
  imagem** (`assertIs`); binarização desconhecida e `dpi_alvo` negativo levantam em vez de cair no
  padrão, porque um método escrito errado que virasse "não binariza" seria uma medição
  silenciosamente feita sobre outra coisa; a binária sai com três canais e só dois valores; **Otsu
  é global e Sauvola é local**, provado numa página com sombra de lombada, onde o Otsu entrega o
  lado escuro inteiro como tinta (>90% de preto) e o Sauvola atravessa (<50%); reamostrar para o
  mesmo DPI é identidade; a escala muda e o conteúdo não; a reamostragem vem antes da binarização;
  e o DPI alvo declarado é o que a medição usou, sem ser o padrão.
- `tests/test_detection.py::CoberturaDaMaiorImagemTests`: a página sem imagem não diz que é scan; o
  scan de página inteira cobre >95%; um diagrama no meio da página cobre <20% -- que é a distinção
  inteira; a maior manda quando há várias; e a página que o PyMuPDF recusa a descrever devolve
  `0.0` com aviso no log, em vez de derrubar o livro.

### O que ficou de fora

- **Nada foi ligado no caminho de produção.** `pdf_to_pgn.py` continua entregando a página crua à
  detecção; ligar o caminho exigiria uma opção em `BatchOptions` e na CLI, e a medição não dá
  motivo para oferecê-la.
- **A supressão de hachura sobre a página inteira** apareceu na varredura de variantes e não foi
  perseguida: com `hatch_kernel_ratio` em 0,020 o `Koblenz` sobe de 64 para **95** FENs legais nos
  mesmos 120 diagramas -- e continua com zero acima do gate --, enquanto o `Euwe Band 7` desaba de
  79 FENs legais para **0**. É uma pista para quem for atrás da leitura, e não deste item, que é
  sobre a página.
- **Os quatro relatórios de campo ficaram com o digest vencido, e não foram republicados daqui.**
  `preprocess.py`, `detection/embedded.py` e `detection/__init__.py` estão no fecho de importação
  que o `cvoff-field` exercita, então a guarda da S-218
  (`test_field_eval.py::test_todo_relatorio_corrente_mediu_o_codigo_de_hoje`) acusa os quatro de
  `docs/metrics/`. **A adição é inerte, e isso foi medido dos dois lados:** nenhum dos 30 módulos
  do fecho chama os nomes novos -- só o próprio `preprocess.py`, entre eles --, e remedir os quatro
  com os modelos arquivados (que ainda estão no disco, conferidos por digest) reproduz cada
  arquivo **campo a campo**, tirando apenas `seconds` e `seconds_per_diagram`. Republicá-los a
  partir do worktree gravaria `C:/Python-Chess2/…` no `path` do modelo -- que é o dano 1 descrito
  em `field_eval._model_path_relativo`, porque os `.pt` moram fora desta árvore -- e
  `code_dirty: true`, porque o item ainda não está commitado. A remedição é do checkout principal,
  depois do commit, e é só trocar o digest: os números não se movem.

### O que o crítico recusou

_a preencher pelo crítico_

## S-548 · Relatório de qualidade por livro: páginas lidas, diagramas, legalidade, tempo — ✅ **implementada em 2026-09-04**

### Problema

O que uma varredura deixa em disco é **um** JSON para a rodada inteira: `cli/batch.py:33`
(`DEFAULT_REPORT = PGN/batch_report.json`), gravado a cada livro por `batch.py:260` com a forma de
`BatchReport.to_dict` (`batch.py:183`) -- `started_at`, a lista dos livros e os totais. A entrada
de cada livro (`BookResult.to_dict`, `batch.py:96`) traz páginas, aceitos, para revisão, ilegais,
repetidos, confiança mínima média, taxa de aceitação e tempo. É bastante, e faltam três coisas --
que são o item:

1. **O relatório não viaja com o livro.** É um arquivo por rodada, no caminho que a rodada
   escolheu, sobrescrito pela rodada seguinte. Comparar o `Koblenz` de hoje com o de um mês atrás
   é ter guardado o `batch_report.json` inteiro à mão, e saber qual dos cinquenta livros dele era
   o `Koblenz`.
2. **Não há procedência.** O `.pt` é reescrito por todo treino (S-31/S-57), então o caminho não o
   identifica; e o mesmo livro lido a 220 e a 300 DPI dá contagens diferentes -- medido na S-547,
   o `Niemeijer` dá 51 diagramas contra 18. Sem o DPI e sem a identidade do checkpoint, dois
   números da mesma pasta não se comparam (S-219).
3. **Faltam as taxas que tornam dois livros comparáveis.** `acceptance_rate` existe
   (`batch.py:92`); `legal_rate`, `seconds_per_page` e `seconds_per_diagram` não. Um livro de 70
   páginas e outro de 2.612 não se comparam por `elapsed_s`, e `120 diagramas` sozinho não diz se
   o livro foi bem -- `120 diagramas, 0 exportados` diz, e é o estado de cinco livros do acervo
   (`ROADMAP.md:151`).

### Solução

**Três funções em `batch.py`, nenhuma delas no caminho da varredura.**
`relatorio_de_qualidade(resultado, options, medido_em=…)` monta o dicionário de um livro;
`caminho_do_relatorio_de_qualidade(pdf, output_dir)` dá `<pasta>/<livro>.qualidade.json`;
`gravar_relatorios_de_qualidade(relatorio, options, output_dir)` grava um por livro e devolve os
caminhos, em ordem.

**Quatro perguntas, e as quatro só respondem juntas:** quantas páginas foram lidas
(`pages`), quantos diagramas saíram de lá (`diagrams`), quantos deles viraram posição exportável
(`exported`, `needs_review`, `illegal`, `duplicates`, com `export_rate` e `legal_rate`), e quanto
custou (`elapsed_s`, `seconds_per_page`, `seconds_per_diagram`). O tempo por página é o que torna
dois livros comparáveis quando um tem 70 páginas e outro 2.612.

**Ao lado do PGN, e não em `docs/metrics/`.** `docs/metrics/` é o arquivo de medição do
**repositório** -- versionado, comparado por guarda, com procedência de código (S-218). O
relatório de um livro varrido na máquina de quem usa o programa é saída do usuário, e mora onde a
saída dele mora.

**O nome sai do PDF e não do PGN.** O livro pulado nem chega a ter PGN próprio nesta rodada, e o
relatório dele -- que diz justamente "já estava exportado" -- ainda tem de saber onde nascer.

**`schema: 1`**, a versão do **formato**, na forma de `text/arquivo.py` e `text/fila.py`: quem
abrir um relatório antigo daqui a seis meses precisa saber se os campos que espera existiam. Sem
isso, um campo acrescentado depois é indistinguível de um campo que a medição daquele dia deixou
em branco.

**A procedência é o que faz o número se reproduzir.** `model.identity` é
`checkpoint.checkpoint_identity` (`checkpoint.py:138`) -- `<tamanho>-<mtime_ns>`, um `stat` --, e
vai junto com `dpi`, `max_boards_per_page`, `orientation`, `reading_order`, `accept_threshold` e
`dedupe`, que são os parâmetros de leitura que mudam a contagem. `program` sai do metadado da
distribuição instalada pela **mesma** leitura que `ui/strings._versao_instalada` faz -- ler o
mesmo metadado de dois lugares não tem como divergir; o que a S-161 proibiu foi *cravar* o número,
que é outra coisa. `measured_at` é o `started_at` da rodada, e não a hora de gravar: o que
identifica a medição é quando ela começou.

**Os caminhos saem relativos à raiz** (`config.caminho_para_relatorio`, `config.py:196`) quando
cabem nela, pela mesma razão dos relatórios de campo: um relatório com o layout do disco de quem
mediu não compara com o de outra máquina.

**Escrita por `atomic_write_json`**, como todo arquivo de trabalho deste projeto: um relatório pela
metade é pior que nenhum, porque ele **abre** e responde números truncados. E um livro cujo
relatório não consegue ser gravado não derruba os outros -- é a regra do livro que falha na
varredura (S-34), e aqui ela pesa mais: perder cinquenta relatórios porque um nome de arquivo é
inválido seria perder a medição inteira por causa da última linha dela.

**Na fila da janela, no fim e não a cada livro.** O `BatchReport` é o mesmo objeto o tempo todo, e
gravar cinquenta arquivos cinquenta vezes escreveria 1.275 arquivos para entregar cinquenta. O que
protege contra a interrupção é o `--report` da própria varredura, que já é gravado a cada livro. O
diálogo aceita `relatorios=False`, porque quem varre para conferir uma coisa só não quer cinquenta
JSON ao lado dos PGN.

### Critério de aceite

- Um JSON por livro, com o nome do PDF, inclusive para o livro **pulado**. ✅
- As quatro perguntas no arquivo, com as taxas derivadas, e sem divisão por zero num livro sem
  página nem diagrama. ✅
- Procedência com a identidade do checkpoint e os parâmetros de leitura; caminhos relativos à
  raiz. ✅
- Medido em 2026-09-04, varredura de verdade com o `.pt` de produção, saída numa pasta do
  scratchpad:

  | | `Estrin - Bauernopfer` | `Niemeijer - Zwarte Magie` |
  |---|---|---|
  | páginas | 88 | 32 |
  | diagramas | 118 | 51 |
  | exportados | **116** | **0** |
  | para revisão / ilegais | 0 / 2 | 51 / 0 |
  | `export_rate` | 0,9831 | **0,0** |
  | `legal_rate` | 0,9831 | 1,0 |
  | `mean_min_confidence` | 0,9845 | 0,2598 |
  | `elapsed_s` | 62,66 | 18,49 |
  | `seconds_per_page` | 0,712 | 0,578 |
  | `seconds_per_diagram` | 0,531 | 0,363 |

  Os dois JSON saíram com a mesma procedência -- `identity` `8786520-1788179963836706300`, DPI
  220, `accept_threshold` 0,80, ordem de coluna, `program` `0.1.0`, `measured_at` o `started_at`
  da rodada -- e são o item inteiro numa linha: o `Niemeijer` **processou** 32 páginas, achou 51
  diagramas e entregou zero, com a confiança mínima média em 0,26. Sem `export_rate` ao lado de
  `diagrams`, "51 diagramas" leria como sucesso.

  Os caminhos saíram **absolutos** nessa rodada, e é o comportamento declarado: a pasta de saída
  estava fora da raiz do projeto, e `caminho_para_relatorio` só relativiza o que cabe nela.

- O relatório de um livro é legível sozinho: nada nele remete ao relatório consolidado nem à
  posição do livro na fila. ✅

### Testes

- `tests/test_batch.py::RelatorioDeQualidadeTests`: as quatro perguntas e as três taxas derivadas;
  o livro sem diagrama e sem página não divide por zero; a procedência diz com que modelo e com
  que DPI; o caminho publicado é relativo à raiz; um arquivo por livro com o nome do PDF e o
  `schema` gravado; o livro pulado também ganha relatório.
- `tests/test_qt_fila_de_livros.py::DialogoTests`: o relatório sai um por livro ao fim da fila,
  com `book`, `diagrams`, `exported` e `provenance`, e o caminho da pasta aparece no rodapé; e a
  fila pode varrer sem deixar relatório nenhum.

### A segunda rodada: o que o relatório dizia sem ter medido

O crítico varreu um PDF truncado e o relatório saiu com `"status": "ok"`, `pages: 0`,
`error: ""`, `legal_rate: 1.0` -- e um `.pgn` de 0 byte ao lado. Duas coisas erradas, e as duas do
mesmo tipo: **o arquivo respondia perguntas que ninguém pôde medir**.

**Livro com zero página é falha.** `_run_one` só chamava de falha o que levantasse exceção; o PDF
que abre e não entrega página nenhuma -- o download que parou no meio, o arquivo de 0 byte -- saía
como `ok`. Na fila da janela isso lê como *"foi lido e não achou nada"*, que é o resultado **de
verdade** de cinco livros do acervo (`ROADMAP.md:151`): os dois ficavam indistinguíveis, que é
exatamente o que este item existe para impedir. Agora ele volta `STATUS_FAILED` com o motivo
escrito -- *"o livro não entregou página nenhuma; o PDF pode estar truncado ou vazio"* --, aparece
por nome no resumo da fila e sai do relatório consolidado como falha.

O outro lado ficou explícito num teste: **zero diagrama em dez páginas continua sendo `ok`**.
Cancelar antes da primeira página continua sendo `cancelado`. A falha é a ausência de página, e
não a ausência de resultado.

**`legal_rate` sem diagrama é `null`, e não `1.0`.** O arquivo dizia *"100% das posições são
legais"* sobre zero posição. Num gráfico que compara cinquenta livros pela legalidade, isso põe o
livro que **falhou** no topo da lista. `null` diz *não medido*, que é a verdade -- é o mesmo
critério do travessão de `ui/busca_de_partidas` e do `Elo` vazio: a ausência de valor não é um
valor. `export_rate` foi junto, pela mesma razão e no mesmo lugar (`_taxa`).

`seconds_per_page` e `seconds_per_diagram` continuam saindo `0.0` num livro sem página nem
diagrama, porque ali o zero **é** a leitura: nenhum segundo foi gasto por página que não houve, e
a diferença entre `0.0` e `null` num campo de custo não muda decisão nenhuma. As taxas são
diferentes: uma taxa é uma fração de alguma coisa, e sem a coisa ela não existe.

### O que mudou no critério de aceite

- O livro truncado sai como **falha com motivo**, e não como `ok` com zero. ✅
- `legal_rate` e `export_rate` saem `null` num livro sem diagrama; com diagramas continuam as
  frações de sempre (0,9831 e 1,0 no `Estrin`; 0,0 e 1,0 no `Niemeijer`). ✅
- A medição de campo de 2026-09-04 -- os dois livros, as dez linhas da tabela, a procedência com
  `identity` `8786520-1788179963836706300` -- **não foi refeita e continua valendo**: os dois
  livros entregaram páginas, e nenhum dos dois campos mudou de valor para eles. O que mudou vale
  para o livro que não entrega nada, e esse não estava na medição.
- O restante do critério da primeira rodada segue igual: um JSON por livro (inclusive o pulado), as
  quatro perguntas com as taxas derivadas, procedência com a identidade do checkpoint, caminhos
  relativos à raiz quando cabem nela, escrita por `atomic_write_json`, e um relatório que não
  grava não derruba os outros.

### Testes acrescentados

- `tests/test_batch.py::LivroSemPaginaTests`: o livro sem página nenhuma vira falha **com motivo**;
  o que leu dez páginas e não achou nada continua `ok`; o cancelado sem página continua
  `cancelado`.
- `tests/test_batch.py::RelatorioDeQualidadeTests::test_a_taxa_sem_diagrama_e_nula_e_nao_perfeita`:
  `legal_rate` e `export_rate` nulos sem diagrama, e as frações de sempre com diagrama. O teste que
  afirmava `legal_rate == 1.0` nesse caso foi **reescrito**: ele afirmava o defeito.

### O que o crítico recusou

| o que ele achou | o que mudou |
|---|---|
| PDF truncado sai como `"status": "ok"`, `pages: 0`, `error: ""` e grava `.pgn` de 0 byte | Zero página é `STATUS_FAILED` com o motivo escrito; o livro aparece por nome no resumo da fila |
| `legal_rate: 1.0` num livro sem diagrama | `null` (`_taxa`), e `export_rate` junto. `seconds_per_*` continuam `0.0`, com o motivo escrito |
| (aprovada com ressalva) o resto do item | Nada mais mudou; a medição de campo dos dois livros não foi refeita, e a seção diz por quê |


## S-549 · Guarda genérica: nenhum módulo de `ui/` importa toolkit — ✅ **implementada em 2026-09-04**

### Problema

A regra existe desde o corte do Tk (S-506): `src/chess_diagram_ocr/ui/` é a camada pura e `qt/` é o
toolkit. O que a cobrava eram três guardas, nenhuma genérica:

- `tests/test_ui_comandos.py:495` (`test_o_catalogo_nao_importa_tkinter`) e
  `tests/test_ui_texto_cor.py:138` (`test_o_modulo_de_cor_nao_importa_tkinter`) olham **um módulo
  cada**, e perguntam só por `tkinter`;
- `tests/test_editor_model.py:405` (`SemTkinterTests`, S-137) percorre `ui/` inteira, mas pergunta por
  `tkinter` e `PIL` -- o toolkit que **saiu**. A lista `SEM_TKINTER` é a de 2026-08-12, quando importar
  Tk em `ui/` era o normal e a lista fixava quem tinha decidido não fazê-lo.

Um `from PyQt6.QtCore import Qt` num módulo de `ui/` passava pelas três em verde, e é o import mais
provável de todos hoje, porque o Qt é o único toolkit que resta. Nada perguntava por `PySide6`, por
`ttkbootstrap` (que saiu do `pyproject.toml` no corte) nem pelo caminho indireto -- `from
chess_diagram_ocr.qt import tema`, que não escreve `PyQt6` em linha nenhuma e só abre com o Qt
instalado. E nada perguntava pelo resto do pacote: `service.py`, `detection/`, `text/` e `cli/` são a
promessa da S-31 (*a interface é apresentação*), e a única cobrança dela era a de a S-500 ter conseguido
nascer.

### Solução

`tests/test_ui_fronteira.py`, uma varredura por `ast` com uma função só -- `violacoes(pasta, raiz,
isencoes)` -- apontada três vezes:

1. para `ui/`: nenhum módulo importa `PyQt6`, `PySide6`, `tkinter`, `ttkbootstrap` nem
   `chess_diagram_ocr.qt`;
2. para o pacote inteiro: nada fora de `qt/` importa toolkit, salvo o que `PODEM_IMPORTAR_TOOLKIT`
   isenta **com motivo** -- hoje só `cli/texto_transcrever.py`, a janela Tk de desenvolvimento que
   transcreve as 123 faixas da S-183 e que o corte deixou de propósito;
3. para `qt/`: o **controle** sobre a árvore real -- a mesma função tem de achar o toolkit em todo
   módulo de desenho (31 de 33; `__init__.py` e `preferencias.py` não têm widget de propósito).

A leitura conta `import x`, `from x import y`, o import tardio dentro de função, o de
`TYPE_CHECKING`, o relativo (`from ..qt import tema`, resolvido contra o pacote do arquivo) e o por
nome (`importlib.import_module("PyQt6.QtGui")`). Não conta prosa: os módulos deste projeto citam
`import tkinter` e `PyQt6` em docstring para dizer que aquilo **não** existe ali, e uma varredura de
texto reprovaria a explicação -- é a mesma razão do `ast` em `test_ui_orfaos.py` (S-511).

A isenção é um mapa e não uma lista de perdão, na forma do `SEM_CHAMADOR`:
`test_toda_isencao_ainda_importa_toolkit` exige que quem está isento **continue** importando toolkit,
senão a isenção envelhece apontando para um arquivo que já não precisa dela.

### Critério de aceite

- `violacoes(ui/)` devolve `{}`, e a mensagem de falha nomeia módulo, linha e o que ele importou. ✅
- `violacoes(pacote inteiro, isenções)` devolve `{}`. ✅ Medido em 2026-09-04: **nenhuma violação
  real**. Fora de `qt/`, o único arquivo do pacote que importa toolkit é `cli/texto_transcrever.py`
  (cinco imports tardios de `tkinter`, linhas 50, 51, 280, 351 e 435), isento por decisão do corte.
- A guarda **acha**: oito módulos sintéticos numa pasta temporária cobrem as seis formas de import, a
  prosa que não conta, o nome parecido que não conta (`tkinter_util`, `PyQt6Compat`,
  `chess_diagram_ocr.qtx`) e a isenção que cobre arquivo e pasta e nada mais. E, sobre a árvore
  real, a mesma função apontada para `qt/` acha o toolkit em 31 módulos. ✅
- A varredura não é vácua sobre `ui/`: mais de 45 módulos lidos, com mais imports que módulos. ✅

### Testes

- `tests/test_ui_fronteira.py::DetectorTests` (novo) -- `test_o_import_de_topo_e_acusado_com_a_linha`,
  `test_os_cinco_toolkits_sao_acusados_em_qualquer_forma`, `test_o_import_tardio_e_o_de_tipo_contam`,
  `test_o_import_relativo_do_pacote_de_desenho_e_resolvido`,
  `test_o_relativo_de_um_nivel_dentro_de_ui_nao_e_toolkit`, `test_citar_o_toolkit_na_prosa_nao_e_importa_lo`,
  `test_a_isencao_cobre_o_arquivo_e_a_pasta_e_nada_mais`, `test_um_nome_parecido_nao_e_toolkit`.
- `tests/test_ui_fronteira.py::FronteiraTests` (novo) -- `test_a_varredura_le_a_camada_pura_inteira`,
  `test_a_mesma_varredura_acha_o_toolkit_onde_ele_mora`, `test_nenhum_modulo_de_ui_importa_toolkit`
  (**o critério**), `test_nada_fora_do_pacote_de_desenho_importa_toolkit`,
  `test_toda_isencao_ainda_importa_toolkit`.
- As três guardas de antes ficam: elas afirmam módulos nomeados, e a lista `SEM_TKINTER` continua
  sendo a descrição de cada módulo puro, que esta guarda não tem.

### O que o crítico recusou

_a preencher pelo crítico_

## S-550 · As S-500 a S-506 do corte do Tk ganham seção de spec (dívida de documentação) — ✅ **implementada em 2026-09-04**

### Problema

Os identificadores S-500 a S-506 são citados em docstring de todo `qt/*.py` (`qt/__init__.py:1`, e a
partir dele cada painel), em `app_pyqt.py:1`, em 18 arquivos de `tests/`, em `pyproject.toml`,
`packaging/cvoff.spec`, `.github/workflows/ci.yml`, `CONTRIBUTING.md` e em oito `docs/*.md` -- e
**nenhum tem seção `## S-5NN`** em `docs/SPEC_*.md`. A tabela "Onde mora a spec de cada item"
(`docs/SPEC_SUITE.md:25` e as outras 26 cópias) pulava de `S-452` para `S-507`: quem lia
`(S-503)` num cabeçalho e ia à tabela não encontrava faixa nenhuma. As guardas de `tests/test_docs.py`
não acusavam porque cobram seção só de item **entregue em mensagem de commit**, e o porte inteiro
entrou no git num commit só, `653f88b`, cujo assunto não cita número.

### Solução

As sete seções abaixo, escritas a posteriori a partir do que o código, os testes e o log dizem: os
docstrings de `qt/`, o `git show 653f88b` (o corte, 2026-08-31, único commit em que `qt/` e
`app_pyqt.py` entram na história), o `810072a` do mesmo dia (a conta do catálogo, S-505) e as
narrativas de `docs/ARCHITECTURE.md` ("A escolha de framework, e como ela mudou") e
`docs/SPEC_ESTUDO_QT.md`. A data de todas é **2026-08-31**, porque é a única que o log tem: a
paridade painel a painel (S-500 a S-505) foi feita fora da história e commitada com o corte.

Elas moram **neste** arquivo, e não num `SPEC_QT.md` novo, porque documento novo em `docs/` custa três
guardas (índice do README, tabela de faixas idêntica, isenção dos `ROADMAP*`) e a S-550 é uma dívida de
documentação, não um documento. A linha da tabela passa a dizer `S-500 a S-506, S-527 a S-580`, nas 27
cópias, byte a byte.

### Critério de aceite

- Cada uma das sete tem Problema, Solução, Critério de aceite e Testes, citando testes que **existem**
  no disco de 2026-09-04. ✅
- `tests/test_docs.py` inteiro verde: a tabela de faixas é a mesma nos 27 arquivos, nenhuma célula é
  ilegível, toda seção está no arquivo que o índice declara, e nenhum número nomeia duas coisas. ✅
- Nenhuma outra seção deste arquivo foi tocada. ✅

### Testes

- `tests/test_docs.py::IndiceNaoEVacuoTests::test_todo_item_com_secao_esta_declarado_no_indice` -- é a
  guarda que passaria a reprovar as sete seções sem a faixa nova na tabela.
- `tests/test_docs.py::test_a_tabela_de_faixas_e_a_mesma_em_todos_os_documentos_que_a_trazem` -- as 27
  cópias.
- `tests/test_docs.py::test_a_secao_esta_no_arquivo_que_o_indice_declara` e
  `NumeroDeItemUnicoTests::test_nenhum_numero_de_item_nomeia_duas_coisas`.

### O que o crítico recusou

_a preencher pelo crítico_

---

# O porte para o Qt e o corte do Tk (S-500 a S-506) — escrito a posteriori pela S-550

As sete seções abaixo não têm rodada de crítica: foram reconstruídas em 2026-09-04 a partir do
código, dos testes e do log. Onde um número é citado, ele é o do commit `653f88b` ou de um teste que
existe no disco.

## S-500 · A janela em PyQt6 nasce como versão de teste sobre o mesmo `service.py` — ✅ **implementada em 2026-08-31**

### Problema

A fronteira da S-31 -- *a interface é apresentação; o que dá para testar mora no pacote* -- era uma
promessa com um cliente só. `653f88b^:app_tkinter.py` tinha 2.327 linhas e era a única janela; nada
media se `service.py`, `detection/`, `ui/page_overlay.py` e `ui/viewport.py` eram de fato
independentes do toolkit, porque nunca houve um segundo chamador. A `docs/ARCHITECTURE.md` recomendava
ficar no Tk, com a saída amarrada a dois gatilhos mensuráveis (S-53) -- e nenhum dos dois disparou.

### Solução

O pacote `src/chess_diagram_ocr/qt/` e a entrada `app_pyqt.py`, uma segunda janela sobre exatamente o
mesmo `OcrService`, **somente-leitura por decisão**: abre o livro, navega, marca os diagramas sobre a
página, lê a página e mostra o que leu -- tabuleiro, FEN, confiança, lado a jogar e legalidade -- e
para antes de gravar, porque um teste que escrevesse no `labels.csv` deixaria de ser um teste. Ela
existe para responder com código que roda três perguntas:

1. *A fronteira da S-31 aguenta outro frontend?* Sim: nada em `service.py`, `detection/`,
   `page_overlay.py` ou `viewport.py` precisou mudar para a janela nascer.
2. *Quanto da lógica de tela já estava fora do Tk?* `ui/page_overlay.py` (onde as caixas estão e o
   que um clique nelas significa) e `ui/viewport.py` (roda, zoom, "caber na página") são reusados
   inteiros; o que o pacote escreve do zero é o desenho, `QPainter` no lugar de `create_rectangle`.
3. *O que o Tk carregava sozinho?* O que não deu para reusar aparece como código novo, e é o inventário
   do que uma migração custaria.

O PyQt6 entra como **extra `qt`** do `pyproject.toml`, e `packaging/cvoff.spec` exclui `PyQt6` e filtra
`chess_diagram_ocr.qt` do `collect_submodules`, para não levar ~150 MB de Qt no `.zip` de quem não
pediu segunda janela. PyQt6 e não PyQt5 porque é o que tem roda publicada na faixa `>=3.10,<3.14`
inteira. O título da janela traz uma marca (`TITULO_DA_JANELA`), porque duas janelas do mesmo produto
lado a lado é a situação em que alguém corrige vinte diagramas na errada.

### Critério de aceite

- Nenhum módulo já existente muda para a janela nascer; `qt/` não importa `tkinter`. ✅
- A janela abre o livro, marca, lê e mostra, recebendo o serviço pronto (`servico=`) -- o que permite
  exercitar o caminho de leitura inteiro sem o `models/piece_classifier.pt`. ✅
- O `.exe` não cresce: `PyQt6` no `excludes` do `.spec` e `qt/` fora do varrimento. ✅ (invertido na
  S-506, quando a janela passou a ser esta.)

### Testes

- `tests/test_app_pyqt.py` -- `FracoesDaVistaTests` (a fração do `yview` do Tk a partir de um
  `QScrollBar`), `TabuleiroTests`, `VisorTests`, `JanelaTests` (abrir, navegar, marcar, ler, clicar na
  caixa, a roda no fim da página) e `SelftestTests`.
- `tests/test_packaging.py::SpecTests::test_o_que_nao_e_dependencia_nao_entra_no_bundle` -- a regra
  pela qual o `PyQt6` entrou no `excludes` enquanto era extra.
- `tests/test_page_overlay.py` e `tests/test_viewport.py` continuam sendo os testes das decisões
  reusadas: repeti-las em `qt/` mediria o mesmo código duas vezes.

### O que o crítico recusou

_não houve rodada: seção escrita a posteriori (S-550)_

## S-501 · O que a versão de teste repetia passa a ser chamado: tema, atalhos, rodapé, tabela, barra, menu, plataforma e tabuleiro — ✅ **implementada em 2026-08-31**

### Problema

A segunda janela repetia decisões em vez de chamá-las, e o cabeçalho de `qt/tabuleiro.py` registrava o
caso mais claro: `BoardGeometry.fit` e `heatmap_color` eram cálculo puro em
`653f88b^:src/chess_diagram_ocr/ui/board_render.py`, e mesmo assim não podiam ser importados, porque
o módulo em que moravam importava `tkinter` e `PIL` na primeira linha -- a incerteza aparecia como
**contorno** na casa em vez de calor, e `UNICODE_PIECES` existia em duas cópias byte a byte. A tabela
de atalhos de `ui/atalhos.py` escrevia tecla na linguagem do Tk (`"<Control-s>"`) e a guarda de foco
da S-20 devolvia `"break"`/`None`. E `recognize_page` rodava o detector de novo sobre a página que o
visualizador acabara de detectar para desenhar os retângulos: o log de uma sessão real mostrava
"Aparado pela moldura" duas vezes por página.

### Solução

Abrir a metade pura de cada módulo do Tk e chamá-la dos dois lados:

- `ui/desenho_do_tabuleiro.py` recebe `BoardGeometry.fit`, `heatmap_color` e `UNICODE_PIECES`, sem
  toolkit; `qt/tabuleiro.py` passa a chamá-los. A incerteza volta a ser calor, com alfa de verdade no
  lugar do `stipple="gray50"` que o canvas do Tk exigia.
- `qt/atalhos.py` **traduz** a tabela de `ui/atalhos.py` numa função pura de 20 linhas em vez de
  redeclará-la em `QKeySequence`, e a guarda vira um `eventFilter` na aplicação -- `True`/`False` é o
  mesmo par de respostas que `"break"`/`None`.
- `qt/tema.py`: a folha de estilo construída por função pura (`folha_de_estilo()`) a partir dos mesmos
  papéis de `ui/tokens.py`; aqui não há `ttkbootstrap`, então *o tema somos nós*, e o eixo de tema
  colapsa -- fica a pele, com o seu `cromo_escuro`.
- `ui/estado_do_rodape.py` (severidade, expiração, descrições) e `qt/rodape.py`; `qt/tabela.py` das
  mesmas `Coluna`; `qt/barra.py` (a barra que quebra em vez de cortar, S-151); `qt/menu.py` da mesma
  declaração (S-161); `qt/legenda.py` (`descricao_completa` passa a ser pública); `qt/plataforma.py`
  (DPI e ícone antes de a janela existir, S-148); `qt/dica.py`.
- `OcrService.recognize_page` aceita a lista de candidatos que quem chamou já detectou: marcar e
  depois ler deixa de varrer a página duas vezes, e o retângulo "3" da tela e o diagrama 3 da lista
  passam a ser o mesmo objeto por construção.

### Critério de aceite

- Nenhuma decisão em duas cópias: `UNICODE_PIECES` é um `assertIs`, e o tabuleiro das duas janelas,
  na mesma área, tem o mesmo tamanho e a mesma origem. ✅
- Nenhuma tecla escrita fora de `ui/atalhos.py`, **também deste lado**. ✅
- F4 (marcar) e depois F5 (ler) não detectam duas vezes. ✅
- A paleta, as peles e as densidades são afirmáveis sem servidor gráfico, porque a folha é texto. ✅

### Testes

- `tests/test_qt_tabuleiro.py` (`test_a_tabela_de_glifos_e_a_do_produto`, `test_a_rampa_de_calor_e_a_do_produto`,
  `test_a_geometria_e_a_do_produto` -- os três `assertIs` que fecharam o achado),
  `tests/test_qt_atalhos.py` (a tradução e "nenhuma tecla escrita fora de `ui/atalhos.py`"),
  `tests/test_qt_tema.py::FolhaDeEstiloTests`, `::PapelDoBotaoTests`, `tests/test_qt_barra.py`,
  `tests/test_qt_menu.py`, `tests/test_qt_legenda.py`, `tests/test_qt_plataforma.py`,
  `tests/test_qt_rodape.py`, `tests/test_qt_tabela.py`, `tests/test_qt_dica.py`.
- `tests/test_service.py::PaginaComCandidatosProntosTests` e
  `tests/test_app_pyqt.py::JanelaTests::test_marcar_duas_vezes_nao_varre_a_pagina_duas_vezes`.
- `tests/test_editor_model.py::SemTkinterTests` -- `desenho_do_tabuleiro.py` e `estado_do_rodape.py`
  entram em `SEM_TKINTER` com a marca `(S-501)`.

### O que o crítico recusou

_não houve rodada: seção escrita a posteriori (S-550)_

## S-502 · A janela em Qt passa a corrigir e gravar: tabuleiro editável e `Ctrl+S` — ✅ **implementada em 2026-08-31**

### Problema

A S-500 parava, de propósito, antes do que a janela do produto tinha além de ler: editar casa a casa,
salvar amostra, treinar, exportar. Aquilo era certo enquanto o pacote existia para **provar** uma
fronteira. O dono decidiu que o Qt substitui o Tk, e a decisão muda o argumento: uma janela que vai ser a
única não pode recusar o gesto mais repetido do programa -- corrigir, `Ctrl+S`, seta. O risco que a
S-500 evitava era um **segundo caminho de escrita** no `labels.csv`.

### Solução

`qt/tabuleiro_editavel.py`: clique, arrasto e pincel sobre um `BoardModel` -- o que cada gesto
*significa* (`press`, `drop`, `paint`, `erase`, e o `BoardChange` que devolve) continua sendo de
`ui/board_model.py` e `ui/board_edit.py`, e o que o widget escreve é só o roteamento do evento do Qt
para a chamada do modelo. A gravação obedece `ui/editor_model.DiagramEditorModel.save_target()` --
*amostra nova ou regravar a linha existente?*, a regra mais delicada da interface (S-49), pura e com
teste sem janela --, e é isso que atende a cautela: o que existe é um segundo widget sobre o mesmo
caminho, não um segundo caminho. O título deixa de dizer "versão de teste", porque é falso desde aqui;
o que ele precisa dizer é **qual** janela é esta, enquanto houver duas escrevendo no mesmo arquivo.

### Critério de aceite

- A correção vai para o `fen_edits` do editor, e não para o item -- ela sobrevive à ida e volta entre
  diagramas, que é o laço mais repetido do programa. ✅
- A posição gravada é a **corrigida**, e não a que o modelo leu. ✅
- A posição ilegal pergunta; o "não" cancela; a confirmada grava. Um erro no repintar depois da
  gravação não vira "falha ao salvar" sobre uma amostra que está no disco (S-318). ✅
- `mouseReleaseEvent` respeita `allow_deselect`: selecionar não exige dois cliques. ✅
- O `labels.csv` dos testes é temporário (`csv_de_rotulos=`). ✅

### Testes

- `tests/test_qt_tabuleiro_editavel.py` -- o roteamento, com `LIMIAR_DE_ARRASTO`.
- `tests/test_qt_gravacao.py::GravacaoTests` e `::VinculoTests` -- os catorze casos da gravação, do
  vínculo e da origem gravada.
- `tests/test_app_pyqt.py::JanelaTests::test_o_titulo_diz_qual_das_duas_janelas_e_esta`.
- `tests/test_editor_model.py` e `tests/test_board_model.py` continuam sendo os testes da decisão.

### O que o crítico recusou

_não houve rodada: seção escrita a posteriori (S-550)_

## S-503 · Os painéis portados um a um, e as decisões abertas em módulos puros de `ui/` — ✅ **implementada em 2026-08-31**

### Problema

Depois da S-502 a janela do Qt tinha a lista, o tabuleiro, a FEN e o salvar **embutidos** -- o mesmo
arranjo que a S-31 tirou do `ChessOcrTkApp`: com o estado do PDF, o do editor e o do estudo no mesmo
objeto, um método de navegação de página mexe no que está sendo editado sem que nada diga. E do lado
do Tk cada painel carregava decisão dentro do widget: `653f88b^:src/chess_diagram_ocr/ui/result_panel.py`
tinha 1.402 linhas; os diálogos devolviam pelo atributo `chosen`; a Galeria, o Dataset, a Revisão, a
sala de estudo e a fita decidiam medidas, colunas, tri-estados e contabilidade em código que só rodava
com uma raiz Tk aberta.

### Solução

Um widget por painel, e para cada um a metade pura aberta num módulo de `ui/` que os dois frontends
podiam chamar:

| painel (`qt/`) | decisão aberta em `ui/` |
|---|---|
| `painel_de_resultado.py` | `editor_model`, `historico`, `legality`, `board_edit` (já puros); `_atualizar_tudo` no lugar dos três `update_*` separados |
| `painel_do_pdf.py` · `visor.py` | `leitura_do_pdf.py` (os três números medidos do visualizador e o leitor do sistema, S-330) |
| `painel_da_galeria.py` | `galeria_declarada.py` (medidas, tri-estado do link, contabilidade do lote, S-67) |
| `painel_de_estudo.py` · `tabuleiro_de_jogo.py` | `sala_declarada.py` (tabela comando→método e as seis medidas, S-280) |
| `painel_do_dataset.py` | `resumo_do_dataset.py` (colunas, paginação, textos, S-23) |
| `painel_de_revisao.py` | `varredura_de_revisao.py` (o pedido e o acumulador da fila, S-116/S-119) |
| `dialogos.py` | `escolha_de_bases.py`, `escopo_da_varredura.py`, `lista_de_partidas.py` (o travessão), `pedido_de_treino.py` |
| `fita.py` · `paleta.py` · `icones.py` | `medidas_da_fita.py` (modos, orçamento, grupos), `filtro_de_comandos.py` (inventário e ordem da paleta), `ui/icones.py` |

O modal do Qt é `exec()`, e é onde os dois frontends mais divergem: a função `perguntar_*` de cada
diálogo cabe em três linhas, o atributo continua existindo para o teste, e o `Escape` fecha de graça.

### Critério de aceite

- Cada painel tem o seu `tests/test_qt_*.py` e se testa **sem abrir a janela inteira**. ✅
- `qt/painel_de_resultado.py` tem menos de um terço das 1.402 linhas de `ui/result_panel.py`, e a
  diferença é código chamado, não omitido. ✅
- Toda decisão aberta está em `SEM_TKINTER` com a marca `(S-503)` e tem teste sem janela. ✅
- A janela conversa com o painel por sinal, e não lendo o estado dele. ✅

### Testes

- `tests/test_qt_painel_de_resultado.py`, `tests/test_qt_painel_do_pdf.py`,
  `tests/test_qt_painel_da_galeria.py`, `tests/test_qt_painel_de_estudo.py`,
  `tests/test_qt_painel_do_dataset.py`, `tests/test_qt_painel_de_revisao.py`,
  `tests/test_qt_dialogos.py`, `tests/test_qt_fita.py`, `tests/test_qt_paleta.py`.
- `tests/test_editor_model.py::SemTkinterTests::test_os_doze_continuam_sem_tkinter` -- os onze módulos
  marcados `(S-503)` na lista.
- `tests/test_review_queue.py` -- o alvo do `patch` passa a ser `ui/varredura_de_revisao.py`.

### O que o crítico recusou

_não houve rodada: seção escrita a posteriori (S-550)_

## S-504 · A aba de texto no Qt: o documento é o estado, e o widget é o desenho — ✅ **implementada em 2026-08-31**

### Problema

`653f88b^:src/chess_diagram_ocr/ui/texto_panel.py` tinha 2.600 linhas, e uma parte delas existia só
para contornar o `tk.Text`: uma etiqueta do Tk dá **uma** fonte ao trecho e a última criada vence --
daí `NEGRITO_ITALICO`, daí `fonte:titulo:bi:2` gerada sob demanda, daí o cache `_fontes_desenhadas`
refeito a cada zoom, e negrito dentro de um título sumia; a pilha de desfazer do Tk guarda índice e
não conteúdo, então todo redesenho exigia `edit_reset()`; e o documento era lido **de volta do
widget**, etiqueta por etiqueta, para gravar (`ui/texto_etiquetas.de_despejo`).

### Solução

`qt/painel_de_texto.py` e `qt/texto_formato.py`. O `QTextCharFormat` guarda peso, pendor e corpo
separados, e os três contornos somem. O documento **é** o estado e o widget é só o desenho dele: toda
ferramenta chama uma função pura de `text/rico.py`, recebe um documento novo e o redesenha -- é o que
faz o negrito sobreviver ao arquivo em vez de existir só enquanto o widget existir. A fronteira
estreita é o deslocamento: as funções puras falam em caractere do *documento*, o `QTextEdit` em
posição do *cursor*, e os dois divergem porque a miniatura do diagrama vale um caractere para o Qt e
nenhum para o documento -- `_Mapa` resolve o que `ui/texto_etiquetas.deslocamento` resolvia
percorrendo o `dump` do widget a cada pergunta. `ui/texto_declarado.py` recebe a tabela
comando→método e o zoom da vista (S-240).

### Critério de aceite

- Negrito, itálico e título convivem no mesmo trecho. ✅
- O negrito aplicado depois do terceiro diagrama cai onde a pessoa clicou, e não três caracteres
  adiante. ✅
- O desfazer vê uma mudança de formato, que não altera caractere nenhum. ✅
- A aba registra as duas operações longas no `BusyRegistry`, como o painel do Tk fazia (fechado na
  S-506, que o achou). ✅

### Testes

- `tests/test_qt_texto.py` -- o formato, o mapa de deslocamento e as ferramentas.
- `tests/test_qt_texto_cauda.py` -- a cauda da aba (S-240 a S-266, S-343): o que o porte da S-502
  tinha parado antes de fazer.
- `tests/test_editor_model.py::SemTkinterTests` -- `texto_declarado.py` com a marca `(S-504)`.

**O que ficou de fora, e virou item.** A digitação no editor do Qt não chegava ao documento -- o
widget recebe o texto e `documento` fica como estava --, medido em 2026-09-02 pela triagem da S-511.
É a **S-521** ([SPEC_EDITOR.md](SPEC_EDITOR.md)), e não um defeito desta seção: o porte trouxe as
ferramentas e o desenho, e o caminho do teclado ao documento ficou para depois.

### O que o crítico recusou

_não houve rodada: seção escrita a posteriori (S-550)_

## S-505 · A janela reúne os painéis: sete abas, uma tabela de comandos, e toda ação com dono — ✅ **implementada em 2026-08-31**

### Problema

Com os painéis como widgets (S-503), o que falta é quem os ligue: a fiação entre eles, a tabela de
comandos que o menu, a paleta e os atalhos leem, e a entrada do processo. E a guarda que perguntava se
uma ação do catálogo tinha dono era satisfeita por um `lambda: None`: ela perguntava se a ação tinha
entrada na tabela, e um comando que não faz nada **tem**. Três ações do catálogo -- `anotar_pagina`,
`anotar_sem_diagrama`, `tirar_do_campo` -- eram servidas por **botões** da janela do Tk e não pela
tabela `_comandos`, então comparar as duas janelas ação a ação passava em verde sem elas; entre elas
estava o único caminho que faz `data/field_set.jsonl` crescer.

### Solução

`qt/janela.py`, `JanelaPrincipal`: monta as seis abas de trabalho ao lado do visualizador, liga sinal a
sinal e **soma as três tabelas de comandos** (a da janela, a da sala e a da aba de texto) numa só, de
onde saem o menu, a paleta e os atalhos -- a janela traduz widget em parâmetro do serviço, e nada
mais. `qt/exportador.py` (com `ui/exportacao_de_pgn.py`: `ExportSettings` e `describe_report`),
`qt/campo.py` (as três ações do conjunto de campo, com `ui/field_draft.py`) e as quatro origens do
painel de Resultado (`carregar_pagina`, `carregar_item_de_revisao`, `carregar_amostra`,
`carregar_avulsos`), cada uma declarando o vínculo que impede `Ctrl+S` de gravar pelo caminho errado.
`app_pyqt.py` é a entrada: argumentos, log, `QApplication` e o `--selftest`.

A conta do catálogo fecha em duas guardas, e a segunda é o **controle** da primeira: todo comando do
catálogo alcança o menu ou está numa das duas listas que declaram por que não; e a varredura de
inertes lê a **fonte** de `qt/janela.py` por `ast`, provada contra uma fonte de mentira -- a primeira
versão pedia `inspect.getsource` do `lambda`, caía num `except SyntaxError` e passava em verde com um
comando inerte no arquivo. É a lição que `test_ui_orfaos.py` (S-511) cita como "a trava da guarda dos
inertes".

### Critério de aceite

- As seis abas na ordem da spec; o visualizador ao lado delas e não dentro. ✅
- A tabela de comandos é a soma de três; todo item de menu tem comando; nenhum é inerte; todo comando
  do catálogo tem dono chamável nesta janela. ✅
- O detector de inertes acha um comando inerte numa fonte sintética. ✅
- A frase de todo painel chega ao rodapé; as abas dizem quanto trabalho carregam. ✅
- `qt/janela.py` entra na catraca de linhas de `tests/test_packaging.py` no lugar do
  `app_tkinter.py`. ✅

### Testes

- `tests/test_qt_janela.py::MontagemTests` -- `test_as_seis_abas_estao_na_ordem_da_spec`,
  `test_a_tabela_de_comandos_e_a_soma_de_tres`, `test_nenhum_comando_do_menu_e_inerte`,
  `test_a_varredura_de_inertes_acha_um_comando_inerte`, `test_todo_item_de_menu_tem_comando`,
  `test_todo_comando_do_catalogo_tem_dono_nesta_janela`,
  `test_as_tres_acoes_da_linha_de_campo_sao_as_do_catalogo`, `test_a_frase_de_todo_painel_chega_ao_rodape`.
- `tests/test_qt_janela.py::FiacaoTests` -- abrir o livro chega à Galeria, ao Estudo e ao Texto; a
  Revisão manda varrer e quem varre é a Galeria; gravar pinta a caixa e reconta as abas; e o resto.
- `tests/test_ui_comandos.py::CoberturaDoCatalogoTests::test_todo_comando_do_catalogo_alcanca_alguem` e
  `::test_a_conta_do_catalogo_acusa_uma_acao_sem_dono` (commit `810072a`, 2026-08-31).
- `tests/test_app_pyqt.py::SelftestTests` e `tests/test_packaging.py::TamanhoDaJanelaTests`.

### O que o crítico recusou

_não houve rodada: seção escrita a posteriori (S-550)_

## S-506 · O corte do Tk: a janela do produto passa a ser a do PyQt6 — ✅ **implementada em 2026-08-31**

### Problema

Com a paridade painel a painel fechada (S-503 a S-505), havia duas janelas escrevendo no mesmo
`labels.csv`: `653f88b^:app_tkinter.py` com 2.327 linhas, 28 módulos de `ui/` acoplados ao toolkit,
46 arquivos de teste que só rodavam com uma raiz Tk, o `ttkbootstrap` como dependência, o PyQt6 como
extra e `packaging/cvoff.spec` excluindo justamente o pacote da janela nova. O dono decidiu a migração
em 2026-08-31, e o corte saiu no mesmo dia (`653f88b`).

### Solução

- Sai `app_tkinter.py`; `ui/` vai de 81 para 52 módulos, e nenhum dos que sobram importa toolkit --
  ela é a camada pura que os dois frontends compartilhavam, e agora só tem um. Seis módulos são
  **podados** em vez de apagados, porque o Qt pede a metade pura deles: `barra`, `degradacao`,
  `folha`, `menu`, `plataforma`, `tabela`. `rodape` sai inteiro (`DESLIGADO` e `Dispositivos` sempre
  moraram em `estado_do_rodape`).
- O PyQt6 deixa de ser o extra `qt` e vira dependência de base; o `ttkbootstrap` sai do
  `pyproject.toml` e do `uv.lock`; o `cvoff.spec` aponta para `app_pyqt.py` e passa a **coletar**
  `qt/` em vez de excluí-lo. O CI para de instalar o extra.
- `data/janela.json` no lugar de `app_tkinter_state.json` -- o estado nunca foi do Tk, é da janela --,
  com o arquivo antigo lido **uma vez** quando o novo ainda não existe, porque ele guarda o histórico
  de 50 livros com a página de cada um.
- A remoção de caixa passa a usar o `DroppedBoxes` puro em vez de um conjunto de índices: ele casa por
  bbox, e índice não é identidade -- uma redetecção com outro DPI renumera tudo.
- Fica de fora, de propósito: `cli/texto_transcrever.py`, a janela Tk que transcreve as 123 faixas de
  referência da S-183 -- ferramenta de desenvolvimento com entrada própria, que não abre pelo `.exe`;
  por isso o `tkinter` não entra no `excludes` do `.spec`.

**O que o corte encontrou, e que teria sumido calado:**

1. Três ações do catálogo sem dono (`anotar_pagina`, `anotar_sem_diagrama`, `tirar_do_campo`): quem
   as acusaria era `ui/alcance.perdidos()`, que saiu no mesmo corte por perguntar sobre os três cromos
   do Tk. Portadas em `qt/campo.py`.
2. Uma confirmação perdida: as 20 perguntas modais do Tk foram listadas por `ast` e comparadas com as
   do Qt; faltava a da S-451, "Salvar todos" sobre página cujos diagramas já têm amostra. Portada.
3. **~20 guardas de varredura verdes e vazias.** Elas varriam sintaxe do toolkit (`ttk.Button`,
   `padx=`, `font=(...)`, `messagebox.ask*`, `bind("<Escape>")`, `threading.Thread(`) e nenhuma ficou
   vermelha no corte: todas passaram sobre lista vazia. Traduzidas para o Qt, acharam na hora 5
   `QPushButton` sem papel declarado, 2 hexadecimais cravados em `qt/tabuleiro.py`, um rótulo escrito à
   mão que o catálogo já tinha, o `QThread` que a varredura de threads não via, e a aba de Texto sem
   registrar as duas operações longas no `BusyRegistry`. Daí a regra que as seções seguintes repetem:
   **uma guarda de varredura tem um controle que acha e deixa de achar**.

**O que o corte custou, e é a lição.** Apagar uma camada não apaga código: apaga o **chamador** de
decisões que ficaram. Sete voltaram um mês depois (`adda88f`: estado da janela, recentes, Aparência e
Densidade, fila e fita, conjunto de peças, árbitro do `Ctrl+Z`, os códigos 1, 3, 4 e 5 do `--selftest`),
onze na triagem da S-511, o motor e o OCR de legenda na S-523 -- e nenhuma quebrava teste, porque o
teste de cada uma seguia verde medindo a decisão sozinha. A guarda que faltava é
`tests/test_ui_orfaos.py`; a que fecha a fronteira pelo outro lado é `tests/test_ui_fronteira.py` (S-549).

### Critério de aceite

- Nenhum módulo de `ui/` importa toolkit. ✅ (guarda genérica só na S-549)
- `ttkbootstrap` fora do `pyproject.toml`; `PyQt6` nas dependências de base; `collect_submodules` sem
  filtro e `chess_diagram_ocr.qt` fora do `excludes`. ✅
- `qt/janela.py` na catraca: **1.196** linhas no corte, contra as 2.327 do `app_tkinter.py` -- a
  diferença é a camada pura sendo chamada em vez de reescrita. ✅
- Cada varredura traduzida acha alguma coisa numa fonte de mentira. ✅
- Suíte no corte: 4.282 passam, 3 falham -- as mesmas três de antes (duas contagens de amostra que o
  `docs/` ainda não alcançara, e a guarda S-218, vermelha por decisão desde 2026-08-30). ✅

### Testes

- `tests/test_packaging.py::SpecTests::test_o_pacote_da_janela_entra_no_varrimento` e
  `::TamanhoDaJanelaTests` (a catraca `LIMITE`, com cada subida registrada).
- `tests/test_editor_model.py::SemTkinterTests::test_a_lista_cobre_todo_modulo_de_ui_que_hoje_dispensa_tkinter`
  -- depois do corte, **todo** módulo de `ui/` está na lista.
- As varreduras traduzidas: `tests/test_busy.py` (`ARQUIVOS_COM_THREAD` aponta para `qt/`, com
  `Tarefa(`), `tests/test_ui_estilos.py::TodoBotaoDeclaraPapelTests`,
  `tests/test_ui_texto_cor.py::SemHexadecimalTests`, `tests/test_strings.py` (`CHAMADAS` do
  `QMessageBox`), `tests/conftest.py` (`CAIXAS`), `tests/test_disciplina_da_suite.py::UmaRaizSoTests`,
  `tests/test_docs.py::test_as_threads_citadas_batem_com_as_do_codigo`.
- O que o corte achou e portou: `tests/test_qt_tema.py::DesabilitadoSeVeTests`,
  `tests/test_qt_painel_do_pdf.py::ControlesDoLivroTests`, `tests/test_qt_tabuleiro.py::ConjuntoDePecasTests`,
  `tests/test_qt_janela.py::EstadoEntreSessoesTests::test_o_estado_do_tk_e_herdado_uma_vez_e_nao_reescrito`,
  `::AparenciaTests`, `::DesfazerTests`, `::FiacaoTests::test_ler_melhor_e_ler_pagina_deixaram_de_ser_o_mesmo_comando`,
  `tests/test_app_pyqt.py::SelftestTests` (os códigos que voltaram a ter dono).

### O que o crítico recusou

_não houve rodada: seção escrita a posteriori (S-550)_

## S-551 · A coluna do tabuleiro cresce pela altura, e o divisor da sala se move — ✅ **implementada em 2026-09-04**

### Problema

Medido em 2026-09-04 a 1400×950 (`fotos/crit_r2/E_1400x950.png`): o widget do tabuleiro da sala
tinha **488×488 px** (lado desenhado 454) e a coluna esquerda **494×777**. O tabuleiro estava
limitado pela **largura**, e sobravam ~230 px de coluna vazia debaixo dele -- de y≈640 a y≈880 --
com duas frases de status flutuando no meio. A 1920×1080 o mesmo arranjo dava 616 px de tabuleiro
e **357 px** de coluna vazia.

Duas causas, e só uma é a do título:

1. **A sobra ia para os rótulos.** `qt/painel_de_estudo.py:344` (`_esquerda`) empilhava tabuleiro,
   faixa de navegação, recorte, `lbl_origem`, `lbl_status` e FEN **sem esticador**: o
   `QVBoxLayout` reparte a sobra entre os itens que aceitam crescer, e os dois rótulos ficavam com
   **79 px cada** -- daí o "flutuando". `lbl_status` ainda repete, palavra por palavra, o que a
   barra de status da janela escreve na última linha da tela.
2. **O divisor não se movia.** `self.divisor.setStretchFactor(0, 3)`/`(1, 2)` (`:249`) reparte a
   largura numa proporção fixa, e nada nunca perguntou se a altura disponível permitiria um
   tabuleiro maior.

### Solução

**A régua é pura, em `ui/sala_declarada.py`.** `lado_do_tabuleiro(largura, altura_util, minimo,
alca, minimo_da_leitura)` responde `min(altura que sobra, largura que dá para tomar)`, com o teto
de largura sendo o que resta depois de a coluna de leitura ficar com o piso dela. O tabuleiro é
quadrado, então ele é limitado pelo menor dos dois recursos -- e a aba Estudo é **mais alta que
larga em toda janela medida**, o que faz o teto de largura ser quase sempre quem manda.

**O piso da leitura é o que impede a resposta óbvia e errada.** `LARGURA_MINIMA_DA_LEITURA = 210`
é somado das partes, como `galeria_declarada.LARGURA_MINIMA_DA_GALERIA`: ~105 px de um lance duplo
por extenso (`12. Bxf7+ Kxf7`, a unidade que `PAPEIS_COLADOS` não deixa quebrar), 72 px de recuo
máximo de variante (`RECUO_POR_NIVEL` × `NIVEL_MAXIMO_DE_RECUO`) e ~33 px de moldura, recheio e
barra de rolagem. Sem ele, "cresça até a altura" daria o tabuleiro inteiro e uma coluna de lances
de 46 px -- foi o que a primeira conta deste item produziu a 1400×950.

**`fracao_para_o_tabuleiro` só empurra a alça para a direita**, e essa é a parte que não é
aritmética: ela devolve `max(fracao_atual, a calculada)`. O arranjo que já está na tela é o piso.
Sem isso a mesma conta *encolheria* o tabuleiro em toda janela estreita -- a 1400×950 o teto de
largura dá 481 px contra os 494 que os pesos do `QSplitter` já davam, e o item que pediu um
tabuleiro maior o teria deixado 13 px menor.

**Quem executa é `PainelDeEstudo._acomodar_o_tabuleiro`**, chamado do `resizeEvent`. Ele mede a
altura livre somando o que os vizinhos do tabuleiro pedem -- e o **recorte escondido não conta**,
que é a diferença que explica metade da foto do crítico: com um diagrama do livro aberto e o
recorte ligado, os 220 px de `LADO_DO_RECORTE` ocupam justamente aquele vazio. A regra **não roda**
depois de a pessoa arrastar a alça (`splitterMoved`) nem depois de `posicionar_divisor` restaurar a
da sessão anterior: ali a repartição já foi escolhida -- pela pessoa, ou pela própria regra na
primeira abertura, cujo resultado a janela gravou --, e uma fração acompanha a largura sozinha
porque é fração e não pixel.

**E a sobra deixou de ir para os rótulos**: um esticador antes do campo de FEN. O bloco fica colado
no tabuleiro e a FEN vira o rodapé da coluna, alinhada com o fim da caixa de comentário ao lado; o
vazio deixa de ser texto solto e passa a ser margem, que é o que ele é.

### Critério de aceite

- **Os rótulos param de flutuar.** ✅ Medido a 1400×950: `lbl_origem` e `lbl_status` foram de
  **79 px cada para 16**, e a faixa de navegação continua colada no tabuleiro (S-517).
- **O divisor se move quando há largura para tomar.** ✅ Medido a 1920×1080: `[622, 256]` →
  `[668, 210]`, o widget do tabuleiro de **616 para 662 px** (lado desenhado 582 → 628, **+46**) e
  a coluna vazia sob ele de **357 para 90 px**.
- **A 1400×950 o tabuleiro não cresce, e o número diz por quê.** ✅ A coluna de leitura já tem
  **203 px**, abaixo do piso declarado de 210: não há largura para tomar, e a régua recusa em vez
  de espremer a lista de lances. O que muda ali é o vazio, de ~230 px de rótulos esticados para
  **134 px** de margem entre o status e a FEN -- e 38 px do que sobrava viraram o cabeçalho da
  S-530. A largura da aba Estudo a 1400 é 702 px porque `LARGURA_MINIMA_DAS_ABAS` (720) é o piso do
  lado esquerdo da janela; o que destrava mais tabuleiro nessa janela é a S-552.
- **A leitura nunca fica abaixo do piso.** ✅ Afirmado varrendo a altura até 1600 px.
- **Arrastar a alça desliga a regra**, e a fração guardada também. ✅
- Numa janela baixa o tabuleiro encolhe pela altura em vez de ser cortado: a 1024×768 o widget é
  488×434 e o lado desenhado 400. ✅
- Nada disso mexe em `ui/board_render.py` nem na esteira da S-449/S-507: `BoardGeometry.fit`
  continua a mesma conta, e o que mudou foi a caixa que ela recebe. ✅

### Testes

- `tests/test_ui_sala_declarada.py` (novo, puro): com altura de sobra quem manda é a largura; com
  altura curta quem manda é a altura; nunca abaixo do piso do próprio tabuleiro; o piso da leitura
  é respeitado e é somado das partes; a fração devolve o lado calculado; **ela só empurra para a
  direita** (o caso de 1400×950, com o número); a 1920×1080 ela de fato move (e o teste carrega os
  662 px); nunca passa de 1,0 nem fica negativa; sem largura devolve a de agora -- antes do
  primeiro `show` o `QSplitter` não tem largura, e dividir por zero ali poria a alça num lugar que
  a janela nunca pediu.
- `tests/test_qt_painel_de_estudo.py::TabuleiroNaColunaTests` (novo): a sobra de altura não vai
  para os rótulos; a faixa de navegação continua colada no tabuleiro; com altura de sobra a alça se
  move e o tabuleiro cresce; a leitura nunca fica abaixo do piso; arrastar a alça desliga a regra;
  a fração guardada também.

### O que o crítico recusou

_a preencher pelo crítico_

## S-552 · A janela cabe em 1024 px de largura — ✅ **implementada em 2026-09-04** (o que resta é uma linha de `qt/janela.py`)

### Problema

Pedida a `1000×800`, a janela ficava em **1245×902**. Medido em 2026-09-04, e o pior não estava no
pedido: **depois de ler uma página o piso subia para 1245×1218** -- mais alto que a tela inteira de
um notebook de 1366×768, e sem volta na sessão. O ChessBase e o Lichess funcionam a 1024 px.

A cadeia, medida elo a elo com `probe_minimos.py`:

| elo | pedia | quem declara |
|---|---|---|
| `LARGURA_MINIMA_DAS_ABAS` | 720 px | `qt/janela.py:152` |
| `LARGURA_MINIMA_DO_VISOR` | 520 px | `qt/janela.py:159` |
| a aba Galeria | **711 × 800** | `qt/painel_da_galeria.py` (S-154) |
| a aba Resultado, com a tela vazia | 301 × 551 | `qt/painel_de_resultado.py` |
| a aba Resultado, **depois de ler uma página** | 301 × **1095** | idem |
| o painel do PDF | 175 × 178 | `qt/painel_do_pdf.py` (a S-528 o levou a 198 × 146) |

Os dois primeiros somam `720 + 520 + 5` de alça = **1245**, e explicam a largura inteira. A altura
vinha da aba mais alta: 800 px da Galeria davam 902 na janela; os 1095 do Resultado davam 1218.

O 1095 é um defeito por si: `detalhes` é um `QLabel` com `wordWrap`, e um rótulo que quebra linha
responde a **altura mínima calculada para a largura mais estreita possível**. Quanto mais o
reconhecimento tem a dizer, mais alta a janela é obrigada a ser.

### Solução

**A metade perdida da S-150.** O docstring de `ui/geometria.PISO_MEDIDO` ainda descrevia as duas
metades daquele item: *"a altura de 800 não cabe num notebook de 1366×768, e por isso o piso
sozinho nunca foi o item. Ela é o que o conteúdo precisa **sem rolagem**; quem fecha a lacuna é a
segunda metade da S-150, `ui/rolagem.py` -- Resultado, Configuração e Galeria rolam
verticalmente"*. `ui/rolagem.py` era do Tk, saiu no corte (S-506), e **nada ocupou o lugar dele**:
não havia um `QScrollArea` em painel nenhum do Qt.

`qt/rolagem.py` (novo, uma função) põe o corpo de um painel dentro de um `QScrollArea` com
`setWidgetResizable(True)`, e `qt/painel_de_resultado.py` e `qt/painel_da_galeria.py` passam a
montar dentro dele. **O painel continua sendo o widget que a janela conhece** -- `qt/janela.py`
adiciona `self.painel` e `self.galeria` às abas pelo nome, e nada lá muda; quem pergunta ao painel
por `campos_de_header`, `tabuleiro` ou `detalhes` continua recebendo os mesmos objetos.

**Encolher o conteúdo foi recusado.** Os 420 px do recorte da galeria e os 260 da lateral são
medidos (S-154) e os detalhes do reconhecimento são o que a pessoa lê para decidir se aceita a
leitura: cortar qualquer um dos dois seria trocar um defeito de janela por um de produto. O que
muda é que o painel deixa de **exigir** a altura dele da janela -- ele a pede ao viewport, e o que
passar vira rolagem.

**A S-528 ajudou de graça:** o cromo do painel do PDF caiu de 176 para 32 px na coluna estreita, e
com ele o piso de altura daquele lado.

### Critério de aceite

- **A altura cabe numa tela de 768.** ✅ Medido: `janela.minimumSize()` foi de **902 → 553** px
  (574 com um livro aberto), e **ler uma página não muda mais o piso** -- era 1218.
- Nenhuma aba pede mais altura do que a tela mínima tem. ✅ Galeria `711×800 → 54×54`; Resultado
  `301×551` (1095 depois de ler) `→ 54×54`. As demais são Estudo 399×451, Revisão 131×436,
  Dataset 516×288 e Texto 149×132.
- O conteúdo não encolheu: o recorte da galeria continua com `BOARD_VIEW_SIZE` px, e a lateral com
  `LARGURA_DA_LATERAL`. ✅ Nas larguras em que não cabem, a área rolável mostra as barras.
- **A largura de 1024 depende de uma linha que este item não toca, e a distância está medida.**
  ✅/⚠ O piso de largura continua sendo `LARGURA_MINIMA_DAS_ABAS + LARGURA_MINIMA_DO_VISOR + alça`
  = **1245 px**, e os dois são literais de `qt/janela.py`, que outro executor está reescrevendo
  nesta sessão. **Debaixo deles não sobrou mais nada segurando a janela**: o que os painéis de
  fato pedem, medido com as fontes de verdade, é `522` (a aba mais exigente, Dataset) `+ 198` (o
  painel do PDF) `+ 5` = **725 px**.

  Provado sem alterar arquivo nenhum (`probe_1024.py`, que troca as duas constantes em memória
  antes de a janela ser montada): com `LARGURA_MINIMA_DAS_ABAS = 500` e `LARGURA_MINIMA_DO_VISOR =
  440`, a janela pedida a 1024×768 **abre exatamente em 1024×768**, com piso de `955×553`, divisor
  em `[500, 519]`, e as seis abas desenhando -- Galeria e Resultado com rolagem, as outras sem.
  Foto: `fotos/exec_fase80/mil24/cedido_*.png`; o estado de hoje, `mil24/como_esta_*.png`
  (1245×768).

  **A linha para quem mexer em `qt/janela.py`:** baixar os dois literais para 500 e 440 fecha o
  item. Os 720 vinham de `galeria_declarada.LARGURA_MINIMA_DA_GALERIA` (420 + 260 + 40), que agora
  é o tamanho **preferido** da galeria e não mais o exigido; os 520 do visor eram "abaixo disso a
  página não cabe nem no ajuste à largura", e o próprio painel responde 198.
- `ui/geometria.piso_da_janela` continua somando das partes e continua **acima** de 1024 --
  justamente por causa dos dois literais --, e há um teste que falha quando isso deixar de ser
  verdade, pedindo a atualização desta seção. ✅

### Testes

- `tests/test_qt_tamanho_da_janela.py` (novo): a Galeria rola em vez de exigir 800 px de altura, e
  o recorte medido da S-154 continua inteiro; **o Resultado não cresce de piso quando o texto
  cresce** (o `detalhes` recebe 60 frases e o `minimumSizeHint` não se mexe); a altura mínima da
  janela cabe em 768; nenhuma aba exige mais altura do que a tela tem; as duas abas que seguravam
  o piso não o seguram mais; o piso de largura é o dos dois literais, **e o teste falha quando
  alguém os baixar** ("os dois literais couberam em 1024: atualize a spec da S-552"); pedida
  pequena, a janela encolhe até o piso e não mais.
- A largura das abas **não** é medida em número absoluto: sob `offscreen` não há a fonte da
  interface e todo widget de texto mede mais -- a aba Dataset responde 842 px no teste e 516 na
  janela de verdade. A régua é a constante declarada (`LARGURA_MINIMA_DA_GALERIA`), e não um
  pixel de tela.
- `tests/test_qt_painel_de_resultado.py` e `tests/test_qt_painel_da_galeria.py` passam sem
  alteração: a área rolável não mudou o que qualquer um deles pergunta.

### O que o crítico recusou

_a preencher pelo crítico_

## S-553 · O foco de teclado se vê — ✅ **implementada em 2026-09-04**

### Problema

**O crítico pôs o foco num botão da barra da sala e fotografou: `hasFocus() == True`, e o desenho
saiu com `0 px` diferentes do não focado.** No primário, no comum e no só-ícone, nas duas peles que
ele mediu (`fotos/crit_r2/foco/foco.txt`; as fotos são
`classica_estudo_do_diagrama_foco.png` × `_semfoco.png` e as duas irmãs). São **12 paradas de
`Tab`** naquela fila -- os cinco `QToolButton`, o tabuleiro, os quatro botões de navegação, o campo
e o texto --, e nenhuma delas dizia onde o teclado estava. É a WCAG 2.4.7 AA; o ChessBase e o
Lichess desenham anel de foco.

**A causa tem duas metades, e as duas foram medidas.** A primeira está em
`qt/tema.py:450` (antes deste item): `QToolButton { … border: 1px solid transparent; … }` -- a
moldura transparente que a S-527 pôs ali para que ligar a cor de um estado não movesse o conteúdo.
Uma borda vinda de folha de estilo **substitui** o retângulo de foco que o estilo da plataforma
desenharia, e nenhuma regra `:focus` existia no arquivo inteiro (a busca por `:focus` em
`qt/tema.py` devolvia zero linhas).

A segunda metade é que **não havia de quem herdar o anel**. Medido aqui sob `offscreen`, com a
folha vazia: `QToolButton`, `QPushButton`, `QComboBox`, `QCheckBox` e `QListWidget` saem com `0 px`
de diferença entre focado e não focado; só o `QLineEdit` (436 px) e o `QSpinBox` (550 px) desenham
alguma coisa, e é o quadro de destaque do `fusion`. Com a folha do produto até esses dois caem para
12 px (o cursor de texto piscando) e 136 px. Ou seja: a folha apaga o pouco que havia, e onde não
havia nada ela não tinha o que apagar.

### Solução

**Uma regra `:focus` por classe, e o anel é a moldura que já existe trocando de cor.**
`tema.CONTROLES_COM_ANEL_DE_FOCO` são as oito classes que a folha já desenha com 1 px de borda --
`QPushButton`, `QToolButton` e as seis de `CONTROLES_COM_MOLDURA` (S-522) --, e é justamente por
já terem a moldura que o anel **não custa um pixel de layout**: nem `padding` novo, nem
`border-width` maior, que moveriam o conteúdo a cada `Tab`.

**`outline` foi medido e não serve.** Com `outline: 1px solid` (com e sem `outline-offset`) o
`QToolButton` continua desenhando **0 px** de diferença; o `QPushButton` muda 64. O Qt não o aplica
a todo controle, e um anel que existe em metade da fila é pior que nenhum -- quem usa o teclado
aprende a não procurá-lo.

**A cor do anel é a letra que já se lê sobre aquela face** (`tema.anel_de_foco`, pura). Sobre o
cromo -- botão comum, botão de ferramenta chato, campo, lista -- é `TEXTO_PADRAO`; sobre a face de
ênfase -- primário e destrutivo -- é `TEXTO_SOBRE_ENFASE`. Nenhum papel novo em `ui/tokens.py`: as
duas tintas já são obrigadas a se ler ali (a segunda passa `AA_TEXTO` sobre as duas faces por
medição da S-444), e um décimo papel para dizer "a cor do anel" seria a mesma cor com dois donos --
o defeito que a S-145 fechou.

**Como o anel se distingue do marcado, que é a decisão que o item tinha de tomar.** O
`QToolButton:checked` se diz por **duas** coisas (S-527): a face funda e uma moldura na cor de
ênfase. O anel usa a letra, que **nunca** é a cor de ênfase -- e a regra `:focus` vem por último na
folha de propósito, porque `QToolButton:focus` e `QToolButton:checked` têm a mesma especificidade e
em QSS o empate é desfeito pela ordem. Resultado: o marcado e focado mostra o foco na moldura e
continua dito pela face, que a regra do foco não toca. Os quatro estados do interruptor ficam
distintos aos pares, e é isso que o teste mede.

**A `QCheckBox` e a `QRadioButton` ficam de fora, e é decisão registrada.** Elas não têm moldura na
folha, então o anel exigiria declarar uma -- e a S-522 mediu o que uma propriedade de caixa nova
faz no `windows11`: o estilo para de pintar o cromo nativo daquele widget. No botão isso custou a
borda, que a folha repôs; na caixa de seleção o cromo nativo é o **indicador**, que é o que se
precisa ver. Trocar um anel por uma caixa sem quadradinho seria caro demais, e esta máquina não tem
como fotografar o estrago (sob `offscreen` o `fusion` desenha o indicador com folha e sem folha). O
motivo está escrito em `CONTROLES_COM_ANEL_DE_FOCO`.

### Critério de aceite

**Antes → depois, pixels diferentes entre focado e não focado**, no mesmo botão, sob `offscreen`
(botão de 48×28, folha do produto aplicada):

| pele | só-ícone | primário | comum (`QPushButton`) |
|---|---|---|---|
| Clássica | **0 → 132** | **0 → 132** | **0 → 132** |
| Foco | **0 → 132** | **0 → 132** | **0 → 132** |
| Fita (compacta) | **0 → 128** | **0 → 128** | **0 → 128** |

**E o resto do elenco, no mesmo desenho:** `QComboBox` 0 → 218, `QLineEdit` 12 → 232, `QSpinBox`
136 → 356, `QListWidget` 0 → 216, `QTextEdit` e `QPlainTextEdit` 12 → 228. `QCheckBox`,
`QRadioButton` e `QTabWidget` continuam em 0, pelo motivo acima.

**Refeito na janela de verdade**, no `windows11`, a 1400×950, nos botões que o crítico fotografou
(`scratchpad/fotos/exec_s553_s554/`): `estudo_do_diagrama` (primário, com texto) **0 → 362 px**,
`promover_variante` (só-ícone) **0 → 116 px**, `modo_treino` (interruptor só-ícone) **0 → 232 px**
na clássica e na "Foco"; 342, 104 e 212 na fita, que é compacta.

**O anel se vê contra toda face em que é desenhado** (razão WCAG, piso `AA_GRAFICO` = 3,0):

| pele | anel | superfície | botão parado | marcado | primário | destrutivo |
|---|---|---|---|---|---|---|
| Clássica e Fita | `#000000` / `#ffffff` na ênfase | 18,43 | 16,21 | 10,36 | 6,44 | 8,79 |
| Foco | `#e9eaec` / `#141013` na ênfase | 13,41 | 11,47 | 6,61 | 7,81 | 5,71 |

**E não é a cor que diz "marcado"**: o anel é a letra e a moldura do marcado é `BOTAO_PRIMARIO` --
`#000000` contra `#0a58ca` na clássica, `#e9eaec` contra `#6ea8fe` na "Foco". Duas cores diferentes
sobre duas faces diferentes; os quatro estados do interruptor (parado, marcado, focado, marcado e
focado) desenham diferente dois a dois, medido.

**O layout não se move**: `pixels_diferentes` levanta quando os dois desenhos têm tamanhos
diferentes, e toda regra `:focus` da folha é conferida por expressão regular contra
`^border: 1px solid #rrggbb; \}$` -- nada de `padding`, nada de largura nova.

### Testes

- `tests/test_qt_tema.py::AnelDeFocoTests` -- as oito classes declaram o anel nas três peles; a
  regra é só a moldura de 1 px (o teste recusa `padding` e largura nova); o anel passa
  `AA_GRAFICO` contra as quatro faces; ele nunca é a cor de ênfase; **focado desenha diferente de
  não focado** no só-ícone, no primário e no comum, nas três peles; e os quatro estados do
  interruptor são distintos aos pares.
- `tests/test_qt_barra_da_sala.py::BarraQueSeLeTests::test_o_foco_se_ve_no_primario_e_no_so_icone_nas_tres_peles`
  -- o mesmo, na fila de verdade, com o papel de verdade, no botão que o crítico fotografou. O
  botão só-ícone é escolhido da tabela (`principais` sem `com_texto`, com ícone, papel neutro) e
  não escrito à mão: um nome literal viraria um teste que mede outra coisa no dia em que aquela
  ação ganhar rótulo.
- `tests/qt_app.py` ganhou `renderizar`, `pixels_diferentes`, `cor_em` e `tinta` -- a régua num
  lugar só, pela razão de `aplicacao()`. `tests/test_qt_tabuleiro.py` passou a importar
  `renderizar` de lá em vez de declarar o seu.

**A armadilha que custou a primeira versão do teste**: mostrar o quadro dá o foco ao primeiro filho
focável, e a fotografia "de repouso" saía já focada -- `0 px` de diferença, verde no defeito e
verde na correção. `_sem_foco` chama `clearFocus` e **afirma** que o botão o largou. É a memória
`Foco do Qt vaza entre testes` cobrada por asserção.

### O que ficou de fora

- **`QCheckBox`, `QRadioButton` e `QTabBar::tab`**, pelo motivo escrito acima: o anel delas
  exigiria uma propriedade de caixa nova, e a S-522 mediu o que isso custa no `windows11`.
- **A espessura.** O anel é de 1 px porque é a moldura que já existe; 2 px exigiriam devolver um
  pixel de `padding` em cada um dos três seletores que declaram recheio de botão, e o recheio é
  derivado da fonte e da densidade (`_escalado`) -- seria uma segunda conta para manter.
- **Nada foi medido no `windows11`.** A correção é uma regra de folha, que os dois estilos leem
  igual; o que só a máquina de quem usa pode dizer é se o anel de 1 px é bastante para o olho.

### O que o crítico recusou

_a preencher pelo crítico_

## S-554 · O ícone desabilitado apaga também na pele escura — ✅ **implementada em 2026-09-04**

### Problema

**Na pele "Foco" o botão só com ícone desabilitado saía idêntico ao habilitado.** O crítico mediu a
tinta contra a face nos dois estados de `promover_variante` (`fotos/crit_r2/desab/desab.txt`, fotos
`foco_promover_on|off.png`): luminância média do traço **0,5659 nos dois**, **39 pixels de traço
nos dois**, razão WCAG **9,47 ligado e 9,47 desligado**. Na clássica funcionava -- 5,65 contra
3,23, com 39 e 38 pixels --, e é por isso que ninguém tinha visto.

**A consequência é um critério de aceite vácuo.** **Onze dos catorze** botões da fila da sala são
só-ícone, e o critério da S-527 -- *"Variante e Exportar ficam cinza sem estudo"* -- é sobre
exatamente esses. Numa das três peles ele não media nada.

**A causa: quem apagava o ícone era o Qt, e o Qt apaga clareando.**
`qt/tema.py:538` declara `QToolButton:disabled { color: … }` (e `:440` o do botão comum), e `color`
vale para o **texto**. O desenho vem do `QIcon`, e `qt/icones.py:91` registrava um pixmap só --
`addPixmap(desenho, QIcon.Mode.Normal, QIcon.State.Off)`. Um `QIcon` sem pixmap para
`QIcon.Mode.Disabled` manda o estilo gerar um: `QCommonStyle` remapeia os tons contra a `QPalette`
e desloca para o claro. Numa paleta clara, clarear é apagar; **numa escura, clarear é destacar**.
Reproduzido aqui sob `offscreen`, tinta mais forte contra a face: na "Foco" ela **subia** de 13,41
para 14,03 ao desabilitar.

E não é defeito da barra da sala: `qt/barra_da_sala.py:225` (`_pintar_icones`) já pinta o ícone na
cor do papel e o repinta na troca de pele -- ele faz o certo para o estado **ligado**. O que
faltava era o estado desligado existir como desenho.

### Solução

**O ícone desabilitado passa a ser desenhado, e não gerado.** `qt_icones.icone()` registra um
segundo pixmap para `QIcon.Mode.Disabled`, do mesmo traço, na cor que `PAPEL_APAGADO`
(`tokens.TEXTO_SECUNDARIO`) resolve contra a pele em uso -- que é **exatamente** a cor com que
`QToolButton:disabled` e `QPushButton:disabled` já pintam a letra ao lado. Ícone e rótulo apagam
juntos porque apagam pela **mesma** decisão, e não por duas que hoje concordam.

**A decisão é perguntada ao tema e não recebida do chamador** (`qt_icones.tinta_apagada`). Ligado,
o ícone carrega o papel do botão -- o primário desenha na letra da ênfase, o destrutivo no vermelho
--, e é o chamador quem sabe disso; desligado não há papel a carregar, a folha pinta os três com a
mesma tinta, e quatro chamadores repetindo a escolha seria o primeiro deles a esquecê-la.

**Vale para a janela inteira, e é por isso que mora em `qt/icones.py`.** Os quatro lugares que
põem ícone em botão passam por esta função: a barra da sala (`qt/barra_da_sala.py:223`), a fila
(`qt/fila.py:88`), a fita (`qt/fita.py:316`) e a navegação da sala de estudo
(`qt/painel_de_estudo.py:277`). Nenhum deles precisou mudar.

**A tinta apagada entra na chave do cache.** Ela vem da pele, e dois desenhos do mesmo traço na
mesma cor de traço podem apagar para cinzas diferentes; devolver o guardado daria um ícone que
apaga na cor da pele anterior. E um traço que não se consiga desenhar continua servindo: o `QIcon`
sai só com o pixmap ligado, e o Qt gera o dele -- que é o estado de antes deste item, e não uma
exceção (regra 4 da `SPEC_APARENCIA`).

### Critério de aceite

**Razão WCAG da tinta mais forte do traço contra a face do botão**, no botão só-ícone da fila, sob
`offscreen`. "Antes" é o `QIcon` gerado pelo Qt; "depois" é o pixmap próprio:

| pele | ligado | desligado **antes** | desligado **depois** |
|---|---|---|---|
| Clássica | 18,43 | 5,60 | **6,54** |
| Foco | 13,41 | **14,03** *(sobe)* | **7,14** |
| Fita | 18,43 | 5,60 | **6,54** |

A coluna que importa é a do meio: na "Foco" o desligado tinha **mais** contraste que o ligado, e é
o defeito inteiro. Depois, a tinta cai nas três peles -- e cai para o valor exato de
`TEXTO_SECUNDARIO` resolvido naquela pele (`#555555` a 6,54:1 na clara, `#a7adb6` a 7,14:1 na
escura), que é a letra que a folha desenha ao lado.

**Refeito na janela de verdade** (`windows11`, 1400×950, `scratchpad/fotos/exec_s553_s554/`), no
`promover_variante` que o crítico fotografou: a tinta mais forte sai de `#000000` a 18,43:1 para
`#555555` a **6,54:1** na clássica e na fita, e de `#e9eaec` a 13,41:1 para `#a7adb6` a **7,14:1**
na "Foco" -- 69 pixels diferentes entre ligado e desligado, onde antes a razão não se movia.

**Os três papéis apagam para a mesma tinta**, medido nos três botões da fila que os carregam
(`estudo_do_diagrama`, `seguir_ocr`, `apagar_variante`), nas três peles: a tinta desligada é
**sempre** `tinta_apagada()`. O primário é o que mais muda -- a face de ênfase vira a superfície, e
os pixels de tinta caem de 8.265 para 1.291.

**E há uma exceção de leitura, que fica registrada.** No **destrutivo** o que apaga não é o valor,
é a **matiz**: `BOTAO_DESTRUTIVO` na pele "Foco" já vale 4,89:1 contra a superfície, menos que os
7,14 do cinza, então a razão *sobe* ao desabilitar (na clássica ela cai, 7,72 → 6,54). O que o olho
lê ali é o vermelho de "isto apaga trabalho" sumindo e o botão virando um cinza igual aos vizinhos
-- exatamente o que o rótulo dele faz, pela mesma regra da folha. Cobrar queda de razão no
destrutivo obrigaria a inventar um cinza mais fraco só para ele: uma segunda tinta de desabilitado,
que é a divergência que este item veio fechar. A queda de razão é cobrada no **neutro**, que é o
papel de onze dos catorze botões, e a igualdade de tinta é cobrada nos três.

**E o desenho muda**: ligado e desligado deixam de ser o mesmo pixmap (`pixmap(…, Mode.Disabled)`
difere de `pixmap(…, Mode.Normal)`), e o botão renderizado difere em pixels nas três peles e nos
três papéis.

### Testes

- `tests/test_qt_icones.py::IconeDesabilitadoTests` (arquivo novo -- `qt/icones.py` não tinha
  teste próprio): o `QIcon` leva o desenho desligado junto; **a tinta apagada é a mesma que a folha
  dá à letra** de `QToolButton:disabled` e `QPushButton:disabled`, nas três peles; o botão só-ícone
  renderizado apaga nas três peles (pixels mudam **e** a razão da tinta cai, e a tinta desligada é
  exatamente a de `PAPEL_APAGADO`); a pele faz parte da chave do cache; e nome desconhecido
  continua devolvendo `None`.
- `tests/test_qt_barra_da_sala.py::BarraQueSeLeTests::test_o_botao_desabilitado_apaga_o_icone_nas_tres_peles`
  -- o mesmo na fila de verdade, com a ação desabilitada pelo caminho normal
  (`QAction.setEnabled`), nos **três** papéis: a tinta desligada é a mesma nos três, e a queda de
  razão é cobrada no neutro (ver a exceção do destrutivo, acima). O teste também afirma que a fila
  ainda tem um botão de cada papel -- sem isso ele passaria a medir dois papéis em silêncio.
- A régua da tinta é `qt_app.tinta`, e ela usa `tokens.razao_de_contraste` -- a do produto (S-146).
  Uma segunda conta de WCAG escrita no teste poderia discordar da que a paleta usa para se aprovar.
  Ela mede a tinta **mais forte** e não a média: o traço de um ícone de 16 px tem meia dúzia de
  pixels cheios e o resto é antialiasing, e uma média mede quanta tinta há em vez de qual é a tinta.

### O que ficou de fora

- **`QIcon.Mode.Active` e `QIcon.Mode.Selected`** continuam com o desenho que o Qt gera. O item é o
  desabilitado, que é o que carrega significado ("esta ação não existe agora"); o ícone sob o
  ponteiro já muda pela face que `QToolButton:hover` pinta.
- **O `QIcon` só declara `State.Off`**, como antes. O botão marcado usa o mesmo traço, e o `Qt`
  resolve a falta de `State.On` caindo no que existe -- comportamento de sempre, não tocado aqui.
- **A letra desabilitada não mudou de cor.** Ela já era `TEXTO_SECUNDARIO` desde a S-506/S-520; o
  que faltava era o ícone concordar com ela.

### O que o crítico recusou

_a preencher pelo crítico_

## S-580 · O fim da faixa reservada — não é item

A mensagem do commit `eb3ba71` cita a faixa "S-527 a S-580", e a guarda `test_todo_item_entregue_tem_secao_em_algum_doc` lê
números em mensagem de commit como entrega. Esta seção existe para dizer que **S-580 é o limite superior da
reserva**, e não um item: quando a faixa for ocupada até aqui, o número recebe a seção de verdade e este parágrafo sai.
