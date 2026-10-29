"""A aba de texto no Qt: a página inteira num editor, com os diagramas onde eles estão (S-211/S-504).

**Quase nada é decidido aqui**, e é a mesma frase do cabeçalho de `ui/texto_panel.py`. Onde o
diagrama entra no fluxo, o que merece destaque e o que vai para o arquivo são de
`text/documento.py`; o que a edição faz com um trecho é de `text/rico.py`; o que a busca acha é de
`text/busca.py`. Nenhum dos três importa toolkit nenhum. Este arquivo é o que sobra: widgets, uma
thread e o vaivém entre o deslocamento do documento e a posição do cursor.

---

**O que o porte apagou, e vale medir.** `ui/texto_panel.py` tem 2.600 linhas, e uma parte delas
existe só para contornar o `tk.Text`:

- **as etiquetas combinadas de fonte.** Uma etiqueta do Tk dá **uma** fonte ao trecho, e a última
  criada vence -- daí `NEGRITO_ITALICO`, daí `fonte:titulo:bi:2` gerada sob demanda, daí o cache
  `_fontes_desenhadas` refeito a cada zoom. `QTextCharFormat` guarda peso, pendor e corpo
  separados, e os três somem. Ver `qt/texto_formato.py`.
- **`edit_reset()` depois de todo redesenho.** A pilha de desfazer do Tk guarda **índice**, não
  conteúdo: trocar o texto inteiro e não zerá-la faria o desfazer apagar um pedaço qualquer do
  texto novo. Aqui a pilha é o próprio histórico de documentos, e redesenhar não a corrompe.
- **a leitura do documento de volta do widget**, etiqueta por etiqueta, para gravar -- era
  `ui/texto_etiquetas.de_despejo`, e ela saiu junto com o toolkit (S-506). Aqui o documento
  **é** o estado; o widget é só o desenho dele.

O que **não** muda é a fronteira: toda ferramenta chama uma função pura de `rico`, recebe um
documento novo e o redesenha. É o que faz o negrito sobreviver ao arquivo em vez de existir só
enquanto o widget existir.

**O deslocamento é a fronteira estreita.** As funções puras falam em deslocamento de caractere do
*documento*; o `QTextEdit` fala em posição do *cursor*. Os dois divergem porque a miniatura do
diagrama vale um caractere para o Qt e nenhum para o documento -- exatamente o que
`ui/texto_etiquetas.deslocamento` resolvia do outro lado, percorrendo o `dump` do widget a cada
pergunta. Ver `_Mapa`.

**A digitação atravessa a mesma fronteira, no outro sentido.** O editor é editável, e o que se
digita nele acontece primeiro no widget. O porte deixou só essa metade: a letra ficava na tela e
fora do documento, e o primeiro redesenho -- o negrito seguinte, o `Ctrl+Z`, o zoom -- a apagava
sem dizer nada; gravar e exportar levavam a folha de antes. Agora cada mudança do texto chega por
`QTextDocument.contentsChange` e vira uma função pura de `rico` (`editar`, `mover`), pela mesma
tradução de `_Mapa`. Quem decide o que a tecla faz com a corrida -- de quem herda, que faixa leva, o
que acontece com a marca do diagrama -- é `rico`; quando a tecla fecha um passo de desfazer é
`ui/texto_declarado`. Aqui fica o vaivém -- e **sem redesenho por tecla**: o widget já tem a letra,
o mapa anda junto com ela e só o trecho digitado é repintado. Redesenhar a folha inteira, com as
miniaturas, é o que o portão de bloqueio da thread da janela não deixaria passar a cada tecla.

**O diagrama é recorte da folha, e a folha vem da leitura.** `ler_pagina` rasteriza a página para
ler o texto, e a miniatura de cada `[Diagrama N]` é o pedaço dessa mesma imagem no `bbox` do bloco
-- em pontos, convertidos pelo mesmo DPI dos dois lados (`_recorte_da_folha`). O porte inicial
descartava a imagem na volta da thread, e a aba mostrava a marca sem figura nenhuma; agora a folha
é rasterizada **uma vez**, na thread de trabalho (S-352), entregue a `ler_pagina` por `imagem_rgb`
e guardada para as miniaturas, para os recortes da exportação (`_gravar_recortes`, S-338) e para o
`.cvtxt` reaberto, que a refaz do livro se ele ainda estiver onde estava (`abrir`). O rascunho
automático (S-255) e a procedência humana ao gravar (S-239) vieram no mesmo movimento: eles moram
em `text/rascunho.py` e `text/correcao.py`, e aqui ficam só o relógio de inatividade e a pergunta.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path
from typing import Any, cast

import numpy as np
from PyQt6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QHelpEvent,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPixmap,
    QShortcut,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextDocumentFragment,
    QTextFormat,
    QTextImageFormat,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.qt import atalhos as qt_atalhos
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.barra import BarraFluida
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.fita_do_texto import FitaDoTexto
from chess_diagram_ocr.qt.imagens import pixmap_de_rgb
from chess_diagram_ocr.qt.painel_de_navegacao import CORRECOES, FOLHAS, RESULTADOS, PainelDeNavegacao
from chess_diagram_ocr.qt.texto_formato import bloco_de, formato_de
from chess_diagram_ocr.qt.trabalho import Tarefa, rastro_de
from chess_diagram_ocr.qt.vazio import EstadoVazio
from chess_diagram_ocr.text import busca, caderno, correcao, rascunho, rico
from chess_diagram_ocr.text.documento import PaginaLida
from chess_diagram_ocr.text.pagina import BlocoDeDiagrama, BlocoDeTexto
from chess_diagram_ocr.ui import atalhos, comandos, espaco, estilos, mesa, strings, texto_cores, tipografia, tokens
from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken
from chess_diagram_ocr.ui.texto_declarado import (
    ACOES_PROPRIAS,
    COMANDOS_DA_ABA,
    DIAGRAMAS_A_ESQUERDA,
    DIAGRAMAS_AO_CENTRO,
    FAMILIA_DA_LETRA_PADRAO,
    FAMILIAS_DA_LETRA,
    MOTORES,
    NOME_DA_FAMILIA,
    NOME_DO_TAMANHO,
    TAMANHO_DA_MINIATURA_PADRAO,
    TAMANHOS_DA_MINIATURA,
    ZOOM_MAXIMO,
    ZOOM_MINIMO,
    Digitacao,
    alinhamento_dos_diagramas,
    codigo_unicode,
    contar_palavras,
    continua_a_digitacao,
    digitacao_depois,
    fora_do_livro,
    frase_das_palavras,
    frase_do_lexico,
    frase_do_rodape,
    largura_da_miniatura,
    paradas_do_zoom,
    porcentagem_do_zoom,
    proxima_familia_da_letra,
    proximo_tamanho_da_miniatura,
)

logger = logging.getLogger(__name__)

__all__ = ["CANCELADA", "LARGURA_DA_MINIATURA", "JanelaDeBusca", "PainelDeTexto"]

CANCELADA = "exportação cancelada pela pessoa"
"""O que a tarefa de exportação devolve quando a pessoa desistiu (F9-C2, §7 item 7).

Um valor de retorno e não uma exceção: desistir não é falhar, e uma exceção cairia em
`_exportacao_falhou`, que abre caixa vermelha. O `\u0001` na frente é o que impede uma frase de
relatório legítima de coincidir com ela."""

LARGURA_DA_MINIATURA = TAMANHOS_DA_MINIATURA[TAMANHO_DA_MINIATURA_PADRAO]
GLIFOS_RECENTES = 20
"""Quantos glifos usados por último a paleta mostra primeiro (S-650), gravados no estado da sessão."""

SEGUNDOS_DO_RECADO = 6.0
"""Quanto o recado transitório fica na barra de estado (S-655): a regra do WordCraft. O texto
inteiro fica na dica, para quem não o leu a tempo."""
"""A miniatura do diagrama dentro do texto, em pixel.

Grande o bastante para reconhecer a posição, pequena o bastante para a linha seguinte caber na
tela. É o mesmo alvo de `texto_panel._miniatura`."""

TETO_DE_FOLHAS = 9999
"""O teto do campo \u00abFolha a ler\u00bb enquanto a aba n\u00e3o sabe quantas folhas o livro tem (item 15)."""

OBJETO = "\ufffc"
"""Como o texto do widget conta a miniatura: um caractere que **nunca** entra no documento.

Chega também colado: o texto que o `QTextEdit` põe na área de transferência traz a miniatura
copiada como este caractere solto, sem imagem nenhuma atrás dele."""

TECLAS_DO_HISTORICO: tuple[str, ...] = ("desfazer", "refazer")
"""As ações cuja tecla, **dentro do editor**, é deste painel e não do `QTextEdit`.

A guarda de atalhos cede `Ctrl+Z` a todo campo de texto (`ui/atalhos.ACOES_DO_CAMPO`), porque o
campo tem o desfazer dele -- e este não tem: ele está desligado de propósito (ver `_montar`). Sem
pegar a tecla aqui, `Ctrl+Z` no meio da folha chegaria a um desfazer desligado e não faria nada.
A tecla sai da tabela (`ui/atalhos.por_acao`), e não daqui."""


@dataclass(frozen=True)
class _Trecho:
    """Onde uma corrida caiu no widget: começo no documento, começo no Qt, tamanho."""

    documento: int
    janela: int
    tamanho: int


class _Mapa:
    """A tradução entre o deslocamento do documento e a posição do cursor do Qt.

    **Os dois divergem, e a razão é a mesma do Tk.** A miniatura do diagrama é um caractere para o
    widget e nenhum para o documento; a quebra que o desenho acrescenta embaixo dela também não é
    do documento. Contar `len` do texto do widget erraria as duas, e o erro cresce a cada diagrama
    -- numa folha de nove, o negrito aplicado no fim cairia nove caracteres adiante.

    A tabela é construída no desenho, que é o único momento em que se sabe as duas coordenadas ao
    mesmo tempo. Era o papel de `ui/texto_etiquetas.deslocamento`, com a diferença de que lá ele
    era recalculado a cada pergunta, percorrendo o `dump` inteiro do widget.
    """

    def __init__(self) -> None:
        self._trechos: list[_Trecho] = []
        self._fim_documento = 0

    def registrar(self, documento: int, janela: int, tamanho: int) -> None:
        if tamanho > 0:
            self._trechos.append(_Trecho(documento, janela, tamanho))
            self._fim_documento = max(self._fim_documento, documento + tamanho)

    def registrar_texto(self, documento: int, janela: int, texto: str) -> None:
        """Registra `texto`, escrito em `janela`, **contando como o Qt conta**: em unidades UTF-16.

        A letra fora do plano básico (`U+1F5F8`, que o OCR às vezes devolve) é **uma** no documento e
        **duas** no Qt, que guarda o par substituto. Um trecho só com `len(texto)` deixava toda posição
        depois dela deslocada de uma -- a letra digitada ia ao lugar certo no documento e a tela era
        lida no vizinho. Ela vira um trecho próprio de tamanho 1, e a metade de baixo do par fica no
        vão entre dois trechos, que `deslocamento` já resolve para o começo do seguinte.
        """
        comeco = 0
        andado = 0
        for k, letra in enumerate(texto):
            if ord(letra) <= 0xFFFF:
                continue
            self.registrar(documento + comeco, janela + andado, k - comeco)
            andado += k - comeco
            self.registrar(documento + k, janela + andado, 1)
            andado += 2
            comeco = k + 1
        self.registrar(documento + comeco, janela + andado, len(texto) - comeco)

    def limpar(self) -> None:
        self._trechos.clear()
        self._fim_documento = 0

    def deslocamento(self, posicao: int) -> int:
        """Da posição do cursor para o deslocamento do documento.

        Uma posição que caia **numa** miniatura -- entre dois trechos -- resolve para o começo do
        trecho seguinte: o cursor está antes do texto que vem depois da imagem, e é ali que uma
        inserção deve cair.
        """
        for trecho in self._trechos:
            if trecho.janela <= posicao < trecho.janela + trecho.tamanho:
                return trecho.documento + (posicao - trecho.janela)
            if posicao < trecho.janela:
                return trecho.documento
        return self._fim_documento

    def posicao(self, deslocamento: int) -> int:
        """A inversa. Deslocamento além do fim resolve para o fim do último trecho."""
        for trecho in self._trechos:
            if trecho.documento <= deslocamento < trecho.documento + trecho.tamanho:
                return trecho.janela + (deslocamento - trecho.documento)
        if not self._trechos:
            return 0
        ultimo = self._trechos[-1]
        return ultimo.janela + ultimo.tamanho

    def trocar(self, janela: int, removidos: int, deslocamento: int, tamanho: int) -> None:
        """Acompanha uma digitação **fiel**, sem redesenho: `removidos` saíram em `janela`, `tamanho` entraram.

        Fiel é a troca em que todo caractere que saiu e todo que entrou é do documento -- nenhuma
        miniatura, nenhuma quebra do desenho. Aí as duas coordenadas andam juntas: o que está antes
        da troca não se mexe, o que está depois anda o mesmo tanto nas duas, e o texto novo vira um
        trecho em `(deslocamento, janela)`. Os trechos que ficam colados nas duas coordenadas se
        fundem de novo -- sem isso cada tecla deixaria um trecho de uma letra, e a tabela que se
        percorre a cada pergunta cresceria com a digitação.
        """
        fim = janela + removidos
        passo = tamanho - removidos
        novos: list[_Trecho] = []
        for trecho in self._trechos:
            termino = trecho.janela + trecho.tamanho
            if termino <= janela:
                novos.append(trecho)
                continue
            if trecho.janela >= fim:
                novos.append(_Trecho(trecho.documento + passo, trecho.janela + passo, trecho.tamanho))
                continue
            if trecho.janela < janela:
                novos.append(_Trecho(trecho.documento, trecho.janela, janela - trecho.janela))
            if termino > fim:
                corte = fim - trecho.janela
                novos.append(_Trecho(trecho.documento + corte + passo, fim + passo, termino - fim))
        if tamanho > 0:
            novos.append(_Trecho(deslocamento, janela, tamanho))
        novos.sort(key=lambda trecho: trecho.janela)
        self._trechos = []
        for trecho in novos:
            anterior = self._trechos[-1] if self._trechos else None
            if (
                anterior is not None
                and anterior.documento + anterior.tamanho == trecho.documento
                and anterior.janela + anterior.tamanho == trecho.janela
            ):
                self._trechos[-1] = _Trecho(anterior.documento, anterior.janela, anterior.tamanho + trecho.tamanho)
                continue
            self._trechos.append(trecho)
        ultimo = self._trechos[-1] if self._trechos else None
        self._fim_documento = ultimo.documento + ultimo.tamanho if ultimo is not None else 0


class PainelDeTexto(QWidget):
    """O editor da página lida: desenha o documento e devolve cada gesto a `text/rico.py`."""

    estado = pyqtSignal(str)
    """Uma frase para a barra de status."""

    documento_mudou = pyqtSignal()
    """A folha foi editada. A janela usa para saber que há o que gravar."""

    diagrama_ativado = pyqtSignal(int, int)
    """Duplo clique numa miniatura: `(folha 0-based, índice do diagrama)`. A janela leva o
    diagrama à sala de estudo, como o duplo clique na caixa do visualizador (item 8)."""

    bloco_destacado = pyqtSignal(object)
    """O `bbox`, em pontos, do bloco da página de onde veio o trecho sob o cursor -- ou `None` (S-642).
    A mesa o contorna no visualizador. Sai só quando o bloco muda, e não a cada tecla."""

    foco_mudou = pyqtSignal(bool)
    """O modo foco ligou ou desligou (S-658): a mesa esconde ou devolve o visualizador."""

    destacada_mudou = pyqtSignal(bool)
    """A aba foi para a janela da mesa ou voltou dela (S-646): a janela principal rearruma o divisor."""

    folha_pedida = pyqtSignal(int)
    """Um `.cvtxt` do livro aberto acabou de entrar na tela: a folha dele (0-based), para o
    visualizador ir até ela (item 9). Não sai para um `.cvtxt` de outro livro."""

    def __init__(
        self,
        *,
        pdf: Path | None = None,
        pagina: int = 0,
        dpi: int | None = None,
        busy: BusyRegistry | None = None,
        pasta_de_rascunhos: Path | None = None,
        pasta_de_cadernos: Path | None = None,
        com_caderno: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._busy = busy
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
        self._livro_do_caderno: Path | None = None
        self._vai_ao_caderno = False
        """A folha da tela é trabalho do caderno: lida pelo motor, aberta dele ou editada. Um
        `.cvtxt` avulso aberto e não tocado não é -- abri-lo para olhar não troca a folha do caderno
        (S-616)."""
        self._rascunho = QTimer(self)
        """O relógio de **inatividade** do rascunho: cada edição o reinicia, e ele grava alguns
        segundos depois da última (S-255). Um relógio fixo gravaria no meio da digitação."""
        self._rascunho.setSingleShot(True)
        self._rascunho.setInterval(int(rascunho.ESPERA_SEGUNDOS * 1000))
        self._rascunho.timeout.connect(self._depois_da_pausa)
        """O registro de ocupação (S-112). `None` é a aba montada sozinha num teste.

        **As duas operações longas desta aba precisam estar nele**, e no corte do Tk elas quase
        não ficaram: o painel de lá registrava as duas, e o porte inicial não. Ler uma folha é
        dezenas de segundos com o motor glifo, e exportar um PDF pesquisável abre o livro inteiro
        -- fechar a janela no meio de qualquer uma delas joga fora trabalho que não volta de
        graça, e o rodapé só sabe perguntar sobre o que está registrado."""
        self._ocupado: BusyToken | None = None
        self._pdf = pdf
        self._pagina_indice = pagina
        self._dpi_fixo = dpi
        """O DPI cravado por quem montou o painel -- o teste, que dá a folha sintética. `None` é o
        produto: a leitura pergunta às Configurações (`ui/configuracoes.dpi`), como o visualizador
        e a leitura dos diagramas fazem, em vez de um 220 cravado que ignorava a janela
        «Ferramentas ▸ Configurações…»."""
        self._dpi = dpi or 220
        """O DPI da folha que está na tela -- o que liga ponto a pixel nos recortes. Muda quando
        uma folha chega (leitura ou arquivo), e **não** quando a configuração muda: a folha já
        renderizada continua na escala em que foi renderizada."""
        self._pagina: PaginaLida | None = None
        self._pagina_rgb: np.ndarray | None = None

        self.documento = rico.DocumentoRico()
        """**O estado é o documento, e não o widget.** É a diferença de fundo com o lado do Tk,
        onde gravar exigia reler o `dump` do editor etiqueta por etiqueta (`de_despejo`)."""
        self._documento_gravado = self.documento
        """O documento como está no disco -- ou como a leitura o entregou. É contra ele que
        `tem_alteracoes` compara, e não contra a pilha: gravar não esvazia a pilha, e desfazer até
        o que foi gravado não deixa nada a perder."""
        self._historico: list[rico.DocumentoRico] = []
        self._rotulos_do_historico: list[str] = []
        """O nome do passo de cada documento empilhado (S-656), na mesma ordem de `_historico`."""
        self._rotulos_refeitos: list[str] = []
        self._rotulo_corrente = ""
        """O nome do comando em curso: `executar` o põe, e `_aplicar` o leva para a pilha."""
        self._executor: Callable[[str], object] | None = None
        self._edicao = 0
        """Quantas edições esta aba recebeu. É o desempate do `Ctrl+Z` sem foco (S-243)."""
        self._refeitos: list[rico.DocumentoRico] = []
        self._mapa = _Mapa()
        self._redesenhando = False
        self._tarefa: Tarefa | None = None
        self._caminho_do_documento: Path | None = None
        self._zoom_da_vista = 0
        self._conferindo_lexico = False
        """**Ligar, e não marcar uma vez** (S-293). Toda ferramenta que muda texto redesenha, e o
        redesenho apaga a marcação inteira -- então corrigir a primeira palavra marcada apagava as
        outras, e a pessoa tinha de reconferir a cada correção. Com o interruptor, a conferência se
        refaz sozinha depois de cada redesenho."""
        self._janela_de_busca: QWidget | None = None
        self._paleta: object | None = None
        self._motor = MOTORES[0]
        """O motor de leitura. O primeiro da lista é o padrão, e a S-423 explica por que ele é o
        `auto` e não o `glifo`."""
        self._modo_bloco = False
        self._tela = ""
        """O texto do widget na última mudança vista -- o `antes` de cada tecla. `contentsChange`
        diz onde mudou; é comparando com isto que se sabe **o que** saiu, e se o Qt disse a
        verdade sobre onde."""
        self._digitacao: Digitacao | None = None
        """O passo de desfazer que a digitação deixou aberto. Toda ferramenta o fecha."""
        self._relogio: Callable[[], float] = time.monotonic
        """De onde vem o "agora" da pausa que fecha o passo. Atributo para o teste poder parar o
        tempo -- esperar um segundo de verdade numa suíte é o teste que ninguém quer rodar."""
        self._mudou_em = 0.0
        self._cursor_em = 0.0
        """Quando o documento mudou e quando o cursor mexeu pela última vez: a régua do salvamento
        no caderno pede os dois parados (`caderno.espera_restante`, S-612)."""
        self._leitura_de: tuple[str, bool] = ("", False)
        self._diagramas = DIAGRAMAS_AO_CENTRO
        """«Diagramas no texto» (S-620). É vista e preferência, e não documento: trocar não grava nada."""
        self._tamanho_da_miniatura = TAMANHO_DA_MINIATURA_PADRAO
        """O tamanho da miniatura (S-623): `ui/texto_declarado.TAMANHOS_DA_MINIATURA`."""
        self._familia_da_letra = FAMILIA_DA_LETRA_PADRAO
        """A letra de leitura (S-632): `ui/texto_declarado.FAMILIAS_DA_LETRA`. Vista, como o zoom."""
        self._texto_ao_lado = False
        """O texto contorna o diagrama que se desenha à esquerda (S-624). Vista, como a preferência da S-620."""
        self._pincel: rico.Atributos | None = None
        """A formatação que o pincel leva (S-653), ou `None` desarmado."""
        self._pincel_fixo = False
        self._pincel_armado_em = 0.0
        self._modo_foco = False
        self._navegacao_antes_do_foco = False
        self._marcas_de_formatacao = False
        self._faixa_ligada = True
        self._fora_do_lexico: list[tuple[int, int]] = []
        """As palavras marcadas pela conferência, em ordem -- o `F7` anda por elas (S-657)."""
        self._ignoradas: set[str] = set()
        """As palavras que a pessoa mandou ignorar nesta folha. Saem com a folha."""
        self._glifos_recentes: list[str] = []
        self._palavras_cache: tuple[object, int] = (None, 0)
        self._ultimas_cores: dict[str, str] = {"letra": texto_cores.nomes()[0], "realce": texto_cores.nomes()[0]}
        """A última cor de letra e de realce aplicadas pelos botões partidos (S-650), guardadas na sessão."""
        self._ler_ao_chegar = False
        """Ler a folha sem caderno ao chegar a ela pela mesa (S-644). Ver `alternar_ler_ao_chegar`."""
        self._mesa_armada = False
        """A mesa de texto da janela principal está armada (S-640). Quem diz é a janela, por `definir_mesa`."""
        self._destacada = False
        """A aba está na janela da mesa (S-646). Quem diz é `MesaDestacada`, por `definir_destacada`."""
        self._bloco_avisado: tuple[float, ...] | None = None
        self._folha_por_ler: int | None = None
        """A folha que a mesa mostrou sem texto, porque ela não está no caderno (S-644)."""
        self._bloco_na_faixa: tuple[int, ...] | None = None
        self.recorte_na_faixa: np.ndarray | None = None
        """O recorte da folha que a faixa do bloco impresso mostra, antes da escala (S-643)."""
        self._folha_pedida_ao_fundo: int | None = None
        self._renderizacao: Tarefa | None = None
        """A folha do caderno sendo rasterizada ao fundo, para as miniaturas (`_renderizar_ao_fundo`)."""
        """O motor e o modo bloco da leitura em curso, como eram quando ela partiu."""
        self._sincronizando = False
        """O painel está repintando o que acabou de ser digitado: a mudança de formato que isso
        gera não é digitação."""
        self._base: tuple[int, str, str] | None = None
        """A fonte de base do último desenho. O trecho digitado é pintado com **a mesma** -- a
        tecla não relê as famílias do sistema, e o redesenho seguinte não muda o que já estava."""
        self._correcoes = 0
        """Quantas correções a mão fez sobre o que o motor leu, contadas na pausa e na gravação
        (item 24). Não a cada tecla: `correcao.correcoes` compara bloco a bloco por `difflib`."""
        self._fornecedor_de_folha: Callable[[int], tuple[np.ndarray, int] | None] | None = None
        """Quem já tem a folha rasterizada -- o visualizador --, perguntado antes de rasterizar
        de novo (item 28). `None` é a aba sozinha, que renderiza por conta própria."""
        self._posicoes: dict[tuple[str, int], tuple[str, ...]] = {}
        """O campo de peças de cada diagrama, por `(livro, folha)`, como o OCR de diagramas do
        produto leu. Por folha porque a leitura dos diagramas e a do texto chegam em qualquer
        ordem; **por livro** porque a folha 14 de um livro não é a folha 14 do outro -- com a chave
        só pela folha, trocar de livro levava as posições do anterior para as folhas do novo
        (item 11). `definir_livro` para outro livro esquece tudo."""
        self._documento_ao_ler: rico.DocumentoRico | None = None
        """O documento na tela quando a leitura em curso partiu. Ver `_leitura_terminou`."""
        self._montado = False
        """O `_montar` terminou? Até lá o filtro de eventos deixa tudo passar: ver `eventFilter`."""

        self._montar()
        self._montado = True
        self._desenhar()
        # Toda edição -- tecla ou ferramenta -- reinicia o relógio do rascunho. É o único ouvinte
        # deste sinal dentro do painel; o `desenhar_documento` de uma folha recém-lida também o
        # emite, e aí `gravar_rascunho` não grava: não há alteração.
        self.documento_mudou.connect(self._agendar_rascunho)
        self.documento_mudou.connect(self._atualizar_status)
        self.editor.cursorPositionChanged.connect(self._anotar_cursor)
        self.campo_de_folha.valueChanged.connect(lambda _valor: self._rotular_leitura())
        atalhos.conferir_dono(self, "PainelDeTexto")

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        caixa = QVBoxLayout(self)
        caixa.setContentsMargins(*(espaco.margem_da_aba(),) * 4)
        caixa.setSpacing(espaco.linha())
        self._montar_controles()
        self.fita = FitaDoTexto(
            self,
            alvo=self._alvo_da_fita,
            controles={
                "@corpo": self.caixa_de_corpo,
                "@cor": self.escolha_de_cor,
                "@realce": self.escolha_de_realce,
                "@cor_rapida": self.cor_rapida,
                "@realce_rapido": self.realce_rapido,
                "@galeria": self.galeria,
                "@folha": self.campo_de_folha,
                "@motor": self.escolha_de_motor,
                "@modo_bloco": self.caixa_de_bloco,
            },
            rotulos_do_desfazer=lambda: list(reversed(self._rotulos_do_historico)),
            desfazer_ate=self.desfazer_ate,
        )
        self.botao_de_ler = self.fita.botao("ler_folha")
        caixa.addWidget(self.fita)
        # A barra fina do modo foco (S-658): o que sobra no lugar da fita, e como sair dele.
        self.barra_do_foco = QLabel(strings.MODO_FOCO_BARRA, self)
        self.barra_do_foco.setAccessibleName("Modo foco")
        self.barra_do_foco.hide()
        caixa.addWidget(self.barra_do_foco)
        # O bloco impresso sob o cursor, na largura do editor (S-643): quem corrige OCR compara a
        # letra impressa e a lida sem atravessar a tela com os olhos. Só na mesa, e só com a folha.
        self.faixa_impressa = QLabel(self)
        self.faixa_impressa.setAccessibleName("Bloco impresso sob o cursor")
        self.faixa_impressa.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.faixa_impressa.hide()
        caixa.addWidget(self.faixa_impressa)

        self.editor = QTextEdit(self)
        self.editor.setAccessibleName("Folha transcrita")
        # O `Tab` sai da folha, como da caixa do comentário do Estudo. Guardado pelo editor, ele
        # escrevia uma tabulação no texto e a tecla nunca passava dali: quem anda pelo teclado não
        # alcançava o resto da aba (OCR_UI ciclo 2, fase 5, crítico do ciclo 4, portão `teclado`).
        # A tabulação que precisar entrar na folha entra colada.
        self.editor.setTabChangesFocus(True)
        self._corpo_de_base = self.editor.font().pointSize()
        """O corpo da fonte antes de qualquer zoom da vista. `aplicar_zoom` soma o degrau **a
        ele**, e não ao que está na tela -- somar ao desenhado acumularia o degrau anterior a cada
        chamada, e a letra cresceria sozinha."""
        self.editor.setAcceptRichText(False)
        # O menu do botão direito é o do próprio editor, mais o que a miniatura sabe fazer (item 10).
        self.editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.editor.customContextMenuRequested.connect(self._abrir_menu_de_contexto)
        # **O estado vazio deixou de ser `placeholderText`** (F9-C2, §7 item 3). A frase continua
        # sendo texto de interface e continua em `ui/strings.py`; o que mudou é o desenho:
        # `placeholderText` não elide **nem quebra linha**, e o crítico do ciclo 1 mediu a dica
        # **cortada em 77 px** em toda janela de 1280 px ou menos -- inclusive no tamanho mínimo,
        # ou seja, num tamanho em que ela nunca é legível. `EstadoVazio` quebra linha, tem título
        # e traz o botão que resolve para dentro do vazio. Ele é sobreposto ao editor e some no
        # primeiro caractere, então continua sem ser exportado com a folha.
        self.editor.setUndoRedoEnabled(False)
        """**O desfazer do Qt fica desligado de propósito.** A pilha deste painel é de
        *documentos* (`rico.DocumentoRico`), e não de edições de texto: uma ferramenta de formato
        não muda um caractere, e o desfazer nativo não a veria. Duas pilhas dariam um `Ctrl+Z` que
        às vezes desfaz o negrito e às vezes a palavra."""
        self.vazio = EstadoVazio(
            self.editor,
            titulo=strings.TEXTO_VAZIO_TITULO,
            # A frase **sem** o "Nenhuma folha lida." da frente: o título já o diz, e repeti-lo
            # a 20 px de distância é a mesma duplicação que o §7 mandou apagar na Galeria.
            # `EDITOR_VAZIO` continua inteiro, porque ele é a frase de quem não tem título.
            frase=strings.TEXTO_VAZIO_FRASE,
            rotulo_do_botao=comandos.rotulo_de_botao("ler_folha"),
            nome_acessivel="Ler a folha da página aberta",
            acao=self.ler,
        )
        self.editor.textChanged.connect(self._mostrar_vazio)
        # A barra diz o estilo, a cor e o realce que valem sob o cursor (S-292, item 22).
        self.editor.cursorPositionChanged.connect(self._seguir_o_cursor)
        folha = self.editor.viewport()
        assert folha is not None  # o editor recém-montado sempre tem a área de desenho
        folha.installEventFilter(self)
        # O `Ctrl+Z` de dentro da folha. Ver `TECLAS_DO_HISTORICO`.
        self.editor.installEventFilter(self)
        self._teclas_do_historico = _teclas_da_tabela(TECLAS_DO_HISTORICO)
        self._teclas_do_editor = _teclas_do_editor()
        """As teclas que só valem dentro da folha (`atalhos.TECLAS_DO_EDITOR`), já traduzidas para o
        Qt: `Ctrl+B`, `Ctrl+I`, `F7`, `Alt+X`... É a tabela de onde `_ligar_teclas_do_editor` monta
        um `QShortcut` por tecla -- e o único caminho por onde elas disparam. A que não traduz sai
        no log em vez de custar o painel."""
        self._ligar_teclas_do_editor()
        corpo = QHBoxLayout()
        # O painel de navegação à esquerda da folha (S-654), com o índice das folhas do caderno
        # numa das abas (S-613); nasce escondido, como a paleta.
        self.navegacao = PainelDeNavegacao(self)
        self.indice = self.navegacao.indice
        self.indice.folha_escolhida.connect(self._abrir_do_indice)
        self.indice.alinhar_pedido.connect(self.alinhar_diagramas_do_caderno)
        self.navegacao.ir_para.connect(self._ir_para_intervalo)
        self.navegacao.busca_mudou.connect(self._refazer_resultados)
        self.navegacao.currentChanged.connect(lambda _i: self._refazer_navegacao())
        corpo.addWidget(self.navegacao)
        corpo.addWidget(self.editor, 1)
        corpo.addWidget(self._montar_paleta())
        caixa.addLayout(corpo, 1)

        # A barra de estado da mesa (S-655): a folha e o que ela tem, as palavras, o léxico, e o
        # zoom na ponta direita. O recado transitório toma o lugar das do meio por 6 s.
        rodape = QHBoxLayout()
        self.status = QLabel("", self)
        self.status.setAccessibleName("Estado da folha")
        # O clique na folha do rodapé leva ao campo da folha (S-655): «Folha 12» é onde se olha para
        # saber em que folha se está, e é dali que se quer ir à outra.
        self.status.setCursor(Qt.CursorShape.PointingHandCursor)
        dica_em(self.status, strings.DICA_DO_RODAPE_DA_FOLHA)
        self.status.installEventFilter(self)
        rodape.addWidget(self.status, 1)
        self.caixa_de_palavras = QLabel("", self)
        self.caixa_de_palavras.setAccessibleName("Palavras da folha")
        rodape.addWidget(self.caixa_de_palavras)
        self.caixa_do_lexico = QToolButton(self)
        self.caixa_do_lexico.setAccessibleName(comandos.nome_acessivel("proxima_fora_do_lexico"))
        self.caixa_do_lexico.setAutoRaise(True)
        self.caixa_do_lexico.clicked.connect(lambda _marcado=False: self.proxima_fora_do_lexico())
        self.caixa_do_lexico.hide()
        rodape.addWidget(self.caixa_do_lexico)
        self.recado = QLabel("", self)
        self.recado.setAccessibleName("Recado da aba")
        self.recado.hide()
        rodape.addWidget(self.recado, 1)
        rodape.addWidget(self._montar_zoom())
        caixa.addLayout(rodape)
        self._relogio_do_recado = QTimer(self)
        self._relogio_do_recado.setSingleShot(True)
        self._relogio_do_recado.setInterval(int(SEGUNDOS_DO_RECADO * 1000))
        self._relogio_do_recado.timeout.connect(self._apagar_recado)
        self.estado.connect(self._mostrar_recado)

    def _montar_zoom(self) -> QWidget:
        """O zoom à vista, no rodapé (S-630): `−`, a régua, `+` e a porcentagem.

        **O zoom já existia e ninguém o achava** -- `Ctrl+roda`, `Ctrl++`, `Ctrl+-` e três itens de
        menu (S-264) --, e o pedido "opção para aumentar e diminuir a fonte da aba" foi a medida
        disso. O desenho é o da barra de estado do WordCraft. A régua tem uma parada por **letra
        diferente** (`paradas_do_zoom`), e não uma por degrau; a porcentagem é a letra da vista
        sobre a letra sem zoom, e o clique nela volta a 100%. Os nomes que o leitor de tela anuncia
        vêm do catálogo, e o catálogo diz que o zoom "não muda o documento" -- é o que separa este
        controle do corpo do parágrafo, que muda.
        """
        from PyQt6.QtWidgets import QSlider, QToolButton

        zoom = QWidget(self)
        linha = QHBoxLayout(zoom)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(2)
        self._paradas_do_zoom = paradas_do_zoom(tema.fonte_base()[0])

        def botao(texto: str, acao: str, alvo: Callable[[], object]) -> QToolButton:
            feito = QToolButton(zoom)
            feito.setText(texto)
            feito.setAccessibleName(comandos.nome_acessivel(acao))
            tecla = atalhos.acelerador(acao)
            dica_em(feito, f"{comandos.rotulo(acao)}\nTecla: {tecla}" if tecla else comandos.rotulo(acao))
            feito.clicked.connect(lambda _marcado=False: alvo())
            return feito

        self.botao_de_afastar = botao("−", "afastar_texto", self.afastar_texto)
        self.regua_do_zoom = QSlider(Qt.Orientation.Horizontal, zoom)
        self.regua_do_zoom.setRange(0, len(self._paradas_do_zoom) - 1)
        self.regua_do_zoom.setPageStep(1)
        self.regua_do_zoom.setAccessibleName("Zoom do texto")
        self.regua_do_zoom.setMaximumWidth(self.fontMetrics().horizontalAdvance("M") * 10)
        self.regua_do_zoom.valueChanged.connect(self._zoom_pela_regua)
        self.botao_de_aproximar = botao("+", "aproximar_texto", self.aproximar_texto)
        self.porcentagem_do_zoom = botao("100%", "zoom_do_texto_normal", self.zoom_do_texto_normal)
        # Largura do maior valor possível: o rodapé não pula quando o número ganha um dígito.
        self.porcentagem_do_zoom.setMinimumWidth(self.fontMetrics().horizontalAdvance("000%") + 12)
        for parte in (self.botao_de_afastar, self.regua_do_zoom, self.botao_de_aproximar, self.porcentagem_do_zoom):
            linha.addWidget(parte)
        self._mostrar_zoom()
        return zoom

    def _zoom_pela_regua(self, indice: int) -> None:
        """A régua mexida pela pessoa. A régua reposta por `_mostrar_zoom` chega com o sinal bloqueado."""
        self.aplicar_zoom(self._paradas_do_zoom[max(0, min(indice, len(self._paradas_do_zoom) - 1))])

    def _mostrar_zoom(self) -> None:
        """Põe a régua, a porcentagem e os dois botões no zoom que vale -- sem disparar nada."""
        base = tema.fonte_base()[0]
        paradas = self._paradas_do_zoom
        # O degrau gravado pode não ser parada (empatou com um vizinho no piso de legibilidade):
        # a régua mostra a parada de mesma letra, que é a mais próxima.
        indice = min(range(len(paradas)), key=lambda i: abs(paradas[i] - self._zoom_da_vista))
        self.regua_do_zoom.blockSignals(True)
        try:
            self.regua_do_zoom.setValue(indice)
        finally:
            self.regua_do_zoom.blockSignals(False)
        porcentagem = porcentagem_do_zoom(self._zoom_da_vista, base)
        self.porcentagem_do_zoom.setText(f"{porcentagem}%")
        self.regua_do_zoom.setAccessibleDescription(f"{porcentagem} por cento")
        self.botao_de_afastar.setEnabled(self._zoom_da_vista > paradas[0])
        self.botao_de_aproximar.setEnabled(self._zoom_da_vista < paradas[-1])

    def _seguir_o_cursor(self) -> None:
        """As três escolhas da barra mostram o que vale sob o cursor -- ou na seleção inteira.

        O Tk tinha isto desde a S-292 e o porte deixou as caixas paradas em «(sem estilo)»: a
        pessoa punha o cursor num título e a barra dizia que não havia estilo. `valor_em_todo`
        responde `None` quando a seleção mistura valores, e aí a caixa volta ao vazio -- a mesma
        regra do negrito misto. As caixas disparam só por `activated` (o clique da pessoa), então
        repô-las aqui não aplica nada.
        """
        if self._redesenhando:
            return
        inicio, fim = self._intervalo()
        if inicio == fim:
            fim = min(len(self.documento.para_texto()), inicio + 1)
        for caixa, atributo in ((self.escolha_de_cor, "cor"), (self.escolha_de_realce, "realce")):
            valor = rico.valor_em_todo(self.documento, inicio, fim, atributo) if fim > inicio else None
            indice = caixa.findData(valor or "")
            caixa.setCurrentIndex(indice if indice >= 0 else 0)
        doc = self.documento
        estilo = rico.valor_em_todo(doc, inicio, fim, "estilo") if fim > inicio else ""
        for nome, amostra in self.amostras.items():
            amostra.setChecked(estilo is not None and nome == (estilo or ""))
        # Os botões de estado (S-650): marcados com o que vale em todo o trecho, desmarcados no misto.
        estados = {a: fim > inicio and rico.vale_em_todo(doc, inicio, fim, a) for a in ("negrito", "italico", "sublinhado", "tachado")}
        alinhamento = rico.valor_em_todo(doc, inicio, fim, "alinhamento") if fim > inicio else None
        marca = self._marca_em(inicio)
        if marca is not None:  # `valor_em_todo` pula a marca do diagrama: sobre ela vale o efetivo (S-620)
            alinhamento = rico.alinhamento_efetivo(marca[2], padrao_do_diagrama=alinhamento_dos_diagramas(self._diagramas))
        for nome, valor in (("alinhar_esquerda", "esquerda"), ("alinhar_centro", "centro"), ("alinhar_direita", "direita"), ("justificar", "justificado")):
            estados[nome] = alinhamento == valor or (valor == "esquerda" and alinhamento == "")
        self.fita.marcar(estados)
        self._mostrar_corpo(inicio, fim)
        self._contar_palavras_da_selecao()

    def _atualizar_status(self) -> None:
        """O rodapé da aba, refeito a cada mudança do documento e a cada gravação.

        A frase é de `ui/texto_declarado.frase_do_rodape`; aqui só se contam as miniaturas, que
        são do desenho e não do documento.
        """
        diagramas = self.documento.diagramas
        cad = self._caderno_da_tela()
        guardada = None if cad is None or self._pagina is None else cad.estado(self._pagina.pagina)
        self.status.setText(
            frase_do_rodape(
                folha=None if self._pagina is None else int(self._pagina.pagina),
                trechos=len(self.documento.corridas),
                diagramas=len(diagramas),
                miniaturas=sum(1 for c in diagramas if self._tem_miniatura(c)),
                por_gravar=self.tem_alteracoes,
                correcoes=self._correcoes,
                do_caderno=guardada is not None,
                conferidas=None if cad is None else (cad.conferidas(), self._folhas_do_livro()),
                # A hora vem do índice do caderno (`gravada_em`, ISO), e não de um relógio do painel:
                # é a hora da gravação de verdade, e a folha reaberta amanhã diz a de hoje.
                gravado_as=guardada.gravada_em[11:16] if guardada is not None else "",
            )
        )

    def ir_ao_campo_de_folha(self) -> None:
        """O clique na folha do rodapé (S-655): a aba Leitura da fita à frente e o campo da folha pronto."""
        from chess_diagram_ocr.ui import fita_do_texto

        leitura = next(i for i, aba in enumerate(fita_do_texto.ABAS) if "@folha" in (it for g in aba.grupos for it in g.itens))
        if self.fita.recolhida:
            self.fita.definir_recolhida(False)
        self.fita.setCurrentIndex(leitura)
        self.campo_de_folha.setFocus()
        self.campo_de_folha.selectAll()

    def _folhas_do_livro(self) -> int:
        """Quantas folhas o livro tem, pelo teto do campo; sem ele, até a última folha do caderno."""
        teto = int(self.campo_de_folha.maximum())
        if teto < TETO_DE_FOLHAS:
            return teto
        folhas = () if self._caderno is None else self._caderno.folhas()
        return folhas[-1].pagina + 1 if folhas else 0

    def _contar_correcoes(self) -> None:
        """Refaz a conta das correções e o rodapé. Na pausa, na gravação e na abertura -- não por tecla."""
        self._correcoes = len(correcao.correcoes(self.documento)) if self.documento.origem is not None else 0
        self._atualizar_status()

    def _ligar_teclas_do_editor(self) -> None:
        """As teclas próprias do editor (S-241/S-259/S-263), ligadas **no widget** (S-511).

        `atalhos.TECLAS_DO_EDITOR` é a única declaração delas, e do lado do Tk quem as ligava era
        o `Text.bind`. O porte trouxe a tabela e não o `bind`: `Ctrl+B` não fazia nada no Qt, sem
        erro nenhum, porque a tabela continuava lá e nenhuma guarda perguntava se alguém a lia.

        Duas coisas, e as duas vêm de `ui/atalhos.py`. Um `QShortcut` por linha da tabela, com
        alcance no editor, disparando o método de `COMANDOS_DA_ABA` -- o mesmo do botão. E
        `teclas_proprias` no próprio widget, que é o que `qt/atalhos.cede_a_tecla` lê para
        entregar ao editor as teclas que ele **divide** com a janela (`Ctrl+R`, `Ctrl++`,
        `Ctrl+-`) e não a que a janela ganha (`Ctrl+H`, que chega por `acoes_proprias`).
        `teclas_cedidas_ao_editor` levanta na montagem se uma tecla nova entrar nas duas tabelas
        sem `SOBREPOSICOES_NO_EDITOR` dizer de quem ela é.
        """
        self.editor.teclas_proprias = atalhos.teclas_cedidas_ao_editor()  # type: ignore[attr-defined]
        for acao, tecla in self._teclas_do_editor.items():
            atalho = QShortcut(tecla, self.editor)
            atalho.setContext(Qt.ShortcutContext.WidgetShortcut)
            atalho.activated.connect(partial(self.executar, acao))

    def _montar_paleta(self) -> QListWidget:
        """O painel lateral de glifos (S-248). Nasce escondido: ele é um caminho a mais.

        Uma lista e não uma grade de botões: os glifos são muitos, a lista rola, e clicar num item
        é o mesmo gesto que clicar num botão -- com a diferença de que a lista não precisa de uma
        decisão de quantas colunas.
        """
        from chess_diagram_ocr.text import paleta as _paleta

        self.paleta_lateral = QListWidget(self)
        # **`"Lista"` não nomeia** (F9-C2, defeito nº 1): era o nome genérico da classe, e o
        # portão do `teclado.py` reprova eco do papel. O que esta lista guarda são os símbolos
        # de anotação que se inserem no texto.
        self.paleta_lateral.setAccessibleName("Símbolos de anotação")
        self.paleta_lateral.setFixedWidth(72)
        self.paleta_lateral.hide()
        self._simbolos_da_paleta = tuple(_paleta.MINIMA)
        self._encher_a_paleta()
        self.paleta_lateral.itemClicked.connect(lambda item: self.inserir_simbolo(item.text()))
        return self.paleta_lateral

    def _encher_a_paleta(self) -> None:
        """Os 20 usados por último primeiro, e depois os de sempre (o conforto do WordCraft, S-650)."""
        self.paleta_lateral.clear()
        recentes = list(getattr(self, "_glifos_recentes", []))
        for simbolo in [*recentes, *(s for s in self._simbolos_da_paleta if s not in recentes)]:
            self.paleta_lateral.addItem(simbolo)

    def _lembrar_glifo(self, simbolo: str) -> None:
        self._glifos_recentes = [simbolo, *(s for s in self._glifos_recentes if s != simbolo)][:GLIFOS_RECENTES]
        self._encher_a_paleta()

    def _montar_controles(self) -> None:
        """Os controles que colhem valor, que a fita põe nos grupos dela (S-650). Ver `ui/fita_do_texto`."""
        barra = self
        self.galeria = self._montar_galeria()
        self.caixa_de_corpo = self._montar_caixa_de_corpo()

        self.escolha_de_cor = QComboBox(barra)
        self.escolha_de_cor.setAccessibleName("Cor da letra")
        self.escolha_de_cor.addItem("(sem cor)", "")
        for nome in texto_cores.nomes():
            self.escolha_de_cor.addItem(nome.capitalize(), nome)
        self.escolha_de_cor.activated.connect(
            lambda _i: self.pintar_letra(str(self.escolha_de_cor.currentData()))
        )

        self.escolha_de_realce = QComboBox(barra)
        self.escolha_de_realce.setAccessibleName("Cor do realce")
        self.escolha_de_realce.addItem("(sem realce)", "")
        # Os mesmos nomes da cor da letra: o realce é o **canal** do autor, e não uma
        # segunda paleta -- `texto_cores.papel_de_realce` resolve o mesmo nome noutro papel.
        for nome in texto_cores.nomes():
            self.escolha_de_realce.addItem(nome.capitalize(), nome)
        self.escolha_de_realce.activated.connect(
            lambda _i: self.pintar_realce(str(self.escolha_de_realce.currentData()))
        )
        # Os botões partidos que lembram a última cor (S-650), o conforto do WordCraft: o clique
        # aplica a mesma de antes, e a seta abre a lista. As listas de cima ficam, porque são elas
        # que mostram a cor **sob o cursor**; o botão mostra a que o clique vai pôr.
        self.cor_rapida = self._botao_partido("letra")
        self.realce_rapido = self._botao_partido("realce")

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
        self.campo_de_folha.setValue(self._pagina_indice + 1)

        self.escolha_de_motor = QComboBox(barra)
        self.escolha_de_motor.setAccessibleName("Motor de leitura")
        for motor in MOTORES:
            self.escolha_de_motor.addItem(motor, motor)
        self.escolha_de_motor.activated.connect(
            lambda _i: setattr(self, "_motor", str(self.escolha_de_motor.currentData()))
        )
        dica_em(
            self.escolha_de_motor,
            "auto é o glifo com a camada do PDF como reserva. O glifo sozinho precisa de "
            "models/char_classifier.pt, que não vem no repositório.",
        )

        self.caixa_de_bloco = QCheckBox(comandos.rotulo_de_botao("modo_bloco"), barra)
        self.caixa_de_bloco.toggled.connect(lambda _ligado: self.modo_bloco_mudou())

    def _botao_partido(self, canal: str) -> QToolButton:
        """Um botão partido de cor: o corpo aplica a última, a seta abre os nomes do autor."""
        botao = QToolButton(self)
        botao.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        botao.setAccessibleName(strings.COR_RAPIDA[canal])
        menu = QMenu(botao)
        for nome in texto_cores.nomes():
            acao = QAction(nome.capitalize(), menu)
            acao.triggered.connect(lambda _m=False, n=nome, c=canal: self._pintar_e_lembrar(c, n))
            menu.addAction(acao)
        botao.setMenu(menu)
        botao.clicked.connect(lambda _m=False, c=canal: self._pintar_e_lembrar(c, self._ultimas_cores[c]))
        self._mostrar_ultima_cor(botao, canal)
        return botao

    def _pintar_e_lembrar(self, canal: str, nome: str) -> None:
        self._ultimas_cores[canal] = nome
        (self.pintar_letra if canal == "letra" else self.pintar_realce)(nome)
        self._mostrar_ultima_cor(self.cor_rapida if canal == "letra" else self.realce_rapido, canal)

    def _mostrar_ultima_cor(self, botao: QToolButton, canal: str) -> None:
        """O botão diz e desenha a cor que o clique vai pôr: o nome e uma amostra pela função da folha."""
        from PyQt6.QtGui import QIcon, QPixmap

        nome = self._ultimas_cores[canal]
        atributos = rico.Atributos(cor=nome) if canal == "letra" else rico.Atributos(realce=nome)
        formato = formato_de(rico.Corrida("A", atributos))
        amostra = QPixmap(14, 14)
        amostra.fill(formato.foreground().color() if canal == "letra" else formato.background().color())
        botao.setIcon(QIcon(amostra))
        botao.setText(nome.capitalize())
        botao.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        dica_em(botao, strings.dica_da_cor_rapida(canal, nome))

    def _alvo_da_fita(self, acao: str) -> Callable[[], object]:
        """Quem atende um botão da fita: o painel (pela tabela ou pelas ações próprias), ou a janela."""
        if acao in COMANDOS_DA_ABA:
            return lambda: self.executar(acao)
        proprio = self.atender(acao)
        if proprio is not None:
            return proprio
        return lambda: self._executar_fora(acao)

    def definir_executor(self, executor: Callable[[str], object] | None) -> None:
        """Quem roda os comandos da fita que são da janela -- a mesa, por exemplo. `None` os desliga."""
        self._executor = executor

    def _executar_fora(self, acao: str) -> None:
        if self._executor is None:
            self.estado.emit(f"«{comandos.rotulo(acao)}» é da janela, e esta aba está sozinha.")
            return
        self._executor(acao)

    def _montar_galeria(self) -> QWidget:
        """A galeria de estilos (S-651): cada amostra desenhada **no próprio estilo**, pela função da folha.

        A fonte de cada botão sai de `texto_formato.formato_de`, a mesma que desenha a folha: a galeria
        não pode mostrar um estilo que a folha não desenha, que é a guarda S-603 aplicada à amostra.
        """
        from PyQt6.QtWidgets import QButtonGroup, QToolButton

        galeria = QWidget(self)
        galeria.setAccessibleName("Galeria de estilos")
        linha = QHBoxLayout(galeria)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(2)
        grupo = QButtonGroup(galeria)
        grupo.setExclusive(True)
        self.amostras: dict[str, QToolButton] = {}
        for estilo in ("", *rico.ESTILOS):
            amostra = QToolButton(galeria)
            amostra.setText(strings.NOME_DO_ESTILO.get(estilo, estilo.capitalize()))
            amostra.setAccessibleName(f"Estilo {strings.NOME_DO_ESTILO.get(estilo, estilo)}")
            amostra.setCheckable(True)
            amostra.setAutoRaise(True)
            amostra.setFont(formato_de(rico.Corrida(estilo or "Normal", rico.Atributos(estilo=estilo))).font())
            amostra.clicked.connect(lambda _marcado=False, e=estilo: self.aplicar_estilo(e))
            grupo.addButton(amostra)
            linha.addWidget(amostra)
            self.amostras[estilo] = amostra
        return galeria

    def estilo_na_galeria(self) -> str | None:
        """O estilo marcado na galeria, ou `None` quando a seleção mistura estilos."""
        for estilo, amostra in self.amostras.items():
            if amostra.isChecked():
                return estilo
        return None

    def _papel_e_base(self, estilo: str) -> tuple[str, int]:
        from chess_diagram_ocr.qt.texto_formato import PAPEL_DO_ESTILO

        base = self._base[0] if self._base is not None else tema.fonte_base()[0]
        return (PAPEL_DO_ESTILO[estilo] if estilo else tipografia.CORPO), base

    def _mostrar_corpo(self, inicio: int, fim: int) -> None:
        """A caixa mostra o corpo do parágrafo sob o cursor em pontos -- vazia quando a seleção mistura (S-631)."""
        comeco, final = rico.intervalo_de_paragrafo(self.documento, inicio, fim)
        degrau = rico.valor_em_todo(self.documento, comeco, final, "corpo") if final > comeco else None
        estilo = rico.valor_em_todo(self.documento, comeco, final, "estilo") if final > comeco else ""
        self.caixa_de_corpo.blockSignals(True)
        try:
            if degrau is None or estilo is None:
                self.caixa_de_corpo.setValue(self.caixa_de_corpo.minimum())
            else:
                papel, base = self._papel_e_base(estilo)
                self.caixa_de_corpo.setValue(tipografia.corpo(int(degrau), base=base, papel=papel))
        finally:
            self.caixa_de_corpo.blockSignals(False)
        self._corpo_mostrado = self.caixa_de_corpo.value()

    def _corpo_digitado(self) -> None:
        """O valor digitado vira o degrau mais próximo, no parágrafo inteiro, num passo de desfazer."""
        valor = self.caixa_de_corpo.value()
        if valor == getattr(self, "_corpo_mostrado", None) or valor < tipografia.MINIMO_LEGIVEL:
            return
        inicio, fim = self._intervalo()
        comeco, final = rico.intervalo_de_paragrafo(self.documento, inicio, fim)
        estilo = rico.valor_em_todo(self.documento, comeco, final, "estilo") or ""
        papel, base = self._papel_e_base(estilo)
        degrau = rico.corpo_no_limite(valor - tipografia.corpo(0, base=base, papel=papel))
        self._rotulo_corrente = "Corpo do parágrafo"
        try:
            self._aplicar(rico.aplicar_no_paragrafo(self.documento, inicio, fim, corpo=degrau))
        finally:
            self._rotulo_corrente = ""

    def _montar_caixa_de_corpo(self) -> QSpinBox:
        """O corpo do **parágrafo** em pontos (S-631). Não é o zoom: ele muda o documento e a exportação."""
        caixa = QSpinBox(self)
        caixa.setAccessibleName("Corpo do parágrafo (pt)")
        caixa.setRange(tipografia.MINIMO_LEGIVEL - 1, 96)
        caixa.setSpecialValueText(" ")  # o valor de baixo é "misto": a caixa vazia, como o negrito misto
        caixa.setSuffix(" pt")
        dica_em(caixa, strings.DICA_DO_CORPO_EM_PONTOS)
        caixa.editingFinished.connect(self._corpo_digitado)
        return caixa

    def _botao(self, barra: BarraFluida, acao: str, alvo: Callable[[], object]) -> QWidget:
        """Um botão de ferramenta: rótulo e dica do catálogo, tecla da tabela.

        Este arquivo não escreve texto de interface nem sequência de tecla -- é a S-324 e a
        S-165, e vale igual aos dois frontends.
        """
        from PyQt6.QtWidgets import QPushButton

        rotulo = comandos.rotulo_de_botao(acao) if _no_catalogo(acao) else acao.capitalize()
        botao = QPushButton(rotulo, barra)
        # **O nome acessível é o rótulo por extenso, e não o texto do botão** (F9-C2).
        # O crítico do ciclo 1 mediu 28 controles que chegavam ao leitor de tela como "-",
        # "+", "|◀" ou ".md" -- o `rotulo_curto` passando pela cascata de
        # `ui/nomes_acessiveis.py` no passo `text()`. Ver `comandos.Comando.no_leitor`.
        if _no_catalogo(acao):
            botao.setAccessibleName(comandos.nome_acessivel(acao))
        botao.clicked.connect(lambda _marcado=False: alvo())
        tema.aplicar_papel(botao, estilos.NEUTRO)
        motivo = comandos.rotulo(acao) if _no_catalogo(acao) else rotulo
        tecla = atalhos.acelerador(acao)
        dica_em(botao, f"{motivo}\nTecla: {tecla}" if tecla else motivo)
        barra.adicionar(botao)
        return botao

    # ------------------------------------------------------------------------------ desenho

    def desenhar_documento(self, doc: rico.DocumentoRico, *, selecao: tuple[int, int] | None = None) -> None:
        """Troca o documento e o desenha. **Este laço não decide nada.**

        Faixa, ordem, separador e atributo já vieram decididos por `text/rico.py`; o que sobra
        aqui é escrever no cursor e pôr a miniatura. É a mesma fronteira do outro frontend.

        `selecao` é `(âncora, ponta)` em deslocamento do documento novo: onde o cursor fica depois
        do desenho. `None` é folha nova -- o cursor volta ao começo, que é o certo para a leitura
        e para o arquivo aberto, e o errado para o negrito no meio da página.
        """
        self.documento = doc
        self._desenhar(selecao=selecao)
        self.documento_mudou.emit()

    def _desenhar(self, *, selecao: tuple[int, int] | None = None) -> None:
        """Refaz o `QTextDocument` inteiro a partir das corridas -- e devolve o cursor a `selecao`.

        **Devolver o cursor é o que torna o redesenho compatível com a digitação.** O documento
        novo nasce com o cursor no começo e a rolagem no topo; com o texto digitado agora sendo
        documento, um `Ctrl+Z` ou um negrito no meio da folha que jogasse o cursor para o título
        faria a tecla seguinte escrever lá -- e ela passaria a ficar.
        """
        barra = self.editor.verticalScrollBar()
        rolagem = barra.value() if selecao is not None and barra is not None else None
        self._redesenhando = True
        try:
            self._mapa.limpar()
            documento = QTextDocument(self.editor)
            documento.setDefaultFont(self.editor.font())
            # **No documento, e não no editor.** `QTextEdit.setUndoRedoEnabled` vale para o
            # documento em vigor, e `_desenhar` troca o documento -- ajustar só o editor no
            # `_montar` fazia o desfazer nativo voltar a ligar no primeiro redesenho, e aí
            # `Ctrl+Z` teria duas pilhas disputando. Foi um teste que pegou.
            documento.setUndoRedoEnabled(False)
            cursor = QTextCursor(documento)
            base = self._base_da_vista()
            self._base = base
            deslocamento = 0

            for corrida in self.documento.corridas:
                if corrida.e_diagrama:
                    self._inserir_miniatura(cursor, corrida)
                inicio = cursor.position()
                cursor.insertText(corrida.texto, formato_de(corrida, base=base))
                self._mapa.registrar_texto(deslocamento, inicio, corrida.texto)
                deslocamento += len(corrida.texto)
            # **O formato de parágrafo é escrito depois do texto, bloco a bloco** (S-601). Escrito
            # no laço, antes de cada corrida, ele caía no bloco em que o cursor estava -- e a corrida
            # separadora (`"\n\n"`, sem atributos) chegava com o cursor ainda no parágrafo anterior:
            # o formato vazio dela apagava o centro e o título que ele acabara de receber.
            self._formatar_blocos(documento)

            # O `setDocument` só apaga o documento que é filho do controle interno do editor -- o da
            # montagem, e na hora --, e os deste painel são filhos do editor: sem soltá-los, cada
            # redesenho deixava a folha anterior inteira, com as miniaturas, pendurada até a janela
            # fechar. Quem é de quem se pergunta **antes** da troca, porque depois dela o da
            # montagem já não existe; e `deleteLater`, e não já, porque o redesenho pode estar
            # acontecendo de dentro de um sinal do documento que sai (`_trocado`).
            anterior = self.editor.document()
            nosso = anterior if anterior is not None and anterior.parent() is self.editor else None
            self.editor.setDocument(documento)
            if nosso is not None:
                nosso.deleteLater()
            # Ligado **depois** de montar: o que o laço acima escreveu é desenho, e não digitação.
            documento.contentsChange.connect(self._digitado)
            self._aplicar_marcas()
            self._tela = _texto_da_tela(documento)
        finally:
            self._redesenhando = False
        if selecao is not None:
            self._devolver_selecao(selecao, rolagem)
        # A marcação do léxico não é do documento e morre com o `QTextDocument` que saiu: com a
        # conferência ligada, ela se refaz sobre a folha nova (S-293).
        if self._conferindo_lexico:
            self._conferir_lexico(avisar=False)

    def _base_da_vista(self) -> tuple[int, str, str]:
        """A fonte de base **com o zoom da vista** (S-264).

        O zoom é um degrau somado ao corpo do sistema, e é aqui que ele entra na folha: toda
        corrida é desenhada por `formato_de` a partir desta base, então aplicá-lo só à fonte do
        editor -- como o porte fazia -- não mudava letra nenhuma, porque cada trecho sai com o seu
        corpo explícito. O degrau parte sempre da origem, nunca do que está na tela.
        """
        from chess_diagram_ocr.ui import tipografia

        tamanho, proporcional, monoespacada = tema.fonte_base()
        # A letra de leitura (S-632) troca só a proporcional: o papel DADO -- a notação -- continua
        # na monoespaçada nas três, porque `texto_formato._fonte` a escolhe pela outra metade da base.
        if self._familia_da_letra == "monoespacada":
            proporcional = monoespacada
        elif self._familia_da_letra == "serifada":
            proporcional = tema.familia_serifada(proporcional)
        return tipografia.corpo(self._zoom_da_vista, base=tamanho), proporcional, monoespacada

    def _formatar_blocos(self, documento: QTextDocument, inicio: int = 0, fim: int | None = None) -> None:
        """Dá a cada bloco da tela entre `inicio` e `fim` (posições do Qt) o formato que o documento pede.

        **Quem decide o formato de um bloco é a corrida em que ele começa**, porque em `rico` o
        parágrafo é o bloco de `rico`, e não o do Qt: depois de um `Enter` no meio de um parágrafo
        lido, os dois blocos do Qt continuam no mesmo parágrafo e levam o mesmo formato. Duas
        exceções, e as duas são desenho:

        - **a linha em branco** sai com o formato vazio. Se herdasse o centro e a margem de título
          do parágrafo de cima, o `Enter` dado nela seria engolido -- o Qt, num bloco vazio com
          formato, só o redefine (a primeira revisão do plano mediu);
        - **o bloco da miniatura** leva o formato da marca logo abaixo dele (S-602): a figura anda
          com o alinhamento do diagrama, e não com o da prosa de cima.

        A pergunta "que formato?" é `formato_de_bloco`, a mesma que a guarda de paridade faz.
        """
        bloco = documento.findBlock(inicio)
        cursor = QTextCursor(documento)
        while bloco.isValid() and (fim is None or bloco.position() <= fim):
            texto = bloco.text()
            if OBJETO in texto:
                seguinte = bloco.next()
                corrida = _corrida_em(self.documento, self._mapa.deslocamento(seguinte.position())) if seguinte.isValid() else None
            elif texto:
                corrida = _corrida_em(self.documento, self._mapa.deslocamento(bloco.position()))
            else:
                corrida = None
            formato = self.formato_de_bloco(corrida)
            if bloco.blockFormat() != formato:
                cursor.setPosition(bloco.position())
                cursor.setBlockFormat(formato)
            bloco = bloco.next()

    def formato_de_bloco(self, corrida: rico.Corrida | None) -> QTextBlockFormat:
        """O formato do bloco em que `corrida` começa, **nesta vista** -- o único lugar que o responde.

        `None` é a linha em branco, que sai sem formato. O alinhamento é o **efetivo**
        (`rico.alinhamento_efetivo`, S-620): o diagrama que ninguém alinhou vai para o centro, e é a
        mesma função que a exportação chama. O desenho escreve isto e a guarda de paridade (S-603) lê
        a tela contra isto; os dois perguntando a uma função só é o que impede o teste de concordar
        com um desenho errado.
        """
        if corrida is None:
            return bloco_de(rico.PADRAO, base=self._base)
        efetivo = rico.alinhamento_efetivo(corrida, padrao_do_diagrama=alinhamento_dos_diagramas(self._diagramas))
        return bloco_de(replace(corrida.atributos, alinhamento=efetivo), base=self._base)

    def _selecao_atual(self) -> tuple[int, int]:
        """`(âncora, ponta)` do cursor, em deslocamento do documento."""
        cursor = self.editor.textCursor()
        return (self._mapa.deslocamento(cursor.anchor()), self._mapa.deslocamento(cursor.position()))

    def _devolver_selecao(self, selecao: tuple[int, int], rolagem: int | None) -> None:
        """Põe o cursor em `selecao` e a rolagem onde estava; o cursor fora da tela a traz até ele."""
        ancora, ponta = selecao
        cursor = self.editor.textCursor()
        cursor.setPosition(self._mapa.posicao(ancora))
        cursor.setPosition(self._mapa.posicao(ponta), QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        barra = self.editor.verticalScrollBar()
        if rolagem is not None and barra is not None:
            barra.setValue(rolagem)
        self.editor.ensureCursorVisible()

    def _inserir_miniatura(self, cursor: QTextCursor, corrida: rico.Corrida) -> None:
        """A imagem do diagrama, **antes** da marca -- e a marca continua no texto.

        Parece redundante numa tela onde a imagem já aparece, e é o contrário: a imagem é do
        widget e morre com ele, a marca é do texto e sobrevive a salvar, copiar e colar. Um
        editor que trocasse a marca pela imagem perderia o diagrama na primeira exportação.

        A imagem **não** entra no mapa: ela não é do documento, e é justamente por isso que
        `_Mapa` existe.
        """
        figura = self._imagem_do_diagrama(corrida)
        if figura is None:
            return
        mapa = figura.scaledToWidth(self._largura_da_miniatura(), Qt.TransformationMode.SmoothTransformation)
        nome = f"diagrama:{corrida.bloco}"
        documento = cursor.document()
        if documento is not None:
            documento.addResource(QTextDocument.ResourceType.ImageResource.value, _url(nome), mapa)
        # Com a medida escrita no formato, e não só no pixmap: é o que o Qt usa para o leiaute, e é
        # o que um teste consegue ler de volta sem desenhar a tela.
        imagem = QTextImageFormat()
        imagem.setName(nome)
        imagem.setWidth(mapa.width())
        imagem.setHeight(mapa.height())
        # O texto alternativo (item 14): é o que o leitor de tela diz no lugar da figura, e o que
        # o `toHtml` escreve no `alt`. A marca vem logo abaixo, mas a marca é texto do documento, e
        # a figura precisa dizer por si o que é.
        numero = int(getattr(self.documento.bloco_de(corrida), "indice", corrida.bloco)) + 1
        folha = "" if self._pagina is None else f" da folha {int(self._pagina.pagina) + 1}"
        imagem.setProperty(QTextFormat.Property.ImageAltText, f"Diagrama {numero}")
        imagem.setProperty(QTextFormat.Property.ImageTitle, f"Diagrama {numero}{folha}")
        # **A figura tem bloco próprio** (S-602): é ele que `_formatar_blocos` alinha com a marca.
        # Depois de um separador ela já começa um bloco em branco; sem separador antes -- `rico.editar`
        # deixa apagá-lo e escrever `Antes.[Diagrama 1]` -- ela cairia no meio da prosa.
        if cursor.positionInBlock() > 0:
            cursor.insertBlock()
        if self._flutua(corrida):
            self._inserir_flutuante(cursor, imagem)
        else:
            cursor.insertImage(imagem)
        cursor.insertBlock()

    def _flutua(self, corrida: rico.Corrida) -> bool:
        """A figura desta marca flutua à esquerda, com o texto ao lado (S-624)? Só a que se desenha à esquerda."""
        if not self._texto_ao_lado:
            return False
        padrao = alinhamento_dos_diagramas(self._diagramas)
        return rico.alinhamento_efetivo(corrida, padrao_do_diagrama=padrao) == rico.ALINHAMENTO_ESQUERDA

    @staticmethod
    def _inserir_flutuante(cursor: QTextCursor, imagem: QTextImageFormat) -> None:
        """A figura flutuante, **pelo importador de HTML do Qt**, que é o único que a sabe fazer (S-624).

        A figura que flutua é um `QTextImageFormat` que aponta para um objeto de quadro com
        `FloatLeft`, e o quadro tem de estar registrado no documento: `QTextDocument.createObject`
        chamado do Python devolve um quadro de índice −1, que o leiaute ignora. O `<img align=left>`
        registra o quadro e, ao contrário do `QTextFrame` inserido pelo cursor, **não** põe
        `U+FDD0`/`U+FDD1` no texto cru -- a figura continua sendo um `OBJETO` só, e `_Mapa` e
        `_texto_da_tela` não mudam. O texto alternativo e o título entram depois, por mescla, que
        preserva o índice do objeto.
        """
        largura, altura = round(imagem.width()), round(imagem.height())
        cursor.insertFragment(
            QTextDocumentFragment.fromHtml(f'<img src="{imagem.name()}" width="{largura}" height="{altura}" align="left">')
        )
        figura = QTextCursor(cursor)
        figura.movePosition(QTextCursor.MoveOperation.PreviousCharacter, QTextCursor.MoveMode.KeepAnchor)
        extra = QTextCharFormat()
        for propriedade in (QTextFormat.Property.ImageAltText, QTextFormat.Property.ImageTitle):
            extra.setProperty(propriedade, imagem.property(propriedade))
        figura.mergeCharFormat(extra)

    def _imagem_do_diagrama(self, corrida: rico.Corrida) -> QPixmap | None:
        """A figura da miniatura: **o recorte da folha, ou o desenho da posição lida**.

        O recorte é a verdade impressa e vem primeiro. Sem folha -- o `.cvtxt` aberto com o livro
        fora do lugar, ou noutra máquina -- a miniatura nascia vazia mesmo quando o OCR de
        diagramas do produto já tinha lido a posição (item 6). Aí ela é desenhada da FEN, com as
        peças que o próprio programa desenha (`desenho_de_diagrama`), e a pessoa vê o diagrama em
        vez de uma marca solta. É desenho e não leitura: quem corrige a posição corrige na aba Livro.
        """
        recorte = self._recorte(corrida)
        if recorte is not None:
            return pixmap_de_rgb(recorte)
        png = _png_da_posicao(_posicao_de(self.documento, corrida), lado_px=self._largura_da_miniatura())
        if png is None:
            return None
        mapa = QPixmap()
        return mapa if mapa.loadFromData(png, "PNG") and not mapa.isNull() else None

    def _tem_miniatura(self, corrida: rico.Corrida) -> bool:
        """Há figura para esta marca -- recorte da folha ou posição lida -- sem desenhá-la."""
        return self._recorte(corrida) is not None or bool(_posicao_de(self.documento, corrida))

    def _largura_da_miniatura(self) -> int:
        """A miniatura **acompanha o zoom da vista** (S-264): a mesma razão que a letra.

        `LARGURA_DA_MINIATURA` é a largura no corpo do sistema; com a vista em +3 degraus sobre
        um corpo de 9 pt a miniatura cresce um terço, e com a vista em -2 ela encolhe. Sem isto,
        aproximar a folha deixava a letra do tamanho que a pessoa pediu e o diagrama do tamanho de
        antes -- cada vez menor em relação ao texto que fala dele.
        """
        corpo_do_sistema = max(1, tema.fonte_base()[0])
        corpo_da_vista = self._base[0] if self._base is not None else corpo_do_sistema
        return max(48, round(largura_da_miniatura(self._tamanho_da_miniatura) * corpo_da_vista / corpo_do_sistema))

    def _recorte(self, corrida: rico.Corrida) -> np.ndarray | None:
        """O pedaço da folha em que o diagrama está, ou `None` sem folha renderizada.

        **O bbox do bloco está em pontos e a folha em pixels**, e o fator entre os dois é o DPI
        com que ela foi renderizada -- é por isso que ele é o mesmo `self._dpi` dos dois lados.
        Usar outro aqui recortaria o lugar errado da folha em silêncio.

        Sem imagem a marca continua no texto e o editor abre igual: é o mesmo contrato de
        `texto_panel._inserir_miniatura`, e é o que faz a aba funcionar num checkout sem PDF.
        """
        if self._pagina_rgb is None:
            return None
        return _recorte_da_folha(self._pagina_rgb, self.documento.bloco_de(corrida), dpi=self._dpi)

    # -------------------------------------------------------------------------- ferramentas

    def _intervalo(self) -> tuple[int, int]:
        """O intervalo selecionado, **em deslocamento de documento**.

        Sem seleção os dois são iguais, e as funções de `rico` tratam isso como "a palavra sob o
        cursor" -- é `rico.intervalo_alvo`, e a decisão é de lá.
        """
        cursor = self.editor.textCursor()
        return (
            self._mapa.deslocamento(cursor.selectionStart()),
            self._mapa.deslocamento(cursor.selectionEnd()),
        )

    def _aplicar(self, novo: rico.DocumentoRico, *, selecao: tuple[int, int] | None = None) -> None:
        """Guarda o documento anterior na pilha e desenha o novo.

        A pilha é de **documentos**, e é o que faz `Ctrl+Z` desfazer um negrito -- que não muda
        caractere nenhum e que uma pilha de texto não veria.

        **Toda ferramenta fecha o passo da digitação**: `Ctrl+Z` depois de "digitar, negritar,
        digitar" desfaz a segunda digitação, e não as duas com o negrito no meio. A seleção fica
        onde estava (ou em `selecao`), para o segundo pincel cair no mesmo trecho que o primeiro.
        """
        self._digitacao = None
        if novo is self.documento:
            return
        selecao = self._selecao_atual() if selecao is None else selecao
        self._historico.append(self.documento)
        self._rotulos_do_historico.append(self._rotulo_corrente or "Edição")
        self._rotulos_refeitos.clear()
        # O contador que decide o `Ctrl+Z` quando o foco não está em desfazível nenhum (S-243).
        self._edicao += 1
        self._refeitos.clear()
        self.desenhar_documento(novo, selecao=selecao)

    def alternar(self, atributo: str) -> None:
        """Liga o atributo no intervalo -- ou desliga, se ele já vale em todo ele (S-241)."""
        inicio, fim = self._intervalo()
        self._aplicar(rico.alternar(self.documento, inicio, fim, atributo))

    def negrito(self) -> None:
        self.alternar("negrito")

    def italico(self) -> None:
        self.alternar("italico")

    def sublinhado(self) -> None:
        self.alternar("sublinhado")

    def tachado(self) -> None:
        self.alternar("tachado")

    def limpar_formato(self) -> None:
        """Tira negrito, itálico e sublinhado. **Não** toca em cor nem em estilo (S-242)."""
        inicio, fim = self._intervalo()
        self._aplicar(rico.limpar_formato(self.documento, inicio, fim))

    def pintar_letra(self, nome: str) -> None:
        """A cor do autor. `""` limpa -- e limpar cor **não** toca a faixa de confiança (S-242)."""
        inicio, fim = self._intervalo()
        if not nome:
            self._aplicar(rico.limpar_cor(self.documento, inicio, fim))
            return
        self._aplicar(rico.aplicar(self.documento, inicio, fim, cor=nome))

    def pintar_realce(self, nome: str) -> None:
        inicio, fim = self._intervalo()
        self._aplicar(rico.aplicar(self.documento, inicio, fim, realce=nome))

    def aplicar_estilo(self, estilo: str) -> None:
        """O estilo do **parágrafo** que o intervalo toca (S-249).

        O alcance passa do que foi selecionado de propósito: o parágrafo é o conjunto de corridas
        do mesmo bloco, e marcar meia frase deixaria dois corpos de fonte na mesma linha.
        """
        inicio, fim = self._intervalo()
        self._aplicar(rico.aplicar_estilo(self.documento, inicio, fim, estilo))

    def alinhar(self, alinhamento: str) -> None:
        inicio, fim = self._intervalo()
        self._aplicar(rico.aplicar_alinhamento(self.documento, inicio, fim, alinhamento))

    def mudar_corpo(self, degrau: int) -> None:
        """Aumenta ou diminui o corpo do parágrafo, em degraus (S-260).

        **O degrau é somado ao que o documento guarda, e não ao que está na tela.** Somar ao
        tamanho desenhado acumularia o degrau anterior a cada redesenho, e a fonte cresceria
        sozinha -- é a razão que `texto_formato._fonte` documenta do outro lado.
        """
        inicio, fim = self._intervalo()
        atual = self._corpo_em(inicio)
        self._aplicar(
            rico.aplicar_no_paragrafo(self.documento, inicio, fim, corpo=rico.corpo_no_limite(atual + degrau))
        )

    def _corpo_em(self, deslocamento: int) -> int:
        percorrido = 0
        for corrida in self.documento.corridas:
            if percorrido <= deslocamento < percorrido + len(corrida.texto):
                return corrida.atributos.corpo
            percorrido += len(corrida.texto)
        return 0

    # ---------------------------------------------------------------------------- histórico

    def contem(self, widget: object) -> bool:
        """Este widget está dentro desta aba? É o que decide de quem é o `Ctrl+Z` (S-243)."""
        return qt_atalhos.contem(self, widget)

    @property
    def edicao(self) -> int:
        """Contador que só cresce, como manda `ui/desfazivel.Desfazivel`. Zero = nunca editado."""
        return self._edicao

    def desfazer(self) -> None:
        """`Ctrl+Z`: devolve o documento anterior -- a palavra digitada inteira é **um** passo."""
        if not self._historico:
            self.estado.emit("Não há mudança anterior nesta folha para desfazer.")
            return
        self._digitacao = None
        self._refeitos.append(self.documento)
        self._rotulos_refeitos.append(self._rotulos_do_historico.pop() if self._rotulos_do_historico else "Edição")
        self._voltar_a(self._historico.pop())

    def desfazer_ate(self, passos: int) -> None:
        """Desfaz `passos` de uma vez, pela lista da barra de acesso rápido (S-656). Um redesenho só."""
        passos = min(int(passos), len(self._historico))
        if passos <= 0:
            return
        self._digitacao = None
        alvo = self.documento
        for _ in range(passos):
            self._refeitos.append(alvo)
            self._rotulos_refeitos.append(self._rotulos_do_historico.pop() if self._rotulos_do_historico else "Edição")
            alvo = self._historico.pop()
        self._voltar_a(alvo)
        self.estado.emit(f"{passos} passo(s) desfeito(s).")

    def refazer(self) -> None:
        """`Ctrl+Y`: repõe o que o desfazer tirou."""
        if not self._refeitos:
            self.estado.emit("Não há o que refazer: nada foi desfeito.")
            return
        self._digitacao = None
        self._historico.append(self.documento)
        self._rotulos_do_historico.append(self._rotulos_refeitos.pop() if self._rotulos_refeitos else "Edição")
        self._voltar_a(self._refeitos.pop())

    def _voltar_a(self, doc: rico.DocumentoRico) -> None:
        """Desenha `doc` com o cursor **onde o texto mudou** -- o fim do trecho que voltou ou saiu.

        É onde qualquer editor põe o cursor depois de desfazer, e é onde a pessoa vai continuar
        escrevendo. Se o texto não mudou (desfazer um negrito), a seleção fica onde estava.
        """
        troca = _janela_da_troca(self.documento.para_texto(), doc.para_texto())
        if troca is None:
            self.desenhar_documento(doc, selecao=self._selecao_atual())
            return
        alvo = troca[0] + troca[2]
        self.desenhar_documento(doc, selecao=(alvo, alvo))

    @property
    def pode_desfazer(self) -> bool:
        return bool(self._historico)

    @property
    def pode_refazer(self) -> bool:
        return bool(self._refeitos)

    # -------------------------------------------------------------------------------- carga

    def mostrar_pagina(
        self, pagina: PaginaLida, *, folha_rgb: np.ndarray | None = None, dpi: int | None = None
    ) -> None:
        """Abre uma `PaginaLida` no editor. É o que a leitura entrega -- e é o ponto de partida
        contra o qual `tem_alteracoes` compara: a folha recém-lida não tem nada por gravar.

        `dpi` é o da `folha_rgb`, quando ela vem: é o que liga os pontos do `bbox` aos pixels dela.
        """
        guardadas = self._posicoes.get((_chave_de_livro(pagina.documento), int(pagina.pagina)))
        if guardadas:
            pagina = pagina.com_posicoes(guardadas)
        self._pagina = pagina
        self._pagina_rgb = folha_rgb
        self._folha_por_ler = None
        self._ignoradas.clear()
        if dpi:
            self._dpi = int(dpi)
        self._historico.clear()
        self._refeitos.clear()
        self._rotulos_do_historico.clear()
        self._rotulos_refeitos.clear()
        self._digitacao = None
        self.desenhar_documento(rico.de_pagina(pagina))
        self._documento_gravado = self.documento
        self._rascunho.stop()  # o desenho emitiu `documento_mudou`; a folha recém-lida não tem o que gravar
        self._correcoes = 0  # a folha recém-lida não tem correção nenhuma
        self._atualizar_status()

    def texto(self) -> str:
        """O texto puro do documento -- **do documento, e não do widget**.

        O widget tem a miniatura e a quebra do desenho; o documento não. É a mesma distinção que
        `_Mapa` mantém, do lado da exportação.
        """
        return self.documento.para_texto()


    # ------------------------------------------------------- estilo, alinhamento e corpo

    def estilo_titulo(self) -> None:
        self.aplicar_estilo(rico.ESTILO_TITULO)

    def estilo_prosa(self) -> None:
        self.aplicar_estilo(rico.ESTILO_PROSA)

    def estilo_notacao(self) -> None:
        self.aplicar_estilo(rico.ESTILO_NOTACAO)

    def estilo_legenda(self) -> None:
        self.aplicar_estilo(rico.ESTILO_LEGENDA)

    def alinhar_esquerda(self) -> None:
        self.alinhar(rico.ALINHAMENTO_ESQUERDA)

    def alinhar_centro(self) -> None:
        self.alinhar(rico.ALINHAMENTO_CENTRO)

    def alinhar_direita(self) -> None:
        self.alinhar(rico.ALINHAMENTO_DIREITA)

    def justificar(self) -> None:
        self.alinhar(rico.ALINHAMENTO_JUSTIFICADO)

    def aumentar_corpo(self) -> None:
        self.mudar_corpo(+1)

    def diminuir_corpo(self) -> None:
        self.mudar_corpo(-1)

    def corpo_normal(self) -> None:
        """Volta o parágrafo ao corpo do estilo dele -- degrau zero, e não "sem corpo"."""
        inicio, fim = self._intervalo()
        self._aplicar(rico.aplicar_no_paragrafo(self.documento, inicio, fim, corpo=0))

    def limpar_cor(self) -> None:
        """Tira a cor do autor. **Não** toca a faixa de confiança (S-242)."""
        self.pintar_letra("")

    def escolher_cor(self) -> None:
        """Abre a lista de cores da barra. O comando é a porta de menu do mesmo gesto."""
        self.escolha_de_cor.showPopup()

    def escolher_realce(self) -> None:
        """O mesmo para o realce. Sem lista na barra, o comando pinta com o primeiro papel."""
        self.escolha_de_realce.showPopup()

    # ------------------------------------------------------------------------- a caixa (S-262)

    def mudar_caixa(self, caixa: str) -> None:
        """MAIÚSCULAS, minúsculas ou Iniciais no alvo.

        **Muda o texto**, e por isso passa pela mesma pilha das outras ferramentas: o documento
        anterior é guardado antes do redesenho. Sem isso, desfazer uma troca de caixa sobre um
        parágrafo seria impossível.
        """
        inicio, fim = self._intervalo()
        self._aplicar(rico.mudar_caixa(self.documento, inicio, fim, caixa))

    def maiusculas(self) -> None:
        self.mudar_caixa(rico.CAIXA_ALTA)

    def minusculas(self) -> None:
        self.mudar_caixa(rico.CAIXA_BAIXA)

    def capitular(self) -> None:
        self.mudar_caixa(rico.CAIXA_INICIAIS)


    # ------------------------------------------------- a área de transferência (S-263)

    def selecionar_tudo(self) -> None:
        """Seleciona o texto inteiro da folha.

        **É uma correção, e não um acréscimo**: no `tk.Text` de fábrica `Ctrl+A` leva o cursor ao
        início da linha, e selecionar tudo não tinha tecla nem comando. O `QTextEdit` já faz o
        certo; o comando existe para ele ter menu, paleta e tecla como os outros quarenta e sete.
        """
        self.editor.selectAll()
        self.editor.setFocus()

    def recortar(self) -> None:
        self.editor.cut()

    def copiar(self) -> None:
        self.editor.copy()

    def colar(self) -> None:
        """Cola no cursor. **O texto colado herda os atributos dos dois lados**, como o digitado.

        O que **não** vem junto é formatação de outro programa: `setAcceptRichText(False)` recusa
        HTML colado, e o que entra é texto -- que é o mesmo contrato do outro frontend, onde a
        área de transferência do Tk carrega texto e não corridas.
        """
        self.editor.paste()

    @property
    def quebra(self) -> bool:
        """As linhas estão quebrando na largura da janela? É o que o estado guarda (S-291)."""
        return self.editor.lineWrapMode() != QTextEdit.LineWrapMode.NoWrap

    def definir_quebra(self, quebrando: bool, *, avisar: bool = False) -> None:
        """Põe a quebra naquele estado. Silencioso por padrão.

        **Separada de `quebrar_linha` porque restaurar não é alternar.** A restauração da abertura
        põe o que a sessão anterior tinha, e uma frase no rodapé anunciando isso seria um recado
        sobre algo que a pessoa não acabou de fazer -- é a mesma razão do `avisar=False` de
        `aplicar_zoom`.
        """
        self.editor.setLineWrapMode(
            QTextEdit.LineWrapMode.WidgetWidth if quebrando else QTextEdit.LineWrapMode.NoWrap
        )
        if not avisar:
            return
        if quebrando:
            self.estado.emit("As linhas voltam a quebrar na largura da janela.")
        else:
            self.estado.emit("Linha inteira: use a rolagem de baixo para ver o fim das linhas longas.")

    def quebrar_linha(self) -> None:
        """Liga ou desliga a quebra na largura da janela (S-265)."""
        self.definir_quebra(not self.quebra, avisar=True)

    # ------------------------------------------------------------- o zoom da vista (S-264)

    @property
    def zoom_da_vista(self) -> int:
        return self._zoom_da_vista

    def aproximar_texto(self) -> None:
        """Aumenta a letra **na tela**. Não muda o documento, não é gravado, não é exportado."""
        self._mudar_zoom(+1)

    def afastar_texto(self) -> None:
        self._mudar_zoom(-1)

    def zoom_do_texto_normal(self) -> None:
        """Volta a folha ao tamanho de tela normal."""
        self.aplicar_zoom(0)

    def _mudar_zoom(self, passo: int) -> None:
        """Um passo de zoom, **de parada em parada** (S-630): o degrau que não muda a letra é pulado.

        Andar degrau a degrau fazia o `−` não mudar nada perto do piso de legibilidade, onde dois
        degraus dão a mesma letra -- e um clique que não muda nada parece controle quebrado.
        """
        atual = self._zoom_da_vista
        adiante = [parada for parada in self._paradas_do_zoom if (parada > atual if passo > 0 else parada < atual)]
        if not adiante:
            limite = self._paradas_do_zoom[-1] if passo > 0 else self._paradas_do_zoom[0]
            self.estado.emit(f"O zoom do texto já está no limite ({limite:+d} degraus).")
            return
        self.aplicar_zoom(adiante[0] if passo > 0 else adiante[-1])

    def _zoom_ancorado(self, ponto: QPoint, passo: int) -> None:
        """O zoom da roda, **com a linha sob o ponteiro parada sob ele** (S-630).

        Sem âncora a folha cresce a partir do topo e o que a pessoa estava olhando foge para baixo
        a cada passo -- é a regra da roda do WordCraft. O caractere sob o ponteiro é lembrado antes
        e, depois do redesenho, a rolagem é acertada para ele voltar à mesma altura.
        """
        sob = self.editor.cursorForPosition(ponto)
        posicao = sob.position()
        antes = self.editor.cursorRect(sob)
        # Em que altura da linha o ponteiro estava: o meio da linha continua sendo o meio dela.
        fracao = (ponto.y() - antes.top()) / max(1, antes.height())
        self._mudar_zoom(passo)
        documento = self.editor.document()
        barra = self.editor.verticalScrollBar()
        if documento is None or barra is None or posicao >= documento.characterCount():
            return
        cursor = QTextCursor(documento)
        cursor.setPosition(posicao)
        depois = self.editor.cursorRect(cursor)
        barra.setValue(barra.value() + round(depois.top() + fracao * depois.height()) - ponto.y())

    def aplicar_zoom(self, degraus: int, *, avisar: bool = True) -> None:
        """Troca a fonte de base do editor e redesenha.

        **Aqui o redesenho é barato, e é a diferença de fundo com o outro frontend.** Lá redesenhar
        zera a pilha de desfazer do Tk -- ela guarda índice, não conteúdo --, e por isso o zoom tem
        de refazer cada etiqueta de fonte à mão, com o cache de atributos de origem que a S-336
        conserta. Aqui a pilha é de documentos e sobrevive ao redesenho, então o zoom é uma fonte
        nova e um `_desenhar`.

        **Grampeia aqui** (S-291): os limites são desta aba, e validá-los no arquivo de estado os
        declararia num segundo lugar.
        """
        from chess_diagram_ocr.ui import tipografia

        degraus = max(ZOOM_MINIMO, min(ZOOM_MAXIMO, int(degraus)))
        self._zoom_da_vista = degraus
        selecao = self._selecao_atual()
        fonte = self.editor.font()
        fonte.setPointSize(tipografia.corpo(degraus, base=self._corpo_de_base))
        self.editor.setFont(fonte)
        self._desenhar(selecao=selecao)
        self._mostrar_zoom()
        if avisar:
            self.estado.emit(f"Zoom do texto: {degraus:+d} degrau(s).")


    # --------------------------------------------------- busca e substituição (S-343)

    def achar(self) -> JanelaDeBusca:
        """Abre a janela de busca. Uma por vez -- reabrir traz a que já está aberta."""
        return self._abrir_busca(substituindo=False)

    def substituir(self) -> JanelaDeBusca:
        """Abre a mesma janela, já com o campo de substituição à mostra."""
        return self._abrir_busca(substituindo=True)

    def _abrir_busca(self, *, substituindo: bool) -> JanelaDeBusca:
        janela = self._janela_de_busca
        if isinstance(janela, JanelaDeBusca) and not janela.isHidden():
            janela.mostrar(substituindo=substituindo)
            return janela
        janela = JanelaDeBusca(self, substituindo=substituindo)
        self._janela_de_busca = janela
        return janela

    def mostrar_intervalo(self, inicio: int, fim: int) -> None:
        """Rola até aquele trecho e o seleciona. É o que a lista da busca chama ao clicar."""
        cursor = self.editor.textCursor()
        cursor.setPosition(self._mapa.posicao(inicio))
        cursor.setPosition(self._mapa.posicao(fim), QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()
        self.editor.setFocus()

    def aplicar_substituicao(self, ocorrencias: Sequence[busca.Ocorrencia], novo: str) -> int:
        """Troca as ocorrências escolhidas e redesenha. Devolve quantas trocou.

        O documento anterior vai para a pilha **antes** do redesenho: é o que faz `desfazer`
        reverter a substituição **inteira**, e não troca a troca.
        """
        novo_doc = busca.substituir(self.documento, ocorrencias, novo)
        if novo_doc.para_texto() == self.documento.para_texto():
            return 0
        self._aplicar(novo_doc)
        return len(ocorrencias)

    # ----------------------------------------------------- a conferência do léxico (S-266)

    def marcar_fora_do_lexico(self) -> None:
        """Liga a conferência do léxico da S-209. **Não corrige nada** (S-266).

        A frase da S-209 é a especificação inteira deste comando: *"palavra fora do dicionário é
        sinalizada, nunca aproximada da mais parecida"*. Dos 18 lances tão maltratados que caem no
        léxico, nenhum está no dicionário -- com correção automática seriam 18 lances reescritos
        como palavra.

        **Ligar, e não marcar uma vez** (S-293): toda ferramenta que muda texto redesenha, e o
        redesenho apaga a marcação -- então corrigir a primeira palavra marcada apagava as outras.
        """
        self._conferindo_lexico = True
        self._conferir_lexico(avisar=True)

    def limpar_marcas_do_lexico(self) -> None:
        """Desliga a conferência e tira as marcas. **Não é desfazer**: elas nunca foram documento."""
        self._conferindo_lexico = False
        self._pintar_lexico(())

    def _conferir_lexico(self, *, avisar: bool) -> None:
        """Refaz a marcação. `avisar=False` no redesenho: a conta já foi dita quando se ligou.

        Um rodapé reescrito a cada tecla seria ruído -- e pior, esconderia o que a ferramenta que
        acabou de rodar tinha a dizer.
        """
        from chess_diagram_ocr.text import dicionario

        conteudo = self.documento.para_texto()
        try:
            lexico = dicionario.carregar()
        except OSError as erro:
            logger.debug("Léxico não carregou: %s", erro)
            self.estado.emit(f"O léxico não pôde ser carregado: {erro}")
            return
        if self._caderno is not None:
            lexico = lexico | self._caderno.lexico()
        achadas = dicionario.desconhecidas(conteudo, lexico, ignorar=fora_do_livro(self.documento))
        achadas = tuple(a for a in achadas if a[2].lower() not in self._ignoradas)
        # **A palavra em digitação não é marcada até terminar** (S-657): com o cursor colado no fim
        # dela e nada que a feche, ela ainda está sendo escrita.
        cursor = self._mapa.deslocamento(self.editor.textCursor().position())
        achadas = tuple(
            a for a in achadas if not (a[0] <= cursor == a[1] and (a[1] == len(conteudo) or conteudo[a[1]].isalnum()))
        )
        self._pintar_lexico([(inicio, fim) for inicio, fim, _palavra in achadas])
        if avisar:
            total = len(dicionario.palavras_de(conteudo))
            self.estado.emit(frase_do_lexico([palavra for _inicio, _fim, palavra in achadas], total))

    def _pintar_lexico(self, intervalos: Iterable[tuple[int, int]]) -> None:
        """A marca é uma **borda ondulada**, e o canal estava livre (S-266).

        A cor da letra é a faixa de confiança, o fundo é o realce do autor, a fonte é o estilo mais
        o corpo, e negrito/itálico/sublinhado/tachado são os quatro pincéis de ênfase. Uma quinta
        marca em qualquer um deles seria a mesma tinta com dois significados na mesma linha.

        **`setExtraSelections` e não formato de caractere**: a marcação não é do documento, e
        escrevê-la no `QTextCharFormat` a faria voltar de `toHtml` e atravessar a gravação.
        """
        from PyQt6.QtGui import QColor, QTextCharFormat

        seletores: list[QTextEdit.ExtraSelection] = []
        intervalos = list(intervalos)
        self._fora_do_lexico = sorted(intervalos)
        if hasattr(self, "caixa_do_lexico"):
            self.caixa_do_lexico.setText(f"{len(intervalos)} fora do léxico")
            self.caixa_do_lexico.setVisible(self._conferindo_lexico and not self.recado.isVisible())
        for inicio, fim in intervalos:
            selecao = QTextEdit.ExtraSelection()
            formato = QTextCharFormat()
            formato.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            formato.setUnderlineColor(QColor(tema.cor_atual(tokens.PROBLEMA_TEXTO)))
            selecao.format = formato
            cursor = QTextCursor(self.editor.document())
            cursor.setPosition(self._mapa.posicao(inicio))
            cursor.setPosition(self._mapa.posicao(fim), QTextCursor.MoveMode.KeepAnchor)
            selecao.cursor = cursor
            seletores.append(selecao)
        self.editor.setExtraSelections(seletores)


    # --------------------------------------------------- os símbolos e a paleta (S-248)

    def _paleta_de_glifos(self) -> object:
        """A paleta, carregada uma vez. Ela lê o metadado do modelo, e isso custa disco."""
        if self._paleta is None:
            from chess_diagram_ocr.text import paleta as _paleta

            self._paleta = _paleta.paleta()
        return self._paleta

    def inserir_simbolo(self, simbolo: str) -> None:
        """Insere o glifo no cursor, **marcando a corrida** se o modelo não o lê (S-247).

        A marca é `fora_do_modelo`, e ela viaja com o documento: sobrevive a salvar, reabrir e
        exportar, e é o que diz a quem receber o arquivo que aquele caractere não veio da página.

        Passa pela pilha, como toda mudança de texto: `rico.inserir` herda os atributos de quem
        está à esquerda -- quem põe uma figurina no meio de um lance em negrito quer a figurina em
        negrito --, e `fora_do_modelo` entra por cima, porque é declaração sobre o que foi
        inserido e não sobre o que estava lá.
        """
        if not simbolo:
            return
        inicio, _fim = self._intervalo()
        fora = bool(self._paleta_de_glifos().marca(simbolo))  # type: ignore[attr-defined]
        self._lembrar_glifo(simbolo)
        depois = inicio + len(simbolo)
        self._aplicar(rico.inserir(self.documento, inicio, simbolo, fora_do_modelo=fora), selecao=(depois, depois))
        self.editor.setFocus()

    def _menu_de_simbolos(self, simbolos: tuple[str, ...]) -> QMenu:
        """A lista junto do ponteiro. **Marca o que o modelo não lê**, e é o item.

        Um glifo que o classificador não conhece continua sendo inserível -- ele vai para o
        `.cvtxt` e para a exportação --, mas quem o insere precisa saber que a folha lida nunca vai
        trazê-lo de volta. A marca é do `text/paleta.py`, e não escrita aqui.
        """
        from PyQt6.QtGui import QAction, QCursor
        from PyQt6.QtWidgets import QMenu

        paleta_atual = self._paleta_de_glifos()
        menu = QMenu(self)
        for simbolo in simbolos:
            rotulo = f"{simbolo}  ·  fora do modelo" if paleta_atual.marca(simbolo) else simbolo  # type: ignore[attr-defined]
            acao = QAction(rotulo, menu)
            acao.triggered.connect(lambda _marcado=False, glifo=simbolo: self.inserir_simbolo(glifo))
            menu.addAction(acao)
        menu.popup(QCursor.pos())
        return menu

    def inserir_figurina(self) -> QMenu:
        """Abre a lista de figurinas junto do ponteiro -- a porta de menu do mesmo gesto (S-248)."""
        from chess_diagram_ocr.text import paleta as _paleta

        return self._menu_de_simbolos(_paleta.figurinas(self._paleta_de_glifos()))  # type: ignore[arg-type]

    def inserir_avaliacao(self) -> QMenu:
        """O mesmo para os símbolos de avaliação."""
        from chess_diagram_ocr.text import paleta as _paleta

        return self._menu_de_simbolos(_paleta.avaliacoes(self._paleta_de_glifos()))  # type: ignore[arg-type]

    def alternar_paleta(self) -> None:
        """Abre ou fecha o painel lateral de glifos. **O foco não sai do texto** (S-248)."""
        if self.paleta_lateral.isVisible():
            self.paleta_lateral.hide()
        else:
            self.paleta_lateral.show()
        self.editor.setFocus()

    # ------------------------------------------------------------- o arquivo (S-343)

    def abrir_documento(self) -> None:
        """Abre um `.cvtxt` gravado antes, com os diagramas de volta se o livro ainda estiver lá."""
        from chess_diagram_ocr.text import arquivo

        # A folha vai ao caderno **antes** de trocar (S-611), e a pergunta só sobra sem ele -- e aí
        # o rascunho já foi ao disco, como em `confirmar_fechamento` (S-605).
        if not self._guardar_a_folha() and not self._confirmar_descarte("Abrir outro arquivo descarta as alterações."):
            return
        origem, _filtro = QFileDialog.getOpenFileName(
            self, "Abrir texto de folha", "", f"{arquivo.NOME_DO_FORMATO} (*{arquivo.EXTENSAO});;Todos (*.*)"
        )
        if not origem:
            return
        try:
            doc = arquivo.carregar(Path(origem))
        except (arquivo.ArquivoInvalido, OSError) as erro:
            logger.debug("Documento não abriu (%s): %s", origem, erro)
            QMessageBox.critical(self, "Texto", str(erro))
            return
        self.abrir(doc)
        self._caminho_do_documento = Path(origem)  # `Salvar` grava de volta aqui (S-343)
        # Abrir para olhar não troca a folha do caderno; a primeira edição troca, e a folha que o
        # caderno tinha fica como `anterior` (S-616).
        self._vai_ao_caderno = False
        cad = self._caderno_da_tela()
        if cad is not None and doc.origem is not None:
            cad.visitar(doc.origem.pagina)

    def abrir(self, doc: rico.DocumentoRico, *, folha_rgb: np.ndarray | None = None, renderizar: bool = True) -> None:
        """Põe o documento na tela e recupera o que só o PDF pode dar: as miniaturas (S-238).

        **O PDF ausente não é erro.** O texto abre igual, as miniaturas faltam, e o rodapé diz
        qual livro não foi encontrado -- a regra de degradação de `ui/theme.py`. O contrário faria
        uma pasta de trabalho movida de lugar bloquear o acesso ao que se corrigiu nela.

        `folha_rgb` é a folha já renderizada, quando quem chama a tem -- o rascunho recuperado é
        da folha que acabou de ser lida, e renderizá-la de novo seria pagar duas vezes.
        `renderizar=False` é de quem vai rasterizá-la fora da thread da janela (`_abrir_do_caderno`).
        """
        from chess_diagram_ocr.text import arquivo

        self._pagina = doc.origem
        self._pagina_rgb = folha_rgb
        self._folha_por_ler = None
        self._historico.clear()
        self._refeitos.clear()
        self._rotulos_do_historico.clear()
        self._rotulos_refeitos.clear()
        self._digitacao = None
        # Documento novo na tela, arquivo de destino zerado: gravar aqui é a **primeira** vez
        # deste documento, e "Salvar" volta a perguntar onde (S-343). Quem abriu de um arquivo
        # repõe o caminho logo depois, em `abrir_documento`.
        self._caminho_do_documento = None
        aviso = ""
        caminho = arquivo.pdf_de(doc)
        if folha_rgb is None and caminho is not None and doc.origem is not None:
            if caminho.exists():
                if renderizar:
                    self._dpi = self._dpi_para_ler()
                    self._pagina_rgb = _renderizar(caminho, doc.origem.pagina, dpi=self._dpi)
            else:
                aviso = f" · o livro {caminho.name} não está no lugar de antes: sem miniaturas"
        if doc.origem is not None:
            self._pagina_indice = int(doc.origem.pagina)
            self.campo_de_folha.setValue(self._pagina_indice + 1)
        self.desenhar_documento(doc)
        self._documento_gravado = self.documento
        self._rascunho.stop()  # como em `mostrar_pagina`: o que veio do disco não tem o que gravar
        self._contar_correcoes()  # o arquivo pode trazer correções gravadas ontem
        # O texto da folha 14 na tela com o visualizador na folha 3 é o que fazia a pessoa
        # procurar a página à mão (item 9). Só para o livro que está aberto: um `.cvtxt` de outro
        # livro não troca o livro de ninguém -- é a mesma regra de `definir_livro`.
        if doc.origem is not None and caminho is not None and self._pdf is not None and _mesmo_livro(caminho, self._pdf):
            self.folha_pedida.emit(self._pagina_indice)
        diagramas = len(self.documento.diagramas)
        figuras = sum(1 for c in self.documento.diagramas if self._tem_miniatura(c))
        resumo = f"Texto aberto: {len(self.documento.corridas)} trecho(s), {diagramas} diagrama(s)"
        if diagramas and not aviso:
            resumo += f" ({figuras} com miniatura)"
        self.estado.emit(resumo + aviso + ".")

    def salvar_documento(self) -> None:
        """Grava o `.cvtxt` **no arquivo já escolhido**, e só pergunta na primeira vez (S-343).

        **"Salvar" e "Salvar como…" eram o mesmo comando**, e os dois perguntavam o destino: o
        catálogo mostrava dois rótulos, o menu dois itens e a paleta duas linhas para uma coisa só.
        Num ciclo de correção, em que se grava a cada trecho conferido, o diálogo repetido é o
        atrito -- e o rótulo "como…" prometia uma escolha que o outro tomava do mesmo jeito.
        """
        self._salvar_documento_em(self._caminho_do_documento)

    def salvar_documento_como(self) -> None:
        """Pergunta o destino e passa a gravar nele."""
        self._salvar_documento_em(None)

    def _salvar_documento_em(self, caminho: Path | None) -> None:
        from chess_diagram_ocr.text import arquivo

        if not self.documento.para_texto().strip():
            # Rodapé e não caixa, como a exportação: é um passo que falta, não uma escolha. O Tk
            # já recusava; o porte gravava um `.cvtxt` vazio e dizia «Texto gravado» (item 19).
            self.estado.emit("Não há texto nesta aba para salvar: leia uma folha ou abra um arquivo.")
            return
        if caminho is None:
            escolhido, _filtro = QFileDialog.getSaveFileName(
                self,
                "Salvar o texto da folha",
                arquivo.sugestao_de_nome(self.documento),
                f"{arquivo.NOME_DO_FORMATO} (*{arquivo.EXTENSAO});;Todos (*.*)",
            )
            if not escolhido:
                return
            caminho = Path(escolhido)
        # **A marcação é aplicada aqui, e não só no arquivo** (S-239): o que se grava é o que fica
        # na tela. Ela é derivada da `PaginaLida`, é idempotente, e não toca no que o motor leu --
        # e o que a mão corrigiu deixa de ser pintado como palpite do motor.
        gravado = correcao.com_procedencia_humana(self.documento)
        try:
            arquivo.gravar(caminho, gravado)
        except OSError as erro:
            QMessageBox.critical(self, "Texto", f"Não foi possível gravar:\n{erro}")
            return
        if gravado is not self.documento:
            # Sem passar pela pilha: a procedência não é edição de ninguém, e um `Ctrl+Z` que a
            # tirasse devolveria a tinta de "revisar" a um trecho já conferido e gravado.
            self._digitacao = None
            self.documento = gravado
            self._desenhar(selecao=self._selecao_atual())
        self._documento_gravado = gravado
        self._caminho_do_documento = caminho
        # O trabalho chegou a um lugar melhor: o rascunho da S-255 sai.
        self._rascunho.stop()
        if self._pagina is not None:
            rascunho.descartar(self._pagina.documento, self._pagina.pagina, pasta=self._pasta_de_rascunhos)
        # A conta aparece porque a correção é o que o `.cvtxt` tem de mais caro -- e porque um
        # número no rodapé é o que faz alguém notar quando ele vem zerado (S-239).
        feitas = len(correcao.correcoes(gravado))
        quanto = f" · {feitas} correção(ões) sobre o que o motor leu" if feitas else ""
        self._correcoes = feitas
        self._atualizar_status()
        self.estado.emit(f"Texto gravado em {caminho.name}{quanto}.")

    @property
    def tem_alteracoes(self) -> bool:
        """A folha tem edição que ainda não está no disco? É o que o fechamento e a releitura perguntam.

        **Comparada com o que foi gravado, e não com a pilha.** A pilha dizia "editado" também
        depois de gravar -- e aí a pergunta "descarta as alterações?" chegava sobre um texto que já
        estava salvo, que é o jeito de ensinar a clicar "Sim" sem ler. Desfazer até o que estava
        gravado também não deixa nada a perder, e a comparação por valor vê isso.
        """
        return self.documento != self._documento_gravado

    def confirmar_fechamento(self) -> bool:
        """A janela vai fechar: `True` se pode, perguntando antes quando há texto por gravar.

        **O rascunho vai para o disco antes da pergunta** (S-255): o relógio de inatividade pode
        não ter disparado, e fechar -- com "Sim", sem tela, ou pela falha que vem a seguir -- é
        exatamente o momento para o qual ele existe. Gravar de novo o que já está lá não custa.

        Com o caderno (S-611) não há pergunta: a folha vai para ele, e a trava sai.
        """
        if self._guardar_a_folha():
            self.fechar_caderno()
            return True
        return self._confirmar_descarte("Fechar a janela descarta as alterações.", ao_fechar=True)

    # ----------------------------------------------------------- o caderno do livro (S-610)

    def _caderno_da_tela(self) -> caderno.Caderno | None:
        """O caderno em que a folha da tela mora: o do livro aberto, se ela for dele."""
        origem = self.documento.origem
        if self._caderno is None or origem is None:
            return None
        if _chave_de_livro(origem.documento) != _chave_de_livro(self._livro_do_caderno):
            return None
        return self._caderno

    @property
    def caderno_aberto(self) -> caderno.Caderno | None:
        """O caderno do livro aberto, para quem pergunta por ele -- o índice das folhas (S-613)."""
        return self._caderno

    def folhas_para_a_suite(self, paginas: Sequence[int] | None) -> list[dict[str, Any]]:
        """As folhas corrigidas do caderno, para o EPUB/DOCX do livro que a suíte escreve (R7).

        A suíte chama isto na thread da janela, depois do diálogo e antes de começar; `paginas` é o
        alcance escolhido nele (0-based, `None` = o livro). A folha da tela entra como está.
        """
        from chess_diagram_ocr.text import caderno_na_suite

        if self._caderno is None:
            return []
        self._guardar_a_folha()
        return caderno_na_suite.folhas_para_a_suite(self._caderno, paginas)

    def folhas_do_livro(self, livro: Path | str, paginas: Sequence[int] | None) -> list[dict[str, Any]]:
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

    def _guardar_a_folha(self) -> bool:
        """Guarda a folha da tela no caderno, se ela mudou (S-611). Devolve se o trabalho está a salvo.

        Toda troca do que está na tela -- ler outra folha, abrir um arquivo, trocar de livro,
        fechar -- passa por aqui antes, e por isso a pergunta "descarta as alterações?" saiu desses
        caminhos: não há mais o que descartar. **Sem caderno** -- a aba de teste, o livro que não
        abre, o caderno que outra janela trava -- a rede é o rascunho de antes, e `False` com
        alteração por gravar diz a quem chama que a pergunta continua.
        """
        self._rascunho.stop()
        cad = self._caderno_da_tela()
        if cad is None or cad.somente_leitura:
            self.gravar_rascunho()
            return not self.tem_alteracoes
        if not self._vai_ao_caderno:
            return not self.tem_alteracoes
        pagina = int(self.documento.origem.pagina)  # type: ignore[union-attr]  # `_caderno_da_tela` viu a origem
        feitas = len(correcao.correcoes(self.documento))
        try:
            feito = cad.gravar(correcao.com_procedencia_humana(self.documento), correcoes=feitas)
        except OSError as erro:
            logger.warning("O caderno não gravou a folha %d: %s", pagina + 1, erro)
            self.estado.emit(f"O caderno não gravou a folha {pagina + 1}: {erro}. O texto continua na tela.")
            self.gravar_rascunho()
            return False
        if feito == caderno.RECUSADA_VAZIA:
            self.estado.emit(f"A folha {pagina + 1} vazia não foi gravada por cima do texto que o caderno tem dela.")
            return True
        self._documento_gravado = self.documento
        self._correcoes = feitas
        self._atualizar_status()
        self._rotular_leitura()
        self._mostrar_indice()
        return True

    def _abrir_caderno(self, livro: Path | None) -> None:
        """Troca o caderno pelo do livro que chegou. A folha da tela vai antes ao do livro que sai."""
        self._guardar_a_folha()
        self.fechar_caderno()
        if self._pasta_de_cadernos is None or livro is None or not livro.exists():
            return
        self._caderno = caderno.abrir(livro, pasta=self._pasta_de_cadernos)
        self._livro_do_caderno = livro
        if self._caderno is None:
            return
        if self._caderno.somente_leitura:
            self.estado.emit(self._caderno.motivo)
        else:
            self._trazer_rascunhos(livro)
        self._mostrar_indice()

    def fechar_caderno(self) -> None:
        """Solta a trava do caderno aberto. Na troca de livro e no fechamento da janela."""
        if self._caderno is not None:
            self._caderno.fechar()
        self._caderno = None
        self._livro_do_caderno = None
        self._mostrar_indice()

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
                doc = _no_livro(rascunho.carregar(achado), livro)
                entrou = cad.trazer_rascunho(doc, achado.quando, correcoes=len(correcao.correcoes(doc)))
            except (OSError, ValueError) as erro:  # `ArquivoInvalido` é um `ValueError`; o rascunho fica
                logger.debug("Rascunho %s não entrou no caderno: %s", achado.caminho, erro)
                continue
            if entrou:
                trazidas.append(achado.folha + 1)
            else:
                logger.info("Rascunho da folha %d mais velho que o caderno: descartado.", achado.folha + 1)
            rascunho.descartar(livro, achado.folha, pasta=self._pasta_de_rascunhos)
        if trazidas:
            self.estado.emit(
                f"{len(trazidas)} rascunho(s) deste livro entraram no caderno (folha "
                f"{', '.join(map(str, trazidas[:6]))}{'…' if len(trazidas) > 6 else ''})."
            )

    def _rotular_leitura(self) -> None:
        """«Abrir folha» quando a folha do campo tem caderno, «Ler folha» quando o motor vai ler."""
        if not hasattr(self, "botao_de_ler"):
            return
        guardada = None if self._caderno is None else self._caderno.estado(int(self.campo_de_folha.value()) - 1)
        abre = guardada is not None and caderno.abre_do_caderno(guardada, motor=self._motor, modo_bloco=self._modo_bloco)
        self.botao_de_ler.setText(strings.ABRIR_FOLHA_DO_CADERNO if abre else comandos.rotulo_de_botao("ler_folha"))

    def _abrir_do_caderno(self, indice: int) -> bool:
        """Põe na tela a folha que o caderno tem, sem motor (S-612). `False` se o arquivo não abriu."""
        cad = self._caderno
        doc = None if cad is None else cad.folha(indice)
        if cad is None or doc is None:
            return False
        dpi = self._dpi_para_ler()
        pronta = self._fornecedor_de_folha(indice) if self._fornecedor_de_folha is not None else None
        folha_rgb = np.array(pronta[0], copy=True) if pronta is not None and int(pronta[1]) == dpi else None
        if folha_rgb is not None:
            self._dpi = dpi
        self.abrir(_no_livro(doc, self._livro_do_caderno), folha_rgb=folha_rgb, renderizar=False)
        if folha_rgb is None:
            self._renderizar_ao_fundo(indice)
        cad.visitar(indice)
        self._vai_ao_caderno = True
        self._mostrar_indice()  # a linha marcada do índice acompanha a folha que abriu
        guardada = cad.estado(indice)
        feitas = 0 if guardada is None else guardada.correcoes
        self.estado.emit(
            f"Folha {indice + 1} aberta do caderno"
            + (f", com {caderno.correcoes_por_extenso(feitas)}" if feitas else "")
            + ". «Ler a folha de novo» fica no menu do botão direito."
        )
        return True

    def _renderizar_ao_fundo(self, indice: int) -> None:
        """A folha aberta do caderno, rasterizada **fora** da thread da janela (S-612).

        O texto entra na hora; as miniaturas chegam quando a folha chegar. Renderizar aqui, como o
        `abrir` de um `.cvtxt` faz, congelava a troca de folha por um a três décimos de segundo a
        cada «Abrir folha» -- o gesto que a aba mais repete. A resposta que chegar para uma folha
        que já saiu da tela é jogada fora.
        """
        livro = self._livro_do_caderno
        if livro is None or not livro.exists():
            return
        dpi = self._dpi_para_ler()
        self._folha_pedida_ao_fundo = indice
        tarefa = Tarefa(lambda: (indice, dpi, _renderizar(livro, indice, dpi=dpi)), parent=self, nome="folha do caderno")
        tarefa.pronto.connect(self._folha_chegou)
        self._renderizacao = tarefa
        tarefa.start()

    def _folha_chegou(self, resultado: object) -> None:
        """A folha rasterizada ao fundo: as miniaturas entram, sem mexer no texto, na seleção nem na pilha."""
        indice, dpi, imagem = cast("tuple[int, int, np.ndarray | None]", resultado)
        if imagem is None or indice != self._folha_pedida_ao_fundo:
            return
        if self._pagina is None or int(self._pagina.pagina) != indice or self._caderno_da_tela() is None:
            return
        self._pagina_rgb = imagem
        self._dpi = int(dpi)
        if self.documento.diagramas:
            self._redesenhar_a_vista()
            return
        self._atualizar_status()
        self._mostrar_impresso()

    def _confirmar_releitura(self, indice: int, correcoes: int) -> bool:
        from chess_diagram_ocr.qt import dialogos

        if not dialogos.ha_quem_responda():
            logger.warning("Ler de novo a folha %d com correções pede resposta, e não há tela: fica como está.", indice + 1)
            return False
        resposta = QMessageBox.question(
            self,
            "Texto",
            caderno.frase_de_releitura(indice, correcoes),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return resposta == QMessageBox.StandardButton.Yes

    def ler_de_novo(self) -> None:
        """O motor lê de novo a folha da tela, mesmo com caderno -- e pergunta se há correção a perder."""
        if self._pagina is not None:
            self.campo_de_folha.setValue(int(self._pagina.pagina) + 1)
        self._ler_folha(de_novo=True)

    def voltar_a_anterior(self) -> bool:
        """Põe na tela a versão de quando a pessoa chegou da última vez à folha (S-611). `Ctrl+Z` desfaz."""
        cad = self._caderno_da_tela()
        anterior = None if cad is None else cad.anterior(self.documento.origem.pagina)  # type: ignore[union-attr]
        if anterior is None:
            self.estado.emit("Esta folha não tem versão anterior no caderno.")
            return False
        self._aplicar(_no_livro(anterior, self._livro_do_caderno))
        self._contar_correcoes()
        self.estado.emit("A versão anterior da folha está na tela; Ctrl+Z volta à de agora.")
        return True

    def descartar_correcoes(self) -> bool:
        """Devolve a folha ao que o motor leu (S-616). A corrigida fica como `anterior`, e `Ctrl+Z` a traz.

        É o único caminho em que a pergunta "descarta?" continua, porque aqui ela é o gesto pedido.
        """
        from chess_diagram_ocr.qt import dialogos

        cad = self._caderno_da_tela()
        if cad is None:
            return False
        pagina = int(self.documento.origem.pagina)  # type: ignore[union-attr]
        lida = cad.lida(pagina)
        if lida is None:
            self.estado.emit("O caderno não tem a leitura do motor desta folha.")
            return False
        if not dialogos.ha_quem_responda():
            return False
        resposta = QMessageBox.question(
            self,
            "Texto",
            f"Descartar as correções da folha {pagina + 1}? A folha volta ao que o motor leu; a versão "
            "corrigida fica como anterior, e Ctrl+Z a traz de volta.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return False
        self._guardar_a_folha()  # a corrigida está no caderno antes de sair da tela
        cad.visitar(pagina)  # e vira `anterior` na gravação que vem
        self._aplicar(_no_livro(lida, self._livro_do_caderno))
        self._guardar_a_folha()
        self._contar_correcoes()
        self.estado.emit(f"A folha {pagina + 1} voltou ao que o motor leu; Ctrl+Z traz as correções de volta.")
        return True

    def marcar_conferida(self) -> bool:
        """Marca a folha da tela como conferida no índice do caderno -- ou desmarca, se ela já está."""
        cad = self._caderno_da_tela()
        if cad is None:
            return False
        pagina = int(self.documento.origem.pagina)  # type: ignore[union-attr]
        self._guardar_a_folha()
        guardada = cad.estado(pagina)
        if guardada is None:
            return False
        conferida = guardada.estado != caderno.CONFERIDA
        novo = caderno.CONFERIDA if conferida else (caderno.EDITADA if guardada.correcoes else caderno.LIDA)
        if not cad.marcar(pagina, novo):
            return False
        self._mostrar_indice()
        self._atualizar_status()
        self.estado.emit(
            f"Folha {pagina + 1} {'conferida' if conferida else 'desmarcada'}: "
            f"{cad.conferidas()} folha(s) conferida(s) neste caderno."
        )
        return True

    def alternar_indice(self) -> None:
        """Abre ou fecha o índice das folhas do caderno (S-613), a aba Folhas do painel de navegação."""
        if self.indice.isVisible():
            self.navegacao.hide()
        else:
            self._mostrar_navegacao(FOLHAS)
            if self._caderno is None:
                self.estado.emit("O índice lista as folhas do caderno do livro aberto: abra um livro e leia uma folha.")
        self.editor.setFocus()

    def alternar_navegacao(self) -> None:
        """Abre ou fecha o painel de navegação (S-654). O foco não sai do texto."""
        if self.navegacao.isVisible():
            self.navegacao.hide()
        else:
            self._mostrar_navegacao(None)
        self.editor.setFocus()

    def mostrar_correcoes(self) -> None:
        """A lista das correções da folha (Revisão › Correções), na aba Correções do painel."""
        self._mostrar_navegacao(CORRECOES)

    def _mostrar_navegacao(self, aba: int | None) -> None:
        self.navegacao.show()
        if aba is not None:
            self.navegacao.setCurrentIndex(aba)
        self._refazer_navegacao()

    def _refazer_navegacao(self) -> None:
        """Refaz a aba à vista do painel. Na pausa da digitação, e não por tecla (S-654)."""
        if not self.navegacao.isVisible():
            return
        aba = self.navegacao.currentIndex()
        if aba == FOLHAS:
            self._mostrar_indice()
        elif aba == RESULTADOS:
            self._refazer_resultados()
        elif aba == CORRECOES:
            linhas = []
            for achada in correcao.correcoes(self.documento) if self.documento.origem is not None else ():
                onde = rico.deslocamento_do_bloco(self.documento, achada.bloco)
                linhas.append((-1 if onde is None else onde, f"«{achada.antes}» → «{achada.depois}»"))
            self.navegacao.mostrar_correcoes(linhas)
        else:
            self.navegacao.mostrar_titulos(rico.titulos(self.documento))

    def _refazer_resultados(self) -> None:
        agulha, inteira, curinga = self.navegacao.opcoes_da_busca()
        texto = self.documento.para_texto()
        try:
            achados = busca.achar(self.documento, agulha, palavra_inteira=inteira, curinga=curinga)
        except (ValueError, re.error) as erro:
            self.navegacao.mostrar_resultados(texto, (), recado=f"Curinga inválido: {erro}")
            return
        self.navegacao.mostrar_resultados(texto, achados)

    def _ir_para_intervalo(self, inicio: int, fim: int) -> None:
        """Uma linha do painel clicada: o cursor (ou a seleção) vai para lá, e a folha rola até ela."""
        self.mostrar_intervalo(inicio, fim) if fim > inicio else self._por_o_cursor(inicio)

    def _por_o_cursor(self, deslocamento: int) -> None:
        cursor = self.editor.textCursor()
        cursor.setPosition(self._mapa.posicao(deslocamento))
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()
        self.editor.setFocus()

    # ----------------------------------------------------------- o pincel de formatação (S-653)

    def pincel_de_formatacao(self) -> None:
        """Um clique arma o pincel para um uso; o segundo clique logo em seguida o fixa; `Esc` desarma."""
        from PyQt6.QtWidgets import QApplication

        agora = self._relogio()
        if self._pincel is not None:
            if agora - self._pincel_armado_em <= QApplication.doubleClickInterval() / 1000:
                self._pincel_fixo = True
                self.estado.emit("Pincel fixo: cada seleção recebe a formatação. Esc desarma.")
                return
            self._desarmar_pincel()
            return
        self.copiar_formato()
        self._pincel_armado_em = agora

    def copiar_formato(self) -> None:
        """`Ctrl+Shift+C`: guarda a formatação do começo da seleção e arma o pincel."""
        inicio, _fim = self._intervalo()
        atributos = rico.atributos_em(self.documento, inicio)
        if atributos is None:
            self.estado.emit("Não há trecho de onde copiar a formatação.")
            return
        self._pincel = atributos
        self._pincel_fixo = False
        self._pincel_armado_em = self._relogio()
        folha = self.editor.viewport()
        if folha is not None:
            folha.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fita.marcar({"pincel_de_formatacao": True})
        self.estado.emit("Pincel armado: selecione o trecho que recebe a formatação (Esc desarma).")

    def colar_formato(self) -> None:
        """`Ctrl+Shift+V`: pinta a seleção com a formatação guardada, sem desarmar o pincel fixo."""
        if self._pincel is None:
            self.estado.emit("Não há formatação copiada: use o pincel ou Ctrl+Shift+C antes.")
            return
        inicio, fim = self._intervalo()
        comeco, final = rico.intervalo_de_paragrafo(self.documento, inicio, fim)
        inteiros = fim > inicio and (comeco, final) == (inicio, fim)
        self._rotulo_corrente = "Pincel de formatação"
        try:
            self._aplicar(rico.pintar(self.documento, inicio, fim, self._pincel, paragrafo=inteiros))
        finally:
            self._rotulo_corrente = ""
        if not self._pincel_fixo:
            self._desarmar_pincel()

    def _desarmar_pincel(self) -> None:
        self._pincel = None
        self._pincel_fixo = False
        folha = self.editor.viewport()
        if folha is not None:
            folha.unsetCursor()
        self.fita.marcar({"pincel_de_formatacao": False})

    def _sair_com_esc(self) -> bool:
        """`Esc` desarma o pincel, e depois sai do modo foco (S-653, S-658). Devolve se fez algo."""
        if self._pincel is not None:
            self._desarmar_pincel()
            self.estado.emit("Pincel desarmado.")
            return True
        if self._modo_foco:
            self.alternar_modo_foco()
            return True
        return False

    # ------------------------------------------------------- o modo foco e as marcas (S-658)

    def alternar_modo_foco(self) -> None:
        """Só a folha: a fita e o painel de navegação somem, e a mesa esconde o visualizador. `Esc` sai."""
        self._modo_foco = not self._modo_foco
        self.fita.setVisible(not self._modo_foco)
        self.barra_do_foco.setVisible(self._modo_foco)
        if self._modo_foco:
            self._navegacao_antes_do_foco = self.navegacao.isVisible()
            self.navegacao.hide()
        elif self._navegacao_antes_do_foco:
            self.navegacao.show()
        self.foco_mudou.emit(self._modo_foco)
        self.editor.setFocus()

    def alternar_marcas_de_formatacao(self) -> None:
        """¶ no fim do parágrafo e o ponto no espaço: é vista, não grava, e acha o espaço duplo do OCR."""
        self._marcas_de_formatacao = not self._marcas_de_formatacao
        self._aplicar_marcas()
        self.fita.marcar({"marcas_de_formatacao": self._marcas_de_formatacao})

    def _aplicar_marcas(self) -> None:
        """Repõe a opção do documento: `_desenhar` cria um `QTextDocument` novo a cada redesenho."""
        from PyQt6.QtGui import QTextOption

        documento = self.editor.document()
        if documento is None:
            return
        opcao = documento.defaultTextOption()
        marcas = QTextOption.Flag.ShowTabsAndSpaces | QTextOption.Flag.ShowLineAndParagraphSeparators
        opcao.setFlags(opcao.flags() | marcas if self._marcas_de_formatacao else opcao.flags() & ~marcas)
        documento.setDefaultTextOption(opcao)

    def alternar_bloco_impresso(self) -> None:
        """Liga ou desliga a faixa do bloco impresso da mesa (S-643)."""
        self._faixa_ligada = not self._faixa_ligada
        self._bloco_na_faixa = None
        self._mostrar_impresso()

    def alternar_fita(self) -> None:
        """`Ctrl+F1`: recolhe a fita deixando só as abas, como no Word (S-652)."""
        self.fita.alternar_recolhida()

    # ---------------------------------------------------- três ferramentas de correção (S-659)

    def mover_paragrafo_acima(self) -> None:
        self._mover_paragrafo(-1)

    def mover_paragrafo_abaixo(self) -> None:
        self._mover_paragrafo(+1)

    def _mover_paragrafo(self, passo: int) -> None:
        inicio, _fim = self._intervalo()
        novo, onde = rico.mover_paragrafo(self.documento, inicio, passo)
        if novo is self.documento:
            self.estado.emit("Não há parágrafo " + ("acima" if passo < 0 else "abaixo") + " para trocar de lugar.")
            return
        self._aplicar(novo, selecao=(onde, onde))

    def codigo_unicode(self) -> None:
        """`Alt+X`: o código antes do cursor vira o caractere, e o caractere vira o código."""
        inicio, _fim = self._intervalo()
        troca = codigo_unicode(self.documento.para_texto()[:inicio])
        if troca is None:
            return
        apagar, escrever = troca
        depois = inicio - apagar + len(escrever)
        self._aplicar(rico.editar(self.documento, inicio - apagar, inicio, escrever), selecao=(depois, depois))

    # --------------------------------------------------------- corrigir pelo léxico (S-657)

    def proxima_fora_do_lexico(self) -> None:
        """`F7`: vai à próxima palavra marcada depois do cursor, e a seleciona. Liga a conferência se preciso."""
        if not self._conferindo_lexico:
            self.marcar_fora_do_lexico()
        if not self._fora_do_lexico:
            self.estado.emit("Nenhuma palavra fora do léxico nesta folha.")
            return
        _inicio, fim = self._intervalo()
        seguinte = next(((i, f) for i, f in self._fora_do_lexico if i >= fim), self._fora_do_lexico[0])
        self.mostrar_intervalo(*seguinte)

    def _lexico_da_folha(self) -> frozenset[str]:
        """O léxico do programa mais o do livro (o caderno), em caixa baixa."""
        from chess_diagram_ocr.text import dicionario

        livro = self._caderno.lexico() if self._caderno is not None else frozenset()
        return dicionario.carregar() | livro

    def _sugestoes_no_menu(self, menu: QMenu, ponto: QPoint) -> None:
        """Sobre uma palavra marcada: até cinco sugestões, acrescentar ao léxico do livro, ignorar (S-657)."""
        from chess_diagram_ocr.text import sugestao

        posicao = self._mapa.deslocamento(self.editor.cursorForPosition(ponto).position())
        achada = next(((i, f) for i, f in self._fora_do_lexico if i <= posicao <= f), None)
        if achada is None:
            return
        inicio, fim = achada
        palavra = self.documento.para_texto()[inicio:fim]
        primeira = menu.actions()[0] if menu.actions() else None
        try:
            lexico = self._lexico_da_folha()
        except OSError:
            lexico = frozenset()
        for sugerida in sugestao.sugestoes(palavra, lexico):
            acao = QAction(sugerida, menu)
            acao.triggered.connect(lambda _m=False, s=sugerida, a=inicio, b=fim: self._aceitar_sugestao(a, b, s))
            menu.insertAction(primeira, acao)
        for rotulo, alvo in (
            (f"Acrescentar «{palavra}» ao léxico do livro", lambda: self._acrescentar_ao_lexico(palavra)),
            (f"Ignorar «{palavra}» nesta folha", lambda: self._ignorar_na_folha(palavra)),
        ):
            acao = QAction(rotulo, menu)
            acao.triggered.connect(lambda _m=False, f=alvo: f())
            menu.insertAction(primeira, acao)
        if primeira is not None:
            menu.insertSeparator(primeira)

    def _aceitar_sugestao(self, inicio: int, fim: int, nova: str) -> None:
        """A troca pelo clique: um passo de desfazer, e uma correção, porque o bloco fica (S-245)."""
        self._rotulo_corrente = "Sugestão do léxico"
        try:
            self._aplicar(rico.substituir_intervalo(self.documento, inicio, fim, nova), selecao=(inicio + len(nova),) * 2)
        finally:
            self._rotulo_corrente = ""
        self._contar_correcoes()

    def _acrescentar_ao_lexico(self, palavra: str) -> None:
        if self._caderno is None or not self._caderno.acrescentar_ao_lexico(palavra):
            self.estado.emit("Sem caderno de livro aberto, não há léxico do livro onde acrescentar.")
            return
        self.estado.emit(f"«{palavra}» entrou no léxico deste livro: deixa de ser marcada nas folhas dele.")
        self._conferir_lexico(avisar=False)

    def _ignorar_na_folha(self, palavra: str) -> None:
        self._ignoradas.add(palavra.lower())
        self._conferir_lexico(avisar=False)

    # ------------------------------------------------------- a barra de estado (S-655)

    def _mostrar_recado(self, frase: str) -> None:
        """A frase transitória toma o lugar das caixas do meio por 6 s, com o texto inteiro na dica."""
        self.recado.setText(frase)
        self.recado.setToolTip(frase)
        self.recado.show()
        self.status.hide()
        self.caixa_de_palavras.hide()
        self.caixa_do_lexico.hide()
        self._relogio_do_recado.start()

    def _apagar_recado(self) -> None:
        self.recado.hide()
        self.status.show()
        self.caixa_de_palavras.show()
        self.caixa_do_lexico.setVisible(self._conferindo_lexico)

    def _contar_palavras_da_selecao(self) -> None:
        inicio, fim = self._selecao_atual()
        total = self._palavras_da_folha()
        selecionadas = contar_palavras(self.documento.para_texto()[inicio:fim]) if fim > inicio else None
        self.caixa_de_palavras.setText(frase_das_palavras(total, selecionadas) if total else "")

    def _palavras_da_folha(self) -> int:
        """A contagem da folha, cacheada pela edição: refeita só quando o documento é outro."""
        if self._palavras_cache[0] is not self.documento:
            self._palavras_cache = (self.documento, contar_palavras(self.documento.para_texto()))
        return self._palavras_cache[1]

    def _mostrar_indice(self) -> None:
        """Redesenha o índice, se ele está à vista. Escondido não custa nada: ele se refaz ao abrir."""
        if not hasattr(self, "indice") or not self.indice.isVisible():
            return
        folhas = () if self._caderno is None else self._caderno.folhas()
        self.indice.mostrar(folhas, atual=None if self._pagina is None else int(self._pagina.pagina))

    def _abrir_do_indice(self, pagina: int) -> None:
        """O clique numa linha do índice: a folha abre como pelo «Abrir folha» (S-612)."""
        self.campo_de_folha.setValue(int(pagina) + 1)
        self.ler()

    def exportar_caderno(self) -> None:
        """O caderno inteiro num `.md`, `.html` ou `.rtf`, folha a folha (S-614), fora da thread da janela.

        As folhas sem caderno são puladas e o relatório as lista. As miniaturas saem de cada folha
        renderizada de novo -- é a parte longa, e por isso a exportação é cancelável entre duas
        folhas, como a de uma folha é antes da escrita.
        """
        from chess_diagram_ocr.text import exportacao

        cad = self._caderno
        if cad is None or self._livro_do_caderno is None:
            self.estado.emit("Abra um livro e leia uma folha: o caderno é do livro aberto.")
            return
        if self._tarefa is not None:
            self.estado.emit("Já há uma leitura ou exportação em curso nesta aba.")
            return
        self._guardar_a_folha()  # a folha da tela entra como está
        estados = cad.folhas()
        if not estados:
            self.estado.emit("O caderno deste livro ainda não tem folha nenhuma.")
            return
        livro = self._livro_do_caderno
        destino, filtro = QFileDialog.getSaveFileName(
            self,
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
        documentos = [_no_livro(d, livro) for d in documentos]
        presentes = {int(d.origem.pagina) for d in documentos if d.origem is not None}
        faltam = [p for p in range(self._folhas_do_livro()) if p not in presentes]
        com_imagens = bool(getattr(formato, "pasta_de_imagens", "")) and livro.exists()
        dpi = self._dpi_para_ler()
        diagramas, ao_lado = alinhamento_dos_diagramas(self._diagramas), self._texto_ao_lado
        desistir = threading.Event()
        self._cancelar_exportacao = desistir

        def _trabalho() -> str:
            recortes: dict[int, dict[int, Path]] = {}
            for doc in documentos if com_imagens else ():
                if desistir.is_set():
                    return CANCELADA
                if not doc.diagramas or doc.origem is None:
                    continue
                pagina = int(doc.origem.pagina)
                folha = _renderizar(livro, pagina, dpi=dpi)
                nome = caminho.with_name(f"{caminho.stem}_f{pagina + 1:04d}{caminho.suffix}")
                recortes[pagina] = _gravar_recortes(doc, nome, folha, dpi=dpi)
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

        self.estado.emit(f"Exportando o caderno ({len(documentos)} folha(s)) para {caminho.name}…")
        self._registrar_ocupado(
            f"Exportando o caderno para {formato.nome}",
            loses_work=True,
            detail=caminho.name,
            cancelar=desistir.set,
        )
        self._tarefa = Tarefa(_trabalho, parent=self)
        self._tarefa.pronto.connect(self._exportacao_terminou)
        self._tarefa.falhou.connect(self._exportacao_falhou)
        self._tarefa.finished.connect(self._soltar_ocupado)
        self._tarefa.start()

    def _exportar_caderno_pesquisavel(self, cad: caderno.Caderno, livro: Path, caminho: Path) -> None:
        """O livro inteiro com a camada invisível do **caderno** (S-253 sobre a S-614).

        Todas as folhas do original saem, e as que o caderno tem ganham a camada do texto dele -- as
        lidas e as corrigidas, porque aqui o motor não roda: o caderno é tudo o que a aba sabe. As
        demais ficam como estão, que é o que a camada do motor (`cvoff-texto-pesquisavel`) também faz.
        """
        from chess_diagram_ocr.text import pdf_pesquisavel

        if not livro.exists():
            self.estado.emit(f"O livro {livro.name} não está no lugar de antes: o PDF pesquisável sai dele.")
            return
        corrigidas = {e.pagina: d for e in cad.folhas() if (d := cad.folha(e.pagina)) is not None}
        corrigidas = {p: _no_livro(d, livro) for p, d in corrigidas.items()}
        desistir = threading.Event()
        self._cancelar_exportacao = desistir

        def _trabalho() -> str:
            if desistir.is_set():
                return CANCELADA
            relatorio = pdf_pesquisavel.escrever_camada([], caminho, origem=livro, corrigidas=corrigidas)
            avisos = "".join(f" Aviso: {aviso}." for aviso in relatorio.avisos)
            return f"PDF pesquisável do caderno em {caminho.name}: {relatorio.resumo()}.{avisos}"

        self.estado.emit(f"Escrevendo o PDF pesquisável do caderno ({len(corrigidas)} folha(s))…")
        self._registrar_ocupado(
            "Exportando o caderno para PDF pesquisável", loses_work=True, detail=caminho.name, cancelar=desistir.set
        )
        self._tarefa = Tarefa(_trabalho, parent=self)
        self._tarefa.pronto.connect(self._exportacao_terminou)
        self._tarefa.falhou.connect(self._exportacao_falhou)
        self._tarefa.finished.connect(self._soltar_ocupado)
        self._tarefa.start()

    # ----------------------------------------------------------- o rascunho automático (S-255)

    def _anotar_cursor(self) -> None:
        self._cursor_em = self._relogio()
        self._mostrar_impresso()
        self._avisar_bloco()

    def _sob_o_cursor(self) -> tuple[object, tuple[int, int]] | None:
        """O que está sob o cursor na folha: a **linha** lida, quando se acha (S-642, etapa 2), e o bloco
        quando não -- a linha reescrita à mão não casa com a lida, e a resposta volta a ser o bloco.

        Devolve o objeto com `bbox` (`LinhaLida` ou o bloco) e a chave `(bloco, linha)`, com `-1` na
        linha quando é o bloco inteiro.
        """
        doc = self.documento
        if doc.origem is None:
            return None
        deslocamento = self._mapa.deslocamento(self.editor.textCursor().position())
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

    def _avisar_bloco(self) -> None:
        """Diz à mesa qual bloco da folha está sob o cursor (S-642). Fora da mesa, nenhum."""
        bbox = None
        doc = self.documento
        if self._na_mesa and doc.origem is not None and int(doc.origem.pagina) == self._pagina_indice:
            achado = self._sob_o_cursor()
            caixa = None if achado is None else getattr(achado[0], "bbox", None)
            bbox = None if caixa is None else tuple(float(v) for v in caixa)
        if bbox != self._bloco_avisado:
            self._bloco_avisado = bbox
            self.bloco_destacado.emit(bbox)

    def ir_ao_ponto(self, x: float, y: float) -> bool:
        """O clique na folha, em pontos (S-642): o cursor vai ao começo do bloco clicado. Devolve se foi.

        O menor bloco que contém o ponto ganha, como a menor caixa de diagrama ganha no
        visualizador. Só vale para a folha que está no editor -- o clique na folha 7 com a folha 3
        no texto não tem para onde levar o cursor.
        """
        doc = self.documento
        if doc.origem is None or int(doc.origem.pagina) != self._pagina_indice:
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
            cursor = self.editor.textCursor()
            cursor.setPosition(self._mapa.posicao(comeco))
            self.editor.setTextCursor(cursor)
            self.editor.ensureCursorVisible()
            self.editor.setFocus()
            return True
        return False

    # ------------------------------------------------------------- a mesa (S-643, S-644)

    # ------------------------------------------------------- os diagramas no texto (Fase 92)

    @property
    def diagramas_a_esquerda(self) -> bool:
        return self._diagramas == DIAGRAMAS_A_ESQUERDA

    def definir_diagramas(self, preferencia: str) -> None:
        """«Diagramas no texto» (S-620). Redesenha **sem** tornar a folha "por gravar": não é edição."""
        preferencia = DIAGRAMAS_A_ESQUERDA if preferencia == DIAGRAMAS_A_ESQUERDA else DIAGRAMAS_AO_CENTRO
        if preferencia == self._diagramas:
            return
        self._diagramas = preferencia
        self._redesenhar_a_vista()

    @property
    def texto_ao_lado(self) -> bool:
        return self._texto_ao_lado

    def definir_texto_ao_lado(self, ligado: bool) -> None:
        """O texto ao lado do diagrama à esquerda (S-624). Vista: redesenha sem tornar a folha «por gravar»."""
        if bool(ligado) == self._texto_ao_lado:
            return
        self._texto_ao_lado = bool(ligado)
        self._redesenhar_a_vista()

    def alternar_texto_ao_lado(self) -> None:
        self.definir_texto_ao_lado(not self._texto_ao_lado)
        self.estado.emit(
            "O texto corre ao lado dos diagramas que ficam à esquerda."
            if self._texto_ao_lado
            else "Os diagramas à esquerda voltam a ter a linha só para eles."
        )

    def interruptores_da_vista(self) -> dict[str, bool]:
        """As marcas que o menu Texto mostra para a vista desta aba, para a janela pô-las ao abrir."""
        return {
            "diagramas_a_esquerda": self.diagramas_a_esquerda,
            "texto_ao_lado": self._texto_ao_lado,
            "ler_ao_chegar": self._ler_ao_chegar,
        }

    def alternar_ler_ao_chegar(self) -> None:
        """«Ler ao chegar numa folha sem caderno» (S-644): para quem corrige o livro do começo ao fim
        com o motor rápido. Desligada por padrão -- ler custa de 1 s a 40 s, e é decisão de quem lê."""
        self._ler_ao_chegar = not self._ler_ao_chegar
        self.estado.emit(
            "Virar a página com a mesa lê a folha que ainda não está no caderno."
            if self._ler_ao_chegar
            else "Virar a página com a mesa mostra a folha por ler, sem ler sozinha."
        )

    def alternar_diagramas_a_esquerda(self) -> None:
        self.definir_diagramas(DIAGRAMAS_AO_CENTRO if self.diagramas_a_esquerda else DIAGRAMAS_A_ESQUERDA)
        self.estado.emit(
            "Os diagramas que ninguém alinhou ficam à esquerda do texto."
            if self.diagramas_a_esquerda
            else "Os diagramas que ninguém alinhou voltam ao centro do texto."
        )

    def definir_tamanho_da_miniatura(self, tamanho: str) -> None:
        """O tamanho da miniatura (S-623). Vista, e não documento: não grava nada nem muda a exportação."""
        tamanho = tamanho if tamanho in TAMANHOS_DA_MINIATURA else TAMANHO_DA_MINIATURA_PADRAO
        if tamanho == self._tamanho_da_miniatura:
            return
        self._tamanho_da_miniatura = tamanho
        self._redesenhar_a_vista()

    def mudar_tamanho_da_miniatura(self) -> None:
        self.definir_tamanho_da_miniatura(proximo_tamanho_da_miniatura(self._tamanho_da_miniatura))
        self.estado.emit(
            f"Miniaturas {NOME_DO_TAMANHO[self._tamanho_da_miniatura]} "
            f"({TAMANHOS_DA_MINIATURA[self._tamanho_da_miniatura]} px no corpo do sistema)."
        )

    @property
    def familia_da_letra(self) -> str:
        return self._familia_da_letra

    def definir_familia_da_letra(self, familia: str) -> None:
        """A letra de leitura (S-632). Vista, e não documento: redesenha sem tornar a folha «por gravar»."""
        familia = familia if familia in FAMILIAS_DA_LETRA else FAMILIA_DA_LETRA_PADRAO
        if familia == self._familia_da_letra:
            return
        self._familia_da_letra = familia
        self._redesenhar_a_vista()

    def mudar_familia_da_letra(self) -> None:
        self.definir_familia_da_letra(proxima_familia_da_letra(self._familia_da_letra))
        nome = NOME_DA_FAMILIA[self._familia_da_letra]
        familia = self._base[1] if self._base is not None else ""
        self.estado.emit(f"Letra da folha: {nome} ({familia})." if familia else f"Letra da folha: {nome}.")

    def _redesenhar_a_vista(self) -> None:
        """Redesenha a folha como está, por uma mudança de vista: nem pilha, nem rascunho, nem caderno."""
        barra = self.editor.verticalScrollBar()
        rolagem = barra.value() if barra is not None else 0
        self._desenhar(selecao=self._selecao_atual())
        if barra is not None:
            barra.setValue(rolagem)
        self._atualizar_status()

    def _alinhar_os_diagramas_da_folha(self, alinhamento: str) -> None:
        """Todos os diagramas desta folha num passo só de desfazer (S-621)."""
        novo = rico.alinhar_diagramas(self.documento, alinhamento)
        if novo is self.documento:
            self.estado.emit("Os diagramas desta folha já estão assim.")
            return
        quantos = rico.diagramas_a_alinhar(self.documento, alinhamento)
        self._aplicar(novo)
        self.estado.emit(f"{quantos} diagrama(s) desta folha realinhado(s); Ctrl+Z desfaz os {quantos} de uma vez.")

    def diagramas_da_folha_a_esquerda(self) -> None:
        self._alinhar_os_diagramas_da_folha(rico.ALINHAMENTO_ESQUERDA)

    def diagramas_da_folha_ao_centro(self) -> None:
        self._alinhar_os_diagramas_da_folha(rico.ALINHAMENTO_CENTRO)

    def diagramas_da_folha_como_a_preferencia(self) -> None:
        self._alinhar_os_diagramas_da_folha("")

    def alinhar_diagramas_do_caderno(self, alinhamento: str) -> int:
        """Todos os diagramas de todas as folhas do caderno (S-621), com a conta antes. Devolve quantas folhas mudaram.

        A pergunta diz quantos diagramas de quantas folhas, e cada folha mudada guarda a de antes como
        `anterior` (S-611). A folha da tela muda pela pilha, para `Ctrl+Z` desfazê-la como as outras edições.
        """
        from chess_diagram_ocr.qt import dialogos

        cad = self._caderno
        if cad is None or cad.somente_leitura:
            self.estado.emit("Abra um livro com caderno para alinhar os diagramas dele.")
            return 0
        self._guardar_a_folha()
        mudar: list[tuple[int, rico.DocumentoRico, int]] = []
        for estado in cad.folhas():
            doc = cad.folha(estado.pagina)
            if doc is not None and (quantos := rico.diagramas_a_alinhar(doc, alinhamento)):
                mudar.append((estado.pagina, doc, quantos))
        if not mudar:
            self.estado.emit("Nenhum diagrama do caderno muda com isso.")
            return 0
        total = sum(q for _p, _d, q in mudar)
        destino = {"esquerda": "à esquerda", "centro": "ao centro"}.get(alinhamento, "como a preferência")
        if not dialogos.ha_quem_responda():
            return 0
        resposta = QMessageBox.question(
            self,
            "Texto",
            f"Alinhar {total} diagrama(s) de {len(mudar)} folha(s) {destino}? A versão de antes de cada folha "
            "fica como anterior no caderno.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return 0
        na_tela = None if self._caderno_da_tela() is None else int(self.documento.origem.pagina)  # type: ignore[union-attr]
        for pagina, doc, _quantos in mudar:
            if pagina == na_tela:
                cad.visitar(pagina)
                self._aplicar(rico.alinhar_diagramas(self.documento, alinhamento))
                self._guardar_a_folha()
                continue
            guardada = cad.estado(pagina)
            cad.visitar(pagina)
            cad.gravar(
                rico.alinhar_diagramas(doc, alinhamento),
                estado=None if guardada is None else guardada.estado,
                correcoes=0 if guardada is None else guardada.correcoes,
            )
        self._mostrar_indice()
        self.estado.emit(f"{total} diagrama(s) de {len(mudar)} folha(s) alinhado(s) {destino}.")
        return len(mudar)

    def aplicar_estado(self, estado: object) -> None:
        """A vista da aba como a sessão anterior a deixou: zoom, quebra, motor, modo bloco, os diagramas e a letra."""
        self.aplicar_zoom(int(getattr(estado, "texto_zoom", 0)), avisar=False)
        self.definir_quebra(bool(getattr(estado, "texto_quebra", True)))
        self.definir_motor(str(getattr(estado, "texto_motor", "")))  # o motor e o modo bloco da sessão anterior (item 17)
        self.definir_modo_bloco(bool(getattr(estado, "texto_bloco", False)))
        self.definir_diagramas(str(getattr(estado, "texto_diagramas", "")))
        self.definir_tamanho_da_miniatura(str(getattr(estado, "texto_miniatura", "")))
        self.definir_familia_da_letra(str(getattr(estado, "texto_familia", "")))
        self.definir_texto_ao_lado(bool(getattr(estado, "texto_ao_lado", False)))
        self._ler_ao_chegar = bool(getattr(estado, "texto_ler_ao_chegar", False))
        for canal, chave in (("letra", "texto_ultima_cor"), ("realce", "texto_ultimo_realce")):
            nome = str(getattr(estado, chave, ""))
            if nome in texto_cores.nomes():
                self._ultimas_cores[canal] = nome
        self._mostrar_ultima_cor(self.cor_rapida, "letra")
        self._mostrar_ultima_cor(self.realce_rapido, "realce")
        self.fita.definir_recolhida(bool(getattr(estado, "texto_fita_recolhida", False)))
        self._glifos_recentes = [str(g) for g in getattr(estado, "texto_glifos_recentes", [])][:GLIFOS_RECENTES]
        self._encher_a_paleta()

    def anotar_estado(self, estado: object) -> None:
        """O contrário de `aplicar_estado`: a vista da aba vai ao estado que a janela grava."""
        estado.texto_zoom = int(self.zoom_da_vista)  # type: ignore[attr-defined]
        estado.texto_quebra = bool(self.quebra)  # type: ignore[attr-defined]
        estado.texto_motor = self.motor  # type: ignore[attr-defined]
        estado.texto_bloco = bool(self.modo_bloco)  # type: ignore[attr-defined]
        estado.texto_diagramas = self._diagramas  # type: ignore[attr-defined]
        estado.texto_miniatura = self._tamanho_da_miniatura  # type: ignore[attr-defined]
        estado.texto_familia = self._familia_da_letra  # type: ignore[attr-defined]
        estado.texto_ao_lado = self._texto_ao_lado  # type: ignore[attr-defined]
        estado.texto_ler_ao_chegar = self._ler_ao_chegar  # type: ignore[attr-defined]
        estado.texto_ultima_cor = self._ultimas_cores["letra"]  # type: ignore[attr-defined]
        estado.texto_ultimo_realce = self._ultimas_cores["realce"]  # type: ignore[attr-defined]
        estado.texto_fita_recolhida = self.fita.recolhida  # type: ignore[attr-defined]
        estado.texto_glifos_recentes = list(self._glifos_recentes)  # type: ignore[attr-defined]

    def folha_rasterizada(self) -> tuple[np.ndarray | None, int]:
        """A folha que o editor tem rasterizada e o DPI dela: é o que a vista da mesa destacada mostra (S-646)."""
        return self._pagina_rgb, int(self._dpi)

    @property
    def _na_mesa(self) -> bool:
        """A aba está numa mesa -- a da janela principal ou a janela própria: ela acompanha a página do
        visualizador (S-644), mostra o bloco impresso sob o cursor (S-643) e avisa o bloco (S-642)."""
        return self._mesa_armada or self._destacada

    @property
    def destacada(self) -> bool:
        return self._destacada

    def definir_mesa(self, ligada: bool) -> None:
        """A janela armou ou desarmou a mesa. A aba passa a acompanhar a página, e a faixa aparece."""
        self._mesa_armada = bool(ligada)
        self._mostrar_impresso()
        self._avisar_bloco()

    def definir_destacada(self, destacada: bool) -> None:
        """A aba foi para a janela da mesa, ou voltou (S-646). Lá ela é mesa como na principal."""
        if bool(destacada) == self._destacada:
            return
        self._destacada = bool(destacada)
        self._mostrar_impresso()
        self._avisar_bloco()
        self.destacada_mudou.emit(self._destacada)

    def folha_atual(self) -> tuple[int, int]:
        """A folha do visualizador (0-based) e quantas o livro tem; zero quando não há livro aberto."""
        total = self.campo_de_folha.maximum() if self._pdf is not None and self.campo_de_folha.maximum() < TETO_DE_FOLHAS else 0
        return self._pagina_indice, int(total)

    def folha_por_ler(self) -> bool:
        """O editor está no vazio «Ler a folha N» da mesa (S-644), sem folha nem texto."""
        return self._folha_por_ler is not None and self._folha_por_ler == self._pagina_indice

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
        self.folha_pedida.emit(alvo)
        return True

    def _seguir_a_pagina(self, pagina: int) -> None:
        """A página do visualizador virou com a mesa armada (S-644).

        Guarda a folha que sai (S-611), abre a que entra do caderno se ela tiver (S-612), ou mostra o
        vazio «Ler a folha N» -- e **não** lê sozinha: ler custa de 1 s a 40 s, e é decisão de quem
        lê. Uma folha que não pôde ir ao caderno não sai da tela.
        """
        if self._tarefa is not None or pagina == self._folha_por_ler:
            return
        origem = self.documento.origem
        if (
            origem is not None
            and int(origem.pagina) == pagina
            and _chave_de_livro(origem.documento) == _chave_de_livro(self._pdf)
        ):
            return
        if not self._guardar_a_folha():
            self.estado.emit("A folha na tela tem alterações que não foram ao caderno: ela fica, e só a página virou.")
            return
        if self._caderno is not None and self._caderno.estado(pagina) is not None and self._abrir_do_caderno(pagina):
            return
        self._mostrar_folha_por_ler(pagina)
        if self._ler_ao_chegar:
            self.ler()

    def _mostrar_folha_por_ler(self, pagina: int) -> None:
        """O editor vazio, com o botão que lê **esta** folha."""
        self._pagina = None
        self._pagina_rgb = None
        self._historico.clear()
        self._refeitos.clear()
        self._rotulos_do_historico.clear()
        self._rotulos_refeitos.clear()
        self._digitacao = None
        self._caminho_do_documento = None
        self._folha_por_ler = pagina
        self.desenhar_documento(rico.DocumentoRico())
        self._documento_gravado = self.documento
        self._rascunho.stop()
        self._vai_ao_caderno = False
        self._correcoes = 0
        self._mostrar_vazio()
        self._atualizar_status()

    def _mostrar_impresso(self) -> None:
        """A faixa do bloco impresso (S-643): o recorte da folha do bloco sob o cursor, ou nada."""
        if not hasattr(self, "faixa_impressa"):
            return
        doc = self.documento
        folha = self._pagina_rgb
        achado = None
        if self._na_mesa and self._faixa_ligada and folha is not None and doc.origem is not None:
            achado = self._sob_o_cursor()
            if achado is not None and isinstance(achado[0], BlocoDeDiagrama):
                achado = None
        imagem = None
        if achado is not None and folha is not None:
            imagem = _recorte_da_folha(folha, achado[0], dpi=self._dpi)
        if achado is None or imagem is None:
            self.faixa_impressa.hide()
            self._bloco_na_faixa = None
            self.recorte_na_faixa = None
            return
        chave = (*achado[1], id(folha))
        if chave == self._bloco_na_faixa and self.faixa_impressa.isVisible():
            return
        self._bloco_na_faixa = chave
        self.recorte_na_faixa = imagem
        largura = max(1, self._area_da_folha().width())
        # A linha impressa fica com a altura de duas linhas de texto (S-643, etapa 2); o bloco inteiro,
        # quando a linha não se acha, com até um terço do editor, como antes.
        e_linha = achado[1][1] >= 0
        altura = 2 * self.editor.fontMetrics().height() if e_linha else max(24, self.editor.height() // 3)
        self.faixa_impressa.setPixmap(
            pixmap_de_rgb(np.ascontiguousarray(imagem)).scaled(
                largura, altura, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        self.faixa_impressa.show()

    def _agendar_rascunho(self) -> None:
        """Reinicia o relógio: a folha é gravada alguns segundos depois da **última** edição.

        No caderno é a régua do WordCraft (2,5 s, e o cursor parado), sem ele os 4 s do rascunho.
        """
        self._mudou_em = self._relogio()
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
            falta = caderno.espera_restante(self._relogio(), mudou_em=self._mudou_em, cursor_em=self._cursor_em)
            if falta > 0:
                self._rascunho.start(max(1, int(falta * 1000)))
                return
        self._guardar_a_folha()
        self._refazer_navegacao()
        if self._conferindo_lexico:
            self._conferir_lexico(avisar=False)
        self._contar_correcoes()

    def gravar_rascunho(self) -> Path | None:
        """Grava o rascunho **se houver o que gravar**. Devolve o caminho, ou `None`.

        Só com alteração por gravar: reescrever o mesmo arquivo a cada quatro segundos é desgaste
        de disco por nada. E só com folha de origem -- documento sem folha não tem chave estável,
        e `rascunho.gravar` devolve `None` para ele.
        """
        self._rascunho.stop()
        if not self.tem_alteracoes or self._pagina is None:
            return None
        try:
            return rascunho.gravar(correcao.com_procedencia_humana(self.documento), pasta=self._pasta_de_rascunhos)
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
            self,
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
        if self._pagina is None:
            return False
        achado = rascunho.achar(self._pagina.documento, self._pagina.pagina, pasta=self._pasta_de_rascunhos)
        if achado is None:
            self.estado.emit("Não há rascunho desta folha por recuperar.")
            return False
        if not self._confirmar_descarte("Recuperar o rascunho descarta as alterações."):
            return False
        return self._recuperar(achado, self._pagina)

    def _recuperar(self, achado: rascunho.Rascunho, pagina: PaginaLida) -> bool:
        """Põe o rascunho na tela como trabalho por gravar e apaga o arquivo dele."""
        try:
            doc = rascunho.carregar(achado)
        except (OSError, ValueError) as erro:  # `arquivo.ArquivoInvalido` é um `ValueError`
            logger.debug("Rascunho não abriu (%s): %s", achado.caminho, erro)
            self.estado.emit(f"O rascunho não pôde ser aberto: {erro}")
            return False
        # A folha é a que acabou de ser lida: a imagem dela serve, e não se renderiza de novo.
        self.abrir(doc, folha_rgb=self._pagina_rgb)
        # **Recuperado é trabalho por gravar, e não trabalho gravado (S-308).** `abrir` iguala o
        # gravado ao que está na tela -- o certo para um arquivo do disco, e o errado para este,
        # que veio de um arquivo que a linha seguinte apaga. Sem isto, o texto resgatado de um
        # travamento voltaria a existir só na memória: as guardas que perguntam antes de descartar
        # passariam direto, e `gravar_rascunho` sairia sem reescrever nada. O segundo travamento
        # perderia tudo -- e o recurso existe exatamente para o segundo travamento.
        self._documento_gravado = rico.de_pagina(pagina)
        # Recuperado é trabalho que chegou a um lugar melhor -- a tela --, e o arquivo sai.
        rascunho.descartar(pagina.documento, pagina.pagina, pasta=self._pasta_de_rascunhos)
        self._agendar_rascunho()
        self.estado.emit(f"Rascunho de {achado.data_legivel} recuperado.")
        return True

    def _confirmar_descarte(self, o_que: str, *, ao_fechar: bool = False) -> bool:
        """Pergunta antes de jogar fora o que foi editado e não foi gravado. Sem isso, não pergunta.

        **Sem tela não há quem responda** (`dialogos.ha_quem_responda`), e a resposta é a mesma de
        `dialogos.perguntar_descarte`: fechar fecha -- não há o que fazer com uma janela que já
        está sendo destruída --, e ler ou abrir outra folha **não** descarta, que é a resposta que
        não perde nada. As duas ficam no log.
        """
        from chess_diagram_ocr.qt import dialogos

        if not self.tem_alteracoes:
            return True
        if not dialogos.ha_quem_responda():
            logger.warning(
                "O texto da aba Texto tem alterações não gravadas e nenhuma tela para perguntar: %s.",
                "o fechamento segue" if ao_fechar else "as alterações ficam",
            )
            return ao_fechar
        onde = "da aba Texto" if ao_fechar else "desta aba"
        resposta = QMessageBox.question(
            self,
            "Texto",
            f"O texto {onde} foi editado e não foi gravado. {o_que} Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return resposta == QMessageBox.StandardButton.Yes


    # ------------------------------------------------------------- a exportação (S-254)

    def salvar(self) -> None:
        """O `.txt` puro, ao lado do `.cvtxt`: quem quer colar num e-mail quer este."""
        self._exportar(".txt")

    def exportar_md(self) -> None:
        """`.md` **porque ele diffa**: duas correções da mesma folha comparam linha a linha."""
        self._exportar(".md")

    def exportar_html(self) -> None:
        self._exportar(".html")

    def exportar_rtf(self) -> None:
        self._exportar(".rtf")

    def exportar_pdf_pesquisavel(self) -> None:
        """O livro com a camada de texto por cima -- o que faz o PDF ser pesquisável."""
        self._exportar(".pdf")

    def _exportar(self, extensao: str) -> None:
        """Pergunta o destino e exporta **fora da thread da janela** (S-254).

        O `.txt` de uma folha é imperceptível, e gravá-lo na thread da janela estaria certo. Deixa
        de estar com o `.rtf` de imagens embutidas e com o PDF pesquisável, que abre o livro,
        escreve a camada e grava um arquivo novo.
        """
        from chess_diagram_ocr.text import arquivo, exportacao

        if self._tarefa is not None:
            self.estado.emit("Já há uma exportação em curso nesta aba.")
            return
        if not self.documento.para_texto().strip():
            # Rodapé e não caixa: é um passo que falta, e não uma escolha.
            self.estado.emit("Não há texto nesta aba para exportar.")
            return
        formato = exportacao.formato_de(extensao)
        destino, _filtro = QFileDialog.getSaveFileName(
            self,
            f"Exportar o texto da folha para {formato.nome}",
            arquivo.sugestao_de_nome(self.documento, extensao=extensao),
            f"{formato.nome} (*{extensao});;Todos (*.*)",
        )
        if not destino:
            return
        caminho = Path(destino)
        # O que se exporta é o que se grava: com a procedência da mão (S-239) -- o cabeçalho do
        # `.txt` a declara -- e sem tocar no que está na tela.
        doc = correcao.com_procedencia_humana(self.documento)
        folha = self._pagina_rgb
        dpi = self._dpi
        com_imagens = bool(getattr(formato, "pasta_de_imagens", ""))
        # A vista dos diagramas vai junto (S-622): o arquivo mostra o que a tela mostra.
        diagramas, ao_lado = alinhamento_dos_diagramas(self._diagramas), self._texto_ao_lado

        # **Cancelável, e o ponto de corte é antes da escrita** (F9-C2, §7 item 7). A conversão
        # do documento é a parte longa; escrever o arquivo é um `write` só. Então desistir tem um
        # lugar seguro e um só: entre as duas. Cortar **durante** a escrita deixaria em disco o
        # `.pdf` truncado que o comentário de `loses_work=True` descreve -- e um arquivo que abre
        # e mente é pior que nenhum, que é a razão de o cancelamento não interromper o `escrever`.
        desistir = threading.Event()
        self._cancelar_exportacao = desistir

        def _trabalho() -> str:
            # Os recortes dos diagramas saem **antes** do arquivo, na mesma thread: são o que o
            # `.md` e o `.html` apontam (S-338). Sem folha renderizada a marca sai sozinha.
            recortes = _gravar_recortes(doc, caminho, folha, dpi=dpi) if com_imagens else {}
            relatorio = exportacao.exportar(doc, formato, recortes=recortes, diagramas=diagramas, ao_lado=ao_lado)
            if desistir.is_set():
                return CANCELADA
            exportacao.escrever(caminho, relatorio)
            return exportacao.texto_do_relatorio(
                caminho, relatorio, tamanho=caminho.stat().st_size
            )

        self.estado.emit(f"Exportando para {caminho.name}…")
        # `loses_work=True`: o arquivo de destino fica pela metade se a janela fechar no meio,
        # e um `.pdf` pesquisável truncado é pior que nenhum -- ele abre e mente.
        self._registrar_ocupado(
            f"Exportando para {formato.nome}",
            loses_work=True,
            detail=caminho.name,
            cancelar=desistir.set,
        )
        self._tarefa = Tarefa(_trabalho, parent=self)
        self._tarefa.pronto.connect(self._exportacao_terminou)
        self._tarefa.falhou.connect(self._exportacao_falhou)
        self._tarefa.finished.connect(self._soltar_ocupado)
        self._tarefa.start()

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
        self._tarefa = None
        if str(frase) == CANCELADA:
            self.estado.emit("Exportação cancelada. Nada foi gravado.")
            return
        self.estado.emit(str(frase))

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

        tarefa, self._tarefa = self._tarefa, None
        rastro = str(getattr(tarefa, "rastro", "") or "") or rastro_de(excecao)
        dialogos.mostrar_falha(self, titulo, mensagem, rastro)

    # ---------------------------------------------------------- a leitura, em thread

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
        self.estado.emit(
            "Modo bloco: a folha é lida em blocos, e não linha a linha."
            if self._modo_bloco
            else "Modo linha: a folha volta a ser lida linha a linha."
        )

    def sincronizar_com_a_pagina(self) -> None:
        """Lê a folha que o visualizador está mostrando -- e não a que o campo diz (S-236)."""
        self.campo_de_folha.setValue(self._pagina_indice + 1)
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
        if self._tarefa is not None:
            self.estado.emit("Já há uma leitura em curso nesta aba.")
            return
        if self._pdf is None:
            # Rodapé e não caixa: é um passo que falta, e não uma escolha.
            self.estado.emit("Abra um PDF antes de ler o texto da folha.")
            return
        # A folha da tela vai ao caderno antes (S-611); sem caderno o rascunho vai ao disco e a
        # pergunta continua, pela razão de `abrir_documento` (S-605).
        if not self._guardar_a_folha() and not self._confirmar_descarte("Ler de novo descarta as alterações."):
            return
        indice = int(self.campo_de_folha.value()) - 1
        guardada = None if self._caderno is None else self._caderno.estado(indice)
        if guardada is not None:
            if not de_novo and caderno.abre_do_caderno(guardada, motor=self._motor, modo_bloco=self._modo_bloco):
                if self._abrir_do_caderno(indice):
                    return
            elif de_novo and guardada.correcoes and not self._confirmar_releitura(indice, guardada.correcoes):
                return
        # O que está na tela quando a leitura parte: o que for digitado **durante** ela não foi
        # confirmado por ninguém, e `_leitura_terminou` pergunta de novo antes de trocá-lo.
        self._documento_ao_ler = self.documento

        motor = self._motor
        bloco = self._modo_bloco
        self._leitura_de = (motor, bloco)
        caminho = self._pdf
        dpi = self._dpi_para_ler()
        teto = self._teto_de_diagramas()
        # A folha que o visualizador já rasterizou serve, se for esta e no mesmo DPI (item 28):
        # copiada aqui, na thread da janela, porque o visualizador pode trocá-la enquanto se lê.
        pronta = self._fornecedor_de_folha(indice) if self._fornecedor_de_folha is not None else None
        imagem_pronta = np.array(pronta[0], copy=True) if pronta is not None and int(pronta[1]) == dpi else None

        def _trabalho() -> tuple[PaginaLida, np.ndarray | None, int, float]:
            # **A folha é rasterizada uma vez, e aqui (S-352).** `ler_pagina` a renderiza sozinha
            # quando ninguém lhe dá a imagem, e as miniaturas precisariam dela de novo -- na thread
            # da janela, que congelava ~355 ms por leitura no outro frontend. O mesmo `dpi` dos
            # dois lados é o que liga pixel a ponto -- e ele viaja com a folha, porque a
            # configuração pode mudar enquanto a leitura corre. O tempo vai junto (item 16): é o
            # número que decide entre o motor rápido e o modo bloco de 40 s.
            inicio = time.perf_counter()
            imagem = imagem_pronta if imagem_pronta is not None else _renderizar(caminho, indice, dpi=dpi)
            lida = _ler(caminho, indice, dpi=dpi, motor=motor, modo_bloco=bloco, imagem_rgb=imagem, max_boards=teto)
            return lida, imagem, dpi, time.perf_counter() - inicio

        self.estado.emit(f"Lendo a folha {indice + 1}…")
        self._registrar_ocupado(
            f"Lendo o texto da folha {indice + 1}",
            loses_work=False,
            detail=f"motor {motor}" + (" · modo bloco" if bloco else ""),
        )
        self._tarefa = Tarefa(_trabalho, parent=self)
        self._tarefa.pronto.connect(self._leitura_terminou)
        self._tarefa.falhou.connect(self._leitura_falhou)
        self._tarefa.finished.connect(self._soltar_ocupado)
        self._tarefa.start()

    def definir_fornecedor_de_folha(self, fornecedor: Callable[[int], tuple[np.ndarray, int] | None] | None) -> None:
        """Quem responde «a folha N já está rasterizada, e em que DPI?» -- o visualizador (item 28)."""
        self._fornecedor_de_folha = fornecedor

    def _dpi_para_ler(self) -> int:
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
        self._tarefa = None
        if isinstance(resultado, tuple):
            pagina, imagem, dpi, segundos = (*resultado, None, None)[:4]
        else:
            pagina, imagem, dpi, segundos = resultado, None, None, None
        assert isinstance(pagina, PaginaLida)
        partida = self._documento_ao_ler
        self._documento_ao_ler = None
        editado_na_leitura = partida is not None and self.documento is not partida
        if (
            editado_na_leitura
            and not self._guardar_a_folha()
            and not self._confirmar_descarte("A folha lida substitui o que foi editado durante a leitura.")
        ):
            self.estado.emit("A folha lida ficou de lado: o texto editado durante a leitura continua na tela.")
            return
        self._pagina_indice = int(self.campo_de_folha.value()) - 1
        self.mostrar_pagina(pagina, folha_rgb=imagem, dpi=dpi)
        self._guardar_leitura()
        diagramas = len(pagina.diagramas)
        figuras = f", {diagramas} diagrama(s)" if diagramas else ""
        # «em 3,9 s»: a pessoa escolhe o motor e o modo bloco pelo preço, e o preço tem de ser dito.
        tempo = "" if segundos is None else f" em {segundos:.1f} s".replace(".", ",")
        if not self.documento.para_texto().strip():
            # A folha vazia não é falha nem é «0 trecho(s)» (item 26): é uma página sem texto para
            # este motor -- capa, figura inteira, ou scan que o glifo não leu --, e a frase diz o
            # que tentar. O estado vazio do editor já está na tela.
            como = f"motor {self._motor}" + (", modo bloco" if self._modo_bloco else "")
            self.estado.emit(
                f"A folha {pagina.pagina + 1} não tem texto lido ({como}{tempo.replace(' em ', ', ')}): "
                "tente outro motor ou o modo bloco."
            )
            return
        self.estado.emit(f"Folha lida{tempo}: {len(self.documento.corridas)} trecho(s){figuras}.")
        # **Depois de desenhar, e não antes**: se a pessoa recusar a oferta, o que fica na tela é
        # a leitura que ela acabou de pedir (S-255).
        self.oferecer_rascunho(pagina)

    def _guardar_leitura(self) -> None:
        """A leitura do motor vai ao caderno na hora: é a folha `lida`, e a que se descarta para (S-616)."""
        cad = self._caderno_da_tela()
        if cad is None:
            return
        motor, bloco = self._leitura_de
        try:
            cad.guardar_leitura(self.documento, motor=motor or self._motor, modo_bloco=bloco)
        except OSError as erro:
            logger.warning("A leitura da folha não foi ao caderno: %s", erro)
            self.estado.emit(f"A folha lida não foi ao caderno: {erro}.")
        self._atualizar_status()
        self._rotular_leitura()
        self._mostrar_indice()

    def _leitura_falhou(self, erro: str, excecao: object = None) -> None:
        self._documento_ao_ler = None
        self._falha("Ler a folha", f"Não foi possível ler a folha:\n{erro}", excecao)

    # ------------------------------------------------------ o que a janela pergunta (S-283)

    def definir_livro(self, pdf: Path | None, *, pagina: int | None = None, paginas: int | None = None) -> None:
        """Diz à aba qual livro está aberto, em que folha o visualizador está e quantas folhas há.

        **A folha lida não cai junto**, e é de propósito: trocar de livro com uma folha corrigida
        na tela e ainda por gravar jogaria fora o trabalho sem perguntar. Quem descarta é `ler`,
        que pergunta antes.

        `paginas` é o teto do campo «Folha a ler» (item 15): com 9.999 cravado, quem digitava 500
        num livro de 289 folhas só descobria o erro na leitura, com a caixa vermelha do PyMuPDF.
        Sem o número (livro fechado, ou chamada antiga) o teto fica largo, como era.
        """
        novo = None if pdf is None else Path(pdf)
        if _chave_de_livro(novo) != _chave_de_livro(self._pdf):
            self._posicoes.clear()  # as posições são do livro que saiu (item 11)
            self._abrir_caderno(novo)
            if self._caderno is None:
                self._anunciar_rascunhos(novo)
            self._rotular_leitura()
        self._pdf = novo
        # O teto só muda quando se sabe o número ou quando o livro fecha: a virada de página chama
        # isto sem `paginas`, e não pode devolver o campo ao teto largo.
        if paginas:
            self.campo_de_folha.setMaximum(max(1, int(paginas)))
        elif novo is None:
            self.campo_de_folha.setMaximum(TETO_DE_FOLHAS)
        if pagina is not None:
            self._pagina_indice = int(pagina)
            self._montando = True
            try:
                self.campo_de_folha.setValue(self._pagina_indice + 1)
            finally:
                self._montando = False
            if self._na_mesa and novo is not None:
                self._seguir_a_pagina(int(pagina))

    def _anunciar_rascunhos(self, livro: Path | None) -> None:
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
        self.estado.emit(
            f"{len(achados)} rascunho(s) deste livro por recuperar (folha {folhas}): "
            "leia a folha e a aba oferece."
        )

    def definir_posicoes(self, pagina: int, posicoes: Sequence[str]) -> None:
        """O campo de peças de cada diagrama da folha, como o OCR de diagramas do produto leu.

        A aba Livro lê a posição com o classificador de peças; esta aba só sabia **onde** cada
        diagrama está. Com a FEN no bloco, o `.cvtxt` a guarda, o `.md` e o `.html` a escrevem
        (item 5) e a miniatura pode nascer dela quando o livro não está. Chega pela janela a cada
        leitura de diagramas (`_chegaram_itens`), em qualquer ordem em relação à leitura do texto:
        a folha que já está na tela recebe na hora, **sem virar alteração por gravar** -- a posição
        é leitura, não edição.
        """
        chave = (_chave_de_livro(self._pdf), int(pagina))
        self._posicoes[chave] = tuple(str(p or "") for p in posicoes)
        if (
            self._pagina is None
            or int(self._pagina.pagina) != int(pagina)
            or _chave_de_livro(self._pagina.documento) != chave[0]
        ):
            return
        nova = self._pagina.com_posicoes(self._posicoes[chave])
        if nova is self._pagina:
            return
        self._pagina = nova
        self.documento = rico.DocumentoRico(corridas=self.documento.corridas, origem=nova)
        if self._documento_gravado.origem is not None:
            self._documento_gravado = rico.DocumentoRico(corridas=self._documento_gravado.corridas, origem=nova)
        self._desenhar(selecao=self._selecao_atual())
        self._atualizar_status()

    def notacao_do_diagrama(self, pagina: int, diagrama: int) -> str:
        """A notação que o livro imprimiu ao lado daquele diagrama, ou `""` (S-283).

        **É o vínculo da S-249 com um cliente.** `BlocoDeTexto.legenda_de` diz de qual diagrama
        cada parágrafo é a legenda, e até a sala de estudo isso só pintava o estilo `legenda` na
        tela. A sala pergunta a mesma coisa por outro motivo: o parágrafo ao lado do diagrama 3
        costuma trazer a linha que o autor dá para aquela posição.

        **Devolve `""` em três casos, e todos são "ainda não sei"**: não há folha lida, a folha
        lida é de outra página, ou nenhum parágrafo daquele diagrama é notação. Nenhum deles é
        erro -- ler a folha custa de 1 s a 40 s, e é decisão de quem lê.

        O corte "é notação" é o de `text/notacao.e_linha_de_notacao`, o mesmo que a S-249 usa para
        pintar o estilo: a **maioria** dos tokens do parágrafo é lance.
        """
        from chess_diagram_ocr.text import notacao
        from chess_diagram_ocr.text import pagina as pagina_mod

        lida = self._pagina
        if lida is None or int(lida.pagina) != int(pagina):
            return ""
        trechos = [
            bloco.texto
            for bloco in lida.blocos
            if isinstance(bloco, pagina_mod.BlocoDeTexto)
            and bloco.legenda_de == int(diagrama)
            and notacao.e_linha_de_notacao(bloco.texto)
        ]
        return " ".join(trechos).strip()

    # ------------------------------------------------------------------------------ a digitação

    def _digitado(self, posicao: int, removidos: int, acrescidos: int) -> None:
        """Uma mudança do texto na tela -- tecla, colar, recortar, arrastar -- vira mudança do documento.

        `contentsChange` diz **onde** mudou; o que saiu vem de `_tela`, o texto como estava. Os
        números do Qt são conferidos contra os dois textos antes de serem usados, e a conta é
        refeita dos dois quando não batem: uma troca de formato chega pelo mesmo sinal sem mudar
        letra nenhuma, e um arrasto dentro da folha chega como **uma** janela que cobre a origem e
        o destino.
        """
        documento = self.editor.document()
        if self._redesenhando or self._sincronizando or documento is None:
            return
        antes, depois = self._tela, _texto_da_tela(documento)
        self._tela = depois
        janela = _janela_informada(antes, depois, posicao, removidos, acrescidos)
        if janela is None:
            return
        inicio, removido, acrescido = janela
        velho, novo = antes[inicio : inicio + removido], depois[inicio : inicio + acrescido]
        giro = _giro(velho, novo)
        if giro:
            self._arrastado(inicio, len(velho), giro)
            return
        if velho and len(novo) > 1:
            # Colar por cima de uma seleção, ou o Qt anunciando mais do que mudou: o que começa e
            # termina igual não foi trocado, e continua sendo o que era -- com atributo e marca.
            miolo = _janela_da_troca(velho, novo)
            if miolo is None:
                return
            inicio, removido, acrescido = inicio + miolo[0], miolo[1], miolo[2]
            novo = depois[inicio : inicio + acrescido]
        self._trocado(inicio, removido, novo)

    def _trocado(self, inicio: int, removido: int, novo: str) -> None:
        """Os `removido` caracteres em `inicio` deram lugar a `novo`: o documento acompanha, por `rico.editar`.

        **Fiel** é a troca que o documento aceitou como a tela a mostra: nenhuma miniatura saiu, nada
        que não é texto entrou, e `rico` não alargou nem recusou a troca. Aí o mapa anda junto e só o
        trecho novo é repintado -- é o caminho de toda tecla comum. O resto -- a marca do diagrama que
        sai inteira, a letra escrita dentro dela, a miniatura apagada sozinha -- redesenha a folha a
        partir do documento, que é quem manda, com o cursor no lugar da troca.
        """
        de = self._mapa.deslocamento(inicio)
        ate = self._mapa.deslocamento(inicio + removido)
        escrito = _do_qt(novo).replace(OBJETO, "")
        alcance = rico.alcance_da_edicao(self.documento, de, ate, escrito)
        if alcance is None:
            self.estado.emit(
                "A marca do diagrama não se edita por dentro: escreva antes ou depois dela, "
                "ou apague-a inteira."
            )
            self._desenhar(selecao=(de, de))
            return
        editado = rico.editar(self.documento, de, ate, escrito)
        mudou = editado is not self.documento
        if mudou:
            agora = self._relogio()
            passo = not continua_a_digitacao(self._digitacao, alcance[0], alcance[1], escrito, agora=agora)
            self._guardar_digitado(editado, passo=passo)
            self._digitacao = digitacao_depois(alcance[0], alcance[1], escrito, agora=agora)
        if removido == ate - de and escrito == novo and alcance == (de, ate):
            self._mapa.trocar(inicio, removido, de, len(escrito))
            self._pintar_o_digitado(inicio, len(escrito), de)
            return
        if alcance != (de, ate):
            self.estado.emit("O diagrama saiu da folha junto com a marca inteira; desfazer o devolve.")
        elif not mudou and removido > ate - de:
            # Só o desenho saiu -- a miniatura, a quebra embaixo dela --, e ele volta no redesenho.
            self.estado.emit(
                "A miniatura é desenho, e não texto: para tirar o diagrama da folha, apague a marca dele."
            )
        cursor = alcance[0] + len(escrito)
        self._desenhar(selecao=(cursor, cursor))

    def _arrastado(self, inicio: int, tamanho: int, giro: int) -> None:
        """Um trecho arrastado dentro da folha: o documento o leva inteiro, por `rico.mover`.

        A janela `[inicio, inicio + tamanho)` saiu girada de `giro`: os `giro` primeiros caracteres
        foram para o fim, ou os outros vieram para o começo -- as duas leituras dão a mesma tela, e
        a que se usa é a do trecho **menor**, que é o que a pessoa arrastou. Tratar o arrasto como
        apagar e escrever faria o trecho perder o que o Qt também perde ao soltar texto puro -- o
        atributo e, pior, a marca do diagrama, que chegaria como texto comum. Por isso a folha é
        redesenhada a partir do documento: o trecho volta com o que era.
        """
        if giro <= tamanho - giro:
            origem, destino = (inicio, inicio + giro), inicio + tamanho
        else:
            origem, destino = (inicio + giro, inicio + tamanho), inicio
        de, ate = rico.alcance_de_apagar(
            self.documento, self._mapa.deslocamento(origem[0]), self._mapa.deslocamento(origem[1])
        )
        para = self._mapa.deslocamento(destino)
        movido = rico.mover(self.documento, de, ate, para)
        self._digitacao = None
        if movido is self.documento:
            self.estado.emit("O trecho não pode ser solto ali: a marca do diagrama não se parte.")
            self._desenhar(selecao=(de, ate))
            return
        self._guardar_digitado(movido, passo=True)
        fim = para if para >= ate else para + (ate - de)
        self._desenhar(selecao=(fim - (ate - de), fim))

    def _guardar_digitado(self, novo: rico.DocumentoRico, *, passo: bool) -> None:
        """Põe `novo` no lugar do documento; `passo` empilha o anterior -- a tecla abriu um passo novo."""
        if passo:
            self._historico.append(self.documento)
            self._rotulos_do_historico.append("Digitação")
            self._refeitos.clear()
            self._rotulos_refeitos.clear()
        # Cresce a cada tecla, e não a cada passo: a pergunta de `ui/desfazivel` é "quem foi editado
        # por último", e a última tecla é a resposta mesmo dentro de um passo aberto (S-243).
        self._edicao += 1
        self.documento = novo
        self.documento_mudou.emit()

    def _pintar_o_digitado(self, inicio: int, tamanho: int, deslocamento: int) -> None:
        """Repinta só o trecho digitado, com o formato da corrida em que o documento o pôs.

        O Qt escreve a letra com o formato da vizinha **da tela**, e o documento escolheu outro
        quando as regras divergem: a faixa da mão no lugar do `revisar` herdado, o negrito da
        seleção que foi trocada. Sem isto a tela mostraria uma coisa e o arquivo gravaria outra até o
        próximo redesenho.
        """
        corrida = _corrida_em(self.documento, deslocamento)
        documento = self.editor.document()
        if tamanho <= 0 or corrida is None or documento is None:
            return
        cursor = QTextCursor(documento)
        cursor.setPosition(inicio)
        cursor.setPosition(inicio + tamanho, QTextCursor.MoveMode.KeepAnchor)
        self._sincronizando = True
        try:
            cursor.setCharFormat(formato_de(corrida, base=self._base))
            # O `Enter` cria um bloco que herda o formato do de cima; os blocos que a tecla tocou
            # recebem o que o documento pede, pela mesma regra do desenho inteiro (S-601).
            if "\n" in self._tela[inicio : inicio + tamanho]:
                self._formatar_blocos(documento, max(0, inicio - 1), inicio + tamanho + 1)
        finally:
            self._sincronizando = False

    # ------------------------------------------------------------------------------ teclado

    def eventFilter(self, a0: object, a1: object) -> bool:  # noqa: N802 - assinatura do Qt
        """`Ctrl+Z` e `Ctrl+Y` dentro da folha são deste painel; o estado vazio acompanha o poço.

        A tecla de desfazer chega ao editor porque a guarda de atalhos a cede a todo campo de
        texto -- e o desfazer do `QTextEdit` está desligado. Ver `TECLAS_DO_HISTORICO`.

        **Nada é filtrado antes de o `_montar` terminar.** O filtro entra no editor antes de o rodapé
        (`self.status`) existir, e o editor já recebe eventos no meio da montagem: a pergunta
        `a0 is self.status` levantava `AttributeError` dentro do filtro. No 3.10 o PyQt só imprime a
        exceção; no 3.13 ela vira `qFatal`, e a CI morria sem uma linha em `test_app_pyqt`.
        """
        if not self._montado:
            return False
        if a0 is self.editor and isinstance(a1, QKeyEvent) and a1.type() == QEvent.Type.KeyPress:
            combinacao = QKeySequence(a1.keyCombination())
            for acao, tecla in self._teclas_do_historico.items():
                alvo = self.atender(acao) if tecla == combinacao else None
                if alvo is not None:
                    alvo()
                    return True
            if a1.key() == Qt.Key.Key_Escape and self._sair_com_esc():
                return True
            # Enter com a marca inteira selecionada abre o diagrama no Estudo (item 30): é o
            # duplo clique do item 8 para quem anda pelo teclado -- o clique (ou Shift+setas)
            # seleciona a marca, o Enter a ativa. Com qualquer outra seleção o Enter é o Enter.
            if a1.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not a1.modifiers() and self._ativar_marca_selecionada():
                return True
        if a0 is self.status and isinstance(a1, QMouseEvent) and a1.type() == QEvent.Type.MouseButtonRelease:
            self.ir_ao_campo_de_folha()
            return True
        if a0 is self.editor.viewport() and isinstance(a1, QEvent) and a1.type() == QEvent.Type.Resize:
            self.vazio.setGeometry(self._area_da_folha())
        if a0 is self.editor.viewport() and isinstance(a1, QHelpEvent) and a1.type() == QEvent.Type.ToolTip:
            # A dica sobre a miniatura (item 23): o que ela é, a posição, e o que o clique faz.
            dica = self._dica_da_marca(a1.pos())
            if dica:
                QToolTip.showText(a1.globalPos(), dica, self.editor.viewport())
            else:
                QToolTip.hideText()
            return True
        if a0 is self.editor.viewport() and isinstance(a1, QWheelEvent) and a1.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+roda é o zoom da vista (item 13). O `QTextEdit` responderia mudando a fonte do
            # editor -- que nenhuma letra segue, porque cada trecho sai com corpo explícito (S-264).
            passo = a1.angleDelta().y()
            if passo:
                self._zoom_ancorado(a1.position().toPoint(), +1 if passo > 0 else -1)
            return True
        if a0 is self.editor.viewport() and isinstance(a1, QMouseEvent) and a1.button() == Qt.MouseButton.LeftButton:
            ponto = a1.position().toPoint()
            if a1.type() == QEvent.Type.MouseButtonPress and self._clicou_na_miniatura(ponto):
                return True
            if a1.type() == QEvent.Type.MouseButtonDblClick and self._ativou_a_miniatura(ponto):
                return True
        return super().eventFilter(a0, a1)  # type: ignore[arg-type]

    # ------------------------------------------------------------------- a miniatura (item 8)

    def _marca_sob(self, ponto: QPoint) -> tuple[int, int, rico.Corrida] | None:
        """A marca `[Diagrama N]` da miniatura que está sob o ponto: `(começo, fim, corrida)`.

        A miniatura é um caractere do widget que não existe no documento (`_Mapa`); a marca dela
        vem logo depois, no bloco seguinte. O cursor que o Qt dá para o ponto cai antes ou depois
        do caractere da imagem, e por isso se sondam os dois.
        """
        documento = self.editor.document()
        if documento is None:
            return None
        posicao = self.editor.cursorForPosition(ponto).position()
        for p in (posicao, posicao - 1):
            if p < 0:
                continue
            sonda = QTextCursor(documento)
            sonda.setPosition(p + 1)  # `charFormat` é o do caractere **antes** do cursor: o `p`
            if sonda.position() != p + 1 or not sonda.charFormat().isImageFormat():
                continue
            achado = self._marca_em(self._mapa.deslocamento(p + 2))
            if achado is not None:
                return achado
        # Sobre o texto da própria marca (item 12): `[Diagrama 3]` é o diagrama tanto quanto a
        # figura -- e é tudo o que há dele quando não há figura nenhuma.
        return self._marca_em(self._mapa.deslocamento(posicao))

    def _marca_em(self, deslocamento: int) -> tuple[int, int, rico.Corrida] | None:
        """A marca de diagrama que contém o deslocamento do documento, ou `None`."""
        comeco = 0
        for corrida in self.documento.corridas:
            fim = comeco + len(corrida.texto)
            if corrida.e_diagrama and comeco <= deslocamento < fim:
                return comeco, fim, corrida
            comeco = fim
        return None

    def _dica_da_marca(self, ponto: QPoint) -> str:
        """O texto da dica sobre a miniatura ou a marca, ou `""` fora delas (item 23).

        Três linhas: o que é («Diagrama 3 da folha 14»), a posição quando se sabe (a FEN, que o
        item 20 também copia) e o que o gesto faz -- a dica é onde quem passa o mouse descobre o
        duplo clique e o botão direito sem ter de adivinhar.
        """
        achado = self._marca_sob(ponto)
        if achado is None:
            return ""
        corrida = achado[2]
        numero = int(getattr(self.documento.bloco_de(corrida), "indice", corrida.bloco)) + 1
        folha = "" if self._pagina is None else f" da folha {int(self._pagina.pagina) + 1}"
        linhas = [f"Diagrama {numero}{folha}"]
        posicao = _posicao_de(self.documento, corrida)
        linhas.append(f"FEN: {posicao}" if posicao else "Posição ainda não lida (OCR dos diagramas na aba Livro)")
        linhas.append("Duplo clique abre no Estudo · botão direito: copiar, apagar")
        return "\n".join(linhas)

    def _clicou_na_miniatura(self, ponto: QPoint) -> bool:
        """O clique na miniatura seleciona a marca dela: é a marca que se apaga, move e copia.

        Sem isto o clique punha o cursor ao lado de um caractere invisível, e a pessoa apagava a
        figura sem apagar o diagrama (`_trocado` avisa, mas avisar é o segundo melhor).
        """
        achado = self._marca_sob(ponto)
        if achado is None:
            return False
        comeco, fim, _corrida = achado
        cursor = self.editor.textCursor()
        cursor.setPosition(self._mapa.posicao(comeco))
        cursor.setPosition(self._mapa.posicao(fim), QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()
        return True

    def _abrir_menu_de_contexto(self, ponto: QPoint) -> None:
        menu = self._menu_de_contexto(ponto)
        folha = self.editor.viewport()
        menu.exec(folha.mapToGlobal(ponto) if folha is not None else self.editor.mapToGlobal(ponto))
        menu.deleteLater()

    def _menu_de_contexto(self, ponto: QPoint) -> QMenu:
        """O menu do botão direito: o padrão do editor e, sobre uma miniatura, o que ela sabe fazer.

        Três ações, e as três já existiam por outro caminho -- é o que as mantém fora do catálogo
        de comandos (S-256): abrir na sala é o duplo clique (item 8), copiar a imagem é o que a
        aba Livro faz com o recorte, apagar o diagrama é apagar a marca, que o clique já
        seleciona. O menu é onde quem não sabe do duplo clique descobre que a miniatura é viva.
        """
        menu = self.editor.createStandardContextMenu(ponto)
        assert menu is not None  # o Qt só devolve `None` sem documento, e o editor sempre tem um
        self._sugestoes_no_menu(menu, ponto)
        # O rascunho da folha na tela, quando há um (item 25): a oferta recusada na leitura volta
        # a estar à mão, sem reler a folha.
        guardado = (
            None
            if self._pagina is None
            else rascunho.achar(self._pagina.documento, self._pagina.pagina, pasta=self._pasta_de_rascunhos)
        )
        if guardado is not None:
            menu.addSeparator()
            recuperar = QAction(f"Recuperar o rascunho de {guardado.data_legivel}", menu)
            recuperar.triggered.connect(lambda: self.recuperar_rascunho())
            menu.addAction(recuperar)
        self._menu_do_caderno(menu)
        achado = self._marca_sob(ponto)
        if achado is None:
            return menu
        comeco, fim, corrida = achado
        numero = int(getattr(self.documento.bloco_de(corrida), "indice", -1)) + 1
        menu.addSeparator()
        estudar = QAction(f"Abrir o diagrama {numero} no Estudo", menu)
        estudar.triggered.connect(lambda: self._ativou_a_miniatura(ponto))
        copiar = QAction(f"Copiar a imagem do diagrama {numero}", menu)
        copiar.triggered.connect(lambda: self._copiar_miniatura(corrida))
        apagar = QAction(f"Apagar o diagrama {numero} da folha", menu)
        apagar.triggered.connect(lambda: self._apagar_diagrama(comeco, fim, numero))
        for acao in (estudar, copiar, apagar):
            menu.addAction(acao)
        return menu

    def _menu_do_caderno(self, menu: QMenu) -> None:
        """O que o caderno sabe fazer com a folha da tela (S-611, S-612, S-616).

        No menu do botão direito, e não no catálogo, até a fita (S-650) e o índice (S-613) lhes darem
        lugar: são gestos sobre **esta** folha, e o menu dela é onde a pessoa os procura.
        """
        cad = self._caderno_da_tela()
        if cad is None or cad.somente_leitura:
            return
        pagina = int(self.documento.origem.pagina)  # type: ignore[union-attr]
        guardada = cad.estado(pagina)
        menu.addSeparator()
        acoes: list[tuple[str, Callable[[], object]]] = [("Ler a folha de novo", self.ler_de_novo)]
        if cad.caminho(pagina, tipo="anterior").exists():
            acoes.append(("Voltar à versão anterior desta folha", self.voltar_a_anterior))
        if cad.caminho(pagina, tipo="lida").exists() and (guardada is None or guardada.correcoes or self._correcoes):
            acoes.append(("Descartar as correções desta folha", self.descartar_correcoes))
        if guardada is not None:
            conferida = guardada.estado == caderno.CONFERIDA
            acoes.append(("Desmarcar a folha como conferida" if conferida else "Marcar a folha como conferida", self.marcar_conferida))
        for rotulo, alvo in acoes:
            acao = QAction(rotulo, menu)
            acao.triggered.connect(lambda _marcado=False, alvo=alvo: alvo())
            menu.addAction(acao)

    def _copiar_miniatura(self, corrida: rico.Corrida) -> None:
        """A figura do diagrama -- recorte ou desenho -- vai para a área de transferência, **e a
        FEN vai junto como texto** quando se sabe (item 20).

        Um só gesto para os dois destinos: quem cola num editor de imagens recebe a figura; quem
        cola numa caixa de texto -- um programa de xadrez, um e-mail -- recebe o campo de peças.
        """
        from PyQt6.QtCore import QMimeData

        figura = self._imagem_do_diagrama(corrida)
        posicao = _posicao_de(self.documento, corrida)
        if figura is None and not posicao:
            self.estado.emit("Este diagrama não tem figura nem posição para copiar.")
            return
        conteudo = QMimeData()
        if figura is not None:
            conteudo.setImageData(figura.toImage())
        if posicao:
            conteudo.setText(posicao)
        area = QApplication.clipboard()
        if area is not None:
            area.setMimeData(conteudo)
        o_que = "Imagem e FEN do diagrama copiadas." if figura is not None and posicao else (
            "Imagem do diagrama copiada." if figura is not None else "FEN do diagrama copiada."
        )
        self.estado.emit(o_que)

    def _apagar_diagrama(self, comeco: int, fim: int, numero: int) -> None:
        """Tira a marca inteira -- e com ela a figura. É uma edição: `Ctrl+Z` a devolve."""
        self._aplicar(rico.apagar(self.documento, comeco, fim), selecao=(comeco, comeco))
        self.estado.emit(f"O diagrama {numero} saiu da folha; desfazer o devolve.")

    def _ativar_marca_selecionada(self) -> bool:
        """Se a seleção é exatamente uma marca `[Diagrama N]`, pede o diagrama na sala."""
        inicio, fim = self._intervalo()
        achado = self._marca_em(inicio) if fim > inicio else None
        if achado is None or (achado[0], achado[1]) != (inicio, fim) or self._pagina is None:
            return False
        indice = getattr(self.documento.bloco_de(achado[2]), "indice", None)
        if indice is None:
            return False
        self.diagrama_ativado.emit(int(self._pagina.pagina), int(indice))
        return True

    def _ativou_a_miniatura(self, ponto: QPoint) -> bool:
        """O duplo clique na miniatura pede o diagrama na sala de estudo (`diagrama_ativado`)."""
        achado = self._marca_sob(ponto)
        if achado is None or self._pagina is None:
            return False
        bloco = self.documento.bloco_de(achado[2])
        indice = getattr(bloco, "indice", None)
        if indice is None:
            return False
        self.diagrama_ativado.emit(int(self._pagina.pagina), int(indice))
        return True

    def _mostrar_vazio(self) -> None:
        """Mostra o estado vazio enquanto não há folha nenhuma no editor (F9-C2, §7 item 14).

        Some no primeiro caractere, e é isso que o mantém fora da exportação: o `EstadoVazio` é um
        widget **sobre** o editor, e não texto dentro dele -- que era a razão de o ciclo 1 ter
        escolhido `placeholderText`, e que continua valendo.
        """
        self.vazio.setGeometry(self._area_da_folha())
        # O vazio da mesa que virou a página para uma folha sem caderno diz **qual** folha (S-644).
        por_ler = self._folha_por_ler
        self.vazio.titulo.setText(strings.TEXTO_VAZIO_TITULO if por_ler is None else strings.folha_por_ler(por_ler + 1))
        self.vazio.frase.setText(strings.TEXTO_VAZIO_FRASE if por_ler is None else strings.FOLHA_POR_LER_FRASE)
        if self.vazio.botao is not None:
            self.vazio.botao.setText(
                comandos.rotulo_de_botao("ler_folha") if por_ler is None else strings.ler_a_folha(por_ler + 1)
            )
        self.vazio.setVisible(not self.editor.toPlainText().strip())

    def _area_da_folha(self) -> QRect:
        """O retângulo da área de desenho do editor, sem o `Optional` de `viewport()`."""
        folha = self.editor.viewport()
        return folha.rect() if folha is not None else self.editor.rect()

    def acoes_proprias(self) -> frozenset[str]:
        """As ações globais que este painel atende enquanto tem o foco (S-244).

        A lista é `ui/texto_declarado.ACOES_PROPRIAS`, a mesma do outro frontend: `Ctrl+S` com o
        cursor no texto salva o texto, e não a posição do tabuleiro.
        """
        return ACOES_PROPRIAS

    def atender(self, acao: str) -> Callable[[], object] | None:
        """A função deste painel para aquela ação. Declarar e não atender come a tecla."""
        return {
            "salvar": self.salvar_documento,
            "desfazer": self.desfazer,
            "refazer": self.refazer,
            "achar": self.achar,
            "substituir": self.substituir,
        }.get(acao)

    def executar(self, acao: str) -> None:
        """Roda o método que `COMANDOS_DA_ABA` liga àquela ação.

        **A tabela é a mesma dos dois frontends**, e é por isso que os métodos deste painel se
        chamam como os de `ui/texto_panel.py`. Um método com outro nome deixaria o comando no menu,
        na paleta e nas três peles -- sem fazer nada, e sem nada acusar (S-240).
        """
        self._rotulo_corrente = comandos.rotulo_de_botao(acao) if _no_catalogo(acao) else acao
        try:
            getattr(self, COMANDOS_DA_ABA[acao])()
        finally:
            self._rotulo_corrente = ""


def _renderizar(caminho: Path, indice: int, *, dpi: int) -> np.ndarray | None:
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


def _ler(
    caminho: Path,
    indice: int,
    *,
    dpi: int,
    motor: str,
    modo_bloco: bool,
    imagem_rgb: np.ndarray | None,
    max_boards: int | None = None,
) -> PaginaLida:
    """`ler_pagina` com a folha já renderizada. **O `import` do leitor mora aqui** -- ver `ler`."""
    from chess_diagram_ocr.text.leitor import ler_pagina

    return ler_pagina(
        caminho, indice, dpi=dpi, motor=motor, modo_bloco=modo_bloco, imagem_rgb=imagem_rgb, max_boards=max_boards  # type: ignore[arg-type]
    )


def _recorte_da_folha(folha: np.ndarray, bloco: object, *, dpi: int) -> np.ndarray | None:
    """O pedaço da folha renderizada em que o bloco está, ou `None` sem `bbox` útil.

    **O bbox do bloco está em pontos e a folha em pixels**, e o fator entre os dois é o DPI com
    que ela foi renderizada. Usar outro aqui recortaria o lugar errado da folha em silêncio.
    Pura, e sem Qt: é a mesma função para a miniatura na tela e para o PNG da exportação.
    """
    bbox = getattr(bloco, "bbox", None)
    if bbox is None:
        return None
    fator = dpi / 72.0
    altura, largura = folha.shape[:2]
    x0 = max(0, int(bbox[0] * fator))
    y0 = max(0, int(bbox[1] * fator))
    x1 = min(largura, int(bbox[2] * fator))
    y1 = min(altura, int(bbox[3] * fator))
    if x1 <= x0 or y1 <= y0:
        return None
    return folha[y0:y1, x0:x1]


def _gravar_recortes(
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
        imagem = _recorte_da_folha(folha, bloco, dpi=dpi) if folha is not None else None
        # Sem folha, o desenho da posição lida (item 7) -- a mesma reserva da miniatura na tela.
        desenho = _png_da_posicao(bloco.placement, lado_px=LADO_DO_RECORTE_DESENHADO) if imagem is None else None
        if imagem is None and desenho is None:
            continue
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            arquivo_png = pasta / f"{destino.stem}_d{bloco.indice + 1}.png"
            if imagem is not None:
                Image.fromarray(np.ascontiguousarray(imagem)).convert("RGB").save(arquivo_png)
            else:
                # Atômica, como toda gravação do projeto (`tests/test_atomic_writes.py`).
                from chess_diagram_ocr.atomic_io import atomic_write_bytes

                atomic_write_bytes(arquivo_png, desenho or b"")
        except Exception as erro:  # noqa: BLE001 - recorte é conforto, e a marca sai sem ele
            logger.debug("Recorte do diagrama %d não gravado: %s", bloco.indice + 1, erro)
            continue
        recortes[chave] = arquivo_png
    return recortes


LADO_DO_RECORTE_DESENHADO = 400
"""O lado, em pixel, do diagrama desenhado da FEN para a exportação: perto do que um recorte a
220 dpi mede, para o `.html` não trocar de escala conforme a origem da figura."""


def _chave_de_livro(caminho: Path | str | None) -> str:
    """A identidade de um livro para a aba: o caminho resolvido, ou `""` sem livro."""
    if not caminho:
        return ""
    try:
        return str(Path(caminho).resolve()).casefold()
    except OSError:  # pragma: no cover - caminho que o sistema recusa resolver
        return str(caminho).casefold()


def _no_livro(doc: rico.DocumentoRico, livro: Path | None) -> rico.DocumentoRico:
    """O documento apontando para o livro onde ele está agora.

    O caderno acha o livro pelo conteúdo (S-610), e a folha guardada pode ter sido lida quando o
    PDF morava noutra pasta: com a origem velha, as miniaturas procurariam o livro no lugar de
    antes, e a folha deixaria de parecer do livro aberto.
    """
    origem = doc.origem
    if origem is None or livro is None or origem.documento == str(livro):
        return doc
    return replace(doc, origem=replace(origem, documento=str(livro)))


def _mesmo_livro(um: Path, outro: Path) -> bool:
    """O mesmo PDF apesar da grafia do caminho -- a regra de `qt/dialogos._mesmo`."""
    try:
        return Path(um).resolve() == Path(outro).resolve()
    except OSError:  # pragma: no cover - caminho que o sistema recusa resolver
        return str(um).lower() == str(outro).lower()


def _posicao_de(doc: rico.DocumentoRico, corrida: rico.Corrida) -> str:
    """O campo de peças do bloco desta marca, ou `""` quando ninguém o leu."""
    return str(getattr(doc.bloco_de(corrida), "placement", "") or "")


def _png_da_posicao(placement: str, *, lado_px: int) -> bytes | None:
    """O diagrama desenhado da FEN, em PNG, ou `None` sem posição ou quando o desenho falha.

    Desenha com as peças do próprio programa (`desenho_de_diagrama`, sem Qt): a mesma figura que
    a exportação do livro usa. O `import` é tardio porque ele carrega a Pillow e o conjunto de
    peças, e a aba abre sem precisar deles.
    """
    if not placement:
        return None
    try:
        from chess_diagram_ocr.desenho_de_diagrama import png_do_diagrama

        return png_do_diagrama(placement, lado_px=lado_px)
    except Exception as erro:  # noqa: BLE001 - a figura é conforto; a marca fica
        logger.debug("Diagrama não desenhado da posição %r: %s", placement, erro)
        return None


def _no_catalogo(acao: str) -> bool:
    """Se o catálogo de comandos conhece esta ação. Ver `_botao`."""
    try:
        comandos.rotulo(acao)
    except KeyError:
        return False
    return True


def _url(nome: str):  # noqa: ANN202 - QUrl, importado tarde para o módulo abrir sem QtCore
    from PyQt6.QtCore import QUrl

    return QUrl(nome)


def _teclas_do_editor() -> dict[str, QKeySequence]:
    """`ação -> QKeySequence` das teclas próprias do editor (`atalhos.TECLAS_DO_EDITOR`)."""
    teclas: dict[str, QKeySequence] = {}
    for acao, sequencia in atalhos.TECLAS_DO_EDITOR.items():
        try:
            teclas[acao] = QKeySequence(qt_atalhos.sequencia_qt(sequencia))
        except ValueError as erro:
            logger.warning("A tecla de %s não traduziu para o Qt (%s).", acao, erro)
    return teclas


def _teclas_da_tabela(acoes: Iterable[str]) -> dict[str, QKeySequence]:
    """`ação -> QKeySequence`, **da tabela** (`ui/atalhos`). Ação sem tecla fica de fora, sem levantar.

    Uma tecla que não traduz não pode custar o painel: ela sai no log, e o botão da barra continua
    desfazendo -- é a disciplina de `qt/menu._acao`.
    """
    teclas: dict[str, QKeySequence] = {}
    for acao in acoes:
        atalho = atalhos.por_acao.get(acao)
        if atalho is None:
            continue
        try:
            teclas[acao] = QKeySequence(qt_atalhos.sequencia_qt(atalho.sequencia))
        except ValueError as erro:
            logger.warning("A tecla de %s não traduziu para o Qt (%s).", acao, erro)
    return teclas


def _texto_da_tela(documento: QTextDocument) -> str:
    """O texto do widget **posição por posição**, com as quebras escritas como `\\n`.

    `toRawText` e não `toPlainText`: o segundo troca o espaço inseparável por espaço comum, e a
    letra que a pessoa não tocou sairia trocada no documento. As duas quebras do Qt -- a de
    parágrafo (`Enter`) e a de linha (`Shift+Enter`) -- viram a quebra do documento; todas valem um
    caractere, e é isso que mantém as posições.
    """
    cru = documento.toRawText().replace("\u2029", "\n").replace("\u2028", "\n")
    if cru.isascii() or all(ord(letra) <= 0xFFFF for letra in cru):
        return cru
    # A letra fora do plano básico vale **duas** posições no Qt, e o PyQt a entrega como uma letra
    # só: o texto é refeito em unidades UTF-16, com o par substituto em duas letras soltas, para que
    # o índice deste texto seja a posição do Qt. Quem leva texto daqui ao documento passa por `_do_qt`.
    unidades = cru.encode("utf-16-le", "surrogatepass")
    return "".join(chr(int.from_bytes(unidades[i : i + 2], "little")) for i in range(0, len(unidades), 2))


def _do_qt(texto: str) -> str:
    """O contrário da metade de `_texto_da_tela`: os pares substitutos soltos voltam a ser uma letra."""
    if all(not 0xD800 <= ord(letra) <= 0xDFFF for letra in texto):
        return texto
    return texto.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")


def _comum_no_comeco(a: str, b: str) -> int:
    """Quantos caracteres do começo `a` e `b` dividem. Busca binária sobre fatias: quem compara é o C."""
    baixo, alto = 0, min(len(a), len(b))
    while baixo < alto:
        meio = (baixo + alto + 1) // 2
        if a[:meio] == b[:meio]:
            baixo = meio
        else:
            alto = meio - 1
    return baixo


def _comum_no_fim(a: str, b: str, limite: int) -> int:
    """Quantos caracteres do fim `a` e `b` dividem, até `limite`."""
    baixo, alto = 0, limite
    while baixo < alto:
        meio = (baixo + alto + 1) // 2
        if a[len(a) - meio :] == b[len(b) - meio :]:
            baixo = meio
        else:
            alto = meio - 1
    return baixo


def _janela_da_troca(antes: str, depois: str) -> tuple[int, int, int] | None:
    """`(início, removidos, acrescidos)` da menor janela que leva `antes` a `depois`; `None` se iguais."""
    if antes == depois:
        return None
    comeco = _comum_no_comeco(antes, depois)
    fim = _comum_no_fim(antes, depois, min(len(antes), len(depois)) - comeco)
    return comeco, len(antes) - comeco - fim, len(depois) - comeco - fim


def _janela_informada(
    antes: str, depois: str, posicao: int, removidos: int, acrescidos: int
) -> tuple[int, int, int] | None:
    """A janela que o Qt anunciou, **se ela bate com os dois textos** -- senão a que os dois dizem.

    Bater é: o que vem antes dela e o que vem depois dela são iguais nos dois textos. É o caso de
    toda tecla medida no Qt 6.11; a conta de reserva existe para a versão que anunciar o documento
    inteiro. `None` quando nenhuma letra mudou -- é a troca de formato, que chega pelo mesmo sinal.
    """
    fim_antes, fim_depois = posicao + removidos, posicao + acrescidos
    if (
        0 <= posicao
        and fim_antes <= len(antes)
        and fim_depois <= len(depois)
        and antes[:posicao] == depois[:posicao]
        and antes[fim_antes:] == depois[fim_depois:]
    ):
        if antes[posicao:fim_antes] == depois[posicao:fim_depois]:
            return None
        return posicao, removidos, acrescidos
    return _janela_da_troca(antes, depois)


def _giro(velho: str, novo: str) -> int:
    """Se `novo` é `velho` girado -- o que um arrasto dentro da mesma janela produz --, de quanto.

    `0` quando não é giro. O espaço inseparável é comparado como espaço: o texto que o `QTextEdit`
    arrasta passa pela área de transferência como texto puro, e ali ele já virou espaço comum.
    """
    if len(velho) != len(novo) or len(velho) < 2 or velho == novo:
        return 0
    a, b = velho.replace("\xa0", " "), novo.replace("\xa0", " ")
    giro = (a + a).find(b)
    return giro if 0 < giro < len(a) else 0


def _corrida_em(doc: rico.DocumentoRico, deslocamento: int) -> rico.Corrida | None:
    """A corrida que contém aquele deslocamento, ou `None` fora do texto."""
    comeco = 0
    for corrida in doc.corridas:
        fim = comeco + len(corrida.texto)
        if comeco <= deslocamento < fim:
            return corrida
        comeco = fim
    return None


class JanelaDeBusca(QDialog):
    """Achar e substituir na folha (S-343).

    **A lista é o item, e não o "próximo".** Uma busca que só anda de ocorrência em ocorrência
    obriga a percorrer o texto para saber quantas há e onde elas estão; a lista responde as duas
    perguntas de uma vez, com o contexto de cada uma -- e é ela que torna a substituição em massa
    conferível antes de acontecer.

    **Quem acha é `text/busca.py`**, que é puro: o padrão, a figurina que casa com a letra, o
    contexto em volta e o bloco de cada ocorrência. Esta janela mostra o que ele devolveu.
    """

    def __init__(self, painel: PainelDeTexto, *, substituindo: bool = False) -> None:
        super().__init__(painel)
        self._painel = painel
        self._achadas: tuple[busca.Ocorrencia, ...] = ()
        self.setWindowTitle("Achar e substituir")
        self.resize(520, 400)

        pilha = QVBoxLayout(self)
        pilha.setContentsMargins(*(espaco.moldura(),) * 4)
        pilha.setSpacing(espaco.folga())

        # **Os dois campos dividem a mesma coluna** (F9-C13, §5.8). Eles não compartilhavam nem a
        # borda esquerda (57 px contra 78) nem a direita (505 contra 396): num formulário de duas
        # linhas, as duas caixas desalinhadas nas duas pontas. A esquerda vem dos dois rótulos
        # com a **mesma** largura; a direita, de uma calha do tamanho do botão reservada na linha
        # de cima -- e ela só existe enquanto a linha de baixo existe, porque alinhar com uma
        # linha escondida seria um buraco no lugar de um alinhamento.
        linha = QHBoxLayout()
        linha.setSpacing(espaco.linha())
        rotulo_de_achar = QLabel("Achar", self)
        linha.addWidget(rotulo_de_achar)
        self.campo_agulha = QLineEdit(self)
        self.campo_agulha.textChanged.connect(lambda _t: self.procurar())
        linha.addWidget(self.campo_agulha, 1)
        self.calha_da_troca = QWidget(self)
        linha.addWidget(self.calha_da_troca)
        pilha.addLayout(linha)

        self.linha_de_troca = QWidget(self)
        troca = QHBoxLayout(self.linha_de_troca)
        troca.setContentsMargins(0, 0, 0, 0)
        troca.setSpacing(espaco.linha())
        rotulo_de_troca = QLabel("Trocar por", self.linha_de_troca)
        troca.addWidget(rotulo_de_troca)
        self.campo_novo = QLineEdit(self.linha_de_troca)
        troca.addWidget(self.campo_novo, 1)
        self.btn_trocar = QPushButton("Substituir todos", self.linha_de_troca)
        self.btn_trocar.clicked.connect(self.substituir_todos)
        tema.aplicar_papel(self.btn_trocar, estilos.NEUTRO)
        troca.addWidget(self.btn_trocar)
        pilha.addWidget(self.linha_de_troca)

        largura_do_rotulo = max(
            rotulo_de_achar.sizeHint().width(), rotulo_de_troca.sizeHint().width()
        )
        for etiqueta in (rotulo_de_achar, rotulo_de_troca):
            etiqueta.setFixedWidth(largura_do_rotulo)
        self.calha_da_troca.setFixedWidth(self.btn_trocar.sizeHint().width())

        opcoes = QHBoxLayout()
        self.caixa_de_caixa = QCheckBox("Diferenciar maiúsculas", self)
        self.caixa_de_figurina = QCheckBox("A letra casa a figurina", self)
        dica_em(
            self.caixa_de_figurina,
            "Procurar «Nf3» acha «♘f3» também: a folha lida traz a figurina, e quem digita\n"
            "a busca tem o teclado.",
        )
        for caixa in (self.caixa_de_caixa, self.caixa_de_figurina):
            caixa.toggled.connect(lambda _ligado: self.procurar())
            opcoes.addWidget(caixa)
        opcoes.addStretch(1)
        pilha.addLayout(opcoes)

        self.lista = QListWidget(self)
        # Sem isto a cascata devolve `"Lista"` -- o eco do papel, que o portão do ciclo 2
        # reprova e que o do ciclo 12 passou a ver porque passou a abrir os diálogos.
        self.lista.setAccessibleName("Ocorrências achadas")
        self.lista.currentRowChanged.connect(self._mostrar)
        pilha.addWidget(self.lista, 1)
        # **O mesmo componente da janela principal** (F9-C14, item 4 do §7 do ciclo 13). A lista
        # abria em branco e a única pista era `Nada achado.` num rótulo abaixo dela.
        self.vazio = EstadoVazio(
            self.lista,
            titulo=strings.BUSCA_SEM_AGULHA_TITULO,
            frase=strings.BUSCA_SEM_AGULHA_FRASE,
        )

        self.lbl_conta = QLabel("", self)
        pilha.addWidget(self.lbl_conta)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        botoes.rejected.connect(self.reject)
        pilha.addWidget(botoes)

        self._mostrar_vazio()
        self.mostrar(substituindo=substituindo)

    def showEvent(self, a0: object) -> None:  # noqa: N802 - API do Qt
        """Sincroniza a calha com a largura **de verdade** do botão (F9-C14).

        A calha é medida por `sizeHint()` na montagem, e a escala tipográfica chega depois: o
        filtro de `QEvent.Show` de `qt/acessibilidade` põe o degrau `ACAO` -- peso 600 -- no
        `Substituir todos`, e um botão meio-negrito é 1 px mais largo. Um pixel é pouco e é
        exatamente o tipo de diferença que este item existe para não ter: as duas caixas dividem
        a mesma coluna ou não dividem.

        O filtro da aplicação roda **antes** do `event()` do objeto, então aqui o `sizeHint` já é
        o da fonte final.
        """
        super().showEvent(a0)  # type: ignore[arg-type]
        self.calha_da_troca.setFixedWidth(self.btn_trocar.sizeHint().width())

    def mostrar(self, *, substituindo: bool) -> None:
        """Traz a janela para a frente, com o campo de troca à mostra ou escondido.

        A calha some junto com a linha que ela alinha (F9-C14): sem a segunda caixa não há o que
        alinhar, e uma calha sozinha é um buraco de 100 px à direita do campo `Achar`.
        """
        self.linha_de_troca.setVisible(substituindo)
        self.calha_da_troca.setVisible(substituindo)
        self.show()
        self.raise_()
        self.activateWindow()
        self.campo_agulha.setFocus()

    def procurar(self) -> tuple[busca.Ocorrencia, ...]:
        """Refaz a lista a cada tecla. Agulha vazia devolve vazio, e a lista fica vazia junto."""
        self._achadas = busca.achar(
            self._painel.documento,
            self.campo_agulha.text(),
            casar_figurina=self.caixa_de_figurina.isChecked(),
            diferenciar_caixa=self.caixa_de_caixa.isChecked(),
        )
        self.lista.clear()
        for ocorrencia in self._achadas:
            self.lista.addItem(ocorrencia.contexto)
        self.lbl_conta.setText(
            "Nada achado." if not self._achadas else f"{len(self._achadas)} ocorrência(s)."
        )
        self._mostrar_vazio()
        return self._achadas

    def _mostrar_vazio(self) -> None:
        """O vazio da lista, e **qual** vazio ele é: sem agulha digitada ou sem ocorrência."""
        vista = self.lista.viewport()
        self.vazio.setGeometry(vista.rect() if vista is not None else self.lista.rect())
        procurando = bool(self.campo_agulha.text())
        self.vazio.titulo.setText(
            strings.BUSCA_SEM_ACHADO_TITULO if procurando else strings.BUSCA_SEM_AGULHA_TITULO
        )
        self.vazio.frase.setText(
            strings.BUSCA_SEM_ACHADO_FRASE if procurando else strings.BUSCA_SEM_AGULHA_FRASE
        )
        self.vazio.setVisible(not self._achadas)

    def _mostrar(self, linha: int) -> None:
        if 0 <= linha < len(self._achadas):
            achada = self._achadas[linha]
            self._painel.mostrar_intervalo(achada.inicio, achada.fim)

    def substituir_todos(self) -> None:
        """Troca **todas** as achadas de uma vez, e diz quantas foram.

        Uma só chamada, e não uma por ocorrência: a substituição inteira entra na pilha como um
        passo, e `Ctrl+Z` reverte a troca toda -- e não troca a troca.
        """
        if not self._achadas:
            self._painel.estado.emit("Não há ocorrência para substituir.")
            return
        trocadas = self._painel.aplicar_substituicao(self._achadas, self.campo_novo.text())
        self._painel.estado.emit(f"{trocadas} ocorrência(s) substituída(s).")
        self.procurar()
