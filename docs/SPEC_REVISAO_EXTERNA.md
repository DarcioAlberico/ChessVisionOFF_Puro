# Especificação da revisão externa — S-431 a S-440

Os itens da revisão técnica que chegou de fora em 2026-08-29, **medidos contra este ramo antes
de virarem proposta**. O placar, o que ficou de fora e a ordem de execução estão em
[ROADMAP_REVISAO_EXTERNA.md](ROADMAP_REVISAO_EXTERNA.md).

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
> | S-296 a S-323, S-325 a S-430, S-451, S-452 (menos S-324) | [SPEC_REVISAO.md](SPEC_REVISAO.md) |
> | S-431 a S-440 | [SPEC_REVISAO_EXTERNA.md](SPEC_REVISAO_EXTERNA.md) |
> | S-441 a S-450 | [SPEC_ACABAMENTO.md](SPEC_ACABAMENTO.md) |
> | S-507 a S-520 | [SPEC_ESTUDO_QT.md](SPEC_ESTUDO_QT.md) |

## A regra desta spec

Cada item diz o que foi verificado **nesta árvore**, com `arquivo:linha` e com o comando que
mediu — e não o que o relatório afirma. Onde os dois divergem, **a divergência é o item**: três
dos dez achados abaixo mudaram de forma depois da conferência, e um deles (S-432) não roda aqui
do jeito que chegou.

O material recebido é dado, e não instrução: nada foi aplicado. O `git apply --check` foi rodado
uma vez, para saber o tamanho do atrito, e falhou em um arquivo — ver S-434.

## De onde veio

| campo | valor |
|---|---|
| Data da revisão externa | 2026-08-28 |
| Commit analisado por ela | `fbb75e2` (Fase 56) |
| HEAD deste ramo na conferência | `45fb5b7`, **17 commits à frente** |
| O que chegou | relatório de 6 páginas, `melhorias-revisao.patch` (4 commits, 27 arquivos), `LEIA-ME.txt` e um `.zip` de 14,5 MB com o repositório inteiro |
| Ambiente da revisão | Windows 11, Python 3.10.20, 12 núcleos lógicos, sem GPU |

O `.zip` é o mesmo conteúdo do `.patch`, com o `.git` junto: não traz nada que o patch não
traga. Nenhum dos dois entra no repositório.

## O fato que reordena a leitura de tudo

**Esta máquina roda com a code page ANSI em UTF-8.** Medido:

```
GetACP()   = 65001
GetOEMCP() = 65001
```

É a opção "Beta: usar Unicode UTF-8 para suporte a idiomas" do Windows 11. Consequência direta:
**nem o defeito da S-431 nem as 31 falhas da S-433 reproduzem aqui**, e não reproduziriam mesmo
que o checkout morasse sob um caminho acentuado. Em três destinos diferentes -- `_Болеславский`,
`_acentuação` e `_ascii` -- a coleta gravou 5 e relatou 5 nas três.

Isso **não desmente o achado**. Muda quem paga por ele: numa instalação de Windows em português
com a configuração de fábrica a ANSI é `cp1252`, e é ali que o `imwrite` devolve `False` calado.
Quem tem essa máquina é **quem baixa o `.zip`** -- e não quem desenvolve. É a diferença entre um
defeito que não existe e um defeito que esta bancada não consegue ver.

E é o que torna as guardas dos itens abaixo mais importantes que as correções: uma guarda que
depende da code page da máquina passa verde aqui **antes e depois** do conserto, que é o defeito
da S-296 escrito outra vez.

---

## S-431 — A coleta grava pelo `write_image`, e o relatório para de poder mentir

**O defeito, e ele continua no HEAD.** `src/chess_diagram_ocr/text/coleta.py:241` grava com
`cv2.imwrite`, e a linha seguinte conta:

```python
for recorte in guardados:
    cv2.imwrite(str(alvo / recorte.nome()), np.asarray(recorte.imagem, np.uint8).reshape(LADO, LADO))
relatorio.por_pasta[chave] = len(guardados)
relatorio.gravados += len(guardados)
```
`src/chess_diagram_ocr/text/coleta.py:240-248`

`cv2.imwrite` devolve `False` em caminho que a code page ANSI não representa, **sem levantar**.
O `relatorio.gravados` soma `len(guardados)` sem olhar o retorno: ele conta o que ofereceu, e
diz que é o que gravou. O destino padrão é `PROJECT_ROOT / "revisao_ocr"` -- de modo que basta a
pasta do projeto, ou a do bundle que o usuário descompacta, morar sob um nome com acento.

É exatamente o acidente que o próprio projeto registra em dois lugares: o item 3 de
`src/chess_diagram_ocr/text/classes.py:16` (a pasta `lower_ä` que "ficou vazia") e o docstring
de `atomic_io.write_image`, escrito para impedir isto.

**O raio de dano é pequeno, e isso é bom.** `coletar` não tem chamador de produção hoje: só
`tests/test_texto_coleta.py` e a declaração de símbolo da S-214 em
`src/chess_diagram_ocr/text_status.py:184`. A troca de "devolve `False`" para "levanta `OSError`"
não pode derrubar tela nenhuma agora -- e é a hora certa de fazê-la, antes de existir chamador.

**A correção.** Duas linhas: `from ..atomic_io import write_image` no topo, e a chamada trocada.
Verificado nesta árvore que `write_image` aceita o array 2-D `(32, 32)` de `uint8` que a coleta
lhe dá, e que o PNG volta do disco idêntico no canal 0, sob destino cirílico.

**O teste que chegou é vácuo aqui, e o item é o teste.** O
`DestinoForaDaCodePageTests` proposto afirma `relatorio.gravados == len(no_disco)` sob um
destino cirílico. Nesta máquina isso é verdade **antes e depois** da correção -- guarda que
passa verde sobre o defeito, que é o nome da S-296. A spec pede três testes, e o primeiro é o
que não depende de máquina:

1. `test_a_gravacao_passa_pelo_atomic_io` — com `mock.patch` em `coleta.write_image`, afirmar
   que ele foi chamado uma vez por recorte guardado. Falha na hora em que alguém devolver
   `cv2.imwrite` ao arquivo, em qualquer code page.
2. `test_uma_gravacao_que_falha_nao_vira_relatorio` — `write_image` levantando `OSError`,
   afirmar que `coletar` **propaga** em vez de devolver um `Relatorio` com contagem. É a
   afirmação de que o relatório não pode mentir, escrita sobre o mecanismo e não sobre o disco.
3. `test_o_recorte_volta_do_disco_com_o_conteudo_que_entrou` — o round-trip sob destino
   cirílico, como veio. Fica: é de graça, e numa máquina de fábrica ele é o teste de verdade.

O docstring da classe tem de dizer que o (3) é o único dos três que depende da code page, senão
alguém lê o verde dele como prova.

**Custo:** 2 linhas de código, ~40 de teste.

---

## S-432 — A lei do `imread`/`imwrite` vira guarda, e a guarda pergunta ao git quem é o repositório

**A ideia está certa, e é o melhor achado do lote.** A proibição de `cv2.imread`/`cv2.imwrite`
está escrita em três docstrings -- `text/dataset.py:27`, `cli/texto_inventario.py:20` e o
cabeçalho de `tests/test_image_io.py` -- e verificada por dois testes que leem o **texto de dois
módulos** (`tests/test_texto_inventario.py:103` e `tests/test_text_dataset.py:91`). Uma lei que
olha dois arquivos não é uma lei: `text/coleta.py` violava desde a S-201 e nenhum dos dois
olhava para lá.

A guarda proposta varre a árvore sintática de todo `.py` e recusa a chamada em qualquer arquivo.
Por `ast` e não por `grep`, porque metade das ocorrências no repositório são docstrings que
explicam a proibição -- e essa parte do desenho está certa.

**A implementação que chegou não roda nesta árvore.** Ela caminha com `os.walk` a partir da raiz
e poda um conjunto fixo (`.venv`, `venv`, `build`, `dist`, `.git`, `__pycache__`,
`site-packages`). Rodada aqui:

| medida | proposta (`os.walk` da raiz) | com `git ls-files` |
|---|---|---|
| arquivos `.py` varridos | 2.207 | 430 |
| tempo | 21,2 s | 0,27 s |
| violações acusadas | **168** | 22 |
| morre antes de terminar? | **sim** | não |

Duas causas, e as duas são pastas que este projeto tem e o clone da revisão não tinha:

- **`.claude/worktrees/`** — sete checkouts de sessões concorrentes, com o mesmo código. São
  **147 das 168** violações. A guarda acusaria para sempre, e o conserto seria impossível: o
  arquivo apontado não é deste ramo.
- **`Ideias para implementar na aba 'Texto'/`** — projeto de terceiro que `.gitignore:171` já
  exclui. O `ast.parse` levanta `TabError` ali (`Text-Editor-master/main.py`, linha 92), e a
  guarda proposta não tem `try`: o teste **dá erro**, não falha. Erro de guarda não se lê como
  achado, se lê como suíte quebrada.

**A correção: o repositório é o que o git diz que é.**

```python
subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "*.py"], ...)
```

Medido: 430 arquivos, 271 ms, zero entradas de `.claude/` e zero de `Ideias`. O `--others
--exclude-standard` é o que faz a guarda ver o arquivo **novo e ainda não commitado** -- sem ele
bastaria não dar `git add` para escapar da lei. E a lista honra `.gitignore` e
`.git/info/exclude` de graça, que é a definição de "o que é este repositório" que o projeto já
mantém.

**A poda continua sendo a resposta certa quando não há git.** Fora de um checkout -- um sdist
desempacotado -- `git ls-files` devolve vazio ou erra, e a guarda tem de saber a diferença entre
"nenhuma violação" e "não olhei nada". Duas afirmações:

- vazio ou `git` ausente ⇒ `skipTest` com a frase dizendo por quê, e nunca verde silencioso;
- `test_a_varredura_alcanca_o_codigo_todo` — a lista tem de conter `app_tkinter.py`,
  `coleta.py`, `atomic_io.py`, `build_windows.py` e `gerar.py`. Veio no patch e é o melhor
  detalhe dele: é a guarda da guarda, e é o que a S-296 ensinou.

**O que a guarda protege que o job de CI da S-437 não protege.** `áéíóúç` cabem em `cp1252`, e
ali o `fopen` estreito funciona: um runner de locale ocidental **não** vê a família do `cv2`.
Esta guarda é estrutural e vê sempre. Se apenas um dos dois entrar, entra este.

**Custo:** ~60 linhas de teste novo, em `tests/test_image_io.py`.

---

## S-433 — As 22 chamadas de `cv2.imread`/`imwrite` que sobraram nos testes

**A contagem, conferida nesta árvore** (varredura por `ast`, fora dos worktrees):

| arquivo | chamadas |
|---|---|
| `src/chess_diagram_ocr/text/coleta.py` | 1 *(é a S-431)* |
| `tests/test_audit.py` | 5 |
| `tests/test_training.py` | 3 |
| `tests/test_dataset.py` | 2 |
| `tests/test_falso_positivo_vence.py` | 2 |
| `tests/test_provenance.py` | 2 |
| `tests/fixtures/gerar.py` | 1 |
| `tests/test_board_detection.py` | 1 |
| `tests/test_board_head.py` | 1 |
| `tests/test_dataset_browser.py` | 1 |
| `tests/test_dataset_cache.py` | 1 |
| `tests/test_experiments.py` | 1 |
| `tests/test_fixtures.py` | 1 |
| **total** | **22, em 13 arquivos** |

**O que isso custa numa máquina de fábrica.** As quatro leituras -- `test_board_detection`,
`test_falso_positivo_vence` (duas) e `test_fixtures` -- devolvem `None` num checkout sob caminho
acentuado, e `None` é **o mesmo valor que significa "arquivo não existe"**. A mensagem que
aparece é `Fixture ausente: refaça com tests/fixtures/gerar.py`, apontando para um fixture que
está no lugar. São 31 falhas somadas às oito da S-434, e a CI, que roda sob `D:/a/...`, nunca
pôde ver nenhuma.

**A correção** é mecânica: `read_image` / `write_image` de `atomic_io`, que devolvem e levantam
o que deveriam. Um detalhe não é mecânico e o patch acertou: em `tests/test_audit.py` o import
precisa de alias.

```python
def add(self, name: str, fen: str, *, image: np.ndarray | None = None, write_image: bool = True) -> None:
```
`tests/test_audit.py:57`

O parâmetro já se chama `write_image`. Importar a função com o nome nu a sombreia dentro do
método, e a chamada vira `TypeError: 'bool' object is not callable`. Vai como
`write_image as gravar_imagem`, com o comentário dizendo por quê -- senão alguém "limpa" o
alias.

**A ordem importa: S-432 antes de S-433.** Escrever a guarda primeiro faz a suíte ficar vermelha
com a lista exata dos 22 lugares, e o conserto vira riscar itens de uma lista que o computador
escreveu. O contrário -- consertar e depois escrever a guarda -- deixa a guarda nascer verde, e
guarda que nunca falhou é guarda que ninguém provou.

**Custo:** 22 substituições em 13 arquivos, mais 13 linhas de import.

---

## S-434 — O `.bat` do motor falso vai na code page OEM

**O defeito.** `tests/test_engine.py:46` grava o lançador em UTF-8:

```python
caminho.write_text(f'@echo off\n"{sys.executable}" "{MOTOR_FALSO}" %*\n', encoding="utf-8")
```

O `cmd.exe` lê arquivo de lote pela **code page do console**, que numa máquina brasileira de
fábrica é `cp850`. O acento de `sys.executable` -- e num Python gerenciado pelo `uv` o
interpretador mora dentro do perfil do usuário -- vira mojibake dentro do `.bat`, e os oito
testes da classe morrem com `EngineTerminatedError: engine process died unexpectedly`.

**Nesta máquina é um no-op**, e vale dizer: `GetOEMCP()` também devolve 65001 aqui, então
`encoding="oem"` e `encoding="utf-8"` produzem os mesmos bytes. A troca é segura de qualquer
lado e correta do outro. O codec `oem` existe desde o Python 3.6 no Windows; verificado.

**O patch não aplica neste ponto, e é o único ponto.** `git apply --check` sobre o HEAD deste
ramo falha em um arquivo só:

```
error: patch failed: tests/test_engine.py:39
error: tests/test_engine.py: patch does not apply
```

A causa é nossa e é benigna: `_launcher` ganhou o parâmetro `caso` e passou a usar
`pasta_temporaria_da_classe` num dos 17 commits desde `fbb75e2`. A resolução é reescrever a
linha à mão. Os outros 26 arquivos aplicam com deslocamento.

**O limite, que é do `cmd.exe` e não daqui.** Caminho com caractere fora da code page OEM
-- cirílico, que é o caso do acervo e o que quebrou na S-111 -- não cabe num `.bat` de jeito
nenhum: o `encode` levanta, em vez de gravar lixo, que é a falha certa. A saída, se isso
aparecer, é fugir do `cmd`: `popen_uci` aceita **lista** de argumentos, e
`[sys.executable, str(MOTOR_FALSO)]` dispensa o arquivo de lote inteiro. Fica registrado aqui e
não feito agora, porque mexe em oito testes para resolver um caso que ninguém viu.

**Custo:** 1 palavra.

---

## S-435 — As duas conexões SQLite que o `with` não fecha

**O defeito, verificado aqui.** `with sqlite3.connect(...)` **não fecha a conexão**: o
`__exit__` do módulo comita ou desfaz a transação, e é tudo. Medido nesta máquina:

```
conexao AINDA ABERTA depois do `with` -> confirmado
rmtree FALHOU: [WinError 32] O arquivo já está sendo usado por outro processo: ...cache.sqlite
```

Os dois lugares:

- `tests/test_database_choice.py:98`
- `tests/test_games_cache.py:322`

**Por que passa verde hoje.** O handle fica aberto, mas o nome local sai de escopo no fim do
método e a contagem de referências do CPython fecha a conexão antes de o `TemporaryDirectory`
limpar. É sincronia, não garantia -- e no 3.13 ela deixou de valer, que é como a revisão
esbarrou nisso. No 3.10 o mesmo defeito já aparece como os `PytestUnraisableExceptionWarning`
que a suíte cospe no fim de cada execução.

`tests/test_games_index.py` tem cinco `sqlite3.connect` sem `with`, e **todos fecham
explicitamente** (`conexao.close()`). Não são afetados. A revisão acertou o alvo.

**A correção:** `contextlib.closing` nos dois. Duas linhas de `import`, duas de chamada.

**Vale por si, e não só pela S-436.** Mesmo que a faixa de Python não mude, isto tira quatro
avisos que a suíte emite a cada execução -- e aviso que sempre aparece é aviso que ninguém lê.

**Custo:** 4 linhas.

---

## S-436 — A faixa de Python vai de 3.10 a 3.13

**O prazo é a razão, e ele é curto.** `pyproject.toml:6` traz `requires-python = "==3.10.*"`. O
Python 3.10 sai de suporte em **outubro de 2026** -- daqui a cerca de dois meses -- e o bundle
do PyInstaller **embarca o interpretador**. Manter o pino deixa de ser conservadorismo e passa a
ser distribuir um Python sem correção de segurança para quem baixa o `.zip`.

O `ROADMAP.md` já registrava a decisão de relaxar "quando houver motivo". O motivo é este, e tem
data.

**O que a revisão mediu antes de propor:** no 3.13.14 a suíte inteira passa (4.582 testes),
`ruff` e `mypy` limpos, e o `uv lock` re-resolvido não mexeu em nenhuma versão de terceiro. O
custo total da migração foram as quatro linhas da S-435.

**O que esta casa mediu por conta própria.** O `uv.lock` que veio no patch tem 875 linhas de
diferença e foi resolvido **na máquina deles**. Um lock é o estado do resolvedor no momento em
que rodou; aceitá-lo de fora é aceitar uma resolução que ninguém aqui viu. Então o lock do patch
foi descartado e o `uv lock` rodou aqui, com `uv 0.11.19`:

```
Resolved 122 packages in 932ms
pacotes antes: 122  depois: 122
versoes que se moveram: NENHUMA
uv.lock | 871 +++++ 6 ---
```

As 871 linhas novas são as entradas de wheel dos interpretadores que a faixa passou a aceitar --
nenhuma versão de terceiro mudou. A conferência é `name`/`version` de todos os 122 pacotes, e
não o olho no diff: um diff de 871 linhas esconde uma linha trocada com facilidade.

**O que fica como está, de propósito:**

- `.python-version` continua em 3.10 -- é o padrão de quem só roda `uv sync`.
- `ruff` (`py310`) e `mypy` (`python_version = "3.10"`) continuam mirando a ponta velha: quem
  lima é ela. Sintaxe de 3.11+ que entrasse sem aviso quebraria na máquina de quem não atualizou.
- O teto em `<3.14` é deliberado. Faixa aberta deixaria o `uv` resolver para uma versão que
  ninguém rodou, e a CI só prova as pontas que roda.

**A ressalva honesta, que veio deles e continua valendo.** Numa das execuções o interpretador
3.13 entregue pelo `uv` veio com o Tk incompleto e **14 testes de janela pularam em vez de
rodar**. A janela é o produto. Promover o 3.13 a padrão do bundle depende de abrir a janela numa
máquina de verdade -- e é por isso que este item para na faixa e no `pyproject.toml`, sem tocar
no `.python-version`.

**Custo:** 1 linha de `pyproject.toml`, um `uv lock` re-resolvido aqui, três frases de README e
`CONTRIBUTING.md`. Depende de S-435.

---

## S-437 — A CI prova as duas pontas da faixa, e um caminho acentuado

**O estado atual.** `.github/workflows/ci.yml` tem **um** job (`check`), sem matriz, numa versão
só de Python e sempre sob caminho ASCII. O `on:` já foi corrigido pela S-296 e dispara em todo
ramo -- essa metade está feita.

Uma faixa `>=3.10,<3.14` provada por uma versão só é promessa sem lastro. São duas mudanças:

**1. Matriz `3.10` / `3.13`, com `UV_PYTHON` e não `--python`.** É o detalhe que decide, e a
revisão o registra como furo que apareceu dentro da própria correção: com a flag apenas no
`uv sync`, o `uv run` seguinte volta a ler o `.python-version` (3.10) e a perna do 3.13 rodaria
3.10 **em silêncio** -- guarda que não olha o que devia, a S-296 outra vez. A variável de
ambiente vale para todo comando `uv` do job, e vai acompanhada de um passo que **reprova** se o
interpretador não for o pedido. Matriz que não prova a versão é decoração.

`ruff` e `mypy` rodam só na perna 3.10 (`if: matrix.python == '3.10'`): os dois estão
configurados para `py310`, a análise seria idêntica nas duas pernas e a segunda pagaria o dobro
pelo mesmo resultado.

**2. Um job que faz o checkout num diretório acentuado** (`path: "acentuado-áéíóúç"`), com o
`fetch-depth: 0` que `tests/test_docs.py` exige.

**O limite deste job, e ele é grande o bastante para mudar a prioridade.** Ele pega a família do
`cmd`/OEM da S-434 -- `á` em UTF-8 são dois bytes, lidos como `cp437` dão dois caracteres de
lixo, e o motor não sobe. Ele **não** pega, num runner de locale ocidental, a família do
`cv2`/ANSI: `áéíóúç` cabem em `cp1252` e ali o `fopen` estreito funciona. Essa família está
coberta pela guarda estrutural da S-432, que é mais forte que sondar um caminho.

Ou seja: **este job existe para o que ninguém previu**, e não para os defeitos que a revisão
achou. Se só um dos dois entrar, entra a S-432.

**O que ele custa.** A perna extra da matriz mais o job acentuado quase dobram o tempo de CI de
cada push -- e este projeto empurra em todo ramo desde a S-296. É o item mais caro do lote em
minuto de máquina, e o único cujo benefício é probabilístico.

**Custo:** ~83 linhas de YAML. Depende de S-436 (a matriz sem a faixa não faz sentido).

---

## S-438 — O `bundle.json` diz de que ambiente saiu o número

**O laço não fecha, e dá para ver daqui.** `docs/metrics/bundle.json` tem quatro campos:

```json
{ "mb": 684, "arquivos": 4275, "data": "2026-08-18", "commit": "9a683d1" }
```

`packaging/build_windows.py` sobrescreve esse arquivo; `tests/test_docs.py` compara o arquivo
com o número que `README.md:62` publica (**684 MB, 4.275 arquivos**). Rodar o comando que o
próprio README manda rodar deixa a árvore suja e a suíte vermelha, com um
`AssertionError: (570, 4039) != (684, 4275)` que não diz o que fazer.

**E o par nem era comparável.** O README já conta a história: o PyInstaller coleta o que está
**instalado**, e não o que o `pyproject.toml` declara -- foi assim que `pythonnet` e
`clr_loader` ficaram dentro do bundle muito depois de a S-69 remover o código que os usava. A
conclusão que faltava tirar é que **o tamanho é função da venv**, não só do commit: os 114 MB
entre aqueles dois builds do *mesmo* commit eram os extras `onnx` e `ocr` presentes num e
ausentes no outro. Sem registro, isso se lê como regressão.

**Três mudanças, e nenhuma afrouxa a guarda:**

1. `bundle.json` ganha `extras`, detectado do ambiente -- cada extra declarado cujas
   distribuições estão todas instaladas. O `commit` dizia de que código; o `extras` diz de que
   ambiente.
2. `build_windows.py` avisa **na hora** em que o build envelheceu o README, com o número novo, o
   arquivo a corrigir e os extras desta venv. Quem mede é quem sabe o número.
3. A mensagem de falha do teste passa a nomear data, commit e extras do que foi gravado, e
   aceita `bundle.json` antigo sem o campo.

**A ressalva:** o leitor de extras é o **terceiro** parser de TOML escrito à mão neste
repositório (`tests/test_docs.py` e `text_status._extras_do_pyproject` são os outros dois), e
pelo mesmo motivo -- `tomllib` é 3.11+ e a faixa começa no 3.10. É consistente com o que a casa
já faz, e não deixa de ser uma dívida: quando o piso da faixa subir para 3.11, os três viram um
`tomllib`. Anotar aqui é o que faz esse dia acontecer.

**Custo:** ~104 linhas em `packaging/build_windows.py`, ~60 de teste novo, 20 em
`tests/test_docs.py`.

---

## S-439 — Um QUICKSTART de 60 linhas ao lado do README de 1.181

**O número, conferido:** `README.md` tinha **1.181 linhas** quando este item foi escrito. Ele
responde *por que* cada decisão foi tomada e o que ela custou, e não há o que cortar nele -- é o
maior patrimônio deste repositório. Mas é a primeira coisa que alguém novo abre, e "como começo"
fica diluído.

O `QUICKSTART.md` proposto responde só isso, em 59 linhas: instalar, pôr os arquivos no lugar,
abrir, o ciclo *corrigir → salvar → treinar*, e os dois avisos que economizam uma hora (o
executável não assinado, e as pastas graváveis ficarem **ao lado** do executável para que
reinstalar não apague o `labels.csv`). Todo o resto aponta de volta para o README.

**Fica na raiz, e não em `docs/`, de propósito.** `tests/test_docs.py::test_todo_documento_
aparece_no_readme` exige que todo `docs/*.md` apareça no índice do README -- promessa que este
arquivo não deve fazer, porque ele é vizinho do README e não documentação técnica.

**Duas conferências que a revisão passou:**

- "os outros **39** comandos" está certo: o `pyproject.toml` declara 40 `cvoff-*`, e a frase vem
  depois de nomear o `cvoff-infer`. Nenhum teste cobre esse número dentro do QUICKSTART -- só a
  contagem do README é guardada --, então ele é uma frase que pode envelhecer calada. **Foi
  escrita sem número**: "e os outros comandos de linha -- o README os lista". Um número que
  nenhuma guarda cobre é um número que mente sozinho.
- Os códigos de saída do `--selftest` (`0` ok, `2` sem PDF, `3` sem checkpoint, `4` lê mas não
  treina, `1` não reconheceu) batem com o que o README documenta.

**A dependência:** o QUICKSTART diz "Requer Python 3.10 a 3.13". Se ele entrar **antes** da
S-436, essa linha tem de dizer 3.10 e ser corrigida depois. É o tipo de detalhe que vira um
documento mentindo por um mês.

**Custo:** 59 linhas novas, 3 no README.

---

## S-440 — A varredura paralela, medida e recusada

**Este item não implementa nada. Ele existe para que a proposta não volte.**

A revisão inicial sugeriu paralelizar a varredura de páginas, com base num ganho medido de
**2,38×**. O número estava certo e a conclusão estava errada: ele mediu **apenas a detecção**. O
perfil real de uma página, na máquina da revisão:

| etapa | fatia do tempo de página |
|---|---|
| Renderização do PDF | 0,4 % |
| Detecção do tabuleiro | 1,1 % |
| **Inferência** | **98,5 %** |

A inferência é o gargalo, e o `torch` já distribui esse trabalho por todos os núcleos. O teste
decisivo -- mesmo trabalho, em regime equivalente a um livro de 120 páginas:

| configuração | tempo | ganho |
|---|---|---|
| 1 processo, 12 threads *(como é hoje)* | 25,15 s | — |
| 4 processos, 3 threads | 24,41 s | 1,03× |
| 6 processos, 2 threads | 27,45 s | 0,92× |
| 12 processos, 1 thread | 29,26 s | 0,86× |

Não há ganho: o modelo é limitado por banda de memória, não por núcleos. Implementar custaria
pool de processos, buffer de reordenação -- justamente o defeito que este projeto já teve de
corrigir entre interface e exportação --, IPC de cerca de 1,9 MB por diagrama e cerca de 300 MB
de RSS por worker, para 0,86×–1,03×.

**O que não transfere e o que transfere.** Os tempos são de CPU da máquina da revisão (12
núcleos lógicos, sem GPU) e **não valem para outra máquina** -- inclusive esta. O que transfere
é a forma do argumento: *o ganho de 2,38× foi medido sobre 1,1% do tempo*. Qualquer proposta
futura de paralelismo tem de medir o pipeline inteiro antes de virar item, e este parágrafo é
onde ela vai bater.

**Decisão: não implementar.** Se alguém quiser reabrir, o caminho é medir a inferência com uma
GPU presente -- é a única mudança que reordena a tabela acima.

**Custo:** zero. É registro.
