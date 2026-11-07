"""A fiação da primeira entrega da prosa, afirmada pelo efeito (S-710, S-715 a S-718, S-720).

**Estes testes nasceram de uma reprovação.** O crítico reverteu 97 consertos, e 33 passaram nas quatro
guardas da entrega: sem `revisar_em` na `LinhaLida`, nenhuma marca chegava à tela, e a suíte ficava verde.
Cada teste daqui existe porque um mutante sobreviveu, e foi conferido revertendo o conserto. O PDF é de
verdade, desenhado no teste; só o que pede modelo ou binário é trocado.
"""

from __future__ import annotations

import subprocess
import unittest
from collections.abc import Sequence
from typing import Any
from unittest import mock

import cv2
import numpy as np
from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr.text import (
    boxes,
    camada_prosa,
    documento,
    fusao,
    guarda_de_leitura,
    leitor,
    pagina,
    rico,
    tesseract,
)
from chess_diagram_ocr.text.leitor_de_linha import Leitura
from chess_diagram_ocr.ui import atalhos

ESCALA = 220 / 72
LINHA = "the white knight wins a pawn"


class _Falso:
    """O Tesseract de mentira. Anota o que recebeu, que é metade do que estes testes afirmam."""

    def __init__(
        self,
        folha: Sequence[tesseract.Palavra] = (),
        falha: str = "",
        linhas: Sequence[str | None] | None = None,
        confianca: float = 0.99,
    ) -> None:
        self.folha, self.falha, self.linhas, self.confianca = list(folha), falha, linhas, confianca
        self.cinza: np.ndarray | None = None
        self.recortes: list[np.ndarray] = []

    def ler_linhas(self, recortes: Sequence[np.ndarray], *, lingua: str, dpi: int) -> Leitura:
        self.recortes = list(recortes)
        if self.linhas is None:
            return Leitura((None,) * len(recortes), self.falha)
        return Leitura(
            tuple(
                None if t is None else tesseract.LinhaDoTesseract(t, (self.confianca,) * len(t.split()))
                for t in self.linhas
            ),
            self.falha,
        )

    def ler_folha(self, cinza: np.ndarray, *, lingua: str, dpi: int) -> tuple[list[tesseract.Palavra], str]:
        self.cinza = cinza
        return (self.folha, self.falha)


def _crua(texto: str, y: float, *, x1: float = 300) -> Any:
    caixa = boxes.Caixa(int(58 * ESCALA), int(y * ESCALA), int(x1 * ESCALA), int((y + 13) * ESCALA))
    return leitor._Cru(texto=texto, caixa=caixa, confianca=0.9, procedencia="glifo")  # noqa: SLF001


class _ComLivro(unittest.TestCase):
    produtor = ""
    fonte = "helv"
    linhas_do_pdf = 12

    def setUp(self) -> None:
        import fitz

        self.caminho = pasta_temporaria(self) / "livro.pdf"
        doc = fitz.open()
        folha = doc.new_page(width=450, height=650)
        for n in range(self.linhas_do_pdf):
            folha.insert_text((60, 60 + 18 * n), LINHA, fontname=self.fonte, fontsize=11)
        if self.produtor:
            doc.set_metadata({"producer": self.produtor})
        doc.save(self.caminho)
        doc.close()

    def ler(self, motor: str, cruas: Sequence[Any], *, diagramas: Sequence[Any] = (), **opcoes: Any) -> pagina.PaginaLida:
        with (
            mock.patch.object(leitor, "linhas_do_glifo", return_value=(list(cruas), [])),
            mock.patch("chess_diagram_ocr.detection.hybrid.detect_diagrams_in_pdf_page", return_value=list(diagramas)),
        ):
            return leitor.ler_pagina(self.caminho, 0, motor=motor, reconhecedor=object(), **opcoes)  # type: ignore[arg-type]

    def boas(self, texto: str = "tne wbite knlght wins a pawn") -> list[Any]:
        return [_crua(texto, 50 + 18 * n) for n in range(self.linhas_do_pdf)]


def _linhas(lida: pagina.PaginaLida) -> list[pagina.LinhaLida]:
    return [linha for bloco in lida.blocos for linha in getattr(bloco, "linhas", ())]


class MarcaChegaATelaTests(_ComLivro):
    """Sem `revisar_em` na `LinhaLida`, nenhuma marca chegava à tela: o mutante que mais assustou."""

    def _marcada(self) -> pagina.PaginaLida:
        # Cada linha tem uma palavra que discorda do glifo e não existe: o teto de 5% marca as primeiras.
        return self.ler(
            "fusao", self.boas("xq wins a pawn the white"), leitor_de_linha=_Falso(linhas=["zqk wins a pawn the white"] * 12)
        )

    def test_a_marca_sai_da_fusao_e_chega_a_linha_lida(self) -> None:
        lida = self._marcada()
        marcadas = [linha.texto[a:b] for linha in _linhas(lida) for a, b in linha.revisar_em]
        self.assertTrue(marcadas, "nenhuma marca chegou à página")
        self.assertEqual(set(marcadas), {"zqk"})

    def test_a_marca_chega_a_corrida_do_documento(self) -> None:
        doc = rico.de_pagina(self._marcada())
        self.assertIn("zqk", [c.texto for c in doc.corridas if c.faixa == documento.REVISAR])
        self.assertTrue(rico.intervalos_a_revisar(doc))

    def test_o_teto_vale_na_folha_real(self) -> None:
        lida = self._marcada()
        total = sum(len(linha.texto.split()) for linha in _linhas(lida))
        marcadas = sum(len(linha.revisar_em) for linha in _linhas(lida))
        self.assertLessEqual(marcadas, total * fusao.FRACAO_MARCADA)

    def test_o_interruptor_desliga_a_marca(self) -> None:
        lida = self.ler(
            "fusao",
            self.boas("xq wins a pawn the white"),
            leitor_de_linha=_Falso(linhas=["zqk wins a pawn the white"] * 12),
            marca_por_palavra=False,
        )
        self.assertFalse(lida.marca_por_palavra)
        self.assertFalse(any(linha.revisar_em for linha in _linhas(lida)))

    def test_a_contagem_le_a_marca_e_nao_a_confianca(self) -> None:
        marcada = pagina.LinhaLida(texto="uma palavra", bbox=(0, 0, 9, 9), confianca=1.0, revisar_em=((0, 3),))
        limpa = pagina.LinhaLida(texto="outra", bbox=(0, 0, 9, 9), confianca=0.0, procedencia="glifo")
        # Pela confiança seria o contrário: a marcada é tranquila, e a outra pede revisão.
        pag = pagina.PaginaLida(
            colunas=(
                pagina.Coluna(
                    indice=0, blocos=(pagina.BlocoDeTexto.de_linhas([marcada]), pagina.BlocoDeTexto.de_linhas([limpa]))
                ),
            ),
            marca_por_palavra=True,
        )
        contagem = documento.contagem_por_faixa(pag)
        self.assertEqual((contagem[documento.REVISAR], contagem[documento.TRANQUILO]), (1, 1))
        so_a_limpa = pagina.PaginaLida(
            colunas=(pagina.Coluna(indice=0, blocos=(pagina.BlocoDeTexto.de_linhas([limpa]),)),), marca_por_palavra=True
        )
        self.assertEqual(documento.contagem_por_faixa(so_a_limpa)[documento.REVISAR], 0)

    def test_a_juncao_de_hifen_leva_a_marca_junto(self) -> None:
        linhas = [
            pagina.LinhaLida(texto="uma em-", bbox=(0, 0, 9, 9)),
            pagina.LinhaLida(texto="barrassment aqui", bbox=(0, 10, 9, 19), revisar_em=((12, 16),)),
        ]
        juntas = leitor._sem_hifen_de_quebra(linhas, frozenset({"embarrassment"}))  # noqa: SLF001
        ((a, b),) = juntas[1].revisar_em
        self.assertEqual(juntas[1].texto[a:b], "aqui")


class CamadaRecusadaTests(_ComLivro):
    produtor = "ABBYY FineReader 15"

    def test_a_camada_de_ocr_nao_entra_como_prosa(self) -> None:
        lida = self.ler("camada_prosa", self.boas())
        self.assertEqual(_linhas(lida)[0].texto, "tne wbite knlght wins a pawn")
        self.assertEqual([a.codigo for a in lida.avisos], [pagina.CAMADA_RECUSADA])

    def test_o_selo_fala_com_gente_e_nao_com_o_codigo_do_criterio(self) -> None:
        mensagem = self.ler("camada_prosa", self.boas()).avisos[0].mensagem
        self.assertNotIn("d:produtor", mensagem)
        self.assertIn("programa de OCR", mensagem)


class SemTextoNaoAvisaTests(_ComLivro):
    linhas_do_pdf = 0

    def test_a_folha_sem_texto_nao_e_recusa(self) -> None:
        self.assertEqual(self.ler("camada_prosa", []).avisos, ())


class LeituraParcialTests(_ComLivro):
    def test_poucas_linhas_para_a_tinta_da_folha(self) -> None:
        um_bloco = [_crua(" ".join([LINHA] * 12), 50)]
        lida = self.ler("glifo", um_bloco)
        self.assertEqual([a.codigo for a in lida.avisos], [pagina.LEITURA_PARCIAL])
        self.assertIn("1 linhas", lida.avisos[0].mensagem)

    def test_poucos_caracteres_para_a_camada_da_folha(self) -> None:
        """Todas as linhas estão lá, com pouco mais de metade do texto: só a camada vê."""
        lida = self.ler("glifo", self.boas("the white knigh"))
        self.assertEqual([a.codigo for a in lida.avisos], [pagina.LEITURA_PARCIAL])

    def test_a_folha_lida_inteira_nao_avisa(self) -> None:
        self.assertEqual(self.ler("glifo", self.boas(LINHA)).avisos, ())

    def test_o_aviso_nao_muda_o_texto(self) -> None:
        lida = self.ler("glifo", self.boas("the white knigh"))
        self.assertEqual(_linhas(lida)[0].texto, "the white knigh")


class ReservaTests(_ComLivro):
    def _palavras(self) -> list[tesseract.Palavra]:
        return [tesseract.Palavra(LINHA.split()[0], 0.9, (180, 100 + 60 * n, 500, 140 + 60 * n), linha=n) for n in range(4)]

    def test_vem_desligada(self) -> None:
        """Ligada por padrão, a régua e os CLIs dariam um número que depende de haver Tesseract."""
        falso = _Falso(folha=self._palavras())
        lida = self.ler("glifo", [_crua("h", 50)], leitor_de_linha=falso)
        self.assertIsNone(falso.cinza)
        self.assertEqual(lida.texto(com_marcas=False), "h")

    def test_os_diagramas_vao_em_branco(self) -> None:
        falso = _Falso(folha=self._palavras())
        candidato = mock.Mock(bbox_pdf=(100.0, 300.0, 200.0, 400.0), detector_score=0.9)
        imagem = np.full((int(650 * ESCALA), int(450 * ESCALA), 3), 255, dtype=np.uint8)
        for n in range(14):
            cv2.putText(imagem, LINHA, (150, 90 + 40 * n), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2, cv2.LINE_AA)
        imagem[int(300 * ESCALA) : int(400 * ESCALA), int(100 * ESCALA) : int(200 * ESCALA)] = 40
        imagem[:4, :4] = 40  # o canto escuro: quem "apagasse" com o pixel do canto não daria branco
        self.ler("glifo", [_crua("h", 50)], diagramas=[candidato], leitor_de_linha=falso, reserva=True, imagem_rgb=imagem)
        assert falso.cinza is not None
        self.assertEqual(int(falso.cinza[int(350 * ESCALA), int(150 * ESCALA)]), 255)

    def test_a_notacao_fica_com_o_glifo_onde_ele_achou_a_linha(self) -> None:
        y = int(50 * ESCALA)
        palavras = [tesseract.Palavra("Nf3", 0.9, (180, y, 400, y + 40), linha=0)]
        lida = self.ler("glifo", [_crua("♘f3", 50)], leitor_de_linha=_Falso(folha=palavras), reserva=True)
        self.assertEqual(lida.texto(com_marcas=False), "♘f3")

    def test_a_caixa_degenerada_nao_casa_com_nada(self) -> None:
        y = int(100 * ESCALA)
        palavras = [tesseract.Palavra("texto", 0.9, (180, y, 400, y + 40), linha=0)]
        degenerada = leitor._Cru(  # noqa: SLF001
            texto="h", caixa=boxes.Caixa(0, 0, 1300, 1900), confianca=0.1, procedencia="glifo"
        )
        lida = self.ler("glifo", [degenerada], leitor_de_linha=_Falso(folha=palavras), reserva=True)
        self.assertEqual(lida.texto(com_marcas=False), "texto")

    def test_marca_as_palavras_em_que_o_leitor_duvida(self) -> None:
        palavras = [
            tesseract.Palavra("white", 0.2 if n == 0 else 0.99, (180 + 40 * n, 100, 210 + 40 * n, 140), linha=0)
            for n in range(25)
        ]
        lida = self.ler("glifo", [_crua("h", 50)], leitor_de_linha=_Falso(folha=palavras), reserva=True)
        self.assertTrue(lida.marca_por_palavra)
        self.assertEqual(sum(len(linha.revisar_em) for linha in _linhas(lida)), 1)

    def test_a_partida_na_calha_nao_parte_no_espaco(self) -> None:
        palavras = [tesseract.Palavra(t, 0.9, (100 + 80 * n, 100, 170 + 80 * n, 125)) for n, t in enumerate("abc")]
        self.assertEqual(len(leitor._partida_no_vao(palavras)), 1)  # noqa: SLF001


class CamadaNaFolhaPerdidaTests(_ComLivro):
    """Quem manda é a montagem da camada, e só a palavra suspeita pode vir de outro lugar."""

    def _suspeita(self) -> list[camada_prosa.PalavraDaCamada]:
        return [
            camada_prosa.PalavraDaCamada(p, (60.0 + 22 * k, 58.0, 80.0 + 22 * k, 66.0), p == "knight")
            for k, p in enumerate(LINHA.split())
        ]

    def _tesseract(self, texto: str) -> tesseract.Palavra:
        # O centro cai na caixa de `knight`, a terceira palavra.
        return tesseract.Palavra(texto, 0.9, (int(104 * ESCALA), int(58 * ESCALA), int(124 * ESCALA), int(66 * ESCALA)))

    def test_sem_reserva_vem_da_camada_com_a_suspeita_marcada(self) -> None:
        with mock.patch.object(camada_prosa, "palavras_da_folha", return_value=self._suspeita()):
            lida = self.ler("camada_prosa", [_crua("h", 50)])
        self.assertEqual([a.codigo for a in lida.avisos], [pagina.CAMADA_NA_FOLHA])
        self.assertIn(LINHA, lida.texto(com_marcas=False))
        self.assertTrue(lida.marca_por_palavra)
        marcadas = {linha.texto[a:b] for linha in _linhas(lida) for a, b in linha.revisar_em}
        self.assertEqual(marcadas, {"knight"})

    def test_com_reserva_a_suspeita_vem_do_tesseract_e_nada_mais_muda(self) -> None:
        falso = _Falso(folha=[self._tesseract("knight!")])
        with mock.patch.object(camada_prosa, "palavras_da_folha", return_value=self._suspeita()):
            lida = self.ler("camada_prosa", [_crua("h", 50)], leitor_de_linha=falso, reserva=True)
        self.assertIn("the white knight! wins a pawn", lida.texto(com_marcas=False))
        self.assertFalse(any(linha.revisar_em for linha in _linhas(lida)[:1]))

    def test_o_lance_da_camada_nao_passa_pelo_tesseract(self) -> None:
        """`10.Qxd2` -> `10.8xd2`: o defeito da segunda rodada, na janela, em 216 de 648 lances mantidos."""
        palavras = [
            camada_prosa.PalavraDaCamada("10.Qxd2", (60.0, 52.0, 110.0, 60.0), False),
            camada_prosa.PalavraDaCamada("afer", (120.0, 52.0, 150.0, 60.0), True),
        ]
        leituras = [
            tesseract.Palavra("10.8xd2", 0.9, (int(60 * ESCALA), int(52 * ESCALA), int(110 * ESCALA), int(60 * ESCALA))),
            tesseract.Palavra("after", 0.9, (int(120 * ESCALA), int(52 * ESCALA), int(150 * ESCALA), int(60 * ESCALA))),
        ]
        cruas = [_crua("10.Qxd2 afer", 50)]
        self.assertEqual(leitor._camada_montada(cruas, palavras, leituras, ESCALA)[0].texto, "10.Qxd2 after")  # noqa: SLF001

    def test_o_lance_em_fonte_de_figurina_chega_bloqueado_e_fica_como_esta(self) -> None:
        """`Rxd5!`, em `FigurineSymbol`: a letra está certa, e o Tesseract leria `Af6` onde está `Nf6`."""
        palavras = [camada_prosa.PalavraDaCamada("Nf6", (60.0, 52.0, 110.0, 60.0), True)]
        leituras = [tesseract.Palavra("Af6", 0.9, (int(60 * ESCALA), int(52 * ESCALA), int(110 * ESCALA), int(60 * ESCALA)))]
        montada = leitor._camada_montada([_crua("Nf6", 50)], palavras, leituras, ESCALA)[0]  # noqa: SLF001
        self.assertEqual(montada.texto, "Nf6")
        self.assertEqual(montada.revisar_em, ())

    def test_sem_palavra_suspeita_o_tesseract_nem_abre(self) -> None:
        falso = _Falso()
        with mock.patch.object(camada_prosa, "palavras_da_folha", return_value=[]):
            self.ler("camada_prosa", [_crua("h", 50)], leitor_de_linha=falso, reserva=True)
        self.assertIsNone(falso.cinza)

    def test_as_palavras_coladas_da_camada_saem_partidas_sem_tesseract(self) -> None:
        cruas = [_crua("thewhite knight", 50)]
        palavras = [
            camada_prosa.PalavraDaCamada("the", (60.0, 52.0, 80.0, 60.0)),
            camada_prosa.PalavraDaCamada("white", (82.0, 52.0, 110.0, 60.0)),
            camada_prosa.PalavraDaCamada("knight", (120.0, 52.0, 150.0, 60.0)),
        ]
        montadas = leitor._camada_montada(cruas, palavras, [], ESCALA)  # noqa: SLF001
        self.assertEqual(montadas[0].texto, "the white knight")

    def test_a_linha_cujas_palavras_nao_somam_o_texto_fica_como_veio(self) -> None:
        """A palavra que caiu noutra linha não pode sumir calada do texto desta."""
        palavras = [camada_prosa.PalavraDaCamada("the", (60.0, 52.0, 80.0, 60.0))]
        cruas = [_crua("the white knight", 50)]
        self.assertEqual(leitor._camada_montada(cruas, palavras, [], ESCALA)[0].texto, "the white knight")  # noqa: SLF001

    def test_a_linha_sem_palavra_nenhuma_fica_como_veio(self) -> None:
        cruas = [_crua("uma linha", 50)]
        self.assertEqual(leitor._camada_montada(cruas, [], [], ESCALA)[0].texto, "uma linha")  # noqa: SLF001

    def test_os_quadros_da_camada_chegam_a_montagem(self) -> None:
        with (
            mock.patch.object(leitor._quadros, "quadros_da_camada", return_value=[(100.0, 200.0)]),  # noqa: SLF001
            mock.patch.object(leitor, "montar", wraps=leitor.montar) as montar,
        ):
            self.ler("camada_prosa", [_crua("h", 50)])
        self.assertEqual(montar.call_args.kwargs["quadros"], [(int(100 * ESCALA), int(200 * ESCALA))])


class LixoDaReservaTests(_ComLivro):
    existe = staticmethod(fusao.existe_no(frozenset({"white"})))

    @staticmethod
    def _token(texto: str, confianca: float = 0.3) -> fusao.Token:
        return fusao.Token(texto, "outro", texto, confianca)

    def test_o_resto_da_faixa_nao_vira_linha(self) -> None:
        for lixo in ("fh)", "a)", "pe", "—"):
            with self.subTest(lixo=lixo):
                self.assertTrue(leitor._e_lixo_da_reserva([self._token(lixo)], self.existe))  # noqa: SLF001

    def test_palavra_lance_numero_e_certeza_ficam(self) -> None:
        for token in (self._token("white"), self._token("Nf3"), self._token("29"), self._token("xq", 0.95), self._token("umalinhagrande")):
            with self.subTest(texto=token.texto):
                self.assertFalse(leitor._e_lixo_da_reserva([token], self.existe))  # noqa: SLF001

    def test_a_pontuacao_colada_nao_faz_a_palavra_virar_lixo(self) -> None:
        self.assertFalse(leitor._e_lixo_da_reserva([self._token("pawn,", 0.2)], fusao.existe_no(frozenset({"pawn"}))))  # noqa: SLF001
        self.assertFalse(leitor._e_lixo_da_reserva([self._token("(29)", 0.2)], self.existe))  # noqa: SLF001

    def test_o_lixo_sai_da_folha_relida(self) -> None:
        palavras = [
            tesseract.Palavra("fh)", 0.2, (20, 100, 60, 130), bloco=1, linha=0),
            tesseract.Palavra("white", 0.9, (400, 200, 600, 240), bloco=2, linha=0),
        ]
        lida = self.ler("glifo", [_crua("h", 50)], leitor_de_linha=_Falso(folha=palavras), reserva=True)
        self.assertEqual(lida.texto(com_marcas=False), "white")


class ItalicoNaProsaTests(_ComLivro):
    fonte = "heit"

    def test_a_tipografia_da_camada_vale_nos_motores_novos(self) -> None:
        lida = self.ler("camada_prosa", self.boas(LINHA))
        self.assertTrue(any(linha.italico_em or linha.italico for linha in _linhas(lida)))
        self.assertTrue(all(linha.italico_em for linha in _linhas(lida)), "a linha não recebeu o detalhe da camada")


class RecorteTests(_ComLivro):
    def test_o_leitor_recebe_a_linha_com_folga(self) -> None:
        """12% da altura de cada lado, como a régua: sem a folga, o `psm 7` come o topo das letras."""
        falso = _Falso(linhas=[LINHA] * 12)
        cruas = self.boas(LINHA)
        self.ler("fusao", cruas, leitor_de_linha=falso)
        altura = cruas[0].caixa.y2 - cruas[0].caixa.y1
        self.assertEqual(falso.recortes[0].shape[0], altura + 2 * max(2, round(altura * 0.12)))


class FaixaPretaNoLeitorTests(unittest.TestCase):
    """A S-599 vale para os dois leitores: o Tesseract recebe a faixa virada, a mesma que o glifo vê."""

    def _folha(self, *, faixa: bool) -> np.ndarray:
        imagem = np.full((1400, 1000, 3), 255, dtype=np.uint8)
        if faixa:
            imagem[300:360, 100:900] = 0
            cv2.putText(imagem, "E.Jackson - D.Baird", (130, 342), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
        return imagem

    def test_a_faixa_chega_como_tinta_sobre_papel(self) -> None:
        recorte = leitor._imagem_do_leitor(self._folha(faixa=True), 220)[300:360, 100:900]
        self.assertGreater(float(recorte.mean()), 200, "o fundo da faixa virou papel")
        self.assertLess(int(recorte.min()), 80, "e as letras viraram tinta")

    def test_a_folha_sem_faixa_e_o_mesmo_objeto(self) -> None:
        imagem = self._folha(faixa=False)
        self.assertIs(leitor._imagem_do_leitor(imagem, 220), imagem)


class FaixaPretaNaFusaoTests(_ComLivro):
    def setUp(self) -> None:
        import fitz

        super().setUp()
        doc = fitz.open(self.caminho)
        doc[0].draw_rect(fitz.Rect(60, 280, 400, 298), color=(0, 0, 0), fill=(0, 0, 0))
        doc.saveIncr()
        doc.close()

    def test_o_recorte_da_fusao_nao_e_a_faixa_preta(self) -> None:
        """Afirmado no recorte que chega ao leitor: trocar `do_leitor` por `imagem` faz este teste acusar."""
        falso = _Falso(linhas=[LINHA] * (self.linhas_do_pdf + 1))
        self.ler("fusao", [*self.boas(LINHA), _crua(LINHA, 283, x1=380)], leitor_de_linha=falso)
        self.assertGreater(float(falso.recortes[-1].mean()), 200)


class _Classificador:
    meta = None

    def classificar(self, recortes: Sequence[np.ndarray]) -> list[tuple[str, float]]:
        return [("a", 0.5 + i / 1000) for i in range(len(recortes))]


class ConfiancaPorCaractereTests(unittest.TestCase):
    def test_um_numero_por_caractere_que_nao_e_espaco(self) -> None:
        imagem = np.full((200, 800, 3), 255, dtype=np.uint8)
        cv2.putText(imagem, "white wins a pawn", (40, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2, cv2.LINE_AA)
        reconhecedor = mock.Mock(classifier=_Classificador(), _leitor_de_linha=None)
        cruas, _ = leitor.linhas_do_glifo(
            imagem, reconhecedor=reconhecedor, colados="nunca", caixa_alta=False, traco=False, marca_fina=False,
            empilhados=False, italico=False, dicionario=False, numeros=False,
        )
        self.assertTrue(cruas)
        self.assertEqual(len(cruas[0].confiancas), len("".join(cruas[0].texto.split())))


class RuidoEmolduradoTests(_ComLivro):
    """Tirar a moldura abre o que estava dentro: sinal solto sai avisado, e não como se fosse a leitura."""

    linhas_do_pdf = 0
    SINAIS = " ".join("i . , ; l - ' :".split() * 8)

    def _com_moldura(self) -> None:
        import fitz

        doc = fitz.open(self.caminho)
        doc[0].draw_rect(fitz.Rect(1, 1, 449, 649), color=(0, 0, 0), width=1)
        doc.saveIncr()
        doc.close()

    def test_o_ruido_na_folha_com_moldura_avisa(self) -> None:
        self._com_moldura()
        lida = self.ler("glifo", [_crua(self.SINAIS, 60)])
        self.assertIn(pagina.FOLHA_NAO_LIDA, [a.codigo for a in lida.avisos])
        self.assertIn("sinais soltos", lida.avisos[0].mensagem)

    def test_o_mesmo_texto_sem_moldura_e_uma_tabela(self) -> None:
        """Uma tabela de torneio dá esse número, e não tem moldura em volta."""
        lida = self.ler("glifo", [_crua(self.SINAIS, 60)])
        self.assertEqual(lida.avisos, ())

    def test_a_leitura_de_verdade_na_folha_com_moldura_nao_avisa(self) -> None:
        self._com_moldura()
        lida = self.ler("glifo", [_crua(LINHA, 60 + 18 * n) for n in range(4)])
        self.assertEqual(lida.avisos, ())


class LanceComSinalTests(unittest.TestCase):
    """O lance com sinal colado não é prosa: era o que ia ao Tesseract e voltava `19.2d3+`."""

    def test_e_notacao(self) -> None:
        for token in ("19.Bd3\uf0b1", "58.Qe7\uf0b2)", "Rxg5i", "Rh8+i)", "24...f4e", "30.Bf2h)", "Rfc1²]", "Na4\uf084", "Bg1²;"):
            with self.subTest(token=token):
                self.assertTrue(fusao.e_notacao(token))

    def test_a_palavra_continua_prosa(self) -> None:
        for token in ("af7anca", "after", "first", "f4e", "Black", "m²"):
            with self.subTest(token=token):
                self.assertFalse(fusao.e_notacao(token))

    def test_o_resultado_com_travessao_e_notacao(self) -> None:
        self.assertTrue(fusao.e_notacao("1—0"))
        self.assertTrue(fusao.e_notacao("0–1"))


class QuemPedeOutraLeituraTests(unittest.TestCase):
    def _palavra(self, texto: str, *, de_figurina: bool = False) -> camada_prosa.PalavraDaCamada:
        return camada_prosa.PalavraDaCamada(texto, (0.0, 0.0, 10.0, 10.0), True, de_figurina)

    def test_a_ligadura_pede(self) -> None:
        self.assertTrue(leitor._pede_outra_leitura(self._palavra("afer")))

    def test_o_lance_com_sinal_nao_pede(self) -> None:
        self.assertFalse(leitor._pede_outra_leitura(self._palavra("19.Bd3\uf0b1")))

    def test_o_sinal_solto_da_fonte_de_figurina_nao_pede(self) -> None:
        """O `i` solto dessa fonte é avaliação: o Tesseract o devolvia como `eel`."""
        self.assertFalse(leitor._pede_outra_leitura(self._palavra("i", de_figurina=True)))

    def test_nao_bloqueada_nao_pede(self) -> None:
        self.assertFalse(
            leitor._pede_outra_leitura(camada_prosa.PalavraDaCamada("after", (0.0, 0.0, 10.0, 10.0)))
        )


class ReservaNaFolhaDaCamadaTests(_ComLivro):
    """O Tesseract na folha inteira custa segundos, e só se paga se houver palavra para ele resolver."""

    def _ler(self, *textos: str) -> _Falso:
        falso = _Falso()
        marcadas = [camada_prosa.PalavraDaCamada(t, (60.0, 50.0, 90.0, 62.0), True) for t in textos]
        with mock.patch.object(camada_prosa, "palavras_da_folha", return_value=marcadas):
            self.ler("camada_prosa", [_crua("h", 50)], leitor_de_linha=falso, reserva=True)
        return falso

    def test_a_palavra_suspeita_chama_o_leitor(self) -> None:
        self.assertIsNotNone(self._ler("afer").cinza)

    def test_so_lance_nao_chama(self) -> None:
        self.assertIsNone(self._ler("Nf3", "19.Bd3\uf0b1").cinza)


class ClasseDoTokenTests(unittest.TestCase):
    def test_letra_de_peca_sozinha_e_notacao(self) -> None:
        for token in ("K", "R", "N", "L", "S", "T", "D", "C"):
            with self.subTest(token=token):
                self.assertEqual(fusao.classe_do_token(token), fusao.NOTACAO)

    def test_fileira_em_fonte_de_diagrama_nao_e_prosa(self) -> None:
        self.assertEqual(fusao.classe_do_token("ÀÉÃÕ"), fusao.OUTRO)

    def test_lance_com_avaliacao_e_parentese_e_notacao(self) -> None:
        """`6.Rg8+–` era prosa, e na camada a figurina do glifo se perdia: 1.187 lances no *Dvoretsky*."""
        for token in ("6.Rg8+–", "Nc5).", "Rh1!).", "Be7–+", "12.Nf3—"):
            with self.subTest(token=token):
                self.assertEqual(fusao.classe_do_token(token), fusao.NOTACAO)

    def test_a_camada_nao_leva_mais_a_figurina_embora(self) -> None:
        existe = fusao.existe_na_camada(fusao.existe_no(frozenset()))
        self.assertEqual(fusao.texto_fundido(fusao.fundir("6.♖g8+", "6.Rg8+–", existe=existe)), "6.♖g8+")


class RegrasDaLeituraDeLinhaTests(unittest.TestCase):
    existe = staticmethod(fusao.existe_no(frozenset({"white", "wins"})))

    def test_a_barra_nao_vence_a_letra(self) -> None:
        """O Tesseract lê `I` como `|`: 8 de 20 erros da fusão, lidos à mão pelo crítico."""
        self.assertEqual(fusao.texto_fundido(fusao.fundir("I wins", "| wins", existe=self.existe)), "I wins")

    def test_a_barra_nao_vence_o_digito_nem_entra_sozinha(self) -> None:
        self.assertEqual(fusao.texto_fundido(fusao.fundir("1 wins", "| wins", existe=self.existe)), "1 wins")
        self.assertEqual(fusao.texto_fundido(fusao.fundir("wins", "| wins", existe=self.existe)), "wins")

    def test_a_palavra_colada_no_lance_nao_sai_duas_vezes(self) -> None:
        """`of2.exf6`, do glifo, com o `of` da camada: saía `of of2.exf6`."""
        saida = fusao.texto_fundido(fusao.fundir("of2.exf6", "of 2.exf6", existe=self.existe))
        self.assertEqual(saida, "of 2.exf6")

    def test_so_a_versao_do_glifo_existe(self) -> None:
        self.assertEqual(fusao.texto_fundido(fusao.fundir("white", "wh1te", existe=self.existe)), "white")

    def test_as_duas_existem_vence_o_leitor(self) -> None:
        self.assertEqual(fusao.texto_fundido(fusao.fundir("white", "wins", existe=self.existe)), "wins")


class SuspeitaTests(unittest.TestCase):
    existe = staticmethod(fusao.existe_no(frozenset({"white"})))

    def test_token_do_glifo_nao_recebe_os_sinais_do_outro_leitor(self) -> None:
        self.assertEqual(fusao.suspeita_de(fusao.Token("xqz", "glifo", "xqz", 0.99), existe=self.existe), 0.0)

    def test_fora_do_lexico_e_sinal_mesmo_com_os_dois_concordando(self) -> None:
        self.assertGreater(fusao.suspeita_de(fusao.Token("xqz", "outro", "xqz", 0.99), existe=self.existe), 0.0)

    def test_a_confianca_do_proprio_leitor_e_sinal(self) -> None:
        self.assertGreater(fusao.suspeita_de(fusao.Token("white", "outro", "white", 0.4), existe=self.existe), 0.0)


class PalavraSuspeitaTests(unittest.TestCase):
    @staticmethod
    def _trecho(texto: str, larguras: Sequence[float], fonte: str = "MyriadPro-Regular", x: float = 0.0) -> dict[str, Any]:
        chars = []
        for letra, largura in zip(texto, larguras, strict=True):
            chars.append((ord(letra), 0, (x, 10.0), (x, 0.0, x + largura * 10, 12.0)))
            x += largura * 10
        return {"font": fonte, "size": 10.0, "chars": tuple(chars)}

    def _palavras(self, *trechos: dict[str, Any], palavras: Sequence[tuple[Any, ...]] | None = None) -> list[Any]:
        if palavras is None:
            palavras = []
            for trecho in trechos:
                texto = "".join(chr(c[0]) for c in trecho["chars"])
                x0, y0, _x1, _y1 = trecho["chars"][0][3]
                palavras.append((x0, y0, trecho["chars"][-1][3][2], 12.0, texto, 0, 0, 0))
        falsa = mock.Mock()
        falsa.get_texttrace.return_value = list(trechos)
        falsa.get_text.return_value = list(palavras)
        return camada_prosa.palavras_da_folha(falsa)

    def test_uso_privado_em_fonte_de_texto_e_suspeito(self) -> None:
        self.assertTrue(self._palavras(self._trecho("\ue001", [0.5]))[0].bloqueada)

    def test_figurina_em_unicode_na_fonte_de_figurina_diz_o_que_e(self) -> None:
        self.assertFalse(self._palavras(self._trecho("♕", [0.5], fonte="FigurineSymbol-T1"))[0].bloqueada)

    def test_digito_na_fonte_de_figurina_e_digito(self) -> None:
        self.assertFalse(self._palavras(self._trecho("12", [0.5, 0.5], fonte="FigurineSymbol-T1"))[0].bloqueada)

    def test_com_duas_ocorrencias_nao_ha_mediana(self) -> None:
        self.assertFalse(self._palavras(self._trecho("ff", [0.3, 0.9]))[0].bloqueada)

    def test_o_vao_sem_caractere_parte_a_palavra(self) -> None:
        """O *Chess Evolution* não escreve o espaço: um token de 52 letras saía colado."""
        um = self._trecho("the", [0.4, 0.4, 0.4])
        dois = self._trecho("white", [0.4, 0.4, 0.4, 0.4, 0.4], x=um["chars"][-1][3][2] + 1.35)
        palavras = self._palavras(um, dois, palavras=[(0.0, 0.0, 40.0, 12.0, "thewhite", 0, 0, 0)])
        self.assertEqual([p.texto for p in palavras], ["the", "white"])

    def test_o_vao_de_entreletra_nao_parte(self) -> None:
        um = self._trecho("the", [0.4, 0.4, 0.4])
        dois = self._trecho("rest", [0.4, 0.4, 0.4, 0.4], x=um["chars"][-1][3][2] + 0.5)
        palavras = self._palavras(um, dois, palavras=[(0.0, 0.0, 40.0, 12.0, "therest", 0, 0, 0)])
        self.assertEqual([p.texto for p in palavras], ["therest"])

    def test_a_ligadura_mapeada_direito_nao_parte_a_palavra(self) -> None:
        """`Aerofl|ot`: o `l` de largura zero fica no começo do `f` largo, e o vão não sai dele."""
        chars = (
            (ord("f"), 0, (0.0, 10.0), (0.0, 0.0, 5.2, 12.0)),
            (ord("l"), 0, (0.0, 10.0), (0.0, 0.0, 0.0, 12.0)),
            (ord("o"), 0, (5.2, 10.0), (5.2, 0.0, 9.0, 12.0)),
        )
        palavras = self._palavras({"font": "MyriadPro-Regular", "size": 10.0, "chars": chars})
        self.assertEqual([p.texto for p in palavras], ["flo"])

    def test_a_suspeita_fica_so_com_o_pedaco_dela(self) -> None:
        normais = self._trecho("ffff", [0.3, 0.3, 0.3, 0.3])
        um = self._trecho("afer", [0.48, 0.52, 0.5, 0.33], x=100.0)
        dois = self._trecho("this", [0.4, 0.3, 0.3, 0.4], x=um["chars"][-1][3][2] + 1.35)
        x1 = dois["chars"][-1][3][2]
        palavras = self._palavras(
            normais, um, dois, palavras=[(0.0, 0.0, 12.0, 12.0, "ffff", 0, 0, 0), (100.0, 0.0, x1, 12.0, "aferthis", 0, 0, 0)]
        )
        self.assertEqual([(p.texto, p.bloqueada) for p in palavras[1:]], [("afer", True), ("this", False)])

    def test_a_folga_vertical_alcanca_a_palavra_da_borda(self) -> None:
        caixa = (0.0, 0.0, 100.0, 10.0)
        palavra = camada_prosa.PalavraDaCamada("x", (10.0, 9.5, 20.0, 11.5))  # centro em 10,5: fora, dentro dos 15%
        linhas, fora = camada_prosa.por_linha([caixa], [palavra])
        self.assertEqual((len(linhas[0]), fora), (1, []))

    def test_o_perfil_do_livro_e_calculado_uma_vez(self) -> None:
        documento_falso = mock.Mock(page_count=5)
        documento_falso.name = "uma-vez.pdf"
        with mock.patch.object(camada_prosa.admissao, "perfil_do_livro", return_value="perfil") as perfil:
            camada_prosa.perfil_em_memoria(documento_falso)
            camada_prosa.perfil_em_memoria(documento_falso)
        camada_prosa._perfis.clear()  # noqa: SLF001
        perfil.assert_called_once()

    def test_vale_a_linha_de_centro_mais_proximo(self) -> None:
        caixas = [(0.0, 0.0, 100.0, 10.0), (0.0, 10.5, 100.0, 20.5)]
        palavra = camada_prosa.PalavraDaCamada("x", (10.0, 10.5, 20.0, 12.5))  # centro em 11,5, na segunda
        linhas, _ = camada_prosa.por_linha(caixas, [palavra])
        self.assertEqual([len(linha) for linha in linhas], [0, 1])


class GuardaTests(unittest.TestCase):
    def _folha(self, linhas: int = 30) -> np.ndarray:
        imagem = np.full((1400, 1000, 3), 255, dtype=np.uint8)
        for n in range(linhas):
            cv2.putText(imagem, LINHA, (120, 80 + 42 * n), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2, cv2.LINE_AA)
        return imagem

    def test_a_altura_da_letra_escala_de_verdade_com_o_dpi(self) -> None:
        """A 73 dpi a letra tem 6 px, abaixo do mínimo de 8 px da régua de 220 dpi."""
        grande = guarda_de_leitura.medir(self._folha(), [], lidos=0, linhas_lidas=0).componentes
        pequena = cv2.resize(self._folha(), None, fx=73 / 220, fy=73 / 220, interpolation=cv2.INTER_AREA)
        medida = guarda_de_leitura.medir(pequena, [], lidos=0, linhas_lidas=0, dpi=73).componentes
        self.assertGreater(medida, 0.5 * grande, "a régua de 220 dpi jogou fora as letras de 73 dpi")

    def test_a_poeira_nao_e_letra(self) -> None:
        imagem = np.full((1400, 1000, 3), 255, dtype=np.uint8)
        for n in range(200):
            imagem[20 + 6 * n : 25 + 6 * n, 30 : 36] = 0
        self.assertEqual(guarda_de_leitura.medir(imagem, [], lidos=0, linhas_lidas=0).componentes, 0)

    def test_a_arte_alta_nao_e_letra(self) -> None:
        imagem = np.full((1400, 1000, 3), 255, dtype=np.uint8)
        for n in range(200):
            imagem[100:400, 20 + 4 * n : 22 + 4 * n] = 0  # componentes altos demais para serem letra
        self.assertEqual(guarda_de_leitura.medir(imagem, [], lidos=0, linhas_lidas=0).componentes, 0)

    def test_as_coordenadas_em_volta_do_diagrama_nao_sao_texto_perdido(self) -> None:
        """A *Polgar 5334*: seis diagramas por folha e 16 de 25 avisando, sem nada perdido."""
        imagem = np.full((1400, 1000, 3), 255, dtype=np.uint8)
        diagrama = (200, 200, 800, 800)  # uma casa = 75 px
        for n in range(8):
            for x, y in ((150, 240 + 75 * n), (820, 240 + 75 * n)):
                cv2.putText(imagem, "87654321"[n], (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2, cv2.LINE_AA)
            for y in (170, 850):
                cv2.putText(imagem, "abcdefgh"[n], (240 + 75 * n, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2, cv2.LINE_AA)
        medida = guarda_de_leitura.medir(imagem, [diagrama], lidos=0, linhas_lidas=0)
        self.assertEqual(medida.componentes, 0)

    def test_a_capa_com_pouca_tinta_nao_e_folha_perdida(self) -> None:
        self.assertFalse(guarda_de_leitura.Medida(47, 2, 1, 1).nao_lida)

    def test_a_folha_curta_com_camada_e_perda_e_nao_capa(self) -> None:
        """*Chess Evolution 2013*, folha 814: três linhas, 68 componentes, e o glifo lê `h`."""
        self.assertTrue(guarda_de_leitura.Medida(68, 1, 1, 1, caracteres_da_camada=80).nao_lida)
        self.assertFalse(guarda_de_leitura.Medida(68, 1, 1, 1, caracteres_da_camada=3).nao_lida)
        self.assertFalse(guarda_de_leitura.Medida(39, 1, 1, 1, caracteres_da_camada=80).nao_lida)

    def test_o_corte_da_densidade_esta_onde_a_medicao_o_pos(self) -> None:
        self.assertTrue(guarda_de_leitura.Medida(1000, 400, 10, 8).nao_lida)
        self.assertFalse(guarda_de_leitura.Medida(1000, 500, 10, 8).nao_lida)

    def test_a_camada_de_um_caractere_nao_absolve_a_folha(self) -> None:
        self.assertTrue(guarda_de_leitura.Medida(2000, 1, 10, 1, caracteres_da_camada=1).nao_lida)

    def test_quem_leu_o_que_a_camada_tem_nao_perdeu_a_folha(self) -> None:
        self.assertFalse(guarda_de_leitura.Medida(1000, 300, 10, 8, caracteres_da_camada=400).nao_lida)
        self.assertTrue(guarda_de_leitura.Medida(1000, 3, 10, 1, caracteres_da_camada=400).nao_lida)
        self.assertTrue(guarda_de_leitura.Medida(1000, 3, 10, 1).nao_lida)


class EsquemaTests(unittest.TestCase):
    def test_a_folha_sem_aviso_continua_no_formato_um(self) -> None:
        """"Nada da primeira entrega muda arquivo gravado": um programa antigo abre a folha comum."""
        dados = pagina.PaginaLida(pagina=1).para_json()
        self.assertEqual(dados["esquema"], 1)
        self.assertNotIn("avisos", dados)

    def test_a_folha_com_aviso_sobe_para_o_dois(self) -> None:
        dados = pagina.PaginaLida(pagina=1, avisos=(pagina.Aviso(pagina.FOLHA_NAO_LIDA, "m"),)).para_json()
        self.assertEqual(dados["esquema"], 2)
        self.assertEqual(pagina.PaginaLida.de_json(dados).avisos[0].codigo, pagina.FOLHA_NAO_LIDA)


class ExecutorTests(unittest.TestCase):
    MOTOR = tesseract.Motor(binario=None, versao="5.5.0")

    def test_a_margem_e_a_que_a_leitura_por_linha_mede(self) -> None:
        self.assertEqual(tesseract.MARGEM_DO_RECORTE, 10)

    def test_o_processo_entra_no_job_object(self) -> None:
        from pathlib import Path

        processo = mock.Mock(returncode=0)
        processo.communicate.return_value = (b"", b"")
        motor = tesseract.Motor(binario=Path("C:/x/tesseract.exe"), versao="5.5.0")
        with mock.patch.object(tesseract, "_no_trabalho") as no_trabalho:
            tesseract.rodar(motor, b"", lingua="eng", dpi=220, psm=7, timeout=5, popen=lambda *_a, **_k: processo)
        no_trabalho.assert_called_once_with(processo)

    def test_erro_no_stderr_com_saida_zero_vira_falha(self) -> None:
        from pathlib import Path

        processo = mock.Mock(returncode=0)
        processo.communicate.return_value = (b"", b"Error in pixReadStream: Unknown format\n")
        motor = tesseract.Motor(binario=Path("C:/x/tesseract.exe"), versao="5.5.0")
        with mock.patch.object(tesseract, "_no_trabalho"), self.assertRaisesRegex(tesseract.FalhaDoTesseract, "pixRead"):
            tesseract.rodar(motor, b"", lingua="eng", dpi=220, psm=7, timeout=5, popen=lambda *_a, **_k: processo)

    def test_saida_diferente_de_zero_e_falha_mesmo_sem_palavra_de_erro(self) -> None:
        from pathlib import Path

        processo = mock.Mock(returncode=3)
        processo.communicate.return_value = (b"parcial", b"nada que pareca erro")
        motor = tesseract.Motor(binario=Path("C:/x/tesseract.exe"), versao="5.5.0")
        with mock.patch.object(tesseract, "_no_trabalho"), self.assertRaises(tesseract.FalhaDoTesseract):
            tesseract.rodar(motor, b"", lingua="eng", dpi=220, psm=7, timeout=5, popen=lambda *_a, **_k: processo)

    def test_o_aviso_comum_do_stderr_nao_derruba(self) -> None:
        from pathlib import Path

        processo = mock.Mock(returncode=0)
        processo.communicate.return_value = (b"ok", b"Estimating resolution as 220\nDetected 4 diacritics\n")
        motor = tesseract.Motor(binario=Path("C:/x/tesseract.exe"), versao="5.5.0")
        with mock.patch.object(tesseract, "_no_trabalho"):
            self.assertEqual(
                tesseract.rodar(motor, b"", lingua="eng", dpi=220, psm=7, timeout=5, popen=lambda *_a, **_k: processo), "ok"
            )

    def test_tessdata_em_caminho_acentuado_vai_pelo_ambiente(self) -> None:
        from pathlib import Path

        motor = tesseract.Motor(binario=Path("C:/x/tesseract.exe"), tessdata=Path("C:/Usuários/ação/tessdata"), versao="5.5.0")
        ambiente = tesseract.ambiente_do_processo(motor, {})
        self.assertEqual(ambiente["TESSDATA_PREFIX"], str(motor.tessdata))

    def test_version_travado_e_morto(self) -> None:
        from pathlib import Path

        processo = mock.Mock()
        processo.communicate.side_effect = [subprocess.TimeoutExpired("t", 1), (b"", b"")]
        with mock.patch.object(subprocess, "Popen", return_value=processo):
            motor = tesseract.examinar(Path("C:/x/tesseract.exe"))
        self.assertFalse(motor.disponivel)
        processo.kill.assert_called_once()


class AtalhoTests(unittest.TestCase):
    def test_shift_f7_e_o_proxima_a_revisar(self) -> None:
        self.assertEqual(atalhos.TECLAS_DO_EDITOR["proxima_a_revisar"], "<Shift-F7>")


if __name__ == "__main__":
    unittest.main()
