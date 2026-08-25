"""Desfazer e refazer a edição do tabuleiro (S-229).

**A função que faltava, e o registro do que custa não tê-la.** Antes deste item, `grep -rn 'undo'
src/` devolvia zero linhas de implementação -- os únicos acertos eram comentários. A Imagem 2 põe
Desfazer, Refazer e Limpar no grupo Edição, e nenhum dos três existia. A S-76 é o registro do custo:
um clique sobrescreveu 1.405 diagramas de trabalho humano.

O que se afirma aqui são as duas metades. A pilha, sem janela: ela é de **estados** e não de
gestos, e por isso não precisa saber inverter operação nenhuma. E o painel, com janela: as **sete
origens de mudança** entram nela, salvar não entra, e trocar de diagrama a zera.
"""

from __future__ import annotations

import tkinter as tk
import unittest
from pathlib import Path

import numpy as np
from tk_root import raiz as raiz_do_processo

from chess_diagram_ocr.config import BUNDLE_ROOT
from chess_diagram_ocr.service import RecognitionOrigin, RecognizedDiagram
from chess_diagram_ocr.settings import RemoteFenSettings
from chess_diagram_ocr.ui import atalhos, board_edit, comandos, historico, menu
from chess_diagram_ocr.ui.board_widget import PieceImages
from chess_diagram_ocr.ui.page_results import PageOcrParams
from chess_diagram_ocr.ui.result_panel import ResultPanel

PLACEMENT = "4k3/8/8/8/8/8/8/4K3"
"""Dois reis, nas casas e8 e e1. Índice 4 é e8; índice 60 é e1."""

OUTRA = "4k3/8/8/8/8/8/4Q3/4K3"
DOCUMENTO = "livro.pdf"
PAGINA = 16


class _ServicoDeMentira:
    """O mínimo de `OcrService` que a gravação usa: `save_sample`, e nada mais.

    Existe para que `test_salvar_nao_entra_no_historico` percorra o caminho de gravação de
    verdade em vez de afirmar sobre um caminho que não rodou -- e sem escrever no `labels.csv`
    da máquina de quem roda a suíte.
    """

    def __init__(self, registro: list[tuple[str, str]]) -> None:
        self._registro = registro

    def save_sample(self, _diagrama: object, fen: str, **_kwargs: object) -> Path:
        self._registro.append(("salvou", board_edit.placement_of(fen)))
        return Path("samples") / "gravado.png"


class PilhaDePosicoesTests(unittest.TestCase):
    """A pilha sozinha: sem `tkinter`, sem painel, sem widget."""

    def test_desfazer_devolve_a_posicao_anterior(self) -> None:
        pilha = historico.Historico(PLACEMENT)
        pilha.registrar(OUTRA)
        self.assertEqual(PLACEMENT, pilha.desfazer())
        self.assertEqual(PLACEMENT, pilha.atual)

    def test_refazer_devolve_o_que_o_desfazer_tirou(self) -> None:
        pilha = historico.Historico(PLACEMENT)
        pilha.registrar(OUTRA)
        pilha.desfazer()
        self.assertEqual(OUTRA, pilha.refazer())
        self.assertEqual(OUTRA, pilha.atual)

    def test_edicao_nova_descarta_o_refazer(self) -> None:
        """A regra de toda pilha de desfazer: o futuro que ela guardava é de uma linha do tempo
        que acabou de deixar de existir."""
        pilha = historico.Historico(PLACEMENT)
        pilha.registrar(OUTRA)
        pilha.desfazer()
        self.assertTrue(pilha.pode_refazer)
        pilha.registrar(board_edit.EMPTY_PLACEMENT)
        self.assertFalse(pilha.pode_refazer)
        self.assertIsNone(pilha.refazer())

    def test_nas_pontas_ele_recusa_em_vez_de_inventar(self) -> None:
        pilha = historico.Historico(PLACEMENT)
        self.assertIsNone(pilha.desfazer())
        self.assertIsNone(pilha.refazer())
        self.assertFalse(pilha.pode_desfazer)
        self.assertFalse(pilha.pode_refazer)

    def test_a_posicao_repetida_nao_entra(self) -> None:
        """Um clique que repõe a mesma peça na mesma casa chega como qualquer outro. Registrá-lo
        encheria a pilha de estados idênticos, e o `Ctrl+Z` seguinte não mudaria nada na tela."""
        pilha = historico.Historico(PLACEMENT)
        self.assertFalse(pilha.registrar(PLACEMENT))
        self.assertFalse(pilha.pode_desfazer)

    def test_o_teto_de_cem_estados(self) -> None:
        pilha = historico.Historico(PLACEMENT)
        for numero in range(250):
            pilha.registrar(f"posicao-{numero}")
        self.assertEqual(historico.TETO, pilha.profundidade)
        for _ in range(historico.TETO):
            self.assertIsNotNone(pilha.desfazer())
        self.assertIsNone(pilha.desfazer())

    def test_zerar_esquece_as_duas_pilhas(self) -> None:
        pilha = historico.Historico(PLACEMENT)
        pilha.registrar(OUTRA)
        pilha.desfazer()
        pilha.zerar(board_edit.EMPTY_PLACEMENT)
        self.assertEqual(board_edit.EMPTY_PLACEMENT, pilha.atual)
        self.assertFalse(pilha.pode_desfazer)
        self.assertFalse(pilha.pode_refazer)

    def test_teto_zero_nao_e_pilha(self) -> None:
        with self.assertRaises(ValueError):
            historico.Historico(teto=0)


class DeclaracaoDosTresComandosTests(unittest.TestCase):
    """Os três nascem do catálogo, e daí para o menu, a legenda e a fita **de graça**."""

    def test_os_tres_estao_no_grupo_edicao(self) -> None:
        for acao in ("desfazer", "refazer", "limpar_tabuleiro"):
            with self.subTest(acao=acao):
                self.assertEqual(comandos.EDICAO, comandos.comando(acao).grupo)

    def test_ctrl_z_e_ctrl_y_aparecem_sem_ninguem_escreve_los_la(self) -> None:
        """O critério de aceite: as teclas entram na tabela e chegam ao menu e à legenda pela
        mesma declaração. Duas listas divergiriam -- é o que a S-161 mediu."""
        self.assertEqual("Ctrl+Z", atalhos.acelerador("desfazer"))
        self.assertEqual("Ctrl+Y", atalhos.acelerador("refazer"))
        self.assertIn("desfazer", menu.acoes_declaradas())
        self.assertIn("refazer", menu.acoes_declaradas())
        self.assertIn("limpar_tabuleiro", menu.acoes_declaradas())

    def test_limpar_nao_e_apagar_casa(self) -> None:
        """Um apaga **uma casa** e o outro esvazia a posição. São dois comandos porque são duas
        perguntas diferentes, e a S-229 lista as duas entre as sete origens de mudança."""
        self.assertNotEqual(
            comandos.comando("apagar_casa").icone, comandos.comando("limpar_tabuleiro").icone
        )


class SeteOrigensNoPainelTests(unittest.TestCase):
    """O painel: as sete origens entram na pilha, salvar não entra, e trocar de diagrama a zera."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz_do_processo()

    def setUp(self) -> None:
        self.status: list[str] = []
        self.gravou: list[tuple[str, str]] = []
        self.host = tk.Frame(self.root)
        self.addCleanup(self.host.destroy)
        self.panel = ResultPanel(
            self.host,
            service=_ServicoDeMentira(self.gravou),  # type: ignore[arg-type] - só `save_sample`
            piece_images=PieceImages(BUNDLE_ROOT / "assets" / "piece_images"),
            paths=lambda: (Path("labels.csv"), Path("samples")),
            ocr_params=lambda: PageOcrParams(dpi=220, max_boards=12, orientation="auto", model_path="m.pt"),
            document_key=lambda: DOCUMENTO,
            model_path=lambda: Path("m.pt"),
            on_status=self.status.append,
            on_ocr_local=lambda _max: None,
            max_boards=lambda: 12,
            on_sync_study=lambda: None,
            on_state_changed=lambda: None,
            on_focus_request=lambda: None,
            on_sample_saved=lambda _gravadas: None,
            remote_fen=RemoteFenSettings,
            on_remote_consent=lambda _cfg: False,
        )

    def _abrir(self, quantos: int = 2) -> None:
        self.panel.show_ocr_results(
            [RecognizedDiagram.from_label(np.zeros((8, 8, 3), dtype=np.uint8), PLACEMENT) for _ in range(quantos)],
            RecognitionOrigin.for_page(DOCUMENTO, PAGINA),
        )

    def _placement(self) -> str:
        return board_edit.placement_of(self.panel.model.fen_at())

    # ------------------------------------------------------------------- as sete origens

    def _mao(self) -> None:
        """Pôr uma peça numa casa vazia -- o clique com o pincel escolhido."""
        self.panel.on_board_changed(board_edit.set_piece(self._placement(), 36, "Q"))

    def _arraste(self) -> None:
        """Arrastar o rei de e8 para d8. O widget entrega a posição de depois."""
        self.panel.on_board_changed(board_edit.move_piece(self._placement(), 4, 3))

    def _apagar_casa(self) -> None:
        self.panel.on_board_changed(board_edit.clear_square(self._placement(), 4))

    def _fen(self) -> None:
        self.panel.fen_var.set(OUTRA)
        self.panel.apply_fen_edit()

    def _limpar(self) -> None:
        self.panel.limpar_tabuleiro()

    def _segunda_opiniao(self) -> None:
        self.panel._apply_second_opinion(self.panel.model.clamped_index(), OUTRA)

    def _correcao_de_rede(self) -> None:
        self.panel._apply_corrected_fen(self.panel.model.clamped_index(), OUTRA)

    def test_desfazer_devolve_a_posicao_anterior(self) -> None:
        """As sete, uma a uma. **É a lista do critério de aceite**, e ela é parametrizada de
        propósito: uma origem nova que esqueça de registrar falha aqui e não seis meses depois."""
        origens = {
            "mão": self._mao,
            "arraste": self._arraste,
            "apagar casa": self._apagar_casa,
            "FEN": self._fen,
            "limpar": self._limpar,
            "segunda opinião": self._segunda_opiniao,
            "correção de rede": self._correcao_de_rede,
        }
        for nome, mudar in origens.items():
            with self.subTest(origem=nome):
                self._abrir()
                antes = self._placement()
                mudar()
                self.assertNotEqual(antes, self._placement(), "a origem não mudou a posição")
                self.panel.desfazer()
                self.assertEqual(antes, self._placement())
                self.assertEqual(antes, self.panel.board.placement)

    def test_refazer_devolve_o_que_o_desfazer_tirou(self) -> None:
        self._abrir()
        self._mao()
        depois = self._placement()
        self.panel.desfazer()
        self.panel.refazer()
        self.assertEqual(depois, self._placement())
        self.assertEqual(depois, self.panel.board.placement)

    def test_edicao_nova_descarta_o_refazer(self) -> None:
        self._abrir()
        self._mao()
        self.panel.desfazer()
        self._arraste()
        self.assertFalse(self.panel.historico.pode_refazer)

    def test_trocar_de_diagrama_zera_o_historico(self) -> None:
        """Desfazer para dentro de outra posição é pior que não desfazer: a pessoa apertaria
        `Ctrl+Z` esperando a casa de trás e receberia o tabuleiro do diagrama anterior."""
        self._abrir(quantos=2)
        self._mao()
        self.assertTrue(self.panel.historico.pode_desfazer)
        self.panel.next_diagram()
        self.assertFalse(self.panel.historico.pode_desfazer)
        self.assertFalse(self.panel.historico.pode_refazer)

    def test_salvar_nao_entra_no_historico(self) -> None:
        """Gravar em `labels.csv` é outra ação, com outro destino e outra reversão -- e confundir
        as duas é como se perderiam 1.405 linhas de novo (S-76).

        A gravação roda de verdade, contra um serviço de mentira: o que se afirma é que ela
        **não** empilha nada, e um `assertEqual` sobre a profundidade só vale se o caminho de
        gravação foi mesmo percorrido.
        """
        self._abrir()
        self._mao()
        antes = self.panel.historico.profundidade
        posicao = self._placement()

        self.panel.save_current()

        self.assertEqual([("salvou", posicao)], self.gravou, "o caminho de gravação não rodou")
        self.assertEqual(antes, self.panel.historico.profundidade)
        self.assertEqual(posicao, self.panel.historico.atual)
        # E o que estava empilhado continua desfazível: salvar não fecha o histórico.
        self.panel.desfazer()
        self.assertNotEqual(posicao, self._placement())

    def test_desfazer_sem_o_que_desfazer_diz_e_nao_estraga(self) -> None:
        self._abrir()
        antes = self._placement()
        self.panel.desfazer()
        self.assertEqual(antes, self._placement())
        self.assertTrue(any("desfazer" in frase.casefold() for frase in self.status))

    def test_limpar_esvazia_as_64_casas(self) -> None:
        self._abrir()
        self.panel.limpar_tabuleiro()
        self.assertEqual(board_edit.EMPTY_PLACEMENT, self._placement())
        self.assertEqual(board_edit.EMPTY_PLACEMENT, self.panel.board.placement)

    # -------------------------------------------------------- os botões e o motivo do cinza

    def test_os_botoes_ficam_cinzas_e_dizem_por_que(self) -> None:
        """A regra da S-165: um botão cinza sem explicação é pior que um botão ausente.

        As duas razões são diferentes e a pessoa precisa saber qual é a dela -- sem diagrama
        aberto não há posição nenhuma; com diagrama e a pilha vazia, não há mudança anterior
        **neste** diagrama, que é a consequência de a pilha ser por diagrama.
        """
        self.assertEqual("disabled", str(self.panel.btn_desfazer.cget("state")))
        sem_diagrama = self.panel._dicas_de_historico["desfazer"].text
        self.assertIn("diagrama aberto", sem_diagrama)

        self._abrir()
        self.assertEqual("disabled", str(self.panel.btn_desfazer.cget("state")))
        self.assertIn("por diagrama", self.panel._dicas_de_historico["desfazer"].text)

        self._mao()
        self.assertEqual("normal", str(self.panel.btn_desfazer.cget("state")))
        self.assertEqual("disabled", str(self.panel.btn_refazer.cget("state")))

        self.panel.desfazer()
        self.assertEqual("normal", str(self.panel.btn_refazer.cget("state")))

    def test_a_dica_traz_a_tecla(self) -> None:
        """A tecla sai de `ui/atalhos.py` e chega aqui sem ninguém a escrever: é o mesmo caminho
        que leva o acelerador ao menu e a linha à legenda."""
        for acao, tecla in (("desfazer", "Ctrl+Z"), ("refazer", "Ctrl+Y")):
            with self.subTest(acao=acao):
                self.assertIn(tecla, self.panel._dicas_de_historico[acao].text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
