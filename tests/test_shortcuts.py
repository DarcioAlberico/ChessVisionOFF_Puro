"""Guarda de foco dos atalhos (S-20/S-31).

O `bind_all` liga as teclas na janela inteira, e é isso que faz `←` funcionar com o foco em
qualquer lugar. O preço é que, dentro do campo de FEN, `←` e `Del` pertencem ao campo -- e
sem a guarda, digitar uma FEN à mão trocaria de diagrama a cada seta.

Testável sem janela porque a regra é sobre a **classe** do widget, não sobre o evento.
"""

from __future__ import annotations

import tkinter as tk
import unittest
from tkinter import ttk

from tk_root import raiz

from chess_diagram_ocr.ui import atalhos
from chess_diagram_ocr.ui.shortcuts import (
    FIELD_KEYS,
    TEXT_ENTRY_WIDGETS,
    WIDGET_KEYS,
    guard,
    ignores_widget,
    keys_of_widget,
    owns_key,
    uses_key,
)


class _FakeEvent:
    def __init__(self, widget: object) -> None:
        self.widget = widget


class _FakeEntry(ttk.Entry):
    """Instanciar `ttk.Entry` exige um Tk; a checagem é de tipo, então basta a classe."""

    def __init__(self) -> None:  # noqa: D107 - sem chamar o __init__ do Tk de proposito
        pass


class IgnoreTests(unittest.TestCase):
    def test_text_entry_widgets_keep_their_own_keys(self) -> None:
        for classe in (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox, ttk.Spinbox):
            with self.subTest(widget=classe.__name__):
                self.assertTrue(ignores_widget(classe.__new__(classe)))

    def test_the_spinbox_is_included_because_it_already_uses_the_arrows(self) -> None:
        """Sem isto, uma seta no seletor "Selecionado" mudaria o diagrama duas vezes."""
        self.assertTrue(ignores_widget(ttk.Spinbox.__new__(ttk.Spinbox)))

    def test_other_widgets_do_not_swallow_the_shortcut(self) -> None:
        for classe in (tk.Canvas, tk.Frame, ttk.Button, ttk.Label):
            with self.subTest(widget=classe.__name__):
                self.assertFalse(ignores_widget(classe.__new__(classe)))

    def test_an_event_without_a_widget_does_not_crash(self) -> None:
        self.assertFalse(ignores_widget(None))


class GuardTests(unittest.TestCase):
    def test_the_handler_runs_and_the_key_is_consumed_outside_a_text_field(self) -> None:
        chamadas: list[int] = []
        resultado = guard(lambda: chamadas.append(1))(_FakeEvent(tk.Canvas.__new__(tk.Canvas)))

        self.assertEqual(chamadas, [1])
        # "break" impede o Tk de repassar a tecla adiante, que e o que evita a acao dupla.
        self.assertEqual(resultado, "break")

    def test_inside_a_text_field_the_handler_does_not_run_and_the_key_passes_through(self) -> None:
        chamadas: list[int] = []
        resultado = guard(lambda: chamadas.append(1))(_FakeEvent(_FakeEntry()))

        self.assertEqual(chamadas, [])
        # `None` (e nao "break") e o que faz o Entry continuar recebendo a seta.
        self.assertIsNone(resultado)


class WidgetQueJaDeclarouATeclaTests(unittest.TestCase):
    """A seta não executa dois painéis ao mesmo tempo (S-117).

    O tabuleiro de estudo liga `<Left>`/`<Right>` no próprio canvas e os handlers devolvem
    `None`; o `bind_all` daqui liga as mesmas teclas ao editor. Os dois disparavam: analisar
    uma posição com as setas na aba Análise movia, invisivelmente, o cursor do editor em outra
    aba -- e o `Ctrl+S` seguinte gravava outro diagrama.
    """

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.disparos: list[str] = []
        self.quadro = tk.Frame(self.root)
        self.addCleanup(self.quadro.destroy)

    def _evento(self, widget: object) -> tk.Event:
        evento = tk.Event()
        evento.widget = widget  # type: ignore[assignment]
        return evento

    def test_o_canvas_que_declarou_a_seta_fica_com_ela(self) -> None:
        """A decisão, testada onde ela é tomada.

        Dirigir o Tk com `event_generate` aqui testaria o roteamento de evento do Tk -- que
        entrega por foco quando o alvo não é focável -- e não a guarda. O que a S-117 muda é a
        resposta de `guard` diante de um widget que já declarou a tecla, e é isso que se afirma.
        """
        canvas = tk.Canvas(self.quadro, width=40, height=40)
        canvas.bind("<Left>", lambda _e: None)
        protegido = guard(lambda: self.disparos.append("editor"), "<Left>")

        self.assertIsNone(protegido(self._evento(canvas)), "cedeu, então o Tk segue para o canvas")
        self.assertEqual(self.disparos, [], "o handler do editor não pode ter rodado")

    def test_fora_dele_o_atalho_do_editor_continua_valendo(self) -> None:
        outro = tk.Frame(self.quadro, width=40, height=40)
        protegido = guard(lambda: self.disparos.append("editor"), "<Left>")

        self.assertEqual(protegido(self._evento(outro)), "break")
        self.assertEqual(self.disparos, ["editor"])

    def test_sem_sequencia_a_segunda_pergunta_nao_e_feita(self) -> None:
        """`guard(handler)` sem tecla mantém o comportamento anterior à S-117 -- e há quem o use."""
        canvas = tk.Canvas(self.quadro, width=40, height=40)
        canvas.bind("<Left>", lambda _e: None)

        self.assertEqual(guard(lambda: self.disparos.append("editor"))(self._evento(canvas)), "break")
        self.assertEqual(self.disparos, ["editor"])

    def test_o_campo_de_texto_continua_vencendo(self) -> None:
        """A guarda antiga não pode ter sido substituída pela nova: as duas valem."""
        campo = ttk.Entry(self.quadro)
        protegido = guard(lambda: self.disparos.append("editor"), "<Left>")

        self.assertIsNone(protegido(self._evento(campo)))
        self.assertEqual(self.disparos, [])

    def test_owns_key_e_por_sequencia_e_nao_por_widget(self) -> None:
        """Ceder o widget inteiro tiraria `Ctrl+S` de quem está com o tabuleiro em foco."""
        canvas = tk.Canvas(self.quadro, width=40, height=40)
        canvas.bind("<Left>", lambda _e: None)

        self.assertTrue(owns_key(canvas, "<Left>"))
        self.assertFalse(owns_key(canvas, "<Control-s>"))

    def test_um_objeto_sem_bind_nao_derruba_a_guarda(self) -> None:
        self.assertFalse(owns_key(object(), "<Left>"))
        self.assertFalse(owns_key(None, "<Left>"))


class _FakeText(tk.Text):
    def __init__(self) -> None:  # noqa: D107 - sem chamar o __init__ do Tk de proposito
        pass


class _FakeSpinbox(ttk.Spinbox):
    def __init__(self) -> None:  # noqa: D107
        pass


class _FakeCombobox(ttk.Combobox):
    def __init__(self) -> None:  # noqa: D107
        pass


class CederEPorTeclaTests(unittest.TestCase):
    """O campo fica com as teclas que usa, e o app com as outras.

    A guarda cedia **qualquer** sequência a um campo de texto. Consequência medida: com o cursor
    no campo de FEN, `Ctrl+S` não salvava, `Ctrl+R` não relia e `Ctrl+N` não puxava o próximo --
    e nada avisava. O docstring da guarda justificava três teclas, `←`, `→` e `Del`, e cedia
    todas. Aqui a conta fecha: cede-se três, e as demais continuam valendo.
    """

    def _cede(self, widget: object, sequencia: str) -> bool:
        """Se a guarda cedeu aquela tecla naquele widget -- afirmado pelos dois lados."""
        chamadas: list[int] = []
        resultado = guard(lambda: chamadas.append(1), sequencia)(_FakeEvent(widget))
        cedeu = resultado is None
        # ceder e nao rodar o handler sao a mesma resposta escrita duas vezes; se um dia
        # divergirem, o defeito e a acao dupla que a S-117 mediu.
        self.assertEqual(chamadas, [] if cedeu else [1])
        return cedeu

    def test_dentro_de_um_campo_so_as_teclas_do_campo_cedem(self) -> None:
        """O achado, virado teste: a lista dos que cedem contra a dos que ficam."""
        campo = _FakeEntry()
        cedidas = {a.sequencia for a in atalhos.ATALHOS if self._cede(campo, a.sequencia)}

        self.assertEqual(cedidas, {"<Left>", "<Right>", "<Delete>"})

    def test_ctrl_s_com_o_cursor_no_campo_de_fen_salva(self) -> None:
        """A tecla do enunciado: digitar uma FEN e apertar `Ctrl+S` grava o diagrama."""
        salvou: list[int] = []
        resultado = guard(lambda: salvou.append(1), "<Control-s>")(_FakeEvent(_FakeEntry()))

        self.assertEqual(salvou, [1])
        self.assertEqual(resultado, "break")

    def test_as_teclas_de_control_do_app_valem_dentro_de_qualquer_campo(self) -> None:
        """O Tk liga `<Control-Key>` a `# nothing` nas cinco classes: `Control` não é do campo."""
        for widget in (_FakeEntry(), _FakeText(), _FakeSpinbox(), _FakeCombobox()):
            for sequencia in ("<Control-s>", "<Control-S>", "<Control-r>", "<Control-n>", "<Control-0>"):
                with self.subTest(widget=type(widget).__name__, tecla=sequencia):
                    self.assertFalse(self._cede(widget, sequencia))

    def test_a_seta_e_o_delete_continuam_sendo_do_campo(self) -> None:
        """A S-20 não foi desfeita: é ela que este item tinha de preservar."""
        for widget in (_FakeEntry(), _FakeText(), _FakeSpinbox(), _FakeCombobox()):
            for sequencia in ("<Left>", "<Right>", "<Delete>"):
                with self.subTest(widget=type(widget).__name__, tecla=sequencia):
                    self.assertTrue(self._cede(widget, sequencia))

    def test_pgup_rola_a_caixa_de_texto_e_vira_a_pagina_no_campo_de_uma_linha(self) -> None:
        """A razão de a lista ser por classe.

        `bind Text <Prior>` é `tk::TextScrollPages`; `bind Entry <Prior>` é `# nothing`. Ceder
        `PgUp` num `Entry` tirava a virada de página do programa em troca de tecla nenhuma.
        """
        for sequencia in ("<Prior>", "<Next>"):
            with self.subTest(tecla=sequencia):
                self.assertTrue(self._cede(_FakeText(), sequencia))
                self.assertFalse(self._cede(_FakeEntry(), sequencia))

    def test_a_seta_vertical_continua_sendo_do_seletor(self) -> None:
        """O motivo pelo qual o `ttk.Spinbox` entrou na lista da S-20 segue valendo."""
        for sequencia in ("<Up>", "<Down>"):
            with self.subTest(tecla=sequencia):
                self.assertTrue(self._cede(_FakeSpinbox(), sequencia))
        self.assertTrue(self._cede(_FakeCombobox(), "<Down>"), "abre a lista do combo")
        self.assertFalse(self._cede(_FakeCombobox(), "<Up>"), "no combo, `↑` não é do widget")

    def test_o_widget_que_nao_e_campo_nao_cede_nada(self) -> None:
        canvas = tk.Canvas.__new__(tk.Canvas)
        for atalho in atalhos.ATALHOS:
            with self.subTest(tecla=atalho.sequencia):
                self.assertFalse(self._cede(canvas, atalho.sequencia))


class TabelaDeTeclasTests(unittest.TestCase):
    """A tabela `WIDGET_KEYS`, conferida sem abrir janela."""

    def test_a_ordem_poe_o_pai_por_ultimo(self) -> None:
        """`ttk.Combobox` e `ttk.Spinbox` herdam de `tk.Entry`, e vale a primeira que casa.

        Com `tk.Entry` em qualquer lugar que não o fim, os três filhos receberiam a resposta do
        pai -- e `↑` deixaria de incrementar o seletor "Selecionado".
        """
        classes = [classe for classe, _ in WIDGET_KEYS]
        for posicao, classe in enumerate(classes):
            for outra in classes[posicao + 1 :]:
                with self.subTest(primeira=classe.__name__, depois=outra.__name__):
                    self.assertFalse(
                        issubclass(outra, classe) and classe is not outra,
                        f"{outra.__name__} é subclasse de {classe.__name__} e vem depois dela",
                    )
        self.assertIs(classes[-1], tk.Entry, "o pai de três dos cinco fecha a lista")

    def test_toda_classe_de_texto_tem_linha_na_tabela(self) -> None:
        """Um widget em `TEXT_ENTRY_WIDGETS` sem teclas declaradas cederia zero, e a S-20 cairia."""
        for classe in TEXT_ENTRY_WIDGETS:
            with self.subTest(widget=classe.__name__):
                self.assertTrue(keys_of_widget(classe.__new__(classe)))

    def test_todo_campo_de_texto_usa_as_teclas_de_campo(self) -> None:
        for classe in TEXT_ENTRY_WIDGETS:
            with self.subTest(widget=classe.__name__):
                self.assertLessEqual(FIELD_KEYS, keys_of_widget(classe.__new__(classe)))

    def test_quem_nao_e_campo_de_texto_nao_tem_tecla(self) -> None:
        for classe in (tk.Canvas, tk.Frame, ttk.Button, ttk.Label):
            with self.subTest(widget=classe.__name__):
                self.assertEqual(keys_of_widget(classe.__new__(classe)), frozenset())
        self.assertEqual(keys_of_widget(None), frozenset())

    def test_uses_key_e_por_tecla_e_nao_por_widget(self) -> None:
        """A diferença entre esta pergunta e `ignores_widget`, dita nos dois sentidos."""
        campo = _FakeEntry()

        self.assertTrue(ignores_widget(campo), "continua sendo um campo de texto")
        self.assertTrue(uses_key(campo, "<Left>"))
        self.assertFalse(uses_key(campo, "<Control-s>"))

    def test_sem_saber_a_tecla_a_guarda_e_a_antiga(self) -> None:
        """`guard(handler)` sem sequência não tem como separar `←` de `Ctrl+S`.

        A resposta segura para quem está digitando é a anterior: o campo leva tudo. É o mesmo
        contrato de `owns_key`, em que `sequence=""` desliga a pergunta.
        """
        chamadas: list[int] = []
        self.assertIsNone(guard(lambda: chamadas.append(1))(_FakeEvent(_FakeEntry())))
        self.assertEqual(chamadas, [])


def _sem_corpo(script: object) -> bool:
    """Um `bind` cujo corpo só tem comentário não faz nada.

    É como o Tk desliga uma tecla: `bind Entry <Prior> {# nothing}` existe para o `<Key>`
    genérico não inserir caractere, e não para `PgUp` fazer algo num campo de uma linha.
    """
    corpo = "\n".join(linha for linha in str(script).splitlines() if not linha.strip().startswith("#"))
    return not corpo.strip()


def _fisica(sequencia: str) -> str:
    """`<Control-Key-s>` e `<Key-Left>`, como o Tk as devolve, viram `<Control-s>` e `<Left>`."""
    return "<" + sequencia.strip("<>").replace("Key-", "") + ">"


def _teclas_que_o_tk_usa(raiz: tk.Misc, classe_tk: str) -> set[str]:
    """As sequências que aquela classe do Tk usa de verdade.

    **Perguntar direto não serve**, e é o que torna este teste necessário em vez de óbvio:
    `bind Entry <Left>` responde vazio, porque quem está ligado é o evento **virtual**
    `<<PrevChar>>`, e só `event info` conta que ele escuta `<Key-Left>`. Uma regra derivada
    de `bind_class` sem expandir os virtuais deixaria `←` de fora -- justamente a tecla que
    a S-20 mediu.
    """
    usadas: set[str] = set()
    for sequencia in raiz.bind_class(classe_tk):
        if _sem_corpo(raiz.bind_class(classe_tk, sequencia)):
            continue
        if sequencia.startswith("<<"):
            usadas.update(_fisica(evento) for evento in raiz.event_info(sequencia))
        else:
            usadas.add(_fisica(sequencia))
    return usadas


class OQueOTkDizTests(unittest.TestCase):
    """A lista declarada, conferida contra o Tk que roda.

    O módulo declara as teclas em vez de perguntá-las ao Tk, porque a guarda tem de responder
    sem janela aberta -- é o que a torna testável. O preço de declarar é divergir, e são estes
    dois testes que cobram: nada cedido é inerte, e nada que colide fica de fora.
    """

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.quadro = tk.Frame(self.root)
        self.addCleanup(self.quadro.destroy)
        self.campos: list[tk.Misc] = [
            tk.Entry(self.quadro),
            ttk.Entry(self.quadro),
            tk.Text(self.quadro),
            ttk.Combobox(self.quadro),
            ttk.Spinbox(self.quadro),
        ]

    def test_nenhuma_tecla_cedida_e_inerte(self) -> None:
        """Ceder uma tecla que o widget não usa é o defeito deste item, na direção contrária.

        Foi assim que `PgUp` sumiu: cedida a um `Entry` em que o Tk a liga a `# nothing`, ela
        não rolava nada lá e não virava página em lugar nenhum.
        """
        for campo in self.campos:
            usadas = _teclas_que_o_tk_usa(self.root, campo.winfo_class())
            for sequencia in sorted(keys_of_widget(campo)):
                with self.subTest(widget=campo.winfo_class(), tecla=sequencia):
                    self.assertIn(
                        sequencia,
                        usadas,
                        f"{sequencia} está declarada para {campo.winfo_class()} e o Tk não a usa",
                    )

    def test_nenhum_atalho_do_app_pisa_numa_tecla_do_campo(self) -> None:
        """A guarda contra o defeito simétrico: ceder de menos.

        Se o Tk usa a tecla e a tabela não a declara, a guarda deixa o atalho global disparar
        dentro do campo -- que é a ação dupla da S-20 de volta. Este teste pega o atalho novo
        que cai numa tecla do campo **e que ninguém declarou**; quando ela já está declarada,
        quem cobra a decisão é o inventário de `InventarioDoQueOCampoEngoleTests`.
        """
        for campo in self.campos:
            usadas = _teclas_que_o_tk_usa(self.root, campo.winfo_class())
            declaradas = keys_of_widget(campo)
            for atalho in atalhos.ATALHOS:
                if atalho.sequencia not in usadas:
                    continue
                with self.subTest(widget=campo.winfo_class(), tecla=atalho.rotulo):
                    self.assertIn(
                        atalho.sequencia,
                        declaradas,
                        f"{atalho.rotulo} ({atalho.acao}) é do {campo.winfo_class()} e não está na tabela",
                    )

    def test_o_campo_que_declarou_a_tecla_fica_com_ela(self) -> None:
        """O caminho da S-223: `Ctrl+Enter` no campo de FEN.

        `uses_key` diz não -- o Tk não usa `Ctrl+Enter` num `Entry` --, e é `owns_key` (S-117)
        que responde sim. Uma declaração em `ui/atalhos.py`, duas ligações.
        """
        campo = ttk.Entry(self.quadro)
        campo.bind("<Control-Return>", lambda _e: None)
        disparos: list[str] = []
        protegido = guard(lambda: disparos.append("app"), "<Control-Return>")

        evento = tk.Event()
        evento.widget = campo  # type: ignore[assignment]
        self.assertFalse(uses_key(campo, "<Control-Return>"), "o Tk não usa essa tecla num Entry")
        self.assertIsNone(protegido(evento), "cedeu, porque o campo declarou a tecla")
        self.assertEqual(disparos, [])

    def test_e_um_campo_vizinho_que_nao_declarou_nao_fica(self) -> None:
        """A ligação é do campo que a declarou, e não da classe dele."""
        vizinho = ttk.Entry(self.quadro)
        disparos: list[str] = []
        evento = tk.Event()
        evento.widget = vizinho  # type: ignore[assignment]

        self.assertEqual(guard(lambda: disparos.append("app"), "<Control-Return>")(evento), "break")
        self.assertEqual(disparos, ["app"])


if __name__ == "__main__":
    unittest.main()


class InventarioDoQueOCampoEngoleTests(unittest.TestCase):
    """Quais atalhos ficam inertes dentro de um campo de texto, e em qual campo.

    **É o teste que faltava quando o defeito foi escrito.** A guarda cedia dez de dez, o
    docstring justificava três, e ninguém tinha a lista -- o achado da S-223 precisou ser
    medido à mão para dizer que `Ctrl+S` não salvava. Com a lista escrita, qualquer mudança
    nos dois lados (uma tecla nova em `ATALHOS`, ou uma classe cedendo mais) aparece aqui.

    Não precisa de janela: cruza `ATALHOS` com `WIDGET_KEYS`, e as duas são declaração.
    """

    def _nome(self, classe: type) -> str:
        return f"{classe.__module__.rsplit('.', 1)[-1]}.{classe.__name__}"

    def test_o_inventario_de_quem_engole_o_que(self) -> None:
        engolidos = {
            atalho.rotulo: sorted(
                self._nome(classe)
                for classe in TEXT_ENTRY_WIDGETS
                if uses_key(classe.__new__(classe), atalho.sequencia)
            )
            for atalho in atalhos.ATALHOS
        }
        todos = ["tkinter.Entry", "tkinter.Text", "ttk.Combobox", "ttk.Entry", "ttk.Spinbox"]

        self.assertEqual(
            {rotulo: onde for rotulo, onde in engolidos.items() if onde},
            {
                # as três da S-20: movem o cursor e apagam caractere em qualquer campo
                "←": todos,
                "→": todos,
                "Del": todos,
                # e a caixa multilinha rola com elas; num campo de uma linha, não
                "Page Up": ["tkinter.Text"],
                "Page Down": ["tkinter.Text"],
            },
            "mudou quem engole o quê -- se foi de propósito, é aqui que se escreve",
        )

    def test_nenhum_atalho_de_control_do_app_e_engolido(self) -> None:
        """`Ctrl+S`, `Ctrl+Shift+S`, `Ctrl+R`, `Ctrl+N`, `Ctrl+0` -- e o `Ctrl+Enter` que vier.

        Nenhum campo de texto os usa: nas cinco classes, `bind <Control-Key>` é `# nothing`.
        Eram cinco teclas mortas dentro de qualquer `Entry`, e é o miolo do defeito.
        """
        for atalho in atalhos.ATALHOS:
            if not atalho.sequencia.startswith("<Control-"):
                continue
            for classe in TEXT_ENTRY_WIDGETS:
                with self.subTest(tecla=atalho.rotulo, widget=classe.__name__):
                    self.assertFalse(uses_key(classe.__new__(classe), atalho.sequencia))
