"""Motor de análise UCI (Stockfish), opcional (S-33).

**Por que opcional de verdade, e não "opcional mas na prática obrigatório".** O produto é um
OCR de diagramas; avaliar a posição é um extra útil. Sem binário instalado, o app funciona
igual e a seção some da tela -- não fica um botão cinza nem uma mensagem de erro a cada
abertura. `find_engine` procura, `EngineAnalyzer` só existe se achou.

**O processo fica aberto entre as análises.** Abrir e fechar o Stockfish a cada posição
custa ~100–300 ms de inicialização, o que sozinho já estouraria o "avaliação em menos de
2 s" do critério de aceite. O preço é ter de fechá-lo explicitamente ao sair -- daí o
`close()` e o suporte a `with`.

**O tempo é teto, não alvo.** `movetime` limita quanto o motor pensa; numa posição simples
ele responde antes. Preferido a `depth` fixo porque profundidade não tem relação estável
com tempo: 20 plies num final são instantâneos e num meio-jogo travado, não.

**O que este módulo não faz.** Não decide se a posição é plausível. A S-33 nota que uma
avaliação bizarra num livro de táticas sugere erro de OCR e poderia alimentar a fila da
S-22; isso é uma hipótese que precisa ser medida antes de virar prioridade, e medi-la exige
o motor instalado -- que não está nesta máquina. Fica registrado como o que é: não feito.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chess
import chess.engine

logger = logging.getLogger(__name__)

ENV_ENGINE_PATH = "CVOFF_ENGINE_PATH"

DEFAULT_MOVETIME_MS = 800
"""Bem abaixo dos 2 s do critério de aceite da S-33, com folga para o custo de ida e volta
com o processo. Configurável para quem quiser análise mais funda."""

TETO_DE_CENTIPEOES = 1000
"""Dez peões: o maior número que uma avaliação diz alguma coisa (S-537/S-538).

**Um número só, com dois nomes, e é de propósito**: `ui/analise_da_partida.TETO_DE_AVALIACAO` é
este valor importado, e não uma segunda constante. A camada pura corta a perda de um lance aqui, e
o motor corta aqui o que a tabela de finais lhe manda -- as duas coisas são a mesma afirmação
("acima de dez peões a diferença deixa de ser informação"), e duas cópias dela divergiriam."""

CP_MINIMO_DE_TABELA = 15_000
"""Acima de 150 peões o `cp` do UCI **não é uma avaliação**: é a tabela de finais falando (S-538).

O Stockfish imprime a vitória por tablebase como `cp 20000 - ply` (`UCI::value`), reservando a
faixa acima de `VALUE_TB_WIN_IN_MAX_PLY` para isso. Sem tratá-la, um KBNvK com `SyzygyPath`
configurado saía na tela como **`+200,00`** e ia para o arquivo como `[%eval 200.0]` -- medido
nesta máquina com as tabelas de 3 e 4 peças. Cento e cinquenta peões é o corte: nenhuma busca
devolve tanto (o material inteiro de um lado dá ~103), e a faixa do Stockfish começa em 19.754."""

CANDIDATE_NAMES = ("stockfish", "stockfish.exe")

CANDIDATE_DIRS = (
    Path("engines"),
    Path("Stockfish"),
    Path("C:/Program Files/Stockfish"),
    Path("C:/Program Files/scid_windows_x64/engines"),
    Path("/usr/games"),
    Path("/usr/local/bin"),
)
"""Onde procurar além do `PATH`. A pasta `engines/` do projeto vem primeiro para que baixar
o binário ali seja a instalação mais simples possível.

A pasta do SCID entrou na S-536, e não é generosidade com um programa de terceiro: quem estuda
xadrez num PC quase sempre já instalou SCID ou ChessBase, e os dois trazem um Stockfish dentro.
Foi assim que esta máquina passou a ter motor -- `C:/Program Files/scid_windows_x64/engines/
stockfish.exe`, Stockfish dev-20230303 --, e antes disso a seção do motor nunca aparecia aqui."""


FALHAS_AO_ABRIR: tuple[type[BaseException], ...] = (
    asyncio.TimeoutError,
    TimeoutError,
    OSError,
    chess.engine.EngineError,
    chess.engine.EngineTerminatedError,
)
"""O que `popen_uci` levanta quando o binário não vira motor. Ver `MotorNaoRespondeu`.

**`asyncio.TimeoutError` e o `TimeoutError` embutido são classes diferentes no Python 3.10**, e
esta linha existe por causa disso: só a partir do 3.11 um é apelido do outro. A primeira redação
capturava o embutido, o `popen_uci` levantava o do `asyncio`, e a janela continuava mostrando a
palavra `TimeoutError` -- exatamente o defeito que a classe veio consertar. Os dois ficam na tupla
para que a versão do Python não decida qual mensagem o usuário lê."""


class MotorNaoRespondeu(RuntimeError):
    """O binário abriu e não falou UCI (S-536, segunda rodada).

    **Existe para que a frase chegue à janela em português.** `SimpleEngine.popen_uci` espera dez
    segundos por `uciok` e, se ele não vem -- porque o programa apontado não é um motor --, levanta
    `TimeoutError`, que tem `str()` **vazio**. `cli.message_for` cai então no nome da classe e a
    janela mostrava a palavra `TimeoutError`, crua e em inglês. Com uma classe própria, a mensagem
    é a frase, e `message_for` a devolve intacta.

    Quem escreve a frase é `ui/motor_declarado.frase_de_motor_que_nao_responde`: ela é texto de
    tela, e texto de tela é decisão da camada pura.
    """


def find_engine(explicit: str | Path | None = None, *, env: dict[str, str] | None = None) -> Path | None:
    """Localiza o binário do motor, ou `None`. Nunca levanta: ausência é o caso normal.

    Ordem: o que foi pedido explicitamente, a variável de ambiente, o `PATH`, e por fim os
    diretórios conhecidos. O explícito vem primeiro porque quem informou um caminho quer
    aquele binário, e cair no do `PATH` em silêncio esconderia o erro de digitação.
    """
    ambiente = os.environ if env is None else env

    for candidato in (explicit, ambiente.get(ENV_ENGINE_PATH, "").strip() or None):
        if candidato:
            caminho = Path(candidato)
            if caminho.is_file():
                return caminho
            logger.warning("Motor informado nao existe: %s", caminho)
            return None

    for nome in CANDIDATE_NAMES:
        achado = shutil.which(nome)
        if achado:
            return Path(achado)

    for diretorio in CANDIDATE_DIRS:
        for nome in CANDIDATE_NAMES:
            caminho = diretorio / nome
            if caminho.is_file():
                return caminho
    return None


@dataclass(frozen=True)
class Evaluation:
    """O que o motor achou da posição, do ponto de vista das **brancas**.

    Normalizar para as brancas é o que faz a barra de vantagem ter um sentido só. O valor
    cru do UCI é relativo a quem joga, e mostrá-lo assim faria a barra pular de lado a cada
    lance sem que a posição tivesse mudado de dono.
    """

    score_cp: int | None
    """Centipeões, positivo para as brancas. `None` quando há mate anunciado."""

    mate_in: int | None
    """Lances até o mate, positivo se quem dá o mate são as brancas."""

    best_move: chess.Move | None
    best_move_san: str = ""
    pv_san: tuple[str, ...] = ()
    depth: int = 0
    elapsed_s: float = 0.0

    tabela: int | None = None
    """`+1` vitória por tabela de finais das brancas, `-1` das pretas, `None` fora dela (S-538).

    Vem do `cp` que o motor imprime acima de `CP_MINIMO_DE_TABELA`. Quando ele está preenchido,
    `score_cp` já foi reescrito para `±TETO_DE_CENTIPEOES` -- é o número que a barra, o gráfico e o
    `[%eval]` do arquivo entendem, e ele diz o que a tabela disse ("acabou, e é deste lado") sem
    afirmar duzentos peões de vantagem."""

    nodes: int = 0
    nps: int = 0
    """Nós visitados e nós por segundo, como o UCI os relata (S-529).

    **Profundidade sozinha não diz se o motor está usando a máquina.** É o único número da tela
    que muda quando `Threads` muda -- a profundidade também muda, mas devagar e por posição --, e
    sem ele não há como ver que a opção pegou. Zero é "o motor não relatou", que alguns relatam
    só no fim da busca."""

    @property
    def is_mate(self) -> bool:
        return self.mate_in is not None

    def display(self) -> str:
        """A avaliação como se lê num tabuleiro: `+1,35`, `-0,40`, `M3`, `-M2`, `1-0`.

        **A vitória por tabela sai como resultado e não como número** (S-538): a tabela não estima
        uma vantagem, ela sabe o placar. `1-0` e `0-1` são os tokens do PGN, que não têm idioma, e
        são os mesmos que a barra já escreve quando o leitor de tablebases da sala responde.
        """
        if self.tabela is not None:
            return "1-0" if self.tabela > 0 else "0-1"
        if self.mate_in is not None:
            return f"{'M' if self.mate_in > 0 else '-M'}{abs(self.mate_in)}"
        if self.score_cp is None:
            return "—"
        return f"{self.score_cp / 100:+.2f}".replace(".", ",")

    def advantage_fraction(self) -> float:
        """Posição da barra, de 0 (pretas ganhando) a 1 (brancas ganhando).

        A conta mora em `fracao_de_vantagem` desde a S-537: a barra lateral, o gráfico da partida
        inteira e este método precisam da **mesma** curva, e três cópias dela divergiriam na
        primeira vez que alguém a ajustasse -- com o número escrito ao lado discordando da barra
        que o desenha.
        """
        return fracao_de_vantagem(self.score_cp, self.mate_in)

    def summary(self) -> str:
        """Uma linha para a interface: avaliação, melhor lance e profundidade."""
        partes = [f"Avaliação: {self.display()}"]
        if self.best_move_san:
            partes.append(f"melhor lance: {self.best_move_san}")
        if self.depth:
            partes.append(f"profundidade {self.depth}")
        return "  |  ".join(partes)


def fracao_de_vantagem(score_cp: int | None, mate_in: int | None) -> float:
    """A avaliação como fração de barra, de 0 (pretas ganhando) a 1 (brancas ganhando).

    **A conversão é logística e não linear**: a diferença entre +0,2 e +1,0 muda a partida, a
    diferença entre +8 e +12 não muda nada. Uma barra linear gastaria quase toda a sua extensão
    com vantagens já decididas.

    `1/(1+10^(-cp/400))` é a curva de expectativa de pontuação do Elo, que é exatamente a relação
    entre vantagem e resultado que se quer mostrar -- ver a grade de comparação com a curva do
    Lichess no cabeçalho de `ui/motor_declarado.py`.

    É função de módulo, e não método, porque três desenhos a usam: a barra vertical da sala
    (S-529), o gráfico da partida inteira (S-537) e o `display` de cada linha do MultiPV.
    """
    if mate_in is not None:
        return 1.0 if mate_in > 0 else 0.0
    if score_cp is None:
        return 0.5
    return 1.0 / (1.0 + 10 ** (-score_cp / 400.0))


def _to_white_pov(score: chess.engine.PovScore) -> tuple[int | None, int | None, int | None]:
    """Extrai `(centipeões, mate_em, tabela)` do ponto de vista das brancas.

    **`mate 0` não carrega sinal, e é o mate que já aconteceu** (S-537). O UCI o responde na
    posição em que quem está no lance está mateado, e `Mate(0)` e `MateGiven` -- os dois lados
    disso -- respondem `0` a `.mate()`. Um zero sem sinal fazia a posição final de toda partida
    valer `-M0`: a barra ia para o lado do vencedor errado, e a análise da partida inteira marcava
    o lance de mate como **erro grave** de quem o deu (medido na Imortal e na defesa de Legall).

    Normalizado para `±1`, que é o que ele quer dizer -- "acabou, e foi deste lado". A diferença
    entre um mate dado e um mate em um lance não muda decisão nenhuma no programa: as duas enchem
    a barra, e as duas valem o teto na conta de perda.

    **A faixa da tabela de finais é a outra normalização** (S-538, segunda rodada). Ver
    `CP_MINIMO_DE_TABELA`: acima dela o `cp` é a tabela dizendo o placar, e ele vira
    `tabela=±1` com o `score_cp` reescrito no teto de dez peões.
    """
    brancas = score.white()
    mate = brancas.mate()
    if mate is not None:
        return None, int(mate) or (1 if brancas > chess.engine.Cp(0) else -1), None
    centipeoes = brancas.score()
    if centipeoes is None:
        return None, None, None
    valor = int(centipeoes)
    if abs(valor) >= CP_MINIMO_DE_TABELA:
        lado = 1 if valor > 0 else -1
        return lado * TETO_DE_CENTIPEOES, None, lado
    return valor, None, None


class EngineAnalyzer:
    """Um processo de motor aberto, analisando posições sob demanda.

    Serializa o acesso com um lock: o protocolo UCI é uma conversa, e duas threads falando
    com o mesmo processo embaralham as respostas -- o resultado de uma análise chegaria
    como se fosse o da outra.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        movetime_ms: int = DEFAULT_MOVETIME_MS,
        threads: int = 1,
        hash_mb: int = 0,
        multipv: int = 0,
        syzygy_path: str = "",
    ) -> None:
        self.path = Path(path)
        self.movetime_ms = int(movetime_ms)
        self.multipv = max(0, int(multipv))
        """Quantas linhas `analyse_multi` devolve quando ninguém pede um número (S-536).

        Zero é "não declarado", e aí quem manda é o argumento de quem chama. Não é opção UCI:
        `python-chess` a envia a cada `analyse` e a repõe depois, então mudá-la nunca derruba o
        processo -- é a metade fácil do "sem reiniciar" da S-536."""

        self._lock = threading.RLock()
        self._engine: chess.engine.SimpleEngine | None = None
        self._opcoes: dict[str, int | str] = {"Threads": max(1, int(threads))}
        if hash_mb:
            self._opcoes["Hash"] = max(1, int(hash_mb))
        if str(syzygy_path or "").strip():
            self._opcoes["SyzygyPath"] = str(syzygy_path).strip()

    @property
    def name(self) -> str:
        motor = self._engine
        if motor is None:
            return self.path.name
        return str(motor.id.get("name", self.path.name))

    @property
    def opcoes(self) -> dict[str, int | str]:
        """As opções UCI que este motor carrega, como uma cópia. É por ela que o teste pergunta."""
        with self._lock:
            return dict(self._opcoes)

    def start(self) -> None:
        """Sobe o processo. Um binário que não fala UCI vira `MotorNaoRespondeu`, em pt-BR.

        O `import` é dentro da função de propósito: `ui/motor_declarado.py` importa este módulo
        (a curva da barra mora aqui), e importá-lo de volta no topo fecharia o ciclo. A frase é
        decisão de tela e mora lá; o que este módulo faz é levantar a classe certa.
        """
        with self._lock:
            if self._engine is not None:
                return
            logger.info("Abrindo motor de analise: %s", self.path)
            try:
                self._engine = chess.engine.SimpleEngine.popen_uci(str(self.path))
            except FALHAS_AO_ABRIR as exc:
                from chess_diagram_ocr.ui.motor_declarado import frase_de_motor_que_nao_responde

                logger.warning("O motor em %s nao respondeu ao UCI: %r", self.path, exc)
                raise MotorNaoRespondeu(frase_de_motor_que_nao_responde(str(self.path))) from exc
            self._configurar(self._opcoes)

    def _configurar(self, opcoes: dict[str, int | str]) -> list[str]:
        """Manda `setoption` uma a uma e devolve as que pegaram. Nunca levanta.

        **Uma a uma, e não num `configure` só** (S-536). `SimpleEngine.configure` manda o
        dicionário inteiro e levanta no primeiro nome que o motor não conhece -- e nesse caminho as
        opções que vinham depois **não** são enviadas. Um motor sem `Hash` perderia o `Threads`
        junto, que é o oposto da degradação que a S-33 declara: aparência não derruba ferramenta.
        """
        motor = self._engine
        if motor is None:  # pragma: no cover - só se chamado fora de `start`
            return []
        aceitas: list[str] = []
        for nome, valor in opcoes.items():
            try:
                motor.configure({nome: valor})
            except (chess.engine.EngineError, chess.engine.EngineTerminatedError) as exc:
                logger.debug("Motor nao aceitou a opcao %s: %s", nome, exc)
                continue
            aceitas.append(nome)
        return aceitas

    def reconfigurar(self, opcoes: dict[str, int | str]) -> list[str]:
        """Aplica opções UCI ao processo **aberto**, sem derrubá-lo. Devolve as que pegaram (S-536).

        **É o que faz "sem reiniciar" ser verdade.** `setoption name Hash value 512` é uma linha no
        `stdin` do processo, e o Stockfish realoca a tabela de transposição sozinho; fechar e
        reabrir custaria os 100 a 300 ms de inicialização que o cabeçalho deste módulo registra, e
        perderia a análise em curso.

        O motor **fechado** só guarda: elas entram no próximo `start`. Não abrir aqui é decisão --
        mexer nas preferências de quem não pediu análise nenhuma não pode subir um processo.

        Serializado pelo mesmo `lock` da análise: um `setoption` no meio de um `go` embaralharia a
        conversa, e é a mesma razão que fez o lock existir.
        """
        limpas = {str(nome): valor for nome, valor in opcoes.items()}
        with self._lock:
            self._opcoes.update(limpas)
            if self._engine is None:
                return []
            return self._configurar(limpas)

    def close(self) -> None:
        with self._lock:
            if self._engine is None:
                return
            try:
                self._engine.quit()
            except Exception as exc:  # pragma: no cover - encerramento e best-effort
                logger.debug("Falha ao encerrar o motor: %s", exc)
            finally:
                self._engine = None

    def trocar_binario(self, caminho: str | Path) -> None:
        """Derruba o processo e passa a apontar para outro binário (S-536).

        **O objeto é o mesmo, e é isso que o método existe para garantir.** A janela guarda uma
        referência ao analisador e é ela quem o fecha ao sair; um `EngineAnalyzer` novo a cada
        troca deixaria o processo da última troca vivo depois de a janela fechar -- e o
        `closeEvent` fecharia um motor que já morreu.

        O processo novo **não** sobe aqui: quem o quer aberto chama `start()`, e quem trocou o
        caminho e não vai analisar nada não precisa pagar os 100 a 300 ms. As opções guardadas
        acompanham a troca, porque elas são das preferências e não do binário.
        """
        with self._lock:
            self.close()
            self.path = Path(caminho)

    def __enter__(self) -> EngineAnalyzer:
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def analyse(
        self, board: chess.Board, *, movetime_ms: int | None = None, depth: int | None = None
    ) -> Evaluation:
        """Avalia a posição. Levanta `RuntimeError` se o motor não responder.

        Posição sem lance legal (mate ou afogamento) devolve avaliação sem melhor lance em
        vez de erro: é uma resposta legítima, e o motor não tem o que sugerir.

        **`depth` é o limite da análise da partida inteira** (S-537), e ele vence o tempo. O
        cabeçalho deste módulo diz por que o tempo é o limite normal -- profundidade não tem
        relação estável com tempo --, e a análise de partida quer justamente o outro lado disso:
        para comparar o lance 12 com o lance 40 os dois têm de ter sido pensados igual, e "igual"
        aí é profundidade e não relógio.
        """
        import time

        limite = (
            chess.engine.Limit(depth=int(depth), time=(movetime_ms / 1000.0) if movetime_ms else None)
            if depth
            else chess.engine.Limit(time=(movetime_ms or self.movetime_ms) / 1000.0)
        )
        inicio = time.monotonic()
        with self._lock:
            self.start()
            assert self._engine is not None
            try:
                info = self._engine.analyse(board, limite)
            except chess.engine.EngineError as exc:
                raise RuntimeError(f"O motor de análise falhou: {exc}") from exc

        return _avaliacao_de(board, info, elapsed_s=time.monotonic() - inicio)


    def analyse_multi(
        self, board: chess.Board, *, count: int = 0, movetime_ms: int | None = None
    ) -> list[Evaluation]:
        """As `count` melhores linhas, da melhor para a pior (S-286).

        **Uma linha diz "o motor prefere isto"; três dizem "estas são as opções"** -- e a segunda
        frase é a que um estudo precisa. Para quem lê um livro a pergunta quase nunca é qual é o
        melhor lance: é se o lance que o livro dá está entre os candidatos.

        `MultiPV` é opção UCI, e nem todo motor a aceita. Motor que recusa devolve **uma** linha em
        vez de erro: a degradação é a mesma que `start` já aplica a `Threads`, e é a regra do
        projeto desde a S-33 -- aparência não derruba ferramenta.

        A opção é reposta em 1 no fim. Deixá-la ligada faria a `analyse` seguinte -- que lê
        `info["pv"]` de um `dict` e não de uma lista -- receber outra forma de resposta.

        `count=0` -- o padrão desde a S-536 -- pega o número das preferências (`self.multipv`), e
        três continua sendo o valor de fábrica delas. Quem passa um número manda nele: a análise
        da partida inteira pede **uma** linha por lance, porque ali a pergunta é o placar e não os
        candidatos.
        """
        quantas = max(1, int(count) or self.multipv or 3)
        limite = chess.engine.Limit(time=(movetime_ms or self.movetime_ms) / 1000.0)
        with self._lock:
            self.start()
            assert self._engine is not None
            try:
                infos = self._engine.analyse(board, limite, multipv=quantas)
            except chess.engine.EngineError as exc:
                raise RuntimeError(f"O motor de análise falhou: {exc}") from exc

        avaliacoes = [_avaliacao_de(board, info) for info in infos]
        return avaliacoes or [_avaliacao_de(board, {})]


def _avaliacao_de(board: chess.Board, info: Any, *, elapsed_s: float = 0.0) -> Evaluation:
    """Uma resposta do UCI virada `Evaluation`. É o mesmo molde para a linha única e para o MultiPV.

    Existe porque a S-286 precisava do mesmo desmonte duas vezes, e duas cópias dele divergiriam na
    primeira vez que um campo mudasse -- é o mecanismo que a S-31 registra para todo par de
    implementações da mesma coisa.
    """
    pontuacao = info.get("score")
    cp, mate, tabela = _to_white_pov(pontuacao) if pontuacao is not None else (None, None, None)
    pv = list(info.get("pv") or [])
    melhor = pv[0] if pv and board.is_legal(pv[0]) else None
    return Evaluation(
        score_cp=cp,
        mate_in=mate,
        tabela=tabela,
        best_move=melhor,
        best_move_san=board.san(melhor) if melhor is not None else "",
        pv_san=tuple(_variation_san(board, pv)),
        depth=int(str(info.get("depth") or 0)),
        elapsed_s=elapsed_s,
        nodes=int(str(info.get("nodes") or 0)),
        nps=int(str(info.get("nps") or 0)),
    )


def _variation_san(board: chess.Board, moves: list[chess.Move], *, limit: int = 6) -> list[str]:
    """A linha principal em notação algébrica, cortada em `limit` lances.

    Cortar não é economia de tela: uma variante de 30 plies de um motor a 800 ms é palpite
    depois dos primeiros lances, e mostrá-la inteira sugeriria uma certeza que não existe.
    """
    tabuleiro = board.copy(stack=False)
    saida: list[str] = []
    for lance in moves[:limit]:
        if not tabuleiro.is_legal(lance):
            break
        saida.append(tabuleiro.san(lance))
        tabuleiro.push(lance)
    return saida
