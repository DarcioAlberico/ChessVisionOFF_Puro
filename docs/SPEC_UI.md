# Especificação da interface — Fases 20 a 24 (S-144 a S-170)

Base: [ROADMAP_UI.md](ROADMAP_UI.md), que traz a avaliação de 2026-08-17 e o sequenciamento.
As fases de modelo e detecção não são tocadas por esta spec — elas seguem em
[SPEC_FASE14.md](SPEC_FASE14.md).

> **Onde mora a spec de cada item (S-NN).**
>
> | itens | arquivo |
> |---|---|
> | S-01 a S-36 | [SPEC.md](SPEC.md) |
> | S-37 a S-77 | [SPEC_FASE7.md](SPEC_FASE7.md) |
> | S-78 a S-82, S-143 | [ANALISE_DETECCAO.md](ANALISE_DETECCAO.md) |
> | S-83 a S-94 | [PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md) |
> | S-95 a S-142, S-218, S-220 | [SPEC_FASE14.md](SPEC_FASE14.md) |
> | S-144 a S-170 | [SPEC_UI.md](SPEC_UI.md) |

Cada item tem **Problema** (com arquivo:linha do estado atual), **Solução**, **Critério de
aceite** e **Testes**. A convenção é a de sempre: nomes de módulo são sugestão, o que importa é a
fronteira de responsabilidade. Todos os números citados foram medidos nesta máquina em
2026-08-17 no commit `3799f35`.

**Três regras valem para toda esta spec.**

1. **Nenhum item pode cravar cor, fonte ou espaçamento fora do módulo de tokens da S-145.** O
   defeito que se está corrigindo é justamente a cor cravada; corrigi-lo com mais uma cor cravada
   troca de dono e não de problema.
2. **O contrato de degradação de `ui/theme.py:12-15` é intocável.** Sem `ttkbootstrap`
   instalado, a janela abre em `ttk` puro. Todo item aqui é verificado nas duas condições.
3. **Interface deste projeto é testável sem abrir janela.** O que decide (qual estilo, qual
   texto, qual largura, qual cor) mora em função pura; o que monta widget não decide nada. É a
   regra da Fase 6 aplicada à aparência — e é ela que faz cada critério de aceite abaixo caber
   num `assertEqual`.

---

# Fase 20 — A fundação visual

> O sistema de design está instalado, carregado e não é usado. Esta fase é a que o liga, e ela
> vem primeiro porque todas as outras escrevem cor, peso ou fonte.

## S-144 · Os botões dizem o que fazem: estilo semântico no lugar de 70 botões iguais ✅ implementada (2026-08-17)

**Problema.** `ttkbootstrap` 2.2.0 está instalado e `ui/theme.py:77` aplica `bootstrap-light`
com sucesso, mas `grep -rn bootstyle src/ app_tkinter.py` devolve **zero linhas**. Lido do objeto
`Style` em execução:

```
TButton          → background #f0f0f0  foreground #000000  relief raised
primary.TButton  → background #0a58ca  foreground #ffffff  (já existe, no mesmo Style)
```

O resultado é que "Salvar posição reconhecida" (`ui/result_panel.py:327`), "Abrir no editor" e
**"Remover"** (`ui/dataset_panel.py:179,182`) — que apaga linha do `labels.csv`, isto é, trabalho
humano — são o mesmo botão cinza. Numa fila de cinco botões de igual peso, o olho não encontra a
ação principal e a destrutiva não pede cuidado nenhum.

**A restrição, medida.** Na 2.2.0 os widgets de `tkinter.ttk` **não** aceitam mais `bootstyle`:

```
ttk.Button(parent, bootstyle="primary")    → TclError: unknown option "-bootstyle"
ttk.Button(parent, style="primary.TButton") → funciona
```

E sem `ttkbootstrap`, num `Tk` com tema `vista`, `style="primary.TButton"` **não levanta**: o Tk
desenha o botão padrão. É o caminho que preserva o contrato de degradação sem trocar a classe de
nenhum widget.

**Solução.** Um módulo `ui/estilos.py` com uma função pura que traduz **papel** em nome de estilo
`ttk`, e três papéis apenas — mais que isso deixa de ser hierarquia:

| papel | nome de estilo | quem recebe |
|---|---|---|
| `PRIMARIO` | `primary.TButton` | a ação que o atalho também faz: "Salvar posição reconhecida", "Anotar página", "Corrigir agora", "OCR melhor diagrama", "Exportar PDF → PGN" — **uma por barra, nunca duas** |
| `DESTRUTIVO` | `danger.TButton` | "Remover", "Quarentena", "Limpar os headers", "Treinar do zero" quando marcado |
| `NEUTRO` | `secondary.TButton` (ou `""`) | todo o resto |

A função recebe o papel e devolve a string; quem monta widget só passa `style=`. Nenhum `if
ttkbootstrap` no código de painel.

**Critério de aceite.**
- Uma ação primária por barra de ações, e ela é a mesma que o atalho de teclado dispara.
- "Remover" e "Quarentena" em `danger`; nenhum outro botão da janela em `danger`.
- A janela abre sem `ttkbootstrap` instalado e nenhum widget levanta `TclError`.

**Testes.** `tests/test_ui_estilos.py`: a tabela papel→estilo é total (todo papel tem nome) e
injetiva; nenhum nome de estilo aparece cravado fora do módulo (varredura de `src/` e
`app_tkinter.py` por `style="` e `.TButton`); e um teste de fumaça que constrói um `ttk.Button`
com cada estilo num `Tk` de tema `vista` e afirma que não levanta.

---

## S-145 · Um módulo de tokens: as 24 cores cravadas viram uma paleta ✅ implementada (2026-08-17)

**Problema.** 24 cores hexadecimais cravadas em 8 arquivos, sem lugar onde a paleta exista
inteira. As consequências não são hipotéticas:

- **três verdes com três significados de "bom"**: `#00c07a` "já salvo" (`ui/pdf_panel.py:92`),
  `#2e7d32` "veio da base" (`ui/gallery_panel.py:285`) e o `success` do tema, `#146c43`, que
  ninguém usa;
- **dois cinzas auxiliares** para o mesmo papel de texto secundário: `#555555`
  (`ui/result_panel.py:279`, `app_tkinter.py:366`, `ui/study_panel.py:165`) e `#666666`
  (`ui/games_dialog.py:81`);
- nenhuma delas passa pelo `Style`, então nenhuma responde a troca de tema.

**Solução.** `ui/tokens.py`, sem `tkinter`, com duas camadas:

1. **papéis semânticos** — `TEXTO_SECUNDARIO`, `PRONTO`, `A_FAZER`, `DISPENSADO`, `ATENCAO`,
   `PROBLEMA`, `SUPERFICIE_PAGINA`, `SUPERFICIE_TABULEIRO`, `MOLDURA`, `COORDENADA`. O painel
   pede o papel, nunca o hex;
2. **resolução** — a função que, dado o `Style` em uso (ou `None` quando não há
   `ttkbootstrap`), devolve o hex do papel, preferindo o token do tema quando existe
   (`success` → `PRONTO`) e caindo num valor de reserva quando não.

Toda cor citada nas S-146 a S-160 é definida aqui e em nenhum outro lugar.

**Critério de aceite.**
- `grep -rnE "#[0-9a-fA-F]{6}"` em `src/chess_diagram_ocr/ui/` e `app_tkinter.py` só casa em
  `ui/tokens.py`.
- Um papel, um hex: dois papéis não resolvem para a mesma cor, e um papel não tem dois hexes.
- Trocar `CVOFF_TTK_THEME` muda as cores resolvidas sem tocar nenhum painel.

**Testes.** `tests/test_ui_tokens.py`: a varredura de hex cravado acima (é o teste que impede a
regressão); a resolução com `Style=None` devolve a paleta de reserva completa; e a razão de
contraste de cada par declarado "texto sobre superfície" é calculada e afirmada — o que dá o
mesmo instrumento à S-146.

---

## S-146 · Contraste medido: a cor que reprova, e as coordenadas que estão na tela e invisíveis ✅ implementada (2026-08-17)

**Problema.** Dois pares reprovam a razão WCGA AA de 4,5:1 para texto, calculados sobre as cores
exatas do código:

| par | razão | onde |
|---|---|---|
| `#00c07a` sobre `#ffffff` | **2,38:1** | `ui/pdf_panel.py:798-802` usa o verde das caixas como **foreground de texto**: "✓ página concluída · N diagrama(s) salvo(s)" |
| `#d8d8d8` sobre `#f2f2f2` | **1,27:1** | `ui/board_render.py:49` desenha as coordenadas em cinza claro, e `ui/result_panel.py:269` dá ao tabuleiro do Resultado o fundo `#f2f2f2` |

O segundo é o pior dos dois: as letras a–h e os números 8–1 **estão desenhados** no canvas do
Resultado e não podem ser lidos. Num programa cujo trabalho é dizer "o bispo está em c4", a
régua que nomeia c4 é invisível.

**Solução.** Separar cor-de-marcação de cor-de-texto na S-145: o verde `PRONTO` continua servindo
de borda de retângulo (onde a razão que importa é contra a página, não contra o branco) e o
texto passa a usar um par `PRONTO_TEXTO` que passa AA. A coordenada deixa de ser uma constante e
passa a ser resolvida **contra a superfície em que vai ser desenhada** — o mesmo mecanismo que
`ui/gallery_panel.py:225-232` já usa para o `tk.Text` da legenda, e que aqui faltou.

**Critério de aceite.**
- Todo par (texto, fundo) declarado nos tokens tem razão ≥ 4,5:1; toda borda contra a superfície
  em que é desenhada tem ≥ 3:1.
- As coordenadas são legíveis nos dois tabuleiros da janela, e o teste diz isso com número.

**Testes.** `tests/test_ui_contraste.py`: a função de razão WCAG (com os casos conhecidos
`#000/#fff` = 21:1 e `#777/#fff` = 4,48:1 como âncoras), e a varredura de todos os pares
declarados. O teste falha nomeando o par e a razão obtida.

---

## S-147 · Um tabuleiro, uma identidade: as superfícies de canvas seguem o tema ✅ implementada (2026-08-17)

**Problema.** Quatro superfícies desenhadas fora do `Style`, e uma delas produz um efeito que
nenhum designer escolheria:

| superfície | cor | onde |
|---|---|---|
| canvas do PDF | `#1c1c1c` | `ui/pdf_panel.py:338` |
| tabuleiro do **Resultado** | `#f2f2f2` | `ui/result_panel.py:269` |
| tabuleiro da **Análise** | `#262421` (padrão) | `ui/board_widget.py:107` |
| tooltip | `#ffffe0` | `ui/tooltip.py:69`, `ui/board_widget.py:561` |

O **mesmo** `InteractiveBoard` aparece claro numa aba e escuro na aba vizinha, sem que nada além
de um argumento diferente justifique. E como metade dos 30 temas do `ttkbootstrap` é escura,
qualquer usuário que exerça o `CVOFF_TTK_THEME` documentado em `ui/theme.py:33` fica com quatro
retângulos imunes à sua escolha.

**Solução.** As quatro superfícies passam a vir dos papéis da S-145. O tabuleiro perde o
parâmetro `background` do chamador: quem decide é o token, não o painel — a escolha "claro no
Resultado" só existia porque o Resultado nasceu com um canvas somente-leitura antes da S-20. A
moldura escura (`BOARD_FRAME`) vale para os dois, porque é ela que dá contraste às coordenadas
(9,47:1) e resolve a S-146 pelo mesmo movimento.

**Critério de aceite.**
- Os dois tabuleiros da janela são visualmente idênticos em fundo, moldura e coordenadas.
- Nenhum painel passa cor de fundo para o `InteractiveBoard`.
- Sob um tema escuro (`CVOFF_TTK_THEME=darkly` ou equivalente 2.0) as quatro superfícies
  acompanham, e o teste afirma isso comparando luminância.

**Testes.** `tests/test_ui_superficies.py`: a resolução de cada superfície sob um tema claro e um
escuro, afirmando que a luminância da superfície acompanha a do tema; e que
`InteractiveBoard.__init__` não tem mais parâmetro de cor.

---

## S-148 · DPI por monitor, e o ícone do produto ✅ implementada (2026-08-17)

**Problema.** Duas ausências que decidem a primeira impressão antes de qualquer widget.

*DPI*: nada no projeto chama `SetProcessDpiAwareness`. Em monitor a 125% ou 150% — o padrão de
fábrica de quase todo notebook novo — o Windows amplia o bitmap da janela inteira, e o texto,
as coordenadas do tabuleiro e a página do PDF ficam borrados. O produto é conferir glifo
impresso: borrão é dano funcional, não estético.

*Ícone*: `iconphoto` nunca é chamado (`app_tkinter.py:124-133`) e `packaging/cvoff.spec:132` traz
`icon=None`. Barra de tarefas, Alt-Tab, atalho e `.exe` mostram a pena genérica do Tk. O projeto
**tem** arte pronta: `assets/piece_images/`.

**Solução.** Uma função `ui/plataforma.py::preparar_janela(root)` chamada antes de qualquer
widget, que (a) no Windows pede consciência de DPI por monitor via `ctypes`, tolerando falha em
silêncio com log de uma linha — é aparência, e aparência não derruba ferramenta; (b) ajusta o
`tk scaling` a partir do DPI efetivo; (c) aplica um `.ico`/`iconphoto` derivado de uma peça de
`assets/`. O `.spec` do bundle passa a apontar para o mesmo `.ico`.

**Critério de aceite.** Em monitor a 150% o texto é nítido e nenhum widget fica cortado por
arredondamento de escala; a janela e o `.exe` mostram o ícone do produto; num ambiente sem
`ctypes.windll` (ou fora do Windows) a chamada não levanta e a janela abre.

**Testes.** `tests/test_ui_plataforma.py`: a função é chamável com um duplo de `root` que levanta
em toda chamada e não propaga nada; o cálculo de escala a partir do DPI é puro e testado em 96,
120 e 144; e um teste que afirma que `cvoff.spec` referencia o arquivo de ícone que existe no
disco.

---

## S-149 · Escala tipográfica, e a FEN em monoespaçada ✅ implementada (2026-08-17)

**Problema.** Segoe UI 9 em toda a janela: título de grupo, rótulo de campo, dado e barra de
status têm o mesmo tamanho e o mesmo peso, e por isso a tela não tem hierarquia nenhuma para o
olho seguir.

E há um caso pior que uniformidade. A **FEN** é o dado central deste produto, e ela aparece em
fonte proporcional em `ui/result_panel.py:296`, `ui/study_panel.py:121` e na coluna `fen` do
`Treeview` (`ui/dataset_panel.py:164`). Em proporcional, `1`, `l` e `I` têm larguras diferentes,
`8/8/8` não alinha com `8/8/8` da linha de baixo, e comparar duas leituras da mesma posição — que
é a tarefa da aba Revisão e da segunda opinião da S-66 — passa a exigir contar caracteres com o
dedo na tela.

**Solução.** Nos tokens da S-145, uma escala de quatro degraus e duas famílias:

| papel | uso |
|---|---|
| `TITULO` | título de grupo (`LabelFrame`), 1 degrau acima e em negrito |
| `CORPO` | rótulo e botão — o Segoe UI 9 de hoje |
| `AUXILIAR` | texto secundário, hoje `#555555`/`#666666` sem tamanho próprio |
| `DADO` | **monoespaçada**: FEN, coluna de FEN, linha de PGN, caminho de arquivo |

Os tamanhos derivam da `TkDefaultFont` do sistema, não de números fixos: quem aumenta a fonte do
Windows aumenta a do programa.

**Critério de aceite.** Todo campo e toda coluna que mostra FEN, PGN ou caminho usa `DADO`; os
títulos de grupo se distinguem do corpo sem depender de borda; mudar a `TkDefaultFont` do sistema
move a escala inteira.

**Testes.** `tests/test_ui_tipografia.py`: a escala é monotônica e derivada do tamanho base
(testada em 9, 10 e 12); varredura que afirma que nenhum widget de FEN/PGN/caminho fica sem a
família monoespaçada.

---

# Fase 21 — A janela que não apaga controles

> É a única fase que corrige perda de função. Hoje, num notebook de 1366×768, o botão de salvar
> não está na tela.

## S-150 · O piso da janela, e a aba que rola ✅ implementada (2026-08-17) (as duas metades)

**Problema.** `app_tkinter.py:127` pede 1700×980 e **nada** define um piso: `root.minsize()`
nunca é chamado. Os `minsize` de `app_tkinter.py:245-246` são do `PanedWindow` (420 + 520 = 940)
e não impedem a janela de encolher — eles só disputam o divisor.

Fotografado em 1100×760, com a aba Resultado aberta: a fila de ações do rodapé — "Aplicar FEN",
"Salvar posição reconhecida", "Salvar todos", "Corrigir Net", "2ª opinião" — é **cortada ao
meio** pela borda inferior, e não há rolagem que a alcance. A barra de status sai da janela junto.
Em 940×620, com o Dataset: somem "Aplicar", "Limpar", "Imagem ausente" e o botão **"Remover"**.

O programa continua funcionando — `Ctrl+S` salva —, e é isso que torna o defeito difícil de ver:
ele não gera erro, gera um usuário que não sabe que existe um botão.

**Solução.** Duas medidas, e a segunda é a que importa:

1. `root.minsize()` com o piso real, calculado da soma dos `minsize` dos painéis mais o *chrome*
   — não um número redondo escolhido a olho;
2. **as abas do `Notebook` passam a rolar verticalmente.** Um `Canvas` com `ttk.Frame` interno,
   ou o `ScrolledFrame` do `ttkbootstrap` quando ele está lá, aplicado nas abas cujo conteúdo tem
   altura mínima real (Resultado, Configuração, Galeria). Piso mais rolagem: abaixo do piso a
   janela não vai, e acima dele nada fica inalcançável.

**Critério de aceite.** Em qualquer tamanho permitido pelo piso, **toda** ação de toda aba é
alcançável por rolagem ou está visível; em 1366×768 (a resolução do teste) a fila de salvar do
Resultado é alcançável.

**Testes.** `tests/test_ui_geometria.py`: o cálculo do piso é puro e afirmado contra a soma
declarada dos painéis; e um roteiro que abre a janela em 1366×768, percorre as 6 abas e afirma,
para cada botão registrado como ação, que `winfo_rooty() + winfo_height()` cai dentro do
`viewport` rolável do painel.

---

## S-151 · As barras de ferramentas refluem em vez de cortar ✅ implementada (2026-08-17)

**Problema.** `ui/pdf_panel.py:242-343` empilha **cinco** barras (`row`, `nav`, `acoes`,
`field_row`, `zoom_row`) antes de a página aparecer: ~200 px, 20% da altura da janela gastos em
controle permanente sobre o painel cuja única razão de existir é mostrar a página grande.

E nenhuma delas reflui. Todas usam `pack(side=LEFT)` numa linha de altura fixa, então quando
falta largura o Tk simplesmente **não desenha** o que passou da borda: em 1100 de largura somem
"Exportar PDF → PGN", "Cancelar exportação", "Tirar o selecionado" e a contagem de diagramas da
página. Sem aviso, sem reticências, sem `>>`.

**Solução.** Um contêiner de barra que sabe duas coisas que `pack` não sabe: **quebrar em duas
linhas** quando a soma das larguras pedidas passa da disponível, e **colapsar por prioridade** —
o rótulo do arquivo encurta antes de um botão sumir, e o que sobrar vai para um botão de
transbordo. A decisão (quais itens em qual linha, para uma largura dada e uma lista de larguras
mínimas e prioridades) é função pura; o widget só executa o arranjo que ela devolveu.

Junto disso, a reorganização que reduz de cinco barras para duas: navegação de página e zoom são
o mesmo eixo ("onde estou e quão perto"), e "Conjunto de campo" é uma tarefa de anotação que não
pertence à barra de visualização — vai para o rodapé da S-163 ou para o menu da S-161.

**Critério de aceite.** Nenhum controle do painel do PDF fica invisível em qualquer largura
permitida pelo piso da S-150; o painel gasta no máximo duas barras acima da página em 1700 de
largura.

**Testes.** `tests/test_ui_barra.py`: a função de arranjo com larguras conhecidas — cabe em uma
linha, cabe em duas, não cabe e transborda —, afirmando que **nenhum** item é descartado em
nenhum dos três casos (é essa a propriedade que hoje falha).

---

## S-152 · `wraplength` derivado da largura real, não cravado ✅ implementada (2026-08-17)

**Problema.** Doze `wraplength` cravados, de 220 a 780 px:

```
dataset_panel.py:184   780      review_panel.py:127,128  760
study_panel.py:118     620      study_panel.py:165       600
result_panel.py:278    520      training_dialog.py:177,178 480
app_tkinter.py:1245    460      app_tkinter.py:365       320
gallery_panel.py:285   220
```

A largura real do painel esquerdo varia de 420 (o `minsize`) a ~1180 (divisor à direita). Nenhum
dos doze consulta `winfo_width`. As duas falhas acontecem juntas em telas diferentes: com o
painel estreito o texto é **cortado** — o texto verde de procedência da Galeria, com
`wraplength=220`, aparece truncado no meio da palavra ("Whit", "Jam", "antiga") porque a lateral
inteira está cortada pela S-154 —, e com o painel largo ele **quebra cedo**, deixando quatro
linhas curtas num espaço que caberia uma.

**Solução.** Um auxiliar que liga o `wraplength` de um rótulo ao `<Configure>` do pai, com um
piso e um teto. Um lugar, e os doze passam a chamá-lo. O teto existe porque linha de texto muito
longa é ruim de ler mesmo quando cabe — 90 caracteres é o limite, e ele fica nos tokens da S-145
como medida, não como pixel.

**Critério de aceite.** Nenhum `wraplength=<número>` no código de painel; ao arrastar o divisor,
todo texto multi-linha reflui e nenhum fica cortado.

**Testes.** `tests/test_ui_texto.py`: varredura por `wraplength=` literal; e a função de cálculo
(largura do pai, piso, teto) afirmada nos três regimes.

---

## S-153 · Tabela que mostra a coluna que importa ✅ implementada (2026-08-17)

**Problema.** Os dois `Treeview` do projeto — `ui/dataset_panel.py:161-169` e
`ui/review_panel.py:132-139` — têm barra **vertical** e nenhuma **horizontal**. As consequências,
fotografadas:

- no Dataset, em 940 de largura, **6 das 8 colunas** são inalcançáveis; em 1700, 4 delas;
- na Revisão, a coluna **"Motivo"** está truncada em **todas** as 129 linhas. Motivo é a razão de
  a fila existir: "ilegal: mais de um rei da mesma cor; peças brancas demais; o lado…" — o texto
  que diz o que conferir é o texto que não se pode ler.

Somado a isso, `anchor="w"` em todas as colunas, inclusive nas numéricas: `1623.8`, `40`, `1` e
`0.082` alinhados à esquerda não se comparam por magnitude, que é a única leitura que uma coluna
de prioridade tem.

**Solução.** Barra horizontal nos dois; `anchor="e"` e formato por tipo de coluna (a S-169 define
o formato); e uma área de detalhe de uma linha sob a tabela da Revisão que mostra o motivo
**inteiro** do item selecionado — a tabela dá a visão geral, o detalhe dá o texto, e nenhuma das
duas tem de escolher entre as duas coisas.

**Critério de aceite.** Toda coluna de todo `Treeview` é alcançável em qualquer largura permitida
pelo piso; o motivo completo do item selecionado é legível sem redimensionar coluna; colunas
numéricas alinhadas à direita.

**Testes.** `tests/test_ui_tabela.py`: para cada painel de tabela, a soma das larguras declaradas
contra a largura mínima do painel — se a soma passa, o painel **precisa** declarar
`xscrollcommand`, e o teste afirma isso lendo a configuração do widget.

---

## S-154 · A coluna de headers da Galeria cabe, ou rola ✅ implementada (2026-08-17)

**Problema.** `ui/gallery_panel.py:172-173` cria o tabuleiro com lado fixo de 420 px
(`BOARD_VIEW_SIZE`, e o comentário explica bem por que é fixo) dentro de `centro`, que é
empacotado com `expand=True`; a lateral "Headers do PGN" é empacotada **depois**
(`gallery_panel.py:252`) e precisa de ~290 px. Na posição padrão do divisor (42% de 1700) sobram
~680 px para 740 pedidos.

Quem perde é a lateral, porque `expand=True` de `centro` já tomou o espaço: campos cortados,
"Copiar headers para to…" cortado, o texto verde de procedência cortado. São os controles que
gravam a procedência de uma partida — o produto da S-83 a S-94 inteira.

**Solução.** A galeria passa a ter um `PanedWindow` vertical próprio entre tabuleiro+legenda e
headers, ou a lateral ganha rolagem quando não cabe. E o `minsize` do painel esquerdo sobe do 420
de hoje para o que a Galeria de fato precisa — 420 era o número da S-31, quando a Galeria não
existia.

**Critério de aceite.** Na posição padrão do divisor, todos os campos e botões de headers estão
inteiros; em qualquer posição do divisor, alcançáveis.

**Testes.** `tests/test_ui_galeria_layout.py`: a largura mínima declarada da lateral mais a do
tabuleiro contra o `minsize` do painel — o teste falha se o `minsize` for menor que a soma, que é
exatamente o estado de hoje.

---

## S-155 · A moldura do tabuleiro: as coordenadas dentro do canvas ✅ implementada (2026-08-17)

**Problema.** Dois defeitos de geometria em `ui/board_render.py`, e os dois aparecem na tela.

*As letras cortadas.* `_draw_coordinates` (linha 349) desenha as letras em
`origin_y + size + 11`, texto centrado de 9 pt em negrito — precisa de ~18 px abaixo do
tabuleiro. `ui/board_widget.py:594` reserva `margin=28`, que `BoardGeometry.fit` divide entre os
dois lados: **14 px**. A base de "a b c d e f g h" é cortada, e isto vale para os **dois**
tabuleiros da janela.

*O transbordo.* `board_render.py:103` é `size = max(min_size, min(width - margin, height - margin,
max_size))`. Quando o canvas é menor que `min_size`, o `max` externo ganha e o tabuleiro fica
**maior que o canvas** — em vez de encolher, ele vaza.

**Solução.** A margem deixa de ser um número no chamador e passa a ser derivada da métrica da
fonte de coordenada (a S-149 já fornece a fonte): `2 × (deslocamento + meia-altura)`, arredondado
para cima. E o transbordo vira decisão explícita: abaixo do mínimo, `fit` devolve o tamanho do
canvas e quem chama sabe que está no limite — não há tamanho em que desenhar fora do canvas seja
a resposta certa.

**Critério de aceite.** As oito letras e os oito números estão inteiros e legíveis nos dois
tabuleiros, em qualquer tamanho de painel; o tabuleiro nunca excede o canvas.

**Testes.** `tests/test_board_geometry.py` (estende o que já existe): `fit` com canvas menor que
`min_size` devolve tamanho ≤ canvas; e a margem calculada para uma fonte dada é ≥ o
deslocamento vertical usado pelo desenho — um teste que amarra os dois números que hoje estão
soltos em arquivos diferentes.

---

## S-156 · Geometria, divisor e aba lembrados entre execuções ✅ implementada (2026-08-17)

**Problema.** `ui/state.py:48-72` lembra o PDF, a página, os dois zooms e três interruptores — e
esse cuidado está documentado item por item. Não lembra: **o tamanho da janela**, **a posição do
divisor** e **a aba aberta**.

Pior que não lembrar: `app_tkinter.py:233` agenda `_set_initial_sashes`, que 180 ms após a
abertura **reposiciona** o divisor em 42% da largura. Quem trabalha com o PDF grande arrasta o
divisor toda sessão e o perde toda sessão. E a janela abre sempre na **Configuração**, a aba menos
usada depois do primeiro dia.

**Solução.** Três campos novos no `AppState` (geometria, fração do divisor, aba), com a mesma
disciplina dos que já existem: o padrão vale na primeira execução, a escolha do usuário vale
depois. `_set_initial_sashes` passa a aplicar a fração **guardada** e só cai nos 42% quando não
há nada guardado. A geometria restaurada é validada contra os monitores atuais — janela salva num
monitor que já não existe volta para o principal, e não para fora da tela.

**Critério de aceite.** Fechar e reabrir devolve tamanho, divisor e aba; uma geometria fora dos
limites da tela atual é corrigida em vez de aplicada; sem estado salvo, o comportamento é o de
hoje.

**Testes.** `tests/test_ui_state.py` (estende o que já existe): ida e volta dos três campos
novos; a função pura que valida geometria contra uma lista de retângulos de monitor, com o caso
"monitor desapareceu" e o caso "cabe em parte".

---

## S-157 · A página centralizada, e o primeiro zoom que serve ✅ implementada (2026-08-17)

**Problema.** O canvas do PDF (`ui/pdf_panel.py:338`) desenha a página encostada no canto
superior esquerdo. Em 40% de zoom numa janela de 1700, ~45% da área de visualização é vazio
`#1c1c1c` à direita da página — a maior área contínua da janela, gasta em nada, exatamente no
painel que existe para mostrar a página grande.

E o zoom inicial vem do estado ou de um padrão de 0,7; `fit_width` existe (`pdf_panel.py:412`,
com atalho `Ctrl+0`) e **não** é usado no primeiro desenho. Não há "ajustar à página", que é o
enquadramento que o trabalho pede: ver a página inteira para escolher o diagrama.

**Solução.** A página é centralizada quando é menor que a área visível — cálculo puro do desvio a
partir do tamanho da página, do zoom e do tamanho do canvas. "Ajustar à página" entra ao lado de
"Ajustar à largura", e o primeiro desenho de um livro sem estado guardado usa "ajustar à página".

**Critério de aceite.** Página menor que a área visível aparece centralizada nos dois eixos;
abrir um livro novo mostra a primeira página inteira; a escolha de zoom do usuário continua
sendo lembrada.

**Testes.** `tests/test_pdf_viewport.py` (estende o que já existe): o desvio de centralização em
página menor, igual e maior que o canvas; e o zoom de "ajustar à página" para três proporções de
página.

---

# Fase 22 — Cor com um significado só

> Curta, e é o achado que o usuário sente sem saber nomear.

## S-158 · Um eixo, um significado: azul e violeta na página e no tabuleiro ✅ implementada (2026-08-17)

**Problema.** Duas paletas, cada uma impecavelmente documentada no seu arquivo, dizendo coisas
diferentes com a mesma cor a 30 cm de distância na mesma janela:

| cor | na página (`ui/pdf_panel.py:80-104`) | no tabuleiro (`ui/board_render.py:39-47`) |
|---|---|---|
| azul | `#4da3ff` — localizado, **ainda não lido** | `#3d7dd4` — casa **reescrita** pelo decodificador |
| violeta | `#9b7bff` — a base reconheceu: **não precisa de você** | `#8e44ad` — as duas leituras **discordam**: olhe |

O olho aprende cor antes de rótulo. Violeta na página quer dizer "pule"; violeta no tabuleiro
quer dizer "pare". Nenhum dos dois arquivos está errado sozinho — e é por isso que nenhuma
auditoria de arquivo achou isto.

**Solução.** Um eixo declarado uma vez, nos tokens da S-145, com os papéis nomeados pelo que
**significam** e não pela cor: `A_FAZER`, `PRONTO`, `DISPENSADO`, `ATENCAO`, `REESCRITO`,
`EM_DISPUTA`, `PROBLEMA`. Os papéis de página e de casa que não podem coexistir na cabeça do
usuário não podem compartilhar matiz — e essa regra fica escrita como teste, não como convenção.

**Critério de aceite.** Nenhuma matiz carrega dois significados na janela; a tabela
papel→significado→cor existe num lugar só e é a mesma que os dois painéis leem.

**Testes.** `tests/test_ui_semantica_cor.py`: os pares de papéis declarados incompatíveis têm
diferença de matiz acima de um limiar; nenhum papel aparece duas vezes com cores diferentes.

---

## S-159 · A cor não é o único portador do estado ✅ implementada (2026-08-17)

**Problema.** `ui/pdf_panel.py:747-786` desenha quatro estados de diagrama em quatro matizes,
com o número numa etiqueta preenchida da mesma cor. Não há forma, traço nem letra que distinga um
estado do outro. E o par mais crítico é o menos distinguível: azul `#4da3ff` contra violeta
`#9b7bff` tem **1,20:1** de razão de contraste entre si, separados essencialmente por matiz, em
linha de 2 px sobre página impressa hachurada.

Para quem tem protanopia ou deuteranopia — ~8% dos homens — "ainda a fazer" e "não precisa" são o
mesmo retângulo. E são justamente os dois estados cuja confusão custa trabalho: refazer o que já
estava pronto, ou pular o que faltava.

**Solução.** Um segundo canal, e o barato é o traço, porque a caixa já é um retângulo: contínuo
para "a fazer", tracejado para "dispensado", grosso contínuo para "pronto". A etiqueta do número
ganha um glifo de estado (`✓` para pronto, `·` para dispensado) — ela já é preenchida e já tem
contraste medido de 6:1 a 10:1 contra o texto `#101010`. E os quatro estados continuam explicados
por texto no rótulo da página, que a S-163 realoja.

**Critério de aceite.** Os quatro estados são distinguíveis numa impressão em tons de cinza da
captura de tela — é este o teste do canal redundante, e ele é objetivo.

**Testes.** `tests/test_page_overlay.py` (estende o que já existe): a função que decide traço e
glifo por estado é total e injetiva — dois estados não compartilham o par (traço, glifo).

---

## S-160 · Os dois amarelos do tabuleiro ✅ implementada (2026-08-17)

**Problema.** `ui/board_render.py:37-38`: casa selecionada `#f7ec74` e casa do último lance
`#cdd26a`, **1,32:1** entre si, e frequentemente adjacentes — selecionar a casa de destino do
lance que acabou de ser jogado é o gesto mais comum da aba Análise.

**Solução.** A seleção passa a usar o canal que a S-159 estabelece: contorno, não preenchimento —
o mesmo raciocínio que `ui/pdf_panel.py:747` já aplicou às caixas da página ("uma propriedade
visual, uma informação"), e que aqui faltou. O amarelo do último lance fica sozinho no seu papel.

**Critério de aceite.** Casa selecionada e casa de último lance são distinguíveis quando
adjacentes, e em tons de cinza.

**Testes.** `tests/test_board_render.py` (estende o que já existe): a seleção não altera o
preenchimento da casa; e os pares de cor de casa declarados têm contraste acima do limiar.

---

# Fase 23 — Navegação e retorno ao usuário

> Onde as coisas moram, e como o programa responde. Vem depois da 21 porque mover controle que
> ainda desaparece quando a janela encolhe é mover o problema.

## S-161 · Barra de menus: um lugar para abrir, exportar, preferências e ajuda ✅ implementada (2026-08-17)

**Problema.** `grep -rn "tk.Menu" src/ app_tkinter.py` devolve vazio: **não há barra de menus**.
Os ~70 comandos da janela são botões permanentemente visíveis, o que produz três consequências
juntas: as barras ocupam 20% da altura (S-151), a ação rara compete visualmente com a frequente,
e o que não é botão **não existe** — não há "Abrir recente", não há "Preferências" (o
`settings.json` da S-32 só é editável fora do programa), não há "Ajuda", não há a lista dos 11
atalhos.

**Solução.** Uma barra de menus com o mínimo honesto — **Arquivo** (Abrir PDF, Abrir recente,
Abrir no leitor do sistema, Exportar para PGN, Sair), **Editar** (Aplicar FEN, Apagar casa, o
que já tem atalho), **Ver** (zoom, marcar diagramas, roda vira a página, tema), **Ferramentas**
(Treinar modelo, Recarregar modelo, Varrer livro, Varrer fila, Conjunto de campo),
**Ajuda** (Atalhos, Sobre, Abrir o log). Todo item de menu que tem atalho **mostra o atalho** —
é assim que o atalho passa a ser descoberto.

O menu não substitui botão: ele dá casa ao comando raro, e é o que autoriza a S-151 a tirar da
barra o que hoje está lá só porque não havia outro lugar.

**Critério de aceite.** Todo comando da janela é alcançável pelo menu; todo comando com atalho
mostra o atalho no menu; nenhum comando sai da janela sem estar no menu.

**Testes.** `tests/test_ui_menu.py`: a definição do menu é dado, não código de widget — uma
estrutura declarativa; e o teste afirma que o conjunto de comandos do menu contém o conjunto de
atalhos de `bind_shortcuts` (`app_tkinter.py:1298-1316`) e que cada rótulo traz o acelerador.

**Como ficou.** Dois módulos e uma tabela na janela. `ui/atalhos.py` declara as dez teclas —
sequência do Tk, rótulo lido, nome do comando, descrição — e é a fonte que `bind_shortcuts`, o
menu e (na S-165) a legenda consomem; `ui/menu.py` declara os cinco menus como dado, sem
`tkinter` até `montar`. O que ficou no `app_tkinter.py` é `_comandos`: 26 nomes → métodos, a única
parte que precisa dos painéis.

`montar` **recusa** uma declaração cujo item não tenha comando, pela mesma disciplina de
`tokens.cor`: um item de menu inerte é pior que a ausência dele, porque a pessoa conclui que a
função existe e está quebrada. O acelerador é só mostrado, nunca ligado — quem liga é o
`bind_shortcuts`, que tem a guarda de foco da S-20 (`←` dentro do campo de FEN é do campo); o
acelerador do Tk não tem guarda, e as duas ligações fariam a tecla disparar duas vezes.

**O critério de aceite ficou cumprido pela metade, e a metade que falta é declarada.** "Todo
comando com atalho mostra o atalho no menu" está verificado por teste. "Todo comando da janela é
alcançável pelo menu" **não**: são ~70 controles, e a própria spec pede o "mínimo honesto" logo
acima. O menu tem 26 comandos — os do documento, do diagrama, da vista, das ferramentas e da
ajuda. Ficaram de fora os campos de configuração (são estado, não comando), as anotações do
conjunto de campo (a S-77 as põe junto da página de propósito) e a navegação interna da Galeria.
Um menu com 70 itens não seria um mapa da janela: seria a mesma pilha de botões noutra vertical.

**O que a implementação encontrou.** O submenu "Abrir recente" saiu com **29 livros, 13 deles
inexistentes** — o histórico da S-156 guarda caminhos absolutos, e os 13 apontavam para
`C:/PythonChess/`, a pasta anterior do projeto (o mesmo evento que a S-37 documenta). Treze itens
de menu que falham ao serem clicados são o defeito que `montar` recusa na declaração, descoberto
pelo usuário um clique por vez. `AppState.recentes` passou a filtrar por existência — com o
predicado injetável, para o teste não depender de disco — e a mostrar 10, não 50: o histórico
responde "em que página eu parei neste livro?" e o menu responde "qual dos últimos eu quero de
volta?".

---

## S-162 · As abas dizem quanto trabalho têm, e trocam pelo teclado ✅ implementada (2026-08-17)

**Problema.** Três defeitos na mesma barra de abas (`app_tkinter.py:251-327`).

*Dois níveis de navegação misturados.* Configuração, Dataset e Galeria são do **acervo**;
Resultado, Análise e Revisão são do **diagrama aberto agora**. Seis abas de igual peso escondem
que três delas mudam de conteúdo quando se clica num retângulo da página e três não.

*Abre na aba errada.* A primeira aba é Configuração — três caminhos de arquivo e os parâmetros de
treino, isto é, a aba que se usa no primeiro dia e quase nunca depois. O trabalho começa em
Resultado.

*Sem teclado e sem estado.* `enable_traversal()` nunca é chamado: não há `Ctrl+Tab` nem tecla de
acesso. E as abas não dizem o que carregam — 129 pendentes na Revisão, 3.936 linhas no Dataset,
1.480 diagramas na Galeria: informação que hoje só aparece depois de clicar.

**Solução.** Contador no rótulo da aba quando há número que importa (`Revisão (129)`,
`Dataset (3.936)`), com o formato vindo de função pura; `enable_traversal()`; a aba inicial
passa a ser a do trabalho (respeitando o que a S-156 guardou); e a separação dos dois níveis
marcada visualmente — um separador na barra ou o grupo do acervo movido para o menu **Ferramentas**
da S-161.

**Critério de aceite.** `Ctrl+Tab` e `Shift+Ctrl+Tab` circulam as abas; o rótulo de Revisão e
Dataset mostra a contagem e ela se atualiza quando o número muda; a primeira abertura de um
checkout novo cai na aba de trabalho.

**Testes.** `tests/test_ui_abas.py`: a função rótulo(nome, contagem) — sem contagem, com zero
(que não mostra "(0)"), com 129 e com 3.936 (separador de milhar em pt-BR).

**Como ficou.** `ui/abas.py` decide o rótulo -- e o que ele decide são os casos de borda: `None` é
"a aba nunca carregou" e `0` é "não há nada aqui", e **nenhum dos dois vira "(0)"**, porque o
parêntese existe para dizer quanto falta. O milhar é ponto, como no resto da interface.

**A contagem criou uma interação com a S-156, e ela falharia em silêncio.** O `AppState` guarda a
aba aberta **pelo rótulo**; com o número dentro, "Revisão (129)" guardado numa sessão não casaria
com "Revisão (54)" na seguinte -- a janela abriria na primeira aba, sem erro nenhum, e a explicação
estaria a dois módulos de distância. `abas.nome_base` separa identidade de estado, e é ele que
`rolagem.selecionar_aba` compara desde então.

**A contagem do Dataset não pode custar o que custa abrir o Dataset.** A S-116 tornou aquela aba
preguiçosa porque `load_rows` custa 689 ms sobre 3.936 linhas; chamá-lo para preencher um rótulo
desfaria o item. `DatasetPanel.contagem_de_amostras` conta as linhas do arquivo -- leitura
sequencial, milissegundos -- e responde a pergunta do rótulo sem carregar nada.

**A ordem das abas é a separação dos dois níveis.** Resultado, Análise e Revisão (o diagrama aberto
agora) vêm antes de Dataset, Galeria e Configuração (o acervo); o corte entre os grupos é onde a
barra muda de assunto. A Configuração foi para o fim -- é a aba do primeiro dia e quase nunca
depois --, e a janela passou a abrir no Resultado num checkout novo, respeitando o que a S-156
guardou nas execuções seguintes. `enable_traversal()` é uma linha que nunca tinha sido escrita:
`Ctrl+Tab` e `Shift+Ctrl+Tab` circulam as abas, verificado com a janela dirigida.

**O separador visual não entrou.** O `ttk.Notebook` não desenha separador entre abas, e o caminho
alternativo da spec -- mover o grupo do acervo para o menu Ferramentas -- esconderia três abas
atrás de um menu para marcar um agrupamento. A ordem faz o corte; a decisão fica registrada aqui
para não parecer esquecimento.

---

## S-163 · A barra de status é da janela, não do painel esquerdo ✅ implementada (2026-08-17)

**Problema.** `app_tkinter.py:329`:

```python
ttk.Label(self.left_frame, textvariable=self.status_var).pack(anchor="w", pady=(6, 0))
```

Um `ttk.Label` cru dentro do **painel esquerdo**. Cinco consequências, todas observadas:

1. está longe do painel direito, onde o trabalho acontece — a página do PDF é clicada à direita e
   a resposta aparece embaixo à esquerda;
2. mostra o que aconteceu por último em **qualquer** painel: "Dataset carregado: 3936 amostras."
   permanece na tela enquanto o usuário navega a Galeria;
3. não tem severidade: erro, aviso e confirmação têm a mesma aparência — e é por isso que 76
   `messagebox` foram necessários;
4. não tem altura fixa nem separador, então o comprimento do texto move o layout acima dele;
5. **sai da janela** quando ela encolhe (S-150).

**Solução.** Um rodapé de janela, irmão do `PanedWindow` e não filho de um painel: separador,
altura fixa, três zonas — mensagem (com severidade vinda dos tokens da S-145), estado do
documento (livro, página, "N de M salvos" — o que hoje está espremido no fim da barra de zoom em
`pdf_panel.py:790-816`) e indicador de operação em curso, alimentado pelo `BusyRegistry` que já
existe em `ui/busy.py`. Mensagem sem severidade grave expira; erro fica até ser substituído.

**Critério de aceite.** O rodapé é visível em qualquer tamanho permitido pelo piso; erro se
distingue de informação sem ler o texto; o estado do documento não desaparece quando outro painel
escreve uma mensagem; o rodapé mostra que há operação longa em curso sem que ela precise escrever
texto.

**Testes.** `tests/test_ui_rodape.py`: a função que decide zona, severidade e expiração a partir
de (mensagem, origem, operações em curso) — puro, sem `tkinter`, como manda `ui/busy.py`.

**Como ficou.** `ui/rodape.py`: 11 funções puras (severidade, expiração, as três descrições, a
projeção do `BusyRegistry`) mais o widget `RodapeDaJanela`. A janela ficou com quatro linhas — a
construção e **a ordem do `pack`**, que é o item: o rodapé antes do `PanedWindow`, senão ele é o
primeiro a sair da tela em vez do último. O estado do documento saiu da barra de zoom do
visualizador e o `ttk.Label` do painel esquerdo deixou de existir; `_set_status` continua sendo o
ponto único por onde os seis painéis falam, e é ele que dá severidade aos 60 chamadores que não
declaram uma. A altura é fixa **por construção**: todo widget do rodapé existe sempre, e o teste
mede que a altura pedida com o rodapé vazio é a mesma com mensagem longa e operação rodando.

**O que a implementação encontrou, e a avaliação não tinha visto.** A janela dirigida mostrou a
primeira mensagem de erro **preta**. A causa não era do rodapé: `tokens._DO_TEMA` manda perguntar
ao tema a cor de três papéis de texto, e sob `bootstrap-light` os três respondem `#212529` — o
mesmo do `TLabel` base. `style.lookup` sobe a cadeia de herança do Tk, então um `danger.TLabel`
que não declara `foreground` devolve o do pai sem dizer que não tinha o seu. Consequência, aberta
desde a S-145: "já salvo" (verde `#146c43`), "posição ilegal" (vermelho `#c0392b`) e contagem de
apoio (cinza `#555555`) resolviam para a **mesma** cor na janela em execução, e as três medições
da S-146 nunca chegavam à tela. A correção é `tokens._resposta_do_tema` — resposta igual à do
estilo base é ausência de resposta —, e o que a trava é um teste com o `Style` **real** em
`tests/test_theme.py`: o falso sempre dizia que os três eram distintos.

---

## S-164 · Progresso com número e cancelamento para as três operações longas ✅ implementada (2026-08-17)

**Problema.** Três operações passam de um minuto — exportar um livro de 402 páginas, varrer o
livro na Galeria, varrer a fila na Revisão — e as três informam **só por texto**. Há três
`ttk.Progressbar` no projeto (`ui/study_panel.py:163`, `ui/training_dialog.py:180`) e nenhuma
delas está nessas três.

Do outro lado, **76 chamadas de `messagebox`**: o retorno que devia ser ambiente e não-bloqueante
é modal e interrompe. Uma exportação que termina abrindo uma caixa que precisa de clique é uma
exportação que não pode ser deixada rodando.

E o `BusyRegistry` da S-60 já sabe o que está rodando, com detalhe ("época 3 de 8") e com
cancelamento — a informação existe e não chega à tela senão por texto.

**Solução.** O indicador do rodapé da S-163 lê o `BusyRegistry`: barra determinada quando há
total conhecido (páginas de um livro), indeterminada quando não, com o `detail` ao lado e o
cancelamento acessível dali — não num botão que só existe numa barra que a S-151 pode ter
colapsado. `Meter`/`Floodgauge` do `ttkbootstrap` quando disponível, `Progressbar` quando não.
E uma revisão dos 76 `messagebox`: erro que exige decisão continua modal; confirmação de sucesso
vira mensagem de rodapé.

**Critério de aceite.** As três operações longas mostram progresso e podem ser canceladas de um
único lugar; concluir uma exportação não abre caixa modal; a contagem de `messagebox` cai e o que
sobra é decisão, não notificação.

**Testes.** `tests/test_busy.py` (estende o que já existe): a projeção de `BusyRegistry.running()`
para (modo da barra, fração, texto) nos três casos — nada rodando, uma com total, uma sem.

**Como ficou.** `BusyOperation` ganhou `feito` e `total`, e `BusyToken.update` os aceita: o número
vai separado da frase porque derivar a fração de "época 3 de 8" exigiria interpretar um texto que
foi escrito para ser lido. Cinco pontos passam o número — exportação, varredura da Galeria, busca
por posição, varredura da fila e treino —, e a projeção `rodape.ocupacao` decide o modo da barra:
determinada com total conhecido, indeterminada sem ele, e **indeterminada de novo com duas
operações**, porque somar 120 de 402 páginas com 3 de 8 épocas daria o progresso de coisa nenhuma.
O cancelamento é o botão do rodapé, que chama `BusyRegistry.request_cancel` — um lugar só, e não um
botão numa barra que a S-151 pode ter colapsado.

A projeção ficou testada em `tests/test_ui_rodape.py` e não no `test_busy.py`: ela é apresentação,
e o registro não conhece barra nenhuma. O `test_busy.py` ganhou o que é dele — os campos de
progresso, a fração limitada a 1,0 e o `replace` que não apaga o total ao atualizar o detalhe.

**A conta dos modais, medida por AST: 66 → 44.** As 22 que saíram são fim de operação longa (2),
pré-condição de uma frase (9), "já está rodando" (3), confirmação de sucesso que repetia a frase do
rodapé (4) e o "nenhum diagrama nesta página" (1) — este último era um clique obrigatório no caso
**mais comum** do programa. As 44 que ficam são 23 `showerror`, 13 perguntas e 8 instruções de
várias linhas; o critério, a tabela e a catraca estão em `tests/test_ui_retorno_modal.py`, com a
decisão de manter erro modal escrita por extenso.

**Correção de número:** a avaliação disse "76 chamadas de `messagebox`" e o certo é 66. O 76 saiu
de `grep -c messagebox`, que conta também `default=messagebox.NO` e `icon=messagebox.WARNING` —
constantes passadas a outra chamada, não caixas. Nenhuma conclusão do item muda (66 caixas contra
3 barras de progresso é a mesma frase), e fica registrado porque número irreprodutível em documento
é o mecanismo da S-135.

---

## S-165 · A legenda de atalhos, e o tooltip onde ele foi criado para estar ✅ implementada (2026-08-17)

**Problema.** Onze atalhos ligados em `app_tkinter.py:1298-1316` — `←`, `→`, `Ctrl+S`,
`Ctrl+Shift+S`, `Ctrl+R`, `Del`, `Ctrl+N`, `PgUp`, `PgDn`, `Ctrl+0` — e **nenhum** aparece na
interface. Depois da S-150 isso deixa de ser conveniência: em notebook, `Ctrl+S` é o único
caminho para salvar, e ele não está escrito em lugar nenhum.

E `ui/tooltip.py` foi criado na S-32 com um propósito explícito no docstring: "um botão cinza sem
explicação é pior que um botão ausente". São 16 tooltips para ~70 controles, e três deles em
botão desabilitado.

**Solução.** Um diálogo "Atalhos" no menu Ajuda (S-161), gerado **da mesma tabela** que
`bind_shortcuts` consome — uma fonte, não duas, senão eles divergem como divergiram os rótulos de
procedência da S-04. E a regra que fecha a S-32: **todo** controle que pode ficar desabilitado
tem tooltip dizendo o motivo, verificado por teste em vez de por lembrança.

**Critério de aceite.** A legenda mostra os 11 atalhos com a mesma descrição do menu; nenhum
controle desabilitável fica sem motivo escrito.

**Testes.** `tests/test_shortcuts.py` (estende o que já existe): o conjunto de sequências da
legenda é igual ao de `bind_shortcuts` — o teste falha quando alguém adiciona atalho e esquece a
legenda; e um inventário de controles desabilitáveis afirmando que cada um tem texto de motivo.

**Como ficou.** A legenda é `ui/legenda.py`, uma `Toplevel` que **percorre** `atalhos.ATALHOS`. Por
isso o teste previsto acima não existe na forma prevista: não há dois conjuntos a comparar, há um.
O que `tests/test_ui_legenda.py` trava é o que sobrou de arriscado — **nenhuma sequência de tecla
escrita fora de `ui/atalhos.py`**, a mesma varredura que a S-145 fez com hexadecimal — e a
propriedade em si: acrescentar uma linha à tabela a faz aparecer na janela sem ninguém editá-la.
`<Control-MouseWheel>` fica fora da varredura com o motivo escrito: é gesto de mouse, não cabe como
acelerador de menu, e uma legenda de teclado que o listasse prometeria uma tecla que não existe.

A legenda é `Toplevel` e não `messagebox` porque a tecla é dado: vai em monoespaçada pela S-149, e a
caixa do sistema desenharia `Ctrl+S` com a mesma aparência da frase ao lado — que é justamente o que
não ajuda a achar a linha certa. Ela também diz a guarda de foco da S-20, no único lugar em que
alguém pergunta "por que a seta não trocou de diagrama agora?".

**São dez atalhos, e não onze.** O critério de aceite acima diz 11 e a lista da avaliação tem 10;
`_bind_shortcuts` ligava 10. Corrigido em `ui/atalhos.py`, com o teste contando.

**A segunda metade fechou a S-32, e ela estava mais aberta do que a avaliação disse.** A varredura
de `tests/test_ui_motivos.py` encontrou **13 controles desabiláveis sem tooltip nenhum**: o
"Cancelar" da Galeria, o da fila, o da exportação, o "Exportar PDF → PGN", o "Analisar posição", o
combo de variantes, o campo do número do lance, o "Partidas vizinhas", o "Treinar modelo" e o
"Cancelar" do rodapé recém-nascido. Todos ganharam o motivo, e o teste passou a exigi-lo de quem
escrever o próximo `state=tk.DISABLED`.

Duas exceções ficaram declaradas com o motivo: os dois `tk.Text` de leitura (a lista de lances e o
detalhe do Dataset), onde `state=DISABLED` é como o Tk faz um texto não editável — não são controle
desligado, e exigir tooltip ali seria ruído com aparência de rigor. E dois botões continuam com o
motivo **escrito na hora** (`disabled_reason()`), porque "não configurado" e "configurado e
desligado" são situações diferentes e uma frase fixa não daria conta das duas — que é exatamente a
razão pela qual `Tooltip.set_text` existe desde a S-32.

---

# Fase 24 — Cópia, formulário e estados vazios

> Independente das quatro anteriores; pode andar em paralelo. Fica no fim porque é a única fase
> cujo erro não custa nada além de si mesmo.

## S-166 · O vocabulário: pt-BR, e um nome por conceito ✅ implementada (2026-08-17)

**Problema.** `ui/strings.py` foi criado na S-04 com o critério certo — "entra o que duas telas
precisam dizer igual" — e três classes de termo ficaram fora.

*Inglês no meio do português:* "Zoom board" (`result_panel.py:251`), "Virar board"
(`study_panel.py:88`), "Heatmap de incerteza" (`result_panel.py:256`), "Corrigir Net"
(`net_button.py:65`), "Batch size" e "Learning rate" (`app_tkinter.py:357-358`), "Headers do
PGN" (`gallery_panel.py:251`), "Split" (`dataset_panel.py:144`) — e **`pending` repetido em 129
linhas** da coluna Status da fila, enquanto o filtro ao lado diz "Só pendentes".

*Um conceito, dois nomes:* "Varrer PDF" (`review_panel.py:114`) e "Varrer livro"
(`gallery_panel.py:145`); "Lado a jogar" (`result_panel.py:304`) e "Vez"
(`gallery_panel.py:328`); "Brancas/Pretas" e "brancas/pretas".

*Rótulo que descreve a própria tela:* `ttk.LabelFrame(self, text="PDF (direita)")`
(`pdf_panel.py:239`) — o nome do grupo é a posição dele no layout. E `->` no lugar de `→`
(`pdf_panel.py:275`), `<<`/`>>`/`|<`/`>|` como navegação (`gallery_panel.py:179-182`,
`study_panel.py:94-97`).

**Solução.** Os termos entram em `ui/strings.py` sob o critério que já está escrito lá, com a
decisão registrada onde ela é discutível: "FEN" e "PGN" **ficam** — são o nome do formato, não
palavra estrangeira; "heatmap" vira "mapa de incerteza"; "Net" vira o nome do que o botão faz;
"Split" vira "conjunto"; `pending` vira "pendente". "Varrer o livro" para os dois lugares que
varrem. E os glifos `→ ⏮ ◀ ▶ ⏭` no lugar do ASCII.

**Critério de aceite.** Nenhum termo em inglês na interface exceto FEN, PGN e nomes próprios; um
conceito, um nome, verificado entre painéis; nenhum rótulo descreve posição na tela.

**Testes.** `tests/test_strings.py` (estende o que já existe, que hoje só verifica acentuação):
uma lista de termos proibidos varrida nos literais de `src/` e `app_tkinter.py`; e a afirmação de
que os termos compartilhados vêm de `strings.py` e não de literal repetido.

**Como ficou.** Quinze termos entraram em `ui/strings.py`, cada um com o motivo da escolha escrito
ao lado. As decisões discutíveis, ditas: **FEN e PGN ficam** (são o nome do formato, como JPEG);
"Zoom" fica (entrou no português e não tem substituto de uma palavra); "heatmap" virou "mapa de
incerteza"; **"Net" virou "Corrigir pela rede"**, porque "Net" não é o nome de nada e o que a
pessoa precisa saber antes de clicar é que a imagem sai da máquina; "Split" virou "Conjunto";
`pending` virou "pendente" -- ele aparecia em 129 linhas da coluna Status enquanto o filtro ao lado
dizia "Só pendentes". "Varrer o livro" passou a nomear os dois lugares que varrem, e `PDF
(direita)` virou "Livro em PDF": um rótulo que descreve a própria posição mente assim que alguém
arrasta o divisor. Os glifos `⏮ ◀ ▶ ⏭ →` substituíram `|< << >> >| ->`.

**O teste achou dois lugares que a leitura não tinha achado.** O primeiro foi o próprio menu da
S-161, que escrevia "Varrer o livro" como literal -- a segunda cópia do termo nasceu no mesmo dia
em que ele foi centralizado. O segundo foi `examples/streamlit_demo.py`, com "Batch size",
"Learning rate", "PDF fixo (direita)" e um "Lado a jogar" à mão: o exemplo não é a interface
(S-54), mas é a mesma tela descrita duas vezes, e é exatamente o mecanismo que a S-04 documenta.

**A varredura usa fronteira de palavra, e isso é decisão.** `max_boards`, `board_zoom` e
`val_board_exact_acc` são chaves -- de opção, de estado e de métrica --, não texto de tela.
Renomeá-las por causa deste teste mudaria a API por causa de uma varredura sobre **interface**, que
é o oposto do que ela existe para proteger.

---

## S-167 · O título da janela diz o produto, o livro e a página ✅ implementada (2026-08-17)

**Problema.** `app_tkinter.py:126`: `"Chess Diagram OCR - Tkinter"`. Nomeia o **toolkit** — que é
a única informação da frase que não interessa a ninguém que use o programa —, não nomeia o
produto (ChessVisionOFF) e não diz o que está aberto. Ao voltar de outra janela pelo Alt-Tab, o
título é a única coisa que se lê, e ele não diz o livro nem a página.

**Solução.** `Karpov A — Chess Combinations · p. 12 — ChessVisionOFF`: o que muda primeiro à
esquerda, o produto no fim. O texto vem de função pura (livro, página, total), e o `•` de
trabalho não salvo entra quando houver.

**Critério de aceite.** O título nomeia o livro e a página e acompanha a navegação; sem livro
aberto, nomeia o produto.

**Testes.** `tests/test_ui_titulo.py`: a função de título com e sem livro, com nome longo
(truncado no meio, preservando o começo e a extensão) e com página fora de faixa.

---

## S-168 · Os três caminhos com "Procurar…", e o campo que não aceita letra em número ✅ implementada (2026-08-17)

**Problema.** `app_tkinter.py:332-334` monta `Modelo (.pt)`, `CSV labels` e `Pasta samples` com
`_entry_row` (`app_tkinter.py:419-423`): um `ttk.Entry` de texto livre. **Sem botão
"Procurar…"** e sem verificação de existência, num programa que usa `filedialog` em cinco outros
lugares. Um caractere errado no caminho do modelo só se manifesta como falha na hora do OCR.

`Learning rate` (`app_tkinter.py:358`) é o mesmo `_entry_row` ligado a um `DoubleVar`: uma letra
digitada faz o `get()` levantar `TclError` — na hora de treinar, não na hora de digitar.

E a grade de alinhamento quebra em dois pontos: a coluna de rótulos tem `width=16` em
`_entry_row`/`_spin_row` e **`width=24`** na linha de orientação (`app_tkinter.py:340`), então
essa linha não alinha com nenhuma outra; e `Learning rate` estica pela largura toda ao lado de
spinboxes de `width=12`, deixando a borda direita irregular.

**Solução.** `_entry_row` ganha uma variante de caminho, com botão "Procurar…" (arquivo ou pasta,
conforme o campo) e um indicador de existência ao lado — verde quando existe, aviso quando não,
usando os papéis da S-145 e não cor cravada. A taxa de aprendizado vira `ttk.Spinbox` com
incremento e faixa, ou `Entry` com validação na digitação; a largura de rótulo vira uma constante
única; e a taxa recebe a mesma largura dos outros campos numéricos.

**Critério de aceite.** Os três caminhos são escolhíveis por diálogo e dizem se existem antes de
qualquer OCR; nenhum campo numérico aceita valor que faça `get()` levantar; uma coluna de rótulos
alinhada em toda a aba.

**Testes.** `tests/test_ui_formulario.py`: a função de validação de caminho (existe, não existe,
vazio, é pasta quando se esperava arquivo); a de número (`"0,001"`, `"1e-3"`, `"abc"`, vazio); e a
varredura que afirma uma única largura de rótulo na aba.

---

## S-169 · Precisão honesta na fila, e o dado cru que não chega à tela ✅ implementada (2026-08-17)

**Problema.** `ui/review_panel.py:55-56` mostra prioridade com uma casa decimal — `1623.8`,
`1617.2`, `1135.5` — em número que ninguém compara nesse detalhe: a casa decimal é ruído com
aparência de exatidão. Confiança aparece como `0.082`, quando a interface fala de confiança em
porcentagem em todo outro lugar.

E `ui/dataset_panel.py:42-43` publica o dado cru na coluna "Lado": `w`, `b`, `—`. O
`ui/strings.py` existe desde a S-04 justamente para que "brancas" tenha um nome só, e a tabela
mostra a letra do CSV.

**Solução.** Formato por tipo de coluna, em função pura: prioridade inteira, confiança em
porcentagem com uma casa (`8,2%`), lado pelo rótulo de `strings.py`, data em formato local. O
valor de ordenação continua sendo o número — formatar é da apresentação, e ordenar pela string
formatada é o defeito clássico que o teste previne.

**Critério de aceite.** Nenhuma coluna mostra dado cru nem precisão que o número não tem;
ordenar por uma coluna formatada ordena pelo valor, não pelo texto.

**Testes.** `tests/test_ui_formato.py`: cada formatador com valor típico, zero, negativo e
ausente; e a afirmação de que a chave de ordenação de uma coluna formatada é o valor original.

---

## S-170 · O estado vazio do Resultado, e o destrutivo com cara de destrutivo ✅ implementada (2026-08-17)

**Problema.** Três coisas que a tela diz e que não são verdade.

*Dado onde não há dado.* Ao abrir, a aba Resultado mostra um tabuleiro **completo na posição
inicial** com o campo de FEN vazio. Parece um diagrama reconhecido; é o padrão do
`ui/editor_model.py`. Um usuário que clique "Salvar posição reconhecida" nesse estado salva a
posição inicial como se fosse leitura de uma página.

*Rótulo depois do campo.* `ui/result_panel.py:318-320` empacota o rótulo "Lance" com
`side=RIGHT` **antes** do campo, também `side=RIGHT` — e o Tk põe o primeiro mais à direita.
O resultado na tela é `[campo] Lance`, ao contrário da ordem de leitura, e é o único campo da
janela assim.

*Destrutivo indistinguível.* "Remover" (`ui/dataset_panel.py:182`) apaga linha do `labels.csv`
— trabalho humano, o mesmo que o comentário de `app_tkinter.py:156-161` protege com tanto cuidado
— e tem exatamente a aparência de "Abrir no editor". "Quarentena" também.

**Solução.** Um estado vazio explícito no Resultado: tabuleiro vazio ou esmaecido, uma frase que
diz o que fazer ("clique num diagrama marcado da página, ou use OCR desta página") e as ações de
salvar desabilitadas com tooltip pela regra da S-165. O rótulo "Lance" volta para antes do campo.
"Remover" e "Quarentena" recebem o papel `DESTRUTIVO` da S-144, e "Remover" ganha confirmação que
**nomeia** o que será apagado e quantas linhas.

**Critério de aceite.** Sem diagrama carregado, o Resultado não mostra posição nenhuma e não
oferece salvar; toda ação destrutiva se distingue visualmente e nomeia o alvo antes de agir.

**Testes.** `tests/test_result_panel.py` (estende o que já existe): o estado inicial não tem
posição e as ações de salvar estão desabilitadas; a frase de confirmação de remoção nomeia
arquivo e contagem para 1 e para N linhas.

**Como ficou.** As três coisas, e a primeira era um defeito com consequência em disco.

*O tabuleiro cheio.* `update_views` já sabia desenhar o tabuleiro vazio quando não há diagrama --
ele só **nunca era chamado na construção**, então a aba abria com a posição inicial que o
`InteractiveBoard` desenha por padrão e a FEN vazia ao lado. Uma linha no fim do `__init__`
resolve o desenho; o resto do item é o que ela revelou: quem clicasse "Salvar posição reconhecida"
naquele estado gravava a **posição inicial** no `labels.csv` como leitura de uma página. As três
ações de edição passam a ficar cinza sem diagrama, com o motivo no tooltip pela regra da S-165, e
a aba ganhou uma frase que diz **o que fazer** -- "clique num diagrama marcado da página, ou use
'OCR todos diagramas'" --, e não que está vazia: "sem dados" descreve a tela; o gesto seguinte é o
que a pessoa procura.

*O rótulo depois do campo.* `[campo] Lance` era o `pack` fazendo o que lhe pediram: dois widgets
com `side=RIGHT` saem na ordem em que chegam, da direita para a esquerda. Empacotar o campo antes
do rótulo devolve a ordem de leitura sem mudar o lado da linha em que os dois ficam. O teste mede
o `winfo_rootx` dos dois -- é a única forma de afirmar "à esquerda" sem reimplementar o `pack`.

*O destrutivo.* "Remover" e "Quarentena" já tinham ganhado o papel `DESTRUTIVO` na S-144; o que
faltava era a pergunta **nomear** o que vai sumir. `strings.frase_de_remocao` diz o arquivo, a
contagem e os nomes -- todos até cinco, e "e mais N" acima disso, porque uma pergunta que ninguém
lê não protege nada. Uma amostra é dita pelo nome; muitas dizem contagem e nomes, porque estender
a seleção de um `Treeview` sem querer é um `Shift+clique` a mais e a única defesa é ver quais.

E o teste fecha o par nos dois sentidos: quem apaga usa `DESTRUTIVO`, **e quem não apaga não usa**
-- se tudo é vermelho, nada é.
