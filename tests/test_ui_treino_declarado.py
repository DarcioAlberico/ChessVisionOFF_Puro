"""O que a tela de treino decide, e o placar que ela conta (S-539/S-540/S-541).

**A régua do "igualmente bom" é a da S-537, e o teste a amarra ali.** Se alguém mudar o corte de
imprecisão da análise da partida, o balde do meio do treino muda junto -- e é o que tem de
acontecer: o mesmo lance na mesma janela não pode ser imprecisão num painel e acerto no outro.
"""

from __future__ import annotations

import json
import unittest

from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr import placar as placar_mod
from chess_diagram_ocr.ui import analise_da_partida as regua
from chess_diagram_ocr.ui import treino_declarado as declarado


class MesmoLanceTests(unittest.TestCase):
    """A comparação de lance, que era de cadeia crua (S-541, r2)."""

    def test_o_xeque_no_gabarito_nao_faz_o_lance_certo_virar_erro(self) -> None:
        """**O caso é comum e ele reprovava a resposta certa.** O gabarito é guardado como o livro
        o imprimiu -- `Ra8+` num lance que na verdade dá mate --, e o que a tela tem em mãos é o
        SAN que o `chess` escreve a partir do tabuleiro, `Ra8#`. Com `==`, quem joga o lance do
        livro conta erro, o exercício volta amanhã como "não sabido", e a repetição espaçada passa
        a medir a grafia."""
        self.assertTrue(declarado.mesmo_lance("Ra8#", "Ra8+"))
        julgamento = declarado.classificar_o_lance("Ra8#", "Ra8+")
        self.assertEqual(placar_mod.CERTO, julgamento.resultado)

    def test_o_juizo_do_autor_tambem_e_aparado(self) -> None:
        self.assertTrue(declarado.mesmo_lance("Qxh7+", "Qxh7+!!"))

    def test_um_lance_parecido_continua_sendo_outro_lance(self) -> None:
        """A aparagem é só de `DECORACAO`: `Nbd2` e `Nfd2` são dois cavalos, e `exd5` não é `d5`."""
        self.assertFalse(declarado.mesmo_lance("Nbd2", "Nfd2"))
        self.assertFalse(declarado.mesmo_lance("d5", "exd5"))


class ClassificacaoTests(unittest.TestCase):
    """Os três baldes, e o corte que os separa."""

    def test_o_lance_do_gabarito_e_certo(self) -> None:
        julgamento = declarado.classificar_o_lance("Qxh7+", "Qxh7+")
        self.assertEqual(placar_mod.CERTO, julgamento.resultado)
        self.assertTrue(julgamento.certo)
        self.assertEqual(0, julgamento.perda)

    def test_o_lance_do_gabarito_e_certo_mesmo_com_o_motor_discordando(self) -> None:
        """**A ordem é a decisão**: quem treina o `1001 Sacrifices` está aprendendo a combinação de
        Reinfeld, e um Stockfish que prefere outra coisa não torna errado o lance que o livro pede."""
        julgamento = declarado.classificar_o_lance("Qxh7+", "Qxh7+", antes=200, depois=-700)
        self.assertEqual(placar_mod.CERTO, julgamento.resultado)
        self.assertEqual(0, julgamento.perda)

    def test_sem_motor_o_balde_do_meio_nao_existe(self) -> None:
        """Sem quem avalie, a única coisa afirmável é se o lance foi o do gabarito."""
        julgamento = declarado.classificar_o_lance("Bd3", "Bc2")
        self.assertEqual(placar_mod.ERRADO, julgamento.resultado)
        self.assertFalse(julgamento.com_motor)
        self.assertEqual("", julgamento.juizo)

    def test_o_balde_do_meio_e_o_silencio_de_julgar(self) -> None:
        """**A régua é `julgar` inteira, e o teste a pergunta em vez de copiar o corte.** Ela já
        mudou de escala uma vez -- de centipeões para expectativa de vitória --, e um número
        escrito aqui teria deixado o treino discordando do relatório da partida na mesma janela."""
        vira = next(
            valor for valor in range(0, -400, -5) if regua.julgar(0, valor, brancas_jogaram=True)[1]
        )
        self.assertEqual(
            placar_mod.EQUIVALENTE,
            declarado.classificar_o_lance("Bd3", "Bc2", antes=0, depois=vira + 5).resultado,
        )
        self.assertEqual(
            placar_mod.ERRADO,
            declarado.classificar_o_lance("Bd3", "Bc2", antes=0, depois=vira).resultado,
        )

    def test_o_juizo_e_o_simbolo_da_tela_sao_os_da_s537(self) -> None:
        simbolos = {regua.IMPRECISAO: "?!", regua.ERRO: "?", regua.ERRO_GRAVE: "??"}
        for depois in (-60, -150, -900):
            with self.subTest(depois=depois):
                julgamento = declarado.classificar_o_lance("Bd3", "Bc2", antes=0, depois=depois)
                esperado = regua.julgar(0, depois, brancas_jogaram=True)[1]
                self.assertTrue(esperado, "a S-537 deixou de julgar uma perda de meio peão")
                self.assertEqual(esperado, julgamento.juizo)
                self.assertEqual(simbolos[esperado], julgamento.simbolo)

    def test_a_posicao_ja_decidida_nao_recebe_juizo_nem_no_treino(self) -> None:
        """A regra que só `julgar` sabe: de +18 para +9 não é erro nenhum, e um corte escrito no
        treino chamaria isso de erro grave."""
        julgamento = declarado.classificar_o_lance("Bd3", "Bc2", antes=1800, depois=900)
        self.assertEqual(placar_mod.EQUIVALENTE, julgamento.resultado)

    def test_o_lance_que_melhora_a_avaliacao_nao_vira_erro(self) -> None:
        """`perda_do_lance` nunca é negativa: um lance que melhora é o motor tendo mudado de ideia."""
        self.assertEqual(0, declarado.classificar_o_lance("Bd3", "Bc2", antes=0, depois=300).perda)


class TentativaTests(unittest.TestCase):
    """O andamento de um exercício."""

    def _tentativa(self) -> declarado.Tentativa:
        return declarado.Tentativa(lances=("Qxh7+", "Kxh7", "Ng5+"))

    def test_o_esperado_anda_de_dois_em_dois(self) -> None:
        """A resposta do adversário é jogada sozinha: pedir os dois lados viraria digitação."""
        tentativa = self._tentativa()
        self.assertEqual("Qxh7+", tentativa.esperado)
        self.assertEqual("Kxh7", tentativa.acertou())
        self.assertEqual("Ng5+", tentativa.esperado)

    def test_a_linha_acaba_quando_o_ultimo_lance_e_de_quem_resolve(self) -> None:
        tentativa = self._tentativa()
        tentativa.acertou()
        self.assertEqual("", tentativa.acertou())
        self.assertTrue(tentativa.terminou)
        self.assertEqual("", tentativa.esperado)

    def test_errar_nao_interrompe_e_conta_a_tentativa(self) -> None:
        """Interromper na primeira faria a única resposta possível ser "ver a solução"."""
        tentativa = self._tentativa()
        tentativa.errou()
        tentativa.errou()
        self.assertEqual("Qxh7+", tentativa.esperado, "a posição não andou")
        self.assertEqual(3, tentativa.tentativas)

    def test_revelar_entrega_o_resto_e_marca_o_exercicio(self) -> None:
        tentativa = self._tentativa()
        tentativa.acertou()
        self.assertEqual(("Ng5+",), tentativa.revelar())
        self.assertTrue(tentativa.revelou)
        self.assertTrue(tentativa.terminou)

    def test_acertar_numa_tentativa_terminada_nao_faz_nada(self) -> None:
        tentativa = declarado.Tentativa()
        self.assertTrue(tentativa.terminou)
        self.assertEqual("", tentativa.acertou())


class FrasesTests(unittest.TestCase):
    """O que a tela escreve."""

    def test_a_frase_do_certo_e_curta(self) -> None:
        julgamento = declarado.classificar_o_lance("Qxh7+", "Qxh7+")
        self.assertEqual("Qxh7+ — certo.", declarado.frase_do_resultado(julgamento, "Qxh7+", "Qxh7+"))

    def test_a_frase_do_equivalente_diz_qual_era_o_da_linha(self) -> None:
        julgamento = declarado.classificar_o_lance("Bd3", "Bc2", antes=0, depois=-20)
        frase = declarado.frase_do_resultado(julgamento, "Bd3", "Bc2")
        self.assertIn("vale o mesmo", frase)
        self.assertIn("Bc2", frase)
        self.assertIn("0,20", frase)

    def test_sem_motor_a_frase_nao_promete_numero(self) -> None:
        """"Perdeu 1,40" numa janela sem motor seria um número inventado."""
        julgamento = declarado.classificar_o_lance("Bd3", "Bc2")
        frase = declarado.frase_do_resultado(julgamento, "Bd3", "Bc2")
        self.assertNotIn("perde", frase)
        self.assertIn("Bc2", frase)

    def test_a_frase_do_erro_traz_o_simbolo_e_a_perda_em_peoes(self) -> None:
        julgamento = declarado.classificar_o_lance("Bd3", "Bc2", antes=0, depois=-410)
        frase = declarado.frase_do_resultado(julgamento, "Bd3", "Bc2")
        self.assertIn("Bd3??", frase)
        self.assertIn("4,10", frase)
        self.assertIn("erro grave", frase)

    def test_a_agenda_diz_quantos_ficaram_para_amanha(self) -> None:
        """Quem some por um mês volta com 400 vencidos e vê 60; sem a segunda frase, a conclusão é
        que o programa perdeu os outros 340."""
        from chess_diagram_ocr.revisao_espacada import Agenda

        frase = declarado.frase_da_agenda(Agenda(fila=("a", "b"), vencidos=42, adiados=40))
        self.assertIn("2 para revisar", frase)
        self.assertIn("40 ficam para amanhã", frase)

    def test_a_agenda_vazia_diz_o_que_fazer(self) -> None:
        from chess_diagram_ocr.revisao_espacada import Agenda

        self.assertIn("Nada para revisar", declarado.frase_da_agenda(Agenda()))

    def test_a_fila_vazia_de_quem_ja_revisou_tudo_diz_quando_o_material_volta(self) -> None:
        """**As duas filas vazias não são o mesmo problema** (S-540, r2). "Nada para revisar"
        servia tanto a quem não extraiu exercício nenhum quanto a quem já revisou tudo hoje -- e a
        segunda pessoa precisa saber **quando** o material volta, não que ele sumiu. A frase dizia
        "extraia as táticas de outro livro" sobre uma coleção de 1.500 exercícios já extraídos."""
        from datetime import date

        from chess_diagram_ocr.revisao_espacada import Agenda

        frase = declarado.frase_da_agenda(Agenda(), volta_em=date(2026, 9, 8), colecao=1500)
        self.assertIn("08/09/2026", frase)
        self.assertIn("1.500", frase)
        self.assertNotIn("extraia", frase.lower())

    def test_o_fim_da_sessao_resume_o_que_se_fez(self) -> None:
        """**Uma sessão que acaba sem resumo acaba sem resultado** (S-540/S-541, r2). A tela dizia
        "Fila de hoje concluída" ao lado de uma agenda que continuava anunciando os três
        exercícios de meia hora atrás, e o placar da sessão sumia junto com o último exercício."""
        sessao = placar_mod.PlacarDoLivro(certos=7, equivalentes=1, errados=2, perda=300)
        frase = declarado.frase_do_fim(4, sessao)
        self.assertIn("4 exercício(s)", frase)
        self.assertIn("8 de 10", frase)
        self.assertIn("80%", frase)
        self.assertIn("0,30", frase, "a perda média por lance é a metade que faltava")

    def test_o_fim_sem_lance_nenhum_nao_inventa_porcentagem(self) -> None:
        frase = declarado.frase_do_fim(0, placar_mod.PlacarDoLivro())
        self.assertIn("nenhum lance jogado", frase)
        self.assertNotIn("%", frase)

    def test_a_agenda_separa_vencidos_de_novos(self) -> None:
        from chess_diagram_ocr.revisao_espacada import Agenda

        frase = declarado.frase_da_agenda(Agenda(fila=("a", "b", "c"), vencidos=1, novos=5))
        self.assertIn("1 vencido(s)", frase)
        self.assertIn("2 novo(s)", frase)

    def test_o_placar_vazio_nao_escreve_nada(self) -> None:
        """`0 de 0` é ruído permanente -- a mesma regra do `(0)` no rótulo de aba da S-162."""
        self.assertEqual("", declarado.frase_do_placar(placar_mod.PlacarDoLivro()))

    def test_o_placar_mostra_as_duas_escalas(self) -> None:
        sessao = placar_mod.PlacarDoLivro(certos=6, equivalentes=1, errados=2)
        livro = placar_mod.PlacarDoLivro(livro="Reinfeld 1001", certos=160, equivalentes=7, errados=47)
        frase = declarado.frase_do_placar(sessao, livro)
        self.assertIn("sessão: 7 de 9", frase)
        self.assertIn("Reinfeld 1001", frase)
        self.assertIn("214 lance(s)", frase)

    def test_a_perda_media_aparece_na_linha_do_livro(self) -> None:
        """**Ela era calculada e nunca mostrada** (S-541, r2). Sem ela, "78%" trata igual quem erra
        dois lances de 60 centipeões e quem larga a dama duas vezes -- a mesma distinção que a
        S-537 faz entre imprecisão e erro grave, aqui contada sobre o livro inteiro."""
        sessao = placar_mod.PlacarDoLivro(certos=1)
        livro = placar_mod.PlacarDoLivro(livro="Reinfeld 1001", certos=50, errados=50, perda=6200)
        self.assertIn("perde 0,62 por lance", declarado.frase_do_placar(sessao, livro))

    def test_sem_motor_a_linha_do_livro_nao_finge_perda_zero(self) -> None:
        """Sem motor a perda é sempre zero, e um `perde 0,00` fixo mentiria por omissão."""
        sessao = placar_mod.PlacarDoLivro(certos=1)
        livro = placar_mod.PlacarDoLivro(livro="Reinfeld 1001", certos=50, errados=50)
        self.assertNotIn("perde", declarado.frase_do_placar(sessao, livro))

    def test_o_gabarito_sai_com_a_procedencia(self) -> None:
        frase = declarado.frase_do_gabarito(("Qxh7+", "Kxh7"), "Reinfeld 1001, p. 63, exercício 214")
        self.assertIn("Qxh7+ Kxh7", frase)
        self.assertIn("exercício 214", frase)

    def test_gabarito_vazio_nao_finge_ter_solucao(self) -> None:
        self.assertIn("não tem solução", declarado.frase_do_gabarito(()))

    def test_a_procedencia_e_a_frase_de_taticas_e_traz_o_nome_curto(self) -> None:
        """O caminho inteiro de um livro do acervo tem 80 caracteres; escrito na tela, ele empurra
        o resto da linha para fora da janela -- foi o que a primeira fotografia mostrou."""
        from chess_diagram_ocr.taticas import Procedencia

        do_dado = Procedencia(livro="C:/PDF/Reinfeld 1001.pdf", pagina=70, folha_impressa=63, numero=214)
        self.assertEqual("Reinfeld 1001, p. 63, exercício 214", do_dado.frase())

    def test_o_desfecho_sai_com_a_solucao_e_nao_antes(self) -> None:
        """"Dá mate" ao lado do tabuleiro **antes** de a pessoa jogar é meia resposta -- e é
        justamente a metade que o livro esconde ao dizer só "as brancas jogam e ganham"."""
        self.assertIn("dá mate", declarado.frase_do_gabarito(("Qxf7#",), "", "mate"))
        self.assertIn("vantagem sem captura", declarado.frase_do_gabarito(("Nf3",), "", "sem_ganho"))
        self.assertNotIn("—", declarado.frase_do_gabarito(("Nf3",), "", "inventado"))


class PlacarTests(unittest.TestCase):
    """Os contadores e o arquivo deles."""

    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)
        self.caminho = self.pasta / "placar.json"

    def test_a_sessao_e_o_livro_contam_juntos(self) -> None:
        placar = placar_mod.Placar()
        placar.registrar("livro.pdf", placar_mod.CERTO)
        placar.registrar("livro.pdf", placar_mod.ERRADO, perda=250)
        self.assertEqual(2, placar.sessao.total)
        self.assertEqual(2, placar.do_livro("livro.pdf").total)
        self.assertEqual(125.0, placar.do_livro("livro.pdf").perda_media)

    def test_zerar_a_sessao_nao_zera_o_livro(self) -> None:
        """**O defeito que a S-541 conserta**: desligar o treino apagava a tarde inteira."""
        placar = placar_mod.Placar()
        placar.registrar("livro.pdf", placar_mod.CERTO)
        placar.zerar_sessao()
        self.assertEqual(0, placar.sessao.total)
        self.assertEqual(1, placar.do_livro("livro.pdf").total)

    def test_o_equivalente_conta_como_bom(self) -> None:
        placar = placar_mod.PlacarDoLivro().com(placar_mod.EQUIVALENTE, perda=20)
        self.assertEqual(1, placar.bons)
        self.assertEqual(1.0, placar.acerto)

    def test_posicao_sem_livro_conta_so_na_sessao(self) -> None:
        """Um "livro sem nome" que cresce para sempre não responde pergunta nenhuma."""
        placar = placar_mod.Placar()
        placar.registrar("", placar_mod.CERTO)
        self.assertEqual(1, placar.sessao.total)
        self.assertEqual({}, placar.livros)

    def test_resultado_desconhecido_levanta(self) -> None:
        with self.assertRaises(KeyError):
            placar_mod.PlacarDoLivro().com("quase")

    def test_o_total_soma_os_livros(self) -> None:
        placar = placar_mod.Placar()
        placar.registrar("um.pdf", placar_mod.CERTO)
        placar.registrar("dois.pdf", placar_mod.ERRADO, perda=300)
        self.assertEqual(2, placar.total.total)
        self.assertEqual(300, placar.total.perda)

    def test_placar_vazio_nao_divide_por_zero(self) -> None:
        vazio = placar_mod.PlacarDoLivro()
        self.assertEqual(0.0, vazio.acerto)
        self.assertEqual(0.0, vazio.perda_media)

    def test_a_ida_e_volta_do_arquivo(self) -> None:
        placar = placar_mod.Placar()
        placar.registrar("um.pdf", placar_mod.CERTO)
        placar.registrar("um.pdf", placar_mod.ERRADO, perda=120)
        placar_mod.gravar(placar, caminho=self.caminho)
        lido = placar_mod.carregar(caminho=self.caminho)
        self.assertEqual(placar.livros, lido.livros)
        self.assertEqual(0, lido.sessao.total, "a sessão não é gravada")

    def test_arquivo_ausente_e_placar_vazio(self) -> None:
        self.assertEqual({}, placar_mod.carregar(caminho=self.pasta / "nunca.json").livros)

    def test_esquema_do_futuro_nao_e_lido_pela_metade(self) -> None:
        self.caminho.write_text(json.dumps({"esquema": 99, "livros": []}), encoding="utf-8")
        self.assertEqual({}, placar_mod.carregar(caminho=self.caminho).livros)

    def test_arquivo_ilegivel_nao_derruba_a_sala(self) -> None:
        self.caminho.write_text("{isto não é json", encoding="utf-8")
        self.assertEqual({}, placar_mod.carregar(caminho=self.caminho).livros)

    def test_o_placar_lembra_de_onde_veio_e_volta_para_la(self) -> None:
        """**A origem existe porque o placar atravessa uma janela que não sabe o caminho dele**
        (S-541, r2). A sala carrega de `pasta_de_treino/placar.json` e passa o objeto para a janela
        de treino, que conta os lances; sem a origem, `gravar` cairia em `CAMINHO_PADRAO` -- em
        `data/placar.json`, que ninguém relê -- e o arquivo da pasta nunca nasceria."""
        placar = placar_mod.carregar(caminho=self.caminho)
        self.assertEqual(self.caminho, placar.origem, "vale mesmo sem o arquivo existir ainda")
        placar.registrar("um.pdf", placar_mod.CERTO)
        self.assertEqual(self.caminho, placar_mod.gravar(placar))
        self.assertTrue(self.caminho.exists())
        self.assertEqual(1, placar_mod.carregar(caminho=self.caminho).do_livro("um.pdf").certos)

    def test_placar_que_nao_veio_do_disco_nao_tem_origem(self) -> None:
        """`None` é o placar de um teste ou de quem treina numa posição colada à mão: quem grava
        sem destino explícito precisa saber que não há para onde voltar."""
        self.assertIsNone(placar_mod.Placar().origem)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
