# Roadmap da aparência — Fases 32 a 35

Avaliação das duas propostas de interface em `Proposta de interface/` e o plano para adotá-las
**sem aposentar a interface de hoje**. Especificação detalhada em
[SPEC_APARENCIA.md](SPEC_APARENCIA.md) (S-219 a S-234).

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
> | S-95 a S-142, S-218 | [SPEC_FASE14.md](SPEC_FASE14.md) |
> | S-144 a S-170 | [SPEC_UI.md](SPEC_UI.md) |
> | S-178 a S-217 | [SPEC_TEXTO.md](SPEC_TEXTO.md) |
> | S-219 a S-234 | [SPEC_APARENCIA.md](SPEC_APARENCIA.md) |

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
| **32** — o catálogo, o ícone e a pele | S-219 a S-222 | a fundação: um comando declarado uma vez, um ícone que segue o tema, e a pele como estado |
| **33** — a pele "Foco" (Imagem 1) | S-223 a S-226 | a fila única, o cromo escuro com documento claro, o deslizador de zoom |
| **34** — a pele "Fita" (Imagem 2) | S-227 a S-230 | a fita de grupos, o desfazer que ela promete, o conjunto de peças |
| **35** — o que as três ganham juntas | S-231 a S-234 | paleta de comandos, densidade, o inventário de alcance e o contrato de degradação |

## Fase 32 — o catálogo, o ícone e a pele

Vem primeiro porque **as duas outras fases desenham a partir dela**, e porque é a única que
justifica o custo total: sem catálogo, cada pele é uma cópia da lista de comandos, e três cópias
divergem no primeiro comando novo.

- **S-219** · O catálogo de comandos, declarado como dado
- **S-220** · O ícone que nasce do token, e não do disco
- **S-221** · A pele como estado da janela, e a clássica como padrão
- **S-222** · Trocar de pele sem fechar a janela, e sem perder o lugar

Ao fim da fase a janela é **a de hoje, sem diferença visível** — e `Ver ▸ Aparência` lista uma
opção. É de propósito: a fundação se prova quando ela não muda nada.

## Fase 33 — a pele "Foco"

- **S-223** · A fila única de ações, e o resto onde ele já estava
- **S-224** · Cromo escuro, documento claro, marcações remedidas
- **S-225** · O deslizador de zoom, sem tirar o teclado nem os botões de enquadrar
- **S-226** · A faixa de abas discreta, e o rodapé que não pode sumir

## Fase 34 — a pele "Fita"

- **S-227** · A fita de grupos nomeados, gerada do catálogo
- **S-228** · Ícone grande com rótulo, e o orçamento de altura que ele respeita
- **S-229** · Desfazer e refazer, que a fita promete e o programa não tem
- **S-230** · O conjunto de peças como escolha, e não como pasta cravada

## Fase 35 — o que as três peles ganham juntas

Os quatro itens que **só fazem sentido depois** de existir mais de uma pele, e que são o preço de
ter três.

- **S-231** · A paleta de comandos, que sai de graça do catálogo
- **S-232** · Densidade: compacta ou confortável
- **S-233** · Nenhuma pele esconde um comando: o inventário de alcance
- **S-234** · A pele não derruba a janela: o contrato de degradação nas três

---

# As cinco sugestões que não vieram das imagens

O pedido abriu espaço para elas, e estas cinco são as que o código de hoje torna baratas. Cada uma
está amarrada a um item, e nenhuma é enfeite.

| sugestão | item | por que ela é barata aqui | por que ela vale |
|---|---|---|---|
| **Desfazer/refazer da edição do tabuleiro** | S-229 | `board_edit` é puro; a pilha é de `str` | a S-76 é o registro do que custa não tê-lo: 1.405 diagramas |
| **Paleta de comandos** (`Ctrl+Shift+P`) | S-231 | o catálogo da S-219 **é** a lista da paleta | é o que torna seguro a pele "Foco" esconder 60 comandos |
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
