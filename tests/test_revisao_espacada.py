"""O FSRS e a agenda do dia (S-540).

**O que estes testes travam.** Não a aritmética do artigo -- ela é a do artigo --, mas as
**propriedades** que fazem o agendamento ser este e não outro, e cada uma pelo caso que ela
resolve:

- a curva de potência, e o intervalo valendo a estabilidade a 90% (é a definição de estabilidade,
  e é o que faz a retenção alvo ser um botão de verdade);
- o erro **nunca** aumentando a estabilidade;
- o item difícil continuando a ganhar intervalo -- é o "inferno de facilidade" do SM-2, que é a
  razão de o FSRS ter sido escolhido;
- sumir por um mês: o acerto depois da ausência valendo **mais** que o acerto em dia, e a fila do
  dia não virando uma parede.
"""

from __future__ import annotations

import json
import unittest
from datetime import date, timedelta

from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr import revisao_arquivo
from chess_diagram_ocr import revisao_espacada as fsrs

HOJE = date(2026, 9, 4)


class CurvaTests(unittest.TestCase):
    """A curva de esquecimento e a inversa dela."""

    def test_a_retencao_no_dia_da_revisao_e_um(self) -> None:
        self.assertAlmostEqual(1.0, fsrs.retencao(0, 10.0), places=6)

    def test_a_retencao_cai_e_nunca_chega_a_zero(self) -> None:
        """A cauda é o que a curva de potência tem e a exponencial não: um item de estabilidade
        dez dias não está perdido em sessenta, e é o que a medição do Anki mostrou."""
        valores = [fsrs.retencao(dias, 10.0) for dias in (0, 5, 10, 30, 365)]
        self.assertEqual(valores, sorted(valores, reverse=True))
        self.assertGreater(valores[-1], 0.0)
        self.assertGreater(fsrs.retencao(60, 10.0), 0.3)

    def test_a_retencao_na_estabilidade_e_noventa_por_cento(self) -> None:
        """**É a definição de estabilidade**, e é o que amarra `FATOR` a `DECAY`."""
        self.assertAlmostEqual(0.9, fsrs.retencao(10.0, 10.0), places=6)

    def test_o_intervalo_a_noventa_por_cento_e_a_propria_estabilidade(self) -> None:
        self.assertEqual(20, fsrs.intervalo(20.0))

    def test_pedir_mais_retencao_encurta_o_intervalo(self) -> None:
        """A perilla inteira do FSRS: 95% de retenção é o mesmo material revisto mais vezes."""
        self.assertLess(fsrs.intervalo(20.0, alvo=0.95), fsrs.intervalo(20.0, alvo=0.90))
        self.assertGreater(fsrs.intervalo(20.0, alvo=0.80), fsrs.intervalo(20.0, alvo=0.90))

    def test_o_intervalo_tem_piso_de_um_dia_e_teto_de_dez_anos(self) -> None:
        """Este programa agenda por dia: não há sessão de quinze minutos num livro de xadrez."""
        self.assertEqual(1, fsrs.intervalo(0.01))
        self.assertEqual(fsrs.TETO_DE_INTERVALO, fsrs.intervalo(999_999.0))


class EstadoTests(unittest.TestCase):
    """O que uma revisão faz com estabilidade e dificuldade."""

    def test_a_estabilidade_inicial_e_o_peso_da_nota(self) -> None:
        """Errar de saída **não zera** o item: dá a ele meio dia. Acertar com facilidade dá quase
        duas semanas, sem passar pelos degraus de aprendizado que o SM-2 obriga."""
        for nota in fsrs.NOTAS:
            with self.subTest(nota=nota):
                estado = fsrs.estado_inicial("x", nota, hoje=HOJE)
                self.assertAlmostEqual(fsrs.PESOS[nota - 1], estado.estabilidade, places=4)
        self.assertLess(
            fsrs.estado_inicial("x", fsrs.DE_NOVO, hoje=HOJE).estabilidade,
            fsrs.estado_inicial("x", fsrs.FACIL, hoje=HOJE).estabilidade,
        )

    def test_a_dificuldade_inicial_cresce_quando_se_erra(self) -> None:
        facil = fsrs.estado_inicial("x", fsrs.FACIL, hoje=HOJE).dificuldade
        errado = fsrs.estado_inicial("x", fsrs.DE_NOVO, hoje=HOJE).dificuldade
        self.assertGreater(errado, facil)
        for nota in fsrs.NOTAS:
            valor = fsrs.estado_inicial("x", nota, hoje=HOJE).dificuldade
            self.assertTrue(fsrs.DIFICULDADE_MINIMA <= valor <= fsrs.DIFICULDADE_MAXIMA)

    def test_o_primeiro_estado_ja_tem_vencimento_e_log(self) -> None:
        estado = fsrs.estado_inicial("chave", fsrs.BOM, hoje=HOJE)
        self.assertFalse(estado.novo)
        self.assertEqual(HOJE + timedelta(days=fsrs.intervalo(estado.estabilidade)), estado.vencimento)
        self.assertEqual(1, estado.revisoes)
        self.assertEqual(1, len(estado.historico))

    def test_acertar_estica_e_errar_encurta(self) -> None:
        estado = fsrs.estado_inicial("x", fsrs.BOM, hoje=HOJE)
        depois = HOJE + timedelta(days=fsrs.intervalo(estado.estabilidade))
        certo = fsrs.proximo(estado, fsrs.BOM, hoje=depois)
        errado = fsrs.proximo(estado, fsrs.DE_NOVO, hoje=depois)
        self.assertGreater(certo.estabilidade, estado.estabilidade)
        self.assertLess(errado.estabilidade, estado.estabilidade)
        self.assertEqual(1, errado.lapsos)
        self.assertEqual(0, certo.lapsos)

    def test_o_erro_nunca_aumenta_a_estabilidade(self) -> None:
        """A trava é explícita: a fórmula de lapso pode devolver mais que a estabilidade anterior
        em item muito novo, e um item que se acabou de errar não pode ficar mais firme por isso."""
        for estabilidade in (0.2, 0.5, 1.0, 3.0, 30.0):
            with self.subTest(estabilidade=estabilidade):
                estado = fsrs.Estado(
                    chave="x", estabilidade=estabilidade, dificuldade=5.0,
                    vencimento=HOJE, ultima=HOJE - timedelta(days=1), revisoes=1,
                )
                seguinte = fsrs.proximo(estado, fsrs.DE_NOVO, hoje=HOJE)
                self.assertLessEqual(seguinte.estabilidade, estado.estabilidade)

    def test_o_item_dificil_continua_ganhando_intervalo(self) -> None:
        """**É a razão de não ser SM-2.** Lá cada erro tira 0,2 do fator e o piso é 1,3; numa
        coleção de combinações metade dos itens desce ao piso e nunca sobe -- o baralho vira uma
        fila diária que não encolhe. Aqui o item de dificuldade máxima acerta e cresce."""
        duro = fsrs.Estado(
            chave="x", estabilidade=2.0, dificuldade=fsrs.DIFICULDADE_MAXIMA,
            vencimento=HOJE, ultima=HOJE - timedelta(days=2), revisoes=5, lapsos=4,
        )
        for _ in range(3):
            seguinte = fsrs.proximo(duro, fsrs.BOM, hoje=(duro.ultima or HOJE) + timedelta(days=3))
            self.assertGreater(seguinte.estabilidade, duro.estabilidade)
            duro = seguinte

    def test_a_dificuldade_reverte_a_media_e_nao_gruda_no_minimo(self) -> None:
        estado = fsrs.estado_inicial("x", fsrs.DE_NOVO, hoje=HOJE)
        dia = HOJE
        for _ in range(12):
            dia += timedelta(days=1)
            estado = fsrs.proximo(estado, fsrs.FACIL, hoje=dia)
        self.assertGreaterEqual(estado.dificuldade, fsrs.DIFICULDADE_MINIMA)
        self.assertLessEqual(estado.dificuldade, fsrs.DIFICULDADE_MAXIMA)

    def test_nota_fora_da_escala_levanta(self) -> None:
        with self.assertRaises(ValueError):
            fsrs.estado_inicial("x", 7, hoje=HOJE)

    def test_estado_novo_recebido_por_proximo_vira_estado_inicial(self) -> None:
        vazio = fsrs.Estado(chave="x")
        self.assertTrue(vazio.novo)
        virou = fsrs.proximo(vazio, fsrs.BOM, hoje=HOJE)
        self.assertEqual("x", virou.chave)
        self.assertEqual(1, virou.revisoes)


class SumirPorUmMesTests(unittest.TestCase):
    """O caso que o item nomeia: o usuário some, e volta."""

    def test_acertar_depois_de_sumir_vale_mais_que_acertar_em_dia(self) -> None:
        """**A resposta nativa do modelo, e não uma regra à parte.** Lembrar de algo que se tinha
        40% de chance de lembrar prova mais que lembrar do que se sabia de cor, e é o `1 - R` que
        está nas duas fórmulas de estabilidade."""
        estado = fsrs.Estado(
            chave="x", estabilidade=10.0, dificuldade=5.0,
            vencimento=HOJE, ultima=HOJE - timedelta(days=10), revisoes=3,
        )
        em_dia = fsrs.proximo(estado, fsrs.BOM, hoje=HOJE)
        atrasado = fsrs.proximo(estado, fsrs.BOM, hoje=HOJE + timedelta(days=30))
        self.assertGreater(atrasado.estabilidade, em_dia.estabilidade)

    def test_o_dia_de_volta_nao_e_uma_parede(self) -> None:
        """Trezentos vencidos numa tela é o motivo pelo qual as pessoas abandonam repetição
        espaçada. O teto do dia adia o resto, e a agenda **diz** quantos ficaram."""
        estados = {
            f"i{n}": fsrs.Estado(
                chave=f"i{n}", estabilidade=5.0 + n, dificuldade=5.0,
                vencimento=HOJE - timedelta(days=30), ultima=HOJE - timedelta(days=60), revisoes=2,
            )
            for n in range(300)
        }
        agenda = fsrs.agenda(list(estados), estados, hoje=HOJE)
        self.assertEqual(fsrs.TETO_DO_DIA, agenda.quantos)
        self.assertEqual(300, agenda.vencidos)
        self.assertEqual(300 - fsrs.TETO_DO_DIA, agenda.adiados)


class AgendaTests(unittest.TestCase):
    """A fila do dia: quem entra, em que ordem, e quantos."""

    def _vencido(self, chave: str, *, estabilidade: float, atraso: int) -> fsrs.Estado:
        return fsrs.Estado(
            chave=chave, estabilidade=estabilidade, dificuldade=5.0,
            vencimento=HOJE - timedelta(days=atraso),
            ultima=HOJE - timedelta(days=atraso + int(estabilidade)),
            revisoes=2,
        )

    def test_o_mais_perdido_vem_antes_do_mais_antigo(self) -> None:
        """**A ordem é por retenção e não por data.** Dois itens vencidos há dez dias: um de
        intervalo três dias já foi esquecido, o de duzentos está intacto. Ordenar pela data
        gastaria a sessão de hoje no que não corria risco."""
        curto = self._vencido("curto", estabilidade=3.0, atraso=10)
        longo = self._vencido("longo", estabilidade=200.0, atraso=10)
        estados = {e.chave: e for e in (longo, curto)}
        agenda = fsrs.agenda(["longo", "curto"], estados, hoje=HOJE)
        self.assertEqual(("curto", "longo"), agenda.fila)

    def test_a_ordem_e_a_mesma_em_duas_chamadas(self) -> None:
        """Uma fila que se embaralha entre dois desenhos da tela é uma fila em que se perde o lugar."""
        estados = {f"i{n}": self._vencido(f"i{n}", estabilidade=5.0, atraso=5) for n in range(10)}
        primeira = fsrs.agenda(list(estados), estados, hoje=HOJE).fila
        self.assertEqual(primeira, fsrs.agenda(list(estados), estados, hoje=HOJE).fila)

    def test_vencidos_antes_de_novos(self) -> None:
        """Aprender coisa nova enquanto o que já se aprendeu está sendo esquecido é o jeito de ter
        um baralho grande e uma memória pequena."""
        estados = {"velho": self._vencido("velho", estabilidade=5.0, atraso=1)}
        agenda = fsrs.agenda(["novo1", "velho", "novo2"], estados, hoje=HOJE)
        self.assertEqual("velho", agenda.fila[0])
        self.assertEqual(2, agenda.novos)

    def test_o_teto_de_novos_e_menor_que_o_de_vencidos(self) -> None:
        """Cada novo de hoje é revisão de amanhã: cem novos por dia produzem a parede em duas semanas."""
        self.assertLess(fsrs.TETO_DE_NOVOS, fsrs.TETO_DO_DIA)
        agenda = fsrs.agenda([f"n{i}" for i in range(100)], {}, hoje=HOJE)
        self.assertEqual(fsrs.TETO_DE_NOVOS, agenda.quantos)
        self.assertEqual(0, agenda.adiados, "novo que não coube hoje não é atraso")

    def test_o_que_nao_venceu_nao_entra(self) -> None:
        futuro = fsrs.Estado(
            chave="x", estabilidade=30.0, dificuldade=5.0,
            vencimento=HOJE + timedelta(days=10), ultima=HOJE, revisoes=1,
        )
        agenda = fsrs.agenda(["x"], {"x": futuro}, hoje=HOJE)
        self.assertTrue(agenda.vazia)
        self.assertEqual(0, agenda.vencidos)

    def test_estado_sem_chave_conhecida_e_ignorado_em_silencio(self) -> None:
        """É o exercício de um livro que saiu da pasta; derrubar a sessão por causa dele seria
        trocar o treino por uma mensagem de erro."""
        estados = {"sumiu": self._vencido("sumiu", estabilidade=5.0, atraso=5)}
        self.assertTrue(fsrs.agenda(["outro"], estados, hoje=HOJE).fila == ("outro",))

    def test_a_agenda_vazia_diz_que_esta_vazia(self) -> None:
        self.assertTrue(fsrs.agenda([], {}, hoje=HOJE).vazia)


class NotaDoTreinoTests(unittest.TestCase):
    """A tradução do que aconteceu no tabuleiro para a escala do FSRS."""

    def test_acertar_de_primeira_e_bom(self) -> None:
        self.assertEqual(fsrs.BOM, fsrs.nota_do_treino(certo=True))

    def test_acertar_depois_de_errar_e_dificil(self) -> None:
        """Errar e corrigir não é o mesmo que não achar -- conta como acerto, com penalidade."""
        self.assertEqual(fsrs.DIFICIL, fsrs.nota_do_treino(certo=True, tentativas=2))

    def test_errar_e_ver_a_solucao_sao_a_mesma_nota(self) -> None:
        """Ver a resposta é não saber a resposta."""
        self.assertEqual(fsrs.DE_NOVO, fsrs.nota_do_treino(certo=False))
        self.assertEqual(fsrs.DE_NOVO, fsrs.nota_do_treino(certo=True, viu_a_solucao=True))

    def test_o_programa_nunca_da_facil_sozinho(self) -> None:
        """`FACIL` multiplica a estabilidade por `w16` e produz intervalos muito longos; concedê-lo
        a todo acerto de primeira esvaziaria a fila com base numa inferência que ninguém fez."""
        notas = {
            fsrs.nota_do_treino(certo=c, tentativas=t, viu_a_solucao=v)
            for c in (True, False)
            for t in (1, 2, 9)
            for v in (True, False)
        }
        self.assertNotIn(fsrs.FACIL, notas)

    def test_todo_rotulo_de_nota_existe_e_o_desconhecido_e_vazio(self) -> None:
        for nota in fsrs.NOTAS:
            self.assertTrue(fsrs.rotulo_da_nota(nota))
        self.assertEqual("", fsrs.rotulo_da_nota(9))


class ArquivoTests(unittest.TestCase):
    """Um arquivo para o acervo inteiro, e a ida e volta sem perda."""

    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)
        self.caminho = self.pasta / "revisao.json"

    def _baralho(self, quantos: int = 3) -> dict[str, fsrs.Estado]:
        return {
            f"livro.pdf#{n}#0": fsrs.proximo(
                fsrs.estado_inicial(f"livro.pdf#{n}#0", fsrs.BOM, hoje=HOJE),
                fsrs.DIFICIL,
                hoje=HOJE + timedelta(days=4),
            )
            for n in range(quantos)
        }

    def test_a_ida_e_volta_nao_perde_o_historico(self) -> None:
        """**Estável e não idêntica**, e a diferença é a quarta casa decimal: `para_json` arredonda
        a estabilidade em 0,0001 dia (8,6 segundos), que é o que mantém o arquivo legível. O que
        não pode mudar é o que se lê de volta -- e uma segunda gravação dá byte a byte o mesmo
        arquivo, que é a propriedade que importa para um arquivo relido todo dia."""
        baralho = self._baralho()
        revisao_arquivo.gravar(baralho, caminho=self.caminho)
        primeira = self.caminho.read_bytes()
        lido = revisao_arquivo.carregar(caminho=self.caminho)
        self.assertEqual(sorted(baralho), sorted(lido))
        um = next(iter(baralho.values()))
        outro = lido[um.chave]
        self.assertEqual(um.vencimento, outro.vencimento)
        self.assertEqual(um.historico, outro.historico)
        self.assertEqual(2, len(outro.historico))
        self.assertAlmostEqual(um.estabilidade, outro.estabilidade, places=3)
        revisao_arquivo.gravar(lido, caminho=self.caminho)
        self.assertEqual(primeira, self.caminho.read_bytes())

    def test_arquivo_ausente_e_baralho_vazio(self) -> None:
        self.assertEqual({}, revisao_arquivo.carregar(caminho=self.pasta / "nunca.json"))

    def test_baralho_vazio_grava_e_nao_ressuscita_o_antigo(self) -> None:
        """**A diferença para a sala de estudo**: aqui o vazio pode querer dizer "apaguei o
        histórico", e deixar o arquivo antigo o traria de volta na abertura seguinte."""
        revisao_arquivo.gravar(self._baralho(), caminho=self.caminho)
        revisao_arquivo.gravar({}, caminho=self.caminho)
        self.assertTrue(self.caminho.exists())
        self.assertEqual({}, revisao_arquivo.carregar(caminho=self.caminho))

    def test_um_item_corrompido_nao_derruba_os_outros(self) -> None:
        """É o único dado deste programa que não se refaz varrendo o livro de novo."""
        revisao_arquivo.gravar(self._baralho(3), caminho=self.caminho)
        dados = json.loads(self.caminho.read_text(encoding="utf-8"))
        dados["itens"][0]["vencimento"] = "isto-nao-e-data"
        self.caminho.write_text(json.dumps(dados), encoding="utf-8")
        self.assertEqual(2, len(revisao_arquivo.carregar(caminho=self.caminho)))

    def test_esquema_do_futuro_nao_e_lido_pela_metade(self) -> None:
        self.caminho.write_text(json.dumps({"esquema": 99, "itens": []}), encoding="utf-8")
        self.assertEqual({}, revisao_arquivo.carregar(caminho=self.caminho))

    def test_mil_itens_com_vinte_revisoes_cabem_em_tres_megabytes(self) -> None:
        """**A medição que justifica guardar o log inteiro** (S-540): ele é a entrada do
        otimizador do FSRS, e jogá-lo fora fecharia a porta para calibrar os pesos. Medido em
        2026-09-04: 1.000 itens com 20 revisões cada dão **2,1 MB** de JSON indentado, lido em
        milissegundos. É mais que a sala de estudo inteira de um livro, e ainda assim é pequeno
        para o que ele guarda -- meses de revisão que não se refazem varrendo o livro de novo."""
        baralho: dict[str, fsrs.Estado] = {}
        for n in range(1000):
            chave = f"livro.pdf#{n}#0"
            estado = fsrs.estado_inicial(chave, fsrs.BOM, hoje=HOJE)
            for volta in range(19):
                estado = fsrs.proximo(estado, fsrs.BOM, hoje=HOJE + timedelta(days=volta + 1))
            baralho[chave] = estado
        revisao_arquivo.gravar(baralho, caminho=self.caminho)
        tamanho = self.caminho.stat().st_size
        self.assertLess(tamanho, 3_000_000, f"o baralho ficou com {tamanho} bytes")
        self.assertEqual(1000, len(revisao_arquivo.carregar(caminho=self.caminho)))

    def test_a_gravacao_e_atomica(self) -> None:
        from pathlib import Path

        fonte = Path(revisao_arquivo.__file__).read_text(encoding="utf-8")
        self.assertIn("atomic_write_json", fonte)
        self.assertNotIn("write_text(", fonte)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
