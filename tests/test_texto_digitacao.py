"""A digitação no documento, sem janela: `rico.editar`/`apagar`/`mover` e o passo de desfazer.

**O que o editor do Qt faz com uma tecla é decidido aqui**, e é por isso que estes testes não abrem
widget nenhum: de quem o texto novo herda, que faixa ele leva, o que acontece com a marca do
diagrama e quando a digitação fecha um passo de `Ctrl+Z`. O painel (`qt/painel_de_texto.py`) só
traduz posição e repinta -- e o que ele traduz é afirmado em `tests/test_qt_texto_digitacao.py`.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.text import documento, rico
from chess_diagram_ocr.ui import texto_declarado
from chess_diagram_ocr.ui.texto_declarado import Digitacao, continua_a_digitacao, digitacao_depois


def _folha() -> rico.DocumentoRico:
    """Três parágrafos e um diagrama: prosa em negrito, a marca e um parágrafo adivinhado."""
    return rico.DocumentoRico(
        corridas=(
            rico.Corrida("Antes ", rico.Atributos(negrito=True), faixa=documento.CONFERIR, bloco=0, procedencia="glifo"),
            rico.Corrida("do lance.", faixa=documento.CONFERIR, bloco=0, procedencia="glifo"),
            rico.Corrida("\n\n", tipo=rico.SEPARADOR),
            rico.Corrida("[Diagrama 1]", tipo=rico.DIAGRAMA, bloco=1),
            rico.Corrida("\n\n", tipo=rico.SEPARADOR),
            rico.Corrida("Depois.", faixa=documento.REVISAR, bloco=2, procedencia="glifo"),
        )
    )


def _marca(doc: rico.DocumentoRico) -> tuple[int, int]:
    comeco = doc.para_texto().index("[Diagrama 1]")
    return comeco, comeco + len("[Diagrama 1]")


class EscreverTests(unittest.TestCase):
    """O texto novo: de quem herda, e o que ele declara sobre si."""

    def test_herda_o_atributo_e_o_bloco_da_esquerda_com_a_faixa_da_mao(self) -> None:
        """A faixa é a da mão, e não a da vizinha: `faixa_de_confianca` diz que a correção humana
        nunca pede revisão -- herdar o `conferir` pintaria a palavra nova de amarelo."""
        depois = rico.editar(_folha(), 3, 3, "X")
        nova = next(c for c in depois.corridas if c.texto == "X")
        self.assertTrue(nova.atributos.negrito)
        self.assertEqual(nova.bloco, 0)
        self.assertEqual(nova.procedencia, "humano")
        self.assertEqual(nova.faixa, documento.faixa_de_confianca(0.0, "humano"))
        self.assertEqual(depois.para_texto()[:7], "AntXes ")

    def test_no_comeco_do_paragrafo_herda_da_direita(self) -> None:
        """Depois do separador não há vizinha de texto à esquerda: quem escreve ali está escrevendo
        **naquele** parágrafo, e a palavra nova é dele -- bloco inclusive, para `correcao` a ver."""
        doc = _folha()
        inicio = doc.para_texto().index("Depois")
        nova = next(c for c in rico.editar(doc, inicio, inicio, "Y").corridas if c.texto == "Y")
        self.assertEqual(nova.bloco, 2)
        self.assertEqual(nova.faixa, documento.TRANQUILO)

    def test_na_linha_em_branco_entre_paragrafos_nasce_um_paragrafo_de_ninguem(self) -> None:
        """Só as vizinhas **imediatas**: pular o separador faria a linha em branco virar o fim do
        parágrafo de cima."""
        doc = _folha()
        meio = doc.para_texto().index("\n\n") + 1
        nova = next(c for c in rico.editar(doc, meio, meio, "Z").corridas if c.texto == "Z")
        self.assertEqual(nova.bloco, rico.SEM_BLOCO)
        self.assertEqual(nova.atributos, rico.PADRAO)

    def test_escrever_por_cima_da_selecao_herda_da_primeira_corrida_selecionada(self) -> None:
        """Trocar uma palavra em negrito devolve a palavra nova em negrito -- o critério de
        `substituir_intervalo`, e o de todo editor."""
        depois = rico.editar(_folha(), 0, 5, "Logo")
        self.assertEqual(depois.corridas[0].texto, "Logo")
        self.assertTrue(depois.corridas[0].atributos.negrito)
        self.assertEqual(depois.corridas[0].procedencia, "humano")

    def test_fora_do_modelo_e_declaracao_e_nao_heranca(self) -> None:
        doc = rico.inserir(rico.de_texto("lance "), 6, "♞", fora_do_modelo=True)
        depois = rico.inserir(doc, 7, "f3")
        marcadas = [c.texto for c in depois.corridas if c.atributos.fora_do_modelo]
        self.assertEqual(marcadas, ["♞"])

    def test_documento_vazio_recebe_o_texto_como_escrita_do_zero(self) -> None:
        depois = rico.editar(rico.DocumentoRico(), 0, 0, "abc")
        self.assertEqual([(c.texto, c.bloco, c.procedencia) for c in depois.corridas], [("abc", rico.SEM_BLOCO, "humano")])


class MarcaDoDiagramaTests(unittest.TestCase):
    """`[Diagrama N]` é o vínculo do texto com a figura: ele sai inteiro ou não sai."""

    def test_escrever_dentro_da_marca_nao_cabe(self) -> None:
        doc = _folha()
        comeco, _fim = _marca(doc)
        self.assertIsNone(rico.alcance_da_edicao(doc, comeco + 3, comeco + 3, "z"))
        self.assertIs(rico.editar(doc, comeco + 3, comeco + 3, "z"), doc)
        self.assertIs(rico.inserir(doc, comeco + 3, "z"), doc, "inserir também não parte a marca")

    def test_escrever_na_borda_da_marca_cabe(self) -> None:
        doc = _folha()
        comeco, fim = _marca(doc)
        self.assertEqual(rico.alcance_da_edicao(doc, comeco, comeco, "z"), (comeco, comeco))
        self.assertEqual(rico.alcance_da_edicao(doc, fim, fim, "z"), (fim, fim))

    def test_apagar_um_pedaco_da_marca_apaga_ela_inteira(self) -> None:
        """Meia marca ainda desenharia a miniatura e sairia quebrada em toda exportação."""
        doc = _folha()
        comeco, fim = _marca(doc)
        self.assertEqual(rico.alcance_de_apagar(doc, fim - 1, fim), (comeco, fim))
        depois = rico.apagar(doc, fim - 1, fim)
        self.assertEqual(depois.diagramas, ())
        self.assertNotIn("Diagrama", depois.para_texto())

    def test_apagar_uma_quebra_do_separador_junta_as_linhas(self) -> None:
        """O separador não é atômico: juntar dois parágrafos que a leitura partiu é correção."""
        doc = _folha()
        inicio = doc.para_texto().index("Depois")
        depois = rico.apagar(doc, inicio - 1, inicio)
        self.assertIn("]\nDepois", depois.para_texto())
        self.assertEqual(len(depois.diagramas), 1)

    def test_apagar_so_encolhe_e_a_corrida_partida_volta_a_ser_uma(self) -> None:
        """Escrever e apagar a mesma letra devolve o mesmo documento -- é o que faz
        `tem_alteracoes` dizer "nada a perder" sem a pessoa ter gravado."""
        doc = _folha()
        self.assertEqual(rico.apagar(rico.editar(doc, 3, 3, "X"), 3, 4), doc)


class MoverTests(unittest.TestCase):
    """O arrasto: as corridas vão inteiras -- a marca continua marca."""

    def test_a_marca_arrastada_leva_o_diagrama_junto(self) -> None:
        doc = _folha()
        comeco, fim = _marca(doc)
        depois = rico.mover(doc, comeco, fim, len(doc.para_texto()))
        self.assertTrue(depois.para_texto().endswith("Depois.[Diagrama 1]"))
        self.assertEqual(depois.diagramas[0].bloco, 1)

    def test_o_trecho_movido_guarda_o_atributo(self) -> None:
        doc = _folha()
        depois = rico.mover(doc, 0, 6, len(doc.para_texto()))
        movida = depois.corridas[-1]
        self.assertEqual((movida.texto, movida.atributos.negrito, movida.procedencia), ("Antes ", True, "glifo"))

    def test_soltar_dentro_da_marca_ou_de_si_mesmo_nao_move(self) -> None:
        doc = _folha()
        comeco, _fim = _marca(doc)
        self.assertIs(rico.mover(doc, 0, 3, comeco + 2), doc)
        self.assertIs(rico.mover(doc, 0, 6, 3), doc)


class PassoDaDigitacaoTests(unittest.TestCase):
    """Quando a tecla entra no passo de desfazer aberto -- `ui/texto_declarado`."""

    def aberta(self, *, cursor: int = 10, apagando: bool = False, quando: float = 100.0) -> Digitacao:
        return Digitacao(cursor=cursor, apagando=apagando, quando=quando)

    def test_a_letra_seguinte_no_mesmo_lugar_continua(self) -> None:
        self.assertTrue(continua_a_digitacao(self.aberta(), 10, 10, "a", agora=100.2))

    def test_sem_passo_aberto_nao_continua(self) -> None:
        self.assertFalse(continua_a_digitacao(None, 10, 10, "a", agora=100.2))

    def test_a_pausa_fecha_o_passo(self) -> None:
        depois_da_pausa = 100.0 + texto_declarado.PAUSA_DA_DIGITACAO + 0.01
        self.assertFalse(continua_a_digitacao(self.aberta(), 10, 10, "a", agora=depois_da_pausa))

    def test_o_cursor_que_pulou_fecha_o_passo(self) -> None:
        self.assertFalse(continua_a_digitacao(self.aberta(), 3, 3, "a", agora=100.2))

    def test_escrever_por_cima_de_selecao_abre_passo(self) -> None:
        self.assertFalse(continua_a_digitacao(self.aberta(), 10, 14, "a", agora=100.2))

    def test_colar_e_um_passo_so_dele(self) -> None:
        self.assertFalse(continua_a_digitacao(self.aberta(), 10, 10, "colado", agora=100.2))
        self.assertIsNone(digitacao_depois(10, 10, "colado", agora=100.2))

    def test_trocar_escrever_por_apagar_fecha_o_passo(self) -> None:
        self.assertFalse(continua_a_digitacao(self.aberta(), 9, 10, "", agora=100.2))

    def test_backspace_e_delete_em_sequencia_continuam(self) -> None:
        apagando = self.aberta(apagando=True)
        self.assertTrue(continua_a_digitacao(apagando, 9, 10, "", agora=100.2), "Backspace")
        self.assertTrue(continua_a_digitacao(apagando, 10, 11, "", agora=100.2), "Delete")
        self.assertFalse(continua_a_digitacao(apagando, 4, 5, "", agora=100.2), "longe do cursor")

    def test_o_passo_aberto_segue_o_cursor(self) -> None:
        self.assertEqual(digitacao_depois(10, 10, "a", agora=1.0), Digitacao(cursor=11, apagando=False, quando=1.0))
        self.assertEqual(digitacao_depois(9, 10, "", agora=1.0), Digitacao(cursor=9, apagando=True, quando=1.0))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
