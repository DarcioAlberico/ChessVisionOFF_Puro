"""Marcar a página como "sem diagrama" pergunta antes de descartar a anotação (S-301).

**O defeito.** `anotar_sem_diagrama` é o único caminho que monta o rascunho *do zero* -- todos os
outros passam por `_rascunho`, que retoma o que está gravado --, e
`field_eval.upsert_page` substitui a página inteira. Uma folha com diagramas revisados à mão
desaparecia num clique, sem confirmação, sem desfazer e sem que a frase de status dissesse o
que saiu. O botão fica colado em "Anotar página", na mesma linha.

**A metade difícil do item é a condição, e não a caixa.** Página *sem* diagrama é obrigatória
no conjunto de campo (S-41): são as únicas que medem falso positivo, e anotá-las é o gesto mais
repetido de quem monta o conjunto. Uma pergunta no caminho delas seria a fricção que a S-164
removeu de `_on_ocr_empty`. Por isso a guarda lê o **arquivo** e não `_rascunho()` -- que,
sem nada gravado, devolve um rascunho montado a partir das caixas da *tela* e faria a caixa
modal abrir em toda página de prosa que o detector marcou por engano.

Os dois testes que valem são o par: um diz que a pergunta aparece, o outro diz que ela **não**
aparece no gesto normal.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.field_eval import AnnotatedDiagram, FieldPage, load_field_set, upsert_page

if TEM_PYQT:
    from PyQt6.QtWidgets import QMessageBox

    from chess_diagram_ocr.qt.campo import PainelDeCampo

DIAGRAMA = AnnotatedDiagram(bbox=(278.0, 437.8, 427.8, 606.8))


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class GuardaDoSemDiagramaTests(unittest.TestCase):
    """**O conjunto é o de mentira, e isso é o item.** Anotar no `data/field_set.jsonl` de verdade
    de dentro da suíte estragaria a referência que os quatro relatórios de campo medem."""

    def setUp(self) -> None:
        self.app = aplicacao()
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.caminho = Path(pasta.name) / "field_set.jsonl"

    def _painel(self, pagina: int) -> PainelDeCampo:
        """O painel de verdade -- só o conjunto e o contexto é que são de teste.

        Montar a janela inteira exigiria checkpoint, PDF e tela, e o que se mede aqui é a decisão
        de perguntar. O painel recebe o contexto por função justamente para isto ser possível.
        """
        montado = PainelDeCampo(
            pdf_path=lambda: Path("Yusupov.pdf"),
            page_index=lambda: pagina,
            caixas=lambda: None,
            caixa_selecionada=lambda: None,
            colocacoes=dict,
            caminho_do_conjunto=self.caminho,
        )
        self.addCleanup(descartar, montado)
        return montado

    def _grava(self, page: int, diagrams: tuple[AnnotatedDiagram, ...]) -> None:
        upsert_page(
            self.caminho,
            FieldPage(pdf="Yusupov.pdf", page=page, diagrams=diagrams, reviewed=True),
        )

    def test_pagina_com_diagrama_anotado_faz_a_pergunta(self) -> None:
        """E a pergunta diz **quantos** diagramas somem: "tem certeza?" não informa nada."""
        self._grava(14, (DIAGRAMA,))
        painel = self._painel(14)

        with mock.patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.No
        ) as caixa:
            self.assertFalse(painel._confirmar_apagar_anotacao())

        caixa.assert_called_once()
        corpo = caixa.call_args.args[2]
        self.assertIn("1 diagrama", corpo)
        self.assertIn("15", corpo, "a página é dita ao usuário em base 1, como no resto da tela")

    def test_recusar_a_pergunta_nao_toca_no_arquivo(self) -> None:
        self._grava(14, (DIAGRAMA,))
        painel = self._painel(14)

        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            painel._confirmar_apagar_anotacao()

        gravadas = load_field_set(self.caminho)
        self.assertEqual([len(pagina.diagrams) for pagina in gravadas], [1])

    def test_pagina_nunca_anotada_nao_pergunta_nada(self) -> None:
        """O gesto normal, e o que impede o conserto de custar mais que o defeito.

        Página sem diagrama é obrigatória no conjunto de campo (S-41), e quem monta o conjunto
        clica neste botão dezenas de vezes seguidas. Uma caixa modal aqui seria a fricção que a
        S-164 removeu.
        """
        painel = self._painel(14)

        with mock.patch.object(QMessageBox, "question") as caixa:
            self.assertTrue(painel._confirmar_apagar_anotacao())

        caixa.assert_not_called()

    def test_pagina_ja_marcada_sem_diagrama_nao_pergunta(self) -> None:
        """Regravar "sem diagrama" sobre "sem diagrama" não descarta nada -- não há o que perder."""
        self._grava(14, ())
        painel = self._painel(14)

        with mock.patch.object(QMessageBox, "question") as caixa:
            self.assertTrue(painel._confirmar_apagar_anotacao())

        caixa.assert_not_called()

    def test_a_anotacao_de_outra_pagina_nao_dispara_a_pergunta(self) -> None:
        """A guarda é por (livro, página): a folha 14 anotada não fala da folha 20."""
        self._grava(14, (DIAGRAMA,))
        painel = self._painel(20)

        with mock.patch.object(QMessageBox, "question") as caixa:
            self.assertTrue(painel._confirmar_apagar_anotacao())

        caixa.assert_not_called()


if __name__ == "__main__":
    unittest.main()
