"""Livros em DjVu: a conversão, os três acertos dela, e a abertura pelo caminho de sempre.

`tests/fixtures/djvu/` vem do repositório da `djvu-rs` (os arquivos de teste do djvu.js, sob The
Unlicense): `boy_jb2.djvu` é uma página JB2 de 279 bytes, e `problem_page.djvu` é um DjVu de várias
partes cuja página usa um dicionário compartilhado.
"""

from __future__ import annotations

import os
import struct
import tempfile
from pathlib import Path

import djvu_rs
import fitz
import numpy as np
import pytest

from chess_diagram_ocr import djvu_bzz, djvu_io
from chess_diagram_ocr.batch import find_pdfs
from chess_diagram_ocr.pdf_io import get_pdf_page_count, opened, render_pdf_page
from chess_diagram_ocr.ui.escopo_da_varredura import books_in_folder

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "djvu"
BOY = (FIXTURES / "boy_jb2.djvu").read_bytes()
COM_DICIONARIO = (FIXTURES / "problem_page.djvu").read_bytes()

DPI_DE_LIVRO = 28
"""O `boy_jb2` tem 256 px de altura e declara 300 DPI, 0,85 polegada, que a escala corrigiria. A 28
DPI ele dá 9,1 polegadas: é como o teste declara uma página cujo cabeçalho merece crédito."""


@pytest.fixture
def pasta(monkeypatch: pytest.MonkeyPatch) -> Path:
    """O cache num lugar só do teste, para cada um converter de verdade."""
    with tempfile.TemporaryDirectory() as temporaria:
        base = Path(temporaria)
        monkeypatch.setattr(djvu_io, "DJVU_CONVERTIDOS_DIR", base / "convertidos")
        yield base


def _pedaco(identificador: bytes, conteudo: bytes) -> bytes:
    return identificador + struct.pack(">I", len(conteudo)) + conteudo + (b"\0" if len(conteudo) & 1 else b"")


def _forma(corpo: bytes) -> bytes:
    return b"AT&TFORM" + struct.pack(">I", len(corpo)) + corpo


def _com_texto(texto: str) -> bytes:
    """O `boy_jb2` com camada de texto: uma página, uma linha, uma palavra (pedaço `TXTa`, sem BZZ)."""
    bruto = texto.encode("utf-8")

    def zona(tipo: int, x: int, y: int, largura: int, altura: int, comprimento: int, filhas: int) -> bytes:
        # O número mágico da zona: `x`, `y` e os demais vão com 0x8000 somado, em big-endian.
        campos = [x + 0x8000, y + 0x8000, largura + 0x8000, altura + 0x8000, 0x8000]
        return bytes([tipo]) + struct.pack(">5H", *campos) + comprimento.to_bytes(3, "big") + filhas.to_bytes(3, "big")

    zonas = (
        zona(1, 0, 0, 192, 256, len(bruto), 1)  # página
        + zona(5, 20, 100, 150, 40, len(bruto), 1)  # linha, relativa à página
        + zona(6, 0, 0, 150, 40, len(bruto), 0)  # palavra, relativa à linha
    )
    txta = len(bruto).to_bytes(3, "big") + bruto + bytes([1]) + zonas
    # O último pedaço do arquivo é ímpar e vem sem o byte de alinhamento, que aqui passa a ser preciso.
    corpo = BOY[12:] + (b"\0" if len(BOY[12:]) & 1 else b"")
    return _forma(corpo + _pedaco(b"TXTa", txta))


def _com_dpi(dados: bytes, dpi: int) -> bytes:
    """Troca o DPI do pedaço `INFO`, que é little-endian. A página fica com os mesmos pixels."""
    inicio = dados.index(b"INFO") + 8
    return dados[: inicio + 6] + struct.pack("<H", dpi) + dados[inicio + 8 :]


def _com_incl_em_cp1251(dados: bytes) -> bytes:
    """O defeito dos livros reais: o nome no `INCL` vira cp1251, e o `DIRM` nem muda de tamanho."""
    inicio = dados.index(b"INCL") + 4
    tamanho = struct.unpack(">I", dados[inicio : inicio + 4])[0]
    nome = dados[inicio + 4 : inicio + 4 + tamanho]
    return dados[: inicio + 4] + b"\xc0" + nome[1:] + dados[inicio + 4 + tamanho :]


def _escrever(pasta: Path, nome: str, dados: bytes) -> Path:
    caminho = pasta / nome
    caminho.write_bytes(dados)
    return caminho


# ------------------------------------------------------------- a abertura pelo caminho de sempre


def test_o_djvu_abre_pelo_mesmo_caminho_do_pdf(pasta: Path) -> None:
    livro = _escrever(pasta, "livro.djvu", _com_dpi(BOY, DPI_DE_LIVRO))

    assert get_pdf_page_count(livro) == 1
    pagina = render_pdf_page(livro, 0, dpi=DPI_DE_LIVRO)

    # No DPI do arquivo, a folha tem os pixels dele e a mesma tinta.
    esperado = djvu_rs.Document.from_bytes(BOY).page(0).render().to_numpy()
    assert pagina.shape[:2] == esperado.shape[:2]
    assert ((pagina[:, :, 0] < 128) == (esperado[:, :, 0] < 128)).mean() > 0.99
    assert (pagina[:, :, 0] < 128).any()


def test_a_extensao_vale_em_qualquer_caixa(pasta: Path) -> None:
    """O acervo tem `.Djvu`, e `.djv` é a outra extensão do formato."""
    assert get_pdf_page_count(_escrever(pasta, "a.Djvu", BOY)) == 1
    assert get_pdf_page_count(_escrever(pasta, "b.djv", BOY)) == 1


def test_quem_recebe_continua_com_o_caminho_do_djvu(pasta: Path) -> None:
    """É esse caminho que entra na sessão, nos rótulos e no nome do PGN."""
    livro = _escrever(pasta, "livro.djvu", BOY)
    with opened(livro) as aberto:
        assert aberto.source == livro


def test_pdf_nao_passa_pela_conversao(pasta: Path) -> None:
    assert djvu_io.pdf_legivel(pasta / "nao_existe.pdf") == str(pasta / "nao_existe.pdf")
    assert not (pasta / "convertidos").exists()


# ------------------------------------------------------------------------ o arquivo guardado


def test_a_segunda_abertura_nao_converte_de_novo(pasta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    livro = _escrever(pasta, "livro.djvu", BOY)
    assert not djvu_io.ja_convertido(livro)
    primeiro = djvu_io.pdf_legivel(livro)
    assert djvu_io.ja_convertido(livro)

    def nao_pode(*_args: object) -> None:
        raise AssertionError("converteu de novo")

    monkeypatch.setattr(djvu_io, "_converter", nao_pode)
    assert djvu_io.pdf_legivel(livro) == primeiro


def test_trocar_o_arquivo_converte_de_novo(pasta: Path) -> None:
    livro = _escrever(pasta, "livro.djvu", BOY)
    primeiro = djvu_io.pdf_legivel(livro)

    livro.write_bytes(_com_texto("novo"))
    os.utime(livro, (1_000_000_000, 1_000_000_000))

    assert djvu_io.pdf_legivel(livro) != primeiro
    with fitz.open(djvu_io.pdf_legivel(livro)) as pdf:
        assert "novo" in pdf[0].get_text()


def test_nome_cirilico_nao_atrapalha_o_cache(pasta: Path) -> None:
    livro = _escrever(pasta, "Портиш, Шаркози - 600 окончаний,1979.djvu", BOY)
    guardado = Path(djvu_io.pdf_legivel(livro))
    assert guardado.name.isascii()
    assert get_pdf_page_count(livro) == 1


def test_converter_um_livro_nao_toca_nele(pasta: Path) -> None:
    livro = _escrever(pasta, "livro.djvu", BOY)
    djvu_io.pdf_legivel(livro)
    assert livro.read_bytes() == BOY


# --------------------------------------------------------- o que a exportação erraria sozinha


def test_cirilico_chega_inteiro_a_camada_de_texto(pasta: Path) -> None:
    """A exportação da `djvu-rs` escreve `???????` aqui, e o programa confiaria nisso."""
    livro = _escrever(pasta, "livro.djvu", _com_texto("Возводя"))

    assert djvu_rs.Document.from_bytes(_com_texto("Возводя")).page(0).text().strip() == "Возводя"
    with fitz.open(djvu_io.pdf_legivel(livro)) as pdf:
        assert pdf[0].get_text().strip() == "Возводя"
        assert "?" not in pdf[0].get_text()
        assert pdf[0].search_for("Возводя")


def test_latim_com_acento_chega_inteiro_a_camada_de_texto(pasta: Path) -> None:
    livro = _escrever(pasta, "livro.djvu", _com_texto("Eröffnung"))
    with fitz.open(djvu_io.pdf_legivel(livro)) as pdf:
        assert pdf[0].get_text().strip() == "Eröffnung"


def test_a_palavra_fica_onde_o_djvu_diz(pasta: Path) -> None:
    dados = _com_dpi(_com_texto("Rook"), DPI_DE_LIVRO)
    linha = djvu_rs.Document.from_bytes(dados).page(0).text_layer()["zones"][0]["children"][0]["rect"]

    with fitz.open(djvu_io.pdf_legivel(_escrever(pasta, "livro.djvu", dados))) as pdf:
        x0, y0, _x1, y1, _texto, *_resto = pdf[0].get_text("words")[0]

    escala = 72 / DPI_DE_LIVRO
    assert x0 == pytest.approx(linha["x"] * escala, abs=0.5)
    # A caixa no PDF é a da fonte, e passa um pouco da linha. O meio dela é que fica dentro.
    assert linha["y"] * escala <= (y0 + y1) / 2 <= (linha["y"] + linha["height"]) * escala


def test_a_camada_e_invisivel(pasta: Path) -> None:
    """A folha com texto é igual à sem texto, e o texto não pinta um pixel."""
    sem = render_pdf_page(_escrever(pasta, "sem.djvu", BOY), 0, dpi=150)
    com = render_pdf_page(_escrever(pasta, "com.djvu", _com_texto("Возводя")), 0, dpi=150)
    assert np.array_equal(sem, com)


def test_dpi_plausivel_fica_como_o_arquivo_declara(pasta: Path) -> None:
    livro = _escrever(pasta, "livro.djvu", _com_dpi(BOY, DPI_DE_LIVRO))
    with fitz.open(djvu_io.pdf_legivel(livro)) as pdf:
        assert pdf[0].rect.height == pytest.approx(256 * 72 / DPI_DE_LIVRO, abs=0.5)


def test_pagina_sem_camada_fica_sem_texto(pasta: Path) -> None:
    with fitz.open(djvu_io.pdf_legivel(_escrever(pasta, "livro.djvu", BOY))) as pdf:
        assert pdf[0].get_text().strip() == ""


@pytest.mark.parametrize(
    ("altura_pt", "esperado"),
    [
        (648.0, 1.0),  # 9 polegadas: um livro comum
        (6.0 * 72, 1.0),  # as duas pontas da faixa ainda valem
        (13.0 * 72, 1.0),
        (2259.0, 648.0 / 2259.0),  # 1.413 x 2.259 px "a 72 DPI": 31 polegadas
        (258.96, 648.0 / 258.96),  # 2.158 px "a 600 DPI": 3,6 polegadas
    ],
)
def test_fator_de_escala(altura_pt: float, esperado: float) -> None:
    assert djvu_io.fator_de_escala(altura_pt) == pytest.approx(esperado)


def test_dpi_absurdo_vira_pagina_de_livro_com_os_mesmos_pixels(pasta: Path) -> None:
    """Os 300 DPI originais do `boy_jb2` dão 0,85 polegada: a folha passa a ter 9."""
    livro = _escrever(pasta, "livro.djvu", _com_texto("Rook"))

    with fitz.open(djvu_io.pdf_legivel(livro)) as pdf:
        pagina = pdf[0]
        assert pagina.rect.height == pytest.approx(648.0, abs=0.01)
        palavra = pagina.get_text("words")[0]
        assert palavra[4] == "Rook"
        # A escala vale também para a camada: a palavra começa no x da página, numa folha de 648 pt.
        assert palavra[0] == pytest.approx(20 * 648.0 / 256, abs=1.0)

    # A tinta acompanha a folha: reduzida ao tamanho original, é a mesma página.
    folha = render_pdf_page(livro, 0, dpi=72 * 256 / 648)
    esperado = djvu_rs.Document.from_bytes(BOY).page(0).render().to_numpy()
    assert folha.shape[:2] == esperado.shape[:2]
    igual = (folha[:, :, 0] < 128) == (esperado[:, :, 0] < 128)
    assert igual.mean() > 0.99


# ------------------------------------------------------------------- o INCL que não é UTF-8


def test_incl_em_cp1251_reproduz_a_falha_da_biblioteca() -> None:
    """A condição que justifica o reparo. Se este teste quebrar, a biblioteca corrigiu o defeito."""
    with pytest.raises(djvu_rs.DecodeError, match="shared dict"):
        djvu_rs.Document.from_bytes(_com_incl_em_cp1251(COM_DICIONARIO)).page(0).render()


def test_incl_em_cp1251_e_reparado_sem_mudar_um_pixel(pasta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """O `DIRM` está em BZZ e não dá para regravá-lo daqui, então é só ele que é ajustado à mão."""
    verdadeiro = djvu_io._nomes_do_dirm(COM_DICIONARIO)
    pagina = next(p for forma, p in djvu_io._componentes(COM_DICIONARIO) if forma == b"DJVU")
    citado = next(conteudo for identificador, conteudo in pagina if identificador == b"INCL")
    ajustado = [b"\xc0" + nome[1:] if nome == citado else nome for nome in verdadeiro]
    monkeypatch.setattr(djvu_io, "_nomes_do_dirm", lambda _d: ajustado)
    livro = _escrever(pasta, "livro.djvu", _com_incl_em_cp1251(COM_DICIONARIO))

    folha = render_pdf_page(livro, 0, dpi=100)
    original = render_pdf_page(_escrever(pasta, "original.djvu", COM_DICIONARIO), 0, dpi=100)

    assert np.array_equal(folha, original)
    assert (folha[:, :, 0] < 128).mean() > 0.01  # e não é uma folha em branco igual a outra


def test_incl_utf8_nao_passa_pelo_reparo(pasta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def nao_pode(_dados: bytes) -> list[bytes]:
        raise AssertionError("foi pelo caminho do reparo")

    monkeypatch.setattr(djvu_io, "paginas_soltas", nao_pode)
    assert get_pdf_page_count(_escrever(pasta, "livro.djvu", COM_DICIONARIO)) == 1


def _djvm(*componentes: bytes) -> bytes:
    """Um DJVM só com o que `paginas_soltas` lê: o `DIRM` com as posições, e sem os metadados."""
    cabeca = 16 + 8 + 3 + 4 * len(componentes) + (1 if (3 + 4 * len(componentes)) & 1 else 0)
    posicoes, posicao = [], cabeca
    for componente in componentes:
        posicoes.append(posicao)
        posicao += len(componente) + (len(componente) & 1)
    dirm = bytes([0x81]) + struct.pack(">H", len(componentes)) + struct.pack(f">{len(posicoes)}I", *posicoes)
    corpo = b"DJVM" + _pedaco(b"DIRM", dirm)
    for componente in componentes:
        corpo += componente + (b"\0" if len(componente) & 1 else b"")
    return _forma(corpo)


def _dicionario(conteudo: bytes) -> bytes:
    return _pedaco(b"FORM", b"DJVI" + _pedaco(b"Djbz", conteudo))


def _pagina(nome: bytes) -> bytes:
    return _pedaco(b"FORM", b"DJVU" + _pedaco(b"INFO", b"\0" * 10) + _pedaco(b"INCL", nome) + _pedaco(b"Sjbz", b"x"))


def test_cada_pagina_recebe_o_dicionario_pelo_nome_e_nao_pela_ordem(monkeypatch: pytest.MonkeyPatch) -> None:
    """A forma do `Pachman_1957_.djvu`: os dicionários fora de ordem, e a contagem batendo.

    Com o casamento pela ordem, este livro saía com letras trocadas e sem erro nenhum.
    """
    dados = _djvm(
        _dicionario(b"da pagina 2"), _dicionario(b"da pagina 1"), _pagina(b"\xc0um"), _pagina(b"\xc0dois"),
    )
    monkeypatch.setattr(djvu_io, "_nomes_do_dirm", lambda _d: [b"\xc0dois", b"\xc0um", b"p1", b"p2"])

    soltas = djvu_io.paginas_soltas(dados)

    assert len(soltas) == 2
    assert b"da pagina 1" in soltas[0] and b"da pagina 2" not in soltas[0]
    assert b"da pagina 2" in soltas[1] and b"da pagina 1" not in soltas[1]
    assert all(b"INCL" not in solta for solta in soltas)
    assert all(solta.startswith(b"AT&TFORM") and solta[12:16] == b"DJVU" for solta in soltas)


def test_incl_que_nao_e_dicionario_some_da_pagina(monkeypatch: pytest.MonkeyPatch) -> None:
    """É como vêm as anotações compartilhadas: dez livros do acervo citam uma."""
    anotacao = _pedaco(b"FORM", b"DJVI" + _pedaco(b"ANTz", b"qualquer"))
    monkeypatch.setattr(djvu_io, "_nomes_do_dirm", lambda _d: [b"anot.iff", b"p1"])

    soltas = djvu_io.paginas_soltas(_djvm(anotacao, _pagina(b"anot.iff")))

    assert len(soltas) == 1
    assert b"INCL" not in soltas[0] and b"Djbz" not in soltas[0]


def test_dicionario_que_herda_e_recusado(monkeypatch: pytest.MonkeyPatch) -> None:
    herdeiro = _pedaco(b"FORM", b"DJVI" + _pedaco(b"INCL", b"\xc0z") + _pedaco(b"Djbz", b"d"))
    monkeypatch.setattr(djvu_io, "_nomes_do_dirm", lambda _d: [b"\xc0a", b"p1"])
    with pytest.raises(ValueError, match="herda"):
        djvu_io.paginas_soltas(_djvm(herdeiro, _pagina(b"\xc0a")))


def test_o_nome_lido_do_dirm_e_o_que_a_pagina_cita() -> None:
    """O BZZ de verdade: o arquivo real traz no `DIRM` o nome que o `INCL` da página cita."""
    nomes = djvu_io._nomes_do_dirm(COM_DICIONARIO)
    pagina = next(p for forma, p in djvu_io._componentes(COM_DICIONARIO) if forma == b"DJVU")
    citado = next(conteudo for identificador, conteudo in pagina if identificador == b"INCL")
    assert len(nomes) == 2
    assert citado in nomes


def test_bzz_recusa_fluxo_que_nao_e_bzz() -> None:
    with pytest.raises(ValueError):
        djvu_bzz.decodificar(b"x")
    with pytest.raises(ValueError):
        djvu_bzz.decodificar(bytes(range(40)))


# ----------------------------------------------------------------------- a página que não decodifica


def _pagina_ruim() -> bytes:
    """A página de `problem_page` sem o `INCL`: o JB2 dela pede um dicionário que ninguém dá.

    É uma recusa de verdade da biblioteca. Bytes aleatórios no JB2 não serviriam: o decodificador
    aritmético aceita qualquer coisa, e devolve uma imagem de lixo sem erro.
    """
    pagina = next(p for forma, p in djvu_io._componentes(COM_DICIONARIO) if forma == b"DJVU")
    return _pedaco(b"FORM", b"DJVU" + b"".join(_pedaco(i, c) for i, c in pagina if i != b"INCL"))


def _livro_com_pagina_ruim() -> bytes:
    """Duas páginas boas e uma ruim. Sem `DIRM` legível, a biblioteca lê pelas posições."""
    return _djvm(BOY[4:], _pagina_ruim(), BOY[4:])


def test_a_premissa_a_exportacao_perde_a_pagina_ruim_sem_avisar() -> None:
    """Se este teste quebrar, a biblioteca passou a reclamar, e `_nao_renderiza` pode ser revisto."""
    documento = djvu_rs.Document.from_bytes(_livro_com_pagina_ruim())
    assert documento.page_count() == 3
    with pytest.raises(djvu_rs.DecodeError):
        documento.page(1).render(dpi=25)
    with fitz.open("pdf", documento.to_pdf(**djvu_io._EXPORTACAO)) as pdf:
        assert not pdf[1].get_images()


class _ExportacaoQueRecusa:
    """O outro jeito de falhar: em três livros reais, a página ruim faz o `to_pdf` levantar.

    O erro real ("image dimensions too large") vem de um JB2 que não dá para escrever à mão, então
    aqui o documento só recusa a exportação de quem tem página ruim.
    """

    def __init__(self, documento: djvu_rs.Document) -> None:
        self._documento = documento

    def page_count(self) -> int:
        return self._documento.page_count()

    def page(self, indice: int) -> djvu_rs.Page:
        return self._documento.page(indice)

    def to_pdf(self, **opcoes: object) -> bytes:
        for indice in range(self.page_count()):
            try:
                self.page(indice).render(dpi=25)
            except djvu_rs.DecodeError as exc:
                raise djvu_rs.ExportError(f"PDF export failed: {exc}") from exc
        return self._documento.to_pdf(**opcoes)


def test_exportacao_que_levanta_vai_pagina_por_pagina(pasta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    verdadeiro = djvu_rs.Document

    class Documento(_ExportacaoQueRecusa):
        @staticmethod
        def from_bytes(dados: bytes) -> _ExportacaoQueRecusa:
            return _ExportacaoQueRecusa(verdadeiro.from_bytes(dados))

    monkeypatch.setattr(djvu_rs, "Document", Documento)
    livro = _escrever(pasta, "livro.djvu", _livro_com_pagina_ruim())

    assert get_pdf_page_count(livro) == 3
    with fitz.open(djvu_io.pdf_legivel(livro)) as pdf:
        assert djvu_io.AVISO_DE_PAGINA_ILEGIVEL in pdf[1].get_text()
        assert pdf[0].get_images() and pdf[2].get_images()


def test_uma_pagina_ruim_nao_derruba_o_livro(pasta: Path) -> None:
    livro = _escrever(pasta, "livro.djvu", _livro_com_pagina_ruim())

    assert get_pdf_page_count(livro) == 3
    boa = render_pdf_page(livro, 0, dpi=40)
    assert (boa[:, :, 0] < 128).any()
    assert np.array_equal(boa, render_pdf_page(livro, 2, dpi=40))

    with fitz.open(djvu_io.pdf_legivel(livro)) as pdf:
        assert djvu_io.AVISO_DE_PAGINA_ILEGIVEL in pdf[1].get_text()
        assert not pdf[1].get_images()
        assert djvu_io.AVISO_DE_PAGINA_ILEGIVEL not in pdf[0].get_text()
        # A página em branco tem o tamanho da que deveria estar ali: 5.050 px a 600 DPI.
        assert pdf[1].rect.height == pytest.approx(5050 * 72 / 600, abs=0.5)


def test_o_aviso_da_pagina_ruim_vai_para_o_log(pasta: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING", logger="chess_diagram_ocr.djvu_io"):
        djvu_io.pdf_legivel(_escrever(pasta, "livro.djvu", _livro_com_pagina_ruim()))
    assert "livro.djvu" in caplog.text and "[2]" in caplog.text


def test_livro_sem_nenhuma_pagina_legivel_e_recusado(pasta: Path) -> None:
    with pytest.raises(ValueError, match="nenhuma das páginas"):
        get_pdf_page_count(_escrever(pasta, "livro.djvu", _djvm(_pagina_ruim(), _pagina_ruim())))
    assert not (pasta / "convertidos").exists()


def test_folha_em_branco_de_verdade_nao_recebe_aviso(pasta: Path) -> None:
    """A página só com `INFO` também sai sem imagem, e essa a biblioteca renderiza."""
    branca = _pedaco(b"FORM", b"DJVU" + next(BOY[i:i + 18] for i in [BOY.index(b"INFO")]))
    with fitz.open(djvu_io.pdf_legivel(_escrever(pasta, "livro.djvu", _djvm(BOY[4:], branca)))) as pdf:
        assert pdf.page_count == 2
        assert djvu_io.AVISO_DE_PAGINA_ILEGIVEL not in pdf[1].get_text()


def test_o_indice_que_viria_com_interrogacoes_nao_entra(pasta: Path) -> None:
    with fitz.open(djvu_io.pdf_legivel(_escrever(pasta, "livro.djvu", BOY))) as pdf:
        assert pdf.get_toc() == []


# ----------------------------------------------------------------------- o que não dá para ler


def test_arquivo_truncado_vira_frase_e_nao_derruba(pasta: Path) -> None:
    livro = _escrever(pasta, "cortado.djvu", COM_DICIONARIO[: len(COM_DICIONARIO) // 2])
    with pytest.raises(ValueError, match="cortado.djvu.*incompleto ou danificado"):
        get_pdf_page_count(livro)
    assert not (pasta / "convertidos").exists()


def test_arquivo_que_nao_e_djvu_vira_frase(pasta: Path) -> None:
    with pytest.raises(ValueError, match="incompleto ou danificado"):
        get_pdf_page_count(_escrever(pasta, "falso.djvu", b"isto nao e um djvu"))


# ------------------------------------------------------------------------------- as pastas


def test_as_varreduras_de_pasta_acham_djvu(pasta: Path) -> None:
    acervo = pasta / "acervo"
    (acervo / "sub").mkdir(parents=True)
    for nome in ("a.pdf", "b.djvu", "c.Djvu", "d.djv", "e.txt", "sub/f.djvu"):
        (acervo / nome).write_bytes(b"x")

    assert [p.name for p in books_in_folder(acervo)] == ["a.pdf", "b.djvu", "c.Djvu", "d.djv"]
    assert sorted(p.name for p in find_pdfs(acervo)) == ["a.pdf", "b.djvu", "c.Djvu", "d.djv", "f.djvu"]
    assert find_pdfs(acervo / "b.djvu") == [acervo / "b.djvu"]
