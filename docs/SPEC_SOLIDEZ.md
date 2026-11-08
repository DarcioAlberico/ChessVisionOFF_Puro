# Especificação da solidez — Fases 110 a 121 (S-800 a S-873)

Base: [ROADMAP_SOLIDEZ.md](ROADMAP_SOLIDEZ.md), que traz as medições de 2026-11-08, as seis premissas
atacadas, o glossário, a ordem das fases e as decisões do dono. Todo caminho abaixo é relativo a
`src/chess_diagram_ocr/`, salvo quando começa por `tests/`, `docs/` ou é um arquivo da raiz. As
linhas citadas são de `origin/main` em `e8c9f64a`.

> **Onde mora a spec de cada item (S-NN).**
>
> | itens | arquivo |
> |---|---|
> | S-01 a S-36 | [SPEC.md](SPEC.md) |
> | S-37 a S-77 | [SPEC_FASE7.md](SPEC_FASE7.md) |
> | S-78 a S-82, S-143, S-175, S-176, S-454, S-455 | [ANALISE_DETECCAO.md](ANALISE_DETECCAO.md) |
> | S-83 a S-94 | [PLANO_BASE_PARTIDAS.md](PLANO_BASE_PARTIDAS.md) |
> | S-95 a S-142, S-171 a S-174, S-218, S-219 | [SPEC_FASE14.md](SPEC_FASE14.md) |
> | S-144 a S-170, S-177 | [SPEC_UI.md](SPEC_UI.md) |
> | S-178 a S-217 | [SPEC_TEXTO.md](SPEC_TEXTO.md) |
> | S-220 a S-234, S-294, S-295, S-324 | [SPEC_APARENCIA.md](SPEC_APARENCIA.md) |
> | S-235 a S-267, S-291 a S-293, S-521 | [SPEC_EDITOR.md](SPEC_EDITOR.md) |
> | S-268 a S-290 | [SPEC_ESTUDO.md](SPEC_ESTUDO.md) |
> | S-296 a S-323, S-325 a S-430, S-451 a S-453 (menos S-324) | [SPEC_REVISAO.md](SPEC_REVISAO.md) |
> | S-431 a S-440 | [SPEC_REVISAO_EXTERNA.md](SPEC_REVISAO_EXTERNA.md) |
> | S-441 a S-450 | [SPEC_ACABAMENTO.md](SPEC_ACABAMENTO.md) |
> | S-507 a S-520 | [SPEC_ESTUDO_QT.md](SPEC_ESTUDO_QT.md) |
> | S-522 a S-526 | [SPEC_REVISAO_EXTERNA_2.md](SPEC_REVISAO_EXTERNA_2.md) |
> | S-500 a S-506, S-527 a S-580 | [SPEC_SUITE.md](SPEC_SUITE.md) |
> | S-581 a S-584 | [PLANO_COLUNAS_SOLUCOES.md](PLANO_COLUNAS_SOLUCOES.md) |
> | S-599 | [PLANO_FAIXAS_REVERSAS.md](PLANO_FAIXAS_REVERSAS.md) |
> | S-601 a S-668 | [SPEC_MESA_DE_TEXTO.md](SPEC_MESA_DE_TEXTO.md) |
> | S-702, S-710 a S-712, S-715 a S-718, S-720 | [SPEC_TEXTO_PRECISO.md](SPEC_TEXTO_PRECISO.md) |
> | S-800 a S-873 | [SPEC_SOLIDEZ.md](SPEC_SOLIDEZ.md) |

Cada item traz o **problema** com a evidência, a **causa**, a **solução** (a menor mudança, ou o
redesenho entregue em pedaços), o **teste que falha primeiro** e o **critério de aceite**. A prova de
cada achado está marcada: *confirmado* quando foi reproduzido por script ou lido sem ambiguidade,
*plausível* quando o mecanismo está no código mas o caso não foi reproduzido. Nenhum item está
entregue; todos valem como plano até o commit que os fecha.

## Fase 110 — Alavancas

## S-800 · Borda de exceção do processo, e o estado da sessão gravado antes da queda

**Problema** (confirmado). `app_pyqt.py:305-341` não instala `sys.excepthook`, e nada em `src/`
instala. Em PyQt6, exceção que escapa de um slot é `qFatal`: o processo sai (0xC0000409, ou 127 sob
`offscreen`) sem uma linha de log. Dos dez `eventFilter` de `qt/`, seis não têm `try`
(`fita_do_texto`, `foco_a_vista`, `painel_de_texto`, `paleta`, `tabela`, `vazio`). E
`JanelaPrincipal._gravar_estado` (`qt/janela.py:889`) só roda no `closeEvent` (`:2251`), então a
queda perde também o histórico de PDFs, a página e o divisor.

**Causa.** Premissa 6 do roadmap: a defesa foi posta slot por slot (`qt/atalhos.py:298` é o único
filtro com borda), e não na raiz.

**Solução.** `qt/plataforma.instalar_borda()`, chamada no `main` antes da `QApplication`: troca
`sys.excepthook` (e `threading.excepthook`) por `logger.critical(..., exc_info=...)` e, havendo
janela, uma frase no rodapé. Segundo pedaço: `_gravar_estado` também em `_abriu_livro` e na troca de
página, com intervalo mínimo de 2 s entre gravações.

**Teste que falha primeiro.** Subprocesso com `QT_QPA_PLATFORM=offscreen` que chama
`instalar_borda()`, agenda `QTimer.singleShot(0, levanta)` e sai do laço em seguida.

**Aceite.** O subprocesso sai com código 0 e o arquivo de log tem a linha `CRITICAL` com o
traceback. Abrir um livro, virar duas páginas e matar o processo deixa `state.json` com o livro e a
página.

## S-801 · crapper no repositório, com catraca de CRAP por função

**Problema.** O método pede CRAP abaixo de 10 por função, e o projeto não tem como medir: nem
`radon` nem `coverage` estão nas dependências de desenvolvimento.

**Solução.** `radon` e `coverage` no extra `dev`. Um `tools/qualidade/crapper.py` (o da revisão, em
que `CRAP = cc² × (1 − cobertura)³ + cc`, com a cobertura por linha de cada função) que lê o JSON do
`coverage` e o do `radon`, e escreve `docs/metrics/crap.json` com as funções de CRAP ≥ 10. A catraca
é um teste que compara o arquivo novo com o registrado: nenhuma função **nova** entra acima de 30,
e o número de funções acima de 10 não sobe.

**Teste que falha primeiro.** Uma função sintética de complexidade 12 sem teste num diretório
temporário: o crapper a reporta com CRAP 12² + 12 = 156.

**Aceite.** `python tools/qualidade/crapper.py` roda em menos de 1 minuto sobre uma cobertura já
gravada. A catraca falha ao acrescentar a função sintética a `src/` e passa ao removê-la. O CI roda a
cobertura numa das duas pernas, não nas duas.

## S-802 · dryer no repositório, com catraca de pares duplicados

**Problema** (confirmado). 65 pares de funções com semelhança ≥ 0,8 e 340 com ≥ 0,6. Exemplos com
1,00: `cli/texto_grade.py:570` e `cli/texto_ordem.py:293` (`parse_args`), `text/colados.py:74` e
`text/duas_linhas.py:77` (`vale`), `text/modelo.py:365` e `text/onnx_glifos.py:229`
(`classificar`), `qt/painel_da_galeria.py:1510` e `qt/painel_de_estudo.py:1747` (confirmação).

**Solução.** `tools/qualidade/dryer.py`: tokeniza cada função com 60 tokens ou mais, troca nomes
por `N`, números por `0` e strings por `S` (palavras-chave ficam), e mede Jaccard sobre 5-gramas. A
catraca guarda os pares ≥ 0,8 em `docs/metrics/dryer.json`: par novo reprova, par que some baixa o
teto. Um par pode ser declarado "semelhante de propósito" com a razão escrita no próprio JSON.

**Teste que falha primeiro.** Duas funções iguais a menos dos nomes num diretório temporário: rank
1,00. Duas funções com o mesmo esqueleto e corpos diferentes: rank abaixo de 0,6.

**Aceite.** Rodada sobre `src/` em menos de 30 s. A catraca acusa uma cópia acrescentada.

## S-803 · mutator no repositório, com piloto em seis módulos puros

**Problema.** Não se sabe quanto do que a suíte cobre ela de fato verifica. `mutmut` não roda
nativo no Windows, que é onde o projeto vive.

**Solução.** `tools/qualidade/mutator.py`: por AST, uma mutação por vez (troca de comparação,
aritmética, `and`/`or`, `not` removido, inteiro + 1, booleano invertido, `return X` → `return None`),
roda o arquivo de teste do módulo e restaura o fonte num `finally`. O piloto roda em `fen_utils.py`,
`splits.py`, `decode.py`, `atomic_io.py`, `settings.py` e `ui/legality.py`, e o escore de cada um
fica em `docs/metrics/mutacao.json`. Não entra no CI de cada push: roda à mão, e o escore registrado
só pode subir.

**Teste que falha primeiro.** Um módulo de brinquedo `soma(a, b): return a + b`, com um teste que
só confere `soma(0, 0) == 0`: a mutação `+` → `-` sobrevive. Com o teste `soma(2, 3) == 5`, ela
morre.

**Aceite.** O fonte do módulo é byte a byte igual ao de antes, também quando o processo é
interrompido no meio (o `finally` restaura). O relatório lista cada sobrevivente com linha e
operador. A S-873 mata os sobreviventes.

## S-804 · Catraca de tipos, e as contagens que só descem

**Problema** (confirmado). 192 `# type: ignore` (80 `arg-type`, 63 `attr-defined`), 892 `Any` e 175
`except Exception`. O `[tool.mypy]` não tem `warn_unused_ignores`, então um `ignore` que já não
silencia nada fica para sempre. O comentário do `[tool.mypy]` (`pyproject.toml:262`) ainda fala de
`app_tkinter.py`, que não existe.

**Solução.** `warn_unused_ignores = true`, apagando os ignores que ele acusar. Um teste de catraca
com as três contagens por pacote (`qt/`, `text/`, `ui/`, `cli/`, raiz), que reprova se uma delas
subir. O comentário passa a falar de `app_pyqt.py`.

**Teste que falha primeiro.** Acrescentar um `except Exception: pass` em `src/`: a catraca reprova
com o nome do pacote.

**Aceite.** `mypy` verde com `warn_unused_ignores`. A catraca está verde em `main` e vermelha com o
acréscimo.

## S-805 · Infraestrutura de teste

**Problema.** Quatro furos, todos confirmados pela auditoria dos testes:

- os testes da aba Texto usam `_TarefaNaHora` (`tests/test_qt_texto_caderno.py:52`), que emite
  `pronto` dentro do `start`. Uma tarefa que termina antes de a tela mudar não pega nenhum defeito
  de "mudou durante a tarefa" (S-823, S-824);
- a guarda `sem_thread_vazada` (`tests/conftest.py:291`, `:326`) aceita threads `Dummy-N` e
  `ThreadPoolExecutor`, que é como um `QThread` aparece. A `Tarefa` é um `QThread`, então a guarda não
  a enxerga (plausível);
- `dados_de_quem_roda_ficam_onde_estao` (`tests/conftest.py:158-237`) vigia `PROJECT_ROOT/data/`,
  que num worktree não tem o cache: a guarda fica vácua. É o caso da memória "guarda de caminho é
  vácua em worktree";
- `tests/qt_app.py:30` pula cerca de 206 classes se o PyQt6 não importar, e o PyQt6 é dependência
  base (`pyproject.toml:43`). Uma instalação quebrada sai verde com pulos.

**Solução.** Uma `TarefaAdiada` em `tests/qt_app.py`, que só emite quando o teste manda. Um registro
de `Tarefa` vivas em `qt/trabalho.py`, conferido pela mesma fixture. A guarda de dados ancorada
também no `git rev-parse --git-common-dir`, como `_raizes_do_repositorio` já faz. Um teste que
reprova, sem pular, quando `import PyQt6.QtWidgets` falha.

**Teste que falha primeiro.** Uma `Tarefa` deixada rodando num teste de mentira: a fixture tem de
acusar.

**Aceite.** As quatro guardas acusam o caso sabotado e passam na suíte atual.

## Fase 111 — Caches e índices que não se apagam sozinhos

## S-806 · `open_store` nunca esvazia o cache

**Problema** (confirmado por script). `games_cache.py:509-518`: quando a impressão digital gravada
difere da de agora, `open_store` chama `_esvazia`. Com 500 linhas feitas sobre `[a.pgn, b.pgn]`,
abrir com `database=[a.pgn]` deixa zero. Quem chega aqui sem querer:

- `cli/games.py:394`: `_census` diz "Não abre a base", e `cvoff-games --census --database X.pgn`
  apaga o cache do acervo inteiro;
- `cli/games.py:250`: `_bases()` tira em silêncio a base que não existe agora. Um disco fora do ar
  ou um arquivo no meio de uma cópia esvazia o cache no `--all` seguinte;
- `stat()` que falha vira tamanho 0 (`games_cache.py:109-112`), e a impressão "muda";
- o painel de estudo (`qt/painel_de_estudo.py:2721`) e a Galeria abrem do mesmo jeito.

O cache é ~56 minutos de varredura, e é o incidente de 2026-10-18 (~9.810 linhas apagadas).

**Causa.** Premissa 1: "o conjunto parece diferente" é tratado como "o cache não vale", e "não vale"
como "apague".

**Solução.** Redesenho em três pedaços. (1) `open_store` nunca faz `DELETE`. (2) A tabela
`positions` ganha a coluna `impressao` e cada linha é respondida só sob a impressão com que foi
feita; linha de impressão antiga é ignorada na leitura, e uma limpeza explícita
(`cvoff-games --limpar-cache`) é o único lugar que apaga. (3) Leitores (`--census`, painel) abrem
com `mode=ro` e sem `database=`; `stat` que falha vira "desconhecido", que não casa nem descasa.

**Teste que falha primeiro.** `test_census_com_subconjunto_nao_apaga_o_cache`: encher com
`[a, b]`, chamar `cli.games.main(["--census", "--database", a])`, conferir 500 linhas.
`test_stat_falho_nao_esvazia`.

**Aceite.** Os dois testes passam. Nenhum `DELETE FROM positions` fora da limpeza explícita (guarda
por `grep`, com piso de um achado: a própria limpeza).

## S-807 · Uma impressão digital de base só, que enxerga membro de `.zip`

**Problema** (confirmado por script). `games_cache.database_fingerprint` (`games_cache.py:107-112`)
dá tamanho 0 a todo membro de `.zip`: reescrever `z.zip/m.pgn` com 50 vezes o conteúdo não muda a
impressão. `games_index.index_fingerprint` (`games_index.py:363`) responde a mesma pergunta por
`nome_da_base` e `tamanho_da_base`, que tratam o zip. A base é identificada só por `caminho.name`, e
dois zips com `games.pgn` dentro parecem a mesma base.

**Causa.** Premissa 3: a mesma decisão em dois módulos (a S-113 já tinha juntado metade dela).

**Solução.** `impressao_da_base(caminho) -> ImpressaoDaBase` (nome qualificado pelo zip, tamanho do
membro) num módulo só, usada por cache e índice.

**Teste que falha primeiro.** `test_impressao_de_membro_de_zip_muda_com_o_conteudo`, e
`test_dois_zips_com_mesmo_membro_sao_bases_diferentes`.

**Aceite.** Os dois passam. `database_fingerprint` e `index_fingerprint` delegam à mesma função.

## S-808 · URI de SQLite por `Path.as_uri()`, e versão ilegível não apaga o índice

**Problema** (confirmado por script). `games_index.py:384` e `:997` montam `f"file:{path}?mode=ro"`
sem escapar o caminho; `games_cache.py:575` e `arvore_de_aberturas.py:718`, `:814` fazem o mesmo
com `as_posix()`. Numa pasta `Xadrez #2`, a versão gravada volta `None`; numa pasta `100%25 ok`, o
SQLite nem abre. E `_abrir_para_escrita` (`games_index.py:416-421`) trata o `None` como "outro
formato" e faz `unlink` do índice, que é construído de 8,6 GB de PGN.

**Solução.** `uri_somente_leitura(caminho)` = `caminho.resolve().as_uri() + "?mode=ro"`, num lugar,
usada pelos quatro. `_abrir_para_escrita` apaga só quando leu uma versão **e** ela é outra; versão
que não leu é erro, dito ao usuário.

**Teste que falha primeiro.** `test_indice_em_pasta_com_cerquilha_sobrevive_a_segunda_rodada` e o
mesmo com `%`.

**Aceite.** Os dois passam. Nenhum `f"file:` sobra em `src/` (guarda por `grep` sem piso, porque o
número certo é zero).

## S-809 · `--build-index` com subconjunto não apaga as outras bases

**Problema** (plausível). `games_index.py:652-660` apaga de `games` e `files` toda base que não está
na lista desta rodada. Com `--database X` explícito, ou com uma base que `_bases()` filtrou por estar
ausente naquele instante, horas de indexação se perdem.

**Solução.** Apagar só a base cujo arquivo não existe mais na pasta das bases, e só com
`--podar`. Rodada com subconjunto acrescenta e atualiza; não poda.

**Teste que falha primeiro.** Indexar `[a, b]`, rodar `--build-index --database a`, conferir que as
partidas de `b` continuam.

**Aceite.** O teste passa. `--podar` sem nenhuma base ausente é no-op.

## Fase 112 — Arquivos do dono

## S-810 · Booleano estrito e faixas numéricas no `settings.json`

**Problema** (confirmado por script). `RemoteFenSettings.from_dict({"enabled": "false"}).is_usable`
é `True`, porque `bool("false")` é verdadeiro. Um `"false"` escrito à mão **liga** o envio de
imagens a um servidor, e o próprio módulo promete que um JSON ruim não liga envio. `timeout` aceita
`nan` e `-5`; `threads` aceita `-3`.

**Solução.** `_booleano(valor)`: só `true` e `false` do JSON; qualquer outra coisa é **desligado**,
com aviso. Faixas declaradas por campo (timeout em `(0, 600]`, threads em `[1, núcleos]`), com
o valor fora da faixa trocado pelo padrão e avisado. O par `_inteiro`/`_flutuante`
(`settings.py:139`, `:162`, idênticos para o dryer) vira um só `_numero(tipo, faixa)`.

**Teste que falha primeiro.** `test_enabled_string_false_e_desligado`;
`test_timeout_nan_volta_ao_padrao`.

**Aceite.** Os dois passam. Nenhum `bool(` sobre valor do JSON em `settings.py`.

## S-811 · Camada de arquivo e camada efetiva

**Problema** (confirmado por script). `settings.py:533-569`: carregar aplica as variáveis
`CVOFF_*` sobre o que leu, e salvar grava o resultado. Com `remote_fen.enabled=true` no arquivo e
`CVOFF_REMOTE_FEN_ENABLED=0` no ambiente, uma gravação de outra opção deixa o arquivo com `false`
para sempre. No sentido contrário, `CVOFF_REMOTE_FEN_URL` vai para o arquivo junto de
`enabled=true`: um consentimento de privacidade que ninguém deu. Seções e chaves desconhecidas somem
na gravação, e `SETTINGS_VERSION` nunca é conferido na leitura. Quem grava: `qt/painel_de_estudo.py:2405-2407` e
`qt/dialogo_de_configuracoes.py:246-250`.

**Solução.** Dois valores com tipos diferentes: `ConfiguracaoDoArquivo` (o que leu, com as chaves
desconhecidas guardadas à parte) e `Configuracao` (efetiva, derivada por
`aplicar_ambiente(arquivo, os.environ)`). Só a primeira tem `gravar`. A versão do arquivo é
conferida: versão futura entra pela S-812.

**Teste que falha primeiro.** `test_salvar_nao_grava_o_ambiente`, nos dois sentidos;
`test_chave_desconhecida_sobrevive_a_gravacao`.

**Aceite.** Os testes passam. O tipo efetivo não tem método de gravação (mypy acusa a tentativa).

## S-812 · Leitura travada

**Problema** (confirmado). Sete leitores tratam o arquivo que não lê como vazio, e o gravador
seguinte escreve o vazio por cima:

- `settings.json` com uma vírgula sobrando vira padrão, e a próxima gravação de motor escreve
  `endpoint: ''` e `engine.path: ''` sobre o arquivo do usuário (`settings.py:533-569`);
- `revisao.json` de esquema 2 com 600 itens carrega com 0, e a gravação seguinte escreve esquema 1
  com 0 itens (`revisao_arquivo.py:43-68`);
- `placar.json`, o estudo da sala, a fila de revisão, o lote de importação (`Lote.carregar` devolve
  `None` e `abrir_lote` recomeça com tudo pendente) e o cache de posições (S-806).

**Causa.** Premissa 1, em sete atores.

**Solução.** Um módulo `arquivo_do_dono.py` com o tipo
`Leitura = Lida[T] | Ilegivel | EsquemaFuturo`. `Ilegivel` e `EsquemaFuturo` copiam o arquivo para
`<nome>.ilegivel-<data>` (D1 do roadmap) e devolvem um valor em memória marcado **travado**, que o
gravador recusa com uma mensagem ao usuário. Os sete leitores passam a devolver `Leitura`; os
gravadores aceitam só `Lida`. Entregue em pedaços, um arquivo por commit, começando pelo
`settings.json`.

**Teste que falha primeiro.** Para cada um dos sete: arquivo corrompido, carregar, mexer, gravar; o
arquivo original tem de estar intacto e a cópia `.ilegivel` tem de existir.

**Aceite.** Os sete testes passam. Nenhum leitor de arquivo do dono devolve o padrão para arquivo
ilegível sem passar pelo `Ilegivel` (guarda por AST nos sete módulos, com piso de sete).

## S-813 · Baralho de revisão e placar sob a leitura travada

**Problema** (confirmado por script). Além da premissa da S-812: `"esquema": "1.0"` levanta
`ValueError` fora do `try` em `revisao_arquivo.py`; `certos: "x"` derruba `placar.py:120-128`,
`:195-217`, porque `de_json` não converte campo a campo. O módulo chama o baralho de "o único dado
que este programa não sabe refazer".

**Solução.** O `esquema` lido por `_inteiro_estrito`; cada item do placar e do baralho lido no seu
`try`, com o item ruim guardado cru e devolvido igual na gravação.

**Teste que falha primeiro.** `test_baralho_de_esquema_futuro_nao_e_sobrescrito`;
`test_placar_com_campo_ruim_nao_derruba`.

**Aceite.** Os dois passam. Um placar com um item ruim entre dez bons carrega os dez e grava os
onze.

## S-814 · Sala de estudo: partida que não lê sobrevive à gravação

**Problema** (plausível). `estudo_arquivo.py:150-168`, `:184-202` e `estudo.py:505-512`,
`:679-692`: partida com `Page` ou `Diagram` ruim vira âncora inválida, e `guardar` a descarta com
log de depuração; um `read_game` que levanta faz `break` e derruba **todas** as seguintes, apesar da
docstring; `OSError` na leitura dá uma `Sala` vazia. A próxima edição marca a sala como suja, e
`gravar` reescreve o arquivo com a sala parcial, ou faz `unlink` se ela estiver vazia.

**Solução.** `continue` no lugar do `break`. A partida que não lê é guardada como texto PGN cru e
devolvida igual na gravação. Sala de leitura incompleta é `Leitura` travada (S-812).

**Teste que falha primeiro.** `test_estudo_sem_ancora_sobrevive_a_gravacao`; um arquivo com a
segunda de cinco partidas quebrada carrega quatro e grava cinco.

**Aceite.** Os dois passam; o arquivo regravado tem a partida quebrada byte a byte igual.

## S-815 · Fila de revisão: FEN corrigida sobrevive ao revarrer

**Problema** (confirmado por leitura). `review_queue.py:627-664`: `merge_queues` preserva só o
`status`. A FEN que o usuário corrigiu por `update_fen` volta a ser a leitura do OCR, e o item fica
"feito". `_safe_name` (`:393-407`) nomeia a pasta de miniaturas só pelo nome do arquivo, sem a
pasta, e dois PDFs com o mesmo nome sobrescrevem as miniaturas um do outro (o acervo tem livros
duplicados). `ReviewQueue.load` falha inteiro por um campo não numérico.

**Solução.** Item feito preserva a FEN. A pasta de miniaturas leva `nome + hash curto do caminho
resolvido`, com migração da pasta antiga quando ela é inequívoca. Cada item lido no seu `try`.

**Teste que falha primeiro.** `test_revarrer_preserva_fen_corrigida`;
`test_dois_pdfs_de_mesmo_nome_nao_dividem_miniaturas`.

**Aceite.** Os dois passam.

## S-816 · `cvoff-scan` retomado preserva as pendências

**Problema** (confirmado por leitura). `cli/scan.py:191-195` chama `merge_queues(ReviewQueue.load(
destino), fila)` sem `pages=`. Como a varredura retomada só passa pelas páginas depois de
`last_page_done` (`gallery_scan.py:277-280`), os itens das páginas anteriores somem. O GUI passa
`pages` (`qt/painel_de_revisao.py:471`, a S-119). O CLI também não confere `source_pdf`, que
`cli/review.py:115` e o painel conferem, e `_queue_path` (`:141`) usa só o nome do arquivo.

**Causa.** Premissa 3: a regra de fusão está no chamador, e foi consertada num chamador só.

**Solução.** `fundir_fila_retomada(anterior, nova, paginas_vistas, fonte)` pura em `review_queue.py`,
que confere a fonte e preserva o que está fora das páginas vistas. O GUI e o CLI a chamam. O nome da
fila ganha o mesmo hash da S-815.

**Teste que falha primeiro.** `test_scan_retomado_preserva_pendencias_das_primeiras_paginas`.

**Aceite.** O teste passa nos dois chamadores (o mesmo caso, parametrizado).

## S-817 · Quarentena de rótulos em conflito sempre desfazível

**Problema** (confirmado). `text/conflitos.py:242-299`, chamado por `cli/texto_conflitos.py:236`:
o manifesto guarda caminhos relativos ao `PROJECT_ROOT`, e `desfazer` os resolve contra a pasta
**atual**. Rodado de outra pasta, ele pula todos os arquivos, diz "0 recortes voltaram" e sai com 0.
O manifesto só é escrito depois de todos os movimentos, então uma queda no meio deixa arquivos na
quarentena sem caminho de volta, contra a promessa "nunca apaga".

**Solução.** Caminhos absolutos no manifesto. O manifesto é escrito antes de mover e atualizado a
cada movimento (por `atomic_io`); `desfazer` já tolera o arquivo que falta. Desfazer zero de N sai
com código diferente de 0.

**Teste que falha primeiro.** `test_desfazer_de_outra_pasta_devolve_tudo`;
`test_queda_no_meio_da_quarentena_e_desfazivel`.

**Aceite.** Os dois passam.

## Fase 113 — Escritas idempotentes e atômicas

## S-818 · Exportação de PGN atômica, e sem `.review.pgn` de rodada anterior

**Problema** (confirmado por script). `pdf_to_pgn.py:1019` e `:1038` gravam o PGN do livro e o de
revisão com `write_text`, que trunca antes de escrever e, no Windows, escreve CRLF. O sidecar de
proveniência é aberto com `open("w")` (`proveniencia.py:194`), e uma linha pela metade faz
`read_sidecar` levantar `JSONDecodeError`. Quando a rodada nova não tem nada a revisar, o
`livro.review.pgn` da rodada anterior fica no disco, e o relatório diz `review_path=None`.

**Solução.** Os três arquivos por `atomic_write_text` com quebra LF. Rodada sem revisão faz
`unlink(missing_ok=True)` do `.review.pgn`.

**Teste que falha primeiro.** `test_exportar_sem_revisao_remove_review_pgn_antigo` (duas rodadas,
a segunda sem item a revisar); `test_pgn_exportado_e_lf`.

**Aceite.** Os dois passam. Uma queda simulada no meio da gravação deixa o PGN anterior inteiro.

## S-819 · Retomada de exportação sem perda de campo

**Problema** (confirmado por script). `export_checkpoint.py:216-276`: `position_from_dict(
position_to_dict(p))` perde `stipulation`, `stipulation_closes`, `stipulation_keys`,
`stipulation_repairs` e `stipulation_reason`; `_context_to_dict` perde `caption_after_move`,
`coordinates`, `first_move_number`, `first_moves_text` e `stipulation`. As páginas lidas antes da
interrupção saem da exportação retomada sem `[Stipulation]`, `[StipulationCheck]` nem
`[OCRStipulation]`. Como `gate_confidence` sobrevive, uma posição aceita por reparo de estipulação
sai sem dizer que foi reparada.

**Causa.** A lista de campos está escrita à mão, e a dataclass cresceu sem ela.

**Solução.** Serialização derivada de `dataclasses.fields`, com conversão explícita só dos tipos
aninhados. Leitura que recusa chave desconhecida e preenche ausente pelo padrão do campo. A versão
do checkpoint sobe, e um checkpoint antigo é retomado com aviso de que os campos novos faltam.

**Teste que falha primeiro.** Para cada campo de `DiagramPosition` e de `DiagramContext`, um valor
diferente do padrão; o ida-e-volta tem de ser igual.

**Aceite.** O teste é gerado a partir de `fields()`, então um campo acrescentado depois entra nele
sozinho.

## S-820 · Importação de imagens idempotente

**Problema** (confirmado por leitura). `importacao_de_imagens.py:871-955`, `:279-293`: cada amostra
vai para `labels.csv` na hora (`gravar_item` → `append_training_sample`), mas o lote que marca o
item como salvo só é gravado a cada 25 itens, e o `gravar_andamento()` final não está num
`finally`. Uma queda, ou qualquer exceção que não seja `OSError`/`ValueError` (um `cv2.error` de
`ler`), deixa até 24 linhas no CSV que o lote ainda mostra como pendentes. A segunda rodada as grava
de novo com nome novo, e nada as deduplica: a mesma imagem cai no treino e no teste. Também:
`LabelStore.append` (`labels.py:384`) aceita nome de arquivo repetido, e o nome da amostra sai do
relógio (`dataset.py:528`), cujo passo medido nesta máquina é ~1,5 ms (plausível: duas gravações no
mesmo passo sobrescrevem o PNG).

**Solução.** O andamento gravado a cada item, e o final num `finally`. `append_training_sample`
recusa imagem cujo hash de conteúdo já está no CSV. `LabelStore.append` recusa nome repetido. O
arquivo da amostra é criado com `open(..., "xb")` e um sufixo aleatório curto. Lote ilegível é
`Leitura` travada (S-812): não recomeça.

**Teste que falha primeiro.** `test_importacao_interrompida_nao_duplica_linhas` (`ler` levanta
`RuntimeError` no item 3; duas rodadas; uma linha por hash);
`test_duas_amostras_no_mesmo_instante_nao_se_sobrescrevem` (relógio congelado).

**Aceite.** Os dois passam.

## S-821 · PDF pesquisável idempotente e atômico

**Problema** (confirmado por leitura). `text/pdf_pesquisavel.py:661` **acrescenta** a marca em
`keywords` a cada rodada; `:589` e `:241` gravam com `save` direto no destino. Usar a saída como
entrada duplica a camada invisível, porque `tinha` conta a camada que nós mesmos escrevemos como
"já tinha texto". `_sem_uso` (`:745`) não tem chamador.

**Solução.** A marca é trocada, não somada. Folha cuja camada é nossa (pela marca) é pulada ou
substituída. A gravação vai por `tobytes()` e `atomic_write_bytes`. `_sem_uso` sai.

**Teste que falha primeiro.** Rodar duas vezes, a saída da primeira como entrada da segunda; a marca
aparece uma vez e a busca por uma palavra devolve um resultado por ocorrência, não dois.

**Aceite.** O teste passa.

## S-822 · Catraca de escrita

**Problema** (confirmado). Além dos casos das S-818 a S-821: `onnx_export.py:61` (`torch.onnx.export`
direto no destino), `cli/texto_estilo_conjunto.py:169` (`manifesto.csv` direto) e `splits.py:252`
(`os.linesep`, então os bytes do `splits.csv` mudam com a plataforma).

**Solução.** Os três consertados (ONNX para um temporário ao lado e `os.replace`). Uma guarda por
AST: nenhum `write_text`, `write_bytes`, `open(..., "w"/"wb"/"a")` ou `.save(` em `src/` fora do
`atomic_io.py` e de uma lista de exceções com razão escrita (log, temporários).

**Teste que falha primeiro.** A guarda, que hoje acusa os pontos acima.

**Aceite.** A guarda passa com a lista de exceções, e a lista só pode encolher (catraca).

## Fase 114 — A tela sabe de onde veio cada resultado

## S-823 · `Ancora(documento, pagina)` pura

**Problema** (confirmado por script e por leitura). `qt/janela.py:1508`: o `quando_pronto` da
leitura captura só `pagina`, e a guarda de `_chegaram_itens` (`:1663`) compara só a página.
`_abriu_livro` (`:1214`) não cancela a tarefa em curso. Ler a página 1 do livro A, abrir o livro B
(que abre na página 1) e deixar a leitura terminar põe os diagramas de A na tela de B; o Ctrl+S
seguinte grava amostras de A com o nome e a página de B, no dataset de treino. No cancelamento
(`:1614`), `_chegaram_itens(self.pdf.page_index, ...)` passa a página **atual**, o que torna a
guarda vácua: virar a página e cancelar arquiva o parcial da página N como página M. A detecção
(`:1457`, `:1642`) tem a mesma forma.

**Causa.** Premissa 2. "O resultado ainda é da tela?" está decidido de três jeitos:
`DeteccaoDeFundo` leva `(documento, pagina)`, `painel_do_pdf._folha_chegou` compara
`(folha.source, folha.indice)`, e a leitura leva só a página.

**Solução.** `ui/ancora.py`: `Ancora(documento: ChaveDoLivro, pagina: int)` congelada e
`ainda_vale(ancora, tela) -> bool`. Capturada no pedido e conferida na chegada pelos três. O
cancelamento usa a âncora capturada. `_abriu_livro` cancela a tarefa em curso.

**Teste que falha primeiro.** Com a `TarefaAdiada` (S-805): ler A, abrir B, soltar a leitura; o
painel não recebe nada e o rodapé diz por quê. Variante: virar a página, cancelar, conferir que o
parcial não é carregado.

**Aceite.** Os dois testes passam, por `QTest`, sem remendar método privado.

## S-824 · Aba Texto arquiva a folha que leu

**Problema** (confirmado por script). `qt/painel_de_texto.py:3871`, em `_leitura_terminou`:
`self._pagina_indice = int(self.campo_de_folha.value()) - 1`. O índice lido está na closure e não
volta no resultado. Ler a folha 5, virar o visualizador para a 9 e deixar a leitura chegar deixa
`documento.origem.pagina == 4` e `folha_atual()[0] == 8`: a aba acha que está na 9 com a 5 na tela.
A troca de livro durante a leitura desenha a folha do livro antigo sob o novo; `_caderno_da_tela`
impede gravá-la no caderno, mas não impede mostrá-la.

**Solução.** `self._pagina_indice = pagina.pagina` (o que veio do resultado), e o resultado de
outro livro é descartado pela `Ancora` da S-823.

**Teste que falha primeiro.** `test_folha_trocada` (hoje falha com `8 != 4`).

**Aceite.** O teste passa, e o de troca de livro também.

## S-825 · `eventFilter` por tabela, com borda

**Problema** (confirmado por leitura). `PainelDeTexto.eventFilter` (`qt/painel_de_texto.py:
4242-4291`, complexidade 34) trata seis assuntos numa cadeia de `if`: histórico do teclado, Esc,
Enter na marca, clique no rodapé, resize do vazio, dica, Ctrl+roda, clique e duplo clique na
miniatura. O comentário de `:4261` registra um `qFatal` que já houve ali, e a defesa foi um
`getattr` local. Outros cinco filtros de `qt/` também não têm borda.

**Solução.** Um dicionário `(objeto, tipo do evento) → tratador`, montado depois de `_montar`, e um
`eventFilter` de dez linhas com `try`/`except` → `logger.exception` e `return False`, como em
`qt/atalhos.py:298`. Os outros cinco filtros ganham a mesma borda por um decorador.

**Teste que falha primeiro.** `Ctrl+roda` e Enter sobre a marca com o tratador remendado para
levantar: o processo segue e o log registra.

**Aceite.** O teste passa; a complexidade do `eventFilter` fica abaixo de 5.

## S-826 · Tarefa sem pai em todos os painéis

**Problema** (confirmado por script, no mecanismo). `trabalho.manter_viva` documenta que uma
`Tarefa` com pai widget aborta o processo ao fechar. A regra vale na janela e é ignorada em 14
lugares: `qt/painel_de_texto.py:2369`, `:2888`, `:2922`, `:3570`, `:3771`, `:3809`;
`analise_da_partida.py:116`; `arvore_de_aberturas.py:441`; `fila_de_livros.py:204`;
`indice_da_base.py:97`; `lote_de_diagramas.py:124`; `painel_de_treino.py:161`, `:263`;
`preferencias.py:428`. O `closeEvent` da janela (`janela.py:2226`) espera o detector, o aquecimento
e a própria tarefa, mas não a da aba Texto. Ler uma folha e fechar a janela basta para o processo
morrer na saída.

**Solução.** `manter_viva(Tarefa(...))` nos 14, com os slots por um `trabalho.slot_se_vivo` (o
`_se_viva` de `janela.py:1581`, promovido). O `closeEvent` espera também as tarefas registradas pela
S-805. Uma guarda por AST: nenhum `Tarefa(` com `parent=`.

**Teste que falha primeiro.** A guarda (acusa os 14); um subprocesso que abre o `PainelDeTexto` com
uma leitura de 2 s, fecha e confere o código de saída 0.

**Aceite.** Os dois passam.

## S-827 · A identidade do livro numa função só

**Problema** (confirmado por leitura). "Mesmo livro" é decidido em cinco lugares:
`ui/galeria_declarada.py:230` (`normcase`), `qt/painel_de_texto.py:4654` (`casefold`), `:4677`
(`Path ==`), `qt/dialogos.py:176` (`resolve ==`, `.lower()` na falha) e `ui/state.py:341`
(`_history_key`, só `resolve`). Hoje concordam porque `resolve` devolve a caixa do disco; num
caminho de rede fora do ar cada um cai num atalho diferente.

**Solução.** `ui/livros.chave_do_livro(caminho) -> ChaveDoLivro`, pura, usada pelos cinco e pela
`Ancora` da S-823.

**Teste que falha primeiro.** Uma tabela de pares (`..`, barra invertida, caixa, caminho que não
resolve) contra a função única; os cinco chamadores trocados por ela não podem mudar nenhum
resultado da tabela.

**Aceite.** Nenhuma comparação de caminho de livro fora da função (guarda por `grep` dos cinco
padrões, com piso zero).

## S-828 · `AppState` tipado no `PainelDeTexto`, e o histórico aparado na leitura

**Problema** (confirmado por leitura). `state_from_dict` (`ui/state.py:364`, complexidade 51) é um
parse único e tipado; a complexidade é repetição. Os defeitos estão em volta:
`PainelDeTexto.aplicar_estado` e `anotar_estado` (`qt/painel_de_texto.py:3174`, `:3196`) recebem
`estado: object` e redeclaram cada padrão do `AppState` por `getattr(estado, "texto_quebra", True)`,
com 14 `type: ignore`: um segundo lugar para os padrões. `MAX_PDF_HISTORY` não é aplicado na
leitura, e um arquivo com 500 entradas segue com 500. A docstring de `_gravar_estado`
(`qt/janela.py:896`) diz que `board_zoom` "não é tocado", e `:922` o grava.

**Solução.** `aplicar_estado(estado: AppState)`, sem `getattr` nem `ignore`. `state_from_dict`
dirigido por uma tabela `(campo, tipo, faixa, padrão)` interpretada por um laço. O histórico aparado
em `state_from_dict`. A docstring corrigida.

**Teste que falha primeiro.** `state_from_dict({"pdf_history": {str(i): 0 for i in range(80)}})`
devolve 50 entradas.

**Aceite.** O teste passa; a complexidade de `state_from_dict` fica abaixo de 10; os 14 `ignore`
somem (a catraca da S-804 desce).

## S-829 · `DeteccaoDeFundo` leva a âncora no próprio sinal

**Problema** (plausível, latente). `qt/trabalho.py:181-216`: `parar` zera `_tarefa` mas não
`_em_curso`. Um `pedir` em seguida inicia outra tarefa, e o `pronto` velho, ainda na fila de
eventos, sai rotulado com o par da nova; o `finished` velho zera a nova, e duas detecções correm.
Hoje `parar` só é chamado no `closeEvent`.

**Solução.** A `Ancora` vai no `partial` do sinal `pronto`, e não num atributo que o próximo pedido
sobrescreve.

**Teste que falha primeiro.** `pedir`, `parar`, `pedir` de outra página, e então os dois sinais na
ordem em que a fila os entregaria: o primeiro resultado sai com a âncora da primeira página.

**Aceite.** O teste passa.

## Fase 115 — Interpretador e documentos

## S-830 · Python 3.13 como interpretador padrão

**Problema** (confirmado). O `README.md:38-43`, o `pyproject.toml:5-12` e a S-436 registram que o
3.10 sai de suporte em outubro de 2026. Hoje é 2026-11-08, o `.python-version` diz `3.10`, o
`.venv` é 3.10 e o `.exe` embarca esse interpretador, sem correção de segurança: o risco que a S-436
nomeou. O CI já roda 3.13 numa perna (`ci.yml:37-39`, com a lista do que falta).

**Solução.** `.python-version` em 3.13, `requires-python >= 3.11` (o piso decidido junto com o dono,
D5), o PyInstaller e o `--selftest` do bundle no 3.13, a perna 3.10 do CI aposentada. O `.venv` de
GPU (memória "GPU para treino") conferido à parte.

**Teste que falha primeiro.** O `tests/test_environment.py` passa a exigir 3.11 ou mais.

**Aceite.** CI verde só em 3.13; o `.exe` gerado roda `--selftest`; o README diz a versão nova.

## S-831 · Documentos no presente do Qt, e os status que se contradizem

**Problema** (confirmado). Restos do Tk no presente: `README.md:178` ("o mesmo `OcrService` que o
Tkinter usa"), `README.md:183` ("widgets de Tk"), `ci.yml:26` e `:37`. `ROADMAP_FASE14.md:22` e
`ROADMAP.md:914` citam "`app_tkinter.py` em 2.226" (o teste compara com `qt/janela.py`, 2.293), e a
mesma linha 22 traz a faixa invertida "S-324 a S-226". Status em conflito: `ROADMAP_FASE14.md:400` e
`:487` com ⚠ e a tabela com ✅; `:906` "S-102 continua aberta" e `:492` com ✅;
`ROADMAP_FASE7.md:1368` "S-36 continua aberta", entregue como S-55; o `ROADMAP_TEXTO_PRECISO.md` só
marca S-711 e S-712, e a spec marca S-710, S-715 a S-718 e S-720; a S-702 tem `###` e não `##` na
spec. O README não cita `cvoff-gallery`, `cvoff-scan` nem `cvoff-texto-conflitos`, e diz que
"`--help` lista o resto", o que nenhum comando faz. O comentário do `pyproject.toml` sobre
`cvoff-texto-status` diz S-178 a S-216 (são 40 itens, até a S-217). `SPEC_REVISAO.md:1336` cita
`cvoff-evaluate`; o comando é `cvoff-eval`. `cvoff-texto-status` diz que a S-182 faz
`tests/test_text_status.py` falhar, e sem os pesos ele pula.

**Solução.** Cada frase corrigida no lugar. O README ganha a lista dos 47 comandos gerada de
`[project.scripts]`, com um teste que compara as duas.

**Teste que falha primeiro.** O teste da lista de comandos (hoje faltam três).

**Aceite.** O teste passa; `grep -n "Tkinter usa\|widgets de Tk\|app_tkinter.py em" README.md docs/`
não acha nada.

## S-832 · A tabela de faixas e o `ARCHITECTURE.md` que enxergam tudo

**Problema** (confirmado). A spec das S-585 a S-598 mora em `ROADMAP_PDF_COM_PGN.md:53-300`, com
`###`, e a tabela "Onde mora a spec de cada item" não tem a linha. A guarda passa porque arquivo
`ROADMAP*` é isento. O `ARCHITECTURE.md:155` diz "meia centena de módulos" em `ui/`, que tem 78; 30
dos 73 módulos de `qt/` e 12 dos 68 de `text/` não são citados, entre eles toda a primeira entrega
das Fases 100 a 107 (`fusao`, `tesseract`, `leitor_de_linha`, `guarda_de_leitura`, `admissao`,
`camada_prosa`, `caderno_na_suite`).

**Solução.** A linha `| S-585 a S-598 | [ROADMAP_PDF_COM_PGN.md](ROADMAP_PDF_COM_PGN.md) |` em toda
cópia da tabela, e a isenção dos `ROADMAP*` restrita a item **não entregue**. O `ARCHITECTURE.md`
com uma linha por módulo, e uma guarda: todo módulo de `qt/`, `text/` e `ui/` aparece nele.

**Teste que falha primeiro.** A guarda do `ARCHITECTURE.md` (acusa 42 módulos) e a da isenção
(acusa as S-585 a S-598).

**Aceite.** As duas passam.

## Fase 116 — Um pipeline só

Os quatro itens desta fase mexem no caminho de medição. Eles entram juntos, e a S-837 remede uma
vez, do checkout principal, por `python -m`.

## S-833 · A exportação reconhece pela mesma função que os relatórios medem

**Problema** (confirmado por leitura). Os relatórios de campo medem `OcrService.recognize_page`
(`field_eval.py:1501`). A exportação (o lote, o `cvoff-export-pgn`, a Galeria, a fila de revisão, as
táticas) passa por `pdf_to_pgn._scan_pages` (`:598-705`), uma cópia da mesma corrente (orientação,
cor, lado, próximo lance, estipulação, legalidade) que já se separou da original:

- `_scan_pages` chama `predict_with_orientation` sem `coordinates=` (`:644-649`), e `service.py:914`
  passa `context.coordinates`, preenchido por `pdf_text.py:1491`. A regra de orientação pelas
  coordenadas da borda funciona no caminho medido e é pulada na exportação;
- `_scan_pages` ignora as opções `colour`, `next_move` e `stipulation`;
- a confiança do portão é calculada duas vezes: `pdf_to_pgn.py:670-675` e
  `RecognizedDiagram.gate_confidence` (`service.py:207-220`).

Os quatro relatórios em `docs/metrics/` descrevem um caminho que não gera PGN nenhum.

**Causa.** Premissa 3.

**Solução.** `_scan_pages` chama `OcrService.recognize_page(..., candidates=...)` e monta
`DiagramPosition.from_recognized(RecognizedDiagram)`. A corrente duplicada e o segundo cálculo do
portão saem. A complexidade de `_scan_pages` (35) cai junto.

**Teste que falha primeiro.** Uma página falsa cujo contexto tem `coordinates`, passada por
`iter_pdf_diagrams` e por `recognize_page`, com `predict_with_orientation` remendado para registrar
os argumentos: os dois caminhos têm de dar os mesmos argumentos, a mesma FEN, a mesma rotação e a
mesma confiança do portão.

**Aceite.** O teste passa, e `pdf_to_pgn.py` não chama `predict_with_orientation` (guarda por
`grep`).

## S-834 · Decodificação restrita sem relógio

**Problema** (confirmado por script). `decode.py:386-391`, `SEGUNDOS_MAXIMOS = 0.5`: a busca para
pelo relógio. Em 40 tabuleiros sintéticos com ruído, 2 saem com FEN ou `constraints_satisfied`
diferentes com orçamento de 50 ms e sem orçamento; 3 levam mais de 50 ms. A mesma probabilidade
decodifica diferente numa máquina carregada, em rodadas paralelas ou na primeira chamada lenta de
um processo (uma causa plausível da memória "primeira leitura do processo difere"), e o relatório
de campo deixa de ser reproduzível.

**Causa.** Premissa 5.

**Solução.** Orçamento em expansões (`max_expansions`), calibrado para o pior caso medido ficar
abaixo de ~0,5 s nesta máquina. O relógio sai.

**Teste que falha primeiro.** Remendar `decode.time.monotonic` para avançar 1 s por chamada: o
resultado tem de ser igual ao de sem remendo.

**Aceite.** O teste passa; os 40 tabuleiros dão o mesmo resultado em dez rodadas com carga
paralela.

## S-835 · Contadores de campo por campo tipado, não por frase

**Problema** (confirmado por leitura). `field_eval.py:1225` e `:1233` contam
`next_move_ambiguous` e `stipulation_ambiguous` por `"trocas diferentes" in reason`, frase escrita
em `lance_seguinte.py:269` e `estipulacao.py:484`. `only_king_missing` confere
`startswith("falta o rei")` (`decode.py:116`), frase definida também em `fen_utils.py:53` e
`ui/legality.py:116`. Reescrever uma mensagem zera um contador publicado, sem teste nenhum falhar.

**Causa.** Premissa 4.

**Solução.** `ambigua: bool` nos resultados de reparo do próximo lance e da estipulação, e
`tipo: TipoDeViolacao` (enum) na `_Violation`. `evaluate_page` (complexidade 50) passa a somar por
`FieldReport.somar_leitura(leitura)` a partir desses campos, e o julgamento de cada anotação vira
`_julgar(anotado, lido, limiar) -> Veredito`.

**Teste que falha primeiro.** Trocar o texto das duas mensagens por outro: os contadores têm de
continuar contando. Antes de partir `evaluate_page`, um teste de caracterização que compara byte a
byte o JSON do relatório em fixtures.

**Aceite.** Os dois passam; `evaluate_page` abaixo de complexidade 15.

## S-836 · Fonte de diagrama e rótulo de eixo numa regra só

**Problema** (confirmado por script). Duas regras de "fonte de diagrama" que discordam:
`pdf_text.py:348-371` e `text/admissao.py:62-65`. `Leipzig` é diagrama para a `admissao` e texto
para `page_text_lines`; `Schachfiguren` e `XadrezFont`, o contrário; `ChessMerida` é diagrama e
figurina ao mesmo tempo na `admissao`. E `leitor.EIXO_SOLTO` e `MIN_EIXOS_NA_FILA`
(`text/leitor.py:748-756`) repetem `pdf_text._AXIS_LABEL` e `_MIN_AXIS_LABELS` (`:341-342`), que o
leitor importa pelo nome privado (`:817`).

**Solução.** `fontes_de_xadrez.py` com os padrões de fonte de diagrama e de figurina, importado
pelos dois lados; as constantes de eixo públicas nele. `_page_lines` (complexidade 36) parte em
`_linhas_do_bloco`, `_sem_eixos_no_bloco`, `_sem_eixos_na_pagina` e `_agrupar`.

**Teste que falha primeiro.** Uma tabela de nomes de fonte em que os dois consumidores têm de
concordar (hoje discordam em quatro).

**Aceite.** O teste passa; nenhum import de nome privado de `pdf_text` fora dele.

## S-837 · Remedição dos quatro relatórios de campo

**Problema.** As S-833 a S-836 mudam o caminho de medição, e a S-218 obriga a remedir os quatro
relatórios de `docs/metrics/`.

**Solução.** Primeiro, reproduzir o relatório arquivado com o `src/` de antes das quatro (memória
"reproduzir o relatório antes de republicar"). Depois, remedir do checkout principal, que tem os
`.pt` e o `PDF/`, por `python -m` (não pelo `cvoff-field`, que lê o `settings.json`), e registrar o
código e o modelo no relatório.

**Aceite.** Os quatro relatórios declaram o commit e o checkpoint. A diferença para os anteriores
está explicada item a item, com a S-833 como causa esperada nas páginas com coordenadas na borda.

## Fase 117 — Treino honesto

## S-838 · Página de campo nunca vai para o treino

**Problema** (confirmado por leitura). `training.py:325-333` e `:346-359`: `ensure_splits` grava o
`splits.csv` (com amostras novas talvez sorteadas para `train`) **antes** de `pin_field_pages` mover
as amostras de página de campo para `test` e gravar de novo. Uma queda entre as duas gravações deixa
a atribuição a `train` no disco, e na rodada seguinte as amostras já não são novas, então nunca são
fixadas (split registrado não se move). Se `field_set.jsonl` não lê, `field_pages_beside` avisa no
log e devolve `set()`, com o mesmo resultado permanente. E o casamento compara `source_pdf` exato,
enquanto `field_eval._name_keys` (`field_eval.py:1389`) normaliza NFC e dupla codificação.

**Solução.** As atribuições forçadas entram em `ensure_splits`, que grava uma vez. Conjunto de
campo ilegível falha fechado: as amostras novas ficam sem partição e o treino recusa começar, dizendo
por quê. O casamento usa a chave de nome de `field_eval`, num lugar só.

**Teste que falha primeiro.** `field_set.jsonl` de lixo e um rótulo novo de página de campo:
`resolve_splits` não o põe em `train`. Segundo caso: `pin_field_pages` remendado para levantar,
nova rodada, a amostra termina em `test`.

**Aceite.** Os dois passam.

## S-839 · O regime do checkpoint guardado inteiro

**Problema** (confirmado por script). `augment.py:103-135`, `:143-183`: `AugmentConfig(hatch=0.9)`
e a probabilidade padrão de hachura dão a mesma letra, `augh`. `from_letters("augh-j0")` descarta o
sufixo `-j0` em silêncio. `version_of_checkpoint` devolve `aug0` tanto para um `.pt` truncado quanto
para um que não existe. "Retreinar no regime do checkpoint" (`ui/pedido_de_treino.py:90`) pode treinar
noutro regime e gravar a letra errada: a mesma classe de defeito do incidente `augx` (memória
"regime do checkpoint exige a letra").

**Solução.** O metadado do checkpoint guarda `asdict(augment)`, e o regime é reconstruído dele,
exato. A letra continua como nome curto, derivada. `from_letters` levanta diante de sufixo que não
sabe honrar. `version_of_checkpoint` levanta para arquivo ilegível e devolve `None` para arquivo
ausente.

**Teste que falha primeiro.** `from_letters(c.version) == c` para configurações com sufixo, ou
`ValueError`; `version_of_checkpoint` de um `.pt` truncado levanta.

**Aceite.** Os dois passam; um checkpoint antigo, sem o dicionário, é lido pela letra com aviso.

## S-840 · `ArchConfig.from_version` recusa o que não conhece

**Problema** (confirmado por script). `model.py:92-97`, com `# type: ignore`: `"cnn-grey-64-linear"`
monta um modelo de 3 canais (tudo que não é `gray` vira RGB); `"resnet-..."` e `"...-mlp"` montam
`PieceClassifier` em silêncio; `build_model` e `PieceClassifier` caem num `else` para valor
desconhecido.

**Solução.** Cada parte conferida contra `typing.get_args(Backbone)`, `get_args(Channels)` e
`get_args(Head)`, com `ValueError`. Os `else` viram `assert_never`. O `ignore` sai.

**Teste que falha primeiro.** `pytest.raises(ValueError)` para as três strings acima.

**Aceite.** O teste passa; o mypy acusa um `Literal` novo não tratado.

## S-841 · O dataset conta e diz o que descarta

**Problema** (confirmado por leitura). `dataset.py:140-141` descarta linha de FEN inválida sem
contador e sem log, e todo outro descarte do mesmo módulo é registrado. Um rótulo estragado some do
treino sem ninguém saber.

**Solução.** Contador por motivo de descarte no `Dataset`, logado no fim da carga e gravado no
metadado do checkpoint. (A colisão de nome de amostra é da S-820.)

**Teste que falha primeiro.** Um CSV com uma FEN inválida entre dez boas: dez amostras, e o
contador "fen inválida" em 1.

**Aceite.** O teste passa; o metadado do checkpoint traz os contadores.

## S-842 · Colocação: um parser de FEN só, na fronteira

**Problema** (confirmado por script). `fen_utils.py:196-228`: `labels_from_fen` aceita
`8/.../44`, `.../4004` e `.../08`, que o python-chess recusa; `fen_from_class_indices([13] * 64)`
(`:287`) levanta `KeyError`, e não `ValueError`, e confere o tamanho só depois de indexar. Há dois
parsers de FEN que discordam.

**Solução.** `Colocacao`: tupla de 64 `Peca | None`, construída só por `Colocacao.de_fen(texto)`
(dígitos 1 a 8, nunca dois seguidos, oito fileiras de oito) e por `Colocacao.de_classes(indices)`.
Rótulos, FEN e legalidade consomem o tipo. Entregue em pedaços: o parser primeiro, depois cada
consumidor.

**Teste que falha primeiro.** As três entradas acima recusadas por `labels_from_fen` **e** por
`is_syntactically_valid_fen`; `[13] * 64` dá `ValueError`.

**Aceite.** Os testes passam; um teste de propriedade compara `Colocacao.de_fen` com o python-chess
em 10 mil FENs sorteadas.

## S-843 · O normalizador de tabuleiro sai

**Problema** (confirmado por leitura). Nada em `src/` constrói um `NormalizerConfig` além do
`IDENTITY` padrão (`preprocess.py:163`). A docstring (`:28-36`, `:124`) diz que o treino normaliza em
`_load_board` e que a versão vai para `ArchConfig.version`; nenhuma das duas coisas é verdade. Ligar
o normalizador criaria um desvio entre treino e serviço que nada registraria.

**Solução.** Subtrair antes de somar: o parâmetro sai de `service` e `inference`, e o normalizador
sai com ele. Se um dia voltar, volta registrado no checkpoint.

**Teste que falha primeiro.** Não há teste honesto de "código morto saiu" além do `mypy` e da suíte;
o item fecha pelo `grep` de `NormalizerConfig` sem resultado e a suíte verde.

**Aceite.** `grep -rn NormalizerConfig src/` vazio; suíte verde.

## S-844 · Identidade de livro nos splits

**Problema** (plausível). `splits.py:124-186`: `groups_by_book` e `groups_by_origin` agrupam pela
string exata de `source_pdf`. O acervo tem o mesmo livro sob vários nomes (`...Copia.pdf`,
`...Copia_hq.pdf`, uma tradução; memória "acervo PDF tem livros duplicados"), e esses grupos não os
mantêm juntos: a mesma página pode cair no treino e no teste.

**Solução.** Uma identidade de livro derivada na fronteira: hash do conteúdo do PDF (D2 opção a) ou
uma tabela de apelidos em `data/` (D2 opção b). Os dois agrupamentos usam a identidade.

**Teste que falha primeiro.** Dois nomes do mesmo livro: os dois caem no mesmo grupo.

**Aceite.** O teste passa; uma contagem no acervo real diz quantas amostras mudariam de partição, e
a mudança é decidida com o dono antes de gravar o `splits.csv`.

## S-845 · `torch.load` só com `weights_only`

**Problema** (confirmado por leitura). `checkpoint.py:110-112`: o recurso de `TypeError` para
`torch.load` sem `weights_only` é morto no torch atual e abre um caminho de `pickle` para arquivo
vindo de fora.

**Solução.** O recurso sai; versão de torch sem `weights_only` é recusada na carga, com mensagem.

**Teste que falha primeiro.** Um `.pt` com um objeto `pickle` arbitrário dentro: a carga recusa.

**Aceite.** O teste passa.

## S-846 · O sal do split fixado por valor

**Problema** (confirmado). `tests/test_splits.py:30-35` diz "Valores fixos: se o algoritmo de hash
mudar, isto quebra de propósito", e faz `assertEqual(assign_split("board_00000.png"),
assign_split("board_00000.png"))`: a função comparada com ela mesma. Mudar `SPLIT_SALT` ou o hash
embaralharia treino, validação e teste com a suíte verde. O mesmo em
`tests/test_detection_census.py:107` e `tests/test_side_survey.py:53`.

**Solução.** Dez pares `nome → partição` escritos no teste, e a lista de `sample_pages(100, 4)`
escrita por valor.

**Teste que falha primeiro.** O teste novo, contra um `SPLIT_SALT` trocado num remendo: tem de
reprovar.

**Aceite.** Os três testes fixam valores; o mutator (S-803) mata a troca do sal.

## Fase 118 — Texto: fronteira e decisões únicas

Os itens desta fase mexem em `text/leitor.py`, `fusao.py` e `pagina.py`, os mesmos arquivos das Fases
100 a 107. Cada um entra num ramo próprio, a partir da `main` que já tem a última entrega da prosa,
e o crítico da skill `ocr-texto-preciso` mede a régua antes e depois.

## S-847 · `ocr.glyph_model` chega à leitura de página

**Problema** (confirmado por leitura). `text/leitor.py:1234` (`_ha_classificador`) carrega o
`CAMINHO_PADRAO_META` fixo, e `:595-599` chama `build_glyph_recognizer()` sem argumento
(`text/recognizer.py:186-190`). Quem chama sem `reconhecedor` é a aba Texto
(`qt/painel_de_texto.py:4578`). Só `ocr.build_recognizer`, o caminho da legenda, lê
`ocr.glyph_model` e `CVOFF_OCR_GLYPH_MODEL`. O `ModeloInvalido` (`text/modelo.py:432`) manda o
usuário configurar exatamente isso. Com `motor="auto"`, quem pôs os pesos noutra pasta cai para a
camada com um aviso no log; com `glifo`, recebe um erro que manda configurar o que já está
configurado.

**Solução.** `classificador_configurado()` em `recognizer.py`, que lê a configuração uma vez na
fronteira; `_ha_classificador` e `linhas_do_glifo` recebem o resultado.

**Teste que falha primeiro.** Configuração apontando para uma cópia temporária do par de pesos,
caminho padrão ausente: `ler_pagina(motor="auto")` sai com procedência `glifo`.

**Aceite.** O teste passa.

## S-848 · `PaginaLida.de_json` na fronteira

**Problema** (confirmado por script). `text/pagina.py:399-411`, `:561-573`, `:936-960`:
`{"largura": null}`, `{"colunas": null}` e `indice: null` levantam `TypeError`, que atravessa o
`_carregar` do caderno (`caderno.py:385` só pega `OSError` e `ValueError`). `"texto": null` vira a
string `"None"`; `confianca: "nan"` passa. Um bloco gravado como `camada` com confiança 1,0 abre
assim mesmo quando a linha dele é `glifo` com 0,2, porque os campos derivados são lidos do arquivo
em vez de recalculados: o estado ilegal que `menos_confiavel` existe para impedir.

**Solução.** Um `try` só em `PaginaLida.de_json`, convertendo `TypeError`, `ValueError` e `KeyError`
em `PaginaInvalida`. `texto` exige `str`; NaN é recusado. `BlocoDeTexto.de_json` recalcula caixa,
confiança, procedência, negrito e itálico por `de_linhas`, e lê do arquivo só `recuado` e
`legenda_de`. Os dois `de_json` quase iguais (`:561`, `:701`, semelhança 0,86) viram um.

**Teste que falha primeiro.** Os três JSONs levantam `PaginaInvalida`; o bloco inconsistente abre
como `glifo` com 0,2.

**Aceite.** Os dois passam.

## S-849 · "Camada de OCR" numa regra só

**Problema** (confirmado por script). Três respostas para "esta camada de texto foi feita por OCR?":
`admissao.PRODUTOR_DE_OCR` (`text/admissao.py:60`), `cli/texto_grade.MARCAS_DE_OCR` (`:107`, com
`glyphless` em `:277`) e `camada.camada_tipografica` (`text/camada.py:201`). `ocrmypdf ... /
Tesseract` é OCR para o `texto_grade` e não para a `admissao`; `OmniPage`, o contrário. A memória
"medir texto só com camada editorada" depende desta resposta.

**Solução.** `procedencia_da_camada(doc, pagina) -> ProcedenciaDaCamada` pura, num lugar, e os três
passam a consultá-la.

**Teste que falha primeiro.** Uma tabela de produtores e fontes com resposta única.

**Aceite.** O teste passa; o ouro-teste (S-702) é reconferido com a regra única, e nenhum livro muda
de estrato sem decisão do dono.

## S-850 · Cache de perfil do livro sem `id()`

**Problema** (confirmado por script). `text/camada_prosa.py:218-228`: documento aberto de bytes tem
`name=None`, e a chave do cache vira `id(doc)`. O id foi reaproveitado e o livro B recebeu o perfil
do livro A. A chave também não tem `mtime`. `camada._identidade` (`text/camada.py:385-400`) recusa
exatamente esse caso, por escrito.

**Solução.** O cache usa `_identidade`, e não guarda nada quando ela é `None`. Uma identidade só para
`_RESPOSTAS` e `_perfis`.

**Teste que falha primeiro.** Dois documentos de bytes abertos e fechados em sequência: o perfil do
segundo é recalculado (contador em `perfil_do_livro`).

**Aceite.** O teste passa.

## S-851 · A folha extraída uma vez por leitura

**Problema** (confirmado por script, desempenho). Uma `ler_pagina(motor="camada")` faz 8
`get_text("dict")` na folha lida e mais 2 ou 3 em cada vizinha (`text/leitor.py:1651-1680`,
`:1316-1331`): `page_margin_lines`, `page_text_lines`, `spans_com` e `linhas_com` do negrito e do
itálico, `camada_tipografica`, `quadros` e as correntes das vizinhas. Numa varredura, cada folha é
reextraída umas 5 vezes como vizinha. A S-725 cobre só o cache do Tesseract.

**Solução.** Um valor congelado `FolhaDaCamada` (dict, palavras, texttrace), extraído uma vez e
entregue a funções puras; as chaves de corrente das vizinhas memorizadas por documento.

**Teste que falha primeiro.** O mesmo contador, exigindo no máximo um `get_text("dict")` por folha.

**Aceite.** O teste passa; a régua da prosa sai igual byte a byte; o tempo por folha numa varredura
de 50 folhas é medido antes e depois.

## S-852 · Um árbitro de confiança só

**Problema** (confirmado por leitura e pelo dryer). O árbitro está em três cópias:
`text/leitor.py:496-513`, `cli/texto_colados.py:62-73` e `cli/texto_duas_linhas.py:107-118`
(semelhança 0,83 a 0,91). O comentário justifica a cópia: "Escrito igual ao de lá de propósito".
Uma edição numa cópia separa o que foi medido do que roda. Os módulos `text/colados.py` e
`text/duas_linhas.py` são gêmeos (`vale` e `_perfil_*` com semelhança 1,00).

**Causa.** Premissa 3.

**Solução.** `colados.arbitro_de_confianca` público, e as duas cópias do CLI apagadas. Os gêmeos
`colados`/`duas_linhas` compartilham `vale` e o perfil por um parâmetro de eixo.

**Teste que falha primeiro.** Um teste que importa o árbitro dos três chamadores e confere que é o
mesmo objeto.

**Aceite.** O teste passa; o dryer não acusa mais os pares.

## S-853 · Contrato do leitor de linha: `None` é "não leu"

**Problema** (confirmado por leitura). O contrato de `text/leitor_de_linha.py:3` diz que `None` é
"não leu" e `""` é "leu vazio". `tesseract.ler_linhas` (`text/tesseract.py:363-366`) devolve `""`
para recorte vazio, que nunca foi ao processo. Com essa leitura vazia, `fundir` derruba a prosa do
glifo, e `text/leitor.py:1395` (`if not tokens: continue`) apaga a linha inteira. E em
`text/leitor.py:1747`, `leituras_da_reserva, _falha = leitor.ler_folha(...)`: no ramo
`camada_na_folha` a falha é jogada fora, enquanto os outros ramos emitem `LEITOR_INDISPONIVEL`. Um
terceiro furo, plausível: `_linhas_da_reserva` alinha as confianças por
`zip(texto.split(), confiancas, strict=False)`, e uma palavra do Tesseract com espaço Unicode dentro
(U+2009) desloca ou corta as confianças sem erro (`text/fusao.py:233` faz o mesmo).

**Solução.** `None` para recorte vazio. `if _falha: avisos.append(Aviso(LEITOR_INDISPONIVEL, ...))`.
Os `Token` construídos direto da lista de `Palavra`, com `strict=True`. A regra 5 da fusão continua
sendo da S-721.

**Teste que falha primeiro.** Um `LeitorDeLinha` falso devolvendo `([], "sem tesseract")` numa folha
admitida com `guarda.nao_lida`: o aviso tem de estar na página. Uma palavra com U+2009: as
confianças continuam alinhadas.

**Aceite.** Os dois passam.

## S-854 · Classificador de glifo e pré-processamento, um só para PyTorch e ONNX

**Problema** (confirmado pelo dryer e por leitura). `text/modelo.py:365` e
`text/onnx_glifos.py:229` (`classificar`) têm semelhança 1,00, e `modelo._entrada` (`:335`) e
`onnx_glifos.preparar_recortes` (`:187`), 0,82. Duas cópias do pré-processamento de glifo são um
desvio entre treino e serviço esperando acontecer. E `carregar_classificador` calcula o SHA-256 do
`.pt` e relê o metadado antes de consultar o cache (`text/modelo.py:423-457`), duas vezes por folha,
e cria um `GlyphRecognizer` novo a cada uma.

**Solução.** O pré-processamento numa função só, que os dois backends chamam. O cache do
classificador chaveado por `(caminho, mtime_ns, tamanho)`, com o hash calculado só quando a chave
falta.

**Teste que falha primeiro.** Os dois backends recebem o mesmo recorte e têm de produzir o mesmo
tensor de entrada; dez folhas seguidas calculam o hash uma vez.

**Aceite.** Os dois passam.

## S-855 · Tipos fechados no texto

**Problema** (confirmado por leitura). `ouro.Manifesto` guarda `split`, `lingua`, `origem`,
`estrato` e `diagramacao` como `str`, conferidos depois em `problemas`; `LivroDoOuro(**livro)`
levanta `TypeError` com chave desconhecida (`text/ouro.py:137-146`). `fusao.Token.origem: str`
(`text/fusao.py:206`), `classe_do_token -> str` e `PaginaLida.unidade: str` deveriam ser fechados.
`_ler_pagina_do_livro` recebe 24 parâmetros nomeados. E `text/vertical.py` (complexidade 28 em
`candidatos`) só tem chamador no `cli/texto_vertical`; `Caixa.angulo` (`text/boxes.py:84-96`) é
sempre 0 em produção, e o ramo `girado` de `linhas.quebrar_em_linhas` é morto.

**Solução.** `Literal` ou `StrEnum`, convertidos uma vez em `de_json`. Uma `OpcoesDeLeitura`
congelada no lugar dos 24 parâmetros. `text/vertical.py`: decisão D3 do roadmap (ligar a S-197 no
caminho da página, ou mover o módulo para o CLI e apagar o ramo `girado`).

**Teste que falha primeiro.** Um manifesto com `estrato` desconhecido levanta na leitura, e não em
`problemas`.

**Aceite.** O teste passa; o mypy acusa um valor fora do `Literal` escrito num teste de tipo.

## S-856 · Exceções estreitas no texto

**Problema** (confirmado por leitura). `ocr_caption._read_band` (`ocr_caption.py:233-237`) devolve
`[]` quando o motor quebra: "sem legenda" fica igual a "motor caiu", e só o log diz qual.
`pdf_text.py:1434` e `text/camada.py:113`, `:158`, `:434`, `:445` usam `except Exception`; em `:434`
e `:445` o `False` vai ao chamador, e em `:445`, se todas as folhas da amostra derem erro, o `False`
vai para o cache.

**Solução.** Cada `except` pega só o tipo esperado. `_read_band` devolve um resultado que distingue
"sem legenda" de "motor indisponível". Resposta que veio de exceção não entra no cache.

**Teste que falha primeiro.** Um motor de legenda que levanta: o resultado diz "indisponível", não
"vazio". Uma amostra em que toda folha levanta: a próxima chamada pergunta de novo.

**Aceite.** Os dois passam; a catraca da S-804 desce.

## Fase 119 — Complexidade e duplicação

Toda divisão desta fase segue a mesma ordem: fixar o que o código faz (teste de caracterização,
byte a byte quando a saída é um arquivo), mudar a estrutura, provar que o comportamento não mudou.
Função do caminho de medição só se divide junto da S-837, ou com a caracterização sobre as páginas
de campo.

## S-857 · Argumentos comuns dos 47 comandos num lugar

**Problema** (confirmado pelo dryer e por leitura). Cerca de 30 dos 65 pares do dryer são
`parse_args` e `build_parser` de `cli/` (`texto_grade` e `texto_ordem` com 1,00; `review` e `sides`
com 0,88; `export_pgn` com `field`, `review` e `sides`). E `cli/__init__.py:246-259` classifica
qualquer `ValueError`, `OSError` ou `RuntimeError`, inclusive um `int("x")` de defeito interno, como
saída 2 "entrada inválida"; decide a saída 3 pela substring `".pt"`; e deixa `sqlite3.Error` cair na
saída 1.

**Solução.** `cli/opcoes.py` com as opções repetidas (`--pdf`, `--pages`, `--dpi`, `--checkpoint`,
`--out`, `--cache`, `--database`) como funções que acrescentam ao parser. Um tipo `EntradaInvalida`
levantado só nas fronteiras de entrada; todo o resto é saída 1, com traceback no log.

**Teste que falha primeiro.** Um `int("x")` dentro de um carregador sai com 1, não com 2; um PDF que
não existe sai com 2.

**Aceite.** Os dois passam; o dryer não acusa mais os pares de `cli/`.

## S-858 · Partir `build_pgn_games` e `Trainer.prepare`

**Problema.** `pdf_to_pgn.build_pgn_games` (complexidade 42) e `training.Trainer.prepare` (36).

**Solução.** `build_pgn_games`: um construtor de cabeçalhos por assunto (identidade e fonte, lado a
mover, contexto e legenda, confiança do OCR, reparos de próximo lance e cor, estipulação,
proveniência, legalidade e rotação), cada um devolvendo um `dict`, e o chamador faz
`game.headers.update(...)`. `Trainer.prepare`: `_resolver_datasets()` (splits gravados ou sorteio)
devolvendo um `Datasets` tipado, `_sabotagem_de_rotulos()`, as duas estratégias de carregador e
`_metadado_base()` pura.

**Teste que falha primeiro.** Um PGN de ouro gerado de fixtures, comparado byte a byte; o metadado
de um treino de uma época sobre o dataset de brinquedo, comparado campo a campo.

**Aceite.** Os dois passam antes e depois; as duas funções abaixo de complexidade 10.

## S-859 · Partir a detecção em cadeias de filtros

**Problema.** `detection/hybrid.detect_diagrams` (36), `board_detection._contour_candidates` (28) e
`detector_de_marcas.classificar` (31).

**Solução.** `detect_diagrams`: estágio embutido (piso e refino), estágio de contorno como uma
cadeia de filtros `(candidato) -> motivo | None` (conflito de sobreposição, prior de tamanho), um
lugar só que registra as recusas, e a seleção (teto por escore, ordem de leitura); os fechos
`_recusado` e `_caixa_do_quad` no nível do módulo. `_contour_candidates`: cada recusa vira um filtro
que devolve um `QuadRecusado`. `classificar`: tabela ordenada de regras, primeiro as de forma
(proporção, toca a borda, tamanho), depois a família pela faixa de solidez (estrela, disco, cruz) e a
variante pelo centro claro, com os limiares nomeados.

**Teste que falha primeiro.** Caracterização: as caixas e os motivos de recusa de 20 páginas de
fixture, gravados antes, comparados depois.

**Aceite.** A caracterização passa; as três abaixo de complexidade 10. `detect_diagrams` é caminho
de medição: entra junto da S-837 ou com a caracterização sobre as páginas de campo.

## S-860 · Partir `_ler_pagina_do_livro` e `linhas_do_glifo`

**Problema.** `text/leitor._ler_pagina_do_livro` (71, a maior do projeto) e `linhas_do_glifo` (37).

**Solução.** `_ler_pagina_do_livro` em cinco: a extração da folha (a `FolhaDaCamada` da S-851), a
detecção dos diagramas, o corpo despachado por motor (`_corpo_camada`, `_corpo_glifo` →
`_guarda_e_reserva` → `_prosa_de_outro_leitor`), devolvendo uma `LeituraDoCorpo(cruas, regioes,
quadros, procedencia, avisos, por_palavra)` em vez de reatribuir a tupla, `anotar_estilo` pura, e
`montar` com as margens. `linhas_do_glifo`: o classificador vem de fora (S-847); as sete correções
viram uma lista `list[Correcao]` montada uma vez das opções.

**Teste que falha primeiro.** A régua da prosa e o JSON de página das folhas do ouro-dev, gravados
antes, comparados byte a byte depois.

**Aceite.** A caracterização passa; as duas abaixo de complexidade 15. Coordenado com as Fases 100 a
107 (seção da Fase 118).

## S-861 · Partir `problemas` e `fundir`

**Problema.** `text/ouro.problemas` (53) e `text/fusao.fundir` (36). `leitor.montar` (34) segue o
mesmo molde.

**Solução.** `problemas`: a conversão na fronteira (S-855) tira uns 15 ramos; o resto se divide em
`_do_cabecalho`, `_dos_livros`, `_das_folhas` e `_do_teste`, puras, cada uma devolvendo
`list[str]`. `fundir`: `_decidir_par(g, t, bloqueado, existe) -> Origem` pura, como tabela de
decisão; `_ajustar_lance` para o número partido, o dígito absorvido e a palavra colada;
`_sem_par_do_glifo` e `_sem_par_do_leitor`.

**Teste que falha primeiro.** Para `problemas`, um manifesto com um defeito de cada tipo e a lista de
mensagens esperada; para `fundir`, a saída da fusão nas folhas do ouro-dev, gravada antes.

**Aceite.** As duas caracterizações passam; as duas abaixo de complexidade 10.

## S-862 · Constantes de caminho e de padrão num lugar

**Problema** (confirmado por leitura). O DPI 220 está em `config.py:289`, `settings.py:418` e
`provenance.py:73`. `char_classifier.pt` e `char_meta.json` em `settings.py:283`, `:289`,
`cli/texto_train.py:34-35` e `text/modelo.py:55`. `field_set.jsonl` em `cli/field.py:54`,
`qt/campo.py:64` e `training.py:350` (derivado de outro jeito). `texto_conflitos.json` em
`cli/texto_conflitos.py:32` e `text/conflitos.py:57`. `"lado_descritor": 24` escrito à mão em
`cli/texto_conflitos.py`, ao lado de `dedupe.LADO_DESCRITOR`. Os nomes `procedencias.py`,
`proveniencia.py` e `provenance.py` não duplicam decisão nenhuma, mas confundem.

**Solução.** Uma constante por valor, no módulo dono, importada pelos outros. A troca de nome de
`procedencias.py` é a decisão D6 do roadmap.

**Teste que falha primeiro.** Uma guarda por AST: cada um dos literais acima aparece uma vez em
`src/`.

**Aceite.** A guarda passa.

## S-863 · Os `main` de CLI de complexidade alta

**Problema.** `cli/texto_train.main` (49), `cli/audit._print_report` (39), `cli/audit.main` (29),
`cli/texto_conflitos.main` (29), `cli/texto_placar.main` (28) e `cli/texto_grade.medir` (29).

**Solução.** Cada `main` fica com três passos: parse (S-857), uma função pura que decide o que fazer
e devolve um plano, e a execução do plano. `_print_report` vira uma lista de seções, cada uma uma
função que devolve linhas.

**Teste que falha primeiro.** A saída de cada comando sobre fixtures, gravada antes.

**Aceite.** As caracterizações passam; os seis abaixo de complexidade 15.

## S-864 · Os pares gêmeos do dryer

**Problema** (confirmado pelo dryer). Além dos já tratados (S-848, S-852, S-854, S-857): os
exportadores `docx_saida.exportar_estudo_docx`/`exportar_texto_docx` e `epub.exportar_estudo_epub`/
`exportar_texto_epub` (0,90 e 0,91); `qt/painel_da_galeria._confirmar_destrutivo` e
`qt/painel_de_estudo._perguntar` (1,00); `qt/arvore_de_aberturas._rodape` e
`qt/busca_de_partidas._rodape` (0,88); `qt/painel_de_recorte._anel` e `qt/tabuleiro_editavel._anel`
(0,81); `detection_census.as_dict` e `side_survey.as_dict` (0,94); `estudo_arquivo.chave_de` e
`text/rascunho.chave_de` (0,88); `cli/texto_grade._linhas_da_camada` e
`cli/texto_ordem._linhas_da_camada` (0,84); `pdf_substituicao.renderizar_com_operacoes` e
`renderizar_regiao_com_operacoes` (1,00); `qt/painel_de_estudo.buscar_partidas` e
`arvore_de_aberturas` (0,95).

**Solução.** Para cada par, decidir se é a mesma decisão (junta) ou só o mesmo esqueleto (declara no
`dryer.json` com a razão). Os exportadores passam a ser um percurso do estudo com dois escritores.

**Teste que falha primeiro.** Os testes existentes de cada par, mais um de caracterização onde não
houver.

**Aceite.** Nenhum par ≥ 0,8 sem decisão escrita.

## Fase 120 — Os arquivos-deus do Qt

## S-865 · `PainelDeTexto` em cinco módulos

**Problema** (confirmado). `qt/painel_de_texto.py` tem 5.030 linhas; a classe `PainelDeTexto` vai de
`:324` a cerca de `:4549`, com 294 métodos, 73 atributos privados e 24 seções marcadas.

**Solução.** Cinco passos, cada um com a suíte verde e a fachada pública (`aplicar_estado`,
`definir_livro`, `ler`, `confirmar_fechamento`) intacta: (1) `qt/texto_espelho.py`: `_Trecho`,
`_Mapa`, `_texto_da_tela`, `_do_qt` e a digitação (`:4072-4240`), quase tudo puro; (2)
`qt/texto_leitura.py`: a orquestração de tarefa (`:3635-3912`, as exportações e
`trazer_da_revisao`) num `ExecutorDaAba` com `manter_viva`, `slot_se_vivo` e a `Ancora`; (3)
`qt/texto_caderno.py`: caderno, rascunho e mesa; (4) `qt/texto_miniaturas.py`: diagramas no texto,
miniatura, dica e menu; (5) `qt/texto_correcao.py`: léxico, correção, pincel e busca.

**Teste que falha primeiro.** Nenhum novo: a divisão é refatoração, e a suíte da aba Texto (mais os
testes das S-823 a S-826) é a caracterização.

**Aceite.** `PainelDeTexto` com menos de 800 linhas, como composição das cinco partes.

## S-866 · `PainelDeEstudo` sem o motor, a análise, as táticas e o índice

**Problema.** `qt/painel_de_estudo.py` tem 3.660 linhas e seis classes.

**Solução.** Primeiro sai o motor vivo, a análise, as táticas e o índice (`:2280-2720`,
`:3185-3280`), com âncora e `manter_viva`; depois a lista de lances.

**Aceite.** Suíte verde em cada passo; o arquivo abaixo de 1.500 linhas.

## S-867 · O bloco de resposta da janela vira decisão pura

**Problema.** `qt/janela.py` (2.293 linhas) é coordenadora legítima, mas o bloco que decide o que
fazer com a resposta de uma leitura (`:1620-1720`) é lógica de domínio dentro do widget.

**Solução.** `ui/page_results` recebe a `Ancora` (S-823) e a resposta e devolve o que a tela deve
mostrar; a janela só aplica. É um passo para a S-31.

**Teste que falha primeiro.** A decisão testada sem Qt, com os casos da S-823.

**Aceite.** O teste passa sem importar PyQt6; a janela perde o bloco.

## Fase 121 — Testes que medem comportamento

## S-868 · Os 26 testes desligados

**Problema** (confirmado). 26 `@unittest.skip` incondicionais: `tests/test_qt_tema.py` (13, motivo
`FOLHA_DO_MAIN`, `:28`), `tests/test_qt_painel_da_galeria.py:482-602` (8, `GALERIA_DO_MAIN`) e
`tests/test_qt_tamanho_da_janela.py` (5, `GALERIA_DO_MAIN` e `RODAPE_DO_MAIN`, `:849`). Eles
descrevem o leiaute da Galeria, do rodapé e da folha de estilo que o merge do religa largou, nunca
mais rodam, e contam como testes. O motivo `RODAPE_DO_MAIN` diz que a conferência de 1.024 px
continua sem medida.

**Solução.** Decisão D4 do roadmap: apagar, ou reescrever contra o leiaute atual. A conferência de
1.024 px vira item datado de qualquer jeito.

**Aceite.** Nenhum `@unittest.skip` incondicional em `tests/` (guarda por `grep`).

## S-869 · Guardas de importação que enxergam PyQt6

**Problema** (confirmado). Dezesseis guardas só conferem `assertNotIn("tkinter", imports)`, e o Tk
saiu: `tests/test_viewport.py:178`, `test_board_model.py:369`, `test_editor_model.py:278`,
`test_page_overlay.py:303`, `test_qt_fita.py:51`, `test_qt_painel_da_galeria.py:65`,
`test_qt_painel_de_estudo.py:91`, `test_qt_painel_de_revisao.py:60`, `test_qt_painel_do_pdf.py:70`,
`test_qt_paleta.py:60`, `test_qt_texto_cauda.py:47`, `test_texto_exportacao.py:152`,
`test_texto_paleta.py:92`, `test_texto_rico.py:355`, `test_ui_comandos.py:615` e
`test_ui_texto_cor.py:146`. A docstring de `SEM_TKINTER` (`tests/test_editor_model.py:433-486`) está
velha. É a memória "guarda de varredura fica vácua no corte".

**Solução.** As guardas de módulo puro conferem `{"PyQt6", "tkinter"}`, como
`tests/test_ui_barra_da_sala.py:385`; as de módulo `qt/` saem.

**Teste que falha primeiro.** Um `import PyQt6` acrescentado a um módulo puro: a guarda acusa.

**Aceite.** As guardas acusam o acréscimo.

## S-870 · Testes de texto da fonte trocados por testes de comportamento

**Problema** (confirmado). `tests/test_augment.py:114` passa se `"augment_version"` aparecer em
qualquer lugar de `Trainer.prepare`, comentário incluído; `:311-313` procura `torch.rand` e
`random.random()` como texto; `tests/test_labels.py:502` procura `"LabelStore"` em `label_origins`;
`tests/test_preprocess.py:173-175` confere a ordem da corrente pela posição de `self.config.X` no
texto.

**Solução.** Semente fixa e saída comparada (aumento); `labels.csv` lido por um remendo que conta a
passagem pelo `LabelStore`; a ordem da corrente conferida por uma imagem em que cada passo deixa
marca.

**Aceite.** Os quatro testes reprovam com a regra quebrada e com o comentário intacto.

## S-871 · Guardas de varredura com piso, e o registro de comandos como catraca

**Problema** (confirmado). `tests/test_cli_errors.py:145-154` faz glob de `cli/*.py` procurando
`"\ndef main("`; se o caminho mudar, o glob volta vazio e o teste passa. `tests/
test_board_detection.py:151-162` varre só três módulos e não vê `importacao_de_imagens.py:743`.
`tests/test_ui_comandos.py:363-554` faz `assertEqual` contra 140 nomes literais (memória "teste não
congela lista do catálogo"). E `tests/conftest.py`, `tests/test_docs.py:819-1005`: 7 testes pulam em
worktree (S-805).

**Solução.** Cada varredura afirma quantos candidatos achou (`assertGreater(len(achados), N)`) e varre
`src/` inteiro. O registro de comandos vira `assertLessEqual(divergem, REGISTRADOS)` com um
dicionário de razões por entrada.

**Aceite.** Mover a pasta varrida reprova as guardas; acrescentar um comando não reprova o registro.

## S-872 · Testes de "não levanta" que conferem o efeito, e tempo escalável

**Problema.** Testes que passariam com a função vazia (confirmado): `tests/test_qt_menu.py:203`,
`test_qt_dica.py:52`, `test_qt_painel_de_recorte.py:149`, `test_qt_tabuleiro_editavel.py:124`,
`test_qt_rodape.py:222`, `test_engine.py:267`, `test_page_results.py:321`. Limites de relógio que
podem oscilar sob cobertura ou carga (plausível): `test_qt_fila_de_livros.py:174` e
`test_qt_indice_da_base.py:98` (menos de 1,5 s depois de um `qWait(100)`), `test_games_index.py:610`,
`test_engine.py:152`, `test_alinhamento.py:96`, `test_tablebase.py:286`; e o `_esperar` de
`test_qt_fila_de_livros.py:116` volta calado no estouro.

**Solução.** Cada teste de "não levanta" confere o estado depois da chamada. Os limites multiplicados
por um fator de ambiente (`CVOFF_FATOR_DE_TEMPO`, padrão 1, 3 sob cobertura). `_esperar` reprova no
estouro.

**Aceite.** Trocar o corpo de cada função testada por `pass` reprova o seu teste; a suíte sob
cobertura passa sem oscilar em três rodadas.

## S-873 · Os sobreviventes do mutator nos seis módulos-piloto

**Problema.** A S-803 lista os mutantes que a suíte deixa viver em `fen_utils.py`, `splits.py`,
`decode.py`, `atomic_io.py`, `settings.py` e `ui/legality.py`.

**Solução.** Para cada sobrevivente: um teste que o mata, ou a remoção do código que ele mostra
morto, ou a declaração de mutante equivalente com a razão.

**Aceite.** O escore de cada módulo-piloto registrado em `docs/metrics/mutacao.json` acima de 90%, e
nenhum sobrevivente sem decisão escrita.
