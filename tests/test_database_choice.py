"""A pergunta "em quais bases procurar?" e o cache que cada conjunto tem.

O que só quebra com widget -- as caixas marcadas, o `.pgn` trazido de fora -- fica na classe do
diálogo; a política (onde mora o cache de um conjunto, e o que a frase diz sobre ele) se testa
sem abrir Tk nenhum, que é o motivo de ela não morar dentro da janela.
"""

from __future__ import annotations

import sqlite3
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from tk_root import raiz as raiz_do_processo

from chess_diagram_ocr.games_cache import DEFAULT_STORE_PATH, open_store
from chess_diagram_ocr.ui.database_choice import DatabaseDialog, cache_note, describe_size, store_path_for


def _pgn(pasta: Path, nome: str, tamanho: int = 1024) -> Path:
    caminho = pasta / nome
    caminho.write_bytes(b"0" * tamanho)
    return caminho


class CaminhoDoCacheTests(unittest.TestCase):
    """Cada conjunto de bases guarda as respostas dele em separado."""

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.a = _pgn(self.raiz, "alfa.pgn")
        self.b = _pgn(self.raiz, "beta.pgn")

    def test_a_pasta_inteira_continua_no_arquivo_de_sempre(self) -> None:
        """É o conjunto que o `cvoff-games` usa: mudá-lo daria dois caches que não se enxergam."""
        caminho = store_path_for([self.a, self.b], default_bases=[self.a, self.b])
        self.assertEqual(caminho, DEFAULT_STORE_PATH)

    def test_um_subconjunto_ganha_arquivo_proprio(self) -> None:
        """Sem isto, experimentar uma base sozinha apagaria as respostas do acervo inteiro."""
        caminho = store_path_for([self.b], default_bases=[self.a, self.b])
        self.assertNotEqual(caminho, DEFAULT_STORE_PATH)
        self.assertEqual(caminho.parent, DEFAULT_STORE_PATH.parent)
        self.assertIn("beta", caminho.name)

    def test_o_caminho_nao_muda_quando_o_arquivo_cresce(self) -> None:
        """Tamanho é guarda de dentro do cache; no nome do arquivo ele abandonaria o anterior."""
        antes = store_path_for([self.b], default_bases=[self.a, self.b])
        self.b.write_bytes(b"1" * 4096)
        self.assertEqual(store_path_for([self.b], default_bases=[self.a, self.b]), antes)

    def test_a_ordem_da_escolha_nao_faz_dois_caches(self) -> None:
        um = store_path_for([self.a, self.b], default_bases=[self.a])
        outro = store_path_for([self.b, self.a], default_bases=[self.a])
        self.assertEqual(um, outro)


class FraseDoCacheTests(unittest.TestCase):
    """O que a próxima busca fará com o que já está guardado -- dito **antes** do clique."""

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.base = _pgn(self.raiz, "alfa.pgn")
        self.cache = self.raiz / "cache.sqlite"

    def _grava_cache(self, bases: list[Path]) -> None:
        with open_store(self.cache, database=bases) as loja:
            loja._conexao.execute("INSERT OR REPLACE INTO positions VALUES ('4k3/8/8/8/8/8/8/4K3', 0, '[]')")
            loja._conexao.commit()

    def test_sem_cache_a_frase_diz_que_a_busca_le_tudo(self) -> None:
        frase = cache_note([self.base], store_path=self.cache)
        self.assertIn("Sem respostas guardadas", frase)

    def test_cache_da_mesma_base_continua_valendo(self) -> None:
        self._grava_cache([self.base])
        frase = cache_note([self.base], store_path=self.cache)
        self.assertIn("continuam valendo", frase)

    def test_base_que_mudou_de_tamanho_avisa_que_o_cache_sera_descartado(self) -> None:
        """O caso real: um `.pgn` novo na pasta muda as contagens de tudo o que está guardado."""
        self._grava_cache([self.base])
        self.base.write_bytes(b"1" * 9999)
        frase = cache_note([self.base], store_path=self.cache)
        self.assertIn("descartadas", frase)

    def test_perguntar_nao_pode_descartar(self) -> None:
        """A frase lê o cache em modo leitura: descobrir o que se perderia não pode perdê-lo."""
        self._grava_cache([self.base])
        self.base.write_bytes(b"1" * 9999)
        cache_note([self.base], store_path=self.cache)
        with sqlite3.connect(str(self.cache)) as conexao:
            (linhas,) = conexao.execute("SELECT count(*) FROM positions").fetchone()
        self.assertEqual(linhas, 1, "a linha guardada tem de sobreviver à pergunta")

    def test_sem_base_marcada_a_frase_diz_isso(self) -> None:
        self.assertIn("Nenhuma base marcada", cache_note([]))


class TamanhoTests(unittest.TestCase):
    def test_gigabase_em_portugues(self) -> None:
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        caminho = _pgn(Path(pasta.name), "grande.pgn", 2_500_000_000)
        self.assertEqual(describe_size(caminho), "2,5 GB")

    def test_arquivo_ausente_nao_levanta(self) -> None:
        self.assertEqual(describe_size(Path("nao-existe.pgn")), "ausente")


class DatabaseDialogTests(unittest.TestCase):
    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz_do_processo()

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.a = _pgn(self.raiz, "alfa.pgn")
        self.b = _pgn(self.raiz, "beta.pgn")

    def _dialogo(self, **kwargs: object) -> DatabaseDialog:
        kwargs.setdefault("note", lambda _bases: "")
        dialogo = DatabaseDialog(self.root, folder=self.raiz, **kwargs)  # type: ignore[arg-type]
        self.addCleanup(lambda: dialogo.winfo_exists() and dialogo.destroy())
        return dialogo

    def test_por_padrao_todas_as_bases_da_pasta_vem_marcadas(self) -> None:
        """O comportamento da S-93 é o padrão da caixa: a pergunta não muda o que já valia."""
        dialogo = self._dialogo()
        dialogo.confirm()
        self.assertEqual(dialogo.chosen, (self.a, self.b))

    def test_desmarcar_deixa_a_gigabase_de_fora(self) -> None:
        dialogo = self._dialogo()
        dialogo._marcas[str(self.b)].set(False)
        dialogo.confirm()
        self.assertEqual(dialogo.chosen, (self.a,))

    def test_sem_nada_marcado_o_botao_fica_cinza_e_o_return_nao_fecha(self) -> None:
        dialogo = self._dialogo()
        dialogo._marcar(False)
        self.assertEqual(str(dialogo.btn_ok.cget("state")), tk.DISABLED)
        dialogo.confirm()
        self.assertIsNone(dialogo.chosen)
        self.assertTrue(dialogo.winfo_exists())

    def test_a_selecao_anterior_e_o_que_a_caixa_abre_marcado(self) -> None:
        dialogo = self._dialogo(selected=[self.a])
        self.assertEqual(dialogo.selection, (self.a,))

    def test_pgn_de_outra_pasta_entra_na_lista_ja_marcado(self) -> None:
        fora = _pgn(self.raiz.parent, "de_fora.pgn")
        self.addCleanup(fora.unlink)
        dialogo = self._dialogo(choose=lambda: [str(fora)])
        dialogo.add_from_disk()
        self.assertIn(fora, dialogo.selection)

        dialogo.confirm()
        assert dialogo.chosen is not None
        self.assertEqual(len(dialogo.chosen), 3, "a de fora entra sem tirar as da pasta")

    def test_adicionar_a_mesma_base_duas_vezes_nao_duplica(self) -> None:
        dialogo = self._dialogo(choose=lambda: [str(self.a)])
        dialogo._marcas[str(self.a)].set(False)
        dialogo.add_from_disk()
        self.assertEqual(len(dialogo._bases), 2, "a lista não pode crescer com o que já tem")
        self.assertIn(self.a, dialogo.selection, "trazê-la de novo é pedir que ela entre")

    def test_a_frase_do_cache_acompanha_o_que_esta_marcado(self) -> None:
        dialogo = self._dialogo(note=lambda bases: f"{len(bases)} marcada(s)")
        self.assertEqual(dialogo.note_var.get(), "2 marcada(s)")

        dialogo._marcas[str(self.b)].set(False)
        dialogo._atualizar()
        self.assertEqual(dialogo.note_var.get(), "1 marcada(s)")
        self.assertIn("1 base(s) marcada(s)", dialogo.total_var.get())

    def test_cancelar_nao_devolve_base_nenhuma(self) -> None:
        dialogo = self._dialogo()
        dialogo.cancel()
        self.assertIsNone(dialogo.chosen)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
