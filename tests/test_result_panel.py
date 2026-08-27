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
from tkinter import ttk

import numpy as np
from tk_root import raiz as raiz_do_processo

from chess_diagram_ocr.config import BUNDLE_ROOT
from chess_diagram_ocr.service import RecognitionOrigin, RecognizedDiagram
from chess_diagram_ocr.settings import RemoteFenSettings
from chess_diagram_ocr.ui import board_edit, result_panel
from chess_diagram_ocr.ui.board_widget import PieceImages
from chess_diagram_ocr.ui.editor_model import EditorBinding
from chess_diagram_ocr.ui.page_results import PageOcrParams
from chess_diagram_ocr.ui.result_panel import ResultPanel

PLACEMENT = "4k3/8/8/8/8/8/8/4K3"
DOCUMENTO = "livro.pdf"
PAGINA = 16


def _diagrama() -> RecognizedDiagram:
    return RecognizedDiagram.from_label(np.zeros((8, 8, 3), dtype=np.uint8), PLACEMENT)


def _raiz() -> tk.Tk:
    """A raiz do processo (`tests/tk_root.py`). Ver o docstring de lá para o porquê."""
    return raiz_do_processo()


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
            on_sample_saved=lambda _gravadas: None,
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
        self.erro: Exception | None = None
        """O que `save_sample` levanta. Existe para a S-318: separar "a gravação falhou" de
        "a tela não pôde ser atualizada" exige poder produzir as duas."""

    def save_sample(self, diagram, fen, **kwargs) -> Path:  # noqa: ANN001, ANN003
        if self.erro is not None:
            raise self.erro
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


def _painel(pai: tk.Misc, *, status: list[str] | None = None) -> ResultPanel:
    """Um `ResultPanel` montado com o mínimo -- o mesmo conjunto de callbacks do teste acima."""
    return ResultPanel(
        pai,
        service=None,  # type: ignore[arg-type] - só a gravação o usa, e ela não roda aqui
        piece_images=PieceImages(BUNDLE_ROOT / "assets" / "piece_images"),
        paths=lambda: (Path("labels.csv"), Path("samples")),
        ocr_params=lambda: PageOcrParams(dpi=220, max_boards=12, orientation="auto", model_path="m.pt"),
        document_key=lambda: DOCUMENTO,
        model_path=lambda: Path("m.pt"),
        on_status=(status if status is not None else []).append,
        on_ocr_local=lambda _max: None,
        max_boards=lambda: 12,
        on_sync_study=lambda: None,
        on_state_changed=lambda: None,
        on_focus_request=lambda: None,
        on_sample_saved=lambda _gravadas: None,
        remote_fen=RemoteFenSettings,
        on_remote_consent=lambda _cfg: False,
    )


class EstadoVazioTests(unittest.TestCase):
    """A aba Resultado ao abrir: **não** mostra posição, e não oferece salvar (S-170).

    O que havia: um tabuleiro completo na posição inicial com o campo de FEN vazio -- o padrão do
    `InteractiveBoard`, nunca sobrescrito porque `update_views` só era chamado depois da primeira
    leitura. Parecia um diagrama reconhecido. Quem clicasse "Salvar posição reconhecida" ali
    gravava a posição inicial no `labels.csv` como se fosse leitura de uma página do livro, e o
    `cvoff-audit` não teria como saber que aquela linha não veio de lugar nenhum.
    """

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = _raiz()

    def setUp(self) -> None:
        self.janela = tk.Toplevel(self.root)
        self.janela.geometry("620x900")
        self.addCleanup(self.janela.destroy)
        self.painel = _painel(self.janela)
        self.painel.pack(fill=tk.BOTH, expand=True)
        self.janela.update()

    def test_sem_diagrama_o_tabuleiro_nao_mostra_posicao_nenhuma(self) -> None:
        self.assertEqual(self.painel.items, [])
        self.assertEqual(self.painel.board.placement, board_edit.EMPTY_PLACEMENT)
        self.assertEqual(self.painel.fen_var.get(), "")

    def test_sem_diagrama_as_acoes_de_salvar_estao_desabilitadas(self) -> None:
        """O critério de aceite: não mostra posição **e** não oferece salvar."""
        for botao in (self.painel.btn_save, self.painel.btn_save_all, self.painel.btn_apply_fen):
            with self.subTest(botao=str(botao.cget("text"))):
                self.assertEqual(str(botao.cget("state")), tk.DISABLED)

    def test_a_frase_diz_o_que_fazer_e_nao_que_esta_vazio(self) -> None:
        """"Sem dados" descreve a tela; o estado vazio útil descreve o gesto seguinte."""
        frase = self.painel.vazio_var.get()
        self.assertIn("Clique num diagrama marcado", frase)
        self.assertIn("OCR", frase)

    def test_com_diagrama_a_frase_some_e_as_acoes_voltam(self) -> None:
        self.painel.show_ocr_results([_diagrama()], RecognitionOrigin.for_page("livro.pdf", 3))
        self.janela.update()

        self.assertEqual(self.painel.vazio_var.get(), "")
        self.assertEqual(str(self.painel.btn_save.cget("state")), tk.NORMAL)
        self.assertNotEqual(self.painel.board.placement, board_edit.EMPTY_PLACEMENT)

    def test_limpar_volta_ao_estado_vazio(self) -> None:
        """`clear()` é o caminho de "nenhum diagrama nesta página": ele tem de desfazer tudo."""
        self.painel.show_ocr_results([_diagrama()], RecognitionOrigin.for_page("livro.pdf", 3))
        self.painel.clear()
        self.janela.update()

        self.assertEqual(self.painel.board.placement, board_edit.EMPTY_PLACEMENT)
        self.assertEqual(str(self.painel.btn_save.cget("state")), tk.DISABLED)
        self.assertTrue(self.painel.vazio_var.get())

    def test_o_rotulo_lance_vem_antes_do_campo(self) -> None:
        """Os dois estavam com `side=RIGHT`, e o `pack` põe o primeiro mais à direita: lia-se
        `[campo] Lance`, ao contrário da ordem de leitura e de todos os outros campos da janela."""
        linha = self.painel.move_number_entry.master
        filhos = list(linha.pack_slaves())
        rotulos = [f for f in filhos if isinstance(f, ttk.Label) and str(f.cget("text")) == "Lance"]
        self.assertEqual(len(rotulos), 1)
        self.assertLess(
            rotulos[0].winfo_rootx(),
            self.painel.move_number_entry.winfo_rootx(),
            "o rótulo continua desenhado à direita do campo",
        )


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
        # Contador no lugar do `lambda: None`: é a única forma de ver o aviso que a S-114
        # descobriu que não acontecia -- ele não deixa rastro na tela nem no serviço.
        self.avisos_de_dataset: list[int] = []
        self.fechados: list[tuple[int, str, str]] = []
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
            on_sample_saved=self.avisos_de_dataset.append,
            remote_fen=RemoteFenSettings,
            on_remote_consent=lambda _cfg: False,
            move_number_of=lambda _pagina, _diagrama: None,
            on_move_number=lambda *_args: None,
        )
        painel.set_review_settler(lambda pos, fen, side: self.fechados.append((pos, fen, side)))
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

    def test_falha_de_tela_nao_e_anunciada_como_falha_de_gravacao(self) -> None:
        """S-318: o `try` cobria também o repintar da aba Dataset e a marca verde no diagrama.

        Um `AttributeError` em qualquer um deles produzia a caixa "Falha ao salvar" sobre uma
        amostra que **está no disco**. A pessoa acredita que perdeu a correção, refaz e salva de
        novo -- e como `append_training_sample` nomeia por timestamp e sempre acrescenta, a
        segunda gravação vira uma linha e um PNG duplicados no `labels.csv`. É o laço mais
        repetido do projeto mentindo sobre o único gesto que ele tem.
        """
        painel, servico, caixas = self._painel(resposta=True)
        painel._on_sample_saved = lambda _g: (_ for _ in ()).throw(AttributeError("painel morto"))
        self._abrir(painel, [PLACEMENT])

        painel.save_current()

        self.assertEqual(len(servico.chamadas), 1, "a gravação aconteceu")
        self.assertEqual(caixas.avisos, [], "e nenhuma caixa disse que ela falhou")

    def test_falha_de_gravacao_continua_avisando(self) -> None:
        """O contrário, e é ele que impede a correção de virar "erro nenhum aparece"."""
        painel, servico, caixas = self._painel(resposta=True)
        servico.erro = OSError("disco cheio")
        self._abrir(painel, [PLACEMENT])

        painel.save_current()

        self.assertEqual(len(caixas.avisos), 1)
        self.assertIn("disco cheio", caixas.avisos[0])

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


class SalvarTodosAvisaTests(unittest.TestCase):
    """`Ctrl+Shift+S` gravava e não avisava ninguém (S-114).

    `save_all` chamava `_save_one` por diagrama e terminava num `showinfo`. Não chamava
    `_on_sample_saved()` nem `_settle()` -- os dois só existiam em `save_current` e em
    `_rewrite_dataset_row`.

    Quem usa o caminho barato de uma página inteira perdia exatamente o sinal que a S-71
    construiu para responder *"onde eu parei neste livro?"*: as caixas verdes de "já salvo" não
    apareciam, a aba Dataset não via as amostras novas, e o item da fila de revisão não fechava
    -- ela mandava corrigir de novo o que já tinha sido corrigido.
    """

    root: tk.Tk

    ESTRUTURA = "8/pp3ppp/8/8/8/8/PP3PPP/8"

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = _raiz()

    _painel = ConfirmacaoDePosicaoIlegalTests._painel
    _abrir = ConfirmacaoDePosicaoIlegalTests._abrir

    def test_quatro_diagramas_produzem_um_aviso_de_dataset(self) -> None:
        """**Um, e não quatro.** O aviso relê o `labels.csv` inteiro na thread da janela -- é o
        custo que a S-116 vai atacar --, e dispará-lo por item multiplicaria por N o
        travamento que o "salvar todos" existe para evitar. Mesmo raciocínio da pergunta
        única de ilegalidade."""
        painel, servico, _caixas = self._painel(resposta=True)
        self._abrir(painel, [PLACEMENT] * 4)

        painel.save_all()

        self.assertEqual(len(servico.chamadas), 4)
        self.assertEqual(len(self.avisos_de_dataset), 1)

    def test_nada_salvo_nao_avisa(self) -> None:
        """Responder "não" à pergunta de ilegalidade não grava nada, e avisar de nada seria
        mandar a aba Dataset reler 3.935 linhas para descobrir que nada mudou."""
        painel, servico, _caixas = self._painel(resposta=False)
        self._abrir(painel, [self.ESTRUTURA] * 3)

        painel.save_all()

        self.assertEqual(servico.chamadas, [])
        self.assertEqual(self.avisos_de_dataset, [])

    def test_salvar_todos_fecha_o_item_da_fila(self) -> None:
        """O vínculo `REVIEW` carrega um diagrama só, e `Ctrl+Shift+S` sobre ele é uma
        gravação -- mas era a única que não fechava o item, e a fila o devolvia na varredura
        seguinte."""
        painel, servico, _caixas = self._painel(resposta=True)
        painel.model.load(
            [_diagrama()], [PLACEMENT], ["w"], binding=EditorBinding.REVIEW, review_position=7
        )
        painel._after_load()

        painel.save_all()

        self.assertEqual(len(servico.chamadas), 1)
        self.assertEqual([posicao for posicao, _fen, _lado in self.fechados], [7])
        self.assertEqual(len(self.avisos_de_dataset), 1)

    def test_salvar_o_atual_continua_avisando_uma_vez(self) -> None:
        """A guarda do caminho que já funcionava: o item não podia trocar um defeito por outro."""
        painel, _servico, _caixas = self._painel(resposta=True)
        self._abrir(painel, [PLACEMENT, PLACEMENT])

        painel.save_current()

        self.assertEqual(len(self.avisos_de_dataset), 1)


if __name__ == "__main__":
    unittest.main()
