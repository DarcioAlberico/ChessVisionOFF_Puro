"""A aba Dataset relê quando alguém olha, e não quando alguém grava (S-116).

`Ctrl+S` avisava a aba Dataset, que chamava `load_rows` sobre o `labels.csv` inteiro **na
thread do Tk e mesmo nunca tendo sido aberta**. Medido nesta máquina sobre 3.936 linhas:

    load_rows (aba Dataset) .......   688.7 ms
    LabelStore.read() .............    29.2 ms
    saved_diagrams_by_page ........     0.2 ms
    TOTAL por Ctrl+S ..............   718.1 ms

É o laço mais interno do projeto -- corrigir, salvar, seta, corrigir --, e ele custava quase um
segundo de janela travada por amostra. O custo cresce com o arquivo que o projeto existe para
fazer crescer.

**Por que estes testes precisam de Tk.** A decisão é "esta aba está na tela?", e quem responde
isso é o `winfo_ismapped` do widget. Um teste sem Tk mediria uma variável booleana que eu mesmo
teria posto -- e não a regra. O que se dirige aqui é a resposta do `ismapped`, que é a entrada
da decisão; o resto é o painel de verdade.
"""

from __future__ import annotations

import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from chess_diagram_ocr.ui import dataset_panel as modulo
from chess_diagram_ocr.ui.dataset_panel import DatasetPanel


class RecargaPreguicosaTests(unittest.TestCase):
    """Uma raiz para a classe, **criada e destruída aqui** -- o molde do `test_gallery_panel`.

    Não é escolha de estilo, e o custo de errar é grande: este módulo roda cedo na ordem
    alfabética, e uma raiz que sobrevivesse a ele deixaria uma segunda viva enquanto os
    módulos seguintes criam e destroem as deles. Nesta máquina isso quebra o Tcl -- 47 testes
    de `test_gallery_panel`, `test_pdf_panel` e `test_result_panel` falharam assim, com
    `image "pyimage1" doesn't exist` e `Can't find a usable tk.tcl`, apontando para os módulos
    errados.
    """

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:  # pragma: no cover - maquina sem display
            raise unittest.SkipTest(f"sem Tk disponível: {exc}") from exc
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.root.destroy()

    def setUp(self) -> None:
        self.leituras = 0
        host = tk.Frame(self.root)
        self.addCleanup(host.destroy)

        def _load_rows(*_args: object, **_kwargs: object) -> list[object]:
            self.leituras += 1
            return []

        remendo = mock.patch.object(modulo, "load_rows", _load_rows)
        remendo.start()
        self.addCleanup(remendo.stop)

        self.painel = DatasetPanel(
            host,
            paths=lambda: (Path("labels.csv"), Path("samples"), Path("splits.csv")),
            on_edit=lambda _linha: None,
            on_status=lambda _texto: None,
        )
        # A raiz do teste e `withdraw()`, entao nada abaixo dela e mapeado de verdade. O que
        # se dirige e a resposta do `ismapped`, que e a entrada da decisao.
        self._visivel = False
        self.painel.winfo_ismapped = lambda: self._visivel  # type: ignore[method-assign]

    def test_gravar_com_a_aba_fechada_nao_le_o_arquivo(self) -> None:
        """**O item numa linha.** Quem nunca abre a aba Dataset nunca paga os 689 ms."""
        self.painel.reload()
        self.painel.reload()
        self.painel.reload()

        self.assertEqual(self.leituras, 0)

    def test_abrir_a_aba_depois_de_gravar_le_uma_vez_so(self) -> None:
        """Três gravações escondidas não viram três leituras: o estado é "mudou", não "quantas"."""
        self.painel.reload()
        self.painel.reload()
        self.painel.reload()

        self._visivel = True
        self.painel._on_map()

        self.assertEqual(self.leituras, 1)

    def test_abrir_a_aba_sem_nada_ter_mudado_nao_le_de_novo(self) -> None:
        """Trocar de aba ida e volta é gesto de navegação, e não pode custar 689 ms cada."""
        self._visivel = True
        self.painel._on_map()
        self.assertEqual(self.leituras, 1, "a primeira vez sempre lê: a aba nasce sem linha nenhuma")

        self.painel._on_map()
        self.painel._on_map()

        self.assertEqual(self.leituras, 1)

    def test_com_a_aba_aberta_gravar_continua_recarregando_na_hora(self) -> None:
        """A preguiça é sobre quem não está olhando. Quem está, vê a amostra nova aparecer."""
        self._visivel = True
        self.painel._on_map()

        self.painel.reload()

        self.assertEqual(self.leituras, 2)

    def test_o_botao_recarregar_continua_lendo(self) -> None:
        """Ele existe justamente para quem mexeu no `labels.csv` por fora."""
        self._visivel = True
        self.painel.reload()
        self.assertEqual(self.leituras, 1)

    def test_o_painel_escuta_o_proprio_map(self) -> None:
        """Sem este vínculo a preguiça vira esquecimento: a aba abriria com a tabela velha.

        O `ttk.Notebook` mapeia e desmapeia o quadro de cada aba ao trocar de aba, e é por isso
        que o sinal chega ao painel sem que a janela principal precise saber de nada.
        """
        self.assertTrue(self.painel.bind("<Map>"), "o painel precisa escutar <Map>")


if __name__ == "__main__":
    unittest.main()
