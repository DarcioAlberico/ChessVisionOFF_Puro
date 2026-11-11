"""A primeira entrega da prosa na janela: a caixa de motor, a língua, o selo e a marca (S-710, S-716 a S-718).

**Os testes afirmam o efeito no texto mostrado**, e não uma chamada: o PDF é de verdade, desenhado aqui, e
`ler_pagina` roda inteiro. Só o que precisa de modelo ou de binário é trocado: as linhas do glifo, o detector
de diagrama e o Tesseract.
"""

from __future__ import annotations

import errno
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest import mock

import numpy as np
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.text import arquivo, boxes, cache_texto, leitor, pagina, rico, tesseract
from chess_diagram_ocr.text.leitor_de_linha import Leitura
from chess_diagram_ocr.ui import state as estado_da_janela
from chess_diagram_ocr.ui import strings

if TEM_PYQT:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QTextCursor
    from PyQt6.QtTest import QTest

    from chess_diagram_ocr.qt import tema, texto_leitura
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto
    from chess_diagram_ocr.text.lingua import LinguaDoLivro


class _Falso:
    """O Tesseract de mentira: lê o que lhe mandam, e anota em que língua pediram."""

    def __init__(self, texto: str = "the white Nf3 wins a pawn") -> None:
        self.texto = texto
        self.linguas: list[str] = []

    def ler_linhas(self, recortes: Sequence[np.ndarray], *, lingua: str, dpi: int) -> Leitura:
        self.linguas.append(lingua)
        return Leitura(tuple(tesseract.LinhaDoTesseract(self.texto, (0.99,) * len(self.texto.split())) for _ in recortes))

    def ler_folha(self, cinza: np.ndarray, *, lingua: str, dpi: int) -> tuple[list[tesseract.Palavra], str]:
        return ([], "Sem Tesseract.")


def _crua(texto: str, y: int) -> Any:
    return leitor._Cru(texto=texto, caixa=boxes.Caixa(58, y, 300, y + 13), confianca=0.9, procedencia="glifo")  # noqa: SLF001


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class _Aba(unittest.TestCase):
    def setUp(self) -> None:
        import fitz

        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.pasta = pasta_temporaria(self)
        self.livro = self.pasta / "livro.pdf"
        doc = fitz.open()
        folha = doc.new_page(width=450, height=650)
        for n in range(30):
            folha.insert_text((60, 60 + 18 * n), "the white knight wins a pawn", fontname="helv", fontsize=11)
        doc.save(self.livro)
        doc.close()
        self.painel = PainelDeTexto(dpi=72, pasta_de_rascunhos=self.pasta / "rascunhos")
        self.addCleanup(descartar, self.painel)
        self.painel.resize(1000, 700)
        self.painel.show()
        self.app.processEvents()
        self.recados: list[str] = []
        self.painel.estado.connect(self.recados.append)
        self.painel.definir_livro(self.livro, pagina=0)

    def escolher(self, motor: str) -> None:
        caixa = self.painel.leitura.escolha_de_motor
        caixa.setCurrentIndex(caixa.findData(motor))
        caixa.activated.emit(caixa.currentIndex())

    def ler(self, cruas: Sequence[Any], falso: _Falso | None = None) -> None:
        with (
            mock.patch.object(leitor, "_reconhecedor_configurado", return_value=mock.MagicMock(name="glifo")),
            mock.patch.object(leitor, "linhas_do_glifo", return_value=(list(cruas), [])),
            mock.patch("chess_diagram_ocr.detection.hybrid.detect_diagrams_in_pdf_page", return_value=[]),
            mock.patch("chess_diagram_ocr.text.leitor_de_linha.leitor_padrao", return_value=falso or _Falso()),
        ):
            self.painel.ler()
            tarefa = self.painel.leitura.tarefa
            self.assertIsNotNone(tarefa, "a tarefa não partiu")
            self.assertTrue(tarefa.wait(30_000))  # type: ignore[union-attr]
            self.app.processEvents()

    def boas(self, texto: str = "tne wbite ♘f3 wins a pawn") -> list[Any]:
        return [_crua(texto, 50 + 18 * n) for n in range(30)]


class ProcedenciaPorPalavraNaTelaTests(_Aba):
    """A S-722 afirmada no efeito: o que o painel mostra e grava, e não o que `ler_pagina` devolve."""

    def _lida(self) -> None:
        self.escolher("fusao")
        self.ler(self.boas(), _Falso())

    def test_as_corridas_e_o_rodape_dizem_de_quem_e_cada_palavra(self) -> None:
        self._lida()
        corridas = self.painel.documento.corridas
        self.assertEqual({c.procedencia for c in corridas if "♘" in c.texto}, {"glifo"})
        self.assertEqual({c.procedencia for c in corridas if "wins" in c.texto}, {"tesseract"})
        self.assertRegex(self.recados[-1], r"Texto: \d+% Tesseract, \d+% glifo\.")

    def test_o_motor_de_glifo_nao_fala_de_procedencia(self) -> None:
        self.escolher("glifo")
        self.ler(self.boas())
        self.assertNotIn("Texto:", self.recados[-1])

    def test_o_arquivo_gravado_um_programa_anterior_abre(self) -> None:
        """Até o G102 o `tesseract` não vai ao disco, e a folha reaberta mostra o mesmo texto."""
        self._lida()
        caminho = self.pasta / "folha.cvtxt"
        self.painel.caderno._salvar_documento_em(caminho)
        bruto = caminho.read_text(encoding="utf-8")
        self.assertNotIn("tesseract", bruto)
        self.assertNotIn("procedencia_em", bruto)
        self.assertEqual(arquivo.carregar(caminho).para_texto(), self.painel.texto())


class CacheDeLeituraNaTelaTests(_Aba):
    """A S-725 afirmada na aba: a leitura volta do disco, o texto é o mesmo, e o menu limpa."""

    def setUp(self) -> None:
        super().setUp()
        self.processos = 0
        self.cache = cache_texto.CacheDeLeitura(self.pasta / "cache_texto")
        motor = tesseract.Motor(binario=self.pasta / "tesseract.exe", tessdata=self.pasta, versao="5.5.0")
        trocas = [
            mock.patch.object(cache_texto, "padrao", return_value=self.cache),
            mock.patch.object(tesseract, "achar_motor", return_value=motor),
            mock.patch.object(tesseract, "ler_linhas", self._ler_linhas),
        ]
        for troca in trocas:
            troca.start()
            self.addCleanup(troca.stop)

    def _ler_linhas(self, recortes: Sequence[Any], **_: Any) -> list[tesseract.LinhaDoTesseract]:
        self.processos += 1
        return [tesseract.LinhaDoTesseract("the white Nf3 wins a pawn", (0.9,) * 6) for _ in recortes]

    def _ler(self) -> pagina.PaginaLida:
        imagem = texto_leitura.renderizar(self.livro, 0, dpi=72)
        with (
            mock.patch.object(leitor, "linhas_do_glifo", return_value=(self.boas(), [])),
            mock.patch.object(leitor, "_reconhecedor_configurado", return_value=mock.MagicMock(name="glifo")),  # sem o .pt na CI (S-847)
            mock.patch("chess_diagram_ocr.detection.hybrid.detect_diagrams_in_pdf_page", return_value=[]),
        ):
            return texto_leitura.ler_a_folha(self.livro, 0, dpi=72, motor="fusao", imagem_rgb=imagem)

    def test_a_segunda_leitura_nao_abre_processo_e_o_texto_e_o_mesmo(self) -> None:
        primeira = self._ler()
        self.assertEqual(self.processos, 1)
        self.assertGreater(self.cache.tamanho(), 0)
        segunda = self._ler()
        self.assertEqual(self.processos, 1)
        self.assertEqual(primeira.texto(), segunda.texto())

    def test_o_menu_limpa_e_a_leitura_seguinte_abre_processo(self) -> None:
        self._ler()
        self.painel.executar("limpar_cache_de_leitura")
        tarefa = self.painel.leitura._limpeza_do_cache
        self.assertIsNotNone(tarefa)
        self.assertTrue(tarefa.wait(30_000))  # type: ignore[union-attr]
        self.app.processEvents()
        self.assertEqual(self.cache.tamanho(), 0)
        self.assertIn("Cache de leitura limpo: 1 folha(s)", self.recados[-1])
        self._ler()
        self.assertEqual(self.processos, 2)

    def test_com_o_cache_vazio_o_menu_diz_que_ja_estava(self) -> None:
        self.painel.executar("limpar_cache_de_leitura")
        self.assertTrue(self.painel.leitura._limpeza_do_cache.wait(30_000))  # type: ignore[union-attr]
        self.app.processEvents()
        self.assertEqual(self.recados[-1], "O cache de leitura já estava vazio.")

    def test_disco_cheio_vira_aviso_na_folha_e_nao_perde_a_leitura(self) -> None:
        erro = OSError(errno.ENOSPC, "No space left on device")
        with mock.patch.object(cache_texto, "atomic_write_text", side_effect=erro):
            lida = self._ler()
        self.assertIn("the white", lida.texto())
        avisos = {a.codigo: a.mensagem for a in lida.avisos}
        self.assertIn("disco está cheio", avisos[pagina.CACHE_NAO_GRAVADO])
        self.assertNotIn("avisos", lida.para_json())


class CaixaDeMotorTests(_Aba):
    def test_os_dois_novos_tem_rotulo_e_nunca_o_identificador_cru(self) -> None:
        caixa = self.painel.leitura.escolha_de_motor
        self.assertEqual(caixa.itemText(caixa.findData("camada_prosa")), "Camada na prosa (livro digital)")
        self.assertEqual(caixa.itemText(caixa.findData("fusao")), "Glifo + Tesseract (experimental)")

    def test_o_padrao_nao_mudou(self) -> None:
        self.assertEqual(self.painel.leitura.motor, "auto")

    def test_escolher_a_camada_na_prosa_muda_o_texto_na_tela(self) -> None:
        self.escolher("camada_prosa")
        self.ler(self.boas())
        # A camada diz `knight` onde o glifo viu `♘f3`, e a palavra que existe vence: é a regra 1.
        self.assertIn("the white knight wins a pawn", self.painel.texto())
        self.assertNotIn("tne", self.painel.texto())

    def test_escolher_a_fusao_muda_o_texto_na_tela_e_le_na_lingua_escolhida(self) -> None:
        falso = _Falso()
        self.escolher("fusao")
        caixa = self.painel.leitura.escolha_de_lingua
        caixa.setCurrentIndex(caixa.findData("por"))
        caixa.activated.emit(caixa.currentIndex())
        self.ler(self.boas(), falso)
        self.assertIn("the white ♘f3 wins a pawn", self.painel.texto())
        self.assertEqual(falso.linguas, ["por"])

    def test_motor_e_lingua_sobrevivem_a_sessao(self) -> None:
        self.painel.leitura.definir_motor("fusao")
        self.painel.leitura.definir_lingua("deu")
        guardado = estado_da_janela.AppState()
        self.painel.anotar_estado(guardado)
        self.assertEqual((guardado.texto_motor, guardado.texto_lingua), ("fusao", "deu"))
        relido = estado_da_janela.state_from_dict(guardado.to_dict())
        self.assertEqual(relido.texto_lingua, "deu")
        self.painel.leitura.definir_motor("glifo")
        self.painel.leitura.definir_lingua("eng")
        self.painel.aplicar_estado(relido)
        self.assertEqual((self.painel.leitura.motor, self.painel.leitura.lingua), ("fusao", "deu"))
        self.assertEqual(self.painel.leitura.escolha_de_lingua.currentData(), "deu")

    def test_lingua_desconhecida_e_ignorada(self) -> None:
        self.painel.leitura.definir_lingua("klingon")
        self.assertEqual(self.painel.leitura.lingua, tesseract.LINGUA_PADRAO)


class SeloTests(_Aba):
    def test_a_folha_lida_nao_tem_selo(self) -> None:
        self.escolher("glifo")
        self.ler(self.boas("the white knight wins a pawn"))
        self.assertTrue(self.painel.selo_da_folha.isHidden())

    def test_a_folha_perdida_mostra_o_selo_em_vez_de_sair_calada(self) -> None:
        self.escolher("glifo")
        self.ler([_crua("h", 50)])
        self.assertFalse(self.painel.selo_da_folha.isHidden())
        self.assertIn("não foi lida inteira", self.painel.selo_da_folha.text())
        self.assertIn("Sem Tesseract.", self.painel.selo_da_folha.text())

    def test_a_folha_lida_como_ruido_mostra_o_selo(self) -> None:
        self.escolher("glifo")
        self.ler(self.boas("x" * 150))
        self.assertFalse(self.painel.selo_da_folha.isHidden())
        self.assertIn("saiu com ruído", self.painel.selo_da_folha.text())

    def test_o_selo_some_na_folha_seguinte(self) -> None:
        aviso = pagina.Aviso(pagina.FOLHA_NAO_LIDA, "Não foi lida.")
        self.painel.mostrar_pagina(pagina.PaginaLida(pagina=0, avisos=(aviso,)))
        self.assertFalse(self.painel.selo_da_folha.isHidden())
        self.painel.mostrar_pagina(pagina.PaginaLida(pagina=1))
        self.assertTrue(self.painel.selo_da_folha.isHidden())

    def test_o_selo_volta_com_a_folha_reaberta_do_arquivo(self) -> None:
        from chess_diagram_ocr.text import arquivo

        aviso = pagina.Aviso(pagina.LEIAUTE_DE_RESERVA, "Relida pela reserva.")
        linha = pagina.LinhaLida(texto="texto", bbox=(0, 0, 9, 9))
        bloco = pagina.BlocoDeTexto.de_linhas([linha])
        lida = pagina.PaginaLida(colunas=(pagina.Coluna(indice=0, blocos=(bloco,)),), avisos=(aviso,))
        reaberto = arquivo.de_json(arquivo.para_json(rico.de_pagina(lida)))
        self.painel.desenhar_documento(reaberto)
        self.painel.vista.atualizar_status()
        self.assertEqual(self.painel.selo_da_folha.text(), "Relida pela reserva.")


class LinguaNoCadernoTests(_Aba):
    """Trocar a língua da fusão é pedir a leitura nova, como trocar de motor (S-717)."""

    def test_o_motor_gravado_leva_a_lingua_so_na_fusao(self) -> None:
        self.painel.leitura.definir_motor("fusao")
        self.painel.leitura.definir_lingua("por")
        self.assertEqual(self.painel.leitura.motor_gravado(), "fusao:por")
        self.painel.leitura.definir_motor("glifo")
        self.assertEqual(self.painel.leitura.motor_gravado(), "glifo")

    def test_a_folha_lida_em_outra_lingua_nao_abre_do_caderno(self) -> None:
        from chess_diagram_ocr.text import caderno

        estado = caderno.EstadoDaFolha(pagina=0, estado=caderno.LIDA, motor="fusao:eng")
        self.painel.leitura.definir_motor("fusao")
        self.painel.leitura.definir_lingua("eng")
        self.assertTrue(caderno.abre_do_caderno(estado, motor=self.painel.leitura.motor_gravado()))
        self.painel.leitura.definir_lingua("por")
        self.assertFalse(caderno.abre_do_caderno(estado, motor=self.painel.leitura.motor_gravado()))


class LinguaDoLivroTests(_Aba):
    """A língua do livro na janela (S-723). Teste de fiação afirma efeito: o que o leitor de linha recebe, e o que fica."""

    PROSA_EM_PORTUGUES = "o rei das brancas não pode sair da coluna com uma torre em jogo pelo lado da dama"

    def setUp(self) -> None:
        super().setUp()
        import fitz

        self.livro_em_ingles = self.livro
        self.livro = self.pasta / "em_portugues.pdf"
        doc = fitz.open()
        folha = doc.new_page(width=450, height=650)
        for n in range(30):
            folha.insert_text((60, 60 + 18 * n), self.PROSA_EM_PORTUGUES[:60], fontname="helv", fontsize=9)
        doc.save(self.livro)
        doc.close()
        self.painel.caderno._pasta_de_cadernos = self.pasta / "cadernos"
        self.painel.definir_livro(None)
        self.painel.definir_livro(self.livro, pagina=0)
        self.addCleanup(self.painel.caderno.fechar_caderno)
        self.escolher("fusao")

    def _ler_em_portugues(self, falso: _Falso | None = None) -> None:
        self.ler([_crua(self.PROSA_EM_PORTUGUES, 50 + 18 * n) for n in range(30)], falso or _Falso(self.PROSA_EM_PORTUGUES))

    def test_a_folha_lida_decide_a_lingua_e_a_leitura_seguinte_usa_ela(self) -> None:
        falso = _Falso(self.PROSA_EM_PORTUGUES)
        self._ler_em_portugues(falso)
        self.assertEqual(falso.linguas, [tesseract.LINGUA_PADRAO])
        self.assertEqual(self.painel.leitura.lingua, "por")
        self.assertEqual(self.painel.leitura.escolha_de_lingua.currentData(), "por")
        self.assertTrue(any("Português (detectada" in recado for recado in self.recados), self.recados)

    def test_a_segunda_leitura_recebe_a_lingua_detectada(self) -> None:
        """Pelo botão: o motor anotado na folha é `fusao:eng`, e a língua nova pede a leitura nova em vez do caderno."""
        self._ler_em_portugues()
        falso = _Falso(self.PROSA_EM_PORTUGUES)
        self._ler_em_portugues(falso)
        self.assertEqual(falso.linguas, ["por"])

    def test_a_escolhida_a_mao_vence_a_detectada(self) -> None:
        caixa = self.painel.leitura.escolha_de_lingua
        caixa.setCurrentIndex(caixa.findData("deu"))
        caixa.activated.emit(caixa.currentIndex())
        falso = _Falso(self.PROSA_EM_PORTUGUES)
        self._ler_em_portugues(falso)
        self.assertEqual(falso.linguas, ["deu"])
        self.assertEqual(self.painel.leitura.lingua, "deu")
        self.assertEqual(self.painel.caderno.aberto.lingua().detectada, "por")  # type: ignore[union-attr]
        self.assertEqual(self.painel.caderno.aberto.lingua().manual, "deu")  # type: ignore[union-attr]

    def test_a_lingua_fica_no_caderno_e_volta_com_o_livro(self) -> None:
        self._ler_em_portugues()
        self.painel.definir_livro(None)
        self.assertEqual(self.painel.leitura.lingua, tesseract.LINGUA_PADRAO)
        self.painel.definir_livro(self.livro, pagina=0)
        self.assertEqual(self.painel.leitura.lingua, "por")

    def test_a_lingua_de_um_livro_nao_passa_para_o_outro(self) -> None:
        caixa = self.painel.leitura.escolha_de_lingua
        caixa.setCurrentIndex(caixa.findData("rus"))
        caixa.activated.emit(caixa.currentIndex())
        outro = self.pasta / "outro.pdf"
        outro.write_bytes(self.livro.read_bytes() + b"% outro livro")
        self.painel.definir_livro(outro, pagina=0)
        self.assertEqual(self.painel.leitura.lingua, tesseract.LINGUA_PADRAO)
        self.painel.definir_livro(self.livro, pagina=0)
        self.assertEqual(self.painel.leitura.lingua, "rus")

    def test_o_estado_da_janela_nao_guarda_a_lingua_do_livro(self) -> None:
        caixa = self.painel.leitura.escolha_de_lingua
        caixa.setCurrentIndex(caixa.findData("rus"))
        caixa.activated.emit(caixa.currentIndex())
        guardado = estado_da_janela.AppState()
        self.painel.anotar_estado(guardado)
        self.assertEqual(guardado.texto_lingua, tesseract.LINGUA_PADRAO)

    def test_o_comando_do_menu_escolhe_e_volta_a_detectar(self) -> None:
        self._ler_em_portugues()
        with mock.patch("chess_diagram_ocr.qt.texto_leitura.QInputDialog.getItem", return_value=("Francês", True)):
            self.painel.executar("lingua_do_livro")
        self.assertEqual(self.painel.leitura.lingua, "fra")
        self.assertEqual(self.painel.caderno.aberto.lingua().manual, "fra")  # type: ignore[union-attr]
        with mock.patch(
            "chess_diagram_ocr.qt.texto_leitura.QInputDialog.getItem", return_value=(strings.LINGUA_DETECTADA_PELO_LIVRO, True)
        ):
            self.painel.executar("lingua_do_livro")
        self.assertEqual(self.painel.leitura.lingua, "por")
        self.assertEqual(self.painel.caderno.aberto.lingua().manual, "")  # type: ignore[union-attr]

    def test_cancelar_o_dialogo_nao_muda_nada(self) -> None:
        with mock.patch("chess_diagram_ocr.qt.texto_leitura.QInputDialog.getItem", return_value=("Francês", False)):
            self.painel.executar("lingua_do_livro")
        self.assertEqual(self.painel.leitura.lingua, tesseract.LINGUA_PADRAO)

    def test_disco_recusando_a_lingua_nao_derruba_o_slot(self) -> None:
        with mock.patch.object(self.painel.caderno.aberto, "guardar_lingua", side_effect=OSError("disco cheio")):
            self.painel.leitura._escolher_lingua("por")
        self.assertEqual(self.painel.leitura.lingua, "por")
        self.assertTrue(any("disco cheio" in recado for recado in self.recados), self.recados)

    def test_as_dez_folhas_sem_resposta_dizem_que_a_pessoa_escolha(self) -> None:
        """É o scan russo sem camada: o glifo escreve latim sem sentido, e calar seria ler em inglês para sempre."""
        sem_sentido = pagina.PaginaLida(pagina=9, colunas=(pagina.Coluna(indice=0, blocos=(pagina.BlocoDeTexto.de_linhas(
            [pagina.LinhaLida(texto=" ".join(["xqzw"] * 30), bbox=(0, 0, 9, 9))]
        ),)),))
        self.painel.leitura._lingua_do_livro = LinguaDoLivro(folhas=tuple(range(9)))
        self.assertEqual(self.painel.leitura._anotar_lingua_da_folha(sem_sentido, "").strip(), strings.LINGUA_NAO_DETECTADA)
        self.assertEqual(self.painel.leitura.lingua, tesseract.LINGUA_PADRAO)

    def test_a_camada_com_palavras_e_quem_conta_para_a_lingua(self) -> None:
        """O glifo não tem cirílico: sem a camada, o livro russo com camada ficaria sem resposta."""
        sem_sentido = pagina.PaginaLida(pagina=0, colunas=(pagina.Coluna(indice=0, blocos=(pagina.BlocoDeTexto.de_linhas(
            [pagina.LinhaLida(texto=" ".join(["xqzw"] * 30), bbox=(0, 0, 9, 9))]
        ),)),))
        russo = "Белый король не может выйти на открытую линию и при этом пешки становятся сильнее после размена ладей на доске " * 2
        self.painel.leitura._anotar_lingua_da_folha(sem_sentido, russo)
        self.assertEqual(self.painel.leitura.lingua, "rus")

    def test_a_leitura_de_verdade_leva_a_camada_a_deteccao(self) -> None:
        """Fiação: a folha deste teste é inglês na camada, e o Tesseract de mentira lê português: quem conta é a camada."""
        self.painel.definir_livro(self.livro_em_ingles, pagina=0)
        self._ler_em_portugues()
        self.assertEqual(self.painel.caderno.aberto.lingua().detectada, "eng")  # type: ignore[union-attr]

    def test_o_comando_esta_no_menu_texto(self) -> None:
        from chess_diagram_ocr.ui import menu

        texto = next(m for m in menu.MENUS if m.titulo == "Texto")
        self.assertIn("lingua_do_livro", [item.acao for item in texto.itens])

    def test_settings_nao_conhece_a_lingua(self) -> None:
        """S-218: `settings.py` está no digest do campo, e a língua do livro nunca passa por ele."""
        from chess_diagram_ocr import config

        fonte = (Path(config.__file__).parent / "settings.py").read_text(encoding="utf-8")
        self.assertNotIn("lingua", fonte)


class LexicoDoLivroNaFusaoTests(_Aba):
    """`lingua` escolhe o léxico, e não só o `tessdata`: `und` existe no alemão, e no português não (S-723)."""

    def _fundida(self, lingua: str) -> str:
        cruas = [_crua("und und und und und und und und", 50 + 18 * n) for n in range(30)]
        with (
            mock.patch.object(leitor, "linhas_do_glifo", return_value=(cruas, [])),
            mock.patch("chess_diagram_ocr.detection.hybrid.detect_diagrams_in_pdf_page", return_value=[]),
        ):
            lida = leitor.ler_pagina(
                self.livro, 0, dpi=72, motor="fusao", lingua=lingua, leitor_de_linha=_Falso("unol unol unol unol unol unol unol unol"), reconhecedor=object()
            )
        return lida.texto()

    def test_a_lingua_do_livro_muda_quem_vence(self) -> None:
        self.assertIn("und", self._fundida("deu"))
        self.assertNotIn("und", self._fundida("por"))


class ProximaARevisarTests(_Aba):
    def _com_marca(self) -> None:
        linha = pagina.LinhaLida(texto="uma palavra errada outra", bbox=(0, 0, 9, 9), revisar_em=((4, 11), (19, 24)))
        bloco = pagina.BlocoDeTexto.de_linhas([linha])
        self.painel.mostrar_pagina(
            pagina.PaginaLida(pagina=0, colunas=(pagina.Coluna(indice=0, blocos=(bloco,)),), marca_por_palavra=True)
        )

    def test_vai_de_palavra_em_palavra_e_da_a_volta(self) -> None:
        self._com_marca()
        vistas = []
        for _ in range(3):
            self.painel.proxima_a_revisar()
            vistas.append(self.painel.editor.textCursor().selectedText())
        self.assertEqual(vistas, ["palavra", "outra", "palavra"])

    def test_sem_marca_responde_no_rodape(self) -> None:
        self.painel.desenhar_documento(rico.de_texto("nada a revisar"))
        self.painel.proxima_a_revisar()
        self.assertEqual(self.recados[-1], strings.NADA_A_REVISAR)

    def test_o_comando_esta_na_fita(self) -> None:
        self.assertIsNotNone(self.painel.fita.botao("proxima_a_revisar"))


class CorrigirAMarcaNoEditorTests(_Aba):
    """A correção de verdade: o editor grava a diferença mínima, e os pedaços da palavra não são marca.

    **Tem de ser pelo editor.** Trocar a corrida inteira por `replace` é o que nenhuma tecla faz, e foi assim que
    `w` e `ite` chegaram ao arquivo como palavras a revisar sem nenhum teste acusar.
    """

    def _folha(self, texto: str, *marcas: tuple[int, int]) -> None:
        linha = pagina.LinhaLida(texto=texto, bbox=(0, 0, 9, 9), revisar_em=marcas)
        bloco = pagina.BlocoDeTexto.de_linhas([linha])
        self.painel.mostrar_pagina(
            pagina.PaginaLida(pagina=0, colunas=(pagina.Coluna(indice=0, blocos=(bloco,)),), marca_por_palavra=True)
        )

    def _cursor(self, inicio: int, fim: int | None = None) -> None:
        editor = self.painel.editor
        cursor = editor.textCursor()
        cursor.setPosition(inicio)
        if fim is not None:
            cursor.setPosition(fim, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        editor.setFocus()
        self.app.processEvents()

    def _marcas_depois_de_reabrir(self) -> list[str]:
        from chess_diagram_ocr.text import arquivo

        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "folha.cvtxt"
            self.painel.caderno._salvar_documento_em(caminho)  # noqa: SLF001
            reaberto = arquivo.carregar(caminho)
        texto = reaberto.para_texto()
        return [texto[a:b] for a, b in rico.intervalos_a_revisar(reaberto)]

    def _paradas(self) -> list[str]:
        vistas = []
        for _ in range(3):
            self.painel.proxima_a_revisar()
            vistas.append(self.painel.editor.textCursor().selectedText())
        return vistas

    def _so_sobra(self, *palavras: str) -> None:
        self.assertEqual(self._marcas_depois_de_reabrir(), list(palavras))
        self.assertEqual(set(self._paradas()), set(palavras))

    def test_backspace_e_a_letra_certa(self) -> None:
        self._folha("the wbite knight wlns a pawn", (4, 9), (17, 21))
        self._cursor(6)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Backspace)
        QTest.keyClicks(self.painel.editor, "h")
        self.assertIn("the white knight", self.painel.editor.toPlainText())
        self._so_sobra("wlns")

    def test_selecionar_a_letra_e_digitar(self) -> None:
        self._folha("the wbite knight wlns a pawn", (4, 9), (17, 21))
        self._cursor(5, 6)
        QTest.keyClicks(self.painel.editor, "h")
        self._so_sobra("wlns")

    def test_a_letra_que_faltava(self) -> None:
        self._folha("the whte knight wlns a pawn", (4, 8), (16, 20))
        self._cursor(6)
        QTest.keyClicks(self.painel.editor, "i")
        self._so_sobra("wlns")

    def test_a_letra_que_faltava_no_comeco(self) -> None:
        """`hite` continua inteiro num trecho igual ao lido, e a palavra agora é outra."""
        self._folha("the hite knight wlns a pawn", (4, 8), (16, 20))
        self._cursor(4)
        QTest.keyClicks(self.painel.editor, "w")
        self._so_sobra("wlns")

    def test_a_letra_a_mais_no_meio(self) -> None:
        self._folha("the whiite knight wlns a pawn", (4, 10), (18, 22))
        self._cursor(6)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Delete)
        self._so_sobra("wlns")

    def test_a_letra_a_mais_no_comeco(self) -> None:
        """O que sobra é igual ao lido, e a palavra corrigida inteira cabe num trecho igual."""
        self._folha("the xwhite knight wlns a pawn", (4, 10), (18, 22))
        self._cursor(4)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Delete)
        self._so_sobra("wlns")

    def test_a_letra_a_mais_no_fim(self) -> None:
        self._folha("the whitex knight wlns a pawn", (4, 10), (18, 22))
        self._cursor(9)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Delete)
        self._so_sobra("wlns")

    def test_o_bloco_de_duas_palavras_marcadas(self) -> None:
        """Só o espaço fica de texto sem marca, e ele basta para não ser a faixa do bloco inteiro."""
        self._folha("wbite wlns", (0, 5), (6, 10))
        self._cursor(2)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Backspace)
        QTest.keyClicks(self.painel.editor, "h")
        self._so_sobra("wlns")

    def test_a_letra_que_faltava_no_fim(self) -> None:
        self._folha("the whit knight wlns a pawn", (4, 8), (16, 20))
        self._cursor(8)
        QTest.keyClicks(self.painel.editor, "e")
        self._so_sobra("wlns")

    def _trocar_letra(self, posicao: int, letra: str) -> None:
        self._cursor(posicao, posicao + 1)
        QTest.keyClicks(self.painel.editor, letra)

    def test_gravar_corrigir_e_gravar_nao_apaga_a_marca_intacta(self) -> None:
        """O carimbo da primeira gravação funde o resto do bloco, e a segunda não pode tomá-lo por faixa."""
        self._folha("the wbite knight wlns a pawm", (4, 9), (17, 21))
        self._trocar_letra(5, "h")
        self.assertEqual(self._marcas_depois_de_reabrir(), ["wlns"])
        self._trocar_letra(27, "n")
        self._so_sobra("wlns")

    def test_gravar_reabrir_e_corrigir_de_novo(self) -> None:
        from chess_diagram_ocr.text import arquivo

        self._folha("the wbite knight wlns a pawm", (4, 9), (17, 21))
        self._trocar_letra(5, "h")
        caminho = self.pasta / "folha.cvtxt"
        self.painel.caderno._salvar_documento_em(caminho)  # noqa: SLF001
        self.painel.desenhar_documento(arquivo.carregar(caminho))
        self._trocar_letra(27, "n")
        self._so_sobra("wlns")

    def test_shift_f7_nao_para_nos_pedacos_antes_de_gravar(self) -> None:
        self._folha("the wbite knight wlns a pawn", (4, 9), (17, 21))
        self._trocar_letra(5, "h")
        self.assertEqual(set(self._paradas()), {"wlns"})

    def test_duas_marcas_na_juncao_das_linhas_sao_duas(self) -> None:
        linhas = [
            pagina.LinhaLida(texto="the wbite", bbox=(0, 0, 9, 9), revisar_em=((4, 9),)),
            pagina.LinhaLida(texto="wlns a pawn", bbox=(0, 10, 9, 19), revisar_em=((0, 4),)),
        ]
        bloco = pagina.BlocoDeTexto.de_linhas(linhas)
        self.painel.mostrar_pagina(
            pagina.PaginaLida(pagina=0, colunas=(pagina.Coluna(indice=0, blocos=(bloco,)),), marca_por_palavra=True)
        )
        self.assertEqual(set(self._paradas()), {"wbite", "wlns"})
        self._trocar_letra(5, "h")
        self._so_sobra("wlns")

    def _faixa_no_bloco_inteiro(self) -> None:
        """Sem marca por palavra e com confiança baixa: quem leu o parágrafo para corrigi-lo já o conferiu."""
        linha = pagina.LinhaLida(texto="the wbite knight wlns a pawn", bbox=(0, 0, 9, 9), confianca=0.1, procedencia="glifo")
        bloco = pagina.BlocoDeTexto.de_linhas([linha])
        self.painel.mostrar_pagina(pagina.PaginaLida(pagina=0, colunas=(pagina.Coluna(indice=0, blocos=(bloco,)),)))
        self.assertTrue(rico.intervalos_a_revisar(self.painel.documento), "a faixa não veio: o teste não vigiaria nada")

    def test_a_faixa_do_bloco_inteiro_sai_com_uma_letra(self) -> None:
        self._faixa_no_bloco_inteiro()
        self._trocar_letra(5, "h")
        self.assertEqual(self._marcas_depois_de_reabrir(), [])

    def test_a_faixa_do_bloco_inteiro_sai_com_a_palavra_redigitada(self) -> None:
        """Aqui sobram palavras inteiras e intactas em volta, e elas não são marcas de palavra."""
        self._faixa_no_bloco_inteiro()
        self._cursor(4, 9)
        QTest.keyClicks(self.painel.editor, "white")
        self.assertEqual(self._marcas_depois_de_reabrir(), [])

    def test_a_faixa_do_bloco_inteiro_sai_com_a_palavra_e_os_espacos(self) -> None:
        """`the` sobra sozinha, sem espaço, e é a outra ponta que diz que aquilo é a faixa."""
        self._faixa_no_bloco_inteiro()
        self._cursor(3, 10)
        QTest.keyClicks(self.painel.editor, " white ")
        self.assertEqual(self._marcas_depois_de_reabrir(), [])

    def test_a_marca_que_sobra_com_o_resto_apagado_fica(self) -> None:
        self._folha("wlns pawn", (0, 4))
        self._cursor(4, 9)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Delete)
        self.assertEqual(self.painel.editor.toPlainText(), "wlns")
        self._so_sobra("wlns")

    def test_duas_marcas_vizinhas_que_a_juncao_de_hifen_uniu(self) -> None:
        """`camada.remapear` une o branco entre elas, em 17 de 414 folhas, e uma letra levava as marcas do bloco a 0."""
        self._folha("the wbite knigbt wins a pawn", (4, 16))
        self.assertEqual(set(self._paradas()), {"wbite", "knigbt"})
        self._trocar_letra(17, "v")
        self._so_sobra("wbite", "knigbt")

    def test_apagar_a_palavra_vizinha_nao_tira_a_marca(self) -> None:
        """Por caractere, `to a` casa com `to a` e `nd` com `nd`, e `and` atravessava dois trechos."""
        self._folha("to a and", (5, 8))
        self._cursor(3, 5)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Delete)
        self.assertEqual(self.painel.editor.toPlainText(), "to and")
        self._so_sobra("and")

    def test_inserir_uma_palavra_nao_tira_a_marca(self) -> None:
        self._folha("the knight wlns a pawn", (11, 15))
        self._cursor(4)
        QTest.keyClicks(self.painel.editor, "white ")
        self._so_sobra("wlns")

    def test_a_palavra_inteira_redigitada(self) -> None:
        self._folha("the wbite knight wlns a pawn", (4, 9), (17, 21))
        self._cursor(4, 9)
        QTest.keyClicks(self.painel.editor, "white")
        self._so_sobra("wlns")


if __name__ == "__main__":
    unittest.main()
