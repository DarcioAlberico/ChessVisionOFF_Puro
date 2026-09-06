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
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont, QTextCursor
    from PyQt6.QtTest import QTest

    from chess_diagram_ocr.qt import tema, texto_formato
    from chess_diagram_ocr.qt.painel_de_texto import MARCA_NAO_SE_EDITA, PainelDeTexto, _Mapa

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


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class MapaEditadoTests(unittest.TestCase):
    """`_Mapa.editar`: o mapa acompanha a digitação sem precisar de um redesenho (S-521).

    **Separada de `MapaTests` de propósito: aqui não se abre janela.** O mapa é uma lista de três
    inteiros e a edição é aritmética sobre ela; montar um painel para afirmar isto mediria o
    desenho junto, que é o que o item existe para não fazer a cada tecla.

    A montagem imita o que `_desenhar` registra numa folha com uma miniatura: dois trechos
    contíguos **no documento** (0-5 e 5-10) e separados **no widget** (0-5 e 7-12), porque a
    imagem e a quebra sob ela valem dois caracteres de tela e nenhum de texto.
    """

    def mapa(self) -> _Mapa:
        mapa = _Mapa()
        mapa.registrar(0, 0, 5)
        mapa.registrar(5, 7, 5)
        return mapa

    def test_insercao_no_meio_de_um_trecho(self) -> None:
        mapa = self.mapa()
        mapa.editar(2, 0, 3)
        self.assertEqual(mapa.deslocamento(2), 2, "o começo da inserção não se moveu")
        self.assertEqual(mapa.deslocamento(5), 5, "o que foi escrito conta no documento")
        # O trecho de depois da miniatura andou os três caracteres nas **duas** coordenadas: no
        # widget porque há três letras a mais na tela, no documento porque há três no texto.
        self.assertEqual(mapa.deslocamento(10), 8)
        self.assertEqual(mapa.posicao(8), 10, "e a volta fecha")

    def test_insercao_no_fim_de_um_trecho(self) -> None:
        """No fim do primeiro trecho o texto novo é **dele**, e não do seguinte."""
        mapa = self.mapa()
        mapa.editar(5, 0, 2)
        self.assertEqual(mapa.deslocamento(6), 6, "o caractere novo caiu no trecho da esquerda")
        self.assertEqual(mapa.deslocamento(9), 7, "a miniatura continua valendo zero")

    def test_insercao_na_emenda_de_dois_pertence_ao_da_esquerda(self) -> None:
        """**A divergência declarada com a S-238**, do lado do mapa: na emenda, herda a esquerda.

        Se herdasse a direita, o mapa diria um trecho e `rico.inserir` -- que herda da esquerda --
        carimbaria outro; as duas decisões têm de concordar ou o bloco do texto digitado muda
        conforme quem se pergunta.
        """
        mapa = _Mapa()
        mapa.registrar(0, 0, 5)
        mapa.registrar(5, 5, 5)
        mapa.editar(5, 0, 2)
        # **A afirmação é sobre qual trecho cresceu**, e não sobre o deslocamento: na emenda os
        # dois dariam o mesmo número, e só o tamanho diz de quem o texto novo é.
        cresceu = [t.tamanho for t in mapa.trechos()]
        self.assertEqual(cresceu, [7, 5], "o texto novo foi para o trecho da direita")
        self.assertEqual(mapa.deslocamento(6), 6, "e continua contíguo no documento")

    def test_remocao_que_atravessa_dois_trechos(self) -> None:
        """Apagar por cima da miniatura come pedaço dos dois lados -- e o widget passa a ter
        tantos caracteres quanto o documento, porque a imagem foi junto."""
        mapa = self.mapa()
        mapa.editar(3, 6, 0)
        self.assertEqual(mapa.deslocamento(0), 0)
        self.assertEqual(mapa.deslocamento(3), 3, "sobraram três do primeiro trecho")
        self.assertEqual(mapa.deslocamento(6), 6, "e três do segundo, agora colados")

    def test_edicao_depois_da_miniatura(self) -> None:
        """O caso que o mapa existe para não errar: digitar **depois** do diagrama."""
        mapa = self.mapa()
        mapa.editar(9, 0, 4)
        self.assertEqual(mapa.deslocamento(9), 7, "a posição do widget vira deslocamento certo")
        self.assertEqual(mapa.posicao(7), 9, "e volta")
        self.assertEqual(mapa.deslocamento(0), 0, "o trecho antes da miniatura não se mexeu")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DigitacaoTests(PainelTests):
    """A digitação chega ao documento (S-521).

    **É a tabela do problema da S-521, linha a linha.** Antes disto o `QTextEdit` era editável,
    ninguém escutava o que ele mudava, e `documento` ficava como estava: salvar gravava a folha
    sem o que tinha sido digitado, e formatar depois de digitar marcava o trecho errado.

    Nenhum dos 37 testes que já existiam neste arquivo digitava: as ferramentas eram chamadas
    pelo método sobre um documento posto por `desenhar_documento`, que é exatamente o caminho que
    funcionava.
    """

    def setUp(self) -> None:
        super().setUp()
        self.painel.desenhar_documento(rico.de_texto("O bispo vai para c4."))
        self.app.processEvents()

    def escrever(self, onde: int, texto: str) -> None:
        """Põe o cursor num deslocamento do documento e digita, tecla a tecla."""
        cursor = self.painel.editor.textCursor()
        cursor.setPosition(self.painel._mapa.posicao(onde))
        self.painel.editor.setTextCursor(cursor)
        QTest.keyClicks(self.painel.editor, texto)
        self.app.processEvents()

    def test_o_que_se_digita_chega_ao_documento(self) -> None:
        """**A primeira linha da tabela**, e a que fazia salvar gravar o texto velho."""
        self.escrever(2, "grande ")
        self.assertEqual(self.painel.documento.para_texto(), "O grande bispo vai para c4.")
        self.assertEqual(self.painel.texto(), self.painel.editor.toPlainText())

    def test_salvar_e_reabrir_devolve_o_que_foi_digitado(self) -> None:
        """O ciclo da S-238, fechado no Qt: o defeito só se via relendo o arquivo."""
        self.escrever(2, "grande ")
        self.assertIn("grande", self.painel.texto())
        redesenhado = rico.de_texto(self.painel.texto())
        self.assertEqual(redesenhado.para_texto(), "O grande bispo vai para c4.")

    def test_formatar_depois_de_digitar_marca_o_que_esta_na_tela(self) -> None:
        """**A segunda linha da tabela.** A seleção da tela caía sete caracteres antes no
        documento, e o redesenho apagava o que tinha sido digitado."""
        self.escrever(2, "grande ")
        alvo = self.painel.texto().index("bispo")
        self.selecionar(alvo, alvo + len("bispo"))
        self.painel.negrito()
        marcadas = [c.texto for c in self.painel.documento.corridas if c.atributos.negrito]
        self.assertEqual(marcadas, ["bispo"])
        self.assertIn("grande", self.painel.texto(), "o redesenho apagou o que foi digitado")

    def test_apagar_com_backspace_chega_ao_documento(self) -> None:
        cursor = self.painel.editor.textCursor()
        cursor.setPosition(self.painel._mapa.posicao(7))
        self.painel.editor.setTextCursor(cursor)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Backspace)
        self.app.processEvents()
        self.assertEqual(self.painel.documento.para_texto(), "O bisp vai para c4.")

    def test_recortar_pelo_comando_chega_ao_documento(self) -> None:
        """`recortar` continua sendo `cut()` do widget, e mesmo assim chega ao documento -- é o
        ponto do ouvinte único: ele não sabe qual gesto foi, só que o documento do Qt mudou.

        **`colar` não é afirmado aqui, e é limitação da plataforma de teste, não do conserto.**
        Sob `offscreen` a inserção vinda da área de transferência é inerte: `canPaste()` responde
        `True`, o `mimeData` tem `text/plain`, e `paste()` e `insertFromMimeData()` não mudam um
        caractere -- enquanto `insertPlainText` no mesmo widget muda. Um teste de colar aqui
        passaria em verde com e sem o conserto, que é a armadilha que a S-506 já registrou.
        """
        self.selecionar(0, 8)
        self.painel.recortar()
        self.app.processEvents()
        self.assertEqual(self.painel.documento.para_texto(), "vai para c4.")
        self.assertEqual(self.painel.texto(), self.painel.editor.toPlainText())

    def test_o_texto_digitado_carimba_procedencia_humana(self) -> None:
        """A correção fica atada ao bloco que corrige, que é o que a fila da S-212 lê."""
        self.escrever(2, "grande")
        procedencias = {c.procedencia for c in self.painel.documento.corridas if "grande" in c.texto}
        self.assertEqual(procedencias, {"humano"})

    def test_desfazer_tira_a_palavra_inteira_e_deixa_o_resto(self) -> None:
        """**O lote.** Uma entrada por tecla daria cem entradas em cem letras."""
        self.escrever(2, "grande ")
        antes = self.painel.edicao
        self.painel.desfazer()
        self.assertEqual(self.painel.documento.para_texto(), "O bispo vai para c4.")
        self.assertGreaterEqual(antes, 1)

    def test_uma_frase_de_tres_palavras_e_tres_entradas_e_nao_quinze(self) -> None:
        partida = self.painel.edicao
        self.escrever(0, "um dois tres")
        self.assertEqual(
            self.painel.edicao - partida,
            3,
            "a pilha ganhou uma entrada por tecla em vez de uma por palavra",
        )

    def test_a_digitacao_comum_nao_redesenha(self) -> None:
        """**O cursor é o que o redesenho custa**, e não o 1,7 ms: redesenhar a cada tecla manda
        o cursor para o começo da folha e interrompe a composição de acento."""
        desenhos = []
        original = self.painel._desenhar
        self.painel._desenhar = lambda: (desenhos.append(1), original())[1]  # type: ignore[method-assign]
        self.escrever(2, "grande")
        self.assertEqual(desenhos, [], "a digitação comum redesenhou")

    def test_apagar_a_marca_do_diagrama_e_recusado(self) -> None:
        """**O contrato de `substituir_intervalo`**: a estrutura do texto não é do teclado."""
        self.painel.mostrar_pagina(pagina_com_diagrama())
        self.app.processEvents()
        antes = self.painel.texto()
        marca = antes.index("[Diagrama 1]")
        cursor = self.painel.editor.textCursor()
        cursor.setPosition(self.painel._mapa.posicao(marca + 1))
        self.painel.editor.setTextCursor(cursor)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Backspace)
        self.app.processEvents()
        self.assertIn("[Diagrama 1]", self.painel.texto(), "a marca do diagrama foi apagada")
        # **E diz por quê.** Recusar em silêncio é pior que recusar: a tecla não faz nada e quem
        # digita fica sem saber se o editor travou.
        self.assertIn(MARCA_NAO_SE_EDITA, self.recados)

    def test_a_traducao_continua_certa_depois_de_digitar(self) -> None:
        """O terceiro defeito da tabela, com miniatura antes e depois do que foi digitado."""
        self.painel.mostrar_pagina(pagina_com_diagrama())
        self.app.processEvents()
        alvo = self.painel.texto().index("Depois")
        self.escrever(alvo, "logo ")
        texto = self.painel.texto()
        self.assertIn("logo Depois", texto)
        onde = texto.index("Depois")
        self.selecionar(onde, onde + len("Depois"))
        self.assertEqual(self.painel.editor.textCursor().selectedText(), "Depois")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
