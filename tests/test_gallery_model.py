"""Navegação, anotação e sincronia da galeria, sem janela (S-67)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from chess_diagram_ocr.gallery import DiagramAnnotation, GalleryAnnotations, load_annotations
from chess_diagram_ocr.gallery_scan import GalleryEntry, GalleryIndex
from chess_diagram_ocr.games_db import DiagramMatch
from chess_diagram_ocr.ui.gallery_model import HEADER_FIELDS, GalleryModel

PLACEMENT = "4k3/8/8/8/8/8/8/4K3"


def _indice(*chaves: tuple[int, int]) -> GalleryIndex:
    return GalleryIndex(
        entries=[GalleryEntry(page_index=p, diagram_index=d, placement=PLACEMENT) for p, d in chaves]
    )


def _modelo(*chaves: tuple[int, int]) -> GalleryModel:
    return GalleryModel(index=_indice(*chaves), annotations=GalleryAnnotations())


class NavegacaoTests(unittest.TestCase):
    def test_galeria_vazia_nao_tem_atual_e_nao_levanta(self) -> None:
        modelo = GalleryModel()
        self.assertTrue(modelo.is_empty)
        self.assertIsNone(modelo.current)
        self.assertFalse(modelo.step(1))
        self.assertEqual(modelo.describe_position(), "nenhum diagrama varrido")

    def test_proximo_e_anterior(self) -> None:
        modelo = _modelo((0, 0), (0, 1), (3, 0))
        self.assertTrue(modelo.step(1))
        self.assertEqual(modelo.current.key, (0, 1))
        self.assertTrue(modelo.step(-1))
        self.assertEqual(modelo.current.key, (0, 0))

    def test_nao_circula_no_fim(self) -> None:
        """Circular faria o último diagrama do livro parecer o primeiro."""
        modelo = _modelo((0, 0), (0, 1))
        modelo.go_to(1)
        self.assertFalse(modelo.step(1))
        self.assertEqual(modelo.current.key, (0, 1))

    def test_nao_circula_no_comeco(self) -> None:
        modelo = _modelo((0, 0), (0, 1))
        self.assertFalse(modelo.step(-1))
        self.assertEqual(modelo.current.key, (0, 0))

    def test_posicao_fora_da_lista_e_corrigida(self) -> None:
        modelo = _modelo((0, 0), (0, 1))
        modelo.position = 99
        self.assertEqual(modelo.current.key, (0, 1))

    def test_ir_para_a_mesma_posicao_nao_conta_como_mudanca(self) -> None:
        modelo = _modelo((0, 0), (0, 1))
        self.assertFalse(modelo.go_to(0))


class SincroniaTests(unittest.TestCase):
    def test_segue_a_pagina_do_pdf(self) -> None:
        modelo = _modelo((0, 0), (4, 0), (4, 1))
        self.assertTrue(modelo.sync_to_page(4))
        self.assertEqual(modelo.current.key, (4, 0))

    def test_pagina_sem_diagrama_nao_move(self) -> None:
        """Rolar até uma página de texto não pode tirar da tela o que se estava anotando."""
        modelo = _modelo((0, 0), (4, 0))
        modelo.go_to(1)
        self.assertFalse(modelo.sync_to_page(9))
        self.assertEqual(modelo.current.key, (4, 0))

    def test_a_galeria_diz_a_pagina_para_o_pdf_seguir(self) -> None:
        modelo = _modelo((0, 0), (7, 2))
        modelo.go_to(1)
        self.assertEqual(modelo.page_index, 7)

    def test_pagina_vazia_nao_tem_pagina(self) -> None:
        self.assertIsNone(GalleryModel().page_index)


class AnotacaoTests(unittest.TestCase):
    def test_editar_grava_no_diagrama_certo(self) -> None:
        modelo = _modelo((0, 0), (2, 1))
        modelo.go_to(1)
        modelo.edit(move_number=24)
        self.assertEqual(modelo.annotations.get(2, 1).move_number, 24)
        self.assertIsNone(modelo.annotations.get(0, 0).move_number)

    def test_header_em_branco_apaga_a_declaracao(self) -> None:
        modelo = _modelo((0, 0))
        modelo.set_header("White", "Tal")
        self.assertEqual(modelo.current_annotation.headers, {"White": "Tal"})
        modelo.set_header("White", "   ")
        self.assertEqual(modelo.current_annotation.headers, {})

    def test_header_reservado_e_recusado(self) -> None:
        modelo = _modelo((0, 0))
        modelo.set_header("FEN", "lixo")
        self.assertEqual(modelo.current_annotation.headers, {})

    def test_anotacao_esvaziada_some_do_conjunto(self) -> None:
        """Visitar não é anotar: o JSON não deve crescer por diagrama visitado."""
        modelo = _modelo((0, 0))
        modelo.set_header("White", "Tal")
        self.assertEqual(modelo.annotated_count(), 1)
        modelo.set_header("White", "")
        self.assertEqual(modelo.annotated_count(), 0)

    def test_editar_sem_diagrama_devolve_none(self) -> None:
        self.assertIsNone(GalleryModel().edit(move_number=3))
        self.assertIsNone(GalleryModel().set_header("White", "Tal"))


class AplicarATodosTests(unittest.TestCase):
    def test_copia_os_declarados_para_os_outros(self) -> None:
        modelo = _modelo((0, 0), (0, 1), (1, 0))
        modelo.set_header("Event", "Kemeri 1937")
        self.assertEqual(modelo.apply_headers_to_all(), 2)
        self.assertEqual(modelo.annotations.get(0, 1).headers, {"Event": "Kemeri 1937"})
        self.assertEqual(modelo.annotations.get(1, 0).headers, {"Event": "Kemeri 1937"})

    def test_campo_em_branco_nao_apaga_o_dos_outros(self) -> None:
        """Aplicar a todos preenche; virar apagador em massa seria perder trabalho."""
        modelo = _modelo((0, 0), (0, 1))
        modelo.go_to(1)
        modelo.set_header("White", "Tal")
        modelo.go_to(0)
        modelo.set_header("Event", "Riga")
        modelo.apply_headers_to_all()
        self.assertEqual(modelo.annotations.get(0, 1).headers, {"White": "Tal", "Event": "Riga"})

    def test_sem_nada_declarado_nao_toca_em_ninguem(self) -> None:
        modelo = _modelo((0, 0), (0, 1))
        self.assertEqual(modelo.apply_headers_to_all(), 0)
        self.assertEqual(modelo.annotated_count(), 0)

    def test_nao_conta_o_proprio_diagrama(self) -> None:
        modelo = _modelo((0, 0))
        modelo.set_header("Event", "Riga")
        self.assertEqual(modelo.apply_headers_to_all(), 0)

    def test_todos_os_campos_da_tela_sao_aplicaveis(self) -> None:
        modelo = _modelo((0, 0), (0, 1))
        for nome in HEADER_FIELDS:
            modelo.set_header(nome, f"v-{nome}")
        modelo.apply_headers_to_all()
        self.assertEqual(len(modelo.annotations.get(0, 1).headers), len(HEADER_FIELDS))


class DerivadosTests(unittest.TestCase):
    def test_fen_efetiva_usa_o_que_a_varredura_leu(self) -> None:
        modelo = GalleryModel(
            index=GalleryIndex(entries=[GalleryEntry(0, 0, PLACEMENT, side_to_move="b")]),
            annotations=GalleryAnnotations(),
        )
        self.assertEqual(modelo.effective_fen(), f"{PLACEMENT} b - - 0 1")

    def test_declaracao_vence_a_varredura(self) -> None:
        modelo = GalleryModel(
            index=GalleryIndex(entries=[GalleryEntry(0, 0, PLACEMENT, side_to_move="b")]),
            annotations=GalleryAnnotations(),
        )
        modelo.edit(side_to_move="w", move_number=30)
        self.assertEqual(modelo.effective_fen(), f"{PLACEMENT} w - - 0 30")

    def test_o_link_acompanha_a_edicao(self) -> None:
        """O defeito clássico seria mudar o lance e o link apontar para a posição antiga."""
        modelo = _modelo((0, 0))
        antes = modelo.lichess_url()
        modelo.edit(move_number=42)
        self.assertNotEqual(modelo.lichess_url(), antes)
        self.assertIn("0_42", modelo.lichess_url())

    def test_link_segue_o_padrao_quando_nao_declarado(self) -> None:
        modelo = _modelo((0, 0))
        self.assertTrue(modelo.exports_lichess_link(default=True))
        self.assertFalse(modelo.exports_lichess_link(default=False))

    def test_declaracao_por_diagrama_vence_o_padrao(self) -> None:
        modelo = _modelo((0, 0))
        modelo.edit(lichess_link=False)
        self.assertFalse(modelo.exports_lichess_link(default=True))

    def test_descricao_conta_a_partir_de_um(self) -> None:
        modelo = _modelo((0, 0), (5, 0))
        modelo.go_to(1)
        self.assertEqual(modelo.describe_position(), "diagrama 2 de 2 — página 6")


class BaseDePartidasTests(unittest.TestCase):
    """O preenchimento pela base (S-72): ele completa, e nunca sobrescreve."""

    def _casamento(self, **campos: object) -> DiagramMatch:
        padrao: dict[str, object] = {
            "page_index": 0,
            "diagram_index": 0,
            "move_number": 39,
            "side_to_move": "b",
            "headers": {"White": "Ljubojevic, Ljubomir", "Black": "Browne, Walter Shawn", "Event": "IBM"},
            "game_label": "Ljubojevic x Browne, IBM 1972",
        }
        padrao.update(campos)
        return DiagramMatch(**padrao)  # type: ignore[arg-type]

    def test_preenche_lance_vez_e_headers_vazios(self) -> None:
        modelo = _modelo((0, 0))
        relatorio = modelo.apply_matches([self._casamento()])
        anotacao = modelo.current_annotation
        self.assertEqual((relatorio.touched, relatorio.fields), (1, 5))
        self.assertEqual(relatorio.confirmed, 1)
        self.assertEqual(anotacao.move_number, 39)
        self.assertEqual(anotacao.side_to_move, "b")
        self.assertEqual(anotacao.headers["Event"], "IBM")
        self.assertIn("Ljubojevic", anotacao.filled_from)

    def test_o_que_a_pessoa_digitou_fica(self) -> None:
        modelo = _modelo((0, 0))
        modelo.edit(move_number=12, headers={"Event": "Amsterdam"})
        modelo.apply_matches([self._casamento()])
        anotacao = modelo.current_annotation
        self.assertEqual(anotacao.move_number, 12, "o lance digitado não pode ser sobrescrito")
        self.assertEqual(anotacao.headers["Event"], "Amsterdam")
        self.assertEqual(anotacao.headers["White"], "Ljubojevic, Ljubomir", "o campo vazio, esse sim, preenche")

    def test_posicao_comum_confirma_mas_nao_preenche(self) -> None:
        """Casar com 40 partidas não identifica partida nenhuma -- mas confirma a leitura.

        As duas metades importam: a posição é real (S-74, tira o diagrama da fila) e não se
        sabe de qual partida ela veio (S-72, não preenche header nenhum).
        """
        modelo = _modelo((0, 0))
        relatorio = modelo.apply_matches([self._casamento(games_matched=40)])
        anotacao = modelo.current_annotation
        self.assertEqual((relatorio.touched, relatorio.fields), (0, 0))
        self.assertEqual((relatorio.confirmed, relatorio.ambiguous), (1, 1))
        self.assertEqual(anotacao.confirmed_from, "40 partidas da base")
        self.assertIsNone(anotacao.move_number)
        self.assertEqual(anotacao.headers, {})
        self.assertFalse(anotacao.is_empty, "a confirmação sozinha já é uma afirmação, e persiste")

    def test_nada_a_preencher_nao_conta_diagrama(self) -> None:
        modelo = _modelo((0, 0))
        modelo.apply_matches([self._casamento()])
        relatorio = modelo.apply_matches([self._casamento()])
        self.assertEqual((relatorio.touched, relatorio.fields), (0, 0), "rodar duas vezes não inventa mudança")
        self.assertEqual(relatorio.confirmed, 1, "mas o diagrama continua confirmado")

    def test_registra_quais_campos_vieram_da_base(self) -> None:
        """É o que faz o PGN dizer `database` em vez de `manual` -- ver `annotated_side_to_move`."""
        modelo = _modelo((0, 0))
        modelo.apply_matches([self._casamento()])
        campos = modelo.current_annotation.filled_fields
        self.assertIn("side_to_move", campos)
        self.assertIn("move_number", campos)
        self.assertIn("header:Event", campos)

    def test_corrigir_a_vez_a_mao_tira_ela_da_procedencia_da_base(self) -> None:
        modelo = _modelo((0, 0))
        modelo.apply_matches([self._casamento()])
        modelo.edit(side_to_move="w")
        anotacao = modelo.current_annotation
        self.assertNotIn("side_to_move", anotacao.filled_fields)
        self.assertIn("move_number", anotacao.filled_fields, "o lance não foi tocado, e continua da base")
        self.assertTrue(anotacao.filled_from, "a evidência fica enquanto sobrar campo dela")

    def test_corrigir_um_header_nao_derruba_a_procedencia_dos_outros(self) -> None:
        modelo = _modelo((0, 0))
        modelo.apply_matches([self._casamento()])
        modelo.set_header("Event", "Amsterdam")
        campos = modelo.current_annotation.filled_fields
        self.assertNotIn("header:Event", campos)
        self.assertIn("header:White", campos)

    def test_sem_campo_nenhum_da_base_a_evidencia_some(self) -> None:
        """Uma evidência que não descreve mais nenhum campo é procedência de coisa alguma."""
        modelo = _modelo((0, 0))
        modelo.apply_matches([self._casamento(headers={})])
        modelo.edit(side_to_move="w", move_number=3)
        self.assertEqual(modelo.current_annotation.filled_fields, ())
        self.assertEqual(modelo.current_annotation.filled_from, "")

    def test_rodar_a_busca_de_novo_nao_apaga_a_procedencia_anterior(self) -> None:
        modelo = _modelo((0, 0))
        modelo.apply_matches([self._casamento(headers={"Event": "IBM"})])
        modelo.apply_matches([self._casamento(headers={"Site": "Amsterdam"})])
        campos = modelo.current_annotation.filled_fields
        self.assertIn("header:Event", campos)
        self.assertIn("header:Site", campos)

    def test_recupera_a_procedencia_de_quem_gravou_antes_de_ela_existir(self) -> None:
        """Reparo: `filled_from` sem `filled_fields` só existe em anotação da versão antiga.

        Sem isto, o PGN sai dizendo `manual` para campo que a base escreveu -- o defeito que a
        correção de procedência existe para eliminar, sobrevivendo nos dados.
        """
        modelo = _modelo((0, 0))
        casamento = self._casamento()
        modelo.annotations.update(
            0,
            0,
            move_number=casamento.move_number,
            side_to_move=casamento.side_to_move,
            headers=dict(casamento.headers),
            filled_from=casamento.game_label,
        )
        relatorio = modelo.apply_matches([casamento])
        campos = modelo.current_annotation.filled_fields
        self.assertEqual(relatorio.recovered, 5, "lance, vez e os três headers")
        self.assertEqual(relatorio.fields, 0, "não preencheu nada -- os valores já estavam lá")
        self.assertIn("side_to_move", campos)
        self.assertIn("header:Event", campos)

    def test_o_reparo_nao_reivindica_o_que_a_pessoa_mudou(self) -> None:
        modelo = _modelo((0, 0))
        modelo.annotations.update(
            0, 0, move_number=12, side_to_move="b", headers={"Event": "Amsterdam"}, filled_from="Ljubojevic x Browne"
        )
        modelo.apply_matches([self._casamento()])
        campos = modelo.current_annotation.filled_fields
        self.assertNotIn("move_number", campos, "39 era o da base; 12 é de quem digitou")
        self.assertNotIn("header:Event", campos)
        self.assertIn("side_to_move", campos)

    def test_o_reparo_nao_toca_em_anotacao_que_ja_tem_procedencia(self) -> None:
        modelo = _modelo((0, 0))
        modelo.apply_matches([self._casamento()])
        relatorio = modelo.apply_matches([self._casamento()])
        self.assertEqual(relatorio.recovered, 0)

    def test_pares_pendentes_saem_das_legendas_sem_repetir(self) -> None:
        modelo = GalleryModel(
            index=GalleryIndex(
                entries=[
                    GalleryEntry(0, 0, PLACEMENT, caption="Coull - Stanciu"),
                    GalleryEntry(1, 0, PLACEMENT, caption="Coull - Stanciu\noutra linha"),
                    GalleryEntry(2, 0, PLACEMENT, caption="Diagrama 12"),
                ]
            ),
            annotations=GalleryAnnotations(),
        )
        self.assertEqual(modelo.pending_pairs(), {("coull", "stanciu")})


class GravacaoTests(unittest.TestCase):
    def test_sem_livro_aberto_nao_grava(self) -> None:
        self.assertIsNone(_modelo((0, 0)).save())

    def test_grava_e_le_de_volta(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            modelo = _modelo((0, 0))
            modelo.pdf_path = Path(pasta) / "livro.pdf"
            modelo.gallery_dir = Path(pasta)
            modelo.edit(move_number=7, lichess_link=False)

            caminho = modelo.save()
            self.assertIsNotNone(caminho)
            self.assertEqual(caminho.parent, Path(pasta), "não pode gravar no data/ de verdade")
            voltou = load_annotations(modelo.pdf_path, directory=Path(pasta))
        self.assertEqual(voltou.get(0, 0), DiagramAnnotation(move_number=7, lichess_link=False))


if __name__ == "__main__":
    unittest.main()
