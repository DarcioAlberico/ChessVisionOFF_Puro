# Análise · O glifo do cabeçalho reconhecido como diagrama

> Medido em 2026-08-14 sobre `Secrets of Chess Training School of Future Champions 1_ao_5.pdf`
> (1181 páginas) e conferido nos outros 26 PDFs do acervo. Scripts de medição descritos ao
> final, em [Como reproduzir](#como-reproduzir).

> **Onde mora a spec de cada item (S-NN).** Este arquivo é o de **detecção**, e é por isso que
> a faixa dele não é contígua: item de detecção mora aqui, ao lado da medição que o motivou, e
> não com o número vizinho. Foi assim que a S-143 entrou junto da S-80, que é a medição que ela
> corrige. `tests/test_docs.py` confere esta tabela contra o disco (S-134).
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

## 1. O que aconteceu na página 231

O cavalo desenhado no alto da página não é texto: é uma **imagem embutida** que o PDF
declara, e `candidates_from_embedded_images` a aceita. Os números da página (índice 231,
`page.get_image_info()`):

| | nativo | na página | fração da página |
|---|---|---|---|
| glifo do cabeçalho | 128×128 px | **15,4 × 15,4 pt** | 0,0009 |
| diagrama de verdade | 1280×1264 px | 153,6 × 151,7 pt | 0,0857 |

O glifo passa em **todas** as quatro guardas do módulo:

| guarda | valor | limite | passa? |
|---|---|---|---|
| `MIN_EMBEDDED_SIDE` | 128 px nativos | ≥ 120 | ✅ passa |
| `ASPECT_TOLERANCE` | aspecto 1,000 | 0,80 – 1,20 | ✅ passa (é quadrado perfeito) |
| `MAX_PAGE_COVERAGE` | 0,0009 da página | ≤ 0,70 | ✅ passa |
| `_pixels_for_bbox` | 128×128 px renderizados | ≥ 16 | ✅ passa |

E sai do detector com `detector_score` **0,700** — mais alto que o de vários diagramas
legítimos de outros livros.

A intuição do relato ("talvez por ser maior que a altura de uma linha") está certa no
espírito e errada no mecanismo: **não é o contorno que o pega, é a imagem embutida.** O
caminho de contorno chegou a olhar essa região e a recusou corretamente —

```
INFO detection.hybrid: Refino do contorno descartado em (375, 16, 391, 32): textura de
tabuleiro cairia de 0.3827 para 0.0215. Fica o recorte embutido cru.
```

— mas a recusa do contorno só decide **como recortar** um candidato que a fonte embutida já
tinha admitido. Nenhuma guarda pergunta se ele deveria existir.

---

## 2. A causa: a guarda mede a unidade errada

```python
MIN_EMBEDDED_SIDE = 120
"""Lado mínimo em pixels nativos. Abaixo disso é ícone, logotipo ou peça solta."""
```

O docstring diz o que a constante quer impedir — ícone, logotipo, peça solta — e a
implementação mede outra coisa. **Pixels nativos são uma propriedade de resolução, não de
tamanho.** Um glifo de 15,4 pt gravado a 600 DPI tem 128 px nativos; um diagrama de 150 pt
gravado a 72 DPI teria 150. A constante separa "imagem de alta resolução" de "imagem de baixa
resolução", que é uma pergunta que ninguém fez.

A grandeza que responde a pergunta certa — *isto ocupa espaço de diagrama na página?* — é o
lado do `bbox` em **pontos**, e ela já está na mão: a função lê `info["bbox"]` três linhas
abaixo, para outra coisa.

---

## 3. A extensão no acervo

Distribuição do lado em pontos de **todas** as imagens embutidas aprovadas pelo filtro atual,
no livro do relato:

```
1181 páginas, 1371 imagens embutidas aprovadas

   10 pt :     5   ← glifo
   20 pt :    65   ← glifo
   30 pt :     1   ← glifo
  ---------------- vale: nada entre 30 e 140 pt ----------------
  140 pt :   231
  150 pt :  1032
  160 pt :    19
  170 pt :     7
  180 pt :    10
  190 pt :     1
```

**71 falsos positivos em 1181 páginas**, e um vale de 110 pt separando as duas populações sem
uma única amostra dentro. O mesmo padrão, em menor escala, no `Karpov 1` (2 em 30 pt) e no
`Kemeri` (1 em 50 pt).

### O que o censo corrigiu neste número

> Esta seção é o primeiro resultado da S-82, e ela contradiz o que a análise afirmava antes de
> existir instrumento. Fica registrada em vez de reescrita em silêncio: é a diferença entre um
> número medido e um número estimado a partir de uma amostragem grosseira.

A primeira varredura olhou só as imagens embutidas aprovadas pelo filtro **atual**, agrupadas
por livro, e concluiu que o vale ia de 50 pt (maior glifo) a 110 pt (menor diagrama). Medido
pelo censo, candidato a candidato, no acervo inteiro:

| população, só fonte embutida | faixa |
|---|---|
| glifos de cabeçalho (`Secrets`, `Karpov`, `Kemeri`) | 15 – 50 pt |
| **fragmentos do `GALLAGHER`** (§S-81) | **38,8 – 106,5 pt** |
| diagramas de verdade (menor: `Euwe Band 1-2`) | **105,6 pt** e acima |

Os fragmentos do `GALLAGHER` **encavalam** os diagramas reais por 0,9 pt. A consequência muda
o plano em dois pontos, e os dois estão anotados adiante:

- O piso em pontos segue seguro e segue resolvendo o relato — o vale entre **glifo** e
  diagrama continua largo (50 → 105,6 pt). O que ele não faz é o que eu tinha escrito de
  bônus: ele **não** limpa o `GALLAGHER`.
- A S-81 deixa de ser a entrega mais dispensável e passa a ser **necessária**: nenhum limiar de
  tamanho pode separar aquelas duas populações, porque elas se sobrepõem.

---

## 4. Os quatro danos, medidos

Não é só ruído na tela. Em ordem de gravidade:

### 4.1 A numeração do PGN aponta para a posição errada — 14 páginas

O glifo mora no alto da página, então em ordem de leitura ele às vezes vem **antes** de um
diagrama de verdade. Medido: em **14 das 71 páginas** o glifo não fica no fim da lista, e
consome um número. Na página 342 ele é o candidato **#0**.

Isso é exatamente o defeito que a S-14 fechou por outro caminho: o `[Diagram "2"]` do PGN
deixa de apontar para o que a tela chama de 2. A S-14 unificou a *regra* de ordenação entre
GUI e exportação; ela não podia prever que a *lista* estivesse contaminada.

### 4.2 O glifo envenena o gabarito de tamanho — 42 páginas

`detect_diagrams` calcula o "lado típico do diagrama nesta página" pela **mediana** dos
candidatos embutidos, e usa isso para decidir quais achados de contorno são diagrama:

```python
sides = [max(box[2], box[3]) for box in embedded_boxes]
expected_side = float(np.median(sides))
```

Numa página com um glifo de 15 pt e um diagrama de 154 pt, a mediana dá ≈ 85 pt. Com
`EMBEDDED_SIZE_TOLERANCE = 0,30`, a janela aceita passa a ser 59–110 pt — e **todo diagrama de
verdade que o contorno achasse seria recusado por tamanho**. São **42 páginas** nessa
condição.

O efeito é silencioso e inverte a intenção do mecanismo: o prior de tamanho existe para
recuperar diagramas não declarados (a medição da S-12 achou 4 por livro no `Schiller` e no
`Karpov`), e o glifo o transforma numa guarda que os bloqueia.

### 4.3 O trabalho humano que o falso positivo gera

Cada glifo vira um recorte na galeria, uma linha na fila de revisão, um item que pede rótulo.
São 71 neste livro. O custo não é o pixel — é o clique.

### 4.4 O custo de varredura

Cada candidato falso paga um `get_pixmap` dedicado, uma passada de `trim_to_grid`, outra de
`trim_to_frame`, um `detect_boards` de refino e uma inferência. Num livro de 1181 páginas isso
é ~6% de trabalho jogado fora — e a S-61 já tinha ido atrás de custo de varredura por menos.

---

## 5. O que testei e **não** funciona

Vale registrar, porque as duas ideias são as primeiras que ocorrem e as duas são armadilhas.

### 5.1 Um piso absoluto de `board_texture_score` — **não**

No livro do relato a separação parece perfeita, no recorte que o pipeline entrega:

| | n | mín | mediana | máx |
|---|---|---|---|---|
| glifos | 71 | 0,1059 | 0,2087 | **0,3827** |
| diagramas | 55 | **0,6562** | 0,7863 | 0,9558 |

Um corte em 0,45 mataria 71/71 glifos e 0/55 diagramas. Tentador — e **errado no acervo**. O
mesmo corte aplicado aos outros livros, sobre diagramas legítimos:

| livro | diagramas medidos | abaixo de 0,45 |
|---|---|---|
| `1001 Sacrifícios (pt-BR)` | 40 | **38** |
| `La Combinación En El Ajedrez` | 40 | **29** |
| `Karpov 1` | 217 | **51** |
| `GALLAGHER` | 11 | **9** |
| `AAGAARD` | 118 | 8 |
| `Kemeri` | 50 | 2 |

`board_texture_score` não é comparável entre livros: casa hachurada, meio-tom de scan e
qualidade de digitalização deslocam a escala inteira. O módulo `embedded.py` já registra isso
no próprio docstring — "0,3607 no recorte errado contra 0,3897 no certo: **0,03**, quase cego"
— e um piso absoluto seria repetir o erro numa casa decimal diferente.

**O que funciona é a mesma nota, mas relativa à página** (§6.3).

### 5.2 Apertar `MIN_EMBEDDED_SIDE` — **não**

Subir de 120 para 200 px nativos mataria o glifo *deste* livro e nada garante o próximo: um
ornamento gravado a 300 DPI tem 64 px, a 1200 DPI tem 256. A constante continuaria medindo a
unidade errada, só que com um número maior. É o tipo de correção que parece funcionar até o
livro seguinte.

---

## 6. O plano

Cinco entregas, em ordem de retorno por esforço. A primeira resolve o relato; as outras fecham
a classe de defeito que ele revelou.

---

### S-78 · O piso de tamanho em pontos, que é a unidade da pergunta ✅ implementada (2026-08-14)

**Problema.** `MIN_EMBEDDED_SIDE` mede resolução e o docstring promete tamanho. 71 falsos
positivos em 1181 páginas, com um vale de 110 pt entre as duas populações.

**Solução.** Uma segunda guarda em `candidates_from_embedded_images`, sobre o `bbox` que a
função já lê:

```python
MIN_EMBEDDED_SIDE_PT = 72.0
"""Lado mínimo do diagrama na página, em pontos. Uma polegada: oito filas de 9 pt.

Existe porque `MIN_EMBEDDED_SIDE` mede **pixels nativos**, que são resolução e não tamanho:
o glifo de cavalo do cabeçalho do `Secrets of Chess Training` tem 128 px nativos em 15,4 pt
de página -- 600 DPI de ornamento -- e passava por ele com folga, 71 vezes no livro.

Medido pelo censo da S-82 no acervo: os glifos vão de 15 a 50 pt e o menor diagrama real tem
105,6 pt (`Euwe Band 1-2`). Qualquer número entre 51 e 105 serve; 72 é o meio dessa faixa e
tem significado independente do acervo, o que o torna preferível a um valor ajustado à
amostra.

**O que ele não resolve:** os fragmentos do `GALLAGHER` chegam a 106,5 pt e encavalam o
diagrama real por 0,9 pt. Aquilo não é um problema de limiar e não tem limiar que resolva --
ver S-81.
"""
```

Manter `MIN_EMBEDDED_SIDE` como está — ele ainda serve, para outra coisa: barrar a imagem
grande na página mas pobre em pixels, que não tem resolução para ser lida.

**Critério de aceite.** No diff do `cvoff-census` contra `docs/metrics/deteccao_20260814.csv`:
todas as perdas abaixo de 72 pt e **zero** perdas acima. É a coluna `das quais acima do
limiar`, e é o que separa "removi o glifo" de "removi diagrama junto".

**Medido.** No livro do relato, 200 páginas: **7 perdas, todas suspeitas, 0 acima do limiar**.
Suspeitos 7 → 0, páginas com numeração deslocada 2 → 0, gabarito misturado 3 → 0. No acervo:
5 perdas, todas suspeitas, 0 acima do limiar — e **3 ganhos** no `GALLAGHER`, onde tirar
fragmentos liberou achados de contorno que eles suprimiam.

**Testes.** `tests/test_detection.py::MinimumSideInPointsTests`. O par que decide é a mesma
imagem de 128×128 nativos em dois retângulos: 15 pt não vira candidato, 154 pt vira.
`MIN_EMBEDDED_SIDE` vê 128 px nos dois e não tem como distingui-los. Nenhum teste fazia essa
distinção porque a fixture `pdf_with_images` sempre desenhou em retângulos grandes — é por isso
que 509 testes verdes não pegaram isto.

---

### S-79 · O gabarito de tamanho calculado sobre o que sobreviveu ✅ implementada (2026-08-14)

**Problema.** `expected_side` é a mediana de **todos** os candidatos embutidos. Um glifo na
lista desloca a mediana e o prior passa a recusar diagramas de verdade — 42 páginas.

**Solução.** Três mudanças, em `detection/hybrid.py`:

1. **`_typical_side` no lugar de `np.median`.** Mediana é robusta a *outlier*, não a
   *bimodalidade*: com um glifo de 15 pt e um diagrama de 154 pt ela dá ~85 pt, que não é o
   tamanho de nada naquela página — e a janela de ±30% vira 59–110 pt, recusando todo achado
   de contorno do tamanho real. A regra nova agrupa os lados pela mesma tolerância que filtra
   e toma o **maior grupo**, com empate resolvido pelo lado maior.
2. **A recusa por tamanho virou `logger.info`.** Era `debug`, e é a única evidência de que a
   guarda agiu. Com o gabarito envenenado, o sintoma era um diagrama que simplesmente não
   aparecia na tela — sem erro, sem log, sem nada a que voltar.
3. **União de ladrilhos não entra no gabarito** (veio junto com a S-81, mesma razão: união é
   inferência nossa, não declaração do PDF).

A S-78 tira o glifo da lista antes de ela chegar aqui, então o caso medido não se repete por
aquela porta. Esta entrega fecha a **classe**: qualquer página que misture dois tamanhos —
diagrama de destaque com diagramas de variante, capa de capítulo, fragmento — caía no mesmo
buraco, e nenhuma dessas some com um piso.

**Testes.** `tests/test_detection.py::TypicalSideTests`, 7 casos, incluindo o de ponta a ponta:
um achado de contorno do tamanho do diagrama tem de continuar dentro da janela numa página que
também tem glifo.

---

### S-80 · A nota de textura relativa à página ❌ **não implementada — a medição reprovou**

> **O alvo desta entrega existia.** Ela foi arquivada em parte por ter "zero instâncias
> confirmadas no acervo", e isso estava errado por um motivo que só a S-143 encontrou: o censo
> **não amostra as páginas onde o defeito mora**. Ver [S-143](#s-143--a-foto-quadrada-que-o-contorno-lê-como-tabuleiro).
> O que segue abaixo continua valendo inteiro — a *proposta* (textura relativa) segue reprovada,
> e é a S-143 que explica por que aquele número não podia funcionar.

**A proposta era.** S-78 é um piso de tamanho, e tamanho é um *proxy*: um ornamento grande —
capa de capítulo, selo, foto quadrada — passaria dos 72 pt e cairia no mesmo buraco. Como
§5.1 mostrou que um piso **absoluto** de `board_texture_score` não sobrevive ao acervo, a ideia
era usá-lo como número **relativo**: um candidato cuja nota fosse muito menor que a dos outros
da mesma página não seria diagrama. A escala do livro se cancelaria na razão.

**A medição.** Razão entre a nota do candidato e a mediana da sua página, sobre o censo do
acervo (`docs/metrics/deteccao_20260814.csv`, 1309 candidatos):

| corte | legítimos perdidos | suspeitos pegos |
|---|---|---|
| 0,40 | 4 / 1032 | **0** / 4 |
| 0,45 | 7 / 1032 | **0** / 4 |
| 0,50 | 12 / 1032 | 2 / 4 |
| 0,60 | 26 / 1032 | 2 / 4 |

Em **todo** ponto da curva a guarda perde mais do que pega. Não há corte que preste.

**E olhar as perdas a olho fecha o assunto.** As 12 do corte 0,50 são todas de contorno, com
nota entre 0,11 e 0,31. Recortei quatro delas:

| candidato | nota | o que é |
|---|---|---|
| `Polgar` p96 #0, 242 pt | 0,158 | **diagrama impecável** — posição de abertura, 28 peças |
| `Reinfeld` p39 #0, 116 pt | 0,269 | **diagrama impecável** |
| `Vishy Anand` p60 #2, 83 pt | 0,127 | lixo de verdade: bloco de texto deformado |
| `Karpov` p100 | — | o índice mudou com a S-78/S-79; não é mais o mesmo candidato |

**O mecanismo, que a S-38 já suspeitava e agora está nomeado.** `board_texture_score` soma
contraste entre casas e periodicidade de grade. Um tabuleiro **cheio de peças** tem as casas
cobertas, então o contraste desaba: a nota mede tanto **densidade de peças** quanto
"tabuleiridade". O diagrama do `Polgar` tira 0,158 por ser uma posição de abertura, e um final
de dois reis na mesma página tira 0,8. Isso acontece **dentro da mesma página e do mesmo
livro**, então a razão não cancela nada — a premissa da S-80 estava errada.

**Por que não entrou mesmo assim.** O alvo dela — o ornamento grande que passa dos 72 pt — tem
**zero instâncias confirmadas** no acervo. Trocar 12 perdas, das quais duas confirmadas como
diagramas perfeitos, por 2 capturas contra uma ameaça hipotética é exatamente a mudança não
medida que a S-82 existe para impedir. Fica registrada como reprovada, com o número.

**O que sobrou de aproveitável, e onde foi parar.** A comparação de textura **da mesma região
da mesma página** continua legítima — é o que a S-38 já fazia — e é ela que decide entre uma
união de ladrilhos e um achado de contorno sobreposto na S-81. O que não se pode é comparar
notas de recortes diferentes, de livros diferentes, ou contra um piso fixo.

**O caso do `Vishy Anand` p60 fica em aberto.** Ele é um falso positivo de contorno real —
texto deformado em quadrilátero. Não é a mesma classe de defeito deste documento e não tem
instrumento ainda; se virar item, é por conta própria e com medição própria.

---

### S-81 · A imagem embutida que é **pedaço** de diagrama ✅ implementada (2026-08-14)

**Problema.** Encontrado durante esta análise, num livro diferente. No `GALLAGHER - Winning
With the King's Gambit`, o PDF quebra um diagrama digitalizado em **vários XObjects de
imagem**, e cada pedaço que tenha ≥ 120 px nativos e aspecto quase quadrado entra como
candidato próprio. Amostra da página 137:

| nativo | na página | o que é |
|---|---|---|
| 336×304 | 101,8 × 92,4 pt | seis colunas de um tabuleiro, cortado |
| 176×160 | 53,4 × 48,6 pt | um canto |
| 224×128 | 67,6 × 39,2 pt | uma faixa |

Censo do livro inteiro (192 páginas): o caminho embutido entrega **40** candidatos, e a
distribuição os separa em dois grupos limpos — **33 fragmentos** de 38,8 a 106,5 pt e **7
scans inteiros** de 302 a 348 pt. Os 152 diagramas de verdade do livro chegam pelo contorno,
a 120 pt.

**Nenhum piso de tamanho resolve isto**, e é a S-82 que prova: o maior fragmento tem 106,5 pt
e o menor diagrama real do acervo tem 105,6 pt. As duas populações se sobrepõem. Por isso esta
entrega deixou de ser a mais dispensável das cinco.

**Solução, em quatro peças.** A primeira era o plano; as outras três a medição exigiu, uma de
cada vez, e cada uma corrigia um sintoma que a anterior tinha criado.

1. **`_merge_adjacent_tiles`** — antes de qualquer filtro, unir imagens embutidas que se
   **encostam** (folga de 2 pt) e tratar o grupo como um candidato só. A ordem das guardas
   passa a ser a decisão: cobertura de página primeiro (o scan de fundo encosta em tudo e
   colapsaria a página num grupo só — e o `Kemeri` tem scan de fundo **e** diagramas embutidos
   de verdade), agrupamento depois, tamanho e aspecto por último — porque um ladrilho de
   240×96 tem aspecto 2,5 e morreria antes de a união existir.

2. **A união não suprime achado de contorno sobreposto** (`_contour_wins_over_merged`). A
   imagem embutida é uma *declaração* do PDF e ganha do contorno desde a S-12; a união não é
   declaração nenhuma, é inferência nossa. Medido: nas páginas 168 e 169 ela produziu caixas
   de 91 pt com textura 0,34 e 0,11 que suprimiam contornos de 120 pt com textura 0,74 e
   0,69 — e na 169 engoliu **dois** diagramas bons. Quando é união, as duas fontes competem, e
   a comparação de textura é legítima aqui porque é **da mesma região da mesma página** — que é
   o que a S-38 já faz, e o que a S-80 não podia fazer.

3. **Contenção no lugar de IoU, só para união** (`_same_region`). Na p168 a união está **97%
   dentro** do achado de contorno e o IoU dá 0,41: a união é bem menor, e a diferença de área
   infla o denominador. IoU pergunta "as duas caixas são a mesma?"; ali a pergunta é "uma está
   dentro da outra?".

4. **A união não calibra o gabarito de tamanho** (S-79). Uma união de 91 px definia o gabarito
   da página, e o prior recusava por tamanho o diagrama de 120 px que o contorno tinha achado —
   **sem sobreposição entre os dois**, então a guarda de IoU nem chegava a opinar.

**E um defeito que só apareceu no livro real.** As peças 2 e 4 dependem de `merged_tiles`, e
`refine_candidate_with_contour` reconstruía o candidato **sem** esse campo. As regras estavam
escritas, os testes de unidade passavam, e no `GALLAGHER` nada mudava. Hoje há teste para a
proveniência sobreviver ao refino.

**Medido, `GALLAGHER` inteiro (192 páginas):**

| | antes | depois |
|---|---|---|
| candidatos | 194 | **200** |
| suspeitos (< 72 pt) | 22 | **1** |
| de imagem embutida | 40 | 25 |
| de contorno | 154 | **175** |

As 9 perdas acima do limiar foram conferidas **uma a uma**, e todas se justificam: cada página
trocou um fragmento de 72–87 pt (textura 0,21–0,35) por um ou dois diagramas de 120–130 pt
(textura 0,56–0,84).

---

### S-82 · O censo de candidatos, para que "melhorou" seja demonstrável ✅ implementada (2026-08-14)

**Problema.** Cada uma das quatro entregas acima muda o que o detector aceita, e nenhuma pode
ser confiada sem medir **os 27 PDFs**. O projeto tem essa disciplina para leitura
(`docs/BASELINE.md`, `cvoff-eval`) e não tem para **detecção**: hoje só se sabe se a detecção
piorou quando alguém vê um cavalo marcado na tela.

Foi assim que este defeito sobreviveu — ele é visível a olho nu em 71 páginas e nenhum número
o mostrava.

**Solução.** `cvoff-census` (`detection_census.py`), que varre um PDF ou o acervo e grava uma
linha por candidato: fonte, lado em pontos, tamanho nativo, se foi aparado, `detector_score`,
`board_texture_score` do recorte **entregue**, e o `bbox`.

```bash
cvoff-census --csv docs/metrics/deteccao_base.csv        # a linha de base
cvoff-census --pdf "PDF/..." --all-pages                 # um livro inteiro
cvoff-census --csv nova.csv --baseline base.csv --fail-on-loss
```

**Três decisões que o código tomou e que valem registro:**

1. **Sem modelo.** Nenhuma inferência, nenhum torch — 0,2 s de import contra ~8 s. Um censo
   caro é um censo que não se roda a cada mudança, e rodar a cada mudança é a única coisa que
   ele existe para ser. Custou mover `sample_pages` de `side_survey` (que importa
   `OcrService`) para `pdf_io`; ela segue reexportada pelo nome antigo.

2. **O diff casa por canto do `bbox`, não por índice.** Quando um falso positivo sai, o
   diagrama que era o #1 vira #0. Casar por índice leria uma remoção como remoção **mais**
   substituição — duas mudanças onde houve uma, e a errada em destaque.

   **E um segundo passe por sobreposição (`moved`), que a S-81 exigiu.** O canto é estável
   entre corridas que não mexem no recorte, e deixa de ser assim que uma entrega reajusta a
   caixa: o diff leu **26 "perdas acima do limiar"** no `GALLAGHER` onde havia um diagrama por
   página, reajustado. Um instrumento que grita perda a cada reajuste é um instrumento que
   ninguém olha na terceira vez. Com o passe, as 26 caíram para 8 — e depois para as 9 finais,
   todas justificadas.

3. **`suspect_below_pt` é lente, não filtro.** O suspeito continua contado em tudo o mais. O
   censo não decide onde cortar; ele mostra a distribuição para que a S-78 decida.

Além do histograma, três contagens que são o motivo de isto não ser um `wc -l`:
`suspects`, `pages_numbering_shifted` (§4.1) e `pages_size_prior_mixed` (§4.2).

**A linha que decide um diff é `das quais acima do limiar`.** Perder suspeito é o objetivo;
perder candidato do tamanho de um diagrama impresso precisa de justificativa um por um. O
censo não sabe o que é diagrama — não há rótulo humano de detecção no acervo — e por isso não
aprova nada sozinho. Ele diz onde olhar.

**Testes.** `tests/test_detection_census.py`, 20 casos. As três contagens são testadas sobre
`CandidateRow` montado à mão, **sem** passar pelo detector: se elas dependessem de o detector
aceitar um glifo, a S-78 as quebraria ao corrigir exatamente isso — e um instrumento que
quebra quando o defeito é corrigido não serve para medir a correção.

**Linha de base gravada.** `docs/metrics/deteccao_20260814.csv` e `.json` (acervo, 24 páginas
por livro) e `docs/metrics/deteccao_secrets.csv` (o livro do relato, 200 páginas). É contra
elas que S-78 a S-81 foram medidas.

> O nome era `deteccao_base` até a S-143, que gravou uma linha de base nova sobre aquele nome
> -- acervo maior (39 livros) e com as páginas de frente. As afirmações desta seção e das
> S-78 a S-82 continuam apontando para o arquivo datado, que é o que elas mediram.

---

### S-143 · A foto quadrada que o contorno lê como tabuleiro ✅ implementada (2026-08-17)

> Relato do usuário: *"o OCR está muito preciso nos diagramas mas ainda tem uns falso diagramas
> como na página 0 e 6"* — `Karpov A - Chess Combinations -World Champions-1 (2011).pdf`.

**O que acontecia.** Dez caixas em duas páginas que não têm diagrama nenhum:

| página | o que virava "diagrama" |
|---|---|
| 1 (capa) | o título `CHESS`, a grade de 9 fotos dos campeões, e 4 retratos isolados |
| 7 (prancha do Steinitz) | 3 casas do **tabuleiro pintado ao fundo do quadro**, e a moldura inteira |

Todas de **contorno**; nenhuma de imagem embutida. É exatamente o alvo que a S-80 descreveu —
"um ornamento grande — capa de capítulo, selo, **foto quadrada**" — e deu como inexistente.

#### 1. Por que ninguém tinha visto: o censo não olha para lá

`sample_pages` descarta as bordas do livro **de propósito**, e a razão está escrita nela:

> *"a primeira e a última página de um livro de xadrez são capa, índice ou catálogo, e
> gastá-las é gastar dois doze avos da amostra em páginas que nunca têm diagrama."*

O raciocínio está certo para *achar diagrama* e é exatamente errado para *achar falso
positivo*: capa, folha de rosto e prancha são **onde o ornamento grande mora**. A S-80
concluiu "zero instâncias confirmadas no acervo" a partir de uma amostra que não podia contê-las,
e arquivou a entrega. Quem achou as instâncias foi o usuário, abrindo o PDF.

Corrigido: `DEFAULT_FRONT_MATTER = 8` e `cvoff-census --front-matter N`. Medido depois, a faixa
tem 121 candidatos de contorno no acervo, e **90 deles não têm contraste de casa nenhum**.

#### 2. Três sinais que pareciam resolver e não sobrevivem ao acervo

Registrados porque cada um passa no `Karpov 1` e morre adiante — e porque a diferença entre
eles e o que ficou é a única coisa que importa aqui.

| sinal | onde morre |
|---|---|
| **tom médio** (foto tem meio-tom, diagrama é tinta e papel) | o scan velho é cinza: perde 169 de 707 candidatos de contorno para pegar 7 de 10. `Koblenz`, `Levenfis` e `Gunderam` inteiros |
| **nitidez local** (foto é suave, traço é duro) | **depende do DPI de render**. A 110 DPI o `Kmoch` de verdade cai a 5,43 e a foto do `Kemeri` sobe a 8,58: o vale **inverte** |
| **rede 8×8 auto-normalizada** (energia de borda na grade / total) | não separa: diagramas reais dão 0,86–1,12 e as fotos 0,90–1,12 |

O padrão é o mesmo da §5.1: **piso fotométrico absoluto não sobrevive a um acervo que vai de
gravura de 1870 a PDF vetorial**, e nitidez ainda por cima depende de um parâmetro que quem
chama escolhe.

#### 3. O que ficou: a parcela de xadrez, sozinha

`board_texture_score` é `0,6·xadrez + 0,4·grade`, e as duas parcelas respondem perguntas
diferentes:

- **grade** — borda que se repete a cada 1/8. Moldura de quadro, faixa de retratos e fachada
  fazem isso muito bem: medido, as fotos do relato tiram **0,04 a 0,80** nela.
- **xadrez** — as 32 casas de uma paridade sistematicamente mais claras que as 32 da outra,
  num reticulado alinhado com o recorte. **Não há como imitar sem ser um tabuleiro.**

Misturar as duas foi o que condenou a S-80: ela mediu 0,29 numa foto contra 0,158 num `Polgar`
impecável, e concluiu — corretamente, para o número que estava olhando — que não havia corte
que prestasse. O número errado não era o corte, era a nota.

Medido, com o `clip` em 0 mordendo onde não há tabuleiro:

| população | com xadrez **exatamente zero** |
|---|---|
| os 10 do relato | **10 de 10** |
| contorno na frente do livro (capa, rosto, prancha) | 90 de 121 |
| contorno na amostra do censo | 21 de 841 |

**Zero não é ajuste à amostra:** é onde a comparação sinal-contra-ruído troca de sinal
(`contraste·2,4 ≤ dispersão·0,9`). O candidato legítimo mais próximo é um `Polgar` de **0,0616**
— posição de abertura, 28 peças, o caso que derruba esta parcela — então qualquer valor em
(0; 0,06) se comportaria igual no acervo. Zero é o que tem significado independente dele.

#### 4. O critério de aceite, e por que não é o diff do censo

Contar candidatos não responde a pergunta: os 21 do censo *parecem* perda. Doze deles são
`Reinfeld` e, a olho, são diagramas perfeitos. Então a medição foi outra — **rodar o OCR de
verdade em todo candidato de contorno do acervo** e perguntar se algum dos removidos entregava
leitura aproveitável:

| | n | confiança mediana | máxima | ≥ gate de exportação (0,80) |
|---|---|---|---|---|
| **removidos pela guarda** | 132 | 0,0197 | **0,5299** | **0** |
| mantidos | 988 | 0,9998 | 1,0000 | 728 |

**Nenhum recorte removido lia acima do gate.** Os 12 do `Reinfeld` são os da **coluna
esquerda**, que o contorno fecha em 101×116 pt em vez de 116×116 — tabuleiro cortado, que o
warp estica e desalinha. Eles leem 0,0001 a 0,41; os gêmeos bem recortados da mesma página, na
coluna direita, leem 0,998 e acima. A guarda os remove porque o recorte é defeituoso, não
apesar disso.

> Fica em aberto, e é outro item: **por que o contorno corta a coluna esquerda do `Reinfeld`.**
> A guarda esconde o sintoma (o recorte ruim some da tela); ela não conserta o recorte. Aqueles
> 3 diagramas por página continuam não sendo detectados naquele livro.
>
> Fechado pela [S-175](#s-175--a-quina-que-a-rasterização-não-liga-e-o-tabuleiro-que-sai-pela-metade).
> A causa não era do livro nem da coluna: era a **fase sub-pixel** da grade contra a malha de
> pixels do render, e o remédio é um terceiro passe de limiar. Depois dela aqueles 3 por página
> saem 116×116 e leem 1,0000 — e não chegam mais a esta guarda.

#### 5. Onde a guarda **não** vale

Só o caminho de contorno. Imagem embutida é *declaração* do PDF e continua ganhando (S-12);
os 3 embutidos com xadrez zero no acervo ficam de fora de propósito. E ela roda **antes** de
tudo no laço: um retrato não pode derrubar uma união de ladrilhos em `_contour_wins_over_merged`
nem envenenar o gabarito de tamanho. Guarda que julga o que a coisa **é** vem antes de guarda
que julga com quem ela compete.

**Testes.** `tests/test_detection.py::CheckerContrastGuardTests`, 7 casos. Dois deles são o
registro da lição: `test_tabuleiro_cheio_de_pecas_sobrevive` é o caso `Polgar` que reprovou a
S-80, e `test_a_parcela_de_grade_sozinha_nao_separaria` prende no lugar o motivo de a guarda
não usar a textura combinada — a fixture de foto **tem** borda periódica e **não** tem
contraste de casa.

#### 6. O censo do acervo, depois

Duas corridas. A primeira com `--front-matter 0`, para bater com a amostragem da linha de base
de 2026-08-14 e isolar o efeito da guarda — **31 livros em comum**, porque o acervo cresceu 8
livros desde então e contá-los como ganho esconderia o que interessa:

| | |
|---|---|
| candidatos | 1307 → **1265** (−42) |
| livros com mudança | **5 de 31** (26 saíram idênticos) |
| perdas | 42, das quais **41 acima do limiar** |
| ganhos / reajustados | 0 / 0 |

**E é aqui que o censo sozinho não decide.** Quarenta e uma perdas "acima do limiar" é
exatamente a linha que a S-82 diz exigir justificativa uma a uma — e a justificativa não está
no censo, porque ele não sabe o que é diagrama. Está na leitura: cruzadas com a varredura de
confiança, **as 42 liam abaixo do gate de exportação**, a maior delas 0,5299.

| livro | perdas | o que eram | leitura |
|---|---|---|---|
| `Vishy Anand` | 21 | texto e fragmentos torcidos em quadrilátero | 0,0000 – 0,2282 |
| `Reinfeld` | 12 | os recortes cortados da coluna esquerda | 0,0001 – 0,4125 |
| `1937 Kemeri` | 4 | fotografias de torneio | 0,0197 – 0,1460 |
| `Karpov 2` | 4 | diagramas warpados em losango | 0,0004 – 0,5299 |
| `Koblenz` | 1 | — | 0,0479 |

As 21 do `Vishy Anand` incluem o caso que a S-80 deixou registrado como *"falso positivo de
contorno real, não é a mesma classe de defeito e não tem instrumento ainda"*. Tem agora.

A segunda corrida é o padrão novo, com as páginas de frente: **39 livros, 1520 candidatos**
(988 de contorno, 532 de imagem embutida), **+52 e nenhuma perda** contra a primeira. Suspeitos
0, numeração deslocada 0, gabarito misturado 0. Os +52 são diagrama de verdade nas 8 primeiras
páginas, que a amostragem nunca tinha visto — no livro do relato, as páginas 1 e 7 ficam com
**zero** candidatos e os 6 ganhos são todos da página 8, imagem embutida, textura 0,43 a 0,63.

**Linha de base nova:** `docs/metrics/deteccao_20260817_s143.csv` e `.json` (39 livros, 24
páginas por livro mais 8 de frente; 1520 candidatos). A de 2026-08-14 fica em
`docs/metrics/deteccao_20260814.csv`, que é o que as S-78 a S-82 mediram. Ela **deixou** de ser
`deteccao_base` na S-175 — ver [o que a S-160 tinha deslocado sem
remedir](#0-a-linha-de-base-do-disco-não-reproduzia-o-programa-do-disco).

---

### S-175 · A quina que a rasterização não liga, e o tabuleiro que sai pela metade ✅ implementada (2026-08-20)

> Item deixado em aberto pela [S-143](#4-o-critério-de-aceite-e-por-que-não-é-o-diff-do-censo):
> *"por que o contorno corta a coluna esquerda do `Reinfeld`."*

#### 0. A linha de base do disco não reproduzia o programa do disco

Antes de medir qualquer coisa, o "antes" precisou ser medido, e não lido de arquivo. Rodando o
censo na árvore de `0978c0d` (a S-160, o commit imediatamente anterior a esta entrega) contra o
`deteccao_base.csv` que estava versionado:

| | |
|---|---|
| candidatos no arquivo | 1520 |
| candidatos que o mesmo comando entrega hoje | **1525** |
| diferença | +5 ganhos, 0 perdas, **85 caixas reajustadas** |

Os +5 são 4 no `Karpov 2` e 1 no `Estrin`, e são o efeito da própria S-160: mover o piso de
contraste para antes da supressão por IoU devolveu o diagrama que um borrão sem xadrez
suprimia. **A S-160 mudou o recorte do acervo e não regravou a linha de base**, então o arquivo
descrevia um programa que não existia mais — e um diff contra ele teria creditado à S-175
ganhos que não são dela.

Por isso esta entrega arquiva **duas** corridas em vez de uma: `deteccao_20260817_s143.*` (o
arquivo antigo, medido antes da S-160) e `deteccao_20260820_s160.*` (a árvore de `0978c0d`,
que é contra o que os números abaixo foram medidos).

#### 1. A causa: o tabuleiro só é *uma* mancha por causa das quinas

As casas escuras de um diagrama impresso são de uma paridade só, e **duas casas da mesma
paridade encostam apenas pela quina**. É por esses 49 pontos, e só por eles, que a tinta do
tabuleiro forma uma única componente 8-conexa — que é exatamente o que este módulo assume ao
tomar a extensão do contorno pela extensão do tabuleiro.

Se um contato de quina não sobrevive à rasterização, a corrente parte e o contorno fecha um
pedaço do tabuleiro. **E não parte uma quina de cada vez:** os 7 contatos de uma mesma linha
vertical da grade caem no **mesmo x**, dividem a mesma fase sub-pixel e morrem juntos. O que
sai é um quad com uma fileira a menos — 7/8 exatos do tabuleiro.

Medido no `Reinfeld_1001_Sacrificios_y_Combinaciones_Brillantes_1977.pdf`, página 141
(0-based), a 220 DPI: a coluna esquerda fecha em 101×116 pt contra 116×116 na direita. Em
pixels o contorno vai de x=99 a x=410 e a borda direita do tabuleiro está em x=454 — 311 px de
355, que é 7 casas de 8.

#### 2. Desde a S-160 o sintoma não era recorte torto: eram três diagramas a menos

Este é o ponto em que o relato da S-143 envelheceu, e vale dizê-lo em voz alta. Um tabuleiro
cortado em 7/8 e esticado pelo warp perde o reticulado 8×8, então o **contraste de casa dele é
exatamente 0,0000** — e o piso da S-143, que a S-160 mudou de lugar para antes da disputa, o
mata. Medido na mesma página 141, na árvore de `0978c0d`:

| candidato | caixa | score | contraste | o que acontece |
|---|---|---|---|---|
| coluna direita, 3× | 116×116 pt | — | — | sai, e lê 0,9999 a 1,0000 |
| coluna esquerda, 3× | 101×116 pt | 0,2798 a 0,2971 | **0,0000** | recusado como `sem-contraste-de-casa` |

`recognize_page` devolvia **3** dos 6 diagramas da página, sem uma linha na tela dizendo que
havia mais. A guarda estava certa — aquele recorte não é tabuleiro —, e é exatamente o que a
S-143 registrou como pendência: *"a guarda esconde o sintoma; ela não conserta o recorte"*.

#### 3. A prova de que é fase, e não o livro

A mesma página, o mesmo arquivo, só mudando o DPI do render, na árvore de `0978c0d`:

| DPI | coluna esquerda | coluna direita |
|---|---|---|
| 150 | **nada** | 118×106 |
| 180 | **nada** | 116×116 |
| **220** (o padrão) | **nada** | 116×116 |
| 240 | 116×116 | 116×116 |
| 260, 300, 400 | 116×116 | 116×116 |

Nada no PDF muda entre essas corridas. A partir de 240 DPI a coluna esquerda sai inteira **sem
reparo nenhum**; abaixo disso ela não sai. Não é uma propriedade daquela coluna nem daquele
livro: é de onde a grade cai em relação à malha de pixels — e por isso o mesmo defeito espera
em qualquer livro cujo diagrama caia na fase errada, que é o que o censo confirmou adiante.

#### 4. Por que o fechamento reto não repara, e o que repara

`MORPH_CLOSE` é dilatação seguida de erosão. Com o elemento quadrado 3×3 a dilatação atravessa
a quina, mas o pescoço que ela cria tem a largura de um pixel e a erosão com o **mesmo**
elemento o corta de volta. Fechar ao longo da **diagonal** sobrevive, porque ali a erosão corre
na direção da ponte e não contra ela.

Medido na unidade do defeito — duas casas afastadas por 1 px na quina:

| operação | componentes 8-conexas |
|---|---|
| cru | 2 |
| fechamento reto 3×3 | **2** |
| fechamento nas duas diagonais | **1** |

Dilatar repararia a quina do mesmo jeito e foi **recusado pela caixa**: entrega 117×117 onde o
tabuleiro mede 116×116, o que deslocaria toda caixa de contorno do acervo em ~1 pt e encheria o
diff do censo de ruído. O fechamento devolve a forma ao tamanho original —
`test_o_reparo_nao_engorda_a_caixa` prende isso.

#### 5. Três passes, e não uma imagem mais ligada

A entrega são **três binarizações**, cada uma contribuindo a sua lista de contornos: o cru, o
fechamento reto (intocado desde o commit inicial) e o reparo de quina.

Unir o fechamento reto ao reparo numa imagem só economiza um `findContours` e **tira
candidato**. O argumento de que a união "só pode ligar mais" é verdade sobre **conexidade** e
falso sobre **candidatos**: fundir duas componentes remove as duas da lista de contornos e põe
a fundida no lugar. Onde o contorno **justo** era o bom, ele deixa de existir — e o
`Gaprindashvili` é o livro em que isso custa caro, porque cada diagrama dele fecha dois
contornos:

| contorno | lado | o que ele é |
|---|---|---|
| justo | 112 pt | a borda da grade — o tabuleiro |
| largo | 116 pt | a moldura impressa em volta, que tira a grade 8×8 de registro |

**Medido nos dois desenhos**, sobre as 13 páginas que o censo amostra daquele livro, com o
modelo de produção em todo candidato de contorno:

| desenho | candidatos | acima do gate de 0,80 |
|---|---|---|
| três passes separados (o entregue) | 68 | **59** |
| reto e reparo fundidos numa imagem | 68 | 56 |

**A contagem não muda; muda qual dos dois contornos sobra.** Nas páginas 35, 69 e 92 o
candidato de 112 pt que lia 1,0000 / 0,9999 / 0,9998 é substituído pelo de 116 pt, que lê
**0,2973 / 0,2897 / 0,0608** — abaixo do gate. Foi por isso que o censo sozinho não bastava
para decidir o desenho: ele marcaria essas três como *reajustadas*, porque a caixa continua
lá, com outro tamanho.

Com os passes separados aquele livro sai **idêntico** ao de antes e nem aparece no diff do
censo. `test_o_fechamento_reto_continua_sendo_um_passe_proprio` afirma que `_threshold_passes`
devolve três imagens e que a segunda é o fechamento reto **byte a byte** — é a lição encravada,
e não um teste de forma.

**O que o terceiro passe custa**, medido em `_extract_candidate_quads` sobre 8 páginas já
renderizadas (render e modelo de fora, porque não é neles que a mudança mexe), mediana de 24
corridas: **61,6 → 95,0 ms por página, +54%.** O gasto está em avaliar mais candidato — um
`warp` de 320 px e uma nota de textura por achado —, e não em binarizar mais uma vez. É o preço
de não trocar um recorte bom por um ruim, e ele aparece na varredura de livro, não no clique.

#### 6. Medido: o censo do acervo

39 livros, 24 páginas amostradas por livro mais 8 de frente, contra
`docs/metrics/deteccao_20260820_s160.csv`:

| | |
|---|---|
| candidatos | 1525 → **1555** (+30) |
| de contorno | 993 → **1023** |
| de imagem embutida | 532 → 532 (intocado) |
| ganhos | **30** |
| **perdas** | **0** (e 0 acima do limiar de suspeita) |
| reajustados (mesma caixa, outro tamanho) | 61 |
| suspeitos (< 72 pt) | 0 → **0** |
| numeração deslocada / gabarito misturado | 0 / 0 → **0 / 0** |

Os ganhos, por livro:

| livro | + | ~ | o que eram |
|---|---|---|---|
| `Niemeijer` | 16 | 4 | diagramas de um scan de 1945 cuja grade cai na fase ruim |
| `Reinfeld` | 13 | 3 | **os três por página da coluna esquerda** — o relato |
| `Koblenz` | 1 | 12 | idem, num livro em que o reajuste é o efeito dominante |

Os outros nove livros do diff aparecem **só com reajuste**: caixa que cresceu para o tamanho
certo sem trocar de identidade. É o efeito esperado de remendar quinas, e é o motivo de a
dilatação ter sido recusada — com ela os 1023 candidatos de contorno se moveriam, e não 61.

**Linha de base nova:** `docs/metrics/deteccao_base.csv` e `.json` (39 livros, 1555
candidatos).

#### 7. Medido: a leitura, que é o que o censo não responde

O censo conta caixa. Uma caixa **reajustada** continua lá com outro tamanho, e o censo não tem
como dizer que ela deixou de ser legível — foi exatamente essa cegueira que quase aprovou os
passes fundidos do §5. A régua que decide é o modelo de produção lendo **todo candidato de
contorno da mesma amostra**, nas duas árvores, casados por página e sobreposição:

| | antes (`0978c0d`) | depois |
|---|---|---|
| candidatos de contorno | 993 | **1023** |
| acima do gate de exportação (0,80) | 745 | **769** |
| casados entre as duas corridas | — | 993 |
| **sumiram** | — | **0** |
| passaram a ler **acima** do gate | — | 12 |
| passaram a ler **abaixo** do gate | — | **1** |
| surgiram | — | 30, dos quais **13** leem acima do gate |

Os 993 casam **todos**: nenhum candidato do programa anterior deixou de existir. Os 13 ganhos
acima do gate são os do `Reinfeld` — os três por página da coluna esquerda, em 13 das páginas
amostradas. Os 16 do `Niemeijer` e o 1 do `Koblenz` são diagramas de verdade num scan de 1945 e
num de 1978 que entram no censo e continuam **abaixo** do gate, como já estavam os vizinhos
deles naqueles livros: o reparo os torna visíveis, não legíveis.

**O único que piorou, nomeado.** `Euwe, Kramer - Das Mittelspiel Band 7 (1958).pdf`, página 49:
o contorno fecha 146,2×145,9 pt onde antes fechava 149,8×149,2, e a leitura cai de **0,8655
para 0,6399**. É um recorte *mais justo* que corta ~3,6 pt do tabuleiro, e é o preço desta
entrega — um diagrama em 993, contra 12 que subiram e 13 que apareceram acima do gate. Fica
registrado com nome e número porque a regra da S-82 é essa: candidato do tamanho de um diagrama
impresso que muda para pior precisa de justificativa, e a justificativa aqui é o saldo, não a
ausência de custo.

**Testes.** `tests/test_board_detection.py::DiagonalContactRepairTests`, 6 casos. Três deles são
o registro da lição: `test_fechamento_reto_nao_liga_a_quina_e_o_reparo_liga` prende a razão de o
passe existir, `test_o_fechamento_reto_continua_sendo_um_passe_proprio` prende a razão de serem
três imagens e não uma, e `test_sem_o_reparo_a_pagina_e_so_manchas_soltas` fixa o que o passe
base sozinho enxerga — sem ele, o teste do tabuleiro inteiro não provaria nada. Conferido
revertendo `_threshold_passes` para as duas passadas anteriores: a página de quinas partidas
devolve **zero** tabuleiros.

---

### S-176 · A faixa da página que passa por diagrama porque saiu quadrada ✅ implementada (2026-08-22)

> Relatado da tela: *"A página 14 do `Yusupov Artur. Build Up Your Chess (all volumes).pdf`
> criou um box equivocado."*

#### 1. O que a página desenhava

Página de índice 14 (a 15ª do arquivo, impressa como 11), a 220 DPI, na árvore de `49a83a6`:

| # | fonte | caixa | o que é |
|---|---|---|---|
| 1 | embutida | **460×403 pt** em `(-9, 12)` | o topo inteiro da página: título, dois parágrafos, dois cabeçalhos de partida **e os diagramas 1‑9 e 1‑10** |
| 2 | embutida | 150×169 pt em `(278, 438)` | o diagrama 1‑11 — correto |

A página tem **três** diagramas e mede 453,6×666 pt. A caixa 1 é mais larga que a página.

#### 2. A causa de entrada: as duas guardas da fonte embutida são sobre *forma*

Este livro é híbrido — texto de verdade mais imagens —, e o produtor do PDF **rasterizou
faixas inteiras da página** onde havia algo que a fonte não desenha: as tarjas de vídeo
reverso do cabeçalho de partida (`M.Gerusel – G.Sosonko`). A faixa não é um diagrama; é um
pedaço de página em bitmap que por acaso contém dois.

`candidates_from_embedded_images` tem duas guardas de entrada, e **as duas são sobre a forma
do retângulo**:

| guarda | limite | a faixa desta página |
|---|---|---|
| `ASPECT_TOLERANCE` | 1,00 ± 0,20 | **1,140** — passa |
| `MAX_PAGE_COVERAGE` | 0,70 da página | **0,614** — passa |

E a prova de que é acidente e não propriedade do livro está nas páginas vizinhas, onde a mesma
faixa existe e morre:

| página | faixa | aspecto | o que acontece |
|---|---|---|---|
| 13 | 452×203 pt | 2,222 | recusada em `ASPECT_TOLERANCE` |
| **14** | **460×403 pt** | **1,140** | **passa** |
| 15 | 452×61 pt | 7,359 | recusada em `ASPECT_TOLERANCE` |

Ou seja: a guarda que segurava esta classe inteira segurava por um sinal que não fala dela. Na
página em que a faixa saiu quase quadrada, não havia guarda nenhuma.

#### 3. O dano não parava na caixa absurda: ele comia os outros dois diagramas

Esta é a metade que não se vê na tela. O contorno **tinha achado** os diagramas 1‑9 e 1‑10, e
eles foram descartados por `prior-de-tamanho`:

| candidato de contorno | lado | destino |
|---|---|---|
| diagrama 1‑9 | 423 px | `prior-de-tamanho` |
| diagrama 1‑10 | 417 px | `prior-de-tamanho` |

Porque `_typical_side` recebeu `[516, 1405]` — o diagrama 1‑11 e a faixa —, não conseguiu
agrupá-los (a distância é 172% do menor, contra os 30% de `EMBEDDED_SIZE_TOLERANCE`), e o
desempate da [S-79](#s-79--o-gabarito-de-tamanho-calculado-sobre-o-que-sobreviveu) é **pelo
maior**. O gabarito da página virou 1405 px, e tudo do tamanho de um diagrama real caiu fora
da janela.

A S-79 fechou a classe "página com duas populações de tamanho" contra um **glifo de
cabeçalho**, onde escolher o maior é certo. Contra uma **faixa**, escolher o maior é escolher
justamente o que não é diagrama. A regra do desempate continua certa; o que faltava é a faixa
não chegar até ela.

#### 4. O sinal que **não** serve: contraste de casa

A tentação era estender à fonte embutida o piso da
[S-143](#s-143--a-foto-quadrada-que-o-contorno-lê-como-tabuleiro) — a faixa dá
`board_checker_score` **0,0000**, e o diagrama 1‑11 da mesma página dá 0,3982.

**Medido no acervo, e reprova.** 1287 candidatos embutidos, 40 páginas amostradas por livro:

| população | quantos |
|---|---|
| contraste > 0 | 1263 |
| **contraste == 0** | **24** |

E os 24 não são faixas. **Dez deles são diagramas impecáveis do `Schiller`** — hachurados,
com duas linhas de legenda acima do tabuleiro no recorte embutido. Grade fora de registro dá
zero pelo mesmo motivo que ausência de tabuleiro dá zero, e a nota não distingue os dois casos.

É a **terceira** vez que este projeto tenta julgar recorte embutido por uma nota absoluta e a
medição reprova — ver a [S-80](#s-80--a-nota-de-textura-relativa-à-página) e as três guardas
que calaram no docstring de `detection/embedded.py`. Fica valendo: nota absoluta sobre recorte
embutido não separa "não é tabuleiro" de "está desalinhado".

#### 5. O sinal que serve é geométrico, e é uma relação e não uma nota

**Um diagrama contém um tabuleiro que o preenche; uma faixa contém um tabuleiro que é um
pedaço dela.** É uma pergunta sobre a razão entre dois objetos, e não sobre o valor de um.

Medido nos **837** candidatos embutidos do acervo em que o contorno acha algum tabuleiro
dentro do bbox, tomando `lado do tabuleiro / lado da região`:

| percentil | 0 | 0,5 | 1 | 5 | 25 | 50 | 75 |
|---|---|---|---|---|---|---|---|
| `board_fill` | 0,1083 | 0,3355 | **0,7076** | 0,7740 | 0,8396 | 0,8662 | 0,9075 |

Duas populações e um vão de **0,33** entre elas: 831 candidatos de 0,7076 a 0,9829, e 6 de
0,1083 a 0,3758. Qualquer corte em (0,38; 0,70) se comporta igual no acervo inteiro.
`BAND_BOARD_FILL` é **0,50**, que tem significado próprio: abaixo dele a imagem é mais longa
que dois tabuleiros, ou seja, tem espaço para outra coisa que não é o diagrama.

#### 6. E os 6 de baixo não são todos faixa — a segunda condição, que o acervo cobrou

**Esta seção começou como um refinamento e virou uma correção.** A primeira versão da guarda
era só o preenchimento, e o acervo a reprovou: 24 páginas por livro, 1483 candidatos → 1478,
**5 perdas e nenhum ganho**. As páginas em que ela ganha não caíram na amostra; as em que ela
perde, sim.

Conferidos um a um, com o quad desenhado sobre a região:

| livro, página | `board_fill` | contraste do achado | o que é |
|---|---|---|---|
| `1001_Winning ... _hq` p812 | 0,1083 | **0,0002** | **diagrama inteiro**; o contorno prendeu **uma casa** |
| `La_Combinacion` p24 | 0,1140 | **0,0061** | idem |
| `Yusupov` p14 | 0,3051 | 0,2608 | faixa — o relato |
| `Yusupov` p1950 | 0,3104 | 0,3110 | faixa |
| `Yusupov` p1820 | 0,3133 | 0,4133 | faixa |
| `GALLAGHER` p140 | 0,3355 | 0,7408 | faixa |
| `GALLAGHER` p124 | 0,3758 | 0,7058 | faixa |

Preenchimento baixo tem **duas** causas, e só uma delas é faixa. A outra é o contorno se
prender a **uma casa** do próprio diagrama — e o preenchimento delas o diz: 0,108 a 0,128 é
1/8, que é quanto uma casa ocupa de um tabuleiro de oito.

Varrendo o `1001_Winning ... _hq` de três em três páginas (374 de 1121) saem **24** desses, e
mais o do `La_Combinacion` — 25 casos reais, todos diagrama legítimo:

| população, `board_fill` < 0,50 | quantos | contraste do achado |
|---|---|---|
| casa do próprio diagrama | 25 | **0,0000 a 0,0061** |
| faixa de página | 17 | **0,1310 a 0,7408** |

Vão de **fator 21**. `BAND_BOARD_CHECKER` é **0,06**: dez vezes acima do maior ruído, duas
vezes abaixo do menor sinal. As faixas incluem as 12 do `Yusupov` que a §8 audita — a de
contraste 0,1310 é a mais fraca do acervo e é o que aperta a margem inferior.

**E não é o piso da S-143 — reusá-lo *foi* o defeito.** `MIN_CHECKER_CONTRAST` é 0,0, e
0,0061 > 0,0: eram exatamente essas as 5 perdas. Os dois pisos respondem perguntas diferentes,
e a diferença é o que está do outro lado. Lá a alternativa é uma **foto**, que dá zero exato
porque não há estrutura nenhuma; aqui é um **pedaço de tabuleiro**, que dá quase zero porque a
estrutura existe e o recorte não a contém. Nem vale generalizar 0,06 de volta: nesta mesma
medição, **21 dos 831** tabuleiros que preenchem o próprio bbox ficam abaixo de 0,06 e são
todos legítimos — eles só não são alcançados porque a primeira condição já os isentou.

Então a guarda é um **par**, e as duas metades vêm de medições diferentes: uma separou faixa de
diagrama, a outra separou faixa de pedaço-de-diagrama.

O contraste volta a ser usado aqui, depois de §4 tê-lo reprovado — e não é contradição. Em §4
ele julgaria **o candidato embutido**, que pode estar desalinhado; aqui ele julga **o achado
de contorno**, que por construção já está alinhado à grade que ele mesmo encontrou. É a mesma
distinção que faz o piso da S-143 valer no caminho de contorno e não no embutido.

**O erro é conservador de propósito.** Uma faixa cujo tabuleiro interno tenha contraste muito
baixo sobrevive à guarda, e volta a ser o defeito do relato naquela página. É a direção certa
de errar: na dúvida, a declaração do PDF fica de pé, que é a regra desde a S-12.

#### 7. Uma passada, dois consumidores

`refine_candidate_with_contour` já rodava `detect_boards` dentro do bbox de cada candidato
embutido desde a S-12 — e **descartava o quad**, usando só o recorte. É o mesmo achado que
responde as duas perguntas: *onde está a grade* (o refino) e *o que esta imagem é* (a faixa).

Por isso a passada saiu para `contour_inside_candidate`, que devolve região, recorte e quad, e
`detect_diagrams` a chama **uma vez** por candidato. Medir duas vezes custaria um `get_pixmap`
e um `detect_boards` a mais por imagem embutida, em toda página de todo livro exportado —
`test_o_contorno_dentro_do_bbox_e_medido_uma_vez_so` prende isso.

#### 8. O resultado, na página do relato

| | antes | depois |
|---|---|---|
| caixas na tela | 2 | **3** |
| caixa que cobre texto e dois diagramas | 1 | **0** |
| diagramas 1‑9 e 1‑10 | ausentes | **presentes**, 138×138 e 137×137 pt |

**E no livro inteiro, auditado caixa a caixa.** 373 páginas amostradas (uma em cada sete das
2612), com e sem a guarda, comparando as caixas e não só a contagem:

| | |
|---|---|
| candidatos | 752 → **760** |
| páginas que mudaram | 12 |
| caixas que **sumiram** | 12 — e **as 12 são faixa**, de 408×387 a 460×403 pt |
| caixas que **apareceram** | 20 — todas de 136 a 142 pt, que é o tamanho de diagrama deste livro |

Nenhuma remoção pegou outra coisa que não uma faixa, e é essa a afirmação que interessa: a
contagem sozinha esconderia uma troca. Em duas das 12 páginas o saldo é **negativo** (7 → 6) e
está certo — ali os quatro diagramas já estavam sendo achados pelo contorno, e o que saiu foi
só a faixa que se somava a eles.

Uma das 12 faixas tem contraste **0,1310**, a mais fraca do acervo; é ela que define a margem
inferior de `BAND_BOARD_CHECKER` citada em §6.

**E o resto do acervo não sentiu nada.** 32 livros, 24 páginas por livro: **1483 candidatos
antes, 1483 depois — diferença zero.** É o raio de alcance que se quer de uma correção
dirigida, e é a mesma medição que reprovou a primeira versão da guarda com 1478.

#### 9. No conjunto de campo, que é a régua

Remedido em 2026-08-23 sobre as 66 páginas da S-99, com o código desta entrega
(`cvoff-field --json`, os quatro relatórios de `docs/metrics/`):

| | antes (S-99) | depois |
|---|---|---|
| detectados | 109 | **110** |
| casados | 106 | **109** |
| falsos positivos | **3** | **1** |
| recall de detecção | 0,9217 | **0,9478** |
| precisão de detecção | 0,9725 | **0,9909** |

**Os dois falsos positivos que somem são as duas faixas da `p14` do Yusupov**, que a S-99 tinha
nomeado como o defeito de detecção que aquela página media — *"dois fragmentos de scan do
`p14`"*, *"o detector perde dois dos três do `p14`"*. Era essa página, e é ela que este item
fecha.

**A atribuição fecha por livro, e são dois — os outros 28 não se mexeram.** Diff do `per_book`
contra o relatório de `9eb6685`:

| livro | casados | falsos positivos | recall | `comparable` | `exact` |
|---|---|---|---|---|---|
| `Yusupov` | 3 → **5** | 2 → **1** | 0,500 → **0,833** | 1 → **3** | 1 → **3** |
| `GALLAGHER` | 4 → **5** | 1 → **0** | 0,800 → **1,000** | — | — |

No `GALLAGHER` é a p124: a única caixa da página era a faixa de 308×274 pt, e passa a ser o
diagrama de contorno de 119×120 pt. E o `Yusupov` cruza um limiar que não é de detecção —
`enough_comparable` vai de **`False` para `True`**: com um diagrama conferível o livro não tinha
base para medir leitura, e com três passa a ter.

**O falso positivo que sobra no `Yusupov` é o legítimo, e isso é o teste da guarda.** É a arte
de capa da `p2`, lida a 0,177 — exatamente o que a S-99 pôs no conjunto para que houvesse
página sem diagrama a medir. A S-176 matou as duas faixas fantasma **sem** matar a medição de
falso positivo; uma guarda que zerasse a coluna teria zerado junto a capacidade de detectá-la.

**O tempo caiu e não é ganho de desempenho.** Os `seconds` do HEAD anterior foram medidos sob
contenção de CPU (um treino ocupando os 12 núcleos), e a diferença entre modelos ali chegava a
113,3 s contra 84,0 s pelo mesmo motivo. Esta remedição rodou com a máquina mais livre. Nada em
`seconds` ou `seconds_per_diagram` desta entrega mede a S-176 — ela mexe em quantos candidatos
existem, não em quanto custa cada um.

**Os quatro relatórios têm de ser remedidos junto com uma mudança de detecção, e a guarda da
S-100 não avisa.** Ela compara `pages` e `annotated` do conjunto, e mudança de código não move
nenhum dos dois: os JSON continuavam válidos aos olhos do teste enquanto descreviam um programa
que já não existia. É o mesmo buraco que a S-175 encontrou no `deteccao_base.csv` versionado, e
por ora o remédio é o mesmo — remedir à mão e dizer que se remediu.

E a faixa passa a deixar rastro: `"faixa-da-pagina"` é o novo motivo em `RejectionRow`, e é o
**primeiro** que barra candidato da fonte embutida — os outros três do `hybrid` julgam achado
de contorno. `detection_census.RejectionRow` diz isso no docstring, porque era a premissa
anterior.

**Testes.** `tests/test_detection.py::PageBandGuardTests`, 11 casos. Os dois que carregam a
medição são `test_uma_casa_achada_dentro_do_diagrama_nao_o_transforma_em_faixa` (o par de §6,
sem o qual a guarda apagaria dois diagramas do acervo) e
`test_o_diagrama_de_dentro_da_faixa_e_recuperado_pelo_contorno` (§3: tirar a faixa não pode
custar o diagrama que estava dentro dela).

**O que fica em aberto.** A guarda alcança a faixa que **contém** um tabuleiro. Uma faixa que
não contenha nenhum não produz achado de contorno, `contour_inside_candidate` devolve `None`,
e ela sobrevive — como sobrevivia antes. É de propósito: ali não há nada a comparar, e recusar
por ausência de achado transformaria "o contorno não conseguiu" em "não é diagrama", que é
justamente a inferência que a S-12 recusa fazer contra a declaração do PDF.

---

## 7. Sequenciamento sugerido

| ordem | entrega | fecha | estado |
|---|---|---|---|
| 1 | **S-82** censo | a cegueira que deixou isto passar | ✅ 2026-08-14 |
| 2 | **S-78** piso em pontos | os 71 glifos do relato | ✅ 2026-08-14 |
| 3 | **S-79** gabarito sobre o que sobreviveu | as 42 páginas de prior envenenado | ✅ 2026-08-14 |
| 4 | **S-80** textura relativa | — | ❌ a medição reprovou |
| 5 | **S-81** imagem fatiada | o `GALLAGHER`, que nenhum limiar alcança | ✅ 2026-08-14 |
| 6 | **S-143** contraste de casa | a foto quadrada, que era o alvo da S-80 | ✅ 2026-08-17 |
| 7 | **S-175** reparo de quina | os 3 por página do `Reinfeld`, que a S-143 deixou em aberto | ✅ 2026-08-20 |
| 8 | **S-176** faixa de página | a caixa de 460 pt do `Yusupov`, que a forma não separava | ✅ 2026-08-22 |

A ordem se pagou quatro vezes, e todas antes de alguém abrir um PDF a olho:

1. O censo **corrigiu o piso** que a S-78 ia usar (o vale não era 50→110 pt) e **promoveu a
   S-81** de "a mais dispensável" a necessária. Ver
   [O que o censo corrigiu neste número](#o-que-o-censo-corrigiu-neste-número).
2. O censo **reprovou a S-80 inteira**, com a curva que mostra que ela perde mais do que pega
   em todo ponto de corte.
3. O censo **pegou uma regressão da S-81** que os testes de unidade não pegavam: a união
   suprimindo achados de contorno bons no `GALLAGHER`.
4. O censo **pegou um efeito colateral no `Polgar`** — 114 diagramas trocando um recorte de
   737 px por um de 241 px — num livro que ninguém tinha motivo para conferir.

**E se pagou uma quinta vez, ao contrário.** A S-143 é o caso em que o instrumento *errou*, e
o modo de errar vale mais que os quatro acertos: ele não mediu de menos, ele mediu **onde não
era**. `sample_pages` descarta as bordas do livro por uma razão correta — economizar amostra —
que vira cegueira assim que a pergunta muda de "onde estão os diagramas" para "onde estão os
falsos positivos". A S-80 leu "zero instâncias" de uma amostra que não podia contê-las e
arquivou a entrega certa pelo motivo errado.

Fica a regra: **um instrumento é amostrado para uma pergunta, e a amostragem é uma premissa
dele.** Quando a pergunta muda, a amostragem tem de ser reconferida antes do número.

---

## Resultado, medido

Acervo inteiro, 32 livros, 24 páginas por livro. Diff contra a linha de base do dia
(`docs/metrics/deteccao_20260814.csv`):

| | antes | depois |
|---|---|---|
| candidatos | 1309 | 1307 |
| **suspeitos (< 72 pt)** | **6** | **1** |
| páginas com numeração deslocada | 1 | **0** |
| páginas com gabarito misturado | 2 | 1 |
| livros com mudança | — | **2 de 32** |

As 7 perdas: 5 suspeitos e 2 fragmentos do `GALLAGHER` de 72 pt (textura 0,35 e 0,23),
conferidos um a um. Os outros 30 livros saíram **byte a byte iguais** — que é o raio de
alcance que se quer de uma correção dirigida.

No livro do relato, 200 páginas amostradas: suspeitos 7 → **0**, numeração deslocada 2 → **0**,
gabarito misturado 3 → **0**, e **zero** perdas acima do limiar.

No `GALLAGHER`, livro inteiro (192 páginas): candidatos 194 → 200, suspeitos 22 → **1**,
candidatos de contorno 154 → **175**.

---

## 8. Como reproduzir

Os números desta análise saíram de cinco varreduras diretas sobre o acervo, com o venv do
projeto (`.venv/Scripts/python.exe`):

| número | como |
|---|---|
| tabela de §1 | `page.get_image_info()` na página de índice 231 |
| histograma de §3 | as quatro guardas de `candidates_from_embedded_images` reaplicadas, agrupando `max(bbox.width, bbox.height)` |
| 14 páginas de §4.1 | `detect_diagrams` completo, checando se o índice do candidato < 60 pt fica no fim da lista |
| 42 páginas de §4.2 | páginas com ≥ 2 candidatos embutidos em que `min(lado) < 60 <= max(lado)` |
| tabelas de §5.1 | `board_texture_score(refine_candidate_with_contour(page, c).board_rgb)`, amostra de 40 páginas com imagem embutida por livro |

A varredura completa do livro do relato leva ~25 min em CPU; a amostragem por livro no acervo,
~40 min. São o argumento para a S-82 existir como ferramenta e não como script de scratchpad.

### Os números da S-175

| número | como |
|---|---|
| as caixas de 101×116 e o motivo da recusa | `detect_boards(render_pdf_page(pdf, 141), rejected=[...], checker_floor=0.0)`, imprimindo o `RejectedQuad` de cada candidato com lado ≥ 90 pt |
| "não é uma componente" | `cv2.connectedComponents(thresh, connectivity=8)` sobre o binário, no `thresh_base` e no passe de reparo |
| a tabela de DPI | o mesmo `detect_boards`, variando `render_pdf_page(..., dpi=)` de 150 a 400 |
| a tabela de operações | duas casas afastadas por 1 px na quina, contando componentes depois de cada fechamento — é a mesma figura do `_severed_corner_pair` dos testes |
| a tabela do `Gaprindashvili` | as 13 páginas que o censo amostra daquele livro, com `_threshold_passes` trocado em memória pelo desenho fundido, e `recognize_page` nos dois |
| o custo de +54% | `_extract_candidate_quads` sobre 8 páginas já renderizadas, mediana de 24 corridas, com os dois desenhos de passe na mesma árvore |
| o censo e a leitura, antes e depois | **duas árvores**: `git worktree add --detach <tmp> 0978c0d` e a de trabalho |

A última linha é o método, e não um detalhe de execução. **Remendar só o passe de limiar dentro
de um processo mediria um programa que não existe** — e havia uma segunda armadilha, esta
específica desta entrega: o `deteccao_base.csv` versionado não reproduzia nem a árvore de
`0978c0d`, porque a S-160 mudou o recorte do acervo sem regravá-lo. Duas árvores é o que garante
que os dois lados sejam **o programa inteiro**, e medir o "antes" em vez de lê-lo de arquivo é o
que garante que ele seja o **antes de verdade**.

### Os números da S-176

| número | como |
|---|---|
| as três caixas embutidas da página, com aspecto e cobertura | `page.get_image_info()` nas páginas 13, 14 e 15, dividindo `bbox` pela área de `page.rect` |
| as duas caixas que a tela desenhava, e as recusas | `detect_diagrams(page, render_pdf_page(pdf, 14, dpi=220), rejected=[...])` |
| os 1287 candidatos e os 24 de contraste zero | `candidates_from_embedded_images` no acervo, 40 páginas por livro, com `board_checker_score(cv2.resize(c.board_rgb, (320, 320)))` |
| os 837 `board_fill` e as duas populações | por candidato: `detect_boards` na região de `contour_inside_candidate`, `max(lado do quad) / max(lado da região)` |
| a classificação dos 6 de baixo | o quad desenhado sobre a região com `cv2.polylines`, conferidos a olho um a um |
| os 25 casos de "uma casa" | o `1001_Winning ... _hq` de três em três páginas (374 de 1121) e o `La_Combinacion` inteiro, filtrando `board_fill < 0,50` |
| os 21 de 831 abaixo de 0,06 com `fill` alto | a mesma varredura, contando `board_checker_contrast` do achado na população de `board_fill >= 0,50` |
| as 5 perdas da primeira versão | `detect_diagrams` com e sem `band_board_fill`, 24 páginas por livro, diff da contagem por página |

**O `board_fill` é medido sobre a região com folga, e não sobre o bbox cru.** São os mesmos 6
pt de `REFINE_PADDING_PT` que o refino usa, então um diagrama pequeno num bbox justo chega a
~0,93 e não a 1,00 — e o corte precisa ser lido nessa escala. Medi-lo sobre o bbox cru daria
outra distribuição e outro número.
