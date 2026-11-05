"""O rodapé do segundo frontend (S-163/S-393/S-501).

**O que estes testes cobrem, e o que não.** A decisão -- severidade, expiração, as três
descrições, a ocupação -- é pura e já é afirmada em `tests/test_ui_rodape.py`. Ela agora mora em
`ui/estado_do_rodape.py` e os dois frontends a chamam, então repeti-la aqui mediria o mesmo código
duas vezes.

O que só existe deste lado é a ligação entre a decisão e os widgets do Qt, e nela há três coisas
que quebram calado:

1. **A mensagem tem de ceder espaço**, e não o livro e a página. No Tk isso é a ordem do `pack`;
   aqui é o esticamento, e trocá-lo empurraria para fora exatamente o que não pode sair.
2. **A altura não pode mudar** com o conteúdo, senão o layout acima do rodapé se move.
3. **A cor da mensagem tem de ser repintada na troca de pele** (S-393), senão um erro na tela
   fica na cor da pele anterior.
"""

from __future__ import annotations

import unittest

from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.ui import estado_do_rodape as estado
from chess_diagram_ocr.ui import tokens
from chess_diagram_ocr.ui.busy import BusyOperation, BusyRegistry

if TEM_PYQT:
    from PyQt6 import sip
    from PyQt6.QtCore import Qt

    from chess_diagram_ocr.qt import rodape, tema


def operacao(**campos: object) -> BusyOperation:
    """Uma operação do `BusyRegistry` com os campos que o teste quiser mexer.

    `feito`/`total` e não uma fração: é o que `BusyOperation` guarda desde a S-164, e `total=0`
    quer dizer "não há total conhecido" -- que é o caminho da barra indeterminada.
    """
    padrao: dict[str, object] = {
        "name": "Lendo a página",
        "loses_work": False,
        "cancellable": False,
        "detail": "",
        "feito": 0,
        "total": 0,
    }
    padrao.update(campos)
    return BusyOperation(**padrao)  # type: ignore[arg-type]


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class ZonasTests(unittest.TestCase):
    """As quatro zonas, e qual delas cede espaço."""

    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.rodape = rodape.RodapeDaJanela()
        self.addCleanup(self.rodape.deleteLater)

    def test_so_a_mensagem_estica(self) -> None:
        """**A ordem do `pack` da S-163, dita em Qt.**

        A mensagem leva 1 e as outras três levam 0: uma mensagem longa encolhe a si mesma em vez
        de empurrar para fora o livro e a página, que é o que a pessoa consulta o tempo todo. É a
        mesma lição que a S-154 mediu na lateral da Galeria.
        """
        linha = self.rodape.layout().itemAt(1).layout()
        esticamentos = {
            linha.itemAt(i).widget(): linha.stretch(i) for i in range(linha.count())
        }
        self.assertEqual(esticamentos[self.rodape._lbl_mensagem], 1)
        for widget in (
            self.rodape._lbl_documento,
            self.rodape._lbl_dispositivos,
            self.rodape._lbl_ocupacao,
        ):
            with self.subTest(widget=widget):
                self.assertEqual(esticamentos[widget], 0)

    def test_o_dispositivo_fica_a_esquerda_do_documento(self) -> None:
        """Quem fica mais perto da mensagem é quem cede espaço primeiro.

        Livro e página são consultados o tempo todo; o dispositivo se olha uma vez por sessão.
        """
        linha = self.rodape.layout().itemAt(1).layout()
        ordem = [linha.itemAt(i).widget() for i in range(linha.count())]
        self.assertLess(
            ordem.index(self.rodape._lbl_dispositivos), ordem.index(self.rodape._lbl_documento)
        )

    def test_a_altura_nao_muda_com_o_conteudo(self) -> None:
        """**Nada aparece nem desaparece**, e é por isso que a altura é fixa por construção.

        É o defeito 4 da S-163: o comprimento do texto movia o layout acima dele. Aqui a barra e
        o botão de cancelar ficam desabilitados em vez de escondidos, exatamente por isto.
        """
        vazio = self.rodape.sizeHint().height()
        self.rodape.mostrar("Uma mensagem bem longa " * 12)
        self.rodape.definir_documento("Um livro de nome comprido.pdf · p. 128 de 640")
        self.rodape.aplicar_ocupacao([operacao(cancellable=True, feito=1, total=2)])
        self.assertEqual(self.rodape.sizeHint().height(), vazio)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class MensagemTests(unittest.TestCase):
    """A zona de mensagem: severidade, cor e prazo."""

    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.rodape = rodape.RodapeDaJanela()
        self.addCleanup(self.rodape.deleteLater)

    def test_a_severidade_sai_da_mesma_tabela_dos_dois_frontends(self) -> None:
        """Copiar `MARCAS_DE_ERRO` daria uma janela dizendo "isto falhou" em vermelho e a outra
        dizendo o mesmo em cinza."""
        self.rodape.mostrar("Falha ao abrir o livro")
        self.assertEqual(self.rodape._severidade, estado.ERRO)
        self.rodape.mostrar("Dataset carregado: 3936 amostras.")
        self.assertEqual(self.rodape._severidade, estado.INFORMACAO)

    def test_a_cor_da_mensagem_e_a_do_papel(self) -> None:
        self.rodape.mostrar("Falha ao abrir o livro")
        self.assertIn(
            tema.cor_atual(estado.PAPEL_DE_TEXTO[estado.ERRO]), self.rodape._lbl_mensagem.styleSheet()
        )

    def test_o_erro_na_tela_e_repintado_na_troca_de_pele(self) -> None:
        """**O defeito da S-393.** A cor era resolvida na hora de escrever e nunca mais.

        Trocar de pele com um erro no rodapé deixava o texto na cor da pele anterior: preto de
        erro sobre o cromo escuro, a 1,30:1 -- abaixo dos 4,5:1 que a S-144 usa como régua.
        """
        self.rodape.mostrar("Falha ao abrir o livro")
        claro = self.rodape._lbl_mensagem.styleSheet()

        tema.aplicar_tema(self.app, cromo_escuro=True)
        self.addCleanup(tema.aplicar_tema, self.app)
        escuro = self.rodape._lbl_mensagem.styleSheet()
        self.assertNotEqual(claro, escuro, "o erro na tela ficou na cor da pele anterior")
        self.assertIn(tokens.NO_CROMO_ESCURO[tokens.PROBLEMA_TEXTO], escuro)

    def test_rodape_sem_mensagem_nao_pinta_nada(self) -> None:
        """Sem severidade não há cor a repintar, e pintar assim mesmo escolheria uma por acaso."""
        tema.repintar()
        self.assertEqual(self.rodape._lbl_mensagem.styleSheet(), "")

    def test_a_informacao_expira_e_o_erro_nao(self) -> None:
        """`EXPIRACAO_MS` diz que erro não expira, e essa é uma decisão do projeto.

        É por ela que o `QStatusBar` não serve: o `showMessage(texto, ms)` dele devolveria a
        expiração para o ponto de chamada, onde alguém a esqueceria.
        """
        self.rodape.mostrar("Dataset carregado: 3936 amostras.")
        self.assertTrue(self.rodape._expiracao.isActive())
        self.rodape.mostrar("Falha ao abrir o livro")
        self.assertFalse(self.rodape._expiracao.isActive())

    def test_expirar_limpa_a_mensagem_e_a_severidade(self) -> None:
        self.rodape.mostrar("Dataset carregado: 3936 amostras.")
        self.rodape._expirar()
        self.assertEqual(self.rodape.mensagem(), "")
        self.assertEqual(self.rodape._severidade, "")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class OcupacaoTests(unittest.TestCase):
    """A zona da operação em curso, e a barra que não pode parecer travada."""

    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.rodape = rodape.RodapeDaJanela()
        self.addCleanup(self.rodape.deleteLater)

    def test_sem_operacao_a_barra_para_e_o_cancelar_desliga(self) -> None:
        self.rodape.aplicar_ocupacao([])
        self.assertEqual(self.rodape._modo_da_barra, estado.PARADO)
        self.assertFalse(self.rodape._btn_cancelar.isEnabled())

    def test_a_operacao_sem_progresso_gira_a_barra(self) -> None:
        """`(0, 0)` é como o Qt diz "indeterminada": a animação é consequência da faixa."""
        self.rodape.aplicar_ocupacao([operacao()])
        self.assertEqual(self.rodape._modo_da_barra, estado.INDETERMINADO)
        self.assertEqual((self.rodape._barra.minimum(), self.rodape._barra.maximum()), (0, 0))

    def test_a_operacao_com_progresso_anda(self) -> None:
        self.rodape.aplicar_ocupacao([operacao(feito=1, total=2)])
        self.assertEqual(self.rodape._modo_da_barra, estado.DETERMINADO)
        self.assertEqual(self.rodape._barra.value(), 50)

    def test_a_faixa_nao_e_reescrita_quando_o_modo_nao_muda(self) -> None:
        """**Reescrevê-la a cada tique reinicia a animação e ela parece travada.**

        É o mesmo sintoma do `start()` repetido no Tk, com outra causa: lá a animação é do
        widget, aqui é da faixa. O valor da determinada, ao contrário, é escrito em todo tique.
        """
        self.rodape.aplicar_ocupacao([operacao()])
        faixas: list[tuple[int, int]] = []
        original = self.rodape._barra.setRange
        self.rodape._barra.setRange = lambda a, b: faixas.append((a, b))  # type: ignore[method-assign]
        self.addCleanup(setattr, self.rodape._barra, "setRange", original)
        for _ in range(4):
            self.rodape.aplicar_ocupacao([operacao()])
        self.assertEqual(faixas, [], "a faixa foi reescrita com o modo parado")

    def test_a_operacao_cancelavel_liga_o_botao(self) -> None:
        self.rodape.aplicar_ocupacao([operacao(cancellable=True)])
        self.assertTrue(self.rodape._btn_cancelar.isEnabled())

    def test_o_botao_chama_quem_foi_dado(self) -> None:
        chamadas: list[str] = []
        rod = rodape.RodapeDaJanela(cancelar=lambda: chamadas.append("cancelou"))
        self.addCleanup(rod.deleteLater)
        rod.aplicar_ocupacao([operacao(cancellable=True)])
        rod._btn_cancelar.click()
        self.assertEqual(chamadas, ["cancelou"])

    def test_sem_cancelador_o_clique_nao_levanta(self) -> None:
        self.rodape.aplicar_ocupacao([operacao(cancellable=True)])
        self.rodape._btn_cancelar.click()


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class AcompanhamentoTests(unittest.TestCase):
    """O rodapé é quem pergunta, e não as sete operações que avisam (S-112)."""

    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.rodape = rodape.RodapeDaJanela()
        self.addCleanup(self.rodape.deleteLater)

    def test_acompanhar_le_o_registro_agora_e_reagenda(self) -> None:
        leituras: list[int] = []

        def operacoes() -> list[BusyOperation]:
            leituras.append(1)
            return [operacao()]

        self.rodape.acompanhar(operacoes, intervalo_ms=10_000)
        self.assertEqual(len(leituras), 1, "não leu na primeira chamada")
        self.assertTrue(self.rodape._acompanhamento.isActive())

    def test_o_dispositivo_entra_no_mesmo_tique(self) -> None:
        """Nenhum dos dois modelos avisa quando muda, então os dois são perguntados juntos."""
        self.rodape.acompanhar(
            list,
            dispositivos=lambda: estado.Dispositivos(pecas="cuda", caracteres="cpu"),
            intervalo_ms=10_000,
        )
        self.assertIn("cuda", self.rodape.dispositivos())

    def test_registrar_acende_a_barra_sem_esperar_o_relogio(self) -> None:
        """**As quatro zonas do rodapé mudam no mesmo turno** (F9-C4).

        O relógio de `acompanhar` é de 400 ms e a zona de mensagem é escrita por sinal, no
        instante em que a operação começa. Nesses 400 ms o rodapé contradizia a si mesmo: em
        `benchmarks/reports/ui/c4/c4_claro_1280x800_dataset.png` -- 1 das 36 capturas -- ele diz
        "Lendo o dataset…" com a **barra escondida** e o **`Cancelar` desabilitado**, que é a
        mesma frase com que o defeito bloqueante nº 2 do ciclo 3 reprovou o ciclo 2.

        O relógio é posto em 10 s de propósito: se ele fosse quem acende a barra, este teste
        falharia -- é a assinatura, e não o tique, que tem de ser suficiente.
        """
        registro = BusyRegistry()
        self.rodape.acompanhar(registro.running, intervalo_ms=10_000)
        self.rodape.assinar_ocupacao(registro.observe, registro.running)
        self.assertFalse(self.rodape._barra.isVisible(), "a barra apareceu sem operação")

        ficha = registro.register("leitura do dataset", loses_work=False, cancellable=True, cancel=lambda: None)
        self.assertEqual(self.rodape._modo_da_barra, estado.INDETERMINADO)
        self.assertTrue(self.rodape._btn_cancelar.isEnabled(), "o Cancelar ficou cinzento com operação viva")

        ficha.release()
        self.assertEqual(self.rodape._modo_da_barra, estado.PARADO)
        self.assertFalse(self.rodape._btn_cancelar.isEnabled())

    def test_soltar_depois_de_o_rodape_morrer_nao_derruba_o_processo(self) -> None:
        """**O registro vive mais que o rodapé, e o Qt não perdoa isso** (F9-C4).

        Uma leitura que termina depois de a janela ser destruída chama `release()`, que avisa os
        observadores. Assinar `self.ocupacao_mudou.emit` guarda o ponteiro C++ do emissor, e emitir
        por ele depois do destrutor **não levanta `RuntimeError` -- derruba o processo**: a suíte
        do tronco inteira parou com `Windows fatal exception: access violation` em
        `busy._avisar -> marcas._soltar -> test_box_drop.setUp`. O `try` de `_avisar` não pega
        isso, porque não é exceção de Python.

        **O que este teste prende é a sequência**, não a queda: isolado, o mesmo caminho sem guarda
        pode degradar para um `AttributeError` que o `try` engole -- conferi. O que ele garante é
        que soltar uma ficha depois de o rodapé morrer é um caminho **exercitado**, e que o
        registro fica consistente; quem impede a queda é a guarda de `assinar_ocupacao`, e a
        evidência dela é a suíte do tronco inteira passando.
        """
        registro = BusyRegistry()
        rod = rodape.RodapeDaJanela()
        rod.acompanhar(registro.running, avisos=registro.observe, intervalo_ms=10_000)
        ficha = registro.register("leitura do dataset", loses_work=False)

        sip.delete(rod)  # o objeto C++ morre; o embrulho de Python continua
        ficha.release()  # a resposta atrasada chega ao registro que sobreviveu

        self.assertEqual(registro.running(), [])

@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DocumentoTests(unittest.TestCase):
    """A zona do livro e da página."""

    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.rodape = rodape.RodapeDaJanela()
        self.addCleanup(self.rodape.deleteLater)

    def test_tudo_salvo_fala_em_verde(self) -> None:
        self.rodape.definir_documento("Aagaard.pdf", True)
        salvo = self.rodape._lbl_documento.styleSheet()
        self.rodape.definir_documento("Aagaard.pdf", False)
        self.assertNotEqual(salvo, self.rodape._lbl_documento.styleSheet())
        self.assertIn(tema.cor_atual(estado.papel_do_documento(True)), salvo)

    def test_os_dois_parametros_sao_posicionais(self) -> None:
        """Para o método **ser** o callback que o painel espera, sem um `lambda` no meio."""
        self.rodape.definir_documento("Aagaard.pdf", True)
        self.assertEqual(self.rodape.documento(), "Aagaard.pdf")

    FRASE = "1937 Kemeri.pdf · p. 121 de 289 · nenhum diagrama nesta página"
    """A frase das 36 capturas. 62 caracteres, e o rodapé desenhava 23 deles."""

    def _largura(self, largura: int) -> None:
        """Põe a faixa naquela largura **e força o leiaute a correr**.

        `show()` e não só `resize()`, e a diferença foi medida: um `QWidget` escondido guarda o
        `QResizeEvent` em `WA_PendingResizeEvent` e só o entrega quando aparece -- então
        `RotuloElidido.resizeEvent` nunca corria, e o rótulo respondia com a elisão da largura de
        construção. O teste mediria a ausência de leiaute, e não a régua. É a mesma razão de o
        instrumento do crítico abrir a janela.
        """
        self.rodape.resize(largura, self.rodape.sizeHint().height())
        self.rodape.show()
        leiaute = self.rodape.layout()
        if leiaute is not None:
            leiaute.activate()
        self.app.processEvents()

    def _elididos(self, largura: int) -> list[tuple[str, str]]:
        """`(inteiro, desenhado)` de cada rótulo elidido, com a faixa naquela largura.

        **É o portão do §4.1 do F9-C7**, e a régua é a que o crítico prescreveu: comparar
        `texto_inteiro` com `text()` e somar a folga da barra. Um teste que só olhasse o rótulo
        não veria o item -- elidir é legítimo quando não há espaço; o defeito é elidir **com
        1534 px livres na mesma faixa**.
        """
        from PyQt6.QtWidgets import QLabel

        self._largura(largura)
        return [
            (rotulo.texto_inteiro, rotulo.text())
            for rotulo in self.rodape.findChildren(QLabel)
            if getattr(rotulo, "texto_inteiro", rotulo.text()) != rotulo.text()
        ]

    def _folga(self, largura: int) -> int:
        """Quantos pixels da faixa nenhum rótulo está usando."""
        from PyQt6.QtWidgets import QLabel

        self._largura(largura)
        tinta = sum(
            rotulo.fontMetrics().horizontalAdvance(rotulo.text())
            for rotulo in self.rodape.findChildren(QLabel)
            if rotulo.isVisibleTo(self.rodape)
        )
        return largura - tinta

    def test_nenhum_rotulo_elide_enquanto_ha_folga_na_mesma_faixa(self) -> None:
        """**Carta §3.3, primeiro item**: texto com reticências onde caberia (F9-C7, §4.1).

        Medido pelo crítico nas três larguras: `'1937 Kemeri…esta página'` no lugar da frase
        inteira -- **39 de 62 caracteres perdidos** -- com **1534 px livres** a 1920, 980 a 1366
        e 894 a 1280. A causa não era a elisão, que é um conserto legítimo do ciclo 1; era o
        **teto de 130 px** que ela herdou da barra do visor, onde ele evita refluxo e onde o
        rodapé não tem nenhum.
        """
        self.rodape.definir_documento(self.FRASE, False)
        for largura in (1920, 1366, 1280):
            with self.subTest(largura=largura):
                folga = self._folga(largura)
                elididos = self._elididos(largura)
                self.assertEqual(
                    [],
                    elididos,
                    f"rotulo elidido com {folga} px livres na mesma faixa: "
                    + "; ".join(f"{i!r} -> {d!r}" for i, d in elididos),
                )
                self.assertGreater(folga, 0, "a faixa encheu: aqui elidir seria legitimo")

    def test_sem_folga_ele_volta_a_elidir(self) -> None:
        """O outro lado, e é o que impede o conserto de virar transbordo.

        Um nome de 149 caracteres com 320 px para ele **tem** de ser cortado -- a alternativa é
        empurrar as outras zonas para fora. O que este par de testes cobra é que a reticência
        apareça por falta de espaço, e nunca por um teto herdado.

        Os 320 px são **do nome**, somados ao mínimo da faixa: desde que o botão das mensagens
        guarda o seu mínimo (OCR_UI ciclo 2, fase 5), uma faixa inteira de 320 px -- que a
        janela, de 1248 px no mínimo, nunca tem -- deixava ao nome menos que uma reticência.
        """
        longo = (
            "Gaprindashvili, Paata - Imagination in Chess. How To Think Creatively And Avoid "
            "Foolish Mistakes (Bastford, 2005) 2p 145 · p. 121 de 289"
        )
        self.rodape.definir_documento(longo, False)
        elididos = self._elididos(self.rodape.minimumSizeHint().width() + 320)
        self.assertEqual(1, len(elididos), "320 px couberam o nome de 149 caracteres?")
        self.assertIn("\u2026", elididos[0][1])

    def test_o_rotulo_do_documento_continua_sem_decidir_a_largura_minima(self) -> None:
        """**O defeito do ciclo 1 não pode voltar** (crítica do ciclo 1, defeito nº 2).

        Pedir o texto inteiro é `sizeHint`; a largura mínima é `minimumSizeHint`, e ela continua
        zero. Sem esta separação, um nome de 149 caracteres voltaria a subir o
        `minimumSizeHint` da janela de 1243 para 1513 px -- o nome de um arquivo decidindo qual é
        a menor tela em que o programa cabe.
        """
        longo = "x" * 149
        self.rodape.definir_documento(longo, False)
        self.app.processEvents()
        rotulo = self.rodape._lbl_documento
        self.assertEqual(0, rotulo.minimumSizeHint().width())
        self.assertGreater(rotulo.sizeHint().width(), 130, "o teto da barra voltou ao rodape")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class ZonaDaMensagemTests(unittest.TestCase):
    """A zona que cede largura em vez de exigi-la (S-552, quinta rodada).

    **O defeito era de janela e a causa era daqui.** `QLabel.minimumSizeHint` de um rótulo sem
    quebra de linha é a largura do texto inteiro; ele subia pelo leiaute do rodapé e virava o piso
    da janela -- medido a 1024x768, uma frase de 600 caracteres punha a janela em 3457 px de
    mínimo, e o erro de modelo ausente tem justamente esse tamanho.

    Aqui se afirma o widget solto, que é onde a regra mora; o efeito na janela é
    `tests/test_qt_tamanho_da_janela.py::RodapeNaoEPisoDeJanelaTests`.
    """

    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.zona = rodape.ZonaDaMensagem()
        # `descartar` e nao `deleteLater`: o rodape registra repintura de tema, e um widget morto
        # que segue registrado e o defeito que `qt_app.descartar` documenta -- ele aparece no
        # vizinho, e nao em quem esqueceu.
        self.addCleanup(descartar, self.zona)
        # **Mostrada, mesmo sob `offscreen`.** Um widget que nunca foi criado tem `crect` mas não
        # recebe `QResizeEvent`: `resize()` muda o número e a elisão não é refeita. Medir a régua
        # num widget nesse estado seria medir o silêncio do Qt, como em `qt/dica.py`.
        self.zona.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.zona.show()
        self.zona.resize(200, 20)
        self.app.processEvents()

    def test_o_minimo_nao_cresce_com_o_texto(self) -> None:
        """**A guarda do bloqueio, no widget.** Era 614 px para 120 caracteres e 10014 para 2000."""
        vazio = self.zona.minimumSizeHint().width()
        self.assertEqual(estado.LARGURA_MINIMA_DA_MENSAGEM, vazio)
        for tamanho in (120, 600, 2000):
            with self.subTest(caracteres=tamanho):
                self.zona.definir_frase("erro " * tamanho)
                self.assertEqual(vazio, self.zona.minimumSizeHint().width())
                self.assertEqual(vazio, self.zona.sizeHint().width())
                self.assertEqual(vazio, self.zona.minimumWidth())

    def test_a_altura_continua_sendo_a_de_uma_linha(self) -> None:
        """O teto é de largura, e só. Trocar um piso de largura por um de altura -- que é o que
        `setWordWrap` faria -- não conserta um rodapé cuja altura é fixa por construção.

        Comparadas duas frases, e não uma contra a zona vazia: um `QLabel` sem texto responde a
        altura da fonte e um com texto responde a do texto desenhado -- 14 contra 12 px aqui --, e
        essa diferença é do Qt e não do tamanho da frase."""
        self.zona.definir_frase("Pronto.")
        curta = self.zona.sizeHint().height()
        self.zona.definir_frase("erro " * 2000)
        self.assertEqual(curta, self.zona.sizeHint().height())
        self.assertEqual(curta, self.zona.minimumSizeHint().height())

    def test_a_frase_longa_e_elidida_pelo_fim_e_guarda_o_comeco(self) -> None:
        """Numa frase de erro o começo é o que a classifica -- é dele que sai a severidade."""
        frase = "Não foi possível carregar o modelo de peças: " + "detalhe " * 60
        self.zona.definir_frase(frase)
        self.assertEqual(frase, self.zona.frase(), "a frase inteira se perdeu")
        self.assertNotEqual(frase, self.zona.text(), "a frase longa não foi elidida")
        # O que está na tela é um **prefixo** da frase mais a reticência: é isso que "guarda o
        # começo" quer dizer, e é o que distingue `ElideRight` de `ElideMiddle` e `ElideLeft`.
        self.assertTrue(
            frase.startswith(self.zona.text().rstrip("…")),
            f"a elisão não guardou o começo: {self.zona.text()!r}",
        )
        self.assertIn("Não foi poss", self.zona.text())
        self.assertLessEqual(
            self.zona.fontMetrics().horizontalAdvance(self.zona.text()), self.zona.width()
        )

    def test_a_frase_inteira_vai_para_a_dica_e_a_curta_nao_deixa_dica(self) -> None:
        """Elidir sem a dica seria esconder a instrução em vez de encurtá-la; e uma dica que
        repete o que já está na tela é ruído -- é o critério de `dica_em` para texto vazio."""
        frase = "Não foi possível carregar o modelo: " + "detalhe " * 60
        self.zona.definir_frase(frase)
        self.assertEqual(frase, self.zona.toolTip())
        self.zona.definir_frase("Pronto.")
        self.assertEqual("Pronto.", self.zona.text())
        self.assertEqual("", self.zona.toolTip())

    def test_alargada_a_zona_mostra_o_que_passou_a_caber(self) -> None:
        """A elisão é refeita no `resizeEvent`: ela é função da largura de agora, e não da de
        quando a frase chegou."""
        frase = "Não foi possível carregar o modelo de peças do disco."
        self.zona.resize(120, 20)
        self.app.processEvents()
        self.zona.definir_frase(frase)
        estreita = self.zona.text()
        self.zona.resize(900, 20)
        self.app.processEvents()
        self.assertNotEqual(estreita, self.zona.text())
        self.assertEqual(frase, self.zona.text())
        self.assertEqual("", self.zona.toolTip(), "coube inteira e a dica ficou")

    def test_o_rodape_devolve_a_frase_inteira_e_nao_o_que_coube(self) -> None:
        """`mensagem()` é o que o roteiro headless do `CONTRIBUTING.md` lê: se ele lesse a tela,
        passaria a afirmar a largura do rodapé em vez do que o programa disse."""
        faixa = rodape.RodapeDaJanela()
        self.addCleanup(descartar, faixa)
        faixa.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        faixa.show()
        faixa.resize(300, 30)
        self.app.processEvents()
        # Sem espaço no fim: `compor` apara a frase, e o que o rodapé guarda é a aparada.
        frase = ("Não foi possível ler a página 21: " + "detalhe " * 60).strip()
        faixa.mostrar(frase)
        self.assertEqual(frase, faixa.mensagem())
        self.assertNotEqual(frase, faixa._lbl_mensagem.text())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
