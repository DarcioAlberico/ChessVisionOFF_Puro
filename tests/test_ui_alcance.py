"""O inventário de alcance: nenhuma pele esconde um comando (S-233).

**O risco central da SPEC_APARENCIA, e ele não é técnico:** três peles convidam a resolver rápido
só numa delas. Um comando novo entra na fita porque foi lá que quem o escreveu estava trabalhando,
some da "Foco" e da clássica, e ninguém descobre até alguém que usa a pele errada precisar dele.

A regra 2 -- *pele é apresentação, nunca conjunto menor* -- não vale nada sem uma máquina que a
cobre. Estes testes são essa máquina, e o que eles cobram com mais cuidado é que ela **possa
falhar**: um inventário que passa por construção é uma tautologia com nome de teste.
"""

from __future__ import annotations

import ast
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from chess_diagram_ocr.ui import alcance, comandos, fita, menu, pele

PDF_PANEL = Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr" / "ui" / "pdf_panel.py"


def _acoes_montadas(fonte: str, funcao: str) -> set[str]:
    """Os nomes de comando que aquela função passa a `ui/comandos.py`, lidos por `ast`.

    É a mesma varredura de `test_ui_comandos._rotulos_literais`, do outro lado: lá ela procura o
    rótulo escrito à mão, aqui procura o nome do comando que o código realmente desenha.
    """
    arvore = ast.parse(fonte)
    alvo = next(no for no in ast.walk(arvore) if isinstance(no, ast.FunctionDef) and no.name == funcao)
    perguntas = ("rotulo", "rotulo_de_botao", "rotulo_alternado", "estilo")
    return {
        no.args[0].value
        for no in ast.walk(alvo)
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Attribute)
        and isinstance(no.func.value, ast.Name)
        and no.func.value.id == "comandos"
        and no.func.attr in perguntas
        and no.args
        and isinstance(no.args[0], ast.Constant)
    }


class InventarioTests(unittest.TestCase):
    """As três peles contra o catálogo inteiro. Sem widget nenhum."""

    def test_toda_pele_alcanca_o_catalogo_inteiro(self) -> None:
        """**O item, numa linha.** E a mensagem já vem pronta para quem a quebrar."""
        faltas = alcance.perdidos()
        self.assertEqual({}, faltas, alcance.relato(faltas))

    def test_a_falha_nomeia_a_pele_e_o_comando(self) -> None:
        """Devolver um booleano manda alguém procurar entre quarenta e um comandos.

        **A simulação é o defeito escrito no roadmap, e não uma variação genérica:** *"um comando
        novo entra na fita porque foi lá que quem o escreveu estava trabalhando, e some da 'Foco' e
        da clássica"*. Então o comando entra no catálogo, ganha casa **só** na fita, e o inventário
        tem de acusar as outras duas -- nomeando quais, e qual comando.
        """
        # O nome não pode conter "fita": a última asserção lê a mensagem, e um comando
        # chamado `so_na_fita` faria o `assertNotIn` acusar a própria palavra do nome.
        novo = "comando_recem_chegado"
        catalogo = [registro.acao for registro in comandos.CATALOGO] + [novo]

        def tela_com_ele(cromo: str) -> set[str]:
            achados = alcance.na_tela(cromo)
            return achados | {novo} if cromo == pele.CROMO_FITA else achados

        faltas = alcance.perdidos(catalogo=catalogo, tela=tela_com_ele)
        self.assertEqual([pele.CLASSICA, pele.FOCO], sorted(faltas), "a fita não podia estar entre as perdas")
        self.assertEqual([novo], faltas[pele.CLASSICA])
        self.assertEqual([novo], faltas[pele.FOCO])

        mensagem = alcance.relato(faltas)
        self.assertIn(pele.CLASSICA, mensagem)
        self.assertIn(pele.FOCO, mensagem)
        self.assertIn(novo, mensagem)
        self.assertNotIn(pele.FITA, mensagem)

    def test_comando_novo_sem_casa_falha(self) -> None:
        """Acrescentar linha ao catálogo sem dar casa a ela derruba a suíte, nas três peles.

        É o caso que a S-233 existe para pegar, e ele não é hipotético: a S-219 registrou que o
        `cancelar_exportacao` viveu como botão sem item de menu, e a S-223 é que lhe deu um.
        """
        catalogo = [registro.acao for registro in comandos.CATALOGO] + ["comando_sem_casa"]
        faltas = alcance.perdidos(catalogo=catalogo)
        self.assertEqual({registro.nome for registro in pele.PELES}, set(faltas))
        for nome, faltando in faltas.items():
            with self.subTest(pele=nome):
                self.assertEqual(["comando_sem_casa"], faltando)

    def test_remover_da_fita_um_comando_sem_item_de_menu_falha(self) -> None:
        """O outro sentido do critério de aceite, e a razão de as duas formas serem somadas.

        Tirar da fita um comando que **tem** item de menu não é perda -- ele continua alcançável,
        e é assim que a "Foco" pode esconder 23 controles sem violar a regra 2. O que falha é
        perder a última casa que o comando tinha.
        """
        com_menu = fita.acoes_da_fita()[0]
        self.assertIn(com_menu, alcance.no_menu(), "o caso escolhido não serve: ele não tem menu")

        def sem_ele(cromo: str) -> set[str]:
            return alcance.na_tela(cromo) - {com_menu}

        self.assertEqual({}, alcance.perdidos(tela=sem_ele), "o menu deixou de segurar o comando")
        faltas = alcance.perdidos(tela=sem_ele, barra_de_menus=lambda: alcance.no_menu() - {com_menu})
        self.assertEqual({registro.nome for registro in pele.PELES}, set(faltas))

    def test_a_paleta_nao_conta_para_o_inventario(self) -> None:
        """**A decisão que faz este módulo medir alguma coisa.**

        A paleta percorre `comandos.CATALOGO`: incluí-la faria `alcancaveis == catálogo` ser
        verdade por definição, e o teste passaria para sempre sem olhar para nada. A prova de que
        ela está fora é que o inventário **sabe falhar** -- com o menu vazio e a tela vazia, ele
        acusa as três peles, o que seria impossível se a terceira forma contasse.
        """
        faltas = alcance.perdidos(tela=lambda _cromo: set(), barra_de_menus=set)
        self.assertEqual({registro.nome for registro in pele.PELES}, set(faltas))
        for nome, faltando in faltas.items():
            with self.subTest(pele=nome):
                self.assertEqual(len(comandos.CATALOGO), len(faltando))

    def test_montagem_desconhecida_levanta(self) -> None:
        """Um inventário que erra a pele é pior que nenhum: ele passa em verde."""
        with self.assertRaises(KeyError):
            alcance.na_tela("cromo_que_nao_existe")
        with self.assertRaises(KeyError):
            alcance.alcancaveis("pele_que_nao_existe")

    def test_o_relato_e_vazio_quando_nao_ha_falta(self) -> None:
        self.assertEqual("", alcance.relato({}))


class SemJanelaTests(unittest.TestCase):
    """A propriedade que torna o inventário barato o bastante para rodar sempre."""

    def test_o_inventario_nao_abre_janela(self) -> None:
        """**Varrer widget custaria uma janela por pele, em toda execução da suíte.**

        A afirmação é feita do jeito mais direto que existe: criar `Tk` ou `Toplevel` durante a
        conta passa a levantar. Se alguém trocar a reflexão por uma varredura de árvore de
        widgets, este teste é o que avisa.
        """

        def recusa(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("o inventário abriu uma janela")

        with patch.object(tk, "Tk", recusa), patch.object(tk, "Toplevel", recusa):
            for registro in pele.PELES:
                with self.subTest(pele=registro.nome):
                    self.assertEqual(
                        {comando.acao for comando in comandos.CATALOGO},
                        alcance.alcancaveis(registro.nome),
                    )
            self.assertEqual({}, alcance.perdidos())


class DeclaracaoDasBarrasTests(unittest.TestCase):
    """A guarda da única declaração deste inventário que pode mentir."""

    def test_a_declaracao_das_barras_bate_com_o_que_o_painel_desenha(self) -> None:
        """`comandos.NAS_BARRAS_DO_PDF` é escrita à mão; `_montar_barras` também.

        Enquanto as duas forem escritas à mão elas podem divergir, e a divergência seria
        silenciosa **e favorável**: uma lista maior que a realidade faria o inventário afirmar que
        a clássica alcança um comando que ela não desenha. É a mesma família de defeito que a
        S-219 mediu nos rótulos, e a resposta é a mesma -- comparar as duas.
        """
        desenhadas = _acoes_montadas(PDF_PANEL.read_text(encoding="utf-8"), "_montar_barras")
        self.assertEqual(set(comandos.NAS_BARRAS_DO_PDF), desenhadas)

    def test_toda_acao_declarada_nas_barras_esta_no_catalogo(self) -> None:
        self.assertEqual([], comandos.acoes_fora_do_catalogo(comandos.NAS_BARRAS_DO_PDF))

    def test_a_linha_de_campo_e_a_unica_casa_dos_tres_de_anotacao(self) -> None:
        """**São os três comandos que o menu não tem**, e por isso a única forma 1 que hoje
        decide alguma coisa. A S-77 os pôs junto da página exibida de propósito: um comando de
        menu que age sobre a página sem que ela esteja à vista grava verdade de referência errada.
        """
        fora_do_menu = {registro.acao for registro in comandos.CATALOGO} - set(menu.acoes_declaradas())
        self.assertEqual(set(comandos.NA_LINHA_DE_CAMPO), fora_do_menu)
        for registro in pele.PELES:
            with self.subTest(pele=registro.nome):
                self.assertTrue(set(comandos.NA_LINHA_DE_CAMPO) <= alcance.na_tela(registro.montar_cromo))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
