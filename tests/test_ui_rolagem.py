"""A aba que rola: o botão que existe volta a ser alcançável (S-150, segunda metade).

**O defeito não gera erro — gera um usuário que não sabe que existe um botão.** Em 1100×760 com
a aba Resultado aberta, a fila de ações do rodapé é cortada ao meio pela borda inferior e não há
rolagem que a alcance. `Ctrl+S` continua salvando, e é isso que torna o defeito difícil de ver.

O teste é de três naturezas, e a terceira é a que fecha o item:

- as duas decisões são **puras** e afirmadas nos três regimes (sobra, empata, falta);
- o widget é exercitado com Tk: a barra aparece quando falta, some quando sobra;
- e o critério de aceite é dirigido — a janela vai a **1366×768**, que é a resolução em que o
  piso da primeira metade não cabia, e o teste pergunta se o último botão da fila chega ao
  viewport. É a pergunta que a fotografia da avaliação fez, escrita como asserção.
"""

from __future__ import annotations

import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk

from tk_root import raiz

from chess_diagram_ocr.ui import geometria, rolagem
from chess_diagram_ocr.ui.rolagem import AbaRolavel, aba_rolavel, altura_do_conteudo, precisa_de_barra


class DecisaoTests(unittest.TestCase):
    """Os três regimes. Sem Tk, e é o que faz o critério caber num `assertEqual`."""

    def test_a_barra_aparece_so_quando_falta_espaco(self) -> None:
        self.assertFalse(precisa_de_barra(pedida=400, viewport=800), "sobra: barra anunciaria rolagem que não há")
        self.assertFalse(precisa_de_barra(pedida=800, viewport=800), "empata: cabe exatamente")
        self.assertTrue(precisa_de_barra(pedida=1200, viewport=800), "falta: é o caso fotografado")

    def test_o_conteudo_nunca_encolhe_abaixo_do_viewport(self) -> None:
        """A linha que separa "rolável" de "quebrado".

        Dentro de um canvas, `expand=True` deixa de significar "cresça até a janela": o
        contêiner não tem altura própria. Sem este piso o tabuleiro do Resultado encolheria para
        o tamanho pedido pelo `tk.Canvas` mesmo com a janela em 1080 — o item consertaria a
        janela pequena estragando a grande.
        """
        self.assertEqual(altura_do_conteudo(pedida=400, viewport=800), 800)
        self.assertEqual(altura_do_conteudo(pedida=800, viewport=800), 800)
        self.assertEqual(altura_do_conteudo(pedida=1200, viewport=800), 1200)

    def test_as_duas_decisoes_concordam(self) -> None:
        """Barra visível se e somente se o conteúdo passou do viewport. Sem terceiro estado."""
        for pedida in (0, 100, 799, 800, 801, 5000):
            with self.subTest(pedida=pedida):
                excedeu = altura_do_conteudo(pedida, 800) > 800
                self.assertEqual(excedeu, precisa_de_barra(pedida, 800))


class AbaRolavelTests(unittest.TestCase):
    """O widget. A barra entra e sai; o conteúdo curto continua preenchendo a aba."""

    def setUp(self) -> None:
        # Uma janela de verdade, e não um `Frame` na raiz: a raiz do processo fica `withdraw`n,
        # e widget não mapeado devolve altura 1 em `winfo_height` -- o teste passaria medindo
        # nada. É o mesmo motivo de os testes daqui chamarem `update()` e não só
        # `update_idletasks()`: sem processar o evento de mapeamento, `ttk.Notebook` não
        # distribui espaço para as abas.
        self.host = tk.Toplevel(raiz())
        self.host.geometry("400x300")
        self.addCleanup(self.host.destroy)

    def _aba(self, altura_do_recheio: int) -> AbaRolavel:
        aba = AbaRolavel(self.host)
        aba.pack(fill=tk.BOTH, expand=True)
        recheio = tk.Frame(aba.conteudo, height=altura_do_recheio, width=200)
        recheio.pack_propagate(False)
        recheio.pack(fill=tk.X)
        self.host.update()
        return aba

    def test_conteudo_alto_ganha_barra_e_regiao_rolavel(self) -> None:
        aba = self._aba(altura_do_recheio=1200)
        self.assertTrue(aba._barra.winfo_ismapped(), "a barra não entrou com 1200 px em 300")
        _, _, _, fundo = (float(valor) for valor in str(aba.canvas.cget("scrollregion")).split())
        self.assertGreaterEqual(fundo, 1200)

    def test_conteudo_curto_nao_ganha_barra(self) -> None:
        """Barra permanente rouba ~17 px de um painel cujo `minsize` é 420, e mente sobre rolagem."""
        aba = self._aba(altura_do_recheio=50)
        self.assertFalse(aba._barra.winfo_ismapped())

    def test_conteudo_curto_continua_preenchendo_a_aba(self) -> None:
        """O regime que uma rolagem malfeita quebra: a aba grande com pouco conteúdo.

        A janela do produto passa a maior parte do tempo aqui, e é o caso em que a rolagem não
        pode ser notada de forma nenhuma.
        """
        aba = self._aba(altura_do_recheio=50)
        self.assertEqual(aba.conteudo.winfo_height(), aba.canvas.winfo_height())
        self.assertEqual(aba.conteudo.winfo_width(), aba.canvas.winfo_width())

    def test_a_barra_entra_e_sai_conforme_o_espaco(self) -> None:
        """Arrastar o divisor não pode deixar a barra presa num dos dois estados."""
        aba = AbaRolavel(self.host)
        aba.pack(fill=tk.BOTH, expand=True)
        recheio = tk.Frame(aba.conteudo, height=1200, width=200)
        recheio.pack_propagate(False)
        recheio.pack(fill=tk.X)
        self.host.update()
        self.assertTrue(aba._barra.winfo_ismapped())

        recheio.configure(height=40)
        self.host.update()
        self.assertFalse(aba._barra.winfo_ismapped(), "a barra ficou presa depois de o conteúdo encolher")

    def test_a_roda_nao_e_engolida_quando_nao_ha_o_que_rolar(self) -> None:
        """Sem barra, devolver `"break"` engoliria a roda de quem estivesse por baixo.

        É a diferença entre "esta aba não rola" e "a roda parou de funcionar nesta aba".
        """
        aba = self._aba(altura_do_recheio=50)
        evento = tk.Event()
        evento.x_root, evento.y_root, evento.delta = (
            aba.canvas.winfo_rootx() + 5,
            aba.canvas.winfo_rooty() + 5,
            120,
        )
        self.assertIsNone(aba._na_roda(evento))

    def test_a_roda_rola_quando_ha_barra_e_o_ponteiro_esta_sobre_a_aba(self) -> None:
        aba = self._aba(altura_do_recheio=1200)
        evento = tk.Event()
        evento.x_root, evento.y_root, evento.delta = (
            aba.canvas.winfo_rootx() + 5,
            aba.canvas.winfo_rooty() + 5,
            -120,
        )
        self.assertEqual(aba._na_roda(evento), "break")
        aba.update()
        self.assertGreater(aba.canvas.yview()[0], 0.0, "a roda não moveu a vista")

    def test_a_roda_fora_do_retangulo_nao_e_desta_aba(self) -> None:
        """Duas abas roláveis e o visualizador de PDF dividem o `bind_all`: cada um checa o seu."""
        aba = self._aba(altura_do_recheio=1200)
        evento = tk.Event()
        evento.x_root, evento.y_root, evento.delta = (
            aba.canvas.winfo_rootx() - 500,
            aba.canvas.winfo_rooty() - 500,
            120,
        )
        self.assertIsNone(aba._na_roda(evento))


class CriterioDeAceiteTests(unittest.TestCase):
    """A pergunta da avaliação, dirigida: numa aba mais alta que a janela, a fila de salvar é
    alcançável?

    A janela vai a **1366×768** porque é a resolução que o item nomeia — a do notebook em que o
    piso de 800 de altura da primeira metade não cabe. O empilhamento é o da aba Resultado
    (tabuleiro, legalidade, FEN, lado a jogar, fila de ações) com o **recheio dimensionado a
    partir do viewport medido**, e não de um número escolhido: o que se está afirmando é a
    propriedade "conteúdo maior que a aba continua alcançável", e ela não pode depender de a
    máquina do teste ter a mesma barra de título da máquina da fotografia.

    Os dois testes são um par: o segundo mostra que o **mesmo** empilhamento numa aba comum
    termina abaixo da borda, que é o estado anterior ao item.
    """

    ALTURA_DA_TELA = 768
    LARGURA_DA_TELA = 1366
    SOBRA_ALEM_DO_VIEWPORT = 300
    """Quanto o conteúdo passa da aba. Qualquer valor positivo serve; 300 é uma fila e meia."""

    def setUp(self) -> None:
        self.janela = tk.Toplevel(raiz())
        self.addCleanup(self.janela.destroy)
        self.janela.geometry(f"{self.LARGURA_DA_TELA}x{self.ALTURA_DA_TELA}")
        self.cadernos = ttk.Notebook(self.janela)
        self.cadernos.pack(fill=tk.BOTH, expand=True)

    def _fila_de_acoes(self, pai: tk.Misc, altura_do_tabuleiro: int) -> ttk.Button:
        """O empilhamento da aba Resultado, e o último botão da fila do rodapé."""
        tabuleiro = tk.Frame(pai, height=altura_do_tabuleiro, width=300)
        tabuleiro.pack_propagate(False)
        tabuleiro.pack(fill=tk.X)
        for texto in ("Legalidade", "FEN", "Lado a jogar"):
            ttk.Label(pai, text=texto).pack(anchor="w")
        fila = ttk.Frame(pai)
        fila.pack(fill=tk.X)
        ultimo = None
        for texto in ("Aplicar FEN", "Salvar posição reconhecida", "Salvar todos", "Corrigir Net", "2ª opinião"):
            ultimo = ttk.Button(fila, text=texto)
            ultimo.pack(side=tk.LEFT)
        assert ultimo is not None
        return ultimo

    def _altura_que_nao_cabe(self, viewport: int) -> int:
        return max(1, viewport + self.SOBRA_ALEM_DO_VIEWPORT)

    @staticmethod
    def _inteiramente_visivel(widget: tk.Misc, topo: int, fundo: int) -> bool:
        """Se o widget está na tela **inteiro**, entre `topo` e `fundo` (coordenadas de raiz).

        "Alcançável" não é "existe": o `pack` do Tk, quando falta espaço, dá altura **zero** ao
        que sobrou em vez de recusar o empacotamento. O botão continua sendo um widget, continua
        respondendo a `invoke()` -- e não está na tela. É exatamente esse o defeito da S-150, e
        medir só a coordenada de baixo não o pega.
        """
        if not widget.winfo_ismapped() or widget.winfo_height() <= 1:
            return False
        return topo <= widget.winfo_rooty() and widget.winfo_rooty() + widget.winfo_height() <= fundo

    def test_a_fila_de_salvar_e_alcancavel_numa_aba_menor_que_o_conteudo(self) -> None:
        alvo = aba_rolavel(self.cadernos, "Resultado")
        aba = alvo.master.master  # canvas -> AbaRolavel; é quem tem o viewport
        assert isinstance(aba, AbaRolavel)
        self.janela.update()

        botao = self._fila_de_acoes(alvo, self._altura_que_nao_cabe(aba.canvas.winfo_height()))
        self.janela.update()
        self.assertTrue(aba._barra.winfo_ismapped(), "o conteúdo coube: o teste não está medindo o item")

        topo = aba.canvas.winfo_rooty()
        fundo = topo + aba.canvas.winfo_height()
        self.assertFalse(self._inteiramente_visivel(botao, topo, fundo), "sem rolar, o botão já estaria na tela")

        aba.canvas.yview_moveto(1.0)
        self.janela.update()
        self.assertTrue(
            self._inteiramente_visivel(botao, topo, fundo),
            f"o botão está em {botao.winfo_rooty()}+{botao.winfo_height()} e o viewport vai de {topo} a {fundo}",
        )

    def test_sem_rolagem_o_mesmo_conteudo_fica_cortado(self) -> None:
        """O controle. Sem ele, o teste acima passaria mesmo que a aba coubesse por acaso."""
        comum = ttk.Frame(self.cadernos)
        self.cadernos.add(comum, text="Resultado")
        self.janela.update()

        botao = self._fila_de_acoes(comum, self._altura_que_nao_cabe(comum.winfo_height()))
        self.janela.update()

        topo = comum.winfo_rooty()
        self.assertFalse(
            self._inteiramente_visivel(botao, topo, topo + comum.winfo_height()),
            "a aba comum coube: o controle deixou de controlar",
        )


class PisoEDocumentoTests(unittest.TestCase):
    """As duas metades da S-150 agora existem, e o documento do piso não pode dizer o contrário.

    O docstring de `PISO_MEDIDO` registrava o item **pela metade**, com todas as letras: "quem
    fecha a lacuna é a segunda metade da S-150, que não foi entregue". Um documento que sobrevive
    ao próprio defeito é a família de apodrecimento que a S-134 catalogou.
    """

    def test_o_piso_continua_saindo_da_soma_dos_paineis(self) -> None:
        self.assertEqual(geometria.piso_da_janela(420, 520), geometria.PISO_MEDIDO)

    def test_o_documento_do_piso_nao_diz_mais_que_falta_a_rolagem(self) -> None:
        # O docstring de atributo de módulo não existe em execução: a asserção é sobre o texto.
        texto = Path(geometria.__file__).read_text(encoding="utf-8")
        self.assertNotIn("não foi entregue", texto)
        self.assertIn("ui/rolagem.py", texto)

    def test_o_modulo_de_rolagem_e_o_que_o_piso_referencia(self) -> None:
        self.assertTrue(hasattr(rolagem, "aba_rolavel"))


if __name__ == "__main__":
    unittest.main()
