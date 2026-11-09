"""Escrita de arquivo passa por `atomic_io` (S-137, catraca da S-822).

O `CONTRIBUTING.md` declara a regra e nada a verificava -- ela era a única das três guardas de
arquitetura sem varredura. As irmãs têm: `tests/test_labels.py::SinglePortTests` para a porta
única do `labels.csv`, e a varredura de `tkinter` para os módulos que não podem importá-lo.

**O que a regra impede tem nome e data.** `Path.write_text` trunca o arquivo antes de escrever:
se o processo morrer no meio, o que sobra é meio arquivo -- e o `labels.csv` é 3.936 rótulos de
trabalho humano acumulado que a interface regrava inteiro a cada correção. É o defeito exato
que a S-25 fechou.

**A S-822 alargou a varredura.** A da S-137 olhava só `write_text` e `write_bytes`, e por fora
dela gravavam direto no destino `torch.save` (o `.pt` do treino de glifos), `np.savez` (o cache
de ~600 MB da varredura), `torch.onnx.export`, `path.open("w")` de CSV, o `.save(caminho)` da
Pillow -- e o próprio `atomic_io.write_image`. Hoje a guarda conhece todas essas formas, e a
exceção deixou de ser por **arquivo** para ser por **função**: um módulo inteiro na lista
deixava passar o caminho novo que alguém escrevesse ao lado do que tinha motivo.

**A lista de exceções é o teste, e ela só encolhe.** Um caminho novo que grave direto ou entra
nela com o motivo escrito -- e com o `TETO_DE_EXCECOES` subido no mesmo commit, à vista de quem
revisa --, ou falha a suíte. Exceção que não desculpa mais nada também reprova: ela viraria
permissão em branco para o próximo que escrevesse ali.
"""

from __future__ import annotations

import ast
import os
import re
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path
from typing import IO

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src" / "chess_diagram_ocr"

TRUNCAM = {"write_text", "write_bytes"}
"""Os métodos de `Path` que truncam antes de escrever: sempre acusados."""

DESTINO_NA_POSICAO = {
    "save": 0,  # Pillow, PyMuPDF, QImage: `.save(destino, ...)`; `.save()` sem argumento é do QPainter
    "savez": 0,
    "savez_compressed": 0,
    "savetxt": 0,
    "tofile": 0,
    "imwrite": 0,
    "to_csv": 0,
}
"""Gravadores cujo destino é o argumento daquela posição. Sem argumento ali, não grava arquivo."""

DESTINO_QUALIFICADO = {"torch.save": 1, "np.save": 0, "numpy.save": 0, "torch.onnx.export": 2}
"""Os que só se reconhecem pelo nome inteiro: o `.save` de `torch` tem o destino no 2.º argumento."""

MODO_DE_ARQUIVO = re.compile(r"^[rwxabtU+]{1,4}$")
"""O que é um modo de `open`. `"pdf"` (o filetype do `fitz.open`) não casa."""

GRAVADORES_ATOMICOS = {"atomic_write_stream", "atomic_write_path"}
"""Quem recebe uma função que escreve: o que ela escreve vai para o temporário vizinho."""

EM_MEMORIA = {"BytesIO", "StringIO"}

EXCECOES = {
    "export_checkpoint.py::CheckpointWriter.flush": (
        "o .partial.jsonl da S-24 é um registro de eventos que só cresce: acrescentar não reescreve "
        "o que já estava, e a linha rasgada no fim não parseia e é descartada na retomada"
    ),
    "qt/painel_de_estudo.py::PainelDeEstudo.write_pgn": (
        "o 'acrescentar ao PGN' da S-346: o arquivo é a base de partidas da pessoa, e reescrevê-la "
        "inteira por troca atômica para pôr um jogo no fim custaria a base toda a cada estudo -- o "
        "append nunca trunca, e a interrupção deixa só o jogo novo pela metade; sobrescrever já é atômico"
    ),
    "text/caderno.py::_gravar_conferido": (
        "é uma escrita atômica própria -- temporário vizinho, fsync e os.replace -- com a releitura "
        "que confere o conteúdo antes da troca, que o atomic_io não faz"
    ),
    "cli/provenance.py::_run_build": (
        "`indice.save(...)` é o ProvenanceIndex.save do projeto, não o da Pillow: ele grava por "
        "atomic_write_bytes, e esta mesma varredura o confere em provenance.py"
    ),
}
"""Onde gravar sem `atomic_io` é aceitável, **com o motivo de cada uma**, por `arquivo::função`.

O critério é o da S-25: **o que ninguém refaz passa por `atomic_io`**, e a escrita atômica custa
as mesmas três linhas em qualquer outro caso. Ficam de fora o registro que só cresce, o que já é
atômico por outro caminho, e o falso positivo de nome (`.save` de classe do projeto).

**Fora da varredura, de propósito: o modo `"x"`.** Criar exclusivo nunca destrói o que existia --
falha com `FileExistsError` --, e os dois usos são reserva de nome (`dataset._reservar_amostra`,
vazia, S-820) e trava (`caderno._travar`, cuja leitura tolera o conteúdo rasgado).

O `labels.py` esteve na lista da S-137, e saiu na S-375; o `pdf_to_pgn.py` saiu na S-822, depois
que a S-818 levou o PGN exportado ao `atomic_write_text`; e o `atomic_io.py` saiu também, porque o
`write_image` dele passou a gravar pelo mesmo caminho que os outros escritores do módulo.
"""

TETO_DE_EXCECOES = 4
"""**A catraca.** Só desce. Subir é decisão de revisão, não efeito colateral de um commit."""


class _Gravacoes(ast.NodeVisitor):
    """As chamadas que gravam arquivo direto no destino, com a função onde cada uma mora."""

    def __init__(self, nome: str) -> None:
        self.nome = nome
        self.escopo: list[str] = []
        self.corpos: list[ast.AST] = []
        self.achados: list[tuple[str, int, str]] = []

    # ---------------------------------------------------------------------------- escopo

    def _entrar(self, no: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.escopo.append(no.name)
        funcao = not isinstance(no, ast.ClassDef)
        if funcao:
            self.corpos.append(no)
        self.generic_visit(no)
        if funcao:
            self.corpos.pop()
        self.escopo.pop()

    visit_ClassDef = _entrar  # noqa: N815 - nome que o ast.NodeVisitor procura
    visit_FunctionDef = _entrar  # noqa: N815
    visit_AsyncFunctionDef = _entrar  # noqa: N815

    def _atribuicoes(self, nome: str) -> Iterator[ast.expr]:
        if not self.corpos:
            return
        for no in ast.walk(self.corpos[-1]):
            if isinstance(no, ast.Assign) and any(
                isinstance(alvo, ast.Name) and alvo.id == nome for alvo in no.targets
            ):
                yield no.value

    def _em_memoria(self, destino: ast.expr) -> bool:
        if not isinstance(destino, ast.Name):
            return False
        return any(
            isinstance(valor, ast.Call) and _ultimo_nome(valor.func) in EM_MEMORIA
            for valor in self._atribuicoes(destino.id)
        )

    def _modos(self, no: ast.expr) -> set[str]:
        valores = list(self._atribuicoes(no.id)) if isinstance(no, ast.Name) else [no]
        return {
            sub.value
            for valor in valores
            for sub in ast.walk(valor)
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and MODO_DE_ARQUIVO.match(sub.value)
        }

    # ---------------------------------------------------------------------------- chamadas

    def visit_Call(self, no: ast.Call) -> None:  # noqa: N802 - nome que o ast.NodeVisitor procura
        if _ultimo_nome(no.func) in GRAVADORES_ATOMICOS:
            # O que a função passada escreve vai para o temporário: não se olha dentro dela.
            self.visit(no.func)
            for argumento in no.args[:1]:
                self.visit(argumento)
            return
        forma = self._grava(no)
        if forma is not None:
            funcao = ".".join(self.escopo) or "<módulo>"
            self.achados.append((f"{self.nome}::{funcao}", no.lineno, forma))
        self.generic_visit(no)

    def _grava(self, no: ast.Call) -> str | None:
        nome = _ultimo_nome(no.func)
        qualificado = _nome_qualificado(no.func)
        if nome in TRUNCAM and isinstance(no.func, ast.Attribute):
            return f".{nome}(...)"
        if nome == "open":
            candidatos = [*no.args[:2], *(k.value for k in no.keywords if k.arg == "mode")]
            modos = {modo for candidato in candidatos for modo in self._modos(candidato)}
            if any(set(modo) & set("wa+") for modo in modos):
                return f"open(..., {sorted(modos)})"
            return None
        if qualificado in DESTINO_QUALIFICADO:
            posicao = DESTINO_QUALIFICADO[qualificado]
        elif nome in DESTINO_NA_POSICAO and isinstance(no.func, ast.Attribute):
            posicao = DESTINO_NA_POSICAO[nome]
        else:
            return None
        if len(no.args) <= posicao or self._em_memoria(no.args[posicao]):
            return None
        return f"{qualificado or nome}(...)"


def _ultimo_nome(funcao: ast.expr) -> str:
    if isinstance(funcao, ast.Attribute):
        return funcao.attr
    if isinstance(funcao, ast.Name):
        return funcao.id
    return ""


def _nome_qualificado(funcao: ast.expr) -> str:
    partes: list[str] = []
    while isinstance(funcao, ast.Attribute):
        partes.append(funcao.attr)
        funcao = funcao.value
    if not isinstance(funcao, ast.Name):
        return ""
    partes.append(funcao.id)
    return ".".join(reversed(partes))


def gravacoes_diretas(codigo: str, nome: str) -> list[tuple[str, int, str]]:
    """`(arquivo::função, linha, forma)` de cada gravação direta no destino em `codigo`."""
    visitante = _Gravacoes(nome)
    visitante.visit(ast.parse(codigo))
    return visitante.achados


def _relativo(caminho: Path) -> str:
    return caminho.relative_to(SRC).as_posix()


def _todas_as_gravacoes() -> list[tuple[str, int, str]]:
    achados: list[tuple[str, int, str]] = []
    for caminho in sorted(SRC.rglob("*.py")):
        achados.extend(gravacoes_diretas(caminho.read_text(encoding="utf-8"), _relativo(caminho)))
    return achados


SEM_LF_DECLARADO: dict[str, str] = {}
"""Onde `write_text` pode gravar a quebra de linha da plataforma, **com o motivo de cada uma**.

Fora daqui, texto sai por `atomic_write_text`, que grava os bytes do texto sem traduzir `\\n`.
`Path.write_text` sem `newline` traduz `\\n` para `os.linesep`, que no Windows é `CR LF` -- e
todo relatório deste projeto vai para `docs/metrics/`, que o `.gitattributes` declara
`*.json text eol=lf`.

**O estrago não aparece no `git status`, e foi por isso que durou.** O git normaliza na leitura:
um arquivo com CRLF no disco casa com um blob em LF e a árvore parece limpa. Foi assim que os
`.py` do checkout principal ficaram com CRLF sem ninguém notar, até que o `_digest_of` -- que
hasheava os bytes crus -- começou a dar digests diferentes para o mesmo commit e a guarda da
S-218 passou a reprovar relatório correto num clone limpo. A cura lá foi normalizar antes de
hashear (S-325); a cura aqui é **não semear CRLF na árvore**, que é a metade que evita o
próximo caso.

**E ela foi cobrada em campo, não em teoria.** Na S-454 o `cvoff-census` gravou
`docs/metrics/deteccao_base.csv` e `.json` com CRLF, e foi preciso normalizá-los à mão antes do
commit. `write_census_json` era uma das cinco chamadas desta lista. A última que restava, a do
`pdf_to_pgn.py`, saiu na S-822: a S-818 levou o PGN ao `atomic_write_text`.
"""


class EscritaAtomicaTests(unittest.TestCase):
    def test_nada_grava_direto_fora_da_lista_declarada(self) -> None:
        """O critério de aceite: um caminho novo entra na lista com motivo, ou falha aqui."""
        fora = [
            f"{onde}:{linha}: {forma}" for onde, linha, forma in _todas_as_gravacoes() if onde not in EXCECOES
        ]
        self.assertEqual(
            fora,
            [],
            "Gravação direta no destino fora do `atomic_io`. Use `atomic_write_text`/`_bytes`/"
            "`_stream`; se ela for legítima, declare a função em EXCECOES com o motivo.",
        )

    def test_toda_excecao_ainda_desculpa_alguma_gravacao(self) -> None:
        """Exceção que sobrevive à gravação que a justificava vira permissão em branco."""
        usadas = {onde for onde, _linha, _forma in _todas_as_gravacoes()}
        self.assertEqual(sorted(set(EXCECOES) - usadas), [])

    def test_a_lista_de_excecoes_so_encolhe(self) -> None:
        self.assertLessEqual(
            len(EXCECOES),
            TETO_DE_EXCECOES,
            "EXCECOES cresceu. Converta a gravação nova para o `atomic_io`; se não houver como, suba "
            "o TETO_DE_EXCECOES no mesmo commit, com a razão escrita na exceção.",
        )

    def test_cada_excecao_diz_por_que(self) -> None:
        for nome, motivo in EXCECOES.items():
            self.assertGreater(len(motivo), 40, f"{nome} está na lista sem justificativa")

    def test_os_donos_de_trabalho_humano_nao_estao_na_lista(self) -> None:
        """**A parte que dá sentido à lista.** Os arquivos que guardam trabalho que ninguém
        recupera -- rótulos, partição, anotações da Galeria e conjunto de campo -- e o próprio
        módulo atômico nunca podem virar exceção, por mais conveniente que pareça no dia."""
        for modulo in ("splits.py", "gallery.py", "field_eval.py", "labels.py", "atomic_io.py"):
            with self.subTest(modulo=modulo):
                self.assertFalse([nome for nome in EXCECOES if nome.startswith(f"{modulo}::")])

    def test_o_detector_acha_cada_forma(self) -> None:
        """**A guarda não pode ficar verde por estar cega.** Cada forma que a S-822 achou no código,
        escrita aqui, tem de ser acusada -- e as que gravam em memória ou no temporário, não."""
        codigo = "\n".join(
            (
                "import io, torch, numpy as np",
                "def grava(caminho, modelo, x, imagem, doc):",
                "    caminho.write_text('a')",
                "    caminho.write_bytes(b'a')",
                "    open(caminho, 'w')",
                "    caminho.open('wb')",
                "    open(caminho, mode='a')",
                "    modo = 'a' if x else 'w'",
                "    caminho.open(modo, encoding='utf-8')",
                "    torch.save(modelo, caminho)",
                "    np.savez(caminho, x=x)",
                "    np.savez_compressed(caminho, x=x)",
                "    np.save(caminho, x)",
                "    torch.onnx.export(modelo, (x,), str(caminho))",
                "    imagem.save(caminho)",
                "    doc.save(str(caminho), garbage=3)",
                "def nao_grava(caminho, modelo, x, imagem, pintor):",
                "    buffer = io.BytesIO()",
                "    torch.save(modelo, buffer)",
                "    imagem.save(buffer, format='PNG')",
                "    pintor.save()",
                "    open(caminho, encoding='utf-8')",
                "    caminho.open('rb')",
                "    open(caminho, 'xb')",
                "    fitz.open('pdf', x)",
                "    atomic_write_stream(caminho, lambda fluxo: torch.save(modelo, fluxo))",
                "    atomic_write_stream(caminho, lambda fluxo: np.savez(fluxo, x=x))",
                "    atomic_write_path(caminho, lambda tmp: torch.onnx.export(modelo, (x,), str(tmp)))",
            )
        )
        achados = gravacoes_diretas(codigo, "exemplo.py")
        self.assertEqual({onde for onde, _linha, _forma in achados}, {"exemplo.py::grava"})
        self.assertEqual(len(achados), 13, achados)

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

        As três foram para o `atomic_write_text`, que grava os bytes do texto sem traduzir --
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


class GravadorQueCaiTests(unittest.TestCase):
    """O `torch.save` que morre no meio dos 8 MB (S-822).

    Direto no destino, o `.pt` de antes já estava truncado quando o erro chegava. Pelo
    `atomic_write_stream`, quem cai no meio leva junto só o temporário.
    """

    def test_o_gravador_que_cai_no_meio_deixa_o_antigo_e_nenhum_temporario(self) -> None:
        from chess_diagram_ocr.atomic_io import atomic_write_stream

        def cai_no_meio(fluxo: IO[bytes]) -> None:
            fluxo.write(b"metade dos pesos")
            raise RuntimeError("disco cheio")

        with tempfile.TemporaryDirectory() as pasta:
            alvo = Path(pasta) / "pesos.pt"
            alvo.write_bytes(b"pesos de ontem")

            with self.assertRaises(RuntimeError):
                atomic_write_stream(alvo, cai_no_meio)

            self.assertEqual(alvo.read_bytes(), b"pesos de ontem")
            self.assertEqual(sorted(p.name for p in Path(pasta).iterdir()), ["pesos.pt"])

    def test_pelo_caminho_a_biblioteca_escreve_no_temporario_e_o_destino_nasce_inteiro(self) -> None:
        from chess_diagram_ocr.atomic_io import atomic_write_path

        vistos: list[Path] = []

        def biblioteca(caminho: Path) -> None:
            vistos.append(caminho)
            with open(caminho, "wb") as saida:
                saida.write(b"modelo onnx")

        with tempfile.TemporaryDirectory() as pasta:
            alvo = Path(pasta) / "m.onnx"
            atomic_write_path(alvo, biblioteca)

            self.assertEqual(alvo.read_bytes(), b"modelo onnx")
            self.assertNotEqual(vistos[0], alvo, "a biblioteca escreveu no destino, não no temporário")
            self.assertEqual(sorted(p.name for p in Path(pasta).iterdir()), ["m.onnx"])


if __name__ == "__main__":
    unittest.main()
