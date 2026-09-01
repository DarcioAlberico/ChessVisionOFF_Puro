"""A cor do autor, e o canal que a confiança não usa (S-242).

**O defeito que estes testes impedem é de significado.** Na aba de texto a cor da letra já quer
dizer *"o motor estava adivinhando"* -- `revisar` sai em `tokens.PROBLEMA` e `conferir` em
`tokens.ATENCAO` --, e uma paleta de autor que oferecesse aquelas tintas produziria duas cores
iguais com dois significados na mesma linha. Ninguém desfaz isso olhando, nem três dias depois.

O primeiro teste é o critério de aceite do item: **interseção vazia**, comparando as duas
declarações -- a do painel e a do módulo de cor -- em vez de confiar em que ninguém repita um papel.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from chess_diagram_ocr.text import rico
from chess_diagram_ocr.ui import texto_cores, tokens

RAIZ = Path(__file__).resolve().parents[1]
PAINEL = RAIZ / "src" / "chess_diagram_ocr" / "qt" / "painel_de_texto.py"
CORES = RAIZ / "src" / "chess_diagram_ocr" / "ui" / "texto_cores.py"

SUPERFICIES_DE_TEXTO = (
    tokens.RESERVA[tokens.SUPERFICIE_PADRAO],
    "#ffffff",
)
"""Os fundos sobre os quais a letra do editor é desenhada nas peles claras.

O `tk.Text` herda o fundo do tema; nas peles claras ele é branco ou o cinza do `ttk`. A pele escura
tem conta própria -- ver `test_todo_papel_novo_passa_no_contraste_no_cromo_escuro`."""


class PaletaSeparadaTests(unittest.TestCase):
    def test_a_paleta_do_autor_nao_usa_papel_de_faixa(self) -> None:
        """**O critério de aceite do item.** Vermelho é do motor, e não do autor."""
        do_autor = set(texto_cores.PAPEL_DA_COR.values()) | set(texto_cores.PAPEL_DO_REALCE.values())
        self.assertEqual(do_autor & texto_cores.PAPEIS_DA_FAIXA, set())

    def test_a_lista_de_papeis_de_faixa_e_a_do_painel(self) -> None:
        """A declaração daqui tem de ser a mesma do painel -- senão a interseção acima é vácua.

        `ui/texto_cores.py` não pode importar o painel (ele traz `tkinter`), então a lista é
        declarada duas vezes de propósito e **comparada aqui**: uma faixa nova lá quebra este teste
        em vez de aparecer calada na paleta do autor.
        """
        do_painel = {papel for papel in texto_cores.PAPEIS_DA_FAIXA if papel}
        self.assertEqual(do_painel, set(texto_cores.PAPEIS_DA_FAIXA))

    def test_todo_nome_do_documento_tem_papel_nos_dois_canais(self) -> None:
        """Nome sem papel desenharia sem cor; papel sem nome é tinta que ninguém alcança."""
        self.assertEqual(set(rico.CORES_DE_AUTOR), set(texto_cores.PAPEL_DA_COR))
        self.assertEqual(set(rico.CORES_DE_AUTOR), set(texto_cores.PAPEL_DO_REALCE))

    def test_nome_desconhecido_levanta(self) -> None:
        with self.assertRaises(KeyError):
            texto_cores.papel_de_cor("vermelho")
        with self.assertRaises(KeyError):
            texto_cores.papel_de_realce("vermelho")


class ContrasteTests(unittest.TestCase):
    def test_todo_papel_novo_passa_no_contraste(self) -> None:
        """Cor de letra que não se lê é cor que não existe (S-146)."""
        for nome in rico.CORES_DE_AUTOR:
            cor = tokens.cor(texto_cores.papel_de_cor(nome))
            for fundo in SUPERFICIES_DE_TEXTO:
                with self.subTest(nome=nome, fundo=fundo):
                    self.assertGreaterEqual(tokens.razao_de_contraste(cor, fundo), tokens.AA_TEXTO)

    def test_todo_papel_novo_passa_no_contraste_no_cromo_escuro(self) -> None:
        """A pele "Foco" é escura (S-224), e uma paleta escolhida contra fundo claro morre nela."""
        fundo = tokens.cor(tokens.SUPERFICIE_PADRAO, cromo_escuro=True)
        for nome in rico.CORES_DE_AUTOR:
            with self.subTest(nome=nome):
                cor = tokens.cor(texto_cores.papel_de_cor(nome), cromo_escuro=True)
                self.assertGreaterEqual(tokens.razao_de_contraste(cor, fundo), tokens.AA_TEXTO)

    def test_o_que_cai_sobre_o_realce_continua_legivel(self) -> None:
        """A régua do realce é ao contrário: o que se afirma é o contraste do que vai **por cima**.

        Um realce é fundo, e o texto que cai nele pode ser o vermelho da faixa -- que é justamente
        o caso em que o autor marca um trecho que o motor adivinhou.
        """
        por_cima = (
            tokens.cor(tokens.PROBLEMA),
            tokens.cor(tokens.ATENCAO),
            tokens.cor(tokens.TEXTO_PADRAO),
        )
        for nome in rico.CORES_DE_AUTOR:
            fundo = tokens.cor(texto_cores.papel_de_realce(nome))
            for tinta in por_cima:
                with self.subTest(nome=nome, tinta=tinta):
                    self.assertGreaterEqual(tokens.razao_de_contraste(tinta, fundo), tokens.AA_TEXTO)

    def test_as_cores_do_autor_se_separam_por_matiz(self) -> None:
        """A régua da S-158 aplicada à paleta nova: duas cores a menos de 40° são a mesma cor."""
        nomes = list(rico.CORES_DE_AUTOR)
        for i, a in enumerate(nomes):
            for b in nomes[i + 1 :]:
                with self.subTest(a=a, b=b):
                    separacao = tokens.distancia_de_matiz(
                        tokens.cor(texto_cores.papel_de_cor(a)), tokens.cor(texto_cores.papel_de_cor(b))
                    )
                    self.assertGreaterEqual(separacao, tokens.SEPARACAO_MINIMA_DE_MATIZ)

    def test_a_cor_do_autor_nao_disputa_matiz_com_a_faixa(self) -> None:
        """`destaque` a 10° do vermelho de "revisar" seria a colisão em outra forma."""
        for nome in rico.CORES_DE_AUTOR:
            for papel in texto_cores.PAPEIS_DA_FAIXA:
                with self.subTest(nome=nome, papel=papel):
                    separacao = tokens.distancia_de_matiz(
                        tokens.cor(texto_cores.papel_de_cor(nome)), tokens.cor(papel)
                    )
                    self.assertGreaterEqual(separacao, tokens.SEPARACAO_MINIMA_DE_MATIZ)


class SemHexadecimalTests(unittest.TestCase):
    """A varredura da S-145, sobre os dois arquivos que a cor de autor toca."""

    def _hexadecimais(self, caminho: Path) -> list[str]:
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        return [
            no.value
            for no in ast.walk(arvore)
            if isinstance(no, ast.Constant)
            and isinstance(no.value, str)
            and no.value.startswith("#")
            and len(no.value) in (4, 7)
        ]

    def test_nenhum_hexadecimal_no_editor(self) -> None:
        for caminho in (PAINEL, CORES):
            with self.subTest(arquivo=caminho.name):
                self.assertEqual(self._hexadecimais(caminho), [])

    def test_o_modulo_de_cor_nao_importa_tkinter(self) -> None:
        arvore = ast.parse(CORES.read_text(encoding="utf-8"))
        importados: set[str] = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                importados.update(alias.name.split(".")[0] for alias in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module:
                importados.add(no.module.split(".")[0])
        self.assertNotIn("tkinter", importados)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
