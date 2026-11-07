"""O diagrama vetorial a partir da FEN (S-542).

**O que se afirma é a geometria, e não o desenho.** Um SVG com 64 `rect` e 32 `use` pode estar com
o rei na casa errada e continuar bem formado; o que estes testes leem é o `data-casa` de cada casa
e a `transform` de cada peça, que é onde o erro de orientação -- o defeito clássico de todo
tabuleiro virado -- aparece. As réguas se afirmam pela ordem do texto, porque é a mesma decisão de
`ui/desenho_do_tabuleiro.reguas` e ela já explicou por que não se compara pixel.
"""

from __future__ import annotations

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import chess

from chess_diagram_ocr import diagrama_svg

SVG = f"{{{diagrama_svg.SVG_NS}}}"
INICIAL = chess.STARTING_FEN
ITALIANA = "rnbqkb1r/pppp1ppp/5n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 0 4"


def _raiz(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def _casas(raiz: ET.Element) -> dict[str, ET.Element]:
    return {r.get("data-casa", ""): r for r in raiz.iter(f"{SVG}rect") if "casa" in r.get("class", "").split()}


def _pecas(raiz: ET.Element) -> dict[str, ET.Element]:
    return {u.get("data-casa", ""): u for u in raiz.iter(f"{SVG}use")}


def _translate(elemento: ET.Element) -> tuple[int, int]:
    casou = re.fullmatch(r"translate\((\d+),(\d+)\)", elemento.get("transform", ""))
    assert casou, elemento.get("transform")
    return int(casou.group(1)), int(casou.group(2))


class BemFormadoTests(unittest.TestCase):
    def test_o_svg_e_xml_bem_formado_com_viewbox_quadrado(self) -> None:
        raiz = _raiz(diagrama_svg.svg_da_posicao(INICIAL))
        self.assertEqual(raiz.tag, f"{SVG}svg")
        lado = 8 * diagrama_svg.CASA + 2 * diagrama_svg.MARGEM
        self.assertEqual(raiz.get("viewBox"), f"0 0 {lado} {lado}")

    def test_o_tamanho_e_em_em_e_nao_em_pixel(self) -> None:
        """`em` é o que deixa o leitor de EPUB refluir o diagrama com o corpo do texto."""
        raiz = _raiz(diagrama_svg.svg_da_posicao(INICIAL))
        self.assertEqual(raiz.get("width"), "18em")
        self.assertEqual(raiz.get("height"), "18em")
        self.assertEqual(_raiz(diagrama_svg.svg_da_posicao(INICIAL, largura_em=12)).get("width"), "12em")

    def test_a_fen_vai_no_atributo_e_no_titulo(self) -> None:
        raiz = _raiz(diagrama_svg.svg_da_posicao(ITALIANA))
        self.assertEqual(raiz.get("data-fen"), ITALIANA)
        titulo = raiz.find(f"{SVG}title")
        assert titulo is not None
        self.assertIn(ITALIANA, titulo.text or "")

    def test_posicao_vazia_e_erro_e_nao_tabuleiro_em_branco(self) -> None:
        """Um diagrama em branco no meio do livro é o defeito que ninguém acha."""
        with self.assertRaises(ValueError):
            diagrama_svg.svg_da_posicao("")
        with self.assertRaises(ValueError):
            diagrama_svg.svg_da_posicao("isto nao e fen")


class CasasTests(unittest.TestCase):
    def test_sao_64_casas_uma_por_nome(self) -> None:
        casas = _casas(_raiz(diagrama_svg.svg_da_posicao(INICIAL)))
        self.assertEqual(sorted(casas), sorted(chess.SQUARE_NAMES))

    def test_a1_e_escura_e_h1_e_clara_de_qualquer_lado(self) -> None:
        for virado in (False, True):
            casas = _casas(_raiz(diagrama_svg.svg_da_posicao(INICIAL, virado=virado)))
            self.assertIn("escura", casas["a1"].get("class", ""), virado)
            self.assertIn("clara", casas["h1"].get("class", ""), virado)

    def test_com_as_brancas_embaixo_a1_fica_no_canto_inferior_esquerdo(self) -> None:
        casas = _casas(_raiz(diagrama_svg.svg_da_posicao(INICIAL)))
        m, c = diagrama_svg.MARGEM, diagrama_svg.CASA
        self.assertEqual((casas["a1"].get("x"), casas["a1"].get("y")), (str(m), str(m + 7 * c)))
        self.assertEqual((casas["h8"].get("x"), casas["h8"].get("y")), (str(m + 7 * c), str(m)))

    def test_virado_poe_a1_no_canto_superior_direito(self) -> None:
        casas = _casas(_raiz(diagrama_svg.svg_da_posicao(INICIAL, virado=True)))
        m, c = diagrama_svg.MARGEM, diagrama_svg.CASA
        self.assertEqual((casas["a1"].get("x"), casas["a1"].get("y")), (str(m + 7 * c), str(m)))
        self.assertEqual((casas["h8"].get("x"), casas["h8"].get("y")), (str(m), str(m + 7 * c)))


class PecasTests(unittest.TestCase):
    def test_a_posicao_inicial_tem_32_pecas_na_casa_certa(self) -> None:
        pecas = _pecas(_raiz(diagrama_svg.svg_da_posicao(INICIAL)))
        self.assertEqual(len(pecas), 32)
        self.assertEqual(pecas["e1"].get("data-peca"), "K")
        self.assertEqual(pecas["d8"].get("data-peca"), "q")
        m, c = diagrama_svg.MARGEM, diagrama_svg.CASA
        self.assertEqual(_translate(pecas["e1"]), (m + 4 * c, m + 7 * c))
        self.assertEqual(_translate(pecas["a8"]), (m, m))

    def test_virado_espelha_a_peca_junto_com_a_casa(self) -> None:
        """A peça e a casa saem da mesma `_posicao`: o rei virado cai onde a casa e1 virada caiu."""
        raiz = _raiz(diagrama_svg.svg_da_posicao(INICIAL, virado=True))
        pecas, casas = _pecas(raiz), _casas(raiz)
        self.assertEqual(_translate(pecas["e1"]), (int(casas["e1"].get("x", "")), int(casas["e1"].get("y", ""))))
        m, c = diagrama_svg.MARGEM, diagrama_svg.CASA
        self.assertEqual(_translate(pecas["e1"]), (m + 3 * c, m))

    def test_a_peca_aponta_um_desenho_definido_no_proprio_arquivo(self) -> None:
        raiz = _raiz(diagrama_svg.svg_da_posicao("8/8/8/8/8/8/8/K6k w - - 0 1"))
        definidos = {g.get("id") for g in raiz.iter(f"{SVG}g")}
        for uso in raiz.iter(f"{SVG}use"):
            self.assertIn(uso.get("href", "").lstrip("#"), definidos)

    def test_so_as_pecas_presentes_entram_em_defs(self) -> None:
        """Um final de rei e peão não carrega os doze desenhos."""
        raiz = _raiz(diagrama_svg.svg_da_posicao("8/8/8/8/8/8/P7/K6k w - - 0 1"))
        self.assertEqual(len(list(raiz.iter(f"{SVG}g"))), 3)

    def test_um_placement_so_desenha_igual_a_fen_inteira(self) -> None:
        pecas = _pecas(_raiz(diagrama_svg.svg_da_posicao(ITALIANA.split()[0])))
        self.assertEqual(pecas["c4"].get("data-peca"), "B")
        self.assertEqual(len(pecas), 32)


class ReguasTests(unittest.TestCase):
    def _reguas(self, svg: str) -> tuple[str, str]:
        textos = [t for t in _raiz(svg).iter(f"{SVG}text") if "regua" in t.get("class", "")]
        letras = sorted((t for t in textos if (t.text or "").isalpha()), key=lambda t: float(t.get("x", "0")))
        numeros = sorted((t for t in textos if (t.text or "").isdigit()), key=lambda t: float(t.get("y", "0")))
        return "".join(t.text or "" for t in letras), "".join(t.text or "" for t in numeros)

    def test_com_as_brancas_embaixo_a_fica_a_esquerda_e_8_no_topo(self) -> None:
        self.assertEqual(self._reguas(diagrama_svg.svg_da_posicao(INICIAL)), ("abcdefgh", "87654321"))

    def test_virado_inverte_as_duas(self) -> None:
        self.assertEqual(self._reguas(diagrama_svg.svg_da_posicao(INICIAL, virado=True)), ("hgfedcba", "12345678"))

    def test_sem_reguas_nao_ha_texto_nem_margem(self) -> None:
        raiz = _raiz(diagrama_svg.svg_da_posicao(INICIAL.split()[0], com_reguas=False))
        self.assertEqual(list(raiz.iter(f"{SVG}text")), [])
        lado = 8 * diagrama_svg.CASA
        self.assertEqual(raiz.get("viewBox"), f"0 0 {lado} {lado}")


class LadoAJogarTests(unittest.TestCase):
    def _ponto(self, svg: str) -> ET.Element | None:
        return next((c for c in _raiz(svg).iter(f"{SVG}circle") if "lado-a-jogar" in c.get("class", "")), None)

    def test_as_pretas_a_jogar_poem_o_ponto_em_cima(self) -> None:
        ponto = self._ponto(diagrama_svg.svg_da_posicao(ITALIANA))
        assert ponto is not None
        self.assertIn("pretas", ponto.get("class", ""))
        self.assertLess(float(ponto.get("cy", "0")), diagrama_svg.MARGEM + diagrama_svg.CASA)

    def test_as_brancas_a_jogar_poem_o_ponto_embaixo(self) -> None:
        ponto = self._ponto(diagrama_svg.svg_da_posicao(INICIAL))
        assert ponto is not None
        self.assertIn("brancas", ponto.get("class", ""))
        self.assertGreater(float(ponto.get("cy", "0")), diagrama_svg.MARGEM + 7 * diagrama_svg.CASA)

    def test_um_placement_sozinho_nao_diz_de_quem_e_a_vez(self) -> None:
        self.assertIsNone(self._ponto(diagrama_svg.svg_da_posicao(INICIAL.split()[0])))
        self.assertEqual(diagrama_svg.lado_da_fen(INICIAL.split()[0]), "")

    def test_quem_chama_pode_calar_ou_impor_o_lado(self) -> None:
        self.assertIsNone(self._ponto(diagrama_svg.svg_da_posicao(INICIAL, lado_a_jogar="")))
        ponto = self._ponto(diagrama_svg.svg_da_posicao(INICIAL.split()[0], lado_a_jogar="b"))
        assert ponto is not None
        self.assertIn("pretas", ponto.get("class", ""))


class SemHexadecimalTests(unittest.TestCase):
    def test_nenhuma_cor_e_escrita_no_modulo(self) -> None:
        """As cores saem de `ui/tokens.py`, como a cor de autor sai dele no `.html` da Fase 39."""
        fonte = Path(diagrama_svg.__file__).read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"#[0-9a-fA-F]{6}\b", fonte), [])

    def test_as_cores_do_diagrama_sao_as_da_reserva(self) -> None:
        from chess_diagram_ocr.ui import tokens

        cores = diagrama_svg.cores_padrao()
        self.assertEqual(cores.clara, tokens.cor(tokens.CASA_CLARA))
        self.assertEqual(cores.escura, tokens.cor(tokens.CASA_ESCURA))


class ContrasteTests(unittest.TestCase):
    """A tinta da margem é lida, ou não está lá.

    O piso é o `AA_GRAFICO` da S-146 -- 4,5:1 --, e a régua saía a **2,51:1** sobre a moldura
    escura. O ponto das pretas era pior: pintado com a própria cor da moldura, **1,0:1**, um ponto
    invisível dizendo de quem era a vez.
    """

    PISO = 4.5

    def setUp(self) -> None:
        from chess_diagram_ocr.ui import tokens

        self.tokens = tokens
        self.cores = diagrama_svg.cores_padrao()

    def test_a_regua_e_lida_sobre_a_moldura(self) -> None:
        razao = self.tokens.razao_de_contraste(self.cores.coordenada, self.cores.moldura)
        self.assertGreaterEqual(razao, self.PISO, f"{razao:.2f}:1")

    def test_a_plaqueta_do_lado_a_jogar_e_lida_nos_dois_estados(self) -> None:
        """O quadrado claro é o que separa a marca da moldura; o círculo cheio é lido contra ele, e
        o vazado pelo contorno. Sem o quadrado, "pretas jogam" é tinta escura sobre fundo escuro."""
        plaqueta = self.tokens.razao_de_contraste(self.cores.clara, self.cores.moldura)
        self.assertGreaterEqual(plaqueta, self.PISO, f"{plaqueta:.2f}:1")
        for tinta in (self.cores.peca_escura,):
            razao = self.tokens.razao_de_contraste(tinta, self.cores.clara)
            self.assertGreaterEqual(razao, self.PISO, f"{razao:.2f}:1")

    def test_o_desenho_usa_as_tintas_medidas_e_nao_a_moldura(self) -> None:
        raiz = _raiz(diagrama_svg.svg_da_posicao(ITALIANA))
        ponto = next(c for c in raiz.iter(f"{SVG}circle") if "lado-a-jogar" in c.get("class", ""))
        placa = next(r for r in raiz.iter(f"{SVG}rect") if r.get("class") == "plaqueta-do-lado")
        self.assertEqual(placa.get("fill"), self.cores.clara)
        self.assertEqual(ponto.get("fill"), self.cores.peca_escura)
        self.assertNotEqual(ponto.get("fill"), self.cores.moldura)
        regua = next(t for t in raiz.iter(f"{SVG}text") if "regua" in t.get("class", ""))
        self.assertEqual(regua.get("fill"), self.cores.coordenada)


class PlaquetaViradaTests(unittest.TestCase):
    def _cy(self, svg: str) -> float:
        raiz = _raiz(svg)
        ponto = next(c for c in raiz.iter(f"{SVG}circle") if "lado-a-jogar" in c.get("class", ""))
        return float(ponto.get("cy", "0"))

    def test_a_marca_fica_do_lado_de_quem_joga(self) -> None:
        """Virado, as pretas estão embaixo -- e "as pretas jogam" apontava para o alto, que é onde
        as brancas estavam."""
        meio = diagrama_svg.MARGEM + 4 * diagrama_svg.CASA
        self.assertGreater(self._cy(diagrama_svg.svg_da_posicao(INICIAL)), meio)
        self.assertLess(self._cy(diagrama_svg.svg_da_posicao(INICIAL, virado=True)), meio)
        self.assertLess(self._cy(diagrama_svg.svg_da_posicao(ITALIANA)), meio)
        self.assertGreater(self._cy(diagrama_svg.svg_da_posicao(ITALIANA, virado=True)), meio)


class ArquivoSvgTests(unittest.TestCase):
    def test_para_o_docx_sai_com_declaracao_e_medido_em_centimetros(self) -> None:
        """`width="18em"` num arquivo solto não tem corpo de texto a que se referir."""
        texto = diagrama_svg.svg_da_posicao(INICIAL, largura_em=7.6, unidade="cm", declaracao=True)
        self.assertTrue(texto.startswith("<?xml "), texto[:40])
        raiz = _raiz(texto)
        self.assertEqual(raiz.get("width"), "7.6cm")
        self.assertEqual(raiz.get("height"), "7.6cm")

    def test_no_epub_continua_sem_declaracao_e_em_em(self) -> None:
        """Dentro do XHTML o SVG é um elemento, e uma declaração no meio do documento é XML inválido."""
        texto = diagrama_svg.svg_da_posicao(INICIAL)
        self.assertFalse(texto.startswith("<?xml"))
        self.assertEqual(_raiz(texto).get("width"), "18em")


class ErroEmPortuguesTests(unittest.TestCase):
    def test_a_fen_ilegivel_falha_em_portugues_com_o_original_ao_lado(self) -> None:
        """O `python-chess` diz "expected 8 rows in position part of fen", que não é o vocabulário
        de quem digitou um diagrama errado. A regra do `cli.message_for`: a frase em português, e o
        original entre parênteses, porque é o que se pesquisa."""
        with self.assertRaises(diagrama_svg.PosicaoInvalida) as capturado:
            diagrama_svg.svg_da_posicao("8/8/8")
        mensagem = str(capturado.exception)
        self.assertIn("posição inválida", mensagem)
        self.assertIn("expected 8 rows", mensagem)
        self.assertIsInstance(capturado.exception, ValueError)

    def test_posicao_vazia_tambem(self) -> None:
        with self.assertRaises(diagrama_svg.PosicaoInvalida):
            diagrama_svg.svg_da_posicao("")


class DescricaoTests(unittest.TestCase):
    def test_o_alt_diz_a_posicao_e_nao_so_o_numero(self) -> None:
        """`alt="Diagrama 1"` é, para quem lê com leitor de tela, o mesmo que imagem sem alternativa."""
        descricao = diagrama_svg.descricao_da_posicao(ITALIANA, marca="Diagrama 3")
        self.assertEqual(descricao, f"Diagrama 3. As pretas jogam. FEN: {ITALIANA}")
        self.assertIn("As brancas jogam", diagrama_svg.descricao_da_posicao(INICIAL))
        self.assertEqual(diagrama_svg.descricao_da_posicao(INICIAL.split()[0]), f"FEN: {INICIAL.split()[0]}")

    def test_a_descricao_e_o_titulo_do_svg(self) -> None:
        titulo = _raiz(diagrama_svg.svg_da_posicao(ITALIANA, titulo=diagrama_svg.descricao_da_posicao(ITALIANA))).find(f"{SVG}title")
        assert titulo is not None
        self.assertIn("As pretas jogam", titulo.text or "")


if __name__ == "__main__":
    unittest.main()
