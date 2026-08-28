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
import os
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src" / "chess_diagram_ocr"

ESCRITAS_DIRETAS = {"write_text", "write_bytes"}
"""Os métodos de `Path` que truncam antes de escrever."""

PERMITIDAS = {
    "atomic_io.py": "é a implementação da escrita atômica; é aqui que o temporário é escrito",
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

**Cinco relatórios saíram da lista na S-380**, e o argumento que os punha nela não sobrevive ao
próprio critério: "refeito rodando o comando de novo" vale para `cvoff-evaluate`, e não vale
para o `--save-matches` do `cvoff-games`, que é o artefato dos **104 minutos** de varredura
(`docs/ARCHITECTURE.md`), nem para o relatório de campo, que é a régua primária do projeto. E
mesmo nos baratos a escrita atômica não custa nada: são as mesmas três linhas, e um JSON
truncado é pior que um JSON ausente, porque `json.load` falha longe de onde a interrupção
aconteceu.

O `labels.py` esteve nesta lista, e saiu na S-375. A escrita direta dele era a do **backup**,
não a do destino -- o original fica intacto enquanto a cópia é feita, que é o oposto do
defeito. Mas um `.bak-` truncado se parece com um backup e não é, e o `write_bytes` deixava
exatamente isso quando a cópia era interrompida. Hoje o backup nasce por `O_EXCL` e some no
caminho da exceção, e o módulo não precisa mais de exceção nenhuma.
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


class SubstituicaoTravadaTests(unittest.TestCase):
    """O `os.replace` que o Windows recusa, e o que o usuário lê (S-373).

    Um `handle` aberto no destino faz o rename falhar com `PermissionError: [WinError 5]`, e
    quem estava na frente da tela recebia essa frase crua -- que manda procurar permissão de
    pasta num problema que é o Excel com o `labels.csv` aberto.
    """

    def _grava(self, destino: Path) -> None:
        from chess_diagram_ocr.atomic_io import atomic_write_text

        atomic_write_text(destino, "conteúdo novo\n")

    def test_insiste_e_a_segunda_tentativa_grava(self) -> None:
        """O antivírus solta sozinho em milissegundos: insistir resolve sem ninguém saber."""
        from unittest.mock import patch as _patch

        import chess_diagram_ocr.atomic_io as io_mod

        with tempfile.TemporaryDirectory() as pasta:
            alvo = Path(pasta) / "estado.json"
            alvo.write_text("antigo\n", encoding="utf-8")
            real = os.replace
            respostas = [PermissionError(5, "Acesso negado")]

            def travando(origem, destino):  # noqa: ANN001, ANN202
                if respostas:
                    raise respostas.pop()
                return real(origem, destino)

            with _patch.object(io_mod.os, "replace", side_effect=travando), \
                 _patch.object(io_mod, "ESPERA_ENTRE_TROCAS", 0.0):
                self._grava(alvo)

            self.assertEqual(alvo.read_text(encoding="utf-8"), "conteúdo novo\n")

    def test_travado_ate_o_fim_diz_o_que_aconteceu_e_nao_perde_o_antigo(self) -> None:
        from unittest.mock import patch as _patch

        import chess_diagram_ocr.atomic_io as io_mod

        with tempfile.TemporaryDirectory() as pasta:
            alvo = Path(pasta) / "labels.csv"
            alvo.write_text("filename,fen\n", encoding="utf-8")

            with _patch.object(io_mod.os, "replace", side_effect=PermissionError(5, "Acesso negado")), \
                 _patch.object(io_mod, "ESPERA_ENTRE_TROCAS", 0.0), \
                 self.assertRaises(PermissionError) as capturado:
                self._grava(alvo)

            recado = str(capturado.exception)
            self.assertIn("aberto em outro programa", recado)
            self.assertIn(alvo.name, recado)
            self.assertEqual(alvo.read_text(encoding="utf-8"), "filename,fen\n", "o antigo fica intacto")

    def test_nao_deixa_temporario_para_tras(self) -> None:
        """O `.tmp` vizinho é interno: ele não pode sobreviver ao erro."""
        from unittest.mock import patch as _patch

        import chess_diagram_ocr.atomic_io as io_mod

        with tempfile.TemporaryDirectory() as pasta:
            alvo = Path(pasta) / "estado.json"
            alvo.write_text("antigo\n", encoding="utf-8")

            with _patch.object(io_mod.os, "replace", side_effect=PermissionError(5, "Acesso negado")), \
                 _patch.object(io_mod, "ESPERA_ENTRE_TROCAS", 0.0), \
                 self.assertRaises(PermissionError):
                self._grava(alvo)

            self.assertEqual(sorted(p.name for p in Path(pasta).iterdir()), ["estado.json"])


if __name__ == "__main__":
    unittest.main()
