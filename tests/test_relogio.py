"""Hora gravada com fuso, e lida nos dois formatos (S-908).

A guarda varre `src/` atrás de `datetime.now()` sem fuso e de `fromtimestamp` sem `tz`: a hora que sai
deles não diz de que fuso é, e duas delas comparadas como texto erram na volta do horário de verão.
"""

from __future__ import annotations

import ast
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import varredura

from chess_diagram_ocr import relogio

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src" / "chess_diagram_ocr"

PERMITIDAS: dict[str, str] = {}
"""`caminho relativo a SRC` -> por que aquele arquivo pode chamar a hora sem fuso.

Vazia: os nomes de arquivo com carimbo (`cli/audit.py`, o manifesto de `text/conflitos.py`) passaram a
`relogio.agora()`, que dá a mesma hora de parede. Quem acrescentar uma entrada diz aqui por quê."""


def _sem_fuso(arvore: ast.AST) -> list[int]:
    """As linhas de `X.now()` sem argumento, `X.utcnow()`, e `X.fromtimestamp(t)` / `utcfromtimestamp` sem `tz`."""
    linhas = []
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)):
            continue
        nome = no.func.attr
        com_tz = any(chave.arg == "tz" for chave in no.keywords)
        if (
            (nome == "now" and not no.args and not no.keywords)
            or nome in ("utcnow", "utcfromtimestamp")
            or (nome == "fromtimestamp" and len(no.args) < 2 and not com_tz)
        ):
            linhas.append(no.lineno)
    return sorted(linhas)


class GuardaTests(unittest.TestCase):
    def test_nenhuma_hora_sem_fuso_em_src(self) -> None:
        achados = []
        for caminho in varredura.fontes(SRC, recursivo=True, piso=300):
            nome = caminho.relative_to(SRC).as_posix()
            if nome in PERMITIDAS:
                continue
            for linha in _sem_fuso(ast.parse(caminho.read_text(encoding="utf-8"))):
                achados.append(f"{nome}:{linha}")
        self.assertEqual(achados, [], "hora sem fuso: use chess_diagram_ocr.relogio (agora_iso, agora, do_arquivo)")

    def test_a_guarda_acha_o_que_procura(self) -> None:
        # Uma guarda que não acha nada passa em verde sobre qualquer código: ela tem de acusar as formas antigas.
        codigo = (
            "datetime.now().isoformat()\n"
            "f'{datetime.now():%Y}'\n"
            "datetime.fromtimestamp(p.stat().st_mtime)\n"
            "datetime.utcnow()\n"
            "datetime.now(timezone.utc)\n"
            "datetime.fromtimestamp(t, tz=timezone.utc)\n"
            "datetime.fromtimestamp(t, timezone.utc)\n"
        )
        self.assertEqual(_sem_fuso(ast.parse(codigo)), [1, 2, 3, 4])

    def test_a_lista_nao_guarda_arquivo_que_nao_existe_mais(self) -> None:
        self.assertEqual([nome for nome in PERMITIDAS if not (SRC / nome).exists()], [])


class RelogioTests(unittest.TestCase):
    def test_agora_iso_tem_deslocamento_e_e_agora(self) -> None:
        gravada = datetime.fromisoformat(relogio.agora_iso())
        self.assertIsNotNone(gravada.tzinfo)
        self.assertLess(abs(gravada - datetime.now(timezone.utc)), timedelta(minutes=1))
        self.assertEqual(gravada.microsecond, 0)

    def test_a_hora_de_parede_continua_onde_estava(self) -> None:
        # `[11:16]` é como o índice do caderno e o painel mostram a hora: tem de ser a hora local.
        texto = relogio.agora_iso()
        self.assertEqual(texto[11:16], datetime.fromisoformat(texto).astimezone().strftime("%H:%M"))

    def test_ler_iso_compara_instantes_de_fusos_diferentes(self) -> None:
        mais_tarde = relogio.ler_iso("2026-10-25T02:10:00+00:00")
        mais_cedo = relogio.ler_iso("2026-10-25T02:30:00+01:00")
        assert mais_tarde is not None and mais_cedo is not None
        self.assertLess(mais_cedo, mais_tarde)

    def test_ler_iso_aceita_o_formato_antigo_como_hora_local(self) -> None:
        lida = relogio.ler_iso("2026-10-24T14:02:11")
        self.assertEqual(lida, datetime(2026, 10, 24, 14, 2, 11).astimezone())

    def test_ler_iso_aceita_z(self) -> None:
        self.assertEqual(relogio.ler_iso("2026-07-26T10:00:00Z"), datetime(2026, 7, 26, 10, tzinfo=timezone.utc))

    def test_ler_iso_ilegivel_e_none(self) -> None:
        for texto in ("", "ontem à tarde", "2026-13-40T99:00:00"):
            with self.subTest(texto=texto):
                self.assertIsNone(relogio.ler_iso(texto))

    def test_ler_iso_de_antes_de_1970_nao_levanta(self) -> None:
        # O Windows recusa converter hora local anterior a 1970 (`OSError`); a leitura não pode cair por isso.
        relogio.ler_iso("0001-01-01T00:00:00")

    def test_do_arquivo_e_o_mesmo_instante_com_fuso(self) -> None:
        instante = relogio.do_arquivo(1_700_000_000.0)
        self.assertIsNotNone(instante.tzinfo)
        self.assertEqual(instante.timestamp(), 1_700_000_000.0)


if __name__ == "__main__":
    unittest.main()
