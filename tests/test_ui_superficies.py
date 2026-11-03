"""As duas superfícies do canvas do tabuleiro, conferidas por paleta (S-449/S-507).

**Este arquivo já existiu e morreu calado.** Ele nasceu com a S-449, que mediu o tabuleiro
flutuando num slab quase-preto -- 62% da largura de uma linha do canvas -- e deu **tamanho** à
esteira: ela passou a ser o tabuleiro mais a margem que as coordenadas reservam, e o que sobra
virou `VAZIO_DE_CANVAS`. Medido na época: *62% -> 4%*.

Um dia depois, o corte do Tk (S-506) apagou os 46 arquivos de teste daquele frontend, e este foi
junto. E `qt/tabuleiro.py` -- que entrou na árvore **no mesmo commit do corte** -- nunca tinha
recebido a correção: ele pintava `fillRect(self.rect(), SUPERFICIE_TABULEIRO)`, que é o defeito
inteiro. Medido em 2026-09-01, antes da S-507: **41,5% da área do widget** num painel de 685x782,
e a fração crescia com a janela.

**A lição não é sobre cor, é sobre guarda.** O item foi implementado, medido e documentado; o que
faltou foi alguém perguntar, no dia do corte, *quem cobra isto agora?*. As varreduras do corte
foram traduzidas para o Qt uma a uma e acharam defeito na hora; esta não foi traduzida porque não
era varredura de sintaxe -- era um teste de pixel sobre um widget que deixou de existir.

**O critério é o reescrito pela S-449, e não o original.** Ele pedia que a borda do tabuleiro
passasse `AA_GRAFICO` contra o vazio, e reprovava nas peles escuras: ali esteira e moldura se
fundem no vazio, e quem separa é o próprio tabuleiro -- o que está certo, porque num cromo escuro
não há slab a desfazer. O que se cobra é que **pelo menos um dos três** passe.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.ui import tokens

PALETAS: tuple[tuple[str, bool], ...] = (
    ("cromo claro", False),
    ("cromo escuro", True),
)
"""As duas paletas que o Qt tem. O eixo é `cromo_escuro`, que é o que `tokens.cor` recebe.

Eram três do lado do Tk -- clara, tema escuro e pele escura -- porque lá o `ttk.Style` era um
terceiro eixo. Aqui não há `Style`: `cor(papel, None, cromo_escuro=...)` responde as duas, e a
pele "foco" é exatamente a segunda.
"""


def cor(papel: str, *, escuro: bool) -> str:
    return tokens.cor(papel, None, cromo_escuro=escuro)


class VazioDeCanvasTests(unittest.TestCase):
    """O vazio não compete com o documento, e o tabuleiro continua se separando dele."""

    def test_o_vazio_e_vizinho_do_fundo_do_painel(self) -> None:
        """**Critério invertido, e de propósito**: aqui não se quer contraste.

        O vazio existe para o espaço em volta do tabuleiro ser continuação da janela em vez de
        moldura preta. A S-449 mediu 1,03:1 na paleta clara.
        """
        for nome, escuro in PALETAS:
            with self.subTest(paleta=nome):
                razao = tokens.razao_de_contraste(
                    cor(tokens.VAZIO_DE_CANVAS, escuro=escuro),
                    cor(tokens.SUPERFICIE_PADRAO, escuro=escuro),
                )
                self.assertLess(
                    razao,
                    tokens.AA_GRAFICO,
                    f"o vazio virou aresta contra o painel na paleta {nome} ({razao:.2f}:1)",
                )

    def test_pelo_menos_um_dos_tres_separa_o_tabuleiro_do_vazio(self) -> None:
        """Esteira, moldura ou casa clara -- **qual dos três é quem troca com a paleta**.

        Na clara são a esteira e a moldura; a casa clara sozinha daria 1,17. Nas escuras as duas
        se fundem no vazio e quem separa é o tabuleiro. Exigir os três reprova um desenho certo.
        """
        for nome, escuro in PALETAS:
            with self.subTest(paleta=nome):
                vazio = cor(tokens.VAZIO_DE_CANVAS, escuro=escuro)
                razoes = {
                    papel: tokens.razao_de_contraste(cor(papel, escuro=escuro), vazio)
                    for papel in (tokens.SUPERFICIE_TABULEIRO, tokens.MOLDURA, tokens.CASA_CLARA)
                }
                self.assertTrue(
                    any(razao >= tokens.AA_GRAFICO for razao in razoes.values()),
                    f"nada separa o tabuleiro do vazio na paleta {nome}: "
                    + ", ".join(f"{papel} {razao:.2f}:1" for papel, razao in razoes.items()),
                )

    def test_a_coordenada_e_legivel_sobre_a_esteira(self) -> None:
        """A esteira é escura desde a S-147 **porque a coordenada é desenhada em cima dela**.

        É a razão de a S-507 não a trocar de cor: o defeito nunca foi o tom, foi ela não ter fim.
        E é a razão de `_desenhar_coordenadas` resolver contra a esteira, e não contra o fundo do
        widget -- que desde a S-507 é o vazio, claro na paleta clara.
        """
        for nome, escuro in PALETAS:
            with self.subTest(paleta=nome):
                esteira = cor(tokens.SUPERFICIE_TABULEIRO, escuro=escuro)
                razao = tokens.razao_de_contraste(tokens.sobre_superficie(esteira), esteira)
                self.assertGreaterEqual(
                    razao,
                    tokens.AA_GRAFICO,
                    f"a letra da coordenada não se lê sobre a esteira na paleta {nome}",
                )

    def test_o_vazio_nao_e_superficie_de_documento(self) -> None:
        """A regra da S-224 vale para página e tabuleiro, e **não** para o nada em volta deles."""
        self.assertIn(tokens.VAZIO_DE_CANVAS, tokens.SUPERFICIES)
        self.assertNotIn(tokens.VAZIO_DE_CANVAS, tokens.SUPERFICIES_DE_DOCUMENTO)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
