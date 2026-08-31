"""A aba de Revisão do segundo frontend (S-22/S-119/S-503).

**O que estes testes cobrem, e o que não.** A prioridade, a fusão de duas varreduras, o que
"revisado" significa e o gate de aceitação são de `review_queue.py`, e já são afirmados em
`tests/test_review_queue.py` -- inclusive o adiamento da leitura do `labels.csv` (S-116), que
mudou de endereço na S-503 e continua sendo medido lá, agora sobre o acumulador compartilhado.

O que só existe deste lado são as três coisas em que o Qt difere do Tk e que quebram calado:

1. **O progresso atravessa a fronteira de thread por sinal**, e não por `panel.after(0, ...)`.
   Tocar num widget da thread da varredura derruba o processo, e nem sempre na hora.
2. **A posição na fila não é a linha da tabela.** Com "só pendentes" ligado a tabela mostra um
   subconjunto, e devolver o índice da linha marcaria o item errado como revisado.
3. **A tabela é a `TabelaQt`** e não um `QTreeWidget` cru: o alinhamento das quatro colunas
   numéricas é a leitura inteira de uma fila ordenada por prioridade (S-153).
"""

from __future__ import annotations

import unittest
from pathlib import Path

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.review_queue import ReviewItem, ReviewQueue
from chess_diagram_ocr.ui import varredura_de_revisao

if TEM_PYQT:
    from PyQt6.QtCore import QThread

    from chess_diagram_ocr.qt import painel_de_revisao as qt_revisao


def _item(pagina: int, *, status: str = "pending", prioridade: float = 1.0) -> ReviewItem:
    return ReviewItem(
        pdf_path="livro.pdf",
        page_index=pagina,
        diagram_index=0,
        board_image=f"p{pagina}.png",
        fen="8/8/8/8/8/8/8/8",
        side_to_move="w",
        min_confidence=0.42,
        mean_entropy=0.1,
        priority=prioridade,
        reasons=("confiança baixa",),
        status=status,  # type: ignore[arg-type]
    )


class DeclaracaoTests(unittest.TestCase):
    """A decisão é a mesma dos dois lados, e nenhum dos dois a reescreve."""

    def test_o_modulo_compartilhado_nao_carrega_tkinter(self) -> None:
        import ast

        arvore = ast.parse(Path(varredura_de_revisao.__file__).read_text(encoding="utf-8"))
        nomes = {no.names[0].name.split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.Import)}
        nomes |= {(no.module or "").split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom)}
        self.assertNotIn("tkinter", nomes)

@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PainelTests(unittest.TestCase):
    """O painel montado sobre uma fila de arquivo."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)

    def painel(self, itens: list[ReviewItem] | None = None, **kwargs: object) -> qt_revisao.PainelDeRevisao:
        caminho = self.pasta / "fila.json"
        if itens is not None:
            fila = ReviewQueue(source_pdf="livro.pdf", items=list(itens))
            fila.save(caminho)
        montado = qt_revisao.PainelDeRevisao(queue_path=caminho, cache_dir=self.pasta, **kwargs)  # type: ignore[arg-type]
        self.addCleanup(descartar, montado)
        montado.show()
        self.app.processEvents()
        return montado

    def test_so_pendentes_filtra_a_tabela_e_nao_a_fila(self) -> None:
        painel = self.painel([_item(0), _item(1, status="done"), _item(2)])
        self.assertEqual(painel.tabela.topLevelItemCount(), 2)
        painel.so_pendentes.setChecked(False)
        self.app.processEvents()
        self.assertEqual(painel.tabela.topLevelItemCount(), 3)
        self.assertEqual(len(painel.queue.items), 3, "o filtro é de vista, e não da fila")

    def test_a_posicao_selecionada_e_a_da_fila_e_nao_a_da_linha(self) -> None:
        """Com o filtro ligado a linha 1 da tabela é o item 2 da fila. Devolver a linha marcaria
        o item errado como revisado -- e o certo continuaria pendente sem ninguém notar."""
        painel = self.painel([_item(0), _item(1, status="done"), _item(2)])
        painel.selecionar_posicao(2)
        self.assertEqual(painel.tabela.indexOfTopLevelItem(painel.tabela.currentItem()), 1)
        self.assertEqual(painel.posicao_selecionada(), 2)

    def test_marcar_revisado_grava_e_redesenha(self) -> None:
        painel = self.painel([_item(0), _item(1)])
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.selecionar_posicao(1)
        painel.marcar_selecionado("done")
        self.assertEqual(painel.queue.items[1].status, "done")
        self.assertEqual(painel.tabela.topLevelItemCount(), 1, "o revisado saiu da vista")
        self.assertEqual(ReviewQueue.load(painel.queue_path).items[1].status, "done")
        self.assertTrue(vistos and "done" in vistos[-1])

    def test_sem_selecao_o_gesto_vira_frase_e_nao_exceção(self) -> None:
        painel = self.painel([_item(0)])
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.tabela.setCurrentItem(None)
        painel.marcar_selecionado("done")
        painel.abrir_selecionado()
        self.assertEqual(vistos, ["Selecione um item da fila."] * 2)

    def test_abrir_proximo_pendente_pula_o_resolvido(self) -> None:
        painel = self.painel([_item(0, status="done"), _item(1)])
        abertos: list[tuple[object, int]] = []
        painel.abriu.connect(lambda item, posicao: abertos.append((item, posicao)))
        painel.abrir_proximo_pendente()
        self.assertEqual([posicao for _item_, posicao in abertos], [1])

    def test_fila_toda_resolvida_diz_isso(self) -> None:
        painel = self.painel([_item(0, status="done")])
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.abrir_proximo_pendente()
        self.assertEqual(vistos, ["Nenhum item pendente na fila."])

    def test_o_motivo_inteiro_fica_sob_a_tabela(self) -> None:
        """A tabela dá a visão geral e o rodapé dá o texto (S-153)."""
        painel = self.painel([_item(0)])
        painel.selecionar_posicao(0)
        self.app.processEvents()
        self.assertEqual(painel.motivo_selecionado(), "Motivo: confiança baixa")
        self.assertEqual(painel.lbl_motivo.text(), painel.motivo_selecionado())

    def test_aplicar_correcao_grava_a_fen_e_marca_revisado(self) -> None:
        painel = self.painel([_item(0)])
        painel.aplicar_correcao(0, "8/8/8/8/8/8/8/K6k", "b")
        self.assertEqual(painel.queue.items[0].fen, "8/8/8/8/8/8/8/K6k")
        self.assertEqual(painel.queue.items[0].side_to_move, "b")
        self.assertEqual(painel.queue.items[0].status, "done")

    def test_posicao_fora_da_fila_nao_levanta(self) -> None:
        painel = self.painel([_item(0)])
        painel.aplicar_correcao(9, "8/8/8/8/8/8/8/K6k", "b")
        self.assertEqual(painel.queue.items[0].fen, "8/8/8/8/8/8/8/8")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class VarreduraTests(unittest.TestCase):
    """O sumidouro: a fila que vem da varredura da Galeria (S-119)."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)

    def painel(self, itens: list[ReviewItem] | None = None, *, com_pedido: bool = True):  # noqa: ANN201
        caminho = self.pasta / "fila.json"
        if itens is not None:
            ReviewQueue(source_pdf="livro.pdf", items=list(itens)).save(caminho)
        pedido = varredura_de_revisao.PedidoDeVarredura(
            pdf_path=Path("livro.pdf"),
            model_path=Path("modelo.pt"),
            labels_csv=self.pasta / "labels.csv",
        )
        montado = qt_revisao.PainelDeRevisao(
            queue_path=caminho,
            cache_dir=self.pasta,
            pedido_de_varredura=(lambda: pedido) if com_pedido else None,
        )
        self.addCleanup(descartar, montado)
        montado.show()
        self.app.processEvents()
        return montado

    def test_pedir_varredura_sem_ninguem_ouvindo_vira_frase(self) -> None:
        """O painel abre e funciona sem janela em volta; só não tem de onde varrer."""
        painel = self.painel([])
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.iniciar_varredura()
        self.assertEqual(vistos, ["Esta janela não tem de onde varrer o livro."])

    def test_a_varredura_desliga_o_botao_e_liga_o_cancelar(self) -> None:
        painel = self.painel([])
        self.assertIsNotNone(painel.sumidouro())
        self.assertFalse(painel.btn_varrer.isEnabled())
        self.assertTrue(painel.btn_cancelar.isEnabled())
        painel.terminar_varredura()
        self.assertTrue(painel.btn_varrer.isEnabled())
        self.assertFalse(painel.btn_cancelar.isEnabled())

    def test_sem_pdf_aberto_nao_ha_sumidouro(self) -> None:
        """A Galeria segue varrendo para a aba dela, e a fila fica como estava."""
        painel = self.painel([], com_pedido=False)
        self.assertIsNone(painel.sumidouro())
        self.assertTrue(painel.btn_varrer.isEnabled())

    def test_segunda_varredura_enquanto_a_primeira_roda_vira_frase(self) -> None:
        painel = self.painel([])
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.pediu_varredura.connect(lambda: None)
        painel.sumidouro()
        painel.iniciar_varredura()
        self.assertEqual(vistos, ["Já existe uma varredura de fila em execução."])

    def test_nada_lido_nada_entregue(self) -> None:
        """Retomar um livro já varrido inteiro (S-120) não pode apagar as pendências."""
        painel = self.painel([_item(0), _item(1)])
        sumidouro = painel.sumidouro()
        assert sumidouro is not None
        sumidouro.deliver(cancelled=False)
        self.assertEqual(len(painel.queue.items), 2, "a fila anterior sobreviveu")
        self.assertTrue(painel.btn_varrer.isEnabled(), "e a aba não fica com o botão cinza")

    def test_a_revarredura_funde_em_vez_de_substituir(self) -> None:
        """Sem a fusão, cada varredura apagaria o trabalho da sessão anterior."""
        painel = self.painel([_item(0, status="done"), _item(1)])
        nova = ReviewQueue(source_pdf="livro.pdf", items=[_item(0), _item(1)])
        painel.aplicar_varredura(nova, False, pages=frozenset({0, 1}))
        self.assertEqual(painel.queue.items[0].status, "done", "o revisado não ressuscitou")

    def test_o_progresso_vem_da_thread_da_varredura_por_sinal(self) -> None:
        """**A afirmação é sobre a thread**, e não sobre o texto. Uma chamada direta a
        `setText` da thread da varredura derruba o processo -- e nem sempre na hora, que é o
        pior formato desse defeito. O sinal atravessa pela conexão em fila que o Qt escolhe
        sozinho quando emissor e receptor estão em threads diferentes.
        """
        painel = self.painel([])
        sumidouro = painel.sumidouro()
        assert sumidouro is not None

        de_onde: list[object] = []

        class Varredura(QThread):
            def run(self) -> None:
                de_onde.append(QThread.currentThread())
                sumidouro.progress(3, 10)

        fio = Varredura()
        fio.start()
        fio.wait(5_000)
        self.app.processEvents()

        self.assertNotEqual(de_onde[0], painel.thread(), "o teste precisa de duas threads")
        self.assertEqual(painel.lbl_progresso.text(), "Varrendo o livro... página 3 de 10")

    def test_cancelar_avisa_e_diz_que_termina_a_pagina(self) -> None:
        painel = self.painel([])
        pedidos: list[int] = []
        painel.pediu_cancelamento.connect(lambda: pedidos.append(1))
        painel.cancelar_varredura()
        self.assertEqual(pedidos, [1])
        self.assertIn("termina a página atual", painel.lbl_progresso.text())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
