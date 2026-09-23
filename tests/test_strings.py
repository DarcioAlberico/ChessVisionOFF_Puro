"""Vocabulário da interface e acentuação em pt-BR (S-04).

A pendência 0.7 ficou aberta desde a Fase 0: as strings da interface estavam sem acento
("posicao", "Configuracao") e centralizá-las dependia da decomposição do Tkinter, que só
veio na 6.2. Aqui ela fecha, e o teste é o que impede a regressão -- sem ele, a próxima
string escrita às pressas volta a ser "posicao" e ninguém percebe.

A varredura olha **literais de string** via AST, não o arquivo inteiro: docstrings e
comentários também são pt-BR, mas o que o usuário lê é o que importa travar.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from chess_diagram_ocr.ui import strings

RAIZ = Path(__file__).resolve().parents[1]

ARQUIVOS_DE_UI = [
    # `strings.py` fica de fora: ele **contém** a lista das formas erradas, de propósito.
    caminho
    for caminho in [
        *sorted((RAIZ / "src" / "chess_diagram_ocr" / "ui").glob("*.py")),
        *sorted((RAIZ / "src" / "chess_diagram_ocr" / "qt").glob("*.py")),
    ]
    if caminho.name != "strings.py"
] + [RAIZ / "src" / "chess_diagram_ocr" / "qt" / "janela.py", RAIZ / "examples" / "streamlit_demo.py"]

PERMITIDOS = {
    # Chaves, nomes de campo e identificadores que por acaso batem com uma palavra da lista.
    "sao",
}
"""Exceções. Vazia de propósito quanto a texto de tela: uma exceção ali seria a string que
o usuário lê errada."""


CHAMADAS_DE_TELA = frozenset({
    "addItems", "addItem", "insertItems", "insertItem", "setItems", "setText", "setPlaceholderText",
    "setToolTip", "setWindowTitle", "setHorizontalHeaderLabels", "setVerticalHeaderLabels",
    "showMessage", "mostrar", "QLabel", "QPushButton", "QCheckBox", "QRadioButton", "QListWidgetItem",
    "QTableWidgetItem", "QTreeWidgetItem",
})
"""As chamadas que escrevem o que recebem na tela: uma lista de palavras passada direto a uma delas
é texto de interface, por mais minúsculas que sejam (crítico da fase 5, ciclo 2)."""


def _literais_visiveis(caminho: Path) -> list[str]:
    """Strings do módulo que não são docstring nem nome de símbolo exportado.

    **`__all__` ficou de fora, e é uma correção de precisão e não uma brecha.** Os itens dele
    são nomes de função e de constante — `"confianca"` ali é o identificador `confianca`, que o
    Python não deixa acentuar sem custo e que ninguém lê na tela. Acentuá-lo por causa desta
    varredura mudaria a API pública de um módulo para satisfazer um teste sobre **texto de
    interface**, que é o oposto do que o teste existe para proteger.
    """
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    ignorados: set[int] = set()
    for no in ast.walk(arvore):
        corpo = getattr(no, "body", None)
        if not isinstance(corpo, list):
            continue
        for item in corpo:
            if isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant):
                if isinstance(item.value.value, str):
                    ignorados.add(id(item.value))

    # **A chave que é o próprio nome** (S-230). `PADRAO = "padrao"` não é texto de tela: é o
    # identificador do registro de conjuntos, escrito minúsculo e sem acento de propósito porque
    # é ele que vai para o `app_tkinter_state.json` -- do mesmo modo que `pele.CLASSICA` e
    # `abas.DATASET`. Acentuá-lo mudaria o formato gravado em disco para satisfazer uma varredura
    # sobre **texto de interface**, que é o mesmo argumento com que `__all__` ficou de fora.
    #
    # A regra é estreita e não uma permissão: só escapa o literal que é **exatamente** o nome
    # MAIÚSCULO ao qual ele é atribuído, em minúsculas. Um `PADRAO = "Padrão do sistema"` -- que
    # é texto -- continua sendo varrido, e um rótulo que diga "padrao" em qualquer outro lugar
    # também.
    for no in ast.walk(arvore):
        alvos = getattr(no, "targets", None) or ([no.target] if isinstance(no, ast.AnnAssign) else [])
        nomes = {alvo.id for alvo in alvos if isinstance(alvo, ast.Name) and alvo.id.isupper()}
        valor = getattr(no, "value", None)
        if nomes and isinstance(valor, ast.Constant) and isinstance(valor.value, str):
            if valor.value in {nome.lower() for nome in nomes}:
                ignorados.add(id(valor))

    for no in ast.walk(arvore):
        alvos = getattr(no, "targets", None) or ([no.target] if isinstance(no, ast.AnnAssign) else [])
        if not any(isinstance(alvo, ast.Name) and alvo.id == "__all__" for alvo in alvos):
            continue
        for item in ast.walk(no):
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                ignorados.add(id(item))
    # **Identificadores nas posições em que só identificador cabe** (OCR_UI ciclo 2, A15). A
    # varredura reprovou por fases seguidas em seis literais que nenhuma pessoa lê: o id de comando
    # (`Comando("configuracoes", "Configurações…", …)`, `Item("configuracoes")`), a chave do JSON
    # gravado em disco (`{"pagina": …}`, `item["pagina"]`), o token cujo valor é o próprio nome em
    # maiúsculas (`SELECAO = "SELECAO"`) e a lista de palavras **dobradas** que casa títulos sem
    # acento (`"… quebra cabecas …".split()`). Nenhuma regra abaixo é por palavra: cada uma olha a
    # **posição** do literal, e só um literal com forma de identificador (`^[a-z_][a-z0-9_]*$`)
    # escapa nas três primeiras -- um `{"Página": …}` ou um `Comando("abrir", "Configuracoes")`
    # continuam varridos.
    #
    # **E a posição tem de ser de identificador de verdade** (crítico da fase 5): a chave de um
    # dicionário que o módulo **enumera** (`list(D)`, `sorted(D)`, `D.keys()`, `for x in D`,
    # `combo.addItems(D)`) vai para a tela -- `REGIMES = {"pagina": 1}` com
    # `combo.addItems(list(REGIMES))` escapava; e o `.split()` só isenta a lista de palavras
    # minúsculas partida por espaço (`"… quebra cabecas …".split()`), não
    # `"Pagina anterior|Proxima pagina".split("|")`. **Ciclo 2 do crítico**: enumerar é também
    # `", ".join(D)` e `[*D]`; e a lista de palavras não escapa quando vai direto a uma chamada que
    # escreve na tela (`combo.addItems("pagina posicao".split())`) -- guardada num nome, num
    # `frozenset(...)` de palavras dobradas, ela continua sendo identificador.
    identificador = re.compile(r"^[a-z_][a-z0-9_]*$")
    palavras_minusculas = re.compile(r"^[a-z0-9 ]+$")
    enumerados: set[str] = set()
    para_a_tela: set[int] = set()   # os nós passados direto a uma chamada que escreve na tela
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call):
            chamada = no.func.id if isinstance(no.func, ast.Name) else getattr(no.func, "attr", "")
            if chamada in CHAMADAS_DE_TELA:
                para_a_tela.update(id(arg) for arg in no.args)
                para_a_tela.update(id(kw.value) for kw in no.keywords)
        if isinstance(no, ast.Starred) and isinstance(no.value, ast.Name):
            enumerados.add(no.value.id)
        if isinstance(no, ast.Call) and no.args and isinstance(no.args[0], ast.Name):
            funcao = no.func
            if (isinstance(funcao, ast.Name) and funcao.id in {"list", "sorted", "tuple", "set", "iter", "enumerate"}) or (
                    isinstance(funcao, ast.Attribute) and funcao.attr in {"addItems", "extend", "setItems", "join"}):
                enumerados.add(no.args[0].id)
        elif (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
              and no.func.attr in {"keys", "items", "values"} and isinstance(no.func.value, ast.Name)):
            enumerados.add(no.func.value.id)
        elif isinstance(no, (ast.For, ast.comprehension)) and isinstance(no.iter, ast.Name):
            enumerados.add(no.iter.id)
    dicionarios_enumerados: set[int] = set()
    for no in ast.walk(arvore):
        alvos = getattr(no, "targets", None) or ([no.target] if isinstance(no, ast.AnnAssign) else [])
        valor = getattr(no, "value", None)
        if isinstance(valor, ast.Dict) and any(isinstance(a, ast.Name) and a.id in enumerados for a in alvos):
            dicionarios_enumerados.add(id(valor))
    for no in ast.walk(arvore):
        if isinstance(no, ast.Dict):
            if id(no) in dicionarios_enumerados:
                continue
            for chave in no.keys:
                if isinstance(chave, ast.Constant) and isinstance(chave.value, str) and identificador.match(chave.value):
                    ignorados.add(id(chave))
        elif isinstance(no, ast.Subscript):
            fatia = no.slice
            if isinstance(fatia, ast.Constant) and isinstance(fatia.value, str) and identificador.match(fatia.value):
                ignorados.add(id(fatia))
        elif isinstance(no, ast.Call):
            funcao = no.func
            nome = funcao.id if isinstance(funcao, ast.Name) else (funcao.attr if isinstance(funcao, ast.Attribute) else "")
            if nome in ("Comando", "Item") and no.args:
                primeiro = no.args[0]
                if isinstance(primeiro, ast.Constant) and isinstance(primeiro.value, str) and identificador.match(primeiro.value):
                    ignorados.add(id(primeiro))
            if (isinstance(funcao, ast.Attribute) and funcao.attr == "split" and not no.args
                    and isinstance(funcao.value, ast.Constant) and isinstance(funcao.value.value, str)
                    and palavras_minusculas.match(funcao.value.value) and id(no) not in para_a_tela):
                ignorados.add(id(funcao.value))
        else:
            alvos = getattr(no, "targets", None) or ([no.target] if isinstance(no, ast.AnnAssign) else [])
            nomes = {alvo.id for alvo in alvos if isinstance(alvo, ast.Name) and alvo.id.isupper()}
            valor = getattr(no, "value", None)
            if nomes and isinstance(valor, ast.Constant) and valor.value in nomes:
                ignorados.add(id(valor))

    return [
        no.value
        for no in ast.walk(arvore)
        if isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in ignorados
    ]


class AccentTests(unittest.TestCase):
    def test_no_ui_string_uses_an_unaccented_portuguese_word(self) -> None:
        """A trava da pendência 0.7 da Fase 0."""
        padrao = re.compile(
            # `s?` e nao `\w*`: "automaticamente" e correto sem acento, e um casamento
            # largo o acusaria junto com "automatica".
            r"\b(" + "|".join(sorted(strings.WORDS_REQUIRING_ACCENTS, key=len, reverse=True)) + r")s?\b",
            re.IGNORECASE,
        )
        faltas: list[str] = []
        for caminho in ARQUIVOS_DE_UI:
            for texto in _literais_visiveis(caminho):
                for achado in padrao.finditer(texto):
                    if achado.group(0).lower() in PERMITIDOS:
                        continue
                    # `@media` e regra CSS, nao portugues. O `@` desambigua sozinho.
                    if achado.start() and texto[achado.start() - 1] == "@":
                        continue
                    faltas.append(f"{caminho.name}: {achado.group(0)!r} em {texto[:60]!r}")

        self.assertEqual(faltas, [], "Strings de UI sem acento:\n" + "\n".join(faltas[:20]))

    def test_os_identificadores_escapam_e_o_texto_de_tela_nas_mesmas_posicoes_nao(self) -> None:
        """A15 do ciclo 2: as regras por posição não abrem brecha para texto de interface."""
        import tempfile

        fonte = (
            'SELECAO = "SELECAO"\n'
            'dados = {"pagina": 1, "Pagina seguinte": 2}\n'
            'valor = item["pagina"]\n'
            'c = Comando("configuracoes", "Configuracoes da pagina")\n'
            'm = Item("configuracoes")\n'
            'vazias = "quebra cabecas".split()\n'
            'rotulo = QLabel("pagina")\n'
            'erro = {"pagina": "Ir para a pagina"}\n'
            # os três casos do crítico da fase 5: texto de tela em posição de identificador
            'ROTULOS = "Pagina anterior|Proxima pagina|Configuracoes".split("|")\n'
            'combo.addItems("Posicao Pagina Revisao".split())\n'
            'REGIMES = {"posicao": 1, "revisao": 2}\n'
            'combo.addItems(list(REGIMES))\n'
            # e os três do ciclo 2 do crítico
            'combo.addItems("selecao posicoes".split())\n'
            'REG1 = {"notacao": 1, "diagnostico": 2}\n'
            'QLabel(", ".join(REG1))\n'
            'REG2 = {"botao": 1, "tabuleiros": 2}\n'
            'combo.addItems([*REG2])\n'
        )
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "modulo.py"
            caminho.write_text(fonte, encoding="utf-8")
            vistos = _literais_visiveis(caminho)
        for escapa in ("SELECAO", "quebra cabecas"):
            self.assertNotIn(escapa, vistos)
        for varrido in ("selecao posicoes", "notacao", "diagnostico", "botao", "tabuleiros"):
            self.assertIn(varrido, vistos, "texto de tela em posição de identificador escapou")
        self.assertEqual(vistos.count("pagina"), 1, "só o `QLabel(\"pagina\")` é texto de tela")
        self.assertEqual(vistos.count("configuracoes"), 0)
        for varrido in ("Pagina seguinte", "Configuracoes da pagina", "Ir para a pagina",
                        "Pagina anterior|Proxima pagina|Configuracoes", "Posicao Pagina Revisao",
                        "posicao", "revisao"):
            self.assertIn(varrido, vistos)

    def test_nenhuma_excecao_de_produto_usa_forma_sem_acento(self) -> None:
        """A varredura de cima olha `ui/`, e a mensagem de exceção **também é interface** (S-392).

        O que o `raise` de um módulo de produto carrega chega à tela por dois caminhos: a caixa de
        erro da janela, que mostra `str(exc)`, e o `cli_errors` da S-126, que a imprime em pt-BR.
        Nenhum dos dois passava por esta guarda, e "Selecao vazia: o retangulo escolhido nao cobre
        nenhum pixel" era o que a janela mostrava a quem arrastava um retângulo vazio.

        **`cli/` fica de fora, e `logger` também**: ali o texto é de terminal e de arquivo de log,
        e a convenção do projeto é escrevê-los sem acento (o mesmo motivo do README).
        """
        raiz = RAIZ / "src" / "chess_diagram_ocr"
        padrao = re.compile(
            r"\b(" + "|".join(sorted(strings.WORDS_REQUIRING_ACCENTS, key=len, reverse=True)) + r")s?\b",
            re.IGNORECASE,
        )
        faltas: list[str] = []
        for caminho in sorted(raiz.rglob("*.py")):
            if caminho.parent.name in ("ui", "cli"):
                continue
            arvore = ast.parse(caminho.read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if not isinstance(no, ast.Raise) or no.exc is None:
                    continue
                for item in ast.walk(no.exc):
                    if isinstance(item, ast.Constant) and isinstance(item.value, str):
                        achado = padrao.search(item.value)
                        if achado and achado.group(0).lower() not in PERMITIDOS:
                            faltas.append(f"{caminho.name}:{no.lineno}: {item.value[:60]!r}")

        self.assertEqual(faltas, [], "Mensagem de exceção sem acento:\n" + "\n".join(faltas[:20]))

    def test_the_word_list_itself_is_unaccented(self) -> None:
        """Ela lista as formas **erradas**; acentuá-la faria o teste acima nunca falhar."""
        for palavra in strings.WORDS_REQUIRING_ACCENTS:
            with self.subTest(palavra=palavra):
                self.assertEqual(palavra, palavra.encode("ascii", "ignore").decode("ascii"))


TITULOS_GENERICOS = frozenset({"erro", "erro!", "aviso", "alerta", "atenção", "atencao", "falha", "error", "warning"})
"""Títulos de caixa que não dizem **o que** falhou. Ver `TituloDeCaixaTests` (S-401)."""


class TituloDeCaixaTests(unittest.TestCase):
    """Toda caixa de diálogo nomeia a operação, e não a categoria (S-401).

    Nove das trinta e nove caixas se chamavam "Erro". O título é a primeira linha que se lê, e
    muitas vezes a única: "Erro / Falha ao renderizar página" diz duas vezes que houve falha e
    nenhuma vez qual gesto a produziu -- enquanto "Mostrar a página" já responde. Não é gosto:
    quem tem três abas abertas e duas operações em curso precisa saber a **qual** delas responder,
    e o `messagebox` do Tk não põe o nome do painel em lugar nenhum.

    A guarda é a mesma classe da S-161 e da S-324: o que a janela mostra é declarado num lugar e
    conferido de fora, em vez de depender de quem escreveu a linha se lembrar.
    """

    CHAMADAS = ("information", "warning", "critical", "question", "about", "setWindowTitle")
    """Os cinco atalhos do `QMessageBox` mais o título posto à mão.

    **Eram as sete do `tkinter.messagebox` até o corte (S-506).** No Qt o título é o **segundo**
    posicional dos atalhos (o primeiro é o widget pai), e por isso a varredura abaixo olha as duas
    posições: `setWindowTitle` de um `QDialog` põe o título na primeira."""

    def _titulos(self) -> list[tuple[str, int, str]]:
        achados: list[tuple[str, int, str]] = []
        for caminho in ARQUIVOS_DE_UI:
            arvore = ast.parse(caminho.read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Attribute):
                    continue
                if no.func.attr not in self.CHAMADAS or not no.args:
                    continue
                # Título vindo de variável ou de f-string sai da varredura: ele é montado com o
                # nome do arquivo ou do livro, que é mais específico do que qualquer literal.
                for candidato in no.args[:2]:
                    if isinstance(candidato, ast.Constant) and isinstance(candidato.value, str):
                        achados.append((caminho.name, no.lineno, candidato.value))
                        break
        return achados

    def test_a_varredura_acha_as_caixas(self) -> None:
        """Sem isto, um `messagebox` renomeado faria o teste abaixo passar sobre lista vazia."""
        self.assertGreaterEqual(len(self._titulos()), 30)

    def test_nenhuma_caixa_se_chama_apenas_erro(self) -> None:
        genericos = [
            f"{arquivo}:{linha}: {titulo!r}"
            for arquivo, linha, titulo in self._titulos()
            if titulo.strip().lower() in TITULOS_GENERICOS
        ]
        self.assertEqual(
            genericos,
            [],
            "Caixa de diálogo com título genérico. O título nomeia a operação -- "
            '"Abrir PDF", "Ler o diagrama" --, e a mensagem diz o que houve:\n' + "\n".join(genericos),
        )

    def test_nenhuma_caixa_fica_sem_titulo(self) -> None:
        vazios = [f"{a}:{n}" for a, n, titulo in self._titulos() if not titulo.strip()]
        self.assertEqual(vazios, [], "Caixa sem título:\n" + "\n".join(vazios))


class VocabularyTests(unittest.TestCase):
    def test_every_side_source_the_pipeline_produces_has_a_label(self) -> None:
        """As três da S-17 mais as duas que só a interface cria."""
        for fonte in ("text", "legality", "default", "manual", "queue"):
            with self.subTest(fonte=fonte):
                self.assertTrue(strings.side_source_label(fonte))

    def test_a_conflict_is_not_a_provenance_and_has_its_own_wording(self) -> None:
        """A discordância da S-17 não é "de onde veio": é "duas fontes se contradizem"."""
        conflito = strings.side_source_label("text", conflicting=True)
        self.assertNotEqual(conflito, strings.side_source_label("text"))
        self.assertIn("discordam", conflito)

    def test_an_unknown_source_yields_no_label_instead_of_a_wrong_one(self) -> None:
        self.assertEqual(strings.side_source_label("inventado"), "")

    def test_detection_sources_read_as_prose_not_as_keys(self) -> None:
        """"embedded" é o valor interno da S-12; o usuário não tem por que conhecê-lo."""
        self.assertIn("embutida", strings.detection_source_label("embedded"))
        self.assertIn("contorno", strings.detection_source_label("contour"))

    def test_an_unknown_detection_source_falls_back_to_the_raw_value(self) -> None:
        """Melhor mostrar a chave crua do que esconder que existe uma fonte nova."""
        self.assertEqual(strings.detection_source_label("futuro"), "futuro")

    def test_the_orientation_labels_cover_the_tri_state_of_s13(self) -> None:
        self.assertEqual(set(strings.ORIENTATION_LABELS), {"auto", "0", "180"})


class TermosProibidosTests(unittest.TestCase):
    """Inglês dentro de uma janela em pt-BR, e o mesmo conceito com dois nomes (S-166).

    A avaliação listou oito termos em inglês -- "Zoom board", "Virar board", "Heatmap de
    incerteza", "Corrigir Net", "Batch size", "Learning rate", "Headers do PGN", "Split" -- mais
    `pending` repetido em 129 linhas da fila **enquanto o filtro ao lado dizia "Só pendentes"**.

    A varredura é sobre literais de string, como a de acentuação: o que importa travar é o que a
    pessoa lê. Comentário e docstring podem citar o termo antigo -- e citam, para dizer o que ele
    era.
    """

    PROIBIDOS = {
        "board": "\"board\" é tabuleiro; ver strings.ZOOM_DO_TABULEIRO e VIRAR_TABULEIRO",
        "heatmap": "virou strings.MAPA_DE_INCERTEZA",
        "batch size": "virou strings.TAMANHO_DO_LOTE",
        "learning rate": "virou strings.TAXA_DE_APRENDIZADO",
        "headers do pgn": "virou strings.CABECALHOS_DO_PGN",
        "corrigir net": "virou strings.CORRIGIR_PELA_REDE",
        "varrer pdf": "um gesto, um nome: strings.VARRER_LIVRO",
    }
    """Termo proibido → onde ele foi parar. O valor é o que a mensagem de falha mostra.

    **"FEN" e "PGN" não estão aqui, e é decisão e não esquecimento**: são o nome do formato, como
    "JPEG". Traduzi-los inventaria vocabulário que não existe fora deste programa."""

    def test_nenhum_termo_em_ingles_sobrou_na_interface(self) -> None:
        faltas = []
        for caminho in ARQUIVOS_DE_UI:
            for texto in _literais_visiveis(caminho):
                minusculo = texto.casefold()
                for termo, destino in self.PROIBIDOS.items():
                    # Com fronteira de palavra: `max_boards`, `board_zoom` e `val_board_exact_acc`
                    # são **chaves** -- de opção, de estado e de métrica --, e não texto de tela.
                    # Renomeá-las por causa desta varredura mudaria a API por causa de um teste
                    # sobre interface, que é o oposto do que ele existe para proteger (S-04).
                    if re.search(rf"{re.escape(termo)}", minusculo):
                        faltas.append(f"{caminho.name}: {texto[:50]!r} tem {termo!r} -- {destino}")
        self.assertEqual(faltas, [], "Termo em inglês na interface: " + "; ".join(faltas[:10]))

    def test_o_status_da_fila_nao_publica_a_chave_do_arquivo(self) -> None:
        """`pending` em 129 linhas, ao lado de um filtro que dizia "Só pendentes"."""
        self.assertEqual(strings.status_da_fila("pending"), "pendente")
        self.assertEqual(strings.status_da_fila("done"), "revisado")
        self.assertEqual(strings.status_da_fila("skipped"), "pulado")

    def test_um_status_desconhecido_mostra_o_valor_cru(self) -> None:
        """Esconder um estado novo faria a tela mentir sobre o que está gravado."""
        self.assertEqual(strings.status_da_fila("futuro"), "futuro")

    def test_nenhum_rotulo_descreve_a_propria_posicao_na_tela(self) -> None:
        """`ttk.LabelFrame(text="PDF (direita)")` -- o nome do grupo era o lugar dele no layout,
        e ele mente assim que alguém arrasta o divisor."""
        posicoes = ("(direita)", "(esquerda)", "(acima)", "(abaixo)", "painel da direita")
        faltas = [
            f"{caminho.name}: {texto[:40]!r}"
            for caminho in ARQUIVOS_DE_UI
            for texto in _literais_visiveis(caminho)
            if any(posicao in texto.casefold() for posicao in posicoes)
        ]
        self.assertEqual(faltas, [])

    def test_a_navegacao_usa_glifo_e_nao_ascii_imitando_seta(self) -> None:
        """`>|` não é uma seta: são duas letras que lembram uma."""
        ascii_de_navegacao = {"<<", ">>", "|<", ">|", "->"}
        faltas = [
            f"{caminho.name}: {texto!r}"
            for caminho in ARQUIVOS_DE_UI
            for texto in _literais_visiveis(caminho)
            if texto.strip() in ascii_de_navegacao
        ]
        self.assertEqual(faltas, [])

    def test_os_termos_compartilhados_vem_do_vocabulario(self) -> None:
        """O critério da S-04: o que duas telas dizem igual mora aqui, e não em dois literais.

        "Varrer o livro" é o caso que motivou o item -- ele estava escrito à mão nas duas abas,
        com dois verbos diferentes.
        """
        for termo in (strings.VARRER_LIVRO, strings.LADO_A_JOGAR, strings.CABECALHOS_DO_PGN):
            with self.subTest(termo=termo):
                literais = [
                    caminho.name
                    for caminho in ARQUIVOS_DE_UI
                    for texto in _literais_visiveis(caminho)
                    if texto == termo
                ]
                self.assertEqual(literais, [], f"{termo!r} escrito à mão fora de `ui/strings.py`")


class FraseDeRemocaoTests(unittest.TestCase):
    """A pergunta antes de apagar nomeia o que vai sumir (S-170).

    A caixa dizia "Remover 3 amostra(s) do labels.csv?" -- contava e não nomeava. O que está
    prestes a ser apagado é rótulo corrigido à mão, e a S-76 é o registro do que custa neste
    projeto um gesto destrutivo mal confirmado: 1.405 diagramas sobrescritos por um clique.
    """

    def test_uma_amostra_e_dita_pelo_nome(self) -> None:
        frase = strings.frase_de_remocao(["0012_1.png"])
        self.assertIn("0012_1.png", frase)
        self.assertIn("labels.csv", frase)

    def test_varias_amostras_dizem_a_contagem_e_os_nomes(self) -> None:
        """A seleção de um `Treeview` é fácil de estender sem querer; ver quais é a defesa."""
        frase = strings.frase_de_remocao([f"00{i}_1.png" for i in range(3)])
        self.assertIn("3 amostras", frase)
        self.assertIn("000_1.png", frase)
        self.assertIn("002_1.png", frase)

    def test_muitas_amostras_nao_viram_parede_de_texto(self) -> None:
        """Uma pergunta que ninguém lê é uma pergunta que não protege nada."""
        frase = strings.frase_de_remocao([f"{i:04d}_1.png" for i in range(40)])
        self.assertIn("40 amostras", frase)
        self.assertIn("e mais 35", frase)
        self.assertLessEqual(len(frase.splitlines()[-1]), 200)

    def test_o_arquivo_citado_e_o_que_esta_configurado(self) -> None:
        """O caminho do CSV é configurável (S-32): a pergunta não pode cravar `labels.csv`."""
        self.assertIn("outro.csv", strings.frase_de_remocao(["a.png"], arquivo="outro.csv"))

    def test_sem_selecao_a_frase_nao_promete_remocao(self) -> None:
        self.assertIn("Nenhuma amostra selecionada", strings.frase_de_remocao([]))


class DestrutivoTests(unittest.TestCase):
    """Ação destrutiva se distingue sem ler o rótulo (S-170, sobre a S-144).

    "Remover" apaga linha do `labels.csv` -- trabalho humano -- e tinha exatamente a aparência de
    "Abrir no editor". A varredura afirma o par: quem apaga usa o papel `DESTRUTIVO`, e quem não
    apaga não usa.
    """

    QUE_APAGAM = ("Remover", "Quarentena")

    @staticmethod
    def _papel_por_rotulo() -> dict[str, str]:
        """`rótulo do botão -> o papel que ele declara`, lido do `ast` do painel.

        **Era por linha de texto, e a linha deixou de ser uma** (S-445): quando o papel não cabe
        em 120 colunas com o resto, a chamada quebra, e o rótulo e `estilos.DESTRUTIVO` passam a
        morar em linhas diferentes. A propriedade que interessa nunca foi "estão na mesma linha"
        -- é "este botão declara aquele papel".

        **A forma da chamada mudou no corte do Tk (S-506), e a propriedade não.** Era
        `ttk.Button(text=..., style=...)`; é `self._botao(barra, rótulo, função, papel)`, o
        ajudante do painel, com o rótulo no segundo posicional e o papel no quarto.
        """
        fonte = (RAIZ / "src" / "chess_diagram_ocr" / "qt" / "painel_do_dataset.py").read_text(encoding="utf-8")
        achados: dict[str, str] = {}
        for no in ast.walk(ast.parse(fonte)):
            if not (
                isinstance(no, ast.Call)
                and isinstance(no.func, ast.Attribute)
                and no.func.attr == "_botao"
                and len(no.args) >= 4
            ):
                continue
            rotulo = no.args[1]
            if isinstance(rotulo, ast.Constant) and isinstance(rotulo.value, str):
                achados[rotulo.value] = ast.unparse(no.args[3])
        return achados

    def test_os_botoes_que_apagam_pedem_o_papel_destrutivo(self) -> None:
        papeis = self._papel_por_rotulo()
        for rotulo in self.QUE_APAGAM:
            with self.subTest(rotulo=rotulo):
                self.assertIn(rotulo, papeis, "o botão sumiu do painel")
                self.assertIn("estilos.DESTRUTIVO", papeis[rotulo])

    def test_quem_nao_apaga_nao_usa_o_papel_destrutivo(self) -> None:
        """Se tudo é vermelho, nada é: o papel só significa alguma coisa enquanto for raro."""
        for rotulo, estilo in self._papel_por_rotulo().items():
            if "estilos.DESTRUTIVO" not in estilo:
                continue
            with self.subTest(rotulo=rotulo):
                self.assertTrue(
                    rotulo in self.QUE_APAGAM,
                    "botão em `danger` que não apaga nada",
                )


class NoDuplicateVocabularyTests(unittest.TestCase):
    """Os rótulos existiam em dois lugares e já tinham divergido em quatro dos cinco."""

    def test_neither_frontend_keeps_its_own_copy_of_the_side_source_labels(self) -> None:
        for caminho in (
            RAIZ / "examples" / "streamlit_demo.py",
            RAIZ / "src" / "chess_diagram_ocr" / "qt" / "painel_de_resultado.py",
        ):
            with self.subTest(arquivo=caminho.name):
                fonte = caminho.read_text(encoding="utf-8")
                # A frase completa só pode aparecer no vocabulário compartilhado.
                self.assertNotIn(strings.SIDE_SOURCE_LABELS["legality"], fonte)


class SemOrfaTests(unittest.TestCase):
    """A última palavra atada à anterior, e o que isso fecha (F9-C9 §4.7 / F9-C10).

    **A pior órfã desta janela era a primeira frase que o produto mostra.** O crítico do ciclo 9
    mediu `'inteira.'` sozinha numa linha, **5,7 % de uma medida de 627 px**, centrada -- a última
    linha da `MENSAGEM_VAZIA`. Medido com o mesmo instrumento antes e depois
    (`benchmarks/reports/ui/c10/c10_orfas.py`, 3 peles x 3 larguras x 2 estados): **6 de 24
    parágrafos com órfã, e 0 depois**.
    """

    def test_a_ultima_palavra_fica_atada_a_anterior(self) -> None:
        self.assertEqual(
            strings.sem_orfa("ler a página inteira."),
            f"ler a página{strings.ESPACO_INQUEBRAVEL}inteira.",
        )

    def test_so_a_ultima(self) -> None:
        """Atar mais do que o necessário empurra a quebra para trás e afrouxa a linha anterior --
        troca uma falta por outra."""
        atada = strings.sem_orfa("uma frase de cinco palavras")
        self.assertEqual(atada.count(strings.ESPACO_INQUEBRAVEL), 1)
        self.assertTrue(atada.endswith(f"cinco{strings.ESPACO_INQUEBRAVEL}palavras"))

    def test_uma_palavra_so_volta_inalterada(self) -> None:
        """Não há a que atar, e inventar um espaço mudaria o texto."""
        self.assertEqual(strings.sem_orfa("Salvar"), "Salvar")
        self.assertEqual(strings.sem_orfa(""), "")

    def test_o_texto_visivel_nao_muda(self) -> None:
        """O espaço inquebrável **é** um espaço para quem lê: trocar por espaço comum devolve o
        original. Se isto falhar, o conserto de composição virou uma mudança de redação."""
        for frase in (
            strings.GALERIA_VAZIA_FRASE,
            strings.REVISAO_VAZIA_FRASE,
            strings.TEXTO_VAZIO_FRASE,
            strings.DATASET_LENDO_FRASE,
        ):
            with self.subTest(frase=frase[:32]):
                self.assertIn(strings.ESPACO_INQUEBRAVEL, frase)
                self.assertEqual(frase.split(), frase.replace(" ", " ").split())

    def test_as_frases_de_estado_vazio_estao_atadas(self) -> None:
        """A regra vale para as frases longas que o produto **desenha com quebra** -- são elas
        que têm última linha. Um rótulo de botão não quebra e não entra."""
        for nome in (
            "GALERIA_VAZIA_FRASE",
            "REVISAO_VAZIA_FRASE",
            "TEXTO_VAZIO_FRASE",
            "DATASET_LENDO_FRASE",
            "GALERIA_LEGENDA_VAZIA",
        ):
            with self.subTest(constante=nome):
                self.assertIn(strings.ESPACO_INQUEBRAVEL, getattr(strings, nome))

    def test_a_mensagem_vazia_do_resultado_tambem(self) -> None:
        from chess_diagram_ocr.qt import painel_de_resultado

        self.assertIn(strings.ESPACO_INQUEBRAVEL, painel_de_resultado.MENSAGEM_VAZIA)


if __name__ == "__main__":
    unittest.main()
