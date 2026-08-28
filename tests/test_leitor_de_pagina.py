"""O leitor de página da S-211, e os dois defeitos de **ordem** que ele existe para não ter.

Nenhum dos dois era de reconhecimento -- o classificador acerta 99,8% em `lower_l` na própria
base --, e mesmo assim a página saía ilegível. Os dois testes que os travam são o coração deste
arquivo; o resto é contrato.

Nada aqui abre PDF nem carrega o classificador: as duas coisas são lentas e nenhuma delas é o que
estes testes perguntam. As imagens são sintéticas e as leituras são falsas, de propósito.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from chess_diagram_ocr.text import leitor
from chess_diagram_ocr.text.boxes import Caixa, escala_de_texto
from chess_diagram_ocr.text.pagina import (
    BlocoDeDiagrama,
    BlocoDeTexto,
    Coluna,
    LinhaLida,
    PaginaInvalida,
    PaginaLida,
)


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
         procedencia: str = "camada", confianca: float = 1.0,
         negrito: bool | None = None) -> leitor._Cru:
    return leitor._Cru(
        texto=texto,
        caixa=Caixa(x1, y1, x2, y2),
        confianca=confianca,
        procedencia=procedencia,  # type: ignore[arg-type]
        coluna=coluna,
        negrito=negrito,
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

    def test_a_fila_so_sai_quando_ha_diagrama_perto(self) -> None:
        """`1 2 3 4 5 6 7 8` é o cabeçalho de uma tabela de oito rodadas, e era apagado em
        silêncio (S-355). Rótulo de eixo é borda de tabuleiro, e borda fica encostada num."""
        fila = _cru("1 2 3 4 5 6 7 8", 40, 300, 240, 314)
        longe = leitor.sem_rotulos_de_eixo([fila], [(40.0, 20.0, 240.0, 200.0)])
        perto = leitor.sem_rotulos_de_eixo([fila], [(40.0, 100.0, 240.0, 295.0)])

        self.assertEqual([c.texto for c in longe], ["1 2 3 4 5 6 7 8"])
        self.assertEqual(perto, [])

    def test_sem_diagrama_nenhum_nada_e_apagado(self) -> None:
        """A folha sem tabuleiro não tem borda de tabuleiro para tirar."""
        fila = _cru("a b c d e f g h", 40, 300, 240, 314)
        self.assertEqual(len(leitor.sem_rotulos_de_eixo([fila])), 1)


class MontagemTests(unittest.TestCase):
    def test_o_diagrama_que_atravessa_a_calha_fecha_as_duas_colunas(self) -> None:
        """A regra de transversal da S-193 valia na ordem de leitura e se perdia na remontagem
        por coluna: a tira da outra coluna continuava aberta, e o parágrafo de cima se juntava
        ao de baixo (S-354)."""
        cruas = [
            _cru("esquerda antes", 20, 20, 240, 34, coluna=0),
            _cru("direita antes", 320, 20, 540, 34, coluna=1),
            _cru("esquerda depois", 20, 300, 240, 314, coluna=0),
            _cru("direita depois", 320, 300, 540, 314, coluna=1),
        ]
        # O diagrama cobre as duas colunas: x de 60 a 500, sobre a calha de 240 a 320.
        colunas = leitor.montar(
            cruas, [(60.0, 60.0, 500.0, 280.0)], escala_px=1.0, faixas=[(20, 240), (320, 540)]
        )
        blocos = {c.indice: [b.tipo for b in c.blocos] for c in colunas}

        self.assertEqual(blocos[0], ["texto", "diagrama", "texto"])
        self.assertEqual(blocos[1], ["texto", "texto"], "a direita também tem de ser cortada")
        for coluna in colunas:
            for bloco in coluna.blocos:
                if bloco.tipo == "texto":
                    self.assertEqual(len(bloco.linhas), 1, "nenhum parágrafo atravessa o diagrama")

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

    def test_a_mudanca_de_peso_corta_o_paragrafo(self) -> None:
        """A quarta regra de `paragrafos.cortar` só funciona se `montar` levar o peso até ela.

        Este é o fixture da folha 51 do Dvoretsky reduzido: entrelinhamento constante, mesma
        margem, e a única diferença entre a prosa e o lance é o negrito. Sem a passagem do peso,
        os três saem num bloco só -- e o bloco sai `negrito=None`.
        """
        cruas = [
            _cru("pawn to advance.", 20, 20, 240, 34, negrito=False),
            _cru("1.Kc8!! b5", 20, 40, 240, 54, negrito=True),
            _cru("As in Reti's study,", 20, 60, 240, 74, negrito=False),
        ]
        blocos = [b for c in leitor.montar(cruas, escala_px=1.0) for b in c.blocos]
        self.assertEqual([b.texto for b in blocos], ["pawn to advance.", "1.Kc8!! b5", "As in Reti's study,"])
        self.assertEqual([b.negrito for b in blocos], [False, True, False])

    def test_sem_peso_conhecido_o_mesmo_fixture_sai_num_bloco_so(self) -> None:
        """O outro lado: nos livros cuja camada não registra peso, a regra fica inerte."""
        cruas = [
            _cru("pawn to advance.", 20, 20, 240, 34),
            _cru("1.Kc8!! b5", 20, 40, 240, 54),
            _cru("As in Reti's study,", 20, 60, 240, 74),
        ]
        blocos = [b for c in leitor.montar(cruas, escala_px=1.0) for b in c.blocos]
        self.assertEqual(len(blocos), 1)
        self.assertIsNone(blocos[0].negrito)

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


class SeparadorDeColadoTests(unittest.TestCase):
    """O separador da S-186 entra desligado, e o número que decidiu isso é da **página**.

    **A conclusão desta classe mudou, e a mudança é o item.** A primeira medição de página deu
    empate e o separador ficou desligado. Ela não viu três coisas: a população (12 páginas de prosa
    **em pé**, sem itálico, que é onde as letras encostam), a régua (CER e número de lance não
    enxergam `M♔king`) e a ordem (rodou antes das quatro correções de geometria). Remedida em 21
    páginas de 7 livros, o `auto` **não piora uma única página** na referência confiável --
    `docs/metrics/texto_colados_pagina.json`.

    O que continua valendo da primeira: os dígitos **não estão colados**, e o `sempre` custa CER --
    agora com o motivo à vista, ele parte figurina correta.
    """

    def test_a_faixa_de_legenda_continua_sem_separar(self) -> None:
        """`colados.PADRAO` descreve a **faixa**, medida sobre 155 delas. Não pode mudar aqui."""
        from chess_diagram_ocr.text import colados

        self.assertEqual(colados.PADRAO, colados.NUNCA)

    def test_a_pagina_separa_com_arbitro(self) -> None:
        """A página é outra população, e a primeira medição dela estava errada.

        Ela rodou antes das correções de geometria, sobre prosa **em pé**, com uma régua que não
        enxerga `M♔king`. Remedida em 21 páginas de 7 livros: na referência confiável o `auto`
        não piora uma única página. Ver `docs/metrics/texto_colados_pagina.json`.
        """
        from chess_diagram_ocr.text import colados

        self.assertEqual(leitor.COLADOS_NA_PAGINA, colados.AUTO)

    def test_o_sempre_continua_fora_dos_dois(self) -> None:
        """Ele parte figurina correta -- `♘f4` vira `♘1f4` --, e é o que o árbitro recusa."""
        from chess_diagram_ocr.text import colados

        self.assertNotEqual(leitor.COLADOS_NA_PAGINA, colados.SEMPRE)
        self.assertNotEqual(colados.PADRAO, colados.SEMPRE)

    def test_a_opcao_existe_e_e_um_dos_tres_modos(self) -> None:
        """Ela fica exposta mesmo perdendo: o modo `sempre` é a linha que a tabela precisa ter."""
        from chess_diagram_ocr.text import colados

        self.assertEqual(set(colados.MODOS), {"auto", "sempre", "nunca"})

    def test_desligado_nao_toca_em_caixa_nenhuma(self) -> None:
        """`nunca` tem de ser identidade -- senão o padrão medido não é o padrão que roda."""
        import numpy as np

        from chess_diagram_ocr.text import colados

        binaria = np.zeros((40, 120), np.uint8)
        binaria[10:30, 10:100] = 255
        caixas = [Caixa(10, 10, 100, 30)]
        self.assertEqual(colados.separar(binaria, caixas, escala=12, modo=colados.NUNCA), caixas)

    def test_sem_arbitro_o_auto_nao_corta(self) -> None:
        """**Sem árbitro, não mexer**: separar sem confirmação custou 2,3 pontos de F1 na origem."""
        import numpy as np

        from chess_diagram_ocr.text import colados

        binaria = np.zeros((40, 120), np.uint8)
        binaria[10:30, 10:45] = 255
        binaria[10:30, 60:100] = 255
        caixa = Caixa(10, 10, 100, 30)
        self.assertEqual(colados.partir(caixa, 52, arbitro=None, modo=colados.AUTO), [caixa])

class VinculoDaLegendaTests(unittest.TestCase):
    """O que a `PaginaLida` passou a carregar: qual parágrafo é legenda de qual diagrama (S-249).

    **Quem decide continua sendo `pdf_text.assign_lines_to_diagrams`** -- a régua da S-16, com raio
    de 60 pt e lado dominante do livro. O que estes testes travam é que a resposta dela **chegue** à
    página, que era exatamente o que faltava para o editor pintar a legenda de legenda.
    """

    def _linha(self, texto: str, bbox: tuple[float, float, float, float]) -> LinhaLida:
        return LinhaLida(texto, bbox, 1.0, "camada")

    def _pagina(self, *blocos: object) -> PaginaLida:
        return PaginaLida(
            documento="livro.pdf",
            pagina=0,
            colunas=(Coluna(indice=0, blocos=tuple(blocos)),),  # type: ignore[arg-type]
        )

    def test_o_paragrafo_logo_abaixo_do_diagrama_e_a_legenda(self) -> None:
        from chess_diagram_ocr.text.leitor import _atar_legendas

        diagrama = BlocoDeDiagrama(indice=3, bbox=(100.0, 100.0, 250.0, 250.0))
        legenda = BlocoDeTexto.de_linhas([self._linha("Daugavpils 1986", (100.0, 256.0, 250.0, 266.0))])
        longe = BlocoDeTexto.de_linhas([self._linha("outro parágrafo", (100.0, 600.0, 250.0, 610.0))])
        colunas = _atar_legendas((Coluna(indice=0, blocos=(diagrama, legenda, longe)),))
        blocos = colunas[0].blocos
        self.assertEqual(blocos[1].legenda_de, 3)
        self.assertIsNone(blocos[2].legenda_de)

    def test_o_indice_e_o_do_detector_e_nao_a_posicao_na_coluna(self) -> None:
        """É por ele que a interface reencontra o diagrama -- o mesmo de `BlocoDeDiagrama.indice`."""
        from chess_diagram_ocr.text.leitor import _atar_legendas

        diagrama = BlocoDeDiagrama(indice=7, bbox=(100.0, 100.0, 250.0, 250.0))
        legenda = BlocoDeTexto.de_linhas([self._linha("Bratislava 1956", (100.0, 256.0, 250.0, 266.0))])
        colunas = _atar_legendas((Coluna(indice=0, blocos=(diagrama, legenda)),))
        self.assertEqual(colunas[0].blocos[1].legenda_de, 7)

    def test_o_paragrafo_comprido_nao_e_legenda(self) -> None:
        """Acima de 25 palavras o bloco é comentário, não legenda -- a régua é a de `pdf_text`."""
        from chess_diagram_ocr.text.leitor import _atar_legendas

        comprido = " ".join(["palavra"] * 40)
        diagrama = BlocoDeDiagrama(indice=0, bbox=(100.0, 100.0, 250.0, 250.0))
        prosa = BlocoDeTexto.de_linhas([self._linha(comprido, (100.0, 256.0, 250.0, 266.0))])
        colunas = _atar_legendas((Coluna(indice=0, blocos=(diagrama, prosa)),))
        self.assertIsNone(colunas[0].blocos[1].legenda_de)

    def test_a_pagina_sem_diagrama_nao_muda(self) -> None:
        from chess_diagram_ocr.text.leitor import _atar_legendas

        coluna = Coluna(indice=0, blocos=(BlocoDeTexto.de_linhas([self._linha("só texto", (0, 0, 10, 10))]),))
        self.assertEqual(_atar_legendas((coluna,)), (coluna,))

    def test_o_vinculo_sobrevive_a_ida_e_volta(self) -> None:
        """A `PaginaLida` serializa sem perda por critério de aceite da S-211."""
        legenda = BlocoDeTexto.de_linhas([self._linha("Diagramm 45", (0.0, 0.0, 50.0, 10.0))])
        pagina = self._pagina(replace(legenda, legenda_de=2))
        de_volta = PaginaLida.de_json(pagina.para_json())
        self.assertEqual(de_volta.blocos[0].legenda_de, 2)

    def test_o_arquivo_antigo_sem_o_campo_nao_tem_legenda(self) -> None:
        """Ausente é "este parágrafo não é legenda de ninguém". Não paga versão de esquema."""
        bruto = self._pagina(
            BlocoDeTexto.de_linhas([self._linha("texto", (0.0, 0.0, 50.0, 10.0))])
        ).para_json()
        del bruto["colunas"][0]["blocos"][0]["legenda_de"]
        self.assertIsNone(PaginaLida.de_json(bruto).blocos[0].legenda_de)

    def test_um_vinculo_estragado_recusa(self) -> None:
        """O campo aponta para um diagrama da mesma página: apontador quebrado desenharia a
        legenda no lugar errado, em silêncio."""
        bruto = self._pagina(
            BlocoDeTexto.de_linhas([self._linha("texto", (0.0, 0.0, 50.0, 10.0))])
        ).para_json()
        bruto["colunas"][0]["blocos"][0]["legenda_de"] = "primeiro"
        with self.assertRaises(PaginaInvalida):
            PaginaLida.de_json(bruto)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class UmaAberturaPorFolhaTests(unittest.TestCase):
    """`ler_pagina` abre o livro uma vez, e não três (S-351).

    A rasterização, a leitura da camada e o detector recebiam o **caminho** e abriam o documento
    cada um. O empréstimo da S-61 existe desde então para isto, e nunca havia chegado ao caminho
    de texto.
    """

    def test_a_leitura_de_uma_folha_abre_o_documento_uma_vez(self) -> None:
        import fitz

        from chess_diagram_ocr import pdf_io

        with TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "livro.pdf"
            doc = fitz.open()
            pagina = doc.new_page(width=300.0, height=400.0)
            pagina.insert_text((40.0, 60.0), "uma linha de prosa", fontsize=11)
            doc.save(str(caminho))
            doc.close()

            antes = pdf_io.open_count()
            leitor.ler_pagina(caminho, 0, dpi=110, motor="camada", marcar_negrito=False, marcar_italico=False)

            self.assertEqual(pdf_io.open_count() - antes, 1)


class HifenDaQuebraTests(unittest.TestCase):
    """A palavra que a quebra de linha partiu volta inteira (S-353).

    `lexico.juntar_hifenizadas` existe desde a S-209, com as três condições medidas, e ninguém a
    chamava: o texto saía `devel- opment` em toda folha em que a diagramação partiu uma palavra.
    """

    LEXICO = frozenset({"development", "for", "white", "nice"})

    def test_a_hifenizada_e_juntada_dentro_do_paragrafo(self) -> None:
        cruas = [
            _cru("a nice devel-", 20, 20, 240, 34),
            _cru("opment for white", 20, 36, 240, 50),
        ]
        colunas = leitor.montar(cruas, (), escala_px=1.0, lexico=self.LEXICO)
        linhas = [linha.texto for c in colunas for b in c.blocos for linha in b.linhas]

        self.assertEqual(linhas, ["a nice development", "for white"])

    def test_sem_lexico_nada_e_juntado(self) -> None:
        """É o comportamento de antes, e o de quem lê com o dicionário desligado."""
        cruas = [
            _cru("a nice devel-", 20, 20, 240, 34),
            _cru("opment for white", 20, 36, 240, 50),
        ]
        colunas = leitor.montar(cruas, (), escala_px=1.0)
        linhas = [linha.texto for c in colunas for b in c.blocos for linha in b.linhas]

        self.assertEqual(linhas, ["a nice devel-", "opment for white"])

    def test_o_nome_composto_nao_e_juntado(self) -> None:
        """A condição 2 da S-209: `Xue-Fierro` não está no léxico, e por isso sobrevive."""
        cruas = [
            _cru("a game by Xue-", 20, 20, 240, 34),
            _cru("Fierro in 1998", 20, 36, 240, 50),
        ]
        colunas = leitor.montar(cruas, (), escala_px=1.0, lexico=self.LEXICO)
        linhas = [linha.texto for c in colunas for b in c.blocos for linha in b.linhas]

        self.assertEqual(linhas, ["a game by Xue-", "Fierro in 1998"])


class MargemVemDaCamadaTests(unittest.TestCase):
    """Cabeçalho e rodapé são da camada do PDF, mesmo numa folha lida pelo glifo (S-356)."""

    def test_a_procedencia_da_margem_e_camada(self) -> None:
        class _Linha:
            def __init__(self, texto: str, bbox: tuple[float, float, float, float]) -> None:
                self.text = texto
                self.bbox = bbox

        cabecalho, rodape = leitor._margens(
            [_Linha("O CAPÍTULO", (40.0, 20.0, 200.0, 32.0)), _Linha("142", (40.0, 760.0, 200.0, 772.0))],
            800.0,
        )

        assert cabecalho is not None and rodape is not None
        self.assertEqual(cabecalho.procedencia, "camada")
        self.assertEqual(rodape.procedencia, "camada")
