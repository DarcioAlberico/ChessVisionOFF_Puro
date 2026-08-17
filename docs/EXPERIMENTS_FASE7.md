# Experimentos — Fase 7

Registro do que foi medido na Fase 7, **inclusive o que não ajudou** — a mesma exigência que
a Fase 5 impôs a si mesma, e pela mesma razão prática: experimento não registrado vira
folclore, e custa à próxima pessoa refazê-lo.

Base: [ROADMAP_FASE7.md](ROADMAP_FASE7.md) · Spec: [SPEC_FASE7.md](SPEC_FASE7.md) ·
Continuação de [EXPERIMENTS.md](EXPERIMENTS.md), que cobre a Fase 5.

**Máquina:** Windows 11, 12 CPUs lógicas, `torch 2.10.0+cpu` — **sem GPU**, como na Fase 5.

**Conjunto de medição desta fase:** `data/field_set.jsonl` (S-41) — **15 páginas anotadas à
mão, 38 diagramas**, 3 páginas sem diagrama. Reproduzir: `cvoff-field`.

> ## ⚠ O conjunto mudou em 2026-08-15, e **nada nesta página é comparável ao de hoje**
>
> O conjunto vigente tem **17 páginas e 39 diagramas** — e a diferença não é só de tamanho: a
> S-95 tirou dele uma leitura alucinada que servia de referência, e a S-99 acrescentou FEN a
> 31 dos 39.
>
> | | esta página (até 2026-08-11) | vigente |
> |---|---|---|
> | páginas / diagramas | 15 / 38 | **17 / 39** |
> | taxa de exportação da produção | 0,7368 | **0,7179** |
> | precisão de detecção | 0,9722 (1 falso positivo) | **0,9231** (3 falsos positivos) |
>
> **As tabelas que reprovaram S-38b, S-40, S-62a e S-62b comparam variantes sobre 38
> diagramas.** Uma variante medida hoje entra nelas sem ser comparável — e a diferença de
> 0,019 na taxa de exportação é da ordem das diferenças que decidiram aqueles vereditos.
>
> Os relatórios desta página estão em `docs/metrics/field_20260809*.json` e
> `field_20260811*.json`, e **todos** declaram `"pages": 15, "annotated": 38` — é assim que se
> confere. `tests/test_field_eval.py::ConjuntoVigenteTests` trava a lista dos que são citados
> como correntes; um relatório de outro conjunto nessa lista faz a suíte falhar.
>
> O controle não foi regravado sobre o conjunto de hoje **de propósito**: a S-99 ainda vai
> crescê-lo de 17 para 60 páginas, e regravá-lo duas vezes é pagar duas vezes pela mesma
> resposta.

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

### O que **não** foi medido em 2026-08-09 — e foi medido em 2026-08-11

O extra foi instalado (`rapidocr-onnxruntime 1.4.4`, modelos no wheel, nada baixado na
primeira execução). As quatro perguntas que ficaram abertas têm resposta na seção
[S-43 medido](#s-43--o-motor-instalado-e-a-faixa-que-lia-pela-metade) abaixo. Duas delas
mudaram de resposta ao serem medidas.

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

---

## S-64 · O aparo pela moldura: o que ele corrigiu, e o que ele não tocou

Medido em 2026-08-09. O "antes" não é um número herdado: é a mesma varredura com
`trim_to_frame` desligada, ou seja, literalmente o comportamento anterior sobre os mesmos
diagramas e o mesmo checkpoint.

### Os seis livros, 606 diagramas

| livro | páginas | diagramas | conf. mín. média | abaixo do gate 0,80 | FENs que mudaram |
|---|---|---|---|---|---|
| **Karpov 1** | 70-99 | 173 | 0,9635 → **0,9889** | 14 → **4** | **10** |
| **Kemeri 1937** | 200-219 | 15 | 0,9330 → **0,9661** | 2 → **1** | 0 |
| Karpov 2 | 70-89 | 114 | 0,9493 → 0,9493 | 10 → 10 | 0 |
| Polgar 5334 | 60-79 | 108 | 1,0000 → 1,0000 | 0 → 0 | 0 |
| Aagaard Endgame | 15-34 | 120 | 1,0000 → 1,0000 | 0 → 0 | 0 |
| Reinfeld ES | 35-49 | 76 | 0,8449 → 0,8449 | 21 → 21 | 0 |

**Nenhum diagrama piorou em nenhum dos seis livros.** Nos quatro sem o defeito, nada se
moveu — que é o comportamento correto de uma segunda tentativa condicionada à falha da
primeira.

O `Kemeri` é o caso interessante da tabela: nenhuma FEN mudou, e mesmo assim um diagrama
subiu acima do gate. A leitura já estava certa; o que estava baixo era a confiança, e o
recorte melhor a levantou. É a diferença entre "corrigir um erro" e "parar de pagar por um
recorte torto".

### Os dez do Karpov 1, um a um

| página | conf. mín. | |
|---|---|---|
| p72 #3 | 0,3991 → 0,9999 | |
| p80 #3 | 0,9385 → 1,0000 | **passava pelo gate com a posição errada** |
| p80 #5 | 0,7905 → 1,0000 | |
| p81 #1 | 0,4963 → 1,0000 | |
| p87 #1 | 0,5268 → 0,9999 | |
| p88 #5 | 0,5062 → 1,0000 | |
| p88 #6 | 0,5461 → 1,0000 | |
| p92 #5 | 0,4916 → 1,0000 | |
| p93 #2 | 0,5353 → 1,0000 | |
| p94 #5 | 0,6397 → 1,0000 | |

Nove dos dez estavam abaixo do gate e iam para o `.review.pgn` como "confiança baixa" — o
que é um diagnóstico errado, porque o problema não era o classificador estar inseguro sobre
uma peça, era a grade estar deslocada quase uma casa. **Um estava acima do gate**, e esse ia
para o PGN principal.

### O conjunto de campo (S-41)

| | S-43 (`--ocr off`) | **S-64** |
|---|---|---|
| recall de detecção | 0,9211 | **0,9211** |
| precisão de detecção | 0,9722 | **0,9722** |
| detectados e legais | 34 | **35** |
| acima do gate | 26 | **28** |
| **taxa de exportação** | **0,6842** | **0,7368** |

| regime | antes | depois |
|---|---|---|
| tabuleiro em fonte (Polgar) | 1,000 | 1,000 |
| **vetorial** (Karpov, Aagaard) | 0,857 | **1,000** (14/14) |
| scan hachurado (Kemeri, Euwe) | 0,500 | 0,500 |
| scan puro (Reinfeld, Gallagher) | 0,429 | 0,429 |

Relatório em `docs/metrics/field_20260809_s64_moldura.json`.

**A leitura honesta deste resultado:** o ganho é inteiramente do regime vetorial, e ele agora
está no teto. O item não tocou scan porque o defeito não era de scan — a imagem embutida com
rodapé é uma característica de PDF vetorial. Os 10 diagramas que ainda não chegam ao PGN são
todos de scan, e nove deles são confiança abaixo do gate: o problema de domínio que a S-40
existe para atacar.

---

## S-52 · O casamento por hash perceptual, contra verdade de referência

Medido em 2026-08-09. O item promete **reportar a taxa** e recusa **prometer 100%**, então a
primeira coisa a medir não é a taxa — é se o mecanismo acerta quando tem o que casar.

### A sonda que dá confiança

As amostras salvas depois da S-31 têm `source_pdf` e `source_page` gravados pela
`RecognitionOrigin`. Isso é verdade de referência de graça: dá para casá-las às cegas e
conferir a resposta.

Índice das **20 primeiras páginas** do `1937 Kemeri.pdf` (11 diagramas), contra as 12
amostras daquelas páginas que têm procedência gravada:

| | |
|---|---|
| casadas | **12 de 12** |
| distância | **0** em todas |
| página recuperada correta | **12 de 12** |
| ambíguas | 0 |

Distância 0 era o esperado, e vale dizer por quê: essas amostras foram salvas pelo caminho
`embedded` com o detector de hoje, então o recorte indexado é o mesmo pixel a pixel. É o
melhor caso, não o caso médio.

### A sonda que dá cautela

Os **3.195 órfãos** contra o mesmo índice de 11 diagramas — quase nenhum deles deveria casar:

| | |
|---|---|
| casamentos | **0** |
| impostor mais próximo | **7 bits** (2 amostras) |
| depois | 9 (×1), 10 (×2), 11 (×13), 12 (×7), 13 (×12), 14 (×17), 15 (×37)… |
| distância máxima vista | 103 bits |

Zero falso positivo é bom. O problema é a folga.

**O limiar é 6, e o impostor mais próximo está a 7.** Do outro lado, um recorte deslocado em
6 px num tabuleiro de 800 custa **6 bits** (medido em `tests/test_provenance.py`) — e
reenquadramento é exatamente o que separa uma amostra de julho do detector de agosto, que a
S-38a mudou. As duas distribuições — casamento verdadeiro reenquadrado e impostor mais
próximo — quase se tocam.

E este é o caso **mais fácil possível**: 11 entradas de índice. Com o acervo inteiro, dezenas
de milhares, o impostor mais próximo só pode chegar mais perto.

### O que isso decidiu no desenho

Três coisas, e nenhuma delas seria óbvia sem os números acima:

- **`cvoff-provenance --match` não grava.** Gravar é `--apply`, um segundo comando. A
  operação escreve em até 3.195 linhas de trabalho humano de uma vez, e a taxa é justamente o
  número que precisa ser olhado antes.
- **O relatório traz o histograma de distância**, e não só a contagem acima do limiar. Um pico
  logo acima do corte significa casamento bom sendo recusado; um platô significa que não há o
  que casar. As duas leituras mudam o que fazer, e a contagem sozinha não distingue.
- **Ambiguidade é medida contra o segundo melhor de outro livro**, com folga de 4 bits. Duas
  renderizações da mesma posição em livros distintos ficam por volta de 10 bits (medido pela
  auditoria da Fase 1), então a folga separa "é este diagrama" de "é um dos dois".

### O que **não** foi medido

A taxa real sobre os 3.195 órfãos. Ela exige indexar os 27 PDFs — ~12 mil páginas, e a S-61
mediu 0,043 s de render mais 0,562 s de detecção por página. São horas de CPU, e é uma decisão
de quando, do mesmo tipo da medição da S-40.

---

## S-43 · O motor instalado, e a faixa que lia pela metade

Medido em 2026-08-11, com `rapidocr-onnxruntime 1.4.4` (`uv pip install`, modelos no wheel,
nada baixado na primeira execução — a promessa do README continua de pé).

### O que a instalação respondeu, e onde ela contrariou a expectativa

| pergunta de 2026-08-09 | resposta medida |
|---|---|
| o `--ocr off` mantém o pipeline igual | **sim** — 0,7368 nos dois, dígito a dígito |
| ligar o OCR muda a taxa de exportação | **não, e é o resultado certo** — ver abaixo |
| a página 40 do `Reinfeld` sai declarada | **não saía.** Ver a faixa, abaixo. Depois do conserto, sai |
| custo por diagrama com OCR | **2,0 a 3,4 s** por diagrama sem texto na camada |

**A taxa de exportação não se move com OCR, e isso não é decepção — é a métrica dizendo a
verdade.** Ela conta detecção, legalidade e gate de confiança; o OCR não toca nenhum dos três.
O que ele move é a **procedência do lado a jogar**, que a taxa de exportação não vê. Foi para
medir isso que o `cvoff-sides` existe.

| | `--ocr off` | `--ocr rapidocr` |
|---|---|---|
| recall de detecção | 0,9211 | 0,9211 |
| precisão de detecção | 0,9722 | 0,9722 |
| taxa de exportação | 0,7368 (28/38) | 0,7368 (28/38) |

Relatórios em `docs/metrics/field_20260811_sem_ocr.json` e `field_20260811_rapidocr.json`.

### A faixa de margem lia a metade de cima dos glifos

O alvo declarado da S-43 — `LAS BLANCAS JUEGAN PRIMERO` no `Reinfeld_1001` p40 — **não
funcionava**, e o motivo é geométrico. `page_scope_declaration` lia a faixa de `MARGIN_BAND`,
7% da altura da página. Naquela página são 34,6 pt, e a linha do cabeçalho não cabe neles: o
motor recebia a metade superior dos glifos.

| faixa | altura | o que o RapidOCR devolveu |
|---|---|---|
| **0,07** (o valor anterior) | 34,6 pt | `TIEAANDDIVEDA`, **confiança 0,71** |
| 0,10 | 49,4 pt | `LAS BLANCAS JUEGAN PRIMERO` (0,94) |
| **0,12** (o valor novo) | 59,3 pt | `LAS BLANCAS JUEGAN PRIMERO` (0,93) |
| 0,15 | 74,2 pt | a declaração **mais** dois fragmentos do diagrama de cima |

**O 0,71 é a lição, não o `TIEAANDDIVEDA`.** O motor não avisa quando recebe meia linha: ele
devolve algo com forma de texto e uma confiança que nenhum limiar razoável barraria. O limiar
de 0,3 da S-42 existe para descartar adivinhação, e aqui ele não tinha como ajudar — o defeito
era do recorte, não da leitura.

`SCOPE_BAND = 0,12` é uma constante **separada** de `MARGIN_BAND` porque as duas respondem a
perguntas diferentes. `MARGIN_BAND` decide o que descartar como cabeçalho corrente, e apertá-la
erra para o lado seguro; `SCOPE_BAND` é o que o motor vê, e apertá-la corta a linha ao meio.

Efeito na página alvo, mesmo checkpoint, mesma chamada:

| diagrama | antes | depois |
|---|---|---|
| #0 | `legality` (a leitura sai a 0,065 e prova pretas) | `legality`, agora com `n=187` |
| #1 | `default` | **`ocr-page-scope`**, `n=189` |
| #2 | `default` | **`ocr-page-scope`** |
| #3 | `default` | **`ocr-page-scope`**, `n=190` |

### O critério de saída da Fase 8, medido

`cvoff-sides`, 12 páginas por livro, **32 livros** (o acervo cresceu dos 27 que a spec cita),
645 diagramas amostrados. O mesmo comando com e sem motor:

| procedência | sem OCR | com RapidOCR |
|---|---|---|
| **assumido** (`default`) | **566 (87,8%)** | **498 (77,2%)** |
| texto (camada do PDF) | 41 | 41 |
| texto/página | 10 | 9 |
| legalidade | 28 | 27 |
| **OCR de legenda** | — | **25** |
| **OCR de cabeçalho** | — | **45** |

| critério | sem OCR | com RapidOCR |
|---|---|---|
| livros com procedência ≠ `default` | **17 de 32** | **19 de 32** |
| **dos quais por texto ou OCR** | **10** | **14** |
| livros com a maioria resolvida | 3 | **5** |

**O alvo da Fase 8 — 12 livros — está atingido, e a manchete engana se ficar sozinha.** Ela
já estava atingida sem OCR (17 de 32), porque `legality` também não é `default` e ela existe
desde a S-17. O que a Fase 8 acrescentou é a coluna de texto: **10 → 14 livros**, e 68
diagramas que deixaram de ser palpite.

Onde eles estão é o que torna o número concreto:

| livro | assumidos antes | depois |
|---|---|---|
| **`Reinfeld_1001_Sacrificios`** | 40 de 41 | **0 de 41** |
| `Gaprindashvili — Imagination in Chess` | 24 de 28 | **5 de 28** |
| `Aagaard — Excelling at Chess Calculation` | 23 de 23 | **15 de 23** |
| `Silman — Complete Book of Chess Strategy` | 9 de 9 | 8 de 9 |

O `Reinfeld` é o item inteiro numa linha. São ~1.900 exercícios em 320 páginas, e metade deles
é de pretas: até aqui o livro saía inteiro como `default` = brancas, ou seja, **certo por
coincidência em metade e errado na outra**. Ele agora sai declarado, e sai declarado por uma
faixa de cabeçalho que só passou a ser legível por causa de 5 pontos percentuais de altura.

Os dois últimos livros são do terceiro regime que a Fase 8 identificou — camada de texto
**parcial**, presente em metade das páginas. Nenhum dos dois tinha uma única procedência antes;
os dois passaram a ter.

Levantamentos em `docs/metrics/sides_20260811_sem_ocr.json` e `sides_20260811_rapidocr.json`.

---

## S-61 · As duas ineficiências da varredura, medidas depois de corrigidas

Medido em 2026-08-11. **Ressalva de método:** a máquina tinha duas grades de treino rodando,
então os valores absolutos estão inflados. O que se compara aqui é o **antes contra o depois
no mesmo estado de máquina**, e é a razão que interessa.

### (a) As duas orientações num único `forward`

Página 80 do `Karpov 1`, 6 diagramas, mediana de 5 repetições:

| | por página | por diagrama |
|---|---|---|
| dois lotes de 64 (antes) | 2,1105 s | 0,3517 s |
| **um lote de 128 (depois)** | **1,5937 s** | **0,2656 s** |

**−24,5% na inferência**, que é 76% do tempo de página. A computação é a mesma — as 128 casas
continuam passando pela rede; o que sai é o custo fixo de pedir um segundo lote.

Não corta a metade que a análise apontou como desperdício. Essa metade só cai com o atalho por
coordenadas, e a S-45 foi **adiada por medição** (13,7% de cobertura, 0 diagramas do ponto de
vista das pretas). O que sobra é este quarto, e ele é de graça.

A garantia que torna isso aceitável está no teste: a leitura do lote fundido é **idêntica** à
de duas chamadas separadas, casa por casa. Sem ela, a otimização seria uma troca de resultado
disfarçada de troca de desempenho.

### (b) Uma abertura por varredura, não três por página

Custo de `fitz.open`, mediana de 5 aberturas, e o que ele soma numa varredura completa
(antes: uma contagem de páginas mais três aberturas por página):

| livro | páginas | por abertura | antes | depois |
|---|---|---|---|---|
| Polgar 5334 | 1.184 | 4,79 ms | 17,0 s | **0,005 s** |
| Karpov 1 | 402 | 17,39 ms | 21,0 s | **0,017 s** |
| **Secrets of Chess Training 1–5** | 1.181 | **40,34 ms** | **143,0 s** | **0,040 s** |

O docstring antigo chamava a conta de irrelevante ao lado do render, e **estava certo para o
livro que ele olhou**. A diferença entre o melhor e o pior caso do acervo é de 8×, e no pior
são quase dois minutos e meio de puro parsing de xref por varredura.

O critério de aceite é contável e virou teste: uma varredura de 3 páginas faz **1** abertura,
onde antes fazia 10. E as FENs de uma varredura com documento emprestado são idênticas às de
uma varredura por caminho — a outra metade do critério.

### "Nenhuma mudança de resultado", conferido fora do teste sintético

O conjunto de campo com o checkpoint de produção, medido **antes** das duas mudanças
(`field_20260811_sem_ocr.json`, 05:56) e **depois** (`field_20260811_producao.json`):

| | antes | depois |
|---|---|---|
| anotados · detectados · casados | 38 · 36 · 35 | 38 · 36 · 35 |
| falsos positivos | 1 | 1 |
| legais · acima do gate | 35 · 28 | 35 · 28 |
| **taxa de exportação** | **0,7368** | **0,7368** |
| recall · precisão | 0,9211 · 0,9722 | 0,9211 · 0,9722 |

Dígito a dígito, as dez métricas. É o que se quer de uma otimização, e é o que um teste
sintético sozinho não prova: ali as imagens são zeros, e a fusão de lote não teria como
divergir mesmo se estivesse errada.

### Uma decisão de projeto que o item obrigou a tomar

O empréstimo **não levanta** quando o arquivo não abre: ele devolve a origem intacta e deixa a
etapa seguinte falhar. A tentação era validar ali — o documento está sendo aberto de qualquer
jeito, por que não? Porque até a S-61 esta abertura não existia, e cada etapa falhava com a
mensagem dela. Levantar aqui trocaria *"não consegui renderizar a página 1"* por um
`FileNotFoundError` vindo de uma camada que quem chamou não sabe que existe. Uma otimização
não deve mudar qual erro o usuário vê.

---

## S-62 · Modelo por tabuleiro: implementado, medido, **reprovado nos próprios critérios**

Medido em 2026-08-11 contra o conjunto de campo da S-41, como a spec manda — e não contra o
split de teste, que é justamente o conjunto que não representa a entrada.

**O controle é o `s40_aug0`, não o checkpoint de produção.** Os dois dão 0,7368, mas só o
primeiro foi treinado sobre o mesmo dataset, com a mesma semente, no mesmo regime de aumento e
no mesmo número de épocas. Comparar contra produção compararia dois datasets.

### A tabela

Custos remedidos com a máquina livre, todos de uma vez. Relatórios em
`docs/metrics/field_20260811_final_*.json`.

| variante | parâmetros | legais | **exportação** | **casas reparadas** | por diagrama | s/diagrama |
|---|---|---|---|---|---|---|
| produção (referência histórica) | 2,19 M | 35 | 0,7368 | 14 | 0,389 | 0,331 |
| **`aug0` — o controle** | **2,19 M** | **35** | **0,7368** | **15** | **0,417** | **0,315** |
| **`s62a` coordenadas e paridade** | **2,19 M** | **35** | **0,7368** | **10** | **0,278** | **0,308** |
| `s62b` cabeça por tabuleiro | 3,26 M | 35 | 0,7368 | **19** | 0,528 | 0,461 |
| `s62ab` cabeça + coordenadas | 3,26 M | **34** | **0,7105** | **19** | 0,528 | 0,363 |

### O veredito, critério a critério

| critério de aceite (escrito antes da primeira linha de código) | alvo | `s62a` | `s62b` | `s62ab` |
|---|---|---|---|---|
| casas reparadas caem **pelo menos pela metade** | ≤ 7 | **10** (−33%) ✗ | 19 ✗ | 19 ✗ |
| a taxa de exportação **sobe** | > 0,7368 | 0,7368 ✗ | 0,7368 ✗ | **0,7105** ✗✗ |
| custo por diagrama ≤ 1,5× | ≤ 0,47 s | **0,308 s** ✓ | 0,461 s ✓ | 0,363 s ✓ |

Dois de três falham nos três. **O item não entra**, e vai para este arquivo ao lado do TTA, dos
pesos de classe e da temperatura calibrada. Foi a regra que a Fase 5 estabeleceu, e é ela que
permite ao projeto dizer "medido" em vez de "melhorado".

**Mas os três não falham igual, e a diferença decide o que fazer depois.**

A **S-62a** é a única variante do projeto inteiro que fez o que a S-62 existia para fazer:
reduziu o reparo do decodificador em um terço, com **864 parâmetros a mais** (+0,04%),
inferência **mais barata** que o controle, e `val_board_exact_acc` idêntica à dele (0,978979).
Ela também terminou na época 8 de 8 — estava subindo, como o `mhsp`.

A **S-62b** é o oposto: 1,07 M de parâmetros a mais, 27% mais reparo, 1,46× o custo, e a
validação pior e instável (0,9009 → 0,9670 → 0,9459 nas três últimas épocas, contra 0,9730 →
0,9790 → 0,9730 do controle). E os dois juntos herdam o pior dos dois: perdem um diagrama e
produzem a única leitura fatalmente ilegal de todas as variantes medidas.

**O critério 2 é o que reprova a S-62a, e ele é inmensurável neste conjunto.** A catraca
medida na seção da S-40 mostra que nenhuma mudança de modelo pode ganhar um diagrama num
conjunto em que os 8 barrados estão a 0,37 do gate. Isso não transforma a reprovação em
aprovação — a regra é a regra —, mas registra **por que** ela deve ser reaberta quando o
conjunto de campo crescer, e qual das três variantes deve ser reaberta.

### O que reprova é mais interessante que a reprovação

**O item existia para reduzir o trabalho do decodificador, e o aumentou.** A tese da S-62 é
que um modelo que decide as 64 casas juntas sabe o que hoje só o `decode.py` sabe — quantos
reis há, que peão não vive na primeira fila. Se a tese valesse, `changed_squares` cairia.
Ele subiu 27%, e o `s62ab` ainda produziu a **única leitura fatalmente ilegal** de todas as
variantes medidas (`legal` 35 → 34). Mais reparo *e* uma posição que o reparo não salvou.

**A confiança se move muito, nos dois sentidos.** Comparado ao controle, o `s62ab` mudou os
diagramas barrados assim:

| diagrama | `aug0` | `s62ab` | |
|---|---|---|---|
| Gallagher p80 | 0,414 | **0,647** | o mais perto que qualquer variante chegou do gate |
| Euwe p25 | 0,002 | **0,276** | 138× |
| Euwe p100 | 0,001 | **ilegal** | |
| **Kemeri p80** | *acima do gate* | **0,631** | **o diagrama que ele perdeu** |
| Reinfeld p40 | 0,180 · 0,254 | 0,025 · 0,000 | |

A leitura honesta disto não é "quase lá". A temperatura calibrada de cada variante diz o
contrário: 1,7185 no controle, 1,4322 no `s62ab`. **O modelo novo é mais afiado, não mais
certo** — ele afirma com mais força tanto onde acerta quanto onde erra, e o preço disso é o
Kemeri p80, que estava passando e parou de passar.

### O que isto não prova

**Não prova que a arquitetura não tem nada a dar.** São 8 épocas para 3,26 M de parâmetros
contra 2,19 M do controle, e a cabeça por tabuleiro é visivelmente mais instável entre épocas
(`val_board_exact_acc` de 0,9009 → 0,9670 → 0,9459 nas três últimas, contra 0,9730 → 0,9790 →
0,9730 do controle). É a comparação justa **a orçamento igual**, que é a que o projeto usa; um
orçamento maior é outra pergunta, e ela custa outras horas de CPU.

**O que o código deixa pronto para essa pergunta.** `--head board` e `--coords` ficam, com a
`arch_version` própria e a garantia de que um checkpoint de um não carrega no outro. O padrão
`ArchConfig()` não mudou: a produção continua sendo exatamente o que era, e a medição contra o
checkpoint de produção confirma isso dígito a dígito.

### A pré-condição da Fase 11 continua de pé, e agora com mais evidência

O roadmap condiciona a Fase 11 a "o conjunto de campo dizer que o erro restante é de
classificação". Ele continua dizendo o contrário, e o resultado desta medição é a segunda
evidência: mexer no classificador — pela entrada (S-62a), pela cabeça (S-62b) ou pelo aumento
(S-40) — não moveu a taxa de exportação em **nenhuma** das quatro variantes treinadas. O
gargalo está antes dele.

---

## S-46 · A solução como validador cruzado: **adiada por medição**

A spec marca o item como *opcional* e adverte que "depende de localizar a solução, que é um
problema de estrutura de livro". Antes de escrever o validador, a pergunta barata: **o texto
que o pipeline já lê contém um lance, e ele fecha na posição lida?**

Medido em 2026-08-11, 4 páginas por livro nos 32 livros do acervo:

| | |
|---|---|
| diagramas amostrados | 239 |
| com alguma legenda | 165 |
| **com algo que parece um lance** | **51 (21,3%)** |
| **dos quais legais na posição lida** | **7 (13,7% dos 51)** |

**Os 21,3% são uma boa notícia enganosa, e os 13,7% explicam por quê.** O texto perto de um
diagrama está cheio de notação algébrica — mas ela é a **continuação da partida**, não a
solução daquele diagrama. Os livros que mais disparam o padrão são de análise, não de
exercício: `A Matter of Endgame Technique` (11), `Euwe Band 7` (7),
`AAGAARD — Practical Chess Defence` (6). O primeiro lance que o regex acha costuma ser o
lance 32 de uma variante, e ele não é legal na posição do diagrama nem com uma leitura
perfeita.

**Por que isso reprova o item e não só o adia por preguiça.** O critério de aceite da S-46 diz
que a discordância *"nunca reescreve a posição automaticamente — vira item de revisão"*. Com
este sinal, 44 dos 51 casos virariam discordância, e a fila da S-22 existe justamente para ser
seletiva: inundá-la com falso positivo destrói a única coisa que ela entrega, que é a ordem.

O item continua correto como ideia — um lance que fecha **é** evidência forte. O que a medição
diz é que chegar a esse lance exige resolver a associação exercício↔solução por editora, que é
o trabalho que a spec previu e que o texto vizinho não substitui. Fica adiado ao lado da S-38b,
da S-44 e da S-45, pelo mesmo motivo: **a medição desaconselha, não a falta de tempo.**

---

## S-40 · Aumento dirigido: medido, **não entra** — e o que a medição ensinou sobre a métrica

Medido em 2026-08-11. Todas as variantes: `--fresh`, semente 42, 8 épocas, mesmo split,
mesmo dataset. **O controle é o `aug0` retreinado**, não o checkpoint de produção — comparar
contra produção compararia também os meses de amostras que entraram desde que ele foi treinado.

### A tabela

| variante | aumento | exportação | legais | reparo | melhor época |
|---|---|---|---|---|---|
| produção (referência histórica) | — | 0,7368 | 35 | 14 | — |
| **`aug0` — o controle** | genérico | **0,7368** (28/38) | 35 | 15 | 7 de 8 |
| `mhsp` | espelho+hachura+granulação+papel | **0,7368** (28/38) | 35 | 17 | **8 de 8** |
| `m` | só espelhamento | **0,7105** (27/38) | 35 | 15 | 7 de 8 |

**Não entra.** A métrica primária não se moveu com o conjunto dirigido, e a transformação que
a spec chamava de "a duplicação de dataset mais barata disponível" **piorou** sozinha.

### Antes de acreditar: o aumento de fato dispara

O primeiro suspeito de um resultado nulo é o módulo estar inerte. Medido sobre uma casa
escura sintética, 40 sementes:

| transformação | disparou | diferença média de pixel quando dispara |
|---|---|---|
| espelhamento (p=0,50) | 18/40 | 25,4 |
| papel (p=0,30) | 9/40 | 22,6 |
| hachura (p=0,30) | 9/40 | 25,4 |
| granulação (p=0,25) | 7/40 | 8,1 |

As quatro disparam na taxa configurada e mudam a imagem de forma substancial. O resultado
nulo é do aumento, não da implementação.

### O que se moveu: a confiança dos barrados

A taxa de exportação não distingue, mas as confianças sim:

| diagrama barrado | `aug0` | `mhsp` | |
|---|---|---|---|
| **Euwe p25** — o caso motivador da S-39/S-40 | 0,002 | **0,123** | **60×** |
| Reinfeld p150 | 0,038 · 0,044 | 0,074 · 0,121 | ~2–3× |
| Gallagher p80 | 0,414 | 0,433 | |
| Reinfeld p40 | 0,180 · 0,254 | 0,031 · 0,089 | piorou |

O Euwe p25 é a hipótese da S-40 funcionando na direção certa e **ficando 6,5× abaixo do
gate**. É exatamente o que a inspeção das imagens tinha previsto acima: *"a degradação certa
não é a hachura"*, é a qualidade do scan em cima dela.

### O achado que vale mais que o veredito: o gate é uma catraca que só desce

A pergunta óbvia é por que seis modelos diferentes deram 27 ou 28 de 38, nunca outra coisa. A
resposta está na distribuição da confiança mínima dos 36 diagramas detectados, com o controle:

| faixa | diagramas | |
|---|---|---|
| ≥ 0,99 | **27** | ███████████████████████████ |
| 0,95–0,99 | 0 | |
| 0,80–0,95 | 1 | █ |
| **0,60–0,80** | **0** | ← a vizinhança do gate está **vazia** |
| 0,40–0,60 | 2 | ██ |
| < 0,40 | 6 | ██████ |

**A distribuição é bimodal e o gate cai no vale.** O modelo ou tem certeza absoluta (27 de 36
acima de 0,99) ou está perdido. Nada está a menos de 0,37 do corte, por baixo.

A consequência é uma assimetria que explica todos os números desta seção e da S-62:

- para **ganhar** um diagrama, uma mudança de modelo precisa levar algo de ≤ 0,43 a ≥ 0,80 —
  quase dobrar;
- para **perder** um, basta derrubar um dos 27 que estavam em 0,99.

Foi o que aconteceu duas vezes: o `m` derrubou o `Kemeri` p187 (0,683) e o `s62ab` derrubou o
`Kemeri` p80 (0,631). Nenhuma variante ganhou nenhum. **A taxa de exportação, neste ponto de
operação, é uma catraca que só clica para baixo** — e isso é uma propriedade do conjunto, não
dos modelos.

### O que isto recomenda

**Não é ajustar o gate.** Baixá-lo para 0,40 traria dois diagramas do `Gallagher` e traria
junto tudo o que a S-15 existe para barrar. O vale entre 0,43 e 0,99 é a evidência de que
0,80 está num lugar razoável.

**É crescer o conjunto de campo.** A S-41 planejava 60 páginas e entregou 15, com 38
diagramas. Com 38, um diagrama vale 0,0263 de taxa e há **zero** diagramas na faixa em que
uma melhoria de modelo se manifestaria primeiro. Um conjunto maior teria diagramas em 0,6–0,8,
e aí a métrica voltaria a ter poder de resolução.

**E é anotar os livros difíceis**, que é o que a S-39 já havia apontado e que esta medição
reforça: os 8 diagramas barrados estão todos abaixo de 0,43, ou seja, são falhas de **domínio**
e não de margem. Nenhum ajuste de modelo treinado nos livros fáceis vai atravessar 0,37 de
distância. O caminho é pôr o domínio no treino.

### A ressalva que virou a segunda rodada

**O `mhsp` estava subindo quando o orçamento acabou.** Melhor época 8 de 8 (0,9730), contra o
controle que fez o melhor na 7 e piorou na 8. O controle convergiu e o dirigido não — um
aumento mais agressivo torna a tarefa mais difícil e pede mais épocas, e declarar "não entra"
com a variante ainda subindo mediria o orçamento, não o aumento.

As ablações `s` (granulação) e `p` (papel) foram trocadas por **mais 8 épocas nas duas
variantes**, pelo achado da catraca: com a vizinhança do gate vazia, uma ablação individual só
poderia produzir 27 ou 28 e não haveria como atribuir a diferença.

### A segunda rodada: 16 épocas, e o controle não tinha mais o que dar

| variante | melhor época | `val_board_exact_acc` |
|---|---|---|
| `aug0` | **7 de 16** | 0,978979 — as 8 épocas extras **não superaram** a 7ª; o checkpoint não foi tocado |
| `mhsp` | **16 de 16** | **0,981982** — melhor que o controle, e ainda na última época |

O controle está convergido, verificado e não suposto: oito épocas a mais e nenhuma bateu a
sétima. O dirigido passou o controle e continuava subindo.

### A tabela final, tudo remedido com a máquina livre

Os custos abaixo foram tomados de uma vez, sem treino concorrente — os das seções
anteriores estavam inflados por contenção e não eram comparáveis entre si. Relatórios em
`docs/metrics/field_20260811_final_*.json`.

| variante | épocas | exportação | legais | **casas reparadas** | s/diagrama |
|---|---|---|---|---|---|
| produção | — | 0,7368 | 35 | 14 | 0,331 |
| **`aug0` — o controle** | **16** | **0,7368** | **35** | **15** | **0,315** |
| `mhsp` | 8 | 0,7368 | 35 | 17 | 0,318 |
| **`mhsp`** | **16** | **0,7368** | **35** | **9** | **0,323** |
| `m` (só espelhamento) | 8 | **0,7105** | 35 | 15 | 0,291 |

**A 16 épocas o aumento dirigido reduz o reparo do decodificador em 40%** — de 15 para 9 —
com custo idêntico e a melhor acurácia de validação de todas as variantes treinadas.

### O veredito, e por que ele é desconfortável

**Pela letra do critério de aceite, a S-40 não entra**: ele pede "ganho no conjunto de campo",
a métrica primária do conjunto de campo é a taxa de exportação, e ela não se moveu. A regra é
a mesma que descartou o TTA, os pesos de classe e a temperatura calibrada, e ela não vale nada
se for afrouxada quando o resultado é simpático.

**E a medição desta seção mostra que o critério está mal-especificado para este ponto de
operação.** A catraca é o argumento: nenhuma mudança de modelo pode ganhar um diagrama num
conjunto em que os 8 barrados estão a 0,37 do gate. Reprovar por essa métrica é reprovar por
um instrumento sem resolução, não por um resultado — e o mesmo se aplica à S-62a.

O que fica registrado para quem reabrir a decisão:

- `models/s40_mhsp_16ep.pt` é o **candidato** ao próximo retreino de produção. Ele domina o
  controle em tudo que hoje é mensurável: menos reparo (9 contra 15), melhor validação
  (0,9820 contra 0,9790), mesmo custo, mesma taxa de exportação.
- Os checkpoints de 8 épocas ficaram guardados (`s40_aug0_8ep.pt`, `s40_mhsp_8ep.pt`) para a
  primeira rodada continuar reproduzível.
- A decisão de trocar o padrão de `AugmentConfig()` **não** foi tomada aqui. Ela depende de um
  conjunto de campo com poder de resolução, e é isso que a recomendação acima pede.

### Uma ironia que vale registrar

**A métrica de aceite da S-62 foi mais bem satisfeita pela S-40 do que pela própria S-62.**
Casas reparadas pelo `decode_constrained`, contra o mesmo controle de 15:

| o que mudou | reparo | |
|---|---|---|
| **aumento dirigido, 16 épocas (S-40)** | **9** | **−40%** |
| canais de coordenada (S-62a) | 10 | −33% |
| cabeça por tabuleiro (S-62b) | 19 | +27% |
| os dois juntos (S-62ab) | 19 | +27% |

A S-62 existe sobre a tese de que o modelo precisa **saber** o que o decodificador sabe —
coordenada, paridade, as outras 63 casas. O que de fato reduziu a dependência do decodificador
foi mostrar ao modelo mais páginas feias. Dado, não arquitetura.
