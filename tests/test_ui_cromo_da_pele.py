"""Cromo escuro, documento claro, marcações remedidas (S-224).

`ui/theme.py:37-50` argumenta contra tema escuro **por escrito**, e o argumento é bom: o produto
é comparar diagrama impresso em papel branco com o que o modelo leu, e pôr a página renderizada
sobre preto faz o olho corrigir contraste em vez de posição. A Imagem 1 não contradiz isso -- a
página dela continua branca. **O que escurece é o cromo.**

A fronteira, então: cromo segue a pele; superfície de documento mantém a paleta medida. E o preço
de registrar uma pele escura é assinar a conta do contraste -- que estes testes cobram, papel a
papel, em cada pele registrada. É o que impede a "Foco" de entrar quebrando o que a S-158
consertou.
"""

from __future__ import annotations

import itertools
import sys
import tkinter as tk
import unittest
from pathlib import Path

from tk_root import raiz

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_ui_tokens import PARES_DE_MARCACAO, PARES_DE_TEXTO  # noqa: E402

from chess_diagram_ocr.ui import pele, theme, tokens  # noqa: E402


def _paletas_por_pele() -> list[tuple[str, dict[str, str]]]:
    """A paleta resolvida de cada pele registrada, sem abrir janela.

    Sem `style`: a reserva é o que se mede, como em `test_ui_tokens`. O eixo que a S-224
    acrescenta é o outro -- `cromo_escuro` --, e ele é da pele e não do tema.
    """
    return [(registro.nome, tokens.paleta(cromo_escuro=registro.cromo_escuro)) for registro in pele.PELES]


def _reprovas_de_texto(paleta: dict[str, str]) -> list[str]:
    """Pares (texto, fundo) abaixo do piso AA. **Os mesmos pares da S-146**, e não uma segunda
    lista: importados de `test_ui_tokens`, que é onde eles foram declarados."""
    return [
        f"{texto} sobre {fundo}: {tokens.razao_de_contraste(paleta[texto], paleta[fundo]):.2f}:1"
        for texto, fundo in PARES_DE_TEXTO
        if tokens.razao_de_contraste(paleta[texto], paleta[fundo]) < tokens.AA_TEXTO
    ]


CASAS = (tokens.CASA_CLARA, tokens.CASA_ESCURA, tokens.CASA_ULTIMO_LANCE)
"""As três casas sobre as quais uma marcação de tabuleiro é desenhada.

**Eram duas, e a terceira faltava.** A S-158 mediu contra a clara e a escura -- metade do
tabuleiro é cada uma --, e ninguém tinha olhado o amarelo do último lance, que é a terceira cor
de casa que existe. Ela aparece exatamente onde o gesto é mais comum: selecionar a casa de destino
do lance que acabou de ser jogado.

A S-257 (noutro ramo) traz `tokens.CASAS_DO_TABULEIRO` com estas três; quando ela entrar, esta
tupla vira a de lá. Os três papéis já existem aqui, e por isso a cobertura não precisava esperar.
"""


def _reprovas_de_marcacao(paleta: dict[str, str]) -> set[str]:
    """Os pares de marcação abaixo do piso gráfico, como `papel sobre fundo`.

    Devolve o **conjunto dos pares**, e não as razões: o que a S-224 cobra é que a pele não
    acrescente nenhum. Comparar números entre peles cobraria outra coisa -- que a pele não mexa
    em marcação nenhuma --, e isso já é o `test_o_cromo_escuro_nao_toca_marcacao_nenhuma`.
    """
    reprovas = {
        f"{marca} sobre {fundo}"
        for marca, fundo in PARES_DE_MARCACAO
        if tokens.razao_de_contraste(paleta[marca], paleta[fundo]) < tokens.AA_GRAFICO
    }
    for papel, (superficie, _) in tokens.SIGNIFICADO.items():
        if superficie != tokens.TABULEIRO:
            continue
        for casa in CASAS:
            if tokens.razao_de_contraste(paleta[papel], paleta[casa]) < tokens.AA_GRAFICO:
                reprovas.add(f"{papel} sobre {casa}")
    return reprovas


REPROVAS_ANTERIORES_A_S224: set[str] = set()
"""Os contornos de casa que somem no fundo em que são desenhados. **Vazio desde a S-295.**

Eram quatro (2026-08-24), medidos contra o piso de 3,0: `ALVO` dava **1,53** na casa escura e
**2,99** no amarelo do último lance; `DIVERGENTE`, 1,86; `PROBLEMA`, 1,73. Mesma família do defeito
que a S-158 mediu e consertou para o `CORRIGIDO` -- *"uma borda desenhada e invisível em metade das
casas"* --, em três papéis que ela não olhou.

**A S-295 os consertou pela via que a S-158 já tinha aberto: luminosidade, com matiz e saturação
intactas.** `ALVO` foi de `#3f7f4c` para `#24482b`, `PROBLEMA` de `#c0392b` para `#77231b`, e
`DIVERGENTE` de `#8e44ad` para `#5b2c6f`. O pior par de cada um passou de 1,53/1,73/1,86 para
3,27/3,27/3,28, e o melhor de ~4 para ~7,5. Nenhuma matiz se moveu, então a regra dos 40° da S-158
sai intacta -- é o que torna a troca barata: ela não disputa faixa de matiz com ninguém.

**O que a S-224 cobra continua valendo, e agora com a lista vazia**: nenhuma pele pode acrescentar
uma reprova. Com o conjunto vazio a igualdade do teste passou a afirmar que **nenhum** par de
marcação reprova em pele nenhuma -- que é mais forte do que ela afirmava, e é o estado certo.

O nome ficou como está, com o número da S que os registrou: renomeá-lo perderia o rastro de quando
o defeito foi medido, e é o rastro que explica por que a lista existia."""


class FronteiraDoDocumentoTests(unittest.TestCase):
    def test_o_documento_nao_escurece_com_a_pele(self) -> None:
        """A folha e o tabuleiro ficam na paleta medida em **qualquer** pele.

        Trocar de *tema* continua movendo as duas, como desde a S-147 -- tema é o eixo de cor, e
        essa escolha é de quem a faz. O que a pele não pode é mudar o fundo contra o qual as doze
        marcações foram medidas.
        """
        for nome, paleta in _paletas_por_pele():
            for papel in tokens.SUPERFICIES_DE_DOCUMENTO:
                with self.subTest(pele=nome, papel=papel):
                    self.assertEqual(tokens.RESERVA[papel], paleta[papel])

    def test_a_identidade_do_tabuleiro_nao_segue_pele_nenhuma(self) -> None:
        """Xadrez impresso é claro-e-escuro em qualquer aparência (S-147)."""
        for nome, paleta in _paletas_por_pele():
            for papel in (tokens.CASA_CLARA, tokens.CASA_ESCURA, tokens.CASA_ULTIMO_LANCE, tokens.ALVO):
                with self.subTest(pele=nome, papel=papel):
                    self.assertEqual(tokens.RESERVA[papel], paleta[papel])

    def test_o_cromo_escuro_nao_toca_marcacao_nenhuma(self) -> None:
        """`NO_CROMO_ESCURO` mexe em cromo, e só. Uma marcação ali seria a paleta medida da
        página mudando de valor por causa de aparência."""
        marcacoes = set(tokens.SIGNIFICADO)
        self.assertEqual(set(), marcacoes & set(tokens.NO_CROMO_ESCURO))


class ContrastePorPeleTests(unittest.TestCase):
    """A conta que registrar uma pele obriga a assinar."""

    def test_todo_texto_atinge_aa_texto_em_toda_pele(self) -> None:
        """Os mesmos sete pares da S-146, agora em cada pele registrada.

        Foi este teste que cobrou o preço do cromo escuro: cinco dos sete reprovavam sobre
        `#1f2124` -- 2,50, 2,97, 2,72, 2,75 e 2,81 --, porque foram escolhidos contra um fundo
        claro. Os cinco ganharam valor de cromo escuro, com matiz preservada.
        """
        for nome, paleta in _paletas_por_pele():
            with self.subTest(pele=nome):
                self.assertEqual([], _reprovas_de_texto(paleta))

    def test_toda_marcacao_atinge_aa_grafico_em_toda_pele(self) -> None:
        """E as três que já reprovavam continuam sendo três: **a pele não acrescenta nenhuma.**

        A igualdade é de propósito, e não uma frouxidão: quando alguém **consertar** os três, este
        teste reprova -- e é o que obriga a lista a ser esvaziada em vez de envelhecer em silêncio
        dizendo que há defeito onde já não há.
        """
        for nome, paleta in _paletas_por_pele():
            with self.subTest(pele=nome):
                self.assertEqual(
                    REPROVAS_ANTERIORES_A_S224,
                    _reprovas_de_marcacao(paleta),
                    "Se um item consertou algum destes, esvazie `REPROVAS_ANTERIORES_A_S224` e diga "
                    "na docstring dela qual foi. Se a lista **cresceu**, foi a pele que quebrou.",
                )

    def test_a_separacao_de_matiz_vale_em_toda_pele(self) -> None:
        """A regra dos 40° da S-158, por pele. Ela sai de graça enquanto nenhuma marcação seguir
        a pele -- e é exatamente por isso que vale a pena afirmá-la: o dia em que alguém puser
        uma marcação em `NO_CROMO_ESCURO`, é aqui que aparece."""
        for nome, paleta in _paletas_por_pele():
            for a, b in itertools.combinations(sorted(tokens.SIGNIFICADO), 2):
                if tokens.SIGNIFICADO[a][0] != tokens.SIGNIFICADO[b][0]:
                    continue
                if min(tokens.saturacao(paleta[a]), tokens.saturacao(paleta[b])) <= tokens.SATURACAO_NEUTRA:
                    continue
                with self.subTest(pele=nome, par=(a, b)):
                    distancia = tokens.distancia_de_matiz(paleta[a], paleta[b])
                    self.assertGreaterEqual(distancia, tokens.SEPARACAO_MINIMA_DE_MATIZ, f"{a} x {b}")

    def test_a_matiz_do_papel_sobrevive_a_troca_de_pele(self) -> None:
        """Clarear para caber no cromo escuro é mexer em **luminosidade**, e não em significado:
        `PROBLEMA_TEXTO` continua sendo o vermelho de "pare" nas duas peles. Um papel que
        trocasse de matiz entre peles seria dois significados com um nome (S-158)."""
        for papel in tokens.NO_CROMO_ESCURO:
            claro, escuro = tokens.RESERVA[papel], tokens.NO_CROMO_ESCURO[papel]
            if min(tokens.saturacao(claro), tokens.saturacao(escuro)) <= tokens.SATURACAO_NEUTRA:
                continue
            with self.subTest(papel=papel):
                self.assertLess(tokens.distancia_de_matiz(claro, escuro), 2.0)

    def test_uma_pele_que_quebra_o_contraste_falha(self) -> None:
        """O critério que fecha o item: o mesmo teste, **sem alteração**, reprova uma pele nova
        que quebre a conta. Aqui a pele hipotética é um cromo escuro que esqueceu o texto."""
        quebrada = dict(tokens.paleta(cromo_escuro=True))
        quebrada[tokens.TEXTO_PADRAO] = tokens.RESERVA[tokens.TEXTO_PADRAO]
        self.assertNotEqual([], _reprovas_de_texto(quebrada))


class TemaDaPeleTests(unittest.TestCase):
    """A pele sugere o tema; a variável de ambiente continua mandando (S-221/S-224)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.addCleanup(theme.apply_theme, self.root)

    def test_a_pele_escura_pede_o_tema_escuro(self) -> None:
        self.assertEqual(theme.DEFAULT_THEME, theme.apply_theme(self.root, cromo_escuro=False))
        self.assertEqual(theme.TEMA_ESCURO, theme.apply_theme(self.root, cromo_escuro=True))

    def test_o_argumento_e_a_variavel_ganham_da_pele(self) -> None:
        """É o que mantém possível a combinação que a S-221 quis preservar: a pele escura com o
        tema claro, se alguém decidir isso."""
        self.assertEqual(
            theme.DEFAULT_THEME,
            theme.apply_theme(self.root, theme.DEFAULT_THEME, cromo_escuro=True),
        )

    def test_trocar_de_pele_volta_do_escuro_para_o_claro(self) -> None:
        """**O achado da S-224, e ele custaria caro se ninguém o tivesse medido.**

        `tb.Style` é um singleton, e o `theme=` do construtor leva do claro ao escuro e **não**
        leva de volta -- o objeto continua o mesmo e o nome não muda. Só a troca de pele expôs
        isso, porque até a S-222 ninguém trocava de tema com a janela aberta. Sem `theme_use`,
        escolher "Foco" e voltar para "Clássica" deixava a janela escura para sempre.
        """
        for esperado, escuro in ((theme.TEMA_ESCURO, True), (theme.DEFAULT_THEME, False)) * 2:
            with self.subTest(cromo_escuro=escuro):
                self.assertEqual(esperado, theme.apply_theme(self.root, cromo_escuro=escuro))

    def test_o_documento_nao_muda_ao_trocar_de_pele_na_janela(self) -> None:
        """O critério, medido com o `Style` de verdade e não só com a reserva."""
        theme.apply_theme(self.root, cromo_escuro=False)
        antes = theme.cor_atual(tokens.SUPERFICIE_PAGINA)
        theme.apply_theme(self.root, cromo_escuro=True)
        self.assertEqual(antes, theme.cor_atual(tokens.SUPERFICIE_PAGINA))
        self.assertNotEqual("#000000", theme.cor_atual(tokens.TEXTO_PADRAO), "o texto ficou preto no escuro")


class RepinturaTests(unittest.TestCase):
    """O que foi pintado fora do `Style` também precisa acompanhar (S-224)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        guardadas = list(theme._repinturas)
        theme._repinturas.clear()
        self.addCleanup(lambda: theme._repinturas.__setitem__(slice(None), guardadas))

    def test_pintar_aplica_agora_e_de_novo_depois(self) -> None:
        rotulo = tk.Label(self.root)
        self.addCleanup(rotulo.destroy)
        theme.pintar(rotulo, "foreground", tokens.TEXTO_PADRAO)
        self.assertEqual(theme.cor_atual(tokens.TEXTO_PADRAO), str(rotulo.cget("foreground")))

        rotulo.configure(foreground="#ff00ff")
        theme.repintar()
        self.assertEqual(theme.cor_atual(tokens.TEXTO_PADRAO), str(rotulo.cget("foreground")))

    def test_a_repintura_de_widget_morto_sai_da_lista(self) -> None:
        """Um widget destruído entre o registro e a troca não é erro: é a janela de antes."""
        efemero = tk.Label(self.root)
        theme.pintar(efemero, "foreground", tokens.TEXTO_PADRAO)
        efemero.destroy()

        theme.repintar()

        self.assertEqual([], theme._repinturas)

    def test_uma_repintura_que_falha_nao_derruba_as_outras(self) -> None:
        """Aparência não derruba ferramenta -- o contrato do módulo, aplicado à repintura."""
        feitas: list[int] = []
        theme.ao_repintar(lambda: (_ for _ in ()).throw(ValueError("cor inventada")))
        theme.ao_repintar(lambda: feitas.append(1))

        with self.assertLogs(theme.logger, level="WARNING"):
            theme.repintar()

        self.assertEqual([1], feitas)
        self.assertEqual(1, len(theme._repinturas), "a que falhou continua na lista")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
