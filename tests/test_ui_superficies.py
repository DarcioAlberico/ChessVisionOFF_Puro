"""As quatro superfícies de canvas, e o tema que agora chega até elas (S-147).

**O achado que este arquivo trava.** `ttkbootstrap` traz 30 temas e metade é escura, mas
quatro retângulos da janela eram desenhados fora do `Style` e ficavam imunes a
`CVOFF_TTK_THEME` — o canvas do PDF, os dois tabuleiros e o tooltip. E o pior deles não era a
imunidade: era o **mesmo** `InteractiveBoard` aparecendo claro na aba Resultado e escuro na aba
Análise, porque cada painel passava um `background=` diferente para o construtor.

O teste é de duas naturezas, e a separação é de propósito:

- o que decide (papel → cor, tema claro ou escuro) é **puro** e roda em milissegundos, sem Tk;
- o que liga (o canvas nasce com a cor que o papel manda) precisa de janela, e são três testes.

A classificação dos 30 temas é afirmada um a um contra o `mode` que a própria biblioteca
declara. É o teste que impede o limiar de virar número de gosto: se um tema futuro cair no lado
errado, ele falha aqui e não na tela de alguém.
"""

from __future__ import annotations

import ast
import inspect
import re
import tkinter as tk
import unittest
from pathlib import Path

from tk_root import raiz

from chess_diagram_ocr.ui import gallery_panel, theme, tokens
from chess_diagram_ocr.ui.board_widget import InteractiveBoard
from chess_diagram_ocr.ui.tokens import AA_TEXTO, RESERVA, razao_de_contraste, sobre_superficie


class EstiloFalso:
    """Um `Style` que responde só o fundo do `TFrame` — o que `tema_e_escuro` consulta."""

    def __init__(self, fundo: str) -> None:
        self.fundo = fundo

    def lookup(self, layout: str, option: str) -> str:
        return self.fundo if (layout, option) == ("TFrame", "background") else ""


class SuperficiesTests(unittest.TestCase):
    """A camada pura: quais papéis seguem o tema, e para onde eles vão."""

    def test_toda_superficie_tem_valor_nos_dois_temas(self) -> None:
        """Uma superfície sem par escuro seria a que fica imune — o defeito de volta, menor."""
        self.assertEqual(set(tokens.SUPERFICIES), set(tokens._NO_ESCURO))
        self.assertTrue(set(tokens.SUPERFICIES) <= set(tokens.PAPEIS))

    def test_no_escuro_toda_superficie_escurece(self) -> None:
        """O critério de aceite da S-147, dito por luminância e não por olho.

        "Acompanhar o tema" tem uma forma verificável: a superfície do tema escuro é **mais
        escura** que a do claro, em todas as quatro. Sem isto, `_NO_ESCURO` poderia trazer
        qualquer cor e o item passaria por ter sido escrito.
        """
        for papel in tokens.SUPERFICIES:
            with self.subTest(papel=papel):
                clara = tokens._luminancia(RESERVA[papel])
                escura = tokens._luminancia(tokens._NO_ESCURO[papel])
                self.assertLess(escura, clara, f"{papel}: escuro {escura:.4f} não é menor que claro {clara:.4f}")

    def test_a_moldura_assenta_o_tabuleiro_nos_dois_temas(self) -> None:
        """A moldura é um degrau **abaixo** da esteira, e é isso que a faz ser vista.

        Depois da S-147 as duas são escuras; se a moldura empatasse ou clareasse, o anel de 2 px
        sumiria e o tabuleiro flutuaria no canvas.
        """
        for rotulo, tabela in (("claro", RESERVA), ("escuro", tokens._NO_ESCURO)):
            with self.subTest(tema=rotulo):
                self.assertLess(
                    tokens._luminancia(tabela[tokens.MOLDURA]),
                    tokens._luminancia(tabela[tokens.SUPERFICIE_TABULEIRO]),
                )

    def test_cor_devolve_o_valor_escuro_so_sob_tema_escuro(self) -> None:
        for papel in tokens.SUPERFICIES:
            with self.subTest(papel=papel):
                self.assertEqual(tokens.cor(papel, EstiloFalso("#ffffff")), RESERVA[papel])
                self.assertEqual(tokens.cor(papel, EstiloFalso("#212529")), tokens._NO_ESCURO[papel])
                self.assertEqual(tokens.cor(papel, None), RESERVA[papel])

    def test_o_que_nao_e_superficie_nao_segue_o_tema(self) -> None:
        """A identidade do tabuleiro não muda de cor com a janela, e é decisão escrita.

        Xadrez impresso é claro-e-escuro em qualquer tema; um tabuleiro que acompanhasse o tema
        deixaria de ser reconhecível como tabuleiro. As marcações também ficam de fora: elas são
        desenhadas sobre a **página** renderizada, cujo fundo é o papel do livro.
        """
        escuro = EstiloFalso("#212529")
        for papel in (tokens.CASA_CLARA, tokens.CASA_ESCURA, tokens.PRONTO, tokens.A_FAZER, tokens.TRACEJADO):
            with self.subTest(papel=papel):
                self.assertEqual(tokens.cor(papel, escuro), RESERVA[papel])

    def test_um_style_que_nao_responde_cai_no_tema_claro(self) -> None:
        """Contrato de degradação: sem tema, a janela abre como abria (S-53)."""

        class Mudo:
            def lookup(self, layout: str, option: str) -> str:
                return ""

        class Quebrado:
            def lookup(self, layout: str, option: str) -> str:
                raise RuntimeError("tema exótico")

        for style in (Mudo(), Quebrado(), None):
            with self.subTest(style=type(style).__name__):
                self.assertFalse(tokens.tema_e_escuro(style))
                self.assertEqual(
                    tokens.cor(tokens.SUPERFICIE_PAGINA, style), RESERVA[tokens.SUPERFICIE_PAGINA]
                )

    def test_o_texto_da_dica_e_legivel_nos_dois_temas(self) -> None:
        """O tooltip tinha fundo cravado e letra herdada do tema: sob tema escuro, ilegível.

        É o defeito de menor consequência dos quatro e o de maior ironia — `ui/tooltip.py` existe
        para explicar botão desabilitado (S-32), e era a explicação que não podia ser lida.
        """
        for rotulo, tabela in (("claro", RESERVA), ("escuro", tokens._NO_ESCURO)):
            fundo = tabela[tokens.SUPERFICIE_DICA]
            with self.subTest(tema=rotulo):
                razao = razao_de_contraste(sobre_superficie(fundo), fundo)
                self.assertGreaterEqual(razao, AA_TEXTO, f"dica {rotulo}: {razao:.2f}:1")


class ClassificacaoDosTemasTests(unittest.TestCase):
    """Os 30 temas de fábrica, um a um, contra o `mode` que a biblioteca declara.

    Este é o teste que dá ao `LIMIAR_DE_TEMA_ESCURO` o direito de ser um número: ele não afirma
    o limiar, afirma a **classificação** — e um limiar errado reprova aqui com o nome do tema.
    """

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import ttkbootstrap as tb
        except ImportError:  # pragma: no cover - checkout sem o extra
            raise unittest.SkipTest("ttkbootstrap não instalado: não há 30 temas a classificar") from None
        raiz()
        cls.style = tb.Style()

    def test_todo_tema_cai_no_lado_que_a_biblioteca_declara(self) -> None:
        errados, vistos = [], 0
        for nome in sorted(self.style.theme_names()):
            self.style.theme_use(nome)
            declarado = str(getattr(self.style.theme, "mode", "") or "")
            if declarado not in ("light", "dark"):  # pragma: no cover - tema sem modo declarado
                continue
            vistos += 1
            if tokens.tema_e_escuro(self.style) != (declarado == "dark"):
                fundo = str(self.style.lookup("TFrame", "background") or "")
                errados.append(f"{nome} ({declarado}, {fundo}, L={tokens._luminancia(fundo):.4f})")
        self.assertEqual([], errados, f"temas classificados errado pelo limiar de {tokens.LIMIAR_DE_TEMA_ESCURO}")
        self.assertGreaterEqual(vistos, 20, "a varredura não chegou aos temas: ela passaria vazia")

    def test_a_vala_entre_os_dois_grupos_e_larga(self) -> None:
        """O limiar não é escolha fina: entre os dois grupos não existe tema nenhum.

        Medido, o mais escuro dos claros dá 0,762 e o mais claro dos escuros dá 0,034. Se um dia
        um tema cair dentro da vala, este teste avisa **antes** de o limiar começar a decidir por
        margem de arredondamento.
        """
        claros, escuros = [], []
        for nome in sorted(self.style.theme_names()):
            self.style.theme_use(nome)
            fundo = str(self.style.lookup("TFrame", "background") or "")
            modo = str(getattr(self.style.theme, "mode", "") or "")
            if not fundo.startswith("#") or modo not in ("light", "dark"):  # pragma: no cover
                continue
            (claros if modo == "light" else escuros).append(tokens._luminancia(fundo))
        self.assertTrue(claros and escuros)
        self.assertGreater(min(claros) / max(escuros), 10.0, "os dois grupos se aproximaram")


class CanvasSegueOPapelTests(unittest.TestCase):
    """A ligação: o canvas nasce com a cor que o papel manda, e os dois tabuleiros empatam."""

    def setUp(self) -> None:
        self.host = tk.Frame(raiz())
        self.addCleanup(self.host.destroy)

    def test_o_tabuleiro_nao_aceita_mais_cor_do_chamador(self) -> None:
        """O parâmetro era a causa: dois painéis, dois valores, um widget com duas identidades."""
        self.assertNotIn("background", inspect.signature(InteractiveBoard.__init__).parameters)
        with self.assertRaises(TypeError):
            InteractiveBoard(self.host, background="#ffffff")  # type: ignore[call-arg]

    def test_os_dois_tabuleiros_da_janela_tem_a_mesma_esteira(self) -> None:
        """`mode` decide o que o tabuleiro faz, e nunca decidiu como ele se parece.

        O Resultado monta em `edit` e a Análise em `play`; era daí que saíam as duas telas.
        """
        edicao = InteractiveBoard(self.host, mode="edit", show_palette=False)
        jogo = InteractiveBoard(self.host, mode="play")
        self.assertEqual(str(edicao.canvas.cget("bg")), str(jogo.canvas.cget("bg")))
        self.assertEqual(str(edicao.canvas.cget("bg")), theme.cor_atual(tokens.SUPERFICIE_TABULEIRO))

    def test_a_coordenada_desenhada_e_legivel_sobre_a_esteira_de_verdade(self) -> None:
        """Não a esteira que o token diz — a que o widget de fato tem."""
        tabuleiro = InteractiveBoard(self.host, mode="play")
        fundo = str(tabuleiro.canvas.cget("bg"))
        from chess_diagram_ocr.ui.board_render import BoardRenderer

        escolhida = BoardRenderer._cor_de_coordenada(tabuleiro.canvas)
        self.assertGreaterEqual(razao_de_contraste(escolhida, fundo), AA_TEXTO)

    def test_o_canvas_da_galeria_nasce_com_o_papel_e_segue_a_troca(self) -> None:
        """Era o **único canvas do `ui/` fora do sistema de cor** (S-394): fundo de fábrica do Tk
        e um `#888` cravado no aviso de "sem recorte" -- o único hexadecimal literal do pacote,
        e um retângulo branco no meio da pele escura."""
        fonte = Path(gallery_panel.__file__).read_text(encoding="utf-8")
        self.assertIn("theme.ao_repintar", fonte)
        self.assertIn("tokens.SUPERFICIE_TABULEIRO", fonte)

    def test_nenhum_modulo_de_ui_crava_cor(self) -> None:
        """`ui/tokens.py` é o único que escreve `#rrggbb`, e é a definição dele fazer isso.

        A varredura é por AST e não por `grep`: o `#` de comentário não conta, e o literal dentro
        de uma f-string de log também não seria cor. O que ela pega é o que chega a um `configure`.
        """
        padrao = re.compile(r"^#[0-9a-fA-F]{3,8}$")
        cravados: list[str] = []
        for caminho in sorted((Path(tokens.__file__).parent).glob("*.py")):
            if caminho.name == "tokens.py":
                continue
            arvore = ast.parse(caminho.read_text(encoding="utf-8"))
            cravados += [
                f"{caminho.name}:{no.lineno}: {no.value}"
                for no in ast.walk(arvore)
                if isinstance(no, ast.Constant) and isinstance(no.value, str) and padrao.match(no.value)
            ]
        self.assertEqual(
            cravados,
            [],
            "Cor cravada fora de `ui/tokens.py`. Quem precisa de cor pede o papel a "
            "`theme.cor_atual`, e registra a repintura ao lado:" + chr(10) + chr(10).join(cravados),
        )

    def test_cor_atual_resolve_e_nao_derruba(self) -> None:
        """A ponte entre painel e tokens: tolerante a tema, intolerante a papel errado."""
        for papel in tokens.SUPERFICIES:
            with self.subTest(papel=papel):
                valor = theme.cor_atual(papel)
                self.assertTrue(valor.startswith("#") and len(valor) == 7)
        with self.assertRaises(KeyError):
            theme.cor_atual("SUPERFICIE_BONITA")


if __name__ == "__main__":
    unittest.main()
