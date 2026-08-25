"""A fila única de ações da pele "Foco", gerada do catálogo (S-223).

A Imagem 1 mostra quatro comandos onde a janela tem 21 nas duas barras do PDF. O diagnóstico dela
está certo -- numa fila de 21 botões de peso igual o olho não encontra a ação do minuto a minuto --
e a contagem, não: desenhá-la ao pé da letra apagaria 23 controles. A regra 2 da SPEC_APARENCIA é
o que impede isso, e o que estes testes cobram é ela: **pele é apresentação do mesmo conjunto de
comandos, nunca um conjunto menor.**
"""

from __future__ import annotations

import tkinter as tk
import unittest
from tkinter import ttk

from tk_root import raiz

from chess_diagram_ocr.ui import atalhos, comandos, fila, icones, menu, pele


class DeclaracaoDaFilaTests(unittest.TestCase):
    """Tudo aqui roda sem abrir janela: a fila é uma consulta ao catálogo."""

    def test_a_fila_sai_do_catalogo(self) -> None:
        """Acrescentar `destaque=True` a uma linha do catálogo põe o comando na fila, e é a
        única coisa que se faz para pô-lo lá."""
        self.assertEqual(
            [registro.acao for registro in comandos.em_destaque()],
            fila.acoes_da_fila(),
        )
        self.assertEqual(["aplicar_fen", "salvar", "proximo_diagrama", "ler_pagina"], fila.acoes_da_fila())

    def test_destaque_exige_atalho(self) -> None:
        """O critério não é o gosto: é a mesma lógica com que `estilos.PRIMARIO` é definido como
        *"a ação que o atalho de teclado também faz"*.

        A spec dizia que os quatro da Imagem 1 já tinham tecla, e **dois não tinham**. A S-223
        resolveu pelos dois lados: `aplicar_fen` ganhou `Ctrl+Enter`, e `exportar_pgn` saiu da
        fila em favor de `salvar` -- exporta-se uma vez por livro e salva-se uma vez por diagrama.
        """
        sem_tecla = [acao for acao in fila.acoes_da_fila() if acao not in atalhos.por_acao]
        self.assertEqual([], sem_tecla, "comando em destaque sem atalho de teclado")

    def test_no_maximo_seis_em_destaque(self) -> None:
        """Acima disso a fila deixa de ser fila e vira a barra que ela veio substituir."""
        self.assertLessEqual(len(comandos.em_destaque()), 6)

    def test_a_fila_vem_agrupada_e_sem_grupo_vazio(self) -> None:
        """**O separador não é um item da lista, e é o que torna a regra estrutural.**

        Devolvendo grupos em vez de uma lista plana com marcas, "separador só entre grupos,
        nunca na ponta" deixa de ser regra a cobrar: quem desenha põe uma barra entre tuplas
        consecutivas, e não sobra onde pôr uma.
        """
        grupos = comandos.fila_de_destaque()
        self.assertTrue(all(grupos), "grupo vazio na fila")
        self.assertEqual(
            [["aplicar_fen", "salvar", "proximo_diagrama"], ["ler_pagina"]],
            [[registro.acao for registro in grupo] for grupo in grupos],
        )

    def test_a_ordem_e_a_do_catalogo_e_nao_a_da_imagem(self) -> None:
        """A Imagem 1 começa por "ler"; aqui a Edição vem antes do OCR, que é a ordem de `GRUPOS`
        -- a mesma da barra de menus. Reordenar a fila seria declarar pela segunda vez em que
        ordem os comandos vivem."""
        vistos = [registro.grupo for grupo in comandos.fila_de_destaque() for registro in grupo]
        self.assertEqual(sorted(set(vistos), key=comandos.GRUPOS.index), list(dict.fromkeys(vistos)))

    def test_nenhum_comando_tem_terceiro_destino(self) -> None:
        """O critério que a regra 2 vira teste: os controles que saem da tela na pele "Foco" têm
        item de menu **ou** estão na linha de conjunto de campo. Não há terceiro lugar."""
        no_menu = set(menu.acoes_declaradas())
        perdidos = [
            registro.acao
            for registro in comandos.CATALOGO
            if registro.acao not in no_menu and registro.acao not in comandos.NA_LINHA_DE_CAMPO
        ]
        self.assertEqual([], perdidos, 'comando que a pele Foco esconde e o menu não alcança')


def _e_separador(widget: tk.Misc) -> bool:
    """`ttk.Frame` **não** herda de `tk.Frame`: o separador é o único `tk.Frame` puro da barra,
    e as molduras de linha da barra fluida são `ttk`."""
    return isinstance(widget, tk.Frame) and not isinstance(widget, ttk.Frame)


def _desenho(barra: tk.Misc) -> list[str]:
    """A fila como uma linha de símbolos: `o` para pílula, `|` para separador."""
    return [
        "|" if _e_separador(filho) else "o"
        for filho in barra.winfo_children()
        if isinstance(filho, ttk.Button) or _e_separador(filho)
    ]


class MontagemDaFilaTests(unittest.TestCase):
    """A fila desenhada: as pílulas, os separadores e a largura."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.janela = tk.Toplevel(self.root)
        self.addCleanup(self.janela.destroy)
        self.chamados: list[str] = []
        self.amarrados = {
            acao: (lambda nome=acao: self.chamados.append(nome)) for acao in fila.acoes_da_fila()
        }

    def _montar(self) -> tk.Widget:
        barra = fila.montar(self.janela, self.amarrados)
        barra.pack(fill=tk.X)
        self.root.update_idletasks()
        return barra

    def test_separador_so_entre_grupos(self) -> None:
        """Nunca na ponta, e um a menos que o número de grupos."""
        barra = self._montar()
        self.assertEqual(["o", "o", "o", "|", "o"], _desenho(barra))

    def test_o_separador_tem_a_altura_das_pilulas(self) -> None:
        """Medida e não escolhida a olho: um traço mais alto que os botões vira risco solto."""
        barra = self._montar()
        pilulas = [filho for filho in barra.winfo_children() if isinstance(filho, ttk.Button)]
        traco = next(filho for filho in barra.winfo_children() if _e_separador(filho))
        self.assertEqual(max(p.winfo_reqheight() for p in pilulas), int(traco.cget("height")))

    def test_a_fila_cabe_em_uma_linha_em_1100(self) -> None:
        """1100 é onde a S-151 mediu o defeito original -- quatro controles sumindo sem aviso."""
        barra = self._montar()
        self.assertEqual(1, barra.linhas_em(1100))

    def test_a_fila_recusa_comando_sem_funcao(self) -> None:
        """Uma pílula grande, com ícone, que não faz nada é pior que a ausência dela."""
        with self.assertRaises(KeyError) as erro:
            fila.montar(self.janela, {"salvar": lambda: None})
        self.assertIn("aplicar_fen", str(erro.exception))

    def test_clicar_na_pilula_chama_o_comando(self) -> None:
        barra = self._montar()
        pilulas = [filho for filho in barra.winfo_children() if isinstance(filho, ttk.Button)]
        pilulas[0].invoke()
        self.assertEqual(["aplicar_fen"], self.chamados)

    def test_cada_pilula_traz_o_icone_do_comando(self) -> None:
        """Os quatro em destaque têm ícone declarado desde a S-220, e é aqui que ele aparece
        pela primeira vez na janela."""
        for acao in fila.acoes_da_fila():
            with self.subTest(acao=acao):
                self.assertIn(comandos.comando(acao).icone, icones.ICONES)
        barra = self._montar()
        pilulas = [filho for filho in barra.winfo_children() if isinstance(filho, ttk.Button)]
        self.assertTrue(all(str(pilula.cget("image")) for pilula in pilulas), "pílula sem ícone")


class PeleFocoTests(unittest.TestCase):
    def test_a_foco_esta_registrada_e_a_classica_continua_primeira(self) -> None:
        """A ordem do menu é a de `PELES`, e a clássica continua sendo o padrão.

        Quando esta S foi escrita eram duas peles; a S-227 registrou a "Fita". O que este teste
        guarda é o que não muda: a clássica é a primeira e é o padrão.
        """
        self.assertIn(pele.FOCO, pele.por_nome)
        self.assertEqual(pele.CLASSICA, pele.PELES[0].nome)
        self.assertEqual(pele.CLASSICA, pele.escolhida("", ambiente={}))

    def test_a_foco_e_escura_desde_a_s224(self) -> None:
        """Quando a S-223 foi escrita este teste dizia o contrário, e estava certo: declarar
        `cromo_escuro` antes de haver paleta escura seria a pele dizendo que é escura enquanto
        desenha claro. A S-224 mediu os nove papéis e assinou a conta."""
        self.assertTrue(pele.registrada(pele.FOCO).cromo_escuro)
        self.assertFalse(pele.registrada(pele.CLASSICA).cromo_escuro)
