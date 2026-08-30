"""Os botões dizem o que fazem, e o contrato de degradação continua valendo (S-144).

Três coisas se afirmam aqui, e a terceira é a que impede o item de custar caro: um
`style="primary.TButton"` num `Tk` **sem** `ttkbootstrap` não pode levantar. O contrato de
`ui/theme.py` está escrito desde a S-53 — aparência não derruba ferramenta — e trocar a classe
de todo widget da janela por `ttkbootstrap.Button` o quebraria.
"""

from __future__ import annotations

import ast
import re
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk

from tk_root import raiz as raiz_do_processo

from chess_diagram_ocr.ui import comandos, estilos
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


class TodoBotaoDeclaraPapelTests(unittest.TestCase):
    """Zero sítios de `ttk.Button` sem papel (S-445).

    **Por `ast` e não por regex, e a diferença foi medida.** A varredura por expressão regular que
    dimensionou este item olhava nove linhas à frente procurando `style=`, e casava com o `style=`
    do botão **seguinte** — ela relatava 30 de 103 com papel quando o número real era 30 de 99.
    Os quatro sítios a mais eram exemplos dentro do docstring de `ui/estilos.py`, que o `ast` não
    vê porque docstring não é código.
    """

    @staticmethod
    def _botoes(src: str) -> list[ast.Call]:
        return [
            no
            for no in ast.walk(ast.parse(src))
            if isinstance(no, ast.Call)
            and isinstance(no.func, ast.Attribute)
            and no.func.attr == "Button"
            and isinstance(no.func.value, ast.Name)
            and no.func.value.id in ("ttk", "tb")
        ]

    def test_todo_botao_da_janela_declara_o_papel(self) -> None:
        """**A maioria é `NEUTRO`, e escrever `NEUTRO` é o item.** O valor não é o `style=""` que
        já saía de lá -- é a declaração ter sido feita, e passar a ser cobrada aqui."""
        sem_papel = []
        for arquivo in ARQUIVOS:
            src = arquivo.read_text(encoding="utf-8")
            for no in self._botoes(src):
                estilo = next(
                    (ast.get_source_segment(src, kw.value) for kw in no.keywords if kw.arg == "style"), ""
                )
                if "comandos.estilo" not in (estilo or "") and "estilos.estilo_de_botao" not in (estilo or ""):
                    sem_papel.append(f"{arquivo.name}:{no.lineno}")
        self.assertEqual(
            [],
            sem_papel,
            "botão sem papel declarado: passe `style=comandos.estilo(...)` ou "
            "`style=estilos.estilo_de_botao(estilos.NEUTRO)`.",
        )

    def test_a_varredura_enxerga_os_botoes_que_existem(self) -> None:
        """Uma varredura que não achasse nada passaria em verde para sempre."""
        total = sum(len(self._botoes(a.read_text(encoding="utf-8"))) for a in ARQUIVOS)
        self.assertGreater(total, 90, "a varredura deixou de encontrar os botões da janela")


class UmaEnfasePorBarraTests(unittest.TestCase):
    """A regra que dá sentido à hierarquia: **uma** ação primária por barra, nunca duas.

    O teste conta por arquivo e não por barra porque a barra não é um objeto que dê para
    contar de fora — mas o efeito é o mesmo onde importa: nenhum painel tem duas ênfases.

    **`ui/comandos.py` é a exceção, e ela é o oposto de uma folga** (S-324). O catálogo declara
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

    def test_o_destrutivo_alcanca_os_dois_da_sala_de_estudo(self) -> None:
        """Apagar variante e apagar continuação tiram **análise humana** da árvore (S-280).

        A régua é a mesma dos dois do Dataset: destrutivo é o que apaga trabalho que não sai de
        graça de uma releitura. Uma variante com comentário e setas é a tarde de alguém, e é por
        isso que os dois também **perguntam** antes quando há o que perder.

        Eles vêm do catálogo e não de um `style=` no painel: desde a S-324 o papel é declarado uma
        vez, e é `comandos.estilo` que o traduz em nome de estilo `ttk`.
        """
        self.assertEqual(
            {registro.acao for registro in comandos.CATALOGO if registro.papel == estilos.DESTRUTIVO},
            {"apagar_variante", "apagar_continuacao"},
        )

    DECLARAM_DESTRUTIVO = {
        "dataset_panel.py": "'Remover' e 'Quarentena' tiram linha do labels.csv (S-144)",
        "gallery_panel.py": "'Limpar os headers', que `ui/estilos.py` cita pelo nome (S-445)",
        "comandos.py": "o catálogo declara o papel como **dado**; a propriedade é afirmada por nome acima",
        "theme.py": "registra a face de `danger.TButton`; é o estilo, e não um botão (S-444)",
    }
    """Onde `estilos.DESTRUTIVO` pode aparecer, e por quê. Cada entrada é uma decisão assinada."""

    def test_nenhum_outro_botao_da_janela_e_destrutivo(self) -> None:
        """Vermelho que aparece onde não se apaga nada deixa de significar "cuidado".

        **Esta lista era `("dataset_panel.py", "estilos.py", "comandos.py")` e o teste passava
        congelando o defeito** (S-445). `ui/estilos.py:47` cita **"Limpar os headers"** pelo nome
        como exemplo canônico de `DESTRUTIVO`, e o painel que o desenha nunca o consultou -- então
        "nenhum destrutivo fora do Dataset" era verdade sobre o código e falso sobre a intenção,
        e o teste protegia a distância entre as duas. O botão apaga os quatro campos de um
        diagrama sem perguntar e sem desfazer, e a S-76 é o registro do que custa confundi-lo com
        o vizinho: 1.405 diagramas.

        **"Copiar headers para todos" ficou de fora, e o critério é que decide.** Ele sobrescreve
        header de todos os diagramas do livro -- mas tem "Desfazer a cópia" no botão de baixo, e o
        critério da S-445 pede os três: apaga trabalho humano, não pergunta, não desfaz.
        """
        fora = {
            arquivo.name: len(re.findall(r"estilos\.DESTRUTIVO", arquivo.read_text(encoding="utf-8")))
            for arquivo in ARQUIVOS
            if arquivo.name not in self.DECLARAM_DESTRUTIVO
        }
        self.assertEqual({}, {nome: n for nome, n in fora.items() if n}, "danger onde não se apaga nada")

    def test_toda_declaracao_de_destrutivo_esta_na_lista_e_a_lista_nao_tem_orfao(self) -> None:
        """A lista acima é uma isenção, e isenção que sobra é isenção que esconde.

        Se alguém tirar o destrutivo de um painel, a entrada correspondente tem de sair junto --
        senão o próximo botão vermelho daquele arquivo entra sem ninguém assinar.
        """
        declaram = {
            arquivo.name
            for arquivo in ARQUIVOS
            if re.search(r"estilos\.DESTRUTIVO", arquivo.read_text(encoding="utf-8"))
        }
        self.assertEqual(set(self.DECLARAM_DESTRUTIVO), declaram)


class DegradacaoTests(unittest.TestCase):
    """Um `Tk` sem `ttkbootstrap`, com tema `vista`: nenhum estilo pode levantar.

    É o contrato de `ui/theme.py` desde a S-53, e é a razão de a S-144 passar `style=` em vez
    de trocar `ttk.Button` por `ttkbootstrap.Button` em 30 módulos.
    """

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        # A raiz é a do processo, e não uma deste módulo (S-416): duas raízes vivas fazem uma
        # `PhotoImage` nascer no interpretador errado, e o Tk recusa a imagem com a mensagem
        # que parece coleta de lixo. O porquê inteiro está em `tests/tk_root.py`.
        cls.root = raiz_do_processo()

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
