"""O conjunto de peças como escolha, e não como pasta cravada (S-230).

`PieceImages` recebia um diretório e o chamador passava sempre o mesmo: `assets/piece_images/`.
Doze PNGs, um conjunto, sem alternativa -- e trocá-lo era sobrescrever os arquivos, o que muda o
conjunto de todo mundo e não tem volta.

**O que a Imagem 2 propõe não entra, e a razão é de produto.** Ela mostra peças fotográficas de um
tabuleiro de madeira; o tabuleiro da janela é onde se *corrige* a leitura, casa a casa, contra um
diagrama impresso, e sombra, perspectiva e madeira atrapalham exatamente essa comparação. O que
entra da imagem é a ideia de que o conjunto é uma escolha.

Os quatro critérios de aceite, na ordem em que a spec os lista: o padrão é o de hoje; conjunto e
pele são eixos independentes; pasta incompleta avisa e desenha o resto; e o cache não confunde
conjuntos.
"""

from __future__ import annotations

import logging
import unittest
from pathlib import Path

from chess_diagram_ocr.config import BUNDLE_ROOT
from chess_diagram_ocr.ui import conjuntos, pele
from chess_diagram_ocr.ui.state import AppState, state_from_dict

PECAS = BUNDLE_ROOT / "assets" / "piece_images"


def _pixels_escuros(imagem: object, limiar: int = 160) -> int:
    """Quantos pixels da imagem contam como traço. `histogram` e nao `getdata`:
    o segundo esta a caminho de sair da Pillow, e a conta e a mesma."""
    return sum(imagem.convert("L").histogram()[:limiar])


class RegistroDeConjuntosTests(unittest.TestCase):
    """O registro sozinho: sem `tkinter`, sem `PIL`, sem abrir imagem."""

    def test_o_padrao_e_o_primeiro_e_nao_engrossa_nem_e_do_usuario(self) -> None:
        """Quem nunca abrir a Configuração tem o tabuleiro de sempre, pixel a pixel."""
        primeiro = conjuntos.CONJUNTOS[0]
        self.assertEqual(conjuntos.PADRAO, primeiro.nome)
        self.assertFalse(primeiro.engrossa)
        self.assertFalse(primeiro.do_usuario)

    def test_todo_conjunto_tem_rotulo_legivel(self) -> None:
        """`"padrao"` não é texto de interface -- é a chave que vai para o disco."""
        for registro in conjuntos.CONJUNTOS:
            with self.subTest(conjunto=registro.nome):
                self.assertNotEqual(registro.nome, registro.rotulo)
                self.assertTrue(registro.rotulo.strip())

    def test_nome_invalido_cai_no_padrao_e_diz_qual_era(self) -> None:
        """Nomear o inválido é metade do valor: sem o nome no log, quem escreveu a variável
        conclui que ela não é lida. É o contrato de `pele.valida`, com outro dono."""
        with self.assertLogs("chess_diagram_ocr.ui.conjuntos", level=logging.WARNING) as registro:
            self.assertEqual(conjuntos.PADRAO, conjuntos.valida("madeira"))
        self.assertIn("madeira", "\n".join(registro.output))

    def test_o_vazio_nao_reclama(self) -> None:
        """"Nunca escolhido" é o estado normal de quem nunca abriu a Configuração."""
        with self.assertRaises(AssertionError):
            with self.assertLogs("chess_diagram_ocr.ui.conjuntos", level=logging.WARNING):
                conjuntos.valida("")

    def test_o_ambiente_ganha_do_guardado(self) -> None:
        """Pela mesma razão de `pele.escolhida`: uma variável que o disco vencesse não serviria
        para abrir o programa num conjunto a partir de um roteiro."""
        self.assertEqual(
            conjuntos.TRACO,
            conjuntos.escolhido(conjuntos.PADRAO, ambiente={conjuntos.CONJUNTO_ENV: conjuntos.TRACO}),
        )
        self.assertEqual(conjuntos.TRACO, conjuntos.escolhido(conjuntos.TRACO, ambiente={}))
        self.assertEqual(conjuntos.PADRAO, conjuntos.escolhido("", ambiente={}))

    def test_registrado_levanta_e_valida_nao(self) -> None:
        with self.assertRaises(KeyError):
            conjuntos.registrado("madeira")

    def test_as_doze_pecas_sao_as_do_repositorio(self) -> None:
        """A lista existe para poder dizer **quais** faltam, e ela tem de bater com o disco."""
        no_disco = sorted(caminho.stem for caminho in PECAS.glob("*.png"))
        self.assertEqual(sorted(conjuntos.PECAS), no_disco)

    def test_pasta_incompleta_nomeia_o_que_falta(self) -> None:
        presentes = {"wp", "wn"}
        faltando = conjuntos.ausentes(
            Path("qualquer"), existe=lambda alvo: alvo.stem in presentes
        )
        self.assertNotIn("wp", faltando)
        self.assertIn("bk", faltando)
        self.assertEqual(len(conjuntos.PECAS) - 2, len(faltando))

    def test_a_pasta_de_verdade_esta_completa(self) -> None:
        self.assertEqual([], conjuntos.ausentes(PECAS))


class EixosIndependentesTests(unittest.TestCase):
    """Pele decide arranjo; tema decide cor; conjunto decide o desenho da peça."""

    def test_conjunto_e_pele_sao_eixos_independentes(self) -> None:
        """O critério de aceite dito como estrutura: nenhum dos dois registros conhece o outro.

        Amarrá-los faria "a fita clara com as peças de traço grosso" ser impossível sem que
        ninguém tivesse decidido isso -- é a mesma separação que a S-221 defendeu entre pele e
        tema, e ela só continua valendo enquanto nada aqui cita nada de lá.
        """
        campos_de_pele = set(pele.Pele.__dataclass_fields__)
        campos_de_conjunto = set(conjuntos.Conjunto.__dataclass_fields__)
        self.assertEqual(set(), campos_de_pele & {"conjunto", "pecas", "piece_set"})
        self.assertEqual(set(), campos_de_conjunto & {"pele", "skin", "cromo_escuro", "densidade"})

        fonte_pele = Path(pele.__file__).read_text(encoding="utf-8")
        fonte_conjunto = Path(conjuntos.__file__).read_text(encoding="utf-8")
        self.assertNotIn("import conjuntos", fonte_pele)
        self.assertNotIn("from . import pele", fonte_conjunto)

    def test_qualquer_combinacao_de_pele_e_conjunto_vale(self) -> None:
        """As três peles vezes os três conjuntos: nove combinações, e nenhuma é recusada."""
        for registro_de_pele in pele.PELES:
            for registro in conjuntos.CONJUNTOS:
                with self.subTest(pele=registro_de_pele.nome, conjunto=registro.nome):
                    self.assertEqual(registro.nome, conjuntos.valida(registro.nome))
                    self.assertEqual(registro_de_pele.nome, pele.valida(registro_de_pele.nome))


class EscolhaGuardadaTests(unittest.TestCase):
    """O conjunto escolhido sobrevive a fechar e reabrir (S-230/S-25)."""

    def test_o_conjunto_e_a_pasta_vao_e_voltam_do_disco(self) -> None:
        estado = AppState()
        estado.piece_set = conjuntos.TRACO
        estado.piece_dir = "D:/pecas"
        de_volta = state_from_dict(estado.to_dict())
        self.assertEqual(conjuntos.TRACO, de_volta.piece_set)
        self.assertEqual("D:/pecas", de_volta.piece_dir)

    def test_estado_de_versao_anterior_abre_no_padrao(self) -> None:
        """Um arquivo da versão 3 não tem os dois campos, e a resposta certa é o padrão -- e não
        um erro que impeça a janela de abrir."""
        antigo = {"version": 3, "last_pdf": "livro.pdf", "skin": pele.FOCO}
        estado = state_from_dict(antigo)
        self.assertEqual("", estado.piece_set)
        self.assertEqual(conjuntos.PADRAO, conjuntos.escolhido(estado.piece_set, ambiente={}))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
