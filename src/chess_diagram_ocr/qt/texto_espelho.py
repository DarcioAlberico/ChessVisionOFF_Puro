"""O espelho da folha: o documento desenhado no editor, e a tela de volta no documento (S-865).

**Saiu de `qt/painel_de_texto.py` com o estado que só ele usa** -- o mapa entre as duas
coordenadas, o texto da tela na última mudança, a fonte de base do desenho e a pilha de documentos
do desfazer. Quem pede um desenho, uma seleção ou um passo de desfazer pede aqui; o documento
continua sendo do painel (`PainelDeTexto.documento`), que é o estado de todas as partes.

**O deslocamento é a fronteira estreita.** As funções puras falam em deslocamento de caractere do
*documento*; o `QTextEdit` fala em posição do *cursor*. Os dois divergem porque a miniatura do
diagrama vale um caractere para o Qt e nenhum para o documento -- exatamente o que
`ui/texto_etiquetas.deslocamento` resolvia do outro lado, percorrendo o `dump` do widget a cada
pergunta. Ver `Mapa`.

**A digitação atravessa a mesma fronteira, no outro sentido.** O editor é editável, e o que se
digita nele acontece primeiro no widget. O porte deixou só essa metade: a letra ficava na tela e
fora do documento, e o primeiro redesenho -- o negrito seguinte, o `Ctrl+Z`, o zoom -- a apagava
sem dizer nada; gravar e exportar levavam a folha de antes. Agora cada mudança do texto chega por
`QTextDocument.contentsChange` e vira uma função pura de `rico` (`editar`, `mover`), pela mesma
tradução de `Mapa`. Quem decide o que a tecla faz com a corrida -- de quem herda, que faixa leva, o
que acontece com a marca do diagrama -- é `rico`; quando a tecla fecha um passo de desfazer é
`ui/texto_declarado`. Aqui fica o vaivém -- e **sem redesenho por tecla**: o widget já tem a letra,
o mapa anda junto com ela e só o trecho digitado é repintado. Redesenhar a folha inteira, com as
miniaturas, é o que o portão de bloqueio da thread da janela não deixaria passar a cada tecla.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QTextBlockFormat, QTextCursor, QTextDocument

from chess_diagram_ocr.qt.texto_formato import bloco_de, formato_de
from chess_diagram_ocr.text import rico
from chess_diagram_ocr.ui.texto_declarado import (
    ESCAPE_DA_PALETA,
    Digitacao,
    alinhamento_dos_diagramas,
    continua_a_digitacao,
    digitacao_depois,
)

if TYPE_CHECKING:
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto

logger = logging.getLogger(__name__)

__all__ = ["OBJETO", "EspelhoDaFolha", "Mapa"]

OBJETO = "￼"
"""Como o texto do widget conta a miniatura: um caractere que **nunca** entra no documento.

Chega também colado: o texto que o `QTextEdit` põe na área de transferência traz a miniatura
copiada como este caractere solto, sem imagem nenhuma atrás dele."""


@dataclass(frozen=True)
class _Trecho:
    """Onde uma corrida caiu no widget: começo no documento, começo no Qt, tamanho."""

    documento: int
    janela: int
    tamanho: int


class Mapa:
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


class EspelhoDaFolha(QObject):
    """O documento na tela, a tela de volta no documento, e a pilha de documentos do desfazer."""

    def __init__(self, aba: PainelDeTexto) -> None:
        super().__init__(aba)
        self._aba = aba
        self._historico: list[rico.DocumentoRico] = []
        self._rotulos_do_historico: list[str] = []
        """O nome do passo de cada documento empilhado (S-656), na mesma ordem de `_historico`."""
        self._rotulos_refeitos: list[str] = []
        self.rotulo_corrente = ""
        """O nome do comando em curso: `PainelDeTexto.executar` o põe, e `aplicar` o leva para a pilha."""
        self._edicao = 0
        """Quantas edições esta aba recebeu. É o desempate do `Ctrl+Z` sem foco (S-243)."""
        self._refeitos: list[rico.DocumentoRico] = []
        self.mapa = Mapa()
        self.redesenhando = False
        self._tela = ""
        """O texto do widget na última mudança vista -- o `antes` de cada tecla. `contentsChange`
        diz onde mudou; é comparando com isto que se sabe **o que** saiu, e se o Qt disse a
        verdade sobre onde."""
        self.digitacao: Digitacao | None = None
        """O passo de desfazer que a digitação deixou aberto. Toda ferramenta o fecha."""
        self._sincronizando = False
        """O painel está repintando o que acabou de ser digitado: a mudança de formato que isso
        gera não é digitação."""
        self.base: tuple[int, str, str] | None = None
        """A fonte de base do último desenho. O trecho digitado é pintado com **a mesma** -- a
        tecla não relê as famílias do sistema, e o redesenho seguinte não muda o que já estava."""

    def zerar_pilha(self) -> None:
        """Folha nova na tela: a pilha do desfazer, a dos refeitos e o passo da digitação recomeçam."""
        self._historico.clear()
        self._refeitos.clear()
        self._rotulos_do_historico.clear()
        self._rotulos_refeitos.clear()
        self.digitacao = None

    def rotulos_do_desfazer(self) -> list[str]:
        """Os nomes dos passos que o desfazer tira, do mais recente ao mais antigo (S-656): a lista da fita."""
        return list(reversed(self._rotulos_do_historico))

    # ----------------------------------------------------------------------------------- desenho

    def desenhar(self, *, selecao: tuple[int, int] | None = None) -> None:
        """Refaz o `QTextDocument` inteiro a partir das corridas -- e devolve o cursor a `selecao`.

        **Devolver o cursor é o que torna o redesenho compatível com a digitação.** O documento
        novo nasce com o cursor no começo e a rolagem no topo; com o texto digitado agora sendo
        documento, um `Ctrl+Z` ou um negrito no meio da folha que jogasse o cursor para o título
        faria a tecla seguinte escrever lá -- e ela passaria a ficar.
        """
        barra = self._aba.editor.verticalScrollBar()
        rolagem = barra.value() if selecao is not None and barra is not None else None
        self.redesenhando = True
        try:
            self.mapa.limpar()
            documento = QTextDocument(self._aba.editor)
            documento.setDefaultFont(self._aba.editor.font())
            # **No documento, e não no editor.** `QTextEdit.setUndoRedoEnabled` vale para o
            # documento em vigor, e `desenhar` troca o documento -- ajustar só o editor no
            # `_montar` fazia o desfazer nativo voltar a ligar no primeiro redesenho, e aí
            # `Ctrl+Z` teria duas pilhas disputando. Foi um teste que pegou.
            documento.setUndoRedoEnabled(False)
            cursor = QTextCursor(documento)
            base = self._aba.vista.base_da_vista()
            self.base = base
            deslocamento = 0

            for corrida in self._aba.documento.corridas:
                if corrida.e_diagrama:
                    self._aba.miniaturas.inserir_miniatura(cursor, corrida)
                inicio = cursor.position()
                cursor.insertText(corrida.texto, formato_de(corrida, base=base))
                self.mapa.registrar_texto(deslocamento, inicio, corrida.texto)
                deslocamento += len(corrida.texto)
            # **O formato de parágrafo é escrito depois do texto, bloco a bloco** (S-601). Escrito
            # no laço, antes de cada corrida, ele caía no bloco em que o cursor estava -- e a corrida
            # separadora (`"\n\n"`, sem atributos) chegava com o cursor ainda no parágrafo anterior:
            # o formato vazio dela apagava o centro e o título que ele acabara de receber.
            self.formatar_blocos(documento)

            # O `setDocument` só apaga o documento que é filho do controle interno do editor -- o da
            # montagem, e na hora --, e os deste painel são filhos do editor: sem soltá-los, cada
            # redesenho deixava a folha anterior inteira, com as miniaturas, pendurada até a janela
            # fechar. Quem é de quem se pergunta **antes** da troca, porque depois dela o da
            # montagem já não existe; e `deleteLater`, e não já, porque o redesenho pode estar
            # acontecendo de dentro de um sinal do documento que sai (`_trocado`).
            anterior = self._aba.editor.document()
            nosso = anterior if anterior is not None and anterior.parent() is self._aba.editor else None
            self._aba.editor.setDocument(documento)
            if nosso is not None:
                nosso.deleteLater()
            # Ligado **depois** de montar: o que o laço acima escreveu é desenho, e não digitação.
            documento.contentsChange.connect(self.digitado)
            self._aba.vista.aplicar_marcas()
            self._tela = _texto_da_tela(documento)
        finally:
            self.redesenhando = False
        if selecao is not None:
            self._devolver_selecao(selecao, rolagem)
        # A marcação do léxico não é do documento e morre com o `QTextDocument` que saiu: com a
        # conferência ligada, ela se refaz sobre a folha nova (S-293).
        if self._aba.correcao.conferindo_lexico:
            self._aba.correcao.conferir_lexico(avisar=False)

    def formatar_blocos(self, documento: QTextDocument, inicio: int = 0, fim: int | None = None) -> None:
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
                corrida = _corrida_em(self._aba.documento, self.mapa.deslocamento(seguinte.position())) if seguinte.isValid() else None
            elif texto:
                corrida = _corrida_em(self._aba.documento, self.mapa.deslocamento(bloco.position()))
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
            return bloco_de(rico.PADRAO, base=self.base)
        efetivo = rico.alinhamento_efetivo(corrida, padrao_do_diagrama=alinhamento_dos_diagramas(self._aba.miniaturas.diagramas))
        return bloco_de(replace(corrida.atributos, alinhamento=efetivo), base=self.base)

    def selecao_atual(self) -> tuple[int, int]:
        """`(âncora, ponta)` do cursor, em deslocamento do documento."""
        cursor = self._aba.editor.textCursor()
        return (self.mapa.deslocamento(cursor.anchor()), self.mapa.deslocamento(cursor.position()))

    def _devolver_selecao(self, selecao: tuple[int, int], rolagem: int | None) -> None:
        """Põe o cursor em `selecao` e a rolagem onde estava; o cursor fora da tela a traz até ele."""
        ancora, ponta = selecao
        cursor = self._aba.editor.textCursor()
        cursor.setPosition(self.mapa.posicao(ancora))
        cursor.setPosition(self.mapa.posicao(ponta), QTextCursor.MoveMode.KeepAnchor)
        self._aba.editor.setTextCursor(cursor)
        barra = self._aba.editor.verticalScrollBar()
        if rolagem is not None and barra is not None:
            barra.setValue(rolagem)
        self._aba.editor.ensureCursorVisible()

    # ------------------------------------------------------------------------ a seleção e a pilha

    def intervalo(self) -> tuple[int, int]:
        """O intervalo selecionado, **em deslocamento de documento**.

        Sem seleção os dois são iguais, e as funções de `rico` tratam isso como "a palavra sob o
        cursor" -- é `rico.intervalo_alvo`, e a decisão é de lá.
        """
        cursor = self._aba.editor.textCursor()
        return (
            self.mapa.deslocamento(cursor.selectionStart()),
            self.mapa.deslocamento(cursor.selectionEnd()),
        )

    def aplicar(self, novo: rico.DocumentoRico, *, selecao: tuple[int, int] | None = None) -> None:
        """Guarda o documento anterior na pilha e desenha o novo.

        A pilha é de **documentos**, e é o que faz `Ctrl+Z` desfazer um negrito -- que não muda
        caractere nenhum e que uma pilha de texto não veria.

        **Toda ferramenta fecha o passo da digitação**: `Ctrl+Z` depois de "digitar, negritar,
        digitar" desfaz a segunda digitação, e não as duas com o negrito no meio. A seleção fica
        onde estava (ou em `selecao`), para o segundo pincel cair no mesmo trecho que o primeiro.
        """
        self.digitacao = None
        if novo is self._aba.documento:
            return
        selecao = self.selecao_atual() if selecao is None else selecao
        self._historico.append(self._aba.documento)
        self._rotulos_do_historico.append(self.rotulo_corrente or "Edição")
        self._rotulos_refeitos.clear()
        # O contador que decide o `Ctrl+Z` quando o foco não está em desfazível nenhum (S-243).
        self._edicao += 1
        self._refeitos.clear()
        self._aba.desenhar_documento(novo, selecao=selecao)

    # --------------------------------------------------------------------------------- histórico

    @property
    def edicao(self) -> int:
        """Contador que só cresce, como manda `ui/desfazivel.Desfazivel`. Zero = nunca editado."""
        return self._edicao

    def desfazer(self) -> None:
        """`Ctrl+Z`: devolve o documento anterior -- a palavra digitada inteira é **um** passo."""
        self._andar(
            de=(self._historico, self._rotulos_do_historico),
            para=(self._refeitos, self._rotulos_refeitos),
            vazio="Não há mudança anterior nesta folha para desfazer.",
        )

    def desfazer_ate(self, passos: int) -> None:
        """Desfaz `passos` de uma vez, pela lista da barra de acesso rápido (S-656). Um redesenho só."""
        passos = min(int(passos), len(self._historico))
        if passos <= 0:
            return
        self.digitacao = None
        alvo = self._aba.documento
        for _ in range(passos):
            self._refeitos.append(alvo)
            self._rotulos_refeitos.append(self._rotulos_do_historico.pop() if self._rotulos_do_historico else "Edição")
            alvo = self._historico.pop()
        self._voltar_a(alvo)
        self._aba.estado.emit(f"{passos} passo(s) desfeito(s).")

    def refazer(self) -> None:
        """`Ctrl+Y`: repõe o que o desfazer tirou."""
        self._andar(
            de=(self._refeitos, self._rotulos_refeitos),
            para=(self._historico, self._rotulos_do_historico),
            vazio="Não há o que refazer: nada foi desfeito.",
        )

    def _andar(
        self,
        *,
        de: tuple[list[rico.DocumentoRico], list[str]],
        para: tuple[list[rico.DocumentoRico], list[str]],
        vazio: str,
    ) -> None:
        """Um passo de uma pilha para a outra: o desfazer e o refazer são o mesmo movimento."""
        documentos, rotulos = de
        if not documentos:
            self._aba.estado.emit(vazio)
            return
        self.digitacao = None
        para[0].append(self._aba.documento)
        para[1].append(rotulos.pop() if rotulos else "Edição")
        self._voltar_a(documentos.pop())

    def _voltar_a(self, doc: rico.DocumentoRico) -> None:
        """Desenha `doc` com o cursor **onde o texto mudou** -- o fim do trecho que voltou ou saiu.

        É onde qualquer editor põe o cursor depois de desfazer, e é onde a pessoa vai continuar
        escrevendo. Se o texto não mudou (desfazer um negrito), a seleção fica onde estava.
        """
        troca = _janela_da_troca(self._aba.documento.para_texto(), doc.para_texto())
        if troca is None:
            self._aba.desenhar_documento(doc, selecao=self.selecao_atual())
            return
        alvo = troca[0] + troca[2]
        self._aba.desenhar_documento(doc, selecao=(alvo, alvo))

    @property
    def pode_desfazer(self) -> bool:
        return bool(self._historico)

    @property
    def pode_refazer(self) -> bool:
        return bool(self._refeitos)

    # ---------------------------------------------------------------- o cursor levado a um trecho

    def mostrar_intervalo(self, inicio: int, fim: int) -> None:
        """Rola até aquele trecho e o seleciona. É o que a lista da busca chama ao clicar."""
        cursor = self._aba.editor.textCursor()
        cursor.setPosition(self.mapa.posicao(inicio))
        cursor.setPosition(self.mapa.posicao(fim), QTextCursor.MoveMode.KeepAnchor)
        self._aba.editor.setTextCursor(cursor)
        self._aba.editor.ensureCursorVisible()
        self._aba.editor.setFocus()

    def por_o_cursor(self, deslocamento: int) -> None:
        cursor = self._aba.editor.textCursor()
        cursor.setPosition(self.mapa.posicao(deslocamento))
        self._aba.editor.setTextCursor(cursor)
        self._aba.editor.ensureCursorVisible()
        self._aba.editor.setFocus()

    # ------------------------------------------------------------------------------- a digitação

    def digitado(self, posicao: int, removidos: int, acrescidos: int) -> None:
        """Uma mudança do texto na tela -- tecla, colar, recortar, arrastar -- vira mudança do documento.

        `contentsChange` diz **onde** mudou; o que saiu vem de `_tela`, o texto como estava. Os
        números do Qt são conferidos contra os dois textos antes de serem usados, e a conta é
        refeita dos dois quando não batem: uma troca de formato chega pelo mesmo sinal sem mudar
        letra nenhuma, e um arrasto dentro da folha chega como **uma** janela que cobre a origem e
        o destino.
        """
        documento = self._aba.editor.document()
        if self.redesenhando or self._sincronizando or documento is None:
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
        de = self.mapa.deslocamento(inicio)
        ate = self.mapa.deslocamento(inicio + removido)
        escrito = _do_qt(novo).replace(OBJETO, "")
        alcance = rico.alcance_da_edicao(self._aba.documento, de, ate, escrito)
        if alcance is None:
            self._aba.estado.emit(
                "A marca do diagrama não se edita por dentro: escreva antes ou depois dela, "
                "ou apague-a inteira."
            )
            self.desenhar(selecao=(de, de))
            return
        editado = rico.editar(self._aba.documento, de, ate, escrito)
        mudou = editado is not self._aba.documento
        if mudou:
            agora = self._aba._relogio()
            passo = not continua_a_digitacao(self.digitacao, alcance[0], alcance[1], escrito, agora=agora)
            self._guardar_digitado(editado, passo=passo)
            self.digitacao = digitacao_depois(alcance[0], alcance[1], escrito, agora=agora)
        if removido == ate - de and escrito == novo and alcance == (de, ate):
            self.mapa.trocar(inicio, removido, de, len(escrito))
            self._pintar_o_digitado(inicio, len(escrito), de)
            if removido == 0 and len(escrito) == 1:
                self._fechar_sequencia(de + 1)
            return
        if alcance != (de, ate):
            self._aba.estado.emit("O diagrama saiu da folha junto com a marca inteira; desfazer o devolve.")
        elif not mudou and removido > ate - de:
            # Só o desenho saiu -- a miniatura, a quebra embaixo dela --, e ele volta no redesenho.
            self._aba.estado.emit(
                "A miniatura é desenho, e não texto: para tirar o diagrama da folha, apague a marca dele."
            )
        cursor = alcance[0] + len(escrito)
        self.desenhar(selecao=(cursor, cursor))

    def _fechar_sequencia(self, posicao: int) -> None:
        r"""Troca `\N` por `♘` **quando a sequência fecha** (S-248), e só digitando: colar não é tecla.

        Três regras, e as três são critério de aceite: a barra sozinha continua sendo barra; uma
        barra seguida de tecla que não abre sequência devolve os dois caracteres; e nada é trocado sem
        a barra -- `Nf3` continua `Nf3`, porque a troca silenciosa sobre texto de OCR é o que a S-209
        proíbe ao léxico. Um passo próprio de desfazer: `Ctrl+Z` devolve o `\N` que foi digitado.
        """
        from chess_diagram_ocr.text import paleta as _paleta

        sequencias = _paleta.SEQUENCIAS_DECLARADAS
        maior = max(len(s) for s in sequencias) + len(ESCAPE_DA_PALETA)
        trecho = self._aba.documento.para_texto()[max(0, posicao - maior) : posicao]
        corte = trecho.rfind(ESCAPE_DA_PALETA)
        if corte < 0:
            return
        chave = trecho[corte + len(ESCAPE_DA_PALETA) :]
        simbolo = sequencias.get(chave)
        if simbolo is None:
            return
        comeco = posicao - len(chave) - len(ESCAPE_DA_PALETA)
        fim = comeco + len(simbolo)
        self.aplicar(rico.editar(self._aba.documento, comeco, posicao, simbolo), selecao=(fim, fim))

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
            self._aba.documento, self.mapa.deslocamento(origem[0]), self.mapa.deslocamento(origem[1])
        )
        para = self.mapa.deslocamento(destino)
        movido = rico.mover(self._aba.documento, de, ate, para)
        self.digitacao = None
        if movido is self._aba.documento:
            self._aba.estado.emit("O trecho não pode ser solto ali: a marca do diagrama não se parte.")
            self.desenhar(selecao=(de, ate))
            return
        self._guardar_digitado(movido, passo=True)
        fim = para if para >= ate else para + (ate - de)
        self.desenhar(selecao=(fim - (ate - de), fim))

    def _guardar_digitado(self, novo: rico.DocumentoRico, *, passo: bool) -> None:
        """Põe `novo` no lugar do documento; `passo` empilha o anterior -- a tecla abriu um passo novo."""
        if passo:
            self._historico.append(self._aba.documento)
            self._rotulos_do_historico.append("Digitação")
            self._refeitos.clear()
            self._rotulos_refeitos.clear()
        # Cresce a cada tecla, e não a cada passo: a pergunta de `ui/desfazivel` é "quem foi editado
        # por último", e a última tecla é a resposta mesmo dentro de um passo aberto (S-243).
        self._edicao += 1
        self._aba.documento = novo
        self._aba.documento_mudou.emit()

    def _pintar_o_digitado(self, inicio: int, tamanho: int, deslocamento: int) -> None:
        """Repinta só o trecho digitado, com o formato da corrida em que o documento o pôs.

        O Qt escreve a letra com o formato da vizinha **da tela**, e o documento escolheu outro
        quando as regras divergem: a faixa da mão no lugar do `revisar` herdado, o negrito da
        seleção que foi trocada. Sem isto a tela mostraria uma coisa e o arquivo gravaria outra até o
        próximo redesenho.
        """
        corrida = _corrida_em(self._aba.documento, deslocamento)
        documento = self._aba.editor.document()
        if tamanho <= 0 or corrida is None or documento is None:
            return
        cursor = QTextCursor(documento)
        cursor.setPosition(inicio)
        cursor.setPosition(inicio + tamanho, QTextCursor.MoveMode.KeepAnchor)
        self._sincronizando = True
        try:
            cursor.setCharFormat(formato_de(corrida, base=self.base))
            # O `Enter` cria um bloco que herda o formato do de cima; os blocos que a tecla tocou
            # recebem o que o documento pede, pela mesma regra do desenho inteiro (S-601).
            if "\n" in self._tela[inicio : inicio + tamanho]:
                self.formatar_blocos(documento, max(0, inicio - 1), inicio + tamanho + 1)
        finally:
            self._sincronizando = False
