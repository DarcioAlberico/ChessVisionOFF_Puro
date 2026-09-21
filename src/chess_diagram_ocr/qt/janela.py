"""A janela: monta as sete abas, liga uma à outra e traduz widget em parâmetro do serviço (S-505).

É o papel que o `app_tkinter.py` tem do outro lado, com a mesma regra de corte da S-31 -- **o que
dá para testar não fica aqui**. Por isso a classe mora no pacote e não no `app_pyqt.py`: uma janela
que só existe dentro do arquivo de entrada só pode ser exercitada abrindo-a.

---

**A janela não decide nada sobre nenhum painel.** Cada um dos sete tem o seu arquivo, os seus
sinais e o seu teste; o que esta classe faz é o que nenhum deles pode fazer sozinho -- saber que os
outros existem. Três coisas, e só três:

1. **A repartição da tela.** À esquerda as seis abas de trabalho, à direita o visualizador. É a do
   produto, e a ordem das abas é a da S-162: Resultado, Estudo e Revisão são do diagrama aberto
   agora; Texto, Dataset e Galeria são do acervo. O corte entre os dois grupos é onde a barra muda
   de assunto.
2. **A fiação.** Cada seta do desenho abaixo é um `connect`, e cada uma existe porque um painel
   sabe uma coisa que outro precisa e nenhum dos dois conhece o outro.
3. **A tabela de comandos.** O menu, a paleta e os atalhos saem todos dela, e ela é a soma de três:
   a desta janela e as duas `COMANDOS_DA_ABA` -- da sala de estudo e da aba de texto.

## As ligações, e por que cada uma existe

    PDF  --abriu_pdf-->        Galeria (adota o livro), Estudo (abre a sala), Resultado (descarta
                               o que era do livro anterior), esta janela (relê as marcas de salvo)
    PDF  --antes_de_trocar-->  Resultado guarda no cache o que está no editor (S-31)
    PDF  --pagina_desenhada--> Resultado restaura a página, Galeria acompanha, as caixas voltam
                               (e, se o cache não sabe da página, o detector roda ao fundo, S-68)
    PDF  --caixa_clicada-->    esta janela decide entre selecionar e ler (`decide_box_click`)
    PDF  --caixa_dispensada--> a caixa sai da página (S-177)
    PDF  --caixa_para_estudo--> o duplo clique leva o diagrama à sala de estudo -- lendo a
                               página antes, se ela ainda não foi lida
    PDF  --regiao_pedida-->    o serviço reconhece o recorte

    Resultado --salvou-->      a caixa fica verde, a Galeria conta de novo, o Dataset relê
    Resultado --revisou-->     a Revisão fecha o item da fila (S-22)
    Resultado --regravou-->    o Dataset relê a linha que mudou (S-23)
    Resultado --selecionou-->  o visualizador destaca a caixa

    Galeria  --pediu_pagina--> o visualizador vira a página (S-67)
    Galeria  --anotacoes-->    as caixas violeta voltam, as abas recontam
    Galeria  <--sumidouro--    a Revisão entrega o coletor: **uma varredura por livro** (S-119)

    Revisão  --abriu-->        o Resultado abre o item, já na casa suspeita
    Revisão  --pediu_varredura--> a Galeria varre (a passada é dela)
    Dataset  --editar-->       o Resultado abre a amostra; salvar **regrava** a linha

    Estudo   <-- posição do diagrama, recorte, linha impressa do Texto, página do PDF, bases
    Estudo   --> a linha vai para o Texto, e a aba dele vem para a frente

**Nenhuma dessas setas volta.** O vínculo do estudo com o OCR é de mão única (analisar uma posição
não é corrigi-la), a Galeria não conhece a Revisão, e o Resultado não conhece nem uma nem outra --
o que cada painel oferece é um sinal, e quem escuta é esta janela.
"""

from __future__ import annotations

import logging
import weakref
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import Any, cast

from PyQt6 import sip
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.board_detection import NoBoardDetectedError
from chess_diagram_ocr.config import (
    DEFAULT_DATASET_CSV,
    DEFAULT_MODEL_PATH,
    DEFAULT_ORIENTATION_MODE,
    DEFAULT_PDF_DIR,
    PROJECT_ROOT,
    find_default_pdf_path,
)
from chess_diagram_ocr.detection import DiagramCandidate, detect_diagrams_in_pdf_page, detect_diagrams_rendering_page
from chess_diagram_ocr.processo_de_trabalho import processo_de_trabalho
from chess_diagram_ocr.qt import acessibilidade, dialogo_de_configuracoes, dialogos, dica, escala, exportador_de_livro, fila, fita, legenda, menu
from chess_diagram_ocr.qt import abas_da_suite, importador_de_livro, painel_de_revisao_de_texto, painel_de_rotulagem, painel_do_pdf
from chess_diagram_ocr.qt import paleta, plataforma, tema
from chess_diagram_ocr.qt.areas_de_trabalho import AreasDeTrabalho
from chess_diagram_ocr.qt.trilho import TrilhoDoLivro
from chess_diagram_ocr.qt import atalhos as qt_atalhos
from chess_diagram_ocr.qt import icones as qt_icones
from chess_diagram_ocr.qt import tabuleiro as qt_tabuleiro
from chess_diagram_ocr.qt.campo import PainelDeCampo
from chess_diagram_ocr.qt.dialogos import ControladorDeTreino
from chess_diagram_ocr.qt.exportador import Exportador
from chess_diagram_ocr.qt.marcas import LeitorDeMarcas, amostras_de_treino_guardadas
from chess_diagram_ocr.qt.painel_da_galeria import PainelDaGaleria
from chess_diagram_ocr.qt.painel_de_estudo import PainelDeEstudo
from chess_diagram_ocr.qt.painel_de_resultado import PainelDeResultado
from chess_diagram_ocr.qt.painel_de_revisao import PainelDeRevisao
from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto
from chess_diagram_ocr.qt.painel_do_dataset import PainelDoDataset
from chess_diagram_ocr.qt.painel_do_pdf import PainelDoPdf
from chess_diagram_ocr.qt.rodape import RodapeDaJanela
from chess_diagram_ocr.qt import leitura
from chess_diagram_ocr.qt.leitura import Aquecimento, Ocupacao
from chess_diagram_ocr.qt.trabalho import DeteccaoDeFundo, Tarefa, manter_viva, rastro_de
from chess_diagram_ocr.review_queue import DEFAULT_QUEUE_PATH
from chess_diagram_ocr.service import OcrService, RecognitionOptions, RecognizedDiagram, RecognitionCanceled
from chess_diagram_ocr.ui import (
    abas,
    conjuntos,
    desfazivel,
    espaco,
    estado_do_rodape,
    geometria,
    pele,
    sala_declarada,
    strings,
)
from chess_diagram_ocr.ui.busy import BusyRegistry
from chess_diagram_ocr.ui.editor_model import DiagramEditorModel
from chess_diagram_ocr.ui.exportacao_de_pgn import ExportSettings
from chess_diagram_ocr.ui.galeria_declarada import LARGURA_MINIMA_DA_GALERIA
from chess_diagram_ocr.ui.page_overlay import (
    BoxClick,
    DiagramBox,
    DroppedBoxes,
    OverlayParams,
    PageBoxes,
    PageBoxesCache,
    boxes_from_candidates,
    boxes_from_diagrams,
    choose_boxes,
    decide_box_click,
    mark_edited,
    mark_saved,
)
from chess_diagram_ocr.ui.page_results import PageOcrParams, colocacoes_conferidas, paginas_editadas
from chess_diagram_ocr.ui.configuracoes import dpi as _dpi, max_boards as _max_boards
from chess_diagram_ocr.ui.pedido_de_treino import TrainingRequest, pedido_de_treino
from chess_diagram_ocr.ui.sala_declarada import COMANDOS_DA_ABA as COMANDOS_DA_SALA
from chess_diagram_ocr.ui.state import AppState, load_state, save_state
from chess_diagram_ocr.ui.texto_declarado import COMANDOS_DA_ABA as COMANDOS_DO_TEXTO
from chess_diagram_ocr.ui.varredura_de_revisao import PedidoDeVarredura

logger = logging.getLogger(__name__)

__all__ = ["LARGURA_MINIMA_DAS_ABAS", "LARGURA_MINIMA_DO_VISOR", "JanelaPrincipal"]

LARGURA_MINIMA_DAS_ABAS = LARGURA_MINIMA_DA_GALERIA
"""O piso do lado esquerdo, somado das partes em `galeria_declarada.LARGURA_MINIMA_DA_GALERIA`.

**É a aba mais exigente que decide o piso**, e não a média: a Galeria precisa do recorte, mais
260 px de lateral, mais a folga -- e abaixo disso quem perde é a coluna de headers, os controles
que gravam a procedência de uma partida (S-154).

**Era `720` cravado, e o número tinha se descolado da soma que ele diz ser** (F9-C2). A soma
valia enquanto o recorte era fixo em 420; quando o item 4 do §7 o trocou por um recorte elástico
de piso 240, o 720 continuou aqui sozinho -- e uma constante que só coincidia com a fórmula dela
é uma constante que já divergiu uma vez sem ninguém ver. Agora ela **é** a fórmula, e o piso da
janela caiu de 1243 px de largura junto com o recorte."""

LARGURA_MINIMA_DO_VISOR = 520
"""O mesmo piso do visualizador do produto: abaixo disso a página não cabe nem no ajuste à
largura, e o que sobra é rolagem horizontal."""

TITULO_DA_JANELA = strings.PRODUTO
"""A marca no título: o produto, e **não mais o toolkit** (OCR_UI C2, A10). Era `"PyQt"`, para
distinguir esta janela da do Tk enquanto as duas escreviam no mesmo `labels.csv`; o corte aconteceu
(S-506) e a barra ainda dizia "… — ChessVisionOFF — PyQt". O título é o de `strings.titulo_da_janela`."""

TITULO_DE_TESTE = TITULO_DA_JANELA
"""O nome que os testes da S-502 citam. Um alias e não um segundo literal."""

ESPERA_AO_FECHAR_MS = 15_000
"""Quanto o fechamento espera pela tarefa em curso, em milissegundos."""

CAMINHO_DO_ESTADO = PROJECT_ROOT / "data" / "janela.json"
"""Onde o que a janela lembra entre execuções fica (S-25/S-156).

**O nome mudou com o corte (S-506), e a razão é a mesma dos dezessete ponteiros que o corte
deixou apontando para o nada:** o arquivo se chamava `app_tkinter_state.json`, e o toolkit que ele
nomeia não existe mais. O estado nunca foi do Tk -- é da janela --, e um arquivo que nomeia o
toolkit errado é a próxima pessoa concluindo que ele é lixo de uma versão anterior."""

CAMINHO_HERDADO_DO_ESTADO = PROJECT_ROOT / "data" / "app_tkinter_state.json"
"""O nome antigo, lido uma vez quando o novo ainda não existe.

**A migração é de uma linha e vale o preço.** Este arquivo guarda o histórico de 50 livros com a
página de cada um -- meses de "onde eu parei neste livro?" --, e renomear sem lê-lo apagaria isso
em silêncio na primeira abertura. Não é reescrito nem apagado: quem grava é sempre
`CAMINHO_DO_ESTADO`, e o antigo fica onde está para o caso de alguém precisar dele."""


class JanelaPrincipal(QMainWindow):
    """As sete abas do produto numa janela, e a fiação entre elas."""

    def __init__(
        self,
        *,
        servico: OcrService | None = None,
        csv_de_rotulos: Path = DEFAULT_DATASET_CSV,
        pasta_de_estudos: Path | None = None,
        pasta_da_galeria: Path | None = None,
        caminho_do_estado: Path | None = None,
        rasterizar_ao_fundo: bool | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if rasterizar_ao_fundo is None:
            rasterizar_ao_fundo = painel_do_pdf.RASTERIZAR_AO_FUNDO
        self._rasterizar_ao_fundo = rasterizar_ao_fundo
        """Repassado ao `PainelDoPdf` (OCR_UI passo 15). Desligado nos testes de janela, que
        perguntam pela folha na linha seguinte a `abrir_pdf`; o produto rasteriza ao fundo."""
        self._servico = servico if servico is not None else OcrService(model_path=DEFAULT_MODEL_PATH)
        self._csv_de_rotulos = Path(csv_de_rotulos)
        self._pasta_de_estudos = pasta_de_estudos
        self._pasta_da_galeria = pasta_da_galeria
        """Onde o índice varrido e as anotações moram. `None` é o padrão do produto, `data/gallery/`.

        Existe pelo mesmo motivo do parâmetro homônimo do painel: **sem ele o teste da janela grava
        no acervo de verdade**, e três caminhos de escrita resolvem o padrão na definição."""

        self._caminho_do_estado = Path(caminho_do_estado) if caminho_do_estado is not None else CAMINHO_DO_ESTADO
        """Onde o estado desta janela é lido e gravado. `None` é o do produto.

        Injetável pelo mesmo motivo de `pasta_da_galeria` e do `caminho_do_conjunto` de
        `qt/campo.py`: **sem isto o teste grava o estado da máquina de quem roda a suíte**, e um
        teste que troca o último PDF de alguém não é um teste."""

        self._estado = self._ler_estado()
        """O que a sessão anterior deixou. Lido **antes** dos widgets, e não depois.

        A ordem é o item: a densidade decide a folha de estilo, a página guardada decide onde o
        livro abre e a fila decide de que arquivo o painel de revisão nasce -- três coisas que os
        widgets recebem na construção. Ler depois obrigaria a construí-los duas vezes."""

        self._estado_aplicado = False
        """O estado lido já chegou aos widgets? (S-322)

        Enquanto for `False`, `_gravar_estado` não grava. O defeito que isto impede está medido do
        outro lado: gravar antes de aplicar lê os widgets **nos padrões de fábrica** e os escreve
        por cima do que estava no disco -- e quem trabalhava com a marcação de diagramas desligada
        a desligava toda sessão."""

        self._estudo_a_reabrir = self._estado.estudo_aberto
        """A mesa em que a sessão anterior parou, guardada até o livro dela abrir (S-347)."""

        self._divisor_por_posicionar = bool(self._estado.sash_fraction)
        """A alça do divisor ainda espera a primeira aparição da janela. Ver `showEvent`."""

        self.busy = BusyRegistry()
        self._ocupacao = Ocupacao(self.busy)
        self._aquecimento = Aquecimento(self._servico, self.busy, dizer=self._dizer,
                                        ocupada=lambda: self._tarefa is not None)
        """Onde as operações longas se declaram (S-112). **Antes dos painéis** (F9-C3): quem lê
        ao fundo precisa dela no construtor, e leitura sem registro é invisível ao rodapé."""

        self._pdf: Path | None = None
        self._itens: list[RecognizedDiagram] = []
        self._salvos: dict[int, set[int]] = {}
        self._leitor_de_marcas = LeitorDeMarcas(
            lambda: self._csv_de_rotulos,
            self,
            ocupado=self.busy,
            splits=lambda: self._caminhos_do_dataset()[2],
            em_processo=self._rasterizar_ao_fundo,
        )
        """Quem lê o `labels.csv` fora da thread da janela (F9-C2). Ver `qt/marcas.py`."""
        self._leitor_de_marcas.prontas.connect(self._marcas_chegaram)
        self._caixas_por_pagina = PageBoxesCache()
        self._tiradas = DroppedBoxes()
        """As caixas que a pessoa tirou da página, por (livro, página) (S-177).

        Guardadas na janela e não no visor porque elas sobrevivem à virada: voltar à página tem de
        trazer a página **sem** o falso positivo que já foi recusado uma vez.

        **`DroppedBoxes` e não um conjunto de índices, e a diferença é medida.** Ela guarda a
        *caixa* -- casa por IoU --, e o índice não é identidade: uma redetecção com outro DPI, ou
        com um diagrama a mais achado antes dele, renumera tudo. Guardar o índice faria a recusa
        migrar para o vizinho, que é pior que não guardar."""
        self._candidatos: tuple[int, tuple[DiagramCandidate, ...]] | None = None
        """O que o detector achou na página exibida, **com o número da página ao lado**.

        Guardado para que "Ler página" não redetecte o que "Marcar diagramas" acabou de achar. Uma
        página só: cada candidato carrega o recorte em 800x800, que são ~1,9 MiB.

        O par com a página é o contrato que `recognize_page` cobra de quem passa a lista: ela não
        tem como conferir de que página vieram os candidatos."""
        self._detector = DeteccaoDeFundo(self)
        self._detector.achou.connect(self._chegou_a_deteccao_de_fundo)
        """Marca a página que acabou de aparecer sem trancar nada (S-68). Ver `_detectar_ao_fundo`."""
        self._tarefa: Tarefa | None = None
        """A tarefa em curso. Guardada num atributo porque um `QThread` sem referência viva é
        coletado no meio da execução, e o sintoma é a janela travada esperando um sinal que nunca
        vem."""
        self._trancas: set[str] = set()
        """Quem está trancando agora -- treino, exportação PGN, exportação do livro (C7)."""
        self._estudar_ao_ler: tuple[int, int] | None = None
        """`(página, diagrama)` que um duplo clique pediu para estudar **antes de a página ser
        lida**. O primeiro clique do par já pôs a leitura em curso; `_chegaram_itens` atende o
        pedido quando ela terminar, e ele morre com a tarefa ou com a virada de página."""
        self._caixa_a_ler: int | None = None
        self._leitura_adiada = QTimer(self)
        self._leitura_adiada.setSingleShot(True)
        self._leitura_adiada.timeout.connect(self._ler_a_caixa_clicada)
        """O clique numa caixa ainda não lida **espera o intervalo do duplo clique** antes de ler.

        A leitura tranca o visor, e um segundo aperto num widget desabilitado não chega a ninguém:
        sem a espera, o duplo clique numa página não lida era engolido pelo próprio primeiro clique.
        A espera custa ~400 ms antes de uma leitura de segundos; o clique numa caixa já lida não
        espera nada, porque selecionar não tranca."""

        self._analisador = sala_declarada.motor_de_analise()
        """O motor UCI, ou `None` (F9-C16). **Antes** dos painéis: `PainelDeEstudo` decide na
        construção se desenha a seção do motor. Ver `ui/sala_declarada.motor_de_analise`."""

        self._montar()
        self._ligar()
        self._aplicar_estado()
        self._atualizar_titulo()
        self._atualizar_abas()
        self.rodape.mostrar("Abra um livro em PDF para começar.")

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        # **A fundação antes dos widgets, e a ordem é o item.** A folha de estilo é da aplicação e
        # alcança todo widget criado depois dela; aplicá-la no fim faria os widgets nascerem com o
        # cinza de fábrica e só depois trocarem de cor, que no Windows pisca.
        #
        # **Com a pele guardada, e não nos padrões** (S-221/S-232). A janela subia sempre no cromo
        # claro e na densidade confortável, e quem escolhia outra coisa a reescolhia toda sessão --
        # ou nem isso, porque a escolha não fazia nada.
        escolhida = self._pele_atual()
        tema.aplicar_tema(cromo_escuro=escolhida.cromo_escuro, densidade=self._densidade_atual())
        plataforma.preparar_janela(self)
        dica.ajustar_atraso()
        # **Antes dos painéis**: os dois tabuleiros leem o conjunto de peças ao nascer (S-230).
        self._aplicar_conjunto()

        self._montar_paineis()

        corpo = QWidget(self)
        pilha = QVBoxLayout(corpo)
        pilha.setContentsMargins(0, 0, 0, 0)
        pilha.setSpacing(0)
        # **O cromo da pele fica acima do divisor, e vazio na clássica** (S-222/S-223/S-227). Um
        # contêiner sempre presente é o que permite trocar de pele sem remontar a janela: a troca
        # esvazia este e o preenche de novo, e página, zoom, diagrama e aba não são alcançados.
        self.cromo = QWidget(corpo)
        self._pilha_do_cromo = QVBoxLayout(self.cromo)
        self._pilha_do_cromo.setContentsMargins(0, 0, 0, 0)
        self._pilha_do_cromo.setSpacing(0)
        pilha.addWidget(self.cromo)
        pilha.addWidget(self.divisor, 1)
        # O rodapé **por último e fora do divisor**: ele é da janela, não de um dos lados, e é o
        # que a S-163 fixou -- mensagem à esquerda, estado do documento e operação em curso à
        # direita, altura fixa por construção.
        self.rodape = RodapeDaJanela(corpo, cancelar=self.busy.request_cancel)
        # **O rodapé pergunta (S-112) e também é avisado (F9-C4).** Perguntar é a rede contra o
        # `release()` esquecido, que é o erro que de fato acontece; o aviso fecha os até 400 ms em
        # que a mensagem já dizia "Lendo o dataset…" e a barra ao lado ainda estava escondida. Os
        # dispositivos entram no mesmo tique: nenhum dos dois modelos torch avisa quando muda.
        self.rodape.acompanhar(self.busy.running, dispositivos=self._dispositivos, avisos=self.busy.observe)
        pilha.addWidget(self.rodape)
        self.setCentralWidget(corpo)

        # `recentes` é uma **função** e não uma lista: o submenu se refaz a cada abertura, e o
        # acervo muda enquanto o programa roda. Uma lista montada aqui mostraria o histórico de
        # quando a janela subiu (S-161).
        self.menu = menu.montar(self, self._comandos(), recentes=self._livros_recentes)
        self._teclas = qt_atalhos.ligar(self, self._comandos())
        """A guarda de foco. **Guardada num atributo de propósito**: um `QObject` sem referência
        viva é coletado, e um filtro coletado deixa de ser chamado sem que nada avise -- a janela
        simplesmente perde o teclado."""
        # A marca dos dois submenus **depois** de montar a barra: a pele e a densidade em vigor
        # foram lidas antes dos widgets, e sem isto o menu abriria sem nada marcado -- que é o
        # mesmo que dizer "nenhuma delas está em uso".
        self._marcar_a_aparencia()
        # **Um menu não promete o que o produto não faz** (F9-C15 §8 item 1). Ver `menu.impedir`.
        if self._analisador is None:
            self.menu.impedir(sala_declarada.COMANDOS_QUE_EXIGEM_MOTOR, motivo=strings.SEM_MOTOR_DICA)
        if self.exportador_de_livro is None:
            self.menu.impedir(exportador_de_livro.COMANDOS, motivo=exportador_de_livro.MOTIVO_AUSENTE)
        if self.livro is None:
            self.menu.impedir(importador_de_livro.COMANDOS, motivo=importador_de_livro.MOTIVO_AUSENTE)
        self.menu.marcar("trilho", ligado=True)
        self._montar_o_cromo(escolhida)
        acessibilidade.tornar_acessivel(self)  # o nome derivado, aqui e em todo diálogo (F9)
        escala.aplicar_escala(self)  # o degrau tipográfico (F9-C2); ver o módulo
        self.resize(1440, 900)

    def _montar_paineis(self) -> None:
        self.divisor = QSplitter(Qt.Orientation.Horizontal, self)

        # **Os quatro painéis do diagrama são modos da aba `Livro`**, e não abas (OCR_UI passo
        # 17, tarefa 3): quem sabe onde cada área mora é `qt/areas_de_trabalho.py`; aqui só se
        # monta cada painel e se diz se ele é modo (`adicionar_modo`) ou aba (`addTab`).
        self.abas = AreasDeTrabalho(self.divisor)
        self.abas.setMinimumWidth(LARGURA_MINIMA_DAS_ABAS)
        self.principal = self.abas.principal

        self.painel = PainelDeResultado(
            self._servico, csv_de_rotulos=self._csv_de_rotulos, parent=self.principal
        )
        self.painel.declarar_contexto(documento=self._chave_do_documento, parametros=self._parametros_de_ocr)
        self.principal.adicionar_modo(abas.RESULTADO, self.painel)

        self.estudo = PainelDeEstudo(
            self.principal,
            # **O motor, se houver um** (F9-C16): sem esta linha os três comandos do menu
            # Estudo nunca podiam funcionar. Ver `ui/sala_declarada.motor_de_analise`.
            analyzer=self._analisador,
            # Vínculo de mão única: o estudo lê a posição do diagrama selecionado e nunca escreve
            # de volta. Um lance jogado no estudo não é uma correção do OCR.
            posicao=self._posicao_de_estudo,
            pasta_inicial=DEFAULT_PDF_DIR,
            pasta_de_estudos=self._pasta_de_estudos,
            # As quatro portas por onde o **livro** entra na sala. Cada uma é uma pergunta que
            # outro painel já sabe responder, e nenhuma deixa a sala escrever naquele painel.
            recorte=self._recorte_do_diagrama,
            linha_impressa=self._linha_impressa,
            abrir_pagina=self._abrir_pagina_do_estudo,
            para_o_texto=self._linha_para_o_texto,
        )
        self.principal.adicionar_modo(abas.ESTUDO, self.estudo)

        self.revisao = PainelDeRevisao(
            self.principal,
            pedido_de_varredura=self._pedido_de_varredura,
            # A fila que a sessão anterior abriu, e não sempre a do produto (S-22/S-156). Vazio no
            # estado é "nunca escolhi outra", e aí a do produto é a certa.
            queue_path=Path(self._estado.review_queue_path or DEFAULT_QUEUE_PATH),
        )
        self.principal.adicionar_modo(abas.REVISAO, self.revisao)

        self.texto = PainelDeTexto(busy=self.busy, parent=self.principal)
        self.principal.adicionar_modo(abas.TEXTO, self.texto)

        self.dataset = PainelDoDataset(
            self.abas,
            caminhos=self._caminhos_do_dataset,
            busy=self.busy,
            em_processo=self._rasterizar_ao_fundo,
        )
        self.abas.addTab(self.dataset, abas.DATASET)

        self.galeria = PainelDaGaleria(
            self.abas,
            service=self._servico,
            pdf_path=lambda: self._pdf,
            model_path=lambda: DEFAULT_MODEL_PATH,
            max_boards=_max_boards,
            # Uma varredura por livro (S-119): a Galeria varre, e a fila de revisão sai da mesma
            # passada. Quem liga as duas abas é esta janela -- nenhuma conhece a outra.
            sumidouro_de_revisao=self.revisao.sumidouro,
            pasta_da_galeria=self._pasta_da_galeria,
            busy=self.busy,
        )
        self.abas.addTab(self.galeria, abas.GALERIA)
        self.rotulagem = painel_de_rotulagem.montar(self.abas)  # a bancada da suíte, se ao alcance
        if self.rotulagem is not None:
            self.abas.addTab(self.rotulagem, abas.ROTULAGEM)
        self.revisao_de_texto = painel_de_revisao_de_texto.montar(self.abas)  # idem, passo 14
        if self.revisao_de_texto is not None:
            self.abas.addTab(self.revisao_de_texto, abas.REVISAO_DE_TEXTO)

        self.lado_do_livro = QWidget(self.divisor)
        self.pdf = PainelDoPdf(
            self.lado_do_livro,
            dpi=_dpi,
            # Todo livro abre na página em que foi deixado, e não só o último (S-25). O histórico
            # guarda 50, e é a pergunta que se faz ao voltar a um livro pela quinta vez.
            pagina_inicial_de=self._pagina_guardada_de,
            pasta_inicial=DEFAULT_PDF_DIR,
            rasterizar_ao_fundo=self._rasterizar_ao_fundo,
        )
        self.pdf.setMinimumWidth(LARGURA_MINIMA_DO_VISOR)

        # **A anotação de campo fica sob a página, e não numa aba** (S-95): ela afirma coisas
        # sobre a página exibida -- quantos diagramas ela tem, se algum é falso positivo --, e
        # numa aba a pessoa anotaria sem estar olhando para o que anota.
        self.campo = PainelDeCampo(
            self.lado_do_livro,
            pdf_path=lambda: self._pdf,
            page_index=lambda: self.pdf.page_index,
            caixas=lambda: self.pdf.boxes,
            caixa_selecionada=lambda: self.pdf.caixa_selecionada,
            colocacoes=self._colocacoes_conferidas,
            aviso_de_treino=self._aviso_de_treino,
        )
        # **O trilho de páginas à esquerda do visor** (OCR_UI passo 17): o mapa do livro, com o
        # estado de cada página e os botões do fluxo principal (importar, primeira duvidosa,
        # exportar). É um índice de largura fixa; a página continua com o resto.
        self.trilho = TrilhoDoLivro(self.lado_do_livro, miniaturas_ao_fundo=self._rasterizar_ao_fundo)
        self.trilho.pagina_pedida.connect(self.pdf.ir_para_pagina)
        self.trilho.exportar_pedido.connect(lambda: self._exportar_livro("epub"))
        coluna = QVBoxLayout()
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(espaco.linha())
        coluna.addWidget(self.pdf, 1)
        coluna.addWidget(self.campo)
        lado = QHBoxLayout(self.lado_do_livro)
        lado.setContentsMargins(0, 0, 0, 0)
        lado.setSpacing(espaco.linha())
        lado.addWidget(self.trilho)
        lado.addLayout(coluna, 1)

        self.divisor.addWidget(self.abas)
        self.divisor.addWidget(self.lado_do_livro)
        self.divisor.setStretchFactor(0, 2)
        self.divisor.setStretchFactor(1, 3)
        # **A alça não apaga a navegação** (F9-C3): colapsar punha 21 de 36 botões fora da tela.
        self.divisor.setChildrenCollapsible(False)
        # **Os tamanhos iniciais são declarados, e não deduzidos.** O `QSplitter` reparte pela
        # `sizeHint` de cada lado, e a de um `QTabWidget` cheio de rótulos com quebra de linha
        # pede toda a largura que lhe derem.
        self.divisor.setSizes([LARGURA_MINIMA_DAS_ABAS, 760])

        self.treino = ControladorDeTreino(self, pedido=self._pedido_de_treino, busy=self.busy)
        self.exportador = Exportador(
            self, configuracao=self._configuracao_de_exportacao, servico=self._servico, busy=self.busy
        )
        # EPUB/DOCX pela suíte, se ao alcance; sem ela os itens ficam cinza com o motivo na dica.
        self.exportador_de_livro = exportador_de_livro.montar(
            self, dizer=self._dizer, trancar=partial(self._trancar, quem="exportação do livro")
        )
        # A importação do livro inteiro, pela mesma suíte e com a mesma guarda (passo 17). A
        # ponte liga o importador ao trilho e guarda o resultado; a janela só a segura.
        # **Sem tranca** (C7): a importação só lê o PDF; a pessoa corrige um diagrama enquanto isso.
        self.livro = importador_de_livro.montar(
            self,
            dizer=self._dizer,
            trancar=lambda _liberado: None,
            ocupado=self.busy,
            trilho=self.trilho,
            pdf_atual=lambda: self._pdf,
            paginas=lambda: self.pdf.page_count,
            revisao_de_texto=self.revisao_de_texto,
        )

    @property
    def editor(self) -> DiagramEditorModel:
        """O modelo do editor, que mora no painel. **Fachada, e é curta de propósito.**

        A janela precisa dele para uma coisa só -- saber de que página veio o que está aberto,
        para o cache e para a marca de salvo. Tudo o mais que se faz com ele é do painel, e é por
        isso que a fachada é uma propriedade de leitura e não um punhado de delegações.
        """
        return self.painel.modelo

    # -------------------------------------------------------------------------------- estado

    def _ler_estado(self) -> AppState:
        """O que a sessão anterior deixou, com o nome antigo lido uma vez se o novo não existe.

        **A herança só vale para o arquivo do produto.** Um teste que passa `caminho_do_estado`
        pede um estado próprio, e cair no do produto porque o dele ainda não existe faria a suíte
        ler o último PDF da máquina de quem a roda -- que é justamente o que o parâmetro evita.
        """
        if self._caminho_do_estado == CAMINHO_DO_ESTADO and not CAMINHO_DO_ESTADO.exists():
            if CAMINHO_HERDADO_DO_ESTADO.exists():
                logger.info(
                    "Estado herdado de %s; a partir de agora ele é gravado em %s.",
                    CAMINHO_HERDADO_DO_ESTADO.name,
                    CAMINHO_DO_ESTADO.name,
                )
                return load_state(CAMINHO_HERDADO_DO_ESTADO)
        return load_state(self._caminho_do_estado)

    def _pagina_guardada_de(self, livro: Path) -> int:
        """Em que página este livro foi deixado. `0` para o que nunca foi aberto (S-25)."""
        return self._estado.page_for(Path(livro))

    def _livros_recentes(self) -> list[tuple[str, Callable[[], None]]]:
        """Os livros que o estado lembra, para o submenu "Abrir recente" (S-161).

        `recentes()` já filtra o que não existe mais no disco -- e o filtro não é zelo: o
        histórico desta máquina apontava 13 entradas para a pasta de antes de o projeto ser
        movido, e um submenu de 13 linhas que falham ao serem clicadas é o mesmo defeito que
        `menu.montar` recusa ao exigir comando para todo item, descoberto um clique por vez.

        `partial` e não `lambda`: um `lambda caminho` dentro do laço captura a **variável**, e os
        dez itens do submenu abririam o décimo livro.
        """
        return [
            (Path(caminho).name, partial(self.abrir_pdf, Path(caminho)))
            for caminho in self._estado.recentes()
        ]

    def _abrir_o_mais_recente(self) -> None:
        """O comando `abrir_recente` fora do menu -- na paleta e no atalho, onde não há submenu.

        **Abre o primeiro da lista**, que é o livro anterior a este. Um comando que não fizesse
        nada quando invocado pela paleta seria o mesmo defeito que a conta do catálogo veio
        fechar: dono chamável, efeito nenhum.
        """
        recentes = self._livros_recentes()
        if not recentes:
            self._dizer("Nenhum livro recente: abra um PDF pela primeira vez.")
            return
        nome, abrir = recentes[0]
        abrir()
        self._dizer(f"Aberto o mais recente: {nome}.")

    def _aplicar_estado(self) -> None:
        """Põe nos widgets o que veio do disco, e só então libera a gravação (S-156/S-291/S-322).

        **Depois de `_ligar` e não antes.** Marcar um interruptor dispara o sinal dele, e o sinal
        só chega a quem escuta depois da fiação -- restaurar antes deixaria a marca na tela e o
        efeito dela por acontecer, que é a metade pior dos dois estados possíveis.
        """
        estado = self._estado
        self._restaurar_arranjo()
        # `last_pdf` vazio é "nunca houve sessão anterior", e aí não há zoom escolhido a
        # restaurar: quem enquadra a primeira abertura é o ajuste à página da S-157.
        if estado.last_pdf:
            self.pdf.aplicar_zoom(estado.pdf_zoom)
        # Depois do zoom (F9-C3): `aplicar_zoom` desliga o enquadramento.
        self.pdf.definir_enquadramento(estado.pdf_enquadramento)
        self.pdf.marcar_diagramas.setChecked(estado.show_diagram_boxes)
        self.pdf.roda_vira_pagina.setChecked(estado.wheel_flips_page)
        self.painel.mostrar_incerteza = estado.show_heatmap
        self.texto.aplicar_zoom(estado.texto_zoom, avisar=False)
        self.texto.definir_quebra(estado.texto_quebra)
        self.estudo.posicionar_divisor(estado.estudo_divisor)
        # Daqui para baixo o disco já está nos widgets, e gravar volta a ser honesto (S-322).
        self._estado_aplicado = True

    def _restaurar_arranjo(self) -> None:
        """Tamanho, posição, divisor e aba de onde a sessão anterior parou (S-156).

        A geometria passa por `geometria_a_aplicar`, que é a mesma decisão pura do outro frontend:
        ela confere a guardada contra as telas de **hoje** e devolve uma centrada quando o monitor
        em que a janela estava não existe mais. Sem isso, trocar de monitor entre duas sessões
        abre a janela fora da tela, sem erro nenhum a que se agarrar.
        """
        alvo = geometria.geometria_a_aplicar(
            self._estado.window_geometry,
            plataforma.monitores(),
            piso=geometria.piso_da_janela(LARGURA_MINIMA_DAS_ABAS, LARGURA_MINIMA_DO_VISOR),
        )
        lida = geometria.geometria_de_texto(alvo) if alvo else None
        if lida is not None:
            self.setGeometry(lida.x, lida.y, lida.largura, lida.altura)
        # O divisor **não** vem aqui: ver `showEvent`.
        # A área de trabalho na primeira abertura, e a guardada nas seguintes (S-162). `nome_atual`
        # traduz o nome que uma sessão antiga guardou e que desde então foi renomeado; um nome de
        # modo (`Resultado`, o que toda sessão anterior ao passo 17 guardou) abre a `Livro` nele.
        self.abas.mostrar_area(abas.nome_atual(self._estado.active_tab) or abas.MODO_DE_TRABALHO)

    def showEvent(self, a0: Any) -> None:  # noqa: N802 - assinatura do Qt
        """Põe o divisor onde ele estava, **na primeira vez que a janela aparece** (S-156).

        **Aqui e não em `_restaurar_arranjo`**, e o motivo é medido: antes do `show()` o
        `QSplitter` ainda tem a largura da montagem, e os dois lados têm piso (`[720, 810]` na
        janela mínima). Pedir 60% ali é pedir 60% de uma largura que não é a final -- o Qt grampeia
        contra os pisos e o que sobra é o arranjo de fábrica, com a alça de volta ao meio.

        É a mesma razão do `_set_initial_sashes` do outro frontend rodar 180 ms depois da
        montagem, e a versão sem relógio dela: o `showEvent` é exatamente o instante em que a
        largura passa a ser a de verdade.

        **Uma vez só.** Todo `show()` posterior -- desminimizar, voltar do Alt-Tab -- reporia a
        alça onde o disco a deixou, por cima de onde a pessoa acabou de pô-la.
        """
        super().showEvent(a0)
        if not self._divisor_por_posicionar:
            return
        self._divisor_por_posicionar = False
        largura = sum(self.divisor.sizes()) or self.divisor.width()
        if largura <= 0:
            return
        esquerda = max(1, int(largura * self._estado.sash_fraction))
        self.divisor.setSizes([esquerda, max(1, largura - esquerda)])

    def _anotar_arranjo(self) -> None:
        """Lê da tela o arranjo de agora e o põe no estado (S-156/S-311).

        **Janela não mostrada não é janela medida** (S-311). Antes do `show()` o divisor devolve os
        tamanhos declarados na montagem, que são do leiaute e não da pessoa: gravá-los apagaria a
        posição da sessão anterior antes de alguém tocar em nada. `isVisible` é o `winfo_ismapped`
        deste lado.

        A geometria sai de `normalGeometry` quando ela existe: é a que a janela tem **fora** do
        maximizado e do minimizado, e é a única que faz sentido restaurar. Ela é o que substitui a
        recusa do `1x1+-32000+-32000` que o Tk devolvia para uma janela minimizada.

        **A aba fica fora da guarda**, e é a diferença entre ela e as outras duas: qual área está à
        frente é verdade com a janela mostrada ou não, e é o `QTabWidget` que responde -- não há
        medida de pixel envolvida. O nome é o da **área** (o modo `Revisão`, e não a aba `Livro`).
        """
        nome = self.abas.nome_da_area_atual()
        if nome:
            self._estado.active_tab = nome
        if not self.isVisible():
            return
        normal = self.normalGeometry()
        atual = normal if not normal.isEmpty() else self.geometry()
        texto = f"{atual.width()}x{atual.height()}{atual.x():+d}{atual.y():+d}"
        self._estado.window_geometry = geometria.geometria_gravavel(texto) or self._estado.window_geometry
        tamanhos = self.divisor.sizes()
        if len(tamanhos) >= 2 and sum(tamanhos) > 0:
            self._estado.sash_fraction = geometria.fracao_de_divisor(tamanhos[0], sum(tamanhos))

    def _gravar_estado(self) -> None:
        """Anota o que a próxima sessão precisa e grava. Nunca levanta -- `save_state` registra.

        **Nada é gravado antes de `_aplicar_estado` (S-322)**: até lá os widgets estão nos padrões
        de fábrica, e escrevê-los por cima do disco apagaria a escolha da sessão anterior sem que
        ninguém tivesse mudado nada.

        `board_zoom` não é tocado aqui, e a omissão é deliberada: é um controle que **este**
        frontend não tem, porque não precisa -- o tabuleiro do Qt se ajusta ao painel, e o
        deslizador de zoom do outro existia porque lá ele era um canvas de tamanho fixo. Não
        escrevê-lo preserva o que estiver no arquivo; zerá-lo seria apagar a escolha de alguém em
        nome de um widget que não há.
        """
        if not self._estado_aplicado:
            logger.debug("Estado ainda não aplicado aos widgets: gravação adiada (S-322).")
            return
        estado = self._estado
        estado.last_pdf = str(self._pdf) if self._pdf is not None else ""
        estado.last_page = self.pdf.page_index
        estado.pdf_zoom = float(self.pdf.zoom)
        estado.pdf_enquadramento = self.pdf.enquadramento
        estado.show_diagram_boxes = bool(self.pdf.marcar_diagramas.isChecked())
        estado.wheel_flips_page = bool(self.pdf.roda_vira_pagina.isChecked())
        estado.show_heatmap = self.painel.mostrar_incerteza
        estado.texto_zoom = int(self.texto.zoom_da_vista)
        estado.texto_quebra = bool(self.texto.quebra)
        estado.review_queue_path = str(self.revisao.queue_path)
        estado.estudo_aberto = self.estudo.chave_do_estudo_aberto
        # `or` o guardado: o divisor devolve `0.0` enquanto não há geometria medida, e zero
        # significa "nunca guardado" -- gravá-lo apagaria a alça da sessão anterior.
        estado.estudo_divisor = self.estudo.fracao_do_divisor or estado.estudo_divisor
        self._anotar_arranjo()
        save_state(self._caminho_do_estado, estado)

    # ------------------------------------------------------------------------------ aparência

    def _pele_atual(self) -> pele.Pele:
        """A pele em vigor: `CVOFF_SKIN`, senão a guardada, senão a clássica (S-221).

        **O ambiente ganha da guardada**, e a razão está em `pele.escolhida`: a variável existe
        para abrir o programa numa aparência a partir de um roteiro, e uma que o disco vencesse
        não serviria para isso.
        """
        return pele.registrada(pele.escolhida(self._estado.skin))

    def _densidade_atual(self) -> str:
        """A densidade em vigor: `CVOFF_DENSITY`, senão a escolhida, senão a que a pele sugere.

        **A pele sugere e a pessoa decide** (S-232). A fita sugere compacta porque é a pele que
        gasta altura com cromo; o que está guardado é a decisão da pessoa, e por isso ela
        sobrevive à troca de pele.
        """
        return pele.densidade_em_vigor(self._pele_atual(), self._estado.densidade)

    def _conjunto_atual(self) -> str:
        """O conjunto de peças em vigor: `CVOFF_PIECES`, senão o guardado, senão o padrão (S-230)."""
        return conjuntos.escolhido(self._estado.piece_set)

    def _aplicar_conjunto(self) -> None:
        """Põe o conjunto em vigor nos tabuleiros. Chamado na abertura e a cada troca.

        **Antes dos painéis, na montagem**: os dois tabuleiros leem o conjunto ao nascer, e
        aplicá-lo depois os faria abrir com o desenho errado e trocar em seguida.
        """
        qt_tabuleiro.definir_conjunto(self._conjunto_atual(), self._estado.piece_dir)

    def _escolher_conjunto(self) -> None:
        """`Ver ▸ Peças`: guarda o conjunto marcado e redesenha os tabuleiros (S-230).

        **A pasta do usuário é perguntada aqui**, e é o que torna a terceira opção real: sem pasta
        escolhida ela cairia nos mesmos doze PNGs do padrão, e a pessoa concluiria que a opção não
        faz nada. Desistir do diálogo repõe a marca no conjunto que estava valendo -- um submenu
        marcado num conjunto que não entrou em vigor é a mesma mentira, com outra roupa.
        """
        pedido = conjuntos.valida(self.menu.escolhido("conjunto_de_pecas") or self._estado.piece_set)
        if conjuntos.registrado(pedido).do_usuario and not self._garantir_pasta_de_pecas():
            self.menu.escolher("conjunto_de_pecas", self._conjunto_atual())
            return
        anterior = self._conjunto_atual()
        self._estado.piece_set = pedido
        self._aplicar_conjunto()
        if pedido != anterior:
            self._dizer(f"Peças: {conjuntos.registrado(pedido).rotulo}.")

    def _garantir_pasta_de_pecas(self) -> bool:
        """A pasta do usuário, perguntada só quando ainda não há uma que exista.

        Guardada **junto** e não em lugar do nome (S-230): quem experimenta a pasta própria, volta
        ao padrão e depois quer a sua de novo não deve ter de reencontrá-la no disco.
        """
        guardada = self._estado.piece_dir.strip()
        if guardada and Path(guardada).is_dir():
            return True
        escolhida = QFileDialog.getExistingDirectory(
            self, strings.PASTA_DE_PECAS, guardada or str(DEFAULT_PDF_DIR)
        )
        if not escolhida:
            return False
        self._estado.piece_dir = escolhida
        return True

    def _marcar_a_aparencia(self) -> None:
        """Põe a marca nos dois submenus de escolha, a partir do que está em vigor."""
        self.menu.escolher("aparencia", self._pele_atual().nome)
        self.menu.escolher("densidade", self._densidade_atual())
        self.menu.escolher("conjunto_de_pecas", self._conjunto_atual())

    def _montar_o_cromo(self, escolhida: pele.Pele) -> str:
        """Desenha o cromo daquela pele acima do divisor. `""` se montou; o motivo se não.

        **Devolve em vez de só registrar** porque quem precisa da resposta é o `--selftest`: "as
        três peles abrem" é uma afirmação verificável, e era a do código 5 do auto-teste que o
        corte do Tk deixou sem dono (S-234/S-506). A janela ignora o retorno -- para ela o
        contrato é o do parágrafo seguinte.

        **A clássica não tem fila nem fita de propósito** (S-221): ela é a janela de sempre, e o
        que ela oferece é o menu mais as barras de cada painel. A fundação se prova quando ela não
        muda nada.

        `KeyError` de comando não amarrado **não pode custar a janela**: quem levanta é
        `fila.montar`/`fita.montar`, e ali o erro é de programa -- mas ele acontece na abertura, e
        uma janela que não abre por causa do cromo é pior que uma janela sem cromo. Fica no log,
        com o nome do comando.
        """
        self._esvaziar_o_cromo()
        montagem = escolhida.montar_cromo
        if montagem == pele.CROMO_CLASSICO:
            self.cromo.setVisible(False)
            return ""
        comandos_da_janela = self._comandos()
        try:
            if montagem == pele.CROMO_FITA:
                barra: QWidget = fita.montar(
                    self.cromo, comandos_da_janela, densidade=self._densidade_atual()
                )
            else:
                barra = fila.montar(self.cromo, comandos_da_janela)
        except Exception as exc:  # noqa: BLE001 - cromo não pode custar a janela
            logger.exception("Cromo %r não montado: a janela abre sem ele.", montagem)
            self.cromo.setVisible(False)
            return f"{escolhida.nome}: {exc}"
        folga = espaco.linha()
        self._pilha_do_cromo.setContentsMargins(folga, folga, folga, 0)
        self._pilha_do_cromo.addWidget(barra)
        self.cromo.setVisible(True)
        self.pdf.nomear_o_que_o_cromo_nao_desenha(self.cromo)  # F9-C7 §3; ver o painel
        return ""

    def provar_as_peles(self) -> list[str]:
        """Monta o cromo de cada pele registrada e devolve as que não montaram (S-234/S-506).

        **É a afirmação que o código 5 do auto-teste faz**, e ela vale porque passa pela tabela de
        comandos **desta** janela: `fila.montar` e `fita.montar` levantam nomeando o comando que
        ninguém amarrou, e é exatamente o defeito que uma pele nova introduz sem que nenhum teste
        de painel note.

        Restaura o cromo em vigor no fim: quem chama pode ser a janela aberta.
        """
        problemas = [
            motivo for registro in pele.PELES if (motivo := self._montar_o_cromo(registro))
        ]
        self._montar_o_cromo(self._pele_atual())
        return problemas

    def _esvaziar_o_cromo(self) -> None:
        """Tira e destrói o que estiver no contêiner do cromo.

        `deleteLater` e não destruição imediata: a troca de pele costuma vir de um clique num
        item de menu, e destruir um widget dentro do tratamento do evento dele é a maneira mais
        curta de derrubar o processo. É a mesma razão de `BarraFluida.esvaziar`.
        """
        while (item := self._pilha_do_cromo.takeAt(0)) is not None:
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.pdf.nomear_o_que_o_cromo_nao_desenha(None)  # cromo vazio = pele clássica (F9-C7 §3)

    def _escolher_pele(self) -> None:
        """`Ver ▸ Aparência`: guarda a pele marcada e remonta o cromo se ela mudou (S-221)."""
        pedida = pele.valida(self.menu.escolhido("aparencia") or self._estado.skin)
        anterior = self._pele_atual().nome
        self._estado.skin = pedida
        if pedida == anterior:
            return
        self._remontar_cromo()
        self._dizer(f"Aparência: {pele.registrada(self._pele_atual().nome).rotulo}.")

    def _escolher_densidade(self) -> None:
        """`Ver ▸ Densidade`: a escolha explícita, que sobrevive à troca de pele (S-232).

        **Guarda mesmo quando o efeito é nenhum.** Escolher "Confortável" estando confortável por
        sugestão da pele não muda um pixel, mas muda o estado: dali em diante é decisão da pessoa,
        e trocar para a fita -- que sugere compacta -- não a desfaz.
        """
        pedida = self.menu.escolhido("densidade")
        if pedida not in pele.DENSIDADES:
            return
        anterior = self._densidade_atual()
        self._estado.densidade = pedida
        if pedida == anterior:
            return
        self._remontar_cromo()
        self._dizer(f"Densidade: {pele.rotulo_de_densidade(pedida)}.")

    def _remontar_cromo(self) -> None:
        """Refaz o cromo sem tocar o conteúdo (S-222).

        Três coisas, nesta ordem: a folha de estilo -- que é quem sabe o cromo escuro e a
        densidade e repinta o que foi pintado fora dela --, o cache de ícones, que é **por cor**, e
        o cromo da pele nova.

        **O que não está aqui é metade do item, e é a mesma fronteira do outro frontend.** Página,
        zoom, diagrama selecionado, FEN em edição, aba aberta, divisor e a frase do rodapé não são
        salvos nem restaurados: eles continuam de pé porque a remontagem não os alcança.
        """
        escolhida = self._pele_atual()
        tema.aplicar_tema(cromo_escuro=escolhida.cromo_escuro, densidade=self._densidade_atual())
        qt_icones.limpar_cache()
        self._marcar_a_aparencia()
        self._montar_o_cromo(escolhida)

    # -------------------------------------------------------------------------------- fiação

    def _ligar(self) -> None:
        """Todas as ligações entre painéis, num lugar só.

        **Num método e não espalhadas pela montagem**, e é decisão: a montagem responde "o que
        existe na tela" e esta responde "quem conversa com quem". Espalhadas, a segunda pergunta
        só se responde lendo as sete construções inteiras -- e foi assim que o `app_tkinter`
        chegou a ter a mesma ligação escrita em dois lugares.
        """
        # Toda frase de painel vai para o rodapé, e nenhum painel sabe que o rodapé existe.
        for painel in (self.painel, self.pdf, self.galeria, self.revisao, self.estudo, self.dataset, self.texto, self.campo):
            painel.estado.connect(self._dizer)
        for quem, controlador in (("treino", self.treino), ("exportação PGN", self.exportador)):
            controlador.estado.connect(self._dizer)
            controlador.controles.connect(partial(self._trancar, quem=quem))
        self.exportador.controles.connect(self._exportacao_mudou)
        self.treino.terminou.connect(self._treino_terminou)

        # --- o visualizador
        self.pdf.abriu_pdf.connect(self._abriu_livro)
        self.pdf.abriu_pdf.connect(lambda caminho: self.trilho.abrir_livro(Path(str(caminho)), self.pdf.page_count))
        self.pdf.pagina_desenhada.connect(self.trilho.marcar_pagina_atual)
        self.pdf.antes_de_trocar_de_pagina.connect(self.painel.lembrar_pagina)
        self.pdf.pagina_desenhada.connect(self._pagina_apareceu)
        self.pdf.caixa_clicada.connect(self._clicou_na_caixa)
        self.pdf.caixa_dispensada.connect(self._tirar_caixa)
        self.pdf.caixa_para_estudo.connect(self._estudar_a_caixa)
        self.pdf.regiao_pedida.connect(self._ler_regiao)
        self.pdf.leitura_pedida.connect(self._leitura_pedida)
        self.pdf.exportacao_pedida.connect(lambda: self.exportador.comecar(self._pdf))
        self.pdf.exportacao_cancelada.connect(self.exportador.cancelar)

        # --- o Resultado
        # A S-451: "Salvar todos" pergunta antes de gravar a segunda cópia, e quem sabe o que já
        # foi salvo é a janela -- o painel não tem o carimbo por página.
        self.painel.diagramas_salvos = lambda _documento, pagina: self._salvos.get(pagina, set())
        self.painel.selecionou.connect(self.pdf.selecionar_caixa)
        self.painel.mudou.connect(self._recarimbar_caixas)
        self.painel.salvou.connect(self._gravou_amostra)
        self.painel.revisou.connect(self._fechar_item_da_fila)
        self.painel.regravou.connect(self._dataset_mudou)

        # --- a Galeria
        self.galeria.pediu_pagina.connect(self.pdf.ir_para_pagina)
        self.galeria.anotacoes_mudaram.connect(self._anotacoes_mudaram)

        # --- a Revisão
        self.revisao.abriu.connect(self._abrir_item_da_fila)
        self.revisao.pediu_varredura.connect(self.galeria.varrer)
        self.revisao.pediu_cancelamento.connect(self.galeria.cancelar_varredura)

        # --- o Dataset
        self.dataset.editar.connect(self._abrir_amostra)

    def _dizer(self, frase: str, severidade: str | None = None) -> None:
        """A frase de qualquer painel no rodapé. Quem emite declara a severidade quando sabe (A10);
        quem não declara cai na heurística de `ui/estado_do_rodape.severidade_de` -- a rede."""
        self.rodape.mostrar(frase, severidade=severidade or estado_do_rodape.severidade_de(frase))

    def _trancar(self, liberado: bool, quem: str = "operação") -> None:
        """Tranca só quem disputa o modelo ou o `labels.csv` com a operação longa (OCR_UI C2, C7).

        Era `abas.setEnabled(False)` -- a janela inteira cinza (análise §6.4). Ficam trancados o
        Resultado (grava amostra), o Dataset (edita o CSV) e a Galeria (varre com o modelo); **por
        quem**, para a operação que termina primeiro não destrancar a outra. O visor tranca por dentro.
        """
        self._trancas.discard(quem) if liberado else self._trancas.add(quem)
        livre = not self._trancas
        self.pdf.trancar(livre)
        for aba in (self.dataset, self.galeria):
            aba.setEnabled(livre)
        self._atualizar_controles()

    def _exportacao_mudou(self, liberado: bool) -> None:
        """O `controles` do exportador vem invertido: `False` é "começou". Ver `trancar`."""
        self.pdf.exportacao_em_curso(not liberado)

    def _leitura_pedida(self, so_o_melhor: bool) -> None:
        """Os dois botões de OCR do visualizador, que diferem só no número de diagramas."""
        self.ler_melhor() if so_o_melhor else self.ler_pagina()

    # -------------------------------------------------------------------------------- livro

    def _abriu_livro(self, caminho: object) -> None:
        """O visualizador abriu outro livro. **Depois de ele abrir de verdade** (S-123).

        A ordem é a correção: com o aviso antes da abertura, um PDF que não abria já tinha
        limpado as caixas, descartado os resultados do livro anterior e apontado a Galeria para o
        arquivo quebrado -- e o `Ctrl+S` seguinte gravava a amostra sob o nome errado. Quem
        garante a ordem é o próprio painel, que só emite depois de contar as páginas.
        """
        alvo = Path(str(caminho))
        anterior = self._pdf
        if self.livro is not None and self.livro.rodando and anterior is not None and anterior != alvo:
            # A importação era do livro anterior: cancelada, e a ponte descarta o resultado
            # que ainda chegar dele (C7 -- a tranca deixou de segurar o «Abrir PDF…»).
            self.livro.cancelar(motivo="troca_de_livro")
            self._dizer(f"A importação de {anterior.name} foi cancelada ao abrir outro livro.")
        self._pdf = alvo
        # As caixas são de um arquivo que pode ter mudado no disco. A chave já inclui o documento,
        # então isto não é correção de defeito: é não guardar afirmação sobre um PDF que ninguém
        # mais está olhando.
        self._caixas_por_pagina.clear()
        self._tiradas.clear()
        self._candidatos = None
        self._itens = []
        self._carregar_marcas_salvas()
        if anterior is not None and self._descartar_o_livro(anterior):
            self.painel.descartar_livro(str(anterior))
        # As abas da suíte acompanham o livro (C7): cada uma tinha o próprio "Abrir PDF…".
        # A contagem de páginas vai junto: a aba não reabre o PDF na thread da janela (`bloqueio`).
        for aba in (self.rotulagem, self.revisao_de_texto):
            if aba is not None and hasattr(aba, "abrir"):
                aba.abrir(alvo, page_count=self.pdf.page_count)
        # Sem isto a galeria só conheceria o livro depois de uma varredura -- e o número do lance
        # digitado na aba Resultado (S-71) seria gravado num modelo sem `pdf_path`, que descarta
        # em silêncio. `request_page=False` porque o visualizador acabou de escolher a página.
        self.galeria.load_pdf(alvo, request_page=False)
        self.estudo.abrir_livro(str(alvo))  # a sala daquele livro volta do disco (S-271)
        # E a mesa em que a sessão anterior parou (S-347). **Só na primeira abertura**: depois
        # dela `estudo_aberto` é o que a pessoa abriu nesta sessão, e reabri-lo a cada troca de
        # livro a puxaria de volta para um diagrama que ela acabou de deixar.
        if self._estudo_a_reabrir:
            self.estudo.reabrir_por_chave(self._estudo_a_reabrir)
            self._estudo_a_reabrir = ""
        self.texto.definir_livro(alvo, pagina=self.pdf.page_index)
        self._atualizar_titulo()
        self._atualizar_abas()
        self._aquecimento.agendar(parent=self)  # o modelo carrega quando a janela ociar (C2)

    def _descartar_o_livro(self, anterior: Path) -> bool:
        """Pergunta antes de esquecer correções à mão do livro que saiu (A7). «Não» as guarda."""
        editadas = paginas_editadas(self.painel.paginas, self.painel.modelo, str(anterior))
        if not dialogos.perguntar_descarte(self, editadas, livro=anterior.name, ao_fechar=False):
            return False
        if self.painel.modelo.page_key is not None and self.painel.modelo.page_key[0] == str(anterior):
            self.painel.limpar()  # senão a virada de página o devolveria ao cache recém-esvaziado
        return True

    def _carregar_marcas_salvas(self) -> None:
        """Pede as marcas deste livro **fora da thread da janela** (F9-C2). Ver `qt/marcas.py`.

        Era leitura síncrona do `labels.csv` inteiro, e o arnês mediu **250 ms** de janela parada
        na abertura de cada livro -- a pior pilha do "abrir PDF", e não o PyMuPDF que o ciclo 1
        acusou. O dicionário fica vazio até a resposta chegar, que é a afirmação honesta sobre um
        livro que acabou de abrir.
        """
        self._salvos = {}
        if self._pdf is not None:
            self._leitor_de_marcas.pedir(self._pdf)

    def _marcas_chegaram(self, livro: str, marcas: object) -> None:
        if self._pdf is None or livro != self._pdf.name:
            return
        self._salvos = dict(marcas or {})
        self._atualizar_abas()
        # O aviso de treino da página veio na mesma leitura (ver `_aviso_de_treino`).
        self.campo.atualizar()

    def abrir_pdf(self, caminho: Path) -> None:
        """Abre um livro. Delegado ao painel, que é quem conta as páginas e rasteriza."""
        self.pdf.load_pdf(Path(caminho))

    def abrir_livro_padrao(self) -> bool:
        """Abre o primeiro PDF de `PDF/`, se houver um. Devolve se abriu.

        Mesma conveniência do produto e mesmo limite: **não** é erro não haver livro nenhum -- um
        checkout novo não tem a pasta, e a janela tem de abrir mesmo assim.
        """
        caminho = find_default_pdf_path()
        if caminho is None:
            return False
        self.abrir_pdf(caminho)
        return True

    def abrir_livro_da_sessao(self) -> bool:
        """O livro em que a sessão anterior parou; sem ele, o primeiro de `PDF/` (S-25).

        **É esta que a abertura do programa chama**, e não `abrir_livro_padrao`: começar sempre no
        primeiro livro da pasta é o mesmo que não lembrar de nada, e quem trabalha um livro por
        semana o reabre à mão toda vez.

        Um `last_pdf` que não existe mais **é dito**, e não engolido: o livro pode ter mudado de
        pasta, e sem a frase a pessoa só vê outro livro abrir sem saber por quê.
        """
        guardado = self._estado.last_pdf.strip()
        if not guardado:
            return self.abrir_livro_padrao()
        caminho = Path(guardado)
        if not caminho.exists():
            logger.warning("Último livro do estado não existe mais: %s", caminho)
            self._dizer(f"Último livro não encontrado: {caminho}", estado_do_rodape.AVISO)
            return self.abrir_livro_padrao()
        self.abrir_pdf(caminho)
        return True

    def _pagina_apareceu(self, pagina: int) -> None:
        """A página está na tela: traz de volta o que já se sabe dela.

        **Depois do desenho, e não antes**: restaurar o editor para uma página que ainda não está
        na tela é o sintoma que a Fase 5 corrigiu -- o seletor apontando para diagramas que não
        são os da página exibida.
        """
        self._candidatos = None
        self._itens = []
        self._estudar_ao_ler = None
        self._leitura_adiada.stop()
        self._aquecimento.adiar()  # C2: a página virou; o aquecimento espera a janela ociar
        # **A página entra no histórico assim que aparece, e não só no fechamento** (S-25). É o
        # que faz a pergunta "onde eu parei neste livro?" continuar respondida depois de trocar de
        # livro no meio da sessão -- e é a mesma anotação que ordena o menu de recentes.
        if self._pdf is not None:
            self._estado.remember_page(self._pdf, pagina)
        self.painel.restaurar_pagina(pagina)
        guardadas = self._caixas_por_pagina.get(self._chave_do_documento(), pagina, self._parametros())
        self._publicar_caixas(guardadas)
        # A galeria acompanha a página, e ela mesma ignora o aviso quando foi ela quem pediu a
        # virada -- senão as duas se chamariam em círculo (S-67).
        self.galeria.sync_to_page(pagina)
        # A anotação de campo é sobre a página exibida: virou a página, ela diz de novo se esta
        # já está anotada e se há amostra de treino dela (S-97).
        self.campo.atualizar()
        self._atualizar_titulo()
        self._dizer_o_que_ha_na_pagina()
        if guardadas is None:
            self._detectar_ao_fundo(pagina)

    def _detectar_ao_fundo(self, pagina: int) -> None:
        """Manda o detector procurar os diagramas desta página, sem trancar nada (S-68).

        **O critério de aceite da S-68 é que os retângulos apareçam antes de qualquer OCR**, e o
        porte para o Qt só os pedia pelo botão "Marcar diagramas": sem ele, o clique na página
        não achava caixa nenhuma. Só quando o cache não sabe da página -- uma página de prosa já
        visitada guarda a resposta vazia, e o detector não a percorre de novo.
        """
        pdf, pagina_rgb, teto = self._pdf, self.pdf.page_rgb, _max_boards()
        if pdf is None or pagina_rgb is None:
            return
        if self._rasterizar_ao_fundo:
            # **No processo de trabalho, e não na thread** (passo 15): a detecção é um segundo de
            # Python, numpy e OpenCV que, numa thread, reveza o GIL com a janela e alonga cada
            # troca de aba e cada virada enquanto corre. O filho rasteriza a página de novo em vez
            # de receber os 26 MB dela -- ver `detect_diagrams_rendering_page`.
            dpi = int(_dpi())
            self._detector.pedir(
                self._chave_do_documento(),
                pagina,
                lambda: processo_de_trabalho().executar(
                    detect_diagrams_rendering_page, pdf, pagina, dpi=dpi, max_boards=teto
                ),
            )
            return
        self._detector.pedir(
            self._chave_do_documento(),
            pagina,
            lambda: detect_diagrams_in_pdf_page(pdf, pagina, pagina_rgb, max_boards=teto),
        )

    def _chegou_a_deteccao_de_fundo(self, documento: str, pagina: int, candidatos: Any) -> None:
        """De outro livro, o resultado é descartado: o cache é por documento, e o livro que saiu
        levou o dele. Da página certa ou de uma que já virou, é o mesmo caminho do botão."""
        if documento == self._chave_do_documento():
            self._chegaram_candidatos(pagina, candidatos)

    # ------------------------------------------------------------------------------ leitura

    def _parametros(self) -> OverlayParams:
        return OverlayParams(dpi=_dpi(), max_boards=_max_boards())

    def _parametros_de_ocr(self) -> PageOcrParams:
        """Com que parâmetros a página foi lida. É a chave do cache do painel de Resultado.

        **Inclui o modelo e a orientação, e não só o DPI**: uma leitura feita com outro `.pt` não
        responde pela mesma página, e restaurá-la calada seria mostrar o resultado de um modelo
        dizendo que é o do outro.
        """
        return PageOcrParams(
            model_path=str(DEFAULT_MODEL_PATH),
            orientation=DEFAULT_ORIENTATION_MODE,
            max_boards=_max_boards(),
            dpi=_dpi(),
        )

    def _opcoes(self, max_diagramas: int | None = None) -> RecognitionOptions:
        """As opções de reconhecimento. `max_diagramas` é o que separa "melhor" de "todos"."""
        return RecognitionOptions(
            model_path=DEFAULT_MODEL_PATH,
            orientation=DEFAULT_ORIENTATION_MODE,
            max_boards=_max_boards() if max_diagramas is None else max_diagramas,
            dpi=_dpi(),
        )

    def _chave_do_documento(self) -> str:
        return str(self._pdf) if self._pdf is not None else ""

    def marcar_diagramas(self) -> None:
        """Só localiza: desenha as caixas sem carregar o modelo.

        É o passo barato, e ele tem valor próprio -- diz **quantos** diagramas a página tem e
        onde, que é o que decide se vale gastar a leitura nela.
        """
        pagina_rgb = self.pdf.page_rgb
        if self._pdf is None or pagina_rgb is None:
            self._dizer("Abra um PDF antes de marcar os diagramas.")
            return

        guardados = self._candidatos_desta_pagina()
        if guardados is not None:
            # **Marcar de novo não redetecta.** O detector é determinístico e receberia a mesma
            # página com os mesmos parâmetros: a segunda varredura devolveria caixa por caixa o
            # que já está na tela, por ~1 s de espera.
            logger.info(
                "Página %d já estava marcada: %d diagrama(s), sem redetectar.",
                self.pdf.page_index + 1,
                len(guardados),
            )
            self._chegaram_candidatos(self.pdf.page_index, guardados)
            return

        pdf, pagina, teto = self._pdf, self.pdf.page_index, _max_boards()
        self._rodar(
            lambda: detect_diagrams_in_pdf_page(pdf, pagina, pagina_rgb, max_boards=teto),
            nome="detecção",
            aviso=f"Procurando diagramas na página {pagina + 1}…",
            quando_pronto=lambda candidatos: self._chegaram_candidatos(pagina, candidatos),
        )

    def ler_melhor(self) -> None:
        """Lê **um** diagrama da página, e não todos (`max_boards=1`).

        **A diferença tinha sumido no porte** (S-506). No Tk eram dois caminhos, `ocr_best` e
        `ocr_all`, e o que os separava era o teto de diagramas; aqui os dois nomes do catálogo
        apontavam para `ler_pagina`, então "OCR melhor diagrama" lia a página inteira. Ninguém
        acusava: os dois comandos tinham dono, e o dono era chamável -- é o limite da conta do
        catálogo, que pergunta se há dono e não se o dono é o certo.
        """
        self.ler_pagina(max_diagramas=1)

    def ler_pagina(self, *, selecionar_depois: int | None = None, max_diagramas: int | None = None) -> None:
        """O caminho completo: detecta, prevê, decide a vez e confere a legalidade.

        A página inteira, e não o diagrama clicado, pelo motivo que `decide_box_click` registra: o
        recorte isolado perde a imagem embutida do PDF e o contexto de texto que decide o lado a
        jogar, e sairia lido pior sem que nada na tela dissesse por quê.

        `max_diagramas` é o teto: `None` usa a preferência inteira e `1` é o "melhor diagrama".
        """
        pagina_rgb = self.pdf.page_rgb
        if self._pdf is None or pagina_rgb is None:
            self._dizer("Abra um PDF antes de ler a página.")
            return
        pdf, pagina, opcoes = self._pdf, self.pdf.page_index, self._opcoes(max_diagramas)
        candidatos = self._candidatos_desta_pagina()
        # **A leitura diz no log de onde vieram os diagramas.** Sem esta linha, o rastro de uma
        # sessão não distingue "marcar e depois ler" de "ler sozinho": os dois deixam uma varredura
        # do detector e nada mais.
        logger.info(
            "Lendo a página %d — %s.",
            pagina + 1,
            f"{len(candidatos)} diagrama(s) já localizados" if candidatos is not None else "detectando por dentro",
        )
        # C2: progresso por diagrama e cancelamento entre eles vão ao serviço (`qt/leitura.py`).
        tarefa: Tarefa | None = None

        def ler() -> list[RecognizedDiagram]:
            return self._servico.recognize_page(
                pdf, pagina, pagina_rgb, options=opcoes, candidates=candidatos,
                progress=self._ocupacao.progresso(f"página {pagina + 1}"),
                should_cancel=lambda: bool(tarefa is not None and tarefa.should_cancel()),
            )

        tarefa = self._rodar(
            ler,
            nome="leitura",
            aviso=f"Lendo a página {pagina + 1}…",
            quando_pronto=lambda itens: self._chegaram_itens(pagina, itens, selecionar_depois),
            total=len(candidatos) if candidatos is not None else 0,
            cancelavel=True,
        )

    def _ler_regiao(self, pagina_rgb: object, regiao: object) -> None:
        """A área que a seleção do visualizador devolveu, em pixel de página (S-31).

        Recortar, grampear aos limites e decidir o que fazer sem contorno é do serviço; o que a
        janela faz é só levar o retângulo até ele -- e é por isso que este método cabe em quatro
        linhas.
        """
        if self._pdf is None:
            return
        opcoes = self._opcoes()
        pagina = cast("Any", pagina_rgb)
        caixa = cast("tuple[int, int, int, int]", regiao)
        self._rodar(
            lambda: self._servico.recognize_region(pagina, caixa, options=opcoes),
            nome="leitura da área",
            aviso="Lendo a área selecionada…",
            quando_pronto=self._chegou_a_area,
        )

    def _chegou_a_area(self, itens: Any) -> None:
        """O que saiu do recorte. **Vínculo `NONE`**: não há página para onde voltar (S-49)."""
        lista = list(itens)
        if not lista:
            self._dizer("Nenhum diagrama encontrado na área selecionada.")
            return
        self.painel.carregar_avulsos(lista)
        self._focar_aba(self.painel)

    def _rodar(
        self,
        funcao: Callable[[], Any],
        *,
        nome: str,
        aviso: str,
        quando_pronto: Callable[[Any], None],
        total: int = 0,
        cancelavel: bool = False,
    ) -> Tarefa | None:
        """Uma tarefa de cada vez, e só o **gravar** desligado enquanto ela corre.

        Não é cerimônia: duas leituras simultâneas disputariam o mesmo modelo (o `OcrService` as
        serializa no lock, então a segunda só esperaria) e a segunda a terminar sobrescreveria a
        lista da primeira -- que pode ser de outra página.

        Registrada no rodapé desde o C2: barra com `total` quando a página já foi marcada, e o
        «Cancelar» chega à tarefa, que o serviço consulta entre diagramas (`qt/leitura.py`).
        """
        if self._tarefa is not None:
            self._dizer("Já há uma tarefa em andamento.", estado_do_rodape.AVISO)
            return None
        # **Sem pai** (`manter_viva`, F9-C2): filha da janela, a `Tarefa` seria destruída com ela
        # e o destrutor de `QThread` aborta o processo com a thread a correr -- o `closeEvent`
        # espera `ESPERA_AO_FECHAR_MS`, mas uma leitura mais longa que isso (crítico Codex, fase 2
        # ciclo 1) não pode derrubar quem fecha. `manter_viva` solta e destrói a thread ao fim; os
        # slots perguntam se a janela ainda existe antes de a tocar.
        tarefa = manter_viva(Tarefa(funcao, nome=nome))
        tarefa.pronto.connect(self._se_viva(quando_pronto))
        tarefa.falhou.connect(self._se_viva(self._falhou))
        tarefa.finished.connect(self._se_viva(self._terminou))
        self._tarefa = tarefa
        # O `register` fica aqui, e não na `Ocupacao`, porque o portão `caissa.ui.audit.progresso`
        # atribui cada thread ao registro feito na mesma função -- e é ele que exige `total=`.
        self._ocupacao.guardar(self.busy.register(
            nome, loses_work=False, cancellable=cancelavel,
            cancel=tarefa.cancelar if cancelavel else None, detail=aviso, total=total,
        ))
        self.rodape.mostrar(aviso)
        self._atualizar_controles()
        tarefa.start()
        return tarefa

    def _se_viva(self, slot: Callable[..., Any]) -> Callable[..., None]:
        """`slot`, só enquanto esta janela existir: uma tarefa sem pai termina depois de a janela
        fechar, e um slot que tocasse widget morto levantaria dentro do laço de eventos."""
        janela = weakref.ref(self)

        def chamar(*args: Any) -> None:
            viva = janela()
            if viva is not None and not sip.isdeleted(viva):
                slot(*args)

        return chamar

    def _terminou(self) -> None:
        self._tarefa = None
        self._estudar_ao_ler = None
        self._ocupacao.soltar()
        self._atualizar_controles()

    def _falhou(self, mensagem: str, excecao: object) -> None:
        """Nenhum diagrama na página **não** é erro: é uma página de prosa, e há muitas.

        Tratá-la como falha ensinaria a pessoa a ignorar a caixa de erro, que é o que faz a caixa
        deixar de servir quando a falha for de verdade.
        """
        if isinstance(excecao, NoBoardDetectedError):
            self._dizer("Nenhum diagrama encontrado nesta página.", estado_do_rodape.INFORMACAO)
            return
        if isinstance(excecao, RecognitionCanceled):  # C2: cancelar não é falha; o lido fica
            lidos = list(excecao.partial)
            if lidos and self._pdf is not None:
                self._chegaram_itens(self.pdf.page_index, lidos, None)
            self._dizer(leitura.frase_de_cancelamento(len(lidos)), estado_do_rodape.INFORMACAO)
            return
        if leitura.sem_modelo(excecao):  # C2: sem o `.pt`, a frase diz onde se aponta o arquivo
            self._dizer(leitura.FRASE_SEM_MODELO, estado_do_rodape.ERRO)
            self.painel.mostrar_vazio_sem_modelo()
            return
        tarefa = self._tarefa  # o rastro vai na caixa, atrás de «Detalhes», com «Copiar» (A10)
        rastro = (tarefa.rastro if tarefa is not None else "") or rastro_de(excecao)
        dialogos.mostrar_falha(self, strings.titulo_de_falha(tarefa.nome if tarefa else "leitura"), mensagem, rastro)
        self._dizer(mensagem, estado_do_rodape.ERRO)

    # ------------------------------------------------------------------------------ resposta

    def _candidatos_desta_pagina(self) -> tuple[DiagramCandidate, ...] | None:
        """Os candidatos guardados, **se** forem da página que está na tela.

        A comparação é o ponto: sem ela, uma detecção que terminou depois da virada entregaria à
        leitura os diagramas da página anterior -- e eles seriam lidos, numerados e mostrados como
        se fossem daqui.
        """
        if self._candidatos is None or self._candidatos[0] != self.pdf.page_index:
            return None
        return self._candidatos[1]

    def _chegaram_candidatos(self, pagina: int, candidatos: Any) -> None:
        caixas = self._caixas_sem_desaprender(pagina, boxes_from_candidates(candidatos))
        self._guardar(caixas)
        if pagina != self.pdf.page_index:
            # A página virou enquanto a detecção corria. As caixas ainda valem -- para **aquela**
            # página --, então ficam no cache e não vão para a tela. Os candidatos também não
            # ficam: `_candidatos` é da página exibida, e a leitura os passaria como dela.
            return
        self._candidatos = (pagina, tuple(candidatos))
        self._publicar_caixas(caixas)
        self._dizer_o_que_ha_na_pagina()

    def _caixas_sem_desaprender(self, pagina: int, detectadas: tuple[DiagramBox, ...]) -> PageBoxes:
        """As caixas do detector, deixando ganhar o que já foi lido **desta** página.

        **O defeito que isto fecha**: marcar depois de ler rebaixava os retângulos de "lido" para
        "a fazer". A lista ao lado continuava mostrando os diagramas com FEN e confiança, e a
        página passava a dizer que não havia leitura nenhuma -- a tela desaprendendo o que ela
        mesma acabara de mostrar.
        """
        lidas = boxes_from_diagrams(self._itens) if pagina == self.pdf.page_index else ()
        return PageBoxes(pagina, self._parametros(), choose_boxes(recognized=lidas, detected=detectadas))

    def _chegaram_itens(self, pagina: int, itens: list[RecognizedDiagram], selecionar: int | None) -> None:
        if pagina != self.pdf.page_index:
            self._dizer(f"A leitura da página {pagina + 1} terminou, mas a tela já está em outra.")
            return
        self._itens = list(itens)
        # **O ponto único de troca de vínculo** (S-49), dentro do painel: o vínculo é `PAGE` e a
        # âncora é o par (documento, página), e é ela que faz `Ctrl+S` gravar amostra nova em vez
        # de regravar a linha de um dataset que não está aberto.
        self.painel.carregar_pagina(self._itens, chave=self._chave_do_documento(), pagina=pagina)

        lidas = boxes_from_diagrams(self._itens)
        guardadas = self._caixas_por_pagina.get(self._chave_do_documento(), pagina, self._parametros())
        caixas = PageBoxes(
            pagina,
            self._parametros(),
            choose_boxes(recognized=lidas, detected=guardadas.boxes if guardadas else ()),
        )
        self._guardar(caixas)
        self._publicar_caixas(caixas)

        if self._itens and selecionar is not None and selecionar < len(self._itens):
            self.painel.lista.setCurrentRow(selecionar)
        pendente, self._estudar_ao_ler = self._estudar_ao_ler, None
        if pendente is not None and pendente[0] == pagina and pendente[1] < len(self._itens):
            self.painel.lista.setCurrentRow(pendente[1])
            self._levar_ao_estudo()
        self._atualizar_abas()
        self._dizer_o_que_ha_na_pagina()

    def _guardar(self, caixas: PageBoxes) -> None:
        self._caixas_por_pagina.put(self._chave_do_documento(), caixas)

    def _publicar_caixas(self, caixas: PageBoxes | None) -> None:
        """Manda as caixas para a tela, tirando as recusadas e carimbando o que já foi salvo.

        **O carimbo não entra no cache** (S-71): se entrasse, salvar uma amostra não pintaria de
        verde o diagrama recém-salvo -- ele só mudaria de cor na próxima visita à página.

        A remoção também não: ela é da pessoa e por (livro, página), e guardá-la no cache faria
        uma redetecção trazer de volta o falso positivo que já foi recusado.
        """
        if caixas is None:
            self.pdf.limpar_caixas()
            return
        visiveis = self._tiradas.apply(self._chave_do_documento(), caixas.page_index, caixas.boxes)
        salvos = self._salvos.get(caixas.page_index, set())
        # O «corrigido» (passo 13) vem do editor, e só quando ele está mostrando **esta** página.
        na_pagina = self.painel.modelo.page_key == (self._chave_do_documento(), caixas.page_index)
        editados = self.painel.modelo.hand_edited_indices() if na_pagina else frozenset()
        marcadas = mark_edited(mark_saved(visiveis, salvos), editados)
        self.pdf.definir_caixas(PageBoxes(caixas.page_index, caixas.params, marcadas))

    def _recarimbar_caixas(self) -> None:
        """Repõe as caixas da página com os carimbos de agora -- a correção acabou de acontecer."""
        guardadas = self._caixas_por_pagina.get(self._chave_do_documento(), self.pdf.page_index, self._parametros())
        if guardadas is not None:
            self._publicar_caixas(guardadas)

    # -------------------------------------------------------------------------------- seleção

    def _clicou_na_caixa(self, indice: int) -> None:
        """Clique numa caixa: seleciona o diagrama lido, ou lê a página se ela ainda não foi.

        Quem decide entre os dois é `page_overlay.decide_box_click`, que é puro -- e a decisão não
        é óbvia: ler **a página** e não o recorte é o que preserva a imagem embutida do PDF e o
        contexto de texto que decide o lado a jogar.
        """
        acao = decide_box_click(recognized_count=len(self._itens), index=indice)
        if acao is BoxClick.SELECT:
            self.painel.lista.setCurrentRow(indice)
            self._focar_aba(self.painel)
            return
        # Adiada, e não imediata: ver `_leitura_adiada`. Um duplo clique a cancela.
        self._caixa_a_ler = indice
        self._leitura_adiada.start(QApplication.doubleClickInterval())

    def _ler_a_caixa_clicada(self) -> None:
        """O intervalo do duplo clique passou sem segundo aperto: era um clique, e ele lê."""
        indice, self._caixa_a_ler = self._caixa_a_ler, None
        if indice is not None:
            self.ler_pagina(selecionar_depois=indice)

    def _estudar_a_caixa(self, indice: int) -> None:
        """Duplo clique numa caixa: o diagrama vai para a sala de estudo.

        **A mesma decisão do clique simples, com outro destino.** Já lido, o diagrama é
        selecionado e a sala o abre; ainda não, a página é lida e a sala o recebe quando a leitura
        chegar. O primeiro clique do par tinha adiado essa leitura (`_leitura_adiada`); o duplo a
        cancela e lê ele mesmo, com o pedido anotado para `_chegaram_itens`. Se uma leitura já
        corre por outro motivo, não se pede uma segunda: o pedido espera por ela.
        """
        self._leitura_adiada.stop()
        self._caixa_a_ler = None
        if decide_box_click(recognized_count=len(self._itens), index=indice) is BoxClick.SELECT:
            self.painel.lista.setCurrentRow(indice)
            self._levar_ao_estudo()
            return
        self._estudar_ao_ler = (self.pdf.page_index, indice)
        if self._tarefa is None:
            self.ler_pagina(selecionar_depois=indice)

    def _levar_ao_estudo(self) -> None:
        """Abre na sala o diagrama selecionado no Resultado e traz a aba -- se houver posição."""
        if self.estudo.load_from_recognized():
            self._focar_aba(self.estudo)

    def _tirar_caixa(self, indice: int) -> None:
        """Tira aquele retângulo da página (S-177). A remoção é por (livro, página).

        **Não apaga nada no disco**, e é o que a torna reversível: o detector continua achando o
        mesmo falso positivo, e "Devolver as caixas" desfaz a recusa desta página.
        """
        documento, pagina = self._chave_do_documento(), self.pdf.page_index
        guardadas = self._caixas_por_pagina.get(documento, pagina, self._parametros())
        alvo = next(
            (caixa for caixa in (guardadas.boxes if guardadas else ()) if caixa.index == int(indice)),
            None,
        )
        if alvo is None or not self.pdf.boxes or all(
            caixa.index != int(indice) for caixa in self.pdf.boxes.boxes
        ):
            self._dizer(f"A caixa {indice + 1} não está mais na página.")
            return
        self._tiradas.drop(documento, pagina, alvo.bbox_pdf)
        self._publicar_caixas(guardadas)
        quantas = self._tiradas.count(documento, pagina)
        recado = (
            f"Caixa {indice + 1} tirada desta página. Devolver as caixas traz de volta."
            if quantas == 1
            else f"Caixa {indice + 1} tirada: {quantas} caixas tiradas desta página."
        )
        self._dizer(recado)

    def devolver_caixas(self) -> None:
        """Desfaz as remoções **desta página**, e diz quantas voltaram."""
        documento, pagina = self._chave_do_documento(), self.pdf.page_index
        quantas = self._tiradas.restore(documento, pagina)
        if not quantas:
            self._dizer("Nenhuma caixa foi tirada desta página.")
            return
        self._publicar_caixas(self._caixas_por_pagina.get(documento, pagina, self._parametros()))
        plural = "" if quantas == 1 else "s"
        self._dizer(f"{quantas} caixa{plural} devolvida{plural} a esta página.")

    # --------------------------------------------------- o que um painel entrega a outro

    def _gravou_amostra(self, indice: int) -> None:
        """O Resultado gravou: carimba a caixa de verde, e conta de novo.

        O carimbo não entra no cache (S-71): se entrasse, salvar não pintaria o diagrama
        recém-salvo -- ele só mudaria de cor na próxima visita à página.
        """
        self._salvos.setdefault(self.pdf.page_index, set()).add(indice)
        self._publicar_caixas(
            self._caixas_por_pagina.get(self._chave_do_documento(), self.pdf.page_index, self._parametros())
        )
        self.dataset.reload()
        self._atualizar_abas()
        self._atualizar_controles()
        if self.livro is not None:
            self.livro.atualizar_trilho()  # C8: a decisão gravada tira a página da conta de dúvidas

    def _fechar_item_da_fila(self, posicao: int, fen: str, lado: str) -> None:
        """Fecha na fila o item que acabou de ser corrigido e salvo (S-22)."""
        self.revisao.aplicar_correcao(int(posicao), fen, lado)
        self._atualizar_abas()
        if self.livro is not None:
            self.livro.atualizar_trilho()  # C8
        self._dizer(f"Item da fila marcado como revisado. {self.revisao.queue.summary()}")

    def _abrir_item_da_fila(self, item: object, posicao: int) -> None:
        """A Revisão mandou corrigir: o Resultado abre o item, e a aba dele vem para a frente.

        **Trazer a aba é parte do gesto**, e não zelo: abrir o item numa aba que ninguém está
        vendo é a mesma classe de silêncio que a S-161 registra -- a ação acontece e nada na tela
        diz que aconteceu.
        """
        if self.painel.carregar_item_de_revisao(item, int(posicao)):
            self._focar_aba(self.painel)

    def _abrir_amostra(self, row: object) -> None:
        """O Dataset mandou editar: o Resultado abre a amostra, e salvar **regrava** a linha."""
        _csv, samples_dir, _splits = self._caminhos_do_dataset()
        if self.painel.carregar_amostra(row, samples_dir):
            self._focar_aba(self.painel)

    def _dataset_mudou(self) -> None:
        """Uma linha do `labels.csv` mudou. A aba Dataset relê -- se estiver à vista (S-116)."""
        self.dataset.reload()
        self._atualizar_abas()

    def _anotacoes_mudaram(self) -> None:
        """A Galeria escreveu no arquivo do livro: o violeta da página volta, e as abas recontam.

        O violeta é `confirmed_from`, gravado quando se escolhe uma partida da base (S-75). Ele
        vem do arquivo de anotações e aparece **antes de qualquer OCR** -- por isso releitura e
        não recontagem.
        """
        self._publicar_caixas(
            self._caixas_por_pagina.get(self._chave_do_documento(), self.pdf.page_index, self._parametros())
        )
        self._atualizar_abas()

    def _focar_aba(self, painel: QWidget) -> None:
        """Traz para a frente o painel que acabou de receber alguma coisa -- aba ou modo."""
        self.abas.mostrar(painel)

    # ---------------------------------------------------- o que a sala de estudo pergunta

    def _posicao_de_estudo(self) -> Any:
        """A posição do diagrama selecionado, **inteira**, para a sala (S-269).

        Quem monta é `ui/study_panel.posicao_do_painel`, que é afirmável sem janela; aqui só se
        diz de onde vem o número do lance, que é anotação da Galeria (S-67).
        """
        return self.painel.posicao_de_estudo(lance_de=self.galeria.move_number_at)

    def _recorte_do_diagrama(self, ancora: Any) -> Any:
        """O recorte do diagrama âncora, como o painel de Resultado o tem em memória (S-282).

        `None` quando o estudo é de outra página ou de FEN digitada à mão -- e é aí que o botão do
        recorte fica cinza, que é o que a dica dele promete.
        """
        return self.painel.recorte_de(ancora)

    def _linha_impressa(self, ancora: Any) -> str:
        """A notação que a aba Texto leu ao lado daquele diagrama, ou `""` (S-283)."""
        return self.texto.notacao_do_diagrama(int(ancora.pagina), int(ancora.diagrama))

    def _abrir_pagina_do_estudo(self, ancora: Any) -> bool:
        """Leva o visualizador à página daquele diagrama (S-284). `False` se o livro não é este."""
        if self._chave_do_documento() != ancora.documento:
            return False
        self.pdf.ir_para_pagina(int(ancora.pagina))
        return True

    def _linha_para_o_texto(self, linha: str) -> bool:
        """Insere a linha do estudo no cursor da aba de texto (S-289), e traz a aba."""
        self.texto.inserir_simbolo(linha)
        self._focar_aba(self.texto)
        return True

    # ------------------------------------------------------- o que os outros perguntam

    def _colocacoes_conferidas(self) -> dict[int, tuple[str, bool]]:
        """As duas listas paralelas da página exibida, entregues a
        `ui/page_results.colocacoes_conferidas` -- que é onde o *porquê* de ler `fen_edits` mora.

        A única parte que precisa da janela é achá-las: no modelo, se ele é desta página; no cache
        de páginas, se não.
        """
        modelo = self.painel.modelo
        pagina = self.pdf.page_index
        if modelo.page_key == (self._chave_do_documento(), pagina):
            itens, edicoes = modelo.items, modelo.fen_edits
        else:
            guardado = self.painel.paginas.get(
                self._chave_do_documento(), pagina, self._parametros_de_ocr()
            )
            if guardado is None:
                return {}
            itens, edicoes = list(guardado.items), list(guardado.fen_edits)
        return colocacoes_conferidas(itens, edicoes)

    def _aviso_de_treino(self) -> str:
        """" · N amostra(s) de treino desta página" quando houver, senão string vazia (S-97).

        **A leitura saiu daqui no F9-C3**, e o número desmente o argumento antigo ("virar página
        é um gesto por vez"): eram **50,5 ms de 166,2 ms por virada, 30 % dela e 3,2x o portão**.
        Quem guarda a resposta por `(tamanho, mtime)` é `qt/marcas.paginas_com_amostra_de_treino`.
        """
        if self._pdf is None:
            return ""
        csv_path, _amostras, splits_path = self._caminhos_do_dataset()
        # **Só a resposta guardada** (passo 15): a leitura fria roda no processo de trabalho com
        # as marcas do livro, e `_marcas_chegaram` manda o campo escrever de novo quando ela vier.
        paginas = amostras_de_treino_guardadas(csv_path, splits_path)
        if paginas is None:
            return ""
        quantas = paginas.get((self._pdf.name, self.pdf.page_index), 0)
        return f" · ⚠ {quantas} amostra(s) de treino desta página" if quantas else ""

    def _caminhos_do_dataset(self) -> tuple[Path, Path, Path]:
        base = self._csv_de_rotulos.parent
        return (self._csv_de_rotulos, base / "samples", base / "splits.csv")

    def _pedido_de_varredura(self) -> PedidoDeVarredura | None:
        """Os parâmetros da varredura, como esta janela os tem. `None` sem livro aberto."""
        if self._pdf is None:
            return None
        return PedidoDeVarredura(
            pdf_path=self._pdf,
            model_path=DEFAULT_MODEL_PATH,
            labels_csv=self._csv_de_rotulos,
            dpi=_dpi(),
            max_boards_per_page=_max_boards(),
        )

    def _pedido_de_treino(self) -> TrainingRequest:
        # Épocas, lote e taxa vêm de `data/settings.json` (Ferramentas ▸ Configurações…), lidos
        # no clique: o que a pessoa mudou na janela vale para o próximo treino, não para este.
        return pedido_de_treino(*self._caminhos_do_dataset(), model_path=DEFAULT_MODEL_PATH)

    def _alternar_trilho(self) -> None:
        # `isHidden` e não `isVisible`: antes de a janela aparecer, `isVisible` é falso para tudo.
        mostrar = self.trilho.isHidden()
        self.trilho.setVisible(mostrar)
        self.menu.marcar("trilho", ligado=mostrar)

    def _exportar_livro(self, formato: str) -> None:
        """O diálogo da suíte (`qt/exportador_de_livro.py`); sem ela, o motivo vai ao rodapé."""
        if self.exportador_de_livro is None:
            self._dizer(exportador_de_livro.MOTIVO_AUSENTE.splitlines()[0])
            return
        self.exportador_de_livro.comecar(
            self._pdf, self.pdf.page_count, formato=formato, pagina_atual=self.pdf.page_index,
            documento_para=self.livro.documento_para if self.livro else None,  # A3: sem reimportar
        )

    def _configuracao_de_exportacao(self) -> ExportSettings:
        return ExportSettings(
            model_path=DEFAULT_MODEL_PATH,
            dpi=_dpi(),
            max_boards_per_page=_max_boards(),
            orientation=DEFAULT_ORIENTATION_MODE,
        )

    def _treino_terminou(self) -> None:
        """O `.pt` em memória pode não ser mais o que está no disco (S-31)."""
        self.treino.concluir()
        self._servico.invalidate_model(DEFAULT_MODEL_PATH)
        self._dizer("Treino encerrado. O modelo em memória foi recarregado.")

    # ------------------------------------------------------------------- a tabela de comandos

    def _comandos(self) -> dict[str, Callable[[], object]]:
        """`ação do catálogo -> o que ela faz nesta janela`. **A soma de três tabelas.**

        A desta janela, mais as duas `COMANDOS_DA_ABA` -- a da sala de estudo (31 comandos) e a da
        aba de texto (48). As duas são declarações dos próprios painéis, e é por isso que os
        métodos do Qt se chamam igual aos do Tk: a tabela é uma só, e uma segunda seria o lugar
        onde um comando some sem ninguém notar -- ele continua no catálogo, no menu e nas três
        peles, e não faz nada.

        **Daqui saem o menu, a paleta e os atalhos**, e é o que garante que os três digam a mesma
        coisa. `qt/menu.montar` levanta nomeando o item que não tiver comando: um menu que desenha
        uma linha inerte é pior que um menu sem ela.
        """
        tabela: dict[str, Callable[[], object]] = {
            # --- o livro
            "abrir_pdf": self.pdf.abrir_pdf,
            "abrir_recente": self._abrir_o_mais_recente,
            "abrir_no_leitor": self.pdf.abrir_no_leitor_do_sistema,
            "sair": self.close,
            # --- navegar
            "pagina_anterior": lambda: self._na_aba_ou(self.pdf.pagina_anterior, "pagina_anterior"),
            "proxima_pagina": lambda: self._na_aba_ou(self.pdf.proxima_pagina, "proxima_pagina"),
            "primeira_pagina": lambda: self.pdf.ir_para_pagina(0),
            "ultima_pagina": lambda: self.pdf.ir_para_pagina(self.pdf.page_count - 1),
            "zoom_mais": self.pdf.aumentar_zoom,
            "zoom_menos": self.pdf.diminuir_zoom,
            "ajustar_largura": self.pdf.ajustar_a_largura,
            "ajustar_pagina": self.pdf.ajustar_a_pagina,
            "marcar_diagramas": lambda: self.pdf.marcar_diagramas.toggle(),
            "roda_vira_pagina": lambda: self.pdf.roda_vira_pagina.toggle(),
            "selecionar_area": self.pdf.alternar_selecao,
            "tirar_caixa": self.pdf.dispensar_a_selecionada,
            "devolver_caixas": self.devolver_caixas,
            # --- ler e gravar
            "ler_pagina": lambda: self._na_aba_ou(self.ler_pagina, "recognise_page"),
            "segunda_opiniao": self.painel.segunda_opiniao,  # C3
            "ler_melhor": self.ler_melhor,
            "salvar": lambda: self._na_aba_ou(self.painel.salvar_atual, "save", "gravar"),
            "salvar_todos": self.painel.salvar_todos,
            "aplicar_fen": self.painel.aplicar_fen,
            "limpar_tabuleiro": self.painel.limpar_tabuleiro,
            "apagar_casa": self._apagar_casa,
            # **Quem desfaz é o foco, e não sempre o tabuleiro** (S-243). Ver `_no_desfazivel`.
            "desfazer": lambda: self._no_desfazivel(lambda alvo: alvo.desfazer()),
            "refazer": lambda: self._no_desfazivel(lambda alvo: alvo.refazer()),
            "diagrama_anterior": lambda: self.painel.andar(-1),
            "proximo_diagrama": lambda: self.painel.andar(1),
            # --- as outras abas
            "proximo_da_fila": self.revisao.abrir_proximo_pendente,
            # **As duas do F9-C3**: ganharam tecla global, e o motivo está em `ui/atalhos.ATALHOS`.
            "corrigir_agora": self.revisao.corrigir_agora,
            "anotar_pagina": self.campo.anotar_pagina,
            "varrer_livro": self.galeria.varrer,
            "exportar_pgn": lambda: self.exportador.comecar(self._pdf),
            "exportar_epub": lambda: self._exportar_livro("epub"),
            "importar_livro": lambda: self.livro.comecar() if self.livro else self._dizer(importador_de_livro.MOTIVO_AUSENTE.splitlines()[0]),
            "cancelar_importacao": lambda: self.livro.cancelar() if self.livro else None,
            "trilho": self._alternar_trilho,
            "primeira_duvidosa": self.trilho._ir_para_a_primeira_duvidosa,
            "proxima_duvidosa": self.trilho.ir_para_a_proxima_duvidosa,
            "anterior_duvidosa": self.trilho.ir_para_a_anterior_duvidosa,
            "exportar_docx": lambda: self._exportar_livro("docx"),
            "cancelar_exportacao": self.exportador.cancelar,
            "treinar": self.treino.iniciar,
            "configuracoes": lambda: dialogo_de_configuracoes.abrir(self, dizer=self._dizer),
            "recarregar_modelo": self._recarregar_modelo,
            # --- a janela
            "aparencia": self._escolher_pele,
            "densidade": self._escolher_densidade,
            "conjunto_de_pecas": self._escolher_conjunto,
            "paleta_de_comandos": self.abrir_paleta,
            "legenda_de_atalhos": lambda: legenda.abrir(self),
            "abrir_log": self._abrir_log,
            "sobre": self._sobre,
        }
        # As duas tabelas dos painéis entram depois: um comando que os dois declarassem seria da
        # aba, e não da janela -- é lá que o método está.
        tabela.update({acao: getattr(self.estudo, metodo) for acao, metodo in COMANDOS_DA_SALA.items()})
        tabela.update({acao: getattr(self.texto, metodo) for acao, metodo in COMANDOS_DO_TEXTO.items()})
        tabela.update(abas_da_suite.donos(self.rotulagem, self.revisao_de_texto, dizer=self._dizer))  # C8
        return tabela

    def _na_aba_ou(self, padrao: Callable[[], Any], *metodos: str) -> Any:
        """O comando global roteado à aba da suíte à frente (C8), senão ao padrão: `Ctrl+S` com a
        Rotulagem à frente grava os rótulos; com a Revisão de texto, as decisões (`qt/abas_da_suite`)."""
        alvo = abas_da_suite.metodo_da_aba_a_frente(self.abas, (self.rotulagem, self.revisao_de_texto), metodos)
        return alvo() if alvo is not None else padrao()

    def abrir_paleta(self) -> Any:
        """A paleta de comandos (S-231): um campo, uma lista filtrada, Enter executa."""
        return paleta.abrir(self, self._comandos())

    def _desfaziveis(self) -> list[desfazivel.Desfazivel]:
        """Os painéis que disputam o `Ctrl+Z`, na ordem de registro -- que é a de construção.

        A ordem decide o empate de `ultimo_editado`, e por isso é uma lista e não um conjunto: uma
        tecla que fizesse coisas diferentes em dois dias iguais é pior que uma que não faz nada.
        """
        return [self.painel, self.texto, self.estudo]

    def _foco(self) -> object:
        """O widget com o foco de teclado, ou `None` -- a janela pode nem estar em primeiro plano."""
        aplicacao = QApplication.instance()
        return aplicacao.focusWidget() if isinstance(aplicacao, QApplication) else None

    def _no_desfazivel(self, acao: Callable[[desfazivel.Desfazivel], None]) -> None:
        """Roda a ação no desfazível que o foco escolhe -- ou avisa que não há nenhum (S-243).

        **A regra é pura e mora em `ui/desfazivel.py`**: o que contém o foco, senão o último que
        recebeu edição, senão nenhum. Aqui só se pergunta quem está com o foco.

        **O passo 2 é o item, e é o que faltava neste frontend.** A declaração de ações da S-244 já
        entrega `Ctrl+Z` à aba de texto e à sala **enquanto o foco está dentro delas**; o que ela
        não cobre é o foco em lugar nenhum dos dois -- num botão da barra, que é onde o cursor fica
        depois de qualquer clique. Ali a tecla ia direto para o tabuleiro, e desfazia a última
        peça arrastada em vez do último parágrafo digitado.
        """
        alvo = desfazivel.alvo_de_desfazer(self._foco(), self._desfaziveis())
        if alvo is None:
            self._dizer("Não há nada para desfazer.")
            return
        acao(alvo)

    def _apagar_casa(self) -> None:
        """`Del`: tira a peça da casa selecionada. O `bool` do tabuleiro é descartado aqui.

        Descartado de propósito e não por um `lambda` que o engole: quem chama pela tecla não tem
        o que fazer com "não havia o que apagar" -- o próprio tabuleiro já não muda nada, e uma
        barra de status dizendo isso a cada `Del` no vazio seria ruído.
        """
        self.painel.tabuleiro.apagar_selecionada()

    def _recarregar_modelo(self) -> None:
        self._servico.invalidate_model(DEFAULT_MODEL_PATH)
        self._dizer("Modelo recarregado do disco.")

    def _abrir_log(self) -> None:
        """Abre a pasta do log no gerenciador de arquivos, ou diz onde ele está.

        `onde_esta_o_rastro` responde as duas coisas -- num checkout sem `CVOFF_LOG_DIR` não há
        arquivo nenhum, e ali a frase é a resposta (S-421).
        """
        from chess_diagram_ocr.logging_setup import onde_esta_o_rastro

        self._dizer(onde_esta_o_rastro())

    def _sobre(self) -> None:
        QMessageBox.about(self, f"Sobre o {strings.PRODUTO}", strings.sobre_o_produto(pele.escolhida()))

    # ------------------------------------------------------------------------------ a tela

    def _atualizar_abas(self) -> None:
        """Põe no rótulo de cada área quanto trabalho ela carrega (S-162) -- aba ou modo.

        Chamado nos pontos em que os números mudam -- abrir livro, salvar amostra, fechar item da
        fila --, e **não num relógio**: a contagem só muda quando alguém a muda, e um disparo
        periódico redesenharia a barra de abas para dizer o mesmo número.
        """
        self.abas.definir_contagens(
            {
                abas.REVISAO: len(self.revisao.queue.pending()),
                abas.DATASET: self.dataset.contagem_de_amostras(),
                abas.GALERIA: len(self.galeria.model),
            }
        )

    def _dizer_o_que_ha_na_pagina(self) -> None:
        """O estado da página no rodapé. A contagem e a frase são de `ui/estado_do_rodape.py`,
        puras e compartilhadas com o Tk -- é por isso que as duas janelas contam igual."""
        if self._pdf is None:
            self.rodape.definir_documento("")
            return
        caixas = self.pdf.boxes
        conta = estado_do_rodape.contagem_das_caixas(caixas.boxes if caixas is not None else ())
        diagramas = estado_do_rodape.descricao_dos_diagramas(
            conta["total"],
            lidos=len(self._itens),
            salvos=conta["salvos"],
            confirmados=conta["confirmados"],
            todos_salvos=conta["todos_salvos"],
        )
        self.rodape.definir_documento(
            estado_do_rodape.descricao_do_documento(
                self._pdf.name, self.pdf.page_index, self.pdf.page_count, diagramas
            ),
            conta["todos_salvos"],
        )

    def _atualizar_titulo(self) -> None:
        livro = self._pdf.name if self._pdf is not None else ""
        base = strings.titulo_da_janela(
            livro,
            self.pdf.page_index if self._pdf is not None else None,
            self.pdf.page_count or None,
        )
        self.setWindowTitle(base)  # já termina no produto (`TITULO_DA_JANELA`); nada de toolkit

    def _atualizar_controles(self) -> None:
        """Desliga o que não faz sentido agora: com uma tarefa em curso.

        **Salvar exige nenhuma tarefa em curso**, e é a única condição que esta janela conhece e o
        painel não: gravar no meio de uma leitura escreveria a amostra de uma página que está
        sendo substituída. O resto dos botões cada painel governa sozinho.
        """
        # C2: só o gravar tranca durante a leitura; o painel inteiro cinza era a página anterior
        # sumindo por segundos. As trancas por recurso (C7) continuam a valer para o painel todo.
        self.painel.setEnabled(not self._trancas)
        self.painel.trancar_gravacao(self._tarefa is not None)

    def closeEvent(self, a0: Any) -> None:  # noqa: N802 - assinatura do Qt
        """Espera a tarefa em curso, grava a sala de estudo e pergunta pelo que se perde.

        Um `QThread` vivo quando o objeto que o representa é destruído derruba o processo com
        `QThread: Destroyed while thread is still running` -- e num bundle isso é uma janela que
        some sem deixar rastro.

        **A espera é limitada, e o limite é generoso**: ler uma página de nove diagramas na CPU
        leva alguns segundos, e fechar no meio disso é gesto comum. Estourar o limite não impede o
        fechamento -- não há nada melhor a fazer com uma thread presa --, mas fica no log.
        """
        perdidas = [operacao for operacao in self.busy.running() if operacao.loses_work]
        editadas = paginas_editadas(self.painel.paginas, self.painel.modelo)  # correções à mão (A7)
        if (perdidas and not self._confirmar_fechamento(perdidas)) or (
            editadas and not dialogos.perguntar_descarte(self, editadas, ao_fechar=True)
        ):
            if a0 is not None:
                a0.ignore()
            return
        # A sala vai para o disco antes de tudo: ela é o único painel cujo trabalho não tem outra
        # cópia, e o `Ctrl+Z` dela não sobrevive à janela (S-271).
        self.estudo.salvar_agora()
        # E o arranjo depois dela, **antes da espera pela tarefa**: uma thread presa não pode
        # custar o último livro, a página e o divisor de quem já mandou fechar (S-156).
        self._gravar_estado()
        self._detector.parar(ESPERA_AO_FECHAR_MS)
        sala_declarada.encerrar_o_motor(self._analisador)
        # As tarefas (a leitura, o aquecimento do modelo) não têm pai desde a fase 2 do ciclo 2:
        # destruí-las a correr derrubava o processo sem rastro (o portão `comandos` mediu: exit
        # 255, nada no log). A espera é cortesia -- sair com a leitura no meio deixa uma thread
        # a terminar sozinha, e `manter_viva` a solta quando acaba.
        self._aquecimento.cancelar()   # o relógio de uma janela fechada não dispara mais
        self._aquecimento.esperar(ESPERA_AO_FECHAR_MS)
        if self._tarefa is not None and not self._tarefa.wait(ESPERA_AO_FECHAR_MS):
            logger.warning("A janela fechou com uma tarefa ainda em andamento; ela termina sozinha.")
        if a0 is not None:
            a0.accept()

    def _confirmar_fechamento(self, perdidas: Sequence[Any]) -> bool:
        """Pergunta antes de fechar sobre uma operação que perde trabalho (S-60/S-112).

        **Só as que perdem**, e é o item: a varredura do livro retoma de onde parou e a busca por
        nome custa a passada de novo -- perguntar sobre elas ensinaria a fechar a caixa sem ler,
        e aí a pergunta que importa (a busca por posição, ~56 min de tudo-ou-nada) passaria batida.
        """
        nomes = ", ".join(operacao.name for operacao in perdidas)
        caixa = QMessageBox(self)
        caixa.setIcon(QMessageBox.Icon.Warning)
        caixa.setWindowTitle("Fechar")
        caixa.setText(f"Estas operações perdem o trabalho feito se a janela fechar agora:\n\n  {nomes}")
        caixa.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        caixa.setDefaultButton(QMessageBox.StandardButton.No)
        return caixa.exec() == QMessageBox.StandardButton.Yes

    def _dispositivos(self) -> Any:
        """Em que dispositivo cada um dos dois modelos torch está (S-182).

        **Relido a cada tique porque nenhum dos dois avisa quando muda**: o de peças carrega na
        primeira leitura da sessão, e o de caracteres é trocado quando um retreino reescreve o
        `.pt`.
        """
        from chess_diagram_ocr.ui import dispositivos as dispositivos_mod
        from chess_diagram_ocr.ui.estado_do_rodape import DESLIGADO, Dispositivos

        return Dispositivos(
            pecas=self._servico.device_label if self._servico.device else None,
            caracteres=dispositivos_mod.descricao_do_classificador_de_caracteres(),
            motivo="",
            ausencia=DESLIGADO,
        )
