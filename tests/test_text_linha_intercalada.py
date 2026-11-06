"""A caixa da altura da folha não intercala as linhas da coluna (S-712). Folhas desenhadas: nenhum livro comercial."""

from __future__ import annotations

import statistics
import unittest
from unittest import mock

import cv2
import numpy as np

from chess_diagram_ocr.text import duas_linhas, gigantes, leitor, linhas
from chess_diagram_ocr.text.boxes import Caixa

TEXTOS = (
    "the white knight wins a pawn",
    "black answers with a quiet move",
    "a rook on the open file decides",
    "after the exchange nothing is left",
    "both sides keep their bishops here",
)
"""Linhas diferentes: as iguais alinham os vãos entre as palavras, e a folha vira cinco colunas."""


def _linha(imagem: np.ndarray, n: int, y: int) -> None:
    cv2.putText(imagem, TEXTOS[n % 5], (220, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2, cv2.LINE_AA)


def _folha(*, faixa: bool = False, fio: bool = False, n_linhas: int = 20) -> np.ndarray:
    """Coluna única de texto; a faixa é a lateral sólida, sem nada que feche a volta da folha."""
    imagem = np.full((1400, 1000, 3), 255, dtype=np.uint8)
    for n in range(n_linhas):
        _linha(imagem, n, 80 + 56 * n)
    if faixa:
        imagem[:, :160] = 40
    if fio:
        imagem[40:1360, 190:193] = 0
    return imagem


def _linhas(imagem: np.ndarray) -> list[list[Caixa]]:
    _, _, _escala, caixas, regioes = leitor.segmentar(imagem)
    saida: list[list[Caixa]] = []
    for _regiao, _coluna, desta in leitor._tiras(caixas, regioes, escala=_escala):
        saida.extend(linhas.quebrar_em_linhas(linhas.ordem_em_faixa(desta)))
    return saida


def _alturas(grupos: list[list[Caixa]]) -> list[float]:
    return [linhas.envolve(g)[3] - linhas.envolve(g)[1] for g in grupos]


class MecanismoTests(unittest.TestCase):
    """As folhas 279 e 578 do *Chess Evolution*, reproduzidas: a faixa abre a banda, e a banda engole a coluna."""

    def test_sem_o_conserto_a_faixa_intercala(self) -> None:
        with mock.patch.object(gigantes, "TIRAR_GIGANTES", False):
            alturas = _alturas(_linhas(_folha(faixa=True)))
        self.assertGreater(max(alturas), 1000, "o caso tem de reproduzir o defeito")

    def test_a_faixa_nao_chega_as_linhas(self) -> None:
        grupos = _linhas(_folha(faixa=True))
        self.assertEqual(len(grupos), 20)
        self.assertLess(max(_alturas(grupos)), 1.8 * statistics.median(_alturas(grupos)))

    def test_as_linhas_saem_iguais_as_da_folha_sem_faixa(self) -> None:
        """Uma caixa de folga por linha: a faixa escura muda um pouco a binária, e duas letras se tocam."""
        com_faixa = [len(g) for g in _linhas(_folha(faixa=True))]
        sem_faixa = [len(g) for g in _linhas(_folha())]
        self.assertEqual(len(com_faixa), len(sem_faixa))
        for a, b in zip(com_faixa, sem_faixa, strict=True):
            self.assertLessEqual(abs(a - b), 1)

    def test_o_fio_vertical_que_divide_a_folha_nao_intercala(self) -> None:
        grupos = _linhas(_folha(fio=True))
        self.assertEqual(len(grupos), 20)
        self.assertLess(max(_alturas(grupos)), 1.8 * statistics.median(_alturas(grupos)))


class QuadroTests(unittest.TestCase):
    """O quadro da S-583 é uma caixa alta e larga: ela é medida antes de sair, e a região continua sendo achada."""

    def _emoldurada(self) -> np.ndarray:
        imagem = _folha(n_linhas=6)
        for n in range(7):
            _linha(imagem, n, 500 + 56 * n)
        # Aberto em cima: fechado, o contorno externo engoliria as letras de dentro.
        imagem[470:900, 190:193] = 0
        imagem[470:900, 780:783] = 0
        imagem[897:900, 190:783] = 0
        return imagem

    def test_a_moldura_nao_vira_linha(self) -> None:
        grupos = _linhas(self._emoldurada())
        self.assertEqual(len(grupos), 13)

    def test_quem_mede_o_quadro_ainda_o_ve(self) -> None:
        with mock.patch.object(leitor._quadros, "molduras_nas_caixas", wraps=leitor._quadros.molduras_nas_caixas) as medir:
            leitor.segmentar(self._emoldurada())
        caixas = medir.call_args.args[0]
        self.assertTrue(any(c.altura > 400 for c in caixas), "a moldura tem de chegar a quem a mede")


class SemGigantesTests(unittest.TestCase):
    """O que não é letra sai. Os números são literais: mudar uma régua tem de quebrar aqui."""

    ESCALA = 20
    BINARIA = np.zeros((2000, 3000), dtype=np.uint8)

    def _fora(self, *caixas: Caixa, binaria: np.ndarray | None = None) -> list[Caixa]:
        ficam = gigantes.sem_gigantes(list(caixas), self.BINARIA if binaria is None else binaria, escala=self.ESCALA)
        return [c for c in caixas if c not in ficam]

    def test_a_folha_sem_gigante_devolve_a_mesma_lista(self) -> None:
        caixas = [Caixa(0, 0, 12, 20), Caixa(20, 0, 32, 26)]
        self.assertIs(gigantes.sem_gigantes(caixas, self.BINARIA, escala=self.ESCALA), caixas)

    def test_o_fio_sai_so_acima_de_oito_escalas(self) -> None:
        self.assertEqual(self._fora(fio := Caixa(0, 0, 4, 161)), [fio])
        self.assertEqual(self._fora(Caixa(0, 0, 4, 160)), [])

    def test_a_largura_do_fio(self) -> None:
        self.assertEqual(self._fora(fio := Caixa(0, 0, 9, 300)), [fio])
        self.assertEqual(self._fora(Caixa(0, 0, 10, 300)), [], "o `I` de título é mais largo que meia escala")

    def test_a_faixa_sai_pela_fracao_da_folha(self) -> None:
        self.assertEqual(self._fora(faixa := Caixa(0, 0, 300, 600)), [faixa], "0,3 de 2.000")
        self.assertEqual(self._fora(Caixa(0, 0, 300, 599)), [])

    def test_a_letra_de_titulo_fica(self) -> None:
        """9 a 12 escalas: `PRACTICAL MATTERS` e `OPENING`, que a primeira versão apagava."""
        titulo = [Caixa(60 * k, 300, 60 * k + 55, 300 + 200) for k in range(8)]
        self.assertEqual(self._fora(*titulo), [])

    def test_a_moldura_aberta_sai_e_o_quadro_fechado_fica(self) -> None:
        """A fechada é o `CHAPTER SIX`: as letras de dentro não existem, e só o recorte dela as lê."""
        quadro = Caixa(100, 100, 900, 400)
        letras = [Caixa(150 + 30 * k, 200, 170 + 30 * k, 220) for k in range(3)]
        self.assertEqual(self._fora(quadro, *letras), [quadro])
        self.assertEqual(self._fora(quadro, *letras[:2]), [])

    def test_a_foto_abaixo_do_corte_sai_pela_tinta(self) -> None:
        binaria = np.zeros((2000, 3000), dtype=np.uint8)
        binaria[10:150, 10:170] = 255
        self.assertEqual(self._fora(foto := Caixa(10, 10, 170, 150), binaria=binaria), [foto])

    def test_o_lado_da_mancha(self) -> None:
        binaria = np.full((2000, 3000), 255, dtype=np.uint8)
        self.assertEqual(self._fora(Caixa(0, 0, 59, 150), binaria=binaria), [], "menos de 3 escalas de largura")
        self.assertEqual(self._fora(foto := Caixa(0, 0, 60, 60), binaria=binaria), [foto])

    def test_a_letra_grande_tem_tinta_de_letra(self) -> None:
        binaria = np.zeros((2000, 3000), dtype=np.uint8)
        binaria[10:150, 10:60] = 255
        binaria[10:50, 10:170] = 255
        self.assertEqual(self._fora(Caixa(10, 10, 170, 150), binaria=binaria), [])

    def test_a_letra_grossa_de_capa_fica_e_o_limite_da_tinta(self) -> None:
        """O `n` da capa do *Estrin*: 0,81 de tinta, e 5 escalas de largo porque a escala da capa sai baixa."""
        binaria = np.full((2000, 3000), 255, dtype=np.uint8)
        binaria[0:19, 0:100] = 0
        self.assertEqual(self._fora(Caixa(0, 0, 100, 100), binaria=binaria), [], "0,81")
        binaria = np.full((2000, 3000), 255, dtype=np.uint8)
        binaria[0:11, 0:100] = 0
        self.assertEqual(self._fora(Caixa(0, 0, 100, 100), binaria=binaria), [], "0,89")
        binaria[0:11, 0:100] = 255
        binaria[0:10, 0:100] = 0
        self.assertEqual(self._fora(foto := Caixa(0, 0, 100, 100), binaria=binaria), [foto], "0,90")

    def test_sem_escala_nao_mexe(self) -> None:
        caixas = [Caixa(0, 0, 4, 1900)]
        self.assertIs(gigantes.sem_gigantes(caixas, self.BINARIA, escala=0), caixas)

    def test_a_constante_desliga(self) -> None:
        caixas = [Caixa(0, 0, 4, 1900)]
        with mock.patch.object(gigantes, "TIRAR_GIGANTES", False):
            self.assertIs(gigantes.sem_gigantes(caixas, self.BINARIA, escala=self.ESCALA), caixas)


class _Classificador:
    """Lê tudo como `x`: a pergunta aqui é quais linhas existem, e não o que elas dizem."""

    def classificar(self, recortes: list[np.ndarray]) -> list[tuple[str, float]]:
        return [("x", 0.9) for _ in recortes]


class _Reconhecedor:
    classifier = _Classificador()


def _pelo_leitor(imagem: np.ndarray) -> list[tuple[int, int, int, int]]:
    """As caixas de linha que `linhas_do_glifo` entrega, e é ela que precisa ter a regra ligada."""
    cruas, _ = leitor.linhas_do_glifo(
        imagem,
        reconhecedor=_Reconhecedor(),
        colados="nunca",
        caixa_alta=False,
        traco=False,
        marca_fina=False,
        empilhados=False,
        italico=False,
        dicionario=False,
        numeros=False,
    )
    return [(c.caixa.x1, c.caixa.y1, c.caixa.x2, c.caixa.y2) for c in cruas]


class FiacaoTests(unittest.TestCase):
    """Pelo leitor, e não pela função: tirar a chamada de `linhas_do_glifo` tem de quebrar aqui."""

    def test_o_titulo_grande_chega_numa_linha_so_dele(self) -> None:
        imagem = _folha(n_linhas=20)
        cv2.putText(imagem, "OPENING", (220, 1380), cv2.FONT_HERSHEY_SIMPLEX, 9.0, (0, 0, 0), 26, cv2.LINE_AA)
        caixas = _pelo_leitor(imagem)
        altas = [c for c in caixas if c[3] - c[1] > 150]
        self.assertTrue(altas, "o título tem de chegar ao leitor de linha")
        normais = [c for c in caixas if c[3] - c[1] <= 150]
        self.assertGreaterEqual(len(normais), 18, "e sem abrir banda nas linhas de cima")
        self.assertLess(max(c[3] - c[1] for c in normais), 60)

    def test_a_letra_grande_ao_lado_do_texto_nao_abre_banda(self) -> None:
        """Pelo leitor inteiro: tirar a separação de `_tiras`, ou a escala da chamada, intercala as seis fileiras."""
        fileiras = [_fileira(200 + 40 * k, n=20) for k in range(6)]
        grande = Caixa(150, 190, 310, 400)  # Por cima das fileiras: à direita delas, a banda se fecha sozinha.
        caixas = [grande, *(c for fileira in fileiras for c in fileira)]
        cinza = np.full((1400, 1000), 255, dtype=np.uint8)
        binaria = np.zeros((1400, 1000), dtype=np.uint8)
        segmentada = (cinza, binaria, 20, caixas, [leitor._regioes.Regiao(0, 1400, ())])
        # A partição desligada: ligada, ela remenda boa parte do estrago, e o teste não veria a separação sumir.
        with mock.patch.object(leitor, "segmentar", return_value=segmentada), mock.patch.object(duas_linhas, "PARTIR_LINHA_ALTA", False):
            cruas, _ = leitor.linhas_do_glifo(
                np.stack([cinza] * 3, axis=2),
                reconhecedor=_Reconhecedor(),
                colados="nunca",
                caixa_alta=False,
                traco=False,
                marca_fina=False,
                empilhados=False,
                italico=False,
                dicionario=False,
                numeros=False,
            )
        retangulos = sorted((c.caixa.y1, c.caixa.y2, c.caixa.x1, c.caixa.x2) for c in cruas)
        inteiras = [(200 + 40 * k, 220 + 40 * k, 0, 316) for k in range(6)]
        self.assertEqual(retangulos, sorted([*inteiras, (190, 400, 150, 310)]), "seis fileiras inteiras, e a grande à parte")

    def test_o_pedaco_solto_sai_da_linha(self) -> None:
        """Um risco acima do começo da linha: a caixa curta não fixa a base, e a banda recolhe os dois."""
        imagem = _folha(n_linhas=20)
        for n in (3, 9, 15):
            imagem[80 + 56 * n - 44 : 80 + 56 * n - 38, 205:215] = 0
        com = _pelo_leitor(imagem)
        with mock.patch.object(duas_linhas, "PARTIR_LINHA_ALTA", False):
            sem = _pelo_leitor(imagem)
        self.assertGreater(max(c[3] - c[1] for c in sem), max(c[3] - c[1] for c in com), "o caso tem de reproduzir")
        alturas = sorted(c[3] - c[1] for c in com)
        self.assertLess(alturas[-1], 1.8 * alturas[len(alturas) // 2])


def _fileira(y: int, n: int = 12, altura: int = 20, x0: int = 0) -> list[Caixa]:
    return [Caixa(x0 + 16 * k, y, x0 + 16 * k + 12, y + altura) for k in range(n)]


class PartirLinhasAltasTests(unittest.TestCase):
    """A linha alta sem caixa gigante: duas fileiras costuradas, ou uma linha com um pedaço da vizinha."""

    NORMAIS = (_fileira(0), _fileira(40), _fileira(80))

    def _partidas(self, alta: list[Caixa]) -> list[list[Caixa]]:
        return duas_linhas.partir_linhas_altas([*self.NORMAIS, alta])[len(self.NORMAIS) :]

    def test_duas_fileiras_costuradas_viram_duas(self) -> None:
        cima, baixo = _fileira(200), _fileira(226)
        alta = sorted(cima + baixo, key=lambda c: c.x1)
        self.assertEqual(self._partidas(alta), [cima, baixo])

    def test_a_ordem_de_leitura_se_mantem(self) -> None:
        for pedaco in self._partidas(sorted(_fileira(200) + _fileira(226), key=lambda c: c.x1)):
            self.assertEqual(pedaco, sorted(pedaco, key=lambda c: c.x1))

    def test_o_pedaco_da_vizinha_sai_da_linha(self) -> None:
        linha = _fileira(240)
        pedaco = [Caixa(30, 205, 42, 215)]
        partidas = self._partidas(sorted(linha + pedaco, key=lambda c: c.x1))
        self.assertEqual(partidas, [pedaco, linha])

    def test_tres_fileiras_viram_tres(self) -> None:
        fileiras = [_fileira(200), _fileira(226), _fileira(252)]
        alta = sorted(fileiras[0] + fileiras[1] + fileiras[2], key=lambda c: c.x1)
        self.assertEqual(self._partidas(alta), fileiras)

    def test_o_titulo_alto_sem_vale_fica_inteiro(self) -> None:
        titulo = _fileira(200, altura=50)
        self.assertEqual(self._partidas(titulo), [titulo])

    def test_o_vale_raso_nao_corta(self) -> None:
        """Metade das caixas atravessa o meio: isso é letra grande, e não duas linhas."""
        titulo = _fileira(200, altura=56, n=6) + _fileira(200, altura=22, n=6, x0=120)
        partidas = self._partidas(titulo)
        self.assertEqual(partidas, [titulo])

    def test_a_linha_normal_nao_e_examinada(self) -> None:
        normal = _fileira(200, altura=30)
        self.assertEqual(self._partidas(normal), [normal])

    def test_o_descendente_que_atravessa_nao_impede_o_corte(self) -> None:
        """Um `g` encostado na linha de baixo: uma caixa em treze na fileira do vale, e ainda são duas linhas."""
        cima, baixo = _fileira(200), _fileira(226)
        descendente = Caixa(200, 200, 212, 240)
        partidas = self._partidas(sorted([*cima, *baixo, descendente], key=lambda c: c.x1))
        self.assertEqual(len(partidas), 2)

    def test_o_vale_com_um_terco_nao_corta(self) -> None:
        """Quatro caixas em catorze atravessam o meio: acima de um quarto da fileira mais cheia, e isso não é vale."""
        cima, baixo = _fileira(200, n=10), _fileira(226, n=10)
        atravessam = [Caixa(200 + 16 * k, 200, 212 + 16 * k, 246) for k in range(4)]
        linha = sorted([*cima, *baixo, *atravessam], key=lambda c: c.x1)
        self.assertEqual(self._partidas(linha), [linha])

    def test_o_corte_so_acima_de_um_virgula_oito(self) -> None:
        """35 de altura contra a mediana de 20: 1,75, e duas fileiras assim continuam inteiras."""
        alta = sorted(_fileira(200, altura=15) + _fileira(220, altura=15), key=lambda c: c.x1)
        self.assertEqual(self._partidas(alta), [alta])

    def test_a_maiuscula_maior_nao_e_outra_linha(self) -> None:
        """`You have` saía `Y` / `ou have`: a maiúscula atravessa o vale, e sozinha não é uma linha."""
        maiuscula = Caixa(0, 200, 30, 250)
        resto = _fileira(232, altura=18, x0=40)
        linha = [maiuscula, *resto]
        self.assertEqual(self._partidas(linha), [linha])

    def test_a_tira_curta_nao_tem_mediana(self) -> None:
        alta = sorted(_fileira(0) + _fileira(26), key=lambda c: c.x1)
        self.assertEqual(duas_linhas.partir_linhas_altas([alta]), [alta])

    def test_a_constante_desliga(self) -> None:
        alta = sorted(_fileira(200) + _fileira(226), key=lambda c: c.x1)
        with mock.patch.object(duas_linhas, "PARTIR_LINHA_ALTA", False):
            self.assertEqual(self._partidas(alta), [alta])


if __name__ == "__main__":
    unittest.main()
