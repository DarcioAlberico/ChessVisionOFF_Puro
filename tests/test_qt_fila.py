"""A fila de ações em destaque da pele "Foco" no segundo frontend (S-223/S-506/S-522), pelo que só
o Qt sabe responder: pílulas por ação, o separador entre grupos e o que cada pílula anuncia.

**O que só existe deste lado.** Quem está na fila e como ela se agrupa é `comandos.fila_de_destaque`,
pura e já afirmada em `tests/test_ui_comandos.py`; repeti-la aqui mediria o mesmo código duas vezes.
O que se afirma aqui é a tradução -- cada registro virando pílula, cada fronteira de grupo virando um
traço --, a **cor** do traço e **o que a pílula anuncia**.

**A cor do traço (S-522)** é onde o retrato desmentiu a forma óbvia: o `QFrame.VLine` desenha com a
cor de texto da paleta, e não com a da folha. O separador é pintado pela folha, e por isso o `grab()`
sob `offscreen` mede o que o produto desenha -- ao contrário da moldura dos controles, que é do
estilo da plataforma.

**O anúncio, e por que ele é cobrado desde o ciclo 10.** O crítico do ciclo 9 reprovou este
frontend porque o portão de teclado media **uma** das três peles. Rodado nas outras duas, a `foco`
devolvia dois controles anunciando `"Próximo diagrama"` na aba Galeria sem nada que os distinguisse
-- a pílula do cromo e o botão do painel, o mesmo comando desenhado nos dois lugares de propósito.
`qt/fila.py` não chamava `setAccessibleName` e não se anunciava como região; as duas linhas que
faltavam estão aqui cobradas.
"""

from __future__ import annotations

import unittest

from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.ui import comandos, tokens

if TEM_PYQT:
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import QWidget

    from chess_diagram_ocr.qt import fila, tema


def _hexa(imagem: object, x: int, y: int) -> str:
    return QColor(imagem.pixel(x, y)).name()  # type: ignore[attr-defined]


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class FilaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        # A folha é da aplicação inteira: o que este teste aplica, ele devolve à clássica.
        self.addCleanup(tema.aplicar_tema, self.app)

    def _fila(self, *, cromo_escuro: bool = False) -> fila.Fila:
        tema.aplicar_tema(self.app, cromo_escuro=cromo_escuro)
        montada = fila.montar(None, {acao: (lambda: None) for acao in fila.acoes_da_fila()})
        self.addCleanup(descartar, montada)
        return montada

    def test_toda_acao_em_destaque_vira_pilula(self) -> None:
        self.assertEqual(set(fila.acoes_da_fila()), set(self._fila().botoes))

    def test_comando_sem_funcao_levanta_nomeando_o_que_falta(self) -> None:
        """Uma pílula com ícone que não faz nada é pior que a ausência dela (S-223)."""
        acoes = fila.acoes_da_fila()
        amarrados = {acao: (lambda: None) for acao in acoes[1:]}
        with self.assertRaises(KeyError) as erro:
            fila.montar(None, amarrados)
        self.assertIn(acoes[0], str(erro.exception))

    def test_ha_um_separador_entre_grupos_e_nenhum_na_ponta(self) -> None:
        montada = self._fila()
        separadores = montada.findChildren(QWidget, tema.ID_DO_SEPARADOR)
        self.assertEqual(len(comandos.fila_de_destaque()) - 1, len(separadores))

    def test_o_separador_e_um_pixel_da_moldura_do_cromo_nas_duas_peles(self) -> None:
        """Medido no `windows11` antes: 2 px em `#848688`, a cor de texto da paleta, mais claro que
        a borda das pílulas. Agora é 1 px da moldura derivada da superfície, e a mesma nas duas
        peles porque o valor sai de `tokens.moldura_sobre` e não de um número escrito."""
        for cromo_escuro in (False, True):
            with self.subTest(cromo_escuro=cromo_escuro):
                montada = self._fila(cromo_escuro=cromo_escuro)
                montada.resize(1600, 48)
                montada.show()
                self.app.processEvents()
                imagem = montada.grab().toImage()
                separador = montada.findChildren(QWidget, tema.ID_DO_SEPARADOR)[0]
                origem = separador.mapTo(montada, QPoint(0, 0))
                y = origem.y() + separador.height() // 2
                superficie = tema.cor_atual(tokens.SUPERFICIE_PADRAO)
                esperada = tokens.moldura_sobre(superficie)

                self.assertEqual(1, separador.width())
                self.assertGreater(separador.height(), 8, "o traço não ocupa a altura da fila")
                self.assertEqual(esperada, _hexa(imagem, origem.x(), y))
                self.assertEqual(superficie, _hexa(imagem, origem.x() - 3, y), "o vizinho não é a superfície")
                self.assertEqual(superficie, _hexa(imagem, origem.x() + 3, y))
                self.assertGreaterEqual(tokens.razao_de_contraste(esperada, superficie), tokens.AA_GRAFICO)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class NomeDaPilulaTests(unittest.TestCase):
    """O que um leitor de tela ouve ao chegar numa pílula da pele Foco."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pai = QWidget()
        self.addCleanup(descartar, self.pai)
        amarrados = {acao: (lambda: None) for acao in fila.acoes_da_fila()}
        self.fila = fila.montar(self.pai, amarrados)

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
        self.assertEqual(self.fila.accessibleName(), fila.REGIAO)
        self.assertTrue(any(letra.isalpha() for letra in fila.REGIAO))

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
