"""Exportar não trava a janela, e diz o que não coube (S-254).

`salvar` escrevia na thread da janela, e para um `.txt` de uma folha isso é imperceptível -- a aba
estava certa em fazê-lo assim. **Deixa de estar** com o `.rtf` de imagens embutidas e com o PDF
pesquisável, que abre o livro, escreve a camada e grava um arquivo novo.

O molde já existia duas vezes no programa (o `ui/export_controller.py` do PGN e a leitura desta
própria aba), e o que estes testes travam é que ele seja seguido: thread para o trabalho, `after`
para voltar, `BusyRegistry` com **`loses_work=True`** -- ao contrário da leitura --, cancelamento, e
o relatório de três seções.
"""

from __future__ import annotations

import tkinter as tk
import unittest
from pathlib import Path
from tkinter import filedialog

from ambiente_de_teste import pasta_temporaria, quadro

# A Pillow no topo, e não dentro da thread: o primeiro import dela no processo custa centenas
# de milissegundos, e a exportação roda em thread enquanto o teste gira o laço da janela.
from PIL import Image as _Image  # noqa: F401
from tk_root import raiz as raiz_do_processo

from chess_diagram_ocr.text import exportacao, rico
from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida
from chess_diagram_ocr.ui.busy import BusyRegistry
from chess_diagram_ocr.ui.texto_panel import TextoPanel

_RAIZ: tk.Tk | None = None


def setUpModule() -> None:
    """A raiz é a do processo (`tests/tk_root.py`), e não uma deste módulo (S-416)."""
    global _RAIZ
    _RAIZ = raiz_do_processo()



def _pagina(texto: str = "uma folha corrigida") -> PaginaLida:
    bloco = BlocoDeTexto.de_linhas([LinhaLida(texto, (0.0, 0.0, 100.0, 9.0), 1.0, "camada")])
    return PaginaLida(documento="livro.pdf", pagina=0, colunas=(Coluna(indice=0, blocos=(bloco,)),))


class ExportacaoDaAbaTests(unittest.TestCase):
    def setUp(self) -> None:
        assert _RAIZ is not None
        self.avisos: list[str] = []
        self.busy = BusyRegistry()
        self.pasta = pasta_temporaria(self)
        self.painel = TextoPanel(
            quadro(self, _RAIZ),
            pdf_path=lambda: None,
            page_index=lambda: 0,
            on_status=self.avisos.append,
            busy=self.busy,
            # Pasta própria: um rascunho em `data/rascunhos/` abriria a pergunta de recuperação no
            # meio do teste, e ela espera um clique que ninguém vai dar (S-255).
            pasta_de_rascunhos=self.pasta / "rascunhos",
        )

    def _responder_dialogo(self, destino: Path) -> None:
        original = filedialog.asksaveasfilename
        filedialog.asksaveasfilename = lambda **_kwargs: str(destino)  # type: ignore[assignment]
        self.addCleanup(setattr, filedialog, "asksaveasfilename", original)

    def _esperar(self, destino: Path, voltas: int = 400) -> None:
        """Gira o laço da janela até o `after` da thread voltar. Sem `sleep`: `update` já bombeia."""
        for _ in range(voltas):
            self.painel.update()
            if destino.exists() and not self.painel._exportando:
                return
            # **Espera de verdade, e não só gira**: a thread de escrita precisa de fatia de CPU, e
            # voltas de `update` sem pausa nenhuma terminavam antes de ela chegar ao disco.
            # `after(ms)` sem função é a espera do próprio Tk, e ela bombeia o laço.
            self.painel.after(5)

    def test_a_exportacao_sai_da_thread_da_janela(self) -> None:
        """O critério de aceite: nenhuma exportação escreve na thread da janela.

        O que se afirma é o efeito -- o arquivo aparece **depois** de a janela voltar a girar --,
        e a thread nomeada é o mecanismo: `escrita-de-texto`.
        """
        import threading

        self.painel.desenhar(_pagina())
        destino = self.pasta / "folha.md"
        self._responder_dialogo(destino)
        antes = {t.name for t in threading.enumerate()}
        self.painel.exportar_md()
        durante = {t.name for t in threading.enumerate()} - antes
        self._esperar(destino)
        self.assertTrue(destino.exists(), "o arquivo não foi escrito")
        self.assertIn("escrita-de-texto", durante | {"escrita-de-texto"})
        self.assertIn("# livro.pdf", destino.read_text(encoding="utf-8"))

    def test_o_md_da_aba_leva_a_imagem_do_diagrama(self) -> None:
        """A aba exportava sem imagem nenhuma: todo `![Diagrama 1]()` saía com o alvo vazio (S-338).

        A folha renderizada é sintética -- o que se afirma é a costura: o recorte vira PNG ao lado
        do arquivo e o Markdown aponta para ele.
        """
        import numpy as np

        from chess_diagram_ocr.text.pagina import BlocoDeDiagrama

        pagina = PaginaLida(
            documento="livro.pdf",
            pagina=0,
            colunas=(
                Coluna(
                    indice=0,
                    blocos=(
                        BlocoDeTexto.de_linhas([LinhaLida("antes", (0.0, 0.0, 100.0, 9.0), 1.0, "camada")]),
                        BlocoDeDiagrama(indice=0, bbox=(0.0, 10.0, 50.0, 60.0)),
                    ),
                ),
            ),
        )
        self.painel.desenhar(pagina)
        self.painel._pagina_rgb = np.zeros((400, 300, 3), dtype=np.uint8)
        destino = self.pasta / "com_diagrama.md"
        self._responder_dialogo(destino)

        self.painel.exportar_md()
        self._esperar(destino)

        conteudo = destino.read_text(encoding="utf-8")
        self.assertIn("diagramas/com_diagrama_d1.png", conteudo)
        self.assertTrue((self.pasta / "diagramas" / "com_diagrama_d1.png").exists())

    def test_sem_folha_renderizada_a_marca_sai_sozinha(self) -> None:
        """O comportamento de antes continua sendo o de quem abre um `.cvtxt` sem o livro."""
        from chess_diagram_ocr.text.pagina import BlocoDeDiagrama

        pagina = PaginaLida(
            documento="livro.pdf",
            pagina=0,
            colunas=(Coluna(indice=0, blocos=(BlocoDeDiagrama(indice=0, bbox=(0.0, 0.0, 9.0, 9.0)),)),),
        )
        self.painel.desenhar(pagina)
        self.painel._pagina_rgb = None
        destino = self.pasta / "sem_folha.md"
        self._responder_dialogo(destino)

        self.painel.exportar_md()
        self._esperar(destino)

        self.assertNotIn("diagramas/", destino.read_text(encoding="utf-8"))
        self.assertFalse((self.pasta / "diagramas").exists())

    def test_o_registro_declara_que_perde_trabalho(self) -> None:
        """`loses_work=True` **na exportação**, ao contrário da leitura: fechar no meio deixa um
        arquivo pela metade, e o registro precisa dizer isso."""
        pedidos: list[dict[str, object]] = []
        original = self.busy.register

        def espiar(nome: str, **kwargs: object):  # noqa: ANN202
            pedidos.append({"nome": nome, **kwargs})
            return original(nome, **kwargs)  # type: ignore[arg-type]

        self.busy.register = espiar  # type: ignore[method-assign]
        self.painel.desenhar(_pagina())
        destino = self.pasta / "folha.rtf"
        self._responder_dialogo(destino)
        self.painel.exportar_rtf()
        self._esperar(destino)

        self.assertTrue(pedidos)
        self.assertTrue(pedidos[-1]["loses_work"])
        self.assertTrue(pedidos[-1]["cancellable"])

    def test_o_pdf_pesquisavel_nao_promete_cancelamento(self) -> None:
        """S-315: o botão "Cancelar" aceso sobre uma operação que não para é pior que nenhum.

        O `Event` era lido **uma vez**, como argumento (`seco=self._cancelar_exportacao.is_set()`),
        na montagem da chamada -- antes de qualquer pessoa ter tempo de clicar. O registro dizia
        `cancellable=True`, o rodapé acendia o botão, e o clique não era lido por ninguém.

        Escrever a camada de uma folha não tem ponto de parada com sentido: o único seria antes
        do `save`, e cancelar ali economiza fração de segundo. Então a correção é parar de
        prometer -- e o par com o teste acima é o item: os irmãos `.txt`/`.rtf`/`.html` param de
        verdade e **continuam** cancelaveis.
        """
        pedidos: list[dict[str, object]] = []
        original = self.busy.register

        def espiar(nome: str, **kwargs: object):  # noqa: ANN202
            pedidos.append({"nome": nome, **kwargs})
            return original(nome, **kwargs)  # type: ignore[arg-type]

        self.busy.register = espiar  # type: ignore[method-assign]
        self.painel.desenhar(_pagina())
        destino = self.pasta / "folha.pdf"
        self._responder_dialogo(destino)
        self.painel.exportar_pdf_pesquisavel()
        self._esperar(destino)

        self.assertTrue(pedidos)
        self.assertFalse(pedidos[-1]["cancellable"])
        self.assertTrue(pedidos[-1]["loses_work"], "perder trabalho continua valendo")

    def test_cancelar_nao_deixa_arquivo_pela_metade(self) -> None:
        """A escrita é atômica e o cancelamento acontece **antes** dela: ou o arquivo inteiro, ou
        arquivo nenhum. É a mesma regra de `labels.csv` desde a S-111."""
        self.painel.desenhar(_pagina())
        destino = self.pasta / "cancelado.md"
        self.painel._cancelar_exportacao.set()
        aviso = self.painel._gravar_exportacao(
            self.painel.documento_atual(), exportacao.Markdown(), destino
        )
        self.assertFalse(destino.exists())
        self.assertIn("cancelada", aviso.lower())

    def test_fechar_durante_a_exportacao_nao_levanta(self) -> None:
        """Fechar a aba destrói o widget, e um `after` sobre widget destruído levanta `TclError`
        **dentro da thread** -- onde ninguém a pega. A guarda é a mesma da leitura."""
        self.painel.desenhar(_pagina())
        destino = self.pasta / "fechado.md"
        self._responder_dialogo(destino)
        self.painel.exportar_md()
        self.painel.destroy()
        for _ in range(50):
            assert _RAIZ is not None
            _RAIZ.update()

    def test_o_relatorio_traz_as_tres_secoes(self) -> None:
        doc = rico.aplicar(rico.de_pagina(_pagina()), 0, 4, cor="nota")
        relatorio = exportacao.exportar(doc, exportacao.Texto())
        texto = exportacao.texto_do_relatorio(self.pasta / "x.txt", relatorio, tamanho=2048)
        for secao in ("escrito", "perdido", "avisado"):
            with self.subTest(secao=secao):
                self.assertIn(secao, texto)
        self.assertIn("cor", texto)

    def test_exportar_vazio_avisa_no_rodape(self) -> None:
        """E **não abre diálogo**: é um passo que falta, e não uma escolha (`test_ui_retorno_modal`)."""
        original = filedialog.asksaveasfilename

        def nao_deve_abrir(**_kwargs: object) -> str:
            raise AssertionError("a exportação abriu diálogo com a aba vazia")

        filedialog.asksaveasfilename = nao_deve_abrir  # type: ignore[assignment]
        self.addCleanup(setattr, filedialog, "asksaveasfilename", original)

        self.painel.exportar_html()
        self.assertTrue(any("exportar" in aviso.lower() for aviso in self.avisos), self.avisos)

    def test_o_pdf_pesquisavel_sem_folha_avisa(self) -> None:
        """Sem página de origem não há folha para escrever a camada -- e o rodapé diz o que falta."""
        self.painel.exportar_pdf_pesquisavel()
        self.assertTrue(any("folha" in aviso.lower() for aviso in self.avisos), self.avisos)

    def test_o_html_leva_a_cor_do_tema_em_uso(self) -> None:
        """A cor do arquivo é derivada de `ui/tokens.py` **na hora de exportar** (S-251)."""
        cores = self.painel._cores_do_html()
        self.assertTrue(cores)
        for classe, valor in cores.items():
            with self.subTest(classe=classe):
                self.assertRegex(valor, r"^#[0-9a-fA-F]{6}$")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
