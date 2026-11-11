"""A montagem da janela: o que existe na tela, e o que cada comando do catálogo faz nela (S-31).

Saiu de `qt/janela.py` pela regra de corte da S-31 (`tests/test_packaging.py`), **sem mudar uma
decisão**: os corpos são os de `_montar_paineis` e `_comandos`, com `janela` onde estava `self`. Os
atributos que a montagem preenche estão declarados na classe, e quem conversa com quem continua em
`JanelaPrincipal._ligar`. `JanelaPrincipal._comandos` segue existindo, delegando: é a face que o
menu, a paleta, os atalhos e os testes pedem.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QSplitter, QVBoxLayout, QWidget

from chess_diagram_ocr.config import DEFAULT_MODEL_PATH, DEFAULT_PDF_DIR
from chess_diagram_ocr.qt import (
    abas_da_suite,
    dialogo_de_configuracoes,
    exportador_de_livro,
    importador_de_livro,
    legenda,
    livro_com_pgn,
    painel_de_revisao_de_texto,
    painel_de_rotulagem,
)
from chess_diagram_ocr.qt.areas_de_trabalho import AreasDeTrabalho
from chess_diagram_ocr.qt.campo import PainelDeCampo
from chess_diagram_ocr.qt.dialogos import ControladorDeTreino
from chess_diagram_ocr.qt.disposicao_de_mesa import DisposicaoDeMesa
from chess_diagram_ocr.qt.exportador import Exportador
from chess_diagram_ocr.qt.painel_da_galeria import PainelDaGaleria
from chess_diagram_ocr.qt.painel_de_estudo import PainelDeEstudo
from chess_diagram_ocr.qt.painel_de_resultado import PainelDeResultado
from chess_diagram_ocr.qt.painel_de_revisao import PainelDeRevisao
from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto
from chess_diagram_ocr.qt.painel_do_dataset import PainelDoDataset
from chess_diagram_ocr.qt.painel_do_pdf import PainelDoPdf
from chess_diagram_ocr.qt.trilho import TrilhoDoLivro
from chess_diagram_ocr.review_queue import DEFAULT_QUEUE_PATH
from chess_diagram_ocr.ui import abas, espaco
from chess_diagram_ocr.ui.configuracoes import dpi as _dpi
from chess_diagram_ocr.ui.configuracoes import max_boards as _max_boards
from chess_diagram_ocr.ui.geometria import (
    LARGURA_MINIMA_DAS_ABAS,
    LARGURA_MINIMA_DO_VISOR,
    LARGURA_PREFERIDA_DAS_ABAS,
    LARGURA_PREFERIDA_DO_VISOR,
)
from chess_diagram_ocr.ui.sala_declarada import COMANDOS_DA_ABA as COMANDOS_DA_SALA
from chess_diagram_ocr.ui.texto_declarado import COMANDOS_DA_ABA as COMANDOS_DO_TEXTO

if TYPE_CHECKING:
    from chess_diagram_ocr.qt.janela import JanelaPrincipal

__all__ = ["montar_paineis", "tabela_de_comandos"]


def montar_paineis(janela: JanelaPrincipal) -> None:
    """Constrói os painéis na ordem em que um pede o outro, e os reparte em abas, modos e lado do livro."""
    janela.divisor = QSplitter(Qt.Orientation.Horizontal, janela)

    # **Os quatro painéis do diagrama são modos da aba `Livro`**, e não abas (OCR_UI passo
    # 17, tarefa 3): quem sabe onde cada área mora é `qt/areas_de_trabalho.py`; aqui só se
    # monta cada painel e se diz se ele é modo (`adicionar_modo`) ou aba (`addTab`).
    janela.abas = AreasDeTrabalho(janela.divisor)
    janela.abas.setMinimumWidth(LARGURA_MINIMA_DAS_ABAS)
    janela.principal = janela.abas.principal

    janela.painel = PainelDeResultado(
        janela._servico, csv_de_rotulos=janela._csv_de_rotulos, parent=janela.principal
    )
    janela.painel.declarar_contexto(documento=janela._chave_do_documento, parametros=janela._parametros_de_ocr)

    janela.estudo = PainelDeEstudo(
        janela.principal,
        # **O motor, se houver um** (F9-C16/S-523): sem esta linha os três comandos do menu
        # Estudo nunca podiam funcionar, e sem binário a seção "Motor" não existe (S-33).
        analyzer=janela._analisador,
        # Vínculo de mão única: o estudo lê a posição do diagrama selecionado e nunca escreve
        # de volta. Um lance jogado no estudo não é uma correção do OCR.
        posicao=janela._posicao_de_estudo,
        pasta_inicial=DEFAULT_PDF_DIR,
        pasta_de_estudos=janela._pasta_de_estudos,
        # As quatro portas por onde o **livro** entra na sala. Cada uma é uma pergunta que
        # outro painel já sabe responder, e nenhuma deixa a sala escrever naquele painel.
        recorte=janela._recorte_do_diagrama,
        linha_impressa=janela._linha_impressa,
        abrir_pagina=janela._abrir_pagina_do_estudo,
        para_o_texto=janela._linha_para_o_texto,
        caminho_do_cache=janela._caminho_do_cache,
    )

    janela.revisao = PainelDeRevisao(
        janela.principal,
        pedido_de_varredura=janela._pedido_de_varredura,
        # A fila que a sessão anterior abriu, e não sempre a do produto (S-22/S-156). Vazio no
        # estado é "nunca escolhi outra", e aí a do produto é a certa.
        queue_path=Path(janela._estado.review_queue_path or DEFAULT_QUEUE_PATH),
    )

    janela.texto = PainelDeTexto(busy=janela.busy, com_caderno=True, parent=janela.principal)
    janela.texto.definir_executor(lambda acao: janela.menu.acoes[acao].trigger())  # o que a fita pede à janela
    janela.texto.diagrama_ativado.connect(janela._estudar_do_texto)  # duplo clique na miniatura (item 8)

    janela.dataset = PainelDoDataset(
        janela.abas,
        caminhos=janela._caminhos_do_dataset,
        busy=janela.busy,
        em_processo=janela._rasterizar_ao_fundo,
    )

    janela.galeria = PainelDaGaleria(
        janela.abas,
        service=janela._servico,
        pdf_path=lambda: janela._pdf,
        model_path=lambda: DEFAULT_MODEL_PATH,
        max_boards=_max_boards,
        # Uma varredura por livro (S-119): a Galeria varre, e a fila de revisão sai da mesma
        # passada. Quem liga as duas abas é esta janela -- nenhuma conhece a outra.
        sumidouro_de_revisao=janela.revisao.sumidouro,
        pasta_da_galeria=janela._pasta_da_galeria,
        caminho_do_cache=janela._caminho_do_cache,
        busy=janela.busy,
    )
    janela.rotulagem = painel_de_rotulagem.montar(janela.abas, folhas_para=janela.texto.folhas_do_livro)  # a bancada da suíte; o caderno vai ao livro dela (R7)
    janela.revisao_de_texto = painel_de_revisao_de_texto.montar(janela.abas)  # idem, passo 14
    # A ordem é a de `abas.MODOS` e `abas.DO_ACERVO`, lida e não copiada (S-162/S-511): área sem
    # painel reprova aqui. A `Livro` já é a primeira aba, e as duas da suíte só existem com ela.
    modos = {abas.RESULTADO: janela.painel, abas.ESTUDO: janela.estudo, abas.REVISAO: janela.revisao, abas.TEXTO: janela.texto}
    acervo = {
        abas.DATASET: janela.dataset,
        abas.GALERIA: janela.galeria,
        abas.ROTULAGEM: janela.rotulagem,
        abas.REVISAO_DE_TEXTO: janela.revisao_de_texto,
    }
    for nome in abas.MODOS:
        janela.principal.adicionar_modo(nome, modos[nome])
    for nome in abas.DO_ACERVO:
        if (aba := acervo[nome]) is not None:
            janela.abas.addTab(aba, nome)

    janela.lado_do_livro = QWidget(janela.divisor)
    janela.pdf = PainelDoPdf(
        janela.lado_do_livro,
        dpi=_dpi,
        # Todo livro abre na página em que foi deixado, e não só o último (S-25). O histórico
        # guarda 50, e é a pergunta que se faz ao voltar a um livro pela quinta vez.
        pagina_inicial_de=janela._pagina_guardada_de,
        pasta_inicial=DEFAULT_PDF_DIR,
        rasterizar_ao_fundo=janela._rasterizar_ao_fundo,
    )
    janela.pdf.setMinimumWidth(LARGURA_MINIMA_DO_VISOR)

    # **A anotação de campo fica sob a página, e não numa aba** (S-95): ela afirma coisas
    # sobre a página exibida -- quantos diagramas ela tem, se algum é falso positivo --, e
    # numa aba a pessoa anotaria sem estar olhando para o que anota.
    janela.campo = PainelDeCampo(
        janela.lado_do_livro,
        pdf_path=lambda: janela._pdf,
        page_index=lambda: janela.pdf.page_index,
        caixas=lambda: janela.pdf.boxes,
        caixa_selecionada=lambda: janela.pdf.caixa_selecionada,
        colocacoes=janela._colocacoes_conferidas,
        aviso_de_treino=janela._aviso_de_treino,
    )
    # **O trilho de páginas à esquerda do visor** (OCR_UI passo 17): o mapa do livro, com o
    # estado de cada página e os botões do fluxo principal (importar, primeira duvidosa,
    # exportar). É um índice de largura fixa; a página continua com o resto.
    janela.trilho = TrilhoDoLivro(janela.lado_do_livro, miniaturas_ao_fundo=janela._rasterizar_ao_fundo)
    janela.trilho.pagina_pedida.connect(janela.pdf.ir_para_pagina)
    janela.trilho.exportar_pedido.connect(lambda: janela._exportar_livro("epub"))
    coluna = QVBoxLayout()
    coluna.setContentsMargins(0, 0, 0, 0)
    coluna.setSpacing(espaco.linha())
    coluna.addWidget(janela.pdf, 1)
    coluna.addWidget(janela.campo)
    lado = QHBoxLayout(janela.lado_do_livro)
    lado.setContentsMargins(0, 0, 0, 0)
    lado.setSpacing(espaco.linha())
    lado.addWidget(janela.trilho)
    lado.addLayout(coluna, 1)

    janela.divisor.addWidget(janela.abas)
    janela.divisor.addWidget(janela.lado_do_livro)
    janela.divisor.setStretchFactor(0, 2)
    janela.divisor.setStretchFactor(1, 3)
    # **A alça não apaga a navegação** (F9-C3): colapsar punha 21 de 36 botões fora da tela.
    janela.divisor.setChildrenCollapsible(False)
    # **Os tamanhos iniciais são declarados, e não deduzidos.** O `QSplitter` reparte pela
    # `sizeHint` de cada lado, e a de um `QTabWidget` cheio de rótulos com quebra de linha
    # pede toda a largura que lhe derem.
    #
    # E são as larguras **preferidas**, e não o piso repetido: até a S-552 a esquerda nascia
    # com `LARGURA_MINIMA_DAS_ABAS`, o que dava no mesmo porque o piso era 720. Baixado o piso
    # para 500, repeti-lo aqui encolheria a aba de trabalho -- o piso diz onde a janela
    # **para**, e não como ela abre. Quem arbitra os dois preferidos é `showEvent`.
    janela.divisor.setSizes([LARGURA_PREFERIDA_DAS_ABAS, LARGURA_PREFERIDA_DO_VISOR])
    # `splitterMoved` só sai do gesto do mouse: `setSizes` não o emite. É o que separa "a
    # pessoa escolheu" de "o programa repartiu" -- ver `resizeEvent`.
    janela.divisor.splitterMoved.connect(janela._alca_movida_a_mao)
    janela.mesa = DisposicaoDeMesa(  # o PDF à esquerda com a aba Texto à frente (S-640)
        janela.divisor, trabalho=janela.abas, livro=janela.lado_do_livro, visor=janela.pdf.visor, estado=janela._estado,
        texto_a_frente=lambda: janela.abas.area_atual() is janela.texto, texto=janela.texto, marcar=lambda *a, **k: janela.menu.marcar(*a, **k),
    )

    janela.treino = ControladorDeTreino(janela, pedido=janela._pedido_de_treino, busy=janela.busy)
    janela.exportador = Exportador(
        janela, configuracao=janela._configuracao_de_exportacao, servico=janela._servico, busy=janela.busy
    )
    # EPUB/DOCX pela suíte, se ao alcance; sem ela os itens ficam cinza com o motivo na dica.
    janela.exportador_de_livro = exportador_de_livro.montar(
        janela, dizer=janela._dizer, trancar=partial(janela._trancar, quem="exportação do livro")
    )
    # A importação do livro inteiro, pela mesma suíte e com a mesma guarda (passo 17). A
    # ponte liga o importador ao trilho e guarda o resultado; a janela só a segura.
    # **Sem tranca** (C7): a importação só lê o PDF; a pessoa corrige um diagrama enquanto isso.
    janela.livro = importador_de_livro.montar(
        janela,
        dizer=janela._dizer,
        trancar=lambda _liberado: None,
        ocupado=janela.busy,
        trilho=janela.trilho,
        pdf_atual=lambda: janela._pdf,
        paginas=lambda: janela.pdf.page_count,
        revisao_de_texto=janela.revisao_de_texto,
    )
    janela.pgn_do_livro = livro_com_pgn.LivroComPgn(  # o .pgn que vem com o PDF digital (S-590)
        janela, dizer=janela._dizer, pdf_atual=lambda: janela._pdf, itens_atuais=lambda: janela._itens,
        painel=janela.painel, revisao=janela.revisao, texto=janela.texto, estudo=janela.estudo, galeria=janela.galeria, focar=janela._focar_aba, ir_para_pagina=janela.pdf.ir_para_pagina)


def tabela_de_comandos(janela: JanelaPrincipal) -> dict[str, Callable[[], object]]:
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
        "abrir_pdf": janela.pdf.abrir_pdf,
        "abrir_recente": janela._abrir_o_mais_recente,
        "abrir_no_leitor": janela.pdf.abrir_no_leitor_do_sistema,
        "sair": janela.close,
        # --- navegar
        "pagina_anterior": lambda: janela._na_aba_ou(janela.pdf.pagina_anterior, "pagina_anterior"),
        "proxima_pagina": lambda: janela._na_aba_ou(janela.pdf.proxima_pagina, "proxima_pagina"),
        "primeira_pagina": lambda: janela.pdf.ir_para_pagina(0),
        "ultima_pagina": lambda: janela.pdf.ir_para_pagina(janela.pdf.page_count - 1),
        "zoom_mais": janela.pdf.aumentar_zoom,
        "zoom_menos": janela.pdf.diminuir_zoom,
        "ajustar_largura": janela.pdf.ajustar_a_largura,
        "ajustar_pagina": janela.pdf.ajustar_a_pagina,
        "marcar_diagramas": lambda: janela.pdf.marcar_diagramas.toggle(),
        "roda_vira_pagina": lambda: janela.pdf.roda_vira_pagina.toggle(),
        "selecionar_area": janela.pdf.alternar_selecao,
        "tirar_caixa": janela.pdf.dispensar_a_selecionada,
        "devolver_caixas": janela.devolver_caixas,
        # --- ler e gravar
        "ler_pagina": lambda: janela._na_aba_ou(janela.ler_pagina, "recognise_page"),
        "segunda_opiniao": janela.painel.segunda_opiniao,  # C3
        "ler_melhor": janela.ler_melhor,
        "salvar": lambda: janela._na_aba_ou(janela.painel.salvar_atual, "save", "gravar"),
        "salvar_todos": janela.painel.salvar_todos,
        "aplicar_fen": janela.painel.aplicar_fen,
        "limpar_tabuleiro": janela.painel.limpar_tabuleiro,
        "apagar_casa": janela._apagar_casa,
        # **Quem desfaz é o foco, e não sempre o tabuleiro** (S-243). Ver `_no_desfazivel`.
        "desfazer": lambda: janela._no_desfazivel(lambda alvo: alvo.desfazer()),
        "refazer": lambda: janela._no_desfazivel(lambda alvo: alvo.refazer()),
        "diagrama_anterior": lambda: janela.painel.andar(-1),
        "proximo_diagrama": lambda: janela.painel.andar(1),
        # --- as outras abas
        "proximo_da_fila": janela.revisao.abrir_proximo_pendente,
        # **As duas do F9-C3**: ganharam tecla global, e o motivo está em `ui/atalhos.ATALHOS`.
        "corrigir_agora": janela.revisao.corrigir_agora,
        "anotar_pagina": janela.campo.anotar_pagina,
        "varrer_livro": janela.galeria.varrer,
        "varrer_fila": janela.abrir_fila_de_livros,
        "exportar_pgn": lambda: janela.exportador.comecar(janela._pdf),
        "exportar_epub": lambda: janela._exportar_livro("epub"),
        "importar_livro": lambda: janela.livro.comecar() if janela.livro else janela._dizer(importador_de_livro.MOTIVO_AUSENTE.splitlines()[0]),
        "cancelar_importacao": lambda: janela.livro.cancelar() if janela.livro else None,
        "trilho": janela._alternar_trilho,
        "mesa_de_texto": lambda: janela.mesa.alternar(),
        "mesa_sempre": lambda: janela.mesa.alternar_sempre(),
        "destacar_mesa": lambda: janela.mesa_destacada.alternar(),
        "primeira_duvidosa": janela.trilho._ir_para_a_primeira_duvidosa,
        "proxima_duvidosa": janela.trilho.ir_para_a_proxima_duvidosa,
        "anterior_duvidosa": janela.trilho.ir_para_a_anterior_duvidosa,
        "exportar_docx": lambda: janela._exportar_livro("docx"),
        "cancelar_exportacao": janela.exportador.cancelar,
        "treinar": janela.treino.iniciar,
        "configuracoes": lambda: dialogo_de_configuracoes.abrir(janela, dizer=janela._dizer),
        "recarregar_modelo": janela._recarregar_modelo,
        # --- a janela
        "aparencia": janela._escolher_pele,
        "densidade": janela._escolher_densidade,
        "conjunto_de_pecas": janela._escolher_conjunto,
        "paleta_de_comandos": janela.abrir_paleta,
        "legenda_de_atalhos": lambda: legenda.abrir(janela),
        "abrir_log": janela._abrir_log,
        "sobre": janela._sobre,
    }
    # As duas tabelas dos painéis entram depois: um comando que os dois declarassem seria da
    # aba, e não da janela -- é lá que o método está.
    tabela.update({acao: getattr(janela.estudo, metodo) for acao, metodo in COMANDOS_DA_SALA.items()})
    tabela.update({acao: getattr(janela.texto, metodo) for acao, metodo in COMANDOS_DO_TEXTO.items()})
    tabela.update(abas_da_suite.donos(janela.rotulagem, janela.revisao_de_texto, dizer=janela._dizer))  # C8
    tabela.update(livro_com_pgn.donos(lambda: janela.pgn_do_livro))  # S-590
    return tabela
