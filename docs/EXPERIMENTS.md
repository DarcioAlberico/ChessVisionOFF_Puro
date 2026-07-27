# Experimentos — Fase 5

Registro do que foi medido na Fase 5, **inclusive o que não ajudou**. Essa é a exigência
literal da S-29, e a razão é prática: experimento não registrado vira folclore ("acho que
RGB não funcionou") e custa à próxima pessoa refazê-lo.

Base: [ROADMAP.md](ROADMAP.md) Fase 5 · Spec: [SPEC.md](SPEC.md) S-26 a S-30 · Números de
referência: [BASELINE.md](BASELINE.md).

**Máquina de todas as medições:** Windows 11, 12 CPUs lógicas, 31,6 GiB de RAM,
`torch 2.10.0+cpu` — **sem GPU**. Todo tempo abaixo é de CPU e não se transfere para uma
máquina com CUDA.

---

## S-26 · Memória e carregamento

### O cache sem teto: 6,11 GiB, medidos

`BoardFenDataset._board_cache` era um `dict` que nunca liberava. Como `index_map` percorre
as 64 casas de cada tabuleiro, uma época carregava todos. Medido percorrendo uma casa de
cada um dos 3.208 tabuleiros:

| tabuleiros carregados | RSS |
|---|---|
| 0 | 0,225 GiB |
| 1.000 | 2,034 GiB |
| 2.000 | 3,824 GiB |
| 3.208 (todos) | **5,99 GiB** |

Linear, 1,79 MiB por tabuleiro — que é exatamente 800 × 800 × 3. A aritmética da S-26
estava certa; o que faltava era o número medido e o fato de que **cresce com o dataset**,
que é feito para crescer.

### Uma época de treino, antes e depois

Mesma máquina, mesmo split (2.569 tabuleiros de treino, 306 de validação), uma época,
`--fresh`, `num_workers=0`:

| | HEAD (pré-Fase 5) | Fase 5, `cache_size=256` | Fase 5, **defaults** |
|---|---|---|---|
| **pico de RSS** | **6,112 GiB** | 1,896 GiB | **1,271 GiB** |
| tempo por época | 538,5 s | 533,8 s | ~465 s |

**Critério da S-26 atingido**: 1,271 GiB contra o limite de 2 GiB, e tempo por época igual ou
melhor. A coluna do meio é a medição com o `cache_size=256` que a spec sugere; a da direita é
com os defaults que ficaram (`DEFAULT_BOARD_CACHE_SIZE=128`, `VAL_BOARD_CACHE_SIZE=4`), tirada
dos três treinos de 8 épocas do fechamento — os três deram o mesmo pico de 1,271 GiB, o que é
o esperado quando o teto do cache é que manda e não o tamanho do modelo.

### O tamanho de cache que a spec sugere é 4× o necessário

A S-26 propõe 256 tabuleiros (~470 MiB). Com `BoardGroupedSampler`, o conjunto de trabalho
não é o dataset nem um número escolhido: é a **janela** de `BOARDS_PER_CHUNK` tabuleiros.
Cada tabuleiro é lido uma vez por época desde que o cache seja ≥ a janela, e acima disso a
taxa de acerto não muda — só a memória. Daí `DEFAULT_BOARD_CACHE_SIZE = 128`, o dobro da
janela, com a folga servindo ao *prefetch* do `DataLoader`, que lê adiante e pode
atravessar a fronteira de duas janelas.

O segundo corte é o cache da validação. O loader de validação roda com `shuffle=False`,
então o acesso já é estritamente sequencial e um cache de **1** tabuleiro dá 98% de
acerto. Dar-lhe o mesmo cache do treino dobrava a memória residente sem trocar por nada;
`VAL_BOARD_CACHE_SIZE = 4`.

### O cache com teto e o amostrador são um item só, não dois

O item 1 da S-26 (cache limitado) **não funciona sem** o item 2 (amostrador por
tabuleiro), e é por isso que o cache original não tinha teto. Medido com 40 tabuleiros e
cache de 8:

| ordem de acesso | taxa de acerto do cache |
|---|---|
| `shuffle=True` puro (o de antes) | **< 0,50** |
| `BoardGroupedSampler`, janela de 8 | **> 0,95** |
| sequencial (o loader de validação) | > 0,98 com cache de **1** |

### A leitura literal da S-26 quebraria o BatchNorm

"As 64 casas do mesmo tabuleiro no mesmo lote" daria, com `batch_size=128`, lotes de **2
tabuleiros**. Isso resolve a memória e cria outro problema: um lote com a estatística de 2
posições deixa o BatchNorm ruidoso e muda a dinâmica do treino por um motivo que não tem
nada a ver com memória — uma das duas posições poderia ser um final com 4 peças.

Por isso o amostrador embaralha por **janela** de 64 tabuleiros em vez de por tabuleiro: a
localidade que o cache precisa continua lá (117 MiB residentes), e o lote volta a misturar
dezenas de posições.

### `num_workers` foi entregue, e medido não compensa nesta máquina

Carregamento puro, sem modelo:

| tabuleiros | workers=0 | workers=2 | workers=4 | workers=6 |
|---|---|---|---|---|
| 200 | **9,9 s** | 14,2 s | 19,5 s | 26,7 s |
| 800 | 39,7 s | 33,6 s | **33,4 s** | 39,3 s |

Em 200 tabuleiros os workers só custam: mais workers, pior. Em 800 o ganho aparece e é de
**16%** — mas sobre o carregamento, que é ~24% da época. Traduzido para a época inteira,
sobram ~4%.

E o custo de memória é grande. Com `num_workers=4`, o pico somado da árvore de processos
foi de **2,701 GiB** — acima do critério da S-26. Os caches não explicam isso: 128
tabuleiros divididos por 5 processos são ~46 MiB cada, 230 MiB no total. O que pesa são
**quatro interpretadores Python com o torch importado**, ~400 MiB cada. No Windows o start
method é `spawn`, então não há memória compartilhada por *copy-on-write* que amorteça isso
como haveria no Linux.

**Decisão: o padrão de `train_model` é `num_workers=0`.** O parâmetro existe, é
configurável e está exposto no `cvoff-train --num-workers`; o que a medição diz é que
ligá-lo troca 4% de tempo por 800 MiB e sai do critério de memória. Numa máquina com
`fork` a conta provavelmente muda, e é por isso que o parâmetro ficou.

**Ressalva de segurança, não de desempenho:** com `spawn`, cada worker reimporta o módulo
`__main__`. `cvoff-train` e `app_tkinter.py` têm guarda `if __name__ == "__main__"` e são
seguros. O `app_streamlit.py` não tem — não pode ter, é um script de topo executado pelo
Streamlit — e por isso passa `num_workers=0` explicitamente.

---

## Fora de fase · O teto de diagramas por página cortava diagrama de verdade

Encontrado pelo uso, não por medição: na página 17 de `A Matter of Endgame Technique`
(grade 3×3, nove diagramas) só oito eram reconhecidos, e o que faltava era o do canto
superior direito.

**A causa.** `detect_boards` seleciona candidatos em ordem de **score** e para ao atingir
`max_boards`, que era 8. Os nove diagramas daquela página pontuam entre 0,2667 e 0,3054 —
um bloco praticamente empatado —, e o nono por 0,0079 de diferença era justamente o do
canto. Score não ordena diagrama por posição, então o que cai fora é arbitrário do ponto de
vista de quem olha a página.

**Subir o teto admite lixo?** Medido em 6 livros, 15 páginas de cada, teto 8 contra teto 30:

| livro | teto 8 | teto 30 | perdidos |
|---|---|---|---|
| `A Matter of Endgame Technique` | 55 | **58** | **3** |
| `AAGAARD - Practical Chess Defence` | 34 | 34 | 0 |
| `Schiller - The Big Book of Combinations` | 83 | 83 | 0 |
| `1937 Kemeri` | 19 | 19 | 0 |
| `400 Quebra-cabeças` | 15 | 15 | 0 |
| `Polgar 5334` | 90 | 90 | 0 |

Não admite. Só o Aagaard muda, e muda recuperando exatamente os diagramas que faltavam —
os outros cinco livros dão **o mesmo número** com teto 8 e com teto 30. Quem filtra de fato
é o piso de score (`max(0,06, melhor × 0,25)`) mais a supressão por IoU; o teto era um
limite secundário grosseiro que só se manifestava atrapalhando.

**O que mudou:** `DEFAULT_MAX_BOARDS = 12` em `config.py` (cobre grade 3×3 e 3×4), no lugar
do literal `8` que estava repetido em seis arquivos. E — o defeito de fato — **o teto deixou
de cortar em silêncio**: quando ele corta candidato que passou no filtro de qualidade, sai
um `warning` com quantos foram e com que score, porque "8 de 9" na tela era
indistinguível de "a página tem 8".

---

## S-29 · Grade de arquitetura

`cvoff-experiment --epochs 3`, semente 42, split `val`, um fator por vez a partir da
referência. Reproduzir: mesmo comando; JSON em [metrics/experiments.json](metrics/experiments.json).

| variante | fator | parâmetros | exata/tabuleiro | Δ | por casa | ilegais | min/época |
|---|---|---|---|---|---|---|---|
| `referencia` | — | 2.193.869 | 0,9673 | — | 0,999183 | 0 | 8,9 |
| `rgb` | canais | 2.194.445 | 0,9771 | +0,0098 | 0,999387 | 0 | 9,6 |
| `res32` | resolução | 621.005 | 0,9804 | +0,0131 | 0,999489 | 0 | **3,9** |
| `res48` | resolução | 1.276.365 | 0,9804 | +0,0131 | 0,999438 | 0 | 5,7 |
| `gap` | cabeça | 94.797 | **0,9183** | **−0,0490** | 0,998213 | 0 | 7,7 |
| `mobilenet` | backbone | 1.530.893 | **0,9869** | **+0,0196** | **0,999796** | 0 | 5,6 |
| `pesos_balanceados` | pesos de classe | 2.193.869 | 0,9706 | +0,0033 | **0,997549** | **1** | 7,8 |

### Como ler estes números, antes de tirar conclusão deles

**São 306 tabuleiros.** Um ponto percentual são 3 tabuleiros. O BASELINE.md já registra que
±1 ponto nessa escala é ruído, e isso vale aqui: `rgb`, `res32`, `res48` e
`pesos_balanceados` estão todos a 1–4 tabuleiros da referência.

**São 3 épocas, não convergência.** O orçamento é igual para todas, o que é o que torna a
comparação justa, mas modelo menor converge mais rápido — então parte do que a tabela mede é
velocidade de convergência, não qualidade final. A referência com 8 épocas chega a 0,9837 no
`val` (BASELINE.md), acima de tudo aqui exceto a MobileNet.

Duas leituras sobrevivem a essas duas ressalvas, e só elas:

### `gap` perde feio, e a premissa da S-29 estava errada

A S-29 aponta que `Linear(128*8*8, 256)` concentra 2,1 M dos 2,19 M parâmetros e sugere
trocá-la por *global average pooling* (~95 k). Medido: **−4,9 pontos**, 15 tabuleiros
piores. É a única variante fora do ruído para baixo, e por margem grande.

A camada não era gordura. *Average pooling* colapsa o mapa 8×8 numa média por canal, o que
descarta **onde** dentro da casa está a forma — e distinguir bispo de peão, que é o erro que
o BASELINE.md registra como o mais teimoso, depende exatamente disso. Contagem de parâmetros
não é medida de utilidade.

### `mobilenet` é a única que muda de regime

0,9869 com **3** épocas, contra 0,9837 da referência com **8**. Não é comparação dentro do
ruído do mesmo orçamento: é uma variante batendo o número convergido da referência com
menos de metade do treino, e com a melhor acurácia por casa da grade (0,999796, ~4 casas
erradas em 19.584 contra 16 da referência). Pré-treino na ImageNet transfere.

Custo a considerar antes de adotar: 1,53 M parâmetros (menos que a referência), mas depende
de baixar pesos pré-treinados, o que é uma dependência de rede na primeira execução e um
item a resolver no empacotamento da S-36.

**Por isso `mobilenet` e `res32` foram para desempate com 8 épocas, decidido no split de
teste** — que é o que o critério de aceite da S-29 exige.

### O desempate, e o veredito: nenhuma arquitetura entra

8 épocas, semente 42, split de teste:

| modelo | exata/tabuleiro | por casa | parâmetros | inferência, 1 tabuleiro | val (melhor época) |
|---|---|---|---|---|---|
| baseline Fase 1 | **0,9906** (317/320) | 0,999854 | 2.193.869 | 50,1 ms | 0,9837 |
| `phase5` (mesma arq.) | 0,9844 (315/320) | 0,999756 | 2.193.869 | 50,1 ms | — |
| `phase5_res32` | **0,9906** (317/320) | 0,999854 | 621.005 | **10,9 ms** | 0,9837 (ép. 7) |
| `phase5_mobilenet` | **0,9906** (317/320) | 0,999854 | 1.530.893 | — | **0,9902** (ép. 4) |

**Os três empatam em 317 de 320.** O critério da S-29 é explícito -- "mudança de arquitetura
só entra se melhorar `board_exact_accuracy` no conjunto de teste além do ruído medido" -- e
empate não é melhora. **`DEFAULT_ARCH` fica como está.**

Três observações que valem mais que o veredito:

**A ordenação do `val` não transferiu para o `test`.** No `val` a MobileNet (0,9902) estava
claramente à frente do `res32` (0,9837); no `test` as duas dão o mesmo 317/320. O conjunto de
teste tem **3 tabuleiros difíceis** — não há resolução para distinguir modelos acima disso. É
um teto de medição, não um empate de qualidade.

**A mesma arquitetura retreinada deu um número pior que o da Fase 1** (315 contra 317).
Mesmos dados, mesmo split, mesma semente, arquitetura idêntica — o que mudou foi o caminho de
treino (amostrador por tabuleiro, early stopping em `val_board_exact_acc` em vez de
`val_loss`). Dois tabuleiros de diferença é exatamente a variância entre execuções que o
BASELINE.md avisa existir, e é a melhor evidência disponível de que **todas as diferenças
desta tabela estão dentro do ruído.**

**`res32` entrega o mesmo com 4,6× menos tempo de inferência e 3,5× menos parâmetros.** Não é
ganho de acurácia e por isso não satisfaz o critério da S-29, mas é um ganho real e fica
registrado como opção — especialmente para o empacotamento da S-36, onde tamanho e
velocidade em CPU são o assunto. Adotá-la invalidaria os checkpoints existentes, então é
decisão do dono do projeto e não efeito colateral desta fase.

---

## S-27 · Pesos de classe: a spec pede, a medição desaconselha

A S-27 propõe `class_weights="balanced"` por padrão. Medido:

| | `"none"` | `"balanced"` |
|---|---|---|
| exata por tabuleiro | 0,9673 | 0,9706 |
| **acurácia por casa** | **0,999183** | **0,997549** |
| **posições ilegais** | **0** | **1** |

A métrica que decide (exata por tabuleiro) fica **praticamente igual** — +0,0033 é um
tabuleiro em 306. O que muda de forma clara é o resto: as casas erradas vão de ~16 para ~48
em 19.584, e é a **única** configuração da grade inteira que produziu uma posição ilegal.

O padrão de erro é o que explica: três vezes mais casas erradas espalhadas por um número
praticamente igual de tabuleiros, ou seja o erro se **concentrou** em vez de atingir
diagramas novos. É o que se espera do peso inverso à frequência — ele compra recall de
classe rara vendendo precisão nas vazias, e uma dama inventada numa casa vazia é exatamente
o tipo de erro que viola contagem de peças e derruba a legalidade.

Os pesos calculados, para registro: `empty=0,10` contra `q=11,83` e `Q=10,94` — duas ordens
de magnitude. **Padrão mantido em `"none"`.** O parâmetro fica porque num dataset com classe
genuinamente ausente do treino a conta pode virar.

Nota lateral: com pesos balanceados a calibração devolveu `T = 1,0000` exatamente, e o ECE
não se moveu (0,00280 → 0,00280). Faz sentido — a loss ponderada já achata a distribuição, e
aí não há excesso de confiança para corrigir. Todas as outras variantes vieram com `T > 1`.

---

## S-28 · Calibração de confiança

Evidência que a grade já dá, antes do fechamento: **o modelo é confiante demais, e piora com
o treino.** A temperatura ajustada no `val` foi de 1,1845 com 1 época e de 1,662 com 3 na
mesma arquitetura. `T > 1` significa achatar a distribuição, ou seja o modelo afirmava mais
certeza do que tinha, e afirmava cada vez mais.

### O fechamento: a calibração não ajuda aqui, e o motivo é interessante

Treino com orçamento cheio (8 épocas, semente 42, `train` só) e avaliação no split `test`,
que nenhum destes modelos viu. O `T` é ajustado no `val` minimizando NLL, como a S-28 manda:

| modelo | exata/tabuleiro (teste) | por casa | ilegais | T | ECE |
|---|---|---|---|---|---|
| baseline Fase 1 (referência) | **0,9906** (317/320) | 0,999854 | 0 | 1,0000 | 0,000112 |
| `phase5` (mesma arquitetura, retreinada) | 0,9844 (315/320) | 0,999756 | 0 | 1,8540 | 0,000837 |
| `phase5_res32` | **0,9906** (317/320) | 0,999854 | 0 | 1,6867 | 0,000343 |
| `phase5_mobilenet` | **0,9906** (317/320) | 0,999854 | 0 | 1,0151 | 0,000124 |
| `phase5` + TTA | 0,9875 (316/320) | 0,999805 | 0 | 1,8540 | 0,001693 |

**O critério de aceite da S-28 (ECE < 0,05) está atingido com folga de duas ordens de
magnitude — e já estava antes da fase**, porque o BASELINE.md registrava ECE 0,0001. Não
havia erro de calibração para corrigir.

Isolando o efeito da temperatura no **mesmo modelo**, que é a única comparação limpa (as
linhas acima misturam modelos diferentes):

| modelo | T | exata | ECE | confiança quando acerta | rejeitados pelo gate |
|---|---|---|---|---|---|
| `phase5` | 1,0000 | 0,9844 | **0,000265** | 0,999763 | **6** de 320 |
| `phase5` | 1,8540 | 0,9844 | 0,000837 | 0,998971 | 12 de 320 |
| `res32` | 1,0000 | 0,9906 | **0,000097** | 0,999963 | **2** de 320 |
| `res32` | 1,6867 | 0,9906 | 0,000343 | 0,999588 | 3 de 320 |

**Calibrar piora o ECE em ~3× e dobra a fila de revisão, sem mudar uma casa.** A acurácia é
idêntica por construção — um escalar positivo não reordena classes.

O motivo é estrutural e vale mais que o número. O modelo acerta 99,98% das casas, então
confiança 0,9998 **já é** quase perfeitamente calibrada; achatá-la afasta a confiança da
verdade em vez de aproximar, e o ECE penaliza confiança abaixo do acerto tanto quanto acima.
A NLL, que é o que o `fit_temperature` minimiza, melhora de verdade (0,00403 → 0,00301 no
`res32`) porque é dominada pelas poucas casas erradas com confiança alta — vale a pena
sacrificar um pouco em 19.579 casas certas para reduzir o prejuízo enorme em 5 erradas. **Os
dois objetivos discordam, e o que o critério de aceite da S-28 nomeia é o ECE.**

Daí `APPLY_CALIBRATED_TEMPERATURE = False`: o `T` continua sendo ajustado e gravado no
checkpoint, porque é diagnóstico útil (T = 1,85 diz que o modelo é confiante demais no
sentido da NLL, e T = 1,0151 diz que a MobileNet já sai calibrada), mas não é aplicado. O
`cvoff-eval` reporta o valor gravado; `load_model(..., apply_temperature=True)` aplica para
quem quiser medir.

### O limiar da S-15, finalmente derivado — mas não da curva de calibração

A S-28 pede o limiar "derivado da curva de calibração". Medido, **isso é degenerado neste
split**: o modelo acerta 99,06% dos tabuleiros, então qualquer limiar ≥ 0 atinge um alvo de
99% de tabuleiros exatos, e nenhum atinge 100%. A curva não tem o que dizer.

A pergunta que tem resposta é o custo. `res32` no teste, 3 tabuleiros errados em 320:

| limiar | rejeitados | erros pegos | falso alarme | custo por erro pego |
|---|---|---|---|---|
| 0,70 | 0 | 0 de 3 | 0 | — (não pega nada) |
| **0,80** | **2** | **1 de 3** | **1** | **1 falso alarme** |
| 0,95 | 3 | 1 de 3 | 2 | — (não pega mais) |
| 0,999 | 38 | 2 de 3 | 36 | **35 falsos alarmes** |

**0,80 é o joelho da curva, e agora está justificado por medição.** Abaixo dele o gate não
pega nada; de 0,95 para 0,999 o erro extra capturado custa 35 rejeições de tabuleiro
correto. O valor deixa de ser "provisório desde a Fase 2".

Duas coisas que a curva também diz, e que importam mais que o número: **nenhum limiar pega
os três erros** — há erro confiante, o bispo lido como peão com confiança 1,000 que o
BASELINE.md descreve —, e **o gate erra mais do que acerta** (a 0,80 ele rejeita 1 correto
para cada 1 erro pego). O gate é um filtro de triagem, não um detector.

---

## S-30 · ONNX

**Paridade numérica, o que a S-30 exige.** `cvoff-export-onnx --model
models/piece_classifier_baseline.pt`, conferido em 40 tabuleiros do split de teste (2.560
casas):

| | medido | tolerância da S-30 |
|---|---|---|
| diferença máxima de probabilidade | **1,19e-07** | 1e-4 |
| diferença média | 1,45e-11 | — |
| **discordâncias de argmax** | **0** | 0 |

A segunda linha importa mais que a primeira: uma divergência minúscula exatamente num empate
troca a classe, e aí a FEN muda. O critério é `max_diff <= tolerância` **e** zero
discordâncias — as duas coisas, não a média.

O arquivo sai com 8,8 MB, opset 17, eixo de lote dinâmico (o pipeline chama o modelo com 64
casas, 448 com TTA e 512 na avaliação).

Detalhe de implementação com prazo: a exportação usa `dynamo=False`, o exportador
TorchScript, para não acrescentar `onnxscript` a um extra que existe justamente para reduzir
o que a distribuição empacotada da S-36 carrega. O torch marca esse caminho como deprecado.
Quando ele sair, a migração é remover o argumento e acrescentar `onnxscript`; a paridade de
1e-4 é conferida por um comando, então a troca é verificável.

**Velocidade, medida.** A docstring do módulo afirmava "2 a 4×" antes de haver medição.
Confirmado, mediana de 25 execuções por ponto, CPU:

| entrada | lote | torch eager | ONNX Runtime | ganho |
|---|---|---|---|---|
| 64×64 | 64 (1 tabuleiro) | 50,14 ms | 16,62 ms | **3,02×** |
| 64×64 | 448 (1 com TTA) | 343,94 ms | 118,60 ms | 2,90× |
| 64×64 | 512 (8 tabuleiros) | 391,92 ms | 134,11 ms | 2,92× |
| 32×32 | 64 (1 tabuleiro) | 10,90 ms | 3,14 ms | **3,48×** |
| 32×32 | 512 (8 tabuleiros) | 98,70 ms | 32,87 ms | 3,00× |

Consistente em ~3× independentemente do lote, o que indica que o ganho vem de fusão de
operadores e não de melhor paralelização.

Onde isso importa: no modo interativo. Reconhecer uma página de 9 diagramas com auto-orientação
são 18 inferências de tabuleiro — 0,9 s em torch contra 0,3 s em ONNX. Não muda a exportação
de um livro, onde o render da página domina.

---

## O que a Fase 5 não conseguiu medir

Registrado porque a ausência de medição é informação:

- **Nada distingue modelos acima de 317/320.** O split de teste tem 3 tabuleiros difíceis, e
  três arquiteturas diferentes empatam neles. Para escolher entre elas seria preciso um
  conjunto de teste maior ou mais difícil -- o que a Fase 1 já sinalizou ao dizer que ±1
  ponto é ruído.
- **O ECE não é mensurável nesta faixa de acurácia.** 0,0001 contra 0,0008 são calculados
  sobre ~5 casas erradas em 20.480; a diferença não sobrevive a nenhuma reamostragem.
- **O limiar da S-15 foi derivado no conjunto limpo, não no sujo.** O lugar onde o gate
  importa é PDF nunca revisado (no `1937 Kemeri` ele rejeita 46 de 47), e ali não há rótulo
  para medir falso alarme. A curva de custo acima vale para diagramas parecidos com os do
  dataset.
- **Nada disto foi medido com GPU.** `torch 2.10.0+cpu`, e todo tempo aqui é de CPU.
