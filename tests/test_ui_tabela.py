"""As duas tabelas: a coluna que importa volta a ser legível (S-153).

**O achado tinha três partes e uma causa.** Os dois `Treeview` do projeto foram montados com o
mesmo bloco de oito linhas copiado, e o bloco não tinha barra horizontal nem alinhamento por
tipo. Daí: seis das oito colunas do Dataset inalcançáveis em 940 px, a coluna "Motivo" truncada
em **todas** as 129 linhas da fila, e `1623.8`, `40`, `1` e `0.082` encostados à esquerda.

O teste que fecha o item é o do critério de aceite, e ele é aritmético: para cada painel, a soma
das larguras mínimas contra a largura mínima que o painel pode ter. Se a soma passa, o painel
**precisa** declarar `xscrollcommand` — e o teste lê isso do widget, não do código.
"""

from __future__ import annotations

import shutil
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from tk_root import raiz

from chess_diagram_ocr.review_queue import ReviewItem
from chess_diagram_ocr.ui import tabela
from chess_diagram_ocr.ui.dataset_panel import DatasetPanel
from chess_diagram_ocr.ui.review_panel import ReviewPanel
from chess_diagram_ocr.ui.tabela import (
    ANCORA_NUMERO,
    ANCORA_TEXTO,
    Coluna,
    ancora,
    largura_minima,
    largura_total,
    precisa_de_barra_horizontal,
)

LARGURA_MINIMA_DO_PAINEL = 420
"""O `minsize` do painel esquerdo, de `app_tkinter.py`. É a largura em que as duas tabelas
precisam continuar inteiras -- e é ela que o critério de aceite da S-153 usa."""


class ColunaTests(unittest.TestCase):
    """Uma coluna sabe o que é, e alinhamento e largura mínima saem daí."""

    def test_numero_alinha_a_direita_e_texto_a_esquerda(self) -> None:
        self.assertEqual(ancora(Coluna("prio", "Prio.", 60, numerica=True)), ANCORA_NUMERO)
        self.assertEqual(ancora(Coluna("motivo", "Motivo", 460)), ANCORA_TEXTO)

    def test_coluna_de_largura_nao_positiva_e_recusada_na_declaracao(self) -> None:
        """Erro na declaração é erro no arquivo; erro em execução é uma coluna de 0 px na tela."""
        with self.assertRaises(ValueError):
            Coluna("x", "X", 0)

    def test_numero_elastico_e_contradicao_e_o_tipo_diz(self) -> None:
        """Coluna elástica é a de conteúdo sem tamanho previsível; número tem largura conhecida."""
        with self.assertRaises(ValueError):
            Coluna("prio", "Prio.", 60, numerica=True, elastica=True)

    def test_a_elastica_pode_encolher_e_as_outras_nao(self) -> None:
        """É ela que devolve espaço às outras quando aperta, e a que a linha de detalhe cobre."""
        fixa = Coluna("split", "Split", 60)
        elastica = Coluna("motivo", "Motivo", 480, elastica=True)
        self.assertEqual(largura_minima(fixa), 60)
        self.assertLess(largura_minima(elastica), elastica.largura)


class BarraHorizontalTests(unittest.TestCase):
    """A decisão pura, e o número que a torna verdadeira."""

    def test_a_soma_decide(self) -> None:
        colunas = (Coluna("a", "A", 200), Coluna("b", "B", 200))
        self.assertFalse(precisa_de_barra_horizontal(colunas, 500))
        self.assertFalse(precisa_de_barra_horizontal(colunas, 400))
        self.assertTrue(precisa_de_barra_horizontal(colunas, 399))

    def test_a_soma_usa_a_largura_minima_e_nao_a_declarada(self) -> None:
        """Porque é o `minwidth` que o `ttk` respeita -- e era o que faltava (ver abaixo)."""
        colunas = (Coluna("a", "A", 200), Coluna("b", "B", 300, elastica=True))
        self.assertEqual(largura_total(colunas), 200 + largura_minima(colunas[1]))
        self.assertLess(largura_total(colunas), 500)


class DeclaracaoDosPaineisTests(unittest.TestCase):
    """O critério de aceite, aritmético: as duas tabelas passam do painel, logo precisam rolar.

    Este teste não abre janela e é o que amarra o item: se um dia as colunas encolherem a ponto
    de caber em 420 px, ele falha e avisa que a barra virou enfeite -- e se alguém acrescentar
    uma nona coluna, ele continua verdadeiro pelo mesmo motivo.
    """

    def test_as_duas_tabelas_nao_cabem_no_painel_minimo(self) -> None:
        for nome, colunas in (("Dataset", DatasetPanel.COLUNAS), ("Revisão", ReviewPanel.COLUNAS)):
            with self.subTest(painel=nome):
                self.assertTrue(
                    precisa_de_barra_horizontal(colunas, LARGURA_MINIMA_DO_PAINEL),
                    f"{nome} cabe em {LARGURA_MINIMA_DO_PAINEL} px: a barra horizontal seria enfeite",
                )

    def test_toda_coluna_numerica_dos_dois_paineis_esta_declarada(self) -> None:
        """As quatro da fila e a de página do Dataset. Eram todas `anchor="w"`."""
        numericas = {
            "Dataset": {coluna.chave for coluna in DatasetPanel.COLUNAS if coluna.numerica},
            "Revisão": {coluna.chave for coluna in ReviewPanel.COLUNAS if coluna.numerica},
        }
        self.assertEqual(numericas["Dataset"], {"página"})
        self.assertEqual(numericas["Revisão"], {"prioridade", "página", "diagrama", "confiança"})

    def test_cada_painel_tem_exatamente_uma_coluna_elastica(self) -> None:
        """Duas elásticas dividem a folga e nenhuma fica com largura previsível; zero deixa a
        tabela com um vazio à direita em janela larga."""
        for nome, colunas in (("Dataset", DatasetPanel.COLUNAS), ("Revisão", ReviewPanel.COLUNAS)):
            with self.subTest(painel=nome):
                self.assertEqual([coluna.chave for coluna in colunas if coluna.elastica].__len__(), 1)

    def test_as_chaves_continuam_batendo_com_a_ordem_dos_valores_inseridos(self) -> None:
        """`COLUMNS` é derivada de `COLUNAS`: os três dicionários paralelos viraram uma lista."""
        self.assertEqual(DatasetPanel.COLUMNS, tuple(coluna.chave for coluna in DatasetPanel.COLUNAS))
        self.assertEqual(ReviewPanel.COLUMNS, tuple(coluna.chave for coluna in ReviewPanel.COLUNAS))


class MontagemTests(unittest.TestCase):
    """O widget: as duas barras existem, e as colunas não colapsam."""

    COLUNAS = (
        Coluna("prio", "Prio.", 60, numerica=True),
        Coluna("status", "Status", 80),
        Coluna("motivo", "Motivo", 460, elastica=True),
    )

    def setUp(self) -> None:
        self.janela = tk.Toplevel(raiz())
        self.janela.geometry("300x240")
        self.addCleanup(self.janela.destroy)
        self.arvore = tabela.montar(self.janela, self.COLUNAS, height=6)
        self.janela.update()

    def test_a_tabela_declara_as_duas_barras(self) -> None:
        """A vertical já estava lá; era a horizontal que faltava nos dois painéis."""
        self.assertTrue(str(self.arvore.cget("yscrollcommand")), "sem barra vertical")
        self.assertTrue(str(self.arvore.cget("xscrollcommand")), "sem barra horizontal: é o defeito da S-153")

    def test_a_barra_horizontal_de_fato_rola(self) -> None:
        """`xview` cobrindo menos que tudo é o que faz a coluna cortada ser alcançável.

        É a asserção que o `minwidth` torna verdadeira: com o padrão de 20 px o `ttk` espreme as
        colunas em vez de admitir que não cabe, `xview` devolve (0.0, 1.0) e a barra fica inerte
        com as colunas ilegíveis na tela -- o estado fotografado.
        """
        inicio, fim = self.arvore.xview()
        self.assertEqual(inicio, 0.0)
        self.assertLess(fim, 1.0, f"a tabela diz caber inteira em 300 px: xview={self.arvore.xview()}")

        self.arvore.xview_moveto(1.0)
        self.janela.update()
        self.assertGreater(self.arvore.xview()[0], 0.0, "rolar para a direita não moveu nada")

    def test_o_alinhamento_chega_ao_widget(self) -> None:
        for coluna in self.COLUNAS:
            with self.subTest(coluna=coluna.chave):
                self.assertEqual(str(self.arvore.column(coluna.chave, "anchor")), ancora(coluna))

    def test_a_largura_minima_chega_ao_widget(self) -> None:
        for coluna in self.COLUNAS:
            with self.subTest(coluna=coluna.chave):
                self.assertEqual(int(self.arvore.column(coluna.chave, "minwidth")), largura_minima(coluna))

    def test_so_a_elastica_estica(self) -> None:
        esticam = [coluna.chave for coluna in self.COLUNAS if self.arvore.column(coluna.chave, "stretch")]
        self.assertEqual(esticam, ["motivo"])

    def test_os_titulos_chegam_ao_cabecalho(self) -> None:
        for coluna in self.COLUNAS:
            with self.subTest(coluna=coluna.chave):
                self.assertEqual(str(self.arvore.heading(coluna.chave, "text")), coluna.titulo)

    def test_a_tabela_recebe_as_opcoes_do_painel(self) -> None:
        """`style` e `selectmode` passam adiante: é o que a aba Dataset usa para a monoespaçada."""
        arvore = tabela.montar(self.janela, self.COLUNAS, selectmode="browse", height=3)
        self.assertEqual(str(arvore.cget("selectmode")), "browse")
        self.assertEqual(int(arvore.cget("height")), 3)


class MotivoInteiroTests(unittest.TestCase):
    """A segunda metade do item: o rodapé que mostra o motivo sem exigir rolagem lateral.

    Rolar para o lado numa lista de 129 linhas custa a coluna de referência -- some a prioridade
    e a página, que são o que diz *qual* item é este. A tabela dá a visão geral, o rodapé dá o
    texto, e a leitura deixou de ser uma escolha entre as duas.
    """

    def setUp(self) -> None:
        self.host = tk.Frame(raiz())
        self.addCleanup(self.host.destroy)
        self.pasta = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.pasta, True)

    @staticmethod
    def _item(*motivos: str) -> ReviewItem:
        return ReviewItem(
            pdf_path="livro.pdf",
            page_index=2,
            diagram_index=1,
            board_image="x.png",
            fen="8/8/8/8/8/8/8/8",
            side_to_move="w",
            min_confidence=0.082,
            mean_entropy=0.4,
            priority=1623.8,
            reasons=motivos,
        )

    def _painel(self, itens: list[ReviewItem]) -> ReviewPanel:
        painel = ReviewPanel(
            self.host,
            scan_request=lambda: None,
            on_open=lambda _item, _pos: None,
            queue_path=self.pasta / "fila.json",
            cache_dir=self.pasta / "cache",
        )
        painel.queue.items = list(itens)
        painel.refresh()
        return painel

    def _selecionar_primeiro(self, painel: ReviewPanel) -> None:
        self._selecionar(painel, 0)

    def _selecionar(self, painel: ReviewPanel, linha: int) -> None:
        painel.tree.selection_set(painel.tree.get_children()[linha])
        # `update()` e nao `update_idletasks()`: `<<TreeviewSelect>>` e evento virtual, e
        # `update_idletasks` so drena as tarefas ociosas -- o rodape ficaria vazio no teste e
        # cheio no produto, que e a pior forma de um teste discordar da tela.
        self.host.update()

    def test_sem_selecao_o_rodape_fica_vazio(self) -> None:
        painel = self._painel([])
        self.assertEqual(painel.motivo_selecionado(), "")
        self.assertEqual(painel.detail_var.get(), "")

    def test_o_motivo_do_item_selecionado_vem_inteiro(self) -> None:
        """O texto que a coluna truncava em todas as 129 linhas."""
        motivos = ("ilegal: mais de um rei da mesma cor", "peças brancas demais", "o lado a jogar não bate")
        painel = self._painel([self._item(*motivos)])
        self._selecionar_primeiro(painel)

        mostrado = painel.detail_var.get()
        for razao in motivos:
            with self.subTest(razao=razao):
                self.assertIn(razao, mostrado)

    def test_o_rodape_mostra_mais_do_que_a_coluna_comporta(self) -> None:
        """A asserção que dá sentido ao rodapé: o texto passa da largura declarada da coluna.

        Sem ela, o rodapé poderia mostrar um motivo curto e parecer redundante -- e o item é
        justamente sobre os que não são curtos.
        """
        motivos = ("ilegal: mais de um rei da mesma cor", "peças brancas demais", "o lado a jogar não bate")
        painel = self._painel([self._item(*motivos)])
        self._selecionar_primeiro(painel)
        coluna_do_motivo = next(coluna for coluna in ReviewPanel.COLUNAS if coluna.chave == "motivo")
        self.assertGreater(len(painel.detail_var.get()), coluna_do_motivo.largura // 7)

    def test_item_sem_motivo_diz_isso_em_vez_de_ficar_em_branco(self) -> None:
        """Rodapé vazio com item selecionado se lê como "o programa não sabe", e ele sabe."""
        painel = self._painel([self._item()])
        self._selecionar_primeiro(painel)
        self.assertIn("sem sinal objetivo", painel.detail_var.get())

    def test_trocar_de_item_troca_o_motivo(self) -> None:
        """Um rodapé que não acompanha a seleção é pior que nenhum: ele mente sobre outro item."""
        painel = self._painel([self._item("primeiro"), self._item("segundo")])
        self._selecionar(painel, 0)
        self.assertIn("primeiro", painel.detail_var.get())

        self._selecionar(painel, 1)
        self.assertIn("segundo", painel.detail_var.get())


if __name__ == "__main__":
    unittest.main()
