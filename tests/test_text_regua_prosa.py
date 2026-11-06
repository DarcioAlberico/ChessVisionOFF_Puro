"""A régua da prosa (S-700, S-701): o alinhamento contra a força bruta, e a tabela dos tokens que já enganaram."""

from __future__ import annotations

import ast
import random
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from chess_diagram_ocr.text import regua_prosa as regua

RAIZ = Path(__file__).resolve().parents[1]


def _levenshtein(a: str, b: str) -> int:
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1]


class AlinhamentoTests(unittest.TestCase):
    def test_confere_com_a_forca_bruta_em_500_pares(self) -> None:
        sorteio = random.Random(20261106)
        alfabeto = "ab cd\nçé♔1."
        for _ in range(500):
            a = "".join(sorteio.choice(alfabeto) for _ in range(sorteio.randint(0, 40)))
            b = "".join(sorteio.choice(alfabeto) for _ in range(sorteio.randint(0, 40)))
            pares = regua.alinhar(a, b)
            custo = sum(1 for i, j in pares if i == -1 or j == -1 or a[i] != b[j])
            self.assertEqual(_levenshtein(a, b), custo, (a, b))
            self.assertEqual(list(range(len(a))), [i for i, _ in pares if i != -1], (a, b))
            self.assertEqual(list(range(len(b))), [j for _, j in pares if j != -1], (a, b))

    def test_letra_fora_do_bmp_conta_uma_vez(self) -> None:
        self.assertEqual([(0, 0), (1, 1)], regua.alinhar("a𝐛", "a𝐛"))

    def test_lados_vazios(self) -> None:
        self.assertEqual([(-1, 0), (-1, 1)], regua.alinhar("", "ab"))
        self.assertEqual([(0, -1), (1, -1)], regua.alinhar("ab", ""))
        self.assertEqual([], regua.alinhar("", ""))


class PlacarTests(unittest.TestCase):
    def test_palavra_colada_custa_no_cer_de_prosa_e_no_wer(self) -> None:
        p = regua.pontuar("if the", "ifthe")
        self.assertEqual(1, p.erros[regua.PROSA], "o separador entre dois tokens de prosa é prosa")
        self.assertEqual(6, p.total[regua.PROSA])
        self.assertEqual((1, 1, 0, 2), (p.wer_s, p.wer_d, p.wer_i, p.wer_n))
        self.assertEqual(1.0, p.wer_prosa())

    def test_token_inventado_custa_uma_insercao_no_wer(self) -> None:
        p = regua.pontuar("if the", "if xyz the")
        self.assertEqual((0, 0, 1, 2), (p.wer_s, p.wer_d, p.wer_i, p.wer_n))

    def test_insercao_vai_a_classe_do_proximo_caractere(self) -> None:
        p = regua.pontuar("Nf3 casa", "Nf3 Xcasa")
        self.assertEqual(1, p.insercoes)
        self.assertEqual({regua.PROSA: 1}, p.insercoes_por_classe)
        self.assertEqual(1, p.erros[regua.PROSA])
        self.assertEqual(0, p.erros[regua.NOTACAO])

    def test_insercao_no_fim_vai_a_classe_do_ultimo(self) -> None:
        p = regua.pontuar("casa", "casaX")
        self.assertEqual({regua.PROSA: 1}, p.insercoes_por_classe)
        p = regua.pontuar("Nf3", "Nf3XY")
        self.assertEqual({regua.NOTACAO: 2}, p.insercoes_por_classe)

    def test_referencia_vazia_conta_a_insercao(self) -> None:
        p = regua.pontuar("", "abc")
        self.assertEqual(3, p.insercoes)
        self.assertEqual(3, p.erros[regua.ESPACO])

    def test_erro_de_notacao_nao_entra_na_prosa(self) -> None:
        p = regua.pontuar("casa Nf3 casa", "casa N13 casa")
        self.assertEqual(0, p.erros[regua.PROSA])
        self.assertEqual(1, p.erros[regua.NOTACAO])

    def test_figurina_revocacao_e_precisao_nas_posicoes_alinhadas(self) -> None:
        p = regua.pontuar("Nf3 Bb5", "Nf3 ab5")
        self.assertEqual((2, 1, 1), (p.fig_ref, p.fig_hip, p.fig_tp))

    def test_troca_palavra_a_palavra(self) -> None:
        p = regua.pontuar("will go", "wi.. go")
        self.assertEqual({"will -> wi..": 1}, p.trocas)
        self.assertEqual(1, p.palavras_prosa_certas)

    def test_palavra_certa_colada_na_vizinha_nao_e_certa(self) -> None:
        p = regua.pontuar("if the", "ifthe")
        self.assertEqual(0, p.palavras_prosa_certas)

    def test_somar_nao_perde_campo(self) -> None:
        a, b = regua.pontuar("if the", "ifthe"), regua.pontuar("Nf3 casa", "N13 Xcasa")
        soma = regua.Placar()
        soma.somar(a)
        soma.somar(b)
        self.assertEqual(a.wer_n + b.wer_n, soma.wer_n)
        self.assertEqual(a.insercoes + b.insercoes, soma.insercoes)
        self.assertEqual(a.fig_ref + b.fig_ref, soma.fig_ref)
        self.assertEqual(a.erros[regua.NOTACAO] + b.erros[regua.NOTACAO], soma.erros[regua.NOTACAO])
        self.assertEqual(a.insercoes_por_classe.get(regua.PROSA, 0) + b.insercoes_por_classe.get(regua.PROSA, 0),
                         soma.insercoes_por_classe.get(regua.PROSA, 0))

    def test_para_dict_tem_as_chaves_do_protocolo(self) -> None:
        d = regua.pontuar("if the", "ifthe").para_dict()
        self.assertEqual({"erros", "total", "pp", "ppc", "trocas", "insercoes", "insercoes_por_classe", "wer", "fig"}, set(d))
        self.assertIn(regua.RUIDO, d["erros"])


class NormalizacaoTests(unittest.TestCase):
    def test_idempotente(self) -> None:
        sorteio = random.Random(7)
        alfabeto = "ab -\n\t…—“”ﬁ♔♙ ­é"
        for _ in range(2000):
            texto = "".join(sorteio.choice(alfabeto) for _ in range(sorteio.randint(0, 30)))
            for modo in regua.MODOS:
                uma = regua.normalizar(texto, modo)
                self.assertEqual(uma, regua.normalizar(uma, modo), repr(texto))

    def test_os_casos_em_que_o_prototipo_nao_era_idempotente(self) -> None:
        self.assertEqual("ab", regua.normalizar("a-\n\nb", regua.CRU))
        self.assertEqual("abc", regua.normalizar("a-\nb-\nc", regua.CRU))

    def test_tip_e_cru(self) -> None:
        self.assertEqual("o “fim”", regua.normalizar("o  “fim”", regua.CRU))
        self.assertEqual('o "fim"', regua.normalizar("o  “fim”", regua.TIP))
        self.assertEqual("a-b", regua.normalizar("a—b", regua.TIP))
        self.assertEqual("a—b", regua.normalizar("a—b", regua.CRU))

    def test_figurina_vira_a_letra_da_lingua_e_o_peao_some(self) -> None:
        figura = "♕e4 ♙d5"
        for lingua, esperado in (("eng", "Qe4 d5"), ("por", "De4 d5"), ("spa", "De4 d5"), ("deu", "De4 d5"),
                                 ("rus", "Фe4 d5"), ("pt", "De4 d5"), ("por+eng", "De4 d5")):
            self.assertEqual(esperado, regua.normalizar(figura, regua.TIP, lingua), lingua)
        self.assertEqual("Сe4", regua.normalizar("♗e4", regua.TIP, "rus"))
        self.assertEqual("Кe4", regua.normalizar("♘e4", regua.TIP, "rus"))
        self.assertEqual("Крe4", regua.normalizar("♔e4", regua.TIP, "rus"))
        self.assertEqual("Ne4", regua.normalizar("♗e4", regua.TIP, "ron"))
        self.assertEqual(figura, regua.normalizar(figura, regua.CRU))

    def test_lingua_desconhecida_usa_o_ingles(self) -> None:
        self.assertEqual("Qe4", regua.normalizar("♕e4", regua.TIP, "xyz"))

    def test_modo_desconhecido_levanta(self) -> None:
        with self.assertRaises(ValueError):
            regua.normalizar("a", "outro")


TABELA: list[tuple[str, str, str]] = [
    # inglês
    ("Nf3", "eng", regua.NOTACAO), ("exd5", "eng", regua.NOTACAO), ("Kg2=", "eng", regua.NOTACAO),
    ("1...Bc5!?", "eng", regua.NOTACAO), ("...Nxc4", "eng", regua.NOTACAO), ("…Rxb2", "eng", regua.NOTACAO),
    ("f1-e1", "eng", regua.NOTACAO), ("b4×c3", "eng", regua.NOTACAO), ("12.", "eng", regua.NOTACAO),
    ("12...", "eng", regua.NOTACAO), ("O-O", "eng", regua.NOTACAO), ("0–0", "eng", regua.NOTACAO),
    ("+-", "eng", regua.NOTACAO), ("±", "eng", regua.NOTACAO), ("!?", "eng", regua.NOTACAO), ("∞", "eng", regua.NOTACAO),
    ("1-0", "eng", regua.NOTACAO), ("½-½", "eng", regua.NOTACAO), ("h4ʘ", "eng", regua.NOTACAO),
    ("P-K4", "eng", regua.NOTACAO), ("QxQch", "eng", regua.NOTACAO), ("Rg8-Rg6.", "eng", regua.NOTACAO),
    ("6…g6!?", "eng", regua.NOTACAO), ("8.Rxg6+–", "eng", regua.NOTACAO), ("Nc5).", "eng", regua.NOTACAO),
    ("Rh1!).", "eng", regua.NOTACAO), ("19.Bd3", "eng", regua.NOTACAO), ("Rfc1²", "eng", regua.NOTACAO),
    ("Rxg5i", "eng", regua.NOTACAO), ("24...f4e", "eng", regua.NOTACAO), ("1...B", "eng", regua.NOTACAO),
    ("31.Bxg6fxg632.Qf4Rb733", "eng", regua.NOTACAO), ("[34.Qxb6Rxb6", "eng", regua.NOTACAO),
    ("97×f6)", "eng", regua.NOTACAO), ("♔e2", "eng", regua.NOTACAO), ("♘", "eng", regua.NOTACAO),
    ("B", "eng", regua.NOTACAO), ("K", "eng", regua.NOTACAO),
    ("the", "eng", regua.PROSA), ("Nimzowitsch", "eng", regua.PROSA), ("e-pawn", "eng", regua.PROSA),
    ("A", "eng", regua.PROSA), ("I", "eng", regua.PROSA), ("O", "eng", regua.PROSA), ("E", "eng", regua.PROSA),
    ("if", "eng", regua.PROSA), ("11th", "eng", regua.PROSA), ("Baadur(2694)", "eng", regua.PROSA),
    ("af7anca", "eng", regua.PROSA), ("f4e", "eng", regua.PROSA),
    # português
    ("Cf3", "por", regua.NOTACAO), ("Dxe7+", "por", regua.NOTACAO), ("Txa1", "por", regua.NOTACAO),
    ("B", "por", regua.NOTACAO), ("D", "por", regua.NOTACAO), ("T", "por", regua.NOTACAO), ("C", "por", regua.NOTACAO),
    ("R", "por", regua.NOTACAO), ("a", "por", regua.PROSA), ("o", "por", regua.PROSA), ("é", "por", regua.PROSA),
    ("à", "por", regua.PROSA), ("A", "por", regua.PROSA), ("O", "por", regua.PROSA), ("E", "por", regua.PROSA),
    ("posição", "por", regua.PROSA), ("peão-g6", "por", regua.PROSA), ("(o", "por", regua.PROSA), ("2ª", "por", regua.PROSA),
    # espanhol: descritiva, e o A que segue prosa
    ("T3Cj", "spa", regua.NOTACAO), ("AXD", "spa", regua.NOTACAO), ("TXPTR", "spa", regua.NOTACAO),
    ("DXg7", "spa", regua.NOTACAO), ("TXg7t", "spa", regua.NOTACAO), ("Ae4", "spa", regua.NOTACAO),
    ("Axc6", "spa", regua.NOTACAO), ("A", "spa", regua.PROSA), ("y", "spa", regua.PROSA), ("jugada", "spa", regua.PROSA),
    # alemão
    ("Sf3", "deu", regua.NOTACAO), ("Lb5", "deu", regua.NOTACAO), ("Sf3—e5", "deu", regua.NOTACAO),
    ("S", "deu", regua.NOTACAO), ("L", "deu", regua.NOTACAO), ("Wissen", "deu", regua.PROSA), ("und", "deu", regua.PROSA),
    # holandês: o P só é peça aqui
    ("Pc3", "nld", regua.NOTACAO), ("P", "nld", regua.NOTACAO), ("P", "eng", regua.PROSA),
    ("Pd5:", "nld", regua.NOTACAO), ("een", "nld", regua.PROSA), ("zijn", "nld", regua.PROSA),
    # francês
    ("Fb5", "fra", regua.NOTACAO), ("F", "fra", regua.NOTACAO), ("Rf1", "fra", regua.NOTACAO),
    ("échecs", "fra", regua.PROSA), ("y", "fra", regua.PROSA), ("à", "fra", regua.PROSA),
    # romeno
    ("Nb5", "ron", regua.NOTACAO), ("N", "ron", regua.NOTACAO), ("Tb7", "ron", regua.NOTACAO),
    ("și", "ron", regua.PROSA), ("poziția", "ron", regua.PROSA), ("o", "ron", regua.PROSA),
    # russo: peça em cirílico, e a homóglifa `е`
    ("Кре2", "rus", regua.NOTACAO), ("Лb4", "rus", regua.NOTACAO), ("Фd1", "rus", regua.NOTACAO),
    ("Л", "rus", regua.NOTACAO), ("Ф", "rus", regua.NOTACAO), ("Кр", "rus", regua.NOTACAO), ("Кре2+", "rus", regua.NOTACAO),
    ("Л", "eng", regua.PROSA), ("и", "rus", regua.PROSA), ("ход", "rus", regua.PROSA), ("белые", "rus", regua.PROSA),
    # sem letra, e a fileira de coordenadas
    ("1936", "eng", regua.OUTRO), (",", "eng", regua.OUTRO), ("—", "eng", regua.OUTRO), ("()", "eng", regua.OUTRO),
    ("/èéêëìíîï)", "por", regua.OUTRO), ('!""""""""#', "por", regua.OUTRO), ("abcdefgh", "por", regua.OUTRO),
    ("%", "por", regua.OUTRO), ("+%", "por", regua.OUTRO),
]
"""Rotulada à mão, nas oito línguas do acervo. Os casos saíram do que já enganou a régua, e de varrer o que o
protótipo chamava de prosa com dígito ou sinal nos JSONL de 2026-10-30."""

NUNCA_PROSA: list[tuple[str, str]] = [
    ("Wxf7", regua.RUIDO), (".l:tb1", regua.RUIDO), ("'ii'xa4", regua.RUIDO), ("'ii'", regua.RUIDO), ("tllb8", regua.RUIDO),
    ("llld4", regua.RUIDO), ("tlld7+", regua.RUIDO), (".ixf6", regua.RUIDO), ("l:!.b5+", regua.RUIDO), ("i.e3", regua.RUIDO),
    ("Àe8", regua.RUIDO), ("~e7", regua.RUIDO), ("©e7", regua.RUIDO), ("^xd6", regua.RUIDO), ("&xb7", regua.RUIDO),
    ("\x15d7", regua.RUIDO), ("'it>h8", regua.RUIDO), ('"i¥d2', regua.RUIDO), ("tt:Je7,", regua.RUIDO),
    ("c!tle7", regua.RUIDO), ("=I=", regua.RUIDO), ("+I=", regua.RUIDO), ("ç", regua.RUIDO), ("æ+", regua.RUIDO),
    ('!""""""""#', regua.OUTRO), ("/èéêëìíîï)", regua.OUTRO),
]


class ClassificadorTests(unittest.TestCase):
    def test_a_tabela_tem_o_tamanho_e_as_linguas_prometidos(self) -> None:
        self.assertGreaterEqual(len(TABELA), 80)
        self.assertEqual({"eng", "por", "spa", "deu", "nld", "fra", "ron", "rus"}, {lingua for _, lingua, _ in TABELA})

    def test_tabela_sem_divergencia(self) -> None:
        erradas = [
            (token, lingua, esperada, regua.classe_do_token(token, lingua))
            for token, lingua, esperada in TABELA
            if regua.classe_do_token(token, lingua) != esperada
        ]
        self.assertEqual([], erradas)

    def test_o_que_a_regua_recusa_como_prosa(self) -> None:
        erradas = [(t, c, regua.classe_do_token(t)) for t, c in NUNCA_PROSA if regua.classe_do_token(t) != c]
        self.assertEqual([], erradas)

    def test_ruido_tem_placar_proprio(self) -> None:
        p = regua.pontuar("casa .l:tb1 casa", "casa XXXXXX casa")
        self.assertEqual(0, p.erros[regua.PROSA])
        self.assertEqual(6, p.erros[regua.RUIDO])

    def test_apelido_de_duas_letras_vale(self) -> None:
        self.assertEqual(regua.NOTACAO, regua.classe_do_token("Л", "ru"))
        self.assertEqual(regua.NOTACAO, regua.classe_do_token("P", "nl"))
        self.assertEqual(regua.PROSA, regua.classe_do_token("Л", "pt"))

    def test_linha_so_de_coordenadas_e_outro(self) -> None:
        for linha, lingua in (("a b c d e f g h", "por"), ("8 7 6 5", "eng"), ("è é ê ë", "por")):
            classes = regua.classes_por_char(linha, lingua)
            self.assertEqual({regua.OUTRO, regua.ESPACO}, set(classes), linha)

    def test_a_e_o_soltos_em_linha_de_verdade_seguem_prosa(self) -> None:
        self.assertIn(regua.PROSA, regua.classes_por_char("a e a e", "por"))
        self.assertIn(regua.PROSA, regua.classes_por_char("a b", "por"))
        texto = "casa\na b c d e f g h\ncasa"
        classes = regua.classes_por_char(texto, "por")
        self.assertEqual(regua.PROSA, classes[0])
        self.assertEqual(regua.OUTRO, classes[5])

    def test_wer_nao_conta_a_linha_de_coordenadas_como_prosa(self) -> None:
        p = regua.pontuar("casa\na b c d e f g h", "casa", "por")
        self.assertEqual(1, p.wer_n)
        self.assertEqual(0, p.wer_d)

    def test_o_classificador_injetado_troca_a_classe_e_desliga_a_linha(self) -> None:
        tudo_prosa = regua.classes_por_char("a b c d", "por", classificar=lambda _: regua.PROSA)
        self.assertEqual({regua.PROSA}, set(tudo_prosa))

    def test_a_versao_esta_declarada(self) -> None:
        self.assertTrue(regua.VERSAO_CLASSIFICADOR)


class FamiliaTests(unittest.TestCase):
    def test_as_familias_da_taxonomia(self) -> None:
        for ref, hip, esperada in (
            ("will", "", "palavra perdida"),
            ("will", "wi..", "traco vertical lido como ponto (l/I -> .)"),
            ("first", "fi1rst", "ligadura fi/fl com 1 a mais"),
            ('"tail', "(tail", "aspas duplas"),
            ("the", "♔e", "figurina inventada em palavra"),
            ("DEFESA", "DEFEsA", "caixa (maiusc/minusc)"),
            ("não", "näo", "acento"),
            ("draw.;", "draw.:", "pontuacao"),
            ("casarão", "casa", "palavra cortada"),
            ("Najdorf", "Najdof", "letra trocada"),
        ):
            self.assertEqual(esperada, regua.familia(ref, hip), (ref, hip))


class EstatisticaTests(unittest.TestCase):
    def test_ic_de_dois_niveis_e_mais_largo_que_o_de_folha(self) -> None:
        erros = [0, 0, 0, 10, 10, 10]
        totais = [100] * 6
        livros = ["a", "a", "a", "b", "b", "b"]
        ponto, baixo, alto = regua.ic95(erros, totais, livros)
        self.assertAlmostEqual(0.05, ponto)
        self.assertAlmostEqual(0.0, baixo)
        self.assertAlmostEqual(0.1, alto)
        _, baixo_folha, alto_folha = regua.ic95(erros, totais)
        self.assertGreater(baixo_folha, baixo)
        self.assertLess(alto_folha, alto)

    def test_mesma_semente_mesmo_intervalo(self) -> None:
        erros, totais, livros = [1, 2, 3, 4], [50] * 4, ["a", "a", "b", "b"]
        self.assertEqual(regua.ic95(erros, totais, livros), regua.ic95(erros, totais, livros))

    def test_diferenca_pareada_de_motor_igual_e_zero(self) -> None:
        erros, totais, livros = [1, 2, 3, 4], [50] * 4, ["a", "a", "b", "b"]
        self.assertEqual((0.0, 0.0, 0.0), regua.diferenca_pareada(erros, totais, erros, totais, livros))

    def test_lista_vazia_e_nan(self) -> None:
        ponto, _, _ = regua.ic95([], [])
        self.assertNotEqual(ponto, ponto)


def _pagina(colunas, cabecalho=None, rodape=None):
    blocos = [SimpleNamespace(linhas=[SimpleNamespace(bbox=b, texto=t) for b, t in linhas]) for linhas in colunas]
    return SimpleNamespace(
        colunas=[SimpleNamespace(blocos=[b]) for b in blocos],
        cabecalho=None if cabecalho is None else SimpleNamespace(bbox=cabecalho[0], texto=cabecalho[1]),
        rodape=None if rodape is None else SimpleNamespace(bbox=rodape[0], texto=rodape[1]),
    )


class MontagemTests(unittest.TestCase):
    def test_cabecalho_que_a_coluna_ja_leu_nao_duplica(self) -> None:
        pagina = _pagina([[((10, 10, 100, 20), "PARTIDA 13"), ((10, 30, 100, 40), "corpo")]], cabecalho=((10, 10, 100, 20), "PARTIDA 13"))
        self.assertEqual(["PARTIDA 13", "corpo"], [ln.texto for ln in regua.linhas_da_pagina(pagina)])

    def test_cabecalho_e_rodape_fora_das_colunas_entram_nas_pontas(self) -> None:
        pagina = _pagina([[((10, 30, 100, 40), "corpo")]], cabecalho=((10, 5, 100, 15), "PARTIDA"), rodape=((10, 90, 100, 99), "42"))
        self.assertEqual(["PARTIDA", "corpo", "42"], [ln.texto for ln in regua.linhas_da_pagina(pagina)])

    def test_cruza_diagrama_pela_fracao_da_area(self) -> None:
        diagrama = [(100, 100, 200, 200)]
        self.assertTrue(regua.cruza_diagrama((110, 110, 190, 120), diagrama))
        self.assertFalse(regua.cruza_diagrama((0, 110, 100, 120), diagrama))
        self.assertFalse(regua.cruza_diagrama((60, 110, 130, 120), diagrama, fracao=0.5))

    def test_retangulo_crescido_de_uma_casa_pega_a_fileira_de_coordenadas(self) -> None:
        diagrama = (100, 100, 180, 180)
        self.assertEqual((90.0, 90.0, 190.0, 190.0), regua.crescer_diagrama(diagrama))
        fileira = (100, 182, 180, 188)
        self.assertFalse(regua.cruza_diagrama(fileira, [diagrama]))
        self.assertTrue(regua.cruza_diagrama(fileira, [regua.crescer_diagrama(diagrama)]))


class ForaDaReferenciaTests(unittest.TestCase):
    DIAGRAMA = ((100, 100, 180, 180),)

    def test_a_linha_dentro_do_diagrama_sai_tenha_o_que_tiver(self) -> None:
        self.assertTrue(regua.fora_da_referencia("White to move", (110, 110, 170, 120), self.DIAGRAMA))

    def test_a_fileira_de_coordenadas_colada_sai_pelo_retangulo_crescido(self) -> None:
        self.assertTrue(regua.fora_da_referencia("/èéêëìíîï)", (100, 182, 180, 188), self.DIAGRAMA, "por"))
        self.assertTrue(regua.fora_da_referencia("a b c d e f g h", (100, 182, 180, 188), self.DIAGRAMA, "por"))

    def test_o_texto_colado_no_diagrama_fica(self) -> None:
        """Eram 9 das 15 linhas a mais no dev: tiradas, viravam inserção de quem as leu certo."""
        self.assertFalse(regua.fora_da_referencia("As brancas jogam", (100, 182, 180, 188), self.DIAGRAMA, "por"))
        self.assertFalse(regua.fora_da_referencia("6...Ng3+", (100, 182, 180, 188), self.DIAGRAMA))

    def test_longe_do_diagrama_fica_mesmo_sem_palavra(self) -> None:
        self.assertFalse(regua.fora_da_referencia("/èéêëìíîï)", (100, 300, 180, 306), self.DIAGRAMA, "por"))


class FronteiraTests(unittest.TestCase):
    def test_a_regua_nao_le_arquivo_nem_importa_o_medido(self) -> None:
        arvore = ast.parse((RAIZ / "src/chess_diagram_ocr/text/regua_prosa.py").read_text(encoding="utf-8"))
        modulos = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                modulos.update(a.name for a in no.names)
            elif isinstance(no, ast.ImportFrom):
                modulos.add(no.module or "")
        self.assertEqual(set(), {m for m in modulos if "chess_diagram_ocr" in m or m.startswith(".") or m in {"fitz", "cv2"}})
        texto = (RAIZ / "src/chess_diagram_ocr/text/regua_prosa.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\bopen\(|read_text|write_bytes", texto))


if __name__ == "__main__":
    unittest.main()
