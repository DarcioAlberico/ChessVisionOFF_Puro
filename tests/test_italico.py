"""A linha em itálico, e o `l` que sai `/` dentro dela (S-211).

O diagnóstico veio do dono do projeto; a medição confirmou. O que estes testes travam é a régua --
e, principalmente, que ela **não dispara em texto em pé**, porque `1/2-1/2` é resultado de partida.
"""

from __future__ import annotations

import unittest

import numpy as np

from chess_diagram_ocr.text import documento
from chess_diagram_ocr.text import italico as it
from chess_diagram_ocr.text.boxes import Caixa
from chess_diagram_ocr.text.pagina import (
    BlocoDeTexto,
    Coluna,
    LinhaLida,
    PaginaInvalida,
    PaginaLida,
)

I2C = {0: "/", 1: "l", 2: "a"}


def _traco(inclinado: bool, altura: int = 24, largura: int = 9) -> np.ndarray:
    """Uma imagem com um traço: em pé, ou pendido para a direita como em itálico."""
    img = np.zeros((altura + 10, largura + 10), np.uint8)
    for y in range(altura):
        desloc = int((altura - y) * 0.35) if inclinado else 0
        img[5 + y, 5 + desloc : 5 + desloc + 3] = 255
    return img


class PendorTests(unittest.TestCase):
    def test_o_traco_pendido_da_pendor_positivo(self) -> None:
        img = _traco(True)
        self.assertGreater(it.pendor_do_box(img, Caixa(0, 0, img.shape[1], img.shape[0])), 0.05)

    def test_o_traco_em_pe_da_pendor_perto_de_zero(self) -> None:
        img = _traco(False)
        self.assertLess(abs(it.pendor_do_box(img, Caixa(0, 0, img.shape[1], img.shape[0]))), 0.05)

    def test_box_baixo_demais_nao_tem_duas_metades(self) -> None:
        self.assertIsNone(it.pendor_do_box(np.zeros((10, 10), np.uint8), Caixa(0, 0, 10, 3)))

    def test_box_sem_tinta_devolve_none(self) -> None:
        self.assertIsNone(it.pendor_do_box(np.zeros((30, 30), np.uint8), Caixa(0, 0, 20, 20)))


def _linha(inclinada: bool, n: int = 10) -> tuple[np.ndarray, list[Caixa]]:
    """Uma linha de `n` traços, todos em pé ou todos pendidos."""
    um = _traco(inclinada)
    alto, largo = um.shape
    img = np.zeros((alto, largo * n), np.uint8)
    caixas = []
    for i in range(n):
        img[:, i * largo : (i + 1) * largo] = um
        caixas.append(Caixa(i * largo, 0, (i + 1) * largo, alto))
    return img, caixas


class LinhaTests(unittest.TestCase):
    def test_a_linha_pendida_e_italica(self) -> None:
        img, caixas = _linha(True)
        self.assertTrue(it.e_italica(img, caixas))

    def test_a_linha_em_pe_nao_e(self) -> None:
        img, caixas = _linha(False)
        self.assertFalse(it.e_italica(img, caixas))

    def test_linha_curta_demais_nao_e_declarada_italica(self) -> None:
        """`1/2-1/2` é uma linha curta, e é onde a barra é legítima -- chutar ali seria caro."""
        img, caixas = _linha(True, n=3)
        self.assertIsNone(it.pendor_da_linha(img, caixas))
        self.assertFalse(it.e_italica(img, caixas))

    def test_o_corte_e_lido_na_chamada(self) -> None:
        img, caixas = _linha(True)
        original = it.PENDOR_DE_ITALICO
        try:
            it.PENDOR_DE_ITALICO = 9.0
            self.assertFalse(it.e_italica(img, caixas))
        finally:
            it.PENDOR_DE_ITALICO = original


class CorrigirTests(unittest.TestCase):
    def test_na_linha_italica_a_barra_vira_ele(self) -> None:
        img, caixas = _linha(True)
        probs = np.zeros((len(caixas), 3), np.float32)
        probs[:, 0] = 0.9
        probs[:, 1] = 0.03
        saida = it.corrigir([("/", 0.9)] * len(caixas), probs, caixas, I2C, img)
        self.assertEqual({c for c, _ in saida}, {"l"})

    def test_na_linha_em_pe_a_barra_fica(self) -> None:
        """É `1/2-1/2`, e trocá-lo apagaria resultado de partida."""
        img, caixas = _linha(False)
        probs = np.zeros((len(caixas), 3), np.float32)
        probs[:, 0] = 0.9
        saida = it.corrigir([("/", 0.9)] * len(caixas), probs, caixas, I2C, img)
        self.assertEqual({c for c, _ in saida}, {"/"})

    def test_o_que_nao_e_barra_passa_intacto(self) -> None:
        img, caixas = _linha(True)
        probs = np.zeros((len(caixas), 3), np.float32)
        probs[:, 2] = 0.9
        saida = it.corrigir([("a", 0.9)] * len(caixas), probs, caixas, I2C, img)
        self.assertEqual({c for c, _ in saida}, {"a"})

    def test_a_confianca_e_a_da_classe_escolhida(self) -> None:
        img, caixas = _linha(True)
        probs = np.zeros((len(caixas), 3), np.float32)
        probs[:, 0] = 0.90
        probs[:, 1] = 0.04
        _, conf = it.corrigir([("/", 0.90)] * len(caixas), probs, caixas, I2C, img)[0]
        self.assertAlmostEqual(conf, 0.04, places=3)

    def test_sem_a_classe_do_ele_devolve_intacto(self) -> None:
        img, caixas = _linha(True)
        probs = np.zeros((len(caixas), 3), np.float32)
        saida = it.corrigir([("/", 0.9)] * len(caixas), probs, caixas, {0: "/"}, img)
        self.assertEqual({c for c, _ in saida}, {"/"})

    def test_lista_vazia_devolve_vazia(self) -> None:
        self.assertEqual(it.corrigir([], np.empty((0, 3), np.float32), [], I2C, np.zeros((4, 4), np.uint8)), [])

    def test_so_a_barra_esta_na_tabela_de_troca(self) -> None:
        """`I` também sai `/`, e **não** entra: escolher entre `l` e `I` é do léxico."""
        self.assertEqual(it.TROCA, {"/": "l"})


class DeclararTests(unittest.TestCase):
    """Os três estados da S-236. `None` é "não se mediu", e não é o mesmo que "não é itálica"."""

    def test_a_linha_pendida_e_declarada_italica(self) -> None:
        img, caixas = _linha(True)
        self.assertIs(it.declarar(img, caixas), True)

    def test_a_linha_em_pe_e_declarada_em_pe(self) -> None:
        img, caixas = _linha(False)
        self.assertIs(it.declarar(img, caixas), False)

    def test_a_linha_curta_nao_e_declarada(self) -> None:
        """Uma linha de três boxes -- um número de lance, um rótulo de eixo -- não tem população."""
        img, caixas = _linha(True, n=it.MIN_BOXES_PARA_MEDIR - 1)
        self.assertIsNone(it.declarar(img, caixas))

    def test_e_italica_achata_o_desconhecido_em_falso(self) -> None:
        """No caminho da correção é isso que se quer: a dúvida não autoriza trocar `/` por `l`."""
        img, caixas = _linha(True, n=it.MIN_BOXES_PARA_MEDIR - 1)
        self.assertIsNone(it.declarar(img, caixas))
        self.assertFalse(it.e_italica(img, caixas))

    def test_o_corte_vale_para_declarar(self) -> None:
        img, caixas = _linha(True)
        self.assertIs(it.declarar(img, caixas, corte=9.0), False)


class MedirUmaVezTests(unittest.TestCase):
    """`corrigir` aceita a medição pronta -- é o que sustenta "a S-236 custa zero" (S-236)."""

    def _probs(self, n: int) -> np.ndarray:
        probs = np.zeros((n, len(I2C)), np.float32)
        probs[:, 0] = 0.9
        probs[:, 1] = 0.6
        return probs

    def test_a_medicao_passada_da_o_mesmo_que_medir_dentro(self) -> None:
        img, caixas = _linha(True)
        lidos = [("/", 0.9)] * len(caixas)
        probs = self._probs(len(caixas))
        dentro = it.corrigir(lidos, probs, caixas, I2C, img)
        passada = it.corrigir(lidos, probs, caixas, I2C, img, italica=it.declarar(img, caixas))
        self.assertEqual(dentro, passada)
        self.assertEqual([c for c, _ in passada], ["l"] * len(caixas))

    def test_a_medicao_passada_como_falsa_nao_troca(self) -> None:
        img, caixas = _linha(True)
        lidos = [("/", 0.9)] * len(caixas)
        saida = it.corrigir(lidos, self._probs(len(caixas)), caixas, I2C, img, italica=False)
        self.assertEqual([c for c, _ in saida], ["/"] * len(caixas))

    def test_a_medicao_desconhecida_nao_troca(self) -> None:
        """`None` chega de linha curta, e ali trocar `/` seria estragar `1/2-1/2`."""
        img, caixas = _linha(True)
        lidos = [("/", 0.9)] * len(caixas)
        saida = it.corrigir(lidos, self._probs(len(caixas)), caixas, I2C, img, italica=None)
        self.assertEqual([c for c, _ in saida], ["l"] * len(caixas))


class CampoNaPaginaTests(unittest.TestCase):
    """O campo que a S-236 acrescenta: como ele serializa, e o que ele **não** muda."""

    def _linha_lida(self, pendor: bool | None) -> LinhaLida:
        return LinhaLida("texto", (0.0, 0.0, 10.0, 10.0), 0.9, "glifo", italico=pendor)

    def test_o_campo_serializa_e_volta(self) -> None:
        for pendor in (True, False, None):
            with self.subTest(italico=pendor):
                volta = LinhaLida.de_json(self._linha_lida(pendor).para_json())
                self.assertIs(volta.italico, pendor)

    def test_a_pagina_antiga_carrega_sem_o_campo(self) -> None:
        """Arquivo gravado antes da S-236: ausente é "não se sabe", e não paga versão de esquema."""
        antigo = {"texto": "a", "bbox": [0, 0, 1, 1], "confianca": 1.0, "procedencia": "camada"}
        self.assertIsNone(LinhaLida.de_json(antigo).italico)

    def test_um_italico_que_nao_e_booleano_recusa(self) -> None:
        antigo = {"texto": "a", "bbox": [0, 0, 1, 1], "italico": "sim"}
        with self.assertRaises(PaginaInvalida):
            LinhaLida.de_json(antigo)

    def test_o_bloco_so_e_italico_se_todas_as_linhas_forem(self) -> None:
        todas = BlocoDeTexto.de_linhas([self._linha_lida(True), self._linha_lida(True)])
        self.assertIs(todas.italico, True)
        mista = BlocoDeTexto.de_linhas([self._linha_lida(True), self._linha_lida(False)])
        self.assertIsNone(mista.italico)
        duvida = BlocoDeTexto.de_linhas([self._linha_lida(True), self._linha_lida(None)])
        self.assertIsNone(duvida.italico)

    def test_a_camada_nao_declara_italico_pela_geometria(self) -> None:
        """A camada de texto não passa pela binária: sem pendor medido, o campo fica em `None`."""
        da_camada = LinhaLida("lido", (0.0, 0.0, 10.0, 10.0), 1.0, "camada")
        self.assertIsNone(da_camada.italico)

    def test_o_texto_da_pagina_nao_muda_com_o_campo(self) -> None:
        """O item acrescenta atributo, e não muda leitura -- é a promessa de CER inalterado."""
        textos = []
        for pendor in (True, False, None):
            bloco = BlocoDeTexto.de_linhas([self._linha_lida(pendor)])
            pagina = PaginaLida(colunas=(Coluna(indice=0, blocos=(bloco,)),))
            textos.append(documento.texto_para_arquivo(pagina, com_cabecalho=False))
        self.assertEqual(len(set(textos)), 1, "o campo mudou o texto que sai da página")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
