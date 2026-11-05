"""O `.djvu` que vira PDF: a rota rápida, a página a página e a resolução do dicionário.

O `djvu-rs` não codifica, e um livro de verdade não entra no repositório. Por isso a biblioteca real
só é exercitada com a menor página que o formato permite (só o `INFO`), e as falhas medidas no acervo
(`PanicException`, dicionário com nome em CP1251) são reproduzidas por uma biblioteca de mentira.
"""

from __future__ import annotations

import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import fitz
from PIL import Image

from chess_diagram_ocr import livro_djvu


def _pedaco(nome: bytes, conteudo: bytes) -> bytes:
    return nome + struct.pack(">I", len(conteudo)) + conteudo + (b"\0" if len(conteudo) % 2 else b"")


def _info(largura: int = 300, altura: int = 600, dpi: int = 300) -> bytes:
    return struct.pack(">HH", largura, altura) + bytes([26, 0]) + struct.pack("<H", dpi) + bytes([22, 1])


def _form(tipo: bytes, *pedacos: bytes) -> bytes:
    miolo = tipo + b"".join(pedacos)
    return b"FORM" + struct.pack(">I", len(miolo)) + miolo


def _pagina_real(largura: int = 300, altura: int = 600, dpi: int = 300) -> bytes:
    return b"AT&T" + _form(b"DJVU", _pedaco(b"INFO", _info(largura, altura, dpi)))


def _agrupado(*componentes: bytes) -> bytes:
    return b"AT&T" + _form(b"DJVM", _pedaco(b"DIRM", b"\x81"), *componentes)


class PanicException(BaseException):
    """Tem o nome do que o PyO3 levanta, e descende do mesmo lugar."""


class _Erro(Exception):
    pass


class _Pixmap:
    def __init__(self, largura: int, altura: int, cor: tuple[int, int, int, int]) -> None:
        self._imagem = Image.new("RGBA", (largura, altura), cor)

    def to_pil(self) -> Image.Image:
        return self._imagem


class _Pagina:
    def __init__(self, comportamento: BaseException | None = None, *, dpi: int = 300) -> None:
        self.width, self.height, self.dpi = 300, 600, dpi
        self.comportamento = comportamento
        self.pedidos: list[float | None] = []

    def render(self, dpi: float | None = None) -> _Pixmap:
        self.pedidos.append(dpi)
        if self.comportamento is not None and dpi is None:
            raise self.comportamento
        if isinstance(self.comportamento, _Erro):
            raise self.comportamento
        return _Pixmap(self.width, self.height, (255, 255, 255, 255))


def _biblioteca(paginas: list[_Pagina], *, avulsa: _Pagina | None = None) -> types.SimpleNamespace:
    def escrever(_caminho: str, **_opcoes: object) -> None:
        raise _Erro("PDF export failed")

    documento = types.SimpleNamespace(
        page_count=lambda: len(paginas), page=lambda i: paginas[i], write_pdf=escrever
    )
    return types.SimpleNamespace(
        Error=_Erro,
        Document=types.SimpleNamespace(
            open=lambda _caminho: documento,
            from_bytes=lambda _dados: types.SimpleNamespace(page=lambda _i: avulsa),
        ),
    )


class _ComPasta(unittest.TestCase):
    def setUp(self) -> None:
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.saida = self.pasta / "convertidos"

    def djvu(self, conteudo: bytes = b"", nome: str = "livro.djvu") -> Path:
        caminho = self.pasta / nome
        caminho.write_bytes(conteudo or _pagina_real())
        return caminho


class TestSufixo(unittest.TestCase):
    def test_reconhece_as_duas_grafias_em_qualquer_caixa(self) -> None:
        for nome in ("a.djvu", "a.djv", "a.Djvu", "A.DJVU"):
            self.assertTrue(livro_djvu.e_djvu(nome), nome)
        self.assertFalse(livro_djvu.e_djvu("a.pdf"))


class TestComABibliotecaReal(_ComPasta):
    def test_a_pagina_vira_pdf_do_tamanho_fisico_dela(self) -> None:
        conversao = livro_djvu.pdf_de_djvu(self.djvu(_pagina_real(300, 600, 300)), pasta=self.saida)
        self.assertEqual(conversao.paginas, 1)
        self.assertEqual(conversao.ilegiveis, ())
        self.assertEqual(conversao.pdf.name, "livro.pdf")
        with fitz.open(conversao.pdf) as pdf:
            self.assertEqual(pdf.page_count, 1)
            self.assertAlmostEqual(pdf[0].rect.width, 72, places=0)
            self.assertAlmostEqual(pdf[0].rect.height, 144, places=0)

    def test_o_mesmo_conteudo_nao_converte_de_novo_nem_em_outra_pasta(self) -> None:
        primeira = livro_djvu.pdf_de_djvu(self.djvu(), pasta=self.saida)
        (self.pasta / "movido").mkdir()
        movido = self.djvu(nome="movido/livro.djvu")
        segunda = livro_djvu.pdf_de_djvu(movido, pasta=self.saida)
        self.assertFalse(primeira.reaproveitada)
        self.assertTrue(segunda.reaproveitada)
        self.assertEqual(primeira.pdf, segunda.pdf)

    def test_outro_conteudo_com_o_mesmo_nome_nao_recebe_o_pdf_antigo(self) -> None:
        primeira = livro_djvu.pdf_de_djvu(self.djvu(_pagina_real(300, 600)), pasta=self.saida)
        segunda = livro_djvu.pdf_de_djvu(self.djvu(_pagina_real(400, 800)), pasta=self.saida)
        self.assertNotEqual(primeira.pdf, segunda.pdf)

    def test_arquivo_que_termina_antes_do_que_declara_e_dito_em_portugues(self) -> None:
        cortado = _pagina_real()[:-6]
        with self.assertRaisesRegex(ValueError, "incompleto"):
            livro_djvu.pdf_de_djvu(self.djvu(cortado), pasta=self.saida)
        self.assertEqual(list(self.saida.rglob("*.pdf")), [])
        self.assertEqual(list(self.saida.rglob("*.tmp")), [])

    def test_arquivo_ausente(self) -> None:
        with self.assertRaisesRegex(ValueError, "não existe"):
            livro_djvu.pdf_de_djvu(self.pasta / "nada.djvu", pasta=self.saida)


class TestPaginaAPagina(_ComPasta):
    def converter(self, biblioteca: types.SimpleNamespace, conteudo: bytes = b"") -> livro_djvu.Conversao:
        with mock.patch.object(livro_djvu, "_biblioteca", return_value=biblioteca):
            return livro_djvu.pdf_de_djvu(self.djvu(conteudo), pasta=self.saida)

    def test_uma_pagina_ruim_nao_derruba_o_livro_e_a_numeracao_nao_anda(self) -> None:
        paginas = [_Pagina(), _Pagina(_Erro("JB2: image dimensions too large")), _Pagina()]
        conversao = self.converter(_biblioteca(paginas))
        self.assertEqual(conversao.paginas, 3)
        self.assertEqual(conversao.ilegiveis, (1,))
        with fitz.open(conversao.pdf) as pdf:
            self.assertEqual(pdf.page_count, 3)
            self.assertIn("página 2", pdf[1].get_text().lower())
            self.assertEqual(pdf[0].get_text().strip(), "")
            self.assertEqual(len(pdf[0].get_images()), 1)

    def test_o_panico_do_rust_e_apanhado_e_tenta_a_metade_da_resolucao(self) -> None:
        pagina = _Pagina(PanicException("range end index out of range"), dpi=1200)
        conversao = self.converter(_biblioteca([pagina]))
        self.assertEqual(conversao.ilegiveis, ())
        self.assertEqual(pagina.pedidos, [None, 600])

    def test_erro_de_decodificacao_nao_gasta_uma_segunda_tentativa(self) -> None:
        pagina = _Pagina(_Erro("JB2: image dimensions too large"))
        with self.assertRaisesRegex(ValueError, "nenhuma das 1"):
            self.converter(_biblioteca([pagina]))
        self.assertEqual(pagina.pedidos, [None])

    def test_ctrl_c_nao_e_confundido_com_falha_da_biblioteca(self) -> None:
        with self.assertRaises(KeyboardInterrupt):
            self.converter(_biblioteca([_Pagina(KeyboardInterrupt())]))

    def test_livro_em_que_nada_decodifica_e_recusado_e_nao_vira_pdf_de_avisos(self) -> None:
        with self.assertRaisesRegex(ValueError, "nenhuma das 2"):
            self.converter(_biblioteca([_Pagina(_Erro("x")), _Pagina(_Erro("y"))]))
        self.assertEqual(list(self.saida.rglob("*.pdf")), [])

    def test_dicionario_compartilhado_e_resolvido_pela_pagina_avulsa(self) -> None:
        conteudo = _agrupado(
            _form(b"DJVI", _pedaco(b"Djbz", b"dic")),
            _form(b"DJVU", _pedaco(b"INFO", _info()), _pedaco(b"INCL", "имя".encode("cp1251"))),
        )
        falha = _Pagina(_Erro("JB2: stream requires shared dict but none provided"))
        conversao = self.converter(_biblioteca([falha], avulsa=_Pagina()), conteudo)
        self.assertEqual(conversao.ilegiveis, ())

    def test_pagina_avulsa_de_outra_medida_e_recusada(self) -> None:
        """Se a ordem suposta estivesse errada, a página entregue seria a de outro lugar do livro."""
        conteudo = _agrupado(
            _form(b"DJVI", _pedaco(b"Djbz", b"dic")),
            _form(b"DJVU", _pedaco(b"INFO", _info()), _pedaco(b"INCL", b"d")),
            _form(b"DJVU", _pedaco(b"INFO", _info())),
        )
        falha = _Pagina(_Erro("stream requires shared dict"))
        outra = _Pagina()
        outra.width = 999
        conversao = self.converter(_biblioteca([falha, _Pagina()], avulsa=outra), conteudo)
        self.assertEqual(conversao.ilegiveis, (0,))


class TestDicionarioEmbutido(unittest.TestCase):
    def embutir(self, *componentes: bytes, total: int) -> list[bytes] | None:
        return livro_djvu._paginas_com_dicionario_embutido(_agrupado(*componentes), total)

    def test_cada_nome_novo_recebe_o_proximo_dicionario_e_o_incl_some(self) -> None:
        avulsas = self.embutir(
            _form(b"DJVI", _pedaco(b"Djbz", b"um")),
            _form(b"DJVU", _pedaco(b"INFO", _info()), _pedaco(b"INCL", b"a")),
            _form(b"DJVU", _pedaco(b"INFO", _info()), _pedaco(b"INCL", b"a")),
            _form(b"DJVI", _pedaco(b"Djbz", b"dois")),
            _form(b"DJVU", _pedaco(b"INFO", _info()), _pedaco(b"INCL", b"b")),
            total=3,
        )
        assert avulsas is not None
        self.assertEqual(len(avulsas), 3)
        self.assertIn(b"Djbz\0\0\0\x02um", avulsas[0])
        self.assertIn(b"Djbz\0\0\0\x02um", avulsas[1])
        self.assertIn(b"Djbz\0\0\0\x04dois", avulsas[2])
        for avulsa in avulsas:
            self.assertNotIn(b"INCL", avulsa)

    def test_componente_de_anotacoes_conta_na_ordem_mas_nao_entra_na_pagina(self) -> None:
        avulsas = self.embutir(
            _form(b"DJVI", _pedaco(b"ANTz", b"anotacao")),
            _form(b"DJVI", _pedaco(b"Djbz", b"dic")),
            _form(
                b"DJVU",
                _pedaco(b"INFO", _info()),
                _pedaco(b"INCL", b"anno"),
                _pedaco(b"INCL", b"dict"),
            ),
            total=1,
        )
        assert avulsas is not None
        self.assertNotIn(b"anotacao", avulsas[0])
        self.assertIn(b"Djbz\0\0\0\x03dic", avulsas[0])

    def test_pagina_que_usa_um_nome_antes_do_componente_foge_da_ordem(self) -> None:
        self.assertIsNone(
            self.embutir(
                _form(b"DJVU", _pedaco(b"INFO", _info()), _pedaco(b"INCL", b"a")),
                _form(b"DJVI", _pedaco(b"Djbz", b"um")),
                total=1,
            )
        )

    def test_contagem_de_paginas_que_nao_bate_e_recusada(self) -> None:
        self.assertIsNone(self.embutir(_form(b"DJVU", _pedaco(b"INFO", _info())), total=2))

    def test_arquivo_de_uma_pagina_so_nao_e_agrupado(self) -> None:
        self.assertIsNone(livro_djvu._paginas_com_dicionario_embutido(_pagina_real(), 1))

    def test_a_pagina_avulsa_abre_na_biblioteca_real(self) -> None:
        djvu_rs = sys.modules.get("djvu_rs") or __import__("djvu_rs")
        avulsas = self.embutir(_form(b"DJVU", _pedaco(b"INFO", _info(120, 240))), total=1)
        assert avulsas is not None
        pagina = djvu_rs.Document.from_bytes(avulsas[0]).page(0)
        self.assertEqual((pagina.width, pagina.height), (120, 240))


if __name__ == "__main__":
    unittest.main()
