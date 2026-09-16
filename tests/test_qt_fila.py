"""A fila de ações em destaque da pele "Foco" (S-223/S-506), pelo que só o Qt sabe responder.

**O que este arquivo cobra, e por que ele nasceu no ciclo 10.** A decisão de *quem* está na fila
é pura e já é afirmada em `tests/test_ui_comandos.py` (`fila_de_destaque`); repeti-la aqui mediria
o mesmo código duas vezes. O que só existe deste lado é **o que a pílula anuncia**.

O crítico do ciclo 9 reprovou este frontend porque o portão de teclado media **uma** das três
peles. Rodado nas outras duas, a `foco` devolvia dois controles anunciando `"Próximo diagrama"` na
aba Galeria sem nada que os distinguisse -- a pílula do cromo e o botão do painel, o mesmo comando
desenhado nos dois lugares de propósito. `qt/fila.py` não chamava `setAccessibleName` e não se
anunciava como região; as duas linhas que faltavam estão aqui cobradas.
"""

from __future__ import annotations

import unittest

from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.ui import comandos

if TEM_PYQT:
    from PyQt6.QtWidgets import QWidget

    from chess_diagram_ocr.qt import fila as qt_fila


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class NomeDaPilulaTests(unittest.TestCase):
    """O que um leitor de tela ouve ao chegar numa pílula da pele Foco."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pai = QWidget()
        self.addCleanup(descartar, self.pai)
        amarrados = {acao: (lambda: None) for acao in qt_fila.acoes_da_fila()}
        self.fila = qt_fila.montar(self.pai, amarrados)

    def test_toda_pilula_anuncia_o_rotulo_por_extenso(self) -> None:
        """**O nome acessível é o rótulo por extenso, e não o texto do botão** (F9-C2/F9-C9).

        Nenhum comando em destaque tem rótulo de glifo hoje, então o número desta pele não muda
        com esta linha; o que muda é que ele deixa de depender disso. A pílula que amanhã
        mostrasse `▶` chegaria ao leitor de tela como "Próximo lance" em vez de repor, numa
        terceira montagem, o defeito nº 1 do ciclo 1.
        """
        for acao, botao in self.fila.botoes.items():
            with self.subTest(acao=acao):
                self.assertEqual(botao.accessibleName(), comandos.nome_acessivel(acao))

    def test_a_fila_se_anuncia_como_regiao(self) -> None:
        """`qt/painel_do_pdf._bloco` nomeia o contêiner desde o ciclo 2, *"sem ele a pessoa ouve
        doze botões seguidos sem saber onde um grupo acaba"*. A fila não nomeava o dela, e por
        isso a pílula `Ler esta página` chegava indistinguível do botão do painel que faz o
        mesmo -- dois controles com o mesmo anúncio, em **cada uma das seis abas**.
        """
        self.assertEqual(self.fila.accessibleName(), qt_fila.REGIAO)
        self.assertTrue(any(letra.isalpha() for letra in qt_fila.REGIAO))

    def test_nenhum_nome_da_fila_carrega_quebra_de_linha(self) -> None:
        """Uma quebra de linha num nome acessível é o leiaute vazando para o anúncio."""
        com_quebra = [
            acao for acao, botao in self.fila.botoes.items() if "\n" in botao.accessibleName()
        ]
        self.assertEqual([], com_quebra)

    def test_a_pilula_de_glifo_nao_desenharia_o_glifo_ao_lado_do_icone(self) -> None:
        """A regra é do catálogo (`Comando.so_glifo`) e vale nos três cromos.

        Hoje a fila não tem comando de glifo -- este teste afirma a **regra**, montando a pílula
        de um comando de glifo do catálogo pelo mesmo caminho que a fila usa. Sem ele, a fila
        seria o próximo lugar em que o defeito da fita reaparece, e ninguém olharia.
        """
        de_glifo = [
            registro for registro in comandos.CATALOGO if registro.so_glifo and registro.icone
        ]
        self.assertTrue(de_glifo, "o catálogo deixou de ter comando de glifo com ícone")
        for registro in de_glifo:
            with self.subTest(acao=registro.acao):
                self.fila._amarrados[registro.acao] = lambda: None
                botao = self.fila._pilula(registro)
                self.addCleanup(descartar, botao)
                self.assertEqual(botao.text(), "")
                self.assertTrue(botao.icon().availableSizes())
                self.assertEqual(botao.accessibleName(), comandos.nome_acessivel(registro.acao))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
