"""A paginação de livro sem janela: onde a página quebra e o que não se separa (S-545).

As alturas aqui são números redondos, e é o ponto: a decisão de paginar não sabe o que é uma
fonte -- ela recebe a linha já medida por `qt/impressao_do_estudo.py`, que é quem tem o
dispositivo na mão. Um teste que precisasse abrir janela para afirmar a quebra estaria medindo o
`QTextLayout`, e não a regra.
"""

from __future__ import annotations

import unittest

import chess
import chess.pgn

from chess_diagram_ocr.estudo import Ancora, Estudo, PosicaoDeEstudo
from chess_diagram_ocr.estudo_paragrafos import DIAGRAMA, TITULO
from chess_diagram_ocr.ui.impressao_do_estudo import (
    LARGURA_DO_DIAGRAMA,
    MARGEM_MM,
    Pagina,
    blocos_do_estudo,
    cabecalho,
    frase_do_pdf,
    paginar,
    rodape,
)

INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"


def _uniformes(blocos: int, linhas: int, altura: float = 10.0) -> list[list[float]]:
    return [[altura] * linhas for _ in range(blocos)]


def _onde(paginas: tuple[Pagina, ...], bloco: int) -> list[int]:
    """Em que páginas (contadas de 1) aquele bloco aparece."""
    return [p.numero for p in paginas for pedaco in p.pedacos if pedaco.bloco == bloco]


class PaginacaoTests(unittest.TestCase):
    def test_o_que_cabe_numa_pagina_sai_numa_pagina(self) -> None:
        paginas = paginar(_uniformes(3, 2), altura_util=100.0)
        self.assertEqual(1, len(paginas))
        self.assertEqual(3, len(paginas[0].pedacos))
        self.assertEqual(1, paginas[0].numero)

    def test_a_pagina_enche_e_a_seguinte_comeca_no_topo(self) -> None:
        paginas = paginar(_uniformes(6, 2), altura_util=45.0)
        self.assertEqual(3, len(paginas))
        for pagina in paginas:
            self.assertEqual(0.0, pagina.pedacos[0].topo, "a página seguinte começa colada no alto")
            self.assertLessEqual(sum(p.altura for p in pagina.pedacos), 45.0)
        self.assertEqual([1, 2, 3], [p.numero for p in paginas])

    def test_um_paragrafo_alto_se_parte_em_linhas(self) -> None:
        """Um estudo de 300 lances sem comentário nenhum é **um** parágrafo, mais alto que a
        folha: uma regra de "parágrafo não se parte" o deixaria sem lugar onde caber."""
        paginas = paginar(_uniformes(1, 30), altura_util=100.0)
        self.assertEqual(3, len(paginas))
        cortes = [(p.pedacos[0].de, p.pedacos[0].ate) for p in paginas]
        self.assertEqual([(0, 10), (10, 20), (20, 30)], cortes, "as linhas saem sem buraco e sem repetir")

    def test_nenhuma_linha_se_perde_nem_se_repete(self) -> None:
        alturas = [[7.0] * 5, [11.0] * 3, [9.0] * 8]
        paginas = paginar(alturas, altura_util=40.0, espaco=3.0)
        for bloco, linhas in enumerate(alturas):
            vistas = [
                indice
                for pagina in paginas
                for pedaco in pagina.pedacos
                if pedaco.bloco == bloco
                for indice in range(pedaco.de, pedaco.ate)
            ]
            with self.subTest(bloco=bloco):
                self.assertEqual(list(range(len(linhas))), vistas)

    def test_o_diagrama_nao_se_separa_do_lance_que_o_pede(self) -> None:
        """**O item.** O bloco anterior ao diagrama é `com_o_proximo`: sobrando espaço só para o
        lance, os dois descem juntos em vez de o diagrama abrir a página seguinte sozinho."""
        alturas = [[10.0] * 4, [10.0], [50.0]]
        paginas = paginar(alturas, altura_util=60.0, com_o_proximo=[False, True, False])
        self.assertEqual([1], _onde(paginas, 0))
        self.assertEqual(_onde(paginas, 1), _onde(paginas, 2), "o lance e o diagrama na mesma página")
        self.assertEqual([2], _onde(paginas, 1))

    def test_um_par_colado_mais_alto_que_a_pagina_nao_gira_para_sempre(self) -> None:
        """A segunda metade da regra: se o grupo não cabe nem numa folha limpa, ele se parte --
        senão a paginação viraria página até o fim do mundo."""
        paginas = paginar([[10.0] * 6, [10.0] * 6], altura_util=40.0, com_o_proximo=[True, False])
        self.assertGreaterEqual(len(paginas), 3)
        self.assertEqual(12, sum(pedaco.ate - pedaco.de for p in paginas for pedaco in p.pedacos))

    def test_nem_uma_linha_solta_fica_no_pe_nem_atravessa(self) -> None:
        """Duas linhas é o mínimo dos dois lados. Aqui cabe **uma** linha do segundo bloco no
        que sobrou, e ela desce inteira com o resto do parágrafo."""
        paginas = paginar([[10.0] * 3, [10.0] * 4], altura_util=40.0)
        self.assertEqual([1], _onde(paginas, 0))
        self.assertEqual([2], _onde(paginas, 1))

    def test_o_espaco_entre_blocos_nao_e_cobrado_no_alto_da_pagina(self) -> None:
        """No alto quem responde pelo ar é a margem; um vão a mais ali desalinharia a primeira
        linha de cada página com a das outras."""
        paginas = paginar(_uniformes(4, 1, altura=10.0), altura_util=25.0, espaco=5.0)
        for pagina in paginas:
            self.assertEqual(0.0, pagina.pedacos[0].topo)
        self.assertEqual(15.0, paginas[0].pedacos[1].topo, "o segundo bloco leva o vão")

    def test_um_estudo_sem_bloco_nenhum_ainda_sai_numa_folha(self) -> None:
        """Uma folha em branco com cabeçalho e número é melhor que um `QPrinter` sem página."""
        paginas = paginar([], altura_util=100.0)
        self.assertEqual(1, len(paginas))
        self.assertEqual((), paginas[0].pedacos)

    def test_bloco_sem_linha_nenhuma_nao_vira_pedaco(self) -> None:
        paginas = paginar([[], [10.0]], altura_util=100.0)
        self.assertEqual([1], [pedaco.bloco for pedaco in paginas[0].pedacos])


def _estudo(*, lances: int = 0, pede: bool = False, ancora: Ancora = Ancora()) -> Estudo:
    estudo = Estudo.de_posicao(PosicaoDeEstudo(placement=INICIAL, vez="w", ancora=ancora))
    tabuleiro = chess.Board()
    for numero in range(lances):
        lance = list(tabuleiro.legal_moves)[numero % 4]
        estudo.no = estudo.no.add_main_variation(lance)
        tabuleiro.push(lance)
    if pede and lances:
        estudo.no.comment = "O autor pede a figura aqui. [%D]"
    return estudo


class BlocosTests(unittest.TestCase):
    def test_a_lista_e_a_de_estudo_paragrafos_mais_a_coesao(self) -> None:
        """A folha impressa e o capítulo do EPUB mostram os mesmos parágrafos do mesmo estudo."""
        from chess_diagram_ocr.estudo_paragrafos import paragrafos

        estudo = _estudo(lances=4, pede=True)
        blocos = blocos_do_estudo(estudo)
        self.assertEqual([p.tipo for p in paragrafos(estudo)], [b.tipo for b in blocos])
        self.assertEqual([p.texto for p in paragrafos(estudo)], [b.texto for b in blocos])

    def test_o_bloco_antes_do_diagrama_e_o_titulo_andam_com_o_proximo(self) -> None:
        blocos = blocos_do_estudo(_estudo(lances=4, pede=True))
        for indice, bloco in enumerate(blocos):
            seguinte = blocos[indice + 1] if indice + 1 < len(blocos) else None
            esperado = seguinte is not None and (seguinte.tipo == DIAGRAMA or bloco.tipo == TITULO)
            with self.subTest(indice=indice, tipo=bloco.tipo):
                self.assertEqual(esperado, bloco.com_o_proximo)

    def test_o_ultimo_bloco_nunca_pede_um_proximo_que_nao_existe(self) -> None:
        self.assertFalse(blocos_do_estudo(_estudo(lances=2))[-1].com_o_proximo)

    def test_o_diagrama_da_raiz_traz_a_fen_da_posicao(self) -> None:
        diagramas = [b for b in blocos_do_estudo(_estudo()) if b.tipo == DIAGRAMA]
        self.assertEqual(1, len(diagramas))
        self.assertTrue(diagramas[0].fen.startswith(INICIAL))


class MargensTests(unittest.TestCase):
    def test_o_cabecalho_e_vazio_na_primeira_e_traz_o_titulo_nas_outras(self) -> None:
        """O título está no corpo da página de abertura: repeti-lo na linha de topo é dizer a
        mesma coisa duas vezes no mesmo campo de visão."""
        self.assertEqual("", cabecalho("Secrets · p. 143", 1))
        self.assertEqual("Secrets · p. 143", cabecalho("Secrets · p. 143", 2))

    def test_o_titulo_do_cabecalho_e_uma_linha_so(self) -> None:
        self.assertEqual("A B", cabecalho("A\n  B ", 3))

    def test_o_rodape_diz_o_numero_e_quantas_ha(self) -> None:
        """Uma folha solta de um lote impresso não diz de onde saiu nem quantas faltam."""
        self.assertEqual("3 de 12", rodape(3, 12))
        self.assertEqual("1 de 1", rodape(0, 0), "nem zero de zero, que não é página nenhuma")

    def test_as_medidas_da_folha_sao_proporcao_e_milimetro(self) -> None:
        """A margem é milímetro porque a folha é física; o diagrama é fração porque a mesma folha
        vale em A4 e em Carta, e vale na prévia, que desenha noutra escala."""
        self.assertGreater(MARGEM_MM, 0.0)
        self.assertLess(MARGEM_MM, 30.0)
        self.assertLess(0.3, LARGURA_DO_DIAGRAMA)
        self.assertLess(LARGURA_DO_DIAGRAMA, 0.8)

    def test_a_frase_do_pdf_traz_o_caminho_inteiro_e_o_tamanho(self) -> None:
        frase = frase_do_pdf("C:/PDF/estudo.pdf", 12, 250 * 1024)
        self.assertIn("C:/PDF/estudo.pdf", frase)
        self.assertIn("12 página(s)", frase)
        self.assertIn("250.0 KB", frase)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
