# Roadmap da interface — Fases 20 a 24

Avaliação de interface gráfica do `app_tkinter`. Especificação detalhada em
[SPEC_UI.md](SPEC_UI.md) (S-144 a S-170). Para o *como* de hoje,
[ARCHITECTURE.md](ARCHITECTURE.md); para o sequenciamento das fases de modelo e detecção, que
esta avaliação **não** toca, [ROADMAP_FASE14.md](ROADMAP_FASE14.md).

**Data da avaliação:** 2026-08-17 · **Ramo:** `fase-5-modelo-desempenho` · **Commit base:** `3799f35`

---

## Como esta avaliação foi feita, e por que foram três passadas

O método das avaliações anteriores deste projeto é auditar o código e refutar cada achado. Para
interface isso não basta: **o defeito de interface mora no pixel, não no `if`.** Um `pack` que
corta um botão é código correto. Uma cor que significa duas coisas é uma constante bem
documentada em dois arquivos que nunca se leram.

Então a avaliação abriu a janela. Três vezes, com um instrumento diferente em cada passada, e
cada passada teve de achar o que a anterior não tinha achado — foi essa a regra, e é ela que
explica por que o achado mais grave está na segunda e o mais interessante na terceira.

| passada | instrumento | o que ela viu |
|---|---|---|
| **1ª** | leitura dos 30 módulos de `ui/` + a janela aberta em 1700×980, as 6 abas fotografadas | a fundação visual: o tema comprado e não usado, 24 cores cravadas, 5 barras empilhadas, o vazio preto do canvas |
| **2ª** | a janela **dirigida por script** em 1100×760 e 940×620, e o contraste de cada par de cores calculado | que o problema não é feiura: abaixo de ~1500×840 a janela **apaga controles**, e duas cores do produto reprovam em contraste com número |
| **3ª** | o significado, não a aparência: o que cada cor, cada rótulo e cada aba **dizem** | que a cor já é uma linguagem, e diz coisas diferentes em dois painéis lado a lado |

A janela foi dirigida pelo roteiro que o [CONTRIBUTING.md](../CONTRIBUTING.md) já documenta
("Rodar a interface sem clicar"), com uma extensão: em vez de imprimir estado, o roteiro
seleciona cada aba, redimensiona a janela e fotografa a si mesmo com `ImageGrab.grab(bbox=...)`
da própria geometria. Nenhum clique global, nenhuma outra janela tocada — e o resultado é
reprodutível, que é o que separa uma avaliação de interface de uma opinião sobre ela.

**Os números de cor foram calculados, não estimados.** Todo contraste citado abaixo é a razão
WCAG 2.1 entre as duas cores exatas do código-fonte. Todo valor de estilo foi lido do objeto
`ttkbootstrap.Style` em execução, não do que a documentação da biblioteca promete.

### O que esta avaliação não fez

Está dito aqui para que ninguém procure: **não** há porte para Qt, **não** há tema escuro por
padrão, **não** há redesenho de ícones de peça e **não** há mudança de fluxo de trabalho. Os dois
gatilhos do porte para Qt continuam registrados no `ARCHITECTURE.md` e nenhum dos dois foi
puxado por esta análise — ao contrário, ela encontrou muito valor ainda não gasto **dentro** do
`ttk`. A razão do tema claro está escrita em `ui/theme.py:29-39` e continua correta: o produto é
comparar diagrama impresso em papel branco com o que o modelo leu.

---

## O eixo da avaliação: a janela não é feia, ela é invisível a si mesma

Três frases resumem as três passadas, e as três são medições.

**1. O projeto paga por um sistema de design e não pede nada dele.** `ttkbootstrap` 2.2.0 está
instalado, o tema `bootstrap-light` é aplicado com sucesso (`ui/theme.py:77`) — e **nenhum dos
~70 widgets da janela pede um estilo**. `grep -rn bootstyle src/ app_tkinter.py` devolve zero
linhas. O que isso custa, medido no objeto `Style` em execução:

| o que a janela usa hoje | o que já existe carregado no mesmo objeto |
|---|---|
| `TButton` → fundo `#f0f0f0`, texto `#000000`, relevo `raised` | `primary.TButton` → fundo `#0a58ca`, texto `#ffffff`, plano |
| — | `danger.TButton`, `success.TButton`, `secondary.TButton`, `link.TButton` |
| — | `Meter`, `Floodgauge`, `ToolTip`, `Icon`, `Fonts` |

O botão "Salvar posição reconhecida" e o botão "Remover" — que apaga trabalho humano do
`labels.csv` — são **pixel por pixel o mesmo botão cinza de relevo levantado**. A paleta que os
distinguiria está na memória do processo desde a linha 129 do `app_tkinter.py`.

**2. Abaixo de ~1500×840 a janela não fica apertada: ela apaga controles.** Não há
`root.minsize()`. Não há refluxo de barra, não há rolagem de aba, e nada avisa. O que
desaparece, fotografado:

| tamanho | o que a janela deixa de ter |
|---|---|
| **1100×760** | a fila de ações do Resultado cortada ao meio — "Aplicar FEN", "Salvar posição reconhecida", "Salvar todos", "Corrigir Net" ficam **inalcançáveis**; a barra de status sai da janela; no painel do PDF somem "Exportar PDF → PGN", "Cancelar exportação", "Tirar o selecionado" e a contagem de diagramas |
| **940×620** | 6 das 8 colunas do Dataset (não há rolagem horizontal); o botão "Remover"; "Aplicar" e "Limpar" dos filtros; a linha de estatísticas cortada em "1 sem" |

1366×768 é a resolução de um notebook comum. Nela, **o atalho `Ctrl+S` é o único caminho para
salvar**, porque o botão não está na tela — e o atalho não está documentado em lugar nenhum da
interface.

**3. A cor já é uma linguagem, e ela diz duas coisas ao mesmo tempo.** Este é o achado que só a
terceira passada encontrou, porque ele não existe em arquivo nenhum: ele existe **entre** dois
arquivos, e os dois estão certos sozinhos.

| a cor | o que ela diz na página do PDF (`ui/pdf_panel.py:80-104`) | o que ela diz no tabuleiro (`ui/board_render.py:35-49`) |
|---|---|---|
| **azul** | `#4da3ff` — localizado pelo detector, **ainda não lido** | `#3d7dd4` — casa **reescrita** pelo decodificador |
| **violeta** | `#9b7bff` — a base de partidas reconheceu: **não precisa de você** | `#8e44ad` — as duas leituras **discordam**: olhe esta casa |

Os dois painéis ficam lado a lado na mesma janela, e o olho aprende cor antes de aprender
rótulo. Violeta na página quer dizer "pule este"; violeta no tabuleiro quer dizer "pare neste".
E os dois azuis e os dois violetas nunca foram comparados entre si porque cada constante está
documentada com excelência **no seu próprio arquivo**.

Pior: na página, azul e violeta têm **1,20:1 de razão de contraste entre si**. Eles se separam
por matiz e quase nada mais, em linha de 2 px, sobre página impressa hachurada. Para quem tem
protanopia ou deuteranopia — ~8% dos homens — "ainda a fazer" e "não precisa" são o mesmo
retângulo.

---

## Os achados, por eixo

Cada linha aponta o item de spec que a resolve. Os `arquivo:linha` são do commit `3799f35`.

### A. Fundação visual — o tema, as cores, a tipografia

| # | achado | evidência | item |
|---|---|---|---|
| A1 | O tema é aplicado e nenhum widget pede estilo: 70 botões cinza de relevo levantado, sem primário, sem destrutivo | `TButton` = `#f0f0f0`/`raised` contra `primary.TButton` = `#0a58ca`/`#ffffff`, ambos no mesmo `Style` | **S-144** |
| A2 | 24 cores cravadas em 8 arquivos, sem módulo de paleta. Três verdes com três significados de "bom": `#00c07a` (salvo), `#2e7d32` (procedência), `#146c43` (o `success` do tema, nunca usado); dois cinzas auxiliares (`#555555`, `#666666`) | `board_render.py:35-49`, `pdf_panel.py:80-104`, `gallery_panel.py:285`, `games_dialog.py:81`, `result_panel.py:279`, `app_tkinter.py:366` | **S-145** |
| A3 | Duas cores reprovam em contraste, com número: `#00c07a` como **texto** sobre branco = **2,38:1** (mínimo AA: 4,5:1); coordenadas `#d8d8d8` sobre o fundo `#f2f2f2` do tabuleiro do Resultado = **1,27:1** — as letras a–h e os números 8–1 estão na tela e são invisíveis | `pdf_panel.py:798-802`, `board_render.py:49` contra `result_panel.py:269` | **S-146** |
| A4 | As superfícies de canvas não seguem o tema: PDF `#1c1c1c`, tabuleiro do Resultado `#f2f2f2`, tabuleiro da Análise `#262421`, tooltip `#ffffe0`. **O mesmo `InteractiveBoard` tem duas identidades visuais em duas abas vizinhas** — e metade dos 30 temas do `ttkbootstrap` é escura, com estas quatro superfícies imunes a ela | `pdf_panel.py:338`, `result_panel.py:269`, `board_widget.py:107`, `tooltip.py:69` | **S-147** |
| A5 | Nenhuma consciência de DPI (`SetProcessDpiAwareness` não é chamado): em monitor a 150% o Windows amplia o bitmap e a janela inteira fica borrada. E nenhum ícone: `iconphoto` nunca é chamado e o `.spec` do bundle traz `icon=None` — a barra de tarefas, o Alt-Tab e o `.exe` mostram a pena genérica do Tk | `app_tkinter.py:124-133`, `packaging/cvoff.spec:132` | **S-148** |
| A6 | Nenhuma escala tipográfica: Segoe UI 9 em tudo — título de grupo, rótulo, dado e status têm o mesmo peso. E a **FEN**, que é o dado central do produto, aparece em fonte proporcional, onde `l`, `1` e `I` têm larguras diferentes e casas não se alinham entre duas leituras | `result_panel.py:296`, `study_panel.py:121`, `dataset_panel.py:164` | **S-149** |

### B. Layout — o que a janela apaga quando encolhe

| # | achado | evidência | item |
|---|---|---|---|
| B1 | Sem `root.minsize()`: em 1100×760 a fila de salvar é cortada ao meio; em 940×620 somem 6 colunas do Dataset e o botão "Remover" | fotografado; `app_tkinter.py:127` define 1700×980 e nada define o piso | **S-150** |
| B2 | As barras não refluem, apenas cortam. O painel do PDF empilha **5 barras** (~200 px = 20% da altura) antes de a página começar, e nenhuma delas quebra em duas linhas quando falta largura | `pdf_panel.py:242-343` | **S-151** |
| B3 | 12 `wraplength` cravados de 220 a 780 px, num painel cuja largura real varia de 420 (o `minsize`) a ~1180 (divisor à direita). Nenhum deriva de `winfo_width`. O texto de procedência da Galeria é cortado **no meio da palavra** ("Whit", "Jam", "antiga") | `dataset_panel.py:184`, `review_panel.py:127-128`, `result_panel.py:278`, `study_panel.py:118`, `gallery_panel.py:285` | **S-152** |
| B4 | Os dois `Treeview` têm rolagem vertical e **nenhuma horizontal**. Na fila de revisão, a coluna "Motivo" — que é a razão de a fila existir — está truncada em **todas** as 129 linhas. E colunas numéricas com `anchor="w"`: 1623.8, 40, 1 e 0.082 alinhados à esquerda não se comparam por magnitude | `dataset_panel.py:161-169`, `review_panel.py:132-139` | **S-153** |
| B5 | A coluna "Headers do PGN" da Galeria não cabe ao lado do tabuleiro na posição padrão do divisor: `centro` toma o espaço com `expand=True` e a lateral é **cortada** — campos, botões e o texto verde de procedência | tabuleiro fixo em 420 px (`gallery_panel.py:58`) + lateral de ~290 px contra ~680 disponíveis; `gallery_panel.py:252` | **S-154** |
| B6 | As coordenadas do tabuleiro são desenhadas em `origin_y + size + 11` e a margem reservada é 28 (14 px por lado): as letras a–h são **cortadas na base** nas duas abas que mostram tabuleiro. E `size = max(min_size, min(...))` faz o tabuleiro **transbordar** o canvas em vez de encolher | `board_render.py:349-358` contra `board_widget.py:594`; `board_render.py:103` | **S-155** |
| B7 | `_set_initial_sashes` reposiciona o divisor em 42% a cada abertura, e o `AppState` guarda página, zoom e três interruptores — mas **não** guarda o tamanho da janela, a posição do divisor nem a aba aberta. Toda sessão começa desfazendo o arranjo da anterior | `app_tkinter.py:233,431-437`, `ui/state.py:48-72` | **S-156** |
| B8 | A página do PDF é encostada à esquerda do canvas: em 40% de zoom, ~45% da área de visualização é vazio `#1c1c1c`. Não há "ajustar à página", e o primeiro desenho não usa "ajustar à largura", que já existe | `pdf_panel.py:338`, `pdf_panel.py:412` | **S-157** |

### C. Cor com um significado só

| # | achado | evidência | item |
|---|---|---|---|
| C1 | Azul e violeta significam coisas diferentes na página e no tabuleiro, e os dois painéis ficam lado a lado | `pdf_panel.py:80-104` contra `board_render.py:39-47` | **S-158** |
| C2 | A cor é o **único** canal do estado da caixa: quatro estados, quatro matizes, nenhuma forma, traço ou letra redundante. Azul contra violeta = **1,20:1** | `pdf_panel.py:747-786` | **S-159** |
| C3 | Dois amarelos no tabuleiro, casa selecionada `#f7ec74` contra último lance `#cdd26a` = **1,32:1**, adjacentes com frequência | `board_render.py:37-38` | **S-160** |

### D. Navegação, arquitetura de informação e retorno ao usuário

| # | achado | evidência | item |
|---|---|---|---|
| D1 | **Não há barra de menus.** Nenhum `tk.Menu` no projeto. Os ~70 comandos são botões permanentemente visíveis, e não existe lugar para "Abrir recente", "Preferências", "Ajuda" ou a lista de atalhos | `grep -rn "tk.Menu" src/ app_tkinter.py` → vazio | **S-161** |
| D2 | As 6 abas misturam **dois níveis de navegação**: Configuração, Dataset e Galeria são do acervo; Resultado, Análise e Revisão são do diagrama que está aberto agora. E a janela abre na Configuração — a aba menos usada depois do primeiro dia | `app_tkinter.py:251-327` | **S-162** |
| D3 | `enable_traversal()` nunca é chamado: não há `Ctrl+Tab` entre as abas nem tecla de acesso. E as abas não dizem quanto trabalho carregam — 129 pendentes na Revisão, 3.936 linhas no Dataset, 1.480 diagramas na Galeria, nada disso aparece no rótulo | `app_tkinter.py:252` | **S-162** |
| D4 | A barra de status é um `ttk.Label` cru dentro do **painel esquerdo**, sem separador, sem relevo, sem altura fixa, e mostra o que aconteceu por último em qualquer painel: "Dataset carregado: 3936 amostras." fica na tela enquanto o usuário trabalha na Galeria. Quando a janela encolhe, ela sai da tela | `app_tkinter.py:329` | **S-163** |
| D5 | Três operações longas — exportar 402 páginas, varrer o livro, varrer a fila — informam **só por texto**. Há 3 `Progressbar` no projeto e nenhuma delas está nessas três. Contra isso, **76 chamadas de `messagebox`**: o retorno que devia ser ambiente é modal | `study_panel.py:163`, `training_dialog.py:180`; `grep -c messagebox` = 76 | **S-164** |
| D6 | 16 tooltips para ~70 controles. A `ui/tooltip.py` existe exatamente para explicar botão desabilitado (S-32) e cobre 3 deles | `grep -c "Tooltip("` = 16 | **S-165** |

### E. Cópia, vocabulário e formulário

| # | achado | evidência | item |
|---|---|---|---|
| E1 | Inglês dentro de uma interface em pt-BR: "Zoom board", "Virar board", "Heatmap de incerteza", "Corrigir Net", "Batch size", "Learning rate", "Headers do PGN", "Split", e **`pending` repetido em 129 linhas** da fila enquanto o filtro ao lado diz "Só pendentes" | `study_panel.py:88`, `result_panel.py:251,256`, `app_tkinter.py:357-358`, `review_panel.py` | **S-166** |
| E2 | Um conceito, dois nomes: "Varrer PDF" (Revisão) e "Varrer livro" (Galeria); "Lado a jogar" (Resultado) e "Vez" (Galeria); "Brancas/Pretas" e "brancas/pretas". O `ui/strings.py` foi criado na S-04 para exatamente isto e estes termos ficaram fora | `review_panel.py:114`, `gallery_panel.py:145`, `result_panel.py:304`, `gallery_panel.py:328` | **S-166** |
| E3 | `ttk.LabelFrame(self, text="PDF (direita)")` — um grupo cujo nome descreve a própria posição na tela. `->` no lugar de `→`. `<<`, `>>`, `\|<`, `>\|` como navegação | `pdf_panel.py:239,275`, `gallery_panel.py:179-182`, `study_panel.py:94-97` | **S-166** |
| E4 | O título da janela é "Chess Diagram OCR - Tkinter": nomeia o *toolkit* e não o produto, e não diz que livro nem que página estão abertos — o que é a única coisa que o usuário precisa ler ao voltar de outra janela | `app_tkinter.py:126` | **S-167** |
| E5 | Três caminhos de arquivo (`Modelo`, `CSV labels`, `Pasta samples`) são `Entry` de texto livre, **sem botão "Procurar…"** e sem verificação de existência, num programa que usa `filedialog` em cinco outros lugares. Um caractere errado só aparece como erro na hora do OCR | `app_tkinter.py:332-334,419-423` | **S-168** |
| E6 | `Learning rate` é um `Entry` ligado a um `DoubleVar`: uma letra digitada faz o `get()` levantar `TclError` na hora de treinar, não na hora de digitar. E a coluna de rótulos tem largura 16 em toda parte e **24** na linha de orientação, que por isso quebra a grade de alinhamento | `app_tkinter.py:358` (`_entry_row` com `DoubleVar`), `app_tkinter.py:340` contra `422` | **S-168** |
| E7 | Precisão falsa na fila de revisão: prioridade `1623.8` (uma casa decimal em número que ninguém compara nesse detalhe) e confiança `0.082` em vez de `8%`. E o Dataset mostra o dado cru na coluna "Lado": `w`, `b`, `—` | `review_panel.py:55-56`, `dataset_panel.py:42-43` | **S-169** |
| E8 | Ao abrir, a aba Resultado mostra **um tabuleiro completo na posição inicial** com a FEN vazia: parece dado onde não há dado nenhum. E o rótulo "Lance" é empacotado depois do campo com `side=RIGHT`, então aparece **à direita dele** — `[campo] Lance`, ao contrário da leitura | `result_panel.py:318-320`, `ui/editor_model.py` | **S-170** |
| E9 | "Remover" (apaga linha do `labels.csv`) tem exatamente a mesma aparência de "Abrir no editor". "Quarentena" também | `dataset_panel.py:179-182` | **S-170** |

---

## O sequenciamento, e a razão de cada degrau

Cinco fases. A ordem não é por tamanho do ganho — é por **dependência**: cada fase entrega o
vocabulário que a seguinte usa.

| fase | o que ela é | itens | por que ela vem aqui |
|---|---|---|---|
| **20** | A fundação visual | S-144 a S-149 | Todo item das fases seguintes escreve cor, peso ou fonte. Sem um módulo de tokens, as 24 cores cravadas viram 40. É a fase que faz o resto ser barato — e é a que muda mais a tela por linha escrita, porque o sistema de design já está pago e carregado. |
| **21** | A janela que não apaga controles | S-150 a S-157 | É a única fase que corrige **perda de função**, não de aparência: hoje um notebook de 1366×768 não tem botão de salvar. Vem depois da 20 só porque o refluxo de barra precisa dos estilos de botão para decidir o que colapsa primeiro. |
| **22** | Cor com um significado só | S-158 a S-160 | Precisa da paleta da 20 para existir sem cravar hex novo. Curta e de alto retorno: é o achado que o usuário sente sem saber nomear. |
| **23** | Navegação e retorno | S-161 a S-165 | O menu e a barra de status da janela reorganizam onde as coisas moram; fazer isso antes da 21 seria mover controles que ainda somem quando a janela encolhe. |
| **24** | Cópia, formulário e estados vazios | S-166 a S-170 | Independente das outras quatro e pode andar em paralelo por outra mão. Fica no fim porque é a única fase cujo erro não custa nada além de si mesmo. |

### O que fazer primeiro se houver só um dia

Nesta ordem, e cada um é medível sozinho:

1. **S-144** — os estilos semânticos nos botões. Uma tarde, e é a mudança que se vê da porta.
2. **S-150** — `root.minsize(1180, 800)` mais rolagem vertical nas abas. Uma hora, e devolve o
   botão de salvar a quem trabalha em notebook.
3. **S-146** — os dois contrastes reprovados. Duas constantes, e uma delas faz reaparecer as
   coordenadas que hoje estão desenhadas e invisíveis.
4. **S-155** — `margin=36`. Uma linha, e as letras a–h deixam de ser cortadas nas duas abas.

### A restrição técnica que decide como a Fase 20 é escrita

Foi medida nesta máquina, e ela contradiz a documentação da biblioteca para a versão anterior:

```
ttk.Button(parent, text="x", bootstyle="primary")   → TclError: unknown option "-bootstyle"
ttk.Button(parent, text="x", style="primary.TButton") → funciona
```

No `ttkbootstrap` **2.2.0** os widgets do `tkinter.ttk` **não** são mais remendados para aceitar
`bootstyle`; só as classes de `ttkbootstrap` aceitam. Então há dois caminhos, e o segundo é o
que a spec adota:

- trocar `ttk.Button` por `ttkbootstrap.Button` em 30 módulos — muda a classe de todo widget da
  janela, e quebra o contrato de degradação de `ui/theme.py:12-15`;
- passar `style="primary.TButton"` no `ttk.Button` que já existe.

O segundo preserva o contrato **exatamente**, e isto foi verificado: num `Tk` sem
`ttkbootstrap`, com o tema `vista`, `ttk.Button(style="primary.TButton")` **não levanta** — o Tk
desenha o botão padrão. Aparência continua não derrubando ferramenta, que é o que o módulo de
tema promete desde a S-53.
