"""Os CLIs de medição dizem o motor, e o gravam (S-727).

Virar o padrão de `ler_pagina` para a fusão mudaria o que eles medem sem guarda nenhuma, e o número
sairia plausível. A varredura é por `ast`, nos arquivos de verdade; os testes sintéticos existem para
provar que ela acusa, porque guarda que nunca acusou passa verde para sempre.
"""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path
from unittest import mock

from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr.cli import texto_custo, texto_estilo_motor, texto_lexico
from chess_diagram_ocr.text import custo as _custo

RAIZ = Path(__file__).resolve().parents[1]
PASTA_DOS_CLIS = RAIZ / "src" / "chess_diagram_ocr" / "cli"


def _nomes_de_ler_pagina(arvore: ast.Module) -> set[str]:
    """Por que nomes o `ler_pagina` de `text.leitor` entra neste arquivo, em qualquer nível."""
    nomes: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and (no.module or "").endswith("text.leitor"):
            nomes |= {apelido.asname or apelido.name for apelido in no.names if apelido.name == "ler_pagina"}
    return nomes


def chamadas_sem_motor(fonte: str) -> list[int]:
    """As linhas em que o `ler_pagina` do leitor é chamado sem `motor=` escrito.

    O homônimo local (`texto_placar_final` tem o seu) não conta, porque não veio de `text.leitor`. `**opcoes`
    conta como falta: o motor ali não está escrito, e é isso que a varredura pede.
    """
    arvore = ast.parse(fonte)
    importados = _nomes_de_ler_pagina(arvore)
    faltas: list[int] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        direto = isinstance(no.func, ast.Name) and no.func.id in importados
        pelo_modulo = isinstance(no.func, ast.Attribute) and no.func.attr == "ler_pagina"
        if (direto or pelo_modulo) and not any(k.arg == "motor" for k in no.keywords):
            faltas.append(no.lineno)
    return faltas


def _clis() -> list[Path]:
    return sorted(PASTA_DOS_CLIS.glob("texto_*.py"))


class VarreduraTests(unittest.TestCase):
    def test_nenhum_cli_chama_ler_pagina_sem_motor(self) -> None:
        faltas = {c.name: chamadas_sem_motor(c.read_text(encoding="utf-8")) for c in _clis()}
        self.assertEqual({}, {nome: linhas for nome, linhas in faltas.items() if linhas})

    def test_a_varredura_ve_os_clis_que_leem(self) -> None:
        """Se a pasta mudar de lugar ou o import de forma, a guarda fica verde e vazia: isto a faz gritar."""
        leem = [c.name for c in _clis() if _nomes_de_ler_pagina(ast.parse(c.read_text(encoding="utf-8")))]
        for nome in ("texto_custo.py", "texto_lexico.py", "texto_pagina.py", "texto_paragrafo.py", "texto_pesquisavel.py"):
            self.assertIn(nome, leem)

    def test_a_varredura_acusa_a_chamada_sem_motor(self) -> None:
        fonte = "from ..text.leitor import ler_pagina\nler_pagina(pdf, 0, dpi=220)\n"
        self.assertEqual([2], chamadas_sem_motor(fonte))

    def test_a_varredura_acusa_dentro_de_funcao_com_import_local(self) -> None:
        """É como a maioria dos CLIs importa: dentro da função, para o `--help` não carregar o `torch`."""
        fonte = "def f():\n    from ..text.leitor import ler_pagina\n    return ler_pagina(pdf, 0)\n"
        self.assertEqual([3], chamadas_sem_motor(fonte))

    def test_a_varredura_acusa_apelido_e_acesso_pelo_modulo(self) -> None:
        self.assertEqual([2], chamadas_sem_motor("from ..text.leitor import ler_pagina as lp\nlp(pdf, 0)\n"))
        self.assertEqual([2], chamadas_sem_motor("from ..text import leitor\nleitor.ler_pagina(pdf, 0)\n"))

    def test_a_varredura_acusa_motor_escondido_em_kwargs(self) -> None:
        self.assertEqual([2], chamadas_sem_motor("from ..text.leitor import ler_pagina\nler_pagina(pdf, 0, **opcoes)\n"))

    def test_a_varredura_aceita_motor_escrito_e_ignora_homonimo(self) -> None:
        self.assertEqual([], chamadas_sem_motor('from ..text.leitor import ler_pagina\nler_pagina(pdf, 0, motor="glifo")\n'))
        self.assertEqual([], chamadas_sem_motor("def ler_pagina(page):\n    return page\nler_pagina(1)\n"))


class RelatorioDizOMotorTests(unittest.TestCase):
    def test_o_custo_grava_o_motor(self) -> None:
        perfil = _custo.Perfil(paginas=1, segundos_por_pagina=1.0, etapas={}, chamadas={})
        _tabela, dados = texto_custo.relatorio(perfil, hoje_por_pagina=1.0, paginas_do_acervo=10)
        self.assertEqual(texto_custo.MOTOR_MEDIDO, dados["motor"])

    def test_o_custo_le_pelo_motor_que_grava(self) -> None:
        """O relatório não pode dizer um motor e a leitura usar outro."""
        with mock.patch("chess_diagram_ocr.text.leitor.ler_pagina") as ler:
            texto_custo._medir_pagina(Path("x.pdf"), 0, dpi=220, reconhecedor=object())
        self.assertEqual(texto_custo.MOTOR_MEDIDO, ler.call_args.kwargs["motor"])

    def test_o_custo_da_fusao_le_pela_fusao_como_a_janela(self) -> None:
        """A S-725: o que a D4 vai decidir é a fusão, com a reserva, e sem cache."""
        with mock.patch("chess_diagram_ocr.text.leitor.ler_pagina") as ler:
            texto_custo._medir_pagina(Path("x.pdf"), 0, dpi=220, reconhecedor=object(), motor="fusao", lingua="por")
        argumentos = ler.call_args.kwargs
        self.assertEqual((argumentos["motor"], argumentos["lingua"], argumentos["reserva"]), ("fusao", "por", True))
        self.assertNotIn("leitor_de_linha", argumentos, "sem leitor, `ler_pagina` usa o padrão, que nasce sem cache")

    def test_o_relatorio_diz_a_fusao(self) -> None:
        perfil = _custo.Perfil(paginas=1, segundos_por_pagina=1.0, etapas={}, chamadas={})
        _tabela, dados = texto_custo.relatorio(perfil, hoje_por_pagina=1.0, paginas_do_acervo=10, motor="fusao")
        self.assertEqual(dados["motor"], "fusao")

    def test_a_juncao_no_glifo_grava_o_motor_e_le_por_ele(self) -> None:
        pagina = mock.Mock(colunas=[])
        with (
            mock.patch("chess_diagram_ocr.text.leitor.ler_pagina", return_value=pagina) as ler,
            mock.patch("chess_diagram_ocr.text.recognizer.build_glyph_recognizer", return_value=object()),
            mock.patch.object(texto_lexico, "DEFAULT_PDF_DIR", RAIZ),
        ):
            dados = texto_lexico.medir_juncao_no_glifo(["README.md"], [0])
        self.assertEqual(texto_lexico.MOTOR_DA_JUNCAO, dados["motor"])
        self.assertEqual(texto_lexico.MOTOR_DA_JUNCAO, ler.call_args.kwargs["motor"])

    def test_o_estilo_declara_os_motores_que_mediu(self) -> None:
        pasta = pasta_temporaria(self)
        (pasta / "livro.pdf").write_bytes(b"")
        saida = pasta / "relatorio.json"
        with (
            mock.patch("chess_diagram_ocr.text.leitor._ha_classificador", return_value=True),
            mock.patch.object(texto_estilo_motor, "medir", return_value={}),
            mock.patch("builtins.print"),
        ):
            self.assertEqual(0, texto_estilo_motor.main(["--pdf-dir", str(pasta), "--json", str(saida)]))
        dados = json.loads(saida.read_text(encoding="utf-8"))
        self.assertEqual(list(texto_estilo_motor.MOTORES_MEDIDOS), dados["motores"])
        self.assertEqual(texto_estilo_motor.REFERENCIA, dados["referencia"])


if __name__ == "__main__":
    unittest.main()
