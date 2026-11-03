"""*Carregar PGN do livro…*: o `.pgn` que vem com o PDF digital, ligado à janela (S-590 a S-595).

O núcleo é `livro_com_pgn` (puro): casa cada diagrama com o seu nó e diz o estado. Este arquivo é
o fio que só a janela pode dar, e mora fora dela pela regra de `qt/importador_de_livro.py` -- cada
fio que a janela não segura é uma linha a menos na catraca de `test_packaging`. Na janela são quatro
linhas: montar, a tabela de comandos, a chamada em `_chegaram_itens` e a de quando o livro abre.

## O que acontece numa página lida

`aplicar(pagina, itens)` roda depois do reconhecimento, **fora do caminho de medição** (S-218): o
`service.py` continua lendo a imagem como sempre, e só depois a FEN do livro entra.

- `CONFERE`, `CORRIGIDO` e `SEM_LEITURA`: a posição e o lado a jogar do nó vão ao Resultado como
  edição desfazível (`PainelDeResultado.adotar_do_livro`), com as casas trocadas em roxo e a frase
  «PGN do livro: Chapter 1 · Game 3 · 5.dxc5 -- ...» nos detalhes. A aba Texto recebe a mesma FEN,
  e é ela que o EPUB/DOCX escreve.
- `DISCORDA`: a leitura fica, e o diagrama entra na Revisão com a FEN do livro como sugestão e o
  motivo escrito. Decidir sozinho trocaria um erro do modelo por um erro de pareamento.
- `FALTANDO`: o rodapé diz quantos diagramas desta página o PDF perdeu; *Diagramas que faltam no
  PDF…* lista os do livro inteiro, desenhados do PGN, e *Pôr na folha os diagramas que faltam* os
  insere na folha da aba Texto (S-595).

## O livro inteiro, e não só a página

A Galeria (S-594) e os que faltam precisam do livro casado inteiro, sem o modelo -- só legendas e
imagens. Isso é lido junto com o índice e guardado em `do_livro`, e os dois comandos respondem na hora.

## Por que o índice é lido em segundo plano

O PGN do Harikrishna tem 120 partidas e 12.697 nós; ler e indexar leva ~1 s, e casar as 748 páginas
mais ~6 s. Feito na mão da interface, seriam sete segundos de janela parada a cada livro aberto. A
leitura começa quando o livro abre (`livro_aberto`), e não na primeira página lida: começar ali fazia
a primeira página chegar antes do índice. A `Tarefa` é sem pai e o slot não é lambda sobre `self` (a
memória "exceção em slot do PyQt6 é qFatal"): a resposta que chega depois de a janela fechar não pode
encontrar este objeto apagado.
"""

from __future__ import annotations

import logging
import weakref
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtGui import QGuiApplication, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr import livro_com_pgn as lp
from chess_diagram_ocr.atomic_io import atomic_write_bytes
from chess_diagram_ocr.pgn_do_livro import IndiceDoLivro
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.trabalho import Tarefa, manter_viva
from chess_diagram_ocr.ui import estilos

__all__ = ["COMANDOS", "LivroComPgn", "donos", "itens_da_pagina"]

logger = logging.getLogger(__name__)

COMANDOS: dict[str, str] = {
    "carregar_pgn_do_livro": "carregar",
    "diagramas_que_faltam": "mostrar_os_que_faltam",
    "esquecer_pgn_do_livro": "esquecer",
    "estudar_na_arvore_do_livro": "estudar_na_arvore",
    "preencher_a_galeria_pelo_livro": "preencher_a_galeria",
    "por_na_folha_os_que_faltam": "por_na_folha",
}
"""`ação do catálogo -> método`. A janela os põe na tabela dela por nome, como os da sala."""

LADO_DA_MINIATURA = 220


def donos(dono: Callable[[], LivroComPgn]) -> dict[str, Callable[[], object]]:
    """A parte desta tabela na de `janela._comandos`, **preguiçosa**: o menu monta a tabela antes de
    a janela criar o `LivroComPgn`, e cada comando o procura só quando é acionado."""

    def acionar(metodo: str) -> Callable[[], object]:
        return lambda: getattr(dono(), metodo)()

    return {acao: acionar(metodo) for acao, metodo in COMANDOS.items()}


def _sobreposicao(a: Sequence[float], b: Sequence[float]) -> float:
    """Interseção sobre união de duas caixas `(x0, y0, x1, y1)`."""
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    area = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / area if area > 0 else 0.0


def itens_da_pagina(
    diagramas: Sequence[lp.DiagramaDoLivro], caixas: Sequence[Sequence[float] | None], pagina: int
) -> dict[int, lp.DiagramaDoLivro]:
    """`índice do diagrama reconhecido -> diagrama do livro`, pela caixa no PDF.

    O detector da janela e as imagens do PDF não numeram igual -- o detector pode achar um a mais
    (um tabuleiro desenhado em vetor) ou a menos. O que eles têm em comum é **onde** o tabuleiro
    está, e a caixa da imagem cobre a do detector quase inteira: metade de sobreposição já separa
    dois diagramas da mesma página com folga.
    """
    saida: dict[int, lp.DiagramaDoLivro] = {}
    da_pagina = [d for d in diagramas if d.pagina == pagina and d.caixa is not None]
    for k, caixa in enumerate(caixas):
        if caixa is None:
            continue
        melhor = max(da_pagina, key=lambda d: _sobreposicao(caixa, d.caixa or (0, 0, 0, 0)), default=None)
        if melhor is not None and melhor.caixa is not None and _sobreposicao(caixa, melhor.caixa) >= 0.5:
            saida[k] = melhor
    return saida


def _ler_o_livro(pgn: Path, pdf: Path | None) -> tuple[IndiceDoLivro, list[lp.DiagramaDoLivro]]:
    """O índice do PGN e o livro inteiro casado com ele pelas legendas, sem o modelo. Em segundo plano."""
    indice = IndiceDoLivro.do_arquivo(pgn)
    if pdf is None:
        return indice, []
    import fitz

    with fitz.open(pdf) as documento:
        paginas = ((k + 1, documento[k].get_text("dict")) for k in range(documento.page_count))
        return indice, lp.casar_livro(paginas, indice, sumario=documento.get_toc())


def _quando_o_indice_chega(fraco: weakref.ref[LivroComPgn], pgn: Path, lido: object) -> None:
    dono = fraco()
    if dono is not None and isinstance(lido, tuple) and isinstance(lido[0], IndiceDoLivro):
        dono._indice_chegou(pgn, lido[0], lido[1])


def _quando_o_indice_falha(fraco: weakref.ref[LivroComPgn], pgn: Path, mensagem: str, *_args: object) -> None:
    dono = fraco()
    if dono is not None:
        dono._indice_falhou(pgn, mensagem)


class LivroComPgn(QObject):
    """O PGN associado ao livro aberto, e o que ele faz com cada página lida."""

    def __init__(
        self,
        pai: QWidget,
        *,
        dizer: Callable[[str], Any],
        pdf_atual: Callable[[], Path | None],
        itens_atuais: Callable[[], Sequence[Any]],
        painel: Any,
        revisao: Any,
        texto: Any,
        estudo: Any,
        galeria: Any,
        focar: Callable[[QWidget], Any],
        ir_para_pagina: Callable[[int], Any],
    ) -> None:
        super().__init__(pai)
        self._pai = pai
        self._dizer = dizer
        self._pdf_atual = pdf_atual
        self._itens_atuais = itens_atuais
        self._painel = painel
        self._revisao = revisao
        self._texto = texto
        self._estudo = estudo
        self._galeria = galeria
        self._focar = focar
        self._ir_para_pagina = ir_para_pagina
        self._pdf: Path | None = None
        self._pgn: Path | None = None
        self.indice: IndiceDoLivro | None = None
        self.do_livro: list[lp.DiagramaDoLivro] = []
        """O livro inteiro casado pelas legendas, sem o modelo -- chega com o índice."""
        self._lendo: Path | None = None
        self._da_pagina: dict[int, lp.DiagramaDoLivro] = {}
        """Os diagramas do livro casados com os reconhecidos da página na tela, por índice."""
        self._esperando: tuple[int, list[Any]] | None = None
        """A página lida enquanto o PGN ainda era lido: o índice que chega é aplicado a ela, e não
        à página que a tela mostra -- a pessoa pode ter virado a folha nesse meio-tempo."""
        sinal = getattr(texto, "diagrama_sem_caixa_ativado", None)
        if sinal is not None:
            sinal.connect(self._estudar_o_inserido)

    # ------------------------------------------------------------------ o PGN do livro aberto

    @property
    def pgn(self) -> Path | None:
        return self._pgn

    def livro_aberto(self) -> None:
        """A janela abriu um livro: se ele tem PGN, a leitura começa já, antes da primeira página."""
        self._conferir_livro()

    def _conferir_livro(self) -> None:
        """Troca de livro sem avisar é o caso normal: a pergunta é feita a cada página lida."""
        pdf = self._pdf_atual()
        if pdf == self._pdf:
            return
        self._pdf, self._pgn, self.indice, self._lendo, self.do_livro = pdf, None, None, None, []
        pgn = lp.pgn_associado(pdf) if pdf is not None else None
        if pgn is not None:
            self._ler(pgn)

    def _ler(self, pgn: Path) -> None:
        self._pgn = pgn
        self._lendo = pgn
        pdf = self._pdf
        tarefa = manter_viva(Tarefa(lambda: _ler_o_livro(pgn, pdf), nome="PGN do livro"))
        fraco = weakref.ref(self)
        tarefa.pronto.connect(lambda indice, f=fraco, p=pgn: _quando_o_indice_chega(f, p, indice))
        tarefa.falhou.connect(lambda mensagem, *a, f=fraco, p=pgn: _quando_o_indice_falha(f, p, mensagem))
        tarefa.start()

    def _indice_chegou(self, pgn: Path, indice: IndiceDoLivro, do_livro: list[lp.DiagramaDoLivro]) -> None:
        if pgn != self._lendo:
            return  # outro livro foi aberto enquanto este PGN era lido
        self.indice, self.do_livro = indice, do_livro
        faltam = sum(1 for d in do_livro if d.estado == lp.FALTANDO)
        self._dizer(
            f"PGN do livro: {pgn.name}, {len(indice.partidas)} partidas e {len(indice.nos)} lances. "
            "Os diagramas lidos daqui em diante vêm dele"
            + (f"; {faltam} diagrama(s) do livro faltam no PDF." if faltam else ".")
        )
        esperando, self._esperando = self._esperando, None
        if esperando is None:
            return
        pagina, itens = esperando
        atuais = list(self._itens_atuais())
        if len(atuais) == len(itens) and all(a is b for a, b in zip(atuais, itens, strict=True)):
            self.aplicar(pagina, itens)

    def _indice_falhou(self, pgn: Path, mensagem: str) -> None:
        if pgn == self._lendo:
            self._lendo = None
        self._dizer(f"O PGN do livro não pôde ser lido ({pgn.name}): {mensagem}")

    def _pronto(self) -> bool:
        """Há PGN lido para o livro aberto; senão diz por quê."""
        self._conferir_livro()
        if self.indice is not None and self._pdf is not None:
            return True
        self._dizer(
            "O PGN do livro ainda está sendo lido; tente daqui a pouco."
            if self._lendo is not None
            else "Carregue o PGN do livro antes (Arquivo > Carregar PGN do livro…)."
        )
        return False

    def carregar(self) -> None:
        pdf = self._pdf_atual()
        if pdf is None:
            self._dizer("Abra o PDF do livro antes de carregar o PGN dele.")
            return
        nome, _filtro = QFileDialog.getOpenFileName(
            self._pai, "PGN do livro", str(Path(pdf).parent), "PGN (*.pgn);;Todos os arquivos (*)"
        )
        if not nome:
            return
        if not lp.associar(pdf, nome):
            self._dizer("O PDF aberto não pôde ser lido para guardar a associação.")
            return
        self._pdf = pdf
        self.indice, self.do_livro = None, []
        self._ler(Path(nome))

    def esquecer(self) -> None:
        pdf = self._pdf_atual()
        if pdf is None or not lp.esquecer(pdf):
            self._dizer("Este livro não tem PGN associado.")
            return
        self._pgn, self.indice, self._lendo, self._esperando, self.do_livro = None, None, None, None, []
        self._dizer("O PGN deste livro foi esquecido; as próximas páginas vêm só do reconhecimento.")

    # ------------------------------------------------------------------ a página lida

    def _casar_pagina(self, pagina: int, itens: Sequence[Any]) -> list[lp.DiagramaDoLivro]:
        """Os diagramas desta página (e o da legenda que abre a seguinte), com as leituras dos itens."""
        import fitz

        assert self.indice is not None and self._pdf is not None
        numero = pagina + 1
        caixas = [getattr(item, "bbox_pdf", None) for item in itens]
        leituras = {k: str(item.placement) for k, item in enumerate(itens)}

        def ler(diagrama: lp.DiagramaDoLivro) -> str:
            if diagrama.pagina != numero:
                return ""
            casados = itens_da_pagina([diagrama], caixas, numero)
            return next((leituras[k] for k in casados), "")

        with fitz.open(self._pdf) as documento:
            paginas = [(n, documento[n - 1].get_text("dict")) for n in (numero - 1, numero, numero + 1) if 1 <= n <= documento.page_count]
            return lp.casar_livro(paginas, self.indice, sumario=documento.get_toc(), ler=ler)

    def aplicar(self, pagina: int, itens: Sequence[Any]) -> None:
        """A FEN do livro em cada diagrama reconhecido da página. Ver o docstring do módulo."""
        self._conferir_livro()
        self._da_pagina = {}
        self._esperando = (pagina, list(itens)) if self.indice is None and self._lendo is not None and itens else None
        if self.indice is None or self._pdf is None or not itens:
            return
        try:
            diagramas = self._casar_pagina(pagina, itens)
        except Exception as exc:  # noqa: BLE001 - o livro de fora não pode custar a página lida
            logger.warning("O PGN do livro não casou a página %d: %s", pagina + 1, exc)
            return
        numero = pagina + 1
        casados = itens_da_pagina(diagramas, [getattr(i, "bbox_pdf", None) for i in itens], numero)
        self._da_pagina = casados
        adotados, discordam = 0, []
        posicoes = [str(item.placement) for item in itens]
        for k, diagrama in casados.items():
            nota = lp.nota_do_diagrama(diagrama, self.indice)
            if diagrama.estado in (lp.CONFERE, lp.CORRIGIDO, lp.SEM_LEITURA):
                campo, lado = diagrama.fen.split()[:2]
                if self._painel.adotar_do_livro(k, itens[k], campo, lado, nota):
                    adotados += 1
                    posicoes[k] = campo
            elif diagrama.estado == lp.DISCORDA:
                discordam.append((k, diagrama))
        if adotados:
            self._texto.definir_posicoes(pagina, posicoes)
        entraram = self._para_a_revisao(pagina, itens, discordam)
        faltam = [d for d in diagramas if d.estado == lp.FALTANDO and d.pagina == numero]
        partes = []
        if adotados:
            partes.append(f"{adotados} diagrama(s) com a posição do PGN do livro")
        if discordam:
            partes.append(f"{len(discordam)} discorda(m) do PGN ({entraram} novo(s) na Revisão)")
        if faltam:
            lances = ", ".join(d.legenda for d in faltam)
            partes.append(f"{len(faltam)} diagrama(s) desta página faltam no PDF ({lances})")
        if partes:
            self._dizer("; ".join(partes) + ".")

    def _para_a_revisao(self, pagina: int, itens: Sequence[Any], discordam: list[tuple[int, lp.DiagramaDoLivro]]) -> int:
        if not discordam or self._revisao is None or self._pdf is None:
            return 0
        from chess_diagram_ocr.review_queue import (
            DEFAULT_CACHE_DIR,
            WEIGHT_SOURCES_DISAGREE,
            ReviewItem,
            cache_board_image,
        )

        novos = []
        for k, diagrama in discordam:
            item = itens[k]
            imagem = cache_board_image(item.board_rgb, DEFAULT_CACHE_DIR, self._pdf.name, pagina, k + 1)
            novos.append(
                ReviewItem(
                    pdf_path=str(self._pdf),
                    page_index=pagina,
                    diagram_index=k + 1,
                    board_image=str(imagem),
                    fen=diagrama.fen,
                    side_to_move=diagrama.fen.split()[1],
                    min_confidence=float(item.min_confidence),
                    mean_entropy=0.0,
                    priority=WEIGHT_SOURCES_DISAGREE,
                    reasons=(f"o PGN do livro discorda da leitura em {len(diagrama.casas)} casas ({diagrama.legenda or 'sem legenda'})",),
                    uncertain_squares=tuple(diagrama.casas),
                )
            )
        return int(self._revisao.acrescentar(novos))

    # ------------------------------------------------------------------ o Estudo e os que faltam

    def estudar_na_arvore(self) -> None:
        """O diagrama selecionado no Resultado, aberto no Estudo com a árvore inteira do autor."""
        indice_do_item = int(self._painel.modelo.clamped_index()) if self._painel.modelo.items else -1
        diagrama = self._da_pagina.get(indice_do_item)
        if self.indice is None or diagrama is None or diagrama.no is None:
            self._dizer("O diagrama selecionado não tem nó no PGN do livro (carregue o PGN e leia a página).")
            return
        self._abrir_no_estudo(diagrama, numero_do_diagrama=indice_do_item + 1)

    def _abrir_no_estudo(self, diagrama: lp.DiagramaDoLivro, *, numero_do_diagrama: int = 0) -> None:
        assert self.indice is not None and diagrama.no is not None
        registro = self.indice.nos[diagrama.no]
        jogo = self.indice.partidas[registro.partida]
        copia = _copia_da_partida(jogo)
        copia.headers["SourcePDF"] = self._pdf.name if self._pdf else ""
        copia.headers["Page"] = str(diagrama.pagina)
        if numero_do_diagrama:
            copia.headers["Diagram"] = str(numero_do_diagrama)
        copia.headers["Caption"] = diagrama.legenda or registro.rotulo
        origem = " · ".join(x for x in (registro.capitulo, registro.secao, registro.rotulo) if x)
        if self._estudo.abrir_no_livro(copia, registro.caminho, origem=f"Livro: {origem}"):
            self._focar(self._estudo)

    def _estudar_o_inserido(self, pagina: int, placement: str) -> None:
        """O duplo clique num diagrama que o PGN pôs na folha do Texto: a árvore do autor (S-595)."""
        try:
            diagrama = next(
                (
                    d
                    for d in self.do_livro
                    if d.pagina == pagina + 1 and d.no is not None and d.fen.split()[0] == placement
                ),
                None,
            )
            if self.indice is None or diagrama is None:
                self._dizer("Este diagrama veio do PGN do livro, e o PGN deste livro não está carregado.")
                return
            self._abrir_no_estudo(diagrama)
        except Exception:  # noqa: BLE001 - exceção em slot do PyQt6 derruba o processo
            logger.exception("O diagrama do PGN do livro não abriu no Estudo")

    def mostrar_os_que_faltam(self) -> None:
        """A lista dos diagramas que o PDF perdeu, no livro inteiro, desenhados do PGN."""
        if not self._pronto():
            return
        faltam = [d for d in self.do_livro if d.estado == lp.FALTANDO]
        if not faltam:
            self._dizer("Nenhum diagrama falta neste PDF: toda legenda tem a sua imagem.")
            return
        _ListaDosQueFaltam(self, faltam).exec()

    def por_na_folha(self) -> None:
        """Os diagramas que faltam na folha da aba Texto, desenhados do PGN e postos antes da legenda (S-595)."""
        if not self._pronto():
            return
        pagina, _paginas = self._texto.folha_atual()
        faltam = [
            (d.legenda, d.fen.split()[0])
            for d in self.do_livro
            if d.estado == lp.FALTANDO and d.pagina == pagina + 1 and d.fen
        ]
        if not faltam:
            self._dizer(f"Nenhum diagrama da folha {pagina + 1} falta no PDF.")
            return
        if self._texto.inserir_diagramas_do_livro(pagina, faltam):
            self._focar(self._texto)
            return
        self._dizer(
            f"{len(faltam)} diagrama(s) da folha {pagina + 1} faltam no PDF, mas a folha lida na aba "
            "Texto não tem a legenda deles (ou já os mostra). Leia a folha e peça de novo."
        )

    # ------------------------------------------------------------------ a Galeria (S-594)

    def preencher_a_galeria(self) -> None:
        """Lance, lado a jogar e cabeçalhos da partida do autor em cada diagrama varrido que confere."""
        if not self._pronto():
            return
        modelo = self._galeria.model
        aberto = modelo.pdf_path
        if aberto is None or self._pdf is None or Path(aberto).resolve() != Path(self._pdf).resolve() or modelo.is_empty:
            self._dizer("A Galeria ainda não varreu este livro: varra-o antes (Galeria > Varrer o livro).")
            return
        assert self.indice is not None
        casamentos, discordam = lp.casamentos_da_galeria(modelo.index.entries, self.do_livro, self.indice)
        self._galeria.preencher_de_fora(casamentos, origem="PGN do livro", discordam=discordam)
        self._focar(self._galeria)


def _copia_da_partida(jogo: Any) -> Any:
    """A partida do livro reescrita e relida: o Estudo edita a árvore, e o índice não pode mudar."""
    import io

    import chess.pgn

    texto = str(jogo.accept(chess.pgn.StringExporter(headers=True, variations=True, comments=True)))
    return chess.pgn.read_game(io.StringIO(texto))


class _ListaDosQueFaltam(QDialog):
    """Página, legenda e o tabuleiro desenhado do PGN, com o que dá para fazer com cada um."""

    def __init__(self, dono: LivroComPgn, faltam: Sequence[lp.DiagramaDoLivro]) -> None:
        super().__init__(dono._pai)
        self._dono = dono
        self._faltam = list(faltam)
        self.setWindowTitle(f"Diagramas que faltam no PDF ({len(faltam)})")
        self.lista = QListWidget(self)
        assert dono.indice is not None
        for diagrama in self._faltam:
            registro = dono.indice.nos[diagrama.no] if diagrama.no is not None else None
            onde = f"{registro.capitulo} · {registro.secao}" if registro else ""
            QListWidgetItem(f"p. {diagrama.pagina} · {diagrama.legenda} · {onde}", self.lista)
        self.tabuleiro = QLabel(self)
        self.tabuleiro.setFixedSize(LADO_DA_MINIATURA, LADO_DA_MINIATURA)
        self.tabuleiro.setAccessibleName("O diagrama, desenhado do PGN do livro")
        self.lista.currentRowChanged.connect(self._mostrar)
        botoes = QHBoxLayout()
        for rotulo, acao in (
            ("Ir à página", self._ir),
            ("Estudar", self._estudar),
            ("Copiar FEN", self._copiar),
            ("Salvar imagem…", self._salvar),
        ):
            botao = QPushButton(rotulo, self)
            tema.aplicar_papel(botao, estilos.NEUTRO)
            botao.clicked.connect(acao)
            botoes.addWidget(botao)
        fechar = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        fechar.rejected.connect(self.reject)
        corpo = QHBoxLayout()
        corpo.addWidget(self.lista, 1)
        corpo.addWidget(self.tabuleiro, 0, Qt.AlignmentFlag.AlignTop)
        caixa = QVBoxLayout(self)
        caixa.addLayout(corpo)
        caixa.addLayout(botoes)
        caixa.addWidget(fechar)
        self.resize(720, 420)
        self.lista.setCurrentRow(0)

    def _atual(self) -> lp.DiagramaDoLivro | None:
        linha = self.lista.currentRow()
        return self._faltam[linha] if 0 <= linha < len(self._faltam) else None

    def _png(self, diagrama: lp.DiagramaDoLivro, lado: int) -> bytes:
        from chess_diagram_ocr.desenho_de_diagrama import png_do_diagrama

        return png_do_diagrama(diagrama.fen.split()[0], lado_px=lado)

    def _mostrar(self, _linha: int) -> None:
        diagrama = self._atual()
        if diagrama is None:
            return
        imagem = QPixmap()
        imagem.loadFromData(self._png(diagrama, LADO_DA_MINIATURA))
        self.tabuleiro.setPixmap(imagem)

    def _ir(self) -> None:
        diagrama = self._atual()
        if diagrama is not None:
            self._dono._ir_para_pagina((diagrama.pagina_da_legenda or diagrama.pagina) - 1)

    def _estudar(self) -> None:
        diagrama = self._atual()
        if diagrama is not None and diagrama.no is not None:
            self._dono._abrir_no_estudo(diagrama)
            self.accept()

    def _copiar(self) -> None:
        diagrama = self._atual()
        if diagrama is not None:
            area = QGuiApplication.clipboard()
            if area is not None:
                area.setText(diagrama.fen)
            self._dono._dizer(f"FEN do diagrama da p. {diagrama.pagina} copiada.")

    def _salvar(self) -> None:
        diagrama = self._atual()
        if diagrama is None or self._dono._pdf is None:
            return
        sugestao = Path(self._dono._pdf).with_name(f"{Path(self._dono._pdf).stem}_p{diagrama.pagina:04d}.png")
        nome, _ = QFileDialog.getSaveFileName(self, "Salvar o diagrama", str(sugestao), "PNG (*.png)")
        if nome:
            atomic_write_bytes(Path(nome), self._png(diagrama, 600))
            self._dono._dizer(f"Diagrama salvo em {nome}.")
