"""O orçamento por página, e o teto que a varredura respeita (S-215).

**O que um teste pode travar aqui, e o que não pode.** Quanto uma página custa é medição, e ela
mora em `docs/metrics/texto_custo_*.json` -- nenhum número de relógio entra em `assertEqual`, e um
teste que o fizesse ficaria vermelho na primeira máquina lenta. O que se trava é o instrumento: o
alvo de cada etapa existindo, o envoltório sendo desfeito, a soma das etapas não passando do
relógio, a política saindo do fator, a amostra não sendo das primeiras páginas, e o `--baseline`
reprovando quando o custo piora.
"""

from __future__ import annotations

import unittest
from time import sleep

import numpy as np

from chess_diagram_ocr.text import custo
from chess_diagram_ocr.text.custo import (
    ETAPAS,
    MARGEM_PADRAO,
    NOMES,
    RESIDUO,
    TOTAL,
    Cronometro,
    Etapa,
    Perfil,
    comparar,
    horas_para_o_acervo,
    medindo,
    politica_para,
)


def pagina_sintetica(largura: int = 240, altura: int = 120) -> np.ndarray:
    """Uma folha branca com barras pretas: componentes de sobra para a segmentação achar."""
    imagem = np.full((altura, largura, 3), 255, dtype=np.uint8)
    for coluna in range(10, largura - 10, 12):
        imagem[30:48, coluna : coluna + 5] = 0
        imagem[70:88, coluna : coluna + 5] = 0
    return imagem


class AlvoTests(unittest.TestCase):
    """As nove etapas apontam para alguma coisa que existe."""

    def test_cada_etapa_aponta_para_um_alvo_que_existe(self) -> None:
        """Pega o rename silencioso: um alvo que sumiu mede zero e não avisa."""
        for etapa in ETAPAS:
            for alvo in etapa.alvos:
                with self.subTest(alvo=alvo):
                    dono, nome = custo._alcancar(alvo)
                    self.assertTrue(
                        hasattr(dono, nome),
                        f"{alvo} não existe -- a etapa mediria zero em silêncio.",
                    )
                    self.assertTrue(callable(getattr(dono, nome)))

    def test_os_nomes_das_etapas_sao_unicos(self) -> None:
        self.assertEqual(len(NOMES), len(set(NOMES)))

    def test_nenhum_alvo_e_declarado_duas_vezes(self) -> None:
        """Dois envoltórios no mesmo atributo: o segundo embrulha o primeiro, e a restauração
        devolveria o **envoltório** em vez da função original -- que sobreviveria ao `with` e
        mediria a página seguinte no cronômetro da anterior."""
        alvos = [alvo for etapa in ETAPAS for alvo in etapa.alvos]
        self.assertEqual(sorted(set(alvos)), sorted(alvos))

    def test_toda_etapa_tem_pelo_menos_um_alvo(self) -> None:
        """Etapa sem alvo mede zero para sempre, e a tabela a mostraria como se fosse barata."""
        for etapa in ETAPAS:
            with self.subTest(etapa=etapa.nome):
                self.assertTrue(etapa.alvos)

    def test_o_residuo_nao_colide_com_etapa(self) -> None:
        """`nao_instrumentado` é linha do perfil, e não pode ser também nome de etapa."""
        self.assertNotIn(RESIDUO, NOMES)


class CronometroTests(unittest.TestCase):
    def test_a_moldura_aninhada_e_descontada_da_de_fora(self) -> None:
        """O tempo exclusivo é o item: sem desconto, `colados` e `classificacao` contariam duas vezes."""
        relogio = Cronometro()
        with relogio.moldura("colados"):
            sleep(0.02)
            with relogio.moldura("classificacao"):
                sleep(0.05)
        self.assertGreater(relogio.segundos["classificacao"], 0.02)
        self.assertLess(
            relogio.segundos["colados"],
            relogio.segundos["classificacao"],
            "a moldura de fora não descontou a de dentro",
        )

    def test_o_residuo_nunca_e_negativo(self) -> None:
        relogio = Cronometro()
        relogio.segundos["coluna"] = 5.0
        relogio.total = 1.0
        self.assertEqual(0.0, relogio.residuo)


# Um par de funções onde uma chama a outra, para exercitar o envoltório de verdade -- e não só a
# `moldura`. Ficam no módulo de teste porque `medindo` aceita `etapas=`, que existe justamente
# para isto: o instrumento tem de poder ser apontado para outro alvo sem mexer em `ETAPAS`.
def _de_dentro() -> int:
    sleep(0.02)
    return 1


def _de_fora() -> int:
    sleep(0.01)
    return _de_dentro() + 1


# `__name__` e nao a string literal: sob o pytest deste projeto o modulo se chama
# `test_texto_custo` (nao ha `tests/__init__.py`), e `import_module("tests.test_texto_custo")`
# carregaria uma **segunda copia** -- o envoltorio iria para ela, e o alvo que roda ficaria
# intacto. E o mesmo erro que `ETAPAS` evita ao declarar onde o nome e PROCURADO.
ETAPAS_DE_TESTE = (
    Etapa("coluna", (f"{__name__}:_de_fora",), "pagina"),
    Etapa("contornos", (f"{__name__}:_de_dentro",), "pagina"),
)


class MedindoTests(unittest.TestCase):
    def test_o_envoltorio_e_desfeito_ao_sair(self) -> None:
        """Envoltório pendurado faria a página seguinte medir o cronômetro da anterior."""
        antes = [custo._alcancar(alvo) for e in ETAPAS for alvo in e.alvos]
        originais = [getattr(dono, nome) for dono, nome in antes]
        with medindo():
            trocados = [getattr(dono, nome) for dono, nome in antes]
            self.assertNotEqual(originais, trocados, "nada foi envolvido")
        depois = [getattr(dono, nome) for dono, nome in antes]
        self.assertEqual(originais, depois)

    def test_o_envoltorio_e_desfeito_mesmo_quando_o_corpo_estoura(self) -> None:
        dono, nome = custo._alcancar(ETAPAS[0].alvos[0])
        original = getattr(dono, nome)
        with self.assertRaises(RuntimeError):
            with medindo():
                raise RuntimeError("a medição estourou no meio")
        self.assertIs(original, getattr(dono, nome))

    def test_a_funcao_envolvida_devolve_o_que_a_original_devolvia(self) -> None:
        with medindo(ETAPAS_DE_TESTE):
            self.assertEqual(2, _de_fora())

    def test_o_aninhamento_real_tambem_e_descontado(self) -> None:
        """O mesmo desconto da `moldura`, agora pelo caminho que o comando usa."""
        with medindo(ETAPAS_DE_TESTE) as relogio:
            _de_fora()
        self.assertGreater(relogio.segundos["contornos"], 0.0)
        self.assertLess(relogio.segundos["coluna"], relogio.segundos["contornos"])

    def test_a_soma_das_etapas_nao_passa_do_total(self) -> None:
        """Resíduo negativo é erro de contabilidade, e é o que este teste existe para pegar."""
        with medindo(ETAPAS_DE_TESTE) as relogio:
            _de_fora()
        self.assertLessEqual(sum(relogio.segundos.values()), relogio.total + 1e-6)
        self.assertGreaterEqual(relogio.residuo, 0.0)


class PerfilDeUmaLeituraTests(unittest.TestCase):
    """O perfil separa as etapas numa segmentação de verdade, sem PDF e sem modelo."""

    def test_o_perfil_separa_as_etapas(self) -> None:
        from chess_diagram_ocr.text import leitor

        with medindo() as relogio:
            leitor.segmentar(pagina_sintetica())
            leitor.montar([], [], escala_px=1.0)

        perfil = Perfil.de_cronometro(relogio, paginas=1)
        for etapa in ("binarizacao", "contornos", "coluna"):
            with self.subTest(etapa=etapa):
                self.assertGreater(
                    perfil.chamadas[etapa],
                    0.0,
                    f"a etapa {etapa} não foi alcançada -- o alvo em ETAPAS não é onde o nome é procurado",
                )
        self.assertEqual(0.0, perfil.chamadas["renderizacao"], "nada renderizou nesta leitura")
        self.assertGreaterEqual(perfil.etapas[RESIDUO], 0.0)

    def test_o_perfil_divide_pelas_paginas(self) -> None:
        relogio = Cronometro()
        relogio.segundos["coluna"] = 4.0
        relogio.chamadas["coluna"] = 8
        relogio.total = 4.0
        perfil = Perfil.de_cronometro(relogio, paginas=4)
        self.assertAlmostEqual(1.0, perfil.etapas["coluna"])
        self.assertAlmostEqual(2.0, perfil.chamadas["coluna"])
        self.assertEqual(4, perfil.paginas)

    def test_a_maior_etapa_ignora_o_residuo(self) -> None:
        """O resíduo não é etapa: apontá-lo como gargalo mandaria otimizar o que não se mediu."""
        relogio = Cronometro()
        relogio.segundos["coluna"] = 1.0
        relogio.total = 100.0
        self.assertEqual("coluna", Perfil.de_cronometro(relogio, 1).maior_etapa)


class PoliticaTests(unittest.TestCase):
    """A política sai do fator, e não do gosto de quem escreve o relatório."""

    def test_ate_uma_vez_e_meia_o_texto_entra_na_varredura(self) -> None:
        self.assertEqual("varredura", politica_para(1.0)[0])
        self.assertEqual("varredura", politica_para(1.5)[0])

    def test_entre_uma_e_meia_e_quatro_o_texto_e_sob_demanda(self) -> None:
        self.assertEqual("sob-demanda", politica_para(1.51)[0])
        self.assertEqual("sob-demanda", politica_para(4.0)[0])

    def test_acima_de_quatro_o_texto_sai_da_varredura(self) -> None:
        self.assertEqual("comando-separado", politica_para(4.01)[0])
        self.assertEqual("comando-separado", politica_para(float("inf"))[0])

    def test_a_frase_acompanha_a_chave(self) -> None:
        """O JSON grava as duas, e a tela mostra a frase: elas não podem se soltar."""
        for chave, teto, frase in custo.POLITICAS:
            with self.subTest(politica=chave):
                escolhida = politica_para(teto)
                self.assertEqual((chave, frase), escolhida)


class UnidadesTests(unittest.TestCase):
    def test_as_horas_saem_dos_segundos_e_das_paginas(self) -> None:
        self.assertAlmostEqual(1.0, horas_para_o_acervo(3600.0, paginas=1))
        self.assertAlmostEqual(10.0, horas_para_o_acervo(3.0, paginas=12_000))

    def test_o_relatorio_traz_as_duas_unidades(self) -> None:
        """Critério de aceite do item: segundos por página **e** horas para o acervo."""
        from chess_diagram_ocr.cli.texto_custo import relatorio

        relogio = Cronometro()
        relogio.segundos["classificacao"] = 2.0
        relogio.total = 3.0
        tabela, dados = relatorio(
            Perfil.de_cronometro(relogio, paginas=1),
            hoje_por_pagina=3.0,
            paginas_do_acervo=12_000,
        )
        self.assertIn("s/página", tabela)
        self.assertIn("h/acervo", tabela)
        for chave in ("segundos_por_pagina", "horas_total", "hoje_por_pagina", "texto_por_pagina"):
            with self.subTest(chave=chave):
                self.assertIn(chave, dados)
        self.assertAlmostEqual(10.0, dados["horas_hoje"], places=2)

    def test_a_politica_escolhida_viaja_com_o_numero_que_a_escolheu(self) -> None:
        """Critério de aceite: a política registrada **com** o fator que a decidiu."""
        from chess_diagram_ocr.cli.texto_custo import relatorio

        relogio = Cronometro()
        relogio.segundos["classificacao"] = 8.0
        relogio.total = 8.0
        _, dados = relatorio(Perfil.de_cronometro(relogio, 1), hoje_por_pagina=2.0, paginas_do_acervo=100)
        self.assertAlmostEqual(5.0, dados["fator"], places=2)
        self.assertEqual("comando-separado", dados["politica"])
        self.assertEqual(custo.politica_para(dados["fator"])[1], dados["politica_frase"])

    def test_a_renderizacao_e_a_deteccao_nao_sao_contadas_duas_vezes(self) -> None:
        """As duas rodam nos dois lados da divisão, e a varredura de hoje já as paga."""
        from chess_diagram_ocr.cli.texto_custo import relatorio

        relogio = Cronometro()
        relogio.segundos["renderizacao"] = 1.0
        relogio.segundos["deteccao"] = 2.0
        relogio.segundos["classificacao"] = 4.0
        relogio.total = 7.0
        _, dados = relatorio(Perfil.de_cronometro(relogio, 1), hoje_por_pagina=3.0, paginas_do_acervo=100)
        self.assertAlmostEqual(4.0, dados["texto_por_pagina"], places=3)
        self.assertAlmostEqual(7.0, dados["total_por_pagina"], places=3)


class BaselineTests(unittest.TestCase):
    """A trava: regressão de desempenho é regressão."""

    def arquivado(self, segundos: float = 1.0, **etapas: float) -> dict[str, object]:
        return {TOTAL: segundos, "etapas": {"classificacao": 0.5, "coluna": 0.2, **etapas}}

    def perfil(self, segundos: float, **etapas: float) -> Perfil:
        relogio = Cronometro()
        for nome, valor in etapas.items():
            relogio.segundos[nome] = valor
        relogio.total = segundos
        return Perfil.de_cronometro(relogio, paginas=1)

    def test_o_baseline_falha_quando_o_custo_piora(self) -> None:
        pioras = comparar(self.arquivado(1.0), self.perfil(2.0, classificacao=0.5, coluna=0.2))
        self.assertTrue(pioras, "o dobro do custo por página passou sem acusar")
        self.assertEqual(TOTAL, pioras[0].onde)
        self.assertAlmostEqual(2.0, pioras[0].fator, places=3)

    def test_o_baseline_passa_dentro_da_margem(self) -> None:
        """Relógio de parede não repete o valor: a margem é o que separa ruído de regressão."""
        igual = self.perfil(1.0 + MARGEM_PADRAO / 2, classificacao=0.5, coluna=0.2)
        self.assertEqual([], comparar(self.arquivado(1.0), igual))

    def test_o_baseline_nomeia_a_etapa_que_piorou(self) -> None:
        """"O total piorou" manda procurar; "classificacao piorou 3x" manda consertar."""
        pioras = comparar(self.arquivado(1.0), self.perfil(1.0, classificacao=1.5, coluna=0.2))
        self.assertEqual(["classificacao"], [p.onde for p in pioras])

    def test_uma_etapa_nova_nao_reprova_a_medicao(self) -> None:
        """Comparar etapa nova contra zero acusaria toda corrida que declarasse uma."""
        antigo = {TOTAL: 1.0, "etapas": {"coluna": 0.2}}
        self.assertEqual([], comparar(antigo, self.perfil(1.0, coluna=0.2, leitura_de_linha=9.0)))

    def test_baseline_estragado_nao_reprova_nada(self) -> None:
        """Campo faltando ou não-numérico é "não dá para comparar", e não "piorou"."""
        self.assertEqual([], comparar({}, self.perfil(9.0, coluna=9.0)))
        self.assertEqual([], comparar({TOTAL: "muito"}, self.perfil(9.0, coluna=9.0)))
        self.assertEqual([], comparar({TOTAL: 1.0, "etapas": []}, self.perfil(1.0, coluna=9.0)))

    def test_o_residuo_nunca_reprova(self) -> None:
        """Ele é o que a medição não conhece, e cobrar dele mandaria otimizar o desconhecido."""
        antigo = {TOTAL: 10.0, "etapas": {RESIDUO: 0.01}}
        self.assertEqual([], comparar(antigo, self.perfil(1.0, coluna=0.0)))

    def test_a_piora_se_le_numa_linha(self) -> None:
        pioras = comparar(self.arquivado(1.0), self.perfil(3.0, classificacao=0.5, coluna=0.2))
        self.assertIn("3.00x", str(pioras[0]))


class AmostraTests(unittest.TestCase):
    def test_a_amostra_nao_e_das_primeiras_paginas(self) -> None:
        """A lição que a S-214 registra: as N primeiras páginas são o rosto, não o livro."""
        from chess_diagram_ocr.cli.texto_custo import paginas_amostradas

        indices = paginas_amostradas(400, 3)
        self.assertEqual([100, 200, 300], indices)
        self.assertNotIn(0, indices)

    def test_a_amostra_cabe_no_livro(self) -> None:
        from chess_diagram_ocr.cli.texto_custo import paginas_amostradas

        for total in (1, 2, 3, 7, 50):
            with self.subTest(total=total):
                indices = paginas_amostradas(total, 3)
                self.assertTrue(indices)
                self.assertTrue(all(0 <= i < total for i in indices))
                self.assertEqual(sorted(set(indices)), indices)

    def test_livro_vazio_nao_amostra_nada(self) -> None:
        from chess_diagram_ocr.cli.texto_custo import paginas_amostradas

        self.assertEqual([], paginas_amostradas(0, 3))
        self.assertEqual([], paginas_amostradas(10, 0))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
