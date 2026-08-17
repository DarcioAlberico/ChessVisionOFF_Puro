"""Os `[project.scripts]` apontam para algo que existe e é chamável (S-128).

**11 dos 15 comandos `cvoff-*` não eram importados por teste nenhum.** Renomear um alvo em
`[project.scripts]`, ou mover um `main`, não quebrava nada até alguém tentar rodar o comando --
e quem tenta rodar é o usuário, no meio de um fluxo de horas.

Roda em qualquer ambiente: só importa módulo e confere que `main` é chamável. Não executa
comando nenhum.
"""

from __future__ import annotations

import importlib
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _entrypoints() -> dict[str, str]:
    """`[project.scripts]` lido à mão.

    Sem `tomllib`: ele é 3.11+ e o projeto está pinado em `requires-python = "==3.10.*"`. Uma
    dependência nova só para ler oito linhas de uma seção seria pagar caro pela elegância --
    e um parser de `chave = "valor"` numa seção declarada é o que a seção é.
    """
    linhas = (RAIZ / "pyproject.toml").read_text(encoding="utf-8").splitlines()
    dentro = False
    scripts: dict[str, str] = {}
    for linha in linhas:
        if linha.strip().startswith("["):
            dentro = linha.strip() == "[project.scripts]"
            continue
        if not dentro or "=" not in linha or linha.strip().startswith("#"):
            continue
        chave, _, valor = linha.partition("=")
        scripts[chave.strip()] = valor.strip().strip('"')
    return scripts


class EntrypointsTests(unittest.TestCase):
    def test_todo_entrypoint_declarado_e_importavel_e_chamavel(self) -> None:
        quebrados = []
        for comando, alvo in sorted(_entrypoints().items()):
            modulo_nome, _, funcao_nome = alvo.partition(":")
            try:
                modulo = importlib.import_module(modulo_nome)
            except ImportError as exc:
                quebrados.append(f"{comando}: não importa {modulo_nome} ({exc})")
                continue
            funcao = getattr(modulo, funcao_nome, None)
            if not callable(funcao):
                quebrados.append(f"{comando}: {alvo} não é chamável")

        self.assertEqual(quebrados, [], "Entrypoint declarado no pyproject.toml que não resolve.")

    def test_ha_entrypoint_declarado(self) -> None:
        """A guarda da guarda: um `[project.scripts]` vazio faria o teste acima passar sempre."""
        self.assertGreaterEqual(len(_entrypoints()), 15)

    def test_todo_cli_com_main_esta_declarado(self) -> None:
        """O outro sentido: um módulo de CLI que ninguém pode chamar é código morto com cara
        de recurso. Foi assim que `cvoff-gallery` e `cvoff-scan` precisaram ser lembrados no
        `pyproject.toml` -- e é o tipo de esquecimento que só aparece no uso.
        """
        declarados = {alvo.partition(":")[0] for alvo in _entrypoints().values()}
        faltando = []
        for caminho in sorted((RAIZ / "src" / "chess_diagram_ocr" / "cli").glob("*.py")):
            if caminho.name in ("__init__.py", "_ocr.py"):
                continue
            modulo = f"chess_diagram_ocr.cli.{caminho.stem}"
            if "\ndef main(" in caminho.read_text(encoding="utf-8") and modulo not in declarados:
                faltando.append(modulo)

        self.assertEqual(faltando, [], "Módulo de CLI com `main` e sem entrypoint no pyproject.toml.")


if __name__ == "__main__":
    unittest.main()
