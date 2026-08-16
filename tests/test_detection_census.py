"""O censo de detecção da S-82.

A divisão dos testes tem uma razão. As três contagens que denunciam defeito
(`suspects`, `pages_numbering_shifted`, `pages_size_prior_mixed`) são funções puras sobre
`CandidateRow`, e são testadas assim -- **sem** passar pelo detector. Se elas dependessem de o
detector aceitar um glifo, a S-78 as quebraria ao corrigir exatamente isso, e um instrumento
que quebra quando o defeito é corrigido não serve para medir a correção.

O que passa pelo detector de verdade é só o teste de ponta a ponta, e ele afirma o que
continua verdade depois da S-78: o censo roda, grava, e o CSV volta igual.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz
from test_detection import PAGE_HEIGHT, PAGE_WIDTH, board_image, pdf_with_images

from chess_diagram_ocr.detection_census import (
    SUSPECT_BELOW_PT,
    BookCensus,
    CandidateRow,
    DetectionCensus,
    census_book,
    diff_census,
    read_census_csv,
    write_census_csv,
    write_census_json,
)
from chess_diagram_ocr.pdf_io import sample_pages


def row(
    *,
    pdf: str = "livro.pdf",
    page: int = 1,
    index: int = 0,
    side_pt: float = 150.0,
    source: str = "embedded",
    texture: float = 0.78,
    x0: float = 100.0,
    y0: float = 100.0,
) -> CandidateRow:
    return CandidateRow(
        pdf=pdf,
        page=page,
        index=index,
        source=source,
        side_pt=side_pt,
        native_width=1280,
        native_height=1280,
        trimmed=True,
        detector_score=0.9,
        texture=texture,
        x0=x0,
        y0=y0,
        x1=x0 + side_pt,
        y1=y0 + side_pt,
    )


def glyph(*, page: int = 1, index: int = 0, x0: float = 375.0, y0: float = 16.0) -> CandidateRow:
    """O cavalo do cabeçalho do `Secrets`: 128 px nativos em 15,4 pt de página."""
    return CandidateRow(
        pdf="livro.pdf",
        page=page,
        index=index,
        source="embedded",
        side_pt=15.4,
        native_width=128,
        native_height=128,
        trimmed=False,
        detector_score=0.7,
        texture=0.21,
        x0=x0,
        y0=y0,
        x1=x0 + 15.4,
        y1=y0 + 15.4,
    )


class SamplePagesMovedTests(unittest.TestCase):
    """A S-82 moveu `sample_pages` para `pdf_io`; quem a nomeia pelo módulo antigo continua vendo."""

    def test_o_nome_antigo_segue_valendo(self) -> None:
        from chess_diagram_ocr.side_survey import sample_pages as pelo_nome_antigo

        self.assertIs(pelo_nome_antigo, sample_pages)

    def test_a_amostragem_nao_mudou(self) -> None:
        self.assertEqual(sample_pages(100, 4), sample_pages(100, 4))
        self.assertEqual(sample_pages(3, 12), [0, 1, 2])
        self.assertEqual(sample_pages(0, 12), [])

    def test_o_censo_nao_carrega_modelo(self) -> None:
        """O motivo de a função ter mudado de casa: 0,2 s de import contra ~8 s com torch.

        Um censo caro é um censo que não se roda a cada mudança, e rodar a cada mudança é a
        única coisa que ele existe para ser.
        """
        import subprocess
        import sys

        resultado = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import chess_diagram_ocr.detection_census; print('torch' in sys.modules)",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(resultado.stdout.strip(), "False")


class ContagensQueDenunciamTests(unittest.TestCase):
    """As três contagens, sobre linhas montadas à mão. Ver o docstring do módulo."""

    def test_o_suspeito_e_o_candidato_menor_que_um_diagrama_impresso(self) -> None:
        livro = BookCensus(pdf="livro.pdf", rows=[row(index=0), glyph(index=1)])

        self.assertEqual(livro.candidates, 2)
        self.assertEqual(len(livro.suspects), 1)
        self.assertEqual(livro.suspects[0].side_pt, 15.4)

    def test_o_limiar_de_suspeita_e_lente_e_nao_filtro(self) -> None:
        """O suspeito continua contado em tudo o mais: o censo não julga, conta."""
        livro = BookCensus(pdf="livro.pdf", rows=[row(index=0), glyph(index=1)])

        self.assertEqual(livro.candidates, 2)
        self.assertEqual(sum(livro.by_source.values()), 2)
        self.assertIn(15.4, [r.side_pt for r in livro.rows])

    def test_glifo_no_fim_da_pagina_nao_desloca_numeracao(self) -> None:
        livro = BookCensus(pdf="livro.pdf", rows=[row(page=1, index=0), glyph(page=1, index=1)])

        self.assertEqual(livro.pages_numbering_shifted, 0)

    def test_glifo_antes_do_diagrama_consome_o_numero_do_pgn(self) -> None:
        """O dano de §4.1: na página 342 do `Secrets` o glifo é o candidato #0."""
        livro = BookCensus(pdf="livro.pdf", rows=[glyph(page=1, index=0), row(page=1, index=1)])

        self.assertEqual(livro.pages_numbering_shifted, 1)

    def test_gabarito_misturado_precisa_dos_dois_na_mesma_pagina(self) -> None:
        """Suspeito e diagrama juntos é o que desloca a mediana de `detect_diagrams`."""
        misturada = BookCensus(pdf="livro.pdf", rows=[glyph(page=1, index=0), row(page=1, index=1)])
        self.assertEqual(misturada.pages_size_prior_mixed, 1)

        so_diagramas = BookCensus(pdf="livro.pdf", rows=[row(page=1, index=0), row(page=1, index=1, x0=300)])
        self.assertEqual(so_diagramas.pages_size_prior_mixed, 0)

        so_glifo = BookCensus(pdf="livro.pdf", rows=[glyph(page=1, index=0)])
        self.assertEqual(so_glifo.pages_size_prior_mixed, 0, "um candidato só não tem gabarito a misturar")

    def test_o_histograma_separa_as_duas_populacoes(self) -> None:
        """É o gráfico onde o vale de 110 pt do `Secrets` aparece sozinho."""
        livro = BookCensus(
            pdf="livro.pdf",
            rows=[glyph(page=1, index=0), row(page=1, index=1, side_pt=153.6)],
        )
        histograma = livro.side_histogram()

        self.assertEqual(histograma, {20: 1, 150: 1})
        self.assertEqual([f for f in histograma if f < SUSPECT_BELOW_PT], [20])


class CsvTests(unittest.TestCase):
    def test_o_csv_volta_igual(self) -> None:
        """Sem ida e volta fiel, o diff da corrida seguinte compara ruído de formatação."""
        censo = DetectionCensus(books=[BookCensus(pdf="livro.pdf", rows=[row(index=0), glyph(index=1)])])

        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "censo.csv"
            write_census_csv(destino, censo)
            de_volta = read_census_csv(destino)

        self.assertEqual(de_volta, censo.rows)

    def test_o_json_carrega_os_parametros_que_produziram_os_numeros(self) -> None:
        """Comparar 220 DPI com 300 mede o DPI, não a mudança no detector."""
        import json

        censo = DetectionCensus(books=[BookCensus(pdf="livro.pdf", rows=[row()])], dpi=300, max_boards=4)
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "censo.json"
            write_census_json(destino, censo)
            dados = json.loads(destino.read_text(encoding="utf-8"))

        self.assertEqual(dados["dpi"], 300)
        self.assertEqual(dados["max_boards"], 4)
        self.assertEqual(dados["suspect_below_pt"], SUSPECT_BELOW_PT)


class DiffTests(unittest.TestCase):
    def test_nada_mudou_nao_gera_linha(self) -> None:
        linhas = [row(index=0), glyph(index=1)]

        self.assertEqual(diff_census(linhas, list(linhas)), [])

    def test_remover_o_glifo_e_uma_perda_e_nao_uma_substituicao(self) -> None:
        """O motivo de casar por canto do bbox e não por índice.

        Quando o glifo sai, o diagrama que era #1 vira #0. Casar por índice leria isso como
        "perdi o #1 e ganhei o #0" -- duas mudanças onde houve uma, e a errada em destaque.
        """
        antes = [glyph(page=1, index=0), row(page=1, index=1)]
        depois = [row(page=1, index=0)]

        mudancas = diff_census(antes, depois)

        self.assertEqual(len(mudancas), 1)
        self.assertEqual(len(mudancas[0].lost), 1)
        self.assertEqual(mudancas[0].lost[0].side_pt, 15.4)
        self.assertEqual(mudancas[0].gained, [], "o diagrama só mudou de número, não é ganho")

    def test_a_perda_esperada_e_a_perigosa_ficam_em_colunas_diferentes(self) -> None:
        """`lost_real` é a coluna que precisa de justificativa a olho, uma por uma."""
        antes = [glyph(page=1, index=0), row(page=2, index=0), row(page=3, index=0)]
        depois = [row(page=2, index=0)]

        mudanca = diff_census(antes, depois)[0]

        self.assertEqual(len(mudanca.lost), 2)
        self.assertEqual([r.side_pt for r in mudanca.lost_suspects], [15.4])
        self.assertEqual([r.page for r in mudanca.lost_real], [3])

    def test_caixa_reajustada_e_movimento_e_nao_perda_mais_ganho(self) -> None:
        """A S-81 uniu ladrilhos e o candidato ficou com outro canto.

        Sem este passe o diff lia 26 "perdas acima do limiar" no `GALLAGHER` onde havia um
        diagrama por página, reajustado. Um instrumento que grita perda a cada reajuste é um
        instrumento que ninguém olha na terceira vez.
        """
        antes = [row(page=1, index=0, x0=100.0, y0=100.0, side_pt=150.0)]
        depois = [row(page=1, index=0, x0=110.0, y0=105.0, side_pt=150.0)]

        mudanca = diff_census(antes, depois)[0]

        self.assertEqual(mudanca.lost, [])
        self.assertEqual(mudanca.gained, [])
        self.assertEqual(len(mudanca.moved), 1)
        self.assertEqual(mudanca.moved[0][0].x0, 100.0)
        self.assertEqual(mudanca.moved[0][1].x0, 110.0)

    def test_caixa_distante_na_mesma_pagina_segue_sendo_perda(self) -> None:
        """O passe casa por sobreposição: dois diagramas distintos não se tocam."""
        antes = [row(page=1, index=0, x0=50.0, y0=50.0, side_pt=100.0)]
        depois = [row(page=1, index=0, x0=400.0, y0=400.0, side_pt=100.0)]

        mudanca = diff_census(antes, depois)[0]

        self.assertEqual(len(mudanca.lost), 1)
        self.assertEqual(len(mudanca.gained), 1)
        self.assertEqual(mudanca.moved, [])

    def test_o_movimento_nao_atravessa_paginas(self) -> None:
        antes = [row(page=1, index=0)]
        depois = [row(page=2, index=0, x0=101.0)]

        mudanca = diff_census(antes, depois)[0]

        self.assertEqual(len(mudanca.lost), 1)
        self.assertEqual(len(mudanca.gained), 1)
        self.assertEqual(mudanca.moved, [])

    def test_o_glifo_removido_nao_vira_movimento_do_diagrama(self) -> None:
        """O caso da S-78 tem de continuar lendo como perda limpa, e não como reajuste."""
        antes = [glyph(page=1, index=0), row(page=1, index=1)]
        depois = [row(page=1, index=0)]

        mudanca = diff_census(antes, depois)[0]

        self.assertEqual(len(mudanca.lost), 1)
        self.assertEqual(mudanca.lost[0].side_pt, 15.4)
        self.assertEqual(mudanca.moved, [])

    def test_o_diff_separa_por_livro(self) -> None:
        antes = [row(pdf="a.pdf"), row(pdf="b.pdf")]
        depois = [row(pdf="a.pdf")]

        mudancas = diff_census(antes, depois)

        self.assertEqual([m.pdf for m in mudancas], ["b.pdf"])


def _pdf_no_disco(destino: Path, placements: list[tuple]) -> Path:
    doc = pdf_with_images(placements)
    try:
        doc.save(str(destino))
    finally:
        doc.close()
    return destino


class PontaAPontaTests(unittest.TestCase):
    """O que continua verdade depois da S-78: o censo roda, grava, e o CSV volta igual."""

    def test_censo_de_um_livro_sintetico(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = _pdf_no_disco(
                Path(tmp) / "sintetico.pdf",
                [(board_image(400), fitz.Rect(80, 100, 380, 400))],
            )
            livro = census_book(pdf, pages=1, dpi=150)

        self.assertEqual(livro.pdf, "sintetico.pdf")
        self.assertEqual(livro.pages_sampled, 1)
        self.assertEqual(livro.pages_failed, 0)
        self.assertGreaterEqual(livro.candidates, 1)
        self.assertEqual(livro.pages_with_candidate, 1)

        detectado = livro.rows[0]
        self.assertEqual(detectado.page, 1, "1-based, como a interface e o PGN contam")
        self.assertGreater(detectado.side_pt, 100.0)
        self.assertGreater(detectado.texture, 0.0)

    def test_pagina_em_branco_nao_e_falha(self) -> None:
        """Livro sem diagrama é caminho normal, não erro -- 12 dos 27 PDFs são scan puro."""
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "vazio.pdf"
            doc = fitz.open()
            doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
            doc.save(str(caminho))
            doc.close()

            livro = census_book(caminho, pages=1, dpi=150)

        self.assertEqual(livro.pages_failed, 0)
        self.assertEqual(livro.pages_with_candidate, 0)


class CliTests(unittest.TestCase):
    def test_um_livro_e_o_csv(self) -> None:
        from chess_diagram_ocr.cli.census import main

        with tempfile.TemporaryDirectory() as tmp:
            pdf = _pdf_no_disco(
                Path(tmp) / "sintetico.pdf",
                [(board_image(400), fitz.Rect(80, 100, 380, 400))],
            )
            destino = Path(tmp) / "censo.csv"
            codigo = main(["--pdf", str(pdf), "--pages", "1", "--dpi", "150", "--csv", str(destino)])

            self.assertEqual(codigo, 0)
            self.assertTrue(destino.is_file())
            self.assertGreaterEqual(len(read_census_csv(destino)), 1)

    def test_pdf_inexistente_sai_com_dois(self) -> None:
        from chess_diagram_ocr.cli.census import main

        self.assertEqual(main(["--pdf", "nao_existe.pdf"]), 2)

    def test_fail_on_loss_reprova_quando_some_candidato_acima_do_limiar(self) -> None:
        """O portão que uma mudança em detecção tem de atravessar."""
        from chess_diagram_ocr.cli.census import main

        with tempfile.TemporaryDirectory() as tmp:
            pdf = _pdf_no_disco(
                Path(tmp) / "sintetico.pdf",
                [(board_image(400), fitz.Rect(80, 100, 380, 400))],
            )
            # Uma baseline que "tinha" um diagrama a mais numa pagina que nao existe mais.
            baseline = Path(tmp) / "base.csv"
            write_census_csv(
                baseline,
                DetectionCensus(books=[BookCensus(pdf="sintetico.pdf", rows=[row(page=9, index=0, x0=10, y0=10)])]),
            )

            codigo = main(
                ["--pdf", str(pdf), "--pages", "1", "--dpi", "150", "--baseline", str(baseline), "--fail-on-loss"]
            )

        self.assertEqual(codigo, 1)


if __name__ == "__main__":
    unittest.main()
