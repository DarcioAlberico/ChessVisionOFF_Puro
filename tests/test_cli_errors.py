"""Os `cvoff-*` falham em pt-BR, com código de saída por classe (S-126).

`uv run cvoff-infer <arquivo de lixo>` produzia **11 quadros de traceback** terminando em
`pymupdf.FileDataError: Failed to open file '...'`, **em inglês**. `cli/infer.py` só capturava
`NoBoardDetectedError`; `cli/export_pgn.py` chamava `save_pdf_positions_to_pgn` sem `try`
nenhum. **14 dos 15 comandos** se comportavam assim.

O `CONTRIBUTING.md` declara que a saída de um `cvoff-*` **é a interface daquele programa**. Nas
três falhas mais prováveis -- PDF corrompido, checkpoint de outra `arch_version`, caminho
inexistente -- essa interface era um traceback em inglês e um código de saída indistinguível.
"""

from __future__ import annotations

import ast
import importlib
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from chess_diagram_ocr.cli import (
    EXIT_BAD_INPUT,
    EXIT_NO_CHECKPOINT,
    EntradaInvalida,
    message_for,
    run_main,
)

COMANDOS_COM_PDF = ("infer", "export_pgn", "batch")

#: 47 `main` em `cli/` em 2026-11-09; o piso deixa espaço para tirar alguns, não para achar zero.
PISO_DE_MAINS = 40


def mains_de_cli(pasta: Path) -> dict[str, set[str]]:
    """`{arquivo: nomes dos decoradores}` de cada `def main` no nível do módulo em `pasta`."""
    achados: dict[str, set[str]] = {}
    for caminho in sorted(pasta.glob("*.py")):
        for no in ast.parse(caminho.read_text(encoding="utf-8")).body:
            if isinstance(no, ast.FunctionDef) and no.name == "main":
                achados[caminho.name] = {ast.unparse(d).rsplit(".", 1)[-1] for d in no.decorator_list}
    return achados
"""Os comandos que recebem um PDF como argumento posicional -- os que dá para dirigir contra um
arquivo de lixo sem inventar um dataset inteiro.

Os outros catorze recebem a mesma proteção pelo **mesmo** decorador, e é isso que
`test_todo_main_de_cli_esta_protegido` verifica. Exigir de cada um deles um cenário de falha
próprio seria testar o `argparse` de quinze comandos, e não a guarda -- e um argumento que o
comando nem aceita produz `SystemExit` do `argparse`, que passa direto de propósito."""


class MensagemTests(unittest.TestCase):
    """A classe da falha (2 ou 3) vem do tipo desde a S-857: ver `SoAFronteiraDizQue...`."""

    def test_a_mensagem_sai_em_pt_br_com_o_original_ao_lado(self) -> None:
        """A tradução ajuda quem lê; o texto original é o que se pesquisa."""
        texto = message_for(OSError("Failed to open file 'lixo.pdf'."))
        self.assertIn("não foi possível abrir o arquivo", texto)
        self.assertIn("lixo.pdf", texto)

    def test_mensagem_sem_padrao_conhecido_sai_como_veio(self) -> None:
        """Inventar tradução para o que não se reconhece seria esconder a informação real."""
        self.assertEqual(message_for(ValueError("épocas não pode ser negativo")), "épocas não pode ser negativo")

    def test_excecao_sem_texto_ainda_diz_alguma_coisa(self) -> None:
        self.assertEqual(message_for(RuntimeError()), "RuntimeError")


class RunMainTests(unittest.TestCase):
    def test_sucesso_passa_direto(self) -> None:
        self.assertEqual(run_main(lambda _argv: 0), 0)

    def test_falha_conhecida_vira_codigo_e_linha_em_pt_br(self) -> None:
        def _falha(_argv: object) -> int:
            raise EntradaInvalida(message_for(OSError("Failed to open file 'x.pdf'")))

        saida = io.StringIO()
        with redirect_stdout(saida):
            codigo = run_main(_falha)

        self.assertEqual(codigo, EXIT_BAD_INPUT)
        self.assertIn("não foi possível abrir", saida.getvalue())
        self.assertNotIn("Traceback", saida.getvalue())

    def test_falha_inesperada_e_a_classe_1(self) -> None:
        """Separada das outras porque significa outra coisa: não é a entrada que está errada,
        é o programa."""

        def _falha(_argv: object) -> int:
            raise KeyError("chave")

        with redirect_stdout(io.StringIO()) as saida:
            codigo = run_main(_falha)

        self.assertEqual(codigo, 1)
        self.assertIn("Falha inesperada", saida.getvalue())

    def test_com_v_o_traceback_volta(self) -> None:
        """Quem está depurando pede o rastro, e continua podendo pedi-lo."""

        def _falha(_argv: object) -> int:
            raise EntradaInvalida("o livro x.pdf: arquivo ou diretório não encontrado")

        with redirect_stdout(io.StringIO()), self.assertRaises(EntradaInvalida):
            run_main(_falha, ["-v"])

    def test_interrupcao_do_usuario_nao_e_falha_do_programa(self) -> None:
        def _para(_argv: object) -> int:
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            run_main(_para)

    def test_systemexit_do_argparse_passa_direto(self) -> None:
        """O `argparse` já disse o que faltava, e engoli-lo trocaria a mensagem dele por uma
        pior."""

        def _sai(_argv: object) -> int:
            raise SystemExit(2)

        with self.assertRaises(SystemExit):
            run_main(_sai)


class ComandosContraLixoTests(unittest.TestCase):
    """**O critério de aceite**, dirigido de verdade: código por classe e nenhum traceback."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lixo = Path(self.tmp.name) / "lixo.pdf"
        self.lixo.write_text("isto não é um PDF\n", encoding="utf-8")

    def test_cada_comando_sai_por_classe_e_sem_traceback(self) -> None:
        for nome in COMANDOS_COM_PDF:
            modulo = importlib.import_module(f"chess_diagram_ocr.cli.{nome}")
            with self.subTest(comando=nome):
                saida = io.StringIO()
                with redirect_stdout(saida):
                    codigo = modulo.main([str(self.lixo)])
                self.assertIn(codigo, (1, 2, 3), f"{nome} saiu com {codigo}")
                self.assertNotIn("Traceback", saida.getvalue())

    def test_todo_main_de_cli_esta_protegido(self) -> None:
        """A varredura que impede o próximo comando de nascer desprotegido.

        Mesma ideia do `SEM_REGISTRO` da S-112: a lista é o teste. Um `cvoff-*` novo sem o
        decorador falha a suíte, e não fica esperando alguém reparar num traceback em inglês.

        Pela árvore e com piso (S-871): era um glob procurando `"\\ndef main("` no texto, e com a
        pasta movida o glob voltava vazio e a guarda passava verde sobre nada.
        """
        raiz = Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr" / "cli"
        mains = mains_de_cli(raiz)
        self.assertGreaterEqual(len(mains), PISO_DE_MAINS, f"a varredura de {raiz} achou só {len(mains)} `main`")
        faltando = [nome for nome, decoradores in mains.items() if "cli_errors" not in decoradores]
        self.assertEqual(faltando, [], "Todo `main` de CLI precisa do decorador `@cli_errors`.")

    def test_a_varredura_reconhece_o_main_sem_decorador(self) -> None:
        """O controle da guarda de cima, sobre fonte escrita aqui: ela tem de saber achar."""
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "protegido.py").write_text("@cli_errors\ndef main(argv=None):\n    pass\n", encoding="utf-8")
            (pasta / "nu.py").write_text("import x\n\n\ndef main(argv=None):\n    pass\n", encoding="utf-8")
            (pasta / "biblioteca.py").write_text("def ajuda():\n    pass\n", encoding="utf-8")
            self.assertEqual({"protegido.py": {"cli_errors"}, "nu.py": set()}, mains_de_cli(pasta))


class SoAFronteiraDizQueAEntradaEInvalidaTests(unittest.TestCase):
    """A classe da falha vem do tipo levantado na fronteira, e não do texto da mensagem (S-857).

    O `run_main` tratava todo `ValueError`, `OSError` e `RuntimeError` como "entrada inválida":
    um `int("x")` de defeito interno saía 2, dizendo à pessoa que a culpa era do que ela apontou.
    E o 3 era decidido por palavras no texto (`"checkpoint"`, `".pt"`).
    """

    def setUp(self) -> None:
        import fitz

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.pdf = self.raiz / "livro.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(self.pdf)
        doc.close()

    def _rodar(self, argv: list[str]) -> tuple[int, str]:
        from chess_diagram_ocr.cli import infer

        saida = io.StringIO()
        with redirect_stdout(saida):
            codigo = infer.main(argv)
        return codigo, saida.getvalue()

    def test_int_x_dentro_de_um_carregador_sai_com_1(self) -> None:
        """O defeito do programa não é culpa de quem chamou."""
        from unittest import mock

        def carregador_com_defeito(*_args: object, **_kwargs: object) -> object:
            return int("x")

        with mock.patch("chess_diagram_ocr.cli.infer.render_pdf_page", carregador_com_defeito):
            codigo, saida = self._rodar([str(self.pdf), "--model", str(self._checkpoint())])
        self.assertEqual(codigo, 1, saida)
        self.assertIn("Falha inesperada", saida)

    def test_pdf_que_nao_existe_sai_com_2(self) -> None:
        codigo, saida = self._rodar([str(self.raiz / "nao_existe.pdf")])
        self.assertEqual(codigo, EXIT_BAD_INPUT, saida)
        self.assertNotIn("Traceback", saida)

    def test_checkpoint_que_nao_existe_sai_com_3(self) -> None:
        codigo, saida = self._rodar([str(self.pdf), "--model", str(self.raiz / "nao_existe.pt")])
        self.assertEqual(codigo, EXIT_NO_CHECKPOINT, saida)

    def test_a_mensagem_nao_decide_a_classe(self) -> None:
        """Um `ValueError` que fala de `.pt` continua sendo defeito: era o que a pista lia."""

        def _falha(_argv: object) -> int:
            raise ValueError("o arquivo pesos.pt veio com um campo estranho")

        with redirect_stdout(io.StringIO()):
            self.assertEqual(run_main(_falha), 1)

    def test_a_entrada_invalida_e_o_checkpoint_invalido_tem_codigo_proprio(self) -> None:
        from chess_diagram_ocr.cli import CheckpointInvalido

        def _entrada(_argv: object) -> int:
            raise EntradaInvalida("--csv: arquivo não encontrado")

        def _checkpoint(_argv: object) -> int:
            raise CheckpointInvalido("--model: arquivo não encontrado")

        with redirect_stdout(io.StringIO()) as saida:
            self.assertEqual(run_main(_entrada), EXIT_BAD_INPUT)
            self.assertEqual(run_main(_checkpoint), EXIT_NO_CHECKPOINT)
        self.assertIn("Erro: --csv: arquivo não encontrado", saida.getvalue())

    def test_banco_sqlite_corrompido_na_fronteira_e_entrada_invalida(self) -> None:
        import sqlite3

        from chess_diagram_ocr.cli import fronteira

        with self.assertRaises(EntradaInvalida), fronteira("--cache"):
            raise sqlite3.DatabaseError("file is not a database")

    def _checkpoint(self) -> Path:
        """Um `.pt` que carrega: o teste do `int("x")` precisa passar da fronteira do modelo."""
        from chess_diagram_ocr.checkpoint import save_checkpoint
        from chess_diagram_ocr.config import PIECE_CLASSES
        from chess_diagram_ocr.model import ArchConfig, PieceClassifier

        caminho = self.raiz / "m.pt"
        metadados = {"arch_version": ArchConfig().version, "class_names": list(PIECE_CLASSES)}
        save_checkpoint(caminho, PieceClassifier().state_dict(), metadata=metadados)
        return caminho


class IntervaloDePaginasTests(unittest.TestCase):
    """`--paginas` inválido fala português, como o resto do programa (S-385).

    `int("58a")` levanta `invalid literal for int() with base 10: '58a'`, e a frase chegava
    inteira à tela dentro de `--paginas inválido: ...`. A S-126 tirou o inglês das três falhas
    mais prováveis; esta é a quarta, e está no argumento que mais se digita à mão.
    """

    def _erro(self, texto: str) -> str:
        from chess_diagram_ocr.cli.texto_pagina import intervalo_de_paginas

        with self.assertRaises(ValueError) as capturado:
            intervalo_de_paginas(texto)
        return str(capturado.exception)

    def test_o_que_vale_continua_valendo(self) -> None:
        from chess_diagram_ocr.cli.texto_pagina import intervalo_de_paginas

        self.assertEqual(intervalo_de_paginas("58-62"), [57, 58, 59, 60, 61])
        self.assertEqual(intervalo_de_paginas("58,60"), [57, 59])
        self.assertEqual(intervalo_de_paginas(" 7 "), [6])

    def test_numero_com_letra_nao_vaza_a_frase_do_int(self) -> None:
        recado = self._erro("58a")
        self.assertNotIn("invalid literal", recado)
        self.assertIn("não é número de página", recado)
        self.assertIn("58-62", recado, "a frase diz o que teria funcionado")

    def test_intervalo_pela_metade_tambem(self) -> None:
        self.assertNotIn("invalid literal", self._erro("58-"))

    def test_intervalo_invertido_continua_recusado(self) -> None:
        self.assertIn("invertido", self._erro("62-58"))


if __name__ == "__main__":
    unittest.main()
