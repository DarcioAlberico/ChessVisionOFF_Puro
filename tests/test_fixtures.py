"""As páginas versionadas de `tests/fixtures/`, e o que elas travam (S-09).

**O que este arquivo conserta.** `test_detect_boards_still_finds_real_sample` era a única
verificação de que o detector acha um tabuleiro de verdade, e ela lia `data/samples/` --
que está fora do git. Na CI ela **pulava**, então o detector não tinha cobertura executável
nenhuma lá: uma regressão que o fizesse achar zero diagramas entrava verde. A S-09 já nomeava
o defeito e o remédio, e o remédio era este: *"substituir o `glob` frágil por caminho de
fixture explícito"*.

**O que elas NÃO travam, e é o item que continua aberto.** Não são um teste de regressão de
**acurácia do modelo**. Para isso faltam duas coisas que não são só arquivo:

1. `data/samples/` e `models/*.pt` estão os dois fora do git -- o segundo por peso (8,4 MB por
   checkpoint), o primeiro por peso e por licença. Um teste de acurácia precisa dos dois, então
   ele pularia na CI de qualquer forma: exatamente a *"falsa sensação de cobertura"* que o
   `ROADMAP.md` usa para explicar por que a pendência 1.8 ainda está aberta.
2. Estas páginas são desenho geométrico. Medir acurácia sobre elas daria um número real sobre
   um domínio que não é o produto -- e um número desses publicado é pior que nenhum.

O que fica travado aqui é **geometria de detecção**, que é o que estas páginas de fato contêm:
quantos diagramas há, onde eles estão e em que ordem saem. O `docs/BASELINE.md` continua sendo
a trava manual de acurácia, como o ROADMAP diz.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import cv2
import numpy as np

from chess_diagram_ocr.atomic_io import read_image
from chess_diagram_ocr.board_detection import detect_boards
from chess_diagram_ocr.config import BOARD_SIZE

FIXTURES = Path(__file__).resolve().parent / "fixtures"

TOLERANCIA_PX = 12
"""Quanto o centro do quad pode andar em relação ao que o gerador desenhou.

**Doze, e não zero**, porque o detector acha o contorno da borda desenhada e não a coordenada
de origem: um pixel de anti-aliasing na borda move o centro. E não é folga: medido em
2026-08-18, os cinco diagramas das três páginas saem com **0 px** de desvio nos dois eixos, e
doze é o que separa "o desenho mudou de lugar" de "o detector mudou de resposta"."""


def _pagina(nome: str) -> np.ndarray:
    imagem = read_image(FIXTURES / f"{nome}.png")
    if imagem is None:  # pragma: no cover - só se o fixture sumir do repositório
        raise AssertionError(f"Fixture ausente: {nome}.png. Refaça com tests/fixtures/gerar.py")
    return cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB)


def _esperado() -> dict[str, list[dict[str, object]]]:
    dados = json.loads((FIXTURES / "esperado.json").read_text(encoding="utf-8"))
    return dados["paginas"]


def _centro(quad: np.ndarray) -> tuple[float, float]:
    medio = quad.reshape(-1, 2).mean(axis=0)
    return float(medio[0]), float(medio[1])


class FixturesVersionadosTests(unittest.TestCase):
    """As páginas existem, são pequenas e têm receita. Sem isto o resto não vale nada."""

    def test_as_paginas_e_o_manifesto_estao_no_repositorio(self) -> None:
        """Elas são versionadas de propósito: é o que faz o detector rodar na CI."""
        for nome in _esperado():
            self.assertTrue((FIXTURES / f"{nome}.png").exists(), f"falta {nome}.png")

    def test_cabem_no_teto_que_a_s09_fixou(self) -> None:
        """**2 MB no total**, e o motivo do teto é o mesmo de sempre: um repositório que
        engorda com dado binário deixa de ser clonável. Um tabuleiro real de `data/samples/`
        pesa ~900 KB sozinho -- é por isso que estas páginas são sintéticas."""
        total = sum(caminho.stat().st_size for caminho in FIXTURES.glob("*.png"))
        self.assertLess(total, 2 * 1024 * 1024, f"os fixtures somam {total / 1024:.0f} KB")

    def test_a_receita_esta_ao_lado_do_que_ela_gera(self) -> None:
        """Um PNG versionado sem o gerador é um dado que ninguém pode conferir nem refazer."""
        self.assertTrue((FIXTURES / "gerar.py").exists())


class DeteccaoNosFixturesTests(unittest.TestCase):
    """O que a CI passou a rodar: o detector, sobre imagem de verdade.

    Antes disto, a única cobertura executável de `detect_boards` sobre uma página com diagrama
    lia `data/samples/` e pulava fora desta máquina.
    """

    def test_cada_pagina_devolve_os_diagramas_que_ela_tem(self) -> None:
        for nome, alvos in _esperado().items():
            with self.subTest(pagina=nome):
                achados = detect_boards(_pagina(nome), max_boards=12)
                self.assertEqual(len(achados), len(alvos))

    def test_todo_recorte_sai_no_tamanho_do_pipeline(self) -> None:
        """800×800 é o que o classificador espera; recorte de outro tamanho quebra o corte
        em 64 casas sem que nada avise."""
        for nome in _esperado():
            with self.subTest(pagina=nome):
                for recorte, _quad in detect_boards(_pagina(nome), max_boards=12):
                    self.assertEqual(recorte.shape[:2], (BOARD_SIZE, BOARD_SIZE))

    def test_todo_diagrama_sai_com_quad(self) -> None:
        """Sem quad não há como voltar à página -- é o que a marcação da S-68 desenha, e o que
        `refine_board_from_quad` reprocura."""
        for nome in _esperado():
            with self.subTest(pagina=nome):
                for _recorte, quad in detect_boards(_pagina(nome), max_boards=12):
                    self.assertIsNotNone(quad)

    def test_os_diagramas_saem_de_onde_o_gerador_os_desenhou(self) -> None:
        """**A trava de regressão desta suíte de fixtures.** Se o detector passar a achar a
        borda errada, ou a deslocar o recorte, os centros andam e isto falha com o número.
        """
        for nome, alvos in _esperado().items():
            achados = detect_boards(_pagina(nome), max_boards=12)
            por_centro = sorted(_centro(quad) for _recorte, quad in achados if quad is not None)
            desenhados = sorted(
                (float(a["x"]) + float(a["lado"]) / 2, float(a["y"]) + float(a["lado"]) / 2)
                for a in alvos
            )
            self.assertEqual(len(por_centro), len(desenhados))
            for achado, desenhado in zip(por_centro, desenhados, strict=True):
                with self.subTest(pagina=nome, centro=desenhado):
                    self.assertAlmostEqual(achado[0], desenhado[0], delta=TOLERANCIA_PX)
                    self.assertAlmostEqual(achado[1], desenhado[1], delta=TOLERANCIA_PX)

    def test_pagina_em_branco_continua_sem_diagrama(self) -> None:
        """O outro lado do fixture: achar diagrama onde não há é o defeito caro, porque ele
        vira PGN com posição inventada."""
        branca = np.full((1400, 1000, 3), 255, dtype=np.uint8)
        self.assertEqual(detect_boards(branca, max_boards=12), [])


class OrdemDeLeituraNosFixturesTests(unittest.TestCase):
    """A ordem em que os quatro diagramas saem, sobre imagem e não sobre bbox fabricada (S-14).

    O resto da suíte testa `reading_order` com retângulos montados à mão -- o que é certo para
    a regra e não diz nada sobre a página. A `quatro_diagramas` tem dois por linha e dois por
    coluna justamente para as duas ordens **discordarem**: se elas concordassem, o teste
    passaria com o parâmetro sendo ignorado.
    """

    PAGINA = "quatro_diagramas"

    def _centros(self, ordem: str) -> list[tuple[float, float]]:
        achados = detect_boards(_pagina(self.PAGINA), max_boards=12, reading_order=ordem)  # type: ignore[arg-type]
        return [_centro(quad) for _recorte, quad in achados if quad is not None]

    def test_por_coluna_desce_a_esquerda_antes_de_subir_a_direita(self) -> None:
        centros = self._centros("column")
        self.assertEqual(len(centros), 4)
        esquerda = [x for x, _y in centros[:2]]
        direita = [x for x, _y in centros[2:]]
        self.assertLess(max(esquerda), min(direita), "os dois primeiros são a coluna da esquerda")
        self.assertLess(centros[0][1], centros[1][1], "e dentro dela, de cima para baixo")

    def test_por_linha_atravessa_a_pagina_antes_de_descer(self) -> None:
        centros = self._centros("row")
        self.assertEqual(len(centros), 4)
        de_cima = [y for _x, y in centros[:2]]
        de_baixo = [y for _x, y in centros[2:]]
        self.assertLess(max(de_cima), min(de_baixo), "os dois primeiros são a linha de cima")
        self.assertLess(centros[0][0], centros[1][0], "e dentro dela, da esquerda para a direita")

    def test_as_duas_ordens_discordam_nesta_pagina(self) -> None:
        """Se um dia concordarem, esta página deixou de testar o parâmetro -- e é melhor
        descobrir isso aqui do que num teste que passa por acidente."""
        self.assertNotEqual(self._centros("column"), self._centros("row"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
