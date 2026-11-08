"""A identidade do livro numa função só (S-827).

"Mesmo livro" era decidido em sete lugares, cada um com o seu atalho para o caminho que não
resolve (caminho de rede fora do ar): `normcase` cru, `.lower()`, a string crua. Com `resolve`
funcionando eles concordavam por acaso; sem ele, `PDF/sub/../Livro.pdf` e `PDF/Livro.pdf` viravam
dois livros num lugar e um noutro.

A tabela de pares abaixo é a especificação. Ela roda contra `ui.livros.mesmo_livro` e contra cada
chamador que se dirige de teste -- **pelo que o chamador faz**, não pela função que ele usa: a
página guardada no histórico, a fila de revisão fundida ou não, a base listada uma vez ou duas. E
cada um roda duas vezes, com `resolve` funcionando e com `resolve` levantando `OSError` para os
caminhos da tabela. Os chamadores que não se dirigem daqui (a aba Texto, a janela, o PGN do
livro) ficam cobertos pela guarda de padrões do fim.
"""

from __future__ import annotations

import os
import re
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.arquivo_do_dono import Lida
from chess_diagram_ocr.review_queue import ReviewItem, ReviewQueue, ReviewStatus, gravar_fila
from chess_diagram_ocr.ui import galeria_declarada
from chess_diagram_ocr.ui.state import AppState

if TEM_PYQT:
    from chess_diagram_ocr.qt import dialogos as qt_dialogos
    from chess_diagram_ocr.qt import painel_de_revisao as qt_revisao

PROJETO = Path(__file__).resolve().parents[1]
SRC = PROJETO / "src" / "chess_diagram_ocr"
WINDOWS = os.name == "nt"

Par = tuple[str, str, str, bool]
"""(nome do caso, um, outro, é o mesmo livro?)."""


def pares(raiz: Path, extensao: str = ".pdf") -> list[Par]:
    """Os pares da especificação, com os livros de verdade criados em `raiz`.

    `outro` é sempre o livro de `raiz/PDF/`, menos no último par, que nem existe no disco.
    """
    (raiz / "PDF" / "sub").mkdir(parents=True, exist_ok=True)
    (raiz / "b").mkdir(exist_ok=True)
    livro = raiz / "PDF" / f"Livro{extensao}"
    livro.write_bytes(b"%PDF-1.4\n")
    (raiz / "b" / f"Livro{extensao}").write_bytes(b"%PDF-1.4\n")
    base = str(raiz)
    barra = base.replace("\\", "/")
    invertida = base.replace("/", "\\")
    return [
        ("barra normal contra a do sistema",f"{barra}/PDF/Livro{extensao}", str(livro), True),
        ("ponto-ponto", f"{barra}/PDF/sub/../Livro{extensao}", str(livro), True),
        # No POSIX a barra invertida é um caractere do nome, e a caixa distingue arquivos.
        ("barra invertida", f"{invertida}\\PDF\\Livro{extensao}", f"{barra}/PDF/Livro{extensao}", WINDOWS),
        ("caixa", f"{barra}/pdf/LIVRO{extensao.upper()}", str(livro), WINDOWS),
        ("mesmo nome noutra pasta", f"{barra}/b/Livro{extensao}", str(livro), False),
        ("outro livro na pasta", f"{barra}/PDF/Outro{extensao}", str(livro), False),
        ("inexistente com ponto-ponto", f"{barra}/Falta/x/../Novo{extensao}", f"{barra}/Falta/Novo{extensao}", True),
    ]


@contextmanager
def resolve_que_falha(raiz: Path) -> Iterator[None]:
    """`Path.resolve` levanta para os caminhos sob `raiz`, como num compartilhamento fora do ar.

    Só sob `raiz`: a fila de revisão e o resto do teste moram noutra pasta e resolvem.
    """
    original = Path.resolve
    prefixo = os.path.normcase(os.path.join(str(raiz), ""))

    def resolve(self: Path, strict: bool = False) -> Path:
        if os.path.normcase(str(self)).startswith(prefixo) or os.path.normcase(str(self)) == prefixo[:-1]:
            raise OSError(53, "O caminho da rede não foi encontrado")
        return original(self, strict=strict)

    with mock.patch.object(Path, "resolve", new=resolve):
        yield


class TabelaDosPares:
    """O molde: `decide(um, outro)` tem de dar a tabela, com e sem `resolve`."""

    extensao = ".pdf"

    def decide(self, um: str, outro: str) -> bool:  # pragma: no cover - cada caso define
        raise NotImplementedError

    def _conferir(self, falhando: bool) -> None:
        assert isinstance(self, unittest.TestCase), "o molde é misturado num TestCase"
        caso = self
        raiz = pasta_temporaria(caso)
        for nome, um, outro, esperado in pares(raiz, self.extensao):
            with caso.subTest(nome, resolve="falha" if falhando else "funciona"):
                if falhando:
                    with resolve_que_falha(raiz):
                        obtido = self.decide(um, outro)
                else:
                    obtido = self.decide(um, outro)
                caso.assertEqual(obtido, esperado, f"{um!r} x {outro!r}")

    def test_com_resolve(self) -> None:
        self._conferir(falhando=False)

    def test_com_o_caminho_que_nao_resolve(self) -> None:
        self._conferir(falhando=True)


class FuncaoUnicaTests(TabelaDosPares, unittest.TestCase):
    def decide(self, um: str, outro: str) -> bool:
        from chess_diagram_ocr.ui.livros import mesmo_livro

        return mesmo_livro(um, outro)


class ChaveTests(unittest.TestCase):
    """O que a chave promete além da igualdade: é congelada, e o hash curto segue a identidade."""

    def test_a_chave_serve_de_chave_de_dicionario_e_o_hash_curto_segue_a_identidade(self) -> None:
        from chess_diagram_ocr.ui.livros import chave_do_livro

        raiz = pasta_temporaria(self)
        tabela = pares(raiz)
        for nome, um, outro, esperado in tabela:
            with self.subTest(nome):
                chave_um, chave_outro = chave_do_livro(um), chave_do_livro(outro)
                assert chave_um is not None and chave_outro is not None
                self.assertEqual({chave_um: 1}.get(chave_outro) == 1, esperado)
                self.assertEqual(chave_um.curta == chave_outro.curta, esperado)
                self.assertRegex(chave_um.curta, r"^[0-9a-f]{8}$")

    def test_sem_livro_nao_ha_chave(self) -> None:
        """`""` não é a pasta atual: é "nenhum livro", e dois "nenhum" não são o mesmo livro."""
        from chess_diagram_ocr.ui.livros import chave_do_livro, mesmo_livro

        self.assertIsNone(chave_do_livro(None))
        self.assertIsNone(chave_do_livro(""))
        self.assertFalse(mesmo_livro(None, None))
        self.assertFalse(mesmo_livro("", ""))
        self.assertFalse(mesmo_livro(None, "livro.pdf"))


class GaleriaTests(TabelaDosPares, unittest.TestCase):
    """`mesmo_arquivo` decide se a fila de revisão é alimentada pela varredura da Galeria."""

    def decide(self, um: str, outro: str) -> bool:
        return galeria_declarada.mesmo_arquivo(Path(um), Path(outro))


class HistoricoDePaginasTests(TabelaDosPares, unittest.TestCase):
    """O livro reaberto por outra grafia volta à página em que foi deixado."""

    def decide(self, um: str, outro: str) -> bool:
        estado = AppState()
        estado.remember_page(Path(outro), 7)
        voltou = estado.page_for(Path(um)) == 7
        estado.remember_page(Path(um), 9)
        # O mesmo livro não ocupa duas entradas do histórico (nem dois itens de «Recentes»).
        self.assertEqual(len(estado.pdf_history), 1 if voltou else 2)
        return voltou


def _item(pagina: int, *, status: ReviewStatus = "pending") -> ReviewItem:
    return ReviewItem(
        pdf_path="livro.pdf",
        page_index=pagina,
        diagram_index=0,
        board_image=f"p{pagina}.png",
        fen="8/8/8/8/8/8/8/8",
        side_to_move="w",
        min_confidence=0.42,
        mean_entropy=0.1,
        priority=1.0,
        reasons=("confiança baixa",),
        status=status,
    )


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class FilaDeRevisaoTests(TabelaDosPares, unittest.TestCase):
    """A revarredura do mesmo livro funde, e o item revisado não ressuscita; de outro livro, troca."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.addCleanup(self.app.processEvents)

    def decide(self, um: str, outro: str) -> bool:
        pasta = pasta_temporaria(self)
        caminho = pasta / "fila.json"
        gravar_fila(Lida(ReviewQueue(source_pdf=outro, items=[_item(0, status="done")]), caminho))
        painel = qt_revisao.PainelDeRevisao(queue_path=caminho, cache_dir=pasta)
        self.addCleanup(descartar, painel)
        painel.aplicar_varredura(ReviewQueue(source_pdf=um, items=[_item(0)]), False, pages=frozenset({0}))
        return painel.queue.items[0].status == "done"


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class BasesDePartidasTests(TabelaDosPares, unittest.TestCase):
    """A base escolhida por outra grafia não aparece duas vezes na lista do diálogo."""

    extensao = ".pgn"

    def setUp(self) -> None:
        self.app = aplicacao()
        self.addCleanup(self.app.processEvents)

    def decide(self, um: str, outro: str) -> bool:
        pasta = Path(outro).parent
        if not Path(outro).exists():
            pasta.mkdir(parents=True, exist_ok=True)
            Path(outro).write_bytes(b"x")
        dialogo = qt_dialogos.DialogoDeBases(folder=pasta, selected=[Path(um)], nota=lambda _bases: "")
        self.addCleanup(descartar, dialogo)
        return len(dialogo._bases) == 1


class GuardaDosAtalhosTests(unittest.TestCase):
    """**Aceite da S-827**: nenhuma comparação de caminho de livro fora de `ui/livros.py`.

    Os padrões são os dos sete lugares que a spec achou, e o do PGN do livro que apareceu depois.
    Piso zero: a lista tem de estar vazia.
    """

    PADROES = (
        re.compile(r"resolve\(\)\s*[!=]="),  # `a.resolve() == b.resolve()`
        re.compile(r"[!=]=\s*\S*resolve\(\)"),
        re.compile(r"resolve\(\)\)\.(casefold|lower)\(\)"),  # a chave da aba Texto
        re.compile(r"\.lower\(\)\s*[!=]=\s*str\("),  # o atalho `str(um).lower() == str(outro).lower()`
        re.compile(r"\bnormcase\("),
        re.compile(r"source_pdf\s*[!=]=\s*\w+\.source_pdf"),  # a fusão da fila de revisão
        re.compile(r"\banterior\s*!=\s*alvo\b"),  # a troca de livro na janela
    )
    ISENTOS = {
        "ui/livros.py": "é a função",
        # A imagem do lote de importação, não um livro: o mesmo arquivo de imagem em dois lotes.
        "importacao_de_imagens.py": "imagem, não livro",
    }

    def test_nenhuma_comparacao_de_caminho_de_livro_fora_da_funcao(self) -> None:
        achados: list[str] = []
        for arquivo in sorted(SRC.rglob("*.py")):
            relativo = arquivo.relative_to(SRC).as_posix()
            if relativo in self.ISENTOS:
                continue
            for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), start=1):
                if any(padrao.search(linha) for padrao in self.PADROES):
                    achados.append(f"{relativo}:{numero}: {linha.strip()}")
        self.assertEqual(achados, [], "use `ui.livros.mesmo_livro` / `chave_do_livro`")

    def test_a_guarda_acha_o_que_procura(self) -> None:
        """Uma guarda de varredura vazia passa em verde sem olhar nada: cada padrão acha o seu."""
        exemplos = (
            "return um.resolve() == outro.resolve()",
            "if Path(a).resolve() != Path(b).resolve():",
            "return str(Path(caminho).resolve()).casefold()",
            "return str(um).lower() == str(outro).lower()",
            "return os.path.normcase(str(um))",
            "if existing.items and existing.source_pdf == queue.source_pdf:",
            "if anterior is not None and anterior != alvo:",
        )
        for padrao, exemplo in zip(self.PADROES, exemplos, strict=True):
            with self.subTest(exemplo):
                self.assertIsNotNone(padrao.search(exemplo))
        self.assertTrue((SRC / "ui" / "livros.py").exists(), "a isenção aponta para um arquivo que existe")


if __name__ == "__main__":
    unittest.main()
