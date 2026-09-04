# Especificação do acabamento — Fases 69 a 72 (S-441 a S-450)

Base: [ROADMAP_ACABAMENTO.md](ROADMAP_ACABAMENTO.md), que traz a medição das três peles, os sete
achados e o sequenciamento. A fundação que esta spec usa — tokens, tipografia, estilos, catálogo de
comandos e peles — é a das Fases 20 a 24 ([SPEC_UI.md](SPEC_UI.md)) e 32 a 35
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
> | S-235 a S-267, S-291 a S-293, S-521 | [SPEC_EDITOR.md](SPEC_EDITOR.md) |
> | S-268 a S-290 | [SPEC_ESTUDO.md](SPEC_ESTUDO.md) |
> | S-296 a S-323, S-325 a S-430, S-451, S-452 (menos S-324) | [SPEC_REVISAO.md](SPEC_REVISAO.md) |
> | S-431 a S-440 | [SPEC_REVISAO_EXTERNA.md](SPEC_REVISAO_EXTERNA.md) |
> | S-441 a S-450 | [SPEC_ACABAMENTO.md](SPEC_ACABAMENTO.md) |
> | S-507 a S-520 | [SPEC_ESTUDO_QT.md](SPEC_ESTUDO_QT.md) |
> | S-522 a S-526 | [SPEC_REVISAO_EXTERNA_2.md](SPEC_REVISAO_EXTERNA_2.md) |
> | S-527 a S-580 | [SPEC_SUITE.md](SPEC_SUITE.md) |

Cada item tem **Problema** (com arquivo:linha do estado atual), **Solução**, **Critério de aceite**
e **Testes**. Nome de módulo é sugestão; o que importa é a fronteira de responsabilidade.

**Quatro regras valem para toda esta spec.**

1. **Acabamento é da janela, não da pele.** Folga, peso, alinhamento e indicador chegam às três
   peles ao mesmo tempo. Um item que melhore uma pele só está mal escrito — é o defeito que o
   achado 2 do roadmap mede em `app_tkinter.py:1978`.
2. **A pele clássica não muda de *arranjo*.** Nenhum controle nasce, morre ou muda de lugar nela.
   Esta é a regra 1 da `SPEC_APARENCIA.md` relida pela S-443, e a parte que ela conserva é a que
   protegia contra três telas divergentes.
3. **Nenhum item desta spec troca rótulo de comando.** O vocabulário continua sendo o de
   `ui/strings.py` e `ui/comandos.py`, como a S-166 e a S-324 fixaram.
4. **Acabamento não derruba ferramenta.** A regra de degradação de `ui/theme.py:12-15` vale aqui
   com um dono a mais: folha de base que não aplicou é aviso no log, nunca janela que não abre.

---

# Fase 69 — a base que falta às três peles

## S-441 · A folha de base do `ttk`: os onze widgets que ninguém estiliza

### Problema

O projeto inteiro tem **cinco** `style.configure`, os cinco em `ui/theme.py:361-378`:

    style.configure(ESTILO_DE_TABELA_DE_DADOS, font=...)      # fonte de tabela
    style.configure(ESTILO_DE_TITULO, font=...)               # fonte de título
    style.configure("Treeview", rowheight=...)                # altura de linha
    style.configure(ESTILO_DE_ABAS_DISCRETO, borderwidth=0, tabmargins=(2, 6, 2, 0))
    style.configure(f"{ESTILO_DE_ABAS_DISCRETO}.Tab", borderwidth=0, padding=(14, 6))

Para `TButton`, `TCheckbutton`, `TEntry`, `TFrame`, `TLabelframe`, `TSpinbox`, `TCombobox`,
`TRadiobutton`, `TSeparator`, `TScale` e `TNotebook` o número é zero. Medido:

    grep -rc 'configure("TButton"' src/chess_diagram_ocr/ui/*.py app_tkinter.py   # 0

O resultado está na fotografia: a faixa de abas da pele clássica desenha o rótulo encostado na
borda dos dois lados, porque os dois únicos `configure` que dão folga a uma aba estão presos ao
estilo `Discreta.TNotebook`, que só a pele "Foco" recebe (`app_tkinter.py:1978`).

> **Correção de bancada, feita ao implementar.** A primeira redação deste item dizia que
> `padding TButton` resolve para `1 1`. **Está errado:** aquele número foi lido com o tema `vista`,
> que é o que responde antes de `apply_theme` rodar. Sob `bootstrap-light` e `bootstrap-dark` o
> `ttkbootstrap` já dá `10 4` ao `TButton`, `5` ao `TEntry`, `10 4 6 4` ao `TMenubutton` e
> `5 6 7 4` ao `TCombobox` — e deixa **vazios** `TNotebook.Tab`, `TCheckbutton`, `TRadiobutton`,
> `TSpinbox` e `TLabelframe`, que são exatamente os que a fotografia mostrou quebrados. A folha
> cobre os vazios e não encosta no resto; o porquê de cada exclusão está na tabela abaixo.

### Solução

Um módulo `ui/folha.py` com **uma** função, `aplicar(style, *, base, densidade)`, chamada de dentro
de `theme.registrar_estilos` — depois do tema e antes de `repintar()`, pela mesma razão que
`apply_theme` registra estilo depois de aplicar tema (`ui/theme.py:163-165`): estilo declarado
antes é sobrescrito.

> **`folha` e não `base`.** `base` é o nome do parâmetro de tamanho de fonte que atravessa
> `tipografia`, `fita` e `theme`; `from . import base` ficaria sombreado dentro de toda função que
> o recebe — inclusive `fita.altura_da_fita`, que é justamente quem consultaria o módulo.

Ela configura **cinco** classes, e **todo número que ela usa sai de `ui/tipografia.py`** — nenhum
literal novo entra no projeto por este item:

| widget | o que a folha define | de onde sai o número |
|---|---|---|
| `TNotebook.Tab` | `padding` | `(FOLGA_DE_MOLDURA, FOLGA_DE_LINHA)` — resolve para o `(14, 6)` da S-226 |
| `TCheckbutton`, `TRadiobutton` | `padding` | `(FOLGA_MINIMA, FOLGA_MINIMA)` |
| `TSpinbox` | `padding` | `(FOLGA_DE_LINHA, FOLGA_MINIMA)` — o vizinho dele é um `TEntry` com 5 |
| `TLabelframe` | `padding` | `(FOLGA, FOLGA_DE_LINHA)` |

E **quatro exclusões**, cada uma com o motivo medido — a ausência é decisão, e o teste
`test_a_folha_nao_encosta_em_quem_o_tema_ja_resolve` a cobra:

| fora da folha | por quê |
|---|---|
| `TButton`, `TMenubutton`, `TEntry`, `TCombobox` | o tema já os folga; escrever por cima **encolhe** o botão de fita de 58 para 50 px |
| `TButton` (segundo motivo) | `(10, 6)` custa +51 px nas duas barras do PDF e as quebra em mais linhas — arranjo, e a regra 2 proíbe |
| `TFrame` | 117 na janela, aninhados até 8 níveis: `8 × 10 × 2 = 160 px` de cada eixo no ramo mais fundo |
| `TSeparator`, `TScale` | não desenham `padding`; o vão deles é com o vizinho, e isso é a S-447 |

O `padding=(14, 6)` que a S-226 já mediu para a faixa discreta é exatamente
`(FOLGA_DE_MOLDURA, FOLGA_DE_LINHA)` na densidade confortável — a folha não inventa a folga da aba,
ela **generaliza a que já foi aprovada** e a entrega às três peles. `ESTILO_DE_ABAS_DISCRETO`
continua existindo e continua sendo o da "Foco": o que ele mantém de próprio é `borderwidth=0`,
que é peso, não folga.

### Critério de aceite

- `folha.aplicar` é chamada uma vez por `registrar_estilos`, e é o único lugar do projeto que
  configura essas classes.
- Nenhum literal de pixel no módulo: todo valor vem de `tipografia.folgas(...)`.
- As três peles recebem a mesma folha. `Discreta.TNotebook` continua diferindo **só** em
  `borderwidth`.
- A densidade compacta (S-232) encolhe a folha inteira pelo fator que `FATOR_DE_FOLGA` já declara.
- Fotografada em 1300×800, a faixa de abas da pele clássica passa a ter folga horizontal ≥ 12 px de
  cada lado do rótulo — hoje é 0.

### Testes

- `tests/test_ui_folha.py` (novo): a folha resolve para as cinco classes; todo valor confere com
  `tipografia.folgas`; papel de folga desconhecido levanta, como `estilo_de_botao` já faz.
- `tests/test_ui_folha.py`: a folha encolhe na compacta; a faixa discreta herda a folga em vez de
  ter a sua; e um `Style` que recusa uma opção registra aviso e segue, com o `padding` das outras
  classes de pé (regra 4). **As três moram aqui e não nos vizinhos que a spec citava**: as três
  afirmam coisas sobre a folha, e a folha tem arquivo.

---

## S-442 · O indicador que encosta no rótulo, e o vão que ele nunca teve

### Problema

Em `☒Marcar diagramas`, `☒Roda vira a página`, `☒Mapa de incerteza` e `☐Treinar do zero` o glifo do
indicador **toca a primeira letra**. Medido:

    style.lookup("TCheckbutton", "indicatormargin")   # ''  (vazio)
    style.lookup("TCheckbutton", "padding")           # ('2',)

Quatro ocorrências aparecem em duas fotografias de aba. Não é caso de borda: é o padrão do widget
em toda a janela, e é o tipo de detalhe que faz a janela parecer não-terminada mesmo quando tudo
funciona.

### Solução

Na folha de base da S-441, `indicatormargin` para `TCheckbutton` e `TRadiobutton` com o vão à
direita do indicador vindo de `FOLGA_DE_LINHA`, e zero nos outros três lados — o vão é entre
indicador e rótulo, não em volta do conjunto, que já é `padding`.

O item é separado da S-441 e não uma linha dela porque `indicatormargin` é a única opção desta fase
que **não** existe em todos os temas `ttk`: no `classic` ela não é lida. Isso a torna o caso de
teste da regra 4, e um item com critério próprio.

### Critério de aceite

- O vão entre indicador e rótulo é ≥ 4 px na densidade confortável, nas três peles. **Medido:**
  `0 0 6 0` na confortável e `0 0 4 0` na compacta, nos dois temas.
- Num tema que não conheça `indicatormargin`, a chamada registra aviso e a janela abre com o
  indicador de hoje — e o `padding` das outras classes não vai junto.
- O vão encolhe na densidade compacta e nunca chega a zero — o piso é o mesmo argumento de
  `FOLGA_MINIMA` (`ui/tipografia.py:229-234`): dois vizinhos colados viram um controle só para o
  olho.

### Testes

- `tests/test_ui_base.py`: o vão sai de `FOLGA_DE_LINHA`; o piso na compacta é ≥ 1.
- `tests/test_ui_degradacao.py`: `Style` que levanta em `indicatormargin` não impede a montagem.

---

## S-443 · A regra 1 relida: a clássica não muda de *arranjo*

### Problema

`SPEC_APARENCIA.md:30` diz *"A pele clássica é o padrão e não muda. Quem nunca abrir
`Ver ▸ Aparência` tem, pixel a pixel, a janela de hoje."* E `ROADMAP_APARENCIA.md:345` recusa
*"Redesenhar as seis abas por dentro. Fora de escopo."*

As duas frases estavam certas nas Fases 32 a 35. Juntas, hoje, elas fecham a única porta pela qual a
janela padrão poderia melhorar: **a pele que 100% dos usuários vê é a proibida de mudar, e o
interior que eles olham o dia inteiro é o fora de escopo.** A S-441 e a S-442 violam a regra 1 como
ela está escrita — e essa é a única razão pela qual elas não foram feitas antes.

### Solução

A regra passa a separar dois eixos que "não muda" fundia:

> **Arranjo** — quais controles existem, onde ficam, em que ordem. Congelado na clássica, como
> estava. Nenhum controle nasce, morre ou muda de lugar.
>
> **Acabamento** — folga, peso, alinhamento, indicador, superfície. **Não é da pele.** É da janela,
> e chega às três ao mesmo tempo.

E o que substitui a proteção que a regra 1 dava: um teste que monta a janela nas três peles e cobra
que o acabamento seja **o mesmo nas três**, do mesmo jeito que a S-233 cobra por inventário que
nenhuma pele esconde comando. A S-233 protege o *alcance*; esta protege o *acabamento*.

Este item também **atualiza os dois documentos**: `SPEC_APARENCIA.md` ganha a releitura da regra 1
com apontador para cá, e `ROADMAP_APARENCIA.md` ganha, na lista do que foi recusado, a nota de que
a recusa do interior valia para aquelas fases e foi reaberta por esta.

### Critério de aceite

- O arranjo da pele clássica é o de hoje: mesmo conjunto de controles, mesmos pais, mesma ordem de
  empacotamento. Verificável por inventário, não por pixel.
- `padding` de `TButton`, `TNotebook.Tab`, `TCheckbutton`, `TEntry`, `TSpinbox` e `TLabelframe` é
  **igual** nas três peles **na mesma densidade**. A ressalva não é conveniência: a pele "Fita"
  sugere compacta, onde a folha é menor de propósito, e exigir igualdade entre densidades cobraria
  o contrário da S-232. Pele não muda acabamento; densidade muda, e é para isso que ela existe.
- `SPEC_APARENCIA.md` e `ROADMAP_APARENCIA.md` apontam para este item onde a regra antiga está
  escrita. Documento que contradiz documento é o defeito que a S-218 já registrou em outra forma.

### Testes

- `tests/test_ui_acabamento.py` (novo): aplica as três peles e compara o `padding` resolvido das
  seis classes, nas duas densidades; qualquer diferença entre peles reprova. Ele inclui `TButton` e
  `TEntry`, que **não** estão na folha — o acabamento tem de ser o mesmo nas três peles inclusive
  onde quem o decide é o tema.
- O inventário de arranjo da clássica **já existe** e não foi duplicado: é o de
  `tests/test_ui_alcance.py` (S-233), que cobra que toda pele alcança o catálogo inteiro.
  **Desde o corte do Tk (S-506) esse arquivo não existe** — ele perguntava sobre as três peles do
  toolkit. Quem cobra a conta hoje é `test_ui_comandos.test_todo_comando_do_catalogo_alcanca_alguem`
  (catálogo → menu ou exceção declarada) mais
  `test_qt_janela.test_todo_comando_do_catalogo_tem_dono_nesta_janela` (a declaração tem dono).
- `tests/test_disciplina_da_suite.py`: a tabela "onde mora a spec de cada item" cobre S-441 a S-450
  nos dois documentos novos.

---

# Fase 70 — a hierarquia que existe e não pinta

## S-444 · `primary` e `danger` que pintam no tema claro

### Problema

**Este é o achado 1 do roadmap, e ele é de correção, não de gosto.** Medido numa janela de três
botões, um por papel, fotografada e amostrada no pixel:

| tema | quem o usa | neutro | primário | destrutivo |
|---|---|---|---|---|
| `bootstrap-dark` | pele "Foco" | `(46,50,54)` | `(61,139,253)` | `(227,93,106)` |
| `bootstrap-light` | **clássica (padrão)** e "Fita" | `(240,240,240)` | `(240,240,240)` | `(240,240,240)` |

No tema claro os três papéis pintam o mesmo cinza. O `style=` está certo e resolvido; o
`bootstrap-light` da 2.2.0 simplesmente não redefine a face de `primary.TButton` nem a de
`danger.TButton`.

A consequência: na pele padrão, **"Remover" (`ui/dataset_panel.py:190`) — que apaga linha do
`labels.csv`, isto é, trabalho humano — é o mesmo cinza de todo botão da janela.** É a S-76 outra
vez: 1.405 diagramas sobrescritos por um clique. A S-144 consertou a API (`bootstyle=` → `style=`)
e o resultado continuou de pé por baixo.

### Solução

`style.configure` + `style.map` para `primary.TButton` e `danger.TButton`, com as cores saindo de
`ui/tokens.py` e resolvidas por `theme.cor_atual` — o mesmo caminho que a S-220 usou para o ícone, e
pela mesma razão: cor que sai do token é correta nas três peles por construção.

> **Em `ui/theme.py`, e não na folha da S-441.** A primeira redação dizia "na folha de base". A
> folha importa `pele` e `tipografia` e nada mais — é o que a mantém sobre *folga*. Para pintar ela
> precisaria de `tokens` e de `theme.cor_atual`, e **`theme` importa `folha`**: seria um ciclo.
> `theme.py` já é a casa dos estilos nomeados (`Dado.Treeview`, `Discreta.TNotebook`), e
> `primary.TButton` é um deles.

Os dois papéis pedem token novo, porque nenhum papel de `tokens.PAPEIS` significa "ênfase de
controle". Entram **três**: a face do primário, a do destrutivo, e **uma** letra para as duas. O
destrutivo reaproveita a matiz de `PROBLEMA`, que já é o vermelho da janela, sem reaproveitar o
**valor** — a S-224 mostrou que contorno de casa e face de botão pedem valores diferentes da mesma
matiz, e é literalmente a mesma armadilha que separou `PROBLEMA` de `PROBLEMA_TEXTO`.

> **Três e não quatro, e quem decidiu foi a regra da paleta.** Duas letras brancas seriam dois
> papéis com o mesmo hexadecimal, e `test_dois_papeis_de_significado_diferente_nao_compartilham_hex`
> proíbe isso com `COINCIDEM_DE_PROPOSITO` **vazia** — cujo docstring desaconselha, com todas as
> letras, "inventar uma diferença só para separar os nomes". A saída já existia no mesmo arquivo:
> `TEXTO_SOBRE_MARCACAO` é **um** papel para "a letra que vai por cima". `TEXTO_SOBRE_ENFASE` é o
> irmão dele.

**As duas paletas são pintadas, e a spec estava errada ao poupar a escura.** A primeira redação
dizia que sob `bootstrap-dark` os dois papéis "já pintam, e pintam bem". Medido no pixel: `#3d8bfd`
com letra branca dá **3,33:1** e `#e35d6a` dá **3,48:1** — os dois abaixo do piso `AA_TEXTO` que o
critério de aceite logo abaixo exige nas três peles. As duas metades do item se contradiziam.

**E a face escura clareia em vez de escurecer.** `#b02a37` sobre o botão neutro `#2e3236` dá
**1,99:1**: vermelho escuro em cima de cinza escuro não é ênfase, é um botão que some. As faces
clareiam, a letra escurece, e o valor escuro sai do claro **clareado em HSL com matiz e saturação
intactas** — a mesma receita dos cinco da S-224, e o que faz o desvio de matiz ser de 0,03°.

### Critério de aceite

- Nas três peles, a face do primário e a do destrutivo diferem da do neutro. Verificado por
  amostragem de pixel num botão montado, não por `style.lookup` — `lookup` devolveu `#f0f0f0` para
  os três papéis no tema claro **e no escuro**, onde a fotografia mostra azul e vermelho. O
  `lookup` não é testemunha nesta questão; o pixel é.
- O par texto-sobre-face de cada papel cumpre o piso `tokens.AA_TEXTO` (4,5) nas três peles.
- Os **três** tokens novos entram em `PAPEIS`, com `RESERVA` e entrada em `NO_CROMO_ESCURO`, como
  todo papel desde a S-158.
- A matiz de cada face sobrevive à troca de pele dentro dos 2° que
  `test_a_matiz_do_papel_sobrevive_a_troca_de_pele` já cobrava. **Medido: 0,21° no primário e 0,03°
  no destrutivo.** A primeira escolha de face escura, tirada a olho de uma tabela de candidatos,
  dava 3,19° e reprovou — é a regra da S-158 pegando o desvio antes de ele virar dois significados
  com um nome.
- Cada face se separa do botão neutro por pelo menos 3,0:1, nas duas paletas. É o critério que
  reprova o vermelho escuro sobre cromo escuro.
- **O estado `disabled` sai do tema, e não dos tokens.** "Limpar os headers" nasce desabilitado, e
  a primeira versão pintava o desabilitado com `SUPERFICIE_PADRAO` e `TEXTO_SECUNDARIO` — letra
  `#555555` contra os `#c8cccf` que o tema dá a todo botão desligado, o que fazia o destrutivo
  desabilitado parecer **mais aceso** que o neutro desabilitado ao lado. Desabilitado é
  desabilitado: `style.lookup("TButton", opção, ["disabled"])`, com os tokens de reserva para o
  tema que não responder.

### Testes

- `tests/test_ui_estilos.py`: os três papéis resolvem para faces distintas nas três peles.
- `tests/test_ui_semantica_cor.py`: contraste AA dos quatro tokens novos, uma vez por pele — é a
  varredura que a S-224 já roda por pele registrada.
- `tests/test_ui_tokens.py`: os quatro papéis novos têm reserva e valor de cromo escuro.

---

## S-445 · Os 73 botões que não pedem papel, e o destrutivo que a Galeria esconde

### Problema

Dos **103** sítios de `ttk.Button` em `ui/` e `app_tkinter.py`, **30 carregam papel e 73 não**
(71%). A distribuição não é uniforme, e é ela que aponta o trabalho:

| arquivo | botões | com papel | sem papel |
|---|---|---|---|
| `gallery_panel.py` | 15 | **0** | 15 |
| `result_panel.py` | 11 | 2 | 9 |
| `study_panel.py` | 10 | 1 | 9 |
| `review_panel.py` | 9 | 1 | 8 |
| `dataset_panel.py` | 11 | 6 | 5 |
| `database_choice.py` | 5 | 0 | 5 |
| `pdf_panel.py` | 14 | 14 | **0** |

`pdf_panel.py` já está inteiro — ele passou pela S-324 — e é a prova de que o custo por botão é
baixo. A Galeria é o oposto: **15 botões, nenhum papel, e um deles é "Limpar os headers"**
(`ui/gallery_panel.py:428`), que `ui/estilos.py:38` cita **pelo nome** como exemplo canônico de
`DESTRUTIVO`. O módulo nomeia o botão; o painel que o desenha não o consulta.

### Solução

Percorrer os 73 e declarar o papel de cada um. A maioria é `NEUTRO` e fica escrito como `NEUTRO` —
o valor não é o `style=""` que já sai de lá, é a declaração ter sido feita e passar a ser cobrável.

Os dois que mudam de face:

- **`DESTRUTIVO`**: "Limpar os headers" (`gallery_panel.py:428`), e o que a varredura achar com o
  mesmo critério — apaga trabalho humano, não pede confirmação, não tem desfazer.
- **`PRIMARIO`**: um por barra, pelo critério de `ui/estilos.py:31-36` — *a ação que o atalho de
  teclado também faz*.

Onde o comando já está no catálogo, o papel vem de `comandos.estilo(acao)` e não de um literal:
é o caminho que `pdf_panel.py` usa nos seus catorze, e ele mantém a declaração num lugar só.

### Critério de aceite

- "Limpar os headers" é `DESTRUTIVO` e pinta como tal nas três peles. ✅
- Todo sítio que já lê o **rótulo** do catálogo passa a ler dele o **papel**. ✅ — cinco:
  `limpar_tabuleiro`, os dois botões de histórico, `achar` e `substituir_todos`.
- Quem declara `DESTRUTIVO` está numa lista com motivo assinado, e isenção órfã reprova. ✅
- Nenhum rótulo muda (regra 3). ✅ · Nenhum botão muda de lugar (regra 2). ✅
- Todo `ttk.Button` de `ui/` e `app_tkinter.py` passa `style=`. **99 de 99.** ✅

> **Os números do problema estavam errados, e o instrumento era o culpado.** "30 de 103, 73 sem
> papel" veio de uma regex que olhava nove linhas à frente atrás de `style=` — e casava com o
> `style=` do botão **seguinte**. Ela também contava como sítio os exemplos dentro do docstring de
> `ui/estilos.py`, que não são código. Pelo `ast`: **30 de 99, 69 sem papel**. Hoje, 99 de 99.
>
> **E a varredura cobrou caro por uma distração do `ast`.** `col_offset` e `end_col_offset` contam
> **bytes UTF-8**, não caracteres; usados como índice de `str`, derrapam um caractere por byte
> extra, e toda linha com acento tem pelo menos um. `"Procurar…"` tem três bytes num caractere, e
> o `).pack(` seguinte virou `)ack(`. Foram **dez** erros de sintaxe, todos reparados — e a
> conferência não foi o olho: **todos os literais de texto de todos os arquivos varridos foram
> comparados com os de `HEAD`**, e a única diferença é a intencional.
>
> A varredura rendeu o que se esperava dela: foi assim que "Copiar headers para todos" apareceu
> sem papel. Ele ficou `NEUTRO` pelo critério de três partes do próprio item — apaga trabalho
> humano ✔, não pergunta ✔, **não desfaz ✘**: tem "Desfazer a cópia" no botão logo abaixo.

### Testes

- `tests/test_ui_estilos.py`: `DECLARAM_DESTRUTIVO` lista quem pode declarar o papel e por quê, e
  um segundo teste reprova entrada órfã. **A lista anterior era
  `("dataset_panel.py", "estilos.py", "comandos.py")` e o teste passava congelando o defeito**: ele
  afirmava que a Galeria não tem destrutivo, o que era verdade sobre o código e falso sobre a
  intenção — `ui/estilos.py:47` cita o botão dela pelo nome.
- `tests/test_ui_enfase.py` (novo): os três papéis pintam faces distintas nas duas paletas, e a face
  pintada é a que o token declara. **Por pixel de widget montado, e não por `lookup`.**

---

## S-446 · Um primário por barra: a regra que já existe, cobrada em todas as barras

### Problema

`ui/estilos.py:31-36` fixa a regra — *"uma por barra de ações, nunca duas"* — e
`ui/comandos.py:900-912` já a cobra **por grupo do catálogo**. Nenhuma das duas alcança uma barra
montada à mão dentro de um painel, que é onde a S-445 vai criar primário novo. Duas ênfases numa
barra é o mesmo que nenhuma, e o teste de grupo não vê isso acontecer.

### Solução

Estender a cobrança do catálogo às barras montadas: uma função pura que recebe a lista de papéis de
uma barra e reprova mais de um `PRIMARIO`. Onde a barra vem do catálogo, a cobrança já existe e não
é refeita — este item é a mesma regra chegando ao resto.

### Critério de aceite

- Nenhuma barra de ações da janela tem dois `PRIMARIO`.
- Uma barra sem primário é **aceita**: nem toda fileira tem uma ação que o teclado também faz, e
  inventar uma para cumprir cota é o defeito que a regra existe para evitar.
- A função é pura e não toca widget, como `estilo_de_botao`.

### Testes

- `tests/test_ui_estilos.py`: duas ênfases reprovam; zero passa; o caso de uma passa.
- `tests/test_ui_comandos.py`: a cobrança por grupo continua valendo, sem duplicar a nova.

---

# Fase 71 — o espaço como dado

## S-447 · Os 154 literais de espaço recolhidos à escala de folga

### Problema

`ui/tipografia.py:220-252` declara quatro papéis de espaço — `FOLGA_DE_MOLDURA` 14, `FOLGA` 10,
`FOLGA_DE_LINHA` 6, `FOLGA_MINIMA` 2 — com fator por densidade, e diz por escrito que *"são os
números que já estão na janela, e não uma escala nova"*. Medida a adoção:

    tipografia.folga(s)( fora de tipografia.py : 4   (fita.py x2, app_tkinter.py x2)
    pad[xy]=<inteiro>                          : 123
    padding=<inteiro>                          : 31

**Quatro chamadas, 154 literais** — e as quatro estão todas no *cromo*. Dentro dos painéis a escala
não é usada uma vez. Os valores literais são 1, 2, 4, 6, 8, 10, 12 e 14: oito degraus onde a escala
tem quatro, com 6 (35×) e 8 (32×) disputando o mesmo papel.

O custo não é de gosto. **A densidade compacta da S-232 encolhe o cromo e não encosta no interior**,
porque o interior não lê a escala — e a densidade compacta existe para caber num 1366×768, que é
exatamente onde o interior aperta.

### Solução

Recolher os 154 à escala, um a um. O mapa é direto e sai da própria declaração de `FOLGAS`:

| literal | papel | observação |
|---|---|---|
| 14, 12 | `FOLGA_DE_MOLDURA` | moldura interna de diálogo |
| 10, 8 | `FOLGA` | vão contra a borda |
| 6, 4 | `FOLGA_DE_LINHA` | de uma linha para a seguinte |
| 2, 1 | `FOLGA_MINIMA` | entre vizinhos do mesmo grupo |

**O módulo é `ui/espaco.py`, e ele existe por causa da assinatura.** `tipografia.folga` é pura e
pede `base` e `densidade` em toda chamada — é o que permite afirmar a escala sem abrir janela. Num
`pack` isso vira uma linha de 100 caracteres para dizer `padx=6`, e obriga o painel a saber de
densidade, que não é assunto dele. Aqui a pergunta é `padx=espaco.linha()`, e quem fixa os dois é
`theme.registrar_estilos` — a mesma função que aplica a folha da S-441, e pela mesma razão: é a
única que conhece fonte **e** densidade sem que ninguém as passe adiante.

Os pares (8→`FOLGA`, 4→`FOLGA_DE_LINHA`) são os que mudam pixel: 8 vira 10 e 4 vira 6 na
confortável. **É mudança de acabamento, não de arranjo** (regra 2), e é o preço de ter quatro
degraus em vez de oito.

Onde um literal não couber em nenhum papel, o item **não** inventa papel: ele registra o sítio na
spec e o deixa literal, com comentário. Papel novo de espaço é decisão, e decisão tomada de dentro
de uma varredura de 154 sítios é decisão tomada com pressa.

### Critério de aceite

- Zero `padx=`/`pady=`/`padding=` com inteiro literal em `ui/` e `app_tkinter.py`, salvo os sítios
  registrados como exceção. ✅ — **273 convertidos, 3 exceções**, cada uma com o motivo no próprio
  sítio e uma entrada em `test_ui_espaco.SemLiteralTests.EXCECOES`.
- Nenhum controle muda de lugar (regra 2): o que muda é quanto de vazio há em volta dele. ✅
- O espaço do interior deriva da fonte do sistema. ✅
- ~~A densidade compacta encolhe o interior dos sete painéis, e não só o cromo.~~ **Inalcançável
  como escrito**, e o motivo é estrutural.

> **São 285 literais e não 154.** O `grep` que dimensionou o item procurava `padx=<inteiro>`; a
> janela também usa `padx=(6, 0)` — o par que dá espaço de um lado só —, e são **131** deles.
>
> **A conversão é por `tokenize`, e não por regex de linha.** `ui/folha.py` e `ui/tipografia.py`
> **documentam** `padx=10` e `padding=(6, 2)` em docstring: uma regex cega converteria prosa.
>
> **Três literais não couberam em papel nenhum e continuam literais**, como este item já mandava:
> a calha de 18 px entre tecla e descrição na legenda (separação de coluna de tabela); os 3 px do
> rodapé, entre `FOLGA_MINIMA` e `FOLGA_DE_LINHA` porque a barra é fina de propósito; e o recuo de
> 22 px que alinha um rótulo sob o **texto** de um `Checkbutton`, e portanto depende da largura do
> indicador e não da escala.
>
> **E a densidade não alcança o interior na troca em execução.** `padx`/`pady` são opções de
> `pack`, fixadas quando o widget é empacotado, e `app_tkinter.remontar_cromo` — que é o que a
> troca chama — diz no próprio docstring que *"refaz o cromo **sem tocar o conteúdo**"*. Os sete
> painéis não são remontados. A densidade escolhida alcança o interior **na abertura seguinte**,
> porque é gravada no estado; entregar o "em execução" pediria remontar os painéis, que é outro
> item e não este.

### Testes

- `tests/test_ui_tipografia.py`: a varredura de fonte que cobra a ausência de literal, com a lista
  de exceções declarada como dado — e não como número no teste.
- `tests/test_ui_densidade.py`: a compacta reduz a altura montada de um painel do interior, e não
  só a do cromo. É o número que prova o item.

---

## S-448 · A grade de formulário: rótulo que não corta, campo dimensionado pelo dado

### Problema

Na aba Configuração, fotografada em 1300×800:

- **"Taxa de aprendizado" é desenhado como `Taxa de aprendizad`**, cortado no meio do glifo. O
  rótulo não cabe na coluna e o Tk corta em vez de a coluna ceder.
- **O campo mais largo do painel guarda o valor mais curto.** "Taxa de aprendizado" (`0.001`) tem
  ≈590 px; "Épocas" (`8`) e "Tamanho do lote" (`128`) têm ≈100. A largura não diz nada sobre o dado.
- **Três colunas de conteúdo em oito linhas.** Os campos começam em x≈128, x≈135 e x≈141.
- **Fontes de entrada misturadas.** `0.001` é desenhado em monoespaçada e `8` e `128` em sans, para
  o mesmo tipo de dado. A monoespaçada é a de `tipografia.DADO`, e ela está certa para tabela — não
  para um campo de número solto ao lado de outros dois que não a usam.

### Solução

Um ajudante de formulário em `ui/campos.py` — que já é o módulo dos campos — montando linha de
rótulo e controle numa grade de duas colunas, com:

- **coluna de rótulo dimensionada pelo mais largo do formulário**, medida pelo `linespace` da fonte
  em uso, como a S-228 já faz para o orçamento de altura da fita: conta pura sobre a fonte, nada de
  `winfo_width` no critério;
- **largura de campo por classe de dado** — caminho, número, texto livre — e não por sítio;
- **fonte por classe de dado**: número curto usa a fonte de corpo, como seus vizinhos; a
  monoespaçada fica onde `tipografia.DADO` já a justifica.

### Critério de aceite

- Nenhum rótulo de formulário é cortado. ✅ — a coluna sai do mais longo dos dez
  (`strings.ROTULOS_DA_CONFIGURACAO`, hoje 22 caracteres), e não de um número escolhido.
- Todos os campos de um formulário começam na mesma coluna. ✅
- Dois campos da mesma classe têm a mesma largura, e a largura cresce com a classe:
  número < texto < caminho. ✅ — `campos.LARGURA_DE_CAMPO`, com `0` querendo dizer "ocupa a sobra".
- Números do mesmo formulário usam a mesma fonte. ✅ — o campo de número deixou a monoespaçada
  `DADO` e usa a de corpo, que é a dos `ttk.Spinbox` ao lado.

> **Eram três medidas do mesmo formulário, e não uma.** O rótulo cortado era
> `largura_do_rotulo=16` contra "Taxa de aprendizado", de 19 caracteres. Mas ao lado dele havia um
> `24` cravado no rótulo da orientação e, no `app_tkinter`, um `_spin_row` que era uma **segunda
> implementação** da mesma linha de formulário, com largura própria — o defeito que a S-153 já
> mediu nas duas tabelas: duas cópias erram a mesma coisa em momentos diferentes. O `_spin_row`
> virou `campos.linha_de_giro`, e as três medidas viraram uma.
>
> **E o campo mais largo guardava o valor mais curto.** `linha_de_numero` pedia `expand=True` e
> comia toda a sobra da linha: ≈590 px para `0.001`, ao lado de "Épocas" (`8`) com ≈100. Largura é
> a primeira dica que um formulário dá sobre o dado que espera, e ali ela dizia o contrário.

### Testes

- `tests/test_ui_campos.py`, `GradeDeFormularioTests`: a coluna cabe o rótulo mais longo; o caso
  que abriu o item (19 caracteres contra 16) é nomeado; a largura cresce com a classe; e **todo
  rótulo montado no formulário passa por `ROTULOS_DA_CONFIGURACAO`** — um que entrasse por fora
  voltaria a ser cortado sem ninguém notar.
- A conta é em **caracteres** e não em pixel: `ttk.Label(width=N)` já reserva N larguras médias de
  caractere, e medir `linespace` aqui seria trocar uma unidade exata por uma aproximada.

---

# Fase 72 — as superfícies do documento

## S-449 · O tabuleiro que não flutua num slab quase-preto

### Problema

Amostrado na fotografia da pele clássica, na linha `y=340` do canvas do tabuleiro:

    691 px de canvas, 429 deles em (49,46,43) = 62%

O tabuleiro mede 261 px e está centrado num vazio quase-preto que ocupa quase dois terços da
largura, dentro de um painel de fundo `(255,255,255)`. **É a aresta de maior contraste da janela, e
ela está em volta de espaço que não carrega informação nenhuma.**

> **Este parágrafo estava errado, e a implementação o corrigiu.** Ele dizia que o valor "foi
> escolhido no canvas e nunca passou por `cor()`". Passou: era `SUPERFICIE_TABULEIRO`, a esteira,
> escolhida escura pela S-147 porque é ela que dá 11,03:1 às coordenadas — que são desenhadas
> **em cima dela**. O defeito não era falta de papel; era a esteira **não ter fim**. Ela era o
> fundo do canvas, e o canvas enche o painel: tudo o que não fosse tabuleiro virava esteira.

### Solução

Um papel novo, `VAZIO_DE_CANVAS`, em `tokens.py`, com entrada em `RESERVA` e em `NO_CROMO_ESCURO`
como todo papel desde a S-158. Na pele clara ele é uma superfície vizinha do fundo do painel — o
vazio deixa de ser uma moldura preta e passa a ser continuação da janela; na "Foco" ele é o cromo
escuro, que é o que a fotografia dela já mostra funcionando por acidente.

O papel entra em `SUPERFICIES` e **não** em `SUPERFICIES_DE_DOCUMENTO`: vazio não é documento, e a
regra da S-224 — *documento mantém contraste medido, cromo segue a pele* — precisa continuar
valendo para página e tabuleiro sem passar a valer para o vazio em volta deles.

### Critério de aceite

- O vazio do canvas resolve por `cor()` nas três peles; zero hexadecimal cru no sítio. ✅
- O contraste entre o vazio e o fundo do painel é **baixo** em toda paleta — critério invertido, e
  de propósito. ✅ **Medido: 1,03 na clara**, 1,21 e 1,04 nas escuras.
- `SUPERFICIES_DE_DOCUMENTO` não muda. ✅
- **Medido: a linha `y=340` do canvas foi de 62% de quase-preto para 4%.**
- ~~A borda do tabuleiro continua distinguível do vazio pelo piso `AA_GRAFICO`.~~ **Reescrito: como
  estava, reprovava nas peles escuras.**

> **O que separa o tabuleiro do vazio troca de dono com a paleta**, e o critério tem de dizer isso.
> Na clara são a esteira (11,50) e a moldura (14,32) — a casa clara sozinha daria **1,17**. Nas
> escuras esteira e moldura se fundem no vazio (1,03 a 1,19) e quem separa é o **tabuleiro** (12,17
> a 13,55); e está certo, porque ali o cromo inteiro é escuro e não há slab a desfazer. O critério
> é: **pelo menos um dos três** — esteira, moldura ou casa clara — passa `AA_GRAFICO` contra o
> vazio, em toda paleta.
>
> **E uma consequência que o item não previa:** `_cor_de_coordenada` resolvia contra
> `canvas.cget("background")`, correto enquanto o fundo *era* a esteira. Com o fundo claro, ela
> escolheria letra escura para desenhar sobre a esteira escura. Ela resolve contra a esteira agora.

### Testes

- `tests/test_ui_tokens.py`: o papel novo tem reserva e valor de cromo escuro; não está em
  `SUPERFICIES_DE_DOCUMENTO`.
- `tests/test_ui_superficies.py`: os dois critérios — vazio pouco contrastante com o painel, borda
  do tabuleiro acima de `AA_GRAFICO` — uma vez por pele registrada.

---

## S-450 · O estado vazio que não desenha o que não existe

### Problema

Na fotografia da aba Resultado, sem diagrama aberto, a janela mostra ao mesmo tempo:

- um **tabuleiro vazio de 8×8 desenhado por inteiro**, com coordenadas e casas pintadas;
- e, logo abaixo, a frase *"Nenhum diagrama aberto. Clique num diagrama marcado da página, ou use
  «OCR todos diagramas» para ler a página inteira."*

O desenho contradiz a frase. Um tabuleiro vazio é uma **posição** — é o que a S-229 empilha e o que
"Limpar" produz —, e não a ausência de posição. Quem abre o programa pela primeira vez vê um
tabuleiro e conclui que há algo aberto.

A frase, por sua vez, está certa no texto e perdida no lugar: alinhada à esquerda, sob o desenho
que a contradiz, na mesma cor e peso do resto.

### Solução

Quando não há diagrama aberto, o canvas desenha o **vazio da S-449** e a frase ao centro, e não o
tabuleiro. A frase ganha o peso de `tipografia.AUXILIAR` e a cor de `tokens.TEXTO_SECUNDARIO`, que
já existem e já são o par para texto que orienta sem competir.

O item **não** cria ilustração nem ícone de estado vazio: `ui/icones.py` desenha traço em caixa
0..100 e daria conta, mas isso é arranjo, e a recusa do roadmap vale.

A distinção que o item precisa acertar, e que é a sua única dificuldade real: **"nenhum diagrama
aberto" e "diagrama aberto e vazio" são estados diferentes** e passam a ter desenhos diferentes. O
segundo continua desenhando o tabuleiro — é uma posição legítima, e a S-229 pode desfazer para ela.

### Critério de aceite

- Sem diagrama aberto: nenhum tabuleiro desenhado, frase centrada, peso auxiliar. ✅ — o teste
  afirma que os itens do canvas são **só** `text`.
- Com diagrama aberto e posição vazia: tabuleiro desenhado, como hoje. ✅ — `mostrar_vazio` não
  toca o modelo, e é isso que mantém os dois estados separados.
- A troca entre os dois estados não pisca nem redimensiona o canvas. ✅
- Nenhum controle da aba muda de lugar (regra 2). ✅

> **O `Label` da frase saiu, e isso é deliberado.** Ele existia para reservar altura e não fazer o
> painel pular entre os dois estados (S-170). Com a frase no canvas ele ficaria em branco nos dois
> estados — reservando altura para nada. Não é controle, e o item que o criou é o mesmo que agora o
> aposenta. O que se perde com ele é o `texto.acompanhar`, que dava quebra de linha pela largura do
> painel; o `create_text` do canvas faz o mesmo com `width=`.

### Testes

- `tests/test_ui_superficies.py`: os dois estados produzem desenhos diferentes, e o de "sem
  diagrama" não contém casa de tabuleiro.
- `tests/test_ui_desfazer.py`: desfazer até a posição vazia continua no estado "aberto e vazio" — a
  pilha não pode levar o painel ao estado "nenhum aberto".
