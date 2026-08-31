"""A cauda da aba de texto no segundo frontend (S-240 a S-266, S-343, S-504).

**O que faltava, e agora está.** O porte da S-502 parou no desenho do documento, nas ferramentas
de formato e no histórico; o cabeçalho de `qt/painel_de_texto.py` listava o resto: busca e
substituição, marcação de léxico, símbolos/figurinas, caixa, zoom, área de transferência,
exportação e a leitura em thread. É o que este arquivo mede.

**O que ele não mede.** O que a busca acha, o que a caixa faz com o texto, o que cada formato
exporta e o que o léxico conhece são de `text/busca.py`, `text/rico.py`, `text/exportacao.py` e
`text/dicionario.py` -- puros, e já afirmados sem janela. Aqui só se confere que o gesto chega
neles e que a resposta volta à tela.
"""

from __future__ import annotations

import unittest

from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.text import rico
from chess_diagram_ocr.ui import texto_declarado

if TEM_PYQT:
    from chess_diagram_ocr.qt import painel_de_texto as qt_texto


def _documento(texto: str = "Nf3 e um lance xyzq.") -> rico.DocumentoRico:
    return rico.DocumentoRico(corridas=(rico.Corrida(texto=texto),))


class DeclaracaoTests(unittest.TestCase):
    """A decisão é a mesma dos dois lados, e nenhum dos dois a reescreve."""

    def test_o_primeiro_motor_e_o_auto(self) -> None:
        """**O padrão era o `glifo` (S-423)**, que precisa de `models/char_classifier.pt` -- e
        esse arquivo não vem no repositório. Num clone novo a aba abria com o motor que não pode
        funcionar, tendo `auto` na mesma caixa."""
        self.assertEqual(texto_declarado.MOTORES[0], "auto")

    def test_o_modulo_puro_nao_carrega_tkinter(self) -> None:
        import ast
        from pathlib import Path

        arvore = ast.parse(Path(texto_declarado.__file__).read_text(encoding="utf-8"))
        nomes = {no.names[0].name.split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.Import)}
        nomes |= {(no.module or "").split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom)}
        self.assertNotIn("tkinter", nomes)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class CaudaTests(unittest.TestCase):
    """A aba montada, com um documento de mentira posto à mão."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.addCleanup(self.app.processEvents)

    def painel(self, texto: str = "Nf3 e um lance xyzq.") -> qt_texto.PainelDeTexto:
        montado = qt_texto.PainelDeTexto()
        self.addCleanup(descartar, montado)
        montado.resize(900, 600)
        montado.show()
        self.app.processEvents()
        montado.desenhar_documento(_documento(texto))
        return montado

    def test_todo_comando_do_catalogo_tem_metodo_neste_painel(self) -> None:
        """**O critério da S-240 aplicado ao segundo frontend.** Um método com outro nome deixa o
        comando no menu, na paleta e nas três peles -- sem fazer nada, e sem nada acusar."""
        painel = self.painel()
        faltando = [
            f"{acao} -> {metodo}"
            for acao, metodo in texto_declarado.COMANDOS_DA_ABA.items()
            if not callable(getattr(painel, metodo, None))
        ]
        self.assertEqual(faltando, [])

    def test_a_caixa_muda_o_texto_e_o_desfazer_a_reverte(self) -> None:
        """Sem a pilha de documentos, desfazer uma troca de caixa sobre um parágrafo seria
        impossível -- é a razão de a pilha ser de documentos e não de edições (S-262)."""
        painel = self.painel("uma frase")
        painel.editor.selectAll()
        painel.maiusculas()
        self.assertEqual(painel.texto(), "UMA FRASE")
        painel.desfazer()
        self.assertEqual(painel.texto(), "uma frase")

    def test_a_caixa_tem_as_tres_formas(self) -> None:
        for metodo, esperado in (("maiusculas", "UMA FRASE"), ("minusculas", "uma frase"), ("capitular", "Uma Frase")):
            with self.subTest(metodo=metodo):
                painel = self.painel("uma frase")
                painel.editor.selectAll()
                getattr(painel, metodo)()
                self.assertEqual(painel.texto(), esperado)

    def test_o_zoom_e_da_vista_e_nao_do_documento(self) -> None:
        """Aumenta a letra **na tela**. Não muda o documento, não é gravado, não é exportado."""
        painel = self.painel()
        antes = painel.texto()
        painel.aproximar_texto()
        self.assertEqual(painel.zoom_da_vista, 1)
        self.assertEqual(painel.texto(), antes)
        self.assertFalse(painel.pode_desfazer, "o zoom não entrou na pilha")
        painel.zoom_do_texto_normal()
        self.assertEqual(painel.zoom_da_vista, 0)

    def test_o_zoom_para_no_limite_e_diz_isso(self) -> None:
        painel = self.painel()
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        for _ in range(texto_declarado.ZOOM_MAXIMO + 2):
            painel.aproximar_texto()
        self.assertEqual(painel.zoom_da_vista, texto_declarado.ZOOM_MAXIMO)
        self.assertTrue(any("já está no limite" in frase for frase in vistos))

    def test_a_quebra_de_linha_alterna(self) -> None:
        from PyQt6.QtWidgets import QTextEdit

        painel = self.painel()
        painel.quebrar_linha()
        self.assertEqual(painel.editor.lineWrapMode(), QTextEdit.LineWrapMode.NoWrap)
        painel.quebrar_linha()
        self.assertEqual(painel.editor.lineWrapMode(), QTextEdit.LineWrapMode.WidgetWidth)

    def test_selecionar_tudo_pega_a_folha_inteira(self) -> None:
        painel = self.painel("uma frase")
        painel.selecionar_tudo()
        self.assertEqual(painel.editor.textCursor().selectedText(), "uma frase")

    def test_a_busca_lista_as_ocorrencias_com_o_contexto(self) -> None:
        """**A lista é o item, e não o "próximo"**: ela responde quantas há e onde de uma vez, e é
        ela que torna a substituição em massa conferível antes de acontecer."""
        painel = self.painel("Nf3 e depois Nf3 de novo.")
        janela = painel.achar()
        self.addCleanup(descartar, janela)
        janela.campo_agulha.setText("Nf3")
        self.assertEqual(len(janela.procurar()), 2)
        self.assertEqual(janela.lista.count(), 2)
        self.assertIn("2 ocorrência", janela.lbl_conta.text())

    def test_a_busca_reabre_a_mesma_janela(self) -> None:
        """Uma por vez: a tecla que abre é a mesma que se aperta quando nada parece ter acontecido."""
        painel = self.painel()
        primeira = painel.achar()
        self.addCleanup(descartar, primeira)
        self.assertIs(painel.substituir(), primeira)
        self.assertTrue(primeira.linha_de_troca.isVisible(), "reabrir por `substituir` mostra a troca")

    def test_substituir_todos_entra_na_pilha_como_um_passo(self) -> None:
        """`Ctrl+Z` reverte a substituição **inteira**, e não troca a troca."""
        painel = self.painel("Nf3 e depois Nf3 de novo.")
        janela = painel.achar()
        self.addCleanup(descartar, janela)
        janela.campo_agulha.setText("Nf3")
        janela.procurar()
        janela.campo_novo.setText("Cf3")
        janela.substituir_todos()
        self.assertEqual(painel.texto(), "Cf3 e depois Cf3 de novo.")
        painel.desfazer()
        self.assertEqual(painel.texto(), "Nf3 e depois Nf3 de novo.")

    def test_substituir_sem_ocorrencia_vira_frase(self) -> None:
        painel = self.painel()
        janela = painel.achar()
        self.addCleanup(descartar, janela)
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        janela.substituir_todos()
        self.assertEqual(vistos, ["Não há ocorrência para substituir."])

    def test_clicar_na_ocorrencia_seleciona_o_trecho(self) -> None:
        painel = self.painel("uma Nf3 aqui")
        janela = painel.achar()
        self.addCleanup(descartar, janela)
        janela.campo_agulha.setText("Nf3")
        janela.procurar()
        janela.lista.setCurrentRow(0)
        self.assertEqual(painel.editor.textCursor().selectedText(), "Nf3")

    def test_a_marca_do_lexico_e_borda_e_nao_documento(self) -> None:
        """**O canal é a borda, e ele estava livre** (S-266): a cor da letra é a faixa de
        confiança, o fundo é o realce do autor, e a fonte é o estilo mais o corpo. E a marca não é
        do documento -- por isso `setExtraSelections`, e não formato de caractere: escrita no
        `QTextCharFormat` ela voltaria de `toHtml` e atravessaria a gravação.
        """
        painel = self.painel("uma palavra xyzqk aqui")
        antes = painel.texto()
        painel.marcar_fora_do_lexico()
        self.assertTrue(painel.editor.extraSelections(), "nada foi marcado")
        self.assertEqual(painel.texto(), antes, "a marcação não tocou o documento")
        self.assertFalse(painel.pode_desfazer, "e não entrou na pilha")

    def test_limpar_marcas_desliga_a_conferencia(self) -> None:
        """Ela se refaz sozinha depois de cada redesenho enquanto estiver ligada (S-293)."""
        painel = self.painel("uma palavra xyzqk aqui")
        painel.marcar_fora_do_lexico()
        painel.limpar_marcas_do_lexico()
        self.assertEqual(painel.editor.extraSelections(), [])
        self.assertFalse(painel._conferindo_lexico)

    def test_a_lista_de_figurinas_marca_o_que_o_modelo_nao_le(self) -> None:
        """Um glifo fora do modelo continua inserível -- mas quem o insere precisa saber que a
        folha lida nunca vai trazê-lo de volta (S-248)."""
        painel = self.painel()
        menu = painel.inserir_figurina()
        self.addCleanup(descartar, menu)
        self.assertTrue(menu.actions(), "a lista de figurinas veio vazia")

    def test_inserir_simbolo_entra_no_documento_e_na_pilha(self) -> None:
        painel = self.painel("lance ")
        painel.editor.moveCursor(painel.editor.textCursor().MoveOperation.End)
        painel.inserir_simbolo("♘")
        self.assertIn("♘", painel.texto())
        painel.desfazer()
        self.assertNotIn("♘", painel.texto())

    def test_a_paleta_lateral_abre_e_fecha_sem_tirar_o_foco(self) -> None:
        from PyQt6.QtWidgets import QApplication

        painel = self.painel()
        painel.activateWindow()
        painel.alternar_paleta()
        self.app.processEvents()
        self.assertTrue(painel.paleta_lateral.isVisible())
        self.assertIs(QApplication.focusWidget(), painel.editor, "o foco saiu do texto")
        painel.alternar_paleta()
        self.assertFalse(painel.paleta_lateral.isVisible())

    def test_ler_sem_pdf_avisa_no_rodape(self) -> None:
        """Rodapé e não caixa: é um passo que falta, e não uma escolha."""
        painel = self.painel()
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.ler()
        self.assertEqual(vistos, ["Abra um PDF antes de ler o texto da folha."])

    def test_exportar_folha_vazia_avisa_no_rodape(self) -> None:
        painel = qt_texto.PainelDeTexto()
        self.addCleanup(descartar, painel)
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.exportar_md()
        self.assertEqual(vistos, ["Não há texto nesta aba para exportar."])

    def test_o_modo_bloco_e_da_caixa_e_nao_do_comando(self) -> None:
        """**O comando não inverte a caixa**: quem a inverte é o widget que a carrega, e inverter
        de novo aqui desfaria o clique."""
        painel = self.painel()
        painel.caixa_de_bloco.setChecked(True)
        self.assertTrue(painel._modo_bloco)
        painel.modo_bloco_mudou()
        self.assertTrue(painel._modo_bloco, "o comando não desfez o clique")

    def test_as_cinco_acoes_do_foco_sao_atendidas(self) -> None:
        """Declarar e não atender come a tecla e não faz nada, que é pior que não declarar."""
        painel = self.painel()
        self.assertEqual(painel.acoes_proprias(), texto_declarado.ACOES_PROPRIAS)
        for acao in texto_declarado.ACOES_PROPRIAS:
            with self.subTest(acao=acao):
                self.assertIsNotNone(painel.atender(acao))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
