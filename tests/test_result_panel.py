"""O campo do número do lance, na aba Resultado (S-71).

O número mora na anotação da galeria, e é lá que a exportação o lê. O que se testa aqui é a
parte que só quebra com widget: o campo seguir o diagrama selecionado, em branco **apagar** em
vez de gravar zero, número inválido avisar sem gravar, e o campo ficar cinza quando o que está
no editor não é o diagrama de uma página -- caso em que gravar apontaria para o diagrama errado.
"""

from __future__ import annotations

import tkinter as tk
import unittest
from pathlib import Path

import numpy as np

from chess_diagram_ocr.config import BUNDLE_ROOT
from chess_diagram_ocr.service import RecognitionOrigin, RecognizedDiagram
from chess_diagram_ocr.settings import RemoteFenSettings
from chess_diagram_ocr.ui import result_panel
from chess_diagram_ocr.ui.board_widget import PieceImages
from chess_diagram_ocr.ui.page_results import PageOcrParams
from chess_diagram_ocr.ui.result_panel import ResultPanel

PLACEMENT = "4k3/8/8/8/8/8/8/4K3"
DOCUMENTO = "livro.pdf"
PAGINA = 16


def _diagrama() -> RecognizedDiagram:
    return RecognizedDiagram.from_label(np.zeros((8, 8, 3), dtype=np.uint8), PLACEMENT)


_RAIZ: tk.Tk | None = None


def _raiz() -> tk.Tk:
    """Uma raiz Tk para o módulo inteiro, criada uma vez e nunca destruída.

    Cada classe criava e destruía a sua. Enquanto houve uma classe só isso funcionou; com
    duas, a segunda `tk.Tk()` do processo caía em `invalid command name "tcl_findLibrary"` --
    reinicializar o Tcl depois de destruir a última raiz não é confiável no Windows. O sintoma
    era pior que a causa: a classe não falhava, era **pulada**, e uma suíte verde escondia
    cinco testes que não rodaram.
    """
    global _RAIZ
    if _RAIZ is None:
        try:
            _RAIZ = tk.Tk()
        except tk.TclError as exc:  # pragma: no cover - maquina sem display
            raise unittest.SkipTest(f"sem Tk disponível: {exc}") from exc
        _RAIZ.withdraw()
    return _RAIZ


class MoveNumberFieldTests(unittest.TestCase):
    """Uma raiz Tk para o módulo, pelo mesmo motivo do `test_gallery_panel` -- ver `_raiz`."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = _raiz()

    def setUp(self) -> None:
        self.status: list[str] = []
        self.lances: dict[tuple[int, int], int | None] = {}
        self.gravacoes: list[tuple[int, int, int | None]] = []
        self.host = tk.Frame(self.root)

        def _gravar(pagina: int, diagrama: int, valor: int | None) -> None:
            self.gravacoes.append((pagina, diagrama, valor))
            if valor is None:
                self.lances.pop((pagina, diagrama), None)
            else:
                self.lances[(pagina, diagrama)] = valor

        self.panel = ResultPanel(
            self.host,
            service=None,  # type: ignore[arg-type] - so a gravacao o usa, e ela nao roda aqui
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
            on_sample_saved=lambda: None,
            remote_fen=RemoteFenSettings,
            on_remote_consent=lambda _cfg: False,
            move_number_of=lambda pagina, diagrama: self.lances.get((pagina, diagrama)),
            on_move_number=_gravar,
        )

    def tearDown(self) -> None:
        self.host.destroy()

    def _abrir_pagina(self, quantos: int = 2) -> None:
        self.panel.show_ocr_results(
            [_diagrama() for _ in range(quantos)],
            RecognitionOrigin.for_page(DOCUMENTO, PAGINA),
        )

    # ------------------------------------------------------------------------ o campo

    def test_sem_nada_no_editor_o_campo_fica_cinza(self) -> None:
        self.assertEqual(str(self.panel.move_number_entry.cget("state")), "disabled")

    def test_com_uma_pagina_aberta_o_campo_liga(self) -> None:
        self._abrir_pagina()
        self.assertEqual(str(self.panel.move_number_entry.cget("state")), "normal")

    def test_grava_o_lance_do_diagrama_selecionado(self) -> None:
        self._abrir_pagina()
        self.panel.move_number_var.set("24")
        self.panel._commit_move_number()
        self.assertEqual(self.gravacoes, [(PAGINA, 0, 24)])

    def test_o_campo_segue_o_diagrama_e_nao_vaza_para_o_vizinho(self) -> None:
        self._abrir_pagina()
        self.panel.move_number_var.set("24")
        self.panel._commit_move_number()

        self.panel.next_diagram()
        self.assertEqual(self.panel.move_number_var.get(), "", "o lance do vizinho não pode vazar")
        self.panel.prev_diagram()
        self.assertEqual(self.panel.move_number_var.get(), "24")

    def test_trocar_de_diagrama_grava_o_que_estava_digitado(self) -> None:
        """O `FocusOut` do campo não dispara quando o foco está no tabuleiro."""
        self._abrir_pagina()
        self.panel.move_number_var.set("31")
        self.panel.next_diagram()
        self.assertEqual(self.lances[(PAGINA, 0)], 31)

    def test_em_branco_apaga_em_vez_de_gravar_zero(self) -> None:
        self._abrir_pagina()
        self.panel.move_number_var.set("24")
        self.panel._commit_move_number()
        self.panel.move_number_var.set("")
        self.panel._commit_move_number()
        self.assertEqual(self.gravacoes[-1], (PAGINA, 0, None))
        self.assertNotIn((PAGINA, 0), self.lances)

    def test_numero_invalido_avisa_e_nao_grava(self) -> None:
        self._abrir_pagina()
        self.panel.move_number_var.set("vinte e quatro")
        self.panel._commit_move_number()
        self.assertEqual(self.gravacoes, [])
        self.assertTrue(any("inválido" in mensagem for mensagem in self.status))

    def test_lance_zero_ou_negativo_tambem_e_invalido(self) -> None:
        self._abrir_pagina()
        for texto in ("0", "-3"):
            with self.subTest(texto=texto):
                self.panel.move_number_var.set(texto)
                self.panel._commit_move_number()
                self.assertEqual(self.gravacoes, [])

    def test_o_campo_volta_ao_valor_gravado_depois_de_recusar(self) -> None:
        self._abrir_pagina()
        self.panel.move_number_var.set("12")
        self.panel._commit_move_number()
        self.panel.move_number_var.set("doze")
        self.panel._commit_move_number()
        self.assertEqual(self.panel.move_number_var.get(), "12")

    def test_regravar_o_mesmo_numero_nao_escreve_de_novo(self) -> None:
        """O campo confirma no `FocusOut`, que dispara a cada passagem do foco."""
        self._abrir_pagina()
        self.panel.move_number_var.set("7")
        self.panel._commit_move_number()
        self.panel._commit_move_number()
        self.panel._commit_move_number()
        self.assertEqual(len(self.gravacoes), 1)

    def test_recorte_de_area_nao_tem_onde_gravar_o_lance(self) -> None:
        """Recorte não é o diagrama N da página N: gravar apontaria para outro diagrama."""
        self.panel.show_ocr_results(
            [_diagrama()], RecognitionOrigin.for_crop(DOCUMENTO, PAGINA, (0, 0, 10, 10))
        )
        self.assertEqual(str(self.panel.move_number_entry.cget("state")), "disabled")
        self.panel.move_number_var.set("24")
        self.panel._commit_move_number()
        self.assertEqual(self.gravacoes, [])


class _ServicoFalso:
    """Só o que a gravação usa. `save_sample` guarda como foi chamada."""

    def __init__(self) -> None:
        self.chamadas: list[dict] = []

    def save_sample(self, diagram, fen, **kwargs) -> Path:  # noqa: ANN001, ANN003
        self.chamadas.append({"fen": fen, **kwargs})
        return Path("data/samples/board_000.png")


class _CaixasFalsas:
    """Substitui o `messagebox` do painel: responde o que o teste mandar e anota o que viu."""

    NO = "no"
    WARNING = "warning"

    def __init__(self, resposta: bool) -> None:
        self.resposta = resposta
        self.perguntas: list[str] = []
        self.avisos: list[str] = []

    def askyesno(self, _titulo, mensagem, **_kwargs) -> bool:  # noqa: ANN001, ANN003
        self.perguntas.append(mensagem)
        return self.resposta

    def showinfo(self, _titulo, mensagem, **_kwargs) -> None:  # noqa: ANN001, ANN003
        self.avisos.append(mensagem)

    showerror = showinfo
    showwarning = showinfo


class ConfirmacaoDePosicaoIlegalTests(unittest.TestCase):
    """Salvar uma posição ilegal passou a ser uma pergunta, e não uma recusa.

    O que estes testes fixam é a consequência da resposta: "sim" grava **com** a marca da
    `ILLEGAL_OK` (sem ela o treino descartaria a amostra e o `cvoff-audit --fix` a tiraria do
    arquivo), e "não" não grava nada.
    """

    root: tk.Tk

    ESTRUTURA = "8/pp3ppp/8/8/8/8/PP3PPP/8"  # capítulo de estrutura: nenhum rei

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = _raiz()

    def _painel(self, *, resposta: bool) -> tuple[object, _ServicoFalso, _CaixasFalsas]:
        servico = _ServicoFalso()
        caixas = _CaixasFalsas(resposta)
        host = tk.Frame(self.root)
        self.addCleanup(host.destroy)
        painel = ResultPanel(
            host,
            service=servico,  # type: ignore[arg-type]
            piece_images=PieceImages(BUNDLE_ROOT / "assets" / "piece_images"),
            paths=lambda: (Path("labels.csv"), Path("samples")),
            ocr_params=lambda: PageOcrParams(dpi=220, max_boards=12, orientation="auto", model_path="m.pt"),
            document_key=lambda: DOCUMENTO,
            model_path=lambda: Path("m.pt"),
            on_status=lambda _mensagem: None,
            on_ocr_local=lambda _max: None,
            max_boards=lambda: 12,
            on_sync_study=lambda: None,
            on_state_changed=lambda: None,
            on_focus_request=lambda: None,
            on_sample_saved=lambda: None,
            remote_fen=RemoteFenSettings,
            on_remote_consent=lambda _cfg: False,
            move_number_of=lambda _pagina, _diagrama: None,
            on_move_number=lambda *_args: None,
        )
        # O painel usa o `messagebox` do modulo; trocar o atributo do modulo e o que permite
        # dirigir a resposta sem abrir caixa nenhuma.
        original = result_panel.messagebox
        result_panel.messagebox = caixas  # type: ignore[assignment]
        self.addCleanup(setattr, result_panel, "messagebox", original)
        return painel, servico, caixas

    def _abrir(self, painel, placements: list[str]) -> None:  # noqa: ANN001
        painel.show_ocr_results(
            [RecognizedDiagram.from_label(np.zeros((8, 8, 3), dtype=np.uint8), p) for p in placements],
            RecognitionOrigin.for_page(DOCUMENTO, PAGINA),
        )

    def test_uma_posicao_legal_nao_pergunta_nada(self) -> None:
        painel, servico, caixas = self._painel(resposta=False)
        self._abrir(painel, [PLACEMENT])

        painel.save_current()

        self.assertEqual(caixas.perguntas, [])
        self.assertEqual(len(servico.chamadas), 1)
        self.assertFalse(servico.chamadas[0]["allow_illegal"])

    def test_sim_grava_a_posicao_ilegal(self) -> None:
        painel, servico, caixas = self._painel(resposta=True)
        self._abrir(painel, [self.ESTRUTURA])

        painel.save_current()

        self.assertEqual(len(caixas.perguntas), 1)
        self.assertIn("falta o rei branco", caixas.perguntas[0])
        self.assertTrue(servico.chamadas[0]["allow_illegal"])

    def test_nao_cancela_a_gravacao(self) -> None:
        painel, servico, caixas = self._painel(resposta=False)
        self._abrir(painel, [self.ESTRUTURA])

        painel.save_current()

        self.assertEqual(len(caixas.perguntas), 1)
        self.assertEqual(servico.chamadas, [])

    def test_salvar_todos_pergunta_uma_vez_so(self) -> None:
        """Oito diagramas de estrutura numa página não podem virar oito caixas iguais."""
        painel, servico, caixas = self._painel(resposta=True)
        self._abrir(painel, [self.ESTRUTURA] * 3 + [PLACEMENT])

        painel.save_all()

        self.assertEqual(len(caixas.perguntas), 1)
        self.assertEqual(len(servico.chamadas), 4)
        self.assertEqual([c["allow_illegal"] for c in servico.chamadas], [True, True, True, False])

    def test_salvar_todos_com_nao_grava_so_o_que_e_legal(self) -> None:
        painel, servico, caixas = self._painel(resposta=False)
        self._abrir(painel, [self.ESTRUTURA, PLACEMENT])

        painel.save_all()

        self.assertEqual(len(caixas.perguntas), 1)
        self.assertEqual(len(servico.chamadas), 1)
        self.assertFalse(servico.chamadas[0]["allow_illegal"])


if __name__ == "__main__":
    unittest.main()
