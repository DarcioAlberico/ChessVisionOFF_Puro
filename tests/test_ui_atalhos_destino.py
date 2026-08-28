"""`Ctrl+S` no editor salva o editor: o destino conforme o foco (S-244).

**O defeito eram duas camadas somadas.** `shortcuts.TEXT_ENTRY_WIDGETS` inclui `tk.Text`, e a
guarda cede a tecla quando o foco está num deles -- deliberado desde a S-20, e por medição: `←`
dentro de um campo pertence ao campo. Do lado do Tk, `bind Text <Control-KeyPress> {# nothing}` come
o que sobrou. Resultado: com o cursor no texto, `Ctrl+S` não salvava a posição (a guarda cedeu) e
não salvava o texto (ninguém ligou). **A tecla mais esperada de um editor era um silêncio de duas
camadas.**

A saída não é tirar a guarda nem acrescentar tecla: é tornar o ceder **tipado**. O painel em foco
declara quais ações são dele, e a guarda pergunta antes de ceder.
"""

from __future__ import annotations

import tkinter as tk
import unittest

from ambiente_de_teste import pasta_temporaria
from tk_root import raiz as raiz_do_processo

from chess_diagram_ocr.ui import atalhos, shortcuts, texto_panel
from chess_diagram_ocr.ui.busy import BusyRegistry
from chess_diagram_ocr.ui.texto_panel import TextoPanel


class _Dono:
    """Um painel de mentira que declara ações para si."""

    def __init__(self, acoes: set[str], master: object = None) -> None:
        self._acoes = frozenset(acoes)
        self.master = master
        self.chamadas: list[str] = []

    def acoes_proprias(self) -> frozenset[str]:
        return self._acoes

    def atender(self, acao: str):  # noqa: ANN201 - Callable | None
        if acao not in self._acoes:
            return None
        return lambda: self.chamadas.append(acao)


class DestinoTests(unittest.TestCase):
    def test_o_foco_escolhe_o_destino(self) -> None:
        dono = _Dono({"salvar"})
        globais = {"salvar": lambda: None}
        alvo = atalhos.destino("salvar", dono, globais)
        self.assertIsNotNone(alvo)
        alvo()  # type: ignore[misc]
        self.assertEqual(dono.chamadas, ["salvar"])

    def test_sem_declaracao_vale_o_global(self) -> None:
        chamadas: list[str] = []
        dono = _Dono({"achar"})
        alvo = atalhos.destino("salvar", dono, {"salvar": lambda: chamadas.append("global")})
        self.assertIsNotNone(alvo)
        alvo()  # type: ignore[misc]
        self.assertEqual(chamadas, ["global"])
        self.assertEqual(dono.chamadas, [])

    def test_o_dono_e_procurado_nos_pais_do_widget_em_foco(self) -> None:
        """Quem declara é o **painel**; quem tem o foco é o `tk.Text` dentro dele."""
        painel = _Dono({"salvar"})
        campo = _Dono(set(), master=painel)
        alvo = atalhos.destino("salvar", campo, {})
        self.assertIsNotNone(alvo)
        alvo()  # type: ignore[misc]
        self.assertEqual(painel.chamadas, ["salvar"])

    def test_sem_foco_e_sem_global_nao_ha_destino(self) -> None:
        """`None` em vez de uma função vazia: uma tecla ligada a comando que a janela não montou é
        um caso real (o roteiro headless), e esconder isso faria a tecla parecer viva."""
        self.assertIsNone(atalhos.destino("salvar", None, {}))

    def test_acao_declarada_sem_implementacao_levanta(self) -> None:
        """Declarar "eu trato salvar" e não tratar come a tecla e não faz nada -- pior que não
        declarar, porque o global também deixa de responder."""

        class Mentiroso:
            def acoes_proprias(self) -> frozenset[str]:
                return frozenset({"salvar", "achar"})

            def atender(self, acao: str):  # noqa: ANN201
                return (lambda: None) if acao == "achar" else None

        with self.assertRaises(KeyError) as erro:
            atalhos.conferir_dono(Mentiroso(), "Mentiroso")
        self.assertIn("salvar", str(erro.exception))

    def test_a_aba_de_texto_cumpre_o_que_declara(self) -> None:
        """O mesmo crivo, sobre o painel de verdade: é o que roda na montagem da janela."""
        raiz = _raiz()
        painel = TextoPanel(
            raiz,
            pdf_path=lambda: None,
            page_index=lambda: 0,
            on_status=lambda _m: None,
            busy=BusyRegistry(),
            pasta_de_rascunhos=pasta_temporaria(self),
        )
        atalhos.conferir_dono(painel, "TextoPanel")
        self.assertEqual(painel.acoes_proprias(), texto_panel.ACOES_PROPRIAS)


class NenhumaTeclaNovaTests(unittest.TestCase):
    def test_a_tabela_tem_as_vinte_e_uma_teclas(self) -> None:
        """Catorze da S-244 -- que era o **oposto** de acrescentar teclas: `Ctrl+S` continua sendo
        uma tecla só, e o que ela mudou foi o destino conforme o foco --, mais as duas da S-267 e as
        duas da S-281.

        As da S-267 não contradizem aquilo. Elas não dão um segundo destino a tecla nenhuma:
        `achar` e `substituir` já estavam declarados em `texto_panel.ACOES_PROPRIAS` e **não tinham
        tecla**, então a declaração da aba não fazia nada.

        As da S-281 são o caso oposto e igualmente honesto: `Home` e `End` **têm** dois destinos --
        primeira/última página na janela, início/fim da linha na sala --, e por isso elas declaram
        `na_sala` e a legenda mostra as duas linhas. O que elas acrescentam ao resto do programa é o
        par que faltava desde a S-70: virar uma página tinha tecla, e ir à ponta não tinha.

        **As três da S-333 são do mesmo tipo das da S-281**: aumentar, diminuir e ajustar à
        página são comandos que já existiam na barra do visualizador e não tinham tecla nenhuma.
        Duas delas têm segundo destino declarado -- dentro do editor, `Ctrl++` e `Ctrl+-` mexem
        no corpo do texto --, e é por isso que aparecem em `SOBREPOSICOES_NO_EDITOR`."""
        self.assertEqual(len(atalhos.ATALHOS), 21)
        self.assertEqual(atalhos.acao_de("<Home>"), "primeira_pagina")
        self.assertEqual(atalhos.acao_de("<End>"), "ultima_pagina")
        self.assertEqual(atalhos.acao_de("<Control-f>"), "achar")
        self.assertEqual(atalhos.acao_de("<Control-h>"), "substituir")
        self.assertEqual(atalhos.acao_de("<Control-plus>"), "zoom_mais")
        self.assertEqual(atalhos.acao_de("<Control-minus>"), "zoom_menos")
        self.assertEqual(atalhos.acao_de("<Control-9>"), "ajustar_pagina")

    def test_toda_acao_propria_da_aba_tem_tecla(self) -> None:
        """**A declaração vazia que a S-267 fecha.** `ACOES_PROPRIAS` diz "esta aba atende esta ação
        global enquanto tem o foco"; sem tecla global, não há o que atender -- a linha existia e não
        fazia nada. É a mesma classe de defeito do item de menu sem comando (S-161)."""
        from chess_diagram_ocr.ui import texto_panel

        sem_tecla = sorted(a for a in texto_panel.ACOES_PROPRIAS if a not in atalhos.por_acao)
        self.assertEqual(sem_tecla, [], "ação declarada como própria da aba e sem tecla na janela")

    def test_a_tecla_de_salvar_declara_os_dois_destinos(self) -> None:
        self.assertTrue(atalhos.por_acao["salvar"].no_editor)
        self.assertTrue(atalhos.por_acao["desfazer"].no_editor)
        self.assertTrue(atalhos.por_acao["refazer"].no_editor)

    def test_as_teclas_do_editor_estao_declaradas_na_tabela(self) -> None:
        """As do editor não são atalhos da janela e mesmo assim são declaradas em `ui/atalhos.py`:
        neste projeto, tecla escrita num painel é o que o teste da legenda proíbe."""
        self.assertEqual(
            set(atalhos.TECLAS_DO_EDITOR),
            {
                "negrito",
                "italico",
                "sublinhado",
                "alinhar_esquerda",
                "alinhar_centro",
                "alinhar_direita",
                "justificar",
                "aumentar_corpo",
                "diminuir_corpo",
                "selecionar_tudo",
                "aproximar_texto",
                "afastar_texto",
                # `substituir` está nas duas tabelas de propósito -- ver `SOBREPOSICOES_NO_EDITOR`.
                "substituir",
            },
        )
        self.assertEqual(atalhos.TECLAS_DO_EDITOR["italico"], "<Control-i>")

    def test_toda_sobreposicao_entre_as_duas_tabelas_esta_declarada(self) -> None:
        """**As duas tabelas são desligadas, e é isso que as faz poder se sobrepor.**

        `ATALHOS` passa pela guarda de foco de `ui/shortcuts.py`; `TECLAS_DO_EDITOR` é `Text.bind` e
        só vale dentro do widget -- mas os dois `bind` existem ao mesmo tempo, e a mesma sequência
        nas duas põe a tecla com dois donos quando o cursor está no texto. Nenhum dos dois lados
        olhava para o outro; este teste é o que os olha, e ele exige **declaração**, não ausência --
        ver `atalhos.SOBREPOSICOES_NO_EDITOR`."""
        sobrepostas = set(atalhos.TECLAS_DO_EDITOR.values()) & set(atalhos.por_sequencia)
        self.assertEqual(
            sobrepostas,
            set(atalhos.SOBREPOSICOES_NO_EDITOR),
            "sobreposição entre as duas tabelas sem declaração em SOBREPOSICOES_NO_EDITOR",
        )

    def test_toda_sobreposicao_declara_um_motivo_conhecido(self) -> None:
        motivos = {atalhos.CEDIDA_PELA_GUARDA, atalhos.GANHA_DO_TK}
        self.assertLessEqual(set(atalhos.SOBREPOSICOES_NO_EDITOR.values()), motivos)
        for sequencia in atalhos.SOBREPOSICOES_NO_EDITOR:
            with self.subTest(sequencia=sequencia):
                self.assertTrue(atalhos.acao_de(sequencia), "sequência que não é atalho da janela")

    def test_a_tecla_cedida_pela_guarda_nao_e_acao_propria_da_aba(self) -> None:
        """**A razão do primeiro motivo, virada teste.**

        `CEDIDA_PELA_GUARDA` só vale porque a guarda cede a tecla a todo widget de texto (S-20) *e*
        porque a aba **não** toma aquela ação para si. Se um dos dois deixar de valer, a tecla passa
        a ter dois donos de verdade dentro do editor."""
        self.assertIn(tk.Text, shortcuts.TEXT_ENTRY_WIDGETS)
        for sequencia, motivo in atalhos.SOBREPOSICOES_NO_EDITOR.items():
            if motivo != atalhos.CEDIDA_PELA_GUARDA:
                continue
            with self.subTest(sequencia=sequencia):
                self.assertNotIn(atalhos.acao_de(sequencia), texto_panel.ACOES_PROPRIAS)

    def test_a_tecla_que_ganha_do_tk_faz_a_mesma_acao_nos_dois_lados(self) -> None:
        """**A razão do segundo motivo.** `GANHA_DO_TK` é a mesma ação nas duas tabelas: o `bind` no
        widget existe só para rodar **antes** da classe `Text`, que faria outra coisa com a tecla.
        Duas ações diferentes ali seriam a colisão que esta tabela existe para não esconder."""
        for sequencia, motivo in atalhos.SOBREPOSICOES_NO_EDITOR.items():
            if motivo != atalhos.GANHA_DO_TK:
                continue
            with self.subTest(sequencia=sequencia):
                acao = atalhos.acao_de(sequencia)
                self.assertIn(acao, texto_panel.ACOES_PROPRIAS)
                self.assertEqual(atalhos.TECLAS_DO_EDITOR.get(acao), sequencia)

    def test_toda_tecla_do_editor_tem_metodo_no_painel(self) -> None:
        """O nome do comando **é** o nome do método (`texto_panel._ligar_teclas`, por `getattr`).

        Uma tecla nova sem método levantaria `AttributeError` na montagem da aba -- e a montagem da
        aba acontece na abertura da janela, o que faria uma tecla mal declarada derrubar o programa
        inteiro. Aqui isso custa um teste sem Tk."""
        for acao in atalhos.TECLAS_DO_EDITOR:
            with self.subTest(acao=acao):
                self.assertTrue(hasattr(TextoPanel, acao), f"{acao} não tem método no painel")

    def test_a_acao_sai_da_sequencia(self) -> None:
        """É por aqui que a guarda descobre que ação a tecla pede, sem receber o nome de fora."""
        self.assertEqual(atalhos.acao_de("<Control-s>"), "salvar")
        self.assertEqual(atalhos.acao_de("<Control-inventado>"), "")


_RAIZ: tk.Tk | None = None


def _raiz() -> tk.Tk:
    assert _RAIZ is not None
    return _RAIZ


def setUpModule() -> None:
    """A raiz é a do processo (`tests/tk_root.py`), e não uma deste módulo (S-416)."""
    global _RAIZ
    _RAIZ = raiz_do_processo()


class GuardaComFocoTests(unittest.TestCase):
    """A guarda de verdade, com um evento de verdade -- é ela que decide o que a tecla faz."""

    def setUp(self) -> None:
        self.chamadas: list[str] = []

    def _evento(self, widget: object) -> tk.Event:
        evento = tk.Event()
        evento.widget = widget  # type: ignore[attr-defined]
        return evento

    def test_ctrl_s_no_editor_grava_o_documento(self) -> None:
        painel = TextoPanel(
            _raiz(),
            pdf_path=lambda: None,
            page_index=lambda: 0,
            on_status=lambda _m: None,
            busy=BusyRegistry(),
            pasta_de_rascunhos=pasta_temporaria(self),
        )
        gravou: list[str] = []
        painel.salvar_documento = lambda: gravou.append("texto")  # type: ignore[method-assign]

        tratador = shortcuts.guard(lambda: self.chamadas.append("posicao"), "<Control-s>")
        resposta = tratador(self._evento(painel.editor))

        self.assertEqual(gravou, ["texto"])
        self.assertEqual(self.chamadas, [])
        self.assertEqual(resposta, "break")

    def test_ctrl_s_fora_do_editor_salva_a_posicao(self) -> None:
        """Com o foco em qualquer outro lugar, **sem diferença nenhuma** em relação a antes."""
        tratador = shortcuts.guard(lambda: self.chamadas.append("posicao"), "<Control-s>")
        resposta = tratador(self._evento(_raiz()))
        self.assertEqual(self.chamadas, ["posicao"])
        self.assertEqual(resposta, "break")

    def test_as_setas_continuam_do_editor(self) -> None:
        """A guarda da S-20 continua valendo: `←` dentro de um campo de texto é do campo.

        O painel não declara `diagrama_anterior`, então a pergunta nova não responde e a resposta
        antiga vale -- ceder, devolvendo `None` para o Tk repassar a tecla ao widget.
        """
        painel = TextoPanel(
            _raiz(),
            pdf_path=lambda: None,
            page_index=lambda: 0,
            on_status=lambda _m: None,
            busy=BusyRegistry(),
            pasta_de_rascunhos=pasta_temporaria(self),
        )
        tratador = shortcuts.guard(lambda: self.chamadas.append("diagrama"), "<Left>")
        resposta = tratador(self._evento(painel.editor))
        self.assertIsNone(resposta)
        self.assertEqual(self.chamadas, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
