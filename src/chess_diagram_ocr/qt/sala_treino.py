"""O treino da sala de estudo: o lance cobrado, o placar, as táticas e a agenda (S-866).

**Saiu de `qt/painel_de_estudo.py` com os quatro atributos que só ele usava** -- a leitura do placar,
o medidor do custo do lance errado, a extração de táticas em curso e a janela de treino aberta -- e
com a pasta onde os três arquivos de treino moram (S-539 a S-541).

**O que é do painel continua no painel.** O interruptor do modo é uma `QAction` da barra da sala, o
placar é escrito num rótulo da faixa sob o tabuleiro, e o corte da lista de lances é do desenho da
lista: esta classe decide o veredicto e grava, e o painel mostra.
"""

from __future__ import annotations

import logging
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

import chess
from PyQt6.QtCore import QObject

from chess_diagram_ocr import placar as placar_mod
from chess_diagram_ocr import revisao_arquivo, taticas_arquivo
from chess_diagram_ocr.arquivo_do_dono import GravacaoRecusada, Leitura, Lida, gravavel
from chess_diagram_ocr.config import DATA_DIR
from chess_diagram_ocr.ui import comandos, treino_declarado
from chess_diagram_ocr.ui.busy import BusyRegistry

if TYPE_CHECKING:
    from chess_diagram_ocr.qt.painel_de_estudo import PainelDeEstudo
    from chess_diagram_ocr.qt.painel_de_treino import ExtratorDeTaticas, JanelaDeTreino

logger = logging.getLogger(__name__)

DADOS = DATA_DIR
"""Onde os arquivos de trabalho do treino moram por omissão (S-539 a S-541). Ver `pasta_de_treino`
no construtor do painel: o padrão é este, e o teste passa outro."""

__all__ = ["DADOS", "TreinoDaSala"]


class TreinoDaSala(QObject):
    """O modo de treino da sala, o placar dele, e as táticas do livro com a agenda de revisão."""

    def __init__(self, sala: PainelDeEstudo, *, pasta_de_treino: Path | None, busy: BusyRegistry | None) -> None:
        super().__init__(sala)
        self._sala = sala
        self._busy = busy
        self._pasta_de_treino = Path(pasta_de_treino) if pasta_de_treino is not None else DADOS
        """Onde moram a coleção de táticas, o baralho de revisão e o placar (S-539 a S-541).

        **Um argumento e não três**, e ele existe pelo motivo dos outros caminhos do painel: o
        teste não pode escrever no `data/` do repositório. O produto usa o padrão, e a janela não
        precisa passar nada -- é o que mantém `qt/janela.py` do tamanho que a catraca exige."""
        self._leitura_do_placar: Leitura[placar_mod.Placar] | None = None
        """O placar do treino, lido do disco no primeiro uso. Ver a propriedade `placar`."""
        self._perda_do_lance: Any = None
        """O medidor do custo do lance errado (S-541), criado no primeiro erro."""
        self._extrator: ExtratorDeTaticas | None = None
        """A extração de táticas em curso, guardada porque um `QObject` sem referência é recolhido
        com a thread dentro."""
        self._treino: JanelaDeTreino | None = None
        """A janela de treino aberta (S-540). Não modal, e guardada pela mesma razão."""

    # ----------------------------------------------------------- treinar (S-290/S-541)

    def alternar_treino(self) -> None:
        """Liga e desliga o modo de treino: a linha some, e o tabuleiro cobra o lance.

        **A sessão zera aqui, e o placar do livro não** (S-541). Até a S-541 os dois contadores
        eram os mesmos, e desligar o treino -- que é o gesto declarado para guardar um lance que se
        quis jogar -- apagava a tarde inteira. Agora o que zera é a sessão; o que o livro acumulou
        está no disco desde o primeiro lance.
        """
        sala = self._sala
        sala.btn_treino.setChecked(not sala.btn_treino.isChecked())
        sala.btn_treino.setText(
            comandos.rotulo_alternado("modo_treino")
            if sala.btn_treino.isChecked()
            else comandos.rotulo_de_botao("modo_treino")
        )
        self.placar.zerar_sessao()
        sala.refresh()
        if sala.btn_treino.isChecked():
            sala.set_status("Treino: jogue o lance da linha. O que vem depois está escondido.")
        else:
            sala.set_status("Treino desligado.")

    @property
    def placar(self) -> placar_mod.Placar:
        """O placar do treino, lido do disco na primeira vez que alguém treina (S-541).

        Preguiçoso porque a sala é montada em toda janela e em dezenas de testes, e nenhum deles
        treina: carregar o `placar.json` no `__init__` faria toda montagem tocar o disco por causa
        de uma frase que quase nunca aparece.
        """
        if self._leitura_do_placar is None:
            self._leitura_do_placar = placar_mod.carregar(caminho=self._caminho_do_placar())
        return self._leitura_do_placar.valor

    def _gravar_o_placar(self, _placar: placar_mod.Placar | None = None) -> None:
        """Grava o placar sobre o arquivo de onde ele veio -- e só se ele leu (S-812).

        O argumento é o que a janela de treino passa; ele é sempre o mesmo objeto de `placar`.
        """
        if self._leitura_do_placar is None:
            return
        try:
            placar_mod.gravar(gravavel(self._leitura_do_placar))
        except GravacaoRecusada as recusa:
            self._sala.set_status(str(recusa))
        except OSError as erro:  # pragma: no cover - disco cheio ou arquivo em uso
            logger.warning("O placar do treino não pôde ser gravado: %s", erro)

    def _caminho_do_placar(self) -> Path:
        return self._pasta_de_treino / placar_mod.CAMINHO_PADRAO.name

    def _livro(self) -> str:
        """O livro do estudo aberto, ou o da sala: é a chave do placar e da extração."""
        return self._sala.estudo.ancora.documento or self._sala.sala.documento

    def mostrar_placar(self) -> None:
        sala = self._sala
        if not sala.btn_treino.isChecked() or self._leitura_do_placar is None:
            sala.navegacao.lbl_placar.setText("")
            return
        sala.navegacao.lbl_placar.setText(
            treino_declarado.frase_do_placar(self.placar.sessao, self.placar.do_livro(self._livro()))
        )

    def treinar(self, move: chess.Move) -> None:
        """Um lance jogado com o treino ligado. **A árvore não muda** (S-290/S-541).

        O gabarito é o nó seguinte da linha, e ele já está lá: o estudo tem tudo de que o treino
        precisa. **Errar não cria variante**, e o caminho de guardar o lance é declarado na própria
        frase: desligar o treino.

        **O veredicto chega na hora e o preço chega depois** (S-541). Se o lance é o da linha, não
        há nada a perguntar. Se não é, ele ainda pode valer o mesmo -- e responder isso custa duas
        buscas do motor, que não cabem na linha de eventos. A frase do rodapé é escrita duas vezes:
        uma dizendo que o lance não é o da linha, outra dizendo quanto ele custou. Sem motor, a
        primeira é a única, e ela continua sendo verdade.
        """
        sala = self._sala
        esperado = sala.estudo.no.variations[0] if sala.estudo.no.variations else None
        if esperado is None:
            sala.set_status("Fim da linha: não há lance a adivinhar aqui.")
            return
        antes = sala.estudo.tabuleiro.copy(stack=False)
        jogado = antes.san(move)
        gabarito = antes.san(esperado.move)
        if move == esperado.move:
            sala.estudo.no = esperado
            sala.refresh()
            self._contar_no_treino(treino_declarado.classificar_o_lance(jogado, gabarito), jogado, gabarito)
            return
        # **O redesenho desfaz o lance na tela.** O modelo do tabuleiro jogou sobre a cópia dele, e
        # sem isto a pessoa fica olhando uma posição que a árvore não tem -- o defeito que a S-290
        # deixou passar porque o caminho de erro não redesenhava nada.
        sala.refresh()
        if not self._medidor_da_perda().pedir(antes, move, (jogado, gabarito, bool(antes.turn))):
            self._contar_no_treino(treino_declarado.classificar_o_lance(jogado, gabarito), jogado, gabarito)
            return
        sala.set_status(f"{jogado} não é o lance da linha: perguntando ao motor quanto custou…")

    def _medidor_da_perda(self) -> Any:
        """O `PerdaDoLance` da sala, criado no primeiro erro. `pedir` recusa sem motor (S-541)."""
        if self._perda_do_lance is None:
            from chess_diagram_ocr.qt.painel_de_treino import PerdaDoLance

            self._perda_do_lance = PerdaDoLance(self._sala, analisador=self._sala.motor.analisador)
            self._perda_do_lance.pronta.connect(self._chegou_a_perda)
            self._perda_do_lance.falhou.connect(self._nao_veio_a_perda)
        return self._perda_do_lance

    def _chegou_a_perda(self, ficha: Any, antes: int, depois: int) -> None:
        jogado, gabarito, brancas = ficha
        julgamento = treino_declarado.classificar_o_lance(
            jogado, gabarito, antes=int(antes), depois=int(depois), brancas=bool(brancas)
        )
        self._contar_no_treino(julgamento, jogado, gabarito)

    def _nao_veio_a_perda(self, ficha: Any, _mensagem: str) -> None:
        jogado, gabarito, _brancas = ficha
        self._contar_no_treino(treino_declarado.classificar_o_lance(jogado, gabarito), jogado, gabarito)

    def _contar_no_treino(self, julgamento: Any, jogado: str, gabarito: str) -> None:
        """Conta o lance nos dois placares e grava o do livro **agora** (S-541).

        Uma gravação por lance e não por sessão, ao contrário do baralho de revisão: o arquivo tem
        uma linha por livro e alguns bytes, e o que se perde numa queda é justamente a sessão que
        ninguém vai repetir. É a decisão inversa da de `qt/painel_de_treino.JanelaDeTreino`, e a
        diferença é o tamanho do que se grava.
        """
        self.placar.registrar(self._livro(), julgamento.resultado, perda=julgamento.perda)
        self.mostrar_placar()
        self._sala.set_status(treino_declarado.frase_do_resultado(julgamento, jogado, gabarito))
        self._gravar_o_placar()

    # -------------------------------------------------- táticas e agenda (S-539/S-540)

    def extrair_taticas(self) -> ExtratorDeTaticas | None:
        """Casa os diagramas deste livro com a solução impressa e grava a coleção (S-539).

        **O livro é o da sala, e não um `filedialog`.** A sala já está aberta sobre um diagrama
        dele, a aba de texto já leu folhas dele, e perguntar de novo qual é o arquivo seria
        desconhecer o que a janela inteira está mostrando.

        A varredura carrega o classificador por conta própria, do caminho padrão -- é o mesmo que
        `cvoff-scan` faz, e é o preço de a extração rodar fora do `OcrService` (que está sob o lock
        da S-31 servindo à página exibida). Dezessete megabytes de modelo por alguns minutos.
        """
        from chess_diagram_ocr.qt import painel_de_treino

        sala = self._sala
        livro = self._livro()
        if not livro or not Path(livro).exists():
            sala.set_status("Abra um livro na sala antes de extrair as táticas dele.")
            return None
        if self._extrator is not None and self._extrator.ocupado:
            sala.set_status("A extração de táticas deste livro já está em curso.")
            return None
        rodada = painel_de_treino.extrair_com_dialogo(
            sala, Path(livro), analisador=sala.motor.analisador, busy=self._busy
        )
        rodada.terminou.connect(partial(self._chegaram_as_taticas, str(livro)))
        rodada.falhou.connect(lambda mensagem, _e: sala.set_status(f"A extração falhou: {mensagem}"))
        self._extrator = rodada
        return rodada

    def _chegaram_as_taticas(self, livro: str, extracao: Any) -> None:
        """Grava o que a extração achou e diz o número -- inclusive quando ele é ruim."""
        if extracao is None:
            self._sala.set_status("Extração de táticas cancelada.")
            return
        try:
            taticas_arquivo.gravar(livro, extracao.exercicios, pasta=self._pasta_das_taticas())
        except OSError as erro:
            self._sala.set_status(f"Os exercícios não puderam ser gravados: {erro}")
            return
        self._sala.set_status(extracao.resumo())

    def _pasta_das_taticas(self) -> Path:
        return self._pasta_de_treino / taticas_arquivo.PASTA_PADRAO.name

    def _caminho_da_revisao(self) -> Path:
        return self._pasta_de_treino / revisao_arquivo.CAMINHO_PADRAO.name

    def _gravar_o_baralho(
        self, leitura: Leitura[revisao_arquivo.BaralhoDoArquivo], baralho: revisao_arquivo.Baralho
    ) -> None:
        """A gravação que a janela de treino chama ao fechar. Método e não `lambda`: um `lambda`
        não tem nome para o critério de aceite citar, e a S-546 já registrou o argumento.

        Grava sobre a leitura de onde o baralho veio, e só se ela leu (S-812), com os itens que não
        leram de volta ao lado (S-813)."""
        try:
            lida = gravavel(leitura)
            revisao_arquivo.gravar(lida.com(lida.valor.com(baralho)))
        except GravacaoRecusada as recusa:
            self._sala.set_status(str(recusa))

    def treinar_a_agenda(self) -> JanelaDeTreino | None:
        """Abre a fila de hoje da repetição espaçada (S-540).

        Sem exercício nenhum extraído, a janela **não abre**: uma tela de treino vazia não diz o
        que fazer, e a frase diz -- o comando que a preenche está ao lado, no mesmo menu.
        """
        from chess_diagram_ocr.qt.painel_de_treino import JanelaDeTreino

        sala = self._sala
        exercicios = taticas_arquivo.carregar_tudo(pasta=self._pasta_das_taticas())
        if not exercicios:
            sala.set_status(
                'Não há exercício extraído ainda. Use "Táticas do livro" com um livro aberto.'
            )
            return None
        leitura = revisao_arquivo.carregar(caminho=self._caminho_da_revisao())
        if not isinstance(leitura, Lida):
            sala.set_status(leitura.mensagem)
        janela = JanelaDeTreino(
            sala,
            exercicios=exercicios,
            baralho=leitura.valor.estados,
            placar=self.placar,
            analisador=sala.motor.analisador,
            gravar=partial(self._gravar_o_baralho, leitura),
            gravar_placar=self._gravar_o_placar,
        )
        janela.fechada.connect(self.mostrar_placar)
        self._treino = janela
        janela.show()
        return janela
