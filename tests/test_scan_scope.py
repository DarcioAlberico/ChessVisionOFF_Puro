"""A pergunta que o botão "Varrer o livro" faz antes de varrer.

O `scan_scope` é o diálogo e a regra de escopo; o que só quebra com widget -- o rádio padrão,
o seletor de arquivos cancelado que não fecha a janela -- fica aqui, e o que a Galeria faz com
a lista escolhida está no `test_gallery_panel`.
"""

from __future__ import annotations

import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from ambiente_de_teste import pasta_temporaria
from tk_root import raiz as raiz_do_processo

from chess_diagram_ocr.ui import scan_scope
from chess_diagram_ocr.ui.scan_scope import ABERTO, ESCOLHER, PASTA, ScanScope, ScanScopeDialog


class LivrosDaPastaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)

    def test_ordena_por_nome_e_ignora_o_que_nao_e_pdf(self) -> None:
        for nome in ("zebra.pdf", "alfa.pdf", "notas.txt"):
            (self.raiz / nome).write_bytes(b"")
        (self.raiz / "subpasta.pdf").mkdir()

        self.assertEqual(
            [caminho.name for caminho in scan_scope.books_in_folder(self.raiz)],
            ["alfa.pdf", "zebra.pdf"],
        )

    def test_pasta_inexistente_e_lista_vazia_e_nao_erro(self) -> None:
        """Acervo ainda não criado é estado normal de instalação nova, não é falha."""
        self.assertEqual(scan_scope.books_in_folder(self.raiz / "nao-existe"), [])


class EscopoTests(unittest.TestCase):
    """A única regra do módulo: quando pular o livro que já tem índice completo."""

    def test_um_livro_e_pedido_explicito_e_nunca_e_pulado(self) -> None:
        escopo = ScanScope(kind=ABERTO, books=(Path("livro.pdf"),))
        self.assertFalse(escopo.skip_complete, "revarrer *este* livro é o que se faz após treinar")

    def test_varios_livros_e_varre_o_que_falta(self) -> None:
        escopo = ScanScope(kind=PASTA, books=(Path("a.pdf"), Path("b.pdf")))
        self.assertTrue(escopo.skip_complete)


class ScanScopeDialogTests(unittest.TestCase):
    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz_do_processo()

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.acervo = Path(self.pasta.name)
        for nome in ("um.pdf", "dois.pdf"):
            (self.acervo / nome).write_bytes(b"")

    def _dialogo(self, **kwargs: object) -> ScanScopeDialog:
        dialogo = ScanScopeDialog(self.root, folder=self.acervo, **kwargs)  # type: ignore[arg-type]
        self.addCleanup(lambda: dialogo.winfo_exists() and dialogo.destroy())
        return dialogo

    def test_com_livro_aberto_o_padrao_e_ele(self) -> None:
        dialogo = self._dialogo(open_book=self.acervo / "um.pdf")
        self.assertEqual(dialogo.kind_var.get(), ABERTO)

        dialogo.confirm()
        assert dialogo.scope is not None
        self.assertEqual(dialogo.scope.books, (self.acervo / "um.pdf",))

    def test_sem_livro_aberto_o_padrao_e_a_pasta_e_o_radio_do_aberto_fica_cinza(self) -> None:
        """Sem PDF na tela o botão recusava varrer. Agora ele oferece o acervo."""
        dialogo = self._dialogo(open_book=None)
        self.assertEqual(dialogo.kind_var.get(), PASTA)
        self.assertEqual(str(dialogo.radio_aberto.cget("state")), tk.DISABLED)

        dialogo.confirm()
        assert dialogo.scope is not None
        self.assertEqual([livro.name for livro in dialogo.scope.books], ["dois.pdf", "um.pdf"])

    def test_pasta_vazia_deixa_a_opcao_cinza(self) -> None:
        vazia = pasta_temporaria(self)
        dialogo = ScanScopeDialog(self.root, open_book=None, folder=vazia)
        self.addCleanup(dialogo.destroy)
        self.assertEqual(str(dialogo.radio_pasta.cget("state")), tk.DISABLED)

    def test_escolher_em_disco_devolve_o_que_o_seletor_deu(self) -> None:
        escolhidos = [str(self.acervo / "dois.pdf"), str(self.acervo / "um.pdf")]
        dialogo = self._dialogo(open_book=None, choose=lambda: escolhidos)
        dialogo.kind_var.set(ESCOLHER)

        dialogo.confirm()
        assert dialogo.scope is not None
        self.assertEqual(dialogo.scope.kind, ESCOLHER)
        self.assertEqual([livro.name for livro in dialogo.scope.books], ["dois.pdf", "um.pdf"])
        self.assertTrue(dialogo.scope.skip_complete)

    def test_cancelar_o_seletor_de_arquivos_nao_fecha_a_pergunta(self) -> None:
        """"Escolhi errado" não é "desisti de varrer": a pessoa ainda quer marcar outro escopo."""
        dialogo = self._dialogo(open_book=None, choose=list)
        dialogo.kind_var.set(ESCOLHER)

        dialogo.confirm()
        self.assertIsNone(dialogo.scope)
        self.assertTrue(dialogo.winfo_exists(), "o diálogo não pode fechar sem escopo nenhum")

    def test_cancelar_a_pergunta_nao_devolve_escopo(self) -> None:
        dialogo = self._dialogo(open_book=self.acervo / "um.pdf")
        dialogo.cancel()
        self.assertIsNone(dialogo.scope)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
