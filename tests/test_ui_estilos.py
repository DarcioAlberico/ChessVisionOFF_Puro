"""Os botões dizem o que fazem, e o contrato de degradação continua valendo (S-144).

Três coisas se afirmam aqui, e a terceira é a que impede o item de custar caro: um
`style="primary.TButton"` num `Tk` **sem** `ttkbootstrap` não pode levantar. O contrato de
`ui/theme.py` está escrito desde a S-53 — aparência não derruba ferramenta — e trocar a classe
de todo widget da janela por `ttkbootstrap.Button` o quebraria.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from chess_diagram_ocr.ui import comandos, estilos
from chess_diagram_ocr.ui.estilos import NEUTRO, PAPEIS_DE_BOTAO, estilo_de_botao

RAIZ = Path(__file__).resolve().parents[1]
ARQUIVOS = [
    *sorted((RAIZ / "src" / "chess_diagram_ocr" / "ui").glob("*.py")),
    *sorted((RAIZ / "src" / "chess_diagram_ocr" / "qt").glob("*.py")),
]


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


def _enfases(caminho: Path, papel: str) -> int:
    """Quantos botões daquele arquivo recebem `estilos.<papel>` -- **por `ast`, e não por texto**.

    A conferência em tempo de execução (`estilos.conferir_barra([...])`) repete os papéis da
    barra como dado, e uma contagem por expressão regular a lê como um segundo botão primário:
    a guarda que afirma a regra passaria a ser acusada de quebrá-la.
    """
    fora = []
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    conferencias = {
        id(no)
        for chamada in ast.walk(arvore)
        if isinstance(chamada, ast.Call)
        and ast.unparse(chamada.func).endswith("conferir_barra")
        for no in ast.walk(chamada)
    }
    for no in ast.walk(arvore):
        if (
            isinstance(no, ast.Attribute)
            and no.attr == papel
            and isinstance(no.value, ast.Name)
            and no.value.id == "estilos"
            and id(no) not in conferencias
        ):
            fora.append(no.lineno)
    return len(fora)


class SemNomeCravadoTests(unittest.TestCase):
    """O nome do estilo mora no módulo, e em nenhum painel."""

    TRADUTORES = ("estilos.py", "tema.py")
    """Quem **pode** escrever nome de estilo: `ui/estilos.py`, que os declara, e `qt/tema.py`, que
    os traduz em folha de estilo do Qt. Os dois citam `primary.TButton` na prosa que explica a
    tradução, e uma varredura por linha não distingue prosa de código."""

    def test_nenhum_painel_escreve_o_nome_do_estilo(self) -> None:
        infratores = []
        for arquivo in ARQUIVOS:
            if arquivo.name in self.TRADUTORES:
                continue
            for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r'style\s*=\s*"[^"]*TButton"', linha):
                    infratores.append(f"{arquivo.name}:{numero}: {linha.strip()[:70]}")
        self.assertEqual([], infratores, "nome de estilo cravado fora de ui/estilos.py")


class TodoBotaoDeclaraPapelTests(unittest.TestCase):
    """Zero sítios de `QPushButton` sem papel (S-445/S-506).

    **Por `ast` e não por regex, e a diferença foi medida.** A varredura por expressão regular que
    dimensionou este item olhava nove linhas à frente procurando `style=`, e casava com o do botão
    **seguinte** — ela relatava 30 de 103 com papel quando o número real era 30 de 99. Os quatro
    sítios a mais eram exemplos dentro do docstring de `ui/estilos.py`, que o `ast` não vê porque
    docstring não é código.

    **A régua mudou de forma no corte do Tk, e não de conteúdo.** Em `ttk` o papel viajava num
    `style=` do próprio construtor; em Qt ele é uma chamada à parte, `tema.aplicar_papel(botao,
    papel)`, porque o Qt não tem nome de estilo -- tem folha de estilo aplicada ao widget. Então a
    pergunta passa a ser sobre a **função** que cria o botão: ela declara o papel de cada um que
    cria? Cinco botões estavam sem, e foram achados por esta linha no dia do corte.
    """

    @staticmethod
    def _botoes(src: str, arvore: ast.AST | None = None) -> list[ast.Call]:
        return [
            no
            for no in ast.walk(arvore if arvore is not None else ast.parse(src))
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "QPushButton"
        ]

    @staticmethod
    def _sem_papel(arvore: ast.AST) -> list[int]:
        """As linhas de `QPushButton(...)` cuja função não declara papel nenhum.

        **Uma árvore só.** Achar o botão numa `ast.parse` e procurar a função noutra compara
        objetos de árvores diferentes: `is` nunca casa, toda função vira `None` e os 23 botões do
        pacote aparecem como 23 infratores. O sintoma é uma lista longa demais para ser verdade.
        """
        fora: list[int] = []
        for f in ast.walk(arvore):
            if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            corpo = ast.unparse(f)
            if "aplicar_papel" in corpo:
                continue
            fora += [
                no.lineno
                for no in ast.walk(f)
                if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "QPushButton"
            ]
        return fora

    def test_todo_botao_da_janela_declara_o_papel(self) -> None:
        """**A maioria é `NEUTRO`, e escrever `NEUTRO` é o item.** O valor não é o padrão que já
        saía de lá -- é a declaração ter sido feita, e passar a ser cobrada aqui."""
        sem_papel = []
        for arquivo in ARQUIVOS:
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
            sem_papel += [f"{arquivo.name}:{linha}" for linha in self._sem_papel(arvore)]
        self.assertEqual(
            [],
            sem_papel,
            "botão sem papel declarado: chame `tema.aplicar_papel(botao, comandos.papel(...))` "
            "ou `tema.aplicar_papel(botao, estilos.NEUTRO)`.",
        )

    def test_a_varredura_enxerga_os_botoes_que_existem(self) -> None:
        """Uma varredura que não achasse nada passaria em verde para sempre."""
        total = sum(len(self._botoes(a.read_text(encoding="utf-8"))) for a in ARQUIVOS)
        self.assertGreater(total, 15, "a varredura deixou de encontrar os botões da janela")


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
            quantos = _enfases(arquivo, "PRIMARIO")
            if quantos > self.LIMITE_POR_ARQUIVO:
                excessos[arquivo.name] = quantos
        self.assertEqual({}, excessos, "mais de uma ação primária no mesmo painel")

    def test_o_destrutivo_alcanca_os_dois_botoes_que_apagam_trabalho(self) -> None:
        """"Remover" e "Quarentena" tiram linha do `labels.csv`, que é rótulo corrigido à mão."""
        dataset = RAIZ / "src" / "chess_diagram_ocr" / "qt" / "painel_do_dataset.py"
        self.assertEqual(_enfases(dataset, "DESTRUTIVO"), 2)

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
        "painel_do_dataset.py": "'Remover' e 'Quarentena' tiram linha do labels.csv (S-144)",
        "painel_da_galeria.py": "'Limpar os headers', que `ui/estilos.py` cita pelo nome (S-445)",
        "campo.py": (
            "'Tirar do campo' apaga um diagrama de `data/field_set.jsonl`, que é a referência "
            "que os relatórios medem -- e ele não pergunta nem desfaz (S-506)"
        ),
        "comandos.py": "o catálogo declara o papel como **dado**; a propriedade é afirmada por nome acima",
        "tema.py": "registra a face do papel destrutivo; é o estilo, e não um botão (S-444)",
        "barra.py": (
            "desenha, na cor do papel, o que o catálogo declara destrutivo -- 'Apagar variante' e "
            "'Apagar daqui' --; ele compara `registro.papel`, não declara papel a botão nenhum. "
            "A linha saiu de `barra_da_sala.py` na S-528, quando a forma da barra em fila foi "
            "extraída para servir também ao painel do PDF (S-527/S-528)"
        ),
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
            arquivo.name: _enfases(arquivo, "DESTRUTIVO")
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
            if _enfases(arquivo, "DESTRUTIVO")
        }
        self.assertEqual(set(self.DECLARAM_DESTRUTIVO), declaram)


if __name__ == "__main__":
    unittest.main()
