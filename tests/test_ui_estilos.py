"""Os botões dizem o que fazem, e o contrato de degradação continua valendo (S-144).

Três coisas se afirmam aqui, e a terceira é a que impede o item de custar caro: um
`style="primary.TButton"` num `Tk` **sem** `ttkbootstrap` não pode levantar. O contrato de
`ui/theme.py` está escrito desde a S-53 — aparência não derruba ferramenta — e trocar a classe
de todo widget da janela por `ttkbootstrap.Button` o quebraria.
"""

from __future__ import annotations

import re
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk

from chess_diagram_ocr.ui import estilos
from chess_diagram_ocr.ui.estilos import DESTRUTIVO, NEUTRO, PAPEIS_DE_BOTAO, PRIMARIO, estilo_de_botao

RAIZ = Path(__file__).resolve().parents[1]
ARQUIVOS = [*sorted((RAIZ / "src" / "chess_diagram_ocr" / "ui").glob("*.py")), RAIZ / "app_tkinter.py"]


class TabelaTests(unittest.TestCase):
    def test_todo_papel_tem_estilo(self) -> None:
        for papel in PAPEIS_DE_BOTAO:
            with self.subTest(papel=papel):
                self.assertIsInstance(estilo_de_botao(papel), str)

    def test_a_tabela_e_injetiva(self) -> None:
        """Dois papéis com o mesmo estilo é o mesmo que não ter os dois papéis."""
        nomes = [estilo_de_botao(papel) for papel in PAPEIS_DE_BOTAO]
        self.assertEqual(len(nomes), len(set(nomes)))

    def test_o_neutro_e_o_padrao_do_ttk_e_nao_um_nome_inventado(self) -> None:
        self.assertEqual(estilo_de_botao(NEUTRO), "")

    def test_papel_desconhecido_levanta_em_vez_de_cair_no_neutro(self) -> None:
        """Um papel escrito errado que virasse botão cinza devolveria a janela ao estado
        anterior sem ninguém notar -- que é exatamente o defeito que a S-144 conserta."""
        with self.assertRaises(KeyError):
            estilo_de_botao("IMPORTANTE")


class SemNomeCravadoTests(unittest.TestCase):
    """O nome do estilo mora no módulo, e em nenhum painel."""

    def test_nenhum_painel_escreve_o_nome_do_estilo(self) -> None:
        infratores = []
        for arquivo in ARQUIVOS:
            if arquivo.name == "estilos.py":
                continue
            for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r'style\s*=\s*"[^"]*TButton"', linha):
                    infratores.append(f"{arquivo.name}:{numero}: {linha.strip()[:70]}")
        self.assertEqual([], infratores, "nome de estilo cravado fora de ui/estilos.py")


class UmaEnfasePorBarraTests(unittest.TestCase):
    """A regra que dá sentido à hierarquia: **uma** ação primária por barra, nunca duas.

    O teste conta por arquivo e não por barra porque a barra não é um objeto que dê para
    contar de fora — mas o efeito é o mesmo onde importa: nenhum painel tem duas ênfases.

    **`ui/comandos.py` é a exceção, e ela é o oposto de uma folga** (S-219). O catálogo declara
    a ênfase de todos os comandos da janela, então contar literal ali mede o arquivo inteiro e
    não uma barra. Lá a regra deixou de precisar de proxy: `comandos.primarios_por_grupo()`
    devolve o grupo e os primários dele, e `test_ui_comandos.test_um_primario_por_grupo` afirma
    a propriedade em vez de contar ocorrências de texto.
    """

    LIMITE_POR_ARQUIVO = 1

    SEM_PROXY = {"comandos.py"}
    """Arquivos onde a regra é cobrada pela propriedade, e não pela contagem de literais."""

    def test_nenhum_painel_tem_duas_acoes_primarias(self) -> None:
        excessos = {}
        for arquivo in ARQUIVOS:
            if arquivo.name in self.SEM_PROXY:
                continue
            texto = arquivo.read_text(encoding="utf-8")
            quantos = len(re.findall(r"estilos\.PRIMARIO", texto))
            if quantos > self.LIMITE_POR_ARQUIVO:
                excessos[arquivo.name] = quantos
        self.assertEqual({}, excessos, "mais de uma ação primária no mesmo painel")

    def test_o_destrutivo_alcanca_os_dois_botoes_que_apagam_trabalho(self) -> None:
        """"Remover" e "Quarentena" tiram linha do `labels.csv`, que é rótulo corrigido à mão."""
        dataset = (RAIZ / "src" / "chess_diagram_ocr" / "ui" / "dataset_panel.py").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"estilos\.DESTRUTIVO", dataset)), 2)

    def test_nenhum_outro_botao_da_janela_e_destrutivo(self) -> None:
        """Vermelho que aparece onde não se apaga nada deixa de significar "cuidado"."""
        fora = {
            arquivo.name: len(re.findall(r"estilos\.DESTRUTIVO", arquivo.read_text(encoding="utf-8")))
            for arquivo in ARQUIVOS
            if arquivo.name not in ("dataset_panel.py", "estilos.py")
        }
        self.assertEqual({}, {nome: n for nome, n in fora.items() if n}, "danger fora do Dataset")


class DegradacaoTests(unittest.TestCase):
    """Um `Tk` sem `ttkbootstrap`, com tema `vista`: nenhum estilo pode levantar.

    É o contrato de `ui/theme.py` desde a S-53, e é a razão de a S-144 passar `style=` em vez
    de trocar `ttk.Button` por `ttkbootstrap.Button` em 30 módulos.
    """

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:  # pragma: no cover - maquina sem display
            raise unittest.SkipTest(f"sem Tk disponível: {exc}") from exc
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.root.destroy()

    def test_cada_estilo_constroi_um_botao_sem_levantar(self) -> None:
        estilo = ttk.Style()
        try:
            estilo.theme_use("vista")
        except tk.TclError:  # pragma: no cover - fora do Windows
            estilo.theme_use(estilo.theme_names()[0])

        quadro = ttk.Frame(self.root)
        try:
            for papel in PAPEIS_DE_BOTAO:
                with self.subTest(papel=papel):
                    botao = ttk.Button(quadro, text="x", style=estilo_de_botao(papel))
                    self.assertIsNotNone(botao)
                    botao.destroy()
        finally:
            quadro.destroy()

    def test_o_estilo_desconhecido_pelo_tema_nao_derruba_a_janela(self) -> None:
        """A prova direta: um nome que **nenhum** tema define continua desenhando um botão."""
        quadro = ttk.Frame(self.root)
        try:
            botao = ttk.Button(quadro, text="x", style="inexistente.TButton")
            self.assertIsNotNone(botao)
        finally:
            quadro.destroy()

    def test_os_papeis_do_modulo_sao_os_tres_declarados(self) -> None:
        self.assertEqual(set(PAPEIS_DE_BOTAO), {PRIMARIO, DESTRUTIVO, NEUTRO})
        self.assertEqual(estilos.PRIMARIO, "PRIMARIO")


if __name__ == "__main__":
    unittest.main()
