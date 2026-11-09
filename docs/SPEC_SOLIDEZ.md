# Especificação da solidez — Fases 110 a 121 (S-800 a S-910)

Base: [ROADMAP_SOLIDEZ.md](ROADMAP_SOLIDEZ.md), que traz as medições de 2026-11-08, as seis premissas
atacadas, o glossário, a ordem das fases e as decisões do dono. Todo caminho abaixo é relativo a
`src/chess_diagram_ocr/`, salvo quando começa por `tests/`, `docs/`, `tools/`, `packaging/`, `.github/` ou é
um arquivo da raiz. As linhas citadas são de `origin/main` em `e8c9f64a`.

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
> | S-585 a S-598 | [ROADMAP_PDF_COM_PGN.md](ROADMAP_PDF_COM_PGN.md) |
> | S-599 | [PLANO_FAIXAS_REVERSAS.md](PLANO_FAIXAS_REVERSAS.md) |
> | S-601 a S-668 | [SPEC_MESA_DE_TEXTO.md](SPEC_MESA_DE_TEXTO.md) |
> | S-702, S-710 a S-712, S-715 a S-718, S-720 | [SPEC_TEXTO_PRECISO.md](SPEC_TEXTO_PRECISO.md) |
> | S-800 a S-910 | [SPEC_SOLIDEZ.md](SPEC_SOLIDEZ.md) |

Cada item traz o **problema** com a evidência, a **causa** quando ela é uma premissa ou não é óbvia, a
**solução** (a menor mudança, ou o redesenho entregue em pedaços), o **teste que falha primeiro** e o
**critério de aceite**. A prova de cada achado está marcada: *confirmado* quando foi reproduzido por script
ou lido sem ambiguidade, *plausível* quando o mecanismo está no código mas o caso não foi reproduzido.
Nenhum item está entregue; todos valem como plano até o commit que os fecha. Item que edita um módulo do
fecho de medição remede os quatro relatórios no próprio commit (roadmap §7), diga-o ou não.
## Fase 110 — Alavancas

## S-800 · Borda de exceção do processo, e o estado da sessão gravado antes da queda

**Problema** (confirmado). O `main` de `app_pyqt.py` (`:281-341`) não instala `sys.excepthook`, e nada em
`src/` instala. Em PyQt6, exceção que escapa de um slot é `qFatal`: o processo sai (0xC0000409, ou 127 sob
`offscreen`) sem uma linha de log. Sete métodos `eventFilter`, em seis módulos de `qt/`, não têm `try`
(`fita_do_texto`, `foco_a_vista` com dois, em `:127` e `:286`, `painel_de_texto`, `paleta`, `tabela`,
`vazio`). E `JanelaPrincipal._gravar_estado` (`qt/janela.py:889`) só roda no `closeEvent` (`:2251`), então a
queda perde também o histórico de PDFs, a página e o divisor.

**Causa.** Premissa 6 do roadmap: a defesa foi posta slot por slot (`qt/atalhos.py:298` e `qt/dica.py:153`
têm borda que loga; `qt/acessibilidade.py:220` engole a exceção em `debug`), e não na raiz.

**Solução.** `qt/plataforma.instalar_borda()`, chamada no `main` antes da `QApplication`: troca
`sys.excepthook` (e `threading.excepthook`) por `logger.critical(..., exc_info=...)` e, havendo janela, uma
frase no rodapé. Segundo pedaço: `_gravar_estado` também em `_abriu_livro` e na troca de página, adiado por
2 s e sempre concluído: a última troca dentro da janela de 2 s é a que se grava, e o `closeEvent` grava o
que estiver pendente.

**Teste que falha primeiro.** Subprocesso com `QT_QPA_PLATFORM=offscreen` que chama `instalar_borda()`,
agenda `QTimer.singleShot(0, levanta)` e sai do laço em seguida.

**Aceite.** O subprocesso sai com código 0 e o arquivo de log tem a linha `CRITICAL` com o traceback. Abrir
um livro, virar duas páginas e matar o processo deixa `state.json` com o livro e a página.

**Entregue** (2026-11-08): o arquivo é `janela.json` (`CAMINHO_DO_ESTADO`), e não `state.json`; o aceite
foi medido lendo o disco com a janela ainda aberta, sem matar processo. A frase do rodapé sai por sinal
(`Borda.frase`), então a exceção de thread também chega a ele pela linha de eventos. O `try/except` do `main`
saiu: a borda já leva ao log o que escapa dali. Os sete `eventFilter` sem `try` ficam cobertos pela borda, sem
embrulho um a um. O relógio não reagenda: a primeira virada agenda, e a gravação lê a última página.

## S-874 · Página que derruba o processo de trabalho nunca roda no processo da janela

**Problema** (confirmado por script). `processo_de_trabalho.py:122-137`: quando o processo filho morre, ele
é recriado; quando morre de novo, a chamada segue **em linha**, no processo da janela. O isolamento existe
para "um PDF que derruba o MuPDF", então uma página que derruba sempre derruba duas vezes e, na terceira,
mata a janela. E `_recriou` vale para a vida inteira do processo: uma segunda queda horas depois, noutra
página, vai direto para "em linha para sempre".

**Solução.** Duas quedas na mesma chamada levantam um erro com frase própria ("a página N derruba o leitor
de PDF"), que a tela mostra e a varredura registra e pula. `_recriou` volta a zero depois de cada chamada
bem-sucedida.

**Teste que falha primeiro.** `test_funcao_que_derruba_o_filho_nunca_roda_no_pai`, com uma função que faz
`os._exit` quando roda no filho e grava um arquivo quando roda no pai.

**Aceite.** O teste passa: o arquivo do pai nunca é criado e o erro tem a página.

**Entregue** (2026-11-08): o erro é `PaginaQueDerruba` (com `pagina`, o índice), e `_recriou` saiu: a
conta de quedas é da chamada, não do objeto. Nenhuma varredura de livro passa pelo processo de trabalho,
então não houve varredura a ensinar a pular; quem mostra a frase é a caixa de `_folha_falhou` do visor (a
rasterização é a primeira a tocar a página), e a detecção ao fundo a deixa no log, como já fazia com
qualquer falha dela. O pool que caiu é descartado só se ainda for o corrente, para a chamada de outra
thread não derrubar o filho que esta acabou de recriar.

## S-906 · O processo de trabalho tem prazo, e o fechamento o encerra

**Problema** (confirmado por leitura e por script). `processo_de_trabalho.py:133` espera
`pool.submit(...).result()` sem `timeout`, e o `closeEvent` da janela (`qt/janela.py:2226-2265`) nunca chama
`processo_de_trabalho().encerrar()`. Com uma função de 8 s rodando no filho e o `main` terminando aos 3 s, o
processo só saiu aos 10 s: o `atexit` do `concurrent.futures` espera o trabalho em curso. Uma página que
**pendura** o MuPDF (a S-874 trata da que derruba) deixa o processo vivo e sem janela no Gerenciador de
Tarefas, segurando a trava do caderno (plausível). Chamadores: `qt/janela.py:1380`, `qt/marcas.py:225`,
`qt/painel_do_dataset.py:453`. E o filho, criado por `spawn`, nunca chama `configure_logging`: todo aviso da
detecção que roda ali vai ao `lastResort`, que no `.exe` é `stderr = None`, e some.

**Solução.** `executar(..., prazo_s=...)` com `result(timeout=prazo_s)`; esgotado o prazo, os filhos do pool
são terminados e sobe `PaginaPendurada` com o número da página, que a tela diz e a varredura registra e
pula. O `closeEvent` chama `encerrar(matar=True)`. O `initializer=` do pool configura o log do filho para o
mesmo arquivo, por `QueueHandler`.

**Teste que falha primeiro.** `test_funcao_pendurada_no_filho_levanta_no_prazo_e_o_processo_sai` (prazo de 1
s, função que dorme 60 s, saída em menos de 5 s) e `test_aviso_logado_no_filho_chega_ao_arquivo`.

**Aceite.** Os dois passam.

**Entregue** (2026-11-08): `PRAZO_S` é 60 s e conta também o `spawn` da primeira chamada; `prazo_s=None`
é sem prazo. Além do pedido, `encerrar(matar=True)` deixa o processo de trabalho fechado: a chamada em
curso, que perde o filho e tentaria de novo pela S-874, recebe `ProcessoEncerrado` em vez de fazer nascer
outro filho que o `atexit` esperaria (`test_fechar_mata_o_filho_e_nao_cria_outro`). O filho herda os
níveis de logger postos no pai, e cada filho tem a sua fila: o morto no meio de um `put` não a passa ao
seguinte. A frase de `PaginaPendurada` chega à tela pelo mesmo caminho da S-874; varredura que passe pelo
processo de trabalho não há.

## S-801 · crapper no repositório, com catraca de CRAP por função

**Problema.** O método pede CRAP abaixo de 10 por função, e o projeto não tem como medir: nem `radon` nem
`coverage` estão nas dependências de desenvolvimento.

**Solução.** `radon` e `coverage` no extra `dev`. Um `tools/qualidade/crapper.py` (o da revisão, em que
`CRAP = cc² × (1 − cobertura)³ + cc`, com a cobertura por linha de cada função) que lê o JSON do `coverage`
e o do `radon`, e escreve `docs/metrics/crap.json` com as funções de CRAP ≥ 10. A catraca é um teste que
compara o arquivo novo com o registrado: nenhuma função **nova** entra acima de 30, e o número de funções
acima de 10 não sobe.

**Teste que falha primeiro.** Uma função sintética de complexidade 12 sem teste num diretório temporário: o
crapper a reporta com CRAP 12² + 12 = 156.

**Aceite.** `python tools/qualidade/crapper.py` roda em menos de 1 minuto sobre uma cobertura já gravada. A
catraca falha ao acrescentar a função sintética a `src/` e passa ao removê-la. O CI roda a cobertura numa
perna só, a 3.13.

**Entregue** (2026-11-08): o `crap.json` saiu da cobertura gravada na revisão (`coverage` 7.16.2, 11:55, com
o `src/` idêntico ao de `e8c9f64a`): 5.928 funções, 609 com CRAP ≥ 10 e 137 ≥ 30 (os 611 da revisão contavam
duas do `app_pyqt.py`, que fica fora). Roda em ~20 s. A catraca do repositório é um teste que só compara
quando há `coverage.json` (ou `CVOFF_COBERTURA`) e `radon`; sem eles pula, e os testes da fórmula e da
comparação rodam sobre dado sintético. No CI a perna 3.13 roda a suíte sob `coverage` e a catraca **avisa
sem reprovar** (`continue-on-error`): a base registrada é de outro ambiente (3.10, outros pulos), e o
`coverage.json` da perna sobe como artefato para regravá-la com `--gravar --forcar`. A função é
identificada por arquivo e nome qualificado, não por linha; o nome da closure de método é montado pelo
crapper, porque o `add_inner_blocks` do `radon` perde a classe.

## S-802 · dryer no repositório, com catraca de pares duplicados

**Problema** (confirmado). 65 pares de funções com semelhança ≥ 0,8 e 340 com ≥ 0,6. Exemplos com 1,00:
`cli/texto_grade.py:570` e `cli/texto_ordem.py:293` (`parse_args`), `text/colados.py:74` e
`text/duas_linhas.py:77` (`vale`), `text/modelo.py:365` e `text/onnx_glifos.py:229` (`classificar`),
`qt/painel_da_galeria.py:1510` e `qt/painel_de_estudo.py:1747` (confirmação).

**Solução.** `tools/qualidade/dryer.py`: tokeniza cada função com 60 tokens ou mais, troca nomes por `N`,
números por `0` e strings por `S` (palavras-chave ficam), e mede Jaccard sobre 5-gramas. A catraca guarda os
pares ≥ 0,8 em `docs/metrics/dryer.json`: par novo reprova, par que some baixa o teto. Um par pode ser
declarado "semelhante de propósito" com a razão escrita no próprio JSON.

**Teste que falha primeiro.** Duas funções iguais a menos dos nomes num diretório temporário: semelhança
1,00. Duas funções com o mesmo esqueleto e corpos diferentes: semelhança abaixo de 0,6.

**Aceite.** Rodada sobre `src/` em menos de 30 s. A catraca acusa uma cópia acrescentada.

**Entregue** (2026-11-08): 2.943 funções com 60+ tokens e **78** pares ≥ 0,8 (20 com 1,00), contra os 65 da
revisão: o protótipo tokenizava o trecho de cada função solto, e o `TokenError` do trecho indentado truncava
a sequência; aqui o arquivo é tokenizado inteiro e fatiado por linha. Par de função com a sua própria
aninhada não conta. Os candidatos saem por filtro de prefixo (exato para Jaccard), e a rodada leva ~8 s. A
f-string vale um `S` só, para que o 3.13 meça o mesmo que o 3.10 (conferido: os mesmos 78). O par é
identificado por arquivo e nome qualificado; par que some também reprova até `--gravar`, que é como o teto
desce, e par novo só entra no registro com `--gravar --aceitar "razão"`, que vai para o campo `proposito`.

## S-803 · mutator no repositório, com piloto em seis módulos puros

**Problema.** Não se sabe quanto do que a suíte cobre ela de fato verifica. `mutmut` não roda nativo no
Windows, que é onde o projeto vive.

**Solução.** `tools/qualidade/mutator.py`: por AST, uma mutação por vez (troca de comparação, aritmética,
`and`/`or`, `not` removido, inteiro + 1, booleano invertido, `return X` → `return None`, constante `str`
trocada por `""`), roda **os arquivos de teste que importam o módulo** (não só o homônimo: no piloto desta
revisão, os dois sobreviventes de `decode.py` conferidos à mão morreram noutros arquivos) e restaura o fonte
num `finally`. O piloto roda em `fen_utils.py`, `splits.py`, `decode.py`, `atomic_io.py`, `settings.py` e
`ui/legality.py`, e o escore de cada um fica em `docs/metrics/mutacao.json`. O piloto feito na revisão, só
com o arquivo homônimo e 50 mutantes amostrados, deu 68% em `splits.py`, 58% em `fen_utils.py` e 74% em
`decode.py`: é um piso. Não entra no CI de cada push: roda à mão, e o escore registrado só pode subir.

**Teste que falha primeiro.** Um módulo de brinquedo `soma(a, b): return a + b`, com um teste que só confere
`soma(0, 0) == 0`: a mutação `+` → `-` sobrevive. Com o teste `soma(2, 3) == 5`, ela morre.

**Aceite.** O fonte do módulo é byte a byte igual ao de antes, também depois de uma interrupção: o `finally`
restaura na saída normal e no Ctrl+C, e uma cópia `<modulo>.py.mutator-orig`, gravada antes da primeira
mutação, é restaurada na partida seguinte quando o processo morreu sem `finally` (um `taskkill /F`). O
mutator roda com `PYTHONDONTWRITEBYTECODE=1` e apaga o `__pycache__` do módulo a cada mutação: a troca `+` →
`-` não muda o tamanho do arquivo, e o `.pyc`, validado por mtime em segundos e tamanho, poderia deixar a
mutação viva depois da restauração. O relatório lista cada sobrevivente com linha e operador. A S-873 mata
os sobreviventes.

**Entregue** (2026-11-08), com o **piloto pela metade**: `mutacao.json` traz `decode.py` 74% (50 mutantes, só
`test_decode.py` o importa), `ui/legality.py` 60% (50, só `test_legality_panel.py`; 14 dos 20 sobreviventes
são mensagem trocada por `""`) e `settings.py` 76% (25 mutantes, 9 arquivos). Ficaram de fora `fen_utils.py`,
`splits.py` e `atomic_io.py`: a linha de base dos arquivos que os importam leva 136 s, 130 s e 218 s
(`test_app_pyqt`, `test_qt_*`, `test_training`), e com sobrevivente pagando a rodada inteira 50 mutantes
custam uma a duas horas por módulo. "Importa" é import direto (as quatro grafias), não o fecho
transitivo; o homônimo roda primeiro, e o `pytest -x` poupa o resto ao mutante que morre nele. O mutante é
o fonte inteiro reescrito por `ast.unparse` (some comentário, a restauração devolve os bytes). Conferido à
mão: um `taskkill /F /T` no meio deixou o mutante e a `.mutator-orig`, e a rodada seguinte restaurou; depois
das três rodadas reais o `git status` do `src/` ficou limpo. `--gravar` recusa escore menor (`--forcar`).

## S-804 · Catraca de tipos, e as contagens que só descem

**Problema** (confirmado). 192 `# type: ignore` (80 `arg-type`, 63 `attr-defined`), 892 `Any` e 170
`except Exception` em `src/` (176 com `app_pyqt.py`). O `[tool.mypy]` não tem `warn_unused_ignores`, então
um `ignore` que já não silencia nada fica para sempre. Três comentários do `pyproject.toml` (`:36`, `:226` e
o do `[tool.mypy]`, `:262`) ainda falam de `app_tkinter.py`, que não existe.

**Solução.** `warn_unused_ignores = true`, apagando os ignores que ele acusar. Um teste de catraca com as
três contagens por pacote (`qt/`, `text/`, `ui/`, `cli/`, raiz), que reprova se uma delas subir. Os três
comentários passam a falar de `app_pyqt.py`.

**Teste que falha primeiro.** Acrescentar um `except Exception: pass` em `src/`: a catraca reprova com o
nome do pacote.

**Aceite.** `mypy` verde com `warn_unused_ignores`. A catraca está verde em `main` e vermelha com o
acréscimo.

**Entregue** (2026-11-08): 24 ignores apagados, nenhum preso a versão -- a CI só roda o mypy na perna
3.10, no Windows e com o `uv.lock`, que é o ambiente do `.venv`. As contagens são lidas pela árvore e não
por `grep`, por isso diferem das do problema: 164 `type: ignore` (os que o mypy obedece), 833 usos de `Any`
(sem o `import`) e 175 `except Exception` (com tupla), em `docs/metrics/catraca_de_tipos.json` por
`tools/qualidade/catraca_de_tipos.py`. O `detection/` entra como pacote próprio. Contagem que desce
também reprova, dizendo o número novo, até o `--gravar`.

## S-805 · Infraestrutura de teste

**Problema.** Quatro furos, todos confirmados pela auditoria dos testes:

- os testes da aba Texto usam `_TarefaNaHora` (`tests/test_qt_texto_caderno.py:54`), que emite `pronto`
  dentro do `start`. Uma tarefa que termina antes de a tela mudar não pega nenhum defeito de "mudou durante
  a tarefa" (S-823, S-824);
- a guarda `sem_thread_vazada` (`tests/conftest.py:291`, `:326`) aceita threads `Dummy-N` e
  `ThreadPoolExecutor`. A `Tarefa` é um `QThread`, e um `QThread` não aparece em `threading.enumerate()`, ou
  aparece como `Dummy-N` depois de `current_thread()`: a guarda não o enxerga (confirmado por script);
- `dados_de_quem_roda_ficam_onde_estao` (`tests/conftest.py:158-237`) vigia `PROJECT_ROOT/data/`, que num
  worktree não tem o cache: a guarda fica vácua. É o caso da memória "guarda de caminho é vácua em
  worktree";
- `tests/qt_app.py:30` decide `TEM_PYQT` por `importlib.util.find_spec("PyQt6")`, e cerca de 206 classes
  pulam quando o pacote falta; o PyQt6 é dependência base (`pyproject.toml:43`). Um ambiente sem o pacote
  sai verde com pulos (com o pacote presente e a DLL quebrada não há pulo: há `ImportError`).

**Solução.** Uma `TarefaAdiada` em `tests/qt_app.py`, que só emite quando o teste manda. O registro `_VIVAS`
que `manter_viva` já mantém (`qt/trabalho.py:251`) passa a receber toda `Tarefa`, e a mesma fixture o
confere. A guarda de dados ancorada também no checkout principal, achado por
`git worktree list --porcelain`, como `_raizes_do_repositorio` (`tests/test_docs.py:275`, com o
`git worktree list` em `:293-300`) já faz; os 7 pulos de `tests/test_docs.py:819-1005` em worktree usam a
mesma âncora. Um teste que reprova, sem pular, quando o pacote PyQt6 não está instalado.

**Teste que falha primeiro.** Uma `Tarefa` deixada rodando num teste de mentira: a fixture tem de acusar.

**Aceite.** As três guardas acusam o caso sabotado e passam na suíte atual; a `TarefaAdiada` é usada pelos
testes das S-823, S-824 e S-894.

**Entregue** (2026-11-08): o registro não é o `_VIVAS`, e sim um `weakref.WeakSet` (`qt/trabalho._TODAS`,
lido por `tarefas_rodando()`): pôr a tarefa com pai no `_VIVAS` faria o `_soltar` destruí-la no `finished`,
e o painel que ainda a consulta acharia o C++ apagado. O `git worktree list` saiu de `tests/test_docs.py` para
`tests/arvores_do_repositorio.py` (`checkout_principal`, `raizes_do_repositorio`). Ancorados no principal, os
7 pulos rodaram e 3 reprovaram contra números velhos: README e ARCHITECTURE remedidos (58 PDFs, 20.758 PNGs,
17,1 GB). As ~206 classes continuam pulando sem o PyQt6; quem reprova é `PyQtAusenteReprovaTests`. A
`TarefaAdiada` já serve a `RenderizarAoFundoTests` da aba Texto.

**Entregue** (2026-11-09, conserto da guarda de dados): comparar `mtime` e listagem do `data/` do principal
acusava o programa do dono, aberto ao lado, gravando uma amostra a cada ~15 s, em testes que não gravaram
nada. A guarda agora pergunta se **este** processo escreveu: `tests/sonda_de_escrita.py` põe um
`sys.addaudithook` por sessão, que anota `open` de escrita, `os.remove`/`rename`/`mkdir`/`rmdir`/`utime`,
`shutil.rmtree` e `sqlite3.connect` fora de `mode=ro` sob `data/` e `pgn_database/` das três raízes, e
`dados_de_quem_roda_ficam_onde_estao` confere e limpa a lista a cada teste. Saíram o retrato dos caches e
a listagem de sessão (`nada_novo_no_data_de_verdade`) com a lista vazia `ESCRITA_LEGITIMA_EM_DATA`; o
`pgn_database/` passou a ser vigiado. Subprocesso e escrita feita em C não são vistos: o filho é protegido
pelo `CVOFF_DATA_DIR` desviado.

## Fase 111 — Caches e índices que não se apagam sozinhos

## S-807 · Uma impressão digital de base só, que enxerga membro de `.zip`

**Problema** (confirmado por script). `games_cache.database_fingerprint` (`games_cache.py:107`, corpo em
`:125-131`) dá tamanho 0 a todo membro de `.zip`: reescrever `z.zip/m.pgn` com 50 vezes o conteúdo não muda
a impressão. `games_index.index_fingerprint` (`games_index.py:363`) responde a mesma pergunta por
`nome_da_base` e `tamanho_da_base`, que tratam o zip (`games_db.py:316`, `:340`); mas `tamanho_da_base`
também devolve 0 em `OSError`, o mesmo defeito do `stat` da S-806 do lado do índice. A base é identificada
só por `caminho.name`, e dois zips com `games.pgn` dentro parecem a mesma base.

**Causa.** Premissa 3: a mesma decisão em dois módulos (a S-113 já tinha juntado metade dela).

**Solução.** `impressao_da_base(caminho) -> ImpressaoDaBase` (nome qualificado pelo zip, tamanho do membro,
ou "desconhecido" quando o tamanho não lê) num módulo só, usada por cache e índice.

**Teste que falha primeiro.** `test_impressao_de_membro_de_zip_muda_com_o_conteudo`, e
`test_dois_zips_com_mesmo_membro_sao_bases_diferentes`.

**Aceite.** Os dois passam. `database_fingerprint` e `index_fingerprint` delegam à mesma função.

## S-806 · `open_store` nunca esvazia o cache

**Problema** (confirmado por script). `games_cache.py:509-518`: quando a impressão digital gravada difere da
de agora, `open_store` chama `_esvazia`. Com 500 linhas feitas sobre `[a.pgn, b.pgn]`, abrir com
`database=[a.pgn]` deixa zero. Quem chega aqui sem querer:

- `cli/games.py:394`: `_census` diz "Não abre a base", e `cvoff-games --census --database X.pgn` apaga o
  cache do acervo inteiro;
- `cli/games.py:250`: `_bases()` tira em silêncio a base que não existe agora. Um disco fora do ar ou um
  arquivo no meio de uma cópia esvazia o cache no `--all` seguinte;
- `stat()` que falha vira tamanho 0 (`games_cache.py:125-130`), e a impressão "muda" (o "desconhecido" que
  conserta isto é o tipo da S-807, que vem antes);
- o painel de estudo (`qt/painel_de_estudo.py:2721`) e a Galeria abrem do mesmo jeito.

O cache é ~56 minutos de varredura, e é o incidente de 2026-10-18 (~9.810 linhas apagadas).

**Causa.** Premissa 1: "o conjunto parece diferente" é tratado como "o cache não vale", e "não vale" como
"apague".

**Solução.** Redesenho em três pedaços. (1) `open_store` nunca faz `DELETE`. (2) A tabela `positions` ganha
a coluna `impressao` e cada linha é respondida só sob a impressão com que foi feita; linha de impressão
antiga é ignorada na leitura, e uma limpeza explícita (`cvoff-games --limpar-cache`) é o único lugar que
apaga. (3) Leitores (`--census`, painel) abrem com `mode=ro` e sem `database=`; `stat` que falha vira
"desconhecido", que não casa nem descasa.

**Teste que falha primeiro.** `test_census_com_subconjunto_nao_apaga_o_cache`: encher com `[a, b]`, chamar
`cli.games.main(["--census", "--all", "--gallery-dir", g, "--cache", c, "--database", a])` com um
`*.index.json` falso em `g`, e conferir 500 linhas. Sem `--all` e sem um índice da Galeria, o comando sai
com `EXIT_BAD_INPUT` em `cli/games.py:486-492` antes de abrir o cache, e o teste passaria hoje.
`test_stat_falho_nao_esvazia`.

**Aceite.** Os dois testes passam. Nenhum `DELETE FROM positions` fora da limpeza explícita (guarda por
`grep`, com piso de um achado: a própria limpeza).

**Entregue** (2026-11-08): os leitores abrem com `somente_leitura=True` **e com** `database=` — sem as
bases não há impressão sob a qual perguntar —, e o censo usa as mesmas bases da varredura (`_bases`). A
chave é `(impressao, placement)`; o cache da versão 1 é migrado na primeira abertura para gravar (a marca
de `meta` vira a impressão de cada linha) e lido sem migrar por quem só lê (vista temporária).
`stored_summary` passou a devolver `(valem, guardadas)`. A Galeria segue abrindo para gravar, sem perigo:
não há mais `DELETE` na abertura. Os docstrings de `config.py` que ainda dizem "`open_store` esvazia" não
foram tocados (módulo do fecho de medição).

## S-808 · URI de SQLite por `Path.as_uri()`, e versão ilegível não apaga o índice

**Problema** (confirmado por script). `games_index.py:384` e `:997` montam `f"file:{path}?mode=ro"` sem
escapar o caminho; `games_cache.py:575` e `arvore_de_aberturas.py:718`, `:814` fazem o mesmo com
`as_posix()`. Numa pasta `Xadrez #2`, a versão gravada volta `None`; numa pasta `100%25 ok`, o SQLite nem
abre. Pior: com `#`, o `?mode=ro` vira fragmento, e o SQLite abre `.../Xadrez ` (com o espaço) **em leitura
e escrita**, criando um arquivo vazio na pasta-mãe. E `_abrir_para_escrita` (`games_index.py:416-421`) trata
o `None` como "outro formato" e faz `unlink` do índice, que é construído de 8,6 GB de PGN.

E caminho de rede também falha, hoje e com a correção ingênua (confirmado por script): por
`\\localhost\C$\...`, o `f"file:{p.as_posix()}?mode=ro"` atual dá "unable to open database file";
`p.resolve().as_uri()` gera `file://localhost/C%24/...` e falha igual; com `\\nas\...` o SQLite responde
"invalid uri authority". E `resolve()` transforma uma unidade mapeada (`Z:\`) em UNC, então quebraria quem
hoje funciona.

**Solução.** `uri_somente_leitura(caminho)` = `"file:" + quote("//" + caminho.as_posix()) + "?mode=ro"`
quando o caminho é UNC e `"file:" + quote(caminho.as_posix()) + "?mode=ro"` quando não é, sem `resolve()`;
num lugar, usada pelas cinco chamadas dos três módulos. A forma `file:////localhost/C%24/...?mode=ro` abriu,
e a escrita foi recusada. `_abrir_para_escrita` apaga só quando leu uma versão **e** ela é outra; versão que
não leu é erro, dito ao usuário.

**Teste que falha primeiro.** `test_indice_em_pasta_com_cerquilha_sobrevive_a_segunda_rodada`, o mesmo com
`%`, e `test_uri_somente_leitura_abre_unc` sobre `\\localhost\<unidade>$\...` (pulado onde o
compartilhamento administrativo não existe).

**Aceite.** Os dois passam. Nenhum `f"file:` sobra em `src/` (guarda por `grep` sem piso, porque o número
certo é zero).

**Entregue** (2026-11-08): `games_db.uri_somente_leitura`, usada pelas cinco aberturas (a do cache é agora
a porta de leitura da S-806). O `quote` também escapa o `:` da unidade (`file:C%3A/...`), e o SQLite o
abre. `_versao_gravada` distingue banco sem tabela nenhuma (não apaga, só cria as tabelas) de `meta` sem a
linha de versão (outra versão, apagado como antes); o que não lê levanta `IndiceIndisponivel`.

## S-809 · `--build-index` com subconjunto não apaga as outras bases

**Problema** (plausível). `games_index.py:652-660` apaga de `games` e `files` toda base que não está na
lista desta rodada. Com `--database X` explícito, ou com uma base que `_bases()` filtrou por estar ausente
naquele instante, horas de indexação se perdem.

**Solução.** Apagar só a base cujo arquivo não existe mais na pasta das bases, e só com `--podar`. Rodada
com subconjunto acrescenta e atualiza; não poda.

**Teste que falha primeiro.** Indexar `[a, b]`, rodar `--build-index --database a`, conferir que as partidas
de `b` continuam.

**Aceite.** O teste passa. `--podar` sem nenhuma base ausente não faz nada.

**Entregue** (2026-11-08): sem poda, o índice pode guardar mais bases do que a rodada leu, e a marca
`meta.database` passou a ser a do manifesto inteiro, comparada como conjunto — senão a consulta da pasta
inteira recusaria o índice depois de uma rodada parcial. A base que saiu da pasta sem `--podar` faz a
consulta recusar, e a frase diz `cvoff-games --build-index --podar`. O botão da janela
(`qt/indice_da_base.py`) poda sempre: é o que a recusa manda apertar, e sem podar ele não a resolveria.
"Pasta das bases" é `PGN_DATABASE_DIR` mais a pasta de cada base da rodada.

## Fase 112 — Arquivos do dono e a identidade do livro

## S-827 · A identidade do livro numa função só

**Problema** (confirmado por leitura). "Mesmo livro" é decidido em pelo menos sete lugares:
`ui/galeria_declarada.py:230` (`normcase`), `qt/painel_de_texto.py:4659` (`casefold`), `:4677`
(`resolve ==`, com `.lower()` na falha, `:4680`), `ui/state.py:341` (`_history_key`, só `resolve`),
`qt/janela.py:1224` (`anterior != alvo`), e `source_pdf ==` na fusão da fila de revisão
(`qt/painel_de_revisao.py:467`, `cli/review.py:115`, que a S-816 junta em `fundir_fila_retomada`). A mesma
comparação, para bases `.pgn`, está em `qt/dialogos.py:176` (`_mesmo`). Hoje concordam porque `resolve`
devolve a caixa do disco; num caminho de rede fora do ar cada um cai num atalho diferente.

**Solução.** `ui/livros.chave_do_livro(caminho) -> ChaveDoLivro`, pura, usada pelos sete, pelas S-815,
S-816, S-878 e S-823 e, para bases, pelo `_mesmo` dos diálogos. Por isso abre a Fase 112.

**Teste que falha primeiro.** Uma tabela de pares (`..`, barra invertida, caixa, caminho que não resolve)
contra a função única; os chamadores trocados por ela não podem mudar nenhum resultado da tabela.

**Aceite.** Nenhuma comparação de caminho de livro fora da função (guarda por `grep` dos padrões acima, com
piso zero).

**Entregue** (2026-11-08): `ui/livros.py` com `ChaveDoLivro` (congelada, `curta` = 8 hex do SHA-1, para as
S-815/S-878), `chave_do_livro` (`None` sem livro), `mesmo_livro` e `caminho_canonico` (`resolve`, e
`abspath` quando ele levanta). A guarda achou um oitavo lugar, `qt/livro_com_pgn.py` (`resolve() !=`), que
também passou à função; `importacao_de_imagens._chave_absoluta` fica isenta (é imagem, não livro). O
histórico de páginas continua gravando o caminho na caixa do disco (`recentes` o mostra e o abre) e acha a
entrada pela chave. Ficam de fora as três chaves gravadas em disco (`estudo.Ancora.chave`,
`estudo_arquivo.chave_de`, `text/rascunho.chave_de`): são impressões do caminho resolvido, e trocar a
entrada delas órfã estudos e rascunhos já gravados.

## S-812 · Leitura travada

**Problema** (confirmado). Seis leitores de arquivo do dono tratam o arquivo que não lê como vazio, e o
gravador seguinte escreve o vazio por cima:

- `settings.json` com uma vírgula sobrando vira padrão, e a próxima gravação das opções do motor escreve
  `endpoint: ''` (e `engine.path: ''`, se o diálogo não mudou o caminho) sobre o arquivo do usuário
  (`settings.py:533-569`);
- `revisao.json` de esquema 2 com 600 itens carrega com 0, e a gravação seguinte escreve esquema 1 com 0
  itens (`revisao_arquivo.py:43-68`);
- `placar.json`, o estudo da sala, a fila de revisão, o lote de importação (`Lote.carregar` devolve `None` e
  `abrir_lote` recomeça com tudo pendente). O sétimo leitor da premissa, o caderno do texto, entra pela
  S-896; o cache de posições, que a premissa cita à parte por não ser arquivo do dono (é refazível), é da
  S-806.

**Causa.** Premissa 1.

**Solução.** Um módulo `arquivo_do_dono.py` com o tipo `Leitura = Lida[T] | Ilegivel | EsquemaFuturo`.
`Ilegivel` e `EsquemaFuturo` copiam o arquivo para `<nome>.ilegivel-<data>` (D1 da solidez) e devolvem um
valor em memória marcado **travado**, que o gravador recusa com uma mensagem ao usuário. Os seis leitores
passam a devolver `Leitura`; os gravadores aceitam só `Lida`. Entregue em pedaços, um arquivo por commit,
começando pelo `settings.json`.

**Teste que falha primeiro.** Para cada um dos seis: arquivo corrompido, carregar, mexer, gravar; o arquivo
original tem de estar intacto e a cópia `.ilegivel` tem de existir.

**Aceite.** Os seis testes passam. Nenhum leitor de arquivo do dono devolve o padrão para arquivo ilegível
sem passar pelo `Ilegivel` (guarda por AST nos seis módulos, com piso de seis).

**Entregue** (2026-11-08): num commit só, e não um por arquivo. A cópia é
`<nome>.ilegivel-<AAAA-MM-DD><extensão>` (a extensão no fim, a forma que a S-896 pede), e reabrir no mesmo
dia não a multiplica. `ConteudoIlegivel(parcial=...)` é a porta da leitura parcial da S-814 e da S-896. A
sala passou a decodificar UTF-8 estrito: o `errors="replace"` regravava o byte como U+FFFD, e agora trava
(a S-905 dá o cp1252). A fila e o lote de versão **mais velha** também travam, porque não há migração.
`Placar.origem` saiu: o caminho mora na `Lida`, e a janela de treino grava por `gravar_placar`, que a sala
lhe passa. `ReviewQueue.load/save` e `Lote.carregar/salvar` viraram `carregar_fila`/`gravar_fila` e
`carregar_lote`/`gravar_lote`. O `cvoff-review` recusa antes de varrer; o `cvoff-scan` grava o índice e
põe a recusa da fila no relatório. As opções do motor da sala passaram a gravar sobre a camada de arquivo, e
por isso já não levam o ambiente ao disco; o diálogo de configurações segue com o defeito até a S-811.

## S-905 · Arquivo do usuário em BOM, ANSI ou UTF-16 abre, e `UnicodeDecodeError` não escapa

**Problema** (confirmado por script). Nenhuma leitura de texto de `src/` está sem `encoding` (84 com
`"utf-8"`, 3 com `"utf-8-sig"`); o defeito é o contrário: UTF-8 **estrito** em arquivo que a pessoa edita ou
escolhe. O README manda editar `data/settings.json` à mão, e `load_settings` (`settings.py:545`, `:550`),
com o mesmo JSON, devolve o caminho `C:\Users\José\stockfish.exe` em UTF-8, devolve os padrões em UTF-8 com
BOM (só com um aviso no log, e o próximo Salvar do diálogo, `qt/dialogo_de_configuracoes.py:250`, apaga o
que a pessoa escreveu), e **levanta** `UnicodeDecodeError` em cp1252 ou no UTF-16 que o `>` do PowerShell
5.1 escreve: isso acontece no `__init__` da janela (`qt/janela.py:283`), e o `.exe` sem console não abre. A
causa é que `UnicodeDecodeError` é `ValueError` e não `JSONDecodeError`: 17 `except` nomeiam
`json.JSONDecodeError` sem `ValueError`, e 13 leituras ficam num `try` que só cobre `OSError` e
`JSONDecodeError`. Outros casos: "Abrir texto de folha" (`text/arquivo.py:107`,
`qt/painel_de_texto.py:2037`) oferece `Todos (*.*)`, e um PDF escolhido ali levanta `UnicodeDecodeError`,
que não é `ArquivoInvalido` e sai do slot; e o parcial da exportação (`export_checkpoint.py:351`, gravado em
`"a"` com `ensure_ascii=False`) cortado no meio de um acento faz a retomada recomeçar do zero, porque o
arquivo inteiro é decodificado antes do laço que descarta a linha rasgada (`:376-389`). O mesmo padrão em
`gallery.py:394`, `:509`, `:582`, `gallery_scan.py:219` e `games_cache.py:640`.

**Causa.** A tolerância prometida ("arquivo corrompido cai no padrão") falha justamente para a corrupção
mais comum no Windows.

**Solução.** `atomic_io.ler_texto(caminho, *, do_usuario: bool) -> str`, num lugar: lê bytes, tira o BOM,
decodifica UTF-16 quando o BOM é de UTF-16, e, para arquivo do usuário, cai em cp1252 quando o UTF-8 falha;
para arquivo do programa, decodifica linha a linha com `errors="replace"`. Falha que sobra vira
`ArquivoIlegivel(ValueError)`, que entra na leitura travada da S-812. Os 17 `except` passam a
`(OSError, ValueError)`. Guarda por AST: nenhum `except` com `JSONDecodeError` sem `ValueError`, e nenhum
`read_text(encoding="utf-8")` de arquivo do dono fora de `ler_texto`.

**Teste que falha primeiro.** `test_settings_em_cp1252_abre_com_o_caminho_acentuado`,
`test_settings_com_bom_le_os_valores`, `test_abrir_documento_que_nao_e_utf8_mostra_erro_e_nao_levanta` e
`test_parcial_rasgado_no_meio_de_um_acento_retoma_da_pagina_anterior`.

**Aceite.** Os quatro passam, e a guarda por AST passa com piso zero. `settings` está no fecho de medição (o
`export_checkpoint` não): o commit que o toca remede.

**Entregue** (2026-11-09): `ler_texto` e `ArquivoIlegivel` moram em `arquivo_do_dono.py`, e não em
`atomic_io`: `ler` já era a borda dos arquivos do dono e passou a chamá-la como arquivo do usuário, para os
sete leitores de uma vez -- `settings.py` não mudou, e a sala em ANSI abre, como a S-812 deixou anotado. O
arquivo do programa decodifica com `errors="replace"` o arquivo inteiro, que estraga só o byte rasgado (o
mesmo que linha a linha), e nunca levanta; o do usuário cai em cp1252 por arquivo, e não por linha como a
base PGN da S-531. Eram 19 `except`, e não 17. A guarda não reconhece "arquivo do dono" pela AST; o que ela
procura é leitura de texto no corpo de um `try` -- quem a põe lá promete tolerância --, com dez exceções
nomeadas por módulo e função, cada uma com a razão (código-fonte, `/proc`, a trava, metadado de modelo, o
dataset de marcas que já recusa alto). Dezoito leituras passaram por `ler_texto`; as decisões de conflito e
o `lexico.txt` do caderno como do usuário. Fica de fora o arquivo misto: UTF-8 com um byte ANSI no meio lê
inteiro como cp1252.

## S-810 · Booleano estrito e faixas numéricas no `settings.json`

**Problema** (confirmado por script).
`RemoteFenSettings.from_dict({"enabled": "false", "endpoint": "http://x"}).is_usable` é `True`, porque
`bool("false")` é verdadeiro (sem endpoint, `is_usable` é falso por outra razão, `settings.py:91`). E o
próprio módulo promete que um JSON ruim não liga envio. Hoje nada envia (S-882), e o envio ligaria no dia em
que o recurso voltar. `timeout` aceita `nan` e `-5`; `threads` aceita `-3`. O mesmo `bool(` está em
`OcrSettings` (`:311`) e em `LocalReaderSettings` (`:357`).

**Solução.** `_booleano(valor)`: só `true` e `false` do JSON; qualquer outra coisa é **desligado**, com
aviso. Faixas declaradas por campo (timeout em `(0, 600]`, threads em `[1, núcleos]`), com o valor fora da
faixa trocado pelo padrão e avisado. A faixa é aplicada na camada efetiva (S-811), para não regravar o
`settings.json` de outra máquina com o número de núcleos desta. O par `_inteiro`/`_flutuante`
(`settings.py:139`, `:162`, idênticos para o dryer) vira um só `_numero(tipo, faixa)`.

**Teste que falha primeiro.** `test_enabled_string_false_e_desligado`, com endpoint preenchido;
`test_timeout_nan_volta_ao_padrao`.

**Aceite.** Os dois passam. Nenhum `bool(` sobre valor do JSON em `settings.py`.

**Entregue** (2026-11-08): `_numero(data, chave, padrao)` tira o tipo do padrão, e a faixa é outra
decisão: `faixas()` (função, porque o teto de `threads` é desta máquina), aplicada por `_nas_faixas` no
`load_settings`, depois do ambiente; a S-811 a leva para `aplicar_ambiente`. `NaN` e infinito são recusados
já na leitura, em todo campo numérico, e não só no `timeout`. Os grampos que já existiam em `training` e
`recognition` (`max(1, ...)`, `dpi` em [72, 600]) ficaram onde estavam. A guarda do aceite é por AST.

## S-811 · Camada de arquivo e camada efetiva

**Problema** (confirmado por script). `settings.py:533-569`: carregar aplica as variáveis `CVOFF_*` sobre o
que leu, e salvar grava o resultado. Com `remote_fen.enabled=true` no arquivo e `CVOFF_REMOTE_FEN_ENABLED=0`
no ambiente, uma gravação de outra opção deixa o arquivo com `false` para sempre. No sentido contrário,
`CVOFF_REMOTE_FEN_URL` vai para o arquivo junto de `enabled=true`: um consentimento de privacidade que
ninguém deu (latente enquanto nada envia, S-882). `CVOFF_OCR_ENGINE`, `CVOFF_OCR_GLYPH_MODEL` e
`CVOFF_LOCAL_READER_PATH` também ligam `enabled=True` e vazam para o arquivo do mesmo jeito
(`settings.py:490-515`). Seções e chaves desconhecidas somem na gravação, e `SETTINGS_VERSION` nunca é
conferido na leitura. Quem grava: `qt/painel_de_estudo.py:2405-2407` e
`qt/dialogo_de_configuracoes.py:246-250`.

**Solução.** Dois valores com tipos diferentes: `ConfiguracaoDoArquivo` (o que leu, com as chaves
desconhecidas guardadas à parte) e `Configuracao` (efetiva, derivada por
`aplicar_ambiente(arquivo, os.environ)`). Só a primeira tem `gravar`. A versão do arquivo é conferida:
versão futura entra pela S-812.

**Teste que falha primeiro.** `test_salvar_nao_grava_o_ambiente`, nos dois sentidos;
`test_chave_desconhecida_sobrevive_a_gravacao`.

**Aceite.** Os testes passam. O tipo efetivo não tem método de gravação (mypy acusa a tentativa).

**Entregue** (2026-11-08): `Configuracao` é o próprio `Settings` (um nome, para os 30 leitores não mudarem), e
`ConfiguracaoDoArquivo` o embrulha com as `desconhecidas`. A gravação é `save_settings(Lida[ConfiguracaoDoArquivo])`,
uma função e não um método, para a trava da S-812 valer nela; o teste roda o mypy num trecho que tenta gravar a
efetiva, com o caso certo ao lado. `aplicar_ambiente` leva também as faixas da S-810. O diálogo de configurações
passou a mostrar e editar a camada de arquivo; as opções do motor da sala já gravavam sobre ela desde a S-812.
Uma seção conhecida que no arquivo não é objeto (`"engine": [1, 2]`) não é guardada: vira os padrões, como antes.

## S-813 · Baralho de revisão e placar sob a leitura travada

**Problema** (confirmado por script). Além da premissa da S-812: `"esquema": "1.0"` levanta `ValueError`
fora do `try` em `revisao_arquivo.py`; `certos: "x"` derruba `placar.py:120-128`, `:195-217`, porque
`de_json` não converte campo a campo. O módulo diz que o baralho é "o único dado deste programa que não se
refaz varrendo o livro de novo" (`revisao_arquivo.py:48`).

**Solução.** O `esquema` dos dois arquivos (também `placar.py:208`) lido pelo `_numero` da S-810. O baralho
já lê cada item no seu `try` (`:63-68`), mas descarta o ruim: passa a guardá-lo cru e a devolvê-lo igual na
gravação. O placar ganha o mesmo.

**Teste que falha primeiro.** `test_baralho_de_esquema_futuro_nao_e_sobrescrito`;
`test_placar_com_campo_ruim_nao_derruba`.

**Aceite.** Os dois passam. Um placar com um item ruim entre dez bons carrega os dez e grava os onze.

**Entregue** (2026-11-08): a S-812 já tinha posto o `ValueError` do `"1.0"` dentro do `try`, mas ele
travava o arquivo como ilegível. O esquema não é lido pelo `_numero` da S-810, que devolve o padrão para
o que não é número e leria um `"2.0"` como esquema 1: `arquivo_do_dono.conferir_esquema` o lê como
número, e `"2.0"` ou `1.5` são esquema futuro. Os dois arquivos têm o mesmo formato, e o formato passou a
morar em `arquivo_do_dono` (`ler_lista`, `gravar_lista`), o que tirou também o par `gravar` do dryer. O
item cru inclui a chave vazia ou repetida, não só o que levanta. O baralho em memória virou
`BaralhoDoArquivo(estados, crus)`, como o `ConfiguracaoDoArquivo` da S-811; o placar ganhou `crus`.

## S-814 · Sala de estudo: partida que não lê sobrevive à gravação

**Problema** (plausível). `estudo_arquivo.py:150-168`, `:184-202` e `estudo.py:505-512`, `:679-692`: partida
com `Page` ou `Diagram` ruim vira âncora inválida, e `guardar` a descarta com log de depuração; um
`read_game` que levanta faz `break` e derruba **todas** as seguintes, apesar da docstring; `OSError` na
leitura dá uma `Sala` vazia. A próxima edição marca a sala como suja, e `gravar` reescreve o arquivo com a
sala parcial, ou faz `unlink` se ela estiver vazia.

Há uma perda que não depende de exceção: o `read_game` do python-chess quase nunca levanta, e manda o lance
ilegal para `game.errors`. `estudos_de_pgn` não confere `errors` (só `estudo.py:617`, no colar, confere),
então uma partida com um lance ilegal é **truncada** em silêncio e regravada cortada.

**Solução.** `continue` no lugar do `break`; a partida que não lê, ou que tem `errors`, é guardada como
texto PGN cru e devolvida igual na gravação. Sala de leitura incompleta é leitura travada (S-812).

**Teste que falha primeiro.** `test_estudo_sem_ancora_sobrevive_a_gravacao`;
`test_lance_ilegal_nao_trunca_a_partida_na_regravacao`; e, com o `read_game` remendado para levantar na
segunda de cinco partidas, quatro carregadas e cinco gravadas.

**Aceite.** Os três passam; o arquivo regravado tem a partida quebrada byte a byte igual.

**Entregue** (2026-11-08): a S-812 já cobria o `OSError` e o arquivo que não decodifica (leitura travada,
sem `unlink`); faltava a partida ilegível dentro de um arquivo que lê. O cru mora em `Sala.crus` e volta
depois dos estudos, sem os brancos das pontas. O trecho de cada partida sai da posição do fluxo
(`pgn_do_livro.FluxoTolerante.posicao`, que conta também as linhas em branco que ele junta), e não de um
corte do texto por conta própria. Vai cru também o estudo de âncora repetida (antes o segundo apagava o
primeiro) e a partida sem conteúdo. "Leitura incompleta" ficou sendo o `read_game` que levanta sem
consumir nada: seguir seria um laço sem fim, e a sala trava com o que leu (`ConteudoIlegivel(parcial=...)`)
-- teste `test_leitura_que_nao_avanca_trava_a_sala`; antes, essa sala voltava vazia e a gravação apagava
o arquivo. O `estudos_de_pgn` do «Abrir um .pgn…» segue sem conferir `errors`: ali o arquivo é de fora e
não é regravado.

## S-815 · Fila de revisão: FEN corrigida sobrevive ao revarrer

**Problema** (confirmado por leitura). `review_queue.py:627-664`: `merge_queues` preserva só o `status`. A
FEN que o usuário corrigiu por `update_fen` volta a ser a leitura do OCR, e o item fica "feito".
`_safe_name` (`:393-407`) nomeia a pasta de miniaturas só pelo nome do arquivo, sem a pasta, e dois PDFs com
o mesmo nome sobrescrevem as miniaturas um do outro (o acervo tem livros duplicados). `ReviewQueue.load`
falha inteiro por um campo não numérico.

**Solução.** Item feito preserva a FEN. A pasta de miniaturas leva `nome + hash curto da ChaveDoLivro`
(S-827), com migração da pasta antiga quando ela é inequívoca. Cada item lido no seu `try`.

**Teste que falha primeiro.** `test_revarrer_preserva_fen_corrigida`;
`test_dois_pdfs_de_mesmo_nome_nao_dividem_miniaturas`.

**Aceite.** Os dois passam.

**Entregue** (2026-11-08): o item feito preserva a FEN **e o lado a jogar**, que o editor grava junto;
o pulado segue a leitura nova. A pasta é `nome_do_livro` (`<nome>-<ChaveDoLivro.curta>`), e
`cache_board_image` passou a receber o caminho do livro, não o nome. **A migração da pasta antiga não foi
feita**: a fila e o índice da Galeria guardam o caminho absoluto de cada miniatura, e mover a pasta os
deixaria apontando para o vazio; a antiga fica onde está, lida por esses caminhos, e a próxima varredura
grava na nova. O item que não lê não é pulado em silêncio: os outros chegam à tela pela
`ConteudoIlegivel(parcial=...)` da S-812, e a fila trava, porque gravar o parcial apagaria o item ruim.

## S-816 · `cvoff-scan` retomado preserva as pendências

**Problema** (confirmado por leitura). `cli/scan.py:191-195` chama
`merge_queues(ReviewQueue.load(destino), fila)` sem `pages=`. Como a varredura retomada só passa pelas
páginas depois de `last_page_done` (`gallery_scan.py:277-280`), os itens das páginas anteriores somem. A
janela passa `pages` (`qt/painel_de_revisao.py:471`, a S-119). O CLI também não confere `source_pdf`, que
`cli/review.py` e o painel conferem, e `_queue_path` (`:139`) usa só o nome do arquivo. E há um terceiro
chamador com o mesmo defeito: `cli/review.py:117` faz `merge_queues(existing, queue)` sem `pages=`, e um
`--merge` com `--start-page`, `--end-page` ou `--limit` apaga as pendências de fora do intervalo.

**Causa.** Premissa 3: a regra de fusão está no chamador, e foi consertada num chamador só.

**Solução.** `fundir_fila_retomada(anterior, nova, paginas_vistas, fonte)` pura em `review_queue.py`, que
confere a fonte e preserva o que está fora das páginas vistas. A janela e os dois CLIs a chamam. O nome da
fila ganha o mesmo hash da S-815, e a conferência da fonte usa a `ChaveDoLivro` (S-827).

**Teste que falha primeiro.** `test_scan_retomado_preserva_pendencias_das_primeiras_paginas`.

**Aceite.** O teste passa nos três chamadores (o mesmo caso, parametrizado).

**Entregue** (2026-11-08): `fundir_fila_retomada(anterior, nova, *, paginas_vistas)` substitui o
`merge_queues`, sem o parâmetro `fonte`: a fonte da passada é `nova.source_pdf`, e um segundo argumento só
teria como divergir dela. `paginas_vistas` é obrigatório, e quem monta a fila o carrega:
`ReviewQueue.paginas_vistas` (não gravado) são as páginas visitadas **menos as que o `limit` cortou** --
sem isso o `--limit` do `cvoff-review` apagava a pendência da página visitada que ficou fora do corte, e
por isso a fusão também confere a chave (página, diagrama). A fila do `cvoff-scan` passou a
`<nome>-<hash>.json`; a gravada como `<nome>.json` é renomeada quando leu e diz que é deste livro, e fica
onde está nos outros casos. O `return 1` do `cvoff-review` sobre fila travada virou `EXIT_FAILURE`, que a
guarda do código de saída cobrava.

## S-817 · Quarentena de rótulos em conflito sempre desfazível

**Problema** (confirmado). `text/conflitos.py:242-299`, chamado por `cli/texto_conflitos.py:236`: o
manifesto guarda caminhos relativos ao `PROJECT_ROOT`, e `desfazer` os resolve contra a pasta **atual**.
Rodado de outra pasta, ele pula todos os arquivos, diz "0 recortes voltaram" e sai com 0. O manifesto só é
escrito depois de todos os movimentos, então uma queda no meio deixa arquivos na quarentena sem caminho de
volta, contra a promessa "**Nada é apagado.**" (`text/conflitos.py:31`). A docstring de `aplicar` defende de
propósito mover primeiro e gravar o manifesto depois, para o manifesto nunca descrever um movimento que não
aconteceu.

**Solução.** Caminhos absolutos no manifesto. O manifesto é escrito antes de mover, com cada entrada em
estado `pendente`, e cada movimento o atualiza para `movido` (por `atomic_io`): ele descreve a intenção e o
que já aconteceu, e nunca diz `movido` do que não saiu, que é o que a docstring protegia. `desfazer` devolve
só o que está `movido` e já tolera o arquivo que falta. E o plano não move nada de um grupo cujo `vencedor`,
digitado no `texto_conflitos.json`, não é chave de `conflito.arquivos` (`text/conflitos.py:226-229`): hoje
todas as pastas viram perdedoras, contadas como "rótulo errado"; o grupo vai para `plano.divergentes`.
Desfazer zero de N sai com código diferente de 0.

**Teste que falha primeiro.** `test_desfazer_de_outra_pasta_devolve_tudo`;
`test_queda_no_meio_da_quarentena_e_desfazivel`; `test_vencedor_inexistente_e_divergente`.

**Aceite.** Os três passam.

**Entregue** (2026-11-08): `desfazer` devolve também o `pendente` que já está na quarentena e falta na base, que é a queda entre o movimento e a regravação do manifesto; o `pendente` que nunca saiu fica, e nada é gravado por cima de recorte que já está na base. Ele devolve uma `Volta` (voltaram, já estavam, faltam), e o código de saída diferente de 0 (`EXIT_BAD_INPUT`) vale quando algum `movido` não está nem na quarentena nem na base, o que inclui o zero de N e não acusa o `desfazer` repetido. O manifesto antigo, com caminho relativo e sem `estado`, é lido contra o `PROJECT_ROOT`, não contra a pasta atual. A chave `movidos` ficou, agora com `estado` em cada entrada. A leitura travada da S-812 não entrou: o manifesto é mapa de operação, não arquivo do dono.

## S-878 · Lote e Galeria não confundem dois livros de mesmo nome

**Problema** (confirmado por script). `batch.py:300-303`, `pdf_to_pgn.py:1234-1235`, `gallery.py:366`,
`gallery_scan.py:203-205` identificam o livro pelo nome do arquivo sem a pasta e sem a extensão. Com
`a/Livro.pdf`, `b/Livro.pdf`, `a/Outro.pdf` e `a/Outro.djvu`, o lote diz `b/Livro.pdf pulado` e
`a/Outro.pdf pulado`, e o `Livro.pgn` tem a saída de `a/Livro.pdf`; com `skip_existing=False`, o segundo
sobrescreve o primeiro. Na Galeria, o trabalho humano de um livro (anotações, partidas escolhidas) cai no
outro. O acervo tem livros duplicados e versões em PDF e DjVu.

**Solução.** O lote detecta nomes repetidos antes de varrer e sufixa a saída com o hash curto da
`ChaveDoLivro` (o mesmo da S-815). A Galeria grava o caminho de origem no JSON e recusa abrir um índice cujo
caminho não bate, dizendo qual é.

**Teste que falha primeiro.** `test_dois_livros_de_mesmo_nome_geram_dois_pgn`;
`test_galeria_de_outro_livro_de_mesmo_nome_e_recusada`.

**Aceite.** Os dois passam.

**Entregue** (2026-11-08): no lote, os **dois** livros de mesmo `stem` levam o sufixo (o nome não
depende da ordem da fila; o `Livro.pgn` antigo fica intocado), e o `.qualidade.json` segue o mesmo
nome; o livro de nome único continua com o nome de sempre. Na Galeria a recusa vale para as
anotações **e** para o índice, na leitura e na gravação (`gallery.conferir_dono`); passam o arquivo
sem `source_pdf` (os do dono), o dono relativo lido contra a raiz (`PDF\Livro.pdf`) e o dono que não
existe mais (livro movido). A exportação de PGN segue sem as anotações do outro livro, em vez de
falhar. Ficaram fora: `default_pgn_output_path` da exportação avulsa (um livro só, sem colisão a
detectar) e as miniaturas e a fila por nome, que são da S-815 e da S-816.

## S-892 · "Aplicar aos vizinhos" não troca a partida que a pessoa escolheu

**Problema** (confirmado por script). `ui/gallery_model.py:767-809` e `qt/dialogos.py:790-806`: com
Havasi–Tartakower escolhida no diagrama 2, aplicar Karpov aos vizinhos a partir do diagrama 1 troca a
partida do diagrama 2 (White, Black, Date e o lance 31), e a contagem devolvida é 1. `neighbours_with_game`
confere se a partida está entre as candidatas do vizinho, mas não se o vizinho já tem outra escolhida; a
pergunta do diálogo não diz isso, e não há desfazer. É escolha humana apagada, a mesma perda que a S-76
citou como motivo da trava.

**Solução.** `neighbours_with_game` exclui o vizinho com `annotation.chosen_game not in (None, hit.key)`, e
a pergunta lista à parte quantos vizinhos foram poupados por já terem outra partida.

**Teste que falha primeiro.** `test_vizinho_com_outra_partida_escolhida_nao_e_tocado`.

**Aceite.** O teste passa.

**Entregue** (2026-11-08): sem escolha, `chosen_game` vale `""` e não `None`, e por isso o critério é
`chosen_game in ("", hit.key)`; com `None` o conserto pouparia todos os vizinhos. Os poupados saem de
`neighbours_keeping_their_game`, e a mesma varredura decide as duas listas. A dica do botão dizia que ele
ficava cinza quando os vizinhos "não têm partida escolhida"; agora diz o critério de verdade.

## S-896 · Folha do caderno que não abre não é relida por cima

**Problema** (confirmado por script). `text/caderno.py:380-387`: `_carregar` devolve `None` para uma folha
gravada por versão futura (`versao: 99`) ou corrompida, só com um `logger.warning`. A aba
(`qt/painel_de_texto.py:2330-2335`) entende "não há folha no caderno" e relê com o motor; `guardar_leitura`
(`:476-494`) grava a leitura nova por cima, e o índice passa a `lida` com `correcoes=0`. A correção
sobrevive só no `.anterior`, que a visita seguinte sobrescreve. Uma folha `editada` com 12 correções termina
sem nenhuma, sem aviso, e sai de `corrigidas()`, então nem vai para a suíte. E a volta da suíte
(`text/caderno_na_suite.py:299-302`) sobrescreve o `.anterior` da folha corrigida nos dois lados, enquanto
um `int(dados["page_index"])` sem tratamento (`:294`) aborta a importação no meio, com as folhas anteriores
já gravadas (plausível).

**Causa.** Premissa 1: "ausente" e "ilegível" são o mesmo `None`. A S-848 trata só do `TypeError` que
escapa.

**Solução.** O caderno passa pela leitura travada da S-812: folha ilegível é copiada para
`folha-NNNN.ilegivel-<data>.cvtxt` antes de qualquer gravação, o índice não é tocado, e a aba diz no rodapé
que a folha não abriu. A volta da suíte grava a versão dela em `.suite.cvtxt` e valida todas as folhas antes
de gravar a primeira.

**Teste que falha primeiro.** `test_folha_ilegivel_nao_perde_estado_nem_conteudo`;
`test_volta_da_suite_com_folha_ruim_nao_grava_nenhuma`.

**Aceite.** Os dois passam.

**Entregue** (2026-11-08): `Caderno.trava(pagina)` diz por que a folha não abre, e `gravar` e
`guardar_leitura` devolvem `TRAVADA` sem tocar na folha nem no índice. A aba nem chama o motor sobre a
folha que não abre (ler ou virar a página para ela só avisa no rodapé), e a folha da tela que esbarra na
trava vai ao rascunho. Além da spec: `trazer_rascunho` levanta `GravacaoRecusada` sobre ela, porque o
`False` fazia a aba apagar o rascunho, talvez a única cópia legível. `guardar_anterior` virou
`guardar_da_suite`, e a versão da suíte, que «Voltar à versão anterior» já não alcança, ganhou no menu da
folha «Abrir a versão da Revisão de texto». A lista ruim da suíte volta como `Volta(invalida=...)`, e
não como exceção, porque quem a aplica é um slot do Qt.

## S-897 · O caderno acha o seu livro e a sua trava

**Problema** (confirmado por leitura). `text/caderno.py:158-168`: a identidade do livro é o hash do primeiro
MiB, e o cabeçalho (`:23-30`) promete que gravação incremental a mantém. Num PDF menor que 1 MiB o primeiro
MiB é o arquivo inteiro: uma anotação muda o hash e o caderno fica órfão (abre vazio). E `:526-554`
(plausível): depois de uma queda o `caderno.lock` fica, o Windows reaproveita o PID logo, `_processo_vivo`
vê outro programa vivo, e o caderno abre só para leitura dizendo que é "Outra janela do programa".

**Solução.** `_pasta_do_livro`, quando nenhuma pasta tem a identidade, procura o índice cujos `apelidos` (já
gravados) contenham o caminho. A trava grava o PID e a hora de criação do processo, e compara os dois.

**Teste que falha primeiro.** `test_pdf_pequeno_anotado_acha_o_mesmo_caderno`; um PID vivo com hora de
criação diferente retoma a trava.

**Aceite.** Os dois passam.

**Entregue** (2026-11-08): o apelido é comparado por `ui.livros.mesmo_livro` (S-827), e entre dois cadernos com o mesmo apelido vence o de índice gravado por último. A trava grava o PID e, na segunda linha, a hora de nascimento do processo (`GetProcessTimes`; no Linux, `/proc`); a trava antiga, só com o PID, usa a hora do arquivo como limite -- quem a escreveu já existia --, o que retoma também as travas vencidas que já estão no disco. A regra é uma só: o vivo com aquele PID que nasceu depois do limite é outro programa. O teste da hora diferente passava no código antigo por outro motivo (a trava de duas linhas era ilegível e retomada); quem falhou antes foram o da mesma hora, que segura a trava, e o da trava antiga mais velha que o processo.

## S-908 · Hora gravada com fuso, e o rascunho mais novo não é apagado

**Problema** (plausível; o mecanismo foi lido sem ambiguidade). `text/caderno.py:519` compara strings ISO
sem fuso: `gravada_em` (`datetime.now()`, `:456`) contra o `mtime` do rascunho (`datetime.fromtimestamp`,
`text/rascunho.py:150`, `:218`), e quem perde é apagado (`qt/painel_de_texto.py:2315`,
`rascunho.descartar`). Na hora repetida da volta do horário de verão, ou depois de trocar o fuso da máquina,
um rascunho 40 minutos mais novo compara como mais velho e some. Há outras seis gravações de `now()` sem
fuso: `gallery_scan.py:339`, `importacao_de_imagens.py:666`, `marcas_de_casa.py:333`, `review_queue.py:528`,
`text/conflitos.py:273` e `text/treino.py:402`. Severidade baixa: o Brasil não tem horário de verão desde
2019.

**Solução.** `agora_iso()` = `datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")`, com
deslocamento; a comparação passa a ser entre `datetime` com fuso, nunca entre strings. Guarda: nenhum
`datetime.now()` sem argumento nem `fromtimestamp` sem `tz` em `src/` fora da função.

**Teste que falha primeiro.** `test_rascunho_gravado_depois_da_volta_do_horario_entra_no_caderno`, com dois
instantes de deslocamentos `+01:00` e `+00:00`.

**Aceite.** O teste e a guarda passam.

**Entregue** (2026-11-08): `agora_iso()` mora em `relogio.py`, fora do fecho de medição, com `agora()`, `do_arquivo(mtime)` e `ler_iso()`, que lê a hora antiga sem fuso como hora local e devolve `None` para a ilegível (que não recusa o rascunho). O conserto fica em `Caderno.trazer_rascunho`; `qt/painel_de_texto.py` não mudou. Além das seis gravações, os dois carimbos de nome de arquivo (`cli/audit.py`, manifesto de `text/conflitos.py`) passaram a `agora()`, e a guarda (`tests/test_relogio.py`) ficou sem exceção. `time.strftime` em `batch.py` fica fora da guarda.

## Fase 113 — Escritas idempotentes e saídas corretas

## S-818 · Exportação de PGN atômica, e sem `.review.pgn` de rodada anterior

**Problema** (confirmado por script). `pdf_to_pgn.py:1019` e `:1038` gravam o PGN do livro e o de revisão
com `write_text`, que trunca antes de escrever e, no Windows, escreve CRLF. O sidecar de proveniência é
aberto com `open("w")` (`proveniencia.py:194`), sem `newline=` (CRLF no Windows), e uma linha pela metade
faz `read_sidecar` levantar `JSONDecodeError`. Quando a rodada nova não tem nada a revisar, o
`livro.review.pgn` da rodada anterior fica no disco, e o relatório diz `review_path=None`.

**Solução.** Os três arquivos por `atomic_write_text` com quebra LF. Rodada sem revisão faz
`unlink(missing_ok=True)` do `.review.pgn`.

**Teste que falha primeiro.** `test_exportar_sem_revisao_remove_review_pgn_antigo` (duas rodadas, a segunda
sem item a revisar); `test_pgn_exportado_e_lf`.

**Aceite.** Os dois passam. Uma queda simulada no meio da gravação deixa o PGN anterior inteiro.

**Entregue** (2026-11-08): sem divergência. A queda simulada virou o terceiro teste (`test_queda_na_gravacao_deixa_o_pgn_anterior_inteiro`), que interrompe a troca de cada um dos três arquivos por vez e confere que o anterior fica byte a byte e que nenhum temporário sobra.

## S-819 · Retomada de exportação sem perda de campo

**Problema** (confirmado por script). `export_checkpoint.py:216-276`:
`position_from_dict(position_to_dict(p))` perde `stipulation`, `stipulation_closes`, `stipulation_keys`,
`stipulation_repairs` e `stipulation_reason`; `_context_to_dict` perde `caption_after_move`, `coordinates`,
`first_move_number`, `first_moves_text` e `stipulation`. As páginas lidas antes da interrupção saem da
exportação retomada sem `[Stipulation]`, `[StipulationCheck]` nem `[OCRStipulation]`. Como `gate_confidence`
sobrevive, uma posição aceita por reparo de estipulação sai sem dizer que foi reparada.

**Causa.** A lista de campos está escrita à mão, e a dataclass cresceu sem ela.

**Solução.** Serialização derivada de `dataclasses.fields`, com conversão explícita só dos tipos aninhados.
Leitura que recusa chave desconhecida e preenche ausente pelo padrão do campo. A versão do checkpoint sobe;
`load_partial`, que hoje recusa toda versão diferente (`export_checkpoint.py:366`), passa a aceitar a
anterior com aviso de que os campos novos faltam.

**Teste que falha primeiro.** Para cada campo de `DiagramPosition` e de `DiagramContext`, um valor diferente
do padrão; o ida-e-volta tem de ser igual.

**Aceite.** O teste é gerado a partir de `fields()`, então um campo acrescentado depois entra nele sozinho.

**Entregue** (2026-11-08): como especificado; o checkpoint vai à versão 2 e a 1 retoma com aviso. Além dos dez
campos citados, o ida-e-volta perdia também `side_to_move_confidence` igual a 0,0 (o `or 1.0` da leitura o
trocava por 1,0). Chave desconhecida numa linha de página cai no mesmo descarte da linha rasgada, com o nome
da chave no aviso.

## S-820 · Importação de imagens idempotente

**Problema** (confirmado por leitura). `importacao_de_imagens.py:871-955`, `:279-293`: cada amostra vai para
`labels.csv` na hora (`gravar_item` → `append_training_sample`), mas o lote que marca o item como salvo só é
gravado a cada 25 itens, e o `gravar_andamento()` final não está num `finally`. Uma queda, ou qualquer
exceção que não seja `OSError`/`ValueError` (um `cv2.error` de `ler`), deixa até 24 linhas no CSV que o lote
ainda mostra como pendentes. A segunda rodada as grava de novo com nome novo, e nada as deduplica: a mesma
imagem cai no treino e no teste. Também: `LabelStore.append` (`labels.py:384`) aceita nome de arquivo
repetido, e o nome da amostra sai do relógio (`dataset.py:528`), cujo passo medido nesta máquina é ~1,5 ms
(plausível: duas gravações no mesmo passo sobrescrevem o PNG).

**Solução.** O andamento gravado a cada item, e o final num `finally`. `append_training_sample` recusa
imagem cujo hash de conteúdo já está no CSV. `LabelStore.append` recusa nome repetido. O arquivo da amostra
é criado com `open(..., "xb")` e um sufixo aleatório curto. Lote ilegível é leitura travada (S-812): não
recomeça.

**Teste que falha primeiro.** `test_importacao_interrompida_nao_duplica_linhas` (`ler` levanta
`RuntimeError` no item 3; duas rodadas; uma linha por hash);
`test_duas_amostras_no_mesmo_instante_nao_se_sobrescrevem` (relógio congelado).

**Aceite.** Os dois passam.

**Entregue** (2026-11-08): divergiu em dois pontos. (1) O andamento não é gravado a cada item: continua a
cada 25, agora também num `finally`. Medido: o lote de 5.600 imagens tem 2,5 MB e leva 0,64 s para gravar,
mais que a leitura do modelo (~0,55 s por imagem). O processo morto, que nem o `finally` cobre, fica com o
dataset: o lote automático reconhece a imagem que já está no `labels.csv` e a marca como salva, apontando
para a amostra que já existe, sem gravar segunda linha (função `ja_no_dataset`, contada à parte na chave
`ja_no_dataset`). Pela conferência, `gravar_item` recusa. (2) Essa conferência mora em `importacao_de_imagens.py`, e não em
`append_training_sample`. Ela compara a procedência (`source_pdf`, página, diagrama) e depois os pixels.
Só pelo conteúdo, o mesmo tabuleiro em pixels iguais em dois livros seria recusado; e conferir o conteúdo
na janela principal leria centenas de PNGs de 800 px a cada «Salvar». `LabelStore.append` recusa nome
repetido, e o PNG nasce com `open(..., "xb")` e sufixo aleatório. Se a gravação falha, o arquivo
reservado é apagado. A leitura travada do lote já vinha da S-812.

## S-821 · PDF pesquisável idempotente e atômico

**Problema** (confirmado por leitura). `text/pdf_pesquisavel.py:664` **acrescenta** a marca em `keywords` a
cada rodada; `:589` e `:241` gravam com `save` direto no destino. Usar a saída como entrada duplica a camada
invisível, porque nada confere se a camada já é nossa: no padrão (`so_sem_camada=False`) toda folha é
reescrita, e `tinha` só alimenta o relatório. `_sem_uso` (`:745`) não tem chamador.

**Solução.** A marca é trocada, não somada. A marca é do documento, não da folha; num documento que a traz,
o texto invisível (modo de renderização 3) escrito pela nossa fonte é removido de cada folha antes de
escrever o novo. A gravação vai por `tobytes()` e `atomic_write_bytes`. `_sem_uso` sai.

**Teste que falha primeiro.** Rodar duas vezes, a saída da primeira como entrada da segunda; a marca aparece
uma vez e a busca por uma palavra devolve um resultado por ocorrência, não dois.

**Aceite.** O teste passa.

**Entregue** (2026-11-08): a camada nossa sai das folhas que a rodada reescreve (a folha que esta rodada
não leu guarda a camada da anterior); a marca do documento é o `producer` ou a palavra nas `keywords`, e o
fluxo reconhecido é o `BT ... ET` em `3 Tr` na `helv` que o `insert_textbox` grava. A S-253 (`escrever`)
recebeu a mesma limpeza, porque copia a folha de um livro que pode ser saída da S-210. Gravar por bytes
depois de fechar o livro deixa a saída ser a própria entrada, o que o `save` recusava.

## S-822 · Catraca de escrita: nada em `src/` grava fora do `atomic_io` sem exceção declarada

**Problema** (confirmado). Além dos casos das S-818 a S-821: `onnx_export.py:61` (`torch.onnx.export` direto
no destino), `cli/texto_estilo_conjunto.py:169` (`manifesto.csv` direto) e `splits.py:252` (`os.linesep`,
então os bytes do `splits.csv` mudam com a plataforma).

Também gravam direto no destino `torch.save` (`cli/texto_estilo_classificador.py:356`,
`text/treino.py:386`), `np.savez` (`text/dataset.py:647`, `cli/texto_estilo_conjunto.py:159`),
`detection_census.py:555`, `:571` e `qt/painel_de_estudo.py:3274` (este em `"a"`). E `atomic_io.write_image`
(`atomic_io.py:141`) não é atômica, dentro do próprio módulo atômico. O lote de diagramas
(`diagramas_em_lote.py:191`) sobrescreve arquivos que já existem na pasta escolhida sem perguntar
(plausível; a docstring de `nomes_do_lote` reconhece o risco e só o resolve dentro do mesmo lote).

**Solução.** Todos consertados (ONNX, `torch.save` e `np.savez` para um temporário ao lado e `os.replace`;
`write_image` pelo mesmo caminho dos outros escritores do módulo). Uma guarda por AST: nenhum `write_text`,
`write_bytes`, `open(..., "w"/"wb"/"a")`, `torch.save`, `np.save*`, nem `.save(` de documento `fitz`, em
`src/` fora das funções atômicas de `atomic_io.py` e de uma lista de exceções com razão escrita (log,
temporários, anexar a um registro de eventos).

**Teste que falha primeiro.** A guarda, que hoje acusa os pontos acima.

**Aceite.** A guarda passa com a lista de exceções, e a lista só pode encolher (catraca).

**Entregue** (2026-11-08): a guarda é a de `tests/test_atomic_writes.py`, estendida em vez de duplicada, e a exceção passou de arquivo para `arquivo::função` (com `TETO_DE_EXCECOES = 4` e reprovação para exceção que não desculpa mais nada); o `pdf_to_pgn.py` saiu das duas listas, já vazias de motivo desde a S-818. O temporário vizinho mora em `atomic_io.atomic_write_stream`, que recebe quem escreve num fluxo (`torch.save`, `np.savez`); `atomic_write_path` dá o caminho do temporário ao `torch.onnx.export`, que só aceita caminho, e `atomic_write_pil` serve à Pillow; `atomic_write_bytes`, `atomic_write_text` e `write_image` passaram a ser ele. Além da lista: `text/onnx_glifos.py`, o cache de marcas de `qt/tema.py` (só gravado se não existe, então um PNG truncado ficaria para sempre), o `.ico` de `ui/plataforma.py` e os recortes de `qt/painel_de_estudo.py` e `qt/painel_de_texto.py`. Divergência: o `write_pgn` em `"a"` ficou como exceção declarada -- é o "acrescentar ao PGN" da S-346, e reescrever a base de partidas inteira para pôr um jogo no fim custaria a base a cada estudo, quando o append nunca trunca. O lote de diagramas não pergunta: o que já está na pasta conta como nome tomado, e o item novo sai com o sufixo. O CSV do censo manteve os bytes (o `\r\n` do módulo `csv`).

## S-876 · Cabeçalho livre inválido não derruba a exportação do livro

**Problema** (confirmado por script). `pdf_to_pgn.py:905-906`, `gallery.py:278-290`,
`ui/gallery_model.py:340-348`: um cabeçalho livre da Galeria com nome `Comentário` ou `Torneio Local` faz
`build_pgn_games` levantar `ValueError: invalid pgn header tag`, porque o python-chess recusa nomes fora de
`^[A-Za-z0-9][A-Za-z0-9_+#=:-]*` e valores com quebra de linha. O campo (`qt/painel_da_galeria.py:1475`) só
faz `strip()`. Um cabeçalho digitado à mão impede de exportar o livro inteiro, e a janela mostra a mensagem
crua em inglês.

**Solução.** O nome validado pelo `TAG_NAME_REGEX` do `chess.pgn` na entrada (`set_header` e `_headers`),
com a recusa dita em português; `\r` e `\n` dos valores trocados por espaço.

**Teste que falha primeiro.** `test_cabecalho_livre_com_acento_nao_derruba_exportacao`.

**Aceite.** O teste passa; o campo recusa o nome inválido antes de gravar a Galeria.

**Entregue** (2026-11-08): a decisão mora em `gallery.recusa_do_nome_de_header` e `gallery.valor_de_header`, usadas por `_headers`, `GalleryModel.set_header` e pelo campo livre do `PainelDaGaleria`. Duas coisas além da letra: a recusa cobre também `FEN` e `SetUp` (o campo livre dizia «Header FEN gravado» sem gravar nada), e o nome inválido que já está num `.json` de Galeria gravado antes sai na leitura com aviso no log -- não há nome válido para onde levá-lo, e mantê-lo pararia a exportação.

## S-877 · Caractere de controle não estraga o EPUB nem o DOCX

**Problema** (confirmado por script). `epub.py:264-289`, `:570-605`, `:646-649` (`html.escape`) e
`docx_saida.py` (ElementTree): um PGN com `\x02` no `Event` e `\x01`/`\x0b` num comentário gera
`content.opf`, `nav.xhtml` e `estudo_001.xhtml` que o próprio `epub.verificar` acusa de XML mal formado, e
um DOCX cujos `core.xml`, `document.xml` e `header1.xml` não abrem. A camada de texto de PDF e as bases de
PGN trazem `\x02`/`\x03` de glifo sem mapa. O exportador grava sem rodar o `verificar` que o módulo tem
(`:237-238`). E o `.md` exportado não escapa `*`, `_` nem `1.` em início de linha
(`text/exportacao.py:220-236`; plausível).

**Solução.** `_texto_xml(s)`, num lugar, remove o que o XML 1.0 proíbe (`[\x00-\x08\x0b\x0c\x0e-\x1f]`),
usada antes de `html.escape` e antes de cada `.text` do ElementTree. O exportador de EPUB roda `verificar`
antes de dar a exportação por concluída. O `_texto_xml` ganha um irmão para Markdown.

**Teste que falha primeiro.** `test_epub_com_controle_passa_no_verificar` e
`test_docx_com_controle_abre_no_elementtree`; `test_markdown_escapa_marcacao_em_inicio_de_linha`.

**Aceite.** Os três passam.

**Entregue** (2026-11-08): o lugar único é `texto_xml` em `text/exportacao.py` (público, porque EPUB, DOCX
e `.html` o chamam), que tira o proibido e escapa numa chamada só, no lugar de cada `html.escape`; o
`docx_saida.py` monta o XML por texto, e não por ElementTree, então não havia `.text` a cobrir lá. O
`.text` do `diagrama_svg` ficou de fora: o que entra nele é marca gerada e FEN validada, nunca texto do
livro. O `verificar` roda dentro de `epub.escrever`, que os dois exportadores chamam, e o pacote com
defeito sai como `ValueError` sem tocar o disco (o painel de estudo passou a apanhá-lo). O irmão do
Markdown é `texto_markdown`: `*`, `_` e a barra em qualquer ponto, `1. `/`2) ` em começo de linha;
`1.e4` colado não é lista no CommonMark e fica como está.

## S-879 · Legenda com lance inexistente cai no casamento pela posição

**Problema** (confirmado por script). `livro_com_pgn.py:269-280`: com `2...Nc6` na legenda o estado é
`confere`; com `2...Kc6` (o OCR troca N por K) o estado é `sem_no`, mesmo com a posição lida idêntica a um
nó do livro, porque o ramo `elif lido` só roda quando a legenda não tem lance nenhum. E
`lance_da_legenda('23.e8Q')` devolve `'23.e8'`, que nunca casa.

**Solução.** Quando `com_rotulo` não acha nó, o casamento cai em `com_posicao(lido)` e depois em
`_vizinhos`. A promoção entra na expressão do lance.

**Teste que falha primeiro.** `test_legenda_com_lance_inexistente_cai_na_posicao`;
`test_lance_com_promocao_e_lido_inteiro`.

**Aceite.** Os dois passam.

**Entregue** (2026-11-08): como na spec. A promoção sem `=` só é lida em lance de peão à última fileira, porque depois de outro lance a letra é avaliação (`12.Re8N`, novidade); e `test_legenda_com_lance_inexistente_cai_nos_vizinhos` cobre a queda em `_vizinhos`.

## S-899 · Solução de tática com número do meio da partida fecha

**Problema** (confirmado por script). `taticas.py:1023-1029` chama `compose_fen` sem `fullmove`, e o
tabuleiro fica no lance 1; `text/notacao.py:466-473` recusa então qualquer número impresso diferente.
`validar_solucao(pl, ["4.Qxf7#"])` dá zero lances e o motivo "o livro escreveu o lance 4 e a posição está no
1"; com `1.Qxf7#` fecha. Livros de partidas imprimem `23.Qxh7+`. E `validar` não distingue `15.` de `15...`:
a linha `["1.", "e5"]` com as pretas na vez fecha, o contrário do que promete a docstring.

**Solução.** `validar_solucao` tira o número e o lado do primeiro token numérico (`N.` brancas, `N...`
pretas) e os passa a `compose_fen`; `validar` confere o ponto contra a reticência. A S-880 trata do roque.

**Teste que falha primeiro.** `test_solucao_numerada_no_meio_da_partida_fecha`;
`test_numero_de_brancas_nao_aceita_lance_de_pretas`.

**Aceite.** Os dois passam.

**Entregue** (2026-11-08): o número e o lado saem do **primeiro lance** e não do primeiro token numérico (`notacao.numero_do_primeiro_lance`, sobre o mesmo laço de `validar`): em «12. 1.Qxf7#» o 12 é o do problema, e lê-lo como lance recusaria a linha que antes fechava. A reticência solta (`4 ... ♗c5`) também diz pretas, e `test_o_numero_e_a_reticencia_soltos_nao_sao_lance_nem_erro` passou a esperar o motivo do lado. O `Exercicio` continua com a FEN no lance 1 (`_exercicio`), o que não muda os lances em SAN.

## Fase 114 — A tela e o editor sabem de onde veio cada resultado

## S-823 · `AncoraDaTela(documento, pagina)` pura

**Problema** (confirmado por script e por leitura). `qt/janela.py:1508`: o `quando_pronto` da leitura
captura só `pagina`, e a guarda de `_chegaram_itens` (`:1663`) compara só a página. `_abriu_livro` (`:1214`)
não cancela a tarefa em curso. Ler a página 1 do livro A, abrir o livro B (que abre na página 1) e deixar a
leitura terminar põe os diagramas de A na tela de B; o Ctrl+S seguinte grava amostras de A com o nome e a
página de B, no dataset de treino. No cancelamento (`:1614`), `_chegaram_itens(self.pdf.page_index, ...)`
passa a página **atual**, o que torna a guarda vácua: virar a página e cancelar arquiva o parcial da página
N como página M. A detecção (`:1457`, `:1642`) tem a mesma forma.

**Causa.** Premissa 2. "O resultado ainda é da tela?" está decidido de três jeitos: `DeteccaoDeFundo` leva
`(documento, pagina)`, `painel_do_pdf._folha_chegou` compara `(folha.source, folha.indice)`, e a leitura
leva só a página.

**Solução.** `ui/ancora_da_tela.py`: `AncoraDaTela(documento: ChaveDoLivro, pagina: int)`, congelada, com a
`ChaveDoLivro` da S-827 (Fase 112), e `ainda_vale(ancora, tela) -> bool`. Capturada no pedido e conferida na
chegada pelos três. O nome não é `Ancora`: `estudo.py` já tem uma classe
`Ancora(documento, pagina, diagrama)`, que é outra coisa. O cancelamento usa a âncora capturada.
`_abriu_livro` cancela a tarefa em curso.

**Teste que falha primeiro.** Com a `TarefaAdiada` (S-805): ler A, abrir B, soltar a leitura; o painel não
recebe nada e o rodapé diz por quê. Variante: virar a página, cancelar, conferir que o parcial não é
carregado.

**Aceite.** Os dois testes passam, por `QTest`, sem remendar método privado.

**Entregue** (2026-11-08): `AncoraDaTela.de(caminho, pagina)` monta a âncora pela `chave_do_livro`, e
`frase_do_descarte` diz no rodapé se a tela mudou de livro ou de página. `_chegaram_itens` e
`_chegaram_candidatos` passam a receber a âncora (os testes que os chamavam com o número da página
passam `AncoraDaTela.de(janela._pdf, n)`), e `_chegou_a_deteccao_de_fundo` saiu: o `achou` do detector
liga direto em `_chegaram_candidatos`, e `painel_do_pdf._folha_chegou` também pergunta `ainda_vale`
(antes, `Path ==`). A âncora do cancelamento vai por `partial` ao `_falhou`, e a frase
«Leitura cancelada: N ficaram na lista» só aparece quando o parcial entrou de fato. `qt/janela.py` ficou
nas mesmas 2.313 linhas. Os testes estão em `tests/test_qt_ancora_da_tela.py`; a `TarefaAdiada` ganhou
o `deleteLater` que `manter_viva` chama.

## S-824 · Aba Texto arquiva a folha que leu

**Problema** (confirmado por script). `qt/painel_de_texto.py:3871`, em `_leitura_terminou`:
`self._pagina_indice = int(self.campo_de_folha.value()) - 1`. O índice lido volta no resultado
(`PaginaLida.pagina`) e é ignorado. Ler a folha 5, virar o visualizador para a 9 e deixar a leitura chegar
deixa `documento.origem.pagina == 4` e `folha_atual()[0] == 8`: a aba acha que está na 9 com a 5 na tela. A
troca de livro durante a leitura desenha a folha do livro antigo sob o novo; `_caderno_da_tela` impede
gravá-la no caderno, mas não impede mostrá-la.

**Solução.** `self._pagina_indice = pagina.pagina` (o que veio do resultado), e o resultado de outro livro é
descartado pela `AncoraDaTela` da S-823.

**Teste que falha primeiro.** `test_folha_trocada`, a escrever com a `TarefaAdiada`; o script da revisão que
o antecipa falha hoje com `8 != 4`.

**Aceite.** O teste passa, e o de troca de livro também.

**Entregue** (2026-11-08): `test_folha_trocada` e `test_livro_trocado` em `tests/test_qt_texto_caderno.py`,
com a `TarefaAdiada`; o primeiro falhava com `8 != 4`, o segundo desenhava «texto lido da folha 5» sob o
livro novo. A folha de outro livro é descartada comparando `chave_do_livro(pagina.documento)` com a do livro
na tela (S-827), e não pela `AncoraDaTela`: a S-823 corria em paralelo, e aqui a folha **não** se compara
(ela vem do resultado), só o livro. O rodapé diz qual folha ficou de lado e por quê. Seis testes que
remendavam `_ler` com uma folha de outro livro (`livro.pdf` contra `pasta/livro.pdf`, ou nenhum livro
aberto) passaram a abrir o livro da folha que chega.

## S-825 · O `eventFilter` do `PainelDeTexto` por tabela

**Problema** (confirmado por leitura). `PainelDeTexto.eventFilter` (`qt/painel_de_texto.py:4242-4291`,
complexidade 34) trata nove assuntos numa cadeia de `if`: histórico do teclado, Esc, Enter na marca, clique
no rodapé, resize do vazio, dica, Ctrl+roda, clique e duplo clique na miniatura. O comentário de `:4261`
registra um `qFatal` que já houve ali, e a defesa foi um `getattr` local. Depois da S-800 a exceção num
filtro vai ao `sys.excepthook` e é registrada (como `qt/atalhos.py:301-304` já descreve), então o que sobra
é a forma.

**Solução.** Um dicionário `(objeto, tipo do evento) → tratador`, montado depois de `_montar`, e um
`eventFilter` de dez linhas que consulta a tabela. Nenhum `try` novo: a borda é a da S-800.

**Teste que falha primeiro.** Não há: é refatoração. Antes dela, um teste de caracterização por `QTest` para
cada um dos nove assuntos acima.

**Aceite.** A caracterização passa antes e depois; a complexidade do `eventFilter` fica abaixo de 5.

**Entregue** (2026-11-08): a caracterização é `tests/test_qt_texto_filtro.py`, nove testes (um por assunto,
cada um com o lado em que o evento **não** é comido); tirar qualquer uma das sete entradas da tabela
reprova o teste do seu assunto e só ele. A tabela tem sete pares e não nove: o histórico, o `Esc` e o
`Enter` são o mesmo `KeyPress` do editor, e ficam num tratador só (`_tecla_na_folha`, complexidade 6). O
`eventFilter` tem complexidade 4. A tabela nasce vazia antes de `_montar` e é cheia depois dele, o que
tira o `getattr(self, "status")`.

## S-826 · Tarefa sem pai em todos os painéis

**Problema** (confirmado por script, no mecanismo). `trabalho.manter_viva` documenta que uma `Tarefa` com
pai widget aborta o processo ao fechar. A regra vale na janela e é ignorada em 16 lugares:
`qt/painel_de_texto.py:2369`, `:2888`, `:2922`, `:3570`, `:3771`, `:3809`; `qt/analise_da_partida.py:116`;
`qt/arvore_de_aberturas.py:309`, `:441`; `qt/busca_de_partidas.py:341`; `qt/fila_de_livros.py:204`;
`qt/indice_da_base.py:97`; `qt/lote_de_diagramas.py:124`; `qt/painel_de_treino.py:161`, `:263`;
`qt/preferencias.py:428`. O `closeEvent` da janela (`qt/janela.py:2226`) espera o detector, o aquecimento e
a própria tarefa, mas não a da aba Texto. Ler uma folha e fechar a janela basta para o processo morrer na
saída.

**Solução.** A `Tarefa` perde o parâmetro `parent` (ele é só por nome, `qt/trabalho.py:85`), e o mypy acusa
os 16; cada um vira `manter_viva(Tarefa(...))`, com os slots por um `trabalho.slot_se_vivo` (o `_se_viva` de
`qt/janela.py:1584`, promovido). O `closeEvent` espera também as tarefas registradas pela S-805. O mypy é a
guarda.

**Teste que falha primeiro.** Um subprocesso que abre o `PainelDeTexto` com uma leitura de 2 s, fecha e
confere o código de saída 0.

**Aceite.** O teste passa e o mypy está verde sem o parâmetro.

## S-828 · `AppState` tipado no `PainelDeTexto`, e o histórico aparado na leitura

**Problema** (confirmado por leitura). `state_from_dict` (`ui/state.py:364`, complexidade 51) é um parse
único e tipado; a complexidade é repetição. Os defeitos estão em volta: `PainelDeTexto.aplicar_estado` e
`anotar_estado` (`qt/painel_de_texto.py:3174`, `:3196`) recebem `estado: object` e redeclaram cada padrão do
`AppState` por `getattr(estado, "texto_quebra", True)`, com 14 `type: ignore`: um segundo lugar para os
padrões. `MAX_PDF_HISTORY` não é aplicado na leitura, e um arquivo com 500 entradas segue com 500. A
docstring de `_gravar_estado` (`qt/janela.py:896`) diz que `board_zoom` "não é tocado", e `:922` o grava.

**Solução.** `aplicar_estado(estado: AppState)`, sem `getattr` nem `ignore`. `state_from_dict` dirigido por
uma tabela `(campo, tipo, faixa, padrão)` interpretada por um laço. O histórico aparado em
`state_from_dict`. A docstring corrigida.

**Teste que falha primeiro.** `state_from_dict({"pdf_history": {str(i): 0 for i in range(80)}})` devolve 50
entradas.

**Aceite.** O teste passa; a complexidade de `state_from_dict` fica abaixo de 10; os 14 `ignore` somem (a
catraca da S-804 desce).

**Entregue** (2026-11-08): o teste é `test_o_historico_lido_e_aparado_ao_teto` (falhava com `80 != 50`), e
ficam as **últimas** 50 entradas, porque a ordem do arquivo é a de uso (`recentes`). A tabela é
`(campo, leitor)` e não `(campo, tipo, faixa, padrão)`: o leitor (`_texto`, `_fracao(0,25, 2,0)`...) junta
tipo e faixa, e o padrão continua só no `AppState` -- pô-lo na tabela seria o segundo lugar que o item tira
do painel. `state_from_dict` tem complexidade 3; `LeituraPorTabelaTests` confere que todo campo do
`AppState` faz ida e volta e que o de tipo errado cai no padrão. `qt: type_ignore` desceu de 81 para 67.

## S-829 · `DeteccaoDeFundo` leva a âncora no próprio sinal

**Problema** (plausível, latente). `qt/trabalho.py:181-216`: `parar` zera `_tarefa` mas não `_em_curso`. Um
`pedir` em seguida inicia outra tarefa, e o `pronto` velho, ainda na fila de eventos, sai rotulado com o par
da nova; o `finished` velho zera a nova, e duas detecções correm. Hoje `parar` só é chamado no `closeEvent`.

**Solução.** A `AncoraDaTela` vai no `partial` do sinal `pronto`, e não num atributo que o próximo pedido
sobrescreve.

**Teste que falha primeiro.** `pedir`, `parar`, `pedir` de outra página, e então os dois sinais na ordem em
que a fila os entregaria: o primeiro resultado sai com a âncora da primeira página.

**Aceite.** O teste passa.

**Entregue** (2026-11-08): `_em_curso` saiu; a âncora vai por `partial` no `pronto` e no `falhou`, e a
tarefa vai no `finished`, para que o `finished` velho não zere a tarefa nova (a segunda metade do
problema, que a solução da spec não cobria). **O PyQt não desfaz a ligação a um `partial`** quando o
objeto morre (medido: o slot é chamado depois de `sip.delete`), e o docstring dizia que o método ligado
era o que protegia: as três ligações passam por `_enquanto_vivo`, que pergunta `sip.isdeleted`. O
teste usa uma `TarefaAdiada` cujo `wait` diz que a thread já acabou com os sinais ainda na fila.

## S-887 · O Ctrl+Z do editor nunca aplica a posição de outro diagrama

**Problema** (confirmado por script). `qt/painel_de_resultado.py:1316` e `:1331` (`_chegou_a_segunda` e
`adotar_do_livro`) gravam `_estado_de(indice)` na pilha única, que guarda só o diagrama selecionado.
`livro_com_pgn.aplicar` (`:327`) chama `adotar_do_livro` para cada diagrama da página. Numa página com dois
diagramas adotados do livro, uma edição no diagrama 0 seguida de Ctrl+Z dá ao diagrama 0 a posição e o lado
do diagrama 1. O mesmo acontece na segunda opinião quando o usuário troca de diagrama enquanto ela é lida. O
tabuleiro na tela vira o de outro diagrama sem aviso, e o Ctrl+S seguinte grava rótulo errado no
`labels.csv`.

**Solução.** Só entra na pilha a mudança do índice selecionado (`indice == self.modelo.clamped_index()`); as
dos outros índices não entram (a pilha já zera ao trocar de diagrama). Com isso a adoção num índice não
selecionado deixa de ser desfazível, contra a docstring de `adotar_do_livro` ("Desfazível como qualquer
edição"), que passa a dizer isso; a alternativa é uma pilha por índice.

**Teste que falha primeiro.** `test_adotar_do_livro_em_outro_indice_nao_entra_na_pilha`: o cenário acima,
afirmando que `fen_at(0)` não é a posição do diagrama 1 depois do Ctrl+Z.

**Aceite.** O teste passa, por `QTest`.

## S-888 · Desfazer volta a posição e a procedência juntas

**Problema** (confirmado por script). `ui/editor_model.py:416-423` e `qt/painel_de_resultado.py:1150-1162`.
Depois de adotar a segunda opinião e dar Ctrl+Z, `fen_at(0)` volta a ser a leitura, mas
`save_target().route` continua `"segunda-opiniao"` e `disputed_squares(0) == (59,)`; com o livro, ficam a
nota em `from_book` e as `book_squares`, e a explicação (`:1748`) segue dizendo "PGN do livro". E desfazer
até a leitura original deixa `has_unsaved_hand_edits` e `has_hand_edits` verdadeiros, porque `_voltar` passa
por `apply_placement`, que marca `edited_by_hand`, e por `set_side`, que muda a procedência da vez para
`"manual"` (`ui/editor_model.py:92-101`, `:293-300`): ao fechar aparece uma pergunta sem motivo, e
`ui/page_results.py:170` não descarta a página do cache. A coluna `corrected_by` (S-52, S-66) existe para
medir de onde veio o rótulo, e uma leitura do modelo aceita sai gravada como "segunda opinião".

**Causa.** A procedência mora fora do estado que a pilha guarda.

**Solução.** O estado da pilha leva a procedência (segunda opinião, livro, casas disputadas, origem da vez e
o `edited_by_hand` do item, que vem da própria edição, `_tabuleiro_mudou` → `apply_placement`, e que nada
desmarca hoje) junto da colocação; `_voltar` restaura tudo e não passa pelos caminhos que marcam edição à
mão.

**Teste que falha primeiro.** `test_desfazer_a_segunda_opiniao_volta_a_rota_ocr_aceito` e
`test_desfazer_ate_a_leitura_nao_deixa_pendencia`.

**Aceite.** Os dois passam.

## S-893 · O campo de FEN aplica também a vez que mostra

**Problema** (confirmado por script). `qt/painel_de_resultado.py:1029-1044`: o campo mostra a FEN inteira
(`... w - - 0 1`, preenchido em `:1630`), mas `aplicar_fen` só lê `placement_of(texto)`. Digitar
`... b - - 0 1` e aplicar muda a posição, deixa o lado `w` no modelo e reescreve o campo com `w`. O campo
aceita algo que mostra e o descarta sem avisar.

**Solução.** Texto com um segundo campo `w` ou `b` chama `modelo.set_side` antes de registrar na pilha; um
segundo campo inválido é recusado com mensagem.

**Teste que falha primeiro.** `test_aplicar_fen_com_vez_preta_troca_o_lado`.

**Aceite.** O teste passa.

## S-894 · O PGN do livro que chega atrasado não apaga a correção em andamento

**Problema** (confirmado por leitura). `qt/livro_com_pgn.py:238-241`, `:327` e `ui/editor_model.py:349`:
`_indice_chegou` só confere se os itens são os mesmos objetos e chama `aplicar`; `mark_from_book`
sobrescreve `fen_edits[k]` sem conferir se a pessoa já mexeu naquele diagrama. A janela é a leitura do
`.pgn` em segundo plano. A correção é trocada pela do livro sem aviso.

**Solução.** `aplicar` pula o índice `k` quando `fen_at(k) != items[k].placement` ou o diagrama tem edição à
mão.

**Teste que falha primeiro.** Com a `TarefaAdiada` (S-805): editar o diagrama 0, soltar o índice do PGN,
afirmar que a edição ficou.

**Aceite.** O teste passa.

**Entregue** (2026-11-09): a pergunta mora em `ui/editor_model.touched(item, fen)` (a que `unsaved_hand_edit` já fazia por dentro) e `DiagramEditorModel.touched_at(k)`, sem pilha; `aplicar` a faz só quando `items[k]` do Resultado ainda é o item lido. Além da letra, o rodapé diz «N diagrama(s) já corrigido(s) à mão ficaram como estavam», e a vez escolhida sem mexer em peça também conta como mexer. A correção desfeita antes de o índice chegar deixa o livro entrar (S-888). A `TarefaAdiada` ganhou `deleteLater`, que o `manter_viva` chama no `finished`.

## S-891 · As setas andam na direção da tela com o tabuleiro virado

**Problema** (confirmado por script). `qt/tabuleiro_editavel.py:237-247` e `ui/teclado_do_tabuleiro.py:79`:
`andar_selecao` soma ±1 e ±8 ao índice sem olhar `flipped`. Com o tabuleiro virado e a seleção em e4, a seta
para cima leva a e5, que na tela fica uma linha **abaixo**, e a seta para a direita leva a f4, uma coluna à
**esquerda**. O tabuleiro do Resultado é virado sempre que o livro imprime do lado das pretas
(`qt/painel_de_resultado.py:1593-1609`): quem corrige pelo teclado se perde justamente nesses diagramas.

**Solução.** O passo é calculado na tela: `display_from_index`, a seta sobre linha e coluna, e
`index_from_display` de volta, numa função pura de `ui/teclado_do_tabuleiro.py`.

**Teste que falha primeiro.** `test_seta_para_cima_sobe_na_tela_com_o_tabuleiro_virado`, por
`QTest.keyClick`, comparando `display_from_index`.

**Aceite.** O teste passa para as quatro setas, virado e não virado.

## S-875 · O motor que caiu é reaberto na próxima análise

**Problema** (confirmado por script). `engine.py:436-442`, `:458-464`, `:490-496`: `EngineTerminatedError` é
subclasse de `EngineError` e vira `RuntimeError`, mas `self._engine` continua apontando para o motor morto,
e `start()` sai cedo quando `_engine` não é `None`. Um motor falso que sai com código 3 no primeiro `go`
deixa as chamadas seguintes falhando com "engine event loop dead". A sala de estudo, o treino e a análise da
partida ficam sem motor até trocar o binário.

**Solução.** No `except`, motor terminado (`EngineTerminatedError`, ou `returncode` preenchido) faz
`self._engine = None`, e o próximo `start()` reabre.

**Teste que falha primeiro.** Em `tests/test_engine.py`, um motor falso que morre no primeiro `go` e
responde no segundo: a segunda `analyse` devolve um lance.

**Aceite.** O teste passa.

## S-882 · "Segunda opinião remota" só aparece quando tem quem a use

**Problema** (confirmado por leitura). `ui/configuracoes.py:122-127` e `ui/strings.py:146` põem no diálogo
de configurações o interruptor "Segunda opinião remota", o campo de endereço e o tempo limite, mas nenhum
módulo de `qt/`, `ui/` ou `cli/` chama `net_correction.build_provider` nem `predict_fen_via_net`, e
`CORRIGIR_PELA_REDE` só existe em `ui/strings.py`. O botão "2ª opinião" usa só o leitor local
(`qt/painel_de_resultado.py:1217`). Nenhuma imagem sai da máquina; o diálogo promete um recurso que não
existe.

**Solução.** Os três campos saem do diálogo até o recurso ser ligado. Uma guarda: todo campo do diálogo tem
um consumidor em `qt/`.

**Teste que falha primeiro.** A guarda (acusa os três campos `remote_fen.*`).

**Aceite.** A guarda passa.

**Entregue** (2026-11-08): os três campos foram para `FORA_DA_JANELA` com o motivo, e a aba «Segunda opinião» passou a ser da seção `local_reader` (some o desvio `ABA_DO_LEITOR_LOCAL` do diálogo). A guarda (`tests/test_configuracoes.py`) lê `qt/` **e** `ui/`, e não só `qt/`: o treino e o reconhecimento são lidos pela camada pura (`ui/pedido_de_treino`, `ui/configuracoes.reconhecimento`) a pedido do `qt/`. Ela é por seção -- quem lê a seção a entrega inteira a quem usa -- e tem o controle positivo das cinco seções lidas. `strings.CORRIGIR_PELA_REDE` ficou: não aparece em tela nenhuma e volta com o recurso.

## S-883 · O leitor tsoj não troca a pasta corrente fora da trava

**Problema** (plausível). `tsoj_reader.py:67-74` e `:182`: `predict` faz `os.chdir` dentro de uma `Tarefa`,
fora do `_IMPORT_LOCK`. Dois `predict` ao mesmo tempo restauram a pasta na ordem errada. Durante os ~7 s da
primeira carga, `Path(".")` e `Path.cwd()` usados pela janela (`qt/painel_de_estudo.py:166`,
`qt/lote_de_diagramas.py:234`) apontam para o clone. O `sys.path.insert(0, checkout)` fica para sempre.

**Solução.** O `chdir` de `predict` sob o `_IMPORT_LOCK`; os dois usos de pasta corrente da janela trocados
por caminho absoluto.

**Teste que falha primeiro.** Duas threads chamando `predict` com um módulo falso: a pasta corrente final é
a inicial.

**Aceite.** O teste passa em 100 repetições.

**Entregue** (2026-11-08): a trava entrou no próprio `_cwd` (virou `RLock`, porque o import já a segura
ali), e as 100 repetições estão dentro do teste. A janela tinha um terceiro uso, `qt/painel_do_pdf.py:222`;
os três caem em `DEFAULT_PDF_DIR`, e uma guarda acusa `Path(".")`, `Path.cwd()` e `os.getcwd()` em `qt/`.
O `sys.path.insert(0, checkout)` ficou: a solução não o pede, e tirá-lo depois do import quebraria
qualquer import tardio do clone, o que não foi conferido sem o clone instalado.

## S-910 · Número com vírgula e ordem alfabética pela mesma régua da tela

**Problema** (plausível). Cerca de 13 lugares fazem `.replace(".", ",")` à mão, e cerca de 8 mostram ponto
decimal ao usuário: `qt/painel_de_resultado.py:1711`, `:1732`; `qt/painel_da_galeria.py:963`, `:1134`;
`ui/impressao_do_estudo.py:261`; `ui/pedido_de_treino.py:112`, `:137`; `ui/resumo_do_dataset.py:168`. Já
existe `ui/formato.py:79`, só para porcentagem. As tabelas do Qt já ordenam pelo idioma do sistema, e a
biblioteca usa `dobrar`; só `qt/painel_do_dataset.py:603` usa `sorted` cru numa caixa de seleção (Á depois
de Z).

**Solução.** `ui/formato.decimal(x, casas)`, usado pelos oito e pelos treze; uma guarda contra `:.Nf}` em
`ui/` e `qt/` fora de `formato`. A caixa do dataset ordena por `dobrar`.

**Teste que falha primeiro.** A guarda (acusa os oito); a caixa do dataset com `Ádám` e `Zukertort` põe
`Ádám` primeiro.

**Aceite.** Os dois passam.

**Entregue** (2026-11-08): `formato.decimal` e `formato.porcentagem` cobrem os 28 lugares que a guarda (AST,
`:.Nf}`, `:.N%}` e `:.{casas}f}`) achou em `ui/` e `qt/`, incluindo os `:.0f}` de MB e minutos. Divergiu: a
confiança de `qt/painel_de_resultado.py` foi para `formato.confianca` (`82,0%`), e não para `decimal`, porque
a S-169 já decidiu que confiança se lê em porcentagem; `qt/painel_de_texto.py` (`segundos`) ficou como exceção
nomeada na guarda, por estar em edição paralela; `dobrar` saiu da lista de órfãs de `tests/test_ui_orfaos.py`,
porque agora tem chamador.

## Fase 115 — Interpretador, empacotamento e documentos

## S-830 · Python 3.13 como interpretador padrão

**Problema** (confirmado). O `README.md:38-43`, o `pyproject.toml:5-12` e a S-436 registram que o 3.10 sai
de suporte em outubro de 2026. Hoje é 2026-11-08, o `.python-version` diz `3.10`, o `.venv` é 3.10 e o
`.exe` embarca esse interpretador, sem correção de segurança: o risco que a S-436 nomeou. O CI já roda 3.13
numa perna (a matriz em `.github/workflows/ci.yml:43-44`; a ressalva de `:37-39` sobre o Tk do 3.13 ficou
vencida com o corte).

**Solução.** `.python-version` em 3.13, `requires-python` no piso que a D5 da solidez escolher (3.13 em (a),
3.11 em (b)), o `python_version` do `[tool.mypy]` (`pyproject.toml:261`), o `target-version` do ruff
(`:238`), os comentários de `:16-22`, o `uv.lock` regerado, o PyInstaller e o `--selftest` do bundle no
3.13, a perna 3.10 do CI aposentada. O `.venv` de GPU (memória "GPU para treino") conferido à parte.

**Teste que falha primeiro.** O `tests/test_environment.py` passa a exigir o piso da D5.

**Aceite.** CI verde no piso e em 3.13; o `.exe` gerado roda `--selftest`; o README diz a versão nova.

## S-831 · Documentos no presente do Qt, e os status que se contradizem

**Problema** (confirmado). Restos do Tk no presente: `README.md:178` ("o mesmo `OcrService` que o Tkinter
usa"), `README.md:183` ("widgets de Tk"), `ci.yml:26` e `:37`. `ROADMAP_FASE14.md:22` cita "`app_tkinter.py`
em 2.226" e `ROADMAP.md:914` dá 2.226 para `qt/janela.py`, que tem 2.293 (o teste compara com tolerância), e
`ROADMAP_FASE14.md:22` traz também a faixa invertida "S-324 a S-226". Status em conflito:
`ROADMAP_FASE14.md:400` e `:487` com ⚠ e a tabela com ✅; `:906` "S-102 continua aberta" e `:492` com ✅;
`ROADMAP_FASE7.md:1368` "S-36 continua aberta", entregue como S-55; o `ROADMAP_TEXTO_PRECISO.md` só marca
S-711 e S-712, e a spec marca também S-710, S-715 a S-718 e S-720; a S-702 tem `###` e não `##` na spec. O
README não cita `cvoff-gallery`, `cvoff-scan` nem `cvoff-texto-conflitos`, e diz que "`--help` lista o
resto", o que nenhum comando faz. O comentário do `pyproject.toml` sobre `cvoff-texto-status` diz S-178 a
S-216 (são 40 itens, até a S-217). `SPEC_REVISAO.md:1337` cita `cvoff-evaluate`; o comando é `cvoff-eval`.
`cvoff-texto-status` diz que a S-182 faz `tests/test_text_status.py` falhar, e sem os pesos ele pula.

**Solução.** Cada frase corrigida no lugar. O README ganha a lista dos 47 comandos gerada de
`[project.scripts]`, com um teste que compara as duas.

**Teste que falha primeiro.** O teste da lista de comandos (hoje faltam três).

**Aceite.** Uma linha de conferência por frase corrigida, cada uma com o `grep` que a acha antes e não a
acha depois; entre elas, `grep -n "Tkinter usa\|widgets de Tk" README.md` e
`grep -n "app_tkinter.py. em" docs/ROADMAP_FASE14.md` vazios, e o número de linhas citado para
`qt/janela.py` igual ao do disco. O texto histórico de `ROADMAP.md` e `ROADMAP_FASE7.md` fica como está.

**Entregue** (2026-11-09): o `qt/janela.py` tem 2.311 linhas no disco de hoje, e não 2.293; é o número citado agora nos dois placares, e a guarda continua com a tolerância da S-135. A faixa invertida virou "S-324 e S-221 a S-226" (a conta da catraca: 1.800 → 1.865). Do `ROADMAP.md` mudou só a coluna "hoje" do placar da Fase 6 e o "hoje são 1.677" logo abaixo, que virou "em 2026-08-18 eram"; no `ROADMAP_FASE7.md` o título "S-36 continua aberta" ficou, com uma nota de que a S-55 a fechou. A regra "falta artefato não versionado" passou a morar em `text_status.so_falta_artefato`, usada pelo teste e pelo comando, que mostra essas divergências à parte. A lista dos 47 comandos sai de `lista_de_comandos` em `tests/test_docs.py`.

## S-832 · A tabela de faixas e o `ARCHITECTURE.md` que enxergam tudo

**Problema** (confirmado). A spec das S-585 a S-598 mora em `ROADMAP_PDF_COM_PGN.md:53-333`, com `###`, e a
tabela "Onde mora a spec de cada item" não tem a linha. A guarda passa porque arquivo `ROADMAP*` é isento. O
`ARCHITECTURE.md:159` diz "meia centena de módulos" em `ui/`, que tem 78; 30 dos 73 módulos de `qt/`, 12 dos
68 de `text/` e cerca de 45 de `ui/` não são citados, entre eles toda a primeira entrega das Fases 100 a 107
(`fusao`, `tesseract`, `leitor_de_linha`, `guarda_de_leitura`, `admissao`, `camada_prosa`,
`caderno_na_suite`).

**Solução.** A linha `| S-585 a S-598 | [ROADMAP_PDF_COM_PGN.md](ROADMAP_PDF_COM_PGN.md) |` em toda cópia da
tabela, e a isenção dos `ROADMAP*` restrita a item **não entregue**. O `ARCHITECTURE.md` com uma linha por
módulo, e uma guarda: todo módulo de `qt/`, `text/` e `ui/` aparece nele.

**Teste que falha primeiro.** A guarda do `ARCHITECTURE.md` (acusa cerca de 87 módulos) e a da isenção
(acusa as S-585 a S-598).

**Aceite.** As duas passam.

**Entregue** (2026-11-09): a guarda conta só a linha de **tabela** da seção do pacote, e por isso `ui/` ganhou seção própria (`### A camada pura da interface`) e tabela; contada assim ela acusava 149 módulos (41 de `qt/`, 29 de `text/` e os 79 de `ui/`, que só tinham citação em prosa), e não os cerca de 87 da estimativa. Os doze "outros" de `text/` saíram da prosa para a tabela. Uma segunda guarda acusa linha que cita módulo que não existe. O `ROADMAP_PDF_COM_PGN.md`, agora casa declarada, passou a trazer a tabela de faixas também.

## S-884 · No `.exe`, o OCR que falta é dito na janela

**Problema** (confirmado por leitura). `packaging/cvoff.spec:102` exclui `onnxruntime`, `settings.py:259`
tem `engine = "rapidocr"` como padrão, e `ocr.py:139-146` responde ao `ImportError` com um aviso no log que
manda rodar `uv sync --extra ocr`, impossível no `.exe`; o pipeline segue sem OCR em silêncio.

**Solução.** Com `sys.frozen`, uma frase própria (como a do `tsoj_reader`, S-387) que a janela mostra. Ou o
`onnxruntime` entra no bundle: decisão D8 da solidez, tomada junto da S-830.

**Teste que falha primeiro.** Com `sys.frozen` simulado e o import falhando, a frase é a do bundle.

**Aceite.** O teste passa.

**Entregue** (2026-11-08): a frase mora em `ui/ocr_que_falta.py` e a janela a põe no rodapé ao abrir, no lugar de "Abra um livro em PDF para começar."; o fecho de medição não foi tocado, e por isso a linha de log de `ocr.py` que manda rodar `uv sync --extra ocr` continua igual também no `.exe` (mudá-la obriga a remedir os quatro relatórios). A D8 segue aberta: com o `onnxruntime` no bundle, o `rapidocr` sobe e a frase deixa de aparecer para ele, sem mudança de código.

## S-885 · CI com permissão mínima e ações fixadas

**Problema** (confirmado). `.github/workflows/ci.yml` não tem bloco `permissions:`, então o token tem o
padrão do repositório em todo push. `actions/checkout@v4` e `astral-sh/setup-uv@v5` estão presos por tag,
não por SHA. O extra `second-opinion` nunca é instalado, e o `tsoj_reader` não roda no CI.

**Solução.** `permissions: contents: read` no topo; as ações fixadas por SHA com a tag em comentário; uma
perna (ou um passo) com o extra `second-opinion`.

**Teste que falha primeiro.** Uma guarda em `tests/test_docs.py` (ou num teste do CI) que exige
`permissions:` e `@<40 hex>` nas ações.

**Aceite.** A guarda passa.

## S-907 · Arrastar um PDF para o ícone abre o livro

**Problema** (confirmado por script). `app_pyqt.py:286-295`: o parser só aceita `--pdf`, e o
`configure_logging` vem depois do `parse_args`. Com
`sys.argv = ['ChessVisionOFF.exe', r'C:\Livros\Nunn.pdf']` e `sys.stderr = sys.stdout = None`, que é o
bundle `console=False`, o `argparse` tenta escrever o erro de uso no `stderr` que não existe e levanta
`AttributeError`, sem janela e sem linha de log. Arrastar o livro para o ícone e "Abrir com..." passam o
caminho como argumento posicional: é o gesto natural no Windows.

**Solução.** `pdf` posicional opcional (`nargs="?"`) ao lado de `--pdf`; `configure_logging` antes do parse;
o parser com `exit_on_error=False`, e um erro de argumento vai ao log enquanto a janela abre assim mesmo.

**Teste que falha primeiro.** `test_main_aceita_pdf_posicional_sem_stderr`: `main` com argv posicional e
`stderr = None`, com a janela remendada; o caminho chega a `abrir_pdf`.

**Aceite.** O teste passa; o `--selftest` do bundle cobre o argumento posicional.

**Entregue** (2026-11-08): além do `exit_on_error=False`, `parse_known_args`, porque no 3.10 o argumento
que sobra (dois livros arrastados de uma vez) ainda chama `parser.error`; o que sobra vai ao log e abre o
primeiro. Quem chega ao `selftest` com o livro posicional é afirmado por teste (`MainTests`), sem gerar o
`.exe`. Fica de fora o `-h` num processo sem `stdout`, que ninguém faz por arrasto.

## S-909 · O arquivo de log não leva o nome do usuário

**Problema** (plausível). A rotação do log está certa (2 MB × 5, `logging_setup.py:105`), mas o arquivo
grava sempre em DEBUG, e a mensagem de erro (S-421) diz à pessoa onde ele está, o que convida a anexá-lo a
um relato. 79 chamadas interpolam caminho inteiro, com o nome do usuário (por exemplo `settings.py:551`,
`engine.py:328`, `labels.py:553`), e algumas logam texto do livro ou FEN (`pdf_text.py:297`, `:1528`;
`games_db.py:678`; `dataset_browser.py:309`).

**Solução.** Um filtro `RedigeCaminho` no handler de arquivo, que troca `Path.home()` por `~`; texto do
livro e FEN só em DEBUG, que deixa de ser o nível padrão do arquivo.

**Teste que falha primeiro.** Um `logger.warning` com um caminho dentro da pasta do usuário: a linha gravada
traz `~`, não o nome.

**Aceite.** O teste passa.

**Entregue** (2026-11-08): `RedigeCaminho` é o **formatador** do handler de arquivo, e não um filtro: o
filtro vê a mensagem antes do `format`, e o traceback, que traz um caminho por quadro, só ganha texto ali.
Cobre `\` e `/`, sem caixa no Windows. O arquivo deixa de gravar DEBUG sem `-v`, **com uma exceção**: o
registro com `exc_info` entra em qualquer nível, porque o `cli.run_main` manda o traceback em DEBUG para não
sujá-lo na tela, e é para isso que o arquivo existe (S-126); com `-v` o arquivo recebe DEBUG inteiro. Foram
para DEBUG as duas linhas de `pdf_text.py` que levam texto do livro (declaração e exigência de escopo) e `dataset_browser.py:309` (FEN); o `games_db.py:678`
citado não loga mais nada ali, e os `warning` de `desenho_de_diagrama.py` que levam a FEN de uma falha ficaram.

## Fase 116 — Um pipeline só

O caminho de medição é o fecho de importação que `field_eval.measured_modules()` calcula (36 módulos com o
OCR desligado, como nos quatro relatórios correntes; com `--ocr glifo` entram os de `text/`, 48 ao todo), e
a guarda da S-218 confere o digest dele. **Todo commit que edita um desses módulos remede os quatro
relatórios, em qualquer fase**: custa cerca de 4 minutos, e em doze remedições seguidas os números voltaram
idênticos. O que esta fase junta são os itens que mudam **número**: a S-834, a S-836 e a S-880. A S-835
troca a forma de contar e tem de dar os mesmos números. A S-843 retira um normalizador que é identidade, e a
S-833 troca o caminho da exportação pelo que os relatórios já medem; nenhuma das duas deve mover número. A
S-837 é a remedição em que os números mudam e precisam ser explicados.

## S-843 · O normalizador de tabuleiro sai

**Problema** (confirmado por leitura). Nada em `src/` constrói um `NormalizerConfig` além do `IDENTITY`
padrão (`preprocess.py:163`). A docstring de `:28-36` prescreve normalizar na leitura, em `_load_board`, e a
de `:124` diz que a versão vai para `ArchConfig.version`, o que não é verdade. `ScanConfig` (`:334`),
`preparar_pagina_de_scan`, `pagina_e_scan` e `binarizar_pagina` também só têm chamador em
`tests/test_preprocess.py`. Ligar o normalizador criaria um desvio entre treino e serviço que nada
registraria.

**Solução.** Subtrair antes de somar: o parâmetro sai de `service` e `inference`, e o normalizador sai com
ele, junto da docstring de `:379` que o cita e dos testes de `tests/test_preprocess.py` que só o exercitam
(entre eles o de `:173-175`, que a S-870 deixa de reescrever). O que for de scan entra na mesma decisão: ou
ganha chamador, ou sai. Se um dia voltar, volta registrado no checkpoint.

**Teste que falha primeiro.** Não há teste honesto de "código morto saiu" além do `mypy` e da suíte; o item
fecha pelo `grep` de `NormalizerConfig` sem resultado e a suíte verde.

**Aceite.** `grep -rn NormalizerConfig src/` vazio; suíte verde. `service` e `inference` estão no fecho de
medição: o commit remede, e os números voltam idênticos (o normalizador era identidade). Vem antes da S-833,
que deixa de precisar passar `normalizer=`.

## S-833 · A exportação reconhece pela mesma função que os relatórios medem

**Problema** (confirmado por leitura). Os relatórios de campo medem `OcrService.recognize_page`
(`field_eval.py:1501`). A exportação (o lote, o `cvoff-export-pgn`, a Galeria, a fila de revisão, as
táticas) passa por `pdf_to_pgn._scan_pages` (`:598-705`), uma cópia da mesma corrente (orientação, cor,
lado, próximo lance, estipulação, legalidade) que já se separou da original:

- `_scan_pages` chama `predict_with_orientation` sem `coordinates=` (`:644-649`), e `service.py:914` passa
  `context.coordinates`, preenchido por `pdf_text.py:1491`. A regra de orientação pelas coordenadas da borda
  funciona no caminho de medição e é pulada na exportação;
- `_scan_pages` ignora as opções `colour`, `next_move` e `stipulation`;
- a confiança do portão é calculada duas vezes, e as duas divergem: `pdf_to_pgn.py:670-675` dá `None` quando
  não houve reparo, e `RecognizedDiagram.gate_confidence` (`service.py:207-220`) dá a confiança mínima.

Os quatro relatórios em `docs/metrics/` descrevem um caminho que não gera PGN nenhum.

**Causa.** Premissa 3.

**Solução.** `_scan_pages` chama `OcrService.recognize_page(..., candidates=...)` e monta
`DiagramPosition.from_recognized(RecognizedDiagram)`, construtor que ainda não existe e é criado aqui. A
corrente duplicada e o segundo cálculo do portão saem. A complexidade de `_scan_pages` (35) cai junto.

**Teste que falha primeiro.** Uma página falsa cujo contexto tem `coordinates`, passada por
`iter_pdf_diagrams` e por `recognize_page`, com `predict_with_orientation` remendado para registrar os
argumentos: os dois caminhos têm de dar os mesmos argumentos, a mesma FEN, a mesma rotação e a mesma
confiança do portão.

**Aceite.** O teste passa, e `pdf_to_pgn.py` não chama `predict_with_orientation` (guarda por `grep`).

## S-834 · Decodificação restrita sem relógio

**Problema** (confirmado por script). `decode.py:386-391` usa `SEGUNDOS_MAXIMOS = 0.5` (`:308`): a busca
para pelo relógio, além do teto de `max_expansions = 5000` (`:325`) que já existe. Em 40 tabuleiros
sintéticos com ruído, 2 saem com FEN ou `constraints_satisfied` diferentes com orçamento de 50 ms e sem
orçamento; 3 levam mais de 50 ms. A mesma probabilidade decodifica diferente numa máquina carregada, em
rodadas paralelas ou na primeira chamada lenta de um processo (uma causa plausível da memória "primeira
leitura do processo difere"), e o relatório de campo deixa de ser reproduzível.

**Causa.** Premissa 5.

**Solução.** O relógio sai, e o teto de `max_expansions`, que já existe, é recalibrado para o pior caso
medido ficar abaixo de ~0,5 s nesta máquina.

**Teste que falha primeiro.** Num tabuleiro cuja leitura crua tem violação, remendar `decode.time.monotonic`
para avançar 1 s por chamada: hoje a busca sai na expansão 0 (o relógio é conferido quando
`expansions % 64 == 0`, `decode.py:391`), e o resultado tem de ser igual ao de sem remendo.

**Aceite.** O teste passa; os 40 tabuleiros dão o mesmo resultado em dez rodadas com carga paralela.

## S-835 · Contadores de campo por campo tipado, não por frase

**Problema** (confirmado por leitura). `field_eval.py:1225` e `:1233` contam `next_move_ambiguous` e
`stipulation_ambiguous` por `"trocas diferentes" in reason`, frase escrita em `lance_seguinte.py:269` e
`estipulacao.py:484`. `only_king_missing` confere `startswith("falta o rei")` (`decode.py:116`), frase
definida também em `fen_utils.py:53` e `ui/legality.py:116`. Reescrever uma mensagem zera um contador
publicado, sem teste nenhum falhar.

**Causa.** Premissa 4.

**Solução.** `ambigua: bool` nos resultados de reparo do próximo lance e da estipulação, e
`tipo: TipoDeViolacao` (enum) na `_Violation`. `evaluate_page` (complexidade 50) passa a somar por
`FieldReport.somar_leitura(leitura)` a partir desses campos, e o julgamento de cada anotação vira
`_julgar(anotado, lido, limiar) -> Veredito`.

**Teste que falha primeiro.** Trocar o texto das duas mensagens por outro: os contadores têm de continuar
contando. Antes de partir `evaluate_page`, um teste de caracterização que compara byte a byte o JSON do
relatório em fixtures.

**Aceite.** Os dois passam, e o commit remede os quatro relatórios (fecho de medição); `evaluate_page`
abaixo de complexidade 15.

## S-836 · Fonte de diagrama e rótulo de eixo numa regra só

**Problema** (confirmado por script). Duas regras de "fonte de diagrama" que discordam:
`pdf_text.py:348-371` e `text/admissao.py:62-65`. `Leipzig` é diagrama para a `admissao` e texto para
`page_text_lines`; `Schachfiguren` e `XadrezFont`, o contrário; `Kingdom`, `Linares`, `Alpha`, `Echecs` e
`Ajedrez` também discordam. `ChessMerida`, `SkakNew-Diagram`, `ChessAlpha` e `UsualChess` são diagrama e
figurina ao mesmo tempo na `admissao`. E `leitor.EIXO_SOLTO` e `MIN_EIXOS_NA_FILA`
(`text/leitor.py:748-756`) repetem `pdf_text._AXIS_LABEL` e `_MIN_AXIS_LABELS` (`:341-342`), que o leitor
importa pelo nome privado (`:817`); `text/lado.py:106` importa `_side_from_line` do mesmo jeito.

**Solução.** `fontes_de_xadrez.py` com os padrões de fonte de diagrama e de figurina, importado pelos dois
lados; as constantes de eixo públicas nele. `_page_lines` (complexidade 36) parte em `_linhas_do_bloco`,
`_sem_eixos_no_bloco`, `_sem_eixos_na_pagina` e `_agrupar`.

**Teste que falha primeiro.** Uma tabela de nomes de fonte em que os dois consumidores têm de concordar
(hoje discordam em oito).

**Aceite.** O teste passa; nenhum import de nome privado de `pdf_text` fora dele (o de `text/lado.py`
incluído).

## S-880 · O lance seguinte e a estipulação jogam com o direito de roque

**Problema** (confirmado por script). `lance_seguinte.py:133` e `estipulacao.py:235` montam a FEN com
` - - 0 1` fixo, sem roque; o mesmo sufixo está em `audit.py:218`, `dataset.py:483` e `semantics.py:187`.
Depois de `1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5`, `infer_castling_rights` dá `KQkq`, e mesmo assim
`conferir(linha="4.O-O Nf6 5.d3 d6")` responde que não replica "nem com até 2 trocas"; com `4.c3` replica.
Livro de abertura imprime `O-O` o tempo todo, e o reparo procura trocas à toa. Na estipulação, uma defesa ou
chave `O-O` fica invisível, e um problema pode sair "fecha" quando o roque o refuta.
`taticas.validar_solucao` já usa `compose_fen` com o roque inferido: a mesma decisão tomada de dois jeitos
(premissa 3).

**Solução.** O `_tabuleiro` dos dois módulos usa `semantics.compose_fen(colocacao, vez, fullmove=...)`. Os
outros três sufixos fixos são conferidos um a um (o do `dataset` é rótulo de treino e pode ficar).

**Teste que falha primeiro.** `test_linha_com_roque_replica`.

**Aceite.** O teste passa; muda número no caminho de medição e entra na remedição da S-837.

## S-837 · Remedição dos quatro relatórios de campo

**Problema.** As S-834, S-836 e S-880 mudam o que o caminho de medição produz. As remedições dos outros
commits que tocam o fecho devolvem os mesmos números; esta não, e a diferença precisa ser explicada.

**Solução.** Primeiro, reproduzir o relatório arquivado com o `src/` de antes das três (memória "reproduzir
o relatório antes de republicar"). Depois, remedir a partir de um worktree limpo no commit que fecha a fase,
com os `.pt` e o `PDF/` lidos do checkout principal por caminho, por `python -m` (não pelo `cvoff-field`,
que lê o `settings.json`), e registrar o código e o modelo no relatório (memórias "remedir campo a partir de
um worktree" e "checkout principal tem sessões concorrentes": não se remede sobre uma árvore que outras
sessões estão mudando).

**Teste que falha primeiro.** Não há teste novo: a guarda da S-218
(`test_todo_relatorio_corrente_mediu_o_codigo_de_hoje`) reprova até os relatórios serem remedidos.

**Aceite.** Os quatro relatórios declaram o commit e o checkpoint. A diferença para os anteriores está
explicada item a item: a S-834 onde a decodificação estourava o relógio, a S-836 nas fontes que mudam de
lado, a S-880 nas legendas com roque. A S-833 não deve mover número nenhum; se mover, é defeito dela.

## Fase 117 — Treino honesto

## S-838 · Página de campo nunca vai para o treino

**Problema** (confirmado por leitura). `training.py:325-333`: `ensure_splits` grava o `splits.csv` (com
amostras novas talvez sorteadas para `train`) **antes** de `pin_field_pages` (`:362-391`) mover as amostras
de página de campo para `test` e gravar de novo (`:390`). Uma queda entre as duas gravações deixa a
atribuição a `train` no disco, e na rodada seguinte as amostras já não são novas, então nunca são fixadas
(split registrado não se move). Se `field_set.jsonl` não lê, `field_pages_beside` (`:348-359`) avisa no log
e devolve `set()`, com o mesmo resultado permanente. E o casamento compara `source_pdf` exato, enquanto
`field_eval._name_keys` (`field_eval.py:1379`) normaliza NFC, dupla codificação e caixa.

**Solução.** As atribuições forçadas entram em `ensure_splits`, que grava uma vez. Conjunto de campo
ilegível falha fechado: as amostras novas ficam sem partição e o treino recusa começar, dizendo por quê. O
casamento usa a chave de nome de `field_eval`, num lugar só.

**Teste que falha primeiro.** `field_set.jsonl` de lixo e um rótulo novo de página de campo, com um nome de
amostra que o hash do split manda para `train` (senão o teste passa por sorte): `resolve_splits` não o põe
em `train`. Segundo caso: `pin_field_pages` remendado para levantar, nova rodada, a amostra termina em
`test`.

**Aceite.** Os dois passam.

## S-839 · O regime do checkpoint guardado inteiro

**Problema** (confirmado por script). `augment.py:103-135`, `:143-183`: `AugmentConfig(hatch=0.9)` e
`AugmentConfig(hatch=0.3)` (o valor que `from_letters` usa para `h`) dão a mesma letra, `augh`.
`from_letters("augh-j0")` descarta o sufixo `-j0` em silêncio. `version_of_checkpoint` devolve `aug0` tanto
para um `.pt` truncado quanto para um que não existe. "Retreinar no regime do checkpoint"
(`ui/pedido_de_treino.py:90`) pode treinar noutro regime e gravar a letra errada: a mesma classe de defeito
do incidente `augx` (memória "regime do checkpoint exige a letra").

**Solução.** O metadado do checkpoint guarda `asdict(augment)`, e o regime é reconstruído dele, exato. A
letra continua como nome curto, derivada. `from_letters` levanta diante de sufixo que não sabe honrar.
`version_of_checkpoint` levanta para arquivo ilegível e devolve `None` para arquivo ausente;
`ui/pedido_de_treino.py:90`, cujo `augment` é `str` e vai para `from_letters` (`qt/dialogos.py:1042`), passa
a tratar `None` como "treino do zero, regime escolhido no diálogo", que é o caminho comum.

**Teste que falha primeiro.** Para toda configuração `c`, `from_metadado(asdict(c)) == c`;
`from_letters("augh-j0")` levanta `ValueError`; `version_of_checkpoint` de um `.pt` truncado levanta.

**Aceite.** Os três passam; um checkpoint antigo, sem o dicionário, é lido pela letra com aviso.

## S-840 · `ArchConfig.from_version` recusa o que não conhece

**Problema** (confirmado por script). `model.py:92-97`, com `# type: ignore`: `"cnn-grey-64-linear"` monta
um modelo de 3 canais (tudo que não é `gray` vira RGB); `"resnet-..."` e `"...-mlp"` montam
`PieceClassifier` em silêncio: `build_model` termina num `return PieceClassifier(arch)` (`:294-296`) para
tudo que não reconhece, e, pelo tipo, o `else` de `PieceClassifier` (`:140`) cobre também `head="board"`,
que nunca chega ali porque `build_model` o desvia antes.

**Solução.** Cada parte conferida contra `typing.get_args(Backbone)`, `get_args(Channels)` e
`get_args(Head)`, com `ValueError`. O `return` final de `build_model` e o `else` de `PieceClassifier` viram
ramos explícitos (`board` incluído) terminados em `assert_never`. O `ignore` sai.

**Teste que falha primeiro.** `pytest.raises(ValueError)` para `cnn-grey-64-linear`, `resnet-gray-64-linear`
e `cnn-gray-64-mlp`.

**Aceite.** O teste passa; o mypy acusa um `Literal` novo não tratado.

## S-841 · O dataset conta e diz o que descarta

**Problema** (confirmado por leitura). `dataset.py:140-141` descarta linha de FEN inválida sem contador e
sem log, e todo outro descarte do mesmo módulo é registrado. Um rótulo estragado some do treino sem ninguém
saber.

**Solução.** Contador por motivo de descarte no `BoardFenDataset` (que o `BoardUnitDataset` envolve), logado
no fim da carga e gravado no metadado do checkpoint. (A colisão de nome de amostra é da S-820.)

**Teste que falha primeiro.** Um CSV com uma FEN inválida entre dez boas: dez amostras, e o contador "fen
inválida" em 1.

**Aceite.** O teste passa; o metadado do checkpoint traz os contadores.

## S-842 · Colocação: um parser de FEN só, na fronteira

**Problema** (confirmado por script). `fen_utils.py:196-228`: `labels_from_fen` aceita `8/.../44`,
`.../4004` e `.../08`, que o python-chess recusa; `fen_from_class_indices([13] * 64)` (`:287`) levanta
`KeyError`, e não `ValueError`, e confere o tamanho só depois de indexar. Há dois parsers de FEN que
discordam.

**Solução.** `Colocacao`: tupla de 64 `Peca | None`, construída só por `Colocacao.de_fen(texto)` (dígitos 1
a 8, nunca dois seguidos, oito fileiras de oito) e por `Colocacao.de_classes(indices)`. Rótulos, FEN e
legalidade consomem o tipo. Entregue em pedaços: o parser primeiro, depois cada consumidor.

**Teste que falha primeiro.** As três entradas acima recusadas por `labels_from_fen`
(`is_syntactically_valid_fen` já as recusa: os dois parsers discordam justamente aí); `[13] * 64` dá
`ValueError`.

**Aceite.** Os testes passam; um teste de propriedade compara `Colocacao.de_fen` com o python-chess em 10
mil FENs sorteadas.

## S-889 · A posição do PGN do livro tem rota própria no rótulo

**Problema** (confirmado por script). `labels.label_route` não recebe `from_book`
(`ui/editor_model.py:416-423`). Com `adotar_do_livro` e nenhum toque da pessoa, a rota sai `ocr-corrigido`,
embora o próprio `mark_net_corrected` diga que leitura de terceiro não conta como trabalho humano. Toda
página de livro digital com PGN infla a contagem de "corrigido à mão" no treino.

**Solução.** Uma constante `PGN_DO_LIVRO` em `labels.py`, um parâmetro `from_book` em `label_route`, e
`from_book=index in self.from_book` no modelo do editor.

**Teste que falha primeiro.** `test_rota_da_posicao_do_livro`: `mark_from_book` seguido de
`save_target().route == PGN_DO_LIVRO`.

**Aceite.** O teste passa; o relatório de rotas do dataset passa a contar a rota nova à parte.

## S-890 · Posição que nenhum lado a jogar torna legal é fatal

**Problema** (confirmado por script). `ui/legality.py:172-196`, `:222`: para `8/8/8/3kK3/8/8/8/8` (reis
adjacentes, com `w` ou `b`) e para `4k3/4R3/8/8/8/8/4r3/4K3` (os dois em xeque), o rótulo é "lado a jogar",
o resumo diz "Só o lado a jogar não fecha", `check_position(...).legal_turn` é `None` (nenhum lado torna a
posição legal) e `illegal_save_question` devolve `None`: a posição é gravada sem pergunta. O painel manda
trocar a vez, o que não conserta nada, e a amostra entra no dataset sem a marca de ilegal confirmada.

**Solução.** Em `explain_position`, posição não legal, não fatal e com `legal_turn is None` é fatal, com o
problema "nenhum lado a jogar torna a posição legal" e as casas de `_check_squares` das duas cores.

**Teste que falha primeiro.** `test_reis_adjacentes_sao_fatais`: `is_fatal` verdadeiro e
`illegal_save_question` diferente de `None`, nos dois casos.

**Aceite.** O teste passa.

## S-844 · Identidade de livro nos splits

**Problema** (plausível). `splits.py:124-186`. O split usa `groups_by_origin` (`training.py:321`), com chave
`(pdf, página, diagrama)` exata, e `duplicate_groups_touching`, que já junta recortes idênticos (colocação e
dHash até 3) entre nomes de livro; `groups_by_book` não tem chamador em produção. O furo que sobra é o mesmo
diagrama com recorte deslocado sob outro nome de PDF. O acervo tem o mesmo livro sob vários nomes
(`...Copia.pdf`, `...Copia_hq.pdf`, uma tradução; memória "acervo PDF tem livros duplicados"), e nesse caso
a mesma página pode cair no treino e no teste.

**Solução.** Uma identidade de livro derivada na fronteira: hash do conteúdo do PDF (D2 da solidez, opção a)
ou uma tabela de apelidos em `data/` (opção b). `groups_by_origin` usa a identidade no lugar do nome;
`groups_by_book` ou ganha chamador ou sai.

**Teste que falha primeiro.** O mesmo diagrama recortado com 6 px de deslocamento (dHash acima de 3) sob
dois nomes de PDF: em (a), dois arquivos de bytes iguais; em (b), dois nomes declarados como apelidos. Os
dois caem no mesmo grupo.

**Aceite.** O teste passa; uma contagem no acervo real diz quantas amostras mudariam de partição, e a
mudança é decidida com o dono antes de gravar o `splits.csv`.

## S-845 · `torch.load` só com `weights_only`

**Problema** (confirmado por leitura; o risco é teórico). `checkpoint.py:110-112`: o recurso de `TypeError`
para `torch.load` sem `weights_only` é morto no torch exigido (`>= 2.6`), e só abriria um caminho de
`pickle` num torch antigo. `cli/texto_train.py:406` e `text/modelo.py:463` chamam `torch.load` sem
`weights_only` explícito, protegidos só pelo padrão do torch atual.

**Solução.** O recurso sai (subtrair), e as três chamadas passam `weights_only=True` explícito.

**Teste que falha primeiro.** Não há: um `.pt` com `__reduce__` arbitrário já dá `UnpicklingError` hoje. O
item fecha por uma guarda: todo `torch.load` de `src/` passa `weights_only=True`.

**Aceite.** A guarda passa, com piso de três chamadas.

## S-846 · O sal do split fixado por valor

**Problema** (confirmado). `tests/test_splits.py:30-35` diz "Valores fixos: se o algoritmo de hash mudar,
isto quebra de propósito", e faz
`assertEqual(assign_split("board_00000.png"), assign_split("board_00000.png"))`: a função comparada com ela
mesma. Mudar `SPLIT_SALT` ou o hash embaralharia treino, validação e teste com a suíte verde. O mesmo em
`tests/test_detection_census.py:107` e `tests/test_side_survey.py:53`.

**Solução.** Dez pares `nome → partição` escritos no teste, e as listas de `sample_pages` dos três testes
escritas por valor (o de `tests/test_side_survey.py:53` usa `sample_pages(402, 12)`).

**Teste que falha primeiro.** O teste novo, rodado com o `SPLIT_SALT` trocado no fonte (um `mock.patch` não
serve: o sal é argumento padrão, avaliado na definição, `splits.py:47`, `:62`, `:272`): tem de reprovar.

**Aceite.** Os três testes fixam valores. O operador de constante `str` da S-803 mata a troca do sal.

## S-900 · O split por livro do texto não aborta o treino

**Problema** (confirmado por script). `text/dataset.py:530-541` e `:590-596` mandam inteiro para o treino o
grupo de duplicatas que atravessa livros, e `livros_em_dois_lados` (`:595-603`) acusa esse mesmo grupo como
livro dos dois lados, o que faz `cli/texto_train.py:274-279` levantar. Com quatro livros e um grupo cruzando
dois deles, 7 a 8 de 10 sementes abortam, conforme o tamanho dos livros. É latente:
`docs/metrics/texto_vazamento.json` mostra que o split por livro nunca rodou. Com o `dedupe` em união-busca,
o mesmo `e` da mesma fonte em dois livros é quase certo, então o primeiro treino que registrar o split
aborta. O teste `tests/test_text_dataset.py:248-255` confere só o vazamento.

**Solução.** `livros_em_dois_lados(livros, lado, aptos=...)` ignora as amostras dos grupos atravessados, que
a regra já mandou para o treino de propósito; `split_por_livro` passa a devolver também esses grupos, e
`cli/texto_train.py` os repassa.

**Teste que falha primeiro.** `test_grupo_que_atravessa_livros_passa_na_trava_de_livro`, nas dez sementes.

**Aceite.** O teste passa.

## Fase 118 — Texto: fronteira e decisões únicas

Os itens desta fase mexem em `text/leitor.py`, `text/fusao.py` e `text/pagina.py`, os mesmos arquivos das
Fases 100 a 107. Cada um entra num ramo próprio, a partir da `main` que já tem a última entrega da prosa, e
o crítico da skill `ocr-texto-preciso` mede a régua antes e depois.

## S-854 · Classificador de glifo e pré-processamento, um só para PyTorch e ONNX

**Problema** (confirmado pelo dryer e por leitura). `text/modelo.py:365` e `text/onnx_glifos.py:229`
(`classificar`) têm semelhança 1,00, e `modelo._entrada` (`:335`) e `onnx_glifos.preparar_recortes`
(`:187`), 0,82. Duas cópias do pré-processamento de glifo são um desvio entre treino e serviço esperando
acontecer; hoje um teste as mantém iguais (`tests/test_texto_onnx.py:77-83`), mas é a premissa 3: copiar e
vigiar a cópia. E `carregar_classificador` já chaveia o cache por `(pesos, meta, device, mtime_ns, size)`
(`text/modelo.py:449`), mas chama `ler_metadado` e `impressao_do_arquivo` (o SHA-256 do `.pt`) **antes** de
consultar o cache (`:423-457`), duas vezes por folha (S-847), e cria um `GlyphRecognizer` novo a cada uma.

**Solução.** O pré-processamento numa função só, que os dois backends chamam. O cache consultado primeiro,
pela chave barata `(caminho, mtime_ns, tamanho)`, e o metadado e o hash calculados só quando ela falta.

**Teste que falha primeiro.** Dez folhas seguidas calculam o hash uma vez (hoje, vinte). A igualdade dos
dois pré-processamentos já tem teste; o que muda é que, com uma função só, ele vira redundante e sai.

**Aceite.** O teste do hash passa, e o de igualdade sai.

## S-847 · `ocr.glyph_model` chega à leitura de página

**Problema** (confirmado por leitura). `_ha_classificador` (`text/leitor.py:1225`) carrega o
`CAMINHO_PADRAO_META` fixo (`:1234`), e `:600-605` chama `build_glyph_recognizer()` sem argumento
(`text/recognizer.py:175-190`). Quem chama sem `reconhecedor` é a aba Texto (`qt/painel_de_texto.py:4578`),
`cli/texto_estilo_motor.py:149` e `cli/texto_flutuante.py:210`. Só `ocr.build_recognizer`, o caminho da
legenda, e `cli/texto_placar.py:288` leem `ocr.glyph_model` (a variável `CVOFF_OCR_GLYPH_MODEL` é aplicada
por `load_settings`, `settings.py:499-502`, que ainda força `engine="glifo"`). O `ModeloInvalido` levantado
em `text/modelo.py:432` manda o usuário configurar exatamente isso. Com `motor="auto"`, quem pôs os pesos
noutra pasta cai para a camada com um aviso no log; com `glifo`, recebe um erro que manda configurar o que
já está configurado.

**Solução.** `classificador_configurado()` em `text/recognizer.py`, que lê a configuração uma vez na
fronteira; `_ha_classificador`, `linhas_do_glifo` e os dois CLIs recebem o resultado. Os dois caminhos
passam por `carregar_classificador`, que lê o metadado e calcula o hash do `.pt` antes de olhar o cache; a
S-854, que vem antes, conserta a ordem.

**Teste que falha primeiro.** Configuração apontando para um par de pesos de brinquedo gerado no próprio
teste (o par real só existe no checkout principal e faria o teste pular no CI), caminho padrão ausente:
`ler_pagina(motor="auto")` sai com procedência `glifo`.

**Aceite.** O teste passa.

## S-848 · `PaginaLida.de_json` na fronteira

**Problema** (confirmado por script). `text/pagina.py:399-411`, `:561-573`, `:936-960`: `{"largura": null}`,
`{"colunas": null}` e `indice: null` levantam `TypeError`, que atravessa o `_carregar` do caderno
(`text/caderno.py:385` só pega `OSError` e `ValueError`); o `indice: null` quebra em
`BlocoDeDiagrama.de_json` (`:621`) e em `Coluna.de_json` (`:773`). `"texto": null` vira a string `"None"`;
`confianca: "nan"` passa. Um bloco gravado como `camada` com confiança 1,0 abre assim mesmo quando a linha
dele é `glifo` com 0,2, porque os campos derivados são lidos do arquivo em vez de recalculados: o estado
ilegal que `menos_confiavel` existe para impedir.

**Solução.** Um `try` só em `PaginaLida.de_json`, convertendo `TypeError`, `ValueError` e `KeyError` em
`PaginaInvalida`. `texto` exige `str`; NaN é recusado. `BlocoDeTexto.de_json` recalcula caixa, confiança,
procedência, negrito e itálico por `de_linhas`, e lê do arquivo só `recuado` e `legenda_de`. Os dois
`de_json` quase iguais (`:561`, `:701`, semelhança 0,86) viram um.

**Teste que falha primeiro.** Os três JSONs levantam `PaginaInvalida`; o bloco inconsistente abre como
`glifo` com 0,2.

**Aceite.** Os dois passam.

## S-849 · "Camada de OCR" numa regra só

**Problema** (confirmado por script). Quatro respostas para "esta camada de texto foi feita por OCR?":
`admissao.PRODUTOR_DE_OCR` (`text/admissao.py:60`, ao lado de `FONTE_DE_OCR`, `:61`, aplicado por trecho em
`:190`), `perfil.de_scan` (`:176`), `cli/texto_grade.MARCAS_DE_OCR` (`:107`, que também lê o `creator`, com
`glyphless` em `:277`) e `camada.camada_tipografica` (`text/camada.py:192`). Pelo produtor,
`ocrmypdf ... / Tesseract` é OCR para o `texto_grade` e não para a `admissao`, e `OmniPage` o contrário; a
`admissao` ainda pega o ocrmypdf pela fonte `GlyphLessFont`, então a divergência é de critério, e só às
vezes de resposta. A memória "medir texto só com camada editorada" depende desta resposta.

**Solução.** `procedencia_da_camada(doc, pagina) -> ProcedenciaDaCamada` pura, num lugar, com os três
critérios (produtor, `creator`, fonte por trecho), e os quatro passam a consultá-la.

**Teste que falha primeiro.** Uma tabela de produtores e fontes com resposta única.

**Aceite.** O teste passa; o ouro-teste (S-702) é reconferido com a regra única, e nenhum livro muda de
estrato sem decisão do dono (D9 da solidez).

## S-850 · Cache de perfil do livro sem `id()`

**Problema** (confirmado por script). `text/camada_prosa.py:215-228`, `perfil_em_memoria`: documento aberto
de bytes tem `name=None`, e a chave do cache vira `(id(doc), page_count)`. O id foi reaproveitado e o livro
B, com o mesmo número de páginas, recebeu o perfil do livro A. A chave também não tem `mtime`.
`camada._identidade` (`text/camada.py:385-400`) recusa exatamente esse caso, por escrito.

**Solução.** O cache usa `_identidade`, e não guarda nada quando ela é `None`. Uma identidade só para
`_RESPOSTAS` e `_perfis`.

**Teste que falha primeiro.** Dois documentos de bytes abertos e fechados em sequência: o perfil do segundo
é recalculado (contador em `perfil_do_livro`).

**Aceite.** O teste passa.

## S-851 · A folha extraída uma vez por leitura

**Problema** (confirmado por script, desempenho). Uma `ler_pagina(motor="camada")` faz 8 `get_text("dict")`
na folha lida (`text/leitor.py:1651-1680`, `:1316-1331`): `page_text_lines`, `spans_com` e `linhas_com` do
negrito e do itálico, `quadros`, `running_page_number` (`_bare_integers`) e, quando `correntes()` dispara,
`page_margin_lines`; com motor de glifo soma-se `camada_tipografica` (`:1687`). `running_page_number` lê
também as quatro vizinhas, uma vez cada, e `documento_registra` amostra de 7 a 14 folhas na primeira vez por
documento. Numa varredura, cada folha é reextraída umas quatro vezes como vizinha (medido no Dvoretsky,
folhas 20 e 21). A S-725 cobre só o cache do Tesseract.

**Solução.** Um valor congelado `FolhaDaCamada` (dict, palavras, texttrace), extraído uma vez e entregue a
funções puras; as chaves de corrente das vizinhas memorizadas por documento.

**Teste que falha primeiro.** Um contador por remendo em `fitz.Page.get_text`, exigindo no máximo um
`get_text("dict")` por folha.

**Aceite.** O teste passa; a régua da prosa sai igual byte a byte; o tempo por folha numa varredura de 50
folhas é medido antes e depois.

## S-852 · Um árbitro de confiança só

**Problema** (confirmado por leitura e pelo dryer). O árbitro está em três cópias: `text/leitor.py:496-513`,
`cli/texto_colados.py:62-73` e `cli/texto_duas_linhas.py:107-118` (as duas cópias do CLI com semelhança 0,91
entre si; com a do leitor, 0,73 e 0,76, porque o leitor já divergiu). O comentário justifica a cópia:
"Escrito igual ao de lá de propósito". Uma edição numa cópia separa o que foi medido do que roda. Os módulos
`text/colados.py` e `text/duas_linhas.py` são gêmeos (`vale` e `_perfil_*` com semelhança 1,00).

**Causa.** Premissa 3.

**Solução.** `colados.arbitro_de_confianca` público, e as duas cópias do CLI apagadas. Os gêmeos
`colados`/`duas_linhas` compartilham `vale` e o perfil por um parâmetro de eixo.

**Teste que falha primeiro.** Um teste que importa o árbitro dos três chamadores e confere que é o mesmo
objeto.

**Aceite.** O teste passa; o dryer não acusa mais os pares.

## S-853 · Contrato do leitor de linha: `None` é "não leu"

**Problema** (confirmado por leitura). O contrato de `text/leitor_de_linha.py:3` diz que `None` é "não leu"
e `""` é "leu vazio". `tesseract.ler_linhas` (`text/tesseract.py:363-366`) devolve `""` para recorte vazio,
que nunca foi ao processo. Com essa leitura vazia, `fundir` derruba a prosa do glifo, e
`text/leitor.py:1392` (`if not tokens:`) apaga a linha inteira. E em `text/leitor.py:1754`,
`leituras_da_reserva, _falha = leitor.ler_folha(...)`: no ramo `camada_na_folha` a falha é jogada fora,
enquanto os outros ramos emitem `LEITOR_INDISPONIVEL`. Um terceiro furo, plausível: `_linhas_da_reserva`
alinha as confianças por `zip(texto.split(), confiancas, strict=False)`, e uma palavra do Tesseract com
espaço Unicode dentro (U+2009) desloca ou corta as confianças sem erro; `text/fusao.py:233` tem o mesmo
efeito por um dicionário truncado por `len(t)`.

**Solução.** `None` para recorte vazio. `if _falha: avisos.append(Aviso(LEITOR_INDISPONIVEL, ...))`. Os
`Token` construídos direto da lista de `Palavra`, com `strict=True`. A regra 5 da fusão continua sendo da
S-721.

**Teste que falha primeiro.** Um `LeitorDeLinha` falso devolvendo `([], "sem tesseract")` numa folha
admitida com `guarda.nao_lida`, com `reserva=True` e uma palavra para a qual `_pede_outra_leitura` responde
verdadeiro (só assim o ramo chama `ler_folha`): o aviso tem de estar na página. Uma palavra com U+2009: as
confianças continuam alinhadas.

**Aceite.** Os dois passam.

## S-855 · Tipos fechados no texto

**Problema** (confirmado por leitura). `LivroDoOuro` e `FolhaDoOuro` (de `text/ouro.py`) guardam `split`,
`lingua`, `origem`, `estrato` e `diagramacao` como `str`, conferidos depois em `problemas`;
`LivroDoOuro(**livro)` levanta `TypeError` com chave desconhecida (`text/ouro.py:137-146`).
`fusao.Token.origem: str` (`text/fusao.py:206`), `classe_do_token -> str` e `PaginaLida.unidade: str`
deveriam ser fechados. `_ler_pagina_do_livro` recebe 25 parâmetros, 23 deles só por nome. E
`text/vertical.py` (complexidade 28 em `candidatos`) só tem chamador no `cli/texto_vertical`; `Caixa.angulo`
(`text/boxes.py:84-96`) é sempre 0 em produção, e o ramo `girado` de `linhas.quebrar_em_linhas` é morto,
como o de ângulo em `text/leitura_de_linha.py:176`.

**Solução.** `Literal` ou `StrEnum`, convertidos uma vez em `de_json`. Uma `OpcoesDeLeitura` congelada no
lugar dos 23 parâmetros nomeados. `text/vertical.py`: decisão D3 da solidez (ligar a S-197 no caminho da
página, ou mover o módulo para o CLI e apagar o ramo `girado`).

**Teste que falha primeiro.** Um manifesto com `estrato` desconhecido levanta na leitura, e não em
`problemas`.

**Aceite.** O teste passa; o mypy acusa um valor fora do `Literal` escrito num teste de tipo.

## S-856 · Exceções estreitas no texto e no perfil de cor

**Problema** (confirmado por leitura). `ocr_caption._read_band` (`ocr_caption.py:233-237`) devolve `[]`
quando o motor quebra, e também quando a faixa não renderiza (`:227-228`): "sem legenda" fica igual a
"falhou", e só o log diz qual. `pdf_text.py:1434` e `text/camada.py:114`, `:159`, `:434`, `:445` usam
`except Exception`; em `:434` e `:445` o `False` vai ao chamador, e em `:445`, se todas as folhas da amostra
derem erro, o `False` vai para o cache. Fora do texto, `cor_por_livro.py:362-365` faz
`except Exception: return None` sem log nenhum: o perfil de cor vem da suíte de fora (`caissa`), e a leitura
muda de resultado conforme ela importa ou não sem que nada registre qual caso aconteceu.

**Solução.** Cada `except` pega só o tipo esperado. `_read_band` devolve um resultado que distingue "sem
legenda" de "motor indisponível". Resposta que veio de exceção não entra no cache. O perfil de cor ilegível
vira `logger.warning(..., exc_info=True)`.

**Teste que falha primeiro.** Um motor de legenda que levanta: o resultado diz "indisponível", não "vazio".
Uma amostra em que toda folha levanta: a próxima chamada pergunta de novo.

**Aceite.** Os dois passam, mais um `assertLogs` com um `colour_for_pdf` que levanta; a catraca da S-804
desce.

## S-898 · Apagar um bloco inteiro conta como correção

**Problema** (confirmado por script). `text/correcao.py:96-127`: `_blocos_comparaveis` percorre só os blocos
ainda presentes em `texto_por_bloco`. Apagar o parágrafo-lixo `~~ lixo de OCR ~~`, a correção mais comum, dá
`correcoes: ()`. Com zero correções, `gravar` deixa a folha como `lida` (`text/caderno.py:446`),
`abre_do_caderno` (`:141-143`) relê sem abrir o caderno quando o motor muda, a releitura não pergunta
(`qt/painel_de_texto.py:3733`), e a S-762 perde as deleções.

**Solução.** Percorrer todos os `BlocoDeTexto` da origem, com `depois = atual.get(indice, "")`;
`blocos_editados` (`text/correcao.py:170`) e `_marcas_intactas` (`:236`), que também indexam `atual[indice]`
e levantariam `KeyError`, fazem o mesmo.

**Teste que falha primeiro.** `test_apagar_o_bloco_inteiro_e_uma_correcao`.

**Aceite.** O teste passa.

## S-901 · Letras de peça por língua e meia-risca numa constante só

**Problema** (confirmado por script). Três decisões para a mesma pergunta: `text/notacao.py:46` usa
`KQRBNSTLDCP`, sem `A` (alfil, espanhol e italiano) nem `F` (fou, francês); `text/fusao.py:61` tem `A` e não
`F`/`L`; `:67` tem `F`/`L` e não `A`. `fusao._ROQUE` (`:68`) aceita `0–0` com meia-risca, e `notacao.LANCE`
e `RESULTADOS` não aceitam `0–0`, `O–O`, `1–0` nem `0–1`. `peso_de_notacao("Axf7+")` e
`peso_de_notacao("Fxe5")` dão 0, `juntar_numero_de_lance("1 5.Axf7+")` não junta, `validar` para em `0–0`, e
`♙e4` conta como lance em `LANCE` enquanto `parse_san("Pe4")` o recusa. O acervo tem livro espanhol.

**Causa.** Premissa 3.

**Solução.** Uma constante de iniciais por língua, num módulo, importada por `notacao` e `fusao`; `_limpo`
troca `–` e `—` por `-`; `RESULTADOS` ganha `1–0` e `0–1`; `♙` e `P` saem do `para_ingles`. `notacao` e
`fusao` estão fora do fecho dos quatro relatórios (OCR desligado), e o commit não remede; `text.notacao`
entra no fecho com `--ocr glifo`.

**Teste que falha primeiro.** `test_notacao_espanhola_francesa_e_meia_risca`.

**Aceite.** O teste passa; o dryer não vê mais duas listas de iniciais.

## S-902 · A busca com figurina não troca peão por bispo

**Problema** (confirmado por script). `text/busca.py:192-200`: `_alternativas` faz `caractere.upper()`, e a
coluna `b` vira `[b♗♝]` mesmo com `diferenciar_caixa=True`.
`achar("bxc6", casar_figurina=True, diferenciar_caixa=True)` acha `♗xc6` e `bxc6`, e
`substituir_todas("bxc6", "dxc6", casar_figurina=True, diferenciar_caixa=True)` reescreve `12.♗xc6` como
`12.dxc6`: a substituição em massa altera um lance real do livro.

**Solução.** Com `diferenciar_caixa=True`, só a letra maiúscula se expande em figurina, e minúscula é
coluna; sem ela, a busca continua achando `♘f3` por `nf3`.

**Teste que falha primeiro.** `test_coluna_b_nao_casa_figurina_de_bispo`.

**Aceite.** O teste passa.

## S-903 · O léxico do livro grava e confere com a mesma dobra de caixa

**Problema** (confirmado por script). `text/caderno.py:284` e `:295` gravam com `.lower()`, e
`text/lexico.py:153` e `:160` conferem com `casefold()`. Depois de "Acrescentar ao léxico", `Großmeister` e
`Παπαδόπουλος` continuam marcadas como desconhecidas. E nenhum dos lados normaliza para NFC (plausível): uma
camada de PDF em NFD (`café`) não casa com `café`.

**Solução.** Uma função `chave_do_lexico(palavra)` = `unicodedata.normalize("NFC", palavra).casefold()`,
usada em `lexico()`, `acrescentar_ao_lexico`, `_de_um_arquivo` e `conhecida`.

**Teste que falha primeiro.** `test_palavra_com_eszett_acrescentada_deixa_de_ser_desconhecida`;
`test_palavra_em_nfd_casa_com_nfc`.

**Aceite.** Os dois passam.

## S-904 · Mudar a caixa devolve a seleção certa

**Problema** (confirmado por script). `text/rico.py:1045-1071`: `mudar_caixa` muda o comprimento do texto
(`straße`, 6 letras, vira `STRASSE`, 7; o mesmo com `ﬁ` → `FI` e com `İ`), e o painel
(`qt/painel_de_texto.py:1683`, `:1442`) mantém a seleção antiga: o pincel seguinte cai um caractere antes do
fim.

**Solução.** Uma função irmã, `mudar_caixa_com_selecao`, devolve o documento e o intervalo novo, e o painel
a usa e passa o intervalo em `selecao=`; `mudar_caixa` fica como está, porque cinco chamadas de
`tests/test_texto_ferramentas.py` dependem do retorno dela.

**Teste que falha primeiro.** `test_maiuscula_de_strasse_seleciona_a_palavra_inteira`.

**Aceite.** O teste passa.

## Fase 119 — Complexidade e duplicação

Toda divisão desta fase segue a mesma ordem: fixar o que o código faz (teste de caracterização, byte a byte
quando a saída é um arquivo), mudar a estrutura, provar que o comportamento não mudou. Função do fecho de
medição se divide com a remedição no mesmo commit, e os números têm de voltar idênticos: é a caracterização
mais forte que o projeto tem.

## S-857 · Argumentos comuns dos 47 comandos num lugar

**Problema** (confirmado pelo dryer e por leitura). Cerca de 30 dos 65 pares do dryer são `parse_args` e
`build_parser` de `cli/` (`texto_grade` e `texto_ordem` com 1,00; `review` e `sides` com 0,88; `export_pgn`
com `field`, `review` e `sides`). E `cli/__init__.py:243-262` classifica qualquer `ValueError`, `OSError` ou
`RuntimeError`, inclusive um `int("x")` de defeito interno, como saída 2 "entrada inválida"; decide a saída
3 por pistas no texto da mensagem (`"checkpoint"`, `".pt"`, `"arch_version"`, `"state_dict"`, `:53`); e
deixa `sqlite3.Error` cair na saída 1.

**Solução.** O mecanismo já existe: `cli/__init__.py:98-138` tem `add_dpi_argument`, `add_model_argument`,
`add_splits_argument` e `add_dataset_arguments`. Ele ganha as opções que ainda se repetem à mão (as de
páginas, `--cache`, `--database`, `--gallery-dir`), e os parsers que as escrevem à mão passam a usá-lo; nada
de um segundo módulo de opções. Um tipo `EntradaInvalida` levantado só nas fronteiras de entrada; todo o
resto é saída 1, com traceback no log.

**Teste que falha primeiro.** Um `int("x")` dentro de um carregador sai com 1, não com 2; um PDF que não
existe sai com 2.

**Aceite.** Os dois passam; o dryer não acusa mais os pares de `cli/`.

## S-858 · Partir `build_pgn_games` e `Trainer.prepare`

**Problema.** `pdf_to_pgn.build_pgn_games` (complexidade 42) e `training.Trainer.prepare` (36).

**Solução.** `build_pgn_games`: um construtor de cabeçalhos por assunto (identidade e fonte, lado a mover,
contexto e legenda, confiança do OCR, reparos de próximo lance e cor, estipulação, proveniência, legalidade
e rotação), cada um devolvendo um `dict`, e o chamador faz `game.headers.update(...)`. `Trainer.prepare`:
`_resolver_datasets()` (splits gravados ou sorteio) devolvendo um `Datasets` tipado,
`_sabotagem_de_rotulos()`, as duas estratégias de carregador e `_metadado_base()` pura.

**Teste que falha primeiro.** Um PGN de ouro gerado de fixtures, comparado byte a byte; o metadado de um
treino de uma época sobre o dataset de brinquedo, comparado campo a campo.

**Aceite.** Os dois passam antes e depois; as duas funções abaixo de complexidade 10.

## S-859 · Partir a detecção em cadeias de filtros

**Problema.** `detection/hybrid.detect_diagrams` (36), `board_detection._contour_candidates` (28) e
`detector_de_marcas.classificar` (31).

**Solução.** `detect_diagrams`: estágio embutido (piso e refino), estágio de contorno como uma cadeia de
filtros `(candidato) -> motivo | None` (conflito de sobreposição, prior de tamanho), um lugar só que
registra as recusas, e a seleção (teto por escore, ordem de leitura); os fechos `_recusado` e
`_caixa_do_quad` no nível do módulo. `_contour_candidates`: cada recusa vira um filtro que devolve um
`RejectedQuad` (`board_detection.py:169`, o tipo da lista `rejected`). `classificar`: tabela ordenada de
regras, primeiro as de forma (proporção, toca a borda, tamanho), depois a família pela faixa de solidez
(estrela, disco, cruz) e a variante pelo centro claro, com os limiares nomeados.

**Teste que falha primeiro.** Caracterização: as caixas e os motivos de recusa das páginas de
`tests/fixtures/` mais páginas sintéticas, até 20, gravados antes, comparados depois.

**Aceite.** A caracterização passa; as três abaixo de complexidade 10. `detect_diagrams` e
`_contour_candidates` estão no fecho de medição: o commit remede, e os números têm de voltar idênticos.

## S-860 · Partir `_ler_pagina_do_livro` e `linhas_do_glifo`

**Problema.** `text/leitor._ler_pagina_do_livro` (71, a maior do projeto) e `linhas_do_glifo` (37).

**Solução.** `_ler_pagina_do_livro` em cinco: a extração da folha (a `FolhaDaCamada` da S-851), a detecção
dos diagramas, o corpo despachado por motor (`_corpo_camada`, `_corpo_glifo` → `_guarda_e_reserva` →
`_prosa_de_outro_leitor`), devolvendo uma
`LeituraDoCorpo(cruas, regioes, quadros, procedencia, avisos, por_palavra)` em vez de reatribuir a tupla,
`anotar_estilo` pura, e `montar` com as margens. `linhas_do_glifo`: o classificador vem de fora (S-847); as
nove chaves de correção e de segmentação viram uma lista de passos montada uma vez das opções (o nome não é
`Correcao`, que já é a correção humana de `text/correcao.py:74`; algo como `PassoDoGlifo`).

**Teste que falha primeiro.** A régua da prosa e o JSON de página das folhas do ouro-dev, gravados antes,
comparados byte a byte depois.

**Aceite.** A caracterização passa; as duas abaixo de complexidade 15. Coordenado com as Fases 100 a 107
(seção da Fase 118).

## S-861 · Partir `problemas` e `fundir`

**Problema.** `text/ouro.problemas` (53) e `text/fusao.fundir` (36). `leitor.montar` (34) segue o mesmo
molde.

**Solução.** `problemas`: a conversão na fronteira (S-855) tira uns 15 ramos; o resto se divide em
`_do_cabecalho`, `_dos_livros`, `_das_folhas` e `_do_teste`, puras, cada uma devolvendo `list[str]`.
`fundir`: `_decidir_par(g, t, bloqueado, existe) -> Origem` pura, como tabela de decisão; `_ajustar_lance`
para o número partido, o dígito absorvido e a palavra colada; `_sem_par_do_glifo` e `_sem_par_do_leitor`.

**Teste que falha primeiro.** Para `problemas`, um manifesto com um defeito de cada tipo e a lista de
mensagens esperada; para `fundir`, a saída da fusão nas folhas do ouro-dev, gravada antes.

**Aceite.** As duas caracterizações passam; as duas abaixo de complexidade 10.

## S-862 · Constantes de caminho e de padrão num lugar

**Problema** (confirmado por leitura). O DPI padrão 220 é literal em cerca de 30 lugares, entre eles
`config.py:289`, `settings.py:418`, `provenance.py:73`, `pdf_io.render_pdf_page` (`:181`),
`text/leitor.py:1247`, `service.py:555`, `batch.py:83`, `pdf_to_pgn.py:502`, `:731`, `:1060`,
`detection_census.py` (quatro), `text/tesseract.py:355`, `:392`, `text/faixas.py`,
`text/guarda_de_leitura.py:61`, `taticas.py:1246` e nove CLIs `texto_*`. `char_classifier.pt` e
`char_meta.json` em `settings.py:283`, `:289`, `cli/texto_train.py:34-35` e `text/modelo.py:55`.
`field_set.jsonl` em `cli/field.py:54`, `qt/campo.py:64` e `training.py:350` (derivado de outro jeito).
`texto_conflitos.json` em `cli/texto_conflitos.py:32` e `text/conflitos.py:57`. `"lado_descritor": 24`
escrito à mão em `cli/texto_conflitos.py` e `cli/texto_train.py:484`, ao lado de `dedupe.LADO_DESCRITOR`. Os
nomes `procedencias.py`, `proveniencia.py`, `provenance.py`, `text/procedencia.py` e `cli/provenance.py` não
duplicam decisão nenhuma, mas confundem.

**Solução.** Uma constante por valor, no módulo dono, importada pelos outros. A troca de nome de
`procedencias.py` é a decisão D6 da solidez. `config`, `pdf_io`, `service`, `settings` e `cli/field` estão
no fecho de medição: o commit remede, e os números voltam idênticos.

**Teste que falha primeiro.** Uma guarda por AST: cada nome de arquivo acima aparece uma vez como literal
**igual** a ele em `src/`, fora de docstring e de comentário, e nenhum parâmetro chamado `dpi` tem `220`
literal como padrão fora do módulo dono (a guarda olha o nome do parâmetro, porque `220` aparece também como
medida de tela, em `qt/livro_com_pgn.py:82`, `ui/cortina.py:72` e `ui/sala_declarada.py:259`).

**Aceite.** A guarda passa.

## S-863 · Os `main` de CLI de complexidade alta

**Problema.** `cli/texto_train.main` (49), `cli/audit._print_report` (39), `cli/audit.main` (29),
`cli/texto_conflitos.main` (29), `cli/texto_placar.main` (28) e `cli/texto_grade.medir` (29).

**Solução.** Cada `main` fica com três passos: parse (S-857), uma função pura que decide o que fazer e
devolve um plano, e a execução do plano. `_print_report` vira uma lista de seções, cada seção uma função que
devolve linhas.

**Teste que falha primeiro.** A saída de cada comando sobre fixtures, gravada antes.

**Aceite.** As caracterizações passam; os seis abaixo de complexidade 15.

## S-864 · Os pares gêmeos do dryer

**Problema** (confirmado pelo dryer). Além dos já tratados (S-848, S-852, S-854, S-857): os exportadores de
um módulo para o outro, `exportar_estudo_docx` com `exportar_estudo_epub` (0,91) e `exportar_texto_docx` com
`exportar_texto_epub` (0,90), invólucros de duas linhas, e `_titulo_do_texto`, idêntico em
`docx_saida.py:645` e `epub.py:474` (1,00); `qt/painel_da_galeria._confirmar_destrutivo` e
`qt/painel_de_estudo._perguntar` (1,00); `qt/arvore_de_aberturas._rodape` e `qt/busca_de_partidas._rodape`
(0,88); `qt/painel_de_recorte._anel` e `qt/tabuleiro_editavel._anel` (0,81); `detection_census.as_dict`
(`:357`) e `side_survey.as_dict` (`:125`) (0,94); `estudo_arquivo.chave_de` e `text/rascunho.chave_de`
(0,88); `cli/texto_grade._linhas_da_camada` e `cli/texto_ordem._linhas_da_camada` (0,84);
`pdf_substituicao.renderizar_com_operacoes` e `renderizar_regiao_com_operacoes` (1,00);
`qt/painel_de_estudo.buscar_partidas` e `arvore_de_aberturas` (0,95).

O par `pdf_substituicao.renderizar_*` espera a D7 (S-881): pode sumir.

**Solução.** Para cada par, decidir se é a mesma decisão (junta) ou só o mesmo esqueleto (declara no
`dryer.json` com a razão). Os exportadores passam a ser um percurso do estudo com dois escritores.

**Teste que falha primeiro.** Os testes existentes de cada par, mais um de caracterização onde não houver.

**Aceite.** Nenhum par ≥ 0,8 sem decisão escrita.

## S-881 · A substituição de diagrama no PDF: ligar ou retirar

**Problema** (confirmado). `pdf_substituicao.py` (917 linhas), `ui/substituicao.py` e
`ui/selecao_de_area.py` têm **0%** de cobertura (626 instruções somadas) e nenhum chamador: a funcionalidade
F9, absorvida em 2026-09-07, está guardada sem o painel (`tests/test_ui_orfaos.py:276`,
`GUARDADO_SEM_O_PAINEL`). `achar_coordenadas` tem complexidade 29 e CRAP 870, o maior do programa. E o
código grava no arquivo do usuário sem guarda contra `entrada == saida`: `substituir_no_pdf(p, p, [])`
levanta `PermissionError` dizendo que o arquivo "está aberto em outro programa", quando quem o segura é o
próprio `fitz.open` da função.

**Solução.** Decisão D7 da solidez: (a) ligar o painel e testar, começando por recusar
`saida.resolve() == entrada.resolve()` com frase própria; (b) retirar os três módulos (subtrair antes de
somar), deixando o registro do que existia no `ARCHITECTURE.md`.

**Teste que falha primeiro.** Em (a), `test_saida_igual_a_entrada_recusada`. Em (b), não há teste honesto
além da suíte verde e da catraca de órfãos baixando.

**Aceite.** Em (a), os três módulos acima de 80% de cobertura; em (b), os três fora de `src/`.

## Fase 120 — Os arquivos-deus do Qt

## S-865 · `PainelDeTexto` em cinco módulos

**Problema** (confirmado). `qt/painel_de_texto.py` tem 5.030 linhas; a classe `PainelDeTexto` vai de `:324`
a `:4546`, com 280 métodos, 79 atributos privados atribuídos (70 no `__init__`) e 28 seções marcadas.

**Solução.** Cinco passos, cada um com a suíte verde e a fachada pública (`aplicar_estado`, `definir_livro`,
`ler`, `confirmar_fechamento`) intacta: (1) `qt/texto_espelho.py`: `_Trecho`, `_Mapa`, a digitação
(`:4072-4240`) e as funções de módulo `_texto_da_tela` e `_do_qt` (`:4752`, `:4770`), quase tudo puro; (2)
`qt/texto_leitura.py`: a orquestração de tarefa (`:3635-3912`, as exportações e `trazer_da_revisao`) num
`ExecutorDaAba` com `manter_viva`, `slot_se_vivo` e a `AncoraDaTela`; (3) `qt/texto_caderno.py`: caderno,
rascunho e mesa; (4) `qt/texto_miniaturas.py`: diagramas no texto, miniatura, dica e menu; (5)
`qt/texto_correcao.py`: léxico, correção, pincel e busca.

**Teste que falha primeiro.** Nenhum novo: a divisão é refatoração, e a suíte da aba Texto (mais os testes
das S-824 a S-826, S-896, S-898 e S-904) é a caracterização.

**Aceite.** `PainelDeTexto` com menos de 800 linhas, como composição das cinco partes.

## S-866 · `PainelDeEstudo` sem o motor, a análise, as táticas e o índice

**Problema.** `qt/painel_de_estudo.py` tem 3.660 linhas e seis classes.

**Solução.** Primeiro sai o motor vivo (`:1142-1321`), a partida inteira pelo motor, as opções do motor e as
partidas da base (`:2262-2726`), e as táticas (`:3185-3280`), com âncora e `manter_viva`; depois a lista de
lances.

**Teste que falha primeiro.** Não há: é refatoração, e a suíte do painel (mais os testes das S-806, S-875 e
S-883, que tocam o painel) é a caracterização.

**Aceite.** Suíte verde em cada passo; o arquivo abaixo de 1.500 linhas.

## S-867 · O bloco de resposta da janela vira decisão pura

**Problema.** `qt/janela.py` (2.293 linhas) é coordenadora legítima, mas o bloco que decide o que fazer com
a resposta de uma leitura (`:1602-1722`, com o cancelamento em `_falhou`, `:1611-1616`) ainda tem a guarda
de página, o cancelamento e a escolha do que selecionar; o resto já delega a decisões puras (`choose_boxes`,
`boxes_from_diagrams`). A guarda de página sai com a S-823; o que este item tira é o resto do bloco (o
cancelamento e a escolha do que selecionar).

**Solução.** `ui/page_results` recebe a `AncoraDaTela` (S-823) e a resposta e devolve o que a tela deve
mostrar; a janela só aplica. É um passo para a S-31.

**Teste que falha primeiro.** A decisão do resto do bloco testada sem Qt.

**Aceite.** O teste passa sem importar PyQt6; a janela perde o bloco.

## Fase 121 — Testes que medem comportamento

## S-868 · Os 26 testes desligados

**Problema** (confirmado). 26 `@unittest.skip` incondicionais: `tests/test_qt_tema.py` (13, motivo
`FOLHA_DO_MAIN`, `:28`), `tests/test_qt_painel_da_galeria.py:482-639` (8, `GALERIA_DO_MAIN`) e
`tests/test_qt_tamanho_da_janela.py` (5, `GALERIA_DO_MAIN` e `RODAPE_DO_MAIN`, `:849`). Eles descrevem o
leiaute da Galeria, do rodapé e da folha de estilo que o merge do religa largou, nunca mais rodam, e contam
como testes. O motivo `RODAPE_DO_MAIN` diz que a conferência de 1.024 px continua sem medida.

**Solução.** Decisão D4 da solidez: apagar, ou reescrever contra o leiaute atual. A conferência de 1.024 px
vira item datado de qualquer jeito.

**Teste que falha primeiro.** Não há: o `grep` do aceite acha os 26 hoje.

**Aceite.** Nenhum `@unittest.skip` incondicional em `tests/` (guarda por `grep`).

## S-869 · As dezesseis guardas "sem tkinter" saem

**Problema** (confirmado). Dezesseis guardas só conferem `assertNotIn("tkinter", imports)`, e o Tk saiu:
`tests/test_viewport.py:178`, `test_board_model.py:369`, `test_editor_model.py:278`,
`test_page_overlay.py:303`, `test_qt_fita.py:51`, `test_qt_painel_da_galeria.py:65`,
`test_qt_painel_de_estudo.py:91`, `test_qt_painel_de_revisao.py:60`, `test_qt_painel_do_pdf.py:70`,
`test_qt_paleta.py:60`, `test_qt_texto_cauda.py:47`, `test_texto_exportacao.py:152`,
`test_texto_paleta.py:92`, `test_texto_rico.py:355`, `test_ui_comandos.py:615` e `test_ui_texto_cor.py:146`.
Nenhuma protege nada que já não esteja protegido: `tests/test_ui_fronteira.py:303`
(`test_nada_fora_do_pacote_de_desenho_importa_toolkit`) varre o pacote inteiro, menos `qt/`, contra `PyQt6`,
`PySide6`, `tkinter`, `ttkbootstrap` e `chess_diagram_ocr.qt`, e isso inclui `text/`. A docstring de
`SEM_TKINTER` (`tests/test_editor_model.py:433-443`) está velha. É a memória "guarda de varredura fica vácua
no corte".

**Solução.** Subtrair: as dezesseis saem, e a docstring de `SEM_TKINTER` é corrigida.

**Teste que falha primeiro.** Não há: a guarda que vale já existe e já acusa um `import PyQt6` em
`text/rico.py`.

**Aceite.** As dezesseis não existem mais, e um `import PyQt6` acrescentado a `text/rico.py` continua
reprovado pela guarda de fronteira.

## S-870 · Testes de texto da fonte trocados por testes de comportamento

**Problema** (confirmado). `tests/test_augment.py:114` passa se `"augment_version"` aparecer em qualquer
lugar de `Trainer.prepare`, comentário incluído; `:311-313` procura `torch.rand` e `random.random()` como
texto; `tests/test_labels.py:502` procura `"LabelStore"` em `label_origins`;
`tests/test_preprocess.py:173-175` confere a ordem da corrente pela posição de `self.config.X` no texto
(este sai com a S-843, que retira o normalizador).

**Solução.** Semente fixa e saída comparada (aumento); `labels.csv` lido por um remendo que conta a passagem
pelo `LabelStore`.

**Teste que falha primeiro.** Cada teste novo, rodado contra a regra quebrada com o comentário intacto: hoje
os antigos passam nesse caso.

**Aceite.** Os três que ficam reprovam com a regra quebrada e com o comentário intacto.

## S-871 · Guardas de varredura com piso, e o registro de comandos como catraca

**Problema** (confirmado). `tests/test_cli_errors.py:145-154` faz glob de `cli/*.py` procurando
`"\ndef main("`; se o caminho mudar, o glob volta vazio e o teste passa.
`tests/test_board_detection.py:151-162` varre só três módulos e não vê `importacao_de_imagens.py:743` (que
hoje já passa `warn_on_cap=False`: ampliar a varredura não acha defeito, mas impede o próximo).
`tests/test_ui_comandos.py:363-554` faz `assertEqual` contra 140 nomes literais (memória "teste não congela
lista do catálogo"). Os 7 pulos de `tests/test_docs.py:819-1005` em worktree ficam com a S-805, que lhes dá
a mesma âncora no checkout principal.

**Solução.** Cada varredura afirma quantos candidatos achou (`assertGreater(len(achados), N)`) e varre
`src/` inteiro. O registro de comandos vira `assertLessEqual(divergem, REGISTRADOS)` com um dicionário de
razões por entrada. Acrescentar um comando sem `rotulo_curto` já não reprova hoje; o que muda é que
**remover** um divergente deixa de reprovar, e acrescentar um divergente sem razão continua reprovando.

**Teste que falha primeiro.** A sabotagem do aceite: mover a pasta varrida, hoje, deixa as guardas verdes.

**Aceite.** Mover a pasta varrida reprova as guardas; remover um divergente não reprova o registro.

## S-872 · Testes de "não levanta" que conferem o efeito, e tempo escalável

**Problema.** Testes que passariam com a função vazia (confirmado): `tests/test_qt_menu.py:203`,
`test_qt_dica.py:52`, `test_qt_painel_de_recorte.py:149`, `test_qt_tabuleiro_editavel.py:124`,
`test_qt_rodape.py:222`, `test_engine.py:267`, `test_page_results.py:321`. Limites de relógio que podem
oscilar sob cobertura ou carga (plausível): `test_qt_fila_de_livros.py:174` e `test_qt_indice_da_base.py:98`
(menos de 1,5 s depois de um `qWait(100)`), `test_games_index.py:610`, `test_engine.py:152`,
`test_alinhamento.py:96`, `test_tablebase.py:286`, `test_decode.py:373`, `test_eco.py:229`,
`test_engine.py:126`, `test_qt_motor.py:315` e, o mais sensível à cobertura,
`test_processo_de_trabalho.py:97` (a thread principal parada menos de 40 ms); e o `_esperar` de
`test_qt_fila_de_livros.py:116` volta calado no estouro.

**Solução.** Cada teste de "não levanta" confere o estado depois da chamada. Os limites multiplicados por um
fator de ambiente (`CVOFF_FATOR_DE_TEMPO`, padrão 1, 3 sob cobertura). `_esperar` reprova no estouro.

**Teste que falha primeiro.** A sabotagem do aceite (o corpo trocado por `pass`) aplicada a cada um dos
sete: hoje eles passam.

**Aceite.** Trocar o corpo de cada função testada por `pass` reprova o seu teste, salvo onde o contrato é
justamente "não faz nada" (`test_page_results.py:321`, descartar página ausente; `test_qt_menu.py:203`;
`test_qt_rodape.py:222`, clique de cancelar sem cancelador): ali o teste confere que o estado ficou igual,
campo a campo. A suíte sob cobertura passa sem oscilar em três rodadas.

## S-873 · Os sobreviventes do mutator nos seis módulos-piloto

**Problema.** Depende da S-803: o `tools/qualidade/mutator.py` e o `docs/metrics/mutacao.json` ainda não
existem, e a lista de sobreviventes de `fen_utils.py`, `splits.py`, `decode.py`, `atomic_io.py`,
`settings.py` e `ui/legality.py` é o que a primeira rodada da S-803 produz.

**Solução.** Para cada sobrevivente: um teste que o mata, ou a remoção do código que ele mostra morto, ou a
declaração de mutante equivalente com a razão.

**Teste que falha primeiro.** A primeira rodada do mutator da S-803: cada sobrevivente é um teste que falta.

**Aceite.** O escore de cada módulo-piloto registrado em `docs/metrics/mutacao.json` acima de 90%, e nenhum
sobrevivente sem decisão escrita.

## S-886 · As funções de produção com CRAP acima de 100 ganham teste

**Problema** (confirmado pela cobertura). Fora de `cli/` e da S-881, nove funções de produção têm CRAP ≥
100: `app_pyqt.selftest` (complexidade 17, 0%: roda no CI do bundle, fora da suíte),
`qt/dialogos.DialogoDePartidas._repovoar` (16, 3%), `qt/__init__.dialogos_do_produto` (15, 4%),
`taticas.tabela_de_solucoes` (19, 22%), `text/leitor.linhas_do_glifo` (37, 53%; dividida na S-860),
`qt/painel_de_estudo.PainelDeEstudo.jogar_a_linha_do_livro` (13, 4%), `qt/__init__._apelidos` (12, 5%),
`qt/dialogos.DialogoDePartidas.procurar_por_nome` (11, 4%) e
`qt/painel_da_galeria.PainelDaGaleria._lote_terminou` (11, 5%). E `cli/games.main` (19%) e `_census` (4%)
são justamente o caminho do defeito da S-806, cujos testes os cobrem.

**Solução.** Um teste de comportamento por função, pelo caminho do usuário (`QTest` nos diálogos);
`selftest` exercitado na suíte com o bundle simulado.

**Teste que falha primeiro.** O teste novo de cada função, escrito contra o comportamento que o usuário vê;
o crapper da S-801 é a medida.

**Aceite.** As nove abaixo de CRAP 30 no `crap.json` da S-801.

## S-895 · A guarda de órfãos enxerga módulo sem `__all__`

**Problema** (confirmado por script). `tests/test_ui_orfaos.py:413-433`: `_exportados` devolve `[]` para
módulo sem `__all__`, que então nunca é varrido. São sete em `ui/` (`board_edit`, `busy`,
`estado_do_rodape`, `legality`, `page_results`, `state`, `strings`), e neles há nomes sem chamador:
`board_edit.apply_edits` e `counts_by_symbol`; em `strings`, `ORIENTATION_LABELS`, `ZOOM_DO_TABULEIRO`,
`ZOOM_DA_PAGINA`, `LIVRO_EM_PDF`, `CONJUNTO_DE_PECAS` e `ROTULOS_DA_CONFIGURACAO`;
`estado_do_rodape.SEVERIDADES`; e o método `DiagramEditorModel.mark_net_corrected`, que ninguém chama (o
lado do modelo da S-882). A guarda passa verde com teto 0 sobre o que enxerga. É a memória "guarda de
varredura fica vácua no corte".

**Solução.** Todo módulo de `ui/` declara `__all__` literal, e a guarda passa a exigi-lo. Os nomes sem
chamador acima saem ou ganham chamador (o de `mark_net_corrected` segue a decisão da S-882).

**Teste que falha primeiro.** `test_todo_modulo_de_ui_declara_all`, que hoje acusa os sete (o
`ui/__init__.py` fica isento, como `orfaos()` já faz).

**Aceite.** O teste passa; a catraca de órfãos continua em zero, agora sobre todos os módulos.
