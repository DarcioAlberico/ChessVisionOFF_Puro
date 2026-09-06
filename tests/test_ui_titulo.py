"""O título da janela: o produto, o livro e a página (S-167).

**O que estava lá:** `"Chess Diagram OCR - Tkinter"`. Nomeia o **toolkit** — a única informação
da frase que não interessa a ninguém que use o programa —, não nomeia o produto e não diz o que
está aberto. Ao voltar de outra janela pelo Alt-Tab, o título é a única coisa que se lê.

A decisão inteira é uma função pura de três valores, e é o que permite afirmar o nome longo, a
página fora de faixa e a janela sem livro sem abrir nenhuma.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.ui import strings
from chess_diagram_ocr.ui.strings import LIMITE_DO_LIVRO_NO_TITULO, PRODUTO, titulo_da_janela

LONGO = "Yusupov A - Boost your Chess 1 - The Fundamentals.pdf"
"""Um nome de verdade do acervo, e ele passa do limite -- é para isto que o corte existe."""


class TituloTests(unittest.TestCase):
    def test_sem_livro_o_titulo_e_o_produto(self) -> None:
        """A resposta honesta para "o que é esta janela" quando não há nada aberto."""
        self.assertEqual(titulo_da_janela(), PRODUTO)
        self.assertEqual(titulo_da_janela("", 3, 402), PRODUTO)
        self.assertEqual(titulo_da_janela("   "), PRODUTO)

    def test_com_livro_e_pagina_diz_os_tres(self) -> None:
        titulo = titulo_da_janela("Karpov.pdf", 11, 402)
        self.assertIn("Karpov.pdf", titulo)
        self.assertIn("p. 12 de 402", titulo)
        self.assertTrue(titulo.endswith(PRODUTO))

    def test_a_pagina_e_dita_em_base_1_como_o_campo_da_tela(self) -> None:
        """O `Spinbox` da página conta de 0; o usuário conta de 1, e o título fala com ele."""
        self.assertIn("p. 1 de 402", titulo_da_janela("livro.pdf", 0, 402))

    def test_o_produto_vem_no_fim_porque_o_corte_e_pela_direita(self) -> None:
        """A barra de tarefas e o Alt-Tab cortam pela direita: o que varia tem de vir antes."""
        titulo = titulo_da_janela("Karpov.pdf", 11, 402)
        self.assertLess(titulo.index("Karpov"), titulo.index(PRODUTO))

    def test_o_toolkit_nao_e_mencionado(self) -> None:
        """"Tkinter" é a única palavra da frase antiga que não dizia nada a ninguém."""
        for titulo in (titulo_da_janela(), titulo_da_janela("livro.pdf", 0, 10)):
            with self.subTest(titulo=titulo):
                self.assertNotIn("Tkinter", titulo)

    def test_pagina_sem_total_ainda_e_dita(self) -> None:
        """Contar as páginas pode falhar; saber em qual se está, não."""
        self.assertIn("p. 4", titulo_da_janela("livro.pdf", 3))
        self.assertNotIn("de", titulo_da_janela("livro.pdf", 3).split("—")[0])

    def test_pagina_fora_da_faixa_e_omitida_em_vez_de_mostrada(self) -> None:
        """Um título que diz "p. 501 de 402" está errado sobre a única coisa que ele veio dizer."""
        for pagina in (500, -1):
            with self.subTest(pagina=pagina):
                self.assertNotIn("p.", titulo_da_janela("livro.pdf", pagina, 402))

    def test_sem_pagina_o_livro_ainda_aparece(self) -> None:
        self.assertEqual(titulo_da_janela("livro.pdf"), f"livro.pdf — {PRODUTO}")


class NomeLongoTests(unittest.TestCase):
    """O corte é no **meio**, e não no fim — e o motivo é o acervo."""

    def test_um_nome_curto_nao_e_tocado(self) -> None:
        self.assertIn("Karpov.pdf", titulo_da_janela("Karpov.pdf", 0, 10))

    def test_um_nome_longo_e_encurtado(self) -> None:
        titulo = titulo_da_janela(LONGO, 0, 402)
        self.assertIn("…", titulo)
        parte_do_livro = titulo.split(" · ")[0]
        self.assertLess(len(parte_do_livro), len(LONGO))
        self.assertLessEqual(len(parte_do_livro), LIMITE_DO_LIVRO_NO_TITULO)

    def test_o_corte_preserva_o_comeco_e_o_fim(self) -> None:
        """Cortar no fim faria "Boost your Chess 1", "…2" e "…3" virarem três títulos iguais.

        O começo diz o autor e o fim diz o volume, e são esses dois que distinguem um livro do
        vizinho na estante.
        """
        titulo = titulo_da_janela(LONGO, 0, 402)
        self.assertIn("Yusupov", titulo)
        self.assertIn("Fundamentals.pdf", titulo)

    def test_dois_volumes_do_mesmo_livro_continuam_distinguiveis(self) -> None:
        """A propriedade que o corte no meio existe para preservar, dita como desigualdade."""
        base = "Yusupov A - Boost your Chess {} - The Fundamentals.pdf"
        primeiro = titulo_da_janela(base.format(1), 0, 402)
        segundo = titulo_da_janela(base.format(2), 0, 402)
        self.assertNotEqual(primeiro, segundo)

    def test_o_encurtado_respeita_o_limite(self) -> None:
        for nome in ("x" * 200, LONGO, "a" * (LIMITE_DO_LIVRO_NO_TITULO + 1)):
            with self.subTest(nome=nome[:20]):
                self.assertLessEqual(len(strings._encurtar(nome)), LIMITE_DO_LIVRO_NO_TITULO)

    def test_um_nome_no_limite_exato_nao_ganha_reticencia(self) -> None:
        """O controle: encurtar o que já cabe é gastar dois caracteres para não dizer nada."""
        nome = "a" * LIMITE_DO_LIVRO_NO_TITULO
        self.assertEqual(strings._encurtar(nome), nome)


class LigacaoComAJanelaTests(unittest.TestCase):
    """A função podia existir e a janela continuar com a frase antiga -- é como ela sobreviveu."""

    def test_a_janela_usa_a_funcao_e_nao_um_literal(self) -> None:
        from pathlib import Path

        fonte = (
            Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr" / "qt" / "janela.py"
        ).read_text(encoding="utf-8")
        self.assertIn("strings.titulo_da_janela(", fonte)
        self.assertNotIn("Chess Diagram OCR - Tkinter", fonte)

    def test_o_titulo_acompanha_a_navegacao(self) -> None:
        """Sem isto ele diria a primeira página do livro para sempre.

        **O corte é o fim do método, e não 1.200 caracteres** (S-506). A janela de tamanho fixo
        media a distância até a chamada em vez da presença dela: quatro linhas de comentário
        acrescentadas no meio do método reprovavam um código que continua certo, e o mesmo número
        deixaria de alcançar a chamada se o método encolhesse. `test_qt_janela` mede o efeito.
        """
        from pathlib import Path

        fonte = (
            Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr" / "qt" / "janela.py"
        ).read_text(encoding="utf-8")
        comeco = fonte.index("def _pagina_apareceu")
        fim = fonte.index(chr(10) + "    def ", comeco + 1)
        self.assertIn("_atualizar_titulo", fonte[comeco:fim])


if __name__ == "__main__":
    unittest.main()
