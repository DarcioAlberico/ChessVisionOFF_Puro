# Roadmap da mesa de texto — Fases 90 a 96

O plano e a especificação para a aba **Texto** virar a bancada onde se corrige o texto de um
livro: o impresso à esquerda, o editor à direita, uma fita de edição no alto, e **nenhum trabalho
perdido ao passar de uma folha para a outra**. As duas partes moram neste arquivo — a Parte I é o
plano, a Parte II é a especificação item a item (S-601 a S-668) — e a razão de não haver um
`SPEC_*.md` separado está em [Onde a spec mora, e quando ela muda de casa](#onde-a-spec-mora-e-quando-ela-muda-de-casa).

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
| S-646 | ⏳ | Os três pré-requisitos (a guarda de atalhos por janela, o painel fora da `QScrollArea`, o `_focar_aba`) seguem como estavam; o R1 decide se ela é pedida |
| S-620 | ✅ com desvio | «Diagramas no texto à esquerda (o padrão é ao centro)», interruptor do menu Texto, guardado em `AppState.texto_diagramas` (e não em Configurações, pelo motivo da S-640). Trocar redesenha sem tornar a folha «por gravar», e a marca com alinhamento escrito vence as duas. A guarda S-603 lê o alinhamento efetivo pela mesma função |
| S-621 | ✅ com desvio | Três comandos do menu Texto para a folha (à esquerda, ao centro, como a preferência), um passo de desfazer. O do caderno inteiro está no **menu do botão direito do índice**, com a pergunta «Alinhar 41 diagrama(s) de 23 folha(s) à esquerda?» e a versão de antes de cada folha como `anterior` |
| S-622 | ✅ | O `.html` e o `.rtf` já seguiam o efetivo; o `.md` põe a figura num `<p align="center"><img …></p>` quando ela não está à esquerda, e mantém o `![…](…)` à esquerda. A exportação recebe a preferência (`exportar(…, diagramas=…)`) |
| S-623 | ✅ com desvio | Pequenas · médias · grandes (160 · 240 · 320 px no corpo do sistema), **médias por padrão** — a miniatura de hoje cresceu de 160 para 240. Um comando que anda em roda, «Tamanho das miniaturas dos diagramas», em vez de três; guardado em `AppState.texto_miniatura` |
| S-624 | ⏳ | O portão pede o protótipo medido em dez folhas reais de cinco livros, com o código declarado (S-218); não foi feito |

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
| **Um segundo modelo para negrito e itálico** | "A resposta é geometria sobre a binária, como o pendor do itálico já é — não uma segunda rede" | A geometria foi medida em 2026-08-29 sobre 20.156 palavras de 14 livros, com o corte aprendido fora do livro: precisão máxima utilizável 0,839, e **apertar o corte não compra precisão** (`text/negrito.py`, `docs/metrics/texto_negrito_imagem.json`). A premissa da recusa caiu. A Fase 96 reabre a pergunta com portão: se o classificador não passar, a recusa volta com número novo. |

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

Cada item traz o problema (com número quando há), a decisão, onde mora, e o **critério de aceite**,
escrito para virar teste. "Puro" quer dizer sem toolkit: o módulo importa sem PyQt e o teste dele
roda sem `QApplication`.

## Fase 90 — O desenho obedece ao documento

### S-601 · O formato de parágrafo é escrito no bloco do parágrafo, e não no do separador

**Problema.** O D1: a corrida separadora apaga o `QTextBlockFormat` do parágrafo anterior.

**O modelo, dito antes da regra.** Para `rico`, **parágrafo é bloco** (`Corrida.bloco`), e não bloco
do Qt: depois de um `Enter` no meio de um parágrafo lido, os dois blocos do Qt continuam no mesmo
bloco de `rico`, e alinhar um alinha os dois. Texto sem bloco (`SEM_BLOCO`, o digitado num documento
vazio) é a exceção: ali `aplicar_no_paragrafo` só escreve nas corridas que alcança.

**Decisão.** A corrida separadora **não toca o bloco do parágrafo que termina**: ela escreve suas
quebras com `cursor.insertBlock(bloco_de(PADRAO), formato)`, uma por `\n`, e os blocos em branco
que ela cria saem com o formato vazio. A corrida de texto escreve o formato do bloco em que começa,
como hoje. **A regra óbvia — "o separador não escreve formato nenhum" — foi testada pela primeira
revisão e está errada:** a linha em branco herda o centro e a margem de título do parágrafo de cima,
e o `Enter` dado nela é engolido (o Qt só redefine o formato do bloco, e nem a tela nem o documento
ganham a linha). Ela também faria cada caractere separador discordar do documento na guarda S-603.

**Onde.** `qt/painel_de_texto.py::_desenhar` e o caminho rápido da digitação (`_pintar_o_digitado`),
que repinta o trecho digitado sem redesenho e precisa obedecer à mesma regra.

**Critério de aceite.**
- numa folha de **três parágrafos de texto**, cada valor de `rico.ALINHAMENTOS` e cada estilo de
  `rico.ESTILOS`, aplicado ao primeiro, ao do meio e ao último, aparece no bloco desenhado; o estilo
  `notacao` é conferido pela família da letra (ele não tem recuo — `bloco_de` não escreve nada para
  ele);
- as linhas em branco entre parágrafos saem `AlignLeft`, sem recuo e sem margem;
- `Enter` na linha em branco depois de um título centralizado insere a linha, na tela e no documento;
- o novo teste **reprova** no ramo avaliado (é o teste do D1) e passa depois do conserto; os testes
  que afirmam só `bloco_de` continuam.

### S-602 · A miniatura mora no bloco da marca

**Problema.** O D2: a imagem do diagrama herda o bloco do parágrafo anterior.

**Decisão.** `_inserir_miniatura` escreve `cursor.setBlockFormat(bloco_de(marca.atributos))`
**antes** de `insertImage`: a figura fica no bloco em branco que o separador anterior já deixou, agora
com o formato da marca, e a marca `[Diagrama N]` no bloco seguinte com o mesmo formato. Figura e
marca andam juntas, como o WordCraft faz com a imagem embutida (o alinhamento da imagem **é** o do
parágrafo dela). **Só quando o cursor não está no começo do bloco** (`positionInBlock() > 0`) a
figura ganha um bloco próprio — o caso existe: `rico.editar` deixa apagar o separador e produzir
`Antes.[Diagrama 1]`, e aí a figura cairia no meio da prosa. Um bloco extra incondicional poria uma
linha em branco a mais por diagrama e um `\n` solto em todo texto copiado.

**Critério de aceite.**
- com a marca em `centro`, `esquerda` e `direita`, o bloco que contém o `OBJETO` e o bloco da marca
  têm o mesmo alinhamento, e o da imagem tem `textIndent() == 0` mesmo depois de prosa;
- numa folha com três diagramas — um deles **sem separador antes** —, a tradução posição →
  deslocamento, `_marca_sob` e o clique na miniatura continuam certos, e copiar a folha não traz
  linha em branco a mais;
- a S-601 e a S-602 entram no mesmo commit (ver o D2).

### S-603 · A guarda de paridade entre documento e desenho

**Problema.** As funções puras e o widget são testados separados, e o defeito mora entre os dois.

**Decisão.** Um leitor de volta, só para teste: `tests/paridade_do_texto.py` percorre o
`QTextDocument` desenhado e, pelo `_Mapa`, devolve para cada deslocamento de documento o que a tela
mostra — negrito, itálico, sublinhado, tachado, cor, realce, corpo em pontos, alinhamento, estilo
(título, prosa e legenda pelo recuo e pela margem; notação pela família da letra). O que ele compara
é o modelo da S-601: o formato de parágrafo vale por **bloco de `rico`**, e todos os blocos do Qt de
um mesmo bloco de `rico` têm de concordar. Um teste gera folhas com combinações de atributos (laço determinístico sobre os
conjuntos fechados de `rico`, sem sorteio) e afirma que **cada caractere** concorda com o documento.
O mesmo leitor é chamado depois de: desenho inicial, cada ferramenta da barra, digitação de uma
palavra, `Enter` no meio de parágrafo centralizado, `Enter` na linha em branco depois de um título,
desfazer, refazer, zoom e reabertura do `.cvtxt`.

**A regra que a guarda impõe ao resto do plano:** cada atributo novo (por exemplo o alinhamento
efetivo do diagrama na S-620, a sugestão de estilo na S-664) entra no leitor de volta no mesmo
commit em que entra no documento.

**Critério de aceite.** A guarda pega o D1 e o D2 quando os consertos são revertidos (o teste é
rodado uma vez contra o código antigo e o resultado vai ao commit), e passa depois.

### S-604 · A sonda vira teste, e a conferência vira regra de revisão

**Decisão.** A sonda usada neste documento (folha de três blocos, leitura do `QTextBlockFormat`)
entra como teste nomeado em `tests/test_qt_texto_paridade.py`. E o `CONTRIBUTING.md` ganha uma
linha na seção de interface: *ferramenta de formato só se dá por entregue com a guarda S-603
passando para o atributo dela*.

**Critério de aceite.** O teste existe, roda em menos de 2 s sob `offscreen`, e o `CONTRIBUTING.md`
cita a S-603.

### S-605 · O remendo do D3 enquanto o caderno não chega

**Decisão.** Dois consertos pequenos, que a Fase 91 depois absorve:
- `ler()` e `abrir_documento()` chamam `gravar_rascunho()` **antes** de perguntar, como
  `confirmar_fechamento` já faz — a pergunta continua, e o "Sim" deixa de apagar a última correção;
- `rascunho.gravar` deixa de podar. A poda saiu inteira (`podar` e `TETO_POR_DOCUMENTO`): documento
  sem folha de origem nem chega a ter rascunho, então não havia rascunho que ela devesse cortar.

**Critério de aceite.** Corrigir uma palavra e, antes dos 4 s, ler outra folha respondendo "Sim":
o rascunho da folha corrigida existe. Gravar rascunhos de 12 folhas do mesmo livro deixa 12.

## Fase 91 — O caderno do livro

### S-610 · O caderno: uma folha corrigida por arquivo, sem poda

**Problema.** O D3. O trabalho mora no rascunho, e o rascunho é podado a oito.

**Decisão.** Módulo puro novo, `text/caderno.py`:

- **onde:** `config.DATA_DIR / "cadernos" / <chave-do-livro>` — derivado de `DATA_DIR`, nunca de
  `RAIZ / "data"`, que é o que faz o `CVOFF_DATA_DIR` da suíte desviá-lo sem linha nova. A chave é a
  parte de livro de `rascunho.chave_de` (nome legível + impressão do caminho resolvido), fatorada
  numa função própria, porque a de hoje traz a folha embutida (`_f{n}`);
- **o livro é procurado pela identidade, e o caminho é apelido.** A chave pelo caminho órfã o
  caderno quando o PDF é movido, e dá **dois** cadernos que divergem quando o mesmo livro está em
  duas pastas — e o acervo tem livros duplicados. O `indice.json` guarda a **identidade de
  conteúdo** do PDF (número de folhas e um resumo dos bytes das primeiras folhas); abrir um livro
  procura primeiro pela identidade, e o caminho de onde ele foi aberto é anotado como apelido no
  índice. A mesma identidade serve à deduplicação de livro da S-661;
- **uma instância escreve.** O programa não tem trava de instância única (não há `QLockFile` nem
  `QLocalServer` em `src/`): duas janelas abertas no mesmo livro gravariam a mesma folha, a última
  vence, e o `indice.json`, lido-mudado-gravado pelas duas, perderia estados. O caderno cria
  `caderno.lock` com criação exclusiva (PID dentro; vencido se o processo não existe mais); a
  segunda instância abre o caderno **só para leitura**, com uma faixa dizendo por quê. O índice pode
  ser refeito a partir dos arquivos, e é refeito quando não abre;
- **o que:** `folha-0012.cvtxt` por folha (o formato que já existe, `text/arquivo.py`, com a
  procedência humana aplicada na gravação) e um `indice.json` com, por folha: estado (`lida`,
  `editada`, `conferida`), motor e modo da leitura, data da última gravação, número de correções;
- **como grava:** em temporário, relê e compara com o que se quis gravar, renomeia por cima; o
  arquivo anterior só sai depois de o novo validar (a escrita de recuperação do WordCraft,
  `docs/recovery.md`). Falha de gravação vai ao rodapé e **não** apaga nada;
- **sem poda.** O caderno é trabalho, não cache. O tamanho é o do texto: uma folha corrigida tem
  poucos KB, e um livro de 300 folhas cabe em poucos MB.

API pura: `abrir(livro) -> Caderno`, `Caderno.folha(n) -> DocumentoRico | None`,
`Caderno.gravar(doc)`, `Caderno.difere(doc) -> bool`, `Caderno.marcar(n, estado)`,
`Caderno.folhas() -> tuple[EstadoDaFolha, ...]`, `Caderno.anterior(n)`, `Caderno.lida(n)` (ver
S-612 e S-616).

**Quem segura o caderno é a janela**, e não o painel: a mesa (S-641, S-644), o índice (S-613) e o
caminho para a suíte (R7) perguntam a ele, e o painel recebe o caderno do livro aberto por
`definir_livro`, como hoje recebe o PDF. A decisão "há o que gravar?" é a função pura
`Caderno.difere`; o painel só a chama. Testes em `tests/test_texto_caderno.py` (puro) e
`tests/test_qt_texto_caderno.py` (a fiação).

**Critério de aceite.**
- gravar 300 folhas de um livro deixa 300 arquivos e um índice que as lista;
- uma gravação interrompida entre o temporário e o renome deixa a versão anterior legível;
- mover o PDF de pasta e abri-lo abre o caderno de antes, com as correções; o mesmo livro aberto de
  duas pastas abre **um** caderno;
- com `caderno.lock` de um processo vivo, uma segunda abertura não grava nada e diz por quê; com o
  de um processo morto, a trava é retomada;
- a suíte grava sob o `CVOFF_DATA_DIR` desviado; a tabela de persistência de
  `docs/ARCHITECTURE.md` lista `data/cadernos/` (a guarda confere a pasta `data/` do checkout real).

### S-611 · Sair de uma folha a guarda, sem perguntar

**Decisão.** Toda troca do documento na tela — ler outra folha, abrir um `.cvtxt`, virar a página
com a mesa acompanhando, trocar de livro, fechar — passa antes por `_guardar_a_folha()`, que grava no
caderno **se** o documento difere do que o caderno tem. A pergunta "descarta as alterações?" sai
desses caminhos — incluindo `abrir_documento` —, porque não há mais o que descartar. O relógio de
inatividade passa a gravar no caderno, com a régua da S-612; o rascunho da S-255 fica só para
documento **sem** folha de origem.

**Gravar sem perguntar exige uma rede.** `Ctrl+A`, `Del` e virar a página gravariam a folha vazia
por cima da boa. Por isso **a primeira gravação depois de cada abertura da folha** gira o arquivo
de antes para `folha-NNNN.anterior.cvtxt` — a versão como ela estava quando a pessoa chegou — e as
gravações seguintes da mesma visita só reescrevem a atual. "Voltar à versão anterior desta folha"
(S-612) a traz de volta. E uma folha **vazia** não é gravada por cima de uma que tem texto: ela vira
`anterior` e a S-616 pergunta.

**Critério de aceite.**
- corrigir uma palavra e clicar "Ler folha" para a folha seguinte **antes** dos 4 s: a correção está
  no caderno, sem caixa nenhuma aberta (o teste patcheia `QMessageBox` para reprovar se abrir);
- o mesmo para trocar de livro e para fechar a janela;
- abrir a folha 3, apagar tudo e ir à folha 4: a folha 3 do caderno continua com o texto, e a versão
  vazia não sobrescreveu nada.

### S-612 · Voltar a uma folha abre o que foi feito nela

**Decisão.**
- **"Ler folha" com a folha no caderno abre o caderno**, sem motor. O texto entra na hora; as
  miniaturas esperam a folha rasterizada, que vem do visualizador quando ele já a tem (`definir_fornecedor_de_folha`) ou
  da thread de trabalho — **não** do `_renderizar` síncrono que `abrir` faz hoje na thread da janela
  (`painel_de_texto.py:1413-1416`), que congelaria a troca de folha. O botão passa
  a dizer **"Abrir folha"** quando a folha tem caderno e **"Ler de novo"** fica no menu dele;
- **trocar o motor ou o modo bloco e clicar "Ler folha"** numa folha em estado `lida`, sem nenhuma
  correção, lê de novo sem perguntar: quem mudou o motor quer a leitura nova, e não há trabalho a
  perder. Com correções, vale o item seguinte;
- **"Ler de novo" sobre uma folha com correções** é o único caminho que ainda pergunta, e a pergunta
  diz o tamanho da perda ("A folha 12 tem 7 correções. Ler de novo guarda esta versão como anterior e
  abre a leitura nova."). A versão substituída fica como `folha-0012.anterior.cvtxt` — um nível só,
  recuperável pelo menu ("Voltar à versão anterior desta folha");
- **a régua do salvamento automático** é a do WordCraft, e substitui os 4 s de
  `rascunho.ESPERA_SEGUNDOS` para o caderno: grava 2,5 s depois da última mudança **e** com o cursor
  parado há 1,5 s — quem está selecionando para negritar não está terminando. A troca de folha não
  espera relógio nenhum (S-611).

**Critério de aceite.**
- ler a folha 3, corrigir, ler a folha 4, voltar à 3: a correção está na tela, sem leitura e sem
  pergunta, e o rótulo do rodapé **no widget** (não a função `frase_do_rodape`) diz "Folha 3 do
  caderno · 1 correção";
- "Ler de novo" na folha 3 com correções pergunta uma vez; recusado, nada muda; aceito, a versão
  anterior é recuperável pelo menu.

### S-613 · O índice das folhas

**Decisão.** Um painel com as folhas do livro que têm caderno, cada uma com o estado (`lida` · ponto
cinza, `editada` · ponto de destaque, `conferida` · marca de visto), o número de correções e a data;
clique abre a folha. Comando novo "Marcar folha como conferida" (`Ctrl+Shift+Enter`, livre na
tabela em 2026-10-24). É o painel "Páginas" do painel de navegação do WordCraft, com a pergunta
deste projeto: **quanto do livro já foi conferido**. O rodapé ganha "34 de 289 folhas conferidas".

**Critério de aceite.** O estado de cada linha vem do `indice.json` (o painel não abre os `.cvtxt`);
marcar como conferida grava o índice e muda a linha, e `editor.document()` é o mesmo objeto antes e
depois (não houve redesenho). O painel mora em `qt/indice_do_caderno.py` e é o mesmo widget da aba
"Folhas" do painel de navegação (S-654).

### S-614 · O livro inteiro sai do caderno

**Decisão.** "Exportar o caderno" junta as folhas em ordem num `.md`, `.html` ou `.rtf`, com uma
quebra e o número da folha entre elas, e os diagramas como cada exportador de folha já faz (S-250 a
S-253). A função pura junta os `DocumentoRico`; os exportadores não mudam. Folhas sem caderno são
puladas e listadas no relatório ("faltam as folhas 1-4, 17"). O PDF pesquisável do livro inteiro
(S-253) passa a usar o texto do caderno onde ele existe.

**Critério de aceite.** Exportar um caderno de 3 folhas com 2 diagramas dá um `.md` com as 3 folhas
na ordem, 2 imagens ao lado e nenhuma folha duplicada; a lista de faltantes está no relatório.

### S-615 · Os rascunhos de hoje entram no caderno

**Decisão.** Na primeira abertura de um livro depois desta fase, cada rascunho de `data/rascunhos/`
desse livro entra no caderno **se** a folha não tiver caderno mais novo; o rascunho é mantido até a
gravação no caderno validar, e só então descartado. A poda a oito deixa de ser chamada pela aba.

**Critério de aceite.** Um rascunho de ontem da folha 5 vira `folha-0005.cvtxt` sem pergunta; um
rascunho mais velho que o caderno não sobrescreve nada e é descartado com uma linha no log.

### S-616 · O `.cvtxt` avulso continua

**Decisão.** "Salvar como…" e "Abrir texto…" continuam gravando e abrindo um `.cvtxt` onde a pessoa
quiser — é o arquivo para mandar a alguém. Abrir um `.cvtxt` do livro aberto oferece "Trazer para o
caderno desta folha", que é uma gravação como as outras (com a versão anterior guardada).

**E jogar fora continua possível, de propósito.** "Descartar as correções desta folha" devolve a
folha ao que o motor leu: a primeira leitura de cada folha é guardada imutável como
`folha-NNNN.lida.cvtxt`, e descartar a põe na tela como edição (um `Ctrl+Z` desfaz, e a versão
corrigida vira `anterior`). É a resposta para quem corrigiu uma folha errada e quer recomeçar — a
pergunta "descarta?" que sai dos caminhos de troca volta aqui, onde ela é o gesto pedido.

**Critério de aceite.** Descartar uma folha com 5 correções mostra a leitura do motor com 0
correções, o caderno guarda a versão corrigida como `anterior`, e `Ctrl+Z` traz as 5 de volta. O
`.lida.cvtxt` não muda com nenhuma gravação.

## Fase 92 — Os diagramas: centro por padrão, esquerda por escolha

### S-620 · A preferência "Diagramas no texto"

**Problema.** A marca do diagrama aceita alinhamento, mas não há padrão, e `""` desenha à esquerda.

**Decisão.** Preferência nas Configurações e no grupo Parágrafo da fita: **Diagramas no texto:
centralizados (padrão) · à esquerda**. Ela decide como se desenha e se exporta a marca cujo
alinhamento é `""` — "ninguém escolheu". Alinhamento escrito na marca vence a preferência, pela
mesma distinção que `rico` já documenta entre `""` e `esquerda`. A resolução é pura:
`rico.alinhamento_efetivo(corrida, preferencia) -> str`, chamada pelo desenho (S-602) e por todos os
exportadores — o que muda a assinatura deles (recebem a preferência) e **muda a saída de hoje**: a
marca `""` passa a sair centralizada nos `.html`/`.rtf` exportados. É a mudança pedida, e os testes
de exportação que afirmam o `""` de hoje são atualizados com ela, não apagados.

**Critério de aceite.**
- folha nova com três diagramas: os três blocos de imagem desenhados centralizados;
- trocar a preferência para "à esquerda" redesenha os três à esquerda **sem** tornar a folha "por
  gravar" (a preferência não é edição);
- um diagrama com `direita` escrito na marca fica à direita sob as duas preferências;
- a guarda S-603 lê o alinhamento efetivo.

### S-621 · Alinhar todos os diagramas da folha, ou do caderno

**Decisão.** Comandos "Diagramas desta folha: à esquerda / ao centro / como a preferência" (o
último limpa o que foi escrito nas marcas). Na folha é **um** passo de desfazer. No caderno inteiro
é um comando do índice (S-613), com a contagem antes ("Alinhar 41 diagramas de 23 folhas à
esquerda?") e a versão anterior de cada folha guardada como na S-611.

**Critério de aceite.** Na folha, um `Ctrl+Z` desfaz o alinhamento de todos; no caderno, a contagem
da pergunta é igual ao número de arquivos mudados, e cada um tem o seu `anterior`.

### S-622 · A exportação mostra o que a tela mostra

**Decisão.** O alinhamento efetivo chega a cada formato: `.html` (`style="text-align:…"` no bloco
da figura), `.rtf` (`\ql`/`\qc`), PDF pesquisável (posição da figura na página gerada) e `.md`
(que não tem alinhamento: a figura vai num `<p align="center">` só quando o alinhamento efetivo não
é `esquerda`, que é o que os visualizadores de Markdown respeitam). `.txt` não muda.

**Critério de aceite.** Para cada formato, um teste de exportação com um diagrama centralizado e um
à esquerda afirma a marcação de cada um.

### S-623 · O tamanho da miniatura

**Decisão.** Preferência **Pequeno · Médio · Grande** (160 · 240 · 320 px no corpo do sistema),
multiplicada pelo zoom como hoje (`_largura_da_miniatura`). O padrão é Médio: na mesa (S-640) o
editor tem a metade da tela, e 160 px é pequeno para conferir uma posição. É vista, e não documento:
não grava no `.cvtxt`, não muda a exportação. Chave `texto_miniatura` no estado da sessão.

**Critério de aceite.** Em Grande com zoom +2 a miniatura tem `round(320 × corpo da vista / corpo do
sistema)` px; trocar o tamanho não torna a folha "por gravar".

### S-624 · O diagrama à esquerda com o texto ao lado (com portão)

**Decisão.** Uma terceira opção, "à esquerda, com o texto ao lado", que é como muitos livros de
xadrez diagramam. O Qt a desenha com um `QTextFrame` de posição `FloatLeft` — é o "Square wrap"
simples, o único que o `QTextDocument` faz sem leiaute próprio. **Portão:** um protótipo mede, em 10
folhas reais (duas de cada um de cinco livros com diagrama ao lado do texto, escolhidas e listadas
em `docs/metrics/texto_flutuante.json`, com o código declarado como manda a S-218), se o cursor, a seleção, a digitação ao lado da figura e o `_Mapa` continuam certos
(a guarda S-603 inteira passando). Um custo já conhecido: o quadro flutuante põe `U+FDD0`/`U+FDD1`
no texto cru do documento, e `_texto_da_tela` só traduz `U+2029`/`U+2028` — sem tratá-los,
`_digitado` e `_trocado` os leriam como texto digitado. Se o protótipo não passar, a opção sai do
plano e a razão fica escrita aqui.

## Fase 93 — A letra da aba

### S-630 · O zoom à vista

**Problema.** O zoom existe (−3 a +8 degraus, `Ctrl+roda`, `Ctrl++`/`Ctrl+-`, gravado no estado), e
o pedido "opção para aumentar e diminuir a fonte" diz que ninguém o achou.

**Decisão.** No **rodapé de hoje** da aba (o `QLabel` do `frase_do_rodape`, que ganha uma linha
horizontal com o controle à direita) — e não na barra de estado da S-655, que só chega na Fase 95 —,
o controle do WordCraft: botão `−`,
régua, botão `+` e o valor em **porcentagem** de largura fixa ("100%", "135%"). A porcentagem é a
razão entre o corpo da vista e o do sistema — a mesma conta de `tipografia.corpo` — e não um número
novo; clique no valor volta a 100%. `Ctrl+roda` passa a **manter sob o ponteiro a linha que estava
sob ele** (hoje mantém o cursor). Os limites continuam `ZOOM_MINIMO`/`ZOOM_MAXIMO`, e o estado
continua `texto_zoom`. **A régua tem 12 paradas, e não são iguais:** `tipografia.corpo` não desce
de 7 pt, então numa fonte de sistema de 9 pt os degraus −3 e −2 dão o mesmo tamanho. A régua mostra
as paradas que existem (degraus que dão o mesmo corpo viram uma parada só), em vez de prometer uma
escala contínua que o desenho não tem.

**Critério de aceite.** O controle mostra o valor gravado ao abrir; mexer nele e na roda dá o mesmo
resultado; o texto e a miniatura crescem juntos (a regra da S-264); `accessibleName()` é "Zoom do
texto" e `accessibleDescription()` contém "135 por cento".

### S-632 · A letra de leitura

**Decisão.** Preferência da vista (chave `texto_familia` no estado da sessão, ao lado de
`texto_zoom`): **a família da letra da folha** — a proporcional do tema
(padrão), uma serifada do sistema (mais perto do impresso, útil para conferir lado a lado na mesa)
ou a monoespaçada (que separa `l`/`1`/`I` e `O`/`0`, que é onde o OCR mais erra). É vista: não
grava, não exporta. A notação continua na monoespaçada, como hoje.

**Critério de aceite.** Trocar a família redesenha a folha com ela (a guarda S-603 lê a família),
não torna a folha "por gravar" e sobrevive a reabrir o programa.

## Fase 94 — A mesa de texto

### S-640 · A disposição de mesa na janela principal

**Decisão.** Com o modo **Texto** à frente, a janela troca a disposição do divisor (`self.divisor`,
`qt/janela.py:525`): **o visualizador do PDF vai para a esquerda e o lado do trabalho, com o
editor, para a direita**, e as larguras passam a ser as da mesa (padrão 45/55, em vez da coluna
mínima de hoje). Ao sair do modo Texto, a disposição de antes volta. As duas frações vão para o
estado da sessão, cada uma com a sua chave, como o divisor de hoje (S-156).

Não há janela nova, não há widget movido e não há guarda de atalhos nova: o PDF à esquerda **é** o
visualizador, com as caixas dos diagramas, a rolagem e o sincronismo de folha (`folha_pedida`,
`definir_fornecedor_de_folha`) que já funcionam.

**A troca de lados não pode desorientar.** Trocar o divisor a cada troca de modo reflui a janela
inteira: o visualizador muda de largura, reajusta e pode saltar de rolagem, e a memória de onde
está cada coisa se inverte. Por isso: a preferência tem **três posições** — "Mesa ao abrir o Texto"
(padrão), "Mesa sempre" e "Nunca" (R1); a página, o zoom e o ponto de rolagem do visualizador
sobrevivem à troca nos dois sentidos; e chamar o Texto de outro lugar (a paleta de glifos usa
`_focar_aba(self.texto)`, `qt/janela.py:1683`) também aplica a disposição, por um caminho só. O
sinal é o `modo_mudou` do `PainelPrincipal` (`qt/painel_principal.py`), que a janela já recebe.

**Critério de aceite.**
- ativar o modo Texto põe o visualizador à esquerda e o editor à direita; voltar ao modo Resultado
  devolve a disposição e a fração de antes;
- as duas frações sobrevivem a fechar e abrir o programa;
- a página, o zoom e o ponto de rolagem do visualizador são os mesmos antes e depois da troca;
- com "Nunca", nada muda em relação a hoje;
- o `Tab` percorre visualizador → barra do editor → editor → rodapé (portão `teclado`), e nenhum
  atalho muda de dono (a guarda é a mesma, a janela é a mesma).

### S-641 · A folha que o editor tem, no visualizador

**Decisão.** Com a mesa ativa, o visualizador mostra **a folha do documento que está no editor** —
abrir um `.cvtxt` ou uma folha do caderno leva o visualizador até ela (o `folha_pedida` de hoje
passa a valer também para o caderno). O contrário continua: virar a página no visualizador é a
S-644. Sem PDF (o `.cvtxt` de um livro que não está no lugar), o lado esquerdo mostra a miniatura
grande da folha se ela estiver no caderno, ou o estado vazio com a frase de hoje ("o livro … não está
no lugar de antes").

**Critério de aceite.** Abrir do caderno a folha 7 com o visualizador na 3 leva o visualizador à 7;
abrir um `.cvtxt` de outro livro não mexe no visualizador.

### S-642 · A folha e o texto apontam um para o outro

**O que existe para apontar.** A `Corrida` tem `texto`, `atributos`, `faixa`, `bloco`,
`procedencia` e `tipo` — **não tem linha nem `bbox`**. O que liga um trecho à folha é o `bloco`, e o
`bbox` do bloco está em `origem.blocos[bloco].bbox`. O texto digitado **herda** o `bloco` do vizinho
(`_da_mao`, `rico.py:1127`), e a `procedencia="humano"` não o separa (formatar texto lido também a
carimba). Por isso o plano tem duas etapas.

**Etapa 1 — por bloco, com o que existe.**
- **cursor no texto → contorno na folha:** o bloco (parágrafo) de onde veio o trecho sob o cursor
  ganha um contorno no visualizador, que rola até ele;
- **clique na folha → cursor no texto:** clicar dentro do `bbox` de um bloco põe o cursor no começo
  dele;
- **o diagrama também:** a miniatura selecionada contorna o diagrama na folha (a caixa que o
  visualizador já desenha fica em destaque), e o duplo clique no diagrama da folha seleciona a marca.

A tradução é pura: `rico.bloco_em(doc, deslocamento) -> int | None` e
`rico.deslocamento_do_bloco(doc, bloco) -> int | None`; o `bbox` em pontos vira pixel pelo DPI da
folha, como em `_recorte_da_folha`.

**Etapa 2 — por linha, só se a etapa 1 provar valor.** Precisa de uma origem por caractere que
sobreviva a `fundir`, ao fatiamento e a `editar`, e que o `.cvtxt` grave — mudança de formato
(R5). A alternativa sem mudar o formato é derivar a linha comparando o texto do
bloco com `bloco.linhas`, como `text/correcao.py` já compara bloco a bloco; ela erra onde a pessoa
reescreveu a linha, e aí a resposta é o bloco.

**Critério de aceite (etapa 1).** Numa folha sintética de três blocos com `bbox` conhecidos: o
cursor em cada bloco contorna o `bbox` dele convertido pelo DPI; o clique no centro de cada `bbox`
põe o cursor no começo do bloco; um documento sem `origem` não contorna nada e não levanta.

### S-643 · O bloco impresso ampliado

**Decisão.** Opcional e ligado por padrão na mesa: uma faixa acima do editor com o **recorte
impresso do bloco** sob o cursor, na largura do editor. Quem corrige OCR compara a letra impressa e
a lida sem atravessar a tela com os olhos. Na etapa 2 da S-642 a faixa desce à linha, e fica com a
altura de duas linhas de texto. Sem origem, a faixa some.

**Critério de aceite.** Com o cursor no segundo bloco de uma folha sintética, a faixa mostra o
recorte do `bbox` dele (pixel a pixel igual ao de `_recorte_da_folha`); num documento sem folha, a
faixa está escondida.

### S-644 · Folha e texto andam juntos

**Decisão.** Virar a página no visualizador com a mesa ativa: guarda a folha que sai (S-611), abre
a que entra do caderno se ela tiver (S-612), ou mostra "Ler a folha 13" no estado vazio se não tiver
— **não** lê sozinha (ler custa de 1 s a 40 s e é decisão de quem lê). Não há atalho novo de folha:
a navegação é a do visualizador, que já tem as teclas dela (`Ctrl+PgUp`/`Ctrl+PgDn` são "página
duvidosa", `ui/atalhos.py:179-180`, e continuam sendo). Preferência "Ler ao chegar numa folha sem
caderno", desligada por padrão, para quem corrige um livro do começo ao fim com o motor rápido.

**Critério de aceite.** Virar para a folha 13 sem caderno: o editor mostra o estado vazio "Ler a
folha 13", `ler` não é chamado, e a folha que saiu está no caderno. Virar para uma folha com caderno
mostra o texto dela sem leitura.

### S-645 · A mesa sem PDF e sem tela grande

**Decisão.** Sem livro aberto, a mesa mostra o editor e, à esquerda, o estado vazio do visualizador
com o botão "Abrir PDF". Com a janela abaixo de 1.000 px de largura, a disposição de mesa não se
aplica e a de hoje fica (a faixa da S-643 continua) — o divisor não é espremido abaixo do mínimo de
nenhum dos dois lados. O limiar é avaliado **ao entrar no modo Texto**, e não a cada
redimensionamento: arrastar a borda da janela não troca os lados no meio do trabalho.

**Critério de aceite.** A 999 px o modo Texto mantém a disposição de hoje; a 1.200 px aplica a da
mesa; redimensionar com o modo ativo não troca os lados; sem PDF, o lado esquerdo tem o botão "Abrir
PDF" e o editor funciona.

### S-646 · Destacar a mesa numa janela própria (depois, com pré-requisito)

**Decisão.** Um comando "Destacar a mesa" leva o editor e uma vista da folha para um `QMainWindow`
próprio — para quem tem dois monitores. **Só entra depois de três pré-requisitos**, que a primeira
revisão achou lendo a fiação:

1. **a guarda de atalhos conhece janelas.** `GuardaDeAtalhos` é instalada na aplicação
   (`qt/atalhos.py:288`) e `ui/atalhos.destino` (`:577`) não pergunta `foco.window()`: com o foco
   na vista da folha da segunda janela, `Del` apagaria a casa do diagrama da janela principal, as
   setas e `PgUp`/`PgDn` virariam a página dela e `Ctrl+N`/`Ctrl+D`/`Ctrl+G` agiriam sobre a fila,
   o diagrama e a anotação. A guarda passa a rotear pela janela do foco, com teste;
2. **o painel sai da `QScrollArea` do modo.** O `PainelDeTexto` mora dentro da área de rolagem do
   `PainelPrincipal`, com `seguir_o_foco` (`qt/painel_principal.py:96-127`): mover é `takeWidget()`
   / `setWidget()` e um cartão no lugar ("O texto está na mesa · Mostrar · Trazer de volta"), e não
   um `setParent`;
3. **quem chama `_focar_aba(self.texto)`** (`qt/janela.py:1683`, usado pela paleta de glifos em
   `:1719`) passa a trazer a mesa para a frente, e não o cartão.

**Critério de aceite.** Destacar e devolver dez vezes não perde seleção, pilha de desfazer nem zoom;
com o foco na segunda janela, `Del`, setas, `PgUp`/`PgDn` e `Ctrl+N` não mudam nada na janela
principal; fechar a principal fecha as duas e grava o caderno.

## Fase 95 — A fita e os painéis

### S-631 · O tamanho em pontos na fita

**Mora na Fase 95**, apesar do número: a caixa é do grupo Fonte da fita (S-650), e deixá-la na
Fase 93 fazia a 93 depender da 95 e a 95 da 93.

**Decisão.** A caixa de tamanho do grupo Fonte mostra o corpo do **parágrafo** sob o cursor em
pontos (o degrau traduzido por `tipografia.corpo`) e aceita um valor; o valor vira o degrau mais
próximo. Seleção que cobre parágrafos de corpos diferentes mostra a caixa vazia (a regra do negrito
misto). `A+`/`A−` são os `aumentar_corpo`/`diminuir_corpo` de hoje. **Não** há tamanho por trecho —
ver o R3.

**Zoom e corpo não podem ser confundidos**, e é o risco do pedido "aumentar a fonte": o `A+` muda o
documento e a exportação, o zoom muda só a tela. A caixa se chama **"Corpo do parágrafo (pt)"**, a
dica de `A+`/`A−` diz "muda o documento", e o zoom se chama **"Zoom"** e mostra porcentagem.

**Critério de aceite.** Com o cursor num parágrafo de corpo +2, a caixa mostra o corpo em pontos;
digitar outro valor muda o documento num passo de desfazer e a guarda S-603 vê o corpo novo; com a
seleção cobrindo corpos diferentes, a caixa fica vazia.

### S-650 · A fita da mesa, declarada como dado

**Problema.** A barra de hoje tem os comandos e não tem a forma: botões de texto numa linha que
quebra, sem grupos nem ícones de formato.

**Decisão.** Um módulo puro, `ui/fita_do_texto.py`, declara as abas e os grupos da fita da mesa
**com os nomes do catálogo** (S-324): cada item é um `acao` que existe em `ui/comandos.py` e em
`COMANDOS_DA_ABA`. A fita da janela principal tem um conjunto **fechado** de grupos (`comandos.GRUPOS`)
e não é tocada; esta é uma declaração à parte, e o widget reusa a `BarraFluida` (`qt/barra.py`) e o
desenho de grupo de `qt/fita.py`. Como em `fita.montar`, comando declarado sem função levanta `KeyError` na
montagem.

| aba | grupo | comandos (os novos em **negrito**) |
|---|---|---|
| Página inicial | Área de transferência | colar, recortar, copiar, **pincel de formatação** |
| | Fonte | **tamanho (pt)**, aumentar/diminuir corpo, caixa (MAIÚSCULAS/minúsculas/Iniciais), limpar formatação, negrito, itálico, sublinhado, tachado, cor da letra, realce |
| | Parágrafo | alinhar à esquerda/centro/direita, justificar, **diagramas: centro/esquerda** (S-620), **marcas de formatação ¶** |
| | Estilos | **galeria** (S-651) |
| | Edição | achar, substituir, selecionar tudo |
| Inserir | Xadrez | figurina, avaliação, paleta de glifos |
| | Diagrama | **alinhar os diagramas da folha** (S-621), **tamanho da miniatura** (S-623) |
| Leitura | Folha | folha a ler, motor, modo bloco, ler folha / abrir folha / **ler de novo** (S-612) |
| | Caderno | **marcar como conferida**, **voltar à versão anterior**, **exportar o caderno** |
| Revisão | Léxico | conferir (ligar/desligar), **próxima fora do léxico**, **acrescentar ao léxico do livro** (S-657) |
| | Correções | **lista das correções da folha** |
| Exibir | Mostrar | **painel de navegação**, **mesa** (S-640), **bloco impresso** (S-643), quebra de linha |
| | Zoom | aproximar, afastar, 100% |
| | Foco | **modo foco** (S-658) |

A aba **Arquivo** é o menu de hoje (abrir, salvar, salvar como, exportar `.txt`/`.md`/`.html`/`.rtf`/PDF
pesquisável). A barra de acesso rápido, no título da mesa, tem salvar, desfazer e refazer — a do
WordCraft (`crates/engine/src/ribbon.rs:24`).

**Dois confortos do WordCraft que entram junto:** a paleta de glifos mostra primeiro os **20
usados por último** (gravados no estado da sessão), e os botões de cor da letra e de realce são
**botões partidos que lembram a última cor** — o clique no botão aplica a mesma de antes, a seta
abre a lista.

**Os botões de estado mostram o estado.** Negrito, itálico, sublinhado, tachado e os quatro
alinhamentos ficam marcados conforme o que vale sob o cursor, pela regra que `_seguir_o_cursor` já
usa (`rico.valor_em_todo`; misto = desmarcado) — com uma exceção: `valor_em_todo` pula a marca do
diagrama, então os botões de alinhamento sobre uma marca leem `rico.alinhamento_efetivo` (S-620), e
não ficam em branco.

**Critério de aceite.**
- todo comando de `COMANDOS_DA_ABA` aparece na fita ou no menu Arquivo — o inventário da S-256
  cobra, **lendo a declaração**, e não uma lista literal no teste;
- todo botão tem nome acessível por extenso e dica com a tecla (S-165/F9-C2);
- com o cursor num trecho negrito centralizado, "negrito" e "centro" estão marcados.

### S-651 · A galeria de estilos

**Decisão.** Os quatro estilos de `rico.ESTILOS` mais "(sem estilo)", cada um desenhado **no próprio
estilo** — o nome "Título" em corpo de título, "Notação" na monoespaçada —, como a galeria da
imagem. O estilo sob o cursor fica marcado. A amostra é desenhada por `texto_formato`, a mesma
função da folha: a galeria não pode mostrar um estilo que a folha não desenha (é a guarda S-603
aplicada à amostra).

**Critério de aceite.** Cada amostra da galeria passa no leitor da S-603 com o formato do estilo
dela; com o cursor num título, a amostra "Título" está marcada.

### S-652 · Fita compacta e fita recolhida

**Decisão.** A fita da mesa usa o orçamento de altura da S-228 e os dois modos que `qt/fita.py` já
tem (plena e compacta, trocados pela largura medida); `Ctrl+F1` recolhe a fita deixando só as abas,
como no Word. O estado guarda o recolhimento.

### S-653 · O pincel de formatação

**Decisão.** O comportamento do WordCraft (`cmd/edit.rs:776-826`): o clique captura os atributos de
**trecho** do começo da seleção (negrito, itálico, sublinhado, tachado, cor, realce) e os de
**parágrafo** (estilo, alinhamento, corpo); a próxima seleção recebe os de trecho, e os de parágrafo
só quando a seleção cobre parágrafos inteiros; cursor sem seleção pinta a palavra. Um clique arma
para um uso; duplo clique fixa; `Esc` desarma. Atalhos `Ctrl+Shift+C`/`Ctrl+Shift+V`, livres na
tabela em 2026-10-24 e declarados em `ui/atalhos.py` (o `test_ui_legenda` proíbe tecla literal fora
de lá). Puro: `rico.atributos_em(doc, deslocamento)` e
`rico.pintar(doc, inicio, fim, atributos, paragrafo: bool)`. A faixa de confiança **não** é copiada
— ela é do motor, não do autor (S-242).

**Critério de aceite.** Pincelar um trecho negrito-vermelho sobre uma palavra comum a deixa
negrito-vermelha no documento **e na tela** (o leitor da S-603), com o botão Negrito marcado, num
passo de desfazer, sem mudar a faixa dela.

### S-654 · O painel de navegação

**Decisão.** Um painel à esquerda do editor (ou recolhido), com três abas, como no WordCraft
(`panes.rs:120-310`):
- **Títulos** — os parágrafos de estilo `titulo` da folha, clique leva ao título;
- **Folhas** — o índice do caderno (S-613);
- **Resultados** — a busca da S-343 em lista, cada achado com 30 caracteres antes e 40 depois e o
  trecho em negrito; clique seleciona. A janela de busca de hoje continua para substituir.
Refeito na pausa da digitação (o relógio de sempre), e não por tecla. Mora em
`qt/painel_de_navegacao.py`; a aba "Folhas" é o widget de `qt/indice_do_caderno.py`.

**Critério de aceite.** Uma folha com dois títulos lista os dois, e o clique no segundo põe o
cursor nele; uma busca com 3 achados lista 3 linhas, e o clique na terceira a seleciona no editor.

### S-655 · A barra de estado da mesa

**Decisão.** Da esquerda para a direita: **folha** ("Folha 12 de 289", clique abre o campo de
folha), **palavras** ("357 palavras", ou "12 de 357" com seleção — contagem pura, cacheada pela
edição), **diagramas** ("3 diagramas"), **léxico** ("2 fora do léxico", clique vai à próxima),
**correções** ("5 correções sobre o que o motor leu"), **caderno** ("gravado às 14:32" ou "por
gravar"), e à direita o zoom da S-630. A frase transitória (o `estado` de hoje) aparece no lugar das
três do meio por 6 s, com o texto inteiro na dica — a regra do WordCraft. Ela **substitui** o
rótulo do rodapé de hoje: a frase de `frase_do_rodape` vira as caixas de folha, diagramas, correções e
caderno, e o controle de zoom da S-630 passa para a ponta direita.

**Critério de aceite.** Com 12 de 357 palavras selecionadas, a caixa diz "12 de 357 palavras"
(contagem pura testada à parte); o recado transitório some depois de 6 s (relógio do teste
parado, como `_relogio`).

### S-656 · O desfazer com rótulo

**Decisão.** Cada documento empilhado ganha o rótulo da ferramenta que o produziu ("Digitação",
"Negrito", "Alinhar ao centro", "Colar") — o `_aplicar` recebe o nome do comando. A barra de acesso
rápido mostra a lista dos últimos 20 passos ao lado do botão de desfazer, e escolher o quinto desfaz
cinco. A pilha continua de **documentos** (a decisão da Fase 36), e é por isso que isto é barato
aqui e caro no `QTextDocument` nativo.

**Critério de aceite.** Escolher o quinto passo da lista deixa o documento igual ao de cinco passos
atrás, a guarda S-603 passa, e a lista mostra os rótulos na ordem certa.

### S-657 · Corrigir pelo léxico

**Problema.** A conferência marca as palavras fora do léxico (S-209/S-293); corrigir cada uma é
selecionar e digitar.

**Decisão.** Três gestos:
- **próxima fora do léxico** (`F7`, livre na tabela) — vai à próxima marcada e a seleciona;
- **menu do botão direito numa palavra marcada** — até cinco **sugestões do léxico**, ordenadas por
  uma **distância de edição com pesos de OCR**, num módulo puro novo (`text/sugestao.py`) com a
  tabela de trocas explícita: `l`↔`/`, `rn`↔`m`, `tu`↔`m`, `c`↔`e`, `I`↔`l`↔`1`, `O`↔`0`, cada uma
  com a página que a mediu (`text/italico.py`, a memória do `tu` fundido). **Não** é
  `text/semelhanca.py`: aquele compara recortes de glifo pela imagem (S-213), e o documento não
  carrega os recortes. Mais "Acrescentar ao léxico do livro" e "Ignorar nesta folha";
- **léxico do livro** — um arquivo de palavras por livro dentro do caderno
  (`data/cadernos/<livro>/lexico.txt`), uma por linha, ordenado, mesclado antes de gravar (a regra
  do dicionário do usuário do WordCraft). Nomes próprios do livro param de ser marcados.
A palavra **em digitação** não é marcada até terminar (espaço, pontuação, `Enter` ou o cursor sair).

**O léxico confere e não troca:** a sugestão só entra pelo clique. É a mesma fronteira que a
recusa do corretor ortográfico desenhou.

**Critério de aceite.** Numa folha com `p/ayer`, o menu sobre a palavra oferece `player` em
primeiro; aceitar troca a palavra num passo de desfazer e conta uma correção; acrescentar `Dvoretsky`
ao léxico do livro tira a marca dela nesta e na próxima folha do mesmo livro, e não noutro livro.

### S-658 · O modo foco e as marcas de formatação

**Decisão.** **Modo foco**: a mesa esconde fita, painel de navegação e folha impressa; fica o
editor, a faixa do bloco impresso (se ligada) e uma barra fina; `Esc` sai. **Marcas de formatação
(¶)**: liga a exibição de fim de parágrafo e espaços pelo `QTextOption` do documento — é vista, não
grava, e ajuda a achar o espaço duplo e a quebra de linha errada que o OCR deixa. Como `_desenhar`
cria um `QTextDocument` novo a cada redesenho, a opção é reaplicada em cada um (a mesma armadilha
do desfazer nativo, que o `_desenhar` já documenta). A tecla do Word, `Ctrl+Shift+8`, **não** é
prometida: com `Shift` o `8` chega como `*` nos teclados US e ABNT2, e a guarda compara a
combinação do evento; medir antes de declarar.

**Critério de aceite.** Com o modo foco ligado, fita, painel de navegação e visualizador estão
escondidos e `Esc` os traz de volta; as marcas de formatação continuam ligadas depois de um negrito
(que redesenha), e não entram no texto copiado.

### S-659 · Três ferramentas de correção do WordCraft

**Decisão.** As que custam pouco e pagam muito em OCR:
- **busca por palavra inteira e com curinga.** `text/busca.padrao_de` só tem `casar_figurina` e
  `diferenciar_caixa`; ganha `palavra_inteira` e `curinga` (`?`, `*`, `[a-z]`, `<`, `>`, a tradução
  do `cmd/find_pattern.rs` do WordCraft), com grupos `` a `\9` na substituição. O `re` do Python
  retrocede, e por isso a tradução **não gera quantificador aninhado** — é o cuidado que o WordCraft
  resolve com um motor linear;
- **mover parágrafo** (`Alt+Shift+↑`/`↓`): a ordem de leitura é erro conhecido do OCR desta aba.
  `rico.mover_paragrafo(doc, bloco, ±1)`, um passo de desfazer; o diagrama anda com a marca;
- **`Alt+X`**: troca o caractere antes do cursor pelo código `U+XXXX` e de volta — para `š`, `ě`, as
  figurinas e o que a paleta não tem.

**Critério de aceite.** Substituir `(\d)l` por `	` com curinga transforma `e4l` em `e41` e não toca
`ll`; mover o segundo parágrafo para cima troca a ordem no documento e na tela (guarda S-603) e um
`Ctrl+Z` desfaz; `Alt+X` depois de `0161` escreve `š`, e de novo devolve `0161`.

## Fase 96 — Negrito e itálico na folha sem camada

### S-660 · O diagnóstico: o estilo que a camada sabe chega à tela em todo motor?

**Problema.** O código diz que o negrito da camada já chega aos dois motores — "o peso não tem
segunda fonte, então o detalhe vale nos dois motores" (`text/leitor.py:1319-1323`) —, e que o
itálico por caractere só entra no motor `camada`, porque no glifo o pendor da imagem é quem
responde. Não há **número** de quanto estilo declarado pela camada a pessoa vê na tela, em cada
motor, depois de `rico.de_pagina` e do desenho. Pode ser que, para os 13 livros com peso, a
resposta ao pedido "negrito" já seja "funciona" — e se for, é a primeira coisa que o dono precisa
saber, antes de qualquer modelo.

**Decisão.** Uma medição, antes de qualquer modelo: nas folhas do protocolo da S-429 (4 por PDF),
nos 13 livros que declaram peso, ler com os três motores e contar, por caractere, negrito e itálico
da camada contra o que o `DocumentoRico` entrega. Relatório em
`docs/metrics/texto_estilo_por_motor.json`, com o código e o modelo declarados (S-218).

**O que a medição decide.** Se `auto` ou `glifo` perdem estilo que a camada declara **com
metadado de fonte** (nome com `Bold`, bit de `flags`), isso é o conserto mais barato do plano: o
metadado de fonte não é palpite de OCR, e pode valer em qualquer motor onde a camada existe. A
S-661 só abre para o que sobrar — as folhas sem camada. Esta medição vai na **primeira entrega**.

**Critério de aceite.** O relatório lista, por livro e por motor, os caracteres com negrito e com
itálico na camada e os que chegam ao `DocumentoRico` e ao desenho (o leitor da S-603), e nomeia os
livros onde a diferença passa de 1%.

**Medido em 2026-10-24** (4 folhas de cada um dos 51 PDFs; 18 livros com estilo declarado nas folhas
lidas, 58 folhas, 42.989 caracteres casados). `auto` e `glifo` dão o mesmo número, porque com o
classificador presente o `auto` **é** o glifo:

| estilo | declarado pela camada | chegou | perda | a mais (o motor marca, a camada não) |
|---|---|---|---|---|
| negrito | 2.489 | 2.256 | **9,4%** | 24 |
| itálico | 504 | 331 | **34,3%** | **1.159** |

**O negrito quase chega; o itálico não.** O itálico a mais é 2,3 vezes o declarado: a régua de linha
do pendor (S-211) decide a linha inteira, e a S-429 só desce ao caractere no motor `camada`. Em 5 dos
15 livros com itálico declarado ele some por inteiro (Gunderam, Koblenz, Yusupov 4, Mieses, Seirawan).
**A consequência para o plano:** antes da Fase 96 vem um conserto barato — o itálico de **metadado
de fonte** (nome com `Italic`/`Oblique`, bit de `flags`) valer por caractere também no glifo, onde a
camada existe, como o negrito já vale. A perda de 9,4% do negrito, que também não tem segunda fonte,
pede o mesmo olhar; a suspeita, **ainda não medida**, é o casamento por geometria entre a linha da
camada e a linha que o glifo segmenta.
A Fase 96 continua sendo só para as folhas **sem** camada.

**O conserto barato, feito e remedido em 2026-10-24** (`86a1315`, a mesma amostra). A premissa que
deixava a camada fora do glifo — "a camada do scan é palpite de outro OCR" — vale para o scan e não
para o livro nascido digital. `camada.camada_tipografica` separa os dois **por folha** (sem
`GlyphLessFont` e sem uma imagem cobrindo 70% dela, o corte de `cli/texto_grade.camada_de_ocr`), e
nessas folhas o itálico da camada responde por cima do pendor, na linha e no caractere:

| estilo | declarado | chegou antes | chegou agora | a mais antes | a mais agora |
|---|---|---|---|---|---|
| negrito | 2.489 | 2.256 | 2.256 | 24 | 24 |
| itálico | 504 | 331 | **421** | 1.159 | **578** |

O negrito idêntico é a reprodução: o conserto não toca o peso. A perda do itálico caiu de 34,3% para
**16,5%**; nos livros tipográficos ele chega inteiro ou quase (Seirawan, os dois *400 Quebra-cabeças*,
Dvoretsky 64 de 65). O que sobra está nos scans com camada de OCR de terceiro, que continuam sem
voz de propósito — é a população da Fase 96.

### S-661 · O conjunto rotulado

**Decisão.** Recortes de **palavra** renderizados de PDFs nascidos digitais, rotulados pela camada
(`normal`, `negrito`, `itálico`, `negrito-itálico`), separados **por livro** em treino/validação/teste
— o protocolo da medição de 2026-08-29, que já tem 20.156 palavras de 14 livros. Duas
degradações sintéticas para aproximar o scan, que é a população-alvo: binarização com limiar
sorteado, desfoque leve, ruído de pontos, reamostragem 300 → 150 dpi → 300.

**O acervo tem livros duplicados, e não há deduplicação de livro.** `text/dedupe.py` (S-202) junta
glifos quase iguais dentro de uma classe, e `text/custo.py` só reconhece o problema. Sem uma
identidade de livro (impressão do conteúdo das primeiras folhas, a mesma da S-610) aplicada
**antes** da divisão por livro, o mesmo livro cai no treino e no teste e a medição fora do livro
mente. A identidade entra como o primeiro passo desta fase.

**Critério de aceite.** O conjunto tem um manifesto com livro (pela identidade), folha, palavra,
rótulo e partição; nenhuma identidade aparece em duas partições; a contagem por classe está no
relatório.

### S-662 · O classificador de estilo da palavra

**Decisão.** Uma rede pequena (o mesmo porte do classificador de glifo; entrada em altura fixa,
largura variável até um teto) que dá a probabilidade das quatro classes para cada palavra. Treina
com `train_model.py`/`text/treino.py` no padrão do projeto, CPU-viável, pesos em `models/` fora do
git como os outros. **Não** substitui a camada: onde a camada declara peso, ela responde (S-660).

**Critério de aceite.** O treino é reproduzível (semente, manifesto e versão do código no
relatório), e a leitura de uma folha com o classificador ligado custa no máximo 20% a mais que sem
ele, medido no motor `glifo`.

### S-663 · O portão

**Decisão.** Medido no teste **fora do livro**, nas duas populações (render limpo e render
degradado). A régua é **precisão por classe**; os números de controle abaixo são de **acerto
global**, que é outra medida — eles dizem se o modelo aprendeu algo, não se passa:

| uso | régua | de onde vem |
|---|---|---|
| aplicar sem perguntar | precisão ≥ 0,9929 por classe | S-213 |
| sugerir | precisão ≥ 0,95 por classe, e cobertura ≥ 0,50 | R4 |
| recusar | abaixo das duas | — |

**Uma medição de controle obrigatória**, a que a geometria não fez e que custou o primeiro
resultado: o classificador tem de vencer "chutar pela altura da palavra" (que acerta 0,8889) e
"chutar normal" (0,9227) — senão aprendeu o tamanho, não o peso. Relatório em
`docs/metrics/texto_estilo_classificador.json`. **Se não passar na régua de sugerir, a fase termina
aqui**, a recusa da ROADMAP_EDITOR volta com o número novo, e o pincel manual (S-241) continua sendo
a resposta.

### S-664 · A sugestão, e não a aplicação

**Decisão.** A `LinhaLida` ganha `negrito_sugerido_em` e `italico_sugerido_em` (intervalos, como
`negrito_em` da S-429), preenchidos só pelo classificador e só onde não há camada. O
`DocumentoRico` os carrega como **sugestão**: o trecho é desenhado normal, com um sublinhado
pontilhado discreto na cor de sugestão do tema. Aceitar (`Ctrl+Shift+Y` na palavra, "Aceitar estilos
sugeridos (N)" na fita para a folha) transforma a sugestão em atributo, num passo de desfazer e
contando como correção. É mudança de formato (R5): a sugestão é um canal da
`Corrida` que não é atributo do autor e sobrevive a `fundir` e `editar`. O `.cvtxt` guarda a sugestão não aceita (a folha reaberta mostra o mesmo);
os exportadores **não** a exportam. A guarda S-603 lê a sugestão de volta.

**Critério de aceite.** Uma folha com três sugestões de negrito: a tela mostra três sublinhados
pontilhados e nenhum negrito; aceitar a folha deixa três trechos negrito e zero sugestões; o `.md`
exportado antes de aceitar não tem `**`.

### S-665 · O itálico por palavra

**Decisão.** Onde o classificador passar na régua de **aplicar** para itálico, ele substitui a
régua de linha do pendor (S-211) — que decide a linha inteira e, como a S-429 mediu na camada, erra
nos dois sentidos quando a linha mistura. O conserto `l`→`/` de `text/italico.py` passa a valer por
palavra itálica, e não por linha: a citação de três palavras no meio de uma linha em pé deixa de
ficar com `/` no lugar de `l`.

**Critério de aceite.** Na folha 311 do `Secrets of Chess Training` (a do diagnóstico da S-211), a
citação itálica sai com `l` e uma linha em pé com `1/2-1/2` continua com `/`.

### S-666 · O que o rodapé diz sobre o estilo

**Decisão.** O rodapé da folha diz de onde veio o estilo: "estilo: camada do PDF", "estilo:
sugerido pela imagem (7 sugestões)" ou "estilo: o livro não informa". É a frase honesta de
`negrito=None` ("não se sabe") que `text/negrito.py` já defende, levada até a tela.

**Critério de aceite.** As três frases aparecem, cada uma, para uma folha sintética com camada com
peso, com sugestões e sem camada; o teste lê o rótulo do widget.

### S-667 · Remedição

O classificador entra no caminho de leitura da página, e o caminho de medição de campo está sob a
S-218. Se `text/leitor.py` passar a chamá-lo, **os quatro relatórios de campo são remedidos** no
mesmo PR, sobre árvore limpa, com o relatório arquivado reproduzido antes.

### S-668 · O que fica para depois desta fase

Sublinhado e versalete pela imagem, e estilo por caractere dentro da palavra. Nenhum dos dois tem
rótulo confiável na camada em quantidade (o sublinhado nem tem bit de fonte), e um classificador sem
rótulo não tem portão.

---

# Onde a spec mora, e quando ela muda de casa

A especificação está **neste** arquivo, e não num `SPEC_MESA_DE_TEXTO.md`, por uma regra de
`tests/test_docs.py`: item com seção `## S-NN` em arquivo cujo nome começa com `ROADMAP` não precisa
entrar na tabela de faixas, e a tabela é copiada byte a byte em 21 documentos. Pôr a faixa S-601 a
S-668 nos 21 antes de um só item existir seria mexer em 21 arquivos por um plano.

**Quando o primeiro item for entregue**, as seções da fase dele mudam para
`docs/SPEC_MESA_DE_TEXTO.md`, a linha `| S-601 a S-668 | [SPEC_MESA_DE_TEXTO.md](SPEC_MESA_DE_TEXTO.md) |`
entra na tabela de todos os documentos que a trazem, e este arquivo passa a apontar para lá.

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
