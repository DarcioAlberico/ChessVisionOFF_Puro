"""O motor da sala de estudo: a posição avaliada, a partida inteira e as opções (S-866).

**Saiu de `qt/painel_de_estudo.py` inteiro, com o estado dele.** O motor é a única parte da sala
que pensa numa thread, e o que isso pede -- a geração que descarta a resposta atrasada (S-285), o
leitor de tablebases aberto na primeira consulta (S-538), o `MotorVivo` que troca o binário sem
reiniciar (S-536) e a rodada da partida inteira (S-537) -- era meia dúzia de atributos espalhados
entre os setenta do painel. Aqui eles são os atributos desta classe, e o painel guarda uma.

**A geração é a âncora da resposta.** Ela cresce em `posicao_mudou`, que o `refresh` do painel chama
a cada mudança de nó, e a resposta que chegar com geração velha é descartada. A thread é um
`threading.Thread` e não uma `Tarefa`: ela não toca nada do Qt, e volta por sinal deste objeto.

**O painel continua sendo quem a pessoa vê.** A seção do motor é montada aqui, mas mora na coluna de
leitura do painel; a barra de avaliação é do painel, porque ela está na fila do tabuleiro; e o
comando do catálogo continua sendo um método do painel, que delega -- `COMANDOS_DA_ABA` é uma
tabela só, e o `getattr` dela é sobre o painel.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import chess
import chess.engine
import chess.pgn
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QDialog, QGroupBox, QLabel, QPushButton, QVBoxLayout, QWidget

from chess_diagram_ocr import estudo as estudo_mod
from chess_diagram_ocr import tablebase
from chess_diagram_ocr.arquivo_do_dono import GravacaoRecusada, gravavel
from chess_diagram_ocr.engine import EngineAnalyzer, Evaluation
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.barra import BarraFluida
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.motor import LinhasDoMotor
from chess_diagram_ocr.settings import EngineSettings, ler_arquivo, load_settings, save_settings
from chess_diagram_ocr.ui import analise_da_partida as analise_declarada
from chess_diagram_ocr.ui import espaco, estilos, motor_declarado, strings, tokens
from chess_diagram_ocr.ui import finais as finais_declarados
from chess_diagram_ocr.ui.busy import BusyRegistry
from chess_diagram_ocr.ui.sala_declarada import CANDIDATOS_DO_MOTOR

if TYPE_CHECKING:
    from chess_diagram_ocr.qt.analise_da_partida import AnalisadorDaPartida, JanelaDaAnalise
    from chess_diagram_ocr.qt.painel_de_estudo import PainelDeEstudo

logger = logging.getLogger(__name__)

__all__ = ["MotorDaSala"]


class MotorDaSala(QObject):
    """O motor da sala: avaliação da posição, partida inteira, linha na árvore e opções."""

    _motor_respondeu = pyqtSignal(int, object, object)
    """Interno: `(geração, nó, avaliações)` vindo da thread do motor."""

    _motor_falhou = pyqtSignal(int, str)
    _motor_terminou = pyqtSignal(int)

    def __init__(
        self,
        sala: PainelDeEstudo,
        *,
        analyzer: EngineAnalyzer | None,
        caminho_das_preferencias: Path,
        busy: BusyRegistry | None,
    ) -> None:
        super().__init__(sala)
        self._sala = sala
        self._analyzer = analyzer
        """O motor, se houver um. `None` esconde a seção inteira em vez de deixá-la cinza (S-33)."""
        self._busy = busy
        self._analysing = False
        self._geracao = 0
        """Cresce a cada mudança de nó. A resposta do motor que chegar com geração velha é
        descartada -- ver `analyse` (S-285)."""
        self._candidatos: list[Evaluation] = []
        self._caminho_das_preferencias = Path(caminho_das_preferencias)
        """De onde saem e para onde voltam as opções do motor (S-536). Argumento porque o teste
        não pode escrever no `data/settings.json` do repositório."""
        self._motor_vivo: Any = None
        """O `MotorVivo` que aplica a troca fora da linha de eventos. Nasce no primeiro uso: sem
        ele, toda sala de teste carregaria uma `QThread` que nunca roda."""
        self._recusa_das_preferencias = ""
        """Por que as opções do motor não foram gravadas, quando não foram (S-812)."""
        self._analise_da_partida: AnalisadorDaPartida | None = None
        """A rodada de análise da partida inteira (S-537), guardada porque um `QObject` sem
        referência é recolhido com a thread dentro."""
        self._finais: Any = None
        """O leitor de tablebases (S-538), aberto na primeira consulta. `None` é "sem pasta"."""
        self._resultado_de_tabela: Any = None
        """O que a tabela disse da posição analisada, ou `None`. Escrito na thread do motor e lido
        na da interface, na mesma volta em que a avaliação chega -- os dois viajam juntos."""
        self._motor_respondeu.connect(self._mostrar_avaliacao)
        self._motor_falhou.connect(self._mostrar_erro_do_motor)
        self._motor_terminou.connect(self._terminar_analise)

    @property
    def has_engine(self) -> bool:
        return self._analyzer is not None

    @property
    def analisador(self) -> EngineAnalyzer | None:
        """O motor que a sala está usando **agora**. É por ele que a janela o fecha ao sair.

        A janela guarda o motor que ela construiu, e a sala pode tê-lo trocado (S-536): perguntar
        aqui é o que faz o `closeEvent` fechar o processo que está vivo, e não o que morreu.
        """
        return self._analyzer

    # ------------------------------------------------------------------------- a seção

    def montar_secao(self, pai: QWidget) -> QGroupBox:
        """A seção do motor. Sem binário, ela simplesmente não existe (S-33).

        **A S-529 trocou os dois widgets de dentro.** A avaliação era um `QProgressBar` horizontal
        de 0 a 100 aqui embaixo -- ela subiu para a barra vertical ao lado do tabuleiro, que é onde
        se lê --, e as linhas do MultiPV eram um `QLabel` de texto cinza, do qual não havia caminho
        nenhum para pôr a segunda ou a terceira na árvore. Agora são `LinhasDoMotor`, e o clique
        insere. O que ficou aqui é o botão, a frase de estado e o rodapé de desempenho.
        """
        assert self._analyzer is not None
        caixa = QGroupBox(
            motor_declarado.titulo_da_secao(self._analyzer.name, self._analyzer.path.name), pai
        )
        self.caixa_do_motor = caixa
        pilha = QVBoxLayout(caixa)
        pilha.setContentsMargins(*(espaco.linha(),) * 4)

        # **Uma `BarraFluida` e não um `QHBoxLayout`** (S-551, terceira rodada): numa janela de
        # 1024 a coluna de leitura cede para o tabuleiro caber inteiro, e um `QHBoxLayout` não
        # reflui -- o botão saía com o rótulo cortado dos dois lados (`nalisar posiçã`). A fila põe
        # a frase de estado na linha de baixo, que é o que este widget existe para fazer.
        linha = BarraFluida(caixa)
        self.btn_analisar = QPushButton("Analisar posição", linha)
        self.btn_analisar.clicked.connect(self.analyse)
        tema.aplicar_papel(self.btn_analisar, estilos.NEUTRO)
        dica_em(
            self.btn_analisar,
            "Fica cinza enquanto o motor está pensando nesta posição, e volta quando\n"
            "ele responde. Sem motor UCI instalado, esta seção inteira não aparece.",
        )
        linha.adicionar(self.btn_analisar)
        self.lbl_motor = QLabel("", linha)
        linha.adicionar(self.lbl_motor)
        pilha.addWidget(linha)

        self.lbl_linha_do_motor = LinhasDoMotor(caixa)
        self.lbl_linha_do_motor.escolhida.connect(self.inserir_linha_do_motor)
        pilha.addWidget(self.lbl_linha_do_motor, 1)

        # **Profundidade e nós por segundo**, na linha de baixo (S-529). Eles estavam no `summary`
        # da frase de cima, misturados com a avaliação e o melhor lance; separados, o número que
        # diz *o quanto confiar* deixa de disputar espaço com o número que diz *quanto vale*.
        self.lbl_desempenho = QLabel("", caixa)
        tema.pintar(self.lbl_desempenho, "color", tokens.TEXTO_SECUNDARIO)
        dica_em(
            self.lbl_desempenho,
            "Profundidade em plies e nós por segundo. Os nós por segundo são o único número da\n"
            "tela que muda quando a opção «Núcleos» muda -- é por ele que se vê que ela pegou.",
        )
        pilha.addWidget(self.lbl_desempenho)
        return caixa

    def _mostrar_o_titulo_do_motor(self) -> None:
        """`Motor (Stockfish dev-20230303)`: o nome que o **motor** diz, e não o do arquivo (S-529).

        **O nome UCI chega depois da montagem, e é por isso que isto é um método.** O processo só
        sobe na primeira análise -- é decisão de `motor_das_preferencias`, e ela paga os 100 a
        300 ms só de quem pede avaliação --, então na hora de desenhar a seção `EngineAnalyzer.name`
        ainda responde o nome do executável. Chamado outra vez quando o motor responde, o título
        passa a distinguir dois Stockfish de versões diferentes, que é o que este item existe para
        fazer. Quem monta a frase é `ui/motor_declarado`.

        Só escreve quando muda: com a análise contínua isto passa aqui a cada ~800 ms, e um
        `setTitle` por resposta repintaria a moldura da caixa para dizer a mesma coisa.
        """
        motor = self._analyzer
        if motor is None:  # pragma: no cover - sem motor não há seção nem título
            return
        titulo = motor_declarado.titulo_da_secao(motor.name, motor.path.name)
        if titulo != self.caixa_do_motor.title():
            self.caixa_do_motor.setTitle(titulo)

    # ------------------------------------------------------------- a posição avaliada

    def posicao_mudou(self) -> None:
        """O nó corrente mudou: a resposta pendente envelhece, e a análise contínua recomeça.

        Chamado pelo `refresh` do painel, e só por ele: `refresh` é o único ponto por onde toda
        mudança de nó passa, e é isso que faz a resposta atrasada do motor ser sempre descartada --
        inclusive a de um caminho de navegação que ainda não existe (S-285).
        """
        self._geracao += 1
        self._candidatos = []
        self._analisar_se_continuo()

    def analyse(self) -> None:
        """Pede a análise da posição corrente. A resposta atrasada é descartada (S-285)."""
        if self._analyzer is None:
            self._sala.set_status(strings.SEM_MOTOR_STATUS)
            return
        if self._analysing:
            return
        self._analysing = True
        self.btn_analisar.setEnabled(False)
        self.lbl_motor.setText("pensando…")
        threading.Thread(
            target=self._trabalho_do_motor,
            args=(self._geracao, self._sala.estudo.tabuleiro.copy(stack=False), self._sala.estudo.no),
            daemon=True,
        ).start()

    def _trabalho_do_motor(self, geracao: int, board: chess.Board, no: chess.pgn.GameNode) -> None:
        assert self._analyzer is not None
        try:
            # A tabela de finais **antes** do motor, e na mesma thread (S-538): ela responde em
            # microssegundos e a resposta dela vence a do motor onde existe. Perguntar depois faria
            # a tela mostrar a estimativa e trocá-la um instante depois.
            self._resultado_de_tabela = self._perguntar_a_tabela(board)
            # **Quantas linhas é preferência desde a S-536**, e `CANDIDATOS_DO_MOTOR` é o que
            # a sala pede quando ela não diz nada -- a medida da S-286, no lugar em que ela
            # sempre esteve.
            avaliacoes = self._analyzer.analyse_multi(
                board, count=self._analyzer.multipv or CANDIDATOS_DO_MOTOR
            )
            self._motor_respondeu.emit(geracao, no, avaliacoes)
        except Exception as exc:  # noqa: BLE001 - o motor é binário de terceiro
            logger.warning("Falha na análise: %s", exc)
            self._motor_falhou.emit(geracao, str(exc))
        finally:
            self._motor_terminou.emit(geracao)

    def _perguntar_a_tabela(self, board: chess.Board) -> Any:
        """O `Resultado` exato deste final, ou `None`. Sem pasta configurada, sempre `None` (S-538).

        `deve_consultar` é o que impede a ida ao disco em toda posição de meio-jogo: a sala passa
        o tempo em posições de 20 peças, e nenhuma tabela cobre essas.

        Devolve o **resultado** e não a frase: a frase depende da cor a jogar, e montá-la aqui --
        na thread do motor -- obrigaria a passar mais um dado pela fronteira. Quem a escreve é
        `_mostrar_avaliacao`, que já tem o tabuleiro corrente na mão.
        """
        leitor = self._leitor_de_finais()
        if not finais_declarados.deve_consultar(
            chess.popcount(board.occupied), tem_pasta=leitor is not None
        ):
            return None
        assert leitor is not None
        achado = leitor.consultar(board)
        return achado if achado is not None and finais_declarados.vence_o_motor(achado.wdl) else None

    def _leitor_de_finais(self) -> Any:
        """O leitor de tablebases, aberto na primeira consulta. `None` quando não há pasta."""
        if self._finais is None:
            self._finais = tablebase.abrir(self._opcoes_do_motor().syzygy_path)
        return self._finais

    def _mostrar_avaliacao(
        self, geracao: int, no: chess.pgn.GameNode, avaliacoes: list[Evaluation]
    ) -> None:
        """Só escreve se ainda estamos no mesmo lance -- ver `analyse`.

        **A tabela de finais vence o motor onde ela responde** (S-538): a frase de cima passa a ser
        o resultado exato, e a barra vai para onde o resultado manda em vez de ficar na estimativa.
        As linhas candidatas continuam sendo as do motor -- a tabela diz o resultado, não a
        variante --, e é por isso que ela substitui uma parte da tela e não a seção inteira.
        """
        if geracao != self._geracao or not avaliacoes:
            return
        self._candidatos = list(avaliacoes)
        melhor = avaliacoes[0]
        tabuleiro = self._sala.estudo.tabuleiro
        brancas = bool(tabuleiro.turn)
        achado = self._resultado_de_tabela
        frase = (
            finais_declarados.frase_do_resultado(achado.wdl, achado.dtz, brancas_jogam=brancas)
            if achado is not None
            else ""
        )
        self.lbl_motor.setText(frase or melhor.display())
        self._pintar_a_barra(melhor, achado, brancas=brancas)
        self.lbl_linha_do_motor.mostrar(
            motor_declarado.linhas_do_motor(
                avaliacoes,
                numero_do_lance=tabuleiro.fullmove_number,
                brancas_jogam=bool(tabuleiro.turn),
            ),
            vazio="Sem lance legal nesta posição.",
        )
        self.lbl_desempenho.setText(
            motor_declarado.frase_de_desempenho(
                profundidade=melhor.depth, nos=melhor.nodes, nos_por_segundo=melhor.nps
            )
        )
        self._gravar_avaliacao(no, melhor)

    def _pintar_a_barra(self, melhor: Evaluation, achado: Any, *, brancas: bool) -> None:
        """Põe a barra lateral onde a avaliação -- ou o resultado da tabela -- manda.

        Com tabela, o número dentro da barra vira o **resultado** (`1-0`, `0-1`, `=`) e não uma
        avaliação: são os tokens do PGN, que não têm idioma e que qualquer enxadrista lê. Escrever
        `+12,80` ali seria pôr uma estimativa em cima de uma certeza.
        """
        vantagem = self._sala.vantagem
        if vantagem is None:  # pragma: no cover - sem motor não há barra
            return
        if achado is None:
            vantagem.definir(melhor.score_cp, melhor.mate_in, melhor.display())
            return
        exatos = finais_declarados.centipeoes_de(
            achado.wdl, brancas_jogam=brancas, teto=analise_declarada.TETO_DE_AVALIACAO
        )
        vantagem.definir(exatos, None, "=" if not exatos else ("1-0" if exatos > 0 else "0-1"))

    def _gravar_avaliacao(self, no: chess.pgn.GameNode, avaliacao: Evaluation) -> None:
        """`[%eval 0.35,18]` no lance, que é onde o Lichess e o ChessBase o leem (S-285).

        **Fora da pilha de desfazer, e de propósito.** A avaliação não é edição de quem estuda:
        pô-la no histórico faria `Ctrl+Z` desfazer um número que o motor escreveu sozinho, e a
        pilha de quem analisou dez lances seria dez passos de nada.
        """
        if avaliacao.score_cp is None and avaliacao.mate_in is None:
            return
        pontuacao = (
            chess.engine.Mate(avaliacao.mate_in)
            if avaliacao.mate_in is not None
            else chess.engine.Cp(int(avaliacao.score_cp or 0))
        )
        no.set_eval(chess.engine.PovScore(pontuacao, chess.WHITE), avaliacao.depth or None)
        self._sala._marcar_sujo(historico=False, da_maquina=True)

    def _mostrar_erro_do_motor(self, geracao: int, mensagem: str) -> None:
        if geracao != self._geracao:
            return
        self.lbl_motor.setText("O motor não respondeu.")
        self.lbl_linha_do_motor.mostrar((), vazio=mensagem)

    def _terminar_analise(self, _geracao: int) -> None:
        self._analysing = False
        self.btn_analisar.setEnabled(True)
        # O processo já subiu (foi ele quem respondeu), então o `id name` do UCI existe: é aqui que
        # o título deixa de ser o nome do arquivo (S-529). Ver `_mostrar_o_titulo_do_motor`.
        self._mostrar_o_titulo_do_motor()
        # A posição pode ter mudado enquanto o motor pensava: com a análise contínua ligada, é aqui
        # que a próxima começa. Sem isto, navegar durante uma análise deixaria o motor parado.
        self._analisar_se_continuo()

    def _analisar_se_continuo(self) -> None:
        continua = self._sala.btn_continua
        if continua is not None and continua.isChecked() and self._analyzer is not None and not self._analysing:
            self.analyse()

    def alternar_analise_continua(self) -> None:
        """Liga e desliga o motor acompanhando o lance corrente."""
        continua = self._sala.btn_continua
        if self._analyzer is None or continua is None:
            self._sala.set_status(strings.SEM_MOTOR_STATUS)
            return
        continua.setChecked(not continua.isChecked())
        if continua.isChecked():
            self.analyse()
        else:
            self.lbl_motor.setText("")
            self.lbl_desempenho.setText("")
            self.lbl_linha_do_motor.mostrar(())
            if self._sala.vantagem is not None:
                self._sala.vantagem.limpar()

    # ------------------------------------------------------- a linha do motor na árvore

    def inserir_linha_do_motor(self, indice: int = 1) -> None:
        """Põe a `indice`-ésima linha do motor na árvore, a partir do lance corrente (S-286/S-529).

        **A procedência vai junto, no PGN.** O que a máquina sugeriu e o que a pessoa jogou não
        podem ficar indistinguíveis no arquivo -- é a regra 2 da SPEC_EDITOR aplicada a lance --, e
        a forma padrão de dizê-lo é o comentário de entrada da variante.

        **O índice existe desde a S-529**, e é o clique numa linha do MultiPV. Até aqui só a
        primeira era alcançável: as outras duas apareciam num `QLabel` e não havia caminho nenhum
        para pô-las na árvore -- o que anulava metade da razão de o MultiPV existir, que é comparar
        o lance do livro com os **candidatos** e não com o preferido.
        """
        sala = self._sala
        if self._analyzer is None:
            sala.set_status(strings.SEM_MOTOR_STATUS)
            return
        posicao = max(1, int(indice)) - 1
        melhor = self._candidatos[posicao] if posicao < len(self._candidatos) else None
        if melhor is None or not melhor.pv_san:
            sala.set_status("O motor ainda não respondeu sobre esta posição.")
            return

        tabuleiro = sala.estudo.tabuleiro
        no = sala.estudo.no
        primeiro: chess.pgn.GameNode | None = None
        for san in melhor.pv_san:
            try:
                lance = tabuleiro.parse_san(san)
            except ValueError:  # pragma: no cover - a linha veio do motor sobre esta posição
                break
            existente = next((filho for filho in no.variations if filho.move == lance), None)
            no = existente if existente is not None else no.add_variation(lance)
            primeiro = primeiro or no
            tabuleiro.push(lance)
        if primeiro is None:
            sala.set_status("O motor não deu lance jogável nesta posição.")
            return
        if not primeiro.starting_comment:
            primeiro.starting_comment = f"{self._analyzer.path.name}: {melhor.display()}"
        sala.refresh()
        sala._marcar_sujo()
        sala.set_status(f"Linha do motor na árvore: {' '.join(melhor.pv_san)}")

    # ------------------------------------------- a partida inteira pelo motor (S-537)

    def analisar_partida(self) -> AnalisadorDaPartida | None:
        """Passa a linha principal pelo motor, grava a avaliação e marca os erros (S-537).

        **É a pergunta do dia seguinte ao torneio**: *em que lance eu perdi?* A sala sabia avaliar
        uma posição desde a S-33 e gravar o número no lance desde a S-285; o que faltava era a
        passada inteira e a leitura dela em uma tela.

        Devolve a rodada, para o teste esperá-la. Quem decide profundidade é o diálogo; quem
        classifica e desenha é `ui/analise_da_partida.py` e `qt/analise_da_partida.py`.
        """
        from chess_diagram_ocr.qt import analise_da_partida as qt_analise

        sala = self._sala
        if self._analyzer is None:
            sala.set_status(strings.SEM_MOTOR_STATUS)
            return None
        if self._analise_da_partida is not None and self._analise_da_partida.ocupado:
            sala.set_status("A partida já está sendo analisada.")
            return None
        _fens, passos = analise_declarada.percurso(sala.estudo.jogo)
        if not passos:
            sala.set_status("Não há lance na linha principal para analisar.")
            return None
        pedido = qt_analise.DialogoDaProfundidade(sala, lances=len(passos))
        if pedido.exec() != QDialog.DialogCode.Accepted:
            return None
        rodada = qt_analise.analisar_com_dialogo(
            sala,
            analisador=self._analyzer,
            jogo=sala.estudo.jogo,
            profundidade=pedido.profundidade(),
            busy=self._busy,
        )
        rodada.terminou.connect(self._chegou_a_analise_da_partida)
        rodada.falhou.connect(lambda mensagem, _erro: sala.set_status(f"A análise da partida falhou: {mensagem}"))
        self._analise_da_partida = rodada
        return rodada

    def _chegou_a_analise_da_partida(self, avaliados: Any) -> JanelaDaAnalise | None:
        """Grava `[%eval]` e o símbolo em cada lance, e abre o relatório (S-537).

        **O símbolo é NAG e não cor de tela**, e é o que faz a análise sobreviver ao arquivo: um
        `??` gravado como `$4` aparece na lista de lances pelo caminho que já existe, vai para o
        PGN e é lido por qualquer programa de xadrez. Uma marca só de tela morreria ao fechar.

        `_marcar_sujo` uma vez no fim, e não por lance: quarenta chamadas empilhariam quarenta
        passos de desfazer para uma operação que a pessoa mandou fazer uma vez.
        """
        from chess_diagram_ocr.qt import analise_da_partida as qt_analise

        sala = self._sala
        cancelada = bool(self._analise_da_partida is not None and self._analise_da_partida.cancelada)
        marcados = self._marcar_os_lances(avaliados)
        sala.refresh()
        if avaliados:
            sala._marcar_sujo(historico=False, da_maquina=True)
        sala.set_status(analise_declarada.frase_final(len(avaliados or []), marcados, cancelado=cancelada))
        if not avaliados:
            return None
        return qt_analise.JanelaDaAnalise(sala, avaliados, ir_para=sala.ir_para_o_ply)

    def _marcar_os_lances(self, avaliados: Any) -> int:
        """Escreve a avaliação e o símbolo nos nós da linha principal. Devolve quantos ganharam
        símbolo.

        O casamento é **por posição na linha principal**, e não por nó guardado: a árvore pode ter
        mudado enquanto o motor pensava, e um nó guardado apontaria para um lance que saiu dela.

        **A posição já matada não recebe `[%eval]`** (S-537): o UCI responde `score mate 0` ali, o
        `engine` normaliza para `±1` -- que a barra precisa --, e o que saía no arquivo era um
        `[%eval #1]` numa posição em que o mate **já aconteceu**. Quem decide é `grava_avaliacao`.

        O que se pula é a **avaliação**, e não o nó: a posição que acaba a partida também pode ser
        um afogamento, e afogar no lugar de matar é justamente o `??` que esta passada existe para
        achar. O símbolo continua sendo escrito, e é do símbolo que a análise vive.
        """
        no: Any = self._sala.estudo.raiz
        marcados = 0
        for lance in avaliados or []:
            if not no.variations:
                break
            no = no.variations[0]
            if analise_declarada.grava_avaliacao(lance):
                pontuacao = (
                    chess.engine.Mate(lance.mate_em)
                    if lance.mate_em is not None
                    else chess.engine.Cp(int(lance.centipeoes))
                )
                no.set_eval(chess.engine.PovScore(pontuacao, chess.WHITE))
            codigo = analise_declarada.NAG_DE_JUIZO.get(lance.juizo)
            if codigo is not None:
                no.nags = estudo_mod.alternar_nag(set(no.nags) - {codigo}, codigo)
                marcados += 1
        return marcados

    # ----------------------------------------- as opções do motor, sem reiniciar (S-536)

    def _opcoes_do_motor(self) -> EngineSettings:
        """As preferências do motor como estão no disco. Arquivo ausente dá os padrões (S-32)."""
        return load_settings(self._caminho_das_preferencias).engine

    def opcoes_do_motor(self) -> QDialog | None:
        """Abre o formulário das opções do motor e aplica o que ele devolver (S-536).

        **Existe com e sem motor**, e é a única ação do grupo Motor que existe sem: numa máquina em
        que a procura automática não achou binário nenhum, este é o caminho para dizer onde ele
        está -- e escondê-lo justamente ali seria escondê-lo de quem precisa dele.

        A gravação é atômica e vale para a próxima sessão; a aplicação é imediata e não reinicia
        nada. Quem sabe o que cada mudança faz com o processo é `plano_de_aplicacao`.
        """
        from chess_diagram_ocr.qt.preferencias import DialogoDoMotor

        antes = self._opcoes_do_motor()
        dialogo = DialogoDoMotor(self._sala, opcoes=antes)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return dialogo
        self.aplicar_opcoes_do_motor(antes, dialogo.valores())
        return dialogo

    def aplicar_opcoes_do_motor(self, antes: EngineSettings, depois: EngineSettings) -> Any:
        """Grava as preferências e põe o motor de acordo, fora da linha de eventos (S-536).

        Separada de `opcoes_do_motor` porque é a parte afirmável sem abrir diálogo -- e porque é
        ela que a fotografia e o teste exercitam.
        """
        from chess_diagram_ocr.qt.preferencias import MotorVivo

        leitura = ler_arquivo(self._caminho_das_preferencias)
        self._recusa_das_preferencias = ""
        try:
            arquivo = leitura.valor
            save_settings(gravavel(leitura).com(arquivo.com(replace(arquivo.preferencias, engine=depois))))
        except GravacaoRecusada as recusa:
            # Vale em memória e não vai para o disco (S-812). A frase sai junto com a do motor
            # aplicado, que chega depois e cobriria esta.
            self._recusa_das_preferencias = str(recusa)
            self._sala.set_status(self._recusa_das_preferencias)
        except OSError as erro:  # pragma: no cover - disco cheio ou pasta somente leitura
            logger.warning("As preferências do motor não puderam ser gravadas: %s", erro)
        # O leitor de finais é reaberto na próxima consulta: a pasta pode ter mudado.
        if self._finais is not None:
            self._finais.close()
            self._finais = None
        if self._motor_vivo is None:
            self._motor_vivo = MotorVivo(self._sala, analisador=self._analyzer)
            self._motor_vivo.aplicado.connect(self._motor_aplicado)
            self._motor_vivo.falhou.connect(lambda mensagem, _erro: self._motor_aplicado(None, mensagem))
        self._motor_vivo.aplicar(antes, depois)
        return self._motor_vivo

    def _motor_aplicado(self, motor: Any, frase: str) -> None:
        self.trocar_de_motor(motor)
        self._sala.set_status(" ".join(parte for parte in (frase, self._recusa_das_preferencias) if parte))

    def trocar_de_motor(self, novo: EngineAnalyzer | None) -> None:
        """Troca o motor da sala e acomoda a tela ao que passou a existir (S-536).

        **Três casos, e só o terceiro custa alguma coisa.** Trocar um motor por outro é atualizar
        o título da seção -- o objeto muitas vezes é o mesmo, com outro binário dentro. Perder o
        motor esconde a seção e a barra lateral, como se ele nunca tivesse existido (S-33). Ganhar
        um motor numa sala que abriu sem nenhum é o caso que obriga a montar a seção agora e a
        **remontar a fila**: uma `QAction` não muda de barra depois de criada, e sem a remontagem o
        grupo Motor continuaria ausente até a próxima abertura -- que é o "reiniciar" que este item
        veio tirar.

        A barra lateral **não** nasce depois: ela mora dentro do arranjo da coluna do tabuleiro, e
        recriá-lo mexeria na repartição que a S-551 calcula. A promessa da S-536 é o motor sem
        reiniciar; a barra chega junto com ele na abertura seguinte, e a seção já mostra tudo.
        """
        sala = self._sala
        tinha = self._analyzer is not None
        self._analyzer = novo
        if novo is None and tinha:
            sala.btn_continua = None
            self.caixa_do_motor.hide()
        elif novo is not None and tinha:
            # O motor que a troca entrega já está aberto (`MotorVivo` chama `start`), então aqui o
            # título sai com o nome UCI e não com o do binário.
            self._mostrar_o_titulo_do_motor()
            self.caixa_do_motor.show()
        elif novo is not None and not tinha:
            self.montar_secao(sala.divisor_vertical)
        if (novo is not None) != tinha:
            sala._remontar_a_barra()
        sala.refresh()
