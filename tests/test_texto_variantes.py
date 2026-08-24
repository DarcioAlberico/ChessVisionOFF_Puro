"""A grade de variantes: o que ela compara, e a regra que a torna uma comparação (S-204).

**A regra é uma só: a grade roda no `val`, e o `test` é tocado uma vez, pela vencedora.** A S-204
mediu o preço de ignorá-la — nos pesos de classe o ganho no `val` foi sete vezes o do `test`,
porque a época é escolhida *porque* maximiza a macro do `val`.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from chess_diagram_ocr.cli import texto_variantes as gv
from chess_diagram_ocr.text.modelo import ARQUITETURA_PADRAO, Arquitetura


def _base_sintetica(n_classes: int = 4, por_classe: int = 60, semente: int = 0):
    aleatorio = np.random.default_rng(semente)
    X = np.empty((n_classes * por_classe, 32 * 32), dtype=np.uint8)
    y = np.empty(n_classes * por_classe, dtype=np.int32)
    for classe in range(n_classes):
        fatia = slice(classe * por_classe, (classe + 1) * por_classe)
        X[fatia] = np.clip(aleatorio.normal(30 + classe * 50, 6, (por_classe, 32 * 32)), 0, 255).astype(np.uint8)
        y[fatia] = classe
    return X, y


class BracosTests(unittest.TestCase):
    def test_o_controle_existe_e_nao_muda_nada(self) -> None:
        """Sem ele a tabela não tem zero, e nenhum ganho é ganho contra coisa nenhuma."""
        controle = gv.POR_NOME["controle"]
        self.assertEqual("desligado", controle.aumento)
        self.assertFalse(controle.pesos_de_classe)
        self.assertEqual(ARQUITETURA_PADRAO, controle.arquitetura)

    def test_cada_braco_muda_uma_coisa_so_em_relacao_ao_controle(self) -> None:
        """Dois eixos ao mesmo tempo produzem uma linha que não atribui o ganho a nada."""
        for braco in gv.BRACOS:
            if braco.nome == "controle":
                continue
            with self.subTest(braco=braco.nome):
                mudancas = sum(
                    (
                        braco.aumento != "desligado",
                        braco.pesos_de_classe,
                        braco.arquitetura != ARQUITETURA_PADRAO,
                    )
                )
                self.assertEqual(1, mudancas, f"{braco.nome} muda {mudancas} eixos")

    def test_nenhum_braco_espelha(self) -> None:
        """Espelhar caractere troca `b` por `d`: não há braço, e não pode haver."""
        for braco in gv.BRACOS:
            with self.subTest(braco=braco.nome):
                self.assertNotIn("espelh", braco.nome)
                self.assertNotIn("flip", braco.nome)

    def test_o_braco_de_arquitetura_declara_os_parametros(self) -> None:
        """É a hipótese da S-204 em número: a densa 2.048→256 são 85% dos parâmetros."""
        menor = gv.POR_NOME["canais-menores"].como_dicionario()
        controle = gv.POR_NOME["controle"].como_dicionario()
        self.assertLess(menor["parametros"], controle["parametros"] / 3)


class ArquiteturaTests(unittest.TestCase):
    """A forma virou dado porque a grade a muda, e o metadado tem de dizer qual carregar."""

    def test_a_forma_padrao_e_a_do_porte_literal(self) -> None:
        self.assertEqual((32, 64, 128), ARQUITETURA_PADRAO.canais)
        self.assertEqual(256, ARQUITETURA_PADRAO.densa)

    def test_a_densa_domina_a_contagem_de_parametros(self) -> None:
        """A hipótese que o braço `densa-128` testa, afirmada aqui em aritmética."""
        so_densa = 128 * 4 * 4 * 256 + 256
        self.assertGreater(so_densa / ARQUITETURA_PADRAO.parametros, 0.8)

    def test_a_versao_separa_duas_formas(self) -> None:
        self.assertNotEqual(ARQUITETURA_PADRAO.versao, Arquitetura(densa=128).versao)

    def test_metadado_sem_arquitetura_carrega_como_a_padrao(self) -> None:
        """O par publicado é de antes da grade, e ele descreve exatamente a forma padrão."""
        self.assertEqual(ARQUITETURA_PADRAO, Arquitetura.de_dicionario(None))

    def test_arquitetura_malformada_levanta(self) -> None:
        from chess_diagram_ocr.text.modelo import ModeloInvalido

        for ruim in ({"canais": [1, 2], "densa": 8}, {"canais": [1, 2, 3], "densa": 0}):
            with self.subTest(ruim=ruim), self.assertRaises(ModeloInvalido):
                Arquitetura.de_dicionario(ruim)


class RelatorioTests(unittest.TestCase):
    """A tabela, e a ressalva que tem de viajar com ela."""

    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.saida = Path(self.tmp.name) / "grade.json"

    def _rodar(self, bracos: list[str]) -> dict:
        X, y = _base_sintetica()
        base = Path(self.tmp.name) / "base"
        base.mkdir(exist_ok=True)

        args = gv.parse_args(
            ["--bracos", *bracos, "--epocas", "1", "--lote", "64", "--saida", str(self.saida)]
        )
        indices = np.arange(y.size)
        preparo = gv.Preparo(
            varredura=type("V", (), {"X": X, "y": y, "classes": [type("C", (), {"pasta": f"c{i}"})() for i in range(4)]})(),
            grupos=np.arange(y.size),
            lado=np.zeros(y.size, np.int8),
            idx_treino=indices,
            idx_val=indices,
            idx_teste=indices,
            classes_sem_teste=["c3"],
        )
        linhas = [gv.rodar_braco(gv.POR_NOME[nome], preparo, args) for nome in bracos]
        vencedora = max(linhas, key=lambda linha: linha["val_macro"])
        gv._gravar(args, preparo, linhas, vencedora, {"macro": 0.5, "acuracia": 0.5, "amostras": 240})
        return json.loads(self.saida.read_text(encoding="utf-8"))

    def test_a_ressalva_do_orcamento_viaja_com_a_tabela(self) -> None:
        """Publicar a tabela sem ela faria a vencedora parecer a que deve ir para produção."""
        relatorio = self._rodar(["controle"])
        self.assertIn("orcamento", relatorio["ressalva"])
        self.assertIn("epocas", relatorio["orcamento"])

    def test_so_a_vencedora_aparece_com_numero_de_teste(self) -> None:
        """O `test` é tocado uma vez. Uma tabela com teste por braço seria outra régua, gasta."""
        relatorio = self._rodar(["controle", "densa-128"])
        self.assertEqual(relatorio["vencedora_no_val"], relatorio["confirmacao_no_teste"]["braco"])
        for braco in relatorio["bracos"]:
            with self.subTest(braco=braco["nome"]):
                self.assertNotIn("teste_macro", braco)

    def test_a_tabela_sai_ordenada_pela_metrica_que_decide(self) -> None:
        relatorio = self._rodar(["controle", "densa-128"])
        macros = [braco["val_macro"] for braco in relatorio["bracos"]]
        self.assertEqual(sorted(macros, reverse=True), macros)

    def test_as_classes_sem_teste_saem_nomeadas(self) -> None:
        """A decisão que a S-204 pede: elas podem ser emitidas e ninguém mediu se acertam."""
        relatorio = self._rodar(["controle"])
        self.assertEqual(1, relatorio["classes_sem_teste"]["quantas"])
        self.assertEqual(["c3"], relatorio["classes_sem_teste"]["quais"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
