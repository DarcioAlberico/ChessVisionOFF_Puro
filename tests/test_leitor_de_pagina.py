"""O leitor de página da S-211, e os dois defeitos de **ordem** que ele existe para não ter.

Nenhum dos dois era de reconhecimento -- o classificador acerta 99,8% em `lower_l` na própria
base --, e mesmo assim a página saía ilegível. Os dois testes que os travam são o coração deste
arquivo; o resto é contrato.

Nada aqui abre PDF nem carrega o classificador: as duas coisas são lentas e nenhuma delas é o que
estes testes perguntam. As imagens são sintéticas e as leituras são falsas, de propósito.
"""

from __future__ import annotations

import unittest

import numpy as np

from chess_diagram_ocr.text import leitor
from chess_diagram_ocr.text.boxes import Caixa, escala_de_texto
from chess_diagram_ocr.text.pagina import BlocoDeDiagrama


def _pagina_com_diagrama(escala_do_texto: int = 12, lado_da_peca: int = 48) -> np.ndarray:
    """Uma página binária com texto pequeno e um "diagrama" de peças grandes.

    É a reprodução mínima do defeito 1: as peças têm massa de tinta muito maior que as letras, e a
    mediana ponderada aterrissa nelas.

    **O lado da peça tem de caber na régua de bloco, e é isso que torna o caso real.** Um quadrado
    grande demais é descartado por `FRACAO_MAXIMA_DE_CARACTERE` e nunca chega a atrapalhar --
    e foi assim que a primeira versão deste teste falhou em reproduzir o defeito. Na página de
    verdade a peça tem 86 px numa folha de 2.420x1.870, isto é, 0,14% dela: **passa** pela régua,
    e é justamente por passar que ela sequestra a escala. 48 px numa folha de 600x500 é 0,77%,
    a mesma situação.
    """
    imagem = np.zeros((600, 500), np.uint8)
    for linha in range(6):
        for coluna in range(30):
            y = 20 + linha * (escala_do_texto + 6)
            x = 20 + coluna * (escala_do_texto + 4)
            imagem[y : y + escala_do_texto, x : x + escala_do_texto // 2] = 255
    for i in range(4):
        for j in range(4):
            y = 300 + i * (lado_da_peca + 4)
            x = 120 + j * (lado_da_peca + 4)
            imagem[y : y + lado_da_peca, x : x + lado_da_peca] = 255
    return imagem


class EscalaForaDosDiagramasTests(unittest.TestCase):
    """Defeito 1: a escala era medida **antes** de excluir o diagrama."""

    def test_o_diagrama_sequestra_a_escala_quando_ele_nao_e_excluido(self) -> None:
        """O teste que descreve o defeito. Se ele parar de valer, o de baixo perdeu o sentido."""
        imagem = _pagina_com_diagrama()
        self.assertGreater(
            escala_de_texto(imagem),
            20,
            "sem excluir o diagrama, a escala tem de sair grande -- é o defeito que se corrige",
        )

    def test_mascarar_o_diagrama_devolve_a_escala_do_texto(self) -> None:
        imagem = _pagina_com_diagrama(escala_do_texto=12)
        escala = leitor.escala_fora_dos_diagramas(imagem, [(110.0, 290.0, 390.0, 570.0)])
        self.assertLessEqual(escala, 16, f"a escala ainda mede o diagrama: {escala}")
        self.assertGreater(escala, 0)

    def test_sem_diagrama_e_a_escala_de_sempre(self) -> None:
        """Não pode mudar o caminho da faixa de legenda, que está medido."""
        imagem = _pagina_com_diagrama()
        self.assertEqual(leitor.escala_fora_dos_diagramas(imagem, []), escala_de_texto(imagem))

    def test_a_pagina_so_de_diagrama_nao_devolve_escala_zero(self) -> None:
        """Mascarar tudo apagaria a tinta, e escala 0 faria a peneira de área aceitar qualquer coisa."""
        imagem = np.zeros((200, 200), np.uint8)
        imagem[50:150, 50:150] = 255
        self.assertGreater(leitor.escala_fora_dos_diagramas(imagem, [(40.0, 40.0, 160.0, 160.0)]), 0)

    def test_imagem_vazia_devolve_zero_em_vez_de_estourar(self) -> None:
        self.assertEqual(leitor.escala_fora_dos_diagramas(np.zeros((0, 0), np.uint8), []), 0)


def _cru(texto: str, x1: int, y1: int, x2: int, y2: int, *, coluna: int = 0,
         procedencia: str = "camada", confianca: float = 1.0) -> leitor._Cru:
    return leitor._Cru(
        texto=texto,
        caixa=Caixa(x1, y1, x2, y2),
        confianca=confianca,
        procedencia=procedencia,  # type: ignore[arg-type]
        coluna=coluna,
    )


class ColunaAntesDaLinhaTests(unittest.TestCase):
    """Defeito 2: a linha era quebrada **antes** de a coluna existir, e as duas se costuravam."""

    def test_duas_colunas_de_linhas_nao_saem_intercaladas(self) -> None:
        """A esquerda inteira, depois a direita -- e não linha a linha atravessando a calha.

        Medido na página 58 do `AAGAARD` contra a camada de texto da própria página: **CER 0,7861
        intercalado, 0,1559 depois de a coluna ser achada**. Nada disso era reconhecimento.
        """
        cruas = []
        for i in range(12):
            y = 20 + i * 20
            cruas.append(_cru(f"esquerda {i}", 20, y, 240, y + 14))
            cruas.append(_cru(f"direita {i}", 300, y, 520, y + 14))
        colunas = leitor.montar(cruas, escala_px=1.0)
        self.assertEqual(len(colunas), 2, "a calha entre as duas colunas não foi achada")
        texto = "\n".join(b.texto for c in colunas for b in c.blocos)
        self.assertLess(
            texto.index("direita 0"),
            texto.index("direita 11"),
            "a coluna da direita saiu fora de ordem",
        )
        self.assertGreater(
            texto.index("direita 0"),
            texto.index("esquerda 11"),
            "as duas colunas saíram intercaladas: é o defeito que este teste trava",
        )

    def test_a_coluna_que_quem_leu_ja_sabe_manda_na_que_a_geometria_diria(self) -> None:
        """O caminho do glifo acha a coluna nas caixas de **caractere**; montar não pode refazê-la."""
        cruas = [
            _cru("primeira", 20, 20, 520, 34, coluna=1),
            _cru("segunda", 20, 40, 520, 54, coluna=0),
        ]
        colunas = leitor.montar(cruas, escala_px=1.0, faixas=[(0, 260), (261, 540)])
        self.assertEqual([c.indice for c in colunas], [0, 1])
        self.assertEqual(colunas[0].blocos[0].texto, "segunda")
        self.assertEqual(colunas[1].blocos[0].texto, "primeira")

    def test_o_piso_de_calha_de_linhas_nao_usa_a_largura_da_linha(self) -> None:
        """O piso de `colunas.calha` sai da largura de **caractere**; com linhas ele vira 20x maior.

        Medido na página 60 do `AAGAARD`: caixa de linha mediana de 552 px daria piso 441, contra
        uma calha de verdade de 34.
        """
        caixas = [Caixa(41, 10 * i, 1239, 10 * i + 8) for i in range(20)]
        self.assertLess(leitor.calha_de_linhas(caixas), 34)


class RotuloDeEixoTests(unittest.TestCase):
    def test_a_fila_do_tabuleiro_sai_do_texto(self) -> None:
        self.assertTrue(leitor.e_fila_de_eixo("a b c d e f g h"))

    def test_a_fila_lida_com_erro_continua_saindo(self) -> None:
        """A régua é estrutural: o modo bloco lê a fila como `a b d f a C e h`, e ela é a mesma."""
        self.assertTrue(leitor.e_fila_de_eixo("a b d f a C e h"))

    def test_a_coluna_de_resultados_de_um_torneio_nao_e_fila_de_eixo(self) -> None:
        """`1 1 0 1` é alinhada e **repetida** -- e é dado. Ver `pdf_text._axis_label_strip`."""
        self.assertFalse(leitor.e_fila_de_eixo("1 1 0 1 1 0 1 1"))

    def test_uma_frase_curta_de_uma_letra_por_palavra_nao_e_fila(self) -> None:
        self.assertFalse(leitor.e_fila_de_eixo("a b c"))

    def test_prosa_nunca_e_fila_de_eixo(self) -> None:
        self.assertFalse(leitor.e_fila_de_eixo("the position features a vital difference"))


class MontagemTests(unittest.TestCase):
    def test_o_diagrama_fecha_o_paragrafo_corrente(self) -> None:
        """Sem isto o diagrama iria para o fim da coluna, que é o defeito que a S-193 corrige."""
        cruas = [
            _cru("antes do diagrama", 20, 20, 240, 34),
            _cru("depois do diagrama", 20, 200, 240, 214),
        ]
        colunas = leitor.montar(cruas, [(20.0, 60.0, 240.0, 180.0)], escala_px=1.0)
        tipos = [b.tipo for c in colunas for b in c.blocos]
        self.assertEqual(tipos, ["texto", "diagrama", "texto"])

    def test_o_bbox_sai_em_pontos_e_nao_em_pixels(self) -> None:
        """A `PaginaLida` sobrevive a uma troca de DPI porque não guarda pixel. Ver a S-41."""
        colunas = leitor.montar([_cru("uma linha", 220, 220, 440, 234)], escala_px=220 / 72.0)
        bloco = colunas[0].blocos[0]
        self.assertAlmostEqual(bloco.bbox[0], 72.0, places=1)
        self.assertAlmostEqual(bloco.bbox[1], 72.0, places=1)

    def test_a_procedencia_da_linha_chega_ao_bloco(self) -> None:
        colunas = leitor.montar([_cru("lida", 20, 20, 240, 34, procedencia="glifo", confianca=0.4)],
                                escala_px=1.0)
        bloco = colunas[0].blocos[0]
        self.assertEqual(bloco.procedencia, "glifo")
        self.assertAlmostEqual(bloco.confianca, 0.4)

    def test_montar_sem_nada_devolve_nenhuma_coluna(self) -> None:
        self.assertEqual(leitor.montar([], []), ())

    def test_uma_pagina_so_de_diagramas_ainda_produz_coluna(self) -> None:
        """É a folha do `Reinfeld`: um diagrama e nada de texto. Ela não pode virar página vazia."""
        colunas = leitor.montar([], [(20.0, 60.0, 240.0, 180.0)], escala_px=1.0)
        self.assertEqual(len(colunas), 1)
        self.assertIsInstance(colunas[0].blocos[0], BlocoDeDiagrama)

    def test_a_confianca_do_detector_chega_ao_bloco_de_diagrama(self) -> None:
        colunas = leitor.montar([], [(20.0, 60.0, 240.0, 180.0)], escala_px=1.0, confiancas=[0.42])
        self.assertAlmostEqual(colunas[0].blocos[0].confianca, 0.42)


class EspacoDoModoBlocoTests(unittest.TestCase):
    def test_o_espaco_dobrado_do_modo_bloco_colapsa(self) -> None:
        """`texto_da_linha` põe um espaço no vão, e o bloco já trouxe o seu: sai `e5,  but`."""
        self.assertEqual(leitor._colapsar_espaco("e5,  but  Ne5"), "e5, but Ne5")

    def test_colapsar_nao_mexe_em_texto_normal(self) -> None:
        self.assertEqual(leitor._colapsar_espaco("uma frase normal"), "uma frase normal")


class MotorTests(unittest.TestCase):
    """O padrão é o classificador deste projeto, e a camada de texto é a exceção.

    **Isto estava invertido até 2026-08-24.** `auto` media quanto texto a camada trazia e a
    preferia acima de um piso. A pergunta estava errada: não é *quanto* a camada traz, é *o que* --
    e para notação de xadrez ela não traz nada de aproveitável. Medido em 16 páginas de 4 livros
    que têm camada: **zero** figurinas Unicode contra 360 do classificador.
    """

    def test_o_padrao_e_o_classificador_deste_projeto(self) -> None:
        self.assertEqual(leitor.MOTOR_PADRAO, "glifo")
        self.assertEqual(leitor.motor_escolhido(), "glifo")

    def test_auto_e_o_glifo_quando_ha_modelo(self) -> None:
        self.assertEqual(leitor.motor_escolhido("auto", tem_modelo=True), "glifo")

    def test_auto_cai_para_a_camada_so_sem_modelo(self) -> None:
        """Sem classificador não há leitura nenhuma, e camada imperfeita ganha de página em branco."""
        self.assertEqual(leitor.motor_escolhido("auto", tem_modelo=False), "camada")

    def test_a_camada_pedida_a_mao_nunca_e_sobreposta(self) -> None:
        """`--motor camada` é o que serve à comparação entre os dois lados."""
        self.assertEqual(leitor.motor_escolhido("camada", tem_modelo=True), "camada")

    def test_o_glifo_pedido_a_mao_nao_cai_para_a_camada(self) -> None:
        """Pedir o glifo e receber a camada em silêncio seria trocar o motor sem avisar."""
        self.assertEqual(leitor.motor_escolhido("glifo", tem_modelo=False), "glifo")

    def test_a_resposta_nunca_e_auto(self) -> None:
        """`auto` é uma pergunta, não uma origem -- e a resposta vira procedência de cada bloco."""
        from chess_diagram_ocr.text.pagina import PROCEDENCIAS

        for motor in leitor.MOTORES:
            for tem in (True, False):
                with self.subTest(motor=motor, tem_modelo=tem):
                    resposta = leitor.motor_escolhido(motor, tem_modelo=tem)
                    self.assertIn(resposta, ("camada", "glifo"))
                    self.assertIn(resposta, PROCEDENCIAS)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
