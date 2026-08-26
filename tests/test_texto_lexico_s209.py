"""O léxico sinaliza, e nunca troca (S-209).

**A regra que o item existe para garantir é negativa**, e por isso o teste mais importante daqui
afirma uma ausência: a palavra desconhecida sai **idêntica**. Não há neste módulo uma função que
troque palavra por palavra parecida, e nenhum teste pode provar que ela não existe -- o que se
prova é que a que existe devolve o texto sem tocá-lo.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.text import lexico
from chess_diagram_ocr.text.lexico import (
    HIFENS,
    MIN_TAMANHO,
    PERFIS,
    Marca,
    carregar,
    conhecida,
    juntar_hifenizadas,
    sinalizar,
    suspeita,
)

LEXICO = frozenset({"embarrassment", "position", "player", "well-known", "wellknown", "f-pawn", "fpawn", "xue", "fierro", "saint", "amant", "some", "so", "me"})


class SinalizacaoTests(unittest.TestCase):
    def test_palavra_desconhecida_sai_identica_e_marcada(self) -> None:
        """O critério de aceite do item, e a regra que contraria o instinto."""
        texto = "the Nimzowitsch position"
        marcas = sinalizar(texto, LEXICO)
        self.assertEqual(["Nimzowitsch"], [m.palavra for m in marcas])
        self.assertEqual("Nimzowitsch", texto[marcas[0].inicio : marcas[0].fim])

    def test_a_marca_nao_carrega_sugestao(self) -> None:
        """A ausência é a entrega: uma sugestão reescreveria os 18 lances que a S-209 mediu."""
        self.assertNotIn("sugestao", Marca(0, 1, "x").__dataclass_fields__)

    def test_o_exemplo_com_que_o_item_abre_e_marcado(self) -> None:
        """`Bib1i0g[aPhY` é o erro que o dicionário vê e a legalidade não."""
        marcas = sinalizar("uma Bib1i0g[aPhY no fim", LEXICO)
        self.assertEqual(["Bib1i0g[aPhY"], [m.palavra for m in marcas])

    def test_a_notacao_nao_e_marcada(self) -> None:
        """A porta larga troca o veto de dígito pela pergunta certa: isto é notação? (S-208)"""
        for token in ("15.Nf3", "Bd3+", "19...Rg8", "1-0", "1/2-1/2", "Nf3"):
            with self.subTest(token=token):
                self.assertEqual((), sinalizar(token, LEXICO))

    def test_a_palavra_conhecida_nao_e_marcada(self) -> None:
        self.assertEqual((), sinalizar("position player", LEXICO))

    def test_o_intervalo_ignorado_nao_e_conferido(self) -> None:
        """`[Diagrama 3]` é referência ao diagrama, e não texto do livro."""
        texto = "position Diagramax player"
        self.assertEqual(["Diagramax"], [m.palavra for m in sinalizar(texto, LEXICO)])
        self.assertEqual((), sinalizar(texto, LEXICO, ignorar=[(9, 18)]))

    def test_sem_lexico_nada_e_marcado_como_conhecido(self) -> None:
        """Léxico vazio marca tudo que é suspeito -- é o certo, e quem chama decide se o usa."""
        self.assertEqual(["position"], [m.palavra for m in sinalizar("position", frozenset())])


class PortaTests(unittest.TestCase):
    """A porta larga da sinalização, e por que ela não é a de `e_palavra`."""

    def test_a_porta_estreita_recusa_o_exemplo_do_item(self) -> None:
        """É o motivo de as duas existirem: `e_palavra` veta qualquer dígito."""
        self.assertFalse(lexico.e_palavra("Bib1i0g[aPhY"))
        self.assertTrue(suspeita("Bib1i0g[aPhY"))

    def test_as_duas_portas_concordam_na_notacao(self) -> None:
        for token in ("Nf3", "1.d4", "15"):
            with self.subTest(token=token):
                self.assertFalse(lexico.e_palavra(token))
                self.assertFalse(suspeita(token))

    def test_as_duas_portas_concordam_na_prosa(self) -> None:
        for token in ("position", "player", "Nimzowitsch"):
            with self.subTest(token=token):
                self.assertTrue(lexico.e_palavra(token))
                self.assertTrue(suspeita(token))

    def test_o_curto_fica_de_fora_das_duas(self) -> None:
        self.assertFalse(suspeita("Kf"))
        self.assertLess(len("Kf"), MIN_TAMANHO)

    def test_o_que_e_quase_so_pontuacao_fica_de_fora(self) -> None:
        self.assertFalse(suspeita("...!?+-"))


class JuncaoTests(unittest.TestCase):
    """A hifenizada da quebra de linha -- uma das duas fronteiras que o dicionário decide."""

    def test_a_hifenizada_da_quebra_de_linha_e_juntada(self) -> None:
        novas, juncoes = juntar_hifenizadas(["it was an em-", "barrassment for White"], LEXICO)
        self.assertEqual(["it was an embarrassment", "for White"], novas)
        self.assertEqual(1, len(juncoes))
        self.assertEqual("embarrassment", juncoes[0].junta)

    def test_o_nome_proprio_hifenizado_nao_e_juntado(self) -> None:
        """Critério de aceite: `Xue-Fierro` é nome composto, e `xuefierro` não está na lista."""
        for par in (["a partida Xue-", "Fierro terminou"], ["jogada por Saint-", "Amant em 1843"]):
            with self.subTest(par=par[0]):
                novas, juncoes = juntar_hifenizadas(par, LEXICO)
                self.assertEqual(par, novas)
                self.assertEqual((), juncoes)

    def test_a_hifenizada_do_autor_nao_e_juntada(self) -> None:
        """A terceira condição, e é ela que salva `f-pawn` e `h-file` -- a construção mais comum
        em prosa de xadrez. Medido no acervo: as 6 quebras hifenizadas das camadas editoradas são
        todas termo de xadrez ou lance, e as 6 são recusadas por ela."""
        novas, juncoes = juntar_hifenizadas(["the f-", "pawn is weak"], LEXICO)
        self.assertEqual(["the f-", "pawn is weak"], novas)
        self.assertEqual((), juncoes)
        self.assertTrue(conhecida("f-pawn", LEXICO), "a premissa do teste é o hífen estar na lista")

    def test_a_palavra_boa_que_decomporia_nao_e_partida(self) -> None:
        """Critério de aceite do item, e é o que a partição de colada faria se tivesse entrado.

        `some` decompõe em `so` + `me`, e as três estão no léxico. **Nenhuma função deste módulo a
        parte** -- ver `PARTIR_COLADAS`, que traz a medição que recusou a partição."""
        self.assertFalse(hasattr(lexico, "partir_coladas"))
        self.assertEqual(["some thing"], juntar_hifenizadas(["some thing"], LEXICO)[0])

    def test_o_intervalo_de_paginas_nao_e_juntado(self) -> None:
        """`pp. 4-` + `7` não é hifenização: o pedaço da esquerda tem de terminar em letra."""
        novas, juncoes = juntar_hifenizadas(["ver pp. 4-", "7 do livro"], LEXICO)
        self.assertEqual((), juncoes)
        self.assertEqual(["ver pp. 4-", "7 do livro"], novas)

    def test_a_meia_risca_nao_e_hifen_de_quebra(self) -> None:
        """`–` é intervalo, e aceitá-la juntaria dois números de página numa palavra."""
        self.assertNotIn("–", HIFENS)

    def test_a_linha_da_direita_que_esvazia_e_preservada(self) -> None:
        """Apagá-la desalinharia a lista de quem tem bbox por linha."""
        novas, _ = juntar_hifenizadas(["an em-", "barrassment"], LEXICO)
        self.assertEqual(2, len(novas))
        self.assertEqual("", novas[1])

    def test_sem_lexico_nada_e_juntado(self) -> None:
        """O dicionário é o **próprio critério**: sem ele não há decisão a tomar."""
        self.assertEqual((), juntar_hifenizadas(["an em-", "barrassment"], frozenset())[1])

    def test_uma_linha_so_nao_junta_nada(self) -> None:
        self.assertEqual((), juntar_hifenizadas(["an em-"], LEXICO)[1])


class PerfilTests(unittest.TestCase):
    """As duas listas são dados, e o perfil escolhe entre elas -- critério de aceite do item."""

    def test_todo_perfil_carrega(self) -> None:
        for nome in PERFIS:
            with self.subTest(perfil=nome):
                self.assertIsInstance(carregar(nome), frozenset)

    def test_o_perfil_sem_nomes_e_subconjunto_do_completo(self) -> None:
        self.assertTrue(carregar("sem-nomes") <= carregar("completo"))

    def test_o_perfil_desconhecido_levanta(self) -> None:
        """Um perfil errado não pode devolver o padrão em silêncio: mediria outra lista."""
        with self.assertRaises(ValueError):
            carregar("perfil-que-nao-existe")  # type: ignore[arg-type]

    def test_trocar_a_lista_nao_exige_mudar_codigo(self) -> None:
        """Todo perfil é uma tupla de caminhos: acrescentar lista é acrescentar linha em PERFIS."""
        for nome, arquivos in PERFIS.items():
            with self.subTest(perfil=nome):
                self.assertTrue(arquivos)
                self.assertTrue(all(str(a).endswith(".txt.gz") for a in arquivos))

    def test_arquivo_ausente_devolve_conjunto_vazio(self) -> None:
        """Ausente não é erro: sem léxico quem consulta devolve o que o modelo leu."""
        self.assertEqual(frozenset(), carregar(caminho=__file__ + ".nao-existe.txt.gz"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
