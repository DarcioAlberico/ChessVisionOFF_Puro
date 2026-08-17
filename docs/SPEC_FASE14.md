# Especificação das melhorias — Fases 14 a 19 (S-95 a S-142)

Base: [ROADMAP_FASE14.md](ROADMAP_FASE14.md), que traz a avaliação de 2026-08-16 e o
sequenciamento. Continuação de [SPEC_FASE7.md](SPEC_FASE7.md) (S-37 a S-75),
[ANALISE_DETECCAO.md](ANALISE_DETECCAO.md) (S-78 a S-82) e
[PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md) (S-83 a S-94).

> **Onde mora cada item.** A spec deste projeto está espalhada por seis arquivos, e essa
> dispersão custou duas entregas — a S-76 e a S-77 não estão em documento nenhum. Este índice
> é o remédio de curto prazo; a S-134 o torna verificável por teste.
>
> | itens | arquivo |
> |---|---|
> | S-01 a S-36 | [SPEC.md](SPEC.md) |
> | S-37 a S-75 | [SPEC_FASE7.md](SPEC_FASE7.md) |
> | S-76, S-77 | **em lugar nenhum** — a S-133 as registra |
> | S-78 a S-82 | [ANALISE_DETECCAO.md](ANALISE_DETECCAO.md) |
> | S-83 a S-94 | [PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md) |
> | S-95 a S-142 | este arquivo |

Cada item tem **Problema** (com arquivo:linha do estado atual), **Solução**, **Critério de
aceite** e **Testes**. A convenção é a de sempre: nomes de módulo são sugestão, o que importa
é a fronteira de responsabilidade. Todos os números citados foram medidos nesta máquina em
2026-08-16, e o comando que os produz está ao lado.

**Uma regra vale para toda esta spec.** Nenhum item de modelo, de detecção ou de decodificação
pode ser julgado antes de a Fase 14 fechar. As duas réguas do projeto — o split de teste e o
conjunto de campo — estão contaminadas pelo que deveriam julgar, e medir contra régua
contaminada foi o que reprovou quatro itens da Fase 7 sem que ninguém soubesse se eles
funcionavam.

---

# Fase 14 — A régua

> O projeto não sabe se lê certo. Esta fase é o instrumento que responde isso, e ela vem
> primeiro porque tudo o que vier depois será julgado por ela.

## S-95 · A verdade de referência deixa de ser a leitura do próprio modelo ✅ implementada (2026-08-16)

**Problema.** `app_tkinter.py:952-956` monta a anotação do conjunto de campo a partir de
`item.placement`, que é **o que o modelo leu**:

```python
lidos = {item.index: item for item in self._page_items(self.page_index)}
rascunho.reset_from(
    [
        (box.bbox_pdf, getattr(lidos.get(indice), "placement", "") or "")
        for indice, box in enumerate(caixas.boxes if caixas is not None else ())
    ]
)
```

A correção humana mora em `fen_edits`, uma lista paralela, e a separação é deliberada
(`ui/editor_model.py:19`, `ui/result_panel.py:15`):

> `fen_edits[i]` é o que o usuário está editando *agora*; `items[i].placement` é o que o
> modelo leu. Fundi-los perderia a leitura original.

A anotação lê o lado errado. **Corrigir o tabuleiro e clicar "Anotar página" grava a leitura
errada como verdade de referência.** `ui/field_draft.py:112-114` avisa contra exatamente isso,
mas só para o campo `reviewed`:

> medir o modelo contra a própria saída dá 1,000 em tudo e não significa nada.

A guarda foi posta em `reviewed` e esquecida em `placement`.

**A prova está no disco.** Dos 39 diagramas anotados, **um** tem FEN de referência: a capa
(página 0) do Yusupov, `4r2R/7Q/6R1/3rrrr1/1R1rrrR1/6Pq/2k1r1Q1/3b2q1` — sem rei branco, 9
torres pretas, 2 damas brancas. `chess.Board(...).status()` devolve `NO_WHITE_KING`.

**Solução.** Duas mudanças, e a segunda é a que impede a repetição.

1. `_field_draft` passa a ler `result_panel.fen_edits[i]` — a propriedade já existe
   (`ui/result_panel.py:204`) e o cache por página já guarda `fen_edits`
   (`ui/result_panel.py:391,413`), então a correção sobrevive à navegação.
2. **A FEN só entra quando alguém a confirmou.** `items[i].edited_by_hand` e
   `EditorModel.has_hand_edits` já distinguem lido de conferido. Diagrama não conferido entra
   com `placement=""`, que o conjunto sempre aceitou e é honesto: caixa anotada, posição não.

A decisão de *de onde vem a verdade* sai de `app_tkinter.py` e vira função pura em
`ui/field_draft.py`: `reset_from` recebe `(bbox, placement, confirmado)` e descarta o
`placement` não confirmado. É a regra da S-31 — o que dá para testar não fica na janela.

**Limpeza do dado existente.** A linha do Yusupov p0 sai do `field_set.jsonl` com backup
datado ao lado, como a S-76 fez com os 1.405 diagramas. Uma FEN ilegal como referência não é
um número ruim: é um número que mente para cima.

**Critério de aceite.** Corrigir uma peça e anotar grava a FEN **corrigida**; anotar sem tocar
no tabuleiro grava `placement=""`; nenhuma posição fatalmente ilegal entra como referência
(guarda por `fen_utils.check_position`).

**Testes.** `tests/test_field_draft.py` — a FEN gravada é a editada e não a lida; sem
confirmação humana o `placement` sai vazio; posição fatalmente ilegal é recusada com o motivo.
O teste de regressão usa leitura e correção **diferentes entre si**, que é o par que falhava
em silêncio.

### O que foi entregue, e o que a medição diz

`FieldDraft.reset_from` passou a receber `(bbox, colocação, conferida)` e
`app_tkinter._page_confirmed_placements` é quem responde de onde vem cada uma — de
`fen_edits`, e não de `items[i].placement`. A guarda de legalidade
(`field_draft._referencia_aceitavel`) recusa notação inválida e posição **fatalmente** ilegal;
ilegal por turno continua entrando, porque é assim que o livro desenha final parcial.

**Dirigido na janela de verdade**, que é o único lugar onde este defeito aparecia (o roteiro
do CONTRIBUTING, `Karpov p100`, 6 diagramas lidos):

| | |
|---|---|
| leitura do modelo | `1kb4r/2q2p2/pp4r1/2bPp2n/2p1P2p/...` |
| correção feita no tabuleiro | `4k3/8/8/8/8/8/8/4K3` |
| **o que o rascunho gravou** | **`4k3/8/8/8/8/8/8/4K3`** |
| os 5 diagramas não conferidos | `""` nos cinco |

**O dado existente foi limpo**, com backup datado em `data/field_set.jsonl.bak-20260816_153807`:
a única colocação do conjunto era a capa do Yusupov, e ela saiu. `cvoff-field` deixou de
publicar o número falso:

```
antes:  Exatidão condicional ......... 1.000   (1 comparável, uma alucinação)
depois: Exatidão condicional ......... — (nenhuma anotação traz a posição)
```

O relatório já sabia dizer "—" quando não há comparável; o que o impedia era a linha ruim. A
exatidão de campo passa a existir de verdade na S-96, e o que enche o `comparable` é a S-99.

---

## S-96 · A exatidão de campo passa a existir ✅ implementada (2026-08-16)

**Problema.** `field_eval.py:404-406` só conta `exact` onde a anotação tem `placement`:

```python
if anotado.placement:
    relatorio.comparable += 1
    relatorio.exact += int(lido.placement == anotado.placement)
```

Com 1 de 39, `comparable=1`. **A métrica primária — a taxa de exportação — mede "o modelo teve
confiança ≥ 0,80 e a posição era legal", não "o modelo leu certo".** Uma leitura confiantemente
errada entra como acerto.

A troca foi consciente (a flag `--no-placement` existe e o *help* a defende com um argumento
correto). O que nunca foi nomeado é o custo: a 7.7 descobriu que a taxa de exportação é *"uma
catraca que só desce"* e atribuiu isso à distribuição bimodal da confiança. A explicação está
um nível abaixo — **uma métrica de confiança não pode medir correção** — e quatro itens de spec
foram julgados por ela.

**Solução.** `cvoff-field` passa a relatar duas medidas lado a lado:

| medida | o que responde | hoje |
|---|---|---|
| taxa de exportação | quanto sai do livro | 0,7179 |
| **exatidão de campo** | quanto do que saiu está **certo** | não medida |

Três regras no relatório:

- `comparable` aparece **ao lado** de toda taxa derivada dele;
- com `comparable / annotated < 0,5`, imprime `insuficiente (n=1 de 39)` no lugar do número —
  um número sem amostra não deve ter aparência de número;
- **"exportado e errado" vira categoria própria**, com a lista dos diagramas. Um diagrama que
  sai errado com confiança alta é pior que um que não sai: o primeiro vai para o PGN e para o
  dataset como verdade, o segundo vai para o `.review.pgn`, que é onde deve ir.

**Onde anotar primeiro.** Nos **28 que passam o gate**, e não nos 39. A assimetria é o
argumento: no diagrama barrado a FEN não vai a lugar nenhum e conferi-la não compra nada; no
aceito ela vira PGN sem que ninguém olhe.

**Critério de aceite.** `cvoff-field` relata exatidão com `n` explícito; com `comparable`
baixo recusa o número; "exportado e errado" aparece com a lista.

**Testes.** `tests/test_field_eval.py` — exatidão sobre conjunto sintético com uma leitura
certa e uma errada; a recusa do número quando `comparable` é baixo; "exportado e errado" conta
o diagrama que passou o gate com FEN diferente da referência.

### O que foi entregue, e o que a medição diz

Três medidas, e a separação entre elas é o item:

| medida | denominador | responde |
|---|---|---|
| taxa de exportação | anotados | quanto sai do livro |
| **exatidão de campo** | **exportados com referência** | quanto do que saiu está certo |
| exatidão condicional | todos com referência | quanto o modelo lê certo, saindo ou não |

`exported_wrong` é categoria própria e vem **antes** dos barrados no relatório, de propósito: o
que não sai vai para o `.review.pgn` e alguém olha; o que sai errado entra no PGN e no dataset
como verdade.

**A recusa é a parte que não parece código.** Com `comparable / annotated < 50%`
(`MIN_COMPARABLE_SHARE`), o relatório imprime *"insuficiente para medir"* com o `n` e o mínimo,
em vez do número — e explica, ali mesmo, que a taxa de exportação acima mede confiança e não
correção. O JSON continua saindo cru, com `comparable_share` e `enough_comparable` ao lado,
porque quem refaz a conta precisa dos números e quem lê o relatório precisa da ressalva.

**O estado de hoje, que é o ponto de partida honesto:**

```
  Do PGN até estar certo (S-96)
    Conferíveis .................. 0 de 39 anotados  (0%)
    Exatidão ..................... insuficiente para medir  (0 de 39, mínimo 50%)
```

**O caminho de medição foi exercitado ponta a ponta** num conjunto descartável, com as
referências vindas da própria leitura do modelo e **uma** trocada de propósito. Não é medição
de qualidade — é o teste do relatório:

```
    Conferíveis .................. 36 de 39 anotados  (92%)
    **Exatidão de campo** ........ 0.9643  (27/28 exportados)
    Exatidão condicional ......... 0.9722  (35/36)
    **Exportados e errados** ..... 1

  O que saiu **errado** para o PGN (1):
      1937 Kemeri.pdf p80: exportado e errado (confiança 0.993)
        leu       5rkn/1R3p1p/5p2/3Bp2P/4P3/6P1/5P2/6K1
        referência 4k3/8/8/8/8/8/8/4K3
```

**A confiança do diagrama errado era 0,993.** É a demonstração do item numa linha: nenhum gate
razoável o barraria, e a taxa de exportação o conta como sucesso.

**O que falta para o número existir de verdade é a S-99** — as FENs conferidas. Até lá o
relatório diz que não sabe, que é a única coisa honesta que ele pode dizer.

---

## S-97 · O conjunto de campo declara a página que o modelo treinou ✅ implementada (2026-08-16)

**Problema.** Cruzando `data/field_set.jsonl` com `data/labels.csv` por
`(source_pdf, source_page-1)`:

| | |
|---|---|
| diagramas anotados | 39 |
| **em páginas de que há amostra rotulada** | **7 — 17,9%** |
| split dessas amostras hoje | **`train`, todas as 9** |

São `Karpov A - Chess Combinations 1` p80 (6 diagramas) e `1937 Kemeri` p187 (1). Os sete
passam o gate — o Karpov exporta **12/12** no relatório de hoje.

**A ressalva, e ela é o que dá urgência ao item.** O checkpoint de produção é de 2026-08-09
10:51 (2.660 amostras); das nove, **oito são de 2026-08-10** e uma é de 2026-08-09 10:09. O
número de **hoje** quase não sofre: o modelo que produz a métrica não viu esses recortes.

Mas a S-107 retreina, e no momento em que isso acontece as nove entram no treino e **o conjunto
de campo passa a medir o modelo em páginas que ele aprendeu** — sem aviso, e exatamente na
medição que decide a promoção. É uma armadilha que fecha no próximo passo: barata agora,
cara depois.

O conjunto de campo existe, nas palavras do próprio `field_eval`, porque o split de teste não
descreve a entrada do produto. Nada no relatório diz que parte dele deixou de ser independente.

**Solução.** `evaluate_field` consulta `labels.saved_diagrams_by_page` (`labels.py:523`, já
pronto e testado) e marca a página como contaminada quando um diagrama anotado casa com uma
amostra de `train`. O relatório ganha:

- a contagem `contaminated` ao lado de `annotated`;
- a taxa de exportação **também** sobre o subconjunto limpo, que é a que vale;
- a lista das páginas contaminadas, para que crescer o conjunto saiba de onde fugir.

**Não é para remover a página.** Remover encolheria um conjunto que já é pequeno demais. É para
que o número apareça, porque hoje ele não aparece — e o critério de saída da fase é sobre o
subconjunto limpo.

**Critério de aceite.** O relatório de hoje declara 2 páginas e 7 diagramas contaminados; a
taxa limpa aparece ao lado da geral; anotar uma página nova avisa na barra se ela tem amostra
de treino.

**Testes.** `tests/test_field_eval.py` — a marcação de contaminação com `labels.csv` sintético;
a taxa limpa exclui a página contaminada; página sem amostra não é marcada.

### O que foi entregue, e o número que ele revelou

`labels.pages_with_training_samples` responde `{(livro, página): quantas amostras de train}`,
e `evaluate_page` recebe a contagem por página. O relatório ganhou a contagem, a **taxa limpa**
e a lista das páginas.

**A diferença entre as duas taxas é maior do que a estimativa da avaliação sugeria:**

```
    **Taxa de exportação** ....... 0.7179  (28/39)
    Em páginas com treino ........ 7 de 39  (18%)
    **Exportação limpa** ......... 0.6562  (21/32)
```

**6,2 pontos percentuais.** Os sete diagramas contaminados exportam **todos** — o que faz
sentido e é o pior caso: a contaminação não é ruído em torno do número, é viés **para cima**.
Contra o alvo de 0,85 da Fase 7, a distância real é de 0,19 e não de 0,13.

As duas páginas, com o que cada uma carrega:

```
  Páginas de que há amostra de **treino** (2):
      1937 Kemeri.pdf p187: 1 diagrama(s) anotado(s), 1 amostra(s) de treino desta página
      Karpov A - ... p80: 6 diagrama(s) anotado(s), 8 amostra(s) de treino desta página
```

**Nada é removido**, e isso é decisão: o conjunto tem 39 diagramas e jogar 18% fora o deixaria
sem resolução nenhuma. O que muda é que o viés passa a ser **publicado em vez de estimado** —
que é a mesma regra da S-96 para a exatidão.

**Na tela**, `_refresh_field_status` avisa **antes** do clique:

```
p80:  anotada: 6 diagramas · vetorial · ⚠ 8 amostra(s) de treino desta página
p100: página não anotada
```

Anotar uma página assim não é proibido — o conjunto é pequeno demais para recusar página —,
mas passa a ser escolha e não acidente. É o que a S-99 precisa saber para escolher de onde
crescer.

---

## S-98 · O mesmo diagrama impresso não cruza split ✅ implementada (2026-08-16)

**Problema.** Cruzando `labels.csv` com `splits.csv` por
`(source_pdf, source_page, source_diagram)`:

```
Schiller - The Big Book of Combinations p41 d1   ->  train, test
Secrets of Chess Training p19 d1                 ->  train, val
Niemeijer - Zwarte Magie p10 d1                  ->  train, val, test
```

**Três diagramas impressos cruzam split, e um está nos três.** O guarda de grupo da S-07
agrupa por semelhança de imagem — ele vê cópia quase byte a byte, não vê o mesmo diagrama
reextraído com recorte diferente, que é o caso quando a mesma página é varrida duas vezes com
o detector ajustado no meio.

O `BASELINE.md` registra 0,9906 de acurácia exata no teste, que é **3 tabuleiros errados em
320**. A contaminação é da mesma ordem de grandeza do erro que o número mede.

**O mecanismo.** `DUPLICATE_HAMMING_THRESHOLD = 3` (`audit.py:41`) foi calibrado para *"a mesma
amostra salva duas vezes"* (`audit.py:242-247`), não para *"a mesma página reextraída com
recorte deslocado"*. Como `append_training_sample` gera nome novo por timestamp
(`dataset.py:443`) e `ensure_splits` sorteia pelo hash do nome (`splits.py:206`), o mesmo
diagrama impresso cai em splits diferentes. `find_duplicate_groups` sobre o dataset inteiro
devolve 373 grupos e **0 espalhados entre splits** — a frase de `cli/audit.py:110` (*"a
validação segue honesta"*) é verdadeira pela definição de grupo e vazia na prática.

**O tamanho, medido, do mais forte para o mais fraco.** Esta gradação existe porque a primeira
versão desta análise afirmou um número alto e a verificação o derrubou:

| evidência | test | val |
|---|---|---|
| **procedência** — mesma tripla `(pdf, página, diagrama)` | **2** | 2 |
| **imagem forte** — dHash ≤ 8 **e** correlação de pixels ≥ 0,70 | **4** de 354 | **8** de 346 |
| indício — dHash ≤ 8 só | 15 | 12 |

A última linha **não é contaminação medida**: nenhum dos 18 pares tem procedência dos dois
lados, e um par de d=5 aberto à mão (`board_20260225_221807_137303.png` × `board_20260227_
005100_915559.png`, FEN `8/8/6kp/1p6/5P2/1P6/P6K/8`) mostra peças visivelmente diferentes com o
mesmo rótulo — ou seja, o corte em 8 também captura **rótulo errado**, que é outro problema.

**O impacto, corrigido.** O `BASELINE.md` publica 0,9906 = 3 erros em **320** tabuleiros, de um
`splits.csv` de 3.195 linhas; o `test` de hoje tem 354. A contaminação demonstrável é de **2 a
4 tabuleiros — 0,6 a 1,2 ponto**, da mesma ordem do erro medido e **dentro do ±1 ponto de IC95
que o `BASELINE.md:74` já declara**. Não é que o número esteja muito errado: é que ele **não
separa generalização de memorização na faixa em que se move**, e é nessa faixa que a Fase 5 e a
S-40 arbitraram.

**E há uma defesa já escrita e desligada.** `groups_by_book` (`splits.py:94`) existe e
**nenhum código de produção a chama** — só `tests/test_provenance.py`.

**Solução.**

1. **`groups_by_origin(entries)`** em `splits.py`, agrupando por `(source_pdf, source_page,
   source_diagram)`, unido aos grupos de imagem. **Com o alcance declarado no docstring:** 625
   de 3.936 linhas (15,9%) têm procedência; ele resolve as 3 triplas e **nenhum** dos casos sem
   procedência. O mapa `arquivo → tripla` é novo — `saved_diagrams_by_page` tem outra
   assinatura e outro recorte, e não serve.
2. **`SPLIT_GROUP_HAMMING_THRESHOLD` separado**, usado só por `duplicate_groups_touching`,
   mantendo o 3 no `--dedupe`, onde um falso positivo **apaga rótulo**. O valor sai de medição,
   não de palpite: com o corte em 8 e sem exigir correlação entram pares de rótulo divergente.
3. **O reparo do passivo é uma decisão, não um automatismo.** Mover linha de `test` é
   irreversível na prática. `cvoff-audit --split-leaks` **lista** os pares e propõe o
   movimento; quem aplica é gente. A direção não pode ser "a do membro mais antigo" — medido, o
   mais antigo do Niemeijer e o do Secrets estão em `val`, e segui-lo puxaria membros de
   `train` para `val`, que é a direção que contamina. A regra é **sempre em direção ao
   `train`**.

**Critério de aceite.** Nenhuma tripla com mais de um split (hoje 3); nenhum par test↔train com
dHash ≤ 8 **e** correlação ≥ 0,70 (hoje 4). E `cvoff-eval --split test` antes e depois do
reparo: **se o número não se mover, o vazamento era inofensivo, e isso também é resultado que
vale registrar.**

**Testes.** `tests/test_splits.py` — o agrupamento por origem; a união com o de imagem; a
estabilidade da S-07 preservada. `tests/test_labels.py` — `label_origins` passa pela porta
única do `labels.csv`.

### O que foi entregue, e o que a medição diz

`splits.groups_by_origin` agrupa pela tripla exata; `training.resolve_splits` **une** os dois
agrupamentos (o de imagem e o de origem) antes de chamar `ensure_splits`; e
`labels.label_origins` é a leitura, pela porta única da S-51.

O reparo do passivo ficou como **relato**, e não como movimento automático — a decisão de
mover uma linha de `test` é de gente. `cvoff-audit` passou a listar, com os membros e o split
de cada um:

```
    Mesmo diagrama em 2+ splits .. 3  (S-98)

  Mesmo diagrama impresso em splits diferentes (3) -- vazamento de treino:
      Niemeijer - Zwarte Magie 100 zwarte dame-problemen (1945).pdf p10 d1
        board_20260810_035556_807024.png  [val]
        board_20260810_035657_014325.png  [train]
        board_20260810_035815_652578.png  [test]
        board_20260810_040016_057788.png  [train]
      Schiller - The Big Book of Combinations (1994).pdf p41 d1  [train] [test]
      Secrets of Chess Training School of Future Champions 1_ao_5.pdf p19 d1  [val] [train]
```

**E uma frase do relatório saiu.** Ele dizia *"membros de um grupo continuam no mesmo split,
então a validação segue honesta"* — verdadeira pela definição de grupo e vazia na prática,
porque o grupo não vê o recorte deslocado. Agora ele diz o que o grupo cobre e mostra, logo
abaixo, o que ele não cobre.

**O que isto não resolve, declarado:** os 3.311 rótulos sem procedência (84,1%) continuam com
o guarda de imagem, e para eles o caminho é recuperar procedência — não este agrupamento.

---

## S-99 · Crescer o conjunto: 60 páginas, cinco regimes, FEN conferida ⚠ **metade entregue** (2026-08-16)

**Problema.** A S-41 planejou 60 páginas e o conjunto tem **17**, com 39 diagramas e **1** FEN.
A S-77 construiu a ferramenta e ela foi usada duas vezes. O ROADMAP_FASE7 chama isto de *"a
pendência que destrava as outras"* desde 2026-08-11.

**E há ordem obrigatória:** crescer o conjunto antes da S-95 é pior que não crescer, porque
cada clique acrescenta verdade que é a saída do modelo.

**Solução.** Não é código: é trabalho humano com a ferramenta consertada. O que a spec fixa é a
**forma**, para que o conjunto meça o que precisa medir:

| regime | páginas hoje | alvo | por quê |
|---|---|---|---|
| `scan-puro` | 6 | 15 | é onde a exportação está em 0,400 |
| `scan-hachurado` | 4 | 12 | os barrados estão todos abaixo de 0,43 — falha de domínio |
| `vetorial` | 3 | 12 | está em 1,000; serve de controle contra regressão |
| `fonte` | 1 | 6 | idem |
| `sem-diagrama` | 3 | 15 | **são as únicas que medem falso positivo** |
| **total** | **17** | **60** | |

**A FEN conferida é obrigatória nos que passam o gate.** Sem ela a S-96 não tem o que medir.
Custo honesto: confirmar uma caixa é um clique, conferir 64 casas é ler o diagrama —
estimativa de ~3 h, das quais ~2 h são as FENs.

**Preferir páginas sem amostra de treino** (S-97), e cobrir os dois livros que hoje exportam
zero: `Euwe, Kramer - Das Mittelspiel Band 1-2` e `GALLAGHER - Winning With the King's Gambit`.

**Critério de aceite.** 60 páginas revisadas, os cinco regimes no alvo, `comparable ≥ 30`, e a
distribuição de confiança mínima com **pelo menos 5 diagramas na faixa 0,60–0,80** — a condição
que a 7.7 apontou como ausente e sem a qual nenhum modelo se distingue de outro.

**Testes.** Não há teste que substitua isto. O que há é a guarda da S-100.

### O que foi feito, e o que não foi (2026-08-16)

**A metade da FEN foi feita; a metade das páginas não.** O conjunto continua com **17 páginas**;
o que mudou é que **31 dos 39 diagramas agora têm posição de referência** (0 antes), e a
exatidão de campo deixou de ser "insuficiente para medir".

Método: cada diagrama foi renderizado a partir do recorte 800×800 **warpado** — o mesmo que o
modelo vê, para que uma divergência seja erro de leitura e não de recorte — com uma grade
`a-h`/`1-8` sobreposta. A posição foi transcrita **antes** de olhar o que o modelo tinha lido, e
só depois comparada.

**O resultado:**

```
    Conferíveis .................. 31 de 39 anotados  (79%)
    **Exatidão de campo** ........ 1.0000  (28/28 exportados)
    Exatidão condicional ......... 0.9032  (28/31)
    **Exportados e errados** ..... 0
```

**E ele reorganiza a leitura da Fase 7.** As três leituras erradas são exatamente as três que o
gate **barrou** — confianças 0,058, 0,001 e 0,056. Nenhuma leitura errada passou. Ou seja: o
modelo **não** exporta lixo; ele se recusa a exportar 28% do que existe. O gate é preciso e
custa recall — e o trabalho rende em detecção e cobertura, não em acurácia de leitura.

### As ressalvas, e elas são grandes

**1. Eu errei muito, e o registro disto vale mais que o número.** Nas 6 divergências iniciais
contra o modelo, **eu estava errado em 5** — todas de **cor** da peça (`b01` c7, `b02` c1,
`b18` h4, `b19` a7, `b30` d7). Resolvi cada uma comparando a casa em disputa com uma peça
branca e uma preta **do mesmo diagrama**; no `Kemeri p187` foi preciso medir o brilho do miolo
(114,7 na disputada, contra 170,5 na torre branca e 98,4 no cavalo preto) para aceitar que a
peça era preta. Mais um erro meu — uma fila deslocada e um rei branco esquecido — foi pego pela
**guarda de legalidade**, não por mim. Taxa bruta antes de corrigir: **6 em 31, ~19%**.

**2. O erro correlacionado é invisível.** Nos 23 diagramas em que eu e o modelo concordamos de
primeira, se os dois erramos igual a referência está errada e a métrica não acusa. Este
conjunto é **mais forte que a saída do modelo** — foi lido por gente, contra a imagem — mas
**não é verdade independente** no sentido estrito.

**3. O 1,000 é sobre o regime fácil.** Dos 28 exportados, 22 são `vetorial` ou `fonte`, que são
renderizações vetoriais nítidas. O número diz pouco sobre `scan-hachurado`, onde quase tudo é
barrado antes de chegar ao gate.

**4. O que falta da S-99 é a parte que muda a resolução:** as 43 páginas restantes, os regimes
abaixo do alvo, e os ≥5 diagramas na faixa de confiança 0,60–0,80. O conjunto mede melhor
**leitura** agora; ele continua sem poder distinguir dois modelos.

---

## S-100 · O conjunto vigente é declarado, e a comparação volta a ser honesta ✅ implementada (2026-08-17)

**Problema.** O conjunto mudou de 15 páginas/38 diagramas para 17/39 em 2026-08-15, e **todas
as medições citadas nos documentos são do conjunto antigo**. `cvoff-field` hoje devolve 0,7179
onde os docs dizem 0,7368; a precisão de detecção aparece em 0,9231 contra 0,9722, com 3 falsos
positivos contra 1. Nenhuma dessas comparações é limpa — as duas pontas mediram conjuntos
diferentes — e nada no projeto avisa.

As tabelas que **reprovaram** S-38b, S-40, S-62a e S-62b comparam variantes sobre 38 diagramas.
Uma variante medida hoje entra numa tabela com que não é comparável.

**Solução.** O JSON do `cvoff-field` já grava `pages` e `annotated`. Falta usá-los:

- `docs/EXPERIMENTS_FASE7.md` ganha no topo a declaração do conjunto vigente e a data em que
  ele mudou;
- um teste lê `data/field_set.jsonl` e **falha** quando um relatório citado como corrente foi
  medido sobre outro conjunto, dizendo qual ele mediu e qual é o de hoje;
- o controle é regravado sobre o conjunto de hoje quando a S-99 fechar — não antes, porque
  regravá-lo duas vezes é pagar duas vezes pela mesma resposta.

**Critério de aceite.** Um relatório antigo citado como corrente faz a suíte falhar com a
mensagem certa.

**Testes.** `tests/test_field_eval.py` — a guarda de conjunto vigente, com JSON sintético de
conjunto antigo.

### O que foi entregue

`field_set_identity` devolve `{pages, annotated}` contando **só as revisadas** -- é o que
`evaluate_field` mede, e os dois números já saíam no JSON com esses nomes. O que faltava era
compará-los.

**Medido, e confirma o enunciado linha por linha:**

| | páginas / diagramas |
|---|---|
| `field_20260809*.json` e `field_20260811*.json` (15 relatórios) | **15 / 38** |
| `field_20260816*.json` e os três da S-107 | **17 / 39** |

**A lista mora no teste, no molde do `SEM_REGISTRO` da S-112.** `RELATORIOS_CORRENTES` nomeia
os quatro relatórios que os documentos apresentam como o número de agora, **com o porquê de
cada um**; os quinze da Fase 7 ficam de fora de propósito, porque são registro histórico e o
cabeçalho do `EXPERIMENTS_FASE7.md` declara o conjunto deles.

Quando a S-99 crescer o conjunto para 60 páginas, a suíte falha em bloco -- e é o ponto: cada
linha da lista tem de ser remedida ou sair, e a decisão passa a ser explícita.

**O cabeçalho do `EXPERIMENTS_FASE7.md`** ganhou o aviso com a tabela das duas medições lado a
lado, e a frase que importa: *a diferença de 0,019 na taxa de exportação é da ordem das
diferenças que decidiram aqueles vereditos*.

**O controle não foi regravado sobre o conjunto de hoje**, e é decisão: a S-99 ainda vai
crescê-lo de 17 para 60 páginas, e regravá-lo duas vezes é pagar duas vezes pela mesma
resposta.

---

# Fase 15 — O dataset e o treino que não mentem

## S-101 · `--dedupe` muda o tamanho de `val`/`test`, e nada registra isso ✅ implementada (2026-08-16)

> **Redimensionado pela verificação.** A primeira versão deste item afirmava que `--dedupe`
> encolheria os conjuntos reservados "sem consultar o split" e quebraria a comparabilidade. A
> primeira metade é verdade e a segunda não; fica registrado porque o motivo importa.

**O que se confirma.** `remove_duplicate_labels` (`audit.py:400-406`) monta
`{name for group in report.duplicate_groups for name in group[1:]}` e chama `LabelStore.remove`
sem consultar `data/splits.csv`. Medido, `cvoff-audit --dedupe` apagaria **433 linhas**: 313 de
`train`, **22 de `test` (6,2%)**, **29 de `val` (8,4%)** e 69 sem split.

**O que refuta o alarme.** Medido também: dos 373 grupos redundantes, **0 se espalham entre
splits**, e **0** linhas removidas têm o representante mantido noutro split. Não é sorte — é a
S-07 funcionando: `splits.group_keys` (`splits.py:73-88`) mapeia cada membro para
`sorted(group)[0]`, exatamente o nome que `find_duplicate_groups` mantém. **Toda linha de
`val`/`test` que sairia é cópia de um representante que fica no mesmo `val`/`test`.**

Então o dedupe não contamina e não muda quais diagramas distintos cada split contém. O que ele
muda é a **contagem**: o `test` passa de 354 para 332 linhas, e um número medido depois deixa
de ser comparável, por denominador, com um medido antes — sem que nada avise. É o mesmo
problema da S-100, num artefato diferente.

**Solução.** Não é mudar o `--dedupe`: é registrar o que ele fez.

- `--dedupe` grava, ao lado do backup datado que já faz, um resumo `{antes, depois, por split}`
  em `docs/metrics/dedupe_<data>.json`;
- o `BASELINE.md` passa a citar o tamanho do `test` junto com o número, porque "0,9906" sem
  "em 320 tabuleiros" não é reproduzível — e hoje o documento já traz os dois, o que se quer é
  que continue trazendo depois de cada limpeza;
- a guarda da S-100 (relatório antigo citado como corrente) passa a comparar também o tamanho
  do split.

**A ordem em relação à S-98 continua importando**, por outro motivo: a S-98 pode mover linhas
entre splits, e mover depois de apagar é apagar informação que ajudaria a decidir para onde
mover.

**Critério de aceite.** Depois de um `--dedupe`, existe o registro do que saiu e de quanto cada
split encolheu; um número publicado sobre o `test` antigo citado como corrente faz a suíte
falhar.

**Testes.** `tests/test_audit.py` — o resumo gravado; a contagem por split confere com o que
foi removido.

### O que foi entregue

`dedupe_summary(report, splits_path)` calcula `{antes, removidos, depois}` por split, e
`write_dedupe_summary` grava em `docs/metrics/dedupe_<data>.json`. O `cvoff-audit --dedupe`
chama os dois **antes** de remover — depois não há como saber de que split cada linha saiu.

Em `docs/metrics/` e não em `data/`: é a mesma categoria dos relatórios de campo e de censo —
número publicado, versionado, e que serve para explicar por que dois números da mesma coisa
não batem.

**`groups_across_splits` fica no arquivo mesmo valendo zero.** É o número que refutou o alarme
original deste item, e é ele que mostra, na próxima limpeza, se a garantia da S-07 deixou de
valer. Uma linha sem split entra como `(sem split)` em vez de sumir da conta.

**Seis testes**, entre eles a contagem por split conferindo com o que o `--dedupe` de fato
removeu, e o grupo que atravessa split aparecendo no resumo.

**O que a spec pedia e não entrou:** a guarda da S-100 comparando também o tamanho do split, e
o `BASELINE.md` citando o `n` ao lado do número. As duas dependem da S-100, que continua
aberta — o registro que este item entrega é o insumo delas.

---

## S-102 · A auditoria barra em vez de relatar ✅ implementada (2026-08-16)

**Problema.** `cvoff-audit` hoje, sem argumento nenhum:

```
!! Redundância acima do teto: 11,0% > 10% (S-63).
   433 amostras redundantes em 373 grupos
   357 amostras sem split
   1 imagem ausente
```

O teto da S-63 **estourou** e o comando sai com código **0** (verificado). Nada no fluxo
consulta a auditoria antes de treinar: a CI roda `ruff`, `mypy`, `pytest` e um teste de import;
`cvoff-train` monta o dataset sem perguntar nada. A imagem ausente é, nas palavras do próprio
relatório, *"descartada em silêncio no treino"*.

**Solução.** Três coisas, e a primeira é a que muda comportamento:

1. `cvoff-audit --strict` sai com **código 1** quando um limite declarado é violado. Sem
   `--strict` continua relatando e saindo 0 — o comando é usado para olhar, e quebrá-lo para
   quem olha seria trocar um problema por outro.
2. `cvoff-train` roda a auditoria antes de montar o dataset e **recusa** quando ela reprova,
   com `--force` para quem sabe o que está fazendo. A mensagem diz o comando que conserta.
3. A CI ganha um passo `cvoff-audit --strict`, que num clone limpo (sem `data/samples/`) pula
   como os outros testes de dados.

**O teto de 10% não é sagrado.** Ele foi escolhido na S-63 para vigiar crescimento. Se 11% for
aceitável, a decisão é subir o teto **explicitamente** e registrar por quê — não é deixar o
alarme tocando.

**Critério de aceite.** `cvoff-audit --strict` no estado de hoje sai 1 e nomeia a violação;
depois da S-101 e do dedupe, sai 0. `cvoff-train` sem `--force` recusa treinar sobre dataset
reprovado.

**Testes.** `tests/test_audit.py` — o código de saída sob cada violação. `tests/test_cli.py` —
`cvoff-train` recusa, e a mensagem cita o comando de conserto.

### O que foi entregue

`AuditReport.violations()` devolve os limites **já declarados** que o relatório viola, em pt-BR
e **com o conserto ao lado** — uma violação sem conserto ao lado é um beco. São quatro: ilegal
fatal, FEN não interpretável, PNG ausente e o teto de redundância da S-63.

Três coisas ficam de fora de propósito, e cada uma tem teste: amostra sem split (quem atribui é
o `cvoff-train`, na linha seguinte — barrar aqui seria barrar o conserto), ilegal confirmada à
mão (decisão humana registrada, S-70) e vazamento de split (o remédio é mover linha, que a S-98
se recusa a fazer sozinha; barrar por algo que o comando não conserta deixaria o projeto sem
saída).

**Medido no dataset de hoje**, e é o critério de aceite:

```
$ cvoff-audit --strict        -> RC=1
  - 1 rótulo(s) com PNG ausente -- conserto: cvoff-audit --drop-missing
  - redundância em 11.0%, acima do teto de 10% (S-63) -- conserto: cvoff-audit --dedupe,
    ou suba o teto explicitamente e registre por quê
$ cvoff-audit                 -> RC=0
$ cvoff-train                 -> RC=2, "a auditoria reprovou o dataset, e o treino não começou"
```

O portão do `cvoff-train` roda com `check_duplicates=False`: pular o hash perceptual de
milhares de imagens 800×800 é o que o mantém barato. Em troca, o teto de redundância não é
conferido ali — é o único dos quatro que precisa dos hashes, e vigiá-lo é trabalho do
`cvoff-audit --strict`. O que o portão pega são os três que corrompem o **treino desta
execução**.

**O que não entrou: o passo na CI.** O `.github/workflows` não ganhou `cvoff-audit --strict` —
num clone limpo `data/samples/` está vazio e o passo precisaria pular como os testes de dados
fazem, e isso é configuração de CI, não código. Fica como pendência nomeada.

---

## S-103 · `split_hash` conferido onde ele importa ✅ implementada (2026-08-16)

**Problema.** `grep split_hash` em `src/` devolve quatro ocorrências, **todas em
`training.py`**: escrito em `training.py:824`, lido só em `_resolve_best_metric`
(`training.py:444`) para decidir se confia na métrica gravada.

`evaluation.evaluate_split` (`evaluation.py:437-465`) e `cli/evaluate.py:176` carregam
`data/splits.csv` e avaliam o checkpoint **sem conferir nada**. A S-07 inteira existe para
tornar impossível medir num conjunto que o modelo já viu, e o dado que fecharia essa porta está
gravado no arquivo desde a Fase 5, ao alcance de um `if`.

**Solução.** `evaluate_split` recebe o `Checkpoint` (que já carrega por `load_model`) e emite
`logger.warning` em três casos, com texto diferente para cada um:

| caso | o que dizer |
|---|---|
| metadados ausentes | checkpoint legado; o número não é auditável |
| `split_hash` vazio | treinado com `--no-splits` — a palavra é **contaminado** |
| `split_hash` diferente do `splits.csv` atual | o modelo foi treinado sobre outra partição; diga os dois hashes |

Aviso e não recusa: há motivo legítimo para comparar um checkpoint antigo, e recusar
impediria a própria auditoria histórica. Mas o número sai com a ressalva ao lado, no texto e
no JSON.

**Critério de aceite.** `cvoff-eval` com checkpoint de outra partição avisa e grava a ressalva
no JSON; com o checkpoint da partição atual, nada muda.

**Testes.** `tests/test_evaluation.py` — os três avisos, sob `assertLogs`; a ressalva no JSON.

### O que foi entregue

`evaluation.split_caveat(model_path, splits)` devolve a ressalva em pt-BR, ou `""`, e
`evaluate_split` a grava em `EvaluationReport.split_caveat`. Os testes moram em
`tests/test_split_caveat.py` (não havia `test_evaluation.py`), e a ressalva é **campo do
relatório** em vez de `logger.warning`: aviso de log não sobrevive à cópia do número para um
documento, e é exatamente aí que a contaminação vira baseline.

**No texto ela vem antes dos números.** Uma ressalva impressa embaixo de um `0,9906` é lida
depois de o número já ter sido anotado.

**No JSON ela sai vazia quando não há o que ressalvar, e não ausente.** Chave ausente obrigaria
quem lê a distinguir *"não havia ressalva"* de *"esta medição é de antes da S-103"*.

**O primeiro uso já encontrou um caso real:**

```
$ cvoff-eval --split val --model models/piece_classifier.pt

  !! Ressalva sobre a partição
     o checkpoint foi treinado sobre outra partição (`split_hash`
     cf7b6cf571f4045d, e o `splits.csv` de agora é 41c44c1caf132b8d): parte
     do que está sendo avaliado pode ter estado no treino dele.
```

É o modelo **de produção**. O `splits.csv` mudou no retreino da S-107, que atribuiu split às
357 amostras que estavam sem — e desde então qualquer avaliação do `piece_classifier.pt` sobre
`val`/`test` carrega essa ressalva. Até agora ela não aparecia em lugar nenhum.

---

## S-104 · O desempate entre épocas empatadas: medir antes de mudar ✅ medido (2026-08-17) — não mudar nada

> **Dívida de baixa severidade, e o item é uma medição.** A primeira versão desta análise
> classificou isto como defeito e propôs a mudança direto. A verificação derrubou a
> classificação, e o registro fica porque o motivo vale mais que o veredito.

**O fato, que se confirma.** `BestEpochPolicy.accepts` (`training.py:593-595`) é
`metric > self.best_metric`, com `metric_for_best = validation.board_exact_accuracy`
(`training.py:915`). A métrica tem granularidade de **um tabuleiro** — 1/306 = 0,00327 no `val`
da Fase 5 — então empate é comum. Em `docs/metrics/phase5_training.json` o máximo é atingido
por duas épocas em **3 de 3** execuções, e em **2 delas** a época gravada tem `val_loss` maior
que a da outra empatada:

| execução | épocas empatadas | `val_loss` gravada | `val_loss` da outra |
|---|---|---|---|
| `phase5` | 6 e 8 | 0,007025 | **0,006036** (−16,4%) |
| `phase5_res32` | 7 e 8 | 0,004034 | **0,003859** (−4,5%) |
| `phase5_mobilenet` | 4 e 6 | **0,001967** | 0,002621 — a gravada já é a melhor |

**Por que não é defeito.** O `>` estrito é decisão escrita e travada por teste.
`training.py:594` diz: *"Estritamente maior: empatar não regrava, porque regravar sem ganho é
risco de graça"*, e `tests/test_training.py:764-770` a trava com a razão explícita —
*"regravar sem ganho é reescrever 8,7 MB e correr o risco da S-57 de graça"*. Um desempate por
`val_loss` faz exatamente o que essa razão proíbe: regrava 8,7 MB por um ganho de **zero
tabuleiros** na métrica que decide.

**E o que não se pode afirmar** é que a época de menor `val_loss` seja melhor no produto.
`val_loss` é entropia cruzada por casa; a métrica de produto é a taxa de exportação, e a Fase 7
já mostrou que as duas se movem em direções diferentes — quatro variantes com validações
distintas deram exportações idênticas.

**Solução: medir, e só então decidir.** Num treino com empate, gravar os dois checkpoints
(`--keep-ties`, que só existe para o experimento) e rodar `cvoff-field` nos dois, depois da
Fase 14. Três resultados possíveis, e os três são resposta:

| se | então |
|---|---|
| a de menor `val_loss` exporta mais | o desempate entra, e o custo de 8,7 MB está pago |
| dão o mesmo | o `>` estrito fica, e agora com número ao lado em vez de argumento |
| a de maior `val_loss` exporta mais | o desempate está errado, e isso é o mais interessante dos três |

**Critério de aceite.** A decisão fica registrada no ROADMAP com o número que a sustenta,
**inclusive se for "não mudar nada"**.

**Testes.** `tests/test_training.py` — `--keep-ties` grava os dois e não altera o padrão; o
teste `test_empatar_nao_regrava` continua verde e intacto.

### O que foi entregue: a ferramenta. A decisão espera o número.

`--keep-ties` grava a época empatada em `<modelo>.tie-e<N>.pt`, **ao lado e não por cima**: o
principal continua sendo o que a política escolheu, e a comparação entre os dois é o que se
quer medir. Um nome por época porque um treino pode empatar mais de uma vez.

O arquivo carrega `tie_with_best_epoch` nos metadados — sem isso, um `.tie-*.pt` copiado para
outro nome seria indistinguível de um checkpoint que a política escolheu, e o experimento
inteiro depende de saber qual é qual.

A guarda mora **antes** do `observe`: ele move o incumbente, e depois dele não há mais como
saber que a época empatou em vez de perder.

**Cinco testes**, entre eles o que separa "empatou" de "piorou" e o que confirma que sem a flag
nada muda. `test_empatar_nao_regrava` continua verde e intacto.

### A decisão: não mudar nada

A tabela inteira está no [ROADMAP_FASE14](ROADMAP_FASE14.md). Os dois números, em resumo:

- **Empate no máximo: 0 de 3 execuções** sobre o dataset de hoje, contra 3 de 3 na Fase 5. A
  validação passou de ~306 para 385 tabuleiros, e um tabuleiro vale 0,0026 em vez de 0,0033 —
  métrica mais fina, empate mais raro. O desempate quase nunca chegaria a disparar.
- **1,3 ponto de validação não move o conjunto de campo.** O `--keep-ties` gravou a época 4
  (0,9688) ao lado da 5 (0,9818), e as duas dão taxa de exportação, exportação limpa, exatidão
  de campo e exportados-e-errados **idênticos**. Se 1,3 pp não move nada, um gap de zero — que
  é o que define empate — move menos ainda.

Então o desempate regravaria 8,7 MB e correria o risco da S-57 por uma diferença que a métrica
de produto não enxerga. O `>` estrito fica, agora com número ao lado em vez de argumento.

**A ressalva:** o conjunto de campo não distinguir duas coisas não prova que são iguais — é a
mesma limitação que a S-107 registrou. O número autoriza *não pagar* pela diferença; não
autoriza dizer que as duas épocas leem igual.

---

## S-105 · O checkpoint guarda o que reproduz o número ✅ implementada (2026-08-17)

**Problema.** Os metadados de `models/piece_classifier.pt` trazem `arch_version`, `seed`,
`class_weights`, `augment_version`, `split_hash`, `dataset_size`, `git_commit`, `best_metric` e
a calibração. **Ausentes:** taxa de aprendizado, tamanho de lote, número de épocas pedido,
otimizador, e qualquer identidade do **conteúdo** dos rótulos.

`cvoff-train --lr 1e-4` e `cvoff-train --lr 1e-3` produzem dois arquivos indistinguíveis pelos
metadados, e há 17 checkpoints em `models/`. O `EXPERIMENTS_FASE7.md` compara nove treinos.

**Solução.** `metadata_base` recebe `**asdict(plan.optim)` e ganha `labels_hash`: SHA-256 dos
pares `(filename, fen)` ordenados **do split de treino**, calculado no mesmo lugar onde
`split_hash` já é. O `split_hash` diz *qual partição*; o `labels_hash` diz *qual verdade* — e é
ele que muda quando 468 amostras entram sem que a partição mude.

**Critério de aceite.** Dois treinos que diferem só no `--lr` produzem checkpoints com
metadados diferentes; corrigir uma FEN e retreinar muda o `labels_hash` com o `split_hash`
intacto.

**Testes.** `tests/test_checkpoint.py` — os campos novos; `labels_hash` estável sob reordenação
e sensível a uma FEN corrigida.

### O que foi entregue

Quatro campos de otimização em `_optim_metadata` — `lr`, `batch_size`, `epochs_requested`,
`patience` e `optimizer`. **Não é `asdict(optim)` inteiro**: isso traria `augment` como
dicionário aninhado e `class_weights`/`seed` duplicados, e os três já têm nome próprio nos
metadados desde a S-27 e a S-40.

`optimizer` é gravado mesmo sendo fixo hoje. Um metadado ausente e um metadado que diz `adam`
são a mesma coisa **até** o dia em que o otimizador mudar — e aí o segundo continua verdadeiro
sobre os checkpoints antigos e o primeiro não diz nada sobre nenhum.

E `labels_hash`, com três decisões que têm teste cada: **ordenado** (a ordem das linhas muda a
cada reescrita do `LabelStore` e não é parte da resposta), **sensível a uma FEN corrigida** (o
caso que o `split_hash` não vê), e **só o split de treino** (`val`/`test` mudarem não altera o
que o modelo aprendeu; quem vigia os reservados é o `split_hash`).

Os testes moram em `tests/test_training.py` e não em `test_checkpoint.py`: é lá que estão o
`_tiny_dataset` e o `TrainingPlan` de que o critério de aceite precisa — dois treinos de
verdade que diferem só no `--lr`, com os metadados conferidos lado a lado.

---

## S-106 · `cvoff-experiment` não reatribui splits no meio da grade ✅ implementada (2026-08-17)

**Problema.** `cli/experiment.py:41` faz `splits = load_splits(args.splits)` **uma vez, antes**
da grade, e passa esse dicionário congelado a `run_variant`. Dentro dele, `experiments.py:115-128`
chama `train_model(splits_path=..., ...)` sem `assign_splits=False`, e o padrão é `True`
(`training.py:1049`).

Efeito: a **primeira** variante atribui split às amostras que estavam sem, reescrevendo o
`splits.csv`; as seguintes treinam sobre a partição nova; e a avaliação de todas usa o mapa
velho, carregado antes da grade. Com **357 amostras sem split** hoje, isto não é hipótese.

**Solução.** `run_variant` passa `assign_splits=False` — a grade lê e não escreve, que é
exatamente o caso de uso para o qual o parâmetro foi criado (`training.py:1066-1069`). E
`cli/experiment.py` recusa começar enquanto houver amostra sem split, com a mensagem mandando
rodar `cvoff-train` uma vez antes.

**Critério de aceite.** Uma grade de duas variantes não altera `splits.csv`; com amostra sem
split, o comando recusa e diz o que fazer.

**Testes.** `tests/test_experiments.py` — o `splits.csv` intacto depois da grade; a recusa com
amostra sem split.

### O que foi entregue

`run_variant` passa `assign_splits=False`, e `cvoff-experiment` recusa começar enquanto houver
amostra sem split — **antes** de começar, porque descobrir isso depois de sete treinos custa
horas. A mensagem manda rodar `cvoff-train --epochs 1` uma vez.

**Cinco testes num arquivo novo** (`tests/test_experiments.py` não existia), e três falham no
código anterior: o `splits.csv` intacto depois de uma variante, as duas variantes vendo a mesma
partição, e a recusa. Os outros dois são guardas — ler não escreve nem quando não há nada a
atribuir, e a guarda anterior (splits ausente) continua de pé com a mensagem dela.

---

## S-107 · O retreino de produção, e o candidato que espera desde 2026-08-11 ✅ medido (2026-08-16)

**Problema.** O modelo que `config.py:168` carrega foi treinado sobre **2.660** amostras em
2026-08-09 (`augment_version=aug0`, `git_commit=88daa9a`). O treino disponível hoje é ≈ **3.128**
— **468 amostras (+17,6%) de correção humana que o produto nunca viu**, das quais 697 rótulos
criados em agosto.

E `models/s40_mhsp_16ep.pt` está no disco desde 2026-08-11, medido como dominante em tudo que
era mensurável: **−40% de reparo do decodificador** (9 casas contra 15), validação 0,9820 contra
0,9790, mesmo custo. A promoção esperava um conjunto de campo com resolução.

**Solução.** Depois das Fases 14 e 15, e não antes:

```bash
cvoff-audit --strict                                                    # S-102
cvoff-train --fresh --seed 42 --model models/controle_20260816.pt
cvoff-train --fresh --seed 42 --augment mhsp --model models/mhsp_20260816.pt
cvoff-field --model models/controle_20260816.pt --json docs/metrics/controle_20260816.json
cvoff-field --model models/mhsp_20260816.pt --json docs/metrics/mhsp_20260816.json
```

Os dois sobre o mesmo dataset, semente e número de épocas — a regra do CONTRIBUTING, que existe
porque comparar contra `piece_classifier.pt` compararia também os meses de amostras que
entraram desde que ele foi treinado.

**A decisão do `AugmentConfig()` padrão sai desta medição**, e é a primeira vez que ela terá
régua capaz de julgá-la: com a exatidão de campo da S-96, "−40% de reparo" deixa de ser número
lateral e passa a ter uma taxa de acerto ao lado.

**Critério de aceite.** O modelo promovido cita `dataset_size ≥ 3.100`; a exatidão de campo
dele é igual ou melhor que a do controle, com `n` declarado; a decisão fica no ROADMAP
**inclusive se for "não promover"**.

**Testes.** Não é item de teste, é item de medição. O que a suíte trava é a S-102 e a S-105.

### O que foi medido

**A decisão é "não promover o `mhsp`", e ela está no [ROADMAP_FASE14](ROADMAP_FASE14.md) com a
tabela inteira.** Aqui fica o que a medição ensinou sobre a própria régua, que é o que
interessa às specs vizinhas:

**A régua não distingue os três modelos.** Exatidão de campo 1,0000 sobre os mesmos 28
diagramas para produção, controle e `mhsp`. O conjunto mede leitura desde a S-99, mas não tem
resolução para escolher entre modelos — que era exatamente a terceira ressalva daquele commit,
agora confirmada em vez de estimada. **A S-99 continua sendo o gargalo**, e agora com um alvo
nomeado: `GALLAGHER p80` é o único diagrama em que o controle e o `mhsp` divergem, e ele está
no conjunto **sem FEN de referência**.

**A armadilha da S-97 fechou, e o número não mudou de tamanho.** As duas páginas contaminadas
(`Karpov p80`, `Kemeri p187`) entraram no treino destes dois modelos — era a previsão literal
da S-97, e o único remédio disponível foi o que ela já implementava: publicar a taxa limpa ao
lado. A ordem entre controle e `mhsp` é a mesma nas duas taxas.

**A S-96 mostrou o modo de falha dela do lado do vencedor.** O diagrama que o controle exporta
a mais passa o gate com confiança acima de 0,80 e não tem referência: pela taxa de exportação
ele é um acerto, e ninguém sabe se é. É a demonstração de que "exportado" e "certo" continuam
sendo perguntas diferentes mesmo quando a resposta parece boa.

**A S-105 teria poupado uma inferência.** Os metadados dos dois checkpoints não trazem lr, lote
nem número de épocas; a única forma de saber que o candidato histórico `s40_mhsp_16ep.pt` rodou
**8** épocas e não 16 foi ler `metadata["metrics"]["total_epochs"]`, que existe por acaso. O
nome do arquivo dizia outra coisa.

**A S-102 não existia para barrar.** O `cvoff-audit --strict` da receita não rodou porque é a
S-102, ainda aberta; o `cvoff-audit` normal rodou e foi lido por gente. Ele acusa redundância
em 11,0% (teto da S-63 é 10%) e 3 triplas cruzando split (S-98) — dois avisos que, com a S-102
implementada, teriam interrompido o retreino em vez de virar uma linha de ressalva.

---

## S-108 · A pendência dos livros hachurados, com o número que a torna acionável

> **Não é achado novo.** O ROADMAP_FASE7 já lista *"anotar os livros hachurados"* como
> pendência desde 2026-08-11. A verificação derrubou o enquadramento de novidade; o que fica é
> o número, que muda **o que** anotar.

**O que a pendência dizia.** *"Os 8 diagramas barrados estão todos abaixo de 0,43 — falha de
domínio, não de margem"*, e o remédio proposto era anotar essas páginas **no conjunto de
campo** — ou seja, medir melhor.

**O número que muda o remédio.** `cvoff-field` de hoje, por livro: `Euwe, Kramer - Das
Mittelspiel Band 1-2` **0/2** e `GALLAGHER - Winning With the King's Gambit` **0/2**. Por
regime: `vetorial` 14/14 e `fonte` 6/6 contra `scan-puro` 6/15 e `scan-hachurado` 2/4.

Cruzando com o `labels.csv` — das 625 linhas com `source_pdf` preenchido: Secrets 258, Karpov 1
59, Yusupov 56, Kemeri 50, Aagaard 13, **Euwe 0, Gallagher 0**.

Os dois livros que exportam zero **não têm um único rótulo no dataset**. A hachura sintética da
S-40 (`augment.py:119`, `RandomHatch` por `sin`) foi construída como substituto de um domínio
que nunca foi coletado — e `augment.py:18` cita, no docstring, exatamente o `Euwe p25`.

**Solução.** Coletar ~40 tabuleiros de cada pelo caminho de seleção de área da S-20, que
funciona mesmo quando o detector falha. Depois, o experimento que fecha a S-40 de verdade:
`aug0` com os dados reais contra `mhsp` sem eles.

**A ressalva de método.** As amostras novas entram por `ensure_splits`, que sorteia — ~70% cai
em `train`, e algumas cairão em `val`/`test`. Isso é o desejável (o conjunto reservado também
precisa do domínio difícil), mas significa que **o ganho medido no `val` estará parcialmente
comprado**; quem julga é o conjunto de campo, e a S-99 precisa incluir páginas desses dois
livros que **não** tenham amostra rotulada.

**A hipótese é falsificável, e é o ponto.** Se 80 tabuleiros reais de domínio hachurado não
moverem a exportação desses dois livros, a conclusão é que o problema não é dado — e isso
também é resposta, e mais barata que a alternativa de mexer no modelo.

**Critério de aceite.** ≥ 40 amostras de cada livro com procedência; a taxa de exportação dos
dois medida antes e depois, sobre páginas de campo sem amostra rotulada.

**Testes.** Nenhum novo: é coleta e medição. As guardas são a S-97 e a S-98.

---

# Fase 16 — O trabalho humano não se perde

> São defeitos, não melhorias. Cada dia de uso acrescenta dado corrompido.

## S-109 · Sair de um campo sem digitar não apaga a procedência da base ✅ implementada (2026-08-16)

**Problema.** `ui/gallery_panel.py:253-254` liga `<FocusOut>` e `<Return>` de cada um dos oito
campos de header a `_on_header_event` → `_commit_header` (`:751-754`):

```python
def _commit_header(self, nome: str) -> None:
    self.model.set_header(nome, self.header_vars[nome].get())
    self._persist()
```

Sem comparar com o valor gravado. E `set_header` (`ui/gallery_model.py:333-335`) tira o campo
da procedência da base sempre que ele estava lá:

```python
restantes = tuple(campo for campo in anotacao.filled_fields if campo != f"header:{nome}")
if restantes != anotacao.filled_fields:
    return self.edit(headers=headers, **_provenance_after(anotacao, restantes))
```

A intenção está certa e escrita no comentário — *"editar este header o tira da procedência da
base"*. O defeito é que **`<FocusOut>` dispara sem edição**: percorrer os headers com `Tab`, que
é o gesto de **conferir** o que a base preencheu, rebaixa a procedência de `database` para
`manual` e reescreve o livro inteiro no disco.

A ironia está no docstring logo abaixo, na S-94: ele descreve o fluxo de limpar campo a campo
*"saindo de cada `Entry` para que o `<FocusOut>` grave"* — o mesmo gesto que dispara o defeito.

Hoje há **4.906 anotações com headers** e **4.901 com `filled_from`**; é esse número que o
gesto de conferir corrói.

**Solução.** Guarda de igualdade em `_commit_header`, `_commit_move`, `_commit_side` e
`_commit_link`: comparar com o valor já gravado e sair **antes** de `set_header`/`edit` e antes
de `_persist()`. Segunda linha de defesa no modelo, que é onde a regra pode ser testada sem
janela: `set_header` com valor idêntico ao gravado é no-op, inclusive na procedência.

**Critério de aceite.** `Tab` pelos oito campos de um diagrama preenchido pela base não muda
`filled_fields`, `filled_from` nem `filled_rule`, e não escreve no disco. Digitar de verdade
continua rebaixando, como a S-86 decidiu.

**Testes.** `tests/test_gallery_model.py` (sem Tk) — `set_header` com o mesmo valor preserva a
procedência inteira; com valor diferente, rebaixa só aquele campo.

### O que foi entregue

A guarda mora no **modelo**, e não só no painel: `gallery_model._apenas_o_que_mudou` filtra os
campos que de fato diferem antes de `edit` tocar em procedência, e `set_header` sai cedo quando
o dicionário de headers não mudou — precisa ser lá porque a linha seguinte já calcula a
procedência nova, e é ela, não o header, que `edit` veria como mudança.

No painel, `_persist_if_changed` evita a **escrita**: os quatro `_commit_*` disparam em
`<FocusOut>` e `<<ComboboxSelected>>`, e sem isso percorrer os oito headers reescrevia o arquivo
do livro inteiro oito vezes.

Sete testes travam a decisão, e **três deles falham no código anterior** — conferido
revertendo o módulo. O que continua valendo: digitar de verdade rebaixa o campo (S-86), apagar
um header rebaixa, e o último campo da base a sair leva `filled_from` e `filled_rule` junto
(S-94).

---

## S-110 · `cvoff-games --apply` não rebaixa uma escolha humana ✅ implementada (2026-08-16)

**Problema.** `ui/gallery_model.py:472` protege a escolha humana assim:

```python
if anterior.chosen_game and anterior.chosen_game != _candidate_key(casamento):
    relatorio.respected += 1
    ...
    continue
```

A guarda só dispara quando a escolha humana **difere** da candidata automática. Quando ela
**coincide** com `candidates[0]`, o fluxo segue e a linha 524 grava
`filled_rule=_fill_rule(casamento)` — trocando `human` pela regra automática (`date`, por
exemplo).

O efeito é o oposto do critério de aceite do plano da Fase 13: a coluna *"A REVISAR:
preenchidos por desempate"* que a S-89 produz e que deveria **cair** a cada sessão passa a
**subir** com o trabalho humano — o diagrama que uma pessoa resolveu volta para a fila.

**Solução.** Quando `anterior.chosen_game` existe e é **igual** a `_candidate_key(casamento)`,
preservar `filled_rule` e `filled_from` e contar em `ApplyReport.respected`. A confirmação da
leitura (`confirmed_from`) continua sendo atualizada — as 64 casas bateram, e isso é informação
nova.

A condição vira: *escolha humana existe* → respeitar, coincidindo ou não. É a leitura correta
de "a escolha humana já respondeu **por que** esta partida".

**Critério de aceite.** `--apply` sobre um diagrama com `chosen_game` igual à candidata
automática mantém `filled_rule="human"` e conta em `respected`; o censo da S-89 não o lista
como "a revisar".

**Testes.** `tests/test_gallery_model.py` — o caso coincidente (que hoje falha) e o divergente
(que já passa), lado a lado, com o docstring dizendo por que os dois são o mesmo caso.

### O que foi entregue

A condição virou `if anterior.chosen_game:` — sem a comparação de chaves. Com ela, o helper
`_candidate_key` ficou sem chamador e saiu: ele existia só para responder *"a pessoa discordou
do desempate?"*, e essa pergunta deixou de decidir alguma coisa.

Três casos travados lado a lado, e **só o do meio falha no código anterior** (conferido
revertendo o módulo):

| escolha humana vs. candidata automática | antes | agora |
|---|---|---|
| divergente | respeitada | respeitada |
| **coincidente** | **`filled_rule` regravado como `date`** | **respeitada** |
| casamento sem candidata nenhuma | respeitada, por acidente da chave vazia | respeitada, pela regra |

O terceiro entrou porque passava pelo motivo errado: a chave vazia diferia da escolhida, e o
teste guarda que a condição continua sendo *"escolha humana existe"* e não *"as chaves
diferem"*.

E `relatorio.respected` passou a **aparecer** na saída do `cvoff-games --apply`. O docstring
do campo já dizia que ele deveria — *"um número alto aqui numa varredura é sinal de que ela
está passando por cima de um livro já revisado à mão"* —, e até aqui metade do que ele deveria
contar era regravado como `date` em vez de contado.

O que continua valendo: `confirmed_from` é atualizado nos três casos, porque as 64 casas
bateram e isso é informação nova sobre a **leitura**, não sobre a partida.

---

## S-111 · A imagem que não gravou não vira linha no CSV ✅ implementada (2026-08-16)

**Problema.** `dataset.py:450` grava a amostra assim:

```python
cv2.imwrite(str(image_path), board_bgr)
```

`cv2.imwrite` devolve `bool` e o retorno é ignorado; a função devolve `image_path` como se
tivesse gravado, e em seguida (`dataset.py:452`) `LabelStore.append` grava a linha. O mesmo
padrão está em `review_queue.py:402`.

Disco cheio, pasta em rede, antivírus segurando o arquivo: a imagem não é gravada, a interface
diz que salvou, e o CSV ganha uma linha órfã. **O prejuízo é o trabalho humano daquela
correção** — e a auditoria de hoje já mostra o sintoma: *"Rótulos cujo PNG sumiu (1) —
descartados em silêncio no treino"*.

**Solução.** `if not cv2.imwrite(...): raise OSError(f"Não foi possível gravar {image_path}")`
nos dois pontos, antes de qualquer escrita no CSV. A ordem já é favorável — a imagem vem
primeiro —, então levantar ali deixa o CSV intacto, e quem chama mostra a falha em vez de um
"salvo" que não aconteceu.

**Critério de aceite.** Com a gravação da imagem falhando, nenhuma linha entra no `labels.csv`
e a interface diz que não salvou.

**Testes.** `tests/test_dataset.py` — `cv2.imwrite` forçado a `False` levanta e o CSV fica com
o mesmo número de linhas; idem para `review_queue`.

### O que foi entregue

`atomic_io.write_image` é a porta única: grava, confere o retorno e levanta `OSError` em
pt-BR nomeando o arquivo. Os dois pontos que ignoravam o retorno — `dataset.py:450` e
`review_queue.py:402` — passam por ela.

Ela mora no `atomic_io` por vizinhança de propósito, e o docstring diz o que ela **não** é:
escrita atômica. O nome do PNG é único por timestamp ou determinístico e reescrito inteiro,
então não há versão anterior a proteger — o que faltava era conferir a resposta.

Os dois testes falham no código anterior (conferido revertendo o módulo): sem a guarda, o CSV
ganhava a linha órfã e a interface dizia que tinha salvado.

---

## S-112 · As doze threads no registro do que se perde ✅ implementada (2026-08-16)

**Problema.** `grep threading.Thread` em `app_tkinter.py` e `ui/*.py` devolve **12**
ocorrências. `grep busy.register` devolve **2**: `ui/export_controller.py:172` e
`ui/training_dialog.py:135`.

Ficam de fora, entre outras, a varredura por posição da Galeria, a busca por nome, a varredura
da Galeria, a varredura da fila de revisão e o recarregamento do dataset. **A mais cara do
programa em tempo — a busca por posição, ~56 min medidos na Fase 13 — é uma das que não se
registram**: fechar a janela aos 50 minutos descarta a passada sem uma palavra.

A S-60 construiu o registro para que nenhuma operação longa morresse em silêncio e o cobriu
para as duas que existiam então. As que vieram depois entraram sem ele, e o
`ARCHITECTURE.md:212` continua dizendo "quatro operações longas".

**Solução.** Cada worker abre um `busy.register(...)` com `loses_work` honesto e `cancel=`
apontando para o `Event` que ele já tem:

| operação | `loses_work` | por quê |
|---|---|---|
| busca por posição | **sim** | a passada é descartada inteira |
| varredura da Galeria | não (depois da S-120) | passa a ter checkpoint |
| varredura da fila | não | guarda o parcial |
| busca por nome | não | é curta |
| recarga do dataset | não | é derivada |

**Critério de aceite.** Fechar a janela durante qualquer das 12 diz o que está rodando e o que
se perde; a busca por posição pede confirmação explícita.

**Testes.** Teste sem Tk que varre `ui/` e `app_tkinter.py` por `threading.Thread(` e exige que
o ponto de partida esteja num registro do `BusyRegistry` ou numa lista de exceções **declarada
e comentada** — no molde do `ARQUIVOS_DE_UI` de `tests/test_strings.py:23-28`. A lista
declarada é o ponto: um worker novo que não estiver nela falha a suíte.

### O que foi entregue

**Cinco registros novos, e os `loses_work` saíram da medição e não da intuição:**

| operação | `loses_work` | por quê |
|---|---|---|
| busca por posição | **sim** | o cache só é gravado depois da passada inteira — meia base lida dá contagens que não valem |
| varredura da Galeria | **sim**, por enquanto | `save_index` só acontece no fim, e fechar mata a thread `daemon` antes dela. **É a S-120 que troca este valor**, quando a varredura ganhar checkpoint |
| varredura da fila | não | os recortes vão para `data/review_cache/` página a página, por `write_image`: refazer relê o PDF, não re-renderiza os tabuleiros |
| busca por nome | não | ~150 s por gigabase, uma passada |
| detecção de duplicatas | não | derivada: o hash perceptual não grava nada |

A tabela do enunciado dizia *"varredura da Galeria: não (depois da S-120)"*, e a implementação
segue o "depois": hoje ela **perde**, e o comentário no ponto de registro nomeia o item que
inverte o valor. Publicar o que é em vez do que vai ser é a mesma regra da S-97.

**As cinco que ficaram de fora estão declaradas, não esquecidas.** `SEM_REGISTRO` em
`tests/test_busy.py` lista o OCR da página, o overlay de diagramas, os dois botões de leitura
de um tabuleiro (rede e local) e a análise do motor — cada uma com uma linha dizendo por quê.
O motivo comum: perguntar *"fechar mesmo assim?"* por causa de uma análise de dois segundos
treina o usuário a responder "sim" sem ler, e aí ele responde "sim" também para a busca por
posição, que custa 56 minutos.

**Onde o registro entra e sai.** As três operações da Galeria dividem thread, `Event` de
cancelamento e o mesmo `_busy(...)` que liga e desliga os botões — então o `release()` mora
lá, no único ponto por onde as seis saídas (`_scan_done`, `_scan_failed`, `_search_done`,
`_search_failed`, `_positions_done`, `_positions_cancelled`) já passavam. Seis cópias de um
`release()` seriam cinco chances de esquecer, e um registro que não sai faz a janela perguntar
para sempre sobre uma operação que acabou.

**`_Token` virou `BusyToken`.** Com sete pontos de registro em vez de dois, os
`_busy_token: object | None` mais `# type: ignore[attr-defined]` que os dois primeiros usavam
virariam sete cópias de um tipo apagado. Saíram os dois `type: ignore` que existiam.

**Quatro testes, e o primeiro falha no código anterior** listando exatamente as cinco threads
sem registro. Os outros três guardam o que a lista de exceções pode virar: nenhuma entrada
apontando para worker que não existe mais, motivo escrito em todas, e o aviso da busca por
posição pedindo confirmação com o nome da operação dentro.

---

## S-113 · O cache de posições com trava e refusão ✅ implementada (2026-08-16)

**Problema.** `ui/gallery_panel.py:515` lê o cache, a linha 546 varre (56 min medidos, 8.034
alvos) e a 554 grava `save_cache(cache)` **com o objeto lido lá atrás**. `cli/games.py` faz o
mesmo. Não há trava nem releitura.

O fluxo que o próprio README sugere — deixar `cvoff-games --all` rodando enquanto se anota um
livro na Galeria — **perde uma das duas passadas**, sem erro, sem log e sem nada na tela: a
segunda a terminar sobrescreve a primeira.

**Solução.** `save_cache` relê o arquivo do disco imediatamente antes de gravar e funde as
posições. A fusão é trivial e segura: a chave é a colocação, e duas respostas da mesma base
nunca se contradizem — o fingerprint já garante isso. Serve também ao caso de um travamento no
meio.

**E o fingerprint precisa de uma regra só.** `games_cache.py:78` grava `int(st_mtime)` no
fingerprint enquanto `games_index.py:99` usa só `f"{nome}:{tamanho}"`. Um `mtime` diferente com
o mesmo conteúdo — uma cópia de arquivo, um sync de nuvem, um antivírus — descarta 56 minutos
de varredura. Adotar nome e tamanho nos dois lugares, ou manter o `mtime` e fazer `_descreve`
imprimi-lo, para que a mensagem diga o que de fato mudou.

**Critério de aceite.** Duas gravações concorrentes preservam as posições das duas; tocar o
`mtime` de um `.pgn` intacto não invalida o cache.

**Testes.** `tests/test_games_cache.py` — a refusão com um arquivo alterado por baixo; o
fingerprint estável sob `os.utime`.

### O que foi entregue

**A refusão é onde mora a correção, e a trava é conveniência.** `save_cache` relê o disco,
traz o que ele tem e o objeto em memória não, e só então grava. Fundir é idempotente e
comutativo — a chave é a colocação, e duas respostas da mesma base não se contradizem —, então
dois processos que gravem fora de ordem chegam ao mesmo arquivo. É por isso que a trava pode
desistir: ela estreita a janela entre reler e substituir, e nunca bloqueia.

**A trava desiste por idade, e não por PID.** Um `.lock` mais velho que os 10 s de
`LOCK_TIMEOUT` é lixo de um processo morto; mantê-lo faria toda gravação seguinte pagar a
espera inteira, e insistir travaria uma varredura de meia hora atrás de um arquivo vazio.
Sistema sem `O_EXCL` cai no mesmo caminho de "grava sem trava".

**`count == 0` sobrevive à fusão**, e tem teste próprio: perder um *"a base não conhece esta
posição"* devolve aquela posição ao alvo de toda varredura futura — que é justamente o custo
que o cache existe para não pagar duas vezes.

**Marca diferente no disco não é conflito, é outra base.** Nesse caso nada dela entra, e a
gravação avisa. Fundir contagens de duas bases inventaria procedência, que é o que a S-74
proíbe.

**O `mtime` saiu do fingerprint**, e a regra passou a ser a do `index_fingerprint`: nome e
tamanho. Havia duas regras para a mesma pergunta — *"é a mesma base?"* — e a mais estrita
descartava o trabalho: uma cópia de pasta, um sync de nuvem ou um antivírus mudam o carimbo
sem tocar num byte, e isso jogava fora **56 minutos**.

**E os caches que já estão no disco continuam valendo.** `_same_database` compara nome e
tamanho campo a campo em vez de `==` sobre o dicionário; sem isso, a primeira execução depois
deste item descartaria exatamente as varreduras que ele existe para deixar de perder. Tem
teste, com a marca antiga (com `mtime`) escrita à mão.

**Nove testes, seis dos quais falham no código anterior** (conferido revertendo o módulo). Os
três que passam nos dois são guardas: que a gravação não deixa `.lock` para trás, que o
tamanho **continua** descartando o cache de outra base, e que a marca do cache e a do índice
extraem os mesmos pares `(nome, tamanho)`.

---

## S-114 · "Salvar todos" avisa quem precisa saber ✅ implementada (2026-08-16)

**Problema.** `ui/result_panel.py:866-921` (`save_all`) chama `_save_one` por diagrama e
termina em `_on_status` + `messagebox.showinfo`. Não chama `self._on_sample_saved()` nem
`self._settle(alvo)` — os dois só aparecem em `save_current` (`:830`) e `_rewrite_dataset_row`
(`:856`).

`Ctrl+Shift+S` é o caminho barato de uma página inteira — uma pergunta de ilegalidade em vez de
N, um modal em vez de N. Quem o usa perde exatamente o sinal que a S-71 construiu para
responder *"onde eu parei neste livro?"*: as caixas verdes de "já salvo" não aparecem, e o
item da fila de revisão não fecha.

**Solução.** Em `save_all`, chamar `self._settle(alvo)` dentro do laço para os alvos com
`settle_position`, e `self._on_sample_saved()` **uma vez ao fim**, quando `salvos > 0` — uma
vez só, e não por diagrama, senão o custo da S-116 se multiplica por N.

**Critério de aceite.** `save_all` com 4 diagramas produz 1 notificação de dataset e fecha os
itens de fila correspondentes; as marcas verdes aparecem sem trocar de página.

**Testes.** `tests/test_result_panel.py` — contador no lugar de `on_sample_saved=lambda: None`,
com asserção de exatamente 1 chamada depois de `save_all` (hoje 0); teste irmão para o vínculo
`REVIEW`.

### O que foi entregue

Duas chamadas, em dois lugares diferentes de propósito:

- **`self._settle(alvo)` dentro do laço**, porque fechar item de fila é por item. O vínculo
  `REVIEW` carrega um diagrama só (`open_review_item` faz `load([diagrama], ...)`), então na
  prática é um; o laço é o lugar certo mesmo assim, porque é onde a informação "este alvo
  salvou" existe.
- **`self._on_sample_saved()` uma vez ao fim, e só quando `salvos > 0`.** O aviso relê o
  `labels.csv` inteiro na thread da janela — é o custo que a S-116 vai atacar —, e chamá-lo por
  diagrama multiplicaria por N justamente o travamento que o "salvar todos" existe para
  evitar. É o mesmo raciocínio da pergunta única de ilegalidade, dez linhas acima. Zero salvos
  não avisa: mandar a aba Dataset reler 3.935 linhas para descobrir que nada mudou é o defeito
  ao contrário.

**Quatro testes, e os dois que importam falham no código anterior** (conferido revertendo o
módulo): quatro diagramas produzem **um** aviso (hoje zero) e o `Ctrl+Shift+S` sobre um item
da fila o fecha (hoje não fecha). Os outros dois são guardas contra trocar um defeito por
outro: nada salvo não avisa, e `save_current` continua avisando uma vez.

O contador no lugar do `on_sample_saved=lambda: None` é o que torna o item visível: a chamada
que faltava não deixa rastro no serviço nem na tela, e por isso sobreviveu à suíte inteira.

---

## S-115 · A galeria entra no que o projeto preserva ✅ implementada (2026-08-16) — opção 2

**Problema.** `data/gallery/` tem **5.953 anotações** em 7 livros: 4.906 com headers, 4.902 com
lado a jogar, 5.750 com `confirmed_from` e **21 com `chosen_game`**, que é escolha humana
explícita da S-86. São 11 MB de texto.

`.gitignore:38` o ignora, `git ls-files data/gallery` devolve 0, e a tabela "Formatos e
persistência" do `ARCHITECTURE.md` não o menciona.

O projeto versiona o `labels.csv` com justificativa escrita — *"é texto, e é a verdade do
projeto"* — e o `field_set.jsonl` pelo mesmo motivo. **A galeria é a mesma categoria de coisa e
está fora**, sem backup e sem menção.

**Solução.** A decisão é do dono do projeto, e a spec fixa as opções e o que cada uma custa:

| opção | custo | o que protege |
|---|---|---|
| **versionar `data/gallery/*.json`** | ~11 MB de texto no repositório, crescendo com o acervo | tudo, com histórico por commit |
| versionar só o que é humano | ~1 MB: um `gallery_human.jsonl` com as linhas de `chosen_game` e headers digitados | a parte irrecuperável; o resto se refaz varrendo |
| não versionar, mas documentar | zero | nada — só deixa de ser surpresa |

**A recomendação é a segunda.** O que a base preencheu se refaz com `cvoff-games --apply` a
partir do cache; o que uma pessoa digitou ou escolheu não se refaz de jeito nenhum. Separar as
duas é a mesma distinção que o `filled_rule` já grava.

**Critério de aceite.** `data/gallery/` aparece na tabela de persistência do `ARCHITECTURE.md`
com o destino decidido; se a opção for a segunda, existe o comando que extrai e o que restaura.

**Testes.** `tests/test_gallery.py` — a ida e volta do extrato humano, se ele existir.

### O que foi entregue — a opção 2

`cvoff-gallery`, com três modos: `--census` conta sem gravar, `--export-human` extrai e
`--import-human` restaura. **`data/gallery_human.jsonl` está versionado; `data/gallery/`
continua fora**, e agora os três aparecem na tabela de persistência do `ARCHITECTURE.md` com o
motivo de cada destino.

| | |
|---|---|
| `data/gallery/` | 13 MB, 7 livros |
| extrato humano | **214 KB**, 1.746 diagramas |
| partidas escolhidas a mão (S-86) | **21** |
| vez a jogar declarada | 17 |
| número do lance | 248 |
| campos de header | 1.694 |

**O crivo é o `filled_fields`, que já respondia a pergunta campo a campo** — e por isso o item
não inventou classificação nenhuma: o que a base preencheu está listado lá, e volta com
`cvoff-games --apply` a partir do cache; o que não está foi digitado.

**Duas exceções ao crivo, e as duas mudam o resultado:**

- **`filled_rule == "human"` inverte o crivo.** Ali o `filled_fields` lista o que a *escolha da
  pessoa* pôs (ver `choose_game`): ela olhou a lista de candidatas e disse qual era. Tratá-los
  como "da base" jogaria fora exatamente as 21 decisões mais caras do acervo.
- **`filled_from` cheio com `filled_fields` vazio não declara nada.** É a anotação anterior à
  correção de procedência da S-72 — a mesma que `_recover_provenance` repara. Nela tudo
  *parece* humano, e chamar isso de humano encheria o extrato de headers da base; pior, o
  `--import-human` os reescreveria como digitados, que é a procedência inventada que a S-94
  existe para impedir. **A primeira versão deste item tinha esse defeito**, e o extrato saía
  com headers de partida completos vindos da base. O número de anotações nessa situação é
  contado e **publicado** pelo `--census`: sem ele, um extrato pequeno pareceria "há pouco
  trabalho humano" quando é "há trabalho que não dá para separar".

**Na restauração, o que vem do extrato vence** — e sai do `filled_fields`, com `filled_from` e
`filled_rule` caindo junto quando não sobra campo da base. É a regra da S-17 (quem está com o
livro na mão é a pessoa) e a mesma aritmética do `_provenance_after` da tela. O que a base
preencheu e ninguém contradisse continua lá, e o `confirmed_from` também: ele é afirmação sobre
a **leitura**, não sobre quem preencheu.

**Onze testes**, entre eles a ida e volta com a galeria apagada no meio, a restauração por
cima de uma galeria revarrida, e a ordenação do arquivo — que existe porque um arquivo
versionado cuja ordem muda a cada execução produz um diff ilegível a cada commit.

**Um passo de ambiente:** o `cvoff-gallery` é entrada nova no `pyproject.toml`, então o
executável só aparece depois de um `uv sync`. Antes disso ele roda por
`python -m chess_diagram_ocr.cli.gallery`.

---

# Fase 17 — O laço interno, e o custo de abrir um livro

## S-116 · `Ctrl+S` deixa de reler o `labels.csv` inteiro ✅ implementada (2026-08-16) — corte 1 de 2

**Problema.** `ui/result_panel.py:830` chama `_on_sample_saved()` → `app_tkinter.py:1142-1147`
`_reload_dataset_panel` → `dataset_panel.reload()` (`ui/dataset_panel.py:161-172`) →
`load_rows` do arquivo inteiro, **na thread do Tk, mesmo com a aba Dataset nunca aberta**.

Medido nesta máquina sobre o `labels.csv` atual (3.936 linhas): ~0,7 a 0,9 s por gravação, mais
um modal de sucesso que pede uma tecla. É o laço mais interno do projeto — corrigir → `Ctrl+S`
→ seta → corrigir — e ele custa, por amostra, quase um segundo de janela travada. Numa página
de 4 diagramas são ~3,5 s de espera para gravar o que já estava pronto.

O custo cresce com o `labels.csv`, que é o arquivo que o projeto existe para fazer crescer.

**Solução.** Dois cortes independentes:

1. **A recarga vira preguiçosa.** A aba Dataset recarrega no `<<NotebookTabChanged>>`; o
   `_on_sample_saved` só marca `invalidate()`. Quem nunca abre a aba nunca paga.
2. **O visualizador atualiza `saved_diagrams` pela amostra recém-gravada**, em vez de relendo o
   arquivo para descobrir o que ele mesmo acabou de escrever.

E o modal de sucesso do caminho de um diagrama vira mensagem na barra de status — a informação
é a mesma e não custa uma tecla. O modal de erro fica.

**Critério de aceite.** De `save_current()` até a janela responder: hoje ~0,8 s, alvo **< 0,05
s** com o `labels.csv` atual. Nenhuma tecla para continuar no caminho de sucesso.

**Testes.** Teste sem Tk que instrumenta `load_rows` e afirma **zero** chamadas depois de uma
gravação com a aba Dataset fechada, e uma quando ela é aberta.

### O que foi entregue

**A medição primeiro, e ela decidiu o escopo.** Os três custos de um `Ctrl+S`, cronometrados
nesta máquina sobre o `labels.csv` de 3.936 linhas:

```
    load_rows (aba Dataset) .......   688.7 ms
    LabelStore.read() .............    29.2 ms
    saved_diagrams_by_page ........     0.2 ms
    TOTAL por Ctrl+S ..............   718.1 ms
```

**96% do custo é um só dos dois cortes.** Feito o corte 1, o mesmo caminho custa **46,1 ms**
(`LabelStore.read()` 30,9 + `load_annotations` do livro 15,0 + `saved_diagrams_by_page` 0,2) —
dentro do alvo de < 50 ms, com uma margem que é honesto chamar de estreita.

**A preguiça mora no painel, e não em quem avisa.** `DatasetPanel.reload()` marca `_stale` e
sai quando `winfo_ismapped()` é falso; o `<Map>` que o `ttk.Notebook` dispara ao trocar de aba
recarrega **uma** vez, por mais gravações que tenham acontecido escondidas. Isso dispensou
mexer no `<<NotebookTabChanged>>` da janela: quem grava uma amostra não tem como saber se
aquela aba está visível, e não deveria — espalhar `if aba_visivel` pelos chamadores poria a
mesma decisão em cinco lugares.

**E o modal de sucesso do `save_current` saiu.** Ele dizia o que a barra de status já diz e
cobrava uma tecla por amostra no laço mais interno do projeto. A confirmação visual continua,
e é a melhor delas: a caixa do diagrama fica verde na hora (S-71). **O modal de erro fica** —
ali a informação não é redundante e a interrupção é o ponto.

### O que **não** foi feito: o corte 2, e ele vale ~31 ms dos 46

`_reload_saved_diagrams` continua relendo o `labels.csv` inteiro para descobrir o que a janela
acabou de escrever. Fazê-lo incrementalmente exige que a `(página, diagrama)` gravada atravesse
o `on_sample_saved`, que hoje não recebe argumento nenhum — é mudança na fronteira entre o
`result_panel` e o `app_tkinter`, e o alvo do critério de aceite já está cumprido sem ela.

Fica registrado com o número para que a decisão de fazê-la seja tomada por ele: **30,9 ms de
`LabelStore.read()` mais 15,0 ms de `load_annotations`**, e o primeiro cresce com o arquivo.

### Uma armadilha de suíte que este item encontrou

O módulo de teste novo roda cedo na ordem alfabética, e a primeira versão dele guardava a raiz
Tk num global de módulo — como fazem o `test_result_panel` e o `test_pdf_panel`. Resultado:
**47 testes falharam** em `test_gallery_panel`, `test_pdf_panel` e `test_result_panel`, com
`image "pyimage1" doesn't exist` e `Can't find a usable tk.tcl`, apontando para os módulos
errados. Uma raiz que sobrevive ao módulo fica viva enquanto os seguintes criam e destroem as
deles, e nesta máquina isso quebra o Tcl.

O molde que funciona é o do `test_gallery_panel`: criar em `setUpClass` e **destruir** em
`tearDownClass`. Fica escrito no docstring da classe, com os sintomas, porque é o tipo de coisa
que o próximo a acrescentar um teste de janela vai reencontrar.

---

## S-117 · A seta não executa dois painéis ao mesmo tempo

**Problema.** `ui/study_panel.py:135-138` liga `<Left>`/`<Right>` no canvas do tabuleiro de
estudo a `undo_move`/`redo_move`, que devolvem `None` (`:340-346`). `app_tkinter.py:1175-1176`
liga as mesmas teclas via `bind_shortcuts` → `root.bind_all` (`ui/shortcuts.py:47-50`), e a
guarda de `ui/shortcuts.py:26` não cede para um widget que já declarou binding próprio.

Como o handler do canvas não devolve `"break"`, os dois disparam: **analisar uma posição com as
setas na aba Análise move, invisivelmente, o cursor do editor em outra aba.** O que `Ctrl+S`
gravaria depois deixou de ser o diagrama que a pessoa acha que está selecionado.

**Solução.** A guarda passa a perguntar duas coisas: além de `ignores_widget`, uma
`owns_key(widget, seq)` que cede quando o widget com foco já declarou binding próprio para
aquela sequência (`widget.bind(seq)` devolve string não vazia). É a regra geral, e vale para os
atalhos que vierem depois.

Alternativa mais barata e menos geral: `undo_move`/`redo_move` devolverem `"break"`. Resolve
este caso e não o próximo.

**Critério de aceite.** Com o foco no tabuleiro de estudo, `<Left>` dispara **um** handler; com
o foco fora dele, dispara o do editor.

**Testes.** Tk real: `bind_shortcuts` mais um canvas com binding próprio, `event_generate
('<Left>')`, asserção de que a lista de handlers disparados tem 1 elemento (hoje 2).

---

## S-118 · O DatasetPanel não perde a página e a seleção ✅ implementada (2026-08-17) — item 1 de 2

**Problema.** `ui/dataset_panel.py:62-63` justifica a paginação com *"3.195 linhas de uma vez
travam o `Treeview` do Tk"*, e o `ARCHITECTURE.md:143-145` repete a premissa. Medido com
`Treeview` real nesta máquina, mesmas 8 colunas: inserir 3.936 linhas custa **~0,03 s**. O que
custa é o `load_rows` que a antecede (S-116), não a inserção.

E a paginação cobra o que não mitiga: o laço de conferir rótulos — abrir no editor, corrigir,
`Ctrl+S`, voltar — **perde o lugar a cada iteração**. A linha corrigida estava na página 15 e a
tabela volta para a 1.

**Solução.** Duas mudanças pequenas, ambas dentro do Tk:

1. `reload()` preserva a página e a seleção: guardar `self._page` e os `filename`
   selecionados antes de recarregar, restaurá-los depois de `apply_filters()`, limitando à
   faixa nova.
2. Com o custo de inserção medido em 0,03 s, a paginação deixa de ser necessária para o
   tamanho atual — mas **isso é uma segunda decisão**, e ela precisa da medição refeita quando
   o `labels.csv` dobrar. O que este item entrega é o item 1; o 2 fica registrado com o número
   ao lado, para que a decisão seja tomada com dado e não com a premissa de 2026-07.

**Critério de aceite.** Corrigir uma linha da página 12 devolve a tabela à página 12, com a
linha selecionada.

**Testes.** Teste sem Tk do modelo de paginação: ir para a página 12, remover uma linha, a
página resultante continua 12 (hoje volta a 0).

### O que foi entregue: o item 1. O item 2 fica com o número ao lado.

`apply_filters(keep_position=...)` separa as duas situações: trocar um filtro é pedir outra
lista, e ali voltar à primeira página é o certo; **salvar uma amostra não é** — a lista é a
mesma. Só o `reload()` preserva.

A aritmética mora em `dataset_browser.page_after_change`, e não no painel, porque é aritmética
e se testa sem abrir janela. Ela trata a borda que acontece: remover a última linha da última
página faz a página pedida deixar de existir, e cair para a **última que existe** — não para a
primeira, que perderia o lugar tanto quanto o defeito original.

A seleção volta **por `filename`, não por índice**: a linha corrigida pode ter mudado de
posição no filtro, e um índice apontaria para a vizinha dela. Só o que está na página desenhada
— perseguir uma linha que saiu dela mudando de página seria adivinhar.

**O item 2 foi medido e não foi feito.** A premissa da paginação — *"3.195 linhas de uma vez
travam o `Treeview` do Tk"* — é falsa: com `Treeview` real e as mesmas 8 colunas, **inserir
3.936 linhas custa 53 ms** e limpar custa 6 ms. (A spec estimava ~30 ms; o número aqui é o
medido nesta máquina.) O que custava eram os 689 ms do `load_rows`, que é a S-116.

A paginação fica assim mesmo, e o motivo está no docstring do `PAGE_SIZE`: 53 ms é o número de
**hoje**, com 3.936 linhas, e o `labels.csv` é o arquivo que o projeto existe para fazer
crescer. Remover a paginação precisa da medição refeita quando ele dobrar — não da premissa de
2026-07 nem desta. O `ARCHITECTURE.md`, que repetia a premissa antiga, passou a citar o
número.

---

## S-119 · Uma varredura por livro em vez de duas

**Problema.** `gallery_scan.py:203-245` (`build_gallery_index`) e `review_queue.py:464-503`
(`build_review_queue`) percorrem o **mesmo** `iter_pdf_diagrams`, com os mesmos parâmetros, e
gravam em arquivos diferentes. Nenhum consome o resultado do outro, e a pessoa precisa saber
apertar os dois botões.

Medido nesta máquina no `PDF/1000 Chess Problems` (420 páginas): **338 s + 299 s**. Abrir um
livro novo custa ~5 min antes de qualquer trabalho humano, e mais ~5 min quando se descobre que
a outra aba também precisa da própria varredura.

É isso que separa "anotar mais 45 páginas de campo" de "anotar mais 45 páginas de campo depois
de 10 minutos de varredura por livro" — e é uma das razões de **27 dos 34 livros** não terem
sido abertos.

**Solução.** Uma varredura por livro. `build_gallery_index` já produz o superconjunto (todos os
diagramas, sem gate); `build_review_queue` passa a aceitar um `GalleryIndex` pronto e derivar a
fila dele, em vez de reabrir o PDF. Na tela vira um botão "Varrer livro" só, e as duas abas
consomem o mesmo artefato.

**Critério de aceite.** As duas varreduras do mesmo livro custam o que hoje custa a maior:
alvo ~338 s no livro de 420 páginas contra os 637 s de hoje. A fila derivada do índice tem os
mesmos itens, na mesma ordem, que a fila varrida direto.

**Testes.** `tests/test_review_queue.py` — a equivalência entre a fila derivada e a varrida,
sem janela.

---

## S-120 · A varredura da Galeria é retomável e diz até onde foi ✅ implementada (2026-08-17)

**Problema.** `gallery_scan.py:228-272` acumula tudo numa lista em memória e só devolve no fim;
`ui/gallery_panel.py:378-388` chama `build_gallery_index` sem `start_page` e grava com o
resultado inteiro. Uma queda ou um fechamento de janela perde a varredura do livro (6 min no
`1001`, ~14 min no Yusupov; ~3,5 h para revarrer os 34 PDFs).

**Pior que o tempo:** o índice truncado é indistinguível de um índice completo. Ele alimenta em
silêncio a busca por posição, o censo e a fila — todos concluindo que o livro tem menos
diagramas do que tem.

**Solução.** Duas camadas, e a primeira sozinha já resolve o pior:

1. `GalleryIndex` grava a faixa efetivamente varrida: `start_page`, `last_page_done`,
   `complete`. Três campos, e é o mínimo que torna o artefato auditável — quem consome sabe se
   está lendo um livro inteiro.
2. Reusar `CheckpointWriter`/`load_partial` (que a S-24 já construiu para a exportação) em
   `build_gallery_index`, com o mesmo desenho: grava parcial, retoma de onde parou.

**Critério de aceite.** Cancelar no meio grava um índice com `complete=False` e
`last_page_done` correto; a Galeria diz na tela que o livro está parcial; retomar continua de
onde parou.

**Testes.** `tests/test_gallery_scan.py` (não existe hoje) — os três campos; a retomada; o
consumidor que recusa concluir sobre índice parcial.

### O que foi entregue

**A camada 1 inteira, e a 2 por um caminho mais barato que o `CheckpointWriter`.** Os três
campos — `start_page`, `last_page_done`, `complete` — tornam o artefato auditável; e como o
índice **já é gravado no fim de cada varredura**, retomar não precisou de um formato parcial
novo: `build_gallery_index(resume_from=...)` recebe o índice do disco, mantém as entradas dele
e começa na página seguinte à última terminada.

**`last_page_done` sai do progresso, e não das entradas.** O progresso é emitido depois de a
página inteira ser lida, e é o único que enxerga página **sem diagrama nenhum** — que não
produz entrada e mesmo assim foi varrida. Tirá-lo das entradas faria a retomada reler todas as
páginas de prosa do fim do capítulo.

**Duas recusas de retomada, cada uma com teste:** índice completo (não há o que continuar, e
reaproveitar as entradas duplicaria o livro) e ordem de leitura diferente (a numeração de
diagrama por página depende dela, S-14, e as entradas antigas descreveriam outros diagramas —
o índice sairia *mentindo* em vez de incompleto).

**`end_page` também produz índice incompleto.** Truncar de propósito trunca do mesmo jeito, e
quem consome precisa saber disso tanto quanto no caso do cancelamento.

**Índice gravado antes deste item lê como completo.** É a decisão que evita gritar lobo: ele é
tão confiável quanto era ontem, e marcar os 34 livros do acervo como parciais de uma vez faria
o aviso deixar de significar alguma coisa.

**E isto inverte o `loses_work` que a S-112 deixou marcado.** O comentário lá nomeava este
item como o que trocaria o valor; a varredura da Galeria passou a `loses_work=False`, porque
fechar a janela custa **a página em curso** e não o livro.

**Dez testes num arquivo novo**, sem abrir PDF: o gerador de diagramas entra como duplo com a
mesma assinatura de `iter_pdf_diagrams`, inclusive o progresso por página, que é o que torna
`last_page_done` confiável.

---

## S-121 · O acervo varrido sem janela aberta

**Problema.** 34 PDFs, **17.823 páginas**, e o estado do acervo hoje: **5** livros com PGN, **7**
com índice de Galeria, **27 sem nada**. A fila de revisão é de 2026-08-09 e cobre um livro.

Varrer é operação de primeiro plano, com janela aberta, e depois da S-119 ainda são ~3,5 h para
o acervo. Ninguém deixa uma janela Tk aberta por 3,5 h.

**Solução.** `cvoff-scan --all`, no molde do `cvoff-games --all` que a Fase 13 já provou: um
comando de linha que varre o acervo inteiro, grava índice de Galeria e fila de revisão por
livro, é retomável (S-120) e imprime um relatório consolidado ao fim.

**Não é interface nova.** É o mesmo `build_gallery_index` chamado de fora da janela, que é onde
uma operação de horas pertence — a mesma decisão que a S-73 tomou para os 104 minutos da busca
por posição: *"104 minutos atrás de um botão é uma janela travada que ninguém entende"*.

**Critério de aceite.** `cvoff-scan --all` numa noite deixa os 34 livros com índice; rodar de
novo varre só o que falta; o relatório diz quantos diagramas por livro e quanto custou.

**Testes.** `tests/test_gallery_scan.py` — o comando sobre dois PDFs sintéticos; a segunda
execução não revarre o que já está completo.

---

## S-122 · O OCR ligado por padrão

**Problema.** `settings.py:162` define `ocr.enabled: bool = False`, e o `data/settings.json`
desta máquina confirma. A medição da S-43 diz o custo: com RapidOCR instalado, a procedência
`default` do lado a jogar cai de **87,8% para 77,2%**.

O motor está no `pyproject.toml`, os modelos vêm no wheel (14,2 MiB, nada baixado na primeira
execução — verificado na Fase 8), a medição está no `ARCHITECTURE.md`, e ele está **desligado**.
Toda exportação feita hoje carimba `[SideToMoveSource] default` em ~88% dos diagramas quando
poderia carimbar em 77%.

**Solução.** O padrão passa a ser "ligado **se o motor estiver instalado**" —
`build_recognizer` já devolve `None` quando o extra falta (S-42), então a degradação é a que já
existe. Quem não tem o extra não paga nada e não vê diferença; quem tem, deixa de precisar
descobrir uma preferência para receber uma melhoria já medida.

**A ressalva honesta, e o motivo de isto não ser trivial.** O custo por diagrama sobe: o motor
só roda onde a camada de texto calou (a precedência da S-43 garante isso), mas nos 7 livros sem
camada ele roda em todos. O número precisa ser medido nesta máquina antes de virar padrão, e
`cvoff-field --ocr rapidocr` contra `--ocr off` é a medição — que a Fase 14 torna comparável.

**Critério de aceite.** Instalação nova com o extra presente lê legenda sem que ninguém mexa em
preferência; sem o extra, nada muda; o custo por diagrama medido antes e depois está no
ROADMAP.

**Testes.** `tests/test_settings.py` — o padrão depende da disponibilidade do motor; a
preferência explícita do usuário vence o padrão nos dois sentidos.

---

## S-138 · A varredura por posição devolve a mesma resposta em qualquer número de processos ✅ implementada (2026-08-17)

**Problema.** Dois defeitos com a mesma raiz — a ordenação acontece **depois** do corte e
**fora** de um dos caminhos.

1. **`--workers 1` nunca ordena.** `games_db.py:714-721` devolve `total` no caminho
   sequencial; o `total.sort()` só existe na linha **755**, depois do bloco do `mp.Pool`.
   Medido com uma base de duas partidas (2020 e 1950) que compartilham uma posição: em
   paralelo a primeira candidata é a de 1950, sequencialmente é a de 2020. A garantia de
   determinismo que o docstring de `PositionIndex.sort` declara — e que existe porque corrigiu
   um defeito real da S-73 — **não vale no caminho documentado como `--workers 1 = sem
   paralelismo`**, que é justamente o de depuração.

2. **O teto de 32 corta por ordem de chegada.** `merge` (`games_db.py:532-538`) corta em
   `max_hits` na chegada de **cada pedaço**, a linha 746 consome `pendentes.next()` de um
   `imap_unordered` — cuja ordem de chegada não é definida — e `total.sort()` roda depois,
   sobre o que sobreviveu. Para as posições com mais de 32 candidatas, **duas varreduras da
   mesma base sobre o mesmo alvo devolvem conjuntos diferentes**, e a lista da S-86 muda de
   conteúdo entre execuções sem que nada tenha mudado.

A primeira candidata é a que vira o preenchimento automático. Isso significa que **qual partida
preenche um diagrama depende de quantos processos a varredura usou**.

**Solução.**

1. Mover `total.sort()` para o ponto único de saída de `scan_by_positions`, antes dos dois
   `return` — ou ordenar dentro de `PositionIndex.merge`, que é onde a invariante pertence.
2. `merge` guarda **as 32 mais antigas do conjunto**, e não as 32 primeiras a chegar: ordenar
   antes de cortar. É mais trabalho por pedaço e é o que torna o teto determinístico.

**Critério de aceite.** A mesma base e o mesmo alvo devolvem candidatas idênticas, dígito a
dígito, com 1 e com N processos — inclusive nas posições que estouram o teto.

**Testes.** `tests/test_games_db.py` — a equivalência 1×N incluindo a **ordem** (o teste atual
compara contagem); uma posição com mais de 32 candidatas, com os pedaços chegando fora de
ordem.

### O que foi entregue

**Os dois defeitos foram consertados no mesmo lugar: dentro do `merge`.** O enunciado dava
duas opções para o primeiro (mover o `sort` para o ponto de saída, ou ordenar no `merge`), e a
segunda resolve os dois de uma vez — porque é lá que a invariante pertence. Um `PositionIndex`
que passou por `merge` está ordenado e cortado pelas **32 mais antigas do conjunto**, não pelas
32 primeiras a chegar, e os caminhos sequencial e paralelo passam ambos por ele.

A chave de ordenação virou `_hit_order`, função de topo, porque `sort` e `merge` têm de usar a
**mesma**: duas cópias divergiriam na primeira correção, e o sintoma seria um teto que corta
candidatas diferentes das que a lista mostra.

**O `total.sort()` do caminho sequencial ficou**, redundante e barato: a invariante *"quem sai
daqui está ordenado"* não pode depender de o próximo leitor saber que o `merge` já ordenou.

**Quatro testes, e os quatro falham no código anterior.** Um deles é a demonstração do teto:
dois pedaços de 10 candidatas cada, um de datas 2000-2009 e outro de 1900-1909, com
`max_hits=5` — antes ficavam as cinco que chegaram primeiro, agora ficam as cinco mais
antigas, em qualquer ordem de chegada.

E um confirma o que **não** muda: a contagem não é cortada pelo teto. A lista serve para
preencher, a contagem para decidir se preencher é honesto (S-74).

---

## S-139 · A consulta por nome alcança as duas cores, e paga o porteiro ✅ implementada (2026-08-17)

**Problema.** Dois defeitos independentes no mesmo caminho, o da janela de candidatas.

1. **O `LIMIT` é compartilhado pelas duas cores.** `games_index.py:278-283`:

   ```sql
   SELECT offset, file FROM games WHERE pair IN (?,?) LIMIT ?
   ```

   Um único `limit=40` para os dois hashes. Medido no índice real (20.902.904 partidas),
   Karpov×Kasparov tem 245 partidas com um hash e outras tantas com o outro: a cota se esgota
   na primeira cor e **a segunda nunca é lida**. O `both_colors=True` fica inerte, em silêncio,
   exatamente nos pares mais citados pelos livros — e o docstring de `lookup_pair` justifica a
   opção com *"'Coull - Stanciu' é como o autor escreveu, não uma declaração de quem tinha as
   brancas"*.

2. **A busca não usa o porteiro da S-85.** `games_index.py:321` chama `partida.positions()` sem
   passar `occupancies`, e `ui/gallery_model.py:627` o invoca a partir de
   `GamesDialog.search_by_name` — **na thread do Tk**. A S-85 mediu que o porteiro de ocupação
   corta ~3× o custo de reproduzir os lances, e este caminho paga o preço cheio.

O critério de aceite da Fase 13 é *"busca por nome de um diagrama: <1 s"*, medido em 27 ms
quando havia **uma** base. Com duas gigabases o caminho já custa 70–220 ms e cresce com a
pasta, tudo com a janela congelada.

**Solução.**

1. Duas consultas com `LIMIT` próprio — `SELECT ... WHERE pair=? LIMIT ?` duas vezes, ou um
   `UNION ALL` —, somando até `limit` no fim. Mudança de uma linha, sem tocar no esquema.
2. `positions_of` recebe `frozenset({occupancy(placement)})` e o repassa a
   `partida.positions(...)`. Reusa a função que já existe em `games_db`, e o docstring de
   `GameRecord.positions` já garante que o porteiro é filtro e não critério.

**Critério de aceite.** Um par prolífico devolve partidas das duas cores; a busca por nome de
um diagrama custa < 1 s com a pasta de base atual, medido.

**Testes.** `tests/test_games_index.py` — o par prolífico com as duas cores presentes; o
porteiro repassado (hoje ausente).

### O que foi entregue

**Duas consultas, e uma repartição — porque "duas consultas" sozinho não conserta.** A primeira
versão deste item deu `LIMIT limit - len(achados)` à segunda cor, que é o mesmo teto global
gasto em ordem: a primeira cor volta a comer tudo. **O teste passou no código anterior**, e foi
isso que mostrou o erro.

`_fair_share` reparte: cada cor recebe `limit // 2`, e o que sobrar — porque um dos lados tem
menos partidas que a fatia — é distribuído em ordem. Um par que só jogou com uma cor continua
recebendo o `limit` inteiro, e tem teste. O `limit` continua sendo teto: ele é o custo em
*seeks* de disco que quem chama aceitou pagar.

O teste do critério de aceite usa `limit` **menor que uma cor sozinha**, que é a condição em
que o defeito aparece — e é a diferença entre o teste que passava no código antigo e o que não
passa.

**O porteiro da S-85** entra em `positions_of` como `frozenset({occupancy(placement)})`. Ele é
filtro e não critério: o que decide continua sendo a igualdade das 64 casas, e há teste de que
a resposta não muda. Também há um teste de que ele é **repassado** — sem isso o item seria
invisível, porque o que muda é o custo, e custo não aparece numa asserção de igualdade.

---

## S-140 · O índice sem a cópia, e o cache que não cabe na memória

**Problema.** Dois artefatos que crescem com o acervo e nenhum dos dois tem teto.

1. **O índice guarda a mesma informação duas vezes.** `games_index.py:138-140` cria `games` com
   rowid implícito e a linha 177 cria `games_pair ON games (pair)`. A coluna de busca fica no
   índice e `offset`/`file` só na tabela: cada linha existe em **duas árvores**, e toda
   consulta paga uma sonda aleatória na tabela que só existe para ser sondada. Medido:
   `data/games_index.sqlite` tem **885 MB** onde **476** bastariam — 409 MB por nada, num
   artefato cujo custo cresce linearmente com a pasta de base (431 MB com uma gigabase, ~1,3 GB
   com três).

2. **O cache de posições é lido inteiro para a memória, na thread do Tk, a cada troca de
   livro.** `games_cache.py:210` faz `json.loads(caminho.read_text(...))` do arquivo inteiro, e
   `ui/gallery_panel.py:638` o chama de `_load_position_cache`. A 1.253 B/posição, os 34 livros
   do acervo projetam ~50 mil posições, **~63 MB de JSON, ~4,2 s de parse e ~190 MB
   residentes** — pagos a cada troca de PDF, com a janela congelada, para responder uma
   pergunta sobre um livro só.

**Solução.**

1. `CREATE TABLE games (pair, offset, file, PRIMARY KEY (pair, file, offset)) WITHOUT ROWID`,
   removendo o `CREATE INDEX`. `INDEX_VERSION` já existe para isto: sobe para 3, e `lookup_pair`
   recusa o índice antigo com a instrução de refazê-lo.
2. Separar as duas perguntas que o arquivo responde. O conjunto *"o que já foi perguntado"*
   pode ser um arquivo de chaves — uma linha por colocação — que só o `cvoff-games` lê; as
   candidatas ficam num SQLite por colocação, e o projeto já tem o padrão pronto na S-87.

**A ordem importa e o custo é assimétrico.** O item 2 é o que trava a janela hoje; o item 1 é
disco, e disco espera. Fazer o 2 primeiro.

**Critério de aceite.** Trocar de livro na Galeria não lê o cache inteiro (medido: hoje cresce
com o acervo, alvo constante); o índice refeito ocupa ≤ 500 MB para a base atual e responde no
mesmo tempo.

**Testes.** `tests/test_games_cache.py` — a leitura por livro não toca as posições dos outros.
`tests/test_games_index.py` — a recusa do índice de versão anterior, com a mensagem que diz
como refazer.

---

## S-141 · O processo filho não reimporta o programa inteiro

**Problema.** `games_db.py:725-731` cria `mp.Pool(min(processos, len(tarefas)))`. No Windows o
`spawn` reimporta o módulo `__main__` em cada filho — e medido, importar `app_tkinter.py` como
`__mp_main__` custa **3,16–3,94 s e ~233 MB** de `torch`, `cv2` e painéis de UI que o filho
**nunca usa**: ele lê PGN e reproduz lances.

Com 10 processos são ~2,3 GB de RAM e ~32 s de CPU jogados fora no arranque de cada varredura —
numa máquina que ao mesmo tempo pode estar treinando.

A S-73 já tinha esbarrado nisto por outro ângulo (a recursão do `spawn` que travou a máquina
uma vez) e resolveu **a recursão**, não o **peso**.

**Solução.** Fazer de `app_tkinter.py` e de `cli/games.py` cascas finas: mover os imports
pesados (`cv2`, `torch`, painéis de UI) para dentro de `main()` e das funções que os usam, de
modo que o `__mp_main__` do filho custe o import de um módulo praticamente vazio. Nenhuma
fronteira de módulo muda; o que muda é **quando** cada import acontece.

**Critério de aceite.** Importar `app_tkinter` como `__mp_main__` custa < 0,5 s e < 30 MB
(hoje 3,2–3,9 s e ~233 MB); a varredura por posição continua dando a mesma resposta.

**Testes.** `tests/test_packaging.py` — um subprocesso que importa `app_tkinter` com o marcador
de filho e afirma que `torch` **não** está em `sys.modules`.

---

## S-142 · A página concluída se diz concluída, e o verde aparece na primeira visita ✅ implementada (2026-08-17)

**Problema.** São dois, e o segundo é um defeito que torna o primeiro mentiroso.

**1. Ninguém diz que a página acabou.** A S-71 pinta de verde cada diagrama já salvo e
`ui/pdf_panel.py:768` (`_update_boxes_label`) soma as parcelas — `"3 diagrama(s) · 1 lido(s) ·
2 salvo(s)"`. A pergunta do laço interno, porém, não é *quantos*: é **"posso virar?"**.
Respondê-la custa comparar duas parcelas que estão em pontas opostas da mesma frase, e numa
página de exercícios com grade 3×3 — nove diagramas, que o teto da S-68 existe para caber — é
uma conta que se erra. Errar para menos faz reabrir a página; errar para mais **deixa
diagrama para trás**, e é o erro que não aparece: nada na tela volta a citar aquela página.

**2. O verde não aparece na primeira visita à página.** `app_tkinter.py:868` desenha as caixas
como o detector as devolveu:

```python
if not painel.set_diagram_boxes(caixas):   # `caixas` vem do `_overlay_worker`, sem carimbo
    return
```

`boxes_from_candidates` constrói `DiagramBox` com `saved=False`, e quem carimba é o
`mark_saved` do `_refresh_overlay` — que este caminho não atravessa. O resultado: numa página
ainda não visitada nesta sessão os retângulos saem **azuis**, mesmo com as amostras no
`labels.csv`. O verde só chega na segunda passada, quando a detecção já está no
`PageBoxesCache` e o `_refresh_overlay` monta as caixas por conta própria.

A primeira visita é exatamente a que a S-71 existe para atender — *"abrir um livro pela quinta
vez e ver de verde o que já foi feito é a única forma barata de responder «onde eu parei?»"*
(`ui/pdf_panel.py:92`). O recurso funcionava em toda página **menos** naquela em que a
pergunta está sendo feita.

**Solução.**

1. `PageBoxes.all_saved`, ao lado de `recognized` e com a mesma regra para o vazio: página sem
   diagrama **não** é página concluída. Só olha `saved` — confirmado pela base (S-75) é *"não
   precisa"*, não *"foi feito"*, e uma página de confirmados não rendeu amostra nenhuma.
2. O rótulo do painel troca a soma por uma frase quando não sobra nada, na cor dos retângulos:
   `✓ página concluída · N diagrama(s) salvo(s)`. Quando falta alguém, `"2 salvo(s)"` passa a
   `"2 de 3 salvo(s)"` — o número solto não dizia se faltava um ou sete.
3. A barra de status anuncia **só o estado terminal**. Ela é uma linha só e todo mundo escreve
   nela; um aviso por virada de página gastaria o lugar do erro de OCR.
4. `_apply_overlay` passa a desenhar **pelo** `_refresh_overlay` em vez de mandar as caixas
   cruas para a tela. O carimbo continua onde a S-71 o pôs — na hora de desenhar, contra o CSV
   — e o cache continua guardando as caixas cruas, que é o que faz a cor acompanhar o CSV em
   vez do momento em que a detecção rodou.

**Critério de aceite.** A primeira visita a uma página cujos diagramas já estão no `labels.csv`
abre com os retângulos verdes e o rótulo dizendo "concluída"; salvar o último diagrama que
faltava anuncia a conclusão sem que seja preciso virar a página e voltar; uma página de prosa
não se diz concluída.

**Testes.** `tests/test_page_overlay.py` — `all_saved` com todos, com um faltando, com a página
vazia, e com confirmados no lugar de salvos. `tests/test_pdf_panel.py` — o rótulo da página
concluída e sua cor, a fração quando falta alguém, e a cor que se apaga na página seguinte.

### O que foi entregue

**O defeito do carimbo é o que dava valor ao item, e ele não estava no pedido.** O pedido era o
marcador de página concluída; a primeira visita desenhar azul apareceu ao seguir de onde
`saved` entra na caixa. Sem essa correção o marcador seria *pior* que nada na única página que
importa: ele afirmaria "faltam 3" sobre uma página inteira já salva.

**A ordem dos dois avisos na barra de status é parte da correção.** `_apply_overlay` escreve
`"Página N: 3 diagrama(s) marcado(s)"` e **depois** chama o `_refresh_overlay`, que é quem
anuncia a conclusão. Invertido, o aviso genérico apagaria o específico justamente no caminho da
primeira visita.

**A guarda da caixa atrasada subiu de lugar.** Ela morava no `set_diagram_boxes`, que recusa
desenhar caixas de outra página. Como agora quem desenha é o `_refresh_overlay` — que também
sincroniza a seleção e anuncia a conclusão —, a recusa precisa vir antes: chamá-lo para a
página 16 com a 17 na tela deixaria o desenho de fora e as duas afirmações de pé, sobre a
página errada.

**A conclusão não é anunciada a cada virada de página, e isso é decisão e não economia.** A
barra é o lugar onde aparecem o erro de OCR e o caminho da amostra salva. Quando ela fala por
cima do `"Exemplo salvo: ..."` — o caso de salvar o último diagrama que faltava — é de
propósito: o caminho do arquivo ainda aparece na caixa de sucesso, e "a página terminou" não
aparece em lugar nenhum.

**Compõe com a S-114 sem ter sido combinado.** Aquele item fez o `save_all` chamar
`_on_sample_saved()`, que é o gatilho do `_refresh_overlay`. Com os dois, `Ctrl+Shift+S` numa
página inteira termina anunciando a conclusão dela.

**Conferido chamando os métodos reais da janela** sobre um objeto mínimo, com quatro cenários:
primeira visita com 3 de 3 no CSV (antes 0 retângulos verdes, agora 3), 2 de 3, nada salvo, e a
detecção da página 5 chegando com a 0 na tela. O cache guarda as caixas cruas nos quatro.

---

# Fase 18 — Quando algo dá errado

> O bundle da S-55 é `console=False` e não grava log por padrão. Hoje, uma janela que não abre
> não deixa rastro nenhum — e é o modo de falha que o `--selftest` da S-55 existe para atender.

> ⚠ **A maior parte dos itens desta fase e da 19 não passou pelo cético.** O orçamento da
> sessão da avaliação acabou antes: 13 dos 59 achados ficaram sem veredito, e são os de
> detecção e metade os de engenharia. A evidência abaixo é a que o auditor deu, com
> arquivo:linha, e várias foram medidas por ele — mas ninguém tentou derrubá-la. **Confira o
> arquivo:linha antes de implementar.** Nos itens que passaram pelo cético, quatro
> sobreviveram menores do que nasceram; é razoável esperar o mesmo aqui.
>
> **Duas exceções, conferidas à mão em 2026-08-16:** a **S-123** (a ordem em
> `ui/pdf_panel.py:577-581` é literalmente `_on_pdf_opened` → `source` → `name` →
> `get_pdf_page_count`) e a **S-124** (reproduzida: `load_settings` com
> `{"engine": {"movetime_ms": "rapido"}}` levanta `ValueError`, e o docstring da própria função
> promete que *"arquivo ausente ou corrompido cai no padrão"*).

## S-123 · O PDF que não abre não troca o livro por dentro ✅ implementada (2026-08-17)

**Problema.** `ui/pdf_panel.py:576-591` — `load_pdf` chama `self._on_pdf_opened(pdf_path)` e
atribui `self.source`/`self.name` **antes** de `get_pdf_page_count`, que é quem levanta quando
o arquivo está corrompido.

O callback já rodou: `app_tkinter.py:633` limpou `page_boxes`, descartou os resultados do
documento anterior e apontou a Galeria para o arquivo quebrado. A tela continua mostrando o
livro anterior; o programa, por dentro, está no arquivo que não abriu. O próximo `Ctrl+S` ou a
próxima anotação vai para o lugar errado.

**Solução.** Inverter a ordem dentro do `try`: abrir o documento (ou chamar
`get_pdf_page_count`) como **primeira** linha, e só então `_on_pdf_opened`, `source`, `name`,
`page_count` e `render_current_page`. No `except`, não tocar em estado nenhum.

É a regra geral que vale para os dois outros itens desta fase: **validar antes de mutar.**

**Critério de aceite.** Abrir um PDF válido e em seguida um corrompido deixa o estado no PDF
válido; a mensagem de erro nomeia o arquivo que falhou.

**Testes.** `tests/test_pdf_panel.py` — o estado preservado depois da falha; nenhum callback
disparado.

### O que foi entregue

`get_pdf_page_count` virou a **primeira** linha de `load_pdf`, e o `page_count` que ela devolve
é o que segue adiante — contar as páginas é abrir o documento, então a validação não custa uma
abertura a mais. Só depois vêm `_on_pdf_opened`, `source`, `name` e o render.

**O `except` continuou largo, contra a letra do enunciado, e a razão é a da própria fase.** Um
`except` estreito só na abertura deixaria uma falha em `_on_pdf_opened` subir para o callback
do Tk — que no bundle da S-55 (`console=False`) não tem para onde escrever. Trocar um modo de
falha silencioso por outro não é o negócio desta fase. O que resolve o enunciado é a **ordem**,
e ela está resolvida com o `except` no lugar onde estava.

**A frase sobre o livro anterior é condicionada ao estado, e não à suposição.** A mensagem diz
`"bom.pdf continua aberto"` testando `self.source is not None and self.source != pdf_path` na
hora do erro — verdadeiro no caso da S-123, e falso se algo quebrar *depois* da troca. Assim a
caixa não promete o que a memória não tem, inclusive na falha que ninguém previu. Sem livro
anterior nenhum, a frase não aparece: dizer "continua aberto" sobre nada seria pior que calar.

**Um `logger.exception` no `except`**, que não havia. Pela S-127, num `.exe` isto agora vira
linha em `logs/chessvisionoff.log`.

**Um defeito de teste encontrado de raspão, e ele escondia testes.** A segunda classe Tk do
módulo era **pulada** — `tk wasn't installed properly` ao criar a segunda raiz do processo,
depois de a primeira ter sido destruída. É a mesma armadilha que o `test_result_panel` já
havia documentado, e a mesma correção: uma raiz de módulo em `_raiz()`, criada uma vez e nunca
destruída. Antes disso os 6 testes novos passavam sem rodar.

**Conferido invertendo a correção:** com o `load_pdf` antigo, 5 dos 6 testes falham. O sexto é
o controle — o PDF válido, que abre nos dois.

---

## S-124 · Um `settings.json` inválido não impede a janela de abrir ✅ implementada (2026-08-17)

**Problema.** `settings.py:320-336` — `load_settings` captura `OSError` e
`json.JSONDecodeError`, mas `EngineSettings.from_dict` (`:138-139`) faz `int(str(...))` e
`RemoteFenSettings.from_dict` (`:115`) faz `float(str(...))`. Um JSON **sintaticamente válido**
com `"movetime_ms": "rápido"` levanta `ValueError`, que ninguém captura.

`app_tkinter.py:135` chama `load_settings()` dentro do `__init__`, antes de a janela existir.
Num checkout sai um traceback; no bundle da S-55 (`packaging/cvoff.spec:111`, `console=False`)
**não sai nada** — o programa não abre e não diz por quê.

**Solução.** Coerção por campo que cai no padrão **daquele campo** — um `_inteiro(dado,
padrao)` / `_flutuante(dado, padrao)` usados nas três `from_dict` — e não um `except
ValueError` global: um `timeout` ruim não pode zerar também o `endpoint`, que é trabalho do
usuário. Cada coerção que cai no padrão emite um `logger.warning` nomeando o campo.

**Critério de aceite.** `settings.json` com qualquer campo de tipo errado abre a janela, usa o
padrão daquele campo, preserva os demais, e o log diz qual campo foi ignorado.

**Testes.** `tests/test_settings.py` — um caso por campo tipado; os outros campos intactos; o
aviso sob `assertLogs`.

### O que foi entregue

`_inteiro(data, chave, padrao)` e `_flutuante(...)` nas três `from_dict`, cada um caindo no
padrão **daquele campo** e avisando com o nome dele. É por campo e não um `except ValueError`
global pela razão do enunciado, e ela tem teste: um `movetime_ms` com `"rápido"` dentro não
pode zerar também o `endpoint`, que é a única preferência do arquivo que ninguém recupera
sozinho.

**Duas decisões que os testes travam:**

- **`"8"` continua valendo.** A coerção não pode virar rigor — um arquivo editado à mão é
  exatamente onde o número entre aspas aparece.
- **Campo ausente não avisa.** Padrão não é defeito, e avisar sobre o que ninguém escreveu
  treinaria a ignorar o log.

**E uma rede de segurança além do que o enunciado pedia:** `load_settings` envolve o
`Settings.from_dict` num `except Exception` que abre com os padrões e loga. Não é o conserto —
o conserto é a coerção por campo, que preserva o resto do arquivo — mas cobre a forma que
ninguém previu, e existe porque o custo do erro é desproporcional: no bundle da S-55
(`console=False`) o programa não abre e não diz por quê.

---

## S-125 · O worker de OCR loga a exceção como os outros cinco ✅ implementada (2026-08-17)

**Problema.** `app_tkinter.py:1053-1061`:

```python
except Exception as exc:
    self.root.after(0, partial(self._on_ocr_error, exc))
```

Sem `logger.exception`. E `_on_ocr_error` (`:1072-1076`) mostra
`messagebox.showerror("Erro", f"Falha no OCR:\n{exc}")` — só `str(exc)`, sem traceback e sem
log. É o **único** dos seis workers do programa que engole a exceção sem registrar.

Reconhecer uma página é o que o programa faz. Quando isso quebra num `.exe` sem console, o
usuário recebe uma linha de texto e o arquivo de log não recebe nada.

**Solução.** Um `logger.exception("Falha no OCR de %s.", origin)` no `except`, igual aos outros
cinco. E, para a mensagem: o serviço levanta uma exceção nomeada (`NoBoardDetectedError` já
existe) e `_on_ocr_error` testa o tipo, para que "não achei tabuleiro nesta página" — que é
esperado e não é erro — deixe de ter a mesma cara que uma falha de verdade.

**Critério de aceite.** Uma exceção no worker produz registro de nível `ERROR` com traceback;
"nenhum tabuleiro" produz mensagem informativa e não caixa de erro.

**Testes.** `tests/test_packaging.py` (que já importa `app_tkinter`) — `_ocr_worker` com um
`run` que levanta, sob `assertLogs`, produz `ERROR` com traceback.

### O que foi entregue

Dois `except` onde havia um, e a separação entre eles é o item inteiro:

| o que aconteceu | log | tela |
|---|---|---|
| `NoBoardDetectedError` | `INFO`, sem rastro | `showinfo`, com o atalho para **Selecionar área (OCR)** |
| qualquer outra coisa | `ERROR` com traceback | `showerror`, dizendo que o traceback está no log |

**A exceção nomeada precisou existir de verdade.** O enunciado dizia que `NoBoardDetectedError`
"já existe" — existe, mas `service.py:683` levantava `ValueError`, e a classe só era usada pelo
`detect_board` de uma imagem só, que não é o caminho da janela. A troca é o que permite testar
o tipo; sem ela a única separação possível continuaria sendo procurar a mensagem dentro do
texto da exceção, que era o que `app_tkinter.py:1174` fazia.

**A troca não move nenhum código de saída da CLI.** `run_main` (S-126) captura `ValueError`,
`OSError` e `RuntimeError` na mesma cláusula, e `NoBoardDetectedError` é `RuntimeError` — os
15 comandos continuam saindo com 2. Conferido rodando `test_cli_errors.py`.

**"Não há diagrama aqui" é a resposta mais comum de um livro** — prosa, índice, página de
soluções. Continuava chegando ao usuário como caixa vermelha de erro, e o texto exibido era o
da exceção, sem dizer o que fazer a seguir. Agora nomeia a saída que existe para o caso em que
*há* diagrama e o detector não o achou, que é a linha que o `README` já dava na tabela de
sintomas.

**Conferido invertendo a correção:** com o `except` único de antes, os 5 testes falham — dois
por `no logs of level INFO or higher triggered`, que é literalmente o defeito do enunciado.

---

## S-126 · Os `cvoff-*` falham em pt-BR, com código de saída por classe

**Problema.** `uv run cvoff-infer <arquivo de lixo>` produz 11 quadros de traceback terminando
em `pymupdf.FileDataError: Failed to open file '...'`, **em inglês**. `cli/infer.py:36-41` só
captura `NoBoardDetectedError`; `cli/export_pgn.py:113` chama `save_pdf_positions_to_pgn` sem
`try` nenhum. **14 dos 15 comandos** se comportam assim.

O `CONTRIBUTING.md:173` declara que a saída dos `cvoff-*` é a interface daquele programa. Nas
três falhas mais prováveis — PDF corrompido, checkpoint de outra `arch_version`, caminho
inexistente — essa interface é um traceback em inglês e um código de saída indistinguível.

**Solução.** Um `run_main(fn, argv)` em `cli/__init__.py` (que hoje só tem docstring),
capturando `ValueError`, `OSError` e `fitz.FileDataError`, imprimindo a mensagem em pt-BR e
devolvendo código de saída por classe — no molde do que o `--selftest` da S-55 já faz
(`0` ok, `2` sem PDF, `3` sem checkpoint, `4` lê mas não treina, `1` falha):

| código | significado |
|---|---|
| 0 | ok |
| 1 | falha inesperada (o traceback vai para o log, não para a tela) |
| 2 | entrada inválida: PDF corrompido, caminho inexistente |
| 3 | checkpoint ausente ou de outra `arch_version` |

`-v` continua mostrando o traceback, para quem está depurando.

**Critério de aceite.** Os 15 comandos, sobre um arquivo de lixo, saem com código 2 e uma linha
em pt-BR; com `-v`, o traceback aparece.

**Testes.** `tests/test_cli.py` — uma tabela dos 15 comandos contra entrada inválida, afirmando
o código e que a saída não contém `Traceback`.

---

## S-127 · O bundle congelado deixa rastro em disco

**Problema.** `packaging/cvoff.spec:111-113` desliga o console com o comentário *"O log continua
indo para o arquivo que `logging_setup.default_log_file()` decide, e é lá que se olha quando
algo falha"*. Mas `logging_setup.py:63-68` devolve `None` quando `CVOFF_LOG_DIR` não está
definida, e **nada no bundle a define**.

Junte com a S-124: o usuário do `.exe` tem uma janela que não aparece, sem console, sem log e
sem código de saída visível.

**Solução.** Congelado (`sys.frozen`), `default_log_file()` cai para `PROJECT_ROOT/logs/` — que
no bundle é a pasta ao lado do `.exe`, junto com `data/`, `models/`, `PDF/` e `PGN/`, que é
onde o usuário já sabe procurar. E `build_windows.py` cria `logs/` junto com as outras quatro.

**Critério de aceite.** Um `.exe` que falha ao abrir deixa `logs/chessvisionoff.log` com o
traceback; o comentário da `cvoff.spec` passa a ser verdade.

**Testes.** `tests/test_packaging.py` — `default_log_file()` com `sys.frozen` simulado devolve
caminho e não `None`.

---

## S-128 · A CI roda o ambiente que o CONTRIBUTING promete

**Problema.** `.github/workflows/ci.yml:31` roda `uv sync --extra dev --frozen`;
`CONTRIBUTING.md:6` manda `uv sync --extra dev --extra onnx --extra ocr`.

Sem os extras, `tests/test_onnx_export.py:51` desliga a classe `ExportTests` inteira — que é
**toda a cobertura executável** de `onnx_export.py` — e o contrato de motor da S-42 não roda.
A S-30 (paridade numérica do ONNX) e a S-42 são código entregue cuja única verificação nunca
roda na CI: uma regressão neles entra verde.

E **11 dos 15 comandos `cvoff-*` não são importados por teste nenhum**: renomear um alvo em
`[project.scripts]` não quebra nada até alguém tentar rodar.

**Solução.** Três coisas, duas baratas:

1. Um teste que lê `[project.scripts]` do `pyproject.toml`, importa cada alvo e confere que
   `main` é chamável. Roda em qualquer ambiente e pega renomeação.
2. Instalar `--extra onnx --extra ocr` na CI.
3. Um teste de ida e volta para `_matches_to_json`/`_matches_from_json` (`cli/games.py:146-193`)
   — o formato v2 **é o artefato dos 104 minutos** de 2026-08-13, tem ramo de compatibilidade
   explícito para a v1, e não tem teste nenhum.

**Critério de aceite.** A CI roda os testes de ONNX e do contrato de OCR; renomear um
entrypoint faz a suíte falhar; o JSON de casamentos sobrevive a uma ida e volta, e a v1
continua carregando.

**Testes.** `tests/test_cli.py` — os 15 entrypoints. `tests/test_games_db.py` — a ida e volta e
o ramo v1.

---

# Fase 19 — A detecção, e a documentação que descreve o programa que existe

## S-129 · A página com `/Rotate` não gera candidato fantasma

**Problema.** `detection/embedded.py:567` lê `info["bbox"]` de `page.get_image_info()` e passa
a caixa crua a `_pixels_for_bbox` (`:608`), que recorta com `page.get_pixmap(clip=bbox)`. A
caixa vem no sistema **não girado**; o pixmap já vem **girado**. Numa página com `/Rotate`
diferente de zero, o recorte sai de outro lugar da página.

O resultado não é um erro: é um candidato que parece diagrama, entra na fila, e ocupa uma vaga
do teto por página — a mesma classe de defeito do glifo de cavalo que a `ANALISE_DETECCAO`
documenta, e igualmente invisível em relatório.

**Solução.** Uma linha em `candidates_from_embedded_images`:

```python
bbox = fitz.Rect(info["bbox"]) * page.rotation_matrix
```

A mesma correção em `pdf_text._page_lines` e `pdf_text._bare_integers`, que têm o problema
irmão: a legenda casada por proximidade usa coordenadas que não são as do render.

**Antes e depois, com o instrumento que a S-82 construiu.** `cvoff-census --baseline` sobre o
acervo diz quantos candidatos entram e saem; a regra da S-82 vale — perder suspeito é o
objetivo, perder candidato do tamanho de um diagrama impresso precisa de justificativa uma a
uma.

**Critério de aceite.** Num PDF sintético com tabuleiro em posição conhecida e `/Rotate 90`, a
caixa do candidato embutido coincide com a do contorno (hoje não coincide); o censo do acervo
não perde candidato legítimo.

**Testes.** `tests/test_detection_embedded.py` — o PDF sintético girado, os quatro valores de
`/Rotate`.

---

## S-130 · A nota de textura não muda com a resolução do recorte

**Problema.** `board_texture_score` (`detection/hybrid.py:71-78`) reamostra para 320 px;
`_board_pattern_score` (`board_detection.py:186`) reamostra de novo para 160. As duas imagens
comparadas em `refine_candidate_with_contour` (`hybrid.py:130-132`) **nunca chegam na mesma
resolução**.

A nota que arbitra "recorte embutido contra achado de contorno" depende, então, da resolução em
que cada um chegou — e não só do que a imagem mostra. Medido, isso vira a decisão em **7 de 141
casos**.

**Solução.** Pontuar as duas a partir do mesmo lado: reduzir ambas a `min(lado_a, lado_b)` com
`INTER_AREA` antes de chamar `board_texture_score`, dentro de `refine_candidate_with_contour` e
de `_contour_wins_over_merged`.

**Critério de aceite.** A mesma imagem, entregue em duas resoluções, recebe a mesma nota (dentro
de tolerância declarada); o censo do acervo mostra o efeito, com os casos que viraram listados
um a um.

**Testes.** `tests/test_hybrid.py` — a nota invariante à escala; a arbitragem estável.

---

## S-131 · O caminho de contorno ganha instrumento antes de ajuste

**Problema.** Contado com `ast`: `board_detection.py` tem **0 constantes nomeadas e 179
literais numéricos**, contra 11 nomeadas em `detection/embedded.py`, 6 em `detection/hybrid.py`
e 5 em `preprocess.py` — todas com o número medido no docstring.

É o único caminho do núcleo sem constante nomeada, sem medição registrada e sem instrumento —
e é a **única fonte** de candidato em boa parte do acervo, para os livros cuja página não traz
imagem embutida.

**Solução.** Na ordem que a S-82 provou valer:

1. **`cvoff-census --recusas`**: gravar também o candidato **recusado**, por `min_score` e por
   IoU, com score, textura e caixa. O instrumento antes do ajuste — hoje o censo conta o que
   entra e é cego ao que foi barrado, que é justamente onde mora o recall perdido.
2. Só então nomear as constantes que decidem, cada uma com o número medido no docstring, no
   padrão dos três módulos irmãos.

**A ordem não é estética.** Nomear 179 literais sem instrumento é renomear no escuro; e o
projeto já tem o precedente do que acontece quando se ajusta limiar sem censo
(`ANALISE_DETECCAO.md` §5, dois ajustes testados e reprovados).

**Critério de aceite.** `cvoff-census --recusas` lista o recusado com o motivo; as constantes
que decidem têm nome e número medido; o censo antes/depois não perde candidato legítimo.

**Testes.** `tests/test_detection_census.py` — as recusas no relatório; o diff que casa por
canto de bbox, como a S-82 já faz.

---

## S-132 · O que o gate não enxerga, escrito onde ele decide

**Problema.** `prediction_from_probs` (`inference.py:239-241`) troca as confianças pelas das
classes efetivamente escolhidas — o que é o desenho certo. A **consequência** não está escrita
em lugar nenhum: uma casa reparada pelo `decode.py` recebeu, por definição, uma classe que não
era o argmax; sua confiança é a da segunda opção, quase sempre baixa.

**Efeito: nenhuma posição reparada pelo decodificador passa o gate de 0,80.** O reparo da S-11
— que é uma das entregas centrais da Fase 2 — é invisível ao critério de saída da Fase 7, e o
número "casas reparadas" que o `cvoff-field` publica ao lado da taxa de exportação descreve
diagramas que, em sua maioria, não foram exportados.

Não é defeito: é propriedade, e ela muda a leitura de duas métricas que o projeto publica lado
a lado.

**Solução.** Registrar a propriedade onde ela decide: docstring de `decode_constrained`, e a
seção do gate no ROADMAP. E, no relatório do `cvoff-field`, separar "casas reparadas" em
**reparadas e exportadas** contra **reparadas e barradas** — hoje o número soma os dois e
sugere que o reparo está ajudando a exportar.

Se um dia se quiser que o reparo chegue ao PGN, a mudança é no **gate** e não no
decodificador — e essa separação é o que este item deixa registrado.

**Critério de aceite.** O docstring diz a propriedade; o relatório separa os dois números.

**Testes.** `tests/test_field_eval.py` — a separação; `tests/test_decode.py` — um teste que
trava a propriedade, com o docstring dizendo por que ela existe.

---

## S-133 · S-76 e S-77 registradas

**Problema.** `git log` traz `dd33644` ("S-76: 'Aplicar a todos' espalhou quatro campos por
1.405 diagramas") e `11235da` ("S-77: anotar o conjunto de campo na propria pagina"). Extraindo
os identificadores de cada documento: `SPEC.md`/`ROADMAP.md` param em S-36; `SPEC_FASE7.md`
vai a S-75; `ANALISE_DETECCAO.md` começa em S-78; `PLANO_BASE_PARTIDAS.md` começa em S-83.

**S-76 e S-77 caem na fenda, e não existem em documento nenhum** — são citadas de passagem
quatro vezes no `PLANO_BASE_PARTIDAS.md` e nunca especificadas.

Duas entregas em produção sem critério de aceite registrado, e uma delas (S-77) é a ferramenta
que o próprio ROADMAP_FASE7 chama de *"a pendência que destrava as outras"*. Quem for crescer o
conjunto de campo não tem onde ler o que ela decidiu — e a S-95 mostra que ela decidiu uma
coisa errada.

**Solução.** Uma seção para cada, no formato das outras: problema, mudança, critério de aceite,
o que foi medido. O conteúdo está nas mensagens de commit, que são longas e boas; é
transcrição, não arqueologia.

**Critério de aceite.** Todo `S-\d+` que aparece em `git log --oneline` tem seção própria em
algum `docs/*.md`.

**Testes.** É a S-134.

---

## S-134 · O índice de documentos, verificável por teste

**Problema.** A spec está em seis arquivos com convenções diferentes e **sem índice**. O
`CONTRIBUTING.md:188` manda registrar mudança de fase no `ROADMAP.md`, que fecha na Fase 6.

`docs/PLANO_BASE_PARTIDAS.md` (51 KB, doze entregas) e `docs/ANALISE_DETECCAO.md` (S-78 a
S-82) não apareciam no índice "Documentação técnica" do README. **Os dois são apontados pelo
código** — `games_db.py:24` cita o primeiro; `cli/census.py:140` e `detection/hybrid.py:223`
citam o segundo — o que é uma referência boa, e não substitui a navegação: quem procura *onde
está a spec da entrega X* lê o índice, não o `grep`.

Essa é a causa mecânica do sumiço de S-76 e S-77: o CONTRIBUTING aponta para o arquivo errado e
não há índice que force a escolha certa.

**Solução.** Três coisas, e a terceira é a que impede a repetição:

1. Uma tabela "faixa de itens → arquivo" no topo do README e no de cada spec (esta já está no
   topo deste arquivo).
2. O §Documentação do CONTRIBUTING passa a dizer "o doc da fase corrente" em vez de nomear o
   `ROADMAP.md`.
3. **Dois testes**: um que extrai `S-\d+` de `git log --oneline` e falha se algum identificador
   entregue não tiver seção em `docs/*.md`; outro que exige que todo `docs/*.md` apareça no
   índice do README.

**Critério de aceite.** Entregar uma S-NN sem documentá-la faz a suíte falhar, nomeando o
identificador e o commit.

**Testes.** `tests/test_docs.py` (novo) — os dois acima.

---

## S-135 · Os números vivos: ARCHITECTURE, README, bundle

**Problema.** Doze divergências medidas entre o que os documentos afirmam e o que o disco tem:

| afirmação | realidade |
|---|---|
| `ARCHITECTURE.md:11` — "`app_tkinter.py` e `app_streamlit.py` são apresentação" | `app_streamlit.py` não existe desde a S-54 |
| `ARCHITECTURE.md:161` — "o `labels.csv` tem 3.313 linhas" | **3.936** |
| `ARCHITECTURE.md` — "`source_page` com 98,6% de células vazias" | **84,1%** |
| `ARCHITECTURE.md:212` — "quatro operações longas" | **12** threads, **2** registradas |
| tabela "Formatos e persistência" | 8 de ~17 artefatos; `splits.csv` duplicado; `provenance_index.jsonl` **não existe** |
| árvore "Estrutura" do README | 31 de 47 módulos |
| README — "7 dos **27** livros" (quatro lugares) | **34** PDFs |
| README — "3.200 PNGs" | **3.935** |
| README — base de partidas "9,7 GB" / "18,9 GB" | **18 GB** |
| README:60 — bundle "696 MB, 5.247 arquivos" | do build de 2026-08-09, que ainda contém `pythonnet` e `clr_loader`, removidos na S-69 |
| README:233 — "o header diz qual dos **três** foi" | **oito** declarados em `semantics.py:40-42`, e um nono (`queue`) emitido fora do tipo |
| README — "os três comandos abaixo" | a lista tem quinze |
| o botão **"2ª opinião"** (S-66) | está na tela (`ui/second_opinion_button.py:59`), exige o extra `second-opinion` e um clone externo de 232 MiB apontado por `local_reader.path` — e **não é mencionado no README nem no CONTRIBUTING** |

**Solução.** Corrigir é a parte fácil; o item é sobre **não repetir**. Cada número passa a ter
uma fonte viva e um teste:

- os de contagem (`labels.csv`, PNGs, PDFs, módulos) vêm de um comando (`cvoff-audit` já conta
  os dois primeiros) e um teste compara o citado com o real;
- o bundle é refeito, e `build_windows.py` grava `{mb, arquivos, data, commit}` em
  `docs/metrics/bundle.json`, versionado, com teste contra o que o README afirma;
- a tabela de persistência ganha as nove linhas que faltam e um teste que lista `data/*` e
  falha nos dois sentidos (artefato sem linha, linha sem artefato);
- a tabela de fontes do lado a jogar ganha `database` e `manual`, com teste sobre
  `get_args(SideSource)`. O `queue` de `result_panel.py:471` precisa de decisão à parte: entra
  no `Literal` com rótulo, ou vira um dos oito;
- **cada chave de `[project.optional-dependencies]` precisa aparecer no README** — hoje o teste
  falharia em `second-opinion`. É a mesma família de guarda, e é o que fecha a linha do botão
  "2ª opinião" acima: uma subseção em "Recursos opcionais", no formato das outras quatro (o que
  faz, o que custa, como habilitar, o que o produto faz sem ele).

**Critério de aceite.** Nenhum número citado em documento diverge do disco sem que a suíte
falhe.

**Testes.** `tests/test_docs.py` — um caso por família de número.

---

## S-136 · `app_tkinter.py` dobrou: reabrir o item ou registrar o novo placar

**Problema.** `SPEC.md:811` fixa o critério de aceite da S-31: *"`app_tkinter.py` abaixo de 600
linhas"*. O `ROADMAP.md:852` registra o placar de fechamento — **651** — e o `:968` a decisão:
*"podia estar abaixo de 600 e não vale a pena; faltam ~50 linhas"*.

Hoje são **1.302**. A trajetória: 2.388 antes da S-31 → **651** (2026-07-27) → 703 → 1.153
(2026-08-12) → 1.302. **Dobrou depois da decomposição**, com as Fases 12 e 13, e nenhum
documento registra.

O argumento "faltam ~50 linhas e não vale a pena" era honesto a 651. A 1.302 ele deixou de ser
o mesmo argumento, e ninguém refez a conta. E a S-95 é a prova de que isso custa: a decisão de
onde vem a verdade de referência mora nessas linhas, e não tinha teste porque não dava para
testar sem janela.

**Solução.** Uma das duas, e a escolha é do dono do projeto:

- **reabrir a S-31**, extraindo para `ui/` o que cresceu — o conjunto de campo (S-77), a
  fiação da Galeria e o cache de página são os três candidatos, e o primeiro é o da S-95;
- **ou registrar o novo placar** no fechamento da S-31, com o motivo do crescimento.

Nos dois casos, um teste `test_a_janela_nao_volta_a_crescer` trava a linha de corte no valor
escolhido, com o docstring dizendo por que 600 foi o alvo. Isso transforma o número numa
decisão em vez de num acidente, que é o que o `CONTRIBUTING.md:39-45` pede de um teste.

**Critério de aceite.** O número está registrado, e crescer além dele faz a suíte falhar.

**Testes.** `tests/test_packaging.py` — a linha de corte, com o motivo no docstring.

---

## S-137 · As três guardas de arquitetura, e o peso que ninguém usa

**Problema.** Quatro coisas pequenas, da mesma família — regras declaradas que nada verifica, e
peso que nada justifica:

1. **`mypy` não olha o produto.** `pyproject.toml:121` declara `files = ["src"]`, e
   `app_tkinter.py` — 1.302 linhas, onde tudo é montado, e onde o `CONTRIBUTING.md:60-62`
   registra que um `AttributeError` sobreviveu a 509 testes verdes — fica de fora. Ele passa
   limpo hoje; o que falta é a guarda.
2. **A regra do `atomic_io` é a única das três sem teste.** As irmãs têm varredura de árvore
   (`tests/test_labels.py:302-330` para a porta única do `labels.csv`; a varredura de `tkinter`
   para os módulos sem Tk). Para o `atomic_io`, `CONTRIBUTING.md:175` declara e nada verifica —
   e `write_text` trunca antes de escrever, que é o defeito exato que a S-25 fechou.
3. **A varredura de `tkinter` cobre 4 dos 12 módulos sem Tk.** Hoje são doze — `board_edit`,
   `board_model`, `busy`, `editor_model`, `field_draft`, `gallery_model`, `legality`,
   `page_overlay`, `page_results`, `state`, `strings`, `viewport` — e só quatro têm teste
   próprio. A separação que sustenta toda a testabilidade da interface é declarada em seis
   docstrings e verificada em quatro.
4. **`streamlit` é dependência obrigatória de um exemplo aposentado.** `pyproject.toml:16` o
   lista em `[project].dependencies`, ao lado de `torch` e `opencv`, enquanto `onnx`, `ocr`,
   `packaging` e `second-opinion` são extras. Nada em `src/` o importa. Ele arrasta `pyarrow`, e
   juntos são **115,4 MiB — 16,6% do bundle** que o usuário baixa e nunca executa, por um
   exemplo que a S-54 aposentou.

E, no mesmo espírito, uma função pública sem chamador: `dataset_browser.py:198`
`route_distribution()` não é referenciada em lugar nenhum, nem em `tests/`. Ela é justamente a
que leria a coluna `corrected_by` da S-52 — **625 valores já gravados que nenhuma tela e nenhum
comando lê**.

**Solução.**

1. `files = ["src", "app_tkinter.py", "packaging", "examples"]`, com
   `[[tool.mypy.overrides]]` mais frouxo para o exemplo se ele não merecer o mesmo rigor —
   fora da lista ele não é "menos rigoroso", é invisível.
2. Um teste no molde do `SinglePortTests`: varrer a árvore e falhar em `write_text`,
   `write_bytes` e `open` para escrita fora de uma lista de exceções **declarada e comentada**,
   dizendo por que cada uma é exceção.
3. A varredura de `tkinter` passa a receber a lista explícita dos doze.
4. `streamlit` vira o extra `demo`, com o mesmo tipo de comentário dos outros quatro extras; e
   `pyarrow`, `onnx` e `onnxruntime` entram em `excludes` da `cvoff.spec`.
5. `route_distribution` é ligada onde o número seria lido — o relatório do `cvoff-audit`, ao
   lado da distribuição de classes que ele já imprime (`cli/audit.py:186-195`) — **ou**
   removida. Deixá-la solta é a única opção que não serve, porque a pergunta que a coluna
   existe para responder ("as amostras corrigidas à mão treinam melhor?") continua sem ninguém
   que a faça.

**Critério de aceite.** `mypy` cobre `app_tkinter.py`; um `write_text` novo fora da lista faz a
suíte falhar; os doze módulos sem Tk estão na varredura; `uv sync` sem extras não instala
`streamlit`; a distribuição por rota aparece no `cvoff-audit` ou a função sai.

**Testes.** `tests/test_atomic_io.py` — a varredura da árvore. `tests/test_viewport.py` — a
lista dos doze. `tests/test_environment.py` — `streamlit` ausente não quebra nada em `src/`.
