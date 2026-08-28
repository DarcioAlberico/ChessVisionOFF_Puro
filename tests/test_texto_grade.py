"""A régua da grade: a direção medida contra o número impresso, e não contra a camada (S-216).

**O teste que dá nome a este arquivo é
`test_a_camada_pode_discordar_do_numero_impresso_e_o_relatorio_conta`.** É o achado que
desqualifica o `tau` como árbitro de grade: nos três livros de grade do acervo a camada de texto
é do `Adobe Acrobat Paper Capture`, e medida contra o número impresso ela erra a direção nos dois
sentidos. Aqui isso é reproduzido em PDF sintético -- uma página cuja numeração impressa atravessa
as colunas e cuja **ordem de emissão** desce por dentro delas.

Os PDFs são construídos com `fitz`, como em `test_texto_ordem.py`: nada aqui depende do acervo.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz

from chess_diagram_ocr.cli import texto_grade as grade
from chess_diagram_ocr.text.grade import FRACAO_DE_VAO

ESQUERDA = 60.0
DIREITA = 340.0
FILEIRAS = (150.0, 400.0, 650.0)
"""Três fileiras a 250 px uma da outra. O vão é a altura de um tabuleiro, e não o entrelinha."""


def _celulas(*, por_fileira: bool) -> list[tuple[int, float, float]]:
    """`(numero, x, y)` das seis células, numeradas nas duas convenções do acervo.

    `por_fileira=True` é o `Karpov`/`Burgess` (1 2 / 3 4 / 5 6); `False` é o
    `Schiller`/`Secrets` (1 4 / 2 5 / 3 6).
    """
    saida: list[tuple[int, float, float]] = []
    for fileira, y in enumerate(FILEIRAS):
        for coluna, x in enumerate((ESQUERDA, DIREITA)):
            numero = 1 + (fileira * 2 + coluna if por_fileira else coluna * len(FILEIRAS) + fileira)
            saida.append((numero, x, y))
    return saida


class _ComPdf(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = TemporaryDirectory()
        self.raiz = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)

    def _pdf(
        self,
        celulas: list[tuple[int, float, float]],
        *,
        nome: str = "livro.pdf",
        producer: str | None = None,
    ) -> Path:
        """Grava as células **na ordem em que vêm na lista** -- é ela que vira a ordem de emissão."""
        doc = fitz.open()
        page = doc.new_page(width=595.0, height=842.0)
        for numero, x, y in celulas:
            page.insert_text((x, y), f"{numero} White to move", fontsize=11)
        if producer is not None:
            doc.set_metadata({"producer": producer})
        caminho = self.raiz / nome
        doc.save(caminho)
        doc.close()
        return caminho

    def _medir(self, caminho: Path) -> grade.PaginaDeGrade:
        with fitz.open(caminho) as doc:
            resultado = grade.medir_pagina(doc[0])
        assert resultado is not None, "a página sintética não foi medida"
        return resultado


class PaginaTests(_ComPdf):
    def test_a_grade_esparsa_e_reconhecida_como_grade(self) -> None:
        resultado = self._medir(self._pdf(_celulas(por_fileira=True)))
        self.assertTrue(resultado.e_grade)
        self.assertEqual(2, resultado.colunas)
        self.assertGreater(resultado.fracao_de_vao, FRACAO_DE_VAO)

    def test_a_prosa_densa_nao_e_grade(self) -> None:
        """Mesmas duas colunas, sem vão entre fileiras: é o par de fixtures do item, aqui em PDF."""
        densa = [
            (fileira * 2 + coluna, x, 100.0 + fileira * 16.0)
            for fileira in range(20)
            for coluna, x in enumerate((ESQUERDA, DIREITA))
        ]
        self.assertFalse(self._medir(self._pdf(densa)).e_grade)

    def test_a_numeracao_atravessando_as_colunas_diz_grade(self) -> None:
        resultado = self._medir(self._pdf(_celulas(por_fileira=True)))
        self.assertEqual("grade", resultado.direcao_impressa)

    def test_a_numeracao_descendo_a_coluna_diz_prosa(self) -> None:
        resultado = self._medir(self._pdf(_celulas(por_fileira=False)))
        self.assertEqual("prosa", resultado.direcao_impressa)

    def test_a_camada_pode_discordar_do_numero_impresso_e_o_relatorio_conta(self) -> None:
        """**O achado que move o item.** A página é numerada atravessando as colunas, e a camada
        de texto emite descendo por dentro delas. As duas respostas saem separadas, e é o desacordo
        entre elas que diz que o `tau` não pode arbitrar isto.
        """
        atravessando = _celulas(por_fileira=True)
        emitida_por_coluna = sorted(atravessando, key=lambda c: (c[1], c[2]))
        resultado = self._medir(self._pdf(emitida_por_coluna))
        self.assertEqual("grade", resultado.direcao_impressa, "o número impresso atravessa as colunas")
        self.assertEqual("prosa", resultado.direcao_emitida, "a camada emitiu coluna a coluna")

    def test_a_pagina_curta_demais_nao_e_medida(self) -> None:
        self.assertIsNone(self._medir_ou_nada(self._pdf([(1, ESQUERDA, 150.0)])))

    def _medir_ou_nada(self, caminho: Path) -> grade.PaginaDeGrade | None:
        with fitz.open(caminho) as doc:
            return grade.medir_pagina(doc[0])


def _pagina(
    direcao: str | None,
    *,
    e_grade: bool = True,
    camada: str | None = None,
) -> grade.PaginaDeGrade:
    """Uma página medida. `camada` fabrica o `tau` que faria a camada opinar naquela direção."""
    taus: dict[str, float] = {}
    if camada == "grade":
        taus = {"tau_prosa": 0.30, "tau_grade": 0.02}
    elif camada == "prosa":
        taus = {"tau_prosa": 0.02, "tau_grade": 0.30}
    elif camada == "empate":
        taus = {"tau_prosa": 0.10, "tau_grade": 0.10}
    return grade.PaginaDeGrade(
        pagina=1,
        e_grade=e_grade,
        fracao_de_vao=0.7,
        colunas=2,
        direcao_impressa=direcao,
        direcao_emitida=None,
        **taus,
    )


class CalibrarTests(unittest.TestCase):
    """A direção é constante por livro, e o piso existe para o livro que não for."""

    def test_o_livro_unanime_e_calibrado_pelo_numero_impresso(self) -> None:
        calibracao = grade.calibrar([_pagina("grade")] * 5)
        self.assertEqual(("grade", "numero impresso"), (calibracao.arranjo, calibracao.fonte))
        self.assertFalse(calibracao.hipotese)
        self.assertEqual((5, 0), (calibracao.votos_impressos_grade, calibracao.votos_impressos_prosa))

    def test_o_livro_dividido_fica_indefinido_e_segue_em_prosa(self) -> None:
        """Abaixo do piso de concordância a resposta é "não sei", e não a maioria simples.

        `indefinido` significa que o livro continua em `prosa`, que é o lado seguro do erro.
        """
        calibracao = grade.calibrar([_pagina("grade")] * 3 + [_pagina("prosa")] * 2)
        self.assertEqual("indefinido", calibracao.arranjo)
        self.assertEqual("nenhuma", calibracao.fonte)

    def test_a_pagina_que_nao_e_grade_nao_vota(self) -> None:
        """Prosa não tem opinião sobre a direção de uma grade; deixá-la votar dilui o sinal."""
        calibracao = grade.calibrar([_pagina("grade"), _pagina("prosa", e_grade=False)])
        self.assertEqual("grade", calibracao.arranjo)

    def test_o_livro_sem_voto_nenhum_fica_indefinido(self) -> None:
        self.assertEqual("indefinido", grade.calibrar([_pagina(None)] * 4).arranjo)


class HipoteseTests(unittest.TestCase):
    """A segunda urna: a camada calibra o livro que o número impresso não alcança."""

    def test_uma_pagina_unanime_nao_calibra_um_livro(self) -> None:
        """**Achado da primeira execução: o `Neumann` foi calibrado com um voto.**

        Uma página unânime é unânime consigo mesma, e o piso de concordância não pega isso --
        1 de 1 é 100%. Quem pega é `VOTOS_MINIMOS_DA_CAMADA`.
        """
        poucas = grade.VOTOS_MINIMOS_DA_CAMADA - 1
        self.assertEqual("indefinido", grade.calibrar([_pagina(None, camada="grade")] * poucas).arranjo)
        self.assertEqual("indefinido", grade.calibrar([_pagina(None, camada="grade")]).arranjo)

    def test_o_piso_de_votos_nao_vale_para_o_numero_impresso(self) -> None:
        """Três verdades bastam; três palpites não. É o `Secrets`, calibrado com 3 páginas."""
        poucas = grade.VOTOS_MINIMOS_DA_CAMADA - 1
        calibracao = grade.calibrar([_pagina("prosa")] * min(3, poucas))
        self.assertEqual(("prosa", "numero impresso"), (calibracao.arranjo, calibracao.fonte))

    def test_sem_numero_impresso_a_camada_calibra_como_hipotese(self) -> None:
        """É o caso do `Yusupov`: 64 páginas de grade e nenhum número legível na camada."""
        calibracao = grade.calibrar([_pagina(None, camada="grade")] * 8)
        self.assertEqual(("grade", "camada"), (calibracao.arranjo, calibracao.fonte))
        self.assertTrue(calibracao.hipotese)
        self.assertEqual((8, 0), (calibracao.votos_da_camada_grade, calibracao.votos_da_camada_prosa))

    def test_o_numero_impresso_vence_a_camada_quando_os_dois_falam(self) -> None:
        """**O teste que sustenta a ordem das duas urnas, e é o caso do `Secrets`.**

        Lá a numeração impressa diz `prosa` e a camada diz `grade` com unanimidade -- e a camada
        está errada. Onde há número impresso, a camada não é nem consultada para decidir.
        """
        calibracao = grade.calibrar([_pagina("prosa", camada="grade")] * 3)
        self.assertEqual(("prosa", "numero impresso"), (calibracao.arranjo, calibracao.fonte))
        self.assertFalse(calibracao.hipotese)
        # E o voto da camada fica registrado, contra o qual ela perdeu.
        self.assertEqual(3, calibracao.votos_da_camada_grade)

    def test_a_camada_dividida_nao_vira_hipotese(self) -> None:
        """Cara ou coroa não é direção. Metade e metade fica `indefinido`, e o livro segue prosa."""
        paginas = [_pagina(None, camada="grade")] * 5 + [_pagina(None, camada="prosa")] * 5
        self.assertEqual("indefinido", grade.calibrar(paginas).arranjo)

    def test_o_empate_no_tau_nao_e_opiniao(self) -> None:
        self.assertIsNone(grade.direcao_pela_camada(_pagina(None, camada="empate")))
        self.assertEqual("indefinido", grade.calibrar([_pagina(None, camada="empate")] * 6).arranjo)

    def test_a_pagina_sem_tau_nao_opina(self) -> None:
        """Referência fora de ordem: ali o `tau` mede a camada, e não a nossa leitura."""
        self.assertIsNone(grade.direcao_pela_camada(_pagina(None)))

    def test_a_camada_prefere_a_leitura_de_tau_menor(self) -> None:
        self.assertEqual("grade", grade.direcao_pela_camada(_pagina(None, camada="grade")))
        self.assertEqual("prosa", grade.direcao_pela_camada(_pagina(None, camada="prosa")))


class ProcedenciaTests(_ComPdf):
    """De onde veio a camada de texto -- é ela que diz quanto a referência da S-194 vale ali."""

    def test_o_pdf_gerado_por_typesetter_nao_e_acusado_de_ocr(self) -> None:
        with fitz.open(self._pdf(_celulas(por_fileira=True))) as doc:
            self.assertIsNone(grade.camada_de_ocr(doc))

    def test_o_paper_capture_se_denuncia_no_producer(self) -> None:
        caminho = self._pdf(
            _celulas(por_fileira=True), producer="Adobe Acrobat 9.0 Paper Capture Plug-in"
        )
        with fitz.open(caminho) as doc:
            self.assertEqual("paper capture", grade.camada_de_ocr(doc))


class TauAgregadoTests(unittest.TestCase):
    """A tabela que decide o item mora no relatório, e não só no documento."""

    LIVROS = {
        "grande_em_prosa.pdf": {"paginas_com_tau": 90, "arranjo": "prosa", "tau_prosa": 0.00, "tau_grade": 0.20},
        "pequeno_em_grade.pdf": {"paginas_com_tau": 10, "arranjo": "grade", "tau_prosa": 0.30, "tau_grade": 0.05},
    }

    def test_a_media_e_por_pagina_e_nao_por_livro(self) -> None:
        """E é essa diferença de tamanho que faz o agregado ser o critério errado para a direção."""
        tau = grade._tau_agregado(dict(self.LIVROS))
        self.assertEqual(100, tau["paginas"])
        self.assertAlmostEqual(0.03, tau["prosa"])       # (90*0,00 + 10*0,30) / 100
        self.assertAlmostEqual(0.185, tau["grade"])      # (90*0,20 + 10*0,05) / 100
        self.assertAlmostEqual(0.005, tau["calibrado"])  # (90*0,00 + 10*0,05) / 100

    def test_ligar_grade_para_todos_seria_pior_que_calibrar(self) -> None:
        """O número que reprova o atalho: um livro grande em prosa domina a média."""
        tau = grade._tau_agregado(dict(self.LIVROS))
        self.assertLess(tau["calibrado"], tau["prosa"])
        self.assertLess(tau["calibrado"], tau["grade"])

    def test_o_livro_indefinido_conta_como_prosa(self) -> None:
        """Ele *recebe* prosa; contá-lo de outro jeito mediria um mundo que não existe."""
        livros = {"x.pdf": {"paginas_com_tau": 4, "arranjo": "indefinido", "tau_prosa": 0.4, "tau_grade": 0.1}}
        self.assertAlmostEqual(0.4, grade._tau_agregado(livros)["calibrado"])

    def test_sem_pagina_com_tau_nao_inventa_media(self) -> None:
        self.assertEqual(
            {"paginas": 0, "prosa": None, "grade": None, "calibrado": None, "so_confirmado": None},
            grade._tau_agregado({"x.pdf": {"paginas_com_tau": 0}}),
        )

    def test_a_hipotese_sai_separada_do_numero_confirmado(self) -> None:
        """**O ganho apoiado em palpite não pode sumir dentro do número bom.**

        `calibrado` aplica a hipótese; `so_confirmado` a lê como prosa. A diferença entre os dois
        é exatamente o que a S-188 vai confirmar ou desmentir.
        """
        livros = {
            "confirmado.pdf": {
                "paginas_com_tau": 10, "arranjo": "grade", "hipotese": False,
                "tau_prosa": 0.30, "tau_grade": 0.05,
            },
            "palpitado.pdf": {
                "paginas_com_tau": 10, "arranjo": "grade", "hipotese": True,
                "tau_prosa": 0.20, "tau_grade": 0.04,
            },
        }
        tau = grade._tau_agregado(livros)
        self.assertAlmostEqual(0.045, tau["calibrado"])       # (0,05 + 0,04) / 2
        self.assertAlmostEqual(0.125, tau["so_confirmado"])   # (0,05 + 0,20) / 2
        self.assertLess(tau["calibrado"], tau["so_confirmado"], "a hipótese só pode melhorar o número")


class ComandoTests(_ComPdf):
    def test_sem_pdf_nenhum_nao_derruba(self) -> None:
        self.assertEqual(0, grade.main(["--pdf-dir", str(self.raiz), "--saida", str(self.raiz / "s.json")]))

    def test_o_relatorio_traz_o_arranjo_calibrado_do_livro(self) -> None:
        self._pdf(_celulas(por_fileira=True))
        saida = self.raiz / "s.json"
        self.assertEqual(0, grade.main(["--pdf-dir", str(self.raiz), "--saida", str(saida)]))
        relatorio = json.loads(saida.read_text(encoding="utf-8"))
        self.assertEqual("grade", relatorio["por_livro"]["livro.pdf"]["arranjo"])
        self.assertEqual(1.0, relatorio["acerto"])
        # A tabela que a S-216 cita mora aqui, e não só no documento: se o campo sair, a spec
        # passa a afirmar um número que nada produz -- que é a cicatriz da S-135.
        self.assertEqual(
            {"paginas", "prosa", "grade", "calibrado", "so_confirmado"}, set(relatorio["tau"])
        )
        self.assertEqual(1, relatorio["tau"]["paginas"])
        self.assertIn("emissao_contra_impresso", relatorio)
        self.assertEqual([], relatorio["hipoteses"]["livros"], "este livro tem número impresso")
        self.assertFalse(relatorio["por_livro"]["livro.pdf"]["hipotese"])

    def test_o_livro_sem_numero_impresso_e_calibrado_por_hipotese(self) -> None:
        """**O caso do `Yusupov`, reproduzido**: grade sem número legível, e a camada opinando.

        A legenda não tem inteiro nenhum, então a primeira urna fica vazia; a camada emitiu
        atravessando as colunas, e é ela que dá a direção -- marcada como hipótese.
        """
        doc = fitz.open()
        # Um livro, e não uma página: abaixo de `VOTOS_MINIMOS_DA_CAMADA` a hipótese é sobre a
        # página que calhou de ser lida, e não sobre o livro. Ver o `Neumann`.
        for _ in range(grade.VOTOS_MINIMOS_DA_CAMADA):
            page = doc.new_page(width=595.0, height=842.0)
            for _, x, y in _celulas(por_fileira=True):  # a ordem da lista é a de emissão
                page.insert_text((x, y), "White to move", fontsize=11)
        doc.save(self.raiz / "sem_numero.pdf")
        doc.close()

        saida = self.raiz / "s.json"
        self.assertEqual(0, grade.main(["--pdf-dir", str(self.raiz), "--saida", str(saida)]))
        relatorio = json.loads(saida.read_text(encoding="utf-8"))
        livro = relatorio["por_livro"]["sem_numero.pdf"]

        self.assertEqual(("grade", "camada", True), (livro["arranjo"], livro["fonte"], livro["hipotese"]))
        self.assertEqual(0, livro["paginas_decidiveis"], "não há número impresso a decidir")
        self.assertEqual(["sem_numero.pdf"], relatorio["hipoteses"]["livros"])
        # **E ela não entra na régua.** O `acerto` mede a calibração contra o número impresso, e
        # a hipótese não tem número impresso -- contá-la inflaria o portão com o próprio palpite.
        self.assertIsNone(relatorio["acerto"])

    def test_o_baseline_que_nao_existe_falha(self) -> None:
        self._pdf(_celulas(por_fileira=True))
        codigo = grade.main(
            [
                "--pdf-dir", str(self.raiz),
                "--saida", str(self.raiz / "s.json"),
                "--baseline", str(self.raiz / "nao.json"),
            ]
        )
        # Caminho apontado que não existe é a classe 2 da S-126, e não a 1 (S-378).
        self.assertEqual(2, codigo)

    def test_o_baseline_inexistente_e_recusado_antes_de_medir(self) -> None:
        """Horas de varredura não podem morrer num caminho digitado errado (S-381).

        A conferência ficava junto da comparação, no fim do comando: o acervo inteiro era lido
        para então dizer que o arquivo não existe.
        """
        from unittest.mock import patch

        self._pdf(_celulas(por_fileira=True))
        with patch.object(grade, "medir", side_effect=AssertionError("mediu antes de conferir")):
            codigo = grade.main(
                [
                    "--pdf-dir", str(self.raiz),
                    "--saida", str(self.raiz / "s.json"),
                    "--baseline", str(self.raiz / "nao.json"),
                ]
            )
        self.assertEqual(2, codigo)
        self.assertFalse((self.raiz / "s.json").exists(), "nada foi medido, nada foi gravado")

    def test_o_baseline_falha_quando_o_acerto_cai(self) -> None:
        """Regressão de calibração é regressão -- mesmo desenho do `cvoff-texto-ordem --baseline`."""
        self._pdf(_celulas(por_fileira=True))
        baseline = self.raiz / "base.json"
        argumentos = [
            "--pdf-dir", str(self.raiz),
            "--saida", str(self.raiz / "s.json"),
            "--baseline", str(baseline),
        ]

        baseline.write_text(json.dumps({"acerto": 1.0}), encoding="utf-8")
        self.assertEqual(0, grade.main(argumentos), "o acerto não caiu; não podia falhar")

        baseline.write_text(json.dumps({"acerto": 1.0 + 2 * grade.QUEDA_TOLERADA}), encoding="utf-8")
        self.assertEqual(1, grade.main(argumentos))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
