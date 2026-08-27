"""Marcar a página como "sem diagrama" pergunta antes de descartar a anotação (S-301).

**O defeito.** `annotate_field_page(empty=True)` é o único caminho que monta o rascunho *do
zero* -- todos os outros passam por `_field_draft`, que retoma o que está gravado --, e
`field_eval.upsert_page` substitui a página inteira. Uma folha com diagramas revisados à mão
desaparecia num clique, sem confirmação, sem desfazer e sem que a frase de status dissesse o
que saiu. O botão fica colado em "Anotar página", na mesma linha.

**A metade difícil do item é a condição, e não a caixa.** Página *sem* diagrama é obrigatória
no conjunto de campo (S-41): são as únicas que medem falso positivo, e anotá-las é o gesto mais
repetido de quem monta o conjunto. Uma pergunta no caminho delas seria a fricção que a S-164
removeu de `_on_ocr_empty`. Por isso a guarda lê o **arquivo** e não `_field_draft()` -- que,
sem nada gravado, devolve um rascunho montado a partir das caixas da *tela* e faria a caixa
modal abrir em toda página de prosa que o detector marcou por engano.

Os dois testes que valem são o par: um diz que a pergunta aparece, o outro diz que ela **não**
aparece no gesto normal.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from chess_diagram_ocr.field_eval import AnnotatedDiagram, FieldPage, load_field_set, upsert_page


def _app_tkinter():  # noqa: ANN202
    """`app_tkinter.py` mora na raiz e não é pacote; o pytest só põe `src/` no path."""
    raiz = str(Path(__file__).resolve().parents[1])
    if raiz not in sys.path:
        sys.path.insert(0, raiz)
    import app_tkinter

    return app_tkinter


class _Fonte:
    def __init__(self, nome: str) -> None:
        self.name = nome


def _janela(app_tkinter, page_index: int):  # noqa: ANN001, ANN202
    """A janela reduzida aos métodos que a guarda toca, com os métodos **reais**.

    Mesmo recurso de `test_box_drop._janela`: montar o `ChessOcrTkApp` inteiro exigiria
    checkpoint, PDF e display, e o que se testa aqui é a decisão de perguntar.
    """
    tipo = type(
        "JanelaMinima",
        (),
        {
            "_confirma_apagar_anotacao": app_tkinter.ChessOcrTkApp._confirma_apagar_anotacao,
        },
    )
    janela = tipo()
    janela.pdf_source = _Fonte("Yusupov.pdf")
    janela.page_index = page_index
    return janela


DIAGRAMA = AnnotatedDiagram(bbox=(278.0, 437.8, 427.8, 606.8))


class GuardaDoSemDiagramaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app_tkinter = _app_tkinter()
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.caminho = Path(pasta.name) / "field_set.jsonl"
        remendo = mock.patch.object(self.app_tkinter, "FIELD_SET_PATH", self.caminho)
        remendo.start()
        self.addCleanup(remendo.stop)

    def _grava(self, page: int, diagrams: tuple[AnnotatedDiagram, ...]) -> None:
        upsert_page(
            self.caminho,
            FieldPage(pdf="Yusupov.pdf", page=page, diagrams=diagrams, reviewed=True),
        )

    def test_pagina_com_diagrama_anotado_faz_a_pergunta(self) -> None:
        """E a pergunta diz **quantos** diagramas somem: "tem certeza?" não informa nada."""
        self._grava(14, (DIAGRAMA,))
        janela = _janela(self.app_tkinter, 14)

        with mock.patch.object(self.app_tkinter.messagebox, "askyesno", return_value=False) as caixa:
            self.assertFalse(janela._confirma_apagar_anotacao())

        caixa.assert_called_once()
        corpo = caixa.call_args.args[1]
        self.assertIn("1 diagrama", corpo)
        self.assertIn("15", corpo, "a página é dita ao usuário em base 1, como no resto da tela")

    def test_recusar_a_pergunta_nao_toca_no_arquivo(self) -> None:
        self._grava(14, (DIAGRAMA,))
        janela = _janela(self.app_tkinter, 14)

        with mock.patch.object(self.app_tkinter.messagebox, "askyesno", return_value=False):
            janela._confirma_apagar_anotacao()

        gravadas = load_field_set(self.caminho)
        self.assertEqual([len(pagina.diagrams) for pagina in gravadas], [1])

    def test_pagina_nunca_anotada_nao_pergunta_nada(self) -> None:
        """O gesto normal, e o que impede o conserto de custar mais que o defeito.

        Página sem diagrama é obrigatória no conjunto de campo (S-41), e quem monta o conjunto
        clica neste botão dezenas de vezes seguidas. Uma caixa modal aqui seria a fricção que a
        S-164 removeu.
        """
        janela = _janela(self.app_tkinter, 14)

        with mock.patch.object(self.app_tkinter.messagebox, "askyesno") as caixa:
            self.assertTrue(janela._confirma_apagar_anotacao())

        caixa.assert_not_called()

    def test_pagina_ja_marcada_sem_diagrama_nao_pergunta(self) -> None:
        """Regravar "sem diagrama" sobre "sem diagrama" não descarta nada -- não há o que perder."""
        self._grava(14, ())
        janela = _janela(self.app_tkinter, 14)

        with mock.patch.object(self.app_tkinter.messagebox, "askyesno") as caixa:
            self.assertTrue(janela._confirma_apagar_anotacao())

        caixa.assert_not_called()

    def test_a_anotacao_de_outra_pagina_nao_dispara_a_pergunta(self) -> None:
        """A guarda é por (livro, página): a folha 14 anotada não fala da folha 20."""
        self._grava(14, (DIAGRAMA,))
        janela = _janela(self.app_tkinter, 20)

        with mock.patch.object(self.app_tkinter.messagebox, "askyesno") as caixa:
            self.assertTrue(janela._confirma_apagar_anotacao())

        caixa.assert_not_called()


if __name__ == "__main__":
    unittest.main()
