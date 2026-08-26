"""Aplicar a todos os semelhantes: o critério é a imagem, e não o caractere lido (S-213).

**O que se trava aqui é o contrato, e não a qualidade do casamento.** Se um par de recortes é ou
não "o mesmo glifo" é julgamento sobre o material, e ele foi feito por medição -- a tabela está em
`docs/metrics/texto_semelhanca.json` e nos limiares de `LIMIAR_POR_RIGOR`. O que um teste pode
travar é o que quebraria calado: o lote aplicado sem ninguém olhar, a lista fora de ordem, a
segunda condição deixando de segurar a precisão, e o rigor virando escolha de risco.
"""

from __future__ import annotations

import unittest

import numpy as np

from chess_diagram_ocr.text.semelhanca import (
    LIMIAR_POR_RIGOR,
    PISO_DE_PRECISAO,
    RIGORES,
    Previsao,
    Semelhante,
    SemPrevisualizacao,
    aplicar,
    avaliar,
    descritores_de,
    distancias,
    limiar_de,
    previsualizar,
    semelhantes,
    tabela,
)


def familia(n_formas: int = 6, por_forma: int = 4, ruido: float = 0.01, semente: int = 0):
    """`(D, y)`: formas bem separadas, cada uma com irmãs a uma distância pequena e conhecida."""
    aleatorio = np.random.default_rng(semente)
    base = aleatorio.random((n_formas, 576)).astype(np.float32)
    D = np.repeat(base, por_forma, axis=0)
    D = np.clip(D + aleatorio.normal(0, ruido, D.shape).astype(np.float32), 0, 1)
    y = np.repeat(np.arange(n_formas), por_forma)
    return D, y


class CriterioTests(unittest.TestCase):
    def test_a_lista_sai_ordenada_por_distancia(self) -> None:
        """Critério de aceite: o duvidoso fica no fim, que é onde o olho deve parar."""
        alvo = np.zeros(576, np.float32)
        candidatos = np.stack([np.full(576, v, np.float32) for v in (0.20, 0.02, 0.10, 0.05)])
        achados = semelhantes(alvo, candidatos, rigor=0.30, mesma_leitura=False)
        distancias_achadas = [s.distancia for s in achados]
        self.assertEqual(sorted(distancias_achadas), distancias_achadas)
        self.assertEqual([1, 3, 2, 0], [s.indice for s in achados])

    def test_o_limiar_corta_e_o_rigor_e_o_numero(self) -> None:
        alvo = np.zeros(576, np.float32)
        candidatos = np.stack([np.full(576, v, np.float32) for v in (0.10, 0.50)])
        self.assertEqual(1, len(semelhantes(alvo, candidatos, rigor=0.20, mesma_leitura=False)))
        self.assertEqual(0, len(semelhantes(alvo, candidatos, rigor=0.05, mesma_leitura=False)))

    def test_a_busca_atravessa_a_classe(self) -> None:
        """É a diferença para `dedupe.agrupar`: ali o assunto é vazamento, aqui é o glifo que saiu da classe."""
        alvo = np.zeros(576, np.float32)
        candidatos = np.stack([np.full(576, 0.05, np.float32)] * 2)
        achados = semelhantes(alvo, candidatos, leituras=["c", "e"], leitura_do_alvo="c", mesma_leitura=False)
        self.assertEqual(2, len(achados), "sem a 2ª condição, a leitura não pode filtrar nada")

    def test_a_segunda_condicao_descarta_a_leitura_diferente(self) -> None:
        alvo = np.zeros(576, np.float32)
        candidatos = np.stack([np.full(576, 0.05, np.float32)] * 2)
        achados = semelhantes(alvo, candidatos, leituras=["c", "e"], leitura_do_alvo="c")
        self.assertEqual([0], [s.indice for s in achados])

    def test_sem_leitura_do_alvo_a_segunda_condicao_nao_esvazia_o_lote(self) -> None:
        """Filtrar por string vazia esvaziaria o lote em silêncio -- o pior jeito de uma trava falhar."""
        alvo = np.zeros(576, np.float32)
        candidatos = np.stack([np.full(576, 0.05, np.float32)] * 2)
        self.assertEqual(2, len(semelhantes(alvo, candidatos, leituras=["c", "e"])))

    def test_descritores_de_tamanhos_diferentes_levantam(self) -> None:
        with self.assertRaises(ValueError):
            distancias(np.zeros(576, np.float32), np.zeros((3, 100), np.float32))

    def test_sem_candidatos_devolve_lista_vazia(self) -> None:
        self.assertEqual([], semelhantes(np.zeros(576, np.float32), np.empty((0, 576), np.float32)))

    def test_rigor_desconhecido_levanta(self) -> None:
        with self.assertRaises(ValueError):
            limiar_de("muito_amplo")

    def test_o_descritor_e_o_da_S202(self) -> None:
        """Uma régua só entre os dois módulos: um limiar daqui quer dizer o mesmo que um de lá."""
        from chess_diagram_ocr.text.dedupe import LADO_DESCRITOR

        D = descritores_de(np.zeros((2, 1024), np.uint8))
        self.assertEqual(LADO_DESCRITOR * LADO_DESCRITOR, D.shape[1])


class PrevisualizacaoTests(unittest.TestCase):
    """Um em cada ~145 boxes sairia errado, e por isso aplicar em silêncio está fora de questão."""

    def previsao(self) -> Previsao:
        candidatos = [Semelhante(3, 0.10), Semelhante(1, 0.02), Semelhante(7, 0.25)]
        return previsualizar(alvo=0, para="e", candidatos=candidatos)

    def test_o_lote_exige_previsualizacao(self) -> None:
        with self.assertRaises(SemPrevisualizacao):
            aplicar(self.previsao())

    def test_previsualizar_nunca_devolve_lote_ja_olhado(self) -> None:
        """A trava é o valor, não a intenção: `previsualizar` não tem como marcar `olhada`."""
        self.assertFalse(self.previsao().olhada)

    def test_confirmado_o_lote_sai(self) -> None:
        self.assertEqual({1: "e", 3: "e", 7: "e"}, aplicar(self.previsao().confirmar()))

    def test_so_o_escolhido_entra_no_lote(self) -> None:
        self.assertEqual({1: "e"}, aplicar(self.previsao().confirmar(), [1]))

    def test_indice_fora_da_previsualizacao_e_recusado(self) -> None:
        """Aplicar a um box que não estava na lista olhada é aplicar sem lista."""
        with self.assertRaises(SemPrevisualizacao):
            aplicar(self.previsao().confirmar(), [1, 99])

    def test_a_previsualizacao_reordena_por_distancia(self) -> None:
        """A ordem é critério de aceite: garanti-la aqui tira a garantia de todo mundo lembrar."""
        self.assertEqual([1, 3, 7], [s.indice for s in self.previsao().candidatos])

    def test_a_pior_distancia_e_a_do_ultimo(self) -> None:
        self.assertAlmostEqual(0.25, self.previsao().pior_distancia)

    def test_o_duvidoso_e_o_que_passa_do_rigor_estrito(self) -> None:
        self.assertFalse(Semelhante(0, LIMIAR_POR_RIGOR["estrito"]).duvidoso)
        self.assertTrue(Semelhante(0, LIMIAR_POR_RIGOR["estrito"] + 0.01).duvidoso)

    def test_previsao_vazia_nao_estoura(self) -> None:
        vazia = previsualizar(0, "e", [])
        self.assertEqual(0.0, vazia.pior_distancia)
        self.assertEqual({}, aplicar(vazia.confirmar()))


class PlacarTests(unittest.TestCase):
    def test_a_mesma_leitura_segura_a_precisao_no_limiar_frouxo(self) -> None:
        """A afirmação central do item, sobre material sintético com a resposta conhecida.

        Metade dos pares próximos é de classes diferentes (o homóglifo), e o modelo os lê
        diferente. Sem a 2ª condição a precisão cai; com ela, volta -- **sem perder cobertura**,
        que é o que a medição nesta base mostrou (0,8276 -> 0,9971 com a mesma cobertura).
        """
        D, y = familia(n_formas=4, por_forma=4, ruido=0.005)
        # Um intruso colado na forma 0, mas de outra classe -- e o modelo o lê como outra coisa.
        D = np.vstack([D, D[0:1] + 0.01])
        y = np.concatenate([y, [99]])
        leituras = np.array([str(c) for c in y], dtype=object)

        so_imagem = avaliar(D, y, limiar=0.30)
        com_leitura = avaliar(D, y, limiar=0.30, leituras=leituras)
        self.assertGreater(com_leitura.precisao, so_imagem.precisao)
        self.assertLessEqual(so_imagem.pares_casados - com_leitura.pares_casados, so_imagem.pares_casados - so_imagem.pares_certos)

    def test_a_precisao_e_a_cobertura_saem_dos_pares(self) -> None:
        D, y = familia(n_formas=3, por_forma=3, ruido=0.002)
        placar = avaliar(D, y, limiar=0.30)
        self.assertEqual(9, placar.pares_da_mesma_classe)
        self.assertAlmostEqual(placar.pares_certos / placar.pares_casados, placar.precisao)
        self.assertAlmostEqual(placar.pares_certos / placar.pares_da_mesma_classe, placar.cobertura)

    def test_o_piso_decide_se_o_rigor_entrega_lote(self) -> None:
        """Critério de aceite: abaixo de ~99% o item entrega a pré-visualização e não o lote."""
        D, y = familia(n_formas=3, por_forma=3, ruido=0.002)
        self.assertTrue(avaliar(D, y, limiar=0.05).entrega_lote)
        # Limiar largo o bastante para casar tudo com tudo: a precisão vira a taxa de acaso.
        frouxo = avaliar(D, y, limiar=1.0)
        self.assertLess(frouxo.precisao, PISO_DE_PRECISAO)
        self.assertFalse(frouxo.entrega_lote)

    def test_placar_sem_par_nenhum_nao_divide_por_zero(self) -> None:
        D, y = familia(n_formas=2, por_forma=1)
        placar = avaliar(D, y, limiar=0.0)
        self.assertEqual(0.0, placar.precisao)
        self.assertEqual(0.0, placar.cobertura)

    def test_a_forma_de_D_e_y_tem_de_bater(self) -> None:
        with self.assertRaises(ValueError):
            avaliar(np.zeros((3, 576), np.float32), np.zeros(2), limiar=0.1)

    def test_a_tabela_diz_se_o_rigor_entrega_lote(self) -> None:
        D, y = familia(n_formas=3, por_forma=3, ruido=0.002)
        linhas = tabela({"imagem/normal": avaliar(D, y, limiar=1.0)})
        self.assertIn("NÃO", "\n".join(linhas))


class RigorTests(unittest.TestCase):
    def test_os_tres_rigores_crescem(self) -> None:
        """O rigor é escolha de **cobertura**: `amplo` alcança mais, e por isso o limiar é maior."""
        valores = [LIMIAR_POR_RIGOR[r] for r in RIGORES]
        self.assertEqual(sorted(valores), valores)
        self.assertEqual(len(set(valores)), len(valores))

    def test_todo_rigor_tem_limiar_e_todo_limiar_tem_rigor(self) -> None:
        self.assertEqual(set(RIGORES), set(LIMIAR_POR_RIGOR))

    def test_nenhum_rigor_e_o_limiar_da_quase_duplicata(self) -> None:
        """0,03 é o corte da S-202 e entrega 6% de cobertura aqui: um lote que não alcança nada."""
        from chess_diagram_ocr.text.dedupe import LIMIAR_PADRAO

        self.assertNotIn(LIMIAR_PADRAO, set(LIMIAR_POR_RIGOR.values()))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
