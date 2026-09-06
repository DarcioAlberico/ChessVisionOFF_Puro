"""O lote de diagramas na janela (S-544): escolhas, prévia, thread e a ação que o abre.

A decisão -- nome de arquivo, tamanho, pele, o que o lote contém -- é de
`ui/lote_de_diagramas.py` e já é afirmada em `tests/test_lote_de_diagramas.py`. O que só existe
aqui é o que atravessa a fronteira de thread, o que o diálogo liga, e o que a prévia desenha.

**A prévia é afirmada por tamanho e por mudança, e não por pixel de glifo**: sob `offscreen` não
há fonte, e a régua deste projeto para desenho é comparar dois desenhos (`qt_app.renderizar`).
"""

from __future__ import annotations

import unittest
from typing import Any

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.estudo import Ancora, Estudo, PosicaoDeEstudo
from chess_diagram_ocr.ui import conjuntos
from chess_diagram_ocr.ui.busy import BusyRegistry
from chess_diagram_ocr.ui.lote_de_diagramas import (
    PNG,
    SVG,
    TAMANHO_MAXIMO,
    TAMANHO_MINIMO,
    TAMANHO_PADRAO,
    UMA_TINTA,
    ItemDoLote,
)

if TEM_PYQT:
    from PyQt6.QtTest import QTest

    from chess_diagram_ocr.qt import painel_de_estudo as qt_estudo
    from chess_diagram_ocr.qt import tabuleiro as qt_tabuleiro
    from chess_diagram_ocr.qt.lote_de_diagramas import (
        LADO_DA_PREVIA,
        POR_MIL,
        DialogoDoLote,
        ExportacaoDoLote,
        previa,
    )

VAZIO = "8/8/8/8/8/8/8/K6k w - - 0 1"
INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"


def _itens(quantos: int = 4) -> list[ItemDoLote]:
    return [ItemDoLote(fen=VAZIO, livro="Livro", pagina=n + 1, diagrama=1) for n in range(quantos)]


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PreviaTests(unittest.TestCase):
    """A prévia responde "que figura vai sair", e não "de que tamanho"."""

    def setUp(self) -> None:
        self.app = aplicacao()

    def test_a_previa_cabe_no_quadrado_pedido_nos_dois_formatos(self) -> None:
        from chess_diagram_ocr.ui.lote_de_diagramas import Opcoes

        for formato in (PNG, SVG):
            with self.subTest(formato=formato):
                mapa = previa(ItemDoLote(fen=INICIAL + " w - - 0 1"), Opcoes(formato=formato), 120)
                self.assertFalse(mapa.isNull(), "a prévia não desenhou")
                self.assertLessEqual(max(mapa.width(), mapa.height()), 120)

    def test_a_previa_e_desenhada_no_tamanho_dela_e_nao_reduzida_do_final(self) -> None:
        """O conjunto de traço grosso existe para a peça **reduzida** (S-230): encolher um PNG de
        2.400 px mostraria a peça fina que o arquivo grande vai ter, não a que a tela promete."""
        from chess_diagram_ocr.ui.lote_de_diagramas import Opcoes

        grande = previa(ItemDoLote(fen=INICIAL + " w - - 0 1"), Opcoes(tamanho=TAMANHO_MAXIMO), 100)
        self.assertLessEqual(max(grande.width(), grande.height()), 100)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DialogoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.dialogo = DialogoDoLote(itens=_itens(), pasta=self.pasta)
        self.addCleanup(descartar, self.dialogo)
        self.addCleanup(self.dialogo.exportacao.esperar, 10_000)

    def _esperar(self, ate_ms: int = 10_000) -> None:
        for _ in range(ate_ms // 20):
            QTest.qWait(20)
            if not self.dialogo.exportacao.ocupado:
                return

    def test_as_escolhas_da_tela_viram_as_opcoes(self) -> None:
        self.dialogo.cmb_formato.setCurrentIndex(self.dialogo.cmb_formato.findData(SVG))
        self.dialogo.cmb_pele.setCurrentIndex(self.dialogo.cmb_pele.findData(UMA_TINTA))
        self.dialogo.chk_plaqueta.setChecked(False)
        self.dialogo.spn_margem.setValue(25)
        escolhas = self.dialogo.opcoes()
        self.assertEqual(SVG, escolhas.formato)
        self.assertEqual(UMA_TINTA, escolhas.pele)
        self.assertFalse(escolhas.plaqueta)
        self.assertEqual(25, escolhas.margem)

    def test_o_tamanho_digitado_e_aparado_na_faixa(self) -> None:
        """`TAMANHOS` sempre declarou "continua aceitando qualquer valor da faixa", e uma caixa
        fechada em oito valores fazia a declaração mentir. Aparar e não recusar: quem digita
        40000 quer o maior que houver."""
        for digitado, esperado in (("900", 900), ("40000", TAMANHO_MAXIMO), ("2", TAMANHO_MINIMO), ("", TAMANHO_PADRAO)):
            with self.subTest(digitado=digitado):
                self.dialogo.cmb_tamanho.setCurrentText(digitado)
                self.assertEqual(esperado, self.dialogo.tamanho_pedido())

    def test_a_caixa_comeca_no_tamanho_e_no_conjunto_que_a_janela_usa(self) -> None:
        """Quem trocou as peças da tela quer as mesmas peças no arquivo."""
        anterior = qt_tabuleiro.conjunto_em_vigor()
        self.addCleanup(qt_tabuleiro.definir_conjunto, anterior)
        qt_tabuleiro.definir_conjunto(conjuntos.TRACO)
        outro = DialogoDoLote(itens=_itens(1), pasta=self.pasta)
        self.addCleanup(descartar, outro)
        self.assertEqual(conjuntos.TRACO, outro.opcoes().conjunto)
        self.assertEqual(TAMANHO_PADRAO, outro.tamanho_pedido())

    def test_o_conjunto_de_pecas_fica_cinza_no_svg_e_a_tela_diz_por_que(self) -> None:
        """O SVG desenha as peças do `python-chess`, que são caminho: dizê-lo é melhor que
        desabilitar a caixa em silêncio."""
        self.dialogo.cmb_formato.setCurrentIndex(self.dialogo.cmb_formato.findData(SVG))
        self.assertFalse(self.dialogo.cmb_conjunto.isEnabled())
        self.assertIn("vetoriais", self.dialogo.lbl_resumo.text())
        self.dialogo.cmb_formato.setCurrentIndex(self.dialogo.cmb_formato.findData(PNG))
        self.assertTrue(self.dialogo.cmb_conjunto.isEnabled())

    def test_mudar_uma_escolha_redesenha_a_previa(self) -> None:
        """A caixa de tamanho é editável, e o índice não muda quando se digita: sem o
        `editTextChanged` a prévia continuaria mostrando o tamanho anterior."""
        antes = self.dialogo.lbl_previa.pixmap().toImage()
        self.dialogo.cmb_pele.setCurrentIndex(self.dialogo.cmb_pele.findData(UMA_TINTA))
        depois = self.dialogo.lbl_previa.pixmap().toImage()
        self.assertNotEqual(antes, depois, "a pele mudou e a prévia não")
        self.assertEqual(LADO_DA_PREVIA, self.dialogo.lbl_previa.width())

    def test_sem_diagrama_nao_ha_previa_nem_botao(self) -> None:
        vazio = DialogoDoLote(itens=[], pasta=self.pasta)
        self.addCleanup(descartar, vazio)
        self.assertFalse(vazio.botao_exportar.isEnabled())
        self.assertIn("Nenhum", vazio.lbl_resumo.text())

    def test_exportar_grava_os_arquivos_e_a_barra_chega_ao_fim(self) -> None:
        self.dialogo.cmb_tamanho.setCurrentText("240")
        self.assertTrue(self.dialogo.exportar())
        self._esperar()
        self.assertEqual(4, len(list(self.pasta.glob("*.png"))))
        self.assertEqual(POR_MIL, self.dialogo.barra.value())
        self.assertIn(str(self.pasta), self.dialogo.lbl_resumo.text())

    def test_o_botao_de_exportar_fica_cinza_enquanto_grava(self) -> None:
        self.dialogo.cmb_tamanho.setCurrentText("240")
        self.dialogo.exportar()
        self.assertFalse(self.dialogo.botao_exportar.isEnabled())
        self.assertTrue(self.dialogo.botao_cancelar.isEnabled())
        self._esperar()
        self.assertTrue(self.dialogo.botao_exportar.isEnabled())
        self.assertFalse(self.dialogo.botao_cancelar.isEnabled())

    def test_duas_rodadas_ao_mesmo_tempo_sao_recusadas(self) -> None:
        """Duas escreveriam na mesma pasta e disputariam os mesmos núcleos -- é a recusa da fila
        de livros, pelo mesmo motivo."""
        self.dialogo.cmb_tamanho.setCurrentText("240")
        self.assertTrue(self.dialogo.exportar())
        self.assertFalse(self.dialogo.exportar())
        self._esperar()


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class ExportacaoTests(unittest.TestCase):
    """A travessia: o aviso vem da thread de trabalho e chega como sinal."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.registro = BusyRegistry()
        self.exportacao = ExportacaoDoLote(busy=self.registro)
        self.addCleanup(descartar, self.exportacao)
        self.addCleanup(self.exportacao.esperar, 10_000)

    def _esperar(self, ate_ms: int = 10_000) -> None:
        for _ in range(ate_ms // 20):
            QTest.qWait(20)
            if not self.exportacao.ocupado:
                return

    def test_o_progresso_chega_por_sinal_e_termina_no_total(self) -> None:
        from chess_diagram_ocr.ui.lote_de_diagramas import Opcoes

        andou: list[tuple[int, int]] = []
        self.exportacao.andou.connect(lambda feitos, total, _nome: andou.append((feitos, total)))
        self.assertTrue(self.exportacao.iniciar(_itens(5), Opcoes(tamanho=240), self.pasta))
        self._esperar()
        self.assertEqual((5, 5), andou[-1])
        assert self.exportacao.relatorio is not None
        self.assertEqual(5, len(self.exportacao.relatorio.gravados))
        self.assertGreater(self.exportacao.relatorio.por_segundo, 0.0)

    def test_lote_vazio_nao_comeca(self) -> None:
        from chess_diagram_ocr.ui.lote_de_diagramas import Opcoes

        self.assertFalse(self.exportacao.iniciar([], Opcoes(), self.pasta))

    def test_o_registro_de_ocupacao_diz_que_nada_se_perde_ao_fechar(self) -> None:
        """Cada arquivo pronto já está no disco: fechar custa o que falta, não o que já saiu.

        A frase importa: "o progresso já está salvo" e "descarta o progresso" treinam respostas
        diferentes, e prometer perda onde não há ensina a clicar em "sim" sem ler (S-112)."""
        from chess_diagram_ocr.ui.lote_de_diagramas import Opcoes

        vistos: list[Any] = []
        self.exportacao.andou.connect(lambda *_a: vistos.append(self.registro.running()))
        avisos: list[str] = []
        self.exportacao.andou.connect(lambda *_a: avisos.append(self.registro.close_warning()))
        self.exportacao.iniciar(_itens(4), Opcoes(tamanho=240), self.pasta)
        self._esperar()
        self.assertTrue(vistos, "a exportação não avisou nem uma vez")
        for rodando in vistos:
            self.assertTrue(rodando, "a exportação não se registrou como ocupada")
            self.assertFalse(any(operacao.loses_work for operacao in rodando))
            self.assertTrue(all(operacao.cancellable for operacao in rodando))
        self.assertTrue(all("já está salvo" in aviso for aviso in avisos))
        self.assertEqual("", self.registro.close_warning(), "o registro ficou ocupado depois do fim")

    def test_cancelar_para_e_o_que_saiu_fica_gravado(self) -> None:
        from chess_diagram_ocr.ui.lote_de_diagramas import Opcoes

        self.exportacao.andou.connect(lambda feitos, *_a: self.exportacao.cancelar() if feitos >= 2 else None)
        self.exportacao.iniciar(_itens(40), Opcoes(tamanho=240), self.pasta)
        self._esperar(3_000)
        self.assertFalse(self.exportacao.ocupado, "a thread não parou em um segundo e meio")
        assert self.exportacao.relatorio is not None
        self.assertTrue(self.exportacao.relatorio.cancelado)
        self.assertGreater(len(list(self.pasta.glob("*.png"))), 0)
        self.assertLess(len(list(self.pasta.glob("*.png"))), 40)


def _estudo(*, ancora: Ancora = Ancora()) -> Estudo:
    return Estudo.de_posicao(PosicaoDeEstudo(placement=INICIAL, vez="w", ancora=ancora))


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class AcaoDaSalaTests(unittest.TestCase):
    """A ação de menu abre o diálogo **com os diagramas certos dentro** -- é o efeito, e não a
    existência do método, que o comando promete."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.painel = qt_estudo.PainelDeEstudo(pasta_inicial=self.pasta, pasta_de_estudos=self.pasta)
        self.addCleanup(descartar, self.painel)

    def test_o_comando_do_catalogo_tem_o_metodo_deste_painel(self) -> None:
        from chess_diagram_ocr.ui.sala_declarada import COMANDOS_DA_ABA

        for acao in ("exportar_diagramas_lote", "imprimir_estudo", "exportar_estudo_pdf"):
            with self.subTest(acao=acao):
                self.assertTrue(callable(getattr(self.painel, COMANDOS_DA_ABA[acao])))

    def test_sem_sala_o_lote_e_o_estudo_aberto(self) -> None:
        dialogo = self.painel.exportar_diagramas_em_lote()
        self.addCleanup(descartar, dialogo)
        self.assertEqual(1, len(dialogo.itens), "o diagrama da raiz")
        self.assertIn("estudo aberto", dialogo.lbl_origem.text())

    def test_com_sala_o_lote_e_a_sala_inteira(self) -> None:
        """A sala *é* o conjunto de diagramas deste livro (S-270), e é ele que quem diagrama
        noutro programa quer."""
        self.painel.sala.documento = "C:/PDF/Secrets.pdf"
        for pagina in range(3):
            estudo = _estudo(ancora=Ancora(documento="C:/PDF/Secrets.pdf", pagina=pagina, diagrama=0))
            estudo.no = estudo.no.add_main_variation(next(iter(estudo.tabuleiro.legal_moves)))
            self.assertTrue(self.painel.sala.guardar(estudo))
        dialogo = self.painel.exportar_diagramas_em_lote()
        self.addCleanup(descartar, dialogo)
        self.assertEqual(3, len(dialogo.itens))
        self.assertEqual({"Secrets"}, {item.livro for item in dialogo.itens})
        self.assertEqual((1, 2, 3), tuple(item.pagina for item in dialogo.itens))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
