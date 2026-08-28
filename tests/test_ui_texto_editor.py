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
from chess_diagram_ocr.text import paleta as _paleta
from chess_diagram_ocr.text.pagina import (
    BlocoDeDiagrama,
    BlocoDeTexto,
    Coluna,
    LinhaLida,
    PaginaLida,
)
from chess_diagram_ocr.ui import atalhos, texto_cores, texto_panel
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
        """O painel com uma pasta de rascunho **própria** (S-255).

        Sem isto a suíte leria `data/rascunhos/` da máquina de quem a roda -- e um rascunho ali
        abriria a pergunta de recuperação no meio de um teste, que trava tudo esperando um clique.
        """
        assert _RAIZ is not None
        return TextoPanel(
            _RAIZ,
            pdf_path=lambda: None,
            page_index=lambda: 0,
            on_status=lambda _mensagem: None,
            busy=BusyRegistry(),
            pasta_de_rascunhos=Path(tempfile.mkdtemp()),
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


class FerramentasDeFormatoTests(_ComJanela, unittest.TestCase):
    """As três teclas, o carimbo de humano e o espelho dos interruptores (S-241)."""

    def _com_texto(self, conteudo: str = "uma frase para formatar") -> TextoPanel:
        painel = self._painel()
        painel.desenhar(_pagina(_texto(conteudo)))
        return painel

    def test_o_negrito_entra_na_palavra_sob_o_cursor(self) -> None:
        painel = self._com_texto()
        painel.editor.mark_set("insert", "1.6")
        painel.negrito()
        doc = painel.documento_atual()
        self.assertEqual([c.texto for c in doc.corridas if c.atributos.negrito], ["frase"])

    def test_alternar_duas_vezes_volta_ao_que_era(self) -> None:
        painel = self._com_texto()
        antes = painel.documento_atual().para_texto()
        painel.editor.tag_add("sel", "1.0", "1.3")
        painel.negrito()
        painel.negrito()
        doc = painel.documento_atual()
        self.assertFalse(any(c.atributos.negrito for c in doc.corridas))
        self.assertEqual(doc.para_texto(), antes)

    def test_ctrl_i_nao_insere_tabulacao(self) -> None:
        """Em `tk8.6/text.tcl:211`, `bind Text <Control-i>` insere **uma tabulação**. Sem o
        `"break"`, a tecla entregaria o itálico e o tab -- e o texto de quem corrige uma página
        ganharia um caractere que ninguém digitou."""
        painel = self._com_texto()
        painel.editor.mark_set("insert", "1.6")
        painel.editor.focus_set()
        painel.editor.event_generate("<Control-i>")
        painel.update()
        self.assertNotIn("	", painel.texto_atual())

    def test_toda_tecla_do_editor_esta_ligada_no_widget(self) -> None:
        """**O que este teste mede, e o que ele não consegue medir** (S-267).

        Ele afirmava "a tecla não mexeu no texto" gerando o evento numa janela `withdraw`n -- e ali
        `event_generate` de teclado **não entrega a ninguém**, porque não há foco de verdade. O
        texto ficava igual porque nada disparava, e o teste passava em verde sobre nove teclas sem
        exercitar uma. Medido em 2026-08-26, com uma janela visível: a mesma tecla dispara, e sem o
        `bind` do widget o `Ctrl+H` da classe `Text` **apaga um caractere** (`abcdef` -> `abdef`).

        O que sobra de afirmável sem janela na tela é o que importa: que cada sequência declarada
        tem um `bind` **no próprio widget**. É esse `bind` que roda antes da classe `Text` e a
        impede -- as bindtags são widget, classe, toplevel, all, nessa ordem. Um `bind_all` chegaria
        tarde. Que o método existe é `test_toda_tecla_do_editor_tem_metodo`; que a sobreposição com
        a tabela da janela está declarada é `tests/test_ui_atalhos_destino.py`.
        """
        painel = self._com_texto()
        for acao, sequencia in atalhos.TECLAS_DO_EDITOR.items():
            with self.subTest(acao=acao):
                ligado = str(painel.editor.bind(sequencia)).strip()
                self.assertTrue(ligado, f"{acao} declarada e sem bind no widget")
                self.assertIn("break", ligado, "o bind não devolve break: a classe Text roda junto")

    def test_desmarcar_o_italico_detectado_carimba_humano(self) -> None:
        """O pincel manual vence a régua da linha, e a corrida passa a `humano` (S-239/S-236)."""
        painel = self._painel()
        painel.desenhar(_pagina(_texto("citação lida em itálico", italico=True)))
        painel.editor.tag_add("sel", "1.0", "1.7")
        painel.italico()
        doc = painel.documento_atual()
        primeira = doc.corridas[0]
        self.assertFalse(primeira.atributos.italico)
        self.assertEqual(primeira.procedencia, "humano")

    def test_o_botao_reflete_o_estado_do_cursor(self) -> None:
        painel = self._painel()
        painel.desenhar(_pagina(_texto("negrito da camada", negrito=True)))
        painel.editor.mark_set("insert", "1.3")
        painel._atualizar_ferramentas()
        self.assertTrue(painel.formato_var["negrito"].get())
        self.assertFalse(painel.formato_var["italico"].get())

    def test_a_cor_do_autor_nao_apaga_a_faixa(self) -> None:
        """Critério de aceite da S-242: "limpar cor" tira a do autor e **não** tira a faixa."""
        painel = self._painel()
        painel.desenhar(_pagina(_texto("adivinhado", 0.1, "glifo")))
        painel.editor.tag_add("sel", "1.0", "1.10")
        painel.pintar_realce("destaque")
        self.assertEqual(painel.documento_atual().corridas[0].atributos.realce, "destaque")
        painel.limpar_cor()
        corrida = painel.documento_atual().corridas[0]
        self.assertEqual(corrida.atributos.realce, "")
        self.assertEqual(corrida.faixa, documento.REVISAR)

    def test_o_txt_nao_carrega_marca_de_cor(self) -> None:
        """O `.txt` é texto puro: um marcador de cor ali seria lixo no arquivo de quem só queria
        colar o texto num e-mail."""
        painel = self._painel()
        painel.desenhar(_pagina(_texto("um trecho pintado")))
        painel.editor.tag_add("sel", "1.0", "1.9")
        painel.pintar_letra("nota")
        self.assertEqual(painel.texto_atual(), "um trecho pintado")

    def test_a_troca_de_tema_repinta_os_dois_canais(self) -> None:
        """Cor de autor e faixa se repintam pelo mesmo caminho -- critério de aceite da S-242."""
        painel = self._painel()
        painel.desenhar(_pagina(_texto("texto")))
        painel._pintar_faixas()
        for nome in texto_cores.nomes():
            with self.subTest(nome=nome):
                etiqueta = texto_cores.etiqueta_de_cor(nome)
                self.assertTrue(str(painel.editor.tag_cget(etiqueta, "foreground")))
        self.assertTrue(str(painel.editor.tag_cget(documento.REVISAR, "foreground")))


class DeslocamentoTests(_ComJanela, unittest.TestCase):
    """A conversão entre índice do Tk e deslocamento do documento (S-241).

    É a fronteira estreita do painel, e o caso que a torna necessária é o diagrama: a miniatura
    conta um caractere para o Tk e zero para o documento, e a quebra que o desenho acrescenta
    embaixo dela não é do documento tampouco.
    """

    def test_o_deslocamento_ignora_o_que_o_desenho_acrescenta(self) -> None:
        pagina = _pagina(
            _texto("antes do diagrama"),
            BlocoDeDiagrama(indice=0, bbox=(0.0, 0.0, 50.0, 50.0)),
            _texto("depois dele"),
        )
        painel = self._painel()
        painel.desenhar(pagina)
        esperado = painel.documento_atual().para_texto()
        self.assertEqual(painel.deslocamento_de("end-1c"), len(esperado))

    def test_a_ida_e_a_volta_se_fecham(self) -> None:
        pagina = _pagina(
            _texto("primeiro bloco"),
            BlocoDeDiagrama(indice=0, bbox=(0.0, 0.0, 50.0, 50.0)),
            _texto("segundo bloco"),
        )
        painel = self._painel()
        painel.desenhar(pagina)
        total = len(painel.documento_atual().para_texto())
        for alvo in range(0, total + 1, 3):
            with self.subTest(alvo=alvo):
                self.assertEqual(painel.deslocamento_de(painel.indice_de(alvo)), alvo)


class PaletaNoWidgetTests(_ComJanela, unittest.TestCase):
    """As três portas de inserção e a marca da S-247, com o widget na mão (S-246 a S-248)."""

    def _com_texto(self, conteudo: str = "1.") -> TextoPanel:
        painel = self._painel()
        painel.desenhar(_pagina(_texto(conteudo)))
        painel.editor.mark_set("insert", "end-1c")
        return painel

    def test_inserir_pelo_painel_poe_o_simbolo_no_cursor(self) -> None:
        painel = self._com_texto()
        painel.inserir_simbolo("♘")
        self.assertTrue(painel.texto_atual().endswith("♘"))

    def test_inserir_fora_do_modelo_marca_a_corrida(self) -> None:
        """Inserir da segunda prateleira é permitido **e sinalizado** -- nunca silencioso."""
        painel = self._com_texto()
        painel.inserir_simbolo("♞")
        marcadas = [c.texto for c in painel.documento_atual().corridas if c.atributos.fora_do_modelo]
        self.assertEqual(marcadas, ["♞"])

    def test_o_que_o_modelo_le_nao_e_marcado(self) -> None:
        painel = self._com_texto()
        painel.inserir_simbolo("♘")
        self.assertFalse(any(c.atributos.fora_do_modelo for c in painel.documento_atual().corridas))

    def test_a_marca_sobrevive_ao_arquivo(self) -> None:
        painel = self._com_texto()
        painel.inserir_simbolo("♞")
        de_volta = arquivo.de_json(arquivo.para_json(painel.documento_atual()))
        self.assertTrue(any(c.atributos.fora_do_modelo for c in de_volta.corridas))

    def test_a_marca_nao_conta_como_correcao(self) -> None:
        """É texto novo, e não leitura corrigida: a S-239 já separa `bloco == -1`."""
        painel = self._painel()
        painel.desenhar(_pagina(_texto("lance lido")))
        painel.editor.mark_set("insert", "end-1c")
        painel.inserir_simbolo("♞")
        doc = painel.documento_atual()
        pares = [(c.antes, c.depois) for c in correcao.correcoes(doc)]
        self.assertNotIn(("", "♞"), pares)

    def test_a_sequencia_de_teclado_fecha_e_vira_simbolo(self) -> None:
        """A barra mais `N` vira `♘` quando a sequência **fecha** -- a segunda porta (S-248)."""
        painel = self._com_texto()
        painel.editor.insert("insert", chr(92) + "N")
        painel._fechar_sequencia()
        self.assertTrue(painel.texto_atual().endswith("♘"))
        self.assertNotIn(chr(92), painel.texto_atual())

    def test_a_barra_sozinha_continua_barra(self) -> None:
        painel = self._com_texto()
        painel.editor.insert("insert", chr(92))
        painel._fechar_sequencia()
        self.assertTrue(painel.texto_atual().endswith(chr(92)))

    def test_a_barra_com_tecla_que_nao_abre_sequencia_devolve_as_duas(self) -> None:
        painel = self._com_texto()
        painel.editor.insert("insert", chr(92) + "Z")
        painel._fechar_sequencia()
        self.assertTrue(painel.texto_atual().endswith(chr(92) + "Z"))

    def test_nada_e_trocado_automaticamente(self) -> None:
        """`Nf3` continua `Nf3`: troca silenciosa sobre texto de OCR é o que a S-209 proíbe."""
        painel = self._com_texto()
        painel.editor.insert("insert", "Nf3")
        painel._fechar_sequencia()
        self.assertTrue(painel.texto_atual().endswith("Nf3"))

    def test_as_tres_entradas_produzem_a_mesma_corrida(self) -> None:
        """Painel, sequência de teclado e comando chegam ao mesmo símbolo com a mesma marca."""
        corridas = []
        for gesto in ("painel", "sequencia", "comando"):
            painel = self._com_texto()
            if gesto == "painel":
                painel.inserir_simbolo("♞")
            elif gesto == "sequencia":
                painel.editor.insert("insert", chr(92) + "n")
                painel._fechar_sequencia()
            else:
                # A porta do comando: `inserir_figurina` abre a lista e chama isto com o escolhido.
                escolhido = [s for s in _paleta.figurinas(painel._paleta) if s == "♞"][0]
                painel.inserir_simbolo(escolhido)
            ultima = painel.documento_atual().corridas[-1]
            corridas.append((ultima.texto, ultima.atributos.fora_do_modelo))
        self.assertEqual(len(set(corridas)), 1, corridas)

    def test_inserir_nao_tira_o_foco_do_editor(self) -> None:
        """O critério de aceite: inserir com o painel aberto não tira a mão do texto (S-248).

        O que se afirma é o **mecanismo**, e não `focus_get`: numa janela retirada da tela o foco de
        teclado é do sistema, e a resposta dele não diz nada sobre o desenho. O mecanismo é
        `takefocus=False` em todo botão da paleta, mais o cursor que continua depois do que se
        inseriu -- é isso que faz a próxima tecla digitar onde se estava.
        """
        painel = self._com_texto()
        painel.alternar_paleta()
        botoes = [
            filho
            for grupo in painel._painel_da_paleta.winfo_children()
            for filho in grupo.winfo_children()
        ]
        self.assertTrue(botoes)
        for botao in botoes[:12]:
            with self.subTest(simbolo=str(botao.cget("text"))):
                self.assertIn(str(botao.cget("takefocus")), ("0", "false", ""))

        painel.inserir_simbolo("♘")
        self.assertEqual(painel.editor.get("insert - 1 chars", "insert"), "♘")

    def test_a_paleta_abre_e_fecha(self) -> None:
        painel = self._com_texto()
        painel.alternar_paleta()
        self.assertIsNotNone(painel._painel_da_paleta)
        painel.alternar_paleta()
        self.assertIsNone(painel._painel_da_paleta)


class EstiloNoWidgetTests(_ComJanela, unittest.TestCase):
    """O estilo desenhado: geometria na etiqueta do estilo, fonte na combinada (S-249)."""

    def test_o_estilo_da_pagina_aparece_sem_ninguem_pedir(self) -> None:
        from chess_diagram_ocr.text.pagina import BlocoDeTarja

        painel = self._painel()
        pagina = _pagina(BlocoDeTarja(linhas=(LinhaLida("CAPÍTULO", (0.0, 0.0, 9.0, 9.0), 1.0, "camada"),)))
        painel.desenhar(pagina)
        self.assertIn("estilo:titulo", painel.editor.tag_names("1.0"))

    def test_aplicar_a_mao_redesenha_com_a_etiqueta(self) -> None:
        painel = self._painel()
        painel.desenhar(_pagina(_texto("uma linha de lances")))
        painel.editor.mark_set("insert", "1.2")
        painel.estilo_notacao()
        self.assertIn("estilo:notacao", painel.editor.tag_names("1.0"))
        self.assertEqual(painel.documento_atual().corridas[0].atributos.estilo, "notacao")

    def test_a_fonte_do_estilo_nao_apaga_o_negrito(self) -> None:
        """No Tk **uma** etiqueta dá a fonte ao trecho: sem a combinada, o negrito de dentro de um
        título sumiria da tela sem sumir do documento."""
        painel = self._painel()
        painel.desenhar(_pagina(_texto("titulo com negrito", negrito=True)))
        painel.editor.mark_set("insert", "1.2")
        painel.estilo_titulo()
        etiquetas = set(painel.editor.tag_names("1.0"))
        self.assertIn("estilo:titulo", etiquetas)
        # O `:0` do fim é o degrau de corpo da S-260: a etiqueta combinada passou a distinguir
        # também o tamanho, senão um título `+1` e um título normal disputariam o mesmo nome.
        self.assertIn("fonte:titulo:b:0", etiquetas)


class FerramentasNoWidgetTests(_ComJanela, unittest.TestCase):
    """As ferramentas da Fase 41 desenhadas: alinhamento, corpo, tachado e caixa (S-259 a S-262).

    O que `tests/test_texto_ferramentas.py` afirma sem janela é o alcance de cada função pura. O que
    só se vê com um `tk.Text` na mão é o **desenho**: que a etiqueta chegou ao widget, que ela
    alcança a imagem do diagrama, e que a ida e volta pelo widget devolve o mesmo documento -- que é
    o achado 1 do ROADMAP_EDITOR, e a única forma de defeito que "na tela está tudo certo".
    """

    def _com_texto(self, conteudo: str = "uma frase para formatar") -> TextoPanel:
        painel = self._painel()
        painel.desenhar(_pagina(_texto(conteudo)))
        return painel

    def test_o_tachado_vira_etiqueta_e_volta_como_atributo(self) -> None:
        painel = self._com_texto()
        painel.editor.mark_set("insert", "1.6")
        painel.tachado()
        self.assertIn("tachado", painel.editor.tag_names("1.5"))
        doc = painel.documento_atual()
        self.assertEqual([c.texto for c in doc.corridas if c.atributos.tachado], ["frase"])

    def test_o_tachado_e_risco_e_nao_fonte(self) -> None:
        """`overstrike` é opção de etiqueta: ela soma com a que dá a fonte em vez de disputá-la."""
        painel = self._com_texto()
        self.assertEqual(str(painel.editor.tag_cget("tachado", "overstrike")), "1")
        self.assertEqual(str(painel.editor.tag_cget("tachado", "font")), "")

    def test_centralizar_poe_a_etiqueta_e_a_justificacao(self) -> None:
        painel = self._com_texto()
        painel.editor.mark_set("insert", "1.2")
        painel.alinhar_centro()
        self.assertIn("alinhamento:centro", painel.editor.tag_names("1.0"))
        self.assertEqual(str(painel.editor.tag_cget("alinhamento:centro", "justify")), "center")

    def test_o_justificado_cai_em_esquerda_na_tela_e_nao_no_documento(self) -> None:
        """A perda é da tela, e ela é declarada: o `tk.Text` não estica espaço entre palavras."""
        painel = self._com_texto()
        painel.editor.mark_set("insert", "1.2")
        painel.justificar()
        self.assertEqual(str(painel.editor.tag_cget("alinhamento:justificado", "justify")), "left")
        self.assertEqual(painel.documento_atual().corridas[0].atributos.alinhamento, "justificado")

    def test_o_alinhamento_sobrevive_a_ida_e_volta_pelo_widget(self) -> None:
        painel = self._com_texto()
        painel.editor.mark_set("insert", "1.2")
        painel.alinhar_direita()
        self.assertEqual(painel.documento_atual().corridas[0].atributos.alinhamento, "direita")

    def _com_diagrama(self) -> TextoPanel:
        """Um painel com uma folha renderizada de mentira, para a miniatura existir."""
        painel = self._painel()
        painel.pack()
        painel._pagina_rgb = np.full((80, 80, 3), 200, dtype=np.uint8)
        painel.desenhar(
            _pagina(
                _texto("antes do diagrama"),
                BlocoDeDiagrama(indice=0, bbox=(0.0, 10.0, 40.0, 50.0), confianca=0.9),
            )
        )
        painel.update()
        return painel

    def test_centralizar_pelo_cursor_na_marca_alcanca_a_miniatura(self) -> None:
        """**O caso que dá nome à fase.**

        Três afirmações, e as três precisam valer juntas para a figura sair da margem:

        1. a etiqueta de alinhamento chega à **imagem**, e não só à marca embaixo dela;
        2. a imagem é o **primeiro item da linha**, que é onde o `-justify` do Tk é lido;
        3. a etiqueta centraliza de fato (`tag_cget`).

        **Não é medido em pixel**, e a razão é da suíte: `bbox` devolve `None` num toplevel
        escondido, e a janela deste módulo é `withdraw`n de propósito. As três acima distinguem o
        caso certo do defeito real -- uma etiqueta que chegasse só à marca passaria num teste de
        `tag_names` e deixaria a imagem encostada na esquerda.
        """
        painel = self._com_diagrama()
        marca = painel.editor.search("[Diagrama", "1.0")
        # O cursor **sobre o `[`**, sem seleção: é onde alguém está quando quer centralizar a
        # figura, e é o caso em que "a palavra sob o cursor" é vazia (`intervalo_de_paragrafo`).
        painel.editor.tag_remove(tk.SEL, "1.0", tk.END)
        painel.editor.mark_set(tk.INSERT, marca)
        painel.alinhar_centro()
        painel.update()

        imagem = painel.editor.dump("1.0", tk.END, image=True)
        self.assertTrue(imagem, "a miniatura não foi desenhada: o teste não mediria nada")
        indice = imagem[0][2]
        self.assertIn("alinhamento:centro", painel.editor.tag_names(indice))
        self.assertEqual(painel.editor.index(f"{indice} linestart"), painel.editor.index(indice))
        self.assertEqual(str(painel.editor.tag_cget("alinhamento:centro", "justify")), "center")
        self.assertIn(
            "alinhamento:centro", painel.editor.tag_names(painel.editor.search("[Diagrama", "1.0"))
        )

    def test_o_cursor_num_caractere_sem_palavra_ainda_alinha_o_paragrafo(self) -> None:
        """`intervalo_alvo` cai na palavra sob o cursor, e fora de uma palavra ela é **vazia**.

        Para o negrito isso é o certo -- não há o que emboldecer num colchete. Para um comando de
        parágrafo é a resposta errada, e era o que fazia "centralizar" com o cursor parado no `[`
        de `[Diagrama 1]` não fazer nada (S-259)."""
        painel = self._com_texto("[nota] uma frase")
        painel.editor.tag_remove(tk.SEL, "1.0", tk.END)
        painel.editor.mark_set(tk.INSERT, "1.0")  # sobre o `[`, que não é letra de palavra
        self.assertEqual(painel.intervalo_alvo(), (0, 0))
        painel.alinhar_centro()
        self.assertEqual(painel.documento_atual().corridas[0].atributos.alinhamento, "centro")

    def test_a_miniatura_nao_leva_as_etiquetas_de_dado(self) -> None:
        """`bloco:` e `proc:` descrevem conteúdo do documento, e a imagem não é conteúdo."""
        painel = self._painel()
        painel._pagina_rgb = np.zeros((60, 60, 3), dtype=np.uint8)
        painel.desenhar(_pagina(BlocoDeDiagrama(indice=0, bbox=(0.0, 0.0, 20.0, 20.0))))
        despejo = painel.editor.dump("1.0", tk.END, image=True)
        self.assertTrue(despejo)
        nomes = set(painel.editor.tag_names(despejo[0][2]))
        self.assertEqual([n for n in nomes if n.startswith(("bloco:", "proc:"))], [])

    def test_aumentar_o_corpo_cria_a_etiqueta_de_fonte_do_degrau(self) -> None:
        painel = self._com_texto()
        painel.editor.mark_set("insert", "1.6")
        painel.aumentar_corpo()
        # `fonte:::1` é `fonte:<estilo>:<peso e pendor>:<degrau>` com os dois primeiros vazios.
        self.assertIn("fonte:::1", painel.editor.tag_names("1.5"))
        self.assertEqual(painel.documento_atual().corridas[1].atributos.corpo, 1)

    def test_o_degrau_nao_se_acumula_a_cada_redesenho(self) -> None:
        """**O defeito que `_fonte_do_trecho` evita**: somar o degrau ao tamanho lido do widget
        faria a fonte crescer sozinha a cada `desenhar_documento`."""
        painel = self._com_texto()
        painel.editor.tag_add("sel", "1.0", "1.3")
        painel.aumentar_corpo()
        primeira = painel.editor.tag_cget("fonte:::1", "font")
        painel.desenhar_documento(painel.documento_atual())
        self.assertEqual(painel.editor.tag_cget("fonte:::1", "font"), primeira)

    def test_o_corpo_para_no_limite_e_o_rodape_diz(self) -> None:
        avisos: list[str] = []
        assert _RAIZ is not None
        painel = TextoPanel(
            _RAIZ,
            pdf_path=lambda: None,
            page_index=lambda: 0,
            on_status=avisos.append,
            busy=BusyRegistry(),
            pasta_de_rascunhos=Path(tempfile.mkdtemp()),
        )
        painel.desenhar(_pagina(_texto("uma palavra")))
        painel.editor.tag_add("sel", "1.0", "1.3")
        for _ in range(rico.CORPO_MAXIMO + 2):
            painel.aumentar_corpo()
        self.assertEqual(painel.documento_atual().corridas[0].atributos.corpo, rico.CORPO_MAXIMO)
        self.assertTrue(any("limite" in mensagem for mensagem in avisos), avisos)

    def test_voltar_ao_normal_desfaz_os_degraus(self) -> None:
        painel = self._com_texto()
        painel.editor.tag_add("sel", "1.0", "1.3")
        painel.aumentar_corpo()
        painel.editor.tag_add("sel", "1.0", "1.3")
        painel.corpo_normal()
        self.assertEqual(painel.documento_atual().corridas[0].atributos.corpo, 0)

    def test_o_degrau_sai_da_fonte_do_editor_e_nao_do_papel_corpo(self) -> None:
        """**O `tk.Text` nasce em `TkFixedFont`, e o papel `CORPO` é outra família e outro corpo.**

        Derivar do papel faria "aumentar" trocar Courier New 10 por Segoe UI 10 -- uma troca de
        família disfarçada de degrau. A afirmação é sobre a família, que é o que denuncia a origem
        errada mesmo quando os tamanhos por acaso coincidem."""
        painel = self._com_texto()
        familia, tamanho = painel._base_do_editor()
        painel.editor.tag_add("sel", "1.0", "1.3")
        painel.aumentar_corpo()
        fonte = str(painel.editor.tag_cget("fonte:::1", "font"))
        self.assertIn(familia, fonte)
        self.assertIn(str(tamanho + 1), fonte)

    def test_a_caixa_muda_o_texto_do_widget(self) -> None:
        painel = self._com_texto()
        painel.editor.mark_set("insert", "1.6")
        painel.maiusculas()
        self.assertEqual(painel.texto_atual(), "uma FRASE para formatar")

    def test_a_troca_de_caixa_e_desfazivel_inteira(self) -> None:
        """Ela redesenha, e o redesenho zera a pilha do Tk: sem o instantâneo, desfazer uma troca
        de caixa seria impossível em vez de ser inteira (o cabeçalho de `ui/texto_panel.py`)."""
        painel = self._com_texto()
        antes = painel.texto_atual()
        painel.editor.tag_add("sel", "1.0", "1.9")
        painel.maiusculas()
        self.assertNotEqual(painel.texto_atual(), antes)
        painel.desfazer()
        self.assertEqual(painel.texto_atual(), antes)

    def test_toda_tecla_do_editor_tem_metodo(self) -> None:
        """`_ligar_teclas` liga por `getattr`: um nome sem método derrubaria a montagem da aba."""
        for acao in atalhos.TECLAS_DO_EDITOR:
            with self.subTest(acao=acao):
                self.assertTrue(callable(getattr(TextoPanel, acao, None)))

    def test_toda_escolha_da_barra_aponta_para_um_comando_do_catalogo(self) -> None:
        """A tabela que ata o nome do domínio ao rótulo da interface, conferida dos dois lados."""
        from chess_diagram_ocr.ui import comandos as catalogo

        self.assertEqual(
            set(texto_panel.COMANDO_DA_ESCOLHA[texto_panel.ALINHAMENTO]), set(rico.ALINHAMENTOS)
        )
        self.assertEqual(set(texto_panel.COMANDO_DA_ESCOLHA[texto_panel.CAIXA]), set(rico.CAIXAS))
        for grupo in texto_panel.COMANDO_DA_ESCOLHA.values():
            for nome, acao in grupo.items():
                with self.subTest(nome=nome):
                    self.assertIn(acao, catalogo.por_acao)


class VistaESelecaoTests(_ComJanela, unittest.TestCase):
    """A Fase 42: seleção, área de transferência, zoom da vista e quebra de linha (S-263 a S-265).

    O que estas quatro têm em comum é **não mexer no documento**. É por isso que quase todo teste
    daqui termina comparando o documento antes com o depois: um zoom que gravasse alguma coisa, ou
    uma quebra de linha que virasse atributo, seriam formatação inventada dentro do arquivo de quem
    corrigiu a página.
    """

    def _com_texto(self, conteudo: str = "uma frase para formatar") -> TextoPanel:
        painel = self._painel()
        painel.desenhar(_pagina(_texto(conteudo)))
        return painel

    def test_selecionar_tudo_pega_a_folha_sem_a_quebra_final(self) -> None:
        """O Tk mantém uma quebra final que não é do documento; incluí-la faria toda ferramenta
        agir sobre um caractere que ninguém escreveu."""
        painel = self._com_texto("uma frase para formatar")
        painel.selecionar_tudo()
        inicio, fim = painel.intervalo_alvo()
        self.assertEqual((inicio, fim), (0, len(painel.documento_atual().para_texto())))

    def test_selecionar_tudo_e_depois_uma_ferramenta_pega_a_folha(self) -> None:
        """É o gesto que o comando existe para servir -- e o que `Ctrl+A` não fazia."""
        painel = self._com_texto("uma frase para formatar")
        painel.selecionar_tudo()
        painel.maiusculas()
        self.assertEqual(painel.texto_atual(), "UMA FRASE PARA FORMATAR")

    def test_copiar_e_colar_passam_pelo_evento_virtual_do_tk(self) -> None:
        """Recortar e colar são o `<<Cut>>`/`<<Paste>>` do Tk, e não uma segunda implementação."""
        painel = self._com_texto("uma frase para formatar")
        painel.editor.tag_remove(tk.SEL, "1.0", tk.END)
        painel.editor.tag_add(tk.SEL, "1.0", "1.3")
        painel.copiar()
        painel.update()
        painel.editor.mark_set(tk.INSERT, "end-1c")
        painel.colar()
        painel.update()
        self.assertTrue(painel.texto_atual().endswith("uma"), painel.texto_atual())

    def test_o_zoom_muda_a_fonte_do_editor_e_nao_o_documento(self) -> None:
        painel = self._com_texto("uma frase para formatar")
        antes_documento = painel.documento_atual()
        antes_fonte = str(painel.editor.cget("font"))
        painel.aproximar_texto()
        painel.update()
        self.assertNotEqual(str(painel.editor.cget("font")), antes_fonte)
        self.assertEqual(painel.documento_atual(), antes_documento)

    def test_o_zoom_parte_sempre_da_fonte_original(self) -> None:
        """**O defeito que `_fonte_original_do_editor` evita**: reler a fonte a cada zoom devolveria
        a já ampliada, e dois cliques dariam +1 e depois +2 sobre o +1."""
        painel = self._com_texto()
        familia, tamanho = painel._fonte_original_do_editor
        painel.aproximar_texto()
        painel.aproximar_texto()
        painel.update()
        self.assertIn(str(tamanho + 2), str(painel.editor.cget("font")))
        painel.zoom_do_texto_normal()
        painel.update()
        self.assertIn(str(tamanho), str(painel.editor.cget("font")))
        self.assertIn(familia, str(painel.editor.cget("font")))

    def test_o_zoom_nao_zera_o_desfazer(self) -> None:
        """Redesenhar zeraria a pilha do Tk, e perder o desfazer da digitação por ter aproximado a
        letra seria uma troca ruim -- por isso `_aplicar_zoom` só reconfigura etiquetas."""
        painel = self._com_texto("uma frase para formatar")
        painel.editor.mark_set(tk.INSERT, "end-1c")
        painel.editor.insert(tk.INSERT, " digitado")
        painel.update()
        painel.aproximar_texto()
        painel.desfazer()
        self.assertNotIn("digitado", painel.texto_atual())

    def test_o_zoom_para_no_limite_e_o_rodape_diz(self) -> None:
        avisos: list[str] = []
        painel = self._painel_com_status(avisos)
        painel.desenhar(_pagina(_texto("uma frase")))
        for _ in range(texto_panel.ZOOM_MAXIMO + 2):
            painel.aproximar_texto()
        self.assertEqual(painel._zoom_da_vista, texto_panel.ZOOM_MAXIMO)
        self.assertTrue(any("limite" in mensagem for mensagem in avisos), avisos)

    def test_a_quebra_troca_o_wrap_e_a_rolagem_horizontal(self) -> None:
        painel = self._com_texto()
        painel.pack()
        painel.update()
        # `winfo_manager` e não `winfo_ismapped`: a janela deste módulo é `withdraw`n, e nela nada
        # é mapeado. O que se afirma é o **empacotamento**, que é o que o comando decide.
        self.assertEqual(str(painel.editor.cget("wrap")), "word")
        self.assertEqual(painel._rolagem_horizontal.winfo_manager(), "")
        painel.quebra_var.set(False)
        painel.quebrar_linha()
        painel.update()
        self.assertEqual(str(painel.editor.cget("wrap")), "none")
        self.assertEqual(painel._rolagem_horizontal.winfo_manager(), "pack")

    def test_a_quebra_nao_entra_no_documento(self) -> None:
        painel = self._com_texto()
        antes = painel.documento_atual()
        painel.quebra_var.set(False)
        painel.quebrar_linha()
        self.assertEqual(painel.documento_atual(), antes)

    def _painel_com_status(self, avisos: list[str]) -> TextoPanel:
        assert _RAIZ is not None
        return TextoPanel(
            _RAIZ,
            pdf_path=lambda: None,
            page_index=lambda: 0,
            on_status=avisos.append,
            busy=BusyRegistry(),
            pasta_de_rascunhos=Path(tempfile.mkdtemp()),
        )


class LexicoNaAbaTests(_ComJanela, unittest.TestCase):
    """O léxico da S-209 conferindo a folha -- e não deixando rastro nenhum (S-266)."""

    def _com_texto(self, conteudo: str) -> TextoPanel:
        painel = self._painel()
        painel.desenhar(_pagina(_texto(conteudo)))
        return painel

    def test_a_palavra_desconhecida_recebe_a_marca(self) -> None:
        painel = self._com_texto("the smdy of the position")
        painel.marcar_fora_do_lexico()
        inicio = painel.indice_de(4)
        self.assertIn(texto_panel.ETIQUETA_DO_LEXICO, painel.editor.tag_names(inicio))

    def test_a_palavra_conhecida_nao_recebe_nada(self) -> None:
        painel = self._com_texto("the smdy of the position")
        painel.marcar_fora_do_lexico()
        inicio = painel.indice_de(painel.documento_atual().para_texto().index("position"))
        self.assertNotIn(texto_panel.ETIQUETA_DO_LEXICO, painel.editor.tag_names(inicio))

    def test_a_marca_do_lexico_nao_entra_no_documento(self) -> None:
        """**O item inteiro numa asserção.** A conferência é derivada do texto e do léxico; gravá-la
        daria um `.cvtxt` com marcas de um léxico que já mudou. Como `corrida_de` ignora etiqueta
        que não conhece, ela atravessa a gravação sem deixar rastro."""
        painel = self._com_texto("the smdy of the position")
        antes = painel.documento_atual()
        painel.marcar_fora_do_lexico()
        self.assertEqual(painel.documento_atual(), antes)

    def test_a_marca_do_diagrama_nao_e_conferida(self) -> None:
        """`[Diagrama 3]` é referência que o programa escreveu: marcá-la seria a aba avisando sobre
        si mesma, em toda folha que tenha diagrama."""
        painel = self._painel()
        painel.desenhar(
            _pagina(
                _texto("the position"),
                BlocoDeDiagrama(indice=2, bbox=(0.0, 0.0, 10.0, 10.0), confianca=0.9),
            )
        )
        painel.marcar_fora_do_lexico()
        marca = painel.editor.search("Diagrama", "1.0")
        self.assertTrue(marca, "a marca não foi desenhada: o teste não mediria nada")
        self.assertNotIn(texto_panel.ETIQUETA_DO_LEXICO, painel.editor.tag_names(marca))

    def test_limpar_tira_todas_as_marcas(self) -> None:
        painel = self._com_texto("the smdy of the position")
        painel.marcar_fora_do_lexico()
        painel.limpar_marcas_do_lexico()
        self.assertEqual(painel.editor.tag_ranges(texto_panel.ETIQUETA_DO_LEXICO), ())

    def test_conferir_de_novo_nao_acumula(self) -> None:
        """Marcar duas vezes tem de dar o mesmo resultado: a segunda limpa antes de marcar."""
        painel = self._com_texto("the smdy of the position")
        painel.marcar_fora_do_lexico()
        uma_vez = painel.editor.tag_ranges(texto_panel.ETIQUETA_DO_LEXICO)
        painel.marcar_fora_do_lexico()
        self.assertEqual(painel.editor.tag_ranges(texto_panel.ETIQUETA_DO_LEXICO), uma_vez)

    def test_a_conta_vai_para_o_rodape(self) -> None:
        """"3 de 412" e "80 de 412" pedem coisas diferentes de quem está conferindo a folha."""
        avisos: list[str] = []
        assert _RAIZ is not None
        painel = TextoPanel(
            _RAIZ,
            pdf_path=lambda: None,
            page_index=lambda: 0,
            on_status=avisos.append,
            busy=BusyRegistry(),
            pasta_de_rascunhos=Path(tempfile.mkdtemp()),
        )
        painel.desenhar(_pagina(_texto("the smdy of the position")))
        painel.marcar_fora_do_lexico()
        self.assertTrue(any("fora do léxico" in mensagem for mensagem in avisos), avisos)


class EstadoNaBarraTests(_ComJanela, unittest.TestCase):
    """A barra diz o que vale sob o cursor -- alinhamento e corpo (S-292).

    A S-241 fixou a regra para os quatro pincéis de ênfase: *"um botão que diz 'negrito' onde o
    texto não é negrito é pior que um botão sem estado nenhum"*. Estes testes a estendem aos dois
    atributos de valor que a Fase 41 acrescentou.
    """

    def _com_texto(self, conteudo: str = "uma frase para formatar") -> TextoPanel:
        painel = self._painel()
        painel.desenhar(_pagina(_texto(conteudo)))
        return painel

    def test_a_lista_marca_o_alinhamento_do_paragrafo(self) -> None:
        painel = self._com_texto()
        self.assertEqual(painel.alinhamento_var.get(), "")
        painel.editor.mark_set(tk.INSERT, "1.2")
        painel.alinhar_centro()
        painel.update()
        self.assertEqual(painel.alinhamento_var.get(), "centro")

    def test_o_alinhamento_e_lido_do_paragrafo_e_nao_da_palavra(self) -> None:
        """O cursor fora de uma palavra num parágrafo centralizado tem de continuar dizendo
        "centro" -- e diria "" se a pergunta fosse sobre `intervalo_alvo` (S-259)."""
        painel = self._com_texto("[nota] uma frase")
        painel.editor.mark_set(tk.INSERT, "1.2")
        painel.alinhar_direita()
        painel.editor.tag_remove(tk.SEL, "1.0", tk.END)
        painel.editor.mark_set(tk.INSERT, "1.0")  # sobre o `[`
        painel._atualizar_ferramentas()
        self.assertEqual(painel.alinhamento_var.get(), "direita")

    def test_o_mostrador_de_corpo_segue_o_cursor(self) -> None:
        painel = self._com_texto()
        painel.editor.tag_add(tk.SEL, "1.0", "1.3")
        painel._atualizar_ferramentas()
        self.assertEqual(painel.corpo_var.get(), "0")
        painel.aumentar_corpo()
        painel.update()
        self.assertEqual(painel.corpo_var.get(), "+1")

    def test_o_mostrador_diz_misto_quando_a_selecao_tem_dois_degraus(self) -> None:
        """`0` é um degrau de verdade, e mostrá-lo onde há dois seria o mostrador afirmando o que
        ele não sabe."""
        painel = self._com_texto("uma frase para formatar")
        painel.editor.tag_add(tk.SEL, "1.0", "1.3")
        painel.aumentar_corpo()
        painel.editor.tag_remove(tk.SEL, "1.0", tk.END)
        painel.editor.tag_add(tk.SEL, "1.0", "1.9")
        painel._atualizar_ferramentas()
        self.assertEqual(painel.corpo_var.get(), texto_panel.ROTULO_DO_CORPO_MISTO)


class VistaGuardadaTests(_ComJanela, unittest.TestCase):
    """O zoom e a quebra sobrevivem ao fechamento da janela (S-291)."""

    def test_restaurar_poe_a_vista_sem_avisar_no_rodape(self) -> None:
        """A janela que abre dizendo "zoom +2" fala de uma coisa que ninguém acabou de fazer."""
        avisos: list[str] = []
        assert _RAIZ is not None
        painel = TextoPanel(
            _RAIZ,
            pdf_path=lambda: None,
            page_index=lambda: 0,
            on_status=avisos.append,
            busy=BusyRegistry(),
            pasta_de_rascunhos=Path(tempfile.mkdtemp()),
        )
        painel.restaurar_vista(zoom=2, quebra=False)
        painel.update()
        self.assertEqual(painel.zoom_da_vista, 2)
        self.assertFalse(bool(painel.quebra_var.get()))
        self.assertEqual(str(painel.editor.cget("wrap")), "none")
        self.assertEqual(avisos, [])

    def test_o_zoom_de_um_arquivo_estragado_e_grampeado(self) -> None:
        """Os limites são desta aba, e é aqui que eles se aplicam -- `ui/state.py` valida só o tipo,
        pela mesma regra que ele já segue para a pele e a geometria."""
        painel = self._painel()
        painel.restaurar_vista(zoom=900)
        self.assertEqual(painel.zoom_da_vista, texto_panel.ZOOM_MAXIMO)
        painel.restaurar_vista(zoom=-900)
        self.assertEqual(painel.zoom_da_vista, texto_panel.ZOOM_MINIMO)


class ConferenciaQueSeRefazTests(_ComJanela, unittest.TestCase):
    """A marcação do léxico se refaz depois do redesenho (S-293)."""

    def _com_erro(self) -> TextoPanel:
        painel = self._painel()
        painel.desenhar(_pagina(_texto("the smdy of the position")))
        return painel

    def test_corrigir_uma_palavra_nao_apaga_as_marcas(self) -> None:
        """**O defeito que o item fecha.** Toda ferramenta que muda texto redesenha, e o redesenho
        apagava a marcação inteira -- então corrigir a primeira palavra marcada apagava as outras,
        que é exatamente o gesto que a conferência existe para servir."""
        painel = self._com_erro()
        painel.marcar_fora_do_lexico()
        self.assertTrue(painel.editor.tag_ranges(texto_panel.ETIQUETA_DO_LEXICO))
        painel.editor.tag_add(tk.SEL, "1.0", "1.3")
        painel.maiusculas()  # muda texto -> redesenha
        painel.update()
        self.assertTrue(
            painel.editor.tag_ranges(texto_panel.ETIQUETA_DO_LEXICO),
            "a marcação não voltou depois do redesenho",
        )

    def test_limpar_desliga_e_o_redesenho_nao_a_traz_de_volta(self) -> None:
        painel = self._com_erro()
        painel.marcar_fora_do_lexico()
        painel.limpar_marcas_do_lexico()
        painel.editor.tag_add(tk.SEL, "1.0", "1.3")
        painel.maiusculas()
        painel.update()
        self.assertEqual(painel.editor.tag_ranges(texto_panel.ETIQUETA_DO_LEXICO), ())

    def test_a_reconferencia_nao_reescreve_o_rodape(self) -> None:
        """A conta já foi dita quando se ligou; repeti-la a cada redesenho esconderia o que a
        ferramenta que acabou de rodar tinha a dizer."""
        avisos: list[str] = []
        assert _RAIZ is not None
        painel = TextoPanel(
            _RAIZ,
            pdf_path=lambda: None,
            page_index=lambda: 0,
            on_status=avisos.append,
            busy=BusyRegistry(),
            pasta_de_rascunhos=Path(tempfile.mkdtemp()),
        )
        painel.desenhar(_pagina(_texto("the smdy of the position")))
        painel.marcar_fora_do_lexico()
        avisos.clear()
        painel.editor.tag_add(tk.SEL, "1.0", "1.3")
        painel.maiusculas()
        painel.update()
        self.assertEqual([a for a in avisos if "léxico" in a], [])

    def test_a_conferencia_continua_fora_do_documento(self) -> None:
        """Refazer-se sozinha não pode ter virado gravação: ela continua derivada (S-266)."""
        painel = self._com_erro()
        painel.marcar_fora_do_lexico()
        antes = painel.documento_atual()
        painel.desenhar_documento(antes)
        self.assertEqual(painel.documento_atual(), antes)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class ZoomComEstiloTests(_ComJanela, unittest.TestCase):
    """O zoom da vista redimensiona **também** o que tem estilo ou corpo (S-336).

    `_aplicar_zoom` refaz a fonte de cada etiqueta de desenho pelo registro `_fontes_desenhadas`, e
    `_pintar_faixas` -- chamado uma linha antes -- **esvazia** esse registro: o laço percorria um
    dicionário vazio. No redesenho o esvaziamento é certo, porque cada corrida volta a pedir a
    etiqueta dela; aqui não há redesenho, e o registro era a única memória de quais existiam.
    """

    def _painel_com_estilo(self):  # noqa: ANN202 - TextoPanel
        painel = self._painel()
        painel.desenhar(_pagina(_texto("um título da folha")))
        painel.editor.tag_add("sel", "1.0", "1.8")
        painel.estilo_titulo()
        return painel

    def _fonte_do_titulo(self, painel) -> str:  # noqa: ANN001
        etiquetas = [nome for nome in painel._fontes_desenhadas if nome.startswith("fonte:titulo")]
        self.assertTrue(etiquetas, "o título tem de ter etiqueta de fonte própria")
        return str(painel.editor.tag_cget(etiquetas[0], "font"))

    def test_o_zoom_muda_a_fonte_do_trecho_com_estilo(self) -> None:
        painel = self._painel_com_estilo()
        antes = self._fonte_do_titulo(painel)

        painel._aplicar_zoom(3, avisar=False)

        self.assertNotEqual(antes, self._fonte_do_titulo(painel))

    def test_o_registro_de_fontes_sobrevive_ao_zoom(self) -> None:
        """Era ele que sumia, e por isso o laço não tinha o que refazer."""
        painel = self._painel_com_estilo()
        antes = set(painel._fontes_desenhadas)

        painel._aplicar_zoom(2, avisar=False)

        self.assertTrue(antes)
        self.assertEqual(antes, set(painel._fontes_desenhadas))


class CorDaAbaTests(_ComJanela, unittest.TestCase):
    """A aba segue a pele e o tema, como as outras superfícies da janela (S-337)."""

    def test_as_faixas_saem_do_tema_em_uso(self) -> None:
        """`tokens.cor(papel)` sem estilo devolve a **reserva clara**, e é o que a aba usava."""
        from chess_diagram_ocr.ui import texto_panel as modulo
        from chess_diagram_ocr.ui import theme

        painel = self._painel()
        painel.desenhar(_pagina(_texto("um trecho")))
        faixa, papel = next((f, p) for f, p in modulo.PAPEL_DA_FAIXA.items() if p)

        self.assertEqual(str(painel.editor.tag_cget(faixa, "foreground")), theme.cor_atual(papel))

    def test_a_aba_se_registra_para_repintar(self) -> None:
        """Sem o registro, trocar de pele deixaria a aba na cor de quando ela nasceu."""
        from chess_diagram_ocr.ui import theme

        chamadas: list[int] = []
        painel = self._painel()
        painel._pintar_faixas = lambda: chamadas.append(1)  # type: ignore[method-assign]

        theme.repintar()

        self.assertTrue(chamadas, "a aba não está na lista de repintura de `ui/theme.py`")


class JanelaDeBuscaTests(_ComJanela, unittest.TestCase):
    """A caixa de achar e substituir responde ao teclado (S-342).

    Ela tinha os dois botões e nenhuma tecla: `Enter` no campo não fazia nada, e fechá-la exigia o
    X do título. As duas ligações são no `Toplevel` inteiro -- a lista e o campo de substituir
    também recebem foco, e uma tecla que funciona num widget e não no vizinho é pior que nenhuma.
    """

    def _com_busca(self):  # noqa: ANN202 - (painel, janela)
        painel = self._painel()
        painel.desenhar(_pagina(_texto("a, b, c")))
        painel.achar()
        janela = painel._janela_de_busca
        self.assertIsNotNone(janela)
        return painel, janela

    def test_enter_acha(self) -> None:
        _painel, janela = self._com_busca()
        janela.agulha_var.set(",")

        janela._ao_teclar_enter()

        self.assertEqual(len(janela._achadas), 2)

    def test_enter_nao_substitui(self) -> None:
        """A troca continua exigindo o botão: é a ação destrutiva desta janela."""
        painel, janela = self._com_busca()
        janela.agulha_var.set(",")
        janela.novo_var.set(";")

        janela._ao_teclar_enter()

        self.assertEqual(painel.texto_atual(), "a, b, c")

    def test_esc_fecha(self) -> None:
        _painel, janela = self._com_busca()

        janela._ao_teclar_esc()

        self.assertFalse(janela.winfo_exists())

    def test_as_teclas_estao_ligadas_na_janela_inteira(self) -> None:
        """Ligadas só no campo, elas não valeriam na lista nem na caixa de substituir."""
        _painel, janela = self._com_busca()
        for sequencia in ("<Return>", "<Escape>"):
            with self.subTest(tecla=sequencia):
                self.assertTrue(janela.bind(sequencia), f"{sequencia} não está ligada no Toplevel")


class SalvarEUmCaminhoSoTests(_ComJanela, unittest.TestCase):
    """"Salvar" grava onde já se escolheu; "Salvar como…" é quem pergunta (S-343).

    Os dois comandos existiam no catálogo, no menu e na paleta, e **faziam a mesma coisa**: os dois
    abriam o diálogo. Num ciclo de correção, em que se grava a cada trecho conferido, o diálogo
    repetido é o atrito -- e o rótulo "como…" prometia uma escolha que o outro tomava igual.
    """

    def _painel_com_texto(self):  # noqa: ANN202 - TextoPanel
        painel = self._painel()
        painel.desenhar(_pagina(_texto("uma folha corrigida")))
        return painel

    def _responder(self, destino: Path) -> list[int]:
        from tkinter import filedialog

        perguntas: list[int] = []
        original = filedialog.asksaveasfilename

        def falso(**_kwargs: object) -> str:
            perguntas.append(1)
            return str(destino)

        filedialog.asksaveasfilename = falso  # type: ignore[assignment]
        self.addCleanup(setattr, filedialog, "asksaveasfilename", original)
        return perguntas

    def test_a_primeira_gravacao_pergunta_e_a_segunda_nao(self) -> None:
        painel = self._painel_com_texto()
        destino = Path(tempfile.mkdtemp()) / "folha.cvtxt"
        perguntas = self._responder(destino)

        painel.salvar_documento()
        painel.salvar_documento()

        self.assertEqual(len(perguntas), 1, "a segunda gravação perguntou de novo")
        self.assertTrue(destino.exists())

    def test_salvar_como_pergunta_sempre(self) -> None:
        painel = self._painel_com_texto()
        destino = Path(tempfile.mkdtemp()) / "folha.cvtxt"
        perguntas = self._responder(destino)

        painel.salvar_documento()
        painel.salvar_documento_como()

        self.assertEqual(len(perguntas), 2)

    def test_documento_novo_volta_a_perguntar(self) -> None:
        """Outra folha é outro arquivo: gravar nela é a primeira vez dela."""
        painel = self._painel_com_texto()
        destino = Path(tempfile.mkdtemp()) / "folha.cvtxt"
        perguntas = self._responder(destino)
        painel.salvar_documento()

        painel.abrir(rico.de_texto("outro documento"))
        painel.salvar_documento()

        self.assertEqual(len(perguntas), 2)


class BarraDeFormatoSegueOCursorTests(_ComJanela, unittest.TestCase):
    """Os interruptores acompanham o cursor movido por tecla (S-344).

    Eram duas setas ligadas, e o cursor anda de seis maneiras: descer uma linha de um título para a
    prosa deixava "Título" aceso, e o clique seguinte decidia pelo estado errado.
    """

    def test_as_seis_teclas_de_navegacao_atualizam_a_barra(self) -> None:
        painel = self._painel()
        painel.desenhar(_pagina(_texto("primeira linha")))
        ligadas = painel.editor.bind()

        for tecla in ("<KeyRelease-Up>", "<KeyRelease-Down>", "<KeyRelease-Home>",
                      "<KeyRelease-End>", "<KeyRelease-Prior>", "<KeyRelease-Next>"):
            with self.subTest(tecla=tecla):
                self.assertIn(tecla, ligadas)
