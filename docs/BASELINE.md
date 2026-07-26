# Baseline — o primeiro número honesto do projeto

Entrega 1.7 do [ROADMAP.md](ROADMAP.md), especificada em [SPEC.md](SPEC.md) (S-08).

**Data:** 2026-07-25 · **Commit:** `c055e71` mais o trabalho da primeira metade da Fase 2 (S-10, S-11, S-14, S-15) na árvore de trabalho · **Métricas em JSON:** [metrics/](metrics/)

Reproduzir:

```
cvoff-eval --split test --model models/piece_classifier_baseline.pt
cvoff-eval --split test --model models/piece_classifier_baseline.pt --no-constrained-decoding
```

---

## Por que este número é diferente dos anteriores

O projeto já tinha números de acurácia. Eles não mediam nada: o único checkpoint existente
(`piece_classifier.pt`) foi treinado de forma incremental sobre **todo** o `labels.csv`, com
validação sorteada a cada execução. Perguntar a acurácia dele no "conjunto de teste" é
perguntar quanto ele decorou — ele viu todas as 320 amostras.

Este baseline corrige as três coisas que faltavam:

1. **Modelo que nunca viu o teste.** `piece_classifier_baseline.pt` foi treinado do zero
   (`--fresh`) usando **apenas** o split `train`, validando no split `val`. O split `test`
   ficou reservado do começo ao fim.
2. **Split persistido e estável.** `data/splits.csv` atribui split por hash do nome do
   arquivo, não por índice de permutação — amostras novas não movem as antigas (S-07).
3. **Split por grupo, não por arquivo.** O dataset tem 234 amostras redundantes em 220
   grupos (mesmo diagrama salvo duas vezes). Se um grupo se dividisse entre treino e teste,
   o teste mediria memorização. **Verificado: 0 dos 220 grupos está espalhado entre splits.**

Sem os três, "melhorou" seria indemonstrável — que é a razão de a Fase 1 vir antes da Fase 2.

---

## Dataset e modelo

| | |
|---|---|
| Linhas em `labels.csv` | 3.195 |
| Rótulos ilegais | 0 (eram ~100; ver 1.3 no ROADMAP) |
| Amostras redundantes | 234 em 220 grupos, mantidas de propósito, mesmo split |
| Split treino / val / teste | 2.569 / 306 / 320 tabuleiros |
| Casas rotuladas | 204.480, sendo 77,0% `empty` |
| Modelo | `PieceClassifier`, 2,19 M parâmetros, entrada 64×64 em tons de cinza |
| Treino | 8 épocas em CPU, ~7,5 min/época; melhor época: a 7ª |
| `val_loss` / `val_acc` da melhor época | 0,004907 / 0,99939 |

O treino aconteceu em duas etapas (3 épocas + 5 retomando) porque a primeira execução foi
interrompida. Isso expôs um problema real: **retomar zera o controle de melhor época**, e a
primeira época da retomada sobrescreve o checkpoint mesmo se for pior. Hoje há um `warning`;
a correção é gravar metadados no checkpoint (item 5.3).

---

## Resultado — conjunto de teste (320 tabuleiros, 20.480 casas)

| Métrica | Valor |
|---|---|
| **Exata por tabuleiro** | **0,9906** (317 de 320) |
| Com até 1 casa errada | 1,0000 |
| Por casa | 0,999854 (3 casas erradas em 20.480) |
| Posições ilegais previstas | **0** |
| Rótulos ilegais no split | 0 |

**Este é o número a bater.** Qualquer mudança da Fase 2 em diante se compara a 0,9906 de
acurácia exata por tabuleiro no split `test`.

No split `val`, com o mesmo modelo: 0,9837 exata por tabuleiro, 10 casas erradas em 19.584,
0 posições ilegais. O `val` é mais difícil que o `test` neste dataset — os 320 tabuleiros do
teste caíram por sorte num conjunto mais limpo. É um recado sobre a **precisão** desses
números: 0,9906 vem de 3 erros em 320, e o intervalo de confiança de 95% em torno disso é de
aproximadamente ±1 ponto (0,98 a 1,00). Uma mudança futura que mova a acurácia exata em meio
ponto não provou nada — para ir além do ruído, ou o conjunto de teste cresce, ou a
comparação se faz sobre os mesmos tabuleiros, par a par.

### Os 3 tabuleiros que erram

| Amostra | Casa | Esperado | Predito | Confiança da casa |
|---|---|---|---|---|
| `board_20260227_005328_507704` | h6 | vazia | `P` | 0,786 |
| `board_20260302_032711_328529` | c2 | `B` | `P` | **1,000** |
| `board_20260416_041530_057626` | h6 | `Q` | `q` | 0,411 |

O do meio é o interessante: o modelo trocou bispo por peão com confiança 1,000. Nenhum
limiar de confiança pega esse caso, e a decodificação restrita também não — a posição
resultante é perfeitamente legal. É o tipo de erro que só a calibração (S-28) ou uma
arquitetura diferente (S-29) atacam.

### Calibração da confiança

| Métrica | Valor |
|---|---|
| Confiança média quando a casa está certa | 0,9998 |
| Confiança média quando a casa está errada | 0,8855 |
| Erro de calibração esperado (ECE) | 0,0001 |
| AUC detectando tabuleiro errado — **mínimo por casa** | **0,9159** |
| AUC detectando tabuleiro errado — média por casa | 0,9033 |

**A média era o número errado, e por uma razão estrutural.** 77% das casas são vazias e
triviais, então a média do tabuleiro fica ~0,97 *mesmo quando há erro* — indistinguível de
um tabuleiro perfeito. O mínimo por casa é um detector melhor (+0,0126 de AUC no teste,
+0,0219 no val), e é o que a UI, os headers do PGN e o gate de exportação passaram a usar.

---

## O efeito da decodificação com restrições (S-11)

No conjunto de teste, com este modelo: **nenhum**. O argmax já produz 0 posições ilegais em
320 tabuleiros, então a busca nunca é acionada. Os dois relatórios são idênticos:

| | argmax puro | restrita |
|---|---|---|
| Exata por tabuleiro | 0,9906 | 0,9906 |
| Posições ilegais | 0 | 0 |
| Tabuleiros reparados | — | 0 |

**Isso não significa que a S-11 não sirva — significa que o conjunto de teste não a mede.**
Com 3 casas erradas em 20.480, não há erro suficiente para violar regra nenhuma. As amostras
do dataset vêm de páginas que o usuário já recortou e corrigiu à mão; elas são o caso fácil
por construção.

Onde a S-11 tem o que fazer é em PDF que ninguém revisou. Medido em `1937 Kemeri.pdf`
(fonte figurina alemã, o caso que motivou a S-11), páginas 10–69, 47 tabuleiros detectados:

| Legalidade da leitura | argmax puro | restrita |
|---|---|---|
| Legal | 25 | **33** |
| Só o lado a jogar não fecha | 6 | 12 |
| **Ilegal de fato** | **16** | **2** |

18 tabuleiros reparados, 34 casas reescritas, 2 buscas que desistiram (e admitiram a falha
em vez de inventar posição). **Ilegalidade real cai de 34% para 4%.**

No `val`, onde há erro suficiente para a busca agir: 2 tabuleiros reparados, 2 casas viraram
a classe correta, **0 casas corretas estragadas**, 1 tabuleiro virou exato.

Em nenhuma das medições a S-11 estragou uma casa que o argmax já acertava. É o que a
teoria prevê — o argmax é o ótimo irrestrito, então o reparo só se move quando uma regra é
violada, e sempre para a alternativa mais provável.

---

## Auto-orientação (S-13): não custa acurácia, e cobre o conjunto girado

Com `mode="auto"`, cada diagrama decide a própria orientação em vez de herdar um checkbox
global. O critério de aceite da S-13 é que o conjunto de teste girado 180° iguale o original:

| conjunto | exatos | acurácia | girou 180° | marcados ambíguos |
|---|---|---|---|---|
| original, `auto` | 317 | 0,9906 | 0 de 320 | 13 |
| **girado 180°, `auto`** | **317** | **0,9906** | **320 de 320** | 13 |
| original, `mode="0"` | 317 | 0,9906 | — | 0 |

Atingido: mesmo número, e nenhuma imagem de pé foi girada por engano. Os 13 ambíguos são
tabuleiros em que a decisão se dá por um fio; nenhum deles estava errado.

O custo é uma segunda inferência por diagrama (~2× o tempo de reconhecimento, que a ~50 ms
por tabuleiro continua irrelevante ao lado do render da página).

Detalhe importante sobre como esse número foi obtido, e sobre o que ele esconde: a primeira
versão da regra passava neste mesmo critério de aceite **e girava 8 dos 47 diagramas do
Kemeri sem motivo**. A discussão está em [ROADMAP.md](ROADMAP.md) na seção da 2.6.

---

## O aviso importante: 0,9906 não é a acurácia em um PDF qualquer

Os dois PDFs medidos com o mesmo modelo, mesma configuração:

| | `1001 Winning Chess Sacrifices` (pág. 20–59) | `1937 Kemeri` (pág. 10–69) |
|---|---|---|
| Tabuleiros | 40 | 47 |
| Legais após S-11 | 40 de 40 | 33 de 47 |
| Confiança mínima, mediana | 0,997 | 0,432 |
| Confiança **média**, mediana | 1,000 | 0,967 |
| Abaixo do limiar de aceite (0,80) | 0 de 40 | 46 de 47 |

O primeiro passa inteiro pelo gate de exportação. O segundo vai inteiro para revisão — o
`.pgn` principal sai **vazio**.

Isso não é defeito do gate, é a informação que ele existe para dar. Mas explica o limite do
baseline: as amostras do `labels.csv` saíram majoritariamente de livros como o primeiro, com
fonte padrão e diagramas limpos. **0,9906 é a acurácia em diagramas parecidos com os que já
estão no dataset**, não em qualquer livro.

Repare também na coluna da confiança média: no Kemeri ela diz 0,967 para praticamente todo
tabuleiro, incluindo os 16 que o argmax leu de forma ilegal. Era esse o número que a UI
mostrava.

---

## Número de referência: o checkpoint contaminado

`piece_classifier.pt`, treinado sobre todo o dataset (portanto tendo visto o teste),
avaliado no mesmo split `test`: **0,9875** exata por tabuleiro, 1 posição ilegal
([metrics/checkpoint_original_test.json](metrics/checkpoint_original_test.json)).

Ou seja: **mais baixo** que o baseline honesto, apesar de ter decorado o conjunto de teste.
A contaminação não estava inflando o número — o treino incremental com validação sorteada a
cada execução simplesmente convergia pior. O número antigo era inútil como medida de
generalização e, por acidente, também pessimista. Fica registrado para que ninguém o
interprete como "o modelo piorou".

---

## O que este baseline não cobre

- **Nenhum teste automatizado trava esses números.** O teste de regressão de acurácia
  (item 1.8) depende de fixtures versionados (S-09), e `data/samples/` está fora do git. Até
  lá, este documento é a trava, e é manual.
- **Detecção de tabuleiro não é medida.** Todas as métricas partem de recortes 800×800 já
  corretos do `labels.csv`. Quanto o detector erra ao achar o diagrama na página é uma
  medição separada, que a S-12 vai precisar estabelecer.
- **Lado a jogar não é medido, porque nem é reconhecido.** 100% das saídas assumem brancas.
  Nas 47 leituras do Kemeri, 12 têm o lado a jogar comprovadamente invertido — e essas são
  só as detectáveis por legalidade. É o assunto da Fase 3.
- **Limiar de aceite de 0,80 é provisório.** Escolhido pela distribuição observada, não
  derivado de curva de calibração. O número justificado sai com a S-28.
