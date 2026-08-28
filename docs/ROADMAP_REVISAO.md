# Roadmap da revisão geral — Fases 52 a 65

Uma revisão do repositório inteiro, feita em 2026-08-27 sobre o ramo `fase-5-modelo-desempenho`,
com dezesseis leituras independentes cobrindo as 79.432 linhas de `src/`, as 2.195 de
`app_tkinter.py` e os 24 documentos de `docs/`. Especificação item a item em
[SPEC_REVISAO.md](SPEC_REVISAO.md) (S-296 em diante).

Este documento não propõe recurso novo. Ele é a lista do que **já existe e não funciona como o
próprio projeto declara** — e o que a torna diferente das treze revisões anteriores é a primeira
linha do placar, que não é sobre código nenhum.

**Data da avaliação:** 2026-08-27 · **Ramo:** `fase-5-modelo-desempenho` · **Método:** dezesseis
revisores independentes, um por área, cada um obrigado a citar `arquivo:linha`; em seguida uma
segunda passada de céticos, com a tarefa de **derrubar** cada achado antes de ele virar item

> **Onde mora a spec de cada item (S-NN).**
>
> | itens | arquivo |
> |---|---|
> | S-01 a S-36 | [SPEC.md](SPEC.md) |
> | S-37 a S-77 | [SPEC_FASE7.md](SPEC_FASE7.md) |
> | S-78 a S-82, S-143, S-175, S-176 | [ANALISE_DETECCAO.md](ANALISE_DETECCAO.md) |
> | S-83 a S-94 | [PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md) |
> | S-95 a S-142, S-171 a S-174, S-218, S-219 | [SPEC_FASE14.md](SPEC_FASE14.md) |
> | S-144 a S-170, S-177 | [SPEC_UI.md](SPEC_UI.md) |
> | S-178 a S-217 | [SPEC_TEXTO.md](SPEC_TEXTO.md) |
> | S-220 a S-234, S-294, S-295, S-324 | [SPEC_APARENCIA.md](SPEC_APARENCIA.md) |
> | S-235 a S-267, S-291 a S-293 | [SPEC_EDITOR.md](SPEC_EDITOR.md) |
> | S-268 a S-290 | [SPEC_ESTUDO.md](SPEC_ESTUDO.md) |
> | S-296 a S-323, S-325 a S-426 (menos S-324) | [SPEC_REVISAO.md](SPEC_REVISAO.md) |

---

# A primeira linha do placar

```
$ uv run pytest      4.508 passaram, 2 pulados, 3.593 subtests   130 s    verde
$ uv run ruff check .                                   4 erros           VERMELHO
$ uv run mypy                          30 erros em 8 arquivos             VERMELHO
```

As três verificações são as mesmas que o `CONTRIBUTING.md` manda rodar antes de abrir um PR e as
mesmas que `.github/workflows/ci.yml` declara. **Duas delas estão vermelhas neste ramo, e ninguém
foi avisado** — porque a CI só dispara em `main`:

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
```
`.github/workflows/ci.yml:4-7`

Os últimos oito commits deste ramo — as Fases 41 a 51 inteiras, mais a sala de estudo — entraram
sem que nenhuma das três verificações rodasse uma única vez. Não é que a CI tenha reprovado e
alguém tenha ignorado: **ela nunca foi convidada**. O `push` para um ramo `fase-*` não casa com
`branches: [main]`, e o `pull_request` só conta quando o alvo é `main`.

Isso reordena tudo o que vem depois. O projeto tem uma cultura de guarda automática rara —
`tests/test_docs.py` confere os números do README contra o disco, `cvoff-census --fail-on-loss`
transforma detecção em portão, a S-233 varre as peles atrás de comando escondido. Mas **a guarda
que não roda é igual à guarda que não existe**, e é por isso que a Fase 52 vem antes de qualquer
conserto: enquanto o portão estiver fechado, cada fase daqui em diante entra do mesmo jeito que
as onze anteriores entraram — sem ninguém olhar.

---

# O placar da revisão

Cento e oitenta e um achados, todos com `arquivo:linha` e citação do trecho que os prova.

| severidade | quantos | o que os define |
|---|---|---|
| alta | 48 | perde trabalho humano, trava a janela, ou dá resposta errada em silêncio |
| média | 90 | o usuário percebe, contorna, e o programa não avisa |
| baixa | 43 | atrito, inconsistência de vocabulário, número desatualizado |

| tipo | quantos |
|---|---|
| defeito de correção | 70 |
| robustez e concorrência | 22 |
| usabilidade | 21 |
| documentação | 19 |
| desempenho | 19 |
| interface | 17 |
| arquitetura | 8 |
| teste | 5 |

**A distribuição diz mais que os totais.** Setenta defeitos de correção num projeto com 4.508
testes verdes é o número que motiva a Fase 65: a suíte deste projeto trava *decisões* — e é
excelente nisso —, mas quase nenhum dos setenta é uma decisão revogada. São caminhos que ninguém
percorreu: o botão que só existe quando o painel está carregado, o `except` que engole o erro de
programação, a thread que termina depois de o usuário trocar de livro.

---

# A segunda passada, e o que ela mudou no placar

Os 181 achados acima são o resultado da **primeira** leitura. Antes de qualquer um deles virar
item, uma segunda passada os atacou: dezoito céticos, cada um com oito achados de severidade
alta ou média e a instrução de **derrubá-los** -- presumir que o achado está errado até que a
leitura do código prove o contrário --, mais oito caçadores nas costuras que a primeira não
percorreu.

Ela custou 4,1 milhões de tokens e 1.772 leituras de arquivo, e vale pelo que **desfez** tanto
quanto pelo que confirmou.

## Oito achados caíram

Quatro deles caíram porque a correção já estava na árvore quando o cético leu -- eles são os
primeiros itens desta revisão, e a "refutação" é o registro de que a correção pegou. Os outros
quatro caíram de verdade, e cada um ensina alguma coisa:

- **O OCR da página "não se declara ao `BusyRegistry`".** Declara-se ausente, de propósito:
  `tests/test_busy.py` mantém uma lista `SEM_REGISTRO` com os dois pontos exatos que o achado
  acusava, e ela é travada por teste. A omissão é uma decisão registrada, não um esquecimento --
  e o revisor não leu a lista.
- **"O extra `onnx` instala um pacote que ninguém importa."** O cético bloqueou o import de
  `onnx` com um *meta path finder* e chamou `export_onnx`: `OnnxExporterError: Module onnx is
  not installed!`, levantado de dentro do `torch`. Quem o importa é o exportador do torch, e não
  o nosso código. **Este é o achado que mais valia derrubar**: removê-lo teria quebrado a S-30.
- **"O `Tooltip` vaza o `after` quando o widget morre."** A premissa era falsa no nível do
  Tkinter: `Misc.after` registra o callback como comando Tcl via `self._register`, que o anexa a
  `widget._tclCommands`, e `Misc.destroy()` os apaga.
- **O erro de `mypy` em `result_panel.py:354` "repete-se em sete lugares".** Repetia-se em um.

## E a severidade caiu, muito

| movimento | quantos |
|---|---|
| alta → média | 23 |
| alta → baixa | 9 |
| média → baixa | 29 |
| média → alta | 1 |
| mantida | 76 |

**Quarenta e um achados desceram de faixa, e um subiu.** Não é que a primeira passada tenha sido
descuidada -- é que ler um caminho para *acusá-lo* e ler o mesmo caminho para *defendê-lo*
produzem dois textos diferentes, e o segundo é o que serve para planejar. O exemplo que resume:
o "`-v` que doze comandos recusam" era alta severidade até alguém rodar o comando de verdade e
descobrir que o traceback **sai** -- pelo `logging`, no stderr. O que sobrou foi uma linha de
conselho redundante, e ela é baixa.

Trinta e três achados voltaram como **confirmado-parcial**: existem, e o sintoma descrito
exagera ou erra em algum ponto. Cada um deles entrou na spec com a correção do cético, e não com
o texto original.

## Setenta e cinco achados novos

Os oito caçadores percorreram o que a primeira passada não tinha percorrido, e trouxeram
**75 achados** -- 12 de severidade alta -- em frentes que uma leitura por área não alcança:

| frente | achados | o que ela procurou |
|---|---|---|
| exceções engolidas | 10 | as 105 capturas largas, uma a uma: o que cada uma esconde quando o erro **não** é o esperado |
| segurança e rede | 10 | o único caminho em que bytes saem da máquina, mais `subprocess` e `os.startfile` |
| métricas e relatórios | 10 | os 100 arquivos de `docs/metrics/` contra a disciplina da S-219 |
| atalhos e catálogo | 10 | as quatro listas de comando cruzadas por script: catálogo, teclas, menu, peles |
| ida e volta dos dados | 10 | escrever e reler cada formato com valor de borda -- acento, aspas, campo vazio |
| primeiro dia | 9 | um clone sem `models/*.pt` e sem `data/samples/`, dirigido do zero |
| estado entre abas | 8 | o que cada aba não sabe quando o livro muda |
| unicode e caminho Windows | 8 | acento em caminho, `cv2.imread`, o limite de 260, nome de livro que vira arquivo |

**Os três piores não são de nenhuma área -- são de costura**, e é exatamente por isso que
dezesseis revisores por área não os viram:

1. **Sem `models/piece_classifier.pt`, o programa inventa a FEN e diz que deu certo.** É o estado
   de 100% dos clones novos, e `cvoff-infer` sai com código **0** mandando a FEN falsa para o
   stdout. Virou a S-320.
2. **O único conserto que o `cvoff-train` imprime num clone novo apaga os 4.454 rótulos
   versionados** -- e não destrava nada. Virou a S-321.
3. **O consentimento de envio não estava amarrado ao endereço.** O docstring afirmava que estava;
   nenhuma linha comparava. Trocar o endpoint por variável de ambiente passava a mandar a imagem
   do tabuleiro para outro host sem perguntar. Virou a S-319.

## O placar depois das duas passadas

```
achados                        256
  confirmados                  130   (90 inteiros, 40 com correção do cético)
  refutados                      8
  novos, da segunda passada     75
  de severidade baixa, aceitos  43   (checados durante a implementação)

severidade, depois da revisão
  alta                          36
  média                        115
  baixa                         62
```

---
---

# O fio que atravessa os quatro achados mais graves

Quatro achados de severidade alta contam a mesma história, e vale lê-los juntos antes das fases.

**1. O botão "Sem diagrama" apaga a anotação de campo da página, sem perguntar.**

```python
rascunho = FieldDraft(pdf_name=self.pdf_source.name, page=self.page_index) if empty else self._field_draft()
```
`app_tkinter.py:1383`

Com `empty=True` o rascunho nasce **do zero** — e `field_eval.upsert_page` substitui a página
inteira. Uma folha com doze diagramas revisados à mão desaparece num clique, sem confirmação e
sem desfazer. O conjunto de campo é a régua primária do projeto desde a Fase 7.

**2. "Recuperar o rascunho" apaga o arquivo de rascunho e marca a aba como limpa.**

O rascunho automático existe para sobreviver a um travamento. Recuperá-lo hoje devolve o texto à
tela **e apaga o arquivo**, deixando o trabalho de volta em memória volátil — exatamente o estado
de que ele tinha acabado de resgatar a pessoa. O segundo travamento perde tudo.

**3. O OCR interativo e a exportação de PGN disputam a mesma sessão de modelo.**

`_set_export_controls_enabled` (`app_tkinter.py:809`) desliga dois botões — `btn_export` e
`btn_cancel_export` — e deixa "Ler melhor diagrama", "Ler página" e "Selecionar área" acesos.
Mas `pdf_to_pgn.py:499` segura a sessão de modelo pela varredura inteira, e `service.py:692` é
onde o OCR da tela vai buscá-la. Clicar em qualquer um dos três durante uma exportação de 402
páginas — ~40 min, medidos pelo próprio projeto — põe a thread a bloquear no `acquire`: os botões
ficam cinzas, o rodapé congela em "Detectando diagramas…", e nada volta até a exportação acabar.
A varredura da Galeria tem o mesmo destino, e o `cancel_scan()` dela não solta nada, porque a
thread está parada antes de conferir o `Event`.

**4. `labels.csv` ausente ou vazio faz o treino apagar o `data/splits.csv` inteiro.**

```python
removed = set(existing) - set(names)
...
if added or removed:
    save_splits(splits_path, result)
```
`splits.py:265-269`

`names` vem vazio quando o CSV não existe, e `cli/train.py` libera esse caso de propósito
(`if args.force or not Path(args.csv).exists(): return None`). Reproduzido com o `.venv` do
projeto: um `splits.csv` de três linhas vira `filename,split
`. O único registro é um
`logger.info`, e o `ValueError("Dataset vazio")` só aparece **depois**. O `splits.csv` é o que
garante que amostra que era `test` continue `test`: perdê-lo não perde dado — perde a
*comparabilidade* de todo número já publicado em `docs/metrics/`.

Os quatro têm a mesma forma: **um caminho de exceção que o código trata como caminho normal.**
Nenhum deles é um algoritmo errado. Todos são o que acontece quando a resposta a "e se estiver
vazio?" nunca foi escrita — e é isso que a Fase 53 organiza.

---

# As catorze fases

Cada fase agrupa achados que **caem juntos**: mesma causa, mesmo arquivo, ou mesma ordem de
conserto. A ordem entre elas não é por severidade — é por dependência. A Fase 52 vem primeiro
porque sem ela nenhuma das outras treze é verificada; a Fase 53 vem em seguida porque perda de
trabalho humano não espera; a Fase 65 vem por último porque só depois de consertar é que se sabe
que teste faltava.

> **A tabela foi remontada depois da segunda passada, e a Fase 55 trocou de assunto.** Ela era
> "A folha do livro"; virou "O primeiro dia", porque a frente de mesmo nome trouxe dois achados
> que nenhuma leitura por área tinha visto e que valem mais que qualquer ajuste do visualizador:
> um clone novo lê FEN inventada, e o conserto que o programa imprime destrói o dado que ele
> entrega. O que era da folha do livro foi para onde cabia -- a virada que re-rasteriza e o
> campo de página que dessincroniza são defeitos de resposta errada, e entraram na Fase 53 com
> os outros; o resto do visualizador espera a Fase 56.
>
> **Alguns itens atravessaram fases pelo mesmo motivo.** A camada duplicada do PDF pesquisável
> era da Fase 58, a procedência da linha impressa era da 57, e a pergunta de documento sobre
> estilo era custo da 58: os três foram confirmados como alta severidade e esforço pequeno, e
> adiar um conserto barato para respeitar a fronteira de um documento é organizar documento em
> vez de consertar programa.

| fase | título | itens | estado | por que ela existe |
|---|---|---|---|---|
| 52 | O portão que nunca foi aberto | S-296 a S-299 | **entregue** | a CI não roda neste ramo, e duas verificações estão vermelhas |
| 53 | O trabalho humano que some | S-300 a S-313 | **entregue** | doze caminhos que apagam sem perguntar e sem desfazer |
| 54 | O que trava, e o que não cancela | S-314 a S-319 | **entregue** |  a janela congela, e três botões "Cancelar" não cancelam nada |
| 55 | O primeiro dia, e o estado entre abas | S-320 a S-323, S-421 a S-424 | **entregue** | um clone novo lê FEN inventada, e o conserto impresso apaga os 4.454 rótulos |
| 56 | O que so a CI podia mostrar | S-325 a S-327 | **entregue** |  o digest que via CRLF, a fita medida nas fontes desta máquina, a sonda de artefato ausente |
| 57 | A folha, o editor e a sala de estudo | S-328 a S-347 | **entregue** |  duas bases para a mesma folha, o desfazer que não vê formato, a sala que não grava |
| 58 | O texto lido: o que erra e o que custa | S-348 a S-357 | **entregue** |  a camada pesquisável duplicada, e 53% do custo numa pergunta repetida |
| 59 | O núcleo, revisitado | S-358 a S-364 | **entregue** |  3,4 s num tabuleiro ilegal, e a sentinela que volta a casar |
| 60 | Os dados e o treino | S-368 a S-376 | **entregue** |  o `splits.csv` apagado, o "melhor época" que indexa a lista errada |
| 61 | Os quarenta comandos | S-377 a S-385 | **entregue** |  o `-v` que a mensagem de erro manda usar e doze comandos recusam |
| 62 | O que sai no `.exe` | S-386 a S-391 | **entregue** |  95 MB não declarados dentro do bundle, e o motor de glifo que não sobe |
| 63 | A cor, o foco e a tecla | S-392 a S-403 | **entregue** |  três painéis fora do sistema de cor, onze diálogos sem Esc |
| 64 | A documentação que envelheceu | S-404 a S-412 | **entregue** |  oito itens entregues fora do índice, e o CER que o próprio relatório desmente |
| 65 | A suíte que não pegou nada disso | S-413 a S-420 | **entregue** |  4.508 testes verdes sobre 70 defeitos de correção |

**A coluna "estado" é o que esta tabela serve para responder.** Ela é lida antes de qualquer
outra coisa por quem retoma o trabalho: item sem marca é item por fazer, e a ordem de execução
está no fim deste documento. A spec de cada um está em [SPEC_REVISAO.md](SPEC_REVISAO.md), e o
que foi **medido** de cada item entra lá, junto do critério de aceite -- inclusive quando a
medição desaconselhar a mudança.

---

## Fase 52 — O portão que nunca foi aberto

**O achado.** `.github/workflows/ci.yml:4-7` dispara em `main`. O trabalho acontece em
`fase-5-modelo-desempenho`. Nas onze fases entregues neste ramo, as três verificações rodaram
zero vezes.

**O que se acumulou enquanto ninguém olhava:** quatro erros de `ruff` (dois blocos de import
desordenados, um import morto em `cli/editor_inventario.py:32`, e um `zip()` sem `strict=` em
`text/rico.py:698` que é um `pairwise` legítimo) e trinta de `mypy`, concentrados em
`ui/texto_panel.py` (doze), `ui/pdf_panel.py:386-387` (onze) e `ui/result_panel.py:354`.

**A tentação a evitar.** Vinte e quatro dos trinta erros de `mypy` são a mesma coisa: um
`lambda n=nome:` dentro de laço, que o `mypy` não infere, e um `dict[str, object]` passado com
`**` a uma assinatura de `tkinter` cheia de `Literal`. Nenhum deles é defeito. A saída fácil é
`# type: ignore` em vinte e quatro linhas; a saída certa é `functools.partial` onde cabe e
`dict[str, Any]` onde o `tkinter` não deixa ser outra coisa — e um `# type: ignore` **com o
motivo escrito** só onde a biblioteca é que está errada.

**Um quarto item, e ele é sobre a guarda e não sobre o erro.** A guarda de caminho da S-219
(`tests/test_docs.py`, "nenhum relatório publica a raiz do disco") só acusa o que começa pela
raiz **atual** — num *worktree* ela passa em verde sobre um arquivo defeituoso. É a mesma classe
de problema da CI: uma guarda que não olha onde o trabalho está.

## Fase 53 — O trabalho humano que some

Doze caminhos, e o denominador comum é que **nenhum deles pergunta**.

- **"Sem diagrama"** substitui a página anotada por uma vazia (`app_tkinter.py:1383`).
- **"Tirar o selecionado"** usa `selected_index`, que vale `0` com a lista vazia: a guarda
  `0 <= 0 < len(boxes)` passa sempre e o comando tira da anotação um diagrama que ninguém
  selecionou (`app_tkinter.py:1400`).
- **"Recuperar o rascunho"** apaga o arquivo e marca a aba como limpa (`ui/texto_panel.py:2165`).
- **Exportar `.txt`** marca o `.cvtxt` como salvo, o que desliga o rascunho automático e faz
  "Ler folha" descartar sem perguntar (`ui/texto_panel.py:2302`).
- **O comentário digitado e não confirmado** some ao fechar o programa: nem `salvar_agora` nem
  `_on_close` chamam `gravar_comentario` (`ui/study_panel.py:841`).
- **`abrir_pgn`** carimba o livro aberto sobre o `SourcePDF` de cada partida, e um estudo de
  outro livro substitui em silêncio o estudo da mesma página (`ui/study_panel.py:1499`).
- **`cvoff-review`** apaga a fila de revisão de outro livro sem uma palavra (`cli/review.py:105`).
- **A fila de revisão** é fechada por índice posicional, e o índice envelhece entre abrir o item
  e salvar (`ui/review_panel.py:342`).
- **A busca na base** grava o resultado no livro que estiver aberto na hora, não no pesquisado
  (`ui/gallery_panel.py:864`).
- **"Salvar todos"** aborta em silêncio no meio do laço, com metade salva
  (`ui/result_panel.py:1202`).
- **A quarentena** move trabalho humano de um arquivo versionado para um que o git ignora
  (`audit.py:445`).
- **A coleta em quarentena** conta como gravado o que o `cv2.imwrite` recusou
  (`text/coleta.py:241`).

**A regra que a fase impõe.** Toda ação que substitui trabalho humano ou o move para fora do
alcance do git faz uma de três coisas: pergunta nomeando o que será perdido, grava um backup
recuperável, ou entra numa pilha de desfazer. Nunca zero das três.

## Fase 54 — O que trava, e o que não cancela

Três botões "Cancelar" que não cancelam:

- **O do treino** — nenhum chamador passa `cancel_event` (`ui/training_dialog.py:225`).
- **O da exportação de PDF pesquisável** — o `Event` é lido uma única vez, no argumento da
  chamada (`ui/texto_panel.py:2063`).
- **O da varredura da Galeria** durante uma exportação — a thread está parada no `acquire` e não
  chega a conferir o `Event`.

E quatro caminhos que travam a janela: o OCR da página, que não se declara ao `BusyRegistry` e
por isso não tem progresso, não tem cancelamento e morre calado ao fechar
(`app_tkinter.py:1488`); "Conferir com o modelo", que roda o `torch` na thread do Tk
(`app_tkinter.py:1704`); `abrir_pgn`, que lê o arquivo inteiro para a memória na mesma thread —
e `pgn_database/` tem arquivos de 8,6 GB e 10,3 GB (`ui/study_panel.py:1494`); e "Detectar
duplicatas", que sem guarda de reentrância vaza um `BusyToken` por clique
(`ui/dataset_panel.py:428`).

## Fase 55 — O primeiro dia

**Esta fase não existia na primeira passada.** Ela saiu inteira da frente *primeiro-dia* da
segunda: um clone do repositório, sem `models/*.pt` e sem `data/samples/`, dirigido do zero até
a primeira FEN. É o estado de 100% de quem instala, e nenhum dos dois achados dela aparece para
quem já tem o acervo montado -- que é toda a gente que já leu este código.

**Sem o classificador, o programa inventa a FEN e diz que deu certo** (S-320). `load_model` caía
num modelo não treinado e o devolvia como se tivesse carregado; `models/*.pt` está no
`.gitignore`. Medido num livro real: o rodapé anuncia "Diagramas detectados: 1" e o tabuleiro
mostra `KKKKKKKK/KKKKKKKK/…` com confiança 0,081. No terminal é pior -- `cvoff-infer` sai com
**código 0**, a FEN falsa no stdout e o aviso no stderr, então `cvoff-infer livro.pdf > fen.txt`
grava um arquivo limpo de mentiras. A primeira FEN da vida de quem instala era ruído.

**E o único conserto que o programa imprime destrói o dado que ele entrega** (S-321). Num clone
limpo, `data/labels.csv` vem com 4.454 linhas e `data/samples/` vem com um `.gitkeep`. O
`cvoff-train` parava com "conserto: `cvoff-audit --drop-missing`", e seguir a instrução reduzia o
CSV a **um cabeçalho** -- sem destravar nada, porque os rótulos utilizáveis continuavam zero. O
primeiro comando que o recém-chegado roda mandava apagar o único dado que o repositório entrega.

**O que sobrava desta fase virou a S-421 a S-424, entregues em 2026-08-28:** toda mensagem de erro
mandava olhar um log que não existe num checkout (S-421); dois comandos não conseguiam imprimir o
`--help` com a saída redirecionada no Windows (S-422); a aba Texto vinha com o motor que nunca
funciona num clone novo, tendo `auto` ao lado (S-423); e a tabela "Resolução de problemas" do
README cobria o modelo que quase ninguém usa e não o que falta sempre (S-424).

## Fase 57 — A folha do livro, o editor e a sala de estudo

O visualizador de PDF é o painel mais usado do programa e o que mais mistura convenções.

**A página é contada em duas bases ao mesmo tempo.** O campo e o rodapé de mensagem dizem base 0;
o rodapé de documento e o título da janela dizem base 1 (`ui/pdf_panel.py:1069`,
`app_tkinter.py:1240`). Quem lê a tela inteira vê dois números para a mesma folha.

**E dois caminhos ainda desalinham o retângulo do diagrama da imagem embaixo dele:** mudar o DPI
não invalida a página rasterizada (`ui/pdf_panel.py:1049`), e o piso da seleção de área é medido
em pixel de tela, e não de página, o que faz o mínimo variar oito vezes conforme o zoom
(`ui/pdf_panel.py:1424`). O terceiro -- o campo de página que dessincronizava -- saiu na S-305.

Mais: PDF protegido por senha troca todo o estado do programa e deixa a tela no livro anterior —
a S-123 está furada (`ui/pdf_panel.py:988`); a roda sobre qualquer janela sobreposta ao canvas
rola o PDF e engole o evento (`ui/pdf_panel.py:808`); a dica de "Ajustar a largura" promete que
`Ctrl+roda` faz o mesmo, e `Ctrl+roda` faz outra coisa (`ui/pdf_panel.py:505`); e aumentar,
diminuir e ajustar o zoom não têm tecla nenhuma (`ui/atalhos.py:172`).

### O editor, dentro da mesma fase

A Fase 36 impôs a regra certa — *todo atributo mora no documento, não no widget* — e as Fases 37
a 42 a cumpriram. O que sobrou são as bordas.

**O desfazer não vê a formatação.** Negrito, cor, realce e "limpar formato" não entram em pilha
nenhuma, e o `Ctrl+Z` seguinte desfaz outra coisa (`ui/texto_panel.py:1288`). Desfazer e refazer
também perdem cursor, seleção e rolagem, jogando a pessoa para o topo (`ui/texto_panel.py:1898`).

**O zoom da vista não redimensiona nada com estilo ou corpo:** `_pintar_faixas` esvazia
`_fontes_desenhadas` **antes** do laço que deveria refazê-las (`ui/texto_panel.py:1709`).

**A aba é a única que nunca segue a pele nem o tema** — chama `tokens.cor` cru em vez de
`theme.cor_atual` (`ui/texto_panel.py:1042`).

**A exportação perde coisas que ela mesma declara não perder:** o `.md`/`.html` da aba nunca
recebe `recortes`, então todo diagrama sai sem imagem — e a aba Estudo faz certo
(`ui/texto_panel.py:2034`); o `.md` perde `estilo` e o relatório declara "perdido nada"; o
`.html` emite classes `estilo-*` sem regra CSS nenhuma (`text/exportacao.py:212`, `:345`); o
`.rtf` joga fora o recorte do diagrama, contra a tabela do próprio módulo, e não conta a perda
(`text/exportacao.py:439`).

E três atritos: a janela de busca não responde a Enter nem a Esc (`ui/texto_busca.py:105`); três
comandos do catálogo com rótulo próprio fazem a mesma coisa (`substituir_todos` = `substituir`,
`salvar_texto_como` = `salvar_texto`); e a barra de formato não acompanha o cursor movido por
seta, `Home`, `End` ou `PgUp`, então os interruptores mentem sobre o trecho.

### A sala de estudo, dentro da mesma fase

A Fase 43 acertou a fundação: o estudo é dado. As pontas que ficaram:

- `jogar_a_linha_do_livro` carimba "linha impressa no livro" no nó errado quando o lance corrente
  já tinha continuação (`ui/study_panel.py:1325`).
- Com a análise contínua ligada, a gravação por inatividade nunca dispara: o motor reagenda o
  temporizador a cada ~800 ms (`ui/study_panel.py:626`).
- `write_pgn` escreve sem `atomic_io`, ao contrário da exportação da mesma aba
  (`ui/study_panel.py:1699`).
- `Ctrl+Z` depois de virar o tabuleiro não desfaz nada e ainda gasta um passo da pilha.
- O comentário da raiz sai duas vezes em todo `.md`/`.html`/`.rtf` (`estudo_saida.py:102`).
- `estudo_aberto` é gravado no estado da aplicação e nunca lido: reabrir não volta para a mesa.
- A confirmação de apagar variante subconta os lances — ignora as subvariantes.
- O botão "Recorte" promete ficar cinza sem âncora, nunca fica, e troca o próprio rótulo para
  "Esconder recorte" sem nada ter aparecido.

## Fase 58 — O texto lido: o que erra e o que custa

**Dois defeitos de correção primeiro.** A camada invisível do PDF pesquisável **sai duplicada**:
`_corpo_que_cabe` tem nome de sonda e escreve (`text/pdf_pesquisavel.py:258`) — toda linha entra
duas vezes. E `dicionario.escolher` trata pontuação de borda como ambiguidade e recusa a correção
certa (`text/dicionario.py:233`).

**Depois o custo, que é grande e mensurável.** `ler_pagina` refaz a amostragem de negrito e
itálico **do livro inteiro** a cada folha: 3,2 s por página, 53% do custo total
(`text/leitor.py:1026`). `unir_pingos` compara cada pingo com toda caixa da página: 336 ms por
folha, 42% da leitura de glifo (`text/boxes.py:278`). `ler_pagina` abre o PDF três vezes por
folha, e o empréstimo de documento da S-61 nunca chegou ao caminho de texto. A aba renderiza a
mesma folha duas vezes, e a segunda trava a thread do Tk por ~355 ms.

**E cinco coisas que o texto perde ou carimba errado:** a junção da hifenizada nunca roda no
caminho de leitura, e o texto sai com `em- barrassment` (`text/pagina.py:413`); `montar` joga o
diagrama que atravessa a calha numa coluna só, desfazendo a regra de transversal da S-193;
`e_fila_de_eixo` apaga em silêncio uma linha legítima como `1 2 3 4 5 6 7 8`; o cabeçalho e o
rodapé saem da camada do PDF mas são carimbados com a procedência do glifo; e léxico vazio faz a
conferência sublinhar a página inteira em vez de se desligar (`text/lexico.py:227`).

## Fase 59 — O núcleo, revisitado

- **`decode_constrained` gasta 3,4 s num tabuleiro ilegal** — 26.000× o caso normal — e roda duas
  vezes por diagrama (`decode.py:277`).
- **A sentinela `(0, 0, 1, 1)` do `hybrid` volta a casar** com qualquer contorno ancorado na
  origem da página (`detection/hybrid.py:733`).
- **Com `CONSTRAINED_DECODING` ligado, a `SingleLegalRule` nunca dispara** — a regra que a cascata
  documenta como "nunca errou em 320" (`orientation.py:231`).
- **`labels_from_fen` converte caractere desconhecido em `empty`**, e a segunda opinião então
  anuncia acordo total sobre uma leitura lixo (`fen_utils.py:212`).
- **`detect_diagrams` corta a página em `max_boards` sem aviso**, e o corte é por posição, não por
  score, enquanto `detect_boards` avisa.
- **`order_quad_points` duplica um canto num quad a 45°** — que é justamente o que tira nota
  máxima de geometria (`board_detection.py:208`).
- **O censo de recusas grava contraste 0,0000** para candidatos cujo contraste acabou de medir.

## Fase 60 — Os dados e o treino

Além do `splits.csv` apagado (S-368, o achado 4 da abertura):

- `best_epoch` retomado do checkpoint indexa o histórico **desta** execução: um treino
  bem-sucedido termina como "Falha no treino" (`training.py:452`).
- `_resolve_best_metric` não confere `best_metric_name`: compara `-train_loss` com acurácia exata
  por tabuleiro (`training.py:451`).
- Sem arquivo de splits, `split_hash` vazio é comparado com vazio, e a métrica incumbente vem de
  outra partição (`training.py:450`).
- Os metadados do checkpoint gravam `batch_size`, que a cabeça por tabuleiro ignora, e omitem o
  `boards_per_batch`, que ela usa.
- No Windows, um *handle* aberto no destino faz toda escrita atômica falhar com `PermissionError`
  cru (`atomic_io.py:48`).
- BOM de UTF-8 no `labels.csv` torna o dataset inteiro ilegível, com mensagem que não diz a causa.
- `LabelStore.backup()` sobrescreve o backup anterior quando dois rodam no mesmo segundo, e a
  cópia não é atômica.
- `AugmentConfig.jitter` e `affine` não são lidos em lugar nenhum, e `version` não os distingue —
  duas configurações diferentes produzem a mesma assinatura.

## Fase 61 — Os quarenta comandos

**O `-v` é o exemplo que resume a fase.** O README garante que os 40 comandos o aceitam; a
mensagem de erro de vários manda usá-lo; e doze deles saem com erro de `argparse`. A causa é
única e está em `cli/__init__.py:96`: como *console script* o `argv` chega sempre `None`, e o
`run_main` nunca enxerga a bandeira que a S-126 declarou global.

O resto da fase é a mesma disciplina aplicada às bordas: códigos de saída fora da tabela da
S-126 — e em `cvoff-export-onnx` **trocados entre si**; cinco comandos gravando relatório com
`Path.write_text`, fora do `atomic_io`, inclusive o artefato de 104 minutos; `--baseline`
validado só depois da medição inteira, o que faz horas de varredura morrerem num caminho errado;
vocabulário misturado entre comandos irmãos (`--apply`/`--aplicar`, `--dry-run`/`--seco`,
`--limit`/`--limite`); o bloco de argumentos de medição copiado à mão em sete comandos, com
*defaults* divergentes; 144 dos 416 argumentos sem `help` — entre eles `--epochs`, `--batch-size`
e `--lr` do `cvoff-train`; e `--paginas` inválido vazando a mensagem em inglês da `int()`.

## Fase 62 — O que sai no `.exe`

- **`pandas` é dependência obrigatória**, não é importado por nenhum módulo de produção, e viaja
  dentro do bundle (`pyproject.toml:10`).
- **`scipy` e `skimage` entraram no bundle sem serem declarados** — 95 MB que a lista `excludes`
  de `packaging/cvoff.spec:89` não conhece. É exatamente o que a S-135 mediu com o `pythonnet`.
- **O bundle não leva `models/char_meta.json`**, então o motor `glifo` nunca sobe no `.exe`, nem
  com os pesos ao lado (`packaging/build_windows.py:141`).
- **O log do `.exe` não rotaciona e grava em DEBUG:** `logs/chessvisionoff.log` cresce para
  sempre. E no bundle sem console, `sys.stderr` é `None` e o `StreamHandler` adicionado
  incondicionalmente falha a cada registro (`logging_setup.py:45`, `:52`).
- **`CVOFF_LOG_DIR` é ignorado por 23 dos 41 comandos**, incluindo uma janela Tk — o mesmo modo de
  falha da S-127.
- **O extra `onnx` instala o pacote `onnx`**, que não é importado em lugar nenhum.
- **`packaging/cvoff.spec` não é lintada nem tipada**, apesar de o `# noqa` do arquivo e o
  comentário do `pyproject` dizerem o contrário.

## Fase 63 — A cor, o foco e a tecla

**Três superfícies estão fora do sistema de cor da S-144.** A mensagem do rodapé não é repintada
na troca de pele — erro preto sobre cromo escuro, contraste 1,30:1 (`ui/rodape.py:501`). O canvas
da Galeria é o único do `ui/` com `#888` cravado e fundo sem token (`ui/gallery_panel.py:1404`).
E a aba Texto, já citada na Fase 56, é a terceira.

**Onze das catorze janelas de diálogo não fecham com Esc** — inclusive a legenda de atalhos
(`ui/legenda.py:66`). **"Selecionar área" é um modo e não tem nenhum feedback de estado** fora da
pele clássica (`ui/fita.py:458`). **A Galeria não tem navegação por teclado**, e as setas mexem,
invisivelmente, no diagrama da aba Resultado. **Nove caixas de erro têm o título genérico "Erro"**,
contra trinta que nomeiam a operação.

Mais: `_focus_result_tab` nunca funciona, porque o painel de resultado não é uma aba do `Notebook`
— e a exceção é engolida em `logger.debug` (`app_tkinter.py:1575`); os contadores das abas não são
atualizados depois de "Varrer o livro", que é quando eles mudam; cada troca de pele vaza uma barra
de menus inteira e reseta o regime do conjunto de campo; o `Tooltip` não cancela o `after` quando
o widget morre; há duas implementações de tooltip com tempos diferentes na mesma janela; e falta
acento numa frase de interface, contra o teste que existe para isso.

## Fase 64 — A documentação que envelheceu

**O item que dói.** A tabela "Onde mora a spec de cada item" **não cobre oito itens entregues**, e
a guarda que a confere é vácua justamente neles — é a S-134 com o mesmo furo que ela existiu para
tapar (`README.md:1037`).

**E o número que o próprio relatório desmente:** o README publica o CER de página do corte antigo
(0,1397) enquanto `docs/metrics/texto_pagina.json`, que ele cita na mesma linha, já diz 0,1001.
A mesma classe de defeito aparece em: 292 classes de caractere contra as 314 do `char_meta.json`
versionado (e o próprio README diz 314 noutra linha); "todos os 40 comandos aceitam `-v`", que a
Fase 61 desmente; o dicionário como "um arquivo de 7.588 palavras", quando desde a S-209 são três
arquivos e 367 mil; e o comando Streamlit que não roda em ambiente novo, porque o extra `demo`
não é mencionado — e a guarda que deveria pegar isso passa por acidente de substring.

**No `ARCHITECTURE.md`:** nenhuma linha sobre o pacote `text/`, que tem 51 módulos; a seção
Threads conta doze onde há treze e ignora as duas da aba Texto; `labels.csv` com 3.313 rótulos
146 linhas depois de dizer 4.450 — e 3.313 é justamente o número que a S-135 existiu para matar;
e três tamanhos de artefato entre 20% e 80% fora do disco. Mais sete âncoras internas quebradas
entre documentos, e a árvore "Estrutura" do README sem 22 dos 53 módulos de primeiro nível —
entre eles o `labels.py` da S-51.

## Fase 65 — A suíte que não pegou nada disso

Quatro mil quinhentos e oito testes verdes, e setenta defeitos de correção. A fase não pede
cobertura; pede que a suíte passe a alcançar as **três formas** em que este relatório encontrou
defeito.

- **Thread que vaza de um teste e morre com exceção cobrada de outro** (`test_estudo_aba.py:938`).
- **Um teste que esqueça `pasta_de_rascunhos` trava a suíte para sempre**, e nada impede nem
  interrompe (`ui/texto_panel.py:394`).
- **Cada rodada abandona mais de cem diretórios em `%TEMP%`** e pendura 99 `TextoPanel` na mesma
  raiz, nenhum destruído.
- **Nove módulos criam `tk.Tk()` próprio**, contra a regra escrita em `tests/tk_root.py`.
- **Os testes de "números vivos" da S-135 pulam sempre na CI**, e ninguém conta os pulos.
- **A janela de achar-e-substituir não tem teste nenhum.**
- **Quatro testes lançam subprocesso** e cada um resolve o import de um jeito; um deles vira pulo
  mudo.
- **Metade da catraca de modais está folgada:** o número declarado é 13 e o real é 18.

---

# O que esta revisão deliberadamente NÃO propõe

- **Nenhum recurso novo.** Não há aqui uma aba, um comando ou um formato que o programa não
  tenha. Tudo é conserto ou acabamento do que já existe.
- **Nenhum treino de modelo.** Nenhuma fase muda `models/piece_classifier.pt` nem os pesos de
  caractere. As Fases 58 e 59 tocam custo e caminho de decisão, não parâmetro aprendido — e a
  disciplina da S-219 continua valendo: quem mexer no caminho de medição remede os quatro
  relatórios de campo.
- **Nenhuma reescrita de módulo.** `ui/texto_panel.py` tem 2.323 linhas e `ui/study_panel.py`
  tem 2.020; ambos foram apontados como grandes por mais de um revisor. Parti-los é uma
  refatoração de risco alto e valor não medido, e este documento prefere registrar a observação
  a transformá-la em item.
- **Nenhuma mudança de dependência além de remover o que não é usado.** O `pandas` sai porque
  ninguém o importa, não porque haja algo melhor.

# A ordem de execução, e por quê

1. **Fase 52 primeiro, inteira.** Sem o portão aberto, nada do que vem depois é verificado.
2. **Fase 53 em seguida**, porque perda de trabalho humano é o único dano que nenhuma fase
   posterior consegue desfazer.
3. **Fases 54, 60 e 61** — o que trava, o que corrompe treino e o que a linha de comando promete —
   antes das fases de acabamento, porque são as que mudam resultado.
4. **Fases 55 a 59** na ordem em que a pessoa encontra o programa: a folha, o editor, o estudo, o
   texto, o núcleo.
5. **Fases 62 a 64** por último entre as de conserto: empacotamento, aparência e documentação são
   o que se ajusta depois de o comportamento parar de mudar.
6. **Fase 65 fecha**, e não abre: só depois de consertar é que se sabe qual teste faltava.

---

# O que a primeira execução da CI encontrou

A S-296 fez a CI rodar num ramo de trabalho pela primeira vez, e ela **reprovou na primeira
tentativa** -- por um defeito que não veio desta revisão. `tests/test_text_grade.py` e
`tests/test_text_pagina.py` importavam um irmão como `from tests.test_text_colunas import ...`,
e `tests` não é pacote: não há `__init__.py`, e o nome só resolve quando a raiz do repositório
está no `sys.path`. Na máquina de desenvolvimento ela está, pelo `.pth` da instalação editável;
na CI, não. Os outros **seis** arquivos que importam irmãos fazem `from test_X import ...`, sem
prefixo -- esses dois eram os únicos fora do padrão, desde a Fase 29.

Ele estava lá havia semanas, invisível, e ninguém podia tê-lo visto: a CI não rodava neste ramo.
É a demonstração do argumento que abre este documento, e ela chegou uma hora depois do conserto.

**Dois itens que a execução deixou registrados, entregues em 2026-08-28 como S-425 e S-426:**

- **O digest da S-219 contava comentário** (S-425). Ele era sobre o conteúdo do arquivo, então
  corrigir uma docstring de `config.py` invalidava os quatro relatórios de campo e custava uma
  remedição de quatro minutos -- três vezes só nesta revisão. Comentário não muda medição, e o
  digest passou a ser sobre a **árvore sintática**: `ast.parse` descarta comentário, as docstrings
  saem, e toda mudança de código continua entrando.
- **A granularidade por classe de widget da cessão de tecla** (S-426). A `main` derivava a lista
  das ligações de classe do próprio Tk, separando `Entry` de `Text`, de `Combobox` e de `Spinbox`.
  **A versão deste ramo fica**, e a razão está medida: derivar do `bind_class` cede toda tecla que
  a classe liga, que é o defeito da S-294 -- `Ctrl+S` no campo de FEN não salvava. O que a
  separação por classe compraria já está comprado pelo significado, e agora está sob teste.

---

# O que ficou entregue

**Encerrada em 2026-08-28.** A coluna *estado* da tabela das catorze fases não tem mais linha sem
marca, e o registro item a item -- problema com `arquivo:linha`, solução, critério de aceite e o
teste que o trava -- está em [SPEC_REVISAO.md](SPEC_REVISAO.md).

## As três verificações, que era por onde tudo começou

```
                              antes da revisão              hoje
$ uv run pytest      4.508 passaram, 3.593 subtests   4.822 passaram, 3.640 subtests
$ uv run ruff check .              4 erros            limpo
$ uv run mypy            30 erros em 8 arquivos       limpo (216 arquivos)
```

Duas delas estavam vermelhas e ninguém tinha sido avisado, porque a CI não rodava neste ramo. A
Fase 52 abriu o portão antes de qualquer conserto, e foi a primeira execução dela que achou um
defeito de importação anterior à revisão -- a demonstração do argumento que abre este documento,
uma hora depois do conserto.

## A conta

```
seções de spec                  130   S-296 a S-426 (menos a S-324, que é da aparência)
  itens que viraram código      121
  refutados na implementação      2   S-360 e S-407
  decididos, e não implementados  1   S-426
  já entregues por outro item     3   S-348, S-368, S-369
  números aposentados             3   S-365 a S-367, renumerados para S-386 a S-391

commits                          32
arquivos tocados                199   +11.082 linhas, -1.547
  em `src/` e no `app_tkinter`   93
arquivos de teste novos           5   mais dois ajudantes de suíte
```

**Os três refutados e decididos contam como entrega**, e é de propósito: o conserto da S-360 foi
escrito e desfeito, porque derrubava o teste que declara a decisão medida da S-11 -- trocar uma
decisão medida por uma não medida não é conserto; a S-407 era verdade quando o relatório foi
escrito e deixou de ser na S-377; e a S-426 escolhe entre duas implementações que existiram ao
mesmo tempo, com a razão medida. Achado que se investiga e não vira código continua sendo trabalho
feito, e o único jeito de ele não ser refeito é estar escrito.

## O que mudou de forma, e não só de conteúdo

- **A medição parou de ser cara de manter.** O digest do caminho de medição passou a ser sobre a
  árvore sintática (S-425): corrigir um comentário deixou de invalidar os quatro relatórios de
  campo. Nas **doze** remedições desta revisão, todos os números de acerto voltaram idênticos --
  que é o resultado desejado de uma fase de conserto, e a prova de que nenhum item mexeu no que
  o programa lê.
- **O índice de specs passou a ser lido.** A tabela *"Onde mora a spec de cada item"* não cobria
  oito itens entregues, e o leitor dela descartava em silêncio a linha com três números -- metade
  dos itens do projeto não estava declarada em lugar nenhum, com as duas guardas verdes (S-404).
- **A suíte passou a alcançar o que ela não alcançava** (Fase 65): thread que vaza de um teste e
  morre no seguinte, caixa modal de verdade que trava a rodada, mais de cem pastas por rodada em
  `%TEMP%`, nove raízes Tk próprias e uma catraca de perguntas modais que declarava 14 sobre 19
  reais. Cada uma virou guarda: elas falham no teste que causou o problema, e não no vizinho.
- **O que o programa diz sobre si mesmo é conferido contra o disco.** Seis guardas novas de
  "números vivos": o CER contra o relatório que o README cita, as classes contra o `char_meta`, o
  léxico contra os `.gz`, as threads contra o `threading.Thread(` do código, os tamanhos de
  artefato contra `data/`, e a árvore do README contra o pacote.

## O que continua em aberto, e por escolha

O que a seção [*O que esta revisão deliberadamente NÃO propõe*](#o-que-esta-revisão-deliberadamente-não-propõe)
listou continua valendo, e um item dela merece o número de hoje: `ui/texto_panel.py` tem **2.574**
linhas e `ui/study_panel.py` tem **2.227** -- os dois cresceram durante a revisão, porque as Fases
57 e 63 acrescentaram comportamento a eles. Parti-los continua sendo refatoração de risco alto e
valor não medido, e continua registrado como observação em vez de item.

**A lição de processo que esta revisão pagou, e que a próxima não deveria pagar de novo:** numere
pelo bloco que a tabela de fases reserva, e não pelo próximo número livre no disco. A Fase 62 saiu
com S-365 a S-370, colidiu com três números da Fase 60, e a correção custou 25 substituições em
oito arquivos mais três seções-ponteiro -- porque `tests/test_docs.py` lê os assuntos dos commits,
e commit empurrado não se reescreve.
