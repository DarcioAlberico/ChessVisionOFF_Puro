"""O tema da janela e, sobretudo, a degradação dele (S-53).

O que precisa de teste aqui não é o tema bonito -- é a promessa de que ele **não pode
derrubar a ferramenta**. Um checkout sem `ttkbootstrap`, um bundle que não o incluiu ou um
`CVOFF_TTK_THEME` com nome errado têm de abrir a janela do mesmo jeito.
"""

from __future__ import annotations

import builtins
import unittest
from unittest.mock import patch

from tk_root import raiz

from chess_diagram_ocr.ui import tokens
from chess_diagram_ocr.ui.theme import (
    DEFAULT_THEME,
    THEME_ENV,
    apply_theme,
    available_themes,
    cor_atual,
    estilo_atual,
)


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


class CorSobOTemaEmUsoTests(unittest.TestCase):
    """As cores que chegam à tela com o tema de verdade aplicado, e não a reserva (S-163).

    Este teste existe porque o anterior não bastou. `tests/test_ui_tokens.py` afirma a resolução
    contra um `Style` falso, e ali os três papéis de texto sempre foram distintos. Na janela em
    execução eles eram **o mesmo** `#212529`: `style.lookup("danger.TLabel", "foreground")` sobe a
    cadeia de herança do Tk e devolve o do `TLabel` base sem dizer que o derivado não tinha cor
    própria. Verde de "já salvo", vermelho de "posição ilegal" e cinza de apoio saíam iguais.

    O instrumento aqui é o `Style` real, com o tema real. É a diferença entre afirmar a função e
    afirmar o que o usuário vê.
    """

    def setUp(self) -> None:
        if not available_themes():
            self.skipTest("ttkbootstrap não está instalado neste ambiente")
        self.raiz = raiz()
        apply_theme(self.raiz)

    def test_os_tres_papeis_de_texto_chegam_distintos_a_tela(self) -> None:
        cores = {papel: cor_atual(papel) for papel in tokens._DO_TEMA}
        self.assertEqual(
            len(set(cores.values())),
            len(cores),
            f"papéis de significado diferente com a mesma cor sob o tema em uso: {cores}",
        )

    def test_cada_um_deles_passa_em_contraste_como_texto(self) -> None:
        """Um papel de texto que o tema respondesse mal reprovaria aqui, e não na tela (S-146)."""
        fundo = tokens.cor(tokens.SUPERFICIE_PADRAO, estilo_atual())
        for papel in tokens._DO_TEMA:
            with self.subTest(papel=papel):
                razao = tokens.razao_de_contraste(cor_atual(papel), fundo)
                self.assertGreaterEqual(razao, tokens.AA_TEXTO, f"{papel}: {razao:.2f}:1")


if __name__ == "__main__":
    unittest.main()
