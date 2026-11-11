"""A catraca de `type: ignore`, `Any` e `except Exception` por pacote (S-804)."""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from ambiente_de_teste import pasta_temporaria

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools" / "qualidade"))

import catraca_de_tipos as catraca  # noqa: E402

COM_TUDO = '''
"""Docstring que fala de Any, de `except Exception` e de # type: ignore: nada disso conta."""
import typing
from typing import Any

# comentário com Any e except Exception: também não conta


def f(x: Any, y: "dict[str, Any]") -> typing.Any:
    try:
        return int(x)  # type: ignore[arg-type]
    except (ValueError, Exception):
        return y
    except OSError:
        return None
'''


class ContagemTests(unittest.TestCase):
    def test_conta_uso_e_nao_comentario_docstring_nem_import(self) -> None:
        self.assertEqual(catraca.contar_fonte(COM_TUDO), {"type_ignore": 1, "any": 3, "except_exception": 1})

    def test_type_ignore_dentro_de_string_nao_conta(self) -> None:
        self.assertEqual(catraca.contar_fonte('x = "a  # type: ignore"\n')["type_ignore"], 0)

    def test_pacote_de_cada_arquivo(self) -> None:
        raiz = Path("/r")
        self.assertEqual(
            [
                catraca.pacote_de(raiz / p, raiz)
                for p in ("app_pyqt.py", "src/chess_diagram_ocr/config.py", "src/chess_diagram_ocr/qt/a/b.py")
            ],
            ["app_pyqt.py", "raiz", "qt"],
        )


class CatracaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raiz = pasta_temporaria(self)
        self.pacote = self.raiz / "src" / "chess_diagram_ocr"
        (self.pacote / "text").mkdir(parents=True)
        self._escreve("text/a.py", COM_TUDO)
        self._escreve("b.py", "x = 1\n")
        self.registro = self.raiz / "registro.json"
        self.assertEqual(self._roda("--gravar")[0], 0)

    def _escreve(self, nome: str, fonte: str) -> None:
        (self.pacote / nome).write_bytes(fonte.encode())

    def _roda(self, *extra: str) -> tuple[int, str]:
        erro = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(erro):
            codigo = catraca.main(["--raiz", str(self.raiz), "--registro", str(self.registro), *extra])
        return codigo, erro.getvalue()

    def test_o_estado_registrado_passa(self) -> None:
        self.assertEqual(self._roda(), (0, ""))

    def test_except_exception_acrescentado_reprova_com_o_pacote_e_gravar_recusa(self) -> None:
        self._escreve("b.py", "try:\n    x = 1\nexcept Exception:\n    pass\n")
        codigo, erro = self._roda()
        self.assertEqual(codigo, 1)
        self.assertIn("raiz: except_exception subiu de 0 para 1", erro)
        antes = self.registro.read_bytes()
        self.assertEqual(self._roda("--gravar")[0], 1)
        self.assertEqual(self.registro.read_bytes(), antes)

    def test_descida_reprova_dizendo_o_numero_novo_ate_regravar(self) -> None:
        self._escreve("text/a.py", COM_TUDO.replace("  # type: ignore[arg-type]", ""))
        codigo, erro = self._roda()
        self.assertEqual(codigo, 1)
        self.assertIn("text: type_ignore desceu de 1 para 0", erro)
        self.assertEqual(self._roda("--gravar")[0], 0)
        self.assertEqual(self._roda(), (0, ""))
        dados = json.loads(self.registro.read_text(encoding="utf-8"))
        self.assertEqual(dados["pacotes"]["text"]["type_ignore"], 0)

    def test_forcar_grava_a_subida(self) -> None:
        self._escreve("b.py", "from typing import Any\nx: Any = 1\n")
        self.assertEqual(self._roda("--gravar", "--forcar")[0], 0)
        self.assertEqual(self._roda(), (0, ""))


class CatracaDoRepositorioTests(unittest.TestCase):
    """O `src/` e o `app_pyqt.py` de hoje contra `docs/metrics/catraca_de_tipos.json`."""

    def test_nenhuma_contagem_subiu_nem_desceu_sem_regravar(self) -> None:
        subidas, descidas = catraca.comparar(catraca.ler_registro(catraca.REGISTRO), catraca.contar_arvore(RAIZ))
        self.assertEqual(
            (subidas, descidas),
            ([], []),
            "Subiu: desfaça (o mypy existe para não precisar de `Any`, de `type: ignore` nem de "
            "`except Exception`). Desceu: `python tools/qualidade/catraca_de_tipos.py --gravar` "
            "baixa o teto, e o registro vai no mesmo commit.",
        )


if __name__ == "__main__":
    unittest.main()
