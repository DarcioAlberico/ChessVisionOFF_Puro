# Roadmap — Fases 100 a 107: a prosa lida quase sem erro, e o erro que sobra marcado

O OCR de **diagrama** deste projeto está maduro, e a notação de lance dentro do texto também
anda bem. O que não está é a **prosa** — o texto que não é lance nem avaliação: a explicação do
autor, o título, a legenda, o nome do torneio. Este roadmap diz quanto ela erra hoje, **onde** e
**por quê**, e o caminho, item a item e com portão medido, até uma leitura de prosa com precisão
de livro editado — literal nos livros digitais, cuja prosa vem da própria camada do PDF, e, nos
escaneados, quase nada errado com o que sobra marcado para um clique (seção 5a). **A primeira coisa
que você vê na aba Texto chega em três a quatro semanas com um executor** (seção 5a).

**Plano e não spec.** Os itens deste documento são escritos como `- **S-7NN** · título` em lista,
e não como cabeçalho `## S-NN`: a especificação de cada um nasce num `SPEC_TEXTO_PRECISO.md`
quando o primeiro item for entregue, e só então a faixa entra na tabela "Onde mora a spec de cada
item" (ver `tests/test_docs.py`, `test_todo_item_com_secao_esta_declarado_no_indice`).

**A skill que executa este plano** é `ocr-texto-preciso` (em `~/.claude/skills/ocr-texto-preciso/`):
ela traz o protocolo de medição, as armadilhas já pagas e o roteiro do crítico; os scripts que
reproduzem cada número deste documento estão versionados em `docs/metrics/texto_prosa_2026-10-30/`
(seção 10). Quem for executar um item começa por ela.

**Base: a `main`.** O documento foi escrito no checkout de `religa-as-decisoes-orfas` (`0be1b93`),
119 commits atrás da `main` (`2a50521`), e a crítica da rodada 2 mostrou que isso importa: o
caderno (`text/caderno.py`), o itálico por caractere da S-660 e a mesa da aba Texto só existem na
`main`. **Todo item parte da `main`**, os caminhos e números de linha citados são os dela, e a linha
de base da seção 1 foi reproduzida sobre ela (1.7).

**A migração, feita em 2026-10-30.** Este documento, o relatório
`docs/metrics/texto_prosa_20261030.json` e a linha do README nasceram **sem commit**, no checkout de
outro ramo (`religa-as-decisoes-orfas`), e os scripts que mediram moravam fora do git, na skill. Foram
levados ao ramo **`texto-preciso`**, cortado da `main` em `2a50521`, em dois commits. O primeiro copia
os 16 scripts **byte a byte** para `docs/metrics/texto_prosa_2026-10-30/` — a convenção do repositório
para script de medição, como `docs/metrics/colunas_solucoes_2026-10-06/` — e é a versão que o
`scripts_sha256` do relatório identifica. O segundo troca, em sete deles, a raiz padrão (a pasta local
do dono) pela raiz do repositório onde o script mora, e aponta a seção 10 para a cópia versionada. O
`dados/` da skill não veio: tem texto de livro comercial. **Daí em diante, edita-se só no ramo**: a
cópia dos scripts que ficou na skill é a de antes da migração.

**Numeração.** Fases 100 a 107 e itens S-700 a S-772. Em 2026-10-30 o maior número tomado em
**todas** as refs era S-668 (S-999 é sentinela de teste) e a maior fase, 96. O vão S-669..S-699 e
as Fases 97 a 99 ficam livres de propósito: quatro sessões pegam itens do mesmo repositório sem
reserva, e um bloco redondo e afastado não colide.

---

## Sumário

1. [O número de hoje](#1-o-número-de-hoje)
2. [O diagnóstico: por que o glifo não chega lá](#2-o-diagnóstico-por-que-o-glifo-não-chega-lá)
3. [A meta, em números que se medem](#3-a-meta-em-números-que-se-medem)
4. [As decisões que organizam o plano](#4-as-decisões-que-organizam-o-plano)
5. [Visão geral das fases](#5-visão-geral-das-fases)
   - [5a. O que você vai ver, e quando](#5a-o-que-você-vai-ver-e-quando)
6. [As fases, item a item](#6-as-fases-item-a-item)
7. [Riscos e decisões do dono](#7-riscos-e-decisões-do-dono)
8. [Sequenciamento e paralelismo](#8-sequenciamento-e-paralelismo)
9. [Como executar um item: executor, crítico e portão](#9-como-executar-um-item-executor-crítico-e-portão)
10. [Como reproduzir os números deste documento](#10-como-reproduzir-os-números-deste-documento)
11. [Registro das revisões críticas](#11-registro-das-revisões-críticas)

---

## 1. O número de hoje

Medido em **2026-10-30** sobre o commit `0be1b93` e reproduzido, idêntico, sobre a `main`
(`2a50521`, seção 1.7); modelo `models/char_classifier.pt` (sha256 `ca4bcc00…`), Tesseract 5.5.0 com
`tessdata` **fast**, RapidOCR `ch_PP-OCRv4_rec`. Relatório completo, com os dois modos de
normalização, IC e diferenças pareadas:
[`docs/metrics/texto_prosa_20261030.json`](metrics/texto_prosa_20261030.json).

> **Todos os livros abaixo são dev, e dev contaminado** (decisão 2): a régua, a taxonomia e as regras
> de fusão foram desenhadas olhando para eles. Estes números orientam o plano; **nenhum decide
> portão**. A medição foi refeita três vezes no mesmo dia por causa da crítica (seção 11): a rodada 1
> achou o diagrama desenhado em fonte contado como prosa e a palavra colada escondida; a rodada 4
> achou lance com reticência (`...Nxc4`), símbolo Informator (`h4ʘ`) e fileira de coordenadas ainda
> contados como prosa — **metade do erro que parecia de reconhecimento era da régua**; a rodada 9
> achou a montagem duplicando o cabeçalho (`PARTIDA 13` duas vezes) na hipótese — **metade da "perda
> de leiaute" dos livros limpos era da régua**. Os números abaixo são da quarta medição.

### 1.1 A régua — e por que ela é nova

A régua de texto que o projeto já tinha (`docs/metrics/texto_pagina.json`, S-211) mede o CER da
página **inteira**, prosa e notação misturadas, contra uma camada que **não representa figurina**.
Ela penaliza o glifo onde ele acerta (`♔` contra `K` da camada) e dilui o erro de prosa no erro de
formato da notação. Não responde à pergunta deste roadmap. A régua nova:

- **referência** — a camada do PDF montada pelo mesmo `text.leitor.ler_pagina(motor="camada")`
  (mesma montagem de coluna dos dois lados), **sem as linhas que cruzam um retângulo de diagrama**
  (o Seirawan desenha o diagrama com fonte: `!""""""""#`, `ç + + + +%`);
- **ouro** — só livros **nascidos digitais**, em que a camada *é* a tinta;
- **classe de cada token da referência** — `notacao` (figurina; lance SAN, longo ou com reticência;
  número de lance; avaliação, inclusive o símbolo Informator como cada fonte o codifica; resultado;
  roque; letra de peça solta; descritiva `P-K4`/`TXPTR`; peça em cirílico), `prosa` (tem letra e não é
  notação) ou `outro` (sem letra, ou só letras acentuadas de fonte de diagrama); o **separador entre
  dois tokens de prosa é prosa**, para a palavra colada custar no CER de prosa;
- **CER por classe** — Levenshtein de caractere com recuo; cada erro vai à classe do caractere da
  referência, a inserção à do caractere seguinte (ou do último, no fim do texto);
- **WER de prosa = (S+D+I)/N** sobre alinhamento de tokens: `ifthe` custa uma troca e uma deleção, e
  o token de prosa inventado custa uma inserção;
- **figurina** — revocação e precisão da letra de peça nas posições alinhadas dos tokens de notação;
- **normalização** — `tip` (aspas, travessões e ligaduras tipográficas para ASCII, figurina para a
  letra da língua) é a de referência; `cru` sai sempre ao lado. As metas valem em `tip`, e a família
  de pontuação (S-734) é medida em `cru`, onde `—` e `-` são diferentes;
- **IC95 em dois níveis** (sorteia livros, depois folhas dentro do livro; 2.000 reamostras, semente
  fixa) e **diferença pareada** nas mesmas folhas para comparar variantes.

Para separar **leiaute** de **reconhecimento**, todos os leitores de linha leem **as mesmas caixas
que o glifo achou**; a variante `tess_oraculo` lê as **linhas visuais da camada** (cada linha da
camada apertada à tinta, e juntada à imediatamente anterior só quando é o mesmo traço de texto); e a
variante `tess_pagina` deixa o Tesseract ler a **página inteira com o leiaute dele** (`--psm 3`,
diagramas pintados de branco).

### 1.2 Ouro digital: o leitor de linha erra de 2,7× a 11× menos que o glifo na prosa

26 folhas de 7 livros (as 2 folhas perdidas inteiras saem para a 1.3), 29.270 caracteres e 5.058
palavras de prosa:

| motor | CER de prosa | IC95 (2 níveis) | WER de prosa (S+D+I) | revocação de figurina |
|---|---:|---|---:|---:|
| **glifo (produção)** | **3,61%** | 1,30–7,11% | **11,5%** | 81,2% |
| Tesseract nas linhas do glifo | 1,33% | 0,06–4,27% | 2,14% | 17,4% |
| RapidOCR nas linhas do glifo | 2,71% | 1,26–5,28% | 9,13% | 17,3% |
| **fusão v5** (seção 1.5) | **1,25%** | 0,09–3,86% | **2,27%** | 79,2% |
| Tesseract nas linhas da camada (oráculo de leiaute) | **0,16%** | 0,06–0,35% | 1,05% | 17,4% |

Diferenças pareadas (mesmas folhas): fusão − glifo na prosa **−2,36 p.p. [−4,17; −1,02]**, melhor
em **25 de 26** folhas (uma empata); na notação +1,26 p.p. [−0,41; +3,13], 8 folhas melhores e 10
piores — dentro do ruído, mas a G1 a vigia. A fusão preserva **98,9%** (530 de 536) dos tokens em que
o glifo leu figurina (presença, não acerto: a G1(a) e a G2 cuidam disso). Sem o *Chess Evolution*,
cujo leiaute ainda intercala linhas, os seis livros restantes dão glifo **2,47%** [0,88–4,46],
Tesseract 0,23%, fusão **0,28%** [0,06–0,70] (WER 0,97%), oráculo **0,10%**.

| livro | língua | fonte | glifo | Tesseract | fusão v5 | oráculo |
|---|---|---|---:|---:|---:|---:|
| Dvoretsky, *Endgame Manual* (2025) | en | Times | 1,87% | 0,13% | 0,21% | 0,13% |
| Hertan, *Forcing Chess Moves* | en | Arial | 4,07% | 0,87% | 0,89% | 0,14% |
| *Chess Evolution 2013* (2 folhas) | en | Source Sans | 14,61% | 11,96% | 10,66% | 0,76% |
| Seirawan, *Xadrez Vitorioso — Finais* | pt | Times | 0,39% | 0,09% | 0,13% | 0,09% |
| Chernev, *Melhores Finais de Capablanca* | pt | Cambria | 1,17% | 0,03% | 0,03% | 0,12% |
| Fischer, *Minhas 60 partidas memoráveis* | pt | Calibri | **6,92%** | 0,10% | 0,27% | 0,10% |
| Kravtsiv, *400 Quebra-cabeças de Estratégia* | pt | Times | 0,50% | 0,03% | 0,03% | 0,00% |

O RapidOCR do wheel é o modelo **chinês+inglês**: não tem acento, e nos quatro livros em português
92% dos erros dele (344 de 374 palavras; `taxonomia.rapid_ouro` do relatório) são exatamente isso
(`não`→`nao`). Bom em inglês limpo, inútil nas outras línguas do
acervo sem trocar de modelo.

**Estrato misto** (folhas com 20–55% de prosa: a partida comentada; 9 folhas de 5 livros): glifo
2,49%, Tesseract 0,23%, fusão 0,30%, oráculo 0,25%; WER do glifo 14,2% contra 3,8% da fusão. Na folha
de partida comentada a fusão perde **+0,08 p.p. [0,00; +0,22]** do Tesseract puro — é ali que o
roteamento token a token tem trabalho a fazer (S-721).

### 1.3 O leiaute perde páginas inteiras em silêncio — e, fora isso, custa pouco

**Na prosa digital, o reconhecimento já quase não é o problema**: o Tesseract `fast` nas caixas da
camada erra 0,16%; nas caixas do glifo, 1,33% (diferença pareada +1,17 p.p. [−0,03; +3,91]). Mas
essa diferença é quase toda **um livro** — o *Chess Evolution*, que intercala linhas: nos seis livros
limpos, o leiaute custa **+0,12 p.p. [−0,06; +0,48]**, não significativo (a primeira leitura deste
documento dizia que o leiaute era "o maior erro que sobra"; metade disso era a régua duplicando o
cabeçalho, achado da rodada 9). O que o leiaute faz de grave é outra coisa:

| livro, folha | linhas da camada | linhas que o glifo achou | glifo | Tesseract, página inteira | Tesseract nas linhas da camada |
|---|---:|---:|---:|---:|---:|
| *Chess Evolution*, 903 | 41 | **1** | 99,9% | 4,2% | 2,8% |
| *Chess Evolution*, 1210 | 47 | **1** | 99,9% | 2,1% | 0,5% |
| *Kmoch* (scan, holandês), 31 | 72 | **1** | 100% | 71 linhas lidas (medido na rodada 4) | — |
| *Kmoch*, 69 | 75 | **1** | 99,8% | 73 linhas lidas (idem) | — |
| *Kmoch*, 106 | 70 | **1** | 100% | — | — |

Nas cinco folhas o glifo devolve **um único bloco de texto** (`h` no *Chess Evolution*, `.` no
*Kmoch*) cobrindo a folha inteira. Não há exceção, aviso nem log: a página sai vazia. As duas têm uma
**região grande, escura e sem texto na borda** — a faixa lateral azul do *Chess Evolution* e a moldura
cinza do scan do *Kmoch*. Ao todo, **5 de 67 folhas medidas (7,5%)** saíram vazias sem aviso — e o
crítico da rodada 9 achou mais duas fora da amostra, *Chess Evolution* 814 e 1396. Nas
folhas 279 e 578 do *Chess Evolution* a primeira linha sai intercalada com a de baixo
(`k15n.ig..♘ht/da4.!th1o6u…`): glifo 16,1% e 12,7%, Tesseract página inteira 2,2% e 2,7%.

**O leiaute do próprio Tesseract é a reserva natural, não o padrão.** Na página inteira ele erra
2,25% no ouro completo (contra 12,9% do glifo, que perde as duas folhas) e **nunca desaba**; mas numa
folha normal é pior que as caixas do glifo (Dvoretsky 3,4%: duas colunas e legendas; insere
coordenadas e cabeçalho — 2.291 caracteres inseridos em 28 folhas). Daí a S-715: ele lê a folha
quando a guarda de leitura incompleta dispara.

### 1.4 Escaneamento simulado: o glifo desaba, e o leiaute também

As **mesmas** 28 folhas do ouro, degradadas por um perfil reprodutível (redução a ~110 dpi efetivos,
desfoque, ruído, JPEG; geometria intacta). O perfil **não está calibrado** contra scan real (S-704):

| motor | CER de prosa | IC95 |
|---|---:|---|
| glifo | **57,2%** | 40,8–73,7% |
| Tesseract nas linhas do glifo | 18,6% | 11,2–25,3% |
| fusão v5 | 19,2% | 12,0–25,7% |
| Tesseract nas linhas da camada | 6,5% | 0,8–14,6% |

O **reconhecimento** por glifo não tolera ruído, e o **leiaute** também não: ler nas caixas do glifo
custa **+12,1 p.p. [6,9; 17,1]** contra ler nas caixas da camada. A figurina sofre junto: a fusão
preserva só 73,9% das figurinas que o glifo leu, porque parte delas o glifo inventou no ruído.

### 1.5 Escaneamento real (referência de terceiro) e a regra de fusão

30 folhas de 10 livros "escaneados", 5 línguas, com a camada de OCR **de terceiro** como referência —
**esta régua só ordena motores**. Admitidas, para ordenar, as 15 folhas de 6 livros em que o oráculo
erra ≤ 10% (*Kemeri*, *Koblenz*, *Yusupov*, *Kmoch* e parte do *Nunn* têm camada desalinhada da tinta):

| motor | CER de prosa | IC95 | WER de prosa |
|---|---:|---|---:|
| glifo | 14,4% | 7,4–25,7% | 35,7% |
| Tesseract nas linhas do glifo | 6,0% | 4,2–8,3% | 13,1% |
| fusão v5 | 7,0% | 5,3–9,2% | 14,3% |
| Tesseract, página inteira | 9,3% | 6,3–12,8% | 14,5% |
| Tesseract nas linhas da camada | 3,7% | 2,1–5,4% | 10,3% |

**"Scan" aqui mistura três produções diferentes**, e o plano as separa daqui em diante (S-702, S-703,
S-705). Pelo censo do crítico da rodada 4: 12 livros do acervo são **ClearScan** (produtor "Paper
Capture", fontes `Fd######`: o glifo é vetorizado e o Unicode vem do OCR — sem ruído de scan; três dos
seis livros da prata admitida são assim); 10 livros são **scan a 144–150 dpi** nativos (Brinckmann,
Gutmayer, Kmoch, Koblenz, Dobonov, Levenfis, Mieses, Stefaniu, Yusupov *Build Up*; o Vladimirov a
110), com altura-x nativa de 7–10 px, abaixo do que o Tesseract tolera — e o filtro do oráculo tirou
dois deles da prata admitida; e 6 livros são scan a 600 dpi, reduzidos na leitura.

O glifo erra mais que o dobro do Tesseract em scan, e no *Brinckmann* (alemão, 1963) 16×: 41,0%
contra 2,5%. A fusão perde **+0,97 p.p. [−0,07; +2,98]** do Tesseract puro, e **a primeira leitura
deste documento disse que a culpa era da referência — estava errada**: das 93 palavras em que a
fusão ingênua erra e o Tesseract acerta, **82 são erro real da fusão** (`the`→`♔e` 5×, `with`→`wi♔`,
`Wissen`→`wta♔n`: o glifo vê figurina em palavra) e só 11 são figurina escrita como lixo na camada
de terceiro.

Cinco regras de fusão foram medidas, todas offline sobre as mesmas linhas
(`texto_prosa_2026-10-30/fusao_v5.py` guarda a última):

| regra | o que decide | prosa ouro | notação ouro (Δ glifo) | prosa prata |
|---|---|---:|---:|---:|
| v1 | notação de qualquer lado → glifo | 1,26% | +1,22 p.p. | 8,1% |
| v2 | só a figurina do glifo manda | 1,26% | +1,59 p.p. | 7,2% |
| v3 | v2 + veto de palavra só de letras | 1,23% | +2,17 p.p. | **6,2%** |
| v4 | v1 + veto de palavra só de letras | 1,20% | +2,04 p.p. | 6,5% |
| **v5** | v4, veto só com palavra que existe, número de lance do Tesseract só se o glifo o partiu | 1,25% | **+1,26 p.p.** | 7,0% |

**A melhor regra depende do estrato.** No digital, a v5 é a que menos piora a notação; no scan, a
**v3** — que entrega a notação em **letra** ao Tesseract — é a melhor fusão (6,2% contra 7,0% da v5), e
no *Brinckmann*, alemão com notação em letra, 3,4% contra 8,5%: no scan o glifo lê letra pior que o
Tesseract. Três aprendizados que a S-721 herda: a regra é **por estrato**; **o Tesseract estraga lance
de peão** no digital (`g4!`→`24!`, `g3`→`¢3`, `f6`→`£6`), por isso ali a notação em letra não vai
para ele sem árbitro; e **"palavra só de letras"
não é palavra** (`Bds` é o Tesseract lendo `♗d5`) — o veto precisa de léxico, e o léxico do projeto
descarta palavra com menos de 4 letras (`the`, `não` não estão nele).

### 1.6 Os erros, por família

541 palavras de prosa erradas no glifo, no ouro sem folha perdida. A família vem de comparar a
palavra da referência com o trecho alinhado da hipótese; o livro de origem vai junto, porque uma
família que só existe num livro é defeito de fonte, não de método:

| família | glifo | de onde vem | o que a causa |
|---|---:|---|---|
| letra trocada (diversas) | 33,3% | *Minhas 60* 92, *Chess Evolution* 42 | glifo isolado, sem contexto de palavra |
| **traço vertical lido como ponto** | **23,7%** | Hertan 100, *Chess Evolution* 28 | o *resize* 32×32 apaga a proporção: `l`, `I` e `.` viram a mesma mancha em fonte sem serifa |
| caixa | 10,7% | *Minhas 60* 27, Dvoretsky 10 | `caixa_alta` decide letra a letra (`DEFEsA`, `White`→`white`) |
| fronteira de palavra | 7,9% | Dvoretsky 21, *Minhas 60* 14 | `of the`→`ofthe`: vão de `f`+`t` com *kerning* |
| pontuação | 7,0% | Capablanca 21 | marca fina perdida ou trocada |
| acento (com e sem caixa) | 5,3% | *Minhas 60* 23 | til lido como trema (`não`→`näo`), `ç` como `C` |
| palavra perdida | 3,0% | *Chess Evolution* 15 | leiaute |
| aspas duplas | 2,4% | Capablanca 7, Dvoretsky 6 | `"` lido como dois apóstrofos ou parêntese |
| ligadura com `1` a mais | 2,2% | Dvoretsky 10 | `first`→`fi1rst`: a haste da ligadura vira caixa própria |

No Tesseract sobram 104 palavras, 80 delas (77%) no *Chess Evolution* (leiaute); o resto é `I`→`|`,
`Informant`→`/nformant`, `Umeå`→`Umea`. Na fusão, o mesmo mais o espaçamento de notação
(`3.Q`→`3. Q`) — 91 palavras.

A ablação dos interruptores do glifo (7 folhas, `texto_prosa_2026-10-30/ablacao.py`, medida na primeira
régua) confirma que **nenhuma** correção existente causa o `l`→`.`: todas ajudam ou são neutras — sem
`caixa_alta` o CER de prosa vai de 4,22% a 8,30%; sem `dicionario`, a 4,52%. O defeito está no
classificador, que nunca recebe altura nem proporção. E uma hipótese barata caiu, por enquanto: ampliar
o recorte 2× antes do Tesseract não paga a 220 dpi em livro digital (S-740 a refaz nos scans de 150 dpi,
onde a resposta pode ser outra).

### 1.7 A mesma medição na `main`

Toda a seção foi medida primeiro em `religa-as-decisoes-orfas` (`0be1b93`). Repetida em 2026-10-30
sobre a `main` (`2a50521`), num worktree destacado com o mesmo `char_classifier.pt` e o mesmo léxico,
as **95 folhas** dos quatro conjuntos (ouro, misto, degradado, prata) deram **texto idêntico** — glifo,
referência, Tesseract, fusão e oráculo, caractere a caractere. Os 119 commits de diferença não tocam o
caminho que lê a prosa nestas folhas; os números acima valem para a `main` sem ajuste.

---

## 2. O diagnóstico: por que o glifo não chega lá

**O classificador não é o problema principal; a arquitetura é.** Ele acerta 99,1% dos recortes que
recebe (`texto_placar_final.json`) — número **dentro da distribuição**: o split daquele treino foi por
cópia exata do PNG, não por livro, e a procedência dos 607.713 recortes é 100% desconhecida (S-201,
S-203). Mesmo descontado isso, o que a página perde está antes e depois dele:

1. **Sem contexto.** Uma `SimpleCNN` de três convoluções (2,6 MB, 314 classes) decide cada caixa
   sozinha. `rn`/`m`, `l`/`I`/`1`, `0`/`o`, `c`/`C` não são decidíveis olhando um glifo; um leitor de
   linha com modelo de sequência resolve pelo vizinho. O próprio projeto já sabia disso — é o
   argumento inteiro da S-188 (`text/leitura_de_linha.py`).
2. **O *resize* apaga geometria.** `ClassificadorDeGlifo._entrada` estica todo recorte para 32×32.
   Caixa alta já foi devolvida pela altura (`caixa_alta.py`, −22% de CER em 2026-08-24); o mesmo
   apagamento produz o traço-ponto (23,7% das palavras de prosa erradas) e não tem correção.
3. **Leiaute frágil e mudo.** Região escura na borda derruba a folha inteira (1.3); ruído quebra a
   linha (1.4); e nada mede a cobertura — a página vazia sai com a mesma cara de uma página lida.
   Fora dessas falhas grosseiras, nos livros digitais limpos o leiaute custa pouco (+0,12 p.p., não
   significativo): o que ele tem de grave é perder ou intercalar a folha inteira.
4. **A decisão da S-188 foi tomada com a régua errada.** O "modo bloco" foi medido em 2026-08-24 em
   CER de página **misturado**, contra uma camada sem figurina, e perdeu (`texto_pagina.json`: 0,1331
   com o modo bloco contra 0,1001 sem ele, em 10 folhas) —
   porque o RapidOCR destrói figurina e a régua contava isso. Na prosa, separada, o leitor de linha
   erra de 2,7× (ouro com o *Chess Evolution*) a 11× (seis livros de leiaute limpo) menos que o glifo. E o modo bloco **amarra a leitura da linha às caixas do glifo** (uma letra por
   caixa): ele não consegue consertar `ifthe` nem `fi1rst`, que são erros de **segmentação**.

**O que isso decide.** A prosa precisa de um **leitor de linha** com contexto e língua, e a notação
continua com o **glifo**, que é o único que conhece figurina. Não é um voto: é **roteamento** — cada
token vai para quem o lê bem, e a régua da seção 1 mede cada classe separada.

---

## 3. A meta, em números que se medem

Todos os alvos são medidos pela régua da Fase 100, em conjuntos **de teste que nunca serviram para
ajustar nada** (S-702), em `tip`, com o IC95 de dois níveis. Os limiares são declarados **aqui, antes**
de qualquer implementação. Um alvo passa quando **o ponto** cumpre a coluna "alvo" **e** o limite
superior do IC95 cumpre a coluna "teto" (decisão 7).

| sigla | o que | conjunto | hoje (dev, 1.2–1.5) | alvo | teto do IC95 |
|---|---|---|---:|---:|---:|
| **M0** | CER de prosa do **produto** nas folhas digitais admitidas (prosa da camada, S-716), mais auditoria visual | ouro-teste | não medido | **≤ 0,05%** e zero divergência na auditoria | ≤ 0,10% |
| **M1** | CER de prosa, digital — **bancada** do leitor de linha (`motor="fusao"`) | ouro-teste | glifo 3,61% · fusão 1,25% | **≤ 0,30%** | ≤ 0,60% |
| **M2** | WER de prosa (S+D+I), digital — bancada | ouro-teste | glifo 11,5% · fusão 2,27% | **≤ 1,0%** | ≤ 2,0% |
| **M3** | CER de prosa, scan real, **por estrato** (ClearScan, scan ≤ 150 dpi, scan ≥ 300 dpi) | scan-ouro-teste (S-703) | não medido | **≤ 1,0%** | ≤ 2,0% |
| **M4** | WER de prosa, scan real | scan-ouro-teste | não medido | **≤ 3,0%** | ≤ 5,0% |
| **M5** | CER de prosa, scan simulado | ouro-teste na família de degradação reservada e calibrada (S-704) | glifo 57,2% (perfil sem calibração) | **≤ 1,0%** | ≤ 2,0% |
| **G1** | a notação não piora | ouro-teste | fusão − glifo: +1,26 p.p. [−0,41; +3,13] | ver abaixo | — |
| **G2** | a figurina não piora | ouro-teste | revocação: glifo 81,2%, fusão 79,2% | ver abaixo | — |
| **G3** | folha perdida em silêncio | ouro, scan-ouro e varredura do acervo | 5 de 67 (e 2 fora da amostra) | **0** | — |
| **G4** | segundos por folha, CPU de 12 threads, por estrato, com a reserva da S-715 no p95 | ouro-teste e scan-ouro-teste | glifo 0,65 s (digital), 1,2–1,6 s (scan) | **digital: ≤ 2,0 s média, ≤ 4,0 s p95; scan: ≤ 3,5 s média, ≤ 6,0 s p95** | — |
| **G5** | a faixa "revisar" captura o erro | ouro-teste | não medido | **≥ 90% das palavras erradas** marcando **≤ 5%** das palavras | — |
| **G6** | negrito e itálico que chegam à tela não pioram | ouro-dev e ouro-teste | régua da S-660 (`docs/metrics/texto_estilo_por_motor.json` na `main`) | não-inferioridade contra o glifo (teto do IC da perda ≤ +2 p.p.) | — |

**Que motor cada meta mede — sem isso, M1 seria a camada comparada com ela mesma.** Depois da S-716,
`auto` põe a prosa da **camada** em toda folha digital admitida; medir M1 no padrão, no ouro-teste (que
só tem folha admitida), daria ≈ 0 por construção. Por isso:

- **M0 — o produto nas folhas digitais admitidas** (`auto`, prosa da camada): CER de prosa ≤ **0,05%**
  (teto 0,10%) contra a mesma camada — o que se mede é a **montagem** (ordem de coluna, cabeçalho,
  junção de hífen, legenda) — **mais** a auditoria visual da S-702 aplicada à saída (20 linhas por
  livro, recorte ao lado do texto, nenhuma divergência). É a única meta que fala da tinta e não da
  camada.
- **M1 e M2 — bancada do leitor de linha:** `ler_pagina(motor="fusao")` **forçado** no ouro-teste. É a
  medida limpa (referência exata) do caminho que todo livro **não** admitido recebe — scan, ClearScan,
  digital com camada de OCR —, e por isso continua sendo a meta de reconhecimento do plano. Fica
  escrito no relatório como "bancada".
- **M3 e M4 — o produto no scan** (`auto`, que lá é a fusão), contra a verdade humana.
- **M5 — a bancada no degradado reservado.**

**O tratamento das linhas que cruzam diagrama é o mesmo nos dois lugares:** a régua as tira da
referência (3 das 4 folhas do Seirawan tinham 8 linhas assim), e a admissão (critério (b) da S-702)
só reprova a folha quando há uma **fileira** de tabuleiro em fonte de diagrama — 6 ou mais caracteres
encostados na mesma linha de base — **fora** de qualquer retângulo: o desenho do tabuleiro em fonte,
dentro do retângulo, sai e a folha fica, e o caractere solto nessa fonte é figurina. A taxa de
admissão por livro está na S-716.

**As guardas, por extenso.**

- **G1 — notação.** Três condições, todas obrigatórias. (a) **Invariante sem referência:** dos tokens em
  que o glifo leu figurina, tirados os que um **veto registrado** trocou por palavra (o veto é uma
  decisão, e decisão certa não pode reprovar o portão), ≥ 99,5% chegam idênticos à saída fundida; os
  vetos são contados à parte e auditados — veto por palavra de **outra** língua é erro (hoje 3 dos 6:
  `Pas`, `Das`, `fixes` num livro em português, que o léxico por língua da S-728 barra) e tem de ser
  **zero**. E "chegar idêntico" é presença, não acerto: a precisão de figurina do glifo é 87,3%, por
  isso a G2 mede o acerto. (b) **Diferença pareada** do CER de notação, fusão − glifo, com
  limite superior do IC95 ≤ **+1,0 p.p.** A margem é larga porque a régua de notação é ruidosa (a
  camada escreve o lance noutro formato); a parte (a) é a que trava o defeito fino. (c) **Legalidade,
  sem referência:** fração das sequências de lance que fecham legais a partir da FEN do diagrama
  (S-729) não cai em relação ao glifo — é o "modelo de língua" da notação, e o único juiz que não
  depende da camada.
- **G4 — tempo, e o que ele custa no acervo.** O acervo tem **25.918 folhas em 54 PDFs** (contadas pelo
  crítico da rodada 6; `custo.PAGINAS_DO_ACERVO` ainda diz 12.000 e fica desatualizado até a S-725). A 2 s
  por folha, varrer o acervo leva ~14 h, e um livro de 800 folhas, ~27 min. A política da S-215
  (`texto_custo_20260826.json`: ler texto custava 2,21× a página sem texto, política "sob demanda")
  muda de faixa acima de 4× — a S-725 remede e a D4 decide. Este é o **único** orçamento de tempo do
  plano: a D4 o aceita e a S-725 o cumpre.
- **G4 — onde se mede.** Na **janela**, não no CLI: o tempo da virada da folha ao texto na tela, com
  "Ler ao chegar" (S-644) ligado. A leitura pode mostrar o glifo primeiro e trocar a prosa quando o
  Tesseract responder (S-717); o G4 mede o tempo até a prosa final.
- **G2 — figurina.** Revocação **e** precisão da letra de peça nas posições alinhadas (régua da
  S-700), diferença pareada fusão − glifo com limite **inferior** do IC95 ≥ −1,0 p.p. em cada uma.
  Contar figurina lida não serve: o veto que tira o `♔e` falso de `the` derrubaria a contagem e
  reprovaria um conserto certo.

**O tamanho de amostra que estes tetos exigem.** Simulado a partir da variação real do dev
(`texto_prosa_2026-10-30/amostra.py`: reamostra livros e folhas e mede a meia-largura superior do IC95
de dois níveis), para os dois sistemas que estão no nível do alvo — o oráculo e a fusão nos seis livros
limpos. A linha que conta é a da **fusão**, que é o que a bancada mede; o oráculo, mais homogêneo entre
livros, subestima a largura (a primeira versão desta tabela só tinha ele, e o crítico da rodada 9 a
derrubou):

| livros × folhas por livro | 6 × 6 | 8 × 6 | 12 × 6 | 16 × 6 | 24 × 6 |
|---|---:|---:|---:|---:|---:|
| oráculo (~0,16%): meia-largura superior, mediana | 0,22 p.p. | 0,21 p.p. | 0,16 p.p. | 0,15 p.p. | 0,12 p.p. |
| **fusão (~0,28%): mediana** | 0,18 p.p. | 0,31 p.p. | 0,28 p.p. | 0,23 p.p. | 0,17 p.p. |
| fusão: p90 | 0,55 p.p. | 0,53 p.p. | 0,40 p.p. | 0,37 p.p. | 0,25 p.p. |

O **poder** de uma comparação pareada é outra conta (`amostra.py --pareado`, S-755): mesmo uma melhora
de −55% (o oráculo contra o Tesseract nas caixas do glifo, seis livros) só abre um portão de
superioridade estrita em 7% das simulações com 8 livros, 28% com 12 e 43% com 24. Portões entre variantes, por isso, são de **não-inferioridade** com margem declarada, e
superioridade só se pede onde o efeito é grande. Daí o ouro-teste ter **≥ 12 livros × 6 folhas** (S-702, D6): com a fusão a 0,30%, 8 livros dão teto
mediano de ~0,61% — **na linha** dos 0,60%, e acima dela em cerca de metade dos sorteios (p90 0,83%); 12
livros dão ~0,58% e p90 ~0,70%. Mesmo com 12, um sistema exatamente no alvo passa no teto só em pouco
mais da metade dos sorteios — por isso o relatório do portão publica a **probabilidade de passar**
estimada pela simulação, ao lado do resultado. **Para um sistema com cauda** — um livro em que o
leiaute falha, como o *Chess Evolution* hoje — a meia-largura vai a 3 p.p. com 8 livros e a 1,7 p.p.
com 24: nenhum tamanho razoável de amostra salva um portão de média sobre leiaute quebrado. Por isso
a G3 e a Fase 101 vêm antes de qualquer portão de M1, e o relatório publica o **pior livro** ao lado
da média.

**Por que estes alvos, e não outros.** M1 e M2 não são aspiração solta: o Tesseract `fast` nas caixas
da camada **já** erra 0,16% e 1,05% no dev, sem nenhum ajuste — o que separa a produção desse número é
**leiaute** (Fase 101) e **roteamento** (S-721), não um reconhecedor que ainda não existe. A escada da
S-745 e o leitor da casa (Fase 105) trabalham sobretudo para o scan, onde o reconhecimento ainda é o
problema. M3 é três vezes M1 porque o scan perde tinta que o digital não perde. **M5 tem o
mesmo alvo da M3** e é medida numa família de degradação que nenhum treino viu (S-704): um perfil
calibrado para errar como o scan real não pode ter meta mais frouxa que o scan real.

**O orçamento de erro da M1, e quem paga cada parcela.** A soma não é portão — ela fecha por álgebra
(oráculo + leiaute + roteamento = bancada, por construção) e as parcelas interagem: consertar o
leiaute muda o sinal do roteamento, que no ouro inteiro aparece "negativo" só porque a fusão
remenda o *Chess Evolution* quebrado. **Cada parcela tem o seu portão** — o teto do IC da sua diferença
pareada abaixo do orçamento, medido depois do conserto da anterior — e um dono:

| parcela | o que mede | hoje (ouro-dev) | orçamento | quem paga |
|---|---|---:|---:|---|
| reconhecimento | Tesseract nas linhas da camada (`tess_oraculo`) | 0,16% (0,10% sem o *Chess Evolution*) | **≤ 0,15%** | já quase pago; S-741 e a escada da S-745 confirmam |
| leiaute | diferença pareada leitor de linha nas caixas do glifo − nas caixas da camada | +1,17 p.p. [−0,03; +3,91]; sem o *Chess Evolution*, +0,12 [−0,06; +0,48] | **≤ +0,10 p.p.** | Fase 101, inclusive a reserva da S-715 |
| roteamento | diferença pareada fusão − leitor de linha puro, na prosa | sem o *Chess Evolution*, +0,05 [0,00; +0,12] (0 folhas melhores, 6 piores); no misto, +0,08 [0,00; +0,22] | **≤ +0,05 p.p.** | S-721 e o árbitro da S-729 |
| **total** | CER de prosa da bancada | 1,25% (0,28% sem o *Chess Evolution*) | **≤ 0,30%** | |

**O plano B, declarado antes de abrir o teste.** Se no fim da Fase 101 a perda de leiaute não
couber em +0,10 p.p., ou se no fim da S-745 o melhor degrau não levar o reconhecimento a ≤ 0,15% no
ouro-dev **e** a Fase 105 não promover (S-755), a M1 não é rebaixada em silêncio: o dono decide entre (a) aceitar M1 ≤ 0,50% com a G5 compensando — o que sobra de erro fica
marcado para revisão, com captura ≥ 90% — ou (b) pagar o orçamento de CPU de mais uma rodada da Fase
105 (D8). A escolha fica registrada aqui **antes** da primeira leitura do ouro-teste.

---

## 4. As decisões que organizam o plano

1. **Medir antes de mexer.** Nenhum item **troca o padrão** sem a Fase 100: a régua, os conjuntos
   congelados e a linha de base publicada. A primeira entrega (5a) entra antes, como opção
   experimental medida com o protótipo da régua. É a lição mais cara deste projeto — o modo
   bloco foi recusado por uma régua que não separava prosa de notação.
2. **Os sete livros digitais medidos em 2026-10-30 são dev, e dev contaminado.** A régua, a
   taxonomia e as regras de fusão foram desenhadas olhando para eles — inclusive para Capablanca,
   *Minhas 60* e *Chess Evolution*, que a primeira versão deste documento chamava de "teste". Nenhum
   deles pode decidir um portão. O teste nasce na S-702 com livros que ninguém leu ainda.
3. **Rotear, não votar.** Notação vai ao glifo; prosa vai ao leitor de linha; o léxico arbitra só
   quando os dois divergem e exatamente um forma palavra. Voto de maioria entre motores que erram
   correlacionado não é árbitro.
4. **Nada some em silêncio.** Toda perda — página sem texto, motor ausente, idioma desconhecido —
   vira aviso visível na `PaginaLida`, no relatório e na janela. Cair para o glifo sem o Tesseract é
   permitido; cair calado não.
5. **Tudo offline.** O produto promete que nada sai da máquina no uso padrão (README). Todo motor,
   modelo e léxico novo viaja no instalador ou fica desligado com aviso; nada baixa na primeira
   execução.
6. **Split por livro, dev separado de teste, e o teste sorteado antes de ser lido.** Limiar se
   ajusta no dev; o teste só é aberto nos portões de fase. Livro duplicado no `PDF/` conta uma vez
   (memória `acervo-pdf-tem-livros-duplicados`). Folha que serviu de exemplo para desenhar um
   conserto (as do *Chess Evolution* e do *Kmoch* na Fase 101) vira **fixture de regressão**, nunca
   medida de portão.
7. **O portão olha o intervalo, não o ponto.** Todo alvo de qualidade passa só se a estimativa
   pontual cumpre o alvo **e** o limite superior do IC95 de dois níveis (livro, folha) cumpre o teto
   declarado ao lado; toda comparação entre variantes é uma diferença **pareada** nas mesmas folhas,
   com o mesmo bootstrap. Diferença dentro do intervalo não é ganho nem perda — é "não medido".
8. **Relatório declara código e modelo.** Todo número publicado em `docs/metrics/` traz commit,
   árvore suja, sha do modelo, versão e sha do `tessdata` e o manifesto do conjunto — a regra da
   S-218, estendida ao motor novo.
9. **A camada de terceiro nunca é verdade.** Ela ordena motores no conjunto "prata"; o erro absoluto
   de scan só existe com verdade humana (S-703).
10. **Tamanho de passo de PR.** Cada S-7NN é entregável sozinho, com teste, e reversível por
   interruptor; nenhum item muda o padrão de leitura sem passar pelo portão da sua fase.

---

## 5. Visão geral das fases

| fase | tema | o que passa a existir | depende de | portão |
|---|---|---|---|---|
| **100** | A régua da prosa | `cvoff-texto-prosa`, conjuntos ouro/scan/degradado congelados, linha de base | nada | relatório reproduzido duas vezes, idêntico fora o tempo |
| **101** | Nenhuma folha perdida em silêncio | guarda de leitura incompleta e campo de avisos, leiaute de reserva do Tesseract, região escura na borda, linha intercalada, leiaute sob ruído | 100 | G3 = 0; perda de leiaute ≤ +0,3 p.p. (teto do IC) |
| **102** | O leitor de linha ao lado do glifo | executor do Tesseract, fusão por token dentro de `linhas_do_glifo`, árbitro de notação pela legalidade, procedência por intervalo, língua e léxico por língua, CLIs com motor fixo | 100, 101 (S-710), D4, D6 (ou o recuo dela) | prosa ≤ 0,8% (teto 1,2%), WER ≤ 2% (teto 3%), G1, G2, G4, G6 e a G5 provisória; não-inferioridade no scan por estrato |
| **103** | O glifo sem as cegueiras do 32×32 | traço-ponto, caixa de palavra, fronteira, ligadura, aspas, acento | 100 | glifo sozinho ≤ 1,5% no ouro-dev |
| **104** | O scan de verdade | pré-processamento por linha, a escada de linhas de base (`best`, ajuste fino do Tesseract, PP-OCR latino), terceiro voto da camada, Fraktur, espaçado | 102, S-703, D7 | M3 ≤ 1,5%, M5 ≤ 1,5% |
| **105** | O leitor de linha da casa | dataset de linhas com lista de exclusão, CRNN-CTC com figurina, decodificação com léxico, dobra por família tipográfica, ficha e reversão do modelo | 100, 102, S-745, D8 | promoção só com o teto do IC da diferença pareada < 0 contra o melhor degrau, poder ≥ 80% e 3 sementes |
| **106** | Confiança, revisão e aprendizado | confiança por palavra calibrada por domínio, faixa "revisar" por palavra, correção humana como dado sem contaminar teste, monitor validado | 102, S-722 | G5 com teto do IC; curva risco–cobertura publicada |
| **107** | O portão final | medição de fecho em todos os conjuntos de teste | todas | M0–M5 e G1–G6 |

---

## 5a. O que você vai ver, e quando

**A primeira entrega** — o que muda na aba Texto antes de qualquer portão, sem trocar o padrão de
ninguém (decisão 10) e sem esperar instalador nem livro novo, porque a máquina do dono já tem o
Tesseract. **Estimativa:** 15 dias de executor somados (tabela abaixo), sem folga; com o crítico de
cada item e folga de um terço, **três a quatro semanas** com um executor só — menos com dois em
paralelo, em duas trilhas que não tocam os mesmos arquivos até se encontrarem: **S-716** (o roteador
de `text/fusao.py` e a prosa da camada) e **S-710 → S-720 → S-715** (a guarda, o executor do Tesseract
e a reserva, que usa o executor). As duas se juntam em **S-717 → S-718** (a caixa de motor e a marca),
que dependem de ambas — a S-717 precisa do roteador da S-716, do aviso da S-710 e do executor da
S-720 (seção 8).

| item | o que você vê | dias |
|---|---|---:|
| **S-716** | nos livros **digitais** (Dvoretsky, Capablanca, *Minhas 60*, Hertan…), a prosa sai **da própria camada do PDF** — que é a tinta impressa — e a notação continua do glifo, com figurina; a prosa fica praticamente sem erro | 3 |
| **S-710** | a folha que o programa não conseguiu ler aparece com um **selo** "esta folha não foi lida inteira", em vez de sair vazia em silêncio | 2 |
| **S-715** | essa folha é relida por outro leiaute e **volta** (o *Chess Evolution* 903 e 1210, o *Kmoch*), com o selo dizendo que foi a reserva | 2 |
| **S-720 + S-717** | na caixa de motor da aba, uma opção nova: **"Glifo + Tesseract (experimental)"** — a prosa do Tesseract com a notação do glifo nos livros escaneados; o padrão não muda | 5 |
| **S-718** | a marca "revisar" passa a ser **por palavra** e honesta: aponta onde os dois leitores discordaram ou onde a palavra não existe no léxico, com um botão "próxima a revisar" | 3 |

**Nada da primeira entrega muda arquivo gravado.** A procedência por intervalo da S-716 e as marcas
da S-718 vivem **em memória**, recalculadas a cada leitura; o caderno e o `.cvtxt` continuam gravando
o texto como hoje, e o `ESQUEMA` só sobe com a S-710 (avisos) e a S-722, no G102 — por isso desligar a
primeira entrega é desligar uma opção, sem migração.

A régua da Fase 100 vem **junto**, não antes: cada item da primeira entrega se mede com os scripts de
`texto_prosa_2026-10-30/` (o protótipo da régua já existe) e entra atrás de interruptor; o portão G100
só é exigido para **trocar o padrão**.

**O que você vai ver, em palavras por folha.** Uma folha do ouro tem ~195 palavras de prosa (5.058
em 26 folhas); uma folha escaneada da prata, ~272 (4.084 em 15). Um livro de 300 folhas, ~58 mil a
~82 mil.

| quando | livro digital admitido (a prosa vem da camada, S-716) | prosa lida pelo leitor de linha — bancada no digital (M1/M2) | livro escaneado |
|---|---|---|---|
| hoje (glifo) | ~22 palavras erradas por folha (WER 11,5%) | ~22 por folha | ~97 por folha (WER 35,7% na prata) |
| primeira entrega | **praticamente nenhuma na prosa** (M0: o erro que sobra é de montagem, ≤ 0,05% de CER) | ~4,4 por folha com a opção experimental (WER 2,27%; ~1,9 nos seis livros de leiaute limpo) | ~39 por folha com a opção experimental (WER 14,3% na prata, referência de terceiro) |
| G102 (a fusão vira padrão onde a camada não serve) | igual: M0 mantida | ≤ 4 por folha (WER ≤ 2%) | não-inferior ao Tesseract puro |
| G107 | igual: M0 mantida | ≤ 2 por folha (M2; ≤ 600 num livro de 300 folhas) | ≤ 8 por folha (M4) |
| G107 com a G5 (90% das erradas marcadas) | — | ~1 palavra errada **sem marca** a cada 5 folhas | ~4 sem marca a cada 5 folhas |

**Por isso "precisão de livro editado" quer dizer duas coisas, e o documento as separa:** no livro
**digital**, é literal — a prosa vem da camada, que é o texto que o editor escreveu; no livro
**escaneado**, é M3/M4 mais a G5 — quase nada errado, e o que sobra marcado para um clique.

**O que preciso de você agora, em uma linha cada:**

- **Até 6 de novembro — começar as transcrições (D3).** Ganha: o único número honesto de erro em livro
  escaneado. Custa: ~15 horas suas ao longo de semanas, numa tela feita para isso (S-703); antes de
  pedir as 15 horas, o executor mede o tempo em duas folhas. Se disser não: o produto sai dizendo que o
  erro de scan não foi medido.
- **Até 20 de novembro — trazer 12 livros digitais que o programa nunca leu (D6; 8 no mínimo).** Ganha: a prova de
  que a melhora vale para livro novo, e não só para os sete que já usamos. Custa: escolher e copiar os
  PDFs. Se disser não: os portões rodam num teste "provisório", com os mesmos livros, e a promessa fica
  rotulada assim.
  **Recebidos em 2026-10-30:** 76 PDFs em `PDF Digitais/`, fora do git como o `PDF/`. O inventário,
  feito sem leitor nenhum (metadados, famílias de fonte e o perfil de admissão da S-702), separou:
  12 fora (6 livros de scan, 2 com produtor de OCR, 1 sem camada de texto, 1 com camada sem prosa
  legível, o próprio Dvoretsky e o original em inglês do *400 Quebra-cabeças*); 11 com o produtor e as
  fontes do Dvoretsky, que vão ao estrato *fonte vista* e não contam para os 12; 17 que repetem a série
  de outro, porque o teste leva um livro por série; e **36 livros independentes**: 33 em inglês, 2 em
  português e 1 em espanhol. Dos 36, 25 são ebook convertido pelo calibre, um estrato a declarar no
  manifesto. A lista livro a livro fica em `dados/2026-10-30/d6_inventario.tsv` da skill, fora do
  repositório. **No sorteio da S-702, o livro em espanhol não deu nenhuma folha com prosa** (é de
  exercícios), e o teste congelou com 16 livros em inglês e português; **falta um livro digital com
  prosa numa terceira língua**, que entra a mais, sem trocar os sorteados (decisão do dono).
- **Antes de a fusão virar padrão (~dezembro) — D1, D4 e D9.** Levar o Tesseract no instalador (+~48 MB
  e as licenças dele); aceitar que ler a folha com texto fique ~2–3× mais lento; e dizer quem escreve o
  livro exportado (seção 7).
- **Mais adiante, cada um quando o item chegar — D2, D5, D7, D8:** downloads (um a um, com nome,
  origem, tamanho e licença), uso de livros e pesos no treino, e o orçamento de CPU da Fase 105.

---

## 6. As fases, item a item

Cada item traz **contexto** (o que o executor precisa saber sem ler o resto), **entrega**,
**verificação** (o comando), **saída** (o critério de pronto) e **reversão**. Os comandos usam o
interpretador do projeto, `.venv/Scripts/python.exe` (memória `interpretador-do-projeto-e-o-venv`).

### Fase 100 — A régua da prosa

O primeiro trabalho não melhora nada: ele torna mensurável o que se vai melhorar. Os scripts de
`texto_prosa_2026-10-30/` (`banco.py`, `rodar.py`, `resumo.py`, `repontuar.py`, `degradar.py`) são o
protótipo medido em 2026-10-30; esta fase os traz para dentro do pacote, com teste.

- **S-700** · `text/regua_prosa.py`: normalização, classes de token, alinhamento e placar por classe.
  - *Contexto:* o protótipo é `texto_prosa_2026-10-30/banco.py`. O alinhamento é Levenshtein com recuo,
    vetorizado por linha em `numpy` (mínimo acumulado para a inserção); 2.000×2.000 caracteres em ~1 s.
  - *Entrega:* funções puras `normalizar`, `classe_do_token`, `alinhar`, `pontuar` → `Placar`. Sem
    I/O. O placar traz, por classe, erros e totais; **inserções** à parte e por classe; WER de prosa
    **(S+D+I)/N** sobre alinhamento de tokens (o `ifthe` custa uma troca e uma deleção, e o token
    de prosa inventado custa uma inserção); precisão e revocação de **letra de peça** nas posições
    alinhadas dos tokens de notação; e as trocas palavra a palavra. O separador **entre dois tokens
    de prosa** é prosa — senão a palavra colada não aparece no CER de prosa. A inserção no fim do
    texto vai à classe do último caractere, não a uma classe que ninguém publica.
  - *Verificação:* `pytest tests/test_text_regua_prosa.py` — alinhamento confere com Levenshtein de
    força bruta em 500 pares aleatórios; atribuição de inserção; `if the`→`ifthe` custa no CER de
    prosa e dá S=1, D=1 no WER; token inventado dá I=1; normalização idempotente.
  - *Saída:* os números do relatório de 2026-10-30 reproduzidos pela função nova, iguais até a 4ª casa
    — **depois** de a S-701 consertar o classificador, nunca antes (reproduzir antes trava o defeito).
  - *Reversão:* módulo novo, sem chamador em produção.
- **S-701** · O classificador de token da régua, testado contra os casos que já enganaram.
  - *Contexto:* a primeira versão contou `f1-e1`, `b4×c3`, `Kg2=` e a letra de peça solta do
    Capablanca como prosa, e inflou o erro de prosa de **todos** os motores (0,0386 → 0,0328 no glifo).
    `text/notacao.fatiar` é **conservador de propósito** (S-208: lance não pode virar prosa no PGN);
    a régua precisa do inverso — ser inclusiva na notação, porque prosa contada como notação só
    some do placar, e notação contada como prosa o envenena. São duas funções, e isso é escrito.
  - *Contexto, rodada 4:* mesmo depois da primeira correção, o classificador chamava de prosa o lance
    com reticência sem número (`...Nxc4`, `…Rxb2`), o símbolo Informator como a fonte o codifica
    (`h4ʘ` no Kravtsiv) e a fileira de coordenadas desenhada em fonte (`/èéêëìíîï)` no Seirawan) —
    cerca de 50 dos 112 erros do oráculo, que passou de 0,38% a 0,16% quando a régua parou de contá-los.
    O acervo tem ainda notação **descritiva** (inglesa `P-K4`, `QxQch`; espanhola `T3Cj`, `AXD`,
    `TXPTR mate` no Reinfeld es e no Dobonov), **cirílica** (Bolesláviski: `Кре2`, `Лb4`, homóglifos
    `е`, `Ь`) e a captura com `X` e `:` (`DXg7`, `Pd5:`), com a cruz de xeque lida como `t` (`TXg7t`).
  - *Entrega:* `classe_do_token(token, lingua)` com letras de peça por língua (en `KQRBN`, pt `RDTBC`,
    es `RDTAC`, de `KDTLS`, fr `RDTFC`, nl `KDTLP`, ro `RDTNC`, ru `КрФЛСК`), notação longa, com
    reticência, descritiva e cirílica, captura com `x`, `X`, `:` e `×`, roque com `0` e `O`, avaliação
    colada e símbolos Informator, figurina; retângulo de diagrama **crescido de uma casa** ao excluir
    linhas da referência, e linha só de `a–h`/`1–8` ou só de letras acentuadas de fonte de diagrama
    como `outro`.
  - *Verificação:* tabela de ≥ 80 tokens rotulados à mão nas **8 línguas do acervo** (en, pt, es, de,
    nl, fr, ro, ru) — `A`, `O`, `I`, `E` são prosa;
    `B`, `D`, `T`, `C` soltos são notação; `e-pawn` é prosa; `Nimzowitsch` é prosa), mais os casos
    que a régua tem de **recusar** como prosa e que nenhuma regex de lance pega: o diagrama desenhado
    em fonte (`!""""""""#`, `ç + + + +%`, `/èéêëìíîï)` no Seirawan) e o lixo de figurina da camada de
    terceiro (`Wxf7`, `.l:tb1`, `'ii'xa4`). Esses saem pela admissão (S-702) ou viram classe
    `ruido`, nunca `prosa`.
  - *Saída:* zero divergência na tabela; relatório diz a versão do classificador.
  - *Reversão:* a régua não tem chamador em produção; trocar a versão do classificador muda o número
    publicado, e por isso a versão vai no relatório.
- **S-702** · Conjuntos ouro-dev e ouro-teste congelados, com admissão que não usa motor nenhum.
  - *Contexto:* **a camada só é referência quando é a tinta.** O *Gaprindashvili* parece editorado e
    tem notação em lixo de OCR (`l:l'.xe3`) sob figurinas impressas. A primeira regra de admissão
    proposta ("o Tesseract nas caixas da camada erra ≤ 2%") foi reprovada pelo crítico: ela depende
    do motor avaliado e das caixas, não do texto — no *Koblenz* p. 14 esse oráculo erra 19% e o
    Tesseract nas caixas do glifo 2,8%. **O acervo quase não tem livro digital de prosa que ninguém
    leu**: os sete digitais com prosa já foram usados (decisão 2); Polgar 5334 é quase só diagrama; o
    único digital de prosa ainda não lido é o *Chess Evolution 2014* (pdfTeX, sem produtor de OCR), da
    mesma série e diagramação de um livro dev — não serve de teste. Os demais são scan.
  - *Entrega, admissão:* uma folha entra no ouro se, **sem rodar OCR nenhum**: (d) o PDF **não** é
    produção de OCR — produtor `Paper Capture`, `Image Conversion`, `FineReader`, `Omniscan`, `Google
    Books`, ou fontes `GlyphLessFont`, `HiddenHorzOCR`, `Fd\d+` reprovam o livro inteiro, porque
    ClearScan **parece** digital (glifo vetorizado) e o Unicode dele veio de um OCR; (a) todo trecho de
    texto da camada é visível — modo de renderização ≠ 3 e opacidade > 0 em `page.get_texttrace()`,
    lido num módulo de `text/` e não em `pdf_text.py`, que está no digest da S-218 —
    e não está **coberto** por imagem de página inteira desenhada **depois** dele (ordem do
    `page.get_bboxlog()`; a imagem de fundo desenhada antes, como no *Chess Evolution*, não reprova);
    e o **livro** não é scan com camada invisível: se mais da metade das 30 folhas de perfil
    (igualmente espaçadas, fixas pelo número de páginas) que têm texto têm texto invisível, o livro
    inteiro sai — é o que recusa a folha de carimbo do *Kemeri*, texto visível sobre o scan (a
    primeira versão decidia isso por folha, "menos de 200 caracteres sobre imagem de página inteira",
    e recusava folhas de solução do *Chess Evolution* — rodada 10); (b) **fora** dos retângulos de
    diagrama (crescidos de uma casa), nenhuma **fileira** de tabuleiro em fonte de **diagrama** — 6 ou
    mais caracteres na mesma linha de base, cada um encostado no anterior (vão menor que meia altura).
    O desenho do tabuleiro em fonte **dentro** do retângulo (Dvoretsky, `Chess-Merida`, 64 trechos por
    diagrama; Seirawan) sai da referência e não reprova a folha (a primeira redação reprovava, e
    derrubava todo o Dvoretsky — rodada 10); o caractere solto nessa fonte fora do diagrama é
    figurina, notação, vai ao glifo e não reprova. O (b) reconhece a fonte de diagrama **pelo nome**:
    a do Seirawan (`TTE…`, embutida sem nome) ele não reconhece, e ali só o retângulo protege;
    (c) nenhum caractere de uso privado em fonte de **texto** (em fonte de figurina ele é a figurina)
    nem um dos padrões de lixo de figurina conhecidos (`l:l'.`, `'ii'`, `.tg`). E uma **auditoria visual** por livro: 20 linhas sorteadas, recorte ao
    lado do texto da camada, conferidas por gente ou por agente que não seja o executor; uma
    divergência reprova o livro.
  - *Entrega, conjuntos:* `assets/texto_prosa/ouro.json` — versionado, **fora de `data/`** (o
    `conftest` desvia o `DATA_DIR` da suíte para uma pasta vazia, e o teste do manifesto ficaria vácuo),
    lido pela raiz do repositório e incluído em `VERSIONADOS` da disciplina da suíte — com `{livro,
    identidade (a de `caderno.identidade_de`, reaproveitada e não reimplementada), folha, lingua,
    estrato, split}`. **ouro-dev** = os sete livros de 2026-10-30 (cinco, depois da auditoria).
    **ouro-teste** = ≥ 12 livros digitais **novos** (decisão D6 — o dono traz; 8 é o mínimo, seção 3), ≥ 3 línguas,
    folhas sorteadas por `sha256(identidade + folha)` **antes** de qualquer leitura, e o manifesto
    commitado antes da primeira corrida. Dois estratos por livro: **prosa** (≥ 55% de prosa) e
    **misto** (20–55%, a partida comentada, onde mora o `the`→`♔e`). Até o teste existir, há um
    **teste provisório**: folhas nunca lidas dos livros dev, sorteadas do mesmo jeito, e todo número
    dele sai com o rótulo "provisório (livro visto)".
  - *Verificação:* `cvoff-texto-prosa --conjunto ouro --conferir-admissao` lista folha rejeitada e o
    critério (a, b, c ou auditoria); e o teste de **falsificação** do (b): com os retângulos de diagrama
    apagados, a admissão recusa por (b) as folhas com diagrama do Dvoretsky — no protótipo
    (`admissao.py --sem-retangulos`), 29 de 30, todas com fileira de 8.
  - *Saída:* manifesto versionado; teste que reprova folha sem identidade, livro nos dois splits, ou
    manifesto de teste com data posterior à primeira leitura registrada.
  - *Reversão:* manifesto é dado versionado; um livro reprovado sai do manifesto num commit que diz o
    critério.
  - *Entregue em 2026-10-30* (ramo `texto-preciso`): `text/admissao.py` (paridade com o protótipo
    nas 360 folhas da tabela da S-716), `text/ouro.py` e `assets/texto_prosa/ouro.json` — 16 livros e
    96 folhas no teste, só identidades no manifesto (o repositório é público). A auditoria visual
    reprovou 5 de 27 livros, entre eles dois dos sete dev; o dev ficou com 5 livros e 27 folhas. Spec,
    números, desvios e achados em `docs/SPEC_TEXTO_PRECISO.md`; a terceira língua do teste fica
    pendente.
  - *Achado:* a linha de base da seção 1 mediu dois livros dev contra uma referência com defeito — no
    *Chess Evolution 2013* a ligadura `ft` perde o `t` na camada, e no *Capablanca* figurinas da tinta
    ficam fora da linha da camada. Os números ficam como publicados, com esta ressalva; a S-706 os
    republica nos cinco livros dev admitidos.
- **S-703** · Scan-ouro: 30 folhas escaneadas com verdade humana.
  - *Contexto:* é o **único** jeito de dizer o erro absoluto em scan; a camada de terceiro (prata)
    só ordena. Sem este item, M3 e M4 não existem.
  - *Entrega:* ≥ 30 folhas de ≥ 8 livros escaneados, ≥ 5 línguas, **estratificadas por produção e
    resolução** — ClearScan, scan ≤ 150 dpi nativos (≥ 1/3 das folhas: é um quarto do acervo) e scan
    ≥ 300 dpi —, incluindo tipografia do século XIX (Neumann 1870, Bachmann 1899), metade no estrato
    misto; M3 e M4 publicados por estrato. **A transcrição não pode ser
    ancorada no sistema avaliado**: ela parte da camada de terceiro (ABBYY/Paper Capture, que nunca
    é motor nosso) ou do zero, nunca da saída do glifo, do Tesseract ou da fusão. **Ferramenta:** um
    modo *transcrição* na aba Texto, com **um caderno por passada** (a segunda digitação não pode abrir
    a primeira — o caderno de hoje reabre a folha com o que já foi corrigido, S-612), linha a linha com
    a faixa impressa ao lado (S-643), e procedência própria **`transcricao:<passada>`** — nem `humano`
    (que hoje carimba o bloco inteiro) nem `corrigido_de` (S-762), que o scan-ouro recusa. Antes de
    pedir as 15 horas, medir o tempo em **duas** folhas. **Dupla digitação em
    ≥ 20% das folhas (≥ 6)**, por outra pessoa ou noutro dia, às cegas da primeira — acordo de
    caractere **≥ 99,9%**, senão a folha volta. O acordo tem de ser dez vezes mais fino que o alvo
    M3 (1%), ou a régua some no ruído. Formato: JSONL com sha da imagem renderizada e da folha.
    **Onde mora:** é texto de livro comercial — fora do repositório e do bundle, numa pasta própria
    com backup declarado (são ~15 h de trabalho humano), e só o manifesto (livro, folha, sha) no git.
  - *Verificação:* `cvoff-texto-prosa --conjunto scan-ouro --acordo` imprime o acordo da dupla
    digitação.
  - *Saída:* 30 folhas com acordo ≥ 99,9% nas duplicadas; split dev/teste por livro (metade/metade),
    sorteado antes da transcrição.
  - *Reversão:* folha com acordo abaixo de 99,9% volta para transcrição; nada do produto muda.
  - *Dono:* ~20–30 min por folha e mais a dupla digitação; **cerca de 15 horas humanas** (decisão D3).
- **S-704** · Degradação sintética reprodutível e **calibrada** como fatia de robustez.
  - *Contexto:* o perfil `medio` de 2026-10-30 equivale a ~110 dpi e leva o glifo a 57,2%, contra
    14,4% na prata (scan real): ele não foi calibrado contra nada, e um alvo (M5) sobre um perfil sem
    calibração mede uma imagem que ninguém imprime.
  - *Entrega:* `text/degradacao.py` com os perfis de `texto_prosa_2026-10-30/degradar.py`, semente por
    folha, geometria intacta, aplicado às **mesmas folhas** do ouro (`--paginas`). Depois da S-703, um
    perfil `calibrado`: o que faz o Tesseract errar no ouro degradado o mesmo que ele erra no
    scan-ouro-dev (±25% relativo). Duas famílias de degradação com geradores **diferentes**: uma para o
    aumento de dados da Fase 105, outra **reservada** para medir a M5 — senão o modelo da casa joga em
    casa. Usado só como fatia; nunca somado ao ouro.
  - *Verificação:* teste de reprodutibilidade (mesma folha e semente → mesmos bytes) e `resumo.py` do
    Tesseract no perfil calibrado contra o scan-ouro-dev, publicado ao lado.
  - *Saída:* mesma folha e semente → mesma imagem, byte a byte (teste); o perfil calibrado publicado
    com a medida que o calibrou.
  - *Reversão:* módulo de medição, sem chamador em produção.
- **S-705** · Prata: livros escaneados com camada de terceiro, rotulados como "só para ordenar", e
  estratificados como o scan-ouro (ClearScan / ≤ 150 dpi / ≥ 300 dpi).
  - *Entrega:* manifesto `assets/texto_prosa/prata.json`; o relatório imprime a palavra **"ordenação"**
    ao lado de todo número prata, e nunca o soma ao ouro.
  - *Verificação:* `cvoff-texto-prosa` (ou, até a S-706 existir, `reproduzir.py` + `resumo.py` de
    `texto_prosa_2026-10-30/`) sobre `prata`, com o filtro `--oraculo-max 0.10` registrado no relatório.
  - *Saída:* relatório com a palavra "ordenação" em todo número prata e os três estratos separados.
  - *Reversão:* manifesto; sem chamador em produção.
- **S-706** · `cvoff-texto-prosa` e a linha de base publicada.
  - *Entrega:* CLI que roda um manifesto, grava `docs/metrics/texto_prosa_<data>.json` (caminhos
    relativos — `test_nenhum_relatorio_publica_a_raiz_do_disco`), com commit, árvore suja, sha do
    modelo e do `tessdata`, versão do classificador de token, IC95 de dois níveis, as duas
    normalizações (`tip` e `cru`, ver 1.1), taxonomia por motor e tempo por etapa **em chave
    separada** (`segundos_*`), e uma leitura de aquecimento descartada (memória
    `primeira-leitura-do-processo-difere`). Os subconjuntos publicados saem de um filtro com
    argumentos registrados no relatório (`texto_prosa_2026-10-30/filtrar.py`), nunca de seleção à mão.
  - *Verificação:* rodar duas vezes; achatar os dois JSON em chaves escalares e comparar **fora**
    `segundos_*` (memória `reproduzir-relatorio-antes-de-republicar`).
  - *Saída:* duas corridas idênticas fora as chaves `segundos_*`; README cita o relatório; o relatório
    traz `codigo.pacote` e `codigo.commit` de cada folha (o que `rodar.py --exigir-src` já grava).
  - *Reversão:* CLI novo; o relatório antigo continua no disco.
  - *Da S-702:* o CLI grava `primeira_leitura_do_teste` no manifesto do ouro na primeira vez que lê o
    split `teste`, e não o lê sem gravar — é o que dá dente à guarda "teste lido antes do
    congelamento" —; grava também, por livro, a primeira leitura de cada livro acrescentado depois do
    congelamento (o que tem `entrou_em`), num campo novo do manifesto, no dia de `entrou_em` ou depois,
    e acrescenta a `ouro.problemas` a guarda que reprova a leitura de antes dessa data; traz o
    `--conjunto ouro --conferir-admissao` que a S-702 adiou; e a linha de base nova se mede nos cinco
    livros dev aprovados na auditoria, não nos sete de 2026-10-30.

  - **Portão G100:** as duas corridas idênticas; linha de base no ouro-dev, ouro-teste, degradado e
    prata publicada; README cita o relatório.
- **S-707** · A suíte irmã medida na mesma régua, antes da S-721.
  - *Contexto:* a `Suite_de_Edicao_de_Xadrez` já funde a prosa do Tesseract com a figurina do glifo
    deste projeto, token a token (`src/caissa/ocr/engines/glyph.py`: "a prosa fica do Tesseract; as
    figurinas viram figurinas"), tem um árbitro que prefere a camada quando ela é confiável
    (`src/caissa/ocr/arbiter.py`) e modelos Tesseract por livro. O roadmap não pode desenhar a fusão
    sem medir a que já existe ao lado.
  - *Entrega:* o pipeline de OCR da suíte rodado nas folhas do ouro-dev e da prata, publicado como
    mais uma linha da régua (`suite`).
  - *Verificação:* `resumo.py --pares fusao_v5-suite` no ouro-dev e na prata, por estrato.
  - *Saída:* decisão escrita sobre o que a S-721 reaproveita da suíte (regras, árbitro, modelos por
    livro) — o que vencer na régua fica; nada é reescrito sem medir.
  - *Reversão:* medição.

### Fase 101 — Nenhuma folha perdida em silêncio

- **S-710** · Guarda de leitura incompleta, e o campo de avisos que a página ainda não tem.
  - *Contexto:* nas cinco folhas perdidas de 2026-10-30 — *Chess Evolution* 903 e 1210, *Kmoch* 31, 69 e
    106 (base 1) — a página inteira some, sem log. `PaginaLida` **não tem** campo de aviso
    (`text/pagina.py`); a decisão 4 e as S-715, S-720, S-721 e S-723 dependem de um. **A primeira versão
    desta guarda foi reprovada por medição** (crítico da rodada 5): "tinta coberta pelas caixas de linha
    ≥ 95%" dá **1,000** na folha perdida — a caixa única e degenerada cobre a folha inteira — e 0,942 em
    folhas boas do Dvoretsky e do Seirawan. Também falha "altura da maior linha ÷ mediana" (47,9 numa
    folha normal). O sinal que separa, medido nas 95 folhas dos quatro conjuntos
    (`texto_prosa_2026-10-30/cobertura.py`), é a **densidade de leitura**: caracteres lidos ÷
    componentes de tinta fora dos diagramas. Folhas normais: **0,903 a 1,285** (ouro, misto, prata e
    degradado); as cinco perdidas: **0,001 a 0,007**.
  - *Entrega:* `PaginaLida.avisos: tuple[Aviso, ...]` (código, mensagem, dado), com ida e volta em
    `para_json`/`de_json`; **`ESQUEMA` sobe de 1 para 2**, com leitura do formato 1 (a S-722 sobe para
    3); a densidade calculada depois da leitura; abaixo de **0,5** → aviso `folha_nao_lida` com o
    valor; a aba Texto mostra o selo na folha; o relatório da régua publica a distribuição da densidade
    por conjunto.
  - *O que ela não pega (rodada 9):* a densidade vê **perda total**, não parcial — no degradado, três
    folhas do Capablanca saem com 35–39% dos caracteres da referência e densidade 0,97–1,16; e dá falso
    alarme em **capa** (Dvoretsky 0,284: arte vira componente sem letra). Daí: (1) a promessa da S-710
    é **perda total** (G3), e o nome do aviso é `folha_nao_lida`; (2) um **segundo sinal**, de perda
    parcial — linhas de texto estimadas pela projeção horizontal da tinta fora dos diagramas contra
    linhas lidas, e, quando a camada existe, caracteres lidos contra caracteres da camada —, com aviso
    próprio `leitura_parcial`; (3) só conta componente **com altura de letra** (8 a 60 px a 220 dpi),
    para a arte da capa não pesar; (4) folha sem texto (capa, branco, só diagrama) é classe à parte e
    não avisa.
  - *Verificação:* uma amostra **estratificada por tipo de folha** — prosa, misto, só notação, índice,
    tabela, capa, folha em branco, só diagrama — em todos os livros do acervo, com taxa de falso alarme
    e de perda publicadas por tipo; as cinco folhas de 2026-10-30 e as duas que o crítico achou fora da
    amostra (*Chess Evolution* 814 e 1396, densidade 0,038 e 0,004) avisam; o corte de 0,5 só fica se
    nenhuma folha **com texto** cair abaixo de 0,7 na varredura dos livros dev.
  - *Saída:* G3 = 0 nas 95 folhas e na varredura, com os números publicados.
  - *Reversão:* o aviso não muda texto nenhum; o corte é constante. O `ESQUEMA` 2 **não** é reversível
    (versão antiga não abre arquivo novo), e por isso entra junto com o primeiro uso dos avisos.
- **S-711** · Região escura na borda: faixa colorida e moldura de scan.
  - *Contexto:* duas aparências, um mecanismo. A faixa lateral azul com letra branca vertical do
    *Chess Evolution* (folhas 903 e 1210) e a moldura cinza do scan do *Kmoch* (folhas 31, 69 e 106)
    fazem o glifo devolver **um** bloco para a folha inteira (`h`, `.`). `text/negativo.py` (S-195)
    trata tarja em negativo **dentro** do texto, não região de página.
  - *Entrega:* achar regiões grandes, escuras ou de cor uniforme encostadas na borda **antes** de
    medir a escala; tratá-las como região própria (ler em negativo quando houver texto claro, senão
    excluir com aviso), e tirar a influência delas da `escala_fora_dos_diagramas` e da segmentação.
  - *Verificação:* fixture sintética na suíte (faixa escura na borda + texto ao lado: a região é
    achada e as linhas também); na régua, as cinco folhas e a varredura do acervo com `inspec.py` e a
    densidade de leitura da S-710.
  - *Saída:* as cinco folhas viram casos de regressão — **na suíte, como fixtures sintéticas** que
    reproduzem o mecanismo (folha desenhada com faixa escura na borda e texto ao lado, sem livro
    comercial e sem classificador: a asserção é sobre regiões e linhas achadas); **na régua, como
    folhas reais** que passam a ler com CER de prosa (Tesseract nas linhas do glifo) a ≤ 1 p.p. do oráculo; o portão é medido em
    folhas **não** usadas no conserto — as outras folhas dos dois livros, e uma varredura do acervo
    inteiro que conta folha com `≤ 2` linhas lidas onde a camada tem `≥ 10`. Nenhuma folha do
    ouro-dev muda de texto.
  - *Reversão:* a detecção de região escura entra atrás de constante; desligada, a folha volta a ser
    lida como hoje (e a reserva da S-715 a cobre).
- **S-712** · Linha intercalada.
  - *Entrega:* caixa de linha com altura > 1,8× a mediana da coluna é partida pela projeção
    horizontal antes de ler. As folhas 279 e 578 do *Chess Evolution* são fixture; o efeito é medido
    nas folhas não vistas do mesmo livro e no ouro-dev.
  - *Verificação:* fixture sintética de duas linhas encostadas que viram uma caixa; na régua, as
    folhas do *Chess Evolution* não vistas.
  - *Saída:* nenhuma caixa de linha com altura > 1,8× a mediana no ouro-dev; perda de leiaute do
    *Chess Evolution* abaixo de +1 p.p. nas folhas não vistas.
  - *Reversão:* constante; desligada, a caixa fica inteira como hoje.
- **S-713** · Perda de leiaute como métrica de primeira classe.
  - *Entrega:* o relatório da régua publica, por livro, `perda_de_leiaute = CER(leitor de linha nas
    caixas do glifo) − CER(leitor de linha nas caixas da camada)`, e a variante `tess_pagina` (o
    Tesseract com o leiaute dele) ao lado — medida **antes** de S-711, S-712 e S-714, para cada conserto
    de leiaute saber quanto da reserva ele dispensa.
  - *Verificação:* o relatório da S-706 traz `perda_de_leiaute` por livro com IC pareado e o
    `tess_pagina` ao lado.
  - *Saída:* a métrica existe no relatório e o G101 a lê dali.
  - *Reversão:* só relatório.
- **S-714** · Leiaute sob ruído.
  - *Contexto:* no perfil médio a perda de leiaute é 12,1 p.p. [6,9; 17,1]. Suspeitos, em ordem: binarização
    (janela fixa contra escala da letra), poeira passando no filtro de componente, e linhas que se
    tocam depois do desfoque.
  - *Verificação:* `cvoff-texto-prosa` (ou, até a S-706 existir, `reproduzir.py` + `resumo.py` de
    `texto_prosa_2026-10-30/`) no degradado calibrado, pareado contra o leiaute de hoje.
  - *Saída:* perda de leiaute ≤ 2 p.p. no perfil médio, sem piorar o ouro limpo.
  - *Reversão:* cada mudança de binarização ou filtro atrás de constante; desligada, volta a de hoje.
- **S-715** · O leiaute de reserva.
  - *Contexto:* o Tesseract lendo a página inteira com o leiaute dele **nunca desaba** — resgata as
    folhas 903 e 1210 do *Chess Evolution* (99,9% → 4,2% e 2,1%), as de linha intercalada (16% → 2,2%)
    e devolve 71 e 73 linhas às folhas do *Kmoch* que o glifo lê com uma —, mas numa folha normal é pior
    que as caixas do glifo (1.3).
  - *Entrega:* quando a guarda da S-710 dispara (densidade de leitura < 0,5), a folha é relida pelo leiaute do
    leitor de linha, a notação continua do glifo onde ele achou caixa, e a folha sai com o aviso
    `leiaute_de_reserva`; nos scans que têm camada de terceiro **conferida contra a tinta**, as caixas
    dessa camada são uma terceira opção de leiaute. A concordância de leiaute (número e posição das
    linhas, glifo × leitor de linha) vira sinal da S-763.
  - *Verificação:* as cinco folhas de 2026-10-30 e a varredura do acervo: folha com densidade de
    leitura baixa é relida pela reserva e sai com aviso; o ouro-dev não aciona a reserva.
  - *Saída:* as duas folhas perdidas do *Chess Evolution* saem com CER de prosa ≤ 5% e aviso; as três
    do *Kmoch*, cuja camada de terceiro está desalinhada da tinta (oráculo 33–49%, CER imensurável
    contra ela), saem com ≥ 90% das linhas da camada achadas e conferência visual de uma folha por quem
    não é o executor; nenhuma das 90 folhas legíveis aciona a reserva.
  - *Reversão:* interruptor; desligado, a folha sai como o glifo a leu, com o aviso da S-710.
- **S-716** · Primeira entrega: a prosa da camada nos livros digitais.
  - *Contexto:* nos livros nascidos digitais a camada **é** a tinta — é a referência do ouro. O
    `leitor.py` recusou a camada como motor por causa da **notação** (ela não representa figurina), não
    da prosa. Rotear a prosa para a camada e a notação para o glifo leva o erro de prosa a perto de zero
    nesses livros, sem Tesseract, sem instalador e sem D4. **Taxa de admissão medida** (`admissao.py` de
    `texto_prosa_2026-10-30/`, numa corrida só; 30 folhas sorteadas por livro com semente **por livro**
    — a amostra de um livro não depende dos outros nem da ordem —, `dados/2026-10-30/admissao.tsv`; e os
    dois *Chess Evolution* **inteiros**, `admissao_livro_inteiro.tsv`):

    | livro | amostra: admitidas | por que as outras saíram | livro inteiro: folhas com texto recusadas |
    |---|---:|---|---:|
    | Dvoretsky, *Endgame Manual* | 30 de 30 | — | — |
    | Hertan, *Forcing Chess Moves* | 30 de 30 | — | — |
    | Seirawan, *Xadrez Vitorioso* | 29 de 30 | sem texto fora dos diagramas (1) | — |
    | Chernev, *Melhores Finais de Capablanca* | 29 de 30 | sem texto fora dos diagramas (1) | — |
    | Fischer, *Minhas 60 partidas memoráveis* | 30 de 30 | — | — |
    | Kravtsiv, *400 Quebra-cabeças* | 30 de 30 | — | — |
    | Polgar, *Chess 5334* | 28 de 30 | sem texto fora dos diagramas (2) | — |
    | *Chess Evolution 2013* | 29 de 30 | sem texto fora dos diagramas (1) | 0 de 1.454 |
    | *Chess Evolution 2014* | 26 de 30 | sem texto fora dos diagramas (4) | 0 de 1.463 |
    | *Gaprindashvili* (controle) | 0 de 30 | (d) produtor de OCR (30) | — |
    | AAGAARD, *Practical Chess Defence* (ClearScan, controle) | 0 de 30 | (d) produtor de OCR (30) | — |
    | *Kemeri* 1937 (scan, controle) | 0 de 30 | (a) livro de scan (30) | — |

    Os nove livros digitais passam, e **nenhuma folha com texto fora dos diagramas é recusada** — nem
    nas 270 folhas sorteadas, nem nas 2.917 folhas com texto dos dois *Chess Evolution* inteiros; as
    recusas são capa, branco e folha só de diagrama, onde não há prosa a rotear. Os três controles saem
    inteiros: *Gaprindashvili* e AAGAARD por (d), e o *Kemeri* por (a), livro de scan — 29 das 30 folhas
    de perfil com texto invisível, contra 0 em todos os livros digitais (27 a 30 folhas de perfil com
    texto em cada um). A primeira versão da tabela usava um sorteio só para todos os livros (a amostra
    mudava com a ordem dos livros e a tabela não se reproduzia) e uma regra **por folha**, "menos de 200
    caracteres sobre imagem de página inteira", que recusava ao menos 72 folhas com texto do *Chess
    Evolution 2014* e 48 do *2013* — soluções e cabeçalhos de partida sobre a imagem de fundo (crítico
    da rodada 10). A regra por folha saiu; a de livro faz o trabalho dela.

  - *Entrega:* motor **`"camada_prosa"`** em `MotorDeTexto`, rotulado "Camada na prosa (livro digital)"
    em `ui/strings.py`. **Mapeamento camada → linha:** para cada linha que o glifo achou, os trechos da
    camada cujo centro cai na caixa dela (crescida 15% na vertical), em ordem de x, formam o texto de
    linha que o roteador de tokens (`text/fusao.py`, criado aqui e completado pela S-721) funde com o
    glifo — notação e figurina do glifo, prosa da camada. Quando a guarda da S-710 marca a folha como não
    lida, a prosa vem da **montagem da própria camada** (`motor="camada"`) e a notação fica sem glifo,
    com aviso. A admissão (a)–(d) é a de `text/admissao.py`, escrita na S-702 e reaproveitada aqui; o perfil
    de livro do critério (a) — 30 folhas igualmente espaçadas, só `get_texttrace`, sem leitura — é
    calculado uma vez por documento aberto e fica em memória. A
    procedência `camada` por intervalo vive **em memória** (a S-722 é que a grava), e o caderno continua
    gravando o texto como hoje.
  - *Verificação:* a S-716 acrescenta ao `texto_prosa_2026-10-30/rodar.py` a variante `camada_prosa` (o
    mesmo mapeamento, por fora do `ler_pagina`, como as fusões v1–v5) e mede: M0 no ouro-dev — CER de
    prosa contra a camada, que mede a **montagem** — e G1/G2/G6 contra o glifo; nos livros com camada de
    OCR, a admissão recusa e nada muda (`admissao.tsv`).
  - *Saída:* opção "Camada na prosa (livro digital)" na caixa de motor; o dono a vê nos livros dele;
    M0 medida no ouro-dev (montagem e auditoria visual).
  - *Reversão:* interruptor; desligado, a folha volta ao glifo.
  - *Da S-702:* (a)–(d) admitem livros cuja camada não é a tinta. A auditoria visual reprovou 5 de 27
    livros que passam neles, entre eles o *Chess Evolution 2013* e o *Capablanca* da tabela acima. Na
    prosa, o defeito é a ligadura que perde letra (`ft` → `f`); na notação, o símbolo de avaliação em
    código de fonte e a figurina fora da linha. A S-716 não põe a prosa da camada por (a)–(d)
    sozinhos: acrescenta a checagem da ligadura — o caractere cuja caixa é mais larga que a letra que
    ele diz ser — ou fica, no padrão, nos livros aprovados na auditoria; e a M0 se mede só nesses.
- **S-717** · Primeira entrega: a fusão experimental na janela.
  - *Entrega:* a S-721 **mínima** — regra v5, léxico de hoje, língua escolhida à mão — exposta como
    "Glifo + Tesseract (experimental)" na caixa de motor da aba, sem mudar o padrão; a leitura pode
    mostrar o glifo primeiro e trocar a prosa quando o Tesseract responder. Rótulos em `ui/strings.py`,
    nunca o identificador cru (`fusao`).
  - *Verificação:* teste de fiação **na janela** que escolhe a opção, lê uma folha e afirma o efeito no
    texto mostrado (memória `patch-nao-intercepta-slot-ligado`: afirmar efeito, não chamada).
  - *Saída:* o dono lê os livros dele com a opção, e o relatório da S-706 a mede.
  - *Reversão:* é uma opção a mais na caixa.
- **S-718** · Primeira entrega: a marca "revisar" honesta, por palavra.
  - *Contexto:* entre a primeira fusão e a S-760, a linha fundida carregaria a confiança do glifo
    pintada sobre o texto do Tesseract — no Hertan, o texto certo do Tesseract sairia "revisar" porque o
    glifo errou ali; `fila.py` já diz que isso "destrói a confiança na fila inteira".
  - *Contexto, rodada 9:* os dois sinais, crus, inundam — a discordância glifo × Tesseract marca 10,0%
    das palavras de prosa no ouro e 27,7% na prata; com o léxico da v5 (que recusa `a`, `é`, `não`,
    `one`), 26,8% e 40,1%. O teto da G5 é 5%.
  - *Entrega:* marca por palavra que **ranqueia** os sinais (discordância, fora do léxico **da língua do
    livro**, e a concordância do Tesseract consigo mesmo nas alternativas do `lstm_choice_mode=2`) e
    marca **no máximo 5%** das palavras da folha — as mais suspeitas —, com "próxima a revisar"; nas
    folhas da S-716 (prosa da camada) não há "outro leitor" e nada é marcado na prosa; **nunca** a
    confiança de um motor pintada sobre o texto de outro.
  - *Verificação:* G5 **provisória** no ouro-dev e na prata: captura de palavras erradas com a fração
    marcada travada em 5%, publicada já no G102 (a prova é a curva captura × fração marcada).
  - *Saída:* G5 provisória medida; a S-761 a substitui pela calibrada.
  - *Reversão:* interruptor; desligado, vale a faixa de hoje.
- **Portão G101:** G3 = 0 no ouro, na prata e numa varredura do acervo inteiro com a guarda da S-710
  (só o glifo e a densidade de leitura: ~0,65 s × 25.918 folhas ≈ 4,7 h de CPU, orçadas aqui) — o
  scan-ouro, que depende da D3, entra no G104; perda de leiaute (diferença pareada leitor de linha nas
  caixas do glifo − nas caixas da camada) com teto do IC95 ≤ +0,3 p.p. no ouro-teste e ≤ +2 p.p. no
  degradado calibrado. Hoje: +1,17 p.p. [−0,03; +3,91] no ouro-dev (+0,12 [−0,06; +0,48] sem o *Chess
  Evolution*) e +12,1 p.p. no degradado médio.

### Fase 102 — O leitor de linha ao lado do glifo

**Onde a fusão entra no `ler_pagina`, e por que ali.** O protótipo de 2026-10-30 funde **depois**
do `ler_pagina` inteiro, sobre `PaginaLida` pronta — tarde demais para produção. Nesse ponto já
rodaram `_com_negrito`/`_com_trechos` (os intervalos `negrito_em`/`italico_em` por caractere,
`leitor.py:1336-1359` na `main`), `_atar_legendas` (que conta palavras do bloco) e
`_sem_hifen_de_quebra` (que junta `em-`+`barrassment`); trocar o texto da linha depois disso
invalida os intervalos e desfaz a junção. A fusão entra **no fim de `linhas_do_glifo`, depois de
`sem_rotulos_de_eixo`**, sobre as `_Cru` da folha inteira em lote, **antes** de `_com_negrito`,
`_com_trechos`, `montar` e da junção de hífen — que passam a trabalhar sobre o texto fundido. Cabeçalho
e rodapé que vêm da camada (procedência `camada`, S-356) nunca entram na fusão. O número de 1,25%
da v5 foi medido na outra posição: a S-721 o **remede** nesta antes de herdá-lo.

- **S-720** · O executor do Tesseract e o contrato `LeitorDeLinha`.
  - *Contexto:* `ocr.py` já tem `TextRecognizer` e um `TesseractRecognizer` via `pytesseract` (o
    motor da S-42 para faixa e página, que descarta palavra abaixo de `MIN_CONFIDENCE` e não conhece
    `nl`). **`ocr.py` está no digest da S-218** (`field_eval.measured_modules()`), e mexer nele obriga
    a remedir os quatro relatórios de campo. O caminho da legenda (`ocr_caption`, `GlyphRecognizer`)
    fica como está.
  - *Entrega:* `text/tesseract.py` (o executor) e `text/leitor_de_linha.py` (o contrato), fora de
    `ocr.py`. O executor: um processo por folha com timeout e `kill` (um Tesseract travado não pode
    prender a `Tarefa` do Qt); `creationflags=CREATE_NO_WINDOW` e os três *pipes* explícitos (o bundle
    é `console=False` e pisca console sem isso); imagem por **stdin**, nunca caminho de arquivo na linha
    de comando (caminho acentuado quebra em máquina cp1252, e esta máquina, em UTF-8, não reproduz —
    memória `code-page-desta-maquina-e-utf8`); `TESSDATA_PREFIX` resolvido e `OMP_THREAD_LIMIT=1`;
    `returncode` ≠ 0 ou `stderr` com erro vira **aviso**, nunca texto vazio calado. **Resolução segura do
    binário:** só caminho absoluto (bundle, `TESSERACT_CMD`, e o PATH varrido **sem** o diretório
    corrente — com nome nu, o Windows procura primeiro na pasta corrente); `--version` conferida na faixa
    medida (5.x); fora dela, "não leu" com aviso — um 4.x no PATH leria sem erro e diferente;
    `TESSDATA_PREFIX` do executor **sempre** sobrescreve o do ambiente; `--user-words` e `TESSDATA_PREFIX`
    passados por caminho curto/ASCII ou testados com code page cp1252 **simulada** (esta máquina é UTF-8
    e não reproduz o defeito pelo disco). **Recursos:** ~30 MB por processo, ~48 MB por folha num TIFF de
    várias páginas, ~124 MB na imagem nativa a 600 dpi (medidos pelo crítico da rodada 6); timeout de 10×
    o p99 medido por folha (mínimo 10 s); os processos num *Job Object* com `KILL_ON_JOB_CLOSE`, para
    fechar a janela não deixar `tesseract.exe` órfão; imagem embutida com teto de megapixels (60 MP) antes
    de extrair — um PDF malicioso pode pedir gigabytes. O contrato distingue
    **"não leu"** (`None`: motor ausente, timeout, erro — a linha fica com o glifo e a folha ganha
    aviso) de **"leu vazio"** (`""`). Ausência do motor nunca levanta no caminho da janela (decisão 4).
    O RapidOCR fica **só na régua**: o `onnxruntime` é excluído do bundle (`packaging/cvoff.spec`) e o
    modelo do wheel não lê acento.
  - *Configuração:* `--dpi` declarado é o real (o protótipo declarava 300 sobre 220 — medido: na
    leitura por linha, `psm 7`, dá o mesmo CER nas 26 folhas, então é correção, não ganho); dicionário
    do Tesseract **desligado** nas linhas de notação (`load_system_dawg=0`); `--user-words` com
    jogadores, aberturas e torneios, respeitando a lista de exclusão da S-750; e a **escala do recorte
    pela altura-x medida** da linha (alvo de 20–30 px), independente da escala do glifo — um scan de 150
    dpi tem altura-x nativa de 7–10 px e o Bachmann, a 220 dpi, de ~52 px.
  - *Verificação:* o *parser* do TSV testado sobre saídas **gravadas** do Tesseract (roda no CI sem o
    binário); leitor falso que devolve `""`, que levanta e que estoura o timeout; teste com caminho
    acentuado forçado no `TESSDATA_PREFIX`; teste de integração marcado `requer_tesseract`, pulado onde
    não há binário.
  - *Saída:* o executor lê as 26 folhas lidas pelo `rodar.py` de 2026-10-30 nas caixas do glifo — um
    processo por folha, TIFF de várias páginas (S-725) — com o **mesmo texto** que o `rodar.py` de
    2026-10-30 lê com um processo por linha (diferença zero), sem console e com aviso quando o binário
    falta ou tem versão fora da faixa.
  - *Reversão:* módulos novos; sem a fusão (S-721) ninguém os chama.
- **S-721** · Fusão por token (`text/fusao.py`).
  - *Contexto:* cinco regras foram medidas offline sobre as mesmas linhas (tabela da 1.5); a de partida
    é a **v5** (`texto_prosa_2026-10-30/fusao_v5.py`) no digital: ganha do glifo em 25 de 26 folhas e,
    nos seis livros limpos, perde do Tesseract puro só +0,05 p.p. [0,00; +0,12]; na notação fica a +1,26
    p.p. do glifo, dentro do ruído, e preserva 98,9% das figurinas dele. O que ela ainda não resolve: no
    estrato misto perde +0,08 p.p. [0,00; +0,22] do Tesseract puro; no scan, +0,97 p.p. [−0,07; +2,98] —
    e **no scan a melhor regra medida é a v3** (6,2% contra 7,0%; *Brinckmann* 3,4% contra 8,5%), que
    entrega a notação em letra ao Tesseract. A regra é **por estrato de produção** (S-702): v5 no
    digital, v3 no scan, decidido pela régua e não por gosto.
  - *Entrega:* no ponto descrito no topo desta fase. Alinhamento de tokens por linha (programação
    dinâmica, custo = distância normalizada); regras, nesta ordem: (1) token de **notação em qualquer
    lado** → glifo — o Tesseract estraga lance de peão (`g4!`→`24!`) —, **salvo** se o leitor de linha
    leu ali uma palavra que existe (`the`, `with`, `Wissen`), caso em que a palavra vence; (2) o número
    de lance do leitor de linha só entra quando o glifo o **partiu** (`1 7.` contra `17.`), nunca quando
    os dois têm o mesmo tamanho (`27.` contra `21.` é erro do Tesseract); (3) prosa → leitor de linha;
    (4) se divergem e **só** a versão do glifo é palavra que existe, fica o glifo; (5) **palavra de
    prosa do glifo sem par fica**, com a confiança mais baixa da linha — o leitor que "não viu" não
    apaga texto; (6) nada de "parece com" (regra da S-209). Três fronteiras: o **roteador** de
    `fusao.py` é próprio e não importa o classificador da régua (`text/regua_prosa.py`), e um teste de
    grafo de import trava isso — o instrumento não pode compartilhar código com o medido; a lista de
    **palavras funcionais curtas** (que `lexico.MIN_TAMANHO = 4` deixa de fora) é **privada** de
    `fusao.py` — acrescentá-la ao léxico compartilhado mudaria `dicionario.corrigir` e a junção de
    hífen no caminho do glifo, e desligar a fusão não devolveria o glifo de antes; e a **confiança**
    da linha fundida continua a do glifo calibrado até a S-760 calibrar a do Tesseract (regra da
    S-189: confiança crua não se compara com calibrada).
  - *Instrumento:* `MotorDeTexto` ganha `"fusao"` (`ler_pagina(motor="fusao")`, `--motor fusao` nos
    CLIs); é por ele que a régua mede a fusão **dentro** do `ler_pagina`, e não mais por fora, como o
    `rodar.py` do protótipo — **este item estende a régua** (S-700/S-706) com `--motor fusao`.
  - *Regras por estrato:* o estrato da folha é decidido em tempo de execução pelo critério (d) da S-702
    (produtor e fontes de OCR → scan ou ClearScan; folha sem camada visível → scan) e pela admissão da
    S-716 (digital admitido → `camada_prosa`, e a fusão não roda). **Digital não admitido: v5** — as
    regras (1)–(6) abaixo. **Scan e ClearScan: v3** — (1) token em que o **glifo** vê figurina → glifo,
    com o número de lance do leitor de linha se o glifo o partiu, **salvo** se o leitor de linha leu ali
    uma palavra que existe no léxico da língua; (2) notação em **letra** (`Lf1-d3`, `Kxf3`) → leitor de
    linha, que no scan a lê melhor que o glifo; (3) prosa → leitor de linha; (5) e (6) como na v5.
    O 6,2% medido da v3 (1.5) vetava por "palavra só de letras"; com o veto por léxico o número **não
    se herda** — a S-721 remede a v3 assim escrita na prata admitida antes de fixá-la no scan, e se ela
    perder para a v3 medida, fica o veto por letras no scan.
  - *Verificação:* intervalos de `negrito_em`/`italico_em` sobrevivem à fusão (teste com linha
    sintética); junção de hífen idêntica com e sem fusão numa linha só de prosa; leitor falso que
    devolve `None` deixa a folha **igual** à do glifo sozinho e com aviso.
  - *Saída:* remedida **nesta** posição: no ouro-dev, prosa ≤ Tesseract puro (limite superior da
    diferença pareada ≤ +0,1 p.p.) **e** notação dentro de G1(a), G1(b) e G2 (a G1(c) é da S-729); no
    estrato misto e na prata admitida, diferença para o Tesseract puro com IC95 contendo zero ou abaixo.
  - *Reversão:* `MotorDeTexto` ganha `"fusao"`; o padrão só muda no G102, e voltar ao glifo sozinho é
    trocar o motor, sem migração (o texto fundido é texto como outro qualquer até a S-722).
- **S-722** · O modelo de página guarda o que a fusão produz.
  - *Contexto:* `LinhaLida` tem **uma** `procedencia` e **uma** `confianca` por linha
    (`text/pagina.py`); a faixa de confiança é por bloco (`documento.faixa_de_confianca`); `PROCEDENCIAS`
    e `ORDEM_DE_CONFIANCA` são tuplas à parte do `Literal` (sem a entrada nova, `menos_confiavel`
    levanta `ValueError`); a procedência diz **de qual motor** o texto veio (`rapidocr` já existe).
  - *Entrega:* procedência **`tesseract`** (o nome do motor, como `rapidocr`; o leitor da Fase 105
    terá o dele), no `Literal`, em `PROCEDENCIAS` e numa posição declarada de `ORDEM_DE_CONFIANCA`;
    linha mista leva a menos confiável das que a compõem; campos por intervalo `procedencia_em` e
    `confianca_em` (o mesmo desenho de `negrito_em`), que é o que a S-761 precisa para marcar palavra
    e não bloco; `ESQUEMA` da página e `arquivo.VERSAO` sobem, com leitura do formato antigo.
  - *Verificação:* ida e volta de `.cvtxt` e caderno com `procedencia_em`/`confianca_em`; arquivo do
    `ESQUEMA` anterior abre igual; `menos_confiavel` com `tesseract` não levanta.
  - *Saída:* a aba Texto e a exportação leem os campos novos; a faixa "revisar" pode marcar palavra.
  - *Reversão:* **este item não é reversível por interruptor** — uma versão antiga do programa não
    abre `.cvtxt` nem caderno gravado com `tesseract` (estoura `PaginaInvalida`). Fica escrito, e o
    formato novo só é gravado depois do portão G102.
- **S-723** · A língua do livro.
  - *Entrega:* parâmetro `lingua` em `ler_pagina` (hoje não existe); detecção por perfil de palavras
    funcionais nas primeiras folhas lidas, guardada no caderno do livro (`text/caderno.py`, só na
    `main`), com troca manual no menu Texto (**não** em `settings.py`: S-218). Escolhe `tessdata` e o
    léxico da S-728. `ocr._TESSERACT_LANGS` não conhece `nl`; o executor da S-720 tem o seu mapa.
  - *Verificação:* detecção nas primeiras 10 folhas lidas de cada livro deduplicado do acervo,
    comparada com a língua declarada à mão numa tabela do teste.
  - *Saída:* acerto de língua em todos os livros do acervo deduplicado (8 línguas).
  - *Reversão:* a língua manual no menu sempre vence a detectada.
- **S-724** · O Tesseract no instalador.
  - *Contexto:* o binário existe nesta máquina em `C:\Program Files\Tesseract-OCR`, instalado à mão; o
    instalador não o leva. Licença Apache-2.0.
  - *Entrega:* `packaging/cvoff.spec` leva uma **lista fechada** — `tesseract.exe`, as 34 DLLs que ele
    carrega (24,9 MB; a pasta instalada tem 740 MB) e o `tessdata` das 8 línguas do acervo (22,6 MB fast,
    sem `osd`) —, com **teto declarado** de +60 MB sobre o bundle de hoje, `bundle.json` e o README
    atualizados (a guarda da S-135 os confere); uma pasta `licencas/` com o texto de cada componente
    embarcado — Tesseract e Leptonica (Apache-2.0), libiconv e libintl (LGPL-2.1), libidn2 e
    libunistring (LGPLv3/GPLv2), libstdc++ e libgcc (GPLv3 com exceção de runtime), OpenSSL, libcurl,
    libssh2 —, e um teste que reprova binário embarcado sem licença ao lado; `assets/texto_prosa/` e
    qualquer lista derivada de livro comercial **fora** do bundle (o `cvoff.spec` embarca `assets/`
    inteiro hoje). O caminho é resolvido como na S-720; ausente → glifo sozinho com aviso na barra de
    status.
  - *Verificação:* `cvoff.spec` gera o bundle; num Windows sem Tesseract instalado, o programa do
    bundle lê uma folha com a fusão; sem a pasta do Tesseract no bundle, lê com o glifo e avisa.
  - *Saída:* bundle medido dentro do teto, licenças no lugar e aprovado pelo dono (decisão D1).
  - *Reversão:* o bundle sem o Tesseract continua funcionando (decisão 4).
- **S-725** · Desempenho, custo de varredura e cache.
  - *Contexto:* o protótipo chama o Tesseract uma vez por linha (≈ 40 processos por folha, 0,7–1,0 s
    com 10 threads). **Empilhar as linhas numa imagem só (`psm 6`) muda o reconhecimento**: medido pelo
    crítico da rodada 6, 14 de 55 linhas mudaram no Dvoretsky e 14 de 25 no *Minhas 60* (`7...2f6`→`7...
    216`, `Yb6`→`Wb6`), e o TSV devolveu 62 linhas para 55. Um **TIFF de várias páginas** pelo stdin, uma
    linha por página com `psm 7`, deu 0,71 s e 0,40 s por folha e **zero** linhas diferentes da leitura
    por linha.
  - *Entrega:* um processo por folha com o TIFF de várias páginas; `cvoff-texto-custo` remedido com
    `motor="fusao"` e a faixa da política da S-215 levada à D4; `custo.PAGINAS_DO_ACERVO` corrigido para
    o acervo de hoje; cache em `data/cache_texto/` com chave **completa** — sha do recorte, versão do
    executor e do pré-processamento, versão do Tesseract, sha do `tessdata` da língua, língua, `psm` e
    sha do modelo (S-752) —, **teto em MB** com despejo LRU, gravação por `atomic_io`, disco cheio vira
    aviso sem perder a leitura, limpeza pelo menu, e `data/cache_texto/` no `.gitignore` **no mesmo
    commit** (o cache é texto de livro comercial). A régua roda **sempre com o cache desligado**. O
    orçamento de tempo é o do G4.
  - *Verificação:* texto **igual** ao da leitura por linha (diferença zero) nas 26 folhas lidas pelo
    `rodar.py` de 2026-10-30; tempo por folha com a máquina parada, com e sem cache; teste de despejo e
    de chave (trocar `tessdata`, língua, `psm`, versão ou modelo invalida a entrada).
  - *Saída:* G4 cumprido com cache desligado; a política da S-215 remedida e publicada.
  - *Reversão:* apagar `data/cache_texto/` é sempre seguro; o lote por folha tem a leitura por linha
    como reserva atrás de constante.
- **S-726** · A S-188 relida com a régua nova, e o modo bloco aposentado com quem o usa.
  - *Entrega:* remedir o modo bloco **só na prosa**; se a fusão por token vencer (esperado: o modo bloco
    amarra a leitura às caixas do glifo e não conserta segmentação), aposentá-lo no caminho da página
    junto com **todos** os consumidores — `ui/state.texto_bloco` (gravado no estado da janela, com
    migração que descarta a chave), a caixa da aba Texto, o `INTERRUPTOR` do menu, `comandos`,
    `texto_declarado`, o `--bloco` de `cli/texto_pagina.py` (o único CLI que o tem), `qt/menu.py`,
    `qt/painel_de_texto.py`, `ui/menu.py`, `text/caderno.py`, `text/fila.py`, `ui/fita_do_texto.py`, a
    sonda S-188 do `text_status` e os 8
    arquivos de teste que o citam (`grep -rln "modo_bloco\|texto_bloco" src tests` na `main`) — e a
    frase da aba "tente outro motor ou o modo bloco", que fica falsa e é reescrita em `ui/strings.py`. Dois
    caminhos híbridos não convivem.
  - *Verificação:* `grep -rln "modo_bloco\|texto_bloco" src tests` na `main` vazio, salvo a migração
    do estado; a suíte verde.
  - *Saída:* o modo bloco não existe no caminho da página; estado antigo abre sem a chave.
  - *Reversão:* é remoção: volta por `git revert` do commit, que precisa ser só dela.
- **S-727** · Os CLIs de medição fixam o motor antes de o padrão mudar.
  - *Contexto:* na `main`, CLIs que publicam `docs/metrics/texto_*.json` (`texto_lexico`,
    `texto_paragrafo`, `texto_pesquisavel`, `texto_custo` e outros) chamam `ler_pagina` com o motor
    **padrão**. Virar o padrão para a fusão mudaria o que eles medem, sem guarda nenhuma.
  - *Entrega:* todo CLI que publica relatório passa `motor=` explícito e o grava no relatório; um teste
    varre `cli/texto_*.py` e reprova chamada de `ler_pagina` sem `motor=`. Entra **antes** do portão
    G102.
  - *Verificação:* teste que varre `cli/texto_*.py` e reprova chamada de `ler_pagina` sem `motor=`.
  - *Saída:* todo relatório `docs/metrics/texto_*.json` novo diz o motor; os antigos ficam como estão.
  - *Reversão:* acrescentar `motor=` explícito não muda número nenhum.
- **S-728** · Léxico por língua.
  - *Contexto:* `text/lexico.py` tem perfis (`acervo`, `idioma`, `nomes`), não línguas; a S-721 e a
    S-723 pressupõem um léxico por língua.
  - *Entrega:* listas por língua (as 8 do acervo: en, pt, es, de, nl, fr, ro, ru) em `assets/lexico/` —
    que vai no bundle, então cada lista precisa de licença compatível com a distribuição e de origem que
    **não** seja a camada dos livros do acervo (`acervo.txt.gz` já é; a D5 decide se continua) —, com procedência
    escrita em `PROCEDENCIA.md`; o perfil atual continua sendo o padrão do glifo, para não mudar o que
    o `dicionario` decide hoje.
  - *Verificação:* contagem de entradas por língua no README conferida por `test_docs`; o `dicionario`
    do glifo com o perfil de hoje dá o mesmo texto no ouro-dev (diferença zero).
  - *Saída:* listas das 8 línguas com procedência escrita e sha no manifesto.
  - *Reversão:* listas novas; o perfil do glifo não muda.
- **S-729** · O árbitro de notação pela legalidade.
  - *Contexto:* as regras 1 e 2 da S-721 são heurísticas de forma (`27.` contra `21.` → "fica o do
    glifo"). A notação tem um modelo de língua exato — a legalidade do lance a partir da posição — e
    `text/notacao.py` já importa `chess` com o `validar` deixado de fora (S-208).
  - *Entrega:* por token de notação, candidatos do glifo (top-k) e do Tesseract
    (`lstm_choice_mode=2`); decide a continuidade do número de lance e a legalidade a partir da FEN do
    diagrama mais próximo; a notação descritiva e a cirílica entram por aqui, com troca de homóglifo
    (`е→e`, `Ь→b`, `б→6`, `З→3`) **só** em token de notação e sob a gramática, e o executor roda
    `rus+eng` nos livros russos.
  - *Verificação:* no ouro-dev, fração de sequências de lance que fecham legais a partir da FEN, antes
    e depois; na prata, os dígitos de casa da notação descritiva.
  - *Saída:* G1(c) — a fração de sequências que fecham legais não cai; e na prata, os dígitos de casa
    errados do Tesseract (`R1D`→`RID`, `P5C`→`PSC`) voltam pela gramática.
  - *Reversão:* interruptor; desligado, valem as regras de forma da S-721.
- **Portão G102:** no ouro-teste (≥ 12 livros × 6 folhas, ou o recuo da D6), CER de prosa ≤ 0,8% com teto do IC95
  ≤ 1,2%, WER ≤ 2,0% com teto ≤ 3,0%, G1, G2 e G4 (sem a D6, no teste provisório da D6, rotulado);
  **no scan, por estrato, não-inferioridade contra o Tesseract puro** (teto do IC da diferença pareada
  ≤ +0,5 p.p.) medida na **prata admitida** — comparar dois motores contra a mesma referência é o uso
  que a prata permite — e remedida no scan-ouro no G104; a fusão não pode virar padrão para todos os
  livros tendo sido medida só no digital; S-727 entregue; G6 e a G5 provisória (S-718) medidas. **Virar
  o padrão é virar na janela**, e não só no `ler_pagina`: a aba passa o motor explícito
  (`ui/texto_declarado.MOTORES`, cujo primeiro é `auto`), restaura o `texto_motor` gravado e reabre a
  folha corrigida do caderno sem reler (S-612). O portão declara o que `auto` passa a ser (camada na
  prosa nos digitais admitidos, fusão nos demais, glifo sem Tesseract), o rótulo na caixa, a migração do
  estado gravado, e a oferta "reler com o leitor novo as folhas **não corrigidas** deste livro"; um teste
  de fiação na janela afirma o efeito. Interruptor para voltar ao glifo sozinho (o formato da S-722 é a
  exceção declarada). É um degrau, não a meta: M1 e M2 fecham na Fase 107.

### Fase 103 — O glifo sem as cegueiras do 32×32

O glifo continua lendo a notação e é o caminho de reserva quando não há leitor de linha. Cada item
ataca uma família da seção 1.6 e é medido pela régua — família e total.

- **S-730** · Traço vertical contra ponto (23,7% das palavras de prosa erradas do glifo; 100 delas só no Hertan, Arial).
  - *Entrega:* `.`, `,`, `'`, `l`, `I`, `|`, `1`, `i` decididos pela geometria da caixa — altura
    sobre a altura-de-x, topo e base contra a linha de base, proporção —, como a `caixa_alta` faz com
    a caixa. Antes de escrever a regra, medir em que *rank* a classe certa está (memória
    `caixa-alta-sai-da-altura`: se está em rank 2, o problema é de decisão, não de treino).
  - *Verificação:* teste de decisão com caixas sintéticas (altura, base, proporção) que roda no CI; na
    régua, a família "traço vertical lido como ponto" do glifo, por livro, no dev.
  - *Saída:* a família cai a ≤ 1/4 do que é hoje no Hertan e no *Chess Evolution*, sem subir em nenhum
    livro; notação dentro de G1(b).
  - *Reversão:* constante, como a `caixa_alta`.
- **S-731** · Caixa coerente na palavra (10,7%): palavra toda em maiúscula não ganha minúscula no meio
  (`DEFEsA`); a primeira letra da linha usa a régua de altura da linha inteira.
  - *Verificação:* teste de decisão (palavra toda em maiúscula, primeira letra da linha); régua da
    família "caixa" por livro.
  - *Saída:* família caixa ≤ 1/3 do que é hoje no dev, sem nenhum `DEFEsA`.
  - *Reversão:* constante.
- **S-732** · Fronteira de palavra (7,9%): o vão de `f`+`t`, `f`+`f` com *kerning*; o léxico como
  árbitro do corte, que já mediu melhor que a confiança (memória `lexico-arbitra-corte-melhor-que-confianca`).
  - *Verificação:* régua da família "fronteira" por livro; teste com pares de caixas sintéticos.
  - *Saída:* família fronteira ≤ 1/3 da de hoje, sem aumentar "espaço inserido".
  - *Reversão:* constante.
- **S-733** · Ligadura `fi`/`fl`/`ff` sem o `1` a mais (2,2%).
  - *Verificação:* régua da família "ligadura com 1 a mais" (Dvoretsky).
  - *Saída:* zero `fi1`/`f1` em palavra do ouro-dev.
  - *Reversão:* constante.
- **S-734** · Aspas duplas e apóstrofo (2,4%), medidos em `cru`: par de apóstrofos colados vira `"`; abre-aspas nunca vira `(`.
  - *Verificação:* régua em `cru` (onde `—` e `-` e as aspas contam) da família aspas e pontuação.
  - *Saída:* aspas duplas zero no Capablanca e no Dvoretsky; pontuação ≤ 1/2 da de hoje.
  - *Reversão:* constante.
- **S-735** · Acento (5,3%): til contra trema (`não`→`näo`), `ç` contra `C`; o segundo corte de caixa
  para a família acentuada (memória `caixa-alta-nao-cobre-acentuada`, ~1,65); contar as amostras de
  cada classe acentuada antes de creditar qualquer número a ela (`par-scaron-tem-7-amostras`).
  - *Verificação:* régua da família acento por livro; antes, contar as amostras de cada classe
    acentuada em `training_data/`.
  - *Saída:* família acento ≤ 1/3 da de hoje no *Minhas 60*, sem `Õ` nem `Ó` inventados (o segundo
    corte não pode quebrar minúscula acentuada).
  - *Reversão:* constante, como a `caixa_alta`.
- **S-736** · ADR: a geometria como entrada do classificador.
  - *Contexto:* numa amostra de 3.000 recortes de `training_data/` (crítico da rodada 3), 57,6% estão
    em 32×32 e 42% guardam o tamanho original — mas justamente `l` (99% esticados) e `I` (100%) perderam
    a proporção, e são classes raras (2.573 e 786 recortes, contra 20.434 de `.` e 33.855 de `e`). A
    saída estrutural é recortar de novo e dar à rede altura relativa, deslocamento da linha de base e
    proporção como entradas — e "recortar de novo dos livros digitais" é recortar dos livros **dev**,
    com a lista de exclusão da S-750 valendo.
  - *Entrega:* decisão registrada (fazer na Fase 105 ou não fazer), com o custo medido.
  - *Verificação:* a ADR cita a contagem de recortes esticados por classe e o custo medido de recortar
    de novo.
  - *Saída:* ADR commitada com decisão (fazer na Fase 105 ou não fazer) e o porquê.
  - *Reversão:* é uma decisão escrita; revê-la é outra ADR.
- **Portão G103:** depois da Fase 102 o glifo lê sobretudo **notação** — e a família traço-ponto
  custa ali também (`Rf1`→`Rf.`, `11.`). O portão mede as duas coisas: glifo sozinho ≤ 1,5% de CER de
  prosa (teto ≤ 2,5%) no ouro-teste, para o caminho de reserva; e, na notação, G1(b), G1(c) e G2
  contra o glifo de hoje com diferença pareada a favor (teto do IC < 0) em pelo menos uma delas.

### Fase 104 — O scan de verdade

- **S-740** · Pré-processamento por linha para o leitor de linha: escala pela altura-x (S-720);
  scan lido da **imagem embutida na resolução nativa**, não do render a 220 dpi; cinza contra
  binarizado; endireitar a linha; limpar a poeira; medido no scan-ouro-dev **por estrato** e no
  degradado calibrado. **Uma hipótese já caiu**:
  ampliar o recorte 2× antes do Tesseract não paga a 220 dpi — 4,57% → 4,64% no limpo e 18,0% → 17,0%
  no degradado médio, em 8 folhas de 4 livros, dentro do ruído — **em livro digital**. Nos scans de
  ≤ 150 dpi (altura-x nativa de 7–10 px) a pergunta é outra, e é ali que ela se refaz: ampliar em
  cinza **antes** de binarizar.
  - *Verificação:* `cvoff-texto-prosa` (ou, até a S-706 existir, `reproduzir.py` + `resumo.py` de
    `texto_prosa_2026-10-30/`) no scan-ouro-dev por estrato, pareado contra o pré-processamento de hoje.
  - *Saída:* no estrato ≤ 150 dpi, CER de prosa do leitor de linha com diferença pareada a favor (teto
    do IC < 0); nos outros estratos, não-inferioridade (teto ≤ +0,2 p.p.).
  - *Reversão:* cada passo atrás de constante.
- **S-741** · `tessdata_best` contra `fast`, no ouro-dev **e** no scan-ouro-dev (decisão D2: são
  downloads, ~15 MB por língua). É o primeiro degrau da S-745 e a primeira parcela do orçamento de
  reconhecimento da M1 (seção 3).
  - *Verificação:* mesma corrida com `tessdata` fast e best, mesmas folhas, `resumo.py --pares`.
  - *Saída:* decisão escrita (best ou fast) com a diferença pareada e o tamanho a mais no bundle.
  - *Reversão:* trocar a pasta de `tessdata`; a chave do cache da S-725 já separa os dois.
- **S-742** · A camada de terceiro como terceiro voto, só na prosa.
  - *Contexto:* ~20 livros escaneados do acervo trazem camada de Paper Capture/ABBYY, boa na prosa e
    ruim na notação.
  - *Entrega:* voto por palavra (glifo, leitor de linha, camada) **só em token de prosa**; notação
    nunca vem da camada. Medido **só no scan-ouro** — na prata a medição seria circular.
  - *Verificação:* no scan-ouro-dev, por estrato, voto com e sem a camada, pareado.
  - *Saída:* entra só se a diferença pareada for a favor (teto do IC < 0) em pelo menos um estrato e
    não-inferior nos outros; senão, fica registrado que não paga.
  - *Reversão:* interruptor; sem camada no PDF, o voto simplesmente não existe.
- **S-743** · Algarismos de estilo antigo e notação oitocentista.
  - *Contexto:* conferido na imagem pelo crítico da rodada 4: Gutmayer, Neumann, Dufresne e Bachmann
    são **Antiqua**, não Fraktur. O problema real do século XIX são os algarismos de estilo antigo, que
    destroem a casa e o número de lance — no Bachmann o Tesseract leu `10.`→`Io.`, `11.`→`ıı.`,
    `Dh5`→`Dhs`, `Kg1`→`Kgı` — e a notação da época (`1) d1—h5`, `g7†m.` no Neumann).
  - *Entrega:* dígito forçado pela gramática na posição de casa e de número de lance (S-729). Fraktur
    só se aparecer um livro nela — e então com o modelo `frak2021` (UB Mannheim, decisão D7), não com o
    `deu_latf` fast.
  - *Verificação:* no Bachmann e no Neumann, contagem de números de lance e casas inválidos antes e
    depois (a gramática da S-729 é o juiz).
  - *Saída:* nenhum `Io.`/`ıı.` nas folhas medidas; casas válidas ≥ 99%.
  - *Reversão:* constante no árbitro da S-729.
- **S-744** · Texto espaçado (*gesperrt*): `f a t a l e n` na ênfase alemã do Gutmayer volta a
  `fatalen` quando o léxico concorda.
  - *Verificação:* folhas do Gutmayer com *gesperrt*: palavras espaçadas juntadas só quando o léxico
    concorda.
  - *Saída:* zero palavra espaçada que o léxico conhece; nenhuma junção de palavras distintas.
  - *Reversão:* constante.
- **S-745** · A escada de linhas de base, antes de qualquer modelo da casa.
  - *Entrega:* no ouro-dev e no scan-ouro-dev, em ordem de custo: (0) o degrau que não custa nada —
    `--user-words`, dicionário desligado na notação, escala por altura-x e um modelo de n-gramas de
    caractere por língua para desempatar as alternativas do `lstm_choice_mode=2`; (1) `tessdata_best` (S-741);
    (2) **ajuste fino do Tesseract** (`tesstrain`/`lstmtraining`, offline e em CPU, a partir do `best`,
    com as linhas de treino da **S-746** e a figurina como caractere novo) — encaixa sem mudança no
    executor da S-720 e no bundle da S-724; (3) um reconhecedor **PP-OCR latino** em ONNX (o
    `onnxruntime` 1.23.2 já está no `.venv`; o wheel só traz o `ch_PP-OCRv4`, sem acento). Os
    downloads (2) e (3) são a decisão D7. A S-755 compara o leitor da casa contra **o melhor degrau**.
  - *Verificação:* cada degrau medido nas mesmas folhas do ouro-dev e do scan-ouro-dev, pareado contra
    o degrau anterior; tabela única no relatório.
  - *Saída:* a escada publicada com o melhor degrau nomeado — é contra ele que a S-755 compara.
  - *Reversão:* cada degrau é configuração do executor (modelo e opções); voltar é trocar a
    configuração.
- **S-746** · As linhas de treino do ajuste fino (o pedaço de dados que a escada precisa antes da
  Fase 105).
  - *Contexto:* a S-745 precisa de linhas rotuladas para o degrau 2, e a Fase 105 só começa depois da
    S-745; sem este item os dois se esperam.
  - *Entrega:* pares (imagem de linha, texto exato) recortados **só** dos livros digitais de treino
    (dev e D6 não sorteados para o teste), com a lista de exclusão da S-750 já aplicada (livro, série,
    editora, léxico, nomes, PGN) e o teste de n-gramas contra as referências do teste; reaproveita
    `text/dataset.py` e `text/aumento.py`. Sem fonte sintética — isso é da S-750.
  - *Verificação:* teste de n-gramas verde; contagem de linhas por livro e por língua no manifesto.
  - *Saída:* manifesto com sha; o degrau 2 da S-745 consome este conjunto e nenhum outro.
  - *Reversão:* dado fora do produto.
- **Portão G104:** G3 = 0 e a não-inferioridade do G102 remedidos no scan-ouro; no scan-ouro-teste, M3 ≤ 1,5% (teto 2,5%) e M4 ≤ 4% (teto 6%); M5 ≤ 1,5% (teto 2,5%) na família de degradação reservada.

### Fase 105 — O leitor de linha da casa

O Tesseract é o primeiro leitor de linha porque já mede bem e não exige treino. Ele não conhece
figurina e não foi treinado em livro de xadrez. Esta fase decide, **por medição e com regra
declarada antes**, se um modelo de linha da casa o substitui — e ela só começa depois da escada de
linhas de base (S-745), porque o modelo da casa tem de vencer **a melhor** delas, não a mais fraca.

**Os quatro conjuntos desta fase, que não se tocam.** (1) **treino**; (2) **validação** — disjunta
do treino por livro **e por família tipográfica**, é nela que se para o treino, se ajusta a
temperatura e se escolhem limiares; (3) **ouro-dev** — os livros de 2026-10-30 aprovados na auditoria
da S-702 (cinco dos sete), só diagnóstico;
(4) **teste** — ouro-teste e scan-ouro-teste, abertos só no portão. Como o acervo não tem outro livro
digital de prosa (S-702), as linhas reais de treino e validação saem dos livros dev **e** dos livros
digitais novos da D6 que não forem sorteados para o teste — e o relatório diz quantas linhas vieram
de cada um.

- **S-750** · Dataset de linhas, com lista de exclusão do teste.
  - *Contexto:* o teste vaza por mais lugares que a imagem. `assets/lexico/acervo.txt.gz` foi
    extraído da camada editorada de 11 livros do acervo (`PROCEDENCIA.md`), que é a própria
    referência do ouro; `nomes.txt.gz` traz nomes casados aos livros; o PGN comentado cita livros
    (`{Fischer: ... (My 60 ...`); *Chess Evolution 2014* é da mesma série e diagramação de um livro
    dev. E as fontes embutidas nos PDFs são **subconjuntos** (Dvoretsky: 9 de 9 com prefixo
    `AAAAAx+`, inclusive `Chess-Merida` e `SemFigNormal`; *Minhas 60*: 17 de 17): renderizar prosa
    arbitrária com elas perde glifo, e o rótulo passa a ter letra que a imagem não mostra. O projeto
    já tem `text/dataset.py` e `text/aumento.py` (do glifo); o dataset de linhas os estende, não os
    duplica.
  - *Entrega:* parte das linhas da **S-746** e acrescenta linhas sintéticas renderizadas com fontes
    **completas** (origem e licença decididas na D7) — nunca com a
    fonte subconjunto do PDF sem conferir o `cmap` de cada caractere do rótulo —, com texto de prosa
    das 8 línguas do acervo e texto de lance de PGN comentado; aumento com uma família de degradação
    **diferente** da que avalia a M5 (S-704). **Lista de exclusão** por identidade de livro **e por
    série/editora** dos livros do teste, aplicada a imagem, corpus de texto, PGN, léxico, nomes e
    fontes; léxico e listas congelados com sha **antes** de abrir o teste; teste automático de
    sobreposição de n-gramas (≥ 8 palavras seguidas) entre o corpus de treino e as referências do
    teste, que reprova o dataset quando acha. Manifesto com sha de cada fonte e de cada lista.
  - *Verificação:* teste de n-gramas (≥ 8 palavras) entre corpus de treino e referências do teste
    reprova o dataset; `cmap` conferido para cada caractere de cada rótulo sintético; manifesto com
    sha de cada fonte, lista e livro.
  - *Saída:* dataset com os quatro conjuntos declarados, contagem de linhas por origem e o teste de
    sobreposição verde.
  - *Reversão:* dado fora do produto; um dataset reprovado não treina nada.
- **S-751** · ADR da arquitetura: CRNN (CNN + BiLSTM + CTC, 3–8 MB) contra SVTR-tiny; inferência em
  CPU ≤ 15 ms por linha; exportação ONNX (extra `onnx` já existe); charset com figurina.
  - *Verificação:* protótipo das duas arquiteturas treinado uma época na corrida-piloto, com tempo por
    linha medido em CPU.
  - *Saída:* ADR commitada com a escolha e os números.
  - *Reversão:* decisão escrita.
- **S-752** · Treino em CPU, com orçamento medido e contrato de modelo.
  - *Contexto:* esta máquina não tem CUDA. O classificador de glifo levou ~65 s por época sobre
    143.276 recortes de 32×32, 34 épocas (`texto_treino_20260823_pesos.json`); uma linha de 32×~600 px
    tem ~19× os pixels de um recorte, mais a BiLSTM — a estimativa grosseira é de **dezenas de horas
    por corrida**, e a S-754 e a S-755 pedem várias.
  - *Entrega:* (a) **corrida-piloto** medida (1 época sobre 10 mil linhas) antes de qualquer
    compromisso, e o orçamento total de CPU levado ao dono (D8); (b) **reprodutível** quer dizer: mesmo
    código, mesmo sha de dataset, mesma semente e `torch.use_deterministic_algorithms(True)` com número
    de threads fixo → métricas de validação iguais até a 4ª casa; (c) **ficha do modelo** — artefato
    nomeado pelo próprio sha, metadado com charset, tamanho de entrada, sha do dataset e do código,
    temperatura, e **recusa de carga** quando o par modelo/metadado se descasa (como o `char_meta`
    schema 2 faz hoje); o modelo anterior fica no disco; o sha do modelo entra na chave do cache da
    S-725; (d) temperatura calibrada **na validação**, nunca no teste.
  - *Verificação:* duas corridas com a mesma semente dão a mesma validação até a 4ª casa; carga de
    modelo com metadado trocado é recusada.
  - *Saída:* ficha do modelo publicada (`docs/metrics/texto_linha_<sha>.json`) com dados, código,
    semente, tempo e validação.
  - *Reversão:* o modelo anterior fica no disco (S-757).
- **S-753** · Decodificação com léxico e gramática de lance: busca em feixe sobre a saída CTC com o
  léxico da língua (S-728, congelado) na prosa e gramática SAN nos trechos de notação; nome próprio
  fora do léxico nunca é "corrigido" (S-209).
  - *Verificação:* na validação, decodificação gulosa contra feixe com léxico, pareado; nome próprio
    fora do léxico nunca trocado (teste com lista de nomes do acervo).
  - *Saída:* o feixe entra só com diferença pareada a favor na validação.
  - *Reversão:* parâmetro do decodificador.
- **S-754** · Generalização de fonte: deixar uma **família tipográfica** de fora.
  - *Contexto:* 7 livros dev em 2026-10-30, 5 famílias (Times em 3 deles). A auditoria da S-702
    reprovou os dois de Cambria e de Source Sans; os cinco que ficam têm 3 famílias (Times em 3, Arial,
    Calibri). Deixar um livro de fora quase nunca deixa a fonte de fora.
  - *Entrega:* uma dobra por família (Times, Calibri, Arial, e as que a D6 trouxer), IC95 por dobra,
    e o ouro-teste com estratos **fonte vista / fonte não vista** declarados no manifesto. É o primeiro
    número do projeto que mede generalização de fonte — a dívida da S-203.
  - *Verificação:* uma corrida por família tipográfica deixada de fora, IC por dobra.
  - *Saída:* "pior dobra não pior que a fusão com a melhor linha de base" é condição da S-755.
  - *Reversão:* medição; não muda o produto.
- **S-755** · Promoção, com regra declarada antes do treino e decidível com a amostra.
  - *Contexto:* superioridade estrita na prosa quase nunca é decidível com o teste que o acervo
    consegue montar. Medido com `amostra.py --pareado` sobre um par real do dev, o oráculo contra o
    Tesseract nas caixas do glifo (**−55% relativo**, seis livros, quarta medição): o teto do IC95 da
    diferença pareada relativa fica abaixo de zero em **8%** das simulações com 6 livros × 6 folhas,
    **7%** com 8, **28%** com 12, **23%** com 16 e **43%** com 24. Um efeito menor — o que um leitor novo
    contra a melhor linha de base costuma ter — cai abaixo disso: superioridade estrita na prosa quase nunca é decidível com
    o teste que o acervo consegue montar.
  - *Regra:* o leitor da casa vira o padrão **só se**, no ouro-teste **e** no scan-ouro-teste:
    (a) **não-inferioridade na prosa** — teto do IC95 da diferença pareada absoluta (casa − melhor
    degrau da S-745) ≤ **+0,05 p.p.**; (b) **superioridade decidível em pelo menos uma frente** que o
    degrau não tem — notação ou figurina (teto do IC da diferença < 0 em G1(b) ou G2) ou tempo (G4,
    média ≤ 70% da do degrau); (c) a pior dobra da S-754 não pior que o degrau; (d) o resultado se
    repete em **≥ 3 sementes**, com a dispersão publicada. Antes de abrir o teste, `amostra.py
    --pareado` estima o poder de (a) e (b) com as diferenças da validação; **sem poder ≥ 80% em (a) ou
    em (b), não há promoção** — o padrão fica com quem já está, e isso é a regra, não derrota.
  - *Verificação:* `amostra.py --pareado` antes de abrir o teste; depois, a regra aplicada nas três
    sementes, com o relatório da comparação publicado.
  - *Saída:* decisão escrita — promove ou não promove —, com o número de cada condição (a)–(d).
  - *Reversão:* S-757.
- **S-756** · O papel do glifo depois: notação, reserva e figurina; documentado no cabeçalho de
  `text/leitor.py`.
  - *Verificação:* o cabeçalho de `text/leitor.py` diz quem lê o quê, e um teste de fiação confirma
    que a notação continua indo ao glifo.
  - *Saída:* documentação e teste no mesmo commit da promoção (ou da não promoção).
  - *Reversão:* documentação.
- **S-757** · Reversão de modelo: o modelo anterior continua no disco e no metadado; a troca é um
  interruptor; **gatilho** de reversão escrito — queda da folha-canário (S-763) ou da concordância
  validada abaixo do limiar do dev, ou qualquer G violada numa remedição.
  - *Verificação:* teste que troca o modelo pelo interruptor e confere que o anterior carrega e lê a
    folha-canário igual ao que lia.
  - *Saída:* gatilho de reversão escrito no relatório da promoção.
  - *Reversão:* é o próprio item.

### Fase 106 — Confiança, revisão e aprendizado

- **S-760** · Confiança por palavra, calibrada por domínio.
  - *Contexto:* com ~99% de palavras certas, uma confiança **constante** já cumpre "ECE ≤ 0,03" — e o
    próprio projeto sabe: `calibracao.py` diz que o ECE ponderado "sai lisonjeiro por construção". A
    S-189 já tem `confianca_por_concordancia` (`text/leitura_de_linha.py`).
  - *Entrega:* calibrador ajustado na **validação** da Fase 105 (ou num pedaço reservado do dev, para o
    Tesseract), separado por domínio (digital / scan); medido por `ece_por_faixa` **e** pela curva
    risco–cobertura (erro restante contra fração de palavras aceitas sem revisão). Para a linha
    fundida, ele **substitui** a regra da S-189 (`confianca_por_concordancia`, em
    `text/leitura_de_linha.py`); a fila da S-212 e a coleta da S-214 passam a consumi-lo.
  - *Verificação:* `ece_por_faixa` e curva risco–cobertura na validação e no ouro-teste, por domínio.
  - *Saída:* calibrador publicado com as duas medidas; a fila da S-212 o consome.
  - *Reversão:* interruptor; desligado, vale a confiança de hoje (glifo calibrado, S-189).
- **S-761** · A faixa "revisar" que paga a atenção de quem revisa (G5): captura ≥ 90% das palavras
  erradas restantes marcando ≤ 5% das palavras, **por palavra** (os intervalos `confianca_em` da
  S-722), com teto do IC95 (captura ≥ 85% no limite inferior). Corte **próprio** da fusão: o
  `corte_de_revisar` de hoje é o `ocr.MIN_CONFIDENCE`, que o `pdf_pesquisavel` e a `coleta` também
  usam e que está no digest da S-218.
  - *Verificação:* no ouro-teste, captura de palavras erradas e fração marcada, com IC.
  - *Saída:* G5 cumprida (captura ≥ 90%, limite inferior ≥ 85%, marcadas ≤ 5%).
  - *Reversão:* o corte é constante própria da fusão; mudá-lo não mexe no `ocr.MIN_CONFIDENCE`.
- **S-762** · A correção humana volta como dado, sem contaminar nada.
  - *Contexto:* `correcao.py` carimba o **bloco inteiro** como `humano` quando se edita um caractere —
    inclusive as palavras erradas que ninguém conferiu —, e o próprio código diz que "a correção é
    registro, e não rótulo" e recusa "treinar o modelo no próprio erro" (`coleta.py`). E a S-703
    proíbe verdade ancorada no motor.
  - *Entrega:* procedência própria para texto corrigido sobre saída de motor
    (`corrigido_de:<motor>@<sha do modelo>`), **nunca** aceita no scan-ouro nem em teste nenhum; para
    o treino, só o par **palavra a palavra que a pessoa tocou**, pela quarentena da S-214, com a versão
    do modelo que gerou o texto registrada; livro do teste nunca entra.
  - *Verificação:* teste que reprova `corrigido_de:` no scan-ouro e em qualquer teste; teste que
    confere que só o par tocado vai à quarentena da S-214.
  - *Saída:* correções da aba Texto chegam à quarentena com a versão do modelo; nenhuma chega a teste.
  - *Reversão:* a quarentena é revisável; nada entra no treino sem passar por ela.
- **S-763** · Monitor de qualidade sem referência, validado antes de ser usado.
  - *Contexto:* a concordância glifo × leitor de linha **mede o glifo**, não a saída: por livro, a
    correlação entre o CER do glifo e o da fusão é só +0,51 por livro nos seis livros limpos (+0,46 por
    folha) — o *Minhas 60* tem glifo 6,92% e fusão 0,27%: a concordância anda com o erro do glifo, não
    com o da saída; ela é cega a leiaute, porque os dois leem as mesmas caixas; e em scan o WER do glifo
    é 35,7%, então um alarme ingênuo dispara sempre.
  - *Entrega:* três sinais, cada um com correlação e taxa de falso alarme **medidas no dev** contra o
    CER por folha, por domínio: a concordância (com base separada para digital e scan), a densidade de leitura da
    S-710, e uma **folha-canário** por língua com referência humana, relida a cada versão. Sinal que
    não correlacionar no dev não vira alarme.
  - *Verificação:* no dev, correlação de cada sinal com o CER por folha e taxa de falso alarme, por
    domínio, publicadas.
  - *Saída:* só vira alarme o sinal que correlacionar no dev; a folha-canário relida a cada versão.
  - *Reversão:* alarme é aviso; não muda texto.
- **S-764** · Regressão viva: cada família consertada vira teste escrito **antes** do conserto e
  conferido revertendo-o (a guarda que se pergunta ao próprio dado — memória
  `suite-de-treino-fases-80-a-86`). Duas camadas: a de **decisão** (a regra de geometria, de caixa, de
  fusão) testada com caixas e textos sintéticos, que roda no CI; e a de **leitura**, com recorte de
  linha binarizado e o classificador, sob o marcador `requer_modelo` — o `char_classifier.pt` não é
  versionado, e teste que pula para sempre no CI não guarda nada (`test_disciplina_da_suite`). Nada de
  folha de livro comercial em `tests/fixtures/` (hoje 200 KB, gerados por `gerar.py`).
  - *Verificação:* cada teste novo é rodado com o conserto revertido e precisa acusar; em clone limpo,
    os de decisão rodam e os `requer_modelo` pulam com motivo.
  - *Saída:* toda família consertada nas Fases 101–104 tem teste de decisão no CI.
  - *Reversão:* testes.

- **S-765** · O livro exportado leva o texto novo.
  - *Contexto:* o EPUB/DOCX da suíte leva do caderno só as folhas editadas ou conferidas; as outras a
    suíte relê com o motor dela (`text/caderno_na_suite.py`). Sem este item, o dono vê a prosa melhor na
    aba e o livro exportado continua com a de antes.
  - *Entrega:* conforme a D9 — ou o tronco envia à suíte as folhas lidas pelo leitor novo (mesmo
    formato 1 do `caderno_na_suite`), ou a suíte adota a fusão medida melhor na S-707.
  - *Verificação:* exportar um livro do ouro-dev e medir a prosa do EPUB na régua.
  - *Saída:* a prosa do livro exportado igual à da aba, folha a folha.
  - *Reversão:* o envio é opção da exportação.
- **S-766** · Corrigir uma vez, corrigir no livro inteiro.
  - *Contexto:* a S-762 leva a correção à quarentena de treino, não às folhas seguintes; a S-213
    (`semelhanca.py`) casa por imagem de glifo e não alcança a prosa que vem do Tesseract.
  - *Entrega:* palavras do livro no caderno — o nome que o dono corrigiu vira `--user-words` do executor
    e entra no árbitro nas folhas seguintes; "corrigir em todas as folhas" com prévia antes de aplicar.
  - *Verificação:* num livro do dev, quantos erros repetidos somem depois da primeira correção.
  - *Saída:* a medida publicada e a prévia obrigatória (nenhuma troca em massa sem o dono ver).
  - *Reversão:* a troca em massa vai ao caderno como corrigida e se desfaz folha a folha.

### Fase 107 — O portão final

- **S-770** · Medição de fecho nos conjuntos de teste (abertos só aqui): M0–M5 e G1–G6.
  - *Verificação:* `cvoff-texto-prosa` (ou, até a S-706 existir, `reproduzir.py` + `resumo.py` de
    `texto_prosa_2026-10-30/`) sobre ouro-teste, scan-ouro-teste e o degradado reservado, uma vez, com o
    relatório publicado antes de qualquer ajuste.
  - *Saída:* M0–M5 e G1–G6 com ponto e teto; o plano B da seção 3 aplicado se algum falhar.
  - *Reversão:* medição.
- **S-771** · README, ARCHITECTURE e o cabeçalho de `text/leitor.py` com o caminho novo e os números.
  - *Verificação:* `pytest tests/test_docs.py` verde; os números citados batem com o relatório (guarda
    de número vivo, como as que o `test_docs` já tem).
  - *Saída:* README, ARCHITECTURE e cabeçalho de `text/leitor.py` atualizados.
  - *Reversão:* documentação.
- **S-772** · Memória do projeto e a skill `ocr-texto-preciso` atualizadas com o que a execução ensinou.
  - *Verificação:* a memória e a skill citam o relatório final e não contradizem o roadmap.
  - *Saída:* memória e skill atualizadas no mesmo dia do portão final.
  - *Reversão:* documentação.

---

## 7. Riscos e decisões do dono

**Toda decisão tem prazo e recuo.** O prazo é o item que ela destrava; o recuo é o que acontece se o
dono não responder até lá — e o recuo **cumpre o próprio portão**, rotulado, em vez de travar o plano.

| | decisão | recomendação | prazo | se o dono não responder | o que custa |
|---|---|---|---|---|---|
| **D1** | Levar o Tesseract no instalador | **sim** | antes da S-724 | a fusão só existe onde o Tesseract estiver instalado à mão; o bundle lê com o glifo e avisa | ~48 MB a mais (34 DLLs, 24,9 MB, e o `tessdata` fast das 8 línguas, 22,6 MB, medidos pelo crítico da rodada 6), licenças de terceiros (S-724) |
| **D2** | Baixar `tessdata_best` | sim, depois da S-741 medir | antes da S-741 | fica o `fast` | ~15 MB por língua; download pede autorização |
| **D3** | Horas humanas para o scan-ouro | sim, ~15 h (30 folhas e a dupla digitação de 6) | começa no primeiro dia; precisa estar pronto antes do G104 | o G104 não fecha (M3/M4 sem número), e o produto sai dizendo que o erro de scan não foi medido | ~15 h humanas |
| **D4** | Aceitar o orçamento do G4 (a leitura com fusão custa ~2–3× a do glifo, e pela política da S-215 isso pode tirar o texto da varredura padrão) | sim | antes do G102 | a fusão fica atrás de interruptor e não vira padrão | varredura de livro inteiro mais lenta (seção 3, G4) |
| **D5** | Fontes, livros do acervo e **pesos derivados** (o `traineddata` ajustado da S-745, o modelo da Fase 105) | uso local; peso derivado de livro comercial **não** vai no instalador sem decisão expressa | antes da S-746 | os pesos ficam fora do bundle | licença das fontes comerciais e dos livros |
| **D6** | Trazer ≥ 12 livros digitais novos (nascidos digitais, com prosa, ≥ 3 línguas; 8 é o mínimo) para o ouro-teste — **entregue em 2026-10-30**: 36 independentes; falta a terceira língua (seção 5a) | **sim** | antes do G102 | os portões G102 e G103 rodam no **teste provisório** (folhas nunca lidas dos 7 livros dev), com o teto recalculado por `amostra.py` para 7 livros e todo número rotulado "provisório (livro visto)"; o G107 não fecha sem eles | trazer os PDFs |
| **D7** | Downloads da escada e do dataset: `tesstrain`, modelo PP-OCR latino, `frak2021` (se houver Fraktur), fontes completas, corpus de domínio público | sim, um a um, com **nome, origem, tamanho e licença** declarados | antes do item que o usa | o degrau da S-745 que depende dele é pulado e registrado | variável |
| **D8** | Orçamento de CPU da Fase 105 (dezenas de horas por corrida, várias corridas) | decidir depois da corrida-piloto da S-752 | antes da S-750 | a Fase 105 não começa; vale o plano B da seção 3 | horas de CPU desta máquina |
| **D9** | Quem escreve o livro exportado: o tronco envia as folhas lidas pelo leitor novo à suíte, ou a suíte adota a fusão que vencer na S-707 | o que a S-707 medir melhor | antes da S-765 | o livro exportado continua com o motor da suíte, e o relatório diz | coordenação entre os dois repositórios |

| risco | dono | sinal | mitigação | teste que prova a mitigação |
|---|---|---|---|---|
| a régua mede a referência e não o motor | executor da Fase 100 | oráculo alto numa folha; família que só existe num livro | admissão da S-702; taxonomia com livro de origem | teste da S-702 que reprova folha com lixo de figurina |
| ajuste no teste | crítico de cada item | limiar mudado depois de abrir o teste | teste só abre nos portões; manifesto com sha e data | teste que reprova manifesto de teste com data posterior à primeira leitura |
| leitor de linha "corrige" lance para palavra | executor da S-721 | figurina some na fusão | roteamento + G1(a) | invariante de preservação de figurina ≥ 99,5% no ouro |
| Tesseract ausente, de versão errada ou em quarentena do antivírus/Smart App Control | executor da S-720 | o executor devolve "não leu" | aviso visível (decisão 4), conferência de `--version`, glifo como reserva | teste com binário falso que devolve versão 4.x e com binário ausente |
| varredura do acervo cara demais | executor da S-725 | segundos por folha acima do G4 | G4 por estrato; reserva só na folha que a guarda marca; política da S-215 remedida | `cvoff-texto-custo` com `motor="fusao"` publicado |
| bundle sem licença ou acima do teto | executor da S-724 | arquivo novo no bundle sem aviso de licença | lista fechada de arquivos e pasta `licencas/` | teste que reprova binário embarcado sem arquivo de licença ao lado |
| cache enchendo o disco ou indo para o git | executor da S-725 | `data/cache_texto/` cresce sem limite; aparece em `git status` | teto em MB com despejo LRU; `.gitignore` no mesmo commit | teste de despejo; `test_docs` da tabela de persistência de `data/` |
| texto de livro comercial no repositório | quem commita | `*.jsonl` de medição, transcrição ou cache em `git status` | dados brutos fora do repositório (skill e `data/` ignorado); a transcrição da S-703 em pasta própria com backup | `git status --porcelain` limpo de `*.jsonl` no commit do item |
| S-218 | quem mexe em módulo compartilhado | módulo do digest de campo alterado | conferir `field_eval.measured_modules()` (na `main`, 34 módulos, entre eles `ocr.py`, `ocr_caption.py`, `pdf_io.py`, `pdf_text.py`, `service.py`, `settings.py`; nenhum de `text/`) | `test_field_eval` |
| sessões concorrentes na árvore principal | quem commita | arquivo cresce sob a edição; commit de outra sessão leva hunk alheio | worktree por item; staging cirúrgico (memória `checkout-principal-tem-sessoes-concorrentes`) | `git diff --cached` só com os próprios hunks |
| D3 ou D6 atrasam | dono | prazo da tabela acima vencido | o recuo da tabela, rotulado | o relatório de portão traz o rótulo "provisório" quando vale o recuo |
| scripts de medição sem versão | executor da Fase 100 | número publicado que nenhum código no git reproduz | `scripts_sha256` no relatório; os scripts entram no repositório na migração (topo) e viram pacote na S-700 | o sha gravado bate com o arquivo |

---

## 8. Sequenciamento e paralelismo

    100 ──┬── 101 ──────────────────────┐
          ├── 102 ──┬── 104 ─────────────┼── 107
          │         ├── 105 ─────────────┤
          │         └── 106 ─────────────┤
          └── 103 ───────────────────────┘
    S-703 (humano) começa junto com a 100 e é pré-requisito da 104
    D6 (livros novos) antes do portão G102

Dependências **entre itens** que o quadro de fases não mostra, e que um executor tropeçaria:

| item | depende de | por quê |
|---|---|---|
| S-715, S-717, S-720, S-721, S-723 | S-710 | o campo `PaginaLida.avisos` e a guarda nascem na S-710 |
| S-716 | — (começa no primeiro dia) | sem a S-710 ela só não avisa a folha não lida; com ela, cai na montagem da camada |
| S-717 | S-716 | o roteador de `text/fusao.py` nasce na S-716 |
| S-715, S-717 | S-720 | a reserva e a opção experimental são o Tesseract |
| S-716 | os critérios (a)–(d) da S-702 | a função de admissão foi escrita na S-702 (`text/admissao.py`) e é reaproveitada na S-716 |
| S-721 | S-707 | a fusão não é desenhada sem medir a da suíte |
| S-765 | D9, S-707 | quem escreve o livro exportado |
| S-718 | S-717 (dois leitores para discordarem), o léxico de hoje | medida "já no G102" |
| S-766 | S-720 (`--user-words`), S-721 (árbitro), S-762, o caderno | a correção do dono entra nas folhas seguintes |
| S-721, S-722 | S-716 | a S-716 entrega o roteador de tokens que a S-721 completa e adianta o campo `procedencia_em` da S-722 |
| S-729 | S-721, e a FEN do diagrama na `PaginaLida` (já na `main`) | o árbitro decide pela legalidade a partir da posição |
| S-711, S-712, S-714 | S-713 (com `tess_pagina`) | cada conserto de leiaute se mede contra a reserva |
| S-721 | S-720, S-723, S-728 | o executor, a língua do livro (que escolhe o `tessdata`) e o léxico por língua |
| S-746 | S-702 (os livros do teste, para a lista de exclusão), D6, D7 (`tesstrain`) | não se recorta linha de treino sem saber o que é teste |
| S-745 degrau 2 | S-746 | o ajuste fino treina nessas linhas e em nenhuma outra |
| S-750 | S-746, S-703, D6, D7 (fontes completas) | o dataset da casa estende o da S-746 |
| S-761 | S-722 | marcar palavra exige os intervalos `confianca_em` |
| S-760 | S-721 | calibra a confiança do que a fusão produz |
| virar o padrão (G102) | S-727, D4, D6 (ou o recuo dela) | os CLIs de medição fixam o motor antes; o dono aceita o tempo; o teste existe |
| S-726 | S-721 medida | só se aposenta o modo bloco depois de a fusão vencer na prosa |
| S-741 | S-725 (chave de cache completa) | senão a troca `fast`→`best` mede leitura antiga |
| M5, S-740 | S-703, S-704 (perfil calibrado) | sem scan-ouro não há calibração |

O caminho crítico é **100 → 101 → 102 → 105 → 107**: a 101 deixou de ser paralela opcional, porque
o leiaute perde folhas inteiras em silêncio (1.3) e nenhum portão de média sobrevive a um
livro de leiaute quebrado (seção 3). A Fase 103 é paralela e toca arquivos diferentes (101:
`regioes`, `negativo`, `linhas`; 103: `caixa_alta`, `marca_fina`, `colados`, `dicionario`; 102:
arquivos novos mais `leitor.py` e `pagina.py`) — o ponto de contato é `text/leitor.py`, e quem chegar
depois rebaseia. **A S-703 e a D6 são os itens de maior prazo** porque dependem de gente: começam no
primeiro dia.

---

## 9. Como executar um item: executor, crítico e portão

O método que deu certo na suíte de treino (memória `suite-de-treino-fases-80-a-86`), adaptado a OCR:

1. **Executor** lê a skill, o item e a seção 1; mede a linha de base do item **antes** de mexer.
2. Escreve o teste da família (S-764) e confere que ele falha.
3. Implementa atrás de interruptor; mede no **dev**; publica o relatório com commit e sha.
4. **Crítico independente** — outro agente, sem o raciocínio do executor — refaz a medição em
   árvore limpa, reverte o conserto e confere que a guarda acusa, procura a regressão em notação,
   figurina e tempo, e lê vinte palavras erradas que sobraram, à mão.
5. O item só fecha quando o crítico aprova; o portão de fase só abre o **teste** quando todos os
   itens da fase fecharam.

Anti-padrões já pagos neste projeto, que o crítico procura de propósito: régua que mistura prosa e
notação; medir por fora do `ler_pagina`; camada de OCR como verdade; livro duplicado contado duas
vezes; primeira leitura do processo sem aquecimento; tempo misturado na comparação de relatórios;
guarda que lê do próprio dado que deveria travar; limiar ajustado no teste.

---

## 10. Como reproduzir os números deste documento

Os scripts estão versionados em `docs/metrics/texto_prosa_2026-10-30/` e rodam com o `.venv` do projeto.
Eles abrem `PDF/` e `models/char_classifier.pt` da pasta em `CVOFF_RAIZ` e, sem ela, do repositório onde
o próprio script mora — o que só serve no checkout principal, porque os PDFs e o `.pt` não são
versionados e só existem lá. Os comandos abaixo rodam da raiz do checkout principal, com `CVOFF_RAIZ`
nela e `S` na pasta dos scripts; enquanto o ramo `texto-preciso` não chegar à `main`, `S` é essa pasta
dentro do worktree do ramo. Os comandos são de **Git Bash**; no PowerShell troque `$TEMP` por
`$env:TEMP`. A saída vai **sempre para fora do repositório** — o checkout principal é compartilhado por
várias sessões, e um `*.jsonl` na raiz dele suja a árvore de todo mundo.

**1. Saber qual código se está medindo.** O `.venv` tem uma instalação editável que aponta para
`src/` do **checkout principal**. Para medir um worktree (a `main`, ou o ramo de um item), é preciso
`PYTHONPATH=<worktree>/src`, copiar `models/char_classifier.pt` para `models/` do worktree (o `.pt` não
é versionado) e passar `--exigir-src <worktree>`: o `rodar.py` imprime e grava em cada folha o pacote
e o commit que mediu, e **recusa rodar** se o pacote importado não morar ali.

```bash
mkdir -p "$TEMP/regua_prosa"; export CVOFF_RAIZ="$PWD"; S=docs/metrics/texto_prosa_2026-10-30
```

```bash
PYTHONPATH="$WT/src" .venv/Scripts/python.exe "$S/rodar.py" --exigir-src "$WT" --livro "Dvoretsky - Dvoretsky's Endgame Manual (2025).pdf|eng|0" --paginas 154 --saida "$TEMP/regua_prosa/teste.jsonl"
```

(`$WT` é a pasta do worktree; para medir o checkout principal, sem `PYTHONPATH` e sem `--exigir-src`.)

**Admissão (S-716/S-702).** A tabela por livro da S-716 sai de uma corrida só do `admissao.py`,
com os 12 livros na ordem da tabela; a semente é por livro, então rodar um livro sozinho dá as mesmas
30 folhas. `todas` no lugar de `30` varre o livro inteiro, e `INI-FIM` uma faixa de folhas (base 1),
para dividir o livro em processos paralelos. O `admissao_livro_inteiro.tsv` publicado foi montado
assim, por faixas, com a versão do script de antes das colunas de perfil (7 colunas em vez de 9; a
lógica de admissão é a mesma, e as 7 colunas reproduzem com o script atual — conferido pelo crítico
da rodada 10 em duas faixas):

```bash
.venv/Scripts/python.exe "$S/admissao.py" "$TEMP/regua_prosa/admissao.tsv" 30 "Dvoretsky - Dvoretsky's Endgame Manual (2025).pdf" "1937 Kemeri.pdf"
```

**2. Reproduzir um conjunto inteiro.** As folhas de cada conjunto estão no próprio relatório
(`conjuntos.<nome>.por_livro.<livro>.folhas`, base 1, com a língua). `reproduzir.py` as lê dali — a
seleção automática (`--livro ...|n`) depende do classificador de token e **mudou** junto com ele
(hoje o Dvoretsky com `|4` escolhe as folhas `153, 328, 500, 677`, e o publicado é `155, 340, 509, 677`,
em base 1 como no relatório; o `--paginas` recebe base 0):

```bash
.venv/Scripts/python.exe "$S/reproduzir.py" docs/metrics/texto_prosa_20261030.json ouro_dev_completo "$TEMP/regua_prosa/ouro.jsonl"
```

```bash
.venv/Scripts/python.exe "$S/fusao_v5.py" "$TEMP/regua_prosa/ouro.jsonl" "$TEMP/regua_prosa/ouro_v5.jsonl"
```

```bash
.venv/Scripts/python.exe "$S/tess_pagina.py" "$TEMP/regua_prosa/ouro_v5.jsonl" "$TEMP/regua_prosa/ouro_pag.jsonl" 3
```

```bash
.venv/Scripts/python.exe "$S/filtrar.py" "$TEMP/regua_prosa/ouro_pag.jsonl" "$TEMP/regua_prosa/ouro_ok.jsonl" --sem-folha-perdida
```

```bash
.venv/Scripts/python.exe "$S/resumo.py" "$TEMP/regua_prosa/ouro_ok.jsonl" tip --pares fusao_v5-glifo,fusao_v5-tess,tess-tess_oraculo
```

- **Os outros conjuntos:** `ouro_dev_estrato_misto`, `degradado_medio_mesmas_folhas` (o
  `reproduzir.py` põe `--degradar medio --sem-rapid`) e `prata_todas` (põe `--sem-rapid`; depois
  `filtrar.py --oraculo-max 0.10` dá a `prata_admitida`).
- **Sem rodar motor de novo:** os JSONL de 2026-10-30 estão em
  `~/.claude/skills/ocr-texto-preciso/dados/2026-10-30/` (texto de livro comercial: uso local, nunca no
  repositório); `repontuar.py` refaz o placar quando a régua muda, `refazer.py --oraculo` refaz só o
  oráculo, e `publicar.py <destino.json> <pasta>` refaz este relatório a partir deles — conferido na
  migração: as 4.039 chaves voltam iguais, menos o `scripts_sha256` dos sete scripts que ela tocou.
- **Tamanho de amostra e poder:** `"$S/amostra.py" <jsonl> tess_oraculo tip` e
  `"$S/amostra.py" <jsonl> --pareado tess_oraculo tess tip`.
- **A guarda da S-710:** `"$S/cobertura.py" <saida.tsv> <jsonl>...` mede a densidade de leitura folha a
  folha.
- **Ver o que o leiaute achou:** `"$S/inspec.py" <pdf> <folha base 0> <saida.png>` desenha os blocos.

---

## 11. Registro das revisões críticas

Este documento passa por dez rodadas de um crítico independente que só aprova excelência, cada uma
com uma lente diferente. A tabela registra cada rodada assim que ela é aplicada; o que ela achou e o que
mudou fica escrito, inclusive quando a crítica desmentiu um número publicado antes.

| rodada | lente | veredito | o que achou (resumo) | o que mudou |
|---|---|---|---|---|
| 1 | metodologia de medição | **reprovado** (2 bloqueantes, 7 importantes) | o diagrama que o Seirawan desenha com fonte contava como prosa; livros chamados de "teste" tinham servido para desenhar régua e fusão; admissão do ouro dependia do motor avaliado; inserção e palavra colada escondidas numa classe não publicada; IC por folha ignorava o livro e os portões ficavam abaixo da resolução; a conclusão da 1.5 estava invertida (82 de 93 palavras eram erro real da fusão); G2 contava figurina lida; transcrição humana ancorada na fusão; população medida ≠ população do alvo | segunda medição inteira: linhas que cruzam diagrama fora; separador entre prosa é prosa; WER (S+D+I)/N; IC em dois níveis e diferença pareada; oráculo em linhas visuais; degradado nas mesmas folhas; estrato misto; fusão v5 (veto com léxico, número de lance só se partido); todos os livros declarados dev contaminado e ouro-teste com livros novos sorteados antes (D6); admissão sem motor; transcrição cega com acordo ≥ 99,9% em ≥ 6 folhas; perfil degradado a calibrar; G1 com invariante sem referência; G2 por precisão/revocação; tabela de tamanho de amostra; `tip` e `cru` publicados; scripts `filtrar.py`, `refazer.py`, `amostra.py` |
| 2 | arquitetura de software | **reprovado** (2 bloqueantes, 9 importantes) | o roadmap não dizia em que ponto do `ler_pagina` a fusão entra (depois dele, os intervalos de negrito/itálico por caractere e a junção de hífen se perdem); a v5 apagava a prosa quando o Tesseract não lia; a página não tinha onde guardar aviso nem procedência por palavra; `"linha"` era procedência mal definida e quebrava arquivo antigo; a integração do Tesseract ignorava o `ocr.py` existente, o console do Windows, timeout e caminho acentuado; a lista da S-218 estava errada; léxico e classificador compartilhados quebravam a reversão; o modo bloco tinha consumidores não listados; cache sem chave completa; testes que não rodariam no CI; e o documento estava escrito sobre um ramo 119 commits atrás da `main` | fusão no fim de `linhas_do_glifo`, antes do estilo e da junção de hífen; "não leu" (`None`) separado de "leu vazio" e prosa do glifo sem par preservada; S-710 cria `avisos`, S-722 cria `procedencia_em`/`confianca_em`, procedência `tesseract`, versão de arquivo subida e item declarado irreversível; executor próprio em `text/tesseract.py` (stdin, `CREATE_NO_WINDOW`, timeout, `stderr` como aviso); S-218 por `measured_modules()`; palavras curtas privadas da fusão e roteador separado da régua; S-726 com todos os consumidores; chave de cache completa; fixtures sintéticas e marcador `requer_modelo`; manifestos em `assets/texto_prosa/`; S-727 (CLIs fixam o motor) e S-728 (léxico por língua); a `main` declarada base e **a linha de base reproduzida nela, idêntica em 95 folhas** (1.7) |
| 3 | engenharia de ML | **reprovado** (3 bloqueantes, 8 importantes) | o teste vazava pelos ativos derivados (léxico tirado da camada dos livros, nomes, PGN que cita os livros, série da mesma editora); a promoção "≥ 20% relativo" não era decidível; a correção humana voltava ao scan-ouro e ao treino como verdade (o caderno carimba o bloco inteiro como `humano`); a Fase 105 não separava treino, validação e dev, e as fontes dos PDFs são subconjuntos; ECE vácuo com 99% de acerto; a concordância não fora validada como monitor (correlação −0,14 com o CER da fusão); livro-novo não media fonte nova; o aumento usava o gerador que avalia a M5; a M1 não tinha item que a pagasse; faltavam linhas de base fortes; nenhum orçamento de CPU nem contrato de modelo | lista de exclusão por livro e por série aplicada a imagem, corpus, PGN, léxico, nomes e fontes, com teste de n-gramas; S-755 reescrita como não-inferioridade + superioridade numa frente decidível, com poder ≥ 80% e 3 sementes, e a **simulação de poder** na seção 3 e no `amostra.py`; S-762 com procedência `corrigido_de` e só pares tocados; quatro conjuntos na Fase 105 e `cmap` conferido; S-760 por `ece_por_faixa` e curva risco–cobertura, por domínio; S-763 com sinais validados no dev e folha-canário; S-754 por família tipográfica; M5 em família de degradação reservada e com o alvo da M3; **orçamento de erro da M1** e plano B declarado; S-745 (escada: `best`, ajuste fino do Tesseract, PP-OCR latino); S-752 com corrida-piloto, definição de reprodutível e ficha; S-757 (reversão); D7 e D8; ressalva do 99,1% e números reais na S-736 |
| 4 | domínio de OCR | **reprovado** (1 bloqueante, 6 importantes) | metade do "erro de reconhecimento" do oráculo era da régua (lance com reticência, símbolo Informator `ʘ`, fileira de coordenadas em fonte contados como prosa); o leiaute do próprio Tesseract nunca fora medido como reserva; "220 dpi" não é escala — um quarto do acervo é scan de 144–150 dpi com altura-x de 7–10 px; "scan" misturava ClearScan, scan pobre e scan bom, e o ouro admitiria ClearScan; notação descritiva e cirílica viravam prosa; a legalidade do lance, o modelo de língua da notação, não era usada; a S-743 mirava Fraktur em livros Antiqua com algarismos antigos; o protótipo declarava `--dpi 300` sobre imagem de 220 | classificador da régua refeito (reticência, Informator, coordenadas, descritiva en/es, cirílico, `X`/`:`, cruz `t`) e **terceira régua aplicada a tudo**: oráculo 0,38% → **0,16%**, orçamento da M1 refeito (o reconhecimento já está quase pago; leiaute e roteamento são o caminho); **S-715** (leiaute de reserva do Tesseract, medido: resgata as 5 folhas perdidas) e `tess_pagina` na S-713; escala do recorte pela altura-x e scan pela imagem nativa (S-720, S-740); critério (d) contra ClearScan na S-702 e estratos por produção e resolução na S-703/S-705/M3; não-inferioridade no scan no G102; **S-729** (árbitro de notação pela legalidade, G1(c)); S-743 reescrita; `--dpi` real (medido: mesmo CER), dicionário desligado na notação, `--user-words` e n-gramas como degrau 0 da S-745; 8 línguas em toda parte |
| 5 | executabilidade a frio | **reprovado** (3 bloqueantes, 5 importantes) | medir num worktree media o checkout principal em silêncio (instalação editável) e quebrava sem o `.pt`; a guarda da S-710, implementada como escrita, dava cobertura 1,000 na folha perdida e falso alarme em folha boa; S-750 sem critério de pronto e em ciclo com a S-745; 51 de 52 itens sem algum de *Verificação*/*Saída*/*Reversão*; números velhos espalhados (G101, Fase 103, S-704, S-763, README, skill); reprodução dependente do scratchpad e de uma seleção de folhas que mudou com a régua; nada commitado; comando da skill que quebrava no PowerShell e sujava a árvore | `rodar.py` grava pacote e commit medidos e recusa rodar fora de `--exigir-src`, com `--modelo`; **guarda refeita por medição**: densidade de leitura (0,905–1,285 nas 90 folhas legíveis, 0,001–0,007 nas 5 perdidas), corte 0,5, `ESQUEMA` declarado; S-746 quebra o ciclo; os 52 itens com os três campos; passada de números contra o relatório; `reproduzir.py` lê as folhas do relatório; dados brutos preservados na skill; seção 10 com saída fora do repositório e o passo de worktree; nota de commit no topo; S-715 com critério mensurável para o *Kmoch*; nomes corrigidos (S-760, S-726, 9 de 9) |
| 6 | riscos e operação | **reprovado** (1 bloqueante, 8 importantes) | D3 e D6 travavam G101/G102 sem prazo nem dependência; o G4 ignorava a política de custo da S-215 e o tamanho real do acervo (25.918 folhas, não 12.000) e tinha três números; empilhar as linhas (`psm 6`) mudava o texto em 14 de 55 linhas; o bundle não tinha lista de arquivos, teto nem licenças (DLLs LGPL e GPL com exceção); binário resolvido sem conferir versão e procurando na pasta corrente; cache sem teto e fora do `.gitignore`; scripts de medição sem versão; riscos sem dono nem teste; a migração do plano criaria duas cópias; caminho absoluto no registro; sem orçamento de memória, timeout nem proteção contra processo órfão | decisões com prazo e recuo que cumpre o portão (provisório rotulado); G101 sem scan-ouro, G102 com não-inferioridade na prata por estrato e remedida no G104; G4 único, por estrato, com a reserva no p95 e o custo do acervo orçado; S-725 com TIFF de várias páginas (texto idêntico, medido), cache com teto, LRU, `atomic_io` e `.gitignore`; S-724 com lista fechada (+60 MB de teto) e `licencas/`; S-720 com resolução segura, `--version`, memória medida, timeout, *Job Object* e teto de megapixels; seção 7 com dono e teste por risco e os riscos que faltavam; procedimento de migração exato no topo; `scripts_sha256` no relatório e registro sem caminho absoluto |
| 7 | produto e experiência do dono | **reprovado** (4 bloqueantes, 6 importantes) | nenhuma entrega visível nem prazo — a primeira mudança na aba vinha depois de ~23 itens; o padrão que o G102 liga não chegaria à janela (a aba passa o motor explícito, restaura o gravado e reabre o caderno sem reler); nos livros digitais a prosa da camada **é** a tinta e o plano não a usava; o livro exportado não melhoraria, e a suíte irmã já tem fusão token a token que o roadmap ignorava; a faixa "revisar" pintaria a confiança do glifo sobre o texto do Tesseract; metas sem tradução para "palavras por folha" e título que prometia demais; decisões em jargão e prazos em número de item; as 15 horas da S-703 sem ferramenta e com procedência que a S-762 recusaria; negrito e itálico sem guarda; nada de "corrigir uma vez, corrigir no livro"; G4 medido no CLI e não na janela | **seção 5a** com a primeira entrega (S-716 prosa da camada nos digitais, S-710, S-715, S-720+S-717 opção experimental na caixa de motor, S-718 marca honesta por palavra; duas a três semanas), a tabela "o que você vai ver" em palavras por folha e "o que preciso de você agora" com datas; título e promessa redefinidos; G102 vira padrão **na janela** (o que `auto` passa a ser, migração do estado, reler folhas não corrigidas, teste de fiação); S-707 mede a suíte antes da S-721; S-765 (o livro exportado) e D9; S-718 e G5 provisória; S-703 com modo transcrição e procedência `transcricao`; G6 (estilo); S-766; G4 medido na janela |
| 8 | convenções do repositório e integridade | **reprovado** (1 bloqueante, 5 importantes) | a migração copiaria scripts que quebram a CI da `main` (87 erros de `ruff`, `cv2.imwrite` proibido pela S-432, caminhos fixos) para uma pasta fora da convenção; a S-715 ainda disparava pela cobertura reprovada e citava números do *Kmoch* errados; a G6 fora do portão final e do quadro de fases; a skill divergia do roadmap no G4; a seção 8 não cobria S-718, S-766 nem o que a S-716 adianta; o `publicar.py` não refazia o bloco escrito à mão; separadores, ordem de itens e de campos, bases de numeração e números miúdos (palavras por folha do scan, *Kmoch* 69, "metade", o 0,1397 vencido) | scripts limpos (`ruff` da `main`: "All checks passed!", sem `imwrite`, caminhos só do ambiente) e **placar idêntico** depois da limpeza (0 de 520 placares mudaram); migração para `docs/metrics/texto_prosa_2026-10-30/` com suíte inteira e `ruff check .`; S-715 pela densidade; G6 em S-770, Fase 102 e 107; dependências novas; `publicar.py` gera o bloco da `main` e os descritores atuais; itens e campos em ordem; 5a com 272 palavras por folha de scan; skill alinhada (G4, G6, numeração, LEIA-ME); `test_docs` simulado na `main` pelo crítico: 35 passaram |
| 9 | adversarial (a afirmação mais fraca) | **reprovado** (2 bloqueantes, 6 importantes) | M1/M2 ficariam vácuas depois da S-716 (camada contra camada) e nenhuma meta dizia que motor mede; **a montagem da régua duplicava o cabeçalho** (`PARTIDA 13` duas vezes) e fabricava metade da "perda de leiaute"; o "roteamento −0,10" era ruído e o orçamento fechava por álgebra; a guarda de densidade não vê perda parcial e dá falso alarme em capa (e havia mais duas folhas perdidas fora da amostra); a G1(a) reprovaria vetos certos e contava presença, não acerto; a marca "honesta" da S-718 inundaria (10–40% das palavras); o tamanho de amostra fora calculado no oráculo; a primeira entrega dependia de formato adiado; "duas a três semanas" sem base; "5 de 58" e "não há digital não lido" errados | **quarta medição inteira** com a montagem do produto (fusão 0,28% nos seis livros limpos; leiaute +0,12 não significativo; a 1.3 e a seção 2 reescritas); **M0** (o produto nas folhas da camada, com auditoria visual) e M1/M2 declaradas bancada; orçamento com portão por parcela e a soma rebaixada a conferência; guarda restrita a perda total, com segundo sinal de perda parcial, componente com altura de letra e amostra estratificada por tipo de folha; G1(a) sem vetos registrados no denominador e veto de outra língua = erro; S-718 ranqueia e trava em 5%; tamanho de amostra no nível da fusão (≥ 12 livros, probabilidade de passar publicada) e poder refeito (7% com 8 livros); a primeira entrega não grava formato novo; prazo com base (15 dias-executor, 3–4 semanas); **a regra de fusão por estrato** (v3 no scan: 6,2% contra 7,0%) |
| 10 | portão final: tudo de novo, contra o JSON | **reprovado** (1 bloqueante, 4 importantes) → **reprovado** (2 importantes) → **aprovado** (3 menores) | 1ª passada: o critério (b) da admissão ("nenhum trecho em fonte de diagrama") recusaria todo o Dvoretsky, que desenha o tabuleiro em `Chess-Merida` — o livro que a 5a promete; números da terceira medição sobreviviam fora das seções 1 e 5a (S-704, S-710, S-763 com correlação −0,14 que hoje é +0,51, G3 "5 de 58"); a skill não acompanhara a rodada 9; a S-716 não começava a frio (sem motor nomeado, sem mapeamento camada → linha, sem comando); a S-721 só especificava a v5. 2ª passada: a tabela de admissão não se reproduzia (um gerador aleatório para todos os livros: a amostra mudava com a ordem) e a regra por folha "texto raso sobre imagem", criada para o carimbo do *Kemeri*, recusava ao menos 72 + 48 folhas com texto dos *Chess Evolution*; a skill ainda ensinava o (b) antigo; "fonte de diagrama" e "de figurina" se sobrepunham (`merida`, `alpha`, `leipzig`) e o (b) nunca tinha disparado; o 89,6% do RapidOCR não saía do JSON | (b) por **fileira** de tabuleiro (6+ caracteres encostados fora dos retângulos; caractere solto é figurina) com teste de falsificação (`--sem-retangulos`: 29 de 30 folhas do Dvoretsky recusadas, fileira de 8; numa cópia fora da tabela recusou 2 folhas, e eram tabuleiros sem retângulo); a regra por folha trocada por uma de **livro** no (a) (livro de scan: 29 de 30 folhas de perfil invisíveis no *Kemeri*, 0 nos digitais); semente por livro e tabela regerada numa corrida, reproduzida em ordem inversa; os dois *Chess Evolution* varridos inteiros: 0 recusas em 2.917 folhas com texto; passada mecânica de todos os números contra o JSON; S-716 com motor `camada_prosa`, mapeamento e comando; S-721 com regras por estrato, estrato em execução e régua estendida a `--motor fusao`; skill realinhada; RapidOCR 92% (344 de 374) e poder pareado no JSON |

Depois da rodada 10, o crítico aprovou o documento com três observações menores, todas consertadas
no mesmo dia: o LEIA-ME dos dados passou a listar o `admissao_livro_inteiro.tsv`, a seção 10 diz como
esse arquivo foi montado, e a migração diz de onde os scripts tiram a raiz do checkout.
