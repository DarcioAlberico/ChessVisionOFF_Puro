"""A aba de texto no Qt: o formato, o mapa de deslocamento e as ferramentas (S-211/S-504).

**O que estes testes cobrem, e o que não.** O que cada ferramenta *faz* com o documento é de
`text/rico.py` -- puro, e afirmado em `tests/test_texto_rico.py`. Como a página vira documento é
de `rico.de_pagina`, afirmado em `tests/test_texto_camada.py`. A paleta do autor e a faixa de
confiança são de `ui/texto_cores.py`. Repetir qualquer um desses aqui mediria o mesmo código duas
vezes.

O que só existe deste lado são três coisas, e as três quebram em silêncio:

1. **O formato.** No Tk uma etiqueta dá **uma** fonte ao trecho, e negrito dentro de um título
   sumia -- daí `NEGRITO_ITALICO` e `fonte:titulo:bi:2`. Aqui as propriedades são independentes, e
   é isto que se afirma: as três convivem.
2. **O mapa de deslocamento.** A miniatura do diagrama vale um caractere para o widget e nenhum
   para o documento. Sem o mapa, o negrito aplicado depois do terceiro diagrama cai três
   caracteres adiante -- e nada levanta.
3. **Que o estado é o documento**, e não o widget. É o que faz o desfazer ver uma mudança de
   formato, que não altera caractere nenhum.
"""

from __future__ import annotations

import unittest
from dataclasses import fields

import numpy as np
from qt_app import MOTIVO, TEM_PYQT, aplicacao

from chess_diagram_ocr.text import rico
from chess_diagram_ocr.text.pagina import BlocoDeDiagrama, BlocoDeTexto, Coluna, LinhaLida, PaginaLida
from chess_diagram_ocr.ui import texto_cores, tipografia, tokens

if TEM_PYQT:
    from PyQt6.QtGui import QFont, QTextCursor

    from chess_diagram_ocr.qt import tema, texto_formato
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto

def _tracos(formato: object) -> tuple[object, ...]:
    """As quatro propriedades que um booleano de `rico.Atributos` pode mexer.

    Existe para o teste parametrico: comparar `QTextCharFormat` inteiro traria a cor e a fonte
    junto, e a pergunta ali e so "ligar este atributo mudou alguma coisa?".
    """
    return (
        formato.fontWeight(),  # type: ignore[attr-defined]
        formato.fontItalic(),  # type: ignore[attr-defined]
        formato.fontUnderline(),  # type: ignore[attr-defined]
        formato.fontStrikeOut(),  # type: ignore[attr-defined]
    )


BASE = (9, "Segoe UI", "Consolas")
"""A fonte do sistema fixada, para o teste não depender da máquina -- é a razão de
`tipografia.fonte` receber `base=`."""


def bloco(conteudo: str) -> BlocoDeTexto:
    return BlocoDeTexto.de_linhas([LinhaLida(conteudo, (0.0, 0.0, 10.0, 10.0), 1.0, "camada", None, None)])


def pagina_com_diagrama() -> PaginaLida:
    return PaginaLida(
        documento="livro.pdf",
        pagina=0,
        colunas=(
            Coluna(
                indice=0,
                blocos=(
                    bloco("Antes do diagrama."),
                    BlocoDeDiagrama(indice=0, bbox=(10.0, 10.0, 60.0, 60.0)),
                    bloco("Depois do diagrama."),
                ),
            ),
        ),
    )


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class FormatoTests(unittest.TestCase):
    """`rico.Atributos` virando `QTextCharFormat`, e o que isso apagou do lado do Tk."""

    def setUp(self) -> None:
        aplicacao()

    def formato(self, **atributos: object):  # noqa: ANN201 - QTextCharFormat
        corrida = rico.Corrida("trecho", rico.Atributos(**atributos))  # type: ignore[arg-type]
        return texto_formato.formato_de(corrida, base=BASE)

    def test_todo_booleano_de_atributo_foi_decidido(self) -> None:
        """Ou se desenha, ou se declara que ainda nao (S-238/S-506).

        **Esta guarda era do lado do Tk e veio junto com o dever dela.** La ela morava em
        `test_ui_texto_etiquetas` e cobrava `ETIQUETA_DO_ATRIBUTO`; o modulo saiu com o toolkit que
        traduzia, e apagar o teste no mesmo movimento deixaria o atributo novo entrar em silencio --
        que e exatamente o modo de falha que uma guarda apagada junto com o codigo nao acusa.
        """
        booleanos = {c.name for c in fields(rico.Atributos) if c.type in ("bool", bool)}
        decididos = set(texto_formato.BOOLEANOS_DESENHADOS) | set(texto_formato.BOOLEANOS_SEM_DESENHO)
        self.assertEqual(booleanos, decididos)

    def test_o_que_nao_se_desenha_nao_esta_entre_os_desenhados(self) -> None:
        """As duas listas sao exclusivas: um nome nas duas e uma decisao que ninguem tomou."""
        self.assertEqual(
            set(texto_formato.BOOLEANOS_DESENHADOS) & set(texto_formato.BOOLEANOS_SEM_DESENHO), set()
        )

    def test_todo_booleano_declarado_como_desenhado_muda_o_formato(self) -> None:
        """**A metade que a declaracao sozinha nao prova.** Parametrico sobre a lista.

        Declarar um atributo como desenhado e nao desenha-lo passa nos dois testes acima e falha
        na tela -- que e o unico lugar onde a pessoa descobre.
        """
        neutro = self.formato()
        for nome in texto_formato.BOOLEANOS_DESENHADOS:
            with self.subTest(atributo=nome):
                ligado = self.formato(**{nome: True})
                self.assertNotEqual(
                    _tracos(ligado), _tracos(neutro), f"{nome} nao muda nada no formato"
                )

    def test_negrito_italico_e_estilo_convivem_no_mesmo_trecho(self) -> None:
        """**É a economia inteira do porte.**

        No `tk.Text` uma etiqueta dá uma fonte e a última criada vence: com a fonte na etiqueta do
        estilo, o negrito de dentro dele sumia -- está escrito em `texto_panel._pintar_estilos`.
        Por isso existem lá `NEGRITO_ITALICO` e `fonte:titulo:bi:2`, geradas sob demanda. Aqui as
        três propriedades são independentes, e o teste é que elas valem juntas.
        """
        formato = self.formato(negrito=True, italico=True, estilo=rico.ESTILO_TITULO)
        self.assertEqual(formato.fontWeight(), QFont.Weight.Bold)
        self.assertTrue(formato.fontItalic())
        self.assertEqual(formato.fontPointSize(), float(tipografia.escala(BASE[0])[tipografia.TITULO]))

    def test_o_corpo_sai_de_tipografia_e_nao_de_um_pixel_cravado(self) -> None:
        """O critério de aceite da S-249: `tipografia` escala pela fonte do sistema."""
        for estilo, papel in texto_formato.PAPEL_DO_ESTILO.items():
            with self.subTest(estilo=estilo):
                formato = self.formato(estilo=estilo)
                self.assertEqual(formato.fontPointSize(), float(tipografia.escala(BASE[0])[papel]))

    def test_a_notacao_sai_monoespacada(self) -> None:
        """Uma linha de lances alinhada é o que a proporcional estraga."""
        self.assertEqual(self.formato(estilo=rico.ESTILO_NOTACAO).fontFamilies(), [BASE[2]])
        self.assertEqual(self.formato(estilo=rico.ESTILO_PROSA).fontFamilies(), [BASE[1]])

    def test_o_degrau_de_corpo_parte_da_origem(self) -> None:
        """Somar ao tamanho **já desenhado** faria a fonte crescer sozinha a cada redesenho."""
        um = self.formato(corpo=1).fontPointSize()
        dois = self.formato(corpo=2).fontPointSize()
        self.assertEqual(dois - um, 1.0)
        for _ in range(3):
            self.assertEqual(self.formato(corpo=2).fontPointSize(), dois)

    def test_os_quatro_tracos_sao_independentes(self) -> None:
        formato = self.formato(sublinhado=True, tachado=True)
        self.assertTrue(formato.fontUnderline())
        self.assertTrue(formato.fontStrikeOut())
        self.assertFalse(formato.fontItalic())

    def test_a_cor_do_autor_ganha_da_faixa(self) -> None:
        """**A ordem das três origens é a decisão.**

        Inverter faria uma anotação humana em amarelo virar vermelho porque o motor duvidou
        daquele trecho -- e a pessoa concluiria que a cor dela não pegou.
        """
        corrida = rico.Corrida("trecho", rico.Atributos(cor="nota"), faixa="revisar")
        formato = texto_formato.formato_de(corrida, base=BASE)
        esperada = tokens.cor(texto_cores.papel_de_cor("nota"), None)
        self.assertEqual(formato.foreground().color().name(), esperada)

    def test_a_faixa_pinta_quando_nao_ha_cor_do_autor(self) -> None:
        corrida = rico.Corrida("trecho", faixa="revisar")
        formato = texto_formato.formato_de(corrida, base=BASE)
        esperada = tokens.cor(texto_cores.PAPEL_DA_FAIXA["revisar"], None)
        self.assertEqual(formato.foreground().color().name(), esperada)

    def test_a_faixa_tranquila_nao_pede_papel_nenhum(self) -> None:
        """`""` é "a cor normal do texto": pintá-la de preto é o que quebraria o tema escuro."""
        corrida = rico.Corrida("trecho", faixa="tranquilo")
        formato = texto_formato.formato_de(corrida, base=BASE)
        self.assertEqual(formato.foreground().color().name(), tokens.cor(tokens.TEXTO_PADRAO, None))

    def test_o_bloco_leva_alinhamento_e_recuo(self) -> None:
        prosa = texto_formato.bloco_de(rico.Atributos(estilo=rico.ESTILO_PROSA), base=BASE)
        legenda = texto_formato.bloco_de(rico.Atributos(estilo=rico.ESTILO_LEGENDA), base=BASE)
        self.assertGreater(prosa.textIndent(), 0, "prosa recua a primeira linha (S-199)")
        self.assertEqual(prosa.leftMargin(), 0)
        self.assertGreater(legenda.leftMargin(), 0, "legenda recua o bloco inteiro")

    def test_o_recuo_acompanha_a_fonte(self) -> None:
        """Um `24` cravado quebraria quem aumentou a fonte do Windows (S-147)."""
        pequeno = texto_formato.recuo_de(rico.ESTILO_PROSA, base=(9, "Segoe UI", "Consolas"))
        grande = texto_formato.recuo_de(rico.ESTILO_PROSA, base=(18, "Segoe UI", "Consolas"))
        self.assertGreater(grande, pequeno)

    def test_o_alinhamento_vira_flag_do_qt(self) -> None:
        for alinhamento in rico.ALINHAMENTOS:
            with self.subTest(alinhamento=alinhamento):
                formato = texto_formato.bloco_de(rico.Atributos(alinhamento=alinhamento), base=BASE)
                self.assertNotEqual(int(formato.alignment()), 0)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PainelTests(unittest.TestCase):
    """A base das quatro classes abaixo: um painel montado, mostrado e ouvindo o `estado`.

    `show()` e `processEvents()` não são cerimônia: sob `offscreen` um `QPlainTextEdit` que nunca
    apareceu não tem layout, e medir cursor ou seleção nele responde sobre o widget errado.
    """

    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.painel = PainelDeTexto(dpi=72)
        self.addCleanup(self.painel.deleteLater)
        self.painel.resize(600, 500)
        self.painel.show()
        self.app.processEvents()
        self.recados: list[str] = []
        self.painel.estado.connect(self.recados.append)

    def selecionar(self, inicio: int, fim: int) -> None:
        """Seleciona por deslocamento **do documento**, traduzindo pelo mapa."""
        cursor = self.painel.editor.textCursor()
        cursor.setPosition(self.painel._mapa.posicao(inicio))
        cursor.setPosition(self.painel._mapa.posicao(fim), QTextCursor.MoveMode.KeepAnchor)
        self.painel.editor.setTextCursor(cursor)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class MapaTests(PainelTests):
    """A tradução deslocamento-do-documento ↔ posição-do-cursor."""

    def test_sem_diagrama_os_dois_coincidem(self) -> None:
        self.painel.desenhar_documento(rico.de_texto("Uma frase simples."))
        self.assertEqual(len(self.painel.texto()), len(self.painel.editor.toPlainText()))
        for desloc in (0, 4, 10):
            self.assertEqual(self.painel._mapa.posicao(desloc), desloc)

    def test_com_diagrama_o_widget_tem_caracteres_a_mais(self) -> None:
        """**É o defeito que o mapa existe para não ter.**

        A miniatura vale um caractere para o widget e nenhum para o documento, e a quebra do
        desenho também não é do documento. Sem o mapa, o negrito aplicado depois do terceiro
        diagrama cairia três caracteres adiante -- e nada levanta.
        """
        self.painel.mostrar_pagina(pagina_com_diagrama(), folha_rgb=np.full((400, 400, 3), 210, np.uint8))
        self.assertGreater(
            len(self.painel.editor.toPlainText()),
            len(self.painel.texto()),
            "sem miniatura desenhada este teste não mede nada",
        )

    def test_o_mapa_fecha_nos_dois_sentidos(self) -> None:
        self.painel.mostrar_pagina(pagina_com_diagrama(), folha_rgb=np.full((400, 400, 3), 210, np.uint8))
        texto = self.painel.texto()
        for desloc in (0, 5, texto.index("Depois"), len(texto) - 1):
            with self.subTest(deslocamento=desloc):
                self.assertEqual(self.painel._mapa.deslocamento(self.painel._mapa.posicao(desloc)), desloc)

    def test_o_trecho_depois_do_diagrama_e_o_certo(self) -> None:
        """A conferência que o mapa existe para passar: selecionar pelo documento e conferir
        que o widget selecionou a mesma palavra."""
        self.painel.mostrar_pagina(pagina_com_diagrama(), folha_rgb=np.full((400, 400, 3), 210, np.uint8))
        alvo = self.painel.texto().index("Depois")
        self.selecionar(alvo, alvo + len("Depois"))
        self.assertEqual(self.painel.editor.textCursor().selectedText(), "Depois")

    def test_sem_folha_a_marca_continua_no_texto(self) -> None:
        """A imagem é do widget e morre com ele; a marca é do texto e sobrevive a salvar."""
        self.painel.mostrar_pagina(pagina_com_diagrama())
        self.assertIn("[Diagrama 1]", self.painel.texto())
        self.assertIn("[Diagrama 1]", self.painel.editor.toPlainText())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class FerramentasTests(PainelTests):
    """Toda ferramenta chama uma função pura de `rico` e redesenha o que voltou."""

    def setUp(self) -> None:
        super().setUp()
        self.painel.desenhar_documento(rico.de_texto("O bispo vai para c4."))

    def test_o_negrito_parte_a_corrida_e_marca_so_o_trecho(self) -> None:
        self.selecionar(2, 7)
        self.painel.negrito()
        marcadas = [c.texto for c in self.painel.documento.corridas if c.atributos.negrito]
        self.assertEqual(marcadas, ["bispo"])

    def test_alternar_de_novo_desliga(self) -> None:
        """Liga o atributo no intervalo -- ou desliga, se ele já vale em todo ele (S-241).

        **As corridas não voltam a se fundir, e é de propósito.** `rico.aplicar` carimba `humano`
        no trecho tocado (S-239), e o carimbo é parte da chave de fusão: desmarcar à mão um
        itálico que a régua da S-236 detectou é uma correção sobre o que o motor leu, e é o tipo
        de informação que a fila da S-212 quer. O que se afirma aqui é o atributo, não a contagem.
        """
        self.selecionar(2, 7)
        self.painel.negrito()
        self.selecionar(2, 7)
        self.painel.negrito()
        self.assertFalse(any(c.atributos.negrito for c in self.painel.documento.corridas))
        self.assertEqual(self.painel.texto(), "O bispo vai para c4.", "o texto mudou")

    def test_limpar_formato_nao_toca_a_cor(self) -> None:
        """A cor tem comando próprio (S-242): quem tira a ênfase quase nunca quer apagar a
        marcação colorida que fez para si."""
        self.selecionar(2, 7)
        self.painel.negrito()
        self.selecionar(2, 7)
        self.painel.pintar_letra("nota")
        self.selecionar(2, 7)
        self.painel.limpar_formato()
        trecho = next(c for c in self.painel.documento.corridas if c.texto == "bispo")
        self.assertFalse(trecho.atributos.negrito)
        self.assertEqual(trecho.atributos.cor, "nota")

    def test_o_estilo_alcanca_o_paragrafo_e_nao_so_a_selecao(self) -> None:
        """Marcar meia frase marcaria meio parágrafo, e o desenho ficaria com dois corpos de
        fonte na mesma linha (S-249)."""
        self.selecionar(2, 7)
        self.painel.aplicar_estilo(rico.ESTILO_TITULO)
        estilos_vistos = {c.atributos.estilo for c in self.painel.documento.corridas}
        self.assertEqual(estilos_vistos, {rico.ESTILO_TITULO})

    def test_o_alinhamento_tambem_e_do_paragrafo(self) -> None:
        self.selecionar(2, 7)
        self.painel.alinhar(rico.ALINHAMENTO_CENTRO)
        alinhamentos = {c.atributos.alinhamento for c in self.painel.documento.corridas}
        self.assertEqual(alinhamentos, {rico.ALINHAMENTO_CENTRO})

    def test_o_corpo_anda_em_degraus(self) -> None:
        self.selecionar(0, 5)
        self.painel.mudar_corpo(2)
        self.assertEqual({c.atributos.corpo for c in self.painel.documento.corridas}, {2})
        self.painel.mudar_corpo(-1)
        self.assertEqual({c.atributos.corpo for c in self.painel.documento.corridas}, {1})

    def test_o_desenho_reflete_o_documento(self) -> None:
        """O widget é o desenho do documento, e não um segundo estado."""
        self.selecionar(2, 7)
        self.painel.negrito()
        cursor = self.painel.editor.textCursor()
        cursor.setPosition(self.painel._mapa.posicao(4))
        self.assertEqual(cursor.charFormat().fontWeight(), QFont.Weight.Bold)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class HistoricoTests(PainelTests):
    """A pilha é de **documentos**, e é o que faz `Ctrl+Z` desfazer um negrito."""

    def setUp(self) -> None:
        super().setUp()
        self.painel.desenhar_documento(rico.de_texto("O bispo vai para c4."))

    def test_desfazer_ve_uma_mudanca_que_nao_alterou_caractere(self) -> None:
        """**É a razão de a pilha ser de documentos.**

        O desfazer nativo do Qt é de edições de texto: uma ferramenta de formato não muda um
        caractere, e ele não a veria. Duas pilhas dariam um `Ctrl+Z` que às vezes desfaz o
        negrito e às vezes a palavra.
        """
        antes = self.painel.texto()
        self.selecionar(2, 7)
        self.painel.negrito()
        self.assertEqual(self.painel.texto(), antes, "o negrito mudou o texto")
        self.painel.desfazer()
        self.assertEqual([c.atributos.negrito for c in self.painel.documento.corridas], [False])

    def test_refazer_repoe(self) -> None:
        self.selecionar(2, 7)
        self.painel.negrito()
        self.painel.desfazer()
        self.painel.refazer()
        self.assertEqual([c.texto for c in self.painel.documento.corridas if c.atributos.negrito], ["bispo"])

    def test_desfazer_com_a_pilha_vazia_diz_por_que(self) -> None:
        self.painel.desfazer()
        self.assertIn("mudança anterior", self.recados[-1])

    def test_o_desfazer_nativo_do_qt_fica_desligado(self) -> None:
        """Duas pilhas sobre o mesmo `Ctrl+Z` é o defeito. Ver `_montar`."""
        self.assertFalse(self.painel.editor.isUndoRedoEnabled())

    def test_abrir_uma_pagina_zera_a_pilha(self) -> None:
        self.selecionar(2, 7)
        self.painel.negrito()
        self.painel.mostrar_pagina(pagina_com_diagrama())
        self.assertFalse(self.painel.pode_desfazer)

    def test_redesenhar_nao_corrompe_a_pilha(self) -> None:
        """**No Tk isto exige `edit_reset()` depois de todo redesenho**, porque a pilha de lá
        guarda índice e não conteúdo: sem zerar, desfazer apagaria um pedaço qualquer do texto
        novo. Aqui a pilha é o próprio histórico de documentos, e redesenhar não a toca."""
        self.selecionar(2, 7)
        self.painel.negrito()
        self.painel._desenhar()
        self.painel._desenhar()
        self.painel.desfazer()
        self.assertEqual([c.atributos.negrito for c in self.painel.documento.corridas], [False])


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class TecladoTests(PainelTests):
    def test_o_painel_declara_as_acoes_que_atende(self) -> None:
        for acao in self.painel.acoes_proprias():
            with self.subTest(acao=acao):
                self.assertIsNotNone(self.painel.atender(acao))

    def test_conferir_dono_aprova_a_declaracao(self) -> None:
        from chess_diagram_ocr.ui import atalhos

        atalhos.conferir_dono(self.painel, "o painel de texto do Qt")

    def test_a_barra_de_ferramentas_quebra_em_vez_de_cortar(self) -> None:
        from chess_diagram_ocr.qt.barra import BarraFluida

        barras = self.painel.findChildren(BarraFluida)
        self.assertEqual(len(barras), 1)
        self.assertGreater(barras[0].linhas_em(160), 1)

    def test_ctrl_b_no_editor_poe_o_trecho_em_negrito(self) -> None:
        """`TECLAS_DO_EDITOR` era a única declaração das teclas do editor, e no Qt ninguém a lia:
        `Ctrl+B` não fazia nada (medido em 2026-09-02, S-511). A tecla chega por um `QShortcut`
        com alcance no editor, e o método é o de `COMANDOS_DA_ABA` -- o mesmo do botão."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest

        self.painel.desenhar_documento(rico.de_texto("O bispo vai para c4."))
        self.painel.activateWindow()
        self.painel.editor.setFocus()
        self.app.processEvents()
        self.selecionar(2, 7)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
        self.app.processEvents()
        marcadas = [c.texto for c in self.painel.documento.corridas if c.atributos.negrito]
        self.assertEqual(marcadas, ["bispo"])

    def test_as_teclas_divididas_com_a_janela_sao_cedidas_ao_editor(self) -> None:
        """`Ctrl+R` é "ler esta página" na janela e "alinhar à direita" no editor
        (`CEDIDA_PELA_GUARDA`): a guarda cede. `Ctrl+H` é "substituir" nas duas e a janela ganha
        (`GANHA_DO_TK`): a guarda a entrega ao painel por `acoes_proprias`. `Ctrl+S` não é do
        editor: é da janela, atendida por este painel (S-244)."""
        from chess_diagram_ocr.qt import atalhos as qt_atalhos

        self.assertTrue(qt_atalhos.cede_a_tecla(self.painel.editor, "<Control-r>"))
        self.assertTrue(qt_atalhos.cede_a_tecla(self.painel.editor, "<Control-b>"))
        self.assertFalse(qt_atalhos.cede_a_tecla(self.painel.editor, "<Control-h>"))
        self.assertFalse(qt_atalhos.cede_a_tecla(self.painel.editor, "<Control-s>"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
