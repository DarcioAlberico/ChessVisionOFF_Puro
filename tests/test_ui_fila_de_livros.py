"""A fila de livros sem janela (S-546): transições, frases e resumo.

A varredura em si é de `batch.py` e já é afirmada em `tests/test_batch.py`; a thread e a tabela,
em `tests/test_qt_fila_de_livros.py`. O que só existe aqui é a decisão: que caminho de estado é
legal, o que cada linha diz, e quanto o conjunto andou.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from chess_diagram_ocr.ui.fila_de_livros import (
    CANCELADO,
    COLUNAS,
    FALHOU,
    LENDO,
    PENDENTE,
    PRONTO,
    PULADO,
    TRANSICOES,
    FilaDeLivros,
    LivroNaFila,
    estado_do_resultado,
    frase_de_estado,
    frase_de_resumo,
    linha_da_tabela,
)

A = Path("PDF/a.pdf")
B = Path("PDF/b.pdf")
C = Path("PDF/c.pdf")


class TransicaoTests(unittest.TestCase):
    def test_o_caminho_normal_de_um_livro_lido(self) -> None:
        fila = FilaDeLivros([A])
        self.assertEqual(fila[0].estado, PENDENTE)
        fila.comecar(0)
        self.assertEqual(fila[0].estado, LENDO)
        fila.concluir(0, PRONTO, paginas=70, diagramas=120, exportados=0, segundos=33.0)
        self.assertEqual(fila[0].estado, PRONTO)

    def test_um_livro_pronto_nao_volta_a_ser_lido(self) -> None:
        """Voltar de `pronto` a `lendo` é o defeito que duplica trabalho e reescreve o PGN."""
        fila = FilaDeLivros([A])
        fila.comecar(0)
        fila.concluir(0, PRONTO)
        with self.assertRaises(ValueError) as erro:
            fila.comecar(0)
        self.assertIn("a.pdf", str(erro.exception))

    def test_pendente_nao_pula_direto_para_pronto(self) -> None:
        """Um livro que nunca foi lido e aparece como pronto é o relatório mentindo."""
        fila = FilaDeLivros([A])
        with self.assertRaises(ValueError):
            fila.concluir(0, PRONTO)

    def test_pulado_e_alcancavel_dos_dois_lados(self) -> None:
        """O `skip_existing` só é descoberto **depois** de a varredura chegar no livro, então na
        fila da janela ele passa por `lendo` por um instante -- e recusar isso levantaria dentro
        de um slot do Qt, que derruba o processo."""
        self.assertIn(PULADO, TRANSICOES[PENDENTE])
        self.assertIn(PULADO, TRANSICOES[LENDO])
        fila = FilaDeLivros([A])
        fila.comecar(0)
        fila.concluir(0, PULADO)
        self.assertEqual(fila[0].estado, PULADO)

    def test_os_quatro_fins_sao_finais(self) -> None:
        for fim in (PRONTO, FALHOU, CANCELADO, PULADO):
            self.assertEqual(TRANSICOES[fim], frozenset(), fim)

    def test_concluir_recusa_um_estado_que_nao_e_fim(self) -> None:
        fila = FilaDeLivros([A])
        with self.assertRaises(ValueError):
            fila.concluir(0, LENDO)

    def test_avancar_num_livro_terminado_e_ignorado(self) -> None:
        """Um aviso atrasado da thread anterior faria a linha voltar a andar depois de já ter
        dito o resultado."""
        fila = FilaDeLivros([A])
        fila.comecar(0)
        fila.concluir(0, PRONTO, paginas=70)
        fila.avancar(0, 3, 70)
        self.assertEqual(fila[0].estado, PRONTO)
        self.assertEqual(fila[0].paginas_feitas, 70)

    def test_o_mesmo_livro_nao_entra_duas_vezes(self) -> None:
        """Ele seria lido duas vezes e escreveria no mesmo PGN."""
        fila = FilaDeLivros([A, B])
        self.assertEqual(fila.acrescentar([A, C]), [C])
        self.assertEqual(len(fila), 3)

    def test_cancelar_marca_os_pendentes_e_nao_o_que_esta_lendo(self) -> None:
        """Quem termina o livro em curso é a thread, que responde entre páginas e devolve o
        parcial (S-24). Marcá-lo aqui apagaria o resultado que ele ainda vai entregar."""
        fila = FilaDeLivros([A, B, C])
        fila.comecar(0)
        self.assertEqual(fila.cancelar_restantes(), 2)
        self.assertEqual([livro.estado for livro in fila], [LENDO, CANCELADO, CANCELADO])

    def test_o_estado_do_resultado_traduz_os_quatro_status_do_batch(self) -> None:
        self.assertEqual(estado_do_resultado("ok"), PRONTO)
        self.assertEqual(estado_do_resultado("pulado"), PULADO)
        self.assertEqual(estado_do_resultado("falhou"), FALHOU)
        self.assertEqual(estado_do_resultado("cancelado"), CANCELADO)

    def test_um_status_novo_vira_falhou_e_nao_excecao(self) -> None:
        """A tradução roda num slot, e uma exceção ali derrubaria a varredura inteira por causa
        de um rótulo novo no relatório."""
        self.assertEqual(estado_do_resultado("inventado"), FALHOU)


class FraseTests(unittest.TestCase):
    def test_o_pendente_diz_que_esta_na_fila(self) -> None:
        self.assertEqual(frase_de_estado(LivroNaFila(pdf=A)), "na fila")

    def test_lendo_conta_a_pagina_e_o_total(self) -> None:
        fila = FilaDeLivros([A])
        fila.comecar(0)
        fila.avancar(0, 12, 70)
        self.assertEqual(frase_de_estado(fila[0]), "lendo a página 12 de 70")

    def test_lendo_sem_total_ainda_nao_inventa_numero(self) -> None:
        """O número de páginas só se sabe ao abrir o livro; meia barra por adivinhação é pior
        que nenhuma."""
        fila = FilaDeLivros([A])
        fila.comecar(0)
        self.assertEqual(frase_de_estado(fila[0]), "abrindo o livro…")
        self.assertEqual(fila[0].fracao, 0.0)

    def test_o_resultado_fica_ao_lado_do_nome(self) -> None:
        """Uma fila que dissesse só "pronto" obrigaria a abrir o PGN para descobrir que ele saiu
        vazio -- que é o caso dos livros do acervo que exportam zero."""
        fila = FilaDeLivros([A])
        fila.comecar(0)
        fila.concluir(0, PRONTO, paginas=70, diagramas=120, exportados=0, ilegais=0, segundos=33.4)
        frase = frase_de_estado(fila[0])
        self.assertIn("120 diagrama(s)", frase)
        self.assertIn("0 exportado(s)", frase)
        self.assertIn("33 s", frase)

    def test_os_ilegais_aparecem_quando_existem_e_calam_quando_nao(self) -> None:
        fila = FilaDeLivros([A, B])
        for indice, ilegais in ((0, 9), (1, 0)):
            fila.comecar(indice)
            fila.concluir(indice, PRONTO, diagramas=10, exportados=1, ilegais=ilegais)
        self.assertIn("9 ilegal(is)", frase_de_estado(fila[0]))
        self.assertNotIn("ilegal", frase_de_estado(fila[1]))

    def test_a_falha_traz_o_motivo(self) -> None:
        fila = FilaDeLivros([A])
        fila.comecar(0)
        fila.concluir(0, FALHOU, erro="ValueError: PDF protegido por senha")
        self.assertIn("senha", frase_de_estado(fila[0]))

    def test_o_cancelado_que_nunca_comecou_nao_publica_zeros(self) -> None:
        """`0 diagrama(s), 0 exportado(s)` num livro que ninguém leu é indistinguível de um livro
        lido e vazio."""
        fila = FilaDeLivros([A])
        fila.cancelar_restantes()
        self.assertEqual(frase_de_estado(fila[0]), "cancelado antes de começar")

    def test_o_tempo_muda_de_unidade_conforme_cresce(self) -> None:
        fila = FilaDeLivros([A, B, C])
        for indice, segundos in ((0, 33.4), (1, 620.0), (2, 7200.0)):
            fila.comecar(indice)
            fila.concluir(indice, PRONTO, segundos=segundos)
        self.assertIn("33 s", frase_de_estado(fila[0]))
        self.assertIn("10,3 min", frase_de_estado(fila[1]))
        self.assertIn("2,0 h", frase_de_estado(fila[2]))


class LinhaTests(unittest.TestCase):
    def test_a_linha_tem_uma_celula_por_coluna(self) -> None:
        self.assertEqual(len(linha_da_tabela(LivroNaFila(pdf=A))), len(COLUNAS))

    def test_a_coluna_do_livro_e_a_unica_elastica(self) -> None:
        """O nome do livro é o único conteúdo sem tamanho previsível."""
        elasticas = [coluna.chave for coluna in COLUNAS if coluna.elastica]
        self.assertEqual(elasticas, ["livro"])

    def test_as_contagens_sao_numericas(self) -> None:
        """Numa fila de cinquenta livros, achar onde a exportação caiu é comparar por magnitude."""
        numericas = {coluna.chave for coluna in COLUNAS if coluna.numerica}
        self.assertEqual(numericas, {"diagramas", "exportados", "ilegais", "tempo"})

    def test_o_livro_que_nao_terminou_deixa_as_contagens_em_branco(self) -> None:
        """Um `0` numa coluna de resultado é indistinguível de "leu e não achou nada"."""
        fila = FilaDeLivros([A])
        fila.comecar(0)
        fila.avancar(0, 5, 70)
        self.assertEqual(linha_da_tabela(fila[0])[2:], ("", "", "", ""))

    def test_o_livro_pronto_publica_as_contagens(self) -> None:
        fila = FilaDeLivros([A])
        fila.comecar(0)
        fila.concluir(0, PRONTO, paginas=70, diagramas=120, exportados=3, ilegais=1, segundos=33.0)
        self.assertEqual(linha_da_tabela(fila[0])[2:], ("120", "3", "1", "33 s"))


class ConjuntoTests(unittest.TestCase):
    def test_a_fracao_do_conjunto_conta_livro_e_nao_pagina(self) -> None:
        """Contar páginas exigiria abrir os cinquenta PDFs antes de começar, e o `page_count` de
        um PDF grande custa segundos (S-61)."""
        fila = FilaDeLivros([A, B])
        fila.comecar(0)
        fila.concluir(0, PRONTO, paginas=70)
        self.assertEqual(fila.fracao, 0.5)

    def test_o_livro_em_curso_entra_na_fracao_pela_pagina(self) -> None:
        fila = FilaDeLivros([A, B])
        fila.comecar(0)
        fila.avancar(0, 35, 70)
        self.assertAlmostEqual(fila.fracao, 0.25)

    def test_a_fila_vazia_nao_divide_por_zero(self) -> None:
        self.assertEqual(FilaDeLivros().fracao, 0.0)

    def test_a_contagem_traz_estado_sem_livro_com_zero(self) -> None:
        """Uma contagem que omitisse os zeros vira `KeyError` no dia em que alguém somar dois."""
        contagem = FilaDeLivros([A]).contagem()
        self.assertEqual(contagem[PENDENTE], 1)
        self.assertEqual(set(contagem), set(TRANSICOES))
        self.assertEqual(contagem[PRONTO], 0)

    def test_so_ha_um_livro_em_curso(self) -> None:
        fila = FilaDeLivros([A, B])
        self.assertIsNone(fila.em_curso)
        fila.comecar(1)
        self.assertEqual(fila.em_curso, 1)


class ResumoTests(unittest.TestCase):
    def test_a_fila_vazia_diz_o_que_fazer(self) -> None:
        self.assertIn("acrescente livros", frase_de_resumo(FilaDeLivros()))

    def test_o_resumo_soma_os_livros_e_os_diagramas(self) -> None:
        fila = FilaDeLivros([A, B])
        for indice in (0, 1):
            fila.comecar(indice)
            fila.concluir(indice, PRONTO, paginas=70, diagramas=100, exportados=90, ilegais=2, segundos=30.0)
        resumo = frase_de_resumo(fila)
        self.assertIn("2 livro(s) lido(s)", resumo)
        self.assertIn("140 página(s)", resumo)
        self.assertIn("200 diagrama(s)", resumo)
        self.assertIn("180 exportado(s)", resumo)
        self.assertIn("4 ilegal(is)", resumo)
        self.assertIn("60 s", resumo)

    def test_a_falha_aparece_por_nome_e_nao_como_contador(self) -> None:
        """"3 livros falharam" não permite agir; os nomes permitem."""
        fila = FilaDeLivros([A])
        fila.comecar(0)
        fila.concluir(0, FALHOU, erro="ValueError: sem senha")
        resumo = frase_de_resumo(fila)
        self.assertIn("1 com falha", resumo)
        self.assertIn("falhou: a.pdf — ValueError: sem senha", resumo)

    def test_o_resumo_conta_o_que_falta(self) -> None:
        fila = FilaDeLivros([A, B, C])
        fila.comecar(0)
        fila.concluir(0, PRONTO)
        self.assertIn("2 por fazer", frase_de_resumo(fila))

    def test_o_pulado_e_o_cancelado_tem_nome_proprio_no_resumo(self) -> None:
        fila = FilaDeLivros([A, B])
        fila.concluir(0, PULADO)
        fila.cancelar_restantes()
        resumo = frase_de_resumo(fila)
        self.assertIn("1 já exportado(s) antes", resumo)
        self.assertIn("1 cancelado(s)", resumo)


if __name__ == "__main__":
    unittest.main()
