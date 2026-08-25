"""O construtor das listas de palavras (`cvoff-texto-lexico`).

O teste que mais importa aqui é o da **lista corrompida**: `MegaDatabase(Jogadores with dot).txt`
traz dois nomes partidos ao meio e concatenados, e depois das réguas ainda sobrariam 39.409
palavras falsas. Palavra falsa no léxico é pior que palavra faltando -- a que falta só deixa de
corrigir, a falsa vira **alvo** de correção.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from chess_diagram_ocr.cli import texto_lexico as lex
from chess_diagram_ocr.text import dicionario as dic


class ReguasDeEntradaTests(unittest.TestCase):
    def test_a_notacao_nao_entra(self) -> None:
        """`Kf3` e `e4` no léxico seriam lance virando alvo de correção."""
        for token in ("Kf3", "e4", "Nc", "0-0", "O-O-O", "1-0"):
            with self.subTest(token=token):
                self.assertFalse(lex.aceita(token))

    def test_a_palavra_curta_nao_entra(self) -> None:
        self.assertFalse(lex.aceita("abc"))
        self.assertTrue(lex.aceita("abcd"))

    def test_o_token_com_pontuacao_no_meio_nao_entra(self) -> None:
        """`A.Koros` é a assinatura da lista corrompida, e ela morre na régua de `PALAVRA`."""
        self.assertFalse(lex.aceita("A.Koros"))
        self.assertTrue(lex.aceita("Aabling-Thomsen"), "hífen é parte de nome próprio")

    def test_a_linha_de_jogador_vira_duas_palavras(self) -> None:
        self.assertEqual(["Aab", "Manfred"], lex.tokens("Aab, Manfred\n"))

    def test_o_bom_da_linha_sobrevive_ao_bom(self) -> None:
        """O BOM do arquivo entra na primeira palavra, e sem tirá-lo ela vira outra palavra."""
        self.assertEqual(["Aab"], lex.tokens("﻿Aab"))

    def test_nome_proprio_e_a_primeira_maiuscula(self) -> None:
        self.assertTrue(lex.e_nome("Alekhine"))
        self.assertFalse(lex.e_nome("attack"))


class ConstruirTests(unittest.TestCase):
    def _pasta(self, arquivos: dict[str, str]) -> Path:
        pasta = Path(tempfile.mkdtemp())
        for nome, conteudo in arquivos.items():
            (pasta / nome).write_text(conteudo, encoding="utf-8")
        return pasta

    def test_as_duas_listas_saem_separadas(self) -> None:
        pasta = self._pasta({"a.txt": "attack\nAlekhine\nposition\nKarpov\n"})
        listas, _ = lex.construir(pasta)
        self.assertEqual({"attack", "position"}, listas["idioma"])
        self.assertEqual({"alekhine", "karpov"}, listas["nomes"])

    def test_a_mesma_palavra_nao_vai_nos_dois_arquivos(self) -> None:
        """`bishop` e `Bishop` são a mesma entrada depois do `casefold`."""
        pasta = self._pasta({"a.txt": "bishop\nBishop\n"})
        listas, _ = lex.construir(pasta)
        self.assertEqual({"bishop"}, listas["idioma"])
        self.assertEqual(set(), listas["nomes"])

    def test_a_lista_corrompida_e_ignorada_pelo_nome(self) -> None:
        nome = lex.IGNORADOS[0]
        pasta = self._pasta({nome: "Cortesulio\nLinaresariano\n", "boa.txt": "Alekhine\n"})
        listas, relatorio = lex.construir(pasta)
        self.assertEqual({"alekhine"}, listas["nomes"])
        ignorados = [linha for linha in relatorio if linha.get("ignorado")]
        self.assertEqual([nome], [linha["arquivo"] for linha in ignorados])

    def test_o_byte_invalido_nao_derruba_a_construcao(self) -> None:
        """As listas vêm de fora: um byte torto em 259 mil linhas não pode parar tudo."""
        pasta = Path(tempfile.mkdtemp())
        (pasta / "a.txt").write_bytes(b"attack\n\xff\xfe\nposition\n")
        listas, _ = lex.construir(pasta)
        self.assertEqual({"attack", "position"}, listas["idioma"])


class EscreverTests(unittest.TestCase):
    def test_o_arquivo_e_o_mesmo_byte_a_byte_em_duas_construcoes(self) -> None:
        """Sem `mtime=0` o gzip carrega a hora, e reconstruir sujaria a árvore de trabalho."""
        with tempfile.TemporaryDirectory() as pasta:
            alvo = Path(pasta) / "l.txt.gz"
            lex.escrever(alvo, {"attack", "position"})
            primeiro = alvo.read_bytes()
            lex.escrever(alvo, {"position", "attack"})
            self.assertEqual(primeiro, alvo.read_bytes())

    def test_o_que_foi_escrito_e_o_que_o_dicionario_le(self) -> None:
        """As duas pontas têm de casar: quem escreve é este comando, quem lê é o dicionário."""
        with tempfile.TemporaryDirectory() as pasta:
            alvo = Path(pasta) / "l.txt.gz"
            lex.escrever(alvo, {"attack", "position"})
            self.assertEqual(frozenset({"attack", "position"}), dic.carregar(alvo))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
