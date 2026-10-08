# Plano — as colunas das páginas de soluções na aba Texto

**2026-10-06.** Medição e plano de correção; nada do código de produção foi alterado. A evidência
(sondas, dados brutos, imagens) está em `docs/metrics/colunas_solucoes_2026-10-06/`.

## Resumo

A aba Texto reconhece colunas: os dois motores (`camada` e `glifo`; o `auto` vai pelo glifo quando
`models/char_classifier.pt` existe) passam por `text/regioes.py`, e na prosa de duas colunas a
leitura sai certa — Nunn, Aagaard, Gallagher, Koblenz, Dvoretsky, Burgess, Karpov, *Secrets of Chess
Training*, e os livros de coluna única ficam com uma.

**Ela falha nas páginas de soluções do `Yusupov — Build Up Your Chess`, e falha muito:** das 84
páginas de soluções medidas (fora as de fim de capítulo), **só 15 saem com duas colunas**; as outras
69 saem como coluna única, com a linha da esquerda intercalada com a da direita. Algumas das que
acham as colunas saem **picadas** em tiras estreitas (a p. 1201 em 7 "colunas"). O caminho da camada
erra junto — é o mesmo módulo.

**A causa tem duas metades, e as duas estão em `regioes.py`:**

1. O título da página («Solutions») e o número de página cruzam a calha: são **duas** linhas, e a
   folha só tolera uma (`colunas.LINHAS_NA_CALHA`). A folha inteira é recusada.
2. A busca por região que vem depois exige `PREENCHIMENTO_DA_COLUNA = 0,70`, e coluna de solução é
   feita de linha curta («1.♗h3!», «(1 point)» à direita, nome centralizado). Ela reprova a coluna
   larga de verdade — e **aprova a tira estreita**, que se enche com pouco. É daí que vêm tanto a
   coluna única quanto a página picada.

**A correção proposta para a primeira metade está medida e não piora nada:** com o corpo da página
tentado sem as linhas isoladas das bordas, as páginas de soluções do Yusupov em duas colunas vão de
**15/84 para 79/81**, e a régua S-194 em 1.090 folhas de 36 livros com camada não piora **nenhuma**. A segunda
metade (o preenchimento) e o quadro «Scoring» do fim de capítulo ficam como passos próprios, porque
nenhuma das réguas geométricas medidas separa a coluna de solução da lista de lances do Chernev —
que é o caso que o preenchimento existe para barrar.

## 1. O que foi medido

### 1.1 A população

Censo da camada de texto de todo `PDF/` (mais o SFC4 do Dvoretsky): livros com camada e páginas com
título de exercício/solução (`censo_exercicios.py`, `censo.json`). Os que têm população:

    Yusupov — Build Up Your Chess          783 páginas de exercício/solução (de 2.612)
    Dvoretsky — Endgame Manual             117
    Aagaard — Practical Chess Defence      113
    Karpov — Chess Combinations 1          109
    Yusupov — Método 4 (es)                 88
    Secrets of Chess Training               76
    Aagaard — A Matter of Endgame Technique 53
    Burgess, SFC4, Schiller, Seirawan, Nunn  6 a 11 cada

### 1.2 A medição do motor da aba

`medir_colunas.py`: 559 páginas (394 de exercício/solução, 165 de controle dos mesmos livros), lidas
por `ler_pagina(motor="glifo")` — o que a aba faz — e comparadas com a camada de texto: a ordem em que
o PDF emite as linhas (a régua da S-194, com o guarda dela), as linhas da camada que o glifo partiu
entre colunas diferentes, e as colunas estreitas (< 20% da largura do texto). Cada página marcada foi
**olhada**, com as colunas desenhadas sobre ela (`mosaico.py`).

O que a inspeção achou, livro a livro:

- **Yusupov — Build Up:** o defeito. Das 12 leituras de coluna única sorteadas, 11 estão erradas
  (página de duas colunas lida como uma); das páginas marcadas como picadas, as de soluções com
  «(N points)» à direita e as tarjas escuras de nome estão picadas de verdade (p. 622, 1021, 1201,
  1446, 2003). Imagens: `m1.png`, `m5.png`, `m6.png`, `m7.png`.
- **Os outros livros:** as marcas são falso alarme da medição — no Burgess as duas colunas estão
  certas; no Schiller p. 273 é uma tabela de números; no *Secrets* e no Aagaard *Matter* a "coluna
  estreita" é a legenda sob diagramas lado a lado, que está certa (`m2.png`).

**A régua da S-194 não serve para o Yusupov**, e isso decide o portão do passo 2: nesse livro a
camada emite as linhas em zigue-zague entre as colunas, o guarda marca a referência como suspeita, e
das 120 páginas de exercício só 24 têm referência confiável. A régua que vale ali é a da diagramação:
**página «Solutions» é de duas colunas** (`solucoes_yusupov.py`).

### 1.3 O número de hoje

    Yusupov, páginas «Solutions» (sem o quadro Scoring)   15 de 84 lidas em duas colunas
    Yusupov, páginas «Solutions» com o quadro Scoring       2 de 17
    Yusupov, controle (lições)                              18 de 30 lidas como coluna única

## 2. A causa, no código

**A folha inteira** (`regioes._cortar`, primeiro ramo) aceita a calha sem teste de preenchimento —
é a régua da S-190, medida em 456 páginas, e é por isso que a prosa de duas colunas sai certa. Na
p. 1917 do Yusupov a calha (224–238 pt) é cruzada por duas bandas: o título «Solutions» no alto e o
número de página, que cai **exatamente** no meio dela. `LINHAS_NA_CALHA = 1`, e a folha é recusada.

**A busca por região** (`_maior_corrida`) acha então o corpo com a calha, e reprova-o em
`_colunas_cheias`: preenchimento [0,32; 0,27] contra o mínimo de 0,70. A folha sai com uma coluna.

**O mesmo teste produz a página picada** — rastreado na p. 1446: a maior corrida *aprovada* é a
de baixo, de 12 bandas, com **quatro** faixas (206, 58, 68 e 48 pt): faixas estreitas se enchem com
pouco e passam no preenchimento, as duas colunas largas não passam. E o que sobra acima dela entra
pelo primeiro ramo, que não testa nada:

    _maior_corrida [0,49) -> bandas 37..49, faixas (10,216) (231,289) (294,362) (371,419)
    _cortar [0,37)        -> duas colunas (sem teste)

**O quadro «Scoring»** do fim de capítulo é um bloco de largura inteira com muitas bandas; ele cruza
a calha, a folha é recusada, e a corrida das soluções acima dele é reprovada pelo preenchimento.

## 3. O que foi testado em protótipo

Por *monkeypatch* (`patch_colunas.py`, variável `COLUNAS_VARIANTE`), medido nas duas réguas: a da
S-194 em **1.090 folhas de 36 livros com camada** (30 por livro, `regua_ordem.py` + `comparar_regua.py`) e a das
559 páginas do glifo.

| | o que faz | S-194: pioram / mudam | glifo | veredito |
|---|---|---|---|---|
| **P1** | sem calha na folha, tenta o **corpo** sem até 2 bandas isoladas em cada borda (vão ≥ k × passo mediano entre bandas); as bandas de borda viram região de uma coluna | **0** / 8 (k=2,5), 9 (k=2,0), 15 (k=1,5) | Yusupov soluções **15/84 → 68/81 (k=2,5), 77/81 (k=2,0), 79/81 (k=1,5)** | **adotar** |
| P2 | `COLUNA_MINIMA` 0,10 → 0,20 na folha toda (medida junto com a P1) | 1 piora (Aagaard p. 293) e 3 deixam de ser confiáveis com distância maior (Polgar p. 1036 0,02→0,23; Yusupov p. 2020 0,05→0,13 e p. 1872 0→0,06) / 50 | conserta a p. 1446 | recusada |
| P4 | 0,20 só nos pedaços da recursão de `_cortar` | 0 / 13 | quase nada: a tira nasce em `_maior_corrida` | neutra |
| P4b | 0,20 também em `_maior_corrida` | 0 / 14 | **piora**: p. 1446 e 622 voltam a coluna única (as faixas fundidas reprovam no preenchimento) | recusada |
| P3 | colunas de largura igual (≤ 1,2×) dispensam o preenchimento (medida com P1+P2) | 7 pioram — as listas de lances do Chernev (p. 172 nas duas cópias do livro, 184, 196) e do Dobonov (p. 13, 79) viram duas colunas, mais a do P2 | conserta o Scoring | recusada |
| P5 | P1 com **bloco** de borda (até 40% das bandas) | 3 pioram — Chernev p. 172 nas duas cópias (0,004→0,038) e SFC4 p. 55 por um par | — | recusada |

**P1 + P4 no glifo, as 559 páginas:** estrutura muda em 89, todas de livros com exercício; páginas
lidas como coluna única 165 → 98; nas páginas com referência confiável nos dois lados, 6 melhoram e
**0 pioram**. Seis páginas pioram a distância com referência suspeita; cinco foram
olhadas (`pior_hoje.png` × `pior_p14.png`): quatro estão **certas agora** e erradas antes (Yusupov
p. 64, 966, 1337, 2501 — a camada é que é zigue-zague), e uma é regressão pequena e real: no Aagaard *Matter*
p. 546 a legenda «★★☆☆☆ Easy…» sai com as estrelas numa coluna e a descrição noutra. É o que a
régua da folha inteira já faz hoje em qualquer página assim sem título; a P1 estende a regra ao corpo.
A sexta, Aagaard *Matter* p. 622, é o mesmo tipo de página e **não foi olhada**.

### 3.1 As réguas que não separam a lista de lances da coluna de solução

Medidas nas corridas candidatas que `_colunas_cheias` julga (`reguas_candidatas.py`), soluções do
Yusupov contra as listas de lances do Chernev e do Dobonov:

    régua                                  soluções Yusupov     listas de lances
    preenchimento da pior coluna           0,22 – 0,56          0,05 – 0,22
    borda justificada (fração rente)       0,33 – 0,47          0,12 – 1,00
    larguras (maior / menor)               1,00 – 1,15          1,10 – 2,44
    calha (pt, caminho da camada)          10 – 11              11 (Dobonov), 68 (Chernev)
    bandas com tinta nos dois lados        0,64 – 0,89          0,57 – 1,00

Nenhuma separa sozinha — o preenchimento chega a se tocar, 0,22 nos dois lados (Yusupov p. 1229 e
Dobonov p. 79) —, e combinar réguas sobre 12 páginas é ajustar a regra à amostra (o próprio cabeçalho de `regioes.py` registra que
o 0,70 de hoje já tem a folga mais estreita do módulo). **O que distingue a lista de lances é o
conteúdo** — a coluna da esquerda começa com número de lance, a da direita é um lance só —, e é por
aí que o passo 3 começa.

## 4. O plano

### Passo 1 — o corpo da folha sem as bandas isoladas das bordas (P1)

**Onde:** `text/regioes.py`, `detectar_regioes`. Depois da tentativa da folha inteira, e **só quando
ela não acha calha**: separa até `BORDA_MAX = 2` bandas no topo e na base, cada uma isolada da
vizinha por um vão ≥ `VAO_DE_BORDA` × o passo mediano entre bandas; tenta a calha no corpo com a
**mesma** régua da folha inteira (`_calhas` + `_quebrar_nas_transversais`, sem preenchimento); as
bandas de borda viram regiões de uma coluna. Onde a folha inteira acha calha hoje, nada muda — é o
mesmo princípio que preservou a S-190 na S-507.

**O número a fixar:** `VAO_DE_BORDA` entre 1,5 e 2,0. A 1,5 o Yusupov chega a 79/81 e a S-194 muda 15
folhas sem piorar nenhuma; a 2,0, 77/81 e 9 folhas. As 6 folhas a mais que 1,5 mexe (Neumann ×4,
Gunderam, Журавлев) têm de ser **olhadas** antes da escolha — a régua só garante que não
piora onde a referência é confiável.

**Testes:** em `tests/test_text_regioes.py`, com caixas sintéticas: (a) duas colunas com título
centralizado e fólio na calha → duas colunas e duas regiões de borda; (b) a mesma folha com o título
colado ao corpo (vão < limiar) → como hoje; (c) folha que já tem calha → idêntica à de hoje;
(d) coluna única com título e fólio → uma coluna. E uma página real por motor, a p. 1917 do Yusupov,
onde a sonda já está escrita.

**Portões:** `cvoff-texto-ordem --baseline docs/metrics/texto_ordem.json` (não piora) e o conjunto
anotado do passo 2.

**Regressão conhecida, a registrar no cabeçalho:** a legenda de estrelas do Aagaard *Matter* (p. 546,
e provavelmente a primeira página de exercícios de cada capítulo).

### Passo 2 — o conjunto anotado das colunas

A S-194 é cega no Yusupov (§1.2). Antes dos passos 3 e 4, um conjunto pequeno com a estrutura certa
anotada — quantas regiões, quantas colunas em cada —, tirado das páginas já olhadas nesta medição:
as 12 soluções do Yusupov, 4 páginas «Scoring», 3 picadas (622, 1201, 1446), as listas de lances
(Chernev p. 74, 172, 184, 196; Dobonov p. 13, 79), a legenda do Aagaard *Matter* p. 546, e controles
de coluna única e de prosa em duas colunas (Nunn, Koblenz, Silman). Um comando (ou um modo do
`cvoff-texto-ordem`) mede acerto de estrutura nele, com `--baseline`. **Os mesmos números deste
documento são o primeiro baseline.**

### Passo 3 — o preenchimento que reprova a coluna de solução e aprova a tira

É a causa das páginas picadas e de parte das de coluna única que a P1 não alcança. **Investigação
primeiro**, com o portão do passo 2: as listas de lances têm de continuar de uma coluna e as
p. 622/1201/1446 têm de sair com duas.

A direção que a medição aponta é o **conteúdo**: uma corrida cuja coluna da esquerda começa com
número de lance (`^\d+\.`) em quase toda banda, e cuja da direita é um token só por banda, é lista de
lances — e é ela, e só ela, que o preenchimento precisa barrar. No caminho da camada o texto já está
lá; no do glifo a decisão de região acontece antes do reconhecimento (`leitor.segmentar`), e o passo
precisa decidir entre reconhecer antes (custo) ou revisitar a região depois da linha lida.

Duas peças baratas podem ir junto, se a medição as confirmar: a P4 (piso de 0,20 nos pedaços da
recursão; neutra na S-194) e julgar a corrida pela **soma** das faixas fundidas, para que a tira
estreita não vença a coluna larga por estar "cheia".

### Passo 4 — o quadro de largura inteira na borda («Scoring»)

As 17 páginas de fim de capítulo do Yusupov (2 de 17 certas hoje, e a P1 não as alcança: o quadro tem
muitas bandas). A P5 mostrou que tratar **bloco** de borda como título quebra o Chernev, porque a
lista de lances também é um bloco separado por espaço. O que o quadro tem e a lista não tem é a
**moldura**: retângulo desenhado (vetor ou imagem na camada; contorno grande na binária do glifo).
Proposta: tirar o quadro emoldurado da projeção da calha, como `boxes.excluir_diagramas` tira o
diagrama, e deixá-lo como região transversal. Portão: as páginas Scoring do conjunto anotado e as
listas de lances.

### O que fica fora

- **As lições com coluna de diagramas** (Yusupov p. 705, 1341, 1829): o texto sai certo e só as
  legendas «Diagram 13-3» se intercalam. Pequeno, e mexer nisso é a S-216 (grade), não a calha.
- **A grade de exercícios** (Yusupov p. 1243, 2472): direção de leitura da grade é a S-216.

## 5. Ordem, tamanho e riscos

    passo 1   pequeno (uma função, ~60 linhas + testes); risco baixo, medido
    passo 2   pequeno (anotar ~30 páginas já olhadas; um modo de medição)
    passo 3   médio a grande; risco alto — é o número com a folga mais estreita do módulo
    passo 4   médio; depende de achar a moldura nos dois motores

O passo 1 entrega sozinho o grosso do ganho (Yusupov 15/84 → 77–79/81) e pode ir antes dos outros.

## 6. Decisões que são do dono do projeto

1. **`VAO_DE_BORDA` 1,5 ou 2,0**, depois de olhar as 6 folhas que só o 1,5 mexe.
2. **Em que ramo do tronco** o passo 1 entra: o checkout está em `religa-as-decisoes-orfas`, com
   `qt/foco_a_vista.py` modificado e sem commit (ciclo 11).
3. **Se a regressão da legenda de estrelas** (Aagaard *Matter*) é aceitável no passo 1, ou espera o
   passo 3.

## 7. Como reproduzir

Do diretório do tronco, com o `.venv` do tronco e `PYTHONPATH=src`; os scripts acham os dados na
própria pasta de evidência.

    # o protótipo, por variante (vazio = hoje; p1, p14, p12, p123, p45, p146 …)
    COLUNAS_VARIANTE=p1 VAO_DE_BORDA=2.0 python docs/metrics/colunas_solucoes_2026-10-06/regua_ordem.py saida.jsonl 30
    python docs/metrics/colunas_solucoes_2026-10-06/comparar_regua.py regua_hoje.jsonl saida.jsonl
    # o motor da aba, 559 páginas (~15 min; SO=Yusupov restringe)
    SAIDA=x.jsonl COLUNAS_VARIANTE=p1 python docs/metrics/colunas_solucoes_2026-10-06/medir_colunas.py
    python docs/metrics/colunas_solucoes_2026-10-06/solucoes_yusupov.py glifo_hoje.jsonl x.jsonl
    # ver as colunas sobre a página
    COLUNAS_VARIANTE=p1 python docs/metrics/colunas_solucoes_2026-10-06/mosaico.py saida.png "<livro.pdf>|<página>" ...

## 8. Execução (2026-10-08)

Ramo `claude/colunas-solucoes` do tronco, a partir do `646c84f`. Os passos 1, 2 e 4 foram
executados; o 3 ficou sem caso no conjunto anotado depois dos outros dois, e não foi feito.

**Passo 1 (S-523)** — `regioes.py`: `BORDA_MAX = 2`, `VAO_DE_BORDA = 1,5`. As 6 folhas que só o
1,5 muda foram olhadas: Neumann p. 40/61 e Gunderam p. 26 são duas colunas de verdade que a folha
não achava; Журавлев p. 88 é grade de diagramas (S-216); Neumann p. 44/49 trocam três colunas
espúrias por duas. Régua da S-194 com o código de produção: idêntica ao protótipo (0 pioram, 15
mudam). Soluções do Yusupov pelo `ler_pagina`: 79 de 81.

**Passo 2 (S-524)** — `cvoff-texto-colunas` e `docs/metrics/colunas_anotadas.json` (42 páginas).
Portão por página. Baselines só com o passo 1: camada 33/40, glifo 34/42.

**Passo 4 (S-525)** — `text/quadros.py` + `detectar_regioes(quadros=)`. A moldura é oca no glifo
(252 x 87 pt, 9 % de tinta) e é uma imagem com linhas centradas na camada. Duas armadilhas
encontradas pela régua da S-194 e corrigidas antes de fechar: (a) a imagem larga com linhas dentro
não basta na camada -- a tira de dois diagramas do Nunn, a imagem de fundo de uma lição (p. 1872) e
o lixo de OCR de um tabuleiro (Pawnless p. 269) viravam quadro; ficou «linhas que cruzam o meio,
são a maioria e têm palavras»; (b) o trecho curto sob o quadro (duas linhas em itálico + fólio)
inventava quatro colunas em três bandas -- trecho curto de corte é de uma coluna.

    conjunto anotado, glifo (o motor da aba)     34/42 -> 41/42   Scoring 8/8; resta Neumann p. 40
    conjunto anotado, camada                     33/40 -> 37/40   Scoring 5/8 (p. 131 camada quebrada;
                                                                  p. 2232/2269 a camada junta as colunas)
    régua S-194, 1.090 folhas, contra hoje       0 pioram, 1 melhora, 17 mudam de estrutura
    régua S-194, contra o passo 1 sozinho        0 mudam de distância, 2 de estrutura
    testes de texto do tronco                    1.268 passaram; 95 nos módulos tocados
    Yusupov pelo ler_pagina, com Scoring         2/15 -> 8/15 -- e as 7 restantes olhadas: têm UMA
                                                 coluna de soluções (p. 702, 1089, 1867…), ou são lição
                                                 com diagrama; a sonda rápida é que supunha duas

**Passo 3** — não executado. Depois dos passos 1 e 4 nenhuma página do conjunto erra pelo
preenchimento; o que resta pelo glifo é a Neumann p. 40 (três colunas numa folha de duas), que é
outro defeito. A régua de conteúdo continua sendo a direção, se um caso aparecer.

**Decisões tomadas** (§6): `VAO_DE_BORDA` 1,5 (olhadas as 6 folhas); ramo próprio a partir do
`646c84f`, fora do checkout com WIP; a legenda de estrelas do Aagaard *Matter* (p. 546) fica como
regressão registrada no cabeçalho de `regioes.py`.

**Evidência**: `docs/metrics/colunas_solucoes_2026-10-06/` (sondas, `regua_passo1/4.jsonl`,
`glifo_passo1/4.jsonl`, imagens) e os baselines `docs/metrics/texto_colunas{,_glifo}.json`.

## 9. Os itens

As três seções abaixo são a spec dos itens entregues neste plano, no lugar que a tabela «Onde
mora a spec de cada item» do README declara para a faixa S-523 a S-525. O ROADMAP_TEXTO (Fase 27)
traz o relato; aqui fica o critério de aceite e a sonda de cada um.

### S-523 · A banda isolada da borda não vota na calha ✅ implementada (2026-10-08)

**O que é.** Quando a projeção da folha inteira não acha calha, até `BORDA_MAX` (2) bandas em cada
borda que estejam isoladas da vizinha por `VAO_DE_BORDA` (1,5) passos medianos de entrelinha saem
da projeção, e o corpo que sobra é tentado com a **mesma** régua da folha -- sem o preenchimento
da busca por região. As bandas de borda viram regiões de uma coluna. Onde a folha inteira acha
calha, nada muda (`text/regioes.py`, `_corpo_sem_as_bordas`).

**Critério de aceite.** No conjunto anotado da S-524, as páginas «solucoes» do Yusupov saem com
duas colunas pelos dois motores; a régua da S-194 não piora nenhuma folha com referência
confiável contra a produção anterior. Medido: 13 de 13 e 0 pioras em 1.090 folhas.

**Sonda.** `tests/test_text_regioes.py::BandaIsoladaNaBordaTests` (a folha sintética de título +
fólio + colunas de linha curta) e `PaginaDeSolucoesDoYusupovTests` (a p. 1917 real, pela camada).

### S-524 · A estrutura de colunas medida contra páginas anotadas à mão ✅ implementada (2026-10-08)

**O que é.** `cvoff-texto-colunas` lê `docs/metrics/colunas_anotadas.json` -- para cada página,
quantas colunas tem a região mais dividida, anotado depois de olhar a página com as colunas
desenhadas sobre ela -- e mede o acerto pelos motores `camada` (linhas da camada de texto) e
`glifo` (caixas de caractere, como a aba Texto). O `--baseline` reprova se **qualquer** página
certa no relatório anterior estiver errada agora: o portão é por página, não por média.

**Critério de aceite.** O relatório diz, por grupo, quantas páginas acertam, nomeia as erradas
com o esperado e o achado, e separa «sem camada» e «livro ausente» de erro. Baselines publicados:
`docs/metrics/texto_colunas.json` (camada, 37 de 40) e `texto_colunas_glifo.json` (glifo, 41 de 42).

**Sonda.** `tests/test_texto_colunas.py` (medição, regressão por página, os códigos de saída) e o
comando com `--baseline` contra os dois arquivos acima.

### S-525 · O quadro de largura inteira é região de uma coluna, e corta a folha em trechos ✅ implementada (2026-10-08)

**O que é.** `text/quadros.py` acha o quadro emoldurado -- no glifo, uma caixa larga
(≥ 0,4 do texto), alta (≥ 3 escalas) e oca (≤ 0,25 de tinta) com bandas dentro; na camada, um
bloco de imagem largo cujas linhas de dentro cruzam o meio, são a maioria e têm palavras -- e
`detectar_regioes(quadros=)` faz dele uma região de uma coluna, tratando cada trecho entre quadros
pela régua de sempre. O trecho curto que o corte deixa (menos de `BANDAS_NA_REGIAO` bandas) é de
uma coluna.

**Critério de aceite.** As páginas «scoring» do conjunto anotado saem com duas colunas pelo glifo
(8 de 8); as listas de lances do Chernev e do Dobonov continuam de uma coluna (6 de 6); a tira de
dois diagramas do Nunn, a imagem de fundo de uma lição e o lixo de OCR de um tabuleiro **não**
viram quadro; a régua da S-194 não piora folha nenhuma.

**Sonda.** `tests/test_text_quadros.py` (a moldura oca contra o tabuleiro cheio; a imagem com e
sem linhas cruzando o meio) e `tests/test_text_regioes.py::QuadroDeLarguraInteiraTests`.

## 10. Depois da fusão (2026-10-08): a legenda de estrelas

A regressão registrada em §8 foi tirada: `LARGURAS_DO_CORPO = 1,5` em `regioes.py` -- as colunas
que o corpo sem as bordas acha têm de ter larguras parecidas (a legenda cortava em 2,8; as
soluções do Yusupov e a prosa de duas colunas ficam entre 1,0 e 1,15). A p. 546 entrou no conjunto
anotado (grupo «legenda», uma coluna).

    conjunto anotado, glifo (o motor da aba)     41/42 -> 42/43   só a Neumann p. 40 resta
    conjunto anotado, camada                     37/40 -> 37/41   a p. 546 sai em duas pela régua de
                                                                  folha inteira (12 linhas, título
                                                                  tolerado) -- como já saía antes de tudo
    régua S-194, contra o código fundido         0 mudam de distância, 2 de estrutura

**Neumann p. 40** (três colunas numa folha de duas, pelo glifo): o corte cai no vão alinhado entre
o número do lance e o lance na tabela de lances da coluna da direita, e a terceira «coluna» (44 pt,
à margem) é sujeira de scan -- riscos de um ou dois pixels em várias bandas. Os dois são de
conteúdo e de tinta, não de geometria da calha: é o passo 3.

### S-526 · A poeira de scan não cobre x nenhum na calha ✅ implementada (2026-10-08)

**O que é.** No caminho do glifo, `detectar_regioes(escala=)` tira da projeção da calha a caixa
mais estreita que `RISCO_EM_ESCALAS` (1/6) da escala -- poeira de scan. A camada, cujas caixas são
linhas, não passa escala e fica como estava. **Tirar também a banda de dois caracteres soltos foi
medido e recusado:** com o fólio sem voto, a régua de folha inteira achava a calha sozinha, a
borda da S-523 deixava de rodar, e o título com um vão interno ia parar dentro das colunas, partido
(uma linha da camada partida a mais em 90 páginas de exercício do Yusupov, 18 folhas confiáveis
piorando a ordem contra 15 melhorando). A banda solta na borda é da S-523; a do meio, da S-190.

**Critério de aceite.** A Neumann p. 40 sai em duas colunas pelo glifo (a calha de verdade era
fechada por um risco de 3 x 3 px dentro de uma banda de texto, além do título tolerado); o
conjunto anotado pelo glifo não perde página nenhuma; nas 559 páginas da medição, contra o código
fundido, nenhuma página com referência confiável piora a ordem.

**Sonda.** `tests/test_text_regioes.py::BandaIsoladaNaBordaTests::test_a_poeira_de_scan_nao_fecha_a_calha`
e o conjunto anotado (`cvoff-texto-colunas --motor glifo --baseline docs/metrics/texto_colunas_glifo.json`).

## 11. A poeira de scan (S-526) e o voto por banda, medido e recusado

A Neumann p. 40 pelo glifo: a calha de verdade (209–221 pt) era fechada pelo título centrado
(tolerado) e por um risco de 3 x 3 px dentro de uma banda de texto; com a segunda banda a folha
perdia a calha, caía no vão alinhado entre o número do lance e o lance (248–254) e ganhava uma
«coluna» de riscos à margem (11 bandas, 4 px de tinta mediana). Duas regras foram testadas:

- **Poeira por caixa** (`RISCO_EM_ESCALAS` = 1/6: a caixa de até 3 px numa escala de 20 não cobre
  `x` nenhum) -- **adotada**. Conjunto anotado pelo glifo **43 de 43**. Nas 559 páginas, contra o
  código fundido (junto com a guarda das larguras, §10): 20 mudam de estrutura; nas 259 com
  referência confiável, 1 melhora e 1 piora (Yusupov p. 2232, 0 → 0,08, três linhas da camada
  partidas); oito páginas do *Secrets of Chess Training* perdem uma terceira coluna de sujeira,
  a Yusupov p. 754 vai de 0,22 para 0,013.
- **Voto por banda** (banda com menos de 3 escalas de tinta não vota) -- **recusada**. Pelo
  conjunto anotado também dava 43 de 43, mas nas 559 páginas: 106 mudanças de estrutura, 18
  folhas confiáveis piorando contra 15 melhorando, e linhas da camada partidas de 31 para 118.
  A causa: com o fólio sem voto, a régua de folha inteira achava a calha sozinha, a borda da S-523
  deixava de rodar, e o título -- que tem um vão interno -- ia parar dentro das colunas, partido
  («Solu | tions»), em 90 páginas de exercício do Yusupov. A banda de dois caracteres soltos na
  borda é assunto da S-523; a do meio da folha, da tolerância da S-190.

Dados: `glifo_fundido_04623bf.jsonl` (o código fundido), `glifo_passo5_poeira.jsonl` (adotado) e
`glifo_passo5_voto_recusado.jsonl` (recusado), comparáveis com `comparar_glifo.py`.
