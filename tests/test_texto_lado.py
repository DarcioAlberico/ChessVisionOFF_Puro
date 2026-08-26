"""O lado a jogar lido pelo classificador deste projeto, e não por motor de fora (S-207).

Os dois testes que a spec nomeia são o esqueleto: `glifo` entra como fonte declarada -- no
`Literal`, no rótulo e no header do PGN --, e a contradição entre a leitura e a legalidade da S-17
chega à fila da S-22 com motivo escrito, em vez de ser resolvida por prioridade fixa.
"""

from __future__ import annotations

import unittest
from typing import get_args

import chess

from chess_diagram_ocr import procedencias
from chess_diagram_ocr.semantics import SideSource, SideToMove, infer_side_to_move
from chess_diagram_ocr.text.lado import (
    FONTE,
    FONTE_DE_PAGINA,
    LadoLido,
    contabilizar,
    lado_de_linhas,
    lado_por_glifo,
    tabela,
    total,
)


class Linha:
    """O mínimo de uma `TextLine`/`_Cru` para `lado_de_linhas` -- as duas formas de nome."""

    def __init__(self, text: str, confidence: float = 1.0) -> None:
        self.text = text
        self.confidence = confidence


class FonteDeclaradaTests(unittest.TestCase):
    def test_o_glifo_entra_como_fonte_declarada(self) -> None:
        """No `Literal`, nos dois escopos, e com rótulo -- senão o header do PGN sai sem legenda."""
        from chess_diagram_ocr.semantics import _SOURCE_LABELS

        valores = set(get_args(SideSource))
        self.assertIn(FONTE, valores)
        self.assertIn(FONTE_DE_PAGINA, valores)
        for fonte in (FONTE, FONTE_DE_PAGINA):
            with self.subTest(fonte=fonte):
                self.assertTrue(_SOURCE_LABELS[fonte].strip())

    def test_o_glifo_nao_e_disfarcado_de_camada_de_texto(self) -> None:
        """A primeira regra da S-43: um palpite tem de parecer um palpite."""
        self.assertNotEqual("text", FONTE)
        self.assertNotEqual("text-page-scope", FONTE_DE_PAGINA)

    def test_o_glifo_nao_e_disfarcado_de_motor_de_terceiros(self) -> None:
        """O que a S-207 acrescenta: `ocr` é o RapidOCR, e não o classificador desta casa."""
        self.assertNotEqual(procedencias.DE_TERCEIROS, FONTE)

    def test_o_glifo_leva_confianca_para_o_pgn(self) -> None:
        """`[SideToMoveConfidence]` só sai das fontes de motor -- as duas do glifo entre elas."""
        from chess_diagram_ocr.pdf_to_pgn import _OCR_SOURCES

        self.assertIn(FONTE, _OCR_SOURCES)
        self.assertIn(FONTE_DE_PAGINA, _OCR_SOURCES)

    def test_o_glifo_conta_como_declaracao_de_texto_na_cascata(self) -> None:
        """Sem isso a leitura do classificador não chegaria a decidir nada."""
        from chess_diagram_ocr.semantics import _TEXT_SOURCES

        self.assertIn(FONTE, _TEXT_SOURCES)
        self.assertIn(FONTE_DE_PAGINA, _TEXT_SOURCES)


class LeituraTests(unittest.TestCase):
    def test_le_a_declaracao_com_a_regua_da_camada(self) -> None:
        """Um segundo reconhecedor de "White to move" divergiria do primeiro; o acervo tem 8 idiomas."""
        lido = lado_por_glifo("White to move", confianca=0.8)
        self.assertIsNotNone(lido)
        self.assertEqual(chess.WHITE, lido.cor)
        self.assertEqual(FONTE, lido.fonte)

    def test_o_escopo_de_pagina_tem_fonte_propria(self) -> None:
        lido = lado_por_glifo("Las blancas juegan", escopo_de_pagina=True)
        self.assertEqual(FONTE_DE_PAGINA, lido.fonte)

    def test_prosa_sem_declaracao_devolve_none(self) -> None:
        self.assertIsNone(lado_por_glifo("a posição é complicada"))

    def test_o_duvidoso_sai_do_piso_da_S42(self) -> None:
        from chess_diagram_ocr.ocr import MIN_CONFIDENCE

        self.assertTrue(LadoLido(chess.WHITE, "x", MIN_CONFIDENCE - 0.01).duvidoso)
        self.assertFalse(LadoLido(chess.WHITE, "x", MIN_CONFIDENCE).duvidoso)

    def test_a_faixa_que_diz_os_dois_lados_nao_responde(self) -> None:
        """Devolver a primeira seria decidir por ordem de leitura. Mesma regra de `page_scope_declaration`."""
        self.assertIsNone(lado_de_linhas([Linha("White to move"), Linha("Black to move")]))

    def test_a_faixa_que_diz_o_mesmo_duas_vezes_responde(self) -> None:
        lido = lado_de_linhas([Linha("nada aqui"), Linha("Black to move", 0.4)])
        self.assertEqual(chess.BLACK, lido.cor)
        self.assertAlmostEqual(0.4, lido.confianca)

    def test_faixa_vazia_devolve_none(self) -> None:
        self.assertIsNone(lado_de_linhas([]))


class ContradicaoTests(unittest.TestCase):
    """A contradição é informação, e não erro a esconder."""

    # Rei branco em a1, torre preta em a8: com as pretas a jogar, as brancas estariam em xeque
    # sem ser a vez delas -- posição ilegal. Só `w` fecha, e é a legalidade quem impõe.
    XEQUE_INVERTIDO = "r6k/8/8/8/8/8/8/K7"

    def contexto_do_glifo(self, cor: bool):
        from chess_diagram_ocr.pdf_text import DiagramContext

        return DiagramContext(
            caption="Black to move",
            side_to_move=cor,
            side_to_move_evidence="black to move",
            side_to_move_origin=FONTE,
            side_to_move_confidence=0.62,
        )

    def test_a_contradicao_vai_para_a_fila_e_nao_e_resolvida_calada(self) -> None:
        """O par sai marcado, e a fila da S-22 o pontua com motivo escrito."""
        from chess_diagram_ocr.review_queue import WEIGHT_SOURCES_DISAGREE

        decidido = infer_side_to_move(self.XEQUE_INVERTIDO, self.contexto_do_glifo(chess.BLACK))
        self.assertTrue(decidido.conflicting, "a contradição sumiu: nada iria para a fila")
        self.assertEqual(chess.WHITE, decidido.color, "a legalidade tinha de vencer")
        self.assertEqual("legality", decidido.source)
        self.assertGreater(WEIGHT_SOURCES_DISAGREE, 0.0)

    def test_sem_contradicao_a_leitura_do_glifo_decide_e_a_fonte_fica(self) -> None:
        """O caminho normal: o glifo respondeu, e o header diz que foi ele."""
        decidido = infer_side_to_move("8/8/8/8/8/8/8/8", self.contexto_do_glifo(chess.BLACK))
        self.assertEqual(chess.BLACK, decidido.color)
        self.assertEqual(FONTE, decidido.source)
        self.assertFalse(decidido.conflicting)

    def test_a_contradicao_e_contada_na_tabela_por_livro(self) -> None:
        """Contá-la é o que impede que ela vire ruído de log."""
        lados = [
            SideToMove(chess.WHITE, FONTE),
            SideToMove(chess.WHITE, "legality", conflicting=True),
        ]
        self.assertEqual(1, contabilizar("livro", lados).contradicoes)


class TabelaTests(unittest.TestCase):
    def lados(self):
        return [
            SideToMove(chess.WHITE, FONTE),
            SideToMove(chess.BLACK, FONTE_DE_PAGINA),
            SideToMove(chess.WHITE, "text"),
            SideToMove(chess.WHITE, "default"),
            SideToMove(chess.WHITE, "default"),
        ]

    def test_as_tres_colunas_do_item(self) -> None:
        """lidos, `default` e contradição -- as três perguntas que o item manda responder."""
        linha = contabilizar("Kemeri", self.lados())
        self.assertEqual(5, linha.diagramas)
        self.assertEqual(2, linha.lidos)
        self.assertEqual(1, linha.de_outra_fonte)
        self.assertEqual(2, linha.assumidos)
        self.assertAlmostEqual(0.4, linha.cobertura)

    def test_os_dois_escopos_do_glifo_contam_como_lidos(self) -> None:
        """Metade contada seria a mesma mentira que o item existe para desfazer."""
        so_pagina = contabilizar("x", [SideToMove(chess.WHITE, FONTE_DE_PAGINA)])
        self.assertEqual(1, so_pagina.lidos)

    def test_o_duvidoso_sai_da_confianca_paralela(self) -> None:
        """A confiança não mora no `SideToMove`: ela é do contexto, e o PGN a grava de lá."""
        lados = [SideToMove(chess.WHITE, FONTE), SideToMove(chess.WHITE, FONTE)]
        self.assertEqual(1, contabilizar("x", lados, [0.1, 0.9]).duvidosos)

    def test_sem_confiancas_nenhum_lido_e_duvidoso(self) -> None:
        """"Não se mediu" não é "todos confiantes", mas é o único que não inventa número."""
        self.assertEqual(0, contabilizar("x", [SideToMove(chess.WHITE, FONTE)]).duvidosos)

    def test_o_total_soma_as_colunas(self) -> None:
        uma = contabilizar("a", self.lados())
        somado = total([uma, uma])
        self.assertEqual("todos", somado.livro)
        self.assertEqual(2 * uma.diagramas, somado.diagramas)
        self.assertEqual(2 * uma.lidos, somado.lidos)

    def test_livro_sem_diagrama_nao_divide_por_zero(self) -> None:
        self.assertEqual(0.0, contabilizar("vazio", []).cobertura)

    def test_a_tabela_fecha_com_o_total(self) -> None:
        linhas = tabela([contabilizar("a", self.lados())])
        self.assertIn("todos", linhas[-1])


class VocabularioTests(unittest.TestCase):
    """A regra da S-181 continua valendo: os dois módulos genéricos não nomeiam motor."""

    def test_o_escopo_de_pagina_e_sufixo_para_as_tres_fontes(self) -> None:
        for origem in ("text", "ocr", "glifo"):
            with self.subTest(origem=origem):
                self.assertEqual(f"{origem}-page-scope", procedencias.escopo_de_pagina(origem))

    def test_o_escopo_de_pagina_e_idempotente(self) -> None:
        """Aplicado duas vezes daria `text-page-scope-page-scope`, que não é `SideOrigin` nenhum."""
        uma = procedencias.escopo_de_pagina("text")
        self.assertEqual(uma, procedencias.escopo_de_pagina(uma))

    def test_todo_escopo_de_pagina_e_um_SideOrigin(self) -> None:
        validos = set(get_args(procedencias.SideOrigin))
        for origem in get_args(procedencias.LineOrigin):
            with self.subTest(origem=origem):
                self.assertIn(procedencias.escopo_de_pagina(origem), validos)

    def test_a_procedencia_sai_do_nome_do_motor(self) -> None:
        self.assertEqual(FONTE, procedencias.procedencia_do_motor(procedencias.MOTOR_DE_CASA))
        for terceiro in ("rapidocr", "easyocr", "tesseract", "um_motor_que_ainda_nao_existe"):
            with self.subTest(motor=terceiro):
                self.assertEqual(procedencias.DE_TERCEIROS, procedencias.procedencia_do_motor(terceiro))

    def test_o_motor_de_casa_e_o_nome_que_o_reconhecedor_declara(self) -> None:
        """Quatro lugares leem esta constante; escrita quatro vezes, uma sairia errada."""
        from chess_diagram_ocr.ocr import KNOWN_ENGINES
        from chess_diagram_ocr.text.recognizer import NOME

        self.assertEqual(procedencias.MOTOR_DE_CASA, NOME)
        self.assertIn(procedencias.MOTOR_DE_CASA, KNOWN_ENGINES)

    def test_todo_LineOrigin_e_um_SideOrigin(self) -> None:
        """A declaração de diagrama é o caso de escopo estreito da mesma procedência."""
        self.assertTrue(set(get_args(procedencias.LineOrigin)) <= set(get_args(procedencias.SideOrigin)))

    def test_todo_SideOrigin_e_um_SideSource(self) -> None:
        """`pdf_text` decide a origem e `semantics` a publica: uma que não atravessasse sumiria."""
        self.assertTrue(set(get_args(procedencias.SideOrigin)) <= set(get_args(SideSource)))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class FaixaDeLegendaTests(unittest.TestCase):
    """O defeito que a medição da S-207 encontrou: a faixa guarda os diagramas vizinhos."""

    def test_os_vizinhos_sao_apagados_do_recorte(self) -> None:
        """Sem isso as peças dos outros diagramas quebram a escala e a faixa lê figurina.

        Medido na página 17 do `1000 Chess Problems` (4 diagramas): apagando só o alvo saem 8
        caixas, todas figurina; apagando os quatro saem 3, e uma é a legenda.
        """
        import fitz

        from chess_diagram_ocr import ocr_caption

        apagados: list[tuple[float, float, float, float]] = []

        class LeitorFalso:
            name = "rapidocr"

            def read(self, image_rgb, *, allowlist: str = ""):  # noqa: ANN001
                return []

        leitor = ocr_caption.CaptionReader(LeitorFalso(), radius_pt=20.0)
        original = ocr_caption._blank_region

        def espiao(image_rgb, region, *, origin, zoom):  # noqa: ANN001
            apagados.append((region.x0, region.y0, region.x1, region.y1))
            return original(image_rgb, region, origin=origin, zoom=zoom)

        documento = fitz.open()
        pagina = documento.new_page(width=400, height=400)
        alvo = (100.0, 100.0, 200.0, 200.0)
        vizinho = (210.0, 100.0, 300.0, 200.0)
        longe = (10.0, 380.0, 30.0, 395.0)
        try:
            ocr_caption._blank_region = espiao
            leitor.lines_around(pagina, alvo, [vizinho, longe])
        finally:
            ocr_caption._blank_region = original
            documento.close()

        self.assertIn(alvo, apagados, "o alvo tem de ser apagado -- é o contrato da S-43")
        self.assertIn(vizinho, apagados, "o vizinho dentro da faixa ficou, e as peças dele quebram a escala")
        self.assertNotIn(longe, apagados, "um diagrama fora da faixa não precisa ser apagado")

    def test_sem_vizinhos_o_leitor_le_como_sempre_leu(self) -> None:
        """O parâmetro é opcional: um chamador antigo não muda de comportamento."""
        import inspect

        from chess_diagram_ocr.ocr_caption import CaptionReader

        assinatura = inspect.signature(CaptionReader.lines_around)
        self.assertIs(assinatura.parameters["vizinhos"].default, ())
