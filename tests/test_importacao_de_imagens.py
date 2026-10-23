"""A importação de imagens de fora para o dataset (`importacao_de_imagens.py`).

O que se afirma aqui é o que decide o que entra no `labels.csv` sem ninguém olhar: o relatório do
ChessMeridaOCR lido imagem a imagem (com as duas suspeitas que ele mesmo carrega -- tabuleiro vazio
e FENs diferentes para a mesma imagem), a FEN da fonte só gravada quando o modelo concorda, o
andamento que sobrevive a reabrir a pasta, e a mesma imagem nunca gravada duas vezes.
"""

from __future__ import annotations

import csv
import unittest
from pathlib import Path

import cv2
import numpy as np
from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr import importacao_de_imagens as imp
from chess_diagram_ocr.importacao_de_imagens import IMPORTADO_COM_FEN, IMPORTADO_CONFERIDO
from chess_diagram_ocr.labels import OCR_ACEITO, OCR_CORRIGIDO

INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
FINAL = "8/8/4k3/8/8/4K3/8/8"


def diagrama(*, margem: int = 40, casa: int = 30, esquerda: int = 0) -> np.ndarray:
    """Um tabuleiro desenhado com moldura, margem em volta e, se pedido, uma faixa à esquerda.

    É o formato das imagens do Sigil: coordenadas ou número do diagrama fora da moldura.
    """
    lado = 8 * casa
    imagem = np.full((lado + 2 * margem, lado + 2 * margem + esquerda, 3), 255, np.uint8)
    x0 = margem + esquerda
    for linha in range(8):
        for coluna in range(8):
            if (linha + coluna) % 2:
                imagem[margem + linha * casa : margem + (linha + 1) * casa, x0 + coluna * casa : x0 + (coluna + 1) * casa] = 110
    cv2.rectangle(imagem, (x0 - 3, margem - 3), (x0 + lado + 2, margem + lado + 2), (0, 0, 0), 3)
    return imagem


def gravar_png(caminho: Path, imagem: np.ndarray) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(cv2.imencode(".png", imagem)[1].tobytes())
    return caminho


def artigo(src: str, fen: str, secao: str = "Text/Section0001.xhtml") -> str:
    return (
        f'<article class="chessocr-entry" data-chessocr-key="x:{fen.split()[0]}"><h3>{secao}</h3>'
        f'<img src="{src}" loading="lazy" alt="Tabuleiro"><p class="chessocr-fen"><strong>FEN:</strong> '
        f'<code>{fen}</code></p><p class="chessocr-links"><a href="https://lichess.org/x">Analisar</a></p></article>'
    )


def relatorio(pasta: Path, livro: str, execucoes: list[list[str]]) -> Path:
    corpo = "".join(
        f'<section class="chessocr-run"><h2>Execução {n}</h2>{"".join(artigos)}</section>'
        for n, artigos in enumerate(execucoes, start=1)
    )
    caminho = pasta / livro / "ChessMeridaOCR.html"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(f"<!doctype html><html><body><h1>ChessMeridaOCR</h1>{corpo}</body></html>", encoding="utf-8")
    return caminho


def pasta_do_sigil(caso: unittest.TestCase) -> Path:
    """Dois livros. No primeiro: uma imagem limpa, uma lida duas vezes igual, uma lida duas vezes
    diferente, uma com tabuleiro vazio e uma citada sem arquivo no disco."""
    raiz = pasta_temporaria(caso) / "Chess Images"
    for nome in ("a", "b", "c", "d"):
        gravar_png(raiz / "Livro Um" / "imagens" / f"{nome}.png", diagrama())
    gravar_png(raiz / "Livro Dois" / "imagens" / "e.png", diagrama(esquerda=60))
    relatorio(
        raiz,
        "Livro Um",
        [
            [
                artigo("imagens/a.png", f"{INICIAL} w KQkq - 0 1", "Seção A"),
                artigo("imagens/b.png", f"{FINAL} b - - 0 1"),
                artigo("imagens/c.png", f"{FINAL} w - - 0 1"),
                artigo("imagens/sumiu.png", f"{FINAL} w - - 0 1"),
            ],
            [
                artigo("imagens/b.png", f"{FINAL} b - - 0 1"),
                artigo("imagens/c.png", f"{INICIAL} w - - 0 1"),
                artigo("imagens/d.png", "8/8/8/8/8/8/8/8 w - - 0 1"),
            ],
        ],
    )
    relatorio(raiz, "Livro Dois", [[artigo("imagens/e.png", f"{FINAL} w - - 0 1")]])
    return raiz


def linhas_do_csv(caminho: Path) -> list[dict[str, str]]:
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


class RelatorioDoSigilTests(unittest.TestCase):
    def test_uma_entrada_por_imagem_com_livro_lado_e_secao(self) -> None:
        lote = imp.ler_relatorios_do_chessmeridaocr(pasta_do_sigil(self))
        por_nome = {Path(item.imagem).name: item for item in lote.itens}

        self.assertEqual(sorted(por_nome), ["a.png", "b.png", "c.png", "d.png", "e.png"])
        self.assertEqual(lote.origem, imp.COM_FEN)
        self.assertEqual(por_nome["a.png"].livro, "Livro Um")
        self.assertEqual(por_nome["a.png"].legenda, "Seção A")
        self.assertEqual(por_nome["a.png"].lado, "w")
        self.assertEqual(por_nome["b.png"].lado, "b")
        self.assertEqual(por_nome["e.png"].livro, "Livro Dois")
        self.assertEqual(por_nome["e.png"].indice, 1)

    def test_imagem_citada_sem_arquivo_e_contada_e_nao_importada(self) -> None:
        lote = imp.ler_relatorios_do_chessmeridaocr(pasta_do_sigil(self))
        self.assertEqual(lote.ausentes, 1)
        self.assertIn("1 citadas no relatório sem imagem no disco", lote.resumo())

    def test_as_suspeitas_do_proprio_relatorio_viram_motivo(self) -> None:
        por_nome = {Path(i.imagem).name: i for i in imp.ler_relatorios_do_chessmeridaocr(pasta_do_sigil(self)).itens}

        self.assertEqual(por_nome["a.png"].motivos, ())
        self.assertEqual(por_nome["b.png"].motivos, (), "lida duas vezes igual não é suspeita")
        self.assertEqual(por_nome["c.png"].motivos, ("o relatório tem 2 FENs diferentes para esta imagem",))
        self.assertEqual(por_nome["c.png"].fen_da_fonte.split()[0], INICIAL, "vale a execução mais nova")
        self.assertEqual(por_nome["d.png"].motivos, ("o relatório deu tabuleiro vazio",))

    def test_a_pasta_de_um_livro_so_tambem_abre(self) -> None:
        lote = imp.ler_relatorios_do_chessmeridaocr(pasta_do_sigil(self) / "Livro Dois")
        self.assertEqual([item.imagem for item in lote.itens], ["imagens/e.png"])
        self.assertEqual(lote.itens[0].livro, "Livro Dois")

    def test_pasta_sem_relatorio_avisa(self) -> None:
        with self.assertRaises(FileNotFoundError):
            imp.ler_relatorios_do_chessmeridaocr(pasta_temporaria(self))


class PastaSemFenTests(unittest.TestCase):
    def test_le_as_subpastas_pula_as_ocultas_e_usa_o_index_csv(self) -> None:
        raiz = pasta_temporaria(self) / "jbc"
        gravar_png(raiz / "Revista-1925" / "n1" / "p001_b01.png", diagrama(margem=0))
        gravar_png(raiz / "Revista-1925" / "n1" / "p002_b01.png", diagrama(margem=0))
        gravar_png(raiz / ".git" / "lfs" / "objeto.png", diagrama(margem=0))
        (raiz / "README.md").write_text("x", encoding="utf-8")
        (raiz / "index.csv").write_text(
            "png,source,title,year,to_move,caption\n"
            "Revista-1925/n1/p001_b01.png,jbc,Revista,1925,b,Pretas jogam e ganham\n",
            encoding="utf-8",
        )

        lote = imp.ler_pasta_de_imagens(raiz)

        self.assertEqual([item.imagem for item in lote.itens], ["Revista-1925/n1/p001_b01.png", "Revista-1925/n1/p002_b01.png"])
        primeira, segunda = lote.itens
        self.assertEqual((primeira.livro, primeira.lado, primeira.legenda), ("Revista 1925", "b", "Pretas jogam e ganham"))
        self.assertEqual((segunda.livro, segunda.lado), ("Revista-1925", ""))
        self.assertTrue(all(not item.fen_da_fonte for item in lote.itens))


class AndamentoTests(unittest.TestCase):
    def test_reabrir_a_pasta_mantem_o_andamento_e_acrescenta_o_novo(self) -> None:
        raiz = pasta_do_sigil(self)
        lotes = pasta_temporaria(self)
        lote, arquivo = imp.abrir_lote(raiz, imp.COM_FEN, diretorio=lotes)
        imp.marcar(lote, 0, imp.DESCARTADO)
        lote.salvar(arquivo)
        gravar_png(raiz / "Livro Dois" / "imagens" / "f.png", diagrama())
        relatorio(
            raiz,
            "Livro Dois",
            [[artigo("imagens/e.png", f"{FINAL} w - - 0 1"), artigo("imagens/f.png", f"{FINAL} w - - 0 1")]],
        )

        de_novo, mesmo_arquivo = imp.abrir_lote(raiz, imp.COM_FEN, diretorio=lotes)

        self.assertEqual(mesmo_arquivo, arquivo)
        self.assertEqual(de_novo.itens[0].status, imp.DESCARTADO)
        self.assertIn("Livro Dois/imagens/f.png", [item.imagem for item in de_novo.itens])

    def test_o_arquivo_do_andamento_e_por_pasta_e_por_origem(self) -> None:
        lotes = pasta_temporaria(self)
        a = imp.caminho_do_lote("C:/x/Chess Images", imp.COM_FEN, diretorio=lotes)
        self.assertNotEqual(a, imp.caminho_do_lote("C:/y/Chess Images", imp.COM_FEN, diretorio=lotes))
        self.assertNotEqual(a, imp.caminho_do_lote("C:/x/Chess Images", imp.SEM_FEN, diretorio=lotes))
        self.assertTrue(a.name.startswith("Chess_Images_com-fen_"))


class ConcordanciaTests(unittest.TestCase):
    def item(self, **campos: object) -> imp.ItemDeImportacao:
        base: dict[str, object] = {
            "imagem": "a.png", "livro": "L", "indice": 1,
            "fen_da_fonte": f"{FINAL} w - - 0 1", "fen_do_modelo": FINAL,
        }
        base.update(campos)
        return imp.ItemDeImportacao(**base)  # type: ignore[arg-type]

    def test_concorda_so_com_a_mesma_posicao_legal_e_sem_aviso(self) -> None:
        self.assertTrue(imp.concorda(self.item()))
        self.assertFalse(imp.concorda(self.item(fen_do_modelo=INICIAL)))
        self.assertFalse(imp.concorda(self.item(fen_do_modelo="")))
        self.assertFalse(imp.concorda(self.item(motivos=("o relatório deu tabuleiro vazio",))))
        sem_rei = "8/8/8/8/8/8/8/4K3"
        self.assertFalse(imp.concorda(self.item(fen_da_fonte=f"{sem_rei} w - - 0 1", fen_do_modelo=sem_rei)))

    def test_casas_diferentes(self) -> None:
        self.assertEqual(imp.casas_diferentes(FINAL, FINAL), [])
        self.assertEqual(imp.casas_diferentes(FINAL, "8/8/4k3/8/8/3K4/8/8"), [43, 44])

    def test_rota_da_conferencia(self) -> None:
        com_leitura = self.item()
        self.assertEqual(imp.rota_da_conferencia(com_leitura, f"{FINAL} b - - 0 1"), OCR_ACEITO)
        self.assertEqual(imp.rota_da_conferencia(com_leitura, f"{INICIAL} w - - 0 1"), OCR_CORRIGIDO)
        self.assertEqual(imp.rota_da_conferencia(self.item(fen_do_modelo=""), FINAL), IMPORTADO_CONFERIDO)


class RecorteTests(unittest.TestCase):
    def test_tira_a_margem_e_a_faixa_ao_lado(self) -> None:
        tabuleiro, usado = imp.recortar(diagrama(margem=25, esquerda=40))
        self.assertEqual(usado, imp.RECORTE_DETECTADO)
        self.assertEqual(tabuleiro.shape, (800, 800, 3))

    def test_forcar_a_imagem_inteira(self) -> None:
        tabuleiro, usado = imp.recortar(diagrama(), imp.RECORTE_INTEIRA)
        self.assertEqual(usado, imp.RECORTE_INTEIRA)
        self.assertEqual(tabuleiro.shape, (800, 800, 3))

    def test_quadro_pequeno_demais_nao_e_o_tabuleiro(self) -> None:
        quadro = np.array([[0, 0], [30, 0], [30, 30], [0, 30]])
        self.assertLess(imp._fracao_do_quadro(quadro, (300, 300, 3)), imp.FRACAO_MINIMA_DO_QUADRO)
        self.assertEqual(imp._fracao_do_quadro(None, (300, 300, 3)), 0.0)


class ImportarOsQueConcordamTests(unittest.TestCase):
    def test_grava_so_o_que_o_modelo_confirma_e_nao_grava_duas_vezes(self) -> None:
        raiz = pasta_do_sigil(self)
        dados = pasta_temporaria(self)
        csv_path, samples = dados / "labels.csv", dados / "samples"
        lote, _arquivo = imp.abrir_lote(raiz, imp.COM_FEN, diretorio=dados / "importacao")
        # O modelo de mentira lê a posição final em toda imagem: concorda com b.png e e.png.
        conta = imp.importar_os_que_concordam(
            lote, ler=lambda _tabuleiro: FINAL, csv_path=csv_path, samples_dir=samples, corrected_by=IMPORTADO_COM_FEN
        )

        self.assertEqual(conta["salvos"], 2)
        self.assertEqual(conta["discordam"], 1)
        self.assertEqual(conta["com_aviso"], 2)
        por_nome = {Path(item.imagem).name: item for item in lote.itens}
        self.assertEqual(por_nome["a.png"].status, imp.PENDENTE)
        self.assertEqual(por_nome["a.png"].motivos, ("o modelo leu outra posição (34 casas diferentes)",))
        self.assertEqual(por_nome["a.png"].fen_do_modelo, FINAL, "a leitura fica guardada para a conferência")
        self.assertEqual(por_nome["b.png"].status, imp.SALVO)

        linhas = linhas_do_csv(csv_path)
        self.assertEqual(len(linhas), 2)
        self.assertEqual({linha["corrected_by"] for linha in linhas}, {IMPORTADO_COM_FEN})
        self.assertEqual(
            sorted(linha["source_pdf"] for linha in linhas), ["ChessMeridaOCR: Livro Dois", "ChessMeridaOCR: Livro Um"]
        )
        self.assertEqual({linha["detection_source"] for linha in linhas}, {"importacao-detectado"})
        b = next(linha for linha in linhas if linha["source_pdf"] == "ChessMeridaOCR: Livro Um")
        self.assertEqual((b["fen"], b["side_to_move"]), (f"{FINAL} b - - 0 1", "b"))
        self.assertTrue((samples / b["filename"]).exists())

        de_novo = imp.importar_os_que_concordam(
            lote, ler=lambda _tabuleiro: FINAL, csv_path=csv_path, samples_dir=samples, corrected_by=IMPORTADO_COM_FEN
        )
        self.assertEqual(de_novo["salvos"], 0)
        self.assertEqual(len(linhas_do_csv(csv_path)), 2)

    def test_cancelar_para_e_o_andamento_fica_gravado(self) -> None:
        raiz = pasta_do_sigil(self)
        dados = pasta_temporaria(self)
        lote, arquivo = imp.abrir_lote(raiz, imp.COM_FEN, diretorio=dados)
        gravacoes: list[int] = []
        conta = imp.importar_os_que_concordam(
            lote,
            ler=lambda _tabuleiro: FINAL,
            csv_path=dados / "labels.csv",
            samples_dir=dados / "samples",
            corrected_by=IMPORTADO_COM_FEN,
            cancelar=lambda: True,
            gravar_andamento=lambda: gravacoes.append(1),
        )
        self.assertEqual(sum(conta.values()), 0)
        self.assertEqual(gravacoes, [1])
        self.assertFalse(arquivo.exists(), "quem grava o arquivo é quem passou gravar_andamento")

    def test_gravar_duas_vezes_a_mesma_imagem_e_recusado(self) -> None:
        raiz = pasta_do_sigil(self)
        dados = pasta_temporaria(self)
        lote = imp.ler_relatorios_do_chessmeridaocr(raiz)
        tabuleiro, usado = imp.recortar(imp.ler_imagem(lote.caminho_da_imagem(lote.itens[1])))
        argumentos = {
            "lado": "b", "recorte": usado, "csv_path": dados / "labels.csv",
            "samples_dir": dados / "samples", "corrected_by": OCR_ACEITO,
        }
        imp.gravar_item(lote, 1, tabuleiro, f"{FINAL} b - - 0 1", **argumentos)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            imp.gravar_item(lote, 1, tabuleiro, f"{FINAL} b - - 0 1", **argumentos)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            imp.marcar(lote, 1, imp.DESCARTADO)


if __name__ == "__main__":
    unittest.main()
