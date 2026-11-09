"""Os campos de texto que só admitem uma lista fechada são `Literal`, e o mypy acusa o valor de fora (S-855).

O ouro (`split`, `lingua`, `origem`, `estrato`, `diagramacao`), a origem do token fundido, a classe de token e
a unidade da página eram `str` conferidos depois, ou nunca. Cada caso errado tem de dar **um** erro, e o caso
certo nenhum: sem o certo ao lado, um pacote que o mypy não achasse viraria `Any`, e os errados passariam
sem ter conferido nada -- o mesmo cuidado de `test_settings.test_o_tipo_efetivo_nao_grava`.
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import chess_diagram_ocr

CABECA = (
    "from typing import Literal\n"
    "from chess_diagram_ocr.text.fusao import Token, classe_do_token\n"
    "from chess_diagram_ocr.text.ouro import FolhaDoOuro, LivroDoOuro\n"
    "from chess_diagram_ocr.text.pagina import PaginaLida\n"
)

ERRADOS = {
    "split": 'LivroDoOuro("x", "treino", "eng")\n',
    "lingua": 'LivroDoOuro("x", "dev", "en")\n',
    "origem": 'LivroDoOuro("x", "dev", "eng", origem="scan")\n',
    "diagramacao": 'LivroDoOuro("x", "dev", "eng", diagramacao="outra")\n',
    "estrato": 'FolhaDoOuro("x", 1, "eng", "titulo", "dev")\n',
    "origem_do_token": 'Token("x", "camada")\n',
    "unidade": 'PaginaLida(unidade="cm")\n',
}

CERTO = (
    'LivroDoOuro("x", "teste", "spa", origem="ebook", diagramacao="vista")\n'
    'FolhaDoOuro("x", 1, "eng", "misto", "reserva")\n'
    'Token("x", "glifo")\n'
    'Token("x", "outro")\n'
    'PaginaLida(unidade="px")\n'
    'classe: Literal["prosa", "notacao", "outro"] = classe_do_token("a")\n'
)


class LiteralTests(unittest.TestCase):
    def test_o_mypy_acusa_o_valor_fora_da_lista(self) -> None:
        from mypy import api

        raiz_de_src = str(Path(chess_diagram_ocr.__file__).resolve().parents[1])
        with TemporaryDirectory() as tmp:
            casos = {**{f"errado_{nome}": fonte for nome, fonte in ERRADOS.items()}, "certo": CERTO}
            arquivos = []
            for nome, fonte in casos.items():
                arquivo = Path(tmp) / f"{nome}.py"
                arquivo.write_bytes((CABECA + fonte).encode("utf-8"))
                arquivos.append(str(arquivo))
            with mock.patch.dict(os.environ, {"MYPYPATH": raiz_de_src}):
                saida, _erro, _codigo = api.run(
                    [*arquivos, "--follow-imports=silent", "--no-incremental", "--no-site-packages"]
                )
        erros: dict[str, int] = dict.fromkeys(casos, 0)
        for linha in saida.splitlines():
            achado = re.search(r"([A-Za-z_]+)\.py:\d+: error", linha)
            if achado:
                erros[achado.group(1)] += 1
        self.assertEqual({nome: (0 if nome == "certo" else 1) for nome in casos}, erros, saida)


if __name__ == "__main__":
    unittest.main()
