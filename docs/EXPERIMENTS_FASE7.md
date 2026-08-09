# Experimentos — Fase 7

Registro do que foi medido na Fase 7, **inclusive o que não ajudou** — a mesma exigência que
a Fase 5 impôs a si mesma, e pela mesma razão prática: experimento não registrado vira
folclore, e custa à próxima pessoa refazê-lo.

Base: [ROADMAP_FASE7.md](ROADMAP_FASE7.md) · Spec: [SPEC_FASE7.md](SPEC_FASE7.md) ·
Continuação de [EXPERIMENTS.md](EXPERIMENTS.md), que cobre a Fase 5.

**Máquina:** Windows 11, 12 CPUs lógicas, `torch 2.10.0+cpu` — **sem GPU**, como na Fase 5.

**Conjunto de medição:** `data/field_set.jsonl` (S-41) — 15 páginas anotadas à mão, 38
diagramas, 3 páginas sem diagrama. Reproduzir: `cvoff-field`.

---

## S-38 · O refino do contorno, antes e depois de conferir o que entrega

`refine_candidate_with_contour` roda o detector de contorno dentro do bbox embutido para
alinhar a grade. Ela conferia se o contorno tinha achado *alguma coisa*, nunca se o que achou
era *melhor*.

`board_texture_score` do recorte cru contra o refinado, nos seis candidatos da página 80 do
`Karpov 1`:

| candidato | cru | refinado | |
|---|---|---|---|
| #0 | 0,3138 | 0,6042 | melhora |
| #1 | 0,2000 | 0,4616 | melhora |
| #2 | 0,3511 | **0,2388** | **piora** |
| #3 | 0,2000 | 0,4271 | melhora |
| #4 | 0,2892 | **0,2252** | **piora — o dos oito reis brancos** |
| #5 | 0,3306 | 0,5059 | melhora |

Efeito de exigir que o refino não piore, no conjunto de campo:

| | antes | depois |
|---|---|---|
| recall de detecção | 0,9211 | 0,9211 |
| precisão de detecção | 0,9722 | 0,9722 |
| **detectados que produzem posição legal** | **33/35** | **35/35** |
| acima do gate | 26 | 26 |
| taxa de exportação | 0,6842 | 0,6842 |

**Entrou.** A métrica primária não se move, mas a ilegalidade zera: o ganho é de natureza,
não de quantidade. Em todo o conjunto, 2 refinos foram descartados — exatamente os previstos.

---

## S-39 · Normalização do tabuleiro: **medido, e nada entrou ligado**

A hipótese era direta e parecia forte. O caso motivador é o `Euwe Band 1-2` p25: recorte
perfeito, `board_texture_score` 1,0000, e `min_confidence` **0,0000**. Casas escuras
hachuradas com linhas diagonais sobre papel de 1956. O pré-processamento era
`cvtColor → resize → /255`, sem nenhuma normalização.

### As quatro etapas, uma por vez, no conjunto de campo

| variante | versão | exportação | legais | acima do gate | recall | precisão | seg |
|---|---|---|---|---|---|---|---|
| **nenhuma (base)** | `norm0` | **0,6842** | 35 | 26 | 0,9211 | 0,9722 | 11,4 |
| deskew | `normd` | 0,6842 | 35 | 26 | 0,9211 | 0,9722 | 11,9 |
| campo plano | `normf` | 0,6842 | 35 | 26 | 0,9211 | 0,9722 | 44,3 |
| supressão de trama | `normh` | **0,0000** | 32 | **0** | 0,9211 | 0,9722 | 15,9 |
| CLAHE | `normc` | 0,6842 | 35 | 26 | 0,9211 | 0,9722 | 11,1 |
| plano + trama | `normfh` | 0,0000 | 33 | 0 | 0,9211 | 0,9722 | 52,5 |
| plano + CLAHE | `normfc` | 0,6842 | 35 | 26 | 0,9211 | 0,9722 | 44,0 |
| trama + CLAHE | `normhc` | 0,0000 | 32 | 0 | 0,9211 | 0,9722 | 16,7 |
| plano + trama + CLAHE | `normfhc` | 0,0000 | 32 | 0 | 0,9211 | 0,9722 | 47,9 |
| tudo | `normdfhc` | 0,0000 | 32 | 0 | 0,9211 | 0,9722 | 49,3 |

Dois resultados, e nenhum era o esperado.

### 1. Campo plano e CLAHE não mudam **nada** — e a razão é o aumento de dados

Não "mudam pouco": produzem os mesmos 35 legais, os mesmos 26 acima do gate, a mesma taxa.
E não é que estejam desligados — medida a diferença média de pixel no tabuleiro do Euwe p25:

| etapa | diferença média de pixel |
|---|---|
| deskew | 0,000 (o tabuleiro já está alinhado; `estimate_skew` devolve 0,0, que é o certo) |
| campo plano | 3,670 |
| supressão de trama | 44,099 |
| CLAHE | 2,999 |

As duas mudam a imagem e o modelo é indiferente. O motivo está em
`training.build_train_transform`: **`ColorJitter(brightness=0.3, contrast=0.3)` já treinou o
modelo a ignorar exatamente esse tipo de ajuste global.** Campo plano e CLAHE são correções
de brilho e contraste; o modelo aprendeu a não olhar para elas.

Isto é bom saber e é o oposto do que a spec da S-39 supunha. O aumento genérico que a S-40
chama de insuficiente já cobre metade do que a S-39 propunha fazer na inferência.

### 2. A trama não é separável da peça, por dois métodos independentes

Período dominante da hachura numa casa escura do Euwe, pelo espectro do gradiente:
**~12,5 px numa casa de 100 px**. É grosseiro — comparável à espessura do traço da peça.

**Mediana**, `min_confidence` por tamanho de kernel:

| caso | cru | k=3 | k=5 | k=7 | k=9 | k=13 | k=17 | k=25 |
|---|---|---|---|---|---|---|---|---|
| Euwe p25 | 0,000 | 0,000 | 0,000 | 0,000 | 0,002 | 0,046 | **0,096** | 0,000 |
| Euwe p100 | 0,001 | 0,001 | 0,002 | 0,007 | 0,001 | 0,000 | 0,000 | 0,000 |
| Gallagher p80 | 0,453 | 0,458 | 0,410 | 0,477 | 0,458 | **0,006** | 0,008 | 0,000 |
| Karpov p80 | 1,000 | 1,000 | 1,000 | 1,000 | 0,960 | **0,790** | 0,000 | 0,182 |
| Polgar p300 | 1,000 | 1,000 | 1,000 | 1,000 | 0,998 | 0,996 | **0,222** | 0,036 |

**Morfologia** (a trama é direcional, a mediana é isotrópica — valia testar):

| caso | cru | fecha3 | fecha5 | fecha7 | fecha9 | abre5 | abre7 | abre9 |
|---|---|---|---|---|---|---|---|---|
| Euwe p25 | 0,000 | 0,000 | 0,000 | 0,022 | 0,020 | 0,000 | 0,000 | 0,008 |
| Euwe p100 | 0,001 | 0,001 | 0,059 | **0,101** | 0,027 | 0,019 | 0,019 | 0,003 |
| Gallagher p80 | 0,453 | 0,484 | 0,287 | 0,143 | 0,222 | 0,440 | 0,516 | 0,347 |
| Karpov p80 | 1,000 | 1,000 | 0,647 | **0,050** | 0,000 | 1,000 | 1,000 | 0,395 |
| Polgar p300 | 1,000 | 1,000 | 0,985 | **0,045** | 0,000 | 1,000 | 1,000 | 0,843 |

**Não há janela.** O kernel que começa a mover o Euwe (13 na mediana, 7 na morfologia) é o
mesmo que derruba o Karpov e o Polgar de 1,000 para 0,05–0,79. E o melhor que o Euwe atinge
em qualquer configuração é **0,101** — oito vezes abaixo do gate de 0,80.

Faz sentido depois de medido: a hachura tem 12,5 px e o traço da peça tem a mesma ordem de
grandeza. Nenhum filtro que separa por **escala** vai distinguir os dois, e foi por escala
que as duas famílias testadas separam.

### O que ficou, e por quê

**Nada ligado por padrão.** `NormalizerConfig()` é `norm0` e o pipeline é o de antes.

O módulo `preprocess.py` **fica**, com os defaults desligados e a medição no docstring —
mesma decisão que a Fase 5 tomou com o TTA (`TTA_ENABLED = False`) e com a temperatura
calibrada (`APPLY_CALIBRATED_TEMPERATURE = False`): o parâmetro continua existindo, medido e
documentado, porque a conta pode virar noutro acervo. E `estimate_skew` é correto e barato:
devolve 0,0 em tabuleiro alinhado, que é o caso de todos os 38 diagramas do conjunto — o que
também é informação, e diz que o warp da S-12 não está deixando sobra de rotação.

### O que isto muda no plano

A S-39 e a S-40 eram um par: **tornar a entrada parecida com o treino** ou **tornar o treino
parecido com a entrada**. A medição elimina a primeira metade. Restam duas saídas, e as duas
são de treino, não de inferência:

1. **S-40, aumento dirigido** — sintetizar hachura, granulação e papel amarelado sobre as
   amostras limpas, e deixar o modelo aprender a atravessá-las. É o caminho natural, e o
   `ColorJitter` já provou que o modelo aprende invariância quando o aumento a ensina.
2. **Anotar os livros hachurados** — as 3.289 amostras vêm quase todas dos livros fáceis.
   Meia dúzia de páginas do Euwe e do Gallagher corrigidas à mão põem o domínio no treino
   sem que ninguém precise simulá-lo. Mais barato de acertar, mais caro em tempo humano.

O erro concreto que qualquer uma das duas precisa consertar, medido no Euwe p25: o modelo lê
as três primeiras filas **corretamente** (`r4rk1/pp3ppp/2n1q3`) e confunde **bispo branco com
peão branco em casa hachurada** na parte de baixo. Não é "o tabuleiro é ilegível" — é uma
confusão de classe específica, num contexto de fundo específico.

---

## S-40 · Aumento dirigido: implementado, **ainda não medido**

O módulo `augment.py` existe, está testado (19 testes: piclabilidade sob `spawn`,
determinismo por semente, rótulo preservado no espelhamento) e está **desligado por
padrão** — `AugmentConfig()` é `aug0` e reproduz o treino que produziu o checkpoint atual.

**Medir exige treinar, e treinar custa ~9 min por época nesta máquina.** A comparação
honesta é quatro variantes × 3 épocas, mesma semente, `--fresh`, avaliadas no conjunto de
campo: ~110 minutos de CPU cheia. Não foi rodado porque a máquina estava em uso.

Reproduzir quando ela estiver livre:

```bash
cvoff-train --fresh --epochs 3 --seed 42 --augment aug0 --model models/experiments/s40_base.pt
cvoff-train --fresh --epochs 3 --seed 42 --augment mhsp --model models/experiments/s40_dirigido.pt
cvoff-field --model models/experiments/s40_base.pt     --json docs/metrics/s40_base.json
cvoff-field --model models/experiments/s40_dirigido.pt --json docs/metrics/s40_dirigido.json
```

**A métrica que decide não é a acurácia de validação.** As duas vão sair em ~0,97: o split
de validação é feito dos mesmos livros fáceis, e o aumento dirigido não deve ajudar ali —
pode até atrapalhar um pouco. O que se quer saber é se o modelo passa a **ler a página
hachurada**, e só a taxa de exportação do conjunto de campo responde isso.

### Duas coisas que a inspeção das imagens mostrou antes de qualquer treino

**1. As amostras de treino já contêm casas hachuradas.** Comparadas lado a lado na escala do
modelo (64×64), casas do `Euwe` contra casas de uma amostra de `data/samples/`: a amostra —
que vem do `Karpov`, um livro que lê a **1,000** — também tem casas escuras listradas na
diagonal. A hipótese ingênua "o modelo nunca viu hachura" está **errada**.

O que difere no Euwe é a qualidade do scan: hachura mais densa e escura, traço da peça
quebrado, granulação em cima. É degradação de scan, não a hachura em si.

**2. Estatística de tom não separa os casos.** Fração de pixels quase-preto/quase-branco:

| página | extremos | cinza médio | lê bem? |
|---|---|---|---|
| Karpov p80 | 76,8% | 11,6% | sim (1,000) |
| Polgar p300 | 80,2% | 11,9% | sim (1,000) |
| Euwe p25 | 56,6% | 23,0% | **não** (0,000) |
| Gallagher p80 | 41,3% | 34,7% | **não** (0,453) |
| amostras de treino (5 sorteadas) | 49,8%–70,3% | 7,0%–19,5% | — |

As páginas que falham têm **mais cinza médio**, mas caem dentro da faixa das amostras de
treino. A estatística global não distingue, o que quer dizer que a diferença é **local** —
está em como a peça se destaca do fundo dentro da casa, não no histograma da página.

Isto é um aviso sobre o que esperar da S-40: sintetizar hachura sobre amostra limpa pode não
reproduzir a degradação certa, porque a degradação certa não é a hachura. A alternativa
continua sendo **anotar meia dúzia de páginas do Euwe e do Gallagher** e pôr o domínio real
no treino — mais caro em tempo humano, e sem o risco de ensinar o modelo a ser robusto a uma
degradação que não é a que ele encontra.

---

## Fase 8 · Três levantamentos que enfraqueceram três itens da spec

A spec das Fases 7 a 11 foi escrita antes destes números. Os três itens abaixo continuam
tecnicamente corretos e passaram a valer muito menos do que ela supunha. Registrado aqui para
que ninguém os implemente confiando na estimativa.

Amostragem: 12 páginas por livro nos dois primeiros, 40 no terceiro, nos 27 PDFs.

### S-44 · O marcador `W`/`B`: **zero ocorrências na camada de texto do acervo**

A spec dizia que a convenção Batsford (`W`/`B` colado à borda do diagrama) é a mais comum da
literatura inglesa, e que ela não é lida nem nos livros que **têm** camada de texto.

Varridas todas as linhas de 1 a 3 caracteres na vizinhança de cada diagrama (raio de 40 pt),
em 380 diagramas de 19 livros com texto: **nenhum marcador `W`/`B`**. O levantamento acusou 5
livros, e os cinco são falso positivo dele mesmo — o que achou foram glifos da fonte de
xadrez sobrepostos ao tabuleiro:

| achado | ocorrências | o que é |
|---|---|---|
| `+` sobreposto | 382 | fonte de diagrama |
| `P`, `O`, `R` sobrepostos | 78 | fonte de diagrama |
| `[2]`, `[3]`, `[4]` à direita | 30 | número de solução do `Karpov` |

E o único livro do acervo que **tem** o marcador impresso — o `GALLAGHER`, onde o `B` ao lado
do diagrama 76 foi verificado à vista — **não tem camada de texto nenhuma**.

**Conclusão.** A parte (a) da S-44 (padrão de letra isolada na camada de texto) não tem o que
ler: alcance **0 de 27 livros**. A parte (b) (classificador de glifo sobre a imagem) continua
sendo o único caminho, precisa de um dataset de glifos anotado à mão, e o alcance conhecido é
**1 livro**.

### S-45 · Coordenadas: **13,7%, e nenhum diagrama do ponto de vista das pretas**

A spec propunha ler as coordenadas impressas para (i) fechar a pendência da S-13 — diagrama
impresso do ponto de vista das pretas — e (ii) obter o registro exato da grade.

Filas (`1`–`8`) e colunas (`a`–`h`) isoladas na vizinhança de cada diagrama, 380 diagramas:

| | diagramas | fração |
|---|---|---|
| com as **filas** legíveis no texto | 52 | 13,7% |
| com as **colunas** legíveis no texto | 2 | 0,5% |

E os 52 estão concentrados: **48 são do `Polgar 5334`**, que já lê a **1,000** no conjunto de
campo. Os outros 4 são do `Yusupov`, todos parciais — a extração perde dígitos (`876541`,
`765432`).

O achado que mais importa é o outro. Dos 49 diagramas em que a sequência é conclusiva:

| ponto de vista | diagramas |
|---|---|
| brancas (`87654321`) | **49** |
| pretas (`12345678`) | **0** |

**A pendência da S-13 pode não existir neste acervo.** Ela está aberta no ROADMAP desde a
Fase 2, e em 49 diagramas com evidência não há um só. A ressalva honesta: 49 é a amostra
**com evidência**, não 380 — os outros 331 não têm coordenada que confirme nem desminta.

**Conclusão.** A S-45 pela camada de texto alcança um livro, e é o que menos precisa. O
benefício de registro de grade continua real, e continua disponível só onde há coordenada.

### S-43 · A faixa de margem descarta **6 declarações contra 150** que a S-16 já vê

`pdf_text.MARGIN_BAND = 0,07` joga fora 7% do topo e do rodapé como cabeçalho corrente. A
spec aponta que o `LAS BLANCAS JUEGAN PRIMERO` do `Reinfeld` mora exatamente ali — verdade, e
verificado à vista —, mas aquele livro não tem camada de texto: a perda é do OCR, não da S-16.

Nos 27 livros, 40 páginas cada, contando declarações dentro e fora da faixa:

| | ocorrências | livros |
|---|---|---|
| descartadas pela faixa de margem | **6** | 3 |
| que a S-16 já enxerga | **150** | — |

As 6, uma a uma:

| livro | texto | veredito |
|---|---|---|
| `Koblenz` | `Juegan las blancas` ×2, `Juegan las negras` ×1 | **perda real** |
| `AAGAARD` | `Black to play - what is the only move?`, `There are two ways for White to play,` | enunciado que caiu na faixa; recuperável |
| `Polgar` | `2.1 White to Move #2` | **cabeçalho de seção** — é o que a faixa existe para descartar |

**Conclusão.** O conserto vale ~4% a mais de declarações, em 3 livros, e o caso do `Polgar`
mostra por que ele não é trivial: ali o texto na margem é um cabeçalho corrente que
**também** é uma declaração de escopo verdadeira para a seção inteira. Distinguir "cabeçalho
que declara" de "cabeçalho que repete" não é a mudança de uma linha que a spec sugeria.

### O que os três juntos dizem sobre a Fase 8

O valor da Fase 8 **concentra-se no OCR de verdade** (S-42 + S-43), e não nos atalhos que a
spec propunha para evitá-lo. Os 7 livros sem camada de texto continuam sendo o alvo, o
`LAS BLANCAS JUEGAN PRIMERO` continua impresso e legível, e agora se sabe que não há caminho
barato até ele: nenhum `W`/`B` em texto, coordenadas em 13,7%, e a faixa de margem valendo 6
declarações.

Isso torna a decisão sobre a dependência de OCR — que o ROADMAP lista como do dono do
projeto — **mais** consequente, não menos: ela deixou de ser um item entre vários e passou a
ser *o* item da Fase 8.

---

## S-42 + S-43 · O motor de OCR entrou, e o que ele ainda não provou

Implementados em 2026-08-09. O que segue é o que foi **medido**, separado do que foi
**construído** — os dois não coincidem neste item, e a diferença é o próximo trabalho.

### O que foi medido: com `--ocr off`, nada muda

O critério de aceite da S-43 exige que ligar o OCR não altere os livros que têm camada de
texto, e que desligá-lo devolva o projeto exatamente como era. A segunda metade está medida:

| | S-38a (2026-08-09 04:33) | S-43, `--ocr off` (2026-08-09) |
|---|---|---|
| recall de detecção | 0,9211 | 0,9211 |
| precisão de detecção | 0,9722 | 0,9722 |
| **taxa de exportação** | **0,6842** (26/38) | **0,6842** (26/38) |
| detectados e legais | 35 | 34 |

Relatório em `docs/metrics/field_20260809_s43_sem_ocr.json`.

**A linha que difere não é do código desta entrega, e vale dizer por quê.** `legal` conta
`is_fatal is not True`, que é função só do campo de peças lido — nenhuma das mudanças da
S-42/S-43 toca detecção, recorte ou classificação. O que mudou entre as duas medições foi o
arquivo: `models/piece_classifier.pt` foi reescrito às 07:49, **depois** da medição da S-38a
às 04:33. Um diagrama do `Euwe` p100 passou a sair fatalmente ilegal com o checkpoint novo.

A verificação direta de que o caminho novo está inerte: das 15 páginas do conjunto de campo,
**0 produzem declaração de escopo de página** pela camada de texto. O único comportamento
que a S-43 acrescenta sem motor de OCR não dispara uma vez aqui.

**Consequência para o roadmap:** o número de referência da Fase 7 (0,6842) continua válido,
mas a linha `legal` do `field_20260809_s38a.json` descreve um checkpoint que não está mais em
disco. Qualquer comparação futura tem de partir do arquivo novo.

### O que **não** foi medido, e é o que falta

Nenhum motor de OCR está instalado nesta máquina. Então:

| pergunta | estado |
|---|---|
| o `--ocr off` mantém o pipeline igual | **medido**: sim |
| ligar o OCR não muda os livros com camada de texto | **provado por construção, não medido** — o motor não roda onde a camada respondeu, e há teste disso; falta o número |
| a página 40 do `Reinfeld` sai com os 6 diagramas em `WHITE` e exercícios 193–198 | **não medido** — é o critério de aceite principal da S-43 e exige `uv sync --extra ocr` |
| o custo por página com OCR ligado fica abaixo de ~2× o reconhecimento | **não medido** — a instrumentação está no log (`_lines_with_ocr`), falta rodar |

Os três últimos são a mesma medição, e ela precisa de uma decisão que é do dono do projeto:
instalar o extra. O código está pronto para ela e não pretende ter respondido a ela.

### O que a implementação ensinou

**O desempate "a camada de texto vence" é quase inalcançável, e isso é bom.** A regra está
na spec e foi implementada. Ao testá-la, ficou claro que o gate por diagrama a torna rara por
construção: o motor só roda onde a camada calou, então as duas fontes praticamente nunca
disputam o mesmo escalão do mesmo diagrama. Para que disputem, uma linha lida na vizinhança
de um diagrama precisa cair também na de outro que já tinha texto. O primeiro teste que
escrevi para ela passava sem exercitá-la — as duas leituras caíam em baldes diferentes. Foi
reescrito para `context_from_lines`, onde o caso é construível, e o teste de integração
passou a afirmar o que de fato acontece: procedências diferentes em diagramas diferentes da
mesma página.

**O tabuleiro é apagado antes do motor, não filtrado depois.** A armadilha nº 3 da S-16 — o
OCR lê as peças como caracteres — tinha duas saídas. Filtrar depois exigiria estender
`_is_diagram_font_row`, que foi feito para o `Polgar` (onde o tabuleiro *é* texto) e não para
pixels. Pintar de branco o interior do `bbox_pdf` no recorte já renderizado custa uma linha e
faz o problema deixar de existir. Branco e não preto: um retângulo preto de 400×400 px é a
coisa mais parecida com um bloco de texto que se pode desenhar.

**O parcial de exportação precisou de mais um campo.** `ScanParams` já guardava
`model_identity` porque retomar depois de treinar misturava dois modelos (S-57). O OCR cria
exatamente o mesmo problema numa segunda dimensão: retomar com motor uma varredura começada
sem ele produziria um PGN em que metade dos `[SideToMoveSource]` diz `default` e a outra
`ocr`, sem que a diferença seja do livro. `ocr_engine` entrou no cabeçalho do parcial pelo
mesmo motivo e com o mesmo default vazio.
