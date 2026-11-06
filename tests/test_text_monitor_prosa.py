"""O monitor sem referência (S-763): sinais com tokens sintéticos e o canário com um medidor falso. **Nenhuma folha de livro aqui**: o que é de livro fica fora do repositório."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr.cli import texto_prosa
from chess_diagram_ocr.text import confianca_palavra as cp
from chess_diagram_ocr.text import fusao, monitor_prosa

RAIZ = Path(__file__).resolve().parents[1]


def existe(token: str) -> bool:
    return token in {"the", "king", "moves"}


def t(texto: str, do_glifo: str | None = None, conf: float | None = 0.96) -> fusao.Token:
    return fusao.Token(texto, "outro", texto if do_glifo is None else do_glifo, conf, texto)


class SinaisTests(unittest.TestCase):
    def test_a_concordancia_conta_so_a_prosa(self) -> None:
        linhas = [[t("the"), t("king", do_glifo="kirg"), t("Nf3", do_glifo="♘f3")]]
        self.assertEqual(monitor_prosa.concordancia(linhas), 0.5)

    def test_sem_prosa_nao_ha_o_que_discordar(self) -> None:
        self.assertEqual(monitor_prosa.concordancia([[t("Nf3", do_glifo="♘f3")]]), 1.0)
        self.assertEqual(monitor_prosa.erro_estimado([[t("Nf3")]], existe=existe, dominio=cp.DIGITAL), 0.0)
        self.assertEqual(monitor_prosa.fracao_acima_do_corte([], existe=existe, dominio=cp.DIGITAL), 0.0)

    def test_o_erro_estimado_sobe_com_a_folha_ruim(self) -> None:
        boa = [[t("the"), t("king"), t("moves")]]
        ruim = [[t("tne", do_glifo="the", conf=0.3), t("kirg", do_glifo="king", conf=0.3), t("moves")]]
        self.assertLess(monitor_prosa.erro_estimado(boa, existe=existe, dominio=cp.DIGITAL), monitor_prosa.erro_estimado(ruim, existe=existe, dominio=cp.DIGITAL))

    def test_a_fracao_acima_do_corte_e_a_da_marca(self) -> None:
        ruim = [[t("tne", do_glifo="the", conf=0.3), t("the")]]
        erros = cp.erros_da_folha(ruim, existe=existe, dominio=cp.DIGITAL)
        esperada = sum(len(m) for m in fusao.marcar_por_erro(erros, fusao.CORTE_DE_REVISAR[fusao.V5])) / 2
        self.assertEqual(monitor_prosa.fracao_acima_do_corte(ruim, existe=existe, dominio=cp.DIGITAL), esperada)


class AlarmeTests(unittest.TestCase):
    def test_sinal_que_nao_passou_na_medicao_nao_dispara(self) -> None:
        """Nenhum dos quatro passou da regra no dev: ver `docs/metrics/texto_confianca_2026-11-06.json`. Se um entrar, é com medida."""
        self.assertEqual(monitor_prosa.ALARMES, {})
        self.assertEqual(monitor_prosa.alarmes_da_folha({"discordancia": 0.99, "densidade": 9.0}, cp.DIGITAL), ())

    def test_o_alarme_da_tabela_dispara_no_corte(self) -> None:
        with mock.patch.object(monitor_prosa, "ALARMES", {cp.SCAN: {"densidade": 0.5}}):
            self.assertEqual(monitor_prosa.alarmes_da_folha({"densidade": 0.5}, cp.SCAN), ("densidade",))
            self.assertEqual(monitor_prosa.alarmes_da_folha({"densidade": 0.4}, cp.SCAN), ())
            self.assertEqual(monitor_prosa.alarmes_da_folha({"densidade": 0.9}, cp.DIGITAL), ())

    def test_o_publicado_bate_com_a_tabela(self) -> None:
        """Quem escreve na tabela sem medir é pego: um sinal em `ALARMES` tem de estar com `vira_alarme` no relatório."""
        relatorio = json.loads((RAIZ / "docs" / "metrics" / "texto_confianca_2026-11-06.json").read_text(encoding="utf-8"))
        for dominio, bloco in relatorio["s763_monitor"]["sinais_por_dominio"].items():
            aprovados = {nome for nome, sinal in bloco["sinais"].items() if sinal["vira_alarme"]}
            self.assertEqual(aprovados, set(monitor_prosa.ALARMES.get(dominio, {})), dominio)


class CanarioTests(unittest.TestCase):
    FOLHA = monitor_prosa.FolhaCanario("abc", 7, "por", 0.001)

    def test_a_mesma_versao_nao_alarma(self) -> None:
        resultado = monitor_prosa.conferir_canario([self.FOLHA], lambda _f: 0.001)
        self.assertFalse(resultado[0].alarme)

    def test_a_regressao_alarma_e_a_folga_nao(self) -> None:
        self.assertTrue(monitor_prosa.conferir_canario([self.FOLHA], lambda _f: 0.001 + monitor_prosa.MARGEM_DO_CANARIO + 1e-6)[0].alarme)
        self.assertFalse(monitor_prosa.conferir_canario([self.FOLHA], lambda _f: 0.001 + monitor_prosa.MARGEM_DO_CANARIO)[0].alarme)

    def test_o_rotulo_diz_que_nao_e_humano_e_o_manifesto_e_obrigado_a_dizer(self) -> None:
        self.assertIn("não humano", monitor_prosa.ROTULO_DO_CANARIO)
        caminho = pasta_temporaria(self) / "canario.json"
        caminho.write_text(json.dumps({"rotulo": "referência humana", "folhas": []}), encoding="utf-8")
        with self.assertRaises(ValueError):
            monitor_prosa.carregar_canario(caminho)

    def test_o_manifesto_versionado_so_tem_identidades_e_numeros(self) -> None:
        folhas = monitor_prosa.carregar_canario()
        self.assertEqual({f.lingua for f in folhas}, {"eng", "por"})
        dados = json.loads(monitor_prosa.caminho_do_canario().read_text(encoding="utf-8"))
        self.assertEqual(set(dados), {"rotulo", "nota", "folhas"})
        for folha in dados["folhas"]:
            self.assertEqual(set(folha), {"identidade", "folha", "lingua", "motor", "cer_de_base"})

    def test_a_folha_do_canario_e_do_dev_e_nunca_do_teste(self) -> None:
        from chess_diagram_ocr.text import ouro

        dev = {f.identidade for f in ouro.carregar().do_split("dev")}
        for folha in monitor_prosa.carregar_canario():
            self.assertIn(folha.identidade, dev)

    def test_o_relatorio_nao_leva_texto(self) -> None:
        relatorio = monitor_prosa.para_relatorio(monitor_prosa.conferir_canario([self.FOLHA], lambda _f: 0.5))
        self.assertEqual(relatorio["rotulo"], monitor_prosa.ROTULO_DO_CANARIO)
        self.assertEqual(set(relatorio["folhas"][0]), {"identidade", "folha", "lingua", "motor", "cer_de_base", "cer", "alarme"})

    def test_o_comando_sai_com_um_no_alarme(self) -> None:
        def relatorio(alarme: bool) -> dict[str, object]:
            return {"rotulo": monitor_prosa.ROTULO_DO_CANARIO, "folhas": [{"lingua": "por", "identidade": "abc", "folha": 7, "motor": "fusao", "cer_de_base": 0.0, "cer": 0.5, "alarme": alarme}]}

        for alarme, codigo in ((True, 1), (False, 0)):
            with mock.patch.object(texto_prosa, "conferir_o_canario", return_value=relatorio(alarme)):
                self.assertEqual(texto_prosa.main(["--canario"]), codigo)


if __name__ == "__main__":
    unittest.main()
