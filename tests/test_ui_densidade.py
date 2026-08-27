"""A densidade como eixo da janela: compacta ou confortável (S-232).

**A S-151 mediu o defeito em 1100×760, e a solução dela não o resolve inteiro.** Quebrar em vez de
cortar acabou com o descarte de controle, e não com o aperto: em 1366×768 -- a tela de notebook mais
comum -- as barras quebram e a página fica com o que sobrar. A fita da S-228 piora isso por
construção, porque uma linha de fita custa ~99 px onde uma linha de barra custa ~28.

O que estes testes travam:

- a escala é **pura e derivada da fonte do sistema**, e não uma segunda tabela de números;
- a densidade confortável é a janela de hoje **por construção**, e não por coincidência;
- a pele **sugere** e a pessoa **decide**, e a decisão sobrevive à troca de pele -- que é a parte
  do item que uma implementação apressada troca por "a fita é compacta e pronto".
"""

from __future__ import annotations

import tkinter as tk
import unittest

from tk_root import raiz

from chess_diagram_ocr.ui import comandos, fita, geometria, menu, pele, theme, tipografia
from chess_diagram_ocr.ui.state import STATE_VERSION, AppState, state_from_dict


class EscalaTests(unittest.TestCase):
    """A escala de espaço. Pura, como a de fonte da S-149, e afirmável em 7, 9 e 12 sem janela."""

    def test_a_densidade_deriva_da_fonte_do_sistema(self) -> None:
        """**Quem aumenta a fonte do Windows quer o programa maior, e não mais apertado.**

        Uma janela de fonte 12 com o vão de fonte 9 fica *mais* densa, não igual -- é o mesmo
        argumento com que a S-149 derivou os tamanhos da `TkDefaultFont`, aplicado ao espaço.
        Os dois valores da tabela do item sobem juntos: o espaçamento e a altura de linha.
        """
        for densidade in pele.DENSIDADES:
            with self.subTest(densidade=densidade):
                pequena = tipografia.folgas(base=9, densidade=densidade)
                grande = tipografia.folgas(base=12, densidade=densidade)
                for papel in tipografia.PAPEIS_DE_FOLGA:
                    self.assertGreater(grande[papel], pequena[papel], f"{papel} não acompanhou a fonte")
                self.assertGreater(
                    tipografia.altura_de_linha(20, densidade=densidade),
                    tipografia.altura_de_linha(15, densidade=densidade),
                )

    def test_a_compacta_e_menor_que_a_confortavel_nos_dois_valores(self) -> None:
        confortavel = tipografia.folgas(densidade=pele.CONFORTAVEL)
        compacta = tipografia.folgas(densidade=pele.COMPACTA)
        for papel in tipografia.PAPEIS_DE_FOLGA:
            with self.subTest(papel=papel):
                self.assertLess(compacta[papel], confortavel[papel])
        self.assertLess(
            tipografia.altura_de_linha(15, densidade=pele.COMPACTA),
            tipografia.altura_de_linha(15, densidade=pele.CONFORTAVEL),
        )

    def test_a_classica_confortavel_e_identica_a_hoje(self) -> None:
        """**O critério de aceite mais fácil de perder de vista, e o mais barato de travar.**

        A densidade confortável não *parece* a janela de hoje: ela **é**, porque `FOLGAS` são os
        números que já estavam escritos nos `padx`/`pady` -- 14 na moldura da legenda, 10 e 6 na
        faixa de cromo, 2 entre dois botões de fita. E 20 é a altura de linha de fábrica do
        `Treeview`. É o mesmo movimento da S-324 com os rótulos: virar dado sem virar outro texto.
        """
        self.assertEqual(
            {
                tipografia.FOLGA_DE_MOLDURA: 14,
                tipografia.FOLGA: 10,
                tipografia.FOLGA_DE_LINHA: 6,
                tipografia.FOLGA_MINIMA: 2,
            },
            tipografia.folgas(base=tipografia.BASE_DE_REFERENCIA, densidade=pele.CONFORTAVEL),
        )
        self.assertEqual(
            tipografia.ALTURA_DE_LINHA_NA_BASE,
            tipografia.altura_de_linha(tipografia.LINHA_NA_BASE, densidade=pele.CONFORTAVEL),
        )
        self.assertEqual(pele.CONFORTAVEL, pele.registrada(pele.CLASSICA).densidade)

    def test_a_folga_nunca_chega_a_zero(self) -> None:
        """Dois vizinhos colados viram um controle só para o olho, e compacta é para caber."""
        for base in (1, 4, 7, 9):
            for densidade in pele.DENSIDADES:
                with self.subTest(base=base, densidade=densidade):
                    for papel in tipografia.PAPEIS_DE_FOLGA:
                        self.assertGreaterEqual(tipografia.folga(papel, base=base, densidade=densidade), 1)

    def test_a_altura_de_linha_nunca_corta_a_letra(self) -> None:
        """**E o piso já morde na fonte 12, não é teórico.**

        Com `linespace` 20 a compacta calcula 20 e o piso responde 21. Da fonte 12 para cima a
        densidade compacta deixa de encolher a tabela, porque não há o que encolher sem cortar a
        perna do `g` -- e numa coluna de FEN e de nome de livro isso é o dado.
        """
        for linha in (11, 15, 20, 30):
            for densidade in pele.DENSIDADES:
                with self.subTest(linespace=linha, densidade=densidade):
                    self.assertGreater(tipografia.altura_de_linha(linha, densidade=densidade), linha)
        self.assertEqual(21, tipografia.altura_de_linha(20, densidade=pele.COMPACTA))

    def test_papel_e_densidade_desconhecidos_levantam(self) -> None:
        """A disciplina de `tokens.cor`: um papel escrito errado devolveria um vão plausível."""
        with self.assertRaises(KeyError):
            tipografia.folga("FOLGA_GIGANTE")
        with self.assertRaises(KeyError):
            tipografia.folga(tipografia.FOLGA, densidade="folgada")
        with self.assertRaises(KeyError):
            tipografia.altura_de_linha(15, densidade="folgada")


class SugestaoEEscolhaTests(unittest.TestCase):
    """A pele sugere, a pessoa decide. É a forma do item, e o que separa isto de "a fita é compacta"."""

    def test_a_fita_sugere_compacta_e_as_outras_confortavel(self) -> None:
        """A fita é a pele que gasta altura com cromo: 99 px de linha contra os ~28 de uma barra."""
        self.assertEqual(pele.COMPACTA, pele.registrada(pele.FITA).densidade)
        self.assertEqual(pele.CONFORTAVEL, pele.registrada(pele.CLASSICA).densidade)
        self.assertEqual(pele.CONFORTAVEL, pele.registrada(pele.FOCO).densidade)

    def test_sem_escolha_cada_pele_traz_a_sugestao_dela(self) -> None:
        for registro in pele.PELES:
            with self.subTest(pele=registro.nome):
                self.assertEqual(registro.densidade, pele.densidade_em_vigor(registro, "", ambiente={}))

    def test_a_escolha_explicita_sobrepoe_a_pele(self) -> None:
        """**E sobrevive à troca de pele**, que é a metade do critério fácil de perder.

        O que está guardado é a decisão da pessoa, não o efeito dela: quem escolheu confortável
        continua confortável **também na fita**, que sugere o contrário.
        """
        for registro in pele.PELES:
            for escolhida in pele.DENSIDADES:
                with self.subTest(pele=registro.nome, escolhida=escolhida):
                    self.assertEqual(escolhida, pele.densidade_em_vigor(registro, escolhida, ambiente={}))

    def test_o_ambiente_ganha_da_guardada(self) -> None:
        """Mesma ordem de `pele.escolhida`: abrir o programa numa aparência a partir de um roteiro."""
        ambiente = {pele.DENSIDADE_ENV: pele.COMPACTA}
        vigor = pele.densidade_em_vigor(pele.registrada(pele.CLASSICA), pele.CONFORTAVEL, ambiente=ambiente)
        self.assertEqual(pele.COMPACTA, vigor)

    def test_densidade_invalida_cai_na_confortavel_e_diz_qual_era(self) -> None:
        """**"Inválida" e "não escolhida" são estados diferentes**, e caem em lugares diferentes.

        Não escolhida cai na sugestão da pele. Inválida cai em confortável, que é o que a tabela
        de degradação da S-234 declara -- quem escreveu um nome errado não pediu nada apertado.
        """
        fita_pele = pele.registrada(pele.FITA)
        with self.assertLogs("chess_diagram_ocr.ui.pele", level="WARNING") as registro:
            vigor = pele.densidade_em_vigor(fita_pele, "folgada", ambiente={})
        self.assertEqual(pele.CONFORTAVEL, vigor)
        self.assertIn("folgada", "\n".join(registro.output))
        self.assertEqual(pele.COMPACTA, pele.densidade_em_vigor(fita_pele, "", ambiente={}))

    def test_todo_rotulo_de_densidade_e_legivel(self) -> None:
        for nome in pele.DENSIDADES:
            with self.subTest(densidade=nome):
                self.assertTrue(pele.rotulo_de_densidade(nome).strip())
        with self.assertRaises(KeyError):
            pele.rotulo_de_densidade("folgada")

    def test_a_densidade_vai_e_volta_do_disco(self) -> None:
        estado = AppState()
        estado.densidade = pele.COMPACTA
        self.assertEqual(pele.COMPACTA, state_from_dict(estado.to_dict()).densidade)
        self.assertEqual(STATE_VERSION, estado.to_dict()["version"])

    def test_estado_de_versao_anterior_abre_sem_densidade_escolhida(self) -> None:
        """Vazio é "não decidi", e cada pele volta a trazer a sugestão dela."""
        antigo = state_from_dict({"version": 4, "skin": pele.FITA})
        self.assertEqual("", antigo.densidade)
        self.assertEqual(
            pele.COMPACTA, pele.densidade_em_vigor(pele.registrada(pele.FITA), antigo.densidade, ambiente={})
        )


class FitaEDocumentoTests(unittest.TestCase):
    """O que a densidade compra em pixel, na tela em que a S-151 mediu o defeito."""

    def test_a_densidade_compacta_crava_o_modo_compacto_da_fita(self) -> None:
        """A tabela do item diz "ícone da fita: 20 px na compacta", e o modo compacto **é** o de
        20 px -- não há um terceiro tamanho a inventar. A largura deixa de ter voto: um monitor
        largo devolveria o ícone de 32 a quem acabou de pedir o de 20."""
        self.assertEqual(20, fita.LADO_DO_ICONE[fita.COMPACTO])
        self.assertEqual(32, fita.LADO_DO_ICONE[fita.PLENO])

    def test_em_1366_compacta_o_pdf_fica_com_60_por_cento(self) -> None:
        """**A metade "a fita cabe em uma linha" foi medida e é falsa, e a S-228 já dizia por quê.**

        O critério de aceite deste item pede duas coisas de 1366×768. A primeira -- a fita numa
        linha -- não acontece em densidade nenhuma: a S-228 mediu que o modo compacto pede **1.726
        px** de largura (mais que os 1.375 do pleno, porque o rótulo sai de baixo do ícone e vai
        para o lado dele), então em 1366 a fita quebra em duas linhas nos dois modos. Não é uma
        falha desta implementação: é uma premissa que já estava refutada quando o item foi escrito.

        A segunda acontece, e é a que importa. Medido com a fonte de referência:

            fita               altura     documento em 768
            plena, 2 linhas    198 px     61,7%
            compacta, 2 linhas  88 px     76,0%

        Os 60% são atendidos nos dois -- e o confortável passa por **1,7 ponto**, ou seja, a uma
        linha de cromo de reprovar. O que a compacta devolve ao documento são **110 px**, que é o
        item fazendo o que foi escrito para fazer.
        """
        plena = 2 * fita.altura_atual(fita.PLENO, densidade=pele.CONFORTAVEL)
        compacta = 2 * fita.altura_atual(fita.COMPACTO, densidade=pele.COMPACTA)
        com_fita = geometria.fracao_do_documento(768, altura_do_cromo=plena)
        com_compacta = geometria.fracao_do_documento(768, altura_do_cromo=compacta)

        self.assertGreaterEqual(com_compacta, 0.60, "a compacta não devolveu 60% ao documento")
        self.assertGreaterEqual(com_fita, 0.60)
        self.assertGreater(com_compacta - com_fita, 0.13, "a compacta deixou de comprar altura")
        self.assertGreaterEqual(plena - compacta, 100, "o ganho em pixel encolheu")

    def test_a_fracao_nunca_e_negativa_nem_estoura(self) -> None:
        self.assertEqual(0.0, geometria.fracao_do_documento(0, altura_do_cromo=50))
        self.assertEqual(0.0, geometria.fracao_do_documento(100, altura_do_cromo=5000))
        self.assertLess(geometria.fracao_do_documento(768, altura_do_cromo=0), 1.0)

    def test_a_fita_continua_dentro_do_orcamento_nas_duas_densidades(self) -> None:
        for modo in fita.MODOS:
            for densidade in pele.DENSIDADES:
                with self.subTest(modo=modo, densidade=densidade):
                    self.assertLessEqual(fita.altura_atual(modo, densidade=densidade), fita.ORCAMENTO[modo])


class NaJanelaTests(unittest.TestCase):
    """O que só se confere com um `Style` de verdade."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def test_a_altura_de_linha_entra_no_estilo_do_treeview(self) -> None:
        """**No `"Treeview"` e não num estilo nomeado.** Um estilo próprio exigiria `style=` nas
        duas tabelas do programa, e a primeira que alguém esquecesse ficaria na altura de fábrica
        -- que é o defeito que a S-153 mediu quando as duas tabelas erravam a mesma coisa."""
        theme.apply_theme(self.root, densidade=pele.COMPACTA)
        self.addCleanup(lambda: theme.apply_theme(self.root, densidade=pele.CONFORTAVEL))
        estilo = theme.estilo_atual()
        if estilo is None:  # pragma: no cover - sem ttk não há estilo a conferir
            self.skipTest("sem Style disponível")
        compacta = int(estilo.lookup("Treeview", "rowheight"))
        theme.apply_theme(self.root, densidade=pele.CONFORTAVEL)
        confortavel = int(estilo.lookup("Treeview", "rowheight"))
        self.assertLess(compacta, confortavel)
        self.assertEqual(theme.altura_de_linha_atual(pele.CONFORTAVEL), confortavel)

    def test_o_menu_ver_tem_o_submenu_de_densidade(self) -> None:
        """A porta da escolha. Sem ela a densidade seria decidida pela pele e por mais ninguém."""
        self.assertIn("densidade", menu.acoes_declaradas())
        self.assertEqual(comandos.VISUALIZACAO, comandos.comando("densidade").grupo)

    def test_o_submenu_lista_as_densidades_registradas(self) -> None:
        janela = tk.Toplevel(self.root)
        self.addCleanup(janela.destroy)
        amarrados = {acao: (lambda: None) for acao in menu.comandos_faltando({})}
        escolhas = {
            "aparencia": tk.StringVar(value=pele.CLASSICA),
            "densidade": tk.StringVar(value=pele.CONFORTAVEL),
        }
        barra = menu.montar(janela, amarrados, escolhas=escolhas)
        ver = janela.nametowidget(barra.entrycget(3, "menu"))
        alvo = comandos.rotulo("densidade")
        indice = next(
            i
            for i in range(ver.index(tk.END) + 1)
            if ver.type(i) == "cascade" and ver.entrycget(i, "label") == alvo
        )
        submenu = janela.nametowidget(ver.entrycget(indice, "menu"))
        rotulos = [submenu.entrycget(i, "label") for i in range(submenu.index(tk.END) + 1)]
        self.assertEqual([pele.rotulo_de_densidade(nome) for nome in pele.DENSIDADES], rotulos)

    def test_montar_recusa_item_de_densidade_sem_variavel(self) -> None:
        """Mesma trava da aparência: `radiobutton` sem variável desenha as opções sem nenhuma
        marcada, e a pessoa conclui que a escolha não pegou."""
        janela = tk.Toplevel(self.root)
        self.addCleanup(janela.destroy)
        amarrados = {acao: (lambda: None) for acao in menu.comandos_faltando({})}
        with self.assertRaises(KeyError) as erro:
            menu.montar(janela, amarrados, escolhas={"aparencia": tk.StringVar()})
        self.assertIn("densidade", str(erro.exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
