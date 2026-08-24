"""O modelo de página da S-211: o que todo bloco carrega, e a ida-e-volta para JSON.

Os três testes que a spec nomeia estão aqui. O quarto que ela nomeia --
`test_nenhum_consumidor_recompoe_a_pagina` -- **não está**, e a razão é a honestidade da conta: o
PGN, o dataset e a fila continuam partindo de `service.RecognizedDiagram`, então um teste com esse
nome passaria hoje por vacuidade e viraria a prova de algo que não aconteceu. Ver a seção "O que
entrou em 2026-08-24" em `docs/SPEC_TEXTO.md`.
"""

from __future__ import annotations

import json
import unittest

from chess_diagram_ocr.text.pagina import (
    PROCEDENCIAS,
    BlocoDeDiagrama,
    BlocoDeTabela,
    BlocoDeTarja,
    BlocoDeTexto,
    Coluna,
    LinhaLida,
    PaginaInvalida,
    PaginaLida,
    bloco_de_json,
    de_diagramas,
)


def _linha(texto: str = "uma linha", **campos: object) -> LinhaLida:
    base: dict[str, object] = {"bbox": (1.0, 2.0, 3.0, 4.0), "confianca": 0.9, "procedencia": "glifo"}
    base.update(campos)
    return LinhaLida(texto=texto, **base)  # type: ignore[arg-type]


def _pagina_cheia() -> PaginaLida:
    """Uma página com **um bloco de cada tipo**, que é o que faz a ida-e-volta valer alguma coisa."""
    return PaginaLida(
        documento="Livro.pdf",
        pagina=41,
        largura=595.0,
        altura=842.0,
        unidade="pt",
        numero_impresso=38,
        cabecalho=LinhaLida("Defensive Methods", (10.0, 5.0, 200.0, 18.0), 1.0, "camada"),
        rodape=LinhaLida("61", (300.0, 820.0, 310.0, 832.0), 1.0, "camada"),
        colunas=(
            Coluna(
                indice=0,
                bbox=(10.0, 20.0, 290.0, 800.0),
                blocos=(
                    BlocoDeTexto.de_linhas([_linha("primeira"), _linha("segunda")], recuado=True),
                    BlocoDeDiagrama(indice=0, bbox=(20.0, 100.0, 180.0, 260.0), confianca=0.87,
                                    placement="8/8/8/8/8/8/8/8"),
                    BlocoDeTarja(linhas=(_linha("EM CAIXA ALTA"),), bbox=(10.0, 300.0, 280.0, 320.0),
                                 confianca=0.5, procedencia="rapidocr"),
                ),
            ),
            Coluna(
                indice=1,
                bbox=(305.0, 20.0, 585.0, 800.0),
                blocos=(
                    BlocoDeTabela(
                        celulas=(("nome", "pts"), ("Alekhine", "8")),
                        bbox=(305.0, 40.0, 580.0, 120.0),
                        confianca=0.66,
                        procedencia="humano",
                    ),
                ),
            ),
        ),
    )


class ContratoDoBlocoTests(unittest.TestCase):
    """*"todo elemento tem bbox, confiança e procedência — sem exceção, travado por teste."*"""

    def test_todo_elemento_traz_bbox_confianca_e_procedencia(self) -> None:
        pagina = _pagina_cheia()
        self.assertEqual(len(pagina.blocos), 4, "a página de prova perdeu um tipo de bloco")
        for bloco in pagina.blocos:
            with self.subTest(tipo=bloco.tipo):
                self.assertEqual(len(bloco.bbox), 4)
                self.assertIsInstance(bloco.confianca, float)
                self.assertIn(bloco.procedencia, PROCEDENCIAS)

    def test_os_quatro_tipos_de_bloco_estao_cobertos(self) -> None:
        """Se um tipo novo nascer sem entrar aqui, o teste acima deixaria de cobri-lo em silêncio."""
        self.assertEqual(
            {b.tipo for b in _pagina_cheia().blocos},
            {"texto", "diagrama", "tabela", "tarja"},
        )

    def test_o_bloco_de_texto_herda_a_pior_procedencia_das_linhas(self) -> None:
        """Um parágrafo com uma linha de glifo **não** é um parágrafo da camada de texto."""
        bloco = BlocoDeTexto.de_linhas(
            [_linha("da camada", procedencia="camada", confianca=1.0), _linha("do glifo", confianca=0.4)]
        )
        self.assertEqual(bloco.procedencia, "glifo")
        self.assertAlmostEqual(bloco.confianca, 0.4, msg="a confiança do bloco é a MÍNIMA das linhas")

    def test_o_diagrama_vira_uma_marca_e_nunca_a_fen(self) -> None:
        """A marca é o que permite mover o diagrama de lugar no texto e ele sobreviver."""
        bloco = BlocoDeDiagrama(indice=4, placement="8/8/8/8/8/8/8/8")
        self.assertEqual(bloco.texto, "[Diagrama 5]")
        self.assertNotIn("8/8", bloco.texto)


class SerializacaoTests(unittest.TestCase):
    def test_a_pagina_serializa_e_volta_sem_perda(self) -> None:
        pagina = _pagina_cheia()
        volta = PaginaLida.de_json(json.loads(json.dumps(pagina.para_json())))
        self.assertEqual(volta, pagina)

    def test_a_ida_e_volta_e_estavel_na_segunda_passada(self) -> None:
        """Um campo perdido na primeira volta só apareceria comparando duas serializações."""
        uma = _pagina_cheia().para_json()
        outra = PaginaLida.de_json(json.loads(json.dumps(uma))).para_json()
        self.assertEqual(uma, outra)

    def test_um_tipo_de_bloco_desconhecido_recusa_em_vez_de_virar_texto(self) -> None:
        """Uma tabela lida por versão nova e aberta por versão velha não pode virar parágrafo."""
        with self.assertRaises(PaginaInvalida) as erro:
            bloco_de_json({"tipo": "grafico", "bbox": [0, 0, 1, 1], "procedencia": "glifo"})
        self.assertIn("grafico", str(erro.exception))

    def test_uma_procedencia_de_fora_da_lista_recusa(self) -> None:
        with self.assertRaises(PaginaInvalida):
            bloco_de_json({"tipo": "texto", "bbox": [0, 0, 1, 1], "procedencia": "chute"})

    def test_um_esquema_do_futuro_recusa_em_vez_de_ler_pela_metade(self) -> None:
        dados = _pagina_cheia().para_json()
        dados["esquema"] = 99
        with self.assertRaises(PaginaInvalida) as erro:
            PaginaLida.de_json(dados)
        self.assertIn("99", str(erro.exception))

    def test_uma_unidade_desconhecida_recusa(self) -> None:
        """Perder a unidade é o defeito silencioso que `UNIDADES` existe para não ter."""
        dados = _pagina_cheia().para_json()
        dados["unidade"] = "polegadas"
        with self.assertRaises(PaginaInvalida):
            PaginaLida.de_json(dados)


class EquivalenciaComOHojeTests(unittest.TestCase):
    """*"uma página só de diagramas produz uma `PaginaLida` equivalente ao que a UI recebe hoje"*."""

    def test_a_pagina_so_de_diagramas_equivale_ao_de_hoje(self) -> None:
        caixas = [(10.0, 20.0, 100.0, 110.0), (200.0, 20.0, 290.0, 110.0), (10.0, 300.0, 100.0, 390.0)]
        pagina = de_diagramas(caixas, pagina=7, largura=595.0, altura=842.0, documento="Livro.pdf")
        self.assertEqual(len(pagina.diagramas), len(caixas))
        self.assertEqual([d.indice for d in pagina.diagramas], [0, 1, 2], "a ordem do detector mudou")
        self.assertEqual([tuple(d.bbox) for d in pagina.diagramas], [tuple(c) for c in caixas])

    def test_a_pagina_so_de_diagramas_nao_inventa_texto(self) -> None:
        pagina = de_diagramas([(10.0, 20.0, 100.0, 110.0)])
        self.assertEqual(pagina.texto(com_marcas=False), "", "diagrama não é prosa")
        self.assertEqual(pagina.texto(), "[Diagrama 1]")

    def test_uma_pagina_vazia_nao_estoura_em_nenhuma_leitura(self) -> None:
        """A folha em branco existe no acervo, e ela não pode ser um caso de erro."""
        vazia = PaginaLida()
        self.assertEqual(vazia.texto(), "")
        self.assertEqual(vazia.blocos, ())
        self.assertEqual(vazia.confianca_minima, 1.0, "não há nada de que duvidar")
        self.assertEqual(vazia.procedencias(), {})
        self.assertEqual(PaginaLida.de_json(json.loads(json.dumps(vazia.para_json()))), vazia)


class OrdemDeLeituraTests(unittest.TestCase):
    def test_o_texto_segue_coluna_a_coluna_e_nao_a_geometria(self) -> None:
        """A coluna da esquerda inteira antes da direita -- e não linha a linha atravessando."""
        esquerda = Coluna(indice=0, blocos=(BlocoDeTexto.de_linhas([_linha("esquerda A")]),
                                            BlocoDeTexto.de_linhas([_linha("esquerda B")])))
        direita = Coluna(indice=1, blocos=(BlocoDeTexto.de_linhas([_linha("direita A")]),))
        pagina = PaginaLida(colunas=(esquerda, direita))
        self.assertEqual(
            pagina.texto().split("\n\n"),
            ["esquerda A", "esquerda B", "direita A"],
        )

    def test_o_diagrama_sai_entre_os_paragrafos_e_nao_no_fim(self) -> None:
        """É a S-193: o diagrama entre o parágrafo 3 e o 4 tem de sair entre o 3 e o 4."""
        coluna = Coluna(
            indice=0,
            blocos=(
                BlocoDeTexto.de_linhas([_linha("antes")]),
                BlocoDeDiagrama(indice=0),
                BlocoDeTexto.de_linhas([_linha("depois")]),
            ),
        )
        self.assertEqual(PaginaLida(colunas=(coluna,)).texto().split("\n\n"),
                         ["antes", "[Diagrama 1]", "depois"])

    def test_sem_marcas_tira_o_diagrama_e_mantem_a_prosa(self) -> None:
        coluna = Coluna(indice=0, blocos=(BlocoDeTexto.de_linhas([_linha("antes")]),
                                          BlocoDeDiagrama(indice=0),
                                          BlocoDeTexto.de_linhas([_linha("depois")])))
        self.assertEqual(PaginaLida(colunas=(coluna,)).texto(com_marcas=False).split("\n\n"),
                         ["antes", "depois"])

    def test_a_confianca_da_pagina_e_a_do_pior_bloco(self) -> None:
        pagina = _pagina_cheia()
        self.assertAlmostEqual(pagina.confianca_minima, min(b.confianca for b in pagina.blocos))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
