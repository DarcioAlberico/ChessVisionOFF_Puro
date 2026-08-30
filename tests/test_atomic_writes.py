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
    "pdf_to_pgn.py": "o PGN exportado e o .review.pgn: saída do produto, e a S-24 já grava parcial a cada 5 páginas",
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

**Mais tres saíram na S-453** -- `detection_census.py`, `experiments.py` e `side_survey.py` --,
e por um motivo que o critério de cima não previa: eles não saíram por serem valiosos, e sim
porque `atomic_write_text` é também o único jeito de garantir LF. Ver `SEM_LF_DECLARADO`.

O `labels.py` esteve nesta lista, e saiu na S-375. A escrita direta dele era a do **backup**,
não a do destino -- o original fica intacto enquanto a cópia é feita, que é o oposto do
defeito. Mas um `.bak-` truncado se parece com um backup e não é, e o `write_bytes` deixava
exatamente isso quando a cópia era interrompida. Hoje o backup nasce por `O_EXCL` e some no
caminho da exceção, e o módulo não precisa mais de exceção nenhuma.
"""


SEM_LF_DECLARADO = {
    "pdf_to_pgn.py": (
        "PGN exportado e .review.pgn: saída de produto, e o padrão PGN especifica CR/LF como "
        "terminador -- nenhum .pgn é versionado neste repositório"
    ),
}
"""Onde `write_text` pode gravar a quebra de linha da plataforma, **com o motivo de cada uma**.

Fora daqui, texto sai por `atomic_write_text`, que abre o temporário com `newline="\n"`.
`Path.write_text` sem `newline` traduz `\n` para `os.linesep`, que no Windows é `CR LF` -- e
todo relatório deste projeto vai para `docs/metrics/`, que o `.gitattributes` declara
`*.json text eol=lf`.

**O estrago não aparece no `git status`, e foi por isso que durou.** O git normaliza na leitura:
um arquivo com CRLF no disco casa com um blob em LF e a árvore parece limpa. Foi assim que os
`.py` do checkout principal ficaram com CRLF sem ninguém notar, até que o `_digest_of` -- que
hasheava os bytes crus -- começou a dar digests diferentes para o mesmo commit e a guarda da
S-218 passou a reprovar relatório correto num clone limpo. A cura lá foi normalizar antes de
hashear (S-325); a cura aqui é **não semear CRLF na árvore**, que é a metade que evita o
próximo caso.

**E ela foi cobrada em campo, não em teoria.** Na S-452 o `cvoff-census` gravou
`docs/metrics/deteccao_base.csv` e `.json` com CRLF, e foi preciso normalizá-los à mão antes do
commit. `write_census_json` era uma das cinco chamadas desta lista.
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

    def _sem_lf_explicito(self) -> list[str]:
        achados = []
        for caminho in sorted(SRC.rglob("*.py")):
            nome = _relativo(caminho)
            if nome in SEM_LF_DECLARADO:
                continue
            arvore = ast.parse(caminho.read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)):
                    continue
                if no.func.attr != "write_text":
                    continue
                quebra = next((k.value for k in no.keywords if k.arg == "newline"), None)
                if not (isinstance(quebra, ast.Constant) and quebra.value == "\n"):
                    achados.append(f"{nome}:{no.lineno}: write_text sem newline explícito")
        return achados

    def test_todo_write_text_grava_lf(self) -> None:
        """**O critério de aceite.** `Path.write_text` sem `newline` traduz `\n` para
        `os.linesep`, e no Windows isso é `CR LF`.

        Cinco chamadas gravavam assim, e três delas eram relatório para `docs/metrics/` -- que o
        `.gitattributes` declara `*.json text eol=lf`. O git normaliza na leitura, então o
        `git status` seguia limpo e nada apontava para o problema. É a mesma mecânica que encheu
        de CRLF os `.py` do checkout principal e fez a guarda da S-218 reprovar relatório correto
        num clone limpo.

        As três foram para o `atomic_write_text`, que abre o temporário com `newline="\n"` --
        então o conserto e a escrita atômica são o mesmo movimento, e elas saíram de `PERMITIDAS`
        no mesmo commit. Um caminho novo que grave a quebra da plataforma ou entra em
        `SEM_LF_DECLARADO` com o motivo escrito, ou falha aqui.
        """
        self.assertEqual(
            self._sem_lf_explicito(),
            [],
            "Escrita de texto sem LF explícito. Use `atomic_write_text`, ou declare o arquivo "
            "em SEM_LF_DECLARADO com o motivo.",
        )

    def test_a_lista_de_lf_nao_guarda_arquivo_que_nao_existe_mais(self) -> None:
        ausentes = [nome for nome in SEM_LF_DECLARADO if not (SRC / nome).exists()]
        self.assertEqual(ausentes, [])

    def test_cada_excecao_de_lf_diz_por_que(self) -> None:
        for nome, motivo in SEM_LF_DECLARADO.items():
            self.assertGreater(len(motivo), 20, f"{nome} está na lista de LF sem justificativa")

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
