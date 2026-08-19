"""Campo de caminho e campo de número: o erro que aparece ao digitar (S-168).

**Nos dois defeitos o erro chegava tarde.** Os três caminhos da aba Configuração eram `Entry` de
texto livre, sem botão "Procurar…" e sem verificação — num programa que usa `filedialog` em
cinco outros lugares. Um caractere errado no caminho do modelo não aparecia ali: aparecia como
falha na hora do OCR, minutos depois, com uma mensagem sobre outra coisa.

E o `Learning rate` era um `Entry` ligado a um `DoubleVar`: uma letra digitada fazia o `get()`
levantar `TclError` **na hora de treinar**. O erro saía do campo errado, no momento errado, e o
traço apontava para o treino.

As duas decisões são puras e injetáveis — `existe` no caminho, o intervalo no número —, e é o
que permite afirmar "não existe" sem tocar o disco e "fora da faixa" sem abrir janela.
"""

from __future__ import annotations

import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk

from tk_root import raiz

from chess_diagram_ocr.ui import campos
from chess_diagram_ocr.ui.campos import ARQUIVO, PASTA, diagnosticar_caminho, numero_na_faixa


class DiagnosticoDeCaminhoTests(unittest.TestCase):
    """As três respostas, e cada uma importa por um motivo diferente."""

    def test_o_caminho_que_existe_nao_diz_nada(self) -> None:
        """Um campo certo não precisa de rótulo confirmando que está certo."""
        resultado = diagnosticar_caminho("modelo.pt", tipo=ARQUIVO, existe=lambda _: True)
        self.assertTrue(resultado)
        self.assertEqual(resultado.mensagem, "")

    def test_vazio_e_configuracao_incompleta_e_nao_erro(self) -> None:
        for cru in ("", "   "):
            with self.subTest(cru=cru):
                resultado = diagnosticar_caminho(cru, existe=lambda _: True)
                self.assertFalse(resultado)
                self.assertIn("não configurado", resultado.mensagem)

    def test_o_caminho_que_nao_existe_e_dito_na_hora(self) -> None:
        """É o erro que hoje só aparece na hora do OCR, com uma mensagem sobre outra coisa."""
        resultado = diagnosticar_caminho("modelo.pt", existe=lambda _: False)
        self.assertFalse(resultado)
        self.assertIn("não existe", resultado.mensagem)

    def test_o_diagnostico_e_verdadeiro_ou_falso_como_um_booleano(self) -> None:
        """`if not diagnosticar_caminho(...)` tem de funcionar: é como o painel o usa."""
        self.assertTrue(bool(diagnosticar_caminho("x", existe=lambda _: True)))
        self.assertFalse(bool(diagnosticar_caminho("", existe=lambda _: True)))

    def test_o_caminho_e_lido_sem_espaco_em_volta(self) -> None:
        vistos: list[Path] = []

        def existe(alvo: Path) -> bool:
            vistos.append(alvo)
            return True

        diagnosticar_caminho("  modelo.pt  ", existe=existe)
        self.assertEqual(vistos, [Path("modelo.pt")])


class TipoDoCaminhoTests(unittest.TestCase):
    """Apontar a pasta de amostras para o CSV é o engano frequente, e ele era ilegível."""

    def setUp(self) -> None:
        import shutil
        import tempfile

        self.pasta = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.pasta, True)
        self.arquivo = self.pasta / "labels.csv"
        self.arquivo.write_text("filename,fen\n", encoding="utf-8")

    def test_uma_pasta_onde_se_espera_arquivo(self) -> None:
        resultado = diagnosticar_caminho(str(self.pasta), tipo=ARQUIVO)
        self.assertFalse(resultado)
        self.assertIn("pasta", resultado.mensagem)

    def test_um_arquivo_onde_se_espera_pasta(self) -> None:
        resultado = diagnosticar_caminho(str(self.arquivo), tipo=PASTA)
        self.assertFalse(resultado)
        self.assertIn("arquivo", resultado.mensagem)

    def test_cada_um_no_seu_lugar_passa(self) -> None:
        self.assertTrue(diagnosticar_caminho(str(self.arquivo), tipo=ARQUIVO))
        self.assertTrue(diagnosticar_caminho(str(self.pasta), tipo=PASTA))


class NumeroTests(unittest.TestCase):
    """O que o `DoubleVar` não sabia responder: "isto é um número?" antes de ser lido."""

    def _faixa(self, texto: str):
        return numero_na_faixa(texto, minimo=1e-6, maximo=1.0)

    def test_o_valor_tipico_passa(self) -> None:
        self.assertTrue(self._faixa("0.001"))

    def test_uma_letra_e_dita_na_hora_em_vez_de_levantar_no_treino(self) -> None:
        resultado = self._faixa("0.00a1")
        self.assertFalse(resultado)
        self.assertIn("não é um número", resultado.mensagem)

    def test_a_virgula_decimal_de_pt_br_e_aceita(self) -> None:
        """A janela é pt-BR e o teclado é pt-BR: recusar a vírgula é recusar o teclado."""
        self.assertTrue(self._faixa("0,001"))

    def test_fora_da_faixa_diz_qual_e_a_faixa(self) -> None:
        """"Inválido" sozinho manda a pessoa adivinhar; o intervalo é a informação que falta."""
        resultado = self._faixa("5")
        self.assertFalse(resultado)
        self.assertIn("1e-06", resultado.mensagem)
        self.assertIn("1", resultado.mensagem)

    def test_vazio_negativo_e_zero(self) -> None:
        self.assertIn("não preenchido", self._faixa("").mensagem)
        self.assertFalse(self._faixa("-0.5"))
        self.assertFalse(self._faixa("0"), "zero está fora da faixa de um learning rate")

    def test_os_extremos_da_faixa_entram(self) -> None:
        self.assertTrue(numero_na_faixa("1", minimo=0.0, maximo=1.0))
        self.assertTrue(numero_na_faixa("0", minimo=0.0, maximo=1.0))


class LinhaDeCaminhoTests(unittest.TestCase):
    """O widget: o botão grava na variável, e o aviso acompanha o que se digita."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.host = tk.Frame(self.root)
        self.addCleanup(self.host.destroy)
        self.var = tk.StringVar(value="")
        self.escolhido = ""

    def _linha(self, tipo: str = ARQUIVO) -> ttk.Frame:
        return campos.linha_de_caminho(
            self.host, "Modelo (.pt)", self.var, tipo=tipo, escolher=lambda: self.escolhido
        )

    def _aviso(self, linha: ttk.Frame) -> str:
        rotulos = [filho for filho in linha.winfo_children() if isinstance(filho, ttk.Label)]
        return str(rotulos[-1].cget("text"))

    def _botao(self, linha: ttk.Frame) -> ttk.Button:
        return next(filho for filho in linha.winfo_children() if isinstance(filho, ttk.Button))

    def test_o_botao_procurar_existe(self) -> None:
        """Ele não existia, num programa que usa `filedialog` em cinco outros lugares."""
        self.assertEqual(str(self._botao(self._linha()).cget("text")), "Procurar…")

    def test_o_botao_grava_o_que_o_dialogo_devolveu(self) -> None:
        linha = self._linha()
        self.escolhido = "C:/modelos/piece_classifier.pt"
        self._botao(linha).invoke()
        self.assertEqual(self.var.get(), self.escolhido)

    def test_cancelar_o_dialogo_nao_apaga_o_caminho(self) -> None:
        """Cancelar devolve string vazia; apagar transformaria um "deixa pra lá" numa perda."""
        self.var.set("modelo.pt")
        linha = self._linha()
        self.escolhido = ""
        self._botao(linha).invoke()
        self.assertEqual(self.var.get(), "modelo.pt")

    def test_o_aviso_nasce_dizendo_que_falta_configurar(self) -> None:
        self.assertIn("não configurado", self._aviso(self._linha()))

    def test_o_aviso_acompanha_o_que_se_digita(self) -> None:
        """A metade que faz a decisão pura valer: sem ela, ela existiria e não seria vista."""
        linha = self._linha()
        self.var.set("caminho/que/nao/existe.pt")
        self.host.update_idletasks()
        self.assertIn("não existe", self._aviso(linha))

    def test_um_caminho_valido_limpa_o_aviso(self) -> None:
        linha = self._linha()
        self.var.set(str(Path(__file__)))
        self.host.update_idletasks()
        self.assertEqual(self._aviso(linha), "")

    def test_o_campo_de_caminho_e_monoespacado(self) -> None:
        """Caminho é dado (S-149), e é onde `l`, `1` e `I` se confundem."""
        from chess_diagram_ocr.ui import theme, tipografia

        linha = self._linha()
        campo = next(filho for filho in linha.winfo_children() if isinstance(filho, ttk.Entry))
        self.assertIn(str(theme.fonte_atual(tipografia.DADO)[0]), str(campo.cget("font")))


class LinhaDeNumeroTests(unittest.TestCase):
    """O `Learning rate` avisa na tecla seguinte, e não dentro do treino."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.host = tk.Frame(self.root)
        self.addCleanup(self.host.destroy)
        self.var = tk.StringVar(value="0.001")
        self.linha = campos.linha_de_numero(self.host, "Learning rate", self.var, minimo=1e-6, maximo=1.0)

    def _aviso(self) -> str:
        rotulos = [filho for filho in self.linha.winfo_children() if isinstance(filho, ttk.Label)]
        return str(rotulos[-1].cget("text"))

    def test_o_valor_valido_nao_gera_aviso(self) -> None:
        self.assertEqual(self._aviso(), "")

    def test_uma_letra_avisa_na_hora(self) -> None:
        self.var.set("0.00a1")
        self.host.update_idletasks()
        self.assertIn("não é um número", self._aviso())

    def test_voltar_a_um_valor_valido_limpa_o_aviso(self) -> None:
        """Um aviso que não some faz a pessoa desconfiar de um campo que já está certo."""
        self.var.set("abc")
        self.host.update_idletasks()
        self.var.set("0.01")
        self.host.update_idletasks()
        self.assertEqual(self._aviso(), "")


class JanelaTests(unittest.TestCase):
    """A ligação com a aba Configuração, e a conversão que deixou de levantar."""

    def _fonte(self) -> str:
        return (Path(__file__).resolve().parents[1] / "app_tkinter.py").read_text(encoding="utf-8")

    def test_os_tres_caminhos_usam_a_linha_de_caminho(self) -> None:
        fonte = self._fonte()
        for rotulo in ("Modelo (.pt)", "CSV labels", "Pasta samples"):
            with self.subTest(rotulo=rotulo):
                self.assertIn(f'campos.linha_de_caminho(cfg_tab, "{rotulo}"', fonte)

    def test_a_pasta_de_amostras_e_declarada_como_pasta(self) -> None:
        self.assertIn("tipo=campos.PASTA", self._fonte())

    def test_o_learning_rate_deixou_de_ser_doublevar(self) -> None:
        """Era ele que levantava `TclError` dentro do treino, com o traço apontando para lá."""
        fonte = self._fonte()
        self.assertNotIn("self.lr_var = tk.DoubleVar", fonte)
        self.assertIn("self.lr_var = tk.StringVar", fonte)
        self.assertIn("lr=self._train_lr()", fonte)


if __name__ == "__main__":
    unittest.main()
