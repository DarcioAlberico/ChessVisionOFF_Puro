"""As partidas da base, vistas da sala de estudo: posição, busca, árvore e índice (S-866).

**Saiu de `qt/painel_de_estudo.py` com o estado que só ele usava.** As três perguntas à base -- que
partidas passam por esta posição (S-287), quais respondem a um formulário (S-533) e o que se joga
daqui (S-535) -- e as duas passadas que as tornam possíveis, o índice por nome (S-532) e a árvore de
aberturas, guardavam no painel cinco atributos que nenhum outro método lia: os dois diálogos
reusados, as duas rodadas em curso e o cache de posições aberto.

**Os diálogos e as rodadas são guardados, e a razão é a mesma para os quatro.** Um `QObject` sem
referência é recolhido com a thread dentro, e destruir um diálogo não modal para abrir o segundo
destruiria um `QThread` em curso -- que derruba o processo sem exceção. As rodadas são `Tarefa`s sem
pai, seguras por `manter_viva` nos módulos que as constroem (S-826).

**O que é da sala continua na sala.** Abrir a partida escolhida passa pela pergunta de abandono e
pela troca de estudo do painel, e jogar o lance da árvore é o `push_move` dele: esta classe pergunta
à base e entrega a resposta, e quem mexe na mesa é o painel.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import chess
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from chess_diagram_ocr import estudo as estudo_mod
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.vazio import EstadoVazio
from chess_diagram_ocr.ui import espaco, strings, tokens
from chess_diagram_ocr.ui.busy import BusyRegistry

if TYPE_CHECKING:
    from chess_diagram_ocr.qt.painel_de_estudo import PainelDeEstudo

__all__ = ["PartidasDaBase"]


class PartidasDaBase(QObject):
    """O que a sala pergunta à base de partidas do usuário, e as passadas que a preparam."""

    def __init__(
        self,
        sala: PainelDeEstudo,
        *,
        bases: Callable[[], Sequence[Path]],
        caminho_do_cache: Path | None,
        busy: BusyRegistry | None,
    ) -> None:
        super().__init__(sala)
        self._sala = sala
        self._bases = bases
        self._caminho_do_cache = caminho_do_cache
        """Onde o cache de posições da base mora. `None` é o padrão do produto,
        `data/games_positions.sqlite`.

        **Existe pela mesma razão do `pasta_da_galeria` e do `caminho_do_estado`** (S-415): sem
        ele, um teste que chegue a `_loja_de_posicoes` cria o arquivo no `data/` de quem roda a
        suíte -- e a guarda de sessão do `conftest` acusa a rodada inteira, num teste que não é o
        culpado. Foi a CI que pegou este, e não a máquina de ninguém: aqui o arquivo já existia
        de uso normal, e a guarda não tinha o que reportar."""
        self._busy = busy
        """O registro de operações longas da janela, para o índice da base (S-532) aparecer no rodapé
        como as outras. Sem ele, a janela que nos contém pode tê-lo: ver `_busy_da_janela`."""
        self._indexador: Any = None
        """A rodada do índice em curso -- guardada porque um `QObject` sem referência é recolhido
        com a thread dentro (`qt/indice_da_base.py`)."""
        self._busca: Any = None
        """O diálogo de busca (S-533), guardado e **reusado**: ele não é modal, tem uma thread
        dentro, e abrir o segundo enquanto o primeiro procura destruiria um `QThread` em curso."""
        self._arvore: Any = None
        """A janela da árvore de aberturas (S-535), guardada e reusada pela mesma razão -- e mais
        uma: ela **acompanha** a posição da sala a cada `refresh`, então destruí-la e recriá-la a
        cada abertura descartaria a consulta em curso a cada lance."""
        self._construtor_da_arvore: Any = None
        """A passada que constrói a árvore, guardada porque um `QObject` sem referência é recolhido
        com a thread dentro -- a mesma razão de `_indexador`."""
        self._loja: Any = None

    def _bases_ou_aviso(self, frase: str) -> tuple[Path, ...]:
        """As bases que a sala já consulta (`bases_de_partidas`) ou, sem elas, a pasta padrão
        (`database_paths`). Vazio diz `frase` no rodapé, e quem chamou desiste."""
        from chess_diagram_ocr.games_db import database_paths

        bases = tuple(self._bases()) or tuple(database_paths())
        if not bases:
            self._sala.set_status(frase)
        return bases

    def _busy_da_janela(self) -> BusyRegistry | None:
        """O `busy` da janela quando ela o passou; senão, o que a janela que nos contém tiver -- é o
        mesmo registro, e uma segunda rodada em curso é recusada por quem a roda."""
        return self._busy if self._busy is not None else getattr(self._sala.window(), "busy", None)

    def acompanhar(self, tabuleiro: chess.Board) -> None:
        """A árvore de aberturas acompanha a posição (S-535), chamada pelo `refresh` do painel.

        Ali, e não em cada método de navegação, porque `refresh` é o único ponto por onde toda
        mudança de nó passa. Fechada, ela não custa nada -- e a consulta em curso não é atropelada:
        `definir_posicao` guarda o pedido e o refaz quando a thread volta.
        """
        if self._arvore is not None and self._arvore.isVisible():
            self._arvore.definir_posicao(tabuleiro)

    # ------------------------------------------------- as partidas da base (S-287)

    def partidas_da_posicao(self) -> QDialog | None:
        """Que partidas da base do usuário chegam a esta posição.

        **Lê o cache, não a base**, e o motivo está em `estudo_partidas`: reproduzir os lances da
        base inteira custa ~104 min em dez processos, e o custo é da passada e não da posição.
        Quando a posição nunca foi perguntada, a resposta diz **isso** em vez de dizer "nenhuma
        partida" -- que seria um número sobre uma pergunta que ninguém fez.

        O `import` mora aqui e não no topo: `games_cache` alcança `games_db` e `pdf_text`, e a aba
        é construída na abertura da janela.
        """
        from chess_diagram_ocr import estudo_partidas

        resposta = estudo_partidas.consultar(
            self._loja_de_posicoes(), self._sala.estudo.tabuleiro.board_fen(), bases=tuple(self._bases())
        )
        self._sala.set_status(resposta.frase)
        if not resposta.achou:
            return None
        return _JanelaDePartidas(self._sala, resposta)

    def buscar_partidas(self) -> QDialog | None:
        """Abre o formulário de busca sobre o índice por nome (S-533).

        **A outra pergunta.** `partidas_da_posicao` responde pela posição que está no tabuleiro, e
        só por ela -- e lê o cache, que só conhece o que já foi perguntado. Esta pergunta não nasce
        do tabuleiro: *as partidas de Carlsen em 2019 com Elo acima de 2700 na Najdorf*. Quem
        responde é `games_index.buscar`, e a posição corrente entra como filtro **opcional**.

        O diálogo é guardado e reusado: ele não é modal e tem uma `Tarefa` dentro, e destruir o
        primeiro para abrir o segundo destruiria um `QThread` em curso -- que derruba o processo
        sem exceção. Reabrir só atualiza a posição, que é a única coisa dele que envelhece.
        """
        from chess_diagram_ocr.qt import busca_de_partidas as qt_busca

        if self._busca is None:
            bases = self._bases_ou_aviso("Não há base de partidas (.pgn) para procurar.")
            if not bases:
                return None
            dialogo = qt_busca.DialogoDeBusca(self._sala.window(), bases=bases)
            dialogo.partida_escolhida.connect(self.abrir_partida_da_base)
            dialogo.indice_pedido.connect(self.indexar_base)
            self._busca = dialogo
        self._busca.definir_posicao(self._sala.estudo.tabuleiro.board_fen())
        self._busca.show()
        self._busca.raise_()
        return self._busca

    def arvore_de_aberturas(self) -> QDialog | None:
        """A árvore de aberturas da posição corrente: que lances a base joga daqui (S-535).

        **A terceira pergunta à base, e ela é a de quem estuda uma abertura.**
        `partidas_da_posicao` diz *quais* partidas passam por aqui (e só sabe o que já foi
        perguntado, pelo cache); `buscar_partidas` responde a um formulário de seis campos. Esta
        responde *o que se joga daqui*, com o número de partidas, o resultado, o Elo e o ano de
        cada lance -- e ela lê um índice por **posição**, que é o que a S-535 construiu.

        O diálogo é guardado e reusado pelas razões de `buscar_partidas`, e mais uma: ele segue a
        posição da sala a cada `refresh`.
        """
        from chess_diagram_ocr.qt import arvore_de_aberturas as qt_arvore

        if self._arvore is None:
            bases = self._bases_ou_aviso("Não há base de partidas (.pgn) para a árvore de aberturas.")
            if not bases:
                return None
            dialogo = qt_arvore.DialogoDaArvore(self._sala.window(), bases=bases)
            dialogo.lance_escolhido.connect(self.jogar_da_arvore)
            dialogo.partidas_pedidas.connect(self.partidas_da_arvore)
            dialogo.construcao_pedida.connect(self.construir_a_arvore)
            self._arvore = dialogo
        self._arvore.definir_posicao(self._sala.estudo.tabuleiro)
        self._arvore.show()
        self._arvore.raise_()
        return self._arvore

    def jogar_da_arvore(self, san: str) -> bool:
        """Joga na árvore de estudo o lance escolhido na árvore de aberturas. Devolve se jogou.

        **Reinterpreta o SAN no tabuleiro da sala**, e não recebe um `chess.Move`: o lance veio de
        uma consulta que rodou numa thread sobre uma cópia, e um `Move` daquela cópia é um par de
        casas sem dono. Ilegal aqui quer dizer que a posição andou entre a consulta e o clique --
        a frase diz isso em vez de jogar outra coisa.

        Quem redesenha a árvore de aberturas é o `refresh` de `push_move`, e não esta função: a
        posição mudaria pelas setas do teclado do mesmo jeito.
        """
        try:
            lance = self._sala.estudo.tabuleiro.parse_san(san)
        except (ValueError, AssertionError):
            self._sala.set_status(f"{san} não é um lance legal na posição que está no tabuleiro agora.")
            return False
        self._sala.push_move(lance)
        return True

    def partidas_da_arvore(self, filtro: Any) -> Any:
        """Abre a busca da S-533 já preenchida com a posição da árvore e o ECO dela.

        É o "mesmo gesto da busca" que o item pede: a lista de partidas que chegam a esta posição
        é a tabela que já existe, com a paginação e a thread que já existem -- e não uma segunda
        lista de partidas neste programa.
        """
        # `Any` e nao `DialogoDeBusca`: o tipo concreto so existe atras do `import` tardio de
        # `buscar_partidas` -- nomea-lo aqui traria o PyQt do dialogo para o topo deste arquivo.
        dialogo: Any = self.buscar_partidas()
        if dialogo is not None:
            dialogo.aplicar_filtro(filtro)
        return dialogo

    def construir_a_arvore(self) -> Any:
        """Constrói a árvore de aberturas com barra e Cancelar, sem sair da janela (S-535).

        A forma é a de `indexar_base` (S-532) e pela mesma razão: a saída de "o arquivo não existe"
        tem de ser um comando da janela e não uma frase mandando abrir um terminal. A diferença é
        o que o cancelamento custa -- aqui a passada inteira é descartada, porque meia árvore dá
        percentagem sobre a metade que se leu, e ela pareceria certa.
        """
        from chess_diagram_ocr.qt import arvore_de_aberturas as qt_arvore

        sala = self._sala
        if self._construtor_da_arvore is not None and self._construtor_da_arvore.ocupado:
            sala.set_status("A árvore de aberturas já está sendo construída.")
            return None
        bases = self._bases_ou_aviso("Não há base de partidas (.pgn) para construir a árvore.")
        if not bases:
            return None
        construtor = qt_arvore.construir_com_dialogo(sala.window(), bases, busy=self._busy_da_janela())
        construtor.terminou.connect(lambda feito: sala.set_status(qt_arvore.frase_final(feito)))
        construtor.falhou.connect(
            lambda mensagem, _excecao: sala.set_status(f"A árvore de aberturas falhou: {mensagem}")
        )
        self._construtor_da_arvore = construtor
        return construtor

    def abrir_partida_da_base(self, caminho: Any, offset: int) -> bool:
        """Põe na mesa a partida que a busca escolheu, lida direto do byte dela (S-533).

        **É o que o índice existe para permitir**: `Achado` guarda em que arquivo e em que byte a
        partida começa, e ler dali custa um `seek` -- não a passada de minutos que a busca por
        posição paga. Se a leitura não devolver partida, o índice está adiantado em relação ao
        arquivo (alguém reescreveu o `.pgn`), e a frase diz isso em vez de abrir meia partida.

        O estudo aberto é guardado na sala antes da troca, como em `_aceitar_colado`: escolher uma
        partida na lista não pode custar a análise que estava na mesa.
        """
        from chess_diagram_ocr import estudo_partidas, games_index

        sala = self._sala
        partida = games_index.partida_em(Path(caminho), int(offset))
        if partida is None or not partida.movetext:
            sala.set_status(
                "A partida escolhida não foi encontrada onde o índice diz que ela está. "
                "Refaça o índice: a base mudou depois da última rodada."
            )
            return False
        novo, motivo = estudo_mod.colar(estudo_partidas.como_pgn(partida))
        if novo is None:
            sala.set_status(f"A partida escolhida não pôde ser lida: {motivo}")
            return False
        if not sala._confirmar_abandono("abrir a partida escolhida na busca"):
            return False
        sala.seguir_ocr.setChecked(False)
        sala.sala.guardar(sala.estudo)
        nomes = f"{partida.headers.get('White', '?')} - {partida.headers.get('Black', '?')}"
        sala._trocar_de_estudo(novo, f"Base: {nomes}")
        sala.set_status(f"{nomes}: {novo.contagem_de_lances()} lance(s) da base.")
        return True

    def indexar_base(self) -> None:
        """Constrói o índice por nome da base, com barra e Cancelar, sem sair da janela (S-532).

        **A fiação que a S-532 deixou pendente**: o indexador existia e ninguém o chamava -- a janela
        continuava mandando abrir um terminal. A ação mora no grupo Base da barra da sala (dentro do
        "Mais": indexa-se uma vez por torneio acrescentado) e no menu Estudo, pelo catálogo.

        As bases e o `busy` saem de `_bases_ou_aviso` e `_busy_da_janela`; uma segunda rodada em
        curso é recusada pelo indexador. A frase final vai para `set_status`, que é o rodapé da aba
        **e** o da janela.
        """
        from chess_diagram_ocr.qt import indice_da_base

        sala = self._sala
        if self._indexador is not None and self._indexador.ocupado:
            sala.set_status("O índice da base já está sendo construído.")
            return
        bases = self._bases_ou_aviso("Não há base de partidas (.pgn) para indexar.")
        if not bases:
            return
        indexador = indice_da_base.indexar_com_dialogo(sala.window(), bases, busy=self._busy_da_janela())
        indexador.terminou.connect(lambda resultado: sala.set_status(indice_da_base.frase_final(resultado)))
        indexador.falhou.connect(lambda mensagem, _excecao: sala.set_status(f"O índice da base falhou: {mensagem}"))
        self._indexador = indexador

    def _loja_de_posicoes(self) -> Any:
        """O cache de posições, aberto uma vez e mantido. `None` quando não há base.

        `open_store` nunca levanta por causa do disco (é decisão dele), então o `None` daqui só
        significa uma coisa: não há PGN em `pgn_database/` para o cache falar a respeito.

        **A sala só lê o cache (S-806)**: abre com `somente_leitura`, e não cria o arquivo. Sem
        arquivo, a loja é a vazia em memória, e é trocada pela do disco quando ele aparece -- um
        `cvoff-games --all` rodado com a sala aberta passa a responder sem reabri-la.
        """
        from chess_diagram_ocr import games_cache

        caminho = self._caminho_do_cache if self._caminho_do_cache is not None else games_cache.DEFAULT_STORE_PATH
        if self._loja is not None and (self._loja.path == caminho or not caminho.exists()):
            return self._loja
        bases = tuple(self._bases())
        if not bases:
            return None
        if self._loja is not None:
            self._loja.close()
        self._loja = games_cache.open_store(caminho, database=list(bases), somente_leitura=True)
        return self._loja


class _JanelaDePartidas(QDialog):
    """As partidas da base que chegam a esta posição (S-287). Só mostra: a escolha é da Galeria."""

    def __init__(self, pai: QWidget, resposta: Any) -> None:
        from PyQt6.QtWidgets import QListWidget

        super().__init__(pai)
        self.setWindowTitle("Partidas da posição")
        self.resize(560, 400)
        pilha = QVBoxLayout(self)
        pilha.setContentsMargins(*(espaco.moldura(),) * 4)
        rotulo = QLabel(resposta.frase, self)
        rotulo.setWordWrap(True)
        # **Uma frase, e não duas** (F9-C14). Quando a lista está vazia quem explica é o estado
        # vazio, que diz a mesma coisa **dentro** do vazio e com o botão junto; deixar as duas na
        # tela é a duplicação que o §7 do ciclo 2 mandou apagar na Galeria -- lá eram duas frases
        # iguais a 320 px uma da outra.
        rotulo.setVisible(bool(resposta.partidas))
        pilha.addWidget(rotulo)
        self.lista = QListWidget(self)
        self.lista.setAccessibleName("Partidas que chegam a esta posição")
        for hit in resposta.partidas:
            self.lista.addItem(hit.label)
        pilha.addWidget(self.lista, 1)
        # **Tinha a frase e não tinha o botão** (F9-C13, §5.3): a frase de `resposta` explicava,
        # e a pessoa ficava olhando uma lista branca sem saída desenhada dentro dela.
        # **Sem botão, e a ausência é a correção do §5.1 do ciclo 15.** Ele desenhava `Fechar`
        # ligado a `self.reject` -- que é exatamente o que o `Fechar` do rodapé faz --, e a tela
        # saía com **dois botões de mesma legenda** a 160 px um do outro numa janela de 560x400.
        # A distinção tinha sido dada ao `accessibleName` (`Fechar e escolher outra posição`), de
        # modo que quem **ouve** recebia dois nomes e quem **vê** recebia `Fechar` duas vezes: é a
        # inversão que esta frente já nomeou e consertou uma vez, no par `outro` da Galeria
        # (F9-C7 §1.8).
        #
        # Entre as duas saídas que o crítico ofereceu -- "faz alguma coisa, ou sai" --, sai: o
        # gesto que resolve aqui é escolher outra posição no tabuleiro, e este diálogo não tem
        # como oferecê-lo (quem sabe trocar de base é a Galeria, e a sala só **lê** a lista de
        # bases). Um botão que repete o rodapé não é uma saída a mais; é a mesma saída desenhada
        # duas vezes. O título e a frase continuam dizendo o que falta e por quê.
        self.vazio = EstadoVazio(
            self.lista,
            titulo=strings.POSICAO_SEM_PARTIDA_TITULO,
            frase=resposta.frase or strings.POSICAO_SEM_PARTIDA_FRASE,
        )
        self.vazio.setVisible(not resposta.partidas)
        if resposta.truncada:
            # **Quem exibe tem de dizer que a lista é menor que a base**: sem isto, escolher
            # achando que se viu tudo é o defeito que a Galeria já mede na sua própria lista.
            aviso = QLabel(f"{len(resposta.partidas)} de {resposta.total} partida(s).", self)
            tema.pintar(aviso, "color", tokens.TEXTO_SECUNDARIO)
            pilha.addWidget(aviso)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        botoes.rejected.connect(self.reject)
        pilha.addWidget(botoes)
        self.show()
