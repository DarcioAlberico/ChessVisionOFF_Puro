"""As anotações por diagrama da galeria e o que elas mudam no PGN (S-67)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import chess

from chess_diagram_ocr.gallery import (
    DiagramAnnotation,
    GalleryAnnotations,
    annotations_path_for,
    export_human,
    human_only,
    lichess_analysis_url,
    load_annotations,
    read_human_extract,
    restore_human,
    save_annotations,
    write_human_extract,
)
from chess_diagram_ocr.pdf_to_pgn import DiagramPosition, build_pgn_text
from chess_diagram_ocr.semantics import SideToMove

PLACEMENT = "4k3/8/8/8/8/8/8/4K3"


def _posicao(page: int = 0, diagram: int = 0, side: SideToMove | None = None) -> DiagramPosition:
    return DiagramPosition(
        page_index=page,
        diagram_index=diagram,
        fen=PLACEMENT,
        confidence=0.99,
        min_confidence=0.98,
        is_legal=True,
        is_fatal=False,
        side_to_move=side,
    )


class AnotacaoTests(unittest.TestCase):
    def test_vazia_e_vazia(self) -> None:
        self.assertTrue(DiagramAnnotation().is_empty)
        self.assertFalse(DiagramAnnotation(move_number=3).is_empty)
        self.assertFalse(DiagramAnnotation(lichess_link=False).is_empty)
        self.assertFalse(DiagramAnnotation(headers={"White": "Tal"}).is_empty)

    def test_lichess_false_nao_e_o_mesmo_que_ausente(self) -> None:
        """Tri-estado: `False` é uma decisão, `None` é "siga o padrão da exportação"."""
        self.assertIsNone(DiagramAnnotation().lichess_link)
        self.assertIs(DiagramAnnotation(lichess_link=False).lichess_link, False)
        self.assertIn("lichess_link", DiagramAnnotation(lichess_link=False).to_dict())
        self.assertNotIn("lichess_link", DiagramAnnotation().to_dict())

    def test_lance_zero_ou_negativo_vira_ausencia(self) -> None:
        self.assertIsNone(DiagramAnnotation.from_dict({"move_number": 0}).move_number)
        self.assertIsNone(DiagramAnnotation.from_dict({"move_number": -4}).move_number)
        self.assertIsNone(DiagramAnnotation.from_dict({"move_number": "seis"}).move_number)
        self.assertEqual(DiagramAnnotation.from_dict({"move_number": "24"}).move_number, 24)

    def test_lado_so_aceita_w_ou_b(self) -> None:
        self.assertEqual(DiagramAnnotation.from_dict({"side_to_move": "B"}).side_to_move, "b")
        self.assertEqual(DiagramAnnotation.from_dict({"side_to_move": "white"}).side_to_move, "w")
        self.assertIsNone(DiagramAnnotation.from_dict({"side_to_move": "x"}).side_to_move)

    def test_headers_reservados_sao_recusados(self) -> None:
        """`[FEN]` digitada à mão criaria um PGN cujo header contradiz o próprio diagrama."""
        anotacao = DiagramAnnotation.from_dict({"headers": {"FEN": "lixo", "SetUp": "0", "White": "Tal"}})
        self.assertEqual(anotacao.headers, {"White": "Tal"})

    def test_header_vazio_some(self) -> None:
        self.assertEqual(DiagramAnnotation.from_dict({"headers": {"White": "   "}}).headers, {})


class ConjuntoTests(unittest.TestCase):
    def test_get_devolve_vazia_e_nunca_none(self) -> None:
        self.assertTrue(GalleryAnnotations().get(3, 1).is_empty)

    def test_gravar_vazia_apaga_a_chave(self) -> None:
        """Limpar os campos tem de significar "volte ao padrão", não "declarei nada"."""
        conjunto = GalleryAnnotations()
        conjunto.set(0, 0, DiagramAnnotation(move_number=5))
        self.assertIn((0, 0), conjunto.entries)
        conjunto.set(0, 0, DiagramAnnotation())
        self.assertNotIn((0, 0), conjunto.entries)

    def test_update_preserva_os_outros_campos(self) -> None:
        conjunto = GalleryAnnotations()
        conjunto.update(1, 2, move_number=9)
        conjunto.update(1, 2, lichess_link=False)
        anotacao = conjunto.get(1, 2)
        self.assertEqual(anotacao.move_number, 9)
        self.assertIs(anotacao.lichess_link, False)

    def test_ida_e_volta_pelo_json(self) -> None:
        conjunto = GalleryAnnotations(source_name="livro.pdf")
        conjunto.set(4, 1, DiagramAnnotation(move_number=17, side_to_move="b", headers={"White": "Tal"}))
        voltou = GalleryAnnotations.from_dict(conjunto.to_dict())
        self.assertEqual(voltou.get(4, 1), conjunto.get(4, 1))

    def test_chave_do_json_e_pagina_ponto_diagrama(self) -> None:
        conjunto = GalleryAnnotations()
        conjunto.set(7, 2, DiagramAnnotation(move_number=1))
        self.assertIn("7.2", conjunto.to_dict()["diagrams"])

    def test_chave_estragada_e_ignorada_sem_derrubar_o_resto(self) -> None:
        dados = {"diagrams": {"lixo": {"move_number": 3}, "2.0": {"move_number": 8}}}
        conjunto = GalleryAnnotations.from_dict(dados)
        self.assertEqual(conjunto.get(2, 0).move_number, 8)
        self.assertEqual(len(conjunto.entries), 1)


class ArquivoTests(unittest.TestCase):
    def test_ausente_devolve_conjunto_vazio(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            conjunto = load_annotations(Path("livro.pdf"), directory=Path(pasta))
        self.assertEqual(conjunto.entries, {})
        self.assertEqual(conjunto.source_name, "livro.pdf")

    def test_corrompido_nao_derruba_a_exportacao(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = annotations_path_for(Path("livro.pdf"), directory=Path(pasta))
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caminho.write_text("{ isto nao e json", encoding="utf-8")
            conjunto = load_annotations(Path("livro.pdf"), directory=Path(pasta))
        self.assertEqual(conjunto.entries, {})

    def test_grava_e_le_de_volta(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            conjunto = GalleryAnnotations(source_name="livro.pdf")
            conjunto.set(0, 1, DiagramAnnotation(move_number=12, lichess_link=False))
            caminho = save_annotations(Path("/qualquer/livro.pdf"), conjunto, directory=Path(pasta))
            self.assertTrue(caminho.exists())
            gravado = json.loads(caminho.read_text(encoding="utf-8"))
            self.assertEqual(gravado["version"], 1)
            voltou = load_annotations(Path("/qualquer/livro.pdf"), directory=Path(pasta))
        self.assertEqual(voltou.get(0, 1).move_number, 12)
        self.assertIs(voltou.get(0, 1).lichess_link, False)

    def test_nome_do_arquivo_segue_o_stem_como_o_pgn(self) -> None:
        caminho = annotations_path_for(Path("/livros/1937 Kemeri.pdf"), directory=Path("/g"))
        self.assertEqual(caminho.name, "1937 Kemeri.json")


class LichessTests(unittest.TestCase):
    def test_url_troca_espaco_por_underscore(self) -> None:
        url = lichess_analysis_url("8/8/8/8/8/8/8/K6k w - - 0 1")
        self.assertEqual(url, "https://lichess.org/analysis/8/8/8/8/8/8/8/K6k_w_-_-_0_1")

    def test_nao_acessa_a_rede(self) -> None:
        """Montar é offline; abrir é que manda a posição para fora (ver o docstring)."""
        import urllib.request
        from unittest import mock

        with mock.patch.object(urllib.request, "urlopen", side_effect=AssertionError("saiu para a rede")):
            lichess_analysis_url(f"{PLACEMENT} w - - 0 1")


class ExportacaoTests(unittest.TestCase):
    """O que a anotação muda no PGN. É aqui que a galeria justifica existir."""

    def _pgn(self, **kwargs) -> str:
        return build_pgn_text([_posicao()], source_name="livro.pdf", **kwargs)

    def test_sem_anotacao_o_pgn_nao_muda(self) -> None:
        self.assertIn(f'[FEN "{PLACEMENT} w - - 0 1"]', self._pgn())

    def test_lance_entra_na_fen(self) -> None:
        pgn = self._pgn(annotations={(0, 0): DiagramAnnotation(move_number=24)})
        self.assertIn(f'[FEN "{PLACEMENT} w - - 0 24"]', pgn)

    def test_vez_declarada_vence_a_deduzida(self) -> None:
        """É a razão de a galeria existir: corrigir o palpite da S-17, não reforçá-lo."""
        posicao = _posicao(side=SideToMove(color=chess.WHITE, source="legality"))
        pgn = build_pgn_text(
            [posicao],
            source_name="livro.pdf",
            annotations={(0, 0): DiagramAnnotation(side_to_move="b")},
        )
        self.assertIn(f'[FEN "{PLACEMENT} b - - 0 1"]', pgn)
        self.assertIn('[SideToMove "pretas"]', pgn)
        self.assertIn('[SideToMoveSource "manual"]', pgn)

    def test_vez_vinda_da_base_nao_sai_como_declarada_a_mao(self) -> None:
        """`manual` significa "uma pessoa conferiu". A base não é uma pessoa (S-72).

        Marcá-la assim seria procedência inventada -- o erro que a Fase 3 inteira existe para
        eliminar, agora com aparência de dado conferido.
        """
        pgn = self._pgn(
            annotations={
                (0, 0): DiagramAnnotation(
                    side_to_move="b",
                    filled_from="Ljubojevic x Browne, IBM 1972",
                    filled_fields=("side_to_move",),
                )
            }
        )
        self.assertIn('[SideToMoveSource "database"]', pgn)
        self.assertNotIn('[SideToMoveSource "manual"]', pgn)
        self.assertIn('[GameSource "Ljubojevic x Browne, IBM 1972"]', pgn)

    def test_vez_corrigida_a_mao_depois_da_base_sai_como_manual(self) -> None:
        """O campo saiu de `filled_fields` ao ser editado -- ver `GalleryModel.edit`."""
        pgn = self._pgn(
            annotations={
                (0, 0): DiagramAnnotation(
                    side_to_move="b",
                    filled_from="Ljubojevic x Browne, IBM 1972",
                    filled_fields=("move_number",),
                )
            }
        )
        self.assertIn('[SideToMoveSource "manual"]', pgn)

    def test_header_da_pessoa_vence_o_inferido(self) -> None:
        pgn = self._pgn(annotations={(0, 0): DiagramAnnotation(headers={"White": "Tal", "Site": "Riga"})})
        self.assertIn('[White "Tal"]', pgn)
        self.assertIn('[Site "Riga"]', pgn)
        self.assertNotIn('[Site "Local"]', pgn)

    def test_link_por_diagrama_vence_o_padrao_da_exportacao(self) -> None:
        """O pedido original: uns diagramas precisam do link e outros não."""
        sem = self._pgn(annotations={(0, 0): DiagramAnnotation(lichess_link=False)}, lichess_links=True)
        self.assertNotIn("lichess.org", sem)

        com = self._pgn(annotations={(0, 0): DiagramAnnotation(lichess_link=True)}, lichess_links=False)
        self.assertIn("https://lichess.org/analysis/", com)

    def test_sem_declaracao_o_diagrama_segue_o_padrao(self) -> None:
        self.assertNotIn("lichess.org", self._pgn(lichess_links=False))
        self.assertIn("lichess.org", self._pgn(lichess_links=True))

    def test_o_link_carrega_a_fen_ja_anotada(self) -> None:
        """Link com a FEN antiga mandaria para o lichess uma posição que o PGN não tem."""
        pgn = self._pgn(annotations={(0, 0): DiagramAnnotation(move_number=24, lichess_link=True)})
        self.assertIn(lichess_analysis_url(f"{PLACEMENT} w - - 0 24"), pgn)

    def test_anotacao_de_outro_diagrama_nao_vaza(self) -> None:
        pgn = build_pgn_text(
            [_posicao(diagram=0), _posicao(diagram=1)],
            source_name="livro.pdf",
            annotations={(0, 1): DiagramAnnotation(move_number=30)},
        )
        self.assertIn("0 30", pgn)
        self.assertIn("0 1", pgn)


if __name__ == "__main__":
    unittest.main()


class ExtratoHumanoTests(unittest.TestCase):
    """O que se versiona da galeria, e por que só isso (S-115).

    `data/gallery/` são 13 MB fora do repositório por dois motivos que continuam de pé -- o
    `*.index.json` é derivado do PDF e o `<livro>.json` descreve o conteúdo de um livro
    protegido. Mas dentro dele há trabalho que **varredura nenhuma reconstrói**: a vez a jogar
    que alguém conferiu na legenda impressa e as 21 partidas escolhidas a mão (S-86).

    O crivo é o `filled_rule`/`filled_fields`, que já responde a pergunta campo a campo: o que
    a base preencheu volta com `cvoff-games --apply`; o que uma pessoa decidiu não volta.
    """

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.raiz = Path(self.pasta.name)
        self.addCleanup(self.pasta.cleanup)

    def _grava(self, livro: str, entradas: dict[tuple[int, int], DiagramAnnotation]) -> None:
        anotacoes = GalleryAnnotations(source_name=f"{livro}.pdf", entries=dict(entradas))
        save_annotations(Path(f"{livro}.pdf"), anotacoes, directory=self.raiz)

    def test_o_que_a_base_preencheu_fica_de_fora(self) -> None:
        da_base = DiagramAnnotation(
            move_number=24,
            side_to_move="b",
            headers={"White": "Karpov, Anatoly"},
            filled_from="Karpov x Korchnoi",
            filled_rule="date",
            filled_fields=("move_number", "side_to_move", "header:White"),
        )
        self.assertTrue(human_only(da_base).is_empty, "tudo isto volta com `cvoff-games --apply`")

    def test_o_que_a_pessoa_digitou_entra(self) -> None:
        """O caso misto, que é o comum: a base deu o lance e a pessoa conferiu a vez."""
        misto = DiagramAnnotation(
            move_number=24,
            side_to_move="b",
            headers={"White": "Karpov, Anatoly", "Event": "Merano"},
            filled_from="Karpov x Korchnoi",
            filled_rule="date",
            filled_fields=("move_number", "header:White"),
        )
        humano = human_only(misto)
        self.assertIsNone(humano.move_number, "o lance veio da base")
        self.assertEqual(humano.side_to_move, "b", "a vez, não")
        self.assertEqual(humano.headers, {"Event": "Merano"})

    def test_a_partida_escolhida_a_mao_leva_os_campos_dela_junto(self) -> None:
        """**A exceção que é o coração do item.** Com `filled_rule="human"`, o `filled_fields`
        lista o que a *escolha da pessoa* pôs (ver `choose_game`) -- ela olhou a lista de
        candidatas e disse qual era. Tratá-los como "da base" jogaria fora as 21 decisões mais
        caras do acervo."""
        escolhida = DiagramAnnotation(
            move_number=24,
            side_to_move="b",
            headers={"White": "Karpov, Anatoly"},
            filled_from="Karpov x Korchnoi",
            filled_rule="human",
            chosen_game="Karpov, Anatoly|Korchnoi, Viktor|1981.10.19||Merano",
            filled_fields=("move_number", "side_to_move", "header:White"),
        )
        humano = human_only(escolhida)
        self.assertEqual(humano.chosen_game, escolhida.chosen_game)
        self.assertEqual(humano.move_number, 24)
        self.assertEqual(humano.headers, {"White": "Karpov, Anatoly"})

    def test_anotacao_anterior_a_procedencia_por_campo_nao_e_chamada_de_humana(self) -> None:
        """`filled_from` cheio e `filled_fields` vazio só acontece numa anotação gravada antes
        da correção da S-72. Ali tudo *parece* humano, e chamar isso de humano encheria o
        extrato de headers da base -- e o `--import-human` os reescreveria como digitados, que
        é a procedência inventada que a S-94 existe para impedir."""
        antiga = DiagramAnnotation(
            move_number=24,
            side_to_move="b",
            headers={"White": "Karpov, Anatoly"},
            filled_from="Karpov x Korchnoi",
        )
        self.assertTrue(human_only(antiga).is_empty)

        self._grava("livro", {(0, 0): antiga})
        extrato = export_human(directory=self.raiz)
        self.assertEqual(extrato.records, [])
        self.assertEqual(extrato.unresolved, 1, "e o número aparece, senão o extrato pequeno mentiria")

    def test_a_escolha_humana_sobrevive_mesmo_na_anotacao_antiga(self) -> None:
        """A base nunca escolhe partida nem marca link: os dois passam sem crivo nenhum."""
        antiga = DiagramAnnotation(filled_from="x", chosen_game="A|B|||", lichess_link=True)
        humano = human_only(antiga)
        self.assertEqual(humano.chosen_game, "A|B|||")
        self.assertIs(humano.lichess_link, True)

    def test_a_ida_e_volta_preserva_o_que_a_pessoa_fez(self) -> None:
        """O critério de aceite: extrair, perder a galeria, restaurar."""
        self._grava(
            "livro",
            {
                (0, 0): DiagramAnnotation(side_to_move="w", headers={"Event": "Merano"}),
                (7, 2): DiagramAnnotation(chosen_game="A|B|1981||Merano", move_number=31),
            },
        )
        extrato = export_human(directory=self.raiz)
        caminho = write_human_extract(extrato.records, self.raiz / "humano.jsonl")

        for arquivo in self.raiz.glob("*.json"):
            arquivo.unlink()  # o disco falhou

        restore_human(read_human_extract(caminho), directory=self.raiz)

        voltou = load_annotations(Path("livro.pdf"), directory=self.raiz)
        self.assertEqual(voltou.get(0, 0).side_to_move, "w")
        self.assertEqual(voltou.get(0, 0).headers, {"Event": "Merano"})
        self.assertEqual(voltou.get(7, 2).chosen_game, "A|B|1981||Merano")
        self.assertEqual(voltou.get(7, 2).move_number, 31)

    def test_restaurar_sobre_uma_galeria_revarrida_tira_o_campo_da_procedencia_da_base(self) -> None:
        """**O que vem do extrato vence.** Se a pessoa digitou `Event` e a reconstrução o
        preencheu pela base, quem está com o livro na mão é ela (S-17) -- e o campo tem de sair
        do `filled_fields`, senão o PGN sairia dizendo `database` sobre o que ela digitou."""
        self._grava("livro", {(0, 0): DiagramAnnotation(headers={"Event": "Merano"})})
        extrato = export_human(directory=self.raiz)
        caminho = write_human_extract(extrato.records, self.raiz / "humano.jsonl")

        self._grava(
            "livro",
            {
                (0, 0): DiagramAnnotation(
                    headers={"Event": "Amsterdam"},
                    filled_from="a base",
                    filled_rule="date",
                    filled_fields=("header:Event",),
                )
            },
        )
        restore_human(read_human_extract(caminho), directory=self.raiz)

        voltou = load_annotations(Path("livro.pdf"), directory=self.raiz).get(0, 0)
        self.assertEqual(voltou.headers["Event"], "Merano")
        self.assertEqual(voltou.filled_fields, (), "deixou de ser da base")
        self.assertEqual(voltou.filled_from, "", "e sem campo da base sobrando, a evidência some")

    def test_o_que_a_base_preencheu_e_ninguem_contradisse_continua_la(self) -> None:
        """Restaurar não é apagar: só toca no que o registro traz."""
        self._grava("livro", {(0, 0): DiagramAnnotation(side_to_move="w")})
        caminho = write_human_extract(export_human(directory=self.raiz).records, self.raiz / "h.jsonl")
        self._grava(
            "livro",
            {
                (0, 0): DiagramAnnotation(
                    move_number=12,
                    headers={"Event": "Amsterdam"},
                    filled_from="a base",
                    filled_fields=("move_number", "header:Event"),
                    confirmed_from="3 partidas da base",
                )
            },
        )
        restore_human(read_human_extract(caminho), directory=self.raiz)

        voltou = load_annotations(Path("livro.pdf"), directory=self.raiz).get(0, 0)
        self.assertEqual(voltou.move_number, 12)
        self.assertEqual(voltou.headers, {"Event": "Amsterdam"})
        self.assertEqual(voltou.filled_fields, ("move_number", "header:Event"))
        self.assertEqual(voltou.confirmed_from, "3 partidas da base", "é afirmação sobre a leitura")

    def test_o_extrato_sai_ordenado_para_o_diff_ser_legivel(self) -> None:
        """Um arquivo versionado cuja ordem muda a cada execução produz um diff ilegível a
        cada commit -- mesma razão pela qual `to_dict` ordena as chaves."""
        self._grava("b", {(3, 0): DiagramAnnotation(side_to_move="w")})
        self._grava("a", {(9, 1): DiagramAnnotation(side_to_move="b"), (2, 0): DiagramAnnotation(move_number=5)})
        registros = export_human(directory=self.raiz).records
        self.assertEqual([(r["book"], r["at"]) for r in registros], [("a", "2.0"), ("a", "9.1"), ("b", "3.0")])

    def test_linha_estragada_nao_leva_o_extrato_junto(self) -> None:
        """Restaurar acontece depois de um desastre: é justamente quando se quer as outras."""
        caminho = self.raiz / "h.jsonl"
        caminho.write_text(
            '{"book": "livro", "at": "0.0", "side_to_move": "w"}\n{isto nao e json\n\n',
            encoding="utf-8",
        )
        with self.assertLogs("chess_diagram_ocr.gallery", level="WARNING"):
            registros = read_human_extract(caminho)
        self.assertEqual(len(registros), 1)

    def test_o_index_derivado_do_pdf_nao_entra(self) -> None:
        """`*.index.json` é posição e caminho de recorte: reconstrói-se varrendo o livro."""
        (self.raiz / "livro.index.json").write_text('{"diagrams": {}}', encoding="utf-8")
        self._grava("livro", {(0, 0): DiagramAnnotation(side_to_move="w")})
        self.assertEqual(export_human(directory=self.raiz).books, 1)
