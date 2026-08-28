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

import importlib
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from chess_diagram_ocr.cli import (
    EXIT_BAD_INPUT,
    EXIT_NO_CHECKPOINT,
    classify,
    message_for,
    run_main,
)

COMANDOS_COM_PDF = ("infer", "export_pgn", "batch")
"""Os comandos que recebem um PDF como argumento posicional -- os que dá para dirigir contra um
arquivo de lixo sem inventar um dataset inteiro.

Os outros catorze recebem a mesma proteção pelo **mesmo** decorador, e é isso que
`test_todo_main_de_cli_esta_protegido` verifica. Exigir de cada um deles um cenário de falha
próprio seria testar o `argparse` de quinze comandos, e não a guarda -- e um argumento que o
comando nem aceita produz `SystemExit` do `argparse`, que passa direto de propósito."""


class ClassificacaoTests(unittest.TestCase):
    def test_arquivo_invalido_e_entrada_invalida(self) -> None:
        self.assertEqual(classify(OSError("Failed to open file 'x.pdf'")), EXIT_BAD_INPUT)

    def test_checkpoint_e_uma_classe_propria(self) -> None:
        """Quem consome isto é script: `cvoff-scan --all && ...` precisa distinguir "este livro
        estava corrompido" de "o modelo sumiu"."""
        self.assertEqual(classify(RuntimeError("size mismatch for checkpoint")), EXIT_NO_CHECKPOINT)
        self.assertEqual(classify(OSError("models/piece_classifier.pt não encontrado")), EXIT_NO_CHECKPOINT)

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
            raise OSError("Failed to open file 'x.pdf'")

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
            raise OSError("Failed to open file 'x.pdf'")

        with redirect_stdout(io.StringIO()), self.assertRaises(OSError):
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
        """
        raiz = Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr" / "cli"
        faltando = []
        for caminho in sorted(raiz.glob("*.py")):
            if caminho.name in ("__init__.py", "_ocr.py"):
                continue
            texto = caminho.read_text(encoding="utf-8")
            if "\ndef main(" in texto and "@cli_errors\ndef main(" not in texto:
                faltando.append(caminho.name)

        self.assertEqual(faltando, [], "Todo `main` de CLI precisa do decorador `@cli_errors`.")


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
