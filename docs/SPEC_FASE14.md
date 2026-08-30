# Especificação das melhorias — Fases 14 a 19 (S-95 a S-142, S-219)

Base: [ROADMAP_FASE14.md](ROADMAP_FASE14.md), que traz a avaliação de 2026-08-16 e o
sequenciamento. Continuação de [SPEC_FASE7.md](SPEC_FASE7.md) (S-37 a S-75),
[ANALISE_DETECCAO.md](ANALISE_DETECCAO.md) (S-78 a S-82) e
[PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md) (S-83 a S-94).

> **Onde mora a spec de cada item (S-NN).** A spec deste projeto está espalhada por cinco
> arquivos, e essa dispersão custou duas entregas — a S-76 e a S-77 ficaram três meses em
> documento nenhum (corrigido na S-133). `tests/test_docs.py` confere esta tabela contra o
> disco (S-134): item entregue sem seção e seção no arquivo errado fazem a suíte falhar.
>
> | itens | arquivo |
> |---|---|
> | S-01 a S-36 | [SPEC.md](SPEC.md) |
> | S-37 a S-77 | [SPEC_FASE7.md](SPEC_FASE7.md) |
> | S-78 a S-82, S-143, S-175, S-176, S-452 | [ANALISE_DETECCAO.md](ANALISE_DETECCAO.md) |
> | S-83 a S-94 | [PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md) |
> | S-95 a S-142, S-171 a S-174, S-218, S-219 | [SPEC_FASE14.md](SPEC_FASE14.md) |
> | S-144 a S-170, S-177 | [SPEC_UI.md](SPEC_UI.md) |
> | S-178 a S-217 | [SPEC_TEXTO.md](SPEC_TEXTO.md) |
> | S-220 a S-234, S-294, S-295, S-324 | [SPEC_APARENCIA.md](SPEC_APARENCIA.md) |
> | S-235 a S-267, S-291 a S-293 | [SPEC_EDITOR.md](SPEC_EDITOR.md) |
> | S-268 a S-290 | [SPEC_ESTUDO.md](SPEC_ESTUDO.md) |
> | S-296 a S-323, S-325 a S-430, S-451, S-453 (menos S-324) | [SPEC_REVISAO.md](SPEC_REVISAO.md) |
> | S-431 a S-440 | [SPEC_REVISAO_EXTERNA.md](SPEC_REVISAO_EXTERNA.md) |
> | S-441 a S-450 | [SPEC_ACABAMENTO.md](SPEC_ACABAMENTO.md) |

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

## S-99 · Crescer o conjunto: 60 páginas, cinco regimes, FEN conferida ✅ **fechada** (2026-08-22)

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

### O fechamento (2026-08-22): 66 páginas, e a régua passou a separar modelos

**Os quatro critérios de aceite, medidos:**

| critério | alvo | medido |
|---|---|---|
| páginas revisadas | 60 | **66** ✅ |
| `comparable` | ≥ 30 | **96** ✅ |
| diagramas na faixa 0,60–0,80 | ≥ 5 | **6** ✅ |
| cinco regimes no alvo | — | ✅ (abaixo) |

| regime | antes | alvo | **agora** |
|---|---|---|---|
| `scan-puro` | 6 | 15 | **19** |
| `scan-hachurado` | 5 | 12 | **13** |
| `vetorial` | 3 | 12 | **12** |
| `fonte` | 1 | 6 | **6** |
| `sem-diagrama` | 4 | 15 | **16** |
| **total** | **19** | **60** | **66** |

O conjunto passou de 40 para **115 diagramas anotados** e de 10 para **30 livros**: as páginas
novas vieram de 20 livros que não estavam nele — inclusive os dois que exportavam zero, que a
spec pedia por nome.

**O número da produção sobre o conjunto novo** (`docs/metrics/field_20260822_s99.json`):

```
    Páginas ...................... 66  (17 sem diagrama)
    Anotados ..................... 115
    Recall de detecção ........... 0.9478     precisão 0.9909  (1 falso positivo)
    **Taxa de exportação** ....... 0.7652  (88/115)
    Conferíveis .................. 96 de 115  (83%)
    **Exatidão de campo** ........ 0.9882  (84/85 exportados)
    Exatidão condicional ......... 0.9583  (92/96)
    **Exportados e errados** ..... 1
```

> **O arquivo citado foi remedido em 2026-08-25**, e o bloco acima é o que ele dizia sobre as 66
> páginas. O conjunto passou a 68 — duas folhas sem diagrama do `Kemeri` —, e o que se moveu foi
> só a detecção: 112 detectados, **3 falsos positivos** e precisão **0,9732**. Recall, taxa de
> exportação, conferíveis, exatidão de campo e condicional ficaram idênticos, porque as duas
> folhas novas não têm diagrama nenhum a ler. Os quatro relatórios correntes se moveram juntos,
> que é o que se espera de detecção: ela não depende do modelo.

**O achado que justifica a S-99 inteira: a exatidão de campo deixou de ser 1,0000.** O conjunto
de 19 páginas dizia que a produção nunca exporta errado. O de 66 achou o contrário, e é um caso
que nenhuma quantidade de páginas fáceis encontraria:

> `Dvoretsky p450`, diagrama 16-92. O modelo lê a posição **girada 180°** (a S-13 escolhe a
> orientação, e escolheu a errada) e, dentro dessa orientação, troca dois peões por torre e
> dama. Confiança mínima **0,9647** — bem acima do gate de 0,80. Sai para o PGN, é legal, e
> está errada.

**E a régua passou a separar os modelos, que era o motivo declarado da 7.7.** Os quatro
medidos sobre as mesmas 66 páginas:

| | produção | **controle** | `mhsp` | tratamento S-108 |
|---|---|---|---|---|
| taxa de exportação | 0,7652 | **0,7913** | 0,7304 | 0,7478 |
| `exact` (de 96) | **92** | 89 | 85 | 91 |
| exatidão condicional | **0,9583** | 0,9271 | 0,8854 | 0,9479 |
| exportados e errados | 1 | **0** | 1 | 1 |
| exatidão de campo | 0,9882 | **1,0000** | 0,9878 | 0,9880 |
| exportação limpa | 0,7453 | **0,7736** | 0,7075 | 0,7358 |

Três leituras deste quadro, e as três são novas:

1. **O veredito da S-107 (`não promover o mhsp`) fica confirmado com régua que enxerga.** Ele é
   o pior nas cinco linhas. Antes ele era indistinguível.
2. **O controle exporta mais e não erra nenhum.** Produção e controle erram diagramas
   *diferentes*: a produção quebra no `Dvoretsky p450` (orientação), `mhsp` e o tratamento da
   S-108 quebram no `Burgess p60` — a dama **preta** em e5 lida como branca, com 0,998 e 0,901
   de confiança. O controle não erra nenhum dos dois. **A decisão de 2026-08-18 de não trocar
   o modelo de produção pelo controle foi tomada sobre o conjunto de 19 páginas, em que a
   diferença era "um diagrama sem FEN de referência". Sobre 66 páginas a diferença existe, e a
   decisão volta a ser do dono do acervo.**
3. **A faixa 0,60–0,80 encheu com página nova, e não com modelo novo.** São 6, em quatro
   livros diferentes (`Neumann` ×3, `Gunderam`, `Burgess`, `Euwe Band 7`) — todos scans ou
   fontes de impressão antiga. A rota que a S-108 abriu (domínio aprendido cria vizinhança de
   corte) e a rota original (faltam páginas difíceis) valem as duas.

### Os quatro relatórios foram remedidos em 2026-08-23, e o motivo é a própria S-100

**O que estava errado.** O commit de 22/08 diz "63 páginas, 110 diagramas", e é o número que
os quatro relatórios declaram. O `data/field_set.jsonl` que ele commitou tem **65 páginas e
112 diagramas**: duas páginas do Yusupov (`p2`, sem diagrama, e `p11`, com dois) foram
anotadas **depois** da medição e entraram no mesmo commit. A guarda da S-100 pegou exatamente
isso — que é para o que ela existe — e foi só ela que pegou. A terceira, a `p14`, foi anotada
em 23/08, e a seção abaixo é sobre ela.

**O que a remedição mudou, e o que não mudou.** Os quatro modelos foram medidos de novo sobre
as 66, com o mesmo código commitado; os números acima já são os novos. O deslocamento é todo
das três páginas do Yusupov que faltavam ser medidas:

**Duas causas se moveram, e a tabela as separa de propósito.** Entre o relatório de 22/08 e o de
hoje mudaram o **conjunto** (63 → 66 páginas) e o **código** (a S-176, commitada no 9eb6685).
Somar as duas numa coluna só seria repetir o defeito que esta seção inteira documenta, então
aqui estão as três medições, todas da produção:

| | 63 pág., código de 22/08 | 66 pág., código de 22/08 | 66 pág., **hoje** (S-176) |
|---|---|---|---|
| anotados | 110 | 115 | 115 |
| detectados | 104 | 109 | **110** |
| casados | 103 | 106 | **109** |
| falsos positivos | 1 | 3 | **1** |
| recall de detecção | 0,9364 | 0,9217 | **0,9478** |
| precisão de detecção | 0,9904 | 0,9725 | **0,9909** |
| exportados | 82 | 85 | **88** |
| `comparable` | 93 | 94 | **96** |
| `exact` | 89 | 90 | **92** |

Lendo por coluna: **o conjunto** acrescentou 5 diagramas e 3 páginas e fez o número **piorar** —
recall de 0,9364 para 0,9217, precisão de 0,9904 para 0,9725 — porque as páginas novas trouxeram
um defeito que o conjunto antigo não continha. **O código** então o consertou, e devolveu mais do
que o conjunto tinha tirado. As duas colunas do meio e da direita medem o mesmo conjunto; a
diferença entre elas é inteiramente a S-176.

**Nenhuma leitura do quadro dos quatro modelos muda em nenhuma das três colunas**: as três
conclusões acima valem, porque a parte que decide correção — exatidão condicional, exportados e
errados, exatidão de campo — mantém a mesma ordem entre os modelos. O `mhsp` é o pior nas cinco
linhas, o controle é o único que não exporta errado, e a produção lê certo mais diagramas no
total. O que se moveu foi denominador e detecção, não veredito.

### A `p14` do Yusupov, e o defeito de detecção que ela mede

**Ela quase entrou como `sem-diagrama`, e tem três diagramas** (1-9, 1-10, 1-11). Assim teria
transformado dois diagramas reais em falsos positivos e publicado precisão 0,9633 — o defeito
da S-95 visto do outro lado: ali uma leitura alucinada servia de referência, aqui uma página
cheia de diagramas afirmaria não ter nenhum. Comparar com a `p2`, do mesmo livro, mostra a
distinção: ela é capa da série, o detector lê um tabuleiro na arte a 0,177, e esse falso
positivo é **legítimo** — é exatamente para isso que página sem diagrama entra no conjunto.

**Como as três caixas foram anotadas.** Do detector de **contorno**
(`board_detection.detect_boards`), sobre a página rasterizada a 220 DPI, e conferidas desenhadas
sobre a página. Ele devolve os três, e devolve quadrados: `138,4×138,4`, `136,5×136,5` e
`139,1×138,4` pontos, todos com razão entre 1,0000 e 1,0047, alinhados na mesma coluna — do
mesmo tamanho das caixas já anotadas na `p11`, que é do mesmo livro.

**E as três FENs, com uma verificação que os outros diagramas do conjunto não têm.** Foram
transcritas do recorte a 960×960 com grade `a-h`/`1-8`, como manda o método acima. O que muda
aqui é que **a página publica a análise**, e ela depende da posição exata:

| | posição | o que a página afirma, e confere |
|---|---|---|
| 1-9 | `rb2r1k1/1p1b1ppp/p1nq4/3p4/3Nn3/1QB1PN2/PP2BPPP/2R2RK1`, pretas | `1...♘xd4! 2.♗xd4 ♘d2! 3.♕d1 ♘xf3† 4.♗xf3 ♕xh2#` — e o mate **existe** na posição transcrita, pelas duas rotas. Ele só funciona porque o bispo de `b8` defende `h2`: é a "queen-bishop battery" que o texto nomeia, e é o que fixa `b8` e `d6` |
| 1-10 | `5rk1/pp1nqrp1/2p3p1/4p3/4P1P1/1BP2P2/PP2Q3/3RK2R`, brancas | `1.♕h2`, e "Black has no defence against ♕h8#". Exige `h7` **vazia** e a torre em `h1` atrás da dama — a "queen + rook battery" do título da seção |
| 1-11 | `5rk1/qp1r2pp/1bpp1p1B/p1nPpP1Q/P1P1P3/2N4P/1P3P1K/1R4R1`, brancas | `1.♗xg7! ♖xg7 2.♖xg7† ♔xg7 3.♖g1† ♔h8 4.♕g4+−`, e a linha lateral `1.♖xg7† ♖xg7 2.♗xg7`. Ambas legais. O `4...♖f7` da ressalva exige `f7` vazia |

As três são legais para o `check_position`, que **infere sozinho o mesmo lado a jogar** que a
notação da página indica.

Quando foram escritas, só o 1-11 era casado pelo detector, e os outros dois ficaram de reserva.
A S-176 mudou isso no mesmo dia: **os três são casados agora, e os quatro modelos leem os três
certo.** O Yusupov sai de `comparable` 1 para 3 e de `exact` 1 para 3, e com isso
`enough_comparable` vira `True` — o livro deixa de ser só contagem de detecção e passa a ter base
de correção. A ressalva do erro correlacionado continua valendo entre mim e os modelos; a análise
impressa, essa, é independente dos dois.

**O defeito que ela mediu, e que durou um dia.** Anotada a página, o `cvoff-field` de 22/08 não
usava o contorno nela: usava a imagem embutida, e as imagens embutidas da `p14` são **fragmentos
de scan**, não diagramas. Media 2 detectados, 1 casado (o 1-11, IoU 0,76), 2 perdidos, e um falso
positivo que era o retângulo `(-9, 12, 451, 415)` — a faixa de topo do scan. O livro inteiro caía
para recall 0,500 e precisão 0,600, o pior do conjunto.

O `detection/__init__.py` já documentava a divisão — "a página inteira é um scan: uma imagem só,
cobrindo tudo" — e o Yusupov é um desses livros; o que ninguém tinha visto é que a `p14` tem o
scan quebrado em **três** imagens em vez de uma, e isso faz o caminho embutido parecer aplicável
quando não é.

**A S-176 fechou isso, e este caso é a evidência dela.** `is_page_band` e
`contour_inside_candidate` derrubam a faixa e deixam o contorno vencer. Medido no mesmo conjunto,
só trocando o código:

| Yusupov (4 páginas, 6 diagramas) | 22/08 | hoje |
|---|---|---|
| casados | 3 | **5** |
| falsos positivos | 2 | **1** |
| recall / precisão | 0,500 / 0,600 | **0,833 / 0,833** |
| `comparable` / `exact` | 1 / 1 | **3 / 3** |
| `enough_comparable` | `False` | **`True`** |

O falso positivo que **sobra** é o que deve sobrar: a arte de capa da `p2`, lida a 0,177. A S-176
matou as duas faixas fantasma sem matar a medição de falso positivo, que é a coisa que uma página
`sem-diagrama` existe para não deixar perder. Uma guarda que zerasse a coluna teria zerado junto a
capacidade de detectá-la. Confirmado por fora rodando `detect_diagrams` com e sem a guarda no
`GALLAGHER p124`: antes a única caixa da página era a faixa embutida de 308×274 pt, depois é o
diagrama de contorno de 119×120 pt.

**E o conserto é dirigido, o que é a parte difícil.** No `per_book`, os **outros 28 livros do
conjunto não se moveram em nenhum dos oito campos** — a mudança inteira está nas duas páginas que
tinham o defeito. É o que separa "a guarda consertou a `p14`" de "a guarda mexeu na régua
inteira", e sem o conjunto de campo não haveria como dizer qual dos dois aconteceu.

**O que fica de lição, e não é sobre detecção.** O defeito existiu por um dia inteiro, e nenhuma
guarda o teria achado. Ele só apareceu porque uma página nova foi anotada **contra a imagem** em
vez de contra a saída do modelo — e o que a anotação correta produziu, no primeiro momento, foi
um número **pior**. Uma régua que só melhora não está medindo.

### Como foi anotado, e o que eu errei

Cada diagrama foi renderizado do recorte **warpado** de 800×800 — o mesmo que o modelo vê — a
900×900 com grade `a-h`/`1-8`. A posição foi transcrita **antes** de abrir a leitura do modelo,
que ficava num JSON à parte. Onde houve divergência, a casa em disputa foi recortada a 200×200
e comparada com uma peça branca e uma preta do mesmo diagrama.

**Errei 5 diagramas em ~70 transcritos (~7%)**, e todos os cinco foram erros de *leitura em
recorte pequeno*, não de peça ambígua:

| diagrama | meu erro | como se resolveu |
|---|---|---|
| `Dvoretsky p700` | torre em f6 (era g6), peão em e4 (era f4) | recorte de 900×900 |
| `Chess Structures p50` (dois) | esqueci a torre em c1 nos dois; cavalo em g6 (era f6) | recorte de 900×900 |
| `Estrin p40` | esqueci o peão branco em g4 | o texto da página traz `14. g4` |
| `Burgess p60` | dama de e5 lida como branca (é preta) | recorte de 200×200 por casa |

E **o modelo errou dois que eu peguei**: `Dvoretsky p450` (a rotação acima) e `Levenfis p150`,
onde ele troca rei e dama de casa em d1/g1 — este barrado em 0,108, aquele exportado a 0,965.
Nos dois casos a referência ficou com a minha leitura, conferida no recorte grande.

**A ressalva do erro correlacionado continua valendo**: nos diagramas em que eu e o modelo
concordamos de primeira, um erro comum aos dois não aparece. O conjunto é mais forte que a
saída do modelo — foi lido por gente contra a imagem, e 17 dos 110 estão anotados **só com a
caixa** porque a hachura não deixava separar 64 casas com segurança — mas não é verdade
independente no sentido estrito.

### Duas coisas que apareceram no caminho, e não são desta spec

**1. `evaluate_field` engole "arquivo não existe" e devolve isso como recall.** O laço tem um
`except Exception` que transforma qualquer falha de leitura em "não detectou nada"
(`field_eval.py:655`). Em 2026-08-22, 11 páginas entraram com o nome do PDF em codificação
dupla (`Eröffnungswege` → `ErÃ¶ffnungswege`), os arquivos não abriram, e o relatório daquele dia
saiu com **recall 0,7596** em vez dos **0,9364** que o código de então valia — sem nada além de
um `WARNING` que diz a mesma frase que uma página legitimamente vazia diz. Um nome errado tem de
derrubar a medição, não baratear o número.

> **Corrigido em outra branch, ainda aberto aqui — e o merge tem de trocar este parágrafo.** O
> commit `6370a7c` (PR #6, branch `claude/competent-vaughan-d2bf5e`, que sai da `main`) fecha
> exatamente isto: só
> `NoBoardDetectedError` continua virando zero detectados, qualquer outra exceção derruba a
> medição com caminho, página e causa, e os PDFs das páginas revisadas são conferidos **antes**
> da primeira leitura — nomeando a pasta e, quando existe lá um arquivo que só difere pela
> codificação do nome, qual é ele. O `cvoff-field` sai com código 2 em vez de publicar um número
> mais barato.
>
> **Cuidado com o número ao fazer o merge: `S-219` foi usado duas vezes, para coisas
> diferentes.** Lá é este conserto do `except Exception`; aqui é o item de procedência no JSON,
> mais abaixo neste mesmo arquivo. Duas sessões escolheram o número lendo cada uma o disco do
> próprio worktree. Por isso o parágrafo acima aponta o **commit**, e não o número.
>
> Enquanto os dois lados não se encontrarem, aquela branch tem o defeito fechado e este documento
> diz que está aberto. **O `test_docs` confere presença de seção, não se o que a seção afirma ainda é
> verdade** — é a mesma família de buraco da S-100, que confere identidade de conjunto e não de
> código. Os números `0,7596` e `0,9364` acima são de 2026-08-22 e **não retroagem**: o
> `0,9478` de hoje é pós-S-176, e trocar um pelo outro faria o parágrafo afirmar que o pipeline
> já valia isso antes da mudança que o levou até lá.

**2. O relatório de campo não grava com que modelo foi medido.** Os quatro JSON de 2026-08-22
só se distinguem pelo nome do arquivo. A comparação do quadro acima depende de quem gravou
lembrar o que rodou.

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

## S-219 · O relatório diz com que código e com que modelo foi medido ✅ implementada (2026-08-23)

> Acrescentado à Fase 14 depois de ela fechar, e mora aqui porque é a outra metade da S-100 —
> não ao lado do número da numeração. Nasceu de um incidente de 2026-08-23, descrito abaixo.

**Problema.** A S-100 declarou o **conjunto** e travou a comparação nele. Faltam as outras duas
entradas de uma medição de campo: **o modelo** e **o código**. Nenhuma das duas era gravada, e o
custo apareceu inteiro no mesmo dia.

Primeiro o barato: os quatro JSON de 2026-08-22 só se distinguiam **pelo nome do arquivo**.
Identificar qual modelo gerou cada um custou meia hora, rodando candidatos até reproduzir bit a
bit — arqueologia para responder uma pergunta que o arquivo devia responder sozinho.

Depois o caro, que a arqueologia desenterrou: os quatro tinham sido medidos com **código de
gerações diferentes**, metade antes e metade depois da S-176. O estado publicado era este:

| relatório | detected | matched | false_positives | recall |
|---|---:|---:|---:|---:|
| `field_20260822_s99` | 109 | 106 | 3 | 0,9217 |
| `controle_20260822` | 110 | 109 | 1 | 0,9478 |
| `mhsp_20260822` | 110 | 109 | 1 | 0,9478 |
| `s108_20260822` | 110 | 109 | 1 | 0,9478 |

**Detecção não depende de modelo.** Um quarteto que discorda nessas quatro colunas é impossível
numa medição sã, e é a assinatura de que foram medidos com código diferente — e **nada avisava**.
A guarda da S-100 não pega: ela compara `pages` e `annotated`, e mudança de código não move
nenhum dos dois.

**Solução.** `field_eval.measurement_fingerprint`, gravada pelo `cvoff-field --json` como
`measured_with`. Três decisões, e cada uma responde a uma forma de a impressão ser inútil:

**1. O digest de código sai de um fecho de importação, e não de uma lista.** Calculado por `ast`
a partir de `cli/field.py` — o CLI, e não `field_eval`, porque é ele que monta o conjunto e fixa
`dpi`, `accept-threshold` e `max-boards`. O fecho pega hoje 29 módulos, entre eles
`detection/hybrid.py` (o defeito com data), `field_eval.py` (que decide o casamento e o portão),
`decode.py` (que entra no `exact`) e o próprio `cli/field.py` — e pega sozinho o módulo que
alguém puser no caminho amanhã. **Uma lista escrita à mão pegaria o defeito de hoje e deixaria
passar o de amanhã**, e um digest que passa batido é pior que digest nenhum, porque quem lê
confia nele.

**2. O motor desligado fica fora do fecho, e o motor usado sai gravado.** `--ocr` nasce `off`, e
o classificador de glifo é alcançado por um import tardio dentro de `ocr.build_recognizer` —
deliberado, e o comentário lá diz que é o ponto. Código que não rodou não pode ter mudado o
número. Digerir o `text/` inteiro deixaria a guarda vermelha o tempo todo enquanto a Fase 26
mexe nele várias vezes por dia, e **uma guarda que grita sempre é apagada**. O que mantém a poda
honesta é o motor sair no relatório: uma corrida com `--ocr glifo` digere o `text/` junto, e
sobem de 29 para 35 os módulos cobertos.

**3. Um digest por módulo, e não um só.** Um hash agregado diz *que* mudou e nunca *o quê* — e
bissectar isso à mão foi a meia hora. Com o mapa, a guarda nomeia o módulo que se moveu.

O modelo entra **por conteúdo** e não por nome (`sha256` do arquivo): copiar
`piece_classifier.pt` para `controle_20260816.pt` não faz dois modelos, e foi o nome ser a única
coisa a distinguir os quatro que criou o problema. O código entra por **nome e conteúdo**, que é
o oposto e pelo motivo oposto: renomear `hybrid.py` muda o que roda tanto quanto editá-la.

**E o `path` sai relativo à raiz quando o modelo mora dentro dela.** O padrão do `--model` chega
já resolvido de `PROJECT_ROOT` e o valor passado à mão chega como foi digitado, então a primeira
publicação destes quatro saiu com **um absoluto e três relativos** — mesmo comando, mesma
máquina. O dano menor é publicar o layout do disco de quem mediu num repositório público; o
dano real é que o mesmo modelo medido em duas máquinas daria `path` diferente com `digest`
igual, e **`path` é o campo que se lê primeiro**. Fora da árvore continua absoluto, e aí não é
ruído: é a informação de que o modelo não mora no repositório.

> **Um limite conhecido:** caminho relativo é resolvido contra o **diretório de trabalho**, e não
> contra a raiz. É assim que o `--model` de fato abre o arquivo; normalizar contra a raiz faria o
> relatório declarar um arquivo diferente do que foi lido para quem rodasse de outro diretório.

**O caso que decidiu isso tem nome e dois arquivos.** `models/s108_20260821.pt` e
`models/controle_s108_20260821.pt` têm **exatamente 8.786.392 bytes** e nomes quase iguais — a
leitura natural é que um é cópia do outro. Medidos, os `sha256` diferem: são **modelos
diferentes**, e o tamanho idêntico era pista da *arquitetura* comum, não de duplicata. Um deles
gerou o `exact` 91 publicado, e até aqui a única forma de saber qual era ler o comando na
mensagem de um commit. É a mesma informação que já se perdeu uma vez.

**4. Uma nota que viaja com o arquivo.** `--nota` grava texto livre em `measured_with.note`, para
o que nenhum digest captura. O caso que a criou é a condição da máquina, e ele tem números:

| corrida | `seconds` | máquina |
|---|---|---|
| as três gerações anteriores destes quatro | 84 a 113 | nove sessões, treino em curso |
| a desta entrega | **57,7 a 64,3** | ociosa, e as quatro em sequência |

São **~40%**, e não ruído de medição. O estrago concreto: o `controle` marcava 113 s e parecia
*o modelo mais lento do quarteto* — era a máquina ocupada. Um leitor futuro compararia modelos
por um número que media outra coisa, e a queda desta entrega passaria por ganho de código. A
ressalva normalmente acabaria na mensagem do commit, que **não viaja junto com o JSON** — e é o
JSON que alguém abre daqui a um mês.

Por isso os quatro foram medidos **um de cada vez**: quatro corridas simultâneas disputariam
entre si e reintroduziriam exatamente o que a nota existe para denunciar.

`dirty` fica ao lado do `commit` porque nesta árvore quase nunca há commit limpo — nove sessões
escrevem nela ao mesmo tempo. Um relatório medido com a árvore suja é indistinguível de um medido
no commit se só o `commit` for gravado; quem decide é o `code.digest`, e o `commit` serve para
achar a vizinhança.

> **Isso deixou de ser argumento e virou episódio, durante a própria medição deste item.** Outra
> sessão commitou entre a primeira e a segunda das quatro corridas, e os relatórios saíram assim:
>
> | corrida | `commit` | `code.digest` |
> |---|---|---|
> | produção | `76e5b042` | `19930ff018e78839` |
> | controle | `bc8b0bca` | `19930ff018e78839` |
>
> O commit mudou, o digest não — porque aquele commit tocou `.gitignore`, um documento e um JSON,
> e **nenhum módulo do caminho de medição**. Uma guarda que comparasse `commit` teria acusado dois
> relatórios corretos como incompatíveis, e a primeira coisa que se faz com uma guarda que acusa
> à toa é desligá-la.

**O defeito que o próprio item quase teve.** A primeira versão do fecho resolvia
`from .hybrid import ...` dentro de `detection/__init__.py` para `chess_diagram_ocr.hybrid`, que
não existe — e **`detection/hybrid.py`, o módulo cuja mudança motivou este item, ficava de fora
do digest**. Passava em tudo e não guardava nada. Dentro de um `__init__.py` o pacote é o próprio
módulo, e não o pai; `test_o_pacote_do_init_resolve_para_ele_mesmo` existe para isso.

**Critério de aceite.**

- ✅ o relatório grava modelo (caminho + digest de conteúdo), `commit`, `dirty`, motor de OCR e o
  digest do código, com a lista de módulos por extenso;
- ✅ o fecho alcança `detection.hybrid`, `detection.embedded`, `field_eval`, `decode`,
  `cli.field`, `service` e `model`;
- ✅ o fecho **não** alcança `ui/` — mudança de botão não obsoleta uma medição;
- ✅ **a suíte falha** quando um módulo do caminho mudou desde que o relatório corrente foi
  gravado, nomeando qual. É a metade que dá trabalho e é a que importa: gravar sem conferir
  deixaria o mesmo buraco, só que documentado;
- ✅ os quatro relatórios correntes remedidos, carregando a impressão, com os números
  reproduzindo os de `c640012` antes de publicar.

## O balanço do primeiro dia, e o que ele diz sobre o desenho

A guarda disparou **três vezes em 2026-08-23**, e nas três o defeito era real e ninguém tinha
percebido. Os quatro relatórios foram remedidos **quatro vezes** no total.

| # | o que mudou | quem escreveu a mudança |
|---|---|---|
| 1 | `--nota` entrou no `cli/field.py` | quem escreveu a guarda |
| 2 | `_model_path_relativo` no `field_eval.py` | quem escreveu a guarda |
| 3 | `caminho_para_relatorio` no `config.py` | **outra sessão** |

O terceiro é o que importa, por dois motivos. É o primeiro contra quem **não** escreveu a guarda
— o teste que só pega o próprio autor não é guarda, é lembrete. E a mudança era **inerte para a
medição**: acrescentou uma função e não alterou nenhum caminho executado. O digest é por
conteúdo e não tem como saber disso, então venceu os quatro relatórios de qualquer forma.

**Ser conservador aqui é o comportamento certo, e o custo é conhecido: um minuto por modelo.**

**O que sustenta isso é a ausência de escape, e não a disciplina de quem edita.** A guarda não
tem `# noqa`, não tem lista de módulos isentos e não tem limiar a afrouxar. Para uma mudança
inerte parar de acusar, seria preciso **mover a função para um módulo pior** — `config.py` é o
lugar certo para uma função sobre `PROJECT_ROOT` — e isso se vê que é errado sem precisar de
virtude nenhuma. É a diferença entre um desenho e um pedido: **uma guarda que oferece escape
será escapada**, e a alternativa a projetá-la sem escape é confiar na disciplina de quem edita,
que é a coisa que nunca funciona.

> Este parágrafo dizia outra coisa quando foi escrito: creditava à sessão que caiu na guarda a
> *decisão* de pagar em vez de contornar. Ela corrigiu — não houve decisão, porque não havia
> opção. A distinção não é modéstia: registrada errado, a lição vira "confie em quem edita", e
> a próxima guarda nasce com uma saída de emergência que alguém vai usar.

**A sequência que se repete, e vale como regra:** mexer no código depois de medir invalida os
quatro. Fechar o código **antes** de medir para publicar — medir custa um minuto, publicar
arquivo vencido custa a confiança no arquivo.

**E o defeito que a guarda não pegou foi achado por leitura humana.** O `path` absoluto não entra
em digest nenhum, então nenhuma verificação automática o alcançaria; quem o achou foi outra
sessão relendo um arquivo já publicado. As duas metades juntas são o argumento do item: a guarda
pega o que muda por baixo, e não substitui alguém olhando o que ficou escrito.

**São duas famílias de defeito, e precisam de dois instrumentos.** O digest cobre **deriva** —
o número certo que envelheceu porque o código mudou por baixo. O caminho absoluto é a outra
família: **o valor certo gravado errado desde a origem**. Ele não envelhece, não vence, e
nenhuma remedição o revela — comparar *hoje* com *quando foi gravado* dá igual, porque sempre
esteve errado. Nove arquivos estavam assim em 2026-08-23, quatro deles já no remoto.

Contra essa família vale um teste de **forma**, e ele é barato:
`test_docs.py::CaminhoPublicadoTests` varre `docs/metrics/*.json` e recusa caminho absoluto
dentro da raiz em campo de caminho. Duas decisões o mantêm vivo:

- **Olha campos de caminho, não toda string.** Medido: `texto_treino_20260823_s204.json` traz
  `{"pasta": "sym_47", "caractere": "/"}` — o `/` é o **glifo da barra**, uma classe do
  classificador. Uma regra de "string que começa com barra" acusaria dado legítimo, e guarda que
  acusa à toa é desligada.
- **Absoluto fora da raiz passa.** Ali o caminho é informação, não ruído.

E ele mora nos testes de propósito: `tests/` não está no fecho de importação, então esta guarda
**não vence relatório nenhum** — verificado, o `code.digest` seguiu `e0a6c677499bccff` depois
dela. É o raro caso em que a cobertura sai de graça.

**O que este item deliberadamente não faz.** Não adivinha quais módulos do fecho uma corrida
executou de fato — só a poda do motor desligado, que é decidível. Um digest condicionado ao que
rodou seria mais justo e é exatamente por onde um digest passa batido.

**Testes.** `test_o_fecho_alcanca_quem_move_o_numero`;
`test_o_pacote_do_init_resolve_para_ele_mesmo`; `test_a_interface_nao_invalida_uma_medicao`;
`test_o_motor_desligado_fica_fora_do_digest`;
`test_a_impressao_muda_quando_um_modulo_medido_muda`;
`test_o_modelo_entra_por_conteudo_e_nao_por_nome`;
`test_modelo_ausente_nao_derruba_a_impressao`;
`test_todo_relatorio_corrente_declara_com_que_codigo_mediu`;
`test_todo_relatorio_corrente_mediu_o_codigo_de_hoje`.

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

### O que foi entregue (2026-08-21)

**80 amostras, 40 de cada livro, com procedência completa.** Os dois livros saíram de **0**
rótulos para 40 cada; `labels.csv` foi de 4.098 para 4.178 linhas, `corrected_by` =
`transcricao-manual` nas 80, e **nenhuma delas cai numa página do conjunto de campo** — a
medição de antes/depois que o critério pede nasce limpa por construção (Euwe rotula as páginas
11–80, o campo mede 25/62/100; Gallagher rotula 6–43, o campo mede 80/124).

**A premissa da spec estava velha, e isso muda o custo do item.** Ela manda coletar *"pelo
caminho de seleção de área da S-20, que funciona mesmo quando o detector falha"*. O detector
não falha mais: `cvoff-census --all-pages` acha **80 candidatos no Euwe** (100% imagem
embutida, todos aparados pela moldura) e **198 no Gallagher** (87,9% contorno). A coleta não
precisou de um único arrasto de mouse.

**Triagem antes de rotular.** `board_checker_score` -- o gate da S-12 -- separa candidato de
página de texto sem tocar em tabuleiro nenhum: no Gallagher **5 dos 198 pontuam exatamente
0,0000** (o índice do livro, o *Index of Variations* e três páginas de texto corrido) contra
0,2891 do menor tabuleiro real; no Euwe o mínimo é 0,7414 e não há falso positivo. Os 5 ficaram
de fora, e com eles o `#170`, que é tabuleiro real com recorte desalinhado.

#### O "antes" que faltava, e ele reformula o item

O item nasceu de *"os dois livros exportam 0/2"* e tratava os dois como o mesmo problema. Com
verdade de referência nos 80, medido contra o modelo de produção:

| | casas certas | tabuleiros inteiros | confiança mínima (mediana) |
|---|---|---|---|
| **Euwe** | 0,9402 | **2 de 40** | **0,0006** |
| **Gallagher** | **0,9973** | **33 de 40** | 0,7522 |

**Os dois exportam zero por razões opostas.** No Euwe o modelo não lê. No Gallagher ele lê
quase perfeito e o **gate** barra: 15 dos 40 são lidos com as 64 casas certas e ficam abaixo de
0,80 -- recall puro, com **zero** exportado errado. Um retreino que ganhe confiança sem ganhar
leitura já move o Gallagher; só o Euwe precisa de domínio novo.

**E há exportado-errado neste domínio, que o conjunto de campo não via.** Três tabuleiros do
Euwe passariam o gate com leitura errada, confiança **0,89 a 0,98**, sempre a mesma troca:
bispo branco lido como peão. O `field_eval` reporta `exportados e errados = 0` porque mede 2
diagramas deste livro; sobre 40 o número é 3.

**A lacuna é de vocabulário, não de margem.** Nas 88 casas de bispo do Euwe o modelo dá à
classe bispo probabilidade **0,0000** -- não é segunda opção fraca, é ausência. A prova que não
depende da minha leitura: no `euwe#001`, posição de abertura com a fila de trás inteira, `c1` e
`c8` **são** os bispos de dama por regra do jogo, e o modelo dá zero aos dois. Nenhum ajuste de
gate alcança isso, e é exatamente a hipótese que a S-40 tentou cobrir com hachura sintética.

#### O método da transcrição, e a taxa de erro dele

Quatro fontes, nesta ordem, e **as quatro acharam coisa diferente**:

| fonte | o que pegou |
|---|---|
| legalidade (S-17), testando os dois lados | posição impossível |
| contagem de material, com bispos por cor de casa | **4 erros** -- dois bispos de casa escura |
| discordância do modelo, ordenada por confiança da casa | **1 erro** que as duas guardas deixaram passar |
| folha de contato a 4×, as 102 chamadas de bispo uma a uma | **6 erros** |
| base de partidas, 10.355.488 jogos | **fechou o laço**: 4 não-confirmações eram erro meu |

**Doze casas erradas em 80 tabuleiros -- 10 tabuleiros, 0,23% das 5.120 casas** -- e onze delas
na mesma direção e na mesma peça: chamei bispo o que era peão. A troca preserva legalidade e,
quando as cores de casa fecham, preserva a contagem de material -- por isso as guardas baratas
não bastam aqui, e por isso a auditoria casa a casa foi feita.

**A décima segunda é a mais instrutiva, porque eu errei duas vezes seguidas na mesma casa.** O
`d6` do `euwe#041` eu li primeiro como cavalo; a folha de contato contra um peão da mesma
página me convenceu de que era peão; e só a comparação contra **bispos confirmados pela base em
casa hachurada** (`012 d6`, `013 c5`, `029 e6`) mostrou o que era: bispo. Duas lições, e as
duas valem para quem anotar o resto do acervo:

- **referência de uma peça só decide entre duas.** Comparar o disputado contra um peão responde
  "é peão?", não "o que é?". O gabarito precisa das três peças plausíveis lado a lado.
- **a referência tem de vir de casa da mesma cor.** O mesmo bispo em casa clara e em casa
  hachurada não se parecem: a trama come o contorno e muda a silhueta aparente.

A confirmação que sobrou não veio de olhar melhor, veio da aritmética: com bispo em `d6` o
material fica **simétrico** -- os dois lados sem os dois cavalos e sem dois peões --, e nem a
leitura de cavalo nem a de peão fechavam assim. **E a base decidiu**: com o bispo, a posição
existe em 91 partidas (`Forgacs x Caro, Coburg 1904`, lance 11); com cavalo ou com peão, em
nenhuma. As três leituras foram à base e só uma voltou.

**A triagem inversa também foi feita, e não achou nada.** A auditoria de bispo só cobre as
casas em que eu *disse* bispo; o erro oposto -- bispo lido como peão -- é invisível para ela e
para o modelo, que dá zero à classe. O crivo foi a altura da tinta: toda casa preta que eu li
como peão ou cavalo e que mede acima de 0,62 de altura entrou numa lista de 25, e as 25 se
explicam (cavalo de verdade mede 0,62--0,81) ou já estavam confirmadas por teoria de abertura.

**A base de partidas é a única fonte independente, e ela se provou.** **75 das 83** colocações
existem numa partida real; **30 delas em exatamente uma** partida entre 10,4 milhões, que é uma
impressão digital de 64 casas -- uma leitura errada não acerta isso por acaso. Melhor ainda:
`euwe#008`, `euwe#009`, `gallagher#008` e `euwe#041` **não** confirmavam antes das correções e
passaram a confirmar depois. As 8 restantes foram reconferidas casa a casa contra o recorte e
estão certas: são posição de análise -- variante que o livro mostra e ninguém jogou --, o que
num livro de Gambito do Rei é metade do conteúdo.

**Ausência da base não é evidência de erro, mas está longe de ser ruído**: das 13
não-confirmações observadas nas quatro passadas, **4 eram defeito meu**. É sinal fraco e caro de
investigar (~25 min por passada), e vale a pena mesmo assim -- foi ele que encontrou o único
erro que sobreviveu a todas as outras guardas.

**O custo é por varredura, não por posição** (S-73), e é isso que torna o método viável: as
quatro passadas custaram o mesmo que teriam custado para uma colocação só.

#### O que o conjunto de campo passou a medir

`comparable` foi de **33 para 36** com as três FEN das páginas de campo dos dois livros
(`Euwe p25`, `Euwe p100`, `GALLAGHER p80`), as três confirmadas pela base. A exatidão
condicional caiu de `1,0000` para **`0,9444`** -- e a queda é o instrumento funcionando: os dois
diagramas do Euwe que o modelo lê errado agora **aparecem**, onde antes eram invisíveis por
falta de referência.

| por livro | exportação | conferíveis | exatidão de campo |
|---|---|---|---|
| `Euwe` | 0,0000 (0/2) | 0 → **2** | — (nada exportado) |
| `GALLAGHER` | 0,5000 (1/2) | 0 → **1** | — → **1,0000** |

#### O "depois": o experimento rodou, e a hipótese passou

O dedupe e o `--drop-missing` foram autorizados em 2026-08-21 e rodaram com registro
(`docs/metrics/dedupe_20260821_072042.json`): 4.177 → 3.733 rótulos, 444 duplicatas, 1 sem
imagem para a quarentena, e o denominador que a S-101 existe para tornar visível -- `val`
401 → 358, `test` 393 → 369. **Nenhuma das 80 era duplicata.**

Dois modelos, mesma receita (`--fresh`, semente 42, 8 épocas, `aug0`, lote 128, lr 0,001), o
mesmo `splits.csv`, e **a única diferença sendo as 80 amostras**:

| | controle (3.653) | tratamento (3.733) |
|---|---|---|
| `Euwe` -- exportação | **0,0000** (0/2) | **0,5000** (1/2) |
| `Euwe` -- exatidão condicional | 0,0000 | **1,0000** |
| exportação limpa (geral) | 0,8065 (25/31) | **0,8387** (26/31) |
| exatidão condicional (geral) | 0,9444 (34/36) | **1,0000** (36/36) |
| exportados e errados | 0 | 0 |
| `val_board_exact_acc` | 0,975069 | 0,978082 |

**A hipótese era falsificável e não foi falsificada.** A spec dizia: *"se 80 tabuleiros reais de
domínio hachurado não moverem a exportação desses dois livros, a conclusão é que o problema não
é dado"*. Eles moveram. O livro que exportava zero exporta, **e certo**.

**O que custou, e está aqui porque custou.** O `1937 Kemeri p187` saiu do PGN: passava o gate no
controle e cai para **0,791** no tratamento. A taxa de exportação geral não muda (34/40 nos
dois) -- o Euwe ganha um e o Kemeri perde um. O que melhora sem contrapartida é a **leitura**:
`exact` 34 → 36, exatidão condicional 0,9444 → 1,0000, e a exportação **limpa** (a que exclui
páginas com amostra de treino) sobe de 0,8065 para 0,8387, porque a página do Euwe é limpa e a
do Kemeri não é.

#### O achado que não era deste item: a faixa da S-99 encheu sozinha

A distribuição de confiança do conjunto de campo, medida nos três modelos sobre as mesmas 19
páginas:

| faixa | produção | controle | **tratamento** |
|---|---|---|---|
| `[0,00, 0,20)` | 2 | 2 | **0** |
| `[0,60, 0,80)` -- **a faixa da S-99** | 0 | 0 | **2** |
| `[0,90, 1,00)` | 35 | 34 | 34 |

O critério da Fase 14 pede **≥ 5 diagramas na faixa 0,60--0,80**, e o ROADMAP atribui a faixa
vazia a *"faltam páginas difíceis"*. **As páginas são as mesmas nos três modelos.** O que
mudou foi o modelo: os dois diagramas que ficavam em 0,000 e 0,020 -- o Euwe -- subiram para o
gate, e um deles parou em **0,6519**; o `Kemeri p187` desceu de cima do corte para **0,7914**.

A faixa não estava vazia só por falta de página difícil. Estava vazia porque **o modelo não
tinha o vocabulário para ficar em dúvida**: onde o domínio era desconhecido ele errava com
0,999 de certeza, e onde era conhecido acertava com 0,999. Fechar a lacuna de domínio criou a
vizinhança do gate que a régua precisava.

Continua faltando para o critério: **2 de 5**. Mas a rota mudou -- não é só anotar mais página,
é também que cada domínio novo aprendido converte um par de extremos em vizinhança de corte.

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

### O corte 2, feito em 2026-08-18: os 46 ms viraram zero

`_reload_saved_diagrams` relia o `labels.csv` inteiro para descobrir o que a janela acabara de
escrever. Agora a `(página, diagrama)` gravada atravessa o `on_sample_saved` — que passou a
receber `Sequence[SavedSample]` em vez de nada —, e quem pinta de verde marca o que recebeu.
A aritmética mora em `labels.note_saved_diagram`, ao lado de `saved_diagrams_by_page`, e um
teste afirma que **as duas produzem o mesmo índice**: se divergirem, o sintoma seria a caixa
que só fica verde ao reabrir o livro, que é o defeito da S-71 de volta por um caminho que
ninguém procuraria.

**Medido nesta máquina, sobre o `labels.csv` de 3.936 linhas** e o livro com mais anotação do
acervo (Yusupov):

| | antes do corte 2 | agora |
|---|---|---|
| `LabelStore.read()` | 28,0 ms — e cresce com o arquivo | — |
| `load_annotations` do livro | 37,2 ms | — |
| `saved_diagrams_by_page` | 0,2 ms | — |
| `note_saved_diagram` | — | < 0,001 ms |
| **total por `Ctrl+S`** | **65,3 ms** | **0,000 ms** |

Os 46,1 ms que este documento publicava eram de um livro com anotação menor; a parcela de
`load_annotations` varia com o livro aberto, e a de `LabelStore.read()` com o `labels.csv`. As
duas somem, então a variação também.

**A sequência vazia é resposta, e não ausência.** Regravar a linha de uma amostra que já existia
(`REWRITE_ROW`) não faz diagrama nenhum ficar verde — ele já estava —, e é isso que `()` diz. O
"salvar todos" manda a lista inteira numa chamada só, como já fazia.

**O `load_annotations` saiu do `Ctrl+S` porque ele nunca deveria ter estado ali.** Ele lê as
anotações da galeria, que é onde mora `confirmed_from` — o violeta das caixas (S-75). Salvar
amostra não pode mudar confirmação nenhuma; o refresco vinha de carona, e por isso escolher uma
candidata na Galeria só acendia o violeta na *próxima* gravação de amostra. Agora quem muda a
anotação é quem avisa: `GalleryPanel._candidate_applied` chama `on_annotations_changed`, e a
janela relê ali. **Um defeito de comportamento consertado por um item de desempenho**, e fica
registrado porque só apareceu ao tirar a releitura do caminho errado.

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

## S-117 · A seta não executa dois painéis ao mesmo tempo ✅ implementada (2026-08-17)

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

## S-119 · Uma varredura por livro ✅ implementada (2026-08-18) em vez de duas

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

### O que foi entregue

A biblioteca saiu antes (`ReviewQueueBuilder`, com a equivalência já travada por teste); o que
fechou agora é a tela. `GalleryPanel.scan` passou a alimentar um `ReviewSink` pelo `on_scanned`
de `build_gallery_index`, e a aba de Revisão deixou de ter passada própria: o botão dela e o da
Galeria são o mesmo gesto, e o menu Ferramentas perdeu "Varrer a fila de revisão" — que era um
segundo comando com o custo inteiro do primeiro.

**O enunciado propunha derivar a fila do `GalleryIndex`, e isso não foi feito** — a razão está
no docstring do `ReviewQueueBuilder` e vale repetir aqui: o índice não é superconjunto da fila.
Ele guarda colocação, confiança mínima, legalidade e legenda; a prioridade da S-22 precisa de
`mean_entropy`, `uncertain_squares` e das casas que o decodificador reparou. Derivar dali daria
uma fila *parecida*, e o critério de aceite pede a **mesma**. Com o acumulador, os dois caminhos
passam pelo mesmo código de montagem e a equivalência é estrutural, não vigiada.

**Dois defeitos foram encontrados ao ligar as pontas, e os dois são de fusão de fila.**

1. **`merge_queues` usava `fresh` como a fila inteira**, então o que ela não tivesse
   desaparecia. Isso estava certo enquanto toda varredura era do livro inteiro, e deixou de
   estar com a varredura retomável da S-120: uma passada que lê só as páginas 300 a 420
   apagaria as pendências das 300 primeiras. Agora ela recebe `pages` — as páginas que a
   passada de fato visitou — e o que está fora sobrevive como estava.
2. **O mesmo defeito já existia no cancelamento**, e ninguém o tinha visto: cancelar uma
   revarredura na página 40 gravava uma fila com as 40 primeiras páginas e só. O conserto do
   item 1 o corrige junto, e fica registrado que ele era anterior a este item.

**A janela é quem liga as duas abas**, e nenhuma conhece a outra: `review_sink` na Galeria,
`on_scan_book` e `on_cancel_book` na Revisão. São as quatro linhas que subiram a catraca do
`app_tkinter.py` de 1.642 para 1.646, e estão registradas lá com o motivo.

**A operação longa passou a ser uma**, e o guarda de `tests/test_ui_retorno_modal.py` mudou de
quatro módulos para três. O `review_panel.py` não perdeu o número: quem registra e publica
`feito=` é quem tem a thread, e ela é uma só. A aba de Revisão mostra a página em curso na sua
própria barra, sem abrir um segundo registro para a mesma passada.

**O que não foi medido, e é honesto dizer.** Os 338 s + 299 s do enunciado são do
`PDF/1000 Chess Problems`, e repetir a medição exigiria as duas versões do programa lado a lado
sobre 420 páginas — ~21 min de máquina para confirmar uma soma. A passada é literalmente uma
agora, e a que sobrou é a da Galeria: o número a esperar é o dela.

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

## S-140 · O índice sem a cópia, e o cache que não cabe na memória ✅ implementada (item 1 em 2026-08-17, item 2 em 2026-08-18)

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

### O que foi entregue no item 1 (2026-08-17)

`games` passou a ser `WITHOUT ROWID` com `PRIMARY KEY (pair, file, offset)`, o `CREATE INDEX
games_pair` saiu, `INDEX_VERSION` subiu para **3** e `lookup_pair` recusa a v2 com a instrução
de refazer. Quatro testes novos, um deles travando o **esquema** — acrescentar de volta um
`CREATE INDEX games_pair` desfaria a economia inteira sem quebrar nada.

**Medido** num índice sintético de 1 milhão de partidas, os dois esquemas sobre as mesmas
linhas:

| | tamanho | 200 consultas |
|---|---|---|
| v2 — rowid + `CREATE INDEX` | 38,9 MB | 14,6 ms |
| v3 — `WITHOUT ROWID` | **21,8 MB** | 13,7 ms |

**−44,0%**, e a consulta não fica mais lenta. Projetado sobre os 885 MB do acervo: **~495 MB**.
A estimativa do enunciado (~476) era **otimista em 4%**, e fica registrado que o número que
vale é o do próximo `--build-index` e não esta projeção.

**A ordem do enunciado foi invertida, e a razão é externa ao item.** Ele diz, com todas as
letras: *"O item 2 é o que trava a janela hoje; o item 1 é disco, e disco espera. Fazer o 2
primeiro."* O item 2 mexe em `ui/gallery_panel.py`, e há uma avaliação de interface em curso
(`docs/ROADMAP_UI.md`, Fases 20 a 24, escrita hoje) que vai reorganizar o pacote `ui/`.
Entregar o item 1 — que não toca `ui/` — é o que dava para entregar sem colidir. **O item 2
saiu em 2026-08-18**, com as Fases 20 a 24 fechadas e o `ui/` já reorganizado.

**O índice atual no disco vira inválido.** `data/games_index.sqlite` está na v2, e a próxima
consulta por nome vai avisar e devolver vazio até alguém rodar:

```bash
uv run cvoff-games --build-index
```

Isso é ~8,4 min para a base de hoje. A alternativa — ler as duas versões — foi descartada pela
razão que o próprio `INDEX_VERSION` já dava: um formato que se aceita nunca é abandonado, e o
custo de manter os dois caminhos vivos é maior que o de uma reconstrução que roda sozinha.

### O que foi entregue no item 2 (2026-08-18)

`data/games_positions.json` virou `data/games_positions.sqlite`, uma linha por colocação, no
mesmo esquema do item 1: `placement` de chave primária, `WITHOUT ROWID`, sem `CREATE INDEX` ao
lado. `PositionStore` responde `get`, `missing`, `answered_of` e `to_index` por `SELECT` sobre
as colocações pedidas; `PositionCache` sobrou como a forma em memória — é o que a migração lê
e o que um teste de `games_census` monta em três linhas.

**Medido sobre o cache desta máquina** (10.656 posições, 11,6 MB), e não projetado:

| | antes (JSON) | agora (SQLite) |
|---|---|---|
| trocar de livro | **0,59 s**, pico de **63 MB** — o acervo inteiro, na thread do Tk | 0 — a conexão fica aberta |
| responder sobre um livro (1.400 colocações, 885 casamentos) | (já estava tudo em memória) | **30 ms**, pico de 5,5 MB |
| abrir a lista de um diagrama | idem | 0,085 ms |
| o arquivo no disco | 11,6 MB | 11,6 MB |

**E o que o critério de aceite pedia — "alvo constante" — foi medido crescendo o acervo**, com
o mesmo livro de 1.400 colocações:

| linhas no cache | arquivo | o livro |
|---|---|---|
| 10.656 | 10,9 MB | 29,9 ms |
| 31.968 | 33,1 MB | 31,5 ms |
| **53.280** (5×) | 55,2 MB | **33,0 ms** (+10%) |

Cinco vezes o acervo custa 10% a mais no livro. Pelo caminho anterior custaria cinco vezes: os
0,59 s e 63 MB de hoje viram ~2,8 s e ~295 MB nas 50 mil posições que os 34 livros projetam —
que é a estimativa do enunciado, aqui confirmada pela curva em vez de suposta.

**A trava e a refusão da S-113 saíram, e não foram perdidas.** O `.lock` de conselho, o
`_funde` e o `save_cache` que relia o disco existiam porque duas passadas simultâneas se
sobrescreviam — cada uma gravava o dicionário inteiro que lera meia hora antes. Com uma linha
por colocação não há retrato para substituir: cada `update` é uma transação, o SQLite serializa
as duas, e o teste que guardava a decisão continua de pé com o mesmo nome e a mesma pergunta.

**O JSON é migrado, e só uma vez.** Descartá-lo custaria ~56 min de varredura por nada, e nada
nele mudou: a resposta é a mesma, o lugar é que é outro. A migração roda quando o SQLite
**acaba de ser criado** e só para o artefato padrão — um `--cache` apontado para outro lugar
não puxa nem renomeia o de `data/`. Depois dela o arquivo vira `games_positions.json.migrado` e
não é lido por nada; renomear em vez de apagar porque apagar o que era do usuário não é da
alçada de uma migração. Isto foi encontrado por acidente e é o registro: a primeira versão
migrava a partir de qualquer caminho, e a primeira execução da suíte renomeou o JSON de verdade
desta máquina. O teste que guarda o par de caminhos nasceu disso.

---

## S-141 · O processo filho não reimporta o programa inteiro ✅ implementada (2026-08-18)

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

### O que foi entregue, e por que não foi a solução do enunciado

**O enunciado foi conferido primeiro, e ele estava certo.** Reimportar `app_tkinter.py` como
`__mp_main__` custa, medido nesta máquina, **3,14 s e 2.212 módulos** — `torch`, `cv2`, `PIL`,
`chess` e os seis painéis da interface. Um filho carregado com esse conjunto ocupa **223 MB**
contra **15 MB** de um filho nu (1.193 módulos contra 61). Com dez processos são ~31 s de CPU e
~2,1 GB de RAM no arranque de cada varredura, e o filho não usa **nada** disso: ele lê PGN e
reproduz lances.

**A solução do enunciado não foi escrita, e a razão é aritmética.** Ela pede cascas finas
*"sem que nenhuma fronteira de módulo mude"*: imports pesados para dentro de `main()`. Só que a
classe `ChessOcrTkApp` — 1.400 das 1.642 linhas do arquivo — referencia ~45 desses nomes como
globais do módulo, em métodos espalhados por ela. Adiar os imports sem mover a classe exigiria
reinjetá-los em `globals()` dentro de `main()`; mover a classe **é** mudar a fronteira, é a
S-31 reaberta, e alcançaria os 15 arquivos de teste que leem `app_tkinter.py` como texto para
cobrar arquitetura. Um item de desempenho não paga essa conta.

**O que foi feito, no lugar onde o custo nasce.** `games_db._filho_sem_o_main_do_pai` tira
`__file__` de `sys.modules["__main__"]` enquanto os processos do `Pool` nascem, e o devolve em
seguida. O `multiprocessing.spawn.get_preparation_data` só manda o caminho do `__main__` ao
filho se esse atributo existir; sem ele, o `_fixup_main_from_path` do outro lado não roda e o
filho arranca com o interpretador nu. A janela é a construção do `Pool` — segundos —, e não a
varredura inteira, que dura meia hora.

**Medido**, com um `__main__` do peso do `app_tkinter.py` (torch, cv2, numpy, PIL, `OcrService`)
sobre uma base sintética de 1,5 MB, e as duas colunas devolvendo os mesmos 20.000 casamentos:

| processos | como era | agora |
|---|---|---|
| 2 | 2,78 s | **1,10 s** |
| 8 | 3,24 s | **0,76 s** (−77%) |

O critério de aceite pedia *"< 0,5 s e < 30 MB"* para o import do filho. Ele não é atingido —
ele deixa de existir: o filho não importa o script do pai, e o que sobra são os 15 MB do
interpretador. **A resposta da varredura não mudou**, que é a outra metade do critério.

**O preço, escrito onde ele pode morder.** Com o `__main__` do filho vazio, nada que atravesse
a fila pode ser definido no script do pai. Nesta chamada nada é — o alvo é
`_scan_positions_chunk`, função de topo do `games_db` desde a S-26, e as tarefas são `Path`,
`int` e `frozenset`. Se um dia o alvo ou um argumento vier do `__main__`, o filho morre ao
desempacotar e o laço de espera fica sem resposta. Está no docstring da função, é o contrato
dela, e é estreito de propósito.

**Num bundle congelado a supressão não roda.** Ali o `spawn` reexecuta o próprio `.exe` e quem
intercepta é o `freeze_support` (S-55). O caminho é outro, não foi medido aqui, e mexer nele às
cegas trocaria três segundos por um risco sem tamanho conhecido.

**O preço acima deixou de ser um travamento** (S-171, 2026-08-18). A guarda de filho morto
detecta o caso em **0,3 s** e descarta a passada com a mensagem que diz o que houve --
verificado com um alvo definido no `__main__` e a supressão ligada. O contrato continua o
mesmo; o que mudou é que violá-lo agora dá erro em vez de silêncio.

**A S-31 continua aberta, e agora com um argumento a menos.** Enquanto o peso do arranque era
razão para quebrar o `app_tkinter.py`, ele valia como pressão; deixou de valer. Quebrá-lo
continua certo pelas razões da S-31 — o que dá para testar não fica na janela —, e essas não
mudaram.

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
havia documentado, e a primeira metade da correção é a mesma: uma raiz de módulo em `_raiz()`.
Antes disso os 6 testes novos passavam sem rodar.

**A segunda metade custou 20 falhas em outro módulo antes de aparecer.** Copiar o
`test_result_panel` inteiro — guardar a raiz e nunca destruí-la — deixa **duas** raízes vivas
no processo, e duas raízes são dois interpretadores Tcl: `PhotoImage` nasce no `_default_root`,
que é a primeira criada, e o widget da outra não a enxerga. O sintoma foi `image "pyimage46"
doesn't exist` em 20 testes do `test_result_panel`, que ninguém tocou. A raiz agora morre num
`tearDownModule`, o que mantém "uma só durante o módulo" sem deixar duas vivas ao mesmo tempo.

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

## S-127 · O bundle congelado deixa rastro em disco ✅ implementada (2026-08-17)

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

### O que foi entregue

`default_log_file()` ganhou o ramo congelado: sem `CVOFF_LOG_DIR`, `sys.frozen` leva a
`PROJECT_ROOT/logs/chessvisionoff.log` — a pasta **ao lado** do `.exe`, e não `_MEIPASS`, que
some a cada reinstalação e é a pior propriedade possível para o arquivo que existe para
sobreviver a uma falha. **Num checkout nada mudou**: continua `None`, o terminal continua sendo
o rastro, e a suíte não passa a sujar o repositório com um `.log`.

`build_windows.py` cria `logs/` junto com as quatro pastas do usuário. Não é a mesma coisa que
elas — `logs/` é do programa —, e o motivo de nascer no build está escrito lá: uma pasta que só
existe depois do problema é uma instrução que não se pode seguir.

**E uma quarta peça, sem a qual o critério de aceite não fecharia.** O enunciado pedia o
arquivo; o critério pede o **traceback dentro dele**. Não vinha: a falha em `ChessOcrTkApp()`
subia para o `sys.excepthook`, que escreve em `stderr` — e num bundle `console=False` `stderr`
não vai a lugar nenhum. O arquivo existiria e a única falha que ninguém consegue diagnosticar
continuaria fora dele. `main()` ganhou um `try/except` que faz `logger.exception("A janela não
abriu.")` e **re-levanta**: num checkout o terminal e o código de saída continuam iguais.

O comentário da `cvoff.spec` passou a nomear `logs/chessvisionoff.log`, e há teste sobre o
texto dele — ele já esteve ali sem ser verdade, e é isso que impede repetir.

**Conferido invertendo a correção:** com o `default_log_file()` antigo e o `main()` sem guarda,
3 dos 7 testes falham. Os outros 4 são controles que **têm** de passar nos dois: a variável de
ambiente continua mandando, o checkout continua sem arquivo, `logs/` continua no build.

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

## S-129 · A página com `/Rotate` não gera candidato fantasma ✅ implementada (2026-08-17)

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

### O que foi entregue

O diagnóstico do enunciado **se confirmou**, e foi reproduzido antes de qualquer mudança — a
Fase 19 avisa que os itens dela não passaram por cético. Num PDF sintético com o tabuleiro em
posição conhecida, a caixa crua acerta só em `/Rotate 0`; `bbox * page.rotation_matrix` acerta
nos quatro. Mesma coisa para as caixas de `get_text("dict")`.

**Mas o tamanho do problema não era o do enunciado.** Medido no acervo em 2026-08-17: **1
página girada em 18.767** — a 1413 do `Yusupov`, com `/Rotate 180`. O texto dizia "um candidato
que parece diagrama, entra na fila, e ocupa uma vaga do teto por página", o que sugere um
defeito ativo; ele é **latente**. Isso não muda a decisão — a correção é de uma linha e é a
identidade quando a rotação é zero, portanto sem risco nas outras 18.766 —, mas muda o motivo:
o item não recupera recall perdido hoje, ele impede um modo de falha silencioso no dia em que
entrar um livro digitalizado em paisagem.

Por isso o **censo antes/depois não foi rodado**: com uma página afetada em 18.767, ele não
distinguiria a mudança do ruído, e custa horas. A regra da S-82 continua valendo para a S-130 e
a S-131, que mexem em limiar.

**A descoberta que justifica as duas correções serem uma só.** As caixas de imagem e de texto
estavam *ambas* no sistema não girado — erradas, e erradas do mesmo jeito. A associação
legenda↔diagrama é **por proximidade**, e proximidade é relativa: ela funcionava por acidente.
Corrigir só `detection/embedded.py` põe as duas em sistemas diferentes e **quebra o que estava
funcionando**. Medido no teste: a legenda passa de ≤ 60 pt para **243 pt** do diagrama a 90°, e
nenhum diagrama herda legenda nenhuma. As duas linhas têm de andar juntas, e há teste dizendo
isso.

**O tamanho do estrago, por rotação** (IoU entre a caixa crua e onde o tabuleiro está
desenhado):

| `/Rotate` | IoU da caixa crua |
|---|---|
| 0 | 1,000 |
| 90 | 0,000 |
| 180 | 0,000 |
| 270 | **0,404** |

O 270 é o pior dos três justamente por não ser zero: um recorte com 40% de diagrama e 60% de
outra coisa passa nas guardas de tamanho e de aspecto e vira um candidato que *parece* mal
recortado, em vez de um erro.

**Os testes ficaram em `tests/test_detection.py`** e não num `test_detection_embedded.py` novo:
é onde moram `pdf_with_images`, `board_image` e `render`, e onde as outras guardas de candidato
embutido já estão. Dois dos quatro nasceram passando **com e sem** a correção — afirmavam que a
caixa cabia na página, e ela cabe mesmo errada. Foram trocados pelos que medem o que quebra.

---

## S-130 · A nota de textura não muda com a resolução do recorte ✅ implementada e medida (2026-08-17)

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

### O que foi entregue

`texture_scores_side_by_side(a, b)` reduz os dois recortes ao **menor lado dos dois** antes de
pontuar, e é ela que `refine_candidate_with_contour` e `_contour_wins_over_merged` chamam. Os
testes ficaram em `tests/test_detection.py`, que é onde os do `hybrid` já moram.

**O diagnóstico do enunciado está certo pelo motivo errado, e o defeito é maior.** Não é que os
dois recortes "nunca cheguem na mesma resolução" — `board_texture_score` leva ambos a 320 px. É
que ampliar não cria detalhe: um recorte de 200 px ampliado a 320 continua borrado ao lado de
um de 800 px reduzido a 320. Medido, o mesmo tabuleiro **hachurado** em oito resoluções:

| lado de origem | 800 | 640 | 480 | 320 | 240 | 200 | 160 | 128 |
|---|---|---|---|---|---|---|---|---|
| nota | 0,0775 | 0,0772 | 0,0775 | 0,0775 | **0,2862** | **0,4203** | 0,0775 | **0,4202** |

Amplitude **0,343**, contra uma margem de decisão de 0,02. Num tabuleiro **limpo** a nota é
estável nas oito (0,6000) — é por isso que ninguém tinha visto, e é por isso que o teste usa
hachura: o acervo de verdade não é limpo.

**Onde mora o ruído, e o que isso diz à S-143.** Decomposta, a parcela de **xadrez** varia
0,0335 a 0,0340; a de **grade** vai de 0,1429 a 1,0000. É *aliasing*: nas reduções para 240,
200 e 128 as linhas da hachura caem sobre a expectativa de período 20 px e
`_periodic_peak_score` reporta uma grade perfeita que a imagem não tem. A S-143 já desconfiava
da parcela de grade por ser imitável por foto e moldura; agora há uma **segunda razão
independente**, e ela é sobre a própria aritmética.

**O efeito no acervo, medido — e a conclusão é "não muda nada que importe".**

| | |
|---|---|
| refinos avaliados (39 livros, 12 páginas cada) | **260** |
| decisões que viraram | **12 (4,6%)** |
| e das 12, quantas movem o que é exportado | **nenhuma** |

Rodado o OCR de verdade nos dois recortes de cada um dos 12: **4 melhoram, 4 pioram, 4
empatam** — e em 10 deles a confiança é 1,0000 nos dois lados, ou seja, a diferença está na
quinta casa. Os dois casos com diferença real são do `GALLAGHER` (0,0920 → 0,0156 e
0,0796 → 0,0791), e os dois estão **muito** abaixo do gate de 0,80 nos dois estados: nem antes
nem depois viram PGN.

Nas 12, o recorte embutido é sempre o menor (299–594 px contra 800 px do contorno), que é
exatamente a assimetria que o item previa.

**Fica implementado mesmo com efeito nulo hoje**, e a razão é a mesma da S-131: a nota é o
instrumento que arbitra duas fontes, e um instrumento que mede a resolução junto com o objeto
não é instrumento. O `GALLAGHER` é um dos dois livros que exportam **0/2** (S-108); quando ele
ganhar dado real, esta é uma das coisas que deixa de estar errada por baixo.

**E uma limitação do censo, que o critério de aceite não previa.** `cvoff-census --baseline`
diz **"nada mudou"** — corretamente. O censo casa candidatos por **canto de bbox**, e o refino
não muda o bbox: ele muda *quais pixels* o recorte contém. O efeito da S-130 é invisível ao
instrumento da S-82 por construção, e a medição acima teve de ser escrita à parte. Quem for
mexer em algo que muda pixels e não caixas precisa saber disto antes de confiar num diff vazio.

---

## S-131 · O caminho de contorno ganha instrumento antes de ajuste ✅ implementada (2026-08-17)

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

### O que foi entregue

**O passo 1 inteiro, e o passo 2 pela metade — e a metade que ficou é a que o enunciado
mandava não fazer no escuro.**

`cvoff-census --recusas [caminho.csv]` grava um `RejectionRow` por candidato de contorno
barrado, com motivo, score, contraste de casa e caixa **em ponto do PDF** (a mesma unidade dos
aceitos, para que os dois CSVs se leiam lado a lado). Dez guardas passaram a deixar rastro
agregável: seis em `board_detection` (`aspecto`, `fora-da-pagina`, `area-relativa`,
`score-baixo`, `sobreposicao`, `teto`) e quatro em `detection/hybrid`
(`sem-contraste-de-casa`, `prior-de-tamanho`, `perdeu-para-embutido`, `teto-da-pagina`). Das
dez, quatro só existiam como `logger.info`, que ninguém agrega, e seis não existiam de forma
nenhuma. Sem `--recusas` nada é montado: o custo é zero para quem não pede.

**A primeira corrida do instrumento mudou o desenho dele.** Sobre o acervo (39 livros, 12
páginas por livro):

| | recusas | CSV |
|---|---|---|
| registrando tudo | **2.630.560** contra 499 aceitos | **280 MB** |
| sem o que está abaixo do piso de área | **4.944** contra 499 aceitos | **564 KB** |

O lado mediano da recusa era **4,6 pt**. Não eram candidatos barrados: eram manchas que o
`findContours` produz aos milhões e que o piso de área descarta por construção — nenhuma delas
pode ser um diagrama perdido. Um CSV de 280 MB não é instrumento, é ruído com cabeçalho.
Registrar só o que passou do piso deixa a recusa por **aspecto**, que é a informativa: algo do
tamanho de um diagrama, barrado por não ser quadrado o bastante.

**A linha de base, medida em 2026-08-17** (`docs/metrics/deteccao_recusas.csv`):

| motivo | recusas | lado mediano |
|---|---|---|
| `score-baixo` | 2.289 | 74,6 pt |
| `aspecto` | 1.673 | 108,3 pt |
| `sobreposicao` | 344 | 177,8 pt |
| `perdeu-para-embutido` | 263 | 138,1 pt |
| `area-relativa` | 256 | 49,7 pt |
| `sem-contraste-de-casa` | 119 | 135,5 pt |

**Dez recusas por candidato aceito**, e as duas maiores populações têm lado mediano *acima* do
limiar de suspeita de 72 pt — ou seja, do tamanho de um diagrama impresso. Isto não prova que
haja recall perdido ali; prova que a pergunta agora tem onde ser feita, que é o que o item
pedia.

**O passo 2, e por que ele não foi cumprido como escrito.** As oito constantes que decidem
foram nomeadas (`MIN_AREA_FRACTION`, `ASPECT_MIN`/`ASPECT_MAX`, `AREA_SATURATION`,
`MIN_VISIBLE_RATIO`, `MIN_QUAD_INSIDE_RATIO`, `QUAD_MARGIN_RATIO`, `DEDUPE_IOU`,
`MIN_RELATIVE_AREA`, `MIN_SCORE_FLOOR`, `MIN_SCORE_RELATIVE`). O enunciado pedia "cada uma com
o número medido no docstring" — e **não há número medido**: eles vêm da Fase 1 e ninguém os
mediu desde então. O docstring diz isso, com essas palavras, em vez de inventar uma
justificativa. Nomear não é medir, e escrever um número que não foi medido ao lado de uma
constante é pior do que deixá-la anônima: passa a parecer decidida.

**Nenhum limiar foi ajustado**, que é a regra da S-82 e o motivo de a ordem do enunciado não
ser estética — `ANALISE_DETECCAO.md` §5 registra dois ajustes feitos sem censo, os dois
reprovados. O instrumento existe; a medição de cada guarda é trabalho de quem for mexer nela, e
agora ela é possível.

---

## S-132 · O que o gate não enxerga, escrito onde ele decide ✅ implementada (2026-08-17)

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

### O que foi entregue

**A propriedade é mais forte do que o enunciado dizia, e a diferença importa.** O texto afirma
"nenhuma posição reparada pelo decodificador passa o gate de 0,80" como observação sobre este
modelo. É **aritmética**, e vale para qualquer modelo:

1. uma casa reparada recebeu uma classe que não era o argmax;
2. a confiança relatada para ela é a dessa classe — `prediction_from_probs` troca as confianças
   pelas das classes efetivamente escolhidas, que é o desenho certo;
3. essa probabilidade é no máximo a **segunda maior** da casa;
4. a segunda maior não pode passar de **0,5**: se passasse, a maior também passaria, e as duas
   somariam mais que 1;
5. `min_confidence` é o mínimo sobre as 64 casas, e o gate é 0,80.

Logo o teto de um diagrama reparado é 0,5, e **subir a qualidade do classificador não move esse
teto**. Escrever "hoje não passa" seria convidar alguém a tentar resolver com um modelo melhor.

**Medido no conjunto de campo em 2026-08-17**, com o relatório já separado:

```
Casas reparadas pelo decode .. 7  (0.219 por diagrama lido)
Diagramas com reparo ......... 3
  reparados e exportados ..... 0
  reparados e barrados ....... 2
```

Os três não somam dois porque o terceiro é **falso positivo**: `repaired_squares` mede o
trabalho do decodificador em tudo o que foi lido (S-62), e a separação mede o destino de um
diagrama **anotado**. O falso positivo não tinha para onde ir, e por isso fica fora dos dois —
há teste sobre exatamente isso, porque somar os três seria a forma mais fácil de a separação
voltar a mentir.

**A separação é pelo gate, e não por suposição.** `repaired_exported` é incrementado testando
`exportado`, não escrevendo zero. Se um dia o gate mudar — e a mudança, se vier, é no **gate** e
não no decodificador —, o número acompanha em vez de continuar afirmando o que já não é
verdade. O teste que cobre isso monta uma confiança impossível à mão para exercitar o ramo
"reparado e exportado" que o pipeline real não produz.

**Onde ficou escrito.** No docstring de `decode_constrained`, que é onde a decisão mora; nos
três campos novos de `FieldReport`; e no relatório do `cvoff-field`, que passou a imprimir as
três linhas e o porquê — só quando há reparo, para não virar ruído nas páginas em que não há.

---

## S-133 · S-76 e S-77 registradas ✅ implementada (2026-08-17)

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

### O que foi entregue

Duas seções em `SPEC_FASE7.md`, sob um cabeçalho novo — *"Depois da Fase 13 — os dois itens que
vieram do uso (2026-08-14)"* —, no formato das outras 39 daquele arquivo. É ali e não noutro
porque o arquivo cobria S-37..S-75 e a fenda começa em S-76: a faixa fica contígua, que é o que
a tabela da S-134 precisa poder afirmar. Mais duas linhas no apêndice de referências cruzadas.

**Medido antes e depois, com o próprio critério de aceite.** Dos 94 identificadores que
aparecem em `git log --oneline`, 92 tinham seção; os 2 que faltavam eram exatamente S-76 e
S-77, como o enunciado previa. Depois: nenhum.

**Duas coisas não são transcrição, e estão marcadas como tal no texto.** As mensagens de commit
descrevem o que se sabia em 2026-08-14; hoje se sabe mais, e omitir isso faria a seção mentir
por ser fiel:

- a trava que faltava à S-76 — só preencher campo **vazio** — virou desenho na S-88;
- a S-77 gravou a coisa errada por três meses. A anotação saía de `item.placement`, que é o que
  o **modelo** leu, com a correção humana numa lista paralela: corrigir o tabuleiro e clicar
  "Anotar página" gravava a leitura do modelo como verdade de referência. Quem for crescer o
  conjunto precisa ler a **S-95**, e não só esta seção.

Sem essa segunda nota, o item entregaria uma spec que descreve uma ferramenta que já não é a
que está no programa — que é o defeito da Fase 19 inteira, cometido dentro do conserto dele.

---

## S-134 · O índice de documentos, verificável por teste ✅ implementada (2026-08-17)

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

### O que foi entregue

A tabela "Onde mora a spec de cada item (S-NN)" no README e no topo dos cinco documentos de
spec; o §Documentação do `CONTRIBUTING` deixou de nomear o `ROADMAP.md` (que fecha na Fase 6, e
era a causa mecânica da fenda); e `tests/test_docs.py`, com **quatro** guardas em vez dos dois
do enunciado — os dois pedidos não cobriam as duas formas de a tabela apodrecer.

| guarda | o defeito que ela pega |
|---|---|
| `test_todo_item_entregue_tem_secao_em_algum_doc` | a S-76: entregue, sem seção em lugar nenhum |
| `test_a_secao_esta_no_arquivo_que_o_indice_declara` | ter seção **no arquivo errado** — a fenda de outro jeito |
| `test_todo_documento_aparece_no_readme` | documento novo que o índice não menciona |
| `test_a_tabela_de_faixas_e_a_mesma_em_todos` | as cinco cópias da tabela divergindo entre si |

**A faixa da `ANALISE_DETECCAO` não é contígua, e isso é decisão e não descuido.** Ela é
`S-78 a S-82, S-143`: item de detecção mora com os outros de detecção, ao lado da medição que o
motivou — a S-143 entrou junto da S-80, que é o que ela corrige. O formato da tabela aceita
vírgula por causa disso; obrigar contiguidade mandaria a S-143 para longe da única página que
explica por que ela existe.

**Os arquivos de medição ficam de fora, e o teste sabe disso.** `EXPERIMENTS.md`,
`EXPERIMENTS_FASE7.md`, `BASELINE.md` e `ROADMAP_FASE7.md` também têm seções `S-NN`, e elas
**não** contam como spec: uma medição sem critério de aceite é exatamente o que a S-133 veio
consertar. Estão numa constante nomeada, com o porquê ao lado.

**A cópia da tabela em cinco arquivos é deliberada**, e o preço dela é a quarta guarda: quem
abre o `SPEC_FASE7` direto não passa pelo README, e mandá-lo procurar o índice noutro arquivo é
o mesmo obstáculo que criou a fenda.

**E a CI teria passado sem olhar nada.** `actions/checkout@v4` clona **raso**: com
`fetch-depth: 1` o `git log --oneline` tem um commit, a lista de entregues sai quase vazia e a
primeira guarda passaria vazia — pior que não existir. A CI ganhou `fetch-depth: 0`, e o teste
se pula sozinho abaixo de 50 commits, para que um clone raso diga "pulado" e não "verde".

**Conferido quebrando cada guarda uma a uma**, com a mutação que ela existe para pegar: apagar
o identificador da seção da S-76, tirar um `docs/*.md` do índice, fazer a cópia do `SPEC.md`
divergir numa faixa, e declarar a S-143 no arquivo errado. As quatro falharam, cada uma na sua,
e nenhuma nas das outras.

---

## S-135 · Os números vivos: ARCHITECTURE, README, bundle ✅ implementada (2026-08-17)

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

### O que foi entregue

Onze guardas em `tests/test_docs.py`, e as correções de texto que elas passaram a exigir.
**Conferido invertendo cada uma:** repostos os doze valores antigos, 10 das 11 falham, cada uma
na sua e nenhuma nas das outras.

**Duas das doze "divergências" do enunciado não eram divergência**, e medir antes de corrigir é
o que impediu de estragá-las:

- **`18,9 GB` da base de partidas estava certo.** O disco tem 17,66 **GiB**, que são 18,96 GB
  decimais. O enunciado listou "18 GB" como a realidade porque mediu em unidade binária e
  comparou com um número decimal. Nada foi mudado ali.
- **"quatro operações longas" já tinha sido corrigido** pela S-112, que passou o texto para
  "doze threads, sete no `BusyRegistry`, cinco declaradas". O enunciado é de 2026-08-16 e o
  conserto é anterior.

**A tolerância é 10%, e é decisão, não folga.** Com igualdade exata, salvar uma amostra deixaria
a suíte vermelha e o time aprenderia a ignorar este arquivo — o oposto do que ele existe para
fazer. Dez por cento passa em crescimento de uso e falha em número esquecido: as doze
divergências reais estavam todas acima disso (15,8%, 18,7%, 30,8%, 49%). De brinde, absorve a
confusão GB↔GiB, que é 7,4% e já custou a este item uma correção errada.

**Os denominadores medidos não foram reescritos.** "7 dos 27 livros são scan puro" foi medido em
2026-08-14 sobre 27 livros; hoje o acervo tem 39. Trocar para "7 dos 39" seria inventar uma
medição que ninguém fez. O texto passou a dizer a data e o denominador dela, e a acrescentar que
os 12 livros novos não foram classificados — e é *esse* número novo que o teste confere.

**O bundle: o mecanismo entrou, a medição não pôde entrar.** `build_windows.py` grava
`docs/metrics/bundle.json` com `{mb, arquivos, data, commit}`, e o README é conferido contra ele.
Mas o `dist/` que existe no disco é o build de **2026-08-09** — ainda leva `pythonnet` e
`clr_loader`, removidos na S-69, e o `streamlit`, fora das obrigatórias desde a S-137. Publicar
o número dele como atual seria cometer o defeito deste item dentro do conserto dele. O arquivo
foi gerado com `"obsoleto": true` e uma nota dizendo de que build é; o README repete isso; e a
décima-primeira guarda existe só para isso: **se as métricas se dizem obsoletas e o README não
avisa, a suíte falha.** Refazer o bundle é uma execução de `packaging/build_windows.py`, e ela
reescreve o arquivo sem esses dois campos.

### O bundle foi refeito em 2026-08-18, e ele achou o que o item existia para achar

`python packaging/build_windows.py --clean`, duas vezes, e os números:

| build | mb | arquivos | o que mudou |
|---|---|---|---|
| 2026-08-09 (o que o README publicava) | 696 | 4.723 | — |
| 2026-08-18, primeira passada | 685 | 4.278 | o `streamlit` de fato tinha saído |
| 2026-08-18, com os `excludes` novos | **684** | **4.275** | e o `pythonnet` **não** |

**O `pythonnet` e o `clr_loader` continuavam dentro do bundle** — 440 KB e 24 KB —, e o
docstring da `cvoff.spec` dizia, com todas as letras, que WebView2 *"não é mais assunto: a aba
'Leitura' que o embutia saiu na S-69, e com ela `pythonnet` e `pywebview`"*. A frase estava
certa sobre o código e errada sobre o bundle, e a razão é a que este item inteiro é sobre:
**o PyInstaller coleta o que está instalado, não o que o `pyproject.toml` declara.** A S-69
tirou a dependência declarada; o pacote continuou no ambiente de quem já o tinha, e o
empacotador continuou achando-o. Os dois entraram para os `excludes`, com o número ao lado —
a mesma disciplina de "cinto e suspensórios" que o `pyarrow` já tinha ali.

São 1 MB em 685. **O tamanho não é o ponto**: o ponto é que um número publicado que ninguém
recalcula envelhece, e que a primeira recalculada desmentiu uma afirmação que estava escrita em
dois arquivos. Era exatamente a aposta do item.

De passagem, o número que ninguém tinha conferido: o README publicava **5.247 arquivos** e o
build que ele descrevia tem **4.723**. O `mb` estava certo porque veio do `tamanho_em_mb`, que é
binário — e é por isso que o novo `gravar_metricas` continua binário, com a unidade escrita no
docstring. Trocar para `10**6` faria o mesmo bundle "engordar" de 696 para 730.

**A tabela de persistência estava com 8 de 16 artefatos**, o `splits.csv` em duas linhas e uma
linha para o `provenance_index.jsonl`, que este repositório nunca teve. Agora ela é conferida
nos dois sentidos, e a linha do `provenance_index` ficou — marcada **sob demanda**, que é o que
ela é: `cvoff-provenance` a produz, e são horas.

**E um `tomli` que o teste não pode usar.** As duas primeiras versões liam o `pyproject.toml`
com ele. Ele está no ambiente, e **não está declarado em lugar nenhum**: vem de carona com o
`mypy`. Um teste que depende do que ninguém declarou passa hoje e some amanhã — a mesma família
de defeito que a S-128 consertou na CI. Foram substituídos por um leitor de dez linhas que só
sabe ler as duas seções de que precisa, com o porquê no docstring.

---

## S-136 · `app_tkinter.py` dobrou: reabrir o item ou registrar o novo placar ✅ implementada (2026-08-17)

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

### O que foi entregue

**A escolha foi registrar o placar, e a razão é de data e não de princípio.** Há uma avaliação
de interface em curso — `docs/ROADMAP_UI.md`, Fases 20 a 24, escrita em 2026-08-17 — e ela vai
reorganizar exatamente este arquivo. Extrair para `ui/` agora seria decidir a decomposição
antes de ler a avaliação que a estuda, e colidir de frente com ela. O que não podia esperar é o
arquivo continuar crescendo em silêncio enquanto isso se resolve.

**O número de hoje é 1.440**, e não os 1.302 do enunciado: cresceu mais 138 linhas entre
2026-08-16 e 2026-08-17, durante as próprias Fases 18 e 19. A trajetória completa está no
`ROADMAP.md`, ao lado da decisão de fechamento da S-31 que ela contradiz.

`TamanhoDaJanelaTests` tem **três** guardas, e a segunda é a que faz a primeira valer:

| guarda | o que impede |
|---|---|
| `test_a_janela_nao_volta_a_crescer` | o arquivo passar de 1.440 sem alguém decidir |
| `test_o_limite_registrado_nao_esta_defasado_para_baixo` | extrair 400 linhas e deixar a folga de volta — uma catraca que não aperta não é catraca |
| `test_o_alvo_original_continua_escrito_na_spec` | os 600 da S-31 sumirem do `SPEC.md` se alguém "atualizar" o critério |

**É catraca, não meta.** O corte é o valor de hoje. Baixá-lo é a S-31 reaberta; subi-lo exige
editar o teste — que é o ponto: passa a ser decisão em vez de acidente.

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

---

# Achados de 2026-08-18 — o que a implementação encontrou

> Os dois itens abaixo não vieram de uma avaliação: vieram de **implementar** os itens da Fase
> 17 e olhar para o que estava ao lado. Ficam aqui, numerados na sequência, porque o método do
> projeto é que achado sem número não é achado — é lembrança.

## S-171 · A varredura que espera para sempre por um pedaço que não volta ✅ implementada (2026-08-18)

**Problema.** `games_db.scan_by_positions` conta conclusões até `len(tarefas)`:

```python
while concluidos < len(tarefas):
    ...
    parcial = pendentes.next(timeout=CANCEL_POLL_SECONDS)
```

Um processo-filho que morra — OOM, crash nativo, `kill` — leva com ele o pedaço que estava
lendo, e o `imap_unordered` **nunca** devolve aquele resultado. O `Pool` repovoa o trabalhador,
os outros pedaços terminam, e o laço fica pendurado no que não vem.

**Reproduzido em 2026-08-18**, com um `Pool` de verdade e um filho que chama `os._exit(1)`:
seis pedaços, **cinco voltaram, e o laço esperou até o teste desistir aos 20 s**. Numa passada
real — ~56 min sobre 10,3 GB de PGN, dez processos — o sintoma é a Galeria dizendo "pedaço 9 de
10" indefinidamente, com a barra de progresso parada e o botão de cancelar como única saída.

**Por que ele importa mais do que a probabilidade sugere.** É a operação mais cara do programa
e a única tudo-ou-nada: quem cancela perde a passada inteira (S-92). Um travamento que só se
resolve cancelando custa exatamente o que o item existe para não custar. E cada filho carrega o
conjunto-alvo e o porteiro de ocupações — com 40 mil posições e dez processos, morrer de memória
não é hipótese exótica.

**Solução.** `_pids_do_pool` fotografa os pids que nasceram com o pool; `_perdeu_um_filho`
compara a cada volta do laço. **O sinal é a troca de pid, e ela é confiável porque o `Pool`
repovoa**: perder um trabalhador faz o conjunto deixar de ser o que nasceu, e isso aparece na
volta seguinte — medido, no mesmo décimo de segundo. Olhar para `is_alive()` não serviria:
depois do repovoamento há três vivos de novo.

A resposta é **descartar a passada e dizer**, que é a mesma do cancelamento e pela mesma razão
da S-92: quem viu parte da base tem contagem de partidas por posição que não vale, e é a
contagem que autoriza preencher header (S-74). Meia varredura gravada seria procedência
inventada.

`_pool` é privado do `multiprocessing` e é lido por `getattr` de propósito: numa versão que não
o tenha, a guarda desliga sozinha e volta-se ao comportamento anterior — que é ruim — em vez de
um `AttributeError`, que é pior.

**E ela fecha o contrato que a S-141 deixou aberto.** Aquele item registrou, com todas as
letras, que suprimir o `__main__` do filho tem um preço: *"se um dia o alvo ou um argumento vier
do `__main__`, o filho morre ao desempacotar e o laço de espera fica sem resposta"*. Com a
guarda, esse caso passou a ser **detectado em 0,3 s**, com a mensagem que diz o que houve —
verificado com um alvo definido no `__main__` e a supressão ligada. O preço da S-141 deixou de
ser um travamento e virou um erro.

**Testes.** `tests/test_games_db.py::FilhoMortoTests` — o pool intacto não dispara, o pid
trocado dispara, o conjunto que encolhe dispara, a ausência de `_pool` desliga a guarda em vez
de levantar, e a passada perdida sai vazia com log de erro. A reprodução completa (um `Pool` de
verdade com um filho que morre) não entra na suíte: ela custa 20 s de espera e não é coisa de
rodar 2.000 vezes por dia. O que fica travado é a decisão — qual sinal conta, e o que se faz
com a passada.

## S-172 · O placar de uma fase envelhece igual a um número do README ✅ implementada (2026-08-18)

**Problema.** O critério de saída da Fase 6 (`ROADMAP.md`) ficou parado em 2026-07-27 e duas das
três linhas ficaram falsas:

| a linha | dizia | era verdade |
|---|---|---|
| executável rodando em máquina sem Python | **não iniciado** (6.8 / S-36) | feito desde a S-55; a S-127 pôs log em arquivo, a S-135 mediu, e o bundle foi refeito hoje |
| `app_tkinter.py` abaixo de 600 linhas | **651** (477 de código) | **1.677**, e o arquivo dobrou depois da decomposição (S-136) |

E a linha 6.8 da tabela de entregas continuava com `—` no status.

**É o mesmo defeito da S-135, num documento que ela não olhou.** Aquele item existe porque *"um
número declarado que ninguém recalcula envelhece"*, e travou onze afirmações de `README.md` e
`ARCHITECTURE.md`. Os critérios de saída das fases não estavam na lista, e são exatamente o tipo
de texto que ninguém revisita: eles descrevem o passado por construção.

**A gravidade não é o número, é a direção do erro.** "Não iniciado" sobre um `.exe` que roda
manda quem lê o roadmap planejar trabalho que já está feito.

**Solução.** As três linhas passam a ter duas colunas — o estado de 2026-07-27 e o de hoje —,
e duas guardas novas em `tests/test_docs.py`:

1. a **última** célula da linha do executável não pode dizer "não iniciado" enquanto
   `packaging/cvoff.spec` estiver no disco;
2. o número de linhas citado bate com `app_tkinter.py`, com a mesma tolerância de 10% dos
   outros números vivos.

A primeira olha a última célula e não a seção inteira **de propósito**: a coluna do meio guarda
o estado de 2026-07-27, e cobrar "não iniciado" ali apagaria o registro de que o placar
envelheceu — que é o que este item existe para mostrar.

**As duas guardas foram verificadas contra um documento mentiroso**, e não só contra o
corrigido: com o placar adulterado para "não iniciado" e para "900 linhas", as duas falham com o
número ao lado. Uma guarda que nunca se viu falhar é decoração.

**Testes.** `tests/test_docs.py::NumerosVivosTests` — as duas descritas acima, ao lado das onze
da S-135.

## S-173 · Uma passada descartada não pode virar "a base não conhece" ✅ implementada (2026-08-18)

**Este item existe porque a S-171 o criou.** Está escrito assim de propósito: a guarda de filho
morto abriu um caminho novo — uma passada descartada **sem ninguém ter cancelado** — e esse
caminho desembocava num defeito de corrupção que estava latente.

**O mecanismo.** `scan_by_positions` devolvia `PositionIndex()` vazio para dois estados que não
são o mesmo:

| o que aconteceu | o que saía | o que significa |
|---|---|---|
| a base foi lida inteira e não achou nada | `PositionIndex()` | **resposta**: "a base não conhece estas" |
| a passada foi descartada | `PositionIndex()` | **nada**: ninguém procurou |

E `update` grava o conjunto-alvo **inteiro** como perguntado — que é a decisão da S-84, e ela é
certa: sem ela as 1.922 posições que a base não conhece voltariam ao alvo de toda varredura
futura. Junte as duas e o resultado é o pior que este cache admite: uma passada descartada
gravaria `count = 0` sobre **milhares de colocações que ninguém chegou a procurar**, e —
perguntado sendo perguntado — elas nunca mais voltariam ao alvo de varredura nenhuma. A
corrupção se parece com trabalho feito.

**Por que ele não tinha mordido antes.** Por sorte, e a sorte é nomeável: o único caminho que
produzia índice vazio era o cancelamento, a Galeria conferia `cancel.is_set()` antes de gravar,
e o `cvoff-games` não tem cancelamento. Eram duas linhas de defesa, as duas em quem **chama** —
e uma delas não existia. A S-171 tirou a premissa de que só o cancelamento descarta.

**Solução.** `PositionIndex.complete`, no molde do `GalleryIndex.complete` da S-120. Falso nos
dois caminhos de descarte. A guarda mora nos dois `update` do cache, e **não** em cada
chamador, pela razão que o próprio defeito demonstrou: quem chama não deve precisar lembrar de
perguntar, e houve dois chamadores e só um lembrava.

**A tela e o comando passaram a dizer o que houve.** A Galeria tem uma frase própria — diferente
da de cancelamento, porque ali a pessoa sabe o que fez e aqui ela não fez nada e precisa saber
que **dá para tentar de novo**, já que nada foi gravado. O `cvoff-games` imprime a mesma
informação e sai com `EXIT_FAILURE`: um comando que varre meia base e sai com 0 mente para o
script que o chamou.

**Testes.** `tests/test_games_cache.py::PassadaDescartadaTests` — a passada descartada não grava
uma linha, as colocações continuam por perguntar, e a passada **completa** que não achou nada
continua gravando (é o lado que a guarda não pode quebrar). `tests/test_gallery_panel.py` — o
worker não abre o cache para gravar, e a frase diz que nada se perdeu.

## S-174 · O auto-teste classifica errado as duas falhas que ele existe para nomear ✅ implementada (2026-08-18)

**Como ele apareceu.** Fazendo o que o critério de saída da Fase 18 manda fazer e ninguém tinha
feito: exercitar as três falhas **no `.exe`**. O critério diz, com todas as letras, *"produzem
mensagem em pt-BR e rastro em disco, no checkout **e** no `.exe`"* — e a metade do `.exe` nunca
tinha sido rodada, porque exigia um bundle, e o bundle estava obsoleto desde 2026-08-09 (S-135).

**O que o bundle recém-construído respondeu**, com os códigos que o README documenta ao lado:

| falha | esperado | **era** |
|---|---|---|
| PDF corrompido | 2 (entrada inválida) | **1** + traceback do `pymupdf` em inglês |
| `settings.json` inválido | 0 (não impede nada) | 0 ✅ — a S-124 já cobria |
| checkpoint de outra `arch_version` | 3 | **1** + traceback do `torch` em inglês |

**Duas das três estavam erradas, e erradas na direção que confunde.** `1` quer dizer *"o
programa falhou"*; nos dois casos quem falhou foi **um arquivo** — um que o usuário escolheu, e
outro que a instalação trouxe. Quem lê `1` procura defeito no programa; quem lê `2` troca o
arquivo e quem lê `3` reinstala.

**A causa é a mesma nos dois, e ela é estrutural:** `selftest` classificava **ausência** e não
**ilegibilidade**. `modelo.exists()` respondia por 3, e um `.pt` truncado passava por essa
guarda para morrer no `except` genérico do reconhecimento — que não tem como saber se o que
falhou foi o modelo, o PDF ou a leitura.

**Solução.** Carregar o checkpoint e abrir o PDF viraram **passos próprios**, porque
classificar exige saber *onde* falhou. A classificação não vem do texto da exceção: as pistas
de `cli._CHECKPOINT_PISTAS` teriam de adivinhar "isto era um checkpoint" de uma mensagem do
`torch` que não contém nem `.pt` nem `state_dict`. O `message_for` da S-126 é reusado para a
frase — um tradutor, não dois.

**E a ordem passou a responder a pergunta certa primeiro.** Instalação antes de entrada: se o
checkpoint não carrega, isso é verdade sobre a instalação e não depende de qual PDF o usuário
escolheu. Antes o PDF era aberto primeiro, e uma instalação quebrada com um PDF ruim reportava
o PDF.

**Verificado no `.exe`, e é o ponto do item:**

```
1. PDF corrompido ......... exit=2   frase pt-BR ✓
2. settings.json invalido .. exit=0
3. checkpoint ilegivel .... exit=3   frase pt-BR ✓ (cita `arch_version`)
4. instalacao boa ......... exit=0
   logs/chessvisionoff.log gravado nos quatro
```

**Testes.** `tests/test_packaging.py::SelftestTests` — os dois códigos, as duas frases, e a
guarda de que um checkpoint **bom** não cai nelas (uma guarda que transforma instalação boa em
erro é pior que a falha que ela cobre).

---

> **Esta secao veio da `main` na integracao dos dois ramos.** O item foi entregue la, e o
> codigo dele -- `missing_field_pdfs` e a separacao entre `NoBoardDetectedError` e falha de
> verdade -- entrou por este merge. A spec vem junto porque item entregue sem secao e a fenda
> que a S-134 existe para fechar.

## S-218 · Um PDF que não abre virava recall baixo ✅ implementada (2026-08-23)

**Problema.** `field_eval.evaluate_field` capturava `Exception` inteira ao ler a página:

```python
try:
    lidos = service.recognize_page(caminho, pagina.page, options=options)
except Exception as exc:  # página quebrada é resultado, não crash
    logger.warning("Falha ao ler %s p%d: %s", pagina.pdf, pagina.page, exc)
    lidos = []
```

A intenção era a da S-34 -- um livro que falha no meio não derruba a varredura inteira --, e
ela está certa para *uma página que não tem tabuleiro*. O que a guarda não separava é que
**"o arquivo não existe" entrava pela mesma porta**, e saía pelo mesmo `lidos = []`.

Em **2026-08-22**, 11 páginas do conjunto de campo entraram com o nome do PDF em codificação
dupla -- `Eröffnungswege` gravado como `ErÃ¶ffnungswege`. Nenhum dos arquivos abriu. O
relatório publicou `detection_recall` **0,7596** onde o pipeline valia **0,9364**, e o único
sinal foi um `WARNING` com **a mesma frase** que uma página legitimamente vazia produz.

O peso disto é o mesmo da S-100: uma métrica medida sobre arquivos que não abriram não é uma
métrica ruim, é um número **sobre outra coisa** -- e no relatório ele tem exatamente a
aparência de uma regressão do detector. Foi para os documentos como se fosse.

**Solução.** Separar as duas situações, e conferir a mais provável antes de medir.

*Só `NoBoardDetectedError` continua virando `lidos = []`.* É a única falha que é medição: a
página abriu, foi lida, e não tem tabuleiro -- que é o detector dizendo "nenhum", e vale
recall zero naquela página. Ela cai para `logger.debug`, porque a página já aparece no
relatório, em `misses`.

*Qualquer outra exceção derruba a medição*, embrulhada em `FieldPageReadError` com o caminho,
o número da página e o **texto original** da causa -- o original porque é ele que
`cli.message_for` traduz e `cli.classify` lê para escolher o código de saída.

*Os PDFs são conferidos antes da primeira leitura*, por `require_field_pdfs`. Pré-voo e não
checagem no laço por duas razões: uma medição de campo leva minutos por livro, e descobrir no
oitavo que o terceiro não existia é descobrir tarde; e **a lista completa é o diagnóstico** --
11 nomes com o mesmo defeito dizem "codificação", um nome de cada vez diz "sumiu um arquivo".

A mensagem diz o nome, a pasta em que procurou, e -- quando a pasta tem um arquivo que só
difere pela codificação do nome -- **qual é ele**:

```
Erro: 2 PDF(s) citados pelo conjunto de campo não foram encontrados.
Pasta procurada: C:\Python-Chess2\ChessVisionOFF_Puro\PDF
  - ErÃ¶ffnungswege.pdf  (a pasta tem "Eröffnungswege.pdf" -- nome em codificação dupla?)
  - sumiu de vez.pdf
Corrija o campo `pdf` do conjunto ou aponte --pdf-dir para a pasta certa. [...]
```

A sugestão é o que separa "arrume o conjunto" de "investigue o que houve": sem ela o
incidente continua sendo 11 caminhos que não existem, e nenhuma pista de que os arquivos
estavam ali o tempo todo com o nome bem escrito. Ela cobre as três maneiras de o conjunto e o
disco discordarem sobre um nome que um humano leria como igual -- codificação dupla desfeita,
NFC (o macOS grava NFD) e caixa dobrada.

Só as páginas **revisadas** entram no pré-voo, pela mesma regra do resto do módulo: um
rascunho pendente citando um PDF que ainda não chegou à máquina não pode impedir a medição do
que já foi anotado.

**Critério de aceite.** `cvoff-field` sobre um conjunto que cita um PDF inexistente **não
imprime relatório nenhum** e sai com código **2** (entrada inválida, não defeito do programa),
citando o nome do arquivo e a pasta. Nenhuma página é lida antes da falha.

**Testes.** `tests/test_field_eval.py::PdfsDoConjuntoTests` -- a mensagem com nome e pasta, a
lista com todos os que faltam, a sugestão do nome bem escrito, o rascunho pendente que não
atrapalha, `missing_field_pdfs` respondendo sem levantar, e o fim a fim pelo CLI com o código
de saída. Em `FieldRunTests`, o par que fecha a separação: `NoBoardDetectedError` continua
valendo zero detectados, e qualquer outra falha derruba com a página nomeada.
