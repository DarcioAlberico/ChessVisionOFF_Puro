"""As regras da própria suíte, cobradas por teste em vez de por convenção (Fase 65).

Quatro mil setecentos e setenta e seis testes verdes, e setenta defeitos de correção. A fase não
pediu cobertura: pediu que a suíte alcançasse as três formas em que o relatório encontrou defeito
-- **o que vaza** (thread, pasta temporária, painel), **o que trava** (uma caixa modal de verdade)
e **o que some** (um teste que pula para sempre e ninguém conta).

As regras que este arquivo cobra já estavam escritas -- em `tests/tk_root.py`, no docstring de
`_painel` do editor, no `conftest`. Estar escrita é o que elas eram, e por isso valiam enquanto
alguém lembrava. Aqui elas passam a falhar.
"""

from __future__ import annotations

import ast
import inspect
import io
import shutil
import subprocess
import textwrap
import tokenize
import unittest
from pathlib import Path

from ambiente_de_teste import pasta_temporaria
from subprocesso import rodar_python

RAIZ = Path(__file__).resolve().parents[1]
TESTES = Path(__file__).resolve().parent

MODULOS = sorted(p for p in TESTES.glob("*.py") if p.name != "conftest.py")
"""Todo módulo de teste, mais os ajudantes. O `conftest` fica de fora: ele é o mecanismo."""


def _arvore(caminho: Path) -> ast.Module:
    return ast.parse(caminho.read_text(encoding="utf-8"))


class UmaRaizSoTests(unittest.TestCase):
    """Nenhum teste cria a própria aplicação Qt (S-416/S-506).

    **A regra é de 2026-07 e vinha do Tk**: com duas raízes vivas ao mesmo tempo havia dois
    interpretadores Tcl, e uma `PhotoImage` criada sem `master` nascia no errado -- o Tk recusava
    a imagem com uma mensagem que parecia coleta de lixo, e foi assim que 20 testes falharam só na
    CI. **Nove módulos criavam a sua assim mesmo**, cada um com o mesmo `try/except` copiado.

    **No Qt a regra é mais dura, não menos.** Uma segunda `QApplication` no mesmo processo não dá
    mensagem nenhuma: o Qt **aborta**, e o pytest imprime os pontos que já tinha e morre sem
    resumo e sem nomear o teste. `tests/qt_app.aplicacao()` devolve a única, e é ela que todo
    teste de widget usa.
    """

    def test_nenhum_modulo_de_teste_cria_a_aplicacao(self) -> None:
        proprios = [
            f"{caminho.name}:{no.lineno}"
            for caminho in MODULOS
            if caminho.name != "qt_app.py"
            for no in ast.walk(_arvore(caminho))
            if isinstance(no, ast.Call)
            and ast.unparse(no.func) in ("QApplication", "QtWidgets.QApplication", "tk.Tk", "tkinter.Tk")
        ]
        self.assertEqual(
            [],
            proprios,
            "Aplicação Qt própria num teste. Chame `qt_app.aplicacao()` -- uma segunda "
            "`QApplication` aborta o processo sem exceção.",
        )

    def test_a_raiz_compartilhada_continua_existindo(self) -> None:
        """A guarda acima ficaria vácua se `qt_app` deixasse de oferecer a aplicação."""
        self.assertIn("def aplicacao(", (TESTES / "qt_app.py").read_text(encoding="utf-8"))


class NadaVazaDoTesteTests(unittest.TestCase):
    """Pasta temporária, widget e arquivo morrem com o teste que os criou (S-415).

    Cada rodada abandonava **mais de cem** diretórios em `%TEMP%` e pendurava 99 `TextoPanel` na
    mesma raiz, nenhum destruído. Nada disso reprova um teste: apodrece a máquina de quem roda a
    suíte, e some do relatório porque tudo está verde.

    Os dois primeiros a rodada ao menos leva embora quando acaba. O terceiro não: um arquivo
    gravado em `data/` fica na árvore de trabalho depois que o pytest sai, e a última guarda
    daqui é sobre ele.
    """

    PAIS_QUE_SAO_A_RAIZ = frozenset({"_RAIZ", "self.root", "cls.root", "raiz()", "raiz_do_processo()"})
    """O que **não** pode ser o pai de um widget de teste: a raiz do processo inteiro."""

    def test_mkdtemp_so_mora_no_ajudante(self) -> None:
        """Uma pasta criada à mão é uma pasta que ninguém apaga -- foi assim 24 vezes."""
        soltos = [
            f"{caminho.name}:{no.lineno}"
            for caminho in MODULOS
            if caminho.name != "ambiente_de_teste.py"
            for no in ast.walk(_arvore(caminho))
            if isinstance(no, ast.Call) and ast.unparse(no.func).endswith("mkdtemp")
        ]
        self.assertEqual(
            [],
            soltos,
            "`mkdtemp` fora de `tests/ambiente_de_teste.py`. Use `pasta_temporaria(self)`, que "
            "registra a remoção no `addCleanup` -- ou `TemporaryDirectory()` num `with`.",
        )

    def test_nenhum_painel_pendura_na_raiz(self) -> None:
        """Painel na raiz vive até o fim da suíte, com os `after` e os `bind_all` dele."""
        pendurados = [
            f"{caminho.name}:{no.lineno} {no.func.id}"
            for caminho in MODULOS
            for no in ast.walk(_arvore(caminho))
            if isinstance(no, ast.Call)
            and isinstance(no.func, ast.Name)
            and no.func.id.endswith("Panel")
            and no.args
            and ast.unparse(no.args[0]) in self.PAIS_QUE_SAO_A_RAIZ
        ]
        self.assertEqual(
            [],
            pendurados,
            "Painel pendurado na raiz compartilhada. Use `quadro(self, raiz)` de "
            "`tests/ambiente_de_teste.py`: destruir quadro é seguro, destruir raiz é que não é.",
        )

    def test_o_conftest_continua_vigiando_o_data_de_verdade(self) -> None:
        """A terceira coisa que vaza de um teste é um arquivo, e essa não morre com a rodada.

        **O caso, de 2026-08-31:** um teste novo chamou `save_index(livro)` e `GalleryModel.save()`
        sem dizer onde gravar, e os dois resolvem `data/gallery/` na definição do argumento -- a
        rodada gravou dois arquivos na árvore do usuário e terminou verde. Uma varredura daqui
        pegaria a primeira chamada e não a segunda: no `GalleryModel` quem grava é um campo posto
        na construção, a suíte constrói vinte modelos sem ele que nunca gravam, e o teste que
        grava direito põe o campo por atribuição depois. Não há forma sintática que separe os
        três, e por isso a guarda é do `conftest` e olha o efeito.

        Esta linha é o que impede que ela seja removida sem que ninguém note. `PROJECT_ROOT` está
        cobrado junto de propósito: a guarda tem de vigiar a pasta que o **código** resolve, e não
        a que fica sob `RAIZ`. Num worktree as duas coincidem, e é aí que trocar uma pela outra
        passa despercebido -- a S-218 já foi vácua exatamente assim.
        """
        conftest = (TESTES / "conftest.py").read_text(encoding="utf-8")
        self.assertIn("nada_novo_no_data_de_verdade", conftest)
        self.assertIn("PROJECT_ROOT", conftest, "a guarda tem de vigiar a pasta que o código resolve")


class NenhumaCaixaDeVerdadeTests(unittest.TestCase):
    """A pergunta que trava a suíte, impedida antes de acontecer (S-414).

    **O caso medido:** um `TextoPanel` sem `pasta_de_rascunhos` lê `data/rascunhos/` da máquina de
    quem roda a suíte. Se houver um rascunho ali -- e há, na máquina de quem usa o programa -- a
    aba oferece recuperá-lo com um `askyesno`, e a suíte fica parada esperando um clique que
    ninguém vai dar. Nada impedia, e nada interrompia.

    A interrupção é do `conftest`, que troca as sete caixas por uma que falha dizendo o título. A
    prevenção é esta: quem constrói a aba num teste diz onde ficam os rascunhos, e a pergunta não
    tem por que aparecer.
    """

    def test_todo_TextoPanel_de_teste_declara_a_pasta_de_rascunhos(self) -> None:
        sem_pasta = [
            f"{caminho.name}:{no.lineno}"
            for caminho in MODULOS
            for no in ast.walk(_arvore(caminho))
            if isinstance(no, ast.Call)
            and isinstance(no.func, ast.Name)
            and no.func.id == "TextoPanel"
            and "pasta_de_rascunhos" not in {argumento.arg for argumento in no.keywords if argumento.arg}
        ]
        self.assertEqual(
            [],
            sem_pasta,
            "`TextoPanel` de teste sem `pasta_de_rascunhos=`: ele lê a pasta de rascunhos da "
            "máquina, e um rascunho de verdade ali abre a pergunta de recuperação no meio da "
            "suíte -- que fica parada esperando um clique.",
        )

    def test_o_conftest_continua_desarmando_as_caixas(self) -> None:
        """A guarda acima é a prevenção; sem a interrupção, o próximo caminho novo trava de novo."""
        conftest = (TESTES / "conftest.py").read_text(encoding="utf-8")
        self.assertIn("nenhuma_caixa_modal_de_verdade", conftest)
        self.assertIn("QMessageBox", conftest)
        self.assertIn("question", conftest)


class UmSubprocessoSoTests(unittest.TestCase):
    """Quem lança Python de fora do pytest usa o mesmo ambiente (S-419).

    Eram quatro testes e quatro maneiras de fazer o filho enxergar o pacote: nenhuma, `sys.path`
    mais diretório de trabalho, `PYTHONPATH`, e o caminho escrito dentro do roteiro gerado. Três
    funcionam neste checkout e nenhuma delas funciona nas mesmas condições -- num `git worktree` a
    primeira importa o pacote do **outro** checkout e mede outro código.
    """

    PERMITIDOS = {
        "subprocesso.py": "é o ajudante: é ele que monta o ambiente",
        "test_environment.py": "mede a instalação **sem** PYTHONPATH, e a razão está no docstring de lá",
        "test_docs.py": "chama `git`, e não Python",
        "test_field_eval.py": "chama `git`, e não Python",
        "test_disciplina_da_suite.py": "esta varredura, que chama `git ls-files`",
    }
    """Quem pode chamar `subprocess` direto, com o motivo -- a exceção é declarada, como sempre."""

    def test_ninguem_lanca_python_por_fora_do_ajudante(self) -> None:
        soltos: list[str] = []
        for caminho in MODULOS:
            if caminho.name in self.PERMITIDOS:
                continue
            for no in ast.walk(_arvore(caminho)):
                if not isinstance(no, ast.Call) or not ast.unparse(no.func).startswith("subprocess."):
                    continue
                argumentos = ast.unparse(no.args[0]) if no.args else ""
                if "sys.executable" in argumentos:
                    soltos.append(f"{caminho.name}:{no.lineno}")
        self.assertEqual(
            [],
            soltos,
            "Subprocesso Python fora de `tests/subprocesso.py`. Use `rodar_python` ou "
            "`rodar_roteiro`: o filho tem de enxergar o mesmo `src/` que o pai.",
        )

    def test_a_lista_de_excecoes_nao_cobre_quem_nao_existe(self) -> None:
        ausentes = sorted(nome for nome in self.PERMITIDOS if not (TESTES / nome).exists())
        self.assertEqual([], ausentes, "A lista de exceções cita um módulo que não existe mais.")


class PuloQueNinguemContaTests(unittest.TestCase):
    """O que a suíte deixa de rodar tem de ser visível (S-417).

    **Os testes de "números vivos" da S-135 pulam sempre na CI**, porque olham `data/samples/`,
    `PDF/` e `pgn_database/` -- que não são versionados. Um teste que pula para sempre é um teste
    que não existe, e a única diferença é que ele aparece na contagem de verdes.

    As duas metades: `-ra` no `pyproject.toml` faz **todo** pulo aparecer com o motivo na saída de
    qualquer rodada; e a lista abaixo garante que o que **é** versionado esteja lá, para que essas
    guardas não possam pular nem aqui nem na CI.
    """

    VERSIONADOS = {
        "data/labels.csv": "o número de rótulos que a ARCHITECTURE publica (S-135)",
        "data/splits.csv": "a partição que o treino e o campo leem",
        "data/field_set.jsonl": "as páginas anotadas à mão da avaliação de campo (S-41)",
        "models/char_meta.json": "as 314 classes que o README cita (S-406)",
        "assets/lexico/acervo.txt.gz": "uma das três listas do dicionário (S-408)",
        "assets/lexico/idioma.txt.gz": "idem",
        "assets/lexico/nomes.txt.gz": "idem",
        "docs/metrics/texto_pagina.json": "o CER de página que o README publica (S-405)",
        "packaging/cvoff.spec": "o `.spec` que o `ruff` linta desde a S-391",
    }
    """O que a suíte lê **e** o repositório versiona. Nenhuma guarda que dependa deles pode pular."""

    def test_o_que_as_guardas_leem_esta_versionado(self) -> None:
        rastreados = subprocess.run(
            ["git", "ls-files", *self.VERSIONADOS],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
        )
        if rastreados.returncode != 0:  # pragma: no cover - checkout sem .git
            self.skipTest("sem git utilizável neste checkout")
        no_indice = {linha.strip().replace("\\", "/") for linha in rastreados.stdout.splitlines() if linha.strip()}
        faltando = sorted(nome for nome in self.VERSIONADOS if nome not in no_indice)
        self.assertEqual(
            [],
            faltando,
            "Artefato que uma guarda lê e que o git não versiona: a guarda vira pulo permanente "
            "na CI, e o número que ela conferia deixa de ser conferido por ninguém.",
        )

    def test_os_versionados_estao_no_disco(self) -> None:
        ausentes = sorted(nome for nome in self.VERSIONADOS if not (RAIZ / nome).exists())
        self.assertEqual([], ausentes)

    def test_todo_pulo_aparece_na_saida(self) -> None:
        """`-ra` é o que faz o pytest listar os pulos e o motivo de cada um ao fim da rodada.

        Sem ele, um `s` no meio de quatro mil pontos é literalmente invisível -- e foi assim que
        os testes da S-135 puderam pular em toda corrida de CI desde que foram escritos.
        """
        pyproject = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("addopts", pyproject, "o `pyproject` perdeu a configuração do pytest")
        self.assertIn('"-ra"', pyproject, "sem `-ra` o motivo de cada pulo não é impresso")


# --------------------------------------------------------- o que a suíte estraga fora dela

FONTES = RAIZ / "src" / "chess_diagram_ocr"

PASTAS_DE_QUEM_USA = ("data", "pgn_database")
"""As duas pastas que `config.DATA_DIR` e `config.PGN_DATABASE_DIR` decidem, e a suíte desvia."""

_FICHAS_DE_LEIAUTE = frozenset({tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT})


def caminhos_montados_a_mao(fonte: str) -> list[int]:
    """Linhas onde `PROJECT_ROOT / "data"` ou `Path("data")` montam um caminho por fora do `config`.

    Por `tokenize`, e não por regex nem `ast`: um docstring que *conta* o caminho antigo é uma ficha
    de texto só e não acusa, e uma quebra de linha no meio da expressão não esconde nada.
    """
    fichas = [f for f in tokenize.generate_tokens(io.StringIO(fonte).readline) if f.type not in _FICHAS_DE_LEIAUTE]
    linhas = []
    for dono, operador, ficha in zip(fichas, fichas[1:], fichas[2:], strict=False):
        if ficha.type != tokenize.STRING or (dono.string, operador.string) not in (("PROJECT_ROOT", "/"), ("Path", "(")):
            continue
        try:
            valor = ast.literal_eval(ficha.string)
        except (ValueError, SyntaxError):
            continue
        if isinstance(valor, str) and valor.replace("\\", "/").split("/")[0] in PASTAS_DE_QUEM_USA:
            linhas.append(ficha.start[0])
    return linhas


LINHA_DO_DESVIO = "os.environ.update({variavel: str(pasta) for variavel, pasta in DESVIOS.items()})\n"
"""A linha do `conftest` que a sabotagem tira. Se ela mudar de forma, a sabotagem muda junto."""

TESTE_QUE_ABRE_O_CACHE = '''
from chess_diagram_ocr import games_cache


def test_abre_o_cache_padrao():
    """O que a Galeria faz ao abrir um livro numa pasta sem bases: o cache padrao, lista vazia."""
    games_cache.open_store(database=[]).close()
'''


class DadosDeQuemRodaTests(unittest.TestCase):
    """O programa, rodado pela suíte, não lê nem grava o `data/` e o `pgn_database/` de quem a roda.

    **O caso medido (2026-09-24).** A janela abre o cache de posições padrão com as bases achadas em
    `pgn_database/`, e `open_store` **esvazia a tabela** quando a lista de bases muda (S-84). Rodada
    no checkout do dono, uma corrida de `test_qt_janela.py` e vizinhos regravou o
    `data/games_positions.sqlite` dele, de 10,9 MB; numa réplica daquele `data/`, a suíte inteira o
    regravou 91 vezes, em 88 testes. Nenhuma corrida o esvaziou -- a lista de bases batia --, mas
    bastava um teste com outra lista para jogar fora ~56 minutos de varredura.

    O desvio mora no `conftest` (`DESVIOS`), e a guarda também (`dados_de_quem_roda_ficam_onde_estao`).
    O que está aqui é o que impede os dois de apodrecerem calados: o pacote tem de ter nascido
    desviado, nenhum caminho novo pode ser montado por fora do `config`, e a guarda tem de ser vista
    reprovando quando o desvio sai.
    """

    def test_o_desvio_chegou_ao_pacote(self) -> None:
        """O `config` foi importado **depois** do desvio, e os padrões congelados saíram dele.

        Um plugin que importasse o pacote antes do `conftest` faria os caminhos nascerem no `data/`
        de verdade, e é aqui que isso aparece -- antes de um teste de janela gravar no cache.
        """
        from conftest import DESVIOS

        from chess_diagram_ocr import config, games_cache, games_db
        from chess_diagram_ocr.ui import escolha_de_bases

        self.assertEqual(config.DATA_DIR, DESVIOS[config.ENV_DATA_DIR])
        self.assertEqual(config.PGN_DATABASE_DIR, DESVIOS[config.ENV_PGN_DATABASE_DIR])
        self.assertEqual(games_db.DEFAULT_DATABASE_DIR, config.PGN_DATABASE_DIR)
        # Os padrões que as funções congelaram na definição: é com eles que a janela abre o cache.
        cache = config.DATA_DIR / "games_positions.sqlite"
        self.assertEqual(inspect.signature(games_cache.open_store).parameters["path"].default, cache)
        self.assertEqual(inspect.signature(games_cache.stored_summary).parameters["path"].default, cache)
        self.assertEqual(inspect.signature(escolha_de_bases.store_path_for).parameters["default_path"].default, cache)

    def test_nenhum_caminho_de_dados_e_montado_por_fora_do_config(self) -> None:
        """Todo caminho em `data/` e `pgn_database/` sai de `config.DATA_DIR` ou `config.PGN_DATABASE_DIR`.

        Eram vinte e seis montados à mão, e cada um seria um furo no desvio: um módulo novo que
        escrevesse `PROJECT_ROOT / "data" / ...` voltaria a gravar no `data/` de quem roda a suíte.
        O `config.py` fica de fora porque é ele quem decide.
        """
        soltos = [
            f"{caminho.relative_to(FONTES).as_posix()}:{linha}"
            for caminho in sorted(FONTES.rglob("*.py"))
            if caminho != FONTES / "config.py"
            for linha in caminhos_montados_a_mao(caminho.read_text(encoding="utf-8"))
        ]
        self.assertEqual(
            [],
            soltos,
            "Caminho em `data/` ou `pgn_database/` montado à mão: use `config.DATA_DIR` ou "
            "`config.PGN_DATABASE_DIR`, que são o que a suíte desvia (tests/conftest.py).",
        )

    def test_a_varredura_acha_o_caminho_montado_a_mao(self) -> None:
        """A varredura acima só vale se acha o que procura: as formas que existiam, e não o docstring."""
        fonte = textwrap.dedent(
            '''
            DEFAULT_STORE_PATH = PROJECT_ROOT / "data" / "games_positions.sqlite"
            DECISOES_PADRAO = Path("data") / "texto_conflitos.json"
            DEFAULT_DATABASE_DIR = config.PROJECT_ROOT / "pgn_database"
            """Era `PROJECT_ROOT / "data" / "labels.csv"` antes da S-383."""
            DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "piece_classifier.pt"
            DEFAULT_SPLITS_PATH = DATA_DIR / "splits.csv"
            '''
        )
        self.assertEqual([2, 3, 4], caminhos_montados_a_mao(fonte))

    def test_a_guarda_reprova_quando_o_desvio_sai(self) -> None:
        """**A prova de vida da guarda**: sem o desvio, o teste que abre o cache padrão reprova.

        Um portão novo sem sabotagem é uma promessa (`tests/test_busy.py`). A sabotagem roda numa
        **cópia** da árvore -- `src/` e o `conftest` --, porque o `data/` de uma cópia é o único
        "dado de verdade" que se pode sujar: o `PROJECT_ROOT` sai do lugar do `config.py` importado.
        A cópia perde só a linha do desvio, e o filho roda o `pytest` dela sem as variáveis que este
        processo herdou do `conftest`.

        O corpo do teste do filho tem de **passar** e a corrida, reprovar: é isso que diz que quem
        reprovou foi a guarda, e não um filho que nem chegou a importar o pacote.
        """
        from conftest import DESVIOS

        conftest = (TESTES / "conftest.py").read_text(encoding="utf-8")
        self.assertEqual(1, conftest.count(LINHA_DO_DESVIO), "A linha do desvio mudou de forma: ajuste a sabotagem.")

        copia = pasta_temporaria(self, prefixo="cvoff-sabotagem-")
        shutil.copytree(FONTES, copia / "src" / "chess_diagram_ocr", ignore=shutil.ignore_patterns("__pycache__"))
        (copia / "tests").mkdir()
        sabotado = conftest.replace(LINHA_DO_DESVIO, "pass  # sabotagem: o desvio saiu\n")
        (copia / "tests" / "conftest.py").write_text(sabotado, encoding="utf-8", newline="\n")
        (copia / "tests" / "test_abre_o_cache.py").write_text(TESTE_QUE_ABRE_O_CACHE, encoding="utf-8", newline="\n")
        # Sem um arquivo de configuração na cópia, o pytest do filho subiria procurando um até a
        # raiz do disco -- e o `addopts` de quem ele achasse mudaria a corrida.
        (copia / "pytest.ini").write_text("[pytest]\n", encoding="utf-8", newline="\n")

        variaveis, fontes_da_copia, raiz_da_copia = sorted(DESVIOS), str(copia / "src"), str(copia)
        filho = rodar_python(
            textwrap.dedent(
                f"""
                import os, sys
                for variavel in {variaveis!r}:
                    os.environ.pop(variavel, None)
                sys.path.insert(0, {fontes_da_copia!r})
                os.chdir({raiz_da_copia!r})
                import pytest
                sys.exit(pytest.main(["-q", "-p", "no:cacheprovider", "tests"]))
                """
            ),
            check=False,
        )
        saida = filho.stdout + filho.stderr
        self.assertNotEqual(0, filho.returncode, saida)
        self.assertIn("1 passed", saida)
        self.assertIn("mexeu nos dados de quem roda a suíte", saida)
        self.assertIn("games_positions.sqlite (criado)", saida)
        self.assertTrue(
            (copia / "data" / "games_positions.sqlite").exists(),
            "A sabotagem não gravou no data/ da cópia: a prova não provou nada.",
        )
