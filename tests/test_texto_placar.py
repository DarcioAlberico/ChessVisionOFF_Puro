"""O placar que decide se a Fase 26 acontece (S-183).

**A tabela não existe ainda, e isso é o estado normal.** Ela depende de ~60 legendas transcritas
à mão, que é trabalho humano. O que se pode travar antes disso são as duas réguas e o formato do
conjunto -- e travá-las agora é o que impede a tabela de nascer medindo a coisa errada.
"""

from __future__ import annotations

import json
import logging
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz

from chess_diagram_ocr.cli import texto_placar as placar


class DistanciaTests(unittest.TestCase):
    def test_a_distancia_de_edicao_conta_as_tres_operacoes(self) -> None:
        self.assertEqual(0, placar.distancia_de_edicao("abc", "abc"))
        self.assertEqual(1, placar.distancia_de_edicao("abc", "abd"))  # troca
        self.assertEqual(1, placar.distancia_de_edicao("abc", "ab"))  # remoção
        self.assertEqual(1, placar.distancia_de_edicao("abc", "abcd"))  # inserção
        self.assertEqual(3, placar.distancia_de_edicao("", "abc"))

    def test_o_exemplo_que_a_f17_usa(self) -> None:
        """`Bib1i0g[aPhY` -> `Bibliography`: 5 caracteres de distância, e nenhum decidível só."""
        self.assertEqual(5, placar.distancia_de_edicao("Bib1i0g[aPhY", "Bibliography"))


class CerTests(unittest.TestCase):
    def test_leitura_perfeita_da_zero(self) -> None:
        self.assertEqual(0.0, placar.cer("Hickl - Yusupov", "Hickl - Yusupov"))

    def test_o_espaco_e_colapsado_e_o_acento_fica(self) -> None:
        """Derrubar acento aqui esconderia a ressalva da S-42 sobre o modelo `ch`+`en`."""
        self.assertEqual(0.0, placar.cer("Hickl  -   Yusupov", "Hickl - Yusupov"))
        self.assertGreater(placar.cer("La Combinacion", "La Combinación"), 0.0)

    def test_o_motor_que_inventa_passa_de_um(self) -> None:
        """**Não é truncado em 1,0 de propósito.**

        Um motor que devolve o dobro de caracteres da referência é pior que um que não devolve
        nada, e truncar faria os dois empatarem em 1,0 -- que é exatamente a comparação que este
        placar existe para não errar.
        """
        nada = placar.cer("", "Bremen 1998")
        lixo = placar.cer("Bremen 1998 xxxxxxxxxxxxxxxxxxxxxx", "Bremen 1998")
        self.assertAlmostEqual(1.0, nada, places=6)
        self.assertGreater(lixo, nada)

    def test_referencia_vazia_com_leitura_e_infinito(self) -> None:
        """Ler texto onde a página não tem texto não é erro de 100%: é invenção."""
        self.assertEqual(0.0, placar.cer("", ""))
        self.assertEqual(float("inf"), placar.cer("algo", ""))


class CamposTests(unittest.TestCase):
    def test_os_campos_saem_do_mesmo_parse_context_do_pipeline(self) -> None:
        """Medir com outro analisador mediria o analisador, e não o motor."""
        faixa = placar.Faixa(
            pdf="x.pdf",
            pagina=1,
            bbox_pt=(0.0, 0.0, 1.0, 1.0),
            texto="31: Jogada das pretas **",
            lado="b",
            numero=31,
            jogadores=None,
            evento=None,
            ano=None,
        )
        certos = placar.campos_resolvidos(faixa.texto, faixa)
        self.assertTrue(certos["lado"])
        self.assertTrue(certos["numero"])

    def test_campo_que_a_legenda_nao_diz_e_acerto_quando_sai_none(self) -> None:
        """`None` é a resposta certa, e um motor que preenche está inventando."""
        faixa = placar.Faixa(
            pdf="x.pdf",
            pagina=1,
            bbox_pt=(0.0, 0.0, 1.0, 1.0),
            texto="Bremen 1998",
            lado=None,
            numero=None,
            jogadores=None,
            evento="Bremen",
            ano=1998,
        )
        certos = placar.campos_resolvidos(faixa.texto, faixa)
        self.assertTrue(certos["lado"])
        self.assertTrue(certos["numero"])


class ReferenciaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = TemporaryDirectory()
        self.raiz = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)

    def _escrever(self, linhas: list[str]) -> Path:
        caminho = self.raiz / "ref.jsonl"
        caminho.write_text("\n".join(linhas), encoding="utf-8")
        return caminho

    def test_o_exemplo_impresso_pelo_comando_e_uma_linha_valida(self) -> None:
        """O `--exemplo` existe para ser copiado; se ele não carregar, ele engana."""
        caminho = self._escrever([json.dumps(placar.EXEMPLO, ensure_ascii=False)])
        faixas = placar.carregar_referencia(caminho)
        self.assertEqual(1, len(faixas))
        self.assertEqual(("Hickl", "Yusupov"), faixas[0].jogadores)
        self.assertIsNone(faixas[0].lado)

    def test_linha_vazia_e_ignorada(self) -> None:
        caminho = self._escrever([json.dumps(placar.EXEMPLO), "", "   "])
        self.assertEqual(1, len(placar.carregar_referencia(caminho)))

    def test_linha_malformada_levanta_dizendo_o_numero(self) -> None:
        caminho = self._escrever([json.dumps(placar.EXEMPLO), "{nao é json"])
        with self.assertRaisesRegex(placar.ReferenciaInvalida, "linha 2"):
            placar.carregar_referencia(caminho)

    def test_campo_obrigatorio_ausente_e_nomeado(self) -> None:
        incompleto = {k: v for k, v in placar.EXEMPLO.items() if k != "texto"}
        caminho = self._escrever([json.dumps(incompleto)])
        with self.assertRaisesRegex(placar.ReferenciaInvalida, "texto"):
            placar.carregar_referencia(caminho)

    def test_bbox_com_menos_de_quatro_numeros_e_recusado(self) -> None:
        torto = dict(placar.EXEMPLO, bbox_pt=[1.0, 2.0])
        caminho = self._escrever([json.dumps(torto)])
        with self.assertRaisesRegex(placar.ReferenciaInvalida, "bbox_pt"):
            placar.carregar_referencia(caminho)


class MedirTests(unittest.TestCase):
    """A camada de texto medida contra si mesma: o controle do controle."""

    def setUp(self) -> None:
        self._dir = TemporaryDirectory()
        self.raiz = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)

        self.legenda = "72. Steinitz - Bird"
        doc = fitz.open()
        page = doc.new_page(width=595.0, height=842.0)
        page.insert_text((100.0, 200.0), self.legenda, fontsize=11)
        doc.save(self.raiz / "livro.pdf")
        doc.close()
        # O diagrama fica logo abaixo da legenda: o retângulo é o que a `CaptionReader` dilata.
        self.bbox = (100.0, 215.0, 300.0, 415.0)

    def _faixa(self, texto: str) -> placar.Faixa:
        return placar.Faixa(
            pdf="livro.pdf",
            pagina=1,
            bbox_pt=self.bbox,
            texto=texto,
            lado=None,
            numero=72,
            jogadores=("Steinitz", "Bird"),
            evento=None,
            ano=None,
        )

    def test_a_camada_de_texto_le_a_propria_legenda_sem_erro(self) -> None:
        tabela = placar.medir([self._faixa(self.legenda)], (placar.FONTE_CAMADA,), pdf_dir=self.raiz)
        camada = tabela["resultado"][placar.FONTE_CAMADA]
        self.assertEqual(1, camada["n"])
        self.assertAlmostEqual(0.0, camada["cer_medio"], places=6)
        self.assertEqual(1, camada["campos"]["numero"]["certos"])
        self.assertEqual(1, camada["campos"]["jogadores"]["certos"])

    def test_o_n_de_cada_celula_esta_declarado(self) -> None:
        """Uma tabela sem `n` não permite saber se a diferença entre dois motores é ruído."""
        tabela = placar.medir([self._faixa(self.legenda)], (placar.FONTE_CAMADA,), pdf_dir=self.raiz)
        camada = tabela["resultado"][placar.FONTE_CAMADA]
        self.assertIn("n", camada)
        for campo in camada["campos"].values():
            self.assertIn("n", campo)

    def test_o_livro_tem_linha_propria(self) -> None:
        """A decisão se toma nos 7 livros sem camada de texto, e sem quebra por livro não dá."""
        tabela = placar.medir([self._faixa(self.legenda)], (placar.FONTE_CAMADA,), pdf_dir=self.raiz)
        self.assertIn("livro.pdf", tabela["resultado"][placar.FONTE_CAMADA]["por_livro"])

    def test_pdf_ausente_vira_aviso_e_nao_derruba(self) -> None:
        faixa = placar.Faixa(
            pdf="nao_existe.pdf",
            pagina=1,
            bbox_pt=self.bbox,
            texto="x",
            lado=None,
            numero=None,
            jogadores=None,
            evento=None,
            ano=None,
        )
        tabela = placar.medir([faixa], (placar.FONTE_CAMADA,), pdf_dir=self.raiz)
        self.assertEqual(["nao_existe.pdf"], tabela["pdfs_ausentes"])


class ConferidoTests(unittest.TestCase):
    """A recusa do não-conferido é o que sustenta a tabela inteira.

    A semeadura pré-preenche `texto` com o que a **camada de texto** diz, e a camada é uma das
    três fontes medidas. Medi-la contra uma referência copiada dela dá zero por construção. O
    `conferido` é o único ponto do processo em que alguém compara com a página impressa.
    """

    def setUp(self) -> None:
        self._dir = TemporaryDirectory()
        self.raiz = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)

        doc = fitz.open()
        page = doc.new_page(width=595.0, height=842.0)
        page.insert_text((100.0, 200.0), "72. Steinitz - Bird", fontsize=11)
        doc.save(self.raiz / "livro.pdf")
        doc.close()

    def _faixa(self, **extra: object) -> placar.Faixa:
        base: dict[str, object] = {
            "pdf": "livro.pdf",
            "pagina": 1,
            "bbox_pt": (100.0, 215.0, 300.0, 415.0),
            "texto": "72. Steinitz - Bird",
            "lado": None,
            "numero": 72,
            "jogadores": ("Steinitz", "Bird"),
            "evento": None,
            "ano": None,
        }
        base.update(extra)
        return placar.Faixa(**base)  # type: ignore[arg-type]

    def _escrever(self, faixas: list[placar.Faixa]) -> Path:
        caminho = self.raiz / "ref.jsonl"
        caminho.write_text(
            "\n".join(json.dumps(f.para_json(), ensure_ascii=False) for f in faixas), encoding="utf-8"
        )
        return caminho

    def test_faixa_nao_conferida_fica_fora_da_tabela(self) -> None:
        caminho = self._escrever([self._faixa(conferido=False, semeado_de="camada")])
        with self.assertLogs(placar.__name__, level=logging.WARNING) as capturado:
            self.assertEqual(0, placar.main(["--referencia", str(caminho), "--pdf-dir", str(self.raiz)]))
        self.assertIn("conferido: false", "\n".join(capturado.output))

    def test_a_faixa_conferida_entra(self) -> None:
        caminho = self._escrever([self._faixa(conferido=True)])
        saida = self.raiz / "tabela.json"
        self.assertEqual(
            0,
            placar.main(
                [
                    "--referencia", str(caminho),
                    "--pdf-dir", str(self.raiz),
                    "--saida", str(saida),
                    "--fonte", placar.FONTE_CAMADA,
                ]
            ),
        )
        tabela = json.loads(saida.read_text(encoding="utf-8"))
        self.assertEqual(1, tabela["resultado"][placar.FONTE_CAMADA]["n"])
        self.assertEqual(0, tabela["nao_conferidas"])

    def test_a_faixa_semeada_e_nunca_editada_e_contada_como_circular(self) -> None:
        """Marcar `conferido: true` sem mudar o texto deixa a coluna da camada circular.

        A tabela não pode recusar isso -- às vezes a camada **está** certa e o humano confirmou.
        O que ela pode é dizer em quantas células o número não é independente, e é o que faz.
        """
        semente = "72. Steinitz - Bird"
        caminho = self._escrever(
            [self._faixa(conferido=True, semeado_de="camada", texto=semente, texto_semente=semente)]
        )
        saida = self.raiz / "tabela.json"
        placar.main(
            [
                "--referencia", str(caminho),
                "--pdf-dir", str(self.raiz),
                "--saida", str(saida),
                "--fonte", placar.FONTE_CAMADA,
            ]
        )
        self.assertEqual(1, json.loads(saida.read_text(encoding="utf-8"))["circulares_camada"])

    def test_texto_editado_deixa_de_ser_circular(self) -> None:
        caminho = self._escrever(
            [
                self._faixa(
                    conferido=True,
                    semeado_de="camada",
                    texto="72. Steinitz - Bird",
                    texto_semente="72. Ste1n1tz - B1rd",
                )
            ]
        )
        saida = self.raiz / "tabela.json"
        placar.main(
            [
                "--referencia", str(caminho),
                "--pdf-dir", str(self.raiz),
                "--saida", str(saida),
                "--fonte", placar.FONTE_CAMADA,
            ]
        )
        self.assertEqual(0, json.loads(saida.read_text(encoding="utf-8"))["circulares_camada"])

    def test_a_volta_pelo_json_preserva_as_marcas(self) -> None:
        original = self._faixa(conferido=True, semeado_de="camada", texto_semente="x")
        de_volta = placar.Faixa.de_json(original.para_json(), linha=1)
        self.assertEqual(original, de_volta)


class SemearTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = TemporaryDirectory()
        self.raiz = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)

    def test_semear_recusa_sobrescrever_conferencia_humana(self) -> None:
        """Sobrescrever apagaria a coisa mais cara do processo.

        O código é o 2 da tabela da S-126 -- o caminho que se apontou já existe --, e não o 1,
        que é reservado a defeito do programa (S-378).
        """
        existente = self.raiz / "ref.jsonl"
        existente.write_text("", encoding="utf-8")
        with self.assertLogs(placar.__name__, level=logging.ERROR):
            self.assertEqual(2, placar.main(["--semear", "--referencia", str(existente)]))

    def test_sem_pdf_nenhum_nao_derruba(self) -> None:
        with self.assertLogs(placar.__name__, level=logging.WARNING):
            self.assertEqual(
                0,
                placar.main(
                    ["--semear", "--referencia", str(self.raiz / "novo.jsonl"), "--pdf-dir", str(self.raiz)]
                ),
            )

    def test_o_que_e_semeado_sai_com_conferido_falso(self) -> None:
        """**Semear não é conferir.** Uma linha nova nunca pode nascer valendo para a tabela."""
        doc = fitz.open()
        page = doc.new_page(width=595.0, height=842.0)
        page.insert_text((100.0, 100.0), "uma pagina sem diagrama", fontsize=11)
        doc.save(self.raiz / "vazio.pdf")
        doc.close()

        faixas, _ = placar.semear([self.raiz / "vazio.pdf"], por_livro=3)
        for faixa in faixas:
            self.assertFalse(faixa.conferido)

    def test_pdf_que_nao_abre_vira_aviso_e_a_varredura_segue(self) -> None:
        quebrado = self.raiz / "quebrado.pdf"
        quebrado.write_bytes(b"nao e um pdf")
        faixas, avisos = placar.semear([quebrado], por_livro=1)
        self.assertEqual([], faixas)
        self.assertTrue(avisos)


class ComandoTests(unittest.TestCase):
    def test_sem_conjunto_de_referencia_diz_o_que_falta_e_sai_com_zero(self) -> None:
        """Ele é trabalho humano; falhar aqui deixaria a CI vermelha para sempre e por nada."""
        with TemporaryDirectory() as tmp:
            ausente = Path(tmp) / "nao_existe.jsonl"
            with self.assertLogs(placar.__name__, level=logging.WARNING) as capturado:
                self.assertEqual(0, placar.main(["--referencia", str(ausente)]))
            self.assertIn("--exemplo", "\n".join(capturado.output))

    def test_conjunto_vazio_tambem_nao_derruba(self) -> None:
        with TemporaryDirectory() as tmp:
            vazio = Path(tmp) / "vazio.jsonl"
            vazio.write_text("", encoding="utf-8")
            with self.assertLogs(placar.__name__, level=logging.WARNING):
                self.assertEqual(0, placar.main(["--referencia", str(vazio)]))

    def test_o_exemplo_sai_e_o_comando_encerra(self) -> None:
        self.assertEqual(0, placar.main(["--exemplo"]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
