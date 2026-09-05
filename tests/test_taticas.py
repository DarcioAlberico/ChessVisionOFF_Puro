"""O casamento de diagrama com solução impressa, e o arquivo dele (S-539).

**O que estes testes travam.** As quatro decisões do módulo, cada uma pelo caso que a produziu:
o número que é uma **linha** e não um parágrafo (foi o que zerou a primeira medição do `Big Book
of Combinations`), a lista de soluções lida contra os números pedidos (o `2.` de dentro da solução
2 não pode reabri-la), a solução provando o lado a jogar, e a recusa carregando o motivo.

A `PaginaLida` dos casos é montada à mão, com bbox de verdade: a geometria **é** a régua aqui, e um
teste que passasse caixas de zero não mediria régua nenhuma.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import chess
from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr import taticas, taticas_arquivo
from chess_diagram_ocr.text.pagina import BlocoDeDiagrama, BlocoDeTexto, Coluna, LinhaLida, PaginaLida

# A posição do mate do pastor, que é o exercício mais curto que existe.
PASTOR = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR"
# Uma em que só as pretas têm lance de tática.
PRETAS = "6k1/5ppp/8/8/8/8/5PPP/1q4K1"


def _linha(texto: str, bbox: tuple[float, float, float, float]) -> LinhaLida:
    return LinhaLida(texto=texto, bbox=bbox)


def _paragrafo(*linhas: LinhaLida, legenda_de: int | None = None) -> BlocoDeTexto:
    bloco = BlocoDeTexto.de_linhas(linhas)
    return bloco if legenda_de is None else BlocoDeTexto(
        linhas=bloco.linhas, bbox=bloco.bbox, legenda_de=legenda_de
    )


def _folha(*blocos: object, pagina: int = 0, impressa: int | None = None) -> PaginaLida:
    return PaginaLida(
        pagina=pagina,
        numero_impresso=impressa,
        colunas=(Coluna(indice=0, blocos=tuple(blocos)),),  # type: ignore[arg-type]
    )


class NumeroDoExercicioTests(unittest.TestCase):
    """O número impresso junto ao diagrama, pela geometria."""

    def _folha_do_schiller(self) -> PaginaLida:
        """A folha 21 do `Big Book of Combinations`, com as caixas medidas dela (2026-09-04).

        O número, o nome dos jogadores e o torneio são **um** parágrafo de três linhas, e o
        diagrama vem logo abaixo. É o caso que a primeira redação errava.
        """
        return _folha(
            _paragrafo(
                _linha("5", (98, 33, 107, 46)),
                _linha("Morphy-De Riviere", (57, 50, 147, 61)),
                _linha("Paris, 1858", (77, 61, 127, 72)),
            ),
            BlocoDeDiagrama(indice=0, bbox=(46, 76, 155, 185)),
        )

    def test_o_numero_e_a_linha_e_nao_o_paragrafo(self) -> None:
        """**A medição que reescreveu a função.** Perguntando ao parágrafo, nenhum dos 1.000
        exercícios daquele livro tinha número, porque o parágrafo é `5 Morphy-De Riviere Paris,
        1858`. Perguntando à linha, o `5` aparece sozinho, centrado sobre o tabuleiro."""
        self.assertEqual(5, taticas.numero_junto_ao_diagrama(self._folha_do_schiller(), 0))

    def test_o_numero_embaixo_do_diagrama_tambem_conta(self) -> None:
        """O acervo faz os dois: o `Manual of Chess Combinations` imprime embaixo."""
        pagina = _folha(
            BlocoDeDiagrama(indice=0, bbox=(46, 76, 155, 185)),
            _paragrafo(_linha("97.", (95, 190, 110, 202))),
        )
        self.assertEqual(97, taticas.numero_junto_ao_diagrama(pagina, 0))

    def test_o_numero_longe_demais_nao_e_deste_diagrama(self) -> None:
        """O teto é `DISTANCIA_DO_NUMERO` da altura do tabuleiro: mais que isso é o número do
        diagrama seguinte, que está a uma altura inteira de distância."""
        altura = 185 - 76
        longe = 76 - int(altura * taticas.DISTANCIA_DO_NUMERO) - 20
        pagina = _folha(
            _paragrafo(_linha("5", (98, longe - 12, 107, longe))),
            BlocoDeDiagrama(indice=0, bbox=(46, 76, 155, 185)),
        )
        self.assertIsNone(taticas.numero_junto_ao_diagrama(pagina, 0))

    def test_o_numero_de_outra_coluna_nao_conta(self) -> None:
        """Duas colunas de exercícios lado a lado: o que ata o número ao tabuleiro é a coluna."""
        pagina = _folha(
            _paragrafo(_linha("8", (256, 33, 307, 46))),
            BlocoDeDiagrama(indice=0, bbox=(46, 76, 155, 185)),
        )
        self.assertIsNone(taticas.numero_junto_ao_diagrama(pagina, 0))

    def test_um_bloco_com_texto_junto_do_numero_nao_e_numero(self) -> None:
        """`97. Alekhine` é legenda; tomá-la por número faria a legenda virar gabarito."""
        pagina = _folha(
            _paragrafo(_linha("97. Alekhine", (90, 40, 160, 52))),
            BlocoDeDiagrama(indice=0, bbox=(46, 76, 155, 185)),
        )
        self.assertIsNone(taticas.numero_junto_ao_diagrama(pagina, 0))

    def test_o_numero_da_propria_folha_nao_e_numero_de_exercicio(self) -> None:
        """**Num livro de um diagrama por folha, o número de página cai dentro do teto** (S-539,
        r2). O `Great Chess Combinations` do Anand tem um tabuleiro que ocupa metade da página, e o
        número impresso na margem ficava a menos de meia altura dele: **78 dos 83** números daquele
        livro eram o número da folha, e três chegaram a virar exercício com gabarito de peão. No
        `Big Book`, onde as duas numerações são colunas distantes, a exclusão custa um em 1.002.
        """
        pagina = _folha(
            BlocoDeDiagrama(indice=0, bbox=(46, 76, 155, 185)),
            _paragrafo(_linha("73", (95, 190, 110, 202))),
            impressa=73,
        )
        self.assertIsNone(taticas.numero_junto_ao_diagrama(pagina, 0))

    def test_a_corrida_preenche_o_que_a_leitura_perdeu(self) -> None:
        """Uma folha `97 98 ? 100` perdeu o 99 por leitura, não por o livro não o ter impresso."""
        pagina = _folha(
            _paragrafo(_linha("97", (60, 10, 70, 20))),
            BlocoDeDiagrama(indice=0, bbox=(46, 30, 155, 130)),
            _paragrafo(_linha("98", (60, 140, 70, 150))),
            BlocoDeDiagrama(indice=1, bbox=(46, 160, 155, 260)),
            BlocoDeDiagrama(indice=2, bbox=(46, 290, 155, 390)),
            _paragrafo(_linha("100", (60, 400, 75, 410))),
            BlocoDeDiagrama(indice=3, bbox=(46, 420, 155, 520)),
        )
        diagramas = [taticas.DiagramaLido(indice=i, placement=PASTOR) for i in range(4)]
        self.assertEqual({0: 97, 1: 98, 2: 99, 3: 100}, taticas.numeros_da_folha(pagina, diagramas))

    def test_a_corrida_nao_sobrescreve_o_que_foi_lido(self) -> None:
        """**O papel vence a corrida, e é a correção da segunda rodada** (2026-09-05).

        A versão anterior devolvia `base + posição` para todos os diagramas, e um `1858` de
        `Paris, 1858` deslocava a folha inteira. Medido no `Big Book of Combinations`: corrigir o
        intruso custa quatro números certos (939 contra 943 em 944 conferíveis contra a folha
        impressa) e a corrida também erra -- na folha 64 ela apagava um `251` impresso. Um número
        que nenhuma lista responde vira recusa; um número trocado vira o gabarito de outro
        exercício, que é o pior resultado possível deste módulo.
        """
        pagina = _folha(
            _paragrafo(_linha("5", (60, 10, 70, 20))),
            BlocoDeDiagrama(indice=0, bbox=(46, 30, 155, 130)),
            _paragrafo(_linha("1858", (60, 140, 80, 150))),
            BlocoDeDiagrama(indice=1, bbox=(46, 160, 155, 260)),
            _paragrafo(_linha("7", (60, 270, 70, 280))),
            BlocoDeDiagrama(indice=2, bbox=(46, 290, 155, 390)),
        )
        diagramas = [taticas.DiagramaLido(indice=i, placement=PASTOR) for i in range(3)]
        self.assertEqual({0: 5, 1: 1858, 2: 7}, taticas.numeros_da_folha(pagina, diagramas))

    def test_a_corrida_nao_repete_numero_que_a_folha_ja_usou(self) -> None:
        """**Um diagrama a mais na varredura inventava o número do exercício seguinte.**

        Era o defeito medido: 57 números do `Big Book` eram dados a dois diagramas diferentes, e o
        último de uma folha recebia o primeiro da folha seguinte -- `96` em duas. Aqui a caixa
        extra fica **sem** número, que é a resposta honesta.
        """
        pagina = _folha(
            _paragrafo(_linha("11", (60, 10, 72, 20))),
            BlocoDeDiagrama(indice=0, bbox=(46, 30, 155, 130)),
            _paragrafo(_linha("12", (60, 140, 72, 150))),
            BlocoDeDiagrama(indice=1, bbox=(46, 160, 155, 260)),
            BlocoDeDiagrama(indice=2, bbox=(46, 290, 155, 390)),
        )
        # O terceiro diagrama é uma detecção a mais: nenhum número foi impresso perto dele.
        diagramas = [taticas.DiagramaLido(indice=i, placement=PASTOR) for i in range(3)]
        achados = taticas.numeros_da_folha(pagina, diagramas)
        self.assertEqual({0: 11, 1: 12, 2: 13}, achados)
        self.assertEqual(len(set(achados.values())), len(achados), "nenhum número em dois lugares")

    def test_a_folha_decide_de_que_lado_esta_o_numero(self) -> None:
        """**O defeito que deslocou os 963 números do `Big Book` de um** (2026-09-05).

        O livro imprime o número **em cima** do tabuleiro, e o de baixo -- que é o do diagrama
        seguinte -- fica mais perto: 14,6 pt contra 29,2 pt na folha 37. Escolhendo pelo mais
        próximo, cada diagrama recebia o número do vizinho e o acerto contra a folha impressa era
        **zero**; deixando a folha votar pela corrida que os dois lados produzem, 943 de 944.
        """
        blocos: list[object] = []
        # Três tabuleiros empilhados, com o número 20 pt acima de cada um e 60 pt abaixo do
        # anterior: é a geometria medida do `Big Book`.
        for posicao in range(3):
            topo = 40 + posicao * 160
            blocos.append(_paragrafo(_linha(str(31 + posicao), (60, topo - 20, 72, topo - 8))))
            blocos.append(BlocoDeDiagrama(indice=posicao, bbox=(46, topo, 155, topo + 110)))
        pagina = _folha(*blocos)
        diagramas = [taticas.DiagramaLido(indice=i, placement=PASTOR) for i in range(3)]
        # O mais próximo do primeiro tabuleiro é o `32` de baixo, a 42 pt; o dele é o `31`, a 8 pt.
        self.assertEqual({0: 31, 1: 32, 2: 33}, taticas.numeros_da_folha(pagina, diagramas))
        self.assertEqual(31, taticas.numero_junto_ao_diagrama(pagina, 0, lado=taticas.LADO_ACIMA))
        self.assertEqual(32, taticas.numero_junto_ao_diagrama(pagina, 0, lado=taticas.LADO_ABAIXO))

    def test_a_folha_que_imprime_embaixo_continua_sendo_lida(self) -> None:
        """O voto não é uma preferência pelo lado de cima: o `Manual of Chess Combinations`
        imprime embaixo, e ali a corrida de baixo é a que fecha."""
        blocos: list[object] = []
        for posicao in range(3):
            topo = 40 + posicao * 160
            blocos.append(BlocoDeDiagrama(indice=posicao, bbox=(46, topo, 155, topo + 110)))
            blocos.append(
                _paragrafo(_linha(str(168 + posicao), (60, topo + 118, 78, topo + 130)))
            )
        pagina = _folha(*blocos)
        diagramas = [taticas.DiagramaLido(indice=i, placement=PASTOR) for i in range(3)]
        self.assertEqual({0: 168, 1: 169, 2: 170}, taticas.numeros_da_folha(pagina, diagramas))

    def test_sem_maioria_nada_e_preenchido(self) -> None:
        """Dois deslocamentos empatados: a folha não tem corrida, e inventar seria pior que calar."""
        pagina = _folha(
            _paragrafo(_linha("5", (60, 10, 70, 20))),
            BlocoDeDiagrama(indice=0, bbox=(46, 30, 155, 130)),
            _paragrafo(_linha("41", (60, 140, 75, 150))),
            BlocoDeDiagrama(indice=1, bbox=(46, 160, 155, 260)),
        )
        diagramas = [taticas.DiagramaLido(indice=i, placement=PASTOR) for i in range(2)]
        self.assertEqual({0: 5, 1: 41}, taticas.numeros_da_folha(pagina, diagramas))

    def test_folha_sem_numero_nenhum_devolve_vazio(self) -> None:
        pagina = _folha(BlocoDeDiagrama(indice=0, bbox=(46, 76, 155, 185)))
        self.assertEqual({}, taticas.numeros_da_folha(pagina, [taticas.DiagramaLido(0, PASTOR)]))
        self.assertIsNone(taticas.numero_junto_ao_diagrama(None, 0))


class ListaDeSolucoesTests(unittest.TestCase):
    """A folha das soluções, lida contra os números que os diagramas pediram."""

    def _folha_de_solucoes(self) -> PaginaLida:
        """A forma do `Manual of Chess Combinations`: número, jogadores, ano, e a linha."""
        return _folha(
            _paragrafo(
                _linha("70. Kupffer, 1898. 1.Qxf7# ", (10, 10, 300, 22)),
                _linha("71. Altrock - Muller, 1988. 1.Nc3 Nf6 2.d3 ", (10, 24, 300, 36)),
                _linha("72. Suba - Portisch, 1984. 1.Nf3 d6 2.d4 ", (10, 38, 300, 50)),
            ),
            pagina=94,
        )

    def test_as_tres_entradas_saem_com_a_linha_de_lances(self) -> None:
        achados = taticas.solucoes_da_folha(self._folha_de_solucoes(), [70, 71, 72])
        self.assertEqual([70, 71, 72], sorted(achados))
        self.assertEqual(("1.Nc3", "Nf6", "2.d3"), achados[71])

    def test_o_numero_de_lance_de_dentro_da_solucao_nao_abre_entrada(self) -> None:
        """**A razão de a busca ser guiada pelos esperados.** `1.` e `2.` estão em toda entrada; uma
        varredura cega de `\\d+\\.` acharia dezenas de entradas numa folha que tem três."""
        achados = taticas.solucoes_da_folha(self._folha_de_solucoes(), [1, 2, 70, 71])
        self.assertEqual([70, 71], sorted(achados))

    def test_um_numero_que_a_folha_nao_traz_simplesmente_nao_aparece(self) -> None:
        self.assertNotIn(99, taticas.solucoes_da_folha(self._folha_de_solucoes(), [70, 99]))

    def test_a_folha_de_exercicios_nao_e_lida_como_folha_de_solucoes(self) -> None:
        """Os mesmos números estão lá, sozinhos embaixo dos diagramas -- e sem lance nenhum atrás.
        É a condição que dispensa uma régua de "esta folha é a das soluções"."""
        exercicios = _folha(
            _paragrafo(_linha("70", (60, 10, 70, 20))),
            BlocoDeDiagrama(indice=0, bbox=(46, 30, 155, 130)),
            _paragrafo(_linha("71", (60, 140, 70, 150))),
            BlocoDeDiagrama(indice=1, bbox=(46, 160, 155, 260)),
        )
        self.assertEqual({}, taticas.solucoes_da_folha(exercicios, [70, 71]))

    def test_folha_vazia_e_lista_vazia(self) -> None:
        self.assertEqual({}, taticas.solucoes_da_folha(None, [1]))
        self.assertEqual({}, taticas.solucoes_da_folha(self._folha_de_solucoes(), []))


class LinhaAoLadoTests(unittest.TestCase):
    """O gabarito impresso junto do diagrama, para os livros sem lista no fim."""

    def test_o_paragrafo_atado_ao_diagrama_vence(self) -> None:
        pagina = _folha(
            BlocoDeDiagrama(indice=0, bbox=(46, 30, 155, 130)),
            _paragrafo(_linha("1.Qxf7# 1-0", (46, 140, 200, 152)), legenda_de=0),
        )
        self.assertEqual(("1.Qxf7#", "1-0"), taticas.linha_ao_lado(pagina, 0))

    def test_sem_vinculo_vale_a_primeira_linha_de_notacao_abaixo(self) -> None:
        pagina = _folha(
            BlocoDeDiagrama(indice=0, bbox=(46, 30, 155, 130)),
            _paragrafo(_linha("A posição é de Morphy.", (46, 140, 200, 152))),
            _paragrafo(_linha("1.Qxf7+ Kxf7 2.Nd6+", (46, 160, 200, 172))),
        )
        self.assertEqual(("1.Qxf7+", "Kxf7", "2.Nd6+"), taticas.linha_ao_lado(pagina, 0))

    def test_legenda_de_partida_nao_e_linha_de_lances(self) -> None:
        """`Ivkov—Dueckstein 1967` traz um número que parece número de lance, e é legenda."""
        pagina = _folha(
            BlocoDeDiagrama(indice=0, bbox=(46, 30, 155, 130)),
            _paragrafo(_linha("Ivkov — Dueckstein, Amsterdam 1967", (46, 140, 220, 152))),
        )
        self.assertEqual((), taticas.linha_ao_lado(pagina, 0))


class ValidacaoDaSolucaoTests(unittest.TestCase):
    """A solução jogada sobre a posição -- e o lado a jogar que sai dela."""

    def test_a_solucao_prova_o_lado_a_jogar(self) -> None:
        """**O resultado mais barato do módulo.** `semantics.infer_side_to_move` chuta brancas
        quando as duas são legais; a linha impressa é prova."""
        solucao = taticas.validar_solucao(PRETAS, ["1...", "Qg6+"], vez="w")
        self.assertEqual("b", solucao.vez)
        self.assertTrue(solucao.fechou)

    def test_o_palpite_anterior_desempata(self) -> None:
        """Quando os dois lados sustentam o mesmo tanto, o que o pipeline achou fica: ignorá-lo
        seria trocar informação por moeda."""
        aberta = "8/8/4k3/8/8/4K3/8/8"
        self.assertEqual("b", taticas.validar_solucao(aberta, ["Kd6"], vez="b").vez)
        self.assertEqual("w", taticas.validar_solucao(aberta, ["Kd4"], vez="w").vez)

    def test_a_linha_que_nao_fecha_entrega_o_que_fechou_e_diz_onde_parou(self) -> None:
        """**Linha parcial vale**: o que vem depois do gabarito numa lista de soluções é variante
        e sujeira de OCR, e parar ali é ler certo. O motivo fica gravado para quem for conferir."""
        solucao = taticas.validar_solucao(PASTOR, ["1.", "Qxf7#", "2.", "Qh8"])
        self.assertEqual(("Qxf7#",), solucao.lances)
        self.assertFalse(solucao.fechou)
        self.assertIn("Qh8", solucao.motivo + solucao.token)

    def test_posicao_ilegal_nao_derruba_o_modulo(self) -> None:
        solucao = taticas.validar_solucao("isto-nao-e-uma-fen", ["1.", "e4"])
        self.assertFalse(solucao.fechou)
        self.assertIn("FEN", solucao.motivo)

    def test_linha_vazia_tem_motivo_proprio(self) -> None:
        self.assertIn("lance", taticas.validar_solucao(PASTOR, []).motivo)

    def test_o_desfecho_separa_mate_de_material_e_de_nada(self) -> None:
        """**"Sem ganho" é etiqueta e não recusa**: metade dos livros para em `+-`."""
        pastor = taticas.compose_fen(PASTOR, chess.WHITE)
        self.assertEqual(taticas.MATE, taticas.desfecho(pastor, ["Qxf7#"]))
        material = taticas.compose_fen("1R4k1/5ppp/8/8/8/8/5PPP/1q4K1", chess.BLACK)
        self.assertEqual(taticas.GANHA_MATERIAL, taticas.desfecho(material, ["Qxb8"]))
        self.assertEqual(taticas.SEM_GANHO, taticas.desfecho(pastor, ["Nf3"]))
        self.assertEqual(taticas.SEM_GANHO, taticas.desfecho(pastor, ["Qh8"]))


class ExtracaoTests(unittest.TestCase):
    """As duas passadas: os números primeiro, as listas depois."""

    def _livro(self) -> list[taticas.Folha]:
        exercicios = _folha(
            _paragrafo(_linha("70", (60, 10, 70, 20))),
            BlocoDeDiagrama(indice=0, bbox=(46, 30, 155, 130)),
            _paragrafo(_linha("71", (60, 140, 70, 150))),
            BlocoDeDiagrama(indice=1, bbox=(46, 160, 155, 260)),
            pagina=20,
            impressa=14,
        )
        solucoes = _folha(
            _paragrafo(
                _linha("70. Kupffer, 1898. 1.Qxf7# ", (10, 10, 300, 22)),
                _linha("71. Altrock, 1988. 1.Nc3 Nf6 ", (10, 24, 300, 36)),
            ),
            pagina=94,
        )
        return [
            taticas.Folha(
                pagina=20,
                texto=exercicios,
                diagramas=(
                    taticas.DiagramaLido(0, PASTOR),
                    taticas.DiagramaLido(1, PASTOR),
                ),
            ),
            taticas.Folha(pagina=94, texto=solucoes),
        ]

    def test_os_dois_diagramas_viram_exercicio_com_procedencia(self) -> None:
        extracao = taticas.extrair(self._livro(), livro="C:/PDF/Reinfeld 1001.pdf")
        self.assertEqual(2, extracao.diagramas)
        self.assertEqual(2, len(extracao.exercicios))
        primeiro = extracao.exercicios[0]
        self.assertEqual(("Qxf7#",), primeiro.lances)
        self.assertEqual(taticas.NO_FIM, primeiro.origem)
        self.assertEqual(94, primeiro.folha_da_solucao)
        self.assertEqual("Reinfeld 1001, p. 14, exercício 70", primeiro.procedencia.frase())

    def test_a_conta_fecha_entre_exercicios_e_recusas(self) -> None:
        """Um diagrama que não aparece nem de um lado nem do outro é um diagrama perdido."""
        folhas = self._livro()
        folhas[0] = taticas.Folha(
            pagina=20,
            texto=folhas[0].texto,
            diagramas=(*folhas[0].diagramas, taticas.DiagramaLido(2, "")),
        )
        extracao = taticas.extrair(folhas, livro="livro.pdf")
        self.assertEqual(3, extracao.diagramas)
        self.assertEqual(3, len(extracao.exercicios) + len(extracao.recusas))
        self.assertEqual({taticas.SEM_FEN: 1}, extracao.por_motivo())

    def test_o_diagrama_sem_numero_recusa_com_o_motivo(self) -> None:
        folhas = [
            taticas.Folha(
                pagina=0,
                texto=_folha(BlocoDeDiagrama(indice=0, bbox=(46, 30, 155, 130))),
                diagramas=(taticas.DiagramaLido(0, PASTOR),),
            )
        ]
        extracao = taticas.extrair(folhas, livro="livro.pdf")
        self.assertEqual({taticas.SEM_NUMERO: 1}, extracao.por_motivo())
        self.assertIn("0 com solução", extracao.resumo())

    def test_a_lista_vence_a_linha_ao_lado(self) -> None:
        """O número foi escrito pelo autor nos dois lugares; a vizinhança na página é inferência."""
        exercicios = _folha(
            _paragrafo(_linha("70", (60, 10, 70, 20))),
            BlocoDeDiagrama(indice=0, bbox=(46, 30, 155, 130)),
            _paragrafo(_linha("1.Nc3 Nf6 2.d3", (46, 140, 220, 152)), legenda_de=0),
        )
        solucoes = _folha(_paragrafo(_linha("70. 1.Qxf7# ", (10, 10, 300, 22))), pagina=94)
        folhas = [
            taticas.Folha(pagina=0, texto=exercicios, diagramas=(taticas.DiagramaLido(0, PASTOR),)),
            taticas.Folha(pagina=94, texto=solucoes),
        ]
        extracao = taticas.extrair(folhas, livro="livro.pdf")
        self.assertEqual(("Qxf7#",), extracao.exercicios[0].lances)

    def test_sem_lista_a_linha_ao_lado_serve_com_dois_plies(self) -> None:
        exercicios = _folha(
            BlocoDeDiagrama(indice=0, bbox=(46, 30, 155, 130)),
            _paragrafo(_linha("1.Nc3 Nf6 2.d3", (46, 140, 220, 152)), legenda_de=0),
        )
        folhas = [
            taticas.Folha(pagina=0, texto=exercicios, diagramas=(taticas.DiagramaLido(0, PASTOR),))
        ]
        extracao = taticas.extrair(folhas, livro="livro.pdf")
        self.assertEqual(taticas.AO_LADO, extracao.exercicios[0].origem)
        self.assertEqual(("Nc3", "Nf6", "d3"), extracao.exercicios[0].lances)

    def test_um_lance_solto_ao_lado_nao_basta(self) -> None:
        """Sem número que ate o gabarito ao diagrama, o vínculo é a vizinhança -- e ela precisa de
        mais de um meio-lance para não ser acaso (`PLIES_MINIMOS_AO_LADO`)."""
        exercicios = _folha(
            BlocoDeDiagrama(indice=0, bbox=(46, 30, 155, 130)),
            _paragrafo(_linha("1. Nc3", (46, 140, 220, 152)), legenda_de=0),
        )
        folhas = [
            taticas.Folha(pagina=0, texto=exercicios, diagramas=(taticas.DiagramaLido(0, PASTOR),))
        ]
        self.assertEqual([], list(taticas.extrair(folhas, livro="l.pdf").exercicios))

    def test_extracao_vazia_diz_isso_em_vez_de_dividir_por_zero(self) -> None:
        self.assertIn("Nenhum diagrama", taticas.Extracao().resumo())

    def test_o_resumo_diz_o_que_o_motor_recusou(self) -> None:
        """**Sem a segunda metade o relatório mente.** No `Manual of Chess Combinations` a extração
        produziu 10 exercícios e o motor recusou os 10: "10 com solução" e "10 recusadas" são a
        mesma frase, e sem a segunda alguém lê 2,4% de aproveitamento onde há 2,4% de ruído."""
        extracao = taticas.extrair(self._livro(), livro="l.pdf")
        self.assertNotIn("motor", extracao.resumo())
        conferidos = tuple(
            taticas.confirmar(e, lambda _b: (0, None)) for e in extracao.exercicios
        )
        com_motor = taticas.Extracao(conferidos, extracao.recusas, diagramas=extracao.diagramas)
        self.assertIn(f"O motor confirmou {len(conferidos)} de {len(conferidos)}", com_motor.resumo())


class MotorTests(unittest.TestCase):
    """A confirmação, com o motor injetado como função -- nada de processo aqui."""

    def _exercicio(self, lance: str = "Qxf7#") -> taticas.Exercicio:
        return taticas.Exercicio(
            fen=taticas.compose_fen(PASTOR, chess.WHITE),
            lances=(lance,),
            procedencia=taticas.Procedencia(livro="l.pdf", pagina=1, diagrama=0, numero=7),
        )

    def test_o_lance_que_o_motor_aprova_fica_confirmado(self) -> None:
        conferido = taticas.confirmar(self._exercicio(), lambda _b: (30, None))
        self.assertEqual(taticas.CONFIRMADA, conferido.motor)
        self.assertEqual(0, conferido.perda_do_motor)

    def test_o_lance_que_perde_muito_fica_marcado_e_nao_apagado(self) -> None:
        """**A discordância não troca o gabarito.** Um livro de 1934 propõe combinações que o
        Stockfish refuta, e trocar a solução pela linha do motor seria treinar o motor."""
        avaliacoes = iter([(400, None), (-200, None)])
        conferido = taticas.confirmar(self._exercicio(), lambda _b: next(avaliacoes))
        self.assertEqual(taticas.DISCORDOU, conferido.motor)
        self.assertEqual(600, conferido.perda_do_motor)
        self.assertEqual(("Qxf7#",), conferido.lances, "o gabarito continua o do livro")

    def test_o_motor_que_falha_deixa_o_exercicio_como_estava(self) -> None:
        def _quebra(_board: object) -> tuple[int | None, int | None]:
            raise RuntimeError("o motor morreu")

        conferido = taticas.confirmar(self._exercicio(), _quebra)
        self.assertEqual(taticas.NAO_PERGUNTADO, conferido.motor)
        self.assertEqual(-1, conferido.perda_do_motor)

    def test_exercicio_sem_lance_nao_pergunta_nada(self) -> None:
        vazio = taticas.Exercicio(fen=chess.STARTING_FEN, lances=(), procedencia=taticas.Procedencia())
        self.assertIs(vazio, taticas.confirmar(vazio, lambda _b: (0, None)))


class ArquivoTests(unittest.TestCase):
    """Um arquivo por livro, com a chave de `estudo_arquivo` -- e a ida e volta sem perda."""

    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)

    def _exercicio(self, diagrama: int = 0) -> taticas.Exercicio:
        return taticas.Exercicio(
            fen=taticas.compose_fen(PASTOR, chess.WHITE),
            lances=("Qxf7#",),
            procedencia=taticas.Procedencia(
                livro="C:/PDF/Reinfeld.pdf", pagina=63, diagrama=diagrama, numero=214
            ),
            desfecho=taticas.MATE,
        )

    def test_a_ida_e_volta_nao_perde_campo(self) -> None:
        taticas_arquivo.gravar("C:/PDF/Reinfeld.pdf", [self._exercicio()], pasta=self.pasta)
        lidos = taticas_arquivo.carregar("C:/PDF/Reinfeld.pdf", pasta=self.pasta)
        self.assertEqual([self._exercicio()], lidos)

    def test_a_chave_e_a_mesma_da_sala_de_estudo(self) -> None:
        """Um livro tem uma sala e uma coleção, e as duas respondem ao mesmo nome."""
        from chess_diagram_ocr import estudo_arquivo

        alvo = taticas_arquivo.caminho_de("C:/PDF/Reinfeld.pdf", pasta=self.pasta)
        self.assertEqual(estudo_arquivo.chave_de("C:/PDF/Reinfeld.pdf"), alvo.stem)

    def test_colecao_vazia_apaga_o_arquivo(self) -> None:
        alvo = taticas_arquivo.gravar("l.pdf", [self._exercicio()], pasta=self.pasta)
        assert alvo is not None
        self.assertIsNone(taticas_arquivo.gravar("l.pdf", [], pasta=self.pasta))
        self.assertFalse(alvo.exists())

    def test_livro_sem_nome_nao_grava(self) -> None:
        self.assertIsNone(taticas_arquivo.gravar("", [self._exercicio()], pasta=self.pasta))

    def test_arquivo_ausente_e_lista_vazia(self) -> None:
        self.assertEqual([], taticas_arquivo.carregar("nunca-existiu.pdf", pasta=self.pasta))

    def test_um_exercicio_corrompido_nao_derruba_os_outros(self) -> None:
        taticas_arquivo.gravar("l.pdf", [self._exercicio(0), self._exercicio(1)], pasta=self.pasta)
        alvo = taticas_arquivo.caminho_de("l.pdf", pasta=self.pasta)
        dados = json.loads(alvo.read_text(encoding="utf-8"))
        dados["exercicios"][0] = {"fen": "", "lances": []}
        alvo.write_text(json.dumps(dados), encoding="utf-8")
        self.assertEqual(1, len(taticas_arquivo.carregar("l.pdf", pasta=self.pasta)))

    def test_esquema_do_futuro_nao_e_lido_pela_metade(self) -> None:
        alvo = taticas_arquivo.caminho_de("l.pdf", pasta=self.pasta)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(json.dumps({"esquema": 99, "exercicios": []}), encoding="utf-8")
        self.assertEqual([], taticas_arquivo.carregar("l.pdf", pasta=self.pasta))

    def test_carregar_tudo_junta_os_livros(self) -> None:
        taticas_arquivo.gravar("um.pdf", [self._exercicio(0)], pasta=self.pasta)
        taticas_arquivo.gravar("dois.pdf", [self._exercicio(1)], pasta=self.pasta)
        self.assertEqual(2, len(taticas_arquivo.carregar_tudo(pasta=self.pasta)))
        self.assertEqual(2, len(taticas_arquivo.livros(pasta=self.pasta)))

    def test_pasta_que_nao_existe_devolve_vazio(self) -> None:
        self.assertEqual([], taticas_arquivo.livros(pasta=self.pasta / "nao-existe"))
        self.assertEqual([], taticas_arquivo.carregar_tudo(pasta=self.pasta / "nao-existe"))

    def test_a_gravacao_e_atomica(self) -> None:
        """`atomic_io`, como todo arquivo de trabalho: a extração de um livro leva minutos."""
        fonte = Path(taticas_arquivo.__file__).read_text(encoding="utf-8")
        self.assertIn("atomic_write_json", fonte)
        self.assertNotIn("write_text(", fonte)


class ProcedenciaTests(unittest.TestCase):
    def test_a_chave_nao_usa_o_numero_impresso(self) -> None:
        """Dois capítulos podem recomeçar a numeração em 1, e a agenda erraria de exercício."""
        um = taticas.Procedencia(livro="l.pdf", pagina=3, diagrama=0, numero=1)
        outro = taticas.Procedencia(livro="l.pdf", pagina=90, diagrama=0, numero=1)
        self.assertNotEqual(um.chave(), outro.chave())

    def test_sem_folha_impressa_a_frase_diz_folha(self) -> None:
        procedencia = taticas.Procedencia(livro="C:/PDF/Um livro.pdf", pagina=9, numero=3)
        self.assertEqual("Um livro, folha 10, exercício 3", procedencia.frase())

    def test_sem_livro_a_frase_nao_mente(self) -> None:
        self.assertIn("não identificado", taticas.Procedencia().frase())


class AdaptadorDePdfTests(unittest.TestCase):
    """`de_pdf` é a costura entre a varredura e a leitura, e as duas contam diferente."""

    def test_o_indice_da_varredura_vira_o_indice_da_leitura(self) -> None:
        """**O `-1` é o defeito que deslocava o livro inteiro** (S-539, r2, 2026-09-05).

        `DiagramPosition.diagram_index` conta de 1 (`pdf_to_pgn.py`, `enumerate(..., start=1)`) e
        `PaginaLida.diagramas` conta de 0. Sem a conversão, cada diagrama recebia a **caixa** do
        seguinte -- e portanto o número impresso do seguinte --, e o último de cada folha ficava
        sem caixa nenhuma. Medido no `Big Book of Combinations`: 963 números, **nenhum** deles o da
        folha impressa. O teste afirma o efeito: o primeiro diagrama sai com o primeiro número.
        """
        from contextlib import contextmanager
        from unittest import mock

        pagina = _folha(
            _paragrafo(_linha("41", (60, 10, 72, 22))),
            BlocoDeDiagrama(indice=0, bbox=(46, 30, 155, 140)),
            _paragrafo(_linha("42", (60, 170, 72, 182))),
            BlocoDeDiagrama(indice=1, bbox=(46, 190, 155, 300)),
        )

        class _Posicao:
            def __init__(self, indice: int, fen: str) -> None:
                self.page_index = 0
                self.diagram_index = indice  # 1-based, como o pipeline o escreve
                self.fen = fen
                self.side_to_move = None

        @contextmanager
        def _abrir(_caminho: object):  # noqa: ANN202 - dublê de `pdf_io.opened`
            yield mock.Mock(page_count=1)

        with (
            mock.patch(
                "chess_diagram_ocr.pdf_to_pgn.scan_pdf_positions",
                return_value=[_Posicao(1, PASTOR), _Posicao(2, PRETAS)],
            ),
            mock.patch("chess_diagram_ocr.pdf_io.opened", _abrir),
            mock.patch("chess_diagram_ocr.text.leitor.ler_pagina", return_value=pagina),
        ):
            extracao = taticas.de_pdf(Path("livro.pdf"))

        # Nenhum dos dois vira exercício -- não há lista de soluções --, mas a procedência diz de
        # que diagrama cada recusa é, e é isso que o número impresso segue.
        por_diagrama = {
            recusa.procedencia.diagrama: recusa.procedencia.numero for recusa in extracao.recusas
        }
        self.assertEqual({0: 41, 1: 42}, por_diagrama)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
