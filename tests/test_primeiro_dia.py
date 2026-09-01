"""O primeiro dia de quem clona: as quatro sobras da Fase 55 (S-421 a S-424).

Nenhuma delas aparece para quem já tem o acervo montado -- que é toda a gente que já leu este
código. É por isso que sobreviveram: elas só existem no estado de **100% de quem instala**, e
ninguém que trabalha aqui volta a esse estado.
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path
from unittest import mock

from subprocesso import rodar_python

from chess_diagram_ocr import logging_setup
from chess_diagram_ocr.ui import texto_declarado

RAIZ = Path(__file__).resolve().parents[1]


class OndeEstaORastroTests(unittest.TestCase):
    """Toda mensagem de erro mandava olhar um log que num checkout não existe (S-421).

    `default_log_file()` devolve `None` sem `CVOFF_LOG_DIR`, **de propósito**: no terminal o rastro
    é o terminal. Mas a caixa de erro da janela e o `cli_errors` diziam "está no log" nos dois
    casos, e no caso comum -- alguém que clonou e rodou -- mandavam procurar um arquivo que ninguém
    escreveu. Quem tenta seguir a instrução conclui que perdeu o rastro; ele nunca existiu.
    """

    def test_sem_log_a_frase_diz_o_que_fazer_para_haver_um(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CVOFF_LOG_DIR", None)
            with mock.patch.object(logging_setup.sys, "frozen", False, create=True):
                frase = logging_setup.onde_esta_o_rastro()
        self.assertIn("CVOFF_LOG_DIR", frase)
        self.assertNotIn("está em", frase, "não pode dizer que está em lugar nenhum")

    def test_com_log_a_frase_diz_o_caminho(self) -> None:
        with mock.patch.dict(os.environ, {"CVOFF_LOG_DIR": r"C:\um\lugar"}):
            frase = logging_setup.onde_esta_o_rastro()
        self.assertIn("chessvisionoff.log", frase)

    def test_ninguem_mais_promete_um_log_generico(self) -> None:
        """A varredura é o item: a frase estava escrita à mão em quatro lugares."""
        alvos = [
            RAIZ / "src" / "chess_diagram_ocr" / "qt" / "janela.py",
            *sorted((RAIZ / "src" / "chess_diagram_ocr" / "ui").glob("*.py")),
            *sorted((RAIZ / "src" / "chess_diagram_ocr" / "cli").glob("*.py")),
        ]
        promessas = [
            f"{caminho.name}:{numero}"
            for caminho in alvos
            for numero, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1)
            if re.search(r'"[^"]*(está no log|no arquivo de log)[^"]*"', linha)
        ]
        self.assertEqual(
            [],
            promessas,
            "Mensagem que promete um log sem perguntar se há um. Use "
            "`logging_setup.onde_esta_o_rastro()`.",
        )


class AjudaComSaidaRedirecionadaTests(unittest.TestCase):
    """`--help` sai inteiro mesmo quando a saída não é UTF-8 (S-422).

    **Dois comandos não conseguiam imprimir a própria ajuda.** `cvoff-texto-pagina` e
    `cvoff-texto-pesquisavel` trazem figurina de xadrez no texto (`♔`, `♘`), e no Windows a saída
    **redirecionada** é a página de código do sistema, não UTF-8: o `print` do argparse levantava
    `UnicodeEncodeError` e o comando saía com código 2. `cvoff-texto-pagina --help > ajuda.txt` é o
    gesto mais natural do mundo, e não funcionava.
    """

    COM_FIGURINA = ("chess_diagram_ocr.cli.texto_pagina", "chess_diagram_ocr.cli.texto_pesquisavel")

    def test_a_ajuda_sai_inteira_numa_saida_cp1252(self) -> None:
        for modulo in self.COM_FIGURINA:
            with self.subTest(comando=modulo):
                resultado = rodar_python(
                    f"import runpy, sys; sys.argv = ['x', '--help']; runpy.run_module({modulo!r}, run_name='__main__')",
                    check=False,
                )
                self.assertEqual(0, resultado.returncode, resultado.stdout[-300:])
                self.assertIn("usage", resultado.stdout.lower())

    def test_a_figurina_continua_na_ajuda(self) -> None:
        """Se ela sumir, o teste acima passa a não medir nada -- e a ajuda perde a informação."""
        fontes = "".join(
            (RAIZ / "src" / "chess_diagram_ocr" / "cli" / f"{nome.rsplit('.', 1)[1]}.py").read_text(encoding="utf-8")
            for nome in self.COM_FIGURINA
        )
        self.assertTrue(
            any(figurina in fontes for figurina in ("♔", "♘", "♞", "♚")),
            "a ajuda perdeu a figurina, e com ela o motivo deste teste",
        )


class MotorPadraoDaAbaTextoTests(unittest.TestCase):
    """A aba abria com o motor que não pode funcionar num clone novo (S-423).

    O glifo precisa de `models/char_classifier.pt`, que não vem no repositório. `auto` estava na
    mesma caixa, a um clique: é o glifo **com a camada como reserva**, então com o classificador no
    lugar ele lê igual, e sem ele cai na camada avisando no log.
    """

    def test_o_padrao_e_auto(self) -> None:
        self.assertEqual("auto", texto_declarado.MOTORES[0])

    def test_os_tres_continuam_oferecidos(self) -> None:
        from chess_diagram_ocr.text import leitor

        self.assertEqual(set(leitor.MOTORES), set(texto_declarado.MOTORES))


class TabelaDoPrimeiroDiaTests(unittest.TestCase):
    """A "Resolução de problemas" cobre o que falta **sempre** (S-424).

    Ela tinha duas linhas sobre o classificador de **caractere** -- o motor que quase ninguém usa
    -- e nenhuma sobre o classificador de **peças**, que é o que falta em 100% dos clones e sem o
    qual o programa não lê diagrama nenhum.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = (RAIZ / "README.md").read_text(encoding="utf-8")

    def test_a_tabela_fala_do_classificador_de_pecas(self) -> None:
        self.assertIn("piece_classifier.pt", self.readme)
        linhas = [linha for linha in self.readme.splitlines() if linha.startswith("| ") and "piece_classifier.pt" in linha]
        self.assertTrue(linhas, "a tabela de problemas não cita o modelo que falta em todo clone")
        self.assertIn("cvoff-train", linhas[0], "a linha tem de dizer como obter o modelo")

    def test_o_primeiro_dia_vem_antes(self) -> None:
        """Ordem importa numa tabela de sintomas: o que acontece com todo mundo vem primeiro."""
        pecas = self.readme.index("piece_classifier.pt")
        char = self.readme.index("char_classifier.pt")
        self.assertLess(pecas, char)
