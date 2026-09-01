"""A janela do segundo frontend: as sete abas e a fiação entre elas (S-505).

**O que estes testes cobrem, e o que não.** Cada painel tem o seu `tests/test_qt_*.py`, e o que
ele decide sozinho é medido lá. Aqui se mede o que **nenhum painel pode medir**: que ele está
ligado ao outro. Uma ligação que falta não quebra teste de painel nenhum -- os dois continuam
verdes, cada um sabendo a sua parte, e o programa é que deixa de funcionar.

É a mesma razão de o `app_tkinter` ter os testes de aba dele: um `connect` esquecido é silencioso
por construção.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.ui import abas, pele
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


_FONTE_DA_JANELA = Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr" / "qt" / "janela.py"


def _comandos_inertes(fonte: str) -> list[str]:
    """As acoes que `_comandos` amarra a um `lambda: None`, lidas do texto do modulo (PR #25).

    **Sobre a fonte e nao sobre o objeto, e a diferenca custou uma guarda vacua.** A primeira
    versao disto pedia `inspect.getsource` da funcao amarrada, que para um `lambda` dentro de um
    dicionario devolve a **linha inteira** (`"abrir_recente": lambda: None,`) -- texto que nao
    parseia como expressao, cai num `except SyntaxError` e faz a guarda passar em verde sobre o
    caso que ela existe para pegar.

    Devolve os nomes na ordem em que aparecem, para a mensagem de falha ser estavel.
    """
    metodo = next(
        no
        for no in ast.walk(ast.parse(fonte))
        if isinstance(no, ast.FunctionDef) and no.name == "_comandos"
    )
    return [
        chave.value
        for dicionario in ast.walk(metodo)
        if isinstance(dicionario, ast.Dict)
        for chave, valor in zip(dicionario.keys, dicionario.values, strict=True)
        if isinstance(chave, ast.Constant)
        and isinstance(valor, ast.Lambda)
        and isinstance(valor.body, ast.Constant)
        and valor.body.value is None
    ]


def _fracao(janela: JanelaPrincipal) -> float:
    """Onde a alca do divisor esta, como fracao da largura. Lida da tela, e nao do estado."""
    tamanhos = janela.divisor.sizes()
    return tamanhos[0] / sum(tamanhos)


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
            caminho_do_estado=self.pasta / "janela.json",
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

    INERTES_DECLARADOS: dict[str, str] = {}
    """Os comandos que **podem** nao fazer nada, e por que -- uma linha cada.

    **Vazia, e e o estado certo.** O PR #25, que atacou a troca de pele em paralelo a este
    trabalho, declarava `abrir_recente` aqui: *"e o pai de um submenu, e nao uma linha clicavel; e
    hoje ele esta vazio porque a janela do Qt nao persiste `AppState.pdf_history`"*. As duas metades
    da isencao caducaram no mesmo commit -- o estado passou a ser persistido, e o comando ganhou
    dono em `_abrir_o_mais_recente`, que abre o livro anterior a este.

    A lista fica: sem ela, `lambda: None` volta a ser a saida facil para um comando que o catalogo
    declara e ninguem implementou. E `test_a_lista_de_inertes_nao_guarda_quem_ja_faz_algo` cobra o
    outro sentido, que e como uma lista de excecao envelhece."""

    def test_nenhum_comando_do_menu_e_inerte(self) -> None:
        """**A guarda de cobertura e satisfeita por um `lambda: None`, e foi** (PR #25).

        `test_todo_item_de_menu_tem_comando` pergunta se a acao tem entrada na tabela; um comando
        que nao faz nada **tem**. Foi assim que `aparencia`, `densidade` e `abrir_recente` ficaram
        parados desde a montagem da janela com todas as guardas do menu verdes -- e e a mesma
        fenda que a conta do catalogo deixa aberta, porque ela pergunta se o dono e chamavel.

        A varredura e sobre a **fonte** do arquivo, e nao sobre o objeto: ver `_comandos_inertes`.
        """
        inertes = _comandos_inertes(_FONTE_DA_JANELA.read_text(encoding="utf-8"))
        self.assertEqual(
            sorted(set(inertes) - set(self.INERTES_DECLARADOS)),
            [],
            "comando de menu que nao faz nada. Implemente-o, ou declare o motivo em "
            "INERTES_DECLARADOS.",
        )

    def test_a_lista_de_inertes_nao_guarda_quem_ja_faz_algo(self) -> None:
        """Isencao que sobra e isencao que esconde: o proximo `lambda: None` daquela acao entraria
        sem ninguem assinar.

        **Nao mede nada enquanto a lista esta vazia, e isso esta dito de proposito.** O trabalho
        dela comeca no dia em que alguem acrescentar uma entrada; ate la quem cobra e a de cima,
        que e absoluta justamente por nao haver isencao nenhuma.
        """
        inertes = set(_comandos_inertes(_FONTE_DA_JANELA.read_text(encoding="utf-8")))
        self.assertEqual(sorted(set(self.INERTES_DECLARADOS) - inertes), [])

    def test_a_varredura_de_inertes_acha_um_comando_inerte(self) -> None:
        """**A anti-vacuidade, e ela existe porque a primeira versao da guarda era vacua** (#25).

        Aquela versao pedia `inspect.getsource` do `lambda`, que devolve a **linha do dicionario**
        (`"abrir_recente": lambda: None,`). Isso nao parseia como expressao, caia num
        `except SyntaxError`, e o teste passava em verde com um comando inerte ainda no arquivo --
        engolindo em silencio exatamente o caso que existe para pegar.

        Uma guarda que so olha um arquivo limpo nao prova que **sabe olhar**. Esta afirma o
        detector contra uma fonte de mentira, e e a diferenca entre "nao achou" e "nao procura".
        """
        fonte = (
            "class J:\n"
            "    def _comandos(self):\n"
            "        return {\n"
            '            "faz_algo": self.metodo,\n'
            '            "nao_faz": lambda: None,\n'
            '            "chama": lambda: outra(self),\n'
            "        }\n"
        )
        self.assertEqual(_comandos_inertes(fonte), ["nao_faz"])

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
            caminho_do_estado=self.pasta / "janela.json",
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


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class EstadoEntreSessoesTests(unittest.TestCase):
    """O que a janela lembra de uma abertura para a seguinte (S-25/S-156/S-322).

    **Duas janelas por teste, e é o desenho.** Afirmar que a primeira gravou o arquivo mede o
    formato, não a promessa: o que a pessoa sente é a *segunda* abrir onde a primeira parou. Cada
    teste aqui fecha uma janela e monta outra sobre o mesmo arquivo.
    """

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.livro = _livro(self.pasta, paginas=6)
        self.estado = self.pasta / "janela.json"
        self.addCleanup(self.app.processEvents)

    def janela(self, *, tamanho: tuple[int, int] | None = (1400, 900)) -> JanelaPrincipal:
        """`tamanho=None` deixa a janela com a geometria que ela mesma restaurou do estado."""
        montada = JanelaPrincipal(
            servico=_ServicoFalso(),  # type: ignore[arg-type]
            csv_de_rotulos=self.pasta / "labels.csv",
            pasta_de_estudos=self.pasta,
            pasta_da_galeria=self.pasta,
            caminho_do_estado=self.estado,
        )
        self.addCleanup(descartar, montada)
        if tamanho is not None:
            montada.resize(*tamanho)
        return montada

    def test_o_livro_e_a_pagina_voltam_na_sessao_seguinte(self) -> None:
        """A promessa inteira num teste: fechar na página 4 do livro e reabrir ali."""
        primeira = self.janela()
        primeira.abrir_pdf(self.livro)
        self.app.processEvents()
        primeira.pdf.ir_para_pagina(3)
        self.app.processEvents()
        primeira.close()

        self.assertTrue(self.estado.exists(), "fechar a janela não gravou o estado")
        segunda = self.janela()
        self.assertTrue(segunda.abrir_livro_da_sessao())
        self.app.processEvents()
        self.assertEqual(self.livro, segunda.pdf.source)
        self.assertEqual(3, segunda.pdf.page_index)

    def test_a_pagina_e_de_cada_livro_e_nao_so_a_do_ultimo(self) -> None:
        """O histórico guarda 50 livros, e a pergunta que ele responde é "onde eu parei **neste**?"

        A anotação é na virada da página e não no fechamento: sem isso, trocar de livro no meio da
        sessão perderia a página do primeiro, que é o gesto mais comum de quem compara dois livros.
        """
        outro = _livro(self.pasta, nome="outro.pdf", paginas=6)
        primeira = self.janela()
        primeira.abrir_pdf(self.livro)
        self.app.processEvents()
        primeira.pdf.ir_para_pagina(2)
        self.app.processEvents()
        primeira.abrir_pdf(outro)
        self.app.processEvents()
        primeira.pdf.ir_para_pagina(4)
        self.app.processEvents()
        primeira.close()

        segunda = self.janela()
        segunda.abrir_pdf(self.livro)
        self.app.processEvents()
        self.assertEqual(2, segunda.pdf.page_index, "o livro anterior perdeu a página")
        segunda.abrir_pdf(outro)
        self.app.processEvents()
        self.assertEqual(4, segunda.pdf.page_index)

    def test_os_interruptores_do_visualizador_sobrevivem_ao_fechamento(self) -> None:
        """Escolha de visualização que se perde a cada abertura vira tarefa a refazer toda vez."""
        primeira = self.janela()
        primeira.pdf.marcar_diagramas.setChecked(False)
        primeira.pdf.roda_vira_pagina.setChecked(False)
        primeira.close()

        segunda = self.janela()
        self.assertFalse(segunda.pdf.marcar_diagramas.isChecked())
        self.assertFalse(segunda.pdf.roda_vira_pagina.isChecked())

    def test_o_mapa_de_incerteza_desligado_continua_desligado(self) -> None:
        """Ele existia no painel do Tk e o porte nao o trouxe: a tinta ficava ligada para sempre.

        Quem confere uma pagina ja revista trabalhava com todas as casas duvidosas pintadas por
        baixo das pecas -- e nao havia como desligar.
        """
        primeira = self.janela()
        self.assertTrue(primeira.painel.heatmap.isChecked(), "nasce ligado, que e como se descobre")
        primeira.painel.heatmap.setChecked(False)
        self.assertFalse(primeira.painel.tabuleiro._heatmap, "a caixa nao alcancou o tabuleiro")
        primeira.close()

        segunda = self.janela()
        self.assertFalse(segunda.painel.heatmap.isChecked())
        self.assertFalse(segunda.painel.tabuleiro._heatmap)

    def test_o_zoom_e_a_quebra_da_aba_de_texto_voltam(self) -> None:
        """O terceiro zoom do programa (S-291), e a quebra que quem lê notação desliga."""
        primeira = self.janela()
        primeira.texto.aplicar_zoom(2, avisar=False)
        primeira.texto.definir_quebra(False)
        primeira.close()

        segunda = self.janela()
        self.assertEqual(2, segunda.texto.zoom_da_vista)
        self.assertFalse(segunda.texto.quebra)

    def test_a_aba_aberta_volta_pelo_nome_e_nao_pelo_indice(self) -> None:
        """Índice não sobrevive a reordenar as abas, e a S-162 é reordená-las."""
        primeira = self.janela()
        primeira.abas.setCurrentIndex(primeira._indice_da_aba(abas.DATASET) or 0)
        primeira.close()

        self.assertEqual(abas.DATASET, primeira._estado.active_tab)
        segunda = self.janela()
        self.assertEqual(abas.DATASET, abas.nome_base(segunda.abas.tabText(segunda.abas.currentIndex())))

    def test_a_primeira_abertura_cai_na_aba_de_trabalho(self) -> None:
        """Sem nada guardado, a Resultado -- e não a primeira que o `QTabWidget` mostrar."""
        janela = self.janela()
        self.assertEqual(
            abas.ABA_DE_TRABALHO, abas.nome_base(janela.abas.tabText(janela.abas.currentIndex()))
        )

    def test_nada_e_gravado_antes_de_o_estado_chegar_aos_widgets(self) -> None:
        """A guarda da S-322, e o defeito que ela impede é o pior de todos aqui.

        Gravar antes de aplicar lê os widgets **nos padrões de fábrica** e os escreve por cima do
        que estava no disco -- e aí nada do que este arquivo promete lembrar sobrevive a fechar a
        janela, sem que nenhum teste de valor individual acuse.
        """
        janela = self.janela()
        janela._estado_aplicado = False
        janela._gravar_estado()
        self.assertFalse(self.estado.exists(), "gravou com o estado ainda não aplicado")

    def test_o_divisor_nao_e_medido_antes_de_a_janela_aparecer(self) -> None:
        """**Divisor não mapeado não é divisor medido** (S-311).

        Antes do `show()` o `QSplitter` devolve os tamanhos declarados na montagem, que são do
        leiaute e não de ninguém: anotá-los apagaria a alça da sessão anterior antes de a pessoa
        tocar em nada.
        """
        janela = self.janela()
        janela._estado.sash_fraction = 0.66
        janela._anotar_arranjo()
        self.assertEqual(0.66, janela._estado.sash_fraction)

    def test_o_divisor_arrastado_volta_no_lugar(self) -> None:
        """`_set_initial_sashes` do outro frontend repunha o divisor a **cada** abertura: quem
        trabalha com o PDF grande o arrastava e o perdia toda sessao (S-156).

        A fracao e lida da tela e nao cravada no teste: os dois lados tem largura minima, e o
        `QSplitter` grampeia o que se pede a elas -- cravar um numero mediria o grampo.
        """
        primeira = self.janela()
        # **2200 e nao os 1400 das outras**, e o numero e medido: com 1534 px a janela esta no
        # piso dos dois lados -- `[720, 810]` -- e o divisor nao tem folga nenhuma para arrastar.
        primeira.resize(2200, 1000)
        primeira.show()
        self.app.processEvents()
        padrao = _fracao(primeira)
        largura = sum(primeira.divisor.sizes())
        primeira.divisor.setSizes([int(largura * 0.6), largura - int(largura * 0.6)])
        self.app.processEvents()
        arrastado = _fracao(primeira)
        self.assertNotAlmostEqual(padrao, arrastado, places=2, msg="o arrasto nao moveu nada")
        primeira.close()

        self.assertAlmostEqual(arrastado, primeira._estado.sash_fraction, places=2)
        # Sem `tamanho`: a segunda janela abre com a geometria que ela restaurou, e e dentro dela
        # que a fracao do divisor tem de caber. Encolhe-la aqui mediria de novo o grampo.
        segunda = self.janela(tamanho=None)
        segunda.show()
        self.app.processEvents()
        self.assertAlmostEqual(arrastado, _fracao(segunda), places=2)
        self.assertGreater(segunda.width(), 2000, "a geometria da sessao anterior nao voltou")

    def test_a_geometria_guardada_e_a_de_fora_do_maximizado(self) -> None:
        """`normalGeometry` é o que substitui a recusa do `1x1+-32000+-32000` do Tk (S-156)."""
        from chess_diagram_ocr.ui import geometria

        janela = self.janela()
        janela.show()
        self.app.processEvents()
        janela._anotar_arranjo()
        lida = geometria.geometria_de_texto(janela._estado.window_geometry)
        self.assertIsNotNone(lida, f"não é geometria: {janela._estado.window_geometry!r}")
        assert lida is not None
        self.assertGreater(lida.largura, 1)
        self.assertGreater(lida.altura, 1)

    def test_a_geometria_de_um_monitor_que_sumiu_e_corrigida(self) -> None:
        """Trocar de monitor entre duas sessões abria a janela fora da tela, sem erro nenhum.

        A decisão é a pura de `ui/geometria.py`, a mesma dos dois frontends; o que se afirma aqui
        é que esta janela **passa por ela** em vez de aplicar o texto guardado como veio.
        """
        from chess_diagram_ocr.qt.janela import plataforma

        self.estado.write_text(
            '{"version": 6, "window_geometry": "1400x900+9000+9000"}', encoding="utf-8"
        )
        with mock.patch.object(plataforma, "monitores", lambda: ((0, 0, 1920, 1040),)):
            janela = self.janela()
        self.assertLess(janela.x(), 1920, "a janela abriu no monitor que não existe mais")

    def test_o_ultimo_livro_que_sumiu_do_disco_e_dito_e_nao_engolido(self) -> None:
        """Antes isto era um `return` silencioso, e a pessoa só via outro livro abrir."""
        self.estado.write_text(
            '{"version": 6, "last_pdf": "' + str(self.pasta / "sumiu.pdf").replace("\\", "/") + '"}',
            encoding="utf-8",
        )
        janela = self.janela()
        recados: list[str] = []
        janela.rodape.mostrar = lambda texto, **_: recados.append(texto)  # type: ignore[assignment]
        janela.abrir_livro_da_sessao()
        self.app.processEvents()
        self.assertTrue(any("não encontrado" in recado for recado in recados), recados)

    def test_o_estado_do_tk_e_herdado_uma_vez_e_nao_reescrito(self) -> None:
        """O arquivo mudou de nome com o corte, e o histórico de 50 livros não pode ir junto."""
        from chess_diagram_ocr.qt import janela as modulo

        herdado = self.pasta / "app_tkinter_state.json"
        herdado.write_text('{"version": 6, "texto_zoom": 3}', encoding="utf-8")
        novo = self.pasta / "novo.json"
        with (
            mock.patch.object(modulo, "CAMINHO_DO_ESTADO", novo),
            mock.patch.object(modulo, "CAMINHO_HERDADO_DO_ESTADO", herdado),
        ):
            montada = JanelaPrincipal(
                servico=_ServicoFalso(),  # type: ignore[arg-type]
                csv_de_rotulos=self.pasta / "labels.csv",
                pasta_de_estudos=self.pasta,
                pasta_da_galeria=self.pasta,
            )
            self.addCleanup(descartar, montada)
            self.assertEqual(3, montada.texto.zoom_da_vista, "o estado antigo não foi lido")
            montada.close()

        self.assertTrue(novo.exists(), "gravou de volta no nome antigo")
        self.assertIn('"texto_zoom": 3', herdado.read_text(encoding="utf-8"))


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class AparenciaTests(unittest.TestCase):
    """`Ver ▸ Aparência` e `Ver ▸ Densidade`, que ate o corte marcavam e nao faziam nada (S-506).

    **O defeito que estes testes fecham passava na conta do catalogo.** Os dois comandos tinham
    dono e o dono era chamavel -- um `lambda: None` --, e a guarda pergunta se **ha** dono, nao se
    ele faz alguma coisa. O menu desenhava as tres peles e as duas densidades, marcava a escolhida,
    e a janela continuava exatamente a mesma.
    """

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.estado = self.pasta / "janela.json"
        self.addCleanup(self.app.processEvents)
        # A folha de estilo e da **aplicacao**, e um teste que a deixa escura contamina o vizinho.
        from chess_diagram_ocr.qt import tema

        self.addCleanup(tema.aplicar_tema)

    def janela(self) -> JanelaPrincipal:
        montada = JanelaPrincipal(
            servico=_ServicoFalso(),  # type: ignore[arg-type]
            csv_de_rotulos=self.pasta / "labels.csv",
            pasta_de_estudos=self.pasta,
            pasta_da_galeria=self.pasta,
            caminho_do_estado=self.estado,
        )
        self.addCleanup(descartar, montada)
        montada.resize(1400, 900)
        return montada

    @staticmethod
    def _cromo(janela: JanelaPrincipal) -> list[str]:
        """O que esta desenhado no conteiner do cromo, por nome de classe."""
        pilha = janela._pilha_do_cromo
        nomes = []
        for indice in range(pilha.count()):
            item = pilha.itemAt(indice)
            widget = item.widget() if item is not None else None
            if widget is not None:
                nomes.append(type(widget).__name__)
        return nomes

    @staticmethod
    def _trocar(janela: JanelaPrincipal, pele_nova: str) -> None:
        """O que o clique no item de menu faz: marca o valor e dispara o comando."""
        janela.menu.escolher("aparencia", pele_nova)
        janela._comandos()["aparencia"]()

    def test_a_classica_nao_desenha_cromo_nenhum(self) -> None:
        """A fundacao se prova quando ela nao muda nada: a classica e a janela de sempre (S-221)."""
        janela = self.janela()
        self.assertEqual([], self._cromo(janela))
        self.assertTrue(janela.cromo.isHidden())

    def test_a_fita_e_a_fila_entram_no_lugar_do_cromo(self) -> None:
        """As duas peles das imagens, e o modulo que cada uma monta."""
        janela = self.janela()
        self._trocar(janela, pele.FITA)
        self.assertEqual(["Fita"], self._cromo(janela))
        self.assertFalse(janela.cromo.isHidden())
        self._trocar(janela, pele.FOCO)
        self.assertEqual(["Fila"], self._cromo(janela))
        self._trocar(janela, pele.CLASSICA)
        self.assertEqual([], self._cromo(janela))

    def test_o_menu_abre_com_a_pele_e_a_densidade_em_vigor_marcadas(self) -> None:
        """Submenu sem marca e o mesmo que dizer "nenhuma delas esta em uso"."""
        janela = self.janela()
        self.assertEqual(pele.CLASSICA, janela.menu.escolhido("aparencia"))
        self.assertEqual(pele.CONFORTAVEL, janela.menu.escolhido("densidade"))

    def test_a_pele_escolhida_sobrevive_ao_fechamento(self) -> None:
        primeira = self.janela()
        self._trocar(primeira, pele.FITA)
        primeira.close()

        segunda = self.janela()
        self.assertEqual(pele.FITA, segunda._pele_atual().nome)
        self.assertEqual(["Fita"], self._cromo(segunda))
        self.assertEqual(pele.FITA, segunda.menu.escolhido("aparencia"))

    def test_a_pele_sugere_a_densidade_e_a_escolha_explicita_ganha(self) -> None:
        """O criterio de aceite da S-232: a escolha sobrepoe a sugestao **e** sobrevive a troca.

        A fita sugere compacta porque e a pele que gasta altura com cromo. Quem nunca abriu o menu
        recebe a sugestao; quem escolheu confortavel continua confortavel tambem na fita.
        """
        janela = self.janela()
        self._trocar(janela, pele.FITA)
        self.assertEqual(pele.COMPACTA, janela._densidade_atual(), "a fita nao sugeriu compacta")

        janela.menu.escolher("densidade", pele.CONFORTAVEL)
        janela._comandos()["densidade"]()
        self.assertEqual(pele.CONFORTAVEL, janela._densidade_atual())

        self._trocar(janela, pele.CLASSICA)
        self._trocar(janela, pele.FITA)
        self.assertEqual(
            pele.CONFORTAVEL, janela._densidade_atual(), "a sugestao da pele desfez a escolha"
        )

    def test_o_cromo_escuro_da_pele_chega_a_folha_de_estilo(self) -> None:
        """A pele "Foco" e escura (S-224), e ate aqui esse `bool` nao saia de `ui/pele.py`.

        **Afirma o efeito e nao a chamada** (PR #25). A primeira versao deste teste punha um
        `mock` em `aplicar_tema` e conferia o `cromo_escuro` que ela recebeu -- o que continua
        verde no dia em que ela receber o argumento e nao fizer nada com ele.
        `tema.cromo_escuro_em_vigor()` existe para essa pergunta.
        """
        from chess_diagram_ocr.qt import tema

        janela = self.janela()
        self.assertFalse(tema.cromo_escuro_em_vigor(), "a classica nao e escura")

        self._trocar(janela, pele.FOCO)
        self.assertTrue(tema.cromo_escuro_em_vigor(), "a pele escura nao chegou ao tema")

        self._trocar(janela, pele.FITA)
        self.assertFalse(tema.cromo_escuro_em_vigor(), "a fita e clara: o escuro nao saiu")

    def test_a_variavel_de_ambiente_ganha_da_guardada(self) -> None:
        """`CVOFF_SKIN` existe para abrir o programa numa aparencia a partir de um roteiro."""
        self.estado.write_text('{"version": 6, "skin": "classica"}', encoding="utf-8")
        with mock.patch.dict("os.environ", {pele.PELE_ENV: pele.FITA}):
            janela = self.janela()
            self.assertEqual(pele.FITA, janela._pele_atual().nome)
        # E o efeito sobrevive a variavel: o cromo montado na abertura e o da fita.
        self.assertEqual(["Fita"], self._cromo(janela))

    def test_uma_pele_escrita_errada_no_disco_nao_impede_a_janela_de_abrir(self) -> None:
        """O contrato de degradacao: `pele.valida` nomeia a invalida no log e cai na classica."""
        self.estado.write_text('{"version": 6, "skin": "roxa"}', encoding="utf-8")
        self.assertEqual(pele.CLASSICA, self.janela()._pele_atual().nome)

    def test_o_conjunto_de_pecas_e_o_terceiro_eixo_e_e_trocavel(self) -> None:
        """Ate o corte ele era um controle da aba Configuracao, que esta janela nao tem (S-230)."""
        from chess_diagram_ocr.qt import tabuleiro as qt_tabuleiro
        from chess_diagram_ocr.ui import conjuntos

        self.addCleanup(qt_tabuleiro.definir_conjunto, conjuntos.PADRAO)
        janela = self.janela()
        self.assertEqual(conjuntos.PADRAO, janela.menu.escolhido("conjunto_de_pecas"))

        janela.menu.escolher("conjunto_de_pecas", conjuntos.TRACO)
        janela._comandos()["conjunto_de_pecas"]()
        self.assertEqual(conjuntos.TRACO, qt_tabuleiro.conjunto_em_vigor())
        self.assertEqual(conjuntos.TRACO, janela._estado.piece_set)

    def test_o_conjunto_escolhido_sobrevive_ao_fechamento(self) -> None:
        from chess_diagram_ocr.qt import tabuleiro as qt_tabuleiro
        from chess_diagram_ocr.ui import conjuntos

        self.addCleanup(qt_tabuleiro.definir_conjunto, conjuntos.PADRAO)
        primeira = self.janela()
        primeira.menu.escolher("conjunto_de_pecas", conjuntos.TRACO)
        primeira._comandos()["conjunto_de_pecas"]()
        primeira.close()

        qt_tabuleiro.definir_conjunto(conjuntos.PADRAO)
        segunda = self.janela()
        self.assertEqual(conjuntos.TRACO, qt_tabuleiro.conjunto_em_vigor())
        self.assertEqual(conjuntos.TRACO, segunda.menu.escolhido("conjunto_de_pecas"))

    def test_desistir_da_pasta_do_usuario_repoe_a_marca(self) -> None:
        """Um submenu marcado num conjunto que nao entrou em vigor e a mesma mentira de antes."""
        from chess_diagram_ocr.qt import janela as modulo
        from chess_diagram_ocr.qt import tabuleiro as qt_tabuleiro
        from chess_diagram_ocr.ui import conjuntos

        self.addCleanup(qt_tabuleiro.definir_conjunto, conjuntos.PADRAO)
        janela = self.janela()
        janela.menu.escolher("conjunto_de_pecas", conjuntos.PASTA)
        with mock.patch.object(modulo.QFileDialog, "getExistingDirectory", lambda *a, **k: ""):
            janela._comandos()["conjunto_de_pecas"]()
        self.assertEqual(conjuntos.PADRAO, janela.menu.escolhido("conjunto_de_pecas"))
        self.assertEqual(conjuntos.PADRAO, qt_tabuleiro.conjunto_em_vigor())

    def test_a_pasta_escolhida_entra_em_vigor_e_e_guardada(self) -> None:
        from chess_diagram_ocr.qt import janela as modulo
        from chess_diagram_ocr.qt import tabuleiro as qt_tabuleiro
        from chess_diagram_ocr.ui import conjuntos

        self.addCleanup(qt_tabuleiro.definir_conjunto, conjuntos.PADRAO)
        minhas = self.pasta / "minhas-pecas"
        minhas.mkdir()
        janela = self.janela()
        janela.menu.escolher("conjunto_de_pecas", conjuntos.PASTA)
        with mock.patch.object(modulo.QFileDialog, "getExistingDirectory", lambda *a, **k: str(minhas)):
            janela._comandos()["conjunto_de_pecas"]()
        self.assertEqual(conjuntos.PASTA, qt_tabuleiro.conjunto_em_vigor())
        self.assertEqual(str(minhas), janela._estado.piece_dir)
        self.assertEqual(minhas, qt_tabuleiro.pasta_do_conjunto())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DesfazerTests(unittest.TestCase):
    """Quem desfaz quando se aperta `Ctrl+Z`: o foco decide, e a regra e pura (S-243/S-506).

    **A declaracao de acoes da S-244 ja cobria o caso 1**, e e por isso que o defeito sobreviveu ao
    porte: com o cursor dentro do texto a tecla ia para o texto. O que faltava era o caso 2 -- foco
    em lugar nenhum dos dois, que e onde ele fica depois de qualquer clique num botao --, e ali a
    tecla ia direto para o tabuleiro.
    """

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)

    def janela(self) -> JanelaPrincipal:
        montada = JanelaPrincipal(
            servico=_ServicoFalso(),  # type: ignore[arg-type]
            csv_de_rotulos=self.pasta / "labels.csv",
            pasta_de_estudos=self.pasta,
            pasta_da_galeria=self.pasta,
            caminho_do_estado=self.pasta / "janela.json",
        )
        self.addCleanup(descartar, montada)
        montada.resize(1400, 900)
        return montada

    def test_os_tres_paineis_disputam_a_tecla(self) -> None:
        """Resultado, Texto e Sala, nessa ordem -- que e a de construcao e a que desempata."""
        from chess_diagram_ocr.ui import desfazivel

        janela = self.janela()
        disputam = janela._desfaziveis()
        self.assertEqual([janela.painel, janela.texto, janela.estudo], disputam)
        for painel in disputam:
            with self.subTest(painel=type(painel).__name__):
                self.assertIsInstance(painel, desfazivel.Desfazivel)

    def test_sem_edicao_nenhuma_a_tecla_diz_que_nao_ha_o_que_desfazer(self) -> None:
        janela = self.janela()
        recados: list[str] = []
        janela.rodape.mostrar = lambda texto, **_: recados.append(texto)  # type: ignore[assignment]
        with mock.patch.object(janela, "_foco", lambda: None):
            janela._comandos()["desfazer"]()
        self.assertEqual(["Não há nada para desfazer."], recados)

    def test_o_ultimo_editado_ganha_quando_o_foco_nao_esta_em_nenhum(self) -> None:
        """**O caso 2, e o defeito que este item conserta.**

        Digitar no texto e depois clicar num botao da barra deixa o foco fora dos dois
        desfaziveis. Antes daqui a tecla desfazia a ultima peca arrastada no tabuleiro.
        """
        janela = self.janela()
        janela.texto._edicao = 7
        janela.painel._edicao = 3
        with (
            mock.patch.object(janela, "_foco", lambda: None),
            mock.patch.object(janela.texto, "desfazer") as do_texto,
            mock.patch.object(janela.painel, "desfazer") as do_tabuleiro,
        ):
            janela._comandos()["desfazer"]()
        do_texto.assert_called_once_with()
        do_tabuleiro.assert_not_called()

    def test_o_foco_dentro_de_um_painel_ganha_do_ultimo_editado(self) -> None:
        """O caso 1: quem contem o widget em foco desfaz, mesmo tendo editado antes do outro."""
        janela = self.janela()
        janela.texto._edicao = 99
        janela.painel._edicao = 1
        with (
            mock.patch.object(janela, "_foco", lambda: janela.painel.tabuleiro),
            mock.patch.object(janela.texto, "desfazer") as do_texto,
            mock.patch.object(janela.painel, "desfazer") as do_tabuleiro,
        ):
            janela._comandos()["desfazer"]()
        do_tabuleiro.assert_called_once_with()
        do_texto.assert_not_called()

    def test_o_refazer_segue_o_mesmo_arbitro(self) -> None:
        janela = self.janela()
        janela.texto._edicao = 2
        with (
            mock.patch.object(janela, "_foco", lambda: None),
            mock.patch.object(janela.texto, "refazer") as do_texto,
        ):
            janela._comandos()["refazer"]()
        do_texto.assert_called_once_with()

    def test_o_foco_de_verdade_e_lido_da_aplicacao(self) -> None:
        """O controle dos testes acima: `_foco` responde o widget que o Qt diz estar em foco.

        **Sob `offscreen` so ha foco depois de `show` + `activateWindow` + `processEvents`**, e por
        isso os outros testes injetam o foco em vez de encena-lo: o que eles medem e o arbitro.
        """
        janela = self.janela()
        # A aba tem de estar a frente: `setFocus` num widget de aba escondida nao toma o foco, e o
        # Qt o entrega ao primeiro focavel da aba visivel.
        janela.abas.setCurrentWidget(janela.texto)
        janela.show()
        janela.activateWindow()
        janela.texto.editor.setFocus()
        self.app.processEvents()
        self.assertIs(janela.texto.editor, janela._foco())
        self.assertTrue(janela.texto.contem(janela._foco()))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
