"""A correção e a gravação da amostra, na janela do Qt (S-23/S-49/S-318/S-502).

**O que estes testes cobrem, e o que não.** *O que* "salvar" significa -- amostra nova ou
regravar a linha existente, e por qual rota de procedência -- é `DiagramEditorModel.save_target()`,
que é puro e é afirmado em `tests/test_editor_model.py`. A gravação em si é
`OcrService.save_sample`, afirmada em `tests/test_labels.py` e `tests/test_provenance.py`. Repetir
qualquer um dos dois aqui mediria o mesmo código duas vezes.

**Onde ela mora, desde a S-503.** O editor era da janela; virou `qt/painel_de_resultado.py`, e
estes testes o exercitam direto -- um painel que só se testa abrindo a janela inteira é o que a
S-31 tirou do `ChessOcrTkApp`. O que continua passando pela janela é o **vínculo**, porque é ela
que sabe de que página veio o que está aberto.

O que só existe deste lado é a **ligação**, e nela estão os defeitos que um porte reintroduz sem
levantar:

1. a correção precisa ir para o `fen_edits` do editor, e não para o item -- senão ela some ao
   andar para o diagrama seguinte e voltar, que é o laço mais repetido do programa;
2. a posição gravada precisa ser a **corrigida**, e não a que o modelo leu;
3. um erro no repintar depois da gravação não pode virar "falha ao salvar" sobre uma amostra que
   está no disco (S-318) -- a pessoa refaz e o `labels.csv` ganha uma linha duplicada.

**O `labels.csv` destes testes é temporário.** Nenhum deles escreve no do projeto, e a janela
recebe o caminho por `csv_de_rotulos=`.
"""

from __future__ import annotations

import csv
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao

from chess_diagram_ocr.service import RecognizedDiagram
from chess_diagram_ocr.ui import board_edit
from chess_diagram_ocr.ui.editor_model import EditorBinding

if TEM_PYQT:
    from PyQt6.QtWidgets import QMessageBox

    from chess_diagram_ocr.qt.janela import JanelaPrincipal
    from chess_diagram_ocr.qt.painel_de_resultado import PainelDeResultado

INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
LEGAL = "4k3/8/8/8/8/8/8/4K3"
"""Dois reis e nada mais: legal, e a correção de uma casa continua legal."""


def diagrama(placement: str = LEGAL, *, indice: int = 0) -> RecognizedDiagram:
    """Um `RecognizedDiagram` com o recorte que `save_sample` grava em PNG.

    `board_rgb` e não `board_image`: o campo se chama assim desde a S-17, e o nome importa --
    é o recorte do tabuleiro em RGB, e é ele que vira o arquivo da amostra.
    """
    return RecognizedDiagram(
        index=indice,
        board_rgb=np.full((64, 64, 3), 200, np.uint8),
        placement=placement,
        min_confidence=0.99,
        square_confidences=[0.99] * 64,
        side_to_move="w",
    )


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class GravacaoTests(unittest.TestCase):
    """Corrigir e gravar, com o `labels.csv` numa pasta temporária."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.csv = self.pasta / "labels.csv"

        servico = mock.MagicMock()
        servico.save_sample.side_effect = self._gravar_de_mentira
        self.servico = servico
        self.painel = PainelDeResultado(servico, csv_de_rotulos=self.csv)
        self.addCleanup(self.painel.deleteLater)
        self.recados: list[str] = []
        self.painel.estado.connect(self.recados.append)
        self.gravados: list[int] = []
        self.painel.salvou.connect(self.gravados.append)
        self.painel.carregar_pagina(
            [diagrama(indice=0), diagrama(indice=1)], chave="livro.pdf", pagina=0
        )

    def _gravar_de_mentira(self, item, fen, *, csv_path, samples_dir, **resto) -> Path:
        """Escreve uma linha no CSV, como `save_sample` faria. Devolve o caminho do PNG."""
        Path(samples_dir).mkdir(parents=True, exist_ok=True)
        destino = Path(samples_dir) / f"amostra_{item.index}.png"
        destino.write_bytes(b"png de mentira")
        novo = not Path(csv_path).exists()
        with Path(csv_path).open("a", encoding="utf-8", newline="") as arquivo:
            escritor = csv.writer(arquivo)
            if novo:
                escritor.writerow(["arquivo", "fen", "rota"])
            escritor.writerow([destino.name, fen, resto.get("corrected_by", "")])
        return destino

    def linhas_gravadas(self) -> list[list[str]]:
        if not self.csv.exists():
            return []
        with self.csv.open(encoding="utf-8", newline="") as arquivo:
            return list(csv.reader(arquivo))[1:]

    # ------------------------------------------------------------------------- correção

    def test_a_correcao_vai_para_o_editor_e_nao_para_o_item(self) -> None:
        """**A fronteira da S-49.** `fen_edits[i]` é o que se corrige agora; `items[i].placement`
        é o que o modelo leu, e o heatmap e a comparação com o rótulo precisam dele."""
        corrigida = board_edit.set_piece(LEGAL, 27, "Q")
        self.painel._tabuleiro_mudou(corrigida)
        self.assertEqual(self.painel.modelo.fen_at(0), corrigida)
        self.assertEqual(self.painel.modelo.items[0].placement, LEGAL, "o item foi alterado")

    def test_a_correcao_sobrevive_a_ida_e_volta_entre_diagramas(self) -> None:
        """É o laço mais repetido do programa: corrigir, andar, voltar."""
        corrigida = board_edit.set_piece(LEGAL, 27, "Q")
        self.painel._tabuleiro_mudou(corrigida)
        self.painel.lista.setCurrentRow(1)
        self.painel.lista.setCurrentRow(0)
        self.assertEqual(self.painel.modelo.fen_at(0), corrigida)
        self.assertEqual(self.painel.tabuleiro.posicao(), corrigida)

    def test_a_casa_corrigida_acende(self) -> None:
        self.painel._tabuleiro_mudou(board_edit.set_piece(LEGAL, 27, "Q"))
        self.assertEqual(self.painel.tabuleiro.casas_marcadas()["corrigidas"], (27,))

    def test_a_posicao_ilegal_acende_as_casas_culpadas(self) -> None:
        """Mover uma peça pode consertar a leitura e tornar a posição ilegal na mesma jogada."""
        self.painel._tabuleiro_mudou(board_edit.set_piece(LEGAL, 0, "K"))
        self.assertTrue(self.painel.tabuleiro.casas_marcadas()["problematicas"])

    # ------------------------------------------------------------------------- gravação

    def test_salvar_grava_a_posicao_corrigida(self) -> None:
        corrigida = board_edit.set_piece(LEGAL, 27, "Q")
        self.painel._tabuleiro_mudou(corrigida)
        self.painel.salvar_atual()

        linhas = self.linhas_gravadas()
        self.assertEqual(len(linhas), 1)
        self.assertEqual(board_edit.placement_of(linhas[0][1]), corrigida)

    def test_salvar_sem_diagrama_avisa_e_nao_grava(self) -> None:
        """Pré-condição, e não falha: vai para a barra de status, sem caixa (S-164)."""
        self.painel.limpar()
        self.painel.salvar_atual()
        self.assertEqual(self.linhas_gravadas(), [])
        self.assertIn("leia uma página", self.recados[-1])

    def test_a_posicao_legal_nao_pergunta_nada(self) -> None:
        """Colapsar "legal" com "sim, grave assim mesmo" faria toda amostra normal ser gravada
        como ilegal confirmada."""
        with mock.patch.object(QMessageBox, "warning") as caixa:
            self.painel.salvar_atual()
        caixa.assert_not_called()
        self.assertEqual(len(self.linhas_gravadas()), 1)

    def test_a_posicao_ilegal_pergunta_e_o_nao_cancela(self) -> None:
        self.painel._tabuleiro_mudou(board_edit.set_piece(LEGAL, 0, "K"))
        with mock.patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.No):
            self.painel.salvar_atual()
        self.assertEqual(self.linhas_gravadas(), [])
        self.assertIn("cancelada", self.recados[-1])

    def test_a_posicao_ilegal_confirmada_grava(self) -> None:
        self.painel._tabuleiro_mudou(board_edit.set_piece(LEGAL, 0, "K"))
        with mock.patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
            self.painel.salvar_atual()
        self.assertEqual(len(self.linhas_gravadas()), 1)
        self.assertTrue(self.servico.save_sample.call_args.kwargs["allow_illegal"])

    def test_a_falha_de_gravacao_vira_caixa_e_log_e_nao_amostra(self) -> None:
        self.servico.save_sample.side_effect = OSError("o disco encheu")
        with (
            mock.patch.object(QMessageBox, "critical") as caixa,
            self.assertLogs("chess_diagram_ocr.qt.painel_de_resultado", level="ERROR"),
        ):
            self.painel.salvar_atual()
        caixa.assert_called_once()
        self.assertEqual(self.linhas_gravadas(), [])

    def test_o_erro_depois_da_gravacao_nao_diz_que_falhou(self) -> None:
        """**O defeito da S-318.** O `try` cobria o repintar em volta, e um erro ali produzia
        "Falha ao salvar" sobre uma amostra que **está no disco** -- a pessoa refaz, e
        `append_training_sample` sempre acrescenta: uma linha e um PNG duplicados.
        """
        with (
            mock.patch.object(self.painel, "_atualizar_tudo", side_effect=RuntimeError("repintou mal")),
            mock.patch.object(QMessageBox, "critical") as caixa,
        ):
            with self.assertRaises(RuntimeError):
                self.painel.salvar_atual()
        caixa.assert_not_called()
        self.assertEqual(len(self.linhas_gravadas()), 1, "a amostra tinha de estar no disco")

    def test_o_diagrama_salvo_fica_marcado(self) -> None:
        self.painel.salvar_atual()
        self.assertEqual(self.gravados, [0])

    def test_salvar_usa_a_rota_de_procedencia_que_o_modelo_decidiu(self) -> None:
        """Quem decide a rota é `save_target()`; esta janela repassa o que ele mandou."""
        self.painel._tabuleiro_mudou(board_edit.set_piece(LEGAL, 27, "Q"))
        alvo = self.painel.modelo.save_target()
        self.painel.salvar_atual()
        self.assertEqual(self.servico.save_sample.call_args.kwargs["corrected_by"], alvo.route)

    def test_o_botao_de_salvar_desliga_sem_diagrama(self) -> None:
        self.assertTrue(self.painel.btn_salvar.isEnabled())
        self.painel.limpar()
        self.assertFalse(self.painel.btn_salvar.isEnabled())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class VinculoTests(unittest.TestCase):
    """O vínculo do editor, que é o que separa amostra nova de regravação (S-23)."""

    def setUp(self) -> None:
        self.app = aplicacao()
        pasta = pasta_temporaria(self)
        self.janela = JanelaPrincipal(
            servico=mock.MagicMock(),
            csv_de_rotulos=pasta / "l.csv",
            caminho_do_cache=pasta / "posicoes.sqlite",
        )
        self.addCleanup(self.janela.deleteLater)

    def test_a_pagina_lida_vincula_por_pagina(self) -> None:
        """`Ctrl+S` numa página de PDF grava **amostra nova**; o vínculo é quem diz isso."""
        self.janela._pdf = Path("livro.pdf")
        self.janela._chegaram_itens(0, [diagrama()], None)
        self.assertIs(self.janela.editor.binding, EditorBinding.PAGE)
        self.assertIsNone(self.janela.editor.editing_sample)
        self.assertIsNone(self.janela.editor.review_position)

    def test_a_origem_gravada_e_a_da_pagina(self) -> None:
        self.janela._pdf = Path("livro.pdf")
        # A tela precisa estar **na** página cuja leitura chegou: `_chegaram_itens` descarta um
        # resultado que chega depois de a pessoa virar a página, e é isso que impede a amostra
        # de ser gravada com a origem da página errada.
        self.janela.pdf._page_index = 3
        self.janela._chegaram_itens(3, [diagrama()], None)
        origem = self.janela.editor.origin
        self.assertIsNotNone(origem)
        self.assertEqual(origem.page_index, 3)

    def test_a_leitura_de_outra_pagina_nao_carrega_o_editor(self) -> None:
        """O outro lado do mesmo guard, e é ele que protege a procedência da amostra."""
        self.janela._pdf = Path("livro.pdf")
        self.janela.pdf._page_index = 0
        self.janela._chegaram_itens(7, [diagrama()], None)
        self.assertIsNone(self.janela.editor.origin)
        self.assertIn("já está em outra", self.janela.rodape.mensagem())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
