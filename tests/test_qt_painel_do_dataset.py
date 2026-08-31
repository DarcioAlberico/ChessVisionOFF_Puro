"""A aba Dataset do segundo frontend (S-23/S-116/S-118/S-503).

**O que estes testes cobrem, e o que não.** O que é legalidade, o que é duplicata e o que cada
filtro deixa passar são de `dataset_browser.py` e já são afirmados em
`tests/test_dataset_browser.py`. O texto da tabela e das estatísticas é de
`ui/resumo_do_dataset.py`, e é puro. Nada disso é remedido aqui.

O que só existe deste lado são as quatro coisas em que o Qt difere do Tk e que quebram calado:

1. **A preguiça da S-116 é `showEvent` e não `<Map>`.** Se ela não chegar, `Ctrl+S` volta a
   custar 689 ms por amostra gravada -- num laço em que a pessoa grava dezenas seguidas.
2. **A pergunta de remoção tem três respostas**, e no Qt os botões precisam ser nomeados: "Sim" e
   "Não" numa pergunta que já é "remover?" leem-se como confirmar e desistir.
3. **A thread do hash perceptual fala por sinal**, e a devolução do botão tem de acontecer nos
   dois desfechos -- senão a falha deixa o botão cinza para sempre (S-314).
4. **Método com nome não-ASCII derruba o PyQt6 ao ser ligado a um sinal**, e este arquivo tem a
   guarda que impede a redescoberta. Ver `NomesLigaveisTests`.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.ui import resumo_do_dataset

if TEM_PYQT:
    from PyQt6.QtWidgets import QMessageBox

    from chess_diagram_ocr.qt import painel_do_dataset as qt_dataset

CABECALHO = "filename,fen,side_to_move,source_pdf,source_page,created_at\n"


class DeclaracaoTests(unittest.TestCase):
    """A decisão é a mesma dos dois lados, e nenhum dos dois a reescreve."""

    @unittest.skipUnless(TEM_PYQT, MOTIVO)
    def test_as_colunas_e_a_pagina_sao_as_mesmas(self) -> None:
        self.assertIs(qt_dataset.PainelDoDataset.COLUNAS, resumo_do_dataset.COLUNAS)
        self.assertIs(qt_dataset.PainelDoDataset.PAGE_SIZE, resumo_do_dataset.PAGE_SIZE)


class NomesLigaveisTests(unittest.TestCase):
    """Nenhum método do pacote `qt/` pode ter nome com caractere fora do ASCII.

    **Não é estilo: é uma queda do processo.** Medido no PyQt6 desta máquina --
    `botao.clicked.connect(self.pôr_em_quarentena)` mata o interpretador **na hora da conexão**,
    com `Segmentation fault` e nada mais: sem exceção, sem rastro, sem uma linha de log. O painel
    do Dataset nasceu com esse nome e a janela não abria; o sintoma não aponta para o nome, e o
    caminho até ele foi bissecar a montagem botão a botão.

    A guarda é sobre o pacote inteiro e não sobre o método que caiu, porque o próximo vai ser
    outro: este projeto nomeia em português, e `pôr`, `português`, `título` e `início` são todos
    identificadores válidos que alguém escreveria sem pensar duas vezes.

    **Rótulo de tela continua acentuado.** O que não pode ser acentuado é o *identificador* que
    vai para um `connect` -- e distinguir os dois casos exigiria saber quais métodos viram slot,
    que é justamente o que muda a cada painel novo. Varrer todos custa nada.

    Sem `skipUnless`: é uma leitura de arquivo, e ela vale mesmo onde o extra `qt` não está
    instalado -- que é onde o defeito passaria despercebido até alguém rodar a janela.
    """

    def test_nenhum_metodo_de_qt_tem_nome_fora_do_ascii(self) -> None:
        raiz = Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr" / "qt"
        culpados = [
            f"{arquivo.name}:{no.lineno} {no.name}"
            for arquivo in sorted(raiz.glob("*.py"))
            for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8")))
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and not no.name.isascii()
        ]
        self.assertEqual(culpados, [], "método de `qt/` com nome não-ASCII derruba o PyQt6 no connect")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PainelTests(unittest.TestCase):
    """O painel montado sobre um `labels.csv` de mentira."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        (self.pasta / "samples").mkdir()
        self.csv = self.pasta / "labels.csv"
        self.addCleanup(self.app.processEvents)

    def escrever(self, *linhas: str) -> None:
        self.csv.write_bytes((CABECALHO + "".join(f"{linha}\n" for linha in linhas)).encode("utf-8"))

    def painel(self, *, mostrar: bool = True, **kwargs: object) -> qt_dataset.PainelDoDataset:
        montado = qt_dataset.PainelDoDataset(
            caminhos=lambda: (self.csv, self.pasta / "samples", self.pasta / "splits.csv"),
            **kwargs,  # type: ignore[arg-type]
        )
        self.addCleanup(descartar, montado)
        if mostrar:
            montado.show()
            self.app.processEvents()
        return montado

    def test_a_aba_so_le_o_csv_quando_aparece(self) -> None:
        """A S-116 medida do outro lado: `load_rows` custa 689 ms, e o `Ctrl+S` chamava isso a
        cada amostra gravada **mesmo com a aba nunca aberta**."""
        self.escrever("a.png,8/8/8/8/8/8/8/K6k,w,Livro,3,2026-01-01")
        painel = self.painel(mostrar=False)
        self.assertEqual(painel.rows, [], "montar não pode ler o dataset")
        painel.reload()
        self.assertEqual(painel.rows, [], "escondida, a aba só anota que mudou")
        painel.show()
        self.app.processEvents()
        self.assertEqual(len(painel.rows), 1, "e paga quando aparece")

    def test_aparecer_de_novo_nao_rele_sem_motivo(self) -> None:
        self.escrever("a.png,8/8/8/8/8/8/8/K6k,w,Livro,3,2026-01-01")
        painel = self.painel()
        self.escrever(
            "a.png,8/8/8/8/8/8/8/K6k,w,Livro,3,2026-01-01",
            "b.png,8/8/8/8/8/8/8/K6k,b,Livro,4,2026-01-02",
        )
        painel.hide()
        painel.show()
        self.app.processEvents()
        self.assertEqual(len(painel.rows), 1, "sem aviso de mudança, a aba não relê")
        painel.reload()
        self.assertEqual(len(painel.rows), 2, "com a aba à vista, `reload` lê na hora")

    def test_o_filtro_de_livro_nasce_do_que_o_csv_tem(self) -> None:
        self.escrever(
            "a.png,8/8/8/8/8/8/8/K6k,w,Aagaard,3,2026-01-01",
            "b.png,8/8/8/8/8/8/8/K6k,b,Dvoretsky,4,2026-01-02",
        )
        painel = self.painel()
        itens = [painel.combo_livro.itemText(i) for i in range(painel.combo_livro.count())]
        self.assertEqual(itens, [resumo_do_dataset.TODOS, "Aagaard", "Dvoretsky"])

    def test_filtrar_por_livro_reduz_a_tabela_e_nao_o_dataset(self) -> None:
        self.escrever(
            "a.png,8/8/8/8/8/8/8/K6k,w,Aagaard,3,2026-01-01",
            "b.png,8/8/8/8/8/8/8/K6k,b,Dvoretsky,4,2026-01-02",
        )
        painel = self.painel()
        painel.combo_livro.setCurrentText("Aagaard")
        painel.aplicar_filtros()
        self.assertEqual(painel.tabela.topLevelItemCount(), 1)
        self.assertEqual(len(painel.rows), 2)
        painel.limpar_filtros()
        self.assertEqual(painel.tabela.topLevelItemCount(), 2)

    def test_a_pagina_e_a_frase_vem_do_modulo_puro(self) -> None:
        self.escrever(*[f"a{n}.png,8/8/8/8/8/8/8/K6k,w,Livro,{n},2026-01-01" for n in range(3)])
        painel = self.painel()
        self.assertEqual(
            painel.lbl_pagina.text(),
            resumo_do_dataset.frase_de_pagina(0, 3, 3, tamanho=painel.PAGE_SIZE),
        )

    def test_a_pagina_nao_passa_da_ultima_nem_da_primeira(self) -> None:
        self.escrever("a.png,8/8/8/8/8/8/8/K6k,w,Livro,3,2026-01-01")
        painel = self.painel()
        painel.mudar_pagina(5)
        self.assertIn("página 1/1", painel.lbl_pagina.text())
        painel.mudar_pagina(-5)
        self.assertIn("página 1/1", painel.lbl_pagina.text())

    def test_sem_selecao_o_gesto_vira_frase(self) -> None:
        self.escrever("a.png,8/8/8/8/8/8/8/K6k,w,Livro,3,2026-01-01")
        painel = self.painel()
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.tabela.clearSelection()
        painel.editar_selecionada()
        painel.quarentenar_selecionadas()
        painel.remover_selecionadas()
        self.assertEqual(
            vistos,
            ["Selecione uma amostra.", "Selecione ao menos uma amostra.", "Selecione ao menos uma amostra."],
        )

    def test_editar_devolve_a_linha_selecionada(self) -> None:
        self.escrever(
            "a.png,8/8/8/8/8/8/8/K6k,w,Livro,3,2026-01-01",
            "b.png,8/8/8/8/8/8/8/K6k,b,Livro,4,2026-01-02",
        )
        painel = self.painel()
        pedidas: list[object] = []
        painel.editar.connect(pedidas.append)
        item = painel.tabela.topLevelItem(1)
        assert item is not None
        item.setSelected(True)
        painel.editar_selecionada()
        self.assertEqual([linha.filename for linha in pedidas], ["b.png"])

    def test_a_selecao_sobrevive_a_recarga(self) -> None:
        """O lugar de quem estava conferindo, guardado por `filename` e não por índice (S-118)."""
        self.escrever(
            "a.png,8/8/8/8/8/8/8/K6k,w,Livro,3,2026-01-01",
            "b.png,8/8/8/8/8/8/8/K6k,b,Livro,4,2026-01-02",
        )
        painel = self.painel()
        item = painel.tabela.topLevelItem(1)
        assert item is not None
        item.setSelected(True)
        painel.reload()
        self.assertEqual([linha.filename for linha in painel.linhas_selecionadas()], ["b.png"])

    def test_a_pergunta_de_remocao_nomeia_as_tres_saidas(self) -> None:
        """"Sim" e "Não" numa pergunta que já é "remover?" leem-se como confirmar e desistir --
        e quem quisesse preservar o PNG apertaria "Não" achando que estava cancelando."""
        self.escrever("a.png,8/8/8/8/8/8/8/K6k,w,Livro,3,2026-01-01")
        painel = self.painel()
        item = painel.tabela.topLevelItem(0)
        assert item is not None
        item.setSelected(True)

        vistas: list[QMessageBox] = []

        def espiar(self: QMessageBox) -> int:
            vistas.append(self)
            return 0

        original = QMessageBox.exec
        QMessageBox.exec = espiar  # type: ignore[method-assign]
        self.addCleanup(lambda: setattr(QMessageBox, "exec", original))
        painel.remover_selecionadas()

        self.assertEqual(len(vistas), 1)
        rotulos = [botao.text() for botao in vistas[0].buttons()]
        self.assertEqual(len(rotulos), 3, "a pergunta tem três respostas")
        self.assertTrue(any("apagar o PNG" in rotulo for rotulo in rotulos))
        self.assertTrue(any("só a linha" in rotulo for rotulo in rotulos))
        self.assertIn("a.png", vistas[0].text(), "a pergunta nomeia o que vai sumir (S-170)")
        self.assertTrue(self.csv.exists(), "e não remove nada sem resposta")

    def test_a_deteccao_de_duplicatas_devolve_o_botao_nos_dois_desfechos(self) -> None:
        """Reabilitar só no caminho feliz troca um travamento por outro (S-314)."""
        self.escrever("a.png,8/8/8/8/8/8/8/K6k,w,Livro,3,2026-01-01")
        painel = self.painel()
        painel.btn_duplicatas.setEnabled(False)
        painel._aplicar_duplicatas([["a.png", "b.png"]])
        self.assertTrue(painel.btn_duplicatas.isEnabled())
        self.assertEqual(painel._grupos_duplicados, [["a.png", "b.png"]])

        vistas: list[str] = []
        original = QMessageBox.critical
        QMessageBox.critical = staticmethod(lambda *args, **kwargs: vistas.append(args[2]))  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(QMessageBox, "critical", original))
        painel.btn_duplicatas.setEnabled(False)
        painel._falhou_duplicatas("disco cheio")
        self.assertTrue(painel.btn_duplicatas.isEnabled())
        self.assertTrue(vistas and "disco cheio" in vistas[0])

    def test_um_clique_de_cada_vez(self) -> None:
        from chess_diagram_ocr.ui.busy import BusyRegistry

        self.escrever("a.png,8/8/8/8/8/8/8/K6k,w,Livro,3,2026-01-01")
        registro = BusyRegistry()
        painel = self.painel(busy=registro)
        painel._busy_token = registro.register("detecção de duplicatas", loses_work=False)
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.detectar_duplicatas()
        self.assertEqual(vistos, ["A detecção de duplicatas já está em andamento."])
        self.assertEqual(len(registro.running()), 1, "e não vaza uma segunda chave")

    def test_as_estatisticas_saem_do_texto_puro(self) -> None:
        self.escrever("a.png,8/8/8/8/8/8/8/K6k,w,Livro,3,2026-01-01")
        painel = self.painel()
        janela = painel.mostrar_estatisticas()
        assert janela is not None
        self.addCleanup(descartar, janela)
        self.assertEqual(
            janela.corpo.toPlainText(), resumo_do_dataset.texto_de_estatisticas(painel.rows)
        )

    def test_dataset_vazio_nao_abre_estatisticas(self) -> None:
        self.escrever()
        painel = self.painel()
        self.assertIsNone(painel.mostrar_estatisticas())

    def test_conferir_com_o_modelo_vira_frase_de_rodape(self) -> None:
        """A caixa era modal por não haver outro lugar, e conferir amostra a amostra é gesto de
        repetição -- exatamente onde um clique obrigatório por resposta custa mais (S-164)."""
        self.escrever("a.png,8/8/8/8/8/8/8/K6k,w,Livro,3,2026-01-01")
        painel = self.painel(conferir=lambda linha: f"{linha.filename}: o modelo concorda")
        item = painel.tabela.topLevelItem(0)
        assert item is not None
        item.setSelected(True)
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.conferir_selecionada()
        self.assertEqual(vistos, ["a.png: o modelo concorda"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
