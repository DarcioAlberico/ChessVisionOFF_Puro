"""A janela do segundo frontend: as sete abas e a fiação entre elas (S-505).

**O que estes testes cobrem, e o que não.** Cada painel tem o seu `tests/test_qt_*.py`, e o que
ele decide sozinho é medido lá. Aqui se mede o que **nenhum painel pode medir**: que ele está
ligado ao outro. Uma ligação que falta não quebra teste de painel nenhum -- os dois continuam
verdes, cada um sabendo a sua parte, e o programa é que deixa de funcionar.

É a mesma razão de o `app_tkinter` ter os testes de aba dele: um `connect` esquecido é silencioso
por construção.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.ui import abas
from chess_diagram_ocr.ui.sala_declarada import COMANDOS_DA_ABA as COMANDOS_DA_SALA
from chess_diagram_ocr.ui.texto_declarado import COMANDOS_DA_ABA as COMANDOS_DO_TEXTO

if TYPE_CHECKING:
    from chess_diagram_ocr.service import RecognizedDiagram

if TEM_PYQT:
    from chess_diagram_ocr.qt.janela import JanelaPrincipal


class _ServicoFalso:
    """O `OcrService` visto de fora, com o que a janela lhe pede na montagem.

    Um objeto de cinco atributos e não um `MagicMock`: o que a janela pergunta ao serviço é
    justamente o que este teste quer poder afirmar, e um mock responderia a tudo.
    """

    device = None
    device_label = ""
    caption_reader = None

    def invalidate_model(self, caminho: object = None) -> None:
        self.invalidado = True

    def model_session(self, caminho: object) -> None:  # pragma: no cover - a varredura não roda
        return None


def _livro(pasta: Path, nome: str = "livro.pdf", paginas: int = 3) -> Path:
    import fitz

    caminho = pasta / nome
    doc = fitz.open()
    for _ in range(paginas):
        doc.new_page(width=300, height=400)
    doc.save(caminho)
    doc.close()
    return caminho


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class MontagemTests(unittest.TestCase):
    """A janela montada, sem livro."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)

    def janela(self) -> JanelaPrincipal:
        montada = JanelaPrincipal(
            servico=_ServicoFalso(),  # type: ignore[arg-type]
            csv_de_rotulos=self.pasta / "labels.csv",
            pasta_de_estudos=self.pasta,
        )
        self.addCleanup(descartar, montada)
        montada.resize(1400, 900)
        return montada

    def test_as_seis_abas_estao_na_ordem_da_spec(self) -> None:
        """**A ordem é o item** (S-162): Resultado, Estudo e Revisão são do diagrama aberto agora;
        Texto, Dataset e Galeria são do acervo. O corte entre os dois grupos é onde a barra muda
        de assunto."""
        janela = self.janela()
        nomes = [abas.nome_base(janela.abas.tabText(i)) for i in range(janela.abas.count())]
        self.assertEqual(
            nomes, [abas.RESULTADO, abas.ESTUDO, abas.REVISAO, abas.TEXTO, abas.DATASET, abas.GALERIA]
        )

    def test_o_visualizador_fica_ao_lado_das_abas_e_nao_dentro_delas(self) -> None:
        """É a repartição do produto: a página do livro à direita, o trabalho à esquerda.

        Pô-lo como sétima aba faria conferir um diagrama exigir trocar de aba a cada olhada --
        que é exatamente o gesto que a janela existe para não cobrar.
        """
        janela = self.janela()
        self.assertEqual(janela.divisor.count(), 2)
        self.assertIs(janela.divisor.widget(0), janela.abas)
        self.assertIs(janela.divisor.widget(1), janela.lado_do_livro)
        # À direita são dois, empilhados: a página e a anotação de campo sob ela (S-95).
        self.assertIs(janela.pdf.parent(), janela.lado_do_livro)
        self.assertIs(janela.campo.parent(), janela.lado_do_livro)

    def test_o_titulo_diz_qual_das_duas_janelas_e_esta(self) -> None:
        """As duas escrevem no mesmo `labels.csv`, e o título é o único lugar que responde
        "qual das duas é esta?" no Alt-Tab."""
        from chess_diagram_ocr.qt.janela import TITULO_DA_JANELA

        janela = self.janela()
        self.assertIn(TITULO_DA_JANELA, janela.windowTitle())

    def test_a_tabela_de_comandos_e_a_soma_de_tres(self) -> None:
        """A desta janela mais as duas `COMANDOS_DA_ABA`. Uma segunda tabela seria o lugar onde
        um comando some sem ninguém notar (S-240/S-280)."""
        janela = self.janela()
        tabela = janela._comandos()
        for acao in COMANDOS_DA_SALA:
            with self.subTest(acao=acao):
                self.assertIn(acao, tabela)
        for acao in COMANDOS_DO_TEXTO:
            with self.subTest(acao=acao):
                self.assertIn(acao, tabela)

    def test_todo_item_de_menu_tem_comando(self) -> None:
        """**É a trava que torna o menu confiável** (S-161): um menu que desenha uma linha inerte
        é pior que um menu sem ela -- a pessoa conclui que a função existe e está quebrada.

        `qt/menu.montar` levanta nomeando o que falta, então a janela ter montado já é a
        afirmação; o que este teste acrescenta é medi-la sem depender de a montagem estar aqui.
        """
        from chess_diagram_ocr.ui import menu as declaracao

        janela = self.janela()
        tabela = janela._comandos()
        faltando = [
            item.acao
            for declarado in declaracao.MENUS
            for item in declarado.itens
            if item.acao and item.acao not in tabela
        ]
        self.assertEqual(faltando, [])

    def test_todo_comando_das_abas_aponta_para_um_metodo_que_existe(self) -> None:
        """A tabela nomeia métodos por texto: um nome errado só aparece ao clicar."""
        janela = self.janela()
        tabela = janela._comandos()
        for acao in list(COMANDOS_DA_SALA) + list(COMANDOS_DO_TEXTO):
            with self.subTest(acao=acao):
                self.assertTrue(callable(tabela[acao]))

    def test_todo_comando_do_catalogo_tem_dono_nesta_janela(self) -> None:
        """**A outra metade da conta do catálogo**, e a que só esta janela pode fechar.

        A guarda pura (`test_ui_comandos.CoberturaDoCatalogoTests`) cobra que toda ação do
        catálogo esteja **declarada**: no menu, ou numa das duas listas de exceção. Ela roda sem
        abrir janela, e por isso não sabe se a declaração tem dono. Esta cobra a outra metade --
        que o dono exista e seja chamável --, e as duas juntas são a conta inteira:

            123 no catálogo = 119 na tabela da janela + 3 na linha de campo + 1 na janela de busca

        Cada exceção é cobrada **pelo dono que ela declara**, e não por um `getattr` solto: um
        `substituir_todos` que passasse a ser atendido por qualquer painel com um método de mesmo
        nome é justamente o acidente que a lista existe para impedir.

        O dono da janela de busca é a **classe** e não um atributo da janela: `JanelaDeBusca` é um
        `QDialog` criado na hora de achar, e a lista de ocorrências que o `substituir_todos` troca
        só existe enquanto ele está aberto. É por isso que o comando não está na tabela.
        """
        from chess_diagram_ocr.qt import campo as painel_de_campo
        from chess_diagram_ocr.qt.painel_de_texto import JanelaDeBusca
        from chess_diagram_ocr.ui import comandos

        janela = self.janela()
        tabela = janela._comandos()
        sem_dono: list[str] = []
        for registro in comandos.CATALOGO:
            acao = registro.acao
            dono = tabela.get(acao)
            if dono is None and acao in painel_de_campo.ACOES_PROPRIAS:
                dono = janela.campo.atender(acao)
            if dono is None and acao in comandos.NA_JANELA_DE_BUSCA:
                dono = getattr(JanelaDeBusca, acao, None)
            if not callable(dono):
                sem_dono.append(acao)
        self.assertEqual([], sem_dono, "ação do catálogo que nenhum painel desta janela atende")

    def test_as_tres_acoes_da_linha_de_campo_sao_as_do_catalogo(self) -> None:
        """Uma lista declarada e uma cópia dela divergem no primeiro nome que entra numa só.

        `qt/campo.py` atende as ações por um `dict` escrito à mão em `atender`. Se
        `comandos.NA_LINHA_DE_CAMPO` ganhar uma quarta, `ACOES_PROPRIAS` a acompanha de graça e o
        `dict` **não** -- e é o teste de cima que acusa, porque o dono some. Este aqui cobra o
        elo mais barato dos dois: que a lista do painel seja a do catálogo, e não uma segunda.
        """
        from chess_diagram_ocr.qt import campo as painel_de_campo
        from chess_diagram_ocr.ui import comandos

        self.assertEqual(painel_de_campo.ACOES_PROPRIAS, frozenset(comandos.NA_LINHA_DE_CAMPO))

    def test_a_frase_de_todo_painel_chega_ao_rodape(self) -> None:
        """Nenhum painel sabe que o rodapé existe, e é a janela que os liga."""
        janela = self.janela()
        for painel, frase in (
            (janela.painel, "do Resultado"),
            (janela.pdf, "do visualizador"),
            (janela.galeria, "da Galeria"),
            (janela.revisao, "da Revisão"),
            (janela.estudo, "do Estudo"),
            (janela.dataset, "do Dataset"),
            (janela.texto, "do Texto"),
        ):
            with self.subTest(painel=frase):
                painel.estado.emit(f"uma frase {frase}")
                self.assertEqual(janela.rodape.mensagem(), f"uma frase {frase}")

    def test_as_abas_dizem_quanto_trabalho_carregam(self) -> None:
        """A contagem no rótulo (S-162), e ela só muda quando alguém a muda."""
        janela = self.janela()
        janela.revisao.queue.items = []
        janela._atualizar_abas()
        rotulos = {abas.nome_base(janela.abas.tabText(i)): janela.abas.tabText(i) for i in range(janela.abas.count())}
        self.assertEqual(rotulos[abas.GALERIA], abas.rotulo(abas.GALERIA, 0))
        self.assertEqual(rotulos[abas.RESULTADO], abas.RESULTADO, "aba sem contagem não ganha número")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class FiacaoTests(unittest.TestCase):
    """As setas entre painéis. **Uma ligação que falta não quebra teste de painel nenhum.**"""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.livro = _livro(self.pasta)
        self.addCleanup(self.app.processEvents)

    def janela(self, *, com_livro: bool = True) -> JanelaPrincipal:
        montada = JanelaPrincipal(
            servico=_ServicoFalso(),  # type: ignore[arg-type]
            csv_de_rotulos=self.pasta / "labels.csv",
            pasta_de_estudos=self.pasta,
            # **Sem isto o teste lê e grava em `data/gallery/` de verdade** -- o mesmo defeito que
            # o painel da galeria já tinha, agora fechado na ponta da janela.
            pasta_da_galeria=self.pasta,
        )
        self.addCleanup(descartar, montada)
        montada.resize(1400, 900)
        if com_livro:
            montada.abrir_pdf(self.livro)
            self.app.processEvents()
        return montada

    def _varrido(self, *paginas: int) -> None:
        """Deixa o livro com um índice de galeria já varrido, um diagrama por página."""
        from chess_diagram_ocr.gallery_scan import GalleryEntry, GalleryIndex, save_index

        save_index(
            self.livro,
            GalleryIndex(
                source_pdf=str(self.livro),
                entries=[
                    GalleryEntry(
                        page_index=pagina,
                        diagram_index=0,
                        placement="8/8/8/8/8/8/8/K6k",
                        side_to_move="w",
                        image_path="",
                        caption="",
                    )
                    for pagina in paginas
                ],
                complete=True,
            ),
            directory=self.pasta,
        )

    def _diagrama(self, indice: int = 0) -> RecognizedDiagram:
        import numpy as np

        from chess_diagram_ocr.service import RecognizedDiagram

        return RecognizedDiagram(
            index=indice,
            board_rgb=np.full((64, 64, 3), 200, np.uint8),
            placement="8/8/8/8/8/8/8/K6k",
            min_confidence=0.93,
            square_confidences=[0.99] * 64,
            side_to_move="w",
        )

    def test_abrir_o_livro_chega_a_galeria_ao_estudo_e_ao_texto(self) -> None:
        """**As três precisam do livro antes de qualquer varredura.**

        Sem isto a Galeria só conheceria o livro depois de varrer -- e o número do lance digitado
        na aba Resultado (S-71) seria gravado num modelo sem `pdf_path`, que descarta em silêncio.
        """
        janela = self.janela()
        self.assertEqual(janela.galeria.model.pdf_path, self.livro)
        self.assertEqual(janela.estudo.sala.documento, str(self.livro))
        self.assertEqual(janela.texto._pdf, self.livro)
        self.assertIn("livro.pdf", janela.windowTitle())

    def test_um_pdf_que_nao_abre_nao_troca_o_livro_de_ninguem(self) -> None:
        """**Abrir antes de trocar** (S-123): com o aviso antes da abertura, um PDF quebrado já
        tinha apontado a Galeria para ele -- e o `Ctrl+S` seguinte gravava sob o nome errado."""
        janela = self.janela()
        quebrado = self.pasta / "quebrado.pdf"
        quebrado.write_bytes(b"isto nao e um PDF")
        with mock.patch("chess_diagram_ocr.qt.painel_do_pdf.QMessageBox.critical") as caixa:
            janela.abrir_pdf(quebrado)
        self.assertTrue(caixa.called)
        self.assertEqual(janela.galeria.model.pdf_path, self.livro, "a Galeria seguiu o que não abriu")
        self.assertEqual(janela._pdf, self.livro)

    def test_a_galeria_vira_a_pagina_do_visualizador(self) -> None:
        """A galeria navega por diagrama e arrasta o visualizador junto (S-67)."""
        janela = self.janela()
        janela.pdf.ir_para_pagina(2)
        self.assertEqual(janela.pdf.page_index, 2)
        janela.galeria.pediu_pagina.emit(0)
        self.assertEqual(janela.pdf.page_index, 0)

    def test_virar_a_pagina_avisa_a_galeria_e_guarda_o_que_estava_no_editor(self) -> None:
        """As duas pontas da virada: o editor guarda **antes**, a galeria acompanha **depois**.

        **A afirmação é sobre o efeito, e não sobre a chamada.** Um `patch.object` sobre método já
        ligado a sinal não intercepta nada -- nem na instância nem na classe: o `connect` guardou o
        método ligado, e o Qt chama aquele. Ver [[patch-nao-intercepta-slot-ligado]].
        """
        self._varrido(0, 1)
        janela = self.janela()
        janela._chegaram_itens(0, [self._diagrama()], None)

        janela.pdf.proxima_pagina()

        guardada = janela.painel.paginas.get(str(self.livro), 0, janela._parametros_de_ocr())
        self.assertIsNotNone(guardada, "o editor não guardou a página antes de ela virar")
        self.assertEqual(janela.galeria.model.page_index, 1, "a galeria não acompanhou a virada")

    def test_a_revisao_manda_varrer_e_quem_varre_e_a_galeria(self) -> None:
        """**Uma varredura por livro** (S-119): duas passadas custavam 338 s + 299 s.

        **O espião entra na escolha do escopo, e não no método.** Um `patch.object` sobre
        `galeria.varrer` não intercepta nada: o `connect` guardou o método **ligado** no momento
        da montagem, e trocar o atributo da instância depois não troca o que o sinal chama. O
        sintoma foi a suíte parada -- o `varrer` de verdade rodou e abriu o diálogo do escopo, que
        sob `offscreen` espera para sempre por um clique que ninguém vai dar.
        """
        janela = self.janela()
        pedidos: list[object] = []

        def _desistindo(aberto: object) -> None:
            pedidos.append(aberto)
            return None  # "desistiu no diálogo": a varredura não começa

        janela.galeria._perguntar_escopo = _desistindo
        janela.revisao.pediu_varredura.emit()
        self.assertEqual(pedidos, [self.livro], "a varredura não chegou à Galeria")

    def test_a_galeria_recebe_o_coletor_da_fila(self) -> None:
        """A fila de revisão sai da mesma passada, e nenhuma das duas abas conhece a outra.

        A afirmação é sobre **de quem** é o coletor que a Galeria vai pedir, e não sobre uma
        chamada: pedi-lo de verdade abriria uma varredura. `==` e não `is` porque um método ligado
        é criado a cada acesso.
        """
        janela = self.janela()
        self.assertEqual(janela.galeria._sumidouro_de_revisao, janela.revisao.sumidouro)

    def test_gravar_uma_amostra_pinta_a_caixa_e_reconta_as_abas(self) -> None:
        janela = self.janela()
        with mock.patch.object(janela.dataset, "reload") as releu, mock.patch.object(
            janela, "_atualizar_abas"
        ) as recontou:
            janela.painel.salvou.emit(0)
        self.assertIn(0, janela._salvos.get(janela.pdf.page_index, set()))
        self.assertTrue(releu.called, "o Dataset não foi avisado da amostra nova")
        self.assertTrue(recontou.called)

    def test_salvar_um_item_da_fila_fecha_o_item(self) -> None:
        """`Ctrl+S` sobre um item da fila também o fecha (S-22), e quem fecha é a aba de Revisão."""
        janela = self.janela()
        with mock.patch.object(janela.revisao, "aplicar_correcao") as fechou:
            janela.painel.revisou.emit(4, "8/8/8/8/8/8/8/K6k", "b")
        fechou.assert_called_with(4, "8/8/8/8/8/8/8/K6k", "b")

    def test_regravar_a_linha_avisa_o_dataset_e_nao_pinta_caixa(self) -> None:
        """Regravar a linha de uma amostra que já existia não faz diagrama nenhum ficar verde --
        ele já estava. O que mudou foi o rótulo (S-23)."""
        janela = self.janela()
        antes = dict(janela._salvos)
        with mock.patch.object(janela.dataset, "reload") as releu:
            janela.painel.regravou.emit()
        self.assertTrue(releu.called)
        self.assertEqual(janela._salvos, antes)

    def test_o_dataset_manda_editar_e_a_aba_resultado_vem_para_a_frente(self) -> None:
        """Abrir a amostra numa aba que ninguém está vendo é a mesma classe de silêncio que a
        S-161 registra: a ação acontece e nada na tela diz que aconteceu."""
        janela = self.janela()
        janela.abas.setCurrentIndex(janela.abas.indexOf(janela.dataset))
        with mock.patch.object(janela.painel, "carregar_amostra", return_value=True) as abriu:
            janela.dataset.editar.emit(object())
        self.assertTrue(abriu.called)
        self.assertIs(janela.abas.currentWidget(), janela.painel)

    def test_a_revisao_manda_corrigir_e_a_aba_resultado_vem_para_a_frente(self) -> None:
        janela = self.janela()
        janela.abas.setCurrentIndex(janela.abas.indexOf(janela.revisao))
        with mock.patch.object(janela.painel, "carregar_item_de_revisao", return_value=True) as abriu:
            janela.revisao.abriu.emit(object(), 2)
        abriu.assert_called_with(mock.ANY, 2)
        self.assertIs(janela.abas.currentWidget(), janela.painel)

    def test_a_aba_que_falhou_em_abrir_nao_e_trazida_para_a_frente(self) -> None:
        """A miniatura pode ter sumido do disco. Trazer a aba mostraria o diagrama anterior como
        se fosse o item pedido."""
        janela = self.janela()
        janela.abas.setCurrentIndex(janela.abas.indexOf(janela.revisao))
        with mock.patch.object(janela.painel, "carregar_item_de_revisao", return_value=False):
            janela.revisao.abriu.emit(object(), 2)
        self.assertIs(janela.abas.currentWidget(), janela.revisao)

    def test_o_estudo_pergunta_a_posicao_ao_resultado_e_o_lance_a_galeria(self) -> None:
        """O vínculo é de mão única: o estudo **lê** o diagrama selecionado e nunca escreve de
        volta -- um lance jogado no estudo não é uma correção do OCR (S-269)."""
        janela = self.janela()
        with mock.patch.object(janela.painel, "posicao_de_estudo", return_value=None) as perguntou:
            self.assertIsNone(janela._posicao_de_estudo())
        self.assertEqual(perguntou.call_args.kwargs["lance_de"], janela.galeria.move_number_at)

    def test_a_linha_do_estudo_vai_para_o_texto_e_traz_a_aba(self) -> None:
        janela = self.janela()
        self.assertTrue(janela._linha_para_o_texto("1. e4 e5"))
        self.assertIn("e4", janela.texto.texto())
        self.assertIs(janela.abas.currentWidget(), janela.texto)

    def test_a_linha_impressa_do_estudo_vem_da_aba_de_texto(self) -> None:
        """Lá o parágrafo do livro vira variante; aqui a aba de Texto é quem o leu (S-283)."""
        janela = self.janela()
        with mock.patch.object(janela.texto, "notacao_do_diagrama", return_value="1. e4") as leu:
            self.assertEqual(janela._linha_impressa(mock.Mock(pagina=2, diagrama=1)), "1. e4")
        leu.assert_called_with(2, 1)

    def test_o_estudo_leva_o_visualizador_a_pagina_da_ancora(self) -> None:
        """`False` quando o livro não é este -- e aí a sala diz isso no rodapé (S-284)."""
        janela = self.janela()
        self.assertTrue(janela._abrir_pagina_do_estudo(mock.Mock(documento=str(self.livro), pagina=2)))
        self.assertEqual(janela.pdf.page_index, 2)
        self.assertFalse(janela._abrir_pagina_do_estudo(mock.Mock(documento="outro.pdf", pagina=1)))

    def test_a_caixa_tirada_some_da_pagina_e_volta_com_o_comando(self) -> None:
        """A remoção é da pessoa e por (livro, página): ela não apaga nada no disco, e é isso que
        a torna reversível (S-177)."""
        from chess_diagram_ocr.ui.page_overlay import DiagramBox, PageBoxes

        janela = self.janela()
        # **Os parâmetros são os da janela, e não uns quaisquer**: eles fazem parte da chave do
        # cache -- é assim que uma leitura feita com outro DPI deixa de responder por esta página
        # --, e caixas guardadas com outros nunca voltam.
        caixas = PageBoxes(
            page_index=0,
            params=janela._parametros(),
            boxes=(DiagramBox(index=0, bbox_pdf=(10.0, 10.0, 60.0, 60.0)),),
        )
        janela._guardar(caixas)
        janela._publicar_caixas(caixas)
        self.assertEqual(len(janela.pdf.boxes or ()), 1)

        janela.pdf.caixa_dispensada.emit(0)
        self.assertEqual(len(janela.pdf.boxes or ()), 0)
        janela.devolver_caixas()
        self.assertEqual(len(janela.pdf.boxes or ()), 1)

    # ------------------------------------------- os cinco botões que voltaram ao visualizador

    def test_os_dois_botoes_de_ocr_do_visualizador_chegam_a_janela(self) -> None:
        """A ligação é afirmada **pelo efeito**, e não trocando o método por um espião.

        Depois do `connect`, trocar `janela.ler_pagina` não troca quem o sinal chama -- o `connect`
        guardou o objeto ligado. Um teste que patchasse o método passaria em verde com o fio
        cortado. Aqui a janela está sem página rasterizada, e a pré-condição no rodapé é a prova de
        que o pedido chegou.
        """
        janela = self.janela(com_livro=False)
        janela.pdf.leitura_pedida.emit(False)
        self.assertEqual("Abra um PDF antes de ler a página.", janela.rodape.mensagem())

    def test_exportar_pelo_visualizador_chega_ao_exportador(self) -> None:
        """Mesma régua: sem livro, a pré-condição do exportador é o que prova o fio."""
        janela = self.janela(com_livro=False)
        janela.pdf.exportacao_pedida.emit()
        self.assertEqual("Abra um PDF antes de exportar o PGN.", janela.rodape.mensagem())

    def test_a_exportacao_acende_o_cancelar_do_visualizador(self) -> None:
        """O `controles` do exportador chega ao painel, e não só ao trancamento da janela."""
        janela = self.janela()
        self.assertFalse(janela.pdf.btn_cancelar_exportacao.isEnabled())

        janela.exportador.controles.emit(False)

        self.assertTrue(janela.pdf.btn_cancelar_exportacao.isEnabled())
        self.assertFalse(janela.pdf.btn_exportar.isEnabled(), "dá para começar duas exportações")
        self.assertFalse(janela.abas.isEnabled(), "o resto da janela não trancou")

    def test_ler_melhor_e_ler_pagina_deixaram_de_ser_o_mesmo_comando(self) -> None:
        """**A regressão que o porte tinha deixado passar** (S-506).

        Os dois nomes do catálogo apontavam para `ler_pagina`, então "OCR melhor diagrama" lia a
        página inteira. Nenhuma guarda acusava: os dois comandos tinham dono e o dono era chamável
        -- a conta do catálogo pergunta se **há** dono, não se ele é o certo.
        """
        janela = self.janela(com_livro=False)
        tabela = janela._comandos()
        self.assertIsNot(tabela["ler_melhor"], tabela["ler_pagina"])

    def test_o_teto_de_diagramas_e_o_que_separa_os_dois(self) -> None:
        """`ocr_best` era `max_boards=1` e `ocr_all` era a preferência inteira, no Tk."""
        from chess_diagram_ocr.qt.janela import DEFAULT_MAX_BOARDS

        janela = self.janela(com_livro=False)
        self.assertEqual(1, janela._opcoes(1).max_boards)
        self.assertEqual(DEFAULT_MAX_BOARDS, janela._opcoes().max_boards)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
