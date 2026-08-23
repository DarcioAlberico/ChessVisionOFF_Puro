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
> | S-78 a S-82, S-143 | [ANALISE_DETECCAO.md](ANALISE_DETECCAO.md) |
> | S-83 a S-94 | [PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md) |
> | S-95 a S-142, S-171 a S-174, S-218, S-220, S-221 | [SPEC_FASE14.md](SPEC_FASE14.md) |
> | S-144 a S-170 | [SPEC_UI.md](SPEC_UI.md) |

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

**Linha de base nova:** `docs/metrics/deteccao_base.csv` e `.json` (39 livros, 24 páginas por
livro mais 8 de frente). A de 2026-08-14 fica em `docs/metrics/deteccao_20260814.csv`, que é o
que as S-78 a S-82 mediram.

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
