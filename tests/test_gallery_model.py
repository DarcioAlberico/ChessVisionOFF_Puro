"""Navegação, anotação e sincronia da galeria, sem janela (S-67)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import chess

from chess_diagram_ocr.gallery import DiagramAnnotation, GalleryAnnotations, load_annotations
from chess_diagram_ocr.gallery_scan import GalleryEntry, GalleryIndex
from chess_diagram_ocr.games_cache import CachedPosition, PositionCache
from chess_diagram_ocr.games_db import DiagramMatch, PositionHit
from chess_diagram_ocr.games_index import build_index
from chess_diagram_ocr.ui.gallery_model import HEADER_FIELDS, GalleryModel, describe_origin

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


class LimparHeadersTests(unittest.TestCase):
    """Limpar tudo de um diagrama (S-94): o gesto de quando a base preencheu a partida errada."""

    def _com_a_base(self) -> GalleryModel:
        """Um diagrama como a busca por posição o deixa: headers, lance, vez e procedência."""
        modelo = _modelo((0, 0), (0, 1))
        modelo.annotations.update(
            0,
            0,
            move_number=24,
            side_to_move="b",
            headers={"White": "Karpov, Anatoly", "Event": "Linares", "Date": "1994.05.30"},
            filled_from="Karpov x Kasparov, Linares 1994",
            filled_rule="date",
            filled_fields=("move_number", "side_to_move", "header:White", "header:Event", "header:Date"),
            confirmed_from="Karpov x Kasparov, Linares 1994",
        )
        return modelo

    def test_apaga_todos_os_headers_e_devolve_quais(self) -> None:
        modelo = self._com_a_base()
        self.assertEqual(modelo.clear_headers(), ("Date", "Event", "White"))
        self.assertEqual(modelo.current_annotation.headers, {})

    def test_o_lance_e_a_vez_ficam(self) -> None:
        """A pessoa costuma ter contado o lance no livro, e apagar trabalho que ninguém mandou
        apagar é o defeito da S-76."""
        modelo = self._com_a_base()
        modelo.clear_headers()
        anotacao = modelo.current_annotation
        self.assertEqual(anotacao.move_number, 24)
        self.assertEqual(anotacao.side_to_move, "b")

    def test_a_procedencia_dos_headers_sai_junto(self) -> None:
        """Header removido deixa de ter origem -- a regra do `set_header`, de uma vez só."""
        modelo = self._com_a_base()
        modelo.clear_headers()
        self.assertEqual(modelo.current_annotation.filled_fields, ("move_number", "side_to_move"))
        self.assertEqual(
            modelo.current_annotation.filled_from,
            "Karpov x Kasparov, Linares 1994",
            "o lance e a vez continuam sendo da base, então a evidência ainda descreve algo",
        )

    def test_sem_nada_da_base_sobrando_a_evidencia_some(self) -> None:
        modelo = _modelo((0, 0))
        modelo.annotations.update(
            0,
            0,
            headers={"Event": "Linares"},
            filled_from="Karpov x Kasparov, Linares 1994",
            filled_rule="date",
            filled_fields=("header:Event",),
        )
        modelo.clear_headers()
        self.assertEqual(modelo.current_annotation.filled_from, "")
        self.assertEqual(
            modelo.current_annotation.filled_rule,
            "",
            "a regra que escolheu a partida não descreve mais nada, e o censo a contaria",
        )

    def test_a_confirmacao_da_leitura_sobrevive(self) -> None:
        """As 64 casas bateram com uma partida de verdade, e limpar header não desfaz isso --
        senão o diagrama voltaria para a fila de revisão por um gesto que não fala dela (S-74)."""
        modelo = self._com_a_base()
        modelo.clear_headers()
        self.assertEqual(modelo.current_annotation.confirmed_from, "Karpov x Kasparov, Linares 1994")

    def test_nao_toca_em_nenhum_outro_diagrama(self) -> None:
        modelo = self._com_a_base()
        modelo.annotations.update(0, 1, headers={"Event": "Linares"})
        modelo.clear_headers()
        self.assertEqual(modelo.annotations.get(0, 1).headers, {"Event": "Linares"})

    def test_o_header_livre_sai_tambem(self) -> None:
        """`headers` é um dicionário, e "todos" quer dizer todos."""
        modelo = _modelo((0, 0))
        modelo.set_header("Annotator", "Kasparov")
        modelo.set_header("SourceQuality", "3")
        self.assertEqual(modelo.clear_headers(), ("Annotator", "SourceQuality"))
        self.assertEqual(modelo.current_annotation.headers, {})

    def test_sem_header_nenhum_nao_faz_nada(self) -> None:
        modelo = _modelo((0, 0))
        modelo.edit(move_number=12)
        self.assertEqual(modelo.clear_headers(), ())
        self.assertEqual(modelo.current_annotation.move_number, 12)

    def test_sem_diagrama_devolve_vazio(self) -> None:
        self.assertEqual(GalleryModel().clear_headers(), ())

    def test_a_anotacao_que_so_tinha_headers_some_do_conjunto(self) -> None:
        """Visitar não é anotar: limpar o único campo declarado tem de esvaziar a linha."""
        modelo = _modelo((0, 0))
        modelo.set_header("Event", "Linares")
        self.assertEqual(modelo.annotated_count(), 1)
        modelo.clear_headers()
        self.assertEqual(modelo.annotated_count(), 0)


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


class DesfazerCopiaTests(unittest.TestCase):
    """O desfazer do "copiar para todos" (S-76): apaga pelo valor, não pela chave."""

    def _modelo_com_headers(self) -> GalleryModel:
        modelo = _modelo((0, 0), (5, 0), (9, 0))
        modelo.annotations.update(0, 0, headers={"Event": "Amsterdam", "White": "Ljubojevic"})
        modelo.annotations.update(5, 0, headers={"Event": "Amsterdam", "White": "Ljubojevic"})
        modelo.annotations.update(9, 0, headers={"Event": "Linares 10th", "White": "Bareev, Evgeny"})
        return modelo

    def test_apaga_so_onde_o_valor_bate(self) -> None:
        modelo = self._modelo_com_headers()
        atingidos = modelo.revert_headers({"Event": "Amsterdam", "White": "Ljubojevic"})
        self.assertEqual(atingidos, 2)
        self.assertEqual(modelo.annotations.get(9, 0).headers, {"Event": "Linares 10th", "White": "Bareev, Evgeny"})
        self.assertEqual(modelo.annotations.get(0, 0).headers, {})

    def test_o_que_a_copia_sobrescreveu_nao_volta(self) -> None:
        """A ressalva que justifica a pergunta antes: o valor anterior não existe mais."""
        modelo = self._modelo_com_headers()
        modelo.revert_headers({"Event": "Amsterdam"})
        self.assertNotIn("Event", modelo.annotations.get(0, 0).headers)

    def test_desfazer_tira_junto_a_procedencia_do_header_removido(self) -> None:
        modelo = _modelo((0, 0))
        modelo.annotations.update(
            0,
            0,
            headers={"Event": "Amsterdam", "Site": "Moscow"},
            filled_fields=("header:Event", "header:Site"),
            filled_from="uma partida",
        )
        modelo.revert_headers({"Event": "Amsterdam"})
        anotacao = modelo.annotations.get(0, 0)
        self.assertEqual(anotacao.filled_fields, ("header:Site",))
        self.assertEqual(anotacao.filled_from, "uma partida")

    def test_valor_vazio_nao_apaga_nada(self) -> None:
        """Senão, um campo em branco no diagrama atual viraria um apagador em massa."""
        modelo = self._modelo_com_headers()
        self.assertEqual(modelo.revert_headers({"Event": ""}), 0)

    def test_o_que_a_copia_levaria_e_visivel_antes_de_copiar(self) -> None:
        modelo = self._modelo_com_headers()
        self.assertEqual(modelo.headers_to_apply(), {"Event": "Amsterdam", "White": "Ljubojevic"})


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

    # ------------------------------------------- a regra que escolheu a partida (S-91)

    def test_a_legenda_preenche_o_que_a_contagem_sozinha_nao_preencheria(self) -> None:
        """Os 232 diagramas do acervo que hoje ficam confirmados e vazios.

        Uma posição em 40 partidas não identifica partida nenhuma *pela contagem* -- mas
        identifica se a legenda do livro nomeia exatamente uma delas.
        """
        modelo = _modelo((0, 0))
        relatorio = modelo.apply_matches([self._casamento(games_matched=40, caption_confirmed=True)])
        anotacao = modelo.current_annotation
        self.assertEqual(relatorio.ambiguous, 0, "a legenda respondeu o que a contagem não respondia")
        self.assertEqual(relatorio.by_caption, 1)
        self.assertEqual(anotacao.move_number, 39)
        self.assertEqual(anotacao.filled_rule, "caption")

    def test_partida_unica_e_desempate_por_data_ficam_distinguiveis(self) -> None:
        """Sem isto, os 141 preenchidos às cegas são indistinguíveis de dado conferido -- e o
        censo da S-89 não teria como listá-los para revisão."""
        unico = _modelo((0, 0))
        unico.apply_matches([self._casamento()])
        self.assertEqual(unico.current_annotation.filled_rule, "unique")

        cego = _modelo((0, 0))
        relatorio = cego.apply_matches([self._casamento(games_matched=3)])
        self.assertEqual(cego.current_annotation.filled_rule, "date")
        self.assertEqual(relatorio.by_caption, 0, "não houve legenda confirmando")

    def test_a_linha_de_procedencia_diz_a_regra(self) -> None:
        """"A mais antiga entre várias" é um palpite, e uma tela que o mostre igual a "partida
        única" mente por omissão."""
        modelo = _modelo((0, 0))
        modelo.apply_matches([self._casamento(games_matched=3)])
        self.assertIn("a mais antiga entre várias", describe_origin(modelo.current_annotation))

    def test_a_regra_sobrevive_ao_disco(self) -> None:
        anotacao = DiagramAnnotation(move_number=39, filled_from="x", filled_rule="caption")
        self.assertEqual(DiagramAnnotation.from_dict(anotacao.to_dict()).filled_rule, "caption")

    def test_regra_desconhecida_no_disco_vira_vazio(self) -> None:
        """"Não sei por que esta partida" é resposta melhor que uma etiqueta inventada."""
        self.assertEqual(DiagramAnnotation.from_dict({"filled_rule": "chute"}).filled_rule, "")

    def test_a_escolha_humana_sobrevive_a_nova_varredura(self) -> None:
        """**O que a S-86 promete e a S-77 já havia ensinado a cobrar.**

        Sem isto, um `cvoff-games --apply` depois de uma tarde de escolhas reimporia a partida
        que o desempate automático prefere, e o trabalho da pessoa sumiria sem aviso.
        """
        modelo = _modelo((0, 0))
        escolhida = PositionHit(
            move_number=24, side_to_move="b", headers={"White": "Karpov, Anatoly", "Black": "Korchnoi, Viktor"}
        )
        modelo.choose_game(escolhida)

        relatorio = modelo.apply_matches([self._casamento(games_matched=3, candidates=(PositionHit(
            move_number=40, side_to_move="w", headers={"White": "Havasi, Kornel", "Black": "Tartakower, Saviely"}
        ),))])
        anotacao = modelo.current_annotation
        self.assertEqual(relatorio.respected, 1)
        self.assertEqual(anotacao.move_number, 24, "o lance da partida escolhida à mão")
        self.assertEqual(anotacao.filled_rule, "human")
        self.assertIn("partidas da base", anotacao.confirmed_from, "mas a leitura segue confirmada")


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


class EscolhaDaPartidaTests(unittest.TestCase):
    """A lista de candidatas e a escolha (S-86) -- toda a decisão, sem abrir um Tk."""

    def _hit(self, brancas: str, pretas: str, lance: int, data: str = "1974.09.12") -> PositionHit:
        return PositionHit(
            move_number=lance,
            side_to_move="b",
            headers={"White": brancas, "Black": pretas, "Date": data, "Event": "Cand fin"},
        )

    def _modelo_com_cache(self, *entradas: tuple[GalleryEntry, list[PositionHit]]) -> GalleryModel:
        cache = PositionCache()
        indice = GalleryIndex(entries=[entrada for entrada, _ in entradas])
        for entrada, partidas in entradas:
            cache.positions[entrada.placement] = CachedPosition(count=len(partidas), games=tuple(partidas))
        return GalleryModel(index=indice, position_cache=cache)

    def setUp(self) -> None:
        self.karpov = self._hit("Karpov, Anatoly", "Korchnoi, Viktor", 24)
        self.outra = self._hit("Havasi, Kornel", "Tartakower, Saviely", 40, data="1929.01.01")
        self.entrada = GalleryEntry(0, 0, "posicao-a", caption="Karpov - Korchnoi")
        self.modelo = self._modelo_com_cache((self.entrada, [self.outra, self.karpov]))

    def test_a_lista_vem_com_a_da_legenda_na_frente(self) -> None:
        candidatas, total = self.modelo.current_candidates()
        self.assertEqual(total, 2)
        self.assertEqual(candidatas[0], self.karpov, "a legenda ordena antes da data (S-91)")

    def test_a_contagem_verdadeira_acompanha_a_lista_truncada(self) -> None:
        """"32 de 147" -- sem isto a pessoa escolhe achando que viu tudo."""
        cache = PositionCache()
        cache.positions["x"] = CachedPosition(count=147, games=(self.karpov,))
        modelo = GalleryModel(index=GalleryIndex(entries=[GalleryEntry(0, 0, "x")]), position_cache=cache)
        candidatas, total = modelo.current_candidates()
        self.assertEqual((len(candidatas), total), (1, 147))

    def test_sem_cache_nao_ha_candidata_e_nada_quebra(self) -> None:
        modelo = GalleryModel(index=GalleryIndex(entries=[self.entrada]))
        self.assertEqual(modelo.current_candidates(), ((), 0))

    def test_escolher_preenche_lance_vez_e_headers(self) -> None:
        campos = self.modelo.choose_game(self.karpov)
        anotacao = self.modelo.current_annotation
        self.assertEqual(anotacao.move_number, 24)
        self.assertEqual(anotacao.side_to_move, "b")
        self.assertEqual(anotacao.headers["White"], "Karpov, Anatoly")
        self.assertEqual(anotacao.chosen_game, self.karpov.key)
        self.assertEqual(anotacao.filled_rule, "human")
        self.assertIn("move_number", campos)

    def test_trocar_de_partida_troca_os_campos_que_a_base_tinha_posto(self) -> None:
        """Mesma origem, versão melhor: o que a base escreveu, a escolha humana pode trocar."""
        self.modelo.choose_game(self.outra)
        self.modelo.choose_game(self.karpov)
        anotacao = self.modelo.current_annotation
        self.assertEqual(anotacao.move_number, 24)
        self.assertEqual(anotacao.headers["White"], "Karpov, Anatoly")
        self.assertNotIn("Havasi", str(anotacao.headers))

    def test_o_que_a_pessoa_digitou_e_declarado_como_conflito_e_nao_sumindo(self) -> None:
        self.modelo.edit(move_number=12, headers={"Event": "Amsterdam"})
        conflitos = self.modelo.conflicts_with(self.karpov)
        self.assertIn("move_number", conflitos)
        self.assertIn("header:Event", conflitos)

    def test_sem_autorizacao_o_digitado_fica_e_o_resto_entra(self) -> None:
        self.modelo.edit(move_number=12)
        self.modelo.choose_game(self.karpov)
        anotacao = self.modelo.current_annotation
        self.assertEqual(anotacao.move_number, 12, "o que a pessoa digitou não some calado")
        self.assertEqual(anotacao.headers["White"], "Karpov, Anatoly", "o campo vazio, esse sim, entra")
        self.assertEqual(anotacao.chosen_game, self.karpov.key, "e a escolha fica registrada")

    def test_com_autorizacao_o_digitado_e_substituido(self) -> None:
        self.modelo.edit(move_number=12)
        self.modelo.choose_game(self.karpov, overwrite=True)
        self.assertEqual(self.modelo.current_annotation.move_number, 24)

    def test_o_vizinho_sem_a_partida_nao_entra(self) -> None:
        """**A trava que faltou no "aplicar a todos" da S-76**, que espalhou quatro campos por
        1.405 diagramas. Aqui o vizinho que não contém aquela partida simplesmente não entra."""
        vizinho_com = GalleryEntry(1, 0, "posicao-b", caption="")
        vizinho_sem = GalleryEntry(2, 0, "posicao-c", caption="")
        modelo = self._modelo_com_cache(
            (self.entrada, [self.karpov]),
            (vizinho_com, [self._hit("Karpov, Anatoly", "Korchnoi, Viktor", 31)]),
            (vizinho_sem, [self.outra]),
        )
        vizinhos = modelo.neighbours_with_game(self.karpov)
        self.assertEqual([v.key for v in vizinhos], [(1, 0)])

    def test_cada_vizinho_recebe_o_lance_dele(self) -> None:
        """É a mesma partida em outro momento dela. Copiar o número do lance seria escrever o
        dado errado com a confiança de quem escolheu a partida certa."""
        vizinho = GalleryEntry(1, 0, "posicao-b", caption="")
        modelo = self._modelo_com_cache(
            (self.entrada, [self.karpov]),
            (vizinho, [self._hit("Karpov, Anatoly", "Korchnoi, Viktor", 31)]),
        )
        self.assertEqual(modelo.apply_game_to_neighbours(self.karpov), 1)
        self.assertEqual(modelo.annotations.get(1, 0).move_number, 31)
        self.assertEqual(modelo.annotations.get(1, 0).chosen_game, self.karpov.key)
        self.assertEqual(modelo.position, 0, "e a navegação volta para onde estava")

    def test_a_partida_que_os_vizinhos_tambem_tem_sobe_na_lista(self) -> None:
        """S-88 como **dica**, e não como regra: ela reprovou a medição (16,6% contra 20%) e
        só 3 casos tinham como ser conferidos. Como ordenação ela não pode errar -- no pior
        caso põe a candidata errada em segundo lugar numa lista que já ia ser lida."""
        terceira = self._hit("Tal, Mikhail", "Botvinnik, Mikhail", 18, data="1960.03.15")
        entrada = GalleryEntry(0, 0, "posicao-a", caption="")
        vizinho = GalleryEntry(1, 0, "posicao-b", caption="")
        modelo = self._modelo_com_cache(
            (entrada, [self.outra, terceira, self.karpov]),
            (vizinho, [self._hit("Tal, Mikhail", "Botvinnik, Mikhail", 25, data="1960.03.15")]),
        )
        candidatas, _ = modelo.current_candidates()
        self.assertEqual(candidatas[0].key, terceira.key, "a que o vizinho também tem vem antes")

    def test_a_legenda_continua_vencendo_a_vizinhanca(self) -> None:
        """A ordem dos critérios é a da força da evidência: legenda, vizinhos, data."""
        vizinho = GalleryEntry(1, 0, "posicao-b", caption="")
        modelo = self._modelo_com_cache(
            (self.entrada, [self.outra, self.karpov]),
            (vizinho, [self._hit("Havasi, Kornel", "Tartakower, Saviely", 40, data="1929.01.01")]),
        )
        candidatas, _ = modelo.current_candidates()
        self.assertEqual(candidatas[0], self.karpov, "a legenda deste diagrama diz Karpov")

    def test_a_dica_da_vizinhanca_nao_descarta_ninguem(self) -> None:
        candidatas, total = self.modelo.current_candidates()
        self.assertEqual(len(candidatas), 2)
        self.assertEqual(total, 2)

    def test_a_busca_por_nome_acha_o_que_a_lista_truncada_perdeu(self) -> None:
        """S-87: em 9 dos 22 casos medidos a partida certa ficou fora do teto de 32, e
        perguntar por nome não tem lista para truncar."""
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        raiz = Path(pasta.name)
        base = raiz / "base.pgn"
        base.write_text(
            '[Event "London"]\n[Date "1851.06.21"]\n[White "Coull, Alison"]\n'
            '[Black "Stanciu, Gabriela"]\n\n1. e4 e5 2. f4 exf4 1-0\n',
            encoding="utf-8",
        )
        indice = raiz / "i.sqlite"
        build_index(base, indice)

        tabuleiro = chess.Board()
        for lance in ("e4", "e5", "f4", "exf4"):
            tabuleiro.push_san(lance)
        entrada = GalleryEntry(0, 0, tabuleiro.board_fen(), caption="Coull - Stanciu")
        modelo = GalleryModel(
            index=GalleryIndex(entries=[entrada]), database_paths=(base,), index_path=indice
        )
        (achada,) = modelo.search_games_by_name()
        self.assertEqual(achada.move_number, tabuleiro.fullmove_number)
        self.assertEqual(achada.headers["Black"], "Stanciu, Gabriela")

    def test_a_busca_por_nome_alcanca_a_segunda_base(self) -> None:
        """O caso da S-93: a partida está no `.pgn` que a busca de antes não abria."""
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        raiz = Path(pasta.name)
        primeira = raiz / "a_primeira.pgn"
        primeira.write_text(
            '[Event "London"]\n[White "Morphy, Paul"]\n[Black "Harrwitz, Daniel"]\n\n1. e4 e5 1-0\n',
            encoding="utf-8",
        )
        segunda = raiz / "b_segunda.pgn"
        segunda.write_text(
            '[Event "Hexagon North Devon"]\n[Date "1973.10.11"]\n[White "Hutchings, Stuart J"]\n'
            '[Black "Keene, Raymond D"]\n[Result "0-1"]\n\n1. c4 Nf6 2. Nc3 b6 0-1\n',
            encoding="utf-8",
        )
        indice = raiz / "i.sqlite"
        build_index([primeira, segunda], indice)

        tabuleiro = chess.Board()
        for lance in ("c4", "Nf6", "Nc3", "b6"):
            tabuleiro.push_san(lance)
        entrada = GalleryEntry(0, 0, tabuleiro.board_fen(), caption="Hutchings - Keene")
        modelo = GalleryModel(
            index=GalleryIndex(entries=[entrada]),
            database_paths=(primeira, segunda),
            index_path=indice,
        )
        (achada,) = modelo.search_games_by_name()
        self.assertTrue(achada.verified, "as 64 casas bateram")
        self.assertEqual(achada.headers["Event"], "Hexagon North Devon")

    def test_a_partida_do_par_sem_a_posicao_entra_como_nao_verificada(self) -> None:
        """**68 dos 140 diagramas do acervo nessa situação** -- a base tem a partida e não tem
        aquela posição. Ela pode dar evento, data e resultado; não pode dar o lance."""
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        raiz = Path(pasta.name)
        base = raiz / "base.pgn"
        base.write_text(
            '[Event "Hastings"]\n[Date "1895.08.10"]\n[White "Coull, Alison"]\n'
            '[Black "Stanciu, Gabriela"]\n[Result "1-0"]\n\n1. d4 d5 2. c4 1-0\n',
            encoding="utf-8",
        )
        indice = raiz / "i.sqlite"
        build_index(base, indice)

        entrada = GalleryEntry(0, 0, "8/8/8/8/8/8/4K3/4k3", caption="Coull - Stanciu")
        modelo = GalleryModel(
            index=GalleryIndex(entries=[entrada]), database_paths=(base,), index_path=indice
        )
        (achada,) = modelo.search_games_by_name()
        self.assertFalse(achada.verified)
        self.assertIn("posição não confere", achada.label)

        campos = modelo.choose_game(achada)
        anotacao = modelo.current_annotation
        self.assertIsNone(anotacao.move_number, "lance vem da posição, e a posição não bate")
        self.assertIsNone(anotacao.side_to_move)
        self.assertEqual(anotacao.headers["Event"], "Hastings")
        self.assertEqual(anotacao.headers["Result"], "1-0")
        self.assertNotIn("move_number", campos)

    def test_a_candidata_nao_verificada_nao_conflita_com_o_lance_digitado(self) -> None:
        """O que ela não sabe não pode discordar de ninguém."""
        nao_verificada = PositionHit(move_number=0, side_to_move="", headers={"Event": "x"}, verified=False)
        self.modelo.edit(move_number=12)
        self.assertNotIn("move_number", self.modelo.conflicts_with(nao_verificada))
        self.modelo.choose_game(nao_verificada)
        self.assertEqual(self.modelo.current_annotation.move_number, 12)

    def test_sem_indice_a_busca_por_nome_devolve_vazio_e_a_lista_continua(self) -> None:
        """Caminho a mais, não substituto: sem índice, a lista do cache segue respondendo."""
        self.assertEqual(self.modelo.search_games_by_name(), ())
        self.assertEqual(len(self.modelo.current_candidates()[0]), 2)

    def test_sem_nomes_na_legenda_nao_ha_por_onde_procurar(self) -> None:
        modelo = self._modelo_com_cache((GalleryEntry(0, 0, "x", caption="Diagrama 41"), [self.karpov]))
        modelo.database_paths, modelo.index_path = (Path("base.pgn"),), Path("i.sqlite")
        self.assertEqual(modelo.search_games_by_name(), ())

    def test_a_escolha_sobrevive_ao_disco(self) -> None:
        self.modelo.choose_game(self.karpov)
        anotacao = self.modelo.current_annotation
        self.assertEqual(DiagramAnnotation.from_dict(anotacao.to_dict()).chosen_game, self.karpov.key)

    def test_uma_anotacao_que_so_tem_a_escolha_nao_e_vazia(self) -> None:
        """Escolher uma partida é uma afirmação inteira, como o `confirmed_from` da S-74 --
        e não a procedência de outro campo. Descartá-la faria a escolha sumir do arquivo."""
        self.assertFalse(DiagramAnnotation(chosen_game="a|b|c||").is_empty)

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
