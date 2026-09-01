# Roadmap do acabamento — Fases 69 a 72

A interface não está feia por falta de sistema de design. Ela está feia porque **o sistema existe,
está pago, está carregado e não chega aos painéis** — que é, palavra por palavra, o diagnóstico que
`ui/estilos.py:4-7` escreveu sobre o `ttkbootstrap` em 2026-08-17 e que hoje vale sobre o próprio
`ui/estilos.py`. Especificação item a item em [SPEC_ACABAMENTO.md](SPEC_ACABAMENTO.md)
(S-441 a S-450).

Para a fundação que este plano usa — tokens, tipografia, estilos, catálogo de comandos, peles —
[SPEC_UI.md](SPEC_UI.md) e [SPEC_APARENCIA.md](SPEC_APARENCIA.md); para o *como* de hoje,
[ARCHITECTURE.md](ARCHITECTURE.md). Nenhuma fase daqui toca modelo, detecção ou texto.

**Data da medição:** 2026-08-29 · **Ramo:** `fase-5-modelo-desempenho` · **HEAD:** `3ce9e20`
· **Método:** a janela foi aberta nas três peles e fotografada, aba por aba, em 1300×800; cada
número deste documento é ou uma contagem sobre a árvore ou uma amostra de pixel da fotografia, e
o comando que o produziu está no item correspondente da spec.

> **Onde mora a spec de cada item (S-NN).**
>
> | itens | arquivo |
> |---|---|
> | S-01 a S-36 | [SPEC.md](SPEC.md) |
> | S-37 a S-77 | [SPEC_FASE7.md](SPEC_FASE7.md) |
> | S-78 a S-82, S-143, S-175, S-176, S-454, S-455 | [ANALISE_DETECCAO.md](ANALISE_DETECCAO.md) |
> | S-83 a S-94 | [PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md) |
> | S-95 a S-142, S-171 a S-174, S-218, S-219 | [SPEC_FASE14.md](SPEC_FASE14.md) |
> | S-144 a S-170, S-177 | [SPEC_UI.md](SPEC_UI.md) |
> | S-178 a S-217 | [SPEC_TEXTO.md](SPEC_TEXTO.md) |
> | S-220 a S-234, S-294, S-295, S-324 | [SPEC_APARENCIA.md](SPEC_APARENCIA.md) |
> | S-235 a S-267, S-291 a S-293 | [SPEC_EDITOR.md](SPEC_EDITOR.md) |
> | S-268 a S-290 | [SPEC_ESTUDO.md](SPEC_ESTUDO.md) |
> | S-296 a S-323, S-325 a S-430, S-451 a S-453 (menos S-324) | [SPEC_REVISAO.md](SPEC_REVISAO.md) |
> | S-431 a S-440 | [SPEC_REVISAO_EXTERNA.md](SPEC_REVISAO_EXTERNA.md) |
> | S-441 a S-450 | [SPEC_ACABAMENTO.md](SPEC_ACABAMENTO.md) |

---

# O que foi medido, e o que a medição decide

A pergunta que abriu esta fase não foi um pedido de recurso: foi *"o programa não está muito
bonito"*. Isso não é especificação, e a tentação é responder com gosto. A resposta aqui é a
contagem — porque o gosto não distingue **"falta desenho"** de **"o desenho existe e não foi
ligado"**, e as duas doenças têm remédios opostos.

A contagem diz que é a segunda.

> **Duas linhas desta tabela foram corrigidas ao implementar**, e nas duas o instrumento era o
> culpado. A dos botões dizia "30 de 103": a regex olhava nove linhas à frente e casava com o
> `style=` do botão seguinte, e contava como sítio os exemplos dentro do docstring de
> `ui/estilos.py`. Pelo `ast` são **30 de 99**. A do espaço dizia 154: o `grep` só via
> `padx=<inteiro>` e não via `padx=(6, 0)`, que são **131** dos **285**.

| sistema | onde está declarado | quanto foi adotado |
|---|---|---|
| cor por papel | `ui/tokens.py`, 39 papéis | **quase total** — 11 hexadecimais crus em `ui/`, todos em desenho de canvas |
| tipografia | `ui/tipografia.py`, 4 papéis + escala | **quase total** — 2 tuplas de fonte cruas |
| **papel de botão** | `ui/estilos.py`, 3 papéis | **30 de 99 sítios de botão** — 69 não pedem papel nenhum |
| **escala de espaço** | `ui/tipografia.py`, `FOLGAS`, 4 papéis | **4 chamadas** — contra 285 literais |
| **aparência de widget** | — | **não existe** |

A última linha é a que explica a fotografia. **O projeto inteiro tem cinco `style.configure`**, os
cinco em `ui/theme.py:361-378`, e eles cobrem fonte de tabela, fonte de título, altura de linha e
a faixa de abas de *uma* pele. Para `TButton`, `TCheckbutton`, `TEntry`, `TFrame`, `TLabelframe`,
`TSpinbox`, `TCombobox`, `TRadiobutton`, `TSeparator`, `TScale` e `TNotebook` o número é **zero**.

Não há folha de base. O que a janela mostra nesses onze widgets é o que o tema der -- e o que ele
dá não é uniforme, o que só ficou claro ao implementar a Fase 69. Ver a correção no fim deste
documento: **o `ttkbootstrap` já folga quem ele tematiza, e deixa vazio exatamente os quatro
widgets que a fotografia mostrou quebrados.** O item continua de pé; o alvo dele encolheu.

---

# Sete achados, e os quatro que mudam o plano

**1 · A hierarquia de botão está correta, é testada, e é invisível na pele que abre por padrão.**
Este é o achado da fase inteira, e ele não é de gosto — é de correção.

`ui/estilos.py` define três papéis e dá a `DESTRUTIVO` uma justificativa que não é decorativa:
*"`labels.csv` é rótulo corrigido à mão, e a S-76 é o registro do que custa um botão destrutivo
que não parece um: 1.405 diagramas sobrescritos por um clique."* O sistema funciona. Medido, numa
janela de três botões, um por papel:

| tema `ttkbootstrap` | quem o usa | neutro | primário | destrutivo |
|---|---|---|---|---|
| `bootstrap-dark` | **só a pele "Foco"** | `(46,50,54)` | `(61,139,253)` azul | `(227,93,106)` vermelho |
| `bootstrap-light` | **a clássica (padrão) e a "Fita"** | `(240,240,240)` | `(240,240,240)` | `(240,240,240)` |

No tema claro os três papéis pintam **o mesmo cinza**. Não é ausência de adoção — é o `style=`
correto, resolvido, e sem efeito: na 2.2.0 o `bootstrap-light` não redefine a face de
`primary.TButton` nem a de `danger.TButton`.

A consequência é literal: **na pele que 100% dos usuários veem sem abrir menu nenhum, "Remover" —
que apaga trabalho humano do `labels.csv` — é o mesmo cinza de "Copiar legenda".** A S-144 foi
escrita para acabar com isso; ela trocou `bootstyle=` por `style=`, que era o defeito de API, e o
defeito de resultado continuou de pé por baixo. `ui/estilos.py:17-21` chega a prever o caso — *"num
`Tk` **sem** `ttkbootstrap`, com o tema `vista`, `style="primary.TButton"` não levanta"* — e o
aceita como contrato de degradação. O que não estava previsto é que o mesmo aconteceria **com** o
`ttkbootstrap` instalado, no tema padrão.

**2 · O respiro das abas já foi escrito, e é entregue a uma pele só.** A faixa de abas da
fotografia clássica não tem folga nenhuma: o rótulo encosta na borda dos dois lados. A correção
existe, tem uma linha, e está em `ui/theme.py:377` —
`padding=(14, 6)`. Ela é aplicada em `app_tkinter.py:1978`:

    self.left_tabs.configure(style=theme.ESTILO_DE_ABAS_DISCRETO if montagem == pele.CROMO_FOCO else "")

`else ""`. A clássica e a "Fita" recebem a aba crua do Win32. É por isso que a fotografia da "Foco"
parece um programa de 2026 e a da clássica parece um de 2009 — **e a diferença entre as duas, ali,
é uma condição de uma linha.**

**3 · A causa estrutural: as Fases 32 a 35 escoparam o desenho ao cromo, por escrito.**
`ROADMAP_APARENCIA.md:345` recusa, na lista do que foi considerado e rejeitado:

> **Redesenhar as seis abas por dentro.** Fora de escopo. As peles mudam o cromo em volta delas.

A decisão estava certa para aquelas fases — três peles em três semanas não cabem com o interior
junto. Mas o cromo é a minoria dos pixels. O que sobrou de fora é o interior dos **sete** painéis,
que é onde o trabalho acontece e é onde o olho fica. Quatro fases de aparência entregaram três
peles e **nenhuma passada no lugar que o usuário olha o dia inteiro.**

**4 · E a regra 1 congela justamente a pele padrão.** `SPEC_APARENCIA.md:30`:

> **A pele clássica é o padrão e não muda.** Quem nunca abrir `Ver ▸ Aparência` tem, pixel a pixel,
> a janela de hoje.

Somada ao achado 3, a regra produz o estado atual: a pele que todo mundo vê é a única proibida de
melhorar, e o interior que todo mundo olha é o único fora de escopo. **Não há caminho pelo qual a
janela padrão fique melhor.** Não por descuido — por duas decisões corretas que, juntas, fecham a
porta.

> **A releitura que esta fase propõe, e que é o item S-443.** A regra 1 protegia contra *arranjo*
> divergente: que a clássica ganhasse controle em lugar diferente e virasse uma quarta tela a
> manter. Essa proteção continua valendo e ninguém a está pedindo de volta. O que ela **não**
> precisava congelar é o acabamento — folga, peso, alinhamento, indicador. A regra passa a ser:
>
> **a pele clássica não muda de *arranjo*.** Nenhum controle nasce, morre ou muda de lugar nela.
> O acabamento é da janela, não da pele, e chega às três ao mesmo tempo ou não chega a nenhuma.

**5 · O tabuleiro flutua num slab quase-preto que ocupa 62% do canvas.** Amostrado na fotografia
clássica, na linha `y=340`: o canvas do tabuleiro tem 691 px de largura e **429 deles são
`(49,46,43)`** — quase-preto — contra um painel de fundo `(255,255,255)`. O tabuleiro em si mede
261 px e está centrado nesse vazio.

É a aresta de maior contraste da janela inteira, e ela está em volta de **espaço vazio**, que não
carrega informação nenhuma. O contraste que a S-146 e a S-224 mediram com cuidado sobre marcação e
texto nunca foi medido sobre o vazio — porque vazio não é papel de cor, e `tokens.py` não tem um
para ele.

**6 · O indicador de caixa de seleção encosta no rótulo, em toda a janela.** `☒Marcar diagramas`,
`☒Roda vira a página`, `☒Mapa de incerteza`, `☐Treinar do zero` — o glifo toca a primeira letra.
`style.lookup("TCheckbutton", "indicatormargin")` devolve vazio. É um `configure` de uma linha, e
ele aparece em quatro pontos da fotografia de uma aba só.

**7 · O formulário da Configuração corta rótulo e dimensiona campo por acaso.** Na mesma aba:
"Taxa de aprendizado" é desenhado como `Taxa de aprendizad`, cortado no meio do glifo; e o campo
mais largo do painel (≈590 px) é o que guarda o valor mais curto (`0.001`), enquanto "Épocas" (`8`)
e "Tamanho do lote" (`128`) ficam com ≈100 px. Três colunas de conteúdo diferentes em oito linhas
de formulário, e a largura do campo não diz nada sobre o dado que ele espera.

**E dois achados que não mudam o plano, mas entram na spec:** os 15 botões de `ui/gallery_panel.py`
não pedem papel nenhum — e um deles é **"Limpar os headers"** (`gallery_panel.py:428`), que
`ui/estilos.py:38` cita **pelo nome** como exemplo canônico de `DESTRUTIVO`. O módulo nomeia o
botão, e o painel que o desenha não o consulta. E a aba Estudo empilha 27 botões de peso idêntico
em quatro fileiras, com o último cortado na borda do painel.

---

# As quatro fases

| fase | itens | o que ela entrega |
|---|---|---|
| **69** — a base que falta às três peles | S-441 a S-443 | a folha de base do `ttk`: onze widgets com folga, peso e indicador; e a regra 1 relida |
| **70** — a hierarquia que existe e não pinta | S-444 a S-446 | primário e destrutivo visíveis no tema claro, e nos botões que os pedem |
| **71** — o espaço como dado | S-447 e S-448 | os 154 literais recolhidos à escala, e a grade de formulário |
| **72** — as superfícies do documento | S-449 e S-450 | o vazio em volta do tabuleiro, e o estado vazio que não desenha o que não existe |

## Fase 69 — a base que falta às três peles — ✅ **completa em 2026-08-29**

Vem primeiro porque é a única que melhora **as três peles de uma vez, sem tocar painel nenhum**, e
porque é a que tem a maior razão entre pixel mudado e linha escrita. Uma folha de base é um arquivo
e um ponto de chamada; ela alcança a janela inteira sem que nenhum widget seja editado.

- **S-441** · A folha de base do `ttk`: os widgets que ninguém estiliza — ✅ **implementada em 2026-08-29**
- **S-442** · O indicador que encosta no rótulo, e o vão que ele nunca teve — ✅ **implementada em 2026-08-29**
- **S-443** · A regra 1 relida: a clássica não muda de *arranjo* — ✅ **implementada em 2026-08-29**

Ao fim da fase o arranjo da janela é o de hoje — mesmos controles, mesmos lugares, mesma ordem — e
o acabamento é outro nas três peles. É o inverso deliberado da Fase 32, que provou a fundação **não
mudando nada**: esta prova a folha de base mudando **só** o acabamento.

> **Onde a fase está, e a medição que cortou o item pela metade.**
>
> **O diagnóstico deste roadmap estava certo na contagem e errado na causa, e o erro era de
> bancada.** A frase "`padding` de um `ttk.Button` resolve para `1 1`" foi lida com o tema `vista`
> — que é o que responde **antes** de `apply_theme` rodar. Sob os temas que o programa de fato usa
> a resposta é outra:
>
> | classe | `bootstrap-light` e `bootstrap-dark` | |
> |---|---|---|
> | `TButton` | `10 4` | já vem folgado |
> | `TMenubutton` | `10 4 6 4` | já vem folgado |
> | `TEntry` | `5` | já vem folgado |
> | `TCombobox` | `5 6 7 4` | já vem folgado |
> | `TNotebook.Tab` | `''` | **vazio** |
> | `TCheckbutton`, `TRadiobutton` | `''`, e `indicatormargin` também | **vazio** |
> | `TSpinbox` | `''`, ao lado de um `TEntry` que tem 5 | **vazio** |
> | `TLabelframe` | `''` | **vazio** |
>
> **O `ttkbootstrap` cobre o que ele tematiza e deixa vazio exatamente o que a fotografia mostrou
> quebrado.** A aba sem folga e o indicador colado no rótulo não eram "o Tk de 2009": eram os dois
> widgets que a biblioteca não desenha. A folha entregue cobre **cinco** classes e não onze, e a
> fronteira virou teste: `test_a_folha_nao_encosta_em_quem_o_tema_ja_resolve`.
>
> Escrever a folha sobre as quatro primeiras foi tentado e **medido como piora**: com
> `padding=(6, 2)` o botão de fita encolhe de 58 para 50 px de largura, porque 6 é menos que os 10
> que o tema já dava. E o valor que a spec pedia — `(10, 6)` — custa **+51 px** nas duas barras do
> painel de PDF e faz o `barra_livro` saltar de 98 para 138 px, quebrando em mais linhas: botão que
> muda de linha é controle que muda de lugar, e a regra 2 proíbe isso na clássica.
>
> Outras duas linhas da spec caíram pela mesma disciplina. **`TFrame` não entra**, e o número é
> grande: são **117 `ttk.Frame` aninhados até 8 níveis**, e um `padding` de classe se aplica a cada
> moldura do ramo — `8 × 10 × 2 = 160 px` de cada eixo no mais fundo. **`TSeparator` e `TScale` não
> têm folga a dar**: o vão deles é com o vizinho, e isso é `pady=` de quem empacota — é a S-447.
>
> O que a fase entregou, então: `ui/folha.py` — e não `ui/base.py`, porque `base` é o nome do
> parâmetro de fonte que atravessa `tipografia`, `fita` e `theme`, e `from . import base` ficaria
> sombreado dentro de toda função que o recebe. A faixa de abas ganhou `(14, 6)` **nas três peles**
> — o valor que a S-226 mediu e que ficava entregue a uma só —, e a aba montada foi de 22 para
> 34 px de altura. O `indicatormargin` existe nos dois temas e resolve para `0 0 6 0`.
>
> **E a S-443 mudou de forma ao ser escrita.** O critério dizia "o `padding` é igual nas três
> peles", e seguido à letra ele reprovaria a pele "Fita" — que sugere densidade compacta, onde a
> folha é *menor de propósito*. O que o teste cobra é acabamento igual **na mesma densidade**: pele
> não muda acabamento, densidade muda, e é para isso que a S-232 existe.
>
> **O que a fase custou em altura, medido, e por que não é violação da regra 2.** Nas duas barras
> do painel de PDF, em 1300×800:
>
> | | `barra_livro` | `barra_vista` | soma |
> |---|---|---|---|
> | antes | 122 | 63 | **185** |
> | depois | 112 | 84 | **196** |
>
> **+11 px no total**, e o `barra_livro` ficou 10 px *mais baixo*. O que reflui é a `barra_vista`,
> pelas duas caixas de seleção que ganharam o vão do indicador — não pelo `TSpinbox`, que foi
> isolado e não muda nada. E reflui é o verbo certo: **posição numa `BarraFluida` é função da
> largura por construção** (S-151), e a barra reflui a cada redimensionamento da janela. A regra 2
> protege controle que muda de pai, de ordem ou de existência; nenhum deles muda aqui. É o que
> separa este caso do `(10, 6)` no `TButton`, que custava +51 px e alargava **todos** os 21
> controles de uma vez.

## Fase 70 — a hierarquia que existe e não pinta — ✅ **completa em 2026-08-29**

- **S-444** · `primary` e `danger` que pintam no tema claro — ✅ **implementada em 2026-08-29**
- **S-445** · Os 69 botões que não pedem papel, e o destrutivo que a Galeria esconde — ✅ **implementada em 2026-08-29**
- **S-446** · Um primário por barra: a regra que já existe, cobrada em todas as barras — ✅ **implementada em 2026-08-29**

Depende da 69 porque a folha de base é onde a correção do tema claro mora. É a fase que fecha a
S-76 de verdade: até ela, o botão que apaga trabalho humano é cinza na pele padrão.

> **Onde a fase está, e as quatro coisas que a medição mudou.**
>
> **1 · O tema escuro precisava da correção tanto quanto o claro, ao contrário do que a spec
> dizia.** Ela mandava não sobrescrever o `bootstrap-dark` porque "lá os dois já pintam, e pintam
> bem". Medido no pixel do widget montado:
>
> | tema | neutro | primário | destrutivo |
> |---|---|---|---|
> | `bootstrap-light` (clássica e "Fita") | `#f0f0f0` 18,4 | `#f0f0f0` **18,4** | `#f0f0f0` **18,4** |
> | `bootstrap-dark` ("Foco") | `#2e3236` 12,9 | `#3d8bfd` **3,33** | `#e35d6a` **3,48** |
>
> No claro os três eram a **mesma face**; no escuro os dois de ênfase ficavam em 3,33 e 3,48 com
> letra branca — **abaixo do piso `AA_TEXTO` de 4,5 que o critério de aceite do próprio item exige
> nas três peles.** As duas metades da spec se contradiziam, e o pixel desempatou: os dois papéis
> passam a sair do token nas duas paletas. Agora: 6,44 / 8,79 no claro e 7,81 / 5,71 no escuro.
>
> **2 · São três tokens e não quatro, e quem decidiu foi a regra da paleta.** A spec pedia face e
> letra de cada papel. Duas letras brancas seriam dois papéis com o mesmo hexadecimal, e
> `test_dois_papeis_de_significado_diferente_nao_compartilham_hex` proíbe isso com
> `COINCIDEM_DE_PROPOSITO` **vazia** — cujo docstring, por sua vez, desaconselha "inventar uma
> diferença só para separar os nomes". A saída já existia no mesmo arquivo:
> `TEXTO_SOBRE_MARCACAO` é **um** papel para "a letra que vai por cima". `TEXTO_SOBRE_ENFASE` é o
> irmão dele, e as duas faces foram escolhidas para que a mesma letra passe AA sobre as duas.
>
> **3 · A face escura clareia em vez de escurecer, e o número é o motivo.** A receita óbvia — o
> mesmo vermelho, mais escuro — reprova no critério que importa: `#b02a37` sobre o botão neutro
> `#2e3236` dá **1,99:1**, vermelho escuro em cima de cinza escuro. As faces clareiam e a letra
> escurece. E o valor escuro do destrutivo é o claro **clareado em HSL com matiz e saturação
> intactas** — 0,03° de desvio —, porque `test_a_matiz_do_papel_sobrevive_a_troca_de_pele` cobra
> menos de 2° e a primeira escolha (`#e8897c`, escolhida a olho na tabela) dava 3,19° e reprovou.
>
> **4 · A pintura mora em `ui/theme.py` e não na folha da S-441.** A spec dizia "na folha de
> base". A folha importa `pele` e `tipografia` e nada mais — é o que a mantém sobre *folga*; para
> pintar ela precisaria de `tokens` e de `theme.cor_atual`, e **`theme` importa `folha`**, então
> seria um ciclo. `theme.py` já é a casa dos estilos nomeados (`Dado.Treeview`,
> `Discreta.TNotebook`), e `primary.TButton` é um deles.
>
> **E o teste que congelava o defeito.** `test_nenhum_outro_botao_da_janela_e_destrutivo` afirmava
> que nenhum arquivo fora do Dataset declara `DESTRUTIVO` — e passava, porque a Galeria nunca
> declarou. Só que `ui/estilos.py:47` cita **"Limpar os headers"** pelo nome como exemplo canônico
> do papel. O teste era verdade sobre o código e falso sobre a intenção, e protegia a distância
> entre as duas. Virou uma lista de isenções com motivo assinado, mais um teste que reprova
> isenção órfã.
>
> **O que a S-445 entregou, e o que ficou de fora.** Entregou o que muda pixel e o que remove
> inconsistência: "Limpar os headers" virou `DESTRUTIVO`, e cinco sítios que já liam o **rótulo**
> do catálogo passaram a ler dele também o **papel** (`limpar_tabuleiro`, os dois de histórico,
> `achar` e `substituir_todos`).
>
> **E a varredura dos `NEUTRO` restantes fechou depois, a pedido** — 69 sítios, e ela rendeu
> três coisas que valem mais que a anotação.
>
> **1 · O número da spec estava errado, e o instrumento era o culpado.** "30 de 103" veio de uma
> regex que olhava nove linhas à frente atrás de `style=` — e casava com o `style=` do botão
> **seguinte**. Refeita com `ast`, a conta é **30 de 99**: os quatro sítios a mais eram exemplos
> dentro do docstring de `ui/estilos.py`, que não são código. Hoje são **99 de 99**.
>
> **2 · O `ast` cobra caro por uma distração, e ela custou dez erros de sintaxe.** `col_offset` e
> `end_col_offset` contam **bytes UTF-8**, não caracteres. Usados como índice de `str`, eles
> derrapam um caractere por byte extra — e toda linha com acento tem pelo menos um. `"Procurar…"`
> tem três bytes num caractere, e o `).pack(` seguinte virou `)ack(`. Os dez foram reparados, e a
> conferência não foi o olho: **todos os literais de texto de todos os arquivos varridos foram
> comparados com os de `HEAD`**, e a única diferença é a intencional.
>
> **3 · Duas asserções do projeto mediam formatação, não fato.**
> `test_strings.DestrutivoTests` exigia que `text="Remover"` e `estilos.DESTRUTIVO` estivessem na
> **mesma linha**, e `test_ui_campos` procurava o texto exato `campos.linha_de_caminho(cfg_tab,`.
> As duas quebraram quando a chamada passou a não caber em 120 colunas. As duas passaram a
> perguntar ao `ast` o que interessa: qual papel aquele botão declara, e qual função monta aquele
> campo.
>
> A varredura ainda vale a pena como passada mecânica — foi ela que achou "Copiar headers para
> todos" sem papel. **Esse ficou `NEUTRO` pelo critério do próprio item** (apaga trabalho humano,
> não pergunta, **não desfaz**): ele tem "Desfazer a cópia" no botão logo abaixo.
>
> **E o estado desabilitado deu o último achado, na janela montada.** "Limpar os headers" **nasce
> desabilitado**, e a primeira versão da pintura mapeava o desabilitado para tokens nossos —
> `SUPERFICIE_PADRAO` no fundo e `TEXTO_SECUNDARIO` na letra. Fotografado na aba Galeria, o
> resultado era um botão desabilitado com letra `#555555` ao lado de um "Partidas da base"
> desabilitado com a letra `#c8cccf` do tema: **o destrutivo desligado parecia mais aceso que o
> neutro desligado.** O desabilitado passou a sair do próprio tema (`lookup` com o estado
> `disabled`, reserva nos tokens se ele não responder). Desabilitado é desabilitado, e tem de ficar
> igual em todo botão que não responde.

## Fase 71 — o espaço como dado — ✅ **completa em 2026-08-29**

- **S-447** · Os **285** literais de espaço recolhidos à escala de folga — ✅ **implementada em 2026-08-29**
- **S-448** · A grade de formulário: rótulo que não corta, campo dimensionado pelo dado — ✅ **implementada em 2026-08-29**

É a fase de menor risco visual e maior risco de tédio: centenas de sítios, um a um, sem nada de
novo na tela.

> **Onde a fase está, e as três coisas que a medição mudou.**
>
> **1 · São 285 literais e não 154, e a diferença é uma forma que a contagem original não via.**
> O `grep` que dimensionou o item procurava `padx=<inteiro>`; a janela também usa
> `padx=(6, 0)` — o par que dá espaço de um lado só. São **131** deles, quase metade do total.
> Convertidos: **273**. A conversão foi feita com `tokenize` e não com regex por linha, e a razão
> é que `ui/folha.py` e `ui/tipografia.py` **documentam** `padx=10` e `padding=(6, 2)` em
> docstring: converter prosa é o defeito que uma regex cega cometeria.
>
> **2 · Três literais não couberam em papel nenhum, e continuam literais.** A spec previu o caso e
> proibiu a saída fácil — *"o item não inventa papel"*. São: a calha de 18 px entre a tecla e a
> descrição na legenda (separação de coluna de tabela, não vão entre vizinhos); os 3 px do rodapé,
> que fica entre `FOLGA_MINIMA` e `FOLGA_DE_LINHA` porque a barra é fina de propósito; e o recuo
> de 22 px que alinha um rótulo sob o **texto** de um `Checkbutton`, e portanto depende da largura
> do indicador e não da escala. Cada um tem o motivo escrito no próprio sítio e uma entrada em
> `test_ui_espaco.SemLiteralTests.EXCECOES`.
>
> **3 · O critério de densidade da spec era inalcançável, e o motivo é estrutural.** Ela pedia que
> "a densidade compacta encolha o interior dos sete painéis". `padx`/`pady` são opções de `pack`,
> fixadas quando o widget é empacotado — e `app_tkinter.remontar_cromo`, que é o que a troca de
> densidade chama, diz no próprio docstring que *"refaz o cromo **sem tocar o conteúdo**"*. Os
> painéis não são remontados, e opção de `pack` não se reaplica sozinha.
>
> O que a fase entrega, então, é o outro lado do item, e ele é o durável: **o espaço do interior
> passa a derivar da fonte do sistema** — quem aumenta a fonte do Windows ganha vão proporcional
> em vez de pixel cravado, que é o argumento da S-149 aplicado ao espaço. A densidade escolhida
> alcança o interior **na abertura seguinte**, porque ela é gravada no estado.
>
> O módulo é `ui/espaco.py`, e ele existe porque `tipografia.folga` é **pura**: ela pede `base` e
> `densidade` em toda chamada, e num `pack` isso vira uma linha de 100 caracteres para dizer
> `padx=6` — além de obrigar o painel a saber de densidade, que não é assunto dele. Aqui a
> pergunta é `padx=espaco.linha()`, e quem fixa os dois é `theme.registrar_estilos`, no mesmo
> ponto em que ela aplica a folha da S-441.
>
> **E a S-448 achou três medidas do mesmo formulário, não uma.** O rótulo cortado —
> `Taxa de aprendizad` — era `largura_do_rotulo=16` contra um rótulo de 19 caracteres. Mas ao lado
> dele havia um `24` cravado no rótulo da orientação e um `_spin_row` no `app_tkinter` que era uma
> **segunda implementação** da mesma linha de formulário, com largura própria. A coluna passou a
> sair do rótulo mais longo dos dez (`strings.ROTULOS_DA_CONFIGURACAO`, hoje 22 caracteres), o
> `_spin_row` virou `campos.linha_de_giro`, e o campo de número deixou de pedir `expand=True` —
> era ele que ficava com ≈590 px para guardar `0.001`, o campo mais largo do painel para o valor
> mais curto dele.

## Fase 72 — as superfícies do documento — ✅ **completa em 2026-08-30**

- **S-449** · O tabuleiro que não flutua num slab quase-preto — ✅ **implementada em 2026-08-30**
- **S-450** · O estado vazio que não desenha o que não existe — ✅ **implementada em 2026-08-30**

Vem por último porque é a que mais depende de julgamento e a que menos trava as outras.

> **Onde a fase está, e o diagnóstico que estava errado.**
>
> **O slab não era falta de token — era esteira sem fim.** Este roadmap supôs que o `(49,46,43)`
> tinha sido "escolhido no canvas e nunca passou por `cor()`". Não: ele saía de `cor()` e tinha
> papel havia tempo — era `SUPERFICIE_TABULEIRO`, a **esteira**, escolhida escura pela S-147 com
> uma razão boa, porque é ela que dá 11,03:1 às coordenadas, que são desenhadas em cima dela.
>
> O erro estava noutro lugar: a esteira **era o fundo do canvas**, e o canvas enche o painel
> (`pack(fill=BOTH, expand=True)`). Então tudo o que não fosse tabuleiro virava esteira — 62% da
> largura, num painel `#f0f0f0`.
>
> A esteira passou a ser um retângulo com tamanho: tabuleiro mais a margem que a coordenada já
> reservava (`board_render.margem_de_coordenada`, a mesma função, para as duas não divergirem). O
> que sobra é `VAZIO_DE_CANVAS`. **Medido na mesma linha `y=340` da mesma fotografia: 62% → 4%.**
>
> **Uma consequência que o item não previa:** `_cor_de_coordenada` resolvia contra
> `canvas.cget("background")`, e estava certo enquanto o fundo *era* a esteira. Com o fundo claro,
> ela passaria a escolher letra escura para desenhar sobre a esteira escura. Ela resolve contra a
> esteira agora — o princípio não mudou, mudou o que está debaixo do que se desenha.
>
> **E o critério de aceite precisou ser reescrito, porque como estava ele reprovava nas peles
> escuras.** Ele pedia que a borda do tabuleiro passasse `AA_GRAFICO` contra o vazio. Medido:
>
> | paleta | vazio vs painel | esteira vs vazio | moldura vs vazio | casa clara vs vazio |
> |---|---|---|---|---|
> | clara | **1,03** | 11,50 | 14,32 | 1,17 |
> | tema escuro | 1,21 | 1,03 | 1,07 | **13,55** |
> | pele escura | 1,04 | 1,08 | 1,19 | **12,17** |
>
> **O que separa o tabuleiro do vazio troca de dono com a paleta.** Na clara são a esteira e a
> moldura — a casa clara sozinha daria 1,17. Nas escuras as duas se fundem no vazio, e quem separa
> é o próprio tabuleiro; e está certo assim, porque ali o cromo inteiro é escuro e não há slab a
> desfazer. O critério passou a ser: **pelo menos um dos três** passa o piso, em toda paleta.
>
> **A S-450 tirou a frase do rótulo e a pôs no canvas.** Ela ficava alinhada à esquerda, **sob** o
> tabuleiro 8×8 que a contradizia. O `Label` saiu junto: ele existia para reservar altura e não
> fazer o painel pular entre os dois estados, e mantê-lo em branco passaria a reservar altura para
> nada. A distinção que o item pedia está de pé — "nenhum diagrama aberto" e "diagrama aberto e
> vazio" continuam sendo estados diferentes, e o segundo desenha tabuleiro, porque é uma posição
> legítima e a pilha da S-229 pode voltar a ela.

---

# O que foi considerado e recusado

- **Porte para Qt.** Os dois gatilhos de `ARCHITECTURE.md:189-195` continuam sem disparar: o `labels.csv` tem 4.858
  linhas contra as 10 mil do gatilho, e a sobreposição editável da Fase 8 não foi pedida. E a
  medição desta fase é um argumento *contra* o porte, não a favor: se cinco `style.configure` são
  a diferença entre a fotografia da "Foco" e a da clássica, o problema nunca foi o Tk.
- **Um quarto tema `ttkbootstrap` desenhado à mão.** Resolveria a S-444 e criaria um tema para
  manter. A folha de base resolve o mesmo com `style.configure` sobre o tema que já vem.
- **Trocar o padrão para a pele "Foco".** É a saída barata, e ela troca o defeito de lugar: o cromo
  escuro põe a página renderizada contra preto, que é exatamente o que `ui/theme.py:54-56` recusa
  por escrito, com um argumento que continua bom.
- **Redesenhar o arranjo dos painéis.** Fora de escopo aqui, e de propósito: as quatro fileiras de
  botão do Estudo e as duas barras do PDF são problema de *arranjo*, não de acabamento. Elas
  merecem um plano próprio, depois destas — e depois que a folga e o peso existirem para desenhá-lo.
- **Ícone em todo botão.** `ui/icones.py` tem catorze traços e eles servem à fila e à fita.
  Espalhá-los pelos painéis é decisão de arranjo, e cai na recusa acima.

---

# Custo, risco e ordem

| fase | esforço | risco | o que trava se der errado |
|---|---|---|---|
| 69 | 2 a 3 dias | **médio** — alcança a janela inteira de uma vez | é a única com reversão de uma linha: não chamar a folha |
| 70 | 2 dias | baixo | os papéis continuam cinza no tema claro, como hoje |
| 71 | 3 a 4 dias | **baixo** — 154 sítios mecânicos | a densidade compacta segue sem alcançar o interior |
| 72 | 2 a 3 dias | médio — papel de cor novo | o tabuleiro segue no slab |

**Total: ~9 a 12 dias.** As fases 71 e 72 são independentes entre si e dependem só da 69; a 70
depende da 69. A ordem escrita é a de maior efeito visível primeiro.

**O risco real desta fase é o oposto do da Fase 34.** Lá, três peles convidavam a consertar só numa;
o perigo era divergir. Aqui há um lugar só — a folha de base — e o perigo é o contrário: **uma linha
errada nela é uma linha errada em cento e três botões.** É o que faz a S-443 valer o item que ela
custa: o teste que fotografa as três peles e cobra que o acabamento seja o mesmo nas três é o mesmo
teste que pega a folha de base saindo do lugar.

**E a regra de degradação de `ui/theme.py:12-15` continua valendo, com um dono a mais:** nem tema
ausente, nem pele desconhecida, nem folha de base que não aplicou podem ser motivo de a janela não
abrir. Acabamento não derruba ferramenta.
