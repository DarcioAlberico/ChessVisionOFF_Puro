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
import os
import shutil
import subprocess
import textwrap
import tokenize
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import quote

import varredura
from ambiente_de_teste import pasta_temporaria
from arvores_do_repositorio import checkout_principal
from qt_app import TEM_PYQT
from sonda_de_escrita import Sonda, normalizado
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
        três, e por isso a guarda é do `conftest` e olha a escrita -- a deste processo, por auditoria
        (`tests/sonda_de_escrita.py`, S-805), e não a mudança na pasta, que pode ser de outro programa.

        Esta linha é o que impede que ela seja removida sem que ninguém note. `PROJECT_ROOT` está
        cobrado junto de propósito: a guarda tem de vigiar a pasta que o **código** resolve, e não
        a que fica sob `RAIZ`. Num worktree as duas coincidem, e é aí que trocar uma pela outra
        passa despercebido -- a S-218 já foi vácua exatamente assim.
        """
        conftest = (TESTES / "conftest.py").read_text(encoding="utf-8")
        self.assertIn("dados_de_quem_roda_ficam_onde_estao", conftest)
        self.assertIn("sonda_de_escrita.instalar(pastas_de_dados_reais())", conftest)
        self.assertIn("PROJECT_ROOT", conftest, "a guarda tem de vigiar a pasta que o código resolve")


class NenhumaCaixaDeVerdadeTests(unittest.TestCase):
    """A pergunta que trava a suíte, impedida antes de acontecer (S-414).

    **O caso medido:** um `TextoPanel` sem `pasta_de_rascunhos` lê `data/rascunhos/` da máquina de
    quem roda a suíte. Se houver um rascunho ali -- e há, na máquina de quem usa o programa -- a
    aba oferece recuperá-lo com um `askyesno`, e a suíte fica parada esperando um clique que
    ninguém vai dar. Nada impedia, e nada interrompia.

    A interrupção é do `conftest`, que troca toda entrada modal do Qt por uma que reprova o teste
    dizendo o que a caixa mostraria (`tests/caixas_modais.py`, S-872). A
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
        "assets/texto_prosa/ouro.json": "o manifesto do ouro da régua da prosa, que os portões abrem (S-702)",
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

    def test_nenhum_teste_pula_sem_condicao(self) -> None:
        """**O `-ra` mostra o pulo, e não o impede** (S-868).

        Vinte e seis testes ficaram atrás de `@unittest.skip` desde o merge do religa, com o motivo
        impresso em toda rodada, e continuaram contando como testes: a Galeria, o rodapé e a folha
        de estilo do `main` que o merge largou. Pulo com condição -- falta o PyQt, falta o arquivo
        não versionado -- é legítimo; pulo sem condição é um teste que não existe. Ou ele mede o
        leiaute de hoje, ou sai.
        """
        achados = [
            f"{caminho.name}:{linha}"
            for caminho in MODULOS
            for linha in pulos_incondicionais(caminho.read_text(encoding="utf-8"))
        ]
        self.assertEqual([], achados, "teste desligado sem condição: reescreva contra o leiaute atual ou apague")

    def test_a_leitura_de_pulos_acha_e_deixa_de_achar(self) -> None:
        """O controle, contra exemplos literais: sem ele, uma leitura que não reconhecesse forma
        nenhuma deixaria a guarda de cima verde para sempre."""
        desligados = textwrap.dedent(
            """
            import unittest, pytest

            @unittest.skip("motivo")
            class Um(unittest.TestCase):
                @unittest.skip("motivo")
                def test_a(self): ...

                def test_b(self):
                    self.skipTest("motivo")

            @pytest.mark.skip(reason="motivo")
            def test_c(): ...

            @pytest.mark.skip
            def test_d(): ...

            def test_e():
                raise unittest.SkipTest("motivo")
            """
        )
        self.assertEqual([4, 6, 10, 12, 15, 19], pulos_incondicionais(desligados))
        condicionais = textwrap.dedent(
            """
            import unittest, pytest

            @unittest.skipUnless(TEM, "motivo")
            class Um(unittest.TestCase):
                @unittest.skipIf(FALTA, "motivo")
                def test_a(self): ...

                def test_b(self):
                    if not ARQUIVO.exists():
                        self.skipTest("motivo")

            @pytest.mark.skipif(FALTA, reason="motivo")
            def test_c(): ...

            def _familia():
                for candidata in CANDIDATAS:
                    return candidata
                raise unittest.SkipTest("motivo")
            """
        )
        self.assertEqual([], pulos_incondicionais(condicionais))


def _e_pulo(no: ast.expr) -> bool:
    """`unittest.skip`, `pytest.mark.skip`, `x.skipTest` ou `unittest.SkipTest` -- chamados ou não."""
    alvo = no.func if isinstance(no, ast.Call) else no
    return isinstance(alvo, ast.Attribute) and alvo.attr in {"skip", "skipTest", "SkipTest"}


def pulos_incondicionais(fonte: str) -> list[int]:
    """As linhas em que um teste é desligado sem condição: decorador `skip` (e não `skipIf`/
    `skipUnless`/`skipif`), ou `skipTest`/`raise SkipTest` direto no corpo da função, fora de
    qualquer `if`. Por `ast`: o texto deste arquivo cita as três formas, e um `grep` se acharia."""
    linhas: list[int] = []
    for no in ast.walk(ast.parse(fonte)):
        if not isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        linhas += [decorador.lineno for decorador in no.decorator_list if _e_pulo(decorador)]
        if isinstance(no, ast.ClassDef):
            continue
        for comando in no.body:
            if isinstance(comando, ast.Expr) and _e_pulo(comando.value):
                linhas.append(comando.lineno)
            elif isinstance(comando, ast.Raise) and comando.exc is not None and _e_pulo(comando.exc):
                linhas.append(comando.lineno)
            elif not isinstance(comando, _SEM_DESVIO):
                # Um `if`, um laço ou um `return` antes: o pulo que vem depois já é condicional.
                break
    return sorted(linhas)


_SEM_DESVIO = (ast.Expr, ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Import, ast.ImportFrom, ast.Pass)
"""Os comandos que não desviam o fluxo: um pulo depois só deles roda sempre."""


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
            for caminho in varredura.fontes(FONTES, recursivo=True, piso=300)
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
        for ajudante in ("arvores_do_repositorio.py", "sonda_de_escrita.py", "caixas_modais.py"):
            shutil.copy2(TESTES / ajudante, copia / "tests")
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
        self.assertIn("test_abre_o_cache_padrao escreveu nos dados de quem roda a suíte", saida)
        self.assertIn("games_positions.sqlite (sqlite3.connect", saida)
        self.assertTrue(
            (copia / "data" / "games_positions.sqlite").exists(),
            "A sabotagem não gravou no data/ da cópia: a prova não provou nada.",
        )


# ------------------------------------------------------- o QThread que a guarda de thread não via (S-805)

TESTE_QUE_DEIXA_A_TAREFA = '''
import threading

from qt_app import aplicacao

SOLTA = threading.Event()
TAREFAS = []


def test_a_deixa_a_tarefa_rodando():
    """Uma `Tarefa` sem pai, como as de `manter_viva`, que o teste não espera."""
    from chess_diagram_ocr.qt.trabalho import Tarefa

    aplicacao()
    tarefa = Tarefa(lambda: SOLTA.wait(30), nome="tarefa esquecida")
    TAREFAS.append(tarefa)
    tarefa.start()


def test_b_solta_e_espera():
    """Solta a tarefa do vizinho e espera o fim: sem isto o processo morre com o `QThread` rodando."""
    SOLTA.set()
    assert all(tarefa.wait(30_000) for tarefa in TAREFAS)
'''


class TarefaVazadaTests(unittest.TestCase):
    """Uma `Tarefa` que sobrevive ao teste reprova **o teste que a deixou** (S-805).

    A `Tarefa` é um `QThread`, e um `QThread` não aparece em `threading.enumerate()` -- ou aparece
    como `Dummy-N`, que a guarda de thread da S-413 aceita. A guarda via thread Python e não via a
    thread do Qt, que é por onde passa todo o trabalho pesado da janela.
    """

    def test_a_guarda_acusa_a_tarefa_deixada_rodando(self) -> None:
        """**A prova de vida**: um teste de mentira deixa uma `Tarefa` rodando, e é ele que reprova.

        O `conftest` é copiado para uma pasta à parte com o teste de mentira ao lado, e o filho roda
        o `pytest` de lá: o primeiro teste tem de reprovar nomeando a tarefa, e o segundo -- que a
        solta -- passar. É o segundo que diz que a falha foi da guarda, e não de um filho quebrado.
        """
        copia = pasta_temporaria(self, prefixo="cvoff-sabotagem-")
        (copia / "tests").mkdir()
        for ajudante in AJUDANTES_DA_GUARDA:
            shutil.copy2(TESTES / ajudante, copia / "tests" / ajudante)
        (copia / "tests" / "test_deixa_a_tarefa.py").write_text(TESTE_QUE_DEIXA_A_TAREFA, encoding="utf-8", newline="\n")
        (copia / "pytest.ini").write_text("[pytest]\n", encoding="utf-8", newline="\n")

        filho = rodar_python(
            textwrap.dedent(
                f"""
                import os, sys
                os.environ["QT_QPA_PLATFORM"] = "offscreen"
                os.chdir({str(copia)!r})
                import pytest
                sys.exit(pytest.main(["-q", "-p", "no:cacheprovider", "tests"]))
                """
            ),
            check=False,
        )
        saida = filho.stdout + filho.stderr
        self.assertNotEqual(0, filho.returncode, saida)
        # Os dois corpos passam e a desmontagem do primeiro reprova: quem acusou foi a guarda.
        self.assertIn("2 passed, 1 error", saida)
        self.assertIn("test_a_deixa_a_tarefa_rodando deixou thread viva", saida)
        self.assertIn("tarefa esquecida", saida)


class DadosDoCheckoutPrincipalTests(unittest.TestCase):
    """As guardas de dados vigiam o `data/` do checkout principal, e não só o desta árvore (S-805).

    Num worktree, `PROJECT_ROOT/data/` e `RAIZ/data/` são a mesma pasta sem cache: a guarda que
    só olhasse para elas passaria verde sobre uma escrita no `data/` que tem o que perder.
    """

    def test_as_pastas_do_checkout_principal_estao_entre_as_vigiadas(self) -> None:
        from conftest import pastas_de_dados_reais

        principal = checkout_principal()
        self.assertIn(principal / "data", pastas_de_dados_reais())
        self.assertIn(principal / "pgn_database", pastas_de_dados_reais())

    def test_a_sonda_anota_a_escrita_no_data_do_principal(self) -> None:
        """**A prova de vida**, num checkout principal de mentira: a escrita que cai lá é anotada.

        A sonda aqui é uma à parte, chamada com os eventos que o interpretador levantaria: nada é
        escrito em pasta nenhuma, e a sonda da sessão não vê nada disto.
        """
        import conftest

        principal = pasta_temporaria(self, prefixo="cvoff-principal-")
        with mock.patch.object(conftest, "checkout_principal", return_value=principal):
            pastas = conftest.pastas_de_dados_reais()
        sonda = Sonda()
        sonda.vigiar(pastas)
        cache = principal / "data" / "games_positions.sqlite"
        sonda("open", (str(cache), "wb", os.O_WRONLY | os.O_CREAT | os.O_TRUNC))

        self.assertEqual([(normalizado(cache), "open")], [(e.caminho, e.evento) for e in sonda.recolher()])
        self.assertEqual([], sonda.recolher(), "recolher esvazia o que entregou")


class SondaDeEscritaTests(unittest.TestCase):
    """O que a sonda conta como escrita, evento por evento, sem escrever nada (S-805)."""

    def setUp(self) -> None:
        self.dados = pasta_temporaria(self, prefixo="cvoff-sonda-") / "data"
        self.sonda = Sonda()
        self.sonda.vigiar([self.dados])

    def _anotadas(self, evento: str, *args: object) -> list[str]:
        self.sonda(evento, args)
        return [escrita.evento for escrita in self.sonda.recolher()]

    def test_leitura_nao_e_escrita(self) -> None:
        arquivo = str(self.dados / "labels.csv")
        self.assertEqual([], self._anotadas("open", arquivo, "r", os.O_RDONLY))
        self.assertEqual([], self._anotadas("os.listdir", str(self.dados)))
        uri = "file:" + quote((self.dados / "games_positions.sqlite").as_posix()) + "?mode=ro"
        self.assertEqual([], self._anotadas("sqlite3.connect", uri))

    def test_cada_forma_de_escrever_e_anotada(self) -> None:
        arquivo, outro = str(self.dados / "labels.csv"), str(self.dados / "novo.csv")
        cache = self.dados / "games_positions.sqlite"
        casos = [
            ("open", (arquivo, "a", os.O_WRONLY | os.O_APPEND | os.O_CREAT)),
            ("open", (arquivo, "r+", os.O_RDWR)),
            ("open", (outro, None, os.O_WRONLY | os.O_CREAT | os.O_EXCL)),
            ("os.remove", (arquivo, -1)),
            ("os.mkdir", (str(self.dados / "gallery"), 0o777, -1)),
            ("shutil.rmtree", (str(self.dados / "gallery"),)),
            ("os.utime", (arquivo, None, None, -1)),
            ("sqlite3.connect", (os.fsencode(cache),)),
            ("sqlite3.connect", ("file:" + quote(cache.as_posix()),)),
        ]
        for evento, args in casos:
            with self.subTest(evento=evento, args=args):
                self.assertEqual([evento], self._anotadas(evento, *args))

    def test_renomear_conta_a_origem_e_o_destino(self) -> None:
        dentro, fora = str(self.dados / "labels.csv"), str(self.dados.parent / "fora.csv")
        self.assertEqual(["os.rename"], self._anotadas("os.rename", dentro, fora, -1, -1))
        self.assertEqual(["os.rename"], self._anotadas("os.rename", fora, dentro, -1, -1))

    def test_pasta_vizinha_de_nome_parecido_nao_e_vigiada(self) -> None:
        vizinha = str(self.dados.parent / "data_antiga" / "x.png")
        self.assertEqual([], self._anotadas("open", vizinha, "wb", os.O_WRONLY | os.O_CREAT))

    def test_caixa_diferente_e_a_mesma_pasta_no_windows(self) -> None:
        if os.path.normcase("A") == "A":
            self.skipTest("sistema de arquivos que distingue caixa")
        maiuscula = str(self.dados / "samples" / "x.png").upper()
        self.assertEqual(["open"], self._anotadas("open", maiuscula, "wb", os.O_WRONLY | os.O_CREAT))

    def test_descritor_de_arquivo_nao_derruba_o_gancho(self) -> None:
        self.assertEqual([], self._anotadas("open", 3, "wb", os.O_WRONLY))
        self.assertEqual([], self._anotadas("os.utime", 3, None, None, -1))


TESTE_COM_OUTRO_PROCESSO_GRAVANDO = '''
from pathlib import Path

from subprocesso import rodar_python

AMOSTRA = Path(__file__).resolve().parents[1] / "data" / "samples" / "rotulada_ao_lado.png"


def test_outro_processo_grava_no_data():
    """O programa do dono, aberto ao lado, grava uma amostra nova no meio do teste."""
    rodar_python(f"from pathlib import Path; Path({str(AMOSTRA)!r}).write_bytes(b'png')")
    assert AMOSTRA.exists()
'''

TESTE_QUE_GRAVA_NO_DATA = '''
import os
from pathlib import Path

DADOS = Path(__file__).resolve().parents[1] / "data"


def test_o_proprio_processo_grava_no_data():
    """O teste grava por conta própria, por um `open` e por um `os.replace`."""
    (DADOS / "samples" / "do_proprio.png").write_bytes(b"png")
    os.replace(DADOS / "samples" / "do_proprio.png", DADOS / "samples" / "renomeada.png")
'''

AJUDANTES_DA_GUARDA = (
    "conftest.py",
    "qt_app.py",
    "arvores_do_repositorio.py",
    "sonda_de_escrita.py",
    "caixas_modais.py",
    "subprocesso.py",
)
"""O que o `conftest` copiado precisa ao lado para importar, e o `subprocesso` que o teste de mentira usa."""


class EscritaDeQuemRodaTests(unittest.TestCase):
    """A guarda de dados pergunta se **este** processo escreveu, e não se alguém escreveu (S-805).

    **O falso positivo, de 2026-11-09.** O dono rotulava diagramas no checkout principal -- uma amostra
    nova em `data/samples/` a cada ~15 s -- enquanto a suíte rodava num worktree. A guarda comparava a
    listagem e o `mtime` do `data/` antes e depois, e acusava ERROR na desmontagem de testes que não
    gravaram nada (`test_ui_orfaos`, `test_qualidade_dryer`, `test_packaging`).

    As duas provas rodam o `conftest` numa cópia, cujo `data/` faz o papel do de verdade: o
    `checkout_principal` de uma pasta fora do git é a própria cópia.
    """

    def _rodar(self, teste: str) -> tuple[subprocess.CompletedProcess[str], Path]:
        copia = pasta_temporaria(self, prefixo="cvoff-guarda-de-escrita-")
        (copia / "tests").mkdir()
        for ajudante in AJUDANTES_DA_GUARDA:
            shutil.copy2(TESTES / ajudante, copia / "tests" / ajudante)
        (copia / "tests" / "test_de_mentira.py").write_text(teste, encoding="utf-8", newline="\n")
        (copia / "pytest.ini").write_text("[pytest]\n", encoding="utf-8", newline="\n")
        (copia / "data" / "samples").mkdir(parents=True)
        filho = rodar_python(
            textwrap.dedent(
                f"""
                import os, sys
                os.chdir({str(copia)!r})
                import pytest
                sys.exit(pytest.main(["-q", "-p", "no:cacheprovider", "tests"]))
                """
            ),
            check=False,
        )
        return filho, copia / "data" / "samples"

    def test_outro_processo_gravando_no_data_nao_reprova_ninguem(self) -> None:
        filho, amostras = self._rodar(TESTE_COM_OUTRO_PROCESSO_GRAVANDO)
        saida = filho.stdout + filho.stderr
        self.assertTrue((amostras / "rotulada_ao_lado.png").exists(), "o outro processo não gravou: nada foi provado")
        self.assertEqual(0, filho.returncode, saida)
        self.assertIn("1 passed", saida)
        self.assertNotIn("error", saida)

    def test_o_proprio_processo_gravando_no_data_reprova_o_teste_que_gravou(self) -> None:
        filho, _ = self._rodar(TESTE_QUE_GRAVA_NO_DATA)
        saida = filho.stdout + filho.stderr
        self.assertNotEqual(0, filho.returncode, saida)
        # O corpo passa e a desmontagem reprova: quem acusou foi a guarda, e no teste que gravou.
        self.assertIn("1 passed, 1 error", saida)
        self.assertIn("test_o_proprio_processo_grava_no_data escreveu nos dados de quem roda a suíte", saida)
        self.assertIn("do_proprio.png (open", saida)
        self.assertIn("renomeada.png (os.rename", saida)


class PyQtAusenteReprovaTests(unittest.TestCase):
    """Sem o PyQt6 a rodada **reprova**, em vez de sair verde com duzentas classes puladas (S-805).

    O PyQt6 é dependência de base desde o corte do Tk (S-506), e os testes de janela pulam sem ele
    (`qt_app.TEM_PYQT`). Pular com o motivo escrito continua melhor que um `ImportError` em cada
    módulo; o que não pode é a corrida inteira terminar verde -- e o `-ra` era a única marca.
    """

    def test_o_pyqt6_esta_instalado(self) -> None:
        self.assertTrue(
            TEM_PYQT,
            "O PyQt6 não está instalado, e os testes de janela pularam todos. Ele é dependência "
            "de base (pyproject.toml): rode `uv sync --extra dev`.",
        )

    def test_sem_o_pyqt6_o_teste_acima_reprova_e_nao_pula(self) -> None:
        """O filho esconde o pacote (`sys.modules["PyQt6"] = None`, que é como o `importlib` diz
        "não há") antes de o pytest começar, e roda só o teste acima: ele tem de **falhar**."""
        alvo = f"{Path(__file__).resolve()}::PyQtAusenteReprovaTests::test_o_pyqt6_esta_instalado"
        filho = rodar_python(
            textwrap.dedent(
                f"""
                import sys
                sys.modules["PyQt6"] = None
                import pytest
                sys.exit(pytest.main(["-q", "-p", "no:cacheprovider", {alvo!r}]))
                """
            ),
            check=False,
        )
        saida = filho.stdout + filho.stderr
        self.assertNotEqual(0, filho.returncode, saida)
        self.assertIn("1 failed", saida)
        self.assertIn("uv sync", saida)


class VarreduraComPisoTests(unittest.TestCase):
    """As guardas que percorrem fonte pedem a lista a `varredura.fontes`, que tem piso (S-871).

    Um glob sobre uma pasta que mudou de lugar devolve vazio, e a guarda fica verde sobre nada.
    """

    def test_pasta_que_mudou_de_lugar_reprova(self) -> None:
        with self.assertRaisesRegex(AssertionError, "abaixo do piso"):
            varredura.fontes(pasta_temporaria(self) / "sumiu", piso=1)

    def test_padrao_que_deixou_de_casar_reprova(self) -> None:
        pasta = pasta_temporaria(self)
        (pasta / "a.py").write_bytes(b"")
        with self.assertRaisesRegex(AssertionError, "achou 0"):
            varredura.fontes(pasta, "texto_*.py", piso=1)

    def test_no_piso_devolve_os_arquivos_em_ordem(self) -> None:
        pasta = pasta_temporaria(self)
        for nome in ("b.py", "a.py", "c.md", "sub/d.py"):
            (pasta / nome).parent.mkdir(exist_ok=True)
            (pasta / nome).write_bytes(b"")
        self.assertEqual([pasta / "a.py", pasta / "b.py"], varredura.fontes(pasta, piso=2))
        self.assertEqual(3, len(varredura.fontes(pasta, recursivo=True, piso=3)))
