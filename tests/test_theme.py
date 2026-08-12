"""O tema da janela e, sobretudo, a degradação dele (S-53).

O que precisa de teste aqui não é o tema bonito -- é a promessa de que ele **não pode
derrubar a ferramenta**. Um checkout sem `ttkbootstrap`, um bundle que não o incluiu ou um
`CVOFF_TTK_THEME` com nome errado têm de abrir a janela do mesmo jeito.
"""

from __future__ import annotations

import builtins
import unittest
from unittest.mock import patch

from chess_diagram_ocr.ui.theme import DEFAULT_THEME, THEME_ENV, apply_theme, available_themes


class _FakeRoot:
    """Não é um `tk.Misc`, e não precisa ser: `apply_theme` só confere que ele existe."""


class DegradationTests(unittest.TestCase):
    def test_sem_ttkbootstrap_a_janela_abre_em_ttk_puro(self) -> None:
        importador = builtins.__import__

        def _sem_ttkbootstrap(name: str, *args: object, **kwargs: object):
            if name == "ttkbootstrap":
                raise ImportError("simulando ambiente sem o pacote")
            return importador(name, *args, **kwargs)  # type: ignore[arg-type]

        with patch.object(builtins, "__import__", _sem_ttkbootstrap):
            self.assertEqual(apply_theme(_FakeRoot()), "ttk")
            self.assertEqual(available_themes(), [])

    def test_tema_inexistente_cai_no_padrao_em_vez_de_estourar(self) -> None:
        if not available_themes():
            self.skipTest("ttkbootstrap não está instalado neste ambiente")
        with patch.dict("os.environ", {THEME_ENV: "tema-que-nao-existe"}):
            self.assertEqual(apply_theme(_FakeRoot()), DEFAULT_THEME)

    def test_sem_janela_a_pre_condicao_e_dita_em_voz_alta(self) -> None:
        if not available_themes():
            self.skipTest("ttkbootstrap não está instalado neste ambiente")
        with self.assertRaises(ValueError):
            apply_theme(None)  # type: ignore[arg-type]


class ThemeTests(unittest.TestCase):
    def test_o_padrao_existe_no_conjunto_instalado(self) -> None:
        """Um padrão que não existe transformaria toda abertura num aviso no log."""
        temas = available_themes()
        if not temas:
            self.skipTest("ttkbootstrap não está instalado neste ambiente")
        self.assertIn(DEFAULT_THEME, temas)

    def test_a_variavel_de_ambiente_troca_o_tema(self) -> None:
        temas = available_themes()
        if len(temas) < 2:
            self.skipTest("ttkbootstrap não está instalado neste ambiente")
        outro = next(nome for nome in temas if nome != DEFAULT_THEME)
        with patch.dict("os.environ", {THEME_ENV: outro}):
            self.assertEqual(apply_theme(_FakeRoot()), outro)


if __name__ == "__main__":
    unittest.main()
