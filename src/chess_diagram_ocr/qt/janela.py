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
    PDF  --caixa_clicada-->    esta janela decide entre selecionar e ler (`decide_box_click`)
    PDF  --caixa_dispensada--> a caixa sai da página (S-177)
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
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.board_detection import NoBoardDetectedError
from chess_diagram_ocr.config import (
    DEFAULT_DATASET_CSV,
    DEFAULT_DPI,
    DEFAULT_MAX_BOARDS,
    DEFAULT_MODEL_PATH,
    DEFAULT_ORIENTATION_MODE,
    DEFAULT_PDF_DIR,
    find_default_pdf_path,
)
from chess_diagram_ocr.detection import DiagramCandidate, detect_diagrams_in_pdf_page
from chess_diagram_ocr.labels import LabelStore, pages_with_training_samples, saved_diagrams_by_page
from chess_diagram_ocr.qt import atalhos as qt_atalhos
from chess_diagram_ocr.qt import dica, legenda, menu, paleta, plataforma, tema
from chess_diagram_ocr.qt.campo import PainelDeCampo
from chess_diagram_ocr.qt.dialogos import ControladorDeTreino
from chess_diagram_ocr.qt.exportador import Exportador
from chess_diagram_ocr.qt.painel_da_galeria import PainelDaGaleria
from chess_diagram_ocr.qt.painel_de_estudo import PainelDeEstudo
from chess_diagram_ocr.qt.painel_de_resultado import PainelDeResultado
from chess_diagram_ocr.qt.painel_de_revisao import PainelDeRevisao
from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto
from chess_diagram_ocr.qt.painel_do_dataset import PainelDoDataset
from chess_diagram_ocr.qt.painel_do_pdf import PainelDoPdf
from chess_diagram_ocr.qt.rodape import RodapeDaJanela
from chess_diagram_ocr.qt.trabalho import Tarefa
from chess_diagram_ocr.service import OcrService, RecognitionOptions, RecognizedDiagram
from chess_diagram_ocr.splits import load_splits
from chess_diagram_ocr.ui import abas, espaco, estado_do_rodape, pele, strings
from chess_diagram_ocr.ui.busy import BusyRegistry
from chess_diagram_ocr.ui.editor_model import DiagramEditorModel
from chess_diagram_ocr.ui.exportacao_de_pgn import ExportSettings
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
    mark_saved,
)
from chess_diagram_ocr.ui.page_results import PageOcrParams
from chess_diagram_ocr.ui.pedido_de_treino import TrainingRequest
from chess_diagram_ocr.ui.sala_declarada import COMANDOS_DA_ABA as COMANDOS_DA_SALA
from chess_diagram_ocr.ui.texto_declarado import COMANDOS_DA_ABA as COMANDOS_DO_TEXTO
from chess_diagram_ocr.ui.varredura_de_revisao import PedidoDeVarredura

logger = logging.getLogger(__name__)

__all__ = ["LARGURA_MINIMA_DAS_ABAS", "LARGURA_MINIMA_DO_VISOR", "JanelaPrincipal"]

LARGURA_MINIMA_DAS_ABAS = 720
"""O piso do lado esquerdo, somado das partes em `galeria_declarada.LARGURA_MINIMA_DA_GALERIA`.

**É a aba mais exigente que decide o piso**, e não a média: a Galeria precisa de 420 px de recorte
mais 260 de lateral mais a folga, e abaixo disso quem perde é a coluna de headers -- os controles
que gravam a procedência de uma partida (S-154)."""

LARGURA_MINIMA_DO_VISOR = 520
"""O mesmo piso do visualizador do produto: abaixo disso a página não cabe nem no ajuste à
largura, e o que sobra é rolagem horizontal."""

TITULO_DA_JANELA = "PyQt"
"""Vai no título da janela, e não é decoração.

Duas janelas do mesmo produto abertas lado a lado é exatamente a situação em que alguém corrige
vinte diagramas na janela errada, e o título é o único lugar que responde "qual das duas é esta?"
no Alt-Tab. **As duas escrevem no mesmo `labels.csv`**, e é isso que torna a marca necessária.

O texto não diz "versão de teste" porque isso é falso desde a S-502 -- o que ele precisa dizer é
**qual** janela é esta, e ele some no dia do corte, quando não houver duas."""

TITULO_DE_TESTE = TITULO_DA_JANELA
"""O nome de antes, que os testes da S-502 citam. Um alias e não um segundo literal."""

ESPERA_AO_FECHAR_MS = 15_000
"""Quanto o fechamento espera pela tarefa em curso, em milissegundos."""


class JanelaPrincipal(QMainWindow):
    """As sete abas do produto numa janela, e a fiação entre elas."""

    def __init__(
        self,
        *,
        servico: OcrService | None = None,
        csv_de_rotulos: Path = DEFAULT_DATASET_CSV,
        pasta_de_estudos: Path | None = None,
        pasta_da_galeria: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._servico = servico if servico is not None else OcrService(model_path=DEFAULT_MODEL_PATH)
        self._csv_de_rotulos = Path(csv_de_rotulos)
        self._pasta_de_estudos = pasta_de_estudos
        self._pasta_da_galeria = pasta_da_galeria
        """Onde o índice varrido e as anotações moram. `None` é o padrão do produto, `data/gallery/`.

        Existe pelo mesmo motivo do parâmetro homônimo do painel: **sem ele o teste da janela grava
        no acervo de verdade**, e três caminhos de escrita resolvem o padrão na definição."""

        self._pdf: Path | None = None
        self._itens: list[RecognizedDiagram] = []
        self._salvos: dict[int, set[int]] = {}
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
        self._tarefa: Tarefa | None = None
        """A tarefa em curso. Guardada num atributo porque um `QThread` sem referência viva é
        coletado no meio da execução, e o sintoma é a janela travada esperando um sinal que nunca
        vem."""

        self.busy = BusyRegistry()
        """Onde as operações longas se declaram (S-112). Uma por janela, e é ela que o rodapé
        desenha e a pergunta de fechamento consulta."""

        self._montar()
        self._ligar()
        self._atualizar_titulo()
        self._atualizar_abas()
        self.rodape.mostrar("Abra um livro em PDF para começar.")

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        # **A fundação antes dos widgets, e a ordem é o item.** A folha de estilo é da aplicação e
        # alcança todo widget criado depois dela; aplicá-la no fim faria os widgets nascerem com o
        # cinza de fábrica e só depois trocarem de cor, que no Windows pisca.
        tema.aplicar_tema()
        plataforma.preparar_janela(self)
        dica.ajustar_atraso()

        self._montar_paineis()

        corpo = QWidget(self)
        pilha = QVBoxLayout(corpo)
        pilha.setContentsMargins(0, 0, 0, 0)
        pilha.setSpacing(0)
        pilha.addWidget(self.divisor, 1)
        # O rodapé **por último e fora do divisor**: ele é da janela, não de um dos lados, e é o
        # que a S-163 fixou -- mensagem à esquerda, estado do documento e operação em curso à
        # direita, altura fixa por construção.
        self.rodape = RodapeDaJanela(corpo, cancelar=self.busy.request_cancel)
        # **O rodapé pergunta; as operações não avisam** (S-112). Um `BusyToken` que esquecesse de
        # avisar deixaria a barra girando para sempre, e `release()` esquecido é o erro que de
        # fato acontece. Os dispositivos entram no mesmo tique porque nenhum dos dois modelos
        # torch avisa quando muda.
        self.rodape.acompanhar(self.busy.running, dispositivos=self._dispositivos)
        pilha.addWidget(self.rodape)
        self.setCentralWidget(corpo)

        self.menu = menu.montar(self, self._comandos())
        # **A marca inicial, senão os dois submenus abrem sem nenhuma.** Um submenu de escolha
        # exclusiva sem marca não diz o que está em vigor -- e a pele em vigor é a que
        # `pele.escolhida()` resolve (ambiente, senão guardada, senão clássica).
        _em_vigor = pele.registrada(pele.escolhida())
        self.menu.escolher("aparencia", _em_vigor.nome)
        self.menu.escolher("densidade", pele.densidade_em_vigor(_em_vigor))
        self._teclas = qt_atalhos.ligar(self, self._comandos())
        """A guarda de foco. **Guardada num atributo de propósito**: um `QObject` sem referência
        viva é coletado, e um filtro coletado deixa de ser chamado sem que nada avise -- a janela
        simplesmente perde o teclado."""
        self.resize(1440, 900)

    def _montar_paineis(self) -> None:
        self.divisor = QSplitter(Qt.Orientation.Horizontal, self)

        self.abas = QTabWidget(self.divisor)
        self.abas.setMinimumWidth(LARGURA_MINIMA_DAS_ABAS)

        self.painel = PainelDeResultado(
            self._servico, csv_de_rotulos=self._csv_de_rotulos, parent=self.abas
        )
        self.painel.declarar_contexto(documento=self._chave_do_documento, parametros=self._parametros_de_ocr)
        self.abas.addTab(self.painel, abas.RESULTADO)

        self.estudo = PainelDeEstudo(
            self.abas,
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
        self.abas.addTab(self.estudo, abas.ESTUDO)

        self.revisao = PainelDeRevisao(self.abas, pedido_de_varredura=self._pedido_de_varredura)
        self.abas.addTab(self.revisao, abas.REVISAO)

        self.texto = PainelDeTexto(busy=self.busy, parent=self.abas)
        self.abas.addTab(self.texto, abas.TEXTO)

        self.dataset = PainelDoDataset(self.abas, caminhos=self._caminhos_do_dataset, busy=self.busy)
        self.abas.addTab(self.dataset, abas.DATASET)

        self.galeria = PainelDaGaleria(
            self.abas,
            service=self._servico,
            pdf_path=lambda: self._pdf,
            model_path=lambda: DEFAULT_MODEL_PATH,
            max_boards=lambda: DEFAULT_MAX_BOARDS,
            # Uma varredura por livro (S-119): a Galeria varre, e a fila de revisão sai da mesma
            # passada. Quem liga as duas abas é esta janela -- nenhuma conhece a outra.
            sumidouro_de_revisao=self.revisao.sumidouro,
            pasta_da_galeria=self._pasta_da_galeria,
            busy=self.busy,
        )
        self.abas.addTab(self.galeria, abas.GALERIA)

        self.lado_do_livro = QWidget(self.divisor)
        self.pdf = PainelDoPdf(
            self.lado_do_livro, dpi=lambda: DEFAULT_DPI, pasta_inicial=DEFAULT_PDF_DIR
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
        coluna = QVBoxLayout(self.lado_do_livro)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(espaco.linha())
        coluna.addWidget(self.pdf, 1)
        coluna.addWidget(self.campo)

        self.divisor.addWidget(self.abas)
        self.divisor.addWidget(self.lado_do_livro)
        self.divisor.setStretchFactor(0, 2)
        self.divisor.setStretchFactor(1, 3)
        # **Os tamanhos iniciais são declarados, e não deduzidos.** O `QSplitter` reparte pela
        # `sizeHint` de cada lado, e a de um `QTabWidget` cheio de rótulos com quebra de linha
        # pede toda a largura que lhe derem.
        self.divisor.setSizes([LARGURA_MINIMA_DAS_ABAS, 760])

        self.treino = ControladorDeTreino(self, pedido=self._pedido_de_treino, busy=self.busy)
        self.exportador = Exportador(
            self, configuracao=self._configuracao_de_exportacao, servico=self._servico, busy=self.busy
        )

    @property
    def editor(self) -> DiagramEditorModel:
        """O modelo do editor, que mora no painel. **Fachada, e é curta de propósito.**

        A janela precisa dele para uma coisa só -- saber de que página veio o que está aberto,
        para o cache e para a marca de salvo. Tudo o mais que se faz com ele é do painel, e é por
        isso que a fachada é uma propriedade de leitura e não um punhado de delegações.
        """
        return self.painel.modelo

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
        for controlador in (self.treino, self.exportador):
            controlador.estado.connect(self._dizer)
            controlador.controles.connect(self._trancar)
        self.treino.terminou.connect(self._treino_terminou)

        # --- o visualizador
        self.pdf.abriu_pdf.connect(self._abriu_livro)
        self.pdf.antes_de_trocar_de_pagina.connect(self.painel.lembrar_pagina)
        self.pdf.pagina_desenhada.connect(self._pagina_apareceu)
        self.pdf.caixa_clicada.connect(self._clicou_na_caixa)
        self.pdf.caixa_dispensada.connect(self._tirar_caixa)
        self.pdf.regiao_pedida.connect(self._ler_regiao)

        # --- o Resultado
        # A S-451: "Salvar todos" pergunta antes de gravar a segunda cópia, e quem sabe o que já
        # foi salvo é a janela -- o painel não tem o carimbo por página.
        self.painel.diagramas_salvos = lambda _documento, pagina: self._salvos.get(pagina, set())
        self.painel.selecionou.connect(self.pdf.selecionar_caixa)
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

    def _dizer(self, frase: str) -> None:
        """A frase de qualquer painel no rodapé, com a severidade que ela declara.

        Quem decide se a frase é informação, aviso ou erro é `ui/estado_do_rodape.severidade` --
        pura, compartilhada com o Tk, e a razão de as duas janelas pintarem de vermelho as mesmas
        frases.
        """
        self.rodape.mostrar(frase, severidade=estado_do_rodape.severidade_de(frase))

    def _trancar(self, liberado: bool) -> None:
        """Liga e desliga o que não pode rodar durante uma operação longa."""
        self.abas.setEnabled(liberado)
        self.pdf.setEnabled(liberado)

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
        self._pdf = alvo
        # As caixas são de um arquivo que pode ter mudado no disco. A chave já inclui o documento,
        # então isto não é correção de defeito: é não guardar afirmação sobre um PDF que ninguém
        # mais está olhando.
        self._caixas_por_pagina.clear()
        self._tiradas.clear()
        self._candidatos = None
        self._itens = []
        self._carregar_marcas_salvas()
        if anterior is not None:
            self.painel.descartar_livro(str(anterior))
        # Sem isto a galeria só conheceria o livro depois de uma varredura -- e o número do lance
        # digitado na aba Resultado (S-71) seria gravado num modelo sem `pdf_path`, que descarta
        # em silêncio. `request_page=False` porque o visualizador acabou de escolher a página.
        self.galeria.load_pdf(alvo, request_page=False)
        self.estudo.abrir_livro(str(alvo))  # a sala daquele livro volta do disco (S-271)
        self.texto.definir_livro(alvo, pagina=self.pdf.page_index)
        self._atualizar_titulo()
        self._atualizar_abas()

    def _carregar_marcas_salvas(self) -> None:
        """Quais diagramas deste livro já têm amostra no CSV (S-71). Só leitura.

        Vale antes de qualquer OCR, e é o que responde "onde eu parei neste livro?" -- a pergunta
        que se faz ao abrir um livro pela quinta vez. CSV ausente não é falha: é um checkout sem
        dados, e ali a resposta honesta é "nenhum".
        """
        self._salvos = {}
        if self._pdf is None:
            return
        try:
            self._salvos = saved_diagrams_by_page(LabelStore(self._csv_de_rotulos).read(), self._pdf.name)
        except OSError as exc:
            logger.warning("Marcas de salvo indisponíveis (%s): %s", self._csv_de_rotulos, exc)

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

    def _pagina_apareceu(self, pagina: int) -> None:
        """A página está na tela: traz de volta o que já se sabe dela.

        **Depois do desenho, e não antes**: restaurar o editor para uma página que ainda não está
        na tela é o sintoma que a Fase 5 corrigiu -- o seletor apontando para diagramas que não
        são os da página exibida.
        """
        self._candidatos = None
        self._itens = []
        self.painel.restaurar_pagina(pagina)
        self._publicar_caixas(
            self._caixas_por_pagina.get(self._chave_do_documento(), pagina, self._parametros())
        )
        # A galeria acompanha a página, e ela mesma ignora o aviso quando foi ela quem pediu a
        # virada -- senão as duas se chamariam em círculo (S-67).
        self.galeria.sync_to_page(pagina)
        # A anotação de campo é sobre a página exibida: virou a página, ela diz de novo se esta
        # já está anotada e se há amostra de treino dela (S-97).
        self.campo.atualizar()
        self._atualizar_titulo()
        self._dizer_o_que_ha_na_pagina()

    # ------------------------------------------------------------------------------ leitura

    def _parametros(self) -> OverlayParams:
        return OverlayParams(dpi=DEFAULT_DPI, max_boards=DEFAULT_MAX_BOARDS)

    def _parametros_de_ocr(self) -> PageOcrParams:
        """Com que parâmetros a página foi lida. É a chave do cache do painel de Resultado.

        **Inclui o modelo e a orientação, e não só o DPI**: uma leitura feita com outro `.pt` não
        responde pela mesma página, e restaurá-la calada seria mostrar o resultado de um modelo
        dizendo que é o do outro.
        """
        return PageOcrParams(
            model_path=str(DEFAULT_MODEL_PATH),
            orientation=DEFAULT_ORIENTATION_MODE,
            max_boards=DEFAULT_MAX_BOARDS,
            dpi=DEFAULT_DPI,
        )

    def _opcoes(self) -> RecognitionOptions:
        return RecognitionOptions(
            model_path=DEFAULT_MODEL_PATH,
            orientation=DEFAULT_ORIENTATION_MODE,
            max_boards=DEFAULT_MAX_BOARDS,
            dpi=DEFAULT_DPI,
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

        pdf, pagina, teto = self._pdf, self.pdf.page_index, DEFAULT_MAX_BOARDS
        self._rodar(
            lambda: detect_diagrams_in_pdf_page(pdf, pagina, pagina_rgb, max_boards=teto),
            nome="detecção",
            aviso=f"Procurando diagramas na página {pagina + 1}…",
            quando_pronto=lambda candidatos: self._chegaram_candidatos(pagina, candidatos),
        )

    def ler_pagina(self, *, selecionar_depois: int | None = None) -> None:
        """O caminho completo: detecta, prevê, decide a vez e confere a legalidade.

        A página inteira, e não o diagrama clicado, pelo motivo que `decide_box_click` registra: o
        recorte isolado perde a imagem embutida do PDF e o contexto de texto que decide o lado a
        jogar, e sairia lido pior sem que nada na tela dissesse por quê.
        """
        pagina_rgb = self.pdf.page_rgb
        if self._pdf is None or pagina_rgb is None:
            self._dizer("Abra um PDF antes de ler a página.")
            return
        pdf, pagina, opcoes = self._pdf, self.pdf.page_index, self._opcoes()
        candidatos = self._candidatos_desta_pagina()
        # **A leitura diz no log de onde vieram os diagramas.** Sem esta linha, o rastro de uma
        # sessão não distingue "marcar e depois ler" de "ler sozinho": os dois deixam uma varredura
        # do detector e nada mais.
        logger.info(
            "Lendo a página %d — %s.",
            pagina + 1,
            f"{len(candidatos)} diagrama(s) já localizados" if candidatos is not None else "detectando por dentro",
        )
        self._rodar(
            lambda: self._servico.recognize_page(
                pdf, pagina, pagina_rgb, options=opcoes, candidates=candidatos
            ),
            nome="leitura",
            aviso=f"Lendo a página {pagina + 1}…",
            quando_pronto=lambda itens: self._chegaram_itens(pagina, itens, selecionar_depois),
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
    ) -> None:
        """Uma tarefa de cada vez, e os controles desligados enquanto ela corre.

        Não é cerimônia: duas leituras simultâneas disputariam o mesmo modelo (o `OcrService` as
        serializa no lock, então a segunda só esperaria) e a segunda a terminar sobrescreveria a
        lista da primeira -- que pode ser de outra página.
        """
        if self._tarefa is not None:
            self._dizer("Já há uma tarefa em andamento.")
            return
        tarefa = Tarefa(funcao, parent=self, nome=nome)
        tarefa.pronto.connect(quando_pronto)
        tarefa.falhou.connect(self._falhou)
        tarefa.finished.connect(self._terminou)
        # O `QThread` é filho da janela, então soltar a referência daqui não o destrói: sem isto,
        # uma sessão de trezentas páginas termina com trezentos threads mortos pendurados no pai.
        tarefa.finished.connect(tarefa.deleteLater)
        self._tarefa = tarefa
        self.rodape.mostrar(aviso)
        self._atualizar_controles()
        tarefa.start()

    def _terminou(self) -> None:
        self._tarefa = None
        self._atualizar_controles()

    def _falhou(self, mensagem: str, excecao: object) -> None:
        """Nenhum diagrama na página **não** é erro: é uma página de prosa, e há muitas.

        Tratá-la como falha ensinaria a pessoa a ignorar a caixa de erro, que é o que faz a caixa
        deixar de servir quando a falha for de verdade.
        """
        if isinstance(excecao, NoBoardDetectedError):
            self._dizer("Nenhum diagrama encontrado nesta página.")
            return
        QMessageBox.warning(self, "A leitura não terminou", mensagem)
        self._dizer(mensagem)

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
        self._candidatos = (pagina, tuple(candidatos))
        caixas = self._caixas_sem_desaprender(pagina, boxes_from_candidates(candidatos))
        self._guardar(caixas)
        if pagina != self.pdf.page_index:
            # A página virou enquanto a detecção corria. As caixas ainda valem -- para **aquela**
            # página --, então ficam no cache e não vão para a tela.
            return
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
        self.pdf.definir_caixas(PageBoxes(caixas.page_index, caixas.params, mark_saved(visiveis, salvos)))

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
        self.ler_pagina(selecionar_depois=indice)

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

    def _fechar_item_da_fila(self, posicao: int, fen: str, lado: str) -> None:
        """Fecha na fila o item que acabou de ser corrigido e salvo (S-22)."""
        self.revisao.aplicar_correcao(int(posicao), fen, lado)
        self._atualizar_abas()
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
        """Traz para a frente a aba que acabou de receber alguma coisa."""
        indice = self.abas.indexOf(painel)
        if indice >= 0:
            self.abas.setCurrentIndex(indice)

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
        """Por diagrama da página exibida: a colocação **corrigida** e se alguém a conferiu (S-95).

        **Vem de `fen_edits`, e não de `items[i].placement`.** As duas listas são paralelas de
        propósito -- fundi-las perderia a leitura original --, e a anotação do conjunto de campo
        já esteve lendo o lado errado: gravava o que o modelo leu como verdade **sobre** o modelo.
        Corrigir o tabuleiro e anotar a página descartava a correção e gravava o erro.
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

        return {
            item.index: (
                edicoes[posicao] if posicao < len(edicoes) else item.placement,
                bool(item.edited_by_hand),
            )
            for posicao, item in enumerate(itens)
        }

    def _aviso_de_treino(self) -> str:
        """" · N amostra(s) de treino desta página" quando houver, senão string vazia (S-97).

        Lê o `labels.csv` e o `splits.csv` a cada troca de página, e isso é aceitável **aqui** pelo
        mesmo motivo que não seria no `Ctrl+S` (S-116): virar página é um gesto por vez, e não o
        laço interno.
        """
        if self._pdf is None:
            return ""
        csv_path, _amostras, splits_path = self._caminhos_do_dataset()
        if not csv_path.exists() or not splits_path.exists():
            return ""
        try:
            paginas = pages_with_training_samples(LabelStore(csv_path).read(), load_splits(splits_path))
        except (OSError, ValueError) as erro:
            # Aviso ausente é melhor que janela quebrada: é informação lateral.
            logger.debug("Não foi possível checar amostras de treino da página: %s", erro)
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
            dpi=DEFAULT_DPI,
            max_boards_per_page=DEFAULT_MAX_BOARDS,
        )

    def _pedido_de_treino(self) -> TrainingRequest:
        csv, amostras, splits = self._caminhos_do_dataset()
        return TrainingRequest(
            csv_path=csv,
            samples_dir=amostras,
            model_path=DEFAULT_MODEL_PATH,
            epochs=8,
            batch_size=16,
            lr=1e-3,
            splits_path=splits,
        )

    def _configuracao_de_exportacao(self) -> ExportSettings:
        return ExportSettings(
            model_path=DEFAULT_MODEL_PATH,
            dpi=DEFAULT_DPI,
            max_boards_per_page=DEFAULT_MAX_BOARDS,
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
            "abrir_recente": lambda: None,
            "abrir_no_leitor": self.pdf.abrir_no_leitor_do_sistema,
            "sair": self.close,
            # --- navegar
            "pagina_anterior": self.pdf.pagina_anterior,
            "proxima_pagina": self.pdf.proxima_pagina,
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
            "ler_pagina": self.ler_pagina,
            "ler_melhor": self.ler_pagina,
            "salvar": self.painel.salvar_atual,
            "salvar_todos": self.painel.salvar_todos,
            "aplicar_fen": self.painel.aplicar_fen,
            "limpar_tabuleiro": self.painel.limpar_tabuleiro,
            "apagar_casa": self._apagar_casa,
            "desfazer": self.painel.desfazer,
            "refazer": self.painel.refazer,
            "diagrama_anterior": lambda: self.painel.andar(-1),
            "proximo_diagrama": lambda: self.painel.andar(1),
            # --- as outras abas
            "proximo_da_fila": self.revisao.abrir_proximo_pendente,
            "varrer_livro": self.galeria.varrer,
            "exportar_pgn": lambda: self.exportador.comecar(self._pdf),
            "cancelar_exportacao": self.exportador.cancelar,
            "treinar": self.treino.iniciar,
            "recarregar_modelo": self._recarregar_modelo,
            # --- a janela
            "aparencia": self.trocar_de_pele,
            "densidade": self.trocar_de_densidade,
            "paleta_de_comandos": self.abrir_paleta,
            "legenda_de_atalhos": lambda: legenda.abrir(self),
            "abrir_log": self._abrir_log,
            "sobre": self._sobre,
        }
        # As duas tabelas dos painéis entram depois: um comando que os dois declarassem seria da
        # aba, e não da janela -- é lá que o método está.
        tabela.update({acao: getattr(self.estudo, metodo) for acao, metodo in COMANDOS_DA_SALA.items()})
        tabela.update({acao: getattr(self.texto, metodo) for acao, metodo in COMANDOS_DO_TEXTO.items()})
        return tabela

    # ------------------------------------------------------------------ os dois eixos da pele

    def _escolha_do_menu(self, acao: str) -> str:
        """O valor marcado naquele submenu, ou `""`.

        O submenu guarda o valor no `data()` da ação e chama o comando **sem argumento** -- é a
        S-166: `pele.Pele` separa `nome` de `rotulo`, e o que vai para o disco é o primeiro.
        """
        grupo = self.menu.grupos.get(acao)
        marcada = grupo.checkedAction() if grupo is not None else None
        return "" if marcada is None else str(marcada.data())

    def trocar_de_pele(self) -> None:
        """Aplica a pele escolhida em `Ver ▸ Aparência` (S-221/S-506).

        **Os dois eixos são separados, e a escolha explícita ganha da sugestão.** A pele sugere
        uma densidade -- a fita sugere compacta porque gasta altura com cromo --, e quem escolheu
        densidade no outro submenu não a perde ao trocar de pele: `pele.densidade_em_vigor`
        responde por isso, e é pura desde a S-232.

        **Este comando esteve inerte** (`lambda: None`) desde a montagem da janela, e o corte do
        Tk o tornou visível: o menu listava as três peles e escolher qualquer uma não fazia nada,
        que é pior que não oferecer a escolha.
        """
        escolhida = self._escolha_do_menu("aparencia")
        if not escolhida:
            return
        self._aplicar_aparencia(escolhida, self._escolha_do_menu("densidade"))

    def trocar_de_densidade(self) -> None:
        """Aplica a densidade escolhida em `Ver ▸ Densidade`. Ver `trocar_de_pele`."""
        self._aplicar_aparencia(self._escolha_do_menu("aparencia"), self._escolha_do_menu("densidade"))

    def _aplicar_aparencia(self, nome_da_pele: str, densidade_guardada: str) -> None:
        """Refaz a folha de estilo e repinta o que já está na tela.

        `repintar` é o que faz a troca valer para os widgets **existentes**: a folha nova pega os
        que nascerem depois dela, e sem esta chamada a janela ficaria metade numa pele e metade
        noutra até o próximo redesenho.
        """
        registro = pele.registrada(pele.escolhida(nome_da_pele))
        densidade = pele.densidade_em_vigor(registro, densidade_guardada)
        # `instance()` é declarada `QCoreApplication`; num programa de janela ela é a
        # `QApplication`, e `aplicar_tema` já trata o `None` sem levantar.
        aplicacao = QApplication.instance()
        tema.aplicar_tema(
            aplicacao if isinstance(aplicacao, QApplication) else None,
            cromo_escuro=registro.cromo_escuro,
            densidade=densidade,
        )
        tema.repintar()
        self.menu.escolher("aparencia", registro.nome)
        self.menu.escolher("densidade", densidade)
        self._dizer(f"Aparência: {registro.rotulo}, densidade {pele.rotulo_de_densidade(densidade)}.")

    def abrir_paleta(self) -> Any:
        """A paleta de comandos (S-231): um campo, uma lista filtrada, Enter executa."""
        return paleta.abrir(self, self._comandos())

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
        """Põe no rótulo de cada aba quanto trabalho ela carrega (S-162).

        Chamado nos pontos em que os números mudam -- abrir livro, salvar amostra, fechar item da
        fila --, e **não num relógio**: a contagem só muda quando alguém a muda, e um disparo
        periódico redesenharia a barra de abas para dizer o mesmo número.
        """
        contagens = {
            abas.REVISAO: len(self.revisao.queue.pending()),
            abas.DATASET: self.dataset.contagem_de_amostras(),
            abas.GALERIA: len(self.galeria.model),
        }
        for indice in range(self.abas.count()):
            nome = abas.nome_base(self.abas.tabText(indice))
            if nome in contagens:
                self.abas.setTabText(indice, abas.rotulo(nome, contagens[nome]))

    def _dizer_o_que_ha_na_pagina(self) -> None:
        """O estado da página no rodapé, e o dispositivo do modelo quando já há um.

        A frase é a de `ui/estado_do_rodape.descricao_dos_diagramas`, que é pura e compartilhada
        com o Tk -- e é por isso que as duas janelas contam a mesma coisa da mesma maneira.
        """
        if self._pdf is None:
            self.rodape.definir_documento("")
            return
        caixas = self.pdf.boxes
        na_pagina = caixas.boxes if caixas is not None else ()
        todos_salvos = bool(na_pagina) and all(caixa.saved for caixa in na_pagina)
        diagramas = estado_do_rodape.descricao_dos_diagramas(
            len(na_pagina),
            lidos=len(self._itens),
            salvos=sum(1 for caixa in na_pagina if caixa.saved),
            confirmados=sum(1 for caixa in na_pagina if caixa.confirmed),
            todos_salvos=todos_salvos,
        )
        self.rodape.definir_documento(
            estado_do_rodape.descricao_do_documento(
                self._pdf.name, self.pdf.page_index, self.pdf.page_count, diagramas
            ),
            todos_salvos,
        )

    def _atualizar_titulo(self) -> None:
        livro = self._pdf.name if self._pdf is not None else ""
        base = strings.titulo_da_janela(
            livro,
            self.pdf.page_index if self._pdf is not None else None,
            self.pdf.page_count or None,
        )
        self.setWindowTitle(f"{base} — {TITULO_DA_JANELA}")

    def _atualizar_controles(self) -> None:
        """Desliga o que não faz sentido agora: com uma tarefa em curso.

        **Salvar exige nenhuma tarefa em curso**, e é a única condição que esta janela conhece e o
        painel não: gravar no meio de uma leitura escreveria a amostra de uma página que está
        sendo substituída. O resto dos botões cada painel governa sozinho.
        """
        self.painel.setEnabled(self._tarefa is None)

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
        if perdidas and not self._confirmar_fechamento(perdidas):
            if a0 is not None:
                a0.ignore()
            return
        # A sala vai para o disco antes de tudo: ela é o único painel cujo trabalho não tem outra
        # cópia, e o `Ctrl+Z` dela não sobrevive à janela (S-271).
        self.estudo.salvar_agora()
        if self._tarefa is not None and not self._tarefa.wait(ESPERA_AO_FECHAR_MS):
            logger.warning("A janela fechou com uma tarefa ainda em andamento.")
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
