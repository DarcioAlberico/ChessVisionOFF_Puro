"""A camada de texto invisível: o PDF pesquisável do que o motor leu (S-210).

Os quatro critérios de aceite do item viram quatro testes com o nome que a spec deu. O primeiro é
o que separa este item de qualquer outro jeito de fazer a mesma coisa: **a página não muda um
pixel**, e isso se confere comparando os pixmaps -- não olhando o código.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from chess_diagram_ocr.text.pdf_pesquisavel import (
    FIGURINA_PARA_LETRA,
    PISO_DA_CAMADA,
    contar_losangos,
    escrever_camada,
    linhas_da_camada,
    pares_sem_mapeamento,
    transliterar,
)


def livro(caminho: Path, *, texto: str = "", folhas: int = 1) -> Path:
    """Um PDF de teste com `folhas` páginas, e um texto opcional pintado na primeira."""
    import fitz

    doc = fitz.open()
    for numero in range(folhas):
        pagina = doc.new_page(width=300, height=200)
        if texto and numero == 0:
            pagina.insert_text((20, 40), texto, fontsize=11, fontname="helv")
    doc.save(str(caminho))
    doc.close()
    return caminho


def pagina_lida(*linhas, documento: str = "", numero: int = 0):
    """Uma `PaginaLida` com um bloco de texto e as linhas dadas: `(texto, confianca, bbox)`."""
    from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida

    lidas = tuple(
        LinhaLida(texto=t, bbox=bbox, confianca=c, procedencia="glifo") for t, c, bbox in linhas
    )
    bloco = BlocoDeTexto(linhas=lidas, bbox=(10.0, 20.0, 290.0, 180.0), confianca=1.0, procedencia="glifo")
    return PaginaLida(
        documento=documento,
        pagina=numero,
        largura=300.0,
        altura=200.0,
        colunas=(Coluna(indice=0, blocos=(bloco,), bbox=(10.0, 20.0, 290.0, 180.0)),),
    )


class PixelTests(unittest.TestCase):
    def test_a_pagina_nao_muda_um_pixel(self) -> None:
        """O critério de aceite que separa este item de qualquer outro jeito de fazer o mesmo."""
        import fitz

        with TemporaryDirectory() as raiz:
            origem = livro(Path(raiz) / "livro.pdf", texto="uma pagina impressa")
            destino = Path(raiz) / "saida.pdf"
            lida = pagina_lida(("uma pagina impressa", 0.9, (20.0, 30.0, 200.0, 45.0)), documento=str(origem))
            relatorio = escrever_camada([lida], destino, origem=origem)
            self.assertEqual(1, relatorio.linhas, "nada foi escrito: o teste não provaria nada")

            antes, depois = fitz.open(origem), fitz.open(destino)
            try:
                self.assertEqual(
                    antes[0].get_pixmap(dpi=100).tobytes("png"),
                    depois[0].get_pixmap(dpi=100).tobytes("png"),
                )
            finally:
                antes.close()
                depois.close()

    def test_a_busca_encontra_a_palavra_no_lugar_certo(self) -> None:
        """E o retângulo cobre a **palavra**, e não o parágrafo -- é o que a camada por linha dá."""
        import fitz

        with TemporaryDirectory() as raiz:
            origem = livro(Path(raiz) / "livro.pdf")
            destino = Path(raiz) / "saida.pdf"
            caixa = (20.0, 30.0, 120.0, 45.0)
            lida = pagina_lida(("Nimzowitsch defende", 0.9, caixa), documento=str(origem))
            escrever_camada([lida], destino, origem=origem)

            saida = fitz.open(destino)
            try:
                achados = saida[0].search_for("Nimzowitsch")
                self.assertEqual(1, len(achados), "a busca não achou a palavra que a camada tem")
                retangulo = achados[0]
                # A folga é a de `FOLGA_DA_CAIXA`: a camada escreve num retângulo 2 pt maior que a
                # bbox da linha, para o `insert_textbox` aceitar o texto.
                da_linha = fitz.Rect(*caixa) + (-3, -3, 3, 3)
                self.assertTrue(
                    da_linha.contains(retangulo),
                    f"o retângulo da busca {tuple(retangulo)} saiu da linha {tuple(da_linha)}",
                )
                self.assertLess(
                    retangulo.width,
                    (caixa[2] - caixa[0]) * 0.9,
                    "o retângulo cobre a linha inteira: a camada não está por palavra",
                )
            finally:
                saida.close()


class PisoTests(unittest.TestCase):
    def test_o_glifo_sem_votacao_folgada_nao_entra(self) -> None:
        """A trava herdada, sobre a matéria que **existe** neste acervo.

        A spec a escreveu sobre o glifo do `ToUnicode` -- *"glifo cuja votação não fecha continua
        `U+FFFD`"* --, e aqui não há `U+FFFD` nenhum (ver `pares_sem_mapeamento`). A mesma regra
        cai sobre a linha lida: uma leitura sem votação folgada não entra na camada, porque a
        camada é invisível e um acerto de busca falso não tem como ser desmentido.
        """
        lida = pagina_lida(
            ("confiante", 0.95, (20.0, 30.0, 200.0, 45.0)),
            ("adivinhada", 0.05, (20.0, 50.0, 200.0, 65.0)),
        )
        linhas, relatorio = linhas_da_camada(lida)
        self.assertEqual(["confiante"], [linha.texto for linha in linhas])
        self.assertEqual(1, relatorio.abaixo_do_piso)

    def test_o_relatorio_diz_o_motivo(self) -> None:
        """"1 linha fora" manda procurar; o motivo escrito manda decidir."""
        with TemporaryDirectory() as raiz:
            origem = livro(Path(raiz) / "livro.pdf")
            lida = pagina_lida(("adivinhada", 0.05, (20.0, 30.0, 200.0, 45.0)), documento=str(origem))
            relatorio = escrever_camada([lida], Path(raiz) / "s.pdf", origem=origem, seco=True)
        self.assertTrue(any("abaixo de" in aviso for aviso in relatorio.avisos))

    def test_o_piso_e_o_da_S42(self) -> None:
        """Um corte, num lugar só: é o piso com que este projeto já decide se um motor vale."""
        from chess_diagram_ocr.ocr import MIN_CONFIDENCE

        self.assertAlmostEqual(float(MIN_CONFIDENCE), PISO_DA_CAMADA)

    def test_a_camada_de_texto_do_pdf_nao_e_alcancada_pelo_piso(self) -> None:
        """Ela vale 1,0 e é o que o editor escreveu -- não é palpite de motor nenhum."""
        from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida

        linha = LinhaLida(texto="da camada", bbox=(20.0, 30.0, 200.0, 45.0), confianca=1.0, procedencia="camada")
        bloco = BlocoDeTexto(linhas=(linha,), bbox=(10.0, 20.0, 290.0, 180.0), procedencia="camada")
        pagina = PaginaLida(documento="", pagina=0, largura=300.0, altura=200.0,
                            colunas=(Coluna(indice=0, blocos=(bloco,), bbox=(10.0, 20.0, 290.0, 180.0)),))
        linhas, _ = linhas_da_camada(pagina)
        self.assertEqual(["da camada"], [x.texto for x in linhas])


class SecoTests(unittest.TestCase):
    def test_o_dry_run_nao_escreve(self) -> None:
        """Critério de aceite: `--seco` diz o que faria sem escrever nada."""
        with TemporaryDirectory() as raiz:
            origem = livro(Path(raiz) / "livro.pdf")
            destino = Path(raiz) / "saida.pdf"
            lida = pagina_lida(("uma linha", 0.9, (20.0, 30.0, 200.0, 45.0)), documento=str(origem))
            relatorio = escrever_camada([lida], destino, origem=origem, seco=True)

            self.assertFalse(destino.exists(), "o modo seco gravou o arquivo")
            self.assertTrue(relatorio.seco)
            self.assertIsNone(relatorio.escrito)
            self.assertEqual(1, relatorio.linhas, "o modo seco tem de dizer o que faria")

    def test_o_seco_e_o_molhado_contam_a_mesma_coisa(self) -> None:
        """Um ensaio que contasse diferente do que a corrida faz não serviria para decidir nada."""
        with TemporaryDirectory() as raiz:
            origem = livro(Path(raiz) / "livro.pdf")
            lida = pagina_lida(
                ("uma linha", 0.9, (20.0, 30.0, 200.0, 45.0)),
                ("outra ♘f3", 0.9, (20.0, 50.0, 200.0, 65.0)),
                documento=str(origem),
            )
            seco = escrever_camada([lida], Path(raiz) / "a.pdf", origem=origem, seco=True)
            molhado = escrever_camada([lida], Path(raiz) / "b.pdf", origem=origem)
        for campo in ("paginas", "linhas", "caracteres", "figurinas", "abaixo_do_piso"):
            with self.subTest(campo=campo):
                self.assertEqual(getattr(seco, campo), getattr(molhado, campo))


class FigurinaTests(unittest.TestCase):
    def test_a_figurina_vira_letra_do_algebrico(self) -> None:
        """A camada é um índice, e não uma renderização: `Nf3` é o que quem busca digita."""
        self.assertEqual(("2.Nxd4 dxc2!", 1), transliterar("2.♘xd4 dxc2!"))

    def test_as_duas_cores_vao_para_a_mesma_letra(self) -> None:
        """O algébrico não distingue cor; quem distingue é de quem é a vez."""
        self.assertEqual(FIGURINA_PARA_LETRA["♘"], FIGURINA_PARA_LETRA["♞"])

    def test_o_texto_sem_figurina_volta_identico(self) -> None:
        self.assertEqual(("uma linha de prosa", 0), transliterar("uma linha de prosa"))

    def test_sem_figurinas_a_notacao_cai_fora_pela_fonte(self) -> None:
        """É o que a troca existe para evitar: sem ela a camada perde o que motivou o item."""
        lida = pagina_lida(("2.♘xd4 ♗g5", 0.9, (20.0, 30.0, 200.0, 45.0)))
        com, _ = linhas_da_camada(lida, figurinas=True)
        sem, relatorio_sem = linhas_da_camada(lida, figurinas=False)
        self.assertIn("N", com[0].texto)
        self.assertNotIn("N", sem[0].texto)
        self.assertEqual(2, relatorio_sem.fora_da_fonte)


class ToUnicodeTests(unittest.TestCase):
    """O caminho vizinho da spec, e a medição que decidiu não construí-lo."""

    def test_o_livro_sem_losango_devolve_lista_vazia(self) -> None:
        with TemporaryDirectory() as raiz:
            origem = livro(Path(raiz) / "livro.pdf", texto="prosa normal")
            self.assertEqual((), pares_sem_mapeamento(origem))

    def test_o_par_sem_mapeamento_e_contado_por_fonte(self) -> None:
        """Sobre o dicionário do `get_text`, e não sobre um PDF sintético: a `helv` da base 14 não
        carrega `U+FFFD` -- ela o grava como `·`, e o teste mediria a fonte de teste."""
        folhas = [
            {"blocks": [{"lines": [
                {"spans": [{"text": "a � b �", "font": "ChessFont"}]},
                {"spans": [{"text": "prosa limpa", "font": "Times"}]},
            ]}]},
            {"blocks": [{"lines": [{"spans": [{"text": "�", "font": "ChessFont"}]}]}]},
        ]
        pares = contar_losangos(folhas)
        self.assertEqual(1, len(pares))
        self.assertEqual("ChessFont", pares[0].fonte)
        self.assertEqual(3, pares[0].ocorrencias)

    def test_a_contagem_ordena_por_ocorrencia(self) -> None:
        folhas = [{"blocks": [{"lines": [{"spans": [
            {"text": "�", "font": "Rara"},
            {"text": "��", "font": "Comum"},
        ]}]}]}]
        self.assertEqual(["Comum", "Rara"], [p.fonte for p in contar_losangos(folhas)])

    def test_folha_vazia_nao_estoura(self) -> None:
        self.assertEqual((), contar_losangos([{}, {"blocks": []}]))

    def test_o_reescritor_de_tounicode_nao_existe(self) -> None:
        """A recusa é decisão medida: zero `U+FFFD` em 14 livros do acervo (2026-08-26)."""
        from chess_diagram_ocr.text import pdf_pesquisavel

        self.assertFalse(hasattr(pdf_pesquisavel, "reescrever_tounicode"))


class CamadaExistenteTests(unittest.TestCase):
    def test_a_folha_que_ja_tem_texto_e_contada_e_avisada(self) -> None:
        """Tirar a camada de origem mudaria o pixel: a nossa soma à dela, e o relatório diz."""
        with TemporaryDirectory() as raiz:
            origem = livro(Path(raiz) / "livro.pdf", texto="ja tinha texto")
            lida = pagina_lida(("ja tinha texto", 0.9, (20.0, 30.0, 200.0, 45.0)), documento=str(origem))
            relatorio = escrever_camada([lida], Path(raiz) / "s.pdf", origem=origem, seco=True)
        self.assertEqual(1, relatorio.ja_tinham_camada)
        self.assertTrue(any("já tinham texto" in aviso for aviso in relatorio.avisos))

    def test_so_sem_camada_pula_a_folha(self) -> None:
        with TemporaryDirectory() as raiz:
            origem = livro(Path(raiz) / "livro.pdf", texto="ja tinha texto")
            lida = pagina_lida(("ja tinha texto", 0.9, (20.0, 30.0, 200.0, 45.0)), documento=str(origem))
            relatorio = escrever_camada([lida], Path(raiz) / "s.pdf", origem=origem, so_sem_camada=True, seco=True)
        self.assertEqual(0, relatorio.linhas)
        self.assertEqual(1, relatorio.ja_tinham_camada)

    def test_sem_pagina_lida_nao_estoura(self) -> None:
        with TemporaryDirectory() as raiz:
            relatorio = escrever_camada([], Path(raiz) / "s.pdf", origem=Path(raiz) / "x.pdf")
        self.assertEqual(0, relatorio.linhas)
        self.assertTrue(relatorio.avisos)

    def test_livro_que_sumiu_avisa_em_vez_de_estourar(self) -> None:
        with TemporaryDirectory() as raiz:
            lida = pagina_lida(("x", 0.9, (20.0, 30.0, 200.0, 45.0)), documento=str(Path(raiz) / "nao-existe.pdf"))
            relatorio = escrever_camada([lida], Path(raiz) / "s.pdf")
        self.assertTrue(any("não está no lugar" in aviso for aviso in relatorio.avisos))

    def test_o_diagrama_nao_entra_na_camada(self) -> None:
        """`[Diagrama N]` nunca esteve impresso na página."""
        from chess_diagram_ocr.text.pagina import BlocoDeDiagrama, Coluna, PaginaLida

        bloco = BlocoDeDiagrama(indice=0, bbox=(10.0, 20.0, 100.0, 110.0))
        pagina = PaginaLida(documento="", pagina=0, largura=300.0, altura=200.0,
                            colunas=(Coluna(indice=0, blocos=(bloco,), bbox=(10.0, 20.0, 100.0, 110.0)),))
        self.assertEqual((), linhas_da_camada(pagina)[0])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
