"""O estudo de uma posição do livro, como dado (S-268/S-269/S-270).

**O que não existia.** A aba de estudo era um `ttk.Frame` com três atributos -- `board`, `game` e
`current_node` -- e todas as decisões sobre eles dentro do widget: qual variante entrar, o que a
lista mostra, o que "ir para o fim" significa. Nada disso era afirmável sem abrir janela, e por isso
quase nada disso tinha teste.

E três coisas não existiam nem lá dentro:

- **o endereço do estudo no livro.** O painel recebia `current_fen: Callable[[], str]` e mais nada.
  Não sabia o livro, a página nem o diagrama -- então o PGN salvo saía sem procedência, enquanto
  `pdf_to_pgn.py` já escreve `SourcePDF`, `Page` e `Diagram` para o mesmo diagrama.
- **um identificador de nó.** Para a lista clicável da S-274 é preciso ir de um clique a um nó, e
  `GameNode` não sobrevive a recarregar o PGN.
- **a separação entre o comentário e os comandos dele.** `python-chess` grava seta e avaliação
  *dentro* do comentário (`[%cal Gf3g5]`, `[%eval 0.35,18]`), lê os dois de volta e **não os tira**
  de `node.comment`. Mostrar isso numa caixa de comentário seria mostrar o encanamento.

## Três decisões que decidem o resto

**O formato é PGN, e é o PGN de todo mundo.** Seta e casa marcada em `[%cal]`/`[%csl]`, avaliação em
`[%eval]`, símbolo em NAG, procedência em header -- com os mesmos nomes que `pdf_to_pgn.py:698-732`
já usa. O arquivo que sai daqui abre no ChessBase e no Scid, que é onde o dono deste projeto estuda.
Um contêiner nosso não teria uma vantagem sequer sobre isso.

**A árvore é a do `chess.pgn`, e ela é recursiva.** O plugin que serviu de referência
(`Ideias para o board da aba de análise/`) tem variante de profundidade 1, e o próprio README dele
anuncia isso como recurso. Para um livro de xadrez é fatal: a nota típica é
`12...Nf6 13.Bg5 (13.Be3!? h6 14.Bh4 g5) Qb6`, com variante dentro de variante.

**O caminho é derivado, nunca guardado.** Um `Caminho` é a tupla de índices de variação da raiz até o
nó -- `(0, 3, 1)` --, e ela é serializável, imprimível e não gasta um byte de arquivo. Mas **promover
ou apagar uma variante muda os índices**, e um caminho guardado antes da operação aponta para outro
lance depois dela. É a mesma forma de defeito que a S-262 registrou no editor: *a pilha do Tk guarda
índice, não conteúdo*. Por isso a regra: quem opera sobre a árvore trabalha com **o nó** e recalcula
o caminho no fim.

Nada de `tkinter` aqui. `Sala` responde "o que eu já estudei neste livro?" em duas linhas de teste.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import chess
import chess.pgn
import chess.svg

logger = logging.getLogger(__name__)

__all__ = [
    "ANOTADOR",
    "CORES_DE_SETA",
    "NAGS_DE_LANCE",
    "NAGS_DE_POSICAO",
    "NOME_DE_NAG",
    "SIMBOLO_DE_NAG",
    "Ancora",
    "Caminho",
    "Estudo",
    "PosicaoDeEstudo",
    "Sala",
    "alternar_nag",
    "caminho_de",
    "colar",
    "com_texto",
    "comandos_do_comentario",
    "no_em",
    "roque_provavel",
    "setas_de",
    "simbolo_de_nag",
    "texto_do_comentario",
    "trocar_seta",
]

ANOTADOR = "ChessVisionOFF"
"""O que vai no header `Annotator`. É o mesmo de `pdf_to_pgn.py:706`, e não é enfeite: ele é o que
distingue, num PGN aberto no ChessBase, o que saiu daqui do que veio de outro lugar."""

LOCAL = "Local"
"""O que vai no header `Site` de um estudo que saiu de um diagrama, e não de um torneio.

Era literal em `de_posicao`, e ganhou nome na S-530 por ter passado a ter **dois** leitores: o
cabeçalho da sala precisa distinguir "o livro não disse onde foi" de um local de verdade, e a
única maneira honesta de fazer isso é comparar com o que o próprio programa escreve. Ver
`ui/cabecalho_da_partida.DE_FABRICA`."""

EVENTO = "ChessVisionOFF Estudo"

Caminho = tuple[int, ...]
"""O endereço de um nó na árvore: `()` é a raiz, `(0,)` o primeiro lance, `(0, 3, 1)` o segundo
lance da quarta variante do primeiro lance. **Derivado, nunca guardado** -- ver o cabeçalho."""

_COMANDO = re.compile(r"\[%(\w+)\s*([^\]]*)\]")
"""Um comando de anotação dentro de um comentário PGN: `[%cal Gf3g5]`, `[%eval 0.35,18]`.

É a convenção do PGN "command annotation" que Lichess, ChessBase e Scid usam, e é onde
`chess.pgn.GameNode.set_arrows` e `set_eval` gravam."""

_ESPACOS = re.compile(r"\s+")


# ---------------------------------------------------------------------------- comentário


def texto_do_comentario(comentario: str) -> str:
    """O que a pessoa escreveu, sem os comandos que a máquina pôs junto.

    Medido com `python-chess` 1.11.2: depois de `set_arrows` e `set_eval`, `node.comment` vale
    `'[%csl Rd4][%cal Gf3g5] roque curto [%eval 0.35,18]'`. A biblioteca lê os comandos de volta
    (`arrows()`, `eval()`) e não os remove do texto -- então quem mostrar `comment` numa caixa de
    comentário mostra o encanamento.
    """
    return _ESPACOS.sub(" ", _COMANDO.sub(" ", str(comentario or ""))).strip()


def comandos_do_comentario(comentario: str) -> tuple[str, ...]:
    """Os comandos do comentário, **na ordem em que estão**, cada um com os colchetes.

    A ordem importa porque ela é preservada em `com_texto`: reescrever a frase de um lance não pode
    reordenar as setas dele nem perder um comando que esta versão da biblioteca não conheça.
    """
    return tuple(m.group(0) for m in _COMANDO.finditer(str(comentario or "")))


def com_texto(comentario: str, texto: str) -> str:
    """O mesmo comentário com outra frase, e **com os comandos intactos**.

    É a única porta de escrita de comentário, e ela existe por causa de um defeito de uma linha:
    `node.comment = novo_texto` apaga as setas e a avaliação daquele lance, em silêncio.
    """
    comandos = "".join(comandos_do_comentario(comentario))
    limpo = _ESPACOS.sub(" ", str(texto or "")).strip()
    if not comandos:
        return limpo
    return f"{comandos} {limpo}".strip()


# ---------------------------------------------------------------------------- NAG (S-278)

SIMBOLO_DE_NAG: dict[int, str] = {
    1: "!",
    2: "?",
    3: "!!",
    4: "??",
    5: "!?",
    6: "?!",
    10: "=",
    13: "∞",
    14: "⩲",
    15: "⩱",
    16: "±",
    17: "∓",
    18: "+-",
    19: "-+",
}
"""Os símbolos que o acervo usa, e **só eles** (S-278).

O PGN define mais de 130 NAGs; um livro de xadrez usa estes catorze. E eles não são invenção nossa:
são exatamente o que `text/notacao._SUFIXO` já reconhece no sufixo de um lance impresso
(`[+#!?±∓⩲⩱=]*`), o que é a evidência de que são estes os que aparecem nas páginas deste acervo.

NAG fora da tabela -- lido de um PGN de fora -- não some e não quebra: aparece como `$NN`, que é o
que o PGN escreveria de qualquer forma."""

NOME_DE_NAG: dict[int, str] = {
    1: "bom lance",
    2: "lance fraco",
    3: "lance excelente",
    4: "erro grave",
    5: "lance interessante",
    6: "lance duvidoso",
    10: "posição equilibrada",
    13: "posição obscura",
    14: "ligeira vantagem das brancas",
    15: "ligeira vantagem das pretas",
    16: "vantagem clara das brancas",
    17: "vantagem clara das pretas",
    18: "vantagem decisiva das brancas",
    19: "vantagem decisiva das pretas",
}

NAGS_DE_LANCE: tuple[int, ...] = (1, 2, 3, 4, 5, 6)
"""Julgam **o lance**, e são exclusivos entre si: nenhum lance é `!` e `?` ao mesmo tempo."""

NAGS_DE_POSICAO: tuple[int, ...] = (10, 13, 14, 15, 16, 17, 18, 19)
"""Julgam **a posição** que o lance produziu, e também são exclusivos entre si.

Os dois grupos convivem, e é assim que o livro escreve: `13.♗g5!? ⩲` é um lance interessante que
deixa as brancas ligeiramente melhor. Por isso são dois conjuntos e não um."""


def simbolo_de_nag(nag: int) -> str:
    """`1` → `!`. NAG desconhecido volta como `$NN`, que é o que o PGN diria dele."""
    return SIMBOLO_DE_NAG.get(int(nag), f"${int(nag)}")


def alternar_nag(nags: set[int], nag: int) -> set[int]:
    """Liga, desliga ou **troca** um símbolo, conforme o grupo dele.

    Clicar em `!` num lance que já é `!` tira o símbolo -- é o mesmo gesto de largar o pincel da
    S-65. Clicar em `?` num lance `!` **troca**, porque um lance não é bom e ruim ao mesmo tempo.
    E clicar em `±` num lance `!` **soma**, porque julgar o lance e julgar a posição são duas
    frases diferentes.
    """
    codigo = int(nag)
    novo = {int(n) for n in nags}
    if codigo in novo:
        novo.discard(codigo)
        return novo
    for grupo in (NAGS_DE_LANCE, NAGS_DE_POSICAO):
        if codigo in grupo:
            novo -= set(grupo)
    novo.add(codigo)
    return novo


# ---------------------------------------------------------------------------- setas (S-279)

CORES_DE_SETA: tuple[str, ...] = ("green", "red", "blue", "yellow")
"""As quatro do padrão `[%cal]`/`[%csl]`, na ordem dos modificadores.

Não são escolha de gosto: `chess.svg.Arrow.pgn` só sabe escrever estas quatro (`G`, `R`, `B`, `Y`) e
qualquer outra vira verde na gravação. Uma quinta cor seria uma cor que não sobrevive ao arquivo."""


def setas_de(no: chess.pgn.GameNode) -> list[chess.svg.Arrow]:
    """As setas e casas marcadas daquele lance. Lista vazia quando não há.

    Envolve `node.arrows()` porque ele levanta em comentário com `[%cal]` malformado -- e um
    comentário estragado de um PGN de fora não pode impedir o estudo de abrir.
    """
    try:
        return list(no.arrows())
    except Exception as erro:  # noqa: BLE001 - PGN de fora pode trazer [%cal] malformado
        logger.debug("Setas ilegíveis num lance: %s", erro)
        return []


def trocar_seta(
    no: chess.pgn.GameNode, origem: int, destino: int, cor: str = "green"
) -> list[chess.svg.Arrow]:
    """Põe a seta se ela não estava; **tira** se estava, mesmo de outra cor.

    O mesmo gesto que desenha apaga -- é o que o Lichess, o Chess.com e o ChessBase fazem, e é o
    que faz o botão direito ser suficiente sozinho. `origem == destino` é casa marcada (`[%csl]`),
    e a regra vale igual.
    """
    atuais = setas_de(no)
    sobra = [seta for seta in atuais if not (seta.tail == origem and seta.head == destino)]
    if len(sobra) == len(atuais):
        sobra.append(chess.svg.Arrow(origem, destino, color=cor if cor in CORES_DE_SETA else "green"))
    no.set_arrows(sobra)
    return sobra


# ---------------------------------------------------------------------------- caminho


def caminho_de(no: chess.pgn.GameNode | None) -> Caminho:
    """O endereço daquele nó, calculado agora. `()` para a raiz e para `None`."""
    partes: list[int] = []
    atual = no
    while atual is not None and atual.parent is not None:
        pai = atual.parent
        # Por identidade, e não por `index`: um nó já removido da árvore não está entre as irmãs, e
        # a resposta certa ali é a raiz -- não uma exceção no meio de um redesenho.
        for indice, irma in enumerate(pai.variations):
            if irma is atual:
                partes.append(indice)
                break
        else:  # pragma: no cover - nó removido entre o clique e o redesenho
            return ()
        atual = pai
    return tuple(reversed(partes))


def no_em(jogo: chess.pgn.GameNode, caminho: Caminho) -> chess.pgn.GameNode | None:
    """O nó daquele endereço, ou `None` se ele não existe mais.

    `None` é resposta legítima e frequente: um caminho guardado antes de apagar uma variante aponta
    para o vazio, e a resposta certa ali é voltar para a raiz -- não levantar.
    """
    atual: chess.pgn.GameNode = jogo
    for indice in caminho:
        if not 0 <= indice < len(atual.variations):
            return None
        atual = atual.variations[indice]
    return atual


# ---------------------------------------------------------------------------- âncora


@dataclass(frozen=True)
class Ancora:
    """O endereço do estudo no livro: que PDF, que página, que diagrama.

    **`pagina` e `diagrama` são 0-based**, como `page_index` e o índice do diagrama correm pelo
    programa inteiro. Os headers `Page` e `Diagram` do PGN são **1-based**, porque é assim que
    `pdf_to_pgn.py:710-711` já os escreve e é assim que a pessoa lê a página. As duas convenções
    existem, colidem, e a conversão fica num lugar só: aqui.
    """

    documento: str = ""
    pagina: int = -1
    diagrama: int = -1
    titulo: str = ""
    """A legenda, quando o livro deu uma. Vai para o header `Caption`, como na S-72."""

    @property
    def valida(self) -> bool:
        """Um estudo sem âncora válida não pertence a livro nenhum: é avulso, e não entra na `Sala`."""
        return bool(self.documento) and self.pagina >= 0 and self.diagrama >= 0

    @property
    def nome_do_livro(self) -> str:
        return Path(self.documento).name if self.documento else ""

    def chave(self) -> str:
        """A chave estável deste diagrama, para achar o estudo de volta.

        Pelo caminho **resolvido**, como `ui/state._history_key` e `text/rascunho.chave_de`: dois
        livros de mesmo nome em pastas diferentes são dois livros.
        """
        bruto = str(self.documento or "sem-documento")
        try:
            bruto = str(Path(bruto).resolve())
        except OSError:  # pragma: no cover - caminho de rede fora do ar
            pass
        impressao = hashlib.sha1(bruto.encode("utf-8")).hexdigest()[:10]
        return f"{impressao}_p{self.pagina + 1}_d{self.diagrama + 1}"

    def rotulo(self) -> str:
        """Como o estudo se apresenta na tela: `Secrets.pdf · p. 143 · diagrama 2`."""
        if not self.valida:
            return "posição avulsa"
        return f"{self.nome_do_livro} · p. {self.pagina + 1} · diagrama {self.diagrama + 1}"


# ---------------------------------------------------------------------------- posição


def roque_provavel(placement: str) -> str:
    """O campo de roque que a posição impressa permite: `KQkq`, `Kq`, `-`.

    **Concede, e não nega.** As duas escolhas erram, e não erram igual: negar torna *ilegal um lance
    legal*, e quem estuda não tem como descobrir por quê -- a peça simplesmente não anda, e nada
    explica. Conceder torna *legal um lance que talvez não fosse*, e isso a pessoa vê, porque ela
    está olhando a página. É a mesma assimetria de custo que a S-208 usou para decidir o que `fatiar`
    declara lance.

    Só concede o roque cujo **rei e torre** estão na casa de origem. Um livro não imprime direito de
    roque, e esta é a única evidência que a imagem dá.
    """
    try:
        board = chess.Board(f"{str(placement).split()[0]} w - - 0 1")
    except (ValueError, IndexError, AttributeError):
        return "-"

    direitos = ""
    if board.piece_at(chess.E1) == chess.Piece(chess.KING, chess.WHITE):
        if board.piece_at(chess.H1) == chess.Piece(chess.ROOK, chess.WHITE):
            direitos += "K"
        if board.piece_at(chess.A1) == chess.Piece(chess.ROOK, chess.WHITE):
            direitos += "Q"
    if board.piece_at(chess.E8) == chess.Piece(chess.KING, chess.BLACK):
        if board.piece_at(chess.H8) == chess.Piece(chess.ROOK, chess.BLACK):
            direitos += "k"
        if board.piece_at(chess.A8) == chess.Piece(chess.ROOK, chess.BLACK):
            direitos += "q"
    return direitos or "-"


@dataclass(frozen=True)
class PosicaoDeEstudo:
    """De onde um estudo nasce: a posição do diagrama, **inteira** (S-269).

    O painel recebia `result_panel.fen_var`, que não é uma FEN: é o campo de peças que
    `fen_from_class_indices` devolve. O lado a jogar mora em `editor_model.side_edits` e não era
    passado; `board_from_fen` completava com `w - - 0 1`. Resultado medido: **todo estudo abria com
    as brancas a jogar e sem direito a roque**, mesmo quando a S-17 leu "pretas jogam" na legenda e
    o rei e as torres estavam em casa.
    """

    placement: str = chess.STARTING_BOARD_FEN
    vez: str = "w"
    """`'w'` ou `'b'`, como `side_edits` o escreve. É o que a Fase 3 inteira existe para responder."""

    lance: int | None = None
    """O número impresso na página, quando a Galeria o anotou (S-67). Sem ele a lista numeraria a
    partir de 1, e os números não bateriam com o livro aberto ao lado."""

    roque: str = ""
    """Vazio significa *deduzir* com `roque_provavel`. Um valor explícito vence a dedução."""

    ancora: Ancora = Ancora()

    def fen(self) -> str:
        """A FEN completa desta posição.

        Um `placement` que já venha com os cinco campos é respeitado inteiro: quem digitou uma FEN à
        mão quer aquela FEN, e sobrescrever a vez dela seria o mesmo defeito, do outro lado.
        """
        bruto = str(self.placement or "").strip()
        partes = bruto.split()
        if len(partes) >= 4:
            return bruto
        campo = partes[0] if partes else chess.STARTING_BOARD_FEN
        vez = "b" if str(self.vez).lower().startswith("b") else "w"
        roque = self.roque.strip() or roque_provavel(campo)
        cheio = self.lance if self.lance and self.lance > 0 else 1
        candidata = f"{campo} {vez} {roque} - 0 {cheio}"
        try:
            chess.Board(candidata)
        except ValueError:
            # Direito de roque que a posição não sustenta -- acontece com placement corrompido pelo
            # OCR. Cair para "sem roque" é pior que o certo e melhor que não abrir o estudo.
            candidata = f"{campo} {vez} - - 0 {cheio}"
        return candidata

    def valida(self) -> bool:
        try:
            chess.Board(self.fen())
        except (ValueError, IndexError):
            return False
        return True


# ---------------------------------------------------------------------------- estudo


@dataclass
class Estudo:
    """Uma partida anotada a partir de um diagrama do livro, e onde se está dentro dela.

    `no` é o nó corrente, e é **o objeto**, não um caminho: dentro de uma sessão a referência
    sobrevive a promover e apagar variante, e um caminho não sobreviveria (ver o cabeçalho).
    """

    jogo: chess.pgn.Game
    ancora: Ancora = Ancora()
    invertido: bool = False
    """Tabuleiro visto das pretas. Vai para o header `Orientation`, que é nosso e não colide com
    nada do padrão -- um leitor que não o conheça o ignora."""

    no: chess.pgn.GameNode = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.no = self.jogo

    # -------------------------------------------------------------- construção

    @classmethod
    def de_posicao(cls, posicao: PosicaoDeEstudo) -> Estudo:
        """Um estudo novo daquela posição, com os headers de procedência preenchidos."""
        jogo = chess.pgn.Game()
        jogo.setup(chess.Board(posicao.fen()))
        ancora = posicao.ancora
        invertido = str(posicao.vez).lower().startswith("b")

        # `Event` nomeia a **origem** e `Site` é "Local": é o par que `pdf_to_pgn.py:698-699` já
        # escreve, e o livro mora em `SourcePDF`, não aqui. Um PGN deste projeto aberto no ChessBase
        # tem de se parecer com os outros PGNs deste projeto.
        jogo.headers["Event"] = EVENTO
        jogo.headers["Site"] = LOCAL
        jogo.headers["Result"] = "*"
        jogo.headers["Annotator"] = ANOTADOR
        if ancora.valida:
            jogo.headers["Round"] = f"{ancora.pagina + 1}.{ancora.diagrama + 1}"
            jogo.headers["SourcePDF"] = ancora.nome_do_livro
            jogo.headers["Page"] = str(ancora.pagina + 1)
            jogo.headers["Diagram"] = str(ancora.diagrama + 1)
            if ancora.titulo:
                jogo.headers["Caption"] = ancora.titulo
        if not posicao.roque.strip() and roque_provavel(posicao.placement) != "-":
            # A procedência do que foi deduzido fica escrita, como manda a S-04 -- e o nome do
            # header é o que `pdf_to_pgn.py:727` já usa para a mesma dedução.
            jogo.headers["CastlingSource"] = "inferred"
        jogo.headers["Orientation"] = "black" if invertido else "white"
        return cls(jogo=jogo, ancora=ancora, invertido=invertido)

    @classmethod
    def de_pgn(cls, texto: str, *, documento: str = "") -> Estudo | None:
        """O estudo daquele PGN, ou `None` se ele não é legível.

        `documento` é o caminho do livro que o chamador conhece: o header `SourcePDF` guarda só o
        **nome**, porque é o que serve a quem abrir o arquivo no ChessBase. O caminho inteiro vem de
        fora, de quem sabe de que arquivo o PGN foi lido.
        """
        try:
            jogo = chess.pgn.read_game(io.StringIO(str(texto or "")))
        except Exception as erro:  # noqa: BLE001 - PGN de fora pode falhar de muitas formas
            logger.debug("PGN de estudo ilegível: %s", erro)
            return None
        return None if jogo is None else cls.de_jogo(jogo, documento=documento)

    @classmethod
    def de_jogo(cls, jogo: chess.pgn.Game, *, documento: str = "") -> Estudo:
        """O estudo de uma partida já lida -- é por aqui que a `Sala` percorre um PGN de muitos."""
        ancora = Ancora(
            documento=documento or jogo.headers.get("SourcePDF", ""),
            pagina=_inteiro(jogo.headers.get("Page", "")) - 1,
            diagrama=_inteiro(jogo.headers.get("Diagram", "")) - 1,
            titulo=jogo.headers.get("Caption", ""),
        )
        invertido = str(jogo.headers.get("Orientation", "white")).lower().startswith("b")
        return cls(jogo=jogo, ancora=ancora, invertido=invertido)

    # -------------------------------------------------------------- saída

    def para_pgn(self) -> str:
        """O estudo como PGN, com headers -- que é o formato do arquivo e o da exportação."""
        self.jogo.headers["Orientation"] = "black" if self.invertido else "white"
        exportador = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
        return str(self.jogo.accept(exportador)).strip()

    # -------------------------------------------------------------- estado

    @property
    def raiz(self) -> chess.pgn.Game:
        return self.jogo

    @property
    def tabuleiro(self) -> chess.Board:
        return self.no.board()

    def caminho(self) -> Caminho:
        return caminho_de(self.no)

    def ir_para(self, caminho: Caminho) -> bool:
        """Vai ao nó daquele endereço. `False` -- e volta para a raiz -- se ele não existe mais."""
        alvo = no_em(self.jogo, caminho)
        if alvo is None:
            self.no = self.jogo
            return False
        self.no = alvo
        return True

    def vazio(self) -> bool:
        """Não há nada aqui que valha guardar: nem lance, nem comentário, nem símbolo, nem seta.

        É a régua que decide o que entra na `Sala` e no arquivo. Um livro tem ~1.500 diagramas, e
        clicar em todos criaria 1.500 partidas de zero lance com aparência de trabalho.

        **O que a máquina escreveu não conta** (S-285): a avaliação do motor mora dentro do mesmo
        campo `comment`, em `[%eval 0.35,18]`, e com a análise contínua ligada ela aparece em todo
        nó por onde se navega. Contá-la faria *passar o olho* num diagrama criar um estudo dele --
        e a sala do livro encheria de posições que ninguém analisou. Por isso a pergunta é sobre
        `texto_do_comentario`, e não sobre `comment`.
        """
        if self.jogo.variations or self.jogo.nags:
            return False
        if texto_do_comentario(self.jogo.comment or ""):
            return False
        return not setas_de(self.jogo)

    def contagem_de_lances(self) -> int:
        """Quantos lances a árvore inteira tem -- linha principal e variantes."""
        return sum(1 for _ in _todos_os_nos(self.jogo)) - 1

    def rotulo(self) -> str:
        return self.ancora.rotulo()


def _inteiro(texto: str) -> int:
    limpo = str(texto or "").strip()
    return int(limpo) if limpo.isdigit() else 0


def _todos_os_nos(no: chess.pgn.GameNode) -> Iterator[chess.pgn.GameNode]:
    yield no
    for filho in no.variations:
        yield from _todos_os_nos(filho)


# ---------------------------------------------------------------------------- colar (S-288)


def colar(texto: str, *, ancora: Ancora = Ancora()) -> tuple[Estudo | None, str]:
    """O que foi colado, como estudo -- ou `None` e **o motivo**.

    O plugin que serviu de referência decide entre FEN e PGN por `chessString.includes('/')`
    (`ChessStringModal.ts`), e a régua é frágil dos dois lados: um comentário de PGN com uma data
    tem barra, e uma FEN mal copiada não tem. Aqui a pergunta é outra e é a que o dado responde:
    **o `chess` consegue montar um tabuleiro com isto?** Se sim, é posição; se não, tenta-se partida.

    O motivo nunca é vazio quando o estudo é `None`, e nunca é genérico: é o que
    `chess.pgn.read_game` registrou em `errors`, que nomeia o lance que não fechou. "PGN inválido"
    mandaria a pessoa procurar o defeito num texto que ela acabou de colar.

    **Não descarta nada**: quem decide o que fazer com o estudo devolvido é quem chamou.
    """
    limpo = str(texto or "").strip()
    if not limpo:
        return None, "Não há nada colado para ler."

    primeira = limpo.splitlines()[0].strip()
    if _e_posicao(primeira):
        posicao = PosicaoDeEstudo(placement=primeira, ancora=ancora)
        if posicao.valida():
            return Estudo.de_posicao(posicao), ""
        return None, f"A FEN colada não é uma posição válida: {primeira[:60]}"

    try:
        jogo = chess.pgn.read_game(io.StringIO(limpo))
    except Exception as erro:  # noqa: BLE001 - texto colado pode ser qualquer coisa
        return None, f"O PGN colado não pôde ser lido: {erro}"
    if jogo is None or (not jogo.variations and not jogo.headers.get("FEN")):
        return None, "O texto colado não é uma FEN nem um PGN."
    if jogo.errors:
        return None, f"O PGN colado tem lance que não fecha: {jogo.errors[0]}"
    return Estudo.de_jogo(jogo, documento=ancora.documento), ""


def _e_posicao(linha: str) -> bool:
    """Uma linha é posição quando o `chess` monta um tabuleiro com ela.

    As oito barras não bastam como régua -- e nem sobram: um campo de peças sozinho (o que o OCR
    desta casa produz) tem sete, e `PosicaoDeEstudo` sabe completá-lo. Por isso a pergunta vai ao
    `chess`, que é quem responde de verdade.
    """
    if linha.startswith("["):
        return False
    try:
        chess.Board(linha if " " in linha else f"{linha} w - - 0 1")
    except (ValueError, IndexError):
        return False
    return True


# ---------------------------------------------------------------------------- sala


class Sala:
    """Os estudos de um livro, um por diagrama (S-270).

    **O item é `abrir`.** Antes disto, trocar de diagrama chamava `_set_board_state`, que fazia
    `self.game = self._new_game(board)` -- a árvore inteira no lixo, sem pergunta, sem aviso e sem
    desfazer. E `follow_ocr_var` nasce em `True`, então essa era a configuração *padrão*.

    Com a sala, trocar de diagrama deixa de ser recomeçar e passa a ser ir para a outra mesa: o
    estudo daquele diagrama volta como estava, com árvore e nó corrente.

    **A chave é a âncora, nunca a FEN.** Duas páginas com o mesmo diagrama são dois estudos; o mesmo
    diagrama relido com outra correção de OCR continua sendo um.
    """

    def __init__(self, documento: str = "") -> None:
        self.documento = str(documento or "")
        self._por_chave: dict[str, Estudo] = {}

    def __len__(self) -> int:
        return len(self._por_chave)

    def __contains__(self, ancora: object) -> bool:
        return isinstance(ancora, Ancora) and ancora.chave() in self._por_chave

    def em(self, ancora: Ancora) -> Estudo | None:
        """O estudo guardado naquele diagrama, ou `None`."""
        return self._por_chave.get(ancora.chave()) if ancora.valida else None

    def abrir(self, posicao: PosicaoDeEstudo) -> Estudo:
        """O estudo daquele diagrama: o guardado, se houver; um novo, se não.

        Um novo **não** é guardado aqui. Quem guarda é `guardar`, e só o que não é `vazio()`.
        """
        guardado = self.em(posicao.ancora)
        if guardado is not None:
            return guardado
        return Estudo.de_posicao(posicao)

    def guardar(self, estudo: Estudo | None) -> bool:
        """Guarda o estudo se ele tiver o que guardar, e o **tira** da sala se ele esvaziou.

        Os dois lados importam: apagar o último lance de um estudo tem de tirá-lo da coleção, senão o
        arquivo do livro acumula partidas de zero lance que ninguém pediu.
        """
        if estudo is None or not estudo.ancora.valida:
            return False
        chave = estudo.ancora.chave()
        if estudo.vazio():
            self._por_chave.pop(chave, None)
            return False
        self._por_chave[chave] = estudo
        return True

    def descartar(self, ancora: Ancora) -> bool:
        return self._por_chave.pop(ancora.chave(), None) is not None if ancora.valida else False

    def estudos(self) -> tuple[Estudo, ...]:
        """Os estudos, **em ordem de página e diagrama** -- que é a ordem em que se lê o livro."""
        return tuple(sorted(self._por_chave.values(), key=lambda e: (e.ancora.pagina, e.ancora.diagrama)))
