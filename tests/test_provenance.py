"""Recuperação de procedência por hash perceptual (S-52).

O item promete uma coisa e recusa outra, e os dois lados têm teste aqui. Promete **reportar a
taxa**: `MatchReport` traz o histograma de distância, e não só a contagem acima do limiar.
Recusa **prometer 100%**: amostra que não está no acervo não casa, e casamento ambíguo entre
dois livros é descartado em vez de escolhido no par ou ímpar.

O que não é testado aqui, e não dá para ser: a taxa real sobre os 3.195 órfãos. Ela exige o
índice dos 27 PDFs, que são horas de CPU -- ver o ROADMAP.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from chess_diagram_ocr.labels import DatasetEntry, LabelStore
from chess_diagram_ocr.provenance import (
    AMBIGUITY_MARGIN,
    IndexEntry,
    ProvenanceIndex,
    ProvenanceMatch,
    apply_matches,
    build_index,
    hash_board_rgb,
    hash_image_file,
    match_samples,
    samples_without_provenance,
)
from chess_diagram_ocr.splits import groups_by_book

LEGAL = "8/8/8/8/8/8/4K3/4k3 w - - 0 1"


def board_image(seed: int, size: int = 800) -> np.ndarray:
    """Um tabuleiro sintético: grade 8×8 mais manchas pseudoaleatórias fazendo de peças.

    A grade importa. Um ruído puro daria hashes bem separados e o teste passaria sem exercer
    o problema real -- que é justamente diagramas de xadrez serem parecidos entre si, e foi
    o que levou a auditoria a medir que um dHash 8×8 é degenerado aqui.
    """
    rng = np.random.default_rng(seed)
    passo = size // 8
    imagem = np.zeros((size, size, 3), dtype=np.uint8)
    for linha in range(8):
        for coluna in range(8):
            clara = (linha + coluna) % 2 == 0
            imagem[linha * passo : (linha + 1) * passo, coluna * passo : (coluna + 1) * passo] = (
                235 if clara else 130
            )
            if rng.random() < 0.35:
                centro = (coluna * passo + passo // 2, linha * passo + passo // 2)
                cor = int(rng.integers(0, 2)) * 255
                cv2.circle(imagem, centro, passo // 3, (cor, cor, cor), -1)
    return imagem


def recropped(board_rgb: np.ndarray, margem: int = 6) -> np.ndarray:
    """A mesma imagem com o enquadramento um pouco diferente.

    É o caso que de fato acontece: a amostra foi salva pelo detector de julho e o índice é
    construído pelo detector de agosto, que a S-38a mudou. O dHash tem de sobreviver a isso,
    e é o que este ajudante verifica.
    """
    altura, largura = board_rgb.shape[:2]
    cortada = board_rgb[margem : altura - margem, margem : largura - margem]
    return cv2.resize(cortada, (largura, altura))


def index_of(*specs: tuple[str, int, int, np.ndarray]) -> ProvenanceIndex:
    return ProvenanceIndex(
        entries=[
            IndexEntry(
                source_pdf=livro,
                source_page=pagina,
                source_diagram=diagrama,
                detection_source="embedded",
                hash_hex=hash_board_rgb(imagem),
            )
            for livro, pagina, diagrama, imagem in specs
        ],
        pages_by_book={livro: pagina for livro, pagina, _d, _i in specs},
    )


class HashTests(unittest.TestCase):
    def test_a_mesma_imagem_da_o_mesmo_hash(self) -> None:
        imagem = board_image(1)
        self.assertEqual(hash_board_rgb(imagem), hash_board_rgb(imagem.copy()))

    def test_imagens_diferentes_dao_hashes_diferentes(self) -> None:
        self.assertNotEqual(hash_board_rgb(board_image(1)), hash_board_rgb(board_image(2)))

    def test_o_arquivo_em_disco_casa_com_a_imagem_em_memoria(self) -> None:
        """A ponte entre os dois lados: o índice hash RGB, a amostra é lida do PNG em BGR.

        Se a conversão estivesse errada, os pesos de R e B na conversão para cinza sairiam
        trocados e **nada** casaria -- sem quebrar nada visivelmente.
        """
        imagem = board_image(3)
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "board.png"
            cv2.imwrite(str(caminho), cv2.cvtColor(imagem, cv2.COLOR_RGB2BGR))
            self.assertEqual(hash_image_file(caminho), hash_board_rgb(imagem))

    def test_arquivo_que_nao_abre_devolve_none(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            self.assertIsNone(hash_image_file(Path(pasta) / "nao_existe.png"))


class IndexPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.caminho = Path(self.pasta.name) / "index.jsonl"

    def test_round_trip(self) -> None:
        original = index_of(("a.pdf", 10, 1, board_image(1)), ("b.pdf", 20, 2, board_image(2)))
        original.save(self.caminho)
        lido = ProvenanceIndex.load(self.caminho)

        self.assertEqual(lido.entries, original.entries)
        self.assertEqual(lido.pages_by_book, original.pages_by_book)
        self.assertTrue(lido.built_at)

    def test_arquivo_ausente_e_indice_vazio(self) -> None:
        self.assertEqual(ProvenanceIndex.load(self.caminho).entries, [])

    def test_linha_rasgada_no_fim_nao_leva_as_anteriores(self) -> None:
        """O formato JSONL existe para isso -- é a mesma razão do `.partial.jsonl` da S-24."""
        index_of(("a.pdf", 10, 1, board_image(1)), ("a.pdf", 11, 1, board_image(2))).save(self.caminho)
        with self.caminho.open("a", encoding="utf-8") as handle:
            handle.write('{"source_pdf": "a.pdf", "source_pa')

        self.assertEqual(len(ProvenanceIndex.load(self.caminho).entries), 2)

    def test_cabecalho_ilegivel_e_erro(self) -> None:
        self.caminho.write_text("isto nao e json\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            ProvenanceIndex.load(self.caminho)

    def test_without_book_tira_o_livro_e_a_contagem(self) -> None:
        indice = index_of(("a.pdf", 10, 1, board_image(1)), ("b.pdf", 20, 1, board_image(2)))
        limpo = indice.without_book("a.pdf")

        self.assertEqual([e.source_pdf for e in limpo.entries], ["b.pdf"])
        self.assertEqual(set(limpo.pages_by_book), {"b.pdf"})

    def test_book_ids_separa_os_livros(self) -> None:
        indice = index_of(("a.pdf", 1, 1, board_image(1)), ("b.pdf", 1, 1, board_image(2)))
        ids = indice.book_ids()
        self.assertEqual(len(set(ids.tolist())), 2)


class MatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.samples = Path(self.pasta.name) / "samples"
        self.samples.mkdir()

    def save_sample(self, name: str, image_rgb: np.ndarray) -> str:
        cv2.imwrite(str(self.samples / name), cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR))
        return name

    def test_a_mesma_imagem_casa_com_distancia_zero(self) -> None:
        imagem = board_image(1)
        indice = index_of(("Kemeri.pdf", 15, 2, imagem), ("Outro.pdf", 3, 1, board_image(99)))
        nome = self.save_sample("a.png", imagem)

        report = match_samples(self.samples, indice, [nome])

        self.assertEqual(report.matched, 1)
        casamento = report.matches[0]
        self.assertEqual(casamento.distance, 0)
        self.assertEqual((casamento.source_pdf, casamento.source_page, casamento.source_diagram), ("Kemeri.pdf", 15, 2))

    def test_enquadramento_diferente_ainda_casa(self) -> None:
        """O caso real: a amostra é de julho e o índice é do detector de agosto (S-38a)."""
        imagem = board_image(4)
        indice = index_of(("Kemeri.pdf", 15, 1, imagem), ("Outro.pdf", 3, 1, board_image(98)))
        nome = self.save_sample("a.png", recropped(imagem))

        report = match_samples(self.samples, indice, [nome])

        self.assertEqual(report.matched, 1, f"distâncias vistas: {report.distances}")
        self.assertEqual(report.matches[0].source_pdf, "Kemeri.pdf")

    def test_imagem_que_nao_esta_no_acervo_nao_casa(self) -> None:
        indice = index_of(("Kemeri.pdf", 15, 1, board_image(1)))
        nome = self.save_sample("a.png", board_image(77))

        report = match_samples(self.samples, indice, [nome])

        self.assertEqual(report.matched, 0)
        self.assertEqual(report.considered, 1)
        # E o histograma registra o que foi visto: e ele que diz se o limiar esta no lugar.
        self.assertEqual(sum(report.distances.values()), 1)

    def test_o_mesmo_diagrama_em_dois_livros_e_ambiguo_e_fica_de_fora(self) -> None:
        """Procedência errada é pior que vazia, porque parece um dado."""
        imagem = board_image(5)
        indice = index_of(("A.pdf", 1, 1, imagem), ("B.pdf", 2, 1, imagem))
        nome = self.save_sample("a.png", imagem)

        report = match_samples(self.samples, indice, [nome])

        self.assertEqual(report.matched, 0)
        self.assertEqual(report.ambiguous, 1)

    def test_o_mesmo_diagrama_duas_vezes_no_mesmo_livro_nao_e_ambiguo(self) -> None:
        """O `Reinfeld` repete exercícios entre problemas e soluções, e as duas respondem
        "veio deste livro" -- que é o que a S-07 precisa saber."""
        imagem = board_image(6)
        indice = index_of(("Reinfeld.pdf", 40, 1, imagem), ("Reinfeld.pdf", 250, 3, imagem))
        nome = self.save_sample("a.png", imagem)

        report = match_samples(self.samples, indice, [nome])

        self.assertEqual(report.matched, 1)
        self.assertEqual(report.ambiguous, 0)
        self.assertEqual(report.matches[0].source_pdf, "Reinfeld.pdf")

    def test_ambiguidade_e_pela_folga_e_nao_pela_distancia(self) -> None:
        casamento = ProvenanceMatch(
            filename="a.png",
            source_pdf="A.pdf",
            source_page=1,
            source_diagram=1,
            detection_source="embedded",
            distance=0,
            runner_up=AMBIGUITY_MARGIN - 1,
        )
        self.assertTrue(casamento.is_ambiguous)
        self.assertFalse(
            ProvenanceMatch(**{**casamento.__dict__, "runner_up": AMBIGUITY_MARGIN}).is_ambiguous
        )

    def test_imagem_ilegivel_e_contada_e_nao_derruba_o_resto(self) -> None:
        imagem = board_image(7)
        indice = index_of(("Kemeri.pdf", 1, 1, imagem))
        bom = self.save_sample("bom.png", imagem)

        report = match_samples(self.samples, indice, ["sumiu.png", bom])

        self.assertEqual(report.unreadable, 1)
        self.assertEqual(report.matched, 1)
        self.assertEqual(report.considered, 2)

    def test_indice_vazio_nao_levanta(self) -> None:
        report = match_samples(self.samples, ProvenanceIndex(), ["a.png"])
        self.assertEqual(report.matched, 0)

    def test_a_taxa_e_por_livro_no_relatorio(self) -> None:
        primeira, segunda = board_image(8), board_image(9)
        indice = index_of(("A.pdf", 1, 1, primeira), ("B.pdf", 1, 1, segunda))
        nomes = [self.save_sample("a.png", primeira), self.save_sample("b.png", segunda)]

        report = match_samples(self.samples, indice, nomes)

        self.assertEqual(report.by_book, {"A.pdf": 1, "B.pdf": 1})
        self.assertAlmostEqual(report.rate, 1.0)
        self.assertEqual(json.loads(json.dumps(report.as_dict()))["matched"], 2)


class ApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.store = LabelStore(Path(self.pasta.name) / "labels.csv")
        self.store.rewrite(
            [
                DatasetEntry(filename="orfa.png", fen=LEGAL),
                DatasetEntry(filename="com_origem.png", fen=LEGAL, source_pdf="Verdadeiro.pdf", source_page="7"),
                DatasetEntry(filename="outra_orfa.png", fen=LEGAL, detection_source="contour"),
            ]
        )

    def match(self, filename: str, livro: str = "Casado.pdf") -> ProvenanceMatch:
        return ProvenanceMatch(
            filename=filename,
            source_pdf=livro,
            source_page=99,
            source_diagram=2,
            detection_source="embedded",
            distance=1,
        )

    def test_preenche_a_orfa(self) -> None:
        self.assertEqual(apply_matches(self.store, [self.match("orfa.png")], backup=False), 1)

        lidas = {e.filename: e for e in self.store.read()}
        self.assertEqual(lidas["orfa.png"].source_pdf, "Casado.pdf")
        self.assertEqual(lidas["orfa.png"].source_page, "99")
        self.assertEqual(lidas["orfa.png"].detection_source, "embedded")

    def test_nao_sobrescreve_procedencia_de_verdade(self) -> None:
        """As 46 vieram da `RecognitionOrigin` na hora da gravação -- fonte melhor que esta."""
        self.assertEqual(apply_matches(self.store, [self.match("com_origem.png")], backup=False), 0)
        lidas = {e.filename: e for e in self.store.read()}
        self.assertEqual(lidas["com_origem.png"].source_pdf, "Verdadeiro.pdf")

    def test_overwrite_sobrescreve_quando_pedido(self) -> None:
        self.assertEqual(
            apply_matches(self.store, [self.match("com_origem.png")], overwrite=True, backup=False), 1
        )
        lidas = {e.filename: e for e in self.store.read()}
        self.assertEqual(lidas["com_origem.png"].source_pdf, "Casado.pdf")

    def test_detection_source_existente_e_preservada_mesmo_com_overwrite(self) -> None:
        """Ela descreve como *aquela* amostra foi achada; o índice descreve como seria hoje."""
        apply_matches(self.store, [self.match("outra_orfa.png")], overwrite=True, backup=False)
        lidas = {e.filename: e for e in self.store.read()}
        self.assertEqual(lidas["outra_orfa.png"].detection_source, "contour")

    def test_casamento_de_arquivo_que_saiu_do_csv_e_ignorado(self) -> None:
        self.assertEqual(apply_matches(self.store, [self.match("fantasma.png")], backup=False), 0)

    def test_backup_antes_de_escrever_em_3195_linhas(self) -> None:
        apply_matches(self.store, [self.match("orfa.png")], backup=True)
        copias = list(self.store.path.parent.glob("labels.csv.bak-*"))
        self.assertEqual(len(copias), 1)

    def test_uma_gravacao_so_para_todos_os_casamentos(self) -> None:
        """Sem a `transaction` da S-51 seriam 3.195 reescritas do arquivo inteiro."""
        with patch("chess_diagram_ocr.labels.atomic_write_bytes") as escrita:
            apply_matches(
                self.store,
                [self.match("orfa.png"), self.match("outra_orfa.png")],
                backup=False,
            )
        self.assertEqual(escrita.call_count, 1)

    def test_samples_without_provenance_lista_so_as_orfas(self) -> None:
        self.assertEqual(samples_without_provenance(self.store), ["orfa.png", "outra_orfa.png"])


class BuildIndexTests(unittest.TestCase):
    """O laço de indexação, com a detecção substituída: o que se testa aqui é a contabilidade."""

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.pdf_dir = Path(self.pasta.name)
        for nome in ("A.pdf", "B.pdf"):
            (self.pdf_dir / nome).write_bytes(b"%PDF-1.4 fake")

    def fake_candidate(self, seed: int) -> object:
        class _Candidato:
            board_rgb = board_image(seed)
            source = "embedded"

        return _Candidato()

    def run_build(self, **kwargs: object) -> ProvenanceIndex:
        with (
            patch("chess_diagram_ocr.pdf_io.get_pdf_page_count", return_value=3),
            patch("chess_diagram_ocr.pdf_io.render_pdf_page", return_value=np.zeros((8, 8, 3), np.uint8)),
            patch(
                "chess_diagram_ocr.detection.detect_diagrams_in_pdf_page",
                side_effect=lambda _p, page, _rgb, **_k: [self.fake_candidate(page)],
            ),
        ):
            return build_index(self.pdf_dir, **kwargs)  # type: ignore[arg-type]

    def test_indexa_todos_os_livros_e_conta_as_paginas(self) -> None:
        indice = self.run_build()

        self.assertEqual(indice.pages_by_book, {"A.pdf": 3, "B.pdf": 3})
        self.assertEqual(len(indice.entries), 6)
        self.assertEqual({e.source_page for e in indice.entries}, {1, 2, 3})

    def test_um_livro_por_vez(self) -> None:
        indice = self.run_build(books=["A.pdf"])
        self.assertEqual(set(indice.pages_by_book), {"A.pdf"})

    def test_reindexar_um_livro_substitui_em_vez_de_duplicar(self) -> None:
        primeiro = self.run_build(books=["A.pdf"])
        segundo = self.run_build(books=["A.pdf"], base=primeiro)

        self.assertEqual(len(segundo.entries), 3)

    def test_teto_de_paginas_para_ensaiar(self) -> None:
        indice = self.run_build(page_limit=1)
        self.assertEqual(indice.pages_by_book, {"A.pdf": 1, "B.pdf": 1})

    def test_cancelar_devolve_o_que_ja_foi_indexado(self) -> None:
        """Uma varredura interrompida no livro 20 de 27 não pode desperdiçar os 19."""
        cancel = threading.Event()
        cancel.set()
        indice = self.run_build(cancel_event=cancel)
        self.assertEqual(indice.entries, [])

    def test_misturar_dpi_diferente_e_recusado(self) -> None:
        """O índice precisa ver o diagrama como o detector o viu; outro DPI é outro recorte."""
        base = ProvenanceIndex(dpi=150)
        with self.assertRaises(ValueError):
            build_index(self.pdf_dir, dpi=220, base=base)


class GroupsByBookTests(unittest.TestCase):
    """O que a procedência destrava: o split agrupado por livro (S-07)."""

    def test_agrupa_por_livro(self) -> None:
        grupos = groups_by_book({"a.png": "X.pdf", "b.png": "X.pdf", "c.png": "Y.pdf", "d.png": "Y.pdf"})
        self.assertEqual(grupos, [["a.png", "b.png"], ["c.png", "d.png"]])

    def test_amostra_sem_procedencia_fica_de_fora(self) -> None:
        """Sem `source_pdf` ela continua com split individual, que é o comportamento de hoje."""
        self.assertEqual(groups_by_book({"a.png": "", "b.png": "X.pdf", "c.png": "X.pdf"}), [["b.png", "c.png"]])

    def test_livro_com_uma_amostra_so_nao_vira_grupo(self) -> None:
        self.assertEqual(groups_by_book({"a.png": "X.pdf"}), [])

    def test_o_grupo_faz_o_livro_inteiro_cair_no_mesmo_split(self) -> None:
        from chess_diagram_ocr.splits import compute_splits

        procedencia = {f"{i}.png": "X.pdf" for i in range(40)}
        splits = compute_splits(procedencia.keys(), groups=groups_by_book(procedencia))

        self.assertEqual(len(set(splits.values())), 1)


if __name__ == "__main__":
    unittest.main()
