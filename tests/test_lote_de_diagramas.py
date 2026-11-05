"""O lote de diagramas sem janela: o nome do arquivo, as escolhas, a pele e a gravação (S-544).

O que a janela decide -- prévia, pasta, thread -- é de `tests/test_qt_lote_de_diagramas.py`.
Aqui está a decisão pura de `ui/lote_de_diagramas.py` e a travessia de disco de
`diagramas_em_lote.py`, que grava igual chamada de um teste ou de um comando de linha.
"""

from __future__ import annotations

import threading
import unittest
from pathlib import Path

import chess
import chess.pgn
from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr.diagramas_em_lote import (
    bytes_do_item,
    frase_de_disco,
    frase_do_relatorio,
    gravar_lote,
)
from chess_diagram_ocr.estudo import Ancora, Estudo, PosicaoDeEstudo
from chess_diagram_ocr.ui import conjuntos, tokens
from chess_diagram_ocr.ui.lote_de_diagramas import (
    MARGEM_MAXIMA,
    PADRAO,
    PNG,
    SVG,
    TAMANHO_MAXIMO,
    TAMANHO_MINIMO,
    UMA_TINTA,
    ItemDoLote,
    Opcoes,
    cores_da_pele,
    da_galeria,
    de_estudos,
    do_estudo,
    frase_do_lote,
    nomes_do_lote,
)

VAZIO = "8/8/8/8/8/8/8/K6k w - - 0 1"
INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"


def _item(**campos: object) -> ItemDoLote:
    return ItemDoLote(fen=str(campos.pop("fen", VAZIO)), **campos)  # type: ignore[arg-type]


class NomeDoArquivoTests(unittest.TestCase):
    """O nome é o que faz o arquivo achável seis meses depois -- e o que não pode colidir."""

    def test_o_numero_vem_com_zero_a_esquerda_na_largura_do_maior(self) -> None:
        """`ex1` e `ex10` num gerenciador de arquivos aparecem 1, 10, 100, 11: quem arrasta 500
        diagramas para a diagramação na ordem em que os vê põe o 100 entre o 10 e o 11."""
        itens = [_item(livro="Livro", pagina=p) for p in (1, 10, 100)]
        self.assertEqual(
            ("Livro_p001.png", "Livro_p010.png", "Livro_p100.png"), nomes_do_lote(itens)
        )

    def test_dois_nomes_iguais_nao_viram_um_arquivo_so(self) -> None:
        """No Windows e no macOS o segundo apagaria o primeiro **em silêncio**, que é a pior
        forma de perder meia hora de trabalho."""
        itens = [_item(livro="Livro", pagina=1, diagrama=1)] * 3
        self.assertEqual(
            ("Livro_p1_d1.png", "Livro_p1_d1-2.png", "Livro_p1_d1-3.png"), nomes_do_lote(itens)
        )

    def test_a_colisao_e_comparada_sem_maiuscula(self) -> None:
        """`A.png` e `a.png` são o mesmo arquivo nos dois sistemas em que este programa roda."""
        nomes = nomes_do_lote([_item(livro="ABC"), _item(livro="abc")])
        self.assertEqual(len({nome.casefold() for nome in nomes}), 2, nomes)

    def test_o_acento_sai_e_a_letra_fica(self) -> None:
        """Sem acento **de propósito**: o lote é consumido por um programa de diagramação, e
        caminho com acento ainda quebra em `\\includegraphics` e em `.zip` aberto noutra máquina."""
        self.assertEqual(("Prokes.png",), nomes_do_lote([_item(livro="Prokeš")]))

    def test_caractere_que_o_windows_recusa_nao_chega_ao_disco(self) -> None:
        self.assertEqual(("a-b-c.png",), nomes_do_lote([_item(livro='a:b/c?')]))

    def test_nome_de_dispositivo_do_ms_dos_ganha_sufixo(self) -> None:
        """`CON.png` não é criável no Windows, e nem com outra extensão. Um livro `Aux.pdf` existe."""
        self.assertEqual(("Aux-1.png",), nomes_do_lote([_item(livro="Aux")]))

    def test_sem_procedencia_o_titulo_nomeia_e_sem_titulo_ha_um_padrao(self) -> None:
        self.assertEqual(("Mate-em-dois.png", "diagrama.png"), nomes_do_lote([_item(titulo="Mate em dois!"), _item()]))

    def test_a_extensao_vem_do_formato_registrado(self) -> None:
        self.assertEqual(("Livro.svg",), nomes_do_lote([_item(livro="Livro")], SVG))

    def test_formato_desconhecido_levanta(self) -> None:
        with self.assertRaises(KeyError):
            nomes_do_lote([_item()], "jpeg")


class OpcoesTests(unittest.TestCase):
    """As escolhas validam na construção: escolha inválida não vira arquivo."""

    def test_a_casa_e_inteira_e_o_lado_sai_perto_do_pedido(self) -> None:
        """Um lado que não seja múltiplo de oito põe uma coluna de 1 px de diferença no damero, e
        é a única coisa que se vê num diagrama de xadrez."""
        for pedido in (240, 360, 480, 640, 800, 1200, 1600, 2400):
            with self.subTest(pedido=pedido):
                opcoes = Opcoes(tamanho=pedido)
                self.assertEqual(opcoes.lado_px, 8 * opcoes.casa_px + 2 * opcoes.faixa_px)
                self.assertLessEqual(abs(opcoes.lado_px - pedido), 8, "o lado real fugiu do pedido")

    def test_sem_regua_e_sem_plaqueta_nao_ha_faixa(self) -> None:
        """A faixa existe para caber o que se desenha nela; sem nada dentro ela é borda vazia."""
        nua = Opcoes(coordenadas=False, plaqueta=False)
        self.assertFalse(nua.com_faixa)
        self.assertEqual(0, nua.faixa_px)
        self.assertEqual(0, nua.faixa_svg)
        self.assertEqual(8 * nua.casa_px, nua.lado_px)

    def test_margem_zero_tambem_tira_a_faixa(self) -> None:
        self.assertFalse(Opcoes(margem=0).com_faixa)

    def test_tamanho_e_margem_fora_da_faixa_levantam(self) -> None:
        for tamanho in (TAMANHO_MINIMO - 1, TAMANHO_MAXIMO + 1):
            with self.subTest(tamanho=tamanho), self.assertRaises(ValueError):
                Opcoes(tamanho=tamanho)
        with self.assertRaises(ValueError):
            Opcoes(margem=MARGEM_MAXIMA + 1)

    def test_formato_pele_e_conjunto_desconhecidos_levantam(self) -> None:
        for campo, valor in (("formato", "jpeg"), ("pele", "sepia"), ("conjunto", "gotico")):
            with self.subTest(campo=campo), self.assertRaises(KeyError):
                Opcoes(**{campo: valor})  # type: ignore[arg-type]

    def test_engrossar_o_traco_e_do_png_e_nao_do_svg(self) -> None:
        """O SVG desenha as peças do `python-chess`, que são caminho: engrossar não tem onde agir."""
        self.assertTrue(Opcoes(conjunto=conjuntos.TRACO, formato=PNG).engrossar)
        self.assertFalse(Opcoes(conjunto=conjuntos.TRACO, formato=SVG).engrossar)
        self.assertFalse(Opcoes(conjunto=conjuntos.PADRAO, formato=PNG).engrossar)

    def test_a_pasta_de_pecas_so_vale_para_o_conjunto_do_usuario(self) -> None:
        self.assertEqual(Path("D:/pecas"), Opcoes(conjunto=conjuntos.PASTA, pasta_de_pecas="D:/pecas").pasta_do_conjunto)
        self.assertIsNone(Opcoes(conjunto=conjuntos.PADRAO, pasta_de_pecas="D:/pecas").pasta_do_conjunto)
        self.assertIsNone(Opcoes(conjunto=conjuntos.PASTA).pasta_do_conjunto)

    def test_a_plaqueta_desligada_vira_lado_vazio_e_ligada_vira_none(self) -> None:
        """`None` é "o que a FEN disser" e `""` é "sem plaqueta" -- é o contrato dos desenhistas."""
        self.assertIsNone(Opcoes(plaqueta=True).lado_a_jogar)
        self.assertEqual("", Opcoes(plaqueta=False).lado_a_jogar)

    def test_a_frase_diz_o_lado_real_e_nao_o_pedido(self) -> None:
        """Uma tela que prometesse 800 e entregasse 792 mentiria sobre o único número que quem
        diagrama vai conferir."""
        opcoes = Opcoes(tamanho=1200)
        self.assertIn(f"{opcoes.lado_px} × {opcoes.lado_px}", frase_do_lote([_item()], opcoes))
        self.assertIn("vetorial", frase_do_lote([_item()], Opcoes(formato=SVG, tamanho=1200)))
        self.assertIn("Nenhum", frase_do_lote([], opcoes))


class PeleDoDiagramaTests(unittest.TestCase):
    """A segunda pele é **derivada** da primeira, e é o que preserva a medição da S-146."""

    def test_a_pele_de_uma_tinta_e_cinza_em_todas_as_cores(self) -> None:
        cores = cores_da_pele(UMA_TINTA)
        for nome in ("clara", "escura", "moldura", "peca_clara", "peca_escura"):
            with self.subTest(cor=nome):
                canais = getattr(cores, nome).lstrip("#")
                self.assertEqual(canais[0:2], canais[2:4])
                self.assertEqual(canais[2:4], canais[4:6])

    def test_a_luminancia_de_cada_cor_sobrevive_a_conversao(self) -> None:
        """Converter por luminância -- e não escolher dois cinzas a olho -- é o que faz a razão de
        contraste do par continuar sendo a mesma depois da conversão."""
        base, cinza = cores_da_pele(PADRAO), cores_da_pele(UMA_TINTA)
        for nome in ("clara", "escura", "peca_clara", "peca_escura"):
            with self.subTest(cor=nome):
                self.assertAlmostEqual(
                    tokens._luminancia(getattr(base, nome)),
                    tokens._luminancia(getattr(cinza, nome)),
                    places=2,
                )

    def test_o_damero_continua_distinguivel_e_a_regua_legivel_nas_duas(self) -> None:
        """O piso é o da S-146, e vale nas duas peles: um livro impresso numa tinta só não pode
        ter as duas casas na mesma mancha nem a coordenada apagada na moldura."""
        for pele in (PADRAO, UMA_TINTA):
            with self.subTest(pele=pele):
                cores = cores_da_pele(pele)
                self.assertGreaterEqual(tokens.razao_de_contraste(cores.clara, cores.escura), 1.5)
                self.assertGreaterEqual(
                    tokens.razao_de_contraste(cores.coordenada, cores.moldura), tokens.AA_TEXTO
                )
                self.assertGreaterEqual(
                    tokens.razao_de_contraste(cores.peca_clara, cores.peca_escura), tokens.AA_GRAFICO
                )

    def test_pele_desconhecida_levanta(self) -> None:
        with self.assertRaises(KeyError):
            cores_da_pele("sepia")


def _estudo(*, ancora: Ancora = Ancora(), lances: int = 0, pede: bool = False) -> Estudo:
    estudo = Estudo.de_posicao(PosicaoDeEstudo(placement=INICIAL, vez="w", ancora=ancora))
    tabuleiro = chess.Board()
    for numero in range(lances):
        lance = list(tabuleiro.legal_moves)[numero % 4]
        estudo.no = estudo.no.add_main_variation(lance)
        tabuleiro.push(lance)
    if pede and lances:
        estudo.no.comment = "Aqui o autor pede a figura. [%D]"
    return estudo


class OrigemDoLoteTests(unittest.TestCase):
    """As três origens: o estudo aberto, vários estudos, e o livro varrido."""

    def test_o_estudo_da_o_diagrama_da_raiz_e_os_que_o_autor_pediu(self) -> None:
        """A regra é a de `estudo_paragrafos`, e não uma segunda: o lote solto e o capítulo do
        EPUB mostram os mesmos diagramas do mesmo estudo."""
        itens = do_estudo(_estudo(lances=3, pede=True))
        self.assertEqual(2, len(itens))
        self.assertEqual((1, 2), tuple(item.diagrama for item in itens))

    def test_a_ancora_do_livro_vira_livro_e_pagina_contada_de_um(self) -> None:
        ancora = Ancora(documento="C:/PDF/Secrets.pdf", pagina=142, diagrama=1)
        item = do_estudo(_estudo(ancora=ancora))[0]
        self.assertEqual("Secrets", item.livro)
        self.assertEqual(143, item.pagina)

    def test_varios_estudos_recebem_a_origem_e_a_ordem_como_exercicio(self) -> None:
        """Sem isso, quinhentas partidas coladas dariam quinhentos arquivos `diagrama_1`."""
        itens = de_estudos([_estudo(), _estudo(), _estudo()], origem="Tata Steel 2021.pgn")
        self.assertEqual((1, 2, 3), tuple(item.exercicio for item in itens))
        self.assertEqual({"Tata-Steel-2021-pgn"}, {item.livro for item in itens})
        self.assertEqual(3, len(set(nomes_do_lote(itens))), "dois exercícios com o mesmo nome")

    def test_o_livro_com_ancora_vence_a_origem_colada(self) -> None:
        ancora = Ancora(documento="Secrets.pdf", pagina=0, diagrama=0)
        itens = de_estudos([_estudo(ancora=ancora)], origem="colado.pgn")
        self.assertEqual("Secrets", itens[0].livro)

    def test_a_galeria_vira_fen_com_o_lado_que_a_varredura_deduziu(self) -> None:
        class _Entrada:
            page_index, diagram_index = 6, 1
            placement, side_to_move = "8/8/8/8/8/8/8/K6k", "b"
            caption = "Diagrama 12: as brancas jogam e ganham"

        itens = da_galeria([_Entrada()], livro="Secrets of Modern Chess Strategy")
        self.assertEqual("8/8/8/8/8/8/8/K6k b - - 0 1", itens[0].fen)
        self.assertEqual((7, 2), (itens[0].pagina, itens[0].diagrama))
        self.assertEqual("Diagrama 12: as brancas jogam e ganham", itens[0].titulo)
        self.assertNotIn(":", nomes_do_lote(itens)[0], "legenda de livro não nomeia arquivo")


class GravarLoteTests(unittest.TestCase):
    """A travessia de disco: um arquivo por item, e um item ruim não derruba os outros."""

    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)

    def test_um_arquivo_por_item_com_o_nome_da_decisao(self) -> None:
        itens = [_item(livro="Livro", pagina=p) for p in (1, 2, 3)]
        relatorio = gravar_lote(itens, Opcoes(tamanho=240), self.pasta / "saida")
        self.assertEqual(3, len(relatorio.gravados))
        self.assertEqual(3, relatorio.total)
        self.assertEqual([], list(relatorio.falhas))
        for caminho in relatorio.gravados:
            self.assertTrue(caminho.exists())
            self.assertEqual(b"\x89PNG", caminho.read_bytes()[:4])
        self.assertGreater(relatorio.media_de_bytes, 0)

    def test_o_svg_sai_como_arquivo_com_declaracao_e_medida_em_pixel(self) -> None:
        """Aqui ele é arquivo, e não elemento dentro do XHTML de um EPUB."""
        relatorio = gravar_lote([_item(livro="Livro")], Opcoes(formato=SVG, tamanho=480), self.pasta)
        texto = relatorio.gravados[0].read_text(encoding="utf-8")
        self.assertTrue(texto.startswith("<?xml "))
        self.assertIn('width="480px"', texto)
        self.assertIn("viewBox", texto, "o vetor continua crescendo sem perder")

    def test_uma_fen_ilegal_entra_no_relatorio_e_a_varredura_segue(self) -> None:
        """Um livro varrido traz posições que o modelo leu errado, e uma delas no meio de
        quinhentas não pode custar as outras 499."""
        itens = [_item(livro="Bom"), _item(fen="nao-e-uma-fen", livro="Ruim"), _item(livro="Outro")]
        relatorio = gravar_lote(itens, Opcoes(tamanho=240), self.pasta)
        self.assertEqual(2, len(relatorio.gravados))
        self.assertEqual(1, len(relatorio.falhas))
        self.assertEqual("Ruim.png", relatorio.falhas[0][0])
        self.assertTrue(relatorio.falhas[0][1], "a falha entra sem motivo escrito")

    def test_cancelar_para_entre_arquivos_e_o_que_saiu_fica(self) -> None:
        parar = threading.Event()
        itens = [_item(livro=f"L{n}") for n in range(6)]

        def _no_segundo(feitos: int, _total: int, _nome: str) -> None:
            if feitos >= 2:
                parar.set()

        relatorio = gravar_lote(itens, Opcoes(tamanho=240), self.pasta, cancelar=parar, progresso=_no_segundo)
        self.assertTrue(relatorio.cancelado)
        self.assertEqual(2, len(relatorio.gravados))
        self.assertEqual(6, relatorio.total)
        self.assertIn("Cancelado", frase_do_relatorio(relatorio))

    def test_a_frase_traz_o_caminho_inteiro(self) -> None:
        """Quem acabou de gravar quinhentos arquivos precisa saber onde procurar, e "na pasta
        escolhida" não é um caminho (S-546)."""
        relatorio = gravar_lote([_item(livro="Livro")], Opcoes(tamanho=240), self.pasta)
        self.assertIn(str(self.pasta), frase_do_relatorio(relatorio))
        self.assertIn("KB", frase_do_relatorio(relatorio))

    def test_a_pasta_nasce_mesmo_quando_o_lote_inteiro_falha(self) -> None:
        destino = self.pasta / "nova"
        relatorio = gravar_lote([_item(fen="x")], Opcoes(tamanho=240), destino)
        self.assertTrue(destino.is_dir())
        self.assertEqual(0, len(relatorio.gravados))
        self.assertEqual(0, relatorio.media_de_bytes, "sem gravado não há divisão por zero")

    def test_o_tamanho_pedido_chega_ao_pixel_do_arquivo(self) -> None:
        from PIL import Image

        opcoes = Opcoes(tamanho=480)
        relatorio = gravar_lote([_item(livro="Livro")], opcoes, self.pasta)
        with Image.open(relatorio.gravados[0]) as figura:
            self.assertEqual((opcoes.lado_px, opcoes.lado_px), figura.size)

    def test_a_margem_escolhida_e_a_mesma_proporcao_nos_dois_formatos(self) -> None:
        """A faixa era um terço da casa no SVG e dois quintos no PNG, e o par do mesmo diagrama
        saía com molduras de larguras diferentes."""
        opcoes = Opcoes(margem=50, tamanho=480)
        png, svg = opcoes.faixa_px / opcoes.casa_px, opcoes.faixa_svg / 45
        self.assertAlmostEqual(png, svg, places=1)
        self.assertAlmostEqual(0.5, svg, places=1)

    def test_sem_plaqueta_o_svg_nao_traz_o_circulo_do_lado(self) -> None:
        texto = bytes_do_item(_item(), Opcoes(formato=SVG, plaqueta=False)).decode("utf-8")
        self.assertNotIn("lado-a-jogar", texto)
        self.assertIn("lado-a-jogar", bytes_do_item(_item(), Opcoes(formato=SVG)).decode("utf-8"))


class DiscoNoRelatorioTests(unittest.TestCase):
    """A falha de disco vira relatório, e não exceção (S-544, segunda rodada).

    **O defeito medido pelo crítico em 2026-09-05**: com a pasta de destino não gravável,
    `gravar_lote` levantava `FileNotFoundError` de dentro da thread -- quinhentos diagramas
    desenhados e nenhuma linha dizendo o que aconteceu. A falha de **desenho** já virava relatório
    desde a primeira rodada; as duas são a mesma pergunta para quem espera ("o que saiu e o que
    não saiu?") e agora têm a mesma resposta.
    """

    def test_a_pasta_que_nao_abre_e_uma_falha_so_e_nao_uma_por_item(self) -> None:
        """Quinhentas linhas iguais num relatório escondem justamente a linha que diz o que houve."""
        pasta = pasta_temporaria(self)
        bloqueio = pasta / "nao_sou_pasta"
        bloqueio.write_bytes(b"")
        relatorio = gravar_lote([_item(), _item(fen=INICIAL + " b - - 0 1")], Opcoes(formato=PNG), bloqueio / "saida")
        self.assertEqual((), relatorio.gravados)
        self.assertEqual(1, len(relatorio.falhas))
        self.assertEqual(2, relatorio.total)
        nome, motivo = relatorio.falhas[0]
        self.assertIn("saida", nome)
        self.assertTrue(motivo, "a falha entrou sem motivo escrito")

    def test_o_arquivo_que_nao_grava_e_falha_daquele_arquivo(self) -> None:
        """A régua do "um diagrama ruim não derruba o lote", aplicada ao disco: o vizinho segue."""
        pasta = pasta_temporaria(self) / "saida"
        pasta.mkdir(parents=True)
        nomes = nomes_do_lote([_item(), _item(fen=INICIAL + " b - - 0 1")], PNG)
        # O primeiro nome ocupado por uma **pasta**: `atomic_write_bytes` não escreve por cima dela.
        (pasta / nomes[0]).mkdir()
        relatorio = gravar_lote([_item(), _item(fen=INICIAL + " b - - 0 1")], Opcoes(formato=PNG), pasta)
        self.assertEqual(1, len(relatorio.gravados))
        self.assertEqual(1, len(relatorio.falhas))
        self.assertEqual(nomes[0], relatorio.falhas[0][0])
        self.assertTrue(relatorio.gravados[0].is_file())

    def test_a_frase_de_disco_vem_do_errno_e_nao_do_idioma_do_sistema(self) -> None:
        """A mensagem do sistema vem no idioma do Windows de quem usa -- em português ela já vem
        traduzida, e uma busca por palavra em inglês passaria num computador e falharia no outro."""
        import errno

        frases = {
            errno.EACCES: "permissão",
            errno.ENOSPC: "espaço",
            errno.ENOENT: "não existe",
        }
        for codigo, pedaco in frases.items():
            with self.subTest(errno=codigo):
                erro = OSError(codigo, "Any message in any language")
                self.assertIn(pedaco, frase_de_disco(erro))
                self.assertIn("Any message", frase_de_disco(erro), "o original sumiu")
        self.assertIn("recusou a escrita", frase_de_disco(OSError(0, "sei lá")))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
