"""Os quatro diálogos do segundo frontend (S-86/S-119/S-503).

**O que estes testes cobrem, e o que não.** Onde mora o cache de cada conjunto de bases, a regra
de pular o livro completo, a montagem da linha da candidata e a ordem das métricas são puras, e
moram nos quatro módulos declarados (`escolha_de_bases`, `escopo_da_varredura`,
`lista_de_partidas`, `pedido_de_treino`) mais `tests/test_games_census.py` e
`tests/test_training.py`. Nada disso é remedido aqui.

O que só existe aqui são as coisas do toolkit que quebram caladas:

1. **`exec()` é o modal e o resultado ao mesmo tempo**, e o `Escape` fecha de graça. No Tk é
   `grab_set` + `wait_window` + `WM_DELETE_WINDOW`, e esquecer o terceiro faz o `X` da janela
   devolver "confirmado" em vez de "desisti".
2. **A cor da linha da candidata é por item**, porque o Qt não tem etiqueta de `Treeview`.
3. **O modal do treino esconde e não destrói ao fechar** -- a thread continua escrevendo nele.
4. **O texto do treino atravessa a fronteira de thread por sinal.**
"""

from __future__ import annotations

import threading
import unittest
from pathlib import Path

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.ui import (
    escopo_da_varredura,
    lista_de_partidas,
    pedido_de_treino,
)

if TEM_PYQT:
    from PyQt6.QtCore import QThread

    from chess_diagram_ocr.qt import dialogos as qt_dialogos


class DeclaracaoTests(unittest.TestCase):
    """Cada diálogo do Tk reexporta o módulo puro que o do Qt chama."""

    @unittest.skipUnless(TEM_PYQT, MOTIVO)
    def test_as_colunas_da_candidata_saem_da_mesma_declaracao(self) -> None:
        """Uma coluna a mais de um lado é a mesma candidata lida de dois jeitos."""
        self.assertEqual(
            [(c.chave, c.titulo, c.largura) for c in qt_dialogos.COLUNAS_DA_LISTA],
            list(lista_de_partidas.COLUNAS),
        )
        # Três elásticas: nomes e evento são os campos sem tamanho previsível.
        self.assertEqual(
            [c.chave for c in qt_dialogos.COLUNAS_DA_LISTA if c.elastica], ["white", "black", "event"]
        )


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class BasesTests(unittest.TestCase):
    """A lista de `.pgn` com caixas de marcar."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)

    def dialogo(self, **kwargs: object) -> qt_dialogos.DialogoDeBases:
        montado = qt_dialogos.DialogoDeBases(
            folder=self.pasta, nota=lambda bases: f"nota de {len(bases)}", **kwargs  # type: ignore[arg-type]
        )
        self.addCleanup(descartar, montado)
        return montado

    def base(self, nome: str, tamanho: int = 1_000) -> Path:
        caminho = self.pasta / nome
        caminho.write_bytes(b"x" * tamanho)
        return caminho

    def test_a_pasta_vem_marcada_por_padrao(self) -> None:
        """É o comportamento de sempre: as duas buscas usavam *todos* os `.pgn`."""
        self.base("a.pgn")
        self.base("b.pgn")
        dialogo = self.dialogo()
        self.assertEqual([caminho.name for caminho in dialogo.selecao], ["a.pgn", "b.pgn"])
        self.assertTrue(dialogo.btn_ok.isEnabled())

    def test_desmarcar_tudo_desabilita_o_procurar(self) -> None:
        """A busca precisa de pelo menos um `.pgn` para ter onde procurar."""
        self.base("a.pgn")
        dialogo = self.dialogo()
        dialogo._marcar(False)
        self.assertFalse(dialogo.btn_ok.isEnabled())
        dialogo.confirmar()
        self.assertIsNone(dialogo.escolhidas, "e o Return não confirma nada")

    def test_a_marca_da_caixa_chega_a_selecao(self) -> None:
        """A caixa é o gesto; sem o sinal ligado, desmarcar não muda a busca."""
        a, b = self.base("a.pgn"), self.base("b.pgn")
        dialogo = self.dialogo()
        dialogo._caixas[str(a)].setChecked(False)
        self.assertEqual(dialogo.selecao, (b,))
        self.assertIn("1 base(s)", dialogo.lbl_total.text())

    def test_a_frase_do_cache_acompanha_a_escolha(self) -> None:
        """Ela é o que decide entre "clico agora" e "hoje não"."""
        self.base("a.pgn")
        dialogo = self.dialogo()
        self.assertEqual(dialogo.lbl_nota.text(), "nota de 1")
        dialogo._marcar(False)
        self.assertEqual(dialogo.lbl_nota.text(), "nota de 0")

    def test_adicionar_de_fora_nao_duplica_o_que_ja_esta_na_lista(self) -> None:
        a = self.base("a.pgn")
        dialogo = self.dialogo()
        dialogo._marcar(False)
        dialogo._escolher = lambda: [str(a), str(self.pasta / "c.pgn")]
        dialogo.adicionar_do_disco()
        self.assertEqual([caminho.name for caminho in dialogo._bases], ["a.pgn", "c.pgn"])
        self.assertEqual([caminho.name for caminho in dialogo.selecao], ["a.pgn", "c.pgn"])

    def test_confirmar_guarda_a_escolha(self) -> None:
        self.base("a.pgn")
        dialogo = self.dialogo()
        dialogo.confirmar()
        self.assertEqual([caminho.name for caminho in dialogo.escolhidas or ()], ["a.pgn"])

    def test_desistir_deixa_a_escolha_em_none(self) -> None:
        """`Escape` e o X: os dois passam por `reject`, e nenhum inventa uma escolha."""
        self.base("a.pgn")
        dialogo = self.dialogo()
        dialogo.reject()
        self.assertIsNone(dialogo.escolhidas)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class EscopoTests(unittest.TestCase):
    """Que livros a varredura percorre."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)

    def dialogo(self, **kwargs: object) -> qt_dialogos.DialogoDeEscopo:
        montado = qt_dialogos.DialogoDeEscopo(folder=self.pasta, **kwargs)  # type: ignore[arg-type]
        self.addCleanup(descartar, montado)
        return montado

    def test_com_livro_aberto_o_padrao_e_ele(self) -> None:
        dialogo = self.dialogo(open_book=Path("livro.pdf"))
        self.assertEqual(dialogo.tipo(), escopo_da_varredura.ABERTO)
        dialogo.confirmar()
        self.assertEqual(dialogo.escopo, escopo_da_varredura.ScanScope("aberto", (Path("livro.pdf"),)))

    def test_sem_livro_aberto_a_opcao_fica_cinza_e_o_padrao_e_a_pasta(self) -> None:
        """É a razão de o diálogo poder ser aberto sem livro nenhum na tela."""
        dialogo = self.dialogo()
        self.assertFalse(dialogo.opcao_aberto.isEnabled())
        self.assertEqual(dialogo.tipo(), escopo_da_varredura.PASTA)

    def test_a_pasta_vazia_desabilita_a_opcao_de_pasta(self) -> None:
        dialogo = self.dialogo()
        self.assertFalse(dialogo.opcao_pasta.isEnabled())

    def test_a_pasta_lista_os_pdfs_em_ordem(self) -> None:
        for nome in ("b.pdf", "a.pdf"):
            (self.pasta / nome).write_bytes(b"%PDF")
        dialogo = self.dialogo()
        self.assertTrue(dialogo.opcao_pasta.isEnabled())
        self.assertIn("2 livro(s)", dialogo.opcao_pasta.text())
        dialogo.confirmar()
        assert dialogo.escopo is not None
        self.assertEqual([caminho.name for caminho in dialogo.escopo.books], ["a.pdf", "b.pdf"])
        self.assertTrue(dialogo.escopo.skip_complete, "mais de um livro é 'varra o que falta'")

    def test_cancelar_o_seletor_nao_e_desistir_de_varrer(self) -> None:
        """Cancelar a caixa de abrir arquivo é "escolhi errado": o diálogo continua aberto para a
        pessoa marcar outro escopo, que é o que ela ia querer fazer de qualquer jeito."""
        dialogo = self.dialogo(escolher=lambda: [])
        dialogo.opcao_escolher.setChecked(True)
        dialogo.confirmar()
        self.assertIsNone(dialogo.escopo)
        self.assertNotEqual(dialogo.result(), int(qt_dialogos.QDialog.DialogCode.Accepted))

    def test_escolher_em_disco_vira_lista_de_livros(self) -> None:
        dialogo = self.dialogo(escolher=lambda: ["x.pdf", "y.pdf"])
        dialogo.opcao_escolher.setChecked(True)
        dialogo.confirmar()
        assert dialogo.escopo is not None
        self.assertEqual(dialogo.escopo.kind, escopo_da_varredura.ESCOLHER)
        self.assertEqual([caminho.name for caminho in dialogo.escopo.books], ["x.pdf", "y.pdf"])


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class TreinoTests(unittest.TestCase):
    """O modal do treino e o controlador que fala com ele de outra thread."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.addCleanup(self.app.processEvents)

    def controlador(self, **kwargs: object) -> qt_dialogos.ControladorDeTreino:
        montado = qt_dialogos.ControladorDeTreino(
            pedido=lambda: pedido_de_treino.TrainingRequest(
                csv_path=Path("labels.csv"),
                samples_dir=Path("samples"),
                model_path=Path("modelo.pt"),
                epochs=8,
                batch_size=16,
                lr=1e-3,
            ),
            **kwargs,  # type: ignore[arg-type]
        )
        self.addCleanup(descartar, montado)
        return montado

    def test_fechar_o_modal_esconde_em_vez_de_destruir(self) -> None:
        """O treino continua rodando, e destruir a janela deixaria a thread escrevendo em
        widgets que já não existem."""
        controlador = self.controlador()
        dialogo = controlador.mostrar()
        self.app.processEvents()
        dialogo.reject()
        self.assertTrue(dialogo.isHidden())
        self.assertIs(controlador.dialogo, dialogo, "o mesmo modal volta no próximo `mostrar`")
        self.assertIs(controlador.mostrar(), dialogo)

    def test_a_barra_e_indeterminada(self) -> None:
        """Ela não sabe quanto falta porque o treino também não: quem conta épocas é o rodapé."""
        dialogo = self.controlador().mostrar()
        self.assertEqual((dialogo.barra.minimum(), dialogo.barra.maximum()), (0, 0))

    def test_o_texto_atravessa_a_fronteira_de_thread(self) -> None:
        """Escrever num `QLabel` da thread do treino derruba o processo -- e nem sempre na hora."""
        controlador = self.controlador()
        dialogo = controlador.mostrar()
        de_onde: list[object] = []

        class Treino(QThread):
            def run(self) -> None:
                de_onde.append(threading.current_thread())
                controlador.escrever("Treinando... época 3/8", "exata/tabuleiro=0.9120")

        fio = Treino()
        fio.start()
        fio.wait(5_000)
        self.app.processEvents()

        self.assertIsNot(de_onde[0], threading.main_thread(), "o teste precisa de duas threads")
        self.assertEqual(dialogo.lbl_status.text(), "Treinando... época 3/8")
        self.assertEqual(dialogo.lbl_metricas.text(), "exata/tabuleiro=0.9120")

    def test_segundo_treino_enquanto_o_primeiro_roda_vira_frase(self) -> None:
        controlador = self.controlador()
        controlador._rodando = True
        vistos: list[str] = []
        controlador.estado.connect(vistos.append)
        controlador.iniciar()
        self.assertEqual(vistos, ["Já existe um treino em execução."])

    def test_cancelar_sem_treino_em_curso_nao_faz_nada(self) -> None:
        controlador = self.controlador()
        vistos: list[str] = []
        controlador.estado.connect(vistos.append)
        controlador.cancelar()
        self.assertEqual(vistos, [])

    def test_cancelar_marca_o_evento_e_avisa_que_termina_a_epoca(self) -> None:
        """A resposta vem entre épocas, não no meio de uma (S-60)."""
        controlador = self.controlador()
        controlador._cancelar = threading.Event()
        vistos: list[str] = []
        controlador.estado.connect(vistos.append)
        controlador.cancelar()
        self.assertTrue(controlador._cancelar.is_set())
        self.assertEqual(vistos, ["Cancelando treino... termina a época atual e para."])

    def test_concluir_devolve_os_controles_e_fecha_o_modal(self) -> None:
        controlador = self.controlador()
        controlador.mostrar()
        controlador._rodando = True
        ligados: list[bool] = []
        controlador.controles.connect(ligados.append)
        controlador.concluir()
        self.assertEqual(ligados, [True])
        self.assertFalse(controlador.rodando)
        self.assertIsNone(controlador.dialogo)

    def test_o_progresso_conta_epocas_no_registro_de_ocupado(self) -> None:
        """Com o número, e não só com a frase: é o que faz a barra do rodapé ser determinada."""
        from chess_diagram_ocr.ui.busy import BusyRegistry

        registro = BusyRegistry()
        controlador = self.controlador(busy=registro)
        controlador._total_de_epocas = 8
        controlador._busy_token = registro.register("treino do modelo", loses_work=True, detail="época 1 de 8")
        controlador.mostrar()
        controlador._progresso({"epoch": 3, "val_board_exact_acc": 0.9})
        self.app.processEvents()
        operacao = registro.running()[0]
        self.assertEqual((operacao.feito, operacao.total), (3, 8))
        self.assertEqual(operacao.detail, "época 3 de 8")
        self.assertIn("época 3/8", controlador.dialogo.lbl_status.text())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
