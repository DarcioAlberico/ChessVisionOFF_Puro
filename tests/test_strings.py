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
    for caminho in sorted((RAIZ / "src" / "chess_diagram_ocr" / "ui").glob("*.py"))
    if caminho.name != "strings.py"
] + [RAIZ / "app_tkinter.py", RAIZ / "examples" / "streamlit_demo.py"]

PERMITIDOS = {
    # Chaves, nomes de campo e identificadores que por acaso batem com uma palavra da lista.
    "sao",
}
"""Exceções. Vazia de propósito quanto a texto de tela: uma exceção ali seria a string que
o usuário lê errada."""


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

    def test_the_word_list_itself_is_unaccented(self) -> None:
        """Ela lista as formas **erradas**; acentuá-la faria o teste acima nunca falhar."""
        for palavra in strings.WORDS_REQUIRING_ACCENTS:
            with self.subTest(palavra=palavra):
                self.assertEqual(palavra, palavra.encode("ascii", "ignore").decode("ascii"))


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

    def test_os_botoes_que_apagam_pedem_o_papel_destrutivo(self) -> None:
        fonte = (RAIZ / "src" / "chess_diagram_ocr" / "ui" / "dataset_panel.py").read_text(encoding="utf-8")
        for rotulo in self.QUE_APAGAM:
            with self.subTest(rotulo=rotulo):
                linha = next(texto for texto in fonte.splitlines() if f'text="{rotulo}"' in texto)
                self.assertIn("estilos.DESTRUTIVO", linha)

    def test_quem_nao_apaga_nao_usa_o_papel_destrutivo(self) -> None:
        """Se tudo é vermelho, nada é: o papel só significa alguma coisa enquanto for raro."""
        fonte = (RAIZ / "src" / "chess_diagram_ocr" / "ui" / "dataset_panel.py").read_text(encoding="utf-8")
        for linha in fonte.splitlines():
            if "estilos.DESTRUTIVO" not in linha or "text=" not in linha:
                continue
            with self.subTest(linha=linha.strip()[:60]):
                self.assertTrue(
                    any(f'text="{rotulo}"' in linha for rotulo in self.QUE_APAGAM),
                    "botão em `danger` que não apaga nada",
                )


class NoDuplicateVocabularyTests(unittest.TestCase):
    """Os rótulos existiam em dois lugares e já tinham divergido em quatro dos cinco."""

    def test_neither_frontend_keeps_its_own_copy_of_the_side_source_labels(self) -> None:
        for caminho in (
            RAIZ / "examples" / "streamlit_demo.py",
            RAIZ / "src" / "chess_diagram_ocr" / "ui" / "result_panel.py",
        ):
            with self.subTest(arquivo=caminho.name):
                fonte = caminho.read_text(encoding="utf-8")
                # A frase completa só pode aparecer no vocabulário compartilhado.
                self.assertNotIn(strings.SIDE_SOURCE_LABELS["legality"], fonte)


if __name__ == "__main__":
    unittest.main()
