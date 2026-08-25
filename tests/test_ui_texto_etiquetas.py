"""A tradução entre documento e etiquetas do Tk, **sem abrir janela** (S-238).

O `dump` do Tk devolve trincas de `str`, e transformá-las em documento é decisão pura. O que este
arquivo trava é a propriedade que faz o arquivo do editor valer alguma coisa: **a ida e a volta são
a mesma tabela**, e não duas que envelhecem separadas.
"""

from __future__ import annotations

import unittest
from dataclasses import fields

from chess_diagram_ocr.text import documento, rico
from chess_diagram_ocr.ui import texto_etiquetas as te


def _corrida(**campos) -> rico.Corrida:  # noqa: ANN003
    campos.setdefault("texto", "x")
    return rico.Corrida(**campos)


class IdaEVoltaTests(unittest.TestCase):
    def test_a_ida_e_volta_e_identidade(self) -> None:
        """A propriedade do módulo inteiro: desenhar e reler devolve a mesma corrida."""
        casos = [
            _corrida(),
            _corrida(faixa=documento.REVISAR),
            _corrida(faixa=documento.CONFERIR, atributos=rico.Atributos(negrito=True)),
            _corrida(bloco=7),
            _corrida(procedencia="glifo"),
            _corrida(procedencia="humano", bloco=0, faixa=documento.REVISAR),
            _corrida(texto="[Diagrama 3]", tipo=rico.DIAGRAMA, bloco=2, procedencia="glifo"),
            _corrida(texto="\n\n", tipo=rico.SEPARADOR),
        ]
        for corrida in casos:
            with self.subTest(corrida=corrida):
                self.assertEqual(te.corrida_de(corrida.texto, te.etiquetas_de(corrida)), corrida)

    def test_a_ordem_das_etiquetas_e_fixa(self) -> None:
        corrida = _corrida(
            faixa=documento.REVISAR,
            atributos=rico.Atributos(negrito=True),
            bloco=3,
            procedencia="glifo",
        )
        self.assertEqual(
            te.etiquetas_de(corrida), (documento.REVISAR, "negrito", "bloco:3", "proc:glifo")
        )

    def test_a_corrida_padrao_leva_so_a_faixa(self) -> None:
        self.assertEqual(te.etiquetas_de(_corrida()), (documento.TRANQUILO,))

    def test_a_marca_do_diagrama_nao_leva_faixa(self) -> None:
        """A marca é referência ao diagrama, e não texto lido: a régua de confiança não a alcança."""
        corrida = _corrida(texto="[Diagrama 1]", tipo=rico.DIAGRAMA, faixa=documento.REVISAR)
        self.assertEqual(te.etiquetas_de(corrida), (te.MARCA,))


class TabelaDeAtributosTests(unittest.TestCase):
    def test_todo_booleano_de_atributo_foi_decidido(self) -> None:
        """Ou se desenha, ou se declara que ainda não. Atributo novo em silêncio some na gravação."""
        booleanos = {c.name for c in fields(rico.Atributos) if c.type in ("bool", bool)}
        decididos = set(te.ETIQUETA_DO_ATRIBUTO) | set(te.SEM_ETIQUETA)
        self.assertEqual(booleanos, decididos)

    def test_toda_etiqueta_mapeia_um_campo_que_existe(self) -> None:
        campos = {c.name for c in fields(rico.Atributos)}
        self.assertLessEqual(set(te.ETIQUETA_DO_ATRIBUTO), campos)

    def test_o_que_ainda_nao_se_desenha_nao_tem_etiqueta(self) -> None:
        self.assertEqual(set(te.SEM_ETIQUETA) & set(te.ETIQUETA_DO_ATRIBUTO), set())


class PerdoaOQueNaoEntendeTests(unittest.TestCase):
    """Esta função roda no caminho de **salvar**: etiqueta estragada não pode custar o trabalho."""

    def test_etiqueta_desconhecida_e_ignorada(self) -> None:
        self.assertEqual(te.corrida_de("x", ["coisa-nova"]), _corrida())

    def test_bloco_ilegivel_vira_sem_bloco(self) -> None:
        self.assertEqual(te.corrida_de("x", ["bloco:abc"]).bloco, rico.SEM_BLOCO)

    def test_procedencia_desconhecida_vira_nenhuma(self) -> None:
        self.assertIsNone(te.corrida_de("x", ["proc:chute"]).procedencia)

    def test_sem_etiqueta_nenhuma_vira_texto_comum(self) -> None:
        corrida = te.corrida_de("digitado", [])
        self.assertEqual(corrida.tipo, rico.TEXTO)
        self.assertEqual(corrida.bloco, rico.SEM_BLOCO)
        self.assertIsNone(corrida.procedencia)


class DespejoTests(unittest.TestCase):
    def test_o_despejo_vira_documento(self) -> None:
        despejo = [
            ("tagon", "tranquilo", "1.0"),
            ("text", "prosa", "1.0"),
            ("tagoff", "tranquilo", "1.5"),
            ("tagon", "marca", "1.5"),
            ("text", "[Diagrama 1]", "1.5"),
            ("tagoff", "marca", "1.17"),
        ]
        doc = te.de_despejo(despejo)
        self.assertEqual(doc.para_texto(), "prosa[Diagrama 1]")
        self.assertEqual([c.tipo for c in doc.corridas], [rico.TEXTO, rico.DIAGRAMA])

    def test_a_imagem_e_ignorada_e_a_marca_nao(self) -> None:
        """A miniatura morre com o widget; `[Diagrama N]` é texto e volta inteiro."""
        despejo = [
            ("image", "img#1", "1.0"),
            ("tagon", "marca", "1.1"),
            ("text", "[Diagrama 1]", "1.1"),
        ]
        self.assertEqual(te.de_despejo(despejo).para_texto(), "[Diagrama 1]")

    def test_a_quebra_do_desenho_nao_entra_no_documento(self) -> None:
        """Sem isto, uma quebra a mais entraria a cada salvar-e-reabrir, para sempre."""
        despejo = [
            ("tagon", te.DESENHO, "1.0"),
            ("text", "\n", "1.0"),
            ("tagoff", te.DESENHO, "2.0"),
            ("tagon", "marca", "2.0"),
            ("text", "[Diagrama 1]", "2.0"),
        ]
        self.assertEqual(te.de_despejo(despejo).para_texto(), "[Diagrama 1]")

    def test_as_marcas_do_cursor_sao_ignoradas(self) -> None:
        despejo = [("mark", "insert", "1.0"), ("text", "oi", "1.0"), ("mark", "current", "1.2")]
        self.assertEqual(te.de_despejo(despejo).para_texto(), "oi")

    def test_pedacos_iguais_saem_fundidos(self) -> None:
        """O Tk parte o texto em cada fronteira de etiqueta; o documento não guarda essas emendas."""
        despejo = [("text", "uma ", "1.0"), ("text", "palavra", "1.4")]
        doc = te.de_despejo(despejo)
        self.assertEqual(len(doc.corridas), 1)
        self.assertEqual(doc.para_texto(), "uma palavra")

    def test_a_origem_vem_de_fora(self) -> None:
        """O widget não tem como devolver a `PaginaLida`; quem a guarda é o painel."""
        self.assertIsNone(te.de_despejo([("text", "oi", "1.0")]).origem)


class FronteiraTests(unittest.TestCase):
    def test_o_modulo_nao_importa_tkinter(self) -> None:
        import ast
        from pathlib import Path

        arvore = ast.parse(Path(te.__file__).read_text(encoding="utf-8"))
        importados: set[str] = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                importados.update(alias.name.split(".")[0] for alias in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module:
                importados.add(no.module.split(".")[0])
        self.assertNotIn("tkinter", importados)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
