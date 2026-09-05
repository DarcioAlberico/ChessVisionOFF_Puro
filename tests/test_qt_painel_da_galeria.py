"""A aba Galeria do segundo frontend (S-67/S-120/S-154/S-503).

**O que estes testes cobrem, e o que não.** Navegação, anotação, casamento com a base e o que pode
ser sobrescrito são do `GalleryModel`, e já são afirmados em `tests/test_gallery_model.py`. As
medidas, o tri-estado e a contabilidade do lote são de `ui/galeria_declarada.py`, e são puros.
Nada disso é remedido aqui.

O que só existe deste lado são as cinco coisas em que o Qt difere do Tk e que quebram calado:

1. **As três threads longas falam por sinal**, e não por `self.after(0, ...)`.
2. **`setChecked` dispara mesmo quando o valor não muda**, então redesenhar a tela grava por cima
   do que ela acabou de ler -- é a razão de `_montando` existir e de este arquivo medi-lo.
3. **`editingFinished` é `<FocusOut>` e `<Return>` de uma vez**: um só sinal onde o outro
   frontend amarra dois eventos por campo.
4. **A pergunta destrutiva precisa de `setDefaultButton`**: num `QMessageBox` o padrão é OK, e um
   `Enter` de reflexo apagaria meia hora de digitação.
5. **A legenda é somente-leitura de verdade** -- e continua selecionável, que é o que o Tk só
   consegue filtrando `<Key>` tecla a tecla.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.gallery_scan import GalleryIndex
from chess_diagram_ocr.ui import galeria_declarada

if TEM_PYQT:
    from PyQt6.QtWidgets import QMessageBox

    from chess_diagram_ocr.qt import painel_da_galeria as qt_galeria


class _ServicoFalso:
    """O serviço que a varredura empresta. Não é chamado por nenhum teste deste arquivo."""

    def model_session(self, _caminho: Path) -> None:  # pragma: no cover - nunca varre de verdade
        return None


class DeclaracaoTests(unittest.TestCase):
    """A decisão é a mesma dos dois lados, e nenhum dos dois a reescreve."""

    def test_o_modulo_puro_nao_carrega_tkinter_nem_imagetk(self) -> None:
        """O painel de Tk que este substituiu importava `tkinter` **e** `PIL.ImageTk` na primeira
        linha; o módulo puro que sobrou dele não pode voltar a importar nenhum dos dois."""
        import ast

        arvore = ast.parse(Path(galeria_declarada.__file__).read_text(encoding="utf-8"))
        nomes = {no.names[0].name.split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.Import)}
        nomes |= {(no.module or "").split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom)}
        self.assertNotIn("tkinter", nomes)
        self.assertNotIn("PIL", nomes)

    def test_o_resumo_do_lote_distingue_as_quatro_situacoes(self) -> None:
        """É a única linha que alguém lê depois de deixar o acervo varrendo por três horas.

        Puro, e afirmado aqui porque foi a S-503 que o extraiu: "pulado" é trabalho poupado,
        "parcial" é trabalho a continuar, "com erro" é trabalho perdido, e "sem varrer" é o que o
        cancelamento deixou. Um contador único diria o número certo e nenhuma das quatro coisas.
        """
        resultados = [
            galeria_declarada.LivroVarrido(Path("a.pdf"), indice=GalleryIndex()),
            galeria_declarada.LivroVarrido(Path("b.pdf"), pulado="12 diagrama(s), índice completo"),
            galeria_declarada.LivroVarrido(Path("c.pdf"), erro=ValueError("pdf corrompido")),
        ]
        frase = galeria_declarada.resumo_do_lote(resultados, pedidos=5)
        self.assertIn("1 livro(s) varrido(s)", frase)
        self.assertIn("1 pulado(s) por índice já completo", frase)
        self.assertIn("1 com erro", frase)
        self.assertIn("cancelada com 2 livro(s) sem varrer", frase)


def montar_painel(caso: unittest.TestCase, pasta: Path, **kwargs: object) -> qt_galeria.PainelDaGaleria:
    """A aba montada e descartada com o teste. **Função, e não método de uma classe-base**: herdar
    de uma `TestCase` para reaproveitar a montagem faria a suíte rodar os testes dela outra vez."""
    app = aplicacao()
    montado = qt_galeria.PainelDaGaleria(
        service=_ServicoFalso(),
        pdf_path=lambda: None,
        model_path=lambda: pasta / "modelo.pt",
        max_boards=lambda: 4,
        **kwargs,  # type: ignore[arg-type]
    )
    caso.addCleanup(descartar, montado)
    montado.show()
    app.processEvents()
    return montado


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PainelTests(unittest.TestCase):
    """A aba montada, sem livro varrido e com um índice de mentira."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)

    def painel(self, **kwargs: object) -> qt_galeria.PainelDaGaleria:
        return montar_painel(self, self.pasta, **kwargs)

    def test_o_estado_vazio_diz_o_que_falta_fazer(self) -> None:
        painel = self.painel()
        self.assertEqual(painel.recorte.text(), "varra o livro para ver os diagramas")
        self.assertFalse(painel.btn_limpar.isEnabled())
        self.assertFalse(painel.btn_candidatas.isEnabled())
        self.assertFalse(painel.btn_desfazer.isEnabled())

    def test_a_lateral_reserva_a_largura_medida(self) -> None:
        """Reservar a largura da lateral primeiro é o item da S-154: com o centro tomando tudo,
        os controles que gravam a procedência ficavam com o que sobrasse -- e não sobrava."""
        painel = self.painel()
        lateral = painel.campos_de_header["White"].parentWidget()
        assert lateral is not None
        self.assertEqual(lateral.width(), galeria_declarada.LARGURA_DA_LATERAL)

    def test_o_recorte_tem_o_lado_declarado(self) -> None:
        """Fixo: a galeria é para percorrer, e um tamanho que muda faria a imagem pular sob o
        ponteiro a cada avanço."""
        painel = self.painel()
        self.assertEqual(painel.recorte.width(), galeria_declarada.BOARD_VIEW_SIZE)
        self.assertEqual(painel.recorte.height(), galeria_declarada.BOARD_VIEW_SIZE)

    def test_a_legenda_e_de_leitura_e_continua_selecionavel(self) -> None:
        """`state=DISABLED` do Tk recusaria a seleção junto e pintaria de cinza -- é por isso que
        o outro frontend filtra `<Key>` tecla a tecla."""
        from PyQt6.QtCore import Qt

        painel = self.painel()
        self.assertTrue(painel.legenda.isReadOnly())
        self.assertTrue(
            painel.legenda.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
        )

    def test_os_quatro_botoes_de_navegacao_atendem_as_acoes_da_aba(self) -> None:
        painel = self.painel()
        self.assertEqual(painel.acoes_proprias(), galeria_declarada.ACOES_PROPRIAS)
        for acao in galeria_declarada.ACOES_PROPRIAS:
            with self.subTest(acao=acao):
                self.assertIsNotNone(painel.atender(acao))
        self.assertIsNone(painel.atender("salvar"))

    def test_com_o_cursor_num_campo_a_aba_cede_a_tecla(self) -> None:
        """Esta aba tem o campo do lance, os oito de header e a legenda: ali `←` é do campo."""
        from PyQt6.QtWidgets import QApplication

        painel = self.painel()
        painel.activateWindow()
        painel.campo_lance.setFocus()
        self.app.processEvents()
        self.assertIs(QApplication.focusWidget(), painel.campo_lance, "o foco não foi para o campo")
        self.assertEqual(painel.acoes_proprias(), frozenset())

    def test_sem_diagrama_os_gestos_viram_frase_e_nao_excecao(self) -> None:
        painel = self.painel()
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.limpar_headers()
        painel.copiar_para_todos()
        painel.copiar_legenda()
        painel.copiar_link()
        self.assertEqual(
            vistos,
            [
                "Este diagrama não tem header declarado; não há o que limpar.",
                "Nada a copiar: nenhum header preenchido neste diagrama.",
                "Este diagrama não tem legenda para copiar.",
            ],
        )

    def test_varrer_sem_livro_nenhum_avisa_no_rodape(self) -> None:
        """Pré-condição vira frase de rodapé, e não caixa modal (S-164)."""
        from chess_diagram_ocr.ui.escopo_da_varredura import PASTA, ScanScope

        painel = self.painel(perguntar_escopo_de_varredura=lambda _aberto: ScanScope(PASTA, ()))
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.varrer()
        self.assertEqual(len(vistos), 1)
        self.assertIn("Nenhum livro para varrer", vistos[0])

    def test_desistir_do_dialogo_de_escopo_nao_e_evento(self) -> None:
        """Nem rodapé, nem log: cancelar não é evento."""
        painel = self.painel(perguntar_escopo_de_varredura=lambda _aberto: None)
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.varrer()
        self.assertEqual(vistos, [])

    def test_buscar_sem_livro_varrido_avisa_no_rodape(self) -> None:
        painel = self.painel()
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.buscar_por_nome()
        painel.buscar_por_posicao()
        self.assertEqual(
            vistos,
            [
                "Varra o livro antes: a busca usa as legendas dos diagramas.",
                "Varra o livro antes: a busca usa as posições dos diagramas.",
            ],
        )


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class AnotacaoTests(unittest.TestCase):
    """A aba com um livro varrido de mentira: os campos gravam, e redesenhar não grava."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)
        self.livro = self.pasta / "livro.pdf"
        self.livro.write_bytes(b"%PDF-1.4")

    def painel(self) -> qt_galeria.PainelDaGaleria:
        from chess_diagram_ocr.gallery_scan import GalleryEntry, save_index

        indice = GalleryIndex(
            source_pdf=str(self.livro),
            entries=[
                GalleryEntry(
                    page_index=pagina,
                    diagram_index=0,
                    placement="8/8/8/8/8/8/8/K6k",
                    side_to_move="w",
                    image_path="",
                    caption=f"legenda da página {pagina}",
                )
                for pagina in (2, 5)
            ],
            complete=True,
        )
        save_index(self.livro, indice, directory=self.pasta)
        montado = qt_galeria.PainelDaGaleria(
            service=_ServicoFalso(),
            pdf_path=lambda: self.livro,
            model_path=lambda: self.pasta / "modelo.pt",
            max_boards=lambda: 4,
            # **Sem isto o teste grava em `data/gallery/` de verdade.** É o defeito que o
            # docstring de `GalleryModel.gallery_dir` já nomeia, e o painel do Qt passou a aceitar
            # o diretório justamente para não repeti-lo: `save_index`, `load_index` e
            # `GalleryModel.save` resolvem o padrão na definição, e são três caminhos de escrita.
            pasta_da_galeria=self.pasta,
        )
        self.addCleanup(descartar, montado)
        montado.show()
        self.app.processEvents()
        montado.load_pdf(self.livro, request_page=False)
        return montado

    def test_o_livro_varrido_aparece_com_a_legenda(self) -> None:
        painel = self.painel()
        self.assertEqual(len(painel.model), 2)
        self.assertEqual(painel.caption(), "legenda da página 2")

    def test_navegar_troca_o_diagrama_e_pede_a_pagina(self) -> None:
        painel = self.painel()
        pedidas: list[int] = []
        painel.pediu_pagina.connect(pedidas.append)
        painel.atender("proximo_diagrama")()
        self.assertEqual(painel.caption(), "legenda da página 5")
        self.assertEqual(pedidas, [5])

    def test_redesenhar_nao_grava_por_cima_do_que_leu(self) -> None:
        """**`setChecked` dispara mesmo quando o valor não muda.**

        Sem a guarda `_montando`, `refresh` marcaria o rádio de lado, o sinal chamaria
        `_gravar_lado`, e a anotação passaria a declarar um lado que ninguém escolheu -- gravado
        no arquivo do livro, e indistinguível de uma escolha real depois.
        """
        painel = self.painel()
        self.assertIsNone(painel.model.current_annotation.side_to_move)
        painel.refresh(request_page=False)
        self.assertIsNone(
            painel.model.current_annotation.side_to_move,
            "redesenhar declarou um lado que ninguém escolheu",
        )
        self.assertIsNone(painel.model.current_annotation.lichess_link)

    def test_escolher_o_lado_grava_de_verdade(self) -> None:
        painel = self.painel()
        for botao in painel.lado.buttons():
            if botao.property("valor") == "b":
                botao.click()
        self.assertEqual(painel.model.current_annotation.side_to_move, "b")

    def test_o_lance_grava_ao_terminar_a_edicao(self) -> None:
        """`editingFinished` é `<FocusOut>` e `<Return>` de uma vez."""
        painel = self.painel()
        painel.campo_lance.setText("24")
        painel.campo_lance.editingFinished.emit()
        self.assertEqual(painel.model.current_annotation.move_number, 24)

    def test_lance_invalido_vira_frase_e_nao_caixa(self) -> None:
        """Digitar e apagar é normal, e um diálogo por tecla errada tornaria a galeria
        insuportável."""
        painel = self.painel()
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.campo_lance.setText("vinte")
        painel.campo_lance.editingFinished.emit()
        self.assertIsNone(painel.model.current_annotation.move_number)
        self.assertTrue(any("Lance inválido" in frase for frase in vistos))

    def test_lance_em_branco_apaga_a_declaracao(self) -> None:
        """Não declarar e declarar vazio são coisas diferentes, e só a primeira deixa a
        exportação decidir."""
        painel = self.painel()
        painel.campo_lance.setText("24")
        painel.campo_lance.editingFinished.emit()
        painel.campo_lance.setText("")
        painel.campo_lance.editingFinished.emit()
        self.assertIsNone(painel.model.current_annotation.move_number)

    def test_o_header_grava_e_acende_o_limpar(self) -> None:
        painel = self.painel()
        painel.campos_de_header["White"].setText("Coull")
        painel.campos_de_header["White"].editingFinished.emit()
        self.assertEqual(painel.model.current_annotation.headers["White"], "Coull")
        painel.refresh(request_page=False)
        self.assertTrue(painel.btn_limpar.isEnabled())

    def test_a_pergunta_destrutiva_tem_cancelar_como_padrao(self) -> None:
        """Num `QMessageBox` o padrão é OK, e um `Enter` de reflexo apagaria meia hora de
        digitação. É o `default=messagebox.CANCEL` do outro lado."""
        painel = self.painel()
        painel.campos_de_header["White"].setText("Coull")
        painel.campos_de_header["White"].editingFinished.emit()

        vistas: list[QMessageBox] = []
        original = QMessageBox.exec

        def espiar(caixa: QMessageBox) -> int:
            vistas.append(caixa)
            return int(QMessageBox.StandardButton.Cancel)

        QMessageBox.exec = espiar  # type: ignore[method-assign]
        self.addCleanup(lambda: setattr(QMessageBox, "exec", original))
        painel.limpar_headers()

        self.assertEqual(len(vistas), 1)
        self.assertEqual(vistas[0].defaultButton(), vistas[0].button(QMessageBox.StandardButton.Cancel))
        self.assertIn("White = Coull", vistas[0].text(), "a pergunta nomeia o que vai sair")
        self.assertEqual(
            painel.model.current_annotation.headers.get("White"), "Coull", "cancelar não apagou nada"
        )


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class LoteDeDiagramasTests(unittest.TestCase):
    """O botão que manda o livro varrido para o lote de diagramas (S-544).

    **A origem é o índice da varredura**, e é a metade desta aba do item: aqui saem os quinhentos
    diagramas de um livro digitalizado; do lado da sala de estudo saem os que alguém analisou. O
    que vira arquivo é decidido por `ui/lote_de_diagramas.da_galeria`, e é afirmado sem janela em
    `tests/test_lote_de_diagramas.py` -- o que só existe aqui é o botão e o que ele abre.
    """

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)

    def painel(self) -> qt_galeria.PainelDaGaleria:
        return montar_painel(self, self.pasta)

    def _indexado(self) -> qt_galeria.PainelDaGaleria:
        from chess_diagram_ocr.gallery_scan import GalleryEntry

        painel = self.painel()
        painel.model.index = GalleryIndex(
            entries=[
                GalleryEntry(page_index=6, diagram_index=0, placement="8/8/8/8/8/8/8/K6k", side_to_move="b"),
                GalleryEntry(page_index=6, diagram_index=1, placement="8/8/8/8/8/8/8/K6k"),
            ]
        )
        painel.model.pdf_path = Path("C:/PDF/Secrets.pdf")
        painel.refresh(request_page=False)
        return painel

    def test_sem_varredura_o_botao_esta_cinza_e_o_clique_avisa(self) -> None:
        """Exportar zero diagramas abriria um diálogo para dizer que não há nada: a resposta a
        "varra o livro antes" é o botão não convidar ao clique."""
        painel = self.painel()
        self.assertFalse(painel.btn_diagramas.isEnabled())
        recados: list[str] = []
        painel.estado.connect(recados.append)
        self.assertIsNone(painel.exportar_diagramas())
        self.assertTrue(any("Varra o livro" in recado for recado in recados), recados)

    def test_o_indice_varrido_abre_o_lote_com_a_pagina_impressa_no_nome(self) -> None:
        painel = self._indexado()
        self.assertTrue(painel.btn_diagramas.isEnabled())
        dialogo = painel.exportar_diagramas()
        assert dialogo is not None
        self.addCleanup(descartar, dialogo)
        self.assertEqual(2, len(dialogo.itens))
        self.assertEqual({"Secrets"}, {item.livro for item in dialogo.itens})
        self.assertEqual((7, 7), tuple(item.pagina for item in dialogo.itens))
        self.assertEqual("8/8/8/8/8/8/8/K6k b - - 0 1", dialogo.itens[0].fen, "o lado que a S-17 deduziu")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
