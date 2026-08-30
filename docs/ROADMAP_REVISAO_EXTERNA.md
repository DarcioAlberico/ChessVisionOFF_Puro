# Roadmap da revisão externa — Fases 66 a 68

Uma revisão técnica independente do repositório, feita por terceiro em 2026-08-28 sobre o commit
`fbb75e2` (Fase 56) e recebida aqui em 2026-08-29. Especificação item a item em
[SPEC_REVISAO_EXTERNA.md](SPEC_REVISAO_EXTERNA.md) (S-431 a S-440).

> **Onde mora a spec de cada item (S-NN).**
>
> | itens | arquivo |
> |---|---|
> | S-01 a S-36 | [SPEC.md](SPEC.md) |
> | S-37 a S-77 | [SPEC_FASE7.md](SPEC_FASE7.md) |
> | S-78 a S-82, S-143, S-175, S-176, S-454 | [ANALISE_DETECCAO.md](ANALISE_DETECCAO.md) |
> | S-83 a S-94 | [PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md) |
> | S-95 a S-142, S-171 a S-174, S-218, S-219 | [SPEC_FASE14.md](SPEC_FASE14.md) |
> | S-144 a S-170, S-177 | [SPEC_UI.md](SPEC_UI.md) |
> | S-178 a S-217 | [SPEC_TEXTO.md](SPEC_TEXTO.md) |
> | S-220 a S-234, S-294, S-295, S-324 | [SPEC_APARENCIA.md](SPEC_APARENCIA.md) |
> | S-235 a S-267, S-291 a S-293 | [SPEC_EDITOR.md](SPEC_EDITOR.md) |
> | S-268 a S-290 | [SPEC_ESTUDO.md](SPEC_ESTUDO.md) |
> | S-296 a S-323, S-325 a S-430, S-451 a S-453 (menos S-324) | [SPEC_REVISAO.md](SPEC_REVISAO.md) |
> | S-431 a S-440 | [SPEC_REVISAO_EXTERNA.md](SPEC_REVISAO_EXTERNA.md) |
> | S-441 a S-450 | [SPEC_ACABAMENTO.md](SPEC_ACABAMENTO.md) |

Este documento não propõe recurso novo. Ele é o que sobrou de dez achados de fora **depois de
cada um ser conferido contra este ramo** -- que está 17 commits à frente do que a revisão viu.

**Data da conferência:** 2026-08-29 · **Ramo:** `fase-5-modelo-desempenho` · **HEAD:** `45fb5b7`
· **Método:** cada afirmação do relatório reproduzida ou refutada nesta árvore, com o comando
registrado. Nada foi aplicado: o material recebido é dado, não instrução.

---

# O que chegou

| arquivo | o que é |
|---|---|
| `ChessVisionOFF_revisao-tecnica.pdf` | o relatório, 6 páginas |
| `melhorias-revisao.patch` | 4 commits, 27 arquivos, +1.422 / −45 linhas |
| `LEIA-ME.txt` | como aplicar, e duas ressalvas do próprio autor |
| `ChessVisionOFF_melhorias.zip` | 14,5 MB, o repositório inteiro no ramo `melhorias-revisao` |

O `.zip` é o mesmo conteúdo do `.patch` com o `.git` junto -- **não traz nada que o patch não
traga**, e foi conferido entrada a entrada. Nenhum dos quatro entra no repositório: a pasta
`Perego/` fica fora do git, como as outras pastas de fonte de terceiro.

Uma observação sobre a qualidade do que veio: o relatório mede o que afirma, separa achado de
recomendação, **retira** uma proposta própria depois de medi-la, e a seção 6 lista o que ele
deixou de fazer e por quê. Nove dos dez itens abaixo são aproveitáveis. Isso é raro e vale dizer
antes das divergências, que é do que trata o resto deste documento.

---

# O placar

| item | o que é | veredito | custo |
|---|---|---|---|
| S-431 | coleta grava zero e relata cinco | **defeito real, ainda no HEAD** | 2 linhas + teste |
| S-432 | a lei do `imread`/`imwrite` vira guarda | **ideia certa, implementação quebra aqui** | ~60 linhas |
| S-433 | 22 chamadas de `cv2` em 13 arquivos | **confirmado, contagem bate** | mecânico |
| S-434 | o `.bat` do motor em code page OEM | **correto, e no-op nesta máquina** | 1 palavra |
| S-435 | duas conexões SQLite que não fecham | **confirmado no mecanismo** | 4 linhas |
| S-436 | faixa de Python 3.10 a 3.13 | **real, e com prazo de dois meses** | 1 linha + relock aqui |
| S-437 | CI com matriz e caminho acentuado | **aceitar, sabendo o que ele não pega** | ~83 linhas YAML |
| S-438 | `bundle.json` diz de que ambiente saiu | **real, o laço não fecha mesmo** | ~180 linhas |
| S-439 | um QUICKSTART ao lado do README | **aceitar, com uma frase corrigida** | 59 linhas |
| S-440 | paralelizar a varredura | **medido e recusado — pelo autor** | zero |

---

# As três divergências

O que uma revisão de fora não pode ver é o que a máquina de fora não tem. As três coisas abaixo
mudam o que se faz com os achados, e nenhuma delas está no relatório -- não por descuido dele.

## 1. Esta bancada não consegue ver o defeito principal

```
GetACP()   = 65001
GetOEMCP() = 65001
```

Esta máquina roda com a code page ANSI em UTF-8 (a opção "Beta: usar Unicode UTF-8" do Windows
11). Medido em três destinos -- `_Болеславский`, `_acentuação`, `_ascii` -- a coleta gravou 5 e
relatou 5 nos três. **O defeito da S-431 não reproduz aqui, e as 31 falhas da S-433 também não.**

Isso não desmente nada. Muda quem paga: numa instalação em português de fábrica a ANSI é
`cp1252`, e é ali que o `imwrite` devolve `False` calado. Quem tem essa máquina é **quem baixa o
`.zip`**, e não quem desenvolve.

E é o que reordena a prioridade: as **guardas** valem mais que as correções, porque uma guarda
que depende da code page passa verde aqui antes e depois do conserto. É o defeito da S-296
escrito de novo, e o teste que veio no patch para a S-431 cai exatamente nele.

## 2. A guarda de AST, como veio, não roda nesta árvore

| medida | como veio (`os.walk` da raiz) | com `git ls-files` |
|---|---|---|
| arquivos varridos | 2.207 | 430 |
| tempo | 21,2 s | 0,27 s |
| violações acusadas | 168 | 22 |
| termina? | **não** | sim |

São 147 violações vindas de `.claude/worktrees/` -- sete checkouts de sessões concorrentes que o
clone da revisão não tinha -- e um `TabError` que **derruba o teste** dentro de
`Ideias para implementar na aba 'Texto'/`, pasta que o `.gitignore:171` já exclui e que a lista
fixa de exclusões da proposta não conhece.

A correção não é acrescentar dois nomes à lista: é parar de manter lista. `git ls-files --cached
--others --exclude-standard` é a definição de "o que é este repositório" que o projeto já
mantém, honra `.gitignore` de graça, e ainda vê o arquivo novo que ninguém commitou.

## 3. O patch não aplica limpo, e falha num arquivo só

```
error: patch failed: tests/test_engine.py:39
error: tests/test_engine.py: patch does not apply
```

Os outros 26 arquivos aplicam com deslocamento. A causa é nossa: `_launcher` ganhou o parâmetro
`caso` e passou a usar `pasta_temporaria_da_classe` num dos 17 commits desde `fbb75e2`.

Mas o atrito de aplicar não é o argumento. **Nenhum dos quatro commits entra por `git am`**:
metade das mudanças precisa de ajuste (a S-432 inteira), a numeração `S-NN` está faltando por
decisão do autor, e as mensagens são dele. As fases abaixo são reimplementação com crédito, e
não importação.

---

# As fases

## Fase 66 — O que o disco perde em silêncio (S-431 a S-435)

O núcleo. Os três defeitos e as duas guardas que fazem eles não voltarem.

**A ordem dentro da fase importa, e é contraintuitiva:**

1. **S-432 primeiro** — a guarda, com `git ls-files`. Ela nasce **vermelha**, com a lista exata
   dos 22 lugares. Guarda que nasce verde é guarda que ninguém provou.
2. **S-431 e S-433** — o conserto vira riscar itens de uma lista que o computador escreveu.
3. **S-434** — uma palavra, independente.
4. **S-435** — quatro linhas, e é pré-requisito da Fase 67.

Ao fim da fase, a suíte tem de estar verde **e** a guarda tem de ter falhado ao menos uma vez no
caminho. Se ela nunca ficou vermelha, algo foi feito fora de ordem.

## Fase 67 — O prazo de outubro (S-436, S-437)

A faixa de Python e a CI que a prova. É a única fase com data: o 3.10 sai de suporte em outubro
de 2026 e o bundle embarca o interpretador.

O `uv lock` é re-resolvido **aqui**, e não aceito de fora. O `.python-version` fica em 3.10.

## Fase 68 — O número que não fecha, e o primeiro dia (S-438, S-439, S-440)

O `bundle.json` com `extras`, o QUICKSTART, e o registro da recomendação retirada.

Nenhum dos três toca código de produção. É a fase que pode esperar -- e a S-440 não custa nada,
então pode vir junto de qualquer uma.

---

# O custo da numeração, medido

A ressalva 6.1 do relatório é: *"os itens não foram numerados como S-NNN; isso exigiria criar as
faixas em `docs/` e na tabela do README, e a numeração é sua"*. Está certa, e agora tem número.

A linha de faixa que hoje diz `S-296 a S-323, S-325 a S-430 (menos S-324)` aparece em **17
arquivos**: o `README.md` e dezesseis documentos de `docs/`. `tests/test_docs.py` exige que
todas sejam idênticas ao README -- é tudo ou nada nos dezessete.

**A conta venceu na hora, e não no primeiro commit** -- e isso foi medido, não suposto. A
primeira tentativa deixou os dez itens com seção e sem faixa declarada, apostando que as guardas
só cobrariam item que aparecesse em `git log`. A suíte respondeu na hora:

```
FAILED tests/test_docs.py::IndiceNaoEVacuoTests::test_todo_item_com_secao_esta_declarado_no_indice
+ ['S-431', 'S-432', ..., 'S-440'] : Item com seção e sem faixa na tabela
```

`test_todo_item_com_secao_esta_declarado_no_indice` cobra **toda seção `## S-NNN` que exista em
`docs/`**, entregue ou não. A exceção é só para item cujas seções moram exclusivamente em
arquivos `ROADMAP*` -- e as destas dez moram na spec.

Então o ritual foi feito junto com estes dois documentos, e não adiado:

- a linha `| S-431 a S-440 | SPEC_REVISAO_EXTERNA.md |` entrou nos **17** arquivos que carregam a
  tabela, o `README.md` entre eles;
- os dois documentos novos carregam a tabela também, como todos os outros;
- os dois entraram no índice de `docs/` do `README.md`, que
  `test_todo_documento_aparece_no_readme` cobra;
- o piso derivado subiu de 7 para 8 arquivos de spec declarados, contra 19 cópias que trazem a
  tabela -- folga de sobra.

`uv run pytest tests/test_docs.py` fica verde. **Quem implementar os itens não paga mais nada
deste custo**: a faixa já existe, e cada `S-43x` que aparecer numa mensagem de commit já tem
onde morar.

---

# O que não se aproveita

**Nada é descartado inteiro.** Dos dez, um não vira código por decisão do próprio autor (S-440),
e três chegam com ajuste obrigatório:

- **A implementação da guarda (S-432)** — trocada por `git ls-files`, pelas razões medidas acima.
- **O teste da S-431** — reescrito. O que veio é vácuo nesta máquina, e vácuo é pior que
  ausente: ele passa verde e dá a impressão de cobrir.
- **O `uv.lock` do patch (S-436)** — descartado, e re-resolvido aqui. Um lock é o estado do
  resolvedor no momento em que rodou; aceitá-lo de fora é aceitar uma resolução que ninguém
  daqui viu.

E dois avisos que vêm do relatório e continuam valendo depois da conferência:

- O 3.13 do `uv` já entregou Tk incompleto, e ali **14 testes de janela pulam em vez de rodar**.
  A janela é o produto. Por isso a Fase 67 para na faixa e não promove o 3.13 a padrão do bundle.
- O job de CI com caminho acentuado **não pega** a família do `cv2`/ANSI num runner ocidental --
  `áéíóúç` cabem em `cp1252`. Quem pega é a guarda da S-432. Se só um dos dois entrar, entra ela.

---

# Como continuar

O relatório e o patch ficam em `Perego/`, fora do git. O que este roadmap não copiou de lá:

- `Perego/ChessVisionOFF_revisao-tecnica.pdf` — as tabelas de medição do paralelismo (seção 5) e
  o perfil de tempo por etapa, que a S-440 resume mas não substitui.
- `Perego/melhorias-revisao.patch` — os quatro commits com o texto original de cada docstring.
  Vale como referência de redação ao escrever os itens: a S-438, em especial, tem 104 linhas
  prontas em `packaging/build_windows.py` que só precisam de revisão, não de reescrita.

---

# O que a implementação mediu

As três fases foram implementadas em 2026-08-29, sobre o HEAD `45fb5b7`. O que segue são os
números da execução, e não a previsão dela.

## A guarda nasceu vermelha, como a ordem exigia

```
$ uv run pytest tests/test_image_io.py -q
FAILED LeiDoProjetoTests::test_ninguem_no_repositorio_chama_imread_nem_imwrite
AssertionError: [] != ['src/chess_diagram_ocr/text/coleta.py:241: cv2.imwrite', ...]
Second list contains 22 additional elements.
1 failed, 13 passed
```

Vinte e duas, o número que a spec previa, e a primeira da lista é a da coleta. Depois das
conversões:

```
14 passed, 4 subtests passed
```

Os outros dois testes da classe -- alcance e fronteira -- passaram desde o primeiro minuto, que é
o esperado: eles guardam a varredura, não o código varrido.

## O placar das três verificações

```
$ uv run ruff check .      All checks passed!
$ uv run mypy              Success: no issues found in 216 source files
$ uv run pytest -q         4.870 passaram, 2 pulados, 3.652 subtests    169 s
```

**4.859 → 4.870**, onze testes novos: três da S-431, três da guarda da S-432 e cinco da S-438.

## O que mudou de forma no caminho

- **O `uv lock` foi re-resolvido aqui**, e não aceito do patch: 122 pacotes antes e depois,
  **nenhuma versão de terceiro se moveu**. As 871 linhas novas são entradas de wheel dos
  interpretadores que a faixa passou a aceitar.
- **O teste do `bundle.json` mede o arquivo gravado, e não o texto do módulo.** A primeira versão
  procurava a linha `"extras": extras,` no fonte de `build_windows.py` -- guarda que continua
  verde se a linha mudar de lugar e parar de rodar. A versão que ficou chama `gravar_metricas`
  com `PROJETO` e `SAIDA` numa pasta temporária e lê o JSON. O `docs/metrics/bundle.json`
  versionado não é tocado: nenhum build foi rodado, e o número publicado continua o de
  2026-08-18.
- **O `.bat` do motor foi reescrito à mão**, porque o hunk do patch não aplicava -- a única
  colisão dos 27 arquivos, e a causa era nossa.

## O que continua em aberto, e é de propósito

- **O `.python-version` fica em 3.10.** A faixa aceita até 3.13 e a CI prova as duas pontas, mas
  promover o 3.13 a padrão do bundle depende de abrir a janela numa máquina de verdade -- o Tk
  do interpretador que o `uv` entrega para 3.13 já veio incompleto uma vez.
- **A matriz da CI ainda não rodou.** Ela é YAML válido e a estrutura foi conferida, mas quem a
  prova é o GitHub. A perna do 3.13 é a primeira coisa a olhar no próximo push.
- **A S-440 não tem código, e nunca vai ter.** É o registro de uma recomendação medida e
  recusada.
