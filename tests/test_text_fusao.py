"""O roteador de tokens: prosa de um leitor, notação do outro, e a marca por palavra (S-716, S-717, S-718)."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest import mock

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
        self.assertEqual(fusao.texto_fundido(fusao.fundir("♘e1", "Gelfand", existe=existe_na_camada, da_camada=True)), "Gelfand")
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
        self.assertEqual(fundida("white knight", "white", guarda_prosa_sem_par=True), "white knight")

    def test_a_regra_5_guarda_palavra_e_nao_o_que_o_glifo_inventou(self) -> None:
        """Medido: guardar tudo põe a prosa de 0,24% em 0,42% no ouro-dev. É o ruído do glifo que entra."""
        self.assertEqual(fundida("white xyz", "white", guarda_prosa_sem_par=True), "white")

    def test_a_palavra_guardada_tem_a_confianca_mais_baixa_da_linha(self) -> None:
        tokens = fusao.fundir("white knight", "white", existe=existe, guarda_prosa_sem_par=True, confiancas_do_glifo=(0.4, 0.99))
        self.assertEqual(0.4, tokens[1].confianca)

    def test_token_bloqueado_fica_com_o_glifo(self) -> None:
        # A camada do Chess Evolution escreve `afer` por `after`: a palavra suspeita não vence.
        self.assertEqual(fundida("after this", "afer this", bloqueados=[True, False]), "after this")

    def test_token_bloqueado_sem_par_nao_entra(self) -> None:
        self.assertEqual(fundida("white", "white afer", bloqueados=[False, True]), "white")


class LanceInteiroNaoSeVetaTests(unittest.TestCase):
    """As pendências da S-723 e a G1(a): `Pas`, `Axed`, `fixes` e `Das` são palavras, e a tinta era um lance."""

    def existe(self, token: str) -> bool:
        return fusao.existe_no(frozenset({"fixes", "axed", "tipo", "aguda"}), curtas=frozenset({"das", "pas", "de", "the"}))(token)

    def test_o_lance_inteiro_fica(self) -> None:
        for glifo, lido in (("♔a4", "Das"), ("♕xe5", "fixes"), ("♘xc4", "Axed"), ("♔a5", "Pas"), ("♕d6.", "de.")):
            with self.subTest(glifo=glifo):
                self.assertEqual(glifo, fusao.texto_fundido(fusao.fundir(glifo, lido, existe=self.existe)))

    def test_o_que_o_glifo_inventa_em_palavra_ainda_perde(self) -> None:
        for glifo, lido in (("♔e", "the"), ("♔o", "tipo"), ("WUd♔", "aguda")):
            with self.subTest(glifo=glifo):
                self.assertEqual(lido, fusao.texto_fundido(fusao.fundir(glifo, lido, existe=self.existe)))

    def test_desligada_a_palavra_vence_o_lance_como_antes(self) -> None:
        with mock.patch.object(fusao, "LANCE_INTEIRO_NAO_SE_VETA", False):
            self.assertEqual("Das", fusao.texto_fundido(fusao.fundir("♔a4", "Das", existe=self.existe)))

    def test_o_veto_e_ouvido_para_a_g1a(self) -> None:
        ouvidos: list[tuple[str, str]] = []
        with mock.patch.object(fusao, "OUVINTE_DE_VETOS", lambda g, t: ouvidos.append((g, t))):
            fusao.fundir("♔o ♔a4", "tipo Das", existe=self.existe)
        self.assertEqual([("♔o", "tipo")], ouvidos)


class FiguraForaDeLanceTests(unittest.TestCase):
    def test_contra_palavra_longa_fora_do_lexico_ela_perde(self) -> None:
        # `ruinös` não está na lista do alemão, e `nta♔` não é lance em língua nenhuma.
        for glifo, lido in (("nta♔.", "ruinös."), ("ge♔h1ich", "gemächlich")):
            with self.subTest(glifo=glifo):
                self.assertEqual(lido, fundida(glifo, lido))

    def test_contra_lance_estragado_curto_ela_fica(self) -> None:
        # O `acl` de `♖ac1`: letras, e não palavra. Sem o mínimo, o lance ia embora.
        self.assertEqual("♖ac", fundida("♖ac", "acl"))

    def test_o_lance_com_a_cor_do_enunciado_e_lance(self) -> None:
        self.assertEqual("W♔d5,", fundida("W♔d5,", "Weds,"))

    def test_a_promocao_com_figurina_e_lance(self) -> None:
        self.assertEqual("e8♕", fundida("e8♕", "e8Wife"))


class LanceTortoTests(unittest.TestCase):
    def test_o_lance_estragado_sem_par_nao_entra_ao_lado_do_glifo(self) -> None:
        """`14...♕c6` contra `14...` e `Hc6`: 14 dos erros de notação a mais do *Chess Evolution*."""
        self.assertEqual("14...♕c6 white", fundida("14...♕c6 white", "14... Hc6 white"))
        self.assertEqual("14 ♔h1", fundida("14 ♔h1", "14 ♔h1 &hl!,"))

    def test_o_nome_que_termina_em_letra_entra(self) -> None:
        self.assertEqual("white Hal", fundida("white", "white Hal"))

    def test_o_ponto_solto_nao_e_tirado_do_lance(self) -> None:
        self.assertEqual(".. ...♕f5,", fundida("...♕f5,", ".. Hf5,"))


class NumeroEReticenciaTests(unittest.TestCase):
    def test_o_numero_do_glifo_nao_se_cola_ao_lance(self) -> None:
        for leitor in ("28711", "Ea836"):
            with self.subTest(leitor=leitor):
                self.assertEqual(leitor[-2:], fundida(leitor[-2:], leitor))

    def test_o_numero_da_folha_que_o_glifo_cortou_volta(self) -> None:
        self.assertEqual("1166", fundida("66", "1166"))

    def test_o_numero_partido_volta_inteiro(self) -> None:
        self.assertEqual("13 Fischer", fundida("1 3 Fischer", "13 Fischer"))

    def test_a_reticencia_partida_volta_inteira(self) -> None:
        self.assertEqual("6... ♕f6", fundida("6. . . ♕f6", "6... Wf6"))
        self.assertEqual("37... ♘e5", fundida("37.. . ♘e5", "37... Ae5"))

    def test_sem_o_leitor_ver_a_reticencia_os_pontos_ficam(self) -> None:
        self.assertEqual("6. . . ♕f6", fundida("6. . . ♕f6", "6. Wf6"))

    def test_o_sinal_que_ja_veio_na_palavra_nao_repete(self) -> None:
        self.assertEqual("white!", fundida("white !", "white!"))


class RegraV3Tests(unittest.TestCase):
    """No scan, a notação em letra é do outro leitor, e só a figurina é de quem a vê."""

    def v3(self, glifo: str, leitor: str, **opcoes: object) -> str:
        return fundida(glifo, leitor, regra=fusao.V3, **opcoes)

    def test_a_notacao_em_letra_vai_ao_leitor(self) -> None:
        self.assertEqual("Lf1-d3 Kxf3", self.v3("Lf1-d8 Kxf8", "Lf1-d3 Kxf3"))
        # Na v5 a mesma linha fica com o glifo: é o que separa as duas.
        self.assertEqual("Lf1-d8 Kxf8", fundida("Lf1-d8 Kxf8", "Lf1-d3 Kxf3"))

    def test_a_figurina_fica_com_o_glifo_e_com_o_numero_do_leitor(self) -> None:
        self.assertEqual("17.♔xf3", self.v3("7.♔xf3", "17.Kxf3"))

    def test_a_palavra_que_existe_vence_a_figurina(self) -> None:
        self.assertEqual("the knight", self.v3("♔e knight", "the knight"))

    def test_sem_par_so_a_figurina_fica(self) -> None:
        # `Sg1-f3` é um token no Tesseract e dois no glifo: o `f3` sem par não é lance a mais.
        self.assertEqual("Sg1-f3", self.v3("Sg1 f3", "Sg1-f3"))
        self.assertEqual("white ♘f3", self.v3("white ♘f3", "white"))
        self.assertEqual("white", self.v3("white 1", "white"))

    def test_a_linha_que_o_leitor_leu_vazia_fica_com_o_glifo(self) -> None:
        """No *Bachmann*, `33. Tg2-g1 Dd1-f3+` sumia inteira: o `psm 7` não leu nada, e a notação em letra não tinha par."""
        self.assertEqual("33. Tg2 g1 Dd1 f3+", self.v3("33. Tg2 g1 Dd1 f3+", ""))

    def test_a_notacao_sem_par_do_leitor_entra(self) -> None:
        self.assertEqual("white Nf3", self.v3("white", "white Nf3"))

    def test_a_regra_nao_conhecida_e_a_v5_nao(self) -> None:
        self.assertEqual({"v5", "v3"}, set(fusao.REGRAS))


class RegrasDaSuiteTests(unittest.TestCase):
    """Das quatro regras de `caissa/ocr/fusion.py` que a S-707 mandou medir, a única nova que pagou."""

    def test_o_parentese_do_numero_volta_junto(self) -> None:
        self.assertEqual("(17...♘e5", fundida("7...♘e5", "(17...Ae5"))
        with mock.patch.object(fusao, "PARENTESE_DO_NUMERO", False):
            self.assertEqual("17...♘e5", fundida("7...♘e5", "(17...Ae5"))


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


def _importados_do_pacote(caminho: Path) -> set[str]:
    """Os módulos irmãos em `text/` que este arquivo importa, inclusive dentro de função."""
    nomes: set[str] = set()
    for no in ast.walk(ast.parse(caminho.read_text(encoding="utf-8"))):
        if isinstance(no, ast.ImportFrom) and no.level == 1:
            if no.module:
                nomes.add(no.module.split(".")[0])
            else:
                nomes.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module and no.module.startswith("chess_diagram_ocr.text"):
            nomes.update(a.name for a in no.names)
            nomes.add(no.module.rsplit(".", 1)[-1])
    return nomes


class FronteiraTests(unittest.TestCase):
    def test_o_roteador_nao_alcanca_a_regua_por_grafo_nenhum(self) -> None:
        """O instrumento não pode compartilhar código com o medido: nem direto, nem por quem `fusao.py` importa."""
        pasta = Path(fusao.__file__).parent
        vistos: set[str] = set()
        faltam = ["fusao"]
        while faltam:
            nome = faltam.pop()
            caminho = pasta / f"{nome}.py"
            if nome in vistos or not caminho.is_file():
                continue
            vistos.add(nome)
            faltam.extend(_importados_do_pacote(caminho))
        self.assertIn("lexico", vistos, "o varredor de import ficou vazio")
        self.assertFalse(vistos & {"regua_prosa", "relatorio_prosa", "bancada_prosa"}, "fusao.py alcança a régua")

    def test_a_lista_de_funcionais_curtas_e_privada(self) -> None:
        """Só `fusao.py` a escreve: no léxico compartilhado ela mudaria `dicionario.corrigir` e a junção de hífen."""
        pasta = Path(fusao.__file__).parents[1]
        for arquivo in pasta.rglob("*.py"):
            if arquivo.name != "fusao.py":
                texto = arquivo.read_text(encoding="utf-8")
                self.assertNotIn("CURTAS_POR_LINGUA", texto, arquivo.name)
                self.assertNotIn("fusao.CURTAS", texto, arquivo.name)

    def test_as_curtas_nao_foram_para_o_lexico_compartilhado(self) -> None:
        from chess_diagram_ocr.text import dicionario

        for palavra in ("the", "não", "und"):
            with self.subTest(palavra=palavra):
                self.assertNotIn(palavra, dicionario.carregar())


if __name__ == "__main__":
    unittest.main()
