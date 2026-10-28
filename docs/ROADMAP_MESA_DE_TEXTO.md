# Roadmap da mesa de texto — Fases 90 a 96

O plano e a especificação para a aba **Texto** virar a bancada onde se corrige o texto de um
livro: o impresso à esquerda, o editor à direita, uma fita de edição no alto, e **nenhum trabalho
perdido ao passar de uma folha para a outra**. Este arquivo é o plano; a especificação item a item
(S-601 a S-668) mora em [SPEC_MESA_DE_TEXTO.md](SPEC_MESA_DE_TEXTO.md), e a razão de ela ter
nascido aqui está em [Onde a spec mora, e quando ela muda de casa](#onde-a-spec-mora-e-quando-ela-muda-de-casa).

**Data da avaliação:** 2026-10-24 · **Ramo avaliado:** `religa-as-decisoes-orfas` (`59d0cd0`, 95
commits à frente de `main`) · **Aba avaliada:** `src/chess_diagram_ocr/qt/painel_de_texto.py`, 2.895
linhas, com os 30 itens do porte para o Qt entregues · **Referência externa:** `wordcraft-main/`
(WordCraft, processador de texto em Rust, MIT OR Apache-2.0), lido por inteiro e não executado.

O que veio antes, e que este plano **não** refaz: o documento rico como dado e as ferramentas de
edição ([ROADMAP_EDITOR.md](ROADMAP_EDITOR.md), [SPEC_EDITOR.md](SPEC_EDITOR.md), S-235 a S-293); o
reconhecimento que alimenta a aba ([ROADMAP_TEXTO.md](ROADMAP_TEXTO.md),
[SPEC_TEXTO.md](SPEC_TEXTO.md)); a fita de grupos e o catálogo de comandos
([SPEC_APARENCIA.md](SPEC_APARENCIA.md)).

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
> | S-523 a S-526 | [PLANO_COLUNAS_SOLUCOES.md](PLANO_COLUNAS_SOLUCOES.md) |
> | S-601 a S-668 | [SPEC_MESA_DE_TEXTO.md](SPEC_MESA_DE_TEXTO.md) |

---

# Parte I — O plano

## O pedido, e o que ele pede de verdade

> "Usa todas as skills de engenharia de software para aprimorar nossos textos da aba 'Texto'. […]
> Implemento o reconhecimento de textos em negrito, itálico e normal. Opção para deixar os
> diagramas à esquerda no texto e por padrão centralizado. Quando for ler uma nova página o
> trabalho de texto da página anterior não se perder. Opção para aumentar e diminuir a fonte da
> aba texto. Gostaria de algo robusto […] com muitas opções de edição e formatação de texto como
> desta imagem. […] Talvez seja necessário que quando clicar no botão 'Texto' seja aberta uma
> janela com o pdf à esquerda e o editor de texto à direita."

A imagem é a captura de divulgação do WordCraft: fita com as abas Arquivo/Página inicial/Inserir/…,
os grupos Área de transferência, Fonte, Parágrafo, Estilos e Edição, painel de navegação à esquerda,
régua, e barra de estado com página, palavras, idioma e zoom.

São seis pedidos, e **a aba de hoje já atende parte de quatro deles** — o que muda o tamanho do
trabalho e, mais ainda, onde ele começa:

| pedido | o que já existe (medido no ramo) | o que falta | fase |
|---|---|---|---|
| negrito, itálico, normal | da **camada do PDF**, por caractere (S-429), e o negrito **nos dois motores** (`text/leitor.py:1319-1323`): 13 dos 42 livros declaram peso; itálico também pelo pendor da imagem (S-211) | medir quanto disso chega à tela (S-660, primeira entrega); negrito na folha **sem camada** — a régua por geometria foi medida e recusada (precisão 0,839 contra a régua de 0,9929) | 90, 96 |
| diagramas: centro por padrão, esquerda por opção | o documento guarda o alinhamento da marca (`ATRIBUTOS_DA_MARCA`) | **o desenho ignora**: ver o defeito D2 abaixo | 90, 92 |
| não perder a folha anterior | rascunho automático por inatividade (S-255) e pergunta antes de descartar | **quatro caminhos perdem trabalho**: ver o defeito D3 | 90 (remendo), 91 |
| aumentar e diminuir a fonte | zoom da vista de −3 a +8 degraus, `Ctrl+roda`, `Ctrl++`/`Ctrl+-`, gravado no estado (S-264) | um controle **à vista**; hoje ele mora no menu e na roda, e o pedido mostra que ninguém o achou | 93 (primeira entrega) |
| algo robusto, como a imagem | os comandos do catálogo da aba (`COMANDOS_DA_ABA`), numa `BarraFluida` de botões de texto | fita por abas, galeria de estilos, painel de navegação, barra de estado, pincel de formatação, correção pelo léxico | 95 |
| janela com o PDF à esquerda | o visualizador mora **à direita** da janela, e a aba Texto disputa a coluna estreita da esquerda (`LARGURA_MINIMA_DAS_ABAS`) | a mesa: janela própria, folha impressa à esquerda, editor à direita, os dois apontando um para o outro | 94 |

## Três defeitos medidos antes de qualquer recurso novo

A leitura do código levantou suspeitas, e as três foram conferidas **no widget montado**, sob
`QT_QPA_PLATFORM=offscreen`, com uma folha sintética de três blocos (`Antes do diagrama.`,
`[Diagrama 1]`, `Depois do diagrama.`) — a mesma de `tests/test_qt_texto_diagramas.py`. A sonda lê
o `QTextBlockFormat` de cada bloco desenhado depois de cada ferramenta.

### D1 — O alinhamento e o estilo de parágrafo não chegam à tela

| ação | o que o documento guarda | o que o editor desenha |
|---|---|---|
| `alinhar_centro` em `Antes do diagrama.` | `alinhamento="centro"` | `AlignLeft` |
| `estilo_titulo` no mesmo parágrafo | `estilo="titulo"` | `topMargin=0` |
| `estilo_legenda` em `Depois do diagrama.` (último bloco) | `estilo="legenda"` | `leftMargin=20` ✅ |

**Só o último parágrafo da folha sai certo**, e a razão é uma linha. `_desenhar` faz, para cada
corrida, `cursor.setBlockFormat(bloco_de(corrida.atributos))` e **depois** `insertText`. A corrida
que separa parágrafos (`"\n\n"`, atributos vazios) chega com o cursor ainda no bloco do parágrafo
anterior — e o `setBlockFormat` dela apaga o formato que o parágrafo acabou de receber. O último
parágrafo escapa porque não há separador depois dele.

Os testes não viram porque testam a metade pura: `test_o_bloco_leva_alinhamento_e_recuo` e
`test_o_alinhamento_vira_flag_do_qt` (`tests/test_qt_texto.py:184-201`) afirmam o que `bloco_de`
**devolve**, e nenhum lê o bloco **desenhado**. É o padrão que a triagem dos órfãos já tinha
nomeado: a pergunta não é "há chamador?", é "o chamador faz o que a decisão diz?". A S-259
(alinhamento) e a S-249 (estilos) estão entregues no documento, no arquivo e na exportação — e
quebradas na tela do Qt.

### D2 — A miniatura do diagrama nunca segue a marca

Com `[Diagrama 1]` selecionado e `alinhar_centro`, o documento passa a guardar `centro` na marca, e
**os dois blocos** — o da imagem e o da marca — continuam `AlignLeft`. O README promete o contrário
(a Fase 41 "centraliza a figura junto, pela única fronteira que a marca do diagrama abre"; a S-259 da
SPEC_EDITOR diz o mesmo com outras palavras), e o Tk cumpria. No Qt são duas causas:

- **o bloco da marca** recebe o formato certo e o perde para o separador seguinte — é o D1 de novo;
- **o bloco da imagem** nunca recebe o formato da marca: `_inserir_miniatura` insere a figura no
  bloco vazio que o separador anterior deixou, e só depois o formato da marca é escrito, já no bloco
  seguinte. Hoje esse bloco sai com o formato vazio (à esquerda, sem recuo) porque o separador
  escreve o seu; **consertar só o D1 piora o D2** — conferido pela primeira revisão: com o separador
  deixando de escrever, a figura passa a herdar o centro e a margem de título do parágrafo de cima.

Por isso a S-601 e a S-602 entram **no mesmo commit**. E é este defeito que o pedido "diagramas
centralizados por padrão" esbarra: sem consertá-lo, nenhuma preferência de alinhamento aparece na
tela.

### D3 — Quatro caminhos em que o trabalho da folha anterior some

1. **A releitura não grava antes de descartar.** `ler()` pergunta "Ler de novo descarta as
   alterações. Continuar?" e, no "Sim", troca o documento. `confirmar_fechamento` grava o rascunho
   antes de perguntar; `ler` não. O relógio do rascunho só dispara 4 s depois da última tecla
   (`rascunho.ESPERA_SEGUNDOS`): quem corrige a última palavra e clica "Ler folha" em seguida perde
   essa correção sem rastro, mesmo dizendo "Sim" a uma pergunta que fala só em descartar.
   `abrir_documento` ("Abrir outro arquivo descarta as alterações") faz o mesmo: pergunta sem
   gravar antes.
2. **O rascunho é podado a oito por livro.** `rascunho.gravar` chama `podar` com
   `TETO_POR_DOCUMENTO = 8`, e o mais antigo sai primeiro. Quem corrige um livro folha a folha sem
   apertar "Salvar" em cada uma perde a correção da folha 1 no momento em que a folha 9 grava o
   rascunho dela. O teto foi escrito para o rascunho como **rede de segurança**; o pedido mostra
   que ele está sendo usado como **o** lugar onde o trabalho mora.
3. **Voltar à folha não traz o trabalho de volta.** O rascunho só é oferecido depois de **reler** a
   folha (1 s com o glifo, até 40 s no modo bloco), e por uma caixa de pergunta. Quem vira a página
   no visualizador para conferir a anterior encontra a aba com a folha que estava nela — ou vazia —,
   e nada diz que o trabalho existe a não ser uma frase de rodapé na troca de livro.

Nenhum dos quatro é desatenção de quem escreveu: cada peça é razoável sozinha. O defeito é de
**modelo** — a aba é de uma folha, e o livro é de muitas. A Fase 91 troca o modelo.

## O que o WordCraft ensina, e o que não se porta

O WordCraft foi lido inteiro por um agente de exploração, sem nada ser executado; os caminhos abaixo
são relativos a `wordcraft-main/`.

**Portar ideias, não código.** Ele é Rust com interface em `egui`; este projeto é Python com
PyQt6. Nada do código atravessa, e não precisa: o modelo de documento dele (`crates/doc/src/para.rs`
— parágrafo com `text` e `runs`, objeto embutido como `U+FFFC` no texto) **é** o do
`QTextDocument`, e o desta aba já é o mesmo desenho por outro nome (corrida, marca, `OBJETO`). A
licença (MIT OR Apache-2.0) permite copiar; ideia, lista de recursos e comportamento de interface
não são protegidos, e portá-los em código novo não gera obrigação. O nome e as marcas da ArtCraft
(`docs/brand/`) não são livres e não entram em lugar nenhum.

**O que vale trazer, em ordem de valor para quem corrige OCR:**

| ideia do WordCraft | onde está lá | o que vira aqui |
|---|---|---|
| comando com id, rótulo, tecla, predicado de habilitado e uma função; fita, menu, atalho e busca despacham pelo id | `crates/engine/src/cmd/*.rs`, `session.rs:1423` | **já é** o catálogo da S-324 (`ui/comandos.py`) e o `COMANDOS_DA_ABA`; a fita da mesa nasce dele (S-650) |
| fita por abas, com os grupos da imagem | `crates/ui-egui/src/ribbon.rs:1067-1323` | S-650 a S-652, recortada ao que esta aba faz |
| pincel de formatação: um clique arma para um uso, duplo clique fixa, `Esc` desarma | `ribbon.rs:1046`, `cmd/edit.rs:776-826` | S-653 |
| sem seleção e com o cursor **dentro** de uma palavra, o formato vale para a palavra | `cmd/format.rs:154-172` | já é `rico.intervalo_alvo`; fica registrado como paridade |
| painel de navegação com Títulos / Páginas / Resultados | `crates/ui-egui/src/panes.rs:120-310` | S-654, com "Páginas" virando "Folhas do caderno" |
| barra de estado: página, palavras (ou "S de N" com seleção), idioma, zoom com `−` régua `+` e `NNN%` | `crates/ui-egui/src/chrome.rs:539-733` | S-630 e S-655 |
| `Ctrl+roda` mantém o ponto sob o cursor, e nunca também rola | `canvas.rs:1028-1045` | o zoom daqui já não rola (o `QWheelEvent` com `Ctrl` no `eventFilter` do painel); manter o ponto entra na S-630 |
| `Ctrl+=` e `Ctrl+-` **não** são zoom lá — são subscrito | `crates/ui-egui/src/lib.rs:2306-2313` | aqui são zoom desde a S-264, e não há subscrito; nada muda |
| salvamento automático só depois de 2,5 s parado **e** cursor quieto há 1,5 s; falha vai para a barra e desliga o automático daquele arquivo | `crates/ui-egui/src/lib.rs:2325-2380` | a régua da S-612 |
| cópia de recuperação: grava em temporário, relê e compara, renomeia, mantém a geração anterior até a nova validar | `docs/recovery.md`, `crates/engine/src/recovery.rs` | a escrita do caderno (S-610) |
| dicionário do usuário: uma palavra por linha, ordenado, mescla o que outro processo gravou antes de escrever | `crates/proof/src/lib.rs:109-313` | o léxico do livro (S-657) |
| sem sublinhado na palavra **que está sendo digitada** | `docs/typing-parity.md:211-237` | a conferência do léxico (S-657) |
| a imagem embutida é alinhada pelo alinhamento do **parágrafo** dela | `crates/doc/src/para.rs:441-460`, `cmd/objects.rs:307-323` | é exatamente o D2, e a S-602 |
| desfazer com rótulo ("Digitação", "Negrito") e lista para desfazer vários | `session.rs:313-322`, `chrome.rs:781-813` | S-656 |

**O que fica de fora, de propósito:** controle de alterações e comentários (`lib.rs:343-390`) — a
procedência humana da S-239 já marca o que a mão mudou, que é o que esta aba precisa saber;
tabelas, cabeçalho e rodapé, mala direta, referências, equações, SmartArt; e a **autocorreção
enquanto se digita** (`cmd/tools.rs:854+`). Esta última merece a frase: `...` vira `…`, `--` vira
travessão e `1-0` pode virar outra coisa — e em notação de xadrez `1...e5`, `1-0` e `0-0` são o
texto. Uma autocorreção que acerta em prosa inglesa apaga placar e lance em silêncio.

## As decisões que organizam o plano

**1. O documento continua sendo o estado.** Toda ferramenta nova é uma função pura de `text/rico.py`
(ou de um módulo puro novo) que recebe um documento e devolve outro; o widget só desenha. É a regra
da Fase 36, e ela vale com mais força aqui: a fita triplica o número de botões, e cada botão é uma
chance de pintar o widget sem tocar o documento — o defeito que funciona até alguém salvar.

**2. O desenho tem de ser conferido contra o documento, e não só a função pura.** O D1 e o D2
existem porque cada metade passava sozinha. A Fase 90 instala a guarda que lê o widget de volta
(S-603), e **toda fase seguinte acrescenta a ela o atributo que introduz**. Recurso sem linha na
guarda não entra.

**3. O livro é a unidade do trabalho; a folha é a unidade da leitura.** A aba continua lendo uma
folha por vez (o custo da leitura não muda), mas o que se corrige vai para um **caderno do livro**:
uma folha corrigida por arquivo, gravada sem pergunta ao sair dela e reaberta sem pergunta ao
voltar. O rascunho da S-255 deixa de ser o lugar do trabalho e volta a ser o que foi escrito para
ser — a rede entre duas gravações. É a revisão de uma recusa antiga, e ela está registrada como tal
em [O que foi recusado antes e volta agora](#o-que-foi-recusado-antes-e-volta-agora).

**4. A mesa começa como disposição da janela, e só depois vira janela própria.** O pedido é "o PDF
à esquerda e o editor à direita". A janela principal **já tem** o visualizador do PDF — à direita,
com a aba Texto espremida na coluna estreita da esquerda. O caminho mais curto e mais seguro é
**trocar os lados e as larguras do divisor enquanto o modo Texto está à frente** (S-640): o PDF que
aparece à esquerda é o visualizador de verdade, com as caixas dos diagramas e o sincronismo de folha
que já existem (`folha_pedida`). A janela própria vem depois, como "Destacar a mesa" (S-646), porque
ela tem um pré-requisito que a primeira revisão achou: a guarda de atalhos é instalada **na
aplicação** (`qt/atalhos.ligar`) e não pergunta em que janela está o foco — numa segunda janela,
`Del`, as setas, `PgUp`/`PgDn` e `Ctrl+N`/`Ctrl+D`/`Ctrl+G` agiriam sobre a janela principal.

Nas duas formas **o editor é um só**: o `PainelDeTexto` não é duplicado. Dois editores do mesmo
documento seriam duas pilhas de desfazer, dois mapas, e o primeiro desacordo entre eles seria
trabalho perdido.

**5. Estilo lido pela imagem é sugestão até passar na régua.** A régua de aplicar em lote é a da
S-213 (precisão 0,9929). O que ficar abaixo dela e acima de uma régua de **sugerir** aparece na
tela como sugestão, e só vira atributo quando a pessoa aceita. Negrito errado numa variante muda o
que a página diz.

## Visão geral das fases

| fase | itens | o que ela entrega | depende de |
|---|---|---|---|
| **90** — o desenho obedece ao documento | S-601 a S-605 | D1 e D2 consertados, a guarda que lê o widget de volta, e o remendo do D3 até o caderno chegar | — |
| **91** — o caderno do livro | S-610 a S-616 | cada folha corrigida guardada sem pergunta, reaberta ao voltar, nunca podada | 90 (a guarda cobre o reabrir) |
| **92** — os diagramas: centro por padrão, esquerda por escolha | S-620 a S-624 | preferência, escolha por diagrama e para a folha, exportação igual à tela, tamanho da miniatura | 90 |
| **93** — a letra da aba | S-630, S-632 | zoom à vista no rodapé de hoje, a letra de leitura | — |
| **94** — a mesa de texto | S-640, S-645 | o PDF à esquerda e o editor à direita, na própria janela | — |
| | S-641 a S-644, S-646 | a folha e o texto apontando um para o outro, andando juntos, e a mesa destacável | 91 |
| **95** — a fita e os painéis | S-631, S-650 a S-659 | fita por abas, tamanho em pontos, galeria de estilos, pincel, navegação, barra de estado, desfazer com rótulo, correção pelo léxico, busca por palavra inteira e curinga | 93, S-640 |
| **96** — negrito e itálico na folha sem camada | S-660 a S-668 | diagnóstico por motor (S-660 vai na primeira entrega), classificador de estilo por palavra com portão de medição, sugestão aceitável | 90 |

**A ordem das fases é por perda, e não por brilho** — e a execução recomendada corta uma fatia
através delas, na seção seguinte. A Fase 90 vem primeiro porque sem ela nada de formato
aparece; a 91 vem em segundo porque é a única que impede trabalho humano de sumir; a fita, que é o
pedido mais visível, vem depois das duas — uma fita bonita sobre um desenho que mente e um caderno
que poda seria exatamente o editor que funciona até alguém salvar.

## A primeira entrega: as duas dores na primeira semana e meia

As duas dores do pedido são **perder trabalho** e **um editor grande ao lado do PDF**. Na ordem por
fase, o editor ao lado do PDF chegaria na terceira ou quarta semana — e ele não depende de nada: a
S-640 só troca o divisor. A segunda revisão propôs cortar uma fatia através das fases, e ela é o
plano de execução recomendado:

| item | o que a pessoa vê | dias |
|---|---|---|
| S-601 a S-603 | alinhamento, estilos e diagramas aparecem na tela como o documento diz | 2 a 3 |
| S-605 | a releitura e o abrir gravam antes de trocar; nenhum rascunho de folha é podado | 0,5 |
| S-640 e S-645 | clicar em Texto põe o PDF à esquerda e o editor largo à direita | 2 |
| S-630 | `− ▬▬ + 100%` no rodapé de hoje da aba | 0,5 |
| S-620, só o padrão | diagramas centralizados (a escolha "à esquerda" vem com o resto da Fase 92) | 0,5 |
| S-660 | o relatório que diz, livro a livro, se o negrito da camada já chega à tela | 1 |

**~7 a 8 dias.** Depois: 91 → 94 (o resto) → 92 (o resto) → 95 → 96. O remendo da S-605 é o que
torna aceitável adiar o caderno uma semana: ele fecha os caminhos 1 e 2 do D3, e o caminho 3 (voltar
à folha) continua como hoje, pela oferta do rascunho.

### Estado da primeira entrega (2026-10-24, ramo `mesa-de-texto-primeira-entrega`)

| item | estado | onde, e o que mudou em relação ao plano |
|---|---|---|
| S-601 a S-604 | ✅ | `_formatar_blocos` em `qt/painel_de_texto.py`: o texto entra primeiro e cada bloco recebe o formato da corrida em que começa, também no caminho rápido da digitação. A guarda é `tests/paridade_do_texto.py`; contra o desenho antigo ela reprovou com «alinhamento 1 na tela, 4 no documento» |
| S-605 | ✅ | `ler`/`abrir_documento` gravam o rascunho antes de perguntar. **A poda saiu inteira**, e não só para documento com folha: documento sem folha nem tem rascunho |
| S-620 (o padrão) | ✅ | `rico.alinhamento_efetivo`, chamado pela tela e pela exportação; a marca sem escolha sai centralizada também no `.html` e no `.rtf` |
| S-630 | ✅ | `−`, régua, `+` e porcentagem no rodapé; a régua tem uma parada por letra diferente (`paradas_do_zoom`), e `Ctrl+roda` deixa parada a linha sob o ponteiro |
| S-640 e S-645 | ✅ com desvio | `qt/disposicao_de_mesa.py` e `ui/mesa.py`. **A preferência é um interruptor do menu Texto («Mesa de texto»), guardado no estado da sessão (`texto_mesa`), e não uma escolha de três posições em Configurações**: `settings.py` está no caminho de medição dos relatórios de campo (S-218), e a seção nova mudava a impressão que os quatro declaram. A posição «sempre» espera o R1 |
| S-660 | ✅ medido | `cvoff-texto-estilo-motor`, relatório em `docs/metrics/texto_estilo_por_motor.json` — o resultado está na seção da S-660 |

### Estado da segunda entrega (2026-10-24, ramo `mesa-de-texto-caderno`, sobre a primeira)

O caderno do livro: a Fase 91 inteira. Testes em
`tests/test_texto_caderno.py` (o módulo puro, a exportação e as frases, 28) e
`tests/test_qt_texto_caderno.py` (a fiação, 21, com **toda** caixa de pergunta reprovando).

| item | estado | onde, e o que mudou em relação ao plano |
|---|---|---|
| S-610 | ✅ com desvio | `text/caderno.py`. **A identidade é o resumo do primeiro MiB do PDF**, e não "número de folhas e resumo das primeiras folhas": o número de folhas exigiria abrir o livro com o PyMuPDF a cada troca, e dois PDFs diferentes não começam pelos mesmos 1.048.576 bytes. A pasta se chama `<livro>_<identidade>`, então achar pela identidade é achar a pasta. **Quem abre o caderno é o painel**, em `definir_livro`, e não a janela: a janela só liga `com_caderno` (uma linha, sob o teto da `janela.py`), e o caderno fica à mão em `painel.caderno_aberto` para o índice da S-613. A trava pergunta ao sistema pelo `OpenProcess` no Windows, porque lá `os.kill(pid, 0)` é `CTRL_C_EVENT` |
| S-611 | ✅ | `_guardar_a_folha` antes de ler outra folha, abrir um `.cvtxt`, trocar de livro e fechar; a pergunta saiu dos quatro caminhos e só sobra sem caderno. A primeira gravação de cada visita gira a folha para `.anterior.cvtxt`; a folha vazia **não** vai por cima da que tem texto e o rodapé diz por quê (a spec dizia que ela "vira anterior"; não há o que guardar de uma folha vazia). Virar a página com a mesa acompanhando é da S-644 |
| S-612 | ✅ com desvio | O botão vira «Abrir folha» quando a folha do campo tem caderno, e abrir não chama o motor; motor ou modo bloco trocados numa folha sem correção leem de novo sem perguntar (`caderno.abre_do_caderno`). **«Ler a folha de novo» e «Voltar à versão anterior» estão no menu do botão direito da folha**, e não num menu do botão, até a fita (S-650) lhes dar lugar. A régua é a do WordCraft (2,5 s e o cursor parado há 1,5 s). A folha que o visualizador não tem rasterizada é renderizada numa `Tarefa` (`_renderizar_ao_fundo`): o texto entra na hora e as miniaturas quando a folha chega, e a resposta para uma folha que já saiu da tela é jogada fora |
| S-613 | ✅ com desvio | `qt/indice_do_caderno.py`: uma linha por folha do `indice.json` (○ lida, ● corrigida, √ conferida — o `U+2713` do plano não existe no Segoe UI, medido com `QRawFont`), e o clique ou o `Enter` abre a folha. **Mora à esquerda da folha, dentro da aba**, aberto e fechado por «Índice das folhas do caderno» no menu Texto, como a paleta de glifos; vira a aba «Folhas» do painel de navegação quando a S-654 existir. «Marcar a folha como conferida no caderno» tem `Ctrl+Shift+Enter`, grava o índice sem redesenhar, e o rodapé ganha «34 de 289 folhas conferidas» a partir da primeira |
| S-614 | ✅ com desvio | «Exportar o caderno do livro…» no menu Texto: `.md`, `.html` ou `.rtf`, as folhas em ordem, cada uma aberta por um título «Folha N» que o próprio formato desenha (`exportacao.exportar_folhas`; **os formatos não mudaram**). As miniaturas saem de cada folha renderizada de novo, na thread de trabalho, com o nome `<arquivo>_f0012_d1.png`; o relatório diz «faltam as folhas 1-4, 17». **O PDF pesquisável do livro usa o caderno** dos dois lados: «Exportar o caderno do livro…» tem a opção PDF pesquisável (o livro inteiro, com a camada das folhas do caderno), e o `cvoff-texto-pesquisavel` põe a folha corrigida no caderno no lugar da leitura do motor, sem lê-la e sem tomar a trava da janela (`--sem-caderno` desliga). A folha do caderno entra **por bloco**, sem piso de confiança, e o metadado diz quantas eram |
| S-615 | ✅ | Na abertura do livro, cada rascunho dele entra no caderno se a folha não tem caderno mais novo, e só então sai da pasta |
| S-616 | ✅ com desvio | «Descartar as correções desta folha» devolve a leitura do motor como edição (`Ctrl+Z` traz as correções) e guarda a corrigida como `anterior`. **O `.lida.cvtxt` é a leitura mais recente do motor**, e não a primeira: ler de novo com outro motor é pedir outra leitura, e descartar deve voltar a ela. Abrir um `.cvtxt` avulso do livro aberto **não** pergunta «trazer para o caderno?»: abri-lo para olhar não muda nada, e a primeira edição o leva ao caderno com a folha de antes como `anterior` |

### Estado da terceira entrega (2026-10-24, ramo `mesa-de-texto-caderno`)

O resto da Fase 94 que não pede a janela própria, e a Fase 92 menos a flutuação com portão.

| item | estado | onde, e o que mudou em relação ao plano |
|---|---|---|
| S-641 | ✅ | Já vinha do `folha_pedida` de hoje: abrir uma folha do caderno leva o visualizador a ela, e um `.cvtxt` de outro livro não mexe nele. Coberto pelo teste da S-644 na janela |
| S-642 (etapa 1) | ✅ | `rico.bloco_em` e `rico.deslocamento_do_bloco` (puros); o painel diz o `bbox` do bloco sob o cursor (`bloco_destacado`), o visualizador o contorna na cor do foco e rola até ele (`VisorDePagina.definir_destaque`), e o clique na folha sai em **pontos** (`ponto_clicado`) e põe o cursor no começo do menor bloco que o contém. Quem liga os dois é `qt/disposicao_de_mesa.py`, e só com a mesa armada. A etapa 2 (por linha) continua esperando a etapa 1 provar valor |
| S-643 | ✅ | A faixa acima do editor com o recorte do bloco sob o cursor (`_recorte_da_folha`, o mesmo da miniatura), na largura do editor e até um terço da altura dele; só na mesa e com a folha rasterizada |
| S-644 | ✅ com desvio | A janela avisa a aba quando a mesa arma (`definir_mesa`); virar a página guarda a folha que sai, abre a que entra do caderno, ou mostra o vazio «A folha 13 ainda não foi lida» com o botão «Ler a folha 13» — e não lê. **A preferência «Ler ao chegar numa folha sem caderno» não entrou**: é uma linha no menu e uma no estado, e fica para quando alguém a pedir |
| S-646 | ⏳ → ✅ na quinta entrega | Ver a quinta entrega |
| S-620 | ✅ com desvio | «Diagramas no texto à esquerda (o padrão é ao centro)», interruptor do menu Texto, guardado em `AppState.texto_diagramas` (e não em Configurações, pelo motivo da S-640). Trocar redesenha sem tornar a folha «por gravar», e a marca com alinhamento escrito vence as duas. A guarda S-603 lê o alinhamento efetivo pela mesma função |
| S-621 | ✅ com desvio | Três comandos do menu Texto para a folha (à esquerda, ao centro, como a preferência), um passo de desfazer. O do caderno inteiro está no **menu do botão direito do índice**, com a pergunta «Alinhar 41 diagrama(s) de 23 folha(s) à esquerda?» e a versão de antes de cada folha como `anterior` |
| S-622 | ✅ | O `.html` e o `.rtf` já seguiam o efetivo; o `.md` põe a figura num `<p align="center"><img …></p>` quando ela não está à esquerda, e mantém o `![…](…)` à esquerda. A exportação recebe a preferência (`exportar(…, diagramas=…)`) |
| S-623 | ✅ com desvio | Pequenas · médias · grandes (160 · 240 · 320 px no corpo do sistema), **médias por padrão** — a miniatura de hoje cresceu de 160 para 240. Um comando que anda em roda, «Tamanho das miniaturas dos diagramas», em vez de três; guardado em `AppState.texto_miniatura` |
| S-624 | ⏳ → ✅ na quinta entrega | Ver a quinta entrega |

### Estado da quarta entrega (2026-10-24, ramo `mesa-de-texto-caderno`): o itálico e a Fase 95

O conserto barato do itálico (S-660, remedido: ver a seção dela) e a Fase 95 inteira. Testes em
`tests/test_qt_texto_fita.py` (30, um por critério de aceite, e os puros ao lado).

| item | estado | onde, e o que mudou em relação ao plano |
|---|---|---|
| S-650 | ✅ com desvio | `ui/fita_do_texto.py` declara as abas (Arquivo, Página inicial, Inserir, Leitura, Revisão, Exibir) e `qt/fita_do_texto.py` as desenha; o inventário do editor ganhou `comandos_do_editor_fora_da_fita`, lido da declaração. A barra de acesso rápido mora no canto das abas. **As cores continuam listas** (a cor e o realce sob o cursor à vista), e não botões partidos que lembram a última cor. **Achado no caminho:** as teclas próprias do editor (`Ctrl+B`, `Ctrl+I`, `Ctrl+L`…) estavam declaradas em `TECLAS_DO_EDITOR` e não ligadas no Qt — `Ctrl+B` não negritava nada. O painel passou a atendê-las, e as dicas da fita as mostram |
| S-631 | ✅ | «Corpo do parágrafo (pt)», no grupo Fonte: o corpo do parágrafo sob o cursor, vazio no misto; o valor digitado vira o degrau mais próximo, num passo de desfazer |
| S-651 | ✅ | A galeria desenha cada estilo com a fonte de `texto_formato.formato_de`, a mesma da folha, e marca o do cursor. A lista de estilos da barra antiga saiu |
| S-652 | ✅ com desvio | `Ctrl+F1` recolhe a fita deixando só as abas, e o estado guarda. A compacta é a aba que não cabe numa linha perder os nomes dos grupos; o orçamento de altura da S-228 não é cobrado aqui |
| S-653 | ✅ | O pincel arma num clique, fixa no segundo clique logo depois, `Esc` desarma; `Ctrl+Shift+C`/`Ctrl+Shift+V`. A faixa de confiança não vai (`rico.ATRIBUTOS_DE_TRECHO`) |
| S-654 | ✅ com desvio | `qt/painel_de_navegacao.py`: Títulos, Folhas (o índice da S-613), Resultados (com «palavra inteira» e «curingas») e **Correções**, a quarta aba, que é a lista da Revisão › Correções |
| S-655 | ✅ com desvio | Palavras («12 de 357 palavras») e léxico («2 fora do léxico», o clique é o `F7») em caixas próprias; folha, diagramas, correções e caderno ficam na frase de `frase_do_rodape`; o recado some em 6 s. **Não entraram** o «gravado às 14:32» nem o clique na folha que abre o campo |
| S-656 | ✅ | Cada passo da pilha tem o nome do comando que o fez (`executar` o põe), e a lista do desfazer, na barra de acesso rápido, desfaz até o escolhido num redesenho só |
| S-657 | ✅ | `F7`; as sugestões em `text/sugestao.py`, com a tabela de trocas de OCR e onde cada uma foi vista; o léxico do livro em `data/cadernos/<livro>/lexico.txt`, relido e mesclado antes de gravar; «Ignorar nesta folha»; a palavra em digitação não é marcada |
| S-658 | ✅ | O modo foco esconde a fita, o painel de navegação e, na mesa, o visualizador; `Esc` volta. As marcas ¶ são reaplicadas a cada `QTextDocument` novo e não vão ao texto copiado. Sem tecla, como o plano pedia |
| S-659 | ✅ | Busca por palavra inteira e com curinga (`busca.curinga_para_regex`, que recusa repetir grupo inteiro), troca com `\1` a `\9`; `Alt+Shift+↑/↓` move o parágrafo; `Alt+X` só com quatro dígitos sem `U+`, porque as letras de `a` a `f` também são hexadecimais |
| os confortos | ✅ | A paleta de glifos mostra primeiro os 20 usados por último, guardados no estado da sessão |

**O que a conferência na tela achou (2026-10-25).** Fotografada a janela de verdade lendo o
Seirawan, quatro defeitos que a suíte não via, todos consertados: os grupos do Word com até quinze
itens passavam da coluna da mesa e eram cortados, alargando a aba e dando rolagem horizontal ao
editor (agora nenhum grupo passa de cinco itens, e os comandos novos têm rótulo curto na fita); a
fita guardava a altura da aba mais alta (`heightForWidth` da aba à vista); os quatro botões de estilo
repetiam a galeria; e `Ctrl+]`/`Ctrl+[` não traduziam para o Qt (`bracketright`), então o corpo do
parágrafo não tinha tecla. O índice passou a marcar a folha que se abriu por ele.

### Estado da quinta entrega (2026-10-25, ramo `mesa-de-texto-caderno`)

| item | estado | onde, e o que mudou em relação ao plano |
|---|---|---|
| S-632 | ✅ com desvio | «Letra da folha: proporcional, serifada ou monoespaçada», um comando que anda em roda (menu Texto e grupo Zoom da aba Exibir), como o das miniaturas, em vez de três; guardado em `AppState.texto_familia`. Troca só a proporcional da base da vista (`_base_da_vista`): a notação fica na monoespaçada nas três, e a guarda S-603 lê a família contra a mesma base. A serifada é a primeira de `tipografia.SERIFADAS_PREFERIDAS` que o sistema tem (Georgia no Windows); sem nenhuma, a proporcional. Testes em `tests/test_qt_texto_letra.py` |
| S-624 | ✅ com desvio, portão passou | **Interruptor de vista, e não uma terceira opção na marca**: «Texto ao lado dos diagramas à esquerda» (`AppState.texto_ao_lado`) faz flutuar toda figura que se desenha à esquerda -- a da preferência e a que a pessoa alinhou à esquerda. Um terceiro valor de alinhamento na marca seria mudança de formato (R5): `Atributos` recusa alinhamento desconhecido ao carregar. **O custo conhecido não veio**: a figura entra pelo importador de HTML do Qt (`<img align=left>`), que registra o quadro flutuante sem pôr `U+FDD0`/`U+FDD1` no texto cru; o `QTextFrame` do cursor os poria, e `createObject` chamado do Python dá um quadro que o leiaute ignora. O `.md` e o `.html` flutuam a figura; o `.rtf` e o `.txt` não sabem, e a deixam à esquerda numa linha própria. Portão em `docs/metrics/texto_flutuante.json` (`cvoff-texto-flutuante`): 10 folhas de 5 livros, 21 figuras, as 21 flutuam e nenhuma no controle, editor certo nas duas vistas |

**O que o portão achou no caminho.** A primeira corrida reprovou a folha 132 do Kemeri **também no
controle**, sem figura nenhuma flutuando: o OCR devolveu `🗸` (`U+1F5F8`), que o Qt conta como duas
posições e o `_Mapa` contava como uma, e toda posição depois dela ficava deslocada -- a letra digitada
ia ao lugar certo no documento, e a tela era lida e repintada no vizinho. Defeito do editor de antes,
consertado (`_Mapa.registrar_texto`, `_texto_da_tela` em unidades UTF-16, `_do_qt`). **E a exportação
da aba não levava a preferência «à esquerda»** que a S-622 dizia levar: `exportar` aceitava
`diagramas=`, e o painel não o passava. Leva agora, com o texto ao lado.

**A Fase 96, até o portão (S-661 a S-663), e onde ela parou.**

| item | estado | onde, e o que mudou em relação ao plano |
|---|---|---|
| S-661 | ✅ com desvio | `cvoff-texto-estilo-conjunto` e `text/estilo.py`; relatório em `docs/metrics/texto_estilo_conjunto.json`, o conjunto em `data/estilo/` (fora do git). 40 folhas espaçadas de cada PDF, só as tipográficas, a palavra rotulada pelo nome da fonte ou o bit **de cada caractere** (a que mistura fica fora), recorte a 300 dpi em 32x192. **Só entra livro cuja camada registra os dois estilos** nas folhas lidas -- um livro que não marca itálico rotularia o itálico como normal --, e sobraram **7 livros (11 arquivos), 51.064 palavras**: 2.441 negrito, 1.604 itálico, 302 negrito-itálico. **A identidade é o texto do livro inteiro** (sequências de cinco palavras), e não as folhas lidas: pelas amostras os dois «400 Quebra-cabeças» não se juntavam e caíam na validação e no teste. As degradações são aplicadas à palavra já normalizada, e não ao recorte de 300 dpi |
| S-662 | ✅ | `cvoff-texto-estilo-classificador`: quatro convoluções, média e máximo **só sobre a largura útil** (senão a rede aprende o comprimento da palavra), treino com as degradações em metade das palavras, semente fixa. Custo: 1 ms por palavra na CPU |
| S-646 | ✅ com desvio | O dono pediu em 2026-10-25 (R1). «Destacar a mesa numa janela própria» (menu Texto e grupo Mostrar da aba Exibir; de novo, devolve) leva o **mesmo** `PainelDeTexto` para uma `JanelaDaMesa` com uma vista da folha à esquerda (`qt/mesa_destacada.py`). Os três pré-requisitos: **(1)** `GuardaDeAtalhos.registrar_janela` -- a guarda pergunta de que janela é o foco, subindo pelos pais (a busca aberta da mesa é da mesa, a caixa da principal é da principal), e a mesa só atende as ações do texto (`ui/mesa.ACOES_DA_MESA_DESTACADA`: salvar, desfazer, refazer, achar, substituir); **(2)** `PainelPrincipal.soltar_modo`/`devolver_modo` por `takeWidget`, porque o `setWidget` da `QScrollArea` destrói o widget que tira do lugar, e um cartão «O texto está na mesa · Mostrar · Trazer de volta» no lugar; **(3)** `_focar_aba` pergunta antes à mesa destacada. Fechar a janela da mesa devolve o texto; fechar a principal grava o caderno e fecha as duas. **Desvio:** a vista da folha mostra a folha que o editor tem rasterizada, e não o visualizador do livro; e a disposição de mesa da janela principal (S-640) continua valendo com o cartão no lugar do texto. Testes em `tests/test_qt_mesa_destacada.py`, com a janela de verdade; a guarda sabotada (sempre os comandos da principal) faz o `PgDn` da mesa virar a página da principal, e o teste reprova |
| S-663 | ✅ medido, **não passa** | `docs/metrics/texto_estilo_classificador.json`, sobre `5ba4ace` em árvore limpa. **Um livro de fora por rodada**, e não a divisão fixa: com 7 livros ela deixava o teste com um livro e 15 itálicos. O número está na seção da S-663 |
| S-664 a S-667 | ✖ fechados pelo portão | A sugestão, o itálico por palavra, a frase do rodapé e a remedição dependiam de um classificador que passasse. O pincel manual (S-241) continua sendo a resposta, e `negrito=None` continua sendo o que a folha sem camada diz |

### Estado da sexta entrega (2026-10-28, ramo `mesa-de-texto-caderno`): o que faltava

Os desvios que as entregas anteriores deixaram por escrito, fechados. Nenhum muda o formato do
documento nem do caderno.

| item | estado | onde, e o que mudou em relação ao plano |
|---|---|---|
| S-640 | ✅ | A terceira posição da preferência, «Mesa em toda área» (`ui/mesa.MESA_SEMPRE`, comando `mesa_sempre`): o impresso à esquerda em qualquer aba, e não só com o texto à frente. `DisposicaoDeMesa` recebe o `menu.marcar` e marca os dois interruptores juntos; os dois moram no grupo novo «Mesa» da aba Exibir, com o destacar da S-646 |
| S-642, S-643 | ✅ etapa 2 | O contorno na folha e a faixa impressa descem do bloco à **linha**: `rico.linha_em` compara o texto do bloco no documento com as linhas lidas e leva a posição do cursor até a linha, sem mudar o formato. Onde a pessoa reescreveu, a comparação não casa e a resposta volta a ser o bloco (a etapa 1). A faixa da linha tem a altura de duas linhas de texto. Testes em `tests/test_texto_caderno.py` (`LinhaEmTests`) e `tests/test_qt_texto_caderno.py` (`ApontarPorLinhaTests`) |
| S-644 | ✅ | «Ler ao chegar numa folha sem caderno» (`ler_ao_chegar`, grupo Ler da aba Leitura; `AppState.texto_ler_ao_chegar`, desligado por padrão): com a mesa acompanhando a página, a folha que ainda não está no caderno é lida ao chegar, em vez de mostrar o convite a ler. Folha que já está no caderno abre o que foi feito nela, como antes |
| S-650 | ✅ | O desvio das cores fechado: «Cor do texto» e «Realce» ganharam **botões partidos** que lembram a última cor -- o clique aplica a mesma de antes, a seta abre as cores do autor. A amostra do botão sai de `texto_formato.formato_de`, a função da folha, e a última cor vai ao estado da sessão (`texto_ultima_cor`, `texto_ultimo_realce`). As listas ficam ao lado, porque mostram a cor sob o cursor |
| S-652 | ✅ | O orçamento de altura agora é cobrado: a fita mede a altura plena na largura de agora e, se ela passa de 20% da altura da janela (`fita_do_texto.FRACAO_DO_ORCAMENTO`, a régua da S-151), esconde os nomes dos grupos e fica compacta; a janela crescendo, os nomes voltam. **Não recolhe sozinha**: recolher esconde os controles que o estado vazio cita pelo nome («Achar no texto…»), e é gesto da pessoa (`Ctrl+F1`), que o orçamento nunca desfaz |
| S-655 | ✅ | Os dois que faltavam: «gravado às 14:32», a hora do índice do caderno, quando não há nada por gravar; e o clique na folha do rodapé leva à aba Leitura da fita (devolvendo a fita se estiver recolhida) com o campo da folha selecionado |

**O que continua fora, e por quê.** A S-668 (sublinhado e versalete pela imagem, estilo por
caractere dentro da palavra) não tem rótulo confiável na camada em quantidade, e classificador sem
rótulo não tem portão. A S-664 a S-667 foram fechadas pelo portão da S-663: sem classificador que
passe, não há sugestão a fazer. A especificação mudou de casa nesta entrega, para
[SPEC_MESA_DE_TEXTO.md](SPEC_MESA_DE_TEXTO.md).

## Custo, risco e ordem

| fase | esforço | risco | o que fica se ela parar no meio |
|---|---|---|---|
| 90 | 2 a 3 dias | **baixo** — o conserto é a regra de quem escreve o formato do bloco (S-601), e a primeira versão dela, testada, engolia o `Enter` na linha em branco; o custo está na guarda | a tela continua mentindo sobre alinhamento e estilo |
| 91 | 4 a 6 dias | **médio** — formato novo em disco (`data/cadernos/`), migração dos rascunhos | o rascunho de hoje, com os três caminhos de perda |
| 92 | 2 a 3 dias | baixo; a flutuação ao lado do texto (S-624) é a parte arriscada e tem portão próprio | os diagramas alinhados à mão, um por um |
| 93 | 1 a 2 dias | baixo | o zoom continua no menu e na roda |
| 94 | 4 a 6 dias, mais 3 a 4 para destacar (S-646) | **médio** — trocar o divisor é barato; destacar exige a guarda de atalhos por janela e mover o painel para fora da `QScrollArea` do modo | a aba na coluna estreita, como hoje |
| 95 | 6 a 9 dias | médio — é a fase com mais superfície; o portão de teclado e o de leitor de tela valem para cada botão | a barra de hoje, que já faz quase tudo, sem a forma da imagem |
| 96 | 6 a 10 dias, metade medição | **alto** — pode terminar em "não passa", como a régua de geometria terminou | o pincel manual da S-241, que é o que existe hoje |

**Total: ~6 a 9 semanas.** As Fases 92 e 93 são independentes entre si e podem correr em paralelo
depois da 90; da 91 a 92 só depende na parte que alinha o caderno inteiro (S-621, que usa o índice
da S-613). A 96 só depende da 90 e pode correr em paralelo com tudo — ela é medição e
modelo, não interface, e o fim dela pode ser uma recusa medida.

## Riscos e decisões que precisam do dono do projeto

Numerados R1 a R7, e citados assim no resto do documento — para não confundir com as cinco
decisões que organizam o plano, que já estão tomadas.

- **R1 · A disposição de mesa vale sozinha ao clicar em "Texto"?** A recomendação é sim (é o que o
   pedido descreve), com a preferência de três posições da S-640. E **a janela própria (S-646) é
   pedida, ou a disposição basta?** A recomendação é entregar a disposição, usar uma semana, e só
   então decidir — ela custa o conserto da guarda de atalhos, que é mudança na janela inteira.
   **Decidido em 2026-10-25: a janela própria é pedida**, com os três pré-requisitos (S-646, feita).
- **R2 · Onde o caderno mora.** A recomendação é `data/cadernos/` (desviado na suíte pelo
   `CVOFF_DATA_DIR`, como `data/rascunhos/`). A alternativa — uma pasta ao lado do PDF — leva o
   trabalho junto quando o livro muda de máquina, e escreve dentro de `PDF/`, que hoje é só leitura.
- **R3 · Tamanho da letra por trecho.** Hoje o corpo é atributo de **parágrafo** (S-260), de propósito:
   "marcar meia frase marcaria meio parágrafo". A caixa de tamanho da fita (S-631) respeita isso.
   Se o dono quiser tamanho por trecho, como no Word, é uma mudança do formato `.cvtxt` e da S-260,
   e fica fora deste plano até ser pedida.
- **R4 · A régua de sugerir estilo** (S-663). A proposta é precisão ≥ 0,95 fora do livro de treino —
   uma sugestão errada a cada vinte, que a pessoa recusa com um clique. É um número de produto, e
   quem o escolhe é o dono.
- **R5 · Duas mudanças de formato do `.cvtxt`.** A sugestão de estilo (S-664) e a origem por linha
   (S-642, segunda etapa) precisam de um canal na `Corrida` que não é atributo do autor e que
   sobrevive a `fundir`, `editar` e ao arquivo. As duas sobem a versão do formato (S-238) e
   precisam de leitura do formato antigo. Nenhuma das duas é pré-requisito do resto do plano.
- **R6 · Em que ramo isto entra.** O plano foi medido em `religa-as-decisoes-orfas`, que está 95
   commits à frente de `main`; os defeitos D1 e D2 precisam ser reconferidos em `main` antes de a
   Fase 90 abrir ramo próprio.
- **R7 · O caderno e o caminho de livro da suíte.** Já há dois caminhos de texto de livro inteiro: a
   aba **Revisão de texto** (`qt/painel_de_revisao_de_texto.py`, SOL-11), que grava texto corrigido
   no IR da suíte, e *Exportar o livro para EPUB…/DOCX…* (`qt/exportador_de_livro.py`), que exporta
   desse IR. O caderno seria uma terceira guarda, e as correções feitas nesta aba não chegariam ao
   EPUB/DOCX. A recomendação: o caderno é a fonte da aba Texto, e a S-614 ganha uma saída **para o
   IR da suíte** quando ela estiver ao alcance, para o EPUB/DOCX do livro levar o que foi corrigido
   aqui. Quem decide se o IR também alimenta o caderno (o caminho de volta) é o dono.

## O que foi recusado antes e volta agora

Duas recusas da ROADMAP_EDITOR são revistas por este plano. As duas com o motivo de antes à vista.

| recusa de antes | o motivo de antes | o que mudou |
|---|---|---|
| **Editar o livro inteiro numa aba só** | "A aba é da folha aberta, por decisão de custo" | A Fase 91 **não** desfaz isso: a aba continua mostrando uma folha. O que muda é que a folha que sai fica guardada. O custo da recusa era o da leitura, e ele não muda. |
| **Um segundo modelo para negrito e itálico** | "A resposta é geometria sobre a binária, como o pendor do itálico já é — não uma segunda rede" | A geometria foi medida em 2026-08-29 sobre 20.156 palavras de 14 livros, com o corte aprendido fora do livro: precisão máxima utilizável 0,839, e **apertar o corte não compra precisão** (`text/negrito.py`, `docs/metrics/texto_negrito_imagem.json`). A premissa da recusa caiu. A Fase 96 reabre a pergunta com portão: se o classificador não passar, a recusa volta com número novo. **Voltou (2026-10-25)**: fora do livro a rede não chega a 0,95 em classe nenhuma, e no scan simulado perde do acaso (S-663). |

E três recusas **continuam de pé**: `.docx` **exportado pela aba** (o `.rtf` cobre a folha com
zero dependências; o DOCX do livro vem da suíte, R7), editor HTML de
terceiros no lugar do `QTextEdit` (rompe "o documento é o estado" e pesa no empacotamento com o
Nuitka) e corretor ortográfico de dicionário (o acervo tem 8 idiomas e notação; o léxico confere e
não troca, e a S-657 o estende sem mudar isso).

## Armadilhas conhecidas desta bancada

Quem implementar vai cair nelas; todas custaram uma rodada antes.

- **Nome de método com acento derruba o PyQt** sem exceção quando ligado por `connect`. Os slots
  novos têm nome ASCII, mesmo que a função pura ao lado tenha acento.
- **`processEvents` não apaga `deleteLater`**: nos testes, desmonte com `descartar`
  (`tests/qt_app.py`). A mesa (S-640) é janela de topo, e uma janela de topo esquecida segura o foco
  para o teste seguinte.
- **Caixa de mensagem abre de verdade na suíte e a trava.** Patch com `mock.patch.object`; o
  caderno existe justamente para tirar duas perguntas do caminho.
- **Patch não intercepta slot já ligado**: teste de fiação afirma o efeito, e não a chamada.
- **Teste não congela a lista do catálogo**: a fita gera botões do catálogo, e um `assertEqual`
  com a lista literal de comandos quebra quando outra sessão acrescenta um.
- **A suíte desvia `data/`** pelo `CVOFF_DATA_DIR`. O caderno grava em `data/cadernos/` e tem de
  entrar no desvio no mesmo commit em que nasce, senão a suíte escreve no caderno de quem a roda.
- **O repositório é LF** (`.gitattributes`), e 52 arquivos ainda estão em CRLF — patch escrito com
  quebra Unix não casa neles.
- **A tabela de persistência dos docs** (`test_a_tabela_de_persistencia_lista_o_que_data_tem`)
  reprova pasta nova em `data/` que ela não liste.

---

# Parte II — A especificação

Mudou de casa com a primeira entrega: os itens S-601 a S-668, fase a fase, estão em
[SPEC_MESA_DE_TEXTO.md](SPEC_MESA_DE_TEXTO.md). Cada um traz o problema, a decisão, onde mora e o
critério de aceite escrito para virar teste.

---

# Onde a spec mora, e quando ela muda de casa

A especificação nasceu **neste** arquivo, e não num `SPEC_MESA_DE_TEXTO.md`, por uma regra de
`tests/test_docs.py`: item com seção `## S-NN` em arquivo cujo nome começa com `ROADMAP` não precisa
entrar na tabela de faixas, e a tabela é copiada byte a byte nos documentos que a trazem. Pôr a
faixa S-601 a S-668 em todos antes de um só item existir seria mexer em vinte e tantos arquivos por
um plano.

**Ela mudou de casa em 2026-10-28**, com as Fases 90 a 95 entregues: as seções foram para
[SPEC_MESA_DE_TEXTO.md](SPEC_MESA_DE_TEXTO.md), a linha
`| S-601 a S-668 | [SPEC_MESA_DE_TEXTO.md](SPEC_MESA_DE_TEXTO.md) |` entrou na tabela de todos os
documentos que a trazem, e este arquivo ficou com o plano.

**Sobre os números.** As Fases 90 a 96 e os itens S-601 a S-668 deixam um vão de propósito: em
2026-10-24 o maior número de fase nos ramos é 86 e o maior item é S-580, e há sessões trabalhando
em ramos que ainda não entraram em `main`. O vão é o que impede a colisão que a segunda revisão
externa já viveu (a numeração de lá colidia com as Fases 73 a 77).

# As duas revisões, e o que cada uma mudou

O pedido terminava em "revisa mais duas vezes em busca de melhorias". As duas revisões foram feitas
por leitores que não escreveram o plano, com o código à mão; o que elas acharam e não estava certo
foi corrigido acima, e fica listado aqui para que a mudança tenha rastro.

## Primeira revisão — os fatos contra o código

Um revisor reproduziu o D1 e o D2 com sondas próprias sob `offscreen`, conferiu cada número citado e
testou as correções propostas antes de aceitá-las. Vinte achados — doze que mudaram o plano, na
tabela, e oito menores:

| achado | gravidade | o que mudou |
|---|---|---|
| a regra da S-601 ("o separador não escreve formato") engole o `Enter` na linha em branco depois de um título — testado | bloqueador | a S-601 passou a escrever as quebras do separador com formato vazio; o critério ganhou o `Enter` na linha em branco |
| a S-642 supunha que a corrida sabe de que **linha** veio; ela só sabe o **bloco**, e o texto digitado herda o bloco do vizinho | bloqueador | a S-642 virou duas etapas: por bloco com o que existe, por linha só com mudança de formato |
| a guarda de atalhos é da aplicação e não pergunta a janela: numa segunda janela, `Del` e as setas agiriam sobre a principal | bloqueador | a mesa começa como **disposição da janela principal** (S-640); a janela própria virou a S-646, com três pré-requisitos |
| o D2 descrevia a causa errada, e consertar só o D1 piorava o D2 | importante | o D2 foi reescrito; S-601 e S-602 entram no mesmo commit |
| a S-602 abria um bloco extra sempre | importante | bloco extra só quando a figura não começa o bloco |
| `Ctrl+PgUp`/`Ctrl+PgDn` já são "página duvidosa" | importante | a S-644 não cria atalho de folha; usa a navegação do visualizador |
| `text/semelhanca.py` compara imagens de glifo, não palavras | importante | a S-657 ganhou um módulo novo de distância com pesos de OCR |
| a S-197 não é deduplicação de livro, e não existe deduplicação de livro | importante | a Fase 96 começa pela identidade do livro, sem a qual o teste fora do livro vaza |
| a chave do caderno pelo caminho órfã o caderno quando o PDF muda de lugar | importante | a S-610 guarda a identidade de conteúdo e oferece religar |
| "abre em milissegundos" era falso: `abrir` rasteriza na thread da janela | importante | a S-612 tira a rasterização da thread da janela |
| 4 s contra 2,5 s + 1,5 s: dois relógios no mesmo plano | importante | um relógio só, o da S-612 |
| a sugestão de estilo e o quadro flutuante são mudanças de formato e de texto cru | importante | R5; o portão da S-624 cita os caracteres de quadro |

Os oito menores: referências cruzadas trocadas, a `BarraFluida` em `qt/barra.py`, a régua de zoom de
paradas desiguais, o `QTextOption` que morre a cada redesenho, `Ctrl+Shift+8` que chega como `*`, a
saída de exportação que muda com a S-620, a precisão por classe contra o acerto global da S-663, e
um quarto caminho de perda no D3 (`abrir_documento`).

## Segunda revisão — o pedido, a ordem e o uso

Um segundo revisor, com outra pergunta: o plano entrega o que foi pedido, na ordem em que dói, com
critérios que um teste consegue cobrar? Conferiu também as referências depois das edições da
primeira (as 44 referências a itens existiam; as faixas da tabela de fases batiam).

| achado | o que mudou |
|---|---|
| o negrito da camada **já** chega aos dois motores (`text/leitor.py:1319-1323`), e a medição que diria isso estava na última fase | a S-660 foi para a primeira entrega |
| o editor ao lado do PDF chegava na semana 3 ou 4, e a S-640 não depende de nada | nasceu [a primeira entrega](#a-primeira-entrega-as-duas-dores-na-primeira-semana-e-meia), com a S-605 (remendo do D3) |
| a Fase 93 dependia da 95 (barra de estado, fita) e a 95 da 93 | a S-630 vai no rodapé de hoje; a S-631 mudou para a Fase 95 |
| gravar sem perguntar erra em cinco casos: jogar fora de propósito, destruição acidental, duas instâncias, o mesmo livro em duas pastas, trocar de motor | `.lida.cvtxt` imutável e "Descartar as correções" (S-616); `anterior` girado na primeira gravação de cada visita (S-611); `caderno.lock` (S-610); identidade antes do caminho (S-610); motor novo relê folha sem correção (S-612) |
| trocar o divisor a cada troca de modo desorienta | preferência de três posições, estado do visualizador preservado, limiar avaliado ao entrar (S-640, S-645) |
| "aumentar a fonte" confunde zoom (vista) e corpo (documento) | rótulos e dicas que dizem qual muda o documento (S-631) |
| o plano ignorava a aba Revisão de texto e o EPUB/DOCX da suíte | R7, e a recusa do `.docx` reescrita |
| WordCraft barato que faltava | S-659 (busca por palavra inteira e curinga, mover parágrafo, `Alt+X`); glifos recentes e cor lembrada na S-650 |
| vinte itens sem critério de aceite, e dois que testavam só a metade pura | critérios escritos, e os da S-612 e da S-653 passam a ler o widget |
| dono do caderno sem nome, arquivos novos sem nome | a janela segura o caderno; `Caderno.difere` é puro; arquivos de módulo, de teste e chaves de estado nomeados |
| "decisão N dos riscos" se confundia com as cinco decisões do plano | os riscos viraram R1 a R7 |

# Como conferir o que já foi implementado

```bash
.venv/Scripts/python.exe -m pytest tests/test_qt_texto_paridade.py tests/test_texto_caderno.py -q
```

Os dois arquivos não existem antes das Fases 90 e 91; enquanto não existirem, o comando falha
dizendo isso, e essa é a resposta certa. Os relatórios de medição da Fase 96 ficam em
`docs/metrics/texto_estilo_por_motor.json` e `docs/metrics/texto_estilo_classificador.json`.
