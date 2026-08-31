"""A fita do segundo frontend, gerada do mesmo catálogo (S-227/S-228/S-503).

**O que estes testes cobrem, e o que não.** A conta da altura, a quebra do rótulo, os grupos e o
orçamento são puros e já são afirmados em `tests/test_ui_fita.py`. Repetir aquilo aqui mediria o
mesmo código duas vezes.

O que só existe deste lado são as quatro coisas em que o Qt difere do Tk e que quebram calado:

1. **O evento de redimensionamento só chega a widget visível.** Uma fita montada como filha de um
   pai que ninguém mostrou nunca troca de modo, e o teste que a montasse assim mediria o modo
   inicial achando que mediu a troca. Ver `fita_variavel`.
2. **`QToolButton` e não `QPushButton`**: só o primeiro põe o ícone acima do texto, que é a forma
   da Imagem 2. Um `QPushButton` desenharia a fita plena como a compacta com o cabeçalho de volta.
3. **A altura medida é do cromo do Qt**, e não do `ttk.Button` de que saíram as três medidas de
   `ui/medidas_da_fita.py`. O que os dois lados têm em comum é o **orçamento**, e é contra ele que
   este arquivo cobra.
4. **O ícone tem de ser pedido no tamanho em que vai ser desenhado.** Um `QIcon` a que se pede um
   tamanho que ele não tem devolve o mais próximo esticado, e o traço de 9% vira mancha.
"""

from __future__ import annotations

import unittest

from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.ui import medidas_da_fita

if TEM_PYQT:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel, QToolButton, QWidget

    from chess_diagram_ocr.qt import fita as qt_fita
    from chess_diagram_ocr.qt import icones as qt_icones

AMARRADOS = {acao: (lambda: None) for acao in medidas_da_fita.acoes_da_fita()}


class DeclaracaoTests(unittest.TestCase):
    """A decisão é a mesma dos dois lados, e nenhum dos dois a reescreve."""

    def test_o_modulo_puro_nao_carrega_tkinter(self) -> None:
        """É a razão de ele existir: `Fita` herda de `ttk.Frame` pela `BarraFluida`, e classe-base
        é avaliada na importação -- então ler o orçamento pelo módulo antigo carrega o Tk junto."""
        import ast
        from pathlib import Path

        arvore = ast.parse(Path(medidas_da_fita.__file__).read_text(encoding="utf-8"))
        importados = {no.names[0].name.split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.Import)}
        importados |= {(no.module or "").split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom)}
        self.assertNotIn("tkinter", importados)

    @unittest.skipUnless(TEM_PYQT, MOTIVO)
    def test_a_conta_da_altura_e_a_mesma_nos_dois(self) -> None:
        """Um segundo modelo de altura faria as duas janelas trocarem de modo em larguras
        diferentes -- que é a mesma fita se comportando de dois jeitos."""
        self.assertIs(qt_fita.altura_da_fita, medidas_da_fita.altura_da_fita)
        self.assertIs(qt_fita.ORCAMENTO, medidas_da_fita.ORCAMENTO)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class MontagemTests(unittest.TestCase):
    """A fita desenhada, nos dois modos cravados."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.addCleanup(self.app.processEvents)

    def fita(self, modo: str, **kwargs: object) -> qt_fita.Fita:
        montada = qt_fita.montar(None, AMARRADOS, modo=modo, **kwargs)  # type: ignore[arg-type]
        self.addCleanup(descartar, montada)
        montada.show()
        self.app.processEvents()
        return montada

    def test_nenhum_modo_descarta_comando(self) -> None:
        """O critério que a troca de modo poderia quebrar em silêncio."""
        for modo in medidas_da_fita.MODOS:
            with self.subTest(modo=modo):
                desenhadas = self.fita(modo).acoes_desenhadas
                self.assertEqual(desenhadas, medidas_da_fita.acoes_da_fita())

    def test_a_altura_medida_cabe_no_orcamento(self) -> None:
        """O número que a S-228 declarou, cobrado do widget do Qt -- que tem o cromo dele."""
        for modo in medidas_da_fita.MODOS:
            with self.subTest(modo=modo):
                fita = self.fita(modo)
                self.assertLessEqual(fita.altura_medida(), medidas_da_fita.ORCAMENTO[modo])

    def test_o_compacto_e_mais_baixo_e_mais_largo_que_o_pleno(self) -> None:
        """O achado da S-228 medido no outro toolkit: o rótulo sai de baixo do ícone e vai para o
        lado dele, e **o que era altura vira largura**. É a razão de o rótulo continuar em duas
        linhas no modo que existe para caber."""
        pleno, compacto = self.fita(medidas_da_fita.PLENO), self.fita(medidas_da_fita.COMPACTO)
        self.assertLess(compacto.altura_medida(), pleno.altura_medida())
        self.assertGreater(compacto.sizeHint().width(), pleno.sizeHint().width())

    def test_o_pleno_poe_o_icone_acima_e_o_compacto_ao_lado(self) -> None:
        """`QToolButton` e não `QPushButton`: só ele sabe `ToolButtonTextUnderIcon`."""
        acao = medidas_da_fita.acoes_da_fita()[0]
        acima = self.fita(medidas_da_fita.PLENO).botao(acao)
        ao_lado = self.fita(medidas_da_fita.COMPACTO).botao(acao)
        self.assertIsInstance(acima, QToolButton)
        self.assertEqual(acima.toolButtonStyle(), Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.assertEqual(ao_lado.toolButtonStyle(), Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

    def test_o_icone_e_pedido_no_tamanho_em_que_vai_ser_desenhado(self) -> None:
        """Um `QIcon` esticado de 20 para 32 transforma o traço de 9% numa mancha."""
        for modo, lado in medidas_da_fita.LADO_DO_ICONE.items():
            with self.subTest(modo=modo):
                botao = self.fita(modo).botao("ler_pagina")
                self.assertEqual(botao.iconSize(), qt_icones.tamanho(lado))
                self.assertIn(qt_icones.tamanho(lado), botao.icon().availableSizes())

    def test_o_cabecalho_do_grupo_vira_dica_no_compacto(self) -> None:
        """Ele custa uma linha de texto por fita, e no compacto essa linha é a diferença entre
        caber e competir com a página. O nome do grupo não se perde."""
        grupo = medidas_da_fita.grupos()[0]
        acao = grupo.itens[0].acao

        pleno = self.fita(medidas_da_fita.PLENO)
        cabecalhos = {rotulo.text() for rotulo in pleno.findChildren(QLabel)}
        self.assertIn(grupo.rotulo, cabecalhos)
        self.assertNotIn(grupo.rotulo, pleno.botao(acao).toolTip())

        compacto = self.fita(medidas_da_fita.COMPACTO)
        self.assertNotIn(grupo.rotulo, {rotulo.text() for rotulo in compacto.findChildren(QLabel)})
        self.assertIn(grupo.rotulo, compacto.botao(acao).toolTip())

    def test_a_tecla_vai_na_dica_quando_existe(self) -> None:
        from chess_diagram_ocr.ui import atalhos

        botao = self.fita(medidas_da_fita.PLENO).botao("ler_pagina")
        self.assertIn(atalhos.acelerador("ler_pagina"), botao.toolTip())

    def test_o_rotulo_quebra_pela_funcao_pura(self) -> None:
        """O `QToolButton` não quebra sozinho: quem reparte é `quebrar_rotulo`, como no Tk."""
        from chess_diagram_ocr.ui import comandos

        fita = self.fita(medidas_da_fita.PLENO)
        for acao in fita.acoes_desenhadas:
            with self.subTest(acao=acao):
                esperado = medidas_da_fita.quebrar_rotulo(comandos.comando(acao).no_botao)
                self.assertEqual(fita.botao(acao).text(), esperado)

    def test_comando_sem_funcao_levanta_nomeando(self) -> None:
        """Um botão grande, com ícone e rótulo, que não faz nada é pior que a ausência dele."""
        faltando = medidas_da_fita.acoes_da_fita()[0]
        parcial = {acao: (lambda: None) for acao in medidas_da_fita.acoes_da_fita()[1:]}
        with self.assertRaises(KeyError) as capturado:
            qt_fita.montar(None, parcial)
        self.assertIn(faltando, str(capturado.exception))

    def test_botao_de_comando_que_a_fita_nao_desenha_levanta(self) -> None:
        with self.assertRaises(KeyError):
            self.fita(medidas_da_fita.PLENO).botao("sair")

    def test_modo_e_densidade_desconhecidos_levantam(self) -> None:
        """Um modo escrito errado que caísse no pleno devolveria um número plausível para o
        orçamento errado."""
        with self.assertRaises(KeyError):
            qt_fita.montar(None, AMARRADOS, modo="medio")
        with self.assertRaises(KeyError):
            qt_fita.montar(None, AMARRADOS, densidade="apertada")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class TrocaDeModoTests(unittest.TestCase):
    """O limiar é medido, e não escolhido: é a largura que a fita plena pede em uma linha."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.addCleanup(self.app.processEvents)

    def fita_variavel(self) -> qt_fita.Fita:
        """A fita sem modo cravado, montada **como janela** e não como filha.

        O `QResizeEvent` só chega a widget visível, e um filho de um pai que ninguém mostrou nunca
        é visível -- então uma fita montada assim não trocaria de modo nunca, e o teste mediria o
        modo inicial achando que mediu a troca. É o parente Qt do defeito que a S-117 registrou no
        Tk: o evento que não chega deixa o teste verde pelo caminho errado.
        """
        fita = qt_fita.montar(None, AMARRADOS)
        self.addCleanup(descartar, fita)
        fita.show()
        self.app.processEvents()
        return fita

    def largura(self, fita: qt_fita.Fita, pixels: int) -> str:
        fita.resize(pixels, 200)
        self.app.processEvents()
        return fita.modo

    def test_o_limiar_e_a_largura_que_a_plena_pede(self) -> None:
        """**A fita nasce compacta**, e o teste tem de alargá-la antes de medir a descida.

        Não é defeito: o primeiro `QResizeEvent` chega com o tamanho de fábrica da janela, que é
        menor que o limiar, e a histerese impede a volta ao pleno até `troca + HISTERESE`. Um
        teste que medisse a partir do estado inicial mediria a histerese achando que mediu o
        limiar -- e passaria a falhar no dia em que alguém trocasse o tamanho de fábrica.
        """
        fita = self.fita_variavel()
        troca = fita.largura_de_troca
        self.assertGreater(troca, 0, "sem o limiar medido a fita nunca entraria em compacto")
        self.largura(fita, troca + medidas_da_fita.HISTERESE)
        self.assertEqual(fita.modo, medidas_da_fita.PLENO)
        self.assertEqual(self.largura(fita, troca), medidas_da_fita.PLENO)
        self.assertEqual(self.largura(fita, troca - 1), medidas_da_fita.COMPACTO)

    def test_a_histerese_impede_a_troca_no_mesmo_pixel(self) -> None:
        """Sem ela, uma janela arrastada na vizinhança do limiar destrói e recria dezessete
        botões a cada pixel de tremor."""
        fita = self.fita_variavel()
        troca = fita.largura_de_troca
        self.largura(fita, troca - 1)
        self.assertEqual(self.largura(fita, troca), medidas_da_fita.COMPACTO)
        self.assertEqual(
            self.largura(fita, troca + medidas_da_fita.HISTERESE), medidas_da_fita.PLENO
        )

    def test_a_troca_de_modo_nao_perde_comando(self) -> None:
        fita = self.fita_variavel()
        troca = fita.largura_de_troca
        for pixels in (troca - 1, troca + medidas_da_fita.HISTERESE, troca - 1):
            with self.subTest(largura=pixels):
                self.largura(fita, pixels)
                self.assertEqual(fita.acoes_desenhadas, medidas_da_fita.acoes_da_fita())

    def test_densidade_compacta_crava_o_modo(self) -> None:
        """O modo é decidido pela largura e a densidade é decidida pela pessoa: quando ela pede
        compacta, um monitor largo não pode devolver o ícone de 32 px (S-232)."""
        from chess_diagram_ocr.ui import pele

        fita = qt_fita.montar(None, AMARRADOS, densidade=pele.COMPACTA)
        self.addCleanup(descartar, fita)
        fita.show()
        self.assertEqual(self.largura(fita, 4000), medidas_da_fita.COMPACTO)

    def test_o_grupo_nunca_quebra_por_dentro(self) -> None:
        """A unidade de quebra é o grupo: um grupo partido ao meio não é um grupo (S-227).

        **A afirmação é de faixa vertical, e não de topo igual**, e a diferença foi medida. Os
        botões de um grupo não têm todos a mesma altura -- "Ler" cabe numa linha e "Selecionar
        área" em duas --, e o `QHBoxLayout` centra os mais baixos. Comparar o topo acusaria quebra
        onde há só alinhamento; o que caracteriza a quebra é a faixa de um botão não encostar na
        do outro, e é isso que se pergunta.

        O caso que ele pegou é real: com a `BarraFluida` na fila de dentro -- que era como este
        módulo começou --, a fita a 400 px punha dois dos quatro grupos em duas linhas cada, e o
        que o olho lia eram sete grupos.
        """
        fita = self.fita_variavel()
        self.largura(fita, 400)
        grupos = fita.findChildren(QWidget, "grupo-da-fita")
        self.assertEqual(len(grupos), len(medidas_da_fita.grupos()))
        for grupo in grupos:
            with self.subTest(grupo=grupo.findChildren(QToolButton)[0].text()):
                faixas = [
                    (botao.mapTo(grupo, botao.rect().topLeft()).y(), botao.height())
                    for botao in grupo.findChildren(QToolButton)
                ]
                self.assertLess(
                    max(topo for topo, _ in faixas),
                    min(topo + altura for topo, altura in faixas),
                    "os botões do grupo não compartilham nenhuma linha de pixel",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
