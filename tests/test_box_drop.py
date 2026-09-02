"""Tirar da página o retângulo que o detector marcou errado (S-177).

**O que isto fecha.** O detector erra, e a caixa errada não é inerte: ela ocupa uma vaga do
`max_boards`, entra na numeração que o `[Diagram "N"]` do PGN usa e -- quando é grande, que é o
caso da faixa de página da S-176 -- esconde os diagramas de verdade debaixo dela. A única
resposta disponível era desligar "Marcar diagramas" para a página inteira, que apaga junto o
que estava certo, ou anotar a página no conjunto de campo, que é gravar no disco uma afirmação
sobre o livro quando o que se queria era limpar a tela.

A regra de `DroppedBoxes` está em `test_page_overlay.py`. O que sobra para cá é a costura: a
janela guardar a remoção, o desenho seguinte não trazer a caixa de volta, e devolver ser página
a página.

**Contra a janela de verdade, e não uma montada com os métodos dela.** No Tk isto era um tipo
sintético com cinco métodos reais e o resto de mentira, porque montar o `ChessOcrTkApp` inteiro
exigia checkpoint, PDF e display. A janela do Qt monta sob `offscreen` com um serviço falso, e
medir a costura na janela que o usuário abre é justamente o que o recurso anterior não dava.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.ui.page_overlay import DiagramBox, PageBoxes

if TEM_PYQT:
    from chess_diagram_ocr.qt.janela import JanelaPrincipal

FAIXA = DiagramBox(index=0, bbox_pdf=(-9.0, 11.6, 450.8, 414.8), source="embedded")
"""A caixa do relato da S-176: 460×403 pt sobre uma página de 453×666."""

DIAGRAMA = DiagramBox(index=1, bbox_pdf=(278.0, 437.8, 427.8, 606.8), source="embedded")


class _ServicoFalso:
    device = None
    device_label = ""
    caption_reader = None

    def invalidate_model(self, caminho: object = None) -> None: ...


def _livro(pasta: Path, paginas: int = 3, nome: str = "livro.pdf") -> Path:
    import fitz

    caminho = pasta / nome
    doc = fitz.open()
    for _ in range(paginas):
        doc.new_page(width=453, height=666)
    doc.save(caminho)
    doc.close()
    return caminho


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class TirarACaixaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.livro = _livro(self.pasta)
        self.janela = JanelaPrincipal(
            motor=None,  # a suíte não procura binário na máquina de quem a roda (S-523)
            servico=_ServicoFalso(),  # type: ignore[arg-type]
            csv_de_rotulos=self.pasta / "labels.csv",
            pasta_de_estudos=self.pasta,
            caminho_do_estado=self.pasta / "janela.json",
            pasta_da_galeria=self.pasta,
        )
        self.addCleanup(descartar, self.janela)
        self.janela.abrir_pdf(self.livro)
        self.app.processEvents()

        # As caixas entram pelo cache, que é por onde a detecção as entrega -- e **com os
        # parâmetros da janela**, que fazem parte da chave.
        self.chave = self.janela._chave_do_documento()
        self.params = self.janela._parametros()
        self.janela._guardar(PageBoxes(0, self.params, (FAIXA, DIAGRAMA)))
        self.janela._publicar_caixas(self.janela._caixas_por_pagina.get(self.chave, 0, self.params))

    def _na_tela(self) -> list[int]:
        caixas = self.janela.pdf.boxes
        return [] if caixas is None else [caixa.index for caixa in caixas.boxes]

    def _recado(self) -> str:
        return self.janela.rodape.mensagem()

    def test_a_caixa_tirada_some_do_desenho_seguinte(self) -> None:
        self.assertEqual(self._na_tela(), [0, 1])
        self.janela._tirar_caixa(0)
        self.assertEqual(self._na_tela(), [1])

    def test_o_cache_do_detector_nao_e_reescrito(self) -> None:
        """O cache guarda o que o **detector** achou; reescrevê-lo faria a remoção parecer
        detecção -- e a remoção é um juízo humano sobre uma página, não um resultado."""
        self.janela._tirar_caixa(0)
        guardadas = self.janela._caixas_por_pagina.get(self.chave, 0, self.params)
        assert guardadas is not None
        self.assertEqual([caixa.index for caixa in guardadas.boxes], [0, 1])

    def test_virar_a_pagina_e_voltar_nao_traz_a_caixa_de_volta(self) -> None:
        """A remoção é da sessão, e sobrevive dentro dela: senão o gesto não resolve nada."""
        self.janela._tirar_caixa(0)
        self.janela.pdf.ir_para_pagina(1)
        self.janela.pdf.ir_para_pagina(0)
        self.app.processEvents()
        self.assertEqual(self._na_tela(), [1])

    def test_a_numeracao_que_sobra_nao_e_refeita(self) -> None:
        """O buraco é a informação honesta: ali havia uma caixa, e você a tirou.

        Renumerar faria o clique no retângulo "2" abrir o diagrama 3 do editor -- é a mesma razão
        que está escrita em `DroppedBoxes.apply`.
        """
        self.janela._tirar_caixa(0)
        self.assertEqual(self._na_tela(), [1], "a caixa que sobrou foi renumerada para 0")

    def test_uma_pagina_com_todas_as_caixas_tiradas_fica_vazia(self) -> None:
        """Redetectar traria de volta exatamente o que o usuário recusou."""
        self.janela._tirar_caixa(0)
        self.janela._tirar_caixa(1)
        self.assertEqual(self._na_tela(), [])

    def test_a_barra_de_status_diz_quantas_ja_foram_tiradas(self) -> None:
        self.janela._tirar_caixa(0)
        self.assertIn("Caixa 1 tirada", self._recado())
        self.janela._tirar_caixa(1)
        self.assertIn("2 caixas tiradas", self._recado())

    def test_tirar_uma_caixa_que_nao_esta_mais_na_pagina_avisa(self) -> None:
        self.janela._tirar_caixa(0)
        self.janela._tirar_caixa(0)
        self.assertIn("não está mais na página", self._recado())

    def test_devolver_traz_de_volta_e_repinta(self) -> None:
        self.janela._tirar_caixa(0)
        self.janela.devolver_caixas()
        self.assertEqual(self._na_tela(), [0, 1])
        self.assertIn("1 caixa devolvida", self._recado())

    def test_devolver_numa_pagina_sem_remocao_nao_repinta_nem_mente(self) -> None:
        self.janela.devolver_caixas()
        self.assertIn("Nenhuma caixa foi tirada", self._recado())
        self.assertEqual(self._na_tela(), [0, 1])

    def test_devolver_e_da_pagina_exibida_e_nao_um_desfazer_global(self) -> None:
        """Desfazer noutra página mudaria o que o usuário não está vendo."""
        self.janela._tirar_caixa(0)
        self.janela._tiradas.drop(self.chave, 1, DIAGRAMA.bbox_pdf)

        self.janela.devolver_caixas()

        self.assertEqual(self.janela._tiradas.count(self.chave, 0), 0)
        self.assertEqual(self.janela._tiradas.count(self.chave, 1), 1, "apagou a remoção da outra página")

    def test_trocar_de_livro_esquece_as_remocoes(self) -> None:
        """Elas são por (livro, página), e o livro novo não herda o juízo feito sobre o velho."""
        self.janela._tirar_caixa(0)
        self.janela.abrir_pdf(_livro(self.pasta, paginas=1, nome="outro.pdf"))
        self.assertEqual(len(self.janela._tiradas), 0)


if __name__ == "__main__":
    unittest.main()
