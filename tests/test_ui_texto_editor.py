"""O editor desenhando o documento, com uma janela de verdade (S-235).

O que este arquivo afirma é a metade que `tests/test_texto_rico.py` não alcança: que **o texto que
o widget passa a conter é o mesmo** depois de o desenho deixar de percorrer `documento.segmentos` e
passar a percorrer as corridas. A trava de não-regressão do item é essa igualdade, e ela só se
verifica com um `tk.Text` na mão.
"""

from __future__ import annotations

import tempfile
import tkinter as tk
import unittest
from pathlib import Path

import numpy as np

from chess_diagram_ocr.text import arquivo, correcao, documento, rico
from chess_diagram_ocr.text.pagina import (
    BlocoDeDiagrama,
    BlocoDeTexto,
    Coluna,
    LinhaLida,
    PaginaLida,
)
from chess_diagram_ocr.ui import texto_panel
from chess_diagram_ocr.ui.busy import BusyRegistry
from chess_diagram_ocr.ui.texto_panel import TextoPanel


def _texto(
    conteudo: str,
    confianca: float = 1.0,
    procedencia: str = "camada",
    negrito=None,
    italico=None,
) -> BlocoDeTexto:
    return BlocoDeTexto.de_linhas(
        [LinhaLida(conteudo, (0.0, 0.0, 10.0, 10.0), confianca, procedencia, negrito, italico)]  # type: ignore[arg-type]
    )


def _pagina(*blocos: object, documento: str = "", folha: int = 0) -> PaginaLida:
    return PaginaLida(
        documento=documento,
        pagina=folha,
        colunas=(Coluna(indice=0, blocos=tuple(blocos)),),  # type: ignore[arg-type]
    )


_RAIZ: tk.Tk | None = None
"""Uma janela para o arquivo inteiro, e não uma por classe.

**Criar e destruir vários `Tk` no mesmo processo não sobrevive nesta máquina**: a partir do segundo,
o Tcl não reencontra `ttk/winTheme.tcl` e o `Tk()` levanta. Com quatro classes de teste isso
significava três delas puladas em silêncio -- testes que existem e não rodam, que é pior que não
tê-los. Uma raiz por módulo, criada uma vez e destruída no fim.
"""


def setUpModule() -> None:
    global _RAIZ
    try:
        _RAIZ = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - maquina sem display
        raise unittest.SkipTest(f"sem Tk disponível: {exc}") from exc
    _RAIZ.withdraw()


def tearDownModule() -> None:
    global _RAIZ
    if _RAIZ is not None:
        _RAIZ.destroy()
        _RAIZ = None


class _ComJanela:
    """A janela escondida que as classes abaixo compartilham.

    Mistura, e **não** classe de teste: herdar de um `TestCase` faria cada filha reexecutar os
    testes da mãe -- três vezes o mesmo caso, três vezes a mesma falha.
    """

    def _painel(self) -> TextoPanel:
        assert _RAIZ is not None
        return TextoPanel(
            _RAIZ,
            pdf_path=lambda: None,
            page_index=lambda: 0,
            on_status=lambda _mensagem: None,
            busy=BusyRegistry(),
        )


class DesenhoDoDocumentoTests(_ComJanela, unittest.TestCase):
    """Sem PDF aberto não há miniatura, e o widget contém exatamente o texto do documento."""

    def test_o_widget_contem_o_texto_do_documento(self) -> None:
        pagina = _pagina(
            _texto("In this position White has a decisive resource."),
            BlocoDeDiagrama(indice=0, bbox=(0.0, 0.0, 50.0, 50.0), confianca=0.9),
            _texto("1...Bxb7 2.Bxb7 Nd7", 0.5, "glifo"),
        )
        painel = self._painel()
        painel.desenhar(pagina)
        self.assertEqual(painel.texto_atual(), rico.de_pagina(pagina).para_texto())

    def test_a_marca_do_diagrama_esta_no_widget(self) -> None:
        painel = self._painel()
        painel.desenhar(_pagina(BlocoDeDiagrama(indice=4, bbox=(0.0, 0.0, 50.0, 50.0))))
        self.assertIn("[Diagrama 5]", painel.texto_atual())

    def test_a_faixa_de_revisar_marca_o_trecho_adivinhado(self) -> None:
        painel = self._painel()
        painel.desenhar(_pagina(_texto("adivinhado", 0.1, "glifo")))
        self.assertIn("revisar", painel.editor.tag_names("1.0"))

    def test_a_marca_nao_leva_faixa(self) -> None:
        """A marca é referência ao diagrama, e não texto lido: a régua de confiança não a alcança.

        As etiquetas de contexto da S-238 -- `bloco:` e `proc:` -- **estão** lá, e é o certo: elas
        são dado carregado pelo widget, não aparência, e é por elas que o diagrama volta ao lugar.
        """
        painel = self._painel()
        painel.desenhar(_pagina(BlocoDeDiagrama(indice=0, bbox=(0.0, 0.0, 5.0, 5.0), confianca=0.1)))
        nomes = set(painel.editor.tag_names("1.0"))
        self.assertIn("marca", nomes)
        self.assertEqual(nomes & set(documento.FAIXAS), set())

    def test_o_negrito_da_camada_vira_tag(self) -> None:
        painel = self._painel()
        painel.desenhar(_pagina(_texto("Título", negrito=True)))
        self.assertIn("negrito", painel.editor.tag_names("1.0"))

    def test_desenhar_documento_aceita_documento_sem_pagina(self) -> None:
        """É o caminho que a S-238 vai usar ao abrir um arquivo cujo PDF não está aberto."""
        painel = self._painel()
        painel.desenhar_documento(rico.de_texto("escrito à mão"))
        self.assertEqual(painel.texto_atual(), "escrito à mão")


class DocumentoAtualTests(_ComJanela, unittest.TestCase):
    """A volta: o que a pessoa tem na tela reconstruído do widget (S-238)."""

    def test_o_documento_atual_reproduz_o_desenhado(self) -> None:
        pagina = _pagina(
            _texto("prosa da página"),
            BlocoDeDiagrama(indice=0, bbox=(0.0, 0.0, 50.0, 50.0), confianca=0.9),
            _texto("1...Bxb7", 0.1, "glifo"),
        )
        painel = self._painel()
        painel.desenhar(pagina)
        self.assertEqual(painel.documento_atual().corridas, rico.de_pagina(pagina).corridas)

    def test_a_pagina_de_origem_acompanha_o_documento(self) -> None:
        pagina = _pagina(_texto("prosa"))
        painel = self._painel()
        painel.desenhar(pagina)
        self.assertIs(painel.documento_atual().origem, pagina)

    def test_o_ciclo_inteiro_pela_janela(self) -> None:
        """Desenhar, gravar, carregar, abrir e reler: o documento tem de ser o mesmo no fim."""
        pagina = _pagina(
            _texto("prosa"),
            BlocoDeDiagrama(indice=0, bbox=(1.0, 2.0, 3.0, 4.0)),
            _texto("lance", 0.5, "glifo"),
        )
        painel = self._painel()
        painel.desenhar(pagina)
        antes = painel.documento_atual()
        with tempfile.TemporaryDirectory() as pasta:
            caminho = arquivo.gravar(Path(pasta) / "a.cvtxt", antes)
            outro = self._painel()
            outro.abrir(arquivo.carregar(caminho))
        self.assertEqual(outro.documento_atual().corridas, antes.corridas)

    def test_a_edicao_a_mao_entra_no_documento(self) -> None:
        painel = self._painel()
        painel.desenhar(_pagina(_texto("prosa")))
        painel.editor.insert("end-1c", " corrigida")
        self.assertEqual(painel.documento_atual().para_texto(), "prosa corrigida")

    def test_digitar_dentro_do_bloco_mantem_a_origem(self) -> None:
        """A regra do Tk que este desenho compra: texto novo herda a etiqueta que os dois vizinhos
        têm. Digitar **dentro** do bloco 0 fica atado ao bloco 0 -- que é o que a S-239 precisa."""
        painel = self._painel()
        painel.desenhar(_pagina(_texto("prosa")))
        painel.editor.insert("1.3", "XX")
        corridas = painel.documento_atual().corridas
        self.assertEqual(painel.documento_atual().para_texto(), "proXXsa")
        self.assertEqual({c.bloco for c in corridas}, {0})

    def test_digitar_fora_de_tudo_nao_inventa_origem(self) -> None:
        painel = self._painel()
        painel.desenhar(_pagina(_texto("prosa")))
        painel.editor.insert("end-1c", " novo")
        novas = [c for c in painel.documento_atual().corridas if c.bloco == rico.SEM_BLOCO]
        self.assertEqual([c.texto for c in novas], [" novo"])


class MiniaturaNoCicloTests(_ComJanela, unittest.TestCase):
    """Com miniatura desenhada -- o caso em que a quebra do desenho poderia se acumular."""

    def _com_folha(self) -> TextoPanel:
        painel = self._painel()
        painel._pagina_rgb = np.full((200, 200, 3), 200, dtype=np.uint8)
        return painel

    def test_a_miniatura_e_desenhada(self) -> None:
        painel = self._com_folha()
        painel.desenhar(_pagina(BlocoDeDiagrama(indice=0, bbox=(0.0, 0.0, 40.0, 40.0))))
        self.assertTrue(painel.editor.dump("1.0", "end-1c", image=True))

    def test_a_quebra_do_desenho_nao_entra_no_documento(self) -> None:
        pagina = _pagina(BlocoDeDiagrama(indice=0, bbox=(0.0, 0.0, 40.0, 40.0)))
        painel = self._com_folha()
        painel.desenhar(pagina)
        self.assertEqual(painel.documento_atual().para_texto(), "[Diagrama 1]")

    def test_a_quebra_nao_se_acumula_a_cada_ciclo(self) -> None:
        """Sem a etiqueta de desenho, seria uma quebra a mais a cada salvar-e-reabrir, para sempre."""
        pagina = _pagina(BlocoDeDiagrama(indice=0, bbox=(0.0, 0.0, 40.0, 40.0)))
        painel = self._com_folha()
        painel.desenhar(pagina)
        primeiro = painel.documento_atual()
        for _ in range(3):
            painel.desenhar_documento(primeiro)
            self.assertEqual(painel.documento_atual().corridas, primeiro.corridas)


class AbrirSemLivroTests(_ComJanela, unittest.TestCase):
    def test_abrir_sem_o_pdf_abre_o_texto_e_avisa(self) -> None:
        """Livro fora do lugar não pode bloquear o acesso ao que se corrigiu nele."""
        pagina = _pagina(
            _texto("prosa"),
            BlocoDeDiagrama(indice=0, bbox=(0.0, 0.0, 40.0, 40.0)),
            documento="/pasta/que/nao/existe/livro.pdf",
            folha=41,
        )
        painel = self._painel()
        painel.abrir(rico.de_pagina(pagina))
        self.assertIn("prosa", painel.texto_atual())
        self.assertIn("[Diagrama 1]", painel.texto_atual())
        self.assertIn("livro.pdf", painel.status_var.get())

    def test_abrir_põe_a_folha_no_campo(self) -> None:
        pagina = _pagina(_texto("prosa"), folha=41)
        painel = self._painel()
        painel.abrir(rico.de_pagina(pagina))
        self.assertEqual(painel.folha_var.get(), "42")

    def test_abrir_documento_sem_pagina_nao_estoura(self) -> None:
        painel = self._painel()
        painel.abrir(rico.de_texto("só texto"))
        self.assertEqual(painel.texto_atual(), "só texto")


class CorrecaoHumanaTests(_ComJanela, unittest.TestCase):
    """A edição feita no widget chega marcada, e o par sobrevive ao arquivo (S-239)."""

    def test_editar_carimba_a_corrida_de_humano(self) -> None:
        painel = self._painel()
        painel.desenhar(_pagina(_texto("Black,s move", 0.9, "glifo")))
        painel.editor.delete("1.5")  # a vírgula de "Black,s"
        painel.editor.insert("1.5", "'")
        marcadas = [c for c in painel.documento_atual().corridas if c.bloco == 0]
        self.assertEqual({c.procedencia for c in marcadas}, {"humano"})

    def test_o_bloco_intocado_mantem_o_motor(self) -> None:
        painel = self._painel()
        painel.desenhar(_pagina(_texto("um", 0.9, "glifo"), _texto("dois", 0.9, "glifo")))
        painel.editor.insert("1.1", "X")
        por_bloco = {
            c.bloco: c.procedencia for c in painel.documento_atual().corridas if c.bloco >= 0
        }
        self.assertEqual(por_bloco, {0: "humano", 1: "glifo"})

    def test_o_par_chega_ao_arquivo_e_volta(self) -> None:
        """O ciclo que a S-212 vai consumir: corrigir na tela, salvar, e achar a troca no `.cvtxt`."""
        painel = self._painel()
        painel.desenhar(_pagina(_texto("Black,s move", 0.9, "glifo")))
        painel.editor.delete("1.5")  # a vírgula de "Black,s"
        painel.editor.insert("1.5", "'")
        with tempfile.TemporaryDirectory() as pasta:
            caminho = arquivo.gravar(Path(pasta) / "a.cvtxt", painel.documento_atual())
            achadas = correcao.correcoes(arquivo.carregar(caminho))
        self.assertEqual([(c.antes, c.depois) for c in achadas], [(",", "'")])
        self.assertEqual(achadas[0].motor, "glifo")

    def test_sem_edicao_nao_ha_correcao(self) -> None:
        painel = self._painel()
        painel.desenhar(_pagina(_texto("intacto", 0.9, "glifo")))
        self.assertEqual(correcao.correcoes(painel.documento_atual()), ())

    def test_o_texto_digitado_no_fim_e_humano_e_nao_e_correcao(self) -> None:
        painel = self._painel()
        painel.desenhar(_pagina(_texto("lido", 0.9, "glifo")))
        painel.editor.insert("end-1c", " acrescentado")
        doc = painel.documento_atual()
        novas = [c for c in doc.corridas if c.bloco == rico.SEM_BLOCO and c.tipo == rico.TEXTO]
        self.assertEqual([c.procedencia for c in novas], ["humano"])
        self.assertEqual(correcao.correcoes(doc), ())


class PendorNaTelaTests(_ComJanela, unittest.TestCase):
    """O itálico que o leitor mede chega ao widget como tag -- e o par com negrito também (S-236)."""

    def test_o_italico_da_pagina_vira_tag(self) -> None:
        painel = self._painel()
        painel.desenhar(_pagina(_texto("uma citação", italico=True)))
        self.assertIn("italico", painel.editor.tag_names("1.0"))

    def test_a_linha_em_pe_nao_leva_a_tag(self) -> None:
        painel = self._painel()
        painel.desenhar(_pagina(_texto("prosa", italico=False)))
        self.assertNotIn("italico", painel.editor.tag_names("1.0"))

    def test_o_desconhecido_desenha_como_normal(self) -> None:
        """`None` do modelo vira `False` na tela: ela desenha ou não desenha, sem terceiro estado."""
        painel = self._painel()
        painel.desenhar(_pagina(_texto("não medido", italico=None)))
        self.assertNotIn("italico", painel.editor.tag_names("1.0"))

    def test_negrito_e_italico_juntos_ganham_a_tag_combinada(self) -> None:
        """Uma tag do Tk só dá **uma** fonte ao trecho: sem a combinada, o negrito sumiria da tela."""
        painel = self._painel()
        painel.desenhar(_pagina(_texto("Título inclinado", negrito=True, italico=True)))
        etiquetas = painel.editor.tag_names("1.0")
        self.assertIn("negrito", etiquetas)
        self.assertIn("italico", etiquetas)
        self.assertIn(texto_panel.NEGRITO_ITALICO, etiquetas)

    def test_so_um_dos_dois_nao_traz_a_combinada(self) -> None:
        painel = self._painel()
        painel.desenhar(_pagina(_texto("só inclinado", italico=True)))
        self.assertNotIn(texto_panel.NEGRITO_ITALICO, painel.editor.tag_names("1.0"))

    def test_a_tag_combinada_nao_vira_atributo_na_volta(self) -> None:
        """Ela é desenho, e não documento: `corrida_de` a ignora por não mapear campo nenhum."""
        painel = self._painel()
        painel.desenhar(_pagina(_texto("Título inclinado", negrito=True, italico=True)))
        corrida = painel.documento_atual().corridas[0]
        self.assertTrue(corrida.atributos.negrito)
        self.assertTrue(corrida.atributos.italico)

    def test_o_italico_sobrevive_ao_ciclo_pela_janela(self) -> None:
        """Desenhar, gravar, reabrir: o pendor medido continua lá -- que é o ponto da S-235."""
        painel = self._painel()
        painel.desenhar(_pagina(_texto("uma citação", italico=True)))
        with tempfile.TemporaryDirectory() as pasta:
            caminho = arquivo.gravar(Path(pasta) / "a.cvtxt", painel.documento_atual())
            volta = arquivo.carregar(caminho)
        self.assertTrue(volta.corridas[0].atributos.italico)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
