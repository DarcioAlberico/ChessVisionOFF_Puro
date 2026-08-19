"""A escala de fontes, e a FEN que precisava de monoespaçada (S-149).

**O achado, e por que ele é dois.** Segoe UI 9 em toda a janela — título de grupo, rótulo, dado
e barra de status com o mesmo tamanho e o mesmo peso — é ausência de hierarquia. Mas a FEN em
fonte proporcional é pior que isso: `1`, `l` e `I` têm larguras diferentes, e comparar duas
leituras da mesma posição passa a exigir contar caractere com o dedo na tela. O primeiro custa
esforço; o segundo custa acerto.

Como no `test_ui_tokens`, o módulo de decisão não importa `tkinter`: a escala inteira é
afirmável em milissegundos. O que precisa de janela é a **ligação** — que o widget de FEN de
fato recebeu a família monoespaçada —, e essa é a metade que faz a outra valer, porque uma
escala perfeita e não usada é exatamente o estado em que a S-144 encontrou o `ttkbootstrap`.
"""

from __future__ import annotations

import re
import tkinter as tk
import unittest
from pathlib import Path

from tk_root import raiz

from chess_diagram_ocr.ui import theme, tipografia
from chess_diagram_ocr.ui.tipografia import (
    AUXILIAR,
    CORPO,
    DADO,
    MINIMO_LEGIVEL,
    PAPEIS_DE_FONTE,
    TITULO,
    escala,
    familia_monoespacada,
    fonte,
)

RAIZ = Path(__file__).resolve().parents[1]
FONTE_CRAVADA = re.compile(r'font=\(\s*"')
"""`font=("Consolas", 10)` e `font=("Segoe UI", 9)` — a família e o número no painel."""


class EscalaTests(unittest.TestCase):
    """A escala pura: derivada do sistema, monotônica, e com piso."""

    def test_e_monotonica_em_tres_bases(self) -> None:
        """9 é o Windows de fábrica, 10 é o de quem aumentou um degrau, 12 é acessibilidade."""
        for base in (9, 10, 12):
            with self.subTest(base=base):
                tamanhos = escala(base)
                self.assertLess(tamanhos[AUXILIAR], tamanhos[CORPO])
                self.assertLess(tamanhos[CORPO], tamanhos[TITULO])

    def test_deriva_da_base_e_nao_de_numeros_fixos(self) -> None:
        """O critério de aceite: mudar a `TkDefaultFont` do sistema move a escala inteira.

        Uma escala cravada passaria nos testes de monotonia e continuaria ignorando quem
        aumentou a fonte do Windows — que é o mesmo defeito de DPI da S-148, num lugar menor.
        """
        de_nove, de_doze = escala(9), escala(12)
        for papel in PAPEIS_DE_FONTE:
            with self.subTest(papel=papel):
                self.assertEqual(de_doze[papel] - de_nove[papel], 3, f"{papel} não acompanhou a base")

    def test_o_dado_tem_o_tamanho_do_corpo(self) -> None:
        """`DADO` é outra **família**, não outro nível: aumentá-lo faria a FEN gritar."""
        self.assertEqual(escala(9)[DADO], escala(9)[CORPO])

    def test_nenhum_papel_desce_do_piso_legivel(self) -> None:
        """Abaixo de 7 pt as hastes de `l`, `i` e `1` colapsam — o caractere que não pode."""
        for base in (0, -3, 1, MINIMO_LEGIVEL):
            with self.subTest(base=base):
                self.assertTrue(all(tamanho >= MINIMO_LEGIVEL for tamanho in escala(base).values()))

    def test_a_resolucao_e_total(self) -> None:
        self.assertEqual(set(PAPEIS_DE_FONTE), set(escala(9)))
        self.assertEqual(set(PAPEIS_DE_FONTE), set(tipografia.DEGRAUS))


class FonteTests(unittest.TestCase):
    """Papel → `(família, tamanho[, peso])`, que é o que o Tk aceita em `font=`."""

    def _fonte(self, papel: str, **extra: object):
        return fonte(papel, base=9, familia="Segoe UI", mono="Consolas", **extra)  # type: ignore[arg-type]

    def test_so_o_dado_e_monoespacado(self) -> None:
        self.assertEqual(self._fonte(DADO)[0], "Consolas")
        for papel in (TITULO, CORPO, AUXILIAR):
            with self.subTest(papel=papel):
                self.assertEqual(self._fonte(papel)[0], "Segoe UI")

    def test_o_titulo_vem_em_negrito_sem_pedir(self) -> None:
        """Os dois canais juntos: 1 pt sozinho não se vê, e negrito sozinho compete com o corpo."""
        self.assertEqual(self._fonte(TITULO)[2], "bold")
        self.assertEqual(len(self._fonte(CORPO)), 2)

    def test_o_negrito_e_do_chamador_e_nao_do_papel(self) -> None:
        """A linha escolhida numa lista precisa de peso sem mudar de nível hierárquico."""
        escolhida = self._fonte(CORPO, negrito=True)
        self.assertEqual(escolhida[2], "bold")
        self.assertEqual(escolhida[1], self._fonte(CORPO)[1], "o negrito não pode mudar o tamanho")

    def test_papel_desconhecido_levanta_em_vez_de_cair_no_corpo(self) -> None:
        """A mesma disciplina de `tokens.cor`: um papel errado que virasse corpo some da vista."""
        with self.assertRaises(KeyError):
            self._fonte("GRANDAO")


class FamiliaMonoespacadaTests(unittest.TestCase):
    """Qual monoespaçada, e por que não a que o Tk indica de primeira."""

    def test_prefere_consolas_quando_o_sistema_a_tem(self) -> None:
        """No Windows a `TkFixedFont` resolve para Courier New — hastes finas, `1` e `l` de novo.

        É a fonte onde o defeito que a monoespaçada veio corrigir volta pela porta dos fundos.
        """
        self.assertEqual(familia_monoespacada(["Arial", "Consolas", "Courier New"], "Courier New"), "Consolas")

    def test_cai_na_reserva_do_tk_quando_nenhuma_preferida_existe(self) -> None:
        """Aí ela entra por ser o que o sistema tem, e não por ter sido escolhida."""
        self.assertEqual(familia_monoespacada(["Arial", "Courier New"], "Courier New"), "Courier New")

    def test_a_comparacao_ignora_caixa_e_espaco(self) -> None:
        self.assertEqual(familia_monoespacada([" consolas "], "Courier New"), "Consolas")

    def test_a_ordem_da_lista_e_a_preferencia(self) -> None:
        disponiveis = ["Menlo", "DejaVu Sans Mono", "Consolas"]
        self.assertEqual(familia_monoespacada(disponiveis, "Courier New"), "Consolas")
        self.assertEqual(familia_monoespacada(["Menlo", "DejaVu Sans Mono"], "x"), "DejaVu Sans Mono")


class SemFonteCravadaTests(unittest.TestCase):
    """A varredura que impede a regressão, e é a irmã da que a S-145 fez com as cores.

    Sem ela a próxima fonte entra cravada exatamente como `Consolas 10` entrou -- uma de cada
    vez, cada uma justificável sozinha, e no fim ninguém sabe onde mora a escala.
    """

    LIVRES = {"board_render.py", "tipografia.py", "theme.py"}
    """`board_render` desenha no canvas e não em widget: a fonte da coordenada e a do símbolo
    Unicode saem do tamanho da casa, não da escala da janela. Os outros dois **são** a escala."""

    def test_nenhum_painel_crava_familia_e_tamanho(self) -> None:
        infratores = []
        arquivos = [*sorted((RAIZ / "src" / "chess_diagram_ocr" / "ui").glob("*.py")), RAIZ / "app_tkinter.py"]
        for arquivo in arquivos:
            if arquivo.name in self.LIVRES:
                continue
            for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
                if FONTE_CRAVADA.search(linha):
                    infratores.append(f"{arquivo.name}:{numero}: {linha.strip()[:70]}")
        self.assertEqual([], infratores, "fonte cravada fora da escala. Peça um papel de `ui/tipografia.py`.")

    def test_a_varredura_enxerga_o_que_deveria(self) -> None:
        """O controle: se o padrão deixasse de casar, o teste acima passaria vazio."""
        texto = (RAIZ / "src" / "chess_diagram_ocr" / "ui" / "board_render.py").read_text(encoding="utf-8")
        self.assertTrue(FONTE_CRAVADA.search(texto))


class EscalaNaJanelaTests(unittest.TestCase):
    """A ligação. Uma escala perfeita e não usada é o estado em que a S-144 achou o tema."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()
        theme.registrar_estilos()

    def test_a_fonte_base_vem_do_sistema(self) -> None:
        tamanho, proporcional, monoespacada = theme.fonte_base()
        self.assertGreaterEqual(tamanho, MINIMO_LEGIVEL)
        self.assertTrue(proporcional and monoespacada)
        self.assertNotEqual(proporcional, monoespacada, "a proporcional e a monoespaçada empataram")

    def test_o_dado_resolvido_e_de_largura_fixa_de_verdade(self) -> None:
        """A propriedade que importa não é o nome da família: é `1` e `l` medirem o mesmo.

        Medido com o Tk, e é a única forma de saber. Uma lista de nomes preferidos pode
        envelhecer; a medição não.
        """
        from tkinter import font as tkfont

        familia, tamanho = theme.fonte_atual(DADO)[:2]
        medidor = tkfont.Font(root=self.root, family=familia, size=tamanho)
        larguras = {medidor.measure(caractere) for caractere in "1lI8/wW"}
        self.assertEqual(len(larguras), 1, f"{familia} não é de largura fixa: {larguras}")

    def test_o_corpo_resolvido_nao_e_de_largura_fixa(self) -> None:
        """O controle do teste acima: se a medição empatasse em qualquer fonte, ela não mede."""
        from tkinter import font as tkfont

        familia, tamanho = theme.fonte_atual(CORPO)[:2]
        medidor = tkfont.Font(root=self.root, family=familia, size=tamanho)
        self.assertNotEqual(medidor.measure("1"), medidor.measure("w"))

    def test_o_titulo_de_grupo_se_distingue_do_corpo(self) -> None:
        """Sem depender de borda: é o critério de aceite, e ele vale para todo `LabelFrame`.

        O estilo é o **padrão** e não um nomeado, de propósito: um nomeado exigiria `style=` nos
        vinte e poucos grupos da janela, e o primeiro esquecido voltaria ao corpo em silêncio.
        """
        from tkinter import ttk

        registrado = str(ttk.Style().lookup(theme.ESTILO_DE_TITULO, "font"))
        self.assertIn("bold", registrado)
        self.assertEqual(theme.ESTILO_DE_TITULO, "TLabelframe.Label")

    def test_a_tabela_de_dados_tem_corpo_monoespacado_e_a_padrao_nao(self) -> None:
        """`ttk` não tem fonte por coluna: quem pede monoespaçada pede para a tabela.

        A fila de Revisão fica **fora** disso de propósito -- a coluna larga dela é prosa.
        """
        from tkinter import ttk

        style = ttk.Style()
        familia_dado = theme.fonte_atual(DADO)[0]
        self.assertIn(str(familia_dado), str(style.lookup(theme.ESTILO_DE_TABELA_DE_DADOS, "font")))
        self.assertNotIn(str(familia_dado), str(style.lookup("Treeview", "font")))

    def test_o_campo_de_fen_do_resultado_nasce_monoespacado(self) -> None:
        """O widget de verdade, e não o papel: é a FEN que o produto existe para mostrar."""
        quadro = tk.Frame(self.root)
        self.addCleanup(quadro.destroy)
        from tkinter import ttk

        campo = ttk.Entry(quadro, font=theme.fonte_atual(DADO))
        self.assertEqual(str(campo.cget("font")).split()[0].strip("{}"), str(theme.fonte_atual(DADO)[0]).split()[0])


if __name__ == "__main__":
    unittest.main()
