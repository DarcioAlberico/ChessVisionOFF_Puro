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

import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import fitz
from test_detection import PAGE_HEIGHT, PAGE_WIDTH, board_image, pdf_with_images

from chess_diagram_ocr.board_detection import MOTIVOS_DE_RECUSA, RejectedQuad
from chess_diagram_ocr.detection_census import (
    REJECTION_CSV_FIELDS,
    SUSPECT_BELOW_PT,
    BookCensus,
    CandidateRow,
    DetectionCensus,
    RejectionRow,
    census_book,
    census_page,
    diff_census,
    read_census_csv,
    rejections_by_reason,
    write_census_csv,
    write_census_json,
    write_rejections_csv,
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


class RecusasTests(unittest.TestCase):
    """O que foi **barrado**, e por qual guarda (S-131).

    O censo da S-82 conta o que entra e é cego ao que foi recusado — e é do lado recusado que
    mora o recall perdido. Sem isto, mexer num limiar de `board_detection.py` é medir metade do
    efeito: dá para ver o falso positivo que sumiu, e não o diagrama que sumiu junto.
    """

    MOTIVOS_DO_HIBRIDO = (
        "prior-de-tamanho",
        "perdeu-para-embutido",
        "faixa-da-pagina",
        "teto-da-pagina",
    )
    """As guardas que moram no `detection/hybrid`, e não no `board_detection`.

    Eram quatro: `"sem-contraste-de-casa"` mudou de casa na S-160 e agora está em
    `MOTIVOS_DE_RECUSA`. Ele precisava correr **antes** da ordenação por score e da supressão
    por IoU do `detect_boards`, e aqui só alcançava o que aquela função já tinha devolvido.

    `"faixa-da-pagina"` entrou na S-176, e é a **única** que barra candidato da fonte embutida
    -- as outras três julgam achado de contorno. Ver `hybrid.BAND_BOARD_FILL`.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cvoff-s131-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pdf = _pdf_no_disco(
            self.tmp / "recusas.pdf",
            # Um tabuleiro e um retângulo achatado: o segundo é o que reprova no aspecto.
            [
                (board_image(400), fitz.Rect(80, 100, 380, 400)),
                (board_image(400), fitz.Rect(60, 450, 500, 620)),
            ],
        )

    def test_sem_pedir_recusas_nada_e_montado(self) -> None:
        """`rejections=None` é o padrão, e precisa continuar barato: o censo roda no acervo."""
        linhas = census_page(self.pdf, 0, "recusas.pdf", dpi=150)
        self.assertGreaterEqual(len(linhas), 1)

    def test_as_recusas_saem_em_ponto_do_pdf_como_os_aceitos(self) -> None:
        """Os dois CSVs se leem lado a lado, então precisam da mesma unidade."""
        recusas: list[RejectionRow] = []
        aceitos = census_page(self.pdf, 0, "recusas.pdf", dpi=150, rejections=recusas)

        self.assertTrue(recusas, "a página sintética precisa produzir alguma recusa")
        conhecidos = set(MOTIVOS_DE_RECUSA) | set(self.MOTIVOS_DO_HIBRIDO)
        for recusa in recusas:
            self.assertEqual(recusa.pdf, "recusas.pdf")
            self.assertEqual(recusa.page, 1, "1-based, como no CandidateRow")
            self.assertIn(recusa.reason, conhecidos)
            # Em ponto do PDF, e não em pixel do render: a 150 DPI o pixel é ~2x o ponto, e
            # uma caixa em pixel estouraria a página.
            self.assertLessEqual(recusa.x1, PAGE_WIDTH + 1)
            self.assertLessEqual(recusa.y1, PAGE_HEIGHT + 1)
        self.assertGreaterEqual(len(aceitos), 1)

    def test_o_speckle_abaixo_do_piso_de_area_nao_entra(self) -> None:
        """A medição que mudou o desenho: registrar tudo deu 2,6 milhões de linhas.

        Na primeira corrida do instrumento sobre o acervo foram **2.630.560 recusas contra 499
        aceitos**, lado mediano de 4,6 pt, num CSV de 280 MB. Manchas de contorno abaixo do piso
        de área não são candidato barrado — são ruído que o `findContours` produz aos milhões, e
        nenhuma delas pode ser um diagrama perdido. Com elas fora sobram 4.944 recusas e 564 KB.
        """
        recusas: list[RejectionRow] = []
        census_page(self.pdf, 0, "recusas.pdf", dpi=150, rejections=recusas)

        minusculas = [r for r in recusas if r.side_pt < 20.0]
        self.assertEqual([], minusculas, "recusa de menos de 20 pt não é candidato, é speckle")

    def test_o_motivo_de_cada_guarda_do_detect_boards(self) -> None:
        """Direto no `detect_boards`, sem PDF: é onde as sete guardas moram.

        Eram seis: o piso de contraste de casa passou a rodar aqui na S-160, antes da disputa
        por score e IoU, em vez de no laço do `hybrid` -- ver `MOTIVOS_DO_HIBRIDO`.
        """
        import numpy as np

        from chess_diagram_ocr.board_detection import detect_boards

        pagina = np.full((800, 600, 3), 255, dtype=np.uint8)
        pagina[100:400, 100:400] = board_image(300)
        pagina[500:700, 100:500] = 40  # retângulo achatado: reprova no aspecto

        recusados: list[RejectedQuad] = []
        detect_boards(pagina, max_boards=1, rejected=recusados)

        motivos = {recusa.reason for recusa in recusados}
        self.assertTrue(motivos, "a página sintética precisa barrar alguma coisa")
        self.assertTrue(
            motivos <= set(MOTIVOS_DE_RECUSA),
            f"motivo fora de MOTIVOS_DE_RECUSA: {motivos - set(MOTIVOS_DE_RECUSA)}",
        )
        for recusa in recusados:
            self.assertEqual(len(recusa.bbox), 4)

    def test_o_csv_de_recusas_grava_os_dez_campos(self) -> None:
        recusas = [
            RejectionRow(
                pdf="livro.pdf", page=7, reason="score-baixo", score=0.03, checker=0.0,
                side_pt=118.4, x0=10.0, y0=20.0, x1=128.4, y1=138.4,
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "recusas.csv"
            write_rejections_csv(destino, recusas)
            linhas = destino.read_text(encoding="utf-8").splitlines()

        self.assertEqual(linhas[0].split(","), list(REJECTION_CSV_FIELDS))
        self.assertIn("score-baixo", linhas[1])
        self.assertIn("118.4", linhas[1])

    def test_o_resumo_agrupa_por_motivo(self) -> None:
        recusas = [
            RejectionRow(pdf="a.pdf", page=1, reason="aspecto", score=0.0, checker=0.0,
                         side_pt=100.0, x0=0.0, y0=0.0, x1=100.0, y1=100.0),
            RejectionRow(pdf="a.pdf", page=2, reason="aspecto", score=0.0, checker=0.0,
                         side_pt=90.0, x0=0.0, y0=0.0, x1=90.0, y1=90.0),
            RejectionRow(pdf="a.pdf", page=3, reason="score-baixo", score=0.01, checker=0.0,
                         side_pt=80.0, x0=0.0, y0=0.0, x1=80.0, y1=80.0),
        ]
        self.assertEqual(rejections_by_reason(recusas), Counter({"aspecto": 2, "score-baixo": 1}))


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
