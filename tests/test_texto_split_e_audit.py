"""O relatório de vazamento, e o portão que o `cvoff-audit` faz dele (S-201/S-203).

**O split da base de caractere não existe em disco**, de propósito: ele é função pura da semente
e é refeito a cada corrida, porque a versão que o guardava deixou um conserto sem alcançar quem
lia do cache. O que fica gravado é o que ele produziu -- e é sobre esse relatório que a
auditoria cobra as duas regras que não se pode conferir de outro jeito.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from chess_diagram_ocr.cli.audit import violacoes_do_texto
from chess_diagram_ocr.text import procedencia as pr

LIMPO = {
    "grupos_em_dois_lados": 0,
    "livros_em_dois_lados": 0,
    "procedencia_por_lado": {"teste": {pr.HUMANO: 1000}},
    "registro_de_procedencia": "1.200 recorte(s) registrado(s): 1.000 humano, 0 modelo, 200 desconhecida; 4 livro(s)",
    "desconhecida_no_teste_permitida": False,
}


class AuditoriaDoTextoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.alvo = Path(self.tmp.name) / "texto_vazamento.json"

    def _gravar(self, **mudancas: object) -> Path:
        self.alvo.write_text(json.dumps({**LIMPO, **mudancas}), encoding="utf-8")
        return self.alvo

    def test_sem_relatorio_nao_e_violacao(self) -> None:
        """Um clone limpo não tem o arquivo, e a auditoria de diagramas não pode depender dele."""
        self.assertEqual([], violacoes_do_texto(self.alvo))

    def test_o_relatorio_limpo_nao_reprova(self) -> None:
        self.assertEqual([], violacoes_do_texto(self._gravar()))

    def test_o_audit_falha_com_rotulo_de_modelo_no_teste(self) -> None:
        achados = violacoes_do_texto(
            self._gravar(procedencia_por_lado={"teste": {pr.HUMANO: 900, pr.MODELO: 100}})
        )
        self.assertEqual(1, len(achados))
        self.assertIn("rótulo de modelo", achados[0])

    def test_relatorio_ilegivel_vira_violacao_em_vez_de_silencio(self) -> None:
        self.alvo.write_text("{ isto nao e json", encoding="utf-8")
        achados = violacoes_do_texto(self.alvo)
        self.assertEqual(1, len(achados))
        self.assertIn("não pôde ser lido", achados[0])


class RelatorioDeVazamentoTests(unittest.TestCase):
    """O arquivo que o `--so-split` grava, conferido contra o que a auditoria espera dele."""

    CAMPOS = (
        "split",
        "ressalva",
        "amostras",
        "grupos_em_dois_lados",
        "livros_em_dois_lados",
        "livros",
        "procedencia_por_lado",
        "registro_de_procedencia",
        "desconhecida_no_teste_permitida",
    )

    def test_o_relatorio_publicado_tem_os_campos_que_a_auditoria_le(self) -> None:
        caminho = pr.CAMINHO_DO_VAZAMENTO
        if not caminho.exists():
            self.skipTest("o split ainda não foi feito: rode `cvoff-texto-train --so-split`")
        relatorio = json.loads(caminho.read_text(encoding="utf-8"))
        for campo in self.CAMPOS:
            with self.subTest(campo=campo):
                self.assertIn(campo, relatorio)

    def test_o_relatorio_publicado_esta_aprovado(self) -> None:
        """Se esta falhar, o último split da base de caractere não pode publicar número."""
        caminho = pr.CAMINHO_DO_VAZAMENTO
        if not caminho.exists():
            self.skipTest("o split ainda não foi feito")
        self.assertEqual([], violacoes_do_texto(caminho))

    def test_a_ressalva_do_split_sem_livro_esta_escrita_por_extenso(self) -> None:
        """O número não mede generalização de fonte, e quem o lê tem de ver isso ao lado dele."""
        caminho = pr.CAMINHO_DO_VAZAMENTO
        if not caminho.exists():
            self.skipTest("o split ainda não foi feito")
        relatorio = json.loads(caminho.read_text(encoding="utf-8"))
        if relatorio["split"] == "livro":
            self.assertTrue(relatorio["livros"]["so_no_teste"])
        else:
            self.assertIn("livro", relatorio["ressalva"])


class CorridaComLivroTests(unittest.TestCase):
    """O caminho inteiro do `--so-split` sobre uma base que **tem** livro.

    É o único teste que exercita o comando de ponta a ponta com registro de procedência, e ele
    existe porque foi essa corrida que pegou o defeito: a máscara da S-201 mandava a amostra
    não-medível para o treino, e isso punha o mesmo livro dos dois lados.
    """

    LIVROS = 5
    POR_CLASSE = 40

    def setUp(self) -> None:
        import csv
        import uuid

        import cv2
        import numpy as np

        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        raiz = Path(self.tmp.name)
        self.base = raiz / "training_data"
        self.csv = raiz / "texto_procedencia.csv"
        self.cache = raiz / "cache.npz"
        self.vazamento = raiz / "vazamento.json"

        aleatorio = np.random.default_rng(4)
        linhas = []
        for classe in ("lower_a", "lower_e", "digit_1", "upper_A"):
            (self.base / classe).mkdir(parents=True)
            for i in range(self.POR_CLASSE):
                nome = uuid.UUID(bytes=bytes(aleatorio.integers(0, 256, 16, dtype=np.uint8))).hex
                ok, buffer = cv2.imencode(".png", aleatorio.integers(0, 255, (32, 32), dtype=np.uint8))
                assert ok
                (self.base / classe / f"{nome}.png").write_bytes(buffer.tobytes())
                linhas.append(
                    {
                        "uuid": nome,
                        "livro": f"Livro {i % self.LIVROS}",
                        "pagina": i,
                        # Um a cada sete é rótulo de modelo, e **espalhado**: é a distribuição
                        # que quebra o split por livro se a regra da S-201 for aplicada nele.
                        "procedencia": "humano" if i % 7 else "modelo",
                        "rotulado_em": "2026-08-23",
                    }
                )

        with open(self.csv, "w", encoding="utf-8", newline="") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=list(pr.COLUNAS))
            escritor.writeheader()
            escritor.writerows(linhas)

    def _rodar(self) -> dict:
        from chess_diagram_ocr.cli import texto_train

        codigo = texto_train.main(
            [
                "--so-split",
                "--base", str(self.base),
                "--cache", str(self.cache),
                "--revarrer",
                "--procedencia", str(self.csv),
                "--vazamento", str(self.vazamento),
            ]
        )
        self.assertEqual(0, codigo)
        return json.loads(self.vazamento.read_text(encoding="utf-8"))

    def test_com_livro_o_split_e_por_livro(self) -> None:
        relatorio = self._rodar()
        self.assertEqual("livro", relatorio["split"])
        self.assertEqual(self.LIVROS, relatorio["livros"]["total"])

    def test_existe_um_livro_so_do_teste(self) -> None:
        """O único número que fala sobre fonte nova."""
        self.assertTrue(self._rodar()["livros"]["so_no_teste"])

    def test_nenhum_livro_atravessa_o_split(self) -> None:
        relatorio = self._rodar()
        self.assertEqual(0, relatorio["livros_em_dois_lados"])
        self.assertEqual(0, relatorio["grupos_em_dois_lados"])

    def test_o_rotulo_de_modelo_nao_mede_o_modelo(self) -> None:
        """A regra da S-201 sobrevive ao livro atômico: ela filtra a medição, não o split."""
        relatorio = self._rodar()
        self.assertEqual(0, relatorio["procedencia_por_lado"]["teste"][pr.MODELO])
        self.assertEqual(0, relatorio["procedencia_por_lado"]["validacao"][pr.MODELO])
        self.assertGreater(relatorio["procedencia_por_lado"]["teste"][pr.HUMANO], 0)

    def test_a_corrida_com_livro_passa_na_auditoria(self) -> None:
        self._rodar()
        self.assertEqual([], violacoes_do_texto(self.vazamento))

    def test_o_relatorio_publicado_nao_e_sobrescrito_por_uma_corrida_de_mentira(self) -> None:
        """Uma base sintética não pode virar a base que o `cvoff-audit` audita."""
        antes = pr.CAMINHO_DO_VAZAMENTO.read_bytes() if pr.CAMINHO_DO_VAZAMENTO.exists() else None
        self._rodar()
        depois = pr.CAMINHO_DO_VAZAMENTO.read_bytes() if pr.CAMINHO_DO_VAZAMENTO.exists() else None
        self.assertEqual(antes, depois)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
