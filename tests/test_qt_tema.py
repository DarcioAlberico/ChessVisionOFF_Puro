"""O tema do segundo frontend: a folha de estilo, a paleta e o papel do botão (S-501).

**O que estes testes cobrem, e o que não.** A paleta em si já é afirmada em
`tests/test_ui_tokens.py` -- contraste, matiz, as três peles -- e a escala de fonte e de espaço
em `tests/test_ui_tipografia.py` e `tests/test_ui_folha.py`. Repetir aquilo aqui mediria o mesmo
código duas vezes.

O que só existe deste lado é a **tradução**: papel de cor virando regra de QSS, classe de
`ui/folha.py` virando seletor de Qt, e papel de botão virando propriedade dinâmica. É onde os
dois frontends podem divergir sem que ninguém perceba, e é o que está abaixo.

**Quase tudo aqui roda sem `QApplication`**, e não é economia: `folha_de_estilo` é pura de
propósito, e um teste de aparência que exigisse servidor gráfico seria um teste que a CI pula.
"""

from __future__ import annotations

import unittest
from unittest import mock

from qt_app import MOTIVO, TEM_PYQT, aplicacao

from chess_diagram_ocr.ui import estilos, folha, pele, tipografia, tokens

if TEM_PYQT:
    from chess_diagram_ocr.qt import tema


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class FolhaDeEstiloTests(unittest.TestCase):
    """A folha é texto, e é construída sem tela."""

    def test_a_folha_e_pura_e_nao_toca_a_aplicacao(self) -> None:
        """O contrato do módulo: afirmar a aparência inteira numa máquina sem tela.

        Se um dia alguém puser uma chamada de `QApplication` dentro de `folha_de_estilo`, é aqui
        que se descobre -- e não numa CI que passa a pular a metade visual do projeto.

        **A pergunta é feita trocando o `QApplication` do módulo por um que recusa tudo**, e não
        conferindo que não existe aplicação nenhuma no processo. A primeira versão deste teste
        fazia isso e passava sozinha e falhava na suíte inteira: a `QApplication` é do processo
        (`tests/qt_app.py`), então qualquer teste de Qt que rodasse antes já a tinha criado. Um
        teste que só passa quando é o primeiro não mede pureza -- mede a ordem da suíte.
        """

        class RecusaTudo:
            def __getattr__(self, nome: str) -> object:
                raise AssertionError(f"folha_de_estilo tocou QApplication.{nome}")

        with mock.patch.object(tema, "QApplication", RecusaTudo()):
            self.assertIn("QWidget", tema.folha_de_estilo())

    def test_a_pele_troca_o_cromo(self) -> None:
        claro = tema.folha_de_estilo(cromo_escuro=False)
        escuro = tema.folha_de_estilo(cromo_escuro=True)
        self.assertNotEqual(claro, escuro)
        self.assertIn(tokens.RESERVA[tokens.SUPERFICIE_PADRAO], claro)
        self.assertIn(tokens.NO_CROMO_ESCURO[tokens.SUPERFICIE_PADRAO], escuro)

    def test_a_pele_nao_toca_a_superficie_do_documento(self) -> None:
        """A folha do livro e o tabuleiro não escurecem porque alguém trocou de aparência.

        É a fronteira da S-224, e ela vale nos dois frontends: quem pinta documento pergunta a
        `cor_atual`, e a resposta tem de ser a mesma nas três peles.
        """
        for papel in tokens.SUPERFICIES_DE_DOCUMENTO:
            with self.subTest(papel=papel):
                self.assertEqual(
                    tokens.cor(papel, None, cromo_escuro=False),
                    tokens.cor(papel, None, cromo_escuro=True),
                    f"{papel} mudou com a pele, e é superfície de documento",
                )

    def test_a_densidade_compacta_encolhe(self) -> None:
        confortavel = tema.folha_de_estilo(densidade=pele.CONFORTAVEL)
        compacta = tema.folha_de_estilo(densidade=pele.COMPACTA)
        self.assertNotEqual(confortavel, compacta)
        self.assertIn("padding: 6px 14px", confortavel)  # a aba, na base de referência
        self.assertIn("padding: 4px 10px", compacta)

    def test_a_folha_acompanha_a_fonte_do_sistema(self) -> None:
        """Quem aumenta a fonte do Windows ganha vão proporcional, e não pixel cravado.

        É o argumento da S-149 e o defeito de DPI da S-148 num lugar menor -- e o que separa
        `_escalado` de um número escrito na folha.
        """
        pequena = tema.folha_de_estilo(base=tipografia.BASE_DE_REFERENCIA)
        grande = tema.folha_de_estilo(base=tipografia.BASE_DE_REFERENCIA * 2)
        self.assertNotEqual(pequena, grande)
        self.assertIn("padding: 4px 10px", pequena)  # QPushButton na base
        self.assertIn("padding: 8px 20px", grande)

    def test_densidade_desconhecida_levanta(self) -> None:
        """Como `tipografia.folga`: a tolerância é a ambiente, não a nome escrito errado."""
        with self.assertRaises(KeyError):
            tema.folha_de_estilo(densidade="espremida")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class RecheioTests(unittest.TestCase):
    """O recheio sai da mesma tabela dos dois lados, e é isto que impede a divergência."""

    def test_a_folha_do_tk_alcanca_as_mesmas_classes_no_qt(self) -> None:
        """Toda classe de `ui/folha.py` tem um seletor de Qt, e nenhum seletor é órfão.

        **É o teste que dá sentido ao módulo.** `ui/folha.py` cobre cinco classes que o
        `ttkbootstrap` deixou vazias; se o Qt cobrir quatro, uma das duas janelas desenha a
        caixa de seleção colada no rótulo e ninguém compara as duas telas lado a lado para
        descobrir. Um mapa parcial falha aqui, na montagem da suíte, e não na tela.
        """
        cobertas = {tema.RECHEIO_DA_FOLHA[seletor] for seletor in tema.RECHEIO_DA_FOLHA}
        self.assertEqual(cobertas, set(folha.CLASSES))

    def test_o_recheio_e_o_da_folha_e_nao_um_numero_repetido(self) -> None:
        """Nenhum pixel da folha do Tk é reescrito aqui: o valor sai de `folha.recheio`."""
        qss = tema.folha_de_estilo()
        for seletor, classe in tema.RECHEIO_DA_FOLHA.items():
            with self.subTest(seletor=seletor):
                h, v = folha.recheio(classe)
                self.assertIn(f"{seletor} {{ padding: {v}px {h}px; }}", qss)

    def test_o_que_o_ttkbootstrap_dava_esta_declarado(self) -> None:
        """Os quatro que o outro tema entregava e o Qt não entrega.

        Sem eles o botão sai com o recheio de fábrica do estilo da plataforma -- que é um número
        no Windows, outro no `Fusion` e outro no `offscreen` da CI. A medição está em
        `ui/folha.py`, e aqui se afirma que ela chegou.
        """
        qss = tema.folha_de_estilo()
        for seletor in tema.RECHEIO_DO_TEMA:
            with self.subTest(seletor=seletor):
                self.assertIn(f"{seletor} {{ padding:", qss)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class EnfaseTests(unittest.TestCase):
    """A ênfase da S-444, do lado do Qt."""

    def test_os_dois_papeis_de_enfase_pintam(self) -> None:
        for cromo_escuro in (False, True):
            qss = tema.folha_de_estilo(cromo_escuro=cromo_escuro)
            for papel in (estilos.PRIMARIO, estilos.DESTRUTIVO):
                with self.subTest(papel=papel, cromo_escuro=cromo_escuro):
                    self.assertIn(f'QPushButton[papel="{papel}"]', qss)

    def test_o_neutro_nao_ganha_face(self) -> None:
        """Se tudo tem ênfase, nada tem -- e o neutro é o padrão, não um terceiro azul."""
        self.assertNotIn(f'QPushButton[papel="{estilos.NEUTRO}"]', tema.folha_de_estilo())

    def test_a_enfase_passa_no_piso_de_contraste_nas_duas_peles(self) -> None:
        """A medição que a S-444 fez no Tk, refeita aqui.

        Ela vale porque a paleta é a mesma; o que muda é quem a pinta. Um dia em que alguém
        troque a face de um papel para "ficar melhor no Qt", é este teste que cobra o piso.
        """
        for cromo_escuro in (False, True):
            letra = tokens.cor(tokens.TEXTO_SOBRE_ENFASE, None, cromo_escuro=cromo_escuro)
            for token in (tokens.BOTAO_PRIMARIO, tokens.BOTAO_DESTRUTIVO):
                face = tokens.cor(token, None, cromo_escuro=cromo_escuro)
                with self.subTest(token=token, cromo_escuro=cromo_escuro):
                    self.assertGreaterEqual(
                        tokens.razao_de_contraste(face, letra),
                        tokens.AA_TEXTO,
                        f"{token} sobre a letra de ênfase reprova o piso AA",
                    )

    def test_o_realce_sob_o_ponteiro_nao_troca_a_cor_do_papel(self) -> None:
        """`hover` clareia a face; ele não a transforma noutro papel.

        É o que `REALCE_DE_ENFASE` promete por escrito, e o que decide o valor `0.18`.
        """
        for cromo_escuro in (False, True):
            letra = tokens.cor(tokens.TEXTO_SOBRE_ENFASE, None, cromo_escuro=cromo_escuro)
            for token in (tokens.BOTAO_PRIMARIO, tokens.BOTAO_DESTRUTIVO):
                face = tokens.cor(token, None, cromo_escuro=cromo_escuro)
                realce = tokens.mistura(face, letra, tokens.REALCE_DE_ENFASE)
                with self.subTest(token=token, cromo_escuro=cromo_escuro):
                    self.assertNotEqual(face, realce, "o realce não mudou nada")
                    if tokens.saturacao(face) > tokens.SATURACAO_NEUTRA:
                        self.assertLess(
                            tokens.distancia_de_matiz(face, realce),
                            tokens.SEPARACAO_MINIMA_DE_MATIZ,
                            "o realce mudou a matiz do papel",
                        )


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PapelDoBotaoTests(unittest.TestCase):
    """A propriedade dinâmica que leva o papel de `ui/estilos.py` até o seletor."""

    def setUp(self) -> None:
        aplicacao()

    def test_o_papel_vira_propriedade(self) -> None:
        from PyQt6.QtWidgets import QPushButton

        botao = tema.aplicar_papel(QPushButton("Salvar"), estilos.PRIMARIO)
        self.addCleanup(botao.deleteLater)
        self.assertEqual(botao.property(tema.PROPRIEDADE_DE_PAPEL), estilos.PRIMARIO)

    def test_o_neutro_tambem_e_declarado(self) -> None:
        """A ausência da propriedade não faz o Qt reavaliar o seletor: o neutro tem de ser dito."""
        from PyQt6.QtWidgets import QPushButton

        botao = tema.aplicar_papel(QPushButton("Copiar"), estilos.NEUTRO)
        self.addCleanup(botao.deleteLater)
        self.assertEqual(botao.property(tema.PROPRIEDADE_DE_PAPEL), estilos.NEUTRO)

    def test_papel_desconhecido_levanta_em_vez_de_cair_no_neutro(self) -> None:
        from PyQt6.QtWidgets import QPushButton

        botao = QPushButton("?")
        self.addCleanup(botao.deleteLater)
        with self.assertRaises(KeyError):
            tema.aplicar_papel(botao, "IMPORTANTE")

    def test_a_barra_com_duas_enfases_e_recusada(self) -> None:
        """`estilos.conferir_barra` é pura e vale nos dois frontends -- este é o lembrete."""
        with self.assertRaises(ValueError):
            estilos.conferir_barra([estilos.PRIMARIO, estilos.PRIMARIO], onde="uma barra do Qt")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class AplicacaoTests(unittest.TestCase):
    """Aparência não derruba ferramenta -- o contrato da S-53, deste lado."""

    def setUp(self) -> None:
        self.app = aplicacao()
        anterior = self.app.styleSheet()
        self.addCleanup(self.app.setStyleSheet, anterior)

    def test_aplicar_devolve_o_que_ficou_valendo(self) -> None:
        self.assertEqual(tema.aplicar_tema(self.app), "qss")
        self.assertIn("QWidget", self.app.styleSheet())

    def test_o_qt_aceita_a_folha_das_tres_peles(self) -> None:
        """Uma regra de QSS inválida é **silenciosa**: o Qt descarta a folha inteira e segue.

        Não há exceção a capturar, então o que se afirma é o efeito -- a folha entrou e voltou a
        sair pelo `styleSheet()`. Um erro de sintaxe numa das peles apareceria aqui como uma
        janela sem tema, que é o defeito, em vez de aparecer na tela de quem trocou de pele.
        """
        for uma in pele.PELES:
            with self.subTest(pele=uma.nome):
                tema.aplicar_tema(self.app, cromo_escuro=uma.cromo_escuro, densidade=uma.densidade)
                self.assertIn("QWidget", self.app.styleSheet())

    def test_densidade_errada_nao_derruba_a_janela(self) -> None:
        self.assertEqual(tema.aplicar_tema(self.app, densidade="espremida"), "qss")

    def test_a_repintura_esquece_o_widget_que_morreu(self) -> None:
        """Um widget destruído entre o registro e a troca é a janela de antes, não um erro.

        `sip.delete` destrói o objeto C++ **agora**, que é o que reproduz o caso real: sair de
        uma barra que a troca de pele destrói no mesmo gesto. `deleteLater` não serviria -- ele
        só marca, e o widget continua vivo até a linha de eventos girar, então a repintura
        seguinte funcionaria e o teste passaria sem tocar no caminho que ele existe para cobrir.
        """
        from PyQt6 import sip
        from PyQt6.QtWidgets import QLabel

        morto = QLabel("some")
        tema.pintar(morto, "color", tokens.TEXTO_SECUNDARIO)
        vivas: list[int] = []
        tema.ao_repintar(lambda: vivas.append(1))
        sip.delete(morto)

        tema.repintar()  # não pode levantar
        self.assertEqual(vivas, [1], "a repintura viva não rodou")
        tema.repintar()
        self.assertEqual(vivas, [1, 1], "a repintura morta não saiu da lista")

    def test_cor_desconhecida_levanta(self) -> None:
        """Intolerante a papel escrito errado, como `tokens.cor`."""
        with self.assertRaises(KeyError):
            tema.cor_atual("AZULZINHO")

    def test_a_fonte_sai_como_qfont_no_papel_pedido(self) -> None:
        from PyQt6.QtGui import QFont

        corpo = tema.fonte_atual(tipografia.CORPO)
        titulo = tema.fonte_atual(tipografia.TITULO)
        self.assertIsInstance(corpo, QFont)
        self.assertGreater(titulo.pointSize(), corpo.pointSize())
        self.assertTrue(titulo.bold(), "o título é negrito por papel, e não por chamador")

    def test_fonte_de_papel_desconhecido_levanta(self) -> None:
        with self.assertRaises(KeyError):
            tema.fonte_atual("GIGANTE")


def _seletores_desabilitados(folha: str) -> set[str]:
    """Os seletores de `:disabled` de uma folha QSS, um por regra.

    Leitura de texto e não de CSS de verdade: a folha é gerada por `folha_de_estilo`, uma regra
    por linha, e o que importa é o seletor antes da chave.
    """
    achados = set()
    for linha in folha.split("\n"):
        cabeca, _, resto = linha.partition("{")
        if resto and cabeca.strip().endswith(":disabled"):
            achados.add(cabeca.strip())
    return achados


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DesabilitadoSeVeTests(unittest.TestCase):
    """Um controle desabilitado tem de **parecer** desabilitado (S-506).

    **O defeito era invisível para a suíte inteira e visível para quem usa.** Um teste que afirma
    `isEnabled()` mede a decisão, não o desenho: durante a exportação o painel do PDF acendia só o
    "Cancelar exportação" e apagava os outros seis, os testes concordavam, e a barra saía **pixel a
    pixel idêntica** à de antes -- porque `QWidget { color: ... }` vale em todos os estados e
    anula o acinzentamento que o Qt faria pela paleta.

    **E o teste de pixel não serve de guarda aqui, o que só a medição mostrou.** Sem a regra, o
    botão ligado e o desligado saem idênticos na plataforma **nativa** e *diferentes* sob
    `offscreen` -- que é como esta suíte inteira roda. Um `assertNotEqual` sobre dois `grab()`
    passa em verde na CI justamente no estado defeituoso: ele mediria o estilo da plataforma de
    teste, e não a folha que o produto usa. Por isso a afirmação é sobre a folha, com o controle
    abaixo provando que a leitura dela acha e deixa de achar.
    """

    def test_a_folha_apaga_o_botao_comum_desabilitado(self) -> None:
        """**É o caso que estava quebrado**, e é o que o par exportar/cancelar usa para dizer qual
        dos dois está vivo."""
        seletores = _seletores_desabilitados(tema.folha_de_estilo())
        self.assertIn(
            "QPushButton:disabled",
            seletores,
            "o botão comum não tem regra de desabilitado, e sem ela ele desenha igual ao ligado",
        )

    def test_os_outros_dois_papeis_continuam_declarando_o_seu(self) -> None:
        """Estes dois já tinham o deles (S-444), e a regra nova não podia apagá-los."""
        seletores = _seletores_desabilitados(tema.folha_de_estilo())
        for papel in (estilos.PRIMARIO, estilos.DESTRUTIVO):
            with self.subTest(papel=papel):
                self.assertIn(f'QPushButton[papel="{papel}"]:disabled', seletores)

    def test_a_leitura_de_seletores_acha_e_deixa_de_achar(self) -> None:
        """O **controle**, contra exemplos literais e não contra a folha de hoje.

        Ancorá-lo na folha de verdade o faria se apagar junto com o defeito: uma leitura que
        deixasse de reconhecer o formato devolveria conjunto vazio, e o caso de cima falharia por
        motivo certo com diagnóstico errado. Estes dois trechos são as duas formas que importam.
        """
        so_com_papel = 'QPushButton[papel="PRIMARIO"]:disabled { color: #888; }'
        self.assertEqual({'QPushButton[papel="PRIMARIO"]:disabled'}, _seletores_desabilitados(so_com_papel))
        self.assertNotIn("QPushButton:disabled", _seletores_desabilitados(so_com_papel))

        com_o_comum = f"QPushButton {{ padding: 4px; }}\n{so_com_papel}\nQPushButton:disabled {{ color: #888; }}"
        self.assertIn("QPushButton:disabled", _seletores_desabilitados(com_o_comum))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
