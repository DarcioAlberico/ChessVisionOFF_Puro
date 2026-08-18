"""A coluna de headers da Galeria cabe, e o piso do painel passou a saber disso (S-154).

**O defeito, e por que ele custava caro.** `corpo` empacotava o centro com `expand=True` e a
lateral **depois**; o `pack` reparte na ordem em que recebe, então o centro tomava tudo e a
lateral ficava com o que sobrasse. Na posição padrão do divisor (42% de 1700) sobravam ~680 px
para ~700 pedidos, e o que era cortado eram os campos que gravam a procedência de uma partida —
o produto da S-83 à S-94 inteira: "Copiar headers para to…", o botão de desfazer, o texto verde
de origem.

**A correção tem duas metades, e a segunda é a que impede a volta.** A primeira é a ordem do
`pack`: a lateral reserva a largura que pede. A segunda é o piso do painel esquerdo, que era
**420** — o número da S-31, escrito quando a Galeria não existia. Um piso que ignora a aba mais
larga é um piso que autoriza cortá-la.

Os testes daqui são de dois tipos, e o segundo é o que envelhece bem: a largura declarada contra
a **medida de verdade** do widget montado. Acrescentar um campo ao PGN passa a falhar aqui, em
vez de reaparecer como uma coluna cortada na tela de alguém.
"""

from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path

from tk_root import raiz

# `app_tkinter.py` mora na raiz e não é pacote; o `pythonpath` do pytest só põe `src/`. Sem
# isto o módulo nem coleta -- e o erro é de coleta, então ele derruba a suíte inteira, não só
# este arquivo. Mesmo gesto do `tests/test_packaging.py`.
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app_tkinter  # noqa: E402 - depende do `sys.path` ajustado acima
from chess_diagram_ocr.service import OcrService  # noqa: E402
from chess_diagram_ocr.ui import geometria
from chess_diagram_ocr.ui.gallery_panel import (
    BOARD_VIEW_SIZE,
    FOLGA_DO_CORPO,
    LARGURA_DA_LATERAL,
    LARGURA_MINIMA_DA_GALERIA,
    GalleryPanel,
)


class DeclaracaoTests(unittest.TestCase):
    """A aritmética do piso, sem janela. É o teste que a spec pede: a soma contra o `minsize`."""

    def test_o_piso_do_painel_esquerdo_cobre_a_galeria(self) -> None:
        """O estado anterior, dito como asserção: 420 não cobria 700, e o teste falharia."""
        self.assertGreaterEqual(
            app_tkinter.LARGURA_MINIMA_ESQUERDA,
            LARGURA_MINIMA_DA_GALERIA,
            "o painel esquerdo pode encolher abaixo do que a Galeria precisa",
        )

    def test_o_piso_e_somado_das_partes_e_nao_escolhido(self) -> None:
        self.assertEqual(LARGURA_MINIMA_DA_GALERIA, BOARD_VIEW_SIZE + LARGURA_DA_LATERAL + FOLGA_DO_CORPO)

    def test_o_420_da_s31_nao_cobria(self) -> None:
        """O número que estava lá, e por que ele não era conservador -- era antigo."""
        self.assertLess(420, LARGURA_MINIMA_DA_GALERIA)

    def test_o_piso_da_janela_acompanhou(self) -> None:
        """Piso de painel que sobe sem o piso da janela subir junto não protege nada."""
        largura, _ = geometria.piso_da_janela(app_tkinter.LARGURA_MINIMA_ESQUERDA, app_tkinter.LARGURA_MINIMA_DIREITA)
        self.assertGreaterEqual(largura, LARGURA_MINIMA_DA_GALERIA + app_tkinter.LARGURA_MINIMA_DIREITA)

    def test_o_piso_ainda_cabe_num_notebook(self) -> None:
        """1366 é a largura que o item nomeia, e um piso maior que ela travaria a janela."""
        largura, _ = geometria.piso_da_janela(app_tkinter.LARGURA_MINIMA_ESQUERDA, app_tkinter.LARGURA_MINIMA_DIREITA)
        self.assertLessEqual(largura, 1366)


class LateralMontadaTests(unittest.TestCase):
    """A lateral de verdade: a largura declarada bate com a medida, e ela não é mais cortada."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.janela = tk.Toplevel(self.root)
        self.janela.geometry(f"{LARGURA_MINIMA_DA_GALERIA}x820")
        self.addCleanup(self.janela.destroy)
        self.painel = GalleryPanel(
            self.janela,
            service=OcrService(model_path=Path("models/piece_classifier.pt")),
            pdf_path=lambda: None,
            model_path=lambda: Path("modelo.pt"),
            max_boards=lambda: 12,
            on_status=lambda _texto: None,
            on_page_request=lambda *_args: None,
        )
        self.painel.pack(fill=tk.BOTH, expand=True)
        self.janela.update()

    def test_a_largura_declarada_cobre_a_que_a_lateral_pede(self) -> None:
        """A amarra que envelhece bem: um campo novo no PGN falha aqui, e não na tela.

        **Cobre, e não iguala.** O `winfo_reqwidth` da lateral depende do tema em uso -- 240 em
        `ttk` puro, 246 sob `bootstrap-light` --, e exigir igualdade faria este teste passar ou
        falhar conforme a ordem em que a suíte roda. O que importa é a reserva nunca ficar
        **curta**; o teto ao lado é o que impede a folga de crescer em silêncio até virar espaço
        morto na tela.
        """
        pedida = self.painel.lateral.winfo_reqwidth()
        self.assertGreaterEqual(
            LARGURA_DA_LATERAL, pedida, "a lateral pede mais do que a reserva: ela sai cortada"
        )
        self.assertLessEqual(LARGURA_DA_LATERAL - pedida, 40, "a reserva virou folga sem dono")

    def test_a_lateral_recebe_a_largura_que_pede(self) -> None:
        """O defeito fotografado, dito com número: ela recebia menos do que pedia.

        Contra o `reqwidth` e não contra a constante: a constante é a **reserva** que o piso do
        painel soma; o que a lateral recebe do `pack` é o que ela pede.
        """
        self.assertGreaterEqual(self.painel.lateral.winfo_width(), self.painel.lateral.winfo_reqwidth())

    def test_os_campos_de_header_estao_inteiros(self) -> None:
        """Não basta a moldura caber: o que se recorta são os `Entry` de dentro dela."""
        cortados = [
            filho
            for filho in self.painel.lateral.winfo_children()
            if filho.winfo_ismapped() and filho.winfo_width() < filho.winfo_reqwidth()
        ]
        self.assertEqual([], cortados, f"{len(cortados)} controles da lateral saem cortados")

    def test_a_lateral_fica_a_direita_do_recorte(self) -> None:
        """A ordem do `pack` mudou, e a leitura da tela não pode ter mudado junto."""
        self.assertGreater(self.painel.lateral.winfo_rootx(), self.painel.canvas.winfo_rootx())

    def test_o_recorte_continua_inteiro(self) -> None:
        """A correção não pode ter trocado a coluna cortada pelo tabuleiro cortado."""
        self.assertGreaterEqual(self.painel.canvas.winfo_width(), BOARD_VIEW_SIZE)


class LateralEmPainelLargoTests(unittest.TestCase):
    """Com folga, quem cresce é o centro -- a lateral tem largura de formulário, não de imagem."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def test_a_folga_vai_para_o_centro(self) -> None:
        janela = tk.Toplevel(self.root)
        janela.geometry("1180x820")
        self.addCleanup(janela.destroy)
        painel = GalleryPanel(
            janela,
            service=OcrService(model_path=Path("models/piece_classifier.pt")),
            pdf_path=lambda: None,
            model_path=lambda: Path("modelo.pt"),
            max_boards=lambda: 12,
            on_status=lambda _texto: None,
            on_page_request=lambda *_args: None,
        )
        painel.pack(fill=tk.BOTH, expand=True)
        janela.update()

        self.assertEqual(
            painel.lateral.winfo_width(),
            painel.lateral.winfo_reqwidth(),
            "a lateral esticou sem precisar: a folga é do recorte",
        )


if __name__ == "__main__":
    unittest.main()
