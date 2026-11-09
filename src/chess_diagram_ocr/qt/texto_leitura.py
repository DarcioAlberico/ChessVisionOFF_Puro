"""O que a aba de texto faz fora da thread da janela: ler a folha, exportar, e a volta da Revisão (S-865).

**Saiu de `qt/painel_de_texto.py` com o estado das tarefas** -- a que está em curso, o registro de
ocupação, o motor, a língua e o modo bloco com que a próxima leitura parte, e o documento que
estava na tela quando ela partiu. Toda `Tarefa` da aba nasce aqui, sem pai e segura por
`manter_viva`, e responde por `slot_se_vivo`: a tarefa sobrevive ao painel que a pediu, e a resposta
não pode tocar um widget apagado. As que registram ocupação o fazem pelo `_registrar_ocupado`
**deste** módulo, que é onde `tests/test_busy.py` procura a prova de registro de cada thread.

**O diagrama é recorte da folha, e a folha vem da leitura.** `ler_pagina` rasteriza a página para
ler o texto, e a miniatura de cada `[Diagrama N]` é o pedaço dessa mesma imagem no `bbox` do bloco
-- em pontos, convertidos pelo mesmo DPI dos dois lados (`texto_miniaturas.recorte_da_folha`). O
porte inicial descartava a imagem na volta da thread, e a aba mostrava a marca sem figura nenhuma;
agora a folha é rasterizada **uma vez**, na thread de trabalho (S-352), entregue a `ler_pagina` por
`imagem_rgb` e guardada para as miniaturas, para os recortes da exportação (`gravar_recortes`,
S-338) e para o `.cvtxt` reaberto, que a refaz do livro se ele ainda estiver onde estava.

**A guarda da chegada é o livro, e não a página** (S-824): a folha lida entra mesmo que o
visualizador tenha virado a página no meio, porque a folha e o livro são os do resultado. Por isso
a leitura não leva a `AncoraDaTela` da janela, que compara também a página.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias, cast

import numpy as np
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QMessageBox, QSpinBox

from chess_diagram_ocr.qt import texto_miniaturas
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.trabalho import Tarefa, manter_viva, rastro_de, slot_se_vivo
from chess_diagram_ocr.text import caderno, correcao, rico
from chess_diagram_ocr.text.documento import PaginaLida
from chess_diagram_ocr.text.pagina import BlocoDeDiagrama
from chess_diagram_ocr.text.tesseract import LINGUA_PADRAO
from chess_diagram_ocr.ui import comandos, formato, strings
from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken
from chess_diagram_ocr.ui.livros import chave_do_livro
from chess_diagram_ocr.ui.texto_declarado import MOTORES, alinhamento_dos_diagramas

if TYPE_CHECKING:
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto

logger = logging.getLogger(__name__)

__all__ = ["CANCELADA", "TETO_DE_FOLHAS", "ExecutorDaAba", "gravar_recortes", "ler_a_folha", "no_livro", "renderizar"]

CANCELADA = "exportação cancelada pela pessoa"
"""O que a tarefa de exportação devolve quando a pessoa desistiu (F9-C2, §7 item 7).

Um valor de retorno e não uma exceção: desistir não é falhar, e uma exceção cairia em
`_exportacao_falhou`, que abre caixa vermelha."""

TETO_DE_FOLHAS = 9999
"""O teto do campo «Folha a ler» enquanto a aba não sabe quantas folhas o livro tem (item 15)."""

Importacao: TypeAlias = Callable[[], Any]
"""Quem devolve a importação do livro pela suíte (a janela), que a volta do R7 reaproveita quando serve."""

LADO_DO_RECORTE_DESENHADO = 400
"""O lado, em pixel, do diagrama desenhado da FEN para a exportação: perto do que um recorte a
220 dpi mede, para o `.html` não trocar de escala conforme a origem da figura."""


def renderizar(caminho: Path, indice: int, *, dpi: int) -> np.ndarray | None:
    """A folha renderizada, de onde saem as miniaturas. `None` quando ela não pôde ser aberta.

    Função do módulo, e não método, por dois motivos: ela roda na thread de trabalho, onde nada
    do widget pode ser tocado; e o teste a troca por uma folha sintética sem abrir PDF nenhum.
    """
    try:
        from chess_diagram_ocr.pdf_io import render_pdf_page

        return render_pdf_page(caminho, indice, dpi=dpi)
    except Exception as erro:  # noqa: BLE001 - miniatura é conforto, não função
        logger.debug("Sem imagem da folha %d para as miniaturas: %s", indice + 1, erro)
        return None


def ler_a_folha(
    caminho: Path,
    indice: int,
    *,
    dpi: int,
    motor: str,
    modo_bloco: bool,
    imagem_rgb: np.ndarray | None,
    max_boards: int | None = None,
    lingua: str = LINGUA_PADRAO,
) -> PaginaLida:
    """`ler_pagina` com a folha já renderizada. **O `import` do leitor mora aqui** -- ver `ler`."""
    from chess_diagram_ocr.text.leitor import ler_pagina

    return ler_pagina(
        caminho, indice, dpi=dpi, motor=motor, modo_bloco=modo_bloco, imagem_rgb=imagem_rgb, max_boards=max_boards, lingua=lingua,  # type: ignore[arg-type]
        reserva=True,  # só aqui: a régua e os CLIs não dependem de haver Tesseract na máquina
    )


def gravar_recortes(
    doc: rico.DocumentoRico, destino: Path, folha: np.ndarray | None, *, dpi: int
) -> dict[int, Path]:
    """Um PNG por diagrama da folha, ao lado do arquivo, e o mapa que `exportar` quer (S-338).

    `diagramas/` ao lado do destino porque é a pasta que os formatos escrevem no caminho da imagem
    (`Markdown.pasta_de_imagens`). Sem folha renderizada -- documento aberto de arquivo, sem o
    livro na tela -- devolve `{}`, e a marca sai sozinha, como o relatório conta.

    **Roda na thread de trabalho, e por isso nada de Qt aqui**: o recorte é numpy e o PNG é da
    Pillow. O `import` fica fora do laço: ele é o mais caro desta função na primeira vez.
    """
    blocos = [(corrida.bloco, doc.bloco_de(corrida)) for corrida in doc.corridas if corrida.e_diagrama]
    if not blocos:
        return {}
    from PIL import Image

    pasta = destino.parent / "diagramas"
    recortes: dict[int, Path] = {}
    for chave, bloco in blocos:
        if not isinstance(bloco, BlocoDeDiagrama):
            continue
        imagem = texto_miniaturas.recorte_da_folha(folha, bloco, dpi=dpi) if folha is not None else None
        # Sem folha, o desenho da posição lida (item 7) -- a mesma reserva da miniatura na tela.
        desenho = texto_miniaturas.png_da_posicao(bloco.placement, lado_px=LADO_DO_RECORTE_DESENHADO) if imagem is None else None
        if imagem is None and desenho is None:
            continue
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            arquivo_png = pasta / f"{destino.stem}_d{bloco.indice + 1}.png"
            # Atômica, como toda gravação do projeto (`tests/test_atomic_writes.py`).
            from chess_diagram_ocr.atomic_io import atomic_write_bytes, atomic_write_pil

            if imagem is not None:
                atomic_write_pil(arquivo_png, Image.fromarray(np.ascontiguousarray(imagem)).convert("RGB"), formato="PNG")
            else:
                atomic_write_bytes(arquivo_png, desenho or b"")
        except Exception as erro:  # noqa: BLE001 - recorte é conforto, e a marca sai sem ele
            logger.debug("Recorte do diagrama %d não gravado: %s", bloco.indice + 1, erro)
            continue
        recortes[chave] = arquivo_png
    return recortes


def no_livro(doc: rico.DocumentoRico, livro: Path | None) -> rico.DocumentoRico:
    """O documento apontando para o livro onde ele está agora.

    O caderno acha o livro pelo conteúdo (S-610), e a folha guardada pode ter sido lida quando o
    PDF morava noutra pasta: com a origem velha, as miniaturas procurariam o livro no lugar de
    antes, e a folha deixaria de parecer do livro aberto.
    """
    origem = doc.origem
    if origem is None or livro is None or origem.documento == str(livro):
        return doc
    return replace(doc, origem=replace(origem, documento=str(livro)))


class ExecutorDaAba(QObject):
    """As tarefas da aba de texto: a leitura da folha, as exportações, a volta da Revisão e a folha ao fundo."""

    def __init__(self, aba: PainelDeTexto, *, busy: BusyRegistry | None, dpi_fixo: int | None) -> None:
        super().__init__(aba)
        self._aba = aba
        self._busy = busy
        """O registro de ocupação (S-112). `None` é a aba montada sozinha num teste.

        **As duas operações longas desta aba precisam estar nele**, e no corte do Tk elas quase
        não ficaram: o painel de lá registrava as duas, e o porte inicial não. Ler uma folha é
        dezenas de segundos com o motor glifo, e exportar um PDF pesquisável abre o livro inteiro
        -- fechar a janela no meio de qualquer uma delas joga fora trabalho que não volta de
        graça, e o rodapé só sabe perguntar sobre o que está registrado."""
        self._ocupado: BusyToken | None = None
        self._dpi_fixo = dpi_fixo
        """O DPI cravado por quem montou o painel -- o teste, que dá a folha sintética. `None` é o
        produto: a leitura pergunta às Configurações (`ui/configuracoes.dpi`), como o visualizador
        e a leitura dos diagramas fazem, em vez de um 220 cravado que ignorava a janela
        «Ferramentas ▸ Configurações…»."""
        self.tarefa: Tarefa | None = None
        """A leitura ou a exportação em curso. Uma por vez nesta aba."""
        self._motor = MOTORES[0]
        self._lingua = LINGUA_PADRAO
        """O motor de leitura. O primeiro da lista é o padrão, e a S-423 explica por que ele é o
        `auto` e não o `glifo`."""
        self._modo_bloco = False
        self._leitura_de: tuple[str, bool] = ("", False)
        """O motor e o modo bloco da leitura em curso, como eram quando ela partiu."""
        self._folha_pedida_ao_fundo: int | None = None
        self.fornecedor_de_folha: Callable[[int], tuple[np.ndarray, int] | None] | None = None
        """Quem já tem a folha rasterizada -- o visualizador --, perguntado antes de rasterizar
        de novo (item 28). `None` é a aba sozinha, que renderiza por conta própria."""
        self._importacao: Importacao | None = None
        """Quem tem a importação do livro pela suíte (a janela), para a volta do R7. `None` é a aba sozinha."""
        self._documento_ao_ler: rico.DocumentoRico | None = None
        """O documento na tela quando a leitura em curso partiu. Ver `_leitura_terminou`."""

    def montar(self) -> None:
        """A folha, o motor, a língua e o modo bloco: os controles da leitura que a fita põe no grupo dela."""
        barra = self._aba
        # **A folha, o motor e o modo bloco ficam na mesma barra que o "Ler".** É a linha do gesto:
        # escolher a folha, escolher como lê-la, e ler -- e separá-la em duas faria a escolha do
        # motor parecer configuração, que é o que a S-423 mostrou custar a primeira leitura de quem
        # instala o programa.
        self.campo_de_folha = QSpinBox(barra)
        # O nome diz o que o número é, e não qual número é -- ver `nomes_acessiveis.CLASSES_COM_VALOR`.
        self.campo_de_folha.setAccessibleName("Folha a ler")
        self.campo_de_folha.setMinimum(1)
        self.campo_de_folha.setMaximum(TETO_DE_FOLHAS)  # até a janela dizer quantas folhas o livro tem
        # Enter no campo lê a folha digitada (item 27): digitar o número e ter de ir ao botão com
        # o mouse era o atrito de quem lê folha a folha. `returnPressed` e não `editingFinished`:
        # este também dispara ao sair do campo com o Tab, e ler por perder o foco seria surpresa.
        linha = self.campo_de_folha.lineEdit()
        if linha is not None:
            linha.returnPressed.connect(self.ler)
        self.campo_de_folha.setValue(self._aba._pagina_indice + 1)

        self.escolha_de_motor = QComboBox(barra)
        self.escolha_de_motor.setAccessibleName("Motor de leitura")
        for motor in MOTORES:
            self.escolha_de_motor.addItem(strings.ROTULOS_DE_MOTOR[motor], motor)
        self.escolha_de_motor.activated.connect(
            lambda _i: setattr(self, "_motor", str(self.escolha_de_motor.currentData()))
        )
        dica_em(
            self.escolha_de_motor,
            "auto é o glifo com a camada do PDF como reserva. O glifo sozinho precisa de "
            "models/char_classifier.pt, que não vem no repositório. «Camada na prosa» lê a prosa do "
            "próprio PDF nos livros nascidos digitais; «Glifo + Tesseract» precisa do Tesseract "
            "instalado. Nos dois, os lances continuam do glifo.",
        )

        self.escolha_de_lingua = QComboBox(barra)
        self.escolha_de_lingua.setAccessibleName("Língua do livro")
        for lingua, rotulo in strings.ROTULOS_DE_LINGUA.items():
            self.escolha_de_lingua.addItem(rotulo, lingua)
        self.escolha_de_lingua.activated.connect(self._lingua_escolhida)
        dica_em(self.escolha_de_lingua, "A língua em que o Tesseract lê a prosa, no motor «Glifo + Tesseract» e na reserva.")

        self.caixa_de_bloco = QCheckBox(comandos.rotulo_de_botao("modo_bloco"), barra)
        self.caixa_de_bloco.toggled.connect(lambda _ligado: self.modo_bloco_mudou())

    # ------------------------------------------- a folha do caderno, rasterizada ao fundo (S-612)

    def renderizar_ao_fundo(self, indice: int) -> None:
        """A folha aberta do caderno, rasterizada **fora** da thread da janela (S-612).

        O texto entra na hora; as miniaturas chegam quando a folha chegar. Renderizar aqui, como o
        `abrir` de um `.cvtxt` faz, congelava a troca de folha por um a três décimos de segundo a
        cada «Abrir folha» -- o gesto que a aba mais repete. A resposta que chegar para uma folha
        que já saiu da tela é jogada fora.
        """
        livro = self._aba.caderno.livro_do_caderno
        if livro is None or not livro.exists():
            return
        dpi = self.dpi_para_ler()
        self._folha_pedida_ao_fundo = indice
        tarefa = manter_viva(Tarefa(lambda: (indice, dpi, renderizar(livro, indice, dpi=dpi)), nome="folha do caderno"))
        tarefa.pronto.connect(slot_se_vivo(self._aba, self._folha_chegou))
        tarefa.start()

    def _folha_chegou(self, resultado: object) -> None:
        """A folha rasterizada ao fundo: as miniaturas entram, sem mexer no texto, na seleção nem na pilha."""
        indice, dpi, imagem = cast("tuple[int, int, np.ndarray | None]", resultado)
        if imagem is None or indice != self._folha_pedida_ao_fundo:
            return
        if self._aba._pagina is None or int(self._aba._pagina.pagina) != indice or self._aba.caderno.caderno_da_tela() is None:
            return
        self._aba._pagina_rgb = imagem
        self._aba._dpi = int(dpi)
        if self._aba.documento.diagramas:
            self._aba.vista.redesenhar()
            return
        self._aba.vista.atualizar_status()
        self._aba.caderno.mostrar_impresso()

    def _confirmar_releitura(self, indice: int, correcoes: int) -> bool:
        from chess_diagram_ocr.qt import dialogos

        if not dialogos.ha_quem_responda():
            logger.warning("Ler de novo a folha %d com correções pede resposta, e não há tela: fica como está.", indice + 1)
            return False
        resposta = QMessageBox.question(
            self._aba,
            "Texto",
            caderno.frase_de_releitura(indice, correcoes),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return resposta == QMessageBox.StandardButton.Yes

    def ler_de_novo(self) -> None:
        """O motor lê de novo a folha da tela, mesmo com caderno -- e pergunta se há correção a perder."""
        if self._aba._pagina is not None:
            self.campo_de_folha.setValue(int(self._aba._pagina.pagina) + 1)
        self._ler_folha(de_novo=True)

    # ------------------------------------------------------------ a exportação do caderno (S-614)

    def exportar_caderno(self) -> None:
        """O caderno inteiro num `.md`, `.html` ou `.rtf`, folha a folha (S-614), fora da thread da janela.

        As folhas sem caderno são puladas e o relatório as lista. As miniaturas saem de cada folha
        renderizada de novo -- é a parte longa, e por isso a exportação é cancelável entre duas
        folhas, como a de uma folha é antes da escrita.
        """
        from chess_diagram_ocr.text import exportacao

        cad = self._aba.caderno.aberto
        if cad is None or self._aba.caderno.livro_do_caderno is None:
            self._aba.estado.emit("Abra um livro e leia uma folha: o caderno é do livro aberto.")
            return
        if self.tarefa is not None:
            self._aba.estado.emit("Já há uma leitura ou exportação em curso nesta aba.")
            return
        self._aba.caderno.guardar_a_folha()  # a folha da tela entra como está
        estados = cad.folhas()
        if not estados:
            self._aba.estado.emit("O caderno deste livro ainda não tem folha nenhuma.")
            return
        livro = self._aba.caderno.livro_do_caderno
        destino, filtro = QFileDialog.getSaveFileName(
            self._aba,
            "Exportar o caderno do livro",
            f"{livro.stem}_caderno.md",
            "Markdown (*.md);;HTML (*.html);;RTF (*.rtf);;PDF pesquisável (*.pdf)",
        )
        if not destino:
            return
        caminho = Path(destino)
        extensao = caminho.suffix.lower()
        if extensao not in (".md", ".html", ".rtf", ".pdf"):
            extensao = {"HTML": ".html", "RTF": ".rtf", "PDF": ".pdf"}.get(filtro.split(" ", 1)[0], ".md")
            caminho = caminho.with_suffix(extensao)
        if extensao == ".pdf":
            self._exportar_caderno_pesquisavel(cad, livro, caminho)
            return
        formato = exportacao.formato_de(extensao)
        documentos = [d for d in (cad.folha(e.pagina) for e in estados) if d is not None]
        documentos = [no_livro(d, livro) for d in documentos]
        presentes = {int(d.origem.pagina) for d in documentos if d.origem is not None}
        faltam = [p for p in range(self._aba.vista.quantas_folhas()) if p not in presentes]
        com_imagens = bool(getattr(formato, "pasta_de_imagens", "")) and livro.exists()
        dpi = self.dpi_para_ler()
        diagramas, ao_lado = alinhamento_dos_diagramas(self._aba.miniaturas.diagramas), self._aba.miniaturas.texto_ao_lado
        desistir = threading.Event()

        def _trabalho() -> str:
            recortes: dict[int, dict[int, Path]] = {}
            for doc in documentos if com_imagens else ():
                if desistir.is_set():
                    return CANCELADA
                if not doc.diagramas or doc.origem is None:
                    continue
                pagina = int(doc.origem.pagina)
                folha = renderizar(livro, pagina, dpi=dpi)
                nome = caminho.with_name(f"{caminho.stem}_f{pagina + 1:04d}{caminho.suffix}")
                recortes[pagina] = gravar_recortes(doc, nome, folha, dpi=dpi)
            relatorio = exportacao.exportar_folhas(
                documentos,
                formato,
                titulo=f"{livro.name} — caderno",
                recortes=recortes,
                faltam=faltam,
                diagramas=diagramas,
                ao_lado=ao_lado,
            )
            if desistir.is_set():
                return CANCELADA
            exportacao.escrever(caminho, relatorio)
            return exportacao.texto_do_relatorio(caminho, relatorio, tamanho=caminho.stat().st_size)

        self._aba.estado.emit(f"Exportando o caderno ({len(documentos)} folha(s)) para {caminho.name}…")
        self._registrar_ocupado(
            f"Exportando o caderno para {formato.nome}",
            loses_work=True,
            detail=caminho.name,
            cancelar=desistir.set,
        )
        self.tarefa = manter_viva(Tarefa(_trabalho, nome="exportação do caderno"))
        self.tarefa.pronto.connect(slot_se_vivo(self._aba, self._exportacao_terminou))
        self.tarefa.falhou.connect(slot_se_vivo(self._aba, self._exportacao_falhou))
        self.tarefa.finished.connect(slot_se_vivo(self._aba, self._soltar_ocupado))
        self.tarefa.start()

    def _exportar_caderno_pesquisavel(self, cad: caderno.Caderno, livro: Path, caminho: Path) -> None:
        """O livro inteiro com a camada invisível do **caderno** (S-253 sobre a S-614).

        Todas as folhas do original saem, e as que o caderno tem ganham a camada do texto dele -- as
        lidas e as corrigidas, porque aqui o motor não roda: o caderno é tudo o que a aba sabe. As
        demais ficam como estão, que é o que a camada do motor (`cvoff-texto-pesquisavel`) também faz.
        """
        from chess_diagram_ocr.text import pdf_pesquisavel

        if not livro.exists():
            self._aba.estado.emit(f"O livro {livro.name} não está no lugar de antes: o PDF pesquisável sai dele.")
            return
        corrigidas = {e.pagina: d for e in cad.folhas() if (d := cad.folha(e.pagina)) is not None}
        corrigidas = {p: no_livro(d, livro) for p, d in corrigidas.items()}
        desistir = threading.Event()

        def _trabalho() -> str:
            if desistir.is_set():
                return CANCELADA
            relatorio = pdf_pesquisavel.escrever_camada([], caminho, origem=livro, corrigidas=corrigidas)
            avisos = "".join(f" Aviso: {aviso}." for aviso in relatorio.avisos)
            return f"PDF pesquisável do caderno em {caminho.name}: {relatorio.resumo()}.{avisos}"

        self._aba.estado.emit(f"Escrevendo o PDF pesquisável do caderno ({len(corrigidas)} folha(s))…")
        self._registrar_ocupado(
            "Exportando o caderno para PDF pesquisável", loses_work=True, detail=caminho.name, cancelar=desistir.set
        )
        self.tarefa = manter_viva(Tarefa(_trabalho, nome="PDF pesquisável do caderno"))
        self.tarefa.pronto.connect(slot_se_vivo(self._aba, self._exportacao_terminou))
        self.tarefa.falhou.connect(slot_se_vivo(self._aba, self._exportacao_falhou))
        self.tarefa.finished.connect(slot_se_vivo(self._aba, self._soltar_ocupado))
        self.tarefa.start()

    # ---------------------------------------------------------------------- a exportação (S-254)

    def exportar(self, extensao: str) -> None:
        """Pergunta o destino e exporta **fora da thread da janela** (S-254).

        O `.txt` de uma folha é imperceptível, e gravá-lo na thread da janela estaria certo. Deixa
        de estar com o `.rtf` de imagens embutidas e com o PDF pesquisável, que abre o livro,
        escreve a camada e grava um arquivo novo.
        """
        from chess_diagram_ocr.text import arquivo, exportacao

        if self.tarefa is not None:
            self._aba.estado.emit("Já há uma exportação em curso nesta aba.")
            return
        if not self._aba.documento.para_texto().strip():
            # Rodapé e não caixa: é um passo que falta, e não uma escolha.
            self._aba.estado.emit("Não há texto nesta aba para exportar.")
            return
        formato = exportacao.formato_de(extensao)
        destino, _filtro = QFileDialog.getSaveFileName(
            self._aba,
            f"Exportar o texto da folha para {formato.nome}",
            arquivo.sugestao_de_nome(self._aba.documento, extensao=extensao),
            f"{formato.nome} (*{extensao});;Todos (*.*)",
        )
        if not destino:
            return
        caminho = Path(destino)
        # O que se exporta é o que se grava: com a procedência da mão (S-239) -- o cabeçalho do
        # `.txt` a declara -- e sem tocar no que está na tela.
        doc = correcao.com_procedencia_humana(self._aba.documento)
        folha = self._aba._pagina_rgb
        dpi = self._aba._dpi
        com_imagens = bool(getattr(formato, "pasta_de_imagens", ""))
        # A vista dos diagramas vai junto (S-622): o arquivo mostra o que a tela mostra.
        diagramas, ao_lado = alinhamento_dos_diagramas(self._aba.miniaturas.diagramas), self._aba.miniaturas.texto_ao_lado

        # **Cancelável, e o ponto de corte é antes da escrita** (F9-C2, §7 item 7). A conversão
        # do documento é a parte longa; escrever o arquivo é um `write` só. Então desistir tem um
        # lugar seguro e um só: entre as duas. Cortar **durante** a escrita deixaria em disco o
        # `.pdf` truncado que o comentário de `loses_work=True` descreve -- e um arquivo que abre
        # e mente é pior que nenhum, que é a razão de o cancelamento não interromper o `escrever`.
        desistir = threading.Event()

        def _trabalho() -> str:
            # Os recortes dos diagramas saem **antes** do arquivo, na mesma thread: são o que o
            # `.md` e o `.html` apontam (S-338). Sem folha renderizada a marca sai sozinha.
            recortes = gravar_recortes(doc, caminho, folha, dpi=dpi) if com_imagens else {}
            relatorio = exportacao.exportar(doc, formato, recortes=recortes, diagramas=diagramas, ao_lado=ao_lado)
            if desistir.is_set():
                return CANCELADA
            exportacao.escrever(caminho, relatorio)
            return exportacao.texto_do_relatorio(
                caminho, relatorio, tamanho=caminho.stat().st_size
            )

        self._aba.estado.emit(f"Exportando para {caminho.name}…")
        # `loses_work=True`: o arquivo de destino fica pela metade se a janela fechar no meio,
        # e um `.pdf` pesquisável truncado é pior que nenhum -- ele abre e mente.
        self._registrar_ocupado(
            f"Exportando para {formato.nome}",
            loses_work=True,
            detail=caminho.name,
            cancelar=desistir.set,
        )
        self.tarefa = manter_viva(Tarefa(_trabalho, nome="exportação"))
        self.tarefa.pronto.connect(slot_se_vivo(self._aba, self._exportacao_terminou))
        self.tarefa.falhou.connect(slot_se_vivo(self._aba, self._exportacao_falhou))
        self.tarefa.finished.connect(slot_se_vivo(self._aba, self._soltar_ocupado))
        self.tarefa.start()

    def _registrar_ocupado(
        self,
        nome: str,
        *,
        loses_work: bool,
        detail: str = "",
        cancelar: Callable[[], None] | None = None,
    ) -> None:
        """Põe a operação no registro, se a janela deu um. Ver o campo `_busy`.

        `cancelar` é o que o botão do rodapé chama. `busy.register` faz
        `cancellable and cancel is not None`, então passar `None` continua registrando uma
        operação sem cancelamento -- prometer o botão sem a função seria oferecer um cancelamento
        que não cancela.
        """
        if self._busy is None:
            return
        self._ocupado = self._busy.register(
            nome,
            loses_work=loses_work,
            detail=detail,
            cancellable=cancelar is not None,
            cancel=cancelar,
        )

    def _soltar_ocupado(self) -> None:
        """**Sai do registro sempre**, e por isso está no `finished` e não no `pronto` (S-112).

        Um `BusyToken` que ficasse pendurado numa falha faria a janela perguntar "fechar mesmo
        assim?" para sempre, sobre uma operação que já acabou."""
        if self._ocupado is not None:
            self._ocupado.release()
            self._ocupado = None

    def _exportacao_terminou(self, frase: object) -> None:
        """O desfecho da exportação -- **e desistir é um desfecho, não um erro**."""
        self.tarefa = None
        if str(frase) == CANCELADA:
            self._aba.estado.emit("Exportação cancelada. Nada foi gravado.")
            return
        self._aba.estado.emit(str(frase))

    def _exportacao_falhou(self, erro: str, excecao: object = None) -> None:
        self._falha("Exportar", f"Falha ao exportar:\n{erro}", excecao)

    def _falha(self, titulo: str, mensagem: str, excecao: object) -> None:
        """A caixa de falha com o rastro atrás de «Detalhes» e o botão «Copiar» (A10, item 21).

        As duas falhas desta aba abriam um `QMessageBox.critical` com a frase e nada mais: o
        rastro ficava no log, que a caixa mandava a pessoa ir procurar. É a mesma caixa de
        `qt/janela._falhou`, e o rastro é o que a `Tarefa` formatou **na thread**, no instante da
        falha -- é ali que a pilha está inteira.
        """
        from chess_diagram_ocr.qt import dialogos

        tarefa, self.tarefa = self.tarefa, None
        rastro = str(getattr(tarefa, "rastro", "") or "") or rastro_de(excecao)
        dialogos.mostrar_falha(self._aba, titulo, mensagem, rastro)

    # ---------------------------------------------------------------------- a leitura, em thread

    @property
    def motor(self) -> str:
        """O motor de leitura escolhido -- o que a janela grava no estado (item 17)."""
        return str(self._motor)

    @property
    def modo_bloco(self) -> bool:
        return bool(self._modo_bloco)

    def definir_motor(self, nome: str) -> None:
        """Repõe o motor gravado na sessão anterior; um nome que a aba não conhece é ignorado."""
        if nome not in MOTORES:
            return
        self._motor = nome
        self.escolha_de_motor.setCurrentIndex(MOTORES.index(nome))

    @property
    def lingua(self) -> str:
        """A língua do livro que o Tesseract lê (S-717) -- a que a janela grava no estado."""
        return str(self._lingua)

    def definir_lingua(self, codigo: str) -> None:
        """Repõe a língua gravada; um código que a aba não conhece é ignorado, como no motor."""
        indice = self.escolha_de_lingua.findData(codigo)
        if indice < 0:
            return
        self._lingua = codigo
        self.escolha_de_lingua.setCurrentIndex(indice)

    def _lingua_escolhida(self, _indice: int) -> None:
        self._lingua = str(self.escolha_de_lingua.currentData())
        self._aba.caderno.rotular_leitura()

    def motor_gravado(self) -> str:
        """O que o caderno anota como motor da folha. **Na fusão a língua vai junto** (S-717).

        Quem troca a língua da fusão quer a leitura nova, como quem troca de motor, e `abre_do_caderno` só
        sabe comparar o motor. É texto anotado no índice, e nenhum outro lugar o interpreta como `MOTORES`.
        """
        return f"{self._motor}:{self._lingua}" if self._motor == "fusao" else str(self._motor)

    def definir_modo_bloco(self, ligado: bool) -> None:
        """Repõe o modo bloco gravado -- sem a frase do rodapé, que é para quem acabou de clicar."""
        self._modo_bloco = bool(ligado)
        self.caixa_de_bloco.blockSignals(True)
        try:
            self.caixa_de_bloco.setChecked(bool(ligado))
        finally:
            self.caixa_de_bloco.blockSignals(False)

    def modo_bloco_mudou(self) -> None:
        """Liga e desliga o modo bloco. **O comando não inverte a caixa**: quem a inverte é ela."""
        self._modo_bloco = self.caixa_de_bloco.isChecked()
        self._aba.estado.emit(
            "Modo bloco: a folha é lida em blocos, e não linha a linha."
            if self._modo_bloco
            else "Modo linha: a folha volta a ser lida linha a linha."
        )

    def sincronizar_com_a_pagina(self) -> None:
        """Lê a folha que o visualizador está mostrando -- e não a que o campo diz (S-236)."""
        self.campo_de_folha.setValue(self._aba._pagina_indice + 1)
        self.ler()

    def ler(self) -> None:
        """Lê a folha pedida numa thread e desenha o resultado quando ele chega.

        **O `import` do leitor mora aqui**, e é regra e não descuido: por `text/recognizer.py` ele
        alcança o **torch**, e esta aba é construída na abertura da janela. Pagar o carregamento de
        um framework de aprendizado para desenhar uma barra de botões atrasaria a janela inteira
        por uma aba que talvez ninguém abra.

        **A folha que já tem caderno abre dele, sem motor** (S-612) -- salvo quando a pessoa trocou
        o motor ou o modo bloco e a folha não tem correção: aí ela quer a leitura nova. Ler de novo
        uma folha corrigida é `ler_de_novo`, que pergunta.
        """
        self._ler_folha(de_novo=False)

    def _ler_folha(self, *, de_novo: bool) -> None:
        if self.tarefa is not None:
            self._aba.estado.emit("Já há uma leitura em curso nesta aba.")
            return
        if self._aba._pdf is None:
            # Rodapé e não caixa: é um passo que falta, e não uma escolha.
            self._aba.estado.emit("Abra um PDF antes de ler o texto da folha.")
            return
        # A folha da tela vai ao caderno antes (S-611); sem caderno o rascunho vai ao disco e a
        # pergunta continua, pela razão de `abrir_documento` (S-605).
        if not self._aba.caderno.guardar_a_folha() and not self._aba.caderno.confirmar_descarte("Ler de novo descarta as alterações."):
            return
        indice = int(self.campo_de_folha.value()) - 1
        if self._aba.caderno.aberto is not None and self._aba.caderno.avisar_trava(self._aba.caderno.aberto, indice):
            return
        guardada = None if self._aba.caderno.aberto is None else self._aba.caderno.aberto.estado(indice)
        if guardada is not None:
            if not de_novo and caderno.abre_do_caderno(guardada, motor=self.motor_gravado(), modo_bloco=self._modo_bloco):
                if self._aba.caderno.abrir_do_caderno(indice):
                    return
            elif de_novo and guardada.correcoes and not self._confirmar_releitura(indice, guardada.correcoes):
                return
        # O que está na tela quando a leitura parte: o que for digitado **durante** ela não foi
        # confirmado por ninguém, e `_leitura_terminou` pergunta de novo antes de trocá-lo.
        self._documento_ao_ler = self._aba.documento

        motor = self._motor
        bloco = self._modo_bloco
        lingua = self._lingua
        self._leitura_de = (self.motor_gravado(), bloco)
        caminho = self._aba._pdf
        dpi = self.dpi_para_ler()
        teto = self._teto_de_diagramas()
        # A folha que o visualizador já rasterizou serve, se for esta e no mesmo DPI (item 28):
        # copiada aqui, na thread da janela, porque o visualizador pode trocá-la enquanto se lê.
        pronta = self.fornecedor_de_folha(indice) if self.fornecedor_de_folha is not None else None
        imagem_pronta = np.array(pronta[0], copy=True) if pronta is not None and int(pronta[1]) == dpi else None

        def _trabalho() -> tuple[PaginaLida, np.ndarray | None, int, float]:
            # **A folha é rasterizada uma vez, e aqui (S-352).** `ler_pagina` a renderiza sozinha
            # quando ninguém lhe dá a imagem, e as miniaturas precisariam dela de novo -- na thread
            # da janela, que congelava ~355 ms por leitura no outro frontend. O mesmo `dpi` dos
            # dois lados é o que liga pixel a ponto -- e ele viaja com a folha, porque a
            # configuração pode mudar enquanto a leitura corre. O tempo vai junto (item 16): é o
            # número que decide entre o motor rápido e o modo bloco de 40 s.
            inicio = time.perf_counter()
            imagem = imagem_pronta if imagem_pronta is not None else renderizar(caminho, indice, dpi=dpi)
            lida = ler_a_folha(
                caminho, indice, dpi=dpi, motor=motor, modo_bloco=bloco, imagem_rgb=imagem, max_boards=teto, lingua=lingua
            )
            return lida, imagem, dpi, time.perf_counter() - inicio

        self._aba.estado.emit(f"Lendo a folha {indice + 1}…")
        self._registrar_ocupado(
            f"Lendo o texto da folha {indice + 1}",
            loses_work=False,
            detail=f"motor {strings.ROTULOS_DE_MOTOR.get(motor, motor)}" + (" · modo bloco" if bloco else ""),
        )
        self.tarefa = manter_viva(Tarefa(_trabalho, nome="leitura da folha"))
        self.tarefa.pronto.connect(slot_se_vivo(self._aba, self._leitura_terminou))
        self.tarefa.falhou.connect(slot_se_vivo(self._aba, self._leitura_falhou))
        self.tarefa.finished.connect(slot_se_vivo(self._aba, self._soltar_ocupado))
        self.tarefa.start()

    def definir_fornecedor_de_folha(self, fornecedor: Callable[[int], tuple[np.ndarray, int] | None] | None) -> None:
        """Quem responde «a folha N já está rasterizada, e em que DPI?» -- o visualizador (item 28)."""
        self.fornecedor_de_folha = fornecedor

    def definir_importacao(self, fornecedor: Importacao | None) -> None:
        """Quem tem a importação do livro pela suíte -- a janela. A volta do R7 a reaproveita quando serve."""
        self._importacao = fornecedor

    def trazer_da_revisao(self) -> bool:
        """Traz ao caderno as folhas editadas na Revisão de texto da suíte (R7 de volta). Devolve se começou.

        A suíte acha as folhas numa `Tarefa` -- pode reimportar páginas com OCR --, e a regra do dono
        é aplicada ao caderno quando elas chegam (`_revisao_chegou`). A folha da tela vai ao caderno
        antes, para a regra ver a correção feita nela.
        """
        from chess_diagram_ocr.qt import revisao_para_o_caderno as volta

        livro = self._aba.caderno.livro_do_caderno
        if self._aba.caderno.aberto is None or livro is None:
            self._aba.estado.emit("Abra um livro com caderno para trazer as correções da Revisão de texto.")
            return False
        if self.tarefa is not None:
            self._aba.estado.emit("Já há uma operação em curso nesta aba.")
            return False
        if not volta.disponivel():
            self._aba.estado.emit(volta.MOTIVO_AUSENTE)
            return False
        self._aba.caderno.guardar_a_folha()
        documento = self._importacao() if self._importacao is not None else None
        desistir = threading.Event()
        self._aba.estado.emit("Procurando as folhas editadas na Revisão de texto…")
        self._registrar_ocupado("Trazendo as correções da Revisão de texto", loses_work=False, detail=livro.name, cancelar=desistir.set)
        self.tarefa = manter_viva(Tarefa(lambda: volta.buscar(livro, documento=documento, desistir=desistir.is_set), nome="volta da revisão"))
        self.tarefa.pronto.connect(slot_se_vivo(self._aba, self._revisao_chegou))
        self.tarefa.falhou.connect(slot_se_vivo(self._aba, self._revisao_falhou))
        self.tarefa.finished.connect(slot_se_vivo(self._aba, self._soltar_ocupado))
        self.tarefa.start()
        return True

    def _revisao_chegou(self, folhas: object) -> None:
        """A regra do dono no caderno; a folha da tela é reaberta se recebeu o texto da revisão."""
        from chess_diagram_ocr.text import caderno_na_suite

        self.tarefa = None
        cad = self._aba.caderno.aberto
        if cad is None:
            return
        lista = folhas if isinstance(folhas, list) else []
        volta = caderno_na_suite.trazer_da_suite(cad, lista, livro=str(self._aba.caderno.livro_do_caderno or ""))
        origem = self._aba.documento.origem
        if origem is not None and int(origem.pagina) in volta.trazidas:
            self._aba.caderno.abrir_do_caderno(int(origem.pagina))
        self._aba.caderno.mostrar_indice()
        self._aba.estado.emit(volta.frase())

    def _revisao_falhou(self, mensagem: object, _erro: object = None) -> None:
        self.tarefa = None
        self._aba.estado.emit(f"As correções da Revisão de texto não vieram: {mensagem}")

    def dpi_para_ler(self) -> int:
        """O DPI da próxima leitura: o cravado pelo teste, ou o das Configurações (o produto)."""
        if self._dpi_fixo:
            return int(self._dpi_fixo)
        from chess_diagram_ocr.ui import configuracoes

        return int(configuracoes.dpi())

    def _teto_de_diagramas(self) -> int | None:
        """Quantos diagramas o leitor procura na folha: o mesmo teto das Configurações que o
        visualizador usa. Sem ele a aba Texto e a aba Livro discordavam sobre quantos há na página."""
        if self._dpi_fixo:
            return None  # o teste dá a folha sintética e não lê de verdade
        from chess_diagram_ocr.ui import configuracoes

        return int(configuracoes.max_boards())

    def _leitura_terminou(self, resultado: object) -> None:
        """A folha lida voltou da thread -- **e a imagem vem com ela** (S-352), com o DPI dela."""
        self.tarefa = None
        if isinstance(resultado, tuple):
            pagina, imagem, dpi, segundos = (*resultado, None, None)[:4]
        else:
            pagina, imagem, dpi, segundos = resultado, None, None, None
        assert isinstance(pagina, PaginaLida)
        partida = self._documento_ao_ler
        self._documento_ao_ler = None
        # **A folha e o livro são os do resultado (S-824)**, e não os da tela quando ele chega: a
        # página pode ter virado e o livro trocado enquanto o motor lia.
        if chave_do_livro(pagina.documento) != chave_do_livro(self._aba._pdf):
            self._aba.estado.emit(
                f"A folha {pagina.pagina + 1} de «{Path(pagina.documento).name}» ficou de lado: "
                "a leitura chegou com outro livro na tela."
            )
            return
        editado_na_leitura = partida is not None and self._aba.documento is not partida
        if (
            editado_na_leitura
            and not self._aba.caderno.guardar_a_folha()
            and not self._aba.caderno.confirmar_descarte("A folha lida substitui o que foi editado durante a leitura.")
        ):
            self._aba.estado.emit("A folha lida ficou de lado: o texto editado durante a leitura continua na tela.")
            return
        self._aba._pagina_indice = int(pagina.pagina)
        self._aba.caderno.mostrar_pagina(pagina, folha_rgb=imagem, dpi=dpi)
        self._guardar_leitura()
        diagramas = len(pagina.diagramas)
        figuras = f", {diagramas} diagrama(s)" if diagramas else ""
        # «em 3,9 s»: a pessoa escolhe o motor e o modo bloco pelo preço, e o preço tem de ser dito.
        tempo = "" if segundos is None else f" em {formato.decimal(segundos, 1)} s"
        if not self._aba.documento.para_texto().strip():
            # A folha vazia não é falha nem é «0 trecho(s)» (item 26): é uma página sem texto para
            # este motor -- capa, figura inteira, ou scan que o glifo não leu --, e a frase diz o
            # que tentar. O estado vazio do editor já está na tela.
            como = f"motor {strings.ROTULOS_DE_MOTOR.get(self._motor, self._motor)}" + (", modo bloco" if self._modo_bloco else "")
            self._aba.estado.emit(
                f"A folha {pagina.pagina + 1} não tem texto lido ({como}{tempo.replace(' em ', ', ')}): "
                "tente outro motor ou o modo bloco."
            )
            return
        self._aba.estado.emit(f"Folha lida{tempo}: {len(self._aba.documento.corridas)} trecho(s){figuras}.")
        # **Depois de desenhar, e não antes**: se a pessoa recusar a oferta, o que fica na tela é
        # a leitura que ela acabou de pedir (S-255).
        self._aba.caderno.oferecer_rascunho(pagina)

    def _guardar_leitura(self) -> None:
        """A leitura do motor vai ao caderno na hora: é a folha `lida`, e a que se descarta para (S-616)."""
        cad = self._aba.caderno.caderno_da_tela()
        if cad is None:
            return
        motor, bloco = self._leitura_de
        try:
            cad.guardar_leitura(self._aba.documento, motor=motor or self._motor, modo_bloco=bloco)
        except OSError as erro:
            logger.warning("A leitura da folha não foi ao caderno: %s", erro)
            self._aba.estado.emit(f"A folha lida não foi ao caderno: {erro}.")
        self._aba.vista.atualizar_status()
        self._aba.caderno.rotular_leitura()
        self._aba.caderno.mostrar_indice()

    def _leitura_falhou(self, erro: str, excecao: object = None) -> None:
        self._documento_ao_ler = None
        self._falha("Ler a folha", f"Não foi possível ler a folha:\n{erro}", excecao)
