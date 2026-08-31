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
import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
TESTES = Path(__file__).resolve().parent

MODULOS = sorted(p for p in TESTES.glob("*.py") if p.name != "conftest.py")
"""Todo módulo de teste, mais os ajudantes. O `conftest` fica de fora: ele é o mecanismo."""


def _arvore(caminho: Path) -> ast.Module:
    return ast.parse(caminho.read_text(encoding="utf-8"))


class UmaRaizSoTests(unittest.TestCase):
    """Nenhum teste cria a própria raiz Tk (S-416).

    **A regra é de 2026-07 e está escrita em `tests/tk_root.py`**: com duas raízes vivas ao mesmo
    tempo há dois interpretadores Tcl, `tkinter._default_root` continua sendo o primeiro, e uma
    `PhotoImage` criada sem `master` nasce no interpretador errado -- o Tk recusa a imagem com uma
    mensagem que parece coleta de lixo, e foi assim que 20 testes do `test_result_panel` falharam
    só na CI. **Nove módulos criavam a sua assim mesmo**, cada um com o mesmo `try/except` copiado.
    """

    def test_nenhum_modulo_de_teste_cria_tk_tk(self) -> None:
        proprios = [
            f"{caminho.name}:{no.lineno}"
            for caminho in MODULOS
            if caminho.name != "tk_root.py"
            for no in ast.walk(_arvore(caminho))
            if isinstance(no, ast.Call) and ast.unparse(no.func) in ("tk.Tk", "tkinter.Tk")
        ]
        self.assertEqual(
            [],
            proprios,
            "Raiz Tk própria num teste. Chame `tk_root.raiz()` e pendure os widgets num quadro "
            "próprio -- o porquê está no docstring de `tests/tk_root.py`.",
        )

    def test_a_raiz_compartilhada_continua_existindo(self) -> None:
        """A guarda acima ficaria vácua se `tk_root` deixasse de oferecer a raiz."""
        self.assertIn("def raiz()", (TESTES / "tk_root.py").read_text(encoding="utf-8"))


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
        self.assertIn("askyesno", conftest)


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
