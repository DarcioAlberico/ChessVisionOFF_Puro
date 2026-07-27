"""Vocabulário da interface e acentuação em pt-BR (S-04).

A pendência 0.7 ficou aberta desde a Fase 0: as strings da interface estavam sem acento
("posicao", "Configuracao") e centralizá-las dependia da decomposição do Tkinter, que só
veio na 6.2. Aqui ela fecha, e o teste é o que impede a regressão -- sem ele, a próxima
string escrita às pressas volta a ser "posicao" e ninguém percebe.

A varredura olha **literais de string** via AST, não o arquivo inteiro: docstrings e
comentários também são pt-BR, mas o que o usuário lê é o que importa travar.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from chess_diagram_ocr.ui import strings

RAIZ = Path(__file__).resolve().parents[1]

ARQUIVOS_DE_UI = [
    # `strings.py` fica de fora: ele **contém** a lista das formas erradas, de propósito.
    caminho
    for caminho in sorted((RAIZ / "src" / "chess_diagram_ocr" / "ui").glob("*.py"))
    if caminho.name != "strings.py"
] + [RAIZ / "app_tkinter.py", RAIZ / "app_streamlit.py"]

PERMITIDOS = {
    # Chaves, nomes de campo e identificadores que por acaso batem com uma palavra da lista.
    "sao",
}
"""Exceções. Vazia de propósito quanto a texto de tela: uma exceção ali seria a string que
o usuário lê errada."""


def _literais_visiveis(caminho: Path) -> list[str]:
    """Strings do módulo que não são docstring (de módulo, classe, função ou atributo)."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    documentacao: set[int] = set()
    for no in ast.walk(arvore):
        corpo = getattr(no, "body", None)
        if not isinstance(corpo, list):
            continue
        for item in corpo:
            if isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant):
                if isinstance(item.value.value, str):
                    documentacao.add(id(item.value))

    return [
        no.value
        for no in ast.walk(arvore)
        if isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in documentacao
    ]


class AccentTests(unittest.TestCase):
    def test_no_ui_string_uses_an_unaccented_portuguese_word(self) -> None:
        """A trava da pendência 0.7 da Fase 0."""
        padrao = re.compile(
            # `s?` e nao `\w*`: "automaticamente" e correto sem acento, e um casamento
            # largo o acusaria junto com "automatica".
            r"\b(" + "|".join(sorted(strings.WORDS_REQUIRING_ACCENTS, key=len, reverse=True)) + r")s?\b",
            re.IGNORECASE,
        )
        faltas: list[str] = []
        for caminho in ARQUIVOS_DE_UI:
            for texto in _literais_visiveis(caminho):
                for achado in padrao.finditer(texto):
                    if achado.group(0).lower() in PERMITIDOS:
                        continue
                    # `@media` e regra CSS, nao portugues. O `@` desambigua sozinho.
                    if achado.start() and texto[achado.start() - 1] == "@":
                        continue
                    faltas.append(f"{caminho.name}: {achado.group(0)!r} em {texto[:60]!r}")

        self.assertEqual(faltas, [], "Strings de UI sem acento:\n" + "\n".join(faltas[:20]))

    def test_the_word_list_itself_is_unaccented(self) -> None:
        """Ela lista as formas **erradas**; acentuá-la faria o teste acima nunca falhar."""
        for palavra in strings.WORDS_REQUIRING_ACCENTS:
            with self.subTest(palavra=palavra):
                self.assertEqual(palavra, palavra.encode("ascii", "ignore").decode("ascii"))


class VocabularyTests(unittest.TestCase):
    def test_every_side_source_the_pipeline_produces_has_a_label(self) -> None:
        """As três da S-17 mais as duas que só a interface cria."""
        for fonte in ("text", "legality", "default", "manual", "queue"):
            with self.subTest(fonte=fonte):
                self.assertTrue(strings.side_source_label(fonte))

    def test_a_conflict_is_not_a_provenance_and_has_its_own_wording(self) -> None:
        """A discordância da S-17 não é "de onde veio": é "duas fontes se contradizem"."""
        conflito = strings.side_source_label("text", conflicting=True)
        self.assertNotEqual(conflito, strings.side_source_label("text"))
        self.assertIn("discordam", conflito)

    def test_an_unknown_source_yields_no_label_instead_of_a_wrong_one(self) -> None:
        self.assertEqual(strings.side_source_label("inventado"), "")

    def test_detection_sources_read_as_prose_not_as_keys(self) -> None:
        """"embedded" é o valor interno da S-12; o usuário não tem por que conhecê-lo."""
        self.assertIn("embutida", strings.detection_source_label("embedded"))
        self.assertIn("contorno", strings.detection_source_label("contour"))

    def test_an_unknown_detection_source_falls_back_to_the_raw_value(self) -> None:
        """Melhor mostrar a chave crua do que esconder que existe uma fonte nova."""
        self.assertEqual(strings.detection_source_label("futuro"), "futuro")

    def test_the_orientation_labels_cover_the_tri_state_of_s13(self) -> None:
        self.assertEqual(set(strings.ORIENTATION_LABELS), {"auto", "0", "180"})


class NoDuplicateVocabularyTests(unittest.TestCase):
    """Os rótulos existiam em dois lugares e já tinham divergido em quatro dos cinco."""

    def test_neither_frontend_keeps_its_own_copy_of_the_side_source_labels(self) -> None:
        for caminho in (RAIZ / "app_streamlit.py", RAIZ / "src" / "chess_diagram_ocr" / "ui" / "result_panel.py"):
            with self.subTest(arquivo=caminho.name):
                fonte = caminho.read_text(encoding="utf-8")
                # A frase completa só pode aparecer no vocabulário compartilhado.
                self.assertNotIn(strings.SIDE_SOURCE_LABELS["legality"], fonte)


if __name__ == "__main__":
    unittest.main()
