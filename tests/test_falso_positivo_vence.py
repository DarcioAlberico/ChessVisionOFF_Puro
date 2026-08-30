"""O falso positivo que **vence** o diagrama por score, e leva o diagrama junto (S-160).

**O relato.** A página 62 do `Vishy_Anand_Great_Chess_Combinations` -- um diagrama impecável,
1 bit, 300 DPI nativo -- lia `3KRQQ1/2KBRP2/2RKKKQ1/...`: vinte reis, confiança mínima 0,000.
Na interface era pior e mais mudo: a página aparecia **sem diagrama nenhum**.

O diagrama nunca chegava ao classificador. As casas escuras daquele livro são hachura a 45°,
o limiar adaptativo emenda as diagonais das casas vizinhas numa faixa só, e a faixa vencia a
disputa. Duas guardas deviam ter barrado isso, e as duas erravam por um motivo diferente:

1. **A régua do aspecto media a caixa alinhada aos eixos.** Uma faixa de 620×314 px tem
   alongamento 1,98 -- muito além de `ASPECT_MAX` --, mas inclinada a 45° fecha caixa de
   662×659, razão 1,0046. Ela saía **mais quadrada que o tabuleiro** (0,978 contra 0,856) e
   vencia por 0,6423 contra 0,6012.
2. **O piso de contraste de casa da S-143 rodava tarde demais.** Ele morava no laço de
   `detection.hybrid.detect_diagrams`, que percorre o que `detect_boards` **já devolveu** --
   isto é, depois da ordenação por score e da supressão por IoU que acontecem lá dentro. A
   faixa vencia, comia o tabuleiro por sobreposição (IoU 0,49) e só então morria. A guarda
   removia o vencedor depois de o vencedor já ter eliminado o diagrama.

**O que este arquivo trava, e o que não trava.** As duas primeiras classes rodam em qualquer
checkout: uma sobre quad fabricado, outra sobre o fixture versionado `diagrama_em_moldura`. A
terceira lê o livro de verdade e **pula** onde ele não está -- ela é a trava manual de
acurácia daquela página, no espírito do `docs/BASELINE.md`, e não a cobertura de CI. A
cobertura de CI são as duas primeiras, e é de propósito: um teste que só roda na máquina de
quem tem o acervo foi exatamente o buraco que a S-09 fechou.
"""

from __future__ import annotations

import math
import unittest
from pathlib import Path

import cv2
import numpy as np

from chess_diagram_ocr.atomic_io import read_image
from chess_diagram_ocr.board_detection import (
    ASPECT_MAX,
    MIN_CHECKER_CONTRAST,
    _checker_score,
    _contour_geometry_score,
    _small_gray,
    detect_boards,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

LIVRO = ROOT / "PDF" / "Vishy_Anand_Great_Chess_Combinations.pdf"
PAGINA_62 = 62
"""Índice base 0, como o `--page` do `cvoff-infer`. É o №55, Korchnoi -- Anand, impresso "61"."""

FEN_DA_PAGINA_62 = "r7/1p2pkb1/3pb1p1/1P3p2/p1P1P2r/P2K1P2/2R2BP1/1R3B2"
"""Conferida casa a casa contra o render a 600 DPI, e não copiada da saída do modelo.

Duas casas merecem nota porque enganam em miniatura: **d3 é rei branco**, não dama -- a cruz
no topo do desenho é a do rei --, e o bispo da primeira fileira está em **f1**, não em e1.
"""


def _quad_retangulo(largura: float, altura: float, giro_graus: float, centro=(360.0, 360.0)) -> np.ndarray:
    """Um retângulo `largura`×`altura` girado de `giro_graus`, como quad de 4 pontos."""
    meia_l, meia_a = largura / 2.0, altura / 2.0
    cantos = np.array(
        [[-meia_l, -meia_a], [meia_l, -meia_a], [meia_l, meia_a], [-meia_l, meia_a]], dtype=np.float32
    )
    angulo = math.radians(giro_graus)
    giro = np.array(
        [[math.cos(angulo), -math.sin(angulo)], [math.sin(angulo), math.cos(angulo)]], dtype=np.float32
    )
    return (cantos @ giro.T + np.array(centro, dtype=np.float32)).astype(np.float32)


class AspectoMedidoNoQuadTests(unittest.TestCase):
    """A régua do aspecto mede a forma do candidato, e não a pegada dele na página.

    Sem PDF, sem imagem e sem modelo: é aritmética sobre quatro pontos, e é o defeito inteiro.
    """

    # 620×314 px inclinado de 45° é a faixa de hachura que venceu na página 62; a página do
    # livro renderiza em 719×718 a 220 DPI.
    FAIXA = (620.0, 314.0)
    AREA_DA_PAGINA = 719.0 * 718.0

    def test_a_faixa_inclinada_e_recusada_como_a_deitada(self) -> None:
        """Girar não pode transformar em diagrama o que deitado não era.

        Alongamento 1,98 está além de `ASPECT_MAX` nas duas posições, e `_contour_geometry_score`
        devolve 0 -- que é o valor que faz `_extract_candidate_quads` recusar por `"aspecto"`.
        """
        largura, altura = self.FAIXA
        self.assertGreater(largura / altura, ASPECT_MAX, "o fixture deixou de ser alongado")

        for giro in (0.0, 30.0, 45.0, 60.0, 90.0, 135.0):
            with self.subTest(giro=giro):
                quad = _quad_retangulo(largura, altura, giro)
                self.assertEqual(_contour_geometry_score(quad, self.AREA_DA_PAGINA), 0.0)

    def test_a_caixa_alinhada_era_a_regua_errada(self) -> None:
        """**Por que a guarda deixava passar.** Não é hipótese: é o número que a caixa dá.

        A caixa da faixa a 45° é quadrada com razão 1,005 -- dentro da faixa aceita --, enquanto
        a forma que a caixa cobre tem alongamento 1,98. Este teste não exercita o código de
        produção; ele fixa a razão de a correção existir, para que trocar `minAreaRect` de volta
        por `boundingRect` não pareça inócuo.
        """
        quad = _quad_retangulo(*self.FAIXA, 45.0)
        _x, _y, largura_caixa, altura_caixa = cv2.boundingRect(quad.astype(np.int32))

        razao_da_caixa = largura_caixa / altura_caixa
        self.assertLess(abs(razao_da_caixa - 1.0), 0.02, "a caixa da faixa girada é quadrada")
        self.assertLess(razao_da_caixa, ASPECT_MAX, "e por isso ela passava no aspecto")

    def test_o_quadrado_de_pe_continua_valendo_o_que_valia(self) -> None:
        """O outro lado: a correção não pode ter apertado o que já entrava.

        Um diagrama fecha quadrado com folga -- o da página 62 mede 466×453, alongamento 1,03 --
        e precisa continuar tirando nota alta.
        """
        quad = _quad_retangulo(466.0, 453.0, 0.0)
        self.assertGreater(_contour_geometry_score(quad, self.AREA_DA_PAGINA), 0.8)


class MolduraNaoLevaODiagramaJuntoTests(unittest.TestCase):
    """A ordem das guardas, sobre o fixture versionado `diagrama_em_moldura` (S-160).

    A moldura é o falso positivo da S-143 -- retrato, foto, quadro, contraste de casa
    exatamente zero -- montado pela primeira vez **em cima de um diagrama**. Ela vence por
    área, e é essa vitória que o piso de contraste tem de anular *antes* de a supressão por
    IoU acontecer.

    A hachura da página 62 produz a mesma sequência, e não está aqui de propósito: reproduzi-la
    exige a granulação de um scan de 1 bit, e um fixture ajustado a esse ponto testaria o
    ajuste em vez do detector.
    """

    PAGINA = "diagrama_em_moldura"
    CENTRO_DO_DIAGRAMA = (410.0, 590.0)
    """Onde `gerar.py` desenha o tabuleiro: (240, 420) com lado 340."""

    CENTRO_DA_MOLDURA = (470.0, 650.0)
    """Onde ele desenha a moldura: (170, 350) com lado 600. É o que saía antes."""

    TOLERANCIA_PX = 12
    """O mesmo de `test_fixtures.py`, e pelo mesmo motivo."""

    def _pagina(self) -> np.ndarray:
        imagem = read_image(FIXTURES / f"{self.PAGINA}.png")
        if imagem is None:  # pragma: no cover - só se o fixture sumir do repositório
            raise AssertionError(f"Fixture ausente: {self.PAGINA}.png. Refaça com tests/fixtures/gerar.py")
        return cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB)

    @staticmethod
    def _centro(quad: np.ndarray) -> tuple[float, float]:
        medio = quad.reshape(-1, 2).mean(axis=0)
        return float(medio[0]), float(medio[1])

    def test_a_pagina_devolve_o_diagrama_e_nao_a_moldura(self) -> None:
        achados = detect_boards(self._pagina(), max_boards=8)

        self.assertEqual(len(achados), 1, "a moldura não é diagrama e o diagrama não sumiu")
        _recorte, quad = achados[0]
        self.assertIsNotNone(quad)
        assert quad is not None
        centro = self._centro(quad)
        self.assertAlmostEqual(centro[0], self.CENTRO_DO_DIAGRAMA[0], delta=self.TOLERANCIA_PX)
        self.assertAlmostEqual(centro[1], self.CENTRO_DO_DIAGRAMA[1], delta=self.TOLERANCIA_PX)

    def test_sem_o_piso_a_moldura_volta_e_o_diagrama_some(self) -> None:
        """**A trava propriamente dita.** `checker_floor=None` é a ordem antiga, e ela erra.

        Ter os dois lados no mesmo arquivo é o que separa "o teste passa" de "o teste prova":
        se alguém desfizer a correção, o de cima falha; se alguém tornar o piso inócuo, este
        aqui falha, porque desligá-lo deixaria de mudar a resposta.
        """
        achados = detect_boards(self._pagina(), max_boards=8, checker_floor=None)

        self.assertEqual(len(achados), 1)
        _recorte, quad = achados[0]
        assert quad is not None
        centro = self._centro(quad)
        self.assertAlmostEqual(centro[0], self.CENTRO_DA_MOLDURA[0], delta=self.TOLERANCIA_PX)
        self.assertAlmostEqual(centro[1], self.CENTRO_DA_MOLDURA[1], delta=self.TOLERANCIA_PX)

    def test_o_motivo_registrado_e_o_da_guarda_que_agiu(self) -> None:
        """Sem isto o censo da S-131 contaria a moldura como recall perdido em vez de acerto."""
        from chess_diagram_ocr.board_detection import RejectedQuad

        recusados: list[RejectedQuad] = []
        detect_boards(self._pagina(), max_boards=8, rejected=recusados)

        sem_xadrez = [r for r in recusados if r.reason == "sem-contraste-de-casa"]
        self.assertTrue(sem_xadrez, "a moldura precisa aparecer no relatório de recusas")
        for recusa in sem_xadrez:
            self.assertLessEqual(recusa.checker, MIN_CHECKER_CONTRAST)


class NenhumRecorteSaiSemXadrezTests(unittest.TestCase):
    """A invariante que a correção compra, sobre todas as páginas versionadas.

    `detect_boards` é a única fonte de candidato nos 12 livros do acervo que são scan de página
    inteira. Devolver dali um recorte sem contraste de casa nenhum é devolver uma posição
    inventada, que vira PGN.
    """

    def test_todo_recorte_devolvido_tem_contraste_de_casa(self) -> None:
        for caminho in sorted(FIXTURES.glob("*.png")):
            with self.subTest(pagina=caminho.stem):
                imagem = read_image(caminho)
                self.assertIsNotNone(imagem)
                pagina = cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB)
                for recorte, _quad in detect_boards(pagina, max_boards=12):
                    self.assertGreater(_checker_score(_small_gray(recorte)), MIN_CHECKER_CONTRAST)


@unittest.skipUnless(LIVRO.exists(), f"{LIVRO.name} não está neste checkout (PDF/ fica fora do git)")
class Pagina62DoAnandTests(unittest.TestCase):
    """A página do relato, lida do livro de verdade.

    **Pula sem o acervo, e isso é uma escolha, não um descuido.** `PDF/` está fora do git por
    peso e por licença. A cobertura que roda em qualquer lugar são as classes acima; esta aqui
    é a conferência sobre o material real, para quem tem o livro na máquina.
    """

    DPI = 220
    """O padrão do `cvoff-infer` e o que a interface usa. Importa: a imagem embutida é 300 DPI
    nativo, então este render **reduz**, e é na redução que a hachura vira moiré."""

    def _pagina(self) -> np.ndarray:
        from chess_diagram_ocr.pdf_io import render_pdf_page

        return render_pdf_page(LIVRO, PAGINA_62, dpi=self.DPI)

    def test_o_recorte_e_um_tabuleiro_e_nao_um_losango(self) -> None:
        """Só detecção: não precisa de checkpoint, e é onde o defeito morava.

        O recorte antigo era um retângulo de 620×314 inclinado a 45°. As três asserções abaixo
        o excluem sem depender de o modelo existir: um diagrama fecha quase quadrado, fica
        dentro da página e tem contraste de casa.
        """
        achados = detect_boards(self._pagina(), max_boards=4)

        self.assertTrue(achados, "a página 62 tem um diagrama e ele precisa ser achado")
        recorte, quad = achados[0]
        assert quad is not None

        largura, altura = np.ptp(quad.reshape(-1, 2), axis=0)
        self.assertLess(max(largura, altura) / min(largura, altura), 1.2, "o recorte é quadrado")
        self.assertGreater(_checker_score(_small_gray(recorte)), MIN_CHECKER_CONTRAST)
        self.assertTrue(
            (quad >= -1.0).all() and (quad[:, 0] <= 719.0).all() and (quad[:, 1] <= 720.0).all(),
            f"o quad sangra para fora da página: {quad.tolist()}",
        )

    def test_a_fen_da_pagina_62(self) -> None:
        """A leitura completa, ponta a ponta. **Precisa do checkpoint** e pula sem ele.

        Ela cobra a FEN exata porque só roda onde há livro *e* modelo -- a máquina de quem
        treina. Se um treino futuro mudar uma casa aqui, a falha é informação: quer dizer que
        esta página piorou, e a `docs/BASELINE.md` é onde a decisão de aceitar ou não se toma.
        """
        from chess_diagram_ocr.config import DEFAULT_MODEL_PATH
        from chess_diagram_ocr.inference import load_model, predict_with_orientation

        if not Path(DEFAULT_MODEL_PATH).exists():
            self.skipTest(f"{DEFAULT_MODEL_PATH} não existe neste checkout")

        achados = detect_boards(self._pagina(), max_boards=1)
        self.assertTrue(achados)

        modelo, dispositivo = load_model(DEFAULT_MODEL_PATH)
        predicao = predict_with_orientation(achados[0][0], modelo, dispositivo, mode="auto").prediction

        self.assertEqual(predicao.fen_board, FEN_DA_PAGINA_62)
        self.assertTrue(predicao.position.is_legal, "; ".join(predicao.position.problems))
        self.assertGreater(predicao.min_confidence, 0.9)


if __name__ == "__main__":
    unittest.main()
