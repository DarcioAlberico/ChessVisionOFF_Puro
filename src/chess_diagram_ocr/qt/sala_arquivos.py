"""O estudo que entra e sai da sala: colar, abrir PGN, exportar, imprimir e levar ao texto (S-866).

**Saiu de `qt/painel_de_estudo.py`, e são funções e não uma classe, porque não há estado.** Cada uma
recebe o painel, escolhe um arquivo, converte o estudo -- ou converte o arquivo em estudo -- e diz o
que fez no rodapé. Quem decide o que cada formato faz é `text/exportacao.py`, `epub.py`,
`docx_saida.py` e `qt/impressao_do_estudo.py`; quem decide o que um `.pgn` vira é
`estudo_arquivo.estudos_de_pgn` e `estudo.colar`.

**Os comandos continuam sendo métodos do painel**, que delegam para cá: `COMANDOS_DA_ABA` é uma
tabela só, e o `getattr` dela é sobre o painel.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr import estudo as estudo_mod
from chess_diagram_ocr import estudo_arquivo
from chess_diagram_ocr.estudo import Estudo
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.vazio import EstadoVazio
from chess_diagram_ocr.ui import espaco, formato, strings, tipografia
from chess_diagram_ocr.ui.sala_declarada import PARTIDAS_MAXIMAS_DE_PGN, TAMANHO_MAXIMO_DE_PGN

if TYPE_CHECKING:
    from PyQt6.QtPrintSupport import QPrintPreviewDialog

    from chess_diagram_ocr.qt.lote_de_diagramas import DialogoDoLote
    from chess_diagram_ocr.qt.painel_de_estudo import PainelDeEstudo

logger = logging.getLogger(__name__)

__all__ = [
    "JanelaDeColar",
    "abrir_pgn",
    "colar_estudo",
    "exportar_diagramas_em_lote",
    "exportar_empacotado",
    "exportar_estudo_pdf",
    "exportar_texto_marcado",
    "imprimir_estudo",
    "levar_para_o_texto",
    "save_pgn",
    "write_pgn",
]

# ------------------------------------------------------------------- entrada (S-288)


def colar_estudo(sala: PainelDeEstudo) -> QDialog:
    """Abre a caixa de colar posição ou partida.

    **Uma caixa e não dois comandos**: quem tem uma FEN e quem tem um PGN faz o mesmo gesto --
    copia de algum lugar e cola aqui --, e obrigá-los a escolher o comando certo antes é
    perguntar o que o próprio texto responde. Quem responde é `estudo.colar`.
    """
    return JanelaDeColar(sala, lambda texto: _aceitar_colado(sala, texto))


def _aceitar_colado(sala: PainelDeEstudo, texto: str) -> None:
    """O que veio da caixa. **Não descarta nada antes de saber que deu certo.**"""
    novo, motivo = estudo_mod.colar(texto)
    if novo is None:
        sala.set_status(motivo)
        return
    if not sala._confirmar_abandono("abrir o que foi colado"):
        return
    sala.seguir_ocr.setChecked(False)
    sala.sala.guardar(sala.estudo)
    sala._trocar_de_estudo(novo, "Base: colado")
    sala.set_status(f"{novo.contagem_de_lances()} lance(s) colados.")


def abrir_pgn(sala: PainelDeEstudo) -> None:
    """Abre um `.pgn` do disco: um estudo, ou a coleção de um livro (S-288).

    **Três respostas para três arquivos**, e a diferença não é de tamanho: o `.pgn` que este
    programa gravou traz `SourcePDF`, `Page` e `Diagram`, e as partidas dele entram **na sala**;
    um `.pgn` de uma partida qualquer abre como estudo avulso; um de muitas partidas sem âncora
    abre uma lista para escolher.
    """
    nome, _filtro = QFileDialog.getOpenFileName(
        sala, "Abrir PGN", str(sala._pasta_inicial), "PGN (*.pgn);;Todos (*.*)"
    )
    if not nome:
        return
    caminho = Path(nome)
    try:
        tamanho = caminho.stat().st_size
    except OSError as erro:
        sala.set_status(f"Não foi possível ler {caminho.name}: {erro}")
        return
    if tamanho > TAMANHO_MAXIMO_DE_PGN:
        sala.set_status(
            f"{caminho.name} tem {formato.decimal(tamanho / 1_048_576, 0)} MB, e a sala abre até "
            f"{TAMANHO_MAXIMO_DE_PGN // 1_048_576} MB. Base de partidas desse tamanho se "
            f"consulta pela busca por posição, que não carrega o arquivo inteiro."
        )
        return
    try:
        with caminho.open(encoding="utf-8", errors="replace") as fluxo:
            achados = estudo_arquivo.estudos_de_pgn(
                fluxo,
                documento=sala.sala.documento,
                onde=caminho.name,
                limite=PARTIDAS_MAXIMAS_DE_PGN,
            )
    except OSError as erro:
        sala.set_status(f"Não foi possível ler {caminho.name}: {erro}")
        return
    _receber_do_pgn(sala, caminho, achados)


def _receber_do_pgn(sala: PainelDeEstudo, caminho: Path, achados: Sequence[Estudo]) -> None:
    if not achados:
        sala.set_status(f"{caminho.name} não tem nenhuma partida legível.")
        return
    if len(achados) >= PARTIDAS_MAXIMAS_DE_PGN:
        sala.set_status(
            f"{caminho.name}: lidas as primeiras {PARTIDAS_MAXIMAS_DE_PGN} partidas; "
            f"o arquivo tem mais."
        )
    # Os que têm âncora deste livro entram na sala; `guardar` recusa os demais sozinho.
    anexados = [e for e in achados if sala.sala.guardar(e)]
    if anexados:
        sala._trocar_de_estudo(anexados[0], f"Base: {caminho.name}")
        sala.set_status(f"{len(anexados)} estudo(s) de {caminho.name} entraram na sala deste livro.")
        sala._marcar_sujo()
        return
    if len(achados) == 1:
        if not sala._confirmar_abandono(f"abrir {caminho.name}"):
            return
        sala._trocar_de_estudo(achados[0], f"Base: {caminho.name}")
        sala.set_status(f"{achados[0].contagem_de_lances()} lance(s) de {caminho.name}.")
        return
    _JanelaDeColecao(sala, caminho.name, list(achados), lambda escolhido: _escolher_da_colecao(sala, escolhido))


def _escolher_da_colecao(sala: PainelDeEstudo, escolhido: Estudo) -> None:
    if not sala._confirmar_abandono("abrir a partida escolhida"):
        return
    sala._trocar_de_estudo(escolhido, "Base: PGN aberto")
    sala.set_status(f"{escolhido.contagem_de_lances()} lance(s) da partida escolhida.")


# -------------------------------------------------------------- saída (S-289)


def exportar_empacotado(sala: PainelDeEstudo, extensao: str, formato: str, exportador: Callable[..., Any]) -> None:
    """O caminho comum do EPUB e do DOCX: escolher o destino, gravar, dizer o que saiu.

    `.epub` **porque o leitor de livro repagina** (S-542): o diagrama vai em SVG e acompanha o corpo
    de letra que a pessoa escolher no leitor. `.docx` **porque o texto continua sendo escrito**
    (S-543): estilos de título nomeados, sumário e o diagrama como imagem numa moldura.

    **Os dois não passam por `text/exportacao.py`, e é a mesma razão do PDF**: aquele módulo
    entrega texto marcado, e estes três entregam um **pacote** -- um zip com manifesto,
    imagens e metadados. Quem monta o pacote são `epub.py` e `docx_saida.py`, que já contam o
    que escreveram; aqui só se escolhe o arquivo.

    **A falha vai para a barra de status e não para uma caixa**, como no PDF: a pessoa acabou
    de escolher o destino e clicou em gravar, então ela está olhando para esta tela, e a mesma
    linha que diria "3 capítulo(s)" diz por que não deu (S-164).
    """
    destino, _filtro = QFileDialog.getSaveFileName(
        sala,
        f"Exportar o estudo para {formato}",
        str(sala._pasta_inicial / f"{_nome_sugerido(sala)}{extensao}"),
        f"{formato} (*{extensao});;Todos (*.*)",
    )
    if not destino:
        return
    sala.gravar_comentario()
    caminho = Path(destino)
    try:
        relatorio = exportador(sala.estudo, caminho)
    except (OSError, ValueError) as erro:  # ValueError: o EPUB que não passa em `verificar` (S-877)
        sala.set_status(f"Não foi possível gravar {caminho.name}: {erro}")
        return
    sala.set_status(relatorio.resumo())


# ------------------------------------------------------- a folha e o lote (S-544/S-545)


def exportar_estudo_pdf(sala: PainelDeEstudo) -> None:
    """`.pdf` **porque a página é decidida aqui** (S-545).

    Os três formatos de texto marcado entregam o estudo como texto, e quem pagina é o programa que
    abrir o arquivo. O PDF sai já paginado como livro -- margem, cabeçalho, número de página,
    e a quebra que não separa o diagrama do lance que o pede --, e o diagrama vai em vetor.
    Por isso ele não passa por `text/exportacao.py`: aquele módulo não tem página.

    **A falha vai para a barra de status, e não para uma caixa** -- ao contrário dos três
    vizinhos. É a régua da S-164 e a catraca de `tests/test_ui_retorno_modal.py`: a pessoa
    acabou de escolher o destino e clicou em gravar, então ela está olhando para esta tela, e
    a mesma linha que diria "6 página(s) em …" diz por que não deu. Uma caixa a mais aqui
    seria interrupção para informar o que o rodapé informa sem parar ninguém.
    """
    from chess_diagram_ocr.qt import impressao_do_estudo as qt_impressao
    from chess_diagram_ocr.ui.impressao_do_estudo import frase_do_pdf

    destino, _filtro = QFileDialog.getSaveFileName(
        sala,
        "Exportar o estudo para PDF",
        str(sala._pasta_inicial / f"{_nome_sugerido(sala)}.pdf"),
        "PDF (*.pdf);;Todos (*.*)",
    )
    if not destino:
        return
    sala.gravar_comentario()
    caminho = Path(destino)
    try:
        paginas = qt_impressao.pdf_do_estudo(sala.estudo, caminho)
        tamanho = caminho.stat().st_size
    except OSError as erro:
        sala.set_status(f"Não foi possível gravar {caminho.name}: {erro}")
        return
    sala.set_status(frase_do_pdf(str(caminho), paginas, tamanho))


def imprimir_estudo(sala: PainelDeEstudo) -> QPrintPreviewDialog:
    """A pré-visualização paginada, e a impressora atrás dela (S-545).

    **Prévia e não impressão direta.** A quebra de página é a decisão que o programa toma por
    quem imprime, e ela tem de ser conferível antes de gastar folha -- é a mesma razão de a
    prévia do lote de diagramas existir. A caixa de escolher impressora vem da própria prévia.
    """
    from chess_diagram_ocr.qt import impressao_do_estudo as qt_impressao

    sala.gravar_comentario()
    return qt_impressao.abrir_previa_de_impressao(sala, sala.estudo)


def exportar_diagramas_em_lote(sala: PainelDeEstudo) -> DialogoDoLote | None:
    """Os diagramas desta sala como arquivos soltos, um por posição (S-544).

    **A origem é a sala quando ela tem estudos, e o estudo aberto quando não.** A sala *é* o
    conjunto de diagramas deste livro (S-270), e é ele que quem diagrama noutro programa quer
    -- quinhentos arquivos de uma vez, nomeados pela página. Um estudo avulso, colado ou
    digitado, não está em sala nenhuma, e aí o lote é ele.
    """
    from chess_diagram_ocr.qt.lote_de_diagramas import abrir_lote_de_diagramas
    from chess_diagram_ocr.ui.lote_de_diagramas import de_estudos, do_estudo

    sala.gravar_comentario()
    guardados = sala.sala.estudos()
    if guardados:
        itens = de_estudos(guardados, origem=Path(sala.sala.documento).stem)
        origem = f"{len(guardados)} estudo(s) da sala deste livro."
    else:
        itens = do_estudo(sala.estudo)
        origem = "O estudo aberto."
    if not itens:
        sala.set_status("Não há diagrama para exportar: o estudo não pede nenhum.")
        return None
    return abrir_lote_de_diagramas(
        sala, itens=itens, origem=origem, pasta=sala._pasta_inicial, busy=sala._busy
    )


def exportar_texto_marcado(sala: PainelDeEstudo, extensao: str) -> None:
    """O estudo naquele formato, com o recorte do diagrama ao lado (S-289).

    **Quem decide o que cada formato faz é `text/exportacao.py`**, e não este módulo: aquele
    módulo existe porque "quatro exportadores escritos separadamente dariam quatro respostas, e
    três estariam erradas em silêncio". Aqui só se converte o estudo em `DocumentoRico` e se
    escolhe o destino.
    """
    from chess_diagram_ocr import estudo_saida
    from chess_diagram_ocr.text import exportacao

    formato = exportacao.formato_de(extensao)
    destino, _filtro = QFileDialog.getSaveFileName(
        sala,
        f"Exportar o estudo para {formato.nome}",
        str(sala._pasta_inicial / f"{_nome_sugerido(sala)}{extensao}"),
        f"{formato.nome} (*{extensao});;Todos (*.*)",
    )
    if not destino:
        return

    sala.gravar_comentario()
    caminho = Path(destino)
    try:
        recortes = _gravar_recorte(sala, caminho)
        relatorio = exportacao.exportar(
            estudo_saida.para_documento(sala.estudo), formato, recortes=recortes
        )
        exportacao.escrever(caminho, relatorio)
    except OSError as erro:
        QMessageBox.critical(sala, "Exportar o estudo", f"Falha ao exportar o estudo:\n{erro}")
        return
    sala.set_status(exportacao.texto_do_relatorio(caminho, relatorio, tamanho=caminho.stat().st_size))


def _nome_sugerido(sala: PainelDeEstudo) -> str:
    """`Secrets_p143_d2`, ou `estudo`. É o nome do arquivo que o diálogo oferece."""
    ancora = sala.estudo.ancora
    if not ancora.valida:
        return "estudo"
    livro = Path(ancora.nome_do_livro).stem[:40] or "estudo"
    return f"{livro}_p{ancora.pagina + 1}_d{ancora.diagrama + 1}"


def _gravar_recorte(sala: PainelDeEstudo, destino: Path) -> dict[int, Path]:
    """Grava o recorte do diagrama ao lado do arquivo, e devolve o mapa que `exportar` quer.

    `diagramas/` ao lado do destino, porque é a pasta que os formatos escrevem no caminho da
    imagem. Sem recorte devolve `{}`, e aí a marca `[Diagrama 1]` sai sozinha.
    """
    from chess_diagram_ocr import estudo_saida

    imagem = sala._recorte(sala.estudo.ancora) if sala.estudo.ancora.valida else None
    if imagem is None:
        return {}
    pasta = destino.parent / "diagramas"
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{destino.stem}.png"
    try:
        from PIL import Image

        from chess_diagram_ocr.atomic_io import atomic_write_pil

        atomic_write_pil(arquivo, Image.fromarray(imagem).convert("RGB"), formato="PNG")
    except Exception as erro:  # noqa: BLE001 - recorte de origem desconhecida
        logger.debug("Recorte não pôde ser gravado (%s): %s", arquivo, erro)
        return {}
    return {estudo_saida.BLOCO_DO_DIAGRAMA: arquivo}


def levar_para_o_texto(sala: PainelDeEstudo) -> None:
    """Manda a linha do estudo para a aba de texto, no cursor (S-289).

    **É o inverso exato da S-283.** Lá o parágrafo do livro vira variante; aqui a variante vira
    parágrafo -- e as duas pontas passam pelo mesmo `estudo_lista`, que é o que garante que a
    numeração seja a mesma nos dois sentidos.
    """
    from chess_diagram_ocr import estudo_saida

    linha = estudo_saida.notacao_do_estudo(sala.estudo)
    if not linha:
        sala.set_status("Não há lance no estudo para levar ao texto.")
        return
    if not sala._para_o_texto(linha):
        sala.set_status("A aba Texto não está pronta para receber a linha.")
        return
    sala.set_status("Linha do estudo inserida na aba Texto.")


# --------------------------------------------------------------------------------- PGN


def write_pgn(sala: PainelDeEstudo, path: Path, append: bool) -> None:
    """Grava o estudo em PGN. **Sobrescrever é atômico** (S-346).

    O caminho de sobrescrita com `write_text` trunca antes de escrever: interrompido no meio,
    ele deixa zero byte no lugar do PGN que estava lá -- e o que estava lá é análise salva de
    outro dia.

    **Acrescentar continua sendo um `append`**, e a diferença é o modo de falha: ele nunca
    trunca, então uma interrupção deixa o arquivo anterior inteiro com um jogo pela metade no
    fim -- ruim de ler, e nada perdido.
    """
    from chess_diagram_ocr.atomic_io import atomic_write_text

    conteudo = sala.pgn_payload()
    if append and path.exists() and path.stat().st_size > 0:
        with path.open("a", encoding="utf-8") as arquivo:
            arquivo.write("\n\n")
            arquivo.write(conteudo)
            arquivo.write("\n")
        return
    atomic_write_text(path, conteudo + "\n")

def save_pgn(sala: PainelDeEstudo) -> None:
    sala.gravar_comentario()
    nome, _filtro = QFileDialog.getSaveFileName(
        sala, "Salvar estudo em PGN", str(sala._pasta_inicial), "PGN (*.pgn);;Todos (*.*)"
    )
    if not nome:
        return

    caminho = Path(nome)
    append = False
    if caminho.exists():
        # Três respostas, não duas: acrescentar é o caso comum (um arquivo por livro), e
        # oferecer só "sobrescrever ou cancelar" faria perder análise já salva.
        caixa = QMessageBox(sala)
        caixa.setWindowTitle("PGN existente")
        caixa.setText("O arquivo já existe.")
        acrescentar = caixa.addButton("Acrescentar ao final", QMessageBox.ButtonRole.AcceptRole)
        sobrescrever = caixa.addButton("Sobrescrever", QMessageBox.ButtonRole.DestructiveRole)
        caixa.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        caixa.exec()
        escolhido = caixa.clickedButton()
        if escolhido not in (acrescentar, sobrescrever):
            return
        append = escolhido is acrescentar

    try:
        write_pgn(sala, caminho, append=append)
    except OSError as exc:
        QMessageBox.critical(sala, "Salvar PGN", f"Falha ao salvar PGN:\n{exc}")
        return
    sala.set_status(
        f"Análise acrescentada em {caminho.name}." if append else f"PGN salvo em {caminho.name}."
    )


class JanelaDeColar(QDialog):
    """A caixa de colar posição ou partida (S-288).

    Um campo só para as duas, porque o gesto é o mesmo -- copia de algum lugar e cola aqui -- e o
    próprio texto diz o que é. Quem responde é `estudo.colar`.
    """

    def __init__(self, pai: QWidget, aceitar: Callable[[str], None]) -> None:
        super().__init__(pai)
        self.setWindowTitle("Colar posição ou partida")
        self.resize(520, 320)
        self._aceitar = aceitar
        pilha = QVBoxLayout(self)
        pilha.setContentsMargins(*(espaco.moldura(),) * 4)
        pilha.addWidget(QLabel("Cole aqui uma FEN ou um PGN. O texto diz qual dos dois é.", self))
        self.campo = QTextEdit(self)
        self.campo.setFont(tema.fonte_atual(tipografia.DADO))
        # **Nome próprio, e não a frase de cima** (F9-C12). Sem ele a varredura de
        # `qt/acessibilidade` acha o rótulo vizinho e o campo passa a anunciar a instrução
        # inteira -- "Cole aqui uma FEN ou um PGN. O texto diz qual dos dois é.", que é uma
        # ajuda e não um nome. O rótulo continua na tela e continua sendo lido como texto.
        self.campo.setAccessibleName("Posição ou partida colada")
        # O `Tab` sai do campo, para o «Colar»: uma FEN ou um PGN colados não pedem tabulação, e
        # guardado pelo campo ele a escrevia e prendia a tecla ali (o portão `teclado` da suíte
        # com a tecla de verdade, OCR_UI ciclo 2, fase 5, crítico do ciclo 4).
        self.campo.setTabChangesFocus(True)
        pilha.addWidget(self.campo, 1)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, parent=self)
        # **O botão diz o verbo, e por isso é feito à mão** (F9-C12). Um `Ok` padrão chega ao
        # leitor de tela como "OK" -- duas letras, da mesma família do `-` e do `+` que o ciclo 1
        # mediu --, e diz menos do que o botão faz. Feito com `addButton`, ele também escapa da
        # tabela de `ui/strings.BOTOES_PADRAO`, que é o contrato de sempre: o explícito vence o
        # derivado. O texto é o mesmo na tela e no anúncio, que é o que a WCAG 2.5.3 pede.
        botoes.addButton("Colar", QDialogButtonBox.ButtonRole.AcceptRole)
        botoes.accepted.connect(self._confirmar)
        botoes.rejected.connect(self.reject)
        pilha.addWidget(botoes)
        self.show()

    def _confirmar(self) -> None:
        texto = self.campo.toPlainText()
        self.accept()
        self._aceitar(texto)


class _JanelaDeColecao(QDialog):
    """A lista de partidas de um `.pgn` de muitas, para escolher uma (S-288)."""

    def __init__(self, pai: QWidget, nome: str, achados: list[Estudo], escolher: Callable[[Estudo], None]) -> None:
        from PyQt6.QtWidgets import QListWidget

        super().__init__(pai)
        self.setWindowTitle(nome)
        self.resize(560, 420)
        self._achados = achados
        self._escolher = escolher
        pilha = QVBoxLayout(self)
        pilha.setContentsMargins(*(espaco.moldura(),) * 4)
        # **A frase deixou de se contradizer** (F9-C14): ela dizia `"0 partida(s) em x.pgn.
        # Escolha uma:"` sobre uma lista vazia, e a segunda oração pede o que a primeira acabou
        # de dizer que não existe. Sem partida, quem fala é o estado vazio.
        pilha.addWidget(
            QLabel(
                f"{len(achados)} partida(s) em {nome}. Escolha uma:"
                if achados
                else f"{nome}",
                self,
            )
        )
        self.lista = QListWidget(self)
        # Ver `JanelaDeColar.campo`: sem nome próprio a lista herda a frase do rótulo acima.
        self.lista.setAccessibleName("Partidas do arquivo")
        for estudo in achados:
            self.lista.addItem(estudo.ancora.rotulo() or f"{estudo.contagem_de_lances()} lance(s)")
        self.lista.itemDoubleClicked.connect(lambda *_: self._confirmar())
        pilha.addWidget(self.lista, 1)
        self.vazio = EstadoVazio(
            self.lista,
            titulo=strings.COLECAO_VAZIA_TITULO,
            frase=strings.COLECAO_VAZIA_FRASE,
            rotulo_do_botao="Escolher outro arquivo",
            nome_acessivel="Escolher outro arquivo PGN",
            acao=self.reject,
        )
        self.vazio.setVisible(not achados)
        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel, parent=self
        )
        botoes.accepted.connect(self._confirmar)
        botoes.rejected.connect(self.reject)
        pilha.addWidget(botoes)
        self.show()

    def _confirmar(self) -> None:
        linha = self.lista.currentRow()
        if not 0 <= linha < len(self._achados):
            return
        escolhido = self._achados[linha]
        self.accept()
        self._escolher(escolhido)
