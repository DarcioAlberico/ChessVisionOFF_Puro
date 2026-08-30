"""A hierarquia de botão que existia e não pintava (S-444 a S-446).

**O achado, e ele é de correção e não de gosto.** A S-144 criou três papéis de botão e o
resultado ficou de pé por baixo: sob `bootstrap-light` -- o tema da pele clássica, que é a padrão
-- `primary.TButton` e `danger.TButton` pintavam o **mesmo** `#f0f0f0` do botão neutro. "Remover",
que apaga linha do `labels.csv`, era o cinza de "Copiar legenda", e a S-76 é o registro do que
isso custa: 1.405 diagramas sobrescritos por um clique.

**O `lookup` não é testemunha aqui, e é o que este arquivo faz diferente.**
`style.lookup("primary.TButton", "background")` devolve o valor do `TButton` base nos **dois**
temas -- inclusive no escuro, onde a face é visivelmente azul. Quem responde é o pixel do widget
montado, e é por isso que estes testes fotografam.
"""

from __future__ import annotations

import time
import tkinter as tk
import unittest
from tkinter import ttk

from PIL import ImageGrab
from tk_root import raiz

from chess_diagram_ocr.ui import estilos, pele, theme, tokens


def _hexa(px: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*px)


class PaletaDaEnfaseTests(unittest.TestCase):
    """A parte pura: os três papéis novos, sem abrir janela."""

    PAPEIS = (tokens.BOTAO_PRIMARIO, tokens.BOTAO_DESTRUTIVO)

    def test_os_tres_papeis_novos_tem_reserva_e_valor_de_cromo_escuro(self) -> None:
        for papel in (*self.PAPEIS, tokens.TEXTO_SOBRE_ENFASE):
            with self.subTest(papel=papel):
                self.assertIn(papel, tokens.PAPEIS)
                self.assertIn(papel, tokens.RESERVA)
                self.assertIn(papel, tokens.NO_CROMO_ESCURO)

    def test_a_letra_passa_o_piso_aa_sobre_as_duas_faces_nas_duas_paletas(self) -> None:
        """**O critério de aceite da S-444**, e ele é o que obrigou a mexer no tema escuro.

        A spec dizia "sob `bootstrap-dark` a folha não sobrescreve: lá os dois já pintam, e pintam
        bem". Medido no pixel, o azul do `ttkbootstrap` dava **3,33:1** com letra branca e o
        vermelho **3,48:1** -- os dois abaixo do piso que este mesmo item exige nas três peles.
        As duas metades da spec se contradiziam.
        """
        for escuro in (False, True):
            letra = tokens.cor(tokens.TEXTO_SOBRE_ENFASE, cromo_escuro=escuro)
            for papel in self.PAPEIS:
                face = tokens.cor(papel, cromo_escuro=escuro)
                with self.subTest(papel=papel, cromo_escuro=escuro):
                    self.assertGreaterEqual(tokens.razao_de_contraste(letra, face), tokens.AA_TEXTO)

    def test_a_face_de_enfase_se_distingue_do_botao_neutro(self) -> None:
        """Uma face que não se separa do vizinho não é ênfase nenhuma -- é o defeito inteiro.

        O neutro é o do próprio tema: `#f0f0f0` no claro e `#2e3236` no escuro, medidos. É por
        isso que a face escura **clareia** em vez de escurecer: `#b02a37` sobre `#2e3236` dá
        1,99:1, vermelho escuro em cima de cinza escuro.
        """
        for escuro, neutro in ((False, "#f0f0f0"), (True, "#2e3236")):
            for papel in self.PAPEIS:
                face = tokens.cor(papel, cromo_escuro=escuro)
                with self.subTest(papel=papel, cromo_escuro=escuro):
                    self.assertGreaterEqual(tokens.razao_de_contraste(face, neutro), 3.0)

    def test_o_destrutivo_herda_a_matiz_de_problema_e_nao_o_valor(self) -> None:
        """A separação da S-224 outra vez: contorno de casa e face de botão são medidos contra
        fundos diferentes. O que atravessa é o **significado**, que mora na matiz."""
        problema = tokens.RESERVA[tokens.PROBLEMA]
        face = tokens.RESERVA[tokens.BOTAO_DESTRUTIVO]
        self.assertLess(tokens.distancia_de_matiz(face, problema), 5.0)
        self.assertNotEqual(face, problema)

    def test_as_duas_faces_nao_se_confundem_entre_si(self) -> None:
        distancia = tokens.distancia_de_matiz(
            tokens.RESERVA[tokens.BOTAO_PRIMARIO], tokens.RESERVA[tokens.BOTAO_DESTRUTIVO]
        )
        self.assertGreater(distancia, tokens.SEPARACAO_MINIMA_DE_MATIZ)


class UmaEnfasePorBarraTests(unittest.TestCase):
    """A regra de `estilos.PRIMARIO`, agora cobrável numa barra montada à mão (S-446)."""

    def test_duas_enfases_reprovam(self) -> None:
        with self.assertRaises(ValueError) as erro:
            estilos.conferir_barra([estilos.PRIMARIO, estilos.NEUTRO, estilos.PRIMARIO], onde="a barra do teste")
        self.assertIn("a barra do teste", str(erro.exception))
        self.assertIn("2", str(erro.exception))

    def test_uma_enfase_passa(self) -> None:
        estilos.conferir_barra([estilos.NEUTRO, estilos.PRIMARIO, estilos.DESTRUTIVO])

    def test_zero_enfase_passa_e_isso_e_criterio(self) -> None:
        """Nem toda fileira tem uma ação que o teclado também faz, e inventar uma para cumprir
        cota é o defeito que a regra existe para evitar."""
        estilos.conferir_barra([estilos.NEUTRO, estilos.NEUTRO])
        estilos.conferir_barra([])

    def test_papel_desconhecido_levanta_em_vez_de_contar_como_neutro(self) -> None:
        with self.assertRaises(KeyError):
            estilos.conferir_barra([estilos.NEUTRO, "IMPORTANTE"])

    def test_a_funcao_e_pura(self) -> None:
        """Como `estilo_de_botao`: nada de widget, nada de `Style`."""
        papeis = [estilos.PRIMARIO, estilos.NEUTRO]
        estilos.conferir_barra(papeis)
        self.assertEqual([estilos.PRIMARIO, estilos.NEUTRO], papeis)


class NoPixelTests(unittest.TestCase):
    """O que só o widget montado responde."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.addCleanup(lambda: theme.apply_theme(self.root, densidade=pele.CONFORTAVEL))

    def _faces(self, *, cromo_escuro: bool) -> dict[str, str]:
        """A face de cada papel, lida do pixel de um botão de verdade."""
        theme.apply_theme(self.root, cromo_escuro=cromo_escuro)
        janela = tk.Toplevel(self.root)
        self.addCleanup(janela.destroy)
        janela.geometry("560x90+140+140")
        linha = ttk.Frame(janela)
        linha.pack(padx=12, pady=12)
        botoes = {
            papel: ttk.Button(linha, text="Remover", style=estilos.estilo_de_botao(papel))
            for papel in estilos.PAPEIS_DE_BOTAO
        }
        for botao in botoes.values():
            botao.pack(side=tk.LEFT, padx=8)
        janela.deiconify()
        janela.lift()
        janela.attributes("-topmost", True)
        # **A janela precisa de tempo de tela, e não de `update_idletasks`.** `ImageGrab` lê o
        # que o compositor já desenhou; sem a espera o recorte pega a janela pela metade, e o
        # pixel que sai é a borda misturada com a face -- foi `#6a2a1d` no lugar de `#8f2018`.
        for _ in range(30):
            self.root.update()
            time.sleep(0.03)

        faces = {}
        for papel, botao in botoes.items():
            x, y = botao.winfo_rootx(), botao.winfo_rooty()
            largura, altura = botao.winfo_width(), botao.winfo_height()
            if largura <= 1 or altura <= 1:  # pragma: no cover - janela que não chegou a desenhar
                self.skipTest("o botão não foi desenhado nesta máquina")
            recorte = ImageGrab.grab(bbox=(x, y, x + largura, y + altura)).convert("RGB")
            # No meio da altura e perto da borda esquerda: o rótulo é centrado, então ali é face
            # limpa -- longe da letra e de dentro da moldura.
            faces[papel] = _hexa(recorte.getpixel((4, altura // 2)))
        return faces

    def test_os_tres_papeis_pintam_faces_distintas_nas_duas_paletas(self) -> None:
        """**O item**, e antes da S-444 ele reprovava no claro com os três em `#f0f0f0`."""
        for escuro in (False, True):
            with self.subTest(cromo_escuro=escuro):
                faces = self._faces(cromo_escuro=escuro)
                self.assertEqual(3, len(set(faces.values())), f"papéis com a mesma face: {faces}")

    def test_a_face_pintada_e_a_que_o_token_declara(self) -> None:
        """Se a face vier do tema e não do token, ela deixa de ser medida por este projeto."""
        for escuro in (False, True):
            faces = self._faces(cromo_escuro=escuro)
            for papel, token in (
                (estilos.PRIMARIO, tokens.BOTAO_PRIMARIO),
                (estilos.DESTRUTIVO, tokens.BOTAO_DESTRUTIVO),
            ):
                with self.subTest(papel=papel, cromo_escuro=escuro):
                    self.assertEqual(tokens.cor(token, cromo_escuro=escuro), faces[papel])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
