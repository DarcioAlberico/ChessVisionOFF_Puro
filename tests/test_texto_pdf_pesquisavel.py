"""O PDF pesquisável feito do texto que uma pessoa corrigiu (S-253).

**O primeiro teste é o critério de aceite inteiro:** a página de saída é pixel a pixel idêntica à de
entrada. A camada é texto invisível (`render_mode=3`) sobre a página original -- se ela pintasse um
pixel, o produto deixaria de ser "o livro, pesquisável" e passaria a ser "uma versão do livro".

Os outros três travam as honestidades do item: corrida sem bloco de origem **não entra** (inventar
posição é pior que não ter o texto), o metadado **declara** que a camada tem correção humana, e a
figurina que a fonte da base 14 não escreve é **contada** em vez de virar `?`.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr.text import pdf_pesquisavel as PP
from chess_diagram_ocr.text import rico
from chess_diagram_ocr.text.pagina import BlocoDeDiagrama, BlocoDeTexto, Coluna, LinhaLida, PaginaLida

try:  # pragma: no cover - a suíte roda sem PyMuPDF em máquina de CI mínima
    import fitz
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore[assignment]


def _livro(pasta: Path) -> Path:
    caminho = pasta / "livro.pdf"
    doc = fitz.open()
    pagina = doc.new_page(width=300, height=200)
    pagina.insert_text((40, 60), "texto impresso da pagina", fontsize=11)
    doc.save(str(caminho))
    doc.close()
    return caminho


def _documento(livro: Path, *, texto: str = "texto corrigido a mao") -> rico.DocumentoRico:
    bloco = BlocoDeTexto.de_linhas([LinhaLida(texto, (35.0, 45.0, 265.0, 70.0), 0.4, "glifo")])
    pagina = PaginaLida(documento=str(livro), pagina=0, colunas=(Coluna(indice=0, blocos=(bloco,)),))
    return rico.de_pagina(pagina)


@unittest.skipIf(fitz is None, "PyMuPDF não instalado")
class CamadaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)
        self.livro = _livro(self.pasta)

    def test_a_pagina_nao_muda_um_pixel(self) -> None:
        """O primeiro critério de aceite, e o que separa "o livro pesquisável" de "outro livro"."""
        doc = _documento(self.livro)
        destino = self.pasta / "saida.pdf"
        PP.escrever(doc, destino)

        antes = fitz.open(str(self.livro))
        depois = fitz.open(str(destino))
        try:
            self.assertEqual(antes[0].get_pixmap(dpi=110).samples, depois[0].get_pixmap(dpi=110).samples)
        finally:
            antes.close()
            depois.close()

    def test_a_busca_encontra_a_palavra_corrigida(self) -> None:
        """E o retângulo devolvido cobre a palavra **na região do bloco**, e não em qualquer canto."""
        doc = _documento(self.livro)
        destino = self.pasta / "saida.pdf"
        PP.escrever(doc, destino)

        saida = fitz.open(str(destino))
        try:
            achados = saida[0].search_for("corrigido")
            self.assertTrue(achados, "a palavra corrigida não entrou na camada")
            caixa = achados[0]
            self.assertGreaterEqual(caixa.x0, 30)
            self.assertLessEqual(caixa.y1, 80)
        finally:
            saida.close()

    def test_cada_trecho_entra_na_camada_uma_vez_so(self) -> None:
        """A sonda que escrevia (S-303).

        `_corpo_que_cabe` tinha nome de medição e gravava: o `insert_textbox` do PyMuPDF termina
        em `if rc >= 0: img.commit(overlay)`. Os dois chamadores gravavam de novo em seguida, e
        toda linha entrava **duas vezes** na camada invisível. Nada disso aparecia na tela --
        `render_mode=3` não pinta pixel --, e por isso os dois testes que existiam
        (`test_a_pagina_nao_muda_um_pixel` e a busca, que já achava) continuavam verdes. O
        defeito só aparece para quem copia o texto, indexa o arquivo, ou conta caracteres.

        Contar **ocorrências** e não "achou": é a diferença entre este teste e o da busca.
        """
        doc = _documento(self.livro)
        destino = self.pasta / "saida.pdf"
        relatorio = PP.escrever(doc, destino)

        saida = fitz.open(str(destino))
        try:
            camada = saida[0].get_text()
        finally:
            saida.close()

        self.assertEqual(camada.count("texto corrigido a mao"), 1)
        self.assertEqual(relatorio.trechos, 1, "o relatório já contava uma; era a camada que tinha duas")

    def test_a_corrida_sem_bloco_nao_entra(self) -> None:
        """Não há onde a pôr, e inventar posição é pior que não ter o texto. O relatório a conta."""
        doc = _documento(self.livro)
        # Escrita do zero de verdade: `rico.inserir` herda o bloco da esquerda por desenho
        # (S-248), e o que este teste precisa é da corrida que **não** tem origem nenhuma.
        solta = rico.Corrida(texto="escrito do zero", procedencia="humano")
        doc = rico.DocumentoRico(corridas=(*doc.corridas, solta), origem=doc.origem)
        trechos, relatorio = PP.camada(doc)
        self.assertEqual(relatorio.sem_bloco, 1)
        self.assertNotIn("do zero", " ".join(trecho.texto for trecho in trechos))

    def test_a_marca_do_diagrama_nao_entra_na_camada(self) -> None:
        """`[Diagrama 3]` nunca esteve impresso na página, e a camada existe para espelhar o livro."""
        bloco = BlocoDeDiagrama(indice=2, bbox=(10.0, 10.0, 90.0, 90.0))
        pagina = PaginaLida(
            documento=str(self.livro), pagina=0, colunas=(Coluna(indice=0, blocos=(bloco,)),)
        )
        trechos, relatorio = PP.camada(rico.de_pagina(pagina))
        self.assertEqual(trechos, ())
        self.assertEqual(relatorio.diagramas, 1)

    def test_o_metadado_declara_correcao_humana(self) -> None:
        doc = _documento(self.livro)
        destino = self.pasta / "saida.pdf"
        PP.escrever(doc, destino, quando="2026-08-25")
        saida = fitz.open(str(destino))
        try:
            metadado = saida.metadata or {}
            self.assertIn("correção humana", str(metadado.get("producer", "")))
            self.assertIn("2026-08-25", str(metadado.get("keywords", "")))
        finally:
            saida.close()

    def test_sem_fonte_de_figurina_entrega_o_latino(self) -> None:
        """**Não falha**: entrega o que dá e conta o que não deu (a regra de `ui/theme.py`)."""
        doc = _documento(self.livro, texto="lance 1.♘f3 corrigido")
        trechos, relatorio = PP.camada(doc)
        self.assertEqual(relatorio.fora_da_fonte, 1)
        self.assertNotIn("♘", trechos[0].texto)
        self.assertIn("corrigido", trechos[0].texto)

    def test_o_dry_run_nao_escreve(self) -> None:
        doc = _documento(self.livro)
        destino = self.pasta / "nao_deve_existir.pdf"
        relatorio = PP.escrever(doc, destino, seco=True)
        self.assertFalse(destino.exists())
        self.assertTrue(relatorio.seco)
        self.assertIsNone(relatorio.escrito)

    def test_o_livro_fora_do_lugar_nao_levanta(self) -> None:
        """Pasta de trabalho movida é caso comum, e a resposta é dizer -- não estourar."""
        bloco = BlocoDeTexto.de_linhas([LinhaLida("texto", (0.0, 0.0, 50.0, 20.0), 1.0, "glifo")])
        pagina = PaginaLida(
            documento=str(self.pasta / "sumiu.pdf"), pagina=0, colunas=(Coluna(indice=0, blocos=(bloco,)),)
        )
        relatorio = PP.escrever(rico.de_pagina(pagina), self.pasta / "saida.pdf")
        self.assertIn("não está no lugar", " ".join(relatorio.avisos))

    def test_o_relatorio_traz_as_tres_secoes(self) -> None:
        doc = _documento(self.livro, texto="lance 1.♘f3 corrigido")
        relatorio = PP.escrever(doc, self.pasta / "saida.pdf")
        texto = PP.texto_do_relatorio(relatorio)
        for secao in ("escrito", "perdido", "avisado"):
            with self.subTest(secao=secao):
                self.assertIn(secao, texto)


class LatinoTests(unittest.TestCase):
    def test_o_que_a_fonte_nao_escreve_e_contado_e_nao_trocado(self) -> None:
        """Escrever `?` poria um caractere errado na busca de quem procurasse pela figurina."""
        dentro, fora = PP.latino("Nf3 ♘f3 ± ⩲")
        # `±` é U+00B1 e **cabe** em Latin-1; `♘` e `⩲` não cabem, e são os dois contados.
        self.assertEqual(fora, 2)
        self.assertNotIn("?", dentro)
        self.assertIn("Nf3", dentro)

    def test_o_acentuado_cabe_na_camada(self) -> None:
        """Latin-1 é o que a base 14 cobre, e o acervo é multilíngue: `ç` e `é` entram."""
        dentro, fora = PP.latino("posição é anotação")
        self.assertEqual(fora, 0)
        self.assertEqual(dentro, "posição é anotação")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
