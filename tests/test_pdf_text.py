from __future__ import annotations

import unittest

import chess
import fitz

from chess_diagram_ocr.pdf_text import (
    DEFAULT_RADIUS_PT,
    TextLine,
    _is_diagram_font_row,
    assign_lines_to_diagrams,
    blocks_near,
    context_from_lines,
    contexts_for_page,
    dominant_placement,
    fold,
    is_diagram_font,
    page_text_lines,
    parse_context,
    running_page_number,
)

PAGE_WIDTH, PAGE_HEIGHT = 595.0, 842.0


def line(text: str, x0: float, y0: float, x1: float, y1: float, *, block_words: int = 4, group: int = 0) -> TextLine:
    return TextLine(text=text, bbox=(x0, y0, x1, y1), block_words=block_words, group_id=group)


def pdf_with_lines(pages: list[list[tuple[str, float, float]]]) -> fitz.Document:
    """PDF gerado em memória com o texto dado em cada página.

    Fixture sintético em vez de arquivo versionado pelo mesmo motivo de `test_detection`:
    o repositório não versiona PDF, e o que estes testes exercitam é geometria de texto.
    """
    doc = fitz.open()
    for lines in pages:
        page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        for text, x, y in lines:
            page.insert_text((x, y), text, fontsize=11)
    return doc


def write_in_font(page: fitz.Page, font: str, items: list[tuple[str, float, float]], size: float = 24.0) -> None:
    """Escreve `items` na página declarando `font` como nome da fonte.

    A fonte entra **sem programa embutido**, e é por isso que o nome chega inteiro do outro
    lado: com um programa embutido o MuPDF reporta o nome interno dele (`NimbusSans-Regular`)
    e não o `/BaseFont` do PDF. Sem programa não há nome interno, e o `get_text("dict")`
    devolve o que o PDF declara -- que é justamente o que `_is_diagram_font_row` lê.

    Não versionar uma `ChessMerida.ttf` só para o teste é deliberado: o repositório não
    versiona binário de fonte, e o que se exercita aqui é o filtro, não o desenho do glifo.
    """
    doc = page.parent
    font_xref = doc.get_new_xref()
    doc.update_object(
        font_xref,
        f"<< /Type /Font /Subtype /TrueType /BaseFont /{font} "
        "/FirstChar 32 /LastChar 255 /Encoding /WinAnsiEncoding >>",
    )
    resources = int(doc.xref_get_key(page.xref, "Resources")[1].split()[0])
    alias = f"Cvoff{font_xref}"
    doc.xref_set_key(resources, f"Font/{alias}", f"{font_xref} 0 R")

    if not page.get_contents():
        page.insert_text((0.0, 0.0), " ", fontsize=1)
    contents = page.get_contents()[0]
    operators = "\n".join(
        f"BT /{alias} {size} Tf {x} {PAGE_HEIGHT - y} Td ({text}) Tj ET" for text, x, y in items
    )
    doc.update_stream(contents, doc.xref_stream(contents) + b"\n" + operators.encode("latin-1"))


class SideToMovePatternTests(unittest.TestCase):
    """Tabela de legendas nos três idiomas do acervo, com as armadilhas medidas."""

    DECLARACOES = [
        # português -- as três formas que o `400 Quebra-cabeças` usa de verdade
        # As cinco formas levantadas nos 400 exercicios do livro. Cobrir so as duas que a
        # S-16 listou deixava 39 exercicios sem lado a jogar.
        ("11: Brancas jogam *", chess.WHITE),
        ("31: Jogada das pretas **", chess.BLACK),
        ("22: Jogada de pretas *", chess.BLACK),
        ("40: Jogar de pretas **", chess.BLACK),
        ("91: Pretas jogam ****", chess.BLACK),
        ("77: Jogam as pretas", chess.BLACK),
        ("As negras jogam e ganham", chess.BLACK),
        ("É a vez das brancas", chess.WHITE),
        # inglês
        ("White to move", chess.WHITE),
        ("Black to move and win", chess.BLACK),
        ("White to play and win", chess.WHITE),
        ("Black plays", chess.BLACK),
        # alemão -- o ß precisa sobreviver à normalização
        ("Weiß am Zug", chess.WHITE),
        ("Schwarz am Zug", chess.BLACK),
        ("Weiss zieht und gewinnt", chess.WHITE),
        ("Schwarz zieht", chess.BLACK),
        # espanhol, que o `Koblenz` usa
        ("Juegan las blancas", chess.WHITE),
        ("Juegan las negras", chess.BLACK),
        # símbolos
        ("◻ 12", chess.WHITE),
        ("◼ 13", chess.BLACK),
    ]

    ARMADILHAS = [
        # Passado: fala do resultado da partida, nao de quem esta na vez.
        "White won the game after a long endgame",
        "Black lost on time",
        # Condicional: fala de uma variante imaginaria. Medido no `Melhores Finais`.
        "Se as brancas jogarem 32 f2xg2, elas perdem",
        "If White plays 20.Nd3 the position collapses",
        # Nome de jogador com a palavra dentro.
        "White - Blackburne, Londres 1883",
        # Sem declaracao nenhuma.
        "Bremen 1998",
        "",
    ]

    def test_declaracoes_sao_reconhecidas(self) -> None:
        for caption, expected in self.DECLARACOES:
            with self.subTest(caption=caption):
                context = parse_context(caption)
                self.assertEqual(context.side_to_move, expected)
                self.assertTrue(context.side_to_move_evidence)

    def test_armadilhas_nao_viram_declaracao(self) -> None:
        for caption in self.ARMADILHAS:
            with self.subTest(caption=caption):
                self.assertIsNone(parse_context(caption).side_to_move)

    def test_declaracoes_opostas_na_mesma_legenda_nao_decidem(self) -> None:
        """Página de soluções lista vários exercícios. Duas respostas é o mesmo que nenhuma."""
        self.assertIsNone(parse_context("11: Brancas jogam\n12: Pretas jogam").side_to_move)

    def test_fold_normaliza_acento_caixa_e_travessao(self) -> None:
        self.assertEqual(fold("Weiß  am   ZUG"), "weiss am zug")
        self.assertEqual(fold("Morphy – De Riviere"), "morphy - de riviere")


class CaptionParsingTests(unittest.TestCase):
    def test_schiller_numero_jogadores_evento_e_ano(self) -> None:
        context = parse_context("5\nMorphy-De Riviere\nParis, 1858")

        self.assertEqual(context.exercise_number, 5)
        self.assertEqual(context.players, ("Morphy", "De Riviere"))
        self.assertEqual(context.event, "Paris")
        self.assertEqual(context.year, 1858)

    def test_aagaard_jogadores_e_evento_sem_numero(self) -> None:
        context = parse_context("Hickl - Yusupov\nBremen 1998")

        self.assertEqual(context.players, ("Hickl", "Yusupov"))
        self.assertEqual(context.event, "Bremen")
        self.assertEqual(context.year, 1998)
        self.assertIsNone(context.exercise_number)

    def test_karpov_numero_grudado_nos_jogadores(self) -> None:
        context = parse_context("N!!79. Steinitz - Bird")

        self.assertEqual(context.exercise_number, 79)
        self.assertEqual(context.players, ("Steinitz", "Bird"))

    def test_numero_partido_pelo_ocr(self) -> None:
        """`1 19 Bartrina - Ghitescu`: o AAGAARD sai assim, e é um dos livros do critério."""
        context = parse_context("1 19 Bartrina - Ghitescu")

        self.assertEqual(context.exercise_number, 119)
        self.assertEqual(context.players, ("Bartrina", "Ghitescu"))

    def test_numero_da_pagina_impressa_nao_vira_numero_de_exercicio(self) -> None:
        """O caso `Reinfeld 1001`: a única linha da página é o número impresso."""
        self.assertIsNone(parse_context("10", page_number=10).exercise_number)
        self.assertEqual(parse_context("10", page_number=37).exercise_number, 10)

    def test_lance_nao_vira_jogadores_nem_evento(self) -> None:
        context = parse_context("14.ILl5 bxa4 15.Ylrh5!")

        self.assertIsNone(context.players)
        self.assertIsNone(context.event)

    def test_campo_nao_declarado_sai_none(self) -> None:
        context = parse_context("Brancas jogam")

        self.assertEqual(context.side_to_move, chess.WHITE)
        self.assertIsNone(context.players)
        self.assertIsNone(context.event)
        self.assertIsNone(context.year)
        self.assertIsNone(context.exercise_number)

    def test_legenda_vazia_produz_contexto_vazio(self) -> None:
        self.assertTrue(parse_context("").is_empty)
        self.assertTrue(parse_context("   \n  ").is_empty)


class ProseVersusCaptionTests(unittest.TestCase):
    """Precisão sem perder o `AAGAARD`, que gruda o enunciado no comentário."""

    def test_padrao_no_meio_de_paragrafo_nao_conta(self) -> None:
        nearby = assign_lines_to_diagrams(
            [line("it was possible for White to play 20.Nd3", 10, 10, 200, 22, block_words=90)],
            [(10.0, 40.0, 200.0, 230.0)],
        )

        self.assertIsNone(context_from_lines(nearby[0]).side_to_move)

    def test_padrao_abrindo_paragrafo_conta(self) -> None:
        nearby = assign_lines_to_diagrams(
            [line("White to play - Do you like having pieces", 10, 10, 200, 22, block_words=90)],
            [(10.0, 40.0, 200.0, 230.0)],
        )

        self.assertEqual(context_from_lines(nearby[0]).side_to_move, chess.WHITE)

    def test_legenda_curta_conta_em_qualquer_posicao_da_linha(self) -> None:
        nearby = assign_lines_to_diagrams(
            [line("31: Jogada das pretas **", 10, 240, 200, 252, block_words=4)],
            [(10.0, 40.0, 200.0, 230.0)],
        )

        self.assertEqual(context_from_lines(nearby[0]).side_to_move, chess.BLACK)


class GeometryTests(unittest.TestCase):
    def test_legenda_da_coluna_vizinha_nao_e_adotada(self) -> None:
        """Karpov: um bloco cobre as legendas das duas colunas, em x disjuntos."""
        lines = [
            line("N!!79. Steinitz - Bird", 82, 45, 181, 56, group=0),
            line("N!!80. Steinitz - Mortimer", 278, 45, 402, 56, group=1),
        ]
        esquerda = (56.0, 66.0, 203.0, 225.0)
        direita = (264.0, 66.0, 411.0, 207.0)

        buckets = assign_lines_to_diagrams(lines, [esquerda, direita])

        self.assertEqual([item.text for item in buckets[0]], ["N!!79. Steinitz - Bird"])
        self.assertEqual([item.text for item in buckets[1]], ["N!!80. Steinitz - Mortimer"])

    def test_legenda_acima_nao_e_roubada_pelo_diagrama_de_cima(self) -> None:
        """O deslocamento de um exercício, medido no Karpov e no Schiller.

        As legendas ficam acima; o vão acima do diagrama (10 pt) é maior que o vão abaixo
        (7 pt). Por distância pura, cada diagrama fica com a legenda do seguinte.
        """
        lines = [
            line("N!!79. Steinitz - Bird", 82, 45, 181, 56, group=0),
            line("N!!81. Steinitz - Elson", 82, 232, 181, 243, group=1),
            line("N!!83. Steinitz - Zukertort", 82, 418, 181, 429, group=2),
        ]
        diagramas = [(56.0, 66.0, 203.0, 225.0), (56.0, 252.0, 203.0, 410.0), (56.0, 440.0, 203.0, 594.0)]

        buckets = assign_lines_to_diagrams(lines, diagramas)

        self.assertEqual([context_from_lines(bucket).exercise_number for bucket in buckets], [79, 81, 83])

    def test_bloco_de_legenda_nao_e_repartido_entre_diagramas(self) -> None:
        """Schiller: número, jogadores e evento são um bloco, e o número anda com eles."""
        lines = [
            line("5", 57, 33, 63, 44, group=0),
            line("Morphy-De Riviere", 57, 45, 147, 56, group=0),
            line("Paris, 1858", 57, 60, 120, 72, group=0),
            line("6", 53, 200, 59, 211, group=1),
            line("Morphy-Mongredien", 53, 212, 151, 223, group=1),
            line("Paris, 1859", 53, 228, 116, 239, group=1),
        ]
        diagramas = [(46.0, 76.0, 156.0, 185.0), (45.0, 243.0, 155.0, 352.0)]

        contexts = [context_from_lines(bucket) for bucket in assign_lines_to_diagrams(lines, diagramas)]

        self.assertEqual([c.exercise_number for c in contexts], [5, 6])
        self.assertEqual([c.players for c in contexts], [("Morphy", "De Riviere"), ("Morphy", "Mongredien")])

    def test_legenda_abaixo_quando_e_ai_que_o_livro_a_poe(self) -> None:
        """400 Quebra-cabeças: uma legenda, abaixo, e nada acima."""
        lines = [line("11: Brancas jogam *", 233, 308, 363, 325, group=0)]
        diagramas = [(103.0, 72.0, 493.0, 297.0)]

        buckets = assign_lines_to_diagrams(lines, diagramas)

        self.assertEqual(buckets[0][0].placement, "below")
        self.assertEqual(context_from_lines(buckets[0]).exercise_number, 11)

    def test_linha_fora_do_raio_nao_entra(self) -> None:
        lines = [line("Bremen 1998", 10, 10, 90, 22)]
        buckets = assign_lines_to_diagrams(lines, [(10.0, 10.0 + DEFAULT_RADIUS_PT + 40.0, 200.0, 300.0)])

        self.assertEqual(buckets[0], [])

    def test_dominant_placement_sem_texto_nenhum(self) -> None:
        self.assertIsNone(dominant_placement([], {}, 2))


class PageTextTests(unittest.TestCase):
    def test_cabecalho_e_rodape_correntes_sao_descartados(self) -> None:
        doc = pdf_with_lines(
            [
                [
                    ("The Defensive Thinking Frame", 150, 14),  # topo: 1,6% da altura
                    ("Hickl - Yusupov", 40, 400),
                    ("20", 300, 820),  # rodape: 97% da altura
                ]
            ]
        )
        textos = [item.text for item in page_text_lines(doc[0])]
        doc.close()

        self.assertIn("Hickl - Yusupov", textos)
        self.assertNotIn("The Defensive Thinking Frame", textos)
        self.assertNotIn("20", textos)

    def test_tabuleiro_desenhado_com_fonte_nao_vira_legenda(self) -> None:
        """Polgar 5334: o diagrama é texto, e as filas ocupariam a legenda inteira."""
        doc = pdf_with_lines(
            [
                [
                    ("31", 90, 100),
                    ("0Z0Z0mkZ", 40, 130),
                    ("Z0Z0Z0a0", 40, 160),
                    ("0Z0Z0Z0Z", 40, 190),
                ]
            ]
        )
        textos = [item.text for item in page_text_lines(doc[0])]
        doc.close()

        self.assertEqual(textos, ["31"])


    def test_blocks_near_ordena_por_distancia(self) -> None:
        doc = pdf_with_lines([[("perto", 100, 290), ("longe", 100, 340)]])
        textos = blocks_near(doc[0], (90.0, 100.0, 300.0, 300.0), radius_pt=60.0)
        doc.close()

        self.assertEqual(textos, ["perto", "longe"])

    def test_contexts_for_page_um_contexto_por_diagrama(self) -> None:
        doc = pdf_with_lines([[("11: Brancas jogam", 120, 320)]])
        contexts = contexts_for_page(doc[0], [(100.0, 100.0, 400.0, 300.0), (100.0, 500.0, 400.0, 700.0)])
        doc.close()

        self.assertEqual(len(contexts), 2)
        self.assertEqual(contexts[0].side_to_move, chess.WHITE)
        self.assertTrue(contexts[1].is_empty)

    def test_contexts_for_page_sem_diagramas(self) -> None:
        doc = pdf_with_lines([[("qualquer coisa", 100, 300)]])
        self.assertEqual(contexts_for_page(doc[0], []), [])
        doc.close()


class DiagramFontTests(unittest.TestCase):
    """O tabuleiro impresso como texto, nas duas codificações que o acervo tem (S-217)."""

    NOMES_DE_DIAGRAMA = [
        # medidos no acervo: as tres fontes que desenham tabuleiro, em 6 livros
        "SkakNew-Diagram",
        "ChessMerida",
        "Chess-Merida",
        # o prefixo de subconjunto do PDF nao pode esconder o nome
        "ABCDEF+ChessMerida",
    ]

    NOMES_QUE_NAO_SAO = [
        # figurina: desenha a peca no meio do lance, e o texto ao redor e prosa de verdade
        "SkakNew-Figurine",
        "SkakNew-Figurine-Bold",
        "SemFigNormal",
        "SemFigBold",
        # as fontes de prosa dos mesmos livros
        "TimesNewRomanPSMT",
        "CMSS12",
        "Cambria",
        "GlyphLessFont",
        "ArialMT",
        "Helvetica",
    ]

    FILAS = [
        # (texto da linha, fonte, e uma nota do porque)
        # `Polgar`: casa vazia e `0`/`Z`, e o crivo de densidade ja pegava
        ("0Z0Z0mkZ", "SkakNew-Diagram"),
        ("Z0Z0Z0a0", "SkakNew-Diagram"),
        # `Polgar` de novo, a fila que ESCAPAVA: so tres casas vazias, e o crivo pedia quatro
        ("0l0o0ORL", "SkakNew-Diagram"),
        # os quatro livros `_hq`: casa vazia e `+`, a codificacao do export do Lichess
        ("t+v+t+l+", "ChessMerida"),
        ("+p+n+p+", "ChessMerida"),
        ("Kb+r", "ChessMerida"),
        ("OoO", "ChessMerida"),
        # `Dvoretsky`: casa vazia e `+` ou `*`, e a fila chega partida em um caractere
        ("*", "Chess-Merida"),
        ("+", "Chess-Merida"),
        ("P", "Chess-Merida"),
        ("k", "Chess-Merida"),
        ("B", "Chess-Merida"),
    ]

    LEGENDAS = [
        # o mesmo texto curto, na fonte de prosa: e legenda, e nao pode cair
        ("B", "TimesNewRomanPSMT"),
        ("P", "TimesNewRomanPSMT"),
        ("8", "ArialMT"),
        ("Steinitz", "TimesNewRomanPSMT"),
        ("Bremen 1998", "Cambria"),
        ("11: Brancas jogam *", "TimesNewRomanPSMT"),
        # lance em figurina: o `X` e uma captura, e apagar a linha apagaria o lance
        ("NXe3", "SkakNew-Figurine"),
        ("Qd5", "SkakNew-Figurine"),
    ]

    def test_nome_de_fonte_de_diagrama(self) -> None:
        for nome in self.NOMES_DE_DIAGRAMA:
            with self.subTest(nome=nome):
                self.assertTrue(is_diagram_font(nome))

    def test_nome_que_nao_e_de_diagrama(self) -> None:
        for nome in self.NOMES_QUE_NAO_SAO:
            with self.subTest(nome=nome):
                self.assertFalse(is_diagram_font(nome))

    def test_fila_de_tabuleiro_cai_pela_fonte(self) -> None:
        for texto, fonte in self.FILAS:
            with self.subTest(texto=texto, fonte=fonte):
                self.assertTrue(_is_diagram_font_row(texto, [fonte]))

    def test_legenda_na_fonte_de_prosa_nao_cai(self) -> None:
        """O risco desta família de filtro é sempre o falso positivo, e ele mora aqui.

        `B` sozinho é o marcador de *pretas jogam* do `Dvoretsky` -- exatamente o dado que a
        S-16 existe para achar -- e também é o bispo do tabuleiro dele. Só a fonte separa os
        dois, e nas páginas 172 e 262 do livro os dois estão na mesma página.
        """
        for texto, fonte in self.LEGENDAS:
            with self.subTest(texto=texto, fonte=fonte):
                self.assertFalse(_is_diagram_font_row(texto, [fonte]))

    def test_linha_que_mistura_fonte_de_diagrama_com_prosa_fica(self) -> None:
        """Nenhuma linha do acervo mistura (0 de 229.510), e é por isso que a regra é `all`.

        Se um livro ainda não medido grudar um glifo de tabuleiro numa legenda, o que se
        perde é o glifo -- e não a legenda.
        """
        self.assertFalse(_is_diagram_font_row("+ Steinitz", ["ChessMerida", "TimesNewRomanPSMT"]))

    def test_sem_fonte_vale_o_crivo_de_texto(self) -> None:
        """Linha do OCR da S-43 não tem fonte, e o crivo de densidade continua valendo."""
        self.assertTrue(_is_diagram_font_row("0Z0Z0mkZ"))
        self.assertFalse(_is_diagram_font_row("Steinitz"))

    def test_lichess_nao_ocupa_a_legenda(self) -> None:
        """`1001 Sacrificios` p.169: a legenda vinha com as filas em `ChessMerida`."""
        doc = pdf_with_lines([[("158", 200, 100), ("Pretas jogam", 200, 480)]])
        write_in_font(
            doc[0],
            "ChessMerida",
            [("t+v+t+l+", 200, 140), ("OoO", 200, 180), ("+p+n+p+", 200, 220), ("Kb+r", 200, 260)],
        )
        textos = [item.text for item in page_text_lines(doc[0])]
        doc.close()

        self.assertEqual(textos, ["158", "Pretas jogam"])

    def test_marcador_de_lado_sobrevive_ao_bispo_na_mesma_pagina(self) -> None:
        """`Dvoretsky` p.172: um `B` é o bispo do tabuleiro, o outro é *Black to move*."""
        doc = pdf_with_lines([[("B", 300, 350), ("Golberg - Zhuk", 300, 400)]])
        write_in_font(doc[0], "Chess-Merida", [("B", 200, 120), ("*", 200, 160), ("+", 200, 200)])
        textos = [item.text for item in page_text_lines(doc[0])]
        doc.close()

        self.assertEqual(textos.count("B"), 1)
        self.assertIn("Golberg - Zhuk", textos)

    def test_digito_de_fila_em_bloco_proprio_nao_vira_legenda(self) -> None:
        """`Polgar` p.178: cada dígito de fila é um bloco de uma linha, e os oito passavam.

        A contagem por bloco nunca disparava -- é `>= 6` num bloco que tem 1. O que os
        identifica é a faixa: alinhados em x, e os oito distintos.
        """
        doc = pdf_with_lines([[("962", 90, 100)] + [(str(rank), 60, 140 + 30 * i) for i, rank in enumerate(range(8, 0, -1))]])
        textos = [item.text for item in page_text_lines(doc[0])]
        doc.close()

        self.assertEqual(textos, ["962"])

    def test_coluna_de_resultados_de_torneio_nao_e_borda_de_tabuleiro(self) -> None:
        """`1937 Kemeri`: a tabela de cruzamento tem dezenas de `1` soltos, e são resultados.

        É o caso que impede a regra de ser "conte a página inteira": alinhados eles são,
        mas repetidos -- e a borda de um tabuleiro traz cada fila uma vez só.
        """
        doc = pdf_with_lines([[("Flohr", 200, 120)] + [("1", 60, 140 + 24 * i) for i in range(9)]])
        textos = [item.text for item in page_text_lines(doc[0])]
        doc.close()

        self.assertEqual(textos.count("1"), 9)
        self.assertIn("Flohr", textos)


class RunningPageNumberTests(unittest.TestCase):
    def test_numero_consecutivo_na_mesma_coluna_e_numero_de_pagina(self) -> None:
        doc = pdf_with_lines([[("10", 300, 120)], [("11", 300, 120)], [("12", 300, 120)]])
        try:
            self.assertEqual(running_page_number(doc, 0), 10)
            self.assertEqual(running_page_number(doc, 1), 11)
        finally:
            doc.close()

    def test_deslocamento_pode_variar_ao_longo_do_livro(self) -> None:
        """O `Reinfeld` vai de -10 na página 46 a -29 na 1012: não há constante afim."""
        doc = pdf_with_lines([[("40", 300, 120)], [("41", 300, 120)], [("41", 300, 120)], [("42", 300, 120)]])
        try:
            self.assertEqual(running_page_number(doc, 2), 41)
            self.assertEqual(running_page_number(doc, 3), 42)
        finally:
            doc.close()

    def test_numero_de_exercicio_em_coluna_diferente_nao_e_confundido(self) -> None:
        """O `400 Quebra-cabeças` numera exercício e página juntos, e os dois andam de 1 em 1."""
        doc = pdf_with_lines(
            [
                [("11", 60, 300), ("20", 300, 780)],
                [("12", 60, 300), ("21", 300, 780)],
            ]
        )
        try:
            self.assertEqual(running_page_number(doc, 0), 20)
        finally:
            doc.close()

    def test_sem_numeracao_legivel_devolve_none(self) -> None:
        doc = pdf_with_lines([[("z_o", 300, 120)], [("ZI", 300, 120)]])
        try:
            self.assertIsNone(running_page_number(doc, 0))
        finally:
            doc.close()


if __name__ == "__main__":
    unittest.main()
