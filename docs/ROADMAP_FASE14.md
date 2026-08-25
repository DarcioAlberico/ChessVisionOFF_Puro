# Roadmap — Fases 14 a 19

Continuação de [ROADMAP_FASE7.md](ROADMAP_FASE7.md), que fecha na Fase 13. Especificação
detalhada em [SPEC_FASE14.md](SPEC_FASE14.md) (S-95 a S-142). Para o *como* de hoje,
[ARCHITECTURE.md](ARCHITECTURE.md); para os números anteriores, [BASELINE.md](BASELINE.md) e
[EXPERIMENTS_FASE7.md](EXPERIMENTS_FASE7.md).

**Data da avaliação:** 2026-08-16 · **Ramo:** `fase-5-modelo-desempenho` · **Commit base:** `72e3e35`

---

## Onde o projeto está (2026-08-18)

**Vinte e duas das vinte e quatro fases estão fechadas.** As duas que faltam têm o código
inteiro entregue e travado por teste; o que falta nelas **não é código** — é uma anotação e uma
decisão, as duas do dono do acervo. Está assim, por medição e não por impressão:

| fase | estado | o que falta |
|---|---|---|
| 0, 1, 3, 4, 5 | ✅ | — |
| 2 | ✅ | critério de saída **fechado em 22/08**: 41 livros, 20.089 páginas, 3 h 25 min, e **0 posições ilegais** em 29.322 exportadas |
| 6 | ⚠ | `app_tkinter.py` em 2.081 contra o alvo de 600 (S-31 aberta, com catraca; +65 nas S-219 a S-226 e +81 na Fase 37, cada subida com o motivo no `test_packaging`) |
| 7 a 13 | ✅ código completo | a 7 registra critério não atingido, com a razão medida |
| **14 — a régua** | ✅ | S-99 fechada em 22/08: 66 páginas, `comparable` 96, faixa 0,60–0,80 com **6 de 5**. A régua achou o primeiro **exportado e errado** do projeto |
| **15 — dataset e treino** | ✅ | S-108 fechada em 21/08: 80 rótulos, dedupe registrado, controle e tratamento medidos. Promover segue sendo decisão sua |
| 16, 17, 18, 19 | ✅ | — |
| 20 a 24 — interface | ✅ | 27 de 27 |

**As duas pendências são pequenas e não são minhas de fechar**, e a razão está escrita item a
item: preencher a 14 com FEN que ninguém conferiu é o defeito que a S-95 consertou, e trocar o
modelo de produção é a decisão que o quadro de riscos marca como sua desde 2026-08-16.

**O que mudou em 2026-08-22.** A **S-99 fechou**: o conjunto de campo foi de 19 para **66
páginas**, de 40 para **115 diagramas**, de 10 para **30 livros**, e os quatro critérios de
aceite estão medidos (`comparable` 93, cinco regimes no alvo, 6 diagramas na faixa 0,60–0,80).
A régua nova achou o que a antiga não podia achar: **a produção exporta um diagrama errado**
(`Dvoretsky p450`, lido girado 180° com 0,965 de confiança) e a exatidão de campo caiu de
1,0000 para 0,9878. E ela **separa os quatro modelos** — o veredito "não promover o `mhsp`"
fica confirmado, e a decisão sobre trocar a produção pelo controle volta à mesa. Ver o quadro
de riscos e a S-99 na spec.

**O que mudou em 2026-08-21.** A S-108 foi coletada: os dois livros que exportavam zero e não
tinham um único rótulo ganharam **40 cada**, transcritos à mão e conferidos por quatro fontes
independentes -- e o que sobrou das duas pendências encolheu de novo. A 14 passou o corte de
conferíveis (36 contra 30) com as três FEN das páginas de campo dos dois livros. A 15 tem a
coleta feita e espera **uma decisão sua**, que não é a promoção: é se o `--dedupe` e o
`--drop-missing` podem rodar. Sem eles o `cvoff-train` recusa, e com eles o denominador de
`val`/`test` muda -- que é exatamente o que a S-101 fez questão de não deixar acontecer calado.

---

## Como esta avaliação foi feita, e o que ela mede

O projeto está saudável por todos os instrumentos que ele mesmo construiu: `ruff` limpo,
`mypy` limpo em 97 arquivos, **1.540 testes verdes e 3 pulados** em 57 segundos, treze fases
fechadas com destino decidido para cada item de spec. Uma avaliação que parasse aqui diria que
não há o que fazer.

Esta não parou aqui. Ela fez a pergunta que nenhum dos instrumentos faz: **o programa lê
certo?**

A resposta é que **o projeto não sabe** — e que os dois instrumentos que deveriam saber, o
split de teste e o conjunto de campo, estão os dois contaminados pelo que deveriam julgar.

O método foi o das análises anteriores: seis auditorias independentes sobre eixos diferentes
do código, cada achado entregue a um cético encarregado de **refutá-lo** lendo os arquivos
citados, e as medições rodadas de verdade — `cvoff-audit`, `cvoff-field`, `pytest`, e leitura
direta dos artefatos de `data/`. Os números abaixo foram todos reproduzidos nesta máquina em
2026-08-16; o comando que produz cada um está ao lado.

### O que a verificação fez com os achados, e o que ela não alcançou

| | |
|---|---|
| achados brutos das seis auditorias | **59** |
| confirmados por um cético que tentou derrubá-los | **39** |
| refutados ou redimensionados | **7** |
| **sem veredito** — o orçamento da sessão acabou | **13** |

**Os 13 sem veredito são os eixos de detecção (6) e metade do de engenharia (7).** Estão
registrados nas Fases 18 e 19 com a evidência que o auditor deu, e **não** com o selo dos
outros: quem for implementá-los confere o arquivo:linha primeiro. Está dito item a item.

**A verificação valeu o que custou, e o registro disto é parte do método.** Quatro achados
sobreviveram menores do que nasceram, e dois deles estavam em itens que esta análise já havia
escrito:

- a contaminação do conjunto de campo é **do próximo retreino**, não do número de hoje — as 8
  amostras do Karpov são posteriores ao checkpoint de produção (S-97);
- o desempate entre épocas empatadas **não é defeito**: é decisão escrita e travada por teste,
  com a razão ao lado. Virou item de medição (S-104);
- `cvoff-audit --dedupe` **não** espalha contaminação: 0 dos 373 grupos cruzam split, porque a
  S-07 já garante isso. O que sobra é bem menor (S-101);
- a contaminação do split de teste é de **2 a 4 tabuleiros**, e não de 15 — dentro do ±1 ponto
  de IC95 que o `BASELINE.md` já declarava (S-98).

Duas "refutações" foram descartadas por circularidade: os céticos leram os documentos que esta
própria avaliação estava escrevendo e concluíram "já está documentado". Um deles registrou a
ressalva sozinho, notando que os arquivos estavam *untracked*.

---

## O eixo da avaliação: as duas réguas estão contaminadas

A Fase 7 abriu com uma frase que reorganizou o projeto: *"não é o modelo que está ruim — é o
conjunto de teste que não representa a entrada"*. O conjunto de campo da S-41 nasceu dessa
frase. Esta avaliação encontrou o degrau seguinte, e ele é mais grave: **o conjunto de campo
tem o mesmo defeito que veio corrigir, e mais um.**

### 1. A verdade de referência é a leitura do próprio modelo

`app_tkinter.py:952-956` monta a anotação de uma página a partir de `item.placement` — **o que
o modelo leu**. A correção humana mora em `fen_edits`, uma lista paralela, e a separação entre
as duas é deliberada e está escrita em dois docstrings:

> `fen_edits[i]` é o que o usuário está editando *agora*; `items[i].placement` é o que o
> modelo leu. Fundi-los perderia a leitura original.
> — `ui/editor_model.py:19` e `ui/result_panel.py:15`

A anotação lê o lado errado. **Corrigir o tabuleiro e clicar "Anotar página" grava a leitura
errada como verdade.** E `ui/field_draft.py:112-114` avisa contra exatamente isso, mas só para
o campo `reviewed`:

> medir o modelo contra a própria saída dá 1,000 em tudo e não significa nada.

A guarda foi posta em `reviewed` e esquecida em `placement`.

**A prova está no disco.** Dos 39 diagramas anotados, **um** tem FEN de referência: a capa
(página 0) do Yusupov, `4r2R/7Q/6R1/3rrrr1/1R1rrrR1/6Pq/2k1r1Q1/3b2q1` — sem rei branco, com 9
torres pretas e 2 damas brancas. `chess.Board(...).status()` devolve `NO_WHITE_KING`.

É contra ela que o produto mede a própria exatidão:

```
comparable            1
exact                 1
conditional_exact     1.0
```

**A exatidão de leitura do produto é 1,000, medida em um diagrama, contra uma alucinação.**

### 2. A métrica primária não mede leitura — mede confiança

`field_eval.py:404-406` só conta `exact` onde a anotação tem `placement`. Com 1 de 39, a taxa
de exportação mede uma coisa só: *o modelo teve confiança ≥ 0,80 e a posição era legal*. **Uma
leitura confiantemente errada entra como acerto.**

A troca foi consciente — a flag `--no-placement` existe e o *help* a defende com um argumento
correto. O que nunca foi nomeado é o custo. A 7.7 descobriu que a taxa de exportação é *"uma
catraca que só desce"* e atribuiu isso à distribuição bimodal da confiança; a explicação está
um nível abaixo. **Uma métrica de confiança não pode medir correção**, e quatro itens de spec
— S-38b, S-40, S-62a, S-62b — foram julgados por ela.

### 3. Um sexto do conjunto de campo vira treino no próximo retreino

Cruzando `data/field_set.jsonl` com `data/labels.csv` por `(source_pdf, source_page-1)`:

| | |
|---|---|
| diagramas anotados no conjunto de campo | 39 |
| **em páginas de que há amostra rotulada** | **7 — 17,9%** |
| e o split dessas amostras hoje | **`train`, todas as 9** |

São `Karpov A - Chess Combinations 1` p80 (6 diagramas) e `1937 Kemeri` p187 (1). Os sete
passam o gate: o Karpov exporta **12/12** no relatório de hoje.

**A ressalva que a verificação obrigou, e que muda a leitura.** O checkpoint de produção é de
2026-08-09 10:51 e foi treinado sobre 2.660 amostras; das nove, **oito são de 2026-08-10** e
uma é de 2026-08-09 10:09. Ou seja: **o número de hoje quase não sofre** — o modelo que produz
a métrica não viu esses recortes.

O problema é o próximo passo. A Fase 15 retreina (é a pendência de 468 amostras logo abaixo), e
no momento em que isso acontece **as nove entram no treino e o conjunto de campo passa a medir
o modelo em páginas que ele aprendeu** — sem que nada avise, e justamente na medição que vai
decidir a promoção.

O conjunto de campo existe, nas palavras do próprio `field_eval`, porque o split de teste não
descreve a entrada do produto. É uma armadilha que fecha no próximo passo, e é por isso que ela
é barata agora e cara depois.

### 4. E o split de teste também está contaminado

Cruzando `labels.csv` com `splits.csv` por `(source_pdf, source_page, source_diagram)`:

```
Schiller - The Big Book of Combinations p41 d1   ->  train, test
Secrets of Chess Training p19 d1                 ->  train, val
Niemeijer - Zwarte Magie p10 d1                  ->  train, val, test
```

**Três diagramas impressos cruzam split, e um deles está nos três** — o Niemeijer foi salvo
quatro vezes. O guarda de grupo da S-07 agrupa por `placement` idêntico **e** dHash ≤ 3, um
limiar calibrado para *"a mesma amostra salva duas vezes"* (`audit.py:242-247`) e não para *"a
mesma página reextraída com recorte deslocado"*. `find_duplicate_groups` devolve 373 grupos e
**0 espalhados entre splits**: a frase de `cli/audit.py:110` — *"a validação segue honesta"* —
é verdadeira pela definição de grupo e vazia na prática.

**O tamanho, com a gradação que a verificação obrigou.** A primeira versão desta análise
afirmou 15 tabuleiros de teste contaminados; o cético derrubou o número, e a versão que
sobrevive é esta:

| evidência | test | val |
|---|---|---|
| **procedência** — mesma tripla `(pdf, página, diagrama)` | **2** | 2 |
| **imagem forte** — dHash ≤ 8 **e** correlação ≥ 0,70 | **4** de 354 | **8** de 346 |
| indício — dHash ≤ 8 só | 15 | 12 |

A última linha não é contaminação medida: nenhum dos 18 pares tem procedência dos dois lados, e
um par de d=5 aberto à mão mostra peças diferentes com o **mesmo rótulo** — o corte em 8
também captura rótulo errado, que é outro problema.

**O impacto honesto:** de 2 a 4 tabuleiros, 0,6 a 1,2 ponto — **dentro do ±1 ponto de IC95 que
o `BASELINE.md:74` já declarava**. O 0,9906 não está muito errado. O que ele não faz é
**separar generalização de memorização na faixa em que se move** — e é nessa faixa que a Fase 5
e a S-40 arbitraram, por meio ponto.

**As duas réguas do projeto medem, em parte, o que o modelo já viu — ou vai ver no próximo
retreino.** É por isso que a Fase 14 vem antes de tudo, e é por isso que nenhum item de modelo
desta análise pode ser julgado antes dela.

---

## O ciclo que dá valor ao projeto está aberto no último passo

Reconhecer, corrigir, `Ctrl+S`, treinar, e o app usar. Funciona até o penúltimo passo.

| `models/piece_classifier.pt` — o que `config.py:168` carrega | |
|---|---|
| amostras de treino | **2.660** |
| `augment_version` | `aug0` |
| `git_commit` · data | `88daa9a` · 2026-08-09 |

| o dataset | 2026-08-16 | 2026-08-23 |
|---|---|---|
| rótulos utilizáveis | **3.935** | **4.064** |
| `train` / `val` / `test` registrados | 2.879 / 346 / 354 | 2.922 / 361 / 370 |
| **sem split** | **357** | **412** |
| treino disponível | ≈ **3.128** | ≈ **3.254** |

**468 amostras (+17,6%) de correção humana que o modelo do app nunca viu** — 697 rótulos
criados em agosto, nenhum no produto. E `models/s40_mhsp_16ep.pt` continua no disco desde
2026-08-11, medido como dominante em tudo que era mensurável (−40% de reparo do decodificador),
sem decisão, esperando justamente uma régua com resolução.

**Remedido em 2026-08-23, e a distância cresceu.** Sobre o `labels.csv` e o `splits.csv` de
`9eb6685`, que já trazem a coleta do app até 2026-08-23 04:38 (`board_20260823_073815_016751`):
são **594 amostras (+22,3%)** que o modelo do produto nunca viu, contra as 468 de 2026-08-16. A
coluna nova é medida e não estimada — "treino disponível" é o tamanho do `train` que o
`cvoff-train` montaria hoje, com os 412 sem split recebendo o deles antes de o dataset ser
montado (S-56). A decisão de promover continua sendo sua, e ficou maior.

---

## O acervo mal foi lido

| | |
|---|---|
| PDFs em `PDF/` | **34** (3 pares duplicados `_hq`, mais um `Andamento.txt` que não é PDF) |
| páginas somadas | **17.823** |
| livros com PGN exportado | **5** |
| livros com índice de Galeria | **7** |
| **livros sem nada** | **27** |

Treze fases de engenharia e ~20% do acervo processado. A fila de revisão
(`data/review_queue.json`) é de 2026-08-09 e cobre **um** livro.

Isso não é preguiça de quem usa: abrir um livro novo custa **duas** varreduras de primeiro
plano, com a janela aberta, porque a Galeria e a fila de revisão percorrem o mesmo PDF com o
mesmo modelo e nenhuma consome o resultado da outra.

---

## A auditoria acusa, e ninguém é obrigado a ouvir

`cvoff-audit` hoje, sem argumento:

```
!! Redundância acima do teto: 11,0% > 10% (S-63).
   433 amostras redundantes em 373 grupos
   357 amostras sem split
   1 imagem ausente
```

O teto da S-63 **estourou** e o comando sai com código **0**. A CI roda `ruff`, `mypy`,
`pytest` e um teste de import; `cvoff-train` monta o dataset sem perguntar nada.

**E a correção que o próprio comando sugere é uma armadilha.** `cvoff-audit --dedupe` apagaria
433 linhas:

| split | linhas apagadas | do total |
|---|---|---|
| `train` | 313 | 10,9% |
| **`test`** | **22** | **6,2%** |
| **`val`** | **29** | **8,4%** |
| sem split | 69 | — |

`remove_duplicate_labels` (`audit.py:400-406`) não consulta `splits.csv`. O comando oferecido
para limpar o dataset encolhe os conjuntos reservados em silêncio e quebra a comparabilidade
com todos os números publicados no `BASELINE.md`. **A ordem importa: consertar o dedupe vem
antes de rodá-lo**, e é por isso que ele é um item de spec e não uma linha de comando neste
documento.

---

## O que foi medido e está desligado

`settings.py:162` define `ocr.enabled: bool = False`, e o `data/settings.json` desta máquina
confirma. A medição da S-43 diz o custo: com RapidOCR instalado, a procedência `default` do
lado a jogar cai de **87,8% para 77,2%**. O motor está no `pyproject.toml`, os modelos vêm no
wheel, a medição está no `ARCHITECTURE.md` — e ele está desligado. Toda exportação feita hoje
carimba `[SideToMoveSource] default` em ~88% dos diagramas quando poderia carimbar em 77%.

---

## O trabalho humano que o programa pode perder

| onde | o quê |
|---|---|
| `data/gallery/` | **5.953 anotações** em 7 livros — 4.906 com headers, 21 com escolha humana de partida (`chosen_game`). Ignorado pelo `.gitignore:38`, **fora do git**, ausente da tabela de persistência do `ARCHITECTURE.md` |
| headers da Galeria | sair de um campo com `Tab`, **sem digitar nada**, rebaixa a procedência de `database` para `manual` e reescreve o livro inteiro no disco |
| `cvoff-games --apply` | quando a escolha humana coincide com a candidata automática, a procedência é rebaixada de `human` para a regra automática, e o censo da S-89 passa a listar como "a revisar" um diagrama que uma pessoa resolveu |
| 10 das 12 threads | não se registram no `BusyRegistry`: fechar a janela durante a busca por posição descarta a passada sem uma palavra |
| `cv2.imwrite` | `dataset.py:450` ignora o `False` de retorno: disco cheio grava a linha no CSV apontando para um PNG que não existe |
| cache de posições | lido, modificado e gravado sem trava: duas varreduras concorrentes descartam uma das duas em silêncio |

O projeto versiona o `labels.csv` com uma justificativa escrita — *"é texto, e é a verdade do
projeto"*. A galeria é a mesma categoria de coisa e está fora.

### E aconteceu durante esta avaliação

Uma das auditorias — que tinha instrução explícita de só ler — **esvaziou o
`data/splits.csv`**: 3.579 linhas viraram uma, o cabeçalho. Foi detectado por `git status` ao
fim do trabalho e restaurado com `git checkout -- data/splits.csv`, íntegro: 2.879 `train`,
346 `val`, 354 `test`.

Não é anedota, é o ensaio da falha. O `splits.csv` carrega uma decisão irreversível na prática
— o `test` existe para responder uma pergunta uma vez — e **o que o salvou foi estar
versionado, e nada mais**. Não havia trava, não havia backup automático, e nada no programa
teria notado.

Se o alvo tivesse sido `data/gallery/`, as 5.953 anotações teriam ido embora sem recurso: ele
não está no git, não tem backup, e nem aparece na tabela de persistência que descreve o que o
programa escreve no disco. **É exatamente o cenário da S-115**, e ele deixou de ser hipotético
hoje.

---

## O que a documentação diz e o disco desmente

| afirmação | realidade |
|---|---|
| `ARCHITECTURE.md:11` — "`app_tkinter.py` e `app_streamlit.py` são apresentação" | `app_streamlit.py` não existe desde a S-54 |
| `ARCHITECTURE.md:161` — "o `labels.csv` tem **3.313** linhas" | **3.936** |
| `ARCHITECTURE.md:212` — "**quatro** operações longas" | **12** threads, **2** registradas no `BusyRegistry` |
| tabela "Formatos e persistência" | 8 de ~17 artefatos; `splits.csv` duplicado; `provenance_index.jsonl` **não existe** |
| `README` — "7 dos **27** livros do acervo" (em quatro lugares) | **34** PDFs |
| `README` — "3.200 PNGs" | **3.935** |
| `README` — base de partidas "9,7 GB" | **18 GB** |
| `README:60` — bundle "696 MB, 5.247 arquivos" | do build de 2026-08-09, que ainda contém `pythonnet` e `clr_loader` — removidos na S-69 |
| `README:233` — "o header `[SideToMoveSource]` diz qual dos **três** foi" | **oito** declarados em `semantics.py:40-42`, e um nono emitido fora do tipo |
| `SPEC.md:811` — critério de aceite "`app_tkinter.py` abaixo de 600 linhas" | **1.302** — dobrou desde a S-31 e nenhum doc registra |
| `docs/PLANO_BASE_PARTIDAS.md` (51 KB, S-83..S-94) | não é referenciado por **nenhum** arquivo do repositório |
| ~~S-76 e S-77~~ ✅ **S-133** | entregues, **em documento nenhum** — caíam na fenda entre `SPEC_FASE7` (até S-75) e `ANALISE_DETECCAO` (a partir de S-78). Registradas em `SPEC_FASE7.md` em 2026-08-17 |

A última linha é a causa mecânica das outras: a spec está em seis arquivos sem índice, e o
`CONTRIBUTING` manda atualizar o `ROADMAP.md`, que fecha na Fase 6.

---

## O que esta avaliação **não** olhou

Registrar isto é parte do método. Três coisas ficaram de fora, e nenhuma por acaso:

- **A qualidade do modelo.** Deliberado: com as duas réguas contaminadas, qualquer veredito
  sobre arquitetura, aumento de dados ou calibração seria a repetição do erro que reprovou
  quatro itens da Fase 7. A Fase 14 existe para tornar essa pergunta respondível.
- **O desempenho sob carga de verdade.** O custo por diagrama medido hoje (0,526 s) saiu com a
  máquina ocupada e **não** é comparável aos 0,331 s de 2026-08-11. Fica sem veredito.
- **A experiência de quem instala pela primeira vez.** O bundle em `dist/` é de 2026-08-09 e
  não representa o código de hoje; medi-lo exigiria refazê-lo, que é a S-135.

---

## Visão geral das fases

```
Fase 14  A régua                              3–4 d + ~3 h suas  ▸ nada depois é julgável sem ela
Fase 15  O dataset e o treino que não mentem  3–5 d              ▸ fecha o ciclo corrigir→treinar
Fase 16  O trabalho humano não se perde       2–3 d              ▸ são defeitos, não melhorias
Fase 17  O laço interno e o custo do livro    4–6 d              ▸ é o que destrava o acervo
Fase 18  Quando algo dá errado                2–3 d              ▸ o .exe que hoje é mudo
Fase 19  Detecção e documentação              3–5 d              ▸ o último caminho sem instrumento
```

Total: ~17 a 26 dias. **As Fases 14 e 16 são as que não podem esperar** — a primeira porque é
a condição de qualquer medição, a segunda porque cada dia de uso acrescenta dado corrompido.

---

## Fase 14 — A régua ⚠ **código completo; o critério depende de anotação humana**

> O projeto não sabe se lê certo, e as duas réguas estão contaminadas pelo que deveriam julgar.

| # | Entrega | Ref. | Estado |
|---|---|---|---|
| 14.1 | A verdade de referência deixa de ser a leitura do próprio modelo | S-95 | ✅ |
| 14.2 | A exatidão de campo passa a existir, com `n` declarado | S-96 | ✅ |
| 14.3 | O conjunto de campo declara a página que o modelo treinou | S-97 | ✅ |
| 14.4 | O mesmo diagrama impresso não cruza split | S-98 | ✅ |
| 14.5 | Crescer o conjunto: 60 páginas, cinco regimes, FEN conferida | S-99 | ✅ **fechada em 22/08**: 66 páginas, 115 diagramas, `comparable` 96, cinco regimes no alvo, faixa 0,60-0,80 com **6** |
| 14.6 | O conjunto vigente é declarado e a comparação volta a ser honesta | S-100 | ✅ |

**Critério de saída:** `cvoff-field` relata exatidão de campo com `comparable ≥ 30`, nenhuma
página do conjunto contaminada por amostra de treino, nenhuma tripla `(pdf, página, diagrama)`
cruzando split, e **pelo menos 5 diagramas na faixa de confiança 0,60–0,80** — a condição que
a 7.7 apontou como ausente e sem a qual nenhum modelo se distingue de outro.

**Medido em 2026-08-18 (`cvoff-field`), e falta pouco:**

| parte | alvo | medido |
|---|---|---|
| conferíveis (`comparable`) | ≥ 30 | **28** — faltam **2** |
| exatidão de campo | — | **1,0000** (28/28) |
| páginas contaminadas por treino | 0 | 2 páginas, 7 diagramas (18%) — **declaradas** pela S-97 |
| triplas cruzando split | 0 | 0 (S-98) |

**Remedido em 2026-08-20, depois da S-175 e de duas correções de anotação:**

| parte | alvo | 2026-08-18 | 2026-08-20 |
|---|---|---|---|
| páginas revisadas / diagramas anotados | — | 18 / 39 | **19 / 40** |
| conferíveis (`comparable`) | ≥ 30 | 28 | **33** ✅ |
| exatidão de campo | — | 1,0000 (28/28) | **1,0000 (33/33)** |
| exportados e **errados** | 0 | 0 | **0** |
| taxa de exportação | — | 0,7179 (28/39) | **0,8500 (34/40)** |
| páginas contaminadas por treino | 0 | 2 páginas, 7 diagramas | 4 páginas, 9 diagramas (22%) — **declaradas** |
| triplas cruzando split | 0 | 0 | **0** |
| diagramas na faixa de confiança 0,60–0,80 | ≥ 5 | 0 | **0** ❌ |

**A cláusula que faltava por dois passou a sobrar por três**, e não por anotação nova: a S-175
devolveu os diagramas da coluna esquerda do `Reinfeld`, que já estavam anotados e nunca eram
detectados. Cinco conferíveis a mais vieram daí e da página 62 do `Anand`.

**Duas cláusulas continuam abertas, e as duas são dado.** A contaminação subiu — de 18% para
22% — porque as amostras novas do `Anand` incluem a página 62, que agora está no conjunto. E a
**faixa de 0,60–0,80 continua vazia**: a distribuição de confiança do conjunto é bimodal, 35
diagramas acima de 0,9 e 2 em 0,000. É o achado da 7.7 intacto — sem vizinhança do gate,
nenhuma mudança pode ganhar ou perder um diagrama por margem, e dois modelos continuam
indistinguíveis por esta métrica. **É a razão que sobra para a S-99 existir**, e ela mudou de
natureza: não é mais "faltam duas leituras", é "faltam páginas difíceis".

### As duas anotações que estavam com o defeito dentro (2026-08-20)

Encontradas ao remedir, e as duas são a mesma classe: **o defeito virou verdade de
referência**. Não é a leitura do modelo entrando como verdade — que é o que a S-95 fechou — é o
*bug* entrando como verdade, por um caminho que a S-95 não alcança.

| onde | o que estava gravado | por quê |
|---|---|---|
| `Anand` p62 | `"diagrams": [], "regime": "sem-diagrama"` | anotada enquanto a S-160 estava viva, quando a interface mostrava aquela página **sem diagrama nenhum** |
| `Reinfeld` p40 e p150, 4 diagramas | caixa de 99 a 102 pt, e FEN deslocada uma casa à direita | anotadas a partir do recorte de 7/8 que a S-175 consertou |

**A caixa é a prova, e ela estava no arquivo o tempo todo.** Das doze anotações daquele livro,
as oito com caixa de ~116 pt casam com a leitura de hoje **casa por casa**; as quatro com caixa
de ~99 a 102 pt são as quatro que divergem. Não é coincidência: 116,14/8 = 14,52 pt por casa, e
116,14 − 102,07 = 14,07 — **uma fileira**. O que está à esquerda do tabuleiro coincide, e tudo
o que está à direita aparece uma casa adiante, que é o que acontece quando 7 fileiras são
esticadas sobre 8 colunas.

As cinco FENs foram **conferidas casa a casa contra o render a 600 DPI** antes de entrar, pela
mesma regra da S-95 e da S-160. Que a leitura de hoje coincida com as cinco é resultado, não
método — e é o que o `exportados e errados` de 3 para **0** mede.

**O que falta é dado, não código.** Todo o instrumento desta fase está entregue e travado por
teste; o que o critério ainda pede é anotação de páginas **difíceis**, que é onde a faixa
0,60–0,80 pode existir. É trabalho do dono do acervo, e é por isso que esta fase não fecha
sozinha: fechá-la escrevendo FEN que ninguém conferiu seria exatamente o defeito que a S-95
consertou — e, como estas duas anotações mostram, conferir contra a tela também não basta
quando a tela está errada.

**A ordem dentro da fase é obrigatória.** A 14.5 vem depois da 14.1: crescer o conjunto com a
ferramenta quebrada acrescenta verdade que é saída do modelo, e **piora** a régua em vez de
melhorá-la.

---

## Fase 15 — O dataset e o treino que não mentem ⚠ **código completo; o critério depende de uma decisão sua**

| # | Entrega | Ref. | Estado |
|---|---|---|---|
| 15.1 | O `--dedupe` registra o denominador que ele muda | S-101 | ✅ |
| 15.2 | A auditoria barra em vez de relatar | S-102 | ✅ |
| 15.3 | `split_hash` conferido: `cvoff-eval` **avisa** sobre o modelo de outra partição | S-103 | ✅ |
| 15.4 | A época salva tem critério de desempate | S-104 | ✅ medido — **não mudar nada** |
| 15.5 | O checkpoint guarda o que reproduz o número | S-105 | ✅ |
| 15.6 | `cvoff-experiment` não reatribui splits no meio da grade | S-106 | ✅ |
| 15.7 | O retreino de produção, e a decisão sobre o candidato de 2026-08-11 | S-107 | ✅ medido — **não promover o `mhsp`** |
| 15.8 | Os livros que exportam zero ganham rótulo no dataset | S-108 | ✅ **80 rótulos + experimento**: o `Euwe` foi de 0/2 para 1/2, e a hipótese não foi falsificada |

**Critério de saída:** o modelo de produção cita `dataset_size ≥ 3.100`; a exatidão de campo do
promovido é igual ou melhor que a do controle, com `n` declarado; e a decisão fica registrada
**inclusive se for "não promover"**.

**Medido em 2026-08-18, lendo os `metadata` dos checkpoints:**

| checkpoint | `dataset_size` | melhor época | métrica |
|---|---|---|---|
| `models/piece_classifier.pt` (**produção**) | **2.660** | 10 | 0,9874 |
| `models/controle_20260816.pt` | **3.173** | 5 | 0,9818 |

**O critério não é atingido por um arquivo que ninguém trocou.** O treino existe, o candidato
existe, a medição existe (S-107: o controle exporta 29/39 contra 28/39 da produção, com
exatidão de campo idêntica sobre os mesmos 28) — e a promoção é **decisão do dono**, como o
quadro de riscos registra desde 2026-08-16.

**Decidido em 2026-08-18: não promover**, com a medição na mesa. A diferença entre os dois é
**um diagrama** — e é um diagrama *sem FEN de referência*, então nem sequer é uma diferença de
correção medida; a exatidão de campo dos dois é a mesma 1,0000 sobre os mesmos 28 conferíveis.
Trocar o modelo que o produto carrega por isso seria pagar risco por ruído.

### O retreino que o disco já tinha, e o documento não (medido em 2026-08-20)

O parágrafo acima diz *"um arquivo que ninguém trocou"*, e na hora em que foi escrito era
verdade. **Não é mais.** Lendo o `metadata` de `models/piece_classifier.pt` hoje:

| campo | o que o documento dizia | o que o arquivo diz |
|---|---|---|
| `dataset_size` | 2.660 | **3.291** |
| melhor época | 10 | 2 |
| `best_metric` (`val_board_exact_acc`) | 0,9874 | **0,9875** |
| `git_commit` | — | `0978c0d` (a S-160) |
| `augment_version` | `aug0` | `aug0` — inalterado |

**A primeira cláusula do critério de saída está atingida por fato:** a produção cita
`dataset_size` 3.291, acima do piso de 3.100. Ela não foi atingida por uma decisão de
promoção; foi atingida porque o dataset cresceu — 98 amostras novas do
`Vishy_Anand_Great_Chess_Combinations`, coletadas durante a S-160 — e o retreino saiu com o
modelo de produção no lugar.

**Medido no conjunto de campo de hoje** (19 páginas, 40 diagramas anotados, depois da correção
da página 62 do `Anand` — ver a nota abaixo): exatidão de campo **1,0000** sobre 29
conferíveis, taxa de exportação 0,7500 (30/40), **zero exportados e errados**.

**O que isto não muda.** A decisão sobre o `mhsp` continua sendo *não promover*, e o
`controle_20260816.pt` continua sem ter sido promovido. O que mudou é o denominador do
critério, e o fato de que **nenhuma guarda viu a troca acontecer**: as duas da S-172 cobrem
placar de fase e número de README, e nenhuma cobre o checkpoint que o produto carrega. É a
mesma classe de apodrecimento, num arquivo que a suíte não olha.

> **A página 62 do `Anand` estava anotada com o defeito dentro.** Ela entrou no conjunto de
> campo como `"diagrams": [], "regime": "sem-diagrama"` — anotada enquanto a S-160 estava viva,
> quando a interface mostrava aquela página **sem diagrama nenhum**. Ela tem um diagrama, e a
> FEN dele é a que o commit da S-160 registra como conferida casa a casa contra o render a 600
> DPI. Corrigida em 2026-08-20: `scan-hachurado`, um diagrama, com `placement`. É o defeito da
> S-95 chegando pelo lado que a S-95 não fechava — não é a leitura do modelo virando verdade, é
> **o bug virando verdade**, e o único remédio é o mesmo: só entra o que foi conferido.

**Consequência, dita sem rodeio:** a primeira cláusula do critério (`dataset_size ≥ 3.100` na
produção) fica **não atingida por escolha**, e a terceira (*"a decisão fica registrada inclusive
se for 'não promover'"*) fica atingida por esta linha. A fase fecha quando um retreino que valha
a troca aparecer — e o que faz um retreino valer a troca é a Fase 14 ter régua, que é a
pendência de anotação logo acima. As duas pendências que sobraram no projeto são, no fundo, a
mesma.

> A 15.7 foi executada em 2026-08-16, **antes** das 15.1 a 15.6 — a pedido, e a ressalva está
> registrada em ["O retreino de produção, medido"](#o-retreino-de-produção-medido-2026-08-16).
> A decisão sobre o `mhsp` está tomada; a troca do arquivo de produção não.

---

## Fase 16 — O trabalho humano não se perde ✅ concluída (2026-08-16)

> São defeitos, não melhorias. Cada dia de uso acrescenta dado corrompido.

| # | Entrega | Ref. | Estado |
|---|---|---|---|
| 16.1 | Sair de um campo sem digitar não apaga a procedência da base | S-109 | ✅ |
| 16.2 | `cvoff-games --apply` não rebaixa uma escolha humana | S-110 | ✅ |
| 16.3 | A imagem que não gravou não vira linha no CSV | S-111 | ✅ |
| 16.4 | As doze threads no registro do que se perde | S-112 | ✅ |
| 16.5 | O cache de posições com trava e refusão | S-113 | ✅ |
| 16.6 | "Salvar todos" avisa quem precisa saber | S-114 | ✅ |
| 16.7 | A galeria entra no que o projeto preserva | S-115 | ✅ opção 2 (extrato humano) |

**Critério de saída:** nenhum gesto de leitura altera dado gravado; fechar a janela durante
qualquer das 12 operações longas diz o que se perde; e `data/gallery/` tem destino declarado —
versionado, ou com backup documentado, mas **decidido**.

**Conferido em 2026-08-18, parte a parte:** as S-109 e S-111 fecham o primeiro; a S-112 registra
as doze operações; e o destino da galeria **está decidido** — opção 2, o extrato humano, com
`data/gallery_human.jsonl` marcado como versionado na tabela de persistência do
`ARCHITECTURE.md` e o par `--export-human`/`--import-human` no `cvoff-gallery`.

---

## Fase 17 — O laço interno, e o custo de abrir um livro ✅ concluída (2026-08-18)

| # | Entrega | Ref. | Estado |
|---|---|---|---|
| 17.1 | `Ctrl+S` deixa de reler o `labels.csv` inteiro na thread da janela | S-116 | ✅ **718 → 0 ms**, os dois cortes; e o violeta das caixas deixou de depender de salvar amostra |
| 17.2 | A seta não executa dois painéis ao mesmo tempo | S-117 | ✅ |
| 17.3 | O DatasetPanel não perde a página e a seleção a cada correção | S-118 | ✅ |
| 17.4 | Uma varredura por livro em vez de duas | S-119 | ✅ um botão, uma passada — e a fusão de fila parava de encurtar a fila numa varredura retomada |
| 17.5 | A varredura da Galeria é retomável e diz até onde foi | S-120 | ✅ |
| 17.6 | O acervo varrido sem janela aberta | S-121 | ✅ |
| 17.7 | O OCR ligado por padrão | S-122 | ✅ medido — **não ligar** |
| 17.8 | A varredura por posição responde igual com 1 e com N processos | S-138 | ✅ |
| 17.9 | A consulta por nome alcança as duas cores, e paga o porteiro | S-139 | ✅ |
| 17.10 | O índice sem a cópia (885 → ~476 MB) e o cache que não cabe na memória | S-140 | ✅ índice −44,0%; cache por colocação — trocar de livro deixou de custar 0,59 s e 63 MB |
| 17.11 | O processo filho não reimporta `torch` e a UI | S-141 | ✅ 223 → 15 MB por filho; arranque de 8 processos 3,24 → 0,76 s — **por outro caminho que o do enunciado** |
| 17.12 | A página concluída se diz concluída, e o verde aparece na primeira visita | S-142 | ✅ |

**Critério de saída:** o ciclo corrigir→salvar→seguinte custa menos de 0,05 s de janela
travada; abrir um livro novo custa **uma** varredura; o número de livros do acervo com índice
sai de 7; e a mesma pergunta à base devolve a mesma resposta duas vezes seguidas.

**Medido em 2026-08-18, os quatro:**

| parte | alvo | medido |
|---|---|---|
| ciclo corrigir→salvar→seguinte | < 0,05 s | **0,000 s** — os dois cortes da S-116 |
| abrir um livro novo | **uma** varredura | uma (S-119): a fila sai da passada da Galeria |
| livros do acervo com índice | > 7 | **10** (`data/gallery/*.index.json`) |
| a mesma pergunta, duas vezes | mesma resposta | S-138, travada por teste |

---

## Fase 18 — Quando algo dá errado ✅ concluída (2026-08-18)

> O bundle da S-55 é `console=False` e não grava log por padrão. Hoje, uma janela que não abre
> não deixa rastro nenhum.

| # | Entrega | Ref. | Estado |
|---|---|---|---|
| 18.1 | O PDF que não abre não troca o livro por dentro | S-123 | ✅ |
| 18.2 | Um `settings.json` inválido não impede a janela de abrir | S-124 | ✅ |
| 18.3 | O worker de OCR loga a exceção como os outros cinco | S-125 | ✅ |
| 18.4 | Os `cvoff-*` falham em pt-BR, com código de saída por classe | S-126 | ✅ |
| 18.5 | O bundle congelado deixa rastro em disco | S-127 | ✅ |
| 18.6 | A CI roda o ambiente que o CONTRIBUTING promete | S-128 | ✅ |

**Critério de saída:** as três falhas mais prováveis — PDF corrompido, `settings.json`
inválido, checkpoint de outra `arch_version` — produzem mensagem em pt-BR e rastro em disco,
no checkout **e** no `.exe`.

**A metade do `.exe` foi exercitada em 2026-08-18, pela primeira vez** — ela exigia um bundle, e
o bundle estava obsoleto desde 2026-08-09 até a S-135 ser refeita. **Duas das três estavam
erradas** (S-174): PDF corrompido e checkpoint ilegível saíam com `1` e traceback em inglês,
onde `1` quer dizer "o programa falhou" e quem falhou era um arquivo. Corrigido e reconferido no
`.exe`: `2`, `0`, `3` e `0`, com frase pt-BR e `logs/chessvisionoff.log` gravado nos quatro.

---

## Fase 19 — A detecção, e a documentação que descreve o programa que existe ✅ concluída (2026-08-18)

| # | Entrega | Ref. | Estado |
|---|---|---|---|
| 19.1 | A página com `/Rotate` não gera candidato fantasma | S-129 | ✅ (1 página em 18.767) |
| 19.2 | A nota de textura não muda com a resolução do recorte | S-130 | ✅ medido — **12 de 260 decisões viram, e nenhuma muda o que exporta** |
| 19.3 | O caminho de contorno ganha instrumento antes de ajuste | S-131 | ✅ instrumento feito; limiares **não** ajustados |
| 19.4 | O que o gate não enxerga, escrito onde ele decide | S-132 | ✅ medido — **0 de 3 diagramas reparados exportam**, e é aritmética |
| 19.5 | S-76 e S-77 registradas | S-133 | ✅ |
| 19.6 | O índice de documentos, verificável por teste | S-134 | ✅ |
| 19.7 | Os números vivos: ARCHITECTURE, README, bundle | S-135 | ✅ bundle refeito (696 → **684 MB**), e ele achou `pythonnet`/`clr_loader` ainda dentro, três fases depois da S-69 |
| 19.8 | `app_tkinter.py` dobrou: reabrir o item ou registrar o novo placar | S-136 | ✅ **registrar** — 1.440 linhas, travadas por catraca |
| 19.9 | `mypy` olha o produto; `streamlit` sai das obrigatórias; `atomic_io` ganha guarda | S-137 | ✅ |

**Critério de saída:** nenhum número citado em documento diverge do disco sem que a suíte
falhe, e `cvoff-census` mostra o efeito das mudanças de detecção sobre o acervo — com a regra
da S-82: perder suspeito é o objetivo, perder candidato do tamanho de um diagrama impresso
precisa de justificativa uma a uma.

---

## Os dois achados que a implementação trouxe (2026-08-18)

Nenhum dos dois veio de avaliação: vieram de **implementar** a Fase 17 e olhar para o lado.
Especificados em [SPEC_FASE14.md](SPEC_FASE14.md).

| # | Entrega | Ref. | Estado |
|---|---|---|---|
| A1 | A varredura por posição para em vez de esperar para sempre por um pedaço que não volta | S-171 | ✅ reproduzido (5 de 6 pedaços, espera infinita) e detectado em 0,3 s |
| A2 | O critério de saída de uma fase envelhece igual a um número do README | S-172 | ✅ duas guardas novas, verificadas contra um documento mentiroso |
| A3 | Uma passada descartada não pode virar "a base não conhece" | S-173 | ✅ e ele foi **criado pela A1** — está registrado assim |

**A1 apareceu ao escrever a S-141** — o item que faz o filho arrancar nu. Ele registrou o
próprio preço (*"o filho morre ao desempacotar e o laço de espera fica sem resposta"*), e
perguntar quanto custava esse "sem resposta" mostrou que o travamento já existia antes, por um
caminho muito mais provável: qualquer filho que morresse.

**A2 apareceu ao refazer o bundle da S-135.** Com o `.exe` medido e travado por teste, o
`ROADMAP.md` continuava dizendo que ele não tinha começado.

**A3 é consequência da A1, e o registro disso é o ponto.** Consertar o travamento criou um
estado que não existia — passada descartada sem cancelamento — e esse estado caía num defeito
de corrupção latente: o cache gravaria "a base não conhece" sobre milhares de colocações que
ninguém procurou. Um conserto que abre um caminho novo tem de ser seguido até onde ele
desemboca, e é isso que a A3 é.

---

## O primeiro dia, executado (2026-08-16)

Os quatro itens do *"se houver só um dia"* — **S-95, S-98, S-109 e S-111** — foram
implementados, e a **S-96**, a **S-97** e metade da **S-99** entraram logo em seguida. Os quatro primeiros são os que corrompem em
silêncio e pioram enquanto o programa é usado; é por isso que vieram antes de qualquer melhoria.

| | antes | depois |
|---|---|---|
| testes | 1.543 | **1.588** (+45, todos travando decisão) |
| `data/field_set.jsonl` — com FEN | **0** de 39 | **31** de 39 |
| `ruff` · `mypy` | limpos | limpos |
| `cvoff-field` — exatidão | `1.000` sobre uma alucinação (n=1) | **`1.000` sobre 28 exportados**, com 31 de 39 conferidos |
| `cvoff-field` — exportados e errados | não media | categoria própria, com a lista e a confiança |
| `cvoff-field` — exportação | `0.7179` | `0.7179` geral e **`0.6562` limpa** (7 de 39 em páginas com treino) |
| `cvoff-audit` — vazamento de split | não media | **3 triplas listadas, com o split de cada membro** |

**O que cada um passou a impedir:**

- **S-95** — corrigir o tabuleiro e anotar a página grava a **correção**. Dirigido na janela
  (`Karpov p100`, 6 diagramas): o modelo leu `1kb4r/2q2p2/pp4r1/...`, a correção foi
  `4k3/8/8/8/8/8/8/4K3`, e foi a correção que entrou; os 5 diagramas não conferidos saíram com
  `placement` vazio. A capa do Yusupov saiu do conjunto, com backup em
  `data/field_set.jsonl.bak-20260816_153807`.
- **S-98** — `groups_by_origin` entra na união de grupos do `resolve_splits`, e o
  `cvoff-audit` lista os três vazamentos com os membros e os splits. **Lista e não move**: a
  direção que não contamina é sempre em direção ao `train`, e quem aplica é gente.
- **S-109** — percorrer os oito headers com `Tab` deixou de rebaixar a procedência de
  `database` para `manual`, e deixou de reescrever o livro no disco oito vezes. Três dos sete
  testes novos falham no código anterior.
- **S-111** — `atomic_io.write_image` confere o retorno do `cv2.imwrite` e levanta em pt-BR. O
  `labels.csv` não ganha mais linha órfã quando o disco enche.

**E a S-96 entrou logo em seguida**, fechando a metade do relatório: `cvoff-field` passou a
separar **três** medidas — taxa de exportação (quanto sai), exatidão de campo (quanto do que
saiu está certo) e exatidão condicional —, a contar **"exportados e errados"** como categoria
própria, e a **recusar** a palavra "exatidão" abaixo de 50% de conferíveis, dizendo o `n` e o
mínimo no lugar do número.

O caminho de medição foi exercitado ponta a ponta num conjunto descartável com uma referência
trocada de propósito, e o diagrama que saiu errado tinha **confiança 0,993** — a demonstração
do item numa linha: nenhum gate razoável o barraria, e a taxa de exportação o conta como
sucesso.

**E a S-97 fechou a terceira metade da régua, com um número que não era esperado.** O
relatório passou a declarar quais páginas do conjunto têm amostra em `train` e a publicar a
taxa **limpa** ao lado da geral:

```
    **Taxa de exportação** ....... 0.7179  (28/39)
    Em páginas com treino ........ 7 de 39  (18%)
    **Exportação limpa** ......... 0.6562  (21/32)
```

**6,2 pontos percentuais de diferença.** Os sete diagramas contaminados exportam **todos**, o
que faz da contaminação um viés **para cima** e não ruído. Contra o alvo de 0,85 da Fase 7, a
distância real é de **0,19** e não de 0,13 — e essa era a régua com que quatro itens de spec
foram reprovados.

Nada é removido do conjunto: 39 diagramas não comportam jogar 18% fora. O que muda é que o
viés é **publicado em vez de estimado**, e que a tela avisa antes do clique
(`⚠ 8 amostra(s) de treino desta página`), para que a S-99 saiba de onde crescer.

**E a S-99 teve a metade da FEN feita**, o que fez a exatidão de campo deixar de ser código e
virar número. O conjunto continua com **17 páginas**, mas **31 dos 39 diagramas têm posição de
referência** — lidos um a um no recorte warpado com grade `a-h`/`1-8`, transcritos antes de
olhar o que o modelo tinha lido.

```
    Conferíveis .................. 31 de 39 anotados  (79%)
    **Exatidão de campo** ........ 1.0000  (28/28 exportados)
    Exatidão condicional ......... 0.9032  (28/31)
    **Exportados e errados** ..... 0
```

### O número que reorganiza a leitura da Fase 7

**As três leituras erradas são exatamente as três que o gate barrou** — confianças 0,058, 0,001
e 0,056. Nenhuma leitura errada passou.

O modelo **não exporta lixo. Ele se recusa a exportar 28% do que existe.** O gate é preciso e o
que ele custa é recall. Isso muda onde o trabalho rende: em **detecção e cobertura**, não em
acurácia de leitura — e explica por que seis variantes de modelo deram sempre 27 ou 28 de 38
(7.7). Elas estavam melhorando algo que já estava certo.

### As ressalvas, e a primeira é sobre quem anotou

**Eu errei em 5 das 6 divergências contra o modelo**, todas de **cor** da peça. Resolvi cada uma
comparando a casa com uma peça branca e uma preta do mesmo diagrama; num caso foi preciso medir
o brilho do miolo (114,7 na disputada contra 170,5 na torre branca e 98,4 no cavalo preto) para
aceitar que eu estava errado. Um sexto erro — fila deslocada, rei branco esquecido — foi pego
pela **guarda de legalidade**, não por mim. Taxa bruta: **6 em 31, ~19%**.

Daí as outras três ressalvas:

- **erro correlacionado é invisível**: nos 23 em que eu e o modelo concordamos de primeira, se
  os dois erramos igual a referência está errada e a métrica não acusa. O conjunto é **mais
  forte que a saída do modelo**, e **não** é verdade independente no sentido estrito;
- **o 1,000 é sobre o regime fácil**: 22 dos 28 exportados são `vetorial` ou `fonte`;
- **a resolução não melhorou**: faltam as 43 páginas, os regimes abaixo do alvo e os ≥5
  diagramas na faixa 0,60–0,80. O conjunto mede **leitura** agora; continua sem distinguir dois
  modelos, que é o que a S-107 vai precisar.

**Um número que muda de leitura.** Com a máquina ociosa, `cvoff-field` custa **0,361 s por
diagrama** — e não os 0,526 s medidos durante a avaliação, que saíram com seis auditorias
rodando. A ressalva registrada em "O que esta avaliação não olhou" estava certa, e o número de
2026-08-11 (0,331 s) continua sendo o comparável.

---

## O retreino de produção, medido (2026-08-16)

**A decisão: não promover o `mhsp`. O `AugmentConfig()` padrão continua `aug0`.** Pendente
desde 2026-08-11, e esta é a primeira vez que houve régua para tomá-la.

Dois treinos sobre o **mesmo** dataset, semente e número de épocas — a regra do CONTRIBUTING —,
3h40 de CPU, seguidos de três medições de campo no mesmo estado de máquina:

```bash
cvoff-train --fresh --seed 42 --model models/controle_20260816.pt
cvoff-train --fresh --seed 42 --augment mhsp --model models/mhsp_20260816.pt
cvoff-field --model models/controle_20260816.pt --json docs/metrics/controle_20260816.json
cvoff-field --model models/mhsp_20260816.pt     --json docs/metrics/mhsp_20260816.json
cvoff-field                                     --json docs/metrics/producao_20260816.json
```

| | produção (2026-08-09) | **controle `aug0`** | `mhsp` |
|---|---|---|---|
| `dataset_size` (treino) | 2.660 | **3.173** | 3.173 |
| `split_hash` | `cf7b6cf5…` | `41c44c1c…` | `41c44c1c…` |
| melhor época | 10 | 5 de 8 | 8 de 8 |
| `val_board_exact_acc` | 0,9874 † | **0,9818** | 0,9766 |
| **taxa de exportação** | 0,7179 (28/39) | **0,7436 (29/39)** | 0,7179 (28/39) |
| exportação limpa | 0,6562 (21/32) | **0,6875 (22/32)** | 0,6562 (21/32) |
| **exatidão de campo** | 1,0000 (28/28) | 1,0000 (28/28) | 1,0000 (28/28) |
| exportados e errados | 0 | 0 | 0 |
| reparos do decode / diagrama | 0,590 | 0,769 | **0,333** |
| custo por diagrama | 0,378 s | 0,467 s | 0,346 s |

† Sobre outro `split_hash` e 513 amostras a menos: **não é comparável**, e está na tabela só
para que ninguém o compare depois sem ver esta linha.

### Por que "não promover"

**A exatidão de campo é 1,0000 nos três, sobre os mesmos 28 diagramas.** O conjunto não
distingue os três modelos em *correção* — é exatamente a ressalva que o commit da S-99 deixou
escrita, e ela se confirmou. Sobra a taxa de exportação como único número discriminante, e ela
**favorece o controle**: 29 contra 28.

**Os −40% de reparo do decodificador se confirmaram, e ficaram maiores: −57%** (0,333 contra
0,769 por diagrama). Era o argumento de 2026-08-11 a favor do `mhsp`. Mas a S-96 estabeleceu
que contagem de reparo não mede correção, e agora existe um número que mede — e ele diz que
os dois leem igualmente certo. **A vantagem de reparo não compra nada mensurável.**

**E o orçamento de treino não é a explicação.** O candidato histórico `s40_mhsp_16ep.pt`, cujo
nome sugere 16 épocas, tem `total_epochs: 8` e `best_epoch: 8` nos próprios metadados: rodou 8,
como este. A comparação é do regime de aumento, não do número de épocas.

### As quatro ressalvas, e a primeira invalidaria a conclusão se fosse maior

- **A diferença de 1 diagrama é de um diagrama sem FEN de referência.** O que o controle
  exporta a mais é `GALLAGHER p80`, e o `field_set.jsonl` o traz com `placement` vazio. Não se
  sabe se aquela leitura está certa — só que passou o gate com confiança acima de 0,80. É o
  modo de falha que a S-96 nomeou, e ele está do lado do vencedor. **A S-99 deve conferir esse
  diagrama antes de a diferença ser usada em qualquer outro argumento.**
- **`n = 28` exportados conferíveis, de 39 anotados em 17 páginas.** Uma diferença de um
  diagrama não sobrevive a nenhum teste de significância, e nada aqui pretende que sobreviva.
  Isto é um veto a promover, não uma prova de superioridade.
- **18% do conjunto está em páginas com amostra de treino**, e desta vez a armadilha da S-97
  fechou: as duas páginas (`Karpov p80`, `Kemeri p187`) **entraram no treino destes dois
  modelos**. A taxa limpa está publicada ao lado por isso, e a ordem entre controle e `mhsp` é
  a mesma nas duas.
- **O `git_commit` dos dois checkpoints difere** (`d1a3eb0` e `c3a4ea8`) porque foram gravados
  em momentos diferentes de uma sessão que comitava outros itens. Nada em `src/` que afete
  treino mudou entre os dois: as S-110, S-112 e S-113 tocam UI, registro de operações e cache
  de posições.

### O que **não** foi feito, e é decisão sua

**`models/piece_classifier.pt` não foi trocado.** A receita da S-107 não inclui a troca, e ela
sobrescreve o modelo que o produto carrega (`config.py:168`). O controle está medido e pronto
em `models/controle_20260816.pt`, com `dataset_size = 3.173 ≥ 3.100` e taxa de exportação
**acima** da de produção sobre o mesmo conjunto — os 468 rótulos de correção humana que o
produto nunca viu. Promovê-lo é:

```bash
cp models/piece_classifier.pt models/piece_classifier_pre_20260816.pt
cp models/controle_20260816.pt models/piece_classifier.pt
```

E o `cvoff-audit --strict` da receita **não rodou porque não existe** — é a S-102, ainda
aberta. Rodou o `cvoff-audit` normal: 3.935 rótulos utilizáveis, 0 ilegais fatais, 1 PNG
sumido, redundância em **11,0%** (acima do teto de 10% da S-63) e 3 triplas cruzando split
(S-98). Nenhum é impeditivo, mas nenhum foi barrado por gate — foi lido por gente, que é
precisamente o que a S-102 existe para deixar de exigir.

**A mesma auditoria em 2026-08-23**, ao lado e não no lugar da de cima: **4.064** rótulos
utilizáveis, 0 ilegais fatais (mais 5 confirmadas à mão, que o comando lista à parte), 1 PNG
sumido, **444 órfãos** sem linha no CSV, 412 sem split e **as mesmas 3 triplas** cruzando split.
O que mudou de verdade é a redundância: de **11,0% para 1,2%** (47 amostras em 46 grupos), e não
foi esta auditoria que a baixou — foi o `cvoff-audit --dedupe` de **2026-08-21** (S-108), que
tirou **444 linhas de 382 grupos** e está registrado em `docs/metrics/dedupe_20260821_072042.json`.
Os **444 órfãos** de hoje são o outro lado dessa remoção: o dedupe tira a linha do CSV e deixa o
PNG no disco, e de fato **nenhum** órfão tem nome posterior a 2026-08-21 — tudo que o app gravou
depois entrou rotulado. O teto de 10% da S-63 deixou de ser violado; o PNG sumido e as 3 triplas
seguem de pé, e seguem sem gate, porque a S-102 continua aberta.

---

## O desempate entre épocas, medido (2026-08-17)

**A decisão: não mudar nada. O `>` estrito de `BestEpochPolicy.accepts` fica.** Dois números a
sustentam, e o segundo é o que decide.

### 1. Não há empate no máximo no dataset de hoje

O item nasceu de `docs/metrics/phase5_training.json`, onde o máximo é atingido por duas épocas
em **3 de 3** execuções. Nas três execuções de 2026-08-16/17 sobre o dataset atual — controle
`aug0`, `mhsp` e o treino com `--keep-ties` — isso aconteceu **0 de 3**:

| execução | máximo | épocas que o atingem | empate no máximo? |
|---|---|---|---|
| controle `aug0` | 0,981818 (época 5) | 1 | não |
| `mhsp` | 0,976623 (época 8) | 1 | não |
| `--keep-ties`, semente 42 | 0,981818 (época 5) | 1 | não |

**A explicação é a granularidade.** A validação passou de ~306 tabuleiros na Fase 5 para
**385** hoje: um tabuleiro vale 1/385 = 0,0026 em vez de 1/306 = 0,0033. Métrica mais fina,
empate mais raro. As três execuções tiveram empate **no meio** — a época 4 empatando a 2 no
`--keep-ties`, a 5 empatando a 4 no `mhsp` —, mas ali o desempate não mudaria nada: uma época
posterior venceu as duas por diferença real.

### 2. E 1,3 ponto de validação não move o conjunto de campo

O `--keep-ties` gravou `models/s104_empate.tie-e4.pt` (época 4, `tie_with_best_epoch: 2`), e
comparar os dois checkpoints responde uma pergunta **mais forte** que a do empate:

| | principal (época 5) | empatada (época 4) |
|---|---|---|
| `val_board_exact_acc` | **0,9818** | 0,9688 |
| `val_loss` | 0,005297 | 0,006170 |
| **taxa de exportação** | 0,7436 (29/39) | **0,7436 (29/39)** |
| exportação limpa | 0,6875 (22/32) | **0,6875 (22/32)** |
| **exatidão de campo** | 1,0000 (28/28) | **1,0000 (28/28)** |
| exportados e errados | 0 | 0 |
| reparos do decode / diagrama | 0,769 | 0,795 |

**1,3 ponto percentual de validação — cinco vezes a granularidade de um tabuleiro — e o
conjunto de campo não distingue as duas.** Se um gap de 1,3 pp não move nada, um gap de
**zero**, que é o que define empate, move menos ainda.

Então o desempate por `val_loss` regravaria 8,7 MB e correria o risco da S-57 por uma
diferença que a métrica de produto não enxerga — que é exatamente o que a razão escrita em
`accepts` proíbe. Ela fica, agora com número ao lado em vez de argumento.

### A ressalva

**O conjunto de campo não distinguir duas coisas não prova que elas são iguais.** É a mesma
limitação que a S-107 registrou: 17 páginas, `n = 28` exportados conferíveis, e nenhum diagrama
na faixa de confiança 0,60–0,80. O que este número autoriza é *não pagar* 8,7 MB por uma
diferença invisível; ele não autoriza dizer que as duas épocas leem igual. Quem quiser o
segundo enunciado precisa da S-99 fechada.

Os dois checkpoints ficam em `models/s104_empate*.pt` (fora do git, como todo `.pt`) e os
relatórios em `docs/metrics/s104_*.json`, para que a comparação seja refazível.

---

## O OCR por padrão, medido (2026-08-17)

**A decisão: não ligar. `ocr.enabled` continua `False`.** O item pedia a medição antes da
mudança — *"o número precisa ser medido nesta máquina antes de virar padrão"* —, e o número
não sustenta a mudança.

```bash
cvoff-field --ocr off      --json docs/metrics/s122_ocr_off.json
cvoff-field --ocr rapidocr --json docs/metrics/s122_ocr_rapidocr.json
```

| | `--ocr off` | `--ocr rapidocr` |
|---|---|---|
| **taxa de exportação** | 0,7179 (28/39) | **0,7179 (28/39)** |
| exatidão de campo | 1,0000 (28/28) | 1,0000 (28/28) |
| casas reparadas / diagrama | 0,219 | 0,219 |
| **custo por diagrama** | **0,367 s** | **1,469 s** |
| custo do conjunto inteiro | 11,7 s | 47,0 s |

**4,0× o custo, e nenhuma diferença em nada que o conjunto de campo mede.** Nem uma casa
reparada a mais, nem um diagrama exportado a mais.

### O que isso não diz

**O benefício da S-43 é real e está noutra métrica.** Ele é a procedência do lado a jogar
caindo de 87,8% `default` para 77,2% — e `cvoff-field` não reporta procedência de lado a
jogar. Quem mede isso é o `cvoff-sides`, que é outro comando e outra passada.

**E o conjunto de campo é o lugar errado para ver o ganho**: os 9 livros dele são
majoritariamente do acervo com camada de texto, e a precedência da S-43 só chama o motor onde
a camada de texto calou. O ganho vive nos **7 livros sem camada de texto**, e o conjunto quase
não os contém — é a mesma limitação de resolução que a S-107 e a S-104 registraram, aqui pela
terceira vez.

### Por que a decisão ainda assim é "não ligar"

O custo de 4× é medido e certo; o benefício é medido noutro conjunto e não aparece aqui. E o
custo agora tem um consumidor novo: o `cvoff-scan --all` da S-121 varre 17.823 páginas, e 4×
transforma uma noite de ~3,5 h em ~14 h.

Ligar por padrão seria impor esse fator a todo mundo por um ganho que só existe em 7 dos 34
livros. **O caminho que o número recomenda é o oposto:** ligar o OCR **por livro**, onde a
camada de texto falta — que é informação que o `cvoff-sides` já sabe produzir e que ninguém
ainda ligou à preferência.

Fica como pendência nomeada, e não como "não fizemos": o mecanismo pedido pelo enunciado
("ligado se o motor estiver instalado") é uma linha; o que falta é justificativa para ele.

---

## Sequenciamento sugerido

A regra é a das fases anteriores: **medição antes de mudança, e mudança antes de refatoração.**
Aqui ela tem uma consequência dura — a primeira semana quase não muda o produto, e é a semana
que decide se as outras cinco significam alguma coisa.

| dia | itens | por que nesta ordem |
|---|---|---|
| 1 | ~~**S-95** + **S-98**~~ ✅ | os dois defeitos que corrompem régua. Enquanto não fecharem, anotar página e salvar amostra pioram o que medem |
| 1 | ~~**S-109** + **S-111**~~ ✅ | mesma razão, do outro lado: são os dois que corrompem **dado** a cada gesto de uso |
| 2 | **S-96** + **S-97** + **S-100** | a exatidão passa a existir, a contaminação passa a aparecer, e o conjunto vigente passa a ser declarado |
| 3–4 | ~~**S-99** — anotar as 60 páginas~~ ✅ | feita em 22/08: 66 páginas, 115 diagramas, 30 livros. Era "a que destrava as outras", e destravou: os quatro modelos passaram a se distinguir |
| 5 | **S-101** + **S-102** | consertar o dedupe **antes** de rodá-lo; depois a auditoria passa a barrar |
| 5 | **S-103** a **S-106** | as quatro guardas baratas do treino, todas de horas |
| 6 | ~~**S-107** — o retreino, e a decisão do `mhsp`~~ ✅ | feito fora de ordem, em 2026-08-16. A régua respondeu **não promover**, e disse também que não distingue os dois modelos em correção — ver a seção acima |
| 7–8 | Fase 16 restante | o que se perde ao fechar a janela, o cache, a galeria |
| 9–12 | Fase 17 | o laço interno e a varredura única; é o que torna o acervo alcançável |
| 13–14 | Fase 18 | as três falhas mais prováveis, e o `.exe` que hoje é mudo |
| 15–18 | Fase 19 | detecção com instrumento, e os números dos documentos travados por teste |

**Se houver só um dia:** S-95, S-98, S-109 e S-111. Os quatro são defeitos que corrompem em
silêncio, os quatro são de horas, e os quatro pioram enquanto o programa é usado.

---

## Riscos e decisões que precisam do dono do projeto

| risco / decisão | observação |
|---|---|
| **A régua contaminada invalida vereditos anteriores** | S-38b, S-40, S-62a e S-62b foram reprovados por uma métrica que mede confiança e não correção, sobre um conjunto com 18% de páginas treinadas. **Não** significa que estavam errados — significa que não foram julgados. Reabri-los é decisão sua, e o custo é uma medição cada |
| **O `BASELINE.md` publica 0,9906 sobre um teste contaminado** | 3 triplas cruzam split, uma delas nas três partições. O número não está errado por muito, mas está errado para cima, e ninguém sabe por quanto até a S-98 |
| ~~**Anotar 60 páginas com FEN custa ~3 h suas**~~ ✅ feito em 22/08 | 66 páginas, `comparable` 96. O que ficou de dívida: 19 dos 115 diagramas estão anotados só com a caixa — 17 porque a hachura do scan não deixava separar 64 casas com segurança, e as duas do `p11` do Yusupov |
| **`data/gallery/` fora do git** | 5.953 anotações, 21 delas escolha humana explícita. Versionar custa ~11 MB de texto no repositório; não versionar custa tudo isso num disco que falhe. A decisão é sua, mas **precisa ser tomada** |
| **`cvoff-audit --dedupe` como está** | Não rodar até a S-101. Ele apagaria 6,2% do `test` e 8,4% do `val` |
| **A base de 18 GB e o índice de 885 MB** | O índice guarda a mesma informação duas vezes; 476 MB bastariam. Refazê-lo custa uma reconstrução, e a decisão pode esperar a Fase 17 |
| ~~**Retreinar produção com `mhsp`**~~ **decidido em 2026-08-16: não** | O `mhsp` exporta 28/39 contra 29/39 do controle, com exatidão de campo **idêntica** (1,0000 sobre os mesmos 28). Os −40% de reparo se confirmaram como −57% e não compram nada mensurável. O `AugmentConfig()` padrão continua `aug0` |
| **Trocar `models/piece_classifier.pt` pelo controle** — **reaberto em 2026-08-22, e é sua** | O "não" de 18/08 dizia que a diferença era um diagrama sem FEN, sobre 19 páginas. Sobre as 66 da S-99 fechada, remedidas com o código da S-176, o controle **exporta mais** (0,7913 contra 0,7652) e **não exporta nenhum errado** (exatidão de campo 1,0000 contra 0,9882). Em troca, a produção lê certo mais diagramas no total (`exact` 92 contra 89). Os dois erram diagramas diferentes. Não é ruído, e a régua que faltava agora existe |
| **Sem GPU** | Continua valendo: `torch 2.10.0+cpu`, época em ~9 min com a máquina livre. Os dois treinos da S-107 custam ~5 h de CPU |
