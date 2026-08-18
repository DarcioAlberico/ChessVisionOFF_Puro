"""A legenda de atalhos, gerada da mesma tabela que liga as teclas (S-165).

Dez atalhos ligados e **nenhum** visível na interface: sem menu, sem legenda, sem tooltip. Depois
da S-150 isso deixou de ser conveniência -- num notebook de 1366×768 o botão de salvar não cabe, e
`Ctrl+S` era o único caminho, escrito em lugar nenhum.

O que estes testes travam não é a janela: é a **fonte única**. Uma segunda lista de teclas escrita
à mão diverge da primeira na primeira tecla nova, e aí a legenda passa a mentir -- que é pior que
não existir.
"""

from __future__ import annotations

import ast
import tkinter as tk
import unittest
from pathlib import Path

from tk_root import raiz

from chess_diagram_ocr.ui import atalhos, legenda, menu

RAIZ = Path(__file__).resolve().parents[1]

ARQUIVOS_DE_UI = sorted((RAIZ / "src" / "chess_diagram_ocr" / "ui").glob("*.py")) + [RAIZ / "app_tkinter.py"]


class FonteUnicaTests(unittest.TestCase):
    """Nenhuma sequência do Tk escrita fora de `ui/atalhos.py`.

    É a mesma varredura que a S-145 fez com hexadecimal, e pela mesma razão: enquanto der para
    escrever a tecla no painel, alguém escreve -- e a legenda, o menu e o `bind` param de concordar
    sem nada avisar.
    """

    GESTOS_DE_MOUSE = ("MouseWheel", "Button")
    """O que a varredura **não** cobre, e por quê.

    `<Control-MouseWheel>` (o zoom ancorado no ponteiro, S-70) é gesto de mouse, não tecla: ele não
    cabe como acelerador de menu -- o Tk só sabe desenhar teclas ali -- e uma legenda de teclado que
    o listasse prometeria uma tecla que não existe. Ele está documentado onde é procurado: no
    tooltip de "Ajustar à largura", ao lado do botão que faz a mesma coisa.
    """

    def _sequencias_literais(self, caminho: Path) -> list[str]:
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        return [
            no.value
            for no in ast.walk(arvore)
            if isinstance(no, ast.Constant)
            and isinstance(no.value, str)
            and no.value.startswith("<Control")
            and not any(gesto in no.value for gesto in self.GESTOS_DE_MOUSE)
        ]

    def test_so_a_tabela_escreve_sequencia_de_tecla(self) -> None:
        infratores = [
            f"{caminho.name}: {seq}"
            for caminho in ARQUIVOS_DE_UI
            if caminho.name != "atalhos.py"
            for seq in self._sequencias_literais(caminho)
        ]
        self.assertEqual(infratores, [], "sequência de atalho escrita fora de `ui/atalhos.py`")

    def test_a_legenda_esta_no_menu_ajuda(self) -> None:
        """Uma legenda que existe e não tem porta é uma legenda que ninguém abre."""
        self.assertIn("legenda_de_atalhos", menu.acoes_declaradas())


class JanelaTests(unittest.TestCase):
    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.pai = tk.Toplevel(self.root)
        self.addCleanup(self.pai.destroy)

    def test_a_legenda_mostra_os_dez_com_a_mesma_descricao_da_tabela(self) -> None:
        """O critério de aceite: a legenda mostra os atalhos com a descrição do menu."""
        janela = legenda.abrir(self.pai)
        self.addCleanup(janela.destroy)
        self.root.update()

        self.assertEqual(
            janela.linhas(),
            [(atalho.rotulo, atalho.descricao) for atalho in atalhos.ATALHOS],
        )

    def test_um_atalho_novo_aparece_sem_ninguem_editar_a_legenda(self) -> None:
        """A propriedade que o item existe para garantir, dita como teste.

        A tabela é percorrida na construção, então acrescentar uma linha em `ATALHOS` a faz
        aparecer aqui. É por isso que não há teste comparando duas listas: só existe uma.
        """
        extra = atalhos.Atalho("<Control-t>", "Ctrl+T", "inventado", "Um comando que só este teste tem")
        original = atalhos.ATALHOS
        atalhos.ATALHOS = (*original, extra)
        self.addCleanup(setattr, atalhos, "ATALHOS", original)

        janela = legenda.JanelaDeAtalhos(self.pai)
        self.addCleanup(janela.destroy)
        self.root.update()

        self.assertIn(("Ctrl+T", "Um comando que só este teste tem"), janela.linhas())

    def test_a_guarda_de_foco_esta_dita_onde_alguem_a_procura(self) -> None:
        """"Por que a seta não trocou de diagrama?" só se pergunta olhando a legenda (S-20)."""
        janela = legenda.abrir(self.pai)
        self.addCleanup(janela.destroy)
        self.root.update()
        textos = [
            str(filho.cget("text"))
            for filho in janela.winfo_children()[0].winfo_children()
            if hasattr(filho, "cget") and "text" in filho.keys()
        ]
        self.assertTrue(any("campo de texto" in texto for texto in textos))

    def test_reabrir_traz_a_que_ja_esta_aberta_em_vez_de_empilhar(self) -> None:
        primeira = legenda.abrir(self.pai)
        self.addCleanup(primeira.destroy)
        self.assertIs(legenda.abrir(self.pai), primeira)


if __name__ == "__main__":
    unittest.main()
