"""A fita de grupos nomeados da pele "Fita", gerada do catálogo (S-227).

A Imagem 2 desenha quatro grupos com cabeçalho e treze comandos entre eles. Quando a spec foi
escrita não havia agrupamento declarado em lugar nenhum -- as duas barras do PDF eram listas
planas. A S-324 declarou os seis grupos; esta é a primeira pele que os desenha.

**O grupo é a unidade de quebra**, e é o que distingue esta fita de uma barra de botões: um grupo
partido ao meio não é um grupo. Ela não escreve uma segunda implementação de quebra -- usa a
`BarraFluida` da S-151 com os grupos como itens, e herda a propriedade que importa: nenhum é
descartado, em nenhuma largura.
"""

from __future__ import annotations

import tkinter as tk
import unittest
from tkinter import ttk

from tk_root import raiz

from chess_diagram_ocr.ui import barra, comandos, fita, icones, menu, pele, theme


class DeclaracaoDaFitaTests(unittest.TestCase):
    """Tudo aqui sem abrir janela: a fita é uma consulta ao catálogo."""

    def test_a_fita_sai_do_catalogo(self) -> None:
        """Acrescentar um comando **com ícone** ao catálogo o faz aparecer na fita, e é a única
        coisa que se faz para pô-lo lá."""
        do_catalogo = [registro.acao for registro in comandos.CATALOGO if registro.icone]
        self.assertEqual(do_catalogo, fita.acoes_da_fita())

    def test_os_quatro_grupos_sao_os_da_imagem(self) -> None:
        """ARQUIVO, EDICAO, VISUALIZACAO e OCR -- os mesmos quatro que a Imagem 2 desenha, e
        pela mesma razão: são os que têm comando com ícone."""
        self.assertEqual(
            [comandos.ARQUIVO, comandos.EDICAO, comandos.VISUALIZACAO, comandos.OCR],
            [grupo.grupo for grupo in fita.grupos()],
        )

    def test_grupo_vazio_nao_desenha_cabecalho(self) -> None:
        """ACERVO e AJUDA não têm comando com ícone. Um título solto é pior que a ausência dele:
        ele promete um grupo e entrega uma faixa em branco."""
        desenhados = {grupo.grupo for grupo in fita.grupos()}
        self.assertNotIn(comandos.ACERVO, desenhados)
        self.assertNotIn(comandos.AJUDA, desenhados)
        self.assertTrue(all(grupo.itens for grupo in fita.grupos()), "grupo sem item virou cabeçalho")

    def test_o_que_a_fita_nao_mostra_o_menu_alcanca(self) -> None:
        """A regra 2: a fita esconde vinte e dois comandos, e nenhum fica inalcançável."""
        na_fita = set(fita.acoes_da_fita())
        no_menu = set(menu.acoes_declaradas())
        perdidos = [
            registro.acao
            for registro in comandos.CATALOGO
            if registro.acao not in na_fita
            and registro.acao not in no_menu
            and registro.acao not in comandos.NA_LINHA_DE_CAMPO
        ]
        self.assertEqual([], perdidos)

    def test_o_cabecalho_e_o_rotulo_do_grupo(self) -> None:
        """`"VISUALIZACAO"` não é texto de interface -- quem traduz é `comandos.rotulo_do_grupo`."""
        for grupo in fita.grupos():
            with self.subTest(grupo=grupo.grupo):
                self.assertEqual(comandos.rotulo_do_grupo(grupo.grupo), grupo.rotulo)

    def test_o_rotulo_quebra_sem_perder_palavra(self) -> None:
        """O `ttk.Button` não aceita `wraplength`, então quem reparte é o módulo -- e o que se
        afirma é que ele reparte, e não encurta: **as mesmas palavras, noutra quebra.**

        A S-228 mediu se o modo compacto podia baixar para uma linha, e a resposta foi não: o
        rótulo ao lado do ícone em linha única pede 2.317 px, que são **três** linhas de fita em
        1366. A quebra em duas vale nos dois modos, e o achado está em `ui/fita.py`.
        """
        for acao in fita.acoes_da_fita():
            original = comandos.rotulo_de_botao(acao)
            with self.subTest(acao=acao):
                quebrado = fita.quebrar_rotulo(original)
                self.assertEqual(original.split(), quebrado.split())
                self.assertLessEqual(len(quebrado.splitlines()), fita.LINHAS_DO_ROTULO)

    def test_uma_palavra_so_nao_quebra(self) -> None:
        """`-`, `+` e "Salvar" não têm onde quebrar, e forçar não faria nada além de estragar."""
        self.assertEqual("-", fita.quebrar_rotulo("-"))
        self.assertEqual("Dataset", fita.quebrar_rotulo("Dataset"))

    def test_a_quebra_equilibra_as_duas_linhas(self) -> None:
        """Uma quebra que deixasse uma linha com uma palavra e outra com cinco daria um botão
        tão largo quanto o não quebrado -- que é o que ela veio evitar."""
        linhas = fita.quebrar_rotulo("Apagar a peça da casa selecionada").splitlines()
        self.assertEqual(2, len(linhas))
        self.assertLessEqual(abs(len(linhas[0]) - len(linhas[1])), 4)

    def test_todo_comando_da_fita_tem_traco_desenhado(self) -> None:
        for acao in fita.acoes_da_fita():
            with self.subTest(acao=acao):
                self.assertIn(comandos.comando(acao).icone, icones.ICONES)


class MontagemDaFitaTests(unittest.TestCase):
    """A fita desenhada, e a quebra por grupo."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.janela = tk.Toplevel(self.root)
        self.addCleanup(self.janela.destroy)
        self.chamados: list[str] = []
        self.amarrados = {
            acao: (lambda nome=acao: self.chamados.append(nome)) for acao in fita.acoes_da_fita()
        }

    def _montar(self, modo: str = fita.PLENO) -> fita.Fita:
        """A fita com o modo **cravado**, que é o que estes testes medem.

        Sem o `modo=`, a largura decide (S-228) -- e uma `Toplevel` sem geometria se ajusta ao
        conteúdo, o que faria a fita nascer compacta e estes testes medirem a outra forma. Quem
        exercita a troca automática é `ModoDaFitaTests`, que dá geometria à janela.
        """
        montada = fita.montar(self.janela, self.amarrados, modo=modo)
        montada.pack(fill=tk.X)
        self.root.update_idletasks()
        return montada

    def _molduras(self, montada: tk.Misc) -> list[ttk.Frame]:
        """As molduras de grupo, achadas pelo cabeçalho.

        Não dá para pegá-las por posição: a `BarraFluida` cria as molduras **de linha** dela
        entre os itens, e elas também são `ttk.Frame`. O cabeçalho é o que distingue um grupo.
        """
        rotulos = [grupo.rotulo for grupo in fita.grupos()]
        achadas: dict[str, ttk.Frame] = {}
        for filho in montada.winfo_children():
            if not isinstance(filho, ttk.Frame):
                continue
            for neto in filho.winfo_children():
                if isinstance(neto, ttk.Label) and str(neto.cget("text")) in rotulos:
                    achadas[str(neto.cget("text"))] = filho
        return [achadas[rotulo] for rotulo in rotulos if rotulo in achadas]

    def test_a_fita_usa_a_barra_e_nao_uma_segunda_quebra(self) -> None:
        """O critério dito como tipo: se ela fosse outra coisa, seria outra implementação de
        quebra -- e este projeto tem uma."""
        self.assertIsInstance(self._montar(), barra.BarraFluida)

    def test_a_quebra_e_sempre_entre_grupos(self) -> None:
        """Os **itens** da barra são os grupos, então não há onde partir um pelo meio: cada
        índice que `arranjo` distribui é um grupo inteiro."""
        montada = self._montar()
        larguras = [moldura.winfo_reqwidth() for moldura in self._molduras(montada)]
        self.assertEqual(len(fita.grupos()), len(larguras))

        for largura in (400, 700, 1100, 1600):
            with self.subTest(largura=largura):
                linhas = barra.arranjo(larguras, largura)
                indices = [indice for linha in linhas for indice in linha]
                self.assertEqual(sorted(indices), list(range(len(larguras))))

    def test_nenhum_grupo_e_descartado(self) -> None:
        """A propriedade da S-151, aplicada a grupos -- e em largura nenhuma ela cede."""
        montada = self._montar()
        larguras = [moldura.winfo_reqwidth() for moldura in self._molduras(montada)]
        for largura in range(120, 1700, 130):
            with self.subTest(largura=largura):
                distribuidos = sum(len(linha) for linha in barra.arranjo(larguras, largura))
                self.assertEqual(len(larguras), distribuidos)

    def test_a_fita_recusa_comando_sem_funcao(self) -> None:
        with self.assertRaises(KeyError) as erro:
            fita.montar(self.janela, {"salvar": lambda: None})
        self.assertIn("abrir_pdf", str(erro.exception))

    def test_cada_grupo_traz_o_cabecalho_e_os_botoes(self) -> None:
        montada = self._montar()
        for moldura, grupo in zip(self._molduras(montada), fita.grupos(), strict=True):
            rotulos = [
                str(filho.cget("text"))
                for filho in moldura.winfo_children()
                if isinstance(filho, ttk.Label)
            ]
            botoes = [
                filho
                for corpo in moldura.winfo_children()
                for filho in corpo.winfo_children()
                if isinstance(filho, ttk.Button)
            ]
            with self.subTest(grupo=grupo.grupo):
                self.assertEqual([grupo.rotulo], rotulos)
                self.assertEqual(len(grupo.itens), len(botoes))
                self.assertTrue(all(str(botao.cget("image")) for botao in botoes), "botão sem ícone")

    def test_clicar_no_botao_chama_o_comando(self) -> None:
        montada = self._montar()
        primeiro = next(
            filho
            for moldura in self._molduras(montada)
            for corpo in moldura.winfo_children()
            for filho in corpo.winfo_children()
            if isinstance(filho, ttk.Button)
        )
        primeiro.invoke()
        self.assertEqual([fita.acoes_da_fita()[0]], self.chamados)

    def test_a_fita_esta_registrada_como_pele(self) -> None:
        self.assertEqual(pele.CROMO_FITA, pele.registrada(pele.FITA).montar_cromo)
        self.assertEqual(["classica", "foco", "fita"], [registro.nome for registro in pele.PELES])


class OrcamentoDeAlturaTests(unittest.TestCase):
    """S-228: a fita custa altura, e a altura é declarada, pura e conferida contra o widget.

    A S-151 mediu o defeito que esta pele arrisca recriar -- cinco barras empilhadas = ~200 px,
    20% da altura da janela, sobre o painel cuja única razão de existir é mostrar a página grande.
    """

    def test_a_altura_e_pura_e_acompanha_a_fonte_do_sistema(self) -> None:
        """Sem `tkinter` na conta: os dois `linespace` entram como número, e é isso que permite
        afirmar o orçamento em 9, 10 e 12 pt sem trocar a fonte do Windows."""
        pequena = fita.altura_da_fita(fita.PLENO, linha_de_texto=15, linha_de_apoio=13)
        grande = fita.altura_da_fita(fita.PLENO, linha_de_texto=20, linha_de_apoio=17)
        self.assertLess(pequena, grande)
        self.assertGreater(pequena, fita.LADO_DO_ICONE[fita.PLENO])

    def test_o_orcamento_do_modo_pleno(self) -> None:
        """120 px é 12% de uma janela de 1000 de altura -- abaixo dos 20% que a S-151 chamou de
        defeito, e acima dos ~56 px das duas barras de hoje."""
        self.assertLessEqual(fita.altura_atual(fita.PLENO), fita.ORCAMENTO[fita.PLENO])

    def test_o_orcamento_do_modo_compacto(self) -> None:
        """64 px é o que cabe sem a fita competir com a página num 1366x768."""
        self.assertLessEqual(fita.altura_atual(fita.COMPACTO), fita.ORCAMENTO[fita.COMPACTO])

    def test_o_compacto_e_de_fato_mais_baixo(self) -> None:
        """Um modo compacto que não economizasse altura seria um modo a menos, não a mais."""
        self.assertLess(fita.altura_atual(fita.COMPACTO), fita.altura_atual(fita.PLENO))

    def test_a_densidade_entra_na_conta(self) -> None:
        """O eixo é da S-232; o que esta fase garante é que a conta já o carrega, em vez de
        cravar um número que ela teria de reescrever."""
        confortavel = fita.altura_da_fita(
            fita.PLENO, linha_de_texto=15, linha_de_apoio=13, densidade=pele.CONFORTAVEL
        )
        compacta = fita.altura_da_fita(
            fita.PLENO, linha_de_texto=15, linha_de_apoio=13, densidade=pele.COMPACTA
        )
        self.assertLess(compacta, confortavel)

    def test_modo_e_densidade_desconhecidos_levantam(self) -> None:
        """Um modo escrito errado que caísse no pleno devolveria um número plausível para o
        orçamento errado -- a mesma disciplina de `tokens.cor`."""
        with self.assertRaises(KeyError):
            fita.altura_da_fita("gigante", linha_de_texto=15, linha_de_apoio=13)
        with self.assertRaises(KeyError):
            fita.altura_da_fita(fita.PLENO, linha_de_texto=15, linha_de_apoio=13, densidade="folgada")


class ModoDaFitaTests(unittest.TestCase):
    """A troca de modo pela largura, com a janela dimensionada de propósito."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()
        # **Com o tema do programa, e não com o `ttk` cru.** As três constantes de moldura de
        # `ui/fita.py` foram medidas contra o tema que a janela aplica, e um `ttk.Button` sem tema
        # tem outro preenchimento -- 4 px a mais aqui. Medir a altura no tema errado afirmaria um
        # orçamento que nenhuma janela deste programa tem.
        theme.apply_theme(cls.root)

    def setUp(self) -> None:
        self.janela = tk.Toplevel(self.root)
        self.addCleanup(self.janela.destroy)
        self.amarrados = {acao: (lambda: None) for acao in fita.acoes_da_fita()}

    def _em(self, largura: int, altura: int = 300) -> fita.Fita:
        self.janela.geometry(f"{largura}x{altura}")
        montada = fita.montar(self.janela, self.amarrados)
        montada.pack(fill=tk.X)
        self.root.update_idletasks()
        self.root.update()
        return montada

    def test_a_altura_calculada_bate_com_a_medida(self) -> None:
        """O critério de aceite: a conta pura e o widget montado discordam em no máximo 2 px.

        É o que faz o orçamento ser afirmável sem `winfo_height` no critério -- e o que impede a
        conta de virar um número decorativo que ninguém compara com a tela.
        """
        for modo in fita.MODOS:
            with self.subTest(modo=modo):
                self.janela.geometry("1900x300")
                montada = fita.montar(self.janela, self.amarrados, modo=modo)
                montada.pack(fill=tk.X)
                self.root.update_idletasks()
                # `update` e nao so `update_idletasks`: a geometria pedida so chega a barra como
                # `<Configure>`, e sem ela a fita arranja contra a largura de 1 px com que nasceu.
                self.root.update()
                self.assertEqual(1, montada.linhas, "medida tirada de uma fita de duas linhas")
                self.assertLessEqual(abs(montada.winfo_reqheight() - montada.altura_prevista()), 2)
                montada.destroy()

    def test_a_fita_larga_fica_plena(self) -> None:
        montada = self._em(2200)
        self.assertEqual(fita.PLENO, montada.modo)
        self.assertEqual(1, montada.linhas)

    def test_em_1366_a_fita_fica_compacta_antes_de_dobrar(self) -> None:
        """1366x768 é a tela em que a S-151 mediu o defeito original, e é o caso que decide o modo.

        **O critério é "entra em compacto *antes* de precisar de segunda linha", e não "não
        dobra".** A spec previa que o compacto coubesse numa linha ali; a medição da S-228 diz que
        não cabe -- são 17 comandos e nenhum rótulo encurtado. O que o modo entrega é a altura: 90
        px contra os 200 que a fita plena gastaria na mesma tela, que é o defeito da S-151 de volta.
        """
        montada = self._em(1366, 768)
        self.assertGreater(montada.largura_de_troca, 1366, "a fita plena caberia: o caso mudou")
        self.assertEqual(fita.COMPACTO, montada.modo)
        plena_dobrada = 2 * fita.altura_atual(fita.PLENO)
        self.assertLess(montada.winfo_reqheight(), plena_dobrada)

    def test_a_troca_acontece_antes_de_precisar_de_segunda_linha(self) -> None:
        """**Derivado, e não escolhido.** O limiar é a largura que a fita plena pede para caber
        em uma linha, lida do próprio widget -- então "entra em compacto antes de dobrar" deixa
        de ser regra a cobrar e vira consequência da forma."""
        montada = self._em(2200)
        self.assertEqual(1, montada.linhas_em(montada.largura_de_troca))
        self.assertEqual(2, montada.linhas_em(montada.largura_de_troca - 1))

    def test_nenhuma_largura_descarta_comando(self) -> None:
        """De 800 a 2560: a troca de modo passa por cima de dezessete botões, e nenhum some."""
        montada = self._em(2200)
        esperado = fita.acoes_da_fita()
        for largura in range(800, 2561, 80):
            with self.subTest(largura=largura):
                self.janela.geometry(f"{largura}x300")
                self.root.update_idletasks()
                self.root.update()
                self.assertEqual(esperado, montada.acoes_desenhadas)

    def test_o_compacto_esconde_o_cabecalho_e_o_poe_na_dica(self) -> None:
        """Um grupo sem cabeçalho não é um grupo sem nome: ele passa a abrir a dica de cada botão
        dele. O cabeçalho custa uma linha de texto por fita, e no compacto é a linha que decide."""
        compacta = fita.montar(self.janela, self.amarrados, modo=fita.COMPACTO)
        compacta.pack(fill=tk.X)
        self.root.update_idletasks()
        self.addCleanup(compacta.destroy)
        rotulos_de_grupo = {grupo.rotulo for grupo in fita.grupos()}
        desenhados = {
            str(neto.cget("text"))
            for filho in compacta.winfo_children()
            for neto in filho.winfo_children()
            if isinstance(neto, ttk.Label)
        }
        self.assertEqual(set(), desenhados & rotulos_de_grupo)
        self.assertEqual(fita.acoes_da_fita(), compacta.acoes_desenhadas)

    def test_o_compacto_e_mais_estreito_que_o_pleno_nao_seria(self) -> None:
        """O achado da S-228 virado guarda: o compacto **não** pode ser mais largo que a forma
        que ele substitui numa proporção que o faça pedir mais linhas de fita.

        Ele é mais largo -- rótulo ao lado ocupa mais que rótulo embaixo --, e o que se afirma é
        o teto disso: no máximo uma linha de fita a mais que a plena, na largura em que a troca
        acontece. Foi essa conta que reprovou o rótulo de linha única, que pedia duas a mais.
        """
        montada = self._em(2400)
        limiar = montada.largura_de_troca
        compacta = fita.montar(self.janela, self.amarrados, modo=fita.COMPACTO)
        compacta.pack(fill=tk.X)
        self.addCleanup(compacta.destroy)
        self.root.update_idletasks()
        self.assertLessEqual(compacta.linhas_em(limiar - 1), 2)

    def test_a_histerese_impede_a_fita_de_piscar_no_limiar(self) -> None:
        """`HISTERESE` existe para que o tremor de um arrasto não remonte a fita, e o custo dela
        é **contável**: cada troca de modo destrói e recria os dezessete botões.

        A razão contável é a segunda que esta constante teve. A primeira -- escrita antes de os
        dois modos serem medidos lado a lado -- dizia que sem a histerese há um laço, porque *"o
        compacto pede menos largura"*. Ele pede **mais** (1.726 px contra 1.375), então o laço
        descrito não existia, e a justificativa não era verificável nem verdadeira. Esta é as
        duas coisas: o teste conta as remontagens.
        """
        montada = self._em(2200)
        limiar = montada.largura_de_troca
        self.assertGreater(limiar, 1, "sem limiar medido não há o que afirmar")

        remontagens = []
        original = montada._reconstruir

        def contar() -> None:
            remontagens.append(montada.modo)
            original()

        montada._reconstruir = contar  # type: ignore[method-assign]

        def em(largura: int) -> None:
            self.janela.geometry(f"{largura}x300")
            self.root.update_idletasks()
            self.root.update()

        # O tremor: quatro travessias do limiar, uma para cada lado. Sem histerese seriam quatro
        # remontagens -- 68 botões destruídos e recriados por um arrasto que não saiu do lugar.
        for _ in range(2):
            em(limiar - 1)
            em(limiar + 1)
        self.assertEqual(fita.COMPACTO, montada.modo, "a primeira travessia tinha de compactar")
        self.assertEqual(1, len(remontagens), f"a fita remontou {len(remontagens)} vezes no tremor")

        # E ela **volta**, quando a janela cresce de verdade: histerese é atraso, não trava.
        em(limiar + fita.HISTERESE)
        self.assertEqual(fita.PLENO, montada.modo)
        self.assertEqual(2, len(remontagens))

    def test_o_icone_do_compacto_e_menor_e_fica_ao_lado(self) -> None:
        pleno = fita.montar(self.janela, self.amarrados, modo=fita.PLENO)
        compacta = fita.montar(self.janela, self.amarrados, modo=fita.COMPACTO)
        for montada in (pleno, compacta):
            montada.pack(fill=tk.X)
            self.addCleanup(montada.destroy)
        self.root.update_idletasks()
        self.assertEqual(tk.TOP, str(pleno.botao("salvar").cget("compound")))
        self.assertEqual(tk.LEFT, str(compacta.botao("salvar").cget("compound")))
        self.assertLess(fita.LADO_DO_ICONE[fita.COMPACTO], fita.LADO_DO_ICONE[fita.PLENO])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
