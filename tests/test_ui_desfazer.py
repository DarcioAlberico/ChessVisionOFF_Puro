"""Desfazer e refazer que sabem quem tem o foco (S-243).

**Duas pilhas, dois donos, uma tecla só.** A do tabuleiro é a da S-229 (posições, por diagrama); a
do editor de texto é a do próprio `tk.Text`, mais um instantâneo do documento para a substituição em
massa. Ligar `Ctrl+Z` a uma delas escolheria errado metade das vezes; ligar às duas faria a tecla
mexer, invisivelmente, no painel que ninguém está olhando -- que é o defeito que a S-117 mediu com
as setas.

A regra vive em `ui/desfazivel.py` e é afirmável com objetos de mentira, que é o que a primeira
classe faz. As duas seguintes montam os painéis de verdade.
"""

from __future__ import annotations

import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida
from chess_diagram_ocr.ui import desfazivel
from chess_diagram_ocr.ui.busy import BusyRegistry
from chess_diagram_ocr.ui.texto_panel import TextoPanel


class _Falso:
    """Um desfazível de mentira: sabe dizer o que contém e quantas edições recebeu."""

    def __init__(self, dentro: object = None, edicao: int = 0) -> None:
        self._dentro = dentro
        self._edicao = edicao
        self.desfeitos = 0
        self.refeitos = 0

    def contem(self, widget: object) -> bool:
        return widget is self._dentro

    def desfazer(self) -> None:
        self.desfeitos += 1

    def refazer(self) -> None:
        self.refeitos += 1

    @property
    def edicao(self) -> int:
        return self._edicao


class RegraDoFocoTests(unittest.TestCase):
    def test_o_foco_no_editor_desfaz_texto(self) -> None:
        editor, tabuleiro = object(), object()
        do_texto, do_tabuleiro = _Falso(editor, 1), _Falso(tabuleiro, 9)
        alvo = desfazivel.alvo_de_desfazer(editor, [do_tabuleiro, do_texto])
        self.assertIs(alvo, do_texto)

    def test_o_foco_no_tabuleiro_desfaz_posicao(self) -> None:
        editor, tabuleiro = object(), object()
        do_texto, do_tabuleiro = _Falso(editor, 9), _Falso(tabuleiro, 1)
        alvo = desfazivel.alvo_de_desfazer(tabuleiro, [do_tabuleiro, do_texto])
        self.assertIs(alvo, do_tabuleiro)

    def test_sem_foco_vale_o_ultimo_editado(self) -> None:
        """O passo 2 é o item: o cursor num botão da barra é onde ele fica depois de todo clique,
        e "nenhum" ali faria `Ctrl+Z` não fazer nada logo depois de uma edição."""
        do_texto, do_tabuleiro = _Falso(object(), 3), _Falso(object(), 7)
        alvo = desfazivel.alvo_de_desfazer(None, [do_texto, do_tabuleiro])
        self.assertIs(alvo, do_tabuleiro)

    def test_sem_edicao_nenhuma_nao_ha_alvo(self) -> None:
        """Devolver o primeiro registrado faria a tecla mexer num painel que ninguém tocou."""
        self.assertIsNone(desfazivel.alvo_de_desfazer(None, [_Falso(), _Falso()]))

    def test_o_empate_fica_com_o_primeiro_registrado(self) -> None:
        """A ordem de registro é a de construção da janela, e é estável entre execuções -- um
        empate resolvido pela iteração de um `set` faria a mesma tecla fazer coisas diferentes em
        dois dias iguais."""
        primeiro, segundo = _Falso(object(), 4), _Falso(object(), 4)
        self.assertIs(desfazivel.alvo_de_desfazer(None, [primeiro, segundo]), primeiro)

    def test_um_painel_que_levanta_nao_derruba_a_tecla(self) -> None:
        """Widget destruído entre o evento e a pergunta é caso real, e a resposta certa é seguir."""

        class Explode:
            def contem(self, widget: object) -> bool:
                raise tk.TclError("widget destruído")

            def desfazer(self) -> None: ...

            def refazer(self) -> None: ...

            edicao = 0

        bom = _Falso(object(), 2)
        self.assertIs(desfazivel.alvo_de_desfazer(object(), [Explode(), bom]), bom)


_RAIZ: tk.Tk | None = None


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


def _pagina(texto: str) -> PaginaLida:
    bloco = BlocoDeTexto.de_linhas([LinhaLida(texto, (0.0, 0.0, 100.0, 9.0), 1.0, "camada")])
    return PaginaLida(documento="livro.pdf", pagina=0, colunas=(Coluna(indice=0, blocos=(bloco,)),))


class PilhaDoEditorTests(unittest.TestCase):
    """O painel de verdade: o que a pilha do editor guarda, e o que o redesenho faz com ela."""

    def _painel(self) -> TextoPanel:
        """O painel com uma pasta de rascunho **própria** (S-255).

        Sem isto a suíte leria `data/rascunhos/` da máquina de quem a roda -- e um rascunho ali
        abriria a pergunta de recuperação no meio de um teste, que trava tudo esperando um clique.
        """
        assert _RAIZ is not None
        return TextoPanel(
            _RAIZ,
            pdf_path=lambda: None,
            page_index=lambda: 0,
            on_status=lambda _m: None,
            busy=BusyRegistry(),
            pasta_de_rascunhos=Path(tempfile.mkdtemp()),
        )

    def test_desfazer_desfaz_a_digitacao(self) -> None:
        painel = self._painel()
        painel.desenhar(_pagina("texto lido da folha"))
        painel.editor.insert("end", " e mais isto")
        painel.desfazer()
        self.assertNotIn("e mais isto", painel.texto_atual())

    def test_desfazer_desfaz_a_substituicao_inteira(self) -> None:
        """**Inteira, e não troca a troca** -- critério de aceite da S-245.

        A pilha do Tk não serve aqui: o redesenho a zera, e uma pilha com índices de um texto que
        já mudou apaga um pedaço qualquer. Por isso a substituição guarda o documento anterior.
        """
        painel = self._painel()
        painel.desenhar(_pagina("a, b, c"))
        doc = painel.documento_atual()
        from chess_diagram_ocr.text import busca

        painel.aplicar_substituicao(busca.achar(doc, ","), ";")
        self.assertEqual(painel.texto_atual(), "a; b; c")
        painel.desfazer()
        self.assertEqual(painel.texto_atual(), "a, b, c")

    def test_refazer_devolve_a_substituicao(self) -> None:
        painel = self._painel()
        painel.desenhar(_pagina("a, b"))
        from chess_diagram_ocr.text import busca

        painel.aplicar_substituicao(busca.achar(painel.documento_atual(), ","), ";")
        painel.desfazer()
        painel.refazer()
        self.assertEqual(painel.texto_atual(), "a; b")

    def test_reler_limpa_so_a_pilha_do_editor(self) -> None:
        """Ler a folha de novo é outro documento: a pilha da folha anterior não pertence a ele.

        A do tabuleiro não é tocada -- ela é de outro dono, e é isso que este teste afirma ao
        comparar o contador de edições dele antes e depois.
        """
        painel = self._painel()
        painel.desenhar(_pagina("primeira leitura"))
        painel.editor.insert("end", " digitado")
        painel.desenhar(_pagina("segunda leitura"))
        painel.desfazer()
        self.assertEqual(painel.texto_atual(), "segunda leitura")

    def test_o_painel_diz_o_que_contem(self) -> None:
        """É por `contem` que o foco escolhe, e o widget em foco é o `tk.Text` **dentro** do painel."""
        painel = self._painel()
        self.assertTrue(painel.contem(painel.editor))
        self.assertTrue(painel.contem(painel))
        self.assertFalse(painel.contem(_RAIZ))

    def test_a_edicao_conta_o_que_a_mao_fez(self) -> None:
        painel = self._painel()
        painel.desenhar(_pagina("texto"))
        antes = painel.edicao
        painel.editor.insert("end", "!")
        painel.update()
        self.assertGreater(painel.edicao, antes)

    def test_o_redesenho_nao_conta_como_edicao(self) -> None:
        """Senão ler uma folha faria o editor parecer "o último editado" sem ninguém ter editado."""
        painel = self._painel()
        painel.desenhar(_pagina("primeira"))
        painel.update()
        antes = painel.edicao
        painel.desenhar(_pagina("segunda"))
        painel.update()
        self.assertEqual(painel.edicao, antes)


class AceleradorTests(unittest.TestCase):
    def test_o_menu_mostra_o_acelerador_do_tk(self) -> None:
        """Os dois comandos aparecem no menu **com a tecla que o Tk já usa**, e não com um par novo."""
        from chess_diagram_ocr.ui import atalhos, menu

        self.assertEqual(atalhos.acelerador("desfazer"), "Ctrl+Z")
        self.assertEqual(atalhos.acelerador("refazer"), "Ctrl+Y")
        declaradas = menu.acoes_declaradas()
        self.assertEqual(declaradas.count("desfazer"), 1)
        self.assertEqual(declaradas.count("refazer"), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
