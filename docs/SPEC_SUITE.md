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

## S-528 · A barra do painel do PDF na mesma gramática, e a página com mais área — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-529 · O painel do motor: barra de avaliação vertical, linhas MultiPV clicáveis, profundidade — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-530 · O cabeçalho da partida (jogadores, Elo, evento, data, resultado) visível e editável — ◻ em andamento

_Seção a escrever pelo executor do item._

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

### Critério de aceite

Todas as medições de busca sobre o índice v5 da **`LumbrasGigaBase_OTB_Complete.pgn` inteira**
(8,6 GB, 10.355.488 partidas), melhor de três, em 2026-09-04:

| busca | tempo | o que voltou |
|---|---|---|
| Carlsen | **30 ms** | 5.141 partidas |
| Carlsen × Anand | **56 ms** | 140 partidas |
| evento "Tata Steel" | **77 ms** | 5.133 partidas |
| Elo ≥ 2700 em 2019 | **44 ms** | 1.989 partidas |
| ECO B90 | **37 ms** | mais de 100.000 partidas |
| Carlsen · 2019 · Elo ≥ 2700 · B90 | **52 ms** | 5 partidas |

- Cada uma **< 1 s** com o índice em dia. ✅ (a mais lenta é 77 ms, 13× dentro do orçamento)
- O índice da gigabase inteira: **611 s (10,2 min) e 1.764 MB**, contra 431 MB na v4 -- o preço de
  treze colunas e seis árvores no lugar de três colunas e uma.
- A janela não trava com dez milhões de partidas: a consulta roda numa `Tarefa`, e o teste afirma
  que ela **começou sem ter terminado** -- o que uma thread faz e uma chamada direta não. ✅
- Um índice de outra versão, ausente ou em obras vira frase **com instrução**, e não tabela vazia. ✅
- Paginação estável: a página seguinte não repete a anterior, e a anterior volta igual. ✅
- Formulário malfeito não vira consulta, e a frase diz **quais** campos. ✅
- `qt/janela.py` não foi tocado. ✅

### Testes

- `tests/test_ui_busca_de_partidas.py`: `de_campos` (vazio ≠ malfeito, nada consertado calado, todo
  campo do `Filtro` alcançável pelo formulário); `problemas` (sem filtro que estreite; cada campo
  com árvore basta sozinho; ano fora da faixa e invertido; ECO que não é código e faixa invertida;
  resultado que o PGN não escreve; todos de uma vez); `COLUNAS`/`linha` (as oito na ordem, Elo
  numérico, evento elástico, travessão e não zero); `resumo` (a frase do item, singular e zero,
  teto, página, os dois jogadores e a cor exigida, cada filtro na frase).
- `tests/test_games_index.py::BuscaTests`: cada filtro sobre uma base de doze partidas, sete
  jogadores, três torneios e cinco anos -- sobrenome achando as duas grafias, qualquer cor, o par
  nas duas montagens, evento por pedaço e **não** como padrão de `LIKE`, faixa de ano inclusiva, a
  partida sem data fora de toda faixa, o Elo mínimo como o menor dos dois, resultado, faixa de ECO,
  a combinação dos cinco, a ordem por data, **a partida sem data no fim e não no começo**,
  paginação, total que não é o da página, contagem no teto, a linha com o que a tabela mostra e o
  offset que abre a partida, o filtro por posição dizendo quantas examinou.
  `MigracaoDeVersaoTests`: v4 recusado com a instrução, apagado e refeito com a coluna nova; a
  versão gravada; índice em obras; índice ausente.
- `tests/test_qt_busca_de_partidas.py`: as oito colunas montadas; os quatro valores de resultado; a
  caixa da posição só com posição; a busca fora da linha de eventos; uma de cada vez; formulário
  malfeito e sem filtro que estreite não viram consulta; "nenhuma partida" com a pergunta ao lado;
  `IndiceIndisponivel` com instrução; o botão que pede o índice; paginação; duplo clique e Enter
  emitindo `(caminho, offset)`; a escolha não fecha o diálogo; falha inesperada no log **e** na
  frase, e `IndiceIndisponivel` só na frase.
- `tests/test_qt_barra_da_sala.py`: a ação da barra abre o diálogo com a janela como pai, as bases
  da sala e a posição do tabuleiro; o diálogo é reusado e a posição atualizada; sem base a frase
  diz isso; a partida que o índice não acha mais não vira meia partida. `tests/test_ui_comandos.py`
  e `tests/test_ui_barra_da_sala.py` cobram o comando novo nos dois sentidos.
- Guardas: `tests/test_editor_model.py::SEM_TKINTER` ganhou `busca_de_partidas.py`;
  `tests/test_busy.py::SEM_REGISTRO` ganhou a thread da busca com o motivo (nada é gravado, e a
  mesma pergunta se refaz com um clique); `docs/ARCHITECTURE.md` passou a contar quinze threads e a
  tabela ganhou a linha da busca.

### O que o crítico recusou

_a preencher pelo crítico_

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

### Critério de aceite

- **A tabela é a classificação padrão inteira**: 500 códigos, todo código com nome, e **toda linha
  legal desde a posição inicial** (um `push_san` que levantasse ali derrubaria a sala num
  `refresh`). ✅
- **O custo de indexar com ECO, contra a mesma v5 sem a coluna preenchida** -- medido em
  2026-09-04, com as rodadas **intercaladas** e por mínimo, porque esta máquina deriva (oito
  rodadas seguidas da mesma medição saem de 2,70 s a 3,54 s, sempre crescendo; uma primeira
  passada sequencial atribuiu a deriva à diferença e mediu +35% onde a intercalada mede +14%):

  | base | v5 sem ECO | v5 com ECO | o ECO custa |
  |---|---|---|---|
  | `Endgame_Study_Database_VI` (62 MB, 93.839 estudos, **todos com `[FEN]`**) | 7,66 s | 6,97 s | dentro do ruído (−9%) |
  | recorte de 300 MB da gigabase (366.031 partidas, **99,99% com `[ECO]`**) | 29,75 s | 25,35 s | dentro do ruído (−15%) |
  | o mesmo recorte com os `[ECO]` **removidos** (pior caso) | 27,83 s | 33,89 s | **+21,8%** (16,6 µs/partida) |
  | recorte de 30 MB do anterior, oito voltas intercaladas | 2,70 s | 3,59 s | **+32,9%** (21,9 µs/partida) |

  **O orçamento de +30% vale nos dois primeiros casos com folga, e o pior caso fica entre +22% e
  +33% conforme a rodada.** Os dois primeiros são as bases reais: numa delas a classificação
  **não roda** (toda partida tem `[FEN]`, e uma composição não tem abertura), na outra ela roda em
  0,01% das partidas. O pior caso é uma base sintética em que nenhuma partida tem `[ECO]` -- e é
  exatamente a base em que a coluna só existe porque a classificação a preenche: sem ela o filtro
  por ECO responderia zero ali, em silêncio. Medida em separado, a classificação de uma partida
  real custa **11,4 µs** (tokenizar mais consultar a árvore, sobre 40.553 partidas do recorte); o
  resto do custo de ponta a ponta são as duas linhas de movetext lidas e a árvore `games_eco` mais
  gorda.
- **A classificação por lance é duas ordens de grandeza mais barata que a por posição**, que é a
  razão de haver duas: ~1 µs contra ~0,5 ms por partida. Um replay na passada do índice seria
  +1 ms × 10 milhões ≈ três horas sobre os dez minutos da gigabase. ✅ (afirmado por teste, com
  teto de 0,05 ms por partida -- dez vezes o medido, para a guarda não virar medidor de máquina
  ocupada)
- **O header vence a tabela** no índice e na sala; a sublinha (`B90a`) é cortada para `B90`; a
  partida montada de um `[FEN]` não ganha abertura. ✅
- **A frase é `ECO B33 · Sicilian, Sveshnikov`**, com o código antes do nome, e um código que a
  tabela não conhece não ganha legenda inventada. ✅
- O filtro por ECO da S-533 acha as partidas classificadas **sem** header. ✅
- A frase da sala custa ~0,5 ms por lance, e a tabela por posição é montada uma vez (84 ms). ✅

### Testes

- `tests/test_eco.py`: `TabelaTests` (os 500 códigos das cinco letras, toda linha legal, todo
  código com nome, o nome é o da primeira linha); `ClassificarTests` (o mais profundo vence, a
  transposição chega ao mesmo código, a ordem dos lances **não** a vê, toda primeira jogada legal
  tem código, sem lance nenhum não há abertura, lance ilegal encerra a leitura, tabuleiro e
  sequência dão o mesmo, o tabuleiro montado de uma FEN não inventa abertura); `HeaderEFraseTests`
  (a sublinha cortada, o header vencendo, o código antes do nome); `MovetextTests` (números,
  resultado e NAGs fora, o lance do comentário não conta, `4... Nf6`, o roque, o teto);
  `CustoTests` (o orçamento por partida, e a comparação entre os dois caminhos -- sem ela, "há
  duas classificações" parece redundância em vez de decisão).
- `tests/test_games_index.py::ColunaEcoTests`: o header vence; sem header os primeiros lances
  classificam (e dão códigos **diferentes** para aberturas diferentes, para o valor não ser fixo);
  a sublinha cortada; a partida montada de um `[FEN]` sem abertura; e a busca por ECO achando a
  que foi classificada sem header.
- `tests/test_qt_barra_da_sala.py`: a partida aberta pela busca leva o ECO dela à faixa sob o
  tabuleiro (`ECO B90 · Sicilian, Najdorf`).
- `README.md` ganhou `eco.py` na árvore de módulos.

### O que o crítico recusou

_a preencher pelo crítico_

## S-535 · Árvore de aberturas: da posição corrente, cada lance com N, %, Elo médio e ano — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-536 · Opções do motor (Hash, Threads, MultiPV, caminho) nas preferências, sem reiniciar — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-537 · Análise de partida: cada lance avaliado, gráfico de avaliação e erros marcados — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-538 · Tablebases Syzygy quando a pasta existir: resultado exato nos finais — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-539 · Táticas do próprio acervo: FEN reconhecida + solução impressa vira exercício — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-540 · Repetição espaçada dos estudos e das táticas, com agenda do dia — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-541 · "Adivinhe o lance" com placar persistente e comparação com o motor — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-542 · Exportar estudo e texto para EPUB, com diagramas como SVG — ✅ **implementada em 2026-09-04**

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

### Solução

**Três módulos puros, e nada de biblioteca nova.** `estudo_paragrafos.py` é **a decisão de
paginação**: o estudo vira uma lista de `Paragrafo` (título, diagrama, comentário, lance, variante
com nível), a partir de `ui/estudo_lista.trechos` -- a travessia já conferida contra o `chess.pgn`.
Regras: a variante de primeiro nível vira parágrafo recuado **sem parênteses**; as mais fundas ficam
dentro dela entre parênteses; o comentário da linha principal corta a linha e vira prosa, o da
variante fica dentro; `[%D]` no comentário pede um diagrama **depois** dele com a posição daquele
lance, e o da raiz sai sempre como número 1; `*` não sai. EPUB e DOCX leem **a mesma lista**, e é
isso que os impede de discordar sobre onde a variante começa.

`diagrama_svg.py` desenha a posição como SVG a partir da FEN ou do `placement`. **As peças são os
caminhos de `chess.svg.PIECES`** (conjunto Cburnett), que o `python-chess` -- dependência obrigatória
desde a primeira versão -- embute; `assets/piece_images/` são PNG de 70 px, não servem a vetor, e uma
fonte de xadrez por `@font-face` mostra letras no leitor que não a carregar. Um `<g id>` por tipo de
peça **presente** em `<defs>`, um `<use>` por peça; casa de 45 unidades (o quadro dos caminhos), 64
`rect` com `data-casa`; réguas opcionais **na ordem de `ui/desenho_do_tabuleiro.reguas`**; lado a
jogar como ponto na margem direita (embaixo brancas, em cima pretas), só quando a FEN traz o campo;
tamanho em `em` (`18em` padrão) para refluir com o texto; cores de `ui/tokens.py`, nenhum
hexadecimal no arquivo. Posição vazia é `ValueError`, não tabuleiro em branco.

`epub.py` empacota com `zipfile`: `mimetype` **primeiro e armazenado**, `META-INF/container.xml`,
`OEBPS/content.opf` (EPUB 3.0, `dc:identifier` `urn:uuid` gerado, `dc:title`, `dc:creator`,
`dc:language`, `dcterms:modified`), `nav.xhtml`, um XHTML por capítulo, `estilo.css`, `imagens/`.
`exportar_estudo_epub(estudo, caminho, metadados)` e `exportar_estudos_epub` (um capítulo por
estudo); `exportar_texto_epub(documento, caminho, metadados, imagens=, cores=, corpos=)` e
`exportar_textos_epub` (uma folha por capítulo). No texto, a formatação inline **é a de
`exportacao.Html.corrida`** -- não uma cópia -- e a folha de estilo traz as mesmas regras por
`Html.regras_de_css()` (método público novo sobre o `_regras` que já existia); o que o EPUB acrescenta
é `<p>` no lugar de `<br>`, um `<h2>` para o estilo título, e a figura em arquivo separado no
manifesto. O diagrama do texto sai em SVG quando o bloco tem `placement`, no PNG injetado quando não
tem, e como `<p class="marca">[Diagrama N]</p>` quando não há nem um nem outro -- **a marca nunca
desaparece** (S-250) e o `Relatorio` conta os três casos. `verificar` faz a conferência que o
`epubcheck` faria: mimetype, container, XML bem formado, manifesto, espinha, `dc:` obrigatórios.

**Fiação pendente (fora deste item):** as ações "Exportar EPUB…" e "Exportar DOCX…" no
`EXPORTAR ▾` de `ui/barra_da_sala.py` e no menu do editor de texto, com o diálogo de arquivo. Os
arquivos são de outro executor nesta rodada; o chamador é uma linha por formato.

### Critério de aceite

- Todo arquivo do zip é XML bem formado, o `mimetype` é o primeiro membro e vai sem compressão,
  toda referência do OPF existe no zip, todo `idref` da espinha está no manifesto. ✅ Afirmado nos
  testes com `zipfile`/`ElementTree` diretamente **e** por `verificar`, que é provado contra três
  defeitos fabricados (mimetype comprimido, imagem prometida e ausente, XHTML mal formado).
- SVG: 64 casas nomeadas, peça na casa certa, virado espelha peça e casa juntas, réguas na ordem de
  `reguas`, ponto do lado a jogar, `em` no tamanho. ✅ 21.050 bytes a posição inicial (≈2,9 KB
  comprimido no zip).
- Medido em 2026-09-04: `PGN/A Matter of Endgame Technique – Jacob Aagaard.pgn` (901 KB, **2.618
  estudos**, todos posição sem lance -- é o PGN que o OCR gravou) → EPUB de **7.627 KB**, 2.618
  capítulos, 2.618 SVG, **3,1 s**, `verificar` vazio. Um estudo: 5 KB, 4 ms. Com análise de verdade,
  `pgn_database/10k_studies.pgn` (300 primeiros estudos): 2.997 parágrafos (1.245 lances, 1.147
  variantes de nível 1, 5 comentários) → 737 KB, 0,6 s; o maior estudo (27 parágrafos) → 4 KB, 5 ms.
  Texto: `DocumentoRico` sintético com título, negrito, itálico, cor, um diagrama lido e um só com a
  marca → 3 KB, 2 diagramas (1 SVG, 1 marca) e o aviso correspondente.
- Conferência externa: `ebook-convert` do Calibre (`C:\Program Files\Calibre2`) converteu o EPUB
  de 2.618 capítulos para TXT sem erro nem aviso (19 s), e o de 300 estudos idem; o texto tem título,
  FEN e linha na ordem do livro. Não virou teste: depende de programa fora do `.venv`.
- Sem dependência nova: `pyproject.toml` inalterado, nenhum extra. ✅

### Testes

- `tests/test_diagrama_svg.py`: bem formado e `viewBox`; tamanho em `em`; FEN no atributo e no
  título; posição vazia é erro; 64 casas por nome; a1 escura e h1 clara de qualquer lado; a1 no
  canto certo normal e virado; 32 peças na casa certa, `translate` do rei; virado espelha peça e
  casa juntas; `use` aponta `g` definido; só presentes em `defs`; `placement` desenha igual à FEN;
  réguas nas duas ordens e ausentes sem margem; ponto em cima/embaixo/ausente/imposto; nenhum
  hexadecimal no módulo; cores iguais à reserva de `tokens`.
- `tests/test_estudo_paragrafos.py`: ordem título → diagrama; título igual ao de `estudo_saida`;
  diagrama 1 com a FEN da raiz e `virado` do estudo; comentário da raiz como parágrafo; comentário
  da principal corta a linha; a linha que continua traz o número; variante recuada sem parênteses;
  comentário da variante fica dentro; subvariante entre parênteses; sem espaço duplo; `[%D]` pede o
  diagrama 2 com a FEN do lance e não vaza como texto; `*` não sai e `1-0` sai; estudo sem lance.
- `tests/test_epub.py`: mimetype primeiro e armazenado (também pelos bytes 30–38); todo XML bem
  formado; toda referência do manifesto no zip; container → OPF → `dc:` obrigatórios; espinha e nav
  com dois capítulos; `verificar` aprova o que sai e pega três defeitos fabricados; capítulo do
  estudo com `h1`, figura, `p.lance`, `p.comentario`, `p.variante.nivel-1` e escape; `[%D]` vira
  segunda figura com SVG bem formado; legenda com a FEN; relatório e `dc:title` do estudo; texto
  em `<p>` sem `<br>`; `<strong>` e `cor-nota` com a regra na folha (`regras_de_css`); título abre
  o capítulo ou o nome da folha entra como `h1`; SVG/PNG injetado/marca e a contagem dos três;
  `Metadados` gera `urn:uuid` e data e respeita o que veio de fora; os três estilos de livro na folha.

### O que o crítico recusou

_a preencher pelo crítico_

## S-543 · Exportar para DOCX — ✅ **implementada em 2026-09-04**

### Problema

O mesmo de S-542 pelo lado de quem edita em Word: `text/exportacao.py:552` não tem `.docx`, e o
`.rtf` (`exportacao.py:411`) é o que se oferecia para abrir num processador de texto -- sem estilo
nomeado, sem imagem vetorial, e com o diagrama como recorte da página ou nada. `python -c "import
docx"` falha no `.venv`: não há `python-docx`, e instalá-lo seria o extra que a máquina do editor
não tem.

### Solução

**`docx_saida.py` escreve OOXML mínimo com `zipfile`**, sem dependência nova: `[Content_Types].xml`,
`_rels/.rels`, `docProps/core.xml` (título, autor, idioma, datas -- os mesmos `Metadados` de
`epub.py`), `word/document.xml`, `word/styles.xml`, `word/_rels/document.xml.rels`, `word/media/`.
Mesmas entradas do EPUB: `exportar_estudo_docx`/`exportar_estudos_docx` (quebra de página entre
estudos) e `exportar_texto_docx`/`exportar_textos_docx` (`imagens=`, `cores=`, `corpos=`).

**Estilos nomeados**, `ESTILOS`: `Título` (negrito, `outlineLvl 0` -- aparece no painel de
navegação), `Lance` (negrito), `Variante` (itálico, recuo 720 twips) e `Variante 2` (1.440),
`Comentário`, `Legenda` (Consolas 8 pt, centrada, para a FEN), `Diagrama` (centrado, `keepNext`) e
`Marca de diagrama`. São os mesmos papéis do CSS do EPUB, lidos da mesma lista de
`estudo_paragrafos`. No texto, negrito/itálico/sublinhado/tachado/cor/realce/corpo vêm de
`Atributos`; cor e realce só saem se `cores` trouxer o hexadecimal (`cor-nota`, `realce-destaque`),
corpo só se `corpos` trouxer `"13pt"` (→ `w:sz 26`); notação em Consolas, legenda em itálico, fora
do modelo e faixa incerta com sublinhado pontilhado. Nenhum hexadecimal no módulo.

**O diagrama vai em par: PNG no `a:blip` e SVG na extensão `asvg:svgBlip`.** Foi a decisão pedida.
O PNG é o que todo leitor de `.docx` desenha (LibreOffice, Google Docs, Word antigo, celular); o SVG
é o que o Word 2016+ prefere e imprime como vetor. É o par que o próprio Word grava ao colar um SVG;
só SVG abre em branco fora do Word novo, só PNG serrilha no papel. O PNG vem de **`diagrama_png.py`**,
módulo novo e puro: PIL (dependência obrigatória) compõe as casas e cola os doze PNGs de
`assets/piece_images/` a 70 px por casa (o tamanho em que foram desenhados; `BUNDLE_ROOT`, como
`qt/tabuleiro.py:57`), réguas e ponto do lado a jogar com a mesma geometria e as mesmas cores do
SVG; peça ausente vira letra e um aviso no log, como o tabuleiro da janela degrada. Sai em paleta de
64 cores: 55 KB em RGB → 20 KB, sem diferença visível. O teste roda **sem Qt**. Para o diagrama do
texto sem `placement`, o PNG é o recorte injetado (`imagens=`), sem SVG; sem nada, sai a marca.
`verificar`: zip, XML bem formado em toda parte, todo membro com tipo de conteúdo, toda relação
apontando membro existente, todo `r:embed` do documento com relação.

### Critério de aceite

- As seis partes obrigatórias no zip; todo XML bem formado; toda parte com tipo de conteúdo; todo
  `r:embed` com relação e toda relação com parte. ✅ Afirmado direto e por `verificar`, provado contra
  três defeitos fabricados (embed sem relação, PNG sem tipo, `document.xml` mal formado).
- Estilos `Título`, `Normal`, `Lance` (negrito), `Variante` (itálico recuado), `Comentário`,
  `Legenda` existem e cada parágrafo do estudo sai com o seu; diagrama com PNG no blip e SVG na
  extensão, ambos no `media/`; largura pedida em EMU (`7,6 cm` padrão = os `18em` do EPUB a 12 pt). ✅
- Medido em 2026-09-04: um estudo do Aagaard → **19 KB, 48 ms** (23 ms a partir do segundo, com
  as peças em cache do processo); 200 estudos → 2.213 KB, 3,4 s; os **2.618** → **32.414 KB, 44,5 s**,
  `verificar` vazio (≈17 ms por diagrama, dos quais ~13 são o PNG). 300 estudos anotados do
  `10k_studies.pgn` → 3.297 parágrafos, 2.433 KB, 4,9 s. Texto sintético (negrito, itálico,
  sublinhado, cor, realce, corpo +2, um diagrama lido e um só com a marca) → 14 KB, 5 parágrafos,
  1 PNG+SVG, 1 marca, 1 aviso.
- Sem `python-docx` e sem extra novo: `pyproject.toml` inalterado. ✅

### Testes

- `tests/test_diagrama_png.py`: assinatura PNG e tamanho 616×616; abaixo de 30 KB; sem réguas nem
  lado não há margem; casa vazia com a cor da paleta; casa com peça sem ela; a1 no canto superior
  direito quando virado e h1 clara; a peça virada acompanha a casa; pasta sem peças desenha letra e
  avisa; a pasta padrão é a do bundle.
- `tests/test_docx_saida.py`: partes obrigatórias; todo XML bem formado; raiz → documento e tipos de
  conteúdo; `r:embed` ↔ relação ↔ parte (quatro num estudo com `[%D]`); `verificar` aprova e pega
  três defeitos; estilos com o traço prometido e nomes com acento; cada parágrafo do estudo com o
  estilo do tipo; PNG no blip e SVG bem formado na extensão; `extent` em EMU; relatório e
  `core.xml`; quebra de página entre estudos; texto cortado na quebra de linha com `Título`;
  formatação inline com cor/realce/corpo resolvidos de fora e nada quando não vêm; par PNG+SVG /
  marca e contagem; PNG injetado sem SVG; `run` escapa; `_meios_pontos`; `_hex`; nenhum hexadecimal.

### O que o crítico recusou

_a preencher pelo crítico_

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

### O que ficou de fora

**A ação de menu não foi escrita.** `ui/comandos.py` e `ui/menu.py` estavam sendo editados por
outro item na mesma árvore, e acrescentar um `Comando` sem o dono correspondente em
`qt/janela.py` quebraria o catálogo. `abrir_fila_de_livros` é a entrada pronta e sem chamador; as
três linhas que faltam estão no relatório do item.

### O que o crítico recusou

_a preencher pelo crítico_

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

### O que o crítico recusou

_a preencher pelo crítico_

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

## S-551 · A coluna do tabuleiro cresce pela altura, e o divisor da sala se move — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-552 · A janela cabe em 1024 px de largura — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-553 · O foco de teclado se vê — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-554 · O ícone desabilitado apaga também na pele escura — ◻ em andamento

_Seção a escrever pelo executor do item._

## S-580 · O fim da faixa reservada — não é item

A mensagem do commit `eb3ba71` cita a faixa "S-527 a S-580", e a guarda `test_todo_item_entregue_tem_secao_em_algum_doc` lê
números em mensagem de commit como entrega. Esta seção existe para dizer que **S-580 é o limite superior da
reserva**, e não um item: quando a faixa for ocupada até aqui, o número recebe a seção de verdade e este parágrafo sai.
