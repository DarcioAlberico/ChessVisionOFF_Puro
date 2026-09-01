"""Os atalhos do segundo frontend: a tradução da tabela e a guarda de foco (S-501).

**O que estes testes cobrem, e o que não.** *Que* teclas a guarda cede já é afirmado em
`tests/test_shortcuts.py`, e a decisão passou a ser a mesma função pura
(`atalhos.cede_a_sequencia`) nos dois frontends. Repetir a lista aqui mediria o mesmo código
duas vezes.

O que só existe deste lado são duas coisas, e são as duas que podem divergir em silêncio:

1. **A tradução da tecla.** Uma sequência que não traduz vira um `QKeySequence` vazio, que não
   dispara e não reclama -- um atalho que simplesmente não existe.
2. **A guarda dentro do laço de eventos do Qt.** Em Tk ela é `"break"` / `None`; aqui é `True` /
   `False` num `eventFilter`, e a diferença entre consumir e devolver a tecla é o que decide se
   digitar uma FEN troca de diagrama a cada seta.
"""

from __future__ import annotations

import unittest

from qt_app import MOTIVO, TEM_PYQT, aplicacao

from chess_diagram_ocr.ui import atalhos

if TEM_PYQT:
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent, QKeySequence
    from PyQt6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QPushButton, QWidget

    from chess_diagram_ocr.qt import atalhos as qt_atalhos


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class TraducaoTests(unittest.TestCase):
    """A tabela do Tk escrita como o Qt a quer, sem uma segunda tabela para manter."""

    def test_as_vinte_e_uma_teclas_traduzem_para_um_qkeysequence_valido(self) -> None:
        """**O teste que dá sentido ao módulo.**

        Uma tecla que não traduz não levanta na janela: ela vira um atalho que não existe, e o
        sintoma é alguém dizendo que "Ctrl+9 não faz nada nessa versão". Aqui ela falha na
        montagem da suíte, com o nome.
        """
        aplicacao()  # `QKeySequence` precisa da aplicação para resolver nome de tecla
        for atalho in atalhos.ATALHOS:
            with self.subTest(sequencia=atalho.sequencia):
                tecla = QKeySequence(qt_atalhos.sequencia_qt(atalho.sequencia))
                self.assertFalse(tecla.isEmpty(), f"{atalho.sequencia} não virou tecla nenhuma")

    def test_a_maiuscula_do_tk_e_shift(self) -> None:
        """A regra que não se adivinha, e que a tabela usa nas duas direções.

        `salvar` é `<Control-s>` e `salvar_todos` é `<Control-S>`. Um tradutor que aplicasse
        `.upper()` sem olhar faria os dois virarem o mesmo atalho -- e "salvar todos" apagaria
        "salvar" sem erro nenhum a que se agarrar.
        """
        self.assertEqual(qt_atalhos.sequencia_qt("<Control-s>"), "Ctrl+S")
        self.assertEqual(qt_atalhos.sequencia_qt("<Control-S>"), "Ctrl+Shift+S")

    def test_os_nomes_que_os_dois_toolkits_escrevem_diferente(self) -> None:
        for tk, qt in (("<Prior>", "PgUp"), ("<Next>", "PgDown"), ("<Delete>", "Del")):
            with self.subTest(tk=tk):
                self.assertEqual(qt_atalhos.sequencia_qt(tk), qt)

    def test_o_par_mais_e_menos_vira_o_proprio_caractere(self) -> None:
        self.assertEqual(qt_atalhos.sequencia_qt("<Control-plus>"), "Ctrl++")
        self.assertEqual(qt_atalhos.sequencia_qt("<Control-minus>"), "Ctrl+-")

    def test_sequencia_que_nao_traduz_levanta_em_vez_de_virar_vazio(self) -> None:
        """Silêncio aqui é um atalho ausente, que é o defeito mais caro deste módulo."""
        for ruim in ("Control-s", "<Control-inventada>", "<Hiper-s>", "<Control->", ""):
            with self.subTest(sequencia=ruim), self.assertRaises(ValueError):
                qt_atalhos.sequencia_qt(ruim)


class FonteUnicaTests(unittest.TestCase):
    """Nenhuma tecla escrita fora de `ui/atalhos.py`, **também deste lado** (S-165/S-501).

    `tests/test_ui_legenda.FonteUnicaTests` faz esta varredura em `ui/` e no `app_tkinter.py`,
    procurando a sequência do Tk (`"<Control-s>"`). Ela não alcança o Qt, que escreve a tecla com
    outra sintaxe (`"Ctrl+S"`) -- e a barra de `qt/janela.py` estava aproveitando isso: seis das
    oito teclas repetiam a tabela literalmente, duas eram inventadas (`F4` chamava "marcar
    diagramas", que a tabela não declara) e **duas estavam trocadas** -- `Ctrl+0` era "página
    inteira" aqui e "ajustar à largura" na janela do produto.

    Não precisa de Qt: é `ast` sobre arquivo, e é por isso que a classe não tem `skipUnless`.
    """

    TRADUTOR = "atalhos.py"
    """O único arquivo do pacote que escreve nome de tecla, porque ele é o tradutor: `TECLAS_NOMEADAS`
    mapeia `"Prior"` para `"PgUp"`. Ele não declara atalho nenhum -- a declaração continua sendo
    de `ui/atalhos.py`, e o teste acima cobra que as vinte e uma dela traduzam."""

    def _teclas_escritas(self, caminho) -> list[str]:
        """Toda string que vira tecla: argumento de `QKeySequence(...)` ou de `setShortcut(...)`.

        Procurar por *chamada* e não por qualquer string é o que evita acusar um rótulo de botão
        que por acaso diga "Ctrl+S" -- e é o que faz `QKeySequence.StandardKey.Open` passar, que
        é convenção da plataforma e não sequência escrita.
        """
        import ast

        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        achadas: list[str] = []
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Call):
                continue
            alvo = no.func
            nome = alvo.attr if isinstance(alvo, ast.Attribute) else getattr(alvo, "id", "")
            if nome not in ("QKeySequence", "setShortcut"):
                continue
            achadas += [
                arg.value
                for arg in no.args
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            ]
        return achadas

    def test_so_o_tradutor_escreve_tecla_no_pacote_qt(self) -> None:
        from pathlib import Path

        pacote = Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr" / "qt"
        infratores = [
            f"{caminho.name}: {tecla}"
            for caminho in sorted(pacote.glob("*.py"))
            if caminho.name != self.TRADUTOR
            for tecla in self._teclas_escritas(caminho)
        ]
        self.assertEqual(infratores, [], "tecla escrita fora de `ui/atalhos.py`")

    BARRA = (
        "pagina_anterior",
        "proxima_pagina",
        "zoom_menos",
        "zoom_mais",
        "ajustar_pagina",
        "ajustar_largura",
        "ler_pagina",
    )
    """As sete ações da barra do visualizador. Elas são a amostra: se estas seguem a tabela, o
    ajudante que as monta segue, e é ele que monta as outras."""

    def test_a_barra_usa_as_teclas_da_tabela(self) -> None:
        """A outra metade: não basta não escrever tecla -- tem de usar a que a tabela declara.

        Sem este, bastaria alguém tirar a ação de um botão para ele ficar mudo, e a varredura
        acima passaria em verde sobre uma barra sem atalho nenhum.

        **A busca é pelo pacote, e não por `janela.py`.** A barra do visualizador saiu da janela
        para `painel_do_pdf.py` quando o visualizador virou painel; o teste pinado no arquivo
        antigo acusaria a mudança de endereço como se fosse atalho perdido.
        """
        from pathlib import Path

        pacote = Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr" / "qt"
        fontes = {
            caminho.name: caminho.read_text(encoding="utf-8") for caminho in pacote.glob("*.py")
        }
        for comando in self.BARRA:
            with self.subTest(comando=comando):
                self.assertIn(comando, atalhos.por_acao, "a ação sumiu da tabela de atalhos")
                self.assertTrue(
                    any(f'"{comando}"' in fonte for fonte in fontes.values()),
                    "nenhum arquivo de `qt/` pede esta ação ao catálogo",
                )


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class GuardaTests(unittest.TestCase):
    """A guarda dentro do laço de eventos: quem fica com a tecla."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.chamadas: list[str] = []
        self.comandos = {
            "diagrama_anterior": lambda: self.chamadas.append("anterior"),
            "salvar": lambda: self.chamadas.append("salvar"),
            "proxima_pagina": lambda: self.chamadas.append("proxima"),
        }
        self.guarda = qt_atalhos.GuardaDeAtalhos(self.comandos)

        # **O foco sobrevive ao teste que o pôs, e isso já custou um verde falso.**
        # `deleteLater` só marca: os widgets do teste anterior continuam vivos até a linha de
        # eventos girar, e `focusWidget()` continua apontando para um deles. Um botão dentro de
        # um painel morto ainda responde `acoes_proprias`, e a cadeia da S-244 encontrava a
        # declaração de um painel de outro teste -- o que fazia a tecla ser atendida por quem já
        # não existia. Limpar na entrada e girar a linha na saída torna a classe independente
        # da ordem em que os testes rodam.
        anterior = QApplication.focusWidget()
        if anterior is not None:
            anterior.clearFocus()
        self.addCleanup(self.app.processEvents)

        self.raiz = QWidget()
        self.addCleanup(self.raiz.deleteLater)
        # **A janela precisa estar mostrada e ativa para o foco existir.** Sob `offscreen` o
        # `setFocus` de um widget cuja janela nunca foi mostrada não faz nada, e `focusWidget()`
        # continua `None` -- o que faria a guarda cair no caminho "sem foco" e três destes testes
        # passarem verdes medindo o comando global em vez da cessão.
        self.raiz.show()
        self.raiz.activateWindow()

    def apertar(self, sequencia: str, foco: object | None = None, guarda: object | None = None) -> bool:
        """Manda a tecla pela guarda com aquele widget em foco. Devolve se ela foi consumida.

        O foco é dado de verdade e não simulado: `eventFilter` pergunta a
        `QApplication.focusWidget()`, e um duplo não responderia por ela. O `processEvents` é o
        que falta para o Qt de fato entregar o foco, e a conferência logo depois é para o teste
        falhar dizendo *"o foco não foi"* em vez de medir o caminho errado em silêncio.
        """
        if foco is not None:
            foco.setFocus(Qt.FocusReason.OtherFocusReason)
            self.app.processEvents()
            self.assertIs(QApplication.focusWidget(), foco, "o foco não foi para o widget do teste")
        tecla = QKeySequence(qt_atalhos.sequencia_qt(sequencia))[0]
        evento = QKeyEvent(
            QEvent.Type.KeyPress, tecla.key().value, tecla.keyboardModifiers()
        )
        return (guarda or self.guarda).eventFilter(self.app, evento)

    def campo(self, classe: type) -> object:
        widget = classe(self.raiz)
        widget.show()
        return widget

    def test_a_tecla_da_janela_e_consumida_e_chama_o_comando(self) -> None:
        botao = self.campo(QPushButton)
        self.assertTrue(self.apertar("<Left>", botao))
        self.assertEqual(self.chamadas, ["anterior"])

    def test_a_seta_dentro_do_campo_e_devolvida_ao_campo(self) -> None:
        """O defeito da S-20: digitar uma FEN trocaria de diagrama a cada seta."""
        entrada = self.campo(QLineEdit)
        self.assertFalse(self.apertar("<Left>", entrada))
        self.assertEqual(self.chamadas, [], "o comando da janela rodou dentro do campo")

    def test_o_ctrl_s_dentro_do_campo_continua_salvando(self) -> None:
        """O defeito da S-294, do outro lado: `Ctrl+S` não pertence a campo de texto nenhum.

        Até aquele item a guarda do Tk cedia os dezoito atalhos a qualquer campo, e com o cursor
        no campo de FEN `Ctrl+S` não salvava. Um frontend novo que cedesse tudo de novo
        reintroduziria a mesma medição.
        """
        entrada = self.campo(QLineEdit)
        self.assertTrue(self.apertar("<Control-s>", entrada))
        self.assertEqual(self.chamadas, ["salvar"])

    def test_a_rolagem_e_cedida_so_a_quem_rola(self) -> None:
        entrada = self.campo(QLineEdit)
        self.assertTrue(self.apertar("<Next>", entrada), "PgDn numa linha só não faz nada no campo")
        self.assertEqual(self.chamadas, ["proxima"])

        self.chamadas.clear()
        texto = self.campo(QPlainTextEdit)
        self.assertFalse(self.apertar("<Next>", texto), "PgDn é de quem rola")
        self.assertEqual(self.chamadas, [])

    def test_a_tecla_sem_comando_montado_segue_para_a_janela(self) -> None:
        """A versão de teste implementa uma parte do fluxo de propósito.

        Uma tecla da tabela cujo comando não foi montado não pode ser **consumida**: consumi-la
        faria a janela engolir `Ctrl+F` e não fazer nada com ele, que é pior que não ligá-lo.
        """
        botao = self.campo(QPushButton)
        self.assertFalse(self.apertar("<Control-f>", botao))
        self.assertEqual(self.chamadas, [])

    def test_o_painel_em_foco_ganha_a_acao_que_declarou(self) -> None:
        """O mecanismo da S-244, pelo `parent()` do Qt.

        É o que faz `←` ser "lance anterior" dentro da sala de estudo e "diagrama anterior" no
        resto da janela. A cadeia sobe pelo `parent()`, e é isso que este teste cobra -- sem o
        passo novo de `atalhos._pai`, a declaração do painel nunca seria consultada aqui.
        """

        class PainelComAcao(QWidget):
            def acoes_proprias(self) -> frozenset[str]:
                return frozenset({"diagrama_anterior"})

            def atender(self, acao: str):  # noqa: ANN201 - assinatura do protocolo
                return (lambda: self.chamadas.append("do painel")) if acao else None

        painel = PainelComAcao(self.raiz)
        painel.chamadas = self.chamadas  # type: ignore[attr-defined]
        painel.show()  # sem isto o filho de um pai escondido não recebe foco
        dentro = QPushButton(painel)
        dentro.show()
        self.assertTrue(self.apertar("<Left>", dentro))
        self.assertEqual(self.chamadas, ["do painel"], "a ação do painel não foi consultada")

    def test_o_evento_que_nao_e_tecla_passa_batido(self) -> None:
        self.assertFalse(self.guarda.eventFilter(self.app, QEvent(QEvent.Type.Show)))
        self.assertFalse(self.guarda.eventFilter(self.app, None))

    def test_um_comando_que_levanta_devolve_a_tecla_em_vez_de_derrubar_a_janela(self) -> None:
        """A borda do laço de eventos: uma exceção aqui sobe para lugar nenhum.

        O sintoma seria uma tecla que às vezes não faz nada, sem uma linha de log a que se
        agarrar -- é a mesma razão do `except` largo de `qt/trabalho.py`.
        """

        def explode() -> None:
            raise RuntimeError("o comando quebrou")

        botao = self.campo(QPushButton)
        guarda = qt_atalhos.GuardaDeAtalhos({"diagrama_anterior": explode})
        with self.assertLogs("chess_diagram_ocr.qt.atalhos", level="ERROR"):
            self.assertFalse(self.apertar("<Left>", botao, guarda))


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class LigarTests(unittest.TestCase):
    """A instalação do filtro."""

    def setUp(self) -> None:
        self.app = aplicacao()

    def test_a_guarda_e_devolvida_e_nasce_filha_da_janela(self) -> None:
        """Um `QObject` sem referência é coletado, e um filtro coletado deixa de ser chamado.

        O sintoma é a janela perder o teclado sem que nada avise, e é por isso que a guarda
        nasce filha da janela **e** é devolvida.
        """
        janela = QWidget()
        self.addCleanup(janela.deleteLater)
        guarda = qt_atalhos.ligar(janela, {"salvar": lambda: None}, aplicacao=self.app)
        self.addCleanup(self.app.removeEventFilter, guarda)
        self.assertIs(guarda.parent(), janela)

    def test_comando_fora_da_tabela_nao_derruba_a_ligacao(self) -> None:
        """Ao contrário de `atalhos.ligacoes`, que levanta nomeando o que falta.

        A diferença é o alcance, e está escrita em `ligar`: lá se liga a tabela inteira e um
        buraco é defeito; aqui a versão de teste implementa uma parte do fluxo de propósito.
        """
        janela = QWidget()
        self.addCleanup(janela.deleteLater)
        guarda = qt_atalhos.ligar(janela, {"comando_que_nao_existe": lambda: None}, aplicacao=self.app)
        self.addCleanup(self.app.removeEventFilter, guarda)
        self.assertEqual(guarda._teclas, {})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
