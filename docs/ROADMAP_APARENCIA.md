# Roadmap da aparência — Fases 32 a 35

Avaliação das duas propostas de interface em `Proposta de interface/` e o plano para adotá-las
**sem aposentar a interface de hoje**. Especificação detalhada em
[SPEC_APARENCIA.md](SPEC_APARENCIA.md) (S-324 a S-234).

Para a avaliação de interface que produziu a fundação que este plano usa,
[ROADMAP_UI.md](ROADMAP_UI.md) e [SPEC_UI.md](SPEC_UI.md); para o *como* de hoje,
[ARCHITECTURE.md](ARCHITECTURE.md). Nenhuma fase daqui toca modelo, detecção ou texto — elas
seguem em [ROADMAP_FASE14.md](ROADMAP_FASE14.md) e [ROADMAP_TEXTO.md](ROADMAP_TEXTO.md).

**Data da avaliação:** 2026-08-23 · **Ramo:** `fase-5-modelo-desempenho` · **Commit base:** `8167b7b`

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
> | S-296 a S-323 | [SPEC_REVISAO.md](SPEC_REVISAO.md) |

---

# O pedido, e o que ele decide

> "O programa deve ter a opção da interface atual e essas duas das imagens."

Essa frase é a arquitetura inteira desta fase, e ela exclui a solução óbvia. **Três telas não
podem ser três montagens de widget**, porque três montagens são três lugares onde um comando novo
precisa ser lembrado — e o primeiro que alguém esquecer produz um programa em que a mesma versão
faz coisas diferentes conforme a aparência escolhida. É o defeito que a S-161 já registrou em
outra forma: *"o que não era botão não existia"*.

A saída é a que este projeto já usa duas vezes. `ui/menu.py` declara a barra de menus **como
dado** e recusa a montagem quando um item declarado não tem comando; `ui/atalhos.py` declara as
dez teclas uma vez e o menu descobre o acelerador por ali. Esta fase estende a mesma disciplina
ao resto: **um catálogo de comandos, três desenhos dele.**

---

# As duas imagens, lidas

## Imagem 1 — a proposta "Foco"

Cromo escuro, uma fila só de ações, o documento ocupando tudo o mais.

| o que a imagem mostra | o que isso é hoje |
|---|---|
| barra de menus `Arquivo · Editar · Ver · Ferramentas · Ajuda` | **já existe**, idêntica: `ui/menu.py:63-134` |
| quatro pílulas com ícone: ler, próximo diagrama, aplicar FEN, exportar | 4 dos 21 controles das duas barras do PDF |
| separador vertical entre a 2ª e a 3ª pílula | um agrupamento que hoje não é declarado em lugar nenhum |
| divisão em dois painéis: tabuleiro à esquerda, página à direita | **já é assim** (`app_tkinter.py:297-309`), com a aba Resultado aberta |
| retângulo **tracejado** laranja sobre o diagrama da página | `ui/page_overlay.py`, estado `TRACEJADO` |
| deslizador de zoom no rodapé do painel esquerdo | hoje são `-`, `+`, rótulo e dois botões de enquadrar |
| tabuleiro em cinzas frios, duas casas com halo azul | `tokens.CASA_CLARA/CASA_ESCURA` e `CONTORNO_DE_SELECAO` |

## Imagem 2 — a proposta "Fita"

Claro, grupos nomeados, ícone grande com rótulo embaixo.

| grupo | comandos na imagem | onde eles estão hoje |
|---|---|---|
| Arquivo | Abrir PDF, Exportar PGN, Salvar | `barra_livro` + `Ctrl+S` |
| OCR | Ler diagrama, Ler todos, Selecionar área | `barra_livro` (3 dos 9) |
| Edição | Desfazer, Refazer, Limpar, Aplicar FEN | **três dos quatro não existem** |
| Visualização | Zoom, Ajustar à largura, Ajustar à página | `barra_vista` (3 dos 12) |

---

# Sete achados, e os cinco que mudam o plano

**1 · Os rótulos das imagens não são vocabulário — são ruído de renderização.** "Arfiro",
"Arviiro", "Prónimto diagrama", "Ediçio", "Visualicão"; e a Imagem 2 mistura português no
cabeçalho com inglês nos botões (`Open PDF`, `Scan all`, `Fit page`). São propostas visuais, não
propostas de texto. O vocabulário que vale continua sendo o de `ui/strings.py` e `ui/menu.py`, que
a S-166 já fixou. **Nenhum item desta fase troca o rótulo de comando nenhum.**

**2 · A Imagem 1 já está metade pronta.** Os cinco menus dela são os cinco de `menu.MENUS`, na
mesma ordem. O que ela propõe de novo não é a barra de menus: é **o que sobra fora dela** — quatro
ações, e nada mais.

**3 · As duas imagens escondem a maior parte do programa, e isso não pode ser adotado.** A
contagem é objetiva:

| o que a janela tem hoje | onde | quantos |
|---|---|---|
| controles da barra do livro | `ui/pdf_panel.py:299-338` | 9 |
| controles da barra da vista | `ui/pdf_panel.py:340-382` | 12 |
| linha do conjunto de campo | `app_tkinter.py:470-499` | 6 |
| abas do painel esquerdo | `app_tkinter.py:311-399` | 6 |
| itens de menu | `ui/menu.py:63-134` | 27 |
| rodapé com progresso **e cancelamento** | `ui/rodape.py` | 1 |

A Imagem 1 mostra 4 comandos; a Imagem 2 mostra 13. Adotá-las ao pé da letra apagaria a fila de
revisão, o Dataset, a Galeria, a Configuração, o treino, a anotação de conjunto de campo e o
**cancelamento** — que depois da S-163 mora no rodapé, e que as duas imagens não têm.

> **A regra que sai daqui, e que vale para as três peles:** pele é *apresentação* do mesmo
> conjunto de comandos, nunca um conjunto menor. Um comando pode mudar de lugar, ganhar ícone,
> virar item de menu — **não pode ficar inalcançável.** É o que a S-233 mede, por inventário.

**4 · A Imagem 2 promete Desfazer e Refazer, e eles não existem.** `grep -rn 'undo' src/` devolve
zero linhas de implementação. Não é descuido da imagem: é a função que falta. `ui/board_edit.py`
é puro (posição → posição) e o `apply_edits` já foi escrito com o comentário *"útil para desfazer
em bloco"* (`ui/board_edit.py:167`) — a pilha custa pouco, e o registro do que custa não tê-la é a
S-76: **1.405 diagramas sobrescritos por um clique.** Vira a S-229.

**5 · A Imagem 1 é escura, e `ui/theme.py:37-50` argumenta contra tema escuro por escrito.** O
argumento é bom e específico: o produto é comparar diagrama impresso em papel branco com o que o
modelo leu, e um tema escuro põe a página renderizada sobre preto — o olho passa a corrigir
contraste em vez de posição.

A imagem, porém, **não contradiz isso**: a página dela continua branca. O que escurece é o cromo.
É essa a leitura que entra, e ela vira a regra da S-224: **cromo segue a pele; superfície de
documento — página e tabuleiro — mantém contraste medido.** As marcações são remedidas contra o
novo fundo pelos testes que já existem, `test_ui_semantica_cor.py` e `test_ui_superficies.py`, que
passam a rodar uma vez por pele registrada.

**6 · Não há um único ícone no repositório.** `assets/` tem 12 PNGs de peça e um `.ico`. As duas
propostas são dirigidas a ícone — 4 na Imagem 1, 13 na Imagem 2. Um conjunto de PNG resolveria a
Imagem 2 e quebraria na Imagem 1: traço escuro sobre cromo escuro some, que é o defeito que a
S-146 mediu no tabuleiro e que `PieceImages.icon` já contorna com `background=`. Daí a S-220:
ícone declarado como **traço numa caixa 0..100**, desenhado pela Pillow no tamanho pedido e na
**cor que o token resolve** — um arquivo de dado, zero binário novo, e correto nas três peles por
construção.

**7 · A fita custa altura, e altura foi exatamente o defeito da S-151.** A S-151 mediu: cinco
barras empilhadas custavam ~200 px, 20% da altura da janela, sobre o painel cuja única razão de
existir é mostrar a página grande. A fita da Imagem 2 — cabeçalho de grupo + ícone grande + rótulo
— mede ~110 a 130 px numa linha só. É metade do que a S-151 removeu, e ela **não quebra como botão
quebra**: um grupo de fita partido ao meio não é um grupo. Por isso a S-228 tem um **orçamento em
pixel** como critério de aceite, e um modo compacto abaixo de uma largura medida.

**E um achado que não muda o plano, mas muda o que se copia da Imagem 2:** o tabuleiro dela é uma
**foto** de tabuleiro de madeira, com sombra e perspectiva. O tabuleiro da janela é onde se
*corrige* a leitura, casa a casa, contra um diagrama impresso — sombra e perspectiva atrapalham
justamente isso. O que entra da imagem é a *escolha* de conjunto de peças (S-230), não a foto.

---

# As quatro fases

| fase | itens | o que ela entrega |
|---|---|---|
| **32** — o catálogo, o ícone e a pele | S-324 a S-222 | a fundação: um comando declarado uma vez, um ícone que segue o tema, e a pele como estado |
| **33** — a pele "Foco" (Imagem 1) | S-223 a S-226 | a fila única, o cromo escuro com documento claro, o deslizador de zoom |
| **34** — a pele "Fita" (Imagem 2) | S-227 a S-230 | a fita de grupos, o desfazer que ela promete, o conjunto de peças |
| **35** — o que as três ganham juntas | S-231 a S-234 | paleta de comandos, densidade, o inventário de alcance e o contrato de degradação |

## Fase 32 — o catálogo, o ícone e a pele

Vem primeiro porque **as duas outras fases desenham a partir dela**, e porque é a única que
justifica o custo total: sem catálogo, cada pele é uma cópia da lista de comandos, e três cópias
divergem no primeiro comando novo.

- **S-324** · O catálogo de comandos, declarado como dado — ✅ **implementada em 2026-08-24**
- **S-220** · O ícone que nasce do token, e não do disco — ✅ **implementada em 2026-08-24**
- **S-221** · A pele como estado da janela, e a clássica como padrão — ✅ **implementada em 2026-08-24**
- **S-222** · Trocar de pele sem fechar a janela, e sem perder o lugar — ✅ **implementada em 2026-08-24**

Ao fim da fase a janela é **a de hoje, sem diferença visível** — e `Ver ▸ Aparência` lista uma
opção. É de propósito: a fundação se prova quando ela não muda nada. **Cumprido em 2026-08-24.**

> **Onde a fase está.** A S-324 entregou `ui/comandos.py` com os 35 comandos da janela, e os três
> lugares que os declaravam passaram a lê-los de lá: `ui/menu.py`, as duas barras de
> `ui/pdf_panel.py` e a linha de conjunto de campo. Nenhum rótulo mudou, e o teste compara os 29
> itens de menu com o registro para garantir isso. Ela também mediu o que o item previa em
> palavras: **11 dos 35 comandos tinham dois textos diferentes**, um no menu e outro no botão.
>
> Dois achados da implementação são decisões que caem na S-223, e estão escritos lá: dois dos
> quatro comandos em `destaque` não têm atalho de teclado, e a ênfase do grupo OCR está no botão
> que o critério de `ui/estilos.py` não escolheria.
>
> A S-220 entregou `ui/icones.py` com os **catorze** traços — a união das duas imagens, restrita
> ao que existe como comando. Os três que faltam da Imagem 2 são os que não existem: Desfazer e
> Refazer, que a S-229 cria. A cor sai do chamador, e a implementação achou o caminho pelo qual
> ela vazaria mesmo assim: reduzir uma imagem colorida desloca o hexadecimal pedido em um degrau
> por canal, que num ícone claro sobre cromo escuro vira halo. O traço passou a ser máscara, e a
> cor entra chapada — medido, sem desvio.
>
> A S-221 entregou `ui/pele.py`, o campo `skin` no estado (`STATE_VERSION` 2 → 3), a variável
> `CVOFF_SKIN` e o submenu `Ver ▸ Aparência` — **com uma opção**, a clássica, marcada. É de
> propósito: registrar "Foco" e "Fita" antes de elas existirem seria oferecer no menu uma escolha
> que não faz nada. A decisão que a implementação virou foi manter `skin` vazio em vez de gravar
> `"classica"`: o nome da pele padrão é de `ui/pele.py`, e cravá-lo em `ui/state.py` reabriria no
> arquivo ao lado a fenda que a S-324 fechou.
>
> A S-222 fechou a fase. A troca remonta o cromo -- as duas barras, a linha de campo e o menu --
> e não toca o conteúdo, e a descoberta foi que **os seis itens que a spec mandava preservar não
> precisam de máquina nenhuma**: eles continuam de pé porque a remontagem não os alcança. Viraram
> asserções, e não um `Contexto` que os fotografasse. A spec também estava errada num ponto que,
> seguido à letra, produziria o defeito que ela proíbe: refazer os `bind_all` a cada troca é o
> que deixaria N ligações da mesma tecla depois de N trocas. A resposta é não religar.
>
> **A Fase 32 está completa, e a janela é a de hoje** -- é o que ela prometia. O catálogo, os
> ícones, o registro de peles e a remontagem existem, são testados e ainda não mudam um pixel.
> Quem os liga é a Fase 33: a S-223 registra a segunda pele, e é aí que a fundação vira tela.

## Fase 33 — a pele "Foco" — ✅ **completa em 2026-08-24**

- **S-223** · A fila única de ações, e o resto onde ele já estava — ✅ **implementada em 2026-08-24**
- **S-224** · Cromo escuro, documento claro, marcações remedidas — ✅ **implementada em 2026-08-24**
- **S-225** · O deslizador de zoom, sem tirar o teclado nem os botões de enquadrar — ✅ **implementada em 2026-08-24**
- **S-226** · A faixa de abas discreta, e o rodapé que não pode sumir — ✅ **implementada em 2026-08-24**

> **Onde a fase está.** A S-223 registrou a segunda pele e desenhou a fila: quatro pílulas com
> ícone, em uma linha a 1100 px, geradas do catálogo. É o primeiro item destas quatro fases que
> muda a tela -- e só para quem abrir `Ver ▸ Aparência` e escolher "Foco".
>
> A fila não é a da imagem, e a diferença foi medida. A regra "destaque exige atalho" reprovava
> dois dos quatro comandos que a Imagem 1 desenha, e os dois lados cederam: `aplicar_fen` ganhou
> `Ctrl+Enter` -- o décimo primeiro atalho, e ele fechava o ciclo corrigir → salvar sem tecla --,
> e `exportar_pgn` deu lugar a `salvar`, porque se exporta uma vez por livro e se salva uma vez
> por diagrama. Uma fila dimensionada por importância em vez de frequência é a barra de 21 botões
> outra vez.
>
> Os três comandos que só existiam como botão -- cancelar exportação e os dois de zoom -- ganharam
> item de menu, e agora há um teste que cobra a regra 2 diretamente: todo comando está no menu ou
> na linha de conjunto de campo, sem terceiro destino.
>
> A S-224 escureceu o cromo, e o preço foi medido: **cinco dos sete pares de texto reprovavam** o
> piso AA sobre o cinza escuro, porque tinham sido escolhidos contra um fundo claro. Os cinco
> ganharam valor de cromo escuro com a matiz preservada — o desvio máximo é de 0,2°. E um deles
> obrigou a separar dois papéis que carregavam significados diferentes com um nome só: `PROBLEMA`
> e `DIVERGENTE` são contorno de casa **e** letra, e sobre cromo escuro os dois usos pedem valores
> opostos. É a S-158 de novo, achada por um caminho novo.
>
> Dois outros achados: oito rótulos liam a paleta clara direto, contornando `cor()` — todos
> ilegíveis na pele escura, todos corrigidos —, e `tb.Style` leva do tema claro ao escuro mas
> **não** de volta, o que deixaria a janela escura para sempre depois da primeira troca.
>
> A S-225 trocou os cinco controles de zoom por um deslizador de escala **logarítmica** — e a
> escolha tem número: na linear o meio do curso seria 112,5%, e na logarítmica é 70,7%, que é o
> zoom em que a janela abre. Ela também faz o deslizador concordar com a roda por construção,
> porque `zoomed` já era multiplicativo. Ele substitui **três** controles e não cinco: enquadrar
> não é um valor de zoom, e continua existindo.
>
> A S-226 fechou a fase, e ela é o item em que a regra 2 mais precisava valer: a Imagem 1 não tem
> faixa de abas nem rodapé, e seguir a imagem apagaria sete painéis e o **cancelamento** de uma
> varredura de dez horas. O que entra da imagem é o peso da faixa, e não o conteúdo. De passagem,
> corrigiu um número: são **sete** abas e não seis — a `Texto` da S-211 —, e os sete rótulos, que
> só existiam como literal dentro do `app_tkinter`, viraram declaração em `ui/abas.py`. O teste que
> conferia a ordem procurava esses literais, e a mudança o teria deixado cego passando em verde.
>
> **A Fase 33 está completa.** A pele "Foco" existe: fila de quatro pílulas com ícone, cromo
> escuro com documento claro, deslizador de zoom logarítmico e faixa de abas discreta -- e a
> clássica continua sendo, pixel a pixel, a janela de sempre.

## Fase 34 — a pele "Fita" — ✅ **completa em 2026-08-25**

- **S-227** · A fita de grupos nomeados, gerada do catálogo — ✅ **implementada em 2026-08-24**
- **S-228** · Ícone grande com rótulo, e o orçamento de altura que ele respeita — ✅ **implementada em 2026-08-25**
- **S-229** · Desfazer e refazer, que a fita promete e o programa não tem — ✅ **implementada em 2026-08-25**
- **S-230** · O conjunto de peças como escolha, e não como pasta cravada — ✅ **implementada em 2026-08-25**

> **Onde a fase está.** A S-227 registrou a terceira pele e desenhou a fita: quatro grupos com
> cabeçalho, catorze botões de ícone com rótulo, uma linha a partir de 1.400 px. Ela mostra quem
> tem ícone -- um botão de fita é ícone com rótulo, e comando sem ícone não tem como ser um --, e
> os grupos `Acervo` e `Ajuda` ficam vazios, sem cabeçalho. Os vinte e dois comandos de fora
> continuam no menu, com teste cobrando.
>
> **Custou três linhas no `app_tkinter.py`**, contra dezesseis da primeira pele. É a medida do que
> a fundação comprou.
>
> **E o achado da fase inteira saiu daqui:** fotografar a fita mostrou o grupo `Arquivo` em
> branco. O primeiro item de **toda** `BarraFluida` estava coberto pela moldura de linha, desde a
> S-151 -- na janela clássica isso são "Abrir PDF" e "Página anterior", invisíveis. `pack(in_=)`
> muda quem arruma e não quem é o pai, e irmão criado depois desenha por cima. O conserto é uma
> linha, e a pele clássica ganhou dois botões que deviam estar lá desde sempre.

> **A Fase 34 fechou, e as três últimas foram de outras sessões** -- estas notas são de quem
> escreveu o plano, lendo o que elas deixaram no disco e medindo antes de escrever.
>
> A **S-228** deu à fita um orçamento de altura declarado e verificado: 120 px no modo pleno,
> 64 no compacto. Medidos: **99 e 44**. E ela reprovou uma linha da própria spec: o modo compacto
> que a Imagem 2 sugeria -- rótulo em **uma** linha ao lado do ícone -- é 940 px **mais largo** que
> o pleno, e pediria três linhas de fita em 1366, que é a tela para a qual o modo foi inventado. O
> compacto entregue herda a quebra em duas linhas, e o que o faz compacto são as outras três
> decisões: ícone menor, rótulo ao lado e cabeçalho na dica. A conta é função pura sobre o `linespace` das fontes --
> nada de `winfo_height` no critério --, e as três constantes do `ttk.Button` que ela usa foram
> medidas nas seis combinações de ícone e linha, o que é o que permite prometer 2 px de tolerância
> contra o widget montado. Ela também acrescentou o que a spec não previa: uma **histerese** de 24
> px, sem a qual a troca de modo é reversível no mesmo pixel e a fita pisca.
>
> A **S-229** trouxe o desfazer que a Imagem 2 promete e que o programa não tinha -- uma pilha de
> **posições** e não de gestos, com o argumento de que uma pilha de gestos precisa saber inverter
> cada operação e o sintoma de esquecer uma é um desfazer que devolve posição que nunca existiu.
> `Ctrl+Z` e `Ctrl+Y` entraram na tabela de atalhos e chegaram ao menu, à legenda, ao catálogo e à
> fita **sem ninguém escrevê-los lá** -- que é a propriedade que a S-161 e a S-324 existem para dar.
>
> A **S-230** fez do conjunto de peças um eixo próprio, e derivou o conjunto de traço grosso em vez
> de desenhar doze arquivos novos. As duas decisões que podiam dar errado saíram certas: engrossar
> **depois** de reduzir, que é onde o problema está, e dilatar a **máscara de traço** e não o alfa,
> que é o que preserva o miolo claro das peças brancas.
>
> **As três peles existem.** O pedido que abriu esta fase -- *"o programa deve ter a opção da
> interface atual e essas duas das imagens"* -- está atendido, e a clássica continua sendo, pixel a
> pixel, a janela de sempre. **E a Fase 35 fechou em 2026-08-25**: a paleta de comandos, a
> densidade, o inventário que prova que nenhuma pele esconde comando, e o contrato de
> degradação medido nas três.

## Fase 35 — o que as três peles ganham juntas — ✅ **completa em 2026-08-25**

Os quatro itens que **só fazem sentido depois** de existir mais de uma pele, e que são o preço de
ter três.

- **S-231** · A paleta de comandos, que sai de graça do catálogo — ✅ **implementada em 2026-08-25**
- **S-232** · Densidade: compacta ou confortável — ✅ **implementada em 2026-08-25**
- **S-233** · Nenhuma pele esconde um comando: o inventário de alcance — ✅ **implementada em 2026-08-25**
- **S-234** · A pele não derruba a janela: o contrato de degradação nas três — ✅ **implementada em 2026-08-25**

---

# As cinco sugestões que não vieram das imagens

O pedido abriu espaço para elas, e estas cinco são as que o código de hoje torna baratas. Cada uma
está amarrada a um item, e nenhuma é enfeite.

| sugestão | item | por que ela é barata aqui | por que ela vale |
|---|---|---|---|
| **Desfazer/refazer da edição do tabuleiro** | S-229 | `board_edit` é puro; a pilha é de `str` | a S-76 é o registro do que custa não tê-lo: 1.405 diagramas |
| **Paleta de comandos** (`Ctrl+Shift+P`) | S-231 | o catálogo da S-324 **é** a lista da paleta | é o que torna seguro a pele "Foco" esconder 60 comandos |
| **Densidade compacta/confortável** | S-232 | deriva de `ui/tipografia.py`, que já escala pela fonte do sistema | a S-151 mediu o defeito em 1100×760; um notebook 1366×768 é o caso comum |
| **Deslizador de zoom** | S-225 | `viewport.clamp_zoom` e `anchor_after_zoom` já existem | `-`/`+` de 0,1 em 0,1 são 8 cliques para ir de 70% a 150% |
| **Troca de pele em execução** | S-222 | `theme.registrar_estilos` já foi escrita prevendo isto (docstring) | escolher aparência reiniciando o programa é escolher no escuro |

**O que foi considerado e recusado**, para que a ausência seja decisão:

- **Porte para Qt.** Os dois gatilhos do `ARCHITECTURE.md:163-168` continuam valendo e nenhum
  disparou (`labels.csv` em 3.936 de 10.000). Fazer três peles em Tk é ~3 semanas; portar são 3 a
  4 e não entrega pele nenhuma.
- **Ícones em PNG.** Ver o achado 6: resolvem uma pele e quebram a outra.
- **Um tema de cor por pele.** Pele decide *arranjo e densidade*; tema decide *cor*. São eixos
  separados, e `CVOFF_TTK_THEME` já dá 30 temas. Amarrar os dois faria "quero a fita clara com o
  tabuleiro escuro" ser impossível sem motivo.
- **Redesenhar as seis abas por dentro.** Fora de escopo. As peles mudam o cromo em volta delas.

---

# Custo, risco e ordem

| fase | esforço | risco | o que trava se der errado |
|---|---|---|---|
| 32 | 4 a 5 dias | **baixo** — nada muda na tela | nada: a pele clássica é o padrão |
| 33 | 3 a 4 dias | médio — o cromo escuro mexe em contraste | a pele "Foco" não é registrada; as outras seguem |
| 34 | 4 a 5 dias | médio — a fita tem orçamento de altura a respeitar | a pele "Fita" não é registrada |
| 35 | 3 dias | baixo | a paleta e a densidade ficam para depois |

**Total: ~2,5 a 3 semanas.** As fases 33 e 34 são independentes entre si — só dependem da 32 — e
podem trocar de ordem ou sair em paralelo. A fase 35 depende das duas.

**O maior risco não é técnico, é de disciplina:** três peles convidam a "resolver rápido só nesta
aqui". A S-233 existe para que isso falhe na suíte, e não seis meses depois, na máquina de quem
escolheu a pele errada.

**A regra de degradação continua a mesma de `ui/theme.py:12-15`, agora com um dono a mais:** nem
tema ausente, nem pele desconhecida, nem ícone que não desenhou podem ser motivo de a janela não
abrir. Aparência não derruba ferramenta.
