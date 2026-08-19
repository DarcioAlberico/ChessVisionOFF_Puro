"""Escrita de arquivo de **trabalho** passa por `atomic_io` (S-137).

O `CONTRIBUTING.md` declara a regra e nada a verificava -- ela era a única das três guardas de
arquitetura sem varredura. As irmãs têm: `tests/test_labels.py::SinglePortTests` para a porta
única do `labels.csv`, e a varredura de `tkinter` para os módulos que não podem importá-lo.

**O que a regra impede tem nome e data.** `Path.write_text` trunca o arquivo antes de escrever:
se o processo morrer no meio, o que sobra é meio arquivo -- e o `labels.csv` é 3.936 rótulos de
trabalho humano acumulado que a interface regrava inteiro a cada correção. É o defeito exato
que a S-25 fechou.

**A lista de exceções é o teste.** Um caminho novo que grave direto ou entra nela com o motivo
escrito, ou falha a suíte -- e escolher entre as duas coisas é justamente a decisão que estava
sendo tomada por omissão.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src" / "chess_diagram_ocr"

ESCRITAS_DIRETAS = {"write_text", "write_bytes"}
"""Os métodos de `Path` que truncam antes de escrever."""

PERMITIDAS = {
    "atomic_io.py": "é a implementação da escrita atômica; é aqui que o temporário é escrito",
    "labels.py": "grava o **backup**, não o destino: o original fica intacto enquanto a cópia é feita",
    "cli/evaluate.py": "relatório de medição em JSON pedido por --json; refeito rodando o comando de novo",
    "cli/export_onnx.py": "relatório de exportação ONNX em JSON, derivado do checkpoint que continua no disco",
    "cli/field.py": "relatório de campo em JSON; refeito com cvoff-field, ~20 s sobre o conjunto atual",
    "cli/provenance.py": "relatório de procedência em JSON, derivado do índice de dHash",
    "cli/games.py": "o JSON de casamentos do --save-matches: caro de refazer, mas derivado da base",
    "detection_census.py": "o censo de detecção: derivado do acervo, refeito com cvoff-census",
    "experiments.py": "os resultados da grade: derivados dos treinos, e o .pt de cada variante sobrevive",
    "pdf_to_pgn.py": "o PGN exportado e o .review.pgn: saída do produto, e a S-24 já grava parcial a cada 5 páginas",
    "side_survey.py": "o levantamento de procedência do lado a jogar: medição derivada, refeita com cvoff-sides",
    "ui/study_panel.py": "PGN de estudo, num caminho que o usuário acabou de escolher num diálogo de salvar",
}
"""Onde a escrita direta é aceitável, **com o motivo de cada uma**.

O critério é o mesmo que a S-25 usou: **trabalho humano acumulado passa por `atomic_io`;
artefato derivado e reproduzível pode ser escrito direto.** Um relatório de medição perdido
pela metade custa rodar o comando de novo; meio `labels.csv` custa meses de correção.

O `labels.py` está na lista por um motivo diferente dos outros, e ele é o mais interessante: a
escrita direta ali é a do **backup**, não a do destino. O original fica intacto enquanto a
cópia é feita, que é o oposto do defeito -- e o destino, esse, passa por
`atomic_write_bytes`.
"""


def _relativo(caminho: Path) -> str:
    return caminho.relative_to(SRC).as_posix()


class EscritaAtomicaTests(unittest.TestCase):
    def _escritas_diretas(self) -> list[str]:
        achados = []
        for caminho in sorted(SRC.rglob("*.py")):
            nome = _relativo(caminho)
            if nome in PERMITIDAS:
                continue
            arvore = ast.parse(caminho.read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute):
                    if no.func.attr in ESCRITAS_DIRETAS:
                        achados.append(f"{nome}:{no.lineno}: .{no.func.attr}(...)")
        return achados

    def test_nada_grava_direto_fora_da_lista_declarada(self) -> None:
        """O critério de aceite: um caminho novo entra na lista com motivo, ou falha aqui."""
        self.assertEqual(
            self._escritas_diretas(),
            [],
            "Escrita direta fora do `atomic_io`. Se ela for legítima, declare-a em PERMITIDAS "
            "com o motivo; se não for, use `atomic_write_text`/`atomic_write_bytes`.",
        )

    def test_a_lista_nao_guarda_arquivo_que_nao_existe_mais(self) -> None:
        """Exceção que sobrevive ao arquivo que a justificava vira permissão em branco."""
        ausentes = [nome for nome in PERMITIDAS if not (SRC / nome).exists()]
        self.assertEqual(ausentes, [])

    def test_cada_excecao_diz_por_que(self) -> None:
        for nome, motivo in PERMITIDAS.items():
            self.assertGreater(len(motivo), 20, f"{nome} está na lista sem justificativa")

    def test_os_donos_de_trabalho_humano_nao_estao_na_lista(self) -> None:
        """**A parte que dá sentido à lista.** Os quatro arquivos que guardam trabalho que
        ninguém recupera -- rótulos, partição, anotações da Galeria e conjunto de campo --
        nunca podem virar exceção, por mais conveniente que pareça no dia."""
        for nome in ("splits.py", "gallery.py", "field_eval.py"):
            with self.subTest(modulo=nome):
                self.assertNotIn(nome, PERMITIDAS)


if __name__ == "__main__":
    unittest.main()
