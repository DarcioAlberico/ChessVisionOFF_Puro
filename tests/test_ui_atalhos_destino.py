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

import tempfile
import tkinter as tk
import unittest
from pathlib import Path

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
            pasta_de_rascunhos=Path(tempfile.mkdtemp()),
        )
        atalhos.conferir_dono(painel, "TextoPanel")
        self.assertEqual(painel.acoes_proprias(), texto_panel.ACOES_PROPRIAS)


class NenhumaTeclaNovaTests(unittest.TestCase):
    def test_nenhuma_sequencia_nova_entra_na_tabela(self) -> None:
        """O item é o **oposto** de acrescentar teclas: `Ctrl+S` continua sendo uma tecla só, com
        um rótulo só na legenda, e o que muda é ela ter destino conforme o foco."""
        self.assertEqual(len(atalhos.ATALHOS), 14)

    def test_a_tecla_de_salvar_declara_os_dois_destinos(self) -> None:
        self.assertTrue(atalhos.por_acao["salvar"].no_editor)
        self.assertTrue(atalhos.por_acao["desfazer"].no_editor)
        self.assertTrue(atalhos.por_acao["refazer"].no_editor)

    def test_as_teclas_do_editor_estao_declaradas_na_tabela(self) -> None:
        """As três de formato não são atalhos da janela e mesmo assim são declaradas em
        `ui/atalhos.py`: neste projeto, tecla escrita num painel é o que o teste da legenda proíbe."""
        self.assertEqual(set(atalhos.TECLAS_DO_EDITOR), {"negrito", "italico", "sublinhado"})
        self.assertEqual(atalhos.TECLAS_DO_EDITOR["italico"], "<Control-i>")

    def test_a_acao_sai_da_sequencia(self) -> None:
        """É por aqui que a guarda descobre que ação a tecla pede, sem receber o nome de fora."""
        self.assertEqual(atalhos.acao_de("<Control-s>"), "salvar")
        self.assertEqual(atalhos.acao_de("<Control-inventado>"), "")


_RAIZ: tk.Tk | None = None


def _raiz() -> tk.Tk:
    assert _RAIZ is not None
    return _RAIZ


def setUpModule() -> None:
    global _RAIZ
    try:
        _RAIZ = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - maquina sem display
        raise unittest.SkipTest(f"sem Tk disponível: {exc}") from exc
    _RAIZ.withdraw()


def tearDownModule() -> None:
    global _RAIZ
    if _RAIZ is not None:
        _RAIZ.destroy()
        _RAIZ = None


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
            pasta_de_rascunhos=Path(tempfile.mkdtemp()),
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
            pasta_de_rascunhos=Path(tempfile.mkdtemp()),
        )
        tratador = shortcuts.guard(lambda: self.chamadas.append("diagrama"), "<Left>")
        resposta = tratador(self._evento(painel.editor))
        self.assertIsNone(resposta)
        self.assertEqual(self.chamadas, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
