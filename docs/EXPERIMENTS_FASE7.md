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
