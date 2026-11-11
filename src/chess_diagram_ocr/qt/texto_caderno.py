"""Onde o trabalho da aba de texto fica a salvo: o caderno do livro, o rascunho, o `.cvtxt` e a mesa (S-865).

**Saiu de `qt/painel_de_texto.py` com o estado deles** -- o caderno aberto e o livro dele, o relógio
de inatividade do rascunho, o arquivo `.cvtxt`, e o que a mesa sabe: se ela está armada ou
destacada, o bloco que foi avisado e o recorte que a faixa mostra. O caderno mora em
`text/caderno.py` e o rascunho em `text/rascunho.py`; aqui ficam o relógio, a pergunta e o vaivém
com a tela.

**O rascunho automático (S-255) e a procedência humana ao gravar (S-239)** vieram no mesmo
movimento da folha rasterizada: eles moram em `text/rascunho.py` e `text/correcao.py`, e aqui ficam
só o relógio de inatividade e a pergunta. O `.cvtxt` reaberto refaz as miniaturas do livro se ele
ainda estiver onde estava (`abrir`).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias

import numpy as np
from PyQt6.QtCore import QObject, Qt, QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QFileDialog, QMenu, QMessageBox

from chess_diagram_ocr.arquivo_do_dono import GravacaoRecusada
from chess_diagram_ocr.qt import texto_leitura, texto_miniaturas
from chess_diagram_ocr.qt.imagens import pixmap_de_rgb
from chess_diagram_ocr.qt.painel_de_navegacao import FOLHAS
from chess_diagram_ocr.text import caderno, correcao, rascunho, rico
from chess_diagram_ocr.text.documento import PaginaLida
from chess_diagram_ocr.text.pagina import BlocoDeDiagrama, BlocoDeTexto
from chess_diagram_ocr.ui import comandos, mesa, strings
from chess_diagram_ocr.ui.livros import chave_do_livro, mesmo_livro

if TYPE_CHECKING:
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto

logger = logging.getLogger(__name__)

__all__ = ["CadernoDaAba", "FolhasDaSuite"]

FolhasDaSuite: TypeAlias = list[dict[str, Any]]
"""As folhas corrigidas do caderno no formato que a suíte lê para o EPUB/DOCX do livro (R7)."""


class CadernoDaAba(QObject):
    """O caderno do livro aberto, o rascunho da folha, o `.cvtxt` e a aba como mesa."""

    def __init__(
        self,
        aba: PainelDeTexto,
        *,
        pasta_de_rascunhos: Path | None,
        pasta_de_cadernos: Path | None,
        com_caderno: bool,
    ) -> None:
        super().__init__(aba)
        self._aba = aba
        self._pasta_de_rascunhos: Path | None = pasta_de_rascunhos
        """Onde o rascunho da S-255 é gravado. `None` usa `text/rascunho.PASTA_PADRAO`; o teste
        passa uma pasta própria, senão leria `data/rascunhos/` da máquina de quem o roda -- e um
        rascunho ali abriria a pergunta de recuperação no meio da suíte."""
        self._pasta_de_cadernos: Path | None = (
            pasta_de_cadernos if pasta_de_cadernos is not None else (caderno.PASTA_PADRAO if com_caderno else None)
        )
        """Onde o caderno do livro mora (S-610). `None` é a aba sem caderno -- a de teste que não o
        pede --, que guarda o trabalho só no rascunho, como antes da Fase 91. A janela liga
        `com_caderno`, e a pasta é a de `text/caderno.PASTA_PADRAO` lida **agora**: é o que deixa a
        suíte dar a cada teste uma pasta própria."""
        self._caderno: caderno.Caderno | None = None
        self.livro_do_caderno: Path | None = None
        self._vai_ao_caderno = False
        """A folha da tela é trabalho do caderno: lida pelo motor, aberta dele ou editada. Um
        `.cvtxt` avulso aberto e não tocado não é -- abri-lo para olhar não troca a folha do caderno
        (S-616)."""
        self._rascunho = QTimer(self._aba)
        """O relógio de **inatividade** do rascunho: cada edição o reinicia, e ele grava alguns
        segundos depois da última (S-255). Um relógio fixo gravaria no meio da digitação."""
        self._rascunho.setSingleShot(True)
        self._rascunho.setInterval(int(rascunho.ESPERA_SEGUNDOS * 1000))
        self._rascunho.timeout.connect(self._depois_da_pausa)
        self._mudou_em = 0.0
        self._cursor_em = 0.0
        """Quando o documento mudou e quando o cursor mexeu pela última vez: a régua do salvamento
        no caderno pede os dois parados (`caderno.espera_restante`, S-612)."""
        self.ler_ao_chegar = False
        """Ler a folha sem caderno ao chegar a ela pela mesa (S-644). Ver `alternar_ler_ao_chegar`."""
        self._mesa_armada = False
        """A mesa de texto da janela principal está armada (S-640). Quem diz é a janela, por `definir_mesa`."""
        self._destacada = False
        """A aba está na janela da mesa (S-646). Quem diz é `MesaDestacada`, por `definir_destacada`."""
        self._bloco_avisado: tuple[float, ...] | None = None
        self._bloco_na_faixa: tuple[int, ...] | None = None
        self.recorte_na_faixa: np.ndarray | None = None
        """O recorte da folha que a faixa do bloco impresso mostra, antes da escala (S-643)."""
        self._faixa_ligada = True

    def no_menu(self, menu: QMenu) -> None:
        """O que o rascunho e o caderno sabem fazer com a folha da tela, no menu do botão direito."""
        # O rascunho da folha na tela, quando há um (item 25): a oferta recusada na leitura volta
        # a estar à mão, sem reler a folha.
        pagina = self._aba._pagina
        guardado = None if pagina is None else rascunho.achar(pagina.documento, pagina.pagina, pasta=self._pasta_de_rascunhos)
        if guardado is not None:
            menu.addSeparator()
            recuperar = QAction(f"Recuperar o rascunho de {guardado.data_legivel}", menu)
            recuperar.triggered.connect(lambda: self.recuperar_rascunho())
            menu.addAction(recuperar)
        self.menu_do_caderno(menu)

    # ------------------------------------------------------------------ a folha que entra na tela

    def mostrar_pagina(
        self, pagina: PaginaLida, *, folha_rgb: np.ndarray | None = None, dpi: int | None = None
    ) -> None:
        """Abre uma `PaginaLida` no editor. É o que a leitura entrega -- e é o ponto de partida
        contra o qual `tem_alteracoes` compara: a folha recém-lida não tem nada por gravar.

        `dpi` é o da `folha_rgb`, quando ela vem: é o que liga os pontos do `bbox` aos pixels dela.
        """
        guardadas = self._aba._posicoes.get((chave_do_livro(pagina.documento), int(pagina.pagina)))
        if guardadas:
            pagina = pagina.com_posicoes(guardadas)
        self._aba._pagina = pagina
        self._aba._pagina_rgb = folha_rgb
        self._aba._folha_por_ler = None
        self._aba.correcao.ignoradas.clear()
        if dpi:
            self._aba._dpi = int(dpi)
        self._aba.espelho.zerar_pilha()
        self._aba.desenhar_documento(rico.de_pagina(pagina))
        self._aba._documento_gravado = self._aba.documento
        self._rascunho.stop()  # o desenho emitiu `documento_mudou`; a folha recém-lida não tem o que gravar
        self._aba._correcoes = 0  # a folha recém-lida não tem correção nenhuma
        self._aba.vista.atualizar_status()

    # ------------------------------------------------------------------------- o arquivo (S-343)

    def abrir_documento(self) -> None:
        """Abre um `.cvtxt` gravado antes, com os diagramas de volta se o livro ainda estiver lá."""
        from chess_diagram_ocr.text import arquivo

        # A folha vai ao caderno **antes** de trocar (S-611), e a pergunta só sobra sem ele -- e aí
        # o rascunho já foi ao disco, como em `confirmar_fechamento` (S-605).
        if not self.guardar_a_folha() and not self.confirmar_descarte("Abrir outro arquivo descarta as alterações."):
            return
        origem, _filtro = QFileDialog.getOpenFileName(
            self._aba, "Abrir texto de folha", "", f"{arquivo.NOME_DO_FORMATO} (*{arquivo.EXTENSAO});;Todos (*.*)"
        )
        if not origem:
            return
        try:
            doc = arquivo.carregar(Path(origem))
        except (arquivo.ArquivoInvalido, OSError) as erro:
            logger.debug("Documento não abriu (%s): %s", origem, erro)
            QMessageBox.critical(self._aba, "Texto", str(erro))
            return
        self.abrir(doc)
        self._aba._caminho_do_documento = Path(origem)  # `Salvar` grava de volta aqui (S-343)
        # Abrir para olhar não troca a folha do caderno; a primeira edição troca, e a folha que o
        # caderno tinha fica como `anterior` (S-616).
        self._vai_ao_caderno = False
        cad = self.caderno_da_tela()
        if cad is not None and doc.origem is not None:
            cad.visitar(doc.origem.pagina)

    def abrir(self, doc: rico.DocumentoRico, *, folha_rgb: np.ndarray | None = None, renderizar: bool = True) -> None:
        """Põe o documento na tela e recupera o que só o PDF pode dar: as miniaturas (S-238).

        **O PDF ausente não é erro.** O texto abre igual, as miniaturas faltam, e o rodapé diz
        qual livro não foi encontrado -- a regra de degradação de `ui/theme.py`. O contrário faria
        uma pasta de trabalho movida de lugar bloquear o acesso ao que se corrigiu nela.

        `folha_rgb` é a folha já renderizada, quando quem chama a tem -- o rascunho recuperado é
        da folha que acabou de ser lida, e renderizá-la de novo seria pagar duas vezes.
        `renderizar=False` é de quem vai rasterizá-la fora da thread da janela (`abrir_do_caderno`).
        """
        from chess_diagram_ocr.text import arquivo

        self._aba._pagina = doc.origem
        self._aba._pagina_rgb = folha_rgb
        self._aba._folha_por_ler = None
        self._aba.espelho.zerar_pilha()
        # Documento novo na tela, arquivo de destino zerado: gravar aqui é a **primeira** vez
        # deste documento, e "Salvar" volta a perguntar onde (S-343). Quem abriu de um arquivo
        # repõe o caminho logo depois, em `abrir_documento`.
        self._aba._caminho_do_documento = None
        aviso = ""
        caminho = arquivo.pdf_de(doc)
        if folha_rgb is None and caminho is not None and doc.origem is not None:
            if caminho.exists():
                if renderizar:
                    self._aba._dpi = self._aba.leitura.dpi_para_ler()
                    self._aba._pagina_rgb = texto_leitura.renderizar(caminho, doc.origem.pagina, dpi=self._aba._dpi)
            else:
                aviso = f" · o livro {caminho.name} não está no lugar de antes: sem miniaturas"
        if doc.origem is not None:
            self._aba._pagina_indice = int(doc.origem.pagina)
            self._aba.leitura.campo_de_folha.setValue(self._aba._pagina_indice + 1)
        self._aba.desenhar_documento(doc)
        self._aba._documento_gravado = self._aba.documento
        self._rascunho.stop()  # como em `mostrar_pagina`: o que veio do disco não tem o que gravar
        self._aba.vista.contar_correcoes()  # o arquivo pode trazer correções gravadas ontem
        # O texto da folha 14 na tela com o visualizador na folha 3 é o que fazia a pessoa
        # procurar a página à mão (item 9). Só para o livro que está aberto: um `.cvtxt` de outro
        # livro não troca o livro de ninguém -- é a mesma regra de `definir_livro`.
        if doc.origem is not None and caminho is not None and self._aba._pdf is not None and mesmo_livro(caminho, self._aba._pdf):
            self._aba.folha_pedida.emit(self._aba._pagina_indice)
        diagramas = len(self._aba.documento.diagramas)
        figuras = sum(1 for c in self._aba.documento.diagramas if self._aba.miniaturas.tem_miniatura(c))
        resumo = f"Texto aberto: {len(self._aba.documento.corridas)} trecho(s), {diagramas} diagrama(s)"
        if diagramas and not aviso:
            resumo += f" ({figuras} com miniatura)"
        self._aba.estado.emit(resumo + aviso + ".")

    def salvar_documento(self) -> None:
        """Grava o `.cvtxt` **no arquivo já escolhido**, e só pergunta na primeira vez (S-343).

        **"Salvar" e "Salvar como…" eram o mesmo comando**, e os dois perguntavam o destino: o
        catálogo mostrava dois rótulos, o menu dois itens e a paleta duas linhas para uma coisa só.
        Num ciclo de correção, em que se grava a cada trecho conferido, o diálogo repetido é o
        atrito -- e o rótulo "como…" prometia uma escolha que o outro tomava do mesmo jeito.
        """
        self._salvar_documento_em(self._aba._caminho_do_documento)

    def salvar_documento_como(self) -> None:
        """Pergunta o destino e passa a gravar nele."""
        self._salvar_documento_em(None)

    def _salvar_documento_em(self, caminho: Path | None) -> None:
        from chess_diagram_ocr.text import arquivo

        if not self._aba.documento.para_texto().strip():
            # Rodapé e não caixa, como a exportação: é um passo que falta, não uma escolha. O Tk
            # já recusava; o porte gravava um `.cvtxt` vazio e dizia «Texto gravado» (item 19).
            self._aba.estado.emit("Não há texto nesta aba para salvar: leia uma folha ou abra um arquivo.")
            return
        if caminho is None:
            escolhido, _filtro = QFileDialog.getSaveFileName(
                self._aba,
                "Salvar o texto da folha",
                arquivo.sugestao_de_nome(self._aba.documento),
                f"{arquivo.NOME_DO_FORMATO} (*{arquivo.EXTENSAO});;Todos (*.*)",
            )
            if not escolhido:
                return
            caminho = Path(escolhido)
        # **A marcação é aplicada aqui, e não só no arquivo** (S-239): o que se grava é o que fica
        # na tela. Ela é derivada da `PaginaLida`, é idempotente, e não toca no que o motor leu --
        # e o que a mão corrigiu deixa de ser pintado como palpite do motor.
        gravado = correcao.com_procedencia_humana(self._aba.documento)
        try:
            arquivo.gravar(caminho, gravado)
        except OSError as erro:
            QMessageBox.critical(self._aba, "Texto", f"Não foi possível gravar:\n{erro}")
            return
        if gravado is not self._aba.documento:
            # Sem passar pela pilha: a procedência não é edição de ninguém, e um `Ctrl+Z` que a
            # tirasse devolveria a tinta de "revisar" a um trecho já conferido e gravado.
            self._aba.espelho.digitacao = None
            self._aba.documento = gravado
            self._aba.espelho.desenhar(selecao=self._aba.espelho.selecao_atual())
        self._aba._documento_gravado = gravado
        self._aba._caminho_do_documento = caminho
        # O trabalho chegou a um lugar melhor: o rascunho da S-255 sai.
        self._rascunho.stop()
        if self._aba._pagina is not None:
            rascunho.descartar(self._aba._pagina.documento, self._aba._pagina.pagina, pasta=self._pasta_de_rascunhos)
        # A conta aparece porque a correção é o que o `.cvtxt` tem de mais caro -- e porque um
        # número no rodapé é o que faz alguém notar quando ele vem zerado (S-239).
        feitas = len(correcao.correcoes(gravado))
        quanto = f" · {feitas} correção(ões) sobre o que o motor leu" if feitas else ""
        self._aba._correcoes = feitas
        self._aba.vista.atualizar_status()
        self._aba.estado.emit(f"Texto gravado em {caminho.name}{quanto}.")

    def confirmar_fechamento(self) -> bool:
        """A janela vai fechar: `True` se pode, perguntando antes quando há texto por gravar.

        **O rascunho vai para o disco antes da pergunta** (S-255): o relógio de inatividade pode
        não ter disparado, e fechar -- com "Sim", sem tela, ou pela falha que vem a seguir -- é
        exatamente o momento para o qual ele existe. Gravar de novo o que já está lá não custa.

        Com o caderno (S-611) não há pergunta: a folha vai para ele, e a trava sai.
        """
        if self.guardar_a_folha():
            self.fechar_caderno()
            return True
        return self.confirmar_descarte("Fechar a janela descarta as alterações.", ao_fechar=True)

    # ---------------------------------------------------------------- o caderno do livro (S-610)

    def caderno_da_tela(self) -> caderno.Caderno | None:
        """O caderno em que a folha da tela mora: o do livro aberto, se ela for dele."""
        origem = self._aba.documento.origem
        if self._caderno is None or origem is None:
            return None
        if chave_do_livro(origem.documento) != chave_do_livro(self.livro_do_caderno):
            return None
        return self._caderno

    @property
    def aberto(self) -> caderno.Caderno | None:
        """O caderno do livro aberto, para quem pergunta por ele -- o índice das folhas (S-613)."""
        return self._caderno

    def folhas_para_a_suite(self, paginas: Sequence[int] | None) -> FolhasDaSuite:
        """As folhas corrigidas do caderno, para o EPUB/DOCX do livro que a suíte escreve (R7).

        A suíte chama isto na thread da janela, depois do diálogo e antes de começar; `paginas` é o
        alcance escolhido nele (0-based, `None` = o livro). A folha da tela entra como está.
        """
        from chess_diagram_ocr.text import caderno_na_suite

        if self._caderno is None:
            return []
        self.guardar_a_folha()
        return caderno_na_suite.folhas_para_a_suite(self._caderno, paginas)

    def folhas_do_livro(self, livro: Path | str, paginas: Sequence[int] | None) -> FolhasDaSuite:
        """As folhas corrigidas do caderno de `livro`, que não precisa ser o aberto (R7).

        É a pergunta da aba Rotulagem, que exporta o livro do projeto dela. O livro aberto aqui
        responde como `folhas_para_a_suite`, com a folha da tela gravada; outro livro abre o caderno
        dele **só para leitura**, sem tomar a trava de quem estiver corrigindo nele.
        """
        from chess_diagram_ocr.text import caderno_na_suite

        if self._caderno is not None and caderno.identidade_de(livro) == self._caderno.identidade:
            return self.folhas_para_a_suite(paginas)
        if self._pasta_de_cadernos is None or not Path(livro).exists():
            return []
        outro = caderno.abrir(livro, pasta=self._pasta_de_cadernos, travar=False)
        return [] if outro is None else caderno_na_suite.folhas_para_a_suite(outro, paginas)

    def guardar_a_folha(self) -> bool:
        """Guarda a folha da tela no caderno, se ela mudou (S-611). Devolve se o trabalho está a salvo.

        Toda troca do que está na tela -- ler outra folha, abrir um arquivo, trocar de livro,
        fechar -- passa por aqui antes, e por isso a pergunta "descarta as alterações?" saiu desses
        caminhos: não há mais o que descartar. **Sem caderno** -- a aba de teste, o livro que não
        abre, o caderno que outra janela trava -- a rede é o rascunho de antes, e `False` com
        alteração por gravar diz a quem chama que a pergunta continua.
        """
        self._rascunho.stop()
        cad = self.caderno_da_tela()
        if cad is None or cad.somente_leitura:
            self.gravar_rascunho()
            return not self._aba.tem_alteracoes
        if not self._vai_ao_caderno:
            return not self._aba.tem_alteracoes
        pagina = int(self._aba.documento.origem.pagina)  # type: ignore[union-attr]  # `caderno_da_tela` viu a origem
        feitas = len(correcao.correcoes(self._aba.documento))
        try:
            feito = cad.gravar(correcao.com_procedencia_humana(self._aba.documento), correcoes=feitas)
        except OSError as erro:
            logger.warning("O caderno não gravou a folha %d: %s", pagina + 1, erro)
            self._aba.estado.emit(f"O caderno não gravou a folha {pagina + 1}: {erro}. O texto continua na tela.")
            self.gravar_rascunho()
            return False
        if feito == caderno.RECUSADA_VAZIA:
            self._aba.estado.emit(f"A folha {pagina + 1} vazia não foi gravada por cima do texto que o caderno tem dela.")
            return True
        if feito == caderno.TRAVADA:
            self.avisar_trava(cad, pagina)
            self.gravar_rascunho()
            return False
        if feitas and feito == caderno.GRAVADA:
            self._ensinar_as_palavras(cad)
        self._aba._documento_gravado = self._aba.documento
        self._aba._correcoes = feitas
        self._aba.vista.atualizar_status()
        self.rotular_leitura()
        self.mostrar_indice()
        return True

    def _ensinar_as_palavras(self, cad: caderno.Caderno) -> None:
        """O que a mão escreveu e o léxico não conhece vai ao léxico do livro, e os árbitros passam a ouvir nas folhas seguintes (S-766)."""
        from chess_diagram_ocr.text import correcao_no_livro, dado_corrigido, fusao

        if not dado_corrigido.pares_tocados(self._aba.documento):
            return
        try:
            novas = correcao_no_livro.ensinar(cad, self._aba.documento, existe=fusao.existe_do_livro(self._aba.leitura.lingua, cad.lexico()))
        except OSError as erro:
            logger.warning("O léxico do livro não gravou: %s", erro)
            return
        if novas:
            self._aba.estado.emit(f"No léxico do livro: {', '.join(novas)}.")

    def corrigir_em_todas_as_folhas(self) -> Any:
        """Abre a janela da troca em massa, com a prévia obrigatória (S-766). A palavra selecionada, ou a última corrigida, já vem nos campos."""
        from chess_diagram_ocr.qt.correcao_no_livro import JanelaDeCorrecaoNoLivro
        from chess_diagram_ocr.text import dado_corrigido

        cad = self._caderno
        if cad is None or cad.somente_leitura:
            self._aba.estado.emit("Só há o que corrigir em todas as folhas com o caderno do livro aberto para escrita.")
            return None
        self.guardar_a_folha()  # o que está na tela entra na procura
        selecionada = self._aba.editor.textCursor().selectedText().strip()
        pares = dado_corrigido.pares_tocados(self._aba.documento)
        antes, depois = (selecionada, "") if selecionada else (pares[-1].antes, pares[-1].depois) if pares else ("", "")
        janela = JanelaDeCorrecaoNoLivro(self._aba, cad, antes=antes, depois=depois)
        self._janela_de_correcao_no_livro = janela
        janela.show()
        return janela

    def folhas_corrigidas_no_livro(self, feito: Any) -> None:
        """A troca em massa terminou: a frase no rodapé, o índice, e a folha da tela, se ela mudou, relida do caderno."""
        from chess_diagram_ocr.text import correcao_no_livro

        pagina = None if self._aba.documento.origem is None else int(self._aba.documento.origem.pagina)
        if pagina is not None and pagina in feito.folhas:
            self.abrir_do_caderno(pagina)
        self.mostrar_indice()
        self._aba.estado.emit(correcao_no_livro.frase_do_resultado(feito))

    def abrir_caderno(self, livro: Path | None) -> None:
        """Troca o caderno pelo do livro que chegou. A folha da tela vai antes ao do livro que sai."""
        self.guardar_a_folha()
        self.fechar_caderno()
        if self._pasta_de_cadernos is None or livro is None or not livro.exists():
            return
        self._caderno = caderno.abrir(livro, pasta=self._pasta_de_cadernos)
        self.livro_do_caderno = livro
        if self._caderno is None:
            return
        if self._caderno.somente_leitura:
            self._aba.estado.emit(self._caderno.motivo)
        else:
            self._trazer_rascunhos(livro)
        self.mostrar_indice()

    def fechar_caderno(self) -> None:
        """Solta a trava do caderno aberto. Na troca de livro e no fechamento da janela."""
        if self._caderno is not None:
            self._caderno.fechar()
        self._caderno = None
        self.livro_do_caderno = None
        self.mostrar_indice()

    def _trazer_rascunhos(self, livro: Path) -> None:
        """Os rascunhos de antes do caderno entram nele (S-615), e só então saem da pasta deles."""
        cad = self._caderno
        assert cad is not None
        try:
            achados = rascunho.listar(livro, pasta=self._pasta_de_rascunhos)
        except OSError as erro:  # noqa: BLE001 - os rascunhos continuam onde estão
            logger.debug("Rascunhos de %s não listados: %s", livro, erro)
            return
        trazidas: list[int] = []
        for achado in achados:
            try:
                doc = texto_leitura.no_livro(rascunho.carregar(achado), livro)
                entrou = cad.trazer_rascunho(doc, achado.quando, correcoes=len(correcao.correcoes(doc)))
            except (OSError, ValueError, GravacaoRecusada) as erro:  # `ArquivoInvalido` é um `ValueError`; o rascunho fica
                logger.debug("Rascunho %s não entrou no caderno: %s", achado.caminho, erro)
                continue
            if entrou:
                trazidas.append(achado.folha + 1)
            else:
                logger.info("Rascunho da folha %d mais velho que o caderno: descartado.", achado.folha + 1)
            rascunho.descartar(livro, achado.folha, pasta=self._pasta_de_rascunhos)
        if trazidas:
            self._aba.estado.emit(
                f"{len(trazidas)} rascunho(s) deste livro entraram no caderno (folha "
                f"{', '.join(map(str, trazidas[:6]))}{'…' if len(trazidas) > 6 else ''})."
            )

    def rotular_leitura(self) -> None:
        """«Abrir folha» quando a folha do campo tem caderno, «Ler folha» quando o motor vai ler."""
        if not hasattr(self._aba, "botao_de_ler"):
            return
        guardada = None if self._caderno is None else self._caderno.estado(int(self._aba.leitura.campo_de_folha.value()) - 1)
        abre = guardada is not None and caderno.abre_do_caderno(guardada, motor=self._aba.leitura.motor_gravado())
        self._aba.botao_de_ler.setText(strings.ABRIR_FOLHA_DO_CADERNO if abre else comandos.rotulo_de_botao("ler_folha"))

    def abrir_do_caderno(self, indice: int) -> bool:
        """Põe na tela a folha que o caderno tem, sem motor (S-612). `False` se o arquivo não abriu."""
        cad = self._caderno
        doc = None if cad is None else cad.folha(indice)
        if cad is None or doc is None:
            if cad is not None:
                self.avisar_trava(cad, indice)
            return False
        dpi = self._aba.leitura.dpi_para_ler()
        pronta = self._aba.leitura.fornecedor_de_folha(indice) if self._aba.leitura.fornecedor_de_folha is not None else None
        folha_rgb = np.array(pronta[0], copy=True) if pronta is not None and int(pronta[1]) == dpi else None
        if folha_rgb is not None:
            self._aba._dpi = dpi
        self.abrir(texto_leitura.no_livro(doc, self.livro_do_caderno), folha_rgb=folha_rgb, renderizar=False)
        if folha_rgb is None:
            self._aba.leitura.renderizar_ao_fundo(indice)
        cad.visitar(indice)
        self._vai_ao_caderno = True
        self.mostrar_indice()  # a linha marcada do índice acompanha a folha que abriu
        guardada = cad.estado(indice)
        feitas = 0 if guardada is None else guardada.correcoes
        self._aba.estado.emit(
            f"Folha {indice + 1} aberta do caderno"
            + (f", com {caderno.correcoes_por_extenso(feitas)}" if feitas else "")
            + ". «Ler a folha de novo» fica no menu do botão direito."
        )
        return True

    def avisar_trava(self, cad: caderno.Caderno, indice: int) -> bool:
        """A folha do caderno não abre (S-896)? O rodapé diz, e quem chama não lê nem grava por cima."""
        trava = cad.trava(indice)
        if trava is None:
            return False
        self._aba.estado.emit(f"A folha {indice + 1} do caderno não abriu, e fica como está. {trava.mensagem}")
        return True

    def voltar_a_anterior(self) -> bool:
        """Põe na tela a versão de quando a pessoa chegou da última vez à folha (S-611). `Ctrl+Z` desfaz."""
        return self._por_versao_na_tela(caderno.Caderno.anterior, "A versão anterior da folha", "Esta folha não tem versão anterior no caderno.")

    def abrir_a_da_revisao(self) -> bool:
        """Põe na tela a versão que a Revisão de texto da suíte deu à folha corrigida aqui (S-896). `Ctrl+Z` desfaz."""
        return self._por_versao_na_tela(caderno.Caderno.da_suite, "A versão da Revisão de texto", "Esta folha não tem versão da Revisão de texto no caderno.")

    def _por_versao_na_tela(self, versao_de: Callable[[caderno.Caderno, int], rico.DocumentoRico | None], qual: str, sem: str) -> bool:
        cad = self.caderno_da_tela()
        origem = self._aba.documento.origem
        versao = None if cad is None or origem is None else versao_de(cad, int(origem.pagina))
        if versao is None:
            self._aba.estado.emit(sem)
            return False
        self._aba.espelho.aplicar(texto_leitura.no_livro(versao, self.livro_do_caderno))
        self._aba.vista.contar_correcoes()
        self._aba.estado.emit(f"{qual} está na tela; Ctrl+Z volta à de agora.")
        return True

    def descartar_correcoes(self) -> bool:
        """Devolve a folha ao que o motor leu (S-616). A corrigida fica como `anterior`, e `Ctrl+Z` a traz.

        É o único caminho em que a pergunta "descarta?" continua, porque aqui ela é o gesto pedido.
        """
        from chess_diagram_ocr.qt import dialogos

        cad = self.caderno_da_tela()
        if cad is None:
            return False
        pagina = int(self._aba.documento.origem.pagina)  # type: ignore[union-attr]
        lida = cad.lida(pagina)
        if lida is None:
            self._aba.estado.emit("O caderno não tem a leitura do motor desta folha.")
            return False
        if not dialogos.ha_quem_responda():
            return False
        resposta = QMessageBox.question(
            self._aba,
            "Texto",
            f"Descartar as correções da folha {pagina + 1}? A folha volta ao que o motor leu; a versão "
            "corrigida fica como anterior, e Ctrl+Z a traz de volta.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return False
        self.guardar_a_folha()  # a corrigida está no caderno antes de sair da tela
        cad.visitar(pagina)  # e vira `anterior` na gravação que vem
        self._aba.espelho.aplicar(texto_leitura.no_livro(lida, self.livro_do_caderno))
        self.guardar_a_folha()
        self._aba.vista.contar_correcoes()
        self._aba.estado.emit(f"A folha {pagina + 1} voltou ao que o motor leu; Ctrl+Z traz as correções de volta.")
        return True

    def marcar_conferida(self) -> bool:
        """Marca a folha da tela como conferida no índice do caderno -- ou desmarca, se ela já está."""
        cad = self.caderno_da_tela()
        if cad is None:
            return False
        pagina = int(self._aba.documento.origem.pagina)  # type: ignore[union-attr]
        self.guardar_a_folha()
        guardada = cad.estado(pagina)
        if guardada is None:
            return False
        conferida = guardada.estado != caderno.CONFERIDA
        novo = caderno.CONFERIDA if conferida else (caderno.EDITADA if guardada.correcoes else caderno.LIDA)
        if not cad.marcar(pagina, novo):
            return False
        self.mostrar_indice()
        self._aba.vista.atualizar_status()
        self._aba.estado.emit(
            f"Folha {pagina + 1} {'conferida' if conferida else 'desmarcada'}: "
            f"{cad.conferidas()} folha(s) conferida(s) neste caderno."
        )
        return True

    def alternar_indice(self) -> None:
        """Abre ou fecha o índice das folhas do caderno (S-613), a aba Folhas do painel de navegação."""
        if self._aba.indice.isVisible():
            self._aba.navegacao.hide()
        else:
            self._aba.correcao.mostrar_navegacao(FOLHAS)
            if self._caderno is None:
                self._aba.estado.emit("O índice lista as folhas do caderno do livro aberto: abra um livro e leia uma folha.")
        self._aba.editor.setFocus()

    # ---------------------------------------------------------- a faixa do bloco impresso (S-643)

    def alternar_bloco_impresso(self) -> None:
        """Liga ou desliga a faixa do bloco impresso da mesa (S-643)."""
        self._faixa_ligada = not self._faixa_ligada
        self._bloco_na_faixa = None
        self.mostrar_impresso()

    # ---------------------------------------------------------------- o índice das folhas (S-613)

    def mostrar_indice(self) -> None:
        """Redesenha o índice, se ele está à vista. Escondido não custa nada: ele se refaz ao abrir."""
        if not hasattr(self._aba, "indice") or not self._aba.indice.isVisible():
            return
        folhas = () if self._caderno is None else self._caderno.folhas()
        self._aba.indice.mostrar(folhas, atual=None if self._aba._pagina is None else int(self._aba._pagina.pagina))

    def abrir_do_indice(self, pagina: int) -> None:
        """O clique numa linha do índice: a folha abre como pelo «Abrir folha» (S-612)."""
        self._aba.leitura.campo_de_folha.setValue(int(pagina) + 1)
        self._aba.leitura.ler()

    # ------------------------------------------------------- a mesa: o bloco sob o cursor (S-642)

    def anotar_cursor(self) -> None:
        self._cursor_em = self._aba._relogio()
        self.mostrar_impresso()
        self.avisar_bloco()

    def _sob_o_cursor(self) -> tuple[object, tuple[int, int]] | None:
        """O que está sob o cursor na folha: a **linha** lida, quando se acha (S-642, etapa 2), e o bloco
        quando não -- a linha reescrita à mão não casa com a lida, e a resposta volta a ser o bloco.

        Devolve o objeto com `bbox` (`LinhaLida` ou o bloco) e a chave `(bloco, linha)`, com `-1` na
        linha quando é o bloco inteiro.
        """
        doc = self._aba.documento
        if doc.origem is None:
            return None
        deslocamento = self._aba.espelho.mapa.deslocamento(self._aba.editor.textCursor().position())
        blocos = doc.origem.blocos
        linha = rico.linha_em(doc, deslocamento)
        if linha is not None:
            no_bloco, indice = linha
            lido = blocos[no_bloco]
            if isinstance(lido, BlocoDeTexto):  # `linha_em` só acha linha em bloco de texto
                return lido.linhas[indice], (no_bloco, indice)
        bloco = rico.bloco_em(doc, deslocamento)
        if bloco is None or not 0 <= bloco < len(blocos):
            return None
        return blocos[bloco], (bloco, -1)

    def avisar_bloco(self) -> None:
        """Diz à mesa qual bloco da folha está sob o cursor (S-642). Fora da mesa, nenhum."""
        bbox = None
        doc = self._aba.documento
        if self.na_mesa and doc.origem is not None and int(doc.origem.pagina) == self._aba._pagina_indice:
            achado = self._sob_o_cursor()
            caixa = None if achado is None else getattr(achado[0], "bbox", None)
            bbox = None if caixa is None else tuple(float(v) for v in caixa)
        if bbox != self._bloco_avisado:
            self._bloco_avisado = bbox
            self._aba.bloco_destacado.emit(bbox)

    def ir_ao_ponto(self, x: float, y: float) -> bool:
        """O clique na folha, em pontos (S-642): o cursor vai ao começo do bloco clicado. Devolve se foi.

        O menor bloco que contém o ponto ganha, como a menor caixa de diagrama ganha no
        visualizador. Só vale para a folha que está no editor -- o clique na folha 7 com a folha 3
        no texto não tem para onde levar o cursor.
        """
        doc = self._aba.documento
        if doc.origem is None or int(doc.origem.pagina) != self._aba._pagina_indice:
            return False
        dentro = [
            (indice, bloco.bbox)
            for indice, bloco in enumerate(doc.origem.blocos)
            if getattr(bloco, "bbox", None) is not None
            and bloco.bbox[0] <= x <= bloco.bbox[2]
            and bloco.bbox[1] <= y <= bloco.bbox[3]
        ]
        for indice, _caixa in sorted(dentro, key=lambda par: (par[1][2] - par[1][0]) * (par[1][3] - par[1][1])):
            comeco = rico.deslocamento_do_bloco(doc, indice)
            if comeco is None:
                continue
            cursor = self._aba.editor.textCursor()
            cursor.setPosition(self._aba.espelho.mapa.posicao(comeco))
            self._aba.editor.setTextCursor(cursor)
            self._aba.editor.ensureCursorVisible()
            self._aba.editor.setFocus()
            return True
        return False

    # ------------------------------- a mesa (S-643, S-644, S-646) e o rascunho automático (S-255)

    def alternar_ler_ao_chegar(self) -> None:
        """«Ler ao chegar numa folha sem caderno» (S-644): para quem corrige o livro do começo ao fim
        com o motor rápido. Desligada por padrão -- ler custa de 1 s a 40 s, e é decisão de quem lê."""
        self.ler_ao_chegar = not self.ler_ao_chegar
        self._aba.estado.emit(
            "Virar a página com a mesa lê a folha que ainda não está no caderno."
            if self.ler_ao_chegar
            else "Virar a página com a mesa mostra a folha por ler, sem ler sozinha."
        )

    def folha_rasterizada(self) -> tuple[np.ndarray | None, int]:
        """A folha que o editor tem rasterizada e o DPI dela: é o que a vista da mesa destacada mostra (S-646)."""
        return self._aba._pagina_rgb, int(self._aba._dpi)

    @property
    def na_mesa(self) -> bool:
        """A aba está numa mesa -- a da janela principal ou a janela própria: ela acompanha a página do
        visualizador (S-644), mostra o bloco impresso sob o cursor (S-643) e avisa o bloco (S-642)."""
        return self._mesa_armada or self._destacada

    @property
    def destacada(self) -> bool:
        return self._destacada

    def definir_mesa(self, ligada: bool) -> None:
        """A janela armou ou desarmou a mesa. A aba passa a acompanhar a página, e a faixa aparece."""
        self._mesa_armada = bool(ligada)
        self.mostrar_impresso()
        self.avisar_bloco()

    def definir_destacada(self, destacada: bool) -> None:
        """A aba foi para a janela da mesa, ou voltou (S-646). Lá ela é mesa como na principal."""
        if bool(destacada) == self._destacada:
            return
        self._destacada = bool(destacada)
        self.mostrar_impresso()
        self.avisar_bloco()
        self._aba.destacada_mudou.emit(self._destacada)

    def folha_atual(self) -> tuple[int, int]:
        """A folha do visualizador (0-based) e quantas o livro tem; zero quando não há livro aberto."""
        total = self._aba.leitura.campo_de_folha.maximum() if self._aba._pdf is not None and self._aba.leitura.campo_de_folha.maximum() < texto_leitura.TETO_DE_FOLHAS else 0
        return self._aba._pagina_indice, int(total)

    def folha_por_ler(self) -> bool:
        """O editor está no vazio «Ler a folha N» da mesa (S-644), sem folha nem texto."""
        return self._aba._folha_por_ler is not None and self._aba._folha_por_ler == self._aba._pagina_indice

    def virar_folha(self, passo: int) -> bool:
        """A janela da mesa virou a folha (S-646): pede ao visualizador a vizinha, e a mesa a acompanha.

        É o mesmo caminho da página virada na janela principal: o visualizador vai à folha
        (`folha_pedida`), a janela devolve a página nova por `definir_livro`, e a aba guarda a folha
        que sai e abre a que entra (S-644). Devolve se havia para onde virar.
        """
        indice, total = self.folha_atual()
        alvo = mesa.folha_vizinha(indice, passo, total)
        if alvo is None:
            return False
        self._aba.folha_pedida.emit(alvo)
        return True

    def seguir_a_pagina(self, pagina: int) -> None:
        """A página do visualizador virou com a mesa armada (S-644).

        Guarda a folha que sai (S-611), abre a que entra do caderno se ela tiver (S-612), ou mostra o
        vazio «Ler a folha N» -- e **não** lê sozinha: ler custa de 1 s a 40 s, e é decisão de quem
        lê. Uma folha que não pôde ir ao caderno não sai da tela.
        """
        if self._aba.leitura.tarefa is not None or pagina == self._aba._folha_por_ler:
            return
        origem = self._aba.documento.origem
        if (
            origem is not None
            and int(origem.pagina) == pagina
            and chave_do_livro(origem.documento) == chave_do_livro(self._aba._pdf)
        ):
            return
        if not self.guardar_a_folha():
            self._aba.estado.emit("A folha na tela tem alterações que não foram ao caderno: ela fica, e só a página virou.")
            return
        if self._caderno is not None and self._caderno.estado(pagina) is not None and self.abrir_do_caderno(pagina):
            return
        self._mostrar_folha_por_ler(pagina)
        if self.ler_ao_chegar:
            self._aba.leitura.ler()

    def _mostrar_folha_por_ler(self, pagina: int) -> None:
        """O editor vazio, com o botão que lê **esta** folha."""
        self._aba._pagina = None
        self._aba._pagina_rgb = None
        self._aba.espelho.zerar_pilha()
        self._aba._caminho_do_documento = None
        self._aba._folha_por_ler = pagina
        self._aba.desenhar_documento(rico.DocumentoRico())
        self._aba._documento_gravado = self._aba.documento
        self._rascunho.stop()
        self._vai_ao_caderno = False
        self._aba._correcoes = 0
        self._aba.vista.mostrar_vazio()
        self._aba.vista.atualizar_status()

    def mostrar_impresso(self) -> None:
        """A faixa do bloco impresso (S-643): o recorte da folha do bloco sob o cursor, ou nada."""
        if not hasattr(self._aba, "faixa_impressa"):
            return
        doc = self._aba.documento
        folha = self._aba._pagina_rgb
        achado = None
        if self.na_mesa and self._faixa_ligada and folha is not None and doc.origem is not None:
            achado = self._sob_o_cursor()
            if achado is not None and isinstance(achado[0], BlocoDeDiagrama):
                achado = None
        imagem = None
        if achado is not None and folha is not None:
            imagem = texto_miniaturas.recorte_da_folha(folha, achado[0], dpi=self._aba._dpi)
        if achado is None or imagem is None:
            self._aba.faixa_impressa.hide()
            self._bloco_na_faixa = None
            self.recorte_na_faixa = None
            return
        chave = (*achado[1], id(folha))
        if chave == self._bloco_na_faixa and self._aba.faixa_impressa.isVisible():
            return
        self._bloco_na_faixa = chave
        self.recorte_na_faixa = imagem
        largura = max(1, self._aba.vista.area_da_folha().width())
        # A linha impressa fica com a altura de duas linhas de texto (S-643, etapa 2); o bloco inteiro,
        # quando a linha não se acha, com até um terço do editor, como antes.
        e_linha = achado[1][1] >= 0
        altura = 2 * self._aba.editor.fontMetrics().height() if e_linha else max(24, self._aba.editor.height() // 3)
        self._aba.faixa_impressa.setPixmap(
            pixmap_de_rgb(np.ascontiguousarray(imagem)).scaled(
                largura, altura, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        self._aba.faixa_impressa.show()

    def agendar_rascunho(self) -> None:
        """Reinicia o relógio: a folha é gravada alguns segundos depois da **última** edição.

        No caderno é a régua do WordCraft (2,5 s, e o cursor parado), sem ele os 4 s do rascunho.
        """
        self._mudou_em = self._aba._relogio()
        self._vai_ao_caderno = True
        espera = caderno.ESPERA_DA_MUDANCA if self._caderno is not None else rascunho.ESPERA_SEGUNDOS
        self._rascunho.start(int(espera * 1000))

    def _depois_da_pausa(self) -> None:
        """A pausa da digitação: o rascunho vai ao disco e, com a conferência ligada, o léxico se refaz.

        A tecla comum não redesenha a folha (é o caminho rápido de `_trocado`), então a palavra
        recém-escrita só era conferida no redesenho seguinte -- e a conferência ligada prometia o
        contrário (S-293). Reconferir a cada tecla seria carregar e varrer o léxico por letra; na
        pausa, uma vez, é o mesmo relógio do rascunho, e pelo mesmo motivo: quem parou de digitar
        é quem vai olhar a folha.

        No caderno, a pausa só grava com o cursor parado também; senão o relógio volta a contar o
        que falta (`caderno.espera_restante`).
        """
        if self._caderno is not None:
            falta = caderno.espera_restante(self._aba._relogio(), mudou_em=self._mudou_em, cursor_em=self._cursor_em)
            if falta > 0:
                self._rascunho.start(max(1, int(falta * 1000)))
                return
        self.guardar_a_folha()
        self._aba.correcao.refazer_navegacao()
        if self._aba.correcao.conferindo_lexico:
            self._aba.correcao.conferir_lexico(avisar=False)
        self._aba.vista.contar_correcoes()

    def gravar_rascunho(self) -> Path | None:
        """Grava o rascunho **se houver o que gravar**. Devolve o caminho, ou `None`.

        Só com alteração por gravar: reescrever o mesmo arquivo a cada quatro segundos é desgaste
        de disco por nada. E só com folha de origem -- documento sem folha não tem chave estável,
        e `rascunho.gravar` devolve `None` para ele.
        """
        self._rascunho.stop()
        if not self._aba.tem_alteracoes or self._aba._pagina is None:
            return None
        try:
            return rascunho.gravar(correcao.com_procedencia_humana(self._aba.documento), pasta=self._pasta_de_rascunhos)
        except OSError as erro:  # noqa: BLE001 - rascunho é rede de segurança, não função
            logger.debug("Rascunho não pôde ser gravado: %s", erro)
            return None

    def oferecer_rascunho(self, pagina: PaginaLida) -> bool:
        """Se houver rascunho daquela folha, **oferece** recuperá-lo. Devolve se recuperou.

        Oferece e não aplica: sobrescrever o que a pessoa acabou de ler com um rascunho de ontem é
        o contrário do que ela quer. E recusar **não apaga** -- na próxima abertura a oferta volta.
        Sem tela não há quem responda, e a resposta que não perde nada é a mesma: o rascunho fica.
        """
        from chess_diagram_ocr.qt import dialogos

        achado = rascunho.achar(pagina.documento, pagina.pagina, pasta=self._pasta_de_rascunhos)
        if achado is None:
            return False
        if not dialogos.ha_quem_responda():
            logger.warning("Há um rascunho da folha %d e nenhuma tela para oferecê-lo: ele fica.", pagina.pagina + 1)
            return False
        resposta = QMessageBox.question(
            self._aba,
            "Texto",
            rascunho.frase_de_recuperacao(achado),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return False
        return self._recuperar(achado, pagina)

    def recuperar_rascunho(self) -> bool:
        """Pelo menu do botão direito (item 25): o rascunho da folha na tela, para quem recusou a
        oferta na leitura e mudou de ideia -- sem ter de ler a folha de novo (até 40 s) para a
        pergunta voltar. Pergunta antes de descartar o que foi editado desde então."""
        if self._aba._pagina is None:
            return False
        achado = rascunho.achar(self._aba._pagina.documento, self._aba._pagina.pagina, pasta=self._pasta_de_rascunhos)
        if achado is None:
            self._aba.estado.emit("Não há rascunho desta folha por recuperar.")
            return False
        if not self.confirmar_descarte("Recuperar o rascunho descarta as alterações."):
            return False
        return self._recuperar(achado, self._aba._pagina)

    def _recuperar(self, achado: rascunho.Rascunho, pagina: PaginaLida) -> bool:
        """Põe o rascunho na tela como trabalho por gravar e apaga o arquivo dele."""
        try:
            doc = rascunho.carregar(achado)
        except (OSError, ValueError) as erro:  # `arquivo.ArquivoInvalido` é um `ValueError`
            logger.debug("Rascunho não abriu (%s): %s", achado.caminho, erro)
            self._aba.estado.emit(f"O rascunho não pôde ser aberto: {erro}")
            return False
        # A folha é a que acabou de ser lida: a imagem dela serve, e não se renderiza de novo.
        self.abrir(doc, folha_rgb=self._aba._pagina_rgb)
        # **Recuperado é trabalho por gravar, e não trabalho gravado (S-308).** `abrir` iguala o
        # gravado ao que está na tela -- o certo para um arquivo do disco, e o errado para este,
        # que veio de um arquivo que a linha seguinte apaga. Sem isto, o texto resgatado de um
        # travamento voltaria a existir só na memória: as guardas que perguntam antes de descartar
        # passariam direto, e `gravar_rascunho` sairia sem reescrever nada. O segundo travamento
        # perderia tudo -- e o recurso existe exatamente para o segundo travamento.
        self._aba._documento_gravado = rico.de_pagina(pagina)
        # Recuperado é trabalho que chegou a um lugar melhor -- a tela --, e o arquivo sai.
        rascunho.descartar(pagina.documento, pagina.pagina, pasta=self._pasta_de_rascunhos)
        self.agendar_rascunho()
        self._aba.estado.emit(f"Rascunho de {achado.data_legivel} recuperado.")
        return True

    def confirmar_descarte(self, o_que: str, *, ao_fechar: bool = False) -> bool:
        """Pergunta antes de jogar fora o que foi editado e não foi gravado. Sem isso, não pergunta.

        **Sem tela não há quem responda** (`dialogos.ha_quem_responda`), e a resposta é a mesma de
        `dialogos.perguntar_descarte`: fechar fecha -- não há o que fazer com uma janela que já
        está sendo destruída --, e ler ou abrir outra folha **não** descarta, que é a resposta que
        não perde nada. As duas ficam no log.
        """
        from chess_diagram_ocr.qt import dialogos

        if not self._aba.tem_alteracoes:
            return True
        if not dialogos.ha_quem_responda():
            logger.warning(
                "O texto da aba Texto tem alterações não gravadas e nenhuma tela para perguntar: %s.",
                "o fechamento segue" if ao_fechar else "as alterações ficam",
            )
            return ao_fechar
        onde = "da aba Texto" if ao_fechar else "desta aba"
        resposta = QMessageBox.question(
            self._aba,
            "Texto",
            f"O texto {onde} foi editado e não foi gravado. {o_que} Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return resposta == QMessageBox.StandardButton.Yes

    # ------------------------------------------------------------ os rascunhos do livro (item 18)

    def anunciar_rascunhos(self, livro: Path | None) -> None:
        """Na troca de livro, diz quantos rascunhos dele há por recuperar e em que folhas (item 18).

        A oferta de recuperação (S-255) só acontece ao ler a folha certa: quem fecha o programa
        com três folhas corrigidas e volta no dia seguinte não tinha como saber que elas existem,
        nem quais são. Rodapé e não caixa: é informação, e a decisão continua sendo ler a folha.
        """
        if livro is None:
            return
        try:
            achados = rascunho.listar(livro, pasta=self._pasta_de_rascunhos)
        except OSError as erro:  # noqa: BLE001 - a lista é conforto; o livro abre igual
            logger.debug("Rascunhos de %s não listados: %s", livro, erro)
            return
        if not achados:
            return
        folhas = ", ".join(str(r.folha + 1) for r in achados[:6]) + ("…" if len(achados) > 6 else "")
        self._aba.estado.emit(
            f"{len(achados)} rascunho(s) deste livro por recuperar (folha {folhas}): "
            "leia a folha e a aba oferece."
        )

    # ---------------------------------------------------- o menu do caderno (S-611, S-612, S-616)

    def menu_do_caderno(self, menu: QMenu) -> None:
        """O que o caderno sabe fazer com a folha da tela (S-611, S-612, S-616).

        No menu do botão direito, e não no catálogo, até a fita (S-650) e o índice (S-613) lhes darem
        lugar: são gestos sobre **esta** folha, e o menu dela é onde a pessoa os procura.
        """
        cad = self.caderno_da_tela()
        if cad is None or cad.somente_leitura:
            return
        pagina = int(self._aba.documento.origem.pagina)  # type: ignore[union-attr]
        guardada = cad.estado(pagina)
        menu.addSeparator()
        acoes: list[tuple[str, Callable[[], object]]] = [("Ler a folha de novo", self._aba.leitura.ler_de_novo)]
        if cad.caminho(pagina, tipo="anterior").exists():
            acoes.append(("Voltar à versão anterior desta folha", self.voltar_a_anterior))
        if cad.caminho(pagina, tipo="suite").exists():
            acoes.append(("Abrir a versão da Revisão de texto", self.abrir_a_da_revisao))
        if cad.caminho(pagina, tipo="lida").exists() and (guardada is None or guardada.correcoes or self._aba._correcoes):
            acoes.append(("Descartar as correções desta folha", self.descartar_correcoes))
        if guardada is not None:
            conferida = guardada.estado == caderno.CONFERIDA
            acoes.append(("Desmarcar a folha como conferida" if conferida else "Marcar a folha como conferida", self.marcar_conferida))
        for rotulo, alvo in acoes:
            acao = QAction(rotulo, menu)
            acao.triggered.connect(lambda _marcado=False, alvo=alvo: alvo())
            menu.addAction(acao)
