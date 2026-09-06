"""A tabela da barra do painel de Resultado, afirmada sem abrir janela (S-528, terceira barra).

**O que este arquivo cobra, e o que não.** A *forma* -- `cabem`, `arranjo`, `dica_de` -- já é
afirmada em `tests/test_ui_barra.py`, e o widget em `tests/test_qt_painel_de_resultado.py`. O que
só existe aqui é a **tabela**: dez ações, cinco grupos, e as pontes com o catálogo de comandos e
com os traços de ícone -- nos dois sentidos, que é o que impede uma chave escrita errada de virar
botão sem desenho.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.ui import barra_do_resultado, comandos, estilos, icones


class CoberturaTests(unittest.TestCase):
    """As pontes, nos dois sentidos."""

    def test_toda_acao_tem_grupo_declarado(self) -> None:
        """`Acao.__post_init__` já levanta; isto é o teto que impede um grupo declarado e vazio."""
        usados = {registro.grupo for registro in barra_do_resultado.ACOES}
        self.assertEqual(set(barra_do_resultado.GRUPOS), usados)
        for grupo in barra_do_resultado.GRUPOS:
            with self.subTest(grupo=grupo):
                self.assertTrue(barra_do_resultado.do_grupo(grupo))
                self.assertTrue(barra_do_resultado.rotulo_do_grupo(grupo))

    def test_toda_acao_tem_metodo_e_todo_metodo_tem_acao(self) -> None:
        """Uma ação sem linha em `METODOS_DO_PAINEL` é um botão que não faz nada, e um método
        declarado para ação que não existe é o nome escrito errado que ninguém vê."""
        declaradas = {registro.acao for registro in barra_do_resultado.ACOES}
        self.assertEqual(declaradas, set(barra_do_resultado.METODOS_DO_PAINEL))

    def test_o_traco_de_cada_acao_existe(self) -> None:
        """A barra é dirigida a ícone: uma chave escrita errada daria um botão de 4 px sem desenho,
        e nada acusaria."""
        for registro in barra_do_resultado.ACOES:
            with self.subTest(acao=registro.acao):
                self.assertIsNotNone(icones.tracos_de(registro.icone), registro.icone)

    def test_os_dois_tracos_novos_sao_desta_barra_e_so_dela(self) -> None:
        """O quarto dicionário existe pela razão do segundo e do terceiro: a chave de `ICONES` é
        nome de comando do catálogo, e `medidas_da_fita.grupos()` põe na fita da janela todo comando
        que declare `icone`."""
        pedidos = {registro.icone for registro in barra_do_resultado.ACOES}
        self.assertEqual(set(), set(icones.ICONES_DO_RESULTADO) - pedidos, "traço sem quem o peça")
        self.assertEqual({"salvar_todos", "mapa_de_incerteza"}, set(icones.ICONES_DO_RESULTADO))
        for nome in icones.ICONES_DO_RESULTADO:
            with self.subTest(icone=nome):
                self.assertNotIn(nome, icones.ICONES, "o traço entrou na fita da janela")

    def test_o_que_esta_no_catalogo_nao_escreve_rotulo_proprio(self) -> None:
        """A fronteira da S-324. As duas exceções são as duas que o catálogo não tem, e as duas
        têm razão escrita no módulo."""
        fora = {registro.acao for registro in barra_do_resultado.ACOES if not registro.no_catalogo}
        self.assertEqual({barra_do_resultado.COPIAR_FEN_LIDA, barra_do_resultado.MAPA_DE_INCERTEZA}, fora)
        for registro in barra_do_resultado.ACOES:
            with self.subTest(acao=registro.acao):
                self.assertTrue(registro.rotulo_curto)
                self.assertTrue(registro.rotulo_longo)

    def test_copiar_a_fen_lida_nao_e_copiar_a_fen_do_estudo(self) -> None:
        """**A distinção é real e é por isso que o nome é próprio**: o comando do catálogo copia a
        posição da sala, com os lances jogados por cima; este copia o que o modelo leu."""
        self.assertNotIn(barra_do_resultado.COPIAR_FEN_LIDA, comandos.por_acao)
        self.assertIn("copiar_fen", comandos.por_acao)


class EnfaseEPrioridadeTests(unittest.TestCase):
    """Quem manda na fila quando falta largura."""

    def test_ha_uma_enfase_so_e_ela_e_a_de_gravar(self) -> None:
        """A regra da S-446: duas ênfases numa barra é o mesmo que nenhuma. A tela existe para
        conferir uma leitura, e gravar a leitura conferida é o que ela faz."""
        primarias = [r.acao for r in barra_do_resultado.principais() if r.papel == estilos.PRIMARIO]
        self.assertEqual(["salvar"], primarias)
        estilos.conferir_barra(
            [registro.papel for registro in barra_do_resultado.principais()],
            onde="a barra do painel de resultado",
        )

    def test_so_o_primario_escreve_texto(self) -> None:
        """Catorze botões com texto não cabem em 494 px -- é a medição da S-527, nesta coluna."""
        com_texto = [r.acao for r in barra_do_resultado.ACOES if r.com_texto]
        self.assertEqual(["salvar"], com_texto)

    def test_as_prioridades_repetidas_sao_os_dois_pares(self) -> None:
        """Duas principais com a mesma prioridade entram e saem juntas (`cabem`): `◄` sem `►` é
        meia navegação, e desfazer sem refazer é um caminho de ida sem volta."""
        por_prioridade: dict[int, list[str]] = {}
        for registro in barra_do_resultado.principais():
            por_prioridade.setdefault(registro.prioridade, []).append(registro.acao)
        pares = {tuple(sorted(nomes)) for nomes in por_prioridade.values() if len(nomes) > 1}
        self.assertEqual(
            {("diagrama_anterior", "proximo_diagrama"), ("desfazer", "refazer")},
            pares,
        )

    def test_a_preferencia_vai_para_o_mais_e_e_a_unica(self) -> None:
        """Liga-se uma vez e esquece-se: eram ~180 px permanentes de `QCheckBox` com texto."""
        self.assertEqual(
            [barra_do_resultado.MAPA_DE_INCERTEZA],
            [registro.acao for registro in barra_do_resultado.secundarias()],
        )
        self.assertTrue(barra_do_resultado.acao(barra_do_resultado.MAPA_DE_INCERTEZA).marcavel)

    def test_o_interruptor_alterna_no_botao_e_nao_no_metodo(self) -> None:
        """Ele não está no catálogo, então não tem `rotulo_alternado`: quem alterna é o item, e o
        método só **lê** o estado -- ver `ui/barra.Acao.alterna_no_metodo`."""
        self.assertFalse(barra_do_resultado.acao(barra_do_resultado.MAPA_DE_INCERTEZA).alterna_no_metodo)


class RecusaTests(unittest.TestCase):
    """O que a tabela não aceita."""

    def test_acao_fora_da_barra_levanta(self) -> None:
        with self.assertRaises(KeyError):
            barra_do_resultado.acao("nao_existe")

    def test_grupo_desconhecido_levanta(self) -> None:
        with self.assertRaises(KeyError):
            barra_do_resultado.rotulo_do_grupo("nao_existe")

    def test_modo_desconhecido_levanta(self) -> None:
        """Não há modo nesta barra, e a recusa fica de pé mesmo assim: um nome escrito errado que
        devolvesse vazio seria indistinguível do único modo que existe."""
        self.assertEqual(frozenset(), barra_do_resultado.grupos_desligados(barra_do_resultado.MODO_UNICO))
        with self.assertRaises(KeyError):
            barra_do_resultado.grupos_desligados("sem-diagrama")

    def test_a_tecla_e_da_janela_e_nao_desta_barra(self) -> None:
        """Registrar de novo aqui daria duas donas para a mesma sequência, que é a colisão que
        `atalhos.conferir_dono` acusa."""
        for registro in barra_do_resultado.ACOES:
            with self.subTest(acao=registro.acao):
                self.assertEqual("", barra_do_resultado.sequencia_de(registro.acao))


class SufixoTests(unittest.TestCase):
    """O total dentro do campo, e não num rótulo ao lado."""

    def test_o_sufixo_traz_o_total(self) -> None:
        self.assertEqual(" de 7", barra_do_resultado.sufixo_de_diagramas(7))

    def test_pagina_sem_diagrama_nao_escreve_numero_negativo(self) -> None:
        """A tela vazia é o estado em que o painel abre, e ` de -1` seria a primeira coisa que ela
        diria."""
        self.assertEqual(" de 0", barra_do_resultado.sufixo_de_diagramas(0))
        self.assertEqual(" de 0", barra_do_resultado.sufixo_de_diagramas(-3))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
