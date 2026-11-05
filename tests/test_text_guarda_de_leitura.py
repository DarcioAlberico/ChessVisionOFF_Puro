"""A folha que saiu vazia avisa: a densidade, os avisos na página, a reserva e a prosa da camada (S-710, S-715, S-716)."""

from __future__ import annotations

import unittest
from collections.abc import Sequence
from typing import Any
from unittest import mock

import cv2
import numpy as np
from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr.text import camada_prosa, documento, guarda_de_leitura, leitor, pagina, rico, tesseract
from chess_diagram_ocr.text.leitor_de_linha import Leitura


def folha_com_texto(linhas: int = 30, *, faixa_escura: bool = False) -> np.ndarray:
    """Uma folha desenhada, sem livro nenhum: linhas de texto, e a faixa escura na borda que perde a página."""
    imagem = np.full((1400, 1000, 3), 255, dtype=np.uint8)
    for n in range(linhas):
        cv2.putText(
            imagem, "the white knight wins a pawn", (120, 80 + 42 * n), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2, cv2.LINE_AA
        )
    if faixa_escura:
        imagem[:, :80] = 30
    return imagem


class DensidadeTests(unittest.TestCase):
    def test_folha_com_texto_lida_passa(self) -> None:
        medida = guarda_de_leitura.medir(folha_com_texto(), [], lidos=700, linhas_lidas=30)
        self.assertTrue(medida.tem_texto)
        self.assertFalse(medida.nao_lida)
        self.assertFalse(medida.parcial)
        self.assertGreater(medida.densidade, 0.7)

    def test_folha_com_texto_nao_lida_acusa(self) -> None:
        medida = guarda_de_leitura.medir(folha_com_texto(), [], lidos=1, linhas_lidas=1)
        self.assertTrue(medida.nao_lida)
        self.assertLess(medida.densidade, 0.01)

    def test_a_faixa_escura_da_borda_nao_esconde_a_perda(self) -> None:
        """A caixa degenerada cobre a folha inteira: é por isso que a guarda não olha cobertura."""
        medida = guarda_de_leitura.medir(folha_com_texto(faixa_escura=True), [], lidos=1, linhas_lidas=1)
        self.assertTrue(medida.nao_lida)

    def test_folha_em_branco_nao_avisa(self) -> None:
        medida = guarda_de_leitura.medir(np.full((1400, 1000, 3), 255, dtype=np.uint8), [], lidos=0, linhas_lidas=0)
        self.assertFalse(medida.tem_texto)
        self.assertFalse(medida.nao_lida)
        self.assertFalse(medida.parcial)

    def test_o_que_esta_no_diagrama_nao_conta(self) -> None:
        """Uma folha só de diagrama, sem nada lido, é capa e não perda."""
        imagem = folha_com_texto(linhas=30)
        medida = guarda_de_leitura.medir(imagem, [(0, 0, 1000, 1400)], lidos=0, linhas_lidas=0)
        self.assertFalse(medida.tem_texto)

    def test_arte_alta_nao_vira_letra(self) -> None:
        imagem = np.full((1400, 1000, 3), 255, dtype=np.uint8)
        for n in range(60):
            imagem[100:400, 20 + 16 * n : 26 + 16 * n] = 0  # componentes altos demais para serem letra
        self.assertFalse(guarda_de_leitura.medir(imagem, [], lidos=0, linhas_lidas=0).tem_texto)

    def test_a_altura_da_letra_escala_com_o_dpi(self) -> None:
        pequena = cv2.resize(folha_com_texto(), None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        a_110 = guarda_de_leitura.medir(pequena, [], lidos=700, linhas_lidas=30, dpi=110)
        self.assertTrue(a_110.tem_texto)

    def test_perda_parcial_tem_sinal_proprio_e_nunca_junto_da_total(self) -> None:
        por_linhas = guarda_de_leitura.Medida(1000, 900, linhas_estimadas=40, linhas_lidas=10)
        self.assertTrue(por_linhas.parcial)
        por_camada = guarda_de_leitura.Medida(1000, 900, 10, 10, caracteres_da_camada=2000)
        self.assertTrue(por_camada.parcial)
        total = guarda_de_leitura.Medida(1000, 1, 40, 1, caracteres_da_camada=2000)
        self.assertTrue(total.nao_lida)
        self.assertFalse(total.parcial)


class AvisosNaPaginaTests(unittest.TestCase):
    def _pagina(self) -> pagina.PaginaLida:
        return pagina.PaginaLida(
            pagina=3,
            avisos=(pagina.Aviso(pagina.FOLHA_NAO_LIDA, "Esta folha não foi lida.", 0.001),),
        )

    def test_ida_e_volta(self) -> None:
        original = self._pagina()
        self.assertEqual(pagina.PaginaLida.de_json(original.para_json()), original)

    def test_o_formato_um_ainda_abre(self) -> None:
        dados = self._pagina().para_json()
        antigo = {k: v for k, v in dados.items() if k != "avisos"} | {"esquema": 1}
        self.assertEqual(pagina.PaginaLida.de_json(antigo).avisos, ())

    def test_aviso_de_versao_mais_nova_nao_derruba_o_arquivo(self) -> None:
        dados = self._pagina().para_json() | {"avisos": [{"codigo": "novo", "mensagem": "m"}]}
        self.assertEqual(pagina.PaginaLida.de_json(dados).avisos[0].codigo, "novo")

    def test_aviso_sem_codigo_e_arquivo_corrompido(self) -> None:
        with self.assertRaises(pagina.PaginaInvalida):
            pagina.PaginaLida.de_json(self._pagina().para_json() | {"avisos": [{"mensagem": "m"}]})

    def test_o_aviso_atravessa_o_cvtxt(self) -> None:
        """É o que faz a folha reaberta do caderno continuar dizendo que não foi lida."""
        from chess_diagram_ocr.text import arquivo

        doc = rico.de_pagina(self._pagina())
        self.assertEqual(arquivo.de_json(arquivo.para_json(doc)).origem.avisos, self._pagina().avisos)  # type: ignore[union-attr]

    def test_a_marca_em_memoria_nao_vai_ao_arquivo(self) -> None:
        linha = pagina.LinhaLida(texto="um dois", bbox=(0, 0, 1, 1), revisar_em=((0, 2),))
        self.assertNotIn("revisar_em", linha.para_json())


class MarcaNoDocumentoTests(unittest.TestCase):
    def _pagina(self, *, marca: bool) -> pagina.PaginaLida:
        linha = pagina.LinhaLida(
            texto="uma palavra errada aqui", bbox=(0, 0, 9, 9), confianca=0.1, procedencia="glifo", revisar_em=((4, 11),)
        )
        bloco = pagina.BlocoDeTexto.de_linhas([linha])
        return pagina.PaginaLida(colunas=(pagina.Coluna(indice=0, blocos=(bloco,)),), marca_por_palavra=marca)

    def test_a_marca_pinta_so_a_palavra(self) -> None:
        doc = rico.de_pagina(self._pagina(marca=True))
        self.assertEqual(doc.para_texto(), "uma palavra errada aqui")
        self.assertEqual(
            [(c.texto, c.faixa) for c in doc.corridas],
            [("uma ", documento.TRANQUILO), ("palavra", documento.REVISAR), (" errada aqui", documento.TRANQUILO)],
        )

    def test_desligada_vale_a_faixa_de_hoje(self) -> None:
        linha = pagina.LinhaLida(texto="uma palavra", bbox=(0, 0, 9, 9), confianca=0.1, procedencia="glifo")
        bloco = pagina.BlocoDeTexto.de_linhas([linha])
        pag = pagina.PaginaLida(colunas=(pagina.Coluna(indice=0, blocos=(bloco,)),))
        self.assertEqual([c.faixa for c in rico.de_pagina(pag).corridas], [documento.REVISAR])

    def test_a_contagem_segue_a_marca(self) -> None:
        self.assertEqual(documento.contagem_por_faixa(self._pagina(marca=True))[documento.REVISAR], 1)

    def test_os_intervalos_a_revisar_acham_a_palavra(self) -> None:
        doc = rico.de_pagina(self._pagina(marca=True))
        ((inicio, fim),) = rico.intervalos_a_revisar(doc)
        self.assertEqual(doc.para_texto()[inicio:fim], "palavra")


class CaraterSuspeitoTests(unittest.TestCase):
    """A ligadura que perde letra, e a que não perde: os dois medidos no *Chess Evolution 2013*."""

    @staticmethod
    def _trecho(texto: str, larguras: Sequence[float], fonte: str = "MyriadPro-Regular") -> dict[str, Any]:
        chars, x = [], 0.0
        for letra, largura in zip(texto, larguras, strict=True):
            chars.append((ord(letra), 0, (x, 10.0), (x, 0.0, x + largura * 10, 12.0)))
            x += largura * 10
        return {"font": fonte, "size": 10.0, "chars": tuple(chars)}

    def _pagina(self, *trechos: dict[str, Any]) -> Any:
        palavras = []
        for trecho in trechos:
            texto = "".join(chr(c[0]) for c in trecho["chars"])
            x0, y0, _x1, _y1 = trecho["chars"][0][3]
            palavras.append((x0, y0, trecho["chars"][-1][3][2], 12.0, texto, 0, 0, 0))
        falsa = mock.Mock()
        falsa.get_texttrace.return_value = list(trechos)
        falsa.get_text.return_value = palavras
        return falsa

    def test_a_letra_larga_sem_par_e_ligadura_que_perdeu_letra(self) -> None:
        normais = self._trecho("ffff", [0.3, 0.3, 0.3, 0.3])
        perdida = self._trecho("afer", [0.48, 0.52, 0.5, 0.33])
        palavras = camada_prosa.palavras_da_folha(self._pagina(normais, perdida))
        self.assertTrue(next(p for p in palavras if p.texto == "afer").bloqueada)

    def test_a_ligadura_com_par_de_largura_zero_nao_e_suspeita(self) -> None:
        """`first`: o `f` mede o mesmo 0,523, seguido de um `i` de largura zero. As duas letras estão lá."""
        normais = self._trecho("ffff", [0.3, 0.3, 0.3, 0.3])
        certa = self._trecho("first", [0.52, 0.0, 0.33, 0.4, 0.33])
        palavras = camada_prosa.palavras_da_folha(self._pagina(normais, certa))
        self.assertFalse(next(p for p in palavras if p.texto == "first").bloqueada)

    def test_codigo_em_fonte_de_figurina_nao_e_letra(self) -> None:
        palavras = camada_prosa.palavras_da_folha(self._pagina(self._trecho("Ã", [0.5], fonte="FigurineSymbol-T1")))
        self.assertTrue(palavras[0].bloqueada)

    def test_a_forma_de_apresentacao_vira_letras(self) -> None:
        falsa = mock.Mock()
        falsa.get_texttrace.return_value = []
        falsa.get_text.return_value = [(0, 0, 9, 9, "ﬁrst", 0, 0, 0)]
        self.assertEqual(camada_prosa.palavras_da_folha(falsa)[0].texto, "first")


class PorLinhaTests(unittest.TestCase):
    def test_a_palavra_cai_na_linha_que_contem_o_centro_em_ordem_de_x(self) -> None:
        caixas = [(0.0, 0.0, 100.0, 10.0), (0.0, 20.0, 100.0, 30.0)]
        palavras = [
            camada_prosa.PalavraDaCamada("dois", (50.0, 1.0, 60.0, 9.0)),
            camada_prosa.PalavraDaCamada("um", (10.0, 1.0, 20.0, 9.0)),
            camada_prosa.PalavraDaCamada("tres", (10.0, 21.0, 20.0, 29.0)),
            camada_prosa.PalavraDaCamada("fora", (10.0, 50.0, 20.0, 59.0)),
        ]
        linhas, fora = camada_prosa.por_linha(caixas, palavras)
        self.assertEqual([[p.texto for p in li] for li in linhas], [["um", "dois"], ["tres"]])
        self.assertEqual([p.texto for p in fora], ["fora"])

    def test_a_palavra_entra_numa_linha_so(self) -> None:
        caixas = [(0.0, 0.0, 100.0, 10.0), (0.0, 10.5, 100.0, 20.5)]
        linhas, _ = camada_prosa.por_linha(caixas, [camada_prosa.PalavraDaCamada("x", (10.0, 8.0, 20.0, 12.0))])
        self.assertEqual(sum(len(li) for li in linhas), 1)


class _LeitorFalso:
    def __init__(self, folha: Sequence[tesseract.Palavra] = (), falha: str = "", linhas: Sequence[str | None] | None = None) -> None:
        self.folha, self.falha, self.linhas, self.pediu_folha = list(folha), falha, linhas, False

    def ler_linhas(self, recortes: Sequence[np.ndarray], *, lingua: str, dpi: int) -> Leitura:
        if self.linhas is None:
            return Leitura((None,) * len(recortes), self.falha)
        return Leitura(
            tuple(None if t is None else tesseract.LinhaDoTesseract(t, (0.99,) * len(t.split())) for t in self.linhas),
            self.falha,
        )

    def ler_folha(self, cinza: np.ndarray, *, lingua: str, dpi: int) -> tuple[list[tesseract.Palavra], str]:
        self.pediu_folha = True
        return (self.folha, self.falha)


class LeituraDoLivroTests(unittest.TestCase):
    """`ler_pagina` num PDF desenhado aqui, com o glifo trocado: a fiação inteira, sem modelo e sem livro."""

    def setUp(self) -> None:
        import fitz

        doc = fitz.open()
        pag = doc.new_page(width=450, height=650)
        for n in range(12):
            pag.insert_text((60, 60 + 18 * n), "the white knight wins a pawn", fontname="helv", fontsize=11)
        self.caminho = pasta_temporaria(self) / "livro.pdf"
        doc.save(self.caminho)
        doc.close()

    def _crua(self, texto: str, y: int) -> Any:
        from chess_diagram_ocr.text import boxes

        escala = 220 / 72
        caixa = boxes.Caixa(int(58 * escala), int(y * escala), int(300 * escala), int((y + 13) * escala))
        return leitor._Cru(texto=texto, caixa=caixa, confianca=0.9, procedencia="glifo")  # noqa: SLF001

    def _ler(self, motor: str, cruas: Sequence[Any], **opcoes: Any) -> pagina.PaginaLida:
        with (
            mock.patch.object(leitor, "linhas_do_glifo", return_value=(list(cruas), [])),
            mock.patch("chess_diagram_ocr.detection.hybrid.detect_diagrams_in_pdf_page", return_value=[]),
        ):
            return leitor.ler_pagina(self.caminho, 0, motor=motor, reconhecedor=object(), **opcoes)  # type: ignore[arg-type]

    def _boas(self, texto: str = "tne wbite knlght wins a pawn") -> list[Any]:
        return [self._crua(texto, 50 + 18 * n) for n in range(12)]

    def test_o_glifo_que_leu_a_folha_nao_avisa(self) -> None:
        self.assertEqual(self._ler("glifo", self._boas(), reserva=False).avisos, ())

    def test_folha_perdida_avisa_e_o_texto_nao_muda_sem_reserva(self) -> None:
        lida = self._ler("glifo", [self._crua("h", 50)], reserva=False)
        self.assertEqual([a.codigo for a in lida.avisos], [pagina.FOLHA_NAO_LIDA])
        self.assertEqual(lida.texto(com_marcas=False), "h")

    def test_a_reserva_rele_a_folha_e_diz_que_releu(self) -> None:
        palavras = [
            tesseract.Palavra("the", 0.9, (100, 100 + 40 * n, 160, 130 + 40 * n), linha=n) for n in range(5)
        ]
        falso = _LeitorFalso(folha=palavras)
        lida = self._ler("glifo", [self._crua("h", 50)], leitor_de_linha=falso, reserva=True)
        self.assertTrue(falso.pediu_folha)
        self.assertEqual([a.codigo for a in lida.avisos], [pagina.FOLHA_NAO_LIDA, pagina.LEIAUTE_DE_RESERVA])
        self.assertEqual(lida.texto(com_marcas=False).split(), ["the"] * 5)

    def test_a_reserva_parte_a_linha_na_calha_e_nao_intercala_as_colunas(self) -> None:
        """No *Kmoch* 106 o Tesseract escreve as duas colunas na mesma linha, por cima do fio."""
        palavras = []
        for n in range(6):
            y = 100 + 40 * n
            palavras.append(tesseract.Palavra(f"esq{n}", 0.9, (100, y, 300, y + 25), linha=n))
            palavras.append(tesseract.Palavra(f"dir{n}", 0.9, (700, y, 900, y + 25), linha=n))
        lida = self._ler("glifo", [self._crua("h", 50)], leitor_de_linha=_LeitorFalso(folha=palavras), reserva=True)
        texto = lida.texto(com_marcas=False).split()
        self.assertEqual(len(texto), 12)
        self.assertNotIn("esq0 dir0", lida.texto(com_marcas=False))
        self.assertLess(max(i for i, t in enumerate(texto) if t.startswith("esq")), min(i for i, t in enumerate(texto) if t.startswith("dir")))

    def test_o_fio_lido_como_barra_parte_a_linha_e_nao_vai_ao_texto(self) -> None:
        palavras = [
            tesseract.Palavra("esq", 0.9, (100, 100, 300, 125), linha=0),
            tesseract.Palavra("|", 0.9, (310, 100, 316, 125), linha=0),
            tesseract.Palavra("dir", 0.9, (326, 100, 500, 125), linha=0),
        ]
        pedacos = leitor._partida_no_vao(palavras)  # noqa: SLF001
        self.assertEqual([[p.texto for p in pedaco] for pedaco in pedacos], [["esq"], ["dir"]])

    def test_o_espaco_entre_palavras_nao_parte_a_linha(self) -> None:
        palavras = [tesseract.Palavra(t, 0.9, (100 + 80 * n, 100, 170 + 80 * n, 125), linha=0) for n, t in enumerate("abc")]
        self.assertEqual(len(leitor._partida_no_vao(palavras)), 1)  # noqa: SLF001

    def test_sem_tesseract_a_folha_sai_como_o_glifo_leu_com_os_dois_avisos(self) -> None:
        lida = self._ler("glifo", [self._crua("h", 50)], leitor_de_linha=_LeitorFalso(falha="Sem Tesseract."), reserva=True)
        self.assertEqual([a.codigo for a in lida.avisos], [pagina.FOLHA_NAO_LIDA, pagina.LEITOR_INDISPONIVEL])
        self.assertIn("Sem Tesseract.", lida.avisos[1].mensagem)
        self.assertEqual(lida.texto(com_marcas=False), "h")

    def test_folha_legivel_nao_aciona_a_reserva(self) -> None:
        falso = _LeitorFalso()
        self._ler("glifo", self._boas(), leitor_de_linha=falso, reserva=True)
        self.assertFalse(falso.pediu_folha)

    def test_a_camada_na_prosa_troca_a_prosa(self) -> None:
        cruas = [self._crua("tne wbite ♘f3 wins a pawn", 50 + 18 * n) for n in range(12)]
        lida = self._ler("camada_prosa", cruas)
        self.assertEqual(lida.avisos, ())
        self.assertTrue(lida.marca_por_palavra)
        primeira = lida.blocos[0].linhas[0]  # type: ignore[union-attr]
        self.assertIn("the", primeira.texto)
        self.assertNotIn("tne", primeira.texto)

    def test_linha_so_de_prosa_da_camada_e_registro(self) -> None:
        lida = self._ler("camada_prosa", self._boas())
        linha = lida.blocos[0].linhas[0]  # type: ignore[union-attr]
        self.assertEqual(linha.texto, "the white knight wins a pawn")
        self.assertEqual((linha.procedencia, linha.confianca), ("camada", 1.0))

    def test_folha_perdida_na_camada_na_prosa_vem_da_camada_com_aviso(self) -> None:
        lida = self._ler("camada_prosa", [self._crua("h", 50)])
        self.assertEqual([a.codigo for a in lida.avisos], [pagina.CAMADA_NA_FOLHA])
        self.assertIn("the white knight", lida.texto(com_marcas=False))

    def test_a_fusao_le_a_prosa_do_leitor_e_a_notacao_do_glifo(self) -> None:
        falso = _LeitorFalso(linhas=["the white Nf3 wins a pawn"] * 12)
        cruas = [self._crua("tne wbite ♘f3 wins a pawn", 50 + 18 * n) for n in range(12)]
        lida = self._ler("fusao", cruas, leitor_de_linha=falso)
        self.assertEqual(lida.blocos[0].linhas[0].texto, "the white ♘f3 wins a pawn")  # type: ignore[union-attr]
        self.assertTrue(lida.marca_por_palavra)

    def test_a_fusao_sem_leitor_deixa_a_folha_igual_a_do_glifo_e_avisa(self) -> None:
        cruas = self._boas()
        do_glifo = self._ler("glifo", cruas, reserva=False)
        sem = self._ler("fusao", cruas, leitor_de_linha=_LeitorFalso(falha="Sem Tesseract."))
        self.assertEqual(sem.texto(), do_glifo.texto())
        self.assertEqual([a.codigo for a in sem.avisos], [pagina.LEITOR_INDISPONIVEL])
        self.assertFalse(sem.marca_por_palavra)

    def test_a_linha_que_o_leitor_nao_leu_fica_com_o_glifo(self) -> None:
        falso = _LeitorFalso(linhas=[None] + ["the white knight wins a pawn"] * 11)
        lida = self._ler("fusao", self._boas(), leitor_de_linha=falso)
        self.assertEqual(lida.blocos[0].linhas[0].texto, "tne wbite knlght wins a pawn")  # type: ignore[union-attr]

    def test_o_padrao_nao_mudou(self) -> None:
        self.assertEqual(leitor.MOTOR_PADRAO, "glifo")
        self.assertEqual(leitor.motor_escolhido("auto"), "glifo")


if __name__ == "__main__":
    unittest.main()
