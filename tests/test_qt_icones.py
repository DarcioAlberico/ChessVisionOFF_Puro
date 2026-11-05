"""O ícone como `QIcon`, nos dois estados que o botão desenha (S-503/S-554).

**O que só existe deste lado.** A forma dos catorze traços é afirmada em `tests/test_ui_icones.py`,
sem toolkit nenhum. Aqui se mede a última perna, PIL -> Qt: que o `QIcon` leva **dois** desenhos --
o ligado e o desligado --, que o desligado apaga nas três peles em vez de clarear, e que ele usa a
mesma tinta com que a folha pinta a letra ao lado.

**Sob `offscreen` não há fonte**, então tudo aqui mede traço e fundo, e nenhum glifo.
"""

from __future__ import annotations

import re
import unittest

from qt_app import MOTIVO, TEM_PYQT, aplicacao, assentado, descartar, pixels_diferentes, tinta

from chess_diagram_ocr.ui import pele, tokens

if TEM_PYQT:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QToolButton

    from chess_diagram_ocr.qt import icones as qt_icones
    from chess_diagram_ocr.qt import tema

NOME = "promover"
"""Um traço qualquer da sala, e é de propósito que ele seja qualquer um: o item não é sobre este
ícone. É o que o crítico fotografou (`crit_r2/desab/foco_promover_on|off.png`)."""

LADO = 16
"""O lado que a barra da sala usa (`qt/barra_da_sala.LADO_DO_ICONE`)."""


def _cor_do_disabled(qss: str, seletor: str) -> str:
    """A cor que a folha dá à **letra** daquele controle desabilitado. Uma regra por linha, como
    as leituras de `tests/test_qt_tema.py`.

    O `(?<![-\\w])` não é zelo: sem ele o `background-color` da mesma regra casa primeiro, e a
    primeira versão deste teste comparou a tinta do ícone com a **face** do botão.
    """
    for linha in qss.splitlines():
        cabeca, _, resto = linha.partition("{")
        achada = re.search(r"(?<![-\w])color: (#[0-9a-f]{6})", resto)
        if cabeca.strip() == f"{seletor}:disabled" and achada:
            return achada.group(1)
    raise AssertionError(f"a folha não declara a letra de {seletor}:disabled")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class IconeDesabilitadoTests(unittest.TestCase):
    """O ícone desabilitado apaga, e apaga nas três peles (S-554).

    **O que o crítico mediu na janela de verdade, em 2026-09-04.** Na pele "Foco" o botão só com
    ícone desabilitado saía **idêntico** ao habilitado -- razão de contraste da tinta 9,47 dos dois
    lados, com a mesma contagem de traço. Onze dos catorze botões da barra da sala são só-ícone, e
    o critério de aceite da S-527 ("Variante e Exportar ficam cinza sem estudo") era vácuo ali.

    **E o desenho serve de prova, ao contrário da S-506.** Lá a fotografia do `offscreen` mentia
    (mostrava diferença onde o `windows11` não mostrava nenhuma). Aqui ela reproduz o defeito: sob
    `offscreen`, com o código de antes, a razão máxima da tinta do só-ícone **subia** de 13,41 para
    14,03 ao desabilitar na pele "Foco". A CI via o defeito, então ela pode cobrar a correção.
    """

    def setUp(self) -> None:
        self.app = aplicacao()
        anterior = self.app.styleSheet()
        self.addCleanup(self.app.setStyleSheet, anterior)
        self.addCleanup(qt_icones.limpar_cache)
        # A pele fica no módulo (`tema._cromo_escuro`): sem devolvê-la, o próximo teste da
        # suíte desenha na pele em que este parou. A limpeza roda ao contrário da ordem de
        # registro, então `aplicar_tema` vem antes de a folha de antes voltar.
        self.addCleanup(tema.aplicar_tema, self.app)

    def _botao(self, cor: str) -> QToolButton:
        """Um botão só-ícone como os onze da barra da sala, mostrado e do tamanho do traço."""
        botao = QToolButton()
        desenho = qt_icones.icone(NOME, LADO, cor)
        assert desenho is not None
        botao.setIcon(desenho)
        botao.setIconSize(qt_icones.tamanho(LADO))
        botao.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        botao.setProperty(tema.PROPRIEDADE_DE_NIVEL, tema.NIVEL_ICONE)
        botao.setAutoRaise(True)
        botao.setFixedSize(2 * LADO, 2 * LADO)
        botao.show()
        self.app.processEvents()
        self.addCleanup(descartar, botao)
        return botao

    def test_o_icone_leva_o_desenho_desligado_junto(self) -> None:
        """Sem ele o Qt gera o dele, que é o defeito: `QCommonStyle` remapeia os tons contra a
        paleta e desloca para o **claro** -- e numa pele escura clarear é destacar."""
        qt_icones.limpar_cache()
        desenho = qt_icones.icone(NOME, LADO, "#000000")
        assert desenho is not None
        ligado = desenho.pixmap(LADO, LADO, QIcon.Mode.Normal)
        desligado = desenho.pixmap(LADO, LADO, QIcon.Mode.Disabled)
        self.assertEqual(ligado.size(), desligado.size())
        self.assertNotEqual(
            ligado.toImage(), desligado.toImage(), "o desligado é o mesmo desenho do ligado"
        )

    def test_a_tinta_apagada_e_a_que_a_folha_da_a_letra_ao_lado(self) -> None:
        """**O item é o ícone e o rótulo apagarem juntos**, e juntos quer dizer pela mesma decisão.

        Duas decisões que hoje concordam são duas decisões que amanhã divergem sem ninguém ver: o
        rótulo apagaria e o desenho ao lado dele não.
        """
        for uma in pele.PELES:
            tema.aplicar_tema(self.app, cromo_escuro=uma.cromo_escuro, densidade=uma.densidade)
            qss = tema.folha_de_estilo(cromo_escuro=uma.cromo_escuro, densidade=uma.densidade)
            for seletor in ("QToolButton", "QPushButton"):
                with self.subTest(pele=uma.nome, seletor=seletor):
                    self.assertEqual(_cor_do_disabled(qss, seletor), qt_icones.tinta_apagada())

    def test_o_botao_so_com_icone_apaga_nas_tres_peles(self) -> None:
        """**É o caso que estava quebrado.** A tinta mais forte do traço tem de perder contraste
        contra a face -- e não ganhar, que é o que a pele escura fazia."""
        for uma in pele.PELES:
            tema.aplicar_tema(self.app, cromo_escuro=uma.cromo_escuro, densidade=uma.densidade)
            qt_icones.limpar_cache()
            face = tema.cor_atual(tokens.SUPERFICIE_PADRAO)
            botao = self._botao(tema.cor_atual(tokens.TEXTO_PADRAO))
            ligado = assentado(botao)
            botao.setEnabled(False)
            desligado = assentado(botao)
            traco_ligado, quantos = tinta(ligado, face)
            traco_desligado, _quantos = tinta(desligado, face)
            com_tinta = tokens.razao_de_contraste(traco_ligado, face)
            sem_tinta = tokens.razao_de_contraste(traco_desligado, face)
            with self.subTest(pele=uma.nome):
                self.assertGreater(quantos, 0, "o botão saiu sem traço nenhum: nada foi medido")
                self.assertGreater(
                    pixels_diferentes(ligado, desligado), 0, "ligado e desligado desenham igual"
                )
                self.assertLess(
                    sem_tinta,
                    com_tinta,
                    f"a tinta desabilitada não apagou: {com_tinta:.2f}:1 -> {sem_tinta:.2f}:1",
                )
                self.assertEqual(qt_icones.tinta_apagada(), traco_desligado)
            botao.setEnabled(True)

    def test_a_pele_faz_parte_da_chave_do_cache(self) -> None:
        """A tinta apagada vem da pele: o mesmo nome, tamanho e cor de traço em duas peles são
        **dois** desenhos, e devolver o guardado daria um ícone que apaga na cor da pele anterior."""
        qt_icones.limpar_cache()
        tema.aplicar_tema(self.app, cromo_escuro=False)
        claro = qt_icones.icone(NOME, LADO, "#000000")
        guardados = qt_icones.cache_de_icones()
        tema.aplicar_tema(self.app, cromo_escuro=True)
        escuro = qt_icones.icone(NOME, LADO, "#000000")
        self.assertGreater(qt_icones.cache_de_icones(), guardados, "a pele nova reusou o desenho velho")
        self.assertIsNot(claro, escuro)

    def test_nome_desconhecido_continua_devolvendo_nada(self) -> None:
        """A regra 4 não mudou: ícone que falta desenha um botão só com texto, e não uma exceção."""
        self.assertIsNone(qt_icones.icone("nao_existe", LADO, "#000000"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
