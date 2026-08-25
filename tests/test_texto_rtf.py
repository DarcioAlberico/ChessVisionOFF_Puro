"""O `.rtf`, e as duas armadilhas do formato (S-252).

**Por que RTF e não `.docx`:** o RTF é texto puro, escrito com a biblioteca padrão, e o Word, o
LibreOffice e o WordPad abrem os três. Negrito, itálico, sublinhado, corpo e imagem cabem nele.
**São ~200 linhas de Python e zero dependência.** O `.docx` faria o mesmo com `python-docx`, e a
conta é a que este projeto já fez três vezes -- na S-54 com o `streamlit`, na S-137 com o `pyarrow`,
na S-42 com o motor de OCR: dependência obrigatória para o que zero dependência já cobre é custo
puro no que o usuário baixa.

As duas armadilhas viram teste porque numa página de xadrez **o caso raro é o caso comum**: o texto
é feito de caracteres fora do ASCII, e o OCR produz chaves e barras por engano.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from chess_diagram_ocr.text import exportacao, rico

RAIZ = Path(__file__).resolve().parents[1]


class EscapeTests(unittest.TestCase):
    def test_a_figurina_vira_escape_assinado(self) -> None:
        """`♘` é U+2658 = 9816, e cabe no positivo."""
        self.assertEqual(exportacao.escapar_rtf("♘"), "\\u9816?")

    def test_o_escape_cobre_acima_de_32767(self) -> None:
        """**O número é assinado de 16 bits**: acima de 32767 ele vira negativo, e um leitor que
        recebesse 39672 no lugar de -25864 desenharia outro glifo."""
        self.assertEqual(exportacao.escapar_rtf("￮"), "\\u-18?")
        # Acima do BMP, o par substituto é o que o formato aceita: 🗸 = U+1F5F8.
        self.assertEqual(exportacao.escapar_rtf("🗸"), "\\u-10179?\\u-8712?")

    def test_o_ascii_nao_e_escapado(self) -> None:
        self.assertEqual(exportacao.escapar_rtf("Nf3 e4"), "Nf3 e4")

    def test_a_chave_e_a_barra_sao_escapadas(self) -> None:
        """Um `}` não escapado quebra o arquivo **inteiro**, e não só a linha -- e a S-211 mediu 96
        caracteres espúrios em 13 páginas de OCR."""
        espurio = "texto com } e { e \\ do OCR"
        self.assertEqual(
            exportacao.escapar_rtf(espurio), "texto com \\} e \\{ e \\\\ do OCR"
        )

    def test_a_quebra_de_linha_vira_par(self) -> None:
        self.assertIn("\\par", exportacao.escapar_rtf("uma\noutra"))


class ArquivoTests(unittest.TestCase):
    def test_o_arquivo_abre_com_os_atributos(self) -> None:
        """O que se afirma é a marcação que o Word lê: `\\b`, `\\i`, `\\ul`, e as chaves em volta."""
        doc = rico.alternar(rico.de_texto("negrito italico sublinhado"), 0, 7, "negrito")
        doc = rico.alternar(doc, 8, 15, "italico")
        doc = rico.aplicar(doc, 16, 26, sublinhado=True)
        saida = exportacao.exportar(doc, exportacao.Rtf()).conteudo
        self.assertTrue(saida.startswith("{\\rtf1"))
        self.assertTrue(saida.rstrip().endswith("}"))
        self.assertIn("{\\b negrito}", saida)
        self.assertIn("{\\i italico}", saida)
        self.assertIn("{\\ul sublinhado}", saida)

    def test_a_pagina_de_xadrez_atravessa(self) -> None:
        doc = rico.de_texto("1.♘f3 ♘f6 2.c4 e6 ±")
        saida = exportacao.exportar(doc, exportacao.Rtf()).conteudo
        self.assertIn("\\u9816?", saida)
        self.assertIn("\\u177?", saida)
        self.assertNotIn("♘", saida)

    def test_o_titulo_muda_de_corpo(self) -> None:
        doc = rico.aplicar_estilo(rico.de_texto("Um título"), 0, 9, "titulo")
        self.assertIn("\\fs28", exportacao.exportar(doc, exportacao.Rtf()).conteudo)

    def test_a_cor_do_autor_e_declarada_como_perda(self) -> None:
        doc = rico.aplicar(rico.de_texto("um trecho"), 0, 9, cor="nota")
        self.assertEqual(exportacao.exportar(doc, exportacao.Rtf()).perdas.get("cor"), 1)


class SemDependenciaNovaTests(unittest.TestCase):
    def test_nenhuma_dependencia_nova(self) -> None:
        """`python-docx` **não** entra: o `.rtf` cobre o caso com a biblioteca padrão.

        Se um dia entrar, entra como **extra** e o formato avisa em pt-BR quando falta -- o molde de
        `onnx`, `ocr` e `demo`. O teste trava a decisão de hoje: nenhum dos dois nomes aparece no
        `pyproject.toml`.
        """
        # Sem leitor de TOML: o Python 3.10 desta suíte não traz `tomllib`, e `test_docs.py` já
        # lê o `pyproject.toml` como texto pelo mesmo motivo.
        bruto = (RAIZ / "pyproject.toml").read_text(encoding="utf-8").lower()
        self.assertNotIn("python-docx", bruto)
        self.assertNotIn("docx", bruto)

    def test_o_exportador_so_usa_a_biblioteca_padrao(self) -> None:
        import ast

        arvore = ast.parse(Path(exportacao.__file__).read_text(encoding="utf-8"))
        externos: set[str] = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                externos.update(alias.name.split(".")[0] for alias in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
                externos.add(no.module.split(".")[0])
        self.assertEqual(externos - {"html", "collections", "dataclasses", "pathlib", "typing", "__future__"}, set())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
