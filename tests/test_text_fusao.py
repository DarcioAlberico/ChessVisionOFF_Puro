"""O roteador de tokens: prosa de um leitor, notação do outro, e a marca por palavra (S-716, S-717, S-718)."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from chess_diagram_ocr.text import fusao


def existe(token: str) -> bool:
    return fusao.existe_no(frozenset({"wins", "white", "with", "knight"}))(token)


def fundida(glifo: str, leitor: str, **opcoes: object) -> str:
    return fusao.texto_fundido(fusao.fundir(glifo, leitor, existe=existe, **opcoes))  # type: ignore[arg-type]


class ClasseDoTokenTests(unittest.TestCase):
    def test_lance_com_figurina_com_reticencia_e_descritiva_sao_notacao(self) -> None:
        for token in ("♘f3", "12.♘f3+", "...Nxc4", "e4", "O-O", "1-0", "P-K4", "QxQch", "17.", "!?", "Лb4"):
            with self.subTest(token=token):
                self.assertEqual(fusao.classe_do_token(token), fusao.NOTACAO)

    def test_palavra_e_prosa_e_numero_solto_e_outro(self) -> None:
        for token, classe in (("the", fusao.PROSA), ("knight,", fusao.PROSA), ("(1968)", fusao.OUTRO), ("—", fusao.OUTRO)):
            with self.subTest(token=token):
                self.assertEqual(fusao.classe_do_token(token), classe)


class ClasseDoTokenPrefixoTests(unittest.TestCase):
    def test_palavra_que_comeca_como_lance_nao_e_notacao(self) -> None:
        """`af7anca`, do glifo: sem âncora no fim, a palavra certa da camada perdia para ele."""
        self.assertEqual(fusao.classe_do_token("af7anca"), fusao.PROSA)

    def test_na_camada_a_prosa_vence_mesmo_fora_do_lexico(self) -> None:
        existe_na_camada = fusao.existe_na_camada(existe)
        self.assertEqual(fusao.texto_fundido(fusao.fundir("♘e1", "Gelfand", existe=existe_na_camada)), "Gelfand")
        self.assertEqual(fusao.texto_fundido(fusao.fundir("♘e1", "Ne1", existe=existe_na_camada)), "♘e1")


class RegrasDaFusaoTests(unittest.TestCase):
    def test_a_prosa_vem_do_outro_leitor(self) -> None:
        self.assertEqual(fundida("Wbite wlns", "White wins"), "White wins")

    def test_a_notacao_fica_com_o_glifo(self) -> None:
        # O Tesseract estraga lance de peão: `g4!` vira `24!`.
        self.assertEqual(fundida("g4! and", "24! and"), "g4! and")

    def test_a_palavra_que_existe_vence_a_notacao_do_glifo(self) -> None:
        # O glifo vê `♔e` em `the`; o outro leitor leu a palavra.
        self.assertEqual(fundida("♔e knight", "the knight"), "the knight")

    def test_o_numero_partido_pelo_glifo_volta_inteiro(self) -> None:
        self.assertEqual(fundida("1 7.♔xf3", "17.Kxf3"), "17.♔xf3")

    def test_numero_de_mesmo_tamanho_fica_o_do_glifo(self) -> None:
        self.assertEqual(fundida("21.♔xf3", "27.Kxf3"), "21.♔xf3")

    def test_prosa_sem_par_do_outro_leitor_entra_e_notacao_sem_par_nao(self) -> None:
        self.assertEqual(fundida("white", "white wins"), "white wins")
        self.assertEqual(fundida("white", "white Nf3"), "white")

    def test_notacao_do_glifo_sem_par_fica_e_prosa_sem_par_sai(self) -> None:
        self.assertEqual(fundida("white ♘f3", "white"), "white ♘f3")
        self.assertEqual(fundida("white xyz", "white"), "white")

    def test_guardar_a_prosa_sem_par_e_a_regra_da_s721(self) -> None:
        self.assertEqual(fundida("white xyz", "white", guarda_prosa_sem_par=True), "white xyz")

    def test_token_bloqueado_fica_com_o_glifo(self) -> None:
        # A camada do Chess Evolution escreve `afer` por `after`: a palavra suspeita não vence.
        self.assertEqual(fundida("after this", "afer this", bloqueados=[True, False]), "after this")

    def test_token_bloqueado_sem_par_nao_entra(self) -> None:
        self.assertEqual(fundida("white", "white afer", bloqueados=[False, True]), "white")


class MarcaPorPalavraTests(unittest.TestCase):
    def _linha(self, n: int) -> list[fusao.Token]:
        return [fusao.Token("white", "outro", "white", 0.99) for _ in range(n)]

    def test_o_teto_e_cinco_por_cento_das_palavras_da_folha(self) -> None:
        tokens = [fusao.Token(f"xq{k}", "outro", f"zz{k}", 0.2) for k in range(100)]
        marcadas = fusao.marcar([tokens], existe=existe)
        self.assertEqual(len(marcadas[0]), 5)

    def test_folha_pequena_nao_marca_nada(self) -> None:
        tokens = [fusao.Token(f"xq{k}", "outro", f"zz{k}", 0.2) for k in range(19)]
        self.assertEqual(fusao.marcar([tokens], existe=existe), [frozenset()])

    def test_as_marcadas_sao_as_mais_suspeitas(self) -> None:
        tokens = self._linha(40)
        tokens[7] = fusao.Token("xqz", "outro", "abc", 0.1)  # discorda, não existe e tem confiança baixa
        tokens[9] = fusao.Token("white", "outro", "whlte", 0.99)  # só discorda
        self.assertEqual(fusao.marcar([tokens], existe=existe), [frozenset({7, 9})])

    def test_prosa_da_camada_nunca_e_marcada(self) -> None:
        tokens = [fusao.Token(f"xq{k}", "outro", f"zz{k}", None) for k in range(100)]
        self.assertEqual(fusao.marcar([tokens], existe=existe, e_da_camada=True), [frozenset()])

    def test_a_confianca_de_um_motor_nao_pinta_o_texto_do_outro(self) -> None:
        # O texto é do outro leitor, concordam, e ele tem certeza: o glifo ter errado não muda nada.
        token = fusao.Token("white", "outro", "white", 0.99)
        self.assertEqual(fusao.suspeita_de(token, existe=existe), 0.0)

    def test_os_intervalos_apontam_a_palavra_no_texto(self) -> None:
        tokens = [fusao.Token(t, "outro") for t in ("uma", "duas", "tres")]
        texto = fusao.texto_fundido(tokens)
        ((inicio, fim),) = fusao.intervalos_de(tokens, {1})
        self.assertEqual(texto[inicio:fim], "duas")


class FronteiraTests(unittest.TestCase):
    def test_o_roteador_nao_importa_a_regua(self) -> None:
        """O instrumento não pode compartilhar código com o medido."""
        arvore = ast.parse(Path(fusao.__file__).read_text(encoding="utf-8"))
        nomes = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                nomes.update(a.name for a in no.names)
            elif isinstance(no, ast.ImportFrom):
                nomes.add(no.module or "")
                nomes.update(a.name for a in no.names)
        self.assertFalse({n for n in nomes if "regua" in n or "banco" in n}, "fusao.py importou a régua")

    def test_as_curtas_nao_foram_para_o_lexico_compartilhado(self) -> None:
        from chess_diagram_ocr.text import dicionario

        for palavra in ("the", "não", "und"):
            with self.subTest(palavra=palavra):
                self.assertNotIn(palavra, dicionario.carregar())


if __name__ == "__main__":
    unittest.main()
