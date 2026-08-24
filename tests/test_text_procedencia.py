"""De onde veio cada recorte: o contrato do arquivo, e a regra que ele carrega (S-201/S-203).

O item existe por causa do achado nº 1 da avaliação de 2026-08-18 deste projeto: **a verdade de
referência era a leitura do próprio modelo**. A regra que fecha essa porta é de uma linha --
rótulo que ninguém conferiu não mede o modelo -- e o resto é fazer com que ela seja conferível.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from chess_diagram_ocr.text import procedencia as pr

CABECALHO = "uuid,livro,pagina,procedencia,rotulado_em\n"


class LeituraTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.csv = Path(self.tmp.name) / "texto_procedencia.csv"

    def _escrever(self, corpo: str) -> Path:
        self.csv.write_text(CABECALHO + corpo, encoding="utf-8")
        return self.csv

    def test_arquivo_ausente_nao_e_erro_e_devolve_vazio(self) -> None:
        """É o estado de hoje e o de todo clone: o arquivo depende de trabalho na origem."""
        self.assertEqual({}, pr.ler(self.csv))

    def test_a_celula_vazia_e_uma_ausencia_declarada(self) -> None:
        """Diferente de a linha não existir: uma é "não se sabe", a outra é "não se procurou"."""
        registro = pr.ler(self._escrever("aaaa,,,,\n"))
        self.assertEqual(pr.DESCONHECIDA, registro["aaaa"].procedencia)
        self.assertFalse(registro["aaaa"].tem_livro)
        self.assertIsNone(registro["aaaa"].pagina)

    def test_a_linha_completa_vira_registro(self) -> None:
        registro = pr.ler(self._escrever("aaaa,Yusupov Build Up 1,212,humano,2026-02-16\n"))
        self.assertEqual("Yusupov Build Up 1", registro["aaaa"].livro)
        self.assertEqual(212, registro["aaaa"].pagina)
        self.assertTrue(registro["aaaa"].mede)

    def test_so_o_humano_mede_o_modelo(self) -> None:
        registro = pr.ler(self._escrever("a,L,1,humano,\nb,L,1,modelo,\nc,L,1,desconhecida,\n"))
        self.assertEqual([True, False, False], [registro[k].mede for k in ("a", "b", "c")])

    def test_procedencia_que_nao_existe_levanta_em_vez_de_virar_desconhecida(self) -> None:
        """Tratar valor estranho como "desconhecida" perderia a diferença entre erro e ausência."""
        with self.assertRaises(pr.ArquivoInvalido):
            pr.ler(self._escrever("aaaa,L,1,conferido-por-ia,\n"))

    def test_coluna_faltando_levanta(self) -> None:
        self.csv.write_text("uuid,procedencia\naaaa,humano\n", encoding="utf-8")
        with self.assertRaises(pr.ArquivoInvalido):
            pr.ler(self.csv)

    def test_uuid_vazio_levanta_dizendo_a_linha(self) -> None:
        with self.assertRaises(pr.ArquivoInvalido) as erro:
            pr.ler(self._escrever(",L,1,humano,\n"))
        self.assertIn("linha 2", str(erro.exception))

    def test_o_resumo_diz_o_que_o_arquivo_trouxe(self) -> None:
        self.assertIn("sem registro", pr.resumo({}))
        registro = pr.ler(self._escrever("a,L,1,humano,\nb,M,1,modelo,\n"))
        texto = pr.resumo(registro)
        self.assertIn("1 humano", texto)
        self.assertIn("2 livro(s)", texto)


class ViolacoesTests(unittest.TestCase):
    """O que o `cvoff-audit` cobra do último split da base de caractere."""

    BASE = {
        "grupos_em_dois_lados": 0,
        "livros_em_dois_lados": 0,
        "procedencia_por_lado": {"teste": {pr.HUMANO: 100}},
        "registro_de_procedencia": "120 recorte(s) registrado(s): 100 humano, 0 modelo, 20 desconhecida; 3 livro(s)",
        "desconhecida_no_teste_permitida": False,
    }

    def test_o_split_limpo_nao_tem_violacao(self) -> None:
        self.assertEqual([], pr.violacoes_do_split(self.BASE))

    def test_grupo_em_dois_lados_e_violacao(self) -> None:
        achados = pr.violacoes_do_split({**self.BASE, "grupos_em_dois_lados": 3})
        self.assertTrue(any("cópia exata" in a for a in achados))

    def test_livro_em_dois_lados_e_violacao(self) -> None:
        achados = pr.violacoes_do_split({**self.BASE, "livros_em_dois_lados": 1})
        self.assertTrue(any("livro" in a for a in achados))

    def test_o_audit_falha_com_rotulo_de_modelo_no_teste(self) -> None:
        """O achado nº 1 da avaliação de agosto, e ele não tem atenuante."""
        achados = pr.violacoes_do_split(
            {**self.BASE, "procedencia_por_lado": {"teste": {pr.HUMANO: 90, pr.MODELO: 10}}}
        )
        self.assertEqual(1, len(achados))
        self.assertIn("rótulo de modelo", achados[0])

    def test_amostra_sem_procedencia_no_teste_e_violacao_quando_ha_registro(self) -> None:
        achados = pr.violacoes_do_split(
            {**self.BASE, "procedencia_por_lado": {"teste": {pr.DESCONHECIDA: 7}}}
        )
        self.assertEqual(1, len(achados))
        self.assertIn("sem procedência", achados[0])

    def test_sem_registro_nenhum_a_desconhecida_no_teste_nao_reprova(self) -> None:
        """Reprovar aqui seria reprovar o único número que existe. A ressalva vai no relatório."""
        achados = pr.violacoes_do_split(
            {
                **self.BASE,
                "procedencia_por_lado": {"teste": {pr.DESCONHECIDA: 13693}},
                "registro_de_procedencia": "sem registro de procedência: toda amostra entra como desconhecida",
            }
        )
        self.assertEqual([], achados)

    def test_a_permissao_explicita_cala_a_violacao_e_fica_registrada(self) -> None:
        achados = pr.violacoes_do_split(
            {
                **self.BASE,
                "procedencia_por_lado": {"teste": {pr.DESCONHECIDA: 7}},
                "desconhecida_no_teste_permitida": True,
            }
        )
        self.assertEqual([], achados)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
