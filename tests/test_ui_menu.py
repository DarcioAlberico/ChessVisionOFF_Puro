"""A barra de menus, e a tabela única de atalhos que ela mostra (S-161).

Não havia um `tk.Menu` no projeto: `grep -rn "tk.Menu" src/ app_tkinter.py` devolvia vazio, e a
consequência não era falta de menu -- era que **o que não fosse botão não existia**. Sem "Abrir
recente", sem "Abrir o log", e sem os dez atalhos escritos em lugar nenhum, o que depois da S-150
significa que num notebook de 1366×768 o `Ctrl+S` era o único caminho para salvar e ninguém tinha
como descobri-lo.

A declaração é dado, e é isso que estes testes usam: quase tudo aqui roda sem abrir janela.
"""

from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path

from tk_root import raiz

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app_tkinter  # noqa: E402 - depende do `sys.path` ajustado acima
from chess_diagram_ocr.ui import atalhos, menu  # noqa: E402
from chess_diagram_ocr.ui.state import AppState  # noqa: E402


class TabelaDeAtalhosTests(unittest.TestCase):
    def test_sao_dez_atalhos_e_nao_onze(self) -> None:
        """A avaliação escreveu "onze" e listou dez; `_bind_shortcuts` ligava dez (S-135)."""
        self.assertEqual(len(atalhos.ATALHOS), 10)

    def test_cada_atalho_tem_sequencia_do_tk_rotulo_e_descricao(self) -> None:
        for atalho in atalhos.ATALHOS:
            with self.subTest(acao=atalho.acao):
                self.assertTrue(atalho.sequencia.startswith("<") and atalho.sequencia.endswith(">"))
                self.assertTrue(atalho.rotulo.strip())
                self.assertGreater(len(atalho.descricao), 15, "descrição que não descreve nada")

    def test_nenhuma_sequencia_e_nenhum_rotulo_se_repete(self) -> None:
        """Duas linhas com a mesma tecla: uma delas nunca dispara, e a legenda promete as duas."""
        self.assertEqual(len({a.sequencia for a in atalhos.ATALHOS}), len(atalhos.ATALHOS))
        self.assertEqual(len({a.rotulo for a in atalhos.ATALHOS}), len(atalhos.ATALHOS))

    def test_o_ctrl_shift_s_e_a_maiuscula_e_nao_um_modificador_a_mais(self) -> None:
        """`<Control-Shift-s>` não chega no Windows; o Tk entrega `<Control-S>` (S-20)."""
        self.assertEqual(atalhos.por_acao["salvar_todos"].sequencia, "<Control-S>")

    def test_ligacoes_recusa_atalho_sem_comando(self) -> None:
        """Tecla declarada e não ligada é tecla que a legenda promete e que não faz nada."""
        with self.assertRaises(KeyError) as erro:
            atalhos.ligacoes({"salvar": lambda: None})
        self.assertIn("proximo_diagrama", str(erro.exception))

    def test_ligacoes_devolve_o_mapa_que_bind_shortcuts_consome(self) -> None:
        comandos = {atalho.acao: (lambda: None) for atalho in atalhos.ATALHOS}
        ligadas = atalhos.ligacoes(comandos)
        self.assertEqual(set(ligadas), {atalho.sequencia for atalho in atalhos.ATALHOS})


class DeclaracaoDoMenuTests(unittest.TestCase):
    def test_todo_comando_com_atalho_mostra_o_atalho(self) -> None:
        """O critério de aceite da S-161, e a razão de a legenda ser descobrível.

        Um item de menu que executa o mesmo que uma tecla e não a mostra desperdiça o único lugar
        da interface onde o atalho é encontrado sem ser procurado.
        """
        declaradas = set(menu.acoes_declaradas())
        for atalho in atalhos.ATALHOS:
            with self.subTest(acao=atalho.acao):
                self.assertIn(atalho.acao, declaradas, "atalho que não tem item de menu nenhum")
                self.assertEqual(atalhos.acelerador(atalho.acao), atalho.rotulo)

    def test_comando_sem_atalho_nao_inventa_acelerador(self) -> None:
        self.assertEqual(atalhos.acelerador("sobre"), "")

    def test_nenhum_rotulo_de_item_se_repete_dentro_do_mesmo_menu(self) -> None:
        for declarado in menu.MENUS:
            rotulos = [item.rotulo for item in declarado.itens if item.tipo != menu.SEPARADOR]
            with self.subTest(menu=declarado.titulo):
                self.assertEqual(len(set(rotulos)), len(rotulos))

    def test_nenhuma_acao_aparece_em_dois_itens(self) -> None:
        """Dois caminhos para o mesmo comando é o começo de eles divergirem."""
        acoes = menu.acoes_declaradas()
        self.assertEqual(len(set(acoes)), len(acoes))

    def test_a_janela_amarra_todos_os_comandos_declarados(self) -> None:
        """A ponte entre os dois módulos: a tabela da janela cobre a declaração do menu.

        Sem janela de verdade -- percorre o **código** de `_comandos` procurando cada nome, que é o
        que permite este teste rodar sem Tk, sem checkpoint e sem PDF.
        """
        fonte = (Path(app_tkinter.__file__).read_text(encoding="utf-8")).split("def _comandos", 1)[1]
        fonte = fonte.split("def _build_menu", 1)[0]
        faltando = [acao for acao in menu.comandos_faltando({}) if f'"{acao}"' not in fonte]
        self.assertEqual(faltando, [], "comando de menu que a janela não amarra")


class MontagemTests(unittest.TestCase):
    """A barra montada de verdade: um `tk.Menu` na janela, com os itens que a declaração diz."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.janela = tk.Toplevel(self.root)
        self.addCleanup(self.janela.destroy)
        self.chamados: list[str] = []
        self.comandos = {
            acao: (lambda nome=acao: self.chamados.append(nome)) for acao in menu.comandos_faltando({})
        }

    def test_a_barra_tem_os_cinco_menus_na_ordem_declarada(self) -> None:
        barra = menu.montar(self.janela, self.comandos)
        titulos = [barra.entrycget(i, "label") for i in range(1, barra.index(tk.END) + 1)]
        self.assertEqual(titulos, [declarado.titulo for declarado in menu.MENUS])

    def test_o_item_com_atalho_carrega_o_acelerador_no_widget(self) -> None:
        """Não basta a declaração dizer: é o `tk.Menu` que a pessoa lê."""
        barra = menu.montar(self.janela, self.comandos)
        editar = self.janela.nametowidget(barra.entrycget(2, "menu"))
        aceleradores = {
            str(editar.entrycget(i, "label")): str(editar.entrycget(i, "accelerator"))
            for i in range(editar.index(tk.END) + 1)
            if str(editar.type(i)) == "command"
        }
        self.assertEqual(aceleradores["Salvar a posição"], "Ctrl+S")
        self.assertEqual(aceleradores["Salvar todas as posições da página"], "Ctrl+Shift+S")

    def test_clicar_no_item_chama_o_comando_amarrado(self) -> None:
        barra = menu.montar(self.janela, self.comandos)
        ferramentas = self.janela.nametowidget(barra.entrycget(4, "menu"))
        ferramentas.invoke(0)
        self.assertEqual(self.chamados, ["ler_pagina"])

    def test_montar_recusa_declaracao_com_item_sem_comando(self) -> None:
        """Um item de menu inerte é pior que nenhum: a pessoa conclui que a função está quebrada."""
        with self.assertRaises(KeyError) as erro:
            menu.montar(self.janela, {"sair": lambda: None})
        self.assertIn("abrir_pdf", str(erro.exception))

    def test_os_interruptores_seguem_a_variavel_do_painel(self) -> None:
        marcada = tk.BooleanVar(value=True)
        barra = menu.montar(
            self.janela,
            self.comandos,
            interruptores={"marcar_diagramas": marcada, "roda_vira_pagina": tk.BooleanVar(value=False)},
        )
        ver = self.janela.nametowidget(barra.entrycget(3, "menu"))
        tipos = [str(ver.type(i)) for i in range(ver.index(tk.END) + 1)]
        self.assertEqual(tipos.count("checkbutton"), 2)

    def test_sem_livro_recente_o_submenu_diz_isso_em_vez_de_ficar_vazio(self) -> None:
        barra = menu.montar(self.janela, self.comandos, recentes=list)
        arquivo = self.janela.nametowidget(barra.entrycget(1, "menu"))
        recentes = self.janela.nametowidget(arquivo.entrycget(1, "menu"))
        recentes.event_generate("<<MenuSelect>>")
        menu._preencher_recentes(recentes, list)
        self.assertIn("nenhum livro", str(recentes.entrycget(0, "label")))

    def test_o_submenu_de_recentes_e_refeito_a_cada_abertura(self) -> None:
        """A lista muda a cada PDF aberto; montá-la uma vez mostraria o acervo de quando a janela subiu."""
        livros: list[tuple[str, object]] = []
        barra = menu.montar(self.janela, self.comandos, recentes=lambda: list(livros))
        arquivo = self.janela.nametowidget(barra.entrycget(1, "menu"))
        recentes = self.janela.nametowidget(arquivo.entrycget(1, "menu"))

        livros.append(("Karpov A.pdf", lambda: None))
        menu._preencher_recentes(recentes, lambda: list(livros))

        self.assertEqual(str(recentes.entrycget(0, "label")), "Karpov A.pdf")


class RecentesDoEstadoTests(unittest.TestCase):
    """De onde sai a lista: o `pdf_history` que a S-156 já guardava, sem arquivo novo."""

    TODOS_EXISTEM = staticmethod(lambda _caminho: True)

    def _estado(self, *nomes: str) -> AppState:
        estado = AppState()
        for nome in nomes:
            estado.remember_page(Path(nome), 1)
        return estado

    def test_o_mais_recente_vem_primeiro(self) -> None:
        recentes = self._estado("a.pdf", "b.pdf", "c.pdf").recentes(existe=self.TODOS_EXISTEM)
        self.assertEqual([Path(c).name for c in recentes], ["c.pdf", "b.pdf", "a.pdf"])

    def test_reabrir_um_livro_o_traz_para_o_topo(self) -> None:
        recentes = self._estado("a.pdf", "b.pdf", "a.pdf").recentes(existe=self.TODOS_EXISTEM)
        self.assertEqual(Path(recentes[0]).name, "a.pdf")

    def test_sem_historico_a_lista_e_vazia(self) -> None:
        self.assertEqual(AppState().recentes(), [])

    def test_o_livro_que_nao_existe_mais_nao_entra_no_menu(self) -> None:
        """O achado da janela dirigida: 13 das 29 entradas apontavam para a pasta anterior do
        projeto, que não existe desde que ele foi movido (S-37). Um item de menu que falha ao ser
        clicado é o mesmo defeito que `menu.montar` recusa -- descoberto pelo usuário, um por um."""
        estado = self._estado("vivo.pdf", "morto.pdf")
        recentes = estado.recentes(existe=lambda caminho: caminho.name == "vivo.pdf")
        self.assertEqual([Path(c).name for c in recentes], ["vivo.pdf"])

    def test_a_lista_do_menu_e_curta_mesmo_com_o_historico_cheio(self) -> None:
        """O histórico guarda 50 para responder "em que página eu parei"; o menu responde outra
        pergunta, e 50 linhas de submenu não são uma lista de recentes."""
        estado = self._estado(*[f"livro{i}.pdf" for i in range(30)])
        self.assertEqual(len(estado.recentes(existe=self.TODOS_EXISTEM)), 10)


if __name__ == "__main__":
    unittest.main()
