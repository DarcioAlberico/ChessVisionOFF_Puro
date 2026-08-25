"""O arquivo do editor: ida, volta, e as recusas (S-238).

O `.txt` da aba é uma saída sem volta -- sem faixa, sem diagrama, sem `PaginaLida` e sem "abrir".
O que este arquivo afirma é o que o `.cvtxt` acrescenta: que **o que se grava é o que volta**, e que
o que não se sabe ler é recusado em português em vez de aberto pela metade.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from chess_diagram_ocr.text import arquivo, rico
from chess_diagram_ocr.text.pagina import (
    BlocoDeDiagrama,
    BlocoDeTexto,
    Coluna,
    LinhaLida,
    PaginaLida,
)

LIVRO = "/livros/AAGAARD - Practical Chess Defence.pdf"


def _texto(conteudo: str, confianca: float = 1.0, procedencia: str = "camada") -> BlocoDeTexto:
    return BlocoDeTexto.de_linhas(
        [LinhaLida(conteudo, (0.0, 0.0, 10.0, 10.0), confianca, procedencia)]  # type: ignore[arg-type]
    )


def _pagina(*blocos: object, documento: str = "", folha: int = 0) -> PaginaLida:
    return PaginaLida(
        documento=documento,
        pagina=folha,
        colunas=(Coluna(indice=0, blocos=tuple(blocos)),),  # type: ignore[arg-type]
    )


def _documento_de_exemplo() -> rico.DocumentoRico:
    return rico.de_pagina(
        _pagina(
            _texto("In this position White has a decisive resource."),
            BlocoDeDiagrama(indice=0, bbox=(10.0, 20.0, 60.0, 70.0), confianca=0.9),
            _texto("1...Bxb7 2.Bxb7 Nd7", 0.5, "glifo"),
            documento=LIVRO,
            folha=57,
        )
    )


class IdaEVoltaTests(unittest.TestCase):
    def test_salvar_e_reabrir_preserva_o_documento(self) -> None:
        doc = _documento_de_exemplo()
        with tempfile.TemporaryDirectory() as pasta:
            destino = arquivo.gravar(Path(pasta) / f"folha{arquivo.EXTENSAO}", doc)
            volta = arquivo.carregar(destino)
        self.assertEqual(volta.corridas, doc.corridas)
        self.assertEqual(volta.para_texto(), doc.para_texto())

    def test_a_pagina_de_origem_volta_inteira(self) -> None:
        """É ela que permite recortar a miniatura de novo -- por isso vai junto, e não o PNG."""
        doc = _documento_de_exemplo()
        with tempfile.TemporaryDirectory() as pasta:
            volta = arquivo.carregar(arquivo.gravar(Path(pasta) / "a.cvtxt", doc))
        assert volta.origem is not None and doc.origem is not None
        self.assertEqual(volta.origem.para_json(), doc.origem.para_json())

    def test_o_bbox_do_diagrama_sobrevive(self) -> None:
        doc = _documento_de_exemplo()
        with tempfile.TemporaryDirectory() as pasta:
            volta = arquivo.carregar(arquivo.gravar(Path(pasta) / "a.cvtxt", doc))
        assert volta.origem is not None
        self.assertEqual(volta.origem.diagramas[0].bbox, (10.0, 20.0, 60.0, 70.0))

    def test_a_faixa_e_a_procedencia_sobrevivem(self) -> None:
        doc = _documento_de_exemplo()
        with tempfile.TemporaryDirectory() as pasta:
            volta = arquivo.carregar(arquivo.gravar(Path(pasta) / "a.cvtxt", doc))
        adivinhada = [c for c in volta.corridas if c.faixa != "tranquilo"]
        self.assertTrue(adivinhada)
        self.assertEqual(adivinhada[0].procedencia, "glifo")

    def test_o_documento_sem_pagina_tambem_grava(self) -> None:
        doc = rico.de_texto("escrito do zero")
        with tempfile.TemporaryDirectory() as pasta:
            volta = arquivo.carregar(arquivo.gravar(Path(pasta) / "a.cvtxt", doc))
        self.assertEqual(volta, doc)
        self.assertIsNone(volta.origem)

    def test_nenhuma_imagem_e_embutida(self) -> None:
        """O diagrama é bbox e índice; o recorte se refaz do livro, que é onde o dado mora."""
        doc = _documento_de_exemplo()
        with tempfile.TemporaryDirectory() as pasta:
            destino = arquivo.gravar(Path(pasta) / "a.cvtxt", doc)
            bruto = destino.read_text(encoding="utf-8")
        self.assertLess(len(bruto), 20_000)
        self.assertNotIn("base64", bruto)
        self.assertNotIn("PNG", bruto)


class RecusaTests(unittest.TestCase):
    def test_versao_futura_recusa_em_portugues(self) -> None:
        dados = arquivo.para_json(rico.de_texto("oi"))
        dados["versao"] = arquivo.VERSAO + 1
        with self.assertRaises(arquivo.VersaoFutura) as caso:
            arquivo.de_json(dados)
        mensagem = str(caso.exception)
        self.assertIn("versão mais nova", mensagem)
        self.assertIn(str(arquivo.VERSAO + 1), mensagem)
        self.assertIn(str(arquivo.VERSAO), mensagem)

    def test_versao_igual_ou_menor_abre(self) -> None:
        dados = arquivo.para_json(rico.de_texto("oi"))
        self.assertEqual(arquivo.de_json(dados).para_texto(), "oi")

    def test_arquivo_sem_versao_recusa(self) -> None:
        with self.assertRaises(arquivo.ArquivoInvalido):
            arquivo.de_json({"documento": {"corridas": []}})

    def test_arquivo_sem_documento_recusa(self) -> None:
        with self.assertRaises(arquivo.ArquivoInvalido):
            arquivo.de_json({"versao": arquivo.VERSAO})

    def test_json_que_nao_e_objeto_recusa(self) -> None:
        with self.assertRaises(arquivo.ArquivoInvalido):
            arquivo.de_json([1, 2, 3])

    def test_arquivo_que_nao_e_json_recusa_nomeando_o_arquivo(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "quebrado.cvtxt"
            caminho.write_text("isto não é json", encoding="utf-8")
            with self.assertRaises(arquivo.ArquivoInvalido) as caso:
                arquivo.carregar(caminho)
        self.assertIn("quebrado.cvtxt", str(caso.exception))

    def test_a_versao_futura_e_um_arquivo_invalido(self) -> None:
        """Quem só quer saber "abriu ou não" pega uma exceção só."""
        self.assertTrue(issubclass(arquivo.VersaoFutura, arquivo.ArquivoInvalido))


class GravacaoTests(unittest.TestCase):
    def test_a_gravacao_nao_deixa_temporario(self) -> None:
        """`atomic_io` escreve ao lado e renomeia; sobrar o temporário seria a troca não ter fechado."""
        with tempfile.TemporaryDirectory() as pasta:
            destino = arquivo.gravar(Path(pasta) / "a.cvtxt", rico.de_texto("oi"))
            self.assertEqual([p.name for p in Path(pasta).iterdir()], [destino.name])

    def test_a_gravacao_cria_a_pasta_que_falta(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            destino = arquivo.gravar(Path(pasta) / "nova" / "a.cvtxt", rico.de_texto("oi"))
            self.assertTrue(destino.exists())

    def test_o_arquivo_e_json_legivel_por_fora(self) -> None:
        """Texto e não binário: quem precisar reparar um arquivo à mão consegue abri-lo."""
        with tempfile.TemporaryDirectory() as pasta:
            destino = arquivo.gravar(Path(pasta) / "a.cvtxt", _documento_de_exemplo())
            dados = json.loads(destino.read_text(encoding="utf-8"))
        self.assertEqual(dados["versao"], arquivo.VERSAO)
        self.assertIn("corridas", dados["documento"])

    def test_gravar_duas_vezes_da_o_mesmo_byte(self) -> None:
        """Sem data no corpo: dois arquivos do mesmo documento são comparáveis com `diff`."""
        doc = _documento_de_exemplo()
        with tempfile.TemporaryDirectory() as pasta:
            um = arquivo.gravar(Path(pasta) / "um.cvtxt", doc).read_bytes()
            outro = arquivo.gravar(Path(pasta) / "outro.cvtxt", doc).read_bytes()
        self.assertEqual(um, outro)


class NomeSugeridoTests(unittest.TestCase):
    def test_o_nome_sai_do_livro_e_da_folha(self) -> None:
        self.assertEqual(
            arquivo.sugestao_de_nome(_documento_de_exemplo()),
            "AAGAARD - Practical Chess Defence_folha58.cvtxt",
        )

    def test_a_extensao_e_trocavel_para_o_txt(self) -> None:
        """O `.txt` e o `.cvtxt` derivam o nome do mesmo lugar, e não de duas linhas parecidas."""
        nome = arquivo.sugestao_de_nome(_documento_de_exemplo(), extensao=".txt")
        self.assertTrue(nome.endswith("_folha58.txt"))

    def test_o_documento_sem_pagina_tem_nome_generico(self) -> None:
        self.assertEqual(arquivo.sugestao_de_nome(rico.de_texto("oi")), "texto.cvtxt")


class PdfDeOrigemTests(unittest.TestCase):
    def test_o_caminho_do_livro_volta_do_documento(self) -> None:
        caminho = arquivo.pdf_de(_documento_de_exemplo())
        assert caminho is not None
        self.assertEqual(caminho.name, "AAGAARD - Practical Chess Defence.pdf")

    def test_documento_sem_pagina_nao_tem_livro(self) -> None:
        self.assertIsNone(arquivo.pdf_de(rico.de_texto("oi")))

    def test_nao_pergunta_se_o_livro_existe(self) -> None:
        """Distinguir "não tem livro" de "o livro mudou de lugar" é do painel, e ele precisa dos dois."""
        self.assertIsNotNone(arquivo.pdf_de(_documento_de_exemplo()))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
